"""W2-H11 - a co-op soldier's removal at death leaves one log line, and a
set_soldier_owner miss says who is where (spec rewrite/prompts/
w2h11_soldier_removal_logging.md (f); owner ruling D218; F3567, F3574).
ONE boot (test_w2_death_side's default map, lobby PORT_H11), rows in order:
 H11-1  the HOST kills DS1_ID (kill_unit_real, the K1 death branch): its log
        holds exactly ONE `[coop-roster] killSoldier:` line naming soldier,
        owner, the base it left (index, name, coop flag), resetArmor 0, battle
        turn and side; get_soldiers no longer lists it. Cause fields and the
        client's count are printed only (F3570, F3566).
 H11-2  the HOST calls set_soldier_owner for the dead DS1_ID (i), GHOST_ID (ii,
        no base soldier, no battle unit) and the control DS2_ID with its own
        owner (iii). Each miss answers ok false, the same error and a `diag`
        listing every base's soldiers (= R0, in order), the dead (DS1_ID) and
        the player units (DS1_ID DEAD), logged once each; (iii) ok, no diag.
A boot step or precondition miss is a FIXTURE-STOP (one CAPTURE line: both
machines' get_soldiers + battle_state; both rows FAIL "boot"). Each row prints
ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <msg>"; every row
runs; an H11-1 staging failure fails H11-2 "staging". The diag text is never
printed (H11-L2). WV-D95/D99/D100: ONE foreground run, no skip path; exit 0
only when both rows pass, 2 otherwise.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, pin_ai_neutral, assert_hash_clean
import test_w2_host_combat as hc
from test_w2_death_side import (kill_real, DS1_ID, DS2_ID, A_ID, SEED_MAP_D, MAP_FP_D, FACTION_PLAYER,
                                FACTION_HOSTILE, COOP_SEAT_0, COOP_SEAT_1, STATUS_DEAD)
from test_w2_delta_core import short

PORT_H11 = "48495"            # this file's lobby key (unused by every other test file)
GHOST_ID = 987654             # H11-2 (ii): no base soldier and no battle unit has this id (asserted)
OWNER_MISS = 999              # H11-2 (i)/(ii): the owner the two misses would write
LOG_FLUSH_S, IDLE_S = 3, 30   # house log flush; wait_host_idle
NOT_FOUND = "soldier id not found"
KILL_NEEDLE = "[coop-roster] killSoldier:"
SSO_NEEDLE = "[coop-test] set_soldier_owner:"
KILL_RE = re.compile(r"\[coop-roster\] killSoldier: soldier (\d+) '(.*)' owner (-?\d+) removed from base (\d+) '(.*)' "
                     r"\(coopBase ([01])\); resetArmor ([01]); cause kill: killer '(.*)' faction (-?\d+) weapon (\S+) "
                     r"ammo (\S+); battle turn (-?\d+) side (-?\d+)$")
BASE_RE = re.compile(r"\[(\d+) '(.*?)' coopBase=([01]):([^\]]*)\]")
SOLDIER_RE = re.compile(r"(\d+)/o(-?\d+)/c([01])")
DEAD_TOKEN = f"unit{DS1_ID}/soldier{DS1_ID}/st{STATUS_DEAD}/"   # H11-2: the dead unit in the diag's `units:` list

def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)

def log_lines(gc, literal):
    """Rstripped lines of this machine's openxcom.log holding `literal` ([] when unreadable)."""
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return [ln.rstrip() for ln in f if literal in ln]
    except OSError:
        return []

def log_count(gc, literal):
    return len(log_lines(gc, literal))

def roster(gc):
    """get_soldiers as [(base name, coopBase 0/1, [(id, owner, craft 0/1), ...]), ...] in base order."""
    r = gc.cmd({"cmd": "get_soldiers"})
    assert r.get("ok"), f"get_soldiers on {gc.name}: {r}"
    return [(b.get("name"), int(bool(b.get("coopBaseFlag"))),
             [(s.get("id"), s.get("owner"), int(s.get("craftId", -1) != -1)) for s in b.get("soldiers", [])])
            for b in r.get("bases", [])]

def bases_with(rost, sid):
    return [i for i, (_n, _c, ss) in enumerate(rost) if any(s[0] == sid for s in ss)]

def capture(name, err, machines):
    """FIXTURE-STOP evidence: both machines' get_soldiers and battle_state, whole."""
    def probe(gc, k):
        try:
            return gc.cmd({"cmd": k})
        except Exception as e:
            return f"probe failed: {short(e)}"
    cap = {gc.name: {k: probe(gc, k) for k in ("get_soldiers", "battle_state")} for gc in machines}
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)

def boot(host, client, ctx):
    """Copy of test_w2_death_side.boot_default on lobby PORT_H11, then the (f) preconditions."""
    hc.bring_up_lobby_roster_pinned(host, client, PORT_H11)
    session.drive_to_battlescape(host, client, {}, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP_D}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP_D and cs.get("mapFingerprint") == MAP_FP_D, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {MAP_FP_D!r})")
    assert pin_ai_neutral(host, client, tag="w2h11"), "pin_ai_neutral pinned no NONE-seat non-player unit"
    ub = session.units_by_id(hs)
    for uid, seat in ((DS1_ID, COOP_SEAT_0), (DS2_ID, COOP_SEAT_1)):
        u = ub.get(uid) or {}
        assert (u.get("faction") == FACTION_PLAYER and u.get("coop") == seat and not u.get("isOut")
                and u.get("onTile")), f"unit {uid} at bring-up: {u} (want a live player soldier of seat {seat})"
    a = ub.get(A_ID) or {}
    assert a.get("faction") == FACTION_HOSTILE and not a.get("isOut"), f"alien {A_ID} at bring-up: {a}"
    session.wait_host_idle(host, client, timeout=IDLE_S)
    assert_hash_clean(host, client, full=True, what="bring-up")
    r = ctx["R_boot"] = roster(host)
    b = bases_with(r, DS1_ID)
    bs, kc = battle_state(host), [log_count(gc, KILL_NEEDLE) for gc in (host, client)]
    ctx["T0"] = bs.get("turn")
    evidence("boot", {"bases": [(n, c, len(ss)) for n, c, ss in r], "basesWith10": b, "turn": ctx["T0"],
                      "side": bs.get("side"), "killLines": kc})
    assert len(b) == 1, f"host get_soldiers lists soldier {DS1_ID} on bases {b} (want exactly one)"
    ctx["b10"], ctx["o10"] = b[0], next(s[1] for s in r[b[0]][2] if s[0] == DS1_ID)
    assert (ctx["T0"] or 0) >= 1 and bs.get("side") == FACTION_PLAYER, (
        f"host battle turn {ctx['T0']} side {bs.get('side')} (want turn >= 1, side {FACTION_PLAYER})")
    assert kc == [0, 0], f"`{KILL_NEEDLE}` lines host/client {kc} at boot (want 0 on both)"

def h11_1(host, client, ctx):
    notes = []
    k = kill_real(host, client, DS1_ID, notes)
    time.sleep(LOG_FLUSH_S)
    u = session.units_by_id(battle_state(host)).get(DS1_ID) or {}
    after = bases_with(roster(host), DS1_ID)
    lines, cn = log_lines(host, KILL_NEEDLE), log_count(client, KILL_NEEDLE)
    g = m.groups() if (len(lines) == 1 and (m := KILL_RE.search(lines[0]))) else None
    evidence("H11-1", {"kill": k, "hostUnit": {x: u.get(x) for x in ("status", "isOut", "onTile", "health")},
                       "hostBasesWith10": after, "hostLines": lines, "clientLines": cn,
                       "cause": {"killer": g[7], "faction": g[8], "weapon": g[9], "ammo": g[10]} if g else None,
                       "b10": ctx["b10"], "o10": ctx["o10"], "T0": ctx["T0"], "notes": notes})
    stage = list(notes)
    if not k.get("ok") or k.get("killed") != [DS1_ID]:
        stage.append(f"kill_unit_real answered {k} (want ok, killed [{DS1_ID}])")
    if u.get("status") != STATUS_DEAD:
        stage.append(f"host unit {DS1_ID} status {u.get('status')} (want DEAD {STATUS_DEAD})")
    if stage:
        ctx["staging"] = "; ".join(stage)
        capture("H11-1 staging", ctx["staging"], (host, client))
        return [f"staging: {ctx['staging']}"]
    f = []
    if after:
        f.append(f"host get_soldiers still lists soldier {DS1_ID} on bases {after} (want none)")
    if not lines:
        f.append(f"no removal line (host `{KILL_NEEDLE}` lines 0, want exactly 1)")
    elif len(lines) != 1:
        f.append(f"host `{KILL_NEEDLE}` lines {len(lines)} (want exactly 1)")
    elif not g:
        f.append(f"host removal line does not parse: {lines[0]!r}")
    else:
        name, flag = ctx["R_boot"][ctx["b10"]][:2]
        want = {"soldier": DS1_ID, "owner": ctx["o10"], "base": ctx["b10"], "baseName": name, "coopBase": flag,
                "resetArmor": 0, "turn": ctx["T0"], "side": FACTION_PLAYER}
        got = {"soldier": int(g[0]), "owner": int(g[2]), "base": int(g[3]), "baseName": g[4], "coopBase": int(g[5]),
               "resetArmor": int(g[6]), "turn": int(g[11]), "side": int(g[12])}
        bad = {x: (got[x], want[x]) for x in want if got[x] != want[x]}
        f += [f"removal line fields (got, want) {bad}"] if bad else []
    return f

def diag_fails(tag, sid, a, r0):
    """One miss's answer against the (f) GREEN: ok false, the same error, a diag matching R0."""
    if a.get("ok") is not False or a.get("error") != NOT_FOUND:
        return [f"{tag} answered ok={a.get('ok')} error={a.get('error')!r} (want ok false, error {NOT_FOUND!r})"]
    d = a.get("diag")
    if not isinstance(d, str):
        return [f"no diag: {tag} answer keys {sorted(a)} (want a `diag`)"]
    f = []
    if not d.startswith(f"want={sid} bases:"):
        f.append(f"{tag} diag does not start 'want={sid} bases:'")
    got = [(int(i), n, int(c), [tuple(int(x) for x in t) for t in SOLDIER_RE.findall(body)])
           for i, n, c, body in BASE_RE.findall(d)]
    want = [(i, n, c, ss) for i, (n, c, ss) in enumerate(r0)]
    if got != want:
        first = next(i for i, (x, y) in enumerate(zip(got + [None], want + [None])) if x != y)
        f.append(f"{tag} diag bases differ from R0: {len(got)} groups for {len(want)} bases, first at {first}")
    if any(s[0] == DS1_ID for grp in got for s in grp[3]):
        f.append(f"{tag} diag lists soldier {DS1_ID} on a base")
    dead = d.split(" dead:", 1)[1].split(" units:", 1)[0].split() if " dead:" in d else None
    if dead is None or str(DS1_ID) not in dead:
        f.append(f"{tag} diag dead list {'missing' if dead is None else 'lacks ' + str(DS1_ID)}")
    units = d.split(" units:", 1)[1] if " units:" in d else None
    if units is None or f" {DEAD_TOKEN}" not in units:
        f.append(f"{tag} diag units {'missing' if units is None else 'lack ' + DEAD_TOKEN}")
    return f

def h11_2(host, client, ctx):
    r0 = roster(host)
    unit_ids = set(session.units_by_id(battle_state(host)))
    b8 = bases_with(r0, DS2_ID)
    pre = [f"id {GHOST_ID} is on host bases {bases_with(r0, GHOST_ID)} or is a battle unit"] if (
        bases_with(r0, GHOST_ID) or GHOST_ID in unit_ids) else []
    pre += [] if len(b8) == 1 else [f"host get_soldiers lists soldier {DS2_ID} on bases {b8} (want exactly one)"]
    if pre:
        capture("H11-2 staging", "; ".join(pre), (host, client))
        return [f"staging: {'; '.join(pre)}"]
    o8 = next(s[1] for s in r0[b8[0]][2] if s[0] == DS2_ID)
    a1 = host.cmd({"cmd": "set_soldier_owner", "soldier_id": DS1_ID, "owner": OWNER_MISS})
    a2 = host.cmd({"cmd": "set_soldier_owner", "soldier_id": GHOST_ID, "owner": OWNER_MISS})
    a3 = host.cmd({"cmd": "set_soldier_owner", "soldier_id": DS2_ID, "owner": o8})
    time.sleep(LOG_FLUSH_S)
    hl, cl = log_lines(host, SSO_NEEDLE), log_count(client, SSO_NEEDLE)
    match = [ln.endswith(f"{SSO_NEEDLE} soldier {sid} not found - {a.get('diag')}".rstrip())
             for ln, (sid, a) in zip(hl, ((DS1_ID, a1), (GHOST_ID, a2)))]

    def view(a):
        d = a.get("diag") if isinstance(a.get("diag"), str) else ""
        return {"ok": a.get("ok"), "error": a.get("error"), "hasDiag": "diag" in a, "diagLen": len(d),
                "groups": len(BASE_RE.findall(d))}
    r0v = {"bases": [(n, c, len(ss)) for n, c, ss in r0], "basesWith10": bases_with(r0, DS1_ID), "s8": (b8[0], o8)}
    evidence("H11-2", {"R0": r0v, "answers": {"i": view(a1), "ii": view(a2), "iii": view(a3)},
                       "hostLines": len(hl), "hostLinesMatch": match, "clientLines": cl})
    if any(a.get("ok") is not False for a in (a1, a2)):
        capture("H11-2 miss answered ok", f"(i) ok={a1.get('ok')} (ii) ok={a2.get('ok')}", (host, client))
    f = diag_fails(f"(i) soldier {DS1_ID}", DS1_ID, a1, r0)
    f += diag_fails(f"(ii) soldier {GHOST_ID}", GHOST_ID, a2, r0)
    if a3.get("ok") is not True or "diag" in a3:
        f.append(f"(iii) control {DS2_ID} answered ok={a3.get('ok')} hasDiag={'diag' in a3} (want ok true, no diag)")
    if len(hl) != 2 or not all(match) or "diag" not in a1 or "diag" not in a2:
        f.append(f"host `{SSO_NEEDLE}` lines {len(hl)} matching {match} (want exactly 2: 'soldier {DS1_ID} not found - "
                 f"<diag (i)>', then 'soldier {GHOST_ID} not found - <diag (ii)>')")
    if cl:
        f.append(f"client `{SSO_NEEDLE}` lines {cl} (want 0)")
    return f

ROWS = (("H11-1", h11_1), ("H11-2", h11_2))

def main():
    t0, results, ctx = time.time(), {}, {}
    host = GameClient("host", None, make_user_dir("w2h11_removal_log_host"))
    client = GameClient("client", None, make_user_dir("w2h11_removal_log_client"))
    try:
        try:
            boot(host, client, ctx)
            ctx["booted"] = True
        except Exception as e:
            capture("boot", short(e, 800), (host, client))
            for rid, _fn in ROWS:
                print(f"FAIL {rid}: boot (FIXTURE-STOP) {short(e, 400)}", flush=True)
        for rid, fn in (ROWS if ctx.get("booted") else ()):
            if ctx.get("staging"):
                print(f"FAIL {rid}: staging ({ctx['staging']})", flush=True)
                continue
            try:
                f = fn(host, client, ctx)
            except Exception as e:
                f = [short(e, 600)]
            results[rid] = not f
            print(f"PASS {rid}" if not f else f"FAIL {rid}: " + "; ".join(f), flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h11] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [r for r, _fn in ROWS if results.get(r)]
    failed = [r for r, _fn in ROWS if not results.get(r)]
    print(f"\ntest_w2_soldier_removal_log: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
