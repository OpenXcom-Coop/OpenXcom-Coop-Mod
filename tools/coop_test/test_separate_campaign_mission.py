"""Separate Campaign: owner-only mission prompt and crash-free YES entry."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import session
import separate_campaign_fixture as fixture
import test_parallel_intents as parallel_intents
import test_parallel_sharedturn as parallel_sharedturn


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has_state(gc, name):
    return any(name in state for state in states(gc))


def top_state(gc):
    return states(gc)[-1].split("::")[-1]


def drain_to_tactical(host, client, rounds=12):
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            if top_state(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        if not moved:
            return
        time.sleep(1.0)


def main(parallel=False):
    tag = "sep_parallel_mission" if parallel else "sep_mission"
    ports = (48982, 48983, 48282) if parallel else (48972, 48973, 48272)
    battle_options = {
        "EnableCoopParallelTurns": parallel,
        "battleXcomSpeed": 2,
        "battleAlienSpeed": 2,
        "skipNextTurnScreen": parallel,
    }
    js = fixture.bring_up(
        tag, ports,
        host_options=battle_options,
        client_options={"EnableCoopParallelTurns": False,
                        "battleXcomSpeed": 2, "battleAlienSpeed": 2})
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)

        # Separate is one authoritative world. Player-local starting rosters may
        # originally use the same ids, but they must be upgraded before any
        # Soldier id is inherited by a BattleUnit.
        for gc, label in ((host, "host"), (client, "client")):
            roster = gc.ok({"cmd": "get_soldiers"})["bases"]
            ids = [s["id"] for b in roster for s in b["soldiers"]]
            assert len(ids) == len(set(ids)), \
                f"{label} Separate world still contains duplicate soldier ids: {ids}"
        geo.slow_clock(host, client)
        world = fixture.geo(host)
        client_base = next(b for b in world["bases"] if b["name"] == "ClientBase")
        client_base_view = next(b for b in fixture.geo(client)["bases"]
                                if b["name"] == "ClientBase")
        assert not client_base_view["coopBase"], client_base_view
        craft = next(c for c in client_base["crafts"] if c["type"] == "STR_SKYRANGER")

        # A real Separate craft may carry both players' soldiers.  Preserve the
        # deployment rule the UI relies on (host crew occupies the outer craft
        # positions and host authority starts the battle), and prove that this
        # does not block either seat from moving on the first parallel XCOM side.
        if parallel:
            aboard = [s for s in fixture.soldiers_at(host, "ClientBase")
                      if s["craftId"] == craft["id"]]
            assert len(aboard) >= 2, aboard
            # Shared's roster order alternates ownership. Stamp the Separate
            # fixture the same way so the runtime assertion proves the normal
            # craft deployment maps host/client to its left/right sequence.
            for index, member in enumerate(aboard):
                owner = index % 2
                for gc in (host, client):
                    gc.ok({"cmd": "set_soldier_owner", "base": "ClientBase",
                           "soldier_id": member["id"], "owner": owner})

        # Send the CLIENT-owned craft to a nearby real mission site.
        site = host.ok({"cmd": "spawn_mission_site",
                        "mission": "STR_ALIEN_TERROR",
                        "deployment": "STR_TERROR_MISSION",
                        "lon": client_base["lon"] + 0.35,
                        "lat": client_base["lat"] + 0.10,
                        "race": "STR_SECTOID", "hours": 240})
        site_id = site["site_id"]
        client.wait_for(
            "mission site replicated",
            lambda: any(s["id"] == site_id
                        for s in fixture.geo(client)["missionSites"]) or None,
            timeout=30, interval=0.3)

        # Landing can be suppressed for an empty transport by the normal OXCE
        # option. Put one real item aboard through the Separate command lane.
        host.ok({"cmd": "shared_reset_stats"})
        equipped = client.ok({"cmd": "craft_equip", "base": "ClientBase",
                              "craft_id": craft["id"],
                              "item": "STR_RIFLE", "count": 1})
        assert equipped["moved"], equipped
        host.wait_for(
            "craft equipment command applied",
            lambda: host.ok({"cmd": "shared_stats"})["okCount"] > 0 or None,
            timeout=30, interval=0.3)

        # The mission-entry regression begins with the host-authoritative craft
        # already en route. Craft-order routing has its own focused harness.
        client_forced = client.ok({"cmd": "craft_force", "base": "ClientBase",
                                   "craft_id": craft["id"], "craft_type": craft["type"],
                                   "status": "STR_OUT", "fuel": 999999,
                                   "lowFuel": False,
                                   "lon": client_base["lon"] + 0.35,
                                   "lat": client_base["lat"] + 0.10,
                                   "dest": f"site:{site_id}"})
        assert client_forced["status"] == "STR_OUT", client_forced
        assert client_forced["reached"] is True, client_forced
        host.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "shared_reset_stats"})
        forced = host.ok({"cmd": "craft_force", "base": "ClientBase",
                          "craft_id": craft["id"], "craft_type": craft["type"],
                          "status": "STR_OUT", "fuel": 999999, "lowFuel": False,
                          "lon": client_base["lon"] + 0.35,
                          "lat": client_base["lat"] + 0.10,
                          "dest": f"site:{site_id}"})
        assert forced["status"] == "STR_OUT", forced
        assert forced["units"] > 0, forced
        assert forced["items"] > 0, forced
        assert forced["reached"] is True, forced

        # Treat ConfirmLandingState as the interesting popup so the time helper
        # leaves it open instead of auto-answering it.
        def landing_started(gc):
            if has_state(gc, "ConfirmLandingState"):
                return "popup"
            if gc is host and gc.ok({"cmd": "shared_landing_state"})["pending"]:
                return "pending"
            return None

        arrival = geo.skip_realtime(
            host, client, 90, speed_idx=2,
            interest=landing_started, stuck_timeout=None)
        assert arrival["hit"], arrival
        host_stats = host.ok({"cmd": "shared_stats"})
        client_stats = client.ok({"cmd": "shared_stats"})
        assert host_stats["failCount"] == 0, host_stats
        assert client_stats["applyCount"] > 0, {
            "host": host_stats, "client": client_stats, "arrival": arrival}
        client.wait_for(
            "client owner received landing prompt",
            lambda: has_state(client, "ConfirmLandingState") or None,
            timeout=15, interval=0.3)
        assert has_state(client, "ConfirmLandingState"), states(client)
        assert not has_state(host, "ConfirmLandingState"), states(host)
        assert host.ok({"cmd": "shared_landing_state"})["pending"] is True

        # This is the crash regression: the client-owned prompt answers YES,
        # while the host alone generates and distributes the battle.
        client.ok({"cmd": "confirm_landing"})
        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(
                f"{label} entered Separate battle",
                lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                timeout=180, interval=1.0)
        assert not host.ok({"cmd": "shared_landing_state"})["pending"]

		# The authoritative host must bind the battle to the requesting craft's
		# real base, not to the base the host happened to have selected.
        for gc, label in ((host, "host"), (client, "client")):
            bs = gc.ok({"cmd": "battle_state"})
            assert bs["battleOwnerPlayerName"] == "ClientPlayer", (label, bs)
            assert bs["selectedBase"] == "ClientBase", (label, bs)
        print("PASS Separate briefing context: client craft uses ClientBase")

        # Drive the real briefing -> inventory -> tactical path. The former test
        # stopped at inBattle=True and therefore missed a completely wedged map.
        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(f"{label} briefing",
                        lambda gc=gc: has_state(gc, "BriefingState") or None,
                        timeout=60, interval=0.5)
            gc.ok({"cmd": "close_briefing"})
        for gc, label in ((host, "host"), (client, "client")):
            gc.wait_for(f"{label} inventory",
                        lambda gc=gc: has_state(gc, "InventoryState") or None,
                        timeout=60, interval=0.5)
            gc.ok({"cmd": "battle_inventory", "action": "ok"})
        drain_to_tactical(host, client)

        hb, cb = host.ok({"cmd": "battle_state"}), client.ok({"cmd": "battle_state"})
        assert hb["host"] is True, hb
        assert cb["host"] is False, cb
        assert cb["battleInit"] is True, cb
        assert hb.get("parallelActive") is parallel, hb
        assert cb.get("parallelActive") is parallel, cb
        if parallel:
            deployed = [u for u in hb["units"] if u.get("faction") == 0
                        and not u.get("isOut") and u.get("isPlayerSoldier")]
            for seat, label in ((0, "host"), (1, "client")):
                assert any(u.get("faction") == 0 and not u.get("isOut")
                           and u.get("coop") == seat for u in hb["units"]), (
                               f"mixed Separate craft has no {label} soldier", hb)
            host_x = [u["x"] for u in deployed if u.get("coop") == 0]
            client_x = [u["x"] for u in deployed if u.get("coop") == 1]
            assert max(host_x) < min(client_x), (
                "Separate deployment must put every host soldier in the left "
                f"lane and every client soldier in the right lane: {deployed}")

        def client_controls_soldier():
            bs = client.ok({"cmd": "battle_state"})
            return any(u.get("selectable") and u.get("coop") == 1
                       for u in bs["units"])

        # Classic turns begin on the server-host side. A client-only squad puts
        # that side in spectator mode; ending it must hand control to the client
        # instead of wedging forever on NextTurnState.
        if not client_controls_soldier():
            print(f"Separate initial control: host turn={hb['coopTurn']} "
                  f"playerTurn={hb['playerTurn']}; client turn={cb['coopTurn']} "
                  f"playerTurn={cb['playerTurn']}")
            host.ok({"cmd": "battle_action", "action": "end_turn_button"})
            client.wait_for("host spectator turn hands control to client",
                            lambda: client_controls_soldier() or None,
                            timeout=60, interval=0.5)

        # Execute one real client-owned walk and require the authoritative host
		# and replica to settle on the same new tile (the reported symptom was
		# soldiers snapping/teleporting back while both machines acted as host).
        cb = client.ok({"cmd": "battle_state"})
        movers = [u for u in cb["units"] if u.get("selectable") and u.get("coop") == 1]
        moved = None
        errors = []
        for unit in movers:
            before = (unit["x"], unit["y"], unit["z"])
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                target = (before[0] + dx, before[1] + dy, before[2])
                command = "battle_intent" if parallel else "battle_action"
                result = client.cmd({"cmd": command, "action": "move",
                                     "unit": unit["id"], "x": target[0],
                                     "y": target[1], "z": target[2]})
                if result.get("ok"):
                    if parallel:
                        assert result.get("routed") is True, result
                    moved = (unit["id"], before)
                    break
                errors.append((unit["id"], target, result.get("error")))
            if moved:
                break
        assert moved is not None, f"no client soldier could take one step: {errors[:12]}"
        moved_id, before = moved

        def unit_pos(gc, uid):
            for unit in gc.ok({"cmd": "battle_state"})["units"]:
                if unit["id"] == uid:
                    return unit["x"], unit["y"], unit["z"]
            return None

        if parallel:
            client.wait_for(
                "client parallel intent finishes",
                lambda: (parallel_intents.parallel(client).get("pendingReqId") == 0) or None,
                timeout=60, interval=0.25)
            deny = parallel_intents.parallel(client).get("lastDenyWarning", "")
            assert not deny, (
                f"client-owned Separate soldier {moved_id} was denied: {deny}; "
                f"host units={host.ok({'cmd': 'battle_state'})['units']}; "
                f"client units={client.ok({'cmd': 'battle_state'})['units']}")
        client.wait_for("client walk completes",
                        lambda: (unit_pos(client, moved_id) != before) or None,
                        timeout=30, interval=0.25)
        host.wait_for("client walk reaches authoritative host",
                      lambda: (unit_pos(host, moved_id) == unit_pos(client, moved_id)) or None,
                      timeout=30, interval=0.25)
        assert unit_pos(host, moved_id) != before

        if parallel:
            # The client-requested mission must retain the exact useful mixed
            # deployment of a host-requested mission: host crew at the outer
            # craft positions and client crew behind them, with BOTH seats able
            # to begin leaving the craft during the first shared XCOM side.
            host_moved = None
            for unit in [u for u in host.ok({"cmd": "battle_state"})["units"]
                         if u.get("faction") == 0 and not u.get("isOut")
                         and u.get("coop") == 0]:
                probe = host.cmd({"cmd": "battle_intent", "action": "probe_step",
                                  "unit": unit["id"], "radius": 3, "max": 400})
                if not probe.get("steps"):
                    continue
                step = probe["steps"][-1]
                host_before = unit_pos(host, unit["id"])
                result = host.cmd({"cmd": "battle_intent", "action": "move",
                                   "unit": unit["id"], "x": step["x"],
                                   "y": step["y"], "z": step["z"]})
                if not result.get("ok"):
                    continue
                host.wait_for("host first-turn craft walk finishes",
                              lambda: parallel_intents.parallel(host).get("canAdmit") is True or None,
                              timeout=60, interval=0.25)
                if unit_pos(host, unit["id"]) != host_before:
                    host_moved = unit["id"]
                    break
            assert host_moved is not None, (
                "host could not move its outer-positioned soldier on the first "
                "parallel XCOM side")
            client.wait_for("host first-turn craft walk reaches client",
                            lambda: unit_pos(client, host_moved) == unit_pos(host, host_moved) or None,
                            timeout=45, interval=0.25)
            print("PASS Separate mixed craft: host and client both move their own "
                  "soldiers on the first parallel XCOM side")

        # Both ready presses must advance the side rather than leave NextTurnState
		# permanently waiting.
        start = host.ok({"cmd": "battle_state"})
        start_turn, start_side = start["turn"], start["side"]
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        if parallel:
            # Parallel mode closes the shared player side only after both seats
            # are ready.  Run the complete alien side: the reported regression
            # surfaced at the following sidestart, not merely on hand-off.
            host.ok({"cmd": "sync_capture", "on": True})
            client.ok({"cmd": "sync_capture", "on": True})
            returned_turn = parallel_sharedturn.cycle_side(host, client)
            assert returned_turn and returned_turn > start_turn, {
                "host": host.ok({"cmd": "battle_state"}),
                "client": client.ok({"cmd": "battle_state"})}
            host_sync = host.ok({"cmd": "parallel_state"}).get("syncCheck", {})
            client_sync = client.ok({"cmd": "parallel_state"}).get("syncCheck", {})
            assert not host_sync.get("fieldDiffs"), host_sync.get("fieldDiffs")
            assert not client_sync.get("fieldDiffs"), client_sync.get("fieldDiffs")
            session.assert_battle_synced(
                host, client, "Separate parallel alien-side return")
            session.assert_sync_clean(
                host, client, "Separate parallel alien-side return")
            print("PASS Separate parallel boundary: alien side returns without desync")
        else:
            host.wait_for(
                "Separate end turn leaves the player side",
                lambda: ((lambda bs: bs.get("side") != start_side
                         or bs.get("turn", start_turn) > start_turn)(
                             host.ok({"cmd": "battle_state"}))) or None,
                timeout=60, interval=0.5)
            client.wait_for(
                "client observes the same side transition",
                lambda: ((lambda bs: bs.get("side") != start_side
                         or bs.get("turn", start_turn) > start_turn)(
                             client.ok({"cmd": "battle_state"}))) or None,
                timeout=60, interval=0.5)
        print("PASS Separate tactical control: client walk converges and end turn advances")
        print("PASS Separate mission: owner-only prompt, correct base, and playable battle")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
