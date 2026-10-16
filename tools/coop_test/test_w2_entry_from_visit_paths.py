"""W2-H74 - test_w2_entry_from_visit_paths.py (EFP): a practice screen over the view of the host's base at the host's YES.

Spec: docs rewrite/prompts/w2h74_entry_from_visit.md (f) row P; TASK 0 constants: docs rewrite/w2h74-task0/sa/CONSTANTS.md. Lead L-BH1, ruling
R-BH-2 fix (a) (QH74-1 .. QH74-6 (a), R-H74-1). Lobby key "49298", dirs w2h74_p_*. Row L (the leave in flight) is absent: TASK 0's ONE
T0-L attempt did not reach an adoption under the leave's LoadGameState (QH74-5 (a); CONSTANTS.md T0-L).
Row P (the client views the host's base with the host's Skyranger craft inventory open, a practice battle over the view, when the host presses
    YES): MARKER (the client's buy at its own base), read B, PROMPT, VISIT (a real globe click + the "HostBase" target), open_craft_equipment
    {coop: true} + craft_inventory, read D, YES (set_seed 2, real click; the trace waits for the client's BriefingState BEFORE
    drive_both_to_tactical, R-H21d-S2-T0-1), read E, BATTLE, RETURN (real OKs), read G.
    Cells P-pre, P-entry (guards), P-snap, P-log, P-own, P-flag, P-common (guard).
Red today (R1): P-snap, P-log, P-own, P-flag FAIL (4 of 7); every other cell PASS. Green (G1, spec E1-E2): all 7 cells PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; a precondition miss ends the row (later cells "not reached")
with ONE CAPTURE line; a boot miss fails P-pre with ONE CAPTURE line. Real presses (YES, OK, the globe click); the client stays zero-disk.
WV-D95 (run to completion in the foreground), WV-D99 (one run; exit 0 only when every cell passes, else 2), WV-D100 (no SKIP, no exit 3).
Helpers copied (never imported) from docs rewrite/lbh1-cap/cap.py (as in test_w2_entry_from_visit.py); the practice screen from
test_w2_practice_battle_entry.py's P4."""
import glob, json, os, subprocess, sys, time  # noqa: E401
from types import SimpleNamespace
import harness
import session
from session import battle_state, event_state
from harness import GameClient, make_user_dir

KEY = "49298"
SEED_P = 2
MARKER_ITEM, MARKER_QTY = "STR_SMOKE_GRENADE", 7
ZOOM_MIN, SYM_PLUS = 3, 43
W_UI, W_PROMPT, W_VISIT, W_ENTRY, W_END, W_RET = 10, 120, 60, 25, 60, 15
RC_OK = (0, 3221226505)
FOLLOWUPS = ("CommendationLateState", "CommendationState", "PromotionsState", "CannotReequipState")
NEEDLES = {"UNWIND": "[coop] W2-H74: battle entry from a view of the host's base", "SNAP": "SEPARATE battle-entry own-world snapshot taken"}
CELLS = {"P": ["P-pre", "P-entry", "P-snap", "P-log", "P-own", "P-flag", "P-common"]}
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
def geo(gc):
    """geo_state: funds, expenditureTail, the client's own base CB (coopBase false, no icon) and its MARKER transfers"""
    g = q(gc, {"cmd": "geo_state"})
    bs = g.get("bases") or []
    own = next((b for b in bs if b.get("coopBase") is False and not b.get("coopIcon")), None) or {}
    return {"funds": g.get("funds"), "expTail": g.get("expenditureTail"), "cb": own.get("name"),
            "marker": [[t.get("qty"), t.get("hours")] for t in own.get("transfers") or [] if t.get("rule") == MARKER_ITEM],
            "bases": [[b.get("name"), b.get("coopBase"), b.get("coopIcon")] for b in bs], "error": g.get("error")}
def has_marker(tr): return any(t and t[0] == MARKER_QTY for t in tr or [])
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

# ----- common steps (spec (f)) -----
def marker_b(r, x):
    """MARKER = the client's buy (PurchaseState::btnOkClick); read B: FUNDS_B, EXP_B, CB with the MARKER transfer"""
    c = x.client
    b = q(c, {"cmd": "buy", "item": MARKER_ITEM, "count": MARKER_QTY})
    ok, s = wait(lambda: top(c) == "GeoscapeState", W_UI, 0.05)
    x.nB = len(log(c))
    B = r.ev["B"] = dict(geo(c), buy=pick(b, ("ok", "error")), topS=s)
    x.CB, x.FUNDS_B, x.EXP_B = B["cb"], B["funds"], B["expTail"]
    if not (b.get("ok") and ok and has_marker(B["marker"]) and isinstance(x.FUNDS_B, int) and isinstance(x.EXP_B, int)):
        raise Stop("MARKER / read B: %s" % js(B))
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
def read_d(r, x):
    c = x.client
    D = r.ev["D"] = {"stack": stack(c), "coop": coop(c), "bases": geo(c)["bases"], "hostTop": top(x.host)}
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
def read_e(r, x):
    E = r.ev["E"] = {"sepSnapshot": record(x.client).get("sepSnapshot"), "log": needles(x.client, x.nB)}
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
    """RETURN = the client's real OK and its follow-ups, geo_clean within W_RET, +1.5 s; read G; the host's real OK + drain"""
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
    G = r.ev["G"] = dict(geo(c), inside=coop(c).get("insideCoopBase"), stack=stack(c), branch=rc.get("debriefOkBranch"),
                         sepReturn=pick(rc.get("sepReturn") or {}, ("ownLoaded", "pushed")), ok=ok1.get("ok"), geoClean=[bool(okg), s])
    k = real_click(x.host, "OK", 10)
    r.ev["hostReturn"] = [k.get("ok")] + list(drain_real(x.host))
    return G
def common(r, name, x, ok0=True, extra=""):
    al = [alive(x.host), alive(x.client)]
    rc = r.ev["rc"] = [shut(x.client), shut(x.host)]
    nc = sorted(crashes() - x.crB)
    r.cell(name, ok0 and all(al) and all(v in RC_OK for v in rc) and not nc,
           "%salive (host, client) %s, exit codes (client, host) %s, new crash files %s (want true, %s, none)" % (extra, al, rc, nc, list(RC_OK)))

# ----- rows -----
def body_p(r, x):
    marker_b(r, x)
    prompt(r, x)
    visit(r, x)
    c = x.client
    a = q(c, {"cmd": "open_craft_equipment", "coop": True})
    okc, _ = wait(lambda: "CraftEquipmentState" in stack(c), W_UI, 0.05)
    b = q(c, {"cmd": "craft_inventory"}) if okc else {"error": "no CraftEquipmentState"}
    oki, _ = wait(lambda: top(c) == "InventoryState", W_UI, 0.05)
    r.ev["practice"] = {"open": pick(a, ("ok", "craftId", "error")), "inventory": pick(b, ("ok", "opened", "error")), "top": bool(oki)}
    D = read_d(r, x)
    D["inBattle"] = safe(battle_state, c).get("inBattle")
    r.cell("P-pre", D["stack"][-3:] == ["BasescapeState", "CraftEquipmentState", "InventoryState"] and D["inBattle"] is True
           and D["coop"].get("insideCoopBase") is True and D["bases"] and all(b[1] is True for b in D["bases"]),
           "READ D client stack %s, battle_state.inBattle %s, insideCoopBase %s, live bases %s (want InventoryState over CraftEquipmentState "
           "over BasescapeState, true, true, every coopBase true)" % (D["stack"], D["inBattle"], D["coop"].get("insideCoopBase"), D["bases"]))
    if not r.done["P-pre"]:
        raise Stop("P-pre")
    ok, codes = yes(r, x)
    r.cell("P-entry", ok, "YES trace %s (want both BriefingState within %d s)" % (r.ev["yes"]["trace"], W_ENTRY))
    if not ok:
        raise Stop("P-entry")
    E = read_e(r, x)
    r.cell("P-snap", E["sepSnapshot"] == 1, "READ E battleEnd.sepSnapshot %s (want 1; today 0, F20753)" % E["sepSnapshot"])
    r.cell("P-log", E["log"]["UNWIND"] == 1, "client log since B: UNWIND %d, SNAP %d (want UNWIND 1; today 0)" % (E["log"]["UNWIND"], E["log"]["SNAP"]))
    battle(r, x)
    G = ret(r, x)
    r.cell("P-own", G["cb"] == x.CB and has_marker(G["marker"]) and G["funds"] == x.FUNDS_B and G["expTail"] == x.EXP_B,
           "READ G %s MARKER %s, funds %s, expenditureTail %s (want the MARKER, FUNDS_B %s, EXP_B %s; today the V loss)"
           % (G["cb"], G["marker"], G["funds"], G["expTail"], x.FUNDS_B, x.EXP_B))
    sr = G["sepReturn"]
    r.cell("P-flag", G["inside"] is False and sr.get("pushed") == 1, "READ G insideCoopBase %s, sepReturn %s (want false, pushed 1; today true, 0)"
           % (G["inside"], sr))
    back = G["stack"] == ["GeoscapeState"] and G["branch"] == "campaign-client-separate"
    common(r, "P-common", x, back, "RETURN client stack %s, debriefOkBranch %r (want [GeoscapeState], 'campaign-client-separate'); "
           % (G["stack"], G["branch"]))
def main():
    c0 = cpu()
    print("==== W2-H74 EFP (slot %s, key %s, exe %s) CPU %s ====" % (harness.HARNESS_SLOT, KEY, time.ctime(os.path.getmtime(harness.EXE)), c0), flush=True)
    Row("P").run(body_p, "w2h74_p")
    fails = [n for n, ok in RESULTS if not ok]
    print("\n==== W2-H74 EFP: %d/%d cells PASS, wall %.1f s, CPU %s -> %s ====" % (len(RESULTS) - len(fails), len(RESULTS), time.time() - T0, c0, cpu()),
          flush=True)
    if fails:
        print("FAILING: %s" % fails, flush=True)
    return 0 if not fails else 2

if __name__ == "__main__":
    sys.exit(main())
