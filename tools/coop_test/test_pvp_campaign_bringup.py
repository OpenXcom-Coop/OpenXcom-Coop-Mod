"""PvP campaign bringup: validates the no_bases fix.

Gamemode 2 (client plays aliens):
  1. Host (XCOM) places base, waits for client blob, clicks BEGIN.
  2. Client (alien) skips base placement, enters CoopState hold.
  3. Both machines reach the geoscape.

Gamemode 3 (host plays aliens):
  1. Host (alien) skips base placement, enters CoopState wait.
  2. Client (XCOM) places base, pushes world blob.
  3. Host clicks BEGIN to release client hold.
  4. Both machines reach the geoscape.

Run:  python tools/coop_test/test_pvp_campaign_bringup.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

PORT = "47995"

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]

def _has(gc, name):
    return any(name in s for s in _states(gc))

def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)

def test_campaign_bringup(fails, alien_player, expect_mode):
    tag = f"gm{expect_mode}_{alien_player}"
    print(f"\n--- campaign {tag} ---")

    host = GameClient("host", 48900, make_user_dir(f"pvp_camp_{tag}_host"))
    client = GameClient("client", 48901, make_user_dir(f"pvp_camp_{tag}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # ---- lobby + team assignment ----
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

        # ---- XCOM player places base ----
        if _has(xcom_gc, "BuildNewBaseState"):
            xcom_gc.ok({"cmd":"place_first_base","lon":LAND_LON,"lat":LAND_LAT,"name":"XcomBase"})
            print(f"PASS {tag}: XCOM player placed base")
        else:
            if not _has(xcom_gc, "GeoscapeState"):
                _fail(fails, f"{tag}: XCOM player not on geoscape: {_states(xcom_gc)[-3:]}")
            print(f"PASS {tag}: XCOM player on geoscape")

        # ---- Alien player must NOT get base placement ----
        time.sleep(2)
        if _has(alien_gc, "BuildNewBaseState"):
            _fail(fails, f"{tag}: alien player got base prompt (no_bases not set)")
        else:
            print(f"PASS {tag}: alien player skipped base")

        # ---- host clicks BEGIN to release both machines to the geoscape ----
        if _has(host, "CoopState"):
            # WAIT_BASES always shows BEGIN (see CoopState::waitSatisfied).
            host.ok({"cmd": "coop_dialog_back"})

        # ---- both reach geoscape ----
        for gc, label in ((host,"host"),(client,"client")):
            gc.wait_for(f"{label} geoscape",
                        lambda g=gc: _has(g, "GeoscapeState") and not _has(g, "CoopState") or None,
                        timeout=120, interval=1.0)
            if _has(gc, "GeoscapeState") and not _has(gc, "CoopState"):
                print(f"PASS {tag}: {label} on geoscape")
            else:
                _fail(fails, f"{tag}: {label} not on geoscape: {_states(gc)[-3:]}")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown(); client.shutdown()

def main():
    fails = []
    test_campaign_bringup(fails, "client", 2)
    test_campaign_bringup(fails, "host", 3)

    print("\n==== PvP campaign bringup summary ====")
    if fails:
        for f in fails: print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: alien skips base, both reach geoscape")
    sys.exit(0)

if __name__ == "__main__":
    main()
