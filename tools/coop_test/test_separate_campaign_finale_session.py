"""A pending different-faction finale survives a rejoin and a reload, and never
leaks into a later session (PR #213 review F11).

A partial faction victory queues a continue/end vote that opens once both
players are back on the Geoscape. The pending owner used to live only in the
process: a client that dropped before the vote never learned of it again, a
reload forgot it, and the main menu did not clear it.

Flow (stock xcom1; the two players are given different factions directly):
  1. Separate campaign up; the client sits in Basescape so the vote cannot
     open yet; the host queues the finale for HostPlayer.
  2. The host saves: the pending owner is in the save file.
  3. The client process dies and a new one rejoins. Once both are back on the
     Geoscape the vote opens.
  4. The host returns to the main menu: no finale state survives it.
  5. Loading the save brings the pending owner back from the file.

Run:  py -3 tools/coop_test/test_separate_campaign_finale_session.py
Exit 0 = pass.
"""

import os
import sys
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

PORT = "52200"
SAVE = "finale_pending.sav"


def finale(gc):
    return gc.ok({"cmd": "get_coop"}).get("factionFinale", {})


def top_is_geoscape(gc):
    st = session.states(gc)
    return bool(st) and "GeoscapeState" in st[-1]


def main():
    host_dir = make_user_dir("sep_finale_host")
    host = GameClient("host", 52900, host_dir)
    client = GameClient("client", 52901, make_user_dir("sep_finale_client"))
    fails = []
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.new_campaign(host, client, port=PORT)

        for player, faction in (("HostPlayer", "faction:A"), ("ClientPlayer", "faction:B")):
            host.ok({"cmd": "separate_profile_set", "player": player, "faction": faction})

        # keep the client off the Geoscape so the vote cannot open yet
        client.ok({"cmd": "click_bases"})
        client.wait_for("client in Basescape", lambda: (
            client.cmd({"cmd": "basescape_menu_state"}).get("base") or None),
            timeout=20, interval=0.25)

        queued = host.ok({"cmd": "faction_finale_queue", "owner": "HostPlayer"})
        print(f"host queued: {queued.get('factionFinale')}")
        assert queued["factionFinale"]["owner"] == "HostPlayer", queued
        client.wait_for("client holds the pending finale",
                        lambda: finale(client).get("owner") == "HostPlayer" or None,
                        timeout=20, interval=0.25)
        time.sleep(2.0)
        assert not host.ok({"cmd": "vote_state"}).get("active"), \
            "the finale vote opened while the client was not on the Geoscape"
        print("PASS queued: both machines hold the pending finale, no vote yet")

        # ---- persisted in the host save ------------------------------------
        host.ok({"cmd": "save_game", "file": SAVE})
        with open(os.path.join(host_dir, "xcom1", SAVE), encoding="utf-8") as f:
            body = list(yaml.safe_load_all(f.read()))[1]
        saved_owner = body.get("separateCampaign", {}).get("pendingFactionFinaleOwner")
        print(f"saved pendingFactionFinaleOwner={saved_owner!r}")
        if saved_owner != "HostPlayer":
            fails.append("the pending finale is not in the host save; a reload forgets the vote")
            print("FAIL " + fails[-1])
        else:
            print("PASS persisted: the host save carries the pending finale owner")

        # ---- the client drops and a new process rejoins -----------------------
        client.proc.kill()
        client.proc.wait(timeout=10)
        host.wait_for("host freeze dialog",
                      lambda: ("CoopState" in session.states(host)[-1]) or None,
                      timeout=60)
        client = GameClient("client", 52902, make_user_dir("sep_finale_client2"))
        client.spawn(); client.connect()
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
                   "player": "ClientPlayer"})
        # The rejoined player closes the "joined" popup like a player would: the
        # world download dialog under it asks the host for the world only once
        # it reaches the top of the stack (CoopState::init).
        client.wait_for("client join popup", lambda: session.has_state(client, "Profile"),
                        timeout=60, interval=0.25)
        client.ok({"cmd": "profile_ok"})
        host.wait_for("rejoined client world ack",
                      lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
                      timeout=120)
        if session.has_state(host, "Profile"):
            host.ok({"cmd": "profile_ok"})
            time.sleep(0.5)
        host.ok({"cmd": "coop_dialog_back"})
        client.wait_for("client back on the Geoscape", lambda: top_is_geoscape(client) or None,
                        timeout=120)
        print(f"rejoined client finale: {finale(client)}")
        print(f"host finale: {finale(host)}")
        try:
            vote = host.wait_for(
                "finale vote after the rejoin",
                lambda: (lambda v: v if v.get("active")
                         and v.get("action", "").startswith("continue_faction_campaign|")
                         else None)(host.ok({"cmd": "vote_state"})),
                timeout=45, interval=0.5)
        except TimeoutError:
            vote = None
            fails.append("the finale vote never opened after the client rejoined: "
                         f"host={finale(host)} client={finale(client)}")
            print("FAIL " + fails[-1])
        if vote:
            print(f"PASS rejoin: the finale vote opened ({vote.get('action')})")

        # ---- nothing survives the main menu --------------------------------
        host.ok({"cmd": "disconnect_to_menu"})
        host.wait_for("host main menu",
                      lambda: ("MainMenuState" in session.states(host)[-1]) or None,
                      timeout=60, interval=0.25)
        stale = finale(host)
        print(f"host finale at the main menu: {stale}")
        if stale.get("owner"):
            fails.append(f"the pending finale survived the main menu into the next session: {stale}")
            print("FAIL " + fails[-1])
        else:
            print("PASS teardown: the main menu clears the pending finale")

        # ---- a reload brings it back from the file ------------------------
        host.ok({"cmd": "load_save_menu", "file": SAVE})
        host.wait_for("host window (resume)", lambda: session.has_state(host, "HostMenu"),
                      timeout=60)
        loaded = finale(host)
        print(f"host finale after load: {loaded}")
        if loaded.get("savedOwner") != "HostPlayer":
            fails.append(f"the loaded save lost the pending finale: {loaded}")
            print("FAIL " + fails[-1])
        else:
            print("PASS reload: the loaded save carries the pending finale")
        assert not fails, fails
        print("ALL FINALE SESSION CHECKS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
