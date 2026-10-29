"""test_entry_from_visit.py: a SEPARATE partner pulled into the host's battle while it views the host's base keeps
its own world.

Lobby key "49297", dirs entry_visit_base_*, entry_visit_geoscape_*.
Row base_visit (the client views the host's base when the host presses YES): MARKER (the client's buy at its own
    base), the baseline read, PROMPT (the host's landing prompt), VISIT (a real globe click on the host's base + the
    "HostBase" target), the pre-YES read, YES (set_seed 2, real click), the briefing read at the client's
    BriefingState, BATTLE, RETURN (real OKs), the return read, COPY (the host's copy of the client world, dumped on
    the HOST), SAVE (host quick save).
    Cells base_visit-pre, base_visit-entry (guards), base_visit-snap, base_visit-log, base_visit-marker,
    base_visit-funds, base_visit-exp, base_visit-inside, base_visit-pushed, base_visit-copy, base_visit-save,
    base_visit-return, base_visit-common (guards).
Row own_geoscape (the control: the client on its own geoscape at YES): MARKER, the baseline read, PROMPT, the
    pre-YES read, YES, the briefing read, BATTLE, RETURN, the return read, COPY.
    Cells own_geoscape-pre, own_geoscape-snap, own_geoscape-own, own_geoscape-copy, own_geoscape-common (all guards).
A build in which the partner loses its world at this entry fails base_visit-snap, -log, -marker, -funds, -exp,
-inside, -pushed, -copy and -save (9 of 18) and passes every other cell.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; every row runs after a failure; a
precondition miss ends its row (later cells "not reached") with ONE CAPTURE line; a boot miss fails the row's -pre
cell with ONE CAPTURE line. Real presses (YES, OK, the globe click); the client stays zero-disk. Run to completion in
the foreground; one run, exit 0 only when every cell passes, else 2; no SKIP, no exit 3. The probe helpers are
local copies, never imported."""
import glob, json, os, sys, time  # noqa: E401
from types import SimpleNamespace
import yaml
import harness
import session
from session import battle_state, event_state
from harness import GameClient, make_user_dir

KEY = "49297"
SEED_P = 2
MARKER_ITEM, MARKER_QTY = "STR_SMOKE_GRENADE", 7
ZOOM_MIN, SYM_PLUS = 3, 43
W_UI, W_PROMPT, W_VISIT, W_ENTRY, W_END, W_RET, W_COPY, W_SAVE = 10, 120, 60, 25, 60, 15, 30, 20
RC_OK = (0, 3221226505)
FOLLOWUPS = ("CommendationLateState", "CommendationState", "PromotionsState", "CannotReequipState")
NEEDLES = {"UNWIND": "[coop] battle entry from a view of the host's base", "SNAP": "SEPARATE battle-entry own-world snapshot taken"}
CELLS = {"base_visit": ["base_visit-pre", "base_visit-entry", "base_visit-snap", "base_visit-log", "base_visit-marker",
                        "base_visit-funds", "base_visit-exp", "base_visit-inside", "base_visit-pushed",
                        "base_visit-copy", "base_visit-save", "base_visit-return",
               "base_visit-common"],
         "own_geoscape": ["own_geoscape-pre", "own_geoscape-snap", "own_geoscape-own", "own_geoscape-copy",
                          "own_geoscape-common"]}
CRASH_GLOB = os.path.join(harness.CRASH_DIR, "crash_*")  # this lane's own crash folder
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
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001 - a probe failure is a value
        return {"error": short(e, 200)}
def safe(fn, gc):
    try:
        r = fn(gc)
        return r if isinstance(r, dict) else {}
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
def record(gc):
    r = safe(event_state, gc).get("battleEnd")
    return r if isinstance(r, dict) else {}
def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log") if gc else ""
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if p and os.path.exists(p) else []
def tail(gc, n=40): return [ln.split("\t")[-1][:300] for ln in log(gc)[-n:]]
def needles(gc, n0):
    ls = log(gc)[n0:]
    return {k: sum(1 for ln in ls if v in ln) for k, v in NEEDLES.items()}
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
def geo(gc):
    """geo_state: funds, expenditureTail, the client's own base CB (coopBase false, no icon) and its MARKER transfers"""
    g = q(gc, {"cmd": "geo_state"})
    bs = g.get("bases") or []
    own = next((b for b in bs if b.get("coopBase") is False and not b.get("coopIcon")), None) or {}
    return {"funds": g.get("funds"), "expTail": g.get("expenditureTail"), "cb": own.get("name"),
            "marker": [[t.get("qty"), t.get("hours")] for t in own.get("transfers") or [] if t.get("rule") == MARKER_ITEM],
            "bases": [[b.get("name"), b.get("coopBase"), b.get("coopIcon")] for b in bs], "error": g.get("error")}
def has_marker(tr): return any(t and t[0] == MARKER_QTY for t in tr or [])
def host_copy(h, cb):
    """the HOST's copy of the client world (coop_file_info role host_copy_of_client): CB's MARKER transfers and the last funds entry"""
    r = q(h, {"cmd": "coop_file_info", "role": "host_copy_of_client"})
    out = pick(r, ("key", "present", "fnv1a64", "error"))
    if not r.get("present"):
        return out
    k = r.get("key")
    d = q(h, {"cmd": "dump_coop_file", "key": k})
    hits = [p for p in glob.glob(os.path.join(h.user_dir, "**", k), recursive=True) if os.path.isfile(p)]
    if not (d.get("ok") and hits):
        out["dump"] = [d.get("ok"), d.get("error"), len(hits)]
        return out
    p = max(hits, key=os.path.getmtime)
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            docs = [x for x in yaml.load_all(fh, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) if isinstance(x, dict)]
        w = next((x for x in docs if "bases" in x), {})
        f = w.get("funds")
        out["funds"] = f[-1] if isinstance(f, list) and f else f
        b = next((b for b in w.get("bases") or [] if isinstance(b, dict) and b.get("name") == cb), {})
        out["marker"] = [[t.get("itemQty") or t.get("qty"), t.get("hours")] for t in b.get("transfers") or [] if t.get("itemId") == MARKER_ITEM]
    except Exception as e:  # noqa: BLE001 - a value
        out["parseError"] = short(e, 200)
    finally:
        os.remove(p)
    return out

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
def cw(gc, match, settle=0.8):
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
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
    """VISIT: centre the client's globe on the host base, zoom to ZOOM_MIN by '+' keys, real clicks at its pixel, the "HostBase" target"""
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
def drain_real(gc, timeout=60):
    seen, t0 = [], time.time()
    while time.time() - t0 < timeout:
        t = top(gc) or ""
        if t == "GeoscapeState":
            return True, seen
        if any(n in t for n in ("VoteMenu", "BattlescapeState", "SaveGameState", "LoadGameState")):
            time.sleep(0.25)
            continue
        d = dlg(gc) if "CoopState" in t else {}
        if "CoopState" not in t or (d.get("backVisible") and (d.get("backText") or "").strip().upper() == "OK"):
            if not real_click(gc, "OK", 5).get("ok"):
                q(gc, {"cmd": "dismiss_popup"})
        seen.append([t, d.get("code")])
        time.sleep(0.5)
    return False, seen

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
    return hb["name"], cid
def boot(x, tag):
    x.host = GameClient("host", None, make_user_dir(tag + "_host"))
    x.client = GameClient("client", None, make_user_dir(tag + "_client"))
    x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()  # noqa: E702
    x.HB, x.cid = seat_guest(x.host, x.client, x.ev)
    time.sleep(2.0)
    session.drain_host_coop_notice(x.host)
    hb = next(b for b in q(x.host, {"cmd": "geo_state"})["bases"] if b.get("name") == x.HB and not b.get("coopIcon"))
    x.hbpos = [hb["lon"], hb["lat"]]
    x.sc = affine(cw(x.client, "INTERCEPT"), cw(x.client, "CANCEL"))
def shut(gc):
    try:
        if alive(gc):
            gc.shutdown(expected_returncodes=RC_OK)
        return gc.proc.poll() if gc and gc.proc else None
    except Exception as e:  # noqa: BLE001 - a failed shutdown is a value (the -common cells)
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
            d[n] = ({"alive": True, "stack": stack(gc), "dlg": dlg(gc), "coop": coop(gc), "geo": geo(gc), "battleEnd": record(gc), "log": tail(gc)}
                    if alive(gc) else {"alive": False, "log": tail(gc) if gc else []})
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
            if "rc" not in self.ev:
                self.ev["rc"] = [shut(x.client), shut(x.host)]
        for n in self.cells:
            if n not in self.done:
                self.cell(n, False, "not reached: %s" % why)
        self.ev["wall"] = round(time.time() - x.t0, 1)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        bad = [n for n in self.cells if not self.done.get(n)]
        print("ROW %s: %s" % (self.rid, "PASS" if not bad else "FAIL (%d failing: %s)" % (len(bad), bad)), flush=True)

# ----- common steps -----
def marker_baseline(r, x):
    """MARKER = the client's buy (PurchaseState::btnOkClick); the baseline read: FUNDS_BEFORE, EXP_BEFORE, CB with the
    MARKER transfer"""
    c = x.client
    b = q(c, {"cmd": "buy", "item": MARKER_ITEM, "count": MARKER_QTY})
    ok, s = wait(lambda: top(c) == "GeoscapeState", W_UI, 0.05)
    x.nBase = len(log(c))
    B = r.ev["baselineRead"] = dict(geo(c), buy=pick(b, ("ok", "error")), topS=s)
    x.CB, x.FUNDS_BEFORE, x.EXP_BEFORE = B["cb"], B["funds"], B["expTail"]
    if not (b.get("ok") and ok and has_marker(B["marker"]) and isinstance(x.FUNDS_BEFORE, int)
            and isinstance(x.EXP_BEFORE, int)):
        raise Stop("MARKER / baseline read: %s" % js(B))
def prompt(r, x):
    """PROMPT = a terror site (spawn_mission_site at the host base +0.35 / +0.10), craft_force, ConfirmLandingState on
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
    h.wait_for("host landing prompt", landing, timeout=W_PROMPT, interval=0.5)
    r.ev["promptS"] = round(time.time() - t, 2)
    time.sleep(1.0)
def visit(r, x):
    c = x.client
    r.ev["click"] = click_marker(c, x.sc, x.hbpos[0], x.hbpos[1], x.HB)
    v, s = wait(lambda: coop(c).get("insideCoopBase") is True and top(c) == "BasescapeState", W_VISIT)
    r.ev["visitS"] = s
    if not v:
        raise Stop("VISIT: the client not in the host's base within %d s" % W_VISIT)
    time.sleep(1.0)
def read_pre_yes(r, x):
    c = x.client
    D = r.ev["preYesRead"] = {"stack": stack(c), "coop": coop(c), "bases": geo(c)["bases"], "hostTop": top(x.host)}
    return D
def yes(r, x):
    """YES = the host's set_seed SEED_P and real YES; the trace (client top, code, insideCoopBase, host top) to both BriefingState"""
    h, c = x.host, x.client
    sd = q(h, {"cmd": "set_seed", "seed": SEED_P})
    if not session.has_state(h, "ConfirmLandingState"):
        raise Stop("YES: no ConfirmLandingState on the host")
    k = real_click(h, "YES", 10)
    trace, last, t1 = [], None, time.time()
    while time.time() - t1 < W_ENTRY:
        tc = top(c)
        e = (tc, dlg(c).get("code") if tc == "CoopState" else None, coop(c).get("insideCoopBase"), top(h))
        if e != last:
            trace.append((round(time.time() - t1, 2),) + e)
            last = e
        if "BriefingState" in (e[0] or "") and "BriefingState" in (e[3] or ""):
            break
        time.sleep(0.05)
    ok = bool(last and "BriefingState" in (last[0] or "") and "BriefingState" in (last[3] or ""))
    r.ev["yes"] = {"seed": sd.get("ok"), "click": k, "trace": trace}
    return ok, [t[2] for t in trace if t[2] is not None]
def read_briefing(r, x):
    E = r.ev["briefingRead"] = {"sepSnapshot": record(x.client).get("sepSnapshot"), "log": needles(x.client, x.nBase)}
    return E
def battle(r, x):
    """BATTLE = drive_both_to_tactical, kill_unit_real faction 1, settle, END TURN both, both DebriefingState"""
    h, c = x.host, x.client
    if not session.drive_both_to_tactical(h, c):
        raise Stop("BATTLE: drive_both_to_tactical timed out (host %s, client %s)" % (stack(h)[-2:], stack(c)[-2:]))
    k = q(h, {"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    wait(lambda: (lambda b: not b.get("isBusy") and b.get("pendingStates") == 0)(safe(battle_state, h)), 45)
    time.sleep(2.0)
    q(c, {"cmd": "battle_action", "action": "end_turn_button"})
    wait(lambda: safe(battle_state, h).get("coopEndTurnText") == "END TURN 1/2", 20)
    q(h, {"cmd": "battle_action", "action": "end_turn_button"})
    wait(lambda: "NextTurnState" in (q(h, {"cmd": "list_widgets"}).get("state") or "") or any("DebriefingState" in s for s in stack(h)), W_END)
    if not any("DebriefingState" in s for s in stack(h)):
        q(h, {"cmd": "dismiss_popup"})
    okh, sh = wait(lambda: "DebriefingState" in stack(h), W_END)
    okc, sc = wait(lambda: top(c) == "DebriefingState", W_END)
    r.ev["battle"] = {"killed": len(k.get("killed") or []), "debrief": [sh, sc]}
    if not (okh and okc):
        raise Stop("BATTLE: debriefing not reached within %d s (host %s, client %s)" % (W_END, stack(h), stack(c)))
def ret(r, x):
    """RETURN = the client's real OK and its follow-ups, geo_clean within W_RET, +1.5 s; the return read; the host's
    real OK + drain"""
    c = x.client
    ok1 = real_click(c, "OK", 10)
    wait(lambda: (lambda st: st[:1] == ["GeoscapeState"] and all(s in FOLLOWUPS for s in st[1:]))(stack(c)), 10, 0.05)
    t0 = time.time()
    while top(c) in FOLLOWUPS and time.time() - t0 < 15:
        real_click(c, "OK", 5)
        time.sleep(0.4)
    okg, s = wait(lambda: geo_clean(c), W_RET, 0.05)
    time.sleep(1.5)
    rc = record(c)
    G = r.ev["returnRead"] = dict(geo(c), inside=coop(c).get("insideCoopBase"), stack=stack(c),
                                  branch=rc.get("debriefOkBranch"),
                         sepReturn=pick(rc.get("sepReturn") or {}, ("ownLoaded", "pushed")), ok=ok1.get("ok"), geoClean=[bool(okg), s])
    k = real_click(x.host, "OK", 10)
    r.ev["hostReturn"] = [k.get("ok")] + list(drain_real(x.host))
    return G
def copy(r, x):
    """COPY = the host's copy of the client world, polled every 0.5 s until it holds the MARKER or W_COPY ends"""
    t0, n, hc = time.time(), 0, {}
    while time.time() - t0 < W_COPY:
        hc = host_copy(x.host, x.CB)
        n += 1
        if has_marker(hc.get("marker")):
            break
        time.sleep(0.5)
    r.ev["COPY"] = dict(hc, s=round(time.time() - t0, 2), polls=n)
    return hc
def save(r, x):
    """SAVE = the host's quick save; client CoopState codes every 0.1 s (its visible OK pressed once per code) until the host's save ended:
    the host stack left [GeoscapeState] (or its copy changed) and is back on [GeoscapeState]; W_SAVE"""
    h, c = x.host, x.client
    f0 = q(h, {"cmd": "coop_file_info", "role": "host_copy_of_client"}).get("fnv1a64")
    rq = q(h, {"cmd": "save_game_ui", "type": "quick"})
    trace, last, pressed, codes, began, ended, t2 = [], None, [], [], False, None, time.time()
    while time.time() - t2 < W_SAVE:
        tc, hs = top(c), stack(h)
        d = dlg(c) if tc == "CoopState" else {}
        if d.get("code") is not None and d.get("code") not in codes:
            codes.append(d.get("code"))
        e = (tc, d.get("code"), hs)
        if e != last:
            trace.append((round(time.time() - t2, 2),) + e)
            last = e
        began = began or hs != ["GeoscapeState"]
        if tc == "CoopState" and d.get("backVisible") and (d.get("backText") or "").strip().upper() == "OK" and d.get("code") not in pressed:
            pressed.append(d.get("code"))
            real_click(c, "OK", 5)
        if hs == ["GeoscapeState"] and (began or q(h, {"cmd": "coop_file_info", "role": "host_copy_of_client"}).get("fnv1a64") != f0):
            ended = round(time.time() - t2, 2)
            break
        time.sleep(0.1)
    S = r.ev["SAVE"] = {"req": pick(rq, ("ok", "error")), "trace": trace, "codes": codes, "pressed": pressed, "ended": ended}
    return S
def common(r, name, x, ok0=True, extra=""):
    al = [alive(x.host), alive(x.client)]
    rc = r.ev["rc"] = [shut(x.client), shut(x.host)]
    nc = sorted(crashes() - x.crB)
    r.cell(name, ok0 and all(al) and all(v in RC_OK for v in rc) and not nc,
           "%salive (host, client) %s, exit codes (client, host) %s, new crash files %s (want true, %s, none)" % (extra, al, rc, nc, list(RC_OK)))

# ----- rows -----
def body_base_visit(r, x):
    marker_baseline(r, x)
    prompt(r, x)
    visit(r, x)
    D = read_pre_yes(r, x)
    r.cell("base_visit-pre", D["stack"][-1:] == ["BasescapeState"] and D["coop"].get("insideCoopBase") is True
           and D["bases"]
           and all(b[1] is True for b in D["bases"]) and D["hostTop"] == "ConfirmLandingState",
           "pre-YES read client top %s, insideCoopBase %s, live bases %s; host top %s (want BasescapeState, true, "
           "every coopBase true, "
           "ConfirmLandingState)" % (D["stack"][-1:], D["coop"].get("insideCoopBase"), D["bases"], D["hostTop"]))
    if not r.done["base_visit-pre"]:
        raise Stop("base_visit-pre")
    ok, codes = yes(r, x)
    r.cell("base_visit-entry", ok and not codes, "YES trace %s; client CoopState codes %s (want both BriefingState "
           "within %d s, none)"
           % (r.ev["yes"]["trace"], codes, W_ENTRY))
    if not ok:
        raise Stop("base_visit-entry")
    E = read_briefing(r, x)
    r.cell("base_visit-snap", E["sepSnapshot"] == 1, "briefing read battleEnd.sepSnapshot %s (want 1)"
           % E["sepSnapshot"])
    r.cell("base_visit-log", E["log"]["UNWIND"] == 1 and E["log"]["SNAP"] == 1, "client log since the baseline read: "
           "UNWIND %d, SNAP %d (want 1, 1)"
           % (E["log"]["UNWIND"], E["log"]["SNAP"]))
    battle(r, x)
    G = ret(r, x)
    r.cell("base_visit-return", G["stack"] == ["GeoscapeState"] and G["branch"] == "campaign-client-separate",
           "RETURN client stack %s, debriefOkBranch %r (want [GeoscapeState], 'campaign-client-separate')" % (G["stack"], G["branch"]))
    if not r.done["base_visit-return"]:
        raise Stop("base_visit-return")
    r.cell("base_visit-marker", G["cb"] == x.CB and has_marker(G["marker"]), "return read %s MARKER transfers %s (want "
           "%s qty %d at %s)"
           % (G["cb"], G["marker"], MARKER_ITEM, MARKER_QTY, x.CB))
    r.cell("base_visit-funds", G["funds"] == x.FUNDS_BEFORE, "return read funds %s (want FUNDS_BEFORE %s; delta %s)"
           % (G["funds"], x.FUNDS_BEFORE, (G["funds"] or 0) - x.FUNDS_BEFORE))
    r.cell("base_visit-exp", G["expTail"] == x.EXP_BEFORE, "return read expenditureTail %s (want EXP_BEFORE %s)"
           % (G["expTail"], x.EXP_BEFORE))
    r.cell("base_visit-inside", G["inside"] is False, "return read insideCoopBase %s (want false)" % G["inside"])
    sr = G["sepReturn"]
    r.cell("base_visit-pushed", sr.get("pushed") == 1 and sr.get("ownLoaded") == 1, "return read sepReturn %s (want "
           "pushed 1, ownLoaded 1)" % sr)
    hc = copy(r, x)
    r.cell("base_visit-copy", has_marker(hc.get("marker")) and hc.get("funds") == x.FUNDS_BEFORE,
           "COPY host copy %s MARKER %s, funds %s after %.1f s (want the MARKER, FUNDS_BEFORE %s within %d s; a stale "
           "copy holds the base-naming world)"
           % (x.CB, hc.get("marker"), hc.get("funds"), r.ev["COPY"]["s"], x.FUNDS_BEFORE, W_COPY))
    S = save(r, x)
    r.cell("base_visit-save", 67 not in S["codes"] and S["ended"] is not None,
           "SAVE client CoopState codes %s, the host's save ended at %s s (want no 67, ended within %d s)"
           % (S["codes"], S["ended"], W_SAVE))
    common(r, "base_visit-common", x)
def body_own_geoscape(r, x):
    marker_baseline(r, x)
    prompt(r, x)
    D = read_pre_yes(r, x)
    r.cell("own_geoscape-pre", D["stack"][-1:] == ["GeoscapeState"] and D["coop"].get("insideCoopBase") is False
           and D["hostTop"] == "ConfirmLandingState",
           "pre-YES read client top %s, insideCoopBase %s; host top %s (want GeoscapeState, false, ConfirmLandingState)"
           % (D["stack"][-1:], D["coop"].get("insideCoopBase"), D["hostTop"]))
    if not r.done["own_geoscape-pre"]:
        raise Stop("own_geoscape-pre")
    ok, codes = yes(r, x)
    if not ok:
        raise Stop("own_geoscape entry: both BriefingState not reached within %d s: %s"
                   % (W_ENTRY, r.ev["yes"]["trace"]))
    E = read_briefing(r, x)
    r.cell("own_geoscape-snap", E["sepSnapshot"] == 1 and E["log"]["SNAP"] == 1 and E["log"]["UNWIND"] == 0,
           "briefing read sepSnapshot %s; client log since the baseline read: SNAP %d, UNWIND %d (want 1; 1, 0)"
           % (E["sepSnapshot"], E["log"]["SNAP"], E["log"]["UNWIND"]))
    battle(r, x)
    G = ret(r, x)
    if G["stack"] != ["GeoscapeState"]:
        raise Stop("own_geoscape RETURN: client stack %s, branch %r" % (G["stack"], G["branch"]))
    sr = G["sepReturn"]
    r.cell("own_geoscape-own", G["cb"] == x.CB and has_marker(G["marker"]) and G["funds"] == x.FUNDS_BEFORE
           and G["expTail"] == x.EXP_BEFORE and G["inside"] is False
           and sr.get("pushed") == 1, "return read %s MARKER %s, funds %s, expenditureTail %s, insideCoopBase %s, "
           "pushed %s (want the MARKER, %s, %s, "
           "false, 1)"
           % (G["cb"], G["marker"], G["funds"], G["expTail"], G["inside"], sr.get("pushed"), x.FUNDS_BEFORE,
              x.EXP_BEFORE))
    hc = copy(r, x)
    r.cell("own_geoscape-copy", has_marker(hc.get("marker")), "COPY host copy %s MARKER %s after %.1f s (want the "
           "MARKER within %d s)"
           % (x.CB, hc.get("marker"), r.ev["COPY"]["s"], W_COPY))
    common(r, "own_geoscape-common", x, ok, "both BriefingState within %d s %s; " % (W_ENTRY, ok))
def main():
    c0 = cpu()
    print("==== test_entry_from_visit (slot %s, key %s, exe %s) CPU %s ===="
          % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    Row("base_visit").run(body_base_visit, "entry_visit_base")
    Row("own_geoscape").run(body_own_geoscape, "entry_visit_geoscape")
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== test_entry_from_visit: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ===="
          % (len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()),
          flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2

if __name__ == "__main__":
    sys.exit(main())
