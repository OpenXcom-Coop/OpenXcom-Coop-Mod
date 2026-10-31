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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import pvp_fixture as PVP
import session
import test_battle_end_rules as BER


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

        # The PvP gm2 skirmish is test_battle_end_rules.boot_pvp's body after its spawn / connect
        # lines, started from the main menu both machines reached; then BER.stage_pvp_elimination (the
        # host kills the client's only alien) and BER.end_pvp_elimination (the host's END TURN,
        # its NextTurnState closed).
        host.ok({"cmd": "set_seed", "seed": BER.SEED_MAP})
        BER.raw.skirmish_host(host, SKIRMISH_PORT)
        BER.raw.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": SKIRMISH_PORT,
                   "player": BER.raw.CLIENT_PLAYER})
        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"})
        client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: BER.raw.lobby(host).get("buttonVisible") or None)
        r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, BER.raw.CLIENT_PLAYER),
                     "team": "Alien"})
        assert r.get("gamemode") == BER.GAMEMODE_PVP, (
            f"lobby_set_team Alien answered gamemode {r.get('gamemode')} (want {BER.GAMEMODE_PVP})")
        time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative's boot phase)
        BER.drive_to_gm2_battlescape(host, client)
        hs, cs = BER.battle_state(host), BER.battle_state(client)
        assert hs.get("coopGamemode") == BER.GAMEMODE_PVP and cs.get("coopGamemode") == BER.GAMEMODE_PVP, (
            f"coopGamemode host={hs.get('coopGamemode')} client={cs.get('coopGamemode')} "
            f"(want {BER.GAMEMODE_PVP})")
        assert hs.get("mapFingerprint") == BER.MAP_FP and cs.get("mapFingerprint") == BER.MAP_FP, (
            f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
            f"baked MAP_FP={BER.MAP_FP!r} (STR_SMALL_SCOUT, SEED_MAP {BER.SEED_MAP})")
        ha, ca = hs.get("authority") or {}, cs.get("authority") or {}
        assert (ha.get("localSeat"), ha.get("hostSim"), ca.get("localSeat"), ca.get("hostSim")) == (
            0, True, 1, False), (
            f"authority host={ha} client={ca} (want host seat 0 hostSim, client seat 1 not hostSim)")
        a = session.units_by_id(hs).get(BER.A_ID) or {}
        assert (a.get("faction"), a.get("coop"), a.get("isOut")) == (BER.FACTION_HOSTILE, 1, False), (
            f"alien {BER.A_ID} at bring-up: faction {a.get('faction')} coop {a.get('coop')} "
            f"isOut {a.get('isOut')} (want a live FACTION_HOSTILE unit of seat 1)")
        pinned = BER.pin_ai_neutral(host, client, tag="campaign_then_skirmish_gm2")   # 0 is legal in gm2
        session.wait_host_idle(host, client, timeout=30)
        BER.assert_hash_clean(host, client, full=True, what="gm2 bring-up")
        print(f"gm2 skirmish boot ok: mapFingerprint {hs.get('mapFingerprint')}, "
              f"pinned {pinned}, authority host={ha} client={ca}", flush=True)
        pre, ending = [], []
        staging = BER.stage_pvp_elimination(host, client, pre)
        assert not pre, f"staging (BER.stage_pvp_elimination) failed: {pre} (staging={staging})"
        closed = BER.end_pvp_elimination(host, client, ending)
        assert not ending, f"ending (BER.end_pvp_elimination) failed: {ending} (ending={closed})"

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
