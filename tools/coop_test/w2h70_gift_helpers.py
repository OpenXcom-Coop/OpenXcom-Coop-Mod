"""Shared helpers of the W2-H70 tests (spec docs rewrite/prompts, W2-H70 "a soldier gifted during a co-op base visit", sections (f) and
Appendix B; TASK 0 rewrite/w2h70-task0/sa/CONSTANTS.md; lead L-H64-2, rulings R-H70-0 and R-H70-2): the boot, every construction step, the
probes, the save-file read and the row runner that test_w2_gift_during_visit.py (rows R1-R3) and test_w2_gift_during_visit_rejoin.py
(rows R4-R6) import. Copied from the capture rewrite/lh64-2-cap/cap.py and W2-H64's TASK 0 rewrite/w2h64-task0/sa/t0_h64a.py (never
imported). Every press is real (click_widget on a visible button, inject_input on a pixel or SDLK_KP2); every probe is an existing
TestServer command. A construction step that misses its precondition raises Stop (its row ends there); run_row prints one EVIDENCE line
per row, one PASS / FAIL line per cell and the row verdict; main returns 0 only when every cell passed, else 2 (WV-D99 / WV-D100).
WV-D95: one foreground run per invocation."""
import base64, glob, json, math, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

QUICK, PROBE = "_quick_.asav", "h70_probe.sav"
HOST_POS = (0.90, -0.60)
GIFTNAMES = ("Zzz Gift", "Zzz Gift2", "Zzz Gift3")
SDLK_KP2 = 258
POLL_S, SEEN54_S, W_67, W_UI, W_NOTICE, W_VISIT, W_SAVE, W_WRITE = 0.005, 10.0, 10.0, 5.0, 10.0, 60.0, 30.0, 10.0
HOLD_L, HOLD_P, HOLD_R, W_DROP, JOIN_S, W_RESUME, W_LEAVE, STABLE_S, BOOT_S = 2.0, 1.0, 3.0, 30.0, 120.0, 60.0, 30.0, 2.0, 60.0
RC_OK = (0, 3221226505)
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
HASH = "Failed to read from hash map"
T0_PUSH = 0.0  # the host's stored partner world after a gift: one sample (TASK 0 polled it)

class Stop(Exception):
    """a WAIT timed out or a precondition missed: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
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
    return pick(q(gc, {"cmd": "get_coop"}), ("pendingHostSaveName", "saveID", "clientName", "hostName", "resumeAck", "insideCoopBase"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "backVisible"))

def blob(gc):
    """coop_file_info: the host's stored partner world; the client's "basehost" and its own-world blob"""
    if not alive(gc):
        return None
    if gc.name == "host":
        return pick(q(gc, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key", "present", "bytes", "fnv1a64"))
    return {"basehost": pick(q(gc, {"cmd": "coop_file_info", "key": "basehost"}), ("present", "bytes", "fnv1a64")),
            "own": pick(q(gc, {"cmd": "coop_file_info", "role": "own_world"}), ("key", "present", "bytes", "fnv1a64"))}

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def gift_lines(gc, n0):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if "[coop-gift]" in ln]

def files(gc):
    """the host's master save folder <user_dir>/xcom1: name -> [bytes, mtime_ns]"""
    out = {}
    for p in sorted(glob.glob(os.path.join(gc.user_dir, "xcom1", "*"))):
        try:
            if os.path.isfile(p):
                st = os.stat(p)
                out[os.path.basename(p)] = [st.st_size, st.st_mtime_ns]
        except FileNotFoundError:  # cap-tail (F24062): renamed after the listing (the save's .bak -> .asav move)
            pass
    return out

def crash():
    """every file in this lane's crash folder (harness.CRASH_DIR)"""
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "*")))

def crash_new(c0):
    new = sorted(crash() - c0)
    hl = [p for p in new if open(p, encoding="utf-8", errors="replace").read().find(HASH) >= 0]
    return {"new": len(new), "hashlogs": len(hl), "dmp": [os.path.basename(p) for p in new if p.lower().endswith(".dmp")],
            "sample": [os.path.basename(p) for p in new[:3]]}

def cpu():
    c = harness.cpu_load()
    return "%s%s" % (harness.cpu_text(c["cpu"]), " | " + ",".join(c["wardogs"]) if c["wardogs"] else "")

def fnv(b):
    """FNV-1a 64 (TestServer coop_file_info), 16 hex digits"""
    h = 1469598103934665603
    for ch in b:
        h = ((h ^ ch) * 1099511628211) % (1 << 64)
    return "%016x" % h

def _sols(w):
    return [[bb.get("name"), s.get("name"), s.get("id")] for bb in w.get("bases") or [] for s in bb.get("soldiers") or []]

def read_save(path):
    """PyYAML load_all: the host half (world bases' soldiers) and every coopClientSaves entry (base64 blob, parsed): key, bytes, fnv,
    soldiers [base, name, id]; the probe's globe"""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    out = {"bytes": os.path.getsize(path), "host": [], "entries": []}
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    for d in docs:
        if "bases" in d:
            out["host"] = _sols(d)
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
            w = next((x for x in yaml.load_all(b.decode("utf-8", errors="replace"), Loader=loader) if isinstance(x, dict) and "bases" in x), {})
            out["entries"].append({"key": e.get("key"), "bytes": len(b), "fnv1a64": fnv(b), "soldiers": _sols(w),
                                   "globe": {k: w.get(k) for k in ("globeLon", "globeLat", "globeZoom")}})
    return out

def probe_globe(path):
    """CIT-SLEEP1 (F24288): the probe save's first entry globe once the file parses with every globe value set, else None"""
    try:
        g = ((read_save(path)["entries"]) or [{}])[0].get("globe") or {}
    except Exception:  # a file still being written is a not-yet
        return None
    return g if g and None not in g.values() else None

def halves(path, gift):
    """QUICK's halves: where GIFTNAME is (host half [base, id]; client entries [key, base, id])"""
    f = read_save(path)
    return {"bytes": f["bytes"], "keys": [[e["key"], e["bytes"], e["fnv1a64"]] for e in f["entries"]],
            "host": [[b, i] for b, n, i in f["host"] if n == gift],
            "client": [[e["key"], b, i] for e in f["entries"] for b, n, i in e["soldiers"] if n == gift]}

def file_once_host(hv):
    return len(hv["host"]) == 1 and not hv["client"]

def file_once_client(hv):
    return not hv["host"] and len(hv["client"]) == 1

def wait(pred, timeout, interval=0.05):
    """poll pred every interval up to timeout -> (value or None, seconds)"""
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 3)
        time.sleep(interval)

def real_click(gc, text, timeout):
    """a real press: click_widget once list_widgets shows the button visible -> ok"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if (w.get("text") or "").strip().lower() == text.lower()]
        if any(w.get("visible") is True and w.get("hidden") is False for w in ws):
            return bool(q(gc, {"cmd": "click_widget", "match": text}).get("ok"))
        time.sleep(0.02)
    return False

def buttons(gc):
    return [w.get("text") for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]

def textlist(gc):
    return next((w for w in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if "TextList" in str(w.get("type"))), None)

def project(G, lon, lat, geom):
    cl, ct = G["globeLon"], G["globeLat"]
    R = ZOOM[int(G["globeZoom"])] * geom["H"]
    x = geom["W"] // 2 + math.floor(R * math.cos(lat) * math.sin(lon - cl))
    y = geom["H"] // 2 + math.floor(R * (math.cos(ct) * math.sin(lat) - math.sin(ct) * math.cos(lat) * math.cos(lon - cl)))
    return x, y

def geometry(gc):
    b = next((x for x in q(gc, {"cmd": "list_widgets"}).get("widgets", []) if str(x.get("text") or "").upper().startswith("INTERCEPT")), None)
    sw, sh = (b["x"] + 63, 2 * (b["y"] + 100)) if b else (320, 200)
    return {"W": sw - 64, "H": sh}

def own_base(gc):
    return next((b for b in q(gc, {"cmd": "geo_state"}).get("bases", []) if not b.get("coopIcon") and not b.get("coopBase")), None)

def soldiers(gc):
    return q(gc, {"cmd": "get_soldiers"}).get("bases", [])

def own(gc, gift):
    """GIFTNAME on the machine's own bases (coopBaseFlag and coopIcon false): [base, id, owner, coopBase]"""
    return [[b.get("name"), z.get("id"), z.get("owner"), z.get("coopBase")] for b in soldiers(gc)
            if not b.get("coopBaseFlag") and not b.get("coopIcon") for z in b.get("soldiers", []) if z.get("name") == gift]

def census(x):
    d = {}
    for n in ("host", "client"):
        gc = getattr(x, n)
        d[n] = own(gc, x.gift) if alive(gc) else None
        d[n + "All"] = [[b.get("name"), bool(b.get("coopBaseFlag")), bool(b.get("coopIcon")), z.get("id"), z.get("owner")] for b in soldiers(gc)
                        for z in b.get("soldiers", []) if z.get("name") == x.gift] if alive(gc) else None
    return d

def once_host(c):
    return c["host"] is not None and c["client"] is not None and len(c["host"]) == 1 and not c["client"]

def once_client(c):
    return c["host"] is not None and c["client"] is not None and len(c["client"]) == 1 and not c["host"]

def click_globe(gc, lon, lat, pk):
    """the client's real globe click: inject_input at the projected pixel (x scale, + 1), the next offset while GeoscapeState stays top"""
    x, y = project(pk["G"], lon, lat, pk["geom"])
    for dx, dy in CLICKS:
        q(gc, {"cmd": "inject_input", "kind": "click", "x": int((x + dx) * pk["scale"]["x"] + 1), "y": int((y + dy) * pk["scale"]["y"] + 1)})
        time.sleep(0.9)
        if top(gc) != "GeoscapeState":
            return [x + dx, y + dy]
    return None

def settle(x):
    t0, last, tch = time.time(), None, time.time()
    while True:
        s = (tuple(stack(x.host)), tuple(stack(x.client)))
        if s != last:
            last, tch = s, time.time()
        if s[0] and s[1] and s[0][-1] == s[1][-1] == "GeoscapeState" and time.time() - tch >= STABLE_S:
            return round(time.time() - t0, 3)
        if time.time() - t0 > BOOT_S:
            raise Stop("both tops GeoscapeState unchanged %.0f s: not within %.0f s: %s" % (STABLE_S, BOOT_S, s))
        time.sleep(0.1)

def boot(tag, key, saves=None):
    """CPU, host + client spawn, connect; new: the host base at HOST_POS, session.new_campaign(port=key) SEPARATE gm1 tcp,
    geo.slow_clock; reload (saves): resume_campaign(QUICK); both tops GeoscapeState unchanged STABLE_S within BOOT_S (else x.err, x.cap)"""
    x = SimpleNamespace(tag=tag, key=key, host=None, client=None, dead=[], err=None, cap=None, cpu=cpu(), hb=None, pk=None, gift=None,
                        n_h=0, n_c=0, c0=crash(), F0=None)
    try:
        x.host = GameClient("host", None, make_user_dir(tag + "_host", saves=saves or ()))
        x.client = GameClient("client", None, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        if saves:
            session.resume_campaign(x.host, x.client, QUICK, port=key)
        else:
            session.HOST_LON, session.HOST_LAT = HOST_POS
            session.new_campaign(x.host, x.client, port=key)
            geo.slow_clock(x.host, x.client)
        x.settle = settle(x)
        x.hb = own_base(x.host)
    except Exception as e:
        x.err = short(e, 600)
        x.cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc)} for n, gc in (("host", x.host), ("client", x.client))
                 if alive(gc)}
    return x

def shut(x):
    """every machine of the boot still running (a killed client was reaped by kill()) -> the shutdown failures"""
    failed = []
    for gc in [x.client, x.host] + x.dead:
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

def pick_gift(x):
    names = {z.get("name") for gc in (x.host, x.client) for b in soldiers(gc) for z in b.get("soldiers", [])}
    x.gift = next((g for g in GIFTNAMES if g not in names), None)
    if x.gift is None:
        raise Stop("every GIFTNAME already in a roster")

def stage_guest(x, ev):
    """the client's first own-base soldier not in a craft (the next such one when the transfer refuses; none: the first) renamed
    GIFTNAME, transfer_to_coop_base to the host's base; the host's 150 closed by a real OK; the host back on GeoscapeState"""
    c, h = x.client, x.host
    pick_gift(x)
    ob = next((b for b in soldiers(c) if not b.get("coopBaseFlag") and not b.get("coopIcon") and b.get("soldiers")), None)
    sols = [z for z in (ob or {}).get("soldiers", []) if not z.get("craft")] or ((ob or {}).get("soldiers") or [])[:1]
    tries, tr = [], {}
    for sol in sols:
        rn = q(c, {"cmd": "rename_soldier", "name": sol["name"], "newName": x.gift})
        tr = q(c, {"cmd": "transfer_to_coop_base", "name": x.gift, "toBase": x.hb.get("name")})
        tries.append([sol.get("name"), sol.get("id"), rn.get("ok"), tr.get("transferred")])
        if tr.get("transferred"):
            break
        q(c, {"cmd": "rename_soldier", "name": x.gift, "newName": sol["name"]})
    v150, s150 = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 150, W_UI)
    ok150 = real_click(h, dlg(h).get("backText") or "OK", W_UI) if v150 else False
    back, _s = wait(lambda: top(h) == "GeoscapeState", W_UI)
    ev["guest"] = {"gift": x.gift, "tries": tries, "150 s": s150 if v150 else None, "150 OK": ok150, "host back": bool(back)}
    if not (tr.get("transferred") and v150 and ok150 and back):
        raise Stop("the guest not staged: %s" % ev["guest"])

def picker(x, ev):
    """the host's quick save within W_SAVE, a named probe save -> the client blob's globe; the client's screen from INTERCEPT, the
    window scale from a select-destination CANCEL on the client's own craft"""
    h, c = x.host, x.client
    qpath, spath = (os.path.join(h.user_dir, "xcom1", f) for f in (QUICK, PROBE))
    t0 = time.time()
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    okq, sq = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, W_SAVE, 0.2)
    wait(lambda: top(h) == "GeoscapeState", 2.0)   # CIT-SLEEP1 (F24288): the quick save's screens closed, at most the old 2.0 s
    hq = stack(h)
    q(h, {"cmd": "save_game", "file": PROBE})
    okn, _sn = wait(lambda: os.path.exists(spath) and os.path.getsize(spath) > 0, W_SAVE, 0.2)
    G = (wait(lambda: probe_globe(spath), 2.0)[0] if okn else None) or {}   # CIT-SLEEP1 (F24288): was a fixed 1.0 s
    cr = next((k for k in (own_base(c) or {}).get("crafts", []) if not k.get("coop")), None)
    q(c, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    session.wait_widget_ready(c, "CANCEL")   # CIT-SLEEP1 (F24288): was a fixed 0.4 s
    cw = q(c, {"cmd": "click_widget", "match": "CANCEL"})
    wait(lambda: top(c) == "GeoscapeState", 2.0)   # CIT-SLEEP1 (F24288): was a fixed 0.5 s
    x.pk = {"G": G, "geom": geometry(c), "scale": cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}}
    ev["picker"] = {"quick s": sq if okq else None, "host": hq, "probe": bool(okn), "G": G, "scale": x.pk["scale"]}
    if not okq or hq[-1:] != ["GeoscapeState"] or not G or None in G.values() or not x.pk["scale"] or top(c) != "GeoscapeState":
        raise Stop("the picker missed: %s" % ev["picker"])

def visit(x, ev):
    c = x.client
    px = click_globe(c, x.hb["lon"], x.hb["lat"], x.pk)
    v, s = wait(lambda: coop(c).get("insideCoopBase") and top(c) == "BasescapeState", W_VISIT, 0.25)
    ev["visit"] = {"pixel": px, "inside s": s if v else None}
    if not v:
        raise Stop("the client not inside the host base within %.0f s: %s" % (W_VISIT, stack(c)))

def to_soldiers(x, ev):
    """the client's real SOLDIERS press inside the visited base: SoldiersState on top"""
    ok = real_click(x.client, "SOLDIERS", W_UI)
    v, s = wait(lambda: top(x.client) == "SoldiersState", W_UI)
    ev["soldiers"] = {"press": ok, "s": s if v else None}
    if not v:
        raise Stop("no SoldiersState: %s" % stack(x.client))

def baseline(x, ev):
    """B, just before the row's gift: crash census, both log line counts, stacks, get_coop, coop_file_info, the host folder"""
    h, c = x.host, x.client
    x.c0, x.n_h, x.n_c = crash(), len(log(h)), len(log(c))
    if not x.gift:
        pick_gift(x)
    x.B = {"t": time.time(), "stack": [stack(h), stack(c)], "get_coop": [coop(h), coop(c)], "blob": [blob(h), blob(c)], "folder": files(h),
           "crash": len(x.c0), "cpu": cpu()}
    ev["B"] = dict(x.B, t=None)
    return x.B

def trigger54(x, ev):
    """the host's save_game_ui quick; poll POLL_S for the 54 on top within SEEN54_S (name QUICK); the client's 67 within W_67"""
    h = x.host
    x.F0 = files(h)
    ev["sessionS"] = session.wait_coop_session(h)   # F24296: the 54 needs the host's live session
    tt = time.time()
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    while time.time() - tt < SEEN54_S:
        if top(h) == "CoopState" and dlg(h).get("code") == 54:
            cp = coop(h)
            v, s67 = wait(lambda: dlg(x.client).get("code") == 67, W_67)
            ev["54"] = {"s": round(time.time() - tt, 3), "name": cp.get("pendingHostSaveName"), "saveID": cp.get("saveID"),
                        "67 s": s67 if v else None, "client": stack(x.client)}
            if cp.get("pendingHostSaveName") != QUICK or not v:
                raise Stop("at the 54: %s" % ev["54"])
            return
        time.sleep(POLL_S)
    raise Stop("the host's 54 not on top within %.0f s: %s %s" % (SEEN54_S, stack(h), dlg(h)))

def ok67(x, ev):
    """the client's real OK on its 67 over SoldiersState: SoldiersState on top, insideCoopBase false"""
    c = x.client
    ok = real_click(c, dlg(c).get("backText") or "OK", W_UI)
    v, s = wait(lambda: top(c) == "SoldiersState" and coop(c).get("insideCoopBase") is False, W_UI)
    ev["67 OK"] = {"press": ok, "s": s if v else None, "client": stack(c), "inside": coop(c).get("insideCoopBase")}
    if not v:
        raise Stop("not SoldiersState with insideCoopBase false after the 67's OK: %s" % ev["67 OK"])

def written(x, timeout, interval=0.02):
    v, s = wait(lambda: (files(x.host).get(QUICK) or [0, 0])[1] > (x.F0.get(QUICK) or [0, 0])[1], timeout, interval)
    return bool(v), s

def host_cancel(x, ev, label="CANCEL"):
    """the host's real CANCEL on the 54: QUICK written within W_SAVE"""
    h = x.host
    ok = real_click(h, dlg(h).get("backText") or "CANCEL", W_UI)
    v, s = written(x, W_SAVE)
    ev[label] = {"press": ok, "written s": s if v else None, "host": stack(h)}
    if not v:
        raise Stop("the CANCEL wrote no %s within %.0f s" % (QUICK, W_SAVE))
    x.how = "CANCEL"

def push_watch(x, ev, label):
    """the host's stored partner world after a gift (TASK 0: polled up to T0_PUSH s for a change from B's)"""
    b0, t0 = (x.B["blob"][0] or {}).get("fnv1a64"), time.time()
    while True:
        b = blob(x.host) or {}
        if b.get("fnv1a64") != b0 or time.time() - t0 >= T0_PUSH:
            ev[label] = {"fnv": b.get("fnv1a64"), "key": b.get("key"), "changed": b.get("fnv1a64") != b0, "s": round(time.time() - t0, 3)}
            return
        time.sleep(0.05)

def partner_gift(x, ev):
    """the client's real presses: OK on a 67 if up, SOLDIERS unless SoldiersState is on top, the guest's row (at most 3), KP2 on
    SoldierInfoState, the host's button; the host's GiftNoticeState within W_NOTICE"""
    c, h = x.client, x.host
    g = ev["gift"] = {}
    if dlg(c).get("code") == 67:
        g["67 OK"] = real_click(c, dlg(c).get("backText") or "OK", W_UI)
        time.sleep(0.3)
    if top(c) != "SoldiersState":
        g["SOLDIERS"] = real_click(c, "SOLDIERS", W_UI)
    v, _s = wait(lambda: top(c) == "SoldiersState", W_UI)
    tl = textlist(c)
    if not v or not tl:
        raise Stop("no SoldiersState / TextList in the visited base: %s" % stack(c))
    sc, info = x.pk["scale"], None
    for row in range(3):
        q(c, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 30) * sc["x"] + 1), "y": int((tl["y"] + 3 + 8 * row) * sc["y"] + 1)})
        info, _s = wait(lambda: top(c) == "SoldierInfoState", W_UI)
        if info:
            g["row"] = row
            break
    if not info:
        raise Stop("no SoldierInfoState from the first 3 rows")
    g["insideAtKP2"] = coop(c).get("insideCoopBase")
    q(c, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
    m, _s = wait(lambda: top(c) == "GiftSoldierMenu", W_UI)
    btns = buttons(c) if m else []
    hostbtn = next((t for t in btns if "host" in t.lower()), None) or coop(h).get("hostName")
    g.update(menu=bool(m), hostbtn=hostbtn)
    if "Gift %s to another player?" % x.gift not in [(t or "").strip() for t in btns]:
        raise Stop("the gift menu does not name %s: %s %s" % (x.gift, btns, stack(c)))
    tg = time.time()
    g["press"] = real_click(c, hostbtn, W_UI)
    v, s = wait(lambda: top(h) == "GiftNoticeState", W_NOTICE, POLL_S)
    g["notice s"] = s if v else None
    if not v:
        raise Stop("no GiftNoticeState on the host within %.0f s of the gift click: %s" % (W_NOTICE, stack(h)))
    x.tgift = tg
    push_watch(x, ev, "store after gift")
    ok = real_click(h, "OK", W_UI)
    v, s = wait(lambda: top(h) != "GiftNoticeState", W_UI)
    g.update({"notice OK": ok, "host": stack(h), "client": stack(c), "inside": coop(c).get("insideCoopBase"), "lines": gift_lines(c, x.n_c)[-4:]})
    if not v:
        raise Stop("the host's notice not closed by its OK: %s" % stack(h))

def host_gift(x, ev, needle):
    """the HOST gifts its first own soldier not in a craft (renamed GIFTNAME) to the partner: BASES, SOLDIERS, its row, KP2, the partner's
    button (real presses); the client's deferral log line within W_NOTICE; the host back on GeoscapeState by real presses"""
    h, c = x.host, x.client
    g = ev["gift"] = {}
    ob = next((b for b in soldiers(h) if not b.get("coopBaseFlag") and not b.get("coopIcon")), None)
    sols = (ob or {}).get("soldiers") or []
    idx = next((i for i, z in enumerate(sols) if not z.get("craft")), None)
    if idx is None:
        raise Stop("no host soldier outside a craft")
    g["soldier"] = [sols[idx]["name"], sols[idx]["id"], idx, q(h, {"cmd": "rename_soldier", "name": sols[idx]["name"], "newName": x.gift}).get("ok")]
    real_click(h, "BASES", W_UI)
    v, _s = wait(lambda: top(h) == "BasescapeState", W_UI)
    real_click(h, "SOLDIERS", W_UI) if v else None
    v, _s = wait(lambda: top(h) == "SoldiersState", W_UI)
    tl = textlist(h)
    if not v or not tl:
        raise Stop("no SoldiersState / TextList on the host: %s" % stack(h))
    sc = x.pk["scale"]
    q(h, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 30) * sc["x"] + 1), "y": int((tl["y"] + 3 + 8 * idx) * sc["y"] + 1)})
    v, _s = wait(lambda: top(h) == "SoldierInfoState", W_UI)
    if not v:
        raise Stop("no SoldierInfoState from the host's row %d" % idx)
    q(h, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
    v, _s = wait(lambda: top(h) == "GiftSoldierMenu", W_UI)
    btns = buttons(h) if v else []
    pb = next((t for t in btns if "client" in t.lower()), None) or coop(h).get("clientName")
    if "Gift %s to another player?" % x.gift not in [(t or "").strip() for t in btns]:
        raise Stop("the host's gift menu does not name %s: %s" % (x.gift, btns))
    x.tgift = time.time()
    g["press"] = [pb, real_click(h, pb, W_UI)]
    v, s = wait(lambda: any(needle in ln for ln in gift_lines(c, x.n_c)) or None, W_NOTICE)
    g["deferral s"] = s if v else None
    push_watch(x, ev, "store after gift")
    for _i in range(6):
        tp = top(h)
        if tp == "GeoscapeState":
            break
        real_click(h, "GEOSCAPE" if tp == "BasescapeState" else "OK", W_UI)
        time.sleep(0.4)
    g.update(host=stack(h), client=stack(c), inside=coop(c).get("insideCoopBase"), lines=gift_lines(c, x.n_c)[-4:])
    if not v:
        raise Stop("no client line %r within %.0f s of the host's gift" % (needle, W_NOTICE))
    if top(h) != "GeoscapeState":
        raise Stop("the host not back on GeoscapeState after its gift: %s" % stack(h))

def leave_base(x, ev):
    """the client's real presses out of the base: the 67's OK, OK on SoldierInfoState / SoldiersState, GEOSCAPE -> GeoscapeState time"""
    c, seen, t0 = x.client, [], time.time()
    while time.time() - t0 < W_LEAVE:
        tp = top(c)
        seen.append(tp)
        if tp == "GeoscapeState":
            ev["leave"] = {"seen": seen, "s": round(time.time() - t0, 3)}
            return time.time()
        if tp == "CoopState":
            real_click(c, dlg(c).get("backText") or "OK", W_UI)
        elif tp == "BasescapeState":
            real_click(c, "GEOSCAPE", W_UI)
        elif tp in ("SoldiersState", "SoldierInfoState", "GiftNoticeState"):
            real_click(c, "OK", W_UI)
        time.sleep(0.4)
    raise Stop("the client not back on GeoscapeState within %.0f s: %s" % (W_LEAVE, seen[-6:]))

def kill_rejoin(x, ev):
    """CAP kill_rejoin: client.kill(); the host's 60 / 62 within W_DROP; a fresh client (<tag>_client2) join_tcp by B's clientName; the
    host's resumeAck within JOIN_S; the host's real OK on a Profile state and real RESUME; both GeoscapeState within W_RESUME; HOLD_R"""
    h, cname = x.host, x.B["get_coop"][0].get("clientName")
    r = ev["rejoin"] = {"store at kill": (blob(h) or {}).get("fnv1a64")}
    x.client.kill()
    x.dead.append(x.client)
    v, s = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") in (60, 62), W_DROP, 0.1)
    r["drop s"] = s if v else None
    if not v:
        raise Stop("no host drop window (60 / 62) within %.0f s: %s %s" % (W_DROP, stack(h), dlg(h)))
    x.client = GameClient("client", None, make_user_dir(x.tag + "_client2"))
    x.client.spawn()
    x.client.connect()
    r["join"] = q(x.client, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": x.key, "player": cname}).get("ok")
    v, s = wait(lambda: coop(h).get("resumeAck") or None, JOIN_S, 0.25)
    r["ack s"] = s if v else None
    if not v:
        raise Stop("no resumeAck within %.0f s of join_tcp" % JOIN_S)
    t0, seen = time.time(), []
    while time.time() - t0 < W_RESUME:
        tp = top(h)
        seen.append(tp)
        if tp and "Profile" in tp:
            real_click(h, "OK", W_UI)
        elif tp == "CoopState" and dlg(h).get("code") in (60, 62) and dlg(h).get("backVisible"):
            real_click(h, dlg(h).get("backText") or "RESUME", W_UI)
        elif tp == "GeoscapeState" and top(x.client) == "GeoscapeState":
            break
        time.sleep(0.3)
    r.update(seen=[t for i, t in enumerate(seen) if i == 0 or seen[i - 1] != t], host=stack(h), client=stack(x.client))
    if top(h) != "GeoscapeState" or top(x.client) != "GeoscapeState":
        raise Stop("not both on GeoscapeState within %.0f s of the ack: %s" % (W_RESUME, r))
    time.sleep(HOLD_R)
    r["blob"] = [blob(h), blob(x.client)]

def read_point(x, ev):
    """the read: both machines alive, the crash folder since B, both stacks"""
    ev["read"] = {"alive": [alive(x.host), alive(x.client)], "crash": crash_new(x.c0), "host": stack(x.host), "client": stack(x.client),
                  "clientDlg": dlg(x.client), "blob": [blob(x.host), blob(x.client)], "lines": gift_lines(x.client, x.n_c)[-6:] if alive(x.client) else None}
    return ev["read"]

def keep_file(x, ev):
    """the written QUICK: its halves and bytes / mtime"""
    p = os.path.join(x.host.user_dir, "xcom1", QUICK)
    ev["write"] = {"how": x.how, "bytes": os.path.getsize(p), "mtime": os.path.getmtime(p)}
    ev["halves"] = halves(p, x.gift)
    x.src = p

def reload(x, ev, key=None):
    """a fresh pair <tag>r_host / _client, QUICK copied into the host's xcom1 before it spawns, resume_campaign, settle -> census"""
    y = boot(x.tag + "r", key or x.key, saves=(x.src,))
    try:
        if y.err:
            ev["reload"] = {"boot": y.err, "cap": y.cap}
            return None
        y.gift = x.gift
        c = census(y)
        ev["reload"] = dict(c, settle=y.settle, crash=crash_new(y.c0)["dmp"])
        return c
    finally:
        x.shutfail = shut(y)

def common(rid, rd):
    cr = rd.get("crash") or {}
    return (rid + "-common", "GUARD", "both machines alive at the read, no new .dmp since B" + ("" if rid == "R5" else ", hashlogs == 0"),
            rd.get("alive") == [True, True] and cr.get("dmp") == [] and (rid == "R5" or cr.get("hashlogs") == 0))

def reloaded(ev):
    rl = ev.get("reload")
    return rl if isinstance(rl, dict) and "host" in rl else None

class Row:
    """one row: one PASS / FAIL line per cell; a precondition miss marks the later cells "not reached\""""
    def __init__(self, rid, ids):
        self.rid, self.ids, self.fails, self.done, self.t0 = rid, ids, [], set(), time.time()
    def cell(self, cid, kind, label, ok):
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]
    def stop(self, why):
        for cid in [c for c in self.ids if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:200]), flush=True)
            self.fails.append(cid)

def run_row(rid, tag, key, build, ids, cellfn, pre):
    """boot (a miss fails the row "boot"), the construction to the read, shutdown, the reload (R1 R2 R3 R5), ONE EVIDENCE line, the
    cells, ONE CAPTURE line when a cell failed, the row verdict -> (passed, wall, shutdown failures)"""
    r, ev, cap = Row(rid, ["%s-%s" % (rid, c) for c in ids]), {}, None
    x = boot(tag, key)
    ev["cpu"], failed = x.cpu, []
    try:
        if x.err:
            print("FAIL %s boot: both tops GeoscapeState unchanged %.0f s not within %.0f s (%s)" % (rid, STABLE_S, BOOT_S, x.err), flush=True)
            r.fails.append("boot")
            r.stop("boot")
            cap = x.cap
        else:
            try:
                build(x, ev)
            except Exception as e:  # Stop, or a probe that raised: the row ends here
                ev["stop"] = short(e, 600)
                cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc), "blob": blob(gc), "lines": gift_lines(gc, 0)[-6:]}
                       for n, gc in (("host", x.host), ("client", x.client)) if alive(gc)}
    finally:
        failed += shut(x)
    if not x.err:
        if "stop" not in ev and rid in ("R1", "R2", "R3", "R5"):
            reload(x, ev)
            failed += x.shutfail
        print("EVIDENCE %s: %s" % (rid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
        r.cell(rid + "-pre", "GUARD", pre, "stop" not in ev)
        if "stop" in ev:
            r.stop(ev["stop"])
        for cid, kind, label, ok in ([] if "stop" in ev else cellfn(rid, ev)):
            r.cell(cid, kind, label, ok)
    if r.fails:
        cap = cap or {k: ev.get(k) for k in ("read", "halves", "live", "reload", "rejoin")}
        print("CAPTURE %s: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    print(("PASS %s" % rid) if not r.fails else ("FAIL %s: %s" % (rid, " ".join(r.fails))), flush=True)
    return not r.fails, round(time.time() - r.t0, 1), failed

def main(name, rows):
    """every row runs; exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100)"""
    t0, res, walls, failed = time.time(), {}, {}, []
    for rid, row in rows:
        res[rid], walls[rid], f = row()
        failed += f
    failed += [rid for rid, _r in rows if not res[rid]]
    print("\n%s: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (name, sum(1 for v in res.values() if v), len(rows), failed,
                                                                   json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0
