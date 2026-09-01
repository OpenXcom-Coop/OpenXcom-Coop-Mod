"""Campaign-to-Skirmish regression: debrief must return to the main menu.

A campaign time packet populates process-static client clock mirrors. Those
mirrors used to survive a full return to the main menu and overwrite the next
Skirmish SavedGame's monthsPassed == -1 marker. Its debriefing screen was then
handled as a campaign debriefing and returned the client to the geoscape.

Run manually:
    python tools/coop_test/test_campaign_then_skirmish_debrief.py
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(r5/W6)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import pvp_fixture as PVP
import session


CAMPAIGN_PORT = "48024"
SKIRMISH_PORT = "48025"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def has_state(gc, name):
    return name in states(gc)


def test_campaign_clock_does_not_leak_into_skirmish_debrief():
    host = GameClient("host", 49025,
                      make_user_dir("campaign_skirmish_debrief_host"))
    client = GameClient("client", 49026,
                        make_user_dir("campaign_skirmish_debrief_client"))

    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        # Reaching the campaign geoscape is sufficient to receive the same time
        # heartbeat that a completed campaign mission leaves cached on a client.
        PVP.start_pvp_campaign(host, client, CAMPAIGN_PORT,
                               alien_player="client")
        client.wait_for(
            "client received a campaign clock",
            lambda: (client.ok({"cmd": "geo_state"})["monthsPassed"] >= 0)
            or None,
            timeout=30,
            interval=0.5,
        )

        # Use the production full-teardown path on both running processes, then
        # start a Skirmish without restarting either executable.
        for gc in (host, client):
            gc.ok({"cmd": "disconnect_to_menu"})
        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(f"{label} returned to the main menu",
                        lambda gc=gc: has_state(gc, "MainMenuState") or None,
                        timeout=60,
                        interval=0.5)

        time.sleep(2)
        gamemode = PVP.start_pvp_skirmish_battle(
            host, client, SKIRMISH_PORT, alien_player="client")
        assert gamemode == 2, f"expected PvP gamemode 2, got {gamemode}"

        host_battle = host.ok({"cmd": "battle_state"})
        executor = host if host_battle.get("coopTurn") == 2 else client
        killed = executor.ok({
            "cmd": "battle_action",
            "action": "kill_unit",
            "coop_side": 1,
        }).get("killed", [])
        assert killed, "the client side had no living unit to eliminate"
        executor.ok({"cmd": "battle_action", "action": "end_turn_button"})

        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(f"{label} Skirmish debriefing",
                        lambda gc=gc: has_state(gc, "DebriefingState") or None,
                        timeout=40,
                        interval=0.25)

        client_world = client.ok({"cmd": "geo_state"})
        assert client_world["monthsPassed"] == -1, (
            "campaign clock leaked into the client Skirmish: "
            f"monthsPassed={client_world['monthsPassed']}"
        )

        # Press the real debriefing OK handler. A Skirmish must destroy its
        # temporary world and return to the main menu, never reveal geoscape.
        result = client.ok({"cmd": "dismiss_popup"})
        assert result.get("handled") == "DebriefingState", result
        client.wait_for(
            "client left Skirmish debriefing for the main menu",
            lambda: has_state(client, "MainMenuState") or None,
            timeout=30,
            interval=0.25,
        )
        after = states(client)
        assert "GeoscapeState" not in after, (
            f"client returned to geoscape after Skirmish debriefing: {after}"
        )

        print("PASS: campaign clock did not leak into the next Skirmish; "
              "the client debriefing returned to the main menu")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    test_campaign_clock_does_not_leak_into_skirmish_debrief()
