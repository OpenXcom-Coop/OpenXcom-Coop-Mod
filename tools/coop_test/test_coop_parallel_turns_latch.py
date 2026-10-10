"""Regression test: the host's parallel-turns choice holds for every battle in the session.

Finding (2026-10-10, origin/main 12cfcfb54): on a fresh SEPARATE campaign the session
host's connectionTCP::_enable_parallel_turns dropped 1 -> 0 right after the COOP_READY
handshake, when a world loaded from a blob written before the flag latched. A battle the
CLIENT's craft started then ran in classic alternating turns (parallelEnabled false on
both machines, so the parallel sync check never ran). A battle the host's craft started
re-latched the flag, and a resumed save kept it.

Rows (each a fresh campaign, both machines enter the battle and settle on the map):
  S1 SEPARATE, host and client both set parallel turns on, the CLIENT's craft lands.
  S2 SEPARATE, both on, the HOST's craft lands.
  S3 SEPARATE, host OFF and client on, the client's craft lands: the host's choice
     (classic) must hold, not the client's.
  H1 SHARED, both on, the host lands the shared craft.
A row passes when parallelEnabled and parallelActive on BOTH machines equal the host's
option once both are on the battlescape.

  * PASS (exit 0) / FAIL (exit 2: a row failed or a process crashed) /
    FAIL (exit 3: a precondition never held).

Env (optional): COOP_PTL_ROWS = "S1,S2,S3,H1" subset.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, HERE)
import session  # noqa: E402
import geo  # noqa: E402
import shared_fixture  # noqa: E402
import test_shared_parallel_campaign as SPC  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

ON = {"EnableCoopParallelTurns": True}
OFF = {"EnableCoopParallelTurns": False}


class Inconclusive(Exception):
    pass


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def has(gc, name):
    return any(name in s for s in states(gc))


def top(gc):
    return states(gc)[-1].split("::")[-1]


def base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise Inconclusive(gc.name + ": no own base")


def flags(gc):
    """In-battle readout: the session flag and whether the parallel side is live."""
    ps = gc.cmd({"cmd": "parallel_state"})
    return {"enabled": bool(ps.get("parallelEnabled")), "active": bool(ps.get("parallelActive"))}


def geo_flag(gc):
    """The session flag on the geoscape (parallel_state answers only in a battle)."""
    return gc.ok({"cmd": "get_coop"}).get("parallelEnabled")


# ---- battle entry --------------------------------------------------------------

def separate_landing(host, client, lander):
    """Fly the lander's first craft to a fresh terror site and confirm the coop landing."""
    b0 = base0(lander)
    if not b0["crafts"]:
        raise Inconclusive(lander.name + ": no craft")
    cid = b0["crafts"][0]["id"]
    site = lander.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                      "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                      "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    lander.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
               "lat": b0["lat"] + 0.10, "dest": f"site:{site}", "fuel": 999999, "lowFuel": False})

    def landing():
        if has(lander, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            t = states(gc)[-1]
            if "CoopState" in t:
                gc.cmd({"cmd": "coop_dialog_back"})
            elif "GeoscapeState" not in t:
                gc.cmd({"cmd": "dismiss_popup"})
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    lander.wait_for("landing prompt", landing, timeout=120, interval=0.5)
    lander.ok({"cmd": "coop_mission_start"})


def through_inventory(host, client):
    """Both machines: briefing -> pre-battle inventory -> OK; settle on the tactical map."""
    for gc in (host, client):
        gc.wait_for(gc.name + " in battle",
                    lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        gc.wait_for(gc.name + " briefing", lambda gc=gc: has(gc, "BriefingState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        gc.wait_for(gc.name + " inventory", lambda gc=gc: has(gc, "InventoryState") or None,
                    timeout=120, interval=0.5)
    for gc in (host, client):
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(30):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)):
            return
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    raise Inconclusive("both machines never settled on the battlescape: "
                       f"{[top(gc) for gc in (host, client)]}")


# ---- the verdict -----------------------------------------------------------------

def verdict(host, client, expected, geo_flags):
    got = {gc.name: flags(gc) for gc in (host, client)}
    bs = {gc.name: bool(gc.cmd({"cmd": "battle_state"}).get("parallelEnabled")) for gc in (host, client)}
    ok = all(f["enabled"] == expected and f["active"] == expected for f in got.values()) \
        and all(v == expected for v in bs.values())
    detail = (f"expected {expected}; battle parallel_state {got}; battle_state.parallelEnabled {bs}; "
              f"geoscape after campaign start {geo_flags}")
    return ok, detail


# ---- rows --------------------------------------------------------------------------

def separate_row(results, row, lander_role, host_opts, tag, ports):
    host = GameClient("host", ports[0], make_user_dir(tag + "_host", options=host_opts))
    client = GameClient("client", ports[1], make_user_dir(tag + "_client", options=ON))
    host.spawn(); client.spawn()
    host.connect(); client.connect()
    try:
        session.new_campaign(host, client, port=ports[2])
        geo.wait_both_ready(host, client)
        geo_flags = {gc.name: geo_flag(gc) for gc in (host, client)}
        lander = client if lander_role == "client" else host
        separate_landing(host, client, lander)
        through_inventory(host, client)
        results[row] = verdict(host, client, host_opts["EnableCoopParallelTurns"], geo_flags)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass
    return alive


def shared_row(results, row, tag, ports):
    js = shared_fixture.bring_up(tag, ports, host_options=dict(ON, skipNextTurnScreen=True),
                                 client_options=ON)
    host, client = js.host, js.client
    try:
        geo_flags = {gc.name: geo_flag(gc) for gc in (host, client)}
        SPC.assign_and_fly(host, client)
        host.ok({"cmd": "confirm_landing"})
        through_inventory(host, client)
        results[row] = verdict(host, client, True, geo_flags)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    rows = os.environ.get("COOP_PTL_ROWS", "S1,S2,S3,H1").split(",")
    results = {}
    note = None
    alive = True
    try:
        if "S1" in rows:
            alive = separate_row(results, "S1 SEPARATE fresh, both on, client's craft lands",
                                 "client", ON, "ptl1", (49611, 49612, "49613")) and alive
        if "S2" in rows:
            alive = separate_row(results, "S2 SEPARATE fresh, both on, host's craft lands",
                                 "host", ON, "ptl2", (49614, 49615, "49616")) and alive
        if "S3" in rows:
            alive = separate_row(results, "S3 SEPARATE fresh, host off / client on, client's craft lands",
                                 "client", OFF, "ptl3", (49617, 49618, "49619")) and alive
        if "H1" in rows:
            alive = shared_row(results, "H1 SHARED, both on, host lands the shared craft",
                               "ptlh", (49620, 49621, 49622)) and alive
    except Inconclusive as e:
        note = "INCONCLUSIVE: " + str(e)
    except Exception as e:
        note = f"ERROR {type(e).__name__}: {e}"
        alive = False

    print("==== RESULT ====")
    for row, (ok, detail) in results.items():
        print(("PASS " if ok else "FAIL ") + row + ": " + detail)
    print("alive:", alive, "| note:", note)
    if not alive:
        sys.exit(2)
    if note:
        sys.exit(3)
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: the host's parallel-turns choice holds in every battle")
    sys.exit(0)


if __name__ == "__main__":
    main()
