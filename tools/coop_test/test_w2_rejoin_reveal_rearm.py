"""W2-H12 - an in-memory SPEC 16 rejoin re-arms the host's hostile reveal set
(spec rewrite/prompts/w2h12_rejoin_reveal_rearm.md (f); SD-2; F3603, F3620,
F3621). ONE boot (test_w2_death_side's default map, lobby PORT_H12): A_ID to
T1, the client leaves, a fresh process (client2) rejoins, the host presses
RESUME. H12-1: the host's hostile set is re-armed and baselined to client2.
H12-2: A_ID to T2 grows it by >= G2 on both machines. H12-3: an END TURN
cycle's boundary hash carries revealHostile. A boot/rejoin step past its bound
is a FIXTURE-STOP (one CAPTURE line; every row FAILs "boot"/"rejoin"). Each
row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <msg>";
every row runs; a staging failure fails later rows "staging". WV-D95/D99/D100:
ONE foreground run, no skip path; exit 0 only when all rows pass, 2 otherwise.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import test_w2_host_combat as hc
from test_w2_death_side import (SEED_MAP_D, MAP_FP_D, A_ID, DS1_ID, DS2_ID, FACTION_PLAYER, FACTION_HOSTILE,
                                COOP_SEAT_0, COOP_SEAT_1)
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, top,
                                         states, has, COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)
from test_w2_delta_core import tele_both, end_turn_cycle, short, desync_record

PORT_H12 = "48497"            # this file's lobby port (unused by every other test file)
# TASK 0 (ledger `## W2-H12 TASK 0`, docs rewrite/w2h12-task0/CONSTANTS.md; F3660: identical on 4 seed-pinned boots)
T1, D1 = (9, 31, 0), 1        # A_ID's first teleport, facing the map centre: hostile floor 318 -> 1081 (+763)
T1_FLOOR = 1081               # the T1 bar: the hostile floor TASK 0 measured at T1 (host = client)
T2, D2 = (31, 9, 0), 5        # H12-2's teleport: hostile floor -> 1724
G2 = 643                      # the measured T2 growth (H12-2's bar)
L0_NEEDLE = "SS2.W4 BASELINE hostile restate (first ev after phase Active): absolute base restate sent (side=hostile"
EMPTY_NEEDLE = "[coop-fog] hostile reveal set allocated EMPTY ("
BASE_RE = re.compile(r"\[coop-reveal\] applied base restate at seq \d+ \(side=hostile, ")
ADD_RE = re.compile(r"\[coop-reveal\] applied add delta at seq \d+ \(side=hostile, \d+ tiles, [1-9]\d* parts "
                    r"newly discovered\)")
IDLE_S, UNPUB_S, LOG_FLUSH_S = 30, 10, 3   # wait_host_idle; unpublishedHostile clears; house log flush

class FixtureMiss(Exception):
    pass

def hostile(gc):
    r = gc.cmd({"cmd": "reveal_state"})
    h = r.get("hostile") or {}
    return {"allocated": h.get("allocated"), "size": h.get("size"),
            "census": [h.get("floor"), h.get("westwall"), h.get("northwall")],
            "mapSizeXYZ": r.get("mapSizeXYZ"), "unpublishedHostile": r.get("unpublishedHostile")}

def rh(gc):
    return (gc.cmd({"cmd": "hash_now", "full": True}).get("h") or {}).get("revealHostile")

def desync_seen(gc):
    return event_state(gc).get("desyncSeen")

def log_count(gc, needle):
    """Lines of this machine's openxcom.log holding `needle` (a literal or a compiled regex; 0 when unreadable)."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if (needle.search(ln) if hasattr(needle, "search") else needle in ln))
    except OSError:
        return 0

def hash_fails(host, gc, what):
    """assert_hash_clean full (equal key sets, then values) plus revealHostile in both."""
    try:
        hh, ch = assert_hash_clean(host, gc, full=True, what=what)
    except AssertionError as e:
        return [f"hash {what}: {short(e, 500)}"]
    return [] if ("revealHostile" in hh and "revealHostile" in ch) else [
        f"hash {what}: revealHostile missing (host {'revealHostile' in hh}, {gc.name} {'revealHostile' in ch})"]

def desync_fails(*machines):
    return [f"desyncSeen true on {gc.name}: {desync_record(gc, True)}" for gc in machines if desync_seen(gc)]

def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)

def miss(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's reveal_state, event_state, dialog and stack (whole), then raise."""
    cap = {}
    for gc in machines:
        cap[gc.name] = {}
        for k, probe in (("reveal_state", lambda g: g.cmd({"cmd": "reveal_state"})),
                         ("event_state", event_state), ("dialog", dialog), ("stack", states)):
            try:
                cap[gc.name][k] = probe(gc)
            except Exception as e:
                cap[gc.name][k] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:400]}")

def step(name, fn, machines):
    try:
        return fn()
    except Exception as e:
        miss(name, short(e, 800), machines)

def boot(host, client):
    """Copy of test_w2_death_side.boot_default on lobby PORT_H12."""
    hc.bring_up_lobby_roster_pinned(host, client, PORT_H12)
    session.drive_to_battlescape(host, client, {}, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP_D}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP_D and cs.get("mapFingerprint") == MAP_FP_D, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {MAP_FP_D!r})")
    assert pin_ai_neutral(host, client, tag="w2h12"), "pin_ai_neutral pinned no NONE-seat non-player unit"
    ub = session.units_by_id(hs)
    for uid, seat in ((DS1_ID, COOP_SEAT_0), (DS2_ID, COOP_SEAT_1)):
        u = ub.get(uid) or {}
        assert (u.get("faction") == FACTION_PLAYER and u.get("coop") == seat and not u.get("isOut")
                and u.get("onTile")), f"unit {uid} at bring-up: {u} (want a live player soldier of seat {seat})"
    a = ub.get(A_ID) or {}
    assert a.get("faction") == FACTION_HOSTILE and not a.get("isOut"), f"alien {A_ID} at bring-up: {a}"
    session.wait_host_idle(host, client, timeout=IDLE_S)
    assert_hash_clean(host, client, full=True, what="bring-up")

def wait_unpublished_clear(host):
    host.wait_for("host unpublishedHostile false",
                  lambda: (hostile(host)["unpublishedHostile"] is False) or None, timeout=UNPUB_S)

def stage_boot(host, client, ctx):
    """Boot, A_ID to T1, census and hash with revealHostile; record P (D219 evidence) and L0 (must be 1)."""
    m = (host, client)
    step("boot", lambda: boot(host, client), m)
    step("tele_both T1", lambda: tele_both(host, client, A_ID, T1, D1), m)
    step("wait_host_idle after T1", lambda: session.wait_host_idle(host, client, timeout=IDLE_S), m)
    step("host unpublishedHostile false after T1", lambda: wait_unpublished_clear(host), m)
    hh, ch = hostile(host), hostile(client)
    bad = hash_fails(host, client, "after T1")
    if hh["census"] != ch["census"] or (hh["census"][0] or 0) < T1_FLOOR:
        bad.insert(0, f"hostile census host {hh['census']} client {ch['census']} (want equal, floor >= {T1_FLOOR})")
    time.sleep(LOG_FLUSH_S)
    ctx["P"], ctx["L0"] = {"census": hh["census"], "revealHostile": rh(host)}, log_count(host, L0_NEEDLE)
    if ctx["L0"] != 1:
        bad.append(f"host BASELINE hostile restate count L0 = {ctx['L0']} (want 1)")
    evidence("boot", {"P": ctx["P"], "L0": ctx["L0"], "clientCensus": ch["census"]})
    if bad:
        miss("T1 census, hash and L0", "; ".join(bad), m)

def stage_rejoin(host, client, ctx):
    """The spec (f) leave + rejoin steps 1-9, each bounded. Returns client2."""
    m = [host, client]
    bid0 = (battle_state(host).get("authority") or {}).get("battleId")
    step("1 drop_client_mid_battle", lambda: drop_client_mid_battle(host, client), m)
    evidence("pause", {"hostHostile": hostile(host)})            # allocated false = F3620
    client2 = ctx["client2"] = GameClient("rejoin", None, make_user_dir("w2h12_rearm_rejoin"))
    m.append(client2)
    step("3 client2 spawn and connect", lambda: (client2.spawn(), client2.connect()), m)
    step("4 rejoin_skirmish", lambda: rejoin_skirmish(client2, PORT_H12), m)

    def s5():
        client2.wait_for("client2 back in the battle", lambda: in_battle_save(client2) or None, timeout=240)
        client2.wait_for("client2 held on dialog 68 over BattlescapeState",
                         lambda: (has(client2, "BattlescapeState")
                                  and dialog(client2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None,
                         timeout=60, interval=0.5)

    def s6():
        def offered():
            if session.has_state(host, "Profile"):        # the join's popup sits over the dialog
                return host.cmd({"cmd": "profile_ok"}) and None
            return dialog(host).get("backVisible") or None
        host.wait_for("host dialog offers RESUME", offered, timeout=120, interval=0.5)
        d = dialog(host)
        assert d.get("code") == COOP_DLG_WAIT_PLAYERS and d.get("backText") == "RESUME", f"host dialog {d}"

    def s7():
        host.ok({"cmd": "coop_dialog_back"})
        for gc in (host, client2):
            gc.wait_for(f"{gc.name} top BattlescapeState", lambda gc=gc: (top(gc) == "BattlescapeState") or None,
                        timeout=120, interval=0.5)

    def s8():
        for gc in (host, client2):
            gc.wait_for(f"{gc.name} phase Active", lambda gc=gc: (battle_state(gc).get("phase") == "Active") or None,
                        timeout=120, interval=0.5)
        ha, ca = (battle_state(gc).get("authority") or {} for gc in (host, client2))
        assert ha.get("peerAbsent") is False, f"host peerAbsent: {ha}"
        assert ha.get("battleId") == ca.get("battleId") == bid0, (
            f"battleId before={bid0} host={ha.get('battleId')} client2={ca.get('battleId')}")
    step("5 client2 in the battle, held on dialog 68", s5, m)
    step("6 host offers RESUME", s6, m)
    step("7 RESUME, both tops BattlescapeState", s7, m)
    step("8 phase Active on both, peerAbsent false, battleId unchanged", s8, m)
    step("9 wait_host_idle(host, client2)", lambda: session.wait_host_idle(host, client2, timeout=IDLE_S), m)
    return client2

def h12_1(host, c2, ctx):
    time.sleep(LOG_FLUSH_S)
    hh, ch = hostile(host), hostile(c2)
    l0n, base = log_count(host, L0_NEEDLE), log_count(c2, BASE_RE)
    evidence("H12-1", {"host": hh, "client2": ch, "revealHostile": {"host": rh(host), "client2": rh(c2)},
                       "hostBaseline": {"L0": ctx["L0"], "now": l0n}, "client2BaseHostile": base,
                       "desyncSeen": [desync_seen(host), desync_seen(c2)],
                       "D219": {"P": ctx["P"], "hostAllocatedEmpty": log_count(host, EMPTY_NEEDLE)}})
    f = []
    if not hh["allocated"]:
        f.append(f"host hostile set not re-armed (allocated {hh['allocated']}, size {hh['size']})")
    elif hh["size"] != hh["mapSizeXYZ"]:
        f.append(f"host hostile size {hh['size']} != mapSizeXYZ {hh['mapSizeXYZ']}")
    if not ch["allocated"]:
        f.append("client2 hostile set not allocated")
    if hh["census"] != ch["census"] or (hh["census"][0] or 0) < 1:
        f.append(f"hostile census host {hh['census']} client2 {ch['census']} (want equal, host floor >= 1)")
    if hh["unpublishedHostile"] is not False:
        f.append(f"host unpublishedHostile {hh['unpublishedHostile']} (want false)")
    f += hash_fails(host, c2, "after RESUME")
    if l0n != ctx["L0"] + 1:
        f.append(f"host BASELINE hostile restate count {l0n} (want L0+1 = {ctx['L0'] + 1})")
    if base != 1:
        f.append(f"client2 applied hostile base restates {base} (want exactly 1)")
    return f + desync_fails(host, c2)

def h12_2(host, c2, ctx):
    c0, a0 = hostile(host)["census"], log_count(c2, ADD_RE)
    try:
        tele_both(host, c2, A_ID, T2, D2)                      # client2 first (F607)
    except Exception as e:
        ctx["staging"] = f"H12-2 tele_both T2: {short(e)}"
        return [f"staging: {ctx['staging']}"]
    notes = []
    for what, fn in (("wait_host_idle", lambda: session.wait_host_idle(host, c2, timeout=IDLE_S)),
                     ("host unpublishedHostile false", lambda: wait_unpublished_clear(host))):
        try:
            fn()
        except Exception as e:
            notes.append(f"{what} after T2: {short(e)}")
    time.sleep(LOG_FLUSH_S)
    hh, ch, a1 = hostile(host), hostile(c2), log_count(c2, ADD_RE)
    evidence("H12-2", {"C0": c0, "host": hh, "client2": ch, "client2AddHostile": [a0, a1], "G2": G2,
                       "notes": notes, "desyncSeen": [desync_seen(host), desync_seen(c2)]})
    f = []
    if not hh["allocated"] or (hh["census"][0] or 0) < (c0[0] or 0) + G2 or a1 - a0 < 1:
        f.append(f"tracking did not resume (host allocated {hh['allocated']}, host floor {c0[0]} -> {hh['census'][0]} "
                 f"(want >= +{G2}), client2 hostile add deltas +{a1 - a0} (want >= 1))")
    if hh["census"] != ch["census"]:
        f.append(f"hostile census host {hh['census']} client2 {ch['census']} (want equal)")
    f += hash_fails(host, c2, "after T2")
    return f + notes + desync_fails(host, c2)

def h12_3(host, c2, ctx):
    rhv = lambda: (event_state(c2).get("hashVerifyCounts") or {}).get("revealHostile", 0)  # noqa: E731
    v0, t0, notes = rhv(), [battle_state(gc).get("turn") for gc in (host, c2)], []
    end_turn_cycle(host, c2, notes)
    v1, t1 = rhv(), [battle_state(gc).get("turn") for gc in (host, c2)]
    evidence("H12-3", {"V0": v0, "V1": v1, "hashVerifyCounts": event_state(c2).get("hashVerifyCounts"),
                       "turn": {"before": t0, "after": t1}, "notes": notes,
                       "desyncSeen": [desync_seen(host), desync_seen(c2)]})
    f = []
    if v1 < v0 + 1:
        f.append(f"boundary hash carries no revealHostile (client2 hashVerifyCounts.revealHostile {v0} -> {v1}, "
                 f"want >= {v0 + 1})")
    if any(a is None or b != a + 1 for a, b in zip(t0, t1)):
        f.append(f"turn {t0} -> {t1} (want +1 on host and client2)")
    f += hash_fails(host, c2, "after the cycle")
    return f + notes + desync_fails(host, c2)

ROWS = (("H12-1", h12_1), ("H12-2", h12_2), ("H12-3", h12_3))

def main():
    t0, results, ctx, c2 = time.time(), {}, {}, None
    host = GameClient("host", None, make_user_dir("w2h12_rearm_host"))
    client = GameClient("client", None, make_user_dir("w2h12_rearm_client"))
    try:
        try:
            stage_boot(host, client, ctx)
            ctx["booted"] = True
            c2 = stage_rejoin(host, client, ctx)
        except FixtureMiss as e:
            for rid, _fn in ROWS:
                print(f"FAIL {rid}: {'rejoin' if ctx.get('booted') else 'boot'} (FIXTURE-STOP) {e}", flush=True)
        for rid, fn in (ROWS if c2 is not None else ()):
            if ctx.get("staging"):
                print(f"FAIL {rid}: staging ({ctx['staging']})", flush=True)
                continue
            try:
                f = fn(host, c2, ctx)
            except Exception as e:
                f = [f"{type(e).__name__}: {short(e, 600)}"]
            results[rid] = not f
            print(f"PASS {rid}" if not f else f"FAIL {rid}: " + "; ".join(f), flush=True)
    finally:
        for gc in [g for g in (host, client, ctx.get("client2")) if g is not None]:
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h12] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [r for r, _fn in ROWS if results.get(r)]
    failed = [r for r, _fn in ROWS if not results.get(r)]
    print(f"\ntest_w2_rejoin_reveal_rearm: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
