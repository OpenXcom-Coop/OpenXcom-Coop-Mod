"""D250-U S-C5b1 - test_campaign_gm3_cydonia.py: a gm3 PvP campaign's Cydonia from the X-COM player's craft (host = the aliens,
client = X-COM). The X-COM player's YES on Cydonia (real play's stack: the destination picker under the confirmation) hands it to the
alien host, which runs both stages in the X-COM player's borrowed world; both play both stages; the X-COM player's stage-2 abort with the
alien host's YES ends the campaign as vanilla on both machines (no debriefing, the ending, the statistics); both reach the main menu.
Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md AMENDMENT SC-4 (SC4-3, SC4-5 row K1, FX5B-1 .. FX5B-10) and its ORCHESTRATOR
RULINGS (QC5B-1 .. QC5B-7 (a)); owner D250, O1 (a); D239 (a); D158 (a); D231 / VL-C-6. TASK 0 pins: docs
rewrite/d250u-task0/sc5b1/CONSTANTS.md (P-C5b1 2/2 on boots Ka / Ka2; the green premise boot Kb; the walls).

Boot K: gm3, key 48027, dirs d250uc5b_k_host / _client. Bring-up (FX5B-2): PF.start_pvp_campaign(alien_player="host"), HOST0 / CLIENT0,
gamemode 3 on both / host noBases true / client false as preconditions, geo.slow_clock. Staging (FX5B-3, FX5B-4): SQ = the two lowest-id
client base soldiers with recovery 0 alone on the client's Skyranger; the client drained to GeoscapeState; open_select_destination then
open_cydonia (stack [GeoscapeState, SelectDestinationState, ConfirmCydoniaState]); client set_seed 1, confirm_cydonia. A bring-up,
staging or abort-step miss is a FIXTURE-STOP: ONE "CAPTURE K:" line (both stacks, battle_state phase / side / turn / missionType,
coop_dialog_info, get_coop, the last 40 engine log lines) and every remaining cell FAILs "boot".
Row K1 (one PASS / FAIL line per cell, one EVIDENCE line, one ROW line; a cell whose precondition was never reached FAILs "blocked: <why>"):
  K1-hand    both inBattle <= ENTRY_S; client pvpBorrow sent / pushed / held +1; host requests / armed / borrowed +1, kind and targetKind
             "cydonia", craftType / craftId == SKY; 0 new client WARN lines; the spine passed; both missionType STR_MARS_CYDONIA_LANDING.
  K1-seats   census equal on both: faction 0 = SQ on seat 1, faction 1 on seat 0 with hasAI false, no other faction; host
             pvpBorrow.active true; host noBases false.
  K1-stage   (FX5B-6 host kill_all faction 1; with no host BriefingState: client END TURN, the host's NextTurnState closed) both stage-2
             BriefingState <= STAGE_S; after the spine both BattlescapeState, turn 1, STR_MARS_THE_FINAL_ASSAULT, map and battleId equal
             (> stage 1's); census as K1-seats with faction 0 a non-empty subset of SQ; host borrowed unchanged, active true.
  K1-end     (FX5B-7 client abort, its AbortMissionState OK, abort_vote_yes(host, host); FX5B-8 poll every POLL_S, never a dismiss)
             within END_S both ending_state {ending 2, statistics true}; no DebriefingState at any poll; Slideshow / VideoState seen on
             both; the client's battleEnd {applied 1, reason abort, gameOver true}, hashVerify (else lastHashVerify) = {battle_end, host seq}.
  K1-menu    (FX5B-9 host statistics_ok, then client) both [MainMenuState] <= MENU_S; host pvpBorrow active false, dropped +1; host
             noBases false; both processes alive.
  K1-common  desyncSeen false on both before the vote; assert_hash_clean(full=True) EQUAL after each spine; 0 new crash files.
RED (C5B1R on 59fa2ed3a): exit 2, 0/6 - K1-hand FAILs with the client's local Cydonia battle (P-C5b1: host never in battle, the
non-host warning +1, no borrow); K1-seats .. K1-common FAIL "blocked: the alien host never borrowed (K1-hand)". GREEN (C5B1G): 6/6.
ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm3_cydonia.py
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

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc5b1/CONSTANTS.md; boots Ka / Ka2 2/2, the green premise Kb) -----
KEY = "48027"
SEED = 1                                     # set on the X-COM CLIENT right before confirm_cydonia (FX5B-4)
SQUAD = 2
MISSION_1, MISSION_2 = "STR_MARS_CYDONIA_LANDING", "STR_MARS_THE_FINAL_ASSAULT"
MAP_FP = {1: -3.7087676953867494e+18, 2: 3.1168362819169787e+18}    # EVIDENCE only (FX5B-10, STOP-IF 13)
ROUTE = ["GeoscapeState", "SelectDestinationState", "ConfirmCydoniaState"]
WARN = "offerBattle() called on a non-host machine - ignoring"
END_LOSE = 2
# ----- bounds (s; TASK 0 measured entry 1.41, stage 2 4.13, AbortMissionState 0.05, ending 0.0, menus 0.1) -----
ENTRY_S, STAGE_S, ABORT_S, END_S, MENU_S, POLL_S = 60, 30, 30, 30, 30, 0.5
CELLS = ["K1-hand", "K1-seats", "K1-stage", "K1-end", "K1-menu", "K1-common"]
RESULTS = []          # (cell, ok, detail)


class FixtureMiss(Exception):
    pass


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, f"blocked: {why}")


def rc(gc):
    return None if gc.proc is None else gc.proc.poll()


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return f"probe failed ({type(e).__name__}: {str(e)[:120]}), rc={rc(gc)}"


def has(gc, name):
    st = stack(gc)
    return isinstance(st, list) and any(name in s for s in st)


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def pvp(gc):
    return gc.cmd({"cmd": "get_coop"}).get("pvpBorrow") or {}


def bview(gc):
    b = battle_state(gc)
    return {"inBattle": b.get("inBattle"), "missionType": b.get("missionType"), "mapFingerprint": b.get("mapFingerprint"),
            "turn": b.get("turn"), "side": b.get("side"), "battleId": (b.get("authority") or {}).get("battleId")}


def census(gc):
    return [{k: u.get(k) for k in ("id", "faction", "coop", "hasAI", "isOut")} for u in battle_state(gc).get("units", [])]


def ending(gc):
    r = gc.cmd({"cmd": "ending_state"})
    return {k: r.get(k) for k in ("hasSave", "ending", "statistics", "campaignEnded")}


def attempt(fn, ok_text):
    try:
        fn()
        return True, ok_text
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:400]}"


def seats_bad(hcen, ccen, sq, subset):
    """K1-seats' census rule on both machines; subset=True (stage 2): faction-0 ids a non-empty subset of SQ."""
    bad = []
    for nm, cen in (("host", hcen), ("client", ccen)):
        f0 = sorted(u["id"] for u in cen if u.get("faction") == 0)
        if (subset and (not f0 or not set(f0) <= set(sq))) or (not subset and f0 != sorted(sq)):
            bad.append(f"{nm}: faction 0 ids {f0} (want {'a non-empty subset of ' if subset else ''}SQ {sorted(sq)})")
        bad += [f"{nm}: unit {u['id']} faction 0 seat {u.get('coop')}" for u in cen if u.get("faction") == 0 and u.get("coop") != 1]
        bad += [] if any(u.get("faction") == 1 for u in cen) else [f"{nm}: no faction 1 unit"]
        bad += [f"{nm}: unit {u['id']} faction 1 seat {u.get('coop')} hasAI {u.get('hasAI')}" for u in cen
                if u.get("faction") == 1 and (u.get("coop") != 0 or u.get("hasAI") is not False)]
        bad += [f"{nm}: unit {u['id']} faction {u.get('faction')}" for u in cen if u.get("faction") not in (0, 1)]
    key = lambda cen: sorted((u["id"], u.get("faction"), u.get("coop"), u.get("hasAI")) for u in cen)  # noqa: E731
    if key(hcen) != key(ccen):
        bad.append(f"census (id, faction, seat, hasAI) host {key(hcen)} != client {key(ccen)}")
    return bad


def capture_boot(err, host, client):
    cap = {}
    for gc in (host, client):
        try:
            bs = battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "rc": rc(gc),
                            "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn", "missionType")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": gc.cmd({"cmd": "get_coop"}),
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE K: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, ev):
    """FX5B-2: G3E's bring_up with this file's KEY (no HOST_SQ0)."""
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
        capture_boot(f"bring-up preconditions (FX5B-2): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    geo.slow_clock(host, client)
    return client0


def stage(host, client, client0, ev):
    """FX5B-3 (SQ) and FX5B-4 (the route) up to the client's confirm_cydonia. Returns (sq, w0, t_confirm). A miss = FIXTURE-STOP."""
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        capture_boot(f"fewer than {SQUAD} client base soldiers with recovery 0 (FX5B-3): "
                     f"{ {s: (recs[s].get('where'), recs[s].get('recovery')) for s in sids} }", host, client)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"client craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client)
    drained, _hit = geo.drain_popups(client)
    if (stack(client) or [None])[-1] != "GeoscapeState":
        capture_boot(f"client top {stack(client)} after drain_popups {drained} (want GeoscapeState, FX5B-4)", host, client)
    osd = client.cmd({"cmd": "open_select_destination", "craft_id": sky["id"], "craft_type": "STR_SKYRANGER"})
    oc = client.cmd({"cmd": "open_cydonia", "craft_id": sky["id"]}) if osd.get("ok") else {}
    route = stack(client)
    ev.update(SQ=sq, drained=drained, openSelectDestination=osd, openCydonia=oc, clientRoute=route, hostStackAtConfirm=stack(host),
              pvpBefore={"host": pvp(host), "client": pvp(client)})
    if not osd.get("ok") or not oc.get("ok") or route != ROUTE:
        capture_boot(f"the route (FX5B-4): open_select_destination {osd}, open_cydonia {oc}, client stack {route} (want {ROUTE})",
                     host, client)
    w0 = BES.log_count(client, WARN)
    sd = client.cmd({"cmd": "set_seed", "seed": SEED})
    t_confirm = time.time()
    cf = client.cmd({"cmd": "confirm_cydonia"})
    if not sd.get("ok") or not cf.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_cydonia {cf}", host, client)
    ev["stacksAfterConfirm"] = [stack(host), stack(client)]
    return sq, w0, t_confirm


def k1_hand(host, client, client0, sq, w0, tc, ev, ctx):
    p0 = ev["pvpBefore"]
    ok, _s = BES.wait_until(lambda: bool(bview(host).get("inBattle")) and bool(bview(client).get("inBattle")), ENTRY_S)
    secs = round(time.time() - tc, 2)
    hb, cb = bview(host), bview(client)
    ev.update(entryS=secs, stacksAtEntry=[stack(host), stack(client)], localClientBattle=None if hb.get("inBattle") else cb)
    sp_ok, sp_detail = attempt(lambda: session.briefings_to_battlescape(host, client), "spine passed") if ok else (False, "")
    hp, cp = pvp(host), pvp(client)
    warn = BES.log_count(client, WARN) - w0
    hb, cb = bview(host), bview(client)
    ev.update(pvpHand={"host": hp, "client": cp}, warnDelta=warn, battle1={"host": hb, "client": cb})
    d = lambda new, old, k: (new.get(k) or 0) - (old.get(k) or 0)  # noqa: E731
    bad = [f"client pvpBorrow.{k} +{d(cp, p0['client'], k)} (want +1)" for k in ("sent", "pushed", "held") if d(cp, p0["client"], k) != 1]
    bad += [f"host pvpBorrow.{k} +{d(hp, p0['host'], k)} (want +1)" for k in ("requests", "armed", "borrowed")
            if d(hp, p0["host"], k) != 1]
    sky = client0["sky"]
    bad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in (("kind", "cydonia"), ("craftType", "STR_SKYRANGER"),
            ("craftId", sky["id"]), ("targetKind", "cydonia")) if hp.get(k) != w]
    bad += [f"{warn} new client log line(s) '{WARN}' (want 0)"] if warn != 0 else []
    if cb.get("inBattle") and not hb.get("inBattle"):
        bad.append(f"the client's local battle: client inBattle true ({cb.get('missionType')}), host inBattle false {secs} s after "
                   f"the confirm (stacks host {ev['stacksAtEntry'][0]} client {ev['stacksAtEntry'][1]})")
    elif not ok:
        bad.append(f"inBattle host/client {[hb.get('inBattle'), cb.get('inBattle')]} {secs} s after the confirm (want both)")
    elif not sp_ok:
        bad.append(f"session.briefings_to_battlescape raised {sp_detail} (stacks {[stack(host), stack(client)]})")
    else:
        bad += [f"{nm} missionType {b.get('missionType')!r} (want {MISSION_1!r})" for nm, b in (("host", hb), ("client", cb))
                if b.get("missionType") != MISSION_1]
    cell("K1-hand", not bad, "; ".join(bad) or f"both inBattle {secs} s after the confirm; client sent / pushed / held +1; host requests / "
         f"armed / borrowed +1, kind / targetKind cydonia, {sky['type']}-{sky['id']}; 0 non-host warnings; spine passed; {MISSION_1}")
    if not hb.get("inBattle") or d(hp, p0["host"], "borrowed") != 1:
        ctx["blocked"] = "the alien host never borrowed (K1-hand)"
    elif not (ok and sp_ok):
        ctx["blocked"] = "both machines never reached the stage-1 battlescape (K1-hand)"
    return hp


def k1_seats(host, client, sq, ev, ctx):
    hcen, ccen = census(host), census(client)
    ctx["hash"].append(("stage 1",) + attempt(lambda: session.assert_hash_clean(host, client, full=True, what="stage 1"), "EQUAL"))
    hp, nb = pvp(host), G3E.coop(host).get("noBases")
    ev.update(census1={"host": hcen, "client": ccen}, mapFp1Pin=MAP_FP[1])
    bad = seats_bad(hcen, ccen, sq, subset=False)
    bad += [f"host pvpBorrow.active {hp.get('active')!r} (want true)"] if hp.get("active") is not True else []
    bad += [f"host get_coop.noBases {nb!r} (want false: the live world is X-COM's)"] if nb is not False else []
    cell("K1-seats", not bad, "; ".join(bad) or f"census equal on both ({len(hcen)} units): SQ {sorted(sq)} on seat 1, faction 1 on seat "
         "0 without AI; host borrows (active), noBases false")


def k1_stage(host, client, sq, hp_hand, ev, ctx):
    a = {}
    ev["stage1Action"] = a
    b1 = bview(host).get("battleId")
    G2F.kill_all(host, client, 1, a, "kills")
    if not has(host, "BriefingState"):
        a["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        a["closeNext"] = BES.close_host_nextturn(host)
    ok, secs = BES.wait_until(lambda: has(host, "BriefingState") and has(client, "BriefingState"), STAGE_S, 0.1)
    ev.update(stage2BriefingS=secs, stacksAtStage2=[stack(host), stack(client)])
    bad = [] if ok else [f"not both stage-2 BriefingState within {STAGE_S} s (stacks host {stack(host)} client {stack(client)})"]
    sp_ok, sp_detail = attempt(lambda: session.briefings_to_battlescape(host, client), "spine passed") if ok else (False, "")
    bad += [f"stage-2 briefings_to_battlescape raised {sp_detail} (stacks {[stack(host), stack(client)]})"] if ok and not sp_ok else []
    hb, cb, hp = bview(host), bview(client), pvp(host)
    ev.update(battle2={"host": hb, "client": cb}, mapFp2Pin=MAP_FP[2], pvpStage2=hp, battleId1=b1)
    if ok and sp_ok:
        ctx["hash"].append(("stage 2",) + attempt(lambda: session.assert_hash_clean(host, client, full=True, what="stage 2"), "EQUAL"))
        hcen, ccen = census(host), census(client)
        ev["census2"] = {"host": hcen, "client": ccen}
        for nm, gc, b in (("host", host, hb), ("client", client, cb)):
            if (stack(gc) or [None])[-1] != "BattlescapeState" or b.get("turn") != 1 or b.get("missionType") != MISSION_2:
                bad.append(f"{nm} top {(stack(gc) or [None])[-1]} turn {b.get('turn')} missionType {b.get('missionType')!r} (want "
                           f"BattlescapeState, 1, {MISSION_2!r})")
        if hb.get("mapFingerprint") is None or hb.get("mapFingerprint") != cb.get("mapFingerprint"):
            bad.append(f"mapFingerprint host {hb.get('mapFingerprint')!r} != client {cb.get('mapFingerprint')!r}")
        if not (isinstance(hb.get("battleId"), int) and isinstance(b1, int) and hb.get("battleId") > b1
                and cb.get("battleId") == hb.get("battleId")):
            bad.append(f"battleId host {hb.get('battleId')} client {cb.get('battleId')} (want equal and > stage 1's {b1})")
        bad += seats_bad(hcen, ccen, sq, subset=True)
    if hp.get("borrowed") != hp_hand.get("borrowed") or hp.get("active") is not True:
        bad.append(f"host pvpBorrow borrowed {hp.get('borrowed')} (K1-hand {hp_hand.get('borrowed')}) active {hp.get('active')!r} "
                   "(want unchanged, true: one borrow carries both stages)")
    cell("K1-stage", not bad, "; ".join(bad) or f"both stage-2 briefings {secs} s; turn 1 {MISSION_2} on both, map and battleId "
         f"{hb.get('battleId')} (> {b1}) equal; census as K1-seats; one borrow (borrowed {hp.get('borrowed')}, active)")
    if not (ok and sp_ok):
        ctx["blocked"] = "both machines never reached the stage-2 battlescape (K1-stage)"


def k1_end(host, client, ev, ctx):
    ctx["desync"] = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    v = ev.setdefault("vote", {})
    v["abort"] = client.cmd({"cmd": "battle_action", "action": "abort"})
    ok, v["abortStateS"] = BES.wait_until(lambda: (stack(client) or [None])[-1] == "AbortMissionState", ABORT_S, 0.1)
    if not ok:
        capture_boot(f"no client AbortMissionState within {ABORT_S} s (stack {stack(client)})", host, client)
    d = client.cmd({"cmd": "dismiss_popup"})
    v["dismiss"] = d.get("handled")
    if d.get("handled") != "AbortMissionState":
        capture_boot(f"client dismiss_popup {d} (want handled AbortMissionState)", host, client)
    try:
        v["vote"] = session.abort_vote_yes(host, host)
    except Exception as e:  # noqa: BLE001
        capture_boot(f"session.abort_vote_yes(host, host): {str(e)[:300]}", host, client)
    p = ev.setdefault("poll", {"debrief": {}, "slideshow": {}, "video": {}, "statistics": {}, "polls": []})
    tv = time.time()
    while True:
        ts = round(time.time() - tv, 2)
        for gc in (host, client):
            st, e = stack(gc), ending(gc)
            p["polls"].append([ts, gc.name, st, e])
            for key, name in (("debrief", "DebriefingState"), ("slideshow", "SlideshowState"), ("video", "VideoState")):
                if isinstance(st, list) and any(name in s for s in st):
                    p[key].setdefault(gc.name, ts)
            if e.get("ending") == END_LOSE and e.get("statistics"):
                p["statistics"].setdefault(gc.name, ts)
        if sorted(p["statistics"]) == ["client", "host"] or ts >= END_S:
            break
        time.sleep(max(0.0, POLL_S - (time.time() - tv - ts)))
    eh, ec = event_state(host), event_state(client)
    hbe, cbe = eh.get("battleEnd") or {}, ec.get("battleEnd") or {}
    hv = cbe.get("hashVerify") if isinstance(cbe.get("hashVerify"), dict) else ec.get("lastHashVerify")
    ev.update(battleEnd={"host": hbe, "client": cbe}, clientVerify=hv)
    both = sorted(p["statistics"]) == ["client", "host"]
    bad = [] if both else [f"ending {END_LOSE} + statistics not on both within {END_S} s: {p['statistics']} (last host {ending(host)} "
                           f"client {ending(client)})"]
    bad += [f"a DebriefingState on a stack (s after the vote): {p['debrief']}"] if p["debrief"] else []
    seen = {n for k in ("slideshow", "video") for n in p[k]}
    bad += [f"SlideshowState / VideoState seen on {sorted(seen)} (want both)"] if seen != {"client", "host"} else []
    bad += [f"client battleEnd {k} {cbe.get(k)!r} (want {w!r})" for k, w in (("applied", 1), ("reason", "abort"), ("gameOver", True))
            if cbe.get(k) != w]
    if not isinstance(hv, dict) or hv.get("kind") != "battle_end" or hv.get("seq") != hbe.get("seq"):
        bad.append(f"client battle_end verify {hv} (want kind battle_end, seq {hbe.get('seq')})")
    cell("K1-end", not bad, "; ".join(bad) or f"ending {END_LOSE} + statistics on both at {p['statistics']} s; no debriefing; "
         f"slideshow / video on both; the client applied battle_end (abort, gameOver) hash-clean at seq {hbe.get('seq')}")
    if not both:
        ctx["blocked"] = "the ending never reached both statistics screens (K1-end)"


def k1_menu(host, client, ev):
    dropped0 = ev["pvpHand"]["host"].get("dropped") or 0
    m = {"host": host.cmd({"cmd": "statistics_ok"}), "client": client.cmd({"cmd": "statistics_ok"})}
    ok, secs = BES.wait_until(lambda: stack(host) == ["MainMenuState"] and stack(client) == ["MainMenuState"], MENU_S)
    hp, nb = pvp(host), G3E.coop(host).get("noBases")
    ev["menus"] = dict(m, secs=secs, stacks=[stack(host), stack(client)], pvpHost=hp, noBases=nb, rc=[rc(host), rc(client)])
    bad = [] if ok else [f"not both [MainMenuState] within {MENU_S} s (stacks host {stack(host)} client {stack(client)}; "
                         f"statistics_ok {m})"]
    bad += [f"host pvpBorrow.active {hp.get('active')!r} (want false)"] if hp.get("active") is not False else []
    bad += [f"host pvpBorrow.dropped {hp.get('dropped')!r} (want {dropped0 + 1})"] if (hp.get("dropped") or 0) != dropped0 + 1 else []
    bad += [f"host get_coop.noBases {nb!r} (want false, F15326)"] if nb is not False else []
    bad += [f"{gc.name} process exited rc={rc(gc)}" for gc in (host, client) if rc(gc) is not None]
    cell("K1-menu", not bad, "; ".join(bad) or f"both main menus {secs} s after the statistics OKs; host pvpBorrow active false, "
         f"dropped {dropped0 + 1}, noBases false; both alive")


def k1_common(host, client, ctx, crash0):
    if "desync" not in ctx:          # the vote never ran (K1-stage blocked it): desyncSeen now
        ctx["desync"] = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen before the vote host {ctx['desync'][0]!r} client {ctx['desync'][1]!r} (want false on both)"] \
        if ctx["desync"] != [False, False] else []
    bad += [f"hash_now full after the {w} spine: {d}" for w, ok, d in ctx["hash"] if not ok]
    bad += [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    cell("K1-common", not bad, "; ".join(bad) or f"desyncSeen false on both before the vote; hash EQUAL after "
         f"{len(ctx['hash'])} spine(s); 0 new crash files")


def run_k1(host, client, client0, ev):
    ctx = {"blocked": None, "hash": []}
    crash0 = crash_set()
    sq, w0, tc = stage(host, client, client0, ev)
    hp_hand = k1_hand(host, client, client0, sq, w0, tc, ev, ctx)
    for fn in (lambda: k1_seats(host, client, sq, ev, ctx), lambda: k1_stage(host, client, sq, hp_hand, ev, ctx),
               lambda: k1_end(host, client, ev, ctx), lambda: k1_menu(host, client, ev)):
        if ctx["blocked"]:
            break
        fn()
    if ctx["blocked"] and ctx["blocked"].endswith("(K1-hand)"):
        block(CELLS, ctx["blocked"])
        return
    if ctx["blocked"]:
        block(CELLS[:-1], ctx["blocked"])
    k1_common(host, client, ctx, crash0)


def main():
    host = GameClient("host", None, make_user_dir("d250uc5b_k_host"))
    client = GameClient("client", None, make_user_dir("d250uc5b_k_client"))
    t0, ev = time.time(), {}
    try:
        try:
            client0 = bring_up(host, client, ev)
            run_k1(host, client, client0, ev)
        finally:
            try:
                with open(os.path.join(host.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as fh:
                    ev["hostRv21Lines"] = [ln.rstrip() for ln in fh if "[coop-guest" in ln]
            except OSError as e:
                ev["hostRv21Lines"] = f"unreadable: {e}"
            print(f"EVIDENCE K1: {json.dumps(dict(ev, wall=round(time.time() - t0, 1)), sort_keys=True, default=str)}", flush=True)
    except FixtureMiss as e:
        block(CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            host.shutdown()
        finally:
            client.shutdown()
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"ROW K1: {'PASS' if not fails else 'FAIL'}" + (f" ({len(fails)} failing: {fails})" if fails else ""), flush=True)
    print(f"\n==== D250-U S-C5b1 gm3 PvP campaign Cydonia: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(CELLS) else 2)


if __name__ == "__main__":
    main()
