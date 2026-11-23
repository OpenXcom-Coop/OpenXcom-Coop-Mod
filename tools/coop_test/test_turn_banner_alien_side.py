"""test_turn_banner_alien_side.py: in turn-by-turn co-op the "It is <player>'s turn" banner shows only while the players'
side is playing, never through the alien side.

Turn-by-turn mode passes a baton between the two players during their side: the player without it sees the banner
naming the one who has it. The baton stays with the last player who held it once the side ends, so a banner that only
asks "is the baton someone else's?" tells the other machine "It is <that player>'s turn" over the HIDDEN MOVEMENT screen
for the whole alien turn.

ONE boot: test_host_combat's roster-pinned terror skirmish (STR_TERROR_MISSION, map seed 1), turn-by-turn mode
(test_turn_baton.pre_ok_traditional), lobby key 47741, aliens pinned; alien A (1000000) un-pinned (tu 60, refilled) on
(34,24,0) facing 6, so the alien side runs while the samples are read. The host presses END TURN (the baton passes to
the second player), the second player presses END TURN (the side ends), host set_seed 1 before it closes its alien-side
turn screen; both machines are read every ~0.15 s through the alien side.

Cells:
  start       (guard) at battle start the second player's banner names the host's turn and the host shows none.
  passed      (guard) after the host's END TURN the host's banner names the second player's turn.
  alien_side  every alien-side sample read with the battlescape on top shows no "...'s turn" banner on either machine
              (>= 1 such host sample: precondition).
  next_side   (guard) on the next player side the second player's banner names the host's turn again.
  common      hash_now full: every bucket EQUAL; desyncSeen false on both; no new crash file.

One EVIDENCE line, one PASS / FAIL line per cell. One run is the result, no skip path. Exit 0 only when every cell
passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_turn_banner_alien_side.py
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
from test_turn_baton import pre_ok_traditional  # noqa: E402
from test_delta_core import both, tele_both  # noqa: E402

KEY = "47741"
A_ID, A_TILE, A_DIR, A_TU = 1000000, (34, 24, 0), 6, 60
SEED = 1
TURN_SUFFIX = "'s turn"
CELLS = ("start", "passed", "alien_side", "next_side", "common")


def top(gc):
    return ((gc.cmd({"cmd": "get_state"}).get("states") or [None])[-1] or "").replace("class OpenXcom::", "")


def read(gc):
    bs = battle_state(gc)
    return {"side": bs.get("side"), "turn": bs.get("turn"), "wait": bs.get("coopWaitText") or "",
            "active": event_state(gc).get("coopActiveSeat"), "top": top(gc)}


def both_read(host, client):
    return {"h": read(host), "c": read(client)}


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(interval)
    return bool(pred())


def close_turn_screens(gc):
    for _ in range(4):
        if "NextTurnState" not in top(gc):
            return
        gc.cmd({"cmd": "close_nextturn"})
        time.sleep(0.2)


def bring_up(host, client):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=HC.MISSION, seat_count=2, pre_ok=pre_ok_traditional)
    pinned = session.pin_ai_neutral(host, client, tag="turn_banner_alien_side")
    session.wait_host_idle(host, client, timeout=30)
    assert A_ID in pinned, f"pin_ai_neutral pinned {pinned} (want {A_ID} among them)"
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU,
                        "refill": True}, ("tu",))
    tele_both(host, client, A_ID, A_TILE, A_DIR)
    assert_hash_clean(host, client, full=True, what="turn_banner_alien_side bring-up")


def common(host, client, crash0):
    try:
        assert_hash_clean(host, client, full=True, what="turn_banner_alien_side common")
        hashed = "all buckets EQUAL"
    except Exception as e:
        hashed = f"{type(e).__name__}: {str(e)[:400]}"
    ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    return (hashed == "all buckets EQUAL" and ds == [False, False] and not crash,
            f"hash {hashed}; desyncSeen host/client {ds} (want False/False); new crash files {crash} (want none)")


def run(host, client, crash0):
    ev, cells = {}, {}
    time.sleep(0.6)  # the banner is driven per frame
    s0 = ev["start"] = both_read(host, client)
    cells["start"] = (s0["c"]["wait"].endswith(TURN_SUFFIX) and s0["h"]["wait"] == "",
                      f"client banner {s0['c']['wait']!r} (want the host's turn), host {s0['h']['wait']!r} (want '')")
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    wait_until(lambda: event_state(host).get("coopActiveSeat") == 1 and read(host)["wait"].endswith(TURN_SUFFIX), 10)
    s1 = ev["passed"] = both_read(host, client)
    cells["passed"] = (s1["h"]["active"] == 1 and s1["h"]["wait"].endswith(TURN_SUFFIX),
                       f"host active seat {s1['h']['active']} banner {s1['h']['wait']!r} (want 1 and the second "
                       f"player's turn)")
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    wait_until(lambda: battle_state(host).get("side") == 1 and battle_state(client).get("side") == 1, 20)
    close_turn_screens(client)
    host.ok({"cmd": "set_seed", "seed": SEED})
    close_turn_screens(host)
    samples = []
    t0 = time.time()
    while time.time() - t0 < 15:
        r = both_read(host, client)
        if r["h"]["side"] != 1 and r["c"]["side"] != 1:
            break
        samples.append(r)
        time.sleep(0.15)
    on_top = [(m, r[m]["wait"]) for r in samples for m in ("h", "c")
              if r[m]["side"] == 1 and r[m]["top"] == "BattlescapeState"]
    host_on_top = [w for m, w in on_top if m == "h"]
    turn_lines = [(m, w) for m, w in on_top if w.endswith(TURN_SUFFIX)]
    ev["alienSide"] = [f"{r['h']['side']}/{r['h']['active']}/{r['h']['wait']!r}/{r['h']['top'][:12]} | "
                       f"{r['c']['side']}/{r['c']['active']}/{r['c']['wait']!r}/{r['c']['top'][:12]}" for r in samples]
    cells["alien_side"] = (bool(host_on_top) and not turn_lines,
                           f"alien-side samples with the battlescape on top: host {len(host_on_top)} (want >= 1); "
                           f"'...'s turn' banners among them {turn_lines[:4]} (want none)")
    wait_until(lambda: (close_turn_screens(host), close_turn_screens(client),
                        battle_state(host).get("side") == 0 and battle_state(client).get("side") == 0
                        and (battle_state(host).get("turn") or 0) >= 2 and top(host) == "BattlescapeState"
                        and top(client) == "BattlescapeState")[-1], 40, interval=0.2)
    wait_until(lambda: read(client)["wait"].endswith(TURN_SUFFIX), 5)
    s3 = ev["next"] = both_read(host, client)
    cells["next_side"] = (s3["c"]["side"] == 0 and s3["c"]["wait"].endswith(TURN_SUFFIX) and s3["h"]["wait"] == "",
                          f"client side {s3['c']['side']} banner {s3['c']['wait']!r} (want 0 and the host's turn), "
                          f"host {s3['h']['wait']!r} (want '')")
    session.wait_host_idle(host, client, timeout=30)
    cells["common"] = common(host, client, crash0)
    print(f"EVIDENCE turn_banner: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    return cells


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49912, make_user_dir("turn_banner_alien_side_host"))
    client = GameClient("client", 49913, make_user_dir("turn_banner_alien_side_client"))
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
                print(f"[turn_banner_alien_side] shutdown {gc.name}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    failed = []
    for c in CELLS:
        ok, detail = cells.get(c, (False, "not reached"))
        print(f"{'PASS' if ok else 'FAIL'} turn_banner-{c}: {detail}", flush=True)
        if not ok:
            failed.append(c)
    print(f"\ntest_turn_banner_alien_side: {len(CELLS) - len(failed)}/{len(CELLS)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
