"""Separate UFO alerts preserve host hyperwave details on the client popup."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


UFO = dict(type="STR_MEDIUM_SCOUT", mission="STR_ALIEN_RESEARCH",
           region="STR_NORTH_AMERICA", race="STR_SECTOID",
           trajectory="P0", state="flying", speed=1, lon=0.4, lat=0.3)


def main():
    js = fixture.bring_up("separate_hyperwave_alert", (49072, 49073, 48372))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        rh = host.ok({"cmd": "spawn_ufo", **UFO})
        rc = client.ok({"cmd": "spawn_ufo", **UFO})
        assert rh.get("ok") and rc.get("ok"), (rh, rc)

        alert = host.ok({"cmd": "ufo_alert", "ufo_id": rh["ufo_id"],
                         "hyperwave": True})
        assert alert["hyperDetected"] is True, alert

        state = client.wait_for(
            "Separate client hyperwave UFO popup",
            lambda: (lambda s: s if s.get("top") == "ufo_detected" else None)(
                client.ok({"cmd": "screen_state"})),
            timeout=30, interval=0.25)
        assert state["hyperwave"] is True, state
        print("PASS Separate client UFO popup preserves host hyperwave details")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
