"""W2-H71 (spec rewrite/prompts/w2h71_visit_window_pops.md (f); TASK 0 rewrite/w2h71-task0/sa/CONSTANTS.md; leads L-H64-1, L-LT8-1;
rulings R-H71-0 (fix (c)), R-H71-1 (QH71-1 .. -6 (a)), R-H71-2 (the lift cells, R3-pre's log clock)): a partner world landing at a co-op
base visit's end closes only the save window it answers. Today the host's MAP_RESULT_SAVE_PROGRESS handler and the client's
close_save_progress handler pop WHATEVER co-op window is on top: the host's "Items received" (150) vanishes unread (R1), and a visit's
"Synchronizing bases." (50) is popped so the base view (CoopState 55) pops the GeoscapeState and runs alone over a deleted globe (R2 host,
R3 client); a lift click there reads the freed globe (TASK 0: a client crash, F20147).
Three rows, one fresh boot pair each (key "49257", dirs w2h71_r1_* / _r2_* / _r3_*; new_campaign at HOST_POS, slow_clock, both tops Geo
unchanged STABLE_S within BOOT_S; the picker (CAP); the visit: the client's real click on the host base marker). Real presses only, except
the levers save_game_ui (the save trigger) and hold_base_result (TEST-ONLY, commit R0), R2's harness gift and R3's TEST-ONLY
force_stream_key_miss (W2-H66; both S45, below) and the probes.
  R1 (host, L-H64-1; no hold): B; save_game_ui quick (the host's 54, the client's 67); the client's OK, PURCHASE/RECRUIT, ONE arrow click on
    ITEM's row, OK (the host's 150 over the 54); HOLD_PRE; read P; the client's GEOSCAPE; QUICK written (W_SAVE); read W after WAIT_W; the
    host's real OK on a 150. Cells: R1-pre GUARD, R1-notice RED, R1-items GUARD, R1-written GUARD, R1-ok RED, R1-client GUARD, R1-common GUARD.
  S45 (vwp-gap, F20480-F20486): W2-H70 pushes the visitor's own world at a gift made during a visit, so the leave's push carries the same
    bytes and no longer moves the host fnv inside the held 50. R2 makes the gift inside the host's held 50 (the harness gift: the host's
    screens are under its modal 50); R3 holds the gift's push on the client's lever until the client's 50 is up.
  R2 (host, L-LT8-1; host hold): B (H0 = host coop_file_info host_copy_of_client fnv1a64); host hold_base_result HOLD_MS; the host's real
    click on the client's marker; HOLD (W_HOLD); at once the host's soldier gift to the visiting client (hold_gift) and the client's OK on its
    notice; the client's GEOSCAPE; watch until the host's top is BasescapeState for 1 s; read V. Cells: R2-pre GUARD, R2-stack RED,
    R2-geo RED, R2-lift RED, R2-leave GUARD.
  R3 (client, L-LT8-1; client hold, QH71-2 (a)): the client's lever on; the gift; its push held (held: one W2-H70 line, one logged miss);
    B; client hold_base_result; the client's GEOSCAPE, back on [GeoscapeState]; at once its real click on the host's marker; with the
    client's 50 on top the lever off; watch until its top is BasescapeState for 1 s; read V. Cells: R3-pre GUARD (R-H71-2: the start of
    the last host fnv == H0 read is later than the client's logged 50 push, the first changed read ends before its logged BasescapeState
    push), R3-stack RED, R3-geo RED, R3-lift RED, R3-leave GUARD.
  -lift cells (R-H71-2): clicked ONLY on [GeoscapeState, BasescapeState] (else FAIL "not reached (red stack)", no click): the real click on
    the visited base's lift tile -> BriefingState over GeoscapeState within W_UI; the briefing's OK, then end_turn_button -> [GeoscapeState,
    BasescapeState] within W_UI (TASK 0's way back); both alive.
Red (commit R1, the R0 build): exit 2, RED exactly R1-notice, R1-ok, R2-stack, R2-geo, R2-lift, R3-stack, R3-geo, R3-lift (8 of 17).
A precondition miss ends its row ("not reached"); a boot miss fails the row's -pre cell with ONE CAPTURE line. ONE EVIDENCE line per row,
one PASS / FAIL line per cell, the verdict; every row runs; exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100). WV-D95.
"""
import base64, datetime, glob, json, math, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY = "49257"
QUICK, PROBE = "_quick_.asav", "w2h71_probe.sav"
HOST_POS = (0.90, -0.60)
ITEM = "STR_STINGRAY_MISSILES"
SDLK_KP2 = 258
HOLD_MS = 3000
HOLD_PRE, WAIT_W, STABLE_S = 1.0, 0.5, 2.0
W_54, W_67, W_150, W_HOLD, W_UI, W_CLOSE = 10.0, 10.0, 10.0, 10.0, 10.0, 2.0
W_SAVE, W_VISIT, W_VIEW, BOOT_S = 30.0, 60.0, 10.0, 60.0
RC_OK = (0, 3221226505)
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
NEEDLES = {"CLEAR": "[coop-session] clearDeferredSave", "CLOSE54": "[coop] W2-H64: the host's save wait (54) closes",
           "PUSHED": "[coop-gift] pushed client progress to host", "HOLD": "[coop-test] hold_base_result: the base view opens in",
           "HOLDFIRE": "[coop-test] hold_base_result: the held base view opens", "GEOPOP": "[coop-ui] pop  class OpenXcom::GeoscapeState",
           "BSPUSH": "[coop-ui] push class OpenXcom::BasescapeState depth="}
PUSH50 = "[coop-ui] push class OpenXcom::CoopState depth=2"
GIFT70 = "[coop-gift] W2-H70: the stored own world follows a gift"  # W2-H70 E1: the client pushed its stored own world at the gift
MISS = "Failed to read from hash map with key: client_"  # loopData's logged miss of the client's own-world key (W2-H66 lever)
W_LEVER = 5.0  # the lever's miss follows the host's reply to the client's push (W2-H70 T1: the whole stream took 0.23 s)
CRASH_GLOB = os.path.join(harness.CRASH_DIR, "crash_*")  # W2-U8h F9563: this lane's own crash folder (CIT-2 H2)
GEO, BS = "GeoscapeState", "BasescapeState"

class Stop(Exception):
    """a WAIT timed out or a precondition missed: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a value
        return {"error": short(e, 200)}
def pick(r, keys):
    return {k: r.get(k) for k in keys}
def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None
def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]
def top(gc):
    s = stack(gc)
    return s[-1] if s else None
def coop(gc):
    return pick(q(gc, {"cmd": "get_coop"}), ("pendingHostSaveName", "insideCoopBase", "onConnect"))
def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "backVisible"))
def fnv(h):
    return q(h, {"cmd": "coop_file_info", "role": "host_copy_of_client"}).get("fnv1a64")
def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []
def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}
def logtime(ln):
    """the engine log's local timestamp [dd-mm-yyyy_HH-MM-SS.mmm] -> epoch seconds (both games log one machine clock)"""
    return datetime.datetime.strptime(ln.split("]")[0].lstrip("["), "%d-%m-%Y_%H-%M-%S.%f").timestamp()
def first_time(gc, n0, needle):
    return next((logtime(ln) for ln in log(gc)[n0:] if needle in ln), None)
def quick(gc):
    p = os.path.join(gc.user_dir, "xcom1", QUICK)
    return os.stat(p).st_mtime_ns if os.path.exists(p) else None

def cpu():
    c = harness.cpu_load()
    return "%s%s" % (harness.cpu_text(c["cpu"]), " | " + ",".join(c["wardogs"]) if c["wardogs"] else "")

def crashes():
    return set(glob.glob(CRASH_GLOB, recursive=True))

def wait(pred, timeout, interval):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)

def _button(gc, text):
    r = q(gc, {"cmd": "list_widgets"})
    ws = [w for w in r.get("widgets", []) if (w.get("text") or "").strip().lower() == text.lower()]
    return next((w for w in ws if w.get("visible") is True and w.get("hidden") is False), None)

def real_click(gc, text, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        w = _button(gc, text)
        if w is not None:
            return bool(q(gc, {"cmd": "click_widget", "match": w.get("text")}).get("ok"))
        time.sleep(0.02)
    return False

def leave_base(gc):
    """CAP's leave_base: close a sub-screen or a CoopState on top, then the real GEOSCAPE"""
    for _ in range(4):
        t = top(gc)
        if t in ("SoldierInfoState", "SoldiersState", "PurchaseState"):
            real_click(gc, "OK", 5)
            time.sleep(0.5)
        elif t == "CoopState":
            real_click(gc, dlg(gc).get("backText") or "OK", 5)
            time.sleep(0.5)
        else:
            break
    return real_click(gc, "GEOSCAPE", W_UI)

# ----- the globe picker (CAP) -----
def project(G, lon, lat, geom):
    cl, ct = G["globeLon"], G["globeLat"]
    R = ZOOM[int(G["globeZoom"])] * geom["H"]
    x = geom["W"] // 2 + math.floor(R * math.cos(lat) * math.sin(lon - cl))
    y = geom["H"] // 2 + math.floor(R * (math.cos(ct) * math.sin(lat) - math.sin(ct) * math.cos(lat) * math.cos(lon - cl)))
    return x, y

def geometry(gc):
    b = next((x for x in gc.ok({"cmd": "list_widgets"}).get("widgets", []) if str(x.get("text") or "").upper().startswith("INTERCEPT")), None)
    sw, sh = (b["x"] + 63, 2 * (b["y"] + 100)) if b else (320, 200)
    return {"W": sw - 64, "H": sh}

def own_base(gc):
    return next((b for b in gc.ok({"cmd": "geo_state"}).get("bases", []) if not b.get("coopIcon") and not b.get("coopBase")), None)

def click_marker(gc, base, pk, fnv_host=None, fnv_reads=None):
    """the real marker click (CAP offsets, ONE request); with fnv_host each cycle reads the host fnv first (R-H71-2) -> (t50 epoch, codes)"""
    x, y = project(pk["G"], base["lon"], base["lat"], pk["geom"])
    t50, codes = None, []
    for dx, dy in CLICKS:
        gc.ok({"cmd": "inject_input", "kind": "click", "x": int((x + dx) * pk["scale"]["x"] + 1), "y": int((y + dy) * pk["scale"]["y"] + 1)})
        t4, moved = time.time(), False
        while time.time() - t4 < (1.0 if moved else 0.9):
            if fnv_host is not None:
                ta = time.time()
                fnv_reads.append((ta, fnv(fnv_host), time.time()))
            st = stack(gc)
            if st[-1:] == ["CoopState"]:
                moved = True
                if fnv_host is None:  # R-H71-3 (F20152): R3 polls the host fnv and does not use the dialog codes
                    c = dlg(gc).get("code")
                    codes.append(c)
                    t50 = t50 or (time.time() if c == 50 else None)
            elif st[-1:] not in ([GEO], ["MultipleTargetsState"]):
                moved = True
            if moved and fnv_host is None:
                break
            time.sleep(0.005)
        if moved:
            break
    return t50, codes

def _scale(gc):
    cr = next((k for k in (own_base(gc) or {}).get("crafts", []) if not k.get("coop")), None)
    q(gc, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    time.sleep(0.4)
    cw = q(gc, {"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.5)
    return cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}

def read_globes(path):
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    for d in docs:
        if "bases" in d:
            out["host"] = {k: d.get(k) for k in ("globeLon", "globeLat", "globeZoom")}
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
            w = next((z for z in yaml.load_all(b.decode("utf-8", errors="replace"), Loader=loader) if isinstance(z, dict) and "bases" in z), None) or {}
            out["client"] = {k: w.get(k) for k in ("globeLon", "globeLat", "globeZoom")}
    return out

def picker(x):
    h, c = x.host, x.client
    qpath, spath = (os.path.join(h.user_dir, "xcom1", f) for f in (QUICK, PROBE))
    t0 = time.time()
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, W_SAVE, 0.25)
    time.sleep(1.0)
    geo.drain_popups(h)
    q(h, {"cmd": "save_game", "file": PROBE})
    okn, _s = wait(lambda: os.path.exists(spath) and os.path.getsize(spath) > 0, W_SAVE, 0.25)
    time.sleep(1.0)
    G = read_globes(spath) if okn else {}
    x.pkC = {"G": G.get("client"), "geom": geometry(c), "scale": _scale(c)}
    x.pkH = {"G": G.get("host"), "geom": geometry(h), "scale": _scale(h)}
    for pk in (x.pkC, x.pkH):
        if not pk["G"] or None in pk["G"].values() or not pk["scale"]:
            raise Stop("picker geometry %s" % json.dumps(pk, default=str)[:300])
    if stack(c)[-1:] != [GEO] or stack(h)[-1:] != [GEO]:
        raise Stop("picker: tops not GeoscapeState %s %s" % (stack(h), stack(c)))

def visit(x):
    _t, codes = click_marker(x.client, x.hb, x.pkC)
    v, _s = wait(lambda: coop(x.client).get("insideCoopBase") and stack(x.client)[-1:] == [BS], W_VISIT, 0.25)
    if not v:
        raise Stop("the client not inside the host base (codes %s, stack %s)" % (codes, stack(x.client)))

def gift(x):
    """CAP host_gift_to_client: BASES, SOLDIERS, the first row, KP2, the client's button; the client's notice OK; the host back on [Geo]"""
    h, c = x.host, x.client
    real_click(h, "BASES", W_UI)
    wait(lambda: top(h) == BS, W_UI, 0.02)
    real_click(h, "SOLDIERS", W_UI)
    v, _s = wait(lambda: top(h) == "SoldiersState", W_UI, 0.02)
    tl = next((w for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if "TextList" in str(w.get("type"))), None)
    if not v or not tl:
        raise Stop("gift: no SoldiersState / TextList on the host")
    sc = x.pkH["scale"]
    q(h, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 30) * sc["x"] + 1), "y": int((tl["y"] + 3) * sc["y"] + 1)})
    if not wait(lambda: top(h) == "SoldierInfoState", W_UI, 0.02)[0]:
        raise Stop("gift: no SoldierInfoState on the host")
    q(h, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
    if not wait(lambda: top(h) == "GiftSoldierMenu", W_UI, 0.02)[0]:
        raise Stop("gift: no GiftSoldierMenu on the host")
    btns = [w.get("text") for w in q(h, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
    real_click(h, next((t for t in btns if "client" in t.lower()), "ClientPlayer"), W_UI)
    if not wait(lambda: top(c) == "GiftNoticeState", W_UI, 0.02)[0]:
        raise Stop("gift: no GiftNoticeState on the client")
    real_click(c, "OK", W_UI)
    for _ in range(3):
        if top(h) in ("SoldierInfoState", "SoldiersState"):
            real_click(h, "OK", W_UI)
            time.sleep(0.4)
    real_click(h, "GEOSCAPE", W_UI)
    if not wait(lambda: stack(h) == [GEO], W_UI, 0.02)[0]:
        raise Stop("gift: the host not back on [GeoscapeState]: %s" % stack(h))
    time.sleep(1.0)

def hold_gift(x, ev):
    """R2 (S45, vwp-gap F20484): the host's soldier gift to the visiting client INSIDE the host's held 50. W2-H70 pushes the client's own
    world at the gift, so the gift (no longer the leave, whose push now carries the same bytes) is the client world that changes the host
    fnv while the 50 is up. The host's screens sit under its own modal 50, so the gift is the harness `gift` command: the call
    GiftSoldierMenu's button makes (giftSoldier(soldier, owner, true)) for the host base's first soldier (the original first SOLDIERS row) to
    the client (owner 1). Then the client's real OK on its GiftNoticeState."""
    h, c = x.host, x.client
    hb = next((b for b in q(h, {"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopIcon") and not b.get("coopBaseFlag")), None)
    name = ((hb or {}).get("soldiers") or [{}])[0].get("name")
    if not name:
        raise Stop("hold_gift: no soldier in the host's own base: %s" % short(hb))
    g = q(h, {"cmd": "gift", "name": name, "owner": 1})
    v, s = wait(lambda: top(c) == "GiftNoticeState", W_UI, 0.02)
    ev["gift"] = {"soldier": name, "ok": g.get("ok"), "owner": (g.get("soldier") or {}).get("owner"), "notice s": s, "host": stack(h)}
    if not (g.get("ok") and v):
        raise Stop("hold_gift: %s" % ev["gift"])
    real_click(c, "OK", W_UI)

def lever(x, on):
    """R3 (S45, vwp-gap F20483): W2-H66's TEST-ONLY force_stream_key_miss on the client: while on, its host-bound stream finds no blob and
    retries, so the world W2-H70 pushes at the gift does not land before B; off (with the client's 50 up), the held stream sends the
    client's current own-world blob. Not usable in R2: the held stream also holds the client's base stream the host's visit needs (F20483)"""
    lv = q(x.client, {"cmd": "force_stream_key_miss", "on": on})
    if not (lv.get("ok") and lv.get("on") is on):
        raise Stop("force_stream_key_miss %s not set on the client: %s" % (on, lv))

def held(x, cr, n_c):
    """after the gift: the client's ONE W2-H70 push and the lever's ONE logged miss of it (a crash file new since cr) -> ev-ready dict"""
    def probe():
        n70 = sum(1 for ln in log(x.client)[n_c:] if GIFT70 in ln)
        ms = sorted(os.path.basename(p) for p in crashes() - cr if MISS in open(p, encoding="utf-8", errors="replace").read())
        return {"n70": n70, "misses": ms}
    v, s = wait(lambda: (lambda d: d if d["n70"] == 1 and len(d["misses"]) == 1 else None)(probe()), W_LEVER, 0.02)
    if not v:
        raise Stop("the W2-H70 push not held by the lever: %s" % probe())
    v["s"] = s
    return v

def baseline(x):
    x.n_h, x.n_c, x.cr0, x.H0, x.q0 = len(log(x.host)), len(log(x.client)), crashes(), fnv(x.host), quick(x.host)

def watch(x, gc, fnv_reads):
    """every ~0.02 s: the host fnv (read first, start / end epochs), then gc's stack; until gc's top is BasescapeState for 1 s (W_VIEW)"""
    t0, last, tch, firsts = time.time(), None, time.time(), {}
    while time.time() - t0 < W_VIEW:
        ta = time.time()
        fnv_reads.append((ta, fnv(x.host), time.time()))
        st = stack(gc)
        if st[-1:] == ["CoopState"] and "c50" not in firsts and dlg(gc).get("code") == 50:
            firsts["c50"] = time.time()
        if st[-1:] == [BS] and "bs" not in firsts:
            firsts["bs"] = time.time()
        if st != last:
            last, tch = st, time.time()
        if st[-1:] == [BS] and time.time() - tch >= 1.0:
            break
        time.sleep(0.02)
    return firsts

def lift(x, gc, base_name, ev):
    """the -lift cell's drive on [Geo, Basescape] (R-H71-2): the lift click -> BriefingState over Geo; OK; end_turn_button -> [Geo, Basescape]"""
    g = q(gc, {"cmd": "geo_state"})
    b = next((z for z in g.get("bases", []) if z.get("name") == base_name), None) or {}
    lf = next((f for f in b.get("facilities") or [] if "LIFT" in str(f.get("type"))), None)
    if not lf:
        ev["lift"] = "no lift tile in %s" % [z.get("name") for z in g.get("bases", [])]
        return False
    sc = x.pkH["scale"] if gc is x.host else x.pkC["scale"]
    px, py = lf["x"] * 32 + 16, 8 + lf["y"] * 32 + 16
    q(gc, {"cmd": "inject_input", "kind": "click", "x": int(px * sc["x"] + 1), "y": int(py * sc["y"] + 1)})
    v1, s1 = wait(lambda: (not alive(gc)) or top(gc) == "BriefingState", W_UI, 0.02)
    st1 = stack(gc) if alive(gc) else ["DEAD"]
    ok1 = bool(v1) and st1[-1:] == ["BriefingState"] and GEO in st1
    ok2 = ok1 and real_click(gc, "OK", W_UI) and bool(wait(lambda: top(gc) == "BattlescapeState", W_UI, 0.02)[0])
    eb = ok2 and q(gc, {"cmd": "battle_action", "action": "end_turn_button"}).get("ok")
    v3, s3 = wait(lambda: stack(gc) == [GEO, BS], W_UI, 0.02) if eb else (None, None)
    ev["lift"] = {"tile": [lf["x"], lf["y"]], "briefing": [st1, s1], "ok": ok2, "endTurn": eb, "back": [stack(gc) if alive(gc) else "DEAD", s3]}
    return bool(ok1 and ok2 and v3 and alive(x.host) and alive(x.client))

class Row:
    """cells are recorded as decided; end() prints EVIDENCE, every cell, ONE CAPTURE line on a failure and the row verdict"""
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.ev, self.lines = rid, cells, x, [], set(), {"cpu": x.cpu}, []

    def cell(self, cid, kind, label, ok):
        self.lines.append("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label))
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            self.lines.append("FAIL %s: not reached (%s)" % (cid, str(why)[:200]))
            self.fails.append(cid)

    def end(self, results, cap=None):
        x = self.x
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)
        print("\n".join(self.lines), flush=True)
        if self.fails:
            if cap is None:
                cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc),
                           "log": [ln.split("\t")[-1][:120] for ln in log(gc) if "[coop" in ln][-12:]}
                   for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
                cap["new crash"] = sorted(crashes() - (x.cr0 or set()))
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

def guard(r, cid, label, fn):
    try:
        v = fn()
    except Exception:
        r.cell(cid, "GUARD", label, False)
        raise
    r.cell(cid, "GUARD", label, True)
    return v

def row_r1(x, results):
    r = Row("R1", ["R1-pre", "R1-notice", "R1-items", "R1-written", "R1-ok", "R1-client", "R1-common"], x)
    if x.err:
        return boot_miss(r, results)
    h, c, ev = x.host, x.client, r.ev

    def pre():
        visit(x)
        baseline(x)
        ev["sessionS"] = session.wait_coop_session(h)   # F24296: the 54 needs the host's live session
        q(h, {"cmd": "save_game_ui", "type": "quick"})
        ev["54 s"] = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 54, W_54, 0.005)[1]
        if not wait(lambda: dlg(c).get("code") == 67, W_67, 0.02)[0] or top(h) != "CoopState":
            raise Stop("the 54 / the client's 67 not seen: %s %s" % (stack(h), dlg(c)))
        real_click(c, dlg(c).get("backText") or "OK", W_UI)
        time.sleep(0.3)
        real_click(c, "PURCHASE/RECRUIT", W_UI)
        wait(lambda: top(c) == "PurchaseState" and (q(c, {"cmd": "screen_rows"}).get("rows") or []), W_UI, 0.02)
        items = [z.get("item") for z in q(c, {"cmd": "screen_rows"}).get("rows") or []]
        tl = next((w for w in q(c, {"cmd": "list_widgets"}).get("widgets", []) if "TextList" in str(w.get("type"))), None)
        if ITEM not in items or not tl:
            raise Stop("no PurchaseState row %s / TextList" % ITEM)
        sc = x.pkC["scale"]
        bx, by = tl["x"] + 227 + 5, tl["y"] + items.index(ITEM) * 8 + 4
        tc = time.time()   # F24297: one red lost this click (amount 0); the client log's PurchaseState push time is comparable
        ev["buyClick"] = {"at": "%s.%03d" % (time.strftime("%H-%M-%S", time.localtime(tc)), int(tc * 1000) % 1000),
                          "tl": {k: tl.get(k) for k in ("visible", "hidden")}}
        q(c, {"cmd": "inject_input", "kind": "click", "x": int(bx * sc["x"] + 1), "y": int(by * sc["y"] + 1)})
        time.sleep(0.4)
        amts = {z.get("item"): (z.get("cells") or [None] * 4)[3] for z in q(c, {"cmd": "screen_rows"}).get("rows") or []}
        if {k: v for k, v in amts.items() if v not in (None, "0", "")} != {ITEM: "1"}:
            raise Stop("ITEM's amount not 1 after one arrow click: %s" % amts)
        real_click(c, "OK", W_UI)
        ev["150 s"] = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 150, W_150, 0.005)[1]
        time.sleep(HOLD_PRE)
        P = ev["P"] = {"host": stack(h), "dlg": dlg(h), "pending": coop(h).get("pendingHostSaveName"), "client": stack(c),
                       "inside": coop(c).get("insideCoopBase")}
        if not (P["host"] == [GEO, "CoopState", "CoopState"] and P["dlg"].get("code") == 150 and P["pending"] == QUICK and P["inside"]):
            raise Stop("read P: %s" % P)
    try:
        guard(r, "R1-pre", "read P: host [GeoscapeState, CoopState, CoopState], top 150 over the 54 (seen on top, %s armed); the client inside "
              "the host base" % QUICK, pre)
        tg = time.time()
        leave_base(c)
        mt, tcl = [x.q0], None
        while time.time() - tg < W_SAVE:
            m = quick(h)
            if m != mt[-1]:
                mt.append(m)
            if tcl is None and stack(c) == [GEO]:
                tcl = round(time.time() - tg, 3)
            if len(mt) > 1 and tcl is not None:
                break
            time.sleep(0.02)
        time.sleep(WAIT_W)
        n = counts(h, x.n_h)
        W = ev["W"] = {"stack": stack(h), "dlg": dlg(h), "pending": coop(h).get("pendingHostSaveName"), "needles": n, "client s": tcl,
                       "transfers": next((b.get("transfers") for b in h.ok({"cmd": "geo_state"}).get("bases", []) if b.get("name") == x.hb["name"]), None)}
        r.cell("R1-notice", "RED", "read W: host top CoopState 150 with its OK visible, 3 states (red today: [GeoscapeState], the 150 popped "
               "unread, F19760)", W["stack"] == [GEO, "CoopState", "CoopState"] and W["dlg"].get("code") == 150 and W["dlg"].get("backVisible") is True)
        r.cell("R1-items", "GUARD", "read W: %s in %s's transfers, qty 1" % (ITEM, x.hb["name"]),
               any(t.get("rule") == ITEM and t.get("qty") == 1 for t in W["transfers"] or []))
        if W["stack"][-1:] == ["CoopState"] and W["dlg"].get("code") == 150:
            n0 = len(log(h))
            ok = real_click(h, W["dlg"].get("backText") or "OK", W_UI)
            vb, sb = wait(lambda: stack(h) == [GEO], W_CLOSE, 0.005)
            c54 = sum(1 for ln in log(h)[n0:] if NEEDLES["CLOSE54"] in ln)
            ev["OK"] = {"click": ok, "back s": sb, "close54": c54}
            r.cell("R1-ok", "RED", "the host's real OK on the 150 -> [GeoscapeState] within %.0f s, CLOSE54 +1" % W_CLOSE, bool(ok and vb and c54 == 1))
        else:
            r.cell("R1-ok", "RED", "not reached (no 150 on top at read W; red today)", False)
        E = ev["E"] = {"mtimes": mt + [quick(h)], "needles": counts(h, x.n_h)}
        r.cell("R1-written", "GUARD", "%s's mtime moved exactly once since B; CLEAR +1; pendingHostSaveName \"\" at W" % QUICK,
               len(set(E["mtimes"])) == 2 and E["needles"]["CLEAR"] == 1 and W["pending"] == "")
        r.cell("R1-client", "GUARD", "the client's stack == [GeoscapeState] within %.0f s of its GEOSCAPE (its 53 closed)" % W_SAVE, tcl is not None)
        common(r, "R1", x)
    except Exception as e:
        r.stop(e)
    r.end(results)

def common(r, p, x):
    nc = sorted(crashes() - x.cr0)
    r.cell(p + "-common", "GUARD", "both alive; no new crash file since B", alive(x.host) and alive(x.client) and not nc)

def visit_row(x, results, rid, who):
    """R2 (who = host) / R3 (who = client)"""
    p = rid
    r = Row(rid, [p + "-pre", p + "-stack", p + "-geo", p + "-lift", p + "-leave"], x)
    if x.err:
        return boot_miss(r, results)
    h, c, ev = x.host, x.client, r.ev
    gc = h if who == "host" else c
    reads = []

    def pre():
        visit(x)
        if who == "client":
            cr, n_c = crashes(), len(log(c))
            lever(x, True)
            gift(x)
            ev["held"] = held(x, cr, n_c)
        baseline(x)
        lv = q(gc, {"cmd": "hold_base_result", "ms": HOLD_MS})
        if lv.get("ms") != HOLD_MS:
            raise Stop("hold_base_result reply %s" % lv)
        if who == "host":
            x.nk = len(log(h))
            t50, codes = click_marker(h, x.cb, x.pkH)
            hl, ev["HOLD s"] = wait(lambda: any(NEEDLES["HOLD"] in ln for ln in log(h)[x.nk:]), W_HOLD, 0.02)
            ev["at HOLD"] = [stack(h), dlg(h).get("code")]
            if not hl or ev["at HOLD"] != [[GEO, "CoopState"], 50]:
                raise Stop("HOLD with the 50 on top: %s (codes %s)" % (ev["at HOLD"], codes))
            hold_gift(x, ev)
            leave_base(c)
            f = watch(x, h, reads)
            ch = [z for z in reads if z[1] and z[1] != x.H0]
            ev["order"] = {"t50": t50, "fnv": ch[0][0] if ch else None, "bs": f.get("bs")}
            ok = bool(t50 and ch and f.get("bs") and t50 < ch[0][0] < f["bs"])
        else:
            leave_base(c)
            if not wait(lambda: stack(c) == [GEO], W_UI, 0.005)[0]:
                raise Stop("the client not back on [GeoscapeState]: %s" % stack(c))
            x.nk = len(log(c))
            click_marker(c, x.hb, x.pkC, h, reads)
            ev["at release"] = [stack(c), dlg(c).get("code")]
            if ev["at release"] != [[GEO, "CoopState"], 50]:
                raise Stop("the client's 50 not on top at the lever's release: %s" % ev["at release"])
            lever(x, False)
            watch(x, c, reads)
            t50, tbs = first_time(c, x.nk, PUSH50), first_time(c, x.nk, NEEDLES["BSPUSH"])
            h0 = [z for z in reads if z[1] == x.H0]
            ch = [z for z in reads if z[1] and z[1] != x.H0]
            ev["order"] = {"log50": t50, "lastH0start": h0[-1][0] if h0 else None, "firstChangedEnd": ch[0][2] if ch else None, "logBS": tbs}
            ok = bool(t50 and tbs and h0 and ch and h0[-1][0] > t50 and ch[0][2] < tbs)
        n = ev["needles"] = {"host": counts(h, x.n_h), "client": counts(c, x.n_c)}
        hold = n[who]["HOLD"] == 1
        if not (ok and n["client"]["PUSHED"] == 1 and hold):
            raise Stop("the landing not inside the held 50: %s" % json.dumps({"order": ev["order"], "needles": n}, default=str))
    try:
        if who == "host":
            label = ("the host's top CoopState 50 when HOLD appeared; the client's PUSHED +1 since B; the host fnv first differed from H0 after the "
                     "host's 50 was first seen and before its BasescapeState")
        else:
            label = ("the client's PUSHED +1 and HOLD since B; the last host fnv == H0 read started after the client's logged 50 push and the first "
                     "changed read ended before its logged BasescapeState push (R-H71-2)")
        guard(r, p + "-pre", label, pre)
        V = ev["V"] = stack(gc)
        r.cell(p + "-stack", "RED", "read V: the %s stack == [GeoscapeState, BasescapeState] (red today: [BasescapeState])" % who, V == [GEO, BS])
        lines = [ln.split("\t")[-1] for ln in log(gc)[x.nk:]]
        geopop, bsp = sum(1 for ln in lines if NEEDLES["GEOPOP"] in ln), [ln for ln in lines if NEEDLES["BSPUSH"] in ln]
        ev["geo"] = {"GEOPOP": geopop, "BSPUSH": bsp}
        r.cell(p + "-geo", "RED", "the %s log since the click: GEOPOP 0 and the BSPUSH line ends depth=2 (red today: GEOPOP 1, depth=1)" % who,
               geopop == 0 and len(bsp) == 1 and bsp[0].endswith("depth=2"))
        if V == [GEO, BS]:
            r.cell(p + "-lift", "RED", "the real lift click -> BriefingState over GeoscapeState; OK, end_turn_button -> [GeoscapeState, "
                   "BasescapeState] within %.0f s; both alive" % W_UI, lift(x, gc, (x.cb if who == "host" else x.hb)["name"], ev))
        else:
            r.cell(p + "-lift", "RED", "not reached (red stack %s: no lift click on it, R-H71-2)" % V, False)
        ok = real_click(gc, "GEOSCAPE", W_UI)
        vb, ev["leave s"] = wait(lambda: stack(gc) == [GEO], W_UI, 0.02)
        nc = sorted(crashes() - x.cr0)
        r.cell(p + "-leave", "GUARD", "the %s's real GEOSCAPE -> [GeoscapeState] within %.0f s; both alive; no new crash file since B" % (who, W_UI),
               bool(ok and vb and alive(h) and alive(c) and not nc))
    except Exception as e:
        r.stop(e)
    r.end(results)

def boot_miss(r, results):
    r.cell(r.cells[0], "GUARD", "boot: both tops GeoscapeState unchanged %.0f s within %.0f s, picker (%s)" % (STABLE_S, BOOT_S, r.x.err), False)
    r.stop("boot")
    r.end(results, cap=r.x.cap)

def boot(rid, tag):
    x = SimpleNamespace(rid=rid, tag=tag, host=None, client=None, err=None, cap=None, cpu=cpu(), hb=None, cb=None, cr0=set(), nk=0, n_h=0, n_c=0)
    try:
        x.host, x.client = GameClient("host", None, make_user_dir(tag + "_host")), GameClient("client", None, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        session.HOST_LON, session.HOST_LAT = HOST_POS
        session.new_campaign(x.host, x.client, port=KEY)
        geo.slow_clock(x.host, x.client)
        t0, last, tch = time.time(), None, time.time()
        while True:
            s = (tuple(stack(x.host)), tuple(stack(x.client)))
            if s != last:
                last, tch = s, time.time()
            if s[0] and s[1] and s[0][-1] == s[1][-1] == GEO and time.time() - tch >= STABLE_S:
                break
            if time.time() - t0 > BOOT_S:
                raise Stop("both tops GeoscapeState unchanged %.0f s: not within %.0f s" % (STABLE_S, BOOT_S))
            time.sleep(0.25)
        x.hb, x.cb = own_base(x.host), own_base(x.client)
        picker(x)
    except Exception as e:
        x.err = short(e, 600)
        x.cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc), "log": [ln.split("\t")[-1][:200] for ln in log(gc)[-40:]]}
                 for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
    return x

def shut(x):
    failed = []
    for gc in (x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

ROWS = (("R1", "w2h71_r1", lambda x, res: row_r1(x, res)), ("R2", "w2h71_r2", lambda x, res: visit_row(x, res, "R2", "host")),
        ("R3", "w2h71_r3", lambda x, res: visit_row(x, res, "R3", "client")))

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for rid, tag, row in ROWS:
        tb = time.time()
        x = boot(rid, tag)
        try:
            row(x, results)
        finally:
            failed += shut(x)
        walls[rid] = round(time.time() - tb, 1)
    failed += [rid for rid, _t, _r in ROWS if not results.get(rid)]
    print("\ntest_visit_window_pops: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _t, _r in ROWS if results.get(rid)), len(ROWS), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
