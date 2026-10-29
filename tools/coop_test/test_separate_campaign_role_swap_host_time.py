"""A process that played as a client can later host a live campaign.

Regression: the client seat is recorded in the process-wide
coop_save_owner_player_id. If it survives the return to the main menu, and
isCampaignReplica() treats any value above zero as a replica even on the
server owner, the same process then hosts a new campaign whose Geoscape
clock never advances, because the host thinks it is a replica. A new
Separate campaign happens to overwrite the value when the host reads the
client's bootstrap base, so the second session is SHARED, which has no such
transfer and exposes the stale seat directly.

Flow:
  1. A hosts, B joins as client (B's seat becomes 1).
  2. Both return to the main menu.
  3. B hosts a new SHARED campaign and A joins as its client.
  4. B's Geoscape clock must advance at speed, and B must not report itself
     as a replica.

Run:  py -3 tools/coop_test/test_separate_campaign_role_swap_host_time.py
Exit 0 = pass.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session


def clock(gc):
    value = gc.ok({"cmd": "geo_state"})["time"]
    return tuple(value[key] for key in ("year", "month", "day", "hour", "minute"))


def to_main_menu(gc):
    gc.ok({"cmd": "disconnect_to_menu"})
    gc.wait_for("main menu", lambda: (
        session.states(gc) and "MainMenuState" in session.states(gc)[-1]) or None,
        timeout=60, interval=0.25)


def main():
    a = GameClient("A", 52880, make_user_dir("sep_roleswap_a"))
    b = GameClient("B", 52881, make_user_dir("sep_roleswap_b"))
    try:
        for gc in (a, b):
            gc.spawn()
        for gc in (a, b):
            gc.connect()

        # ---- session 1: A hosts, B is the client --------------------------
        session.new_campaign(a, b, port="52180",
                             host_name="FirstHost", client_name="FirstClient")
        first = b.ok({"cmd": "get_coop"})
        print(f"session 1 client: serverOwner={first.get('serverOwner')} "
              f"localSeat={first.get('localSeat')} "
              f"saveOwnerId={first.get('saveOwnerId')}")
        assert first.get("serverOwner") is False, first

        # ---- both return to the main menu -----------------------------------
        to_main_menu(b)
        to_main_menu(a)
        menu = b.ok({"cmd": "get_coop"})
        print(f"B at main menu: saveOwnerId={menu.get('saveOwnerId')}")
        if "saveOwnerId" in menu:
            assert menu["saveOwnerId"] == 0, (
                "the client seat survived the main-menu teardown: " + repr(menu))

        # ---- session 2: B hosts, A is the client ----------------------------
        session.new_campaign(b, a, port="52181", campaign_mode="shared",
                             host_name="SecondHost", client_name="SecondClient")
        second = b.ok({"cmd": "get_coop"})
        print(f"session 2 host: serverOwner={second.get('serverOwner')} "
              f"localSeat={second.get('localSeat')} "
              f"saveOwnerId={second.get('saveOwnerId')} "
              f"campaignReplica={second.get('campaignReplica')}")
        assert second.get("serverOwner") is True, second
        assert second.get("localSeat") == 0, second
        if "campaignReplica" in second:
            assert second["campaignReplica"] is False, second

        b.ok({"cmd": "geo_set_speed", "idx": 4})
        time.sleep(1.0)
        before = clock(b)
        time.sleep(4.0)
        after = clock(b)
        print(f"B host clock: {before} -> {after}")
        assert after != before, (
            "the new host's Geoscape clock is frozen after it played as a "
            f"client: {before} -> {after}")
        print("PASS role swap: a former Separate client hosts a SHARED campaign "
              "whose clock advances")
    finally:
        a.shutdown()
        b.shutdown()


if __name__ == "__main__":
    main()
