"""Issue #136: hotseat mode must be startable from the New Battle screen.

Hotseat is a single-machine, no-network mode (Player 1 = X-Com, Player 2 = the
aliens, passing the keyboard). The PR #75 menu redesign buried the toggle inside
the networked HOST dialog, which hid START HOST and offered no way to launch a
battle - so it was "impossible to actually start a hotseat game". The fix moves
the toggle onto the New Battle screen; the existing OK/START button then
launches the battle with the hotseat flag honored.

This is a single-client test on purpose: hotseat has no network component.

Run:  python tools/coop_test/test_hotseat_start.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def test_hotseat_starts_from_new_battle():
    gc = GameClient("hotseat", 48788, make_user_dir("hotseat_start"))
    try:
        gc.spawn()
        gc.connect()

        # nothing armed at the main menu
        assert gc.ok({"cmd": "get_coop"})["hotseat"] is False, \
            "hotseat should start disarmed"

        # New Battle > arm HOTSEAT (drives the real on-screen toggle handler)
        gc.ok({"cmd": "open_new_battle"})
        gc.wait_for("new battle screen",
                    lambda: session.has_state(gc, "NewBattleState"))
        armed = gc.ok({"cmd": "newbattle_hotseat", "on": True})
        assert armed["hotseat"] is True, f"toggle did not arm hotseat: {armed}"
        assert gc.ok({"cmd": "get_coop"})["hotseat"] is True

        # START launches the battle with the flag honored (the solo branch, since
        # hotseat is not a networked co-op session)
        gc.ok({"cmd": "newbattle_ok"})
        gc.wait_for("briefing",
                    lambda: session.has_state(gc, "BriefingState"), timeout=120)
        gc.ok({"cmd": "close_briefing"})
        gc.wait_for("battlescape",
                    lambda: session.has_state(gc, "BattlescapeState"), timeout=120)

        bs = gc.ok({"cmd": "battle_state"})
        assert bs["inBattle"], f"no battle after starting hotseat: {bs}"
        # the flag must survive the trip into the battle - the battlescape reads
        # it every turn to swap unit control between the two humans
        assert gc.ok({"cmd": "get_coop"})["hotseat"] is True, \
            "hotseat flag dropped on the way into the battle"
        print(f"PASS: hotseat armed on New Battle and launched, stack={states(gc)}")
    finally:
        gc.shutdown()


def test_disarm_leaves_normal_battle():
    """Toggling hotseat off again returns to a normal (AI-driven) skirmish: the
    flag must be clear so the battle is not accidentally left in hotseat."""
    gc = GameClient("hotseat_off", 48789, make_user_dir("hotseat_off"))
    try:
        gc.spawn()
        gc.connect()

        gc.ok({"cmd": "open_new_battle"})
        gc.wait_for("new battle screen",
                    lambda: session.has_state(gc, "NewBattleState"))
        gc.ok({"cmd": "newbattle_hotseat", "on": True})
        off = gc.ok({"cmd": "newbattle_hotseat", "on": False})
        assert off["hotseat"] is False, f"toggle did not disarm hotseat: {off}"
        assert gc.ok({"cmd": "get_coop"})["hotseat"] is False
        print("PASS: hotseat toggle disarms cleanly")
    finally:
        gc.shutdown()


def main():
    test_hotseat_starts_from_new_battle()
    test_disarm_leaves_normal_battle()
    print("ALL HOTSEAT START TESTS PASSED")


if __name__ == "__main__":
    main()
