"""test_entry_waits_for_naming.py: a co-op battle started while the partner names a new base waits until the partner
has finished; then the partner joins as usual.
In a SEPARATE campaign the host's YES on its landing prompt sends the battle offer at once. If the partner's machine
accepted it while on the naming window of a new base it has already paid for, the entry would close the window, its
own-world snapshot would refuse the unnamed base (a CoopState 995 "Save failed" dialog over its briefing) and the
return after the battle would load the world from before the build: the new base would be gone and its cost back.
ONE boot pair (key KEY, dirs entry_waits_for_naming_host / _client): spawn + connect both; session.new_campaign SEPARATE
tcp, host base at HOST_POS; geo.slow_clock; geo.drain_popups; the window mapping per machine from INTERCEPT + its
CANCEL (real clicks); then the guest steps of session.bring_up_separate_guest_battle (copied, never called: its tail
drives the partner's screens): the host seats its first 3 soldiers on its Skyranger, the client's "Guest Zzz" is
transferred, visited and seated there. "Entered" (partner) = its top is BriefingState with BattlescapeState directly
under it. A "log window" = the partner's openxcom.log lines between M_YES (read right before the host's YES) and M_END
(read 3 s after the first poll that saw it entered; no entry seen: at the row's last polled step, before the battle
drive).
  Row naming_window: landing (site SITE_NAMING, the Skyranger forced to it, the host's ConfirmLandingState); the
  partner: BASES, BUILD NEW BASE, ONE real globe click at its pick_point(), OK -> BaseNameState with one own base ""
  (paid); the host's real YES (click_widget); both polled every POLL s.
    naming_window-hold       (FIX)   no poll saw the partner entered and at T_YES + WAIT_S its top is BaseNameState.
    naming_window-hostwait   (FIX)   at T_YES + WAIT_S the host's event_state.phase is Handshake and its stack holds
                                     BriefingState.
                             (step)  host close_briefing -> pre-battle InventoryState; battle_inventory ok; LINE_S s.
    naming_window-hostline   (GUARD) the host's inventory_view line is WAIT_TEXT and visible.
                             (step)  if the partner's top is BaseNameState: NAME by real key presses, OK; else
                                     "pulled in" (the next 3 cells not reached).
    naming_window-named      (FIX)   the partner's top is PlaceLiftState within 5 s of the OK.
    naming_window-liftwait   (FIX)   at OK + LIFT_HOLD_S the partner's top is PlaceLiftState, not entered, the host's
                                     phase Handshake.
                             (step)  the LIFT_TILE real click.
    naming_window-enter      (FIX)   within ENTER_S of the lift click the partner is entered.
    naming_window-no_dialog  (FIX)   the partner's log window holds no "push class OpenXcom::CoopState".
                             (step)  session.drive_both_to_tactical; session.coop_abort_battle; the partner back on
                                     its own geoscape.
    naming_window-base       (FIX)   the partner's own bases hold one named NAME with at least 1 facility.
    naming_window-funds      (FIX)   the partner's funds equal PAID (the funds after the build).
  Row unpaid_placement (a placement not yet paid for does not hold the battle): landing (site SITE_UNPAID); the
  partner to ConfirmNewBaseState at its pick_point() (no OK); the host's real YES; polled every POLL s.
    unpaid_placement-enter      (GUARD) within ENTER_S of the YES the partner is entered, no BuildNewBaseState /
                                        ConfirmNewBaseState on its stack.
    unpaid_placement-no_dialog  (GUARD) the partner's log window holds no "push class OpenXcom::CoopState".
  Row END: no_crash (GUARD) no crash file new in harness.CRASH_DIR since the bring-up; both processes alive until
  their shutdown (the unpaid_placement row's battle is left at its briefing).
A build in which the battle does not wait fails the 8 FIX cells and passes naming_window-hostline,
unpaid_placement-enter, unpaid_placement-no_dialog and no_crash; with the wait all 12 cells pass.
Every subject press is a real click_widget / inject_input; no dismiss_popup or coop_dialog_back reaches the partner
while it names. One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; a precondition miss
ends its row (later cells "not reached"); a boot miss fails every row "boot" with ONE CAPTURE line.
ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_entry_waits_for_naming.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49287"                               # lobby key
HOST_POS = (0.90, -0.60)                    # rad: both bases on land
# rad from the host base: session.bring_up_separate_guest_battle's site offset, mirrored for the unpaid_placement row
SITE_NAMING, SITE_UNPAID = (0.35, 0.10), (0.35, -0.10)
NAME = "hnewk"                              # lowercase: inject_input key = unicode sym
LIFT_TILE = (2, 2)                          # BaseView tile: base (80, 88) in the 192 x 192 view at (0, 8), 32 px tiles
MIN_SEP = 0.25                              # rad from every base and marker (two placements on one boot)
WAIT_S, LIFT_HOLD_S, ENTER_S, LINE_S, POLL, LANDING_S = 5.0, 2.0, 10.0, 1.5, 0.25, 120
WAIT_TEXT = "Waiting for ClientPlayer to finish equipping"  # STR_COOP_WAITING_FOR_EQUIP, {0} = the partner
PUSH_COOP_STATE = "push class OpenXcom::CoopState"
ROWS = (("naming_window", ("naming_window-hold", "naming_window-hostwait", "naming_window-hostline",
                           "naming_window-named", "naming_window-liftwait", "naming_window-enter",
                           "naming_window-no_dialog", "naming_window-base", "naming_window-funds")),
        ("unpaid_placement", ("unpaid_placement-enter", "unpaid_placement-no_dialog")), ("END", ("no_crash",)))
FIX = ("naming_window-hold", "naming_window-hostwait", "naming_window-named", "naming_window-liftwait",
       "naming_window-enter", "naming_window-no_dialog", "naming_window-base", "naming_window-funds")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]


class Stop(Exception):  # a precondition missed: the row ends here
    pass


# ----- probes and real input (copied from test_save_during_naming.py, never imported) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 2)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}
def stk(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.split("::")[-1] for s in r["states"]] if "states" in r else ["probe failed: %s" % r.get("error")]
def top(gc): return (stk(gc) or [None])[-1]
def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backText", "error") if k in r}
def phase(gc): return q(gc, {"cmd": "event_state"}).get("phase")
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon", 0), 5),
           round(b.get("lat", 0), 5), len(b.get("facilities") or [])] for b in g.get("bases", [])]
    return {"bases": bl, "funds": g.get("funds"), "stack": stk(gc), "error": g.get("error")}
def own(c): return [[b[0], b[1], b[6]] for b in c["bases"] if not b[2] and not b[3]]
def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def cw(gc, match, settle=1.0):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"match": match, "ok": r.get("ok"), "err": r.get("error"), "base": [r.get("baseX"), r.get("baseY")],
            "win": [r.get("winX"), r.get("winY")], "after": stk(gc)}
def affine(r1, r2):
    """window = s * base + o per axis, from two click_widget replies (base / window centres)"""
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})
def win(sc, bx, by): return int(round(sc[0] * bx + sc[1])), int(round(sc[2] * by + sc[3]))
def click_px(gc, bx, by, sc, until_not, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    """real clicks at base pixel (bx, by) + offsets through the window mapping until the top leaves `until_not`"""
    tries = []
    for dx, dy in offsets:
        wx, wy = win(sc, bx + dx, by + dy)
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        t4 = time.time()
        while time.time() - t4 < 1.0 and top(gc) == until_not:
            time.sleep(0.05)
        tries.append([bx + dx, by + dy, top(gc)])
        if tries[-1][2] != until_not:
            break
    return tries
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def pick_point(gc, avoid):
    """the partner's new-base point: rings 0.20-0.50 rad step 0.05 (then 0.55, 0.60) x 16 around the partner's
    first own base, >= MIN_SEP from every base and marker; the point and its 8 neighbours at 0.02 rad on land;
    inside the globe surface (10 px margin, 30 px top)."""
    c = avoid[0]
    for r in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
        for k in range(16):
            p = (c[0] + r * math.cos(2 * math.pi * k / 16), c[1] + r * math.sin(2 * math.pi * k / 16))
            if any(dist(p, b) < MIN_SEP for b in avoid):
                continue
            pr = globe(gc, lon=p[0], lat=p[1])
            if not pr.get("land"):
                continue
            nb = [globe(gc, lon=p[0] + dx, lat=p[1] + dy).get("land") for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02)]
            if all(nb) and 10 < pr["x"] < pr["globeW"] - 10 and 30 < pr["y"] < pr["globeH"] - 10:
                return {"lon": round(p[0], 5), "lat": round(p[1], 5), "x": pr["x"], "y": pr["y"], "r": r, "k": k}
    return None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def entered(s): return s[-2:] == ["BattlescapeState", "BriefingState"]
def wait_until(pred, timeout, step=0.1):
    t = time.time()
    while time.time() - t < timeout:
        if pred():
            return round(time.time() - t, 2)
        time.sleep(step)
    return None
def coopwin(lines): return [ln.split("\t")[-1][:160] for ln in lines
                            if "[coop-handshake] battle_" in ln or "held battle_offer" in ln or PUSH_COOP_STATE in ln]


# ----- boot, rows -----
class Boot:
    def __init__(self):
        self.aff, self.cid = {}, None
        self.host = GameClient("host", None, make_user_dir("entry_waits_for_naming_host"))
        self.client = GameClient("client", None, make_user_dir("entry_waits_for_naming_client"))
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu()}
        self.mark, self.m_end, self.t_ent, self.t_yes = {}, None, None, None
    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok:
            raise Stop(what)
    def poll(self, t0, secs, trace, stop=None):
        """poll both every POLL s until t0 + secs or stop(cs, hs); trace = changes of [partner tail, host tail, host phase]"""
        while time.time() - t0 < secs:
            time.sleep(max(0.0, t0 + (int((time.time() - t0) / POLL) + 1) * POLL - time.time()))
            cs, hs = stk(self.b.client), stk(self.b.host)
            e = [cs[-3:], hs[-2:], phase(self.b.host)]
            if entered(cs) and self.t_ent is None:
                self.t_ent = time.time()
            if not trace or trace[-1][1:] != e:
                trace.append([round(time.time() - t0, 2)] + e)
            if stop and stop(cs, hs):
                return
    def read_mend(self):
        """M_END: 3 s after the first poll that saw the partner entered; with no entry seen, now (the row's last polled step)"""
        if self.m_end is None:
            if self.t_ent is not None:
                time.sleep(max(0.0, self.t_ent + 3.0 - time.time()))
            self.m_end = len(logl(self.b.client))
        return logl(self.b.client)[self.mark["client"]:self.m_end]
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in dict(ROWS)[self.rid]:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "FIX" if cid in FIX else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def capture(b):
    """every live machine's probes and log tail (the setup failure dump)"""
    out = {}
    for gc in (b.host, b.client):
        if not alive(gc):
            out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None}
            continue
        w, e = q(gc, {"cmd": "list_widgets"}), q(gc, {"cmd": "event_state"})
        out[gc.name] = {"stack": stk(gc), "dialog": dlg(gc), "geo_state": census(gc), "event": {k: e.get(k) for k in ("phase", "battleId", "localSeat")},
                        "widgets": [w.get("state")] + [[v.get("text"), v.get("visible")] for v in w.get("widgets", []) if v.get("text")][:14],
                        "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-15:]]}
    return out
def bring_up(b):
    h, c, S = b.host, b.client, session
    for gc in (h, c):
        gc.spawn()
        gc.connect(timeout=240)
    S.HOST_LON, S.HOST_LAT = HOST_POS
    S.new_campaign(h, c, port=KEY)
    geo.slow_clock(h, c)
    time.sleep(2.0)
    ev = {"drain": [str(geo.drain_popups(gc))[:120] for gc in (h, c)]}
    for gc in (h, c):
        b.aff[gc.name] = affine(cw(gc, "INTERCEPT", 0.6), cw(gc, "CANCEL", 0.6))
    hc, cc = census(h), census(c)
    ev.update({"aff": b.aff, "host": own(hc), "client": own(cc)})
    if not (hc["stack"] == ["GeoscapeState"] and cc["stack"] == ["GeoscapeState"] and len(own(hc)) == 1 and len(own(cc)) == 1):
        return False, ev
    # the guest (session.bring_up_separate_guest_battle's steps, copied)
    hb = S._campaign_own_roster_base(h)
    b.cid = S._campaign_skyranger(h)["id"]
    rh = sorted(s["id"] for s in hb["soldiers"])
    for sid in rh:
        q(h, {"cmd": "craft_assign", "craft_id": b.cid, "soldier_id": sid, "on": False})
    seats = [q(h, {"cmd": "craft_assign", "craft_id": b.cid, "soldier_id": sid, "on": True}).get("seated") for sid in rh[:3]]
    spare = next(s for s in S._campaign_own_roster_base(c)["soldiers"] if not s.get("craft"))["name"]
    rep = [q(c, {"cmd": "rename_soldier", "name": spare, "newName": "Guest Zzz"}),
           q(c, {"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": hb["name"]}), q(c, {"cmd": "visit_coop_base", "base": hb["name"]})]
    c.wait_for("inside", lambda: c.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    br = c.wait_for("guest", lambda: (lambda r: r if any("Guest" in s["name"] for s in r["soldiers"]) else None)(
        c.ok({"cmd": "base_report", "coop": True})), timeout=40)
    gid = next(s for s in br["soldiers"] if "Guest" in s["name"])["id"]
    pc = next(cr for cr in br["crafts"] if "SKYRANGER" in cr["type"])["id"]
    rep += [q(c, {"cmd": "craft_assign", "soldier_id": gid, "craft_id": pc, "coop": True, "on": True}), q(c, {"cmd": "open_soldiers", "base": hb["name"]})]
    c.wait_for("soldiers", lambda: S.has_state(c, "SoldiersState") or None, timeout=30)
    rep += [q(c, {"cmd": "soldiers_ok"}), q(c, {"cmd": "leave_base"})]
    S.wait_back_on_geoscape(c, "client back")
    ev.update({"hostSquad": rh[:3], "seated": seats, "guest": gid, "replies": [bool(r.get("ok")) for r in rep],
               "transferred": rep[1].get("transferred"), "crashFiles": len(crashes() - b.c0)})
    return all(seats) and all(ev["replies"]) and bool(rep[1].get("transferred")), ev
def landing(b, r, off):
    """session.drain_host_coop_notice; the site at the host base + off; the Skyranger forced 0.01 rad short of it;
    then the landing-prompt waiter of session.bring_up_separate_guest_battle"""
    h, c, S = b.host, b.client, session
    S.drain_host_coop_notice(h)
    b0 = S._campaign_base0(h)
    site = q(h, {"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + off[0],
                 "lat": b0["lat"] + off[1], "race": "STR_SECTOID", "hours": 240})
    sid = site.get("site_id")
    r.need(sid is not None and wait_until(lambda: any(s["id"] == sid for s in q(h, {"cmd": "geo_state"}).get("missionSites", [])), 30, 0.25)
           is not None, "site %s not in missionSites (%s)" % (sid, site.get("error")))
    q(h, {"cmd": "craft_force", "craft_id": b.cid, "status": "STR_OUT", "lon": b0["lon"] + off[0] - 0.01, "lat": b0["lat"] + off[1],
          "dest": "site:%s" % sid, "fuel": 999999, "lowFuel": False})

    def prompt():
        if S.has_state(h, "ConfirmLandingState"):
            return True
        t = S.states(h)[-1]
        if "CoopState" in t:
            h.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in t:
            h.cmd({"cmd": "dismiss_popup"})
        h.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    try:
        h.wait_for("landing prompt", prompt, timeout=LANDING_S, interval=0.5)
    except TimeoutError:
        pass
    geo.slow_clock(h, c)
    r.ev["site"] = sid
    r.need(top(h) == "ConfirmLandingState" and top(c) == "GeoscapeState", "landing: host %s, client %s" % (stk(h)[-2:], stk(c)[-2:]))
def to_confirm(b, r):
    """the partner: BASES, BUILD NEW BASE, ONE real globe click at the pick -> ConfirmNewBaseState"""
    c = b.client
    cw(c, "BASES")
    cw(c, "NEW BASE")
    r.need(top(c) == "BuildNewBaseState", "client top %s after BUILD NEW BASE" % top(c))
    cc = census(c)
    pick = r.ev["pick"] = pick_point(c, [(x[4], x[5]) for x in cc["bases"] if not x[2] and not x[3]] + [(x[4], x[5]) for x in cc["bases"] if x[2] or x[3]])
    r.need(pick, "no land point for the pick")
    r.ev["globeClick"] = click_px(c, pick["x"], pick["y"], b.aff["client"], "BuildNewBaseState")
    r.need(top(c) == "ConfirmNewBaseState", "client top %s after the globe click" % top(c))
def yes(b, r, trace, secs, stop=None):
    """the host's real YES on ConfirmLandingState (click_widget YES) at T_YES after M_YES; both polled every POLL s for secs (or stop)"""
    r.mark = {gc.name: len(logl(gc)) for gc in (b.host, b.client)}
    cr = q(b.host, {"cmd": "click_widget", "match": "YES"})
    r.t_yes = time.time()
    hb = {}

    def st(cs, hs):
        if "BriefingState" in hs and "t" not in hb:
            hb["t"] = round(time.time() - r.t_yes, 2)
        return bool(stop and stop(cs, hs) and "t" in hb)
    r.poll(r.t_yes, secs, trace, st)
    r.ev["yes"] = {"reply": [cr.get("ok"), cr.get("text"), cr.get("error")], "hostBriefing_s": hb.get("t")}
    r.need(hb.get("t") is not None and hb["t"] <= 5.0, "host top BriefingState not within 5 s of YES (%s)" % stk(b.host)[-2:])
def run_naming_window(b, r):
    h, c, ev = b.host, b.client, r.ev
    landing(b, r, SITE_NAMING)
    ev["PRE_BUILD"] = census(c)["funds"]
    to_confirm(b, r)
    cw(c, "OK")
    cc = census(c)
    new = [x for x in own(cc) if x[1] == ""]
    r.need(top(c) == "BaseNameState" and len(new) == 1, "client on BaseNameState with one own base \"\" (%s, %s)" % (top(c), own(cc)))
    ev["newBase"], ev["PAID"] = new[0][0], cc["funds"]
    trace = ev["hold"] = []
    yes(b, r, trace, WAIT_S)
    cs, hs, hp = stk(c), stk(h), phase(h)
    r.cell("naming_window-hold", r.t_ent is None and cs[-1:] == ["BaseNameState"], "partner stack at +WAIT_S %s, "
           "entered %s s after YES (want BaseNameState on top, "
           "never entered)" % (cs[-4:], round(r.t_ent - r.t_yes, 2) if r.t_ent else None))
    r.cell("naming_window-hostwait", hp == "Handshake" and "BriefingState" in hs, "host phase %s, stack %s at +WAIT_S "
           "(want Handshake with BriefingState)" % (hp, hs[-3:]))
    if r.t_ent is not None:
        r.read_mend()  # M_END is due 3 s after the entry, before the host's steps
    q(h, {"cmd": "close_briefing"})
    ev["hostInv_s"] = wait_until(lambda: top(h) == "InventoryState" and q(h, {"cmd": "inventory_view"}).get("preBattle") is True, 10.0, 0.2)
    r.need(ev["hostInv_s"] is not None, "host top %s, not the pre-battle InventoryState within 10 s of close_briefing" % stk(h)[-2:])
    bi = q(h, {"cmd": "battle_inventory", "action": "ok"})
    r.need(bi.get("ok"), "host battle_inventory ok: %s" % bi)
    time.sleep(LINE_S)
    v = q(h, {"cmd": "inventory_view"})
    ev["hostLine"] = [v.get("lineText"), v.get("lineVisible"), v.get("okPressed"), phase(h)]
    r.cell("naming_window-hostline", v.get("lineText") == WAIT_TEXT and v.get("lineVisible") is True,
           "host line +%s s after its ready %r visible=%s (want %r visible)" % (LINE_S, v.get("lineText"), v.get("lineVisible"), WAIT_TEXT))
    cs = stk(c)
    if cs[-1:] == ["BaseNameState"]:
        for ch in NAME:
            key(c, ord(ch))
            time.sleep(0.08)
        time.sleep(0.4)
        q(c, {"cmd": "click_widget", "match": "OK"})
        t_ok = time.time()
        ev["tNamed"] = wait_until(lambda: top(c) == "PlaceLiftState", 5.0)
        r.cell("naming_window-named", ev["tNamed"] is not None, "partner top PlaceLiftState %s s after the OK "
               "(want <= 5); now %s" % (ev["tNamed"], stk(c)[-2:]))
        tr2 = ev["liftHold"] = []
        r.poll(t_ok, LIFT_HOLD_S, tr2, lambda cs_, hs_: entered(cs_))
        cs2, hp2 = stk(c), phase(h)
        r.cell("naming_window-liftwait", cs2[-1:] == ["PlaceLiftState"] and r.t_ent is None and hp2 == "Handshake",
               "at +LIFT_HOLD_S partner %s, entered %s, host phase %s (want PlaceLiftState, not entered, Handshake)" % (cs2[-2:], r.t_ent is not None, hp2))
        if cs2[-1:] == ["PlaceLiftState"]:
            q(c, {"cmd": "inject_input", "kind": "click", "x": win(b.aff["client"], LIFT_TILE[0] * 32 + 16, 8 + LIFT_TILE[1] * 32 + 16)[0],
                  "y": win(b.aff["client"], LIFT_TILE[0] * 32 + 16, 8 + LIFT_TILE[1] * 32 + 16)[1]})
            t_lift = time.time()
            tr3 = ev["enter"] = []
            r.poll(t_lift, ENTER_S, tr3, lambda cs_, hs_: entered(cs_))
            ev["tEnter"] = round(r.t_ent - t_lift, 2) if r.t_ent else None
            r.cell("naming_window-enter", r.t_ent is not None and r.t_ent >= t_lift, "partner entered %s s after the "
                   "lift click (want <= %s); now %s"
                   % (ev["tEnter"], ENTER_S, stk(c)[-3:]))
        else:
            r.cell("naming_window-enter", False, "not reached: partner top %s, not PlaceLiftState" % cs2[-2:])
    else:
        ev["pulledIn"] = cs[-3:]
        for cid in ("naming_window-named", "naming_window-liftwait", "naming_window-enter"):
            r.cell(cid, False, "not reached: the partner was pulled in (stack %s), no naming window to type in" % cs[-3:])
    win_c = r.read_mend()
    pushes = [ln.split("\t")[-1] for ln in win_c if PUSH_COOP_STATE in ln]
    ev["logC"] = coopwin(win_c)
    r.cell("naming_window-no_dialog", not pushes, "partner log M_YES -> M_END: %d CoopState push(es) %s (want 0)"
           % (len(pushes), pushes[:2]))
    ok = session.drive_both_to_tactical(h, c)
    r.need(ok, "drive_both_to_tactical False (host %s, client %s)" % (stk(h)[-2:], stk(c)[-3:]))
    try:
        session.coop_abort_battle(h, c)
        session.wait_back_on_geoscape(c, "partner back after the battle")
    except Exception as e:  # noqa: BLE001
        raise Stop("abort / return: %s" % str(e)[:300])
    time.sleep(1.0)
    cc = census(c)
    ev["afterReturn"] = [own(cc), cc["funds"], cc["stack"]]
    r.need(cc["stack"][-1:] == ["GeoscapeState"], "partner top %s after the return" % cc["stack"][-2:])
    named = [x for x in own(cc) if x[1] == NAME]
    r.cell("naming_window-base", len(named) == 1 and named[0][2] >= 1, "partner own bases [id, name, facilities] %s "
           "(want one %r with >= 1 facility)" % (own(cc), NAME))
    r.cell("naming_window-funds", cc["funds"] == ev["PAID"], "partner funds %s (want PAID %s; PRE_BUILD %s)"
           % (cc["funds"], ev["PAID"], ev["PRE_BUILD"]))
def run_unpaid_placement(b, r):
    c, ev = b.client, r.ev
    landing(b, r, SITE_UNPAID)
    to_confirm(b, r)
    ev["ownCount"] = len(own(census(c)))
    trace = ev["trace"] = []
    yes(b, r, trace, ENTER_S, lambda cs_, hs_: entered(cs_))
    cs = stk(c)
    ev["tEnter"] = round(r.t_ent - r.t_yes, 2) if r.t_ent else None
    r.cell("unpaid_placement-enter", r.t_ent is not None and "BuildNewBaseState" not in cs
           and "ConfirmNewBaseState" not in cs,
           "partner entered %s s after YES (want <= %s); stack %s (want no BuildNewBaseState / ConfirmNewBaseState)" % (ev["tEnter"], ENTER_S, cs))
    win_c = r.read_mend()
    pushes = [ln.split("\t")[-1] for ln in win_c if PUSH_COOP_STATE in ln]
    ev["logC"] = coopwin(win_c)
    r.cell("unpaid_placement-no_dialog", not pushes, "partner log M_YES -> M_END: %d CoopState push(es) %s (want 0)"
           % (len(pushes), pushes[:2]))


class X:  # the file's run state: failing cells
    def __init__(self): self.fails = []
def main():
    x = X()
    T0[0] = time.time()
    b = Boot()
    b.c0 = crashes()
    end = {"key": KEY, "slot": harness.HARNESS_SLOT}
    try:
        ev = {"key": KEY, "slot": harness.HARNESS_SLOT, "cpu": cpu(), "t": now()}
        try:
            ok, bev = bring_up(b)
            ev.update(bev)
        except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
            ok, ev["error"] = False, ("%s: %s" % (type(e).__name__, e))[:400]
        ev["tBoot"] = now()
        print("EVIDENCE boot: %s" % js(ev), flush=True)
        if not ok:
            print("CAPTURE boot: %s" % js(capture(b)), flush=True)
            for rid, cells in ROWS[:2]:
                for cid in cells:
                    print("FAIL %s %s: boot" % (cid, "FIX" if cid in FIX else "GUARD"), flush=True)
                    x.fails.append(cid)
                print("FAIL %s: boot" % rid, flush=True)
        else:
            for rid, fn in (("naming_window", run_naming_window), ("unpaid_placement", run_unpaid_placement)):
                r = Row(x, b, rid)
                try:
                    fn(b, r)
                    r.finish()
                except Stop as e:
                    r.finish(str(e))
                except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                    r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        end["aliveBeforeShutdown"] = {gc.name: alive(gc) for gc in (b.host, b.client)}
        end["rc"] = {}
        for gc in (b.client, b.host):
            try:
                if alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
                end["rc"][gc.name] = gc.proc.poll() if gc.proc else None
            except Exception as e:  # noqa: BLE001
                end["rc"][gc.name] = str(e)[:200]
    new = sorted(crashes() - b.c0)
    end.update({"newCrash": [os.path.basename(p) for p in new], "crashDir": harness.CRASH_DIR, "cpu": cpu(), "t": now()})
    print("EVIDENCE END: %s" % js(end), flush=True)
    ok = not new and all(end["aliveBeforeShutdown"].values())
    print("%s no_crash GUARD: %d new crash file(s) %s since the bring-up; alive until shutdown %s (want 0, both alive)"
          % ("PASS" if ok else "FAIL", len(new), end["newCrash"][:4], end["aliveBeforeShutdown"]), flush=True)
    print("PASS END" if ok else "FAIL END: no_crash", flush=True)
    x.fails += [] if ok else ["no_crash"]
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY test_entry_waits_for_naming: %d/%d cells pass; failing %s; wall %.1f s"
          % (len(cl) - len(set(x.fails)), len(cl), sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2


if __name__ == "__main__":
    sys.exit(main())
