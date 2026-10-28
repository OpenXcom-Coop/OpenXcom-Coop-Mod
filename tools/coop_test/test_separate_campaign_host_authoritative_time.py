"""Separate campaign client must never simulate Geoscape time locally.

The host opens Basescape while the client remains on the Geoscape at a fast
speed. The client clock must stay frozen because only the host owns strategic
simulation. The source contract also ensures replica detection is outside the
live-connection gate, so losing the host cannot enable local simulation.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


ROOT = Path(__file__).resolve().parents[2]


def clock(gc):
    value = gc.ok({"cmd": "geo_state"})["time"]
    return tuple(value[key] for key in ("year", "month", "day", "hour", "minute"))


def main():
    source = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    assert "if (_game->getCoopMod()->isCampaignReplica())\n\t\ttimeSpan = 0;" in source
    replica_body = tcp.split("bool connectionTCP::isCampaignReplica()", 1)[1].split("\n}", 1)[0]
    assert "coop_save_owner_player_id > 0" in replica_body
    assert "getCoopStatic()" not in replica_body

    js = fixture.bring_up("sep_host_time", (52870, 52871, 52170))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        host.ok({"cmd": "geo_set_speed", "idx": 4})
        client.ok({"cmd": "geo_set_speed", "idx": 4})

        host.ok({"cmd": "click_bases"})
        host.wait_for("host entered Basescape", lambda: (
            host.cmd({"cmd": "basescape_menu_state"}).get("base") or None),
            timeout=20, interval=.25)

        # Let any already queued host time packet settle before measuring.
        time.sleep(1.5)
        before = clock(client)
        time.sleep(4.0)
        after = clock(client)
        assert after == before, (
            "Separate client advanced its own Geoscape clock while the host "
            f"was in Basescape: {before} -> {after}")
        print("PASS Separate client clock stays frozen while host is outside Geoscape")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
