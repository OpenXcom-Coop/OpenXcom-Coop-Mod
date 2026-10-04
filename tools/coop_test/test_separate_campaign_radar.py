"""Separate Campaign: own and foreign bases have equivalent real radar coverage."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


def main():
    js = fixture.bring_up("sep_radar", (48972, 48973, 48272))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        bases = {b["name"]: b for b in fixture.geo(host)["bases"]}

        results = {}
        for base_name in ("HostBase", "ClientBase"):
            base = bases[base_name]
            ufo = host.ok({
                "cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
                "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                "race": "STR_SECTOID", "trajectory": "P0", "state": "flying",
                "speed": 0, "lon": base["lon"], "lat": base["lat"]
            })
            results[base_name] = host.ok({
                "cmd": "base_detect_trials", "base": base_name,
                "ufo_id": ufo["ufo_id"], "trials": 4000
            })

        own, foreign = results["HostBase"], results["ClientBase"]
        assert own["coopBase"] is False, own
        assert foreign["coopBase"] is True, foreign
        assert own["detected"] > 0 and foreign["detected"] > 0, results

        # Both freshly-created bases have the same completed radar facilities and
        # the UFOs are directly above them. Random sampling need not be identical,
        # but a foreign-base ownership flag must not materially reduce detection.
        own_rate = own["detected"] / own["trials"]
        foreign_rate = foreign["detected"] / foreign["trials"]
        assert abs(own_rate - foreign_rate) < 0.04, results
        print("PASS Separate radar: own and foreign bases have equivalent detection rates "
              f"({own_rate:.1%} vs {foreign_rate:.1%})")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
