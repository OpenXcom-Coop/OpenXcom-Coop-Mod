"""D250-U S-C2 - test_campaign_battle_gm3_end.py: a gm3 PvP campaign battle's end (host = the aliens, client = X-COM). In ONE
gm3 campaign a won, an aborted and a lost battle each end with both debriefings; the X-COM player's world carries the battle's
results (missions, deaths, the craft's fate), the X-COM player's page 3 is live and the alien host's hidden, and the alien host is
back in its exact parked world with the battle's mission site gone from both globes.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, (d) "Stage S-C2" and (f) "test_campaign_battle_gm3_end.py" AS AMENDED by
AMENDMENT SC-2 (SC2-6 test text, SC2-7 fixture rules FX2-1 .. FX2-13) and its ORCHESTRATOR RULINGS (QC2-A-1 (a): D1-alien compares
pvpBorrow.home with pvpBorrow.parked; QC2-A-2 (a)); owner D250, O1 (a); D154, D155, D180, D181, D231; QC-9, QC-10, QC-11, QC-17 (a).
TASK 0 pins: docs rewrite/d250u-task0/sc2/CONSTANTS.md (first dispatch d250ucb-red: bring-up, HOST0 / CLIENT0, HOST_SQ0 and every FX2
value; RE-DISPATCH d250ucb-red2 on the W2-H37 base: TITLE_WIN / TITLE_ABORT / TITLE_LOSS and the debriefing values, each 2/2).

Boot D: gm3, lobby key 48013, dirs d250uc2_d_host / d250uc2_d_client. Bring-up: PF.start_pvp_campaign(alien_player="host"); HOST0 /
CLIENT0; HOST_SQ0 (the host's soldier_record for every CLIENT0 soldier id); geo.slow_clock. gamemode 3 on both, host noBases true and
client noBases false are bring-up preconditions (FX2-2). A bring-up, staging, entry or row-action miss is a FIXTURE-STOP: ONE
"CAPTURE D:" line (both stacks, battle_state phase / side / turn, coop_dialog_info, get_coop, the last 40 engine log lines) and every
remaining cell FAILs "boot".
Each row stages (FX2-3 .. FX2-7): a fresh host-real mission site at X + the row's point (X = the client's XcomBase), its mirror on the
client, the squad SQ (the two lowest-id client soldiers in its base with recovery 0, re-seated each row), the client's Skyranger forced
out to the mirror, the landing prompt (both drained, speed idx 2), client set_seed SEED then confirm_landing, both inBattle,
session.briefings_to_battlescape, the hash.
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; every row runs after a failure unless its
precondition was never reached, then each of its cells FAILs "blocked: <why>"):
  D1 X-COM wins (host kill_unit_real every live alien; client END TURN; the host's DebriefingState):
     D1-host, D1-client, D1-page3, D1-return, D1-alien, D1-site, D1-common.
  D2 abort (client ABORT, its AbortMissionState OK, the alien host's YES on the vote; the host's DebriefingState):
     D2-host, D2-client, D2-alien, D2-site, D2-return, D2-common.
  D3 X-COM loses (client END TURN; host kill_unit_real every live X-COM unit; host END TURN if needed; the host's DebriefingState):
     D3-host, D3-client, D3-alien, D3-site, D3-return, D3-common.
  <row>-host: host DebriefingState <= 60 s, the row's title, displayOnly false; on page 3 Sell and Transfer hidden.
  <row>-client: the client's display-only DebriefingState <= 20 s; BES.debrief_view equal on BES.DEBRIEF_FIELDS.
  D1-page3: the client's battleEnd.worldAdopted 1 <= 30 s; on page 3 the client's Sell shown.
  <row>-return: the client's OK first -> geo_clean <= 10 s. D1: debriefOkBranch "campaign-client-borrowed", every SQ soldier in its
     base with missions + 1, the Skyranger returning or at base, noBases false. D2: every SQ soldier in its base, the Skyranger
     returning or at base. D3: every SQ soldier dead, the Skyranger gone, the host's records for the SQ ids == HOST_SQ0's.
  <row>-alien: the host's OK -> geo_clean <= 60 s; host noBases true, funds and real bases == HOST0's, pvpBorrow.active false,
     pvpBorrow.home == pvpBorrow.parked (QC2-A-1 (a); the live ids / daysPassed / monthsPassed are EVIDENCE).
  <row>-site: the host-real site gone from the host's globe and its mirror from the client's <= 10 s; pvpBorrow.fate {kind "site",
     action "deleted"}.
  <row>-common: event_state.desyncSeen false on both, 0 new crash files in the row, assert_hash_clean(full=True) EQUAL before the
     row's action.
"Returning" = status STR_OUT with the craft's own base as its destination (TestServer destKind "base"; the engine has no STR_RETURNING
status); "at base" = STR_READY, STR_REFUELLING, STR_REARMING or STR_REPAIRS (SC2-6 item 3; CONSTANTS.md RE-DISPATCH).
RED (C2R on S-C1's green, base 58a185218 with W2-H37): 2/19 cells PASS (D1-client, D1-common); D1-host (the host's Sell shown),
D1-page3, D1-return, D1-alien, D1-site FAIL; the 12 D2 / D3 cells FAIL "blocked: the alien host never went home (D1-alien)".
GREEN (C2G): 19/19.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_battle_gm3_end.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import repro_atom_side_begin as RSB  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_shared_page3 as P3  # noqa: E402

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc2/CONSTANTS.md; boots w / a / l / w2 and the RE-DISPATCH six, 2/2 each) -----
KEY = "48013"
SEED = 1                                     # set on the X-COM CLIENT right before each confirm_landing
TITLE = {"D1": "Aliens defeated", "D2": "Terror continues", "D3": "Craft is lost"}   # TITLE_WIN / TITLE_ABORT / TITLE_LOSS
MAP_FP = {"D1": 5.996615470105667e+18, "D2": -4.990271614617468e+18, "D3": -4.990271614617468e+18}   # EVIDENCE (STOP-IF 13)
SITE = {"mission": "STR_ALIEN_RESEARCH", "deployment": "STR_MEDIUM_SCOUT", "race": "STR_SECTOID", "hours": 240}   # FX2-4
POINT = {"D1": (0.35, 0.10), "D2": (-0.35, 0.10), "D3": (0.10, 0.35)}          # FX2-3: X + point
CRAFT_AT = {"D1": (0.34, 0.10), "D2": (-0.34, 0.10), "D3": (0.09, 0.35)}       # FX2-5: 0.01 rad short in longitude, toward X
SQUAD = 2
AT_BASE = ("STR_READY", "STR_REFUELLING", "STR_REARMING", "STR_REPAIRS")       # SC2-6 item 3
REC4 = ("where", "baseIndex", "name", "dead")                                  # SC2-6 item 2 (HOST_SQ0)
# ----- bounds -----
MIRROR_S = 30
LANDING_S = 180
BOTH_IN_S = 60
ABORT_S = 30
DEBRIEF_S = 60
CLIENT_DEBRIEF_S = 20
ADOPT_S = 30
OK_S = 10
HOST_OK_S = 60
SITE_S = 10
STEP_S = 60
ROWS = {"D1": ["D1-host", "D1-client", "D1-page3", "D1-return", "D1-alien", "D1-site", "D1-common"],
        "D2": ["D2-host", "D2-client", "D2-alien", "D2-site", "D2-return", "D2-common"],
        "D3": ["D3-host", "D3-client", "D3-alien", "D3-site", "D3-return", "D3-common"]}
ALL_CELLS = ROWS["D1"] + ROWS["D2"] + ROWS["D3"]


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, f"blocked: {why}")


def evidence(row, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def row_verdict(row, names):
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def stack(gc):
    return session.states_stripped(gc)


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def coop(gc):
    r = gc.cmd({"cmd": "get_coop"})
    return {k: r.get(k) for k in ("gamemode", "noBases", "coopDialog", "inBattle", "pvpBorrow")}


def real_bases(g):
    return [{"name": b.get("name"), "lon": round(b.get("lon") or 0.0, 9), "lat": round(b.get("lat") or 0.0, 9)}
            for b in g.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")]


def deb(gc):
    return gc.cmd({"cmd": "debrief_state"})


def page3(gc):
    d = deb(gc)
    return {k: d.get(k) for k in ("page", "onTop", "sellVisible", "transferVisible")}


def sky_of(gc, sky0):
    """The X-COM Skyranger (CLIENT0's type / id, coop false) in this machine's real bases: {status, destKind} or None."""
    for b in gc.ok({"cmd": "geo_state"}).get("bases", []):
        if b.get("coopBase") or b.get("coopIcon"):
            continue
        for c in b.get("crafts", []):
            if c.get("type") == sky0["type"] and c.get("id") == sky0["id"] and not c.get("coop"):
                return {"base": b.get("name"), "status": c.get("status"), "destKind": c.get("destKind")}
    return None


def returning_or_at_base(sk):
    return bool(sk) and ((sk.get("status") == "STR_OUT" and sk.get("destKind") == "base") or sk.get("status") in AT_BASE)


def srec(gc, sid):
    return BES.soldier_rec(gc, sid=sid)


def rec4(gc, sid):
    recs, _meta = BES.soldier_recs(gc, sid=sid)
    return [{k: r.get(k) for k in REC4} for r in recs]


def probe(gc):
    r = gc.cmd({"cmd": "research_probe", "names": [], "tail": 0})
    return {k: r.get(k) for k in ("ids", "daysPassed", "monthsPassed")}


def has_site(gc, site_id=None, point=None):
    """host: a real (coop false) site with `site_id`; client: a coop mirror within 0.01 of `point`."""
    for m in gc.ok({"cmd": "geo_state"}).get("missionSites", []):
        if site_id is not None and not m.get("coop") and m.get("id") == site_id:
            return True
        if point is not None and m.get("coop") and abs(m.get("lon", 9.0) - point[0]) < 0.01 \
                and abs(m.get("lat", 9.0) - point[1]) < 0.01:
            return True
    return False


def capture_boot(err, host, client):
    cap = {}
    for gc in (host, client):
        try:
            bs = battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": gc.cmd({"cmd": "get_coop"}),
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE D: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, ev):
    """Spawn, the gm3 campaign (the HOST on the Alien team), HOST0 / CLIENT0 / HOST_SQ0, geo.slow_clock (FX2-2)."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, KEY, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    ch, cc = coop(host), coop(client)
    hg, cg = host.ok({"cmd": "geo_state"}), client.ok({"cmd": "geo_state"})
    rp = probe(host)
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": real_bases(hg), "ids": rp.get("ids"),
             "daysPassed": rp.get("daysPassed"), "monthsPassed": rp.get("monthsPassed")}
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": real_bases(cg),
               "sky": sky and {"type": sky.get("type"), "id": sky.get("id")}, "soldiers": sids}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")])
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions (FX2-2): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    host_sq0 = {sid: rec4(host, sid) for sid in sids}
    ev["HOST_SQ0"] = host_sq0
    geo.slow_clock(host, client)
    return host0, client0, xb, host_sq0


def stage_row(row, host, client, xb, client0, ev):
    """FX2-3 .. FX2-7: SQ, the host site and its mirror, craft_force, the landing prompt, set_seed + confirm, both inBattle, the
    spine. Returns (site_id, point, sq, missions0). A miss = FIXTURE-STOP."""
    geo.slow_clock(host, client)
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        seen = {s: (recs[s].get("where"), recs[s].get("recovery")) for s in sids}
        capture_boot(f"{row}: fewer than {SQUAD} client soldiers in base with recovery 0 (FX2-6): {seen}", host, client)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"{row}: client craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    pre = {sid: srec(client, sid) for sid in sq}
    missions0 = {sid: pre[sid].get("missions") for sid in sq}
    ev.update(SQ=sq, missions0=missions0, clientIdsBefore=probe(client).get("ids"),
              sqBefore={sid: {k: pre[sid].get(k) for k in ("coop", "owner", "missions")} for sid in sq})
    dx, dy = POINT[row]
    point = [xb["lon"] + dx, xb["lat"] + dy]
    site = host.cmd(dict(SITE, cmd="spawn_mission_site", lon=point[0], lat=point[1]))
    if not site.get("ok"):
        capture_boot(f"{row}: host spawn_mission_site {site}", host, client)
    t0, mir = time.time(), None
    while mir is None and time.time() - t0 < MIRROR_S:
        mir = next((m for m in client.ok({"cmd": "geo_state"}).get("missionSites", [])
                    if m.get("coop") and abs(m.get("lon", 9.0) - point[0]) < 0.01 and abs(m.get("lat", 9.0) - point[1]) < 0.01),
                   None)
        if mir is None:
            time.sleep(0.1)
    ev.update(point=point, siteHost=site.get("site_id"), mirrorS=round(time.time() - t0, 2), siteClient=mir and mir.get("id"))
    if mir is None:
        capture_boot(f"{row}: no coop mirror of host site {site.get('site_id')} on the client within {MIRROR_S} s", host, client)
    cx, cy = CRAFT_AT[row]
    cf = client.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + cx, "lat": xb["lat"] + cy,
                     "dest": f"site:{mir['id']}", "fuel": 999999, "lowFuel": False})
    if not cf.get("ok"):
        capture_boot(f"{row}: client craft_force {cf}", host, client)

    def prompt():
        if session.has_state(client, "ConfirmLandingState"):
            return True
        for gc in (host, client):
            geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    t1 = time.time()
    try:
        client.wait_for("client landing prompt", prompt, timeout=LANDING_S, interval=0.25)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"{row}: client landing prompt: {e}", host, client)
    ev.update(promptS=round(time.time() - t1, 2), hostStackAtPrompt=stack(host))
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED}), client.cmd({"cmd": "confirm_landing"})
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"{row}: client set_seed {sd} / confirm_landing {cl}", host, client)
    ok, secs = BES.wait_until(lambda: bool(battle_state(host).get("inBattle")) and bool(battle_state(client).get("inBattle")),
                              BOTH_IN_S)
    ev["bothInS"] = secs
    if not ok:
        capture_boot(f"{row}: not both inBattle within {BOTH_IN_S} s of the client's confirm_landing", host, client)
    try:
        session.briefings_to_battlescape(host, client)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"{row}: session.briefings_to_battlescape: {str(e)[:300]}", host, client)
    bh, bc = battle_state(host), battle_state(client)
    ev.update(turn=[bh.get("turn"), bc.get("turn")], mapFingerprint=[bh.get("mapFingerprint"), bc.get("mapFingerprint")],
              mapFpPin=MAP_FP[row], pvpBorrowAtEntry=coop(host).get("pvpBorrow"))
    return site.get("site_id"), point, sq, missions0


def act(row, host, client, ev):
    """The row's end: FX2-8 (D1 win), FX2-9 (D2 abort), FX2-10 (D3 loss). A step miss = FIXTURE-STOP."""
    a = {}
    ev["action"] = a
    if row == "D1":
        G2F.kill_all(host, client, 1, a, "kills")
        if "DebriefingState" not in stack(host):
            a["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            a["closeNext"] = BES.close_host_nextturn(host)
    elif row == "D2":
        a["abort"] = client.cmd({"cmd": "battle_action", "action": "abort"})
        ok, secs = BES.wait_until(lambda: (stack(client) or [None])[-1] == "AbortMissionState", ABORT_S)
        a["abortStateS"] = secs
        if not ok:
            capture_boot(f"D2: no client AbortMissionState within {ABORT_S} s (stack {stack(client)})", host, client)
        d = client.cmd({"cmd": "dismiss_popup"})
        a["dismiss"] = d.get("handled")
        if d.get("handled") != "AbortMissionState":
            capture_boot(f"D2: client dismiss_popup {d} (want handled AbortMissionState)", host, client)
        try:
            a["vote"] = session.abort_vote_yes(host, host)
        except Exception as e:  # noqa: BLE001
            capture_boot(f"D2: session.abort_vote_yes(host, host): {str(e)[:300]}", host, client)
    else:
        a["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        try:
            RSB.drive_side_change(host, client, 1, timeout=STEP_S)
        except Exception as e:  # noqa: BLE001
            capture_boot(f"D3: drive_side_change to side 1: {str(e)[:300]}", host, client)
        G2F.kill_all(host, client, 0, a, "kills")
        if "DebriefingState" not in stack(host):
            a["hostEndTurn"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            a["closeNext"] = BES.close_host_nextturn(host)


def common(row, host, client, crash0, hash_res):
    eh, ec = event_state(host), event_state(client)
    new = sorted(crash_set() - crash0)
    bad = []
    if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False:
        bad.append(f"desyncSeen host {eh.get('desyncSeen')!r} client {ec.get('desyncSeen')!r} (want false on both)")
    if new:
        bad.append(f"{len(new)} new crash file(s) in the row (first {os.path.basename(new[0])})")
    if hash_res[0] is not True:
        bad.append(f"hash_now full before the action: {hash_res[1]}")
    cell(f"{row}-common", not bad, "; ".join(bad) or "desyncSeen false on both, 0 new crash files, hash_now full EQUAL before "
         "the action")


def return_bad(row, gok, crec, csq, csky, cco, sq, missions0, client):
    """<row>-return's checks on the client after its OK (the D3 host-record check is added after the host's OK)."""
    bad = [] if gok else [f"client not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(client)})"]
    if row == "D1" and crec.get("debriefOkBranch") != "campaign-client-borrowed":
        bad.append(f"battleEnd.debriefOkBranch {crec.get('debriefOkBranch')!r} (want 'campaign-client-borrowed')")
    for sid in sq:
        r = csq[sid]
        if row == "D3":
            if r.get("where") != "dead":
                bad.append(f"SQ {sid}: where {r.get('where')!r} (want 'dead', D181)")
            continue
        want_m = missions0[sid] + 1 if isinstance(missions0[sid], int) else None
        if r.get("where") != "base" or (row == "D1" and r.get("missions") != want_m):
            bad.append(f"SQ {sid}: where {r.get('where')!r} missions {r.get('missions')!r} (want 'base'"
                       + (f", missions {want_m}" if row == "D1" else "") + ")")
    if row == "D3":
        if csky is not None:
            bad.append(f"client Skyranger still in its base: {csky} (want gone)")
    elif not returning_or_at_base(csky):
        bad.append(f"client Skyranger {csky} (want returning: STR_OUT to its own base, or at base {list(AT_BASE)})")
    if row == "D1" and cco.get("noBases") is not False:
        bad.append(f"client noBases {cco.get('noBases')!r} (want false)")
    return bad


def end_row(row, host, client, site_id, point, sq, missions0, host0, client0, host_sq0, ctx, ev):
    """Both debriefings, page 3, the client's OK, the host's OK, the site; the row's cells (not -common)."""
    names = [n for n in ROWS[row] if not n.endswith("-common")]
    title, sky0 = TITLE[row], client0["sky"]
    ok, secs = BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = deb(host)
    ev["hostDebrief"] = {k: v for k, v in hdeb.items() if k != "widgets"}
    if not ok:
        cell(f"{row}-host", False, f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})")
        ctx["blocked"] = f"the host's debriefing never opened ({row}-host)"
        block(names, ctx["blocked"])
        return
    hflip = P3.to_page2(host)
    hp3 = page3(host)
    ev["hostPage3"] = dict(hp3, flipped=hflip)
    hbad = [f"debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in (("title", title), ("displayOnly", False))
            if hdeb.get(k) != w]
    hbad += [f"page 3 not reached (page {hp3.get('page')}, onTop {hp3.get('onTop')})"] if hp3.get("page") != 2 else []
    hbad += [f"page 3 {k} {hp3.get(k)!r} (want false: the alien host never works the X-COM base's page 3, D154)"
             for k in ("sellVisible", "transferVisible") if hp3.get(k) is not False]
    cell(f"{row}-host", not hbad, "; ".join(hbad) or f"host DebriefingState {secs} s, title {title!r}, displayOnly false; page 3 "
         f"Sell and Transfer hidden")
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                         and d.get("displayOnly") is True)(deb(client)), CLIENT_DEBRIEF_S)
    cdeb = deb(client)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(cdeb)
    ev["clientDebrief"] = {k: v for k, v in cdeb.items() if k != "widgets"}
    cbad = [] if cok else [f"no client display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(client)})"]
    cbad += [f"client {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    cell(f"{row}-client", not cbad, "; ".join(cbad) or f"client display-only debriefing {csecs} s, equal on DEBRIEF_FIELDS")
    if row == "D1":
        aok, asecs = BES.wait_until(lambda: (BES.record(client).get("worldAdopted") or 0) >= 1, ADOPT_S)
        cflip = P3.to_page2(client)
        cp3 = page3(client)
        ev["clientPage3"] = dict(cp3, flipped=cflip, worldAdopted=BES.record(client).get("worldAdopted"), adoptS=asecs)
        pbad = [] if aok else [f"client battleEnd.worldAdopted {BES.record(client).get('worldAdopted')!r} after {ADOPT_S} s "
                               f"(want 1)"]
        pbad += [f"client page 3 not reached (page {cp3.get('page')})"] if cp3.get("page") != 2 else []
        if cp3.get("sellVisible") is not True:
            pbad.append(f"client page 3 sellVisible {cp3.get('sellVisible')!r} (want true, D154)")
        cell("D1-page3", not pbad, "; ".join(pbad) or f"client worldAdopted 1 ({asecs} s); page 3 Sell shown")
    # the client's OK first (FX2-12)
    t_ok = time.time()
    pk = BES.press_ok(client)
    _reached, cscreens = BES.drain(client, timeout=OK_S)
    gok, _gs = BES.wait_until(lambda: BES.geo_clean(client), OK_S)
    crec, csky, cco = BES.record(client), sky_of(client, sky0), coop(client)
    csq = {sid: srec(client, sid) for sid in sq}
    cg = client.ok({"cmd": "geo_state"})
    ev["clientOk"] = {"press": pk, "drain": cscreens, "geoClean": gok, "geoS": round(time.time() - t_ok, 2), "stack": stack(client),
                      "debriefOkBranch": crec.get("debriefOkBranch"), "chain": crec.get("chain"),
                      "worldAdopted": crec.get("worldAdopted"), "sky": csky, "noBases": cco.get("noBases"),
                      "sq": {sid: {k: csq[sid].get(k) for k in ("where", "coop", "owner", "missions", "dead")} for sid in sq},
                      "ids": probe(client).get("ids"), "time": cg.get("time"), "battleEnd": crec}
    rbad = return_bad(row, gok, crec, csq, csky, cco, sq, missions0, client)
    if row == "D1":
        cell("D1-return", not rbad, "; ".join(rbad) or "client geo_clean; campaign-client-borrowed; every SQ soldier in base with "
             f"missions + 1; Skyranger {csky}; noBases false")
    # the host's OK (FX2-12): never drain a CoopState 994
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hgok, hgs = BES.wait_until(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    hprobe = probe(host)
    ev["hostOk"] = {"press": hk, "drain": hscreens, "on994": on994, "geoClean": hgok, "geoS": hgs, "stack": stack(host),
                    "noBases": hco.get("noBases"), "funds": hg.get("funds"), "realBases": real_bases(hg), "probe": hprobe,
                    "time": hg.get("time"), "pvpBorrow": pv, "battleEnd": BES.record(host)}
    abad = [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, CoopState 994 {on994}, stack "
                            f"{stack(host)})"]
    abad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    abad += [f"host funds {hg.get('funds')!r} (want HOST0 {host0['funds']!r})"] if hg.get("funds") != host0["funds"] else []
    abad += [f"host real bases {real_bases(hg)} (want HOST0 {host0['realBases']})"] if real_bases(hg) != host0["realBases"] else []
    abad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    if "home" not in pv:
        abad.append("host pvpBorrow.home absent (want == pvpBorrow.parked, QC2-A-1 (a))")
    elif pv.get("home") != pv.get("parked"):
        abad.append(f"host pvpBorrow.home {pv.get('home')} != parked {pv.get('parked')}")
    cell(f"{row}-alien", not abad, "; ".join(abad) or f"host geo_clean ({hgs} s), noBases true, funds and real bases == HOST0, "
         f"pvpBorrow.active false, home == parked")
    gone_ok, gone_s = BES.wait_until(lambda: not has_site(host, site_id=site_id) and not has_site(client, point=point), SITE_S)
    fate = pv.get("fate") or {}
    sbad = [] if gone_ok else [f"after {SITE_S} s: host site {site_id} present {has_site(host, site_id=site_id)}, client mirror "
                               f"present {has_site(client, point=point)} (want both gone)"]
    sbad += [f"host pvpBorrow.fate {pv.get('fate')!r} (want kind 'site', action 'deleted')"] \
        if fate.get("kind") != "site" or fate.get("action") != "deleted" else []
    cell(f"{row}-site", not sbad, "; ".join(sbad) or f"host site {site_id} and its mirror gone ({gone_s} s); fate {fate}")
    if row == "D3":
        hsq = {sid: rec4(host, sid) for sid in sq}
        ev["hostSqAfter"] = hsq
        rbad += [f"host soldier_record {sid}: {hsq[sid]} != HOST_SQ0 {host_sq0.get(sid)}" for sid in sq
                 if hsq[sid] != host_sq0.get(sid)]
    if row != "D1":
        cell(f"{row}-return", not rbad, "; ".join(rbad) or (f"client geo_clean; every SQ soldier in base; Skyranger {csky}"
             if row == "D2" else "client geo_clean; every SQ soldier dead; Skyranger gone; the host's SQ records == HOST_SQ0"))
    ev["times"] = {"host": hg.get("time"), "client": client.ok({"cmd": "geo_state"}).get("time")}
    if not hgok or pv.get("active") is not False or hco.get("noBases") is not True:
        ctx["blocked"] = f"the alien host never went home ({row}-alien)"
    elif not gok:
        ctx["blocked"] = f"the X-COM client never reached its geoscape ({row}-return)"


def run_row(row, host, client, xb, host0, client0, host_sq0, ctx):
    ev = {}
    if ctx["blocked"]:
        block(ROWS[row], ctx["blocked"])
        evidence(row, {"blocked": ctx["blocked"]})
        row_verdict(row, ROWS[row])
        return
    crash0 = crash_set()
    try:
        site_id, point, sq, missions0 = stage_row(row, host, client, xb, client0, ev)
        try:
            session.assert_hash_clean(host, client, full=True)
            hash_res = (True, "EQUAL")
        except Exception as e:  # noqa: BLE001
            hash_res = (False, str(e)[:400])
        ev["hash"] = hash_res[1]
        act(row, host, client, ev)
        end_row(row, host, client, site_id, point, sq, missions0, host0, client0, host_sq0, ctx, ev)
        common(row, host, client, crash0, hash_res)
    finally:
        evidence(row, ev)
    row_verdict(row, ROWS[row])


def main():
    host = GameClient("host", None, make_user_dir("d250uc2_d_host"))
    client = GameClient("client", None, make_user_dir("d250uc2_d_client"))
    t0 = time.time()
    try:
        ev0 = {}
        try:
            host0, client0, xb, host_sq0 = bring_up(host, client, ev0)
        finally:
            evidence("bring-up", ev0)
        ctx = {"blocked": None}
        for row in ("D1", "D2", "D3"):
            run_row(row, host, client, xb, host0, client0, host_sq0, ctx)
    except FixtureMiss as e:
        block(ALL_CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(ALL_CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            host.shutdown()
        finally:
            client.shutdown()
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== D250-U S-C2 gm3 PvP campaign battle end: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
