"""Separate purchase arrivals notify the buyer and the receiving base owner.

An owner's own order at its own base notifies only that owner. A visitor's
order at the partner's base notifies both the visitor and the base owner."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def has_arrival(gc):
    return any("ItemsArrivingState" in state
               for state in gc.ok({"cmd": "get_state"}).get("states", []))


def arrival_count(gc):
    return sum("ItemsArrivingState" in state
               for state in gc.ok({"cmd": "get_state"}).get("states", []))


def deliver(host, buyer, item):
    buyer.ok({"cmd": "buy", "item": item, "count": 1, "base": "HostBase"})
    host.wait_for(
        f"{item} order on the host",
        lambda: host.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                    ["items"].get(item, 0) == 1 or None,
        timeout=30, interval=0.5)
    result = host.ok({"cmd": "force_transfer_arrivals", "base": "HostBase"})
    assert result["remaining"] == 0, result


def main():
    js = fixture.bring_up("sep_item_arrival_owner", (49030, 49031, 48330))
    host, client = js.host, js.client
    try:
        # The host's own order at its own base notifies only the host.
        deliver(host, host, "STR_PISTOL")
        host.wait_for("owner's own arrival popup", lambda: has_arrival(host) or None,
                      timeout=20, interval=0.3)
        own_rows = host.ok({"cmd": "items_arriving_rows"})["rows"]
        assert len(own_rows) == 1 and own_rows[0].strip(), own_rows
        geo.drain_popups(host)

        # The client's order at the host's base notifies both players. The host
        # sent the earlier arrival first on the same connection, so once this
        # popup is up on the client the earlier one has been received too: the
        # client must hold exactly this one popup with only the rifle row.
        deliver(host, client, "STR_RIFLE")
        host.wait_for("base owner arrival popup", lambda: has_arrival(host) or None,
                      timeout=20, interval=0.3)
        client.wait_for("buyer arrival popup", lambda: has_arrival(client) or None,
                        timeout=20, interval=0.3)
        host_rows = host.ok({"cmd": "items_arriving_rows"})["rows"]
        client_rows = client.ok({"cmd": "items_arriving_rows"})["rows"]
        assert len(host_rows) == 1 and host_rows[0].strip(), host_rows
        assert client_rows == host_rows, (client_rows, host_rows)
        assert own_rows[0] not in client_rows, (own_rows, client_rows)
        assert arrival_count(client) == 1, client.ok({"cmd": "get_state"})
        geo.drain_popups(host)
        geo.drain_popups(client)
        print("PASS Separate arrival popup reaches the buyer and the base owner, "
              "and an owner's own order stays with the owner")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
