"""W2-H66 S-B HUN (tools/coop_test/test_w2_hold_until_named.py): a co-op gift or base visit while the partner names a new base
(L-H66-1, ruling R-H66-2, amendment EB4-R ruling R-H66B-2). Spec docs rewrite/prompts/w2h66_sb_hold_until_named.md (f) and AMENDMENT
EB4-R R.4; TASK 0 values in rewrite/w2h66-task0/sb/CONSTANTS.md (boots a, b, a2 red; c, c2 green).
In a SEPARATE campaign, while a player is on BaseNameState its new base sits in its own base list with the name "", so every serialisation
of its world refuses: a host gift makes the partner's push refuse (a "Save failed (MEMORY)" 995 flashes for 0.2 s, the host's copy of its
world stays old), and a visit to its base makes the base answer refuse (the visitor enters at once and sees an OLDER base, the naming
player gets a 995 that stays). The fix holds the push and the base answer until the base is named, then answers once, one stream at a time.
ONE boot pair (key KEY, dirs w2h66b_host / _client): spawn + connect; session.new_campaign (SEPARATE, tcp, host base at HOST_POS);
geo.slow_clock; geo.drain_popups; the window mapping per machine from INTERCEPT + its CANCEL (real clicks). OWNER = the machine that names /
whose base is visited, VISITOR = the other. "FUNDS digits" = the digits of the list_widgets text that starts with "FUNDS>". "Log window" =
the lines of that machine's openxcom.log between two marks. Every row starts with both tops GeoscapeState.
  Row V  (guard) host visits PARTNER_BASE, no naming.
    V-enter host top BasescapeState within ENTER_S of the click.  V-live then its FUNDS digits == the partner's funds.
    V-no995 the partner's log window click -> V-live has no CoopState push.  V-home host GEOSCAPE: GeoscapeState within 5 s, funds == PRE.
  Row G  (C1) partner to BaseNameState; host BASES, SOLDIERS, GIFT_ROW click, GIVE_KEY, the partner's button; partner GiftNoticeState OK,
         names NAME_G.
    G-no995 (RED) partner log RECV -> PlaceLiftState push: no CoopState push.  G-named partner PlaceLiftState within 5 s of the OK.
    G-lands (RED) within LANDS_S of the OK the host copy fnv differs from H0, no host save.  G-calm no CoopState push PlaceLiftState -> +LANDS_S.
  Row P  (C2) partner to BaseNameState; host visits PARTNER_BASE; both polled every POLL for WAIT_S; partner names NAME_P.
    P-wait (RED) host top CoopState 50 at +WAIT_S.  P-no995 (RED) no partner poll saw 995.  P-named partner PlaceLiftState within 5 s.
    P-live (RED) within ENTER_S of the OK host BasescapeState with FUNDS digits == partner funds.  P-home partner lift + GEOSCAPE; host
    GEOSCAPE: GeoscapeState within 5 s, funds == PRE.
  Row H  (C2b) row P with the roles swapped: the host names NAME_H, the partner visits HOST_BASE.  H-wait, H-no995, H-named, H-live, H-home.
  Row Q  (C1 + C2 in one naming) partner to BaseNameState; host gift (BASES, MINI0, SOLDIERS, ...); host visits PARTNER_BASE; WAIT_S polls;
         H1 = host copy fnv; partner names NAME_Q; polled every POLL until T_OK + max(ENTER_S, LANDS_S).
    Q-wait (RED) host CoopState 50 at +WAIT_S.  Q-no995 (RED) partner log RECV -> T_OK + LANDS_S: no CoopState push.  Q-named.
    Q-live (RED) within ENTER_S host BasescapeState, FUNDS digits == partner funds.  Q-lands (RED) within LANDS_S the host copy differs from
    H1, save folder unchanged.  Q-stays host log OK -> T_OK + LANDS_S: no BasescapeState pop.  Q-home as P-home.
  END    CRASH (GUARD) no new crash file in harness.CRASH_DIR since row V, both processes alive until their shutdown.
Red today: the 12 RED cells FAIL, the 14 others PASS. Green (W2-H66 S-B G1: EB1-EB5 with EB4-R): all 26 PASS.
Every press is a real click_widget or inject_input (no gift, visit, leave, dismiss or dialog-back lever). One EVIDENCE line per row, one
PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (later cells "not reached"); a boot miss fails every cell
"boot" with ONE CAPTURE line. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip; exit 0 only when every cell passes, else 2.
Run: python tools/coop_test/test_w2_hold_until_named.py   (OXC_HARNESS_SLOT selects the lane)"""
import glob, json, math, os, re, subprocess, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49237"                               # TASK 0 ran on "49238" (rewrite/w2h66-task0/sb)
HOST_POS = (0.90, -0.60)                    # rad, the capture's host base
MIN_SEP = 0.25                              # rad from every base and marker: four new bases, each visit click hits one marker
RINGS = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60)   # LAND_PICK rings (0.55 / 0.60 = its replacement rule)
NAMES = {"G": "hnewg", "P": "hnewp", "H": "hnewh", "Q": "hnewq"}  # lowercase: inject_input key = unicode sym
LIFT_TILE = (2, 2)                          # BaseView tile: base (80, 88)
GIFT_ROW, GIVE_KEY = (68, 44), 258          # SoldiersState row 0 / Options::giveUnit (SDLK_KP2)
MINI0 = (199, 49)                           # BasescapeState mini base slot 0 (MiniBaseView at (192, 41), 16 px a slot): HOST_BASE
WAIT_S, ENTER_S, LANDS_S, GIFT_S, POLL = 5.0, 10.0, 8.0, 5.0, 0.25
SETTLE, SETTLE_MENU = 0.5, 1.0              # before a click on a state just pushed (TASK 0 F20190: a menu click at +0.05 s was lost)
ROWS = (("V", ("V-enter", "V-live", "V-no995", "V-home")), ("G", ("G-no995", "G-named", "G-lands", "G-calm")),
        ("P", ("P-wait", "P-no995", "P-named", "P-live", "P-home")), ("H", ("H-wait", "H-no995", "H-named", "H-live", "H-home")),
        ("Q", ("Q-wait", "Q-no995", "Q-named", "Q-live", "Q-lands", "Q-stays", "Q-home")), ("END", ("CRASH",)))
RED = ("G-no995", "G-lands", "P-wait", "P-no995", "P-live", "H-wait", "H-no995", "H-live", "Q-wait", "Q-no995", "Q-live", "Q-lands")
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
T0 = [time.time()]

class Stop(Exception):  # a precondition missed: the row ends here
    pass

# ----- probes and real input (copied from docs rewrite/lh66-1-cap/cap.py and test_w2_save_during_naming.py, never imported) -----
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
def code(gc): return dlg(gc).get("code")
def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    bl = [[b.get("coopBaseId"), b.get("name"), bool(b.get("coopIcon")), bool(b.get("coopBase")), round(b.get("lon", 0), 5),
           round(b.get("lat", 0), 5)] for b in g.get("bases", [])]
    return {"bases": bl, "funds": g.get("funds"), "stack": stk(gc), "error": g.get("error")}
def own(c): return [b for b in c["bases"] if not b[2] and not b[3]]
def funds(gc): return q(gc, {"cmd": "geo_state"}).get("funds")
def cpu():
    ps = ("[math]::Round(((Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples | "
          "Measure-Object -Property CookedValue -Average).Average, 1); @(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count")
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout.split()
        return {"t": time.strftime("%H:%M:%S"), "cpu": v[0] if v else None, "wardogs": v[1] if len(v) > 1 else None}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:120]}
def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def short(ln):
    p = ln.split("\t")
    return (p[0][-13:-1] + " " + p[-1])[:220]
NEEDLES = ("[coop-ui] push class OpenXcom::CoopState", "[coop-ui] pop  class OpenXcom::CoopState", "PlaceLiftState", "GiftNoticeState",
           "class OpenXcom::BasescapeState", "[coop-gift]", "[coop-visit]", "[coop-save]", "Save failed")
def win(gc, a, b=None): return [short(x) for x in logl(gc)[a:b] if any(n in x for n in NEEDLES)]
def first_after(gc, a, needle):
    for i, ln in enumerate(logl(gc)[a:]):
        if needle in ln:
            return a + i
    return None
def pushes(gc, a, b, cls): return [short(x) for x in logl(gc)[a:b] if "[coop-ui] push class OpenXcom::%s depth" % cls in x]
def cw(gc, match, settle=1.0, ready=False):
    if ready:  # W2-U9 (F20796 / F20872): a POPUP window (InterceptState) drops a click on a hidden button
        session.wait_widget_ready(gc, match)
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
def click_px(gc, bx, by, sc, until_not, offsets=((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2))):
    """real clicks at base pixel (bx, by) + offsets through the window mapping until the top leaves `until_not`"""
    tries = []
    for dx, dy in offsets:
        wx, wy = int(round(sc[0] * (bx + dx) + sc[1])), int(round(sc[2] * (by + dy) + sc[3]))
        t = time.time()
        q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        seen, t4 = [], time.time()
        while time.time() - t4 < 1.0:
            tp = top(gc)
            e = [tp] + ([code(gc)] if tp == "CoopState" else [])
            if not seen or seen[-1][1:] != e:
                seen.append([round(time.time() - t, 2)] + e)
            time.sleep(0.05)
        tries.append({"base": [bx + dx, by + dy], "t": t, "seen": seen, "top": top(gc)})
        if tries[-1]["top"] != until_not:
            break
    return tries
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def pick_point(gc, centre, avoid):
    """LAND_PICK: rings x 16 around the builder's first own base, >= MIN_SEP from every base and marker; the point and its 8
    neighbours at 0.02 rad on land; inside the globe surface (10 px margin, 30 px top)."""
    for r in RINGS:
        for k in range(16):
            p = (centre[0] + r * math.cos(2 * math.pi * k / 16), centre[1] + r * math.sin(2 * math.pi * k / 16))
            if any(dist(p, b) < MIN_SEP for b in avoid):
                continue
            pr = globe(gc, lon=p[0], lat=p[1])
            if not pr.get("land"):
                continue
            nb = [globe(gc, lon=p[0] + dx, lat=p[1] + dy).get("land") for dx in (-0.02, 0, 0.02) for dy in (-0.02, 0, 0.02)]
            if all(nb) and 10 < pr["x"] < pr["globeW"] - 10 and 30 < pr["y"] < pr["globeH"] - 10:
                return {"lon": round(p[0], 5), "lat": round(p[1], 5), "x": pr["x"], "y": pr["y"], "r": r, "k": k}
    return None
def until(pred, deadline, step=0.05):
    """the absolute time pred() first held, polling until the absolute deadline; None when it never did"""
    while True:
        if pred():
            return time.time()
        if time.time() >= deadline:
            return None
        time.sleep(step)
def after(t, base): return round(t - base, 2) if t else None
def tick(t0, k): time.sleep(max(0.0, t0 + k * POLL - time.time()))
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def folder(gc):
    out = {}
    for p in glob.glob(os.path.join(gc.user_dir, "xcom1", "*")):
        try:
            if os.path.isfile(p):
                out[os.path.basename(p)] = os.stat(p).st_mtime_ns
        except FileNotFoundError:  # cap-tail (F24062): renamed after the listing (the save's .bak -> .asav move)
            pass
    return out
def copyfnv(h): return q(h, {"cmd": "coop_file_info", "role": "host_copy_of_client"}).get("fnv1a64")
def funds_text(gc):
    w = q(gc, {"cmd": "list_widgets"})
    t = next((x.get("text") for x in w.get("widgets", []) if (x.get("text") or "").startswith("FUNDS>")), None)
    d = re.sub(r"\D", "", t or "")
    return t, (int(d) if d else None)
def soldier_names(gc):
    r = q(gc, {"cmd": "get_soldiers"})
    return sorted(s.get("name") for b in r.get("bases", []) if not b.get("coopIcon") and not b.get("coopBaseFlag") for s in b.get("soldiers", []))

# ----- the boot and the row frame -----
class Boot:
    def __init__(self):
        self.aff, self.base, self.fails = {}, {}, []
        self.host = GameClient("host", None, make_user_dir("w2h66b_host"))
        self.client = GameClient("client", None, make_user_dir("w2h66b_client"))
class Row:
    def __init__(self, b, rid):
        self.b, self.rid, self.res, self.ev = b, rid, {}, {"t": now()}
    def cell(self, cid, ok, label):
        self.res[cid] = (bool(ok), label)
    def need(self, ok, what):
        if not ok:
            raise Stop(what)
    def finish(self, stop=None):
        self.ev["tEnd"] = now()
        if stop:
            self.ev["stop"] = stop
        print("EVIDENCE %s: %s" % (self.rid, js(self.ev)), flush=True)
        fails = []
        for cid in dict(ROWS)[self.rid]:
            ok, label = self.res.get(cid, (False, "not reached (%s)" % stop))
            print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, "RED" if cid in RED else "GUARD", label), flush=True)
            fails += [] if ok else [cid]
        if stop:
            print("CAPTURE %s: %s" % (self.rid, js(capture(self.b))), flush=True)
        print(("PASS %s" % self.rid) if not fails else ("FAIL %s: %s" % (self.rid, " ".join(fails))), flush=True)
        self.b.fails += fails
def capture(b):
    """every live machine's probes and log tail (the FIXTURE-STOP dump)"""
    out = {}
    for gc in (b.host, b.client):
        if not alive(gc):
            out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None}
            continue
        w = q(gc, {"cmd": "list_widgets"})
        out[gc.name] = {"get_state": q(gc, {"cmd": "get_state"}), "dialog": dlg(gc), "geo_state": census(gc),
                        "widgets": [w.get("state")] + [[v.get("text"), v.get("visible")] for v in w.get("widgets", []) if v.get("text")],
                        "log": [short(ln) for ln in logl(gc)[-15:]]}
    return out
def bring_up(b):
    for gc in (b.host, b.client):
        gc.spawn()
        gc.connect(timeout=240)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    session.new_campaign(b.host, b.client, port=KEY)
    geo.slow_clock(b.host, b.client)
    time.sleep(2.0)
    ev = {"drain": [str(geo.drain_popups(gc))[:120] for gc in (b.host, b.client)]}
    for gc in (b.host, b.client):
        b.aff[gc.name] = affine(cw(gc, "INTERCEPT", 0.6), cw(gc, "CANCEL", 0.6, ready=True))
    h, c = census(b.host), census(b.client)
    ev.update({"aff": b.aff, "host": h, "client": c})
    ok = h["stack"] == ["GeoscapeState"] and c["stack"] == ["GeoscapeState"] and len(own(h)) == 1 and len(own(c)) == 1
    if ok:
        b.base = {"host": own(h)[0], "client": own(c)[0]}   # HOST_BASE / PARTNER_BASE: [id, name, icon, coopBase, lon, lat]
    return ok, ev

# ----- steps -----
def both_geo(b, r):
    s = [stk(b.host), stk(b.client)]
    r.need(s[0][-1:] == ["GeoscapeState"] and s[1][-1:] == ["GeoscapeState"], "row start: tops %s / %s" % (s[0][-1:], s[1][-1:]))
def to_name(b, r, gc):
    """gc: centre on its first own base, BASES, BUILD NEW BASE, ONE real globe click at LAND_PICK, OK -> BaseNameState, own base "" """
    ev = r.ev["toName"] = {}
    first = own(census(gc))[0]
    globe(gc, centerLon=first[4], centerLat=first[5])
    cw(gc, "BASES")
    cw(gc, "NEW BASE")
    r.need(top(gc) == "BuildNewBaseState", "%s top %s after BUILD NEW BASE" % (gc.name, top(gc)))
    pick = ev["LAND_PICK"] = pick_point(gc, (first[4], first[5]), [(x[4], x[5]) for x in census(gc)["bases"]])
    r.need(pick, "no land point for LAND_PICK")
    ev["click"] = [t["top"] for t in click_px(gc, pick["x"], pick["y"], b.aff[gc.name], "BuildNewBaseState")]
    r.need(top(gc) == "ConfirmNewBaseState", "%s top %s after the globe click" % (gc.name, top(gc)))
    cw(gc, "OK")
    cc = census(gc)
    new = [x[:2] for x in own(cc) if x[1] == ""]
    r.need(top(gc) == "BaseNameState" and len(new) == 1, "%s on BaseNameState with one own base \"\" (%s, %s)" % (gc.name, top(gc), own(cc)))
    ev["X"], ev["funds"] = new[0], cc["funds"]
def visit(b, r, v, okey):
    """v: centre on the marker of the owner's first base, ONE real click on its pixel; v's top CoopState 50 or BasescapeState within 2 s"""
    ev = r.ev["visit"] = {}
    m = [x for x in census(v)["bases"] if x[2] and x[0] == b.base[okey][0]]
    r.need(m, "%s has no marker with coopBaseId %s" % (v.name, b.base[okey][0]))
    globe(v, centerLon=m[0][4], centerLat=m[0][5])
    time.sleep(0.5)
    pr = globe(v, lon=m[0][4], lat=m[0][5])
    tries = click_px(v, pr["x"], pr["y"], b.aff[v.name], "GeoscapeState")
    ev.update({"marker": m[0][:2], "px": [pr.get("x"), pr.get("y")], "tries": [[t["base"], t["seen"]] for t in tries]})
    tv = tries[-1]["t"]
    ev["tEnter"] = after(until(lambda: (lambda t: t == "BasescapeState" or (t == "CoopState" and code(v) == 50))(top(v)), tv + 2.0), tv)
    r.need(ev["tEnter"] is not None, "%s top %s (code %s) 2 s after the visit click" % (v.name, top(v), code(v)))
    return tv
def name(b, r, gc, nm):
    """close every top CoopState 995 by its back button (max 3; today only), type nm by real key presses, OK; returns T_OK"""
    ev = r.ev["name"] = {"closed": []}
    for _ in range(3):
        if top(gc) == "CoopState" and code(gc) == 995:
            ev["closed"].append(cw(gc, dlg(gc).get("backText") or "OK")["after"][-2:])
        else:
            break
    r.need(top(gc) == "BaseNameState", "%s top %s before typing the name" % (gc.name, top(gc)))
    for ch in nm:
        key(gc, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    t = time.time()
    cw(gc, "OK", 0.0)
    return t
def finish(b, r, gc):
    """LIFT_TILE click (top BasescapeState within 5 s), GEOSCAPE (top GeoscapeState within 5 s)"""
    click_px(gc, LIFT_TILE[0] * 32 + 16, 8 + LIFT_TILE[1] * 32 + 16, b.aff[gc.name], "PlaceLiftState", offsets=((0, 0),))
    r.need(until(lambda: top(gc) == "BasescapeState", time.time() + 5.0, 0.1), "%s top %s after the lift click" % (gc.name, top(gc)))
    time.sleep(SETTLE)
    cw(gc, "GEOSCAPE", 0.0)
    r.need(until(lambda: top(gc) == "GeoscapeState", time.time() + 5.0, 0.1), "%s top %s after GEOSCAPE" % (gc.name, top(gc)))
def home(gc):
    time.sleep(SETTLE)
    t = time.time()
    cw(gc, "GEOSCAPE", 0.0)
    return after(until(lambda: top(gc) == "GeoscapeState", t + 5.0, 0.1), t)
def live(v, owner, t0, ev):
    """within ENTER_S of t0 the visitor's top is BasescapeState with a FUNDS text; its digits against the owner's funds"""
    got = {}
    def p():
        if top(v) != "BasescapeState":
            return False
        got["t"], got["d"] = funds_text(v)
        return got["d"] is not None
    ev["tLive"] = after(until(p, t0 + ENTER_S, POLL), t0)
    ev["fundsText"], ev["fundsDigits"], ev["ownerFunds"] = got.get("t"), got.get("d"), funds(owner)
    return ev["tLive"] is not None and got.get("d") == ev["ownerFunds"]
def watch(owner, v, t0, secs, trace, codes):
    """poll both every POLL until t0 + secs; trace = changes of [visitor top, its code, owner tail, owner code]"""
    k = 0
    while time.time() - t0 < secs:
        k += 1
        tick(t0, k)
        vs, os_ = stk(v), stk(owner)
        oc = code(owner) if "CoopState" in os_ else None
        codes.add(oc)
        e = [vs[-1:], code(v) if vs[-1:] == ["CoopState"] else None, os_[-2:], oc]
        if not trace or trace[-1][1:] != e:
            trace.append([round(time.time() - t0, 2)] + e)
def gift(b, r, mini=False):
    """host: BASES, (MINI0,) SOLDIERS, GIFT_ROW click, GIVE_KEY, SETTLE_MENU, the partner's button; partner RECV within GIFT_S (returns its
    log line M1); host back by OK, OK, GEOSCAPE; partner GiftNoticeState OK -> BaseNameState"""
    h, c = b.host, b.client
    ev = r.ev["gift"] = {}
    s0 = soldier_names(h)
    cw(h, "BASES")
    if mini:
        click_px(h, MINI0[0], MINI0[1], b.aff["host"], "-", offsets=((0, 0),))
    cw(h, "SOLDIERS")
    click_px(h, GIFT_ROW[0], GIFT_ROW[1], b.aff["host"], "SoldiersState", offsets=((0, 0), (0, 1)))
    r.need(top(h) == "SoldierInfoState", "host top %s after the GIFT_ROW click" % top(h))
    key(h, GIVE_KEY)
    r.need(until(lambda: top(h) == "GiftSoldierMenu", time.time() + 3.0, 0.05), "host top %s after GIVE_KEY" % top(h))
    time.sleep(SETTLE_MENU)
    w = [x.get("text") for x in q(h, {"cmd": "list_widgets"}).get("widgets", []) if x.get("text") and x.get("visible")]
    tgt = [t for t in w if t.upper() != "CANCEL" and not t.startswith("Gift ")]
    r.need(tgt, "no partner button in GiftSoldierMenu %s" % w)
    m0, tg = len(logl(c)), time.time()
    ev["button"] = cw(h, tgt[0], 0.0)["match"]
    ev["tRecv"] = after(until(lambda: first_after(c, m0, "[coop-gift] RECV added soldier") is not None, tg + GIFT_S, 0.1), tg)
    r.need(ev["tRecv"] is not None, "partner log: no RECV added soldier within GIFT_S")
    m1 = first_after(c, m0, "[coop-gift] RECV added soldier")
    ev["gifted"] = sorted(set(s0) - set(soldier_names(h)))
    for lab in ("OK", "OK", "GEOSCAPE"):
        if top(h) != "GeoscapeState":
            cw(h, lab, 0.8)
    r.need(top(h) == "GeoscapeState", "host top %s after OK, OK, GEOSCAPE" % top(h))
    cw(c, "OK")
    r.need(top(c) == "BaseNameState", "partner top %s after the GiftNoticeState OK" % top(c))
    return m1

# ----- rows -----
def row_v(b, r):
    h, c, ev = b.host, b.client, r.ev
    both_geo(b, r)
    pre = ev["PRE"] = funds(h)
    m0 = len(logl(c))
    tv = visit(b, r, h, "client")
    ev["tTop"] = after(until(lambda: top(h) == "BasescapeState", tv + ENTER_S, POLL), tv)
    r.cell("V-enter", ev["tTop"] is not None, "host top BasescapeState %s s after the click (want <= %s)" % (ev["tTop"], ENTER_S))
    ok = live(h, c, tv, ev)
    r.cell("V-live", ok, "host FUNDS %r digits %s vs partner funds %s" % (ev["fundsText"], ev["fundsDigits"], ev["ownerFunds"]))
    p = pushes(c, m0, None, "CoopState")
    r.cell("V-no995", not p, "partner log click -> V-live CoopState pushes %s (want none)" % p)
    tg = home(h)
    hf = funds(h)
    r.cell("V-home", tg is not None and hf == pre, "host GeoscapeState %s s after GEOSCAPE, funds %s (PRE %s)" % (tg, hf, pre))
def row_g(b, r):
    h, c, ev = b.host, b.client, r.ev
    both_geo(b, r)
    to_name(b, r, c)
    h0, f0 = copyfnv(h), folder(h)
    ev["H0"] = h0
    m1 = gift(b, r)
    t_ok = name(b, r, c, NAMES["G"])
    seen, k = {}, 0
    while time.time() - t_ok < LANDS_S:
        k += 1
        tick(t_ok, k)
        if "named" not in seen and top(c) == "PlaceLiftState":
            seen["named"] = round(time.time() - t_ok, 2)
        fv = copyfnv(h)
        if "lands" not in seen and fv and fv != h0:
            seen["lands"], seen["fnv"], seen["folderSame"] = round(time.time() - t_ok, 2), fv, folder(h) == f0
    m2 = len(logl(c))
    ev["seen"], ev["partnerWin"] = seen, win(c, m1, m2)
    pl = first_after(c, m1, "[coop-ui] push class OpenXcom::PlaceLiftState depth")
    p1 = pushes(c, m1, pl, "CoopState") if pl is not None else ["no PlaceLiftState push"]
    r.cell("G-no995", pl is not None and not p1, "partner log RECV -> PlaceLiftState push CoopState pushes %s (want none)" % p1)
    r.cell("G-named", seen.get("named") is not None and seen["named"] <= 5.0, "partner top PlaceLiftState %s s after the OK (want <= 5)" % seen.get("named"))
    r.cell("G-lands", "lands" in seen and seen["folderSame"], "host copy %s -> %s at %s s after the OK, save folder unchanged %s (want a change within %s)"
           % (h0, seen.get("fnv"), seen.get("lands"), seen.get("folderSame"), LANDS_S))
    p2 = pushes(c, pl, m2, "CoopState") if pl is not None else ["no PlaceLiftState push"]
    r.cell("G-calm", pl is not None and not p2, "partner log PlaceLiftState -> T_OK + LANDS_S CoopState pushes %s (want none)" % p2)
    finish(b, r, c)
def row_visit(b, r, owner, v, okey, nm):
    """rows P / H: OWNER names, VISITOR visits the owner's first base"""
    ev, rid = r.ev, r.rid
    both_geo(b, r)
    to_name(b, r, owner)
    pre = ev["PRE"] = funds(v)
    mo, mv = len(logl(owner)), len(logl(v))
    tv = visit(b, r, v, okey)
    trace, codes = [], set()
    watch(owner, v, tv, WAIT_S, trace, codes)
    vt, vc = top(v), code(v)
    ev["wait"] = {"trace": trace, "codes": sorted(x for x in codes if x)}
    r.cell(rid + "-wait", vt == "CoopState" and vc == 50, "visitor top %s code %s at +WAIT_S (want CoopState 50)" % (vt, vc))
    r.cell(rid + "-no995", 995 not in codes, "owner codes during WAIT_S %s (want no 995)" % ev["wait"]["codes"])
    t_ok = name(b, r, owner, nm)
    ev["tNamed"] = after(until(lambda: top(owner) == "PlaceLiftState", t_ok + 5.0), t_ok)
    r.cell(rid + "-named", ev["tNamed"] is not None, "owner top PlaceLiftState %s s after the OK (want <= 5)" % ev["tNamed"])
    ok = live(v, owner, t_ok, ev)
    r.cell(rid + "-live", ok, "visitor BasescapeState %s s after the OK, FUNDS %r digits %s vs owner funds %s" % (ev["tLive"], ev["fundsText"], ev["fundsDigits"], ev["ownerFunds"]))
    ev["ownerWin"], ev["visitorWin"] = win(owner, mo), win(v, mv)
    finish(b, r, owner)
    tg = home(v)
    vf = funds(v)
    r.cell(rid + "-home", tg is not None and vf == pre, "visitor GeoscapeState %s s after GEOSCAPE, funds %s (PRE %s)" % (tg, vf, pre))
def row_p(b, r): row_visit(b, r, b.client, b.host, "client", NAMES["P"])
def row_h(b, r): row_visit(b, r, b.host, b.client, "host", NAMES["H"])
def row_q(b, r):
    h, c, ev = b.host, b.client, r.ev
    both_geo(b, r)
    to_name(b, r, c)
    pre, h0, f0 = funds(h), copyfnv(h), folder(h)
    ev["PRE"], ev["H0"] = pre, h0
    m1 = gift(b, r, mini=True)
    r.need(len(ev["gift"]["gifted"]) == 1, "host get_soldiers lost %s (want exactly one name)" % ev["gift"]["gifted"])
    tv = visit(b, r, h, "client")
    trace, codes = [], set()
    watch(c, h, tv, WAIT_S, trace, codes)
    ht, hc = top(h), code(h)
    ev["wait"] = {"trace": trace, "stacks": [stk(h)[-2:], stk(c)[-2:]]}
    h1 = ev["H1"] = copyfnv(h)
    r.cell("Q-wait", ht == "CoopState" and hc == 50, "host top %s code %s at +WAIT_S (want CoopState 50)" % (ht, hc))
    mh = len(logl(h))
    t_ok = name(b, r, c, NAMES["Q"])
    seen, trace2, k, marks = {}, [], 0, None
    while time.time() - t_ok < max(ENTER_S, LANDS_S):
        k += 1
        tick(t_ok, k)
        el = round(time.time() - t_ok, 2)
        ct, htp, fv = top(c), top(h), copyfnv(h)
        if "named" not in seen and ct == "PlaceLiftState":
            seen["named"] = el
        if "live" not in seen and htp == "BasescapeState" and el <= ENTER_S:
            ft = funds_text(h)
            if ft[1] is not None:
                seen["live"], seen["fundsText"], seen["fundsDigits"], seen["ownerFunds"] = el, ft[0], ft[1], funds(c)
        if "lands" not in seen and fv and fv != h1 and el <= LANDS_S:
            seen["lands"], seen["fnv"], seen["folderSame"] = el, fv, folder(h) == f0
        e = [htp, code(h) if htp == "CoopState" else None, ct, fv]
        if not trace2 or trace2[-1][1:] != e:
            trace2.append([el] + e)
        if marks is None and el >= LANDS_S:
            marks = (len(logl(c)), len(logl(h)))
    marks = marks or (len(logl(c)), len(logl(h)))
    ev.update({"after": trace2, "seen": seen, "copyEnd": copyfnv(h), "folderSameEnd": folder(h) == f0, "endStacks": [stk(h)[-2:], stk(c)[-2:]],
               "partnerWin": win(c, m1, marks[0]), "hostWin": win(h, mh, marks[1])})
    p1 = pushes(c, m1, marks[0], "CoopState")
    r.cell("Q-no995", not p1, "partner log RECV -> T_OK + LANDS_S CoopState pushes %s (want none)" % p1)
    r.cell("Q-named", seen.get("named") is not None and seen["named"] <= 5.0, "partner top PlaceLiftState %s s after the OK (want <= 5)" % seen.get("named"))
    r.cell("Q-live", "live" in seen and seen["fundsDigits"] == seen["ownerFunds"], "host BasescapeState %s s after the OK, FUNDS %r digits %s vs partner funds %s"
           % (seen.get("live"), seen.get("fundsText"), seen.get("fundsDigits"), seen.get("ownerFunds")))
    r.cell("Q-lands", "lands" in seen and seen["folderSame"], "host copy H1 %s -> %s at %s s after the OK (H0 %s), save folder unchanged %s (want a change within %s)"
           % (h1, seen.get("fnv"), seen.get("lands"), h0, seen.get("folderSame"), LANDS_S))
    pops = [short(x) for x in logl(h)[mh:marks[1]] if "[coop-ui] pop  class OpenXcom::BasescapeState depth" in x]
    r.cell("Q-stays", not pops, "host log OK -> T_OK + LANDS_S BasescapeState pops %s (want none)" % pops)
    finish(b, r, c)
    tg = home(h)
    hf = funds(h)
    r.cell("Q-home", tg is not None and hf == pre, "host GeoscapeState %s s after GEOSCAPE, funds %s (PRE %s)" % (tg, hf, pre))

FLOW = (("V", row_v), ("G", row_g), ("P", row_p), ("H", row_h), ("Q", row_q))
def run_rows(b):
    cv = crashes()
    for rid, fn in FLOW:
        r = Row(b, rid)
        try:
            fn(b, r)
            r.finish()
        except Stop as e:
            r.finish(str(e))
        except Exception as e:  # noqa: BLE001 - an unexpected exception ends the row like a precondition miss
            r.finish("exception %s: %s" % (type(e).__name__, str(e)[:300]))
    r = Row(b, "END")
    new, al = sorted(os.path.basename(p) for p in crashes() - cv), [alive(b.host), alive(b.client)]
    r.ev.update({"newCrash": new, "aliveBeforeShutdown": al, "crashDir": harness.CRASH_DIR})
    r.cell("CRASH", not new and all(al), "new crash files since row V %s (want none), host / client alive before shutdown %s" % (new, al))
    r.finish()
def main():
    T0[0] = time.time()
    crash0, b, rcs = crashes(), Boot(), []
    try:
        ev = {"key": KEY, "slot": harness.HARNESS_SLOT, "cpu": cpu(), "t": now()}
        try:
            ok, bev = bring_up(b)
            ev.update(bev)
            ev["bases"] = b.base
        except Exception as e:  # noqa: BLE001 - a boot that raises is a boot miss
            ok, ev["error"] = False, ("%s: %s" % (type(e).__name__, e))[:400]
        print("EVIDENCE boot: %s" % js(ev), flush=True)
        if not ok:
            print("CAPTURE boot: %s" % js(capture(b)), flush=True)
            for rid, cells in ROWS:
                for cid in cells:
                    print("FAIL %s %s: boot" % (cid, "RED" if cid in RED else "GUARD"), flush=True)
                    b.fails.append(cid)
                print("FAIL %s: boot" % rid, flush=True)
        else:
            run_rows(b)
    finally:
        for gc in (b.client, b.host):
            try:
                if alive(gc):
                    gc.shutdown(expected_returncodes=OKRC)
                rcs.append([gc.name, gc.proc.poll() if gc.proc else None])
            except Exception as e:  # noqa: BLE001
                rcs.append([gc.name, str(e)[:200]])
        print("EVIDENCE shutdown: %s" % js({"rc": rcs, "newCrashAll": sorted(os.path.basename(p) for p in crashes() - crash0), "cpu": cpu()}), flush=True)
        cl = [cid for _r, cs in ROWS for cid in cs]
        print("SUMMARY W2-H66 S-B HUN: %d/%d cells pass; failing %s; wall %.1f s" % (len(cl) - len(set(b.fails)), len(cl),
                                                                                  sorted(set(b.fails)) or "none", now()), flush=True)
    return 0 if not b.fails else 2

if __name__ == "__main__":
    sys.exit(main())
