"""Shared campaign: the client's UFO window and UFO flags follow the host's hyper-wave detection (issue #183).

The host simulates the one shared world and detects its UFOs; the client raises its own UFO
window from the host's ufo_popup alert and mirrors the host's UFOs from its position snapshot.
In ONE bring-up, one host-only UFO per scenario (ufo_alert_helpers):
  hyperwave_alert     hyper-wave alert -> hyper-wave window; client UFO hyperDetected == host's.
  conventional_alert  conventional alert -> conventional window; client UFO not hyper-wave detected.
  stale_flag          hyper-wave alert, the host loses the UFO, then re-detects it conventionally ->
                      the fresh window is conventional and the client's UFO flag matches the host's.
  gained_later        conventional alert, then the host's decoder decodes the tracked UFO without a
                      window -> the client's UFO becomes hyper-wave detected.
Every scenario runs; exit 0 only if all pass, else 2.

Run:  python tools/coop_test/test_shared_hyperwave_ufo_alert.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import ufo_alert_helpers


def main():
    js = shared_fixture.bring_up("shared_hyperwave_alert", (48384, 48385, 48386))
    host, client = js.host, js.client
    try:
        failed = ufo_alert_helpers.run_hyperwave_scenarios(host, client, "Shared")
    finally:
        js.shutdown()
    ufo_alert_helpers.report("Shared", failed)


if __name__ == "__main__":
    main()
