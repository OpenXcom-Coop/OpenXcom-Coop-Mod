"""PvP campaigns keep main's two-world rules (PR #213 review F3, ruling RU11).

PvP campaigns are stored with campaign type Separate, but only the cooperative
game modes (0/1) use the new single host-authoritative world. PvP (game mode
2/3) keeps one independent world per player, exactly as on main:

  gm3 (host = aliens, client = X-COM):
    - the client is NOT a replica: its own world simulates, so research it
      starts at its own base makes progress;
    - the client's starting craft crew is not trimmed to a per-player quota;
    - no single-world profile/wallet is applied to the PvP world.
    - the alien host's mirror of the client's X-COM base detects a UFO right
      above it with X-COM's facilities (main's _facilitiesCoop radar data,
      which on main only the client sends).
  gm2 (host = X-COM, client = aliens):
    - the alien client's mirror of the X-COM base carries X-COM's radar range,
      so the alien side sees the radar circle (main's _radar_range_coop).

Run:  py -3 tools/coop_test/test_pvp_campaign_world_rules.py
Exit 0 = pass, 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import geo
import pvp_fixture as PVP

PORT_GM3 = "52190"
PORT_GM2 = "52191"


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def _base(gc, name):
    for base in gc.ok({"cmd": "geo_state"})["bases"]:
        if base["name"] == name:
            return base
    return None


def _soldiers(gc, base_name):
    for base in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if base["name"] == base_name:
            return base["soldiers"]
    return []


def check_gm3_client_world(fails):
    print("\n--- gm3: host = aliens, client = X-COM ---")
    host = GameClient("host", 52890, make_user_dir("pvp_rules3_host"))
    client = GameClient("client", 52891, make_user_dir("pvp_rules3_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        gm = PVP.start_pvp_campaign(host, client, PORT_GM3, alien_player="host")
        if gm != 3:
            _fail(fails, f"expected gamemode 3, got {gm}")
            return

        coop = client.ok({"cmd": "get_coop"})
        print(f"    client get_coop: serverOwner={coop.get('serverOwner')} "
              f"gamemode={coop.get('gamemode')} "
              f"campaignReplica={coop.get('campaignReplica')} "
              f"separateWorld={coop.get('separateWorld')}")
        if coop.get("campaignReplica") is True:
            _fail(fails, "gm3 client reports itself as a campaign replica")

        # ---- starting crew is the template crew, not a per-player quota ----
        roster = _soldiers(client, "XcomBase")
        on_craft = [s for s in roster if s.get("craft")]
        off_craft = [s for s in roster if not s.get("craft")]
        print(f"    client XcomBase soldiers={len(roster)} on craft={len(on_craft)} "
              f"owners={sorted({s['owner'] for s in roster})} "
              f"coop={sorted({s['coop'] for s in roster})}")
        if not on_craft:
            _fail(fails, "no starting soldier is on a craft; crew check is vacuous")
        elif off_craft:
            _fail(fails, f"gm3 client starting crew was trimmed: {len(off_craft)} "
                         f"of {len(roster)} soldiers lost their craft seat")
        else:
            print("PASS gm3 crew: every starting soldier keeps its craft seat")
        if any(s["owner"] != 999 for s in roster):
            _fail(fails, "gm3 client soldiers were re-seated to a campaign owner: "
                         f"{sorted({s['owner'] for s in roster})}")
        else:
            print("PASS gm3 soldiers: starting soldiers keep the unowned PvP id")

        # ---- no single-world player wallet in PvP ---------------------------
        for gc, label in ((host, "host"), (client, "client")):
            report = gc.ok({"cmd": "month_report"})
            print(f"    {label} month_report playerFunds={report.get('playerFunds')} "
                  f"funds={report.get('funds')}")
            if report.get("playerFunds"):
                _fail(fails, f"gm3 {label} has Separate player wallets in PvP: "
                             f"{report.get('playerFunds')}")

        # ---- the client's own world simulates ------------------------------
        topics = client.ok({"cmd": "available_research", "base": "XcomBase"})["topics"]
        if not topics:
            _fail(fails, "gm3 client has no available research topic")
            return
        topic = topics[0]
        r = client.cmd({"cmd": "research_start", "topic": topic,
                        "scientists": 10, "base": "XcomBase"})
        print(f"    client research_start {topic}: {r}")
        base = _base(client, "XcomBase")
        before = {p["name"]: p["spent"] for p in base["research"]}
        if topic not in before:
            _fail(fails, f"research {topic} did not start on the gm3 client: {before}")
            return
        geo.skip_ingame_time(host, client, minutes=60 * 24 * 3,
                             speed_idx=5, real_timeout=120)
        geo.slow_clock(host, client)
        after = {p["name"]: p["spent"] for p in _base(client, "XcomBase")["research"]}
        # A project's cost is rolled at 50-150 % of the rule's (STR_LASER_WEAPONS:
        # 50), so 10 scientists can finish it inside the 3 days. A finished project
        # leaves the list; its discovery is progress too.
        done = client.ok({"cmd": "is_researched", "topic": topic})["researched"]
        print(f"    client research spent: {before.get(topic)} -> {after.get(topic)} "
              f"(completed={done})")
        if not done and after.get(topic, 0) <= before.get(topic, 0):
            _fail(fails, "gm3 client world is frozen: its own research made no "
                         f"progress over 3 in-game days ({before} -> {after})")
        else:
            print("PASS gm3 client world simulates: research progressed")

        # ---- alien host: radar of its mirror of the X-COM base -------------
        mirror = host.wait_for(
            "X-COM mirror base on the alien host",
            lambda: _base(host, "XcomBase"), timeout=60, interval=0.5)
        print(f"    host mirror: coopBase={mirror.get('coopBase')} "
              f"coopIcon={mirror.get('coopIcon')} "
              f"radarRangeCoop={mirror.get('radarRangeCoop')}")
        ufo = host.ok({
            "cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
            "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
            "race": "STR_SECTOID", "trajectory": "P0", "state": "flying",
            "speed": 0, "lon": mirror["lon"], "lat": mirror["lat"]})
        deadline = time.time() + 30
        result = None
        while time.time() < deadline:
            result = host.ok({"cmd": "base_detect_trials", "base": "XcomBase",
                              "ufo_id": ufo["ufo_id"], "trials": 2000})
            if result["detected"] > 0:
                break
            time.sleep(1.0)
        print(f"    alien host detection from the X-COM mirror: {result}")
        if not result or result["detected"] == 0:
            _fail(fails, "gm3 alien host's mirror of the X-COM base has no radar")
        else:
            print("PASS gm3 radar: the X-COM mirror base detects with X-COM's radar")
    except Exception as e:
        print(f"[ERROR] gm3: {e!r}")
        _fail(fails, repr(e))
    finally:
        host.shutdown()
        client.shutdown()


def check_gm2_alien_radar(fails):
    print("\n--- gm2: host = X-COM, client = aliens ---")
    host = GameClient("host", 52892, make_user_dir("pvp_rules2_host"))
    client = GameClient("client", 52893, make_user_dir("pvp_rules2_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        gm = PVP.start_pvp_campaign(host, client, PORT_GM2, alien_player="client")
        if gm != 2:
            _fail(fails, f"expected gamemode 2, got {gm}")
            return

        mirror = client.wait_for(
            "X-COM mirror base on the alien client",
            lambda: _base(client, "XcomBase"), timeout=60, interval=0.5)
        # The mirror's radar range arrives with the periodic base-marker sync.
        deadline = time.time() + 30
        while time.time() < deadline and not mirror.get("radarRangeCoop"):
            time.sleep(1.0)
            mirror = _base(client, "XcomBase")
        print(f"    client mirror: coopBase={mirror.get('coopBase')} "
              f"coopIcon={mirror.get('coopIcon')} "
              f"radarRangeCoop={mirror.get('radarRangeCoop')}")
        if not mirror.get("radarRangeCoop"):
            _fail(fails, "gm2 alien client's mirror of the X-COM base has no radar range")
        else:
            print("PASS gm2 radar: the alien side sees the X-COM radar circle")
    except Exception as e:
        print(f"[ERROR] gm2: {e!r}")
        _fail(fails, repr(e))
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    check_gm3_client_world(fails)
    check_gm2_alien_radar(fails)
    print("\n==== PvP world rules summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  PvP keeps main's two-world rules")
    sys.exit(0)


if __name__ == "__main__":
    main()
