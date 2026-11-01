"""Shared UFO alerts preserve host hyperwave details on the client popup."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture


UFO = dict(type="STR_MEDIUM_SCOUT", mission="STR_ALIEN_RESEARCH",
           region="STR_NORTH_AMERICA", race="STR_SECTOID",
           trajectory="P0", state="flying", speed=1, lon=0.4, lat=0.3)


def main():
    js = shared_fixture.bring_up("shared_hyperwave_alert", (49070, 49071, 48370))
    host, client = js.host, js.client
    try:
        rh = host.ok({"cmd": "spawn_ufo", **UFO})
        rc = client.ok({"cmd": "spawn_ufo", **UFO})
        assert rh.get("ok") and rc.get("ok"), (rh, rc)

        alert = host.ok({"cmd": "ufo_alert", "ufo_id": rh["ufo_id"],
                         "hyperwave": True})
        assert alert["hyperDetected"] is True, alert

        state = client.wait_for(
            "client hyperwave UFO popup",
            lambda: (lambda s: s if s.get("top") == "ufo_detected" else None)(
                client.ok({"cmd": "screen_state"})),
            timeout=30, interval=0.25)
        assert state["hyperwave"] is True, state
        print("PASS Shared client UFO popup preserves host hyperwave details")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
