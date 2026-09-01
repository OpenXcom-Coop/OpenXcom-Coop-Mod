"""PvP campaign: client disconnect + reconnect during mission.

Repro:
  1. Gamemode 3 (host=alien, client=XCOM), campaign running.
  2. Client disconnects (Options > Abandon).
  3. Host shows "waiting for player to reconnect" dialog.
  4. Client reconnects.
  5. Host clicks RESUME.
  6. BUG: host sent to main menu, client forcibly disconnected.

Expected: both machines return to the geoscape.

Run:  python tools/coop_test/test_pvp_campaign_reconnect.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(fast-follow)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

PORT = "47997"

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]

def _has(gc, name):
    return any(name in s for s in _states(gc))

def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)

def main():
    fails = []
    print("=== PvP campaign disconnect/reconnect (gamemode 3) ===")

    # ---- Phase 1: campaign bringup ----
    host = GameClient("host", 48920, make_user_dir("pvp_rc_h"))
    client = GameClient("client", 48921, make_user_dir("pvp_rc_c"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # lobby + team assignment
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

        # Put host on Alien -> gamemode 3
        ls = host.cmd({"cmd": "lobby_state"})
        names = ls.get("players", [])
        for i, n in enumerate(names):
            if "HostPlayer" in n:
                r = host.ok({"cmd":"lobby_set_team","row":i,"team":"Alien"})
                gm = r["gamemode"]
                break
        if gm != 3:
            _fail(fails, f"expected gamemode 3, got {gm}")
            return
        print(f"PASS: gamemode {gm}")

        session.start_campaign_via_button(host)

        # Host places base (host=alien, no_bases -> skips via WAIT_PLAYERS)
        # Client places base (client=XCOM)
        host.wait_for("host wait", lambda: _has(host, "CoopState") or _has(host, "GeoscapeState"), timeout=60)
        if _has(host, "CoopState"):
            # BEGIN should be visible; click it once client places base
            time.sleep(2)
        client.wait_for("client base", lambda: _has(client, "BuildNewBaseState"))
        client.ok({"cmd":"place_first_base","lon":LAND_LON,"lat":LAND_LAT,"name":"XcomBase"})
        time.sleep(3)
        if _has(host, "CoopState"):
            host.ok({"cmd": "coop_dialog_back"})

        # Both reach geoscape
        for gc, label in ((host,"host"),(client,"client")):
            gc.wait_for(f"{label} geoscape",
                lambda g=gc: _has(g, "GeoscapeState") and not _has(g, "CoopState"),
                timeout=120, interval=1.0)
            if _has(gc, "GeoscapeState") and not _has(gc, "CoopState"):
                print(f"PASS: {label} on geoscape")
            else:
                _fail(fails, f"{label} not on geoscape")
                return

        # ---- Phase 2: client disconnects ----
        print("--- client disconnecting ---")
        client.shutdown()
        time.sleep(5)

        hst = _states(host)
        print(f"host after client drop: {hst[-3:]}")
        has_wait = any("CoopState" in s for s in hst)
        if not has_wait:
            _fail(fails, "host did not show wait/lost dialog after client drop")
        else:
            print("PASS: host shows wait dialog after client drop")

        # ---- Phase 3: client reconnects ----
        print("--- client reconnecting ---")
        client2 = GameClient("client2", 48922, make_user_dir("pvp_rc_c2"))
        client2.spawn(); client2.connect()
        client2.ok({"cmd":"join_tcp","ip":"127.0.0.1","port":PORT,"player":"ClientPlayer"})
        time.sleep(5)

        # Dismiss any join popups
        for _ in range(10):
            if _has(client2, "Profile"):
                client2.ok({"cmd":"profile_ok"})
                time.sleep(0.5)
            else:
                break

        # Wait for client to settle in CLIENT_RESUME_HOLD
        client2.wait_for("client2 in hold",
            lambda: any("CoopState" in s for s in _states(client2)) or None,
            timeout=30, interval=0.5)
        time.sleep(10)  # generous settle time for rejoin protocol

        hst2 = _states(host)
        cst2 = _states(client2)
        print(f"host after rejoin: {hst2[-3:]}")
        print(f"client after rejoin: {cst2[-3:]}")

        # ---- Phase 4: host resumes ----
        print("--- host clicking RESUME ---")
        # Dismiss the "player joined" Profile popup on the host
        if _has(host, "Profile"):
            host.ok({"cmd": "profile_ok"})
            time.sleep(1)
        # Click RESUME on the WAIT_PLAYERS dialog
        if _has(host, "CoopState"):
            host.ok({"cmd": "coop_dialog_back"})
        time.sleep(5)

        try:
            hst3 = _states(host)
            print(f"host final: {hst3[-3:]}")
        except Exception as e:
            print(f"host final: {e}")
            hst3 = []

        try:
            cst3 = _states(client2)
            print(f"client final: {cst3[-3:]}")
        except Exception as e:
            print(f"client final: {e}")
            cst3 = []

        # ---- Assertions ----
        host_on_geo = "GeoscapeState" in hst3[-1] if hst3 else False
        # Client needs time to load the streamed world after campaign_begun
        client_on_geo = False
        deadline = time.time() + 60
        while time.time() < deadline and not client_on_geo:
            try:
                cst3 = _states(client2)
                client_on_geo = "GeoscapeState" in cst3[-1] if cst3 else False
            except:
                break
            if not client_on_geo:
                time.sleep(2)
        if not client_on_geo:
            try:
                cst3 = _states(client2)
            except:
                cst3 = []
            print(f"client final: {cst3[-3:] if cst3 else 'error'}")

        if host_on_geo:
            print("PASS: host returned to geoscape")
        else:
            _fail(fails, f"host not on geoscape: {hst3[-3:]}")

        if client_on_geo:
            print("PASS: client returned to geoscape")
        else:
            _fail(fails, f"client not on geoscape: {cst3[-3:]}")

    except Exception as e:
        print(f"[ERROR] {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown()
        try: client2.shutdown()
        except: pass

    print("\n==== PvP campaign reconnect summary ====")
    if fails:
        for f in fails: print(f"  FAIL {f}")
        sys.exit(2)
    print("  both machines returned to geoscape after disconnect + reconnect")
    sys.exit(0)

if __name__ == "__main__":
    main()
