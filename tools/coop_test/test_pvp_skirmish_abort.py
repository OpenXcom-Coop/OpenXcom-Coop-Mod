"""PvP skirmish abort: vote system in adversarial mode.

Run:  python tools/coop_test/test_pvp_skirmish_abort.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "47993"


def _has(gc, name):
    return any(name in s
               for s in gc.cmd({"cmd": "get_state"})["states"])


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def _vote(gc, want):
    """Wait for vote_state.{} to be true, returning the full vote dict."""
    return gc.wait_for(
        f"vote {want} on {gc.name}",
        lambda: (lambda s: s if s.get(want) else None)(
            gc.ok({"cmd": "vote_state"})),
        timeout=30, interval=0.25)


def test_abort(fails, alien_player, gamemode):
    tag = f"gm{gamemode}_{alien_player}"
    print(f"\n--- abort {tag} ---")
    host = GameClient("host", 48902, make_user_dir(f"pvp_ab_{tag}_host"))
    client = GameClient("client", 48903, make_user_dir(f"pvp_ab_{tag}_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT,
                                           alien_player=alien_player)
        if gm != gamemode:
            _fail(fails, f"{tag}: expected gamemode {gamemode}, got {gm}")
            return
        print(f"    in battle, gamemode {gamemode}")

        host.ok({"cmd": "battle_action", "action": "abort"})

        for gc in (host, client):
            v = _vote(gc, "active")
            if v.get("action") != "abandon_mission":
                _fail(fails, f"{tag}: {gc.name} wrong vote: {v}")
                return
        print("    abandon-mission vote active on both machines")

        cast = client.ok({"cmd": "vote_cast", "yes": True})
        if not cast.get("accepted"):
            _fail(fails, f"{tag}: vote_cast rejected: {cast}")
            return

        for gc in (host, client):
            v = _vote(gc, "finished")
            if not v.get("passed"):
                _fail(fails, f"{tag}: {gc.name} vote did not pass: {v}")
                return
        print("    vote passed on both machines")

        # Drain post-battle popups to the main menu.  On the skirmish host,
        # finishBattle pushes GoToMainMenuState after DebriefingState.  The
        # client receives DebriefingState via a network packet.
        deadline = time.time() + 120
        for gc, label in ((host, "host"), (client, "client")):
            while time.time() < deadline:
                st = [s.replace("class OpenXcom::", "")
                      for s in gc.cmd({"cmd": "get_state"})["states"]]
                if "MainMenuState" in st or "GoToMainMenuState" in st:
                    break
                r = gc.cmd({"cmd": "dismiss_popup"})
                if r.get("wait"):
                    time.sleep(1)
                elif not r.get("ok"):
                    time.sleep(0.5)
                time.sleep(0.3)
            st = [s.replace("class OpenXcom::", "")
                  for s in gc.cmd({"cmd": "get_state"})["states"]]
            if "MainMenuState" in st or "GoToMainMenuState" in st:
                print(f"PASS {tag} abort: {label} returned to main menu")
            else:
                _fail(fails, f"{tag}: {label} not at main menu: {st[-3:]}")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_abort(fails, "client", 2)
    test_abort(fails, "host", 3)

    print("\n==== PvP skirmish abort summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: vote passes, both return to main menu")
    sys.exit(0)


if __name__ == "__main__":
    main()
