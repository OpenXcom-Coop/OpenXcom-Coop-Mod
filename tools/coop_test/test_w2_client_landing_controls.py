"""W2-H9 (owner D199 = (a)) - the controls: every path the SEPARATE-client refusal
must NOT touch. Green before AND after W2-H9.

  H9-3  host-craft joint battle with a client guest (SEPARATE, SPEC 19 S1 fixture):
        both machines enter; the guest is seat 1; no refusal anywhere.
  H9-4  SHARED client landing: the client orders the shared craft, answers YES on
        its brokered prompt; the host generates and both enter; no refusal.
  H9-5  single player: the landing prompt still appears and YES still starts the
        battle; no refusal.

Each row is its own boot and ONE run. The red rows are test_w2_client_landing.py.

Run:  python tools/coop_test/test_w2_client_landing_controls.py
Exit 0 = every row PASS; 2 = any row FAIL.
"""

import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, EXE, LAND_LON, LAND_LAT  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402

H9_LOG = "[coop-h9]"
KEEP = ["ConfirmLandingState", "CraftErrorState"]
CRASH_DIR = os.path.join(os.path.dirname(EXE), "crashlogs")
PUSH_RE = re.compile(r"\[coop-ui\] push (?:class )?(?:OpenXcom::)?(\w+) depth=")

T0 = time.time()


def log(msg):
    print("[%7.1fs] %s" % (time.time() - T0, msg), flush=True)


class RowFail(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise RowFail(msg)


# ---- shared helpers (copied into each W2-H9 file; session.py is never edited) ----

def strip(s):
    return s.replace("class OpenXcom::", "")


def stack(gc):
    return [strip(s) for s in session.states(gc)]


def top_of(gc):
    st = stack(gc)
    return st[-1] if st else ""


def crash_files():
    return set(glob.glob(os.path.join(CRASH_DIR, "crash_*")))


def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def log_count(gc, needle):
    return sum(1 for line in log_lines(gc) if needle in line)


def pushes(gc, state_name):
    """WV-D112 screen record: how many times `state_name` was pushed on gc."""
    n = 0
    for line in log_lines(gc):
        m = PUSH_RE.search(line)
        if m and m.group(1) == state_name:
            n += 1
    return n


def probe(gc):
    es = gc.cmd({"cmd": "event_state"})
    return es.get("coopClientBattleRefused"), es.get("coopClientBattleRefusedLast")


def base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base")


def skyranger(gc):
    for c in base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("no skyranger")


def craft_by_id(gc, cid):
    for c in base0(gc)["crafts"]:
        if c["id"] == cid and "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("skyranger %s gone" % cid)


def own_roster_base(gc):
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if not b["coopBaseFlag"] and not b.get("coopIcon") and b["soldiers"]:
            return b
    raise AssertionError("no real base with soldiers")


def seat_three(gc, tag):
    """Unseat all, seat the 3 lowest ids of the own roster base on the own Skyranger."""
    rb = own_roster_base(gc)
    bname = rb["name"]
    cid = skyranger(gc)["id"]
    ids = sorted(s["id"] for s in rb["soldiers"])
    for sid in ids:
        gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False,
                "base": bname})
    squad = ids[:3]
    for sid in squad:
        r = gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True,
                    "base": bname})
        check(r.get("seated"), "FIXTURE: %s soldier %s not seated: %s" % (tag, sid, r))
    log("%s: seated %s on own Skyranger %s at base %s" % (tag, squad, cid, bname))
    return cid, squad


def send_to_new_site(gc, tag, cid):
    b0 = base0(gc)
    site = gc.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                  "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                  "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    gc.wait_for("%s site listed" % tag,
                lambda: any(s["id"] == site_id and not s.get("coop")
                            for s in gc.ok({"cmd": "geo_state"})["missionSites"]) or None,
                timeout=30)
    gc.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
           "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10, "dest": "site:%d" % site_id,
           "fuel": 999999, "lowFuel": False})
    sk = skyranger(gc)
    check(sk["status"] == "STR_OUT" and sk.get("destKind") == "site"
          and sk.get("destId") == site_id,
          "FIXTURE: %s own skyranger not OUT to its own site %d: %s" % (tag, site_id, sk))
    log("%s: own site %d spawned; Skyranger %s OUT to it" % (tag, site_id, cid))
    return site_id


def drain_one(gc, keep):
    top = top_of(gc)
    if "GeoscapeState" in top:
        return
    if "CoopState" in top:
        gc.cmd({"cmd": "coop_dialog_back"})
    else:
        gc.cmd({"cmd": "dismiss_popup", "keep": list(keep)})


def arrival_poll(gc, tag, others, timeout=60):
    """Every 0.5 s up to 60 s on gc: stop on top ConfirmLandingState or
    CraftErrorState; otherwise drain popups (never the kept states) and run the clock
    at geo_set_speed idx 2. `others` are drained the same way."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        top = top_of(gc)
        if "ConfirmLandingState" in top:
            log("%s arrival: top ConfirmLandingState" % tag)
            return "ConfirmLandingState"
        if "CraftErrorState" in top:
            log("%s arrival: top CraftErrorState" % tag)
            return "CraftErrorState"
        drain_one(gc, KEEP)
        gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        for m in others:
            drain_one(m, KEEP)
            m.cmd({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.5)
    raise RowFail("FIXTURE: %s craft never arrived in %ds (stack %s)"
                  % (tag, timeout, stack(gc)[-3:]))


def no_refusal(gcs, tag):
    """Probe 0, 0 [coop-h9] lines and 0 CraftErrorState pushes on every machine."""
    time.sleep(3)  # house log flush
    for gc in gcs:
        p = probe(gc)
        check(p == (0, ""), "%s: %s probe %r, want (0, '')" % (tag, gc.name, p))
        check(log_count(gc, H9_LOG) == 0, "%s: %s logged %d [coop-h9] lines"
              % (tag, gc.name, log_count(gc, H9_LOG)))
        check(pushes(gc, "CraftErrorState") == 0, "%s: %s CraftErrorState pushes %d"
              % (tag, gc.name, pushes(gc, "CraftErrorState")))


def shutdown_all(*gcs):
    for gc in gcs:
        if gc is None:
            continue
        try:
            gc.shutdown()
        except Exception as e:  # report, never mask the row verdict
            log("%s shutdown: %r" % (gc.name, e))


def dump(tag, gcs):
    """Probe dump of every machine (STOP-IF 2 evidence)."""
    for gc in gcs:
        try:
            es = gc.cmd({"cmd": "event_state"})
            gco = gc.cmd({"cmd": "get_coop"})
            bs = gc.cmd({"cmd": "battle_state"})
            log("DUMP %s %s: stack=%s phase=%s battleId=%s hostSim=%s desyncSeen=%s "
                "refused=%s last=%r coopStatic=%s serverOwner=%s shared=%s gamemode=%s "
                "inBattle=%s missionType=%s" % (
                    tag, gc.name, stack(gc)[-4:], es.get("phase"), es.get("battleId"),
                    es.get("hostSim"), es.get("desyncSeen"),
                    es.get("coopClientBattleRefused"), es.get("coopClientBattleRefusedLast"),
                    gco.get("coopStatic"), gco.get("serverOwner"), gco.get("shared"),
                    gco.get("gamemode"), bs.get("inBattle"), bs.get("missionType")))
        except Exception as e:
            log("DUMP %s %s failed: %r" % (tag, gc.name, e))


# ---- H9-3: host-craft joint battle with a client guest -------------------------------

def row_h9_3():
    host = GameClient("host", 1, make_user_dir("w2h9_3_host"))
    client = GameClient("client", 2, make_user_dir("w2h9_3_client"))
    try:
        host.spawn(); client.spawn(); host.connect(); client.connect()

        def guard(h, c):
            cc = c.cmd({"cmd": "get_coop"})
            hc = h.cmd({"cmd": "get_coop"})
            ok = (cc.get("coopStatic") is True and cc.get("serverOwner") is False
                  and cc.get("shared") is False and cc.get("gamemode") in (0, 1)
                  and hc.get("serverOwner") is True)
            check(ok, "VACUITY H9-3: client coopStatic=%r serverOwner=%r shared=%r "
                      "gamemode=%r; host serverOwner=%r" % (
                          cc.get("coopStatic"), cc.get("serverOwner"), cc.get("shared"),
                          cc.get("gamemode"), hc.get("serverOwner")))
            log("H9-3 vacuity guard: client coopStatic=True serverOwner=False shared=False "
                "gamemode=%s; host serverOwner=True" % cc.get("gamemode"))

        session.bring_up_separate_guest_battle(host, client, port="48485",
                                               pre_mission_start=guard)
        for gc in (host, client):
            check("BattlescapeState" in top_of(gc), "H9-3: %s top %s, want BattlescapeState"
                  % (gc.name, top_of(gc)))
        es_h = host.cmd({"cmd": "event_state"})
        es_c = client.cmd({"cmd": "event_state"})
        check(es_c.get("phase") == "Active", "H9-3: client phase %s" % es_c.get("phase"))
        check(es_c.get("battleId") == es_h.get("battleId"),
              "H9-3: battleId client %s host %s" % (es_c.get("battleId"), es_h.get("battleId")))
        for gc in (host, client):
            players = [u for u in gc.cmd({"cmd": "battle_state"}).get("units", [])
                       if u.get("isPlayerSoldier")]
            guests = [u for u in players if "Guest" in (u.get("name") or "")]
            check(len(guests) == 1 and guests[0].get("coop") == 1,
                  "H9-3: %s player units named Guest* %s, want exactly one with coop == 1"
                  % (gc.name, [(u.get("name"), u.get("coop")) for u in guests]))
        no_refusal((host, client), "H9-3")
        for gc in (host, client):
            check(gc.cmd({"cmd": "event_state"}).get("desyncSeen") is False,
                  "H9-3: %s desyncSeen" % gc.name)
        log("PASS H9-3: both on BattlescapeState, client phase Active, battleId %s equal, one "
            "Guest* unit coop == 1 on both, probe 0 / 0 [coop-h9] lines / 0 CraftErrorState "
            "pushes on both, desyncSeen false" % es_c.get("battleId"))
    except Exception:
        dump("H9-3", (host, client))
        raise
    finally:
        shutdown_all(host, client)


# ---- H9-4: SHARED client landing runs on the host ---------------------------------------

def row_h9_4():
    # TASK 0 (step-5 verdict of test_shared_landing.py on the tip build = PASS): the
    # YES is the CLIENT's, on its brokered ConfirmLandingState.
    js = shared_fixture.bring_up("w2h9s", (48487, 48488, 48486))
    host, client = js.host, js.client
    try:
        b0 = base0(host)
        cid = skyranger(host)["id"]
        site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                        "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                        "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
        site_id = site["site_id"]
        for gc in (host, client):
            gc.wait_for("site replicated to %s" % gc.name,
                        lambda gc=gc: any(s["id"] == site_id
                                          for s in gc.ok({"cmd": "geo_state"})["missionSites"])
                        or None, timeout=60, interval=0.5)
        r = client.ok({"cmd": "craft_order", "order": "target", "craft_id": cid,
                       "craft_type": skyranger(client)["type"], "site_id": site_id})
        check(r.get("ok") or r.get("sent"), "FIXTURE H9-4: client craft_order not sent: %s" % r)
        host.wait_for("host applied the client's craft order",
                      lambda: (craft_by_id(host, cid)["destKind"] == "site") or None,
                      timeout=30, interval=0.5)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10, "dest": "site:%d" % site_id,
                 "fuel": 999999, "lowFuel": False})

        def brokered():
            if host.ok({"cmd": "shared_landing_state"})["pending"]:
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None

        host.wait_for("host brokered the landing prompt", brokered, timeout=90, interval=0.5)
        client.wait_for("client brokered ConfirmLandingState",
                        lambda: session.has_state(client, "ConfirmLandingState"), timeout=60,
                        interval=0.5)
        check(client.cmd({"cmd": "get_coop"}).get("shared") is True,
              "VACUITY H9-4: client get_coop.shared is not True")
        log("H9-4 vacuity guard: client get_coop.shared=True; client brokered prompt up")
        client.ok({"cmd": "confirm_landing"})
        host.wait_for("host entered the brokered battle",
                      lambda: host.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                      timeout=180, interval=1.0)
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"),
                      timeout=60, interval=0.5)
        check(session.drive_both_to_tactical(host, client),
              "H9-4: drive_both_to_tactical timed out (host=%s client=%s)"
              % (stack(host)[-3:], stack(client)[-3:]))
        for gc in (host, client):
            check("BattlescapeState" in top_of(gc), "H9-4: %s top %s, want BattlescapeState"
                  % (gc.name, top_of(gc)))
        es_h = host.cmd({"cmd": "event_state"})
        es_c = client.cmd({"cmd": "event_state"})
        check(es_c.get("phase") == "Active", "H9-4: client phase %s" % es_c.get("phase"))
        check(es_c.get("battleId") == es_h.get("battleId"),
              "H9-4: battleId client %s host %s" % (es_c.get("battleId"), es_h.get("battleId")))
        check(not host.ok({"cmd": "shared_landing_state"})["pending"],
              "H9-4: host pending landing not cleared")
        no_refusal((host, client), "H9-4")
        log("PASS H9-4: both on BattlescapeState, client phase Active, battleId %s equal, "
            "pending false, probe 0 / 0 [coop-h9] lines / 0 CraftErrorState pushes on both"
            % es_c.get("battleId"))
    except Exception:
        dump("H9-4", (host, client))
        raise
    finally:
        js.shutdown()


# ---- H9-5: single player -----------------------------------------------------------------

def row_h9_5():
    sp = GameClient("sp", 1, make_user_dir("w2h9_5_sp"))
    try:
        sp.spawn(); sp.connect()
        sp.ok({"cmd": "open_new_game", "mode": "solo"})
        sp.wait_for("difficulty", lambda: session.has_state(sp, "NewGameState"))
        sp.ok({"cmd": "newgame_ok"})
        sp.wait_for("base placement", lambda: session.has_state(sp, "BuildNewBaseState"),
                    timeout=60)
        r = sp.cmd({"cmd": "place_first_base", "lon": session.HOST_LON, "lat": session.HOST_LAT,
                    "name": "SoloBase"})
        if not r.get("ok"):
            sp.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT,
                   "name": "SoloBase"})

        def on_geoscape():
            if "GeoscapeState" in top_of(sp):
                return True
            drain_one(sp, KEEP)
            return None

        sp.wait_for("SP geoscape top", on_geoscape, timeout=30, interval=0.5)
        check(sp.cmd({"cmd": "get_coop"}).get("coopStatic") is False,
              "VACUITY H9-5: get_coop.coopStatic is not False")
        log("H9-5 vacuity guard: coopStatic=False (single player)")
        cid, _ = seat_three(sp, "SP")
        send_to_new_site(sp, "SP", cid)
        path = arrival_poll(sp, "SP", ())
        check(path == "ConfirmLandingState", "H9-5: SP arrival reached %s, want the landing "
              "prompt" % path)
        sp.ok({"cmd": "confirm_landing"})
        sp.wait_for("SP BriefingState", lambda: session.has_state(sp, "BriefingState"),
                    timeout=60, interval=0.5)
        check(sp.cmd({"cmd": "battle_state"}).get("inBattle") is True,
              "H9-5: battle_state.inBattle is not True")
        no_refusal((sp,), "H9-5")
        log("PASS H9-5: ConfirmLandingState appeared, BriefingState after YES, inBattle true, "
            "probe 0 / 0 [coop-h9] lines / 0 CraftErrorState pushes")
    except Exception:
        dump("H9-5", (sp,))
        raise
    finally:
        shutdown_all(sp)


ROWS = (("H9-3", row_h9_3), ("H9-4", row_h9_4), ("H9-5", row_h9_5))


def main():
    crash_before = crash_files()
    failed = []
    walls = []
    for name, fn in ROWS:
        t = time.time()
        try:
            fn()
            print("[PASS] %s" % name, flush=True)
        except Exception as e:
            failed.append(name)
            print("[FAIL] %s: %s: %s" % (name, type(e).__name__, e), flush=True)
        walls.append((name, time.time() - t))
    new_crash = sorted(crash_files() - crash_before)
    if new_crash:
        failed.append("crashlog")
        print("[FAIL] crashlog: new crashlog files %s" % new_crash, flush=True)
    print("\n==== W2-H9 control rows summary ====")
    for name, w in walls:
        print("  %-5s %-4s wall %.1fs" % (name, "FAIL" if name in failed else "PASS", w))
    print("  total wall %.1fs; FAILED: %s" % (time.time() - T0, ", ".join(failed) or "none"))
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
