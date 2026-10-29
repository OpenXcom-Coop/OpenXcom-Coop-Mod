"""Focused Separate regression: foreign base and geoscape presentation."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import separate_campaign_fixture as fixture


def main():
    js = fixture.bring_up("sep_ui", (48942, 48943, 48242))
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        # Vanilla assigns eight soldiers to the starting Skyranger. Separate's
        # two-player quota is seven places per player and must be applied before
        # the campaign starts, not only to later assignment clicks.
        for gc, base_name in ((host, "HostBase"), (client, "ClientBase")):
            report = gc.ok({"cmd": "base_report", "base": base_name})
            transport = next(c for c in report["crafts"]
                             if c["type"] == "STR_SKYRANGER")
            assert transport["soldiers"] == 7, (gc.name, report)
        client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientBase"})
        wallets = client.ok({"cmd": "month_report"})["playerFunds"]
        own_menu = client.ok({"cmd": "basescape_menu_state"})
        assert own_menu["displayedFunds"] == wallets["ClientPlayer"], own_menu
        assert own_menu["miniDisplaySlots"]["ClientBase"] == 0, own_menu
        assert own_menu["miniDisplaySlots"]["HostBase"] == 1, own_menu
        client.ok({"cmd": "basescape_select_base", "base": "HostBase"})
        menu = client.ok({"cmd": "basescape_menu_state"})
        assert menu["foreign"] and menu["base"] == "HostBase", menu
        assert menu["displayedFunds"] == wallets["HostPlayer"], menu
        assert not menu["visible"]["newBase"], menu
        assert menu["baseOwnerVisible"], menu
        assert menu["baseOwnerText"] == "Owner: HostPlayer", menu
        for button in ("facilities", "research", "manufacture", "sell"):
            assert not menu["visible"][button], menu
        # Owner ruling RU17: a visitor may transfer their own soldiers out of a
        # partner base, so Transfer shows there.
        assert menu["visible"]["transfer"], menu
        assert menu["miniBorderColors"]["HostBase"] == 1, menu
        host_costs = client.ok({"cmd": "base_report", "base": "HostBase"})
        assert host_costs["ownerPlayerMaintenance"] == \
            host_costs["monthlyMaintenance"], host_costs
        client.ok({"cmd": "open_screen", "screen": "monthly_costs",
                   "base": "HostBase"})
        cost_screen = client.ok({"cmd": "screen_state"})
        assert cost_screen["top"] == "monthly_costs", cost_screen
        assert cost_screen["maintenance"] == \
            host_costs["ownerPlayerMaintenance"], (cost_screen, host_costs)
        client.ok({"cmd": "close_screens"})

        client.ok({"cmd": "globe_click_base", "base": "HostBase",
                   "include_craft": True})
        client.wait_for(
            "foreign marker opens Basescape",
            lambda: (client.cmd({"cmd": "basescape_menu_state"}).get("base")
                     == "HostBase") or None,
            timeout=15, interval=0.3)
        client.ok({"cmd": "leave_base"})
        client.ok({"cmd": "click_bases"})
        own = client.wait_for(
            "BASES selects own base",
            lambda: (lambda r: r if r.get("base") == "ClientBase" else None)(
                client.cmd({"cmd": "basescape_menu_state"})),
            timeout=15, interval=0.3)
        assert not own["foreign"], own
        assert own["miniBorderColors"]["HostBase"] == 247, own
        client.ok({"cmd": "leave_base"})
        print("PASS Separate UI: seven starting crew, foreign base/craft overlap, and own BASES selection")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()

