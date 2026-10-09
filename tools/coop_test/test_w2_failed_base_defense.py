"""W2-H24 stage S-C2 (spec rewrite/prompts/w2h24_failed_battle_start.md AMENDMENT H24-2 section 3; D261, R-H24-2-7..R-H24-2-10; TASK 0
rewrite/w2h24-task0/sc2/CONSTANTS.md): a co-op CAMPAIGN base defence whose battle file the partner's game refuses. Today S-A's unwind
skips the world restore for a base defence: the host is back on the world map with the session live, the base still marked in battle
and the stores the battle took gone, and the partner is told nothing. D261: the session ends - "ERROR: Out Of Sync" (CoopState 999)
over the host's world map, "Server connection lost" (CoopState 21) on the partner, each OK to the main menu (existing UI only).
  Boot B0 (lobby key "48587", w2h24_f_host / _client): B0 the negative control, a clean co-op base-defence start.
  Boot BR (lobby key "48584", w2h24_d_host / _client): BR the host corrupts the battle file (corrupt_next_blob), the partner refuses it.
  Cells: B0-1 GUARD the start works, B0-2 GUARD MARKS = the base's one mark, B0-3 GUARD CRASH 0; BR-1 GUARD refused, BR-2 RED UNWIND
  reads the session end, BR-3 RED the host explains (999), BR-4 RED the partner is told (21), BR-5 RED both land on the main menu,
  BR-6 GUARD CRASH 0.
  Stage S-C1 (AMENDMENT H24-2 section 4; D260 (b), R-H24-2-11..R-H24-2-14; TASK 0 rewrite/w2h24-task0/sc1/CONSTANTS.md T0-D1): a co-op
  CAMPAIGN base defence whose partner's game dies during the ~1 s start. Today the host sits on "Waiting for <name> to reconnect..." over
  a briefing that can never start, the base marked in battle and short of the stores the battle took, and a rejoin never reaches
  RESUME. D260 (b): the host waits on the world map with the base given back what the start took; once the partner is back and RESUME
  is pressed, the defence starts again for both.
  Boot BD (lobby key "48588", w2h24_e_host / _client / _client2): BD the client's hold_battle_ready armed, the trigger, the window (host
  Handshake + client held), U1, client.kill(), observe W, S1 / MARKS, then client2 rejoins (rejoin(): a copy of
  test_w2_failed_battle_start.rejoin() with a 60 s resumeAck cap, ending at RESUME) and both reach phase Active within 60 s, U2.
  Cells: BD-1 RED UNWIND, BD-2 RED the host waits on the world map, BD-3 RED the stores are back (S1 == S0), BD-4 RED MARKS 0, BD-5 RED
  the defence starts again for both (U2 == U1), BD-6 GUARD CRASH 0.
BASEDEF = test_w2_failed_battle_start.camp() through drain_host_coop_notice (host squad of 3 on the Skyranger, the client's "Guest"
transferred to the host base and seated), then the baseline (host base_report storage S0 + soldier ids R0, MARKS []), spawn_ufo
(test_shared_base_defense.py's arguments), the row's lever, the needle baseline, trigger_base_defense (reply base = the host base).
U = the host's battle_state.units soldierIds (faction 0, soldierId != -1).
W = 15 s, POLL = 0.2 s. MARKS / UNWIND / CRASH, the flow rule, the EVIDENCE / CAPTURE lines and the row bookkeeping are
test_w2_failed_battle_start's (imported, unchanged). A WAIT that times out (or a lever reply that is not ok) ends the row, its later
cells "not reached"; a boot miss fails its row "boot"; every row runs after a failure; ONE run (WV-D95); exit 0 iff every cell passes,
else 2. Red (TASK 0 T0-R1): B0 PASS, BR FAIL BR-2..BR-5. Red (S-C1, T0-D1): B0, BR PASS; BD FAIL BD-1..BD-5, BD-6 PASS.
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
from test_w2_failed_battle_start import (q, lever, stack, bstate, coop, dlg, log, since, marks, wait, changes,  # noqa: E402
                                         Row, Stop, short)

W, POLL = 15.0, 0.2
KEY_B0, KEY_BR, KEY_BD = "48587", "48584", "48588"
REFUSE, MISMATCH = "battle_refuse received (battleId=", "battle blob sha MISMATCH (battleId="
CLIENT_ACTIVE, UNWIND = "CLIENT phase Active (battleId=", "W2-H24: failed battle start ("
ENDS = "(refused) - a refused base defense ends the session"
TODAY = "(refused) unwound - battle marks cleared=0, crafts sent home=0"
REARMED, PREPARED = "battle marks cleared=1, crafts sent home=0", "battle offer PREPARED (battleId="
RESUMED_GUARD = "offerResumedBattle() called outside a disk resume (phase="
OOS, LOST, BASE_MARK = "ERROR: Out Of Sync", "Server connection lost", "bases/inBattlescape"
GEO, BRF, MENU, BS, COOP = "GeoscapeState", "BriefingState", "MainMenuState", "BattlescapeState", "CoopState"
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}


class BRow(Row):
    def boot_miss(self, results, walls):
        print("EVIDENCE %s boot: %s\nFAIL %s boot: BASEDEF did not reach the base-defence trigger" % (self.rid, self.x.err, self.rid),
              flush=True)
        self.fails.append("boot")
        self.end(None, results, walls)


def basedef_head(x, key):
    """test_w2_failed_battle_start.camp() through S.drain_host_coop_notice(host): the host squad of 3 on the Skyranger, the client's
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


def trigger(r, x, corrupt):
    """the BASEDEF baseline, the row's lever, the needle baseline, trigger_base_defense -> the client's log size at the baseline"""
    h, c = x.host, x.client
    b = q(h, {"cmd": "base_report"})
    if b.get("name") != x.hbase:
        raise Stop("host base_report: %s" % json.dumps(b, default=str)[:300])
    x.s0, x.r0 = b.get("storage") or {}, sorted(s.get("id") for s in b.get("soldiers") or [])
    m0 = marks(h, "w2h24_%s_pre.sav" % r.rid.lower())
    if m0["flags"] != []:
        raise Stop("baseline MARKS not []: %s" % m0)
    ufo = lever(h, UFO)
    if corrupt:
        lever(h, {"cmd": "corrupt_next_blob"})
    r.ctx["n_h"], n_c = len(log(h)), len(log(c))
    t = lever(h, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")})
    if t.get("base") != x.hbase:
        raise Stop("trigger_base_defense hit %r, not the host base %r" % (t.get("base"), x.hbase))
    return n_c


def row_b0(x, results, walls):
    r = BRow("B0", ["B0-1", "B0-2"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        n_c = trigger(r, x, False)
        t0 = time.time()
        wait("both phase Active", lambda: bstate(h)["phase"] == "Active" and bstate(c)["phase"] == "Active", 30.0)
        hb, cb, mt = bstate(h), bstate(c), q(h, {"cmd": "battle_state"}).get("missionType")
        act, unw = since(c, n_c, CLIENT_ACTIVE), since(h, r.ctx["n_h"], UNWIND)
        r.cell("B0-1", "GUARD", 'the start works: both phase Active, equal non-zero battleId, host missionType "STR_BASE_DEFENSE", '
               "client CLIENT phase Active +1, UNWIND +0", hb["phase"] == cb["phase"] == "Active" and bool(hb["battleId"])
               and hb["battleId"] == cb["battleId"] and mt == "STR_BASE_DEFENSE" and len(act) == 1 and not unw,
               {"host": hb, "client": cb, "missionType": mt, "active": act, "UNWIND": unw, "s to both Active": round(time.time() - t0, 2)})
        r.ctx["MARKS"] = marks(h, "w2h24_b0.sav")
        fl = r.ctx["MARKS"]["flags"]
        r.cell("B0-2", "GUARD", 'MARKS = 1 line ending "%s" (the live defence\'s mark)' % BASE_MARK,
               fl is not None and len(fl) == 1 and fl[0].endswith(BASE_MARK), r.ctx["MARKS"])
    except Exception as e:  # Stop, or a lever that raised: the row ends here
        r.stop(e)
    r.end("B0-3", results, walls)


def shown(polls, code, title):
    return [[t, d] for t, d in polls if d.get("code") == code and d.get("title") == title and d.get("backVisible") is True][:1]


def row_br(x, results, walls):
    r = BRow("BR", ["BR-%d" % i for i in range(1, 6)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        n_c = trigger(r, x, True)
        tt = time.time()
        wait("host battle_refuse received +1", lambda: since(h, r.ctx["n_h"], REFUSE), 30.0)
        t_ref, t0, polls, hd, cd = round(time.time() - tt, 2), time.time(), [], [], []
        while time.time() - t0 < W:  # observe both machines for W: stacks, dialog codes / titles / backVisible
            t, hs, cs, hdl, cdl = round(time.time() - t0, 2), stack(h), stack(c), dlg(h), dlg(c)
            polls.append((t, [hs, hdl.get("code"), cs, cdl.get("code")]))
            hd.append((t, hdl)); cd.append((t, cdl))
            time.sleep(POLL)
        hs_w, hc_w, cc_w = stack(h), coop(h), coop(c)
        b1 = q(h, {"cmd": "base_report"})
        gone = {k: [v, (b1.get("storage") or {}).get(k, 0)] for k, v in x.s0.items() if (b1.get("storage") or {}).get(k, 0) != v}
        r.ctx["MARKS"] = marks(h, "w2h24_br.sav") if q(h, {"cmd": "world_state"}).get("has_save") else {"flags": None, "has_save": False}
        ref, mis, act = since(h, r.ctx["n_h"], REFUSE), since(c, n_c, MISMATCH), since(c, n_c, CLIENT_ACTIVE)
        unw = since(h, r.ctx["n_h"], UNWIND)
        r.cell("BR-1", "GUARD", "refused: host refuse +1 with reason=corrupt; client sha MISMATCH +1; client CLIENT phase Active +0",
               len(ref) == 1 and "reason=corrupt" in ref[0] and len(mis) == 1 and not act,
               {"refuse": ref, "mismatch": mis, "active": act, "s to refuse": t_ref})
        r.cell("BR-2", "RED", 'UNWIND +1 reading "%s" (red today: "%s", T0-R1)' % (ENDS, TODAY), len(unw) == 1 and ENDS in unw[0],
               {"UNWIND": unw, "MARKS": r.ctx["MARKS"], "stores gone vs S0": gone,
                "soldiers same": sorted(s.get("id") for s in b1.get("soldiers") or []) == x.r0 if b1.get("soldiers") else None})
        h999 = shown(hd, 999, OOS)
        r.cell("BR-3", "RED", 'the host explains: a host poll in W shows code 999 "%s" backVisible true; at W host coopSession false, no '
               "BriefingState on its stack (red today: [GeoscapeState], no dialog, coopSession true, T0-R1)" % OOS,
               bool(h999) and hc_w.get("coopSession") is False and BRF not in hs_w,
               {"first 999": h999, "host stack at W": hs_w, "host get_coop at W": hc_w, "stacks": changes(polls)})
        c21 = shown(cd, 21, LOST)
        r.cell("BR-4", "RED", 'the partner is told: a client poll in W shows code 21 "%s" backVisible true (red today: [GeoscapeState], '
               "no dialog, T0-R1)" % LOST, bool(c21), {"first 21": c21, "client get_coop at W": cc_w})
        pressed, menu = {}, {}
        for gc, code in ((h, 999), (c, 21)):
            d = dlg(gc)
            pressed[gc.name] = (q(gc, {"cmd": "coop_dialog_back"}) if d.get("code") == code and d.get("backVisible") is True
                                else {"not pressed": d})
        tp = time.time()
        while time.time() - tp < W and any(p.get("ok") is True and n not in menu for n, p in pressed.items()):
            for gc in (h, c):
                if gc.name not in menu and pressed[gc.name].get("ok") is True and stack(gc)[-1:] == [MENU] \
                        and q(gc, {"cmd": "world_state"}).get("has_save") is False:
                    menu[gc.name] = round(time.time() - tp, 2)
            time.sleep(POLL)
        r.cell("BR-5", "RED", "both land on the main menu: coop_dialog_back on the host's 999 and the client's 21; within 15 s each top "
               "MainMenuState, world_state.has_save false (red today: no dialog to press, T0-R1)",
               all(p.get("ok") is True for p in pressed.values()) and len(menu) == 2,
               {"pressed": pressed, "s to main menu": menu, "host stack": stack(h), "client stack": stack(c)})
    except Exception as e:  # Stop, or a lever that raised: the row ends here
        r.stop(e)
    r.end("BR-6", results, walls)


def units(gc):
    """U: the soldierIds of gc's battle_state units on the player side (faction 0, soldierId != -1), sorted"""
    return sorted(u.get("soldierId") for u in q(gc, {"cmd": "battle_state"}).get("units") or []
                  if u.get("faction") == 0 and u.get("soldierId", -1) != -1)


def rejoin(x, n_h, ev):
    """client2 rejoins: a copy of test_w2_failed_battle_start.rejoin() (test_rejoin_flow.py :47-:70) on key "48588" with a 60 s
    resumeAck cap, ending at RESUME (the re-armed defence then takes client2 into the battle, so the copy's client2-GeoscapeState wait
    and its CoopState 52 sampler are left out) -> True when resumeAck came and RESUME was pressed; ev collects the values"""
    h = x.host
    try:
        x.client2 = GameClient("client2", 3, make_user_dir(x.tag + "_client2"))
        x.client2.spawn(); x.client2.connect()
        ev["join_tcp"] = x.client2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY_BD, "player": "ClientPlayer"})
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
    except Exception as e:  # a timed-out wait (Stop / TimeoutError) or a machine gone: BD-5's own evidence
        ev["wait"] = short(e, 300)
    ev.update({"host stack": stack(h), "host dialog": dlg(h), "client2 stack": stack(x.client2), "client2 dialog": dlg(x.client2),
               "resumed-offer guard": since(h, n_h, RESUMED_GUARD)})
    return "resumeAck s" in ev and (ev.get("RESUME") or {}).get("ok") is True


def row_bd(x, results, walls):
    r = BRow("BD", ["BD-%d" % i for i in range(1, 6)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        lever(c, {"cmd": "hold_battle_ready", "on": True}, key="armed")
        trigger(r, x, False)
        tt = time.time()
        wait("host phase Handshake and client held", lambda: bstate(h)["phase"] == "Handshake"
             and q(c, {"cmd": "hold_battle_ready"}).get("held") is True, 30.0)
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
        r.ctx["MARKS"] = marks(h, "w2h24_bd.sav")
        unw = since(h, r.ctx["n_h"], UNWIND)
        why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
        path = {"first poll after the kill": first, "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first["phase"], "?"),
                "UNWIND reason": why}
        r.cell("BD-1", "RED", 'UNWIND +1 reading "(partner dropped)" or "(partner lost)" and "%s" (red today: 0 lines, T0-D1)' % REARMED,
               len(unw) == 1 and bool(why) and REARMED in unw[0], {"UNWIND": unw, "path": path, "window": win, "U1": u1})
        r.cell("BD-2", "RED", "the host waits on the world map: at W the stack ends [GeoscapeState, CoopState], dialog 62, no "
               "BriefingState / BattlescapeState, inBattle false, phase Idle (red today: 62 over BriefingState, inBattle true, T0-D1)",
               hs[-2:] == [GEO, COOP] and d.get("code") == 62 and BRF not in hs and BS not in hs and hb["inBattle"] is False
               and hb["phase"] == "Idle", {"stack": hs, "dialog": d, "battle": hb, "stacks": changes(polls)})
        r1 = sorted(s.get("id") for s in b1.get("soldiers") or [])
        r.cell("BD-3", "RED", "the stores are back: S1 == S0 (red today: 12 item types short, T0-D1)", s1 == x.s0,
               {"S1 vs S0 differences": diff, "base": b1.get("name"), "soldiers after the drop": r1, "R0": x.r0})
        r.cell("BD-4", "RED", "MARKS = 0 lines (red today: 1, bases/inBattlescape, T0-D1)", r.ctx["MARKS"]["flags"] == [], r.ctx["MARKS"])
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
        r.cell("BD-5", "RED", "the defence starts again for both: resumeAck true, RESUME pressed, host PREPARED +1 after the RESUME, "
               'within 60 s both phase Active with equal battleId, host missionType "STR_BASE_DEFENSE", U2 == U1 (red today: resumeAck '
               "never true in 60 s, T0-D1)", ok and len(prep) == 1 and hb2["phase"] == cb2.get("phase") == "Active" and bool(hb2["battleId"])
               and hb2["battleId"] == cb2.get("battleId") and mt == "STR_BASE_DEFENSE" and bool(u1) and u2 == u1, ev)
    except Exception as e:  # Stop, or a lever / kill() that raised: the row ends here
        r.stop(e)
    r.end("BD-6", results, walls)


def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for tag, key, row in (("w2h24_f", KEY_B0, row_b0), ("w2h24_d", KEY_BR, row_br), ("w2h24_e", KEY_BD, row_bd)):
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
    rows = ("B0", "BR", "BD")
    failed += [rid for rid in rows if not results.get(rid)]
    print("\ntest_w2_failed_base_defense: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid in rows if results.get(rid)), len(rows), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
