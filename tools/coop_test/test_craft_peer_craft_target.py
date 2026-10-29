"""test_craft_peer_craft_target.py: in SEPARATE co-op a craft sent after the PARTNER's craft (a mirror on its machine) keeps
that destination across a geoscape save and reload, as W2-H48 gave alien bases issue #28's treatment (R-H51-0, lead L-H48-1). Today every
save strips the partner's mirrors and the craft node keeps only the target's rule type and id, so after the reload the craft binds to
whatever the loaded world holds under them: itself (it hovers, "DESTINATION: INTERCEPTOR-2"), the player's own docked craft of that type
and id (it flies home and lands), or nothing (an interim waypoint: "has reached WAY POINT-n / Now patrolling").

Spec: docs rewrite/prompts/w2h51_craft_peer_craft_target.md (stage S-A, (d) and (f), FX51-1 .. FX51-13) and its ORCHESTRATOR RULINGS
(QH51-1 .. QH51-7 (a)); R-H51-0 / VL-H51-1, L-H48-1, issue #28, R-H48-0; F17740-F17753, F17800-F17819, F18000-F18019. TASK 0 pins:
docs rewrite/w2h51-task0/sa/CONSTANTS.md (Ka on HEAD + T1, Kg on + E1-E8, then restored).

Keys "49174" / "49175" (bring-up / resume lobby), dirs w2h51_s_*. ONE SEPARATE gm0 boot S. The host's targets patrol (craft_force); every
send goes through the REAL globe picker (open_select_destination, a real inject_input click at the target's projected pixel,
MultipleTargetsState, ConfirmDestinationState naming the target, OK): R5 (guard) the host's INTERCEPTOR-4 HINT4 -> its own SKYRANGER-1
HSKY first; R1 (c) the client's INTERCEPTOR-2 CINT2 -> the host's INTERCEPTOR-2 HINT2; R2 (b) the client's INTERCEPTOR-1 CINT1 -> the host's
SKYRANGER-1 HSKY while the client's own SKYRANGER-1 CSKY stays docked; R3 (a) the client's SKYRANGER-2 CSKY2 -> the host's INTERCEPTOR-3
HINT3; the C4 control (approach, then the targets fly away via craft_order); R4 (a, host) the host's INTERCEPTOR-1 HINT1 -> the client's
SKYRANGER-2 CSKY2. The host's quick save (SaveGameState) then the named save (PyYAML: host world + client blob); both end; the host
respawns on its dir, client2 on an EMPTY dir; session.resume_campaign; the relink phase (idx 0), the follow phase (idx 1); every popup
recorded then closed with dismiss_popup (a landing or a redirect is never confirmed). The relink cells read geo_state destCraft (T1,
TEST-ONLY): displayStatus reads the same text red and green for R1 / R2. R6 reads both save files and the bases' co-op ids. A bring-up,
staging, send, save or resume miss prints ONE "CAPTURE S:" line and FAILs every remaining cell "boot".
RED (R1 = HEAD + T1; TASK 0 Ka): exit 2, 9/20 - FAIL R1-relink, R1-follow, R2-relink, R2-follow, R3-relink, R3-status, R4-relink,
R4-status, R4-nopatrol, R6-client, R6-host. GREEN (G1 = E1-E8; TASK 0 Kg): 20/20.
ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_craft_peer_craft_target.py
"""

import base64
import glob
import json
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
import yaml  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h51-task0/sa/CONSTANTS.md) -----
K1, K2 = "49174", "49175"                                                # FX51-1: bring-up lobby / resume lobby
CFG = {"tag": "w2h51_s", "save": "w2h51_s.sav", "probe": "w2h51_probe.sav"}   # FX51-1 / FX51-5 / FX51-9
# name: (owner, rule type, id (None = the spawn_craft reply), patrol offset from the client base X (None = docked until its UI send))
LAYOUT = {"HSKY": ("host", "STR_SKYRANGER", 1, (-0.35, 0.12)), "HINT2": ("host", "STR_INTERCEPTOR", 2, (0.35, 0.12)),   # FX51-4
          "HINT3": ("host", "STR_INTERCEPTOR", None, (0.0, 0.42)), "HINT4": ("host", "STR_INTERCEPTOR", None, None),
          "HINT1": ("host", "STR_INTERCEPTOR", 1, None), "CINT2": ("client", "STR_INTERCEPTOR", 2, None),
          "CINT1": ("client", "STR_INTERCEPTOR", 1, None), "CSKY2": ("client", "STR_SKYRANGER", None, None),
          "CSKY": ("client", "STR_SKYRANGER", 1, None)}
FOL = {"R5": ("HINT4", "HSKY"), "R1": ("CINT2", "HINT2"), "R2": ("CINT1", "HSKY"), "R3": ("CSKY2", "HINT3"), "R4": ("HINT1", "CSKY2")}
AWAY = {"HINT2": (1.10, 0.30), "HSKY": (-1.10, 0.30), "HINT3": (0.90, 0.42)}   # FX51-7: the targets' away points (offsets from X)
MIRROR_S, SAVE_S, RELINK_S = 30, 90, 10                                  # FX51-12 (s)
APPROACH, AWAYW, R4FLY, FOLLOW = (82, 60), (15, 40), (4, 20), (75, 45)    # FX51-7 / -8 / -11 / -12: (game minutes, real cap s);
#   APPROACH 60 -> 82 game min by FX51-12's rule (2 x Ka's measured 41); FOLLOW 75 >= Ka's (b) landing (36) + 20 (CONSTANTS.md)
ESC, END, MOVE, NEAR, POLL = 0.02, 0.05, 0.10, 0.01, 0.25                # FX51-13 (rad), FX51-7 approach, FX51-11 poll (s)
ZOOM = [0.45, 0.60, 0.90, 1.40, 2.25, 3.60]                              # Globe::setupRadii, x the globe height (CAP)
CLICKS = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (2, 2), (-2, -2), (2, -2), (-2, 2), (3, 0), (-3, 0), (0, 3), (0, -3)]  # FX51-6
HOME = ("STR_REFUELLING", "STR_REARMING", "STR_REPAIRS", "STR_READY")
CK = ("type", "id", "name", "status", "destKind", "displayStatus", "lon", "lat", "fuel", "lowFuel", "coop", "destCraft")
ROWS = {"R1": ["R1-before", "R1-relink", "R1-follow"], "R2": ["R2-before", "R2-relink", "R2-follow"],
        "R3": ["R3-before", "R3-relink", "R3-status"], "R4": ["R4-before", "R4-relink", "R4-status", "R4-nopatrol"],
        "R5": ["R5-before", "R5-relink", "R5-file"], "R6": ["R6-client", "R6-host", "R6-ids"], "S-common": ["S-common"]}
FIX = {"R1-relink", "R1-follow", "R2-relink", "R2-follow", "R3-relink", "R3-status", "R4-relink", "R4-status", "R4-nopatrol",
       "R6-client", "R6-host"}
RESULTS, EV, IDS = [], {}, {}      # (cell, ok, detail); every value read (EVIDENCE); craft name -> id

class FixtureMiss(Exception): pass

def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)

def block(names, why):
    done = {x[0] for x in RESULTS}
    for n in names:
        if n not in done:
            cell(n, False, f"blocked: {why}")

def row_verdict(row, names):
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)

def load():
    """CPU % and the count of the owner's game processes (S24), recorded beside every wall."""
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor | Measure-Object -Property "
                            "LoadPercentage -Average).Average; @(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count"],
                           capture_output=True, text=True, timeout=60).stdout.split()
        return {"cpu": v[0] if v else None, "wardogs": v[1] if len(v) > 1 else None}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:120]}

# ----- probes and one-line helpers -----
def sub(d, ks): return {k: d.get(k) for k in ks}
def other(o): return "client" if o == "host" else "host"
def gs(gc): return gc.ok({"cmd": "geo_state"})
def stack(gc): return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
def texts(gc): return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]
def evs(gc): return sub(gc.cmd({"cmd": "event_state"}), ("desyncSeen",))
def coopv(gc): return sub(gc.cmd({"cmd": "get_coop"}), ("gamemode", "noBases", "localSeat"))
def crash_set(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def key(n): return f"{LAYOUT[n][1]}-{IDS[n]}"
def r4(v): return None if v is None else round(v, 4)
def dist(a, b):     # radians on (lon, lat); the longitude difference wraps at 2 pi (HSKY's away leg crosses lon 0)
    return round(math.hypot((a["lon"] - b["lon"] + math.pi) % (2 * math.pi) - math.pi, a["lat"] - b["lat"]), 4) if a and b else 9.0
def dcs(c): return (c or {}).get("destCraft") and [c["destCraft"].get(k) for k in ("type", "id", "coop", "self", "coopBaseId", "coopIcon")]
def brief(c): return c and [c.get("displayStatus"), c.get("status"), dcs(c), r4(c.get("lon")), r4(c.get("lat")), c.get("fuel")]
def want(t, b, coop=True): return {"type": LAYOUT[t][1], "id": IDS[t], "coop": coop, "self": False, "coopBaseId": b}
def dc_ok(c, w): return all(((c or {}).get("destCraft") or {}).get(k, "absent") == v for k, v in w.items())
def gmin(g): t = g.get("time") or {}; return ((t.get("month", 0) * 31 + t.get("day", 0)) * 24 + t.get("hour", 0)) * 60 + t.get("minute", 0)

def own(g, icon=False):    # the machine's own real base, or (icon=True) the peer's coop-icon base, in a geo_state
    return next((b for b in g.get("bases", []) if bool(b.get("coopIcon")) == icon and (icon or not b.get("coopBase"))), None)

def snap(m):
    """Every craft of every base per machine (own: / mir: + type-id, with T1's destCraft), the coop-icon bases' ids, the game minute."""
    out = {}
    for on, gc in m.items():
        g = gs(gc)
        cr = {("mir:" if c.get("coop") else "own:") + f"{c.get('type')}-{c.get('id')}": dict(sub(c, CK), base=b.get("name"))
              for b in g.get("bases", []) for c in b.get("crafts", [])}
        ib = [b for b in g.get("bases", []) if b.get("coopIcon")]
        out[on] = {"crafts": cr, "icons": [b.get("coopBaseId") for b in ib], "gmin": gmin(g),
                   "iconBases": [[b.get("coopBaseId"), b.get("name"), b.get("coopBase"), len(b.get("crafts", []))] for b in ib]}
    return out

def view(s, n, on):
    """Craft n as machine `on` sees it: its own copy on its owner, the mirror on the other machine."""
    return ((s.get(on) or {}).get("crafts") or {}).get(("own:" if on == LAYOUT[n][0] else "mir:") + key(n))

def wait(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 2)
        time.sleep(interval)

def capture(err, *machines):
    """ONE CAPTURE line (stack, get_coop, event_state, every geo_state craft with destCraft, the log tail per machine); boot FAIL."""
    cap = {}
    for gc in (g for g in machines if g is not None and g.proc is not None and g.proc.poll() is None):
        try:
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "get_coop": gc.cmd({"cmd": "get_coop"}), "event_state": evs(gc),
                            "crafts": [dict(sub(c, CK), base=b.get("name")) for b in gs(gc).get("bases", []) for c in b.get("crafts", [])],
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE S: {json.dumps({'missed': err, 'machines': cap}, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)

# ----- saves (H48T) and the globe picker (CAP) -----
def read_save(path):
    """The host world and the client blob (coopClientSaves) of a save: craft nodes (all keys but cargo), bases' coopbaseid, waypoints,
    the globe view."""
    def world(d):
        return {"crafts": [dict({k: v for k, v in c.items() if k not in ("items", "weapons", "vehicles", "soldiers")}, base=b.get("name"))
                           for b in (d or {}).get("bases") or [] for c in b.get("crafts") or []],
                "bases": [{"name": b.get("name"), "coopbaseid": b.get("coopbaseid", "absent")} for b in (d or {}).get("bases") or []],
                "waypoints": (d or {}).get("waypoints"), "globe": {k: (d or {}).get(k) for k in ("globeLon", "globeLat", "globeZoom")}}
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

def save(host, client, name, ev, tag):
    """FX51-9: the host's quick save through SaveGameState, 2 s, drain, then the named save_game; both read with PyYAML."""
    qpath, spath = (os.path.join(host.user_dir, "xcom1", f) for f in ("_quick_.asav", name))
    t0 = time.time()
    q = host.cmd({"cmd": "save_game_ui", "type": "quick"})
    okq, sq = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, SAVE_S, 0.2)
    time.sleep(2.0)
    geo.drain_popups(host)
    n = host.cmd({"cmd": "save_game", "file": name})
    okn, sn = wait(lambda: os.path.exists(spath) and os.path.getsize(spath) > 0, SAVE_S, 0.2)
    time.sleep(1.0)
    if not okq or not okn:
        capture(f"FX51-9 {tag}: quick {q} on disk {okq}, named {n} on disk {okn}", host, client)
    files = {"quick": read_save(qpath), "named": read_save(spath)}
    ev[tag] = {"quickS": sq, "namedS": sn, "files": files}
    if any("blob" not in f or "world" not in f for f in files.values()):
        capture(f"FX51-9 {tag}: a save without its host world or the client blob (coopClientSaves)", host, client)
    return files

def relaunch(x, ev):
    """FX51-10: both end; the host respawns on its dir, client2 on an EMPTY dir; session.resume_campaign."""
    t0 = time.time()
    x["client"].shutdown(); x["host"].shutdown()
    host = x["host"] = GameClient("host", None, x["host"].user_dir)
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(CFG["tag"] + "_client2"))
    host.spawn(); host.connect(timeout=240); c2.spawn(); c2.connect(timeout=240)
    try:
        session.resume_campaign(host, c2, CFG["save"], port=K2)
    except Exception as e:  # noqa: BLE001
        capture(f"FX51-10 resume: {type(e).__name__}: {str(e)[:300]}", host, c2)
    ev["resumeS"] = round(time.time() - t0, 2)
    return host, c2

def project(G, lon, lat, geom):
    """Globe::polarToCart + pointBack on the base-coordinate globe surface at (0, 0) (CAP)."""
    cl, ct = G["globeLon"], G["globeLat"]
    R = ZOOM[int(G["globeZoom"])] * geom["H"]
    c = math.cos(ct) * math.cos(lat) * math.cos(lon - cl) + math.sin(ct) * math.sin(lat)
    x = geom["W"] // 2 + math.floor(R * math.cos(lat) * math.sin(lon - cl))
    y = geom["H"] // 2 + math.floor(R * (math.cos(ct) * math.sin(lat) - math.sin(ct) * math.cos(lat) * math.cos(lon - cl)))
    return x, y, c >= 0.0

def geometry(gc):
    """The geoscape's screen size from its INTERCEPT button (x = screenWidth-63, y = screenHeight/2-100); 320 x 200 when absent."""
    b = next((x for x in gc.ok({"cmd": "list_widgets"}).get("widgets", [])
              if str(x.get("text") or "").upper().startswith("INTERCEPT")), None)
    sw, sh = (b["x"] + 63, 2 * (b["y"] + 100)) if b else (320, 200)
    return {"screenW": sw, "screenH": sh, "W": sw - 64, "H": sh, "fallback": not b}

def ui_send(m, on, row, sender, target, pk, ev):
    """FX51-6: the real picker on machine `on`: open_select_destination, a real click at the target's pixel, MTS -> CDS naming it, OK."""
    gc = m[on]
    geo.drain_popups(gc)
    s0 = snap({on: gc})
    me, tg = view(s0, sender, on), view(s0, target, on)
    r = ev.setdefault("sends", {})[row] = {"machine": gc.name, "sender": key(sender), "target": key(target), "senderBefore": brief(me),
                                           "target0": brief(tg)}
    if not me or not tg:
        capture(f"FX51-6 {row}: sender {key(sender)} {me} or target {key(target)} {tg} missing on {gc.name}", *m.values())
    r["open"] = gc.cmd({"cmd": "open_select_destination", "craft_id": IDS[sender], "craft_type": LAYOUT[sender][1]})
    x, y, front = project(pk["G"][on], tg["lon"], tg["lat"], pk["geom"][on])
    r["pixel"], tries, name, sc = [x, y, front], [], (tg.get("name") or "?").upper(), pk["scale"]
    if not r["open"].get("ok") or not front:
        capture(f"FX51-5 / FX51-6 {row}: open {r['open']}, pixel {r['pixel']}", *m.values())
    for dx, dy in CLICKS:
        wx, wy = int((x + dx) * sc["x"] + 1), int((y + dy) * sc["y"] + 1)
        gc.ok({"cmd": "inject_input", "kind": "click", "x": wx, "y": wy})
        time.sleep(0.5)
        st = stack(gc)
        t = {"base": [x + dx, y + dy], "top": st[-1] if st else None, "texts": texts(gc)}
        if t["top"] == "MultipleTargetsState":
            caps = t["mts"] = [c for c in t["texts"] if name in str(c).upper()]
            if len(caps) == 1:
                gc.cmd({"cmd": "click_widget", "match": caps[0]})
                time.sleep(0.4)
                st = stack(gc)
                t["top"], t["texts"] = (st[-1] if st else None), texts(gc)
            else:
                gc.cmd({"cmd": "click_widget", "match": "CANCEL"})
                time.sleep(0.3)
        tries.append(t)
        if t["top"] == "ConfirmDestinationState":
            if any(name in str(c).upper() for c in t["texts"]):
                r["ok"] = gc.cmd({"cmd": "click_widget", "match": "OK"})
                time.sleep(0.5)
                r.update(tries=tries, stackAfter=stack(gc), senderAfter=brief(view(snap({on: gc}), sender, on)))
                print(f"SEND {row}: {json.dumps(r, sort_keys=True, default=str)}", flush=True)
                return r
            gc.cmd({"cmd": "click_widget", "match": "CANCEL"})
            time.sleep(0.3)
        if stack(gc)[-1:] != ["SelectDestinationState"]:
            break
    if stack(gc)[-1:] == ["SelectDestinationState"]:
        gc.cmd({"cmd": "click_widget", "match": "CANCEL"})
    r.update(tries=tries)
    capture(f"FX51-6 {row}: no click named {name}: {json.dumps(tries, default=str)[:1500]}", *m.values())

def popups(gc, phase, t0):
    """Every popup on gc: recorded (stack, list_widgets texts), then dismiss_popup (never a landing / redirect confirm)."""
    out = []
    for _ in range(8):
        st = stack(gc)
        if not st or st[-1] == "GeoscapeState":
            break
        r = {"t": round(time.time() - t0, 2), "phase": phase, "machine": gc.name, "top": st[-1], "stack": st, "texts": texts(gc)}
        d = gc.cmd({"cmd": "dismiss_popup"})
        r["dismiss"] = d.get("handled") or d.get("error")
        out.append(r)
        print(f"POPUP {json.dumps(r, sort_keys=True, default=str)}", flush=True)
        if d.get("wait") or not d.get("ok"):
            break
    return out

def pline(label, p):
    parts = []
    for n, t in FOL.values():
        on = LAYOUT[n][0]
        c = view(p["s"], n, on)
        parts.append(f"{n}:{brief(c)} d={dist(c, view(p['s'], t, on))} peer={(view(p['s'], n, other(on)) or {}).get('displayStatus')!r}")
    print(f"POLL {label} t={p['t']} gmin={p['gmin']} " + " | ".join(parts), flush=True)

def window(m, label, idx, w, ev, until=None):
    """Both clocks at idx every poll; snapshots of both machines; popups recorded + dismissed; stop at w = (game min, s) or until()."""
    t1, polls, pops, g0 = time.time(), [], [], None
    while True:
        for gc in m.values():
            gc.cmd({"cmd": "geo_set_speed", "idx": idx})
        s = snap(m)
        g0 = s["host"]["gmin"] if g0 is None else g0
        p = {"t": round(time.time() - t1, 2), "gmin": s["host"]["gmin"] - g0, "s": s}
        polls.append(p)
        pline(label, p)
        for gc in m.values():
            pops += popups(gc, label, t1)
        if p["gmin"] >= w[0] or p["t"] >= w[1] or (until and until(p)):
            break
        time.sleep(POLL)
    for gc in m.values():
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})
    ev.setdefault("windows", {})[label] = {"polls": polls, "popups": pops, "s": round(time.time() - t1, 2)}
    return polls, pops

def node(files, part, base, n):
    return {k: next((c for c in (f.get(part) or {}).get("crafts", []) if c.get("base") == base and (c.get("type"), c.get("id")) ==
                     (LAYOUT[n][1], IDS[n])), None) for k, f in files.items()}

def node_bad(files, part, base, n, t, cid):
    """Both saves' node of n: dest {type, id} == t's and coopDestCraftBaseId == cid (None = the key must be absent)."""
    bad = []
    for k, c in node(files, part, base, n).items():
        d = (c or {}).get("dest") or {}
        if c is None or (d.get("type"), d.get("id")) != (LAYOUT[t][1], IDS[t]) or c.get("coopDestCraftBaseId", None) != cid:
            got = c and {"dest": d and sub(d, ("type", "id")), "coopDestCraftBaseId": c.get("coopDestCraftBaseId", "absent")}
            bad.append(f"{k} {n}: {got}")
    return bad

def boot(x, ev):
    """FX51-2 .. FX51-11: bring-up, staging, the sends, C4, the save, the resume, the relink and follow phases, and every cell."""
    m = {"host": x["host"], "client": x["client"]}
    for gc in m.values():
        gc.spawn(); gc.connect(timeout=240)
    try:
        session.new_campaign(m["host"], m["client"], port=K1)
    except Exception as e:  # noqa: BLE001
        capture(f"FX51-2 bring-up: {type(e).__name__}: {str(e)[:300]}", *m.values())
    geo.slow_clock(m["host"], m["client"])
    ev["mode"] = {n: coopv(gc) for n, gc in m.items()}
    g = {n: gs(gc) for n, gc in m.items()}
    bases = {n: own(g[n]) for n in m}
    HB, CB = [(bases[n] or {}).get("coopBaseId") for n in ("host", "client")]
    have = {n: sorted(f"{c['type']}-{c['id']}" for c in (bases[n] or {}).get("crafts", []) if not c.get("coop")) for n in m}
    ev["bases"] = {n: bases[n] and sub(bases[n], ("name", "lon", "lat", "coopBaseId")) for n in m}
    ev["bases"]["crafts0"] = have
    need = {"STR_SKYRANGER-1", "STR_INTERCEPTOR-1", "STR_INTERCEPTOR-2"}
    if any(ev["mode"][n].get("gamemode") != 0 or not need <= set(have[n]) for n in m) or not HB or not CB:
        capture(f"FX51-2 preconditions: modes {ev['mode']}, bases {ev['bases']}", *m.values())
    X = (bases["client"]["lon"], bases["client"]["lat"])
    try:                                                                       # FX51-3
        sp = {"CSKY2": m["client"].ok({"cmd": "spawn_craft", "type": "STR_SKYRANGER"}),
              "HINT3": m["host"].ok({"cmd": "spawn_craft", "type": "STR_INTERCEPTOR"}),
              "HINT4": m["host"].ok({"cmd": "spawn_craft", "type": "STR_INTERCEPTOR"})}
    except Exception as e:  # noqa: BLE001
        capture(f"FX51-3 spawn_craft: {e}", *m.values())
    IDS.update({n: (i if i is not None else sp[n]["craft_id"]) for n, (o, ty, i, off) in LAYOUT.items()})
    ev["ids"], ev["spawn"] = dict(IDS), sp
    geo.slow_clock(m["host"], m["client"])
    pts = {n: (X[0] + off[0], X[1] + off[1]) for n, (o, ty, i, off) in LAYOUT.items() if off}
    ev["force"] = {n: m["host"].cmd({"cmd": "craft_force", "craft_id": IDS[n], "status": "STR_OUT", "lon": p[0], "lat": p[1],
                                     "dest": "patrol"}) for n, p in pts.items()}
    pt = lambda n: {"lon": pts[n][0], "lat": pts[n][1]}  # noqa: E731

    def placed():      # FX51-4: the forced crafts on the host and their mirrors on the client, STR_OUT at their points
        s = snap(m)
        bad = [(n, on) for n in pts for on in m if (view(s, n, on) or {}).get("status") != "STR_OUT" or dist(view(s, n, on), pt(n)) > NEAR]
        bad += [(n, "host") for n in ("HINT1", "HINT4") if (view(s, n, "host") or {}).get("status") not in HOME]
        return s if not bad else None
    s, ev["mirrorS"] = wait(placed, MIRROR_S, 0.25)
    if not s:
        capture(f"FX51-4 the forced crafts / mirrors not in place within {MIRROR_S} s: force {ev['force']}", *m.values())
    files = save(m["host"], m["client"], CFG["probe"], ev, "probe")            # FX51-5: the picker geometry
    pk = {"G": {"host": files["named"]["world"]["globe"], "client": files["named"]["blob"]["globe"]},
          "geom": {n: geometry(gc) for n, gc in m.items()}}
    op = m["client"].cmd({"cmd": "open_select_destination", "craft_id": IDS["CINT1"], "craft_type": "STR_INTERCEPTOR"})
    cw = m["client"].cmd({"cmd": "click_widget", "match": "CANCEL"})
    time.sleep(0.3)
    if not op.get("ok") or not cw.get("baseX") or None in pk["G"]["host"].values() or None in pk["G"]["client"].values():
        capture(f"FX51-5 picker geometry: G {pk['G']}, open {op}, cancel {cw}", *m.values())
    pk["scale"] = {"x": cw["winX"] / cw["baseX"], "y": cw["winY"] / cw["baseY"]}
    ev["picker"] = pk
    for row in ("R5", "R1", "R2", "R3"):                                        # FX51-6: the host's own escort first
        ui_send(m, LAYOUT[FOL[row][0]][0], row, FOL[row][0], FOL[row][1], pk, ev)
    window(m, "C4-approach", 1, APPROACH, ev, until=lambda p: all(
        dist(view(p["s"], FOL[r][0], "client"), view(p["s"], FOL[r][1], "client")) < NEAR for r in ("R1", "R2")))
    ev["away"] = {n: m["host"].cmd({"cmd": "craft_order", "order": "target", "craft_id": IDS[n], "craft_type": LAYOUT[n][1],
                                    "lon": X[0] + d[0], "lat": X[1] + d[1]}) for n, d in AWAY.items()}
    if not all(v.get("ok") for v in ev["away"].values()):
        capture(f"FX51-7 away orders: {ev['away']}", *m.values())
    window(m, "C4-away", 1, AWAYW, ev)
    ui_send(m, "host", "R4", "HINT1", "CSKY2", pk, ev)                           # FX51-8
    window(m, "R4-fly", 1, R4FLY, ev)
    geo.slow_clock(m["host"], m["client"])
    b0 = ev["before"] = snap(m)
    reads = [("host@before", evs(m["host"])), ("client@before", evs(m["client"]))]
    cv = lambda n, s=b0: view(s, n, LAYOUT[n][0])  # noqa: E731
    ds3, ds4 = (cv("CSKY2") or {}).get("displayStatus"), (cv("HINT1") or {}).get("displayStatus")
    want3, want4 = [f"DESTINATION: {(view(b0, t, LAYOUT[n][0]) or {}).get('name')}" for n, t in (FOL["R3"], FOL["R4"])]
    ws = {"R1": want("HINT2", HB), "R2": want("HSKY", HB), "R3": want("HINT3", HB), "R4": want("CSKY2", CB),
          "R5": want("HSKY", HB, coop=False)}
    for row, (n, t) in FOL.items():
        c, tm = cv(n), view(b0, t, LAYOUT[n][0])
        extra, ok = "", dc_ok(c, ws[row]) and (row != "R1" or (c or {}).get("status") == "STR_OUT")
        if row in ("R1", "R2"):
            ok, extra = ok and dist(c, tm) <= ESC, f"; dist to the mirror {dist(c, tm)} (want <= {ESC})"
        if row == "R2":
            ok, extra = ok and (cv("CSKY") or {}).get("status") in HOME, extra + f"; CSKY {(cv('CSKY') or {}).get('status')} (want HOME)"
        if row in ("R3", "R4"):
            d0, wd = (ds3, want3) if row == "R3" else (ds4, want4)
            ok, extra = ok and d0 == wd, f"; DS{row[1]} {d0!r} (want {wd!r})"
        cell(f"{row}-before", ok, f"{LAYOUT[n][0]} {n} destCraft {dcs(c)} {(c or {}).get('status')} (want {ws[row]}"
             f"{' STR_OUT' if row == 'R1' else ''}){extra}")
    files = save(m["host"], m["client"], CFG["save"], ev, "save")
    hb, cb = ev["names"] = bases["host"]["name"], bases["client"]["name"]
    bad = node_bad(files, "world", hb, "HINT4", "HSKY", None)
    cell("R5-file", not bad, "; ".join(bad) or f"both saves' world HINT4: dest {key('HSKY')}, no coopDestCraftBaseId")
    bad = [b for n, t in (FOL["R1"], FOL["R2"], FOL["R3"]) for b in node_bad(files, "blob", cb, n, t, HB)]
    cell("R6-client", not bad, "; ".join(bad) + f" (want coopDestCraftBaseId {HB})" if bad else
         f"both saves' blob CINT2 / CINT1 / CSKY2: dest = the target, coopDestCraftBaseId {HB}")
    bad = node_bad(files, "world", hb, "HINT1", "CSKY2", CB)
    cell("R6-host", not bad, "; ".join(bad) + f" (want coopDestCraftBaseId {CB})" if bad else
         f"both saves' world HINT1: dest {key('CSKY2')}, coopDestCraftBaseId {CB}")
    ids_bad = []
    for k, f in files.items():
        for p, nm, want_id in (("world", hb, HB), ("blob", cb, CB)):
            b = next((b for b in (f.get(p) or {}).get("bases", []) if b["name"] == nm), None)
            ids_bad += [f"{k} {p} {nm} coopbaseid {b and b['coopbaseid']} (want {want_id})"] if not b or b["coopbaseid"] != want_id else []
    host, c2 = relaunch(x, ev)
    m = {"host": host, "client": c2}
    ev["modeAfter"] = {"host": coopv(host), "client2": coopv(c2)}
    first = {}
    checks = {f"{r}-relink": (lambda s, r=r: dc_ok(view(s, FOL[r][0], LAYOUT[FOL[r][0]][0]), ws[r])) for r in FOL}
    checks["ids"] = lambda s: HB in s["client"]["icons"] and CB in s["host"]["icons"]

    def until(p):
        first.update({n: p for n, fn in checks.items() if n not in first and fn(p["s"])})
        return len(first) == len(checks)
    rp, rpops = window(m, "relink", 0, (10 ** 6, RELINK_S), ev, until=until)
    reads += [("host@relink", evs(host)), ("client2@relink", evs(c2))]
    fp, fpops = window(m, "follow", 1, FOLLOW, ev)
    reads += [("host@follow", evs(host)), ("client2@follow", evs(c2))]
    p0, pe = rp[0], fp[-1]
    mach = {f"{r}-relink": LAYOUT[FOL[r][0]][0] for r in FOL}
    ev["first"] = {n: {"t": p["t"], "gmin": p["s"][mach.get(n, "host")]["gmin"] - p0["s"][mach.get(n, "host")]["gmin"]}
                   for n, p in first.items()}
    ev["clock"] = {"hostBefore": b0["host"]["gmin"], "hostResume": p0["s"]["host"]["gmin"], "clientBefore": b0["client"]["gmin"],
                   "client2Resume": p0["s"]["client"]["gmin"], "resumeS": ev.get("resumeS")}
    for row, (n, t) in FOL.items():
        on, cn = LAYOUT[n][0], f"{row}-relink"
        v = first.get(cn, rp[-1])
        cell(cn, cn in first, f"{'client2' if on == 'client' else 'host'} {n} destCraft {dcs(view(v['s'], n, on))} "
             f"{(view(v['s'], n, on) or {}).get('displayStatus')!r} at {v['t']} s (want {ws[row]} within {RELINK_S} s)")
    for row in ("R1", "R2"):
        n, t = FOL[row]
        a, e, et = view(p0["s"], n, "client"), view(pe["s"], n, "client"), view(pe["s"], t, "client")
        if row == "R1":
            ok, d = dist(a, e) >= MOVE and dist(e, et) <= END, f"moved {dist(a, e)} since the resume (want >= {MOVE})"
        else:
            homes = [(p["t"], view(p["s"], n, "client").get("status")) for p in rp + fp
                     if (view(p["s"], n, "client") or {}).get("status") in HOME]
            ok, d = not homes and dist(e, et) <= END, f"HOME at {homes[:3]} (want none)"
        cell(f"{row}-follow", ok, f"client2 {n} {brief(e)} at the end ({pe['gmin']} game min, {pe['t']} s): {d}; dist to the mirror "
             f"{dist(e, et)} (want <= {END})")
    for row, wd in (("R3", ds3), ("R4", ds4)):
        n, on = FOL[row][0], LAYOUT[FOL[row][0]][0]
        f = first.get(f"{row}-relink")
        a, e = (view(f["s"], n, on) or {}).get("displayStatus") if f else None, (view(pe["s"], n, on) or {}).get("displayStatus")
        cell(f"{row}-status", f is not None and a == wd and e == wd, f"{n} at the first relinked poll {a!r} "
             f"({'at ' + str(f['t']) + ' s' if f else 'never relinked'}), at the end {e!r} (want DS{row[1]} {wd!r} both)")
    nm = (cv("HINT1") or {}).get("name") or "?"
    pat = [(p["phase"], p["t"], p["texts"]) for p in rpops + fpops if p["machine"] == "host" and p["top"] == "CraftPatrolState"
           and nm.upper() in " ".join(p["texts"]).upper()]
    cell("R4-nopatrol", not pat, f"host CraftPatrolState naming {nm!r} in the relink / follow phases: {pat}")
    ids_bad += [] if "ids" in first else [f"live coop-icon bases: client2 {rp[-1]['s']['client']['icons']} (want {HB}), host "
                                          f"{rp[-1]['s']['host']['icons']} (want {CB})"]
    cell("R6-ids", not ids_bad, "; ".join(ids_bad) or f"both saves: world {hb} coopbaseid {HB}, blob {cb} {CB}; after the resume "
         f"client2 holds a coop-icon base {HB} and the host {CB} at {first['ids']['t']} s")
    new = sorted(crash_set() - x["crash0"])
    bad = [f"{k} desyncSeen {v.get('desyncSeen')!r}" for k, v in reads if v.get("desyncSeen") is not False]
    bad += [f"{len(new)} new crash file(s) (first {os.path.basename(new[0])})"] if new else []
    ev["common"] = {"reads": reads, "newCrash": new}
    cell("S-common", not bad, "; ".join(bad) or f"desyncSeen false at {len(reads)} reads ({', '.join(k for k, _ in reads)}); "
         f"0 new crash files")
    ev["HB"], ev["CB"] = HB, CB

def row_ev(row, ev):
    """A row's EVIDENCE: the send, the follower at each read on both machines (destCraft, ds, status, position, fuel), the save nodes,
    the relink latency (wall, game minutes on its machine), the popups naming it, the peer's view."""
    w, sv = ev.get("windows") or {}, (ev.get("save") or {}).get("files") or {}
    rp, fp = (w.get("relink") or {}).get("polls") or [], (w.get("follow") or {}).get("polls") or []
    if row in FOL:
        n, t = FOL[row]
        on = LAYOUT[n][0]
        part, bn = ("blob", (ev.get("names") or ["?", "?"])[1]) if on == "client" else ("world", (ev.get("names") or ["?", "?"])[0])
        f = (ev.get("first") or {}).get(f"{row}-relink")
        at = lambda p: p and {"t": p["t"], "gmin": p["gmin"], n: brief(view(p["s"], n, on)),  # noqa: E731
                              "peer": brief(view(p["s"], n, other(on))), "target": brief(view(p["s"], t, on)),
                              "dist": dist(view(p["s"], n, on), view(p["s"], t, on))}
        b0 = ev.get("before") or {}
        nm = str((view(b0, n, on) or {}).get("name") or "?").upper()
        pops = [sub(p, ("phase", "t", "machine", "top", "texts")) for wn in ("relink", "follow")
                for p in (w.get(wn) or {}).get("popups", []) if nm in " ".join(p.get("texts") or []).upper()]
        return {"ids": [key(n), key(t)], "send": sub((ev.get("sends") or {}).get(row) or {}, ("pixel", "senderAfter", "stackAfter")),
                "before": at({"t": 0, "gmin": 0, "s": b0}) if b0 else None, "nodes": node(sv, part, bn, n) if sv and IDS else None,
                "resume": at(rp[0]) if rp else None, "relinked": f and {"t": f["t"], "gmin": f["gmin"]}, "end": at(fp[-1]) if fp else None,
                "popups": pops}
    if row == "R6":
        return {"HB": ev.get("HB"), "CB": ev.get("CB"), "saveS": [(ev.get("save") or {}).get(k) for k in ("quickS", "namedS")],
                "files": {k: {"bytes": f.get("bytes"), **{p: {q: (f.get(p) or {}).get(q) for q in ("bases", "waypoints")}
                                                         for p in ("world", "blob")}} for k, f in sv.items()},
                "iconBases": {k: p and {"client": p["s"]["client"]["iconBases"], "host": p["s"]["host"]["iconBases"]}
                              for k, p in (("before", {"s": ev["before"]} if ev.get("before") else None), ("resume", rp and rp[0]),
                                           ("end", fp and fp[-1]))}}
    return dict(sub(ev, ("common", "mode", "modeAfter", "bases", "ids", "mirrorS", "picker", "away", "clock", "resumeS", "wall", "load0",
                         "load1", "error")), windows={k: {"s": v["s"], "polls": len(v["polls"]), "gmin": v["polls"][-1]["gmin"]}
                                                    for k, v in w.items()},
                popups=[sub(p, ("phase", "t", "machine", "top", "texts", "dismiss")) for wn in ("relink", "follow")
                        for p in (w.get(wn) or {}).get("popups", [])])

def run_boot():
    """Boot S: host and client, the rows, then every machine shut down; EVIDENCE and ROW lines per row."""
    tag = CFG["tag"]
    x = {"tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None, "crash0": crash_set()}
    ev = EV["S"] = {"load0": load()}
    t0, cells = time.time(), [c for r in ROWS.values() for c in r]
    try:
        boot(x, ev)
    except FixtureMiss as e:
        block(cells, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot S: {ev['error']}", flush=True)
        block(cells, f"error {ev['error']}")
    finally:
        ev["wall"] = round(time.time() - t0, 1)
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
        ev["load1"] = load()
        for row, names in ROWS.items():
            print(f"EVIDENCE {row}: {json.dumps(row_ev(row, ev), sort_keys=True, default=str)}", flush=True)
            row_verdict(row, names)
    return ev

def main():
    t0 = time.time()
    run_boot()
    allc = [c for r in ROWS.values() for c in r]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== W2-H51 craft -> the partner's craft across a save and reload: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s, cpu {EV['S'].get('load0')} -> {EV['S'].get('load1')} ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (FIX cell)' if n in FIX else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)

if __name__ == "__main__":
    main()
