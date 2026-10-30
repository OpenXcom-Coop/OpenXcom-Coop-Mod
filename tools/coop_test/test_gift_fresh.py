"""Autonomous test: brand-new hosted campaign, connect a client, gift the
first host soldier, verify the client sees them at the host's base.

Separate is one host-owned world: a gift changes the soldier's owner and the
soldier stays at the host's base. There is no mirror base and no physical
move between worlds. The player-visible result: the client owns the soldier at the host's base, and the host's own
soldier list no longer shows it.

Run:  python tools/coop_test/test_gift_fresh.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session


def main():
    host = GameClient("host", 47801, make_user_dir("host-user"))
    client = GameClient("client", 47802, make_user_dir("client-user"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()

        session.new_campaign(host, client)
        print("fresh coop session established")

        # --- pick host's first soldier, gift, verify ---
        hs = host.ok({"cmd": "get_soldiers"})
        hbase = next(b for b in hs["bases"] if b["name"] == "HostBase")
        soldier = next(s for s in hbase["soldiers"] if s["owner"] == 0)
        sid = soldier["id"]
        print(f"gifting {soldier['name']} (id={sid}) from '{hbase['name']}'")

        host.ok({"cmd": "gift", "name": soldier["name"], "owner": 1})

        def at_host_base(gc):
            for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
                if b["name"] == "HostBase":
                    return next((s for s in b["soldiers"] if s["id"] == sid), None)
            return None

        def client_sees():
            s = at_host_base(client)
            return s if s and s["name"] == soldier["name"] and s["owner"] == 1 else None

        s = client.wait_for("soldier at host base on client", client_sees, timeout=60)
        print(f"PASS: client sees {s['name']} owner={s['owner']} at HostBase")

        hs2 = at_host_base(host)
        assert hs2 and hs2["owner"] == 1, f"host world did not record the new owner: {hs2}"
        host.ok({"cmd": "open_screen", "screen": "soldiers", "base": "HostBase"})
        host.wait_for("host soldiers screen",
                      lambda: (host.cmd({"cmd": "screen_state"}).get("top") == "soldiers") or None,
                      timeout=15, interval=0.3)
        shown = host.cmd({"cmd": "screen_state"}).get("displayed", [])
        host.ok({"cmd": "close_screens"})
        assert sid not in shown, f"host's soldier list still shows the gifted soldier: {shown}"
        others = sorted(s["id"] for s in hbase["soldiers"] if s["owner"] == 0 and s["id"] != sid)
        assert sorted(shown) == others, f"host's soldier list {shown} != its other soldiers {others}"
        print("PASS: gone from the host's soldier list")
        print("TEST PASSED")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
