"""test_campaign_gm3_basedef.py: an attack on the X-COM player's own base in a gm3 PvP campaign (host = the aliens,
client = X-COM). The X-COM player's base defence is handed to the alien host, which runs it in the X-COM player's
borrowed world; both play it; X-COM wins; the X-COM player's world keeps the result and the alien host goes home to its
own world. The pinned values (title, map fingerprint, bounds) were measured on several boots.

Boot: gm3, key 48028, dirs campaign_gm3_basedef_host / _client. Bring-up: PF.start_pvp_campaign(alien_player="host"),
HOST0 / CLIENT0, gamemode 3 on both / host noBases true / client false as preconditions, geo.slow_clock. The tank:
client give_items STR_TANK_LASER_CANNON x1, TANK0 = the client's base_report storage. The attack: the client's
spawn_base_assault UFO never arrives (DESTROYED at its first waypoint with the tank still in the stores, on four boots),
so the attack is a client spawn_ufo (the UFO arguments) + client trigger_base_defense {ufo_id} (the handler called
directly, logged; no setupDefenses on the client, so client_return's tank value is EVIDENCE only). Then geo_set_speed
idx 1 on both until the client's top is CoopState code 3 or the UFO is gone from the client's globe (<= ARRIVE_S, plain
popups drained), then idx 0. The waits that need the hand-off (both inBattle, the battle) run only after it (client
pvpBorrow.sent +1 or its CoopState 3 seen). A bring-up or staging miss is a setup failure: ONE "CAPTURE boot:" line
(both stacks, battle_state phase / side / turn / missionType, coop_dialog_info, get_coop, the last 40 engine log lines)
and every remaining cell FAILs "boot".
Row base_defense (one PASS / FAIL line per cell, one EVIDENCE line, one ROW line; a cell whose precondition was never
reached FAILs "blocked: <why>"):
  hand_off        client top CoopState code 3 <= ARRIVE_S of the attack; client pvpBorrow sent / pushed / held +1;
                  host borrowed +1, kind "baseDefense", targetKind "base", targetMirror false; both inBattle
                  <= ENTRY_S; the spine passed; both missionType STR_BASE_DEFENSE.
  seat_census     census equal on both: faction 0 on seat 1 (soldier ids a non-empty subset of CLIENT0's soldiers plus
                  one STR_TANK_LASER_CANNON vehicle unit), faction 1 on seat 0 with hasAI false; host geo_state real
                  bases == CLIENT0's; host pvpBorrow.active true.
  host_debrief    (host kill_all faction 1; while no host DebriefingState: client END TURN, the host's NextTurnState
                  closed) host DebriefingState <= DEBRIEF_S, title TITLE_WIN, displayOnly false; its page 3 Sell and
                  Transfer hidden.
  client_debrief  client display-only DebriefingState <= CLIENT_DEBRIEF_S; BES.debrief_view equal on
                  BES.DEBRIEF_FIELDS.
  client_return   (the client's OK first) client geo_clean <= OK_S; battleEnd.debriefOkBranch
                  "campaign-client-borrowed", worldAdopted 1; the client's real base present; client noBases false.
                  Its tank storage vs TANK0: EVIDENCE (no setupDefenses on the client).
  alien_home      (the host's OK) host geo_clean <= HOST_OK_S; noBases true; funds and real bases == HOST0;
                  pvpBorrow.active false; home == parked; fate {kind "base", coopId == targetCoopId, action
                  "untouched"}.
  no_desync       desyncSeen false on both; 0 new crash files since the row's start; assert_hash_clean(full=True)
                  EQUAL before the kills.
A failure looks like this: exit 2, 0/7 - hand_off FAILs (the client clears the defence and starts nothing: no
hand-off, no borrow, no battle); the other six FAIL "blocked: no borrowed base defence (hand_off)".
ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm3_basedef.py
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
import battle_end_helpers as BES  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402
import test_campaign_battle_gm3_end as G3E  # noqa: E402
import test_shared_page3 as P3  # noqa: E402

# ----- pins -----
KEY = "48028"
TANK = "STR_TANK_LASER_CANNON"               # the tank given to the client (TANK0 1 in 4/4 boots)
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}     # the attacking UFO (see the module docstring)
MISSION = "STR_BASE_DEFENSE"
TITLE_WIN = "Base is saved"                    # the host's debriefing title after the win
MAP_FP = 8.531978294236504e+18               # EVIDENCE only; a mismatch never fails
KEEP = ("CoopState", "BriefingState", "BattlescapeState", "BaseDefenseState", "DebriefingState", "ConfirmLandingState", "Profile")
# ----- bounds (s) -----
# measured: hand-off 0.35, both inBattle 1.71, host debriefing 0.05 after the end turn, client 0.05, OKs 0.35 / 0.05
ARRIVE_S, ENTRY_S, DEBRIEF_S, CLIENT_DEBRIEF_S, OK_S, HOST_OK_S = 30, 60, 60, 20, 10, 60
CELLS = ["hand_off", "seat_census", "host_debrief", "client_debrief", "client_return", "alien_home", "no_desync"]
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


def dlg(gc):
    r = gc.cmd({"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible")}


def bview(gc):
    b = battle_state(gc)
    return {"inBattle": b.get("inBattle"), "phase": b.get("phase"), "missionType": b.get("missionType"),
            "mapFingerprint": b.get("mapFingerprint"), "turn": b.get("turn"), "battleId": (b.get("authority") or {}).get("battleId")}


def census(gc):
    return [{k: u.get(k) for k in ("id", "faction", "coop", "hasAI", "isOut", "type", "soldierId")}
            for u in battle_state(gc).get("units", [])]


def storage(gc):
    r = gc.cmd({"cmd": "base_report"})
    return {"name": r.get("name"), "tank": (r.get("storage") or {}).get(TANK, 0), "error": r.get("error")}


def my_ufo(gc, uid):
    return [u for u in gc.ok({"cmd": "geo_state"}).get("ufos", []) if u.get("id") == uid and not u.get("coop")]


def attempt(fn, ok_text):
    try:
        fn()
        return True, ok_text
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:400]}"


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
    print(f"CAPTURE boot: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, ev):
    """test_campaign_battle_gm3_end's bring_up with this file's KEY (no HOST_SQ0)."""
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
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": G3E.real_bases(cg),
               "base": xb and xb.get("name"), "soldiers": sids}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")])
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions: gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sids:
        capture_boot(f"the client has no real base / soldiers (base {xb and xb.get('name')}, soldiers {sids})", host, client)
    geo.slow_clock(host, client)
    return host0, client0


def attack(host, client, client0, ev):
    """The tank, then the attack (the spawn_ufo route, see the module docstring). Returns the attack record."""
    a = ev.setdefault("attack", {})
    gi = client.cmd({"cmd": "give_items", "item": TANK, "count": 1})
    st0 = storage(client)
    a.update(giveItems=gi, TANK0=st0["tank"], storageBefore=st0, pvpBefore={"host": pvp(host), "client": pvp(client)})
    if not gi.get("ok") or st0["name"] != client0["base"]:
        capture_boot(f"client give_items {TANK}: {gi}, base_report {st0} (the item missing = setup failure)", host, client)
    su = client.cmd(dict(UFO))
    if not su.get("ok"):
        capture_boot(f"client spawn_ufo: {su}", host, client)
    tb = client.cmd({"cmd": "trigger_base_defense", "ufo_id": su.get("ufo_id")})
    ta = time.time()
    a.update(spawnUfo=su, trigger=tb, stacksAfterTrigger=[stack(host), stack(client)])
    if not tb.get("ok") or tb.get("base") != client0["base"]:
        capture_boot(f"client trigger_base_defense {tb} (want base {client0['base']!r})", host, client)
    a["speed1"] = [gc.cmd({"cmd": "geo_set_speed", "idx": 1}).get("ok") for gc in (host, client)]
    how, coop3, drained = None, None, []
    while time.time() - ta < ARRIVE_S:
        cs, d = stack(client), dlg(client)
        if isinstance(cs, list) and cs[-1:] == ["CoopState"] and d.get("code") == 3:
            how, coop3 = "the client's top CoopState code 3", round(time.time() - ta, 2)
            break
        if not my_ufo(client, su.get("ufo_id")):
            how = "the UFO gone from the client's globe"
            break
        for gc in (host, client):
            dd, _hit = geo.drain_popups(gc, interest=geo.popup(*KEEP))
            drained += [[gc.name, round(time.time() - ta, 2), dd]] if dd else []
        time.sleep(0.25)
    a.update(ended=how, endedS=round(time.time() - ta, 2), coop3S=coop3, drained=drained,
             stacksAtEnd=[stack(host), stack(client)], pvpAtEnd={"host": pvp(host), "client": pvp(client)}, storageAtEnd=storage(client))
    a["speed0"] = [gc.cmd({"cmd": "geo_set_speed", "idx": 0}).get("ok") for gc in (host, client)]
    sent = lambda p: p.get("sent") or 0  # noqa: E731
    a["handed"] = coop3 is not None or sent(a["pvpAtEnd"]["client"]) > sent(a["pvpBefore"]["client"])
    return a, ta


def check_hand_off(host, client, a, ta, ev, ctx):
    p0 = a["pvpBefore"]
    d = lambda new, old, k: (new.get(k) or 0) - (old.get(k) or 0)  # noqa: E731
    if not a["handed"]:
        hb, cb, hp, cp = bview(host), bview(client), pvp(host), pvp(client)
        ev.update(noHandOff={"battle": [hb, cb], "pvp": {"host": hp, "client": cp}, "stacks": [stack(host), stack(client)]})
        cell("hand_off", False, f"no hand-off: the attack ended with {a['ended']} {a['endedS']} s after the trigger, the client's top "
             f"never CoopState code 3; client pvpBorrow sent / pushed / held +{d(cp, p0['client'], 'sent')} / "
             f"+{d(cp, p0['client'], 'pushed')} / +{d(cp, p0['client'], 'held')}, host borrowed +{d(hp, p0['host'], 'borrowed')}; "
             f"inBattle host / client {[hb.get('inBattle'), cb.get('inBattle')]} (stacks host {stack(host)} client {stack(client)})")
        ctx["blocked"] = "no borrowed base defence (hand_off)"
        return {}
    ok, secs = BES.wait_until(lambda: bool(bview(host).get("inBattle")) and bool(bview(client).get("inBattle")), ENTRY_S)
    ev.update(entryS=secs, stacksAtEntry=[stack(host), stack(client)])
    sp_ok, sp_detail = attempt(lambda: session.briefings_to_battlescape(host, client), "spine passed") if ok else (False, "")
    hp, cp, hb, cb = pvp(host), pvp(client), bview(host), bview(client)
    ev.update(pvpHand={"host": hp, "client": cp}, battle={"host": hb, "client": cb}, mapFpPin=MAP_FP)
    bad = [] if a["coop3S"] is not None else [f"the client's top never CoopState code 3 within {ARRIVE_S} s of the attack"]
    bad += [f"client pvpBorrow.{k} +{d(cp, p0['client'], k)} (want +1)" for k in ("sent", "pushed", "held") if d(cp, p0["client"], k) != 1]
    bad += [f"host pvpBorrow.borrowed +{d(hp, p0['host'], 'borrowed')} (want +1)"] if d(hp, p0["host"], "borrowed") != 1 else []
    bad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in (("kind", "baseDefense"), ("targetKind", "base"),
            ("targetMirror", False)) if hp.get(k) != w]
    if not ok:
        bad.append(f"inBattle host / client {[hb.get('inBattle'), cb.get('inBattle')]} {secs} s after the hand-off (want both)")
    elif not sp_ok:
        bad.append(f"session.briefings_to_battlescape raised {sp_detail} (stacks {[stack(host), stack(client)]})")
    else:
        bad += [f"{nm} missionType {b.get('missionType')!r} (want {MISSION!r})" for nm, b in (("host", hb), ("client", cb))
                if b.get("missionType") != MISSION]
    cell("hand_off", not bad, "; ".join(bad) or f"the client held on CoopState 3 ({a['coop3S']} s after the attack); client sent / pushed / "
         f"held +1; host borrowed +1, baseDefense, target base {hp.get('targetCoopId')} (not a mirror); both inBattle {secs} s; spine "
         f"passed; {MISSION} on both")
    if not hb.get("inBattle") or d(hp, p0["host"], "borrowed") != 1:
        ctx["blocked"] = "no borrowed base defence (hand_off)"
    elif not (ok and sp_ok):
        ctx["blocked"] = "both machines never reached the borrowed battlescape (hand_off)"
    return hp


def check_seats(host, client, client0, ev, ctx):
    hcen, ccen = census(host), census(client)
    ctx["hash"] = attempt(lambda: session.assert_hash_clean(host, client, full=True, what="before the kills"), "EQUAL")
    hp, hg = pvp(host), host.ok({"cmd": "geo_state"})
    ev.update(census={"host": hcen, "client": ccen}, hostRealBasesInBattle=G3E.real_bases(hg), hash=ctx["hash"][1])
    bad = []
    for nm, cen in (("host", hcen), ("client", ccen)):
        f0 = [u for u in cen if u.get("faction") == 0]
        sol = sorted(u.get("soldierId") for u in f0 if u.get("soldierId", -1) != -1)
        veh = [u.get("type") for u in f0 if u.get("soldierId", -1) == -1]
        if not sol or not set(sol) <= set(client0["soldiers"]):
            bad.append(f"{nm}: faction-0 soldier ids {sol} (want a non-empty subset of CLIENT0's {client0['soldiers']})")
        if veh != [TANK]:
            bad.append(f"{nm}: faction-0 vehicle units {veh} (want exactly one {TANK})")
        bad += [f"{nm}: unit {u['id']} faction 0 seat {u.get('coop')}" for u in f0 if u.get("coop") != 1]
        bad += [] if any(u.get("faction") == 1 for u in cen) else [f"{nm}: no faction 1 unit"]
        bad += [f"{nm}: unit {u['id']} faction 1 seat {u.get('coop')} hasAI {u.get('hasAI')}" for u in cen
                if u.get("faction") == 1 and (u.get("coop") != 0 or u.get("hasAI") is not False)]
    key = lambda cen: sorted((u["id"], u.get("faction"), u.get("coop"), u.get("hasAI"), u.get("type")) for u in cen)  # noqa: E731
    bad += [f"census host {key(hcen)} != client {key(ccen)}"] if key(hcen) != key(ccen) else []
    bad += [f"host real bases {G3E.real_bases(hg)} (want CLIENT0's {client0['realBases']}: the live world is X-COM's)"] \
        if G3E.real_bases(hg) != client0["realBases"] else []
    bad += [f"host pvpBorrow.active {hp.get('active')!r} (want true)"] if hp.get("active") is not True else []
    cell("seat_census", not bad, "; ".join(bad) or f"census equal on both ({len(hcen)} units): X-COM soldiers and the {TANK} on seat 1, faction 1 "
         "on seat 0 without AI; the host's live world holds CLIENT0's bases; host borrows (active)")


def check_end(host, client, client0, host0, hp_hand, ev, ctx):
    a = ev.setdefault("end", {})
    ctx["desync"] = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    G2F.kill_all(host, client, 1, a, "kills")
    if not has(host, "DebriefingState"):
        a["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        a["closeNext"] = BES.close_host_nextturn(host)
    ok, secs = BES.wait_until(lambda: has(host, "DebriefingState"), DEBRIEF_S)
    hdeb = G3E.deb(host)
    ev["hostDebrief"] = {k: v for k, v in hdeb.items() if k != "widgets"}
    if not ok:
        cell("host_debrief", False, f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})")
        ctx["blocked"] = "the host's debriefing never opened (host_debrief)"
        return
    flip = P3.to_page2(host)
    hp3 = G3E.page3(host)
    ev["hostPage3"] = dict(hp3, flipped=flip)
    hbad = [f"debrief_state.{k}={hdeb.get(k)!r} (want {w!r})" for k, w in (("title", TITLE_WIN), ("displayOnly", False)) if hdeb.get(k) != w]
    hbad += [f"page 3 not reached (page {hp3.get('page')}, onTop {hp3.get('onTop')})"] if hp3.get("page") != 2 else []
    hbad += [f"page 3 {k} {hp3.get(k)!r} (want false)" for k in ("sellVisible", "transferVisible") if hp3.get(k) is not False]
    cell("host_debrief", not hbad, "; ".join(hbad) or f"host DebriefingState {secs} s, title {TITLE_WIN!r}, displayOnly false; page 3 Sell and "
         "Transfer hidden")
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                         and d.get("displayOnly") is True)(G3E.deb(client)), CLIENT_DEBRIEF_S)
    cdeb = G3E.deb(client)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(cdeb)
    ev["clientDebrief"] = {k: v for k, v in cdeb.items() if k != "widgets"}
    cbad = [] if cok else [f"no client display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(client)})"]
    cbad += [f"client {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    cell("client_debrief", not cbad,
         "; ".join(cbad) or f"client display-only debriefing {csecs} s, equal on DEBRIEF_FIELDS")
    # the client's OK first
    t_ok = time.time()
    pk = BES.press_ok(client)
    _reached, screens = BES.drain(client, timeout=OK_S)
    gok, _gs = BES.wait_until(lambda: BES.geo_clean(client), OK_S)
    crec, cco, cg, cst = BES.record(client), G3E.coop(client), client.ok({"cmd": "geo_state"}), storage(client)
    ev["clientOk"] = {"press": pk, "drain": screens, "geoS": round(time.time() - t_ok, 2), "stack": stack(client), "noBases": cco.get("noBases"),
                      "battleEnd": {k: crec.get(k) for k in ("debriefOkBranch", "worldAdopted", "chain", "applied", "reason")},
                      "realBases": G3E.real_bases(cg), "storageAfterReturn": cst, "tankVsTANK0": [cst["tank"], ev["attack"]["TANK0"]],
                      "time": cg.get("time"), "pvp": pvp(client)}
    rbad = [] if gok else [f"client not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(client)})"]
    rbad += [f"battleEnd.{k} {crec.get(k)!r} (want {w!r})" for k, w in (("debriefOkBranch", "campaign-client-borrowed"),
             ("worldAdopted", 1)) if crec.get(k) != w]
    rbad += [f"the client's real bases {G3E.real_bases(cg)} (want its base {client0['base']!r} present)"] \
        if client0["base"] not in [b["name"] for b in G3E.real_bases(cg)] else []
    rbad += [f"client noBases {cco.get('noBases')!r} (want false)"] if cco.get("noBases") is not False else []
    cell("client_return", not rbad, "; ".join(rbad) or f"client geo_clean; campaign-client-borrowed, worldAdopted 1; {client0['base']} present; "
         f"noBases false (tank {cst['tank']} vs TANK0 {ev['attack']['TANK0']}: EVIDENCE)")
    # the host's OK: never drain a CoopState 994
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hgok, hgs = BES.wait_until(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    ev["hostOk"] = {"press": hk, "drain": hscreens, "on994": on994, "geoS": hgs, "stack": stack(host), "noBases": hco.get("noBases"),
                    "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "probe": G3E.probe(host), "time": hg.get("time"), "pvpBorrow": pv}
    abad = [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, CoopState 994 {on994}, stack {stack(host)})"]
    abad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    abad += [f"host funds {hg.get('funds')!r} (want HOST0 {host0['funds']!r})"] if hg.get("funds") != host0["funds"] else []
    abad += [f"host real bases {G3E.real_bases(hg)} (want HOST0 {host0['realBases']})"] if G3E.real_bases(hg) != host0["realBases"] else []
    abad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    abad += ["host pvpBorrow.home absent (want == parked)"] if "home" not in pv else \
        ([f"host pvpBorrow.home {pv.get('home')} != parked {pv.get('parked')}"] if pv.get("home") != pv.get("parked") else [])
    want = {"kind": "base", "coopId": hp_hand.get("targetCoopId"), "action": "untouched"}
    abad += [f"host pvpBorrow.fate {pv.get('fate')!r} (want {want})"] if pv.get("fate") != want else []
    cell("alien_home", not abad, "; ".join(abad) or f"host geo_clean ({hgs} s), noBases true, funds and real bases == HOST0, active false, "
         f"home == parked, fate {want}")


def check_common(host, client, ctx, crash0):
    if "desync" not in ctx:
        ctx["desync"] = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    after = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen host / client {ctx['desync']} before the kills, {after} at the end (want false on both)"] \
        if ctx["desync"] != [False, False] or after != [False, False] else []
    bad += [f"hash_now full before the kills: {ctx['hash'][1]}"] if not ctx["hash"][0] else []
    bad += [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    cell("no_desync", not bad, "; ".join(bad) or "desyncSeen false on both; hash EQUAL before the kills; 0 new crash files")


def run_row(host, client, host0, client0, ev):
    ctx = {"blocked": None}
    crash0 = crash_set()
    a, ta = attack(host, client, client0, ev)
    hp_hand = check_hand_off(host, client, a, ta, ev, ctx)
    if ctx["blocked"]:
        block(CELLS, ctx["blocked"])
        return
    check_seats(host, client, client0, ev, ctx)
    check_end(host, client, client0, host0, hp_hand, ev, ctx)
    if ctx["blocked"]:
        block(CELLS[:-1], ctx["blocked"])
    check_common(host, client, ctx, crash0)


def main():
    host = GameClient("host", None, make_user_dir("campaign_gm3_basedef_host"))
    client = GameClient("client", None, make_user_dir("campaign_gm3_basedef_client"))
    t0, ev = time.time(), {}
    try:
        try:
            host0, client0 = bring_up(host, client, ev)
            run_row(host, client, host0, client0, ev)
        finally:
            print(f"EVIDENCE base_defense: {json.dumps(dict(ev, wall=round(time.time() - t0, 1)), sort_keys=True, default=str)}", flush=True)
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
    print(f"ROW base_defense: {'PASS' if not fails else 'FAIL'}" + (f" ({len(fails)} failing: {fails})" if fails else ""), flush=True)
    print(f"\n==== test_campaign_gm3_basedef: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(CELLS) else 2)


if __name__ == "__main__":
    main()
