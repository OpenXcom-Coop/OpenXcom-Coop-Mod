"""Separate Campaign: the visitor's craft equipment rules, the owner-only mission prompt and a crash-free YES
entry into the battle the host runs.

In the battle the client commands its own soldier (its walk is admitted and lands on both machines, the host's
selection of it is refused: session.assert_seat_commands) and its END TURN leaves the player side."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import session
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
    tag = "sep_mission"
    ports = (48972, 48973, 48272)
    battle_options = {
        "battleXcomSpeed": 2,
        "battleAlienSpeed": 2,
    }
    js = fixture.bring_up(
        tag, ports,
        host_options=battle_options,
        client_options={"battleXcomSpeed": 2, "battleAlienSpeed": 2})
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

        # Vehicles use the same host-authoritative craft equipment lane as normal
        # items. First reproduce a client equipping the host's foreign craft, then
        # put a tank on the mission craft so battle generation is covered too.
        # Free enough physical space for the later two-tank assertion: starting
        # crew size is ruleset/configuration dependent, while six soldiers plus two 2x2
        # tanks would correctly exceed the Skyranger's capacity of fourteen.
        host_craft = next(c for c in next(
            b for b in world["bases"] if b["name"] == "HostBase")["crafts"]
            if c["type"] == "STR_SKYRANGER")
        host_roster = [s for s in fixture.soldiers_at(host, "HostBase")
                       if s.get("craftId") == host_craft["id"]]
        for soldier in host_roster[6:]:
            host.ok({"cmd": "craft_assign", "base": "HostBase",
                     "craft_id": host_craft["id"], "soldier_id": soldier["id"], "on": False})
        host.wait_for(
            "host craft space freed for two physical tanks",
            lambda: (lambda r: r if next(
                c for c in r["crafts"] if c["id"] == host_craft["id"]
            )["soldiers"] == 6 else None)(
                host.ok({"cmd": "base_report", "base": "HostBase"})),
            timeout=30, interval=0.3)
        for base_name in ("HostBase", "ClientBase"):
            for gc in (host, client):
                gc.ok({"cmd": "give_items", "base": base_name,
                       "item": "STR_TANK_CANNON", "count": 1})
                gc.ok({"cmd": "give_items", "base": base_name,
                       "item": "STR_HWP_CANNON_SHELLS", "count": 100})
        host.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "open_craft_equipment", "base": "HostBase",
                   "craft_id": host_craft["id"]})
        before_items = next(c for c in host.ok(
            {"cmd": "base_report", "base": "HostBase"})["crafts"]
            if c["id"] == host_craft["id"])["items"].get("STR_RIFLE", 0)
        client.ok({"cmd": "craft_equip", "base": "HostBase",
                   "craft_id": host_craft["id"],
                   "item": "STR_RIFLE", "count": 1})
        time.sleep(1.0)
        after_items = next(c for c in host.ok(
            {"cmd": "base_report", "base": "HostBase"})["crafts"]
            if c["id"] == host_craft["id"])["items"].get("STR_RIFLE", 0)
        assert after_items == before_items, (
            "visitor changed ordinary equipment on the base owner's craft",
            before_items, after_items)
        foreign_tank = client.ok({"cmd": "craft_equip", "base": "HostBase",
                                  "craft_id": host_craft["id"],
                                  "item": "STR_TANK_CANNON", "count": 1})
        assert foreign_tank["moved"], foreign_tank
        try:
            host.wait_for(
                "client tank reaches host craft",
                lambda: (lambda r: r if next(
                    c for c in r["crafts"] if c["id"] == host_craft["id"]
                )["vehicles"].get("STR_TANK_CANNON", 0) == 1 else None)(
                    host.ok({"cmd": "base_report", "base": "HostBase"})),
                timeout=30, interval=0.3)
        except TimeoutError as exc:
            raise AssertionError(
                f"{exc}; host stats={host.ok({'cmd': 'shared_stats'})}; "
                f"client stats={client.ok({'cmd': 'shared_stats'})}; "
                f"host base={host.ok({'cmd': 'base_report', 'base': 'HostBase'})}"
            ) from exc
        client.wait_for(
            "open foreign equipment screen refreshes tank quantity",
            lambda: (lambda r: r if r.get("craft") == "1" else None)(
                client.ok({"cmd": "craft_equipment_state",
                           "item": "STR_TANK_CANNON"})),
            timeout=30, interval=0.3)
        client.ok({"cmd": "craft_equipment_ok"})
        host.ok({"cmd": "open_craft_equipment", "base": "HostBase",
                 "craft_id": host_craft["id"]})
        host_tank_view = host.ok({"cmd": "craft_equipment_state",
                                  "item": "STR_TANK_CANNON"})
        # The list renders a zero quantity as an empty cell.
        assert host_tank_view["craft"] in ("", "0"), (
            host_tank_view,
            host.ok({"cmd": "base_report", "base": "HostBase"}),
            client.ok({"cmd": "base_report", "base": "HostBase"}))
        host.ok({"cmd": "craft_equipment_ok"})
        owner_claim = host.ok({"cmd": "craft_equip", "base": "HostBase",
                               "craft_id": host_craft["id"],
                               "item": "STR_TANK_CANNON", "count": 1})
        assert owner_claim["moved"], owner_claim
        host.wait_for(
            "host base owner takes priority on the only tank",
            lambda: (lambda c: c if (
                c["vehicleSeats"].get("STR_TANK_CANNON", [0, 0]) == [1, 0]
                and c["vehicleOwners"].get("STR_TANK_CANNON", [])
                == ["HostPlayer"]
            ) else None)(next(
                c for c in host.ok({"cmd": "base_report", "base": "HostBase"})["crafts"]
                if c["id"] == host_craft["id"])),
            timeout=30, interval=0.3)
        # Once a second physical tank exists, the visitor can select it and both
        # seats retain one independently controlled vehicle.
        for gc in (host, client):
            gc.ok({"cmd": "give_items", "base": "HostBase",
                   "item": "STR_TANK_CANNON", "count": 1})
        client.ok({"cmd": "craft_equip", "base": "HostBase",
                   "craft_id": host_craft["id"],
                   "item": "STR_TANK_CANNON", "count": 1})
        try:
            host.wait_for(
                "two tanks satisfy host and client selections",
                lambda: (lambda c: c if (
                    c["vehicleSeats"].get("STR_TANK_CANNON", [0, 0]) == [1, 1]
                    and sorted(c["vehicleOwners"].get("STR_TANK_CANNON", []))
                    == ["ClientPlayer", "HostPlayer"]
                ) else None)(next(
                    c for c in host.ok({"cmd": "base_report", "base": "HostBase"})["crafts"]
                    if c["id"] == host_craft["id"])),
                timeout=30, interval=0.3)
        except TimeoutError as exc:
            raise AssertionError(
                f"{exc}; host stats={host.ok({'cmd': 'shared_stats'})}; "
                f"client stats={client.ok({'cmd': 'shared_stats'})}; "
                f"host base={host.ok({'cmd': 'base_report', 'base': 'HostBase'})}; "
                f"client base={client.ok({'cmd': 'base_report', 'base': 'HostBase'})}"
            ) from exc
        # A 2x2 tank consumes four of the client's seven allocated places.
        # Reduce its initially over-quota eight-person roster to three first.
        client_roster = [s for s in fixture.soldiers_at(client, "ClientBase")
                         if s.get("craftId") == craft["id"]]
        for soldier in client_roster[3:]:
            client.ok({"cmd": "craft_assign", "base": "ClientBase",
                       "craft_id": craft["id"], "soldier_id": soldier["id"],
                       "on": False})
        host.wait_for(
            "client mission craft has room in its player quota",
            lambda: (lambda r: r if next(
                c for c in r["crafts"] if c["id"] == craft["id"]
            )["soldiers"] == 3 else None)(
                host.ok({"cmd": "base_report", "base": "ClientBase"})),
            timeout=30, interval=0.3)
        mission_tank = client.ok({"cmd": "craft_equip", "base": "ClientBase",
                                  "craft_id": craft["id"],
                                  "item": "STR_TANK_CANNON", "count": 1})
        assert mission_tank["moved"], mission_tank
        host.wait_for(
            "mission tank reaches authoritative craft",
            lambda: (lambda r: r if next(
                c for c in r["crafts"] if c["id"] == craft["id"]
            )["vehicles"].get("STR_TANK_CANNON", 0) == 1 else None)(
                host.ok({"cmd": "base_report", "base": "ClientBase"})),
            timeout=30, interval=0.3)

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

        # Drive the real briefing -> equipment -> tactical path on both machines. Stopping at inBattle=True
        # would miss a completely wedged map.
        if not session.drive_both_to_tactical(host, client):
            raise AssertionError(f"tactical never reached: host={session.states(host)} "
                                 f"client={session.states(client)}")

        hb, cb = host.ok({"cmd": "battle_state"}), client.ok({"cmd": "battle_state"})
        assert hb["host"] is True, hb
        assert cb["host"] is False, cb
        for battle, label in ((hb, "host"), (cb, "client")):
            assert any(u.get("faction") == 0 and not u.get("isPlayerSoldier")
                       and u.get("weapon") == "STR_TANK_CANNON"
                       and u.get("coop") == 1
                       for u in battle["units"]), (
                f"{label} battle omitted the synchronized tank", battle)

        # The client commands its own soldier; the host may not select it.
        client_soldier = next(u["id"] for u in hb["units"] if u.get("isPlayerSoldier")
                              and u.get("coop") == 1 and not u.get("isOut"))
        session.assert_seat_commands(host, client, client_soldier, None, host_check=True,
                                     what="Separate mission")

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
