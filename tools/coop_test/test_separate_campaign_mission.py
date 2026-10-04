"""Separate Campaign: owner-only mission prompt and crash-free YES entry."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


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


def main():
    js = fixture.bring_up("sep_mission", (48972, 48973, 48272))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        geo.slow_clock(host, client)
        world = fixture.geo(host)
        client_base = next(b for b in world["bases"] if b["name"] == "ClientBase")
        client_base_view = next(b for b in fixture.geo(client)["bases"]
                                if b["name"] == "ClientBase")
        assert not client_base_view["coopBase"], client_base_view
        craft = next(c for c in client_base["crafts"] if c["type"] == "STR_SKYRANGER")

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
                result = client.cmd({"cmd": "battle_action", "action": "move",
                                     "unit": unit["id"], "x": target[0],
                                     "y": target[1], "z": target[2]})
                if result.get("ok"):
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

        client.wait_for("client walk completes",
                        lambda: (unit_pos(client, moved_id) != before) or None,
                        timeout=30, interval=0.25)
        host.wait_for("client walk reaches authoritative host",
                      lambda: (unit_pos(host, moved_id) == unit_pos(client, moved_id)) or None,
                      timeout=30, interval=0.25)
        assert unit_pos(host, moved_id) != before

        # Both ready presses must advance the side rather than leave NextTurnState
		# permanently waiting.
        start = host.ok({"cmd": "battle_state"})
        start_turn, start_side = start["turn"], start["side"]
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
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
