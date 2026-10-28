"""W2-H68 (R-H68-0; the W2-H8 K3 follow-up) - SEPARATE campaign: the selected base stays on its base when a
base screen hides and shows the partner's mirror bases, so the geoscape BASES button opens the player's own
base with every button.

A SEPARATE world holds the partner's bases as `_coopIcon` mirrors. An open base screen takes them out of the
live base list and puts them back on every exit. `SavedGame::_selectedBase` is an INDEX; written
while the mirrors are out, it names a mirror once they are back, and the next BASES opens the mirror's layout
(BUILD FACILITIES, RESEARCH, MANUFACTURE, TRANSFER, SELL/SACK hidden) over the player's first base.

ONE boot, lobby key "49249" (user dirs w2h68_host / w2h68_client), slot from OXC_HARNESS_SLOT. Spec
rewrite/prompts/w2h68_selected_base_mirror.md (f); pins from rewrite/w2h68-task0/sa/CONSTANTS.md (TASK 0
boots a, b red; c green).

  B   bring-up: SEPARATE campaign, both on the geoscape     (no cell; a miss fails every cell "boot")
  H0  host BASES, GEOSCAPE (control)                        H0-sel, H0-geo
  H1  host builds "hsnew" (BUILD NEW BASE, globe, OK, name, lift), GEOSCAPE        H1-geo
  H2  host BASES, TRANSFER, CANCEL, GEOSCAPE                H2-shown, H2-buttons, H2-transfer, H2-geo
  H3  reset RS, base-strip click on slot 2, right click on the lift              H3-geo
  H4  reset RS, key 2, BUILD NEW BASE, CANCEL               H4-geo
  C1  client builds "ltrnew", GEOSCAPE                      C1-geo
  C2  client as H2                                          C2-shown, C2-buttons, C2-transfer, C2-geo
  L   both base lists (control)                             L-lists
  end shutdown                                              CRASH
RS = BASES, GEOSCAPE, BASES, key 1: the reset both builds reach alike. Red on the pre-fix build:
H1-geo, H2-shown, H2-buttons, H2-transfer, H2-geo, H3-geo, H4-geo, C1-geo, C2-shown, C2-buttons, C2-transfer,
C2-geo (the selection names a mirror, or the redirect's first base); H0-*, L-lists and CRASH pass.

Each row prints ONE "EVIDENCE <row>:" line, one "PASS <cell>" / "FAIL <cell>: <why>" line per cell and
"ROW <row>: PASS|FAIL". Every row runs after a failure; a precondition miss ends its row (its cells FAIL "not
reached"). Every press is a real click_widget or inject_input. run it to completion in the foreground.
ONE run is the bar, no SKIP. Exit 0 = every cell passed; 2 = at least one cell failed.
Run:  python tools/coop_test/test_selected_base_mirror.py
"""

import glob
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49249"
HOST_POS = (0.90, -0.60)               # bases >= 0.15 rad apart, both on land (TASK 0: 0.21 rad)
NAME2, NAME1 = "hsnew", "ltrnew"       # the host's / the client's second base
LIFTS = ((2, 2), (3, 2), (2, 3), (3, 3))  # BaseView tiles; the first that leaves PlaceLiftState is used
MINI1 = (24, 8)                        # MiniBaseView slot 1 centre (16 px per slot)
KEY1, KEY2 = 49, 50                    # Options::keyBaseSelect1 / 2 = SDLK_1 / SDLK_2
FIVE = ("BUILD FACILITIES", "RESEARCH", "MANUFACTURE", "TRANSFER", "SELL")
WIN_S, POLL, TR_S, STEP_CAP_S = 3.0, 3.0, 2.0, 6.0
OKRC = (0, 1, 3221226505, -1073740791, 3221225477)
ROWCELLS = (("H0", ("H0-sel", "H0-geo")), ("H1", ("H1-geo",)),
            ("H2", ("H2-shown", "H2-buttons", "H2-transfer", "H2-geo")), ("H3", ("H3-geo",)), ("H4", ("H4-geo",)),
            ("C1", ("C1-geo",)), ("C2", ("C2-shown", "C2-buttons", "C2-transfer", "C2-geo")), ("L", ("L-lists",)))
CELLS = [c for _, cs in ROWCELLS for c in cs] + ["CRASH"]
RESULT = {}

class Pre(Exception):
    """A fixture step missed its precondition: ends its row."""

# --------------------------------------------------------------------------- probes and presses (helpers copied from t0_h65a.py)

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead socket is evidence, not a test error
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}

def stk(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.split("::")[-1] for s in r["states"]] if "states" in r else ["<get_state: %s>" % r.get("error")]

def census(gc):
    g = q(gc, {"cmd": "geo_state"})
    return {"bases": [[b.get("name"), bool(b.get("coopIcon")), b.get("lon", 0), b.get("lat", 0)] for b in g.get("bases", [])],
            "sel": g.get("selectedBase"), "error": g.get("error")}

def top(gc): return (stk(gc) or [None])[-1]
def SEL(gc): return census(gc)["sel"]
def KINDS(gc): return ["mirror" if b[1] else "own" for b in census(gc)["bases"]]
def names(gc, mirror): return [b[0] for b in census(gc)["bases"] if b[1] == mirror]
def widgets(gc): return q(gc, {"cmd": "list_widgets"}).get("widgets", [])
def crashes(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def alive(gc): return gc.proc is not None and gc.proc.poll() is None
def key(gc, sym): return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})
def globe(gc, **kw): return q(gc, dict({"cmd": "globe_point"}, **kw))
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])

def snap(gc):
    c = census(gc)
    return "%s sel=%r bases=%s" % (stk(gc)[-1:], c["sel"], ["%s%s" % (b[0], "*" if b[1] else "") for b in c["bases"]])

def rect(gc, suffix):
    hits = [w for w in widgets(gc) if w.get("type", "").endswith("::" + suffix)]
    if len(hits) != 1:
        raise Pre("%s: one %s widget, got %d" % (gc.name, suffix, len(hits)))
    return hits[0]["x"], hits[0]["y"]

def five(gc):
    tb = [w for w in widgets(gc) if w.get("type", "").endswith("::TextButton")]
    return {c: [w.get("visible") for w in tb if c in (w.get("text") or "").upper()] for c in FIVE}

def wait_for(pred, cap=POLL):
    t = time.time()
    while time.time() - t < cap:
        if pred():
            return True
        time.sleep(0.1)
    return bool(pred())

def ready(gc):  # no surface of the top state hidden (a POPUP window hides them all while it opens)
    return wait_for(lambda: not any(w.get("hidden") for w in widgets(gc)))

def press(gc, match, want):
    # a POPUP window (InterceptState) hides its buttons while it opens and a hidden button drops the click
    session.wait_widget_ready(gc, match, timeout=POLL)   # the shared gate (same rule, same bound)
    r = q(gc, {"cmd": "click_widget", "match": match})
    if not r.get("ok") or not wait_for(lambda: top(gc) == want):
        raise Pre("%s %r -> %s, top %s (want %s)" % (gc.name, match, r.get("error") or "ok", stk(gc)[-1:], want))
    return r

def affine(r1, r2):
    out = [(r1["winX"] - r2["winX"]) / (r1["baseX"] - r2["baseX"]) if r1["baseX"] != r2["baseX"] else None,
           (r1["winY"] - r2["winY"]) / (r1["baseY"] - r2["baseY"]) if r1["baseY"] != r2["baseY"] else None]
    sc = round(out[0] or out[1], 3)
    return (sc, r1["winX"] - sc * r1["baseX"], sc, r1["winY"] - sc * r1["baseY"])

def click_px(gc, sc, bx, by, button="left"):
    wx, wy = int(round(sc[0] * bx + sc[1])), int(round(sc[2] * by + sc[3]))
    return q(gc, {"cmd": "inject_input", "kind": "click", "x": wx, "y": wy, "button": button})

def pick_point(gc, avoid):
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
                return {"lon": round(p[0], 5), "lat": round(p[1], 5), "x": pr["x"], "y": pr["y"]}
    return None

def window_cycle(gc):
    press(gc, "INTERCEPT", "InterceptState")
    press(gc, "CANCEL", "GeoscapeState")

def build_base(x, gc, name, ev):
    """BASES, BUILD NEW BASE, ONE globe click at PICK, OK, the name (typed once the popup shows it), OK, LIFT -> BasescapeState"""
    press(gc, "BASES", "BasescapeState")
    press(gc, "NEW BASE", "BuildNewBaseState")
    bl = census(gc)["bases"]
    pick = pick_point(gc, [(b[2], b[3]) for b in bl if not b[1]] + [(b[2], b[3]) for b in bl if b[1]])
    if not pick:
        raise Pre("%s: no land point for PICK" % gc.name)
    ready(gc)
    for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2)):
        click_px(gc, x.aff[gc.name], pick["x"] + dx, pick["y"] + dy)
        if wait_for(lambda: top(gc) != "BuildNewBaseState", 1.0):
            break
    ev["pick"] = pick
    if top(gc) != "ConfirmNewBaseState":
        raise Pre("%s: top %s after the globe click at PICK %s" % (gc.name, stk(gc)[-1:], pick))
    press(gc, "OK", "BaseNameState")
    if [b[0] for b in census(gc)["bases"] if not b[1]].count("") != 1:
        raise Pre("%s: BaseNameState without one own base named \"\": %s" % (gc.name, snap(gc)))
    # the POPUP window hides the TextEdit for ~0.1 s and a hidden surface drops keys
    if not wait_for(lambda: [w.get("hidden") for w in widgets(gc) if w.get("type", "").endswith("::TextEdit")] == [False]):
        raise Pre("%s: the BaseNameState TextEdit still hidden after %.0f s" % (gc.name, POLL))
    for ch in name:
        key(gc, ord(ch))
        time.sleep(0.08)
    time.sleep(0.4)
    press(gc, "OK", "PlaceLiftState")
    ready(gc)
    for tx, ty in LIFTS:
        click_px(gc, x.aff[gc.name], tx * 32 + 16, 8 + ty * 32 + 16)
        if wait_for(lambda: top(gc) != "PlaceLiftState", 1.0):
            x.lift[gc.name] = (tx, ty)
            break
        ev.setdefault("swaps", []).append("LIFT (%d, %d) -> next" % (tx, ty))
    if not wait_for(lambda: top(gc) == "BasescapeState"):
        raise Pre("%s: top %s after the lift (want BasescapeState)" % (gc.name, stk(gc)[-1:]))
    ev["lift"] = x.lift.get(gc.name)

def rs(x, gc, ev):
    """BASES, GEOSCAPE, BASES, key 1: own base 1 shown, the mirrors hidden"""
    press(gc, "BASES", "BasescapeState")
    press(gc, "GEOSCAPE", "GeoscapeState")
    press(gc, "BASES", "BasescapeState")
    key(gc, KEY1)
    if not wait_for(lambda: SEL(gc) == x.own1[gc.name] and set(KINDS(gc)) == {"own"}):
        raise Pre("RS: %s %s (want sel %r, every base own)" % (gc.name, snap(gc), x.own1[gc.name]))
    ev["rs"] = snap(gc)

def cell(cid, ok, msg):
    return cid, (bool(ok), msg)

# --------------------------------------------------------------------------- rows

def row_h0(x, ev):
    h = x.host
    press(h, "BASES", "BasescapeState")
    ev["inBase"] = snap(h)
    s1 = SEL(h)
    press(h, "GEOSCAPE", "GeoscapeState")
    s2 = ev["geo"] = SEL(h)
    oh = x.own1["host"]
    return dict([cell("H0-sel", s1 == oh, "host selectedBase in the base screen %r (want %r)" % (s1, oh)),
                 cell("H0-geo", s2 == oh, "host selectedBase after GEOSCAPE %r (want %r)" % (s2, oh))])

def row_h1(x, ev):
    h, c = x.host, x.client
    build_base(x, h, NAME2, ev)
    if not (SEL(h) == NAME2 and KINDS(h) == ["own", "own"]):
        raise Pre("after the lift: host %s (want sel %r, [own, own])" % (snap(h), NAME2))
    press(h, "GEOSCAPE", "GeoscapeState")
    ev["geo"] = snap(h)
    sel = SEL(h)
    if KINDS(h) != ["own", "mirror", "own"]:
        raise Pre("host kinds %s after GEOSCAPE (want [own, mirror, own])" % KINDS(h))
    window_cycle(c)
    w = WIN_S
    while not wait_for(lambda: KINDS(c) == ["own", "mirror", "mirror"], w if w == WIN_S else 1.0) and w < STEP_CAP_S:
        w += 1.0
    ev["client"] = snap(c)
    ev["winS"] = w
    if KINDS(c) != ["own", "mirror", "mirror"]:
        raise Pre("client kinds %s after a window cycle + %.0f s (want [own, mirror, mirror])" % (KINDS(c), w))
    return dict([cell("H1-geo", sel == NAME2, "host selectedBase after the new base's GEOSCAPE %r (want %r)" % (sel, NAME2))])

def transfer_pair(x, gc, new, rows_ok, ev):
    """BASES; TRANSFER (raw); CANCEL when TransferBaseState is on top; GEOSCAPE"""
    press(gc, "BASES", "BasescapeState")
    ev["shown"] = snap(gc)
    shown, fv = SEL(gc), five(gc)
    ev["five"] = fv
    ready(gc)
    r = q(gc, {"cmd": "click_widget", "match": "TRANSFER"})
    on = wait_for(lambda: top(gc) == "TransferBaseState", TR_S)
    ss = q(gc, {"cmd": "screen_state"})
    tr = ev["transfer"] = {"reply": r.get("error") or "ok", "top": ss.get("top"), "rows": ss.get("rows"), "stack": stk(gc)[-1:]}
    if on:
        press(gc, "CANCEL", "BasescapeState")
        ev["afterCancel"] = snap(gc)
    press(gc, "GEOSCAPE", "GeoscapeState")
    g = SEL(gc)
    ev["geo"] = snap(gc)
    t = ev["tag"]
    return dict([cell(t + "-shown", shown == new, "%s selectedBase in the base screen %r (want %r)" % (gc.name, shown, new)),
                 cell(t + "-buttons", all(v == [True] for v in fv.values()), "%s visible %s (want one True each)" % (gc.name, fv)),
                 cell(t + "-transfer", tr["top"] == "transfer_base" and rows_ok(tr["rows"] or []),
                      "%s TRANSFER %s" % (gc.name, tr)),
                 cell(t + "-geo", g == new, "%s selectedBase after GEOSCAPE %r (want %r)" % (gc.name, g, new))])

def row_h2(x, ev):
    oh, oc = x.own1["host"], x.own1["client"]
    ev["tag"] = "H2"
    return transfer_pair(x, x.host, NAME2, lambda rows: rows == [oh, oc], ev)

def row_h3(x, ev):
    h = x.host
    rs(x, h, ev)
    mx, my = rect(h, "MiniBaseView")
    ready(h)
    click_px(h, x.aff["host"], mx + MINI1[0], my + MINI1[1])
    if not wait_for(lambda: SEL(h) == NAME2):
        raise Pre("base-strip click at %s: host %s (want sel %r)" % ((mx + MINI1[0], my + MINI1[1]), snap(h), NAME2))
    vx, vy = rect(h, "BaseView")
    lt = x.lift.get("host") or LIFTS[0]
    ev["liftpx"] = (vx + lt[0] * 32 + 16, vy + lt[1] * 32 + 16)
    ready(h)
    click_px(h, x.aff["host"], ev["liftpx"][0], ev["liftpx"][1], button="right")
    if not wait_for(lambda: top(h) == "GeoscapeState"):
        raise Pre("right click on the lift %s: host %s (want GeoscapeState)" % (ev["liftpx"], snap(h)))
    s = SEL(h)
    ev["geo"] = snap(h)
    return dict([cell("H3-geo", s == NAME2, "host selectedBase after the lift's right click %r (want %r)" % (s, NAME2))])

def row_h4(x, ev):
    h = x.host
    rs(x, h, ev)
    key(h, KEY2)
    if not wait_for(lambda: SEL(h) == NAME2):
        raise Pre("key 2: host %s (want sel %r)" % (snap(h), NAME2))
    press(h, "NEW BASE", "BuildNewBaseState")
    press(h, "CANCEL", "GeoscapeState")
    s = SEL(h)
    ev["geo"] = snap(h)
    return dict([cell("H4-geo", s == NAME2, "host selectedBase after BUILD NEW BASE, CANCEL %r (want %r)" % (s, NAME2))])

def row_c1(x, ev):
    c = x.client
    build_base(x, c, NAME1, ev)
    if not (SEL(c) == NAME1 and KINDS(c) == ["own", "own"]):
        raise Pre("after the lift: client %s (want sel %r, [own, own])" % (snap(c), NAME1))
    press(c, "GEOSCAPE", "GeoscapeState")
    s = SEL(c)
    ev["geo"] = snap(c)
    if KINDS(c) != ["own", "mirror", "mirror", "own"]:
        raise Pre("client kinds %s after GEOSCAPE (want [own, mirror, mirror, own])" % KINDS(c))
    return dict([cell("C1-geo", s == NAME1, "client selectedBase after the new base's GEOSCAPE %r (want %r)" % (s, NAME1))])

def row_c2(x, ev):
    oh, oc = x.own1["host"], x.own1["client"]
    ev["tag"] = "C2"
    # spec (f): the row of the host's new base is not asserted (its mirror's name follow is W2-H65 S-A's)
    return transfer_pair(x, x.client, NAME1, lambda rows: oc in rows and oh in rows and NAME1 not in rows, ev)

def row_l(x, ev):
    oh, oc = x.own1["host"], x.own1["client"]
    ho, hm, co, cm = names(x.host, False), names(x.host, True), names(x.client, False), names(x.client, True)
    ev.update({"hostOwn": ho, "hostMirrors": hm, "clientOwn": co, "clientMirrors": cm})
    ok = ho == [oh, NAME2] and oc in hm and co == [oc, NAME1] and oh in cm
    return dict([cell("L-lists", ok, "host own %s mirrors %s; client own %s mirrors %s (want own [%s, %s] + %s; own [%s, %s] + %s)"
                      % (ho, hm, co, cm, oh, NAME2, oc, oc, NAME1, oh))])

ROWS = (("H0", row_h0), ("H1", row_h1), ("H2", row_h2), ("H3", row_h3), ("H4", row_h4), ("C1", row_c1), ("C2", row_c2),
        ("L", row_l))

# --------------------------------------------------------------------------- driver

class X:
    def __init__(self):
        self.host = GameClient("host", None, make_user_dir("w2h68_host"))
        self.client = GameClient("client", None, make_user_dir("w2h68_client"))
        self.aff, self.own1, self.lift, self.alive = {}, {}, {}, []

def record(cid, ok, msg):
    RESULT[cid] = (ok, msg)
    print("%s %s%s" % ("PASS" if ok else "FAIL", cid, "" if ok else ": " + msg), flush=True)

def capture(x, why):
    out = {"why": why}
    for gc in (x.host, x.client):
        if gc.proc is None or not alive(gc):
            out[gc.name] = {"alive": False, "rc": gc.proc.poll() if gc.proc else None}
            continue
        log = os.path.join(gc.user_dir, "openxcom.log")
        out[gc.name] = {"stack": stk(gc), "geo_state": census(gc), "screen_state": q(gc, {"cmd": "screen_state"}),
                        "widgets": [[w.get("type", "").split("::")[-1], w.get("text"), w.get("visible")] for w in widgets(gc)],
                        "log": [ln.split("\t")[-1][:200] for ln in (open(log, encoding="utf-8", errors="replace").read().splitlines()
                                                                    if os.path.exists(log) else [])[-12:]]}
    return out

def bring_up(x):
    for gc in (x.host, x.client):
        gc.spawn()
        gc.connect(timeout=240)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    session.new_campaign(x.host, x.client, port=KEY)
    geo.slow_clock(x.host, x.client)
    time.sleep(2.0)
    for gc in (x.host, x.client):
        geo.drain_popups(gc)
        x.aff[gc.name] = affine(press(gc, "INTERCEPT", "InterceptState"), press(gc, "CANCEL", "GeoscapeState"))
    for gc in (x.host, x.client):
        own, mir = names(gc, False), names(gc, True)
        if stk(gc) != ["GeoscapeState"] or len(own) != 1 or len(mir) != 1:
            raise Pre("%s: want [GeoscapeState] with one own base + one mirror: %s" % (gc.name, snap(gc)))
        x.own1[gc.name] = own[0]
    print("EVIDENCE B: host %s | client %s | affine %s | OWN %s" % (snap(x.host), snap(x.client), x.aff["host"], x.own1),
          flush=True)

def main():
    crash0, x = crashes(), None
    t0 = time.time()
    try:
        x = X()
        try:
            bring_up(x)
            booted = True
        except Exception as e:  # noqa: BLE001 - a boot miss fails every cell "boot"
            booted = False
            print("CAPTURE boot: %s" % capture(x, "%s: %s" % (type(e).__name__, str(e)[:300])), flush=True)
            for c in CELLS:
                record(c, False, "boot")
        if booted:
            for rid, fn in ROWS:
                ev, vals, miss = {}, {}, None
                try:
                    vals = fn(x, ev)
                except Pre as e:
                    miss = str(e)
                except Exception as e:  # noqa: BLE001 - every row runs after a failure
                    miss = "%s: %s" % (type(e).__name__, str(e)[:300])
                print("EVIDENCE %s: %s" % (rid, " ".join("%s=%s" % kv for kv in ev.items())), flush=True)
                if miss:
                    print("PRECONDITION %s: %s | host %s | client %s" % (rid, miss, snap(x.host), snap(x.client)), flush=True)
                cs = dict(ROWCELLS)[rid]
                for c in cs:
                    record(c, *vals.get(c, (False, "not reached: %s" % (miss or "no value"))))
                print("ROW %s: %s" % (rid, "PASS" if all(RESULT[c][0] for c in cs) else "FAIL"), flush=True)
    finally:
        if x is not None:
            for gc in (x.client, x.host):
                x.alive.append([gc.name, gc.proc is not None and alive(gc)])
                try:
                    if gc.proc is not None and alive(gc):
                        gc.shutdown(expected_returncodes=OKRC)
                except Exception as e:  # noqa: BLE001
                    x.alive[-1].append("shutdown: %s" % str(e)[:200])
        new = sorted(crashes() - crash0)
        if "CRASH" not in RESULT:
            print("EVIDENCE end: newCrash=%s alive=%s crashDir=%s" % ([os.path.basename(p) for p in new][:3], x.alive if x else None,
                                                                     harness.CRASH_DIR), flush=True)
            ok = not new and x is not None and all(a[1] and len(a) == 2 for a in x.alive)
            record("CRASH", ok, "new crash files %d %s; alive until shutdown %s" % (len(new), [os.path.basename(p) for p in new][:3],
                                                                                  x.alive if x else None))
            print("ROW end: %s" % ("PASS" if ok else "FAIL"), flush=True)
    failed = [c for c in CELLS if not RESULT.get(c, (False,))[0]]
    print("SUMMARY: %d/%d cells passed; failing %s; wall %.1f s" % (len(CELLS) - len(failed), len(CELLS), failed, time.time() - t0),
          flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
