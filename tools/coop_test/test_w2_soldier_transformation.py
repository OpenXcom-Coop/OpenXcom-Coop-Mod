"""W2-H16c (S-12, F6605; D226 a; Q1 a .. Q7 a; V1-V4): a soldier transformation made on one machine reaches the shared world;
the transformation lists show own soldiers only. Spec docs rewrite/prompts/w2h16c_soldier_transformation.md (e)-(f); TASK 0
rewrite/w2h16c-task0/CONSTANTS.md rulings C1-C7 applied. Levers (test-only): open_transformation, set_soldier_dead,
transform_probe. Real input: the SoldiersState action box (drop-down arithmetic, F6880) and Start (click_widget, raw rule key).
Boot A (SHARED): H16c-1..10; Boot B (SEPARATE): H16c-11. RED (commit 1): H16c-1..8 and -10 fail on their named cells, -9 and
-11 pass; GREEN: all pass. "G:" cells are guards (CAPTURE on a miss). `requests` is recorded per row, never a verdict.
EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
"""

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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Transform_Test")
BOOT_A = ("w2h16ca", (49340, 49341, 47330))     # SHARED; lobby 47330 (F6699)
BOOT_B = ("w2h16cb", (49342, 49343, 47332))     # SEPARATE; lobby 47332
BOOST, CLONE, RETIRE, RAISE = "STR_H16C_BOOST", "STR_H16C_CLONE", "STR_H16C_RETIRE", "STR_H16C_RAISE"
RULES = [BOOST, CLONE, RETIRE, RAISE]
ROCKET = "STR_SMALL_ROCKET"
OPTION = {"OVERVIEW": 3, BOOST: 4, CLONE: 5, RETIRE: 6, RAISE: 7}   # action-box rows (F6881); row 2 INVENTORY is never clicked
N_OPTIONS, SCALE = 8, 2                                               # 640x400 window over 320x200, no bands (F5802)
S0_S, POLL_S, POLL_I, UI_S, BOX_S, TAIL_S = 20.0, 3.0, 0.25, 3.0, 2.0, 5.0
GEO, SS, STS, STLS, SIS, BOX = ("GeoscapeState", "SoldiersState", "SoldierTransformationState",
                                "SoldierTransformationListState", "SoldierInfoState", "CoopState")

class GuardMiss(Exception):
    """A guard failed: the row ends after its CAPTURE line."""

def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."

def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while not (last := pred()) and time.time() - t0 < timeout:
        time.sleep(interval)
    return bool(last), last

def pick(d, *keys): return {k: d.get(k) for k in keys}  # noqa: E704
def stack(gc): return session.states_stripped(gc)  # noqa: E704
def top(gc): return (stack(gc) or [""])[-1]  # noqa: E704
def rs(gc): return pick(gc.cmd({"cmd": "shared_resync_stats"}), "requests", "pending")  # noqa: E704
def ss(gc): return pick(gc.cmd({"cmd": "shared_stats"}), "cmd", "okCount", "failCount", "applyCount", "lastFail")  # noqa: E704
def tp(gc): return gc.cmd({"cmd": "transform_probe"})  # noqa: E704
def one(p, sid): return ([s for s in p.get("soldiers") or [] if s.get("id") == sid] or [{}])[0]  # noqa: E704
def hist(p, sid, rule): return (one(p, sid).get("history") or {}).get(rule, 0)  # noqa: E704
def rockets(p): return (p.get("stores") or {}).get(ROCKET, 0)  # noqa: E704
def new_transfers(p0, p): return (p.get("transfers") or [])[len(p0.get("transfers") or []):]  # noqa: E704
def displayed(gc): return gc.cmd({"cmd": "screen_state"}).get("displayed")  # noqa: E704
def fr(p): return [p.get("funds"), rockets(p)]  # noqa: E704
def brief(p, sid): return pick(one(p, sid), "where", "history", "stats", "craftId", "owner")  # noqa: E704

def view(p, ids, hours=True):
    """What S0 compares (spec (f) row frame): funds, stores, transfers, soldier counter and the row's soldiers. S0 drops the
    transfer hours: the host's clock (idx 0) advances its transfers between rows and a replica's never do (F6690)."""
    tr = [t if hours else {k: v for k, v in t.items() if k != "hours"} for t in p.get("transfers") or []]
    return {"funds": p.get("funds"), "counter": p.get("soldierCounter"), "stores": p.get("stores"), "transfers": tr,
            "soldiers": [s for s in p.get("soldiers") or [] if s.get("id") in ids]}

def captions(gc):
    """Visible plain Text captions of the top state (list_widgets; a TextButton is not a Text)."""
    w = gc.cmd({"cmd": "list_widgets"}).get("widgets") or []
    return [e.get("text") for e in w if e.get("type") == "class OpenXcom::Text" and e.get("visible")]

class Row:
    def __init__(self, rid):
        self.rid, self.t0, self.ev, self.fails, self.passed, self.ids = rid, time.time(), {}, [], [], ()
    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return ok

def capture(x, tag):
    """FIXTURE-STOP dump (STOP-IF 3): both machines' transform_probe, screen_state, shared_stats, shared_resync_stats, stack."""
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"stack": stack(gc), "transform_probe": tp(gc), "screen_state": gc.cmd({"cmd": "screen_state"}),
                            "shared_stats": gc.cmd({"cmd": "shared_stats"}),
                            "shared_resync_stats": gc.cmd({"cmd": "shared_resync_stats"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)

def guard(r, x, name, ok, detail):
    if r.cell("G:" + name, ok, detail):
        return
    capture(x, f"{r.rid} (guard {name})")
    raise GuardMiss(f"guard {name}")

def s0(r, x, staging=()):
    """Row frame S0: the row's staging on both machines, client first (S25); then <= 20 s until both transform_probe agree
    on the view, both stand on the geoscape and no restream is pending (C3: the red restream pops the client's screens).
    R0 = both `requests` (EVIDENCE only)."""
    h, c = x.host, x.client
    d = {"req0": {gc.name: rs(gc)["requests"] for gc in (h, c)}, "staging": []}
    for gc in (c, h):
        for req in staging:
            v = gc.cmd(req)
            d["staging"].append([gc.name, req, pick(v, "ok", "dead", "funds", "error")])
            guard(r, x, f"staging {gc.name} {req['cmd']}", v.get("ok") is True and v.get("dead", True) is True, f"{v}")
    t0 = time.time()

    def agreed():
        if top(h) != GEO or top(c) != GEO or rs(c)["pending"]:
            return None
        ph, pc = tp(h), tp(c)
        return {"host": ph, "client": pc} if view(ph, r.ids, False) == view(pc, r.ids, False) else None
    ok, p = wait_until(agreed, S0_S, 0.25)
    d["agreeS"] = round(time.time() - t0, 2)
    r.ev["S0"] = d
    guard(r, x, "S0 agreement", ok, f"not agreed in {d['agreeS']} s; stacks {stack(h)} / {stack(c)}")
    d["R0"] = {gc.name: rs(gc)["requests"] for gc in (h, c)}
    d["ss"] = {gc.name: ss(gc) for gc in (h, c)}
    d["view"] = view(p["host"], r.ids)
    return p

def hold(r, x):
    """The host keeps a screen on top from before the row's action until its poll ends (no heartbeat, TRACE 2)."""
    o = x.host.cmd({"cmd": "open_screen", "screen": "soldiers"})
    guard(r, x, "hold", o.get("ok") is True and wait_until(lambda: top(x.host) == SS, UI_S)[0], f"{o}; stack {stack(x.host)}")

def close(r, x):
    r.ev["close"] = {gc.name: pick(gc.cmd({"cmd": "close_screens"}), "popped", "refused") for gc in (x.host, x.client)}
    r.ev["requestsAtClose"] = {gc.name: rs(gc)["requests"] for gc in (x.host, x.client)}

def start(r, x, gc, rule, sid, tag, dead=False, back=GEO):
    """open_transformation -> the REAL screen -> its Start (the raw rule key; visible: guard) -> the screen pops to `back`."""
    o = gc.cmd({"cmd": "open_transformation", "rule": rule, "soldierId": sid, "dead": dead})
    guard(r, x, f"{tag} open", o.get("ok") is True and wait_until(lambda: top(gc) == STS, UI_S)[0], f"{o}; stack {stack(gc)}")
    b = tp(gc).get("buttons") or []
    st = [e for e in b if e.get("text") == rule]
    r.ev[f"{tag} {rule} buttons"] = b
    guard(r, x, f"{tag} Start visible", bool(st) and st[0].get("visible") is True, f"buttons {b}")
    cw = gc.cmd({"cmd": "click_widget", "match": rule})
    ok = wait_until(lambda: top(gc) != STS, UI_S)[0]
    guard(r, x, f"{tag} Start pressed", cw.get("ok") is True and ok and top(gc) == back,
          f"click {pick(cw, 'ok', 'text', 'error')}; stack {stack(gc)} (want top {back})")

def dropdown(cb, row):
    """ComboBox::setDropdown for the action box (ComboBox.cpp :296-312, TASK 0 (ii)): items = min(N, 10), row height 8 (small
    font 9, spacing -1), the popup above the box: list top = y - (items x 8 + 6) + 3, x + 2, width w - 4 - 14 + 1. Returns the
    window pixels of the box's centre and of option `row`'s centre."""
    x0, y0, w, h = cb
    items, rh = min(N_OPTIONS, 10), 8
    lt, lx, lw = y0 - (items * rh + 6) + 3, x0 + 2, w - 4 - 14 + 1
    return ((int((x0 + w / 2.0) * SCALE), int((y0 + h / 2.0) * SCALE)),
            (int((lx + lw / 2.0) * SCALE), int((lt + rh * row + rh / 2.0) * SCALE)))

def mode(r, x, gc, opt, tag):
    """open_soldiers + the action-box route (real input): click the box's centre, then option `opt`. Returns the TextList."""
    o = gc.cmd({"cmd": "open_soldiers"})
    guard(r, x, f"{tag} soldiers", o.get("ok") is True and wait_until(lambda: top(gc) == SS, UI_S)[0], f"{o}; stack {stack(gc)}")
    time.sleep(0.2)
    w = gc.cmd({"cmd": "list_widgets"}).get("widgets") or []
    cb = [e for e in w if str(e.get("type")).endswith("ComboBox") and e.get("y") == 176]
    tl = [e for e in w if str(e.get("type")).endswith("TextList")]
    guard(r, x, f"{tag} action box", bool(cb and tl), f"widgets {w}")
    (bx, by), (ox, oy) = dropdown([cb[0][k] for k in ("x", "y", "w", "h")], OPTION[opt])
    k1 = gc.cmd({"cmd": "inject_input", "kind": "click", "x": bx, "y": by})
    time.sleep(0.3)
    k2 = gc.cmd({"cmd": "inject_input", "kind": "click", "x": ox, "y": oy})
    time.sleep(0.4)
    r.ev[f"{tag} route {opt}"] = {"box": [bx, by], "option": [ox, oy], "clicks": [pick(k, "ok", "error") for k in (k1, k2)]}
    return tl[0]

def identify(r, x, gc, rule, tl, ids, tag):
    """C5: a transformation mode is identified by its Start caption: a real click on the first displayed row opens the REAL
    SoldierTransformationState whose Start reads the rule key; then close_screens."""
    gc.cmd({"cmd": "inject_input", "kind": "click", "x": int((tl["x"] + tl["w"] / 2.0) * SCALE), "y": int((tl["y"] + 4.0) * SCALE)})
    ok = wait_until(lambda: top(gc) == STS, UI_S)[0]
    b = [e.get("text") for e in tp(gc).get("buttons") or []] if ok else []
    r.ev[f"{tag} identify {rule}"] = {"ok": ok, "buttons": b}
    gc.cmd({"cmd": "close_screens"})
    guard(r, x, f"{tag} mode {rule}", bool(ids) and ok and rule in b, f"displayed {ids}; buttons {b}; stack {stack(gc)}")

def poll(r, x):
    """Both transform_probe every ~0.25 s for 3 s; the times the row's view changed are kept; returns the last probes."""
    changes, n, t0, last, prev = [], 0, time.time(), None, None
    while time.time() - t0 < POLL_S:
        last = {gc.name: tp(gc) for gc in (x.host, x.client)}
        v = {k: view(p, r.ids) for k, p in last.items()}
        if v != prev:
            changes.append(round(time.time() - t0, 2))
            prev = v
        n += 1
        time.sleep(POLL_I)
    r.ev["poll"] = {"samples": n, "changedAt": changes}
    r.ev["end"] = {k: dict(view(p, r.ids), top=p.get("top"), buttons=p.get("buttons")) for k, p in last.items()}
    return last

def own(r, x, p, p0, sid, rule, tag, cost, rocket):
    """G: the clicking machine's own change (red: its local write; green: the host's result applied)."""
    got = {"history": [hist(p0, sid, rule), hist(p, sid, rule)], "funds": [p0.get("funds"), p.get("funds")],
           "rockets": [rockets(p0), rockets(p)]}
    guard(r, x, f"{tag} own change", got["history"][1] == got["history"][0] + 1 and p0.get("funds") - p.get("funds") == cost
          and rockets(p0) - rockets(p) == rocket, f"soldier {sid} {rule}: {got} (want history +1, funds -{cost}, rockets -{rocket})")

def row_1(r, x):
    r.ids = tuple(x.ids)
    s0(r, x)
    for gc, want, name in ((x.client, x.C, "clientList"), (x.host, x.H, "hostList")):
        tl = mode(r, x, gc, BOOST, gc.name)
        ids = displayed(gc)
        r.ev[f"{gc.name} displayed"] = ids
        identify(r, x, gc, BOOST, tl, ids, gc.name)
        r.cell(name, ids == want, f"{gc.name} {BOOST} list {ids} (want {want}): the transformation list shows the partner's "
                                  f"soldiers (F6605)")

def row_2(r, x):
    c = x.client
    r.ids = (x.C3, x.H3)
    p = s0(r, x, [{"cmd": "set_soldier_dead", "soldierId": i} for i in (x.C3, x.H3)])
    dead = {n: [s["id"] for s in p[n].get("soldiers") or [] if s.get("where") == "dead"] for n in p}
    r.ev["dead"] = dead
    guard(r, x, "deaths", all(v == [x.C3, x.H3] for v in dead.values()), f"dead lists {dead} (want [{x.C3}, {x.H3}] on both)")
    tl = mode(r, x, c, RAISE, "client")
    ids = displayed(c)
    r.ev["client displayed"] = ids
    identify(r, x, c, RAISE, tl, ids, "client")
    r.cell("raiseList", ids == [x.C3], f"client {RAISE} list {ids} (want [{x.C3}]): the list shows the partner's dead (F6605)")
    mode(r, x, c, "OVERVIEW", "client")
    guard(r, x, "overview open", wait_until(lambda: top(c) == STLS, UI_S)[0], f"stack {stack(c)}")
    rows = tp(c).get("rows") or []
    rr = [q for q in rows if q.get("c0") == RAISE]
    r.ev["overview rows"] = rows
    c.cmd({"cmd": "close_screens"})
    guard(r, x, "overview RAISE row", bool(rr), f"rows {rows}")
    r.cell("overview", rr[0].get("c2") == "1", f"overview eligible for {RAISE} '{rr[0].get('c2')}' (want '1'): the overview "
                                               f"counts the partner's dead (F6605)")

def row_3(r, x):
    r.ids = (x.C1,)
    p0 = s0(r, x)
    hold(r, x)
    start(r, x, x.client, BOOST, x.C1, "client")
    e = poll(r, x)
    h, c = e["host"], e["client"]
    own(r, x, c, p0["client"], x.C1, BOOST, "client", 100000, 1)
    a0, a1 = r.ev["S0"]["ss"]["host"]["applyCount"], ss(x.host)["applyCount"]
    r.cell("reachedHost", one(h, x.C1) == one(c, x.C1) and fr(h) == fr(c) and a1 == a0 + 1,
           f"C1 host {brief(h, x.C1)} / client {brief(c, x.C1)}; funds+rockets {fr(h)}/{fr(c)}; host applyCount {a0} -> {a1} "
           f"(want +1): the client's transformation stayed on its machine (S-12)")
    close(r, x)

def row_4(r, x):
    r.ids = (x.H1,)
    p0 = s0(r, x)
    hold(r, x)
    start(r, x, x.host, BOOST, x.H1, "host", back=SS)
    e = poll(r, x)
    h, c = e["host"], e["client"]
    own(r, x, h, p0["host"], x.H1, BOOST, "host", 100000, 1)
    r.cell("reachedClient", one(c, x.H1) == one(h, x.H1) and fr(h) == fr(c), f"H1 host {brief(h, x.H1)} / client "
           f"{brief(c, x.H1)}; funds+rockets {fr(h)}/{fr(c)}: the host's transformation never reached the client")
    close(r, x)

def row_5(r, x):
    r.ids = (x.C1,)
    p0 = s0(r, x)
    hold(r, x)
    start(r, x, x.client, CLONE, x.C1, "client")
    e = poll(r, x)
    h, c = e["host"], e["client"]
    own(r, x, c, p0["client"], x.C1, CLONE, "client", 50000, 0)
    nc, nh = new_transfers(p0["client"], c), new_transfers(p0["host"], h)
    guard(r, x, "client clone", len(nc) == 1 and nc[0].get("kind") == "soldier", f"client new transfers {nc}")
    cid = nc[0].get("soldierId")
    cc, hc = one(c, cid), one(h, cid)
    r.ev["clone"] = {"id": cid, "client": cc, "host": hc, "counters": [h.get("soldierCounter"), c.get("soldierCounter")],
                     "newTransfers": {"host": nh, "client": nc}}
    # SavedGame::getId post-increments (SavedGame.cpp :2343-2354): after the clone both counters hold its id + 1
    r.cell("cloneOnBoth", hc == cc and nh == nc and nc[0].get("hours") == 24 and cc.get("where") == "transfer"
           and h.get("soldierCounter") == c.get("soldierCounter") == cid + 1 and cc.get("owner") == x.seat["client"]
           and one(h, x.C1).get("history") == one(c, x.C1).get("history"),
           f"clone {cid}: host {pick(hc, 'where', 'owner')} / client {pick(cc, 'where', 'owner')} (want owner {x.seat['client']} "
           f"on both); new transfers host {nh} / client {nc}; counters {r.ev['clone']['counters']}; C1 history "
           f"{one(h, x.C1).get('history')}/{one(c, x.C1).get('history')}: the client's clone exists only on the client (F6689)")
    close(r, x)

def row_6(r, x):
    r.ids = (x.C2,)
    p0 = s0(r, x)
    hold(r, x)
    start(r, x, x.client, RETIRE, x.C2, "client")
    e = poll(r, x)
    h, c = e["host"], e["client"]
    nc, nh = new_transfers(p0["client"], c), new_transfers(p0["host"], h)
    want = [{"hours": 24, "kind": "item", "soldierId": -1, "item": ROCKET, "qty": 1}]
    r.ev["newTransfers"] = {"host": nh, "client": nc}
    guard(r, x, "client own change", not one(c, x.C2) and nc == want, f"client C2 {one(c, x.C2)}; new transfers {nc} (want {want})")
    r.cell("reachedHost", not one(h, x.C2) and nh == want, f"host C2 {pick(one(h, x.C2), 'where', 'name')}; host new transfers "
                                                          f"{nh} (want {want}): the client's retirement stayed on its machine")
    close(r, x)

def row_7(r, x):
    r.ids = (x.C3,)
    p0 = s0(r, x)
    guard(r, x, "C3 dead", all(one(p0[n], x.C3).get("where") == "dead" for n in p0), f"C3 {[brief(p0[n], x.C3) for n in p0]}")
    hold(r, x)
    start(r, x, x.client, RAISE, x.C3, "client", dead=True)
    e = poll(r, x)
    h, c = e["host"], e["client"]
    nc, nh = new_transfers(p0["client"], c), new_transfers(p0["host"], h)
    r.ev["newTransfers"] = {"host": nh, "client": nc}
    guard(r, x, "client own change", one(c, x.C3).get("where") == "transfer" and hist(c, x.C3, RAISE) == hist(p0["client"], x.C3, RAISE) + 1,
          f"client C3 {pick(one(c, x.C3), 'where', 'history')}")
    r.cell("reachedHost", one(h, x.C3) == one(c, x.C3) and nh == nc and [t.get("hours") for t in nc] == [24], f"C3 host "
           f"{brief(h, x.C3)} / client {brief(c, x.C3)}; new transfers {nh} / {nc}: the client's resurrection stayed on its machine")
    close(r, x)

def row_8(r, x):
    h, c = x.host, x.client
    r.ids = (x.H1, x.C4)
    p0 = s0(r, x)
    for gc in (h, c):
        gc.cmd({"cmd": "shared_reset_stats"})
    r.ev["shared_cmd"] = pick(c.cmd({"cmd": "shared_cmd", "jcmd": "soldier_transform", "baseId": 0, "payload": {
        "rule": BOOST, "soldierId": x.H1, "dead": False, "name": "x"}}), "ok", "error")
    guard(r, x, "client failCount +1", wait_until(lambda: ss(c)["failCount"] >= 1, UI_S)[0], f"client {ss(c)}")
    seen = wait_until(lambda: top(c) == BOX, UI_S)[0]
    back = c.cmd({"cmd": "coop_dialog_back"}) if top(c) == BOX else {}
    r.ev["refusal box"] = {"seen": seen, "back": pick(back, "ok", "code", "error")}
    guard(r, x, "refusal box closed", seen and wait_until(lambda: top(c) != BOX, UI_S)[0], f"seen {seen}; stack {stack(c)}")
    f = {gc.name: ss(gc) for gc in (h, c)}
    p1 = {gc.name: tp(gc) for gc in (h, c)}
    r.ev["after refusal"] = {"shared_stats": f, "H1 history": {n: one(p1[n], x.H1).get("history") for n in p1}}
    r.cell("refusal", f["client"]["lastFail"] == "not your soldier" and f["host"]["applyCount"] == 0
           and all(one(p1[n], x.H1) == one(p0[n], x.H1) for n in p1),
           f"client lastFail '{f['client']['lastFail']}' (want 'not your soldier'); host applyCount {f['host']['applyCount']} "
           f"(want 0); H1 unchanged {[one(p1[n], x.H1) == one(p0[n], x.H1) for n in p1]}")
    hold(r, x)
    start(r, x, c, BOOST, x.C4, "client control")
    e = poll(r, x)
    own(r, x, e["client"], p0["client"], x.C4, BOOST, "client control", 100000, 1)
    r.cell("control", one(e["host"], x.C4) == one(e["client"], x.C4), f"control: C4 host {brief(e['host'], x.C4)} / client "
           f"{brief(e['client'], x.C4)}: the client's own transformation stayed on its machine")
    close(r, x)

def row_9(r, x):
    c = x.client
    r.ids = (x.C4,)
    p0 = s0(r, x, [{"cmd": "set_funds", "value": 1000000}])
    o = c.cmd({"cmd": "open_soldier_info", "soldierId": x.C4})
    guard(r, x, "info open", o.get("ok") is True and wait_until(lambda: top(c) == SIS, UI_S)[0], f"{o}; stack {stack(c)}")
    hold(r, x)
    start(r, x, c, BOOST, x.C4, "client", back=SIS)
    time.sleep(3.0)
    cap1, p1 = captions(c), tp(c)
    own(r, x, p1, p0["client"], x.C4, BOOST, "client", 100000, 1)
    pp = c.cmd({"cmd": "pop_state"})
    ok = wait_until(lambda: top(c) == GEO, UI_S)[0]
    o2 = c.cmd({"cmd": "open_soldier_info", "soldierId": x.C4})
    guard(r, x, "info reopen", pp.get("ok") is True and ok and o2.get("ok") is True and wait_until(lambda: top(c) == SIS, UI_S)[0],
          f"pop {pp}; open {o2}; stack {stack(c)}")
    time.sleep(0.5)
    cap2 = captions(c)
    r.ev["captions"] = {"open": cap1, "reopened": cap2}
    r.cell("captions", bool(cap1) and cap1 == cap2, f"open {cap1} / reopened {cap2}: the open soldier screen kept a stale soldier")
    close(r, x)

def row_10(r, x):
    h, c = x.host, x.client
    r.ids = (x.H2, x.C4)
    p0 = s0(r, x, [{"cmd": "set_funds", "value": 100000}])
    hold(r, x)
    try:
        dn = c.cmd({"cmd": "shared_update_defer", "on": True})
        guard(r, x, "defer on", dn.get("deferred") is True, f"{dn}")
        a0 = ss(h)["applyCount"]
        start(r, x, h, BOOST, x.H2, "host", back=SS)
        ok = wait_until(lambda: ss(h)["applyCount"] >= a0 + 1, UI_S)[0]
        r.ev["host applyCount +1 (wait)"] = {"ok": ok, "before": a0, "now": ss(h)["applyCount"]}
        hf = tp(h).get("funds")
        guard(r, x, "host funds 0", hf == 0, f"host funds {hf}")
        start(r, x, c, BOOST, x.C4, "client stale")         # the client's stale Start is visible: guard + EVIDENCE
        time.sleep(1.0)
    finally:
        r.ev["defer off"] = pick(c.cmd({"cmd": "shared_update_defer", "on": False}), "ok", "deferred")
    seen = wait_until(lambda: top(c) == BOX, BOX_S)[0]
    r.ev["refusal box"] = {"seen": seen, "back": pick(c.cmd({"cmd": "coop_dialog_back"}), "ok", "code", "error") if seen else None}
    guard(r, x, "refusal box closed", wait_until(lambda: top(c) != BOX, UI_S)[0], f"stack {stack(c)}")
    e = poll(r, x)
    lf, a1 = ss(c)["lastFail"], ss(h)["applyCount"]
    want = {"H2": hist(p0["host"], x.H2, BOOST) + 1, "C4": hist(p0["host"], x.C4, BOOST), "funds": 0}
    got = {n: {"H2": hist(e[n], x.H2, BOOST), "C4": hist(e[n], x.C4, BOOST), "funds": e[n].get("funds")} for n in e}
    # F6939 / R-H16c-R-1: the host applied the winning transformation (one apply), the stale one was refused
    r.cell("agree", all(v == want for v in got.values()) and lf == "STR_NOT_ENOUGH_MONEY" and a1 == a0 + 1,
           f"BOOST counts / funds {got} (want {want} on both); client lastFail '{lf}' (want STR_NOT_ENOUGH_MONEY); host "
           f"applyCount {a0} -> {a1} (want +1): two transformations paid from one budget; the worlds disagree")
    close(r, x)

def row_11(r, x):
    h, c = x.host, x.client
    guard(r, x, "start", wait_until(lambda: top(h) == GEO and top(c) == GEO, S0_S, 0.2)[0], f"stacks {stack(h)} / {stack(c)}")
    br = c.cmd({"cmd": "base_report"})                       # the client's own base (first real base)
    sid = (br.get("soldiers") or [{}])[0].get("id")
    r.ids = (sid,)
    p0, s1 = tp(c), {gc.name: ss(gc) for gc in (h, c)}
    r.ev["S0"] = {"base": br.get("name"), "id": sid, "client": view(p0, r.ids), "rules": p0.get("transformations"), "ss": s1}
    guard(r, x, "own soldier", bool(one(p0, sid)) and sorted(p0.get("transformations") or []) == sorted(RULES), f"{r.ev['S0']}")
    start(r, x, c, BOOST, sid, "client")
    time.sleep(2.0)
    p1, s2 = tp(c), {gc.name: ss(gc) for gc in (h, c)}
    r.ev["end"] = {"client": view(p1, r.ids), "shared_stats": s2}
    r.cell("clientBoost", hist(p1, sid, BOOST) == hist(p0, sid, BOOST) + 1 and one(p1, sid).get("stats") != one(p0, sid).get("stats"),
           f"client soldier {sid}: history {one(p1, sid).get('history')}, stats changed "
           f"{one(p1, sid).get('stats') != one(p0, sid).get('stats')}")
    r.cell("noCommand", all(pick(s2[n], "cmd", "applyCount") == pick(s1[n], "cmd", "applyCount") for n in s2),
           f"shared_stats before {s1} / after {s2} (want cmd and applyCount unchanged)")

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
            x.client.cmd({"cmd": "shared_update_defer", "on": False})
            r.ev["settleAfterMiss"] = {gc.name: pick(gc.cmd({"cmd": "close_screens"}), "popped", "refused")
                                       for gc in (x.host, x.client)}
        except Exception as e:
            r.ev["settleAfterMiss"] = short(e)
    r.ev["cellsPassed"], r.ev["wallS"] = r.passed, round(time.time() - r.t0, 1)
    print(f"EVIDENCE {rid}: {json.dumps(r.ev, sort_keys=True, default=str)}", flush=True)
    results[rid] = not r.fails
    print(f"PASS {rid}" if not r.fails else f"FAIL {rid}: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)

def setup_a(x):
    """Seats, C1..C4 / H1..H4 from the host's base_report owners (base order), the rockets (client, then host), and the
    boot guard: both probes offer the four rules and agree."""
    h, c = x.host, x.client
    h.ok({"cmd": "geo_set_speed", "idx": 0})
    x.seat = {gc.name: gc.cmd({"cmd": "synced_options_state"}).get("localSeat") for gc in (h, c)}
    base = h.ok({"cmd": "geo_state"})["bases"][0]["name"]
    sols = h.ok({"cmd": "base_report", "base": base})["soldiers"]
    x.ids = [s["id"] for s in sols]
    x.C = [s["id"] for s in sols if s["owner"] == x.seat["client"]]
    x.H = [s["id"] for s in sols if s["owner"] == x.seat["host"]]
    if len(x.C) < 4 or len(x.H) < 4:
        raise RuntimeError(f"fewer than 4 soldiers a seat at {base}: seats {x.seat}, soldiers {sols}")
    (x.C1, x.C2, x.C3, x.C4), (x.H1, x.H2, x.H3, x.H4) = x.C[:4], x.H[:4]
    gi = {gc.name: pick(gc.cmd({"cmd": "give_items", "item": ROCKET, "count": 10}), "ok", "stored", "error") for gc in (c, h)}
    ok, p = wait_until(lambda: (lambda ph, pc: (ph, pc) if sorted(ph.get("transformations") or []) == sorted(RULES)
                                and sorted(pc.get("transformations") or []) == sorted(RULES)
                                and view(ph, x.ids) == view(pc, x.ids) else None)(tp(h), tp(c)), 5.0, 0.25)
    info = {"seats": x.seat, "base": base, "C": x.C, "H": x.H, "C1..C4": x.C[:4], "H1..H4": x.H[:4], "give_items": gi,
            "owners": {s["id"]: s["owner"] for s in sols}, "names": {s["id"]: s.get("name") for s in sols}}
    if not (ok and all(v.get("ok") for v in gi.values())):
        raise RuntimeError(f"boot guard (four rules on both, probes equal): {info}; probes {p}")
    info["transformations"], info["funds"], info["rockets"] = p[0]["transformations"], p[0]["funds"], rockets(p[0])
    return info

def boot_b():
    tag, (hp, cp, lp) = BOOT_B
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", mods=(MOD,)))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client", mods=(MOD,)))
    try:
        for f in (host.spawn, client.spawn, host.connect, client.connect):
            f()
        session.new_campaign(host, client, port=str(lp), campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))

def boot(tag, up, setup, rows, results, walls, tail=False):
    t0, js, info, x = time.time(), None, None, None
    try:
        js = up()
        x = SimpleNamespace(host=js.host, client=js.client)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        info = setup(x)
        print(f"EVIDENCE boot {tag}: {json.dumps(info, sort_keys=True, default=str)}", flush=True)
    except Exception as e:
        print(f"CAPTURE {tag} (boot miss): {short(e, 6000)}", flush=True)
        for rid, _fn in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
    try:
        for rid, fn in (rows if info is not None else ()):
            run_one(rid, fn, x, results)
        if info is not None and tail:
            time.sleep(TAIL_S)      # the last row's repair restream, if any (EVIDENCE only)
            print(f"EVIDENCE {tag} tail: {json.dumps({'requests': {gc.name: rs(gc)['requests'] for gc in (x.host, x.client)}})}",
                  flush=True)
    finally:
        try:
            js is not None and js.shutdown()
        except Exception as e:
            print(f"[w2h16c] {tag} shutdown: {short(e)}", flush=True)
        walls[tag] = round(time.time() - t0, 1)

ROWS_A = (("H16c-1", row_1), ("H16c-2", row_2), ("H16c-3", row_3), ("H16c-4", row_4), ("H16c-5", row_5), ("H16c-6", row_6),
          ("H16c-7", row_7), ("H16c-8", row_8), ("H16c-9", row_9), ("H16c-10", row_10))
ROWS_B = (("H16c-11", row_11),)

def main():
    t0, results, walls = time.time(), {}, {}
    boot(BOOT_A[0], lambda: shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], mods=(MOD,)), setup_a, ROWS_A, results, walls,
         tail=True)
    boot(BOOT_B[0], boot_b, lambda x: {"mods": [os.path.basename(MOD)]}, ROWS_B, results, walls)
    failed, n = [rid for rid, _ in ROWS_A + ROWS_B if not results.get(rid)], len(ROWS_A + ROWS_B)
    print(f"\ntest_w2_soldier_transformation: {n - len(failed)}/{n} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
