"""test_campaign_gm3_basedef_rejoin.py: an attack on the X-COM player's own base in a gm3 PvP campaign whose borrowed
start is interrupted by the X-COM player's lost game (host = the aliens, client = X-COM). the alien host goes home to its own
world and the attack waits; once the player is back and RESUME is pressed, the defence starts again for both, in the X-COM player's world,
and ends through S-C2's return.
Spec: docs rewrite/prompts/d250u_pvp_campaigns_sc.md AMENDMENT SC-4 (SC4-6, SC4-7, SC4-8 file B row B2, FX5B-2, FX5B-11 .. FX5B-17) and its
ORCHESTRATOR RULINGS (QC5B-1 .. QC5B-7 (a)); owner D250, O1 (a); D260 (b), D262 (b), D265 (a); F15519, F15520, F15522; S-C3's H14 variant `ab`
(docs rewrite/d250u-task0/sc3/CONSTANTS.md: B2-end asserts the host's noBases and funds). TASK 0 pins: docs
rewrite/d250u-task0/sc5b2/CONSTANTS.md (P-C5b2 2/2 on boots Ba2 / Ba3; the green premise boot Rb; the walls).

Boot R: gm3, key 48037, dirs d250uc5b2_r_host / _client / _client2. Bring-up (FX5B-2) as file A; FX5B-11 the tank; FX5B-16: client
hold_battle_ready {on: true} (armed) before the attack; the attack is FX5B-12's stated fallback as in file A (client spawn_ufo + client
trigger_base_defense; TASK 0: spawn_base_assault's UFO never arrives, F16170) with its wait (<= ARRIVE_S; geo_set_speed idx 1 on both, then
idx 0). The window (FX5B-16; it needs the hand-off: client pvpBorrow.sent +1 or its CoopState 3 seen): host pvpBorrow.borrowed +1, host phase
Handshake and client hold_battle_ready.held true <= WATCH_S (plain host popups drained); client.kill(); W = W_S of host stacks every W_POLL.
FX5B-17 the rejoin (test_failed_base_defense.rejoin()'s steps on KEY): client2 spawn / connect / join_tcp; host get_coop.resumeAck true
<= RESUME_ACK_S; profile_ok on a top Profile (the host); session.press_back_when_shown(host, "host RESUME", codes=(60, 62)). A bring-up or
staging miss is a FIXTURE-STOP: ONE "CAPTURE R:" line and every remaining cell FAILs "boot".
Row B2 (one PASS / FAIL line per cell, one EVIDENCE line, one ROW line; a cell whose precondition was never reached FAILs "blocked: <why>"):
  B2-start   in the window host pvpBorrow.borrowed +1, phase Handshake, client held true; after the kill: host UNWIND ("W2-H24: failed battle
             start (") +1 reading "(partner dropped)" or "(partner lost)"; at W the host stack ends [GeoscapeState, CoopState] with dialog
             62, no BriefingState / BattlescapeState, inBattle false; host pvpBorrow {active false, swappedBack +1, rearmed 1, pending true,
             refusedSent unchanged}; host geo_state real bases == HOST0.
  B2-again   resumeAck true, RESUME pressed; within AGAIN_S of RESUME both phase Active with equal battleId (plain host popups drained while
             no borrow); host pvpBorrow.borrowed == the window's + 1, kind "baseDefense", active true; host geo_state real bases == CLIENT0's;
             both missionType STR_BASE_DEFENSE; the spine passed; client2's faction-0 units on seat 1.
  B2-end     (FX5B-13 / FX5B-14 with client2) host title TITLE_B; client2's display-only debriefing equal (BES.DEBRIEF_FIELDS); client2
             geo_clean <= OK_S, debriefOkBranch "campaign-client-borrowed", worldAdopted 1; host geo_clean <= HOST_OK_S, active false,
             home == parked, real bases == HOST0, noBases true and funds == HOST0's (H14 variant `ab` includes H14b).
  B2-common  desyncSeen false on host and client2; 0 new crash files since the row's start (the hard-killed client writes none: TASK 0 Rb).
RED (C5B2R on 9eacec774): exit 2, 0/4 - B2-start FAILs (P-C5b2: no hand-off, no borrow to drop); the other three FAIL "blocked: no
borrowed base defence to drop (B2-start)". GREEN (C5B2G): 4/4.
ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_campaign_gm3_basedef_rejoin.py
"""

import glob
import json
import os
import re
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

# ----- TASK 0 pins (docs rewrite/d250u-task0/sc5b2/CONSTANTS.md; boots Ba2 / Ba3 red, Rb green) -----
KEY = "48037"
TAG = "d250uc5b2_r"
TANK = "STR_TANK_LASER_CANNON"               # FX5B-11
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}     # FX5B-12 fallback (QC5B-7 (b), W2-H24's arguments)
MISSION = "STR_BASE_DEFENSE"
TITLE_B = "Base is saved"                    # FX5B-15 (Bb, Rb)
UNWIND = "failed battle start ("
KEEP = ("CoopState", "BriefingState", "BattlescapeState", "BaseDefenseState", "DebriefingState", "ConfirmLandingState", "Profile")
# ----- bounds (s; TASK 0 Rb: hand-off 0.35, window 1.36, resumeAck 1.56, second borrow 0.05 and both Active 2.16 after RESUME) -----
ARRIVE_S, WATCH_S, W_S, W_POLL, RESUME_ACK_S, AGAIN_S = 30, 135, 15.0, 0.2, 60, 60
DEBRIEF_S, CLIENT_DEBRIEF_S, OK_S, HOST_OK_S = 60, 20, 10, 60
CELLS = ["B2-start", "B2-again", "B2-end", "B2-common"]
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


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return f"probe failed ({type(e).__name__}: {str(e)[:120]})"


def has(gc, name):
    st = stack(gc)
    return isinstance(st, list) and any(name in s for s in st)


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def coop(gc):
    return gc.cmd({"cmd": "get_coop"})


def pvp(gc):
    return coop(gc).get("pvpBorrow") or {}


def dlg(gc):
    r = gc.cmd({"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible")}


def bview(gc):
    b = battle_state(gc)
    return {"inBattle": b.get("inBattle"), "phase": b.get("phase"), "missionType": b.get("missionType"),
            "mapFingerprint": b.get("mapFingerprint"), "turn": b.get("turn"), "battleId": (b.get("authority") or {}).get("battleId")}


def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:240] for ln in logl(gc)[n0:] if needle in ln]


def my_ufo(gc, uid):
    return [u for u in gc.ok({"cmd": "geo_state"}).get("ufos", []) if u.get("id") == uid and not u.get("coop")]


def drain_host(host, out, t_ref):
    dd, _hit = geo.drain_popups(host, interest=geo.popup(*KEEP))
    if dd:
        out.append([round(time.time() - t_ref, 2), dd])


def capture_boot(err, *machines):
    cap = {}
    for gc in machines:
        if not alive(gc):
            continue
        try:
            bs = battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn", "missionType")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": coop(gc), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE R: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
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
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": G3E.real_bases(hg)}
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    client0 = {"noBases": cc.get("noBases"), "realBases": G3E.real_bases(cg), "base": xb and xb.get("name")}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")])
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions (FX5B-2): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb:
        capture_boot("the client has no real base", host, client)
    geo.slow_clock(host, client)
    return host0, client0


def attack(host, client, client0, ev):
    """FX5B-11, FX5B-16's hold, FX5B-12 (the stated fallback route, as file A). Returns the attack record."""
    a = ev.setdefault("attack", {})
    gi = client.cmd({"cmd": "give_items", "item": TANK, "count": 1})
    a["giveItems"] = gi
    if not gi.get("ok"):
        capture_boot(f"client give_items {TANK}: {gi} (FX5B-11: the item missing = FIXTURE-STOP)", host, client)
    h = client.cmd({"cmd": "hold_battle_ready", "on": True})
    a.update(hold=h, pvpBefore={"host": pvp(host), "client": pvp(client)})
    if h.get("armed") is not True:
        capture_boot(f"client hold_battle_ready {h} (FX5B-16)", host, client)
    su = client.cmd(dict(UFO))
    if not su.get("ok"):
        capture_boot(f"client spawn_ufo (FX5B-12 fallback): {su}", host, client)
    tb = client.cmd({"cmd": "trigger_base_defense", "ufo_id": su.get("ufo_id")})
    ta = time.time()
    a.update(spawnUfo=su, trigger=tb)
    if not tb.get("ok") or tb.get("base") != client0["base"]:
        capture_boot(f"client trigger_base_defense {tb} (want base {client0['base']!r}, FX5B-12)", host, client)
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
             stacksAtEnd=[stack(host), stack(client)], pvpAtEnd={"host": pvp(host), "client": pvp(client)})
    a["speed0"] = [gc.cmd({"cmd": "geo_set_speed", "idx": 0}).get("ok") for gc in (host, client)]
    sent = lambda p: p.get("sent") or 0  # noqa: E731
    a["handed"] = coop3 is not None or sent(a["pvpAtEnd"]["client"]) > sent(a["pvpBefore"]["client"])
    return a


def b2_start(host, client, host0, a, ev, ctx):
    p0 = a["pvpBefore"]["host"]
    if not a["handed"]:
        hb, hp, cp = bview(host), pvp(host), pvp(client)
        ev["noHandOff"] = {"battle": [hb, bview(client)], "pvp": {"host": hp, "client": cp}, "stacks": [stack(host), stack(client)]}
        cell("B2-start", False, f"no borrow to drop (P-C5b2): the attack ended with {a['ended']} {a['endedS']} s after the trigger, the client's "
             f"top never CoopState code 3, client pvpBorrow.sent {cp.get('sent') or 0}, host borrowed {hp.get('borrowed') or 0} (before "
             f"{p0.get('borrowed') or 0}); host inBattle {hb.get('inBattle')}, phase {hb.get('phase')} (stacks host {stack(host)} client "
             f"{stack(client)})")
        ctx["blocked"] = "no borrowed base defence to drop (B2-start)"
        return
    w, drained, tw = ev.setdefault("window", {}), [], time.time()

    def window():
        return (pvp(host).get("borrowed") or 0) == (p0.get("borrowed") or 0) + 1 and bview(host).get("phase") == "Handshake" \
            and client.cmd({"cmd": "hold_battle_ready"}).get("held") is True
    ok = False
    while time.time() - tw < WATCH_S:
        if window():
            ok = True
            break
        drain_host(host, drained, tw)
        time.sleep(0.2)
    w0 = pvp(host)
    w.update(ok=ok, s=round(time.time() - tw, 2), drained=drained, stacks=[stack(host), stack(client)], pvp=w0, battle=bview(host))
    if not ok:
        cell("B2-start", False, f"no window within {WATCH_S} s of the hand-off: host pvpBorrow {w0}, battle {bview(host)}, client held "
             f"{client.cmd({'cmd': 'hold_battle_ready'}).get('held')!r}")
        ctx["blocked"] = "no borrowed start to interrupt (B2-start)"
        return
    ctx["borrowedAtWindow"] = w0.get("borrowed") or 0
    n_h = len(logl(host))
    client.kill()
    tk = time.time()
    first, polls = dict(bview(host), t=round(time.time() - tk, 2)), []
    while time.time() - tk < W_S:
        st = stack(host)
        if not polls or polls[-1][1] != st:
            polls.append([round(time.time() - tk, 2), st])
        time.sleep(W_POLL)
    unw = since(host, n_h, UNWIND)
    why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
    hst, hd, hb, hco, hg = stack(host), dlg(host), bview(host), coop(host), host.ok({"cmd": "geo_state"})
    hp = hco.get("pvpBorrow") or {}
    ev["atW"] = {"lossPath": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first.get("phase"), "?"), "firstPoll": first,
                 "UNWIND": unw, "stacks": polls, "dialog": hd, "battle": hb, "pvp": hp, "noBases": hco.get("noBases"),
                 "gamemode": hco.get("gamemode"), "funds": hg.get("funds"), "realBases": G3E.real_bases(hg),
                 "coopPvpLog": since(host, n_h, "[coop-pvp]")}
    bad = [] if len(unw) == 1 and why else [f"host UNWIND lines {unw} (want 1 reading (partner dropped) or (partner lost))"]
    bad += [f"host stack at W {hst} dialog {hd.get('code')} (want it to end [GeoscapeState, CoopState] with dialog 62)"] \
        if not isinstance(hst, list) or hst[-2:] != ["GeoscapeState", "CoopState"] or hd.get("code") != 62 else []
    bad += [f"host stack {hst} holds a battle screen"] if has(host, "BriefingState") or has(host, "BattlescapeState") else []
    bad += [f"host inBattle {hb.get('inBattle')!r} (want false)"] if hb.get("inBattle") is not False else []
    d = lambda k: (hp.get(k) or 0) - (p0.get(k) or 0)  # noqa: E731
    bad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w_!r})" for k, w_ in (("active", False), ("pending", True)) if hp.get(k) is not w_]
    bad += [f"host pvpBorrow.swappedBack +{d('swappedBack')} (want +1)"] if d("swappedBack") != 1 else []
    bad += [f"host pvpBorrow.rearmed {hp.get('rearmed')!r} (want 1: the X-COM player's request re-armed, D260 (b))"] \
        if hp.get("rearmed") != 1 else []
    bad += [f"host pvpBorrow.refusedSent {hp.get('refusedSent')!r} (want unchanged {p0.get('refusedSent')!r})"] \
        if (hp.get("refusedSent") or 0) != (p0.get("refusedSent") or 0) else []
    bad += [f"host real bases {G3E.real_bases(hg)} (want HOST0 {host0['realBases']})"] if G3E.real_bases(hg) != host0["realBases"] else []
    cell("B2-start", not bad, "; ".join(bad) or f"window {w['s']} s (borrowed +1, Handshake, client held); after the drop UNWIND +1 "
         f"({why[0]}); at W [GeoscapeState, CoopState] dialog 62, inBattle false; the request re-armed (active false, swappedBack +1, "
         "rearmed 1, pending true, no refusal); the host's real bases == HOST0")
    if hb.get("inBattle") is not False or hd.get("code") != 62:
        ctx["blocked"] = "the host never waited on its globe after the drop (B2-start)"


def rejoin(host, x, ev):
    """FX5B-17: test_failed_base_defense.rejoin()'s steps on KEY. Returns the RESUME time or None."""
    j = ev.setdefault("rejoin", {})
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(TAG + "_client2"))
    c2.spawn(); c2.connect()
    tj = time.time()
    j["join_tcp"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    ok, j["resumeAckS"] = BES.wait_until(lambda: coop(host).get("resumeAck") is True, RESUME_ACK_S)
    j.update(hostStack=stack(host), hostDialog=dlg(host), client2Stack=stack(c2), client2Dialog=dlg(c2))
    if not ok:
        return None, f"host resumeAck not true within {RESUME_ACK_S} s of client2's join"
    if session.has_state(host, "Profile"):
        j["hostProfileOk"] = host.cmd({"cmd": "profile_ok"})
        time.sleep(0.5)
    try:
        j["RESUME"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
    except Exception as e:  # noqa: BLE001
        return None, f"host RESUME: {str(e)[:300]}"
    j["resumeS"] = round(time.time() - tj, 2)
    return time.time(), None


def b2_again(host, x, client0, ev, ctx):
    tr, err = rejoin(host, x, ev)
    c2 = x["client2"]
    if tr is None:
        cell("B2-again", False, f"the rejoin (FX5B-17): {err} (host {stack(host)} {dlg(host)}, client2 {stack(c2)} {dlg(c2)})")
        ctx["blocked"] = "the X-COM player never got back (B2-again)"
        return
    g, drained = ev.setdefault("again", {}), []
    while time.time() - tr < AGAIN_S:
        if (pvp(host).get("borrowed") or 0) > ctx["borrowedAtWindow"] and "borrowS" not in g:
            g["borrowS"] = round(time.time() - tr, 2)
        hb, cb = bview(host), bview(c2)
        if hb.get("phase") == "Active" and cb.get("phase") == "Active" and hb.get("battleId") and hb.get("battleId") == cb.get("battleId"):
            g["activeS"] = round(time.time() - tr, 2)
            break
        if "borrowS" not in g:
            drain_host(host, drained, tr)
        time.sleep(0.25)
    hb, cb, hp, hg = bview(host), bview(c2), pvp(host), host.ok({"cmd": "geo_state"})
    g.update(drained=drained, battle={"host": hb, "client2": cb}, pvp=hp, hostRealBases=G3E.real_bases(hg), stacks=[stack(host), stack(c2)])
    bad = [] if "activeS" in g else [f"not both phase Active with equal battleId within {AGAIN_S} s of RESUME (host {hb}, client2 {cb}; "
                                     f"second borrow {'at %s s' % g['borrowS'] if 'borrowS' in g else 'never'})"]
    bad += [f"host pvpBorrow.borrowed {hp.get('borrowed')!r} (want the window's {ctx['borrowedAtWindow']} + 1)"] \
        if (hp.get("borrowed") or 0) != ctx["borrowedAtWindow"] + 1 else []
    bad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w_!r})" for k, w_ in (("kind", "baseDefense"), ("active", True)) if hp.get(k) != w_]
    bad += [f"host real bases {G3E.real_bases(hg)} (want CLIENT0's {client0['realBases']})"] \
        if G3E.real_bases(hg) != client0["realBases"] else []
    sp_ok = False
    if "activeS" in g:
        try:
            session.briefings_to_battlescape(host, c2)
            sp_ok = True
        except Exception as e:  # noqa: BLE001
            bad.append(f"session.briefings_to_battlescape raised {str(e)[:300]}")
        hb, cb = bview(host), bview(c2)
        bad += [f"{nm} missionType {b.get('missionType')!r} (want {MISSION!r})" for nm, b in (("host", hb), ("client2", cb))
                if b.get("missionType") != MISSION]
        f0 = [u for u in battle_state(c2).get("units", []) if u.get("faction") == 0]
        g["client2Faction0"] = [{k: u.get(k) for k in ("id", "coop", "type", "soldierId")} for u in f0]
        bad += [] if f0 else ["client2: no faction-0 unit"]
        bad += [f"client2: unit {u['id']} faction 0 seat {u.get('coop')} (want 1)" for u in f0 if u.get("coop") != 1]
    cell("B2-again", not bad, "; ".join(bad) or f"resumeAck {ev['rejoin']['resumeAckS']} s, RESUME; the second borrow {g.get('borrowS')} s "
         f"and both Active (battleId {hb.get('battleId')}) {g.get('activeS')} s after RESUME; borrowed {hp.get('borrowed')}, baseDefense, "
         f"active; the host's live world holds CLIENT0's bases; {MISSION} on both; client2's units on seat 1")
    if not sp_ok:
        ctx["blocked"] = "no defence after the rejoin (B2-again)"


def b2_end(host, x, host0, ev, ctx):
    c2, e = x["client2"], ev.setdefault("end", {})
    ctx["desync"] = [event_state(host).get("desyncSeen"), event_state(c2).get("desyncSeen")]
    G2F.kill_all(host, c2, 1, e, "kills")
    if not has(host, "DebriefingState"):
        e["endTurn"] = c2.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        e["closeNext"] = BES.close_host_nextturn(host)
    ok, secs = BES.wait_until(lambda: has(host, "DebriefingState"), DEBRIEF_S)
    hdeb = G3E.deb(host)
    e["hostDebrief"] = {k: v for k, v in hdeb.items() if k != "widgets"}
    if not ok:
        cell("B2-end", False, f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})")
        return
    bad = [f"host debrief_state.{k}={hdeb.get(k)!r} (want {w_!r})" for k, w_ in (("title", TITLE_B), ("displayOnly", False))
           if hdeb.get(k) != w_]
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                         and d.get("displayOnly") is True)(G3E.deb(c2)), CLIENT_DEBRIEF_S)
    cdeb = G3E.deb(c2)
    hv, cv = BES.debrief_view(hdeb), BES.debrief_view(cdeb)
    e["client2Debrief"] = {k: v for k, v in cdeb.items() if k != "widgets"}
    bad += [] if cok else [f"no client2 display-only DebriefingState within {CLIENT_DEBRIEF_S} s (stack {stack(c2)})"]
    bad += [f"client2 {k}={cv.get(k)!r} != host {hv.get(k)!r}" for k in BES.DEBRIEF_FIELDS if cok and cv.get(k) != hv.get(k)]
    pk = BES.press_ok(c2)
    _r, screens = BES.drain(c2, timeout=OK_S)
    gok, gs = BES.wait_until(lambda: BES.geo_clean(c2), OK_S)
    crec = BES.record(c2)
    e["client2Ok"] = {"press": pk, "drain": screens, "geoS": gs, "stack": stack(c2), "noBases": G3E.coop(c2).get("noBases"),
                      "battleEnd": {k: crec.get(k) for k in ("debriefOkBranch", "worldAdopted", "applied", "reason")},
                      "realBases": G3E.real_bases(c2.ok({"cmd": "geo_state"}))}
    bad += [] if gok else [f"client2 not on a clean GeoscapeState {OK_S} s after its OK (stack {stack(c2)})"]
    bad += [f"client2 battleEnd.{k} {crec.get(k)!r} (want {w_!r})" for k, w_ in (("debriefOkBranch", "campaign-client-borrowed"),
            ("worldAdopted", 1)) if crec.get(k) != w_]
    hk = BES.press_ok(host)
    hreached, hscreens, on994 = G2F.drain_host(host)
    hgok, hgs = BES.wait_until(lambda: BES.geo_clean(host), HOST_OK_S) if hreached else (False, 0)
    hco, hg = G3E.coop(host), host.ok({"cmd": "geo_state"})
    pv = hco.get("pvpBorrow") or {}
    e["hostOk"] = {"press": hk, "drain": hscreens, "on994": on994, "geoS": hgs, "stack": stack(host), "noBases": hco.get("noBases"),
                   "funds": hg.get("funds"), "realBases": G3E.real_bases(hg), "pvpBorrow": pv}
    bad += [] if hgok else [f"host not on a clean GeoscapeState after its OK (reached {hreached}, CoopState 994 {on994}, stack {stack(host)})"]
    bad += [f"host pvpBorrow.active {pv.get('active')!r} (want false)"] if pv.get("active") is not False else []
    bad += ["host pvpBorrow.home absent (want == parked)"] if "home" not in pv else \
        ([f"host pvpBorrow.home {pv.get('home')} != parked {pv.get('parked')}"] if pv.get("home") != pv.get("parked") else [])
    bad += [f"host real bases {G3E.real_bases(hg)} (want HOST0 {host0['realBases']})"] if G3E.real_bases(hg) != host0["realBases"] else []
    bad += [f"host noBases {hco.get('noBases')!r} (want true)"] if hco.get("noBases") is not True else []
    bad += [f"host funds {hg.get('funds')!r} (want HOST0 {host0['funds']!r})"] if hg.get("funds") != host0["funds"] else []
    cell("B2-end", not bad, "; ".join(bad) or f"host title {TITLE_B!r} ({secs} s); client2's display-only debriefing equal; client2 "
         f"geo_clean, campaign-client-borrowed, worldAdopted 1; host geo_clean ({hgs} s), active false, home == parked, real bases, "
         "noBases and funds == HOST0")


def b2_common(host, x, ctx, crash0):
    c2 = x["client2"]
    if "desync" not in ctx:
        ctx["desync"] = [event_state(host).get("desyncSeen"), event_state(c2).get("desyncSeen") if alive(c2) else None]
    after = [event_state(host).get("desyncSeen"), event_state(c2).get("desyncSeen") if alive(c2) else None]
    new = sorted(crash_set() - crash0)
    bad = [f"desyncSeen host / client2 {ctx['desync']} before the kills, {after} at the end (want false on both)"] \
        if ctx["desync"] != [False, False] or after != [False, False] else []
    bad += [f"{len(new)} new crash file(s) since the row's start (first {os.path.basename(new[0])})"] if new else []
    cell("B2-common", not bad, "; ".join(bad) or "desyncSeen false on host and client2; 0 new crash files")


def run_b2(host, client, x, host0, client0, ev):
    ctx = {"blocked": None}
    crash0 = crash_set()
    a = attack(host, client, client0, ev)
    b2_start(host, client, host0, a, ev, ctx)
    if ctx["blocked"]:
        block(CELLS, ctx["blocked"])
        return
    b2_again(host, x, client0, ev, ctx)
    if ctx["blocked"]:
        block(["B2-end"], ctx["blocked"])
    else:
        b2_end(host, x, host0, ev, ctx)
    b2_common(host, x, ctx, crash0)


def main():
    host = GameClient("host", None, make_user_dir(TAG + "_host"))
    client = GameClient("client", None, make_user_dir(TAG + "_client"))
    x = {"client2": None}
    t0, ev = time.time(), {}
    try:
        try:
            host0, client0 = bring_up(host, client, ev)
            run_b2(host, client, x, host0, client0, ev)
        finally:
            print(f"EVIDENCE B2: {json.dumps(dict(ev, wall=round(time.time() - t0, 1)), sort_keys=True, default=str)}", flush=True)
    except FixtureMiss as e:
        block(CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        for gc in (x["client2"], client, host):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"ROW B2: {'PASS' if not fails else 'FAIL'}" + (f" ({len(fails)} failing: {fails})" if fails else ""), flush=True)
    print(f"\n==== D250-U S-C5b2 gm3 PvP campaign base defence after a lost start: {len(RESULTS) - len(fails)}/{len(RESULTS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(CELLS) else 2)


if __name__ == "__main__":
    main()
