"""Issue #74 - stand up a live 2-player session parked EXACTLY one step before
the repro, and leave both games running for a human to drive.

By default it runs the UNFIXED binary (bin/x64/Release-nofix/OpenXcom.exe) so the
bug is still present; pass --fixed to use the normal build and watch the same
steps come out clean.

What it leaves you with
-----------------------
  * two visible game windows (host left, client right), both on the tactical map
    of ONE SHARED co-op battle, coop turn initialised;
  * an X-COM soldier holding STR_BLASTER_LAUNCHER + a loaded STR_BLASTER_BOMB;
  * an alien holding the same, in the hand named by --alien-hand (default LEFT -
    the broken case: nobody clicks a hand button for an AI actor, so the packet
    reports `BattlescapeState::_hand`, which is still its "right" default);
  * a snapshot of the pre-shot item census written next to this script, so
    repro74_probe.py can diff against it.

Then trigger the shot and look at the result - see the printed instructions, or
`python tools/coop_test/repro74_probe.py --help`.

The script exits when set-up is done; the two games keep running (the in-game
TestServer just goes back to listening, so the probe can reconnect). Close the
windows, or run `repro74_probe.py quit`, when you are finished.

Run:  python tools/coop_test/repro74_setup.py
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
import session

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "repro74_state.json")
NOFIX_EXE = os.path.join(harness.REPO, "bin", "x64", "Release-nofix", "OpenXcom.exe")


def _visible_spawn(self, extra_args=()):
    """harness.GameClient.spawn, but the window opens NORMAL instead of
    minimised - a human has to be able to see and click these two games."""
    harness._acquire_machine_lock()
    env = os.environ.copy()
    env["OXC_TEST_PORT"] = str(self.port)
    env["SDL_VIDEO_WINDOW_POS"] = "0,40" if "host" in self.name else "700,40"
    args = [harness.EXE, "-user", self.user_dir] + list(extra_args)
    self.proc = subprocess.Popen(args, env=env, cwd=os.path.dirname(harness.EXE))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixed", action="store_true",
                    help="use bin/x64/Release (the FIXED build) instead of Release-nofix")
    ap.add_argument("--alien-hand", choices=("left", "right"), default="left",
                    help="hand the alien's blaster launcher goes in "
                         "(default left = the broken case; right is the control)")
    ap.add_argument("--ports", default="48796,48797,48196",
                    help="host_test,client_test,coop_session")
    args = ap.parse_args()

    if not args.fixed:
        if not os.path.exists(NOFIX_EXE):
            sys.exit(f"no unfixed build at {NOFIX_EXE}\n"
                     f"build one by stashing the engine fix and running "
                     f"tools/worktree_bootstrap.ps1 -Build, then copying "
                     f"bin/x64/Release to bin/x64/Release-nofix")
        harness.EXE = NOFIX_EXE
    harness.GameClient.spawn = _visible_spawn

    # imported AFTER the patches so they pick up the exe override
    import shared_fixture
    import test_coop_alien_launcher_item_loss as T

    ports = tuple(int(p) for p in args.ports.split(","))
    print(f"exe   : {harness.EXE}")
    print(f"alien : blaster launcher in its {args.alien_hand.upper()} hand")
    print("bringing up the SHARED campaign and flying a squad to a terror site "
          "(a few minutes)...")

    js = shared_fixture.bring_up("i74m", ports)
    host, client = js.host, js.client
    T.enter_battle(js)

    hb = T.battle(host)
    soldier = next(u for u in hb["units"] if u["faction"] == 0 and not u["isOut"])
    alien = next(u for u in hb["units"] if u["faction"] == 1 and not u["isOut"])

    given = {}
    for tag, gc in (("host", host), ("client", client)):
        given[tag] = [T.arm(gc, soldier["id"], "right"),
                      T.arm(gc, alien["id"], args.alien_hand)]
    for i in range(2):
        h, c = given["host"][i], given["client"][i]
        if (h["weaponId"], h["ammoId"]) != (c["weaponId"], c["ammoId"]):
            sys.exit(f"set-up failed: the two machines assigned different item ids "
                     f"({h} vs {c}) - the session is not in a clean state")

    owner = None
    for gc, tag in ((host, "host"), (client, "client")):
        if session.can_drive(T.battle(gc)):
            owner = tag
    census = {"host": T.census(host), "client": T.census(client)}
    diff = T.diff_census(census["host"], census["client"])

    state = {
        "ports": {"host": ports[0], "client": ports[1]},
        "soldier": soldier["id"],
        "alien": alien["id"],
        "alien_pos": [alien["x"], alien["y"], alien["z"]],
        "alien_hand": args.alien_hand,
        "soldier_launcher": given["host"][0]["weaponId"],
        "soldier_bomb": given["host"][0]["ammoId"],
        "alien_launcher": given["host"][1]["weaponId"],
        "alien_bomb": given["host"][1]["ammoId"],
        "sim_owner": owner,
        "exe": harness.EXE,
        "pre_census": {k: {str(i): v for i, v in c.items()} for k, c in census.items()},
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)

    print()
    print("=" * 72)
    print("READY - both windows are on the tactical map of one SHARED co-op battle")
    print("=" * 72)
    print(f"  soldier unit {soldier['id']}: launcher item {state['soldier_launcher']}, "
          f"bomb {state['soldier_bomb']} (right hand)")
    print(f"  alien   unit {alien['id']}: launcher item {state['alien_launcher']}, "
          f"bomb {state['alien_bomb']} ({args.alien_hand} hand) "
          f"@({alien['x']},{alien['y']},{alien['z']})")
    print(f"  item instances: {len(census['host'])} on each machine, "
          f"{'IDENTICAL' if not diff else 'ALREADY DIVERGED: ' + str(diff)}")
    print(f"  simulation owner (the side whose actions replicate): {owner}")
    print(f"  state written to {STATE_PATH}")
    print()
    print("TRIGGER THE SHOT - two ways:")
    print()
    print("  A) let the alien AI do it (closest to the field report). End the turn")
    print("     on both machines and watch the alien turn play out; the AI uses")
    print("     BA_LAUNCH when it holds a blaster launcher.")
    print()
    print("  B) fire it deterministically, from the machine that owns the")
    print("     simulation:")
    print("       python tools/coop_test/repro74_probe.py fire")
    print()
    print("THEN READ THE RESULT:")
    print("       python tools/coop_test/repro74_probe.py check")
    print()
    print("  Unfixed, the peer never spends the alien's blaster bomb (it shot with")
    print("  a fabricated weapon that has no ammo), so `check` reports the bomb")
    print("  surviving on ONE machine only, and `check --idspace` shows the two")
    print("  item-id counters have drifted a step apart - from then on every id in")
    print("  the coop protocol means a different item on the two machines.")
    print()
    print("  Both games keep running after this script exits. Close the windows, or")
    print("  run: python tools/coop_test/repro74_probe.py quit")


if __name__ == "__main__":
    main()
