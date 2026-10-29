"""test_host_save_wait_closes.py: every co-op host geoscape save waits behind "Saving..." (CoopState 54) for the
second player's world; inside the host's base the wait lasts the whole visit, and a soldier gift (keypad 2) puts the
host's GiftNoticeState over the 54. A save written while the notice covers the 54 (the world landing when the player
leaves the base, or the drop write of test_host_save_under_window) disarms it but cannot pop the 54 under the notice.
The 54 closes itself as soon as it is the top state again with nothing armed ("[coop] the host's save wait (54)
closes"). When broken, after the notice's OK the host sees "Saving..." until CANCEL, which writes nothing.
Three rows, one fresh boot pair each (key "49227", dirs wait_closes_<row>_host / _client, drop_and_rejoin's rejoiner
wait_closes_drop_and_rejoin_client2; session.new_campaign SEPARATE gm1 tcp, the host base at HOST_POS; both tops
GeoscapeState unchanged STABLE_S within BOOT_S). Construction (real presses only): leave_under_notice /
drop_and_rejoin stage the guest (the client's first own-base soldier not in a craft renamed GIFTNAME,
transfer_to_coop_base to the host's base, the host's 150 closed by a real OK); the picker (quick save, named probe
save, select-destination CANCEL scale); the visit (the client's globe click on the host base); the baseline read; the
trigger (save_game_ui quick: the 54 on top, the client's 67); leave_under_notice / drop_and_rejoin: HOLD_PRE and the
gift (the client's OK on its 67, SOLDIERS, the guest's row, KP2, the host's button: the host's notice on top over the
54).
  leave_under_notice: the client leaves the base (OK, GEOSCAPE); QUICK written within W_SAVE; WAIT_W; the leave read;
    the host's real OK on the notice.
  drop_and_rejoin: client.kill() at the notice's first sight; the drop read HOLD_S later; a NEW client (fresh dir)
    joins KEY by name until the host's resumeAck with its 62 on top within JOIN_S; the host's real RESUME; the notice
    on top within W_RESUME (the resume read); the notice's real OK.
  armed_wait (the armed-wait guard): no gift; HOLD_W with the client on its 67 (the hold read); the client's OK on its
    67 and GEOSCAPE; QUICK written and the 54 gone within W_SAVE (the blob handler's pop); the end read 1 s later.
leave_under_notice / drop_and_rejoin: poll POLL_S up to W_CLOSE after the notice's OK for back() (the host stack ==
the baseline's, top GeoscapeState), then the end read. Needles (host log since the baseline): DEFERRED_DROP, CLEAR,
FREEZE, DROP and CLOSE54 (the 54's own close line). Cells (16), named <row>-<check>: -pre GUARD (the preconditions,
with the leave / drop reads); drop_and_rejoin-rejoin GUARD (the resume read); leave_under_notice-close /
drop_and_rejoin-close FIX (back() within W_CLOSE); leave_under_notice-log / drop_and_rejoin-log FIX (CLOSE54 1 at the
end read); leave_under_notice-once / drop_and_rejoin-once GUARD (QUICK's mtime at the end read == at the leave / drop
read; CLEAR 1); armed_wait-hold GUARD (the hold read: the 54 on top, armed, CLEAR 0); armed_wait-write GUARD;
armed_wait-log GUARD (CLOSE54 0 at the hold and end reads); -common GUARD (host alive; each new crash_*.log since the
baseline is the key miss below, one per gift push).
When broken (with the drop write of test_host_save_under_window in place): exit 2, failing exactly
leave_under_notice-close, leave_under_notice-log, drop_and_rejoin-close and drop_and_rejoin-log (4).
A precondition miss ends its row (cells "not reached"); a boot miss fails the row's -pre cell with ONE CAPTURE line.
ONE EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; exit 0 only when every cell passes, else 2.
one foreground run per invocation.
A gift made during a base visit pushes the client's stored world; it lands about 0.2 s after the notice and races the
notice's CLEAR guard and drop_and_rejoin's drop write. leave_under_notice / drop_and_rejoin arm the client's
force_stream_key_miss test command just before the host's button (no client world lands) and wait until the logged key
misses equal the client's gift pushes (at most one); leave_under_notice then releases it and waits until CLEAR equals
that count before the leave.
Run: python tools/coop_test/test_host_save_wait_closes.py
"""
import base64, glob, json, math, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import geo  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, cpu_load, cpu_text  # noqa: E402

KEY = "49227"
QUICK, PROBE = "_quick_.asav", "picker_probe.sav"
HOST_POS = (0.90, -0.60)
GIFTNAME = "Zzz Gift"
REJOIN_NAME = "ClientPlayer"
SDLK_KP2 = 258
POLL_S, SEEN54_S, W_67, HOLD_PRE, W_UI, W_NOTICE, W_VISIT = 0.005, 10.0, 10.0, 1.0, 5.0, 10.0, 60.0
HOLD_S, W_SAVE, STABLE_S, BOOT_S = 5.0, 30.0, 2.0, 60.0
W_BACK, WAIT_W, W_CLOSE, JOIN_S, W_RESUME, HOLD_W = 60.0, 1.0, 2.0, 40.0, 15.0, 4.0
W_MISS = 5.0  # the key miss follows the host's reply to the client's push (the whole stream took 0.23 s in one run)
MISS = "Failed to read from hash map with key: client_%s_%s.data"  # loopData's miss of the client's own-world key (saveID, name)
GIFT_PUSH = "[coop-gift] the stored own world follows a gift"  # the client pushed its stored world at the gift
RC_OK = (0, 3221226505)
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
NEEDLES = {"DEFERRED_DROP": "[coop] the partner dropped during the host's deferred save",
           "CLEAR": "[coop-session] clearDeferredSave",
           "FREEZE": "[coop-session] freeze (lobbyMode=", "DROP": "[coop-session] onClientDrop",
           "CLOSE54": "[coop] the host's save wait (54) closes"}
PATH4 = ("DEFERRED_DROP", "CLEAR", "FREEZE", "DROP")

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
    return pick(q(gc, {"cmd": "get_coop"}), ("pendingHostSaveName", "saveID", "clientName", "onConnect", "resumeAck", "insideCoopBase", "error"))

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
        except FileNotFoundError:  # renamed after the listing (the save's .bak -> .asav move)
            pass
    return out

def misses(r, paths):
    """the names of the crash files among paths that hold the key miss r.miss (none before settle sets it)"""
    out = []
    for p in sorted(paths):
        with open(p, encoding="utf-8", errors="replace") as fh:
            if getattr(r, "miss", None) and r.miss in fh.read():
                out.append(os.path.basename(p))
    return out

def settle(r, x):
    """once the client's GiftSoldierMenu is gone (its handler, with any gift push, has run), n_push = the client's gift
    push lines; poll up to W_MISS until the key misses since the baseline number n_push (that push's stream failed on
    the key miss) -> ev["key_miss"]"""
    c = x.client
    gone, _s = wait(lambda: "GiftSoldierMenu" not in stack(c), W_UI)
    r.miss = MISS % (r.ev["at54"]["saveID"], r.ev["baseline"]["get_coop"].get("clientName"))
    r.n_push = sum(1 for ln in log(c) if GIFT_PUSH in ln)
    v, s = wait(lambda: len(misses(r, session._crash_log_snapshot() - r.cr0)) == r.n_push, W_MISS, 0.02)
    r.ev["key_miss"] = {"menu gone": bool(gone), "n_push": r.n_push,
                        "misses": misses(r, session._crash_log_snapshot() - r.cr0), "s": s}
    if not (gone and v and r.n_push <= 1):
        raise Stop("the key misses did not settle: %s" % r.ev["key_miss"])

def release(r, x):
    """leave_under_notice: the key miss off; poll up to W_SAVE until the host's CLEAR equals n_push (a gift push the key
    miss held lands under the notice and completes the save; with no push nothing lands before the leave)
    -> ev["release"]"""
    off = q(x.client, {"cmd": "force_stream_key_miss", "on": False})
    v, s = wait(lambda: counts(x.host, r.n_h)["CLEAR"] == r.n_push, W_SAVE, 0.02)
    r.ev["release"] = {"off": bool(off.get("ok") and off.get("on") is False), "CLEAR s": s if v else None}
    if not (r.ev["release"]["off"] and v):
        raise Stop("the key miss release: %s" % r.ev["release"])

def cpu():
    """the machine's CPU load (Processor(_Total)) and any Wardogs* process"""
    c = cpu_load()
    return "%s%s" % (cpu_text(c["cpu"]), " | " + ",".join(c["wardogs"]) if c["wardogs"] else "")

def probe_globe(path):
    """the named probe save's first embedded partner world's globe (PyYAML load_all, CSafeLoader when present; base64 or binary blob)"""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
        for d in docs:
            for e in d.get("coopClientSaves") or []:
                raw = e.get("blob")
                b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
                w = next((x for x in yaml.load_all(b.decode("utf-8", errors="replace"), Loader=loader) if isinstance(x, dict) and "bases" in x),
                         None)
                return {k: (w or {}).get(k) for k in ("globeLon", "globeLat", "globeZoom")}
    except Exception as e:  # a value
        return {"error": short(e, 200)}
    return {}

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
    """the client's first own-base soldier not in a craft renamed GIFTNAME, moved to the host's base; the 150's real OK"""
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
    back, _sb = wait(lambda: top(h) == "GeoscapeState", W_UI)
    ev["guest"] = {"soldier": sol and [sol.get("name"), sol.get("id")], "rename": rn.get("ok"), "transferred": tr.get("transferred"),
                   "150 s": s150 if v150 else None, "150 OK": ok150, "host back": bool(back)}
    if not (rn.get("ok") and tr.get("transferred") and v150 and ok150 and back):
        raise Stop("the guest not staged: %s" % ev["guest"])

def picker(x, ev):
    """the host's quick save, a named probe save (the blob's globe), the client's screen and select-destination CANCEL scale"""
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
    G = probe_globe(spath) if okn else {}
    cr = next((k for k in (own_base(c) or {}).get("crafts", []) if not k.get("coop")), None)
    q(c, {"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    time.sleep(0.4)
    cw = q(c, {"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.5)
    x.pk = {"G": G, "geom": geometry(c), "scale": cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}}
    ev["picker"] = {"quick s": sq if okq else None, "host": hq, "probe": bool(okn), "G": G, "scale": x.pk["scale"]}
    if not okq or hq[-1:] != ["GeoscapeState"] or not G or None in G.values() or "error" in G or not x.pk["scale"] or top(c) != "GeoscapeState":
        raise Stop("the picker missed: %s" % ev["picker"])

def visit(x, ev):
    c = x.client
    px = click_globe(c, x.hb["lon"], x.hb["lat"], x.pk)
    v, s = wait(lambda: coop(c).get("insideCoopBase") and top(c) == "BasescapeState", W_VISIT, 0.25)
    ev["visit"] = {"pixel": px, "inside s": s if v else None}
    if not v:
        raise Stop("the client not inside the host base within %.0f s: %s" % (W_VISIT, stack(c)))

def baseline(r, x):
    """The baseline, just before the trigger: crash snapshot, the host log's line count, stack, get_coop,
    coop_file_info, the folder"""
    h = x.host
    r.cr0, r.n_h = session._crash_log_snapshot(), len(log(h))
    r.ev["baseline"] = {"stack": stack(h), "get_coop": coop(h), "coop_file_info": blobinfo(h), "folder": files(h)}
    return r.ev["baseline"]

def at54(r, x):
    """save_game_ui quick; poll POLL_S up to SEEN54_S for the host's top 54 (name, saveID, CLEAR); the client's 67 within W_67"""
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
    """real presses: OK on the 67, SOLDIERS, the guest's row, KP2, the host's button; POLL_S up to W_NOTICE for the host's notice"""
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
    miss_on = q(c, {"cmd": "force_stream_key_miss", "on": True})  # no client world lands before the drop / release
    seq["key miss on"] = bool(miss_on.get("ok") and miss_on.get("on") is True)
    if not seq["key miss on"]:
        raise Stop("force_stream_key_miss not armed on the client: %s" % miss_on)
    tg = time.time()
    seq["host button"] = real_click(c, hostbtn, W_UI)
    while time.time() - tg < W_NOTICE:
        if top(h) == "GiftNoticeState":
            tn = time.time()
            cp = coop(h)
            ev["notice"] = {"s": round(tn - tg, 3), "stack": stack(h), "name": cp.get("pendingHostSaveName"), "CLEAR": counts(h, r.n_h)["CLEAR"]}
            return tn
        time.sleep(POLL_S)
    raise Stop("no GiftNoticeState on the host within %.0f s of the gift click: %s" % (W_NOTICE, stack(h)))

def leave_base(x, ev, label):
    """OK on SoldierInfoState / SoldiersState, GEOSCAPE; back on its own geoscape within W_BACK -> GEOSCAPE's time"""
    c, oks = x.client, []
    for _ in range(4):
        if top(c) not in ("SoldierInfoState", "SoldiersState"):
            break
        oks.append(real_click(c, "OK", W_UI))
        time.sleep(0.5)
    g = real_click(c, "GEOSCAPE", W_UI)
    tg = time.time()
    try:
        session.wait_back_on_geoscape(c, "%s back" % label, timeout=W_BACK)
        back = True
    except Exception as e:  # a value: the row ends
        back = short(e, 300)
    ev["leave"] = {"OKs": oks, "GEOSCAPE": g, "back": back, "s": round(time.time() - tg, 3)}
    if back is not True:
        raise Stop("the client not back on its geoscape within %.0f s: %s" % (W_BACK, back))
    return tg

def rejoin(r, x):
    """a NEW client (fresh dir) joins KEY as the baseline clientName; profile_ok on a Profile top; resumeAck + 62 within
    JOIN_S"""
    h = x.host
    name = r.ev["baseline"]["get_coop"].get("clientName") or REJOIN_NAME
    x.client2 = x.client = GameClient("client2", None, make_user_dir(x.tag + "_client2"))
    x.client.spawn(); x.client.connect()
    tj, gc, n = time.time(), x.client, 0
    j = pick(q(gc, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": name}), ("ok", "error"))
    while time.time() - tj < JOIN_S:
        for m in (h, gc):
            if top(m) == "Profile" and (m is h or dlg(gc).get("code") != 52):
                n += 1 if q(m, {"cmd": "profile_ok"}).get("ok") else 0
        if coop(h).get("resumeAck") is True and top(h) == "CoopState" and dlg(h).get("code") == 62:
            r.ev["rejoin"] = {"name": name, "pin": name == REJOIN_NAME, "join": j, "profile_ok": n, "s": round(time.time() - tj, 2)}
            return
        time.sleep(0.1)
    r.ev["rejoin"] = {"name": name, "join": j, "profile_ok": n, "s": None, "host": stack(h), "host dialog": dlg(h), "rejoiner": stack(gc)}
    raise Stop("the host's resumeAck with its 62 on top not within %.0f s: %s" % (JOIN_S, r.ev["rejoin"]))

def read(r, x):
    """a read: the host stack, coop_dialog_info, get_coop, the folder (QUICK), the needle counts since the baseline,
    host alive, new crash files"""
    h = x.host
    rd = {"stack": stack(h), "dialog": dlg(h), "get_coop": coop(h), "folder": files(h), "needles": counts(h, r.n_h), "alive": alive(h),
          "new crash": sorted(session._crash_log_snapshot() - r.cr0)}
    a, b = rd["folder"].get(QUICK), r.ev["baseline"]["folder"].get(QUICK)
    rd["written"], rd["mtime"] = bool(a and (b is None or a[1] > b[1])), a and a[1]
    rd["misses"] = misses(r, rd["new crash"])
    return rd

def written(r, x):
    """QUICK's mtime_ns newer than the baseline's"""
    a, b = files(x.host).get(QUICK), r.ev["baseline"]["folder"].get(QUICK)
    return bool(a and (b is None or a[1] > b[1]))

def wait_back(r, x):
    """poll POLL_S up to W_CLOSE for back(): the host stack == the baseline's (top GeoscapeState) -> seconds or None"""
    v, s = wait(lambda: stack(x.host) == r.ev["baseline"]["stack"], W_CLOSE, POLL_S)
    return s if v else None

class Row:
    """cells are recorded as decided; end() prints EVIDENCE, every cell, ONE CAPTURE line on a failure and the row verdict"""
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.n_h = rid, cells, x, [], set(), time.time(), 0
        self.cr0, self.ev, self.lines = session._crash_log_snapshot(), {}, []

    def cell(self, cid, kind, label, ok):
        self.lines.append("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label))
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            self.lines.append("FAIL %s: not reached (%s)" % (cid, str(why)[:160]))
            self.fails.append(cid)

    def end(self, results, walls, cap=None):
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)
        print("\n".join(self.lines), flush=True)
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
        self.ev["cpu"] = self.x.cpu
        self.cell(self.cells[0], "GUARD", "boot: both tops GeoscapeState unchanged %.0f s not reached (%s)" % (STABLE_S, self.x.err), False)
        self.stop("boot")
        self.end(results, walls, cap=self.x.cap)

def to_notice(r, x):
    """the guest, the picker, the visit, the baseline, the trigger, HOLD_PRE, the gift: the notice on top over the
    baseline stack + [CoopState], name QUICK, CLEAR +0"""
    ev = r.ev
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
    return B, tn

def guard(r, cid, label, fn):
    """run fn (a precondition); any miss fails cid and ends the row (re-raised), else cid passes"""
    try:
        v = fn()
    except Exception:
        r.cell(cid, "GUARD", label, False)
        raise
    r.cell(cid, "GUARD", label, True)
    return v

def ok_and_close(r, x, p):
    """the host's real OK on the notice, back() within W_CLOSE, the end read; the -close and -log cells"""
    ok = r.ev["notice OK"] = real_click(x.host, "OK", W_UI)
    bs = r.ev["back s"] = wait_back(r, x)
    E = r.ev["end_read"] = read(r, x)
    r.cell(p + "-close", "FIX", "back(): the host stack == the baseline's (top GeoscapeState) within %.0f s after the "
           "notice's OK (when broken: top CoopState 54 \"Saving...\" with nothing armed)" % W_CLOSE,
           bool(ok and bs is not None))
    r.cell(p + "-log", "FIX", "CLOSE54 = 1 at the end read (when broken: 0)", E["needles"]["CLOSE54"] == 1)
    return E

def common_cell(r, p, E):
    """every crash_*.log new since the baseline is the key miss, one per gift push (n_push; armed_wait arms no key
    miss: 0)"""
    n = getattr(r, "n_push", 0)
    r.cell(p + "-common", "GUARD", "the host alive at the end read; every crash_*.log new since the baseline is the "
           "key miss %s, %d of them" % (getattr(r, "miss", None), n),
           bool(E["alive"] and len(E["misses"]) == len(E["new crash"]) == n))

def row_leave_under_notice(x, results, walls):
    """the gift's notice over the 54; the client leaves the base; the write lands under the notice; the host's OK"""
    r = Row("leave_under_notice", ["leave_under_notice-pre", "leave_under_notice-close", "leave_under_notice-log",
                                   "leave_under_notice-once", "leave_under_notice-common"], x)
    if x.err:
        return r.boot_miss(results, walls)
    ev = r.ev
    ev["cpu"] = x.cpu

    def pre():
        B, _tn = to_notice(r, x)
        release(r, x)
        tg = leave_base(x, ev, "leave_under_notice")
        v, _s = wait(lambda: written(r, x), W_SAVE, 0.02)
        ev["written s after GEOSCAPE"] = round(time.time() - tg, 3) if v else None
        time.sleep(WAIT_W)
        W = ev["leave_read"] = read(r, x)
        n = W["needles"]
        if not (W["written"] and n["CLEAR"] == 1 and n["DEFERRED_DROP"] == 0
                and W["stack"] == B["stack"] + ["CoopState", "GiftNoticeState"]
                and W["get_coop"].get("pendingHostSaveName") == ""):
            raise Stop("the leave read: %s" % json.dumps(W, default=str)[:400])
        return W
    try:
        W = guard(r, "leave_under_notice-pre", "construction met; the 54 on top within %.0f s, name %s, CLEAR +0; the "
                  "notice on top over the baseline stack + [CoopState], name %s; the client back on its geoscape; the "
                  "leave read: %s written once (CLEAR 1, DEFERRED_DROP 0), host stack the baseline + [CoopState, "
                  "GiftNoticeState], name \"\"" % (SEEN54_S, QUICK, QUICK, QUICK), pre)
        E = ok_and_close(r, x, "leave_under_notice")
        r.cell("leave_under_notice-once", "GUARD", "%s's mtime_ns at the end read == at the leave read; CLEAR still 1; "
               "name \"\" (the close writes nothing)" % QUICK,
               bool(E["mtime"] == W["mtime"] and E["needles"]["CLEAR"] == 1 and E["get_coop"].get("pendingHostSaveName") == ""))
        common_cell(r, "leave_under_notice", E)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_drop_and_rejoin(x, results, walls):
    """kill at the notice; the drop write; a NEW client rejoins; the host's RESUME; the notice's OK"""
    r = Row("drop_and_rejoin", ["drop_and_rejoin-pre", "drop_and_rejoin-rejoin", "drop_and_rejoin-close",
                                "drop_and_rejoin-log", "drop_and_rejoin-once", "drop_and_rejoin-common"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, ev = x.host, r.ev
    ev["cpu"] = x.cpu

    def pre():
        B, tn = to_notice(r, x)
        td = time.time()
        x.client.kill()
        ev["drop"] = {"event": "client.kill()", "s after notice": round(td - tn, 3), "rc": x.client.proc.poll()}
        while time.time() - td < HOLD_S:
            time.sleep(0.05)
        D = ev["drop_read"] = read(r, x)
        if not (not alive(x.client) and D["written"] and tuple(D["needles"][k] for k in PATH4) == (1, 1, 1, 1)
                and D["stack"] == B["stack"] + ["CoopState", "GiftNoticeState", "CoopState"]
                and D["dialog"].get("code") == 62):
            raise Stop("the drop read: %s" % json.dumps(D, default=str)[:400])
        return D

    def back_in():
        rejoin(r, x)
        ev["RESUME"] = real_click(h, "RESUME", W_RESUME)
        v, s = wait(lambda: top(h) == "GiftNoticeState", W_RESUME, 0.02)
        ev["notice after RESUME s"] = s if v else None
        R = ev["resume_read"] = read(r, x)
        if not (ev["RESUME"] and v and R["stack"] == ev["baseline"]["stack"] + ["CoopState", "GiftNoticeState"]
                and R["get_coop"].get("pendingHostSaveName") == ""):
            raise Stop("after RESUME: %s" % json.dumps(R, default=str)[:400])
    try:
        D = guard(r, "drop_and_rejoin-pre", "construction met; the notice on top over the baseline stack + "
                  "[CoopState], name %s, CLEAR +0; the client exited; the drop read %.0f s after the kill: %s written, "
                  "(DEFERRED_DROP, CLEAR, FREEZE, DROP) = (1, 1, 1, 1), host stack the baseline + [CoopState, "
                  "GiftNoticeState, CoopState], code 62 (the drop write)" % (QUICK, HOLD_S, QUICK), pre)
        guard(r, "drop_and_rejoin-rejoin", "the NEW client joins %s: the host's resumeAck true with its 62 on top "
              "within %.0f s; the host's real RESUME; GiftNoticeState on top within %.0f s; the resume read: stack the "
              "baseline + [CoopState, GiftNoticeState], name \"\"" % (KEY, JOIN_S, W_RESUME), back_in)
        E = ok_and_close(r, x, "drop_and_rejoin")
        r.cell("drop_and_rejoin-once", "GUARD",
               "%s's mtime_ns at the end read == at the drop read; CLEAR still 1" % QUICK,
               bool(E["mtime"] == D["mtime"] and E["needles"]["CLEAR"] == 1))
        common_cell(r, "drop_and_rejoin", E)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_armed_wait(x, results, walls):
    """the armed-wait guard: no gift; HOLD_W; the client's OK on its 67 + GEOSCAPE; the blob handler writes and pops
    the 54"""
    r = Row("armed_wait", ["armed_wait-pre", "armed_wait-hold", "armed_wait-write", "armed_wait-log",
                           "armed_wait-common"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, c, ev = x.host, x.client, r.ev
    ev["cpu"] = x.cpu

    def pre():
        picker(x, ev)
        visit(x, ev)
        baseline(r, x)
        a = at54(r, x)
        if a["name"] != QUICK or a["CLEAR"] != 0 or a["67 s"] is None:
            raise Stop("at the 54: %s" % a)
    try:
        guard(r, "armed_wait-pre", "construction met (no guest); the 54 on top within %.0f s, name %s, CLEAR +0; the "
              "client's 67 within %.0f s" % (SEEN54_S, QUICK, W_67), pre)
        time.sleep(HOLD_W)
        H = ev["hold_read"] = read(r, x)
        r.cell("armed_wait-hold", "GUARD", "the hold read after %.0f s: host top CoopState with code 54, name %s, "
               "CLEAR 0 (the 54's own close does nothing while armed)" % (HOLD_W, QUICK),
               bool(H["stack"][-1:] == ["CoopState"] and H["dialog"].get("code") == 54
                    and H["get_coop"].get("pendingHostSaveName") == QUICK and H["needles"]["CLEAR"] == 0))
        ev["67 OK"] = real_click(c, dlg(c).get("backText") or "OK", W_UI)
        time.sleep(0.3)
        tg = leave_base(x, ev, "armed_wait")
        v, _s = wait(lambda: written(r, x) and stack(h) == ev["baseline"]["stack"], W_SAVE, 0.02)
        ev["written and back s after GEOSCAPE"] = round(time.time() - tg, 3) if v else None
        time.sleep(1.0)
        E = ev["end_read"] = read(r, x)
        r.cell("armed_wait-write", "GUARD", "within %.0f s of the client's GEOSCAPE: %s written and back() (the blob "
               "handler's pop); at the end read CLEAR 1, name \"\"" % (W_SAVE, QUICK),
               bool(v and E["needles"]["CLEAR"] == 1 and E["get_coop"].get("pendingHostSaveName") == ""))
        r.cell("armed_wait-log", "GUARD", "CLOSE54 = 0 at the hold and end reads (an armed 54 never closes itself)",
               H["needles"]["CLOSE54"] == 0 and E["needles"]["CLOSE54"] == 0)
        common_cell(r, "armed_wait", E)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def boot(rid, tag):
    """CPU, spawn, connect, HOST_POS, new_campaign(port=KEY), slow_clock, both tops GeoscapeState STABLE_S (else x.err, x.cap)"""
    x = SimpleNamespace(rid=rid, tag=tag, host=None, client=None, client1=None, client2=None, err=None, cap=None, cpu=cpu(), hb=None, pk=None)
    try:
        x.host, x.client = GameClient("host", None, make_user_dir(tag + "_host")), GameClient("client", None, make_user_dir(tag + "_client"))
        x.client1 = x.client
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
    """every machine of the boot (the killed client was reaped by kill(); drop_and_rejoin's rejoiner too) -> the
    shutdown failures"""
    failed = []
    for gc in (x.client2, x.client1, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

ROWS = (("leave_under_notice", "wait_closes_leave_under_notice", row_leave_under_notice),
        ("drop_and_rejoin", "wait_closes_drop_and_rejoin", row_drop_and_rejoin),
        ("armed_wait", "wait_closes_armed_wait", row_armed_wait))

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
    print("\ntest_host_save_wait_closes: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _t, _r in ROWS if results.get(rid)), len(ROWS), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
