"""Issue #82: leaving the battlescape must not leave the battlescape behind.

A menu picks its palette in its constructor by asking the SavedGame whether a
battle is running (State::setInterface -> setPaletteByDepth). Several exit points
jumped straight to the main menu without dropping the SavedGame, so the battle
outlived the battlescape and every menu opened afterwards was told "yes, we are in
a battle" and painted itself in the battlescape palette.

Two things are asserted, in order of strength:

  * the INVARIANT - at the main menu there is no world at all (`world_state`:
    has_save and has_battle both false). This catches an exit point that skipped
    the GoToMainMenuState teardown even when nothing visibly changes colour.
  * the SYMPTOM - the LOAD GAME list opened after the exit has a byte-identical
    palette to the same list opened on a pristine boot of the same build.

Cases:
  T1  CANCEL on the host window over a loaded mid-battle co-op save   (the report)
  T2  the host vanishes mid-battle; the client acknowledges and leaves (the EDIT)

Not covered here (needs its own battle bring-up, and the paths are the same two
call sites): the in-battle `disconnect_to_menu` teardown, and the skirmish
debriefing exit.

Run:  python tools/coop_test/test_battlescape_exit_palette.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import shared_fixture
import test_coop_alien_launcher_item_loss as I74

PORTS = (47821, 47822, 47966)
SAVE = "exit82_battle.sav"


# ---- probes ---------------------------------------------------------------

def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has(gc, name):
    return any(name in s for s in states(gc))


def load_menu_palette(gc):
    """Open LOAD GAME, read the list's palette, close it again."""
    gc.ok({"cmd": "open_load_menu"})
    gc.wait_for("load list open", lambda: has(gc, "ListLoadState") or None, timeout=30)
    pal = None
    for e in gc.ok({"cmd": "get_palettes"})["states"]:
        if "ListLoadState" in e["state"]:
            pal = e["colors"]
    assert pal is not None, "ListLoadState vanished before its palette could be read"
    gc.ok({"cmd": "pop_state"})
    gc.wait_for("load list closed", lambda: (not has(gc, "ListLoadState")) or None, timeout=30)
    return pal


def assert_no_world(gc, where):
    w = gc.ok({"cmd": "world_state"})
    assert not w["has_battle"], f"{where}: a SavedBattleGame outlived the battlescape ({w})"
    assert not w["has_save"], f"{where}: the SavedGame reached the main menu ({w})"


def assert_menu_palette(gc, control, where):
    pal = load_menu_palette(gc)
    assert pal == control, (
        f"{where}: the LOAD GAME list is not in the standard palette.\n"
        f"  expected (pristine boot): {control[:8]}\n"
        f"  got:                      {pal[:8]}")


def capture_control_palette():
    """The LOAD GAME palette on a boot of this build that has never seen a battle."""
    gc = GameClient("control", 47820, make_user_dir("exit82_control"))
    try:
        gc.spawn()
        gc.connect()
        return load_menu_palette(gc)
    finally:
        gc.shutdown()


# ---- cases ----------------------------------------------------------------

def test_client_after_host_loss(client, control):
    """T2: the host process dies mid-battle. The client is told, acknowledges the
    "Server connection lost" dialog, and must arrive at the main menu with no world."""
    client.wait_for("connection-lost dialog",
                    lambda: (client.cmd({"cmd": "coop_dialog_info"}).get("code") == 21) or None,
                    timeout=180, interval=2.0)
    client.ok({"cmd": "coop_dialog_back"})
    client.wait_for("client back at the main menu",
                    lambda: has(client, "MainMenuState") or None, timeout=60)

    assert_no_world(client, "T2 host lost mid-battle")
    assert_menu_palette(client, control, "T2 host lost mid-battle")
    print("PASS T2: a client let out of a lost battle carries no world into the menus")


def test_host_menu_cancel(host, control):
    """T1: load a mid-battle co-op save from the main menu (which pushes the
    battlescape and then the host window on top of it) and press CANCEL."""
    host.ok({"cmd": "load_save_menu", "file": SAVE})
    host.wait_for("host window over the battle save",
                  lambda: has(host, "HostMenu") or None, timeout=120, interval=1.0)

    w = host.ok({"cmd": "world_state"})
    assert w["has_battle"], f"T1 is unsound: the save did not bring a battle with it ({w})"

    host.ok({"cmd": "host_menu_cancel"})
    host.wait_for("back at the main menu",
                  lambda: (has(host, "MainMenuState") and not has(host, "HostMenu")) or None,
                  timeout=60)

    assert_no_world(host, "T1 host-window CANCEL")
    assert_menu_palette(host, control, "T1 host-window CANCEL")
    print("PASS T1: CANCEL on the host window drops the battle; LOAD GAME stays standard")


# ---- driver ---------------------------------------------------------------

def main():
    fails = []

    control = capture_control_palette()
    print(f"control LOAD GAME palette captured: {control[:4]}...")

    # Phase A: a real co-op battle, so the exits under test are the real ones.
    js = shared_fixture.bring_up("exit82", PORTS)
    host_dir = js.host_dir
    try:
        I74.enter_battle(js)
        print("both machines are in the battlescape")

        # A mid-battle save for T1. The host save embeds the client world, so the
        # reloaded save is a genuine co-op battle save (it opens the host window).
        js.host.ok({"cmd": "save_game", "file": SAVE})
        assert os.path.exists(os.path.join(host_dir, "xcom1", SAVE)), "mid-battle save not on disk"
        print(f"host saved mid-battle -> {SAVE}")

        # T2: pull the host out from under the client, mid-battle.
        js.host.shutdown()
        try:
            test_client_after_host_loss(js.client, control)
        except Exception as e:
            fails.append(f"T2: {e}")
            print(f"FAIL T2: {e}")
    except Exception as e:
        fails.append(f"phase A (battle bring-up): {e}")
        print(f"FAIL phase A: {e}")
    finally:
        js.shutdown()

    # Phase B: a fresh instance that loads the mid-battle save from the menu.
    host = GameClient("host", PORTS[0], host_dir)
    try:
        host.spawn()
        host.connect()
        test_host_menu_cancel(host, control)
    except Exception as e:
        fails.append(f"T1: {e}")
        print(f"FAIL T1: {e}")
    finally:
        host.shutdown()

    if fails:
        print("\n%d battlescape-exit case(s) FAILED:" % len(fails))
        for f in fails:
            print("  " + f)
        return 2
    print("\nALL BATTLESCAPE EXIT PALETTE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
