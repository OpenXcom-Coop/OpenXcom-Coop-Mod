"""Custom Battle regression: a client drop at debrief must not reopen the lobby.

The tactical world has already been cleared when DebriefingState is shown, so
coopBattleLive() is false.  The host disconnect path used to mistake that for a
pre-battle custom-battle session and push LobbyMenu underneath the disconnect
notice.

Run manually:
    python tools/coop_test/test_skirmish_debrief_disconnect.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import pvp_fixture as PVP
import session


PORT = "48023"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def in_debrief(gc):
    return "DebriefingState" in states(gc) or None


def test_client_disconnect_does_not_open_lobby_on_host_debrief():
    host = GameClient("host", 49023,
                      make_user_dir("skirm_debrief_drop_host"))
    client = GameClient("client", 49024,
                        make_user_dir("skirm_debrief_drop_client"))

    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        # PvP is used only to end the Custom Battle deterministically on both
        # machines.  This still exercises the common skirmish disconnect path.
        gamemode = PVP.start_pvp_skirmish_battle(
            host, client, PORT, alien_player="client")
        assert gamemode == 2, f"expected PvP gamemode 2, got {gamemode}"

        host_battle = host.ok({"cmd": "battle_state"})
        executor = host if host_battle.get("coopTurn") == 2 else client

        # Wipe the client side and end the executor's turn.  The normal PvP
        # finishBattle path must put both instances on their debriefing screen.
        killed = executor.ok({
            "cmd": "battle_action",
            "action": "kill_unit",
            "coop_side": 1,
        }).get("killed", [])
        assert killed, "the client side had no living unit to eliminate"
        executor.ok({"cmd": "battle_action", "action": "end_turn_button"})

        host.wait_for("host custom-battle debriefing",
                      lambda: in_debrief(host), timeout=40, interval=0.25)
        client.wait_for("client custom-battle debriefing",
                        lambda: in_debrief(client), timeout=40, interval=0.25)

        before = states(host)
        assert "LobbyMenu" not in before, \
            f"host already had a lobby before the disconnect: {before}"

        # Abrupt process shutdown models a client crash/network loss.  The host
        # receives the normal remote-disconnect event and runs disconnectTCP().
        client.shutdown()

        host.wait_for(
            "host notices the disconnected client",
            lambda: ("CoopState" in states(host)) or None,
            timeout=30,
            interval=0.25,
        )

        after = states(host)
        assert "DebriefingState" in after, \
            f"client disconnect removed the host debriefing: {after}"
        assert "LobbyMenu" not in after, \
            f"client disconnect reopened the lobby over host debriefing: {after}"

        print("PASS: client disconnect left the host on Custom Battle debriefing "
              "without opening LobbyMenu")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    test_client_disconnect_does_not_open_lobby_on_host_debrief()
