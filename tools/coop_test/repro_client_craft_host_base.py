"""Repro: a SEPARATE client's craft keeps flying while the host sits in a base view.

Player report (2026-10-09, X-Com Files 3.9, nightly 12cfcfb54, SEPARATE): "when
client's car is on its way to a mission the car keeps moving towards target
location when host goes to base management - clock stops but vehicle keeps
moving slowly."

Scenario (vanilla data, SEPARATE campaign):
  1. Fresh SEPARATE coop campaign, both players on the geoscape.
  2. The client spawns a mission site far from its base and craft_force's its
     first craft out towards it (huge fuel, so it never turns back).
  3. Phase A: both players on the geoscape at speed idx 1 (1 min).
  4. Phase B: the host opens its BasescapeState (open_screen basescape), so the
     host GeoscapeState stops thinking and its clock stops.
  5. Phase C: the host leaves the base; both back at speed idx 1.

Every 0.5 s it samples the host clock, the client clock and the client craft's
lon/lat (plus the host's mirror of that craft) and prints per-phase totals.

Exit 0 = the client craft did not move while the host clock was frozen;
exit 2 = it moved (the report reproduced); exit 3 = a precondition failed.
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import geo  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

PORT = "47731"
SPEED = 1          # 1 min per tick on both machines in phases A and C
PHASE_S = {"A": 12.0, "B": 20.0, "C": 10.0}


def gs(gc):
    return gc.ok({"cmd": "geo_state"})


def own_base(g):
    for b in g["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    return None


def gmin(t):
    return geo._abs_minutes(t)


def dist(a, b):
    """Great-circle angle (rad) between two (lon, lat) points."""
    (lo1, la1), (lo2, la2) = a, b
    c = (math.sin(la1) * math.sin(la2)
         + math.cos(la1) * math.cos(la2) * math.cos(lo1 - lo2))
    return math.acos(max(-1.0, min(1.0, c)))


def find_craft(g, cid, coop):
    for b in g["bases"]:
        for c in b.get("crafts", []):
            if c["id"] == cid and bool(c["coop"]) == coop:
                return c
    return None


def sample(host, client, cid):
    hg, cg = gs(host), gs(client)
    cc = find_craft(cg, cid, coop=False)
    hc = find_craft(hg, cid, coop=True)
    return {
        "t": time.time(),
        "host_min": gmin(hg["time"]), "host_time": hg["time"],
        "client_min": gmin(cg["time"]), "client_time": cg["time"],
        "craft": (cc["lon"], cc["lat"]) if cc else None,
        "craft_status": cc["status"] if cc else None,
        "mirror": (hc["lon"], hc["lat"]) if hc else None,
        "host_top": geo.top_state(host).split("::")[-1],
        "client_top": geo.top_state(client).split("::")[-1],
    }


def fmt_t(t):
    return "%02d-%02d %02d:%02d" % (t["month"], t["day"], t["hour"], t["minute"])


def run_phase(name, host, client, cid, seconds, apply_speed):
    rows = []
    t_end = time.time() + seconds
    while time.time() < t_end:
        if apply_speed:
            for gc in (host, client):
                if geo.on_geoscape(gc):
                    gc.cmd({"cmd": "geo_set_speed", "idx": SPEED})
        else:
            # the client keeps its own speed; only the host is in the base view
            if geo.on_geoscape(client):
                client.cmd({"cmd": "geo_set_speed", "idx": SPEED})
        s = sample(host, client, cid)
        rows.append(s)
        print("  [%s %5.1fs] host=%s client=%s craft=%s mirror=%s top=%s/%s" % (
            name, s["t"] - rows[0]["t"], fmt_t(s["host_time"]), fmt_t(s["client_time"]),
            ("(%.5f,%.5f)" % s["craft"]) if s["craft"] else None,
            ("(%.5f,%.5f)" % s["mirror"]) if s["mirror"] else None,
            s["host_top"], s["client_top"]))
        time.sleep(0.5)
    first, last = rows[0], rows[-1]
    moved = dist(first["craft"], last["craft"]) if first["craft"] and last["craft"] else None
    mmoved = dist(first["mirror"], last["mirror"]) if first["mirror"] and last["mirror"] else None
    summary = {
        "phase": name,
        "real_s": round(last["t"] - first["t"], 1),
        "host_game_min": last["host_min"] - first["host_min"],
        "client_game_min": last["client_min"] - first["client_min"],
        "craft_rad": moved,
        "mirror_rad": mmoved,
        "host_tops": sorted({r["host_top"] for r in rows}),
        "client_tops": sorted({r["client_top"] for r in rows}),
    }
    return summary


def main():
    host = GameClient("host", 0, make_user_dir("ccb_host"))
    client = GameClient("client", 0, make_user_dir("ccb_client"))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    results = []
    verdict = 3
    try:
        session.new_campaign(host, client, port=PORT)
        geo.wait_both_ready(host, client)
        geo.slow_clock(host, client)
        for gc in (host, client):
            geo.drain_popups(gc)

        cg = gs(client)
        cb = own_base(cg)
        if not cb or not cb["crafts"]:
            print("PRECONDITION: client has no own base/craft:", cb)
            return 3
        craft = next((c for c in cb["crafts"] if "SKYRANGER" in c["type"]), cb["crafts"][0])
        cid = craft["id"]
        site = client.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                          "deployment": "STR_TERROR_MISSION", "lon": cb["lon"] + 2.5,
                          "lat": cb["lat"], "race": "STR_SECTOID", "hours": 240})["site_id"]
        r = client.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                       "lon": cb["lon"] + 0.05, "lat": cb["lat"], "dest": f"site:{site}",
                       "fuel": 999999, "lowFuel": False})
        print("client craft %d (%s) -> site %d: %s" % (cid, craft["type"], site, r.get("displayStatus")))

        results.append(run_phase("A", host, client, cid, PHASE_S["A"], apply_speed=True))

        host.ok({"cmd": "open_screen", "screen": "basescape"})
        host.wait_for("host basescape", lambda: geo.top_state(host).endswith("BasescapeState") or None,
                      timeout=10, interval=0.2)
        time.sleep(1.5)  # past the 1 s heartbeat grace, so phase B is the steady state
        results.append(run_phase("B", host, client, cid, PHASE_S["B"], apply_speed=False))

        host.ok({"cmd": "leave_base"})
        host.wait_for("host geoscape", lambda: geo.on_geoscape(host) or None, timeout=10, interval=0.2)
        results.append(run_phase("C", host, client, cid, PHASE_S["C"], apply_speed=True))

        print("==== SUMMARY ====")
        for s in results:
            print("  phase %s: real %.1fs host +%d game-min client +%d game-min "
                  "client craft moved %s rad host mirror moved %s rad host_tops=%s client_tops=%s" % (
                      s["phase"], s["real_s"], s["host_game_min"], s["client_game_min"],
                      "%.5f" % s["craft_rad"] if s["craft_rad"] is not None else None,
                      "%.5f" % s["mirror_rad"] if s["mirror_rad"] is not None else None,
                      s["host_tops"], s["client_tops"]))
        b = results[1]
        if b["host_tops"] != ["BasescapeState"]:
            print("PRECONDITION: host left the base view during phase B")
            return 3
        if b["craft_rad"] is None:
            print("PRECONDITION: client craft not sampled in phase B")
            return 3
        if b["host_game_min"] == 0 and b["craft_rad"] > 1e-6:
            print("REPRODUCED: host clock frozen (+0 game-min) but the client craft moved %.5f rad in %.1fs"
                  % (b["craft_rad"], b["real_s"]))
            verdict = 2
        else:
            print("NOT REPRODUCED: host +%d game-min, client craft moved %.5f rad"
                  % (b["host_game_min"], b["craft_rad"]))
            verdict = 0
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        print("alive:", alive)
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return verdict


if __name__ == "__main__":
    sys.exit(main())
