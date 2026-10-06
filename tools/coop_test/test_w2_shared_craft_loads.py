"""W2-H20b stage B (owner D255 a, D226 a; spec rewrite/prompts/w2h20b_shared_base_writes.md AMENDMENT H20b-B-1 B10, QB1 a .. QB4 a,
H20bB-M1..M5, R-H20bB-T0-1 / -T0-2; TASK 0 rewrite/w2h20bB-task0/CONSTANTS.md): in SHARED, a craft loadout template load (A8), "move
ground items to base" (A12) and, with oxceAlternateCraftEquipmentManagement ON, the soldier and craft inventory screens (A3, A4, A6) end
as host-applied craft_equip / craft_assign end-states, and a replica's own option-ON staging triggers no world re-copy (F8259); today each
stays on one machine until a restream reverts the client. H / C / C2 = H20's rule (h20.setup, option OFF; S25). SKY(gc) = base_report
HostBase craft {SKY id, STR_SKYRANGER} items (whole map); ST(gc) = geo_state HostBase items; reqs / mm = the client's shared_resync_stats.
W = 10 s at 0.25 s; RW 5 s, HOLD 8 s (TASK 0). park = host open_soldiers (no heartbeat, H20bB-M4), unpark = host soldiers_ok; converge =
both on GeoscapeState (no CoopState / LoadGameState), SKY and ST equal, <= 30 s; every row starts with converge + client
shared_reset_resync_stats. (item, slot) = STR_PISTOL into the actor's left hand, else belt, else backpack (run time); an A3 / A4 / A6 SKY
delta is {PISTOL +1, PISTOL_CLIP +1} (TASK 0). A row whose named RED cell fails evaluates no later cell (F8045).
Boot A2 (SHARED, 49427 / 49428 / 47927, option OFF): HB-1 A8 TB-2's setup, park, client CES loadout_load 1, OK. RED: SKY(host) unchanged
  after W. HB-2 A12 park, client craft inventory ground_to_base, close. RED: SKY(host) == the reply's before after W. HB-9 js.finish().
Boot B2 (SHARED, 49429 / 49430 / 47928; setup: TB-4's option-OFF settle, option ON on both, TB-6's host no-edit round trip, converge):
  HB-7 (guard) parked client soldier screen, PISTOL onto H (the partner's): client SKY == before, host unchanged, reqs 0 over RW. HB-3 A3
  client soldier screen (C) / HB-5 A4 / A6 client craft screen (C2), parked. RED: SKY(host) unchanged after W. HB-4 A3 host soldier screen
  (H), client on its geoscape. RED: reqs +1 within W. HB-10 (guard) js.finish(). HB-6 (LAST, R-H20bB-T0-2) F8259: host on its geoscape,
  the client's craft screen held HOLD. RED: reqs +1 or the InventoryState gone (closed, or the client crashed: F8598, W2-H21); only
  after a FAILED HB-6 does the shutdown tolerate a dead client (rc 3, its crash log as EVIDENCE).
Boot S2 (SEPARATE, tag w2h20b2s, labels 49431 / 49432, lobby 47929, option ON): HB-8 (guard) TB-11: ClientBase soldier screen on top 8 s,
  PISTOL onto its first soldier, close, craft screen round trip: SKY PISTOL / PISTOL_CLIP +1 locally, shared_stats unchanged 1 s after.
EVIDENCE line per row before its verdict; a failed row prints ONE CAPTURE line (both machines' base_report, geo_state items,
soldier_layouts, shared_resync_stats, shared_stats, option_values, stacks); a boot miss fails its rows "boot" with ONE CAPTURE line; a
failed shutdown is a FAIL line. Every row runs after a failure. ONE run (WV-D95); exit 0 iff everything passes, else 2.
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import harness  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded: setup, soldier screens, q / stack / wait_until)
import test_w2_shared_base_writes as sbw  # noqa: E402  (main-guarded: bso, items, Row)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
from test_w2_shared_base_equip import q, stack, wait_until  # noqa: E402
from test_w2_shared_base_writes import bso  # noqa: E402

TAG_A, PORTS_A = "w2h20b2a", (49427, 49428, 47927)
TAG_B, PORTS_B = "w2h20b2b", (49429, 49430, 47928)
TAG_S, LABELS_S, LOBBY_S = "w2h20b2s", (49431, 49432), "47929"
HB, CB, GEO, OPT, SKYR = "HostBase", "ClientBase", "GeoscapeState", "oxceAlternateCraftEquipmentManagement", "STR_SKYRANGER"
PISTOL, CLIP, INV, CES = "STR_PISTOL", "STR_PISTOL_CLIP", "InventoryState", "CraftEquipmentState"
DELTA = {CLIP: 1, PISTOL: 1}  # TASK 0: every A3 / A4 / A6 SKY delta (the moved pistol carries its clip)
W, POLL, RW, HOLD, CONV, SETTLE = 10.0, 0.25, 5.0, 8.0, 30.0, 1.0
ROWS_A, ROWS_B, ROWS_S = ["HB-1", "HB-2", "HB-9"], ["HB-7", "HB-3", "HB-5", "HB-4", "HB-10", "HB-6"], ["HB-8"]
ORDER = ROWS_A + ROWS_B + ROWS_S


def timed(pred, timeout):
    t0 = time.time()
    v = wait_until(pred, timeout)
    return v, round(time.time() - t0, 2)


def sky(gc, cid, base=HB):
    """SKY(gc): the craft {cid, STR_SKYRANGER}'s whole item map from base_report (world_dump does not compare craft items, F8265)."""
    rep = q(gc, {"cmd": "base_report", "base": base})
    c = next((c for c in rep.get("crafts") or [] if c.get("id") == cid and c.get("type") == SKYR), None)
    return None if c is None else dict(sorted((c.get("items") or {}).items()))


def st(gc, base=HB):
    return dict(sorted(sbw.items(gc, base).items()))


def rs(gc):
    r = q(gc, {"cmd": "shared_resync_stats"})
    return [r.get("requests"), r.get("mismatches")]


def opt(gc):
    return (q(gc, {"cmd": "option_values", "ids": [OPT]}).get("values") or {}).get(OPT)


def diff(a, b):
    a, b = a or {}, b or {}
    return {t: b.get(t, 0) - a.get(t, 0) for t in sorted(set(a) | set(b)) if b.get(t, 0) != a.get(t, 0)}


def is_dead(s):  # h20.stack's reply for a machine whose socket is gone
    return any(str(e).startswith("<get_state") for e in s)


def top(gc):
    return (stack(gc) or [None])[-1]


def settled(s):
    return bool(s) and s[-1] == GEO and not any("CoopState" in e or "LoadGameState" in e for e in s)


def equal(x):
    return sky(x.host, x.sky) == sky(x.client, x.sky) and st(x.host) == st(x.client)


def dump(gc, base=HB):
    return {"base_report": q(gc, {"cmd": "base_report", "base": base}), "items": sbw.items(gc, base),
            "soldier_layouts": q(gc, {"cmd": "soldier_layouts", "base": base}), "shared_stats": q(gc, {"cmd": "shared_stats"}),
            "shared_resync_stats": q(gc, {"cmd": "shared_resync_stats"}), "option_values": opt(gc), "stack": stack(gc)}


def converge(x, timeout=CONV):
    """Both on GeoscapeState with no CoopState / LoadGameState, SKY and ST equal on both (B8); a dead machine ends the wait."""
    t0, last = time.time(), {}

    def ok():
        last["stacks"] = [stack(x.host), stack(x.client)]
        if any(is_dead(s) for s in last["stacks"]):
            last["dead"] = True
            return True
        return all(settled(s) for s in last["stacks"]) and equal(x)
    got = bool(wait_until(ok, timeout)) and not last.get("dead")
    return {"ok": got, "s": round(time.time() - t0, 2), "dead": bool(last.get("dead")), "stacks": last.get("stacks")}


def watch(x, secs):
    t0, first, v = time.time(), None, [None, None]
    while time.time() - t0 < secs:
        v = rs(x.client)
        if (v[0] or 0) > 0 and first is None:
            first = round(time.time() - t0, 2)
        time.sleep(POLL)
    return {"reqs": v[0], "mm": v[1], "first req s": first}


class Row(sbw.Row):
    def __init__(self, rid, x):
        x.first = getattr(x, "first", {})
        super().__init__(rid, x)
        self.ev = {"ids": x.ids, "seats": x.seats, "H / C / C2": [x.H, x.C, x.C2], "SKY": x.sky}

    def report(self, results):
        self.evidence()
        if self.fails:
            for gc in (self.x.host, self.x.client):
                self.cap[gc.name] = dump(gc, self.x.base)
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def guard(r, x, tag="start"):
    """Every row's setup guard: converge + the client's shared_reset_resync_stats (the restream cooldown, F8527)."""
    c = converge(x)
    rep = q(x.client, {"cmd": "shared_reset_resync_stats"})
    r.ev[tag] = {"converge": [c["ok"], c["s"]], "sky host / client": [sky(x.host, x.sky), sky(x.client, x.sky)],
                 "reqs / mm": rs(x.client)}
    return r.cell(f"G: converge + client shared_reset_resync_stats ({tag})", c["ok"] and rep.get("ok") is True, [c, rep])


def open_ces(r, gc, base, cid, inv=False):
    rep = q(gc, {"cmd": "open_craft_equipment", "base": base, "craft_id": cid})
    if not r.cell(f"G: {gc.name} open_craft_equipment {base} {cid}", rep.get("ok") and rep.get("craftId") == cid
                  and wait_until(lambda: CES in stack(gc), 30), [rep, stack(gc)]):
        return False
    if not inv:
        return True
    rep = q(gc, {"cmd": "craft_inventory"})
    return r.cell(f"G: {gc.name} craft_inventory", rep.get("opened") is True and wait_until(lambda: INV in stack(gc), 30),
                  [rep, stack(gc)])


def close_ces(r, gc, inv=False):
    if inv:
        rep = q(gc, {"cmd": "battle_inventory", "action": "ok"})
        r.cell(f"G: {gc.name} battle_inventory ok", rep.get("ok") and wait_until(lambda: INV not in stack(gc), 30), [rep, stack(gc)])
    rep = q(gc, {"cmd": "craft_equipment_ok"})
    return r.cell(f"G: {gc.name} craft_equipment_ok", rep.get("ok") and wait_until(lambda: CES not in stack(gc), 30),
                  [rep, stack(gc)])


def edit(r, gc, name):
    """(item, slot) per TASK 0's rule on gc's open base inventory: select `name` (base_screen_op), STR_PISTOL into its left hand,
    else belt, else backpack (S25: read at run time)."""
    sel = bso(gc, op="select", name=name)
    g = q(gc, {"cmd": "inventory_ground"})
    u = next((u for u in g.get("soldiers") or [] if u.get("name") == name), None)
    slots = (u or {}).get("slots") or {}
    slot = "left" if "STR_LEFT_HAND" not in slots else ("belt" if "STR_BELT" not in slots else "backpack")
    mv = q(gc, {"cmd": "inventory_move", "name": name, "item": PISTOL, "slot": slot})
    r.ev[gc.name + " edit"] = {"select": sel, "slot": slot, "unit slots": {k: [e.get("item") for e in v] for k, v in slots.items()},
                               "ground " + PISTOL: (g.get("items") or {}).get(PISTOL, 0), "inventory_move": mv}
    return sel.get("ok") is True and u is not None and mv.get("moved") is True


def park(r, x):
    rep = q(x.host, {"cmd": "open_soldiers", "base": HB})
    return r.cell("G: park (host SoldiersState on top)", rep.get("ok") and wait_until(lambda: top(x.host) == "SoldiersState", 10),
                  [rep, stack(x.host)])


def release(r, x):
    """unpark; the client's reqs / mm over RW; converge (the red rows' cleanup: the restream reverts the client)."""
    rep = q(x.host, {"cmd": "soldiers_ok"})
    up = bool(wait_until(lambda: top(x.host) == GEO, 10, 0.05))
    rel = {"unpark": [rep.get("ok"), up], "over RW": watch(x, RW)}
    rel["converge"] = converge(x)
    r.ev["release"] = rel
    rel["ok"] = r.cell("G: unpark + converge after the row", up and rel["converge"]["ok"], rel)
    return rel


def parked(r, x, act):
    """H20bB-M4: park, the client's `act` (its values, or None after a failed setup cell), the host read over W (until SKY and ST
    equal on both), then release - always. Returns (act values, {equal, s, host sky, host before}, release values)."""
    h0, a, w = sky(x.host, x.sky), None, None
    if not park(r, x):
        return a, w, release(r, x)
    try:
        a = act()
        if a is not None:
            got, s = timed(lambda: equal(x), W)
            w = {"equal": bool(got), "s": s, "host sky": sky(x.host, x.sky), "client sky": sky(x.client, x.sky), "host before": h0}
    finally:
        rel = release(r, x)
    return a, w, rel


def green(r, w, rel, red, red_ok):
    """The named RED cell, then the green cells (F8045: a failed RED cell evaluates no later cell)."""
    if not r.cell(red, red_ok, {"host before": w["host before"], "host after W": w["host sky"]}):
        return
    if r.cell("SKY and ST not equal on both within W", w["equal"], w):
        r.cell("the client asked for a world re-copy over RW after the unpark", rel["over RW"]["reqs"] == 0, rel["over RW"])


def hb_1(x, r):
    h, c = x.host, x.client
    if not guard(r, x):
        return
    # TB-2's setup: template slot 1 = the SKY's items (stage A's equip_template puts it on the host), then two pistols off (craft_equip)
    opened = open_ces(r, c, HB, x.sky)
    save = bso(c, op="loadout_save", index=1) if opened else {}
    close_ces(r, c)
    got, s = timed(lambda: bso(h, op="read", index=1).get("loadout") == save.get("loadout"), W)
    b = {g.name: [sky(g, x.sky) or {}, st(g)] for g in (h, c)}
    ce = q(c, {"cmd": "craft_equip", "item": PISTOL, "count": -2, "base": HB, "craft_id": x.sky})
    off, s2 = timed(lambda: all((sky(g, x.sky) or {}).get(PISTOL, 0) == b[g.name][0].get(PISTOL, 0) - 2
                                and st(g).get(PISTOL, 0) == b[g.name][1].get(PISTOL, 0) + 2 for g in (h, c)), W)
    r.ev["setup"] = {"loadout_save 1": save.get("loadout"), "host read 1 s": s, "craft_equip": ce, "pistols -2 s": s2}
    if not (r.cell("G: client loadout_save 1 == the SKY's items", opened and save.get("loadout") == b["client"][0], save)
            and r.cell("G: the host's loadout 1 == the client's within W", got, s)
            and r.cell("G: craft_equip STR_PISTOL -2 on both within W", ce.get("moved") is True and off, [ce, s2])
            and guard(r, x, "after the setup")):
        r.evidence()
        return

    def act():
        if not open_ces(r, c, HB, x.sky):
            return None
        c0 = sky(c, x.sky)
        load = bso(c, op="loadout_load", index=1)
        c1 = sky(c, x.sky)
        close_ces(r, c)
        return {"loadout_load": load, "client sky before": c0, "client SKY diff at once": diff(c0, c1),
                "client SKY diff after OK": diff(c0, sky(c, x.sky))}
    a, w, rel = parked(r, x, act)
    r.ev.update({"load": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w):
        return
    if not r.cell("non-vacuity: the client's SKY PISTOL +2 at once", a["loadout_load"].get("ok") is True
                  and a["client SKY diff at once"].get(PISTOL) == 2, a):
        return
    green(r, w, rel, "the client's craft loadout load never reached the host", w["host sky"] != w["host before"])


def hb_2(x, r):
    c = x.client
    if not guard(r, x):
        return

    def act():
        if not open_ces(r, c, HB, x.sky, inv=True):
            return None
        g0 = q(c, {"cmd": "inventory_ground"}).get("items")
        gb = bso(c, op="ground_to_base")
        c1 = sky(c, x.sky)
        close_ces(r, c, inv=True)
        return {"ground": g0, "ground_to_base": gb, "client sky at once": c1, "client sky after close": sky(c, x.sky)}
    a, w, rel = parked(r, x, act)
    r.ev.update({"move": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w):
        return
    gb = a["ground_to_base"]
    bef, aft = gb.get("before") or {}, gb.get("after") or {}
    if not r.cell("non-vacuity: reply after < before for a type, the client's SKY == after", gb.get("ok") is True
                  and gb.get("craftId") == x.sky and any(aft.get(t, 0) < n for t, n in bef.items())
                  and a["client sky at once"] == dict(sorted(aft.items())), a):
        return
    green(r, w, rel, "the client's move-ground-to-base never reached the host", w["host sky"] != dict(sorted(bef.items())))


def finish(x, r):
    """HB-9 / HB-10 (guard): world equality + replica zero-disk."""
    r.ev.update({"world_diff now": shared_fixture.world_diff(x.host, x.client), "client save files now": session.save_files(
        x.js.client_dir), "sky host / client": [sky(x.host, x.sky), sky(x.client, x.sky)]})
    r.evidence()
    try:
        x.js.finish()
    except AssertionError as e:
        r.cell("js.finish", False, h20.short(e, 1500))


def setup_b2(x):
    """TB-4's settle (option OFF; F8526), the option ON on both (set_option, P10 raw-on-both), TB-6's host no-edit round trip (F8525),
    converge. Raises on a miss (the boot's rows fail "boot" with its CAPTURE)."""
    r, h, c = Row("Boot B2 setup", x), x.host, x.client
    whole_layouts = lambda gc: {e.get("id"): h20.whole(e)  # noqa: E731
                                for e in q(gc, {"cmd": "soldier_layouts", "base": HB}).get("soldiers") or []}
    for gc in (h, c):
        if h20.open_soldier_screen(r, gc):
            h20.close_soldier_screen(r, gc)
    eq, s = timed(lambda: whole_layouts(h) == whole_layouts(c), W)
    L = whole_layouts(h)
    crew = [e.get("id") for e in q(h, {"cmd": "base_report", "base": HB}).get("soldiers") or [] if e.get("craft") == x.sky]
    empty = [i for i in crew if not (L.get(i) or [None])[0]]
    so = {gc.name: q(gc, {"cmd": "set_option", "name": OPT, "value": True}) for gc in (h, c)}
    on = {gc.name: opt(gc) for gc in (h, c)}
    h0 = sky(h, x.sky)
    if h20.open_soldier_screen(r, h):
        h20.close_soldier_screen(r, h)
    h1 = sky(h, x.sky)
    cv = converge(x)
    x.setup = {"layouts equal": [bool(eq), s], "SKY crew": crew, "SKY crew with an empty layout": empty, "set_option": so,
               "option": on, "host round trip SKY diff": diff(h0, h1), "converge": [cv["ok"], cv["s"]], "sky": sky(h, x.sky)}
    if r.fails or not eq or not crew or empty or on != {"host": True, "client": True} or not cv["ok"]:
        raise RuntimeError(f"Boot B2 setup: {r.fails} {json.dumps(x.setup, default=str)}")


def hb_7(x, r):
    h, c = x.host, x.client
    r.ev["Boot B2 setup"] = x.setup
    if not guard(r, x):
        return

    def act():
        c0 = sky(c, x.sky)
        if not h20.open_soldier_screen(r, c):
            return None
        e = edit(r, c, x.H)
        h20.close_soldier_screen(r, c)
        return {"moved": e, "client sky before": c0, "client SKY diff at once": diff(c0, sky(c, x.sky)), "host sky": sky(h, x.sky)}
    a, w, rel = parked(r, x, act)
    r.ev.update({"edit": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w and r.cell("G: STR_PISTOL moved onto H", a["moved"], a)):
        return
    r.cell("the client's SKY changed after a partner edit", a["client SKY diff at once"] == {}, a)
    r.cell("the host's SKY changed", w["host sky"] == w["host before"], w)
    r.cell("the client asked for a world re-copy over RW after the unpark", rel["over RW"]["reqs"] == 0, rel["over RW"])


def client_edit(x, r, who, craft, red):
    """HB-3 (soldier screen) / HB-5 (craft screen, the staging): the client moves STR_PISTOL onto its own `who`, parked."""
    c = x.client
    if not guard(r, x):
        return

    def act():
        c0 = sky(c, x.sky)
        if not (open_ces(r, c, HB, x.sky, inv=True) if craft else h20.open_soldier_screen(r, c)):
            return None
        e = edit(r, c, getattr(x, who))
        close_ces(r, c, inv=True) if craft else h20.close_soldier_screen(r, c)
        return {"moved": e, "client sky before": c0, "client SKY diff after the close": diff(c0, sky(c, x.sky))}
    a, w, rel = parked(r, x, act)
    r.ev.update({"edit": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w and r.cell(f"G: STR_PISTOL moved onto {who}", a["moved"], a)):
        return
    if not r.cell(f"non-vacuity: the client's SKY diff == {DELTA}", a["client SKY diff after the close"] == DELTA, a):
        return
    green(r, w, rel, red, w["host sky"] != w["host before"])


def hb_4(x, r):
    h, c = x.host, x.client
    if not guard(r, x):
        return
    gv = r.ev["give STR_PISTOL 1"] = {g.name: q(g, {"cmd": "give_items", "item": PISTOL, "count": 1, "base": HB}) for g in (c, h)}
    if not r.cell("G: give_items STR_PISTOL 1 on both, client first (R-H20bB-G-1, F8754)", all(v.get("ok") for v in gv.values()), gv):
        return
    h0 = sky(h, x.sky)
    if not h20.open_soldier_screen(r, h):
        return
    e = edit(r, h, x.H)
    h20.close_soldier_screen(r, h)
    hd = diff(h0, sky(h, x.sky))
    t0, first, eq = time.time(), None, None
    while time.time() - t0 < W:  # until SKY and ST equal on both; the client's reqs on every poll
        if (rs(c)[0] or 0) > 0 and first is None:
            first = round(time.time() - t0, 2)
        if equal(x):
            eq = round(time.time() - t0, 2)
            break
        time.sleep(POLL)
    over = watch(x, RW)
    cv = converge(x)  # the red cleanup (the restream already landed on the client's geoscape)
    r.ev.update({"moved": e, "host SKY diff": hd, "first req s": first, "equal s": eq, "over RW": over, "converge": cv,
                 "sky host / client end": [sky(h, x.sky), sky(c, x.sky)]})
    r.evidence()
    if not (r.cell("G: converge after the row", cv["ok"], cv) and r.cell("G: STR_PISTOL moved onto H", e, r.ev.get("host edit"))):
        return
    if not r.cell(f"non-vacuity: the host's SKY diff == {DELTA}", hd == DELTA, hd):
        return
    if not r.cell("the host's soldier-screen craft load reached the client only by a world re-copy", first is None and over["reqs"] == 0,
                  {"first req s": first, "over RW": over}):
        return
    r.cell("SKY and ST not equal on both within W", eq is not None, eq)


def hb_6(x, r):
    h, c = x.host, x.client
    if not guard(r, x):
        return
    if not (r.cell("G: the host idle on its geoscape", stack(h) == [GEO], stack(h)) and open_ces(r, c, HB, x.sky, inv=True)):
        r.evidence()
        return
    t0, sh, sc = time.time(), st(h), st(c)
    first, gone, tops = None, None, []
    while time.time() - t0 < HOLD:  # the screen must stay on top through HOLD (R-H20bB-T0-2: a crashed client counts as gone)
        s, v = stack(c), rs(c)
        t = round(time.time() - t0, 2)
        tops.append([t, s[-1:], v])
        if (v[0] or 0) > 0 and first is None:
            first = t
        if is_dead(s) or s[-1:] != [INV]:
            gone = [t, s]
            break
        time.sleep(POLL)
    last, eq, s_eq, cv = rs(c), None, None, None
    if gone is None:
        close_ces(r, c, inv=True)
        eq, s_eq = timed(lambda: equal(x), W)
    else:
        cv = converge(x)  # the red cleanup (a dead client ends it at once)
    r.ev.update({"ST diff (host -> client) at open": diff(sh, sc), "first req s": first, "gone": gone, "tops (thinned)": tops[::4],
                 "reqs / mm before the close": last, "equal after the close": [bool(eq), s_eq], "cleanup converge": cv})
    r.evidence()
    if not r.cell("non-vacuity: the client's ST != the host's while open", sh != sc, diff(sh, sc)):
        return
    if not r.cell("the client's open craft screen was closed by a world re-copy (F8259)", first is None and gone is None,
                  {"first req s": first, "gone": gone}):
        return
    r.cell("reqs / mm changed before the close", last == [0, 0], last)
    r.cell("SKY and ST not equal on both within W after the close", bool(eq), s_eq)


def hb_8(x, r):
    h, c = x.host, x.client
    so = {g.name: q(g, {"cmd": "set_option", "name": OPT, "value": True}) for g in (h, c)}
    on = {g.name: opt(g) for g in (h, c)}
    rep = q(c, {"cmd": "base_report", "base": CB})
    sid = next((cr.get("id") for cr in rep.get("crafts") or [] if cr.get("type") == SKYR), None)
    first = ((rep.get("soldiers") or [{}])[0]).get("name")
    s0, k0 = {g.name: h20.stats3(g) for g in (h, c)}, sky(c, sid, CB)
    r.ev.update({"set_option": so, "option": on, "ClientBase SKY": [sid, k0], "first soldier": first})
    if not (r.cell("G: option ON on both", on == {"host": True, "client": True}, [so, on])
            and r.cell("G: a ClientBase SKYRANGER and a first soldier", sid is not None and first and k0 is not None, [sid, first])
            and h20.open_soldier_screen(r, c, CB)):
        r.evidence()
        return
    held = [time.sleep(1.0) or top(c) for _ in range(8)]  # the top state once a second for 8 s
    e = edit(r, c, first)
    h20.close_soldier_screen(r, c)
    k1 = sky(c, sid, CB)
    if open_ces(r, c, CB, sid, inv=True):
        close_ces(r, c, inv=True)
    k2 = sky(c, sid, CB)
    time.sleep(SETTLE)
    s1 = {g.name: h20.stats3(g) for g in (h, c)}
    d = diff(k0, k1)
    r.ev.update({"top each second": held, "SKY diff (soldier screen)": d, "SKY diff (craft round trip)": diff(k1, k2),
                 "shared_stats before": s0, "shared_stats 1 s after": s1})
    r.evidence()
    r.cell("G: STR_PISTOL moved onto the first soldier", e, r.ev.get("client edit"))
    r.cell("the InventoryState left the top within 8 s", held == [INV] * 8, held)
    r.cell("the client's ClientBase SKY PISTOL / PISTOL_CLIP not +1 locally", d.get(PISTOL) == 1 and d.get(CLIP) == 1, d)
    r.cell("shared_stats cmd / applyCount / failCount changed", s0 == s1, [s0, s1])


def boot_miss(tag, e, rids, results, x=None):
    cap = {"error": h20.short(e, 1500)}
    if x is not None:
        cap.update({g.name: dump(g, x.base) for g in (x.host, x.client)})
    print(f"CAPTURE boot {tag} (boot miss): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    for rid in rids:
        results[rid] = False
        print(f"EVIDENCE {rid}: {json.dumps({'boot': 'miss'})}\nFAIL {rid}: boot", flush=True)


def run_rows(x, rows, results, walls):
    for rid, fn in rows:
        r, t1 = Row(rid, x), time.time()
        try:
            fn(x, r)
        except Exception as e:
            r.cell(f"G: {rid} exception", False, h20.short(e))
        for g in (x.host, x.client):  # a stopped row leaves no screen behind; a dead client (HB-6 red) is left to the shutdown
            before = stack(g)
            if not is_dead(before) and (before or [""])[-1] != GEO:
                rep = q(g, {"cmd": "close_screens"})
                wait_until(lambda: top(g) == GEO, 5.0)
                r.cap[f"{g.name} cleanup"] = {"before": before, "close_screens": rep, "after": stack(g)}
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)


def crash_logs(js):
    roots = [os.path.dirname(harness.EXE), js.host_dir, js.client_dir]
    return {p for root in roots for p in glob.glob(os.path.join(root, "**", "crash_*.log"), recursive=True)}


def down(tag, results, fn):
    """A boot's shutdown; a failure is a FAIL line `shutdown <tag>` (exit 2), and the run goes on."""
    try:
        fn()
    except Exception as e:
        results["shutdown " + tag] = False
        print(f"FAIL shutdown {tag}: {h20.short(e, 800)}", flush=True)


def down_b2(js, results, crash0):
    """R-H20bB-T0-2: only after a FAILED HB-6 is a dead client (rc 3) tolerated, its new crash log printed as EVIDENCE."""
    try:
        js.host.shutdown()
    finally:
        rc = js.client.proc.poll() if js.client.proc else None
        if results.get("HB-6") is False and rc == 3:
            logs = {p: open(p, "r", encoding="utf-8", errors="replace").read()[:2500] for p in sorted(crash_logs(js) - crash0)}
            print(f"EVIDENCE HB-6 shutdown (dead client tolerated, R-H20bB-T0-2): "
                  f"{json.dumps({'client rc': rc, 'new crash logs': logs}, sort_keys=True)}", flush=True)
            js.client.shutdown(expected_returncodes=(0, 3))
        else:
            js.client.shutdown()


def shared_boot(tag, ports, rids, rows, results, walls, setup=None):
    t0, js, x, crash0 = time.time(), None, None, set()
    try:
        try:
            js = shared_fixture.bring_up(tag, ports)
            crash0 = crash_logs(js)
            x = h20.X(js.host, js.client, js)
            h20.setup(x)  # option OFF on both, seats differ, H / C / C2, the SKYRANGER, the HostBase index (raises on a miss)
            if setup:
                setup(x)
            walls["boot " + tag] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every row of this boot "boot" with ONE CAPTURE line
            return boot_miss(tag, e, rids, results, x)
        run_rows(x, rows, results, walls)
    finally:
        if js is not None:
            down(tag, results, (lambda: down_b2(js, results, crash0)) if tag == TAG_B else js.shutdown)


def boot_s(results, walls):
    t0 = time.time()
    h = GameClient("host", LABELS_S[0], make_user_dir(TAG_S + "_host"))
    c = GameClient("client", LABELS_S[1], make_user_dir(TAG_S + "_client"))
    x = h20.X(h, c, base=CB)
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=LOBBY_S, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            x.seats = {gc.name: q(gc, {"cmd": "get_coop"}).get("localSeat") for gc in (h, c)}
            walls["boot " + TAG_S] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails HB-8 "boot" with ONE CAPTURE line
            return boot_miss(TAG_S, e, ROWS_S, results, x)
        run_rows(x, (("HB-8", hb_8),), results, walls)
    finally:
        down(TAG_S, results, lambda: shutdown_clients(h, c))


def main():
    t0, results, walls = time.time(), {}, {}
    shared_boot(TAG_A, PORTS_A, ROWS_A, (("HB-1", hb_1), ("HB-2", hb_2), ("HB-9", finish)), results, walls)
    shared_boot(TAG_B, PORTS_B, ROWS_B, (
        ("HB-7", hb_7),
        ("HB-3", lambda x, r: client_edit(x, r, "C", False, "the client's soldier-screen craft load never reached the host")),
        ("HB-5", lambda x, r: client_edit(x, r, "C2", True, "the client's craft-screen load never reached the host")),
        ("HB-4", hb_4), ("HB-10", finish), ("HB-6", hb_6)), results, walls, setup_b2)
    boot_s(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    downs = sorted(k for k, v in results.items() if k.startswith("shutdown") and not v)
    print(f"\ntest_w2_shared_craft_loads: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed + downs}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed or downs else 0


if __name__ == "__main__":
    sys.exit(main())
