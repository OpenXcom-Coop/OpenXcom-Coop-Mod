"""Different-faction Separate lobbies show each player's faction in the roster."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import session
import shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)


def lobby_rows(machine, who):
    machine.ok({"cmd": "open_coop_menu"})
    state = machine.wait_for(
        f"{who} faction lobby",
        lambda: (lambda value: value if value.get("lobbyOpen") else None)(
            machine.cmd({"cmd": "lobby_state"})),
        timeout=30,
    )
    rows = (state["hostRowName"].strip(), state["clientRowName"].strip())
    machine.ok({"cmd": "lobby_action"})
    machine.wait_for(
        f"{who} returned to geoscape",
        lambda: (not session._has_state(machine, "LobbyMenu")) or None,
        timeout=30,
    )
    return rows


def main():
    require_mods()
    js = shared_fixture.bring_up(
        "sep_rosigma_lobby_factions", (49610, 49611, 48910),
        mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    try:
        host_rows = lobby_rows(js.host, "host")
        client_rows = lobby_rows(js.client, "client")
        assert host_rows == client_rows, (host_rows, client_rows)
        assert host_rows[0].startswith("HostPlayer (") and host_rows[0].endswith(")"), host_rows
        assert host_rows[1].startswith("ClientPlayer (") and host_rows[1].endswith(")"), host_rows
        assert "difficulty:" not in " ".join(host_rows), host_rows
        assert host_rows[0].split("(", 1)[1] != host_rows[1].split("(", 1)[1], host_rows
        print("PASS different-faction Separate lobby shows matching faction labels")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
