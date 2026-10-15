"""FS2-G3 row G3X - test_w2_stage2_gm3_rearm.py: a gm3 PvP campaign's Cydonia (host = the aliens, client = X-COM) whose X-COM player is
lost between part 1 and part 2. QA-4 (b) (following owner D282 (b)): part 2 WAITS on the alien host in the borrowed X-COM world (part 1's
results kept); after the rejoin and the alien host's RESUME the same part 2 is offered again and both play it.
Spec: docs rewrite/prompts/fs2g3_gm3_part2_rearm.md (f) and its ORCHESTRATOR RULINGS (QG-1 .. QG-4 (a)); AMENDMENT FS2-A
(rewrite/prompts/fs2_sa_part2_rearm.md) QA-4 (b), VL-FS2A-4; D260 (b); QC-13 (a) narrowed. TASK 0 pins: docs
rewrite/fs2g3-task0/sa/CONSTANTS.md (red premise boots Pa / Pb 2/2, green premise boot Pc).

ONE boot (boot P: gm3, key KEY, dirs fs2g3_g3x_host / _client / _client2). FXG-1 bring-up and FXG-2 staging = K's
(test_d250_campaign_gm3_cydonia.py) bring_up / stage / capture_boot copied with KEY and the row id as parameters (K's KEY is read
inside them, F16808): the client's open_select_destination {Skyranger, STR_SKYRANGER}, open_cydonia, set_seed SEED, confirm_cydonia;
a miss is a FIXTURE-STOP (ONE CAPTURE line, every cell FAILs "boot"). FXG-3 part 1 (entry <= ENTRY_S, the spine, hash). FXG-4
kill_all faction 1, client hold_battle_ready {on: true}, client END TURN + the host's NextTurnState closed, the window (host Handshake
battleId B1 + 1, client held) <= WINDOW_S. FXG-5 client.kill(), W of host stacks at POLL. FXG-6 S2F's rejoin() (client2, join_tcp
NAME, resumeAck <= RJ, profile_ok, RESUME). FXG-7 part 2.

  G3X-1 GUARD part 1 by the hand-off + the window (precondition; a failure ends the row).
  G3X-2 RED   PARK +1 and UNWIND +0 (red today: UNWIND +1, PARK 0).
  G3X-3 RED   the alien host waits inside part 2 in the borrowed world at W: [.., GeoscapeState, BriefingState, CoopState] 62 backVisible
              false, has_battle true, PART2 Idle / MT2 / FP2, HOME 0, pvpBorrow active true with swappedBack / borrowed == P0's, gamemode 3,
              noBases false, real bases == CLIENT0's (red today: [GeoscapeState, CoopState], has_battle false, HOME 1, noBases true).
  G3X-4 GUARD the rejoin reaches RESUME (resumeAck <= RJ, RESUME pressed, RESUMED_GUARD +0, client2 never > 30 s on 52).
  G3X-5 RED   part 2 starts for both: has_battle true at RESUME; REARM +1 and OFFER +1 <= REARM_S; the spine to turn 1; PART2 host ==
              client2 (Active, battleId > B1 + 1, turn 1, MT2, FP2, xcom == XCOM2); census seats; borrow kept; hash EQUAL; UNWIND 0
              (red today: "no part 2 on the host", at once).
  G3X-6 GUARD desyncSeen false on host and client before the kill and on host and client2 at the end; part 1's hash EQUAL.
  G3X-7 GUARD CRASH 0 (no new crash file in this lane's crash folder since the row's start).
UNWIND / PARK counted since the kill, REARM / OFFER since the RESUME press (S2F's needles); HOME = `[coop-pvp] host: back on its own world`
since the kill. PART2 = S2F part2(). P0 / FP2 / XCOM2 / B1 read at run time (S25). EVIDENCE before each verdict; a failed row prints ONE
CAPTURE line. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2. Red (R1, the unchanged
build): FAIL G3X-2, G3X-3, G3X-5; every other cell passes. Green (G1, G1-G2): every cell passes.

Run:  python tools/coop_test/test_w2_stage2_gm3_rearm.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_w2_battle_end_separate as BES  # noqa: E402
import test_d250_campaign_battle_gm2 as G2F  # noqa: E402
import test_d250_campaign_battle_gm3_end as G3E  # noqa: E402
import test_w2_stage2_failed_start as S2F  # noqa: E402
from test_d250_campaign_gm3_cydonia import (stack, has, pvp, bview, census, seats_bad, attempt, crash_set,  # noqa: E402
                                            SEED, SQUAD, ROUTE, MISSION_1, MISSION_2)
from test_w2_stage2_failed_start import (Row, Stop, q, short, ev, log, since, dlg, part2, wait, rejoin,  # noqa: E402
                                         UNWIND, PARK, REARM, OFFER)

# ----- pins (docs rewrite/fs2g3-task0/sa/CONSTANTS.md; S54 rules there) -----
KEY, TAG = "48607", "fs2g3_g3x"
MT1, MT2 = MISSION_1, MISSION_2
HOME = "[coop-pvp] host: back on its own world"
GEO, BRF, COOP = "GeoscapeState", "BriefingState", "CoopState"
# ----- bounds (s; TASK 0 Pa / Pb / Pc: entry 1.61, window 5.54-5.85, resumeAck 2.24-2.25, re-arm 0.01 after RESUME) -----
ENTRY_S, WINDOW_S, W, POLL, RJ, REARM_S = 60, 30, 15.0, 0.2, 60, 60
CELLS = ["G3X-%d" % i for i in range(1, 8)]


class FixtureMiss(Exception):
    pass


def capture_boot(err, host, client, rid):
    """K's capture_boot with the row id a parameter: ONE CAPTURE line, then FixtureMiss."""
    cap = {}
    for gc in (host, client):
        try:
            bs = session.battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "rc": None if gc.proc is None else gc.proc.poll(),
                            "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn", "missionType")},
                            "event_state": ev(gc), "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}),
                            "get_coop": gc.cmd({"cmd": "get_coop"}), "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE {rid}: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def bring_up(host, client, bev, key, rid):
    """FXG-1: K's bring_up with KEY and the row id as parameters; NAME = host get_coop.clientName (S25)."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, key, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client, rid)
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
    name = S2F.coop(host).get("clientName")
    bev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0, gamemode=[ch.get("gamemode"), cc.get("gamemode")], NAME=name)
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"bring-up preconditions (FXG-1): gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3), "
                     f"noBases host {ch.get('noBases')!r} client {cc.get('noBases')!r} (want true / false)", host, client, rid)
    if not xb or not sky or len(sids) < SQUAD or not name:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers, or the host no client name (base "
                     f"{xb and xb.get('name')}, sky {sky}, soldiers {sids}, clientName {name!r})", host, client, rid)
    geo.slow_clock(host, client)
    return client0


def stage(host, client, client0, bev, rid):
    """FXG-2: K's stage (SQ, the route, set_seed, confirm_cydonia) with the row id a parameter. Returns (sq, t_confirm)."""
    sky = client0["sky"]
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    recs = {sid: G3E.srec(client, sid) for sid in sids}
    sq = [sid for sid in sids if recs[sid].get("where") == "base" and recs[sid].get("recovery") == 0][:SQUAD]
    if len(sq) < SQUAD:
        capture_boot(f"fewer than {SQUAD} client base soldiers with recovery 0: "
                     f"{ {s: (recs[s].get('where'), recs[s].get('recovery')) for s in sids} }", host, client, rid)
    asg = [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": False}) for sid in sids]
    asg += [client.cmd({"cmd": "craft_assign", "craft_id": sky["id"], "soldier_id": sid, "on": True}) for sid in sq]
    if not all(r.get("ok") for r in asg):
        capture_boot(f"client craft_assign (SQ {sq}): {[r for r in asg if not r.get('ok')][:2]}", host, client, rid)
    drained, _hit = geo.drain_popups(client)
    if (stack(client) or [None])[-1] != GEO:
        capture_boot(f"client top {stack(client)} after drain_popups {drained} (want GeoscapeState)", host, client, rid)
    osd = client.cmd({"cmd": "open_select_destination", "craft_id": sky["id"], "craft_type": "STR_SKYRANGER"})
    oc = client.cmd({"cmd": "open_cydonia", "craft_id": sky["id"]}) if osd.get("ok") else {}
    route = stack(client)
    bev.update(SQ=sq, drained=drained, openSelectDestination=osd, openCydonia=oc, clientRoute=route,
               pvpBefore={"host": pvp(host), "client": pvp(client)})
    if not osd.get("ok") or not oc.get("ok") or route != ROUTE:
        capture_boot(f"the route: open_select_destination {osd}, open_cydonia {oc}, client stack {route} (want {ROUTE})", host, client, rid)
    sd = client.cmd({"cmd": "set_seed", "seed": SEED})
    t_confirm = time.time()
    cf = client.cmd({"cmd": "confirm_cydonia"})
    if not sd.get("ok") or not cf.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_cydonia {cf}", host, client, rid)
    bev["stacksAfterConfirm"] = [stack(host), stack(client)]
    return sq, t_confirm


def g3x_1(r, host, client, ctx, bev, tc):
    """FXG-3 part 1 and FXG-4 the window; G3X-1 (precondition: a failure raises Stop)."""
    e = {"bring-up": bev}
    ok_in, _s = BES.wait_until(lambda: bool(bview(host).get("inBattle")) and bool(bview(client).get("inBattle")), ENTRY_S)
    e["entry s"] = round(time.time() - tc, 2)
    sp = attempt(lambda: session.briefings_to_battlescape(host, client), "spine passed") if ok_in else (False, "no entry")
    hb, cb = bview(host), bview(client)
    b1, hp1 = hb.get("battleId"), pvp(host)
    ctx["hash1"] = attempt(lambda: session.assert_hash_clean(host, client, full=True, what="part 1"), "EQUAL") if sp[0] \
        else (False, "not reached")
    e.update({"spine": sp, "part 1": {"host": hb, "client": cb}, "pvpHand": hp1, "hash1": ctx["hash1"]})
    b2, ok_w = (b1 + 1 if isinstance(b1, int) else None), False
    if ok_in and sp[0]:
        a = {}
        G2F.kill_all(host, client, 1, a, "kills")
        e["kills"] = [k.get("how") for k in a.get("kills") or []]
        e["hold"] = q(client, {"cmd": "hold_battle_ready", "on": True})
        n_h = len(log(host))
        if not has(host, BRF):
            e["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
            e["closeNext"] = BES.close_host_nextturn(host)
        t1, he, held = time.time(), {}, None
        while time.time() - t1 < WINDOW_S:
            he, held = ev(host), q(client, {"cmd": "hold_battle_ready"}).get("held")
            if he.get("phase") == "Handshake" and he.get("battleId") == b2 and held is True:
                ok_w = True
                break
            time.sleep(POLL)
        hs = he.get("stage") if isinstance(he.get("stage"), dict) else {}
        e.update({"window s": round(time.time() - t1, 2), "host": {k: he.get(k) for k in ("phase", "battleId")}, "held": held,
                  "stage": {k: hs.get(k) for k in ("emitted", "fromBattleId", "toBattleId", "nextStage")},
                  "handoff": since(host, n_h, "stage hand-off - battle %s -> %s offered (stageOf)" % (b1, b2)),
                  "offer": since(host, n_h, "battle_offer sent (battleId=%s," % b2), "hostStack": stack(host)})
    p0, pw = pvp(host), part2(host)
    ctx.update({"B1": b1, "B2": b2, "P0": p0, "FP2": pw.get("mapFingerprint"), "XCOM2": pw.get("xcom"),
                "desync0": [ev(host).get("desyncSeen"), ev(client).get("desyncSeen")]})
    e.update({"P0": p0, "PART2 host at window": pw, "desync before kill": ctx["desync0"]})
    d = lambda k: (hp1.get(k) or 0) - (bev["pvpBefore"]["host"].get(k) or 0)  # noqa: E731
    st = e.get("stage") or {}
    ok = (ok_in and sp[0] and all(d(k) == 1 for k in ("requests", "armed", "borrowed")) and hp1.get("kind") == "cydonia"
          and hb.get("missionType") == MT1 and cb.get("missionType") == MT1 and ok_w and (e.get("hold") or {}).get("armed") is True
          and st.get("emitted") == 1 and st.get("toBattleId") == b2 and st.get("nextStage") == MT2 and len(e["handoff"]) == 1
          and len(e["offer"]) == 1 and e["hostStack"] == [GEO, BRF] and p0.get("active") is True)
    r.cell("G3X-1", "GUARD", "part 1 by the hand-off (host pvpBorrow requests / armed / borrowed +1, kind cydonia; both inBattle, spine, "
           "%s); the window: host stage emitted 1 / toBattleId B1 + 1 / nextStage %s, +1 hand-off, +1 battle_offer (battleId=B1 + 1), "
           "host Handshake B1 + 1, client held, host stack [GeoscapeState, BriefingState], P0 active" % (MT1, MT2), ok, e)
    if not ok:
        raise Stop("G3X-1 (precondition) failed")


def g3x_5(r, host, c2, ctx, n_k):
    """FXG-7 part 2; G3X-5."""
    label = ("part 2 starts for both: has_battle at RESUME; REARM +1 and OFFER +1 within %d s of RESUME, the spine to turn 1, PART2 host "
             "== client2: Active, battleId > B1 + 1, turn 1, %s, FP2, xcom XCOM2; census seats; borrowed == P0's, active; hash EQUAL; "
             "UNWIND 0 (red today: no part 2 on the host)" % (REARM_S, MT2))
    evd = {"has_battle at RESUME": ctx.get("hasBattleAtResume")}
    if "t_resume" not in ctx:
        return r.cell("G3X-5", "RED", label, False, dict(evd, why="no RESUME"))
    n_r = ctx["n_resume"]
    if ctx.get("hasBattleAtResume") is not True:
        evd.update({"why": "no part 2 on the host", "REARM": since(host, n_r, REARM), "OFFER": since(host, n_r, OFFER),
                    "UNWIND": since(host, n_k, UNWIND), "HOME": since(host, n_k, HOME), "host stack": stack(host),
                    "client2 stack": stack(c2), "host pvpBorrow": pvp(host)})
        return r.cell("G3X-5", "RED", label, False, evd)
    try:
        evd["rearm s"] = wait("REARM and OFFER", lambda: since(host, n_r, REARM) and since(host, n_r, OFFER), REARM_S)
        t = time.time()
        session.briefings_to_battlescape(host, c2)
        evd["spine s"] = round(time.time() - t, 2)
    except Exception as e:  # a timed-out wait or a spine that raised: G3X-5's own evidence
        evd["wait"] = short(e, 400)
    hp, cp, pv = part2(host), part2(c2), pvp(host)
    hcen, ccen = census(host), census(c2)
    seats = seats_bad(hcen, ccen, ctx["SQ"], subset=True)
    h2 = attempt(lambda: session.assert_hash_clean(host, c2, full=True, what="part 2"), "EQUAL") if "wait" not in evd \
        else (False, "not reached")
    evd.update({"REARM": since(host, n_r, REARM), "OFFER": since(host, n_r, OFFER), "PART2 host": hp, "PART2 client2": cp,
                "census": {"host": hcen, "client2": ccen}, "seats bad": seats, "host pvpBorrow": pv, "hash2": h2,
                "UNWIND": since(host, n_k, UNWIND)})
    p0 = ctx["P0"]
    ok = (len(evd["REARM"]) == 1 and len(evd["OFFER"]) == 1 and "wait" not in evd and not evd["UNWIND"] and not seats and h2[0]
          and isinstance(hp.get("battleId"), int) and hp["battleId"] > ctx["B2"] and hp["battleId"] == cp.get("battleId")
          and all(p.get("phase") == "Active" and p.get("turn") == 1 and p.get("missionType") == MT2 and p.get("mapFingerprint") == ctx["FP2"]
                  and p.get("xcom") == ctx["XCOM2"] for p in (hp, cp))
          and pv.get("borrowed") == p0.get("borrowed") and pv.get("active") is True)
    r.cell("G3X-5", "RED", label, ok, evd)


def row_g3x(r, host, client, ctx, bev, tc):
    g3x_1(r, host, client, ctx, bev, tc)
    n_k = len(log(host))
    client.kill()
    tk, polls = time.time(), []
    first = dict(ev(host), t=round(time.time() - tk, 2))
    while time.time() - tk < W:
        polls.append([round(time.time() - tk, 2), stack(host), ev(host).get("phase"), dlg(host).get("code")])
        time.sleep(POLL)
    park, unw, home = since(host, n_k, PARK), since(host, n_k, UNWIND), since(host, n_k, HOME)
    why = [w for w in ("(partner dropped)", "(partner lost)") if any(w in ln for ln in park + unw)]
    path = {"first poll after the kill": {k: v for k, v in first.items() if k != "stage"}, "reason": why,
            "loss path (first poll)": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first.get("phase"), "?"),
            "host after": [p for i, p in enumerate(polls) if i == 0 or p[1:] != polls[i - 1][1:]]}
    r.cell("G3X-2", "RED", "PARK +1 and UNWIND +0 (red today: UNWIND +1, PARK 0)", len(park) == 1 and not unw and len(why) == 1,
           {"PARK": park, "UNWIND": unw, "path": path})
    hs, d, hasb, hp = stack(host), dlg(host), q(host, {"cmd": "world_state"}).get("has_battle"), part2(host)
    hco, pv, rb = G3E.coop(host), pvp(host), G3E.real_bases(q(host, {"cmd": "geo_state"}))
    p0 = ctx["P0"]
    ok3 = (isinstance(hs, list) and hs[-3:] == [GEO, BRF, COOP] and d.get("code") == 62 and d.get("backVisible") is False
           and hasb is True and hp.get("phase") == "Idle" and hp.get("missionType") == MT2 and hp.get("mapFingerprint") == ctx["FP2"]
           and not home and pv.get("active") is True and pv.get("swappedBack") == p0.get("swappedBack")
           and pv.get("borrowed") == p0.get("borrowed") and hco.get("gamemode") == 3 and hco.get("noBases") is False
           and rb == ctx["CLIENT0"]["realBases"])
    r.cell("G3X-3", "RED", "the alien host waits inside part 2 in the borrowed world: stack ends [GeoscapeState, BriefingState, CoopState], "
           "dialog 62 backVisible false, has_battle true, PART2 Idle / %s / FP2, HOME 0, pvpBorrow active true, swappedBack and borrowed "
           "== P0's, gamemode 3, noBases false, real bases == CLIENT0's (red today: [GeoscapeState, CoopState], has_battle false, HOME 1, "
           "swappedBack P0 + 1, noBases true, real bases == HOST0's)" % MT2, ok3,
           {"stack": hs, "dialog": d, "has_battle": hasb, "PART2 host": hp, "HOME": home, "pvpBorrow": pv, "P0": p0,
            "gamemode": hco.get("gamemode"), "noBases": hco.get("noBases"), "realBases": rb, "CLIENT0 realBases": ctx["CLIENT0"]["realBases"],
            "HOST0 realBases": bev["HOST0"]["realBases"]})
    evd, n_j = {}, len(log(host))
    ok4 = rejoin(host, ctx, KEY, TAG, n_j, evd)
    ctx["hasBattleAtResume"] = q(host, {"cmd": "world_state"}).get("has_battle") if "t_resume" in ctx else None
    r.cell("G3X-4", "GUARD", "the rejoin reaches RESUME: host resumeAck true within %d s, RESUME pressed, RESUMED_GUARD +0 since the join, "
           "client2 never > 30 s on CoopState 52" % RJ, ok4, evd)
    c2 = ctx["client2"]
    g3x_5(r, host, c2, ctx, n_k)
    d_end = [ev(host).get("desyncSeen"), ev(c2).get("desyncSeen")]
    r.cell("G3X-6", "GUARD", "desyncSeen false on host and client before the kill and on host and client2 at the row's end; part 1's hash "
           "EQUAL", ctx["desync0"] == [False, False] and d_end == [False, False] and ctx["hash1"][0] is True,
           {"before the kill (host, client)": ctx["desync0"], "at the end (host, client2)": d_end, "hash part 1": ctx["hash1"]})


def main():
    t0, ctx, bev = time.time(), {}, {}
    crash0 = crash_set()
    host = GameClient("host", None, make_user_dir(TAG + "_host"))
    client = GameClient("client", None, make_user_dir(TAG + "_client"))
    r = Row("G3X", CELLS[:6])
    booted = False
    try:
        try:
            client0 = bring_up(host, client, bev, KEY, "G3X")
            sq, tc = stage(host, client, client0, bev, "G3X")
            ctx.update(name=bev["NAME"], SQ=sq, CLIENT0=client0)
            booted = True
            print("[fs2g3] G3X boot ok: %s (%.1f s)" % (json.dumps(bev, sort_keys=True, default=str), time.time() - t0), flush=True)
        except Exception as e:  # noqa: BLE001  a bring-up / staging miss (FixtureMiss) or a probe that raised: FIXTURE-STOP
            if not isinstance(e, FixtureMiss):
                try:
                    capture_boot(short(e, 300), host, client, "G3X")
                except FixtureMiss:
                    pass
            print("EVIDENCE G3X boot: %s" % short(e, 600), flush=True)
            for cid in CELLS:
                print("FAIL %s: boot (FIXTURE-STOP)" % cid, flush=True)
            r.fails += list(CELLS)
        if booted:
            try:
                row_g3x(r, host, client, ctx, bev, tc)
            except Exception as e:  # the precondition, a timed-out wait, or a lever / kill() that raised: the row ends here
                r.stop(short(e))
            new = sorted(crash_set() - crash0)
            r.cell("G3X-7", "GUARD", "CRASH 0 (no new crash file in this lane's crash folder since the row's start)", not new,
                   [os.path.basename(f) for f in new])
            if r.fails:
                S2F.capture("G3X", host, ctx)
    finally:
        for gc in (ctx.get("client2"), client, host):
            try:
                if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print("FAIL G3X shutdown (%s): %s" % (gc.name, short(e, 300)), flush=True)
                r.fails.append("shutdown %s" % gc.name)
    print(("PASS G3X" if not r.fails else "FAIL G3X: %s" % " ".join(r.fails)), flush=True)
    passed = len([c for c in CELLS if c not in r.fails])
    print("\n==== FS2-G3 gm3 PvP Cydonia part 2 after a lost X-COM player: %d/%d cells PASS, wall %.1f s ====" % (
        passed, len(CELLS), time.time() - t0), flush=True)
    return 0 if not r.fails else 2


if __name__ == "__main__":
    sys.exit(main())
