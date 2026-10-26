"""W2-H78 - test_w2_visit_during_handoff_fresh.py (VDF): a SEPARATE partner with NO stored copy of the host's base (right after a resume)
asks for the host's base while the host's battle is handed to it: nothing happens, and it reaches its briefing alive. Spec: docs
rewrite/prompts/w2h78_visit_during_handoff.md (f) rows R2, R3; TASK 0: docs rewrite/w2h78-task0/sa/CONSTANTS.md. Lead L-H74-1 (lh74-1-cap C1b,
F21614, F21624), ruling R-LH74-1-1 (QH78-1 .. QH78-7 (a)), VL-H78-1. Keys "49460" (new campaign), "49461" (resume); dirs w2h78_r2_*,
w2h78_r3_* (+ _client2). Sibling VDH (test_w2_visit_during_handoff.py): rows R1, G.
Row R2 (C1b): seat_guest, the host's save "h78r2.sav", both shut down, the host respawned on its dir and a FRESH client, resume_campaign,
    LOCATE, PRE ("baseclient" ABSENT), PROMPT, ARM (hold_blob_ack), YES (set_seed 2, real YES), HELD, CLICK (a real globe click on the host
    base, the "HostBase" target), OBS, RELEASE, ENTRY, WATCH, END. Cells R2-pre, R2-click, R2-alive, R2-brief, R2-host.
Row R3 ("h78r3.sav"): as R2 with LEVER (TEST-ONLY visit_coop_base: the same CoopState 50 request, past the click guard) for CLICK. Cells
    R3-pre, R3-drop, R3-alive, R3-brief, R3-host. Red today: every cell but R2-pre and R3-pre FAILS (8 of 10: the partner crashes in
    CoopState::loadWorld, exit code 3 recorded, never raised; the host shows 62). Green (G1, spec E1-E4): all 10 PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure; a precondition miss ends its row
("not reached") with ONE CAPTURE line, a boot miss fails its -pre cell. WV-D95 (foreground, to completion), WV-D99 (one run; exit 0 only
when every cell passes, else 2), WV-D100 (no SKIP, no exit 3). Helpers copied (never imported) from docs rewrite/lh74-1-cap/cap.py; LOCATE's
CANCEL press waits for the button to be shown (CONSTANTS.md, S54)."""
import glob, json, os, sys, time  # noqa: E401
from types import SimpleNamespace
import harness
import session
from harness import GameClient, make_user_dir

KEY, KEY_R, SAVE = "49460", "49461", {"R2": "h78r2.sav", "R3": "h78r3.sav"}
SEED_P, ZOOM_MIN, SYM_PLUS = 2, 3, 43
OBS_S, W_LEVER, W_HOLD, W_PROMPT, W_HELD, W_ENTRY, W_UI, W_SAVE, W_RESUME = 2.0, 0.5, 10.0, 120, 30, 25, 10, 30, 240
RC_OK = (0, 3221226505)
NEEDLES = {"CLICKIGN": "[coop-visit] base click ignored: a battle hand-off is in flight",
           "DROP": "[coop-visit] base request dropped: a battle hand-off is in flight (role 2)",
           "ADOPT": "W1-P3: read-only BriefingState pushed", "EQUAL": "battle_ready saveBlob EQUAL"}
CELLS = {"R2": ["R2-pre", "R2-click", "R2-alive", "R2-brief", "R2-host"], "R3": ["R3-pre", "R3-drop", "R3-alive", "R3-brief", "R3-host"]}
CRASH_GLOB = os.path.join(harness.CRASH_DIR, "crash_*")  # W2-U8h F9563: this lane's own crash folder (CIT-2 H2)
T0 = time.time()
RESULTS = []
class Stop(Exception):
    pass

# ----- probes (CAP) -----
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
def coop(gc): return pick(q(gc, {"cmd": "get_coop"}), ("insideCoopBase", "inBattle", "error"))
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

# ----- real presses (CAP) -----
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
    """click_widget by caption; shown=True first waits (W_UI) until list_widgets shows it visible and not hidden (a window hides every
    widget while it pops up, and a hidden button ignores the click: CONSTANTS.md, the LOCATE swap)"""
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
    """CLICK: centre the client's globe on the host base, zoom to ZOOM_MIN by '+' keys, real clicks at its pixel, the "HostBase" target"""
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

# ----- fixture (CAP seat_guest: bring_up_separate_guest_battle's seat) -----
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
    """quit and reap one game; a game that already exited (a crash: exit code 3) is reaped with its own code and recorded, never raised"""
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
            d[n] = ({"alive": True, "stack": stack(gc), "dlg": dlg(gc), "coop": coop(gc), "log": tail(gc)} if alive(gc)
                    else {"alive": False, "rc": gc.proc.poll() if gc and gc.proc else None, "log": tail(gc) if gc else []})
        if alive(self.x.client):
            d["client"].update(hold=pick(q(self.x.client, {"cmd": "hold_blob_ack"}), ("armed", "held")),
                               baseclient=finfo(self.x.client, "baseclient"), basehost=finfo(self.x.client, "basehost"))
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

# ----- common steps (spec (f)) -----
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
def fresh(r, x, tag):
    """CAP C1b (F21624): the host's save on disk, both shut down, the host respawned, a FRESH <tag>_client2, resume_campaign on KEY_R"""
    f = SAVE[r.rid]
    path = os.path.join(x.host.user_dir, "xcom1", f)
    n = q(x.host, {"cmd": "save_game", "file": f})
    ok, s = wait(lambda: os.path.exists(path) and os.path.getsize(path) > 0, W_SAVE)
    r.ev["save"] = {"reply": n.get("ok"), "onDisk": bool(ok), "s": s}
    if not ok:
        raise Stop("SAVE: %s not on disk within %d s: %s" % (f, W_SAVE, js(n)))
    time.sleep(1.0)
    rc = r.ev["save"]["rc"] = [shut(x.client), shut(x.host)]
    if not all(v in RC_OK for v in rc):
        raise Stop("RESTART: the first session's exit codes (client, host) %s (want %s)" % (rc, list(RC_OK)))
    t = time.time()
    x.host = GameClient("host", None, x.host.user_dir)
    x.client = GameClient("client2", None, make_user_dir(tag + "_client2"))
    x.host.spawn(); x.host.connect(timeout=W_RESUME); x.client.spawn(); x.client.connect(timeout=W_RESUME)  # noqa: E702
    session.resume_campaign(x.host, x.client, f, port=KEY_R)
    v, s2 = wait(lambda: top(x.host) == "GeoscapeState" and top(x.client) == "GeoscapeState", W_UI, 0.05)
    r.ev["resume"] = {"s": round(time.time() - t, 2), "geo": [bool(v), s2]}
    if not v:
        raise Stop("RESUME: tops (host, client) %s, %s (want GeoscapeState both)" % (top(x.host), top(x.client)))
    time.sleep(2.0)
def pre(r, x, want_bc):
    """PRE = the client's coop_file_info "baseclient" (present or absent as the row wants) and "basehost" (PRE_B)"""
    bc, bh = finfo(x.client, "baseclient"), finfo(x.client, "basehost")
    x.PRE_B = bh.get("bytes")
    r.ev["PRE"] = {"baseclient": bc, "basehost": bh}
    if bool(bc.get("present")) != want_bc or not isinstance(x.PRE_B, int) or x.PRE_B <= 0:
        raise Stop("PRE: baseclient %s (want present %s), basehost %s" % (js(bc), want_bc, js(bh)))
def prompt(r, x):
    """PROMPT = CAP's site (spawn_mission_site at the host base +0.35 / +0.10), craft_force, ConfirmLandingState on the host"""
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
def yes(r, x, arm):
    """marks (each machine's log length), ARM (the client's hold_blob_ack on) when asked, YES (set_seed SEED_P, the host's real YES)"""
    h, c = x.host, x.client
    x.nh, x.nc = len(log(h)), len(log(c))
    if arm:
        a = q(c, {"cmd": "hold_blob_ack", "on": True})
        r.ev["arm"] = pick(a, ("ok", "armed", "held"))
        if not (a.get("ok") and a.get("armed")):
            raise Stop("ARM: hold_blob_ack %s" % js(a))
    sd = q(h, {"cmd": "set_seed", "seed": SEED_P})
    k = real_click(h, "YES", W_UI)
    x.t_yes = time.time()
    r.ev["yes"] = {"seed": sd.get("ok"), "click": k.get("ok")}
    if not k.get("ok"):
        raise Stop("YES: %s" % js(k))
def held(r, x):
    """HELD = the client's hold_blob_ack held >= 1 within W_HELD; the client's top GeoscapeState"""
    c = x.client
    v, s = wait(lambda: (q(c, {"cmd": "hold_blob_ack"}).get("held") or 0) >= 1, W_HELD, 0.05)
    tc = top(c)
    r.ev["held"] = {"held": bool(v), "s": s, "top": tc}
    if not v or tc != "GeoscapeState":
        raise Stop("HELD: held %s after %.2f s, client top %s (want >= 1 within %d s, GeoscapeState)" % (bool(v), s, tc, W_HELD))
def click(r, x):
    """CLICK = CAP click_marker on the host base (the "HostBase" target), then OBS"""
    c = x.client
    x.nk = len(log(c))
    ck = click_marker(c, x.sc, x.hbpos[0], x.hbpos[1], x.HB)
    obs(r, x)
    r.ev["click"] = {"targets": ck.get("targets"), "tries": ck.get("tries"), "pick": (ck.get("pick") or {}).get("ok")}
    return r.ev["click"]["pick"] is True
def obs(r, x):
    """OBS = for OBS_S, the client's top and coop_dialog_info code every 0.05 s; the first time a CoopState 50 is on top"""
    c, t0, trace, last, x.first50 = x.client, time.time(), [], None, None
    while time.time() - t0 < OBS_S:
        tc = top(c)
        code = dlg(c).get("code") if tc == "CoopState" else None
        if code == 50 and x.first50 is None:
            x.first50 = round(time.time() - t0, 3)
        if [tc, code] != last:
            trace.append([round(time.time() - t0, 3), tc, code])
            last = [tc, code]
        time.sleep(0.05)
    r.ev["obs"] = {"trace": trace, "first50": x.first50}
def release(r, x):
    rl = q(x.client, {"cmd": "hold_blob_ack", "on": False})
    r.ev["release"] = pick(rl, ("ok", "armed", "sent"))
def entry_watch_end(r, x):
    """ENTRY = the client's ADOPT line since YES (or the client dead) within W_ENTRY; WATCH = W_HOLD s every 0.25 s; END = END_B, needles,
    the crash census"""
    h, c = x.host, x.client
    ad, s = wait(lambda: count(c, x.nc, "ADOPT") >= 1 or (not alive(c) and "DEAD"), W_ENTRY, 0.05)
    x.entry = ad is True
    r.ev["entry"] = {"adopt": ad, "s": s, "sinceYes": round(time.time() - x.t_yes, 2)}
    x.watch, t1 = [], time.time()
    while time.time() - t1 < W_HOLD:
        e = {"t": round(time.time() - t1, 2), "ha": alive(h), "ca": alive(c)}
        if e["ca"]:
            e["cs"] = stack(c)
            e["cc"] = dlg(c).get("code") if e["cs"][-1:] == ["CoopState"] else None
            e.update(coop(c))
        if e["ha"]:
            e["ht"] = top(h)
            e["hc"] = dlg(h).get("code") if e["ht"] == "CoopState" else None
        x.watch.append(e)
        time.sleep(0.25)
    x.END_B = finfo(c, "basehost").get("bytes") if alive(c) else None
    x.hInBattle = coop(h).get("inBattle")
    x.alive = [alive(h), alive(c)]
    x.newCrash = [os.path.basename(p) for p in sorted(crashes() - x.crB)]
    x.n = {"CLICKIGN": count(c, getattr(x, "nk", x.nc), "CLICKIGN"), "DROP": count(h, x.nh, "DROP"), "ADOPT": count(c, x.nc, "ADOPT"),
           "EQUAL": count(h, x.nh, "EQUAL")}
    ch = []
    for e in x.watch:
        k = [e["ca"], e.get("cs", [])[-2:], e.get("cc"), e.get("inBattle"), e.get("insideCoopBase"), e["ha"], e.get("ht"), e.get("hc")]
        if not ch or ch[-1][1:] != k:
            ch.append([e["t"]] + k)
    r.ev["END"] = {"watch": ch, "PRE_B": x.PRE_B, "END_B": x.END_B, "needles": x.n, "hostInBattle": x.hInBattle, "alive": x.alive,
                   "newCrash": x.newCrash}
def brief_cell(r, x, name, extra_ok=True, extra=""):
    ok = x.entry and bool(x.watch) and all(e["ca"] and e["cs"][-2:] == ["BattlescapeState", "BriefingState"] and e.get("inBattle") is True
                                           and e.get("insideCoopBase") is False for e in x.watch)
    r.cell(name, ok and extra_ok, "%sENTRY %s; WATCH client (stack tail, code, inBattle, insideCoopBase) %s (want ADOPT within %d s, then "
           "[BattlescapeState, BriefingState], true, false throughout %.0f s)" % (extra, r.ev["entry"]["adopt"], r.ev["END"]["watch"],
                                                                                   W_ENTRY, W_HOLD))
def host_cell(r, x, name, drop0=True):
    h62 = [e["t"] for e in x.watch if e.get("hc") == 62]
    ok = x.n["EQUAL"] == 1 and x.hInBattle is True and not h62 and (x.n["DROP"] == 0 or not drop0)
    r.cell(name, ok, "host EQUAL since YES %d, inBattle %s at WATCH's end, CoopState 62 at %s, DROP %d (want 1, true, never%s)"
           % (x.n["EQUAL"], x.hInBattle, h62, x.n["DROP"], ", 0" if drop0 else ""))

def lever(r, x):
    """LEVER = the client's visit_coop_base {base HB} (the TEST-ONLY lever: the CoopState 50 request past the click guard), then OBS"""
    x.nk = len(log(x.client))
    lv = q(x.client, {"cmd": "visit_coop_base", "base": x.HB})
    obs(r, x)
    r.ev["lever"] = pick(lv, ("ok", "error"))
    return lv.get("ok") is True
def alive_cell(r, x, name):
    r.cell(name, x.alive[1] and not x.newCrash, "client alive at WATCH's end %s (exit code %s), new crash files %s (want alive, none; today "
           "exit code 3 and a crash file: CoopState::loadWorld on an empty base list)" % (x.alive[1], x.client.proc.poll(), x.newCrash))
def pre_detail(r): return "guest seated %s, save %s, resume %s, baseclient present %s, prompt %.2f s, held %s" % (
    r.ev["seat"]["seated"], r.ev["save"], r.ev["resume"], r.ev["PRE"]["baseclient"]["present"], r.ev["promptS"], r.ev["held"])

# ----- rows -----
def body_r2(r, x):
    fresh(r, x, "w2h78_r2")
    locate(r, x)
    pre(r, x, False)
    prompt(r, x)
    yes(r, x, True)
    held(r, x)
    picked = click(r, x)
    r.cell("R2-pre", picked, "%s, CLICK targets %s picked HostBase %s" % (pre_detail(r), r.ev["click"]["targets"], picked))
    if not picked:
        raise Stop("CLICK: the HostBase target not picked: %s" % js(r.ev["click"]))
    release(r, x)
    entry_watch_end(r, x)
    r.cell("R2-click", x.first50 is None and x.n["CLICKIGN"] == 1, "OBS client (top, code) %s, first CoopState 50 at %s s; CLICKIGN %d "
           "(want no 50 within %.1f s, 1; today 50 within ~0.1 s, 0)" % (r.ev["obs"]["trace"], x.first50, x.n["CLICKIGN"], OBS_S))
    alive_cell(r, x, "R2-alive")
    brief_cell(r, x, "R2-brief")
    host_cell(r, x, "R2-host")
def body_r3(r, x):
    fresh(r, x, "w2h78_r3")
    locate(r, x)
    pre(r, x, False)
    prompt(r, x)
    yes(r, x, True)
    held(r, x)
    ok = lever(r, x)
    good = ok and x.first50 is not None and x.first50 <= W_LEVER
    r.cell("R3-pre", good, "%s, LEVER reply %s, first CoopState 50 on the client's top at %s s (want ok, within %.1f s)"
           % (pre_detail(r), r.ev["lever"], x.first50, W_LEVER))
    if not good:
        raise Stop("LEVER: %s, first 50 at %s s" % (js(r.ev["lever"]), x.first50))
    release(r, x)
    entry_watch_end(r, x)
    r.cell("R3-drop", x.n["DROP"] == 1, "host DROP lines since YES %d (want 1; today 0: the host serves the request mid-stream)" % x.n["DROP"])
    alive_cell(r, x, "R3-alive")
    with50 = [e["t"] for e in x.watch if any("CoopState" in s for s in e.get("cs", []))]
    brief_cell(r, x, "R3-brief", not with50, "a CoopState on the client's stack at WATCH %s (want never: the adoption pops the 50); " % with50)
    host_cell(r, x, "R3-host", drop0=False)
def main():
    c0 = cpu()
    print("==== W2-H78 VDF (slot %s, keys %s / %s, exe %s) CPU %s ====" % (harness.HARNESS_SLOT, KEY, KEY_R, time.ctime(os.path.getmtime(harness.EXE)), c0))
    Row("R2").run(body_r2, "w2h78_r2")
    Row("R3").run(body_r3, "w2h78_r3")
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== W2-H78 VDF: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()))
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2
if __name__ == "__main__":
    sys.exit(main())
