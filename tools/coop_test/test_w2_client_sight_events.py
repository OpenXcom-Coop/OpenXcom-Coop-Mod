"""W2-H35b S-A - test_w2_client_sight_events.py: on the co-op second player's machine an alien's `visible` flag and
each X-COM soldier's list of seen units follow vanilla when another soldier opens a door (K1) and when an AI unit
thinks during its own turn (K4) (spec rewrite/prompts/w2h35b_client_sight_events.md (f); rulings R-R5U1-1: the second
player's off-turn view follows vanilla; D171: hidden aliens stay hidden; W2-H35 QH-3 (a): capture first).

Vanilla refreshes sight through the doorway right after a door opens (TileEngine::unitOpensDoor :4240-:4242) and hides
the acting AI unit, then refreshes sight around it, before each AI action (BattlescapeGame::handleAI :373-:375). The
second player's machine runs neither: its door apply refreshes only the door actor (A5), and it has no think.

TASK 0 verdicts (docs rewrite/w2h35b-task0/sa/CONSTANTS.md, capture boots Ha and Hb equal, S28): K1 CONFIRMED (host
A visible and in V's list after the door; client A not drawn, V's list empty); K4 CONFIRMED (seed 1: A's first action
is an auto shot at W without walking; host hides A at its think; client keeps A drawn through the alien side). The
door is a normal BARN door, not a UFO door (TASK 0 F14001): its west-wall part leaves the door census and a north-wall
part appears when it opens.

ONE classic co-op day boot (lobby key 46640, user dirs w2h35b_a_host / w2h35b_a_client): CAS's boot (copied):
SEED_ROSTER 1 before open_new_battle, SEED_MAP 1 before newbattle_ok, seat_count 2, pin_ai_neutral (A = the only
alien), reactions 0 for every X-COM unit on both, A base TU 54; A on A_BOOT facing 5 checked on both.

Rows, in order (every row runs after a failure):
  K1  another soldier opens the door; V can see A through it. tele O (8) to O_TILE facing O_DIR0, V (9) to V_DOOR
      facing V_DOOR_DIR; client turn intent O -> O_OPEN_DIR (a real rotation opens nothing), then the same intent
      again (the zero-tick re-issue opens the door it faces, RDD phase_turn_opens_door).
      K1-pre  (after the rotation) the door closed on both, no `door` ev, vis false on both, A in neither machine's
              list(V) nor list(O), O facing O_OPEN_DIR on both.
      K1-open (after the door chain: seq barrier, wait_host_idle) the door open on both (census equal), host vis true
              and A in host list(V) (precondition: vanilla revealed A).
      K1-here here(client) true.                       K1-list list(client, V) equal to list(host, V).
  K4  the AI alien loses its last viewer during its own turn and acts without walking. tele A to K4_A_TILE facing 5,
      A base TU 54, W (10) to W_TILE facing W_DIR (A behind W, W in A's cone), V to V_TILE facing 6, client turn
      intent V -> 7; END TURN (client first, host set_seed SEED_K4 right before its press); host held on its
      alien-side NextTurnState, client caught up; tele V to V_AWAY facing 2 (A behind V); screens closed client
      first, then the host's (the AI runs); sampled until side 0 on both and the seq barrier.
      K4-pre   while held: side 1 on both; vis true on both; W in host list(A).
      K4-host  a host side-1 sample with vis false while A is on K4_A_TILE (precondition: vanilla's think hid A).
      K4-think here(client) false in every qualifying sample (taken after the client applied the first ev of A's
               first action, the client's A on K4_A_TILE, client side 1), >= 3 qualifying samples.
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).
"here(gc)" / "vis(gc)" = A's battle_state units[].visibleHere / visible on that machine; "list(gc, U)" = U's
units[].visibleUnits (R5-U1 S-A's T1 probe). The sampler polls battle_state (host, then client) and the client's
event_state every 0.25 s under CAS's per-GameClient lock.

RED at the red commit (unchanged build): K1-here, K1-list, K4-think FAIL; every other cell PASS. GREEN (W2-H35b E1,
E2, E3, E4): every cell PASS.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up
failure prints ONE "CAPTURE boot:" line and fails every row "boot"; a staging miss fails that row's cells "staging".
WV-D99 / WV-D100: one run is the result; no skip, no second boot, no other fixture; exit 0 only when every cell
passes, else 2. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_sight_events.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_w2_delta_core import both, tele_both, settle_on_battlescape
# vis, ua, snap, close_screens, top, states, client_turn, Sampler and the per-GameClient lock (installed on import)
import test_w2_client_alien_sight as cas

# ----- TASK 0 pins (CONSTANTS.md; boots Ha and Hb equal, S28) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral)
A_BOOT, A_BOOT_DIR = (27, 12, 0), 5             # A at boot, inside the barn
O_ID, V_ID, W_ID = 8, 9, 10                     # O opens the door, V watches, W is A's target in K4
DOOR = (29, 13, 0, 1)                           # the barn door A's W walk opens (normal door, west wall; F14001)
DOOR_OPEN = (29, 13, 0, 2)                      # the census entry the opened door leaves on that tile (north wall)
O_TILE, O_DIR0, O_OPEN_DIR = (28, 13, 0), 4, 2  # A never in O's cone through the rotation 4 -> 3 -> 2
V_DOOR, V_DOOR_DIR = (32, 14, 0), 6             # TASK 0 oracle: V sees A through the open door (O in place)
K4_A_TILE, K4_A_DIR, A_TU = (20, 18, 0), 5, 54  # A base TU 54 (set_stat, no refill: recovered at A's side start)
W_TILE, W_DIR = (19, 20, 0), 5                  # inside A's cone 5; A behind W
V_TILE, V_DIR, V_TURN = (28, 18, 0), 6, 7       # the turn to 7 shows A on both (W2-H35 D-pre)
V_AWAY, V_AWAY_DIR = (29, 18, 0), 2             # A behind V: nobody sees A once the host's think runs
SEED_K4 = 1                                     # host set_seed right before its END TURN press (TASK 0 hunt)
MIN_Q = 3                                       # qualifying samples (STOP-IF 12)
KEY = "46640"                                   # this file's lobby key (spec (G))

ROWS = (("K1", ("K1-pre", "K1-open", "K1-here", "K1-list", "K1-common")),
        ("K4", ("K4-pre", "K4-host", "K4-think", "K4-common")))
RESULTS = {}
CRASH0 = set()
_BUF = {"ev": [], "lines": []}
ua, short = cas.ua, cas.short


def ev(text):
    _BUF["ev"].append(text)


def cell(name, ok, detail):
    RESULTS[name] = bool(ok)
    _BUF["lines"].append(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def flush_row(row, cells):
    print(f"EVIDENCE {row}: {' || '.join(_BUF['ev'])}", flush=True)
    for line in _BUF["lines"]:
        print(line, flush=True)
    print(f"ROW {row}: {'PASS' if all(RESULTS.get(c) for c in cells) else 'FAIL'}", flush=True)
    _BUF["ev"], _BUF["lines"] = [], []


def crash_files():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def common(host, client, row):
    try:
        assert_hash_clean(host, client, full=True, what=f"w2h35b {row}")
        h = "EQUAL"
    except AssertionError as e:
        h = str(e)[:600]
    ds = (event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen"))
    new = sorted(crash_files() - CRASH0)
    cell(f"{row}-common", h == "EQUAL" and ds == (False, False) and not new,
         f"hash_now full {h}; desyncSeen h/c {ds}; new crash files {new}")


def staging_miss(cells, detail):
    """A staging step off its pin: the row's cells FAIL "staging" (its common cell is still measured)."""
    ev(f"staging miss: {detail}")
    for c in cells:
        if c not in RESULTS and not c.endswith("-common"):
            cell(c, False, f"staging: {detail}")


def evs_a(gc, seq0):
    return [(e.get("seq"), e.get("kind"), e.get("actionId"))
            for e in (gc.cmd({"cmd": "event_log", "tail": 400}).get("events") or []) if (e.get("seq") or 0) > seq0]


def door_state(gc):
    keys = {(d["x"], d["y"], d["z"], d["part"]) for d in session.find_doors(gc)}
    if DOOR in keys and DOOR_OPEN not in keys:
        return "closed"
    return "open" if DOOR_OPEN in keys and DOOR not in keys else f"other {sorted(keys)}"


def at(s, uid, pos, d):
    return all(ua(s[m], uid).get("pos") == pos and ua(s[m], uid).get("dir") == d for m in ("h", "c"))


def lists(s, uid):
    return ua(s["h"], uid).get("sees"), ua(s["c"], uid).get("sees")


def first_cue(host, seq):
    """The host's `[coop-cue] <kind> seq <seq> ...` line (actor / unit evidence, P-4)."""
    try:
        with open(os.path.join(host.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if f"seq {seq} actionId" in line and "[coop-cue]" in line:
                    return line.split("[coop-cue]", 1)[1].strip()[:300]
    except OSError as e:
        return short(e, 120)
    return None


class Sampler(cas.Sampler):
    """CAS's sampler plus the client's event_state.lastSeqApplied in each sample."""

    def run(self):
        while not self.stop_ev.is_set():
            ts = time.time()
            try:
                self.rows.append({"t": round(ts - self.t0, 2), "h": cas.vis(self.host), "c": cas.vis(self.client),
                                  "cSeq": event_state(self.client).get("lastSeqApplied")})
            except Exception as e:  # recorded, never retried
                self.rows.append({"t": round(ts - self.t0, 2), "error": short(e, 200)})
            dt = cas.PERIOD - (time.time() - ts)
            if dt > 0:
                self.stop_ev.wait(dt)


# ===================== rows =====================


def row_k1(host, client):
    cells = dict(ROWS)["K1"]
    tele_both(host, client, O_ID, O_TILE, O_DIR0)
    tele_both(host, client, V_ID, V_DOOR, V_DOOR_DIR)
    s0 = cas.snap(host, client)
    if not (at(s0, O_ID, O_TILE, O_DIR0) and at(s0, V_ID, V_DOOR, V_DOOR_DIR) and at(s0, A_ID, A_BOOT, A_BOOT_DIR)):
        staging_miss(cells, cas.fmt(s0))
        return common(host, client, "K1")
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    de0 = event_state(host).get("coopDoorEvsEmitted")
    r1, s1 = cas.client_turn(host, client, O_ID, O_OPEN_DIR)
    de1 = event_state(host).get("coopDoorEvsEmitted")
    d1 = (door_state(host), door_state(client))
    rot = evs_a(host, seq0)
    seq1 = event_state(host).get("lastSeqEmitted") or 0
    r2 = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": O_ID, "toDir": O_OPEN_DIR})
    host.wait_for("host door ev", lambda: (event_state(host).get("coopDoorEvsEmitted") or 0) > (de1 or 0) or None,
                  timeout=20)
    session.wait_seq_barrier(host, client, timeout=30)
    session.wait_host_idle(host, client, timeout=30)
    s2 = cas.snap(host, client)
    d2 = (door_state(host), door_state(client))
    census_eq = session.door_census(host) == session.door_census(client)
    hev, cev = evs_a(host, seq1), evs_a(client, seq1)
    ev(f"K1: rotation intent {r1} evs {rot}; door intent {r2} host evs {hev} client evs {cev} | door h/c {d1} -> "
       f"{d2} (census equal {census_eq}) | O dir h/c {ua(s2['h'], O_ID).get('dir')}/{ua(s2['c'], O_ID).get('dir')} V "
       f"dir h/c {ua(s2['h'], V_ID).get('dir')}/{ua(s2['c'], V_ID).get('dir')} | client selected {s2['c']['sel']} | "
       f"list(O) h/c {lists(s2, O_ID)} | after {cas.fmt(s2)}")
    v1, lv1, lo1 = (ua(s1["h"]).get("vis"), ua(s1["c"]).get("vis")), lists(s1, V_ID), lists(s1, O_ID)
    no_a = all(A_ID not in (x or []) for x in lv1 + lo1)
    o_dirs = (ua(s1["h"], O_ID).get("dir"), ua(s1["c"], O_ID).get("dir"))
    cell("K1-pre", d1 == ("closed", "closed") and de1 == de0 and not any(k == "door" for _, k, _a in rot)
         and v1 == (False, False) and no_a and o_dirs == (O_OPEN_DIR, O_OPEN_DIR),
         f"door h/c {d1}; coopDoorEvsEmitted {de0} -> {de1}; evs {rot}; vis h/c {v1}; list(V) h/c {lv1}; list(O) h/c "
         f"{lo1}; O dir h/c {o_dirs} (want closed, no door ev, False, no A, {O_OPEN_DIR})")
    hv, lv2 = ua(s2["h"]).get("vis"), lists(s2, V_ID)
    cell("K1-open", d2 == ("open", "open") and census_eq and any(k == "door" for _, k, _a in hev) and hv is True
         and A_ID in (lv2[0] or []),
         f"door h/c {d2} census equal {census_eq}; host vis {hv}; host list(V) {lv2[0]} (precondition: open, True, "
         f"holds {A_ID})")
    here = ua(s2["c"]).get("here")
    cell("K1-here", here is True, f"here(client) {here} (want True)")
    cell("K1-list", lv2[1] == lv2[0], f"list(V) host {lv2[0]} client {lv2[1]} (want equal)")
    common(host, client, "K1")


def k4_cycle(host, client):
    rec = {"seq0": event_state(host).get("lastSeqEmitted") or 0}
    turn0 = battle_state(host).get("turn")
    smp = Sampler(host, client)
    smp.start()
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host END TURN 1/2", lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                      timeout=20)
        host.ok({"cmd": "set_seed", "seed": SEED_K4})
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("alien side on both, host held on its turn screen",
                      lambda: (battle_state(host).get("side") == 1 and "NextTurnState" in (cas.top(host) or "")
                               and battle_state(client).get("side") == 1) or None, timeout=30)

        def caught():
            c, h = event_state(client), event_state(host)
            return (c.get("lastSeqApplied") == h.get("lastSeqEmitted") and c.get("queueDepth") == 0) or None
        try:
            client.wait_for("client applied every host ev while the host is held", caught, timeout=10)
            rec["caught"] = True
        except TimeoutError as e:
            rec["caught"] = short(e, 200)
        rec["held"], rec["heldTop"] = cas.snap(host, client), cas.top(host)
        tele_both(host, client, V_ID, V_AWAY, V_AWAY_DIR)
        rec["screens"] = (cas.close_screens(client), cas.close_screens(host))
        deadline = time.time() + 60
        while time.time() < deadline:
            hs = battle_state(host)
            if hs.get("side") == 0 and hs.get("turn", -1) >= turn0 + 1 and "NextTurnState" not in (cas.top(host) or ""):
                break
            if "NextTurnState" in (cas.top(host) or ""):
                cas.close_screens(host)
            time.sleep(0.05)
        session.wait_seq_barrier(host, client, timeout=30)
    finally:
        rec["rows"], rec["errors"] = smp.stop()
    rec["hev"] = evs_a(host, rec["seq0"])
    settle_on_battlescape(client)
    settle_on_battlescape(host)
    session.wait_host_idle(host, client, timeout=30)
    rec["post"] = cas.snap(host, client)
    w = session.units_by_id(battle_state(host)).get(W_ID) or {}
    rec["w"] = (w.get("health"), w.get("isOut"))
    return rec


def row_k4(host, client):
    cells = dict(ROWS)["K4"]
    tele_both(host, client, A_ID, K4_A_TILE, K4_A_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU},
         ("tu",))
    tele_both(host, client, W_ID, W_TILE, W_DIR)
    tele_both(host, client, V_ID, V_TILE, V_DIR)
    r, s = cas.client_turn(host, client, V_ID, V_TURN)
    if not (at(s, A_ID, K4_A_TILE, K4_A_DIR) and at(s, W_ID, W_TILE, W_DIR) and at(s, V_ID, V_TILE, V_TURN)):
        staging_miss(cells, f"intent {r}; {cas.fmt(s)}")
        return common(host, client, "K4")
    rec = k4_cycle(host, client)
    held, rows = rec["held"], rec["rows"]
    sb = [q for q, k, _a in rec["hev"] if k == "side_begin"]
    first = next(((q, k, a) for q, k, a in rec["hev"] if sb and q > sb[0] and a), None)
    a_evs = [(q, k, a) for q, k, a in rec["hev"] if a]
    host_false = [r["t"] for r in rows if r["h"]["side"] == 1 and ua(r["h"]).get("vis") is False
                  and ua(r["h"]).get("pos") == K4_A_TILE]
    qual = [r for r in rows if first and (r.get("cSeq") or 0) >= first[0] and r["c"]["side"] == 1
            and ua(r["c"]).get("pos") == K4_A_TILE]
    here_q = [ua(r["c"]).get("here") for r in qual]
    ev(f"K4: staged {cas.fmt(s)} | held (caught {rec['caught']}, host top {rec['heldTop']}) {cas.fmt(held)} | first "
       f"ev of A's first action {first} cue {first_cue(host, first[0]) if first else None} | A evs {a_evs} | W "
       f"health/out {rec['w']} | samples {len(rows)}, host side-1 false-on-tile {len(host_false)}, qualifying "
       f"{len(qual)} here(client) {here_q} | sampler errors {rec['errors']} | after {cas.fmt(rec['post'])}")
    hv = (ua(held["h"]).get("vis"), ua(held["c"]).get("vis"))
    a_list = ua(held["h"]).get("sees") or []
    sides = (held["h"]["side"], held["c"]["side"])
    cell("K4-pre", sides == (1, 1) and rec["caught"] is True and "NextTurnState" in (rec["heldTop"] or "")
         and hv == (True, True) and W_ID in a_list,
         f"side h/c {sides}; caught {rec['caught']}; host top {rec['heldTop']}; vis h/c {hv}; host list(A) {a_list} "
         f"(want 1/1, True, NextTurnState, True/True, holds {W_ID})")
    cell("K4-host", len(host_false) >= 1,
         f"host side-1 samples with vis False while A on {K4_A_TILE}: {len(host_false)} at t {host_false[:6]} "
         f"(precondition >= 1: vanilla's think hid A)")
    cell("K4-think", len(qual) >= MIN_Q and all(v is False for v in here_q),
         f"here(client) in {len(qual)} qualifying samples (after seq {first[0] if first else None}, client A on "
         f"{K4_A_TILE}, client side 1): {here_q} (want >= {MIN_Q}, all False)")
    common(host, client, "K4")


ROW_FNS = {"K1": row_k1, "K4": row_k4}


# ===================== bring-up =====================


def boot(host, client):
    """CAS's boot with this file's key (copied): SEED_ROSTER on the host before open_new_battle, SEED_MAP before
    newbattle_ok, seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on both (client first, F607),
    A base TU 54; A on A_BOOT facing A_BOOT_DIR on both."""
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
    raw.skirmish_host(host, KEY)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (baked {MAP_FP!r})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    pinned = pin_ai_neutral(host, client, tag="w2h35b")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="w2h35b bring-up")
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU},
         ("tu",))
    s = cas.snap(host, client)
    assert at(s, A_ID, A_BOOT, A_BOOT_DIR), f"A at boot: {cas.fmt(s)} (baked {A_BOOT} facing {A_BOOT_DIR})"


def capture_boot(host, client, err):
    cap = {"error": short(err, 600)}
    for gc in (host, client):
        d = {}
        for k, fn in (("states", lambda: cas.states(gc)),
                      ("battle", lambda: {k2: battle_state(gc).get(k2) for k2 in ("side", "turn")}),
                      ("phase", lambda: event_state(gc).get("phase")),
                      ("dialog", lambda: gc.cmd({"cmd": "coop_dialog_info"}))):
            try:
                d[k] = fn()
            except Exception as e:
                d[k] = short(e, 120)
        try:
            with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
                d["log"] = [ln.rstrip() for ln in f.readlines()[-40:]]
        except OSError as e:
            d["log"] = short(e, 120)
        cap[gc.name] = d
    print(f"CAPTURE boot: {json.dumps(cap, default=str)}", flush=True)


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49852, make_user_dir("w2h35b_a_host"))
    client = GameClient("client", 49853, make_user_dir("w2h35b_a_client"))
    blocked = None
    try:
        try:
            boot(host, client)
            CRASH0 = crash_files()
        except Exception as e:  # a bring-up failure fails every row
            capture_boot(host, client, e)
            blocked = "boot"
        for row, cells in ROWS:
            if blocked:
                ev(f"not run ({blocked})")
                for c in cells:
                    cell(c, False, blocked)
            else:
                try:
                    ROW_FNS[row](host, client)
                except Exception as e:  # every row runs after a failure
                    ev(f"row raised {short(e)}")
                    for c in cells:
                        if c not in RESULTS:
                            cell(c, False, f"row {row} raised {short(e)}")
            flush_row(row, cells)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h35b] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_w2_client_sight_events: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
