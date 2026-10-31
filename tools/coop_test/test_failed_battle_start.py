"""test_failed_battle_start.py: a co-op CAMPAIGN battle start that is refused or that loses its partner, and a co-op
SKIRMISH start that loses its partner. When broken, a refused start leaves the host's craft "in battle" at its target,
the landing question pops up again and the .sav keeps inBattlescape for the craft and the site; a partner lost during
the ~1 s start leaves the host on "Waiting for <name>" over a briefing that can never start, and a rejoin never
reaches RESUME.
  Boot failed_start_refused (lobby key "48580", failed_start_refused_host / _client): refused_start, a refused start
  (host corrupt_next_blob), then clean_start, the negative control on the same world (a clean start, then a mid-battle
  kill: the battle pauses for the lost partner). Boot failed_start_drop (key "48581", failed_start_drop_host / _client /
  _client2): partner_drops, the partner lost during the start (client hold_battle_ready, then kill), then client2
  rejoins (test_rejoin_flow.py :47-:70).
  Cells: refused_start-1 GUARD refused, refused_start-2 GUARD no battle, refused_start-3 FIX UNWIND, refused_start-4
  FIX no re-prompt, refused_start-5 FIX craft turned home, refused_start-6 FIX MARKS 0, refused_start-7 GUARD the site
  stays, refused_start-no_crash GUARD CRASH 0; clean_start-works GUARD the start works, clean_start-pause GUARD the
  pause, clean_start-no_crash GUARD CRASH 0; partner_drops-1 FIX UNWIND, partner_drops-2 FIX the host waits on the
  geoscape, partner_drops-3 FIX craft home, partner_drops-4 FIX MARKS 0, partner_drops-5 FIX the rejoin works (when
  broken, the kill takes the -2 path and client2 gets the world, but the host never reads resumeAck in 120 s),
  partner_drops-no_crash GUARD CRASH 0.
  Boot failed_start_skirmish (key "48582", failed_start_skirmish_host / _client): skirmish_partner_drops, a co-op
  SKIRMISH start that loses its partner: test_handshake_teardown.drive_to_seated, the client's hold_battle_ready,
  newbattle_ok, host Handshake + client held, client.kill(), observe W. Cells: skirmish_partner_drops-unwind FIX
  UNWIND, skirmish_partner_drops-main_menu FIX the host lands on a bare main menu with the session ended (as after a
  refused skirmish start), skirmish_partner_drops-no_battle FIX no battle, skirmish_partner_drops-no_crash GUARD
  CRASH 0. EVIDENCE names the loss path and the stale-heal line delta (recorded, never asserted).
W = 15 s, POLL = 0.2 s. CAMP = camp(): session.bring_up_separate_guest_battle's steps with staged=False (the full
flight) up to the landing prompt, the geoscape clock left at its speed. SKY = the host's geo_state entry of the craft.
MARKS = host save_game, then the file's "inBattlescape: true" lines with their key paths. UNWIND = host log lines with
"failed battle start (" since the row's baseline. CRASH = session._crash_log_snapshot() delta, read at the row's end in
every case. A WAIT that times out (or a test command reply that is not ok) ends the row, its later cells "not
reached". EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; every row runs after a failure; ONE run;
exit 0 iff every cell passes, else 2. A build without the campaign unwind fails refused_start-3 .. refused_start-6 and
partner_drops-1 .. partner_drops-5 and passes clean_start; a build with it but without the skirmish unwind passes
those three rows and fails skirmish_partner_drops-unwind, -main_menu and -no_battle (its no_crash cell passes).
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
from test_handshake_teardown import drive_to_seated  # noqa: E402

W, POLL = 15.0, 0.2
KEY_REFUSED, KEY_DROP, KEY_SKIRMISH = "48580", "48581", "48582"
UNMARKED, STALE = "battle marks cleared=0, crafts sent home=0", "[exit] stale SavedGame reached the main menu"
REFUSE, MISMATCH = "battle_refuse received (battleId=", "battle blob sha MISMATCH (battleId="
CLIENT_ACTIVE, UNWIND = "CLIENT phase Active (battleId=", "failed battle start ("
REJOIN_GUARD, MARKED = "offerRejoinBattle() called while the battle is not ", "battle marks cleared=2, crafts sent home=1"
CLS, GEO, BRF, BS, COOP = "ConfirmLandingState", "GeoscapeState", "BriefingState", "BattlescapeState", "CoopState"

class Stop(Exception):
    """a WAIT timed out or a test command reply was not ok: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}

def hook_cmd(gc, obj, key="ok"):
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
    """host save_game (a direct SavedGame::save), then every `inBattlescape: true` line with its key path"""
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
                cap.update({"host get_coop": coop(x.host), "host coop_dialog_info": dlg(x.host), "SKY": sky(x.host, x.cid) if x.cid else None,
                            "UNWIND": since(x.host, self.ctx["n_h"], UNWIND), "HL": hl})
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("EVIDENCE %s boot: %s\nFAIL %s boot: the boot did not reach the row's start (CAMP: the landing "
              "prompt; the skirmish boot: BATTLE SETTINGS seated)" % (self.rid, self.x.err, self.rid), flush=True)
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
    """CAMP: the host squad of 3 on the Skyranger, the client's "Guest" transferred and seated, a terror site near base
    0, the craft forced to it, the landing prompt (geo_set_speed idx 2)"""
    host, client, S = x.host, x.client, session
    S.new_campaign(host, client, port=key)
    _base, x.cid, _squad, _guest = S.assemble_separate_guest_squad(host, client)
    for gc in (host, client):
        S.drain_host_coop_notice(gc)
    x.b0 = (lambda b: (b["lon"], b["lat"]))(S._campaign_base0(host))
    x.site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                      "lon": x.b0[0] + 0.35, "lat": x.b0[1] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    host.wait_for("site on host", lambda: x.site in sky(host, None, sites=True) or None, timeout=30)
    assert force_to_site(x).get("ok"), "craft_force failed"
    host.wait_for("host landing prompt", landing_prompt(host), timeout=120, interval=0.5)

def seated(x, key):
    """the skirmish boot: test_handshake_teardown.drive_to_seated, lobby -> BATTLE SETTINGS with seat 1 holding
    soldiers 0 and 1"""
    x.seated = drive_to_seated(x.host, x.client, key)

def boot(tag, key, up=camp):
    x = SimpleNamespace(tag=tag, host=None, client=None, client2=None, err=None, cid=None, site=None, b0=None)
    try:
        x.host, x.client = GameClient("host", 1, make_user_dir(tag + "_host")), GameClient("client", 2, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        up(x, key)
    except Exception as e:
        x.err = short(e, 600)
    return x

def row_refused_start(x, results, walls):
    r = Row("refused_start", ["refused_start-%d" % i for i in range(1, 8)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        n_h = r.ctx["n_h"] = len(log(h))
        n_c, s0 = len(log(c)), sky(h, x.cid)
        if s0.get("destKind") != "site" or s0.get("destId") != x.site:
            raise Stop("baseline SKY destKind site, destId %s: %s" % (x.site, s0))
        hook_cmd(h, {"cmd": "corrupt_next_blob"})
        hook_cmd(h, {"cmd": "coop_mission_start"})
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
        s1, r.ctx["MARKS"], hb, cb, hc, cc = (sky(h, x.cid), marks(h, "failed_start_refused_marks.sav"), bstate(h),
                                              bstate(c), coop(h), coop(c))
        ref, mis, act, unw = since(h, n_h, REFUSE), since(c, n_c, MISMATCH), since(c, n_c, CLIENT_ACTIVE), since(h, n_h, UNWIND)
        r.cell("refused_start-1", "GUARD",
               "refused: host refuse +1 with reason=corrupt; client sha MISMATCH +1; client CLIENT phase Active +0",
               len(ref) == 1 and "reason=corrupt" in ref[0] and len(mis) == 1 and not act, {"refuse": ref, "mismatch": mis, "active": act})
        r.cell("refused_start-2", "GUARD",
               "no battle: host phase Idle, inBattle false, battleId 0; client phase Idle; both onConnect 1, "
               "coopSession true",
               hb["phase"] == "Idle" and hb["inBattle"] is False and hb["battleId"] == 0 and cb["phase"] == "Idle"
               and all(v["onConnect"] == 1 and v["coopSession"] is True for v in (hc, cc)), {"host": [hb, hc], "client": [cb, cc]})
        r.cell("refused_start-3", "FIX", 'UNWIND +1 reading "(refused) unwound - %s" (when broken: 0 lines)' % MARKED,
               len(unw) == 1 and ("(refused) unwound - " + MARKED) in unw[0], unw)
        hit = [t for t, st in polls if CLS in st]
        r.cell("refused_start-4", "FIX",
               "no re-prompt: ConfirmLandingState on no host poll after the refusal (when broken: up from 1.71 s)",
               bool(polls) and not hit, {"polls": len(polls), "with CLS": len(hit), "first CLS s": hit[:1], "stacks": changes(polls)})
        r.cell("refused_start-5", "FIX",
               'craft turned home: SKY destKind not "site", and destKind "base" while status STR_OUT '
               '(when broken: "site")',
               s1.get("destKind") not in (None, "site") and (s1.get("status") != "STR_OUT" or s1.get("destKind") == "base"), s1)
        r.cell("refused_start-6", "FIX", "MARKS = 0 lines (when broken: 2, bases/crafts + missionSites)",
               r.ctx["MARKS"]["flags"] == [], r.ctx["MARKS"])
        ids = sky(h, None, sites=True)
        r.cell("refused_start-7", "GUARD",
               "the target stays: host geo_state.missionSites holds the site id %s" % x.site,
               x.site in ids, ids)
    except Exception as e:  # Stop, or a test command / kill() that raised: the row ends here
        r.stop(e)
    r.end("refused_start-no_crash", results, walls)

def row_clean_start(x, results, walls):
    r = Row("clean_start", ["clean_start-works", "clean_start-pause"], x)
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
        hook_cmd(h, {"cmd": "coop_mission_start"})
        wait("both phase Active", lambda: bstate(h)["phase"] == "Active" and bstate(c)["phase"] == "Active", 20.0)
        hb, cb, act, unw = bstate(h), bstate(c), since(c, n_c, CLIENT_ACTIVE), since(h, n_h, UNWIND)
        r.cell("clean_start-works", "GUARD",
               "the start works: both phase Active, equal non-zero battleId, client CLIENT phase Active +1, UNWIND +0",
               hb["phase"] == cb["phase"] == "Active" and bool(hb["battleId"]) and hb["battleId"] == cb["battleId"] and len(act) == 1
               and not unw, {"host": hb, "client": cb, "active": act, "UNWIND": unw})
        c.kill()
        tk = time.time()
        wait("host peerAbsent true and dialog 62", lambda: bstate(h)["peerAbsent"] is True and dlg(h).get("code") == 62, 30.0)
        hb, s, unw, d = bstate(h), sky(h, x.cid), since(h, n_h, UNWIND), dlg(h)
        r.cell("clean_start-pause", "GUARD", 'the pause for the lost partner: host phase Active, peerAbsent true, '
               'inBattle true, dialog 62 within 30 s, UNWIND +0, SKY destKind "site"',
               hb["phase"] == "Active" and hb["peerAbsent"] is True and hb["inBattle"] is True
               and d.get("code") == 62 and not unw and s.get("destKind") == "site",
               {"host": hb, "dialog": d, "UNWIND": unw, "SKY": s, "s after kill": round(time.time() - tk, 2)})
    except Exception as e:  # Stop, or a test command / kill() that raised: the row ends here
        r.stop(e)
    r.end("clean_start-no_crash", results, walls)

def rejoin(x, n_h, ev):
    """client2 rejoins (test_rejoin_flow.py :47-:70) -> True when every partner_drops-5 check holds; ev collects the
    values"""
    h, on52 = x.host, {"since": None, "max s": 0.0}
    try:
        x.client2 = GameClient("client2", 3, make_user_dir(x.tag + "_client2"))
        x.client2.spawn(); x.client2.connect()
        ev["join_tcp"] = x.client2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY_DROP,
                                        "player": "ClientPlayer"})
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
    except Exception as e:  # a timed-out wait (Stop / TimeoutError) or a machine gone: partner_drops-5's own evidence
        ev["wait"] = short(e, 300)
    ev.update({"host resumeAck": coop(h).get("resumeAck"), "host stack": stack(h), "host dialog": dlg(h), "client2 stack": stack(c2),
               "client2 dialog": dlg(c2), "client2 longest on 52 s": on52["max s"], "rejoin guard": since(h, n_h, REJOIN_GUARD)})
    return (ev["host resumeAck"] is True and (ev.get("RESUME") or {}).get("ok") is True and ev["host stack"][-1:] == [GEO]
            and ev["client2 stack"][-1:] == [GEO] and not ev["rejoin guard"] and on52["max s"] <= 30.0)

def row_partner_drops(x, results, walls):
    r = Row("partner_drops", ["partner_drops-%d" % i for i in range(1, 6)], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        hook_cmd(c, {"cmd": "hold_battle_ready", "on": True}, key="armed")
        n_h = r.ctx["n_h"] = len(log(h))
        hook_cmd(h, {"cmd": "coop_mission_start"})
        wait("host phase Handshake and client held", lambda: bstate(h)["phase"] == "Handshake"
             and q(c, {"cmd": "hold_battle_ready"}).get("held") is True, 30.0)
        c.kill()
        tk, polls = time.time(), []
        first = dict(bstate(h), t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append((round(time.time() - tk, 2), stack(h)))
            time.sleep(POLL)
        hs, hb, d, s, r.ctx["MARKS"] = (stack(h), bstate(h), dlg(h), sky(h, x.cid),
                                        marks(h, "failed_start_drop_marks.sav"))
        unw = since(h, n_h, UNWIND)
        why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
        path = {"first poll after the kill": first, "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first["phase"], "?"),
                "UNWIND reason": why}
        r.cell("partner_drops-1", "FIX",
               'UNWIND +1 reading "(partner dropped)" or "(partner lost)" and "%s" (when broken: 0 lines)' % MARKED,
               len(unw) == 1 and bool(why) and MARKED in unw[0], {"UNWIND": unw, "path": path})
        r.cell("partner_drops-2", "FIX", "the host waits on the geoscape: stack ends [GeoscapeState, CoopState], "
               "dialog 62, no BriefingState / BattlescapeState, inBattle false, phase Idle, peerAbsent false (when "
               "broken: 62 over BriefingState, inBattle true)",
               hs[-2:] == [GEO, COOP] and d.get("code") == 62 and BRF not in hs and BS not in hs and hb["inBattle"] is False
               and hb["phase"] == "Idle" and hb["peerAbsent"] is False, {"stack": hs, "dialog": d, "battle": hb, "stacks": changes(polls)})
        r.cell("partner_drops-3", "FIX", 'SKY destKind "base" (when broken: "site")', s.get("destKind") == "base", s)
        r.cell("partner_drops-4", "FIX", "MARKS = 0 (when broken: 2)", r.ctx["MARKS"]["flags"] == [], r.ctx["MARKS"])
        ev = {}
        ok = rejoin(x, n_h, ev)
        r.cell("partner_drops-5", "FIX", "the rejoin works: resumeAck true, RESUME pressed, client2 and host top "
               "GeoscapeState, rejoin guard +0, client2 never > 30 s on CoopState 52 (when broken: resumeAck never "
               "true in 120 s)", ok, ev)
    except Exception as e:  # Stop, or a test command / kill() that raised: the row ends here
        r.stop(e)
    r.end("partner_drops-no_crash", results, walls)

def row_skirmish_partner_drops(x, results, walls):
    r = Row("skirmish_partner_drops", ["skirmish_partner_drops-unwind", "skirmish_partner_drops-main_menu",
                                       "skirmish_partner_drops-no_battle"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c = x.host, x.client
    try:
        hook_cmd(c, {"cmd": "hold_battle_ready", "on": True}, key="armed")
        n_h = r.ctx["n_h"] = len(log(h))
        hook_cmd(h, {"cmd": "newbattle_ok"})
        wait("host phase Handshake and client held", lambda: bstate(h)["phase"] == "Handshake"
             and q(c, {"cmd": "hold_battle_ready"}).get("held") is True, 30.0)
        c.kill()
        tk, polls = time.time(), []
        first = dict(bstate(h), t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append((round(time.time() - tk, 2), stack(h)))
            time.sleep(POLL)
        hs, hb, d, hc, has_save = stack(h), bstate(h), dlg(h), coop(h), q(h, {"cmd": "world_state"}).get("has_save")
        unw, stale = since(h, n_h, UNWIND), since(h, n_h, STALE)
        why = re.findall(r"\((partner dropped|partner lost)\)", " ".join(unw))
        path = {"first poll after the kill": first, "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first["phase"], "?"),
                "UNWIND reason": why, "stale-heal lines (recorded, never asserted)": stale}
        r.cell("skirmish_partner_drops-unwind", "FIX",
               'UNWIND +1 reading "(partner dropped)" or "(partner lost)" and "%s" (when broken: 0 lines)' % UNMARKED,
               len(unw) == 1 and bool(why) and UNMARKED in unw[0], {"UNWIND": unw, "path": path})
        lobby = [t for t, st in polls if "LobbyMenu" in st]
        r.cell("skirmish_partner_drops-main_menu", "FIX", "the host lands on a bare main menu, the session ended (as "
               "after a refused skirmish start): at W stack ['MainMenuState'], has_save false, coopSession false, "
               "onConnect -1, no coop dialog, LobbyMenu on no poll (when broken: [BriefingState, CoopState] 62)",
               hs == ["MainMenuState"] and has_save is False and hc["coopSession"] is False and hc["onConnect"] == -1
               and d.get("present") is False and bool(polls) and not lobby,
               {"stack": hs, "has_save": has_save, "get_coop": hc, "dialog": d, "LobbyMenu polls s": lobby[:3], "stacks": changes(polls)})
        r.cell("skirmish_partner_drops-no_battle", "FIX",
               "no battle: host phase Idle, inBattle false, battleId 0 (when broken: inBattle true)",
               hb["phase"] == "Idle" and hb["inBattle"] is False and hb["battleId"] == 0, hb)
    except Exception as e:  # Stop, or a test command / kill() that raised: the row ends here
        r.stop(e)
    r.end("skirmish_partner_drops-no_crash", results, walls)

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for tag, key, rows, up in (("failed_start_refused", KEY_REFUSED, (row_refused_start, row_clean_start), camp),
                               ("failed_start_drop", KEY_DROP, (row_partner_drops,), camp),
                               ("failed_start_skirmish", KEY_SKIRMISH, (row_skirmish_partner_drops,), seated)):
        tb = time.time()
        x = boot(tag, key, up)
        walls[tag + (" CAMP" if up is camp else " seated")] = round(time.time() - tb, 1)
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
    rows = ("refused_start", "clean_start", "partner_drops", "skirmish_partner_drops")
    failed += [rid for rid in rows if not results.get(rid)]
    print("\ntest_failed_battle_start: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid in rows if results.get(rid)), len(rows), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
