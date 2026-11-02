"""test_battle_start_casualty.py: a battle that starts with a non-player unit already dead or stunned (a crashed UFO's
power sources) must start on both machines: the second player never settles that casualty itself; the host settles it
and its events carry the result. A client that settled it in its own BattlescapeGame constructor would work on a copy
the host snapshotted before its own settle: it would desync and freeze in its equip screen.
Point A = both briefings up, the host has NOT pressed OK (the only point where a client-side settle would show); point
B = after the host's OK, the client has applied every event; point C = turn 1, after the equip screens.
  no_casualty  a negative seed (a guard row): no casualty; the whole spine; nothing diverges.
  killed  seed 2 (1000013 killed): at A no refusal, unit fields equal, nodes equal (node 113); at B the host's settle
      arrives (one cue, the client's unit equal, one silent ring record); at C turn 1, full hash, saves equal.
  stunned  seed 23 (unit 1000008 stunned): A as killed (node 70; the unit fields cell is a guard here); B / C as killed.
  killed_in_handshake  seed 2, the host's briefing OK in phase Handshake (hold_battle_ready): A as killed; the host
      emits no cue and no event while in Handshake; at B the settle arrives in the first post-Active event's delta (no
      ring record); C as killed.
FIX in a cell's text marks a check that fails without that rule. EVIDENCE line before each verdict; every row runs
after a failure; a WAIT that times out ends its row (later cells "not reached"); a failed row prints ONE CAPTURE line.
Exit 0 only when every row passes, else 2."""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import session  # noqa: E402
import repro_atom_walk as W  # noqa: E402
import test_corpse_node as CN  # noqa: E402

WAIT_S, POLL_S, EQ_S = 10.0, 0.1, 20.0
SEED_NEG = 1                                  # no unit of any faction dead or stunned at A
FINGERPRINT_NEG = 8.922486664436846e+18       # SEED_NEG's map fingerprint
HANDSHAKE_SEQ_AT_A = 0                               # the host's lastSeqEmitted at A in Handshake
UF = ("status", "health", "stun", "morale", "direction", "onTile", "isOut")
STATUS_DEAD, STATUS_UNCONSCIOUS, NO_SOUND = 6, 7, -1
CUE_RE = re.compile(r"\[coop-cue\] death seq \d+ actionId \d+: (\{.*\})")
HL_RE, CL_RE = r"\[coop-cue\] death|bt_desync|coop-equip|saveBlob", r"DESYNC|coop-tripwire"
CELLS = ("map_pinned", "start_casualties", "death_sounds_set", "hold_armed", "hold_released", "no_refusal_at_a",
         "units_equal_at_a", "nodes_equal_at_a", "host_silent_in_handshake", "settle_applied", "client_victim_settled",
         "death_ring", "turn_one_reached", "hash_equal", "saves_equal", "no_refusal_at_turn_one")
ES_KEYS = ("phase", "lastSeqEmitted", "lastSeqApplied", "queueDepth", "desyncSeen", "coopClientBStatePushes",
           "coopClientBStateLastSite")


class RowEnd(Exception):
    """A WAIT timed out: the row ends, its later cells are not reached."""


class Row:
    def __init__(self, name, lobby, labels, victim, cells):
        self.name, self.lobby, self.labels, self.victim = name, lobby, labels, victim
        self.cells = [c for c in CELLS if c in cells]
        self.done, self.fails, self.ended, self.host, self.client, self.hl0 = set(), [], None, None, None, 0

    def check(self, cell, ok, evidence, what):
        print(f"EVIDENCE {self.name} {cell} {json.dumps(evidence, sort_keys=True, default=str)}", flush=True)
        print(f"{self.name} {cell} {'PASS' if ok else 'FAIL'} - {what}", flush=True)
        self.done.add(cell)
        if not ok:
            self.fails.append(cell)

    def wait(self, label, pred, timeout=WAIT_S):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if pred():
                print(f"[{self.name}] wait {label}: met after {time.time() - t0:.2f}s", flush=True)
                return
            time.sleep(POLL_S)
        self.ended = f"wait {label} timed out after {timeout:.0f}s"
        raise RowEnd(self.ended)


es, bs, stack = session.event_state, session.battle_state, session.states_stripped


def unit(gc, uid):
    return next((u for u in bs(gc).get("units", []) if u.get("id") == uid), {})


def uf_diff(host, client):
    a, b = ({u["id"]: [u.get(k) for k in UF] for u in bs(gc).get("units", [])} for gc in (host, client))
    return {i: (a.get(i), b.get(i)) for i in sorted(set(a) | set(b)) if a.get(i) != b.get(i)}


def ring(client, uid=None):
    r = ((es(client).get("displayTwo") or {}).get("death") or {}).get("ring") or []
    return [x for x in r if uid is None or x.get("unit") == uid]


def log_lines(gc, pattern, start=0):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            f.seek(start)
            return [ln for ln in f.read().decode("utf-8", "replace").splitlines() if re.search(pattern, ln)]
    except OSError:
        return []


def cues(row, uid=None):
    ms = [(CUE_RE.search(ln), ln) for ln in log_lines(row.host, r"\[coop-cue\] death", row.hl0)]
    ps = [json.loads(m.group(1)) if m else {"unparsed": ln} for m, ln in ms]
    return [p for p in ps if uid is None or p.get("unit") == uid]


def applied(row):
    h, c = es(row.host), es(row.client)
    return c.get("lastSeqApplied") == h.get("lastSeqEmitted") and c.get("queueDepth") == 0


def saves(row, point):
    t = {m: CN.save_and_read(gc, f"battle_start_casualty_{row.name.lower()}_{point}_{m}.sav")
         for m, gc in (("host", row.host), ("client", row.client))}
    hn, cn = CN.node_types(t["host"]), CN.node_types(t["client"])
    hi, ci = CN.item_ids(t["host"]), CN.item_ids(t["client"])
    nd = {k: (hn.get(k), cn.get(k)) for k in sorted(set(hn) | set(cn)) if hn.get(k) != cn.get(k)}
    return nd, sorted(set(hi) ^ set(ci)), (len(hn), len(hi))


def drive(row, seed, pre=None):
    """drive_to_battlescape's own steps through newbattle_ok, then the host's briefing."""
    host, client = row.host, row.client
    W.bring_up_lobby(host, client, str(row.lobby))
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    r = host.cmd({"cmd": "newbattle_mission", "type": CN.MISSION})
    assert r.get("ok"), f"newbattle_mission {CN.MISSION}: {r}"
    for i in range(8):
        if not host.cmd({"cmd": "newbattle_seat_soldier", "seat": session.COOP_SEAT_1, "index": i}).get("ok"):
            break
    if pre is not None:
        pre(host, client)
    host.ok({"cmd": "set_seed", "seed": seed})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)


def point_a(row, phase):
    row.wait("A: client BriefingState over its BattlescapeState",
             lambda: stack(row.client)[-2:] == ["BattlescapeState", "BriefingState"], 90)
    row.wait(f"A: host top BriefingState, phase {phase}",
             lambda: stack(row.host)[-1:] == ["BriefingState"] and es(row.host).get("phase") == phase)


def setup(row, fp, stunned=None):
    got = bs(row.host).get("mapFingerprint")
    row.check("map_pinned", got == fp, {"mapFingerprint": got, "want": fp}, "mapFingerprint pinned")
    if stunned is None:
        return
    u = unit(row.host, row.victim)
    v = {k: u.get(k) for k in ("status", "health", "stun", "deathSounds")}
    ok = v["status"] == 0 and (v["stun"] >= v["health"] if stunned else v["health"] == 0)
    row.check("start_casualties", ok, v,
              f"host {row.victim} status 0, {'stun >= health' if stunned else 'health 0'} at A")
    if not stunned:
        row.check("death_sounds_set", bool(v["deathSounds"]), v,
                  f"host {row.victim} deathSounds non-empty (death_ring non-vacuity)")


def cells_a(row, fix):
    e = es(row.client)
    n, site = e.get("coopClientBStatePushes"), e.get("coopClientBStateLastSite")
    row.check("no_refusal_at_a", n == 0, {"refusals": n, "lastSite": site}, f"{' FIX' if fix else ''} REF 0 at A")
    d = uf_diff(row.host, row.client)
    row.check("units_equal_at_a", not d, {"ufDiff": d},
              f"{' FIX' if fix and row.name != 'stunned' else ''} UF equal at A")
    nd, _, cnt = saves(row, "A")
    row.check("nodes_equal_at_a", not nd, {"nodeDiff": nd, "nodes": cnt[0]},
              f"{' FIX' if fix else ''} NODES equal at A")


def check_settle_applied(row, cue_want, cue_cell=True):
    # cue_want None: no death cue (no_casualty); a dict: ONE cue of the victim with these fields (killed, stunned);
    # killed_in_handshake: death_ring owns cues
    h, c = es(row.host), es(row.client)
    ev = {"desyncSeen": (h.get("desyncSeen"), c.get("desyncSeen")),
          "btDesync": log_lines(row.host, "bt_desync", row.hl0), "cues": cues(row)}
    ok = h.get("desyncSeen") is False and c.get("desyncSeen") is False and not ev["btDesync"]
    mine = cues(row, row.victim)
    ok = ok and (not cue_cell or (not ev["cues"] if cue_want is None else
                                  len(mine) == 1 and all(mine[0].get(k) == v for k, v in cue_want.items())))
    row.check("settle_applied", ok, ev, "APPLIED, desyncSeen false on both, no bt_desync" + (
        "" if not cue_cell else ", no death cue" if cue_want is None else f", ONE death cue {cue_want}"))


def check_client_victim(row, status):
    cu = unit(row.client, row.victim)
    want = {"status": status, "onTile": False, "isOut": True, "direction": 3}
    got, d = {k: cu.get(k) for k in want}, uf_diff(row.host, row.client)
    row.check("client_victim_settled", got == want and not d, {"client": got, "ufDiff": d},
              f"client {row.victim} {want}; UF equal")


def spine_c(row):
    try:
        session.equip_both_ready(row.host, row.client, timeout=EQ_S)
    except TimeoutError as e:
        row.ended = f"wait equip_both_ready({EQ_S:.0f}s) timed out: {e}"
        raise RowEnd(row.ended)
    session.dismiss_battle_start_overlays(row.host)
    session.dismiss_battle_start_overlays(row.client)
    hs, cs = stack(row.host), stack(row.client)
    turns = (bs(row.host).get("turn"), bs(row.client).get("turn"))
    inv = [s for s in hs + cs if "InventoryState" in s]
    row.check("turn_one_reached", turns == (1, 1) and not inv, {"turn": turns, "stacks": (hs, cs)},
              "turn 1 on both, no InventoryState")
    try:
        session.assert_hash_clean(row.host, row.client, full=True, what=f"{row.name} hash_equal")
        row.check("hash_equal", True, {"hash_now": "full EQUAL"}, "assert_hash_clean(full=True)")
    except AssertionError as e:
        row.check("hash_equal", False, {"hash_now": str(e)[:600]}, "assert_hash_clean(full=True)")
    nd, idiff, cnt = saves(row, "C")
    row.check("saves_equal", not nd and not idiff, {"nodeDiff": nd, "itemDiff": idiff, "counts": cnt},
              "NODES and ITEMS equal")
    e = es(row.client)
    n, site, ds = e.get("coopClientBStatePushes"), e.get("coopClientBStateLastSite"), (
        es(row.host).get("desyncSeen"), e.get("desyncSeen"))
    row.check("no_refusal_at_turn_one", n == 0 and ds == (False, False),
              {"refusals": n, "lastSite": site, "desyncSeen": ds}, "REF 0, desyncSeen false")


def run_no_casualty(row):
    drive(row, SEED_NEG)
    point_a(row, "Active")
    setup(row, FINGERPRINT_NEG)
    cas = [{k: u.get(k) for k in ("id", "faction", "status", "health", "stun")} for u in bs(row.host).get("units", [])
           if u.get("health", 1) <= 0 or u.get("stun", 0) >= u.get("health", 1)]
    row.check("start_casualties", not cas, {"casualties": cas},
              "no unit of any faction with health <= 0 or stun >= health at A")
    cells_a(row, fix=False)
    row.host.ok({"cmd": "click_widget", "match": "ok"})
    session.dismiss_client_briefing(row.client)
    row.wait("B: APPLIED", lambda: applied(row))
    check_settle_applied(row, None)
    spine_c(row)


def run_casualty(row, seed, fp, stunned):
    drive(row, seed)
    point_a(row, "Active")
    setup(row, fp, stunned)
    cells_a(row, fix=True)
    row.host.ok({"cmd": "click_widget", "match": "ok"})
    session.dismiss_client_briefing(row.client)
    st = STATUS_UNCONSCIOUS if stunned else STATUS_DEAD
    row.wait(f"B: host {row.victim} status {st} and APPLIED",
             lambda: unit(row.host, row.victim).get("status") == st and applied(row))
    check_settle_applied(row, {"instant": True, "outcome": "unconscious"} if stunned else {"instant": True})
    check_client_victim(row, st)
    recs = ring(row.client, row.victim)
    want = {"instant": True, "outcome": "unconscious" if stunned else "dead", "sound": NO_SOUND,
            **({} if stunned else {"endedBy": "instant"})}
    ok = len(recs) == 1 and all(recs[0].get(k) == v for k, v in want.items())
    row.check("death_ring", ok,
              {"ring": [{k: r.get(k) for k in ("unit", "instant", "outcome", "endedBy", "sound")} for r in recs]},
              f"RING holds exactly one record of {row.victim}: {want}")
    spine_c(row)


def run_killed_in_handshake(row):
    arm = {}
    drive(row, CN.SEED_KILLED, pre=lambda h, c: arm.update(c.cmd({"cmd": "hold_battle_ready", "on": True})))
    point_a(row, "Handshake")
    row.wait("A: client battle_ready held", lambda: row.client.cmd({"cmd": "hold_battle_ready"}).get("held") is True)
    setup(row, CN.FINGERPRINT_KILLED, False)
    row.check("hold_armed", arm.get("armed") is True, {k: arm.get(k) for k in ("ok", "armed", "held")}, "hold armed")
    seq_a = es(row.host).get("lastSeqEmitted")
    cells_a(row, fix=True)
    row.host.ok({"cmd": "click_widget", "match": "ok"})
    row.wait(f"host {row.victim} status 6", lambda: unit(row.host, row.victim).get("status") == STATUS_DEAD)
    h = es(row.host)
    ev = {"phase": h.get("phase"), "seqAtA": seq_a, "seq": h.get("lastSeqEmitted"), "cues": cues(row)}
    row.check("host_silent_in_handshake",
              ev["phase"] == "Handshake" and not ev["cues"] and ev["seq"] == seq_a == HANDSHAKE_SEQ_AT_A, ev,
              f"host still Handshake, no death cue, lastSeqEmitted == its value at A == {HANDSHAKE_SEQ_AT_A}")
    rel = row.client.cmd({"cmd": "hold_battle_ready", "on": False})
    row.check("hold_released", rel.get("sent") is True, {k: rel.get(k) for k in ("ok", "armed", "held", "sent")},
              "release sent")
    row.wait("host phase Active", lambda: es(row.host).get("phase") == "Active")
    session.dismiss_client_briefing(row.client)
    row.wait("B: APPLIED", lambda: applied(row))
    check_settle_applied(row, None, cue_cell=False)
    check_client_victim(row, STATUS_DEAD)
    recs, cl = ring(row.client, row.victim), cues(row)
    row.check("death_ring", not recs and not cl, {"ring": recs, "cues": cl},
              f"RING holds NO record of {row.victim}, no death cue")
    spine_c(row)


def capture(row):
    cap = {"ended": row.ended}
    for m, gc in (("host", row.host), ("client", row.client)):
        try:
            cap[m] = {"stack": stack(gc), **{k: v for k, v in es(gc).items() if k in ES_KEYS}}
            if row.victim:
                cap[m]["victimUF"] = {k: unit(gc, row.victim).get(k) for k in UF}
            if gc is row.client:
                cap["ring"] = ring(gc)[-3:]
        except Exception as ex:  # noqa: BLE001 - a dead game still gets its capture line
            cap[m] = {"probeError": repr(ex)}
    cap["HL"], cap["clientLog"] = log_lines(row.host, HL_RE, row.hl0), log_lines(row.client, CL_RE)
    print(f"CAPTURE {row.name} {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def run_row(row, body):
    t0 = time.time()
    hd = make_user_dir(f"battle_start_casualty_{row.name.lower()}_host", options={"coopGhostStepper": True})
    cd = make_user_dir(f"battle_start_casualty_{row.name.lower()}_client", options={"coopGhostStepper": True})
    row.host, row.client = GameClient("host", row.labels[0], hd), GameClient("client", row.labels[1], cd)
    hlp = os.path.join(hd, "openxcom.log")
    row.hl0 = os.path.getsize(hlp) if os.path.exists(hlp) else 0  # HL = the host log from here
    try:
        body(row)
    except RowEnd:
        pass
    except Exception as e:  # noqa: BLE001 - a boot miss or a broken step ends the row with its capture
        row.ended = ("step: " if row.done else "boot: ") + f"{type(e).__name__}: {e}"
        row.fails += [] if row.done else ["boot"]
        print(f"[{row.name}] {row.ended}", flush=True)
    if row.ended or row.fails:
        capture(row)
    try:
        shutdown_clients(row.host, row.client)
    except Exception as e:  # noqa: BLE001
        print(f"[{row.name}] shutdown failed: {e}", flush=True)
        row.fails.append("shutdown")
    missed = [c for c in row.cells if c not in row.done]
    if missed:
        print(f"{row.name} not reached: {' '.join(missed)} ({row.ended})", flush=True)
    ok = not row.fails and not missed
    print(f"{row.name}: {'PASS' if ok else 'FAIL'} - failed {row.fails} wall={time.time() - t0:.1f}s", flush=True)
    return ok


def main():
    t0 = time.time()
    base = ("map_pinned", "start_casualties", "no_refusal_at_a", "units_equal_at_a", "nodes_equal_at_a",
            "settle_applied", "turn_one_reached", "hash_equal", "saves_equal", "no_refusal_at_turn_one")
    rows = [
        (Row("no_casualty", 47914, (49570, 49571), None, base), run_no_casualty),
        (Row("killed", 47915, (49572, 49573), 1000013,
             base + ("death_sounds_set", "client_victim_settled", "death_ring")),
         lambda r: run_casualty(r, CN.SEED_KILLED, CN.FINGERPRINT_KILLED, False)),
        (Row("stunned", 47916, (49574, 49575), 1000008, base + ("client_victim_settled", "death_ring")),
         lambda r: run_casualty(r, CN.SEED_STUNNED, CN.FINGERPRINT_STUNNED, True)),
        (Row("killed_in_handshake", 47917, (49576, 49577), 1000013,
             base + ("death_sounds_set", "hold_armed", "hold_released", "host_silent_in_handshake",
                     "client_victim_settled", "death_ring")), run_killed_in_handshake),
    ]
    verdicts = [(row.name, run_row(row, body)) for row, body in rows]
    ok = all(v for _, v in verdicts)
    print("test_battle_start_casualty: " + ("PASS" if ok else "FAIL") + " ("
          + ", ".join(f"{n} {'PASS' if v else 'FAIL'}" for n, v in verdicts) + f") wall={time.time() - t0:.1f}s", flush=True)
    return ok


if __name__ == "__main__":
    try:
        PASSED = main()
    except Exception as e:  # noqa: BLE001 - exit 0 only when every row passes
        print(f"test_battle_start_casualty: FAIL - {type(e).__name__}: {e}", flush=True)
        PASSED = False
    sys.exit(0 if PASSED else 2)
