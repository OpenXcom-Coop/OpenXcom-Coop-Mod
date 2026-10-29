"""W2-H34 stage S-A (spec rewrite/prompts/w2h34_separate_copy_refresh.md (f); TASK 0 rewrite/w2h34-task0/sa/CONSTANTS.md; orchestrator ruling
R-9B-6, QH34-1..7 (a); F10982, F12420, F12421, F12511, F12512): a SEPARATE second player who rejoins a battle gets the host's stale copy of
its world back. The host's copy of a SEPARATE client's world is refreshed only by the client's pushes (base placement, gifts, the return, a
host save), never at a battle entry, so a rejoin adopts the base-placement push (monthsPassed -1): at the return the client is charged the
start-of-game maintenance a second time (GeoscapeState's first-month block) and its guest's seat on the host's craft is lost.
  Boot J (key "48604", dirs w2h34_j_host / _client / _client2): CR.boot_separate's spawn lines, then bring_up_separate_guest_battle(
  pre_mission_start=fx, pre_landing=pin). fx (the client's own geoscape, before the battle): F_S0 = its funds; MARKER = F_S0 +
  BES.MARKER_DELTA (client set_funds, the C28P marker); GEO0 = its geo_state (funds == MARKER); OWN_BEFORE = its "Guest Zzz" soldier_record;
  OWN_SOLDIER = its get_soldiers record of that id (coopBase); H_FX = copy_view(host) read AFTER the marker; the host log length (REJECT
  baseline). pin: host set_seed BES.SEED_P. Both mapFingerprints == BES.MAP_FP_P. A boot miss fails both rows "boot" with ONE CAPTURE line.
  Row RE (the host's copy at the battle entry): RE-1 FIX within W_COPY 15 s the copy's fnv != H_FX's, then its view funds == MARKER,
  monthsPassed == GEO0's, guest lines >= 1; RE-2 GUARD both tops BattlescapeState, the host's REJECT count since fx 0 (no CoopState 994), HASH.
  Row RJ (client2 returns from a rejoined battle; R4-L2's CR2 + CR4 construction): CR.baseline, client.kill(), CR.pause, CR.rejoin, CR.resume,
  both tops BattlescapeState, COPY = CRS.ending, client2's display-only debriefing, its OK through its follow-ups, +1.0 s reads, the host's
  OK + drain, reads again. RJ-1 GUARD the rejoin resumed (PAUSE, resumeAck, RESUME, both tops, battleId B0 on both, HASH); RJ-2 GUARD client2
  -> its own GeoscapeState, battleEnd.sepReturn includes SEP_WANT; RJ-funds FIX client2's funds == MARKER at +1 s and after the host's OK;
  RJ-guest FIX its guest's soldier_record name / coopCraft / coopCraftType / where / baseIndex == OWN_BEFORE's (MR6: coopCraft -1 and
  coopCraftType "" when COPY.recovery > 0), missions == OWN_BEFORE's + 1, get_soldiers coopBase == OWN_SOLDIER's; RJ-copy FIX within
  BES.FNV_S of client2's OK the copy's fnv changes, its view funds == MARKER, monthsPassed == GEO0's, guest lines >= 1; RJ-end GUARD the
  host's OK + drain -> GeoscapeState, no alive "Guest Zzz" on the host; RJ-crash GUARD CRASH 0 and client2 zero-disk (every case).
copy_view(host) = the PBE host_copy pattern: coop_file_info {role host_copy_of_client}, dump_coop_file on the HOST only (a client stays
zero-disk), parse funds (the last "  - N" under the top-level "funds:"), monthsPassed and the lines holding "Guest Zzz", then remove the dump.
RED at H1 (TASK 0 boots Ja / Jb, decision rule (i)): RE-1, RJ-funds, RJ-guest, RJ-copy FAIL; RE-2, RJ-1, RJ-2, RJ-end, RJ-crash PASS.
GREEN at H2 (E1: the client's first SEPARATE entry uploads its entry snapshot through the save-progress round trip): every cell PASS.
EVIDENCE before each verdict; a WAIT that times out ends its row (later cells "not reached"), except RE-1's wait (RE-2 still runs, RJ runs);
a failed row prints ONE CAPTURE line; every row runs after a failure. ONE foreground run, no SKIP path, exit 0
only when every cell passes, else 2. Definitions, REJOIN, needles and the safe battle_state probe: test_campaign_rejoin.py.
"""
import json
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402  (main-guarded: the C28P marker, pin and return helpers)
import test_campaign_rejoin as CR  # noqa: E402  (main-guarded: Row, run, the rejoin construction)
import test_campaign_rejoin_separate as CRS  # noqa: E402  (main-guarded: ending, rec_view, geo_view, SEP_WANT)
from harness import GameClient, make_user_dir  # noqa: E402

KEY_J = "48604"
GUEST = "Guest Zzz"
W_COPY = 15.0
REJECT = "rejected client progress blob from '"
SEP_WANT = CRS.SEP_WANT
GUEST_FIELDS = ("name", "coopCraft", "coopCraftType", "where", "baseIndex")
FX = {}


def copy_info(host):
    return CR.pick(CR.q(host, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key", "present", "bytes", "fnv1a64", "error"))


def copy_view(host):
    """the host's copy of the client world: its fnv, dump_coop_file on the HOST, the parse, the dump removed after reading"""
    info = copy_info(host)
    key = info.get("key")
    out = {"key": key, "fnv": info.get("fnv1a64"), "bytes": info.get("bytes")}
    if not key:
        return dict(out, error="no key: %s" % info)
    p = os.path.join(host.user_dir, "xcom1", key)
    if os.path.exists(p):
        os.remove(p)
    out["dump"] = CR.q(host, {"cmd": "dump_coop_file", "key": key}).get("ok")
    if not os.path.exists(p):
        return dict(out, error="no dump file")
    with open(p, "rb") as f:
        lines = f.read().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    os.remove(p)
    funds, i = None, next((k for k, ln in enumerate(lines) if ln == "funds:"), None)
    if i is not None:
        j = i + 1
        while j < len(lines) and lines[j].startswith("  - "):
            funds, j = int(lines[j][4:].strip()), j + 1
    out.update(funds=funds, monthsPassed=next((int(ln.split(":", 1)[1]) for ln in lines if ln.startswith("monthsPassed:")), None),
               guest=sum(1 for ln in lines if GUEST in ln))
    return out


def own_soldier(gc, sid):
    """this machine's get_soldiers record with id sid ({} when none)"""
    for b in CR.q(gc, {"cmd": "get_soldiers"}).get("bases") or []:
        for s in b.get("soldiers") or []:
            if s.get("id") == sid:
                return dict(CR.pick(s, ("id", "name", "coop", "coopBase", "craft", "dead")), base=b.get("name"))
    return {}


def view_ok(v):
    """a copy view holding the client's current world: funds == MARKER, monthsPassed == GEO0's, the guest present"""
    return (v.get("funds") == FX.get("MARKER") and v.get("monthsPassed") == (FX.get("GEO0") or {}).get("monthsPassed")
            and (v.get("guest") or 0) >= 1)


def fx(host, client):
    """pre_mission_start: the C28P money marker, then GEO0, OWN_BEFORE, OWN_SOLDIER, H_FX (AFTER the marker), the REJECT baseline"""
    FX["F_S0"] = CR.q(client, {"cmd": "geo_state"}).get("funds")
    FX["MARKER"] = int(FX["F_S0"]) + BES.MARKER_DELTA
    FX["set_funds"] = CR.q(client, {"cmd": "set_funds", "value": FX["MARKER"]}).get("ok")
    FX["GEO0"] = CRS.geo_view(client)
    FX["OWN_BEFORE"] = BES.soldier_rec(client, name=GUEST)
    FX["OWN_SOLDIER"] = own_soldier(client, FX["OWN_BEFORE"].get("id"))
    FX["H_FX"] = copy_view(host)
    FX["N_H"] = len(CR.log(host))


def pin(host, client):
    """pre_landing: the C28P map pin"""
    FX["pin"] = CR.q(host, {"cmd": "set_seed", "seed": BES.SEED_P}).get("ok")


def boot_j(tag):
    """boot J: CR.boot_separate's spawn lines + bring_up_separate_guest_battle(fx, pin); the marker and the map pin checked (x.err on a miss)"""
    x = CR.new_x(tag)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        session.bring_up_separate_guest_battle(x.host, x.client, port=KEY_J, pre_mission_start=fx, pre_landing=pin)
        fp = [CR.bs_raw(gc).get("mapFingerprint") for gc in (x.host, x.client)]
        own, hfx = FX.get("OWN_BEFORE") or {}, FX.get("H_FX") or {}
        print("EVIDENCE boot J: %s" % json.dumps({"FX": dict(FX, OWN_BEFORE=CRS.rec_view(own, GUEST_FIELDS + ("id", "missions", "recovery"))),
                                                  "mapFingerprint": fp}, sort_keys=True, default=str), flush=True)
        missed = [m for m, bad in (("map pin %s (want both %r, SEED_P %s)" % (fp, BES.MAP_FP_P, BES.SEED_P), fp != [BES.MAP_FP_P, BES.MAP_FP_P]),
                                 ("marker: GEO0 funds %s != MARKER %s" % ((FX.get("GEO0") or {}).get("funds"), FX.get("MARKER")),
                                  (FX.get("GEO0") or {}).get("funds") != FX.get("MARKER")),
                                 ("OWN_BEFORE / OWN_SOLDIER missing", not own.get("id") or not FX.get("OWN_SOLDIER")),
                                 ("H_FX unread: %s" % hfx, not hfx.get("fnv") or hfx.get("funds") is None))
                if bad]
        if missed:
            x.err = "FIXTURE: " + "; ".join(missed)
    except Exception as e:
        x.err = CR.short(e, 600)
    return x


def miss(r, results, walls, first):
    """a boot miss: both rows FAIL "boot"; only the first prints the CAPTURE line"""
    print("EVIDENCE %s boot: %s\nFAIL %s boot: boot J missed (bring-up, the marker or the map pin)" % (r.rid, r.x.err, r.rid), flush=True)
    r.fails.append("boot")
    if first:
        return r.end(None, None, results, walls)
    results[r.rid], walls[r.rid] = False, 0.0
    print("FAIL %s: boot" % r.rid, flush=True)


def row_re(x, results, walls):
    r = CR.Row("RE", ["RE-1", "RE-2"], x)
    if x.err:
        return miss(r, results, walls, True)
    h, c, hfx = x.host, x.client, FX["H_FX"]
    try:
        t0, s = time.time(), None
        while time.time() - t0 < W_COPY:
            f = copy_info(h).get("fnv1a64")
            if f and f != hfx.get("fnv"):
                s = round(time.time() - t0, 2)
                break
            time.sleep(CR.POLL)
        now = copy_view(h)
        sh, sc = CR.stack(h), CR.stack(c)
        print("EVIDENCE RE: %s" % json.dumps({"H_FX": hfx, "now": now, "changed s": s, "waited s": round(time.time() - t0, 2),
                                              "host stack": sh, "client stack": sc}, sort_keys=True, default=str), flush=True)
        r.cell("RE-1", "FIX", "within W_COPY %.0f s the host's copy of the client world changes (fnv != H_FX's %s), then its view: funds == "
               "MARKER %s, monthsPassed == GEO0's %s, guest lines >= 1 (red today: fnv unchanged at W_COPY; F_S0 / -1 / 0, F12512)"
               % (W_COPY, hfx.get("fnv"), FX["MARKER"], FX["GEO0"].get("monthsPassed")), s is not None and view_ok(now),
               {"changed s": s, "now": now, "H_FX": hfx})
        rej = CR.since(h, FX["N_H"], REJECT)
        ok, hev = CR.hash_ok(h, c, "RE")
        r.cell("RE-2", "GUARD", "both tops BattlescapeState; the host's REJECT count since fx == 0 (no CoopState 994); HASH(host, client)",
               sh[-1:] == [CR.BS] and sc[-1:] == [CR.BS] and not rej and ok, {"host stack": sh, "client stack": sc, "REJECT": rej, "HASH": hev})
    except Exception as e:  # a probe that raised: the row ends here
        r.stop(e)
    r.end(None, None, results, walls)


def row_rj(x, results, walls):
    r = CR.Row("RJ", ["RJ-1", "RJ-2", "RJ-funds", "RJ-guest", "RJ-copy", "RJ-end"], x)
    if x.err:
        return miss(r, results, walls, False)
    h, c, own, osd, ev, evo = x.host, x.client, FX["OWN_BEFORE"], FX["OWN_SOLDIER"], {}, {}
    try:
        CR.baseline(r, x, c)
        r.n_h = len(CR.log(h))
        c.kill()
        ok, ev["PAUSE"] = CR.pause(x)
        evo["the copy at the pause (F10982)"] = copy_view(h)
        acked = ok and CR.rejoin(x, KEY_J, ev)
        resumed = acked and CR.resume(x, ev)
        c2, tops, hb, cb, hok, hev = x.client2, None, {}, {}, False, "not reached"
        if resumed:
            try:
                tops = CR.wait("both tops BattlescapeState", lambda: CR.top(h) == CR.BS and CR.top(c2) == CR.BS, 60.0)
            except CR.Stop as e:
                ev["tops wait"] = str(e)
        if tops is not None:
            hb, cb = CR.auth(h), CR.auth(c2)
            hok, hev = CR.hash_ok(h, c2, "RJ")
        rj1 = ok and acked and resumed and tops is not None and hb.get("battleId") == cb.get("battleId") == x.b0 and hok
        r.cell("RJ-1", "GUARD", "the rejoin resumed: PAUSE ok, the host's resumeAck acked within W_ACK %.0f s, RESUME pressed, both tops "
               "BattlescapeState <= 60 s, battleId == B0 %s on both, HASH(host, client2)" % (CR.W_ACK, x.b0), rj1,
               dict(ev, tops_s=tops, host=hb, client2=cb, HASH=hev))
        if not rj1:
            raise CR.Stop("RJ-1 missed (%s)" % (ev.get("ack wait") or ev.get("tops wait") or "PAUSE / RESUME / B0 / HASH"))
        copy, ctx = CRS.ending(x, {}), {}
        evo["COPY"] = CRS.rec_view(copy)
        f1 = BES.cell_debriefs(h, c2, ctx)
        if f1 or CR.top(c2) != "DebriefingState":
            raise CR.Stop("WAIT client2's display-only DebriefingState: %s (client2 stack %s)" % (f1, CR.stack(c2)))
        fnv0, t_ok = copy_info(h).get("fnv1a64"), time.time()
        ok1, at_geo, secs = BES.client_ok_through_followups(c2, ctx, "ret")
        if at_geo:
            time.sleep(1.0)
        g1, sep = CRS.geo_view(c2), BES.record(c2).get("sepReturn") or {}
        r.cell("RJ-2", "GUARD", "client2's OK through its follow-ups -> its own GeoscapeState; battleEnd.sepReturn includes %s"
               % json.dumps(SEP_WANT, sort_keys=True), ok1.get("pressed") is True and at_geo and {k: sep.get(k) for k in SEP_WANT} == SEP_WANT,
               {"OK": ok1, "GeoscapeState": at_geo, "s": secs, "chain": (ctx.get("ret") or {}).get("clientChain"), "stack": CR.stack(c2),
                "sepReturn": sep})
        if not (at_geo and {k: sep.get(k) for k in SEP_WANT} == SEP_WANT):
            raise CR.Stop("RJ-2: client2 not on its own GeoscapeState with SEP_WANT (GeoscapeState %s, sepReturn %s)" % (at_geo, sep))
        rec = BES.soldier_rec(c2, sid=own.get("id"))
        osd2 = own_soldier(c2, own.get("id"))
        changed = None
        while time.time() - t_ok < BES.FNV_S:
            f = copy_info(h).get("fnv1a64")
            if f and f != fnv0:
                changed = round(time.time() - t_ok, 2)
                break
            time.sleep(CR.POLL)
        after = copy_view(h)
        hok2 = BES.press_ok(h)
        at_geo_h, screens = BES.drain(h) if hok2.get("pressed") else (False, [])
        g2 = CRS.geo_view(c2)
        evo.update({"client2 +1 s": g1, "client2 after the host's OK": g2, "host": CRS.geo_view(h)})
        r.cell("RJ-funds", "FIX", "client2's funds == MARKER %s 1 s after its GeoscapeState AND after the host's OK + drain (D180 (a); red today: "
               "F_S0 %s - 1869000 both times, F12511)" % (FX["MARKER"], FX["F_S0"]), g1.get("funds") == g2.get("funds") == FX["MARKER"],
               {"+1 s": g1, "after the host's OK": g2, "MARKER": FX["MARKER"], "F_S0": FX["F_S0"]})
        want = {k: own.get(k) for k in GUEST_FIELDS}
        if (copy.get("recovery") or 0) > 0:  # MR6: a wounded guest loses its seat at the return
            want.update(coopCraft=-1, coopCraftType="")
        got = {k: rec.get(k) for k in GUEST_FIELDS}
        r.cell("RJ-guest", "FIX", "client2's guest (soldier_record id %s): %s == %s, missions == OWN_BEFORE's + 1, get_soldiers coopBase == "
               "OWN_SOLDIER's %s (D155 (a); red today: coopCraft -1, coopCraftType \"\", coopBase -1, F12421)" % (own.get("id"), GUEST_FIELDS,
                                                                                                                 want, osd.get("coopBase")),
               bool(rec) and got == want and rec.get("missions") == (own.get("missions") or 0) + 1 and bool(osd2)
               and osd2.get("coopBase") == osd.get("coopBase"),
               {"record": got, "want": want, "missions": [rec.get("missions"), own.get("missions")], "get_soldiers": osd2, "OWN_SOLDIER": osd,
                "COPY.recovery": copy.get("recovery")})
        r.cell("RJ-copy", "FIX", "within BES.FNV_S %d s of client2's OK the host's copy changes (fnv != %s), its view: funds == MARKER %s, "
               "monthsPassed == GEO0's %s, guest lines >= 1 (red today: F_S0 / -1)" % (BES.FNV_S, fnv0, FX["MARKER"], FX["GEO0"].get("monthsPassed")),
               changed is not None and view_ok(after), {"changed s": changed, "fnv before the OK": fnv0, "view": after})
        if changed is None:
            raise CR.Stop("WAIT the host's copy changes after client2's OK: timed out after %d s" % BES.FNV_S)
        recs, _meta = BES.soldier_recs(h, name=GUEST)
        alive = [CRS.rec_view(g) for g in recs if not g.get("dead")]
        r.cell("RJ-end", "GUARD", "the host's OK + drain -> GeoscapeState; no alive \"Guest Zzz\" on the host",
               hok2.get("pressed") is True and at_geo_h and not alive,
               {"OK": hok2, "GeoscapeState": at_geo_h, "screens": screens, "stack": CR.stack(h), "alive Guest Zzz": alive, "records": len(recs)})
    except Exception as e:  # Stop, or a probe / kill() / spawn that raised: the row ends here
        r.stop(e)
    evo["RESTASH (host log)"] = len(CR.since(h, 0, CR.RESTASH)) if CR.alive(h) else "host gone"
    print("EVIDENCE RJ (EVIDENCE only, never asserted): %s" % json.dumps(evo, sort_keys=True, default=str), flush=True)
    r.end("RJ-crash", x.client2.user_dir if x.client2 is not None else None, results, walls)


def main():
    return CR.run((("w2h34_j", boot_j, (("RE", row_re), ("RJ", row_rj))),), "test_sep_copy_refresh")


if __name__ == "__main__":
    sys.exit(main())
