"""test_campaign_gm3_targets.py: gm3 PvP campaign battles at a UFO and at an alien base (host = the aliens, client =
X-COM). In ONE gm3 campaign the X-COM player wins at a crashed UFO, aborts at a landed UFO and destroys an alien base, each the alien
host's own object reached through its mirror; after each battle the target leaves the alien host's world by vanilla's rule:
the crashed UFO disappears, the landed UFO takes off, the destroyed base goes with its links cleared.

Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md, AMENDMENT SC-3: SC3-7 "Stage S-C5a", SC3-8 (levers T1-T3; product S1-S4), SC3-9
(cells, fixture rules FX5-1 .. FX5-12, FX2-* by reference); rulings QC-11 (a), QC5-1 .. QC5-3 (a); L-D250-SC1-1; F14323, F15327 .. F15330,
F15333; owner D250, O1 (a). TASK 0 pins: docs rewrite/d250u-task0/sc5a/CONSTANTS.md (boots Ta / Tb on the lever build, Tc on the green
premise: TITLE_U1 / TITLE_U2 3/3, TITLE_A1 in Tc; F15570 .. F15577).

Boot T: gm3, lobby key 48022, dirs d250uc5_t_host / d250uc5_t_client. Bring-up (FX5-2 = FX3-2 + the crash baseline):
PF.start_pvp_campaign(alien_player="host"); HOST0 / CLIENT0 / xb; geo.slow_clock. gamemode 3 on both, host noBases true and client
noBases false are preconditions. A bring-up, staging or row-action miss is a FIXTURE-STOP: ONE "CAPTURE T:" line (both stacks,
battle_state phase / side / turn, coop_dialog_info, get_coop, the last 40 engine log lines) and every remaining cell FAILs "boot".
Each row (FX5-3 .. FX5-10): SQ (the two lowest-id client soldiers in its base with recovery 0), the HOST's target at X + the row's point
(X = the client's XcomBase) and its mirror on the client (UCOOP / ACOOP read at run time), the client's Skyranger forced out to the mirror
by coop id (lever T1: craft_force dest "ufoCoop:" / "alienBaseCoop:"), the landing prompt (both drained, speed idx 2), client set_seed 1
then confirm_landing, both inBattle, session.briefings_to_battlescape, the hash, the action, both debriefings, the client's OK, the
host's OK, the target's fate.
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; a row whose landing never borrowed FAILs its
other six cells "blocked: <why>"):
  U1 crashed UFO + X-COM wins (G2F.kill_all faction 1; client END TURN + the host's NextTurnState closed while no host debriefing).
  U2 landed UFO + abort (client ABORT, its AbortMissionState OK, the alien host's YES on the vote).
  A1 alien base + X-COM wins (spawn_alien_base race STR_SECTOID, lever T2; host_alien_base_found; kill_all as U1).
  <row>-hand: client pvpBorrow sent / pushed / held +1; host pvpBorrow borrowed +1, targetKind "ufo" / "alienBase", targetMirror true,
     targetCoopId == UCOOP / ACOOP, craftType / craftId == the client's Skyranger; both inBattle <= 60 s; the spine passed.
  <row>-host: host DebriefingState <= 60 s, title TITLE[row], displayOnly false.
  <row>-client: the client's display-only DebriefingState <= 20 s, equal to the host's on BES.DEBRIEF_FIELDS.
  <row>-return: client geo_clean <= 10 s after its OK; debriefOkBranch "campaign-client-borrowed"; every SQ soldier where "base" (U1, A1:
     missions == missions0 + 1); the Skyranger returning or at base (G3E.returning_or_at_base).
  <row>-alien: host geo_clean <= 60 s after its OK; noBases true; funds and real bases == HOST0; pvpBorrow.active false; home == parked.
  <row>-target: U1 fate {ufo, UCOOP, "deleted"}, then <= 10 s no host real UFO (coop false, coopId UCOOP) and no client mirror. U2 fate
     {ufo, UCOOP, "takeoff"}, then host geo_set_speed idx 0 and <= LIFT_S the host's real UFO status 0 or absent. A1 fate {alienBase,
     ACOOP, "deleted"}, then <= 10 s no host real base (alien_base_state coop false, coopId ACOOP) and no client mirror.
  <row>-common: event_state.desyncSeen false on both, 0 new crash files since the row's start, assert_hash_clean(full=True) EQUAL before
     the action.
RED (C5R, the lever build): 12/21 cells PASS; FAIL U1-target and U2-target (fate "untouched", the real UFO stays: F15330), A1-hand (refused
"target": F15328) and A1-host .. A1-common ("blocked: the alien base landing never borrowed (A1-hand)"). GREEN (C5G): 21/21.

ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm3_targets.py
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
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc5a/CONSTANTS.md) -----
KEY = "48022"
SEED = 1                                     # set on the X-COM CLIENT right before each confirm_landing
TITLE = {"U1": "UFO is recovered", "U2": "UFO is not recovered", "A1": "Alien Base destroyed"}       # FX5-12
MAP_FP = {"U1": -5.462816325144846e+18, "U2": 3.3951652687105495e+18, "A1": -7.901758915371136e+18}  # EVIDENCE only
UFO = {"type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID",
       "trajectory": "P0", "hours": 240}                                       # FX5-4
POINT = {"U1": (0.35, 0.10), "U2": (-0.35, 0.10), "A1": (0.10, 0.35)}          # FX5-3: X + point
CRAFT_AT = {"U1": (0.34, 0.10), "U2": (-0.34, 0.10), "A1": (0.09, 0.35)}       # FX5-6: 0.01 rad short in longitude, toward X
KIND = {"U1": "ufo", "U2": "ufo", "A1": "alienBase"}
ACTION = {"U1": "deleted", "U2": "takeoff", "A1": "deleted"}
NAMES = {"U1": "UFO", "U2": "UFO", "A1": "alien base"}
SQUAD = 2
# ----- bounds -----
MIRROR_S = 30
LANDING_S = 180
BOTH_IN_S = 60
ABORT_S = 30
DEBRIEF_S = 60
CLIENT_DEBRIEF_S = 20
OK_S = 10
HOST_OK_S = 60
TARGET_S = 10
LIFT_S = 30                                  # FX5-11
CELLS = ("hand", "host", "client", "return", "alien", "target", "common")
ROWS = {r: [f"{r}-{c}" for c in CELLS] for r in ("U1", "U2", "A1")}
ALL_CELLS = ROWS["U1"] + ROWS["U2"] + ROWS["A1"]


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


def pvp(gc):
    return gc.cmd({"cmd": "get_coop"}).get("pvpBorrow") or {}


def icon_bases(gc):
    return [{k: b.get(k) for k in ("name", "lon", "lat")} for b in gc.ok({"cmd": "geo_state"}).get("bases", []) if b.get("coopIcon")]


def ufos(gc):
    return [{k: u.get(k) for k in ("id", "coopId", "coop", "status")} for u in gc.ok({"cmd": "geo_state"}).get("ufos", [])]


def abases(gc):
    return [{k: a.get(k) for k in ("id", "coopId", "coop", "discovered", "race")}
            for a in gc.ok({"cmd": "alien_base_state"}).get("alienBases", [])]


def target_of(row, host, client, tc):
    """(the host's real target entries, the client's mirror entries) with coop id `tc`."""
    get = ufos if KIND[row] == "ufo" else abases
    return ([x for x in get(host) if not x.get("coop") and x.get("coopId") == tc],
            [x for x in get(client) if x.get("coop") and x.get("coopId") == tc])


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
    print(f"CAPTURE T: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, ev):
    """Spawn, the gm3 campaign (the HOST on the Alien team), HOST0 / CLIENT0 / xb, the crash baseline, geo.slow_clock (FX5-2)."""
    ev["crashBaseline"] = len(crash_set())
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, KEY, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    ch, cc = G3E.coop(host), G3E.coop(client)
    hg, cg = host.ok({"cmd": "geo_state"}), client.ok({"cmd": "geo_state"})
    rp = G3E.probe(host)
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "ids": rp.get("ids"),
             "daysPassed": rp.get("daysPassed"), "monthsPassed": rp.get("monthsPassed")}
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": G3E.real_bases(cg),
               "sky": sky and {"type": sky.get("type"), "id": sky.get("id")}, "soldiers": sids}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")])
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions (FX3-2): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    geo.slow_clock(host, client)
    return host0, client0, xb


def spawn_target(row, host, client, point, ev):
    """FX5-4 / FX5-5: the HOST's own UFO or alien base at `point` and its mirror on the client. Returns (coop id, craft dest)."""
    if KIND[row] == "ufo":
        sp = host.cmd(dict(UFO, cmd="spawn_ufo", state="crashed" if row == "U1" else "landed", lon=point[0], lat=point[1]))
        real = next((u for u in ufos(host) if not u.get("coop") and u.get("id") == sp.get("ufo_id")), None) if sp.get("ok") else None
        prefix = "ufoCoop"
    else:
        sp = host.cmd({"cmd": "spawn_alien_base", "lon": point[0], "lat": point[1], "race": "STR_SECTOID"})
        fd = host.cmd({"cmd": "host_alien_base_found", "alien_base_id": sp.get("alien_base_id")}) if sp.get("ok") else {}
        real = next((a for a in abases(host) if not a.get("coop") and a.get("id") == sp.get("alien_base_id")), None) \
            if fd.get("ok") else None
        prefix = "alienBaseCoop"
    ev.update(spawn=sp, hostReal=real)
    if not real:
        capture_boot(f"{row}: the host's {NAMES[row]} (spawn {sp}) not found in its own world", host, client)
    tc = real["coopId"]
    t0, mir = time.time(), None
    while mir is None and time.time() - t0 < MIRROR_S:
        mir = next((x for x in (ufos(client) if KIND[row] == "ufo" else abases(client))
                    if x.get("coop") and x.get("coopId") == tc and (KIND[row] == "ufo" or x.get("discovered"))), None)
        if mir is None:
            time.sleep(0.1)
    ev.update(targetCoopId=tc, mirrorS=round(time.time() - t0, 2), mirror=mir)
    if mir is None:
        capture_boot(f"{row}: no client mirror of the host's {NAMES[row]} (coop id {tc}) within {MIRROR_S} s", host, client)
    return tc, f"{prefix}:{tc}"


def stage_row(row, host, client, xb, client0, ev):
    """FX5-3 .. FX5-8: SQ, the target and its mirror, craft_force, the prompt, set_seed + confirm, the entry wait. Returns
    (sq, missions0, tc, pv_client0, pv_host0, entered, entry_s). A miss before the confirm = FIXTURE-STOP."""
    geo.slow_clock(host, client)
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        seen = {s: (recs[s].get("where"), recs[s].get("recovery")) for s in sids}
        capture_boot(f"{row}: fewer than {SQUAD} client soldiers in base with recovery 0 (FX2-6): {seen}", host, client)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"{row}: client craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    missions0 = {sid: G3E.srec(client, sid).get("missions") for sid in sq}
    pv_c0, pv_h0 = pvp(client), pvp(host)
    ev.update(SQ=sq, missions0=missions0, clientIdsBefore=G3E.probe(client).get("ids"), iconBasesBefore=icon_bases(client))
    dx, dy = POINT[row]
    point = [xb["lon"] + dx, xb["lat"] + dy]
    ev["point"] = point
    tc, dest = spawn_target(row, host, client, point, ev)
    cx, cy = CRAFT_AT[row]
    cf = client.cmd({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": xb["lon"] + cx, "lat": xb["lat"] + cy,
                     "dest": dest, "fuel": 999999, "lowFuel": False})
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
    rel0 = pv_c0.get("released") or 0
    _entered, secs = BES.wait_until(lambda: (bool(battle_state(host).get("inBattle")) and bool(battle_state(client).get("inBattle")))
                                   or (pvp(client).get("released") or 0) > rel0, BOTH_IN_S)
    both = bool(battle_state(host).get("inBattle")) and bool(battle_state(client).get("inBattle"))
    ev.update(bothInS=secs if both else None, stacksAfterConfirm={"host": stack(host), "client": stack(client)})
    return sq, missions0, tc, pv_c0, pv_h0, both, secs


def hand_cell(row, host, client, tc, client0, pv_c0, pv_h0, both, secs, ev):
    """<row>-hand: the hand-off record deltas, both inBattle, the spine. Returns True when the battle runs."""
    pc, ph = pvp(client), pvp(host)
    ev.update(pvpClientAfterConfirm=pc, pvpHostAfterConfirm={k: v for k, v in ph.items() if k not in ("parked", "home")})
    sky = client0["sky"]
    bad = [f"client pvpBorrow.{k} {pv_c0.get(k) or 0} -> {pc.get(k) or 0} (want +1)" for k in ("sent", "pushed", "held")
           if (pc.get(k) or 0) != (pv_c0.get(k) or 0) + 1]
    if (ph.get("borrowed") or 0) != (pv_h0.get("borrowed") or 0) + 1:
        bad.append(f"host pvpBorrow.borrowed {pv_h0.get('borrowed') or 0} -> {ph.get('borrowed') or 0} (want +1); host lastRefuse "
                   f"{ph.get('lastRefuse')!r}; client lastRefuseSeen {pc.get('lastRefuseSeen')!r}, released "
                   f"{pv_c0.get('released') or 0} -> {pc.get('released') or 0}")
    else:
        want = {"targetKind": KIND[row], "targetMirror": True, "targetCoopId": tc, "craftType": sky["type"], "craftId": sky["id"]}
        bad += [f"host pvpBorrow.{k} {ph.get(k)!r} (want {w!r})" for k, w in want.items() if ph.get(k) != w]
    if not both:
        bad.append(f"not both inBattle within {BOTH_IN_S} s of the confirm (stacks host {stack(host)} client {stack(client)})")
    else:
        try:
            session.briefings_to_battlescape(host, client)
        except Exception as e:  # noqa: BLE001
            bad.append(f"session.briefings_to_battlescape: {str(e)[:300]}")
            both = False
    if both:
        bh, bc = battle_state(host), battle_state(client)
        units = bh.get("units", [])
        ev.update(turn=[bh.get("turn"), bc.get("turn")], mapFingerprint=[bh.get("mapFingerprint"), bc.get("mapFingerprint")],
                  mapFpPin=MAP_FP[row], aliens=len([u for u in units if u.get("faction") == 1 and not u.get("isOut")]))
    cell(f"{row}-hand", not bad, "; ".join(bad) or f"hand-off +1 on both records, host borrowed the X-COM world (target "
         f"{KIND[row]} {tc}, mirror), both inBattle {secs} s, spine passed")
    return both


def act(row, host, client, ev):
    """FX5-9: U1 / A1 FX2-8 (kills, END TURN), U2 FX2-9 (the abort vote). A step miss = FIXTURE-STOP."""
    a = {}
    ev["action"] = a
    if row in ("U1", "A1"):
        t0 = time.time()
        G2F.kill_all(host, client, 1, a, "kills")
        a["killS"] = round(time.time() - t0, 2)
        if "DebriefingState" not in stack(host):
            a["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            a["closeNext"] = BES.close_host_nextturn(host)
        return
    a["abort"] = client.cmd({"cmd": "battle_action", "action": "abort"})
    ok, secs = BES.wait_until(lambda: (stack(client) or [None])[-1] == "AbortMissionState", ABORT_S)
    a["abortStateS"] = secs
    if not ok:
        capture_boot(f"U2: no client AbortMissionState within {ABORT_S} s (stack {stack(client)})", host, client)
    d = client.cmd({"cmd": "dismiss_popup"})
    a["dismiss"] = d.get("handled")
    if d.get("handled") != "AbortMissionState":
        capture_boot(f"U2: client dismiss_popup {d} (want handled AbortMissionState)", host, client)
    try:
        a["vote"] = session.abort_vote_yes(host, host)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"U2: session.abort_vote_yes(host, host): {str(e)[:300]}", host, client)


def target_cell(row, host, client, tc, pv, ev):
    fate = pv.get("fate") or {}
    want = {"kind": KIND[row], "coopId": tc, "action": ACTION[row]}
    bad = [f"host pvpBorrow.fate {pv.get('fate')!r} (want {want})"] if {k: fate.get(k) for k in want} != want else []
    if row == "U2":
        ev["liftSpeed"] = host.cmd({"cmd": "geo_set_speed", "idx": 0}).get("ok")
        ok, secs = BES.wait_until(lambda: all(u.get("status") == 0 for u in target_of(row, host, client, tc)[0]), LIFT_S)
        hr, cm = target_of(row, host, client, tc)
        ev.update(liftS=secs if ok else None, targetAfter={"host": hr, "client": cm})
        if not ok:
            bad.append(f"after {LIFT_S} s at speed idx 0 the host's real UFO {hr} (want status 0 or absent)")
        detail = f"fate {fate}; the host's real UFO lifted or gone ({secs} s)"
    else:
        ok, secs = BES.wait_until(lambda: target_of(row, host, client, tc) == ([], []), TARGET_S)
        hr, cm = target_of(row, host, client, tc)
        ev.update(goneS=secs if ok else None, targetAfter={"host": hr, "client": cm})
        if not ok:
            bad.append(f"after {TARGET_S} s the host's real {NAMES[row]} {hr} and the client's mirror {cm} (want both gone)")
        detail = f"fate {fate}; the host's real {NAMES[row]} and the client's mirror gone ({secs} s)"
    cell(f"{row}-target", not bad, "; ".join(bad) or detail)


def end_row(row, host, client, tc, sq, missions0, host0, client0, ctx, ev):
    """Both debriefings, the client's OK, the host's OK, the target; the row's cells (not -hand / -common)."""
    names = [f"{row}-{c}" for c in ("host", "client", "return", "alien", "target")]
    ok, secs = BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    hdeb = G3E.deb(host)
    ev["hostDebrief"] = {k: hdeb.get(k) for k in ("title", "displayOnly", "rating", "total", "rows")}
    if not ok:
        cell(f"{row}-host", False, f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})")
        ctx["blocked"] = f"the host's debriefing never opened ({row}-host)"
        block(names, ctx["blocked"])
        return
    hbad = [f"debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in (("title", TITLE[row]), ("displayOnly", False))
            if hdeb.get(k) != w]
    cell(f"{row}-host", not hbad, "; ".join(hbad) or f"host DebriefingState {secs} s, title {TITLE[row]!r}, displayOnly false")
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                         and d.get("displayOnly") is True)(G3E.deb(client)), CLIENT_DEBRIEF_S)
    cdeb = G3E.deb(client)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(cdeb)
    ev["clientDebrief"] = {k: cdeb.get(k) for k in ("title", "displayOnly", "rating", "total")}
    cbad = [] if cok else [f"no client display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(client)})"]
    cbad += [f"client {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    cell(f"{row}-client", not cbad, "; ".join(cbad) or f"client display-only debriefing {csecs} s, equal on DEBRIEF_FIELDS")
    # the client's OK first (FX2-12)
    t_ok = time.time()
    pk = BES.press_ok(client)
    _reached, cscreens = BES.drain(client, timeout=OK_S)
    gok, _gs = BES.wait_until(lambda: BES.geo_clean(client), OK_S)
    crec, csky = BES.record(client), G3E.sky_of(client, client0["sky"])
    csq = {sid: G3E.srec(client, sid) for sid in sq}
    ev["clientOk"] = {"press": pk.get("pressed"), "drain": cscreens, "geoClean": gok, "geoS": round(time.time() - t_ok, 2),
                      "debriefOkBranch": crec.get("debriefOkBranch"), "worldAdopted": crec.get("worldAdopted"), "sky": csky,
                      "sq": {sid: {k: csq[sid].get(k) for k in ("where", "missions", "dead")} for sid in sq},
                      "ids": G3E.probe(client).get("ids"), "iconBases": icon_bases(client), "pvpBorrow": pvp(client)}
    rbad = [] if gok else [f"client not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(client)})"]
    if crec.get("debriefOkBranch") != "campaign-client-borrowed":
        rbad.append(f"battleEnd.debriefOkBranch {crec.get('debriefOkBranch')!r} (want 'campaign-client-borrowed')")
    for sid in sq:
        r = csq[sid]
        want_m = missions0[sid] + 1 if isinstance(missions0[sid], int) else None
        if r.get("where") != "base" or (row != "U2" and r.get("missions") != want_m):
            rbad.append(f"SQ {sid}: where {r.get('where')!r} missions {r.get('missions')!r} (want 'base'"
                        + (f", missions {want_m}" if row != "U2" else "") + ")")
    if not G3E.returning_or_at_base(csky):
        rbad.append(f"client Skyranger {csky} (want returning: STR_OUT to its own base, or at base {list(G3E.AT_BASE)})")
    cell(f"{row}-return", not rbad, "; ".join(rbad) or f"client geo_clean; campaign-client-borrowed; every SQ soldier in base"
         + ("" if row == "U2" else " with missions + 1") + f"; Skyranger {csky}")
    # the host's OK (FX2-12): never drain a CoopState 994
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hgok, hgs = BES.wait_until(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    ev["hostOk"] = {"press": hk.get("pressed"), "drain": hscreens, "on994": on994, "geoClean": hgok, "geoS": hgs, "stack": stack(host),
                    "noBases": hco.get("noBases"), "funds": hg.get("funds"), "probe": G3E.probe(host),
                    "pvpBorrow": {k: v for k, v in pv.items() if k not in ("parked", "home")}, "parked": pv.get("parked")}
    abad = [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, CoopState 994 {on994}, stack "
                            f"{stack(host)})"]
    abad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    abad += [f"host funds {hg.get('funds')!r} (want HOST0 {host0['funds']!r})"] if hg.get("funds") != host0["funds"] else []
    abad += [f"host real bases {G3E.real_bases(hg)} (want HOST0 {host0['realBases']})"] \
        if G3E.real_bases(hg) != host0["realBases"] else []
    abad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    if "home" not in pv:
        abad.append("host pvpBorrow.home absent (want == pvpBorrow.parked, QC2-A-1 (a))")
    elif pv.get("home") != pv.get("parked"):
        abad.append(f"host pvpBorrow.home {pv.get('home')} != parked {pv.get('parked')}")
    cell(f"{row}-alien", not abad, "; ".join(abad) or f"host geo_clean ({hgs} s), noBases true, funds and real bases == HOST0, "
         f"pvpBorrow.active false, home == parked")
    target_cell(row, host, client, tc, pv, ev)
    ev["times"] = {"host": host.ok({"cmd": "geo_state"}).get("time"), "client": client.ok({"cmd": "geo_state"}).get("time")}
    if not hgok or pv.get("active") is not False or hco.get("noBases") is not True:
        ctx["blocked"] = f"the alien host never went home ({row}-alien)"
    elif not gok:
        ctx["blocked"] = f"the X-COM client never reached its geoscape ({row}-return)"


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


def run_row(row, host, client, xb, host0, client0, ctx):
    ev = {}
    if ctx["blocked"]:
        block(ROWS[row], ctx["blocked"])
        evidence(row, {"blocked": ctx["blocked"]})
        row_verdict(row, ROWS[row])
        return
    crash0 = crash_set()
    try:
        sq, missions0, tc, pv_c0, pv_h0, both, secs = stage_row(row, host, client, xb, client0, ev)
        if not hand_cell(row, host, client, tc, client0, pv_c0, pv_h0, both, secs, ev):
            ev.update(target=target_of(row, host, client, tc), sky=G3E.sky_of(client, client0["sky"]),
                      stacks={"host": stack(host), "client": stack(client)})
            block(ROWS[row], f"the {NAMES[row]} landing never borrowed ({row}-hand)")
            if not (stack(host)[-1:] == ["GeoscapeState"] and stack(client)[-1:] == ["GeoscapeState"]):
                ctx["blocked"] = f"a machine left off its globe after {row}-hand (stacks {ev['stacks']})"
        else:
            try:
                session.assert_hash_clean(host, client, full=True)
                hash_res = (True, "EQUAL")
            except Exception as e:  # noqa: BLE001
                hash_res = (False, str(e)[:400])
            ev["hash"] = hash_res[1]
            act(row, host, client, ev)
            end_row(row, host, client, tc, sq, missions0, host0, client0, ctx, ev)
            common(row, host, client, crash0, hash_res)
    finally:
        evidence(row, ev)
    row_verdict(row, ROWS[row])


def main():
    host = GameClient("host", None, make_user_dir("d250uc5_t_host"))
    client = GameClient("client", None, make_user_dir("d250uc5_t_client"))
    t0 = time.time()
    try:
        ev0 = {}
        try:
            host0, client0, xb = bring_up(host, client, ev0)
        finally:
            evidence("bring-up", ev0)
        ctx = {"blocked": None}
        for row in ("U1", "U2", "A1"):
            run_row(row, host, client, xb, host0, client0, ctx)
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
    print(f"\n==== D250-U S-C5a gm3 campaign battles at UFOs and alien bases: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
