"""W2-H82 S-B - test_w2_visit_during_save_push.py (VSP): the SEPARATE host saves, presses CANCEL on "Saving...", and clicks the partner's base
while the partner's save-progress stream is still running. The host gets the base view once that stream has ended, its "Synchronizing bases..."
closes, and the partner's save progress still reaches the host (VL-H82-2).

Spec: docs rewrite/prompts/w2h82_stream_crossing_hangs.md (common) + rewrite/prompts/w2h82_sb_visit_during_save_push.md (f) rows R-SP and G;
TASK 0 constants: docs rewrite/w2h82-task0/sb/CONSTANTS.md. Lead L-H78-1 (capture lh78-1-cap SP-1 / SP-ctl, F22296, F22298), ruling
R-LH78-1-1 (REG :1431), mechanism R-H82-1 (QH82-1 .. QH82-7 (a)). Lobby key "49518", dirs w2h82_sp_*, w2h82_g_*. The sibling VSR
(test_w2_visit_before_save_reply.py) holds row R-SPB. TEST-ONLY lever: hold_blob_ack {on: true, scope: "save"} (W2-H82 L1: the host withholds
the per-chunk ack while its own save is pending, so the partner's save-progress stream waits after its first chunk).
Row R-SP (capture SP-1): seat_guest, LOCATE (the host's affine, the partner base CB), STABLE (stable geoscapes, both clocks geo_set_speed 0),
    PREC (the host's copy of the partner's world, fnv PRE_C), ARM, SAVE (save_game_ui quick; the host's CoopState 54), HELD, CANCEL (real),
    HCLICK (a real globe click on the partner base and the "ClientBase" target; the host's CoopState 50 within 1 s), SETTLE, RELEASE, COPY,
    VIEW (the host's BasescapeState within W_VIEW of RELEASE), WATCH, LEAVE (real GEOSCAPE, if VIEW), END. Cells SP-pre, SP-copy, SP-view,
    SP-held, SP-crash.
Row G (capture SP-ctl, the guard: no click during the stream): seat_guest, LOCATE, STABLE, PREC, ARM, SAVE, HELD, CANCEL, RELEASE, COPY, STABLE,
    an unheld HCLICK, VIEW (from that click), WATCH, LEAVE, END. Cells G-pre, G-copy, G-view, G-quiet.
Red today (R1): SP-view, SP-held FAIL (2 of 9); every other cell PASS. Green (G1, spec F1-F5): all 9 PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; every row runs after a failure; a precondition miss ends its
row (later cells "not reached") with ONE CAPTURE line; a boot miss fails the row's -pre cell with ONE CAPTURE line. WV-D95 (run to completion
in the foreground), WV-D99 (one run; exit 0 only when every cell passes, else 2), WV-D100 (no SKIP, no exit 3). Helpers copied (never
imported) from docs rewrite/lh78-1-cap/cap.py; LOCATE's CANCEL press waits for the button to be shown (F21950)."""
import glob, json, os, subprocess, sys, time  # noqa: E401
from types import SimpleNamespace
import harness
import session
from harness import GameClient, make_user_dir

KEY = "49518"
ZOOM_MIN, SYM_PLUS = 3, 43
W_54, W_CANCEL, W_CLICK50, W_HELD, W_VIEW, W_COPY, W_HOLD, W_LEAVE, W_UI, SETTLE_S = 10, 10, 1.0, 15, 15, 20, 10.0, 60, 10, 1.0
RC_OK = (0, 3221226505)
NEEDLES = {"STREAMHOLD": "[coop-visit] base answer held: a world stream is in flight (role 1)",
           "EB4REL": "[coop-visit] held base answer released (role 1)",
           "REPLYHOLD": "[coop-save] save-progress go-ahead held: a world stream is in flight",
           "REPLYREL": "[coop-save] held save-progress go-ahead released",
           "REPLYSTASH": "[coop-test] hold_save_reply: SEND_FILE_HOST_SAVE_PROGRESS held"}
HOST_NEEDLES = ("REPLYSTASH",)
CELLS = {"R-SP": ["SP-pre", "SP-copy", "SP-view", "SP-held", "SP-crash"], "G": ["G-pre", "G-copy", "G-view", "G-quiet"]}
CRASH_GLOB = os.path.join(os.path.dirname(os.path.abspath(harness.EXE)), "crashlogs", "**", "crash_*")
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
def ncode(gc, code): return q(gc, {"cmd": "coop_dialog_count", "code": code}).get("count")
def coop(gc): return pick(q(gc, {"cmd": "get_coop"}), ("insideCoopBase", "inBattle", "onConnect", "pendingHostSaveName", "error"))
def hold(gc): return pick(q(gc, {"cmd": "hold_blob_ack"}), ("armed", "held", "scope", "error"))
def copyq(gc): return pick(q(gc, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key", "present", "bytes", "fnv1a64", "error"))
def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log") if gc else ""
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if p and os.path.exists(p) else []
def tail(gc, n=40): return [ln.split("\t")[-1][:300] for ln in log(gc)[-n:]]
def count(gc, n0, key): return sum(1 for ln in log(gc)[n0:] if NEEDLES[key] in ln)
def cpu():
    ps = ("[math]::Round(((Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples | "
          "Measure-Object -Property CookedValue -Average).Average, 1); @(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count")
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout.split()
        return "%s %% (Wardogs %s)" % (v[0] if v else None, v[1] if len(v) > 1 else None)
    except Exception as e:  # noqa: BLE001 - a value
        return short(e, 80)
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
    """click_widget by caption; shown=True first waits (W_UI) until list_widgets shows it visible and not hidden (F21950)"""
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
    """centre the host's globe on the partner base, zoom to ZOOM_MIN by '+' keys, real clicks at its pixel, the "ClientBase" target"""
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
def stable_geo(host, client, stable=5.0, timeout=90.0):
    t0, last, prev = time.time(), time.time(), None
    while time.time() - t0 < timeout:
        cur = (tuple(stack(host)), tuple(stack(client)))
        if cur != prev:
            prev, last = cur, time.time()
        if cur[0] and cur[1] and cur[0][-1] == "GeoscapeState" and cur[1][-1] == "GeoscapeState" and time.time() - last >= stable:
            return {"ok": True, "s": round(time.time() - t0, 2)}
        time.sleep(0.1)
    return {"ok": False, "host": list(prev[0]) if prev else None, "client": list(prev[1]) if prev else None}

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
def boot(x, tag):
    x.host = GameClient("host", None, make_user_dir(tag + "_host"))
    x.client = GameClient("client", None, make_user_dir(tag + "_client"))
    x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()  # noqa: E702
    seat_guest(x.host, x.client, x.ev)
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
        self.x = SimpleNamespace(host=None, client=None, ev=self.ev, crB=crashes(), t0=time.time(), view=False, leave=False, watch=[])

    def cell(self, name, ok, detail):
        self.done[name] = bool(ok)
        RESULTS.append((name, bool(ok)))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    def capture(self, why):
        d = {"why": why}
        for n in ("host", "client"):
            gc = getattr(self.x, n)
            d[n] = ({"alive": True, "stack": stack(gc), "dlg": dlg(gc), "coop": coop(gc), "hold": hold(gc), "copy": copyq(gc), "log": tail(gc)}
                    if alive(gc) else {"alive": False, "rc": gc.proc.poll() if gc and gc.proc else None, "log": tail(gc) if gc else []})
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
    """LOCATE = the partner base CB / cbpos from the host's geo_state (coopIcon); the host's affine from INTERCEPT / CANCEL"""
    session.drain_host_coop_notice(x.host)
    cb = next((b for b in q(x.host, {"cmd": "geo_state"}).get("bases") or [] if b.get("coopIcon")), None)
    if not cb:
        raise Stop("LOCATE: no partner base (coopIcon) in the host's geo_state")
    x.CB, x.cbpos = cb.get("name"), [cb["lon"], cb["lat"]]
    x.hsc = affine(cw(x.host, "INTERCEPT"), cw(x.host, "CANCEL", shown=True))
    g, s = wait(lambda: geo_clean(x.host), W_UI, 0.05)
    r.ev["locate"] = {"cb": x.CB, "cbpos": x.cbpos, "hsc": x.hsc, "geoClean": [bool(g), s]}
    if not g:
        raise Stop("LOCATE: the host not back on a clean geoscape: %s" % stack(x.host))
def stable(r, x, tag="stable"):
    """STABLE = CAP stable_geo, then both machines geo_set_speed {idx: 0} (R-H18-1)"""
    sg = stable_geo(x.host, x.client)
    sp = [q(x.host, {"cmd": "geo_set_speed", "idx": 0}).get("ok"), q(x.client, {"cmd": "geo_set_speed", "idx": 0}).get("ok")]
    r.ev[tag] = {"r": sg, "speed": sp}
    if not sg.get("ok") or not all(sp):
        raise Stop("%s: %s" % (tag.upper(), js(r.ev[tag])))
def prec(r, x):
    """PREC = the host's coop_file_info {role: "host_copy_of_client"} (present, fnv PRE_C)"""
    cp = copyq(x.host)
    x.PRE_C = cp.get("fnv1a64")
    r.ev["PREC"] = cp
    if not cp.get("present") or not x.PRE_C:
        raise Stop("PREC: host_copy_of_client %s (want present)" % js(cp))
def arm(r, x, scope, code):
    a = q(x.host, {"cmd": "hold_blob_ack", "on": True, "scope": scope})
    r.ev["arm_" + scope] = pick(a, ("ok", "armed", "scope"))
    if not (a.get("ok") and a.get("armed") and a.get("scope") == code):
        raise Stop("ARM %s: hold_blob_ack %s" % (scope, js(a)))
def save(r, x):
    """marks (each machine's log length), SAVE = the host's save_game_ui {type: "quick"}; its top CoopState 54 within W_54"""
    h = x.host
    x.nh, x.nc = len(log(h)), len(log(x.client))
    sv = q(h, {"cmd": "save_game_ui", "type": "quick"})
    v, s = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 54, W_54, 0.05)
    r.ev["save"] = {"ok": sv.get("ok"), "saw54": [bool(v), s], "pending": coop(h).get("pendingHostSaveName")}
    if not v:
        raise Stop("SAVE: the host's CoopState 54 not on top within %d s: %s %s" % (W_54, stack(h), js(dlg(h))))
def held(r, x):
    """HELD = the host's hold_blob_ack held >= 1 within W_HELD"""
    v, s = wait(lambda: (hold(x.host).get("held") or 0) >= 1, W_HELD, 0.05)
    r.ev["held"] = [bool(v), s]
    if not v:
        raise Stop("HELD: no ack withheld within %d s: %s" % (W_HELD, js(hold(x.host))))
def cancel(r, x):
    """CANCEL = the host's real "CANCEL"; its top GeoscapeState within W_CANCEL"""
    h = x.host
    k = real_click(h, "CANCEL", W_UI)
    g, s = wait(lambda: top(h) == "GeoscapeState", W_CANCEL, 0.05)
    r.ev["cancel"] = {"click": k.get("ok"), "geo": [bool(g), s], "pending": coop(h).get("pendingHostSaveName")}
    if not (k.get("ok") and g):
        raise Stop("CANCEL: %s, host stack %s" % (js(k), stack(h)))
def hclick(r, x, need50=True):
    """HCLICK = CAP click_marker on the partner base ("ClientBase"); the host's top CoopState 50 within W_CLICK50"""
    h = x.host
    ck = click_marker(h, x.hsc, x.cbpos[0], x.cbpos[1], x.CB)
    x.t_click = time.time()
    v50, s50 = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 50, W_CLICK50, 0.05)
    r.ev["click"] = {"targets": ck.get("targets"), "pick": (ck.get("pick") or {}).get("ok"), "coop50": [bool(v50), s50]}
    if need50 and not ((ck.get("pick") or {}).get("ok") and v50):
        raise Stop("HCLICK: %s, host top %s dlg %s" % (js(r.ev["click"]), top(h), js(dlg(h))))
def release(r, x):
    """RELEASE = the host's hold_blob_ack {on: false}"""
    rl = q(x.host, {"cmd": "hold_blob_ack", "on": False})
    x.t_rel = time.time()
    r.ev["release"] = pick(rl, ("ok", "armed", "sent"))
def copy_wait(r, x):
    """COPY = the host's copy present with fnv != PRE_C within W_COPY"""
    cp, s = wait(lambda: (lambda c: c if c.get("present") and c.get("fnv1a64") not in (None, "", x.PRE_C) else None)(copyq(x.host)), W_COPY, 0.05)
    x.copy = bool(cp)
    r.ev["copy"] = {"ok": x.copy, "s": s, "end": cp or copyq(x.host)}
def view_wait(r, x, t_from):
    """VIEW = the host's top BasescapeState within W_VIEW of t_from (the time recorded)"""
    v, s = wait(lambda: top(x.host) == "BasescapeState", max(0.0, W_VIEW - (time.time() - t_from)), 0.05)
    x.view = bool(v)
    r.ev["view"] = {"ok": x.view, "s": round(time.time() - t_from, 2), "stack": stack(x.host)}
def watch_end(r, x):
    """WATCH = W_HOLD s every 0.25 s (alive both; both tops and dialog codes; the host's CoopState 50 count and insideCoopBase); LEAVE (if
    VIEW: the host's real GEOSCAPE, a clean geoscape, insideCoopBase false); END = the needles since SAVE, the crash census"""
    h, c = x.host, x.client
    x.watch, t1 = [], time.time()
    while time.time() - t1 < W_HOLD:
        e = {"t": round(time.time() - t1, 2), "ha": alive(h), "ca": alive(c)}
        if e["ha"]:
            e["hs"] = stack(h)
            e["hc"] = dlg(h).get("code") if e["hs"][-1:] == ["CoopState"] else None
            e["h50"] = ncode(h, 50)
            e["hin"] = coop(h).get("insideCoopBase")
        if e["ca"]:
            e["ct"] = top(c)
            e["cc"] = dlg(c).get("code") if e["ct"] == "CoopState" else None
        x.watch.append(e)
        time.sleep(0.25)
    if x.view:
        lv = real_click(h, "GEOSCAPE", W_UI)
        g, s = wait(lambda: geo_clean(h) and coop(h).get("insideCoopBase") is False, W_LEAVE, 0.05)
        x.leave = bool(lv.get("ok") and g)
        r.ev["leave"] = {"click": lv.get("ok"), "clean": [bool(g), s]}
    x.alive = [alive(h), alive(c)]
    x.newCrash = [os.path.basename(p) for p in sorted(crashes() - x.crB)]
    x.n = {k: count(h, x.nh, k) if k in HOST_NEEDLES else count(c, x.nc, k) for k in NEEDLES}
    ch = []
    for e in x.watch:
        k = [e["ha"], e.get("hs", [])[-3:], e.get("hc"), e.get("h50"), e.get("hin"), e["ca"], e.get("ct"), e.get("cc")]
        if not ch or ch[-1][1:] != k:
            ch.append([e["t"]] + k)
    r.ev["END"] = {"watch": ch, "PRE_C": x.PRE_C, "copy": copyq(h), "needles": x.n, "alive": x.alive, "newCrash": x.newCrash}
def view_cell(r, x, name):
    h50 = [e["t"] for e in x.watch if not e["ha"] or (e.get("h50") or 0) > 0]
    r.cell(name, x.view and not h50 and x.leave, "VIEW %s; host CoopState 50 (or dead) during WATCH at %s; LEAVE %s; WATCH host [alive, stack "
           "tail, code, CoopState 50 count, insideCoopBase, ...] %s (want BasescapeState within %d s, no 50 after it, back to a clean geoscape "
           "with insideCoopBase false)" % (r.ev["view"], h50, r.ev.get("leave"), r.ev["END"]["watch"], W_VIEW))
def copy_cell(r, x, name):
    r.cell(name, x.copy, "host copy %s vs PRE_C %s (want present and changed within %d s)" % (js(r.ev["copy"]), x.PRE_C, W_COPY))

# ----- rows -----
def body_sp(r, x):
    locate(r, x)
    stable(r, x)
    prec(r, x)
    arm(r, x, "save", 2)
    save(r, x)
    held(r, x)
    cancel(r, x)
    hclick(r, x)
    r.cell("SP-pre", True, "guest seated %s, STABLE %s, SAVE 54 %s, HELD %s, CANCEL geoscape %s, HCLICK targets %s picked %s, CoopState 50 %s"
           % (r.ev["seat"]["seated"], r.ev["stable"]["r"], r.ev["save"]["saw54"], r.ev["held"], r.ev["cancel"]["geo"], r.ev["click"]["targets"],
              r.ev["click"]["pick"], r.ev["click"]["coop50"]))
    time.sleep(SETTLE_S)
    release(r, x)
    copy_wait(r, x)
    view_wait(r, x, x.t_rel)
    watch_end(r, x)
    copy_cell(r, x, "SP-copy")
    view_cell(r, x, "SP-view")
    r.cell("SP-held", x.n["STREAMHOLD"] >= 1 and x.n["EB4REL"] == x.n["STREAMHOLD"],
           "client STREAMHOLD %d, EB4REL %d since SAVE (want >= 1, equal)" % (x.n["STREAMHOLD"], x.n["EB4REL"]))
    r.cell("SP-crash", not x.newCrash and all(x.alive) and x.n["REPLYHOLD"] == 0,
           "new crash files %s, alive (host, client) %s, client REPLYHOLD %d (want none, both, 0)" % (x.newCrash, x.alive, x.n["REPLYHOLD"]))
def body_g(r, x):
    locate(r, x)
    stable(r, x)
    prec(r, x)
    arm(r, x, "save", 2)
    save(r, x)
    held(r, x)
    cancel(r, x)
    r.cell("G-pre", True, "guest seated %s, STABLE %s, SAVE 54 %s, HELD %s, CANCEL geoscape %s"
           % (r.ev["seat"]["seated"], r.ev["stable"]["r"], r.ev["save"]["saw54"], r.ev["held"], r.ev["cancel"]["geo"]))
    release(r, x)
    copy_wait(r, x)
    copy_cell(r, x, "G-copy")
    stable(r, x, "stable2")
    hclick(r, x, need50=False)
    view_wait(r, x, x.t_click)
    watch_end(r, x)
    view_cell(r, x, "G-view")
    r.cell("G-quiet", x.n["STREAMHOLD"] == 0 and x.n["REPLYHOLD"] == 0 and not x.newCrash and all(x.alive),
           "client STREAMHOLD %d, REPLYHOLD %d, new crash files %s, alive %s (want 0, 0, none, both)"
           % (x.n["STREAMHOLD"], x.n["REPLYHOLD"], x.newCrash, x.alive))
def main():
    c0 = cpu()
    print("==== W2-H82 VSP (slot %s, key %s, exe %s) CPU %s ====" % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    Row("R-SP").run(body_sp, "w2h82_sp")
    Row("G").run(body_g, "w2h82_g")
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== W2-H82 VSP: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()),
          flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2

if __name__ == "__main__":
    sys.exit(main())
