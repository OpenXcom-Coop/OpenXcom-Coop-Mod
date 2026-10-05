"""W2-H16e (F6176; D226 a; Q1 a .. Q5 a; vetoes V1-V3): the mind-shield switch on the base view, the craft-weapon switch on the
craft screen and the host's remembered dogfight weapon switch reach the shared world. Spec docs rewrite/prompts/
w2h16e_item_toggles.md (e)-(f); TASK 0 rewrite/w2h16e-task0/CONSTANTS.md; rulings R-H16e-T0-1..5. Levers (test-only):
toggle_probe, set_toggle_state (staging, THIS machine), open_craft_info. Real input: right-click on the BaseView cell centre,
left-click on the CraftInfoState weapon icon (after its icons are not hidden, F6581). Boot A (SHARED, the host's
oxceRememberDisabledCraftWeapons on): H16e-1..H16e-8 (H16e-8 the dogfight, last); Boot B (SEPARATE): H16e-9 (guard row).
S0 (every row): every switch enabled except the row's start values, client first (S25); both probes equal; R0 = requests.
RED (commit 1): H16e-1..6 and H16e-8 fail on their named cell; H16e-7 and H16e-9 pass. GREEN: all pass. "G:" cells are
guards (CAPTURE on a miss). EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2."""

import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Toggle_Test")
OPT = "oxceRememberDisabledCraftWeapons"
BOOT_A = ("w2h16ea", (49335, 49336, 47314))      # SHARED; lobby 47314 (F6422)
BOOT_B = ("w2h16eb", (49337, 49338, 47316))      # SEPARATE; lobby 47316
FAC, INT, AV = "STR_H16E_MIND_SHIELD", "STR_INTERCEPTOR", "STR_AVENGER"
CELLS = {"A": (0, 3), "B": (4, 2)}               # beside the radar and the living quarters (TASK 0 (i): indices 9 / 10)
WEAPONS = {"I1.0": (INT, 1, 0), "I1.1": (INT, 1, 1), "I2.0": (INT, 2, 0), "I2.1": (INT, 2, 1)}
SCALE, BAND, GRID = 2, 0, 32                     # window = int(base * 2 + 0) (F5802, F6587); BaseView::GRID_SIZE
POLL_S, POLL_I, UI_S = 3.0, 0.25, 3.0
GEO, BASE, INFO = "GeoscapeState", "BasescapeState", "CraftInfoState"

class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""
def short(e, n=500): return (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E704
def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not (last := pred()) and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(last), last
def pick(d, *keys): return {k: d.get(k) for k in keys}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def rs(gc): return pick(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending", "gaveUp")  # noqa: E704
def ss(gc): return pick(gc.cmd({"cmd": "shared_stats"}), "cmd", "okCount", "failCount", "applyCount", "applyQueued")  # noqa: E704
def tp(gc): return gc.ok({"cmd": "toggle_probe"})["bases"]  # noqa: E704
def strip(t): return str(t or "").replace("class OpenXcom::", "")  # noqa: E704
def wkey(key, x): return (AV, x.av, 0) if key == "AV.0" else WEAPONS[key]  # noqa: E704
def other(x, gc): return x.client if gc is x.host else x.host  # noqa: E704
def win(bx, by): return [int(bx * SCALE + BAND), int(by * SCALE + BAND)]  # noqa: E704
def closeall(x): return {gc.name: pick(gc.cmd({"cmd": "close_screens"}), "ok", "popped") for gc in (x.host, x.client)}  # noqa: E704
def fidx(bases, key):
    return next((i for i, f in enumerate(bases[0]["facilities"]) if f["type"] == FAC and (f["x"], f["y"]) == CELLS[key]), None)
def craft(bases, ctype, cid, bi=None):
    return next((c for b in (bases if bi is None else bases[bi:bi + 1]) for c in b["crafts"] if (c["type"], c["id"]) == (ctype, cid)), {})
def flag(bases, key, x=None, bi=0):
    """The switch `key` on one machine: a mind-shield cell (A / B) of base `bi`, or a weapon slot (I1.0 .. I2.1, AV.0)."""
    if key in CELLS:
        f = [f for f in bases[bi]["facilities"] if (f["x"], f["y"]) == CELLS[key]]
        return f[0]["disabled"] if f else None
    ctype, cid, slot = wkey(key, x)
    w = craft(bases, ctype, cid, bi if key in WEAPONS else None).get("weapons") or []
    return w[slot]["disabled"] if slot < len(w) else None
def proj(bases):
    """Compact toggle_probe of every base: detection, the mind shields, every craft [status, [[disabled, ammo, rearming]]]."""
    return [{"base": b["name"], "dc": b["detectionChance"],
             "mind": {f"{f['x']},{f['y']}": [f["disabled"], f["buildTime"]] for f in b["facilities"] if f["mind"]},
             "crafts": {f"{c['type'][4:]}-{c['id']}": [c["status"], [[w["disabled"], w["ammo"], w["rearming"]] for w in c["weapons"]]]
                        for c in b["crafts"]}} for b in bases]
def eqp(bases):
    """The S0 equality: facilities and craft switches / status (ammo / rearming are host-sim only, F6414)."""
    return [[b["name"], b["detectionChance"], [[f["x"], f["y"], f["type"], f["buildTime"], f["disabled"]] for f in b["facilities"]],
             [[c["id"], c["type"], c["status"], [[w["slot"], w["type"], w["disabled"]] for w in c["weapons"]]] for c in b["crafts"]]]
            for b in bases]
def widgets(gc):
    w = gc.cmd({"cmd": "list_widgets"})
    return strip(w.get("state")), [dict(pick(e, "x", "y", "w", "h", "hidden", "text"), type=strip(e.get("type")))
                                   for e in w.get("widgets", [])]
class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed = rid, time.time(), {}, [], []
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok
def capture(x):
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"toggle_probe": proj(tp(gc)), "stack": stack(gc), "widgets": widgets(gc),
                            "dogfight_state": gc.cmd({"cmd": "dogfight_state"}), "shared_stats": ss(gc), "resync": rs(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    return cap
def guard(r, x, name, ok, detail):
    """A miss: CAPTURE both machines' toggle_probe, stack, list_widgets, dogfight_state and shared_stats (STOP-IF 3)."""
    if r.cell("G:" + name, ok, detail):
        return
    print(f"CAPTURE {r.rid} (guard {name}): {json.dumps(capture(x), sort_keys=True, default=str)}", flush=True)
    raise GuardMiss(f"guard {name}")
def stage(gc, key, disabled, x):
    if key in CELLS:
        return gc.cmd({"cmd": "set_toggle_state", "kind": "facility", "x": CELLS[key][0], "y": CELLS[key][1], "disabled": disabled})
    ctype, cid, slot = wkey(key, x)
    return gc.cmd({"cmd": "set_toggle_state", "kind": "weapon", "craftId": cid, "craftType": ctype, "slot": slot, "disabled": disabled})
def s0(r, x, over):
    """Row frame S0: tops on the geoscape; every switch enabled except `over`, client then host; probes equal; R0."""
    h, c = x.host, x.client
    guard(r, x, "start", wait_until(lambda: top(h) == GEO and top(c) == GEO, 10.0, 0.2)[0], f"stacks {stack(h)} / {stack(c)}")
    want = dict({k: False for k in list(CELLS) + list(WEAPONS) + (["AV.0"] if x.av else [])}, **over)
    st = {f"{gc.name} {k}": stage(gc, k, v, x) for gc in (c, h) for k, v in want.items()}
    guard(r, x, "staging", all(v.get("ok") is True and v.get("disabled") == want[k.split()[1]] for k, v in st.items()), f"{st}")
    ok = wait_until(lambda: eqp(tp(h)) == eqp(tp(c)), UI_S, 0.25)[0]
    d = r.ev["S0"] = {"R0": {gc.name: rs(gc)["requests"] for gc in (h, c)}, "ss": {gc.name: ss(gc) for gc in (h, c)},
                      "probe": {gc.name: proj(tp(gc)) for gc in (h, c)}, "staged": over}
    guard(r, x, "S0 equal", ok, f"host {eqp(tp(h))} / client {eqp(tp(c))}")
    return d
def poll(x, keys, extra=None):
    """Both machines' toggle_probe every 0.25 s for 3 s: the row's switches (+ `extra`); only the changes are kept."""
    out, n, t0 = [], 0, time.time()
    while time.time() - t0 < POLL_S:
        s = {}
        for gc in (x.host, x.client):
            b = tp(gc)
            s.update({f"{gc.name[0]}.{k}": flag(b, k, x) for k in keys})
            s.update({f"{gc.name[0]}.{k}": v for k, v in (extra(b) if extra else {}).items()})
        if not out or {k: v for k, v in out[-1].items() if k != "t"} != s:
            out.append(dict(s, t=round(time.time() - t0, 2)))
        n += 1
        time.sleep(POLL_I)
    return {"samples": n, "changes": out}
def end(r, x):
    e = {gc.name: tp(gc) for gc in (x.host, x.client)}
    r.ev["end"] = {n: proj(b) for n, b in e.items()}
    return e
def close(r, x, d):
    r.ev["close"] = closeall(x)
    now = r.ev["requests"] = {gc.name: rs(gc)["requests"] for gc in (x.host, x.client)}
    r.cell("requests", now == d["R0"], f"requests {now} vs R0 {d['R0']} (STOP-IF 5)")
def rclick(r, x, gc, key):
    """open_screen basescape; the BaseView shown (TASK 0: (0, 8, 192, 192)); right-click the cell centre of `key`."""
    o = gc.cmd({"cmd": "open_screen", "screen": "basescape"})
    def bv():
        st, ws = widgets(gc)
        v = [w for w in ws if w["type"] == "BaseView"]
        return v[0] if st == BASE and v and v[0]["hidden"] is False else None
    ok, v = wait_until(bv, UI_S, 0.05)
    guard(r, x, f"{gc.name} base view", o.get("ok") is True and ok, f"open {o}; stack {stack(gc)}")
    b = [v["x"] + GRID * CELLS[key][0] + GRID / 2.0, v["y"] + GRID * CELLS[key][1] + GRID / 2.0]
    rep = gc.cmd({"cmd": "inject_input", "kind": "click", "button": "right", "x": win(*b)[0], "y": win(*b)[1]})
    r.ev[f"rclick {gc.name} {key}"] = {"baseView": [v["x"], v["y"], v["w"], v["h"]], "base": b, "win": win(*b), "ok": rep.get("ok")}
def open_info(r, x, gc, ctype, cid):
    """open_craft_info; the screen on top and its 15x17 weapon icons not hidden (F6581); returns the icons by x."""
    o = gc.cmd({"cmd": "open_craft_info", "craftId": cid, "craftType": ctype})
    def shown():
        st, ws = widgets(gc)
        ic = sorted([w for w in ws if w["type"] == "InteractiveSurface" and w["w"] == 15 and w["h"] == 17], key=lambda w: w["x"])
        return ic if st == INFO and ic and not any(w["hidden"] for w in ic) else None
    ok, ic = wait_until(shown, UI_S, 0.05)
    guard(r, x, f"{gc.name} craft screen", o.get("ok") is True and ok, f"open {o}; stack {stack(gc)}; {widgets(gc)}")
    r.ev[f"open {gc.name} {ctype}-{cid}"] = pick(o, "baseIndex", "index")
    return ic
def icon(r, x, gc, ic, slot):
    w = ic[slot]
    b = [w["x"] + w["w"] / 2.0, w["y"] + w["h"] / 2.0]
    rep = gc.cmd({"cmd": "inject_input", "kind": "click", "x": win(*b)[0], "y": win(*b)[1]})
    time.sleep(0.1)
    names = [t["text"] for t in widgets(gc)[1] if t["type"] == "Text" and t["w"] == 95 and t["h"] == 16]
    r.ev[f"icon {gc.name} {slot}"] = {"rect": [w["x"], w["y"], w["w"], w["h"]], "win": win(*b), "ok": rep.get("ok"),
                                      "star": [str(n or "").startswith("*") for n in names]}   # R-H16e-T0-2
def row_switch(r, x, gc, key, start, name, why, dc=False):
    """H16e-1..4 / H16e-6: `gc` flips switch `key` (S0 disabled = start) by real input; both hold `not start` after the poll."""
    d = s0(r, x, {key: start})
    if key in CELLS:
        rclick(r, x, gc, key)
    else:
        icon(r, x, gc, open_info(r, x, gc, WEAPONS[key][0], WEAPONS[key][1]), WEAPONS[key][2])
    r.ev["poll"] = poll(x, (key,), lambda b: {"dc": b[0]["detectionChance"]})
    e, o = end(r, x), other(x, gc)
    guard(r, x, f"{gc.name} own change", flag(e[gc.name], key) is (not start), f"{gc.name} {key} {flag(e[gc.name], key)}")
    got, dc0, dc1 = flag(e[o.name], key), d["probe"]["host"][0]["dc"], e["host"][0]["detectionChance"]
    r.cell(name, got is (not start) and (not dc or dc1 > dc0), f"{o.name} {key} disabled {got} (want {not start})"
           + (f", host detectionChance {dc0} -> {dc1} (want a rise)" if dc else "") + f": {why}")
    close(r, x, d)
def row_h16e_5(r, x):
    h, c = x.host, x.client
    d = s0(r, x, {"I2.0": True})
    fo = r.ev["force"] = {gc.name: gc.cmd({"cmd": "craft_force", "craft_id": 2, "ammo": 0}) for gc in (c, h)}
    st = {gc.name: craft(tp(gc), INT, 2) for gc in (h, c)}
    guard(r, x, "staged ammo and READY", all(v.get("status") == "STR_READY" and all(w["ammo"] == 0 for w in v["weapons"])
                                             for v in st.values()), f"{st}; force {fo}")
    icon(r, x, c, open_info(r, x, c, INT, 2), 0)
    r.ev["poll"] = poll(x, ("I2.0",), lambda b: {"st": craft(b, INT, 2).get("status")})   # R-H16e-T0-3: no client window asserted
    e = end(r, x)
    guard(r, x, "client own change", flag(e["client"], "I2.0") is False, f"client I2.0 {flag(e['client'], 'I2.0')}")
    hf, hs, cs = flag(e["host"], "I2.0"), craft(e["host"], INT, 2)["status"], craft(e["client"], INT, 2)["status"]
    r.cell("reCheck", hf is False and hs == "STR_REARMING" and cs == "STR_REARMING",
           f"host I2.0 disabled {hf} (want False), host status {hs} / client status {cs} (want STR_REARMING on both): "
           "the host never re-checked the craft (T-2)")
    close(r, x, d)
def row_h16e_7(r, x):
    h, c = x.host, x.client
    d = s0(r, x, {"I2.1": True})
    try:
        ic = open_info(r, x, c, INT, 2)
        fo = r.ev["force out"] = h.cmd({"cmd": "craft_force", "craft_id": 2, "status": "STR_OUT"})
        ok = wait_until(lambda: craft(tp(c), INT, 2).get("status") == "STR_OUT", UI_S, 0.1)[0]
        guard(r, x, "client sees OUT", fo.get("ok") is True and ok, f"force {fo}; client {craft(tp(c), INT, 2)}")
        icon(r, x, c, ic, 1)
        time.sleep(2.0)
        e = end(r, x)
        guard(r, x, "client own change", flag(e["client"], "I2.1") is False, f"client I2.1 {flag(e['client'], 'I2.1')}")
        hs = craft(e["host"], INT, 2)["status"]
        r.ev["slot 1 disabled (EVIDENCE only, F6649)"] = {n: flag(e[n], "I2.1") for n in e}
        r.cell("outGate", hs == "STR_OUT", f"host status {hs} after the click (want STR_OUT): a craft that is out was re-checked")
    finally:
        r.ev["force ready"] = pick(h.cmd({"cmd": "craft_force", "craft_id": 2, "status": "STR_READY"}), "ok", "error")
    close(r, x, d)
def pump(x): geo.skip_realtime(x.host, x.client, 1, speed_idx=0, stuck_timeout=None)  # noqa: E704
def dfs(gc): return gc.ok({"cmd": "dogfight_state"}).get("dogfights", [])  # noqa: E704
def df_for(gc, cid, uid): return next((f for f in dfs(gc) if f["craftId"] == cid and f["ufoId"] == uid), None)  # noqa: E704
def row_h16e_8(r, x):
    """The test_shared_dogfight_control.py recipe; the disengage wait ends on both dogfight lists empty (R-H16e-T0-1)."""
    h, c = x.host, x.client
    guard(r, x, "host option", x.opt is True, f"host {OPT} {x.opt}")
    sc = {gc.name: gc.cmd({"cmd": "spawn_craft", "type": AV, "weapon": "STR_CANNON_UC"}) for gc in (h, c)}
    guard(r, x, "avenger", sc["host"].get("ok") is True and sc["host"].get("craft_id") == sc["client"].get("craft_id"), f"{sc}")
    x.av = sc["host"]["craft_id"]
    d = s0(r, x, {})
    b0 = next(b for b in h.ok({"cmd": "geo_state"})["bases"] if not b.get("coopBase") and not b.get("coopIcon"))
    uid = h.ok({"cmd": "spawn_ufo", "type": "STR_MEDIUM_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                "race": "STR_SECTOID", "trajectory": "P0", "state": "flying", "speed": 1, "lon": b0["lon"] + 0.03, "lat": b0["lat"]})["ufo_id"]
    seen = lambda: any(u["id"] == uid for u in c.ok({"cmd": "geo_state"}).get("ufos", []))  # noqa: E731
    t0 = time.time()
    while time.time() - t0 < 45 and not seen():
        pump(x)
    guard(r, x, "ufo on client", seen(), f"ufo {uid}")
    co, t1 = c.cmd({"cmd": "craft_order", "order": "target", "craft_id": x.av, "craft_type": AV, "ufo_id": uid}), time.time()
    while time.time() - t1 < 120 and not (df_for(h, x.av, uid) and df_for(c, x.av, uid)):
        pump(x)
    hd, cd = df_for(h, x.av, uid), df_for(c, x.av, uid)
    r.ev["open"] = {"order": pick(co, "ok", "error"), "s": round(time.time() - t1, 1), "host": hd, "client": cd}
    guard(r, x, "dogfight on both", bool(hd and cd) and hd["replica"] is False and cd["replica"] is True, f"{r.ev['open']}")
    try:
        r.ev["toggle"] = pick(c.cmd({"cmd": "dogfight_action", "action": "weaponToggle", "arg": 0}), "ok", "error")
        ok = wait_until(lambda: (df_for(h, x.av, uid) or {}).get("weaponEnabled", [None])[0] is False, 5.0, 0.1)[0]
        r.ev["host window"] = (df_for(h, x.av, uid) or {}).get("weaponEnabled")
        guard(r, x, "host window state", ok, f"host dogfight {df_for(h, x.av, uid)}")
        r.ev["poll"] = poll(x, ("AV.0",))
        e = end(r, x)
        guard(r, x, "host remembered", flag(e["host"], "AV.0", x) is True, f"host AV.0 {flag(e['host'], 'AV.0', x)} (T-3 write)")
        got = flag(e["client"], "AV.0", x)
        r.cell("remembered", got is True, f"client {AV}-{x.av} slot 0 disabled {got} (want True): "
                                          "the host's remembered weapon switch never reached the client (T-3)")
    finally:
        r.ev["disengage"] = pick(c.cmd({"cmd": "dogfight_action", "action": "disengage"}), "ok", "error")
        n = 0
        while n < 10 and (dfs(h) or dfs(c)):
            pump(x)
            n += 1
        r.ev["after disengage"] = {"pumps": n, "host": len(dfs(h)), "client": len(dfs(c))}
    now = r.ev["requests"] = {gc.name: rs(gc)["requests"] for gc in (h, c)}
    r.cell("requests", now == d["R0"], f"requests {now} vs R0 {d['R0']} (STOP-IF 5)")
def row_h16e_9(r, x):
    """SEPARATE: the client's own mind-shield and weapon switches stay on its machine; no shared command."""
    h, c = x.host, x.client
    guard(r, x, "start", wait_until(lambda: top(h) == GEO and top(c) == GEO, 10.0, 0.2)[0], f"stacks {stack(h)} / {stack(c)}")
    s_0, b = {gc.name: pick(ss(gc), "cmd", "applyCount") for gc in (h, c)}, tp(c)
    guard(r, x, "own base 0", b[0]["name"] == "ClientBase", f"{[e['name'] for e in b]}")
    fb = c.cmd({"cmd": "fac_build", "facility": FAC, "x": CELLS["A"][0], "y": CELLS["A"][1]})
    ok, i = wait_until(lambda: fidx(tp(c), "A"), UI_S, 0.05)       # index 9 (TASK 0 (v)), never 0
    bt = c.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": i if ok else -1, "time": 0})
    r.ev["facility"] = {"fac_build": pick(fb, "ok", "error"), "index": i, "buildTime0": pick(bt, "ok", "type", "buildTime")}
    guard(r, x, "own facility", ok and bt.get("ok") is True and bt.get("buildTime") == 0, f"{r.ev['facility']}")
    rclick(r, x, c, "A")
    icon(r, x, c, open_info(r, x, c, INT, 2), 0)
    time.sleep(2.0)
    e = end(r, x)
    fa, wa = flag(e["client"], "A"), flag(e["client"], "I2.0")
    s_1 = {gc.name: pick(ss(gc), "cmd", "applyCount") for gc in (h, c)}
    r.ev["shared_stats"] = {"before": s_0, "after": s_1}
    r.cell("ownFlags", fa is True and wa is True, f"client facility A disabled {fa}, client I2.0 disabled {wa} (want True / True)")
    r.cell("noCommand", s_0 == s_1, f"shared_stats {s_0} -> {s_1} (want unchanged)")
    r.ev["close"] = closeall(x)
def run_one(rid, fn, x, results):
    r = Row(rid)
    try:
        fn(r, x)
    except GuardMiss as e:
        r.ev["guardMiss"] = str(e)
    except Exception as e:
        r.cell("exception", False, short(e, 800))
    if any(f.startswith(("G:", "exception")) for f in r.fails):
        try:
            r.ev["closeAfterMiss"] = closeall(x)
        except Exception as e:
            r.ev["closeAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)
def setup_a(x):
    """Host fac_build A (0, 3) and B (4, 2); buildTime 0 on the client, then the host; both list A and B built and enabled."""
    h, c = x.host, x.client
    x.opt = h.cmd({"cmd": "option_values", "ids": [OPT]}).get("values", {}).get(OPT)
    fb = {k: pick(h.cmd({"cmd": "fac_build", "facility": FAC, "x": v[0], "y": v[1]}), "ok", "error") for k, v in CELLS.items()}
    ok = wait_until(lambda: all(fidx(tp(gc), k) is not None for gc in (h, c) for k in CELLS), 15.0, 0.1)[0]
    ix = {gc.name: {k: fidx(tp(gc), k) for k in CELLS} for gc in (h, c)}
    if not ok or ix["host"] != ix["client"]:
        raise RuntimeError(f"facilities not listed on both: fac_build {fb}, indices {ix}")
    bt = {f"{gc.name} {k}": pick(gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": i, "time": 0}), "ok", "buildTime")
          for gc in (c, h) for k, i in ix["host"].items()}
    def built(gc): return all(f["buildTime"] == 0 and f["disabled"] is False for f in tp(gc)[0]["facilities"] if f["type"] == FAC)
    ok = wait_until(lambda: built(h) and built(c) and eqp(tp(h)) == eqp(tp(c)), UI_S, 0.2)[0]
    info = {"option": {"host": x.opt, "client": c.cmd({"cmd": "option_values", "ids": [OPT]}).get("values", {}).get(OPT)},
            "fac_build": fb, "indices": ix, "buildTime0": bt, "probe": {gc.name: proj(tp(gc)) for gc in (h, c)}}
    if not ok:
        raise RuntimeError(f"A / B not built + enabled + equal on both: {info}")
    return info
def boot_b():
    tag, (hp, cp, lp) = BOOT_B
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", mods=(MOD,)))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client", mods=(MOD,)))
    try:
        [f() for f in (host.spawn, client.spawn, host.connect, client.connect)]
        session.new_campaign(host, client, port=str(lp), campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))
def boot(tag, up, setup, rows, results, walls):
    t0, js, info = time.time(), None, None
    try:
        js = up()
        x = SimpleNamespace(host=js.host, client=js.client, av=None, opt=None)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = setup(x)
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
    except Exception as e:
        cap = capture(x) if js is not None else None
        print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn in (rows if info is not None else ()):
            run_one(rid, fn, x, results)
    finally:
        try:
            js is not None and js.shutdown()
        except Exception as e:
            print(f"[w2h16e] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

T1, T2 = "the client's mind-shield switch stayed on its machine (T-1)", "the client's weapon switch stayed on its machine (T-2)"
T3 = "the host's weapon switch never reached the client"
ROWS_A = (("H16e-1", lambda r, x: row_switch(r, x, x.client, "A", False, "reachedHost", T1, dc=True)),
          ("H16e-2", lambda r, x: row_switch(r, x, x.client, "A", True, "reachedHost", T1)),
          ("H16e-3", lambda r, x: row_switch(r, x, x.host, "B", False, "reachedClient", "the host's switch never reached the client")),
          ("H16e-4", lambda r, x: row_switch(r, x, x.client, "I2.0", False, "reachedHost", T2)),
          ("H16e-5", row_h16e_5),
          ("H16e-6", lambda r, x: row_switch(r, x, x.host, "I1.1", False, "reachedClient", T3)),
          ("H16e-7", row_h16e_7), ("H16e-8", row_h16e_8))
ROWS_B = (("H16e-9", row_h16e_9),)

def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_A[0], lambda: shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], mods=(MOD,), host_options={OPT: True}),
         setup_a, ROWS_A, results, walls)
    boot(BOOT_B[0], boot_b, lambda x: {"bases": {gc.name: [b["name"] for b in tp(gc)] for gc in (x.host, x.client)}},
         ROWS_B, results, walls)
    failed, n = [rid for rid, _ in ROWS_A + ROWS_B if not results.get(rid)], len(ROWS_A + ROWS_B)
    print(f"\ntest_w2_shared_toggles: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
