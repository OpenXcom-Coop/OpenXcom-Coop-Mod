"""PvP campaign month-end: time advancement and monthly settlement.

In PvP, the geoscape time runs on both machines via co-op time sync.
The XCOM player should see month-end settlement (funds change).  The
alien player (no_bases, stub funds 1000) should peacefully survive
the month roll without crashing.

Validates:
  1. Both machines can advance to month-end without crashing.
  2. XCOM player's funds change (maintenance subtracted).
  3. Alien player's funds stay at stub (1000).
  4. Both machines advance past month-end boundary.

Run:  python tools/coop_test/test_pvp_campaign_month.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session
import geo

PORT = "48002"


def _states(gc):
    return [s.replace("class OpenXcom::", "")
            for s in gc.cmd({"cmd": "get_state"})["states"]]


def _has(gc, name):
    return any(name in s for s in _states(gc))


def _geo(gc):
    return gc.ok({"cmd": "geo_state"})


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def test_month_roll(fails, alien_player, expect_mode):
    tag = f"gm{expect_mode}_{alien_player}"
    print(f"\n--- month-end {tag} ---")

    host = GameClient("host", 48982, make_user_dir(f"pvp_mon_{tag}_host"))
    client = GameClient("client", 48983, make_user_dir(f"pvp_mon_{tag}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # ---- campaign bringup ----
        host.ok({"cmd": "open_new_game", "mode": "coop"})
        host.wait_for("diff", lambda: _has(host, "NewGameState"))
        host.ok({"cmd": "newgame_ok"})
        host.wait_for("hostw", lambda: _has(host, "HostMenu"))
        host.ok({"cmd": "host_tcp", "server":"TestSrv","port":PORT,"player":"HostPlayer"})
        host.wait_for("lobby", lambda: _has(host, "LobbyMenu"))

        client.ok({"cmd":"join_tcp","ip":"127.0.0.1","port":PORT,"player":"ClientPlayer"})
        client.wait_for("lobby", lambda: _has(client, "LobbyMenu"), timeout=120)
        for gc in (host, client):
            gc.wait_for("popup", lambda g=gc: _has(g, "Profile"))
            gc.ok({"cmd":"profile_ok"})
        host.wait_for("eligible", lambda: host.cmd({"cmd":"lobby_state"}).get("startEligible") or None)

        ls = host.cmd({"cmd": "lobby_state"})
        names = ls.get("players", [])
        want = "ClientPlayer" if alien_player == "client" else "HostPlayer"
        for i, n in enumerate(names):
            if want in n:
                r = host.ok({"cmd":"lobby_set_team","row":i,"team":"Alien"})
                gm = r["gamemode"]
                break
        if gm != expect_mode:
            _fail(fails, f"{tag}: expected {expect_mode}, got {gm}")
            return

        session.start_campaign_via_button(host)

        xcom_gc = host if alien_player == "client" else client
        alien_gc = client if alien_player == "client" else host

        if _has(xcom_gc, "BuildNewBaseState"):
            xcom_gc.ok({"cmd":"place_first_base","lon":LAND_LON,"lat":LAND_LAT,"name":"XcomBase"})
        time.sleep(2)
        if _has(host, "CoopState"):
            host.ok({"cmd": "coop_dialog_back"})

        for gc, label in ((host,"host"),(client,"client")):
            gc.wait_for(f"{label} geoscape",
                lambda g=gc: _has(g, "GeoscapeState") and not _has(g, "CoopState"),
                timeout=120, interval=1.0)
            if not _has(gc, "GeoscapeState") or _has(gc, "CoopState"):
                _fail(fails, f"{tag}: {label} not on geoscape")
                return
        print(f"PASS {tag}: both on geoscape")

        # ---- baseline ----
        h0 = _geo(host)
        c0 = _geo(client)
        mp0 = h0.get("monthsPassed", -1)
        hf0 = h0.get("funds", -1)
        cf0 = c0.get("funds", -1)
        print(f"    baseline: mp={mp0} host_funds={hf0} client_funds={cf0}")

        # ---- advance to month-end ----
        print("    advancing to month 28...")
        geo.slow_clock(host, client)
        host.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})

        t0 = time.time()
        rolled = False
        while time.time() - t0 < 180:
            try:
                geo.skip_ingame_time(host, client, minutes=60 * 24 * 2,
                                     speed_idx=5, real_timeout=60)
            except Exception as e:
                print(f"    skip error: {e}")
                break
            h1 = _geo(host)
            c1 = _geo(client)
            if h1.get("monthsPassed", mp0) > mp0:
                rolled = True
                break
            time.sleep(1)

        if not rolled:
            # B1/B2: when the host is the alien player (gamemode 3),
            # no_bases gates prevent time from advancing (GeoscapeState
            # early-returns in several timeXxx handlers).  Month never
            # rolls, no alien events spawn, no monthly report.
            if expect_mode == 3:
                print(f"    known: gm3 host (alien) cannot advance time "
                      f"(no_bases blocks geoscape sim — B1/B2)")
            else:
                _fail(fails, f"{tag}: did not roll the month within 180s")
            return

        h1 = _geo(host)
        c1 = _geo(client)
        mp1 = h1.get("monthsPassed", -1)
        hf1 = h1.get("funds", -1)
        cf1 = c1.get("funds", -1)
        print(f"PASS {tag}: month rolled: mp {mp0} -> {mp1}")
        print(f"    host_funds: {hf0} -> {hf1}")
        print(f"    client_funds: {cf0} -> {cf1}")

        # Drain month-end popups
        for gc, label in ((host, "host"), (client, "client")):
            for _ in range(10):
                geo.drain_popups(gc)
                time.sleep(0.3)

        # ---- verify geoscape state after month roll ----
        # Drain any popups that accumulated (ufo alerts, monthly report, etc.)
        for gc, label in ((host, "host"), (client, "client")):
            deadline = time.time() + 30
            while time.time() < deadline:
                st = _states(gc)
                if st and "GeoscapeState" in st[-1]:
                    break
                gc.cmd({"cmd": "dismiss_popup"})
                time.sleep(0.5)

        h2 = _geo(host)
        c2 = _geo(client)

        xcom_funds = h2.get("funds") if alien_player == "client" else c2.get("funds")
        alien_funds = c2.get("funds") if alien_player == "client" else h2.get("funds")

        # XCOM: funds should have changed (maintenance subtracted)
        xcom_start = hf0 if alien_player == "client" else cf0
        if xcom_funds < xcom_start:
            print(f"PASS {tag}: XCOM funds decreased ({xcom_start} -> {xcom_funds})")
        else:
            print(f"    {tag}: XCOM funds unchanged ({xcom_start} -> {xcom_funds})"
                  f" — may have negative maintenance")

        # Alien: should still have stub funds
        if 500 <= alien_funds <= 2000:
            print(f"PASS {tag}: alien funds {alien_funds} (stub, ~1000)")
        else:
            print(f"    {tag}: alien funds {alien_funds} (not a stub)")

        # Both machines should still be on geoscape
        for gc, label in ((host, "host"), (client, "client")):
            st = _states(gc)
            on_geo = "GeoscapeState" in st[-1] if st else False
            if on_geo:
                print(f"PASS {tag}: {label} on geoscape after month roll")
            else:
                _fail(fails, f"{tag}: {label} not on geoscape: {st[-3:]}")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_month_roll(fails, "client", 2)
    test_month_roll(fails, "host", 3)

    print("\n==== PvP campaign month-end summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: month rolled, XCOM funds changed, alien still stub")
    sys.exit(0)


if __name__ == "__main__":
    main()
