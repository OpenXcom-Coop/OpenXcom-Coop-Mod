"""W2-H80 S-A LBG (tools/coop_test/test_lost_base_ghost.py): a base the host loses in a base defence leaves a marker of itself on the
host's globe, and clicking it opens the partner's base (lead L-BH2, ruling R-LBH2-1, veto line VL-H80-1; capture lbh2-cap F21826-F21830).
Spec docs rewrite/prompts/w2h80_lost_base_ghost.md (f) LBG; TASK 0 values in rewrite/w2h80-task0/sa/CONSTANTS.md.
In a SEPARATE campaign the host owns HB (garrisoned, its first base) and SPARE; a base defence on HB pulls the client in; the host aborts; the
host's debriefing erases HB and sends nothing. The HOST presses OK first; its geoscape init asks the client for its bases while the client is
still on its display-only debriefing in the battle world (the host's world), which answers [HB, SPARE]; W2-H62 EB1 drops SPARE, not HB, so
the host builds a partner-style marker of its own lost base. Green (E1, TCP): the client does not answer while its live world is the SEPARATE
battle world (`[coop] baseRequest not answered ...`).
ONE boot (key KEY, dirs w2h80_g_*). Bring-up: spawn + connect both; session.new_campaign (HB at HOST_POS); geo.slow_clock; geo.drain_popups;
the window mapping per machine from INTERCEPT + CANCEL (real clicks). SPARE: BASES, BUILD NEW BASE, one globe click at PICK, OK, the name keys,
OK, LIFTS, GEOSCAPE (real clicks). P0: client INTERCEPT + CANCEL, 3 s: host own [HB, SPARE], host mirrors [CB], client mirrors {HB, SPARE}.
D-mark; spawn_ufo; trigger_base_defense (HB: the first own base); briefing OK clicks, the host's pre-battle battle_inventory ok (lever),
NextTurnState clicks; abort (battle_action abort, dismiss_popup on AbortMissionState, session.abort_vote_yes: levers); both DebriefingState;
HOST OK (real clicks to GeoscapeState); OK_GAP_S; CLIENT OK; A0 both GeoscapeState; A1 client INTERCEPT + CANCEL + RT_SETTLE; A1h the same
on the host; A2 >= PLUS10_S after A0. GHOST(host) = host mirrors with id LOST or within POS_TOL of LOST_POS.
  Row R1  R1-pre (GUARD) the construction above reached A0 (P0, the trigger names HB, host BattlescapeState + client phase Active, both
          DebriefingState, LOST gone from the host's own list at HOST_BACK, the client still on DebriefingState after OK_GAP_S, the client's
          RETURN line, both GeoscapeState at A0).  R1-A0 (RED) GHOST(host) empty at A0.  R1-RT (RED) GHOST(host) empty at A1h.
          R1-10 (RED) GHOST(host) empty at A2.  R1-cb (GUARD) CB in the host's mirrors at A0, A1h, A2.  R1-skip (RED) the client's SKIP
          lines between D-mark and A0 >= 1.  R1-own (GUARD) the client's SKIP lines between A0 and A2 == 0.
  Row R2  R2-open (RED) no ghost to click at A2, or the host's click on it (right-click centre, ZOOM_MIN, click) opens no BasescapeState
          within W_OPEN (today: BasescapeState of the client's world, selectedBase = CB's name).
  Row R3  R3-mir (GUARD) the client's mirror ids == [SPARE] at A0, A1, A1h and A2.
  END     CRASH (GUARD): no new crash file in the lane's crash folder since the file start; both processes alive until their shutdown.
Red today: R1-A0, R1-RT, R1-10, R1-skip, R2-open FAIL; the other 5 PASS. Green (E1): all 10 PASS.
Every press is a real click_widget or inject_input except the logged levers named above. One EVIDENCE line per row, one PASS / FAIL line per
cell, then the row verdict; a precondition miss ends its row (CAPTURE line, later cells "not reached"); a boot miss fails R1-pre with ONE
CAPTURE line. ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_lost_base_ghost.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo, harness, session  # noqa: E401,E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49492"                               # lobby key (CONSTANTS.md; 0 hits in src + tools at 4aaaff0c0)
HOST_POS = (0.90, -0.60)                    # rad: HB; SPARE is picked >= 0.15 rad away on land
SPARE_NAME = "spare"
LIFTS = ((2, 2), (3, 2), (2, 3), (3, 3))    # the lift tile, then its replacement tiles in row order
OK_GAP_S, RT_SETTLE, PLUS10_S, W_OPEN, POS_TOL = 2.0, 3.0, 10.0, 30.0, 1e-4
BOOT_S, W_BATTLE, W_DEBRIEF = 240.0, 180.0, 150.0
ZOOM_MIN, SYM_PLUS, SYM_ESC = 3, 43, 27
UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
       "race": "STR_SECTOID", "trajectory": "P0", "state": "flying"}
SKIP_N = "[coop] baseRequest not answered - the live world is the SEPARATE battle world"   # E1 (client)
EB1_N = "[coop] coopBase3 marker"                                                       # host, EVIDENCE only
RETURN_N = "SEPARATE return - own world loaded"                                                      # client
NEEDLES = ("baseRequest not answered", "coopBase3 marker", "coop-ui] push", "coop-ui] pop", "[coop-session]", "coop-debrief")
ROWS = (("R1", ("R1-pre", "R1-A0", "R1-RT", "R1-10", "R1-cb", "R1-skip", "R1-own")), ("R2", ("R2-open",)), ("R3", ("R3-mir",)),
        ("END", ("CRASH",)))
RED = ("R1-A0", "R1-RT", "R1-10", "R1-skip", "R2-open")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]

class Stop(Exception):  # a precondition missed: the row ends here (capture=False: an earlier row's miss, no second CAPTURE)
    def __init__(self, what, capture=True):
        Exception.__init__(self, what)
        self.capture = capture

# ----- probes and real input (copied from the capture rewrite/lbh2-cap/cap.py, never imported) -----
def js(v): return json.dumps(v, sort_keys=True, default=str)
def now(): return round(time.time() - T0[0], 2)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "**", "crash_*"), recursive=True))
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
    return {k: r.get(k) for k in ("code", "title", "backText", "backVisible", "error") if k in r}
def bphase(gc):
    r = q(gc, {"cmd": "battle_state"})
    return {"phase": r.get("phase"), "inBattle": r.get("inBattle"), "missionType": r.get("missionType")}
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon", 0), 5),
           round(b.get("lat", 0), 5)] for b in g.get("bases", [])]
    return {"t": now(), "bases": bl, "stack": stk(gc), "selectedBase": g.get("selectedBase"), "error": g.get("error")}
def own(c): return [[b[0], b[1]] for b in c["bases"] if not b[2] and not b[3]]
def mirrors(c): return [[b[0], b[1], b[4], b[5]] for b in c["bases"] if b[2]]
def mir_ids(c): return [m[0] for m in mirrors(c)]
def ghost(c, st):
    return [m for m in mirrors(c) if m[0] == st["lost"] or (abs(m[2] - st["lostPos"][0]) <= POS_TOL and abs(m[3] - st["lostPos"][1]) <= POS_TOL)]
def cpu():
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def lines_since(gc, n0): return [ln.split("\t")[0][-13:-1] + " " + ln.split("\t")[-1][:200] for ln in logl(gc)[n0:] if any(n in ln for n in NEEDLES)]
def hits(gc, needle, n0, n1=None):
    """the log lines holding `needle` in [n0, n1): [line index, time hh-mm-ss.mmm, text]"""
    return [[i, ln.split("\t")[0][-13:-1], ln.split("\t")[-1][:120]] for i, ln in enumerate(logl(gc)[n0:n1], n0) if needle in ln]
def cw(gc, match, settle=1.0, ready=False):
    if ready:  # a POPUP window (InterceptState) drops a click on a hidden button
        session.wait_widget_ready(gc, match)
    r = q(gc, {"cmd": "click_widget", "match": match})
    time.sleep(settle)
    return {"match": match, "ok": r.get("ok"), "err": r.get("error"), "base": [r.get("baseX"), r.get("baseY")],
            "win": [r.get("winX"), r.get("winY")], "after": stk(gc)}
def affine(r1, r2):
    out = [(r1["win"][i] - r2["win"][i]) / (r1["base"][i] - r2["base"][i]) if r1["base"][i] != r2["base"][i] else None for i in (0, 1)]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["win"][0] - sc * r1["base"][0], sc, r1["win"][1] - sc * r1["base"][1])
def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})
def click_px(gc, bx, by, sc, until_not, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    """real clicks at base pixel (bx, by) + offsets through the window mapping until the top leaves `until_not`"""
    tries = []
    for dx, dy in offsets:
        wx, wy = int(round(sc[0] * (bx + dx) + sc[1])), int(round(sc[2] * (by + dy) + sc[3]))
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        seen, t4 = [], time.time()
        while time.time() - t4 < 1.0:
            t = top(gc)
            e = [t] + ([dlg(gc).get("code")] if t == "CoopState" else [])
            if not seen or seen[-1] != e:
                seen.append(e)
            time.sleep(0.05)
        tries.append({"base": [bx + dx, by + dy], "win": [wx, wy], "seen": seen, "top": top(gc)})
        if tries[-1]["top"] != until_not:
            break
    return tries
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def pick_point(gc, avoid):
    """PICK: land >= 0.15 rad from every base / marker; rings 0.20-0.50 rad around the first base, 16 directions; 8 neighbours land"""
    c = avoid[0]
    for r in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        for k in range(16):
            p = (c[0] + r * math.cos(2 * math.pi * k / 16), c[1] + r * math.sin(2 * math.pi * k / 16))
            if any(dist(p, b) < 0.15 for b in avoid):
                continue
            pr = globe(gc, lon=p[0], lat=p[1])
            if not pr.get("land"):
                continue
            nb = [globe(gc, lon=p[0] + dx, lat=p[1] + dy).get("land") for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02)]
            if all(nb) and 10 < pr["x"] < pr["globeW"] - 10 and 30 < pr["y"] < pr["globeH"] - 10:
                return {"lon": p[0], "lat": p[1], "x": pr["x"], "y": pr["y"], "r": r, "k": k}
    return None
def capture(b):
    out = {}
    for gc in (b.host, b.client):
        out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None} if not alive(gc) else {
            "get_state": q(gc, {"cmd": "get_state"}), "get_coop": q(gc, {"cmd": "get_coop"}), "dialog": dlg(gc), "geo_state": census(gc),
            "battle": bphase(gc), "log": [ln.split("\t")[-1][:300] for ln in logl(gc)[-40:]]}
    return out
# ----- the boot and the construction steps -----
class Boot:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h80_g_host"))
        self.client = GameClient("client", None, make_user_dir("w2h80_g_client"))
        self.aff, self.swaps = {}, []
class Row:
    def __init__(self, x, b, rid):
        self.x, self.b, self.rid, self.res = x, b, rid, {}
        self.ev = {"t": now(), "cpu": cpu(), "swaps": []}
        self.n0 = [len(logl(b.host)), len(logl(b.client))] if b is not None else [0, 0]
    def cell(self, cid, ok, label): self.res[cid] = (bool(ok), label)
    def need(self, ok, what, capture=True):
        if not ok: raise Stop(what, capture)  # noqa: E701
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if self.b is not None:
            self.ev["hostLog"], self.ev["clientLog"] = lines_since(self.b.host, self.n0[0]), lines_since(self.b.client, self.n0[1])
        self.ev["stop"] = stop and str(stop)
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails, cells = [], dict(ROWS)[self.rid]
        for cid in cells:
            miss = "precondition miss: %s" % stop if cid == cells[0] and cid.endswith("-pre") else "not reached (%s)" % stop
            ok, label = self.res.get(cid, (False, miss))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "RED" if cid in RED else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop and stop.capture:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.x.fails += fails
def bring_up(b, r):
    for gc in (b.host, b.client):
        gc.spawn()
        gc.connect(timeout=BOOT_S)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    session.new_campaign(b.host, b.client, port=KEY)
    geo.slow_clock(b.host, b.client)
    time.sleep(2.0)
    ev = r.ev["boot"] = {"key": KEY, "slot": harness.HARNESS_SLOT, "drain": [str(geo.drain_popups(gc))[:120] for gc in (b.host, b.client)]}
    for gc in (b.host, b.client):
        b.aff[gc.name] = affine(cw(gc, "INTERCEPT", 0.6), cw(gc, "CANCEL", 0.6, ready=True))
    h, c = census(b.host), census(b.client)
    ev.update({"aff": b.aff, "host": h["bases"], "client": c["bases"], "t": now()})
    r.need(h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"], "boot: both on GeoscapeState (%s, %s)" % (h["stack"], c["stack"]))
def build_base(b, r, gc, name):
    """SPARE: BASES, BUILD NEW BASE, ONE globe click at PICK, OK, NAME (keys), OK, the lift tile, GEOSCAPE (real clicks / keys)"""
    ev = r.ev["spare"] = {"bases": cw(gc, "BASES")["after"], "newBase": cw(gc, "NEW BASE")["after"]}
    r.need(top(gc) == "BuildNewBaseState", "SPARE: %s top %s after BUILD NEW BASE" % (gc.name, top(gc)))
    cc = census(gc)
    ev["pick"] = pick_point(gc, [(x[4], x[5]) for x in cc["bases"] if not x[2]] + [(x[4], x[5]) for x in cc["bases"] if x[2]])
    r.need(ev["pick"], "SPARE: no land point for PICK")
    ev["globeClick"] = click_px(gc, ev["pick"]["x"], ev["pick"]["y"], b.aff[gc.name], "BuildNewBaseState")[-1]
    r.need(top(gc) == "ConfirmNewBaseState", "SPARE: %s top %s after the globe click" % (gc.name, top(gc)))
    ev["confirmOk"] = cw(gc, "OK")["after"]
    r.need(top(gc) == "BaseNameState", "SPARE: %s top %s after confirm OK" % (gc.name, top(gc)))
    for ch in name:
        key(gc, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    ev["nameOk"] = cw(gc, "OK")["after"]
    r.need(top(gc) == "PlaceLiftState", "SPARE: %s top %s after the name's OK" % (gc.name, top(gc)))
    ev["lift"] = []
    for tx, ty in LIFTS:
        ev["lift"].append([tx, ty, click_px(gc, tx * 32 + 16, 8 + ty * 32 + 16, b.aff[gc.name], "PlaceLiftState", offsets=((0, 0),))[-1]["top"]])
        if top(gc) != "PlaceLiftState":
            break
        r.ev["swaps"].append("LIFT (%d, %d) did not leave PlaceLiftState" % (tx, ty))
    r.need(top(gc) != "PlaceLiftState", "SPARE: PlaceLiftState never left (%s)" % ev["lift"])
    ev["geo"] = cw(gc, "GEOSCAPE")["after"]
    r.need(top(gc) == "GeoscapeState", "SPARE: %s not back on GeoscapeState (%s)" % (gc.name, stk(gc)))
    nb = [x for x in own(census(gc)) if x[1] == name]
    r.need(len(nb) == 1, "SPARE: %r not in %s's own list once (%s)" % (name, gc.name, nb))
    return nb[0][0]
def cycle(gc): return [cw(gc, "INTERCEPT")["after"][-1:], cw(gc, "CANCEL", ready=True)["after"][-1:]]
def both(b): return {"host": census(b.host), "client": census(b.client)}
def p0(b, r, st):
    """P0: the client's geoscape init; host own [HB, SPARE], host mirrors [CB], client mirrors {HB, SPARE}; LOST = HB"""
    r.ev["p0Cycle"] = cycle(b.client)
    time.sleep(3.0)
    p = both(b)
    hown, cown = own(p["host"]), own(p["client"])
    hb = [x for x in hown if x[0] != st["spare"]]
    r.ev["P0"] = {"hostOwn": hown, "hostMir": mirrors(p["host"]), "clientOwn": cown, "clientMir": mirrors(p["client"])}
    r.need(len(hown) == 2 and len(hb) == 1 and len(cown) == 1, "P0: host own %s, client own %s" % (hown, cown))
    lb = [x for x in p["host"]["bases"] if x[0] == hb[0][0]][0]
    st.update({"lost": hb[0][0], "lostName": hb[0][1], "lostPos": [lb[4], lb[5]], "cb": cown[0][0], "cbName": cown[0][1]})
    r.ev["ids"] = dict(st)
    r.need(mir_ids(p["host"]) == [st["cb"]] and sorted(mir_ids(p["client"])) == sorted([st["lost"], st["spare"]]),
           "P0: host mirrors %s (want [CB]), client mirrors %s (want {HB, SPARE})" % (mir_ids(p["host"]), mir_ids(p["client"])))
def advance_to_battle(b, r):
    """press the briefing's OK (real click), the pre-battle inventory's OK (battle_inventory lever, logged) and NextTurnState (click)"""
    trace, t1, pressed = [], time.time(), []
    while time.time() - t1 < W_BATTLE:
        row = [round(time.time() - t1, 2)]
        for gc in (b.host, b.client):
            t = top(gc)
            row.append([t] + ([dlg(gc).get("code")] if t == "CoopState" else []) + [bphase(gc).get("phase")])
            if t == "BriefingState":
                if session.wait_widget_ready(gc, "OK", timeout=5) is not None:
                    pressed.append([gc.name, "BriefingState OK", cw(gc, "OK", 0.5)["after"][-1:]])
            elif t == "InventoryState":
                pressed.append([gc.name, "battle_inventory ok (lever)", q(gc, {"cmd": "battle_inventory", "action": "ok"}).get("ok")])
                time.sleep(0.5)
            elif t == "NextTurnState":
                sc = b.aff[gc.name]
                wx, wy = int(round(sc[0] * 160 + sc[1])), int(round(sc[2] * 100 + sc[3]))
                pressed.append([gc.name, "NextTurnState click", q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy}).get("ok")])
                time.sleep(0.6)
        if not trace or trace[-1][1:] != row[1:]:
            trace.append(row)
        if row[1][0] == "BattlescapeState" and row[2][0] == "BattlescapeState":
            break
        time.sleep(0.25)
    r.ev["advance"] = {"trace": trace, "pressed": pressed, "secs": round(time.time() - t1, 2)}
def press_through(gc, cap=90.0):
    """real clicks until GeoscapeState (calm 1 s): an OK screen's 'OK'; a CoopState by its own button"""
    steps, t1 = [], time.time()
    while time.time() - t1 < cap:
        t = top(gc)
        if t == "GeoscapeState":
            time.sleep(1.0)
            if top(gc) == "GeoscapeState":
                break
            continue
        if t in ("LoadGameState", "SaveGameState") or (t or "").startswith("probe failed"):
            time.sleep(0.25)
            continue
        if t == "CoopState":
            d = dlg(gc)
            if d.get("backVisible") and d.get("backText"):
                steps.append([round(time.time() - t1, 2), t, d.get("code"), cw(gc, d["backText"], 0.8)["after"][-2:]])
            else:
                time.sleep(0.25)
                if not steps or steps[-1][1:3] != [t, d.get("code")]:
                    steps.append([round(time.time() - t1, 2), t, d.get("code"), "wait"])
            continue
        w = q(gc, {"cmd": "list_widgets"})
        texts = [x.get("text") for x in w.get("widgets", []) if x.get("visible") and str(x.get("type", "")).endswith("::TextButton")]
        okb = next((m for m in ("OK", "Ok") if any(m.lower() == (tx or "").strip().lower() for tx in texts)), None)
        if okb:
            session.wait_widget_ready(gc, okb, timeout=5)
            steps.append([round(time.time() - t1, 2), t, "OK", cw(gc, okb, 0.8)["after"][-2:]])
        else:
            steps.append([round(time.time() - t1, 2), t, "no OK", texts[:8]])
            time.sleep(1.0)
            if len(steps) > 3 and all(s[1] == t and s[2] == "no OK" for s in steps[-3:]):
                break
    return {"steps": steps, "secs": round(time.time() - t1, 2)}
def abort_host(b, r):
    """the abort (levers): battle_action abort, AbortMissionState, dismiss_popup, session.abort_vote_yes"""
    h = b.host
    ev = r.ev["abort"] = {"abort": q(h, {"cmd": "battle_action", "action": "abort"})}
    t1 = time.time()
    while time.time() - t1 < 30 and not session.has_state(h, "AbortMissionState"):
        time.sleep(0.05)
    r.need(session.has_state(h, "AbortMissionState"), "abort: host AbortMissionState never shown %s" % stk(h))
    ev["confirm"] = q(h, {"cmd": "dismiss_popup"}).get("handled")
    try:
        ev["vote"] = session.abort_vote_yes(h, b.client)
    except Exception as e:  # noqa: BLE001
        ev["vote"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    t1, trace = time.time(), []
    while time.time() - t1 < W_DEBRIEF:
        row = [stk(h)[-2:], stk(b.client)[-2:]]
        if not trace or trace[-1][1:] != row:
            trace.append([round(time.time() - t1, 2)] + row)
        if all("DebriefingState" in x for x in row):
            break
        time.sleep(0.05)
    ev["debrief"] = trace
    r.need(all("DebriefingState" in stk(gc) for gc in (h, b.client)), "abort: both DebriefingState within W_DEBRIEF (%s)" % trace[-1:])
def visit(b, r, m):
    """CLICK: right-click the marker to centre, '+' to ZOOM_MIN, left-click it; MultipleTargetsState -> ESC, '+', re-click (logged);
    trace for W_OPEN what opens; read the open base; close it (its CoopState button, GEOSCAPE, session.wait_back_on_geoscape)"""
    h, sc, (lon, lat) = b.host, b.aff["host"], (m[2], m[3])
    ev = r.ev["click"] = {"marker": m, "g0": globe(h, lon=lon, lat=lat)}
    g = ev["g0"]
    if g.get("ok") and 10 < g["x"] - g["globeX"] < g["globeW"] - 10 and 10 < g["y"] - g["globeY"] < g["globeH"] - 10:
        wx, wy = int(round(sc[0] * g["x"] + sc[1])), int(round(sc[2] * g["y"] + sc[3]))
        ev["right"] = [wx, wy, q(h, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy, "button": "right"}).get("ok")]
        time.sleep(0.8)
    g1 = globe(h)
    if g1.get("cenLon") is None or dist((g1["cenLon"], g1["cenLat"]), (lon, lat)) >= 0.05:
        g1 = globe(h, centerLon=lon, centerLat=lat)
        r.ev["swaps"].append("CLICK: no right-click centre -> view move to (%s, %s)" % (g1.get("cenLon"), g1.get("cenLat")))
    zs = [globe(h).get("zoom")]
    while (zs[-1] or 0) < ZOOM_MIN and len(zs) < 7:
        key(h, SYM_PLUS)
        time.sleep(0.6)
        zs.append(globe(h).get("zoom"))
    g2 = globe(h, lon=lon, lat=lat)
    ev.update({"zooms": zs, "px": [g2.get("x"), g2.get("y")], "tClick": now()})
    ev["tries"] = click_px(h, g2["x"], g2["y"], sc, "GeoscapeState")
    if top(h) == "MultipleTargetsState":
        for k in (SYM_ESC, SYM_PLUS):
            key(h, k)
            time.sleep(0.6)
        g3 = globe(h, lon=lon, lat=lat)
        r.ev["swaps"].append("CLICK: MultipleTargetsState -> ESC, '+' (zoom %s), re-click" % g3.get("zoom"))
        ev["tries"] += click_px(h, g3["x"], g3["y"], sc, "GeoscapeState")
    trace, t1, bs_at = [], time.time(), None
    while time.time() - t1 < W_OPEN + 3.0:
        st = stk(h)
        e = [st[-1] if st else None] + ([dlg(h).get("code")] if st[-1:] == ["CoopState"] else [])
        if not trace or trace[-1][1:] != e:
            trace.append([round(time.time() - t1, 2)] + e)
        if bs_at is None and "BasescapeState" in st:
            bs_at = time.time()
        if (bs_at and time.time() - bs_at >= 3.0) or (bs_at is None and time.time() - t1 >= W_OPEN):
            break
        time.sleep(0.05)
    seen = [x for t in ev["tries"] for x in t["seen"]]
    first = next((x for x in seen if x[0] == "BasescapeState"), None)
    g = census(h)
    ev.update({"trace": trace, "bsAt": round(bs_at - t1, 2) if bs_at else (0.0 if first else None), "open": {
        "stack": g["stack"], "selectedBase": g["selectedBase"], "bases": [x[:4] for x in g["bases"]],
        "insideCoopBase": q(h, {"cmd": "get_coop"}).get("insideCoopBase")}})
    back = ev["back"] = {"close": []}
    while top(h) == "CoopState" and len(back["close"]) < 3:
        d = dlg(h)
        if not d.get("backText"):
            back["close"].append([d, "no button"])
            break
        back["close"].append([d.get("code"), d.get("backText"), cw(h, d["backText"])["after"]])
    if "BasescapeState" in stk(h):
        back["geo"] = cw(h, "GEOSCAPE")["after"]
    try:
        back["back"] = bool(session.wait_back_on_geoscape(h, "host back on its own geoscape"))
    except Exception as e:  # noqa: BLE001
        back["back"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    return ev
# ----- the rows -----
def row_r1(b, r, st):
    """R1: the boot, SPARE, P0, the base defence on HB, the abort, HOST OK, OK_GAP_S, CLIENT OK, A0 / A1 / A1h / A2"""
    h, c, ev = b.host, b.client, r.ev
    bring_up(b, r)
    st["spare"] = build_base(b, r, h, SPARE_NAME)
    p0(b, r, st)
    nh, nc = len(logl(h)), len(logl(c))  # D-mark
    ufo = q(h, UFO)
    tr = ev["trigger"] = {"ufo": ufo, "reply": q(h, {"cmd": "trigger_base_defense", "ufo_id": ufo.get("ufo_id")}), "t": now()}
    r.need(ufo.get("ok") and tr["reply"].get("ok") and tr["reply"].get("base") == st["lostName"],
           "trigger: %s (want ok, base %r)" % (tr, st["lostName"]))
    advance_to_battle(b, r)
    r.need(top(h) == "BattlescapeState" and bphase(c).get("phase") == "Active",
           "battle: host %s, client phase %s (want BattlescapeState, Active)" % (stk(h), bphase(c)))
    abort_host(b, r)
    ho = press_through(h)
    hb = census(h)
    ev["hostBack"] = {"t": now(), "steps": ho, "own": own(hb), "mirrors": mirrors(hb), "stack": hb["stack"]}
    r.need(hb["stack"] == ["GeoscapeState"] and st["lost"] not in [x[0] for x in own(hb)], "HOST_BACK: %s" % ev["hostBack"])
    time.sleep(OK_GAP_S)
    cs = ev["clientAfterGap"] = {"t": now(), "stack": stk(c), "dialog": dlg(c)}
    r.need(cs["stack"][-1:] == ["DebriefingState"], "GAP: the client's top %s after OK_GAP_S (want DebriefingState)" % cs)
    ev["clientOk"] = press_through(c)
    ret = hits(c, RETURN_N, nc)
    st["A0"] = a0 = both(b)
    t_a0, nh0, nc0 = time.time(), len(logl(h)), len(logl(c))
    r.need(ret and a0["host"]["stack"] == ["GeoscapeState"] and a0["client"]["stack"] == ["GeoscapeState"],
           "A0: RETURN %s; stacks %s, %s" % (ret, a0["host"]["stack"], a0["client"]["stack"]))
    r.cell("R1-pre", True, "reached A0: P0 %s; trigger %s; LOST %s gone from the host's own list at HOST_BACK; client on DebriefingState "
                           "after OK_GAP_S; RETURN %s" % (ev["P0"]["hostOwn"], tr["reply"], st["lost"], ret[0][1]))
    ev["cpuA0"] = cpu()
    ev["A1cycle"] = cycle(c)
    time.sleep(RT_SETTLE)
    st["A1"] = both(b)
    ev["A1hcycle"] = cycle(h)
    time.sleep(RT_SETTLE)
    st["A1h"] = both(b)
    while time.time() - t_a0 < PLUS10_S:
        time.sleep(0.25)
    st["A2"] = both(b)
    st["sinceA0"] = since = round(time.time() - t_a0, 2)
    nh2, nc2 = len(logl(h)), len(logl(c))
    gh = {k: ghost(st[k]["host"], st) for k in ("A0", "A1", "A1h", "A2")}
    ev["host"] = {k: [x[:4] for x in st[k]["host"]["bases"]] for k in ("A0", "A1", "A1h", "A2")}
    sk1, sk2 = hits(c, SKIP_N, nc, nc0), hits(c, SKIP_N, nc0, nc2)
    ev["needles"] = {"skipDmarkToA0": sk1, "skipA0toA2": sk2, "skipHost": hits(h, SKIP_N, nh), "eb1": hits(h, EB1_N, nh), "return": ret}
    r.cell("R1-A0", not gh["A0"], "GHOST(host) at A0: %s (want none; LOST %s at %s)" % (gh["A0"], st["lost"], st["lostPos"]))
    r.cell("R1-RT", not gh["A1h"], "GHOST(host) at A1h, after the host's INTERCEPT + CANCEL: %s (want none)" % gh["A1h"])
    r.cell("R1-10", not gh["A2"] and since >= PLUS10_S, "GHOST(host) at A2, %.2f s after A0: %s (want none)" % (since, gh["A2"]))
    cbs = {k: st["cb"] in mir_ids(st[k]["host"]) for k in ("A0", "A1h", "A2")}
    r.cell("R1-cb", all(cbs.values()), "CB %s in the host's mirrors at A0 / A1h / A2: %s" % (st["cb"], cbs))
    r.cell("R1-skip", len(sk1) >= 1, "the client's SKIP lines between D-mark and A0: %d %s (want >= 1)" % (len(sk1), sk1[:3]))
    r.cell("R1-own", not sk2, "the client's SKIP lines between A0 and A2: %d %s (want 0)" % (len(sk2), sk2[:3]))
def row_r2(b, r, st):
    """R2: the host's click on the ghost at A2 (CLICK), if one exists"""
    r.need("A2" in st, "R1 did not reach A2", capture=False)
    g2 = ghost(st["A2"]["host"], st)
    r.ev["ghostA2"] = g2
    if not g2:
        r.cell("R2-open", True, "GHOST(host) empty at A2: nothing to click")
        return
    v = visit(b, r, g2[0])
    r.cell("R2-open", v["bsAt"] is None, "the host's click on ghost %s: BasescapeState at %s s, selectedBase %r, insideCoopBase %s (want no "
                                         "BasescapeState within W_OPEN)" % (g2[0], v["bsAt"], v["open"]["selectedBase"], v["open"]["insideCoopBase"]))
def row_r3(b, r, st):
    """R3: the client's mirrors = the host's surviving bases"""
    r.need(all(k in st for k in ("A0", "A1", "A1h", "A2")), "R1 did not reach A2", capture=False)
    m = r.ev["clientMir"] = {k: mir_ids(st[k]["client"]) for k in ("A0", "A1", "A1h", "A2")}
    r.ev["client"] = {k: [x[:4] for x in st[k]["client"]["bases"]] for k in ("A0", "A1", "A1h", "A2")}
    r.cell("R3-mir", all(v == [st["spare"]] for v in m.values()), "client mirror ids at A0 / A1 / A1h / A2: %s (want [%s] each)" % (m, st["spare"]))
class X:  # the file's run state: failing cells, every process's alive-until-shutdown record
    def __init__(self): self.fails, self.alive = [], []
def main():
    x, crash0, b, st = X(), crashes(), None, {}
    T0[0] = time.time()
    try:
        b = Boot()
        for rid, fn in (("R1", row_r1), ("R2", row_r2), ("R3", row_r3)):
            r = Row(x, b, rid)
            try:
                fn(b, r, st)
                r.finish()
            except Stop as e:
                r.finish(e)
            except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
                r.finish(Stop("exception %s: %s" % (type(e).__name__, str(e)[:300])))
    finally:
        for gc in ((b.client, b.host) if b else ()):
            x.alive.append([gc.name, alive(gc)])
            try:
                if alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
            except Exception as e:  # noqa: BLE001
                print("FAIL shutdown %s: %s" % (gc.name, str(e)[:300]), flush=True)
                x.alive[-1][1] = False
        r, new = Row(x, None, "END"), sorted(crashes() - crash0)
        r.ev.update({"newCrash": [os.path.basename(p) for p in new], "aliveUntilShutdown": x.alive, "crashDir": harness.CRASH_DIR})
        r.cell("CRASH", not new and x.alive and all(a[1] for a in x.alive),
               "new crash files %d %s; alive until shutdown %s" % (len(new), r.ev["newCrash"][:3], x.alive))
        r.finish()
    cl = [cid for _r, cs in ROWS for cid in cs]
    print("SUMMARY W2-H80 S-A LBG: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(x.fails)), len(cl),
                                                                               sorted(set(x.fails)) or "none", now()), flush=True)
    return 0 if not x.fails else 2
if __name__ == "__main__":
    sys.exit(main())
