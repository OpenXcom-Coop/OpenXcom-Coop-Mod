"""test_client_base_mirror_dup.py: after a SEPARATE resume the host keeps ONE mirror of the partner's base. The host's
baseRequest is answered with the partner's coopBase3 (copy 1) before the partner's once-per-connection coopBase arrives;
the host's coopBase handler must refresh that mirror in place (same id and position) instead of adding copy 2. Two
identical "ClientBase" mirrors with the same crafts would make a click on the partner's base marker list "ClientBase"
twice and a click on a partner craft list that craft twice.
Lobby keys "49189" / "49190" (bring-up / resume), user dirs client_base_mirror_dup_*. ONE SEPARATE boot, the host base
apart from the client base (X = the client base's position, P = a client interceptor patrolling near X).
Rows: before_save (controls before the save) before_save_one_mirror, before_save_craft_window, before_save_base_visit;
the host's named save, both games end, the host respawns on its dir, client2 on an EMPTY dir, session.resume_campaign,
T = its return; resume_reads: resume_one_mirror_5s, resume_crafts_once (T + 5 s), resume_client_one_mirror,
resume_one_mirror_30s (T + 30 s); resume_craft_click (a real click on the patrolling partner craft, between the two
resume reads): resume_craft_window; resume_base_click (a real click on the partner's base marker, LAST):
resume_base_visit, resume_base_back, no_crash. Real presses only: inject_input clicks at the projected pixel, Esc on a
list, click_widget GEOSCAPE in a peer base; no popup drain inside a peer base, never leave_base / coop_dialog_back /
dismiss_popup. With a second mirror, resume_one_mirror_5s, resume_crafts_once, resume_craft_window,
resume_one_mirror_30s and resume_base_visit fail (the FIX cells; exit 2); with one mirror all 11 cells pass. ONE run,
no skip; exit 0 only if all pass, else 2.
Run:  python tools/coop_test/test_client_base_mirror_dup.py
"""

import base64, glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
import yaml  # noqa: E402

# ----- setup values -----
KEY_BRINGUP = "49189"
KEY_RESUME = "49190"
TAG, SAVE, PROBE_BEFORE, PROBE_AFTER = (
    "client_base_mirror_dup", "client_base_mirror_dup.sav", "mirror_dup_probe_before.sav", "mirror_dup_probe_after.sav")
HOST_POS, SPLIT_MIN, PATROL_OFF = (0.90, -0.60), 0.15, (0.30, 0.10)   # rad: host base, split, P's patrol point from X
MIRROR_S, CRAFT_S, SAVE_S, EARLY_READ_S, LATE_READ_S, DWELL_S, VISIT_S = 30, 10, 30, 5, 30, 2.0, 60   # s
ESC = 27                                                                 # SDLK_ESCAPE = Options::keyCancel
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]                              # Globe::setupRadii, x the globe height
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
ROWS = {"before_save": ["before_save_one_mirror", "before_save_craft_window", "before_save_base_visit"],
        "resume_reads": ["resume_one_mirror_5s", "resume_crafts_once", "resume_client_one_mirror",
                         "resume_one_mirror_30s"],
        "resume_craft_click": ["resume_craft_window"],
        "resume_base_click": ["resume_base_visit", "resume_base_back", "no_crash"]}
FIX = {"resume_one_mirror_5s", "resume_crafts_once", "resume_craft_window", "resume_one_mirror_30s",
       "resume_base_visit"}
RESULTS, EV = [], {"rows": {r: [] for r in list(ROWS) + ["END"]}}
T0 = time.time()

class BootMiss(Exception): pass
class RowMiss(Exception): pass

def now(): return round(time.time() - T0, 2)
def step(row, label, **kw): EV["rows"][row].append(dict({"t": now(), "step": label}, **kw))
def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
def block(names, why):
    for n in [n for n in names if n not in {x[0] for x in RESULTS}]:
        cell(n, False, why)
def load():
    """CPU (Processor(_Total) % Processor Time, the last 2 s; harness.cpu_load) and the count of foreign game
    processes."""
    c = harness.cpu_load()
    return {"cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}

# ----- probes -----
def gs(gc): return gc.ok({"cmd": "geo_state"})
def stack(gc): return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
def texts(gc): return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
def inside(gc): return gc.cmd({"cmd": "get_coop"}).get("insideCoopBase")
def crash_set(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def own_base(g): return next((b for b in g.get("bases", []) if not b.get("coopIcon") and not b.get("coopBase")), None)
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def brief(r): return {"t": r["t"], "copies": r["copies"], "icons": r["icons"], "stack": r["stack"]}
def icons_of(g):
    """The coop-icon bases of a geo_state reply, in list order: [idx, id, name, lon hex, lat hex, crafts (type-id)]."""
    return [[i, b.get("coopBaseId"), b.get("name"), float(b.get("lon")).hex(), float(b.get("lat")).hex(),
             [f"{c.get('type')}-{c.get('id')}" for c in b.get("crafts", [])]] for i, b in enumerate(g.get("bases", [])) if b.get("coopIcon")]
def read(gc, bid):
    """copies(gc, bid) = the coop-icon bases with coopBaseId bid; keys(gc, bid) = the type-id of every craft in them."""
    g = gs(gc)
    cps = [b for b in g.get("bases", []) if b.get("coopIcon") and b.get("coopBaseId") == bid]
    return {"t": now(), "copies": len(cps), "keys": [f"{c.get('type')}-{c.get('id')}" for b in cps for c in b.get("crafts", [])],
            "crafts": [c for b in cps for c in b.get("crafts", [])], "icons": icons_of(g), "own": own_base(g), "stack": stack(gc)}
def wait(pred, timeout, interval=0.25):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 2)
        time.sleep(interval)
def drain(gc):
    """geo.drain_popups only while gc stands on its own world (insideCoopBase false, no BasescapeState): a drain inside
    a peer base closes the partner base screen and the game ends in a defeat."""
    st, ins = stack(gc), inside(gc)
    return {"skipped": [ins, st]} if ins or "BasescapeState" in st else {"drained": geo.drain_popups(gc)[0]}
def capture(err, *machines):
    """ONE CAPTURE line (stack, get_coop, the coop-icon bases, list_widgets, the log tail per machine); boot FAIL."""
    cap = {}
    for gc in (g for g in machines if g is not None and g.proc is not None and g.proc.poll() is None):
        try:
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "get_coop": gc.cmd({"cmd": "get_coop"}), "icons": icons_of(gs(gc)), "widgets": texts(gc),
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE: {json.dumps({'missed': err, 'machines': cap}, sort_keys=True, default=str)}", flush=True)
    raise BootMiss(err)

# ----- saves -----
def read_save(path):
    def world(d):
        return {"bases": [[b.get("name"), b.get("coopbaseid", "absent")] for b in (d or {}).get("bases") or []],
                "globe": {k: (d or {}).get(k) for k in ("globeLon", "globeLat", "globeZoom")}}
    out, loader = {"file": os.path.basename(path), "bytes": os.path.getsize(path)}, getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    for d in docs:
        if "bases" in d:
            out["world"] = world(d)
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            blob = (base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)).decode("utf-8", errors="replace")
            out["blob"] = world(next((x for x in yaml.load_all(blob, Loader=loader) if isinstance(x, dict) and "bases" in x), None))
    return out
def named_save(host, name):
    """The host's named save_game; the file on disk (non-empty) within SAVE_S. Returns (reply, seconds, read_save or None)."""
    path = os.path.join(host.user_dir, "xcom1", name)
    n = host.cmd({"cmd": "save_game", "file": name})
    ok, s = wait(lambda: os.path.exists(path) and os.path.getsize(path) > 0, SAVE_S, 0.2)
    time.sleep(1.0)
    return n, s, read_save(path) if ok else None
def probe_save(host, name):
    """The save for the picker probe: the quick save through SaveGameState, 2 s, a drain on the own world, the named
    save."""
    qpath, t0 = os.path.join(host.user_dir, "xcom1", "_quick_.asav"), time.time()
    q = host.cmd({"cmd": "save_game_ui", "type": "quick"})
    okq, _ = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, SAVE_S, 0.2)
    time.sleep(2.0)
    drain(host)
    n, s, f = named_save(host, name)
    return {"quick": [q.get("ok"), okq], "named": [n.get("ok"), s], "file": f}

# ----- the globe picker and real clicks -----
def project(G, lon, lat, geom):
    cl, ct = G["globeLon"], G["globeLat"]
    R = ZOOM[int(G["globeZoom"])] * geom["H"]
    c = math.cos(ct) * math.cos(lat) * math.cos(lon - cl) + math.sin(ct) * math.sin(lat)
    x = geom["W"] // 2 + math.floor(R * math.cos(lat) * math.sin(lon - cl))
    y = geom["H"] // 2 + math.floor(R * (math.cos(ct) * math.sin(lat) - math.sin(ct) * math.cos(lat) * math.cos(lon - cl)))
    return x, y, c >= 0.0
def geometry(gc):
    b = next((x for x in gc.ok({"cmd": "list_widgets"}).get("widgets", []) if str(x.get("text") or "").upper().startswith("INTERCEPT")), None)
    sw, sh = (b["x"] + 63, 2 * (b["y"] + 100)) if b else (320, 200)
    return {"W": sw - 64, "H": sh, "fallback": not b}
def picker_geometry(gc, probe, row):
    """G from a host probe save, the screen from INTERCEPT, the window scale from a picker CANCEL on the host's first own craft."""
    p = probe_save(gc, probe)
    cr = next((c for c in (own_base(gs(gc)) or {}).get("crafts", []) if not c.get("coop")), None)
    op = gc.cmd({"cmd": "open_select_destination", "craft_id": cr and cr["id"], "craft_type": cr and cr["type"]})
    cw = gc.cmd({"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.4)
    G = ((p["file"] or {}).get("world") or {}).get("globe") or {}
    pk = {"G": G, "geom": geometry(gc), "scale": cw.get("baseX") and {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]},
          "craft": cr and f"{cr['type']}-{cr['id']}", "open": op.get("ok"), "save": p, "after": stack(gc)}
    step(row, "picker", **{k: pk[k] for k in ("G", "geom", "scale", "craft", "open", "after")}, save=p["named"])
    if not op.get("ok") or not pk["scale"] or None in G.values() or not G or pk["after"][-1:] != ["GeoscapeState"]:
        raise RowMiss(f"picker geometry {json.dumps(pk, default=str)[:400]}")
    return pk
def click(gc, lon, lat, pk, row, label):
    """A real left click (inject_input) at the projected pixel of (lon, lat), trying the CLICKS offsets until the top is
    not GeoscapeState; every state seen in 0.9 s per offset, a CoopState with coop_dialog_info."""
    x, y, front = project(pk["G"], lon, lat, pk["geom"])
    tries = []
    for dx, dy in CLICKS:
        wx, wy = int((x + dx) * pk["scale"]["x"] + 1), int((y + dy) * pk["scale"]["y"] + 1)
        gc.ok({"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        trace, t4 = [], time.time()
        while time.time() - t4 < 0.9:
            st = stack(gc)
            if st[-1:] == ["MultipleTargetsState"]:  # read once more, on a later frame: a one-target MultipleTargetsState
                st = stack(gc)                       # closes itself in its first init() (vanilla); a picker stays on top
            e = {"t": now(), "top": st[-1] if st else None}
            if e["top"] == "CoopState":
                e["dialog"] = [(d := gc.cmd({"cmd": "coop_dialog_info"})).get("code"), d.get("title")]
            if not trace or trace[-1]["top"] != e["top"]:
                trace.append(e)
            time.sleep(0.03)
        st = stack(gc)
        tries.append({"t": now(), "px": [x + dx, y + dy], "win": [wx, wy], "top": st[-1] if st else None, "texts": texts(gc), "trace": trace})
        if tries[-1]["top"] != "GeoscapeState":
            break
    r = {"label": label, "target": [lon, lat], "pixel": [x, y, front], "tries": tries, "top": tries[-1]["top"], "texts": tries[-1]["texts"],
         "seen": [e["top"] for t in tries for e in t["trace"]] + [tries[-1]["top"]],
         "codes": [e["dialog"][0] for t in tries for e in t["trace"] if e.get("dialog")]}
    step(row, "click " + label, **{k: r[k] for k in ("target", "pixel", "top", "seen", "codes", "texts")}, tries=tries)
    return r
def esc(gc, row, label):
    """Esc (keyCancel) on the open window, 0.6 s; a CANCEL click only if the top is still not GeoscapeState."""
    gc.ok({"cmd": "inject_input", "kind": "key", "key": ESC})
    time.sleep(0.6)
    r = {"esc": stack(gc)}
    if r["esc"][-1:] != ["GeoscapeState"]:
        r["cancel"] = gc.cmd({"cmd": "click_widget", "match": "CANCEL"}).get("ok")
        time.sleep(0.5)
        r["after"] = stack(gc)
    r["top"] = (r.get("after") or r["esc"] or [None])[-1]
    step(row, "esc " + label, **r)
    return r
def leave(gc, row, label):
    """Wait (VISIT_S) for insideCoopBase true on BasescapeState, DWELL_S, a real click_widget GEOSCAPE, wait_back_on_geoscape."""
    seen, t1, r = [], time.time(), {"inside": False}
    while time.time() - t1 < VISIT_S:
        st, ins = stack(gc), inside(gc)
        if not seen or seen[-1][1:] != [st, ins]:
            seen.append([now(), st, ins])
        if ins and st[-1:] == ["BasescapeState"]:
            r = {"inside": True, "insideT": now(), "insideTexts": texts(gc)[:3]}
            break
        time.sleep(0.25)
    r["seen"] = seen
    if r["inside"]:
        time.sleep(DWELL_S)
        r["dwell"] = [now(), stack(gc), inside(gc)]
        cw = gc.cmd({"cmd": "click_widget", "match": "GEOSCAPE"})
        r["geoscape"] = [now(), cw.get("ok"), cw.get("error")]
        try:
            session.wait_back_on_geoscape(gc, f"{label} back on the geoscape")
            r["back"] = True
        except Exception as e:  # noqa: BLE001
            r["back"] = f"{type(e).__name__}: {str(e)[:200]}"
        r["backT"], r["after"] = now(), stack(gc)
    step(row, "leave " + label, **r)
    return r

# ----- rows -----
def row_before_save(x):
    host, client, CB, HB, X = x["host"], x["client"], x["CB"], x["HB"], x["X"]
    step("before_save", "load", **load())
    h, c = read(host, CB), read(client, HB)
    step("before_save", "read", host=brief(h), client=brief(c), hostKeys=h["keys"], clientKeys=c["keys"])
    cell("before_save_one_mirror", h["copies"] == 1 and c["copies"] == 1,
         f"copies(host, CB {CB}) {h['copies']}, copies(client, HB {HB}) {c['copies']} (want 1 / 1)")
    pk = picker_geometry(host, PROBE_BEFORE, "before_save")
    pm = next((k for k in h["crafts"] if f"{k['type']}-{k['id']}" == x["pkey"]), None)
    if not pm:
        raise RowMiss(f"P {x['pkey']} mirror missing on the host")
    step("before_save", "drain", **drain(host))
    r = click(host, pm["lon"], pm["lat"], pk, "before_save", "before_save_craft")
    e = (esc(host, "before_save", "before_save_craft") if r["top"] != "GeoscapeState"
         else {"top": "GeoscapeState (never left)"})
    cell("before_save_craft_window",
         r["top"] == "GeoscapeCraftState" and "MultipleTargetsState" not in r["seen"] and e["top"] == "GeoscapeState",
         f"click {x['pkey']} at {r['pixel']}: top {r['top']}, seen {r['seen']}, texts {r['texts'][:5]}; Esc -> {e['top']} "
         f"(want GeoscapeCraftState, no MultipleTargetsState, then GeoscapeState)")
    if e["top"] != "GeoscapeState":
        raise RowMiss(f"host top {e['top']} after the craft window")
    step("before_save", "drain", **drain(host))
    r = click(host, X[0], X[1], pk, "before_save", "before_save_base")
    if r["top"] in ("CoopState", "BasescapeState"):
        v = leave(host, "before_save", "before_save_base")
    else:
        v = (esc(host, "before_save", "before_save_base") if r["top"] != "GeoscapeState"
             else {"top": "GeoscapeState (never left)"})
    h = read(host, CB)
    step("before_save", "read after", host=brief(h))
    ok = (50 in r["codes"] or "BasescapeState" in r["seen"]) and v.get("inside") and v.get("back") is True
    cell("before_save_base_visit", ok and (h["own"] or {}).get("coopBaseId") == HB and h["copies"] == 1,
         f"click X at {r['pixel']}: codes {r['codes']}, seen {r['seen']}, texts {r['texts'][:3]}; inside {v.get('inside')}, GEOSCAPE "
         f"{v.get('geoscape')}, back {v.get('back')}; own base {(h['own'] or {}).get('coopBaseId')}, copies {h['copies']} (want CoopState 50 / "
         f"BasescapeState, inside, back, own base {HB}, 1 copy)")
def row_resume_reads(x, part):
    host, c2, CB, HB = x["host"], x["client2"], x["CB"], x["HB"]
    if part == "5s":
        time.sleep(max(0.0, x["T"] + EARLY_READ_S - time.time()))
        ck = sorted(f"{c['type']}-{c['id']}" for c in (own_base(gs(c2)) or {}).get("crafts", []))
        if not ck:
            raise RowMiss("client2 holds no own base craft")
        h, w = wait(lambda: (lambda s: s if all(k in s["keys"] for k in ck) else None)(read(host, CB)), CRAFT_S)
        h = h or read(host, CB)
        c = x["client5s"] = read(c2, HB)
        cnt = {k: h["keys"].count(k) for k in ck}
        step("resume_reads", "read +5 s", tRel=round(time.time() - x["T"], 2), craftWait=w, client2Crafts=ck,
             host=brief(h), hostKeys=h["keys"], client2=brief(c))
        cell("resume_one_mirror_5s", h["copies"] == 1,
             f"copies(host, CB {CB}) {h['copies']} at T + {round(h['t'] - x['Tb'], 2)} s (want 1)")
        cell("resume_crafts_once", all(v == 1 for v in cnt.values()),
             f"client2's crafts in keys(host, CB): {cnt} (want each exactly once)")
        x["read5sOk"] = True
        return
    time.sleep(max(0.0, x["T"] + LATE_READ_S - time.time()))
    h, c = read(host, CB), read(c2, HB)
    step("resume_reads", "read +30 s", tRel=round(time.time() - x["T"], 2), host=brief(h), hostKeys=h["keys"],
         client2=brief(c))
    c5 = x["client5s"]["copies"]
    cell("resume_client_one_mirror", c5 == 1 and c["copies"] == 1,
         f"copies(client2, HB {HB}) {c5} at +5 s, {c['copies']} at +30 s (want 1 / 1)")
    cell("resume_one_mirror_30s", h["copies"] == 1,
         f"copies(host, CB {CB}) {h['copies']} at T + {round(h['t'] - x['Tb'], 2)} s (want 1)")
def row_resume_craft_click(x):
    host, CB = x["host"], x["CB"]
    step("resume_craft_click", "load", **load())
    step("resume_craft_click", "drain", **drain(host))
    pk = x["pkAfter"] = picker_geometry(host, PROBE_AFTER, "resume_craft_click")
    pm = [k for k in read(host, CB)["crafts"] if f"{k['type']}-{k['id']}" == x["pkey"]]
    step("resume_craft_click", "P mirror", tRel=round(time.time() - x["T"], 2),
         P=[[k["status"], k["lon"], k["lat"]] for k in pm])
    if not pm or pm[0]["status"] != "STR_OUT":
        raise RowMiss(f"P {x['pkey']} mirror on the host not STR_OUT: {pm}")
    r = click(host, pm[0]["lon"], pm[0]["lat"], pk, "resume_craft_click", "resume_craft")
    e = (esc(host, "resume_craft_click", "resume_craft") if r["top"] != "GeoscapeState"
         else {"top": "GeoscapeState (never left)"})
    cell("resume_craft_window", r["top"] == "GeoscapeCraftState" and "MultipleTargetsState" not in r["seen"],
         f"click {x['pkey']} at {r['pixel']}: top {r['top']}, seen {r['seen']}, texts {r['texts'][:5]}; Esc -> {e['top']} "
         f"(want GeoscapeCraftState, no MultipleTargetsState)")
def row_resume_base_click(x):
    host, c2, CB, HB, X = x["host"], x["client2"], x["CB"], x["HB"], x["X"]
    step("resume_base_click", "load", **load())
    st, ins = stack(host), inside(host)
    if st[-1:] != ["GeoscapeState"] or ins or not x.get("pkAfter"):
        raise RowMiss(f"host stack {st}, insideCoopBase {ins}, picker {bool(x.get('pkAfter'))} before the base click")
    step("resume_base_click", "drain", **drain(host))
    r = click(host, X[0], X[1], x["pkAfter"], "resume_base_click", "resume_base")
    if r["top"] in ("CoopState", "BasescapeState"):
        v = leave(host, "resume_base_click", "resume_base")
        back = v.get("back") is True
    else:
        v = (esc(host, "resume_base_click", "resume_base") if r["top"] != "GeoscapeState"
             else {"top": "GeoscapeState (never left)"})
        back = v["top"] == "GeoscapeState"
    cell("resume_base_visit", (50 in r["codes"] or "BasescapeState" in r["seen"]) and v.get("inside") is True and
         "MultipleTargetsState" not in r["seen"],
         f"click X at {r['pixel']}: top {r['top']}, codes {r['codes']}, seen {r['seen']}, texts {r['texts'][:4]}; inside {v.get('inside')} "
         f"(want CoopState 50 / BasescapeState, inside the partner's base, no MultipleTargetsState)")
    h = read(host, CB)
    cell("resume_base_back", back and (h["own"] or {}).get("coopBaseId") == HB,
         f"back {v.get('back', v.get('top'))}, host stack {h['stack']}, own base "
         f"{(h['own'] or {}).get('coopBaseId')} (want back on its own geoscape, own base {HB})")
def run_row(row, fn, *a):
    try:
        fn(*a)
    except RowMiss as e:
        step(row, "precondition miss", why=str(e))
        block(ROWS[row], f"not reached ({str(e)[:300]})")
def boot(x):
    """Bring-up (split host base), P, before_save, the named save, the relaunch + resume, resume_reads (+5 s),
    resume_craft_click, resume_reads (+30 s), resume_base_click, END, no_crash."""
    host, client = x["host"], x["client"]
    for gc in (host, client):
        gc.spawn(); gc.connect(timeout=240)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    try:
        session.new_campaign(host, client, port=KEY_BRINGUP)
    except Exception as e:  # noqa: BLE001
        capture(f"bring-up: {type(e).__name__}: {str(e)[:300]}", host, client)
    geo.slow_clock(host, client)
    hb, cb = own_base(gs(host)), own_base(gs(client))
    if not hb or not cb:
        capture(f"own bases: host {hb}, client {cb}", host, client)
    x.update(HB=hb["coopBaseId"], CB=cb["coopBaseId"], X=(cb["lon"], cb["lat"]))
    split, at = round(dist((hb["lon"], hb["lat"]), x["X"]), 4), abs(hb["lon"] - HOST_POS[0]) < 1e-6 and abs(hb["lat"] - HOST_POS[1]) < 1e-6
    step("before_save", "bring-up", HB=x["HB"], CB=x["CB"], host=[hb["lon"], hb["lat"]], X=x["X"], split=split,
         tops=[stack(host), stack(client)])
    if not at or split < SPLIT_MIN or [stack(host)[-1:], stack(client)[-1:]] != [["GeoscapeState"]] * 2:
        capture(f"split host base: host base at {[hb['lon'], hb['lat']]} (want {HOST_POS}), {split} rad from X (want >= {SPLIT_MIN})", host, client)
    sp = client.ok({"cmd": "spawn_craft", "type": "STR_INTERCEPTOR"})
    pt = (x["X"][0] + PATROL_OFF[0], x["X"][1] + PATROL_OFF[1])
    f = client.cmd({"cmd": "craft_force", "craft_id": sp["craft_id"], "status": "STR_OUT", "lon": pt[0], "lat": pt[1], "dest": "patrol"})
    x["pkey"] = f"STR_INTERCEPTOR-{sp['craft_id']}"
    s, w = wait(lambda: [k for k in read(host, x["CB"])["crafts"] if f"{k['type']}-{k['id']}" == x["pkey"] and k["status"] == "STR_OUT"
                         and dist((k["lon"], k["lat"]), pt) < 0.01], MIRROR_S)
    step("before_save", "patrol", spawn=sp, force=f, point=pt, mirrorS=w, mirror=bool(s))
    if not s:
        capture(f"P {x['pkey']}: the host mirror not STR_OUT within 0.01 rad of {pt} within {MIRROR_S} s (force {f})", host, client)
    run_row("before_save", row_before_save, x)
    st, ins = stack(host), inside(host)
    if ins or "BasescapeState" in st:
        capture(f"before the save: host stack {st}, insideCoopBase {ins}", host, client)
    n, s, fl = named_save(host, SAVE)
    step("before_save", "save", reply=n, s=s, world=(fl or {}).get("world"), blob=(fl or {}).get("blob"))
    if not fl or not fl.get("world") or not fl.get("blob"):
        capture(f"named save {SAVE}: reply {n}, on disk {bool(fl)}, file {fl}", host, client)
    client.shutdown(); host.shutdown()
    host = x["host"] = GameClient("host", None, host.user_dir)
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(TAG + "_client2"))
    host.spawn(); host.connect(timeout=240); c2.spawn(); c2.connect(timeout=240)
    try:
        session.resume_campaign(host, c2, SAVE, port=KEY_RESUME)
    except Exception as e:  # noqa: BLE001
        capture(f"resume: {type(e).__name__}: {str(e)[:300]}", host, c2)
    x["T"], x["Tb"] = time.time(), now()
    step("resume_reads", "resume", T=x["Tb"], tops=[stack(host), stack(c2)])
    geo.slow_clock(host, c2)
    step("resume_reads", "load", **load())
    run_row("resume_reads", row_resume_reads, x, "5s")
    run_row("resume_craft_click", row_resume_craft_click, x)
    if x.get("read5sOk"):
        run_row("resume_reads", row_resume_reads, x, "30s")
    run_row("resume_base_click", row_resume_base_click, x)
    h, c = read(host, x["CB"]), read(c2, x["HB"])
    step("END", "read", host=brief(h), client2=brief(c))
    new, alive = sorted(crash_set() - x["crash0"]), {g.name: g.proc.poll() is None for g in (host, c2)}
    cell("no_crash", not new and all(alive.values()),
         f"{len(new)} new crash file(s) {[os.path.basename(p) for p in new][:3]}, alive {alive} "
         f"(want 0, both alive)")
def main():
    x = {"host": GameClient("host", None, make_user_dir(TAG + "_host")), "client": GameClient("client", None, make_user_dir(TAG + "_client")),
         "client2": None, "crash0": crash_set()}
    EV["load0"], allc = load(), [c for r in ROWS.values() for c in r]
    try:
        boot(x)
    except BootMiss as e:
        block(allc, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] boot: {type(e).__name__}: {str(e)[:300]}", flush=True)
        block(allc, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
        EV["load1"] = load()
    for row, names in list(ROWS.items()) + [("END", [])]:
        print(f"EVIDENCE {row}: {json.dumps(EV['rows'][row], sort_keys=True, default=str)}", flush=True)
        if names:
            bad = [n for n, ok, _ in RESULTS if n in names and not ok]
            print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== test_client_base_mirror_dup: one mirror of the partner's base after a SEPARATE resume: "
          f"{len(RESULTS) - len(fails)}/{len(allc)} cells PASS, wall "
          f"{time.time() - T0:.1f} s, cpu {EV['load0']} -> {EV['load1']} ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)

if __name__ == "__main__":
    main()
