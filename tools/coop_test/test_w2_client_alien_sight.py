"""W2-H35 S-A - test_w2_client_alien_sight.py: on the co-op second player's machine an alien's `visible` flag follows
vanilla at an applied walk step of that alien and at an applied side change - hidden, then shown again exactly if one
of this machine's X-COM units sees it (DF-5; spec rewrite/prompts/w2h35_coop_client_alien_visibility.md (f); ruling
R-R5U1-1: the second player's off-turn view follows vanilla; D171).

Before W2-H35 the second player's machine sets an alien's flag only when its own X-COM unit acts and never clears it
(vanilla's step clear UnitWalkBState :244 / :250 and side-change clear SavedBattleGame::endTurn :1752 + BattlescapeGame
:746 run on the host only; capture df5-capture F12941, F12944-F12947, F12949).

ONE classic co-op boot (lobby key 48958, user dirs w2h35_host / w2h35_client), the capture's own chain (TASK 0 pins:
docs rewrite/w2h35-task0/sa/CONSTANTS.md, boots Ha and Hb equal): bring-up (test_w2_ai_origins' boot: SEED_ROSTER 1,
default NEW BATTLE, SEED_MAP 1, seat_count 2, pin_ai_neutral, reactions 0 on both); A base TU 54 on both; staging
cycles W (seed 1), D1 (seed 2), tele A to P0, D2 (seed 2), tele A to P0, tele V (soldier 9) to V_TILE facing 6, each
cycle followed by closing the client's player-side turn screen. A mismatch with the pins fails every row "staging".

Rows, in order (every row runs after a failure):
  A   alien_cycle(SEED_A): A walks into V's view during the alien turn; HOLD with the client's player-side turn
      screen left up. A-pre (A on P0, vis false on both, client hiddenMovementShown true in every side-0 sample, the
      walk is A_PATH, >= 3 path samples), A-walk (here(client) true in every path sample), A-after (end of HOLD: vis
      and here true on both), A-list (A in V's visibleUnits on the client exactly as on the host, host [A]), A-close
      (after the client closes its turn screen, soldier 8 selected: here(client) true).
  C1  client turn intent V -> V_TURN_A (control). C1-agree (vis and here equal on both and true), C1-list (V's
      visibleUnits [A] on both).
  B   alien_cycle(SEED_B): A walks out of V's view. B-pre (walk is B_PATH, no shot / hit / death / spot ev, V not out
      and facing V_TURN_A, >= 3 path samples), B-walk (here(client) false in every path sample), B-after (vis and here
      false on both), B-list (host [], client equal), B-close (V selected: here(client) false).
  C2  client turn intent V -> V_TURN_B. C2-agree (vis and here equal on both and false).
  D   tele A to D_TILE keeping its facing; V turn intent D_FACE; A base TU 0 on both; V turn intent D_AWAY; END TURN
      with the host held on its alien-side NextTurnState. D-pre (vis true on both), D-sticky (vis true on both after
      V turned away: vanilla keeps it), D-side (both on side 1, host held: host vis false, here(client) false), D-after
      (the cycle back to side 0, screens closed client first, wait_seq_barrier: vis and here false on both, no A ev).
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).
"here(gc)" = A's battle_state units[].visibleHere on that machine, "vis(gc)" = units[].visible (R5-U1 S-A's T1 probe).
A "path sample" = a client sample of the cycle (battle_state polled host then client every 0.25 s, one lock per
GameClient) whose A position is a tile of the walk (the client's event_state.lastWalk steps[].to; equal to the host's).

RED at the red commit (unchanged build): A-walk, A-after, A-list, A-close, B-walk, B-after, B-list, B-close, C2-agree,
D-side, D-after FAIL; every other cell PASS. GREEN (W2-H35 E1-E3): every cell PASS.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up failure
prints ONE "CAPTURE boot:" line and fails every row "boot". WV-D99 / WV-D100: one run is the result; no skip, no second
boot, no other fixture; exit 0 only when every cell passes, else 2. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_alien_sight.py
"""

import glob
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_w2_delta_core import both, tele_both, settle_on_battlescape

# The sampler thread and the driver share each GameClient socket: one lock per GameClient serialises every
# request / response pair (the df5-capture idiom; the harness itself is single-threaded).
_orig_cmd = harness.GameClient.cmd


def _locked_cmd(self, obj):
    lk = self.__dict__.get("_h35_lock")
    if lk is None:
        lk = self.__dict__.setdefault("_h35_lock", threading.RLock())
    with lk:
        return _orig_cmd(self, obj)


harness.GameClient.cmd = _locked_cmd

# ----- TASK 0 pins (CONSTANTS.md; boots Ha and Hb equal, S28) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral)
V_ID = 9                                        # the client seat's second soldier (the viewer)
A_TU = 54                                       # A base TU (set_stat, no refill: recovered at A's side start)
P0, P0_DIR = (27, 15, 0), 6                     # A after W (seed 1)
V_TILE, V_DIR = (28, 18, 0), 6                  # cone 6 holds every A_PATH tile, not P0; A never has V in its cone
SEED_W, SEED_A, SEED_B, SEED_D = 1, 2, 3, 1     # host set_seed right before its END TURN press
A_PATH = [(26, 16, 0), (25, 17, 0), (24, 18, 0), (23, 18, 0), (22, 18, 0), (21, 18, 0), (20, 18, 0)]
V_TURN_A = 7                                    # (20,18) inside cone 7; every B_PATH tile outside it
B_PATH = [(19, 19, 0), (19, 20, 0), (19, 21, 0), (18, 22, 0), (18, 23, 0), (17, 24, 0)]
V_TURN_B = 0                                    # (17,24) outside cone 0
D_TILE = (20, 18, 0)                            # A teleported here keeping its facing (5 after B)
D_FACE, D_AWAY = 6, 0                           # V's turn ends at 7: vanilla stops a turn on a new spot (F13340)
HOLD, PERIOD, MIN_PATH_SAMPLES = 3.0, 0.25, 3     # HOLD: the client's player-side screen left up after the cycle
KEY = "48958"                                   # this file's lobby key (F13155)
COMBAT_KINDS = ("shot", "hit", "death", "spot")
CHAIN_KINDS = ("turn", "walk_step", "kneel", "shot", "hit", "explosion", "melee", "psi", "death", "corpse", "spot")

ROWS = (("A", ("A-pre", "A-walk", "A-after", "A-list", "A-close", "A-common")),
        ("C1", ("C1-agree", "C1-list", "C1-common")),
        ("B", ("B-pre", "B-walk", "B-after", "B-list", "B-close", "B-common")),
        ("C2", ("C2-agree", "C2-common")),
        ("D", ("D-pre", "D-sticky", "D-side", "D-after", "D-common")))
RESULTS = {}
CRASH0 = set()
_BUF = {"ev": [], "lines": []}   # a row's EVIDENCE parts and cell lines, printed together by flush_row()


def short(e, n=400):
    return f"{type(e).__name__}: {str(e)[:n]}"


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


def vis(gc):
    """A df5_vis-shaped view of battle_state (T1 fields)."""
    bs = battle_state(gc)
    units = {}
    for u in bs.get("units") or []:
        units[u.get("id")] = {"pos": (u.get("x"), u.get("y"), u.get("z")), "dir": u.get("direction"),
                              "vis": u.get("visible"), "here": u.get("visibleHere"), "sees": u.get("visibleUnits"),
                              "out": u.get("isOut"), "tu": u.get("tu")}
    return {"units": units, "side": bs.get("side"), "turn": bs.get("turn"), "hms": bs.get("hiddenMovementShown"),
            "sel": bs.get("selectedId")}


def ua(v, uid=A_ID):
    return v["units"].get(uid) or {}


def states(gc):
    return gc.cmd({"cmd": "get_state"}).get("states") or []


def top(gc):
    return (states(gc) or [None])[-1]


def close_screens(gc):
    n, depth = 0, None
    while True:
        st = states(gc)
        if not st or "NextTurnState" not in st[-1] or (depth is not None and len(st) >= depth):
            return n
        depth = len(st)
        gc.cmd({"cmd": "close_nextturn"})
        n += 1


def evs(gc, seq0):
    return [(e.get("seq"), e.get("kind")) for e in (gc.cmd({"cmd": "event_log", "tail": 300}).get("events") or [])
            if (e.get("seq") or 0) > seq0]


def snap(host, client):
    return {"h": vis(host), "c": vis(client)}


def fmt(s):
    """A and V on both machines, compact."""
    h, c = s["h"], s["c"]
    ah, ac, vh, vc = ua(h), ua(c), ua(h, V_ID), ua(c, V_ID)
    return (f"side h/c {h['side']}/{c['side']} A h pos {ah.get('pos')} dir {ah.get('dir')} vis/here {ah.get('vis')}/"
            f"{ah.get('here')} tu {ah.get('tu')} | A c pos {ac.get('pos')} vis/here {ac.get('vis')}/{ac.get('here')} | "
            f"V h dir {vh.get('dir')} sees {vh.get('sees')} out {vh.get('out')} | V c dir {vc.get('dir')} sees "
            f"{vc.get('sees')} | sel h/c {h['sel']}/{c['sel']} hms c {c['hms']}")


class Sampler(threading.Thread):
    """vis() on the host, then the client, every PERIOD s."""

    def __init__(self, host, client):
        super().__init__(daemon=True)
        self.host, self.client, self.rows, self.t0, self.stop_ev = host, client, [], time.time(), threading.Event()

    def run(self):
        while not self.stop_ev.is_set():
            ts = time.time()
            try:
                self.rows.append({"t": round(ts - self.t0, 2), "h": vis(self.host), "c": vis(self.client)})
            except Exception as e:  # recorded, never retried
                self.rows.append({"t": round(ts - self.t0, 2), "error": short(e, 200)})
            dt = PERIOD - (time.time() - ts)
            if dt > 0:
                self.stop_ev.wait(dt)

    def stop(self):
        self.stop_ev.set()
        self.join(timeout=5)
        return [r for r in self.rows if "error" not in r], [r for r in self.rows if "error" in r]


def alien_cycle(host, client, seed, hold, d_side=False):
    """END TURN (client first; host set_seed right before its press); the client's alien-side turn screen closed
    first, then the host's (its AI waits while that screen is up); the host's player-side screen closed; the client's
    player-side screen LEFT UP for `hold` s after the seq barrier (closing it runs updateSoldierInfo). d_side: both
    machines read while the host is still held on its alien-side NextTurnState, after the client applied every ev."""
    rec = {"seq0": event_state(host).get("lastSeqEmitted") or 0, "marks": {}}
    turn0 = battle_state(host).get("turn")
    rec["pre"] = snap(host, client)
    smp = Sampler(host, client)
    smp.start()
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host END TURN 1/2", lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                      timeout=20)
        host.ok({"cmd": "set_seed", "seed": seed})
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("alien side on both, host held on its turn screen",
                      lambda: (battle_state(host).get("side") == 1 and "NextTurnState" in (top(host) or "")
                               and battle_state(client).get("side") == 1) or None, timeout=30)
        if d_side:
            def caught():
                c, h = event_state(client), event_state(host)
                return (c.get("lastSeqApplied") == h.get("lastSeqEmitted") and c.get("queueDepth") == 0) or None
            try:
                client.wait_for("client applied every host ev while the host is held", caught, timeout=10)
                rec["caught"] = True
            except TimeoutError as e:
                rec["caught"] = short(e, 200)
            rec["dSide"] = snap(host, client)
            rec["dSideTop"] = top(host)
        rec["marks"]["clientScreens"] = close_screens(client)
        rec["marks"]["hostScreens"] = close_screens(host)
        deadline = time.time() + 60
        while time.time() < deadline:
            hs = battle_state(host)
            if hs.get("side") == 0 and hs.get("turn", -1) >= turn0 + 1 and "NextTurnState" not in (top(host) or ""):
                break
            if "NextTurnState" in (top(host) or ""):
                close_screens(host)
            time.sleep(0.05)
        session.wait_seq_barrier(host, client, timeout=30)
        rec["marks"]["clientTop"] = top(client)
        time.sleep(hold)
    finally:
        rec["rows"], rec["errors"] = smp.stop()
    lw = event_state(client).get("lastWalk") or {}
    rec["path"] = [tuple((s.get("to") or {}).get(k) for k in ("x", "y", "z")) for s in (lw.get("steps") or [])
                   if (s.get("seq") or 0) > rec["seq0"]]
    rec["hev"] = evs(host, rec["seq0"])
    cam = event_state(client).get("camera") or {}
    rec["cam"] = [(m.get("seq"), m.get("reason"), m.get("visible"), m.get("onScreen")) for m in (cam.get("moves") or [])
                  if isinstance(m, dict) and (m.get("seq") or 0) > rec["seq0"]]
    rec["post"] = snap(host, client)
    tiles = set(rec["path"])
    rec["pathSamples"] = [r for r in rec["rows"] if ua(r["c"]).get("pos") in tiles]
    rec["hostByTile"] = {}
    for r in rec["rows"]:
        p = ua(r["h"]).get("pos")
        if p in tiles:
            rec["hostByTile"].setdefault(f"{p[0]},{p[1]}", []).append(ua(r["h"]).get("vis"))
    return rec


def close_client_screen(host, client):
    n = close_screens(client)
    settle_on_battlescape(client)
    settle_on_battlescape(host)
    session.wait_host_idle(host, client, timeout=30)
    time.sleep(0.5)  # BattlescapeState::init (updateSoldierInfo) runs on the frame after the pop
    return n, snap(host, client)


def client_turn(host, client, uid, to_dir):
    """The client's X-COM unit acts: a turn intent from the client (the real intent path). Waits for the host's
    `turn` ev, then the seq barrier; the final facing is what the host's turn reached (a turn that spots a new unit
    stops there, UnitTurnBState :129-:131)."""
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": uid, "toDir": to_dir})
    host.wait_for(f"host turn ev for unit {uid}", lambda: any(k == "turn" for _, k in evs(host, seq0)) or None,
                  timeout=20)
    session.wait_seq_barrier(host, client, timeout=30)
    return r, snap(host, client)


def vh_pair(s, keys=("vis", "here")):
    return tuple(ua(s["h"]).get(k) for k in keys), tuple(ua(s["c"]).get(k) for k in keys)


def common(host, client, row):
    try:
        assert_hash_clean(host, client, full=True, what=f"w2h35 {row}")
        h = "EQUAL"
    except AssertionError as e:
        h = str(e)[:600]
    ds = (event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen"))
    new = sorted(crash_files() - CRASH0)
    cell(f"{row}-common", h == "EQUAL" and ds == (False, False) and not new,
         f"hash_now full {h}; desyncSeen h/c {ds}; new crash files {new}")


# ===================== rows =====================


def row_a(host, client):
    rec = alien_cycle(host, client, SEED_A, HOLD)
    pre, post = rec["pre"], rec["post"]
    ps = rec["pathSamples"]
    hms = sorted({str(r["c"]["hms"]) for r in rec["rows"] if r["c"]["side"] == 0})  # R5-U2 S-E (QU2-A1-2): own side
    here_c = [ua(r["c"]).get("here") for r in ps]
    ev(f"A: pre {fmt(pre)} | walk {rec['path']} | host samples per path tile {rec['hostByTile']} | client path "
       f"samples {len(ps)} here {here_c} | hms c {hms} | evs {[k for _, k in rec['hev']]} | client camera.moves "
       f"{rec['cam']} | sampler errors {rec['errors']} | hold end {fmt(post)}")
    pa, pc = ua(pre["h"]), ua(pre["c"])
    cell("A-pre", pa.get("pos") == P0 and pc.get("pos") == P0 and pa.get("vis") is False and pc.get("vis") is False
         and hms == ["True"] and rec["path"] == A_PATH and len(ps) >= MIN_PATH_SAMPLES,
         f"A pos h/c {pa.get('pos')}/{pc.get('pos')} vis h/c {pa.get('vis')}/{pc.get('vis')}; hms {hms}; walk "
         f"{rec['path']} (want A_PATH); path samples {len(ps)} (>= {MIN_PATH_SAMPLES})")
    cell("A-walk", len(ps) >= MIN_PATH_SAMPLES and all(v is True for v in here_c),
         f"here(client) in {len(ps)} path samples: {here_c} (want all True)")
    hv, cv = vh_pair(post)
    cell("A-after", hv == (True, True) and cv == (True, True), f"HOLD end vis/here host {hv} client {cv} (want True)")
    sh, sc = ua(post["h"], V_ID).get("sees"), ua(post["c"], V_ID).get("sees")
    cell("A-list", sh == [A_ID] and sc == sh, f"V visibleUnits host {sh} client {sc} (want host [{A_ID}], client same)")
    n, s = close_client_screen(host, client)
    ev(f"A-close: closed {n}; {fmt(s)}")
    sel, here = s["c"]["sel"], ua(s["c"]).get("here")
    cell("A-close", sel == SEATED[0] and here is True,
         f"client selected {sel} (staging: want {SEATED[0]}), here(client) {here} (want True)")
    common(host, client, "A")


def row_c1(host, client):
    r, s = client_turn(host, client, V_ID, V_TURN_A)
    ev(f"C1: intent {r}; {fmt(s)}")
    hv, cv = vh_pair(s)
    cell("C1-agree", hv == cv == (True, True), f"vis/here host {hv} client {cv} (want equal and True)")
    sh, sc = ua(s["h"], V_ID).get("sees"), ua(s["c"], V_ID).get("sees")
    cell("C1-list", sh == sc == [A_ID], f"V visibleUnits host {sh} client {sc} (want [{A_ID}] on both)")
    common(host, client, "C1")


def row_b(host, client):
    rec = alien_cycle(host, client, SEED_B, HOLD)
    pre, post = rec["pre"], rec["post"]
    ps = rec["pathSamples"]
    here_c = [ua(r["c"]).get("here") for r in ps]
    combat = [(q, k) for q, k in rec["hev"] if k in COMBAT_KINDS]
    vh = ua(post["h"], V_ID)
    ev(f"B: pre {fmt(pre)} | walk {rec['path']} | host samples per path tile {rec['hostByTile']} | client path "
       f"samples {len(ps)} here {here_c} | evs {[k for _, k in rec['hev']]} | client camera.moves {rec['cam']} | "
       f"sampler errors {rec['errors']} | hold end {fmt(post)}")
    cell("B-pre", rec["path"] == B_PATH and not combat and vh.get("out") is False and vh.get("dir") == V_TURN_A
         and len(ps) >= MIN_PATH_SAMPLES,
         f"walk {rec['path']} (want B_PATH); combat evs {combat}; V out {vh.get('out')} dir {vh.get('dir')} (want "
         f"{V_TURN_A}); path samples {len(ps)} (>= {MIN_PATH_SAMPLES})")
    cell("B-walk", len(ps) >= MIN_PATH_SAMPLES and all(v is False for v in here_c),
         f"here(client) in {len(ps)} path samples: {here_c} (want all False)")
    hv, cv = vh_pair(post)
    cell("B-after", hv == (False, False) and cv == (False, False),
         f"end of HOLD vis/here host {hv} client {cv} (want False)")
    sh, sc = ua(post["h"], V_ID).get("sees"), ua(post["c"], V_ID).get("sees")
    cell("B-list", sh == [] and sc == sh, f"V visibleUnits host {sh} client {sc} (want host [], client equal)")
    n, s = close_client_screen(host, client)
    ev(f"B-close: closed {n}; {fmt(s)}")
    sel, here = s["c"]["sel"], ua(s["c"]).get("here")
    cell("B-close", sel == V_ID and here is False,
         f"client selected {sel} (staging: want {V_ID}), here(client) {here} (want False)")
    common(host, client, "B")


def row_c2(host, client):
    r, s = client_turn(host, client, V_ID, V_TURN_B)
    ev(f"C2: intent {r}; {fmt(s)}")
    hv, cv = vh_pair(s)
    cell("C2-agree", hv == cv == (False, False), f"vis/here host {hv} client {cv} (want equal and False)")
    common(host, client, "C2")


def row_d(host, client):
    a = ua(vis(host))
    tele_both(host, client, A_ID, D_TILE, a.get("dir"))
    r1, s1 = client_turn(host, client, V_ID, D_FACE)
    ev(f"D-pre: A teleported {a.get('pos')} -> {D_TILE} keeping dir {a.get('dir')}; intent {r1}; {fmt(s1)}")
    v1 = (ua(s1["h"]).get("vis"), ua(s1["c"]).get("vis"))
    cell("D-pre", v1 == (True, True), f"vis host/client {v1} (want True on both); V dir h/c "
         f"{ua(s1['h'], V_ID).get('dir')}/{ua(s1['c'], V_ID).get('dir')}")
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": 0}, ("tu",))
    r2, s2 = client_turn(host, client, V_ID, D_AWAY)
    ev(f"D-sticky: A base TU 0 on both; intent {r2}; {fmt(s2)}")
    v2 = (ua(s2["h"]).get("vis"), ua(s2["c"]).get("vis"))
    cell("D-sticky", v2 == (True, True), f"vis host/client {v2} after V turned to {ua(s2['h'], V_ID).get('dir')} "
         f"(want True on both: vanilla keeps the flag on a turn)")
    rec = alien_cycle(host, client, SEED_D, 0.5, d_side=True)
    ds = rec["dSide"]
    ev(f"D-side: caught {rec.get('caught')}; host top {rec.get('dSideTop')}; {fmt(ds)}")
    held = (ds["h"]["side"] == 1 and ds["c"]["side"] == 1 and "NextTurnState" in (rec.get("dSideTop") or "")
            and rec.get("caught") is True)
    hvis, chere = ua(ds["h"]).get("vis"), ua(ds["c"]).get("here")
    cell("D-side", held and hvis is False and chere is False,
         f"side 1 on both with the host held and the client caught up: {held}; host vis {hvis} (precondition False); "
         f"here(client) {chere} (want False)")
    settle_on_battlescape(client)
    settle_on_battlescape(host)
    session.wait_seq_barrier(host, client, timeout=30)
    s3 = snap(host, client)
    a_evs = [(q, k) for q, k in rec["hev"] if k in CHAIN_KINDS]
    moved = ua(s3["h"]).get("pos") != D_TILE or ua(s3["h"]).get("dir") != a.get("dir")
    ev(f"D-after: cycle evs {rec['hev']}; client camera.moves {rec['cam']}; {fmt(s3)}")
    hv, cv = vh_pair(s3)
    cell("D-after", s3["h"]["side"] == 0 and s3["c"]["side"] == 0 and hv == (False, False) and cv == (False, False)
         and not a_evs and not moved,
         f"side h/c {s3['h']['side']}/{s3['c']['side']}; vis/here host {hv} client {cv} (want False); A evs {a_evs}; "
         f"A moved {moved}")
    common(host, client, "D")


ROW_FNS = {"A": row_a, "C1": row_c1, "B": row_b, "C2": row_c2, "D": row_d}


# ===================== bring-up and staging =====================


def boot(host, client):
    """test_w2_ai_origins' boot with this file's key: SEED_ROSTER on the host before open_new_battle, SEED_MAP before
    newbattle_ok, seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on both (client first, F607)."""
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
    pinned = pin_ai_neutral(host, client, tag="w2h35")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="w2h35 bring-up")
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU},
         ("tu",))


def capture_boot(host, client, err):
    cap = {"error": short(err, 600)}
    for gc in (host, client):
        d = {}
        for k, fn in (("states", lambda: states(gc)),
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


def staging(host, client):
    """The capture's chain to case A: W (seed 1), D1 (seed 2), tele A to P0, D2 (seed 2), tele A to P0, tele V to
    V_TILE facing V_DIR; each cycle followed by closing the client's player-side turn screen. Raises on a pin miss."""
    alien_cycle(host, client, SEED_W, 0.5)
    close_client_screen(host, client)
    s = snap(host, client)
    got = [(ua(s[m]).get("pos"), ua(s[m]).get("dir")) for m in ("h", "c")]
    print(f"[w2h35] staging W: A h/c {got}", flush=True)
    assert got == [(P0, P0_DIR)] * 2, f"W: A at {got} (pin {(P0, P0_DIR)} on both)"
    for name in ("D1", "D2"):
        rec = alien_cycle(host, client, SEED_A, 0.5)
        close_client_screen(host, client)
        print(f"[w2h35] staging {name}: walk {rec['path']}", flush=True)
        assert rec["path"] == A_PATH, f"{name}: walk {rec['path']} (pin {A_PATH})"
        tele_both(host, client, A_ID, P0, P0_DIR)
    tele_both(host, client, V_ID, V_TILE, V_DIR)
    s = snap(host, client)
    print(f"[w2h35] staged: {fmt(s)}", flush=True)
    got = [(ua(s[m], V_ID).get("pos"), ua(s[m], V_ID).get("dir")) for m in ("h", "c")]
    assert got == [(V_TILE, V_DIR)] * 2, f"V at {got} (pin {(V_TILE, V_DIR)} on both)"


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49852, make_user_dir("w2h35_host"))
    client = GameClient("client", 49853, make_user_dir("w2h35_client"))
    blocked = None
    try:
        try:
            boot(host, client)
            CRASH0 = crash_files()
        except Exception as e:  # a bring-up failure fails every row
            capture_boot(host, client, e)
            blocked = "boot"
        if blocked is None:
            try:
                staging(host, client)
            except Exception as e:
                print(f"STAGING: {short(e, 600)}", flush=True)
                blocked = "staging"
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
                print(f"[w2h35] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_w2_client_alien_sight: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
