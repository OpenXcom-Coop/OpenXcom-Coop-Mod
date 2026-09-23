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
        client.ok({"cmd": "open_screen", "screen": "basescape", "base": "ClientBase"})
        client.ok({"cmd": "basescape_select_base", "base": "HostBase"})
        menu = client.ok({"cmd": "basescape_menu_state"})
        assert menu["foreign"] and menu["base"] == "HostBase", menu
        for button in ("newBase", "facilities", "research", "manufacture",
                       "transfer", "sell"):
            assert not menu["visible"][button], menu
        assert menu["miniBorderColors"]["HostBase"] == 1, menu
        client.ok({"cmd": "leave_base"})

        client.ok({"cmd": "globe_click_base", "base": "HostBase"})
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
        print("PASS Separate UI: foreign restrictions, direct marker and own BASES selection")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()

