"""Real ROSIGMA final missions through Geoscape -> Battlescape -> Geoscape."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo, session, shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)

def states(gc): return gc.cmd({"cmd": "get_state"})["states"]
def has(gc, name): return any(name in state for state in states(gc))
def top(gc): return states(gc)[-1].split("::")[-1]

def close_to_tactical(host, client):
    for gc in (host, client):
        gc.wait_for("ROSIGMA final briefing", lambda gc=gc: has(gc, "BriefingState") or None,
                    timeout=180, interval=.5)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        gc.wait_for("ROSIGMA final inventory", lambda gc=gc: has(gc, "InventoryState") or None,
                    timeout=120, interval=.5)
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(30):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)): return
        for gc in (client, host):
            if top(gc) != "BattlescapeState": gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(.5)
    raise AssertionError((states(host), states(client)))

def prepare_faction_force(host, client, owner, owner_seat, base_name, craft_type,
                          soldier_type):
    base = next(b for b in host.ok({"cmd": "geo_state"})["bases"] if b["name"] == base_name)
    matching = [craft for craft in base["crafts"] if craft["type"] == craft_type]
    if not matching:
        spawned = [gc.ok({"cmd": "spawn_craft", "base": base_name,
                          "type": craft_type, "weapon": "STR_NONE"})
                   for gc in (host, client)]
        craft_ids = {result["craft_id"] for result in spawned}
        assert len(craft_ids) == 1, f"different craft ids between peers: {spawned}"
        base = next(b for b in host.ok({"cmd": "geo_state"})["bases"]
                    if b["name"] == base_name)
        matching = [craft for craft in base["crafts"] if craft["type"] == craft_type]
    craft = matching[0]
    if craft.get("soldiers", 0) == 0:
        owner_gc = host if owner == "HostPlayer" else client
        roster = next(b["soldiers"] for b in owner_gc.ok({"cmd": "get_soldiers"})["bases"]
                      if b["name"] == base_name)
        if not roster:
            peer_ids = []
            for _ in range(4):
                created = [gc.ok({"cmd": "spawn_soldier", "base": base_name,
                                  "type": soldier_type, "owner": owner_seat})
                           for gc in (host, client)]
                ids = {result["soldier_id"] for result in created}
                assert len(ids) == 1, f"different soldier ids between peers: {created}"
                peer_ids.append(next(iter(ids)))
            roster = next(b["soldiers"] for b in owner_gc.ok({"cmd": "get_soldiers"})["bases"]
                          if b["name"] == base_name)
        assert roster, f"{base_name} has no soldiers for its ROSIGMA finale"
        for soldier in roster[:4]:
            for gc in (host, client):
                gc.ok({"cmd": "force_soldier_craft", "base": base_name,
                       "craft_id": craft["id"], "craft_type": craft["type"],
                       "soldier_id": soldier["id"]})
    return next(craft for craft in next(
        b for b in host.ok({"cmd": "geo_state"})["bases"]
        if b["name"] == base_name)["crafts"] if craft["type"] == craft_type)

def start_finale(host, client, owner, base_name, craft, mission, deployment):
    geo.slow_clock(host, client)
    base = next(b for b in host.ok({"cmd": "geo_state"})["bases"] if b["name"] == base_name)
    lon, lat = base["lon"] + .18, base["lat"] + .06
    site_id = host.ok({"cmd": "spawn_mission_site", "mission": mission,
        "deployment": deployment, "owner": owner, "lon": lon, "lat": lat,
        "race": "STR_CHAOS_FINAL_UNITED_HARD", "hours": 240})["site_id"]
    client.wait_for("ROSIGMA finale replicated", lambda: any(
        s["id"] == site_id for s in client.ok({"cmd": "geo_state"})["missionSites"]) or None,
        timeout=60, interval=.5)
    forced = []
    owner_gc = host if owner == "HostPlayer" else client
    other_gc = client if owner_gc is host else host
    # A client-owned craft must reach the target in its owner view before the
    # authoritative host processes that arrival (same ordering as the focused
    # Separate client-mission regression).
    for gc in (owner_gc, other_gc):
        forced.append(gc.ok({"cmd": "craft_force", "base": base_name,
            "craft_id": craft["id"], "craft_type": craft["type"],
            "status": "STR_OUT", "fuel": 999999, "lowFuel": False,
            "lon": lon, "lat": lat, "dest": f"site:{site_id}"}))
    assert all(result["reached"] for result in forced), forced
    assert all(result["units"] > 0 for result in forced), forced
    arrival = geo.skip_realtime(host, client, 90, speed_idx=2,
        interest=lambda gc: "landing" if has(owner_gc, "ConfirmLandingState") else None,
        stuck_timeout=None)
    if not has(owner_gc, "ConfirmLandingState"):
        raise AssertionError({"arrival": arrival, "forced": forced,
            "hostStates": states(host), "clientStates": states(client),
            "hostGeo": host.ok({"cmd": "geo_state"}),
            "clientGeo": client.ok({"cmd": "geo_state"})})
    owner_gc.ok({"cmd": "confirm_landing"})
    for gc in (host, client):
        try:
            gc.wait_for("real ROSIGMA final battle", lambda gc=gc: (lambda battle:
                battle if battle.get("inBattle") else None)(gc.ok({"cmd": "battle_state"})),
                timeout=240, interval=1)
        except TimeoutError as error:
            raise AssertionError({"peer": gc.name, "states": states(gc),
                "battle": gc.cmd({"cmd": "battle_state"}),
                "otherStates": states(client if gc is host else host),
                "otherBattle": (client if gc is host else host).cmd(
                    {"cmd": "battle_state"})}) from error
    close_to_tactical(host, client)
    battle = host.ok({"cmd": "battle_state"})
    assert battle["missionType"] == deployment, battle
    assert battle["battleOwnerPlayerName"] == owner, battle

def win_stages(host, client, expected_completed):
    mission_types = []
    for _ in range(8):
        deadline = time.time() + 120
        while time.time() < deadline:
            for gc in (host, client):
                if has(gc, "BriefingState"):
                    gc.ok({"cmd": "close_briefing"})
                if has(gc, "InventoryState"):
                    gc.ok({"cmd": "battle_inventory", "action": "ok"})
                if gc is host and top(gc) == "NextTurnState":
                    gc.cmd({"cmd": "close_nextturn"})
            if all(top(gc) == "BattlescapeState" for gc in (host, client)):
                break
            if len(host.ok({"cmd": "separate_profile_state"}).get(
                    "completedFactions", [])) >= expected_completed:
                return mission_types
            time.sleep(.25)
        if top(host) != "BattlescapeState":
            transition = host.wait_for("active ROSIGMA battle stage",
                lambda: ("result" if (has(host, "InfoboxState") or
                         has(host, "DebriefingState") or len(host.ok(
                             {"cmd": "separate_profile_state"}).get(
                                 "completedFactions", [])) >= expected_completed) else
                         "stage" if top(host) == "BattlescapeState" else None),
                timeout=120, interval=.25)
            if transition == "result": break
        battle = host.ok({"cmd": "battle_state"})
        if not battle.get("inBattle"): break
        mission_types.append(battle["missionType"])
        print(f"  finishing ROSIGMA stage {len(mission_types)}: {battle['missionType']}",
              flush=True)
        stable = 0
        deadline = time.time() + 30
        while time.time() < deadline and stable < 4:
            if top(host) == "BattlescapeState":
                stable += 1
            else:
                stable = 0
            time.sleep(.25)
        assert stable == 4, (battle["missionType"], states(host))
        result = None
        for _retry in range(10):
            result = host.cmd({"cmd": "battle_action", "action": "finish_victory"})
            if result.get("ok"):
                break
            if ("Access violation" not in result.get("error", "") and
                    result.get("error") != "not in battlescape"):
                raise AssertionError(result)
            time.sleep(.5)
        assert result and result.get("ok"), result
        time.sleep(1)
        if has(host, "DebriefingState") or has(host, "InfoboxState"): break
    try:
        host.wait_for("victory result", lambda: (has(host, "InfoboxState") or
                      has(host, "DebriefingState") or
                      not host.cmd({"cmd": "battle_state"}).get("inBattle")) or None,
                      timeout=120, interval=.5)
    except TimeoutError as error:
        raise AssertionError({"missions": mission_types, "states": states(host),
            "battle": host.cmd({"cmd": "battle_state"}),
            "profile": host.ok({"cmd": "separate_profile_state"})}) from error
    return mission_types

def return_to_geoscape(host, client):
    for _ in range(40):
        if all(session.has_state(gc, "GeoscapeState") and not has(gc, "DebriefingState")
               and not has(gc, "InfoboxState") for gc in (host, client)): return
        for gc in (host, client):
            if has(gc, "InfoboxState") or has(gc, "DebriefingState"):
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(.5)
    raise AssertionError((states(host), states(client)))

def continue_after_partial_finale(host, client, expected_owner):
    return_to_geoscape(host, client)
    for gc in (host, client):
        gc.wait_for("faction finale vote", lambda gc=gc: (lambda vote:
            vote if vote.get("active") and vote.get("action", "").startswith(
                "continue_faction_campaign|") else None)(
                    gc.ok({"cmd": "vote_state"})), timeout=30, interval=.25)
    host_vote = host.ok({"cmd": "vote_state"})
    assert host_vote["action"] == "continue_faction_campaign|" + expected_owner, host_vote
    vote_id = host_vote["id"]
    host.ok({"cmd": "vote_cast", "id": vote_id, "yes": True})
    client.ok({"cmd": "vote_cast", "id": vote_id, "yes": True})
    for gc in (host, client):
        result = gc.wait_for("continue vote passed", lambda gc=gc: (lambda vote:
            vote if vote.get("finished") else None)(gc.ok({"cmd": "vote_state"})),
            timeout=30, interval=.25)
        assert result["passed"], result
        gc.ok({"cmd": "vote_close"})

def main():
    require_mods()
    js = shared_fixture.bring_up("sep_rosigma_real_faction_finales",
        (49510, 49511, 48810), mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=0, client_difficulty=3, transport="tcp")
    host, client = js.host, js.client
    try:
        marine_craft = prepare_faction_force(host, client, "HostPlayer", 0,
            "HostBase", "STR_CHAPTERARMY", "STR_PRIMARISLV1")
        adeptas_craft = prepare_faction_force(host, client, "ClientPlayer", 1,
            "ClientBase", "STR_LANDRAIDER", "STR_CANONESS")
        start_finale(host, client, "HostPlayer", "HostBase", marine_craft,
                     "STR_FINAL_MISSION_MARINES", "STR_MARS_CYDONIA_LANDING")
        marine_stages = win_stages(host, client, 1)
        assert has(host, "DebriefingState"), states(host)
        continue_after_partial_finale(host, client, "HostPlayer")
        partial = host.ok({"cmd": "separate_profile_state"})
        assert partial["completedFactions"] == ["difficulty:0"], partial
        assert partial["pendingFactionRechecks"] == ["ClientPlayer"], partial
        start_finale(host, client, "ClientPlayer", "ClientBase", adeptas_craft,
                     "STR_FINAL_MISSION_ADEPTAS", "STR_MARS_CYDONIA_LANDING_ADEPTAS")
        adeptas_stages = win_stages(host, client, 2)
        final = host.ok({"cmd": "separate_profile_state"})
        assert final["completedFactions"] == ["difficulty:0", "difficulty:3"], final
        for gc in (host, client):
            gc.wait_for("campaign victory statistics",
                lambda gc=gc: has(gc, "StatisticsState") or None,
                timeout=60, interval=.25)
        host_ending = host.ok({"cmd": "ending_state"})
        client_ending = client.ok({"cmd": "ending_state"})
        assert host_ending["endingCutscene"], host_ending
        assert client_ending["endingCutscene"] == host_ending["endingCutscene"], \
            (host_ending, client_ending)
        assert host_ending["endingFaction"], host_ending
        assert client_ending["endingFaction"], client_ending
        assert host_ending["endingFaction"] != client_ending["endingFaction"], \
            (host_ending, client_ending)
        print("PASS real ROSIGMA finales through Battlescape and Geoscape: "
              f"Marines={marine_stages}, Adeptas={adeptas_stages}")
    finally: js.shutdown()

if __name__ == "__main__": main()
