"""test_alien_side_end_reveal.py: the two machines stay in sync when the alien side ends with alien sight the client
has not been sent yet.

Vanilla's SavedBattleGame::endTurn turns every alien's turret back to its body facing. An alien that turned during its
side therefore looks new to the host's alien-sight cache at the side change, the host sweeps it again, and when that
sweep finds tiles (here: ground the alien's plasma shots opened up) the side change's hash already counts them. Those
bits must reach the client with the side change itself; sent in a later envelope, the client checks the side change's
`revealHostile` hash without them, reports a desync and halts the battle.

Probe: event_state `sideChangeReveal` (host, TEST-ONLY): for each side change, which reveal sets still held bits the
client had not been sent when its hash was built ({turn, newSide, hostile, player}).

ONE boot: test_follow_camera's terror skirmish (STR_TERROR_MISSION, map seed 1, night), lobby key 47731, aliens pinned,
X-COM reactions 0. Staging: alien A (1000000) un-pinned (tu 60, refilled), client soldier 8 on (20,24,0) facing 2, A on
(34,24,0) facing 6. One END TURN cycle with host set_seed 3 right before its press: A turns and fires three plasma snap
shots (measured: hits at (32,14,2) and nearby), then the side changes to the civilians.

Cells:
  shot      (precondition) the host emitted >= 1 `shot` cue in the cycle (its own openxcom.log `[coop-cue] shot`
            lines: a desync repair reloads the battle and clears the event log).
  pending   (precondition) at this cycle's side change to the civilian side (newSide 2) the host's hostile set held
            bits the client had not been sent when the hash was built.
  in_sync   the client reported no desync through the cycle (event_state desyncSeen false).
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
import test_client_alien_sight as AS  # noqa: E402  (alien_cycle and its per-GameClient lock)
import test_host_combat as HC  # noqa: E402
from test_delta_core import both, tele_both  # noqa: E402

KEY = "47731"                     # this file's lobby key
A_ID, V_ID = 1000000, 8           # the alien, the client soldier
A_TU = 60
V_TILE, V_DIR = (20, 24, 0), 2
A_TILE, A_DIR = (34, 24, 0), 6
SEED = 3                          # host set_seed right before its END TURN press
NEUTRAL = 2
CELLS = ("shot", "pending", "in_sync", "common")


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
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU,
                        "refill": True}, ("tu",))
    tele_both(host, client, V_ID, V_TILE, V_DIR)
    tele_both(host, client, A_ID, A_TILE, A_DIR)
    print(f"[alien_side_end_reveal] boot ok: MAP_FP {fps[0]!r} seated {seated.get('soldierIds')} pinned "
          f"{len(pinned)}; A on {A_TILE} facing {A_DIR}, soldier {V_ID} on {V_TILE} facing {V_DIR}", flush=True)


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


def host_log_size(host):
    try:
        return os.path.getsize(os.path.join(host.user_dir, "openxcom.log"))
    except OSError:
        return 0


def host_log_since(host, offset):
    try:
        with open(os.path.join(host.user_dir, "openxcom.log"), "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def run(host, client, crash0):
    log0 = host_log_size(host)
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    turn0 = battle_state(host).get("turn")
    n0 = len(event_state(host).get("sideChangeReveal") or [])
    ev = {"seq0": seq0, "turn0": turn0}
    try:
        rec = AS.alien_cycle(host, client, SEED, 1.0)
        ev["cycle"] = "done"
    except Exception as e:  # a client halted by a desync never gets back to its battlescape
        rec = None
        ev["cycle"] = f"{type(e).__name__}: {str(e)[:300]}"
    time.sleep(1.0)  # the host's log flush
    cues = [ln.split("[coop-cue] ", 1)[1][:60] for ln in host_log_since(host, log0) if "[coop-cue] shot seq" in ln]
    ring = event_state(host).get("sideChangeReveal") or []
    changes = [r for r in ring if r.get("turn") == turn0 and r.get("newSide") == NEUTRAL]
    ces = event_state(client)
    ev.update(shotCues=cues, sideChangeReveal=ring[-4:], ringGrew=len(ring) - n0,
              clientDesync={k: ces.get(k) for k in ("desyncSeen", "desyncBucket", "desyncSeq")},
              clientTop=(client.cmd({"cmd": "get_state"}).get("states") or [None])[-1])
    print(f"EVIDENCE alien_side_end: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    cells = {"shot": (bool(cues), f"host `shot` cues in the cycle {cues} (want >= 1)"),
             "pending": (bool(changes) and changes[-1].get("hostile") is True,
                         f"side change to the civilian side on turn {turn0}: {changes} (want hostile True: the alien "
                         f"sight swept at the side change was not yet sent when its hash was built)"),
             "in_sync": (ces.get("desyncSeen") is False,
                         f"client desyncSeen {ces.get('desyncSeen')} (want False)")}
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
