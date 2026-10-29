"""The host negotiates every multiplayer option and the client UI mirrors it."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


HOST_OPTIONS = {
    "EnableHostOnlyTimeSpeed": True,
    "EnableResearchSync": True,
    "UnbalancedCraftSoldiersLimit": True,
    "EnableReactionFirePvp": False,
    "EnableOtherPlayerFootsteps": False,
    "EnableXcomEquipmentAliensPVP": False,
    "EnableCoopParallelTurns": True,
}

CLIENT_OPTIONS = {key: not value for key, value in HOST_OPTIONS.items()}


def main():
    js = fixture.bring_up(
        "multiplayer_options", (49370, 49371, 48670),
        host_options=HOST_OPTIONS, client_options=CLIENT_OPTIONS)
    try:
        host = js.host.ok({"cmd": "multiplayer_options_state"})
        client = js.client.ok({"cmd": "multiplayer_options_state"})

        expected = {
            "researchSync": True,
            "hostOnlyTimeSpeed": True,
            # Reaction-fire suppression is PvP-only; campaigns force it on.
            "reactionFirePvp": True,
            "otherPlayerFootsteps": False,
            "xcomEquipmentAliensPvp": False,
            "parallelTurns": True,
            "unbalancedCraftLimit": True,
        }
        assert host["runtime"] == expected, host
        assert client["runtime"] == expected, client
        assert client["configured"] == expected, client
        print("PASS host multiplayer options are negotiated and mirrored by the client UI")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
