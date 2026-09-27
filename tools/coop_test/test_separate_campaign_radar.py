"""Separate Campaign: foreign bases use their real facilities for UFO detection."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


def main():
    js = fixture.bring_up("sep_radar", (48972, 48973, 48272))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        client_base = next(b for b in fixture.geo(host)["bases"]
                           if b["name"] == "ClientBase")
        ufo = host.ok({
            "cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
            "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
            "race": "STR_SECTOID", "trajectory": "P0", "state": "flying",
            "speed": 0, "lon": client_base["lon"], "lat": client_base["lat"]
        })
        radar = host.ok({"cmd": "base_detect_trials", "base": "ClientBase",
                         "ufo_id": ufo["ufo_id"], "trials": 500})
        assert radar["coopBase"] is True, radar
        assert radar["detected"] > 0, radar
        print("PASS Separate radar: a foreign base detected a UFO with its real facilities")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
