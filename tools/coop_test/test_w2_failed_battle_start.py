"""W2-H24 stage S-A (spec rewrite/prompts/w2h24_failed_battle_start.md (f), QH24-5 a; TASK 0 rewrite/w2h24-task0/CONSTANTS.md): a failed
or refused co-op CAMPAIGN battle start. Refused: the host's craft stays "in battle" at its target, the landing question pops up again
and the .sav keeps inBattlescape for the craft and the site (F5198). The partner lost during the ~1 s start: the host sits on "Waiting
for <name>" over a briefing that can never start and a rejoin never reaches RESUME (F5199).
  Boot A (lobby key "48580", w2h24_a_host / _client): C1 a refused start (host corrupt_next_blob), then C0 the negative control on the
  same world (a clean start, then a mid-battle kill: the SPEC 16 pause). Boot B (key "48581", w2h24_b_host / _client / _client2): C2 the
  partner lost during the start (client hold_battle_ready, then kill), then client2 rejoins (test_rejoin_flow.py :47-:70).
  Cells: C1-1 GUARD refused, C1-2 GUARD no battle, C1-3 RED UNWIND, C1-4 RED no re-prompt, C1-5 RED craft turned home, C1-6 RED MARKS 0,
  C1-7 GUARD the site stays, C1-8 GUARD CRASH 0; C0-1 GUARD the start works, C0-2 GUARD the SPEC 16 pause, C0-3 GUARD CRASH 0; C2-1 RED
  UNWIND, C2-2 RED the host waits on the geoscape, C2-3 RED craft home, C2-4 RED MARKS 0, C2-5 RED the rejoin works (TASK 0 T0-2: the
  kill took the -2 path; today client2 gets the world but the host never reads resumeAck in 120 s), C2-6 GUARD CRASH 0.
W = 15 s, POLL = 0.2 s. CAMP = r4l6 TASK 0 t0_2.py's head (session.bring_up_separate_guest_battle :2446-:2546 through the landing prompt,
geoscape clock left at its speed). SKY = the host's geo_state entry of the craft. MARKS = host save_game, then the file's "inBattlescape:
true" lines with their key paths. UNWIND = host log lines with "W2-H24: failed battle start (" since the row's baseline. CRASH =
session._crash_log_snapshot() delta, read at the row's end in every case. A WAIT that times out (or a lever reply that is not ok) ends
the row, its later cells "not reached". EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; every row runs after a
failure; ONE run (WV-D95); exit 0 iff every cell passes, else 2. Red (commit 1): C1 FAIL C1-3..C1-6, C0 PASS, C2 FAIL C2-1..C2-5.
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

W, POLL = 15.0, 0.2
KEY_A, KEY_B = "48580", "48581"
REFUSE, MISMATCH = "battle_refuse received (battleId=", "battle blob sha MISMATCH (battleId="
CLIENT_ACTIVE, UNWIND = "CLIENT phase Active (battleId=", "W2-H24: failed battle start ("
REJOIN_GUARD, MARKED = "offerRejoinBattle() called while the battle is not ", "battle marks cleared=2, crafts sent home=1"
CLS, GEO, BRF, BS, COOP = "ConfirmLandingState", "GeoscapeState", "BriefingState", "BattlescapeState", "CoopState"

class Stop(Exception):
    """a WAIT timed out or a lever reply was not ok: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}

def lever(gc, obj, key="ok"):
    rep = q(gc, obj)
    if rep.get(key) is not True:
        raise Stop("%s %s: %s" % (gc.name, obj.get("cmd"), json.dumps(rep, default=str)[:300]))
    return rep

def pick(r, keys):
    return {k: r.get(k) for k in keys}

def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]

def bstate(gc):
    r = q(gc, {"cmd": "battle_state"})
    return dict(pick(r, ("phase", "inBattle", "error")), **pick(r.get("authority") or {}, ("battleId", "peerAbsent")))

def coop(gc):
    return pick(q(gc, {"cmd": "get_coop"}), ("onConnect", "coopSession", "lobbyMode", "lobbyClosed", "resumeAck", "coopDialog", "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backVisible", "error"))

def sky(host, cid, sites=False):
    g = q(host, {"cmd": "geo_state"})
    if sites:
        return [s.get("id") for s in g.get("missionSites") or []]
    crafts = [c for b in g.get("bases") or [] if not b.get("coopBase") and not b.get("coopIcon") for c in b.get("crafts") or []]
    return next((pick(c, ("status", "destKind", "destId")) for c in crafts if c.get("id") == cid), {"missing craft": cid})

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]

def marks(host, fname):
    """host save_game (a direct SavedGame::save), then every `inBattlescape: true` line with its key path (r4l6 TASK 0 sav_flags)"""
    rep, path, out, keys = q(host, {"cmd": "save_game", "file": fname}), os.path.join(host.user_dir, "xcom1", fname), [], []
    if rep.get("ok") is not True or not os.path.exists(path):
        return {"reply": rep, "file": "missing", "flags": None}
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, s in enumerate((ln.rstrip("\r\n") for ln in f), 1):
            ind, body = len(s) - len(s.lstrip(" ")), s.strip()
            if not body or body.startswith("#"):
                continue
            if body.startswith("- "):
                ind, body = ind + 2, body[2:]
            while keys and keys[-1][0] >= ind:
                keys.pop()
            m = re.match(r"([A-Za-z_][A-Za-z0-9_]*):", body)
            keys += [(ind, m.group(1))] if m else []
            out += ["%d %s" % (n, "/".join(k for _, k in keys))] if "inBattlescape: true" in s else []
    return {"reply": rep, "flags": out}

def wait(desc, pred, timeout, interval=POLL):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))

def changes(polls):
    return [[t, st] for i, (t, st) in enumerate(polls) if i == 0 or st != polls[i - 1][1]]

class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.ctx = rid, cells, x, [], set(), time.time(), {"n_h": 0}
        self.cr0 = session._crash_log_snapshot()

    def cell(self, cid, kind, label, ok, ev):
        print("EVIDENCE %s: %s" % (cid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        print("EVIDENCE %s stop: %s" % (self.rid, why), flush=True)
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)

    def end(self, crash_cid, results, walls):
        """the CRASH cell (every case), ONE CAPTURE line when a cell failed, the row verdict"""
        if crash_cid:
            new = sorted(session._crash_log_snapshot() - self.cr0)
            self.cell(crash_cid, "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new, new)
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            live = [(gc.name, gc) for gc in (x.host, x.client, x.client2) if gc is not None and gc.proc is not None and gc.proc.poll() is None]
            cap = {"stacks": {n: stack(gc) for n, gc in live}, "battle_state": {n: bstate(gc) for n, gc in live}, "MARKS": self.ctx.get("MARKS")}
            if x.host is not None:
                hl = [ln.split("\t")[-1][:200] for ln in log(x.host) if "coop-handshake" in ln or "[coop]" in ln][-15:]
                cap.update({"host get_coop": coop(x.host), "host coop_dialog_info": dlg(x.host), "SKY": sky(x.host, x.cid),
                            "UNWIND": since(x.host, self.ctx["n_h"], UNWIND), "HL": hl})
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("EVIDENCE %s boot: %s\nFAIL %s boot: CAMP did not reach the landing prompt" % (self.rid, self.x.err, self.rid), flush=True)
        self.fails.append("boot")
        self.end(None, results, walls)

def landing_prompt(host):
    def ready():
        st = stack(host)
        if CLS in st:
            return True
        if st[-1:] == [COOP]:
            host.cmd({"cmd": "coop_dialog_back"})
        elif st[-1:] != [GEO]:
            host.cmd({"cmd": "dismiss_popup"})
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
    return ready

def force_to_site(x):
    return q(x.host, {"cmd": "craft_force", "craft_id": x.cid, "status": "STR_OUT", "lon": x.b0[0] + 0.34, "lat": x.b0[1] + 0.10,
                      "dest": "site:%s" % x.site, "fuel": 999999, "lowFuel": False})

def camp(x, key):
    """CAMP: the r4l6 TASK 0 t0_2.py head - the host squad of 3 on the Skyranger, the client's "Guest" transferred and seated, a terror
    site near base 0, the craft forced to it, the landing prompt (geo_set_speed idx 2)"""
    host, client, S = x.host, x.client, session
    S.new_campaign(host, client, port=key)
    hb = S._campaign_own_roster_base(host)
    x.cid, rh = S._campaign_skyranger(host)["id"], sorted(s["id"] for s in hb["soldiers"])
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
    x.b0 = (lambda b: (b["lon"], b["lat"]))(S._campaign_base0(host))
    x.site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                      "lon": x.b0[0] + 0.35, "lat": x.b0[1] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    host.wait_for("site on host", lambda: x.site in sky(host, None, sites=True) or None, timeout=30)
    assert force_to_site(x).get("ok"), "craft_force failed"
    host.wait_for("host landing prompt", landing_prompt(host), timeout=120, interval=0.5)

def boot(tag, key):
    x = SimpleNamespace(tag=tag, host=None, client=None, client2=None, err=None, cid=None, site=None, b0=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        camp(x, key)
    except Exception as e:
        x.err = short(e, 600)
    return x

def row_c1(x, results, walls):
    r = Row("C1", ["C1-%d" % i for i in range(1, 8)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        n_h = r.ctx["n_h"] = len(log(h))
        n_c, s0 = len(log(c)), sky(h, x.cid)
        if s0.get("destKind") != "site" or s0.get("destId") != x.site:
            raise Stop("baseline SKY destKind site, destId %s: %s" % (x.site, s0))
        lever(h, {"cmd": "corrupt_next_blob"})
        lever(h, {"cmd": "coop_mission_start"})
        t0, polls = time.time(), []
        wait("host battle_refuse received +1", lambda: since(h, n_h, REFUSE), 30.0)

        def back():
            st, ph = stack(h), bstate(h)["phase"]
            polls.append((round(time.time() - t0, 2), st))
            return st[-1:] in ([GEO], [CLS]) and ph == "Idle"
        wait("host top GeoscapeState or ConfirmLandingState and phase Idle", back, W)
        t1 = time.time()
        while time.time() - t1 < W:
            polls.append((round(time.time() - t0, 2), stack(h)))
            time.sleep(POLL)
        s1, r.ctx["MARKS"], hb, cb, hc, cc = sky(h, x.cid), marks(h, "w2h24_c1.sav"), bstate(h), bstate(c), coop(h), coop(c)
        ref, mis, act, unw = since(h, n_h, REFUSE), since(c, n_c, MISMATCH), since(c, n_c, CLIENT_ACTIVE), since(h, n_h, UNWIND)
        r.cell("C1-1", "GUARD", "refused: host refuse +1 with reason=corrupt; client sha MISMATCH +1; client CLIENT phase Active +0",
               len(ref) == 1 and "reason=corrupt" in ref[0] and len(mis) == 1 and not act, {"refuse": ref, "mismatch": mis, "active": act})
        r.cell("C1-2", "GUARD", "no battle: host phase Idle, inBattle false, battleId 0; client phase Idle; both onConnect 1, coopSession true",
               hb["phase"] == "Idle" and hb["inBattle"] is False and hb["battleId"] == 0 and cb["phase"] == "Idle"
               and all(v["onConnect"] == 1 and v["coopSession"] is True for v in (hc, cc)), {"host": [hb, hc], "client": [cb, cc]})
        r.cell("C1-3", "RED", 'UNWIND +1 reading "(refused) unwound - %s" (red today: 0 lines, T0-1)' % MARKED,
               len(unw) == 1 and ("(refused) unwound - " + MARKED) in unw[0], unw)
        hit = [t for t, st in polls if CLS in st]
        r.cell("C1-4", "RED", "no re-prompt: ConfirmLandingState on no host poll after the refusal (red today: up from 1.71 s, T0-1)",
               bool(polls) and not hit, {"polls": len(polls), "with CLS": len(hit), "first CLS s": hit[:1], "stacks": changes(polls)})
        r.cell("C1-5", "RED", 'craft turned home: SKY destKind not "site", and destKind "base" while status STR_OUT (red today: "site")',
               s1.get("destKind") not in (None, "site") and (s1.get("status") != "STR_OUT" or s1.get("destKind") == "base"), s1)
        r.cell("C1-6", "RED", "MARKS = 0 lines (red today: 2, bases/crafts + missionSites, T0-1)", r.ctx["MARKS"]["flags"] == [], r.ctx["MARKS"])
        ids = sky(h, None, sites=True)
        r.cell("C1-7", "GUARD", "the target stays: host geo_state.missionSites holds the site id %s" % x.site, x.site in ids, ids)
    except Exception as e:  # Stop, or a lever / kill() that raised: the row ends here
        r.stop(e)
    r.end("C1-8", results, walls)

def row_c0(x, results, walls):
    r = Row("C0", ["C0-1", "C0-2"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        if CLS not in stack(h):
            if force_to_site(x).get("ok") is not True:
                raise Stop("host craft_force back to the site failed")
            wait("host landing prompt", landing_prompt(h), 120.0, 0.5)
        n_h = r.ctx["n_h"] = len(log(h))
        n_c = len(log(c))
        lever(h, {"cmd": "coop_mission_start"})
        wait("both phase Active", lambda: bstate(h)["phase"] == "Active" and bstate(c)["phase"] == "Active", 20.0)
        hb, cb, act, unw = bstate(h), bstate(c), since(c, n_c, CLIENT_ACTIVE), since(h, n_h, UNWIND)
        r.cell("C0-1", "GUARD", "the start works: both phase Active, equal non-zero battleId, client CLIENT phase Active +1, UNWIND +0",
               hb["phase"] == cb["phase"] == "Active" and bool(hb["battleId"]) and hb["battleId"] == cb["battleId"] and len(act) == 1
               and not unw, {"host": hb, "client": cb, "active": act, "UNWIND": unw})
        c.kill()
        tk = time.time()
        wait("host peerAbsent true and dialog 62", lambda: bstate(h)["peerAbsent"] is True and dlg(h).get("code") == 62, 30.0)
        hb, s, unw, d = bstate(h), sky(h, x.cid), since(h, n_h, UNWIND), dlg(h)
        r.cell("C0-2", "GUARD", 'the SPEC 16 pause: host phase Active, peerAbsent true, inBattle true, dialog 62 within 30 s, UNWIND +0, '
               'SKY destKind "site"', hb["phase"] == "Active" and hb["peerAbsent"] is True and hb["inBattle"] is True
               and d.get("code") == 62 and not unw and s.get("destKind") == "site",
               {"host": hb, "dialog": d, "UNWIND": unw, "SKY": s, "s after kill": round(time.time() - tk, 2)})
    except Exception as e:  # Stop, or a lever / kill() that raised: the row ends here
        r.stop(e)
    r.end("C0-3", results, walls)

def rejoin(x, n_h, ev):
    """client2 rejoins (test_rejoin_flow.py :47-:70) -> True when every C2-5 check holds; ev collects the values"""
    h, on52 = x.host, {"since": None, "max s": 0.0}
    try:
        x.client2 = GameClient("client2", 3, make_user_dir(x.tag + "_client2"))
        x.client2.spawn(); x.client2.connect()
        ev["join_tcp"] = x.client2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY_B, "player": "ClientPlayer"})
    except Exception as e:
        ev["join"] = short(e)
        return False
    c2, t0 = x.client2, time.time()

    def sample():  # client2's longest unbroken stretch on CoopState 52 ("Loading...") across the two waits
        on52["since"] = (on52["since"] or time.time()) if dlg(c2).get("code") == 52 else None
        on52["max s"] = max(on52["max s"], round(time.time() - on52["since"], 1) if on52["since"] else 0.0)
    try:
        wait("host resumeAck", lambda: sample() or coop(h).get("resumeAck") is True, 120.0)
        ev["resumeAck s"] = round(time.time() - t0, 1)
        if session.has_state(h, "Profile"):
            ev["host profile_ok"] = q(h, {"cmd": "profile_ok"})
            time.sleep(0.5)
        ev["RESUME"] = session.press_back_when_shown(h, "host RESUME", codes=(60, 62))
        wait("client2 top GeoscapeState", lambda: sample() or stack(c2)[-1:] == [GEO], 120.0)
    except Exception as e:  # a timed-out wait (Stop / TimeoutError) or a machine gone: C2-5's own evidence
        ev["wait"] = short(e, 300)
    ev.update({"host resumeAck": coop(h).get("resumeAck"), "host stack": stack(h), "host dialog": dlg(h), "client2 stack": stack(c2),
               "client2 dialog": dlg(c2), "client2 longest on 52 s": on52["max s"], "rejoin guard": since(h, n_h, REJOIN_GUARD)})
    return (ev["host resumeAck"] is True and (ev.get("RESUME") or {}).get("ok") is True and ev["host stack"][-1:] == [GEO]
            and ev["client2 stack"][-1:] == [GEO] and not ev["rejoin guard"] and on52["max s"] <= 30.0)

def row_c2(x, results, walls):
    r = Row("C2", ["C2-%d" % i for i in range(1, 6)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        lever(c, {"cmd": "hold_battle_ready", "on": True}, key="armed")
        n_h = r.ctx["n_h"] = len(log(h))
        lever(h, {"cmd": "coop_mission_start"})
        wait("host phase Handshake and client held", lambda: bstate(h)["phase"] == "Handshake"
             and q(c, {"cmd": "hold_battle_ready"}).get("held") is True, 30.0)
        c.kill()
        tk, polls = time.time(), []
        first = dict(bstate(h), t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append((round(time.time() - tk, 2), stack(h)))
            time.sleep(POLL)
        hs, hb, d, s, r.ctx["MARKS"] = stack(h), bstate(h), dlg(h), sky(h, x.cid), marks(h, "w2h24_c2.sav")
        unw = since(h, n_h, UNWIND)
        why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
        path = {"first poll after the kill": first, "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first["phase"], "?"),
                "UNWIND reason": why}
        r.cell("C2-1", "RED", 'UNWIND +1 reading "(partner dropped)" or "(partner lost)" and "%s" (red today: 0 lines, T0-2)' % MARKED,
               len(unw) == 1 and bool(why) and MARKED in unw[0], {"UNWIND": unw, "path": path})
        r.cell("C2-2", "RED", "the host waits on the geoscape: stack ends [GeoscapeState, CoopState], dialog 62, no BriefingState / "
               "BattlescapeState, inBattle false, phase Idle, peerAbsent false (red today: 62 over BriefingState, inBattle true, T0-2)",
               hs[-2:] == [GEO, COOP] and d.get("code") == 62 and BRF not in hs and BS not in hs and hb["inBattle"] is False
               and hb["phase"] == "Idle" and hb["peerAbsent"] is False, {"stack": hs, "dialog": d, "battle": hb, "stacks": changes(polls)})
        r.cell("C2-3", "RED", 'SKY destKind "base" (red today: "site", T0-2)', s.get("destKind") == "base", s)
        r.cell("C2-4", "RED", "MARKS = 0 (red today: 2, T0-2)", r.ctx["MARKS"]["flags"] == [], r.ctx["MARKS"])
        ev = {}
        ok = rejoin(x, n_h, ev)
        r.cell("C2-5", "RED", "the rejoin works: resumeAck true, RESUME pressed, client2 and host top GeoscapeState, rejoin guard +0, "
               "client2 never > 30 s on CoopState 52 (red today: resumeAck never true in 120 s, T0-2)", ok, ev)
    except Exception as e:  # Stop, or a lever / kill() that raised: the row ends here
        r.stop(e)
    r.end("C2-6", results, walls)

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for tag, key, rows in (("w2h24_a", KEY_A, (row_c1, row_c0)), ("w2h24_b", KEY_B, (row_c2,))):
        tb = time.time()
        x = boot(tag, key)
        walls[tag + " CAMP"] = round(time.time() - tb, 1)
        for row in rows:
            row(x, results, walls)
        for gc in (x.client2, x.client, x.host):  # each boot shut down before the next (kill() already reaped a killed client)
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:
                print("FAIL %s shutdown (%s): %s" % (tag, gc.name, short(e, 300)), flush=True)
                failed.append("%s shutdown %s" % (tag, gc.name))
        walls[tag] = round(time.time() - tb, 1)
    rows = ("C1", "C0", "C2")
    failed += [rid for rid in rows if not results.get(rid)]
    print("\ntest_w2_failed_battle_start: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid in rows if results.get(rid)), len(rows), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
