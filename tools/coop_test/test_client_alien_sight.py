"""test_client_alien_sight.py: on the co-op second player's machine an alien's `visible` flag follows
vanilla at an applied walk step of that alien and at an applied side change - hidden, then shown again exactly if one
of this machine's X-COM units sees it (the second player's off-turn view follows vanilla).

Vanilla clears the flag at each walk step (UnitWalkBState :244 / :250) and at the side change (SavedBattleGame::endTurn
:1752 + BattlescapeGame :746). Those clears run on the host; without the same clears on the second player's machine,
that machine sets an alien's flag only when its own X-COM unit acts and never clears it.

ONE classic co-op boot (lobby key 48958, user dirs client_alien_sight_host / client_alien_sight_client), the fixture
values equal in two boots: bring-up (test_ai_origins' boot: SEED_ROSTER 1, default NEW BATTLE, SEED_MAP 1, seat_count
2, pin_ai_neutral, reactions 0 on both); A base TU 54 on both; staging cycles walk_to_start (seed 1), first_path_walk
(seed 2), tele A to A_START, second_path_walk (seed 2), tele A to A_START, tele V (soldier 9) to V_TILE facing 6, each
cycle followed by closing the client's player-side turn screen. A mismatch with the fixture values fails every row
"staging".

Rows, in order (every row runs after a failure); a cell's name is <row>-<cell>:
  alien_walks_into_view    alien_cycle(SEED_WALK_IN): A walks into V's view during the alien turn; HOLD with the
      client's player-side turn screen left up. pre (A on A_START, vis false on both, client hiddenMovementShown true
      in every side-0 sample, the walk is IN_PATH, >= 3 path samples), walk (here(client) true in every path sample),
      after (end of HOLD: vis and here true on both), list (A in V's visibleUnits on the client exactly as on the
      host, host [A]), close (after the client closes its turn screen, soldier 8 selected: here(client) true).
  client_turn_sees_alien   client turn intent V -> V_TURN_SEE (control). agree (vis and here equal on both and true),
      list (V's visibleUnits [A] on both).
  alien_walks_out_of_view  alien_cycle(SEED_WALK_OUT): A walks out of V's view. pre (walk is OUT_PATH, no shot / hit /
      death / spot ev, V not out and facing V_TURN_SEE, >= 3 path samples), walk (here(client) false in every path
      sample), after (vis and here false on both), list (host [], client equal), close (soldier 8 selected:
      here(client) false; the client keeps soldier 8 at each X-COM side start).
  client_turn_loses_alien  client turn intent V -> V_TURN_LOSE. agree (vis and here equal on both and false).
  side_change_clears_flag  tele A to STICKY_TILE keeping its facing; V turn intent STICKY_FACE; A base TU 0 on both;
      V turn intent STICKY_AWAY; END TURN with the host held on its alien-side NextTurnState. pre (vis true on both),
      sticky (vis true on both after V turned away: vanilla keeps it), side (both on side 1, host held: host vis
      false, here(client) false), after (the cycle back to side 0, screens closed client first, wait_seq_barrier:
      vis and here false on both, no A ev).
  Every row: <row>-common (hash_now full: every bucket EQUAL; event_state.desyncSeen false on both; 0 new crash files).
"here(gc)" = A's battle_state units[].visibleHere on that machine, "vis(gc)" = units[].visible.
A "path sample" = a client sample of the cycle (battle_state polled host then client every 0.25 s, one lock per
GameClient) whose A position is a tile of the walk (the client's event_state.lastWalk steps[].to; equal to the host's).

A build without the second player's clears fails alien_walks_into_view walk / after / list / close,
alien_walks_out_of_view walk / after / list / close, client_turn_loses_alien-agree and side_change_clears_flag side /
after; every other cell passes. With them, every cell passes.

Each row prints one "EVIDENCE <row>:" line, one PASS / FAIL line per cell and "ROW <row>: PASS|FAIL". A bring-up failure
prints ONE "CAPTURE boot:" line and fails every row "boot". one run is the result; no skip, no second
boot, no other fixture; exit 0 only when every cell passes, else 2. run in the foreground to completion.

Run:  python tools/coop_test/test_client_alien_sight.py
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
from test_delta_core import both, tele_both, settle_on_battlescape

# The sampler thread and the driver share each GameClient socket: one lock per GameClient serialises every
# request / response pair (the harness itself is single-threaded).
_orig_cmd = harness.GameClient.cmd


def _locked_cmd(self, obj):
    lk = self.__dict__.get("_sampler_lock")
    if lk is None:
        lk = self.__dict__.setdefault("_sampler_lock", threading.RLock())
    with lk:
        return _orig_cmd(self, obj)


harness.GameClient.cmd = _locked_cmd

# ----- fixture values (equal in two boots) -----
SEED_ROSTER, SEED_MAP = 1, 1
MAP_FP = -4.48310638993e+18
SEATED = [8, 9]
A_ID, A_TYPE = 1000000, "STR_SECTOID_SOLDIER"   # the only alien (pin_ai_neutral)
V_ID = 9                                        # the client seat's second soldier (the viewer)
A_TU = 54                                       # A base TU (set_stat, no refill: recovered at A's side start)
A_START, A_START_DIR = (27, 15, 0), 6           # A after walk_to_start (seed 1)
# cone 6 holds every IN_PATH tile, not A_START; A never has V in its cone
V_TILE, V_DIR = (28, 18, 0), 6
# host set_seed right before its END TURN press
SEED_TO_START, SEED_WALK_IN, SEED_WALK_OUT, SEED_SIDE_CHANGE = 1, 2, 3, 1
IN_PATH = [(26, 16, 0), (25, 17, 0), (24, 18, 0), (23, 18, 0), (22, 18, 0), (21, 18, 0), (20, 18, 0)]
V_TURN_SEE = 7                                  # (20,18) inside cone 7; every OUT_PATH tile outside it
OUT_PATH = [(19, 19, 0), (19, 20, 0), (19, 21, 0), (18, 22, 0), (18, 23, 0), (17, 24, 0)]
V_TURN_LOSE = 0                                 # (17,24) outside cone 0
STICKY_TILE = (20, 18, 0)                       # A teleported here keeping its facing (5 after alien_walks_out_of_view)
STICKY_FACE, STICKY_AWAY = 6, 0                 # V's turn ends at 7: vanilla stops a turn on a new spot
HOLD, PERIOD, MIN_PATH_SAMPLES = 3.0, 0.25, 3     # HOLD: the client's player-side screen left up after the cycle
KEY = "48958"                                   # this file's lobby key
COMBAT_KINDS = ("shot", "hit", "death", "spot")
CHAIN_KINDS = ("turn", "walk_step", "kneel", "shot", "hit", "explosion", "melee", "psi", "death", "corpse", "spot")

ROWS = (("alien_walks_into_view", ("alien_walks_into_view-pre", "alien_walks_into_view-walk",
                                   "alien_walks_into_view-after", "alien_walks_into_view-list",
                                   "alien_walks_into_view-close", "alien_walks_into_view-common")),
        ("client_turn_sees_alien", ("client_turn_sees_alien-agree", "client_turn_sees_alien-list",
                                    "client_turn_sees_alien-common")),
        ("alien_walks_out_of_view", ("alien_walks_out_of_view-pre", "alien_walks_out_of_view-walk",
                                     "alien_walks_out_of_view-after", "alien_walks_out_of_view-list",
                                     "alien_walks_out_of_view-close", "alien_walks_out_of_view-common")),
        ("client_turn_loses_alien", ("client_turn_loses_alien-agree", "client_turn_loses_alien-common")),
        ("side_change_clears_flag", ("side_change_clears_flag-pre", "side_change_clears_flag-sticky",
                                     "side_change_clears_flag-side", "side_change_clears_flag-after",
                                     "side_change_clears_flag-common")))
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
    """A compact view of battle_state: each unit's position, facing and visibility fields, the side and selection."""
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


def alien_cycle(host, client, seed, hold, held_read=False):
    """END TURN (client first; host set_seed right before its press); the client's alien-side turn screen closed
    first, then the host's (its AI waits while that screen is up); the host's player-side screen closed; the client's
    player-side screen LEFT UP for `hold` s after the seq barrier (closing it runs updateSoldierInfo). held_read: both
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
        if held_read:
            def caught():
                c, h = event_state(client), event_state(host)
                return (c.get("lastSeqApplied") == h.get("lastSeqEmitted") and c.get("queueDepth") == 0) or None
            try:
                client.wait_for("client applied every host ev while the host is held", caught, timeout=10)
                rec["caught"] = True
            except TimeoutError as e:
                rec["caught"] = short(e, 200)
            rec["heldRead"] = snap(host, client)
            rec["heldReadTop"] = top(host)
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
        assert_hash_clean(host, client, full=True, what=f"client_alien_sight {row}")
        h = "EQUAL"
    except AssertionError as e:
        h = str(e)[:600]
    ds = (event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen"))
    new = sorted(crash_files() - CRASH0)
    cell(f"{row}-common", h == "EQUAL" and ds == (False, False) and not new,
         f"hash_now full {h}; desyncSeen h/c {ds}; new crash files {new}")


# ===================== rows =====================


def row_walks_into_view(host, client):
    rec = alien_cycle(host, client, SEED_WALK_IN, HOLD)
    pre, post = rec["pre"], rec["post"]
    ps = rec["pathSamples"]
    hms = sorted({str(r["c"]["hms"]) for r in rec["rows"] if r["c"]["side"] == 0})  # the client's own side
    here_c = [ua(r["c"]).get("here") for r in ps]
    ev(f"alien_walks_into_view: pre {fmt(pre)} | walk {rec['path']} | host samples per path tile "
       f"{rec['hostByTile']} | client path samples {len(ps)} here {here_c} | hms c {hms} | evs "
       f"{[k for _, k in rec['hev']]} | client camera.moves {rec['cam']} | sampler errors {rec['errors']} | hold end "
       f"{fmt(post)}")
    pa, pc = ua(pre["h"]), ua(pre["c"])
    cell("alien_walks_into_view-pre", pa.get("pos") == A_START and pc.get("pos") == A_START
         and pa.get("vis") is False and pc.get("vis") is False
         and hms == ["True"] and rec["path"] == IN_PATH and len(ps) >= MIN_PATH_SAMPLES,
         f"A pos h/c {pa.get('pos')}/{pc.get('pos')} vis h/c {pa.get('vis')}/{pc.get('vis')}; hms {hms}; walk "
         f"{rec['path']} (want IN_PATH); path samples {len(ps)} (>= {MIN_PATH_SAMPLES})")
    cell("alien_walks_into_view-walk", len(ps) >= MIN_PATH_SAMPLES and all(v is True for v in here_c),
         f"here(client) in {len(ps)} path samples: {here_c} (want all True)")
    hv, cv = vh_pair(post)
    cell("alien_walks_into_view-after", hv == (True, True) and cv == (True, True),
         f"HOLD end vis/here host {hv} client {cv} (want True)")
    sh, sc = ua(post["h"], V_ID).get("sees"), ua(post["c"], V_ID).get("sees")
    cell("alien_walks_into_view-list", sh == [A_ID] and sc == sh,
         f"V visibleUnits host {sh} client {sc} (want host [{A_ID}], client same)")
    n, s = close_client_screen(host, client)
    ev(f"alien_walks_into_view-close: closed {n}; {fmt(s)}")
    sel, here = s["c"]["sel"], ua(s["c"]).get("here")
    cell("alien_walks_into_view-close", sel == SEATED[0] and here is True,
         f"client selected {sel} (staging: want {SEATED[0]}), here(client) {here} (want True)")
    common(host, client, "alien_walks_into_view")


def row_turn_sees_alien(host, client):
    r, s = client_turn(host, client, V_ID, V_TURN_SEE)
    ev(f"client_turn_sees_alien: intent {r}; {fmt(s)}")
    hv, cv = vh_pair(s)
    cell("client_turn_sees_alien-agree", hv == cv == (True, True),
         f"vis/here host {hv} client {cv} (want equal and True)")
    sh, sc = ua(s["h"], V_ID).get("sees"), ua(s["c"], V_ID).get("sees")
    cell("client_turn_sees_alien-list", sh == sc == [A_ID],
         f"V visibleUnits host {sh} client {sc} (want [{A_ID}] on both)")
    common(host, client, "client_turn_sees_alien")


def row_walks_out_of_view(host, client):
    rec = alien_cycle(host, client, SEED_WALK_OUT, HOLD)
    pre, post = rec["pre"], rec["post"]
    ps = rec["pathSamples"]
    here_c = [ua(r["c"]).get("here") for r in ps]
    combat = [(q, k) for q, k in rec["hev"] if k in COMBAT_KINDS]
    vh = ua(post["h"], V_ID)
    ev(f"alien_walks_out_of_view: pre {fmt(pre)} | walk {rec['path']} | host samples per path tile "
       f"{rec['hostByTile']} | client path samples {len(ps)} here {here_c} | evs {[k for _, k in rec['hev']]} | client "
       f"camera.moves {rec['cam']} | sampler errors {rec['errors']} | hold end {fmt(post)}")
    cell("alien_walks_out_of_view-pre", rec["path"] == OUT_PATH and not combat and vh.get("out") is False
         and vh.get("dir") == V_TURN_SEE and len(ps) >= MIN_PATH_SAMPLES,
         f"walk {rec['path']} (want OUT_PATH); combat evs {combat}; V out {vh.get('out')} dir {vh.get('dir')} (want "
         f"{V_TURN_SEE}); path samples {len(ps)} (>= {MIN_PATH_SAMPLES})")
    cell("alien_walks_out_of_view-walk", len(ps) >= MIN_PATH_SAMPLES and all(v is False for v in here_c),
         f"here(client) in {len(ps)} path samples: {here_c} (want all False)")
    hv, cv = vh_pair(post)
    cell("alien_walks_out_of_view-after", hv == (False, False) and cv == (False, False),
         f"end of HOLD vis/here host {hv} client {cv} (want False)")
    sh, sc = ua(post["h"], V_ID).get("sees"), ua(post["c"], V_ID).get("sees")
    cell("alien_walks_out_of_view-list", sh == [] and sc == sh,
         f"V visibleUnits host {sh} client {sc} (want host [], client equal)")
    n, s = close_client_screen(host, client)
    ev(f"alien_walks_out_of_view-close: closed {n}; {fmt(s)}")
    sel, here = s["c"]["sel"], ua(s["c"]).get("here")
    # the client keeps soldier 8 at each X-COM side start, not V.
    cell("alien_walks_out_of_view-close", sel == SEATED[0] and here is False,
         f"client selected {sel} (staging: want {SEATED[0]}, the kept soldier), here(client) {here} (want False)")
    common(host, client, "alien_walks_out_of_view")


def row_turn_loses_alien(host, client):
    r, s = client_turn(host, client, V_ID, V_TURN_LOSE)
    ev(f"client_turn_loses_alien: intent {r}; {fmt(s)}")
    hv, cv = vh_pair(s)
    cell("client_turn_loses_alien-agree", hv == cv == (False, False),
         f"vis/here host {hv} client {cv} (want equal and False)")
    common(host, client, "client_turn_loses_alien")


def row_side_change_clears(host, client):
    a = ua(vis(host))
    tele_both(host, client, A_ID, STICKY_TILE, a.get("dir"))
    r1, s1 = client_turn(host, client, V_ID, STICKY_FACE)
    ev(f"side_change_clears_flag-pre: A teleported {a.get('pos')} -> {STICKY_TILE} keeping dir {a.get('dir')}; "
       f"intent {r1}; {fmt(s1)}")
    v1 = (ua(s1["h"]).get("vis"), ua(s1["c"]).get("vis"))
    cell("side_change_clears_flag-pre", v1 == (True, True), f"vis host/client {v1} (want True on both); V dir h/c "
         f"{ua(s1['h'], V_ID).get('dir')}/{ua(s1['c'], V_ID).get('dir')}")
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": 0}, ("tu",))
    r2, s2 = client_turn(host, client, V_ID, STICKY_AWAY)
    ev(f"side_change_clears_flag-sticky: A base TU 0 on both; intent {r2}; {fmt(s2)}")
    v2 = (ua(s2["h"]).get("vis"), ua(s2["c"]).get("vis"))
    cell("side_change_clears_flag-sticky", v2 == (True, True),
         f"vis host/client {v2} after V turned to {ua(s2['h'], V_ID).get('dir')} "
         f"(want True on both: vanilla keeps the flag on a turn)")
    rec = alien_cycle(host, client, SEED_SIDE_CHANGE, 0.5, held_read=True)
    ds = rec["heldRead"]
    ev(f"side_change_clears_flag-side: caught {rec.get('caught')}; host top {rec.get('heldReadTop')}; {fmt(ds)}")
    held = (ds["h"]["side"] == 1 and ds["c"]["side"] == 1 and "NextTurnState" in (rec.get("heldReadTop") or "")
            and rec.get("caught") is True)
    hvis, chere = ua(ds["h"]).get("vis"), ua(ds["c"]).get("here")
    cell("side_change_clears_flag-side", held and hvis is False and chere is False,
         f"side 1 on both with the host held and the client caught up: {held}; host vis {hvis} (precondition False); "
         f"here(client) {chere} (want False)")
    settle_on_battlescape(client)
    settle_on_battlescape(host)
    session.wait_seq_barrier(host, client, timeout=30)
    s3 = snap(host, client)
    a_evs = [(q, k) for q, k in rec["hev"] if k in CHAIN_KINDS]
    moved = ua(s3["h"]).get("pos") != STICKY_TILE or ua(s3["h"]).get("dir") != a.get("dir")
    ev(f"side_change_clears_flag-after: cycle evs {rec['hev']}; client camera.moves {rec['cam']}; {fmt(s3)}")
    hv, cv = vh_pair(s3)
    cell("side_change_clears_flag-after", s3["h"]["side"] == 0 and s3["c"]["side"] == 0 and hv == (False, False)
         and cv == (False, False) and not a_evs and not moved,
         f"side h/c {s3['h']['side']}/{s3['c']['side']}; vis/here host {hv} client {cv} (want False); A evs {a_evs}; "
         f"A moved {moved}")
    common(host, client, "side_change_clears_flag")


ROW_FNS = {"alien_walks_into_view": row_walks_into_view, "client_turn_sees_alien": row_turn_sees_alien,
           "alien_walks_out_of_view": row_walks_out_of_view, "client_turn_loses_alien": row_turn_loses_alien,
           "side_change_clears_flag": row_side_change_clears}


# ===================== bring-up and staging =====================


def boot(host, client):
    """test_ai_origins' boot with this file's key: SEED_ROSTER on the host before open_new_battle, SEED_MAP before
    newbattle_ok, seat_count 2, pin_ai_neutral, every live X-COM unit's reactions 0 on both (client first)."""
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
    pinned = pin_ai_neutral(host, client, tag="client_alien_sight")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A type host/client {types} (want {A_TYPE})"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == 0 and not u.get("isOut"):  # FACTION_PLAYER
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="client_alien_sight bring-up")
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
    """The chain that sets up alien_walks_into_view: walk_to_start (seed 1), first_path_walk (seed 2), tele A to
    A_START, second_path_walk (seed 2), tele A to A_START, tele V to V_TILE facing V_DIR; each cycle followed by
    closing the client's player-side turn screen. Raises on a pin miss."""
    alien_cycle(host, client, SEED_TO_START, 0.5)
    close_client_screen(host, client)
    s = snap(host, client)
    got = [(ua(s[m]).get("pos"), ua(s[m]).get("dir")) for m in ("h", "c")]
    print(f"[client_alien_sight] staging walk_to_start: A h/c {got}", flush=True)
    assert got == [(A_START, A_START_DIR)] * 2, f"walk_to_start: A at {got} (pin {(A_START, A_START_DIR)} on both)"
    for name in ("first_path_walk", "second_path_walk"):
        rec = alien_cycle(host, client, SEED_WALK_IN, 0.5)
        close_client_screen(host, client)
        print(f"[client_alien_sight] staging {name}: walk {rec['path']}", flush=True)
        assert rec["path"] == IN_PATH, f"{name}: walk {rec['path']} (pin {IN_PATH})"
        tele_both(host, client, A_ID, A_START, A_START_DIR)
    tele_both(host, client, V_ID, V_TILE, V_DIR)
    s = snap(host, client)
    print(f"[client_alien_sight] staged: {fmt(s)}", flush=True)
    got = [(ua(s[m], V_ID).get("pos"), ua(s[m], V_ID).get("dir")) for m in ("h", "c")]
    assert got == [(V_TILE, V_DIR)] * 2, f"V at {got} (pin {(V_TILE, V_DIR)} on both)"


def main():
    global CRASH0
    t0 = time.time()
    host = GameClient("host", 49852, make_user_dir("client_alien_sight_host"))
    client = GameClient("client", 49853, make_user_dir("client_alien_sight_client"))
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
                print(f"[client_alien_sight] shutdown {gc.name}: {short(e, 200)}", flush=True)
    names = [c for _, cells in ROWS for c in cells]
    failed = [c for c in names if not RESULTS.get(c)]
    print(f"\ntest_client_alien_sight: {len(names) - len(failed)}/{len(names)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
