"""PvP gamemode selection and lobby team-display correctness.

Validates:
  1. Default lobby: both rows show "XCOM", gamemode 1 (PVE).
  2. Client -> Alien: gamemode 2. Roster is sorted alphabetically
     ("ClientPlayer" < "HostPlayer"), so teams = [Alien, XCOM].
  3. Host -> Alien (from state 2): gamemode 4 (both Alien).
     teams = [Alien, Alien].
  4. Client -> XCOM (from state 4): gamemode 3 (host plays aliens).
     teams = [XCOM, Alien].
  5. Host -> XCOM (from state 3): back to gamemode 1, [XCOM, XCOM].

All validations use lobby_state (the player-facing lobby UI), specifically
the `playerTeams` array that mirrors what the player sees on the roster
team column. Rows are resolved dynamically via `row_for()` so the test
works regardless of sort order.

Run:  python tools/coop_test/test_pvp_skirmish_gamemode_selection.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "47990"


def _lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def _assert_teams(fails, tag, host_ls, client_ls, expect_host, expect_client):
    ht = host_ls.get("playerTeams")
    ct = client_ls.get("playerTeams")
    print(f"    host   sees teams: {ht}")
    print(f"    client sees teams: {ct}")
    if ht != expect_host:
        _fail(fails, f"{tag} host sees {ht}, expected {expect_host}")
    if ct != expect_client:
        _fail(fails, f"{tag} client sees {ct}, expected {expect_client}")
    if ht == expect_host and ct == expect_client:
        team_desc = ', '.join(f"{n}={t}" for n, t in
                              zip(host_ls.get("players", []), ht))
        print(f"PASS {tag}: both machines agree ({team_desc})")


def main():
    fails = []
    host = GameClient("host", 48890, make_user_dir("pvp_lobby_host"))
    client = GameClient("client", 48891, make_user_dir("pvp_lobby_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()

        gamemode, host_ls, client_ls = \
            PVP.start_pvp_skirmish_lobby(host, client, PORT, alien_player="client")

        # ---- 1. gamemode 2 (client on Alien team) --------------------------
        if gamemode != 2:
            _fail(fails, f"expected gamemode 2, got {gamemode}")
        else:
            print(f"PASS gamemode: {gamemode} (client plays aliens)")
        # Roster sorted by name: [client, host].
        # Client=Alien (row 0), Host=XCOM (row 1) -> [Alien, XCOM]
        _assert_teams(fails, "gamemode 2", host_ls, client_ls,
                      ["Alien", "XCOM"], ["Alien", "XCOM"])

        # ---- 2. both on Alien -> gamemode 4 --------------------------------
        host_row = PVP.row_for(host, "HostPlayer")
        r = host.ok({"cmd": "lobby_set_team", "row": host_row, "team": "Alien"})
        gm4 = r["gamemode"]
        if gm4 != 4:
            _fail(fails, f"expected gamemode 4 (both Alien), got {gm4}")
        else:
            print(f"PASS gamemode: {gm4} (both play aliens, PVE2)")
        time.sleep(1)

        hl4 = _lobby(host)
        cl4 = _lobby(client)
        _assert_teams(fails, "gamemode 4", hl4, cl4,
                      ["Alien", "Alien"], ["Alien", "Alien"])

        # ---- 3. client back to XCOM -> gamemode 3 (host plays aliens) ------
        client_row = PVP.row_for(host, "ClientPlayer")
        r = host.ok({"cmd": "lobby_set_team", "row": client_row, "team": "XCOM"})
        gm3 = r["gamemode"]
        if gm3 != 3:
            _fail(fails, f"expected gamemode 3 after reverting client, got {gm3}")
        else:
            print(f"PASS gamemode: {gm3} (host plays aliens, PVP2)")
        time.sleep(1)

        hl3 = _lobby(host)
        cl3 = _lobby(client)
        _assert_teams(fails, "gamemode 3", hl3, cl3,
                      ["XCOM", "Alien"], ["XCOM", "Alien"])

        # ---- 4. host back to XCOM -> gamemode 1 (PVE) ----------------------
        host_row = PVP.row_for(host, "HostPlayer")
        r = host.ok({"cmd": "lobby_set_team", "row": host_row, "team": "XCOM"})
        gm1 = r["gamemode"]
        if gm1 != 1:
            _fail(fails, f"expected gamemode 1 after reverting host, got {gm1}")
        else:
            print(f"PASS gamemode: {gm1} (both XCOM, PVE)")
        time.sleep(1)

        hl1 = _lobby(host)
        cl1 = _lobby(client)
        _assert_teams(fails, "gamemode 1", hl1, cl1,
                      ["XCOM", "XCOM"], ["XCOM", "XCOM"])

    except Exception as e:
        print(f"[ERROR] {e}")
        fails.append(str(e))
    finally:
        host.shutdown()
        client.shutdown()

    print("\n==== PvP gamemode selection summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  skirmish lobby gamemode selection and team labels are correct")
    sys.exit(0)


if __name__ == "__main__":
    main()
