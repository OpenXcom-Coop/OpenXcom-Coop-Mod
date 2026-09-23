"""Focused Separate regression: foreign craft crew view and 7+7 quota."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture


def main():
    js = fixture.bring_up("sep_craft", (48940, 48941, 48240))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)

        # Give the host one owned soldier physically stationed at ClientBase.
        before = {s["name"] for s in fixture.soldiers_at(host, "ClientBase")}
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
            "replica cleared recruit transfer",
            lambda: (client.ok({"cmd": "incoming_transfers",
                                "base": "ClientBase"})["soldiers"] == 0) or None,
            timeout=30, interval=0.5)
        geo.drain_popups(host)
        geo.drain_popups(client)

        roster = fixture.soldiers_at(host, "ClientBase")
        guest = next(s for s in roster if s["owner"] == 0 and s["name"] not in before)
        craft_id = next(s["craftId"] for s in roster
                        if s["owner"] == 1 and s["craftId"] >= 0)

        # This is the Crew column on Bases > Equip Craft shown in bugi5.PNG.
        host.ok({"cmd": "open_screen", "screen": "crafts", "base": "ClientBase"})
        crafts = host.ok({"cmd": "crafts_state", "craft_id": craft_id})
        assert crafts["crew"] == 0, crafts
        host.ok({"cmd": "pop_state"})

        # The foreign owner's seven crew must not consume the visitor's display
        # quota on the real Equip Craft screen.
        host.ok({"cmd": "open_craft_equipment", "base": "ClientBase",
                 "craft_id": craft_id})
        equipment = host.ok({"cmd": "craft_equipment_state"})
        assert equipment["crew"] == 0, equipment
        assert equipment["used"] == 0 and equipment["available"] == 7, equipment
        host.ok({"cmd": "craft_equipment_ok"})

        host.ok({"cmd": "open_craft_info", "base": "ClientBase",
                 "craft_id": craft_id})
        summary = host.ok({"cmd": "craft_info_state"})
        assert summary["visibleCrew"] == 0, summary
        host.ok({"cmd": "pop_state"})

        host.ok({"cmd": "open_screen", "screen": "craft_soldiers",
                 "base": "ClientBase", "craft_id": craft_id})
        screen = host.ok({"cmd": "screen_state"})
        assert screen["top"] == "craft_soldiers", screen
        assert screen["displayed"] == [guest["id"]], screen
        assert screen["maxUnits"] == 14, screen
        assert screen["usedNum"] == 0 and screen["availableNum"] == 7, screen
        host.ok({"cmd": "pop_state"})

        host.ok({"cmd": "craft_assign", "base": "ClientBase",
                 "craft_id": craft_id, "soldier_id": guest["id"], "on": True})
        for gc in (host, client):
            gc.wait_for(
                "guest assigned to foreign craft",
                lambda gc=gc: (next(
                    s for s in fixture.soldiers_at(gc, "ClientBase")
                    if s["name"] == guest["name"])["craftId"] == craft_id) or None,
                timeout=30, interval=0.5)

        host.ok({"cmd": "open_screen", "screen": "craft_soldiers",
                 "base": "ClientBase", "craft_id": craft_id})
        screen = host.ok({"cmd": "screen_state"})
        assert screen["usedNum"] == 1 and screen["availableNum"] == 6, screen
        host.ok({"cmd": "pop_state"})

        host.ok({"cmd": "open_craft_equipment", "base": "ClientBase",
                 "craft_id": craft_id})
        equipment = host.ok({"cmd": "craft_equipment_state"})
        assert equipment["crew"] == 1, equipment
        assert equipment["used"] == 1 and equipment["available"] == 6, equipment
        host.ok({"cmd": "craft_equipment_ok"})

        host.ok({"cmd": "open_screen", "screen": "crafts", "base": "ClientBase"})
        crafts = host.ok({"cmd": "crafts_state", "craft_id": craft_id})
        assert crafts["crew"] == 1, crafts
        host.ok({"cmd": "pop_state"})
        fixture.assert_same_world(host, client, "Separate craft quota")
        print("PASS Separate craft: owner-filtered icons and 7+7 capacity")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
