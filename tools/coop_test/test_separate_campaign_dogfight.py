"""Separate Campaign: owned intercept rows and owner-only concurrent dogfights."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def craft_at(gc, base_name, craft_id, craft_type):
    base = next(b for b in fixture.geo(gc)["bases"] if b["name"] == base_name)
    return next(c for c in base["crafts"]
                if c["id"] == craft_id and c["type"] == craft_type)


def visible_fights(gc):
    state = gc.ok({"cmd": "dogfight_state"})
    return state, [d for d in state["dogfights"] if d["visible"]]


def main():
    js = fixture.bring_up("sep_dogfight", (48970, 48971, 48270))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)

        # The real InterceptState must list only locally owned craft.
        host_rows = host.ok({"cmd": "intercept_list"})["rows"]
        client_rows = client.ok({"cmd": "intercept_list"})["rows"]
        assert host_rows and {r["base"] for r in host_rows} == {"HostBase"}, host_rows
        assert client_rows and {r["base"] for r in client_rows} == {"ClientBase"}, client_rows

        hg = fixture.geo(host)
        host_base = next(b for b in hg["bases"] if b["name"] == "HostBase")
        client_base = next(b for b in hg["bases"] if b["name"] == "ClientBase")
        host_craft = next(c for c in host_base["crafts"]
                          if c["type"] == "STR_INTERCEPTOR")
        client_craft = next(c for c in client_base["crafts"]
                            if c["type"] == "STR_INTERCEPTOR")

        def spawn_near(base):
            return host.ok({
                "cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
                "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                "race": "STR_SECTOID", "trajectory": "P0", "state": "flying",
                "speed": 1, "lon": base["lon"] + 0.03, "lat": base["lat"]
            })["ufo_id"]

        host_ufo = spawn_near(host_base)
        client_ufo = spawn_near(client_base)
        client.wait_for(
            "both UFOs replicated",
            lambda: (len([u for u in fixture.geo(client)["ufos"]
                          if u["id"] in (host_ufo, client_ufo)]) == 2) or None,
            timeout=30, interval=0.3)

        # Enter both pairs through the real DogfightState lane in one host tick.
        # The deterministic hook avoids tiny scouts ending between harness polls.
        host.ok({"cmd": "start_test_dogfight",
                 "base": "HostBase", "craft_id": host_craft["id"],
                 "craft_type": host_craft["type"],
                 "ufo_id": host_ufo})
        host.ok({"cmd": "start_test_dogfight",
                 "base": "ClientBase", "craft_id": client_craft["id"],
                 "craft_type": client_craft["type"],
                 "ufo_id": client_ufo})

        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(0.15)
            hs, hv = visible_fights(host)
            cs, cv = visible_fights(client)
            if hs["count"] >= 2 and len(hv) == 1 and len(cv) == 1:
                break
        else:
            raise AssertionError(
                f"owner-only concurrent dogfights did not open: "
                f"host={visible_fights(host)} client={visible_fights(client)}")

        assert hv[0]["craftId"] == host_craft["id"], hv
        assert cv[0]["craftId"] == client_craft["id"], cv
        assert hv[0]["base"] == "HostBase", hv
        assert cv[0]["base"] == "ClientBase", cv
        assert hs["visibleCount"] == cs["visibleCount"] == 1, (hs, cs)

        # The host remains the sole simulator even for the client's hidden-on-host
        # fight. Damage written to its live authoritative objects must replicate.
        host.ok({"cmd": "craft_force", "base": "ClientBase",
                 "craft_id": client_craft["id"],
                 "craft_type": client_craft["type"], "damage": 7})
        host.ok({"cmd": "set_ufo_damage", "ufo_id": client_ufo, "damage": 11})

        def damage_synced():
            hc = craft_at(host, "ClientBase", client_craft["id"], client_craft["type"])
            cc = craft_at(client, "ClientBase", client_craft["id"], client_craft["type"])
            hu = next(u for u in fixture.geo(host)["ufos"] if u["id"] == client_ufo)
            cu = next(u for u in fixture.geo(client)["ufos"] if u["id"] == client_ufo)
            return (hc["damage"] == cc["damage"] and hc["damage"] >= 7
                    and hu["damage"] == cu["damage"] and hu["damage"] >= 11)

        client.wait_for("host-authoritative dogfight damage", damage_synced,
                        timeout=30, interval=0.3)
        print("PASS Separate dogfight: owned intercept rows, concurrent owner-only "
              "windows, and host-authoritative damage sync")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
