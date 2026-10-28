"""R4-L2 stages S-A and S-D (spec rewrite/prompts/r4l2_campaign_rejoin.md (f) rows CR2, CR4, QL2-1 a, QL2-4 a, QL2-5 a, QL2-6 a; TASK 0
rewrite/r4l2-task0/sa/CONSTANTS.md T0-2, rewrite/r4l2-task0/sd/CONSTANTS.md T0-E): a SEPARATE co-op campaign player whose game is killed during a
battle restarts, rejoins, is offered the battle (CR2), finishes it and gets its guest's record in its own world (CR4).
  Boot S (key "48599", w2r4l2_s_host / _client / _client2): bring_up_separate_guest_battle(pre_mission_start=f) (SPEC 19 S1: 3 host
  soldiers + the client's "Guest Zzz" seated on the host's craft; f records OWN_BEFORE = the client's own "Guest Zzz" record and F0 =
  the client's funds, for CR4); GID = the host battle unit named "Guest" (coop 1); B0, SPLIT0, T0, HASH; ICON0 (the host's
  partner-base icons) and H0 (the host's copy of the client world, coop_file_info); client.kill() (the loss path in EVIDENCE: TASK 0
  measured -2, peerAbsent true at the first poll); PAUSE; ICON1; REJOIN(client2, "48599", campaign); walk_far(host, client2, GID).
  Cells: CR2-1 GUARD PAUSE; CR2-2 GUARD phase 1 served (a client2 poll on 68; EVIDENCE only, never asserted, QL2-4: RESTASH, ICON0 /
  ICON1, H0 == the host copy's fnv at the pause); CR2-3 RED the live offer (OFFER +1 reading battleId=B0, REFUSED +0); CR2-4 RED
  RESUME offered within W_ACK and pressed; CR2-5 RED the same battle on both; CR2-6 RED SPLIT (client2's holds GID on seat 1);
  CR2-7 RED HASH; CR2-8 RED one client2 walk of GID applied, HASH again; CR2-9 GUARD CRASH 0 and client2 zero-disk.
  Row CR4 (S-D, boot S after CR2; the C28P ending of test_battle_end_separate on the rejoined client2): host kill_unit_real for every
  live faction-1 unit, chain_settled(host, client2) after each; end_turn_both(host, client2); close_host_nextturn(host); the host's
  DebriefingState within 60 s; COPY = the host's soldier_rec(name="Guest Zzz") before any OK. Cells (every one GUARD, QL2-6 a): CR4-1
  client2's display-only debriefing within 20 s, equal to the host's on debrief_view's fields; CR4-2 client2's OK through its follow-ups
  -> its own GeoscapeState, battleEnd.sepReturn {ownLoaded 1, guestsApplied 1, guestsMissing 0, pushed 1}, its own guest's
  soldier_record (OWN_BEFORE's id) == COPY on RECORD_FIELDS, missions == OWN_BEFORE.missions + 1; CR4-3 the host's OK + drain ->
  GeoscapeState, no alive "Guest Zzz" on the host, client2 zero-disk; CR4-4 CRASH 0. EVIDENCE only (never asserted, QL2-4): ICON at the
  end vs ICON0, client2 funds vs F0 (with monthsPassed and the date), RESTASH.
Definitions, REJOIN, needles, the flow rule and the safe battle_state probe: test_campaign_rejoin.py (imported, import
only). EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; ONE run; exit 0 iff every cell passes, else 2.
Red (S-A commit 1): CR2 FAIL on CR2-3, CR2-4 and CR2-5..CR2-8 "not reached" (CR2-1, CR2-2, CR2-9 PASS).
S-D (one test-only commit, proof only): CR2 and CR4 PASS, exit 0.
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402  (main-guarded: soldier_rec and the C28P ending helpers)
import test_campaign_rejoin as CR  # noqa: E402  (main-guarded: the S-A helpers)

KEY_S = "48599"
FREEZE, DROP = "[coop-session] freeze (lobbyMode=", "[coop-session] onClientDrop"
DEBRIEF = "DebriefingState"
SEP_WANT = {"ownLoaded": 1, "guestsApplied": 1, "guestsMissing": 0, "pushed": 1}
OWN = {}


def fx(host, client):
    """pre_mission_start f: OWN_BEFORE (the client's own "Guest Zzz" record) and F0 (the client's funds) before the battle"""
    OWN["OWN_BEFORE"] = BES.soldier_rec(client, name="Guest Zzz")
    OWN["F0"] = CR.q(client, {"cmd": "geo_state"}).get("funds")


def icons(host):
    """ICON: the host's geo_state bases with coopIcon (the partner's base icons)"""
    return [b.get("name") for b in CR.q(host, {"cmd": "geo_state"}).get("bases") or [] if b.get("coopIcon")]


def copy_info(host, key=None):
    """the host's copy of the client world: coop_file_info by role (host_copy_of_client) or by key"""
    return CR.pick(CR.q(host, {"cmd": "coop_file_info", "key": key} if key else {"cmd": "coop_file_info", "role": "host_copy_of_client"}),
                   ("key", "present", "bytes", "fnv1a64", "error"))


def row_cr2(x, results, walls):
    r = CR.Row("CR2", ["CR2-%d" % i for i in range(1, 9)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        gids = [CR.pick(u, ("id", "coop", "name")) for u in CR.bs_raw(h).get("units") or []
                if u.get("faction") == 0 and "Guest" in str(u.get("name"))]
        print("EVIDENCE CR2 fixture: %s" % json.dumps({"GID units": gids, "OWN_BEFORE": OWN.get("OWN_BEFORE"), "F0": OWN.get("F0")},
                                                     sort_keys=True, default=str), flush=True)
        if len(gids) != 1 or gids[0]["coop"] != 1:
            raise CR.Stop("FIXTURE-STOP: GID = exactly one host battle unit named \"Guest\" on coop 1: %s" % gids)
        gid = gids[0]["id"]
        CR.baseline(r, x, c)
        icon0, h0 = icons(h), copy_info(h)
        x.icon0 = icon0  # S-D: CR4's EVIDENCE (ICON at the end vs ICON0, QL2-4)
        r.n_h = n_h = len(CR.log(h))
        c.kill()
        first = CR.auth(h)
        ok, pv = CR.pause(x)
        drop, freeze = CR.since(h, n_h, DROP), CR.since(h, n_h, FREEZE)
        pv["loss path"] = {"first poll after the kill": first, "FREEZE": freeze, "DROP": drop, "kill rc": c.proc.returncode,
                           "path": "-2 (receive)" if drop else ("-3 (send)" if freeze else "?")}
        r.cell("CR2-1", "GUARD", "PAUSE(host) (phase Active, peerAbsent true, battleId B0, inBattle true, dialog 62 backVisible false, "
               "[..., BattlescapeState, CoopState] within %.0f s of the kill)" % CR.W_PAUSE, ok, pv)
        if not ok:
            raise CR.Stop("PAUSE(host) not reached within %.0f s" % CR.W_PAUSE)
        icon1, hp = icons(h), copy_info(h, h0.get("key"))

        def cell2(ev, n):
            r.cell("CR2-2", "GUARD", "phase 1 served: a client2 poll on dialog 68 (EVIDENCE only, never asserted: RESTASH, ICON0 / ICON1, "
                   "H0 == the host copy's fnv at the pause)", ev.get("c2 on 68 s") is not None,
                   {"c2 on 68 s": ev.get("c2 on 68 s"), "join_tcp": ev.get("join_tcp"), "RESTASH": CR.since(h, n_h, CR.RESTASH),
                    "ICON0": icon0, "ICON1": icon1, "H0": h0, "at the pause": hp, "H0 == at the pause": h0.get("fnv1a64") == hp.get("fnv1a64")})
        CR.rejoin_tail(r, x, "CR2", KEY_S, gid, cell2)
    except Exception as e:  # Stop, or a probe / kill() / spawn that raised: the row ends here
        r.stop(e)
    r.end("CR2-9", x.client2.user_dir if x.client2 is not None else None, results, walls)


def rec_view(rec, keys=BES.RECORD_FIELDS + ("id", "coop", "coopName", "coopCraft", "where", "dead")):
    return {k: rec.get(k) for k in keys}


def geo_view(gc):
    g = CR.q(gc, {"cmd": "geo_state"})
    return {"funds": g.get("funds"), "monthsPassed": g.get("monthsPassed"), "time": g.get("time"), "error": g.get("error")}


def ending(x, ev):
    """CR4's construction (the C28P ending on the rejoined client2) -> COPY; a WAIT that times out ends the row (Stop)"""
    h, c2 = x.host, x.client2
    if not (CR.alive(c2) and CR.top(h) == CR.BS and CR.top(c2) == CR.BS):
        raise CR.Stop("CR2 left no resumed battle: client2 alive %s, tops %s / %s"
                      % (CR.alive(c2), CR.top(h), CR.top(c2) if CR.alive(c2) else None))
    live = [u.get("id") for u in CR.bs_raw(h).get("units") or [] if u.get("faction") == 1 and not u.get("isOut")]
    ev["kills"] = []
    for uid in live:
        resp = CR.q(h, {"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        sok, secs, _samples = BES.chain_settled(h, c2, stable=1.0, timeout=45, want_live=None)
        ev["kills"].append([uid, resp.get("killed"), secs])
        if not sok:
            raise CR.Stop("WAIT chain_settled(host, client2) after kill_unit_real %s: timed out after %s s" % (uid, secs))
    ev["after the kills"] = {"live hostiles": [u.get("id") for u in CR.bs_raw(h).get("units") or [] if u.get("faction") == 1 and not u.get("isOut")],
                             "players": [CR.pick(u, ("id", "coop", "health", "status", "isOut")) for u in CR.bs_raw(h).get("units") or []
                                         if u.get("faction") == 0]}
    BES.end_turn_both(h, c2)
    ev["close_host_nextturn"] = BES.close_host_nextturn(h)
    ev["host DebriefingState s"] = CR.wait("the host's DebriefingState", lambda: DEBRIEF in CR.stack(h), 60.0)
    copy = BES.soldier_rec(h, name="Guest Zzz")
    ev["COPY"] = rec_view(copy)
    print("EVIDENCE CR4 ending: %s" % json.dumps(ev, sort_keys=True, default=str), flush=True)
    return copy


def row_cr4(x, results, walls):
    r = CR.Row("CR4", ["CR4-1", "CR4-2", "CR4-3"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c2, own = x.host, x.client2, OWN.get("OWN_BEFORE") or {}
    r.n_h = len(CR.log(h))
    try:
        copy, ctx = ending(x, {}), {}
        f1 = BES.cell_debriefs(h, c2, ctx)
        hv, cv = BES.debrief_view(CR.q(h, {"cmd": "debrief_state"})), BES.debrief_view(CR.q(c2, {"cmd": "debrief_state"}))
        r.cell("CR4-1", "GUARD", "client2's display-only debriefing within %d s, equal to the host's on debrief_view's fields" % BES.CLIENT_DEBRIEF_S,
               not f1, {"fails": f1, "waited": (ctx.get("cell1") or {}).get("waited"), "client2 stack": CR.stack(c2), "views equal": hv == cv,
                        "host": {k: hv.get(k) for k in ("title", "total", "rating")}, "soldiers": [s.get("name") for s in hv.get("soldiers") or []]})
        if CR.top(c2) != DEBRIEF:
            raise CR.Stop("WAIT client2's display-only DebriefingState: timed out after %d s" % BES.CLIENT_DEBRIEF_S)
        ok1, at_geo, secs = BES.client_ok_through_followups(c2, ctx, "ret")
        rec = BES.soldier_rec(c2, sid=own.get("id"))
        sep = BES.record(c2).get("sepReturn") or {}
        diff = {k: [rec.get(k), copy.get(k)] for k in BES.RECORD_FIELDS if rec.get(k) != copy.get(k)}
        r.cell("CR4-2", "GUARD", "client2's OK through its follow-ups -> its own GeoscapeState; sepReturn %s; its own guest's soldier_record "
               "(id %s) == COPY on RECORD_FIELDS; missions == OWN_BEFORE.missions + 1" % (json.dumps(SEP_WANT, sort_keys=True), own.get("id")),
               ok1.get("pressed") is True and at_geo and {k: sep.get(k) for k in SEP_WANT} == SEP_WANT and bool(rec) and bool(copy)
               and not diff and rec.get("missions") == (own.get("missions") or 0) + 1,
               {"OK": ok1, "GeoscapeState": at_geo, "s": secs, "chain": (ctx.get("ret") or {}).get("clientChain"), "stack": CR.stack(c2),
                "sepReturn": sep, "record": rec_view(rec), "RECORD_FIELDS diff": diff,
                "missions": [rec.get("missions"), own.get("missions")], "OWN_BEFORE": rec_view(own)})
        if not at_geo:
            raise CR.Stop("WAIT client2's own GeoscapeState after its OK: timed out after %d s" % BES.OK_S)
        hok = BES.press_ok(h)
        at_geo_h, screens = BES.drain(h) if hok.get("pressed") else (False, [])
        recs, _meta = BES.soldier_recs(h, name="Guest Zzz")
        alive = [rec_view(g) for g in recs if not g.get("dead")]
        try:
            zd = session.assert_client_zero_disk(c2.user_dir) or "clean"
        except AssertionError as e:
            zd = CR.short(e, 300)
        r.cell("CR4-3", "GUARD", "the host's OK + drain -> GeoscapeState; no alive \"Guest Zzz\" on the host; client2 zero-disk",
               hok.get("pressed") is True and at_geo_h and not alive and zd == "clean",
               {"OK": hok, "GeoscapeState": at_geo_h, "screens": screens, "stack": CR.stack(h), "alive Guest Zzz": alive, "records": len(recs),
                "zero-disk": zd, "fatalVote.armed": (CR.q(h, {"cmd": "event_state"}).get("fatalVote") or {}).get("armed")})
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    new = sorted(session._crash_log_snapshot() - r.cr0)
    r.cell("CR4-4", "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new, {"crash": new})
    print("EVIDENCE CR4 QL2-4 (never asserted): %s" % json.dumps(
        {"ICON0": getattr(x, "icon0", None), "ICON at the end": icons(h) if CR.alive(h) else "host gone", "F0": OWN.get("F0"),
         "client2": geo_view(c2) if CR.alive(c2) else "client2 gone", "host": geo_view(h) if CR.alive(h) else "host gone",
         "RESTASH (host log)": len(CR.since(h, 0, CR.RESTASH)), "RESTASH since CR4": CR.since(h, r.n_h, CR.RESTASH)},
        sort_keys=True, default=str), flush=True)
    r.end(None, None, results, walls)


def main():
    return CR.run((("w2r4l2_s", lambda tag: CR.boot_separate(tag, KEY_S, pre=fx), (("CR2", row_cr2), ("CR4", row_cr4))),),
                  "test_campaign_rejoin_separate")


if __name__ == "__main__":
    sys.exit(main())
