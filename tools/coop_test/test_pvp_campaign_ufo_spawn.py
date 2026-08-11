"""PvP campaign: natural UFO spawning on the geoscape.

In PvP, alien missions should spawn naturally as the geoscape sim runs.
The alien-controlling machine should see UFOs (forced detection).
The XCOM player should see them via radar.

This test advances time and checks for UFOs in geo_state, WITHOUT
using spawn_ufo (which force-creates a UFO bypassing the sim).

Validates (both gm2 host=XCOM and gm3 host=alien):
  1. Natural UFOs appear as time advances (no spawn_ufo involved).
  2. Both machines observe UFOs as the geoscape sim runs.

UFOs are transient, so detection runs at the MAX time step and gates on
the UNION of coop UFO ids each machine EVER sees across the window -- never
on an instantaneous count, which can sample the gap between two UFOs and
fail nondeterministically (the original flake: the peer saw UFOs while the
host's one-shot count read 0 a moment too early).

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
            # Drain popups after month roll (a few passes is enough; the UFO
            # accumulation loop below also auto-drains every tick).
            for gc in (host, client):
                for _ in range(4):
                    geo.drain_popups(gc)
                    time.sleep(0.2)
                gc.cmd({"cmd": "dismiss_popup"})

        # ---- advance at MAX speed and ACCUMULATE natural-UFO sightings ----
        # Natural UFOs are transient: each spawns, flies, may land, then leaves.
        # At the max time step (speed 5 = one game-DAY per tick) a single
        # instantaneous count can fall in the gap between two UFOs and read 0 even
        # though the alien sim IS producing them - that was the flake (the peer saw
        # UFOs while the host's one-shot count sampled a moment too early, so the
        # gate failed nondeterministically). The detection must survive the MAX
        # step, so keep speed 5 and gate on the UNION of coop UFO ids each machine
        # has EVER seen across the window, not on a UFO being airborne at one exact
        # instant. hufos0/cufos0 are the (zero) baselines captured above.
        print("    advancing (max speed) + accumulating UFO sightings...")
        host_seen, client_seen = set(), set()

        def _harvest():
            for gc, seen in ((host, host_seen), (client, client_seen)):
                for u in _geo(gc).get("ufos", []):
                    seen.add(u["coopId"])

        _harvest()
        roll_mp = _geo(host).get("monthsPassed", 0)
        start_min = geo.game_minutes(host) or 0
        t0 = time.time()
        while time.time() - t0 < 240:
            try:
                geo.skip_ingame_time(host, client, minutes=60 * 6,
                                     speed_idx=5, real_timeout=30)
            except Exception:
                break
            _harvest()
            # Stop as soon as BOTH machines have observed a natural UFO.
            if host_seen and client_seen:
                break
            now_min = geo.game_minutes(host) or start_min
            # Hard caps so an unlucky seed still terminates AND we never sit long
            # enough to cross the next month-end (avoids the month-end base-defense
            # UAF): stop after ~20 game-days or if a 2nd month rolls.
            if now_min - start_min > 20 * 24 * 60:
                break
            if _geo(host).get("monthsPassed", roll_mp) > roll_mp:
                break

        hseen, cseen = len(host_seen), len(client_seen)
        print(f"    UFO sightings accumulated: host={hseen} client={cseen}")

        if hseen > 0:
            print(f"PASS {tag}: host observed natural UFO(s) at max time step "
                  f"(ids={sorted(host_seen)})")
        else:
            _fail(fails, f"{tag}: no natural UFOs ever observed on host over the window")

        if cseen > 0:
            print(f"PASS {tag}: client observed natural UFO(s) at max time step")
        else:
            _fail(fails, f"{tag}: no natural UFOs ever observed on client over the window")

        # ---- P2/P7 desync gate: the role-aware no_bases guard must freeze only
        # the non-host alien machine. Identify the two machines by role:
        #   gm2 -> alien = client (getHost false, frozen); xcom = host (runs)
        #   gm3 -> alien = host   (getHost true, runs);     xcom = client (runs)
        alien_gc = client if alien_player == "client" else host
        xcom_gs = _geo(xcom_gc)
        alien_gs = _geo(alien_gc)

        # (1) gm2 only: the alien CLIENT (getHost==false) must self-generate ZERO
        # UFOs. With the guard removed it ran determineAlienMissions on the month
        # roll and spun up its own alien world -> desync. coop==false marks a real
        # self-UFO; coop==true is a mirror of the peer's UFO.
        if expect_mode == 2:
            self_ufos = [u for u in alien_gs.get("ufos", []) if not u["coop"]]
            if self_ufos:
                _fail(fails, f"{tag}: alien client self-generated UFOs: "
                             f"{[u['id'] for u in self_ufos]}")
            else:
                print(f"PASS {tag}: alien client has zero self-generated UFOs")

        # (2) both modes: every real UFO on the XCOM machine must be mirrored on
        # the alien machine. Join on coopId (the shared cross-machine id); use the
        # coop flag (not coopId) as the real/mirror selector. Set equality.
        xcom_real = {u["coopId"] for u in xcom_gs.get("ufos", []) if not u["coop"]}
        alien_mirror = {u["coopId"] for u in alien_gs.get("ufos", []) if u["coop"]}
        if xcom_real == alien_mirror:
            print(f"PASS {tag}: UFO sets match ({len(xcom_real)} real == mirror)")
        else:
            _fail(fails, f"{tag}: UFO set mismatch: "
                         f"xcom_only={xcom_real - alien_mirror}, "
                         f"alien_only={alien_mirror - xcom_real}")

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
