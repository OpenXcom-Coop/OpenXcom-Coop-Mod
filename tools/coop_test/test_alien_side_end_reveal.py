"""test_alien_side_end_reveal.py: the two machines stay in sync when the alien side ends with alien sight the client
has not been sent yet.

A side change's hash covers the alien side's explored map (`revealHostile`). The host sweeps the aliens' sight again at
the side change (CoopFog::authorHostilePass; in a game, for an alien whose sight changed after its side's last
envelope: vanilla's endTurn turning the aliens' turrets back, terrain burning at the turn's end). Those new bits must
reach the client with the side change itself; sent in a later envelope, the client checks the side change's
`revealHostile` hash without them, reports a desync and halts the battle.

Probe: event_state `sideChangeReveal` (host, TEST-ONLY): for each side change, which reveal sets still held bits the
client had not been sent when its hash was built ({turn, newSide, hostile, player}).

ONE boot: test_follow_camera's terror skirmish (STR_TERROR_MISSION, map seed 1, night), lobby key 47731, every alien
pinned (none acts), X-COM reactions 0. One END TURN cycle (the client first, then the host); while the host's alien-side
turn screen is up, the host's alien sweeps are held until the next side change (TEST-ONLY reveal_hostile_pass
{holdUntilSideChange}: as for sight that changes inside endTurn, after the side's last envelope) and alien A (1000000)
is moved (battle_teleport_unit on both) to (34,24,0) facing 6, where it sees ground its side has not explored; then the
host's screen closes, the alien side ends at once and the side change to the civilians sweeps A's new sight.

Cells:
  pending   (precondition) at this cycle's side change to the civilian side (newSide 2) the host's hostile set held
            bits the client had not been sent when the hash was built.
  in_sync   the client reported no desync through the cycle (event_state desyncSeen false) and both machines are back on
            the player side, turn 2.
  common    hash_now full: every bucket EQUAL (revealHostile included); desyncSeen false on both; no new crash file.

One EVIDENCE line, one PASS / FAIL line per cell. One run is the result, no skip path. Exit 0 only when every cell
passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_alien_side_end_reveal.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, assert_hash_clean  # noqa: E402
import test_host_combat as HC  # noqa: E402
from test_delta_core import both, tele_both  # noqa: E402

KEY = "47731"                     # this file's lobby key
A_ID = 1000000                    # the alien moved during its side's turn screen
A_TILE, A_DIR = (34, 24, 0), 6
NEUTRAL = 2
CELLS = ("pending", "in_sync", "common")


def top(gc):
    return ((gc.cmd({"cmd": "get_state"}).get("states") or [None])[-1] or "").replace("class OpenXcom::", "")


def close_turn_screens(gc):
    for _ in range(4):
        if "NextTurnState" not in top(gc):
            return
        gc.cmd({"cmd": "close_nextturn"})
        time.sleep(0.2)


def bring_up(host, client):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=HC.MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": HC.SEED_MAP}))
    pinned = session.pin_ai_neutral(host, client, tag="alien_side_end_reveal")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="alien_side_end_reveal bring-up")
    fps = [battle_state(gc).get("mapFingerprint") for gc in (host, client)]
    assert fps == [HC.MAP_FP, HC.MAP_FP], f"mapFingerprint host/client {fps} (want {HC.MAP_FP})"
    assert A_ID in pinned, f"pin_ai_neutral pinned {pinned} (want {A_ID} among them)"
    for x in battle_state(host)["units"]:
        if x.get("faction") == 0 and not x.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": x["id"], "stat": "reactions",
                                "value": 0}, ("tu",))
    print(f"[alien_side_end_reveal] boot ok: MAP_FP {fps[0]!r} seated {seated.get('soldierIds')} pinned "
          f"{len(pinned)}", flush=True)


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="alien_side_end_reveal common")
        hashed = "all buckets EQUAL"
    except Exception as e:
        hashed = f"{type(e).__name__}: {str(e)[:400]}"
    ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def run(host, client, crash0):
    turn0 = battle_state(host).get("turn")
    n0 = len(event_state(host).get("sideChangeReveal") or [])
    ev = {"turn0": turn0}
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    host.wait_for("host END TURN 1/2", lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                  timeout=20)
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    host.wait_for("alien side on both, the host held on its turn screen",
                  lambda: (battle_state(host).get("side") == 1 and "NextTurnState" in top(host)
                           and battle_state(client).get("side") == 1) or None, timeout=30)
    close_turn_screens(client)
    ev["hold"] = host.cmd({"cmd": "reveal_hostile_pass", "holdUntilSideChange": True})
    ev["moved"] = tele_both(host, client, A_ID, A_TILE, A_DIR)
    close_turn_screens(host)
    t0 = time.time()
    while time.time() - t0 < 40:
        close_turn_screens(host)
        close_turn_screens(client)
        hs, cs = battle_state(host), battle_state(client)
        if (event_state(client).get("desyncSeen") or (hs.get("side") == 0 and cs.get("side") == 0
                                                       and (hs.get("turn") or 0) > turn0 and (cs.get("turn") or 0) > turn0)):
            break
        time.sleep(0.2)
    time.sleep(0.5)
    ring = event_state(host).get("sideChangeReveal") or []
    changes = [r for r in ring if r.get("turn") == turn0 and r.get("newSide") == NEUTRAL]
    ces = event_state(client)
    back = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]
    ev.update(sideChangeReveal=ring[-4:], ringGrew=len(ring) - n0, back=back,
              clientDesyncSeen=ces.get("desyncSeen"), clientTop=top(client))
    print(f"EVIDENCE alien_side_end: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    cells = {"pending": (bool(changes) and changes[-1].get("hostile") is True,
                         f"side change to the civilian side on turn {turn0}: {changes} (want hostile True: A's new "
                         f"sight was swept at the side change, after its side's last envelope)"),
             "in_sync": (ces.get("desyncSeen") is False and back == [(0, turn0 + 1)] * 2,
                         f"client desyncSeen {ces.get('desyncSeen')} (want False); side/turn host/client {back} "
                         f"(want 0/{turn0 + 1} on both)")}
    session.wait_host_idle(host, client, timeout=30)
    cells["common"] = common(host, client, crash0)
    return cells


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49908, make_user_dir("alien_side_end_reveal_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49909, make_user_dir("alien_side_end_reveal_client",
                                                       options={"coopGhostStepper": True}))
    cells = {}
    try:
        try:
            bring_up(host, client)
            cells = run(host, client, crash0)
        except Exception as e:
            print(f"CAPTURE: {type(e).__name__}: {str(e)[:800]}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[alien_side_end_reveal] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    failed = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} alien_side_end-{c}: {detail}", flush=True)
        if not ok:
            failed.append(c)
    print(f"\ntest_alien_side_end_reveal: {len(CELLS) - len(failed)}/{len(CELLS)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
