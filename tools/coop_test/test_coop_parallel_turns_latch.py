"""Regression test: the host's parallel-turns choice holds for every battle in the session.

Finding (2026-10-10, origin/main 12cfcfb54): on a fresh SEPARATE campaign the session
host's connectionTCP::_enable_parallel_turns dropped 1 -> 0 right after the COOP_READY
handshake, when a world loaded from a blob written before the flag latched. A battle the
CLIENT's craft started then ran in classic alternating turns (parallelEnabled false on
both machines, so the parallel sync check never ran). A battle the host's craft started
re-latched the flag, and a resumed save kept it.

Rows (each a fresh campaign, both machines enter the battle and settle on the map):
  S2 SEPARATE, both parallel, the HOST's craft lands.
  S3 SEPARATE, host traditional and client parallel, the HOST's craft lands: the host's
     choice (traditional) must hold, not the client's.
  H1 SHARED, both parallel, the host lands the shared craft (one host-owned and one
     client-owned soldier).
  B1 (on H1's battle, main #210): no turn / wait banner at a parallel side start on
     either machine, sampled 8 s at turn 1 and again after one side boundary.
A row passes when event_state.turnMode on BOTH machines equals the host's option once
both are on the battlescape (the host stamps the mode on the battle offer and the client
mirrors it, D-19b).
the option is CoopTurnMode ("parallel" /
"traditional"); main's S1 and S3 landed the CLIENT's craft, which never starts a SEPARATE
battle: S1 is dropped and S3 lands the host's craft.

  * PASS (exit 0) / FAIL (exit 2: a row failed, a process crashed or a precondition
    never held; MG-P1).

Env (optional): COOP_PTL_ROWS = "S2,S3,H1" subset (B1 runs with H1).
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
from harness import GameClient, make_user_dir  # noqa: E402

ON = {"CoopTurnMode": "parallel"}      # the rewrite's turn-mode option (Options.cpp CoopTurnMode)
OFF = {"CoopTurnMode": "traditional"}


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
    """In-battle readout: this battle's turn mode as the host stamped it on the
    battle offer and this machine mirrors it (event_state.turnMode, D-19b), and this
    machine's own option (event_state.optionTurnMode)."""
    es = gc.cmd({"cmd": "event_state"})
    return {"mode": es.get("turnMode"), "option": es.get("optionTurnMode")}


def geo_flag(gc):
    """This machine's own turn-mode option, read on the geoscape."""
    return gc.cmd({"cmd": "event_state"}).get("optionTurnMode")


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
    """MG-P1 (rewrite battle entry): the host enters, then session.drive_both_to_tactical
    takes both machines through the briefings and the pre-battle equip screens together
    and settles both on the tactical map."""
    host.wait_for("host in battle", lambda: host.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                  timeout=180, interval=1.0)
    if not session.drive_both_to_tactical(host, client):
        raise Inconclusive("both machines never settled on the battlescape: "
                           f"{[top(gc) for gc in (host, client)]}")


# ---- the verdict -----------------------------------------------------------------

def verdict(host, client, expected, geo_flags):
    """both machines run the battle in the HOST's turn mode (`expected`)."""
    got = {gc.name: flags(gc) for gc in (host, client)}
    ok = all(f["mode"] == expected for f in got.values())
    detail = f"expected {expected}; battle event_state {got}; options on the geoscape {geo_flags}"
    return ok, detail


# ---- B1 (main #210: test_parallel_sharedturn's banner check; MG-P1) ------------------

FORBIDDEN_BANNERS = ("'s turn", "waiting for", "spectator mode")  # main's tokens, matched case-blind
END_TURN_HALF = "END TURN 1/2"  # the host's tally text once the client pressed END TURN (test_battle_end_separate)


def no_banners(host, client, seconds=8.0):
    """Sampled, not one snapshot (main's assert_no_banners): the rewrite's turn / wait
    banner is battle_state.coopWaitText. Returns (clean, every text each machine showed)."""
    deadline = time.time() + seconds
    seen = {"host": set(), "client": set()}
    while time.time() < deadline:
        for gc in (host, client):
            w = gc.cmd({"cmd": "battle_state"}).get("coopWaitText") or ""
            if w:
                seen[gc.name].add(w)
        time.sleep(0.5)
    bad = [w for v in seen.values() for w in v if any(f in w.lower() for f in FORBIDDEN_BANNERS)]
    return not bad, {k: sorted(v) for k, v in seen.items()}


def cycle_side(host, client, timeout=240):
    """One parallel side boundary: END TURN on both seats (the client first, then the host
    once its END TURN reads 1/2, the readiness tally), then drain both machines (never a
    BattlescapeState or a VoteMenu) until the player side is back on both. Returns the turn."""
    start = host.cmd({"cmd": "battle_state"}).get("turn")
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    host.wait_for("host " + END_TURN_HALF,
                  lambda: host.cmd({"cmd": "battle_state"}).get("coopEndTurnText") == END_TURN_HALF or None,
                  timeout=20, interval=0.25)
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    deadline = time.time() + timeout
    while time.time() < deadline:
        bs = {}
        for gc in (host, client):
            b = gc.cmd({"cmd": "battle_state"})
            if not b.get("inBattle"):
                raise Inconclusive(f"{gc.name} left the battle during the side boundary")
            bs[gc.name] = b
            if top(gc) not in ("BattlescapeState", "VoteMenu"):
                gc.cmd({"cmd": "dismiss_popup"})
        if (all((b.get("turn") or 0) > start and b.get("side") == 0 for b in bs.values())
                and all(top(gc) == "BattlescapeState" for gc in (host, client))):
            return bs["host"]["turn"]
        time.sleep(1.0)
    raise Inconclusive(f"the player side never came back: host={top(host)} client={top(client)}")


def banner_row(results, host, client):
    """B1: no turn / wait banner at a parallel side start on either machine, at turn 1
    and after one side boundary (the non-player units pinned first, session.pin_ai_neutral,
    so the alien side cannot act)."""
    ok1, seen1 = no_banners(host, client)
    session.pin_ai_neutral(host, client, tag="mgp1-b1")
    turn = cycle_side(host, client)
    ok2, seen2 = no_banners(host, client)
    results["B1 SHARED parallel, no turn / wait banner at a side start (main #210)"] = (
        ok1 and ok2, f"turn 1 showed {seen1}; turn {turn} showed {seen2}")


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
        if geo_flags != {"host": host_opts["CoopTurnMode"], "client": "parallel"}:
            raise Inconclusive(f"the turn-mode options did not take: {geo_flags}")
        lander = client if lander_role == "client" else host
        separate_landing(host, client, lander)
        through_inventory(host, client)
        results[row] = verdict(host, client, host_opts["CoopTurnMode"], geo_flags)
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
        if geo_flags != {"host": "parallel", "client": "parallel"}:
            raise Inconclusive(f"the turn-mode options did not take: {geo_flags}")
        # main's assign_and_fly + the host's landing = the rewrite's SHARED mixed
        # bring-up (one host-owned and one client-owned soldier; the host confirms the
        # landing; it drives both machines to the tactical map).
        session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1})
        results[row] = verdict(host, client, "parallel", geo_flags)
        banner_row(results, host, client)
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    return alive


def main():
    rows = os.environ.get("COOP_PTL_ROWS", "S2,S3,H1").split(",")  # S1 dropped
    results = {}
    note = None
    alive = True
    try:
        if "S2" in rows:
            alive = separate_row(results, "S2 SEPARATE fresh, both on, host's craft lands",
                                 "host", ON, "ptl2", (49614, 49615, "49616")) and alive
        if "S3" in rows:
            alive = separate_row(results, "S3 SEPARATE fresh, host traditional / client parallel, host's craft lands",
                                 "host", OFF, "ptl3", (49617, 49618, "49619")) and alive
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
        sys.exit(2)  # a precondition miss fails the run
    if not all(ok for ok, _ in results.values()):
        sys.exit(2)
    print("PASS: the host's parallel-turns choice holds in every battle")
    sys.exit(0)


if __name__ == "__main__":
    main()
