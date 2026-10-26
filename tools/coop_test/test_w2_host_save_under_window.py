"""W2-H64 stage S-A (spec rewrite/prompts/w2h64_sa_write_under.md (f), common file rewrite/prompts/w2h64_save_under_window.md; TASK 0
rewrite/w2h64-task0/sa/CONSTANTS.md; lead L-H59-1, ruling R-H64-0; F19186, F19188): in a co-op campaign every host geoscape save waits
behind "Saving..." (CoopState 54) for the second player's world. While that player is inside the host's base the wait lasts the whole
visit, and a soldier gift (keypad 2 on its soldier screen) puts the host's GiftNoticeState over the 54. When the player then drops,
W2-H59's drop helper coopWriteArmedSaveOnPeerDrop writes only a TOP 54, so it returns, and the save is lost (F19186).
Two rows, one fresh boot pair each (key "49225", dirs w2h64_<row>_host / _client; session.new_campaign SEPARATE gm1 tcp, the host base at
HOST_POS; both tops GeoscapeState unchanged STABLE_S within BOOT_S). Construction (real presses only): stage the guest (the client's first
own-base soldier not in a craft renamed GIFTNAME, transfer_to_coop_base to the host's base, the host's "Items received" (150) closed by a
real OK), the picker (the host's quick save, a named probe save, the client's select-destination CANCEL scale), the visit (the client's
globe click on the host base), baseline B, the trigger (save_game_ui quick: the 54 on top, the client's 67), HOLD_PRE, the gift (the
client's OK on its 67, SOLDIERS, the guest's row, KP2, the host's button: the host's GiftNoticeState on top over the 54), the drop:
  R-GD client.kill() at the notice's first sight (the E2 drop arm); R-GT the host's TEST-ONLY force_server_error (the a3 arm), the 62
  within W_62, then the client is killed after the read.
The read is HOLD_S after the drop event. Cells (X = GD GT): X-pre GUARD (construction met; the 54 on top within SEEN54_S, name QUICK,
CLEAR +0; the client's 67; the notice on top within W_NOTICE over B's stack + [CoopState], name QUICK, CLEAR +0; GD: the client exited;
GT: SERVER +1, the 62 within W_62); X-file RED (QUICK written: mtime newer than B's); X-blob RED (one embedded partner world, key
host_<saveID at the 54>_<B clientName>.data, its FNV-1a 64 = B's coop_file_info fnv1a64); GD-path RED ((H59LOG, CLEAR, FREEZE, DROP) =
(1, 1, 1, 1)); GT-path RED ((1, 1, 1, 0) and SERVER 1); GD-name GUARD / GT-name RED (pendingHostSaveName ""); X-stack GUARD (B's stack +
[CoopState, GiftNoticeState, CoopState], code 62: the 54 stays under the notice); X-common GUARD (host alive; each new crash_*.log
is the lever's miss, one per W2-H70 push). 14 cells.
Red (commit R1): exit 2, RED exactly on GD-file, GD-blob, GD-path, GT-file, GT-blob, GT-path, GT-name (7).
A precondition miss ends its row (cells "not reached"); a boot miss fails the row "boot" with ONE CAPTURE line. ONE EVIDENCE line per
row, one PASS / FAIL line per cell, the row verdict; exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100). WV-D95: one
foreground run per invocation.
W2-H70 T1 (docs rewrite/prompts/w2h70_t1_hsw_hsc_repoint.md; F20123): W2-H70's gift pushes the client's stored world, which would
complete the save before the drop. The client's TEST-ONLY force_stream_key_miss, armed just before the host's button, fails every
client save stream, so no client world lands and the drop write runs on every build. The drop waits until the lever's logged misses
equal the client's W2-H70 pushes (0 without W2-H70, 1 with it); X-common counts exactly those.
Run: python tools/coop_test/test_w2_host_save_under_window.py
"""
import base64, glob, json, math, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, cpu_load, cpu_text  # noqa: E402

KEY = "49225"
QUICK, PROBE = "_quick_.asav", "h64_probe.sav"
HOST_POS = (0.90, -0.60)
GIFTNAME = "Zzz Gift"
SDLK_KP2 = 258
POLL_S, SEEN54_S, W_67, HOLD_PRE, W_UI, W_NOTICE, W_VISIT = 0.005, 10.0, 10.0, 1.0, 5.0, 10.0, 60.0
HOLD_S, W_62, W_SAVE, STABLE_S, BOOT_S = 5.0, 5.0, 30.0, 2.0, 60.0
W_LEVER = 5.0  # W2-H70 T1: the lever's miss follows the host's reply to the client's push (T0-6: the whole stream took 0.23 s)
MISS = "Failed to read from hash map with key: client_%s_%s.data"  # loopData's miss of the client's own-world key (saveID, name)
GIFT70 = "[coop-gift] W2-H70: the stored own world follows a gift"  # W2-H70 E1: the client pushed its stored world at the gift
RC_OK = (0, 3221226505)
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
NEEDLES = {"H59LOG": "[coop] W2-H59: the partner dropped during the host's deferred save", "CLEAR": "[coop-session] clearDeferredSave",
           "FREEZE": "[coop-session] freeze (lobbyMode=", "DROP": "[coop-session] onClientDrop",
           "SERVER": "[coop-test] force_server_error: onConnect -3 (main thread)"}
PATH4 = ("H59LOG", "CLEAR", "FREEZE", "DROP")

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
    return pick(q(gc, {"cmd": "get_coop"}), ("pendingHostSaveName", "saveID", "clientName", "onConnect", "insideCoopBase", "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "error"))

def blobinfo(gc):
    return pick(q(gc, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key", "present", "bytes", "fnv1a64", "error"))

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}

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

def misses(r, paths):
    """W2-H70 T1: the names of the crash files among paths that hold the lever's miss r.miss (none before settle sets it)"""
    out = []
    for p in sorted(paths):
        with open(p, encoding="utf-8", errors="replace") as fh:
            if getattr(r, "miss", None) and r.miss in fh.read():
                out.append(os.path.basename(p))
    return out

def settle(r, x):
    """W2-H70 T1: once the client's GiftSoldierMenu is gone (its handler, with any W2-H70 push, has run), n70 = the client's W2-H70
    push lines; poll up to W_LEVER until the lever's misses since B number n70 (that push's stream failed on the lever) -> ev["lever"]"""
    c = x.client
    gone, _s = wait(lambda: "GiftSoldierMenu" not in stack(c), W_UI)
    r.miss = MISS % (r.ev["at54"]["saveID"], r.ev["B"]["get_coop"].get("clientName"))
    r.n70 = sum(1 for ln in log(c) if GIFT70 in ln)
    v, s = wait(lambda: len(misses(r, session._crash_log_snapshot() - r.cr0)) == r.n70, W_LEVER, 0.02)
    r.ev["lever"] = {"menu gone": bool(gone), "n70": r.n70, "misses": misses(r, session._crash_log_snapshot() - r.cr0), "s": s}
    if not (gone and v and r.n70 <= 1):
        raise Stop("the lever did not settle: %s" % r.ev["lever"])

def cpu():
    return cpu_text(cpu_load()["cpu"])

def fnv(b):
    """FNV-1a 64 (offset 1469598103934665603, prime 1099511628211, mod 2^64; TestServer coop_file_info), 16 hex digits"""
    h = 1469598103934665603
    for ch in b:
        h = ((h ^ ch) * 1099511628211) % (1 << 64)
    return "%016x" % h

def read_save(path):
    """the save's embedded partner worlds (key, bytes, fnv1a64): PyYAML load_all (CSafeLoader when present), each blob base64 (a str)
    or binary (bytes); the host world's globe for the picker"""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    except Exception as e:  # a value
        return {"error": short(e, 300)}
    out = []
    for d in docs:
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
            ent = {"key": e.get("key"), "bytes": len(b), "fnv1a64": fnv(b)}
            try:
                w = next((x for x in yaml.load_all(b.decode("utf-8", errors="replace"), Loader=loader) if isinstance(x, dict) and "bases" in x),
                         None)
                ent["globe"] = {k: (w or {}).get(k) for k in ("globeLon", "globeLat", "globeZoom")}
            except Exception as ex:  # a value
                ent["parse"] = short(ex, 200)
            out.append(ent)
    return {"entries": out}

def wait(pred, timeout, interval=0.05):
    """poll pred every interval up to timeout -> (value or None, seconds)"""
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
    """a real press: click_widget once list_widgets shows the button visible -> ok"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _button(gc, text) is not None:
            return bool(q(gc, {"cmd": "click_widget", "match": text}).get("ok"))
        time.sleep(0.02)
    return False

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

def click_globe(gc, lon, lat, pk):
    """the client's real globe click: inject_input at the projected pixel (x scale, + 1), the next offset while GeoscapeState stays top"""
    x, y = project(pk["G"], lon, lat, pk["geom"])
    for dx, dy in CLICKS:
        q(gc, {"cmd": "inject_input", "kind": "click", "x": int((x + dx) * pk["scale"]["x"] + 1), "y": int((y + dy) * pk["scale"]["y"] + 1)})
        time.sleep(0.9)
        if top(gc) != "GeoscapeState":
            return [x + dx, y + dy]
    return None

def stage_guest(x, ev):
    """the client's first own-base soldier not in a craft (none: the first) renamed GIFTNAME, transfer_to_coop_base to the host's
    base; the host's 150 closed by a real OK; the host back on GeoscapeState"""
    c, h = x.client, x.host
    names = [z.get("name") for gc in (h, c) for b in q(gc, {"cmd": "get_soldiers"}).get("bases", []) for z in b.get("soldiers", [])]
    if GIFTNAME in names:
        raise Stop("%s already in a roster" % GIFTNAME)
    own = next((b for b in q(c, {"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag") and not b.get("coopIcon")
                and b.get("soldiers")), None)
    sol = next((z for z in (own or {}).get("soldiers", []) if not z.get("craft")), None) or ((own or {}).get("soldiers") or [None])[0]
    rn = q(c, {"cmd": "rename_soldier", "name": sol and sol["name"], "newName": GIFTNAME})
    tr = q(c, {"cmd": "transfer_to_coop_base", "name": GIFTNAME, "toBase": x.hb.get("name")})
    v150, s150 = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 150, W_UI)
    ok150 = real_click(h, dlg(h).get("backText") or "OK", W_UI) if v150 else False
    back, sb = wait(lambda: top(h) == "GeoscapeState", W_UI)
    ev["guest"] = {"soldier": sol and [sol.get("name"), sol.get("id")], "rename": rn.get("ok"), "transferred": tr.get("transferred"),
                   "150 s": s150 if v150 else None, "150 OK": ok150, "host back": bool(back)}
    if not (rn.get("ok") and tr.get("transferred") and v150 and ok150 and back):
        raise Stop("the guest not staged: %s" % ev["guest"])

def picker(x, ev):
    """the host's quick save within W_SAVE, a named probe save -> the client blob's globe; the client's screen from INTERCEPT, the
    window scale from a select-destination CANCEL on the client's own craft"""
    h, c = x.host, x.client
    qpath, spath = (os.path.join(h.user_dir, "xcom1", f) for f in (QUICK, PROBE))
    t0 = time.time()
    q(h, {"cmd": "save_game_ui", "type": "quick"})
    okq, sq = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, W_SAVE, 0.2)
    time.sleep(2.0)
    hq = stack(h)
    q(h, {"cmd": "save_game", "file": PROBE})
    okn, _sn = wait(lambda: os.path.exists(spath) and os.path.getsize(spath) > 0, W_SAVE, 0.2)
    time.sleep(1.0)
    G = (((read_save(spath) if okn else {}).get("entries") or [{}])[0]).get("globe") or {}
    cr = next((k for k in (own_base(c) or {}).get("crafts", []) if not k.get("coop")), None)
    q(c, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    time.sleep(0.4)
    cw = q(c, {"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.5)
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

def baseline(r, x):
    """B, just before the trigger: crash snapshot, the host log's line count, stack, get_coop, coop_file_info, the folder"""
    h = x.host
    r.cr0, r.n_h = session._crash_log_snapshot(), len(log(h))
    r.ev["B"] = {"stack": stack(h), "get_coop": coop(h), "coop_file_info": blobinfo(h), "folder": files(h)}
    return r.ev["B"]

def at54(r, x):
    """trigger (save_game_ui quick), poll POLL_S up to SEEN54_S: the host's top CoopState with code 54 -> name, saveID, CLEAR; the
    client's 67 within W_67"""
    h, ev = x.host, r.ev
    tt = time.time()
    ev["trigger"] = pick(q(h, {"cmd": "save_game_ui", "type": "quick"}), ("ok", "error"))
    while time.time() - tt < SEEN54_S:
        s = stack(h)
        if s and s[-1] == "CoopState" and dlg(h).get("code") == 54:
            cp = coop(h)
            ev["at54"] = {"s": round(time.time() - tt, 3), "name": cp.get("pendingHostSaveName"), "saveID": cp.get("saveID"),
                          "CLEAR": counts(h, r.n_h)["CLEAR"]}
            v, s67 = wait(lambda: dlg(x.client).get("code") == 67, W_67)
            ev["at54"]["67 s"] = s67 if v else None
            return ev["at54"]
        time.sleep(POLL_S)
    raise Stop("the host's 54 not on top within %.0f s: %s %s" % (SEEN54_S, stack(h), dlg(h)))

def gift(r, x):
    """inside the host base (real presses): OK on the 67, SOLDIERS, the guest's row, KP2 on SoldierInfoState, the host's button; poll
    POLL_S up to W_NOTICE for the host's GiftNoticeState on top -> its time, the host stack, get_coop, CLEAR, coop_file_info"""
    c, h, ev = x.client, x.host, r.ev
    d = dlg(c)
    seq = {"67 OK": real_click(c, d.get("backText") or "OK", W_UI), "SOLDIERS": real_click(c, "SOLDIERS", W_UI)}
    seq["SoldiersState"], _s = wait(lambda: top(c) == "SoldiersState", W_UI)
    tl = next((w for w in q(c, {"cmd": "list_widgets"}).get("widgets", []) if "TextList" in str(w.get("type"))), None)
    if seq["SoldiersState"] and tl:
        sc = x.pk["scale"]
        q(c, {"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + 30) * sc["x"] + 1), "y": int((tl["y"] + 3) * sc["y"] + 1)})
        seq["SoldierInfoState"], _s = wait(lambda: top(c) == "SoldierInfoState", W_UI)
    if seq.get("SoldierInfoState"):
        q(c, {"cmd": "inject_input", "kind": "key", "key": SDLK_KP2})
        seq["GiftSoldierMenu"], _s = wait(lambda: top(c) == "GiftSoldierMenu", W_UI)
    btns = [w.get("text") for w in q(c, {"cmd": "list_widgets"}).get("widgets", []) if w.get("text")] if seq.get("GiftSoldierMenu") else []
    seq["menu names the guest"] = "Gift %s to another player?" % GIFTNAME in btns
    hostbtn = next((t for t in btns if "host" in t.lower()), None)
    ev["gift"] = seq
    if not (seq["menu names the guest"] and hostbtn):
        raise Stop("the gift menu not reached: %s %s %s" % (seq, btns, stack(c)))
    lv = q(c, {"cmd": "force_stream_key_miss", "on": True})  # W2-H70 T1: no client world lands before the drop / release
    seq["lever on"] = bool(lv.get("ok") and lv.get("on") is True)
    if not seq["lever on"]:
        raise Stop("force_stream_key_miss not armed on the client: %s" % lv)
    tg = time.time()
    seq["host button"] = real_click(c, hostbtn, W_UI)
    while time.time() - tg < W_NOTICE:
        if top(h) == "GiftNoticeState":
            tn = time.time()
            cp = coop(h)
            ev["notice"] = {"s": round(tn - tg, 3), "stack": stack(h), "name": cp.get("pendingHostSaveName"), "CLEAR": counts(h, r.n_h)["CLEAR"],
                            "coop_file_info": blobinfo(h)}
            return tn
        time.sleep(POLL_S)
    raise Stop("no GiftNoticeState on the host within %.0f s of the gift click: %s" % (W_NOTICE, stack(h)))

def drop_kill(r, x, tn):
    t = time.time()
    x.client.kill()
    r.ev["drop"] = {"event": "client.kill()", "s after notice": round(t - tn, 3), "rc": x.client.proc.poll()}
    return t, not alive(x.client), "the client process exited"

def drop_server(r, x, tn):
    h, d = x.host, r.ev.setdefault("drop", {})
    t = time.time()
    d["reply"] = pick(q(h, {"cmd": "force_server_error"}), ("ok", "error"))
    d["s after notice"] = round(t - tn, 3)
    v, s = wait(lambda: top(h) == "CoopState" and dlg(h).get("code") == 62, W_62, 0.02)
    d["62 s"] = s if v else None
    return time.time(), bool(d["reply"].get("ok") is True and counts(h, r.n_h)["SERVER"] == 1 and v), "SERVER +1, the 62 within %.0f s" % W_62

def read(r, x, B):
    h = x.host
    rd = {"stack": stack(h), "dialog": dlg(h), "get_coop": coop(h), "folder": files(h), "needles": counts(h, r.n_h), "alive": alive(h),
          "new crash": sorted(session._crash_log_snapshot() - r.cr0)}
    a, b = rd["folder"].get(QUICK), B["folder"].get(QUICK)
    rd["written"] = bool(a and (b is None or a[1] > b[1]))
    rd["blob"] = read_save(os.path.join(h.user_dir, "xcom1", QUICK)) if rd["written"] else None
    rd["misses"] = misses(r, rd["new crash"])
    return rd

class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.n_h = rid, cells, x, [], set(), time.time(), 0
        self.cr0, self.ev = session._crash_log_snapshot(), {}

    def evidence(self):
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)

    def cell(self, cid, kind, label, ok):
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)

    def end(self, results, walls, cap=None):
        """ONE CAPTURE line when a cell failed, then the row verdict"""
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            if cap is None:
                cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc)} for n, gc in (("host", x.host), ("client", x.client))
                       if alive(gc)}
                if alive(x.host):
                    cap["host needle deltas"] = counts(x.host, self.n_h)
                    cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(x.host) if "[coop" in ln][-12:]
                cap["new crash"] = sorted(session._crash_log_snapshot() - self.cr0)
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("FAIL %s boot: the boot did not reach both tops GeoscapeState unchanged %.0f s (%s)" % (self.rid, STABLE_S, self.x.err), flush=True)
        self.fails.append("boot")
        self.stop("boot")
        self.end(results, walls, cap=self.x.cap)

def drop_row(x, results, walls, rid, p, drop):
    """construction (2)-(4), B, the trigger, HOLD_PRE, the gift, the row's drop, the read HOLD_S after the drop event, the cells"""
    r = Row(rid, ["%s-%s" % (p, c) for c in ("pre", "file", "blob", "path", "name", "stack", "common")], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, ev = x.host, r.ev
    ev["cpu"] = x.cpu
    pre = ("construction met; the 54 on top within %.0f s, name %s, CLEAR +0; the client's 67; the notice on top within %.0f s over B's "
           "stack + [CoopState], name %s, CLEAR +0; the lever settled; " % (SEEN54_S, QUICK, W_NOTICE, QUICK))
    try:
        try:
            stage_guest(x, ev)
            picker(x, ev)
            visit(x, ev)
            B = baseline(r, x)
            a = at54(r, x)
            if a["name"] != QUICK or a["CLEAR"] != 0 or a["67 s"] is None:
                raise Stop("at the 54: %s" % a)
            time.sleep(HOLD_PRE)
            tn = gift(r, x)
            n = ev["notice"]
            if n["stack"] != B["stack"] + ["CoopState", "GiftNoticeState"] or n["name"] != QUICK or n["CLEAR"] != 0:
                raise Stop("at the notice: %s" % n)
            settle(r, x)
            td, ok, what = drop(r, x, tn)
            pre += what
            if not ok:
                raise Stop("the drop: %s" % ev["drop"])
        except Stop as e:
            r.evidence()
            r.cell(p + "-pre", "GUARD", pre, False)
            raise
        while time.time() - td < HOLD_S:
            time.sleep(0.05)
        rd = ev["read"] = read(r, x, B)
        if alive(x.client):
            x.client.kill()
            ev["drop"]["client killed after the read"] = True
        r.evidence()
        r.cell(p + "-pre", "GUARD", pre, True)
        nd = rd["needles"]
        r.cell(p + "-file", "RED", "%s written (mtime newer than B's) %.0f s after the drop (red today: not written, F19186)" % (QUICK, HOLD_S),
               rd["written"])
        key, fv = "host_%s_%s.data" % (a["saveID"], B["get_coop"].get("clientName")), B["coop_file_info"].get("fnv1a64")
        e = (rd.get("blob") or {}).get("entries")
        r.cell(p + "-blob", "RED", "the file embeds 1 partner world, key %s, FNV-1a 64 = B's coop_file_info %s (red today: no file; F19188)"
               % (key, fv), bool(rd["written"] and e is not None and len(e) == 1 and e[0]["key"] == key and e[0]["fnv1a64"] == fv))
        if p == "GT":
            r.cell("GT-path", "RED", "(H59LOG, CLEAR, FREEZE, DROP) = (1, 1, 1, 0) and SERVER 1 since B (red today: (0, 0, 1, 0))",
                   tuple(nd[k] for k in PATH4) == (1, 1, 1, 0) and nd["SERVER"] == 1)
            r.cell("GT-name", "RED", "pendingHostSaveName \"\" at the read (red today: still armed, a3 has no onClientDrop)",
                   rd["get_coop"].get("pendingHostSaveName") == "")
        else:
            r.cell("GD-path", "RED", "(H59LOG, CLEAR, FREEZE, DROP) = (1, 1, 1, 1) since B (red today: (0, 0, 1, 1))",
                   tuple(nd[k] for k in PATH4) == (1, 1, 1, 1))
            r.cell("GD-name", "GUARD", "pendingHostSaveName \"\" at the read (onClientDrop clears it)", rd["get_coop"].get("pendingHostSaveName") == "")
        r.cell(p + "-stack", "GUARD", "the host stack = B's + [CoopState, GiftNoticeState, CoopState] with code 62 (the 54 stays under the notice)",
               rd["stack"] == B["stack"] + ["CoopState", "GiftNoticeState", "CoopState"] and rd["dialog"].get("code") == 62)
        r.cell(p + "-common", "GUARD", "the host alive at the read; every crash_*.log new since B is the lever's miss %s, %d of them (W2-H70 T1)"
               % (r.miss, r.n70), bool(rd["alive"] and len(rd["misses"]) == len(rd["new crash"]) == r.n70))
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_gd(x, results, walls):
    drop_row(x, results, walls, "R-GD", "GD", drop_kill)

def row_gt(x, results, walls):
    drop_row(x, results, walls, "R-GT", "GT", drop_server)

def boot(rid, tag):
    """CPU, host + client spawn, connect, the host base at HOST_POS, session.new_campaign(port=KEY), geo.slow_clock, both tops
    GeoscapeState unchanged STABLE_S within BOOT_S (else x.err and x.cap: both stacks, coop_dialog_info, get_coop)"""
    x = SimpleNamespace(rid=rid, tag=tag, host=None, client=None, err=None, cap=None, cpu=cpu(), hb=None, pk=None)
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
            if s[0] and s[1] and s[0][-1] == s[1][-1] == "GeoscapeState" and time.time() - tch >= STABLE_S:
                break
            if time.time() - t0 > BOOT_S:
                raise Stop("both tops GeoscapeState unchanged %.0f s: not within %.0f s" % (STABLE_S, BOOT_S))
            time.sleep(0.1)
        x.hb = own_base(x.host)
    except Exception as e:
        x.err = short(e, 600)
        x.cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc)} for n, gc in (("host", x.host), ("client", x.client))
                 if alive(gc)}
    return x

def shut(x):
    """every machine of the boot still running (a killed client was reaped by kill()) -> the shutdown failures"""
    failed = []
    for gc in (x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

ROWS = (("R-GD", "w2h64_gd", row_gd), ("R-GT", "w2h64_gt", row_gt))

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for rid, tag, row in ROWS:
        tb = time.time()
        x = boot(rid, tag)
        walls[tag + " boot"] = round(time.time() - tb, 1)
        try:
            row(x, results, walls)
        finally:
            failed += shut(x)
        walls[tag] = round(time.time() - tb, 1)
    failed += [rid for rid, _t, _r in ROWS if not results.get(rid)]
    print("\ntest_w2_host_save_under_window: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _t, _r in ROWS if results.get(rid)), len(ROWS), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
