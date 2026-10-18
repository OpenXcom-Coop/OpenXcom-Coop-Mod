"""Separate Campaign lobby rows must use the locked save roster.

Covers the live/new-mission side of the regression. The host and client open
the in-game lobby independently after a fresh Separate campaign starts. Both
must see HostPlayer exactly once in seat 0 and ClientPlayer exactly once in
seat 1. Saved-geoscape and saved-battle resume lobbies are checked centrally by
session.resume_campaign() and session.resume_campaign_battle().

Run: python -u tools/coop_test/test_separate_campaign_ingame_lobby_roster.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import session


def check_lobby(machine, who):
    machine.ok({"cmd": "open_coop_menu"})
    machine.wait_for(
        f"{who} in-game lobby",
        lambda: (machine.cmd({"cmd": "lobby_state"})
                 if machine.cmd({"cmd": "lobby_state"}).get("lobbyOpen") else None),
        timeout=30,
    )
    state = machine.ok({"cmd": "lobby_state"})
    assert state["hostRowName"].strip() == "HostPlayer", state
    assert state["clientRowName"].strip() == "ClientPlayer", state
    assert sorted(name.strip() for name in state["players"]) == \
        ["ClientPlayer", "HostPlayer"], state
    machine.ok({"cmd": "lobby_action"})
    machine.wait_for(
        f"{who} returned to geoscape",
        lambda: (not session._has_state(machine, "LobbyMenu")) or None,
        timeout=30,
    )


def main():
    host = GameClient("host", 48970, make_user_dir("separate_lobby_roster_host"))
    client = GameClient("client", 48971, make_user_dir("separate_lobby_roster_client"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.new_campaign(host, client, port="47970", campaign_mode="coop")
        check_lobby(host, "host")
        check_lobby(client, "client")
        print("PASS Separate in-game lobby: both machines show the locked roster once")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
