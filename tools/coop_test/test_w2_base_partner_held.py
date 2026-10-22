"""EQ-3 stage S-C - test_w2_base_partner_held.py (BPH): the co-op partner's held item on a SHARED base inventory screen leaves your
pile while it is held (you cannot pick that copy) and is drawn under the partner's pointer; it comes back when the partner puts it
down, cancels or leaves the screen (VL-EQ3-1; owner D291 (b) + (c) on base screens; QEQ3-9 (a): display-level, each machine maps the
partner's held item onto its OWN copy, no host arbitration and no refusal; QEQ3-10 (a): the held item rides S-B's `base_equip_ptr`
snapshot; QEQ3-13 (a): the TEST-ONLY `base_held_defer` lever times H4's race; VL-EQ3-7: both keep the last item, no "Order
cancelled"; R-EQ3-3; R-EQ2-1 (QEQ2-8: a lifted soldier item leaves the read-only paperdoll; QEQ2-10)). Spec: docs repo
rewrite/prompts/eq3_base_screens.md + eq3c_held.md (f) as amended by its PIN-PASS AMENDMENTS; TASK 0 constants
rewrite/eq3-task0/sc/CONSTANTS.md.
Boot S (SHARED, key 49416, dirs eq3c_s_host / _client): shared_fixture.bring_up + W2-H20's setup (H, C, SKY, HostBase; H20's and
BPP's helpers imported, never edited). Spine: S1 the host stages H (inventory_move {H, ITEM_H, left}, real OK; the client's record
of H carries it within W); S2 both open HostBase's Soldiers inventory, the client NEXTs to C; S3 move(client, PT1), move(host, PT2)
(BPP's recipe: each snapshot `on`). Preconditions: PILE_TYPE's cell >= 2 entries and LAST_TYPE exactly 1 entry on both screens
(pins with their replacement rules, logged); each cursor_pos inside its Inventory surface. A spine miss = every row FAIL "spine"
with ONE CAPTURE line.
Reads: count = the screen's inventory_view.ground entries at the cell (a held item is parked at x 1000000, F20617); "draws" = the
observer's event_state.equip.presence.drawn.held = its equip.basePresence.held.local, at (drawn.x - 16, drawn.y - 24) (EQ-2 S-D's
centring); the paperdoll = inventory_view.drawnSlots; basePresence.held absent reads -1 (the red).
  H1 LIFT  the client picks PILE_TYPE's cell; the host: H1-drop (count one lower within W_PTR), H1-draw (draws its held.local under
           the client's pointer); the host picks the same cell and right-clicks: H1-mate (guard: a PILE_TYPE item other than held.local)
  H2 PUT   the client drops its cursor item on C's belt cell BELT: H2-back (the host's count back to its pre-H1 value within W_PTR,
           H1-drop seen first), H2-off (guard: the host's drawn.held -1 within W_PTR)
  H3 OWNED the client NEXTs to H (S-A's read-only view); the host lifts ITEM_H from H's left hand, then right-clicks: H3-gone (the
           client's drawnSlots lacks its ITEM_H id while held), H3-draw (the client draws it under the host's pointer), H3-back (back in
           the client's drawnSlots within W_PTR and H carries ITEM_H in the left hand on both; H3-gone seen first)
  H4 RACE  the client NEXTs to C (an own soldier: S-A's partner view takes no click; logged in CONSTANTS.md); both
           base_held_defer {on: true}; the client, then the host, picks LAST_TYPE; both {on: false}; W_PTR on both; both right-click:
           H4-both (guard: both cursors still hold it), H4-noline (guard: no "Order cancelled - item unavailable", no line shown),
           H4-draw (each draws its own held.local = its own cursor item under the other's pointer)
  H5 OK    the client (on C) picks PILE_TYPE, real OK, right click, real OK: H5-stay (guard: the first OK leaves the screen on top),
           H5-back (the host's count drops while the client holds, back within W_PTR after the right click), H5-off (guard: the host's
           drawn.ptr false within W_PTR of the second OK), H5-belt (guard: the host's record of C carries PILE_TYPE at BELT within W)
  X        base_held_defer {on: false} on both in the boot's finally; X-crash (guard: no new crash file, both games alive)
RED (HEAD = R1 on the r1 build): 8 of 16 cells - H1-drop, H1-draw, H2-back, H3-gone, H3-draw, H3-back, H4-draw, H5-back; the 8 guards
PASS. Green: 16 / 16. One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; every row runs after a failure
(a precondition miss ends its row, its later cells "not reached"); every row ends with both cursors empty (H1 hands the client's pick
to H2), recorded. WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_w2_base_partner_held.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded: setup, screens, q / stack, layouts)
import test_w2_base_partner_pointer as bpp  # noqa: E402  (main-guarded: move, cpos, equip, drawn, bp, alive, PT1 / PT2)
from test_w2_shared_base_equip import q, stack, open_soldier_screen  # noqa: E402

TAG, PORTS = "eq3c_s", (49416, 49416, 49416)  # BPH_PORTS (pin pass: two inert labels and the rendezvous key)
HB, GEO, INV = "HostBase", "GeoscapeState", "InventoryState"
GROUND, BELT_SLOT, LEFT = "STR_GROUND", "STR_BELT", "STR_LEFT_HAND"
PILE_PIN, LAST_PIN, ITEM_H, BELT_PIN = "STR_PISTOL_CLIP", "STR_GRENADE", "STR_PISTOL", (0, 0)  # pins (rules: pick_types, pick_belt)
TEXT_ITEM_MISSING = "Order cancelled - item unavailable"  # STR_COOP_DENY_ITEM_MISSING (EQ-2's pre-battle refusal)
HALF = (16, 24)                    # EQ-2 S-D: the held item's top-left = the pointer - (HAND_W * SLOT_W / 2, HAND_H * SLOT_H / 2)
W_PTR, W, CYCLE_CAP, CLICK_W = 2.0, 10.0, 16, 2.0
POLL, PAGE = 0.05, 1000000         # a parked ground item sits at x PAGE (F20617)
CELLS = {
    "H1": ["H1-drop", "H1-draw", "H1-mate"],
    "H2": ["H2-back", "H2-off"],
    "H3": ["H3-gone", "H3-draw", "H3-back"],
    "H4": ["H4-both", "H4-noline", "H4-draw"],
    "H5": ["H5-stay", "H5-back", "H5-off", "H5-belt"],
    "X": ["X-crash"],
}
ORDER = ["H1", "H2", "H3", "H4", "H5", "X"]
EV = {}  # every row's EVIDENCE (TASK 0 dumps it as JSON)


class Row(bpp.Row):
    def report(self, results):
        EV[self.rid] = self.ev
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        fails = []
        for c in CELLS[self.rid]:
            ok, d = self.got.get(c, (False, f"not reached ({self.why})"))
            results[c] = ok
            print(f"PASS {c}" if ok else f"FAIL {c}: {json.dumps(d, default=str)[:900]}", flush=True)
            fails += [] if ok else [c]
        print(f"ROW {self.rid}: " + ("PASS" if not fails else "FAIL " + ",".join(fails)), flush=True)


class Stop(Exception):
    """A row's precondition miss: the row ends, its later cells are "not reached"."""


# ===================== probes =====================


def view(gc):
    r = q(gc, {"cmd": "inventory_view"})
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "ground", "drawnSlots", "lineText", "lineVisible", "slots")}


def cur(gc):
    return view(gc).get("selectedItem")


def types(gc):
    """{item id: (type, owner unit id, slot, slotX, slotY)} of gc's base screen (battle_items)."""
    return {it["id"]: (it.get("type"), it.get("owner"), it.get("slot"), it.get("slotX"), it.get("slotY"))
            for it in q(gc, {"cmd": "battle_items"}).get("items") or []}


def count(gc, cell):
    return sum(1 for g in view(gc).get("ground") or [] if [g.get("x"), g.get("y")] == list(cell))


def kinds(gc):
    """{type: {(x, y): n}} of gc's ground on the page (parked entries left out)."""
    t, out = types(gc), {}
    for g in view(gc).get("ground") or []:
        if g.get("x") is not None and g["x"] < PAGE:
            k = out.setdefault((t.get(g["id"]) or ("?",))[0], {})
            k[(g["x"], g["y"])] = k.get((g["x"], g["y"]), 0) + 1
    return out


def local(gc):
    """gc's basePresence.held.local (absent = -1: the red)."""
    v = (bpp.bp(gc).get("held") or {}).get("local")
    return v if isinstance(v, int) else -1


def under(gc, iid):
    """gc draws item `iid` under the partner's pointer, centred as EQ-2 S-D centres it, and it is gc's mapped held.local."""
    d = bpp.drawn(gc)
    return (isinstance(iid, int) and iid >= 0 and d.get("ptr") is True and d.get("held") == iid and local(gc) == iid
            and [d.get("heldX"), d.get("heldY")] == [(d.get("x") or 0) - HALF[0], (d.get("y") or 0) - HALF[1]])


def show(gc):
    d = bpp.drawn(gc)
    return {"drawn": {k: d.get(k) for k in ("ptr", "x", "y", "held", "heldX", "heldY")}, "held": bpp.bp(gc).get("held"),
            "cursor": cur(gc)}


def seen(preds, timeout, whole=False):
    """Sample every predicate each POLL: {name: seconds of its first true, None = never}; ends when all were true (whole: never)."""
    t0, first = time.time(), {k: None for k in preds}
    while True:
        el = round(time.time() - t0, 3)
        for k, f in preds.items():
            if first[k] is None and f():
                first[k] = el
        if el >= timeout or (not whole and None not in first.values()):
            return first
        time.sleep(POLL)


def click(gc, **kw):
    r = q(gc, dict({"cmd": "inventory_click"}, **kw))
    return r.get("error") or r.get("ok")


def lift(gc, ev, key, want_type, **at):
    """A real left click with an empty cursor; the picked item must be a `want_type` (else the row's precondition)."""
    ev[key] = {"click": click(gc, **at), "at": at}
    h20.wait_until(lambda: cur(gc) not in (None, -1), CLICK_W, POLL)
    iid = cur(gc)
    ev[key]["picked"] = [iid, (types(gc).get(iid) or ("?",))[0]]
    if iid in (None, -1) or ev[key]["picked"][1] != want_type:
        raise Stop(f"precondition: {gc.name}'s click {at} put {ev[key]['picked']} on its cursor (want a {want_type})")
    return iid


def give_back(gc, ev, key):
    """The holder's right click (vanilla's cancel); a cursor a right click cannot reach is cleared by the lever (recorded)."""
    if cur(gc) in (None, -1):
        return True
    ev[key] = {"right": click(gc, slot=GROUND, x=0, y=0, button="right")}
    h20.wait_until(lambda: cur(gc) == -1, CLICK_W, POLL)
    if cur(gc) != -1:
        ev[key]["cleared"] = q(gc, {"cmd": "inventory_cursor_clear"}).get("cleared")
    return cur(gc) == -1


def goto(gc, uid, rec):
    """NEXT (a real click) until gc's screen shows `uid`, at most CYCLE_CAP presses."""
    for _ in range(CYCLE_CAP):
        now = view(gc).get("unitId")
        rec.append(now)
        if now == uid:
            return True
        click(gc, widget="next")
        h20.wait_until(lambda: view(gc).get("unitId") != now, CLICK_W, POLL)
    return view(gc).get("unitId") == uid


def carries(gc, uid, t, slot, xy=None):
    """The item id of type `t` that unit `uid` carries in `slot` (at `xy` for a slot cell) on gc's screen, else None."""
    return next((i for i, (ty, ow, sl, sx, sy) in types(gc).items()
                 if ty == t and ow == uid and sl == slot and (xy is None or [sx, sy] == list(xy))), None)


def belt_rec(gc, name, t, xy):
    """gc's soldier_layouts record of `name` holds a `t` at STR_BELT `xy`."""
    L = (h20.layouts(gc).get(name) or {}).get("layout") or []
    return any(i.get("type") == t and i.get("slot") == BELT_SLOT and [i.get("x"), i.get("y")] == list(xy) for i in L)


def ready(x, r):
    """A row's head: both base screens on top, both cursors empty (an earlier row's leftover is recorded and cleared)."""
    for gc in (x.host, x.client):
        if bpp.top(gc) != INV:
            raise Stop(f"precondition: {gc.name}'s base inventory screen on top ({stack(gc)})")
        if cur(gc) not in (None, -1):
            r.ev.setdefault("leftover", {})[gc.name] = [cur(gc), give_back(gc, r.ev, "leftover " + gc.name)]
        if cur(gc) != -1:
            raise Stop(f"precondition: {gc.name}'s cursor empty ({cur(gc)})")


def ends(x, r):
    r.ev["cursors at end"] = {gc.name: cur(gc) for gc in (x.host, x.client)}


# ===================== spine =====================


def pick_types(x):
    """PILE_TYPE / LAST_TYPE by their pins, else their replacement rules (the first type, by its lowest ground cell on the host)."""
    m = {gc.name: kinds(gc) for gc in (x.host, x.client)}
    order = sorted(m["host"], key=lambda t: min(m["host"][t]))
    pile_ok = lambda t: all(any(n >= 2 for n in (m[g].get(t) or {}).values()) for g in m)  # noqa: E731
    last_ok = lambda t: all(sum((m[g].get(t) or {}).values()) == 1 for g in m)  # noqa: E731
    pile = PILE_PIN if pile_ok(PILE_PIN) else next((t for t in order if pile_ok(t)), None)
    last = LAST_PIN if last_ok(LAST_PIN) else next((t for t in order if last_ok(t)), None)
    cell = lambda g, t, ok: next((list(c) for c, n in sorted(m[g].get(t, {}).items()) if ok(n)), None)  # noqa: E731
    x.pile, x.last = pile, last
    x.pile_cell = {g: cell(g, pile, lambda n: n >= 2) for g in m}
    x.last_cell = {g: cell(g, last, lambda n: n == 1) for g in m}
    return {"kinds": {g: {t: {f"{a},{b}": n for (a, b), n in v.items()} for t, v in m[g].items()} for g in m},
            "PILE_TYPE": [PILE_PIN, pile], "LAST_TYPE": [LAST_PIN, last], "pileCell": x.pile_cell, "lastCell": x.last_cell}


def sizes():
    """{type: [invWidth, invHeight]} from the ruleset the game reads (the Release deploy, F6757; test_r5_alien_equip's reader)."""
    d, t = {}, None
    with open(os.path.join(os.path.dirname(os.path.abspath(harness.EXE)), "standard", "xcom1", "items.rul"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^  - type: (\S+)", line)
            if m:
                t = m.group(1)
                d[t] = [1, 1]
                continue
            m = re.match(r"^    inv(Width|Height): (\d+)", line)
            if m and t:
                d[t][0 if m.group(1) == "Width" else 1] = int(m.group(2))
    return d


def pick_belt(x):
    """BELT: C's STR_BELT (0, 0) when PILE_TYPE fits there on the client's screen, else the next belt cell (the slot's cell order)
    where it fits: every cell of its footprint a belt cell that no carried item's footprint covers (F21916: a 2 x 1 item)."""
    sz = sizes()
    foot = lambda t, a, b: {(a + i, b + j) for i in range(sz.get(t, [1, 1])[0]) for j in range(sz.get(t, [1, 1])[1])}  # noqa: E731
    cells = [tuple(c) for c in ((view(x.client).get("slots") or {}).get(BELT_SLOT) or {}).get("cells") or []]
    held = [(ty, sx, sy) for (ty, ow, sl, sx, sy) in types(x.client).values() if ow == x.ids["C"] and sl == BELT_SLOT]
    used = set().union(*[foot(ty, sx, sy) for ty, sx, sy in held]) if held else set()
    order = [tuple(BELT_PIN)] + [c for c in cells if c != tuple(BELT_PIN)]
    x.belt = next((list(c) for c in order if c in cells and foot(x.pile, *c) <= set(cells) - used), None)
    return {"cells": cells, "items": held, "used": sorted(used), "BELT": [list(BELT_PIN), x.belt]}


def spine(x):
    h, c = x.host, x.client
    h20.setup(x)
    sh, sp = bpp.Shim(), {}
    sp["S1 open"] = open_soldier_screen(sh, h)
    sp["S1 move"] = q(h, {"cmd": "inventory_move", "name": x.H, "item": ITEM_H, "slot": "left"})
    sp["S1 ok"] = click(h, widget="ok")
    h20.wait_until(lambda: INV not in stack(h), 10.0, POLL)
    sp["S1 soldiers_ok"] = q(h, {"cmd": "soldiers_ok"}).get("ok")
    h20.wait_until(lambda: bpp.top(h) == GEO, 10.0, POLL)
    hand = lambda gc: any(i.get("type") == ITEM_H and i.get("slot") == LEFT  # noqa: E731
                          for i in (h20.layouts(gc).get(x.H) or {}).get("layout") or [])
    sp["S1 client record"], sp["S1 within"] = h20.converge(lambda: hand(c))
    sp["S2 open"] = {gc.name: open_soldier_screen(sh, gc) for gc in (h, c)}
    sp["S2 nav"] = []
    sp["S2 client on C"] = goto(c, x.ids["C"], sp["S2 nav"])
    sp["S2 host unit"] = view(h).get("unitId")
    ev = {}
    sp["S3 moves"] = [bpp.move(c, bpp.PT1, ev), bpp.move(h, bpp.PT2, ev), ev]
    sp["cursor"] = {gc.name: bpp.cpos(gc) for gc in (h, c)}
    sp["pins"] = pick_types(x)
    sp["belt"] = pick_belt(x)
    x.item_h = {gc.name: carries(gc, x.ids["H"], ITEM_H, LEFT) for gc in (h, c)}
    sp["ITEM_H ids"] = x.item_h
    sp["host record of C belt"] = belt_rec(h, x.C, x.pile or "", x.belt or [-1, -1])
    sp["basePresence"] = {gc.name: bpp.bp(gc) for gc in (h, c)}
    x.spine = {"ids": x.ids, "names": {"H": x.H, "C": x.C, "C2": x.C2}, "sky": x.sky, "hbIndex": x.hb_index, "seats": x.seats,
               "steps": sp, "open fails": sh.fails}
    xy = lambda n, k: sp["cursor"][n].get(k) if isinstance(sp["cursor"][n].get(k), int) else -1  # noqa: E731
    inside = all(0 <= xy(n, "x") < 320 and 0 <= xy(n, "y") < 200 for n in ("host", "client"))  # the Inventory surface (rect)
    if not (sp["S1 move"].get("landedSlot") == LEFT and sp["S1 client record"] and all(sp["S2 open"].values())
            and sp["S2 client on C"] and all(sp["S3 moves"][:2]) and inside and x.pile and x.last and x.belt
            and None not in x.pile_cell.values() and None not in x.last_cell.values() and None not in x.item_h.values()
            and not sp["host record of C belt"] and all(bpp.top(gc) == INV for gc in (h, c))):
        raise RuntimeError(f"spine: {x.spine}")


# ===================== rows =====================


def h1(x, r):
    h, c = x.host, x.client
    ready(x, r)
    hc = x.pile_cell["host"]
    x.n0 = n0 = r.ev["hostCount0"] = count(h, hc)
    r.ev["clientPick id"] = lift(c, r.ev, "clientPick", x.pile, slot=GROUND, x=x.pile_cell["client"][0], y=x.pile_cell["client"][1])
    first = r.ev["first true (s)"] = seen({"drop": lambda: count(h, hc) == n0 - 1, "draw": lambda: under(h, local(h))}, W_PTR)
    r.ev["host"] = show(h)
    r.ev["hostCount"] = count(h, hc)
    x.h1_drop = first["drop"] is not None
    r.cell("H1-drop", x.h1_drop, f"the host's count at {hc} {n0} -> {r.ev['hostCount']} (want {n0 - 1} within {W_PTR} s while "
                                 f"the client holds {r.ev['clientPick id']}; first {first['drop']})")
    r.cell("H1-draw", first["draw"] is not None, f"the host draws {r.ev['host']} (want its held.local, != -1, under the client's "
                                                 f"pointer at (x - {HALF[0]}, y - {HALF[1]}) within {W_PTR} s)")
    loc = r.ev["host held.local before its pick"] = local(h)
    mate = lift(h, r.ev, "hostPick", x.pile, slot=GROUND, x=hc[0], y=hc[1])
    r.cell("H1-mate", mate != loc, f"the host picked {mate} (want a {x.pile} other than its held.local {loc})")
    give_back(h, r.ev, "hostReturn")
    r.ev["cursors at end"] = {"host": cur(h), "client (kept for H2)": cur(c)}


def h2(x, r):
    h, c = x.host, x.client
    if cur(h) != -1 or (types(c).get(cur(c)) or ("?",))[0] != x.pile:
        raise Stop(f"precondition: H1 left the client holding a {x.pile} and the host empty (cursors {cur(h)} / {cur(c)})")
    held, hc = cur(c), x.pile_cell["host"]
    r.ev["drop"] = click(c, slot=BELT_SLOT, x=x.belt[0], y=x.belt[1])
    h20.wait_until(lambda: cur(c) == -1, CLICK_W, POLL)
    r.ev["landed"] = carries(c, x.ids["C"], x.pile, BELT_SLOT, x.belt)
    if r.ev["landed"] != held:
        raise Stop(f"precondition: {held} not on C's belt {x.belt} on the client ({r.ev['landed']}; cursor {cur(c)})")
    first = r.ev["first true (s)"] = seen({"back": lambda: count(h, hc) == x.n0, "off": lambda: bpp.drawn(h).get("held") == -1}, W_PTR)
    r.ev["host"], r.ev["hostCount"] = show(h), count(h, hc)
    r.cell("H2-back", x.h1_drop and first["back"] is not None,
           f"the host's count at {hc} {r.ev['hostCount']} (want back to {x.n0} within {W_PTR} s of the belt drop, after H1-drop "
           f"{'seen' if x.h1_drop else 'NOT seen'}; first {first['back']})")
    r.cell("H2-off", first["off"] is not None, f"the host's drawn.held {r.ev['host']['drawn']['held']} (want -1 within {W_PTR} s)")
    ends(x, r)


def h3(x, r):
    h, c, hid = x.host, x.client, x.ids["H"]
    ready(x, r)
    nav = r.ev["nav"] = {"client": [], "host": []}
    if not (goto(c, hid, nav["client"]) and goto(h, hid, nav["host"])):
        raise Stop(f"precondition: both screens on H {hid} (navs {nav})")
    cid = r.ev["client ITEM_H"] = carries(c, hid, ITEM_H, LEFT)
    if cid is None or not h20.wait_until(lambda: cid in (view(c).get("drawnSlots") or []), W_PTR, POLL):
        raise Stop(f"precondition: H's {ITEM_H} {cid} in the client's drawnSlots {view(c).get('drawnSlots')}")
    r.ev["host pick"] = lift(h, r.ev, "hostLift", ITEM_H, slot=LEFT, x=0, y=0)
    first = r.ev["first true held (s)"] = seen({"gone": lambda: cid not in (view(c).get("drawnSlots") or []),
                                                 "draw": lambda: under(c, cid)}, W_PTR)
    r.ev["client held"] = dict(show(c), drawnSlots=view(c).get("drawnSlots"))
    give_back(h, r.ev, "hostReturn")
    hand = lambda: (cid in (view(c).get("drawnSlots") or []) and carries(c, hid, ITEM_H, LEFT) is not None  # noqa: E731
                    and carries(h, hid, ITEM_H, LEFT) is not None)
    back = r.ev["back within (s)"] = seen({"back": hand}, W_PTR)["back"]
    r.ev["client after"] = dict(show(c), drawnSlots=view(c).get("drawnSlots"))
    r.cell("H3-gone", first["gone"] is not None, f"the client's drawnSlots {r.ev['client held']['drawnSlots']} while the host holds "
                                                 f"H's {ITEM_H} (want {cid} absent within {W_PTR} s; first {first['gone']})")
    r.cell("H3-draw", first["draw"] is not None, f"the client draws {r.ev['client held']} (want {cid} = its held.local under the "
                                                 f"host's pointer within {W_PTR} s)")
    r.cell("H3-back", first["gone"] is not None and back is not None,
           f"after the host's right click: the client's drawnSlots {r.ev['client after']['drawnSlots']} (want {cid} back within "
           f"{W_PTR} s, H3-gone {'seen' if first['gone'] is not None else 'NOT seen'}; back {back}); H's left hand on both "
           f"{[carries(gc, hid, ITEM_H, LEFT) for gc in (h, c)]}")
    ends(x, r)


def h4(x, r):
    h, c = x.host, x.client
    ready(x, r)
    nav = r.ev["client nav to C"] = []
    if not goto(c, x.ids["C"], nav):
        raise Stop(f"precondition: the client's screen on its own C {x.ids['C']} (nav {nav})")
    try:
        r.ev["defer on"] = {gc.name: q(gc, {"cmd": "base_held_defer", "on": True}) for gc in (c, h)}
        ids = {"client": lift(c, r.ev, "clientPick", x.last, slot=GROUND, x=x.last_cell["client"][0], y=x.last_cell["client"][1])}
        ids["host"] = lift(h, r.ev, "hostPick", x.last, slot=GROUND, x=x.last_cell["host"][0], y=x.last_cell["host"][1])
    finally:
        r.ev["defer off"] = {gc.name: q(gc, {"cmd": "base_held_defer", "on": False}) for gc in (c, h)}
    lines = []

    def no_line():
        lines.append({gc.name: [view(gc).get("lineText"), view(gc).get("lineVisible")] for gc in (h, c)})
        return False
    first = r.ev["first true (s)"] = seen({"hostDraw": lambda: under(h, ids["host"]), "clientDraw": lambda: under(c, ids["client"]),
                                           "lines": no_line}, W_PTR, whole=True)
    r.ev["look"] = {gc.name: show(gc) for gc in (h, c)}
    r.ev["lines (distinct)"] = sorted({json.dumps(s, sort_keys=True) for s in lines})
    hold = {gc.name: cur(gc) for gc in (h, c)}
    r.cell("H4-both", hold == ids, f"cursors after {W_PTR} s {hold} (want {ids}: both keep their {x.last})")
    bad = [s for s in lines for v in s.values() if v[0] == TEXT_ITEM_MISSING or v[1] is True]
    r.cell("H4-noline", lines and not bad, f"lines over {W_PTR} s: {r.ev['lines (distinct)']} (want no '{TEXT_ITEM_MISSING}' and "
                                           f"no line shown on either screen)")
    r.cell("H4-draw", first["hostDraw"] is not None and first["clientDraw"] is not None,
           f"host / client draw {r.ev['look']} (want each its own cursor item {ids} = its held.local under the other's pointer "
           f"within {W_PTR} s; first {first['hostDraw']} / {first['clientDraw']})")
    for gc in (c, h):
        give_back(gc, r.ev, gc.name + "Return")
    ends(x, r)


def h5(x, r):
    h, c = x.host, x.client
    ready(x, r)
    nav = r.ev["client nav to C"] = []
    if not goto(c, x.ids["C"], nav):
        raise Stop(f"precondition: the client's screen on its own C {x.ids['C']} (nav {nav})")
    hc = x.pile_cell["host"]
    n0 = r.ev["hostCount0"] = count(h, hc)
    r.ev["clientPick id"] = lift(c, r.ev, "clientPick", x.pile, slot=GROUND, x=x.pile_cell["client"][0], y=x.pile_cell["client"][1])
    drop = r.ev["drop within (s)"] = seen({"drop": lambda: count(h, hc) == n0 - 1}, W_PTR)["drop"]
    r.ev["ok1"] = click(c, widget="ok")
    stay = r.ev["first off top (s)"] = seen({"gone": lambda: bpp.top(c) != INV}, CLICK_W, whole=True)["gone"]
    r.ev["client after ok1"] = {"stack": stack(c), "cursor": cur(c)}
    r.cell("H5-stay", stay is None and bpp.top(c) == INV and cur(c) == r.ev["clientPick id"],
           f"after the first OK the client's stack {r.ev['client after ok1']} (want its InventoryState on top for {CLICK_W} s, the "
           f"item still on the cursor)")
    give_back(c, r.ev, "clientReturn")
    back = r.ev["back within (s)"] = seen({"back": lambda: count(h, hc) == n0}, W_PTR)["back"]
    r.ev["hostCount after"] = count(h, hc)
    r.cell("H5-back", drop is not None and back is not None,
           f"the host's count at {hc}: {n0}, drop while the client holds {drop}, back to {n0} after the right click {back} "
           f"(want both within {W_PTR} s; now {r.ev['hostCount after']})")
    r.ev["ok2"] = click(c, widget="ok")
    if not h20.wait_until(lambda: INV not in stack(c), 10.0, POLL):
        raise Stop(f"precondition: the client's second OK closes its screen ({stack(c)})")
    off = r.ev["off within (s)"] = seen({"off": lambda: bpp.drawn(h).get("ptr") is not True}, W_PTR)["off"]
    r.cell("H5-off", off is not None, f"the host's drawn.ptr {bpp.drawn(h).get('ptr')} (want false within {W_PTR} s of the second OK)")
    r.ev["soldiers_ok"] = q(c, {"cmd": "soldiers_ok"}).get("ok")
    got, r.ev["belt within (s)"] = h20.converge(lambda: belt_rec(h, x.C, x.pile, x.belt))
    r.cell("H5-belt", got, f"the host's record of C {h20.compact(h20.layouts(h).get(x.C))} (want a {x.pile} at {BELT_SLOT} {x.belt} "
                           f"within {W} s: H2's drop sent at the client's OK, W2-H20)")
    r.ev["cursors at end"] = {"host": cur(h), "client": "screen closed"}


def px(x, r):
    crash = sorted(session._crash_log_snapshot() - x.crash0)
    up = {gc.name: bpp.alive(gc) for gc in (x.host, x.client)}
    r.ev.update(newCrashFiles=crash, alive=up, tops={gc.name: stack(gc) for gc in (x.host, x.client)})
    r.cell("X-crash", not crash and all(up.values()), f"new crash files {crash} (want none); alive {up} (want both)")


FNS = {"H1": h1, "H2": h2, "H3": h3, "H4": h4, "H5": h5, "X": px}


def main(tag=TAG, ports=PORTS, extra=None):
    t0, results, walls, js, x = time.time(), {}, {}, None, None
    crash0 = session._crash_log_snapshot()
    try:
        try:
            js = shared_fixture.bring_up(tag, ports)
            x = h20.X(js.host, js.client, js)
            x.crash0, x.h1_drop, x.n0 = crash0, False, None
            spine(x)
            walls["spine"] = round(time.time() - t0, 1)
            print(f"EVIDENCE spine: {json.dumps(x.spine, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = x.spine
        except Exception as e:  # a spine miss fails every row "spine" with ONE CAPTURE line
            cap = {"error": h20.short(e, 4000)}
            if x is not None:
                for g in (x.host, x.client):
                    cap[g.name] = {"stack": stack(g), "view": view(g), "basePresence": bpp.bp(g)}
                # CIT-DIAG (F24295): the spine once missed on the two machines' ground piles differing at pin time; record
                # whether the worlds differ (checksum, resync state) and whether the piles agree a moment later
                def piles():
                    try:
                        return {g.name: {t: {f"{a},{b}": n for (a, b), n in v.items()} for t, v in kinds(g).items()}
                                for g in (x.host, x.client)}
                    except Exception as e2:  # noqa: BLE001 - the capture must not raise
                        return h20.short(e2, 300)
                cap["pilesNow"] = piles()
                for g in (x.host, x.client):
                    cap[g.name]["shared_checksum"] = q(g, {"cmd": "shared_checksum"})
                    cap[g.name]["shared_resync_stats"] = q(g, {"cmd": "shared_resync_stats"})
                time.sleep(2.0)
                cap["pilesAfter2s"] = piles()
            print(f"CAPTURE spine: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = cap
            for rid in ORDER:
                for cname in CELLS[rid]:
                    results[cname] = False
                    print(f"FAIL {cname}: spine", flush=True)
                print(f"ROW {rid}: FAIL spine", flush=True)
            return results, walls
        try:
            for rid in ORDER:
                r, t1 = Row(rid), time.time()
                try:
                    FNS[rid](x, r)
                except Exception as e:
                    r.why = h20.short(e, 900)
                    r.ev["stopped"] = r.why
                    if rid != "H1":  # H1 hands the client's pick to H2; any other stopped row leaves both cursors empty
                        r.ev["cleanup"] = {gc.name: give_back(gc, r.ev, "cleanup " + gc.name) for gc in (x.host, x.client)
                                           if bpp.top(gc) == INV}
                walls[rid] = round(time.time() - t1, 1)
                r.report(results)
            if extra:
                extra(x)
        finally:
            EV["defer off at end"] = {gc.name: q(gc, {"cmd": "base_held_defer", "on": False}) for gc in (x.host, x.client)}
    finally:
        if js is not None:
            js.shutdown()
        walls["total"] = round(time.time() - t0, 1)
    return results, walls


if __name__ == "__main__":
    res, wl = main()
    allc = [cname for rid in ORDER for cname in CELLS[rid]]
    failed = [cname for cname in allc if not res.get(cname)]
    print(f"\ntest_w2_base_partner_held: {len(allc) - len(failed)}/{len(allc)} cells passed (fail={failed}) "
          f"walls {json.dumps(wl)}", flush=True)
    sys.exit(2 if failed else 0)
