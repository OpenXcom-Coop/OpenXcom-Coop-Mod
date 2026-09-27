"""Separate Campaign: owner-only mission prompt and crash-free YES entry."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has_state(gc, name):
    return any(name in state for state in states(gc))


def main():
    js = fixture.bring_up("sep_mission", (48972, 48973, 48272))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
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
        print("PASS Separate mission: owner-only prompt and safe YES entry")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
