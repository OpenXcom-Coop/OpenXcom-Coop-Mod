"""W2-H16d (#65 playtest rule; owner D226 a; spec rewrite/prompts/w2h16d_shared_list_order.md (f) + ORCHESTRATOR RULINGS;
TASK 0 rewrite/w2h16d-task0/CONSTANTS.md): in a SHARED campaign the base strip, the craft list, the soldier sort boxes and
arrows and the research arrows must not reorder a shared list on one machine only (SHARED commands address a base by its
index, F6397). Boot A (SHARED; 49331/49332, lobby 47310): S0 (SharedBase2 built, research P1 / P2 started, both machines'
four orders equal) + H16d-1..6, H16d-8 (last: it reorders and renames bases). H16d-7 (ORIGINAL ORDER after an arrival) is
DROPPED (R-H16d-T0-1: the host clock stops while the client sits in a base screen, F6961; the restore fences stand on
reading). Boot B (SEPARATE; 49333/49334, lobby 47312): H16d-9 (guard row: the vanilla reorders stay local).

Cell rule: ONE click per cell; both machines' order of the list the click targets, read before and polled every 0.25 s for
2 s. GREEN = the clicker's order unchanged and both machines equal at the window end; RED (named) = the clicker's order
changed. "G:" cells are guards (red and green): the other machine's order unchanged at every poll, the craft-list click
guard, the equal sort key on the clicker, every screen reached, the 4 own rows of the SHARED training screens (R-H16d-T0-2:
their arrows swap roster positions at the visible row index, so every cell reads the roster through base_report). The first
guard miss of a row prints ONE CAPTURE (four orders, stacks, list_widgets of the top state, shared_stats). requests == R0
at each row end (STOP-IF 5). Every sort cell uses a key EQUAL for every soldier (SOLDIER TYPE; CRAFT on the crew-armor
screen, the hole of its :193 fence) plus shift: unfenced, the stable sort keeps the order and shift reverses it, so the
order ALWAYS changes, whatever an earlier red row left behind.
Pixels (TASK 0): window = int(base x 2.0), bands 0 (checked against the EQUIP CRAFT click_widget reply), from the unrounded
centre (F5802); list row r: y = rect.y + 8r + 4; arrow buttons 11x8 at rect.x + arrowPos (up) / + 12 (down), centre + 5.5,
arrowPos 238 (training) / 192 (research); ComboBox: the box centre, then dropdown row r at (x + 2 + (w - 17) / 2,
popupY + 3 + 8r + 4), popupY = y + h (below) or y - 86 (above: 10 rows x 8 + 6).
RED on the pre-fix build: H16d-1..6 and H16d-8 fail on their named cells, H16d-9 passes. GREEN: all pass.
ONE run; exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients, LAND_LON, LAND_LAT  # noqa: E402
BOOT_A, BOOT_B = ("w2h16da", (49331, 49332, 47310)), ("w2h16db", (49333, 49334), "47312")
HB, SB2, CB, RENAME = "HostBase", "SharedBase2", "ClientBase", "H16D"
H, C, GEO = "host", "client", "GeoscapeState"
SCALE, POLL_S, POLL_I, POPUP_H, OWN_ROWS = 2.0, 2.0, 0.25, 10 * 8 + 3 * 2, 4
ROW_SS_TYPE, ROW_CAS_CRAFT, ROW_ALLOC_TYPE = 4, 3, 3      # dropdown rows: SOLDIER TYPE / CRAFT / SOLDIER TYPE (TASK 0)
ARROW_TRAINING, ARROW_RESEARCH = 238, 192                 # setArrowColumn: ATS :187, APS :175 / RS :104
ALLOC = {"martial": "AllocateTrainingState", "psi": "AllocatePsiTrainingState"}
SS_KEYS = ("cmd", "okCount", "failCount", "applyCount", "applyQueued", "lastFail")
ORDER = ["H16d-1", "H16d-2", "H16d-3", "H16d-4", "H16d-5", "H16d-6", "H16d-8", "H16d-9"]
short = lambda e, n=600: (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E731
class Miss(Exception):  # a blocking guard missed: the row stops
    pass
def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead socket is evidence, not a test error
        return {"error": short(e, 160)}
def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:
        return ["<get_state: %s>" % short(e, 120)]
top = lambda gc: (stack(gc) or [""])[-1]  # noqa: E731
req = lambda gc: q(gc, {"cmd": "shared_resync_stats"}).get("requests")  # noqa: E731
sstats = lambda gc: {k: v for k, v in q(gc, {"cmd": "shared_stats"}).items() if k in SS_KEYS}  # noqa: E731
def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v
        time.sleep(interval)
def bases(gc):
    g = q(gc, {"cmd": "geo_state"})
    return [b["name"] for b in g["bases"]] if g.get("bases") else "<geo_state %s>" % g.get("error")
def crafts(gc):
    g = q(gc, {"cmd": "geo_state"})
    if not g.get("bases"):
        return "<geo_state %s>" % g.get("error")
    return ["%s-%d" % (k["type"].replace("STR_", ""), k["id"]) for k in g["bases"][0].get("crafts", [])]
def research(gc):
    g = q(gc, {"cmd": "geo_state"})
    return [p["name"] for p in g["bases"][0].get("research", [])] if g.get("bases") else "<geo_state %s>" % g.get("error")
def soldiers(gc, base):
    s = q(gc, {"cmd": "base_report", "base": base}).get("soldiers")
    return s if isinstance(s, list) else None
def roster(gc, base):
    s = soldiers(gc, base)
    return [k["id"] for k in s] if s is not None else "<base_report %s>" % base
def widgets(gc):
    r = q(gc, {"cmd": "list_widgets"})
    return r.get("state"), [{"t": (w.get("type") or "").split("::")[-1], "rect": [w["x"], w["y"], w["w"], w["h"]],
                             "vis": w.get("visible"), "text": w.get("text")} for w in r.get("widgets", [])]
class X:
    def __init__(self, host, client, base):
        self.host, self.client, self.base, self.R0, self.P = host, client, base, {}, []
    def other(self, gc):
        return self.client if gc is self.host else self.host
    def roster(self, gc):
        return roster(gc, self.base[gc.name])
    def orders(self, gc):
        return {"bases": bases(gc), "crafts": crafts(gc), "research": research(gc), "roster": self.roster(gc)}
def capture(tag, x, why):
    cap = {}
    for gc in (x.host, x.client):
        try:
            st, ws = widgets(gc)
            cap[gc.name] = {"orders": x.orders(gc), "stack": stack(gc), "shared_stats": sstats(gc),
                            "list_widgets": [st] + [[w["t"], w["rect"], w["vis"], w["text"]] for w in ws if w["t"] != "Text"]}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
class Row:
    def __init__(self, rid, x):
        self.rid, self.x, self.ev, self.fails, self.passed, self.captured = rid, x, {}, [], [], False
    def cell(self, name, ok, detail=""):
        (self.passed if ok else self.fails).append(name if ok else f"{name}: {detail}")
        if not ok and name.startswith("G:") and not self.captured:   # FIXTURE-STOP dump (STOP-IF 3)
            self.captured = True
            capture(self.rid, self.x, name)
        return ok
    def need(self, name, ok, detail=""):
        if not self.cell(name, ok, detail):
            raise Miss(name)
    def report(self, results):
        self.ev["cellsPassed"] = self.passed
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else
              f"FAIL {self.rid}: {len(self.fails)} cell(s): " + " | ".join(self.fails), flush=True)

# --------------------------------------------------------------------------- input and screens
def click(gc, bx, by, button="left", mod=None):
    wx, wy = int(bx * SCALE), int(by * SCALE)
    gc.ok(dict({"cmd": "inject_input", "kind": "click", "x": wx, "y": wy, "button": button}, **({"mod": mod} if mod else {})))
    return [bx, by, wx, wy, button, mod]
def wait_top(r, gc, name, tag, timeout=5.0):
    r.need(f"G:{tag} {gc.name} {name}", wait_until(lambda: top(gc) == name, timeout), stack(gc))
def one(r, gc, kind, tag):
    st, ws = widgets(gc)
    hits = [w["rect"] for w in ws if w["t"] == kind and w["vis"]]
    r.need(f"G:{tag} {gc.name} one {kind}", len(hits) == 1, [st, hits])
    r.ev[f"{tag} {gc.name} {kind} rect"] = hits[0]
    return hits[0]
def close(r, gc, tag):
    q(gc, {"cmd": "close_screens"})
    r.need(f"G:{tag} {gc.name} closed", wait_until(lambda: top(gc) == GEO, 5.0), stack(gc))
def open_screen(r, gc, tag, screen, top_state, **kv):
    rep = q(gc, dict({"cmd": "open_screen", "screen": screen}, **kv))
    r.need(f"G:{tag} {gc.name} open_screen {screen}", rep.get("ok"), rep)
    wait_top(r, gc, top_state, tag)
def equip_craft(r, gc, tag):
    """basescape (first base) -> EQUIP CRAFT (click_widget; its reply checks SCALE) -> CraftsState; the TextList rect."""
    open_screen(r, gc, tag, "basescape", "BasescapeState")
    st, ws = widgets(gc)
    b = [w["rect"] for w in ws if (w["text"] or "").upper() == "EQUIP CRAFT"]
    r.need(f"G:{tag} {gc.name} one EQUIP CRAFT", len(b) == 1, [st, b])
    cx, cy = b[0][0] + b[0][2] / 2.0, b[0][1] + b[0][3] / 2.0
    cw = q(gc, {"cmd": "click_widget", "match": "EQUIP CRAFT"})
    r.need(f"G:{tag} {gc.name} scale {SCALE} bands 0", cw.get("ok") and [cw.get("winX"), cw.get("winY")] ==
           [int(cx * SCALE), int(cy * SCALE)], cw)
    wait_top(r, gc, "CraftsState", tag)
    return one(r, gc, "TextList", tag)
def open_alloc(r, gc, kind, tag):
    rep = q(gc, {"cmd": "open_alloc_screen", "kind": kind})
    r.need(f"G:{tag} {gc.name} open_alloc_screen {kind}", rep.get("ok"), rep)
    wait_top(r, gc, ALLOC[kind], tag)
    p = wait_until(lambda: (lambda v: v if v.get("rows") or v.get("error") else None)(
        q(gc, {"cmd": "alloc_screen_probe"})), 3.0) or {}
    rows = [w.get("soldierId") for w in p.get("rows", [])]
    r.ev[f"{tag} {gc.name} {kind} rows [listing, ids]"] = [p.get("listing"), rows]
    r.need(f"G:{tag} {gc.name} {OWN_ROWS} own rows", p.get("ok") and p.get("listing") == "own" and len(rows) == OWN_ROWS, p)
    return one(r, gc, "TextList", tag)

# --------------------------------------------------------------------------- cells
def cell(x, r, name, gc, probe, act, red, shift=False, expect_change=False):
    """ONE click (spec (f) cell rule): `probe(machine)` = the list the click targets."""
    o = x.other(gc)
    b = {m.name: probe(m) for m in (x.host, x.client)}
    r.ev[name + " click [bx, by, wx, wy, button, mod]"] = act()
    t0, t_ch, seen = time.time(), None, []
    while True:
        a = {m.name: probe(m) for m in (x.host, x.client)}
        if t_ch is None and a[gc.name] != b[gc.name]:
            t_ch = round(time.time() - t0, 2)
        if a[o.name] != b[o.name] and a[o.name] not in seen:
            seen.append(a[o.name])
        if time.time() - t0 >= POLL_S:
            break
        time.sleep(POLL_I)
    if shift:   # the latch is cleared after the window (TASK 0: consumed within 0.05 s)
        q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    r.ev[name] = {"before": b, "after": a, "tChange": t_ch}
    r.cell(f"G:{name}: {o.name} unchanged", not seen, f"{o.name} {b[o.name]} -> {seen}")
    if expect_change:   # H16d-9: SEPARATE keeps the vanilla reorder
        return r.cell(name, a[gc.name] != b[gc.name], f"the {gc.name}'s order did not change in SEPARATE: {a[gc.name]}")
    if a[gc.name] != b[gc.name]:
        return r.cell(name, False, f"{red}: {gc.name} {b[gc.name]} -> {a[gc.name]}")
    return r.cell(name, a[H] == a[C], f"orders differ: host {a[H]} client {a[C]}")
def sort_cell(x, r, name, gc, row, above, key, red, expect_change=False):
    """The top state's ONE ComboBox: the box, 0.3 s, then dropdown row `row` with shift (equal key: a pure reversal)."""
    sol = soldiers(gc, x.base[gc.name]) or []
    vals = sorted(set(str(s.get(key)) for s in sol))
    r.ev[f"{name} key {key}"] = [len(sol), vals]
    r.need(f"G:{name}: equal {key} key on the {gc.name}", len(sol) > 1 and len(vals) == 1, f"{key} {vals} over {len(sol)}")
    bx, by, bw, bh = one(r, gc, "ComboBox", name)
    py = by - POPUP_H if above else by + bh
    box, pick = (bx + bw / 2.0, by + bh / 2.0), (bx + 2 + (bw - 17) / 2.0, py + 3 + 8 * row + 4)
    r.ev[f"{name} dropdown [popupY, row]"] = [py, row]
    def act():
        k = click(gc, *box)
        time.sleep(0.3)
        return [k, click(gc, *pick, mod="shift")]
    return cell(x, r, name, gc, x.roster, act, red, shift=True, expect_change=expect_change)
def arrow(x, r, name, gc, L, pos, row, down, red, probe=None):
    p = (L[0] + pos + (12 if down else 0) + 5.5, L[1] + 8 * row + 4)
    return cell(x, r, name, gc, probe or x.roster, lambda: click(gc, *p), red)

# --------------------------------------------------------------------------- Boot A rows
def h1(x, r):   # craft list: right-click (client, row 1) and shift+right-click (host, row 0)
    h, c = x.host, x.client
    for gc, row, mod, n, o in ((c, 1, None, "H16d-1a client right-click craft row 1", "O-2a"),
                               (h, 0, "shift", "H16d-1b host shift+right-click craft row 0", "O-2b")):
        L = equip_craft(r, gc, n[:7])
        p = (L[0] + L[2] / 2.0, L[1] + 8 * row + 4)
        cell(x, r, n, gc, crafts, lambda: click(gc, *p, button="right", mod=mod),
             f"the {gc.name}'s craft list reordered on its machine only ({o})", shift=bool(mod))
        click(gc, *p)   # the click guard: a left-click on the same row opens the craft
        r.need(f"G:{n[:7]} {gc.name} click guard CraftInfoState", wait_until(lambda: top(gc) == "CraftInfoState", 3.0), stack(gc))
        close(r, gc, n[:7])
def h2(x, r):   # soldier-list sort box (client)
    c = x.client
    open_screen(r, c, "H16d-2", "soldiers", "SoldiersState")
    sort_cell(x, r, "H16d-2 client soldier list SOLDIER TYPE + shift", c, ROW_SS_TYPE, False, "type",
              "the client's soldier-list sort reordered the shared roster on its machine only (O-3a)")
    close(r, c, "H16d-2")
def h3(x, r):   # crew-armor sort box, CRAFT (selIdx 3: inside the hole of the :193 fence) (host)
    h = x.host
    open_screen(r, h, "H16d-3", "craft_armor", "CraftArmorState", craft_id=1)
    sort_cell(x, r, "H16d-3 host crew-armor CRAFT + shift", h, ROW_CAS_CRAFT, True, "craft",
              "the host's crew-armor CRAFT sort reordered the shared roster on its machine only (O-3d)")
    close(r, h, "H16d-3")
def h4(x, r):   # martial training: arrows (client), sort box (host)
    h, c = x.host, x.client
    L = open_alloc(r, c, "martial", "H16d-4a")
    arrow(x, r, "H16d-4a client martial row 0 DOWN arrow", c, L, ARROW_TRAINING, 0, True,
          "the client's martial arrow reordered the shared roster on its machine only (O-3g)")
    arrow(x, r, "H16d-4b client martial row 1 UP arrow", c, L, ARROW_TRAINING, 1, False,
          "the client's martial arrow reordered the shared roster on its machine only (O-3g)")
    close(r, c, "H16d-4b")
    open_alloc(r, h, "martial", "H16d-4c")
    sort_cell(x, r, "H16d-4c host martial SOLDIER TYPE + shift", h, ROW_ALLOC_TYPE, True, "type",
              "the host's martial sort reordered the shared roster on its machine only (O-3f)")
    close(r, h, "H16d-4c")
def h5(x, r):   # psi training: arrow + sort box (client), arrow (host)
    h, c = x.host, x.client
    L = open_alloc(r, c, "psi", "H16d-5a")
    arrow(x, r, "H16d-5a client psi row 1 UP arrow", c, L, ARROW_TRAINING, 1, False,
          "the client's psi arrow reordered the shared roster on its machine only (O-3i)")
    sort_cell(x, r, "H16d-5b client psi SOLDIER TYPE + shift", c, ROW_ALLOC_TYPE, True, "type",
              "the client's psi sort reordered the shared roster on its machine only (O-3h)")
    close(r, c, "H16d-5b")
    L = open_alloc(r, h, "psi", "H16d-5c")
    arrow(x, r, "H16d-5c host psi row 0 DOWN arrow", h, L, ARROW_TRAINING, 0, True,
          "the host's psi arrow reordered the shared roster on its machine only (O-3i)")
    close(r, h, "H16d-5c")
def h6(x, r):   # research arrows: client row 0 DOWN, host row 1 UP
    h, c = x.host, x.client
    r.need("G:H16d-6 research [P1, P2] on both", research(h) == x.P and research(c) == x.P,
           {H: research(h), C: research(c), "P": x.P})
    for gc, row, down, n in ((c, 0, True, "H16d-6a client research row 0 DOWN arrow"),
                             (h, 1, False, "H16d-6b host research row 1 UP arrow")):
        open_screen(r, gc, n[:7], "research", "ResearchState")
        L = one(r, gc, "TextList", n[:7])
        arrow(x, r, n, gc, L, ARROW_RESEARCH, row, down,
              f"the {gc.name}'s research list reordered on its machine only (O-4)", probe=research)
        close(r, gc, n[:7])
def h8(x, r):   # base strip (client) + a command by index (LAST in Boot A)
    h, c = x.host, x.client
    r.need("G:H16d-8 bases [HostBase, SharedBase2] on both", bases(h) == [HB, SB2] and bases(c) == [HB, SB2],
           {H: bases(h), C: bases(c)})
    open_screen(r, c, "H16d-8a", "basescape", "BasescapeState", base=SB2)
    m = one(r, c, "MiniBaseView", "H16d-8a")
    p = (m[0] + 24, m[1] + 8)   # MiniBaseView slot 1 centre (test_w2_old_bases MINI_SLOT1_CENTRE)
    cell(x, r, "H16d-8a client right-click base-strip slot 1", c, bases, lambda: click(c, *p, button="right"),
         "the base list reordered on the client only (O-1)")
    r.ev["H16d-8a selectedBase"] = {g.name: q(g, {"cmd": "geo_state"}).get("selectedBase") for g in (h, c)}
    close(r, c, "H16d-8a")
    rep = q(c, {"cmd": "base_rename", "base": SB2, "name": RENAME})
    r.need("G:H16d-8b client base_rename", rep.get("ok"), rep)
    time.sleep(POLL_S)
    a, want = {g.name: bases(g) for g in (h, c)}, [HB, RENAME]
    r.ev["H16d-8b bases after the client's rename of SharedBase2 (2 s)"] = a
    n = "H16d-8b client renames SharedBase2"
    if a[H] == [RENAME, SB2] and a[C] == [RENAME, HB]:
        r.cell(n, False, f"the client's rename of SharedBase2 renamed the host's HostBase (F6397): host {a[H]} client {a[C]}")
    else:
        r.cell(n, a[H] == want and a[C] == want, f"bases host {a[H]} client {a[C]} != {want} on both")

# --------------------------------------------------------------------------- Boot B row
def h9(x, r):   # SEPARATE keeps vanilla: the client's own roster and craft order change; nothing goes over the wire
    h, c = x.host, x.client
    ss0 = {g.name: sstats(g) for g in (h, c)}
    r.ev["H16d-9 shared_stats before"] = ss0
    open_screen(r, c, "H16d-9a", "soldiers", "SoldiersState")
    sort_cell(x, r, "H16d-9a client soldier list SOLDIER TYPE + shift (SEPARATE)", c, ROW_SS_TYPE, False, "type", "",
              expect_change=True)
    close(r, c, "H16d-9a")
    L = equip_craft(r, c, "H16d-9b")
    p = (L[0] + L[2] / 2.0, L[1] + 8 * 1 + 4)
    cell(x, r, "H16d-9b client right-click craft row 1 (SEPARATE)", c, crafts, lambda: click(c, *p, button="right"), "",
         expect_change=True)
    close(r, c, "H16d-9b")
    ss1 = {g.name: sstats(g) for g in (h, c)}
    r.ev["H16d-9 shared_stats after"] = ss1
    r.cell("H16d-9c shared_stats unchanged on both", ss1 == ss0, f"{ss0} -> {ss1}")

# --------------------------------------------------------------------------- boots
def s0(x):
    """Boot A S0 (TASK 0 (i)): SharedBase2 through build_new_base, P1 / P2 through res_start, the four orders equal."""
    h, c = x.host, x.client
    h.ok({"cmd": "build_new_base", "lon": LAND_LON + 0.03, "lat": LAND_LAT + 0.03, "name": SB2})
    if not wait_until(lambda: bases(h) == [HB, SB2] and bases(c) == [HB, SB2], 30.0, 0.1):
        raise RuntimeError(f"S0 bases host {bases(h)} client {bases(c)} != [HostBase, SharedBase2]")
    if not wait_until(lambda: top(h) == GEO, 10.0):
        raise RuntimeError(f"S0 host top {stack(h)} after build_new_base")
    h.ok({"cmd": "open_screen", "screen": "new_research"})
    projects = q(h, {"cmd": "screen_state"}).get("projects") or []
    h.ok({"cmd": "close_screens"})
    if len(projects) < 2 or not wait_until(lambda: top(h) == GEO, 5.0):
        raise RuntimeError(f"S0 new_research projects {projects}, host {stack(h)}")
    x.P = projects[:2]
    for p in x.P:
        h.ok({"cmd": "shared_cmd", "jcmd": "res_start", "baseId": 0, "payload": {"project": p}})
    if not wait_until(lambda: research(h) == x.P and research(c) == x.P, 30.0, 0.1):
        raise RuntimeError(f"S0 research host {research(h)} client {research(c)} != {x.P}")
    o = {g.name: x.orders(g) for g in (h, c)}
    x.R0 = {g.name: req(g) for g in (h, c)}
    print(f"EVIDENCE S0: {json.dumps({'orders': o, 'P': x.P, 'R0': x.R0}, sort_keys=True)}", flush=True)
    if o[H] != o[C]:
        raise RuntimeError("S0 orders differ (guard)")
def up_a():
    js = shared_fixture.bring_up(*BOOT_A)
    return X(js.host, js.client, {H: HB, C: HB}), js.shutdown
def up_b():
    host = GameClient(H, BOOT_B[1][0], make_user_dir(BOOT_B[0] + "_host"))
    client = GameClient(C, BOOT_B[1][1], make_user_dir(BOOT_B[0] + "_client"))
    try:
        host.spawn()
        client.spawn()
        host.connect()
        client.connect()
        session.new_campaign(host, client, port=BOOT_B[2], campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    x = X(host, client, {H: HB, C: CB})
    x.R0 = {g.name: req(g) for g in (host, client)}
    return x, lambda: shutdown_clients(host, client)
def run_row(rid, fn, x, results, walls):
    r, t0 = Row(rid, x), time.time()
    try:
        fn(x, r)
    except Miss:
        pass
    except Exception as e:
        r.cell(f"G:{rid} exception", False, short(e))
    for g in (x.host, x.client):   # a stopped row leaves no screen behind
        if top(g) != GEO:
            q(g, {"cmd": "close_screens"})
            wait_until(lambda: top(g) == GEO, 5.0)
    now = {g.name: req(g) for g in (x.host, x.client)}
    r.cell(f"G:{rid} requests == R0", now == x.R0, f"requests {now} vs R0 {x.R0} (STOP-IF 5)")
    walls[rid] = round(time.time() - t0, 1)
    r.report(results)
def boot(results, walls, tag, rows, up, setup=None):
    t0, x, kill = time.time(), None, None
    try:
        x, kill = up()
        walls[f"boot {tag}"] = round(time.time() - t0, 1)
        if setup:
            t1 = time.time()
            setup(x)
            walls[f"S0 {tag}"] = round(time.time() - t1, 1)
    except Exception as e:   # a boot miss fails its rows "boot" with ONE CAPTURE line
        print(f"CAPTURE boot {tag} (boot miss): {short(e, 1500)}", flush=True)
        if x is not None:
            capture(f"boot {tag}", x, "boot miss")
        for rid, _ in rows:
            results[rid] = False
            print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
        if kill:
            kill()
        return
    try:
        for rid, fn in rows:
            run_row(rid, fn, x, results, walls)
    finally:
        t1 = time.time()
        kill()
        walls[f"shutdown {tag}"] = round(time.time() - t1, 1)
def main():
    t0, results, walls = time.time(), {}, {}
    boot(results, walls, "A", [("H16d-1", h1), ("H16d-2", h2), ("H16d-3", h3), ("H16d-4", h4), ("H16d-5", h5),
                               ("H16d-6", h6), ("H16d-8", h8)], up_a, s0)
    boot(results, walls, "B", [("H16d-9", h9)], up_b)
    failed = [rid for rid in ORDER if not results.get(rid)]
    print(f"\ntest_w2_shared_list_order: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0
if __name__ == "__main__":
    sys.exit(main())
