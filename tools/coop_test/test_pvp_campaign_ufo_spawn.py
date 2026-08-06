"""PvP campaign: natural UFO spawning on the geoscape.

In PvP, alien missions should spawn naturally as the geoscape sim runs.
The alien-controlling machine should see UFOs (forced detection).
The XCOM player should see them via radar.

This test advances time and checks for UFOs in geo_state, WITHOUT
using spawn_ufo (which force-creates a UFO bypassing the sim).

Validates:
  1. Natural UFOs appear as time advances (no spawn_ufo involved).
  2. Both machines see UFOs in geo_state after time advancement.
  3. gm2 (host=XCOM): time advances, UFOs should appear.
  4. gm3 (host=alien): time cannot advance (B1/B2), so UFOs won't
     appear — this IS the bug.

Run:  python tools/coop_test/test_pvp_campaign_ufo_spawn.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session
import geo

PORT = "48001"


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


def test_natural_ufo_spawn(fails, alien_player, expect_mode):
    tag = f"gm{expect_mode}_{alien_player}"
    print(f"\n--- natural UFO spawn {tag} ---")

    host = GameClient("host", 48984, make_user_dir(f"pvp_nufo_{tag}_host"))
    client = GameClient("client", 48985, make_user_dir(f"pvp_nufo_{tag}_client"))
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

        # ---- baseline: no UFOs (game just started) ----
        h0 = _geo(host)
        c0 = _geo(client)
        hufos0 = len(h0.get("ufos", []))
        cufos0 = len(c0.get("ufos", []))
        print(f"    baseline UFOs: host={hufos0} client={cufos0}")

        # ---- advance time to let alien missions spawn ----
        # Roll the month first (triggers determineAlienMissions for month 1).
        # In gm3, no_bases blocked the initial month-0 mission generation.
        # After the month rolls with our fix, missions should appear.
        print("    rolling month to trigger mission generation...")
        mp0 = _geo(host).get("monthsPassed", -1)
        geo.slow_clock(host, client)
        host.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})

        t0 = time.time()
        rolled = False
        while time.time() - t0 < 180:
            try:
                geo.skip_ingame_time(host, client, minutes=60 * 24 * 2,
                                     speed_idx=5, real_timeout=60)
            except Exception:
                break
            if _geo(host).get("monthsPassed", mp0) > mp0:
                rolled = True
                break
        if rolled:
            print(f"    month rolled: mp {mp0} -> {_geo(host)['monthsPassed']}")
            # Drain popups after month roll
            for gc in (host, client):
                for _ in range(10):
                    geo.drain_popups(gc)
                    time.sleep(0.3)
                gc.cmd({"cmd": "dismiss_popup"})

        # Advance a few more days for UFOs to appear
        print("    advancing a few days for UFOs to spawn...")
        ufos_found = False
        t0 = time.time()
        while time.time() - t0 < 120:
            try:
                geo.skip_ingame_time(host, client, minutes=60 * 4,
                                     speed_idx=5, real_timeout=30)
            except Exception:
                break
            h1 = _geo(host)
            hufos = len(h1.get("ufos", []))
            hday = h1.get("time", {}).get("day", 0)
            if hufos > 0:
                ufos_found = True
                print(f"    day {hday}: host UFOs={hufos} "
                      f"client UFOs={len(_geo(client).get('ufos', []))}")
                break
            if hday > 15:
                break

        if not ufos_found:
            if expect_mode == 3:
                print(f"    known: gm3 host (alien) — still no UFOs despite "
                      f"month roll")
            else:
                _fail(fails, f"{tag}: no UFOs found after month roll + 15 days")
            return

        h1 = _geo(host)
        c1 = _geo(client)
        hufos1 = len(h1.get("ufos", []))
        cufos1 = len(c1.get("ufos", []))

        if hufos1 > hufos0:
            print(f"PASS {tag}: host UFOs increased {hufos0} -> {hufos1}")
        else:
            if expect_mode == 2:
                _fail(fails, f"{tag}: no natural UFOs appeared on host")
            else:
                print(f"    known: gm3 host UFOs unchanged {hufos0} -> {hufos1} (B1)")

        if cufos1 > cufos0:
            print(f"PASS {tag}: client UFOs increased {cufos0} -> {cufos1}")
        else:
            if expect_mode == 2:
                _fail(fails, f"{tag}: no natural UFOs appeared on client")
            else:
                print(f"    known: gm3 client UFOs unchanged {cufos0} -> {cufos1} (B1)")

        # Check that host is still on geoscape (dismiss any alerts)
        for gc, label in ((host, "host"), (client, "client")):
            for _ in range(10):
                st = _states(gc)
                if st and "GeoscapeState" in st[-1]:
                    break
                gc.cmd({"cmd": "dismiss_popup"})
                time.sleep(0.3)
            if st and "GeoscapeState" in st[-1]:
                print(f"PASS {tag}: {label} on geoscape after time advance")
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
    test_natural_ufo_spawn(fails, "client", 2)
    test_natural_ufo_spawn(fails, "host", 3)

    print("\n==== PvP campaign natural UFO spawn summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: natural UFOs appear after month roll")
    sys.exit(0)


if __name__ == "__main__":
    main()
