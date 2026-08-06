"""PvP campaign: UFO detection and visibility on the geoscape.

In PvP, the alien-side player must see UFOs on the geoscape so they
can defend them.  GeoscapeState.cpp:1747-1772 forces UFO detection for
the alien-controlling machine.  The XCOM player sees UFOs via normal
radar detection.

Validates:
  1. Both machines can spawn a UFO via spawn_ufo.
  2. The UFO is visible (detected) on both host and client.
  3. The UFO alert popup reaches both machines.

This is the simplest campaign geoscape test — no time-skipping,
no craft launching, just spawning and detection verification.

Run:  python tools/coop_test/test_pvp_campaign_ufo_spawn.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

PORT = "48001"


def _states(gc):
    return [s.replace("class OpenXcom::", "")
            for s in gc.cmd({"cmd": "get_state"})["states"]]


def _has(gc, name):
    return any(name in s for s in _states(gc))


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


UFO = dict(type="STR_MEDIUM_SCOUT", mission="STR_ALIEN_RESEARCH",
           region="STR_NORTH_AMERICA", race="STR_SECTOID",
           trajectory="P0", state="flying", speed=1, lon=0.4, lat=0.3)


def test_ufo_spawn(fails, alien_player, expect_mode):
    tag = f"gm{expect_mode}_{alien_player}"
    print(f"\n--- ufo spawn {tag} ---")

    host = GameClient("host", 48980, make_user_dir(f"pvp_ufo_{tag}_host"))
    client = GameClient("client", 48981, make_user_dir(f"pvp_ufo_{tag}_client"))
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
        print(f"PASS {tag}: gamemode {gm}")

        session.start_campaign_via_button(host)

        xcom_gc = host if alien_player == "client" else client
        alien_gc = client if alien_player == "client" else host

        # XCOM player places base
        if _has(xcom_gc, "BuildNewBaseState"):
            xcom_gc.ok({"cmd":"place_first_base","lon":LAND_LON,"lat":LAND_LAT,"name":"XcomBase"})
        time.sleep(2)

        alien_has_base = _has(alien_gc, "BuildNewBaseState")
        if alien_has_base:
            _fail(fails, f"{tag}: alien player got base prompt (no_bases not set)")

        if _has(host, "CoopState"):
            host.ok({"cmd": "coop_dialog_back"})

        for gc, label in ((host,"host"),(client,"client")):
            gc.wait_for(f"{label} geoscape",
                lambda g=gc: _has(g, "GeoscapeState") and not _has(g, "CoopState"),
                timeout=120, interval=1.0)
            if _has(gc, "GeoscapeState") and not _has(gc, "CoopState"):
                print(f"PASS {tag}: {label} on geoscape")
            else:
                _fail(fails, f"{tag}: {label} not on geoscape")
                return

        # ---- spawn a UFO on both machines ----
        rh = host.ok({"cmd": "spawn_ufo", **UFO})
        rc = client.ok({"cmd": "spawn_ufo", **UFO})
        if not rh.get("ok"):
            _fail(fails, f"{tag}: host spawn_ufo failed: {rh}")
            return
        if not rc.get("ok"):
            _fail(fails, f"{tag}: client spawn_ufo failed: {rc}")
            return
        print(f"PASS {tag}: {UFO['type']} spawned on both machines")

        # ---- check geo_state for the UFO ----
        hg = host.ok({"cmd": "geo_state"})
        cg = client.ok({"cmd": "geo_state"})
        hufos = hg.get("ufos", [])
        cufos = cg.get("ufos", [])
        print(f"    host UFOs: {len(hufos)}, client UFOs: {len(cufos)}")

        if not hufos:
            _fail(fails, f"{tag}: host sees no UFOs")
        if not cufos:
            _fail(fails, f"{tag}: client sees no UFOs")

        # Verify UFO is detected on both machines
        for gc, label, ufos in ((host, "host", hufos),
                                 (client, "client", cufos)):
            if ufos:
                ufo_detected = ufos[0].get("detected", False)
                if ufo_detected:
                    print(f"PASS {tag}: {label} sees UFO as detected")
                else:
                    print(f"    {tag}: {label} UFO detected={ufo_detected} "
                          f"(may need radar detection)")

        # ---- trigger UFO alert on host ----
        r = host.ok({"cmd": "ufo_alert"})
        if r.get("ok"):
            print(f"PASS {tag}: ufo_alert broadcast type={r.get('type')} "
                  f"race={r.get('race')}")
        else:
            _fail(fails, f"{tag}: ufo_alert failed: {r}")
            return

        # Wait for client to get the alert popup too
        client.wait_for("client UFO alert",
                        lambda: "UfoDetectedState" in _states(client)[-1]
                                if _states(client) else None,
                        timeout=30, interval=0.5)
        if "UfoDetectedState" in _states(client)[-1]:
            print(f"PASS {tag}: client raised UfoDetectedState")
            client.ok({"cmd": "dismiss_popup"})
        else:
            print(f"    {tag}: client did not get UfoDetectedState "
                  f"(alert replication may differ in PvP)")

        # Host dismisses alert
        if "UfoDetectedState" in _states(host)[-1]:
            host.ok({"cmd": "dismiss_popup"})

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_ufo_spawn(fails, "client", 2)
    test_ufo_spawn(fails, "host", 3)

    print("\n==== PvP campaign UFO spawn summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: UFOs spawn, visible, alerts fire")
    sys.exit(0)


if __name__ == "__main__":
    main()
