"""W2-H21d S-3 (F8979 routed, F9201, F9202; spec rewrite/prompts/w2h21d_preview_battle_paths.md (f), QH21d-3 a, QH21d-4 a, QH21d-5 a;
TASK 0 rewrite/w2h21d-task0/s3/CONSTANTS.md): in SHARED either player may answer a craft's "land?" prompt. When the host's own copy is
not on its screen (here dismissed generically: the race's host-side state, F9203) and the host has a practice screen open - the
Ufopaedia craft preview (P1) or a base craft equipment screen (P4) - the second player's YES starts the battle ON TOP of that screen and
frees its practice battle; after the debriefing the host returns to it (TASK 0 T0-X: the host died 3/3, 0.4-0.7 s after its
debriefing OK, a different first frame each time).
  Boot LG bring_up("w2h21ldg", (49540, 49541, 46976)):
    H21d-LG (GUARD; TASK 0 2/2) DRIVE; the client's confirm_landing; within W the host stack == [GeoscapeState, BriefingState];
        battle_state.isPreview false; alive(host) HOLD s more.
  Boot L1 bring_up("w2h21ld1", (49542, 49543, 46977)):
    H21d-L1 (named RED; TASK 0 3/3) DRIVE; PV(host), non-vacuity: top BattlescapeState, isPreview true, inBattle true; the client's
        confirm_landing; RED: within W the host stack == [GeoscapeState, BriefingState] (TASK 0: [GeoscapeState, UfopaediaStartState,
        UfopaediaSelectState, ArticleStateCraft, StatsForNerdsState, BattlescapeState, BriefingState]); then LG's later cells.
  Boot L2 bring_up("w2h21ld2", (49544, 49545, 46978)):
    H21d-L2 (named RED; TASK 0 2/2) as L1 with the host's P4 (open_craft_equipment {HostBase, the SKYRANGER} + craft_inventory),
        non-vacuity: top InventoryState, inBattle true (TASK 0: [GeoscapeState, CraftEquipmentState, InventoryState, BriefingState]).
DRIVE = test_w2_client_landing_controls row_h9_4's drive to both prompts (the host's site, the client's craft_order, the host's
craft_force, the host's shared_landing_state.pending, the client's ConfirmLandingState), then the host's broker copy on top within W and
its dismiss_popup -> handled "generic" for ConfirmLandingState, the host's stack [GeoscapeState], pending still true, the client's top
ConfirmLandingState. PV = W2-H21c's pv (test_w2_preview_restream). W = 10 s at 0.25 s polls, HOLD = 2 s, SETTLE 0.3 s before a key,
click or lever (F2888). HL = the host's openxcom.log screen record after the YES. CRASH = new crashlogs/crash_*.log since the row
started (first 4 frames). Setup guard per boot: stacks [GeoscapeState], localSeat 0 / 1, has_battle false (a miss fails the row
`boot`). One boot per row, shut down before the next. EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; every row runs
after a failure; ONE run (WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_w2_client_landing_controls as lc  # noqa: E402  (main-guarded: base0, skyranger, craft_by_id)
import test_w2_preview_restream as pr  # noqa: E402  (main-guarded: pv, alive, boot, shut, Row, log_*, ui, crash_*)
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded)

BOOTS = (("w2h21ldg", (49540, 49541, 46976), "LG"), ("w2h21ld1", (49542, 49543, 46977), "L1"),
         ("w2h21ld2", (49544, 49545, 46978), "L2"))
W, POLL, HOLD, SETTLE = 10.0, 0.25, 2.0, 0.3
GEO, BS, BRF, CLS = "GeoscapeState", "BattlescapeState", "BriefingState", "ConfirmLandingState"
INV, CEQ, HB = "InventoryState", "CraftEquipmentState", "HostBase"
WANT = [GEO, BRF]
TASK0 = {"LG": "guard: the host stack [GeoscapeState, BriefingState] 2/2",
         "L1": "named red 3/3: [GeoscapeState, UfopaediaStartState, UfopaediaSelectState, ArticleStateCraft, StatsForNerdsState, "
               "BattlescapeState, BriefingState]; T0-X 3/3 host deaths after the debriefing OK",
         "L2": "named red 2/2: [GeoscapeState, CraftEquipmentState, InventoryState, BriefingState]"}
q, stack, short, wait_until = h20.q, h20.stack, h20.short, h20.wait_until


def mach(gc):
    gco, bs = q(gc, {"cmd": "get_coop"}), q(gc, {"cmd": "battle_state"})
    return {"alive": pr.alive(gc), "stack": stack(gc), "world_state": q(gc, {"cmd": "world_state"}),
            "get_coop": {k: gco.get(k) for k in ("localSeat", "inBattle", "lobbyMode", "shared", "error")},
            "battle_state": {k: bs.get(k) for k in ("isPreview", "inBattle", "phase", "turn", "error")},
            "shared_landing_state": q(gc, {"cmd": "shared_landing_state"})}


def capture(x, n_hl, crash0):
    return {"host": mach(x.host), "client": mach(x.client), "HL": pr.ui(pr.log_lines(x.host, n_hl))[-30:],
            "host log": [ln.split("\t")[-1] for ln in pr.log_lines(x.host)[-20:]], "CRASH": pr.crash_info(crash0)}


def drive(r, x):
    """DRIVE -> (ok, craft id): row_h9_4's drive to both prompts, then the host's dismiss_popup of its own broker copy"""
    host, client = x.host, x.client
    try:
        b0 = lc.base0(host)
        cid = lc.skyranger(host)["id"]
        site_id = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                           "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
        for gc in (host, client):
            gc.wait_for("site replicated to %s" % gc.name, lambda gc=gc: any(
                s["id"] == site_id for s in gc.ok({"cmd": "geo_state"})["missionSites"]) or None, timeout=60, interval=0.5)
        rep = client.ok({"cmd": "craft_order", "order": "target", "craft_id": cid, "craft_type": lc.skyranger(client)["type"],
                         "site_id": site_id})
        if not (rep.get("ok") or rep.get("sent")):
            raise AssertionError("client craft_order not sent: %s" % rep)
        host.wait_for("host applied the client's craft order",
                      lambda: (lc.craft_by_id(host, cid)["destKind"] == "site") or None, timeout=30, interval=0.5)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10,
                 "dest": "site:%d" % site_id, "fuel": 999999, "lowFuel": False})

        def brokered():
            if host.ok({"cmd": "shared_landing_state"})["pending"]:
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None
        host.wait_for("host brokered the landing prompt", brokered, timeout=90, interval=0.5)
        client.wait_for("client brokered ConfirmLandingState", lambda: session.has_state(client, CLS), timeout=60, interval=0.5)
    except Exception as e:
        return r.cell("G: DRIVE reached both prompts (row_h9_4)", False, short(e)), None
    r.ev["DRIVE"] = {"craft": cid, "site": site_id, "host": stack(host), "client": stack(client)}
    if not r.cell("G: the host's broker copy on top within %.0f s" % W, wait_until(lambda: pr.on_top(host, CLS), W, 0.05),
                  stack(host)):
        return False, cid
    time.sleep(SETTLE)
    d = q(host, {"cmd": "dismiss_popup"})
    time.sleep(SETTLE)
    st = r.ev["dismiss"] = {"reply": {k: d.get(k) for k in ("type", "handled", "ok", "error")}, "host": stack(host),
                            "pending": q(host, {"cmd": "shared_landing_state"}).get("pending"), "client": stack(client)}
    ok = (CLS in str(d.get("type")) and d.get("handled") == "generic" and st["host"] == [GEO] and st["pending"] is True
          and st["client"][-1:] == [CLS])
    return r.cell("G: the host's dismiss_popup -> generic %s; host [%s], pending true, the client's top %s" % (CLS, GEO, CLS),
                  ok, st), cid


def practice(r, x, kind, cid):
    """L1: PV(host); L2: the host's P4 on the landing craft. The non-vacuity cell."""
    host = x.host
    if kind == "L1":
        ok, r.ev["PV(host)"] = pr.pv(host, x.keys["host"])
        if not r.cell("G: PV(host) reached the preview", ok, r.ev["PV(host)"]):
            return False
        want_top, want_pre = BS, True
    else:
        rep = q(host, {"cmd": "open_craft_equipment", "base": HB, "craft_id": cid})
        ok = rep.get("ok") and rep.get("craftId") == cid and wait_until(lambda: CEQ in stack(host), W, 0.05)
        time.sleep(SETTLE)
        rep2 = q(host, {"cmd": "craft_inventory"})
        ok = ok and rep2.get("opened") is True and wait_until(lambda: pr.on_top(host, INV), W, 0.05)
        r.ev["P4(host)"] = {"open": {k: rep.get(k) for k in ("ok", "craftId", "error")},
                            "inventory": {k: rep2.get(k) for k in ("ok", "opened", "error")}, "stack": stack(host)}
        if not r.cell("G: the host's P4 (open_craft_equipment + craft_inventory) opened", ok, r.ev["P4(host)"]):
            return False
        want_top, want_pre = INV, None
    nv = r.ev["non-vacuity"] = {"stack": stack(host), "isPreview": q(host, {"cmd": "battle_state"}).get("isPreview"),
                                "inBattle": q(host, {"cmd": "get_coop"}).get("inBattle")}
    return r.cell("G: non-vacuity: host top %s%s, inBattle true" % (want_top, ", isPreview true" if want_pre else ""),
                  nv["stack"][-1:] == [want_top] and (want_pre is None or nv["isPreview"] is True) and nv["inBattle"] is True, nv)


def row(r, x, kind, crash0):
    host, client = x.host, x.client
    ok, cid = drive(r, x)
    if not ok or (kind != "LG" and not practice(r, x, kind, cid)):
        r.ev["not reached"] = "the client's YES and every later cell"
        return r.cap.update(capture(x, 0, crash0))
    n_hl = pr.log_size(host)
    time.sleep(SETTLE)
    t1 = time.time()
    rep = q(client, {"cmd": "confirm_landing"})
    if not r.cell("G: the client's confirm_landing ok", rep.get("ok") is True, rep):
        return r.cap.update(capture(x, n_hl, crash0))
    tl, last = [], None
    while True:
        s = stack(host) if pr.alive(host) else ["<dead>"]
        if s != last:
            tl.append((round((time.time() - t1) * 1000), s))
            last = s
        if s == WANT or s == ["<dead>"] or time.time() - t1 >= W:
            break
        time.sleep(POLL)
    r.ev["host timeline after the YES"] = tl
    r.cell("%swithin %.0f s the host stack == %s" % ("" if kind == "LG" else "RED: ", W, WANT), tl[-1][1] == WANT, tl[-1][1])
    pre = r.ev["isPreview"] = q(host, {"cmd": "battle_state"}).get("isPreview")
    r.cell("battle_state.isPreview false", pre is False, pre)
    time.sleep(HOLD)
    al = r.ev["alive after HOLD"] = pr.alive(host)
    r.cell("alive(host) %.0f s more" % HOLD, al, stack(host) if al else "dead")
    r.ev["HL"] = pr.ui(pr.log_lines(host, n_hl))[-20:]
    r.ev["CRASH"] = pr.crash_info(crash0)
    r.ev["client after"] = stack(client)
    if r.fails:
        r.cap.update(capture(x, n_hl, crash0))


def run_boot(tag, ports, kind, results, walls):
    t0, crash0 = time.time(), pr.crash_names()
    r = pr.Row("H21d-" + kind, TASK0[kind])
    js, x = pr.boot(tag, ports, [r])
    if js is not None:
        try:
            row(r, x, kind, crash0)
        except Exception as e:
            r.cell("G: H21d-%s exception" % kind, False, short(e))
            if not r.cap:
                r.cap.update(capture(x, 0, crash0))
        pr.shut(js, r, tag, False)
    walls[r.rid] = r.ev["wall s"] = round(time.time() - t0, 1)
    r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    for tag, ports, kind in BOOTS:
        run_boot(tag, ports, kind, results, walls)
    rids = ["H21d-" + k for _t, _p, k in BOOTS]
    failed = [rid for rid in rids if not results.get(rid)]
    print(f"\ntest_w2_landing_reply_practice: {len(rids) - len(failed)}/{len(rids)} passed (fail={failed}) walls "
          f"{json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
