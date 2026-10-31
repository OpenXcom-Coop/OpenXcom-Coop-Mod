"""In a SHARED campaign both players play one world, so a reorder control either changes a shared list on both
machines through the host or leaves it alone (issue #65; SHARED commands address a base by its index). Boot shared
(SHARED; 49331/49332, lobby 47310): the setup (SharedBase2 built, research P1 / P2 started, both machines' four orders
equal), then craft_list, soldier_sort, crew_armor_sort, martial_training, psi_training, research_arrows and base_strip
(last: it reorders and renames bases). The craft list, the training screens and the research arrows leave the shared
order alone. The soldier-list sort and the crew-armor sort reorder the clicking player's own soldiers among the places
they already hold, through the host, on both machines; the partner's soldiers keep their places. The base strip moves
the selected base one place left on both machines, so a later command that names a base by its index reaches the same
base on both. There is no ORIGINAL ORDER row after an arrival: the host clock stops while the client sits in a base
screen, so the test cannot stage one. Boot separate (SEPARATE; 49333/49334, lobby 47312): separate_reorders (guard row:
the client's soldier sort goes through the host as one command, its craft list still reorders).

Cell rule: ONE click per cell; both machines' order of the list the click targets, read before and polled every 0.25 s
for 2 s. A "leave alone" cell passes when the clicker's order is unchanged and both machines are equal at the window
end; it fails with its named message when the clicker's order changed. A "both machines" cell passes when both
machines hold the expected order at the window end; its partner cell fails when a partner's soldier left its place at
any poll. "guard:" cells are guards: the other machine's order unchanged at every poll (leave alone cells), the
craft-list click guard, the equal sort key on the clicker, one roster on both machines before a sort, every screen
reached, the 4 own rows of the SHARED training screens (every cell reads the roster through base_report). The first
guard miss of a row prints ONE CAPTURE (four orders, stacks, list_widgets of the top state, shared_stats).
requests == R0 at each row end. Every sort cell uses a key EQUAL for every soldier (SOLDIER TYPE; CRAFT on the
crew-armor screen) plus shift: a sort that runs keeps the order and shift reverses it, so it ALWAYS reverses the
clicker's own soldiers, whatever an earlier row left behind.
Pixels: window = int(base x 2.0), bands 0 (checked against the EQUIP CRAFT click_widget reply), from the unrounded
centre; list row r: y = rect.y + 8r + 4; arrow buttons 11x8 at rect.x + arrowPos (up) / + 12 (down), centre + 5.5,
arrowPos 238 (training) / 192 (research); ComboBox: the box centre, then dropdown row r at (x + 2 + (w - 17) / 2,
popupY + 3 + 8r + 4), popupY = y + h (below) or y - 86 (above: 10 rows x 8 + 6).
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
BOOT_SHARED, BOOT_SEPARATE = (("list_order_shared", (49331, 49332, 47310)),
                              ("list_order_separate", (49333, 49334), "47312"))
HB, SB2, CB, RENAME = "HostBase", "SharedBase2", "ClientBase", "Renamed"
H, C, GEO = "host", "client", "GeoscapeState"
SEAT = {H: 0, C: 1}                                       # the owner seat a soldier carries (base_report "owner")
SCALE, POLL_S, POLL_I, POPUP_H, OWN_ROWS = 2.0, 2.0, 0.25, 10 * 8 + 3 * 2, 4
ROW_SS_TYPE, ROW_CAS_CRAFT, ROW_ALLOC_TYPE = 4, 3, 3      # dropdown rows: SOLDIER TYPE / CRAFT / SOLDIER TYPE
ARROW_TRAINING, ARROW_RESEARCH = 238, 192                 # setArrowColumn: ATS :187, APS :175 / RS :104
ALLOC = {"martial": "AllocateTrainingState", "psi": "AllocatePsiTrainingState"}
SS_KEYS = ("cmd", "okCount", "failCount", "applyCount", "applyQueued", "lastFail")
ORDER = ["craft_list", "soldier_sort", "crew_armor_sort", "martial_training", "psi_training", "research_arrows",
         "base_strip", "separate_reorders"]
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
def owned(gc, base):
    """The base roster as [id, owner seat] pairs."""
    s = soldiers(gc, base)
    return [[k["id"], k.get("owner")] for k in s] if s is not None else "<base_report %s>" % base
def crafts_at(gc, base):
    g = q(gc, {"cmd": "geo_state"})
    for b in g.get("bases") or []:
        if b["name"] == base:
            return ["%s-%d" % (k["type"].replace("STR_", ""), k["id"]) for k in b.get("crafts", [])]
    return "<geo_state %s: no base %s>" % (g.get("error"), base)
def reversed_own(order, seat):
    """`order` after the soldiers of `seat` reverse among the places they hold; every other soldier keeps its place."""
    places = [i for i, s in enumerate(order) if s[1] == seat]
    out = list(order)
    for i, s in zip(places, [order[i] for i in reversed(places)]):
        out[i] = s
    return out
def partner_places(order, seat):
    return [[i] + s for i, s in enumerate(order) if s[1] != seat] if isinstance(order, list) else order
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
        if not ok and name.startswith("guard:") and not self.captured:   # setup-failure dump
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
    r.need(f"guard:{tag} {gc.name} {name}", wait_until(lambda: top(gc) == name, timeout), stack(gc))
def one(r, gc, kind, tag):
    st, ws = widgets(gc)
    hits = [w["rect"] for w in ws if w["t"] == kind and w["vis"]]
    r.need(f"guard:{tag} {gc.name} one {kind}", len(hits) == 1, [st, hits])
    r.ev[f"{tag} {gc.name} {kind} rect"] = hits[0]
    return hits[0]
def close(r, gc, tag):
    q(gc, {"cmd": "close_screens"})
    r.need(f"guard:{tag} {gc.name} closed", wait_until(lambda: top(gc) == GEO, 5.0), stack(gc))
def open_screen(r, gc, tag, screen, top_state, **kv):
    rep = q(gc, dict({"cmd": "open_screen", "screen": screen}, **kv))
    r.need(f"guard:{tag} {gc.name} open_screen {screen}", rep.get("ok"), rep)
    wait_top(r, gc, top_state, tag)
def equip_craft(r, gc, tag):
    """basescape (first base) -> EQUIP CRAFT (click_widget; its reply checks SCALE) -> CraftsState; the TextList rect."""
    open_screen(r, gc, tag, "basescape", "BasescapeState")
    st, ws = widgets(gc)
    b = [w["rect"] for w in ws if (w["text"] or "").upper() == "EQUIP CRAFT"]
    r.need(f"guard:{tag} {gc.name} one EQUIP CRAFT", len(b) == 1, [st, b])
    cx, cy = b[0][0] + b[0][2] / 2.0, b[0][1] + b[0][3] / 2.0
    cw = q(gc, {"cmd": "click_widget", "match": "EQUIP CRAFT"})
    r.need(f"guard:{tag} {gc.name} scale {SCALE} bands 0", cw.get("ok") and [cw.get("winX"), cw.get("winY")] ==
           [int(cx * SCALE), int(cy * SCALE)], cw)
    wait_top(r, gc, "CraftsState", tag)
    return one(r, gc, "TextList", tag)
def open_alloc(r, gc, kind, tag):
    rep = q(gc, {"cmd": "open_alloc_screen", "kind": kind})
    r.need(f"guard:{tag} {gc.name} open_alloc_screen {kind}", rep.get("ok"), rep)
    wait_top(r, gc, ALLOC[kind], tag)
    p = wait_until(lambda: (lambda v: v if v.get("rows") or v.get("error") else None)(
        q(gc, {"cmd": "alloc_screen_probe"})), 3.0) or {}
    rows = [w.get("soldierId") for w in p.get("rows", [])]
    r.ev[f"{tag} {gc.name} {kind} rows [listing, ids]"] = [p.get("listing"), rows]
    r.need(f"guard:{tag} {gc.name} {OWN_ROWS} own rows", p.get("ok") and p.get("listing") == "own" and len(rows) == OWN_ROWS, p)
    return one(r, gc, "TextList", tag)

# --------------------------------------------------------------------------- cells
def cell(x, r, name, gc, probe, act, reorder_msg, shift=False, expect_change=False):
    """ONE click (the cell rule): `probe(machine)` = the list the click targets."""
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
    if shift:   # the latch is cleared after the window (measured: consumed within 0.05 s)
        q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    r.ev[name] = {"before": b, "after": a, "tChange": t_ch}
    if expect_change:   # separate_reorders: the SEPARATE craft list keeps its reorder (the other machine: evidence only)
        return r.cell(name, a[gc.name] != b[gc.name], f"the {gc.name}'s order did not change in SEPARATE: {a[gc.name]}")
    r.cell(f"guard:{name}: {o.name} unchanged", not seen, f"{o.name} {b[o.name]} -> {seen}")
    if a[gc.name] != b[gc.name]:
        return r.cell(name, False, f"{reorder_msg}: {gc.name} {b[gc.name]} -> {a[gc.name]}")
    return r.cell(name, a[H] == a[C], f"orders differ: host {a[H]} client {a[C]}")
def both_cell(x, r, name, gc, probe, act, want, msg, keep=None, shift=False):
    """ONE click whose change goes through the host: both machines must hold `want` at the window end, and `keep(order)`
    (the partner's soldiers with their places) must stay as it was before the click on both machines at every poll."""
    b = {m.name: probe(m) for m in (x.host, x.client)}
    r.ev[name + " click [bx, by, wx, wy, button, mod]"] = act()
    t0, t_ch, moved = time.time(), {}, []
    while True:
        a = {m.name: probe(m) for m in (x.host, x.client)}
        for m in (x.host, x.client):
            if m.name not in t_ch and a[m.name] != b[m.name]:
                t_ch[m.name] = round(time.time() - t0, 2)
            if keep and keep(a[m.name]) != keep(b[m.name]) and [m.name, a[m.name]] not in moved:
                moved.append([m.name, a[m.name]])
        if time.time() - t0 >= POLL_S:
            break
        time.sleep(POLL_I)
    if shift:   # the latch is cleared after the window (measured: consumed within 0.05 s)
        q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    r.ev[name] = {"before": b, "after": a, "want": want, "tChange": t_ch}
    if keep:
        r.cell(f"{name}: the partner's soldiers keep their places", not moved, f"moved {moved}")
    return r.cell(name, a[H] == want and a[C] == want, f"{msg}: want {want}, host {a[H]} client {a[C]}")
def sort_cell(x, r, name, gc, row, above, key, reorder_msg, expect_change=False, own=False, partner_min=1):
    """The top state's ONE ComboBox: the box, 0.3 s, then dropdown row `row` with shift (equal key: a pure reversal).
    own: the sort goes through the host and reverses the clicker's own soldiers among their places on both machines
    (both read the clicker's base)."""
    sol = soldiers(gc, x.base[gc.name]) or []
    vals = sorted(set(str(s.get(key)) for s in sol))
    r.ev[f"{name} key {key}"] = [len(sol), vals]
    r.need(f"guard:{name}: equal {key} key on the {gc.name}", len(sol) > 1 and len(vals) == 1, f"{key} {vals} over {len(sol)}")
    bx, by, bw, bh = one(r, gc, "ComboBox", name)
    py = by - POPUP_H if above else by + bh
    box, pick = (bx + bw / 2.0, by + bh / 2.0), (bx + 2 + (bw - 17) / 2.0, py + 3 + 8 * row + 4)
    r.ev[f"{name} dropdown [popupY, row]"] = [py, row]
    def act():
        k = click(gc, *box)
        time.sleep(0.3)
        return [k, click(gc, *pick, mod="shift")]
    if own:
        seat, base = SEAT[gc.name], x.base[gc.name]
        b = {m.name: owned(m, base) for m in (x.host, x.client)}
        mine = sum(1 for s in b[gc.name] if s[1] == seat) if isinstance(b[gc.name], list) else 0
        r.need(f"guard:{name}: one roster on both machines, the {gc.name} owns >= 2, the partner >= {partner_min}",
               b[H] == b[C] and mine >= 2 and len(b[gc.name]) - mine >= partner_min, b)
        return both_cell(x, r, name, gc, lambda m: owned(m, base), act, reversed_own(b[gc.name], seat), reorder_msg,
                         keep=lambda o: partner_places(o, seat), shift=True)
    return cell(x, r, name, gc, x.roster, act, reorder_msg, shift=True, expect_change=expect_change)
def arrow(x, r, name, gc, L, pos, row, down, reorder_msg, probe=None):
    p = (L[0] + pos + (12 if down else 0) + 5.5, L[1] + 8 * row + 4)
    return cell(x, r, name, gc, probe or x.roster, lambda: click(gc, *p), reorder_msg)

# --------------------------------------------------------------------------- boot shared rows
def row_craft_list(x, r):   # craft list: right-click (client, row 1) and shift+right-click (host, row 0)
    h, c = x.host, x.client
    for gc, row, mod, n, o in ((c, 1, None, "craft_client client right-click craft row 1", "right-click"),
                               (h, 0, "shift", "craft_host host shift+right-click craft row 0", "shift+right-click")):
        L = equip_craft(r, gc, n.split(" ")[0])
        p = (L[0] + L[2] / 2.0, L[1] + 8 * row + 4)
        cell(x, r, n, gc, crafts, lambda: click(gc, *p, button="right", mod=mod),
             f"the {gc.name}'s craft list reordered on its machine only ({o})", shift=bool(mod))
        click(gc, *p)   # the click guard: a left-click on the same row opens the craft
        r.need(f"guard:{n.split(' ')[0]} {gc.name} click guard CraftInfoState",
               wait_until(lambda: top(gc) == "CraftInfoState", 3.0), stack(gc))
        close(r, gc, n.split(" ")[0])
def row_soldier_sort(x, r):   # soldier-list sort box (client): its own soldiers, through the host
    c = x.client
    open_screen(r, c, "soldier_sort", "soldiers", "SoldiersState")
    sort_cell(x, r, "soldier_sort client soldier list SOLDIER TYPE + shift", c, ROW_SS_TYPE, False, "type",
              "the client's soldier-list sort did not reverse its own soldiers on both machines", own=True)
    close(r, c, "soldier_sort")
def row_crew_armor_sort(x, r):   # crew-armor sort box, CRAFT (selIdx 3; a stat sort only shows its column) (host)
    h = x.host
    open_screen(r, h, "crew_armor_sort", "craft_armor", "CraftArmorState", craft_id=1)
    sort_cell(x, r, "crew_armor_sort host crew-armor CRAFT + shift", h, ROW_CAS_CRAFT, True, "craft",
              "the host's crew-armor CRAFT sort did not reverse its own soldiers on both machines", own=True)
    close(r, h, "crew_armor_sort")
def row_martial_training(x, r):   # martial training: arrows (client), sort box (host)
    h, c = x.host, x.client
    L = open_alloc(r, c, "martial", "martial_client_down")
    arrow(x, r, "martial_client_down client martial row 0 DOWN arrow", c, L, ARROW_TRAINING, 0, True,
          "the client's martial arrow reordered the shared roster on its machine only")
    arrow(x, r, "martial_client_up client martial row 1 UP arrow", c, L, ARROW_TRAINING, 1, False,
          "the client's martial arrow reordered the shared roster on its machine only")
    close(r, c, "martial_client_up")
    open_alloc(r, h, "martial", "martial_host_sort")
    sort_cell(x, r, "martial_host_sort host martial SOLDIER TYPE + shift", h, ROW_ALLOC_TYPE, True, "type",
              "the host's martial sort reordered the shared roster on its machine only")
    close(r, h, "martial_host_sort")
def row_psi_training(x, r):   # psi training: arrow + sort box (client), arrow (host)
    h, c = x.host, x.client
    L = open_alloc(r, c, "psi", "psi_client_up")
    arrow(x, r, "psi_client_up client psi row 1 UP arrow", c, L, ARROW_TRAINING, 1, False,
          "the client's psi arrow reordered the shared roster on its machine only")
    sort_cell(x, r, "psi_client_sort client psi SOLDIER TYPE + shift", c, ROW_ALLOC_TYPE, True, "type",
              "the client's psi sort reordered the shared roster on its machine only")
    close(r, c, "psi_client_sort")
    L = open_alloc(r, h, "psi", "psi_host_down")
    arrow(x, r, "psi_host_down host psi row 0 DOWN arrow", h, L, ARROW_TRAINING, 0, True,
          "the host's psi arrow reordered the shared roster on its machine only")
    close(r, h, "psi_host_down")
def row_research_arrows(x, r):   # research arrows: client row 0 DOWN, host row 1 UP
    h, c = x.host, x.client
    r.need("guard:research_arrows research [P1, P2] on both", research(h) == x.P and research(c) == x.P,
           {H: research(h), C: research(c), "P": x.P})
    for gc, row, down, n in ((c, 0, True, "research_client_down client research row 0 DOWN arrow"),
                             (h, 1, False, "research_host_up host research row 1 UP arrow")):
        open_screen(r, gc, n.split(" ")[0], "research", "ResearchState")
        L = one(r, gc, "TextList", n.split(" ")[0])
        arrow(x, r, n, gc, L, ARROW_RESEARCH, row, down,
              f"the {gc.name}'s research list reordered on its machine only", probe=research)
        close(r, gc, n.split(" ")[0])
def row_base_strip(x, r):   # base strip (client) + a command by index (LAST in boot shared)
    h, c = x.host, x.client
    r.need("guard:base_strip bases [HostBase, SharedBase2] on both", bases(h) == [HB, SB2] and bases(c) == [HB, SB2],
           {H: bases(h), C: bases(c)})
    open_screen(r, c, "base_strip_client", "basescape", "BasescapeState", base=SB2)
    m = one(r, c, "MiniBaseView", "base_strip_client")
    p = (m[0] + 24, m[1] + 8)   # MiniBaseView slot 1 centre (test_old_bases MINI_SLOT1_CENTRE)
    both_cell(x, r, "base_strip_client client right-click base-strip slot 1", c, bases,
              lambda: click(c, *p, button="right"), [SB2, HB],
              "the base strip did not move SharedBase2 one place left on both machines")
    r.ev["base_strip_client selectedBase"] = {g.name: q(g, {"cmd": "geo_state"}).get("selectedBase") for g in (h, c)}
    close(r, c, "base_strip_client")
    rep = q(c, {"cmd": "base_rename", "base": SB2, "name": RENAME})
    r.need("guard:base_rename_client client base_rename", rep.get("ok"), rep)
    time.sleep(POLL_S)
    a, want = {g.name: bases(g) for g in (h, c)}, [RENAME, HB]
    r.ev["base_rename_client bases after the client's rename of SharedBase2 (2 s)"] = a
    r.cell("base_rename_client client renames SharedBase2", a[H] == want and a[C] == want,
           f"bases host {a[H]} client {a[C]} != {want} on both")

# --------------------------------------------------------------------------- boot separate row
# SEPARATE (one world): the client's soldier sort goes through the host as one command; its craft list still reorders
def row_separate_reorders(x, r):
    h, c = x.host, x.client
    ss0 = {g.name: sstats(g) for g in (h, c)}
    r.ev["separate_reorders shared_stats before"] = ss0
    open_screen(r, c, "separate_soldier_sort", "soldiers", "SoldiersState")
    sort_cell(x, r, "separate_soldier_sort client soldier list SOLDIER TYPE + shift (SEPARATE)", c, ROW_SS_TYPE, False,
              "type", "the client's SEPARATE soldier sort did not reverse its own soldiers on both machines",
              own=True, partner_min=0)
    close(r, c, "separate_soldier_sort")
    L = equip_craft(r, c, "separate_craft_order")
    p = (L[0] + L[2] / 2.0, L[1] + 8 * 1 + 4)
    cell(x, r, "separate_craft_order client right-click craft row 1 (SEPARATE)", c, lambda m: crafts_at(m, CB),
         lambda: click(c, *p, button="right"), "",
         expect_change=True)
    close(r, c, "separate_craft_order")
    ss1 = {g.name: sstats(g) for g in (h, c)}
    r.ev["separate_reorders shared_stats after"] = ss1
    d = {g: {k: ss1[g].get(k, 0) - ss0[g].get(k, 0) for k in ("cmd", "okCount", "failCount")} for g in (H, C)}
    r.cell("separate_one_command the sort is one host command, the craft reorder none",
           d[H]["cmd"] == 1 and all(d[g]["okCount"] == 1 and d[g]["failCount"] == 0 for g in (H, C)),
           f"{ss0} -> {ss1}")

# --------------------------------------------------------------------------- boots
def shared_setup(x):
    """Boot shared setup: SharedBase2 through build_new_base, P1 / P2 through res_start, the four orders equal."""
    h, c = x.host, x.client
    h.ok({"cmd": "build_new_base", "lon": LAND_LON + 0.03, "lat": LAND_LAT + 0.03, "name": SB2})
    if not wait_until(lambda: bases(h) == [HB, SB2] and bases(c) == [HB, SB2], 30.0, 0.1):
        raise RuntimeError(f"setup bases host {bases(h)} client {bases(c)} != [HostBase, SharedBase2]")
    if not wait_until(lambda: top(h) == GEO, 10.0):
        raise RuntimeError(f"setup host top {stack(h)} after build_new_base")
    h.ok({"cmd": "open_screen", "screen": "new_research"})
    projects = q(h, {"cmd": "screen_state"}).get("projects") or []
    h.ok({"cmd": "close_screens"})
    if len(projects) < 2 or not wait_until(lambda: top(h) == GEO, 5.0):
        raise RuntimeError(f"setup new_research projects {projects}, host {stack(h)}")
    x.P = projects[:2]
    for p in x.P:
        h.ok({"cmd": "shared_cmd", "jcmd": "res_start", "baseId": 0, "payload": {"project": p}})
    if not wait_until(lambda: research(h) == x.P and research(c) == x.P, 30.0, 0.1):
        raise RuntimeError(f"setup research host {research(h)} client {research(c)} != {x.P}")
    o = {g.name: x.orders(g) for g in (h, c)}
    x.R0 = {g.name: req(g) for g in (h, c)}
    print(f"EVIDENCE setup: {json.dumps({'orders': o, 'P': x.P, 'R0': x.R0}, sort_keys=True)}", flush=True)
    if o[H] != o[C]:
        raise RuntimeError("setup orders differ (guard)")
def up_shared():
    js = shared_fixture.bring_up(*BOOT_SHARED)
    return X(js.host, js.client, {H: HB, C: HB}), js.shutdown
def up_separate():
    host = GameClient(H, BOOT_SEPARATE[1][0], make_user_dir(BOOT_SEPARATE[0] + "_host"))
    client = GameClient(C, BOOT_SEPARATE[1][1], make_user_dir(BOOT_SEPARATE[0] + "_client"))
    try:
        host.spawn()
        client.spawn()
        host.connect()
        client.connect()
        session.new_campaign(host, client, port=BOOT_SEPARATE[2], campaign_mode="coop")
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
        r.cell(f"guard:{rid} exception", False, short(e))
    for g in (x.host, x.client):   # a stopped row leaves no screen behind
        if top(g) != GEO:
            q(g, {"cmd": "close_screens"})
            wait_until(lambda: top(g) == GEO, 5.0)
    now = {g.name: req(g) for g in (x.host, x.client)}
    r.cell(f"guard:{rid} requests == R0", now == x.R0, f"requests {now} vs R0 {x.R0}")
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
            walls[f"setup {tag}"] = round(time.time() - t1, 1)
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
    boot(results, walls, "shared",
         [("craft_list", row_craft_list), ("soldier_sort", row_soldier_sort), ("crew_armor_sort", row_crew_armor_sort),
          ("martial_training", row_martial_training), ("psi_training", row_psi_training),
          ("research_arrows", row_research_arrows), ("base_strip", row_base_strip)], up_shared, shared_setup)
    boot(results, walls, "separate", [("separate_reorders", row_separate_reorders)], up_separate)
    failed = [rid for rid in ORDER if not results.get(rid)]
    print(f"\ntest_shared_list_order: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0
if __name__ == "__main__":
    sys.exit(main())
