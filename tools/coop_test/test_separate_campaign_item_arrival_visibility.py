"""Separate purchase arrivals notify only the purchasing player."""

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
        # Client deliberately buys its item into the host's base. Destination
        # ownership must not replace purchaser ownership for the notification.
        client.ok({"cmd": "buy", "item": "STR_RIFLE", "count": 1,
                   "base": "HostBase"})
        host.wait_for(
            "client purchase replicated",
            lambda: host.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                        ["items"].get("STR_RIFLE", 0) == 1 or None,
            timeout=30, interval=0.5)
        result = host.ok({"cmd": "force_transfer_arrivals", "base": "HostBase"})
        assert result["remaining"] == 0, result
        client.wait_for("purchaser arrival popup", lambda: has_arrival(client) or None,
                        timeout=20, interval=0.3)
        assert not has_arrival(host), host.ok({"cmd": "get_state"})
        rows = client.ok({"cmd": "items_arriving_rows"})["rows"]
        assert len(rows) == 1 and rows[0].strip(), rows
        geo.drain_popups(client)
        print("PASS Separate item arrival popup is purchaser-only across a foreign base")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
