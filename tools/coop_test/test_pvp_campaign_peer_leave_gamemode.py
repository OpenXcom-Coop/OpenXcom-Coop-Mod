"""PvP campaign: the host keeps its game mode when the client leaves.

A PvP campaign (game mode 2) is stored with the Separate campaign type but
keeps main's two-world rules. connectionTCP::isSeparateCampaign() and
SavedGame::isSeparateCoopCampaign() tell the two apart by the game mode. A
client that leaves through its menu on the geoscape reaches the host's
disconnectTCP drop path, which used to zero the game mode outside a battle.
The host then waited for the rejoin with Separate single-world rules applied
to its PvP world, and a save in that wait would record game mode 0.

Expected: while the host waits for the player, game mode stays 2 and the
world is not classified as a Separate single world.

Run:  python tools/coop_test/test_pvp_campaign_peer_leave_gamemode.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture


def main():
    fails = []
    host = GameClient("host", 48934, make_user_dir("pvp_leave_gm_h"))
    client = GameClient("client", 48935, make_user_dir("pvp_leave_gm_c"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        gm = pvp_fixture.start_pvp_campaign(host, client, "47995", alien_player="client")
        before = host.ok({"cmd": "get_coop"})
        assert gm == 2 and before.get("gamemode") == 2 and not before.get("separateWorld"), \
            f"setup: expected a gamemode-2 PvP world, got fixture={gm} coop={before}"

        # The client leaves through its menu: a clean leave, not a lost socket.
        client.ok({"cmd": "disconnect_to_menu"})
        host.wait_for(
            "host waits for the player",
            lambda: (not host.cmd({"cmd": "get_coop"}).get("clientName")
                     or any("CoopState" in s for s in host.cmd({"cmd": "get_state"}).get("states", [])))
                    or None,
            timeout=30, interval=0.25)
        # Read across the whole wait window, not once.
        deadline = time.time() + 5
        while time.time() < deadline:
            coop = host.cmd({"cmd": "get_coop"})
            if coop.get("gamemode") != 2 or coop.get("separateWorld"):
                fails.append(f"host lost its PvP game mode after the client left: "
                             f"gamemode={coop.get('gamemode')} separateWorld={coop.get('separateWorld')}")
                break
            time.sleep(0.25)
        if not fails:
            print("PASS: host keeps gamemode 2 and two-world rules while it waits")
    finally:
        host.shutdown(); client.shutdown()

    print("\n==== PvP peer-leave game mode summary ====")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        sys.exit(2)
    print("  host game mode survived the client's leave")
    sys.exit(0)


if __name__ == "__main__":
    main()
