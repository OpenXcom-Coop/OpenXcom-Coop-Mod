"""Reproduce a pending Space Marines finale after another faction wins."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import geo
import session
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


SOURCE = r"C:\Users\arita\Documents\OpenXcom\40k\campaign_continue.sav"
SAVE = "separate_pending_finale_fixture.sav"


def main():
    host_dir = make_user_dir("sep_pending_finale_host", saves=(SOURCE,),
                             mods=(MOD_40K, MOD_ROSIGMA))
    os.makedirs(os.path.join(host_dir, "40k"), exist_ok=True)
    os.replace(os.path.join(host_dir, "xcom1", os.path.basename(SOURCE)),
               os.path.join(host_dir, "40k", SAVE))
    host = GameClient("host", 49640, host_dir)
    client = GameClient("client", 49641, make_user_dir(
        "sep_pending_finale_client", mods=(MOD_40K, MOD_ROSIGMA)))
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()
        host.ok({"cmd": "load_save_menu", "file": SAVE})
        host.wait_for("host resume window", lambda: session._has_state(host, "HostMenu"),
                      timeout=120)
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": "48940",
                 "player": "HostPlayer"})
        host.wait_for("host lobby", lambda: session._has_state(host, "LobbyMenu"))
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": "48940",
                   "player": "ClientPlayer"})
        client.wait_for("client lobby", lambda: session._has_state(client, "LobbyMenu"))
        time.sleep(3)
        session.resume_campaign_via_button(host, "ClientPlayer")
        host.wait_for("world ack",
                      lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
                      timeout=120)
        host.ok({"cmd": "coop_dialog_back"})
        client.wait_for("client geoscape",
                        lambda: session._has_state(client, "GeoscapeState") or None,
                        timeout=120)

        def finale(machine):
            state = machine.cmd({"cmd": "geo_state"})
            for site in state.get("missionSites", []):
                if site.get("deployment") == "STR_MARS_CYDONIA_LANDING":
                    return site
            faction_state = machine.cmd({"cmd": "separate_faction_mission_state"})
            for base in faction_state.get("alienBases", []):
                if base.get("type") == "STR_MARS_CYDONIA_LANDING":
                    return base
            return None

        result = geo.skip_ingame_time(host, client, 60 * 24 * 28, speed_idx=5,
            interest=lambda machine: finale(machine), dismiss=True,
            real_timeout=180, stuck_timeout=None)
        profile = host.ok({"cmd": "separate_profile_state"})
        faction_state = host.ok({"cmd": "separate_faction_mission_state"})
        host.ok({"cmd": "save_game", "file": "separate_pending_finale_after_month.sav"})
        print({"advance": result, "profile": profile,
               "time": host.ok({"cmd": "geo_state"}).get("time"),
               "missionSites": host.ok({"cmd": "geo_state"}).get("missionSites"),
               "alienBases": faction_state.get("alienBases")})
        assert result["hit"], "Space Marines finale did not spawn"
        finale_target = result["hit"][1]
        assert finale_target.get("ownerPlayerName") == "HostPlayer", finale_target
        geo.skip_ingame_time(host, client, 35, speed_idx=5, dismiss=True,
                             real_timeout=30, stuck_timeout=None)
        for machine in (host, client):
            state = machine.ok({"cmd": "separate_faction_mission_state"})
            visible = next((base for base in state.get("alienBases", [])
                            if base.get("type") == "STR_MARS_CYDONIA_LANDING"), None)
            assert visible and visible.get("discovered"), state.get("alienBases")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
