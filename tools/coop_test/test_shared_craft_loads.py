"""In SHARED, a craft loadout template load, "move ground items to base" and, with oxceAlternateCraftEquipmentManagement
ON, the soldier and craft inventory screens end as host-applied craft_equip / craft_assign end-states, and a replica's
own option-ON staging triggers no world re-copy. Without the fix each stays on one machine until a restream reverts the
client. H / C / C2 as in test_shared_base_equip.setup() (option OFF). SKY(gc) = base_report HostBase craft {SKY id,
STR_SKYRANGER} items (whole map); ST(gc) = geo_state HostBase items; reqs / mm = the client's shared_resync_stats.
W = 10 s at 0.25 s; RW 5 s, HOLD 8 s. park = host open_soldiers (no heartbeat), unpark = host soldiers_ok; converge =
both on GeoscapeState (no CoopState / LoadGameState), SKY and ST equal, <= 30 s; every row starts with converge + client
shared_reset_resync_stats. (item, slot) = STR_PISTOL into the actor's left hand, else belt, else backpack (run time); a
soldier / craft screen SKY delta is {PISTOL +1, PISTOL_CLIP +1}. A row whose main cell (the one that fails without the
fix) fails evaluates no later cell.
Option-OFF boot (SHARED, 49427 / 49428 / 47927): loadout_load_syncs: template slot 1 = the SKY's items, two pistols off,
  park, client CES loadout_load 1 (the host applies the load and the client's screen follows it: its SKY PISTOL +2
  within W), OK; without the fix SKY(host) is unchanged after W. ground_to_base_syncs: park,
  client craft inventory ground_to_base, close; without the fix SKY(host) == the reply's before after W.
  world_equal_option_off: js.finish().
Option-ON boot (SHARED, 49429 / 49430 / 47928; setup: the option-OFF layouts settle, option ON on both, a host
  soldier-screen round trip with no edit, converge):
  partner_edit_refused (guard) parked client soldier screen, PISTOL onto H (the partner's): client SKY == before, host
  unchanged, reqs 0 over RW. soldier_screen_load_syncs: client soldier screen (C) / craft_screen_load_syncs: client
  craft screen (C2), parked; without the fix SKY(host) is unchanged after W. host_load_no_recopy: host soldier screen
  (H), client on its geoscape; without the fix reqs +1 within W. world_equal_option_on (guard) js.finish().
  open_screen_kept (LAST): host on its geoscape, the client's craft screen held HOLD; without the fix reqs +1 or the
  InventoryState gone (closed, or the client crashed); only after a FAILED open_screen_kept does the shutdown tolerate a
  dead client (rc 3, its crash log as EVIDENCE).
SEPARATE boot (labels 49431 / 49432, lobby 47929, option ON): separate_reaches_host (guard): ClientBase soldier screen on
  top 8 s, PISTOL onto its first soldier, close, craft screen round trip: SKY PISTOL / PISTOL_CLIP +1 on the client,
  the host's ClientBase SKY equal to the client's within W (one world: the host applies the client's edits).
EVIDENCE line per row before its verdict; a failed row prints ONE CAPTURE line (both machines' base_report, geo_state
items, soldier_layouts, shared_resync_stats, shared_stats, option_values, stacks); a boot miss fails its rows
"boot" with ONE CAPTURE line; a failed shutdown is a FAIL line. Every row runs after a failure. ONE run; exit 0 iff
everything passes, else 2.
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
import test_shared_base_equip as sbe  # noqa: E402  (main-guarded: setup, soldier screens, q / stack / wait_until)
import test_shared_base_writes as sbw  # noqa: E402  (main-guarded: bso, items, Row)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
from test_shared_base_equip import q, stack, wait_until  # noqa: E402
from test_shared_base_writes import bso  # noqa: E402

TAG_OPTION_OFF, PORTS_OPTION_OFF = "craft_loads_option_off", (49427, 49428, 47927)
TAG_OPTION_ON, PORTS_OPTION_ON = "craft_loads_option_on", (49429, 49430, 47928)
TAG_SEPARATE, LABELS_SEPARATE, LOBBY_SEPARATE = "craft_loads_separate", (49431, 49432), "47929"
HB, CB, GEO, OPT, SKYR = "HostBase", "ClientBase", "GeoscapeState", "oxceAlternateCraftEquipmentManagement", "STR_SKYRANGER"
PISTOL, CLIP, INV, CES = "STR_PISTOL", "STR_PISTOL_CLIP", "InventoryState", "CraftEquipmentState"
DELTA = {CLIP: 1, PISTOL: 1}  # every soldier / craft screen SKY delta (the moved pistol carries its clip)
W, POLL, RW, HOLD, CONV, SETTLE = 10.0, 0.25, 5.0, 8.0, 30.0, 1.0
ROWS_OPTION_OFF, ROWS_OPTION_ON, ROWS_SEPARATE = (
    ["loadout_load_syncs", "ground_to_base_syncs", "world_equal_option_off"],
    ["partner_edit_refused", "soldier_screen_load_syncs", "craft_screen_load_syncs", "host_load_no_recopy",
     "world_equal_option_on", "open_screen_kept"],
    ["separate_reaches_host"])
ORDER = ROWS_OPTION_OFF + ROWS_OPTION_ON + ROWS_SEPARATE


def timed(pred, timeout):
    t0 = time.time()
    v = wait_until(pred, timeout)
    return v, round(time.time() - t0, 2)


def sky(gc, cid, base=HB):
    """SKY(gc): the craft {cid, STR_SKYRANGER}'s whole item map from base_report (world_dump does not compare
    craft items)."""
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


def is_dead(s):  # sbe.stack's reply for a machine whose socket is gone
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
    """Both on GeoscapeState with no CoopState / LoadGameState, SKY and ST equal on both; a dead machine ends the
    wait."""
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
    """Every row's setup guard: converge + the client's shared_reset_resync_stats (the restream cooldown)."""
    c = converge(x)
    rep = q(x.client, {"cmd": "shared_reset_resync_stats"})
    r.ev[tag] = {"converge": [c["ok"], c["s"]], "sky host / client": [sky(x.host, x.sky), sky(x.client, x.sky)],
                 "reqs / mm": rs(x.client)}
    return r.cell(f"guard: converge + client shared_reset_resync_stats ({tag})", c["ok"] and rep.get("ok") is True, [c, rep])


def open_ces(r, gc, base, cid, inv=False):
    rep = q(gc, {"cmd": "open_craft_equipment", "base": base, "craft_id": cid})
    if not r.cell(f"guard: {gc.name} open_craft_equipment {base} {cid}", rep.get("ok") and rep.get("craftId") == cid
                  and wait_until(lambda: CES in stack(gc), 30), [rep, stack(gc)]):
        return False
    if not inv:
        return True
    rep = q(gc, {"cmd": "craft_inventory"})
    return r.cell(f"guard: {gc.name} craft_inventory", rep.get("opened") is True and wait_until(lambda: INV in stack(gc), 30),
                  [rep, stack(gc)])


def close_ces(r, gc, inv=False):
    if inv:
        rep = q(gc, {"cmd": "battle_inventory", "action": "ok"})
        r.cell(f"guard: {gc.name} battle_inventory ok", rep.get("ok") and wait_until(lambda: INV not in stack(gc), 30), [rep, stack(gc)])
    rep = q(gc, {"cmd": "craft_equipment_ok"})
    return r.cell(f"guard: {gc.name} craft_equipment_ok", rep.get("ok") and wait_until(lambda: CES not in stack(gc), 30),
                  [rep, stack(gc)])


def edit(r, gc, name):
    """(item, slot) on gc's open base inventory: select `name` (base_screen_op), STR_PISTOL into its left hand, else
    belt, else backpack (read at run time)."""
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
    return r.cell("guard: park (host SoldiersState on top)", rep.get("ok") and wait_until(lambda: top(x.host) == "SoldiersState", 10),
                  [rep, stack(x.host)])


def release(r, x):
    """unpark; the client's reqs / mm over RW; converge (the cleanup without the fix: the restream reverts the
    client)."""
    rep = q(x.host, {"cmd": "soldiers_ok"})
    up = bool(wait_until(lambda: top(x.host) == GEO, 10, 0.05))
    rel = {"unpark": [rep.get("ok"), up], "over RW": watch(x, RW)}
    rel["converge"] = converge(x)
    r.ev["release"] = rel
    rel["ok"] = r.cell("guard: unpark + converge after the row", up and rel["converge"]["ok"], rel)
    return rel


def parked(r, x, act):
    """Park, the client's `act` (its values, or None after a failed setup cell), the host read over W (until SKY and ST
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


def check_sync(r, w, rel, main_cell, main_ok):
    """The main cell (the one that fails without the fix), then the sync cells (a failed main cell evaluates no later
    cell)."""
    if not r.cell(main_cell, main_ok, {"host before": w["host before"], "host after W": w["host sky"]}):
        return
    if r.cell("SKY and ST not equal on both within W", w["equal"], w):
        r.cell("the client asked for a world re-copy over RW after the unpark", rel["over RW"]["reqs"] == 0, rel["over RW"])


def row_loadout_load(x, r):
    h, c = x.host, x.client
    if not guard(r, x):
        return
    # setup: template slot 1 = the SKY's items (the client's loadout_save reaches the host, as in
    # test_shared_base_writes' base_write_5), then two pistols off (craft_equip)
    opened = open_ces(r, c, HB, x.sky)
    save = bso(c, op="loadout_save", index=1) if opened else {}
    close_ces(r, c)
    got, s = timed(lambda: bso(h, op="read", index=1).get("loadout") == save.get("loadout"), W)
    b = {g.name: [sky(g, x.sky) or {}, st(g)] for g in (h, c)}
    ce = q(c, {"cmd": "craft_equip", "item": PISTOL, "count": -2, "base": HB, "craft_id": x.sky})
    off, s2 = timed(lambda: all((sky(g, x.sky) or {}).get(PISTOL, 0) == b[g.name][0].get(PISTOL, 0) - 2
                                and st(g).get(PISTOL, 0) == b[g.name][1].get(PISTOL, 0) + 2 for g in (h, c)), W)
    r.ev["setup"] = {"loadout_save 1": save.get("loadout"), "host read 1 s": s, "craft_equip": ce, "pistols -2 s": s2}
    if not (r.cell("guard: client loadout_save 1 == the SKY's items", opened and save.get("loadout") == b["client"][0], save)
            and r.cell("guard: the host's loadout 1 == the client's within W", got, s)
            and r.cell("guard: craft_equip STR_PISTOL -2 on both within W", ce.get("moved") is True and off, [ce, s2])
            and guard(r, x, "after the setup")):
        r.evidence()
        return

    def act():
        if not open_ces(r, c, HB, x.sky):
            return None
        c0 = sky(c, x.sky)
        load = bso(c, op="loadout_load", index=1)
        # the host applies the load; the client's screen follows when the apply lands
        got, s = timed(lambda: diff(c0, sky(c, x.sky)).get(PISTOL) == 2, W)
        c1 = sky(c, x.sky)
        close_ces(r, c)
        return {"loadout_load": load, "client sky before": c0, "client SKY +2 within (s)": s if got else None,
                "client SKY diff before OK": diff(c0, c1), "client SKY diff after OK": diff(c0, sky(c, x.sky))}
    a, w, rel = parked(r, x, act)
    r.ev.update({"load": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w):
        return
    if not r.cell("non-vacuity: the client's SKY PISTOL +2 within W", a["loadout_load"].get("ok") is True
                  and a["client SKY +2 within (s)"] is not None, a):
        return
    check_sync(r, w, rel, "the client's craft loadout load never reached the host", w["host sky"] != w["host before"])


def row_ground_to_base(x, r):
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
    check_sync(r, w, rel, "the client's move-ground-to-base never reached the host",
               w["host sky"] != dict(sorted(bef.items())))


def finish(x, r):
    """world_equal_option_off / world_equal_option_on (guard): world equality + replica zero-disk."""
    r.ev.update({"world_diff now": shared_fixture.world_diff(x.host, x.client), "client save files now": session.save_files(
        x.js.client_dir), "sky host / client": [sky(x.host, x.sky), sky(x.client, x.sky)]})
    r.evidence()
    try:
        x.js.finish()
    except AssertionError as e:
        r.cell("js.finish", False, sbe.short(e, 1500))


def setup_option_on(x):
    """The layouts settle (option OFF: each machine opens and closes its soldier screen, then the whole layouts are
    equal), the option ON on both (set_option on each machine), a host soldier-screen round trip with no edit,
    converge. Raises on a miss (the boot's rows fail "boot" with its CAPTURE)."""
    r, h, c = Row("option-ON setup", x), x.host, x.client
    whole_layouts = lambda gc: {e.get("id"): sbe.whole(e)  # noqa: E731
                                for e in q(gc, {"cmd": "soldier_layouts", "base": HB}).get("soldiers") or []}
    for gc in (h, c):
        if sbe.open_soldier_screen(r, gc):
            sbe.close_soldier_screen(r, gc)
    eq, s = timed(lambda: whole_layouts(h) == whole_layouts(c), W)
    L = whole_layouts(h)
    crew = [e.get("id") for e in q(h, {"cmd": "base_report", "base": HB}).get("soldiers") or [] if e.get("craft") == x.sky]
    empty = [i for i in crew if not (L.get(i) or [None])[0]]
    so = {gc.name: q(gc, {"cmd": "set_option", "name": OPT, "value": True}) for gc in (h, c)}
    on = {gc.name: opt(gc) for gc in (h, c)}
    h0 = sky(h, x.sky)
    if sbe.open_soldier_screen(r, h):
        sbe.close_soldier_screen(r, h)
    h1 = sky(h, x.sky)
    cv = converge(x)
    x.setup = {"layouts equal": [bool(eq), s], "SKY crew": crew, "SKY crew with an empty layout": empty, "set_option": so,
               "option": on, "host round trip SKY diff": diff(h0, h1), "converge": [cv["ok"], cv["s"]], "sky": sky(h, x.sky)}
    if r.fails or not eq or not crew or empty or on != {"host": True, "client": True} or not cv["ok"]:
        raise RuntimeError(f"option-ON setup: {r.fails} {json.dumps(x.setup, default=str)}")


def row_partner_edit(x, r):
    h, c = x.host, x.client
    r.ev["option-ON setup"] = x.setup
    if not guard(r, x):
        return

    def act():
        c0 = sky(c, x.sky)
        if not sbe.open_soldier_screen(r, c):
            return None
        e = edit(r, c, x.H)
        sbe.close_soldier_screen(r, c)
        return {"moved": e, "client sky before": c0, "client SKY diff at once": diff(c0, sky(c, x.sky)), "host sky": sky(h, x.sky)}
    a, w, rel = parked(r, x, act)
    r.ev.update({"edit": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w and r.cell("guard: STR_PISTOL moved onto H", a["moved"], a)):
        return
    r.cell("the client's SKY changed after a partner edit", a["client SKY diff at once"] == {}, a)
    r.cell("the host's SKY changed", w["host sky"] == w["host before"], w)
    r.cell("the client asked for a world re-copy over RW after the unpark", rel["over RW"]["reqs"] == 0, rel["over RW"])


def client_edit(x, r, who, craft, main_cell):
    """soldier_screen_load_syncs (soldier screen) / craft_screen_load_syncs (craft screen, the staging): the client
    moves STR_PISTOL onto its own `who`, parked."""
    c = x.client
    if not guard(r, x):
        return

    def act():
        c0 = sky(c, x.sky)
        if not (open_ces(r, c, HB, x.sky, inv=True) if craft else sbe.open_soldier_screen(r, c)):
            return None
        e = edit(r, c, getattr(x, who))
        close_ces(r, c, inv=True) if craft else sbe.close_soldier_screen(r, c)
        return {"moved": e, "client sky before": c0, "client SKY diff after the close": diff(c0, sky(c, x.sky))}
    a, w, rel = parked(r, x, act)
    r.ev.update({"edit": a, "host over W": w})
    r.evidence()
    if not (rel["ok"] and a and w and r.cell(f"guard: STR_PISTOL moved onto {who}", a["moved"], a)):
        return
    if not r.cell(f"non-vacuity: the client's SKY diff == {DELTA}", a["client SKY diff after the close"] == DELTA, a):
        return
    check_sync(r, w, rel, main_cell, w["host sky"] != w["host before"])


def row_host_load(x, r):
    h, c = x.host, x.client
    if not guard(r, x):
        return
    gv = r.ev["give STR_PISTOL 1"] = {g.name: q(g, {"cmd": "give_items", "item": PISTOL, "count": 1, "base": HB}) for g in (c, h)}
    if not r.cell("guard: give_items STR_PISTOL 1 on both, client first", all(v.get("ok") for v in gv.values()), gv):
        return
    h0 = sky(h, x.sky)
    if not sbe.open_soldier_screen(r, h):
        return
    e = edit(r, h, x.H)
    sbe.close_soldier_screen(r, h)
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
    cv = converge(x)  # the cleanup without the fix (the restream already landed on the client's geoscape)
    r.ev.update({"moved": e, "host SKY diff": hd, "first req s": first, "equal s": eq, "over RW": over, "converge": cv,
                 "sky host / client end": [sky(h, x.sky), sky(c, x.sky)]})
    r.evidence()
    if not (r.cell("guard: converge after the row", cv["ok"], cv) and r.cell("guard: STR_PISTOL moved onto H", e, r.ev.get("host edit"))):
        return
    if not r.cell(f"non-vacuity: the host's SKY diff == {DELTA}", hd == DELTA, hd):
        return
    if not r.cell("the host's soldier-screen craft load reached the client only by a world re-copy", first is None and over["reqs"] == 0,
                  {"first req s": first, "over RW": over}):
        return
    r.cell("SKY and ST not equal on both within W", eq is not None, eq)


def row_open_screen_kept(x, r):
    h, c = x.host, x.client
    if not guard(r, x):
        return
    if not (r.cell("guard: the host idle on its geoscape", stack(h) == [GEO], stack(h)) and open_ces(r, c, HB, x.sky, inv=True)):
        r.evidence()
        return
    t0, sh, sc = time.time(), st(h), st(c)
    first, gone, tops = None, None, []
    while time.time() - t0 < HOLD:  # the screen must stay on top through HOLD (a crashed client counts as gone)
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
        cv = converge(x)  # the cleanup without the fix (a dead client ends it at once)
    r.ev.update({"ST diff (host -> client) at open": diff(sh, sc), "first req s": first, "gone": gone, "tops (thinned)": tops[::4],
                 "reqs / mm before the close": last, "equal after the close": [bool(eq), s_eq], "cleanup converge": cv})
    r.evidence()
    if not r.cell("non-vacuity: the client's ST != the host's while open", sh != sc, diff(sh, sc)):
        return
    if not r.cell("the client's open craft screen was closed by a world re-copy", first is None and gone is None,
                  {"first req s": first, "gone": gone}):
        return
    r.cell("reqs / mm changed before the close", last == [0, 0], last)
    r.cell("SKY and ST not equal on both within W after the close", bool(eq), s_eq)


def row_separate_reaches_host(x, r):
    h, c = x.host, x.client
    so = {g.name: q(g, {"cmd": "set_option", "name": OPT, "value": True}) for g in (h, c)}
    on = {g.name: opt(g) for g in (h, c)}
    rep = q(c, {"cmd": "base_report", "base": CB})
    sid = next((cr.get("id") for cr in rep.get("crafts") or [] if cr.get("type") == SKYR), None)
    first = ((rep.get("soldiers") or [{}])[0]).get("name")
    s0, k0 = {g.name: sbe.stats3(g) for g in (h, c)}, sky(c, sid, CB)
    r.ev.update({"set_option": so, "option": on, "ClientBase SKY": [sid, k0], "first soldier": first})
    if not (r.cell("guard: option ON on both", on == {"host": True, "client": True}, [so, on])
            and r.cell("guard: a ClientBase SKYRANGER and a first soldier", sid is not None and first and k0 is not None, [sid, first])
            and sbe.open_soldier_screen(r, c, CB)):
        r.evidence()
        return
    held = [time.sleep(1.0) or top(c) for _ in range(8)]  # the top state once a second for 8 s
    e = edit(r, c, first)
    sbe.close_soldier_screen(r, c)
    k1 = sky(c, sid, CB)
    if open_ces(r, c, CB, sid, inv=True):
        close_ces(r, c, inv=True)
    k2 = sky(c, sid, CB)
    time.sleep(SETTLE)
    s1 = {g.name: sbe.stats3(g) for g in (h, c)}
    d = diff(k0, k1)
    eq, s_eq = timed(lambda: sky(h, sid, CB) == sky(c, sid, CB), W)
    r.ev.update({"top each second": held, "SKY diff (soldier screen)": d, "SKY diff (craft round trip)": diff(k1, k2),
                 "shared_stats before": s0, "shared_stats 1 s after": s1,
                 "host / client SKY within W": [sky(h, sid, CB), sky(c, sid, CB), s_eq]})
    r.evidence()
    r.cell("guard: STR_PISTOL moved onto the first soldier", e, r.ev.get("client edit"))
    r.cell("the InventoryState left the top within 8 s", held == [INV] * 8, held)
    r.cell("the client's ClientBase SKY PISTOL / PISTOL_CLIP not +1", d.get(PISTOL) == 1 and d.get(CLIP) == 1, d)
    r.cell("the host's ClientBase SKY not equal to the client's within W", bool(eq), r.ev["host / client SKY within W"])


def boot_miss(tag, e, rids, results, x=None):
    cap = {"error": sbe.short(e, 1500)}
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
            r.cell(f"guard: {rid} exception", False, sbe.short(e))
        for g in (x.host, x.client):  # a stopped row leaves no screen behind; a dead client (open_screen_kept failing)
            # is left to the shutdown
            before = stack(g)
            if not is_dead(before) and (before or [""])[-1] != GEO:
                rep = q(g, {"cmd": "close_screens"})
                wait_until(lambda: top(g) == GEO, 5.0)
                r.cap[f"{g.name} cleanup"] = {"before": before, "close_screens": rep, "after": stack(g)}
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)


def crash_logs(js):
    roots = [harness.CRASH_DIR, js.host_dir, js.client_dir]  # (this harness slot's own crash folder)
    return {p for root in roots for p in glob.glob(os.path.join(root, "**", "crash_*.log"), recursive=True)}


def down(tag, results, fn):
    """A boot's shutdown; a failure is a FAIL line `shutdown <tag>` (exit 2), and the run goes on."""
    try:
        fn()
    except Exception as e:
        results["shutdown " + tag] = False
        print(f"FAIL shutdown {tag}: {sbe.short(e, 800)}", flush=True)


def down_option_on(js, results, crash0):
    """Only after a FAILED open_screen_kept is a dead client (rc 3) tolerated, its new crash log printed as EVIDENCE."""
    try:
        js.host.shutdown()
    finally:
        rc = js.client.proc.poll() if js.client.proc else None
        if results.get("open_screen_kept") is False and rc == 3:
            logs = {p: open(p, "r", encoding="utf-8", errors="replace").read()[:2500] for p in sorted(crash_logs(js) - crash0)}
            print(f"EVIDENCE open_screen_kept shutdown (dead client tolerated): "
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
            x = sbe.X(js.host, js.client, js)
            sbe.setup(x)  # option OFF on both, seats differ, H / C / C2, the SKYRANGER, the HostBase index (raises on a miss)
            if setup:
                setup(x)
            walls["boot " + tag] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every row of this boot "boot" with ONE CAPTURE line
            return boot_miss(tag, e, rids, results, x)
        run_rows(x, rows, results, walls)
    finally:
        if js is not None:
            down(tag, results, (lambda: down_option_on(js, results, crash0)) if tag == TAG_OPTION_ON else js.shutdown)


def boot_separate(results, walls):
    t0 = time.time()
    h = GameClient("host", LABELS_SEPARATE[0], make_user_dir(TAG_SEPARATE + "_host"))
    c = GameClient("client", LABELS_SEPARATE[1], make_user_dir(TAG_SEPARATE + "_client"))
    x = sbe.X(h, c, base=CB)
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=LOBBY_SEPARATE, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            x.seats = {gc.name: q(gc, {"cmd": "get_coop"}).get("localSeat") for gc in (h, c)}
            walls["boot " + TAG_SEPARATE] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails separate_reaches_host "boot" with ONE CAPTURE line
            return boot_miss(TAG_SEPARATE, e, ROWS_SEPARATE, results, x)
        run_rows(x, (("separate_reaches_host", row_separate_reaches_host),), results, walls)
    finally:
        down(TAG_SEPARATE, results, lambda: shutdown_clients(h, c))


def main():
    t0, results, walls = time.time(), {}, {}
    shared_boot(TAG_OPTION_OFF, PORTS_OPTION_OFF, ROWS_OPTION_OFF, (
        ("loadout_load_syncs", row_loadout_load), ("ground_to_base_syncs", row_ground_to_base),
        ("world_equal_option_off", finish)), results, walls)
    shared_boot(TAG_OPTION_ON, PORTS_OPTION_ON, ROWS_OPTION_ON, (
        ("partner_edit_refused", row_partner_edit),
        ("soldier_screen_load_syncs", lambda x, r: client_edit(
            x, r, "C", False, "the client's soldier-screen craft load never reached the host")),
        ("craft_screen_load_syncs", lambda x, r: client_edit(
            x, r, "C2", True, "the client's craft-screen load never reached the host")),
        ("host_load_no_recopy", row_host_load), ("world_equal_option_on", finish),
        ("open_screen_kept", row_open_screen_kept)), results, walls, setup_option_on)
    boot_separate(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    downs = sorted(k for k, v in results.items() if k.startswith("shutdown") and not v)
    print(f"\ntest_shared_craft_loads: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed + downs}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed or downs else 0


if __name__ == "__main__":
    sys.exit(main())
