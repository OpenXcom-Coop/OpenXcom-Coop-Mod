"""Separate base-resource arrivals notify the receiving base owner."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def has_arrival(gc):
    return any("ItemsArrivingState" in state
               for state in gc.ok({"cmd": "get_state"}).get("states", []))


def main():
    js = fixture.bring_up("sep_item_arrival_owner", (49030, 49031, 48330))
    host, client = js.host, js.client
    try:
        # Client deliberately buys an item into the host's base. Items become
        # base storage, so the receiving base owner must get the notification.
        client.ok({"cmd": "buy", "item": "STR_RIFLE", "count": 1,
                   "base": "HostBase"})
        host.wait_for(
            "client purchase replicated",
            lambda: host.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                        ["items"].get("STR_RIFLE", 0) == 1 or None,
            timeout=30, interval=0.5)
        result = host.ok({"cmd": "force_transfer_arrivals", "base": "HostBase"})
        assert result["remaining"] == 0, result
        host.wait_for("base owner arrival popup", lambda: has_arrival(host) or None,
                      timeout=20, interval=0.3)
        assert not has_arrival(client), client.ok({"cmd": "get_state"})
        rows = host.ok({"cmd": "items_arriving_rows"})["rows"]
        assert len(rows) == 1 and rows[0].strip(), rows
        geo.drain_popups(host)
        print("PASS Separate base-resource arrival popup follows the receiving base owner")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
