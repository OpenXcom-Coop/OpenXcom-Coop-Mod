"""A foreign-base storage overflow is shown only to its Separate owner.

The test makes its own save: a fresh 40K + ROSIGMA Separate campaign whose
ClientBase stores are filled past capacity, saved by the host before the next
hourly storage check. Both machines then resume that save.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import geo
import session
import shared_fixture
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)


TAG = "sep_storage_owner_resume"
OPTIONS = {"storageLimitsEnforced": True}
SAVE_NAME = "separate_storage_owner_resume.sav"
# A stock item of the starting bases. More is given until ClientBase's stores
# are over capacity on both machines.
FILL_ITEM = "STR_LASER_RIFLEG"
FILL_STEP = 500
EVENT_HOLD_MINUTES = 30 * 24 * 60


def stores(machine, base_name):
    # The used total is a float sum whose last digits depend on the order the
    # items were added in, so it is compared rounded.
    report = machine.ok({"cmd": "base_report", "base": base_name})
    return round(report["usedStores"], 2), report["availableStores"]


def make_save():
    """A Separate campaign saved with ClientBase over its storage capacity."""
    js = shared_fixture.bring_up(
        TAG, (49630, 49631, 48930), mods=(MOD_40K, MOD_ROSIGMA),
        campaign_mode="coop", host_difficulty=0, client_difficulty=3, host_options=OPTIONS, client_options=OPTIONS,
        transport="tcp")
    host, client = js.host, js.client
    try:
        geo.slow_clock(host, client)
        for _ in range(10):
            used, available = stores(host, "ClientBase")
            if used > available + 1:
                break
            for machine in (host, client):
                machine.ok({"cmd": "give_items", "base": "ClientBase",
                            "item": FILL_ITEM, "count": FILL_STEP})
        host_stores = stores(host, "ClientBase")
        try:
            client.wait_for("client sees the overfull ClientBase",
                            lambda: stores(client, "ClientBase") == host_stores or None,
                            timeout=30)
        except TimeoutError as error:
            raise AssertionError({
                "host": stores(host, "ClientBase"), "client": stores(client, "ClientBase"),
                "hostItems": base(host, "ClientBase")["items"].get(FILL_ITEM),
                "clientItems": base(client, "ClientBase")["items"].get(FILL_ITEM),
                "hostStates": states(host), "clientStates": states(client)}) from error
        assert host_stores[0] > host_stores[1] + 1, host_stores
        # Hold ROSIGMA's pending geoscape events past the test: an event that
        # closes over the full stores opens its own sell screen.
        for event in host.ok({"cmd": "geo_events"})["events"]:
            if not event["over"]:
                host.ok({"cmd": "set_event_countdown", "name": event["name"],
                         "minutes": EVENT_HOLD_MINUTES})
        # The save must come before the hourly check opens the overflow dialog.
        assert not storage_dialog(host) and not storage_dialog(client), \
            (states(host), states(client))
        host.ok({"cmd": "save_game", "file": SAVE_NAME})
        host.wait_for("host campaign save written", lambda: any(
            os.path.basename(path) == SAVE_NAME
            for path in session.save_files(host.user_dir)) or None, timeout=30)
        print(f"made save {SAVE_NAME}: ClientBase stores {host_stores[0]} / {host_stores[1]}")
        return host.user_dir
    finally:
        js.shutdown()


def states(machine):
    return machine.cmd({"cmd": "get_state"}).get("states", [])


def storage_dialog(machine):
    current = states(machine)
    return ("storage" if any("SellState" in name or "ErrorMessageState" in name
                             for name in current) else None)


def storage_interest(machine):
    return storage_dialog(machine)


# The settle after the time skip must leave the overflow screens open.
storage_interest.keep = ("ErrorMessageState", "SellState")


def base(machine, name):
    return next(row for row in machine.ok({"cmd": "geo_state"})["bases"]
                if row["name"] == name)


def main():
    require_mods()
    host_dir = make_save()
    host = GameClient("host", 49632, host_dir)
    client = GameClient("client", 49633, make_user_dir(
        TAG + "_client2", mods=(MOD_40K, MOD_ROSIGMA), options=OPTIONS))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        host.ok({"cmd": "load_save_menu", "file": SAVE_NAME})
        host.wait_for("host resume window", lambda: session._has_state(host, "HostMenu"),
                      timeout=120)
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": "48931",
                 "player": "HostPlayer"})
        host.wait_for("host resume lobby", lambda: session._has_state(host, "LobbyMenu"))
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": "48931",
                   "player": "ClientPlayer"})
        client.wait_for("client resume lobby", lambda: session._has_state(client, "LobbyMenu"))
        time.sleep(3)
        session.resume_campaign_via_button(host, "ClientPlayer")
        host.wait_for("client world ack",
                      lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
                      timeout=120)
        session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        client.wait_for("resumed geoscape",
                        lambda: session._has_state(client, "GeoscapeState") or None,
                        timeout=120)

        result = geo.skip_realtime(
            host, client, 45, speed_idx=3,
            interest=storage_interest, dismiss=True, stuck_timeout=None)
        assert result["hit"], result
        assert result["hit"][0] == "client", result
        assert not storage_dialog(host), {"result": result, "host": states(host)}
        assert storage_dialog(client), {"result": result, "client": states(client)}

        # Close only the error message. The mandatory SellState queued behind it
        # must remain and retain ClientBase as its target.
        while "SellState" not in states(client)[-1]:
            dismissed = client.ok({"cmd": "dismiss_popup"})
            assert dismissed.get("handled") == "generic", dismissed
            client.wait_for("ClientBase sell state",
                            lambda: "SellState" in states(client)[-1] or None,
                            timeout=10)

        # Sell the filler, which brings ClientBase back under its capacity, as a
        # player must before this sell screen closes.
        client_before = base(host, "ClientBase")["items"]
        host_before = base(host, "HostBase")["items"]
        sold_item = FILL_ITEM
        sold = client_before.get(sold_item, 0)
        result_sell = client.cmd({"cmd": "sell_open_item", "item": sold_item, "count": sold})
        assert sold and result_sell.get("ok"), {
            "items": client_before, "sell": result_sell, "states": states(client)}

        expected = client_before[sold_item] - sold
        host.wait_for(
            "authoritative ClientBase sale",
            lambda: base(host, "ClientBase")["items"].get(sold_item, 0) == expected or None,
            timeout=30,
        )
        assert base(host, "HostBase")["items"].get(sold_item, 0) == \
            host_before.get(sold_item, 0), {
                "item": sold_item,
                "before": host_before.get(sold_item, 0),
                "after": base(host, "HostBase")["items"].get(sold_item, 0),
            }

        # The host may advance several hourly ticks while the remote SellState is
        # open. Those ticks must not have queued duplicate overflow dialogs.
        time.sleep(2)
        assert not storage_dialog(client), {
            "error": "duplicate ClientBase storage dialog was queued",
            "states": states(client),
        }
        print("PASS ClientBase overflow is owner-routed and shown only once")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
