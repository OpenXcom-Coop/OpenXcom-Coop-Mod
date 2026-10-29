"""test_failed_base_defense.py: a co-op CAMPAIGN base defence whose start fails. A refused base defence takes the shared
unwind like every other failed start; this test leaves that path unasserted.
  Boot base_defense_clean (lobby key "48587", base_defense_clean_host / _client): clean_start, the negative control, a
  clean co-op base-defence start.
  Cells: clean_start-works GUARD the start works, clean_start-marks GUARD MARKS = the base's one mark,
  clean_start-no_crash GUARD CRASH 0.
  partner_drops: a co-op CAMPAIGN base defence whose partner's game dies during the ~1 s start. When broken, the host
  sits on "Waiting for <name> to reconnect..." over a briefing that can never start, the base marked in battle and short
  of the stores the battle took, and a rejoin never reaches RESUME. Wanted: the host waits on the world map with the
  base given back what the start took; once the partner is back and RESUME is pressed, the defence starts again for
  both.
  Boot base_defense_drop (lobby key "48588", base_defense_drop_host / _client / _client2): partner_drops, the client's
  hold_battle_ready armed, the trigger, the window (host Handshake + client held), U1, client.kill(), observe W, S1 /
  MARKS, then client2 rejoins (rejoin(): a copy of test_failed_battle_start.rejoin() with a 60 s resumeAck cap, ending
  at RESUME) and both reach phase Active within 60 s, U2.
  Cells: partner_drops-1 FIX UNWIND, partner_drops-2 FIX the host waits on the world map, partner_drops-3 FIX the
  stores are back (S1 == S0), partner_drops-4 FIX MARKS 0, partner_drops-5 FIX the defence starts again for both
  (U2 == U1), partner_drops-no_crash GUARD CRASH 0.
BASEDEF = test_failed_battle_start.camp() through drain_host_coop_notice (host squad of 3 on the Skyranger, the client's "Guest"
transferred to the host base and seated), then the baseline (host base_report storage S0 + soldier ids R0, MARKS []), spawn_ufo
(test_shared_base_defense.py's arguments), the needle baseline, trigger_base_defense (reply base = the host base).
U = the host's battle_state.units soldierIds (faction 0, soldierId != -1).
W = 15 s, POLL = 0.2 s. MARKS / UNWIND / CRASH, the flow rule, the EVIDENCE / CAPTURE lines and the row bookkeeping are
test_failed_battle_start's (imported, unchanged). A WAIT that times out (or a test command reply that is not ok) ends
the row, its later cells "not reached"; a boot miss fails its row "boot"; every row runs after a failure; ONE run;
exit 0 iff every cell passes, else 2. A build where a dropped partner leaves the host stuck passes clean_start and fails
partner_drops-1 .. partner_drops-5 (partner_drops-no_crash passes).
"""
import json
import os
import re
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
from test_failed_battle_start import (q, hook_cmd, stack, bstate, coop, dlg, log, since, marks, wait,  # noqa: E402
                                      changes, Row, Stop, short)

W, POLL = 15.0, 0.2
WATCH_CAP_S = 135  # a start wait ends at both phase Active; >= max(120, 2.5 x 30.4 s)
KEY_CLEAN, KEY_DROP = "48587", "48588"
CLIENT_ACTIVE, UNWIND = "CLIENT phase Active (battleId=", "failed battle start ("
REARMED, PREPARED = "battle marks cleared=1, crafts sent home=0", "battle offer PREPARED (battleId="
RESUMED_GUARD = "offerResumedBattle() called outside a disk resume (phase="
BASE_MARK = "bases/inBattlescape"
GEO, BRF, BS, COOP = "GeoscapeState", "BriefingState", "BattlescapeState", "CoopState"
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}


class BRow(Row):
    def boot_miss(self, results, walls):
        print("EVIDENCE %s boot: %s\nFAIL %s boot: BASEDEF did not reach the base-defence trigger" % (self.rid, self.x.err, self.rid),
              flush=True)
        self.fails.append("boot")
        self.end(None, results, walls)


def basedef_head(x, key):
    """test_failed_battle_start.camp() through S.drain_host_coop_notice(host): the host squad of 3 on the Skyranger, the client's
    "Guest" transferred to the host base and seated on the Skyranger (no site, no craft_force, no landing prompt)"""
    host, client, S = x.host, x.client, session
    S.new_campaign(host, client, port=key)
    hb = S._campaign_own_roster_base(host)
    x.cid, rh, x.hbase = S._campaign_skyranger(host)["id"], sorted(s["id"] for s in hb["soldiers"]), hb["name"]
    for sid in rh:
        host.cmd({"cmd": "craft_assign", "craft_id": x.cid, "soldier_id": sid, "on": False})
    for sid in rh[:3]:
        r = host.cmd({"cmd": "craft_assign", "craft_id": x.cid, "soldier_id": sid, "on": True})
        assert r.get("seated"), "host soldier %s not seated: %r" % (sid, r)
    spare = next(s for s in S._campaign_own_roster_base(client)["soldiers"] if not s.get("craft"))["name"]
    client.ok({"cmd": "rename_soldier", "name": spare, "newName": "Guest Zzz"})
    tr = client.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": hb["name"]})
    assert tr.get("transferred"), "guest transfer failed: %r" % tr
    client.ok({"cmd": "visit_coop_base", "base": hb["name"]})
    client.wait_for("client inside host base", lambda: client.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = client.wait_for("guest visible at host base", lambda: (lambda r: r if any("Guest" in s["name"] for s in r["soldiers"]) else None)(
        client.ok({"cmd": "base_report", "coop": True})), timeout=40)
    guest = next(s for s in rep["soldiers"] if "Guest" in s["name"])["id"]
    craft = next(c for c in rep["crafts"] if "SKYRANGER" in c["type"])["id"]
    client.ok({"cmd": "craft_assign", "soldier_id": guest, "craft_id": craft, "coop": True, "on": True})
    client.ok({"cmd": "open_soldiers", "base": hb["name"]})
    client.wait_for("client soldiers screen", lambda: S.has_state(client, "SoldiersState") or None, timeout=30)
    client.ok({"cmd": "soldiers_ok"}); client.ok({"cmd": "leave_base"})
    S.wait_back_on_geoscape(client, "client back on geoscape")
    S.drain_host_coop_notice(host)


def boot(tag, key):
    x = SimpleNamespace(tag=tag, host=None, client=None, client2=None, err=None, cid=None, hbase=None, s0=None, r0=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        basedef_head(x, key)
    except Exception as e:
        x.err = short(e, 600)
    return x


def trigger(r, x):
    """the BASEDEF baseline, the needle baseline, trigger_base_defense -> the client's log size at the baseline"""
    h, c = x.host, x.client
    b = q(h, {"cmd": "base_report"})
    if b.get("name") != x.hbase:
        raise Stop("host base_report: %s" % json.dumps(b, default=str)[:300])
    x.s0, x.r0 = b.get("storage") or {}, sorted(s.get("id") for s in b.get("soldiers") or [])
    m0 = marks(h, "base_defense_%s_pre.sav" % r.rid.lower())
    if m0["flags"] != []:
        raise Stop("baseline MARKS not []: %s" % m0)
    ufo = hook_cmd(h, UFO)
    r.ctx["n_h"], n_c = len(log(h)), len(log(c))
    t = hook_cmd(h, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    if t.get("base") != x.hbase:
        raise Stop("trigger_base_defense hit %r, not the host base %r" % (t.get("base"), x.hbase))
    return n_c


def row_clean_start(x, results, walls):
    r = BRow("clean_start", ["clean_start-works", "clean_start-marks"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        n_c = trigger(r, x)
        t0 = time.time()
        wait("both phase Active", lambda: bstate(h)["phase"] == "Active" and bstate(c)["phase"] == "Active",
             WATCH_CAP_S)
        hb, cb, mt = bstate(h), bstate(c), q(h, {"cmd": "battle_state"}).get("missionType")
        act, unw = since(c, n_c, CLIENT_ACTIVE), since(h, r.ctx["n_h"], UNWIND)
        r.cell("clean_start-works", "GUARD", 'the start works: both phase Active, equal non-zero battleId, host '
               'missionType "STR_BASE_DEFENSE", client CLIENT phase Active +1, UNWIND +0',
               hb["phase"] == cb["phase"] == "Active" and bool(hb["battleId"])
               and hb["battleId"] == cb["battleId"] and mt == "STR_BASE_DEFENSE" and len(act) == 1 and not unw,
               {"host": hb, "client": cb, "missionType": mt, "active": act, "UNWIND": unw, "s to both Active": round(time.time() - t0, 2)})
        r.ctx["MARKS"] = marks(h, "base_defense_clean_marks.sav")
        fl = r.ctx["MARKS"]["flags"]
        r.cell("clean_start-marks", "GUARD", 'MARKS = 1 line ending "%s" (the live defence\'s mark)' % BASE_MARK,
               fl is not None and len(fl) == 1 and fl[0].endswith(BASE_MARK), r.ctx["MARKS"])
    except Exception as e:  # Stop, or a test command that raised: the row ends here
        r.stop(e)
    r.end("clean_start-no_crash", results, walls)


def units(gc):
    """U: the soldierIds of gc's battle_state units on the player side (faction 0, soldierId != -1), sorted"""
    return sorted(u.get("soldierId") for u in q(gc, {"cmd": "battle_state"}).get("units") or []
                  if u.get("faction") == 0 and u.get("soldierId", -1) != -1)


def rejoin(x, n_h, ev):
    """client2 rejoins: a copy of test_failed_battle_start.rejoin() (test_rejoin_flow.py :47-:70) on key "48588" with a 60 s
    resumeAck cap, ending at RESUME (the re-armed defence then takes client2 into the battle, so the copy's client2-GeoscapeState wait
    and its CoopState 52 sampler are left out) -> True when resumeAck came and RESUME was pressed; ev collects the values"""
    h = x.host
    try:
        x.client2 = GameClient("client2", 3, make_user_dir(x.tag + "_client2"))
        x.client2.spawn(); x.client2.connect()
        ev["join_tcp"] = x.client2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY_DROP,
                                        "player": "ClientPlayer"})
    except Exception as e:
        ev["join"] = short(e)
        return False
    t0 = time.time()
    try:
        wait("host resumeAck", lambda: coop(h).get("resumeAck") is True, 60.0)
        ev["resumeAck s"] = round(time.time() - t0, 1)
        if session.has_state(h, "Profile"):
            ev["host profile_ok"] = q(h, {"cmd": "profile_ok"})
            time.sleep(0.5)
        ev["n_h at RESUME"] = len(log(h))
        ev["RESUME"] = session.press_back_when_shown(h, "host RESUME", codes=(60, 62))
    except Exception as e:  # a timed-out wait (Stop / TimeoutError) or a machine gone: partner_drops-5's own evidence
        ev["wait"] = short(e, 300)
    ev.update({"host stack": stack(h), "host dialog": dlg(h), "client2 stack": stack(x.client2), "client2 dialog": dlg(x.client2),
               "resumed-offer guard": since(h, n_h, RESUMED_GUARD)})
    return "resumeAck s" in ev and (ev.get("RESUME") or {}).get("ok") is True


def row_partner_drops(x, results, walls):
    r = BRow("partner_drops", ["partner_drops-%d" % i for i in range(1, 6)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        hook_cmd(c, {"cmd": "hold_battle_ready", "on": True}, key="armed")
        trigger(r, x)
        tt = time.time()
        wait("host phase Handshake and client held", lambda: bstate(h)["phase"] == "Handshake"
             and q(c, {"cmd": "hold_battle_ready"}).get("held") is True, WATCH_CAP_S)
        win, u1 = {"s to the window": round(time.time() - tt, 2), "host stack": stack(h)}, units(h)
        c.kill()
        tk, polls = time.time(), []
        first = dict(bstate(h), t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append((round(time.time() - tk, 2), stack(h)))
            time.sleep(POLL)
        hs, hb, d, b1 = stack(h), bstate(h), dlg(h), q(h, {"cmd": "base_report"})
        s1 = b1.get("storage") or {}
        diff = {k: [x.s0.get(k, 0), s1.get(k, 0)] for k in sorted(set(x.s0) | set(s1)) if x.s0.get(k, 0) != s1.get(k, 0)}
        r.ctx["MARKS"] = marks(h, "base_defense_drop_marks.sav")
        unw = since(h, r.ctx["n_h"], UNWIND)
        why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
        path = {"first poll after the kill": first, "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first["phase"], "?"),
                "UNWIND reason": why}
        r.cell("partner_drops-1", "FIX",
               'UNWIND +1 reading "(partner dropped)" or "(partner lost)" and "%s" (when broken: 0 lines)' % REARMED,
               len(unw) == 1 and bool(why) and REARMED in unw[0], {"UNWIND": unw, "path": path, "window": win, "U1": u1})
        r.cell("partner_drops-2", "FIX", "the host waits on the world map: at W the stack ends [GeoscapeState, "
               "CoopState], dialog 62, no BriefingState / BattlescapeState, inBattle false, phase Idle (when broken: "
               "62 over BriefingState, inBattle true)",
               hs[-2:] == [GEO, COOP] and d.get("code") == 62 and BRF not in hs and BS not in hs and hb["inBattle"] is False
               and hb["phase"] == "Idle", {"stack": hs, "dialog": d, "battle": hb, "stacks": changes(polls)})
        r1 = sorted(s.get("id") for s in b1.get("soldiers") or [])
        r.cell("partner_drops-3", "FIX", "the stores are back: S1 == S0 (when broken: 12 item types short)", s1 == x.s0,
               {"S1 vs S0 differences": diff, "base": b1.get("name"), "soldiers after the drop": r1, "R0": x.r0})
        r.cell("partner_drops-4", "FIX", "MARKS = 0 lines (when broken: 1, bases/inBattlescape)",
               r.ctx["MARKS"]["flags"] == [], r.ctx["MARKS"])
        ev = {}
        ok = rejoin(x, len(log(h)), ev)
        if ok:
            try:
                wait("both phase Active after RESUME", lambda: bstate(h)["phase"] == "Active"
                     and bstate(x.client2)["phase"] == "Active", 60.0)
            except Stop as e:
                ev["both Active"] = short(e, 200)
        hb2, cb2 = bstate(h), bstate(x.client2) if x.client2 is not None else {}
        mt, u2 = q(h, {"cmd": "battle_state"}).get("missionType"), units(h)
        prep = since(h, ev["n_h at RESUME"], PREPARED) if "n_h at RESUME" in ev else []
        r2 = sorted(s.get("id") for s in q(h, {"cmd": "base_report"}).get("soldiers") or [])
        ev.update({"host": hb2, "client2": cb2, "missionType": mt, "PREPARED after RESUME": prep, "U1": u1, "U2": u2,
                   "soldiers after the rejoin": r2})
        r.cell("partner_drops-5", "FIX", "the defence starts again for both: resumeAck true, RESUME pressed, host "
               'PREPARED +1 after the RESUME, within 60 s both phase Active with equal battleId, host missionType '
               '"STR_BASE_DEFENSE", U2 == U1 (when broken: resumeAck never true in 60 s)',
               ok and len(prep) == 1 and hb2["phase"] == cb2.get("phase") == "Active" and bool(hb2["battleId"])
               and hb2["battleId"] == cb2.get("battleId") and mt == "STR_BASE_DEFENSE" and bool(u1) and u2 == u1, ev)
    except Exception as e:  # Stop, or a test command / kill() that raised: the row ends here
        r.stop(e)
    r.end("partner_drops-no_crash", results, walls)


def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for tag, key, row in (("base_defense_clean", KEY_CLEAN, row_clean_start),
                          ("base_defense_drop", KEY_DROP, row_partner_drops)):
        tb = time.time()
        x = boot(tag, key)
        walls[tag + " BASEDEF"] = round(time.time() - tb, 1)
        row(x, results, walls)
        for gc in (x.client2, x.client, x.host):  # each boot shut down before the next (kill() already reaped a killed client)
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:
                print("FAIL %s shutdown (%s): %s" % (tag, gc.name, short(e, 300)), flush=True)
                failed.append("%s shutdown %s" % (tag, gc.name))
        walls[tag] = round(time.time() - tb, 1)
    rows = ("clean_start", "partner_drops")
    failed += [rid for rid in rows if not results.get(rid)]
    print("\ntest_failed_base_defense: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid in rows if results.get(rid)), len(rows), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
