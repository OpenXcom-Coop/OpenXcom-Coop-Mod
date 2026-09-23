"""Focused Separate regression: foreign-base hire ownership and arrival."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def main():
    js = fixture.bring_up("sep_soldiers", (48944, 48945, 48244))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        host.ok({"cmd": "buy", "item": "STR_SOLDIER", "count": 1,
                 "kind": "soldier", "base": "ClientBase"})
        for gc in (host, client):
            gc.wait_for(
                "foreign recruit en route",
                lambda gc=gc: (gc.ok({"cmd": "incoming_transfers",
                                      "base": "ClientBase"})["soldiers"] == 1) or None,
                timeout=30, interval=0.5)
        host.ok({"cmd": "force_transfer_arrivals", "base": "ClientBase"})
        client.wait_for(
            "replica transfer removed",
            lambda: (client.ok({"cmd": "incoming_transfers",
                                "base": "ClientBase"})["soldiers"] == 0) or None,
            timeout=30, interval=0.5)

        host_rows = host.ok({"cmd": "items_arriving_rows"})["rows"]
        client_rows = client.ok({"cmd": "items_arriving_rows"})["rows"]
        assert len(host_rows) == len(client_rows) == 1
        assert not host_rows[0].startswith("[")
        assert client_rows[0].startswith("[HostPlayer] "), client_rows
        geo.drain_popups(host); geo.drain_popups(client)

        roster = fixture.soldiers_at(host, "ClientBase")
        host_owned = {s["id"] for s in roster if s["owner"] == 0}
        client_owned = {s["id"] for s in roster if s["owner"] == 1}
        for gc, expected in ((host, host_owned), (client, client_owned)):
            gc.ok({"cmd": "open_soldiers", "base": "ClientBase"})
            shown = set(gc.ok({"cmd": "screen_state"})["displayed"])
            assert shown == expected, (gc.name, shown, expected)
            gc.ok({"cmd": "soldiers_ok"})
        fixture.assert_same_world(host, client, "Separate soldier arrival")
        print("PASS Separate soldiers: arrival, owner label and private roster")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()

