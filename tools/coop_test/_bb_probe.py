"""Probe: trace exactly which machine gets BuildNewBaseState in PvP campaign.

Mirrors the real manual flow: New Game -> SEPARATE -> lobby -> team toggle
-> START CAMPAIGN -> observe base placement on both machines.
"""

import os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

PORT = "47996"

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]

def _has(gc, name):
    return any(name in s for s in _states(gc))

def probe(alientag, alien_player, expect_gamemode):
    print(f"\n=== probe {alientag}: {alien_player} plays aliens, expect gm={expect_gamemode} ===")
    host = GameClient("host", 48990, make_user_dir(f"probe_{alientag}_host"))
    client = GameClient("client", 48991, make_user_dir(f"probe_{alientag}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # Step 1: New Game -> SEPARATE
        host.ok({"cmd": "open_new_game", "mode": "coop"})
        host.wait_for("diff", lambda: _has(host, "NewGameState"))
        host.ok({"cmd": "newgame_ok"})
        host.wait_for("hostw", lambda: _has(host, "HostMenu"))
        host.ok({"cmd": "host_tcp", "server":"TestSrv","port":PORT,"player":"HostPlayer"})
        host.wait_for("lobby", lambda: _has(host, "LobbyMenu"))

        # Step 2: Client joins
        client.ok({"cmd":"join_tcp","ip":"127.0.0.1","port":PORT,"player":"ClientPlayer"})
        client.wait_for("lobby", lambda: _has(client, "LobbyMenu"), timeout=120)
        for gc in (host, client):
            gc.wait_for("popup", lambda g=gc: _has(g, "Profile"))
            gc.ok({"cmd":"profile_ok"})
        host.wait_for("eligible", lambda: host.cmd({"cmd":"lobby_state"}).get("startEligible") or None)

        # Step 3: Set teams
        ls = host.cmd({"cmd":"lobby_state"})
        names = ls.get("players", [])
        target_name = "ClientPlayer" if alien_player == "client" else "HostPlayer"
        for i, n in enumerate(names):
            if target_name in n:
                r = host.ok({"cmd":"lobby_set_team","row":i,"team":"Alien"})
                print(f"  lobby_set_team(row={i}, name={n}) -> gamemode={r['gamemode']}")
                break
        time.sleep(1)

        # Verify lobby state on BOTH machines
        for gc, tag in ((host,"host"),(client,"client")):
            ls = gc.cmd({"cmd":"lobby_state"})
            print(f"  {tag} lobby: teams={ls.get('playerTeams')} names={ls.get('players')}")

        # Step 4: START CAMPAIGN
        print("  pressing START CAMPAIGN...")
        session.start_campaign_via_button(host)

        # Step 5: Poll state for 10 seconds on both machines
        print("  polling state after start:")
        for t in range(10):
            time.sleep(1)
            for gc, tag in ((host,"host"),(client,"client")):
                st = _states(gc)
                has_bb = "BuildNewBaseState" in st
                has_hold = "CoopState" in st
                has_geo = "GeoscapeState" in st
                flags = []
                if has_bb: flags.append("BASE")
                if has_hold: flags.append("HOLD")
                if has_geo: flags.append("GEO")
                if t == 0 or t == 4 or t == 9:
                    print(f"    t={t}: {tag:6} {flags} top={st[-1][:30]}")
    finally:
        host.shutdown()
        client.shutdown()

probe("gm2", "client", 2)
probe("gm3", "host", 3)
print("\ndone")
