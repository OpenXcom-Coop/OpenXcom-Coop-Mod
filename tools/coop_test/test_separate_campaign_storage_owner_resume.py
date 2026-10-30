"""A foreign-base storage overflow is shown only to its Separate owner."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import GameClient, make_user_dir
import geo
import session
from test_separate_campaign_three_month_factions import (
    MOD_40K, MOD_ROSIGMA, require_mods)


SAVE_PATH = r"C:\Users\arita\Documents\OpenXcom\40k\campaign_continue.sav"
SAVE_NAME = "campaign_continue.sav"


def states(machine):
    return machine.cmd({"cmd": "get_state"}).get("states", [])


def storage_dialog(machine):
    current = states(machine)
    return ("storage" if any("SellState" in name or "ErrorMessageState" in name
                             for name in current) else None)


def base(machine, name):
    return next(row for row in machine.ok({"cmd": "geo_state"})["bases"]
                if row["name"] == name)


def main():
    require_mods(("the 40K campaign save", SAVE_PATH))
    host_dir = make_user_dir(
        "sep_storage_owner_resume_host", saves=(SAVE_PATH,),
        mods=(MOD_40K, MOD_ROSIGMA), options={"storageLimitsEnforced": True})
    # 40k is the active master, so its saves live in <user>/40k rather than the
    # vanilla xcom1 folder used by make_user_dir's generic fixture staging.
    master_save_dir = os.path.join(host_dir, "40k")
    os.makedirs(master_save_dir, exist_ok=True)
    os.replace(os.path.join(host_dir, "xcom1", SAVE_NAME),
               os.path.join(master_save_dir, SAVE_NAME))
    host = GameClient("host", 49630, host_dir)
    client = GameClient("client", 49631, make_user_dir(
        "sep_storage_owner_resume_client", mods=(MOD_40K, MOD_ROSIGMA),
        options={"storageLimitsEnforced": True}))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        host.ok({"cmd": "load_save_menu", "file": SAVE_NAME})
        host.wait_for("host resume window", lambda: session._has_state(host, "HostMenu"),
                      timeout=120)
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": "48930",
                 "player": "HostPlayer"})
        host.wait_for("host resume lobby", lambda: session._has_state(host, "LobbyMenu"))
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": "48930",
                   "player": "ClientPlayer"})
        client.wait_for("client resume lobby", lambda: session._has_state(client, "LobbyMenu"))
        time.sleep(3)
        session.resume_campaign_via_button(host, "ClientPlayer")
        host.wait_for("client world ack",
                      lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
                      timeout=120)
        host.ok({"cmd": "coop_dialog_back"})
        client.wait_for("resumed geoscape",
                        lambda: session._has_state(client, "GeoscapeState") or None,
                        timeout=120)

        result = geo.skip_realtime(
            host, client, 45, speed_idx=3,
            interest=lambda machine: storage_dialog(machine),
            dismiss=True, stuck_timeout=None)
        assert result["hit"], result
        assert result["hit"][0] == "client", result
        assert not storage_dialog(host), {"result": result, "host": states(host)}
        assert storage_dialog(client), {"result": result, "client": states(client)}

        # Close only the error message. The mandatory SellState queued behind it
        # must remain and retain ClientBase as its target.
        while not any("SellState" in name for name in states(client)):
            dismissed = client.ok({"cmd": "dismiss_popup"})
            assert dismissed.get("handled") == "generic", dismissed
            client.wait_for("ClientBase sell state",
                            lambda: any("SellState" in name for name in states(client)) or None,
                            timeout=10)

        client_before = base(host, "ClientBase")["items"]
        host_before = base(host, "HostBase")["items"]
        sold_item = None
        for item, count in client_before.items():
            if count <= 0:
                continue
            result_sell = client.cmd({"cmd": "sell_open_item", "item": item, "count": 1})
            if result_sell.get("ok"):
                sold_item = item
                break
        assert sold_item, {"items": client_before, "states": states(client)}

        expected = client_before[sold_item] - 1
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
