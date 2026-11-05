"""PvP campaign: the alien player's UFO window keeps the hyper-wave details (issue #183).

In a PvP campaign each player simulates a world of their own. In game mode 2 the host plays
X-COM and the client the aliens: the host's radar detects the host's UFO, the UfoDetectedState
ctor broadcasts ufo_popup, and the alien client raises its own window for its mirror of that UFO
(the mirror is matched by type and race). The aliens know their own UFOs completely - the alien
client's mirrors are always hyper-wave detected - so the alien player's window must show craft
type, race, mission and zone even when X-COM saw the UFO on conventional radar only.

  ALERT  the X-COM host raises a CONVENTIONAL alert for a UFO the alien client has mirrored
         -> the client's window for that mirror (by coop id) is the hyper-wave one.

The UFO is spawned on the X-COM host only, beside its base (inside its radar cover, so the host's
radar sweep keeps it tracked), and reaches the alien client through the host's mirror snapshot,
as the PvP campaign tests do. Game mode 3 (alien host, X-COM client) is not covered: there the
alien host's own sim detects its UFOs, so the alien player's window is never built from a peer's
alert.

Run:  python tools/coop_test/test_pvp_campaign_hyperwave_ufo_alert.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients
import geo
import pvp_fixture
import ufo_alert_helpers as UA

KEY = "48392"   # lobby rendezvous key (an in-process label, see harness.py)


def main():
    host = GameClient("host", 48390, make_user_dir("pvp_hyperwave_alert_host"))
    client = GameClient("client", 48391, make_user_dir("pvp_hyperwave_alert_client"))
    try:
        host.spawn()
        host.connect()
        client.spawn()
        client.connect()
        gm = pvp_fixture.start_pvp_campaign(host, client, KEY, alien_player="client")
        roles = {gc.name: gc.ok({"cmd": "get_coop"}) for gc in (host, client)}
        assert gm == 2 and all(r.get("gamemode") == 2 for r in roles.values()), (gm, roles)
        assert roles["host"].get("noBases") is False and roles["client"].get("noBases") is True, roles
        print("PASS setup: game mode 2, X-COM host, alien client", flush=True)
        geo.slow_clock(host, client)

        base = next(b for b in host.ok({"cmd": "geo_state"})["bases"]
                    if b["name"] == "XcomBase" and not b["coopBase"])
        spawned = host.ok({"cmd": "spawn_ufo", **UA.UFO,
                           "lon": base["lon"] + 0.03, "lat": base["lat"] + 0.02})
        real = UA.find_ufo(host, id=spawned["ufo_id"], coop=False)
        assert real and real["detected"] is True, (spawned, real)
        mirror = UA.wait_ufo(client, "the alien client's mirror of the host's UFO", timeout=UA.WAIT_S,
                             coop=True, coopId=real["coopId"], detected=True)
        print(f"EVIDENCE host UFO {json.dumps(real)} / alien client mirror {json.dumps(mirror)}", flush=True)
        assert UA.ufo_window(client) is None, f"client already shows a UFO window: {UA.ufo_window(client)}"

        # ---- ALERT: X-COM detected it on conventional radar ------------------------
        UA.alert(host, spawned["ufo_id"], False)
        window = UA.wait_ufo_window(client, "the alien client's UFO window", ufoCoopId=real["coopId"])
        assert window["hyperwave"] is True, \
            f"the alien player's window lost the hyper-wave details for a conventional X-COM detection: {window}"
        print("PASS alert: the alien client's window for a conventionally detected UFO is the hyper-wave one",
              flush=True)

        client.ok({"cmd": "dismiss_popup"})
        print("ALL PVP HYPER-WAVE UFO ALERT TESTS PASSED", flush=True)
    finally:
        shutdown_clients(host, client)


if __name__ == "__main__":
    main()
