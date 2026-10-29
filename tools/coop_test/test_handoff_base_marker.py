"""test_handoff_base_marker.py: a SEPARATE partner clicks the host's base just before the host presses YES on a landing,
and the host's base answer ends AFTER the battle offer reached the partner and BEFORE the host read the partner's battle_accept. The partner
drops that cut answer in its hand-off and reaches its briefing; nothing from the cut answer is stored or opened.

Lobby key "49517", user dirs handoff_base_marker_*. test_handoff_base_stream.py checks the base answer still streaming
when the partner's battle_accept arrives. Test hooks: hold_blob_ack {on: true, scope: "base"} and hold_battle_accept
(the client's onOffer stashes its battle_accept; {on: false} sends it).
Row answer_after_offer: seat_guest, LOCATE, PRE ("baseclient" present, PRE_F), PROMPT, ARM, the client's
    hold_battle_accept {on: true}, CLICK (a real globe click on the host base and the "HostBase" target; the client's
    CoopState 50 on top within 1 s), HELD, YES (set_seed 2, the host's real YES), STASH (client) within W_ACC with
    0 ACCRX on the host, RELEASE (the ack hold), MARKER (BASEDROP, or the client's "baseclient" fnv != PRE_F - an absent
    "baseclient" reads fnv "" and differs - or the client's session gone) within W_MARK, the client's hold_battle_accept
    {on: false} (if alive and connected), ENTRY (from that release), WATCH, END.
    Cells answer_after_offer-pre, -drop, -store, -entry, -brief, -host, -crash.
Without the fix: the base answer ends MAP_RESULT_CLIENT_BASE, the partner's CoopState 55 parses the post-offer tail and
throws, its catch ends the partner's session (a crash-log file) and the host unwinds the start: the -drop, -store,
-entry, -brief, -host and -crash cells FAIL (6 of 7), -pre passes. With the fix all 7 pass.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; a precondition miss ends the row (later cells "not reached")
with ONE CAPTURE line; a boot miss fails answer_after_offer-pre with ONE CAPTURE line. One run: exit 0 only when every
cell passes, else 2 (no skip, no exit 3). LOCATE's CANCEL press waits for the button to be shown."""
import glob, json, os, sys, time  # noqa: E401
from types import SimpleNamespace
import harness
import session
from harness import GameClient, make_user_dir

KEY = "49517"
YES_SEED = 2
ZOOM_MIN, SYM_PLUS = 3, 43
W_CLICK50, W_HELD, W_ACC, W_MARK, W_ENTRY, W_HOLD, W_PROMPT, W_UI = 1.0, 15, 30, 10, 30, 10.0, 120, 10
RC_OK = (0, 3221226505)
NEEDLES = {"ADOPT": "read-only BriefingState pushed", "EQUAL": "battle_ready saveBlob EQUAL",
           "DEFER": "[coop-handshake] battle blob deferred: a world stream to the partner is still running",
           "START": "[coop-handshake] deferred battle blob streaming (battleId=",
           "BASEDROP": "[coop-visit] base answer dropped: a battle hand-off is in flight",
           "ACCEPTED": "[coop-handshake] battle_offer accepted (battleId=", "ACCRX": "[coop-handshake] battle_accept received (battleId=",
           "STASH": "[coop-test] hold_battle_accept: battle_accept stashed"}
HOST_NEEDLES = ("EQUAL", "DEFER", "START", "ACCRX")
CELLS = {"answer_after_offer": ["answer_after_offer-pre", "answer_after_offer-drop", "answer_after_offer-store",
                                "answer_after_offer-entry", "answer_after_offer-brief", "answer_after_offer-host",
                                "answer_after_offer-crash"]}
CRASH_GLOB = os.path.join(harness.CRASH_DIR, "crash_*")  # this harness slot's own crash folder
T0 = time.time()
RESULTS = []
class Stop(Exception):
    pass

# ----- probes -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def short(e, n=300): return ("%s: %s" % (type(e).__name__, e))[:n]
def pick(r, keys): return {k: r.get(k) for k in keys}
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(CRASH_GLOB, recursive=True))
def q(gc, obj):
    if not alive(gc):
        return {"error": "dead"}
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001 - a probe failure is a value
        return {"error": short(e, 200)}
def stack(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.replace("class OpenXcom::", "") for s in r.get("states", [])] if "states" in r else ["probe failed %s" % r.get("error")]
def top(gc):
    s = stack(gc)
    return s[-1] if s else None
def dlg(gc): return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "backText", "backVisible", "error"))
def ncode(gc, code): return q(gc, {"cmd": "coop_dialog_count", "code": code}).get("count")
def coop(gc): return pick(q(gc, {"cmd": "get_coop"}), ("insideCoopBase", "inBattle", "onConnect", "error"))
def hold(gc): return pick(q(gc, {"cmd": "hold_blob_ack"}), ("armed", "held", "scope", "error"))
def finfo(gc, key): return pick(q(gc, {"cmd": "coop_file_info", "key": key}), ("present", "bytes", "fnv1a64", "error"))
def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log") if gc else ""
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if p and os.path.exists(p) else []
def tail(gc, n=40): return [ln.split("\t")[-1][:300] for ln in log(gc)[-n:]]
def count(gc, n0, key): return sum(1 for ln in log(gc)[n0:] if NEEDLES[key] in ln)
def cpu():
    c = harness.cpu_load()
    return "%s %% (Wardogs %s)" % (harness.cpu_text(c["cpu"]), len(c["wardogs"]))
def wait(pred, timeout, interval=0.25):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 2)
        time.sleep(interval)

# ----- real presses -----
def real_click(gc, text, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = q(gc, {"cmd": "list_widgets"})
        w = next((w for w in r.get("widgets", []) if (w.get("text") or "").strip().lower() == text.lower() and w.get("visible") is True
                  and w.get("hidden") is False), None)
        if w is not None:
            c = q(gc, {"cmd": "click_widget", "match": w.get("text")})
            return {"ok": bool(c.get("ok")), "state": (r.get("state") or "").replace("class OpenXcom::", ""), "s": round(time.time() - t0, 2)}
        time.sleep(0.05)
    return {"ok": False, "miss": "%s: button %r not shown within %.0f s" % (gc.name, text, timeout)}
def cw(gc, match, settle=0.8, shown=False):
    """click_widget by caption; shown=True first waits (W_UI) until list_widgets shows it visible and not hidden"""
    t0 = time.time()
    while shown and time.time() - t0 < W_UI and not any(match.lower() in (w.get("text") or "").lower() and w.get("visible") is True
                                                        and w.get("hidden") is False for w in q(gc, {"cmd": "list_widgets"}).get("widgets", [])):
        time.sleep(0.05)
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(0 if shown else settle)
    return {"base": [r.get("baseX"), r.get("baseY")], "win": [r.get("winX"), r.get("winY")]}
def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def click_px(gc, bx, by, sc, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    tries = []
    for dx, dy in offsets:
        wx, wy = int(round(sc[0] * (bx + dx) + sc[1])), int(round(sc[2] * (by + dy) + sc[3]))
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        v, _ = wait(lambda: top(gc) != "GeoscapeState", 1.0, 0.05)
        tries.append([wx, wy, top(gc)])
        if v:
            break
    return tries
def click_marker(gc, sc, lon, lat, name):
    """centre the client's globe on the host base, zoom to ZOOM_MIN by '+' keys, real clicks at its pixel, the "HostBase" target"""
    globe(gc, centerLon=lon, centerLat=lat)
    zs = [globe(gc).get("zoom")]
    while (zs[-1] or 0) < ZOOM_MIN and len(zs) < 7:
        q(gc, {"cmd": "inject_input", "kind": "key", "key": SYM_PLUS})
        time.sleep(0.6)
        zs.append(globe(gc).get("zoom"))
    g = globe(gc, lon=lon, lat=lat)
    out = {"zooms": zs, "px": [g.get("x"), g.get("y")], "tries": click_px(gc, g.get("x"), g.get("y"), sc)}
    if top(gc) == "MultipleTargetsState":
        lw = q(gc, {"cmd": "list_widgets"})
        out["targets"] = [w.get("text") for w in lw.get("widgets", []) if w.get("text")]
        t = next((t for t in out["targets"] if t.strip() == name), None)
        if t:
            out["pick"] = real_click(gc, t.strip(), 5)
    return out
def geo_clean(gc):
    st = stack(gc)
    return bool(st) and st[-1] == "GeoscapeState" and not any(("CoopState" in s or "LoadGameState" in s) for s in st)

# ----- fixture (seat_guest: bring_up_separate_guest_battle's seat) -----
def seat_guest(h, c, ev):
    session.new_campaign(h, c, port=KEY)
    hb = session._campaign_own_roster_base(h)
    cid = session._campaign_skyranger(h)["id"]
    rh = sorted(s["id"] for s in hb["soldiers"])
    for sid in rh:
        h.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in rh[:3]:
        if not h.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True}).get("seated"):
            raise Stop("host soldier %s not seated" % sid)
    cb = session._campaign_own_roster_base(c)
    spare = next(s for s in cb["soldiers"] if not s.get("craft"))["name"]
    c.ok({"cmd": "rename_soldier", "name": spare, "newName": "Guest Zzz"})
    if not c.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": hb["name"]}).get("transferred"):
        raise Stop("guest transfer failed")
    c.ok({"cmd": "visit_coop_base", "base": hb["name"]})
    c.wait_for("client inside host base", lambda: c.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = c.wait_for("guest visible at host base", lambda: (lambda r: r if any("Guest" in s["name"] for s in r["soldiers"]) else None)(
        c.ok({"cmd": "base_report", "coop": True})), timeout=40)
    gid = next(s for s in rep["soldiers"] if "Guest" in s["name"])["id"]
    peer = next(k for k in rep["crafts"] if "SKYRANGER" in k["type"])["id"]
    sa = c.ok({"cmd": "craft_assign", "soldier_id": gid, "craft_id": peer, "coop": True, "on": True})
    c.ok({"cmd": "open_soldiers", "base": hb["name"]})
    c.wait_for("client soldiers screen", lambda: session.has_state(c, "SoldiersState") or None, timeout=30)
    c.ok({"cmd": "soldiers_ok"})
    c.ok({"cmd": "leave_base"})
    session.wait_back_on_geoscape(c, "client back on geoscape")
    ev["seat"] = {"hostBase": hb["name"], "craft": cid, "squad": rh[:3], "guest": gid, "seated": sa.get("seated")}
    if sa.get("seated") is not True:
        raise Stop("the guest not seated on the host's Skyranger: %s" % js(sa))
    return hb["name"], cid
def boot(x, tag):
    x.host = GameClient("host", None, make_user_dir(tag + "_host"))
    x.client = GameClient("client", None, make_user_dir(tag + "_client"))
    x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()  # noqa: E702
    x.HB, x.cid = seat_guest(x.host, x.client, x.ev)
    time.sleep(2.0)
def shut(gc):
    """quit and reap one game; a game that already exited is reaped with its own code and recorded, never raised"""
    try:
        if gc is None or gc.proc is None:
            return None
        rc = gc.proc.poll()
        gc.shutdown(expected_returncodes=RC_OK if rc is None else (rc,))
        return gc.proc.poll()
    except Exception as e:  # noqa: BLE001 - a failed shutdown is a value
        return short(e, 200)
class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.done = rid, CELLS[rid], {}, {}
        self.x = SimpleNamespace(host=None, client=None, ev=self.ev, crB=crashes(), t0=time.time())

    def cell(self, name, ok, detail):
        self.done[name] = bool(ok)
        RESULTS.append((name, bool(ok)))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    def capture(self, why):
        d = {"why": why}
        for n in ("host", "client"):
            gc = getattr(self.x, n)
            d[n] = ({"alive": True, "stack": stack(gc), "dlg": dlg(gc), "coop": coop(gc), "hold": hold(gc), "log": tail(gc)} if alive(gc)
                    else {"alive": False, "rc": gc.proc.poll() if gc and gc.proc else None, "log": tail(gc) if gc else []})
        print("CAPTURE %s: %s" % (self.rid, js(d)), flush=True)

    def run(self, body, tag):
        x = self.x
        why = ""
        try:
            try:
                boot(x, tag)
            except Exception as e:  # noqa: BLE001 - a boot miss fails the row's -pre cell with ONE CAPTURE line
                self.capture("boot: " + short(e))
                self.cell(self.cells[0], False, "boot: %s" % short(e))
                raise Stop("boot")
            body(self, x)
        except Exception as e:  # noqa: BLE001 - a precondition miss ends the row
            why = self.ev["stop"] = short(e, 500)
            if str(e) != "boot":
                self.capture(why)
        finally:
            self.ev["rc"] = [shut(x.client), shut(x.host)]
        for n in self.cells:
            if n not in self.done:
                self.cell(n, False, "not reached: %s" % why)
        self.ev["wall"] = round(time.time() - x.t0, 1)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        bad = [n for n in self.cells if not self.done.get(n)]
        print("ROW %s: %s" % (self.rid, "PASS" if not bad else "FAIL (%d failing: %s)" % (len(bad), bad)), flush=True)

# ----- common steps -----
def locate(r, x):
    """LOCATE = the host base's lon / lat from the host's geo_state; the client's affine from INTERCEPT / CANCEL"""
    session.drain_host_coop_notice(x.host)
    hb = next(b for b in q(x.host, {"cmd": "geo_state"})["bases"] if b.get("name") == x.HB and not b.get("coopIcon"))
    x.hbpos = [hb["lon"], hb["lat"]]
    x.sc = affine(cw(x.client, "INTERCEPT"), cw(x.client, "CANCEL", shown=True))
    g, s = wait(lambda: geo_clean(x.client), W_UI, 0.05)
    r.ev["locate"] = {"hbpos": x.hbpos, "sc": x.sc, "geoClean": [bool(g), s]}
    if not g:
        raise Stop("LOCATE: the client not back on a clean geoscape: %s" % stack(x.client))
def pre(r, x):
    """PRE = the client's coop_file_info "baseclient" (present, fnv PRE_F)"""
    bc = finfo(x.client, "baseclient")
    x.PRE_F = bc.get("fnv1a64")
    r.ev["PRE"] = {"baseclient": bc}
    if not bc.get("present") or not x.PRE_F:
        raise Stop("PRE: baseclient %s (want present)" % js(bc))
def prompt(r, x):
    """PROMPT = a mission site (spawn_mission_site at the host base +0.35 / +0.10), craft_force, ConfirmLandingState on
    the host"""
    h = x.host
    b0 = session._campaign_base0(h)
    sid = h.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    h.wait_for("site on host", lambda: any(s["id"] == sid for s in h.ok({"cmd": "geo_state"})["missionSites"]) or None, timeout=30)
    h.ok({"cmd": "craft_force", "craft_id": x.cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10, "dest": "site:%s" % sid,
          "fuel": 999999, "lowFuel": False})
    def landing():
        if session.has_state(h, "ConfirmLandingState"):
            return True
        t = session.states(h)[-1]
        if "CoopState" in t:
            h.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in t:
            h.cmd({"cmd": "dismiss_popup"})
        h.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    t = time.time()
    h.wait_for("host landing prompt", landing, timeout=W_PROMPT, interval=0.25)
    r.ev["promptS"] = round(time.time() - t, 2)
    time.sleep(1.0)
def arm(r, x):
    """ARM = the client's hold_blob_ack {on: true, scope: "base"}"""
    a = q(x.client, {"cmd": "hold_blob_ack", "on": True, "scope": "base"})
    r.ev["arm"] = pick(a, ("ok", "armed", "scope"))
    if not (a.get("ok") and a.get("armed") and a.get("scope") == 1):
        raise Stop("ARM: hold_blob_ack %s" % js(a))
def click(r, x):
    """CLICK = click_marker on the host base ("HostBase"); the client's top CoopState 50 within W_CLICK50; HELD within
    W_HELD"""
    c = x.client
    ck = click_marker(c, x.sc, x.hbpos[0], x.hbpos[1], x.HB)
    v50, s50 = wait(lambda: top(c) == "CoopState" and dlg(c).get("code") == 50, W_CLICK50, 0.05)
    r.ev["click"] = {"targets": ck.get("targets"), "pick": (ck.get("pick") or {}).get("ok"), "coop50": [bool(v50), s50],
                     "hostBasehost": finfo(x.host, "basehost").get("bytes")}
    if not ((ck.get("pick") or {}).get("ok") and v50):
        raise Stop("CLICK: %s, client top %s dlg %s" % (js(r.ev["click"]), top(c), js(dlg(c))))
    hv, sh = wait(lambda: (hold(c).get("held") or 0) >= 1, W_HELD, 0.05)
    r.ev["held"] = [bool(hv), sh]
    if not hv:
        raise Stop("HELD: no base-answer ack withheld within %d s: %s" % (W_HELD, js(hold(c))))
def yes(r, x):
    """marks (each machine's log length), YES (set_seed YES_SEED, the host's real YES)"""
    h, c = x.host, x.client
    x.nh, x.nc = len(log(h)), len(log(c))
    sd = q(h, {"cmd": "set_seed", "seed": YES_SEED})
    k = real_click(h, "YES", W_UI)
    x.t_yes = time.time()
    r.ev["yes"] = {"seed": sd.get("ok"), "click": k.get("ok")}
    if not k.get("ok"):
        raise Stop("YES: %s" % js(k))
def entry_watch_end(r, x, t_from):
    """ENTRY = the client's ADOPT since YES (or the client dead) within W_ENTRY of t_from; WATCH = W_HOLD s every 0.25 s; END = END_F,
    the needles since YES, the crash census"""
    h, c = x.host, x.client
    ad, s = wait(lambda: count(c, x.nc, "ADOPT") >= 1 or (not alive(c) and "DEAD"), max(0.0, W_ENTRY - (time.time() - t_from)), 0.05)
    x.entry = ad is True
    r.ev["entry"] = {"adopt": ad, "s": round(time.time() - t_from, 2), "sinceYes": round(time.time() - x.t_yes, 2)}
    x.watch, t1 = [], time.time()
    while time.time() - t1 < W_HOLD:
        e = {"t": round(time.time() - t1, 2), "ha": alive(h), "ca": alive(c)}
        if e["ca"]:
            e["cs"] = stack(c)
            e["cc"] = dlg(c).get("code") if e["cs"][-1:] == ["CoopState"] else None
            e["c50"] = ncode(c, 50)
            e.update(pick(coop(c), ("insideCoopBase", "inBattle")))
        if e["ha"]:
            e["ht"] = top(h)
            e["hc"] = dlg(h).get("code") if e["ht"] == "CoopState" else None
            e["h62"] = ncode(h, 62)
        x.watch.append(e)
        time.sleep(0.25)
    x.END_F = finfo(c, "baseclient").get("fnv1a64") if alive(c) else None
    x.alive = [alive(h), alive(c)]
    x.newCrash = [os.path.basename(p) for p in sorted(crashes() - x.crB)]
    x.n = {k: count(h, x.nh, k) if k in HOST_NEEDLES else count(c, x.nc, k) for k in NEEDLES}
    ch = []
    for e in x.watch:
        k = [e["ca"], e.get("cs", [])[-3:], e.get("cc"), e.get("c50"), e.get("inBattle"), e["ha"], e.get("ht"), e.get("hc"), e.get("h62")]
        if not ch or ch[-1][1:] != k:
            ch.append([e["t"]] + k)
    r.ev["END"] = {"watch": ch, "PRE_F": x.PRE_F, "END_F": x.END_F, "needles": x.n, "alive": x.alive, "newCrash": x.newCrash}
def acc(gc): return pick(q(gc, {"cmd": "hold_battle_accept"}), ("armed", "held", "error"))
def brief_cell(r, x, name):
    ok = x.entry and bool(x.watch) and all(e["ca"] and e["cs"][-1:] == ["BriefingState"] and e.get("c50") == 0 and e.get("inBattle") is True
                                           and "BasescapeState" not in e["cs"] for e in x.watch)
    r.cell(name, ok, "ENTRY %s; WATCH client [alive, stack tail, code, CoopState 50 count, inBattle, ...] %s (want ADOPT within %d s of the "
           "accept's release, then BriefingState on top, no CoopState 50, no BasescapeState, inBattle true throughout %.0f s)"
           % (r.ev["entry"], r.ev["END"]["watch"], W_ENTRY, W_HOLD))
def host_cell(r, x, name):
    h62 = [e["t"] for e in x.watch if (e.get("h62") or 0) > 0]
    r.cell(name, x.n["EQUAL"] == 1 and not h62, "host EQUAL since YES %d, CoopState 62 during WATCH at %s (want 1, never)" % (x.n["EQUAL"], h62))

# ----- row -----
def marker(x):
    """MARKER: BASEDROP, or the "baseclient" fnv != PRE_F (absent included), or the client's session gone (get_coop error, MainMenuState, dead)"""
    c = x.client
    if count(c, x.nc, "BASEDROP") >= 1:
        return "BASEDROP"
    if not alive(c):
        return "DEAD"
    if "error" in q(c, {"cmd": "get_coop"}):
        return "GETCOOP_ERROR"
    if top(c) == "MainMenuState":
        return "MAINMENU"
    fv = finfo(c, "baseclient")
    if fv.get("error") is None and fv.get("fnv1a64") != x.PRE_F:
        return "FNV %s" % (fv.get("fnv1a64") or "(absent)")
    return None
def body_answer_after_offer(r, x):
    c, h = x.client, x.host
    locate(r, x)
    pre(r, x)
    prompt(r, x)
    arm(r, x)
    aa = q(c, {"cmd": "hold_battle_accept", "on": True})
    r.ev["armAccept"] = pick(aa, ("ok", "armed", "held"))
    if not (aa.get("ok") and aa.get("armed")):
        raise Stop("ARM: hold_battle_accept %s" % js(aa))
    click(r, x)
    yes(r, x)
    st, ss = wait(lambda: count(c, x.nc, "STASH") >= 1, W_ACC, 0.05)
    a0 = count(h, x.nh, "ACCRX")
    r.ev["stash"] = {"ok": bool(st), "s": ss, "accrx": a0, "accept": acc(c)}
    if not st or a0 != 0:
        raise Stop("STASH: the client's stash line %s within %d s, host ACCRX %d (want the line, 0)" % (bool(st), W_ACC, a0))
    rl = q(c, {"cmd": "hold_blob_ack", "on": False})
    r.ev["release"] = pick(rl, ("ok", "armed", "sent"))
    mk, sm = wait(lambda: marker(x), W_MARK, 0.05)
    a1 = count(h, x.nh, "ACCRX")
    cc = coop(c)
    r.ev["marker"] = {"which": mk, "s": sm, "accrx": a1, "coop": cc, "top": top(c)}
    r.cell("answer_after_offer-pre", bool(mk) and a1 == 0,
           "guest seated %s, baseclient present, prompt %.2f s, CLICK targets %s picked %s, CoopState 50 %s, "
           "HELD %s, STASH %s after %.2f s, host ACCRX while stashed %d, MARKER %s after %.2f s (want all, 0, a marker within W_MARK %d s)"
           % (r.ev["seat"]["seated"], r.ev["promptS"], r.ev["click"]["targets"], r.ev["click"]["pick"], r.ev["click"]["coop50"], r.ev["held"],
              bool(st), ss, a1, mk, sm, W_MARK))
    if not mk:
        raise Stop("MARKER: no BASEDROP, no baseclient change and the session still up within %d s" % W_MARK)
    if alive(c) and cc.get("onConnect") == 1 and cc.get("error") is None:
        ra = q(c, {"cmd": "hold_battle_accept", "on": False})
        r.ev["acceptRelease"] = pick(ra, ("ok", "armed", "held", "sent"))
    else:
        r.ev["acceptRelease"] = {"skipped": "client alive %s, onConnect %s" % (alive(c), cc.get("onConnect"))}
    entry_watch_end(r, x, time.time())
    r.cell("answer_after_offer-drop", x.n["BASEDROP"] == 1 and x.n["DEFER"] == 0,
           "client BASEDROP %d, host DEFER %d since YES (want 1, 0)" % (x.n["BASEDROP"], x.n["DEFER"]))
    r.cell("answer_after_offer-store", x.END_F == x.PRE_F,
           "client baseclient fnv END_F %r vs PRE_F %r (want equal)" % (x.END_F, x.PRE_F))
    r.cell("answer_after_offer-entry", x.entry, "ADOPT %s within %d s of the accept's release %s (%s)"
           % (r.ev["entry"]["adopt"], W_ENTRY, r.ev["acceptRelease"], r.ev["entry"]))
    brief_cell(r, x, "answer_after_offer-brief")
    host_cell(r, x, "answer_after_offer-host")
    r.cell("answer_after_offer-crash", not x.newCrash and all(x.alive),
           "new crash files %s, alive (host, client) %s (want none, both)" % (x.newCrash, x.alive))
def main():
    c0 = cpu()
    print("==== test_handoff_base_marker (slot %s, key %s, exe %s) CPU %s ====" % (
        harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    Row("answer_after_offer").run(body_answer_after_offer, "handoff_base_marker")
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== test_handoff_base_marker: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (
        len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()), flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2

if __name__ == "__main__":
    sys.exit(main())
