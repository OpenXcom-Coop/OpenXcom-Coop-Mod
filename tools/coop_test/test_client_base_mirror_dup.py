"""test_client_base_mirror_dup.py: after a SEPARATE resume the host keeps ONE mirror of the partner's base (lead L-H51-1,
ruling R-H57-0). Today the host answers its own baseRequest with the partner's coopBase3 (checked: copy 1) before the partner's
once-per-connection coopBase arrives (unchecked: copy 2): two identical "ClientBase" mirrors with the same crafts, so a click on the
partner's base marker lists "ClientBase" twice and a click on a partner craft lists it twice (capture lh51-1-cap, F18280-F18292, 4/4).
Spec: docs rewrite/prompts/w2h57_client_base_mirror_dup.md (stage S-A, (d) and (f)), ORCHESTRATOR RULINGS QH57-1 .. QH57-4 (a); TASK 0
pins: docs rewrite/w2h57-task0/sa/CONSTANTS.md (boots a, b red on HEAD; c green on HEAD + E1-E2, then restored).
Keys "49189" / "49190" (bring-up / resume lobby), dirs w2h57_s_*. ONE SEPARATE boot S, the host base apart from the client base.
Rows: C0 (controls before the save) C0-count, C0-craft, C0-base; the host's named save, both end, the host respawns on its dir, client2
on an EMPTY dir, session.resume_campaign, T = its return; R1 R1-5s, R1-crafts (T + 5 s), R1-client, R1-30s (T + 30 s); R3 (a real click
on the patrolling partner craft, between the R1 reads) R3-click; R2 (a real click on the partner's base marker, LAST) R2-click, R2-back,
CRASH. Real presses only: inject_input clicks at the projected pixel, Esc on a list, click_widget GEOSCAPE in a peer base; no popup drain
inside a peer base, never leave_base / coop_dialog_back / dismiss_popup. RED (TASK 0 a, b): exit 2, FAIL R1-5s, R1-crafts,
R3-click, R1-30s, R2-click. GREEN: 11/11. ONE run, no skip; exit 0 only if all pass, else 2.
Run:  python tools/coop_test/test_client_base_mirror_dup.py
"""

import base64, glob, json, math, os, sys, time  # noqa: E401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
import yaml  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h57-task0/sa/CONSTANTS.md; every value kept, boots a / b / c) -----
K1 = "49189"
K2 = "49190"
TAG, SAVE, PROBE, PROBE2 = "w2h57_s", "w2h57_s.sav", "w2h57_probe.sav", "w2h57_probe2.sav"
HOST_POS, SPLIT_MIN, PATROL_OFF = (0.90, -0.60), 0.15, (0.30, 0.10)   # rad: host base, split, P's patrol point from X
MIRROR_S, CRAFT_S, SAVE_S, READ1_S, READ2_S, DWELL_S, VISIT_S = 30, 10, 30, 5, 30, 2.0, 60   # s
ESC = 27                                                                 # SDLK_ESCAPE = Options::keyCancel
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]                              # Globe::setupRadii, x the globe height (H51T)
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]
ROWS = {"C0": ["C0-count", "C0-craft", "C0-base"], "R1": ["R1-5s", "R1-crafts", "R1-client", "R1-30s"], "R3": ["R3-click"],
        "R2": ["R2-click", "R2-back", "CRASH"]}
RED = {"R1-5s", "R1-crafts", "R3-click", "R1-30s", "R2-click"}
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
    """CPU (Processor(_Total) % Processor Time, the last 2 s; harness.cpu_load, D307) and the owner's game processes."""
    c = harness.cpu_load()
    return {"cpu": harness.cpu_text(c["cpu"]), "wardogs": str(len(c["wardogs"]))}

# ----- probes (CAP icons_of / own_base, H51T stack / texts) -----
def gs(gc): return gc.ok({"cmd": "geo_state"})
def stack(gc): return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
def texts(gc): return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
def inside(gc): return gc.cmd({"cmd": "get_coop"}).get("insideCoopBase")
def crash_set(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def own_base(g): return next((b for b in g.get("bases", []) if not b.get("coopIcon") and not b.get("coopBase")), None)
def dist(a, b): return math.hypot((a[0] - b[0] + math.pi) % (2 * math.pi) - math.pi, a[1] - b[1])
def brief(r): return {"t": r["t"], "copies": r["copies"], "icons": r["icons"], "stack": r["stack"]}
def icons_of(g):
    """CAP: the coop-icon bases of a geo_state reply, in list order: [idx, id, name, lon hex, lat hex, crafts (type-id)]."""
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
    """geo.drain_popups only while gc stands on its own world (insideCoopBase false, no BasescapeState): trap F18291."""
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
    print(f"CAPTURE S: {json.dumps({'missed': err, 'machines': cap}, sort_keys=True, default=str)}", flush=True)
    raise BootMiss(err)

# ----- saves (H51T read_save / save) -----
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
    """H51T's save for the picker probe: the quick save through SaveGameState, 2 s, a drain on the own world, the named save."""
    qpath, t0 = os.path.join(host.user_dir, "xcom1", "_quick_.asav"), time.time()
    q = host.cmd({"cmd": "save_game_ui", "type": "quick"})
    okq, _ = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, SAVE_S, 0.2)
    time.sleep(2.0)
    drain(host)
    n, s, f = named_save(host, name)
    return {"quick": [q.get("ok"), okq], "named": [n.get("ok"), s], "file": f}

# ----- the globe picker and real clicks (CAP picker_geometry / globe_click / press_key_cancel / close_peer_base_visit) -----
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
    """A real left click (inject_input) at the projected pixel of (lon, lat), H51T's offsets until the top is not GeoscapeState;
    every state seen in 0.9 s per offset, a CoopState with coop_dialog_info."""
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
def row_c0(x):
    host, client, CB, HB, X = x["host"], x["client"], x["CB"], x["HB"], x["X"]
    step("C0", "load", **load())
    h, c = read(host, CB), read(client, HB)
    step("C0", "read", host=brief(h), client=brief(c), hostKeys=h["keys"], clientKeys=c["keys"])
    cell("C0-count", h["copies"] == 1 and c["copies"] == 1, f"copies(host, CB {CB}) {h['copies']}, copies(client, HB {HB}) {c['copies']} (want 1 / 1)")
    pk = picker_geometry(host, PROBE, "C0")
    pm = next((k for k in h["crafts"] if f"{k['type']}-{k['id']}" == x["pkey"]), None)
    if not pm:
        raise RowMiss(f"P {x['pkey']} mirror missing on the host")
    step("C0", "drain", **drain(host))
    r = click(host, pm["lon"], pm["lat"], pk, "C0", "c0_craft")
    e = esc(host, "C0", "c0_craft") if r["top"] != "GeoscapeState" else {"top": "GeoscapeState (never left)"}
    cell("C0-craft", r["top"] == "GeoscapeCraftState" and "MultipleTargetsState" not in r["seen"] and e["top"] == "GeoscapeState",
         f"click {x['pkey']} at {r['pixel']}: top {r['top']}, seen {r['seen']}, texts {r['texts'][:5]}; Esc -> {e['top']} "
         f"(want GeoscapeCraftState, no MultipleTargetsState, then GeoscapeState)")
    if e["top"] != "GeoscapeState":
        raise RowMiss(f"host top {e['top']} after the craft window")
    step("C0", "drain", **drain(host))
    r = click(host, X[0], X[1], pk, "C0", "c0_base")
    if r["top"] in ("CoopState", "BasescapeState"):
        v = leave(host, "C0", "c0_base")
    else:
        v = esc(host, "C0", "c0_base") if r["top"] != "GeoscapeState" else {"top": "GeoscapeState (never left)"}
    h = read(host, CB)
    step("C0", "read after", host=brief(h))
    ok = (50 in r["codes"] or "BasescapeState" in r["seen"]) and v.get("inside") and v.get("back") is True
    cell("C0-base", ok and (h["own"] or {}).get("coopBaseId") == HB and h["copies"] == 1,
         f"click X at {r['pixel']}: codes {r['codes']}, seen {r['seen']}, texts {r['texts'][:3]}; inside {v.get('inside')}, GEOSCAPE "
         f"{v.get('geoscape')}, back {v.get('back')}; own base {(h['own'] or {}).get('coopBaseId')}, copies {h['copies']} (want CoopState 50 / "
         f"BasescapeState, inside, back, own base {HB}, 1 copy)")
def row_r1(x, part):
    host, c2, CB, HB = x["host"], x["client2"], x["CB"], x["HB"]
    if part == "5s":
        time.sleep(max(0.0, x["T"] + READ1_S - time.time()))
        ck = sorted(f"{c['type']}-{c['id']}" for c in (own_base(gs(c2)) or {}).get("crafts", []))
        if not ck:
            raise RowMiss("client2 holds no own base craft")
        h, w = wait(lambda: (lambda s: s if all(k in s["keys"] for k in ck) else None)(read(host, CB)), CRAFT_S)
        h = h or read(host, CB)
        c = x["r1c"] = read(c2, HB)
        cnt = {k: h["keys"].count(k) for k in ck}
        step("R1", "read +5 s", tRel=round(time.time() - x["T"], 2), craftWait=w, client2Crafts=ck, host=brief(h), hostKeys=h["keys"],
             client2=brief(c))
        cell("R1-5s", h["copies"] == 1, f"copies(host, CB {CB}) {h['copies']} at T + {round(h['t'] - x['Tb'], 2)} s (want 1)")
        cell("R1-crafts", all(v == 1 for v in cnt.values()), f"client2's crafts in keys(host, CB): {cnt} (want each exactly once)")
        x["r1ok"] = True
        return
    time.sleep(max(0.0, x["T"] + READ2_S - time.time()))
    h, c = read(host, CB), read(c2, HB)
    step("R1", "read +30 s", tRel=round(time.time() - x["T"], 2), host=brief(h), hostKeys=h["keys"], client2=brief(c))
    c5 = x["r1c"]["copies"]
    cell("R1-client", c5 == 1 and c["copies"] == 1, f"copies(client2, HB {HB}) {c5} at +5 s, {c['copies']} at +30 s (want 1 / 1)")
    cell("R1-30s", h["copies"] == 1, f"copies(host, CB {CB}) {h['copies']} at T + {round(h['t'] - x['Tb'], 2)} s (want 1)")
def row_r3(x):
    host, CB = x["host"], x["CB"]
    step("R3", "load", **load())
    step("R3", "drain", **drain(host))
    pk = x["pk2"] = picker_geometry(host, PROBE2, "R3")
    pm = [k for k in read(host, CB)["crafts"] if f"{k['type']}-{k['id']}" == x["pkey"]]
    step("R3", "P mirror", tRel=round(time.time() - x["T"], 2), P=[[k["status"], k["lon"], k["lat"]] for k in pm])
    if not pm or pm[0]["status"] != "STR_OUT":
        raise RowMiss(f"P {x['pkey']} mirror on the host not STR_OUT: {pm}")
    r = click(host, pm[0]["lon"], pm[0]["lat"], pk, "R3", "r3_craft")
    e = esc(host, "R3", "r3_craft") if r["top"] != "GeoscapeState" else {"top": "GeoscapeState (never left)"}
    cell("R3-click", r["top"] == "GeoscapeCraftState" and "MultipleTargetsState" not in r["seen"],
         f"click {x['pkey']} at {r['pixel']}: top {r['top']}, seen {r['seen']}, texts {r['texts'][:5]}; Esc -> {e['top']} "
         f"(want GeoscapeCraftState, no MultipleTargetsState)")
def row_r2(x):
    host, c2, CB, HB, X = x["host"], x["client2"], x["CB"], x["HB"], x["X"]
    step("R2", "load", **load())
    st, ins = stack(host), inside(host)
    if st[-1:] != ["GeoscapeState"] or ins or not x.get("pk2"):
        raise RowMiss(f"host stack {st}, insideCoopBase {ins}, picker {bool(x.get('pk2'))} before the base click")
    step("R2", "drain", **drain(host))
    r = click(host, X[0], X[1], x["pk2"], "R2", "r2_base")
    if r["top"] in ("CoopState", "BasescapeState"):
        v = leave(host, "R2", "r2_base")
        back = v.get("back") is True
    else:
        v = esc(host, "R2", "r2_base") if r["top"] != "GeoscapeState" else {"top": "GeoscapeState (never left)"}
        back = v["top"] == "GeoscapeState"
    cell("R2-click", (50 in r["codes"] or "BasescapeState" in r["seen"]) and v.get("inside") is True and "MultipleTargetsState" not in r["seen"],
         f"click X at {r['pixel']}: top {r['top']}, codes {r['codes']}, seen {r['seen']}, texts {r['texts'][:4]}; inside {v.get('inside')} "
         f"(want CoopState 50 / BasescapeState, inside the partner's base, no MultipleTargetsState)")
    h = read(host, CB)
    cell("R2-back", back and (h["own"] or {}).get("coopBaseId") == HB, f"back {v.get('back', v.get('top'))}, host stack {h['stack']}, own base "
         f"{(h['own'] or {}).get('coopBaseId')} (want back on its own geoscape, own base {HB})")
def run_row(row, fn, *a):
    try:
        fn(*a)
    except RowMiss as e:
        step(row, "precondition miss", why=str(e))
        block(ROWS[row], f"not reached ({str(e)[:300]})")
def boot(x):
    """Bring-up (split host base), P, C0, the named save, the relaunch + resume, R1 (+5 s), R3, R1 (+30 s), R2, END, CRASH."""
    host, client = x["host"], x["client"]
    for gc in (host, client):
        gc.spawn(); gc.connect(timeout=240)
    session.HOST_LON, session.HOST_LAT = HOST_POS
    try:
        session.new_campaign(host, client, port=K1)
    except Exception as e:  # noqa: BLE001
        capture(f"bring-up: {type(e).__name__}: {str(e)[:300]}", host, client)
    geo.slow_clock(host, client)
    hb, cb = own_base(gs(host)), own_base(gs(client))
    if not hb or not cb:
        capture(f"own bases: host {hb}, client {cb}", host, client)
    x.update(HB=hb["coopBaseId"], CB=cb["coopBaseId"], X=(cb["lon"], cb["lat"]))
    split, at = round(dist((hb["lon"], hb["lat"]), x["X"]), 4), abs(hb["lon"] - HOST_POS[0]) < 1e-6 and abs(hb["lat"] - HOST_POS[1]) < 1e-6
    step("C0", "bring-up", HB=x["HB"], CB=x["CB"], host=[hb["lon"], hb["lat"]], X=x["X"], split=split, tops=[stack(host), stack(client)])
    if not at or split < SPLIT_MIN or [stack(host)[-1:], stack(client)[-1:]] != [["GeoscapeState"]] * 2:
        capture(f"split host base: host base at {[hb['lon'], hb['lat']]} (want {HOST_POS}), {split} rad from X (want >= {SPLIT_MIN})", host, client)
    sp = client.ok({"cmd": "spawn_craft", "type": "STR_INTERCEPTOR"})
    pt = (x["X"][0] + PATROL_OFF[0], x["X"][1] + PATROL_OFF[1])
    f = client.cmd({"cmd": "craft_force", "craft_id": sp["craft_id"], "status": "STR_OUT", "lon": pt[0], "lat": pt[1], "dest": "patrol"})
    x["pkey"] = f"STR_INTERCEPTOR-{sp['craft_id']}"
    s, w = wait(lambda: [k for k in read(host, x["CB"])["crafts"] if f"{k['type']}-{k['id']}" == x["pkey"] and k["status"] == "STR_OUT"
                         and dist((k["lon"], k["lat"]), pt) < 0.01], MIRROR_S)
    step("C0", "patrol", spawn=sp, force=f, point=pt, mirrorS=w, mirror=bool(s))
    if not s:
        capture(f"P {x['pkey']}: the host mirror not STR_OUT within 0.01 rad of {pt} within {MIRROR_S} s (force {f})", host, client)
    run_row("C0", row_c0, x)
    st, ins = stack(host), inside(host)
    if ins or "BasescapeState" in st:
        capture(f"before the save: host stack {st}, insideCoopBase {ins}", host, client)
    n, s, fl = named_save(host, SAVE)
    step("C0", "save", reply=n, s=s, world=(fl or {}).get("world"), blob=(fl or {}).get("blob"))
    if not fl or not fl.get("world") or not fl.get("blob"):
        capture(f"named save {SAVE}: reply {n}, on disk {bool(fl)}, file {fl}", host, client)
    client.shutdown(); host.shutdown()
    host = x["host"] = GameClient("host", None, host.user_dir)
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(TAG + "_client2"))
    host.spawn(); host.connect(timeout=240); c2.spawn(); c2.connect(timeout=240)
    try:
        session.resume_campaign(host, c2, SAVE, port=K2)
    except Exception as e:  # noqa: BLE001
        capture(f"resume: {type(e).__name__}: {str(e)[:300]}", host, c2)
    x["T"], x["Tb"] = time.time(), now()
    step("R1", "resume", T=x["Tb"], tops=[stack(host), stack(c2)])
    geo.slow_clock(host, c2)
    step("R1", "load", **load())
    run_row("R1", row_r1, x, "5s")
    run_row("R3", row_r3, x)
    if x.get("r1ok"):
        run_row("R1", row_r1, x, "30s")
    run_row("R2", row_r2, x)
    h, c = read(host, x["CB"]), read(c2, x["HB"])
    step("END", "read", host=brief(h), client2=brief(c))
    new, alive = sorted(crash_set() - x["crash0"]), {g.name: g.proc.poll() is None for g in (host, c2)}
    cell("CRASH", not new and all(alive.values()), f"{len(new)} new crash file(s) {[os.path.basename(p) for p in new][:3]}, alive {alive} "
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
        print(f"[ERROR] boot S: {type(e).__name__}: {str(e)[:300]}", flush=True)
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
    print(f"\n==== W2-H57 one mirror of the partner's base after a SEPARATE resume: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, wall "
          f"{time.time() - T0:.1f} s, cpu {EV['load0']} -> {EV['load1']} ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)

if __name__ == "__main__":
    main()
