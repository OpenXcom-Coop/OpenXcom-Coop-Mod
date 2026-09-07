"""Coop multi-stage (next-stage) transition: the two machines must land in the
SAME stage-2 battle - same map, same units, same positions.

Follow-up to test_coop_nextstage_crash.py (#184, which only proved both
machines reach STR_ALIEN_COLONY_P2 without crashing). Player report on the
2.0.34 nightly:

    "we were able to get to the next stage in the base attack, but it was not
     working correctly. The client was seeing aliens where I (the host) saw
     nothing. In fact, I (the host) wasn't seeing any aliens at all."

So the discriminator here is a CENSUS COMPARE after the transition, not merely
"both are in stage 2":

  * live hostile count on host == on client
  * every unit id/faction/position identical on both
  * map fingerprint identical on both

Run:  python tools/coop_test/test_coop_nextstage_census.py
Exit 0 = pass; 2 = failure (census mismatch / crash / did not advance).

Env:
  NEXTSTAGE_DUMP=<dir>   write both machines' raw stage-2 censuses as JSON
  NEXTSTAGE_FINISH=1     after the census compare, also clear stage 2 and
                         assert both machines reach the debriefing/geoscape
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient
from tftd_common import make_tftd_user_dir
import session
import harness

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SAVE_SRC = os.environ.get("TFTD_SAVE") or os.path.join(FIX, "tftd_base_assault.sav")
SAVE = "tftd_base_assault.sav"
PORT = "47956"
DUMP = os.environ.get("NEXTSTAGE_DUMP")
FINISH = os.environ.get("NEXTSTAGE_FINISH") == "1"


def tftd_data_present():
    exe_dir = os.path.dirname(harness.EXE)
    return os.path.isdir(os.path.join(exe_dir, "TFTD", "GEODATA"))


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def proc_dead(gc):
    return gc.proc is not None and gc.proc.poll() is not None


def census(b):
    """(id, faction, coop, out, x, y, z) per unit, sorted by id."""
    rows = []
    for u in b.get("units", []):
        rows.append((u["id"], u["faction"], u.get("coop"), bool(u.get("isOut")),
                     u["x"], u["y"], u["z"]))
    return sorted(rows)


def hostiles(b):
    return sorted(u["id"] for u in b.get("units", [])
                  if u.get("faction") == 1 and not u.get("isOut"))


def fmt(rows, limit=200):
    return "\n".join("    id=%-4d f=%d coop=%s out=%s pos=(%d,%d,%d)" % r
                     for r in rows[:limit])


def dump(tag, b):
    if not DUMP:
        return
    os.makedirs(DUMP, exist_ok=True)
    with open(os.path.join(DUMP, "%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump(b, f, indent=1, sort_keys=True)


def main():
    if not tftd_data_present():
        print("SKIP: TFTD (xcom2) game data not staged next to the exe "
              "(no TFTD/GEODATA) - this repro is TFTD-only.")
        sys.exit(0)
    if not os.path.exists(SAVE_SRC):
        print(f"SKIP: fixture {SAVE_SRC} not found.")
        sys.exit(0)

    host_dir = make_tftd_user_dir("nsx_host", saves=[SAVE_SRC])
    client_dir = make_tftd_user_dir("nsx_client")
    host = GameClient("host", 47961, host_dir)
    client = GameClient("client", 47962, client_dir)
    fail = None
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=120); client.connect(timeout=120)
        session.resume_campaign_battle(host, client, SAVE, port=PORT, timeout=180)

        hb, cb = battle(host), battle(client)
        assert hb.get("missionType") == "STR_ALIEN_BASE_ASSAULT", \
            f"unexpected stage-1 mission {hb.get('missionType')}"
        print(f"stage 1: host mission={hb.get('missionType')} turn={hb.get('turn')} "
              f"units={len(hb.get('units', []))} | client units={len(cb.get('units', []))}")
        dump("stage1_host", hb); dump("stage1_client", cb)

        print("stage-1 live aliens: host=%s client=%s" % (hostiles(hb), hostiles(cb)))

        # --- drive the transition (same as the #184 regression test) ---------
        print("killing all remaining aliens on the HOST (faction=1)...")
        print("kill_unit_real ->",
              host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1}))
        host.wait_for("all aliens dead on host",
                      lambda: (not hostiles(battle(host))) or None,
                      timeout=30, interval=1.0)
        print("battle_autoend ->", host.cmd({"cmd": "battle_autoend"}))
        print("close_nextturn ->", host.cmd({"cmd": "close_nextturn"}))

        print("waiting for BOTH machines to enter stage 2 (STR_ALIEN_COLONY_P2)...")
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(1.5)
            for gc, tag in ((host, "host"), (client, "client")):
                if proc_dead(gc):
                    raise AssertionError(
                        f"{tag.upper()} CRASHED on next-stage transition: rc="
                        f"{gc.proc.returncode} (0x{gc.proc.returncode & 0xffffffff:08x})")
            hs = states(host)
            if not any("BattlescapeState" in s for s in hs):
                continue
            hb, cb = battle(host), battle(client)
            if (hb.get("missionType") == "STR_ALIEN_COLONY_P2" and hb.get("inBattle")
                    and cb.get("missionType") == "STR_ALIEN_COLONY_P2" and cb.get("inBattle")):
                break
        else:
            raise AssertionError(
                "machines did not both reach stage 2 within 120s: "
                f"host={battle(host).get('missionType')} "
                f"client={battle(client).get('missionType')}")

        # let the coop turn handshake settle before sampling
        time.sleep(6)
        hb, cb = battle(host), battle(client)
        dump("stage2_host", hb); dump("stage2_client", cb)
        print("beforeGame: host=%s client=%s" % (hb.get("beforeGame"), cb.get("beforeGame")))
        print(f"host  : mission={hb.get('missionType')} turn={hb.get('turn')} "
              f"battleInit={hb.get('battleInit')} coopTurn={hb.get('coopTurn')} "
              f"units={len(hb.get('units', []))} mapFp={hb.get('mapFingerprint')} "
              f"mapXYZ={hb.get('mapSizeXYZ')}")
        print(f"client: mission={cb.get('missionType')} turn={cb.get('turn')} "
              f"battleInit={cb.get('battleInit')} coopTurn={cb.get('coopTurn')} "
              f"units={len(cb.get('units', []))} mapFp={cb.get('mapFingerprint')} "
              f"mapXYZ={cb.get('mapSizeXYZ')}")

        # --- THE DISCRIMINATOR -----------------------------------------------
        h_hostiles, c_hostiles = hostiles(hb), hostiles(cb)
        print(f"stage-2 live aliens: host={h_hostiles}")
        print(f"stage-2 live aliens: client={c_hostiles}")

        problems = []
        if not h_hostiles:
            problems.append(
                "HOST HAS NO LIVE ALIENS in stage 2 (client has %d) - the player's "
                "'I wasn't seeing any aliens at all'" % len(c_hostiles))
        if h_hostiles != c_hostiles:
            problems.append("live-alien id sets differ: host=%s client=%s"
                            % (h_hostiles, c_hostiles))
        if hb.get("mapFingerprint") != cb.get("mapFingerprint"):
            problems.append("map fingerprints differ (different stage-2 maps): "
                            "host=%s client=%s"
                            % (hb.get("mapFingerprint"), cb.get("mapFingerprint")))
        hc, cc = census(hb), census(cb)
        if hc != cc:
            honly = [r for r in hc if r not in cc]
            conly = [r for r in cc if r not in hc]
            problems.append(
                "unit census differs (%d host-only, %d client-only rows)\n"
                "  host-only:\n%s\n  client-only:\n%s"
                % (len(honly), len(conly), fmt(honly), fmt(conly)))
        if problems:
            raise AssertionError("STAGE-2 DESYNC:\n  - " + "\n  - ".join(problems))

        print("PASS: stage-2 census matches on both machines "
              f"({len(h_hostiles)} live aliens, {len(hc)} units, same map)")

        # --- THE REAL SYMPTOM: fog of war / spotted aliens --------------------
        # Identical units at identical positions still leaves "the client sees
        # aliens where the host sees nothing" possible: what a player SEES is
        # BattleUnit::_visibleUnits + Tile discovery, neither of which travels in
        # the unit census. Drive past the "Turn 1" screen so the first real
        # player turn is live on both, then compare.
        print("\n== closing the stage-2 turn screen on both machines")
        for gc, tag in ((host, "host"), (client, "client")):
            st = states(gc)
            print(f"  {tag} stack: {[s.split('::')[-1] for s in st[-4:]]}")
            if any("NextTurnState" in s for s in st):
                print(f"  {tag} dismiss_popup ->", gc.cmd({"cmd": "dismiss_popup"}))
        time.sleep(6)
        hb, cb = battle(host), battle(client)
        dump("stage2_turn1_host", hb); dump("stage2_turn1_client", cb)
        for tag, b in (("host", hb), ("client", cb)):
            print(f"  {tag}: turn={b.get('turn')} side={b.get('side')} "
                  f"coopTurn={b.get('coopTurn')} discoveredFloor={b.get('mapDiscoveredFloor')} "
                  f"spotted={b.get('spotted')} beforeGame={b.get('beforeGame')}")
        vis = []
        if hb.get("turn") != cb.get("turn"):
            vis.append("turn counters differ: host=%s client=%s"
                       % (hb.get("turn"), cb.get("turn")))
        if not hb.get("spotted") and cb.get("spotted"):
            vis.append("HOST SPOTS NO ALIENS while the client spots %s - the "
                       "player's exact report" % cb.get("spotted"))
        if sorted(hb.get("spotted", [])) != sorted(cb.get("spotted", [])):
            vis.append("spotted-alien sets differ: host=%s client=%s"
                       % (hb.get("spotted"), cb.get("spotted")))
        if hb.get("mapDiscoveredFloor") != cb.get("mapDiscoveredFloor"):
            vis.append("discovered-floor counts differ (fog of war desync): "
                       "host=%s client=%s"
                       % (hb.get("mapDiscoveredFloor"), cb.get("mapDiscoveredFloor")))
        if census(hb) != census(cb):
            vis.append("unit census drifted apart once the turn started")
        # The mechanism, asserted directly: SavedBattleGame::_beforeGame. nextStage()
        # -> resetTurnCounter() raises it; only startFirstTurn()/resetUnitTiles()
        # clears it. While it is up TileEngine::calculateLineVoxel excludes every unit
        # from LOS, so the machine cannot spot anything. The client clears it for free
        # via SavedBattleGame::load(); the host has to be given the same finish.
        for tag, b in (("host", hb), ("client", cb)):
            if b.get("beforeGame"):
                vis.append("%s is still BEFORE GAME in stage 2 (startFirstTurn never "
                           "ran): no unit can be spotted there" % tag)
            if b.get("turn", 0) < 1:
                vis.append("%s stage-2 turn counter is %s, never started (turn >= 1 also "
                           "gates the host's click_close/next_turn coop packets)"
                           % (tag, b.get("turn")))
        if vis:
            raise AssertionError("STAGE-2 VISIBILITY DESYNC:\n  - " + "\n  - ".join(vis))
        print("PASS: stage-2 visibility matches on both machines "
              f"(spotted={hb.get('spotted')}, discoveredFloor={hb.get('mapDiscoveredFloor')})")

        if FINISH:
            finish_stage2(host, client)
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  {tag} states: {states(gc)[-4:]}")
            except Exception as ee:
                print(f"  {tag}: unreachable ({ee})")
    finally:
        host.shutdown(); client.shutdown()
    sys.exit(2 if fail else 0)


def finish_stage2(host, client):
    """Clear stage 2 and prove both machines get back out to the geoscape."""
    print("\n== finishing stage 2 (kill all aliens -> debrief -> geoscape)")
    print("kill_unit_real ->",
          host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1}))
    host.wait_for("stage-2 aliens dead on host",
                  lambda: (not hostiles(battle(host))) or None,
                  timeout=45, interval=1.0)
    print("battle_autoend ->", host.cmd({"cmd": "battle_autoend"}))
    print("close_nextturn ->", host.cmd({"cmd": "close_nextturn"}))

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} at debriefing",
                    lambda gc=gc: any("DebriefingState" in s for s in states(gc)) or None,
                    timeout=120, interval=2.0)
    print("both machines reached the debriefing")
    hd = host.cmd({"cmd": "debrief_state"})
    cd = client.cmd({"cmd": "debrief_state"})
    print("host debrief  :", {k: v for k, v in hd.items() if k != "ok"})
    print("client debrief:", {k: v for k, v in cd.items() if k != "ok"})

    # DebriefingState::btnOkClick (the real OK button) on both machines.
    for gc, tag in ((host, "host"), (client, "client")):
        print(f"{tag} dismiss_popup ->", gc.cmd({"cmd": "dismiss_popup"}))
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} back on the geoscape",
                    lambda gc=gc: (any("GeoscapeState" in s for s in states(gc))
                                   and not battle(gc).get("inBattle")) or None,
                    timeout=120, interval=2.0)
    print("PASS: both machines returned to the geoscape after stage 2")


if __name__ == "__main__":
    main()
