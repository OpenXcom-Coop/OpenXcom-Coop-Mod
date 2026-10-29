"""test_equip_hold_ends.py: a reservation on the pre-battle equip screen also ends when its holder leaves or turn 1
starts, and no bulk tool takes a reserved item. A leave during equip ends the leaver's hold; turn 1 puts every cursor
item back; the host's own template and auto-equip skip a held item, and so does a client's bulk order. Held items are
read by id, never by pile cell.
Boot holder_leaves (co-op, KEY_C, dirs equip_hold_ends_leave_*): test_prebattle_equip.py's spine plus a staging
(copied, never imported; client first, after the client applied the host's first evs): C1, C2 stripped; STAGE_TYPES +
HOLD_EXTRA on PILE.
  holder_leaves  the client picks the 2-clip cell (precondition: the host's holds.table[clientSeat] = it within
     W_HOLD), its pointer drawn on the host; client.kill(); once the host's authority.peerAbsent is true:
     holder_leaves-back (the held id on the host's page within W_END), holder_leaves-once (ends.leave delta 1, every
     other 0), holder_leaves-ptr (GUARD: the host's drawn.ptr false within W_END). It ends the boot.
Boot tools_and_turn (co-op, KEY_C reused, dirs equip_hold_ends_tools_*): the same spine + EXTRA_S (spare stock: a
build whose tools take a held item consumes the first ones).
  auto_equip  H1 stripped, given an unloaded STR_RIFLE (vanilla's auto-equip takes clips only for a held weapon); the
     client picks the first STR_RIFLE_CLIP in tile order; the host's auto-equip key: auto_equip-skips_held (the held
     id on PILE on both, never on H1)
  template_apply  H1 stripped, given a rifle and a belt clip, create_template (real click), stripped; the client picks
     the first clip; the host's apply_template: template_apply-skips_held (the held id on PILE on both, never on H1;
     TEXT_SHORT shown exactly when it was the only clip)
  bulk_order  the host picks the first STR_GRENADE; the client's auto-equip key on C1 (an inv_bulk order):
     bulk_order-skips_held (GUARD: answered within W_HOLD, the host's held grenade on C1 on neither machine)
  turn_start  the client's ready (real OK), then its pick of the single STR_GRENADE cell; the host's ready -> turn 1:
     turn_start-once (the host's ends.start delta 1), turn_start-pile (GUARD: that id on PILE on both),
     turn_start-clear (the client's holds.table all -1, localHeld -1)
  END  no_crash (GUARD: no new crash file, the host alive at the end of each boot)
holds = event_state.equip.presence.holds; ends cells read the row's delta. Every row ends with both cursors empty (a
failed cleanup ends the boot's later rows "not reached"). A build with the hold table but without these ends fails
holder_leaves-back, holder_leaves-once, turn_start-once, turn_start-clear, auto_equip-skips_held and
template_apply-skips_held (6 of 10) and passes holder_leaves-ptr, turn_start-pile, bulk_order-skips_held and no_crash.
One EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure (a
precondition miss ends its own row); a boot step past its bound prints ONE CAPTURE line and fails that boot's rows
"boot". run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.
Run:  python tools/coop_test/test_equip_hold_ends.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
from test_host_combat import bring_up_lobby_roster_pinned  # noqa: E402
from test_delta_core import both, diff_buckets  # noqa: E402
from test_delta_items import items_by_id  # noqa: E402
from test_client_items import strip_both  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

# ----- pinned setup values (the spine's as in test_prebattle_equip.py) -----
KEY_C = "49285"                    # lobby key: boot holder_leaves, then boot tools_and_turn after its shutdown
SEED_MAP = 1                       # set_seed right before newbattle_ok
MAP_FP = -4.48310638993e+18        # the host's mapFingerprint at SEED_MAP 1
C_IDS, H_IDS = [8, 9], [10, 11, 12, 13, 14]   # the client's seated units, the host's own soldiers
C1, C2, H1 = 8, 9, 10              # C1 = the client's screen, H1 = the host's screen
PILE = (14, 19, 1)                 # the craft pile tile at turn 0
STAGE_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE", "STR_SMOKE_GRENADE")
HOLD_EXTRA = "STR_RIFLE_CLIP"      # the clip cell holds a stack of 2
EXTRA_S = ("STR_RIFLE_CLIP", "STR_GRENADE")   # boot tools_and_turn only
RIFLE_T, CLIP_T, GRENADE_T = "STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE"
GROUND, BELT = "STR_GROUND", "STR_BELT"
GROUND_COLS = 20                   # the first ground page (a held item is parked at x 1000000)
SCALE, CLIENT_PT = 2, (150, 120)   # window / logical; the client's pointer on the Inventory surface
TEXT_SHORT = "Not enough items to copy template!"   # STR_NOT_ENOUGH_ITEMS_FOR_TEMPLATE
W_HOLD, W_PTR, W_END, DROP_WAIT_S = 2.0, 2.0, 3.0, 30.0
CLICK_WAIT_S, LAND_WAIT_S, ANSWER_WAIT_S, TURN_WAIT_S = 2.0, 10.0, 3.0, 5.0
LINE_READ_S, KEY_SETTLE_S, SETTLE_S, POLL_S = 1.5, 0.3, 0.5, 0.05
BRIEFING_WAIT_S, ENTRY_WAIT_S, SCREEN_S = 30.0, 5.0, 15.0
ENDS = ("put", "answer", "cancel", "deny", "move", "leave", "start")
EXPECTED_RC = (0, 3221226505)
ROWS_L = (("holder_leaves", ("holder_leaves-back", "holder_leaves-once", "holder_leaves-ptr")),)
ROWS_S = (("auto_equip", ("auto_equip-skips_held",)), ("template_apply", ("template_apply-skips_held",)),
          ("bulk_order", ("bulk_order-skips_held",)),
          ("turn_start", ("turn_start-once", "turn_start-pile", "turn_start-clear")))
ROWS_X = (("END", ("no_crash",)),)
CPU_CSV = os.path.join(tempfile.gettempdir(), "equip_hold_ends_cpu_s%d.csv" % harness.HARNESS_SLOT)


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # a dead instance
        return [f"<no stack: {str(e)[:120]}>"]


es = event_state
equip = lambda gc: es(gc).get("equip") or {}  # noqa: E731
turn = lambda gc: battle_state(gc).get("turn")  # noqa: E731
authority = lambda gc: battle_state(gc).get("authority") or {}  # noqa: E731
cursor = lambda gc: inv_view(gc).get("selectedItem")  # noqa: E731
holds = lambda gc: (equip(gc).get("presence") or {}).get("holds")  # noqa: E731 - None when the build has none
table = lambda gc: (holds(gc) or {}).get("table") or [-1, -1, -1, -1]  # noqa: E731
drawn = lambda gc: (equip(gc).get("presence") or {}).get("drawn") or {}  # noqa: E731
delta = lambda after, before: {k: after[k] - before[k] for k in ENDS}  # noqa: E731
unit_items = lambda its, uid: {i: it for i, it in its.items() if it.get("owner") == uid}  # noqa: E731
unit_brief = lambda its, uid: sorted([i, it.get("type"), it.get("slot")] for i, it in unit_items(its, uid).items())  # noqa
screen_up = lambda gc: (lambda v: v.get("open") is True and v.get("top") is True and v.get("preBattle") is True)(  # noqa: E731
    inv_view(gc))
at_cell = lambda gc, cell: [g["id"] for g in (inv_view(gc).get("ground") or [])  # noqa: E731
                            if (g.get("x"), g.get("y")) == tuple(cell)]
on_page = lambda gc, iid: (lambda c: c is not None and c[0] is not None and 0 <= c[0] < GROUND_COLS)(cell_of(gc, iid))  # noqa
on_pile = lambda it: bool(it) and it.get("onTile") is True and it.get("owner") in (None, -1) \
    and (it.get("tx"), it.get("ty"), it.get("tz")) == PILE  # noqa: E731
click = lambda gc, **kw: (lambda r: {"req": kw, "ok": r.get("ok"), "error": r.get("error")})(  # noqa: E731
    gc.cmd(dict({"cmd": "inventory_click"}, **kw)))
key = lambda gc, sym: (lambda r: {"key": sym, "ok": r.get("ok"), "error": r.get("error")})(  # noqa: E731
    gc.cmd({"cmd": "inject_input", "kind": "key", "key": sym}))


def alive(gc):
    if gc.proc is None or gc.proc.poll() is not None:
        return False
    try:
        return bool(gc.cmd({"cmd": "ping"}).get("pong"))
    except Exception:
        return False


def inv_view(gc):
    r = gc.cmd({"cmd": "inventory_view"})
    if not r.get("ok"):
        return {"error": r.get("error"), "open": None, "ground": []}
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "ground", "preBattle", "okPressed", "lineText",
                                  "lineVisible")}


def wait_until(pred, timeout, interval=POLL_S):
    """Poll `pred` (bounded). Returns (value or None, seconds waited)."""
    t0 = time.time()
    while True:
        v = pred()
        if v:
            return v, round(time.time() - t0, 3)
        if time.time() - t0 > timeout:
            return None, round(time.time() - t0, 3)
        time.sleep(interval)


def cpu_pct(mean=False):
    v = []
    try:
        with open(CPU_CSV, encoding="utf-8", errors="replace") as f:
            for ln in list(f)[1:]:
                try:
                    v.append(float(ln.split(",")[1].strip().strip('"')))
                except (ValueError, IndexError):
                    pass
    except OSError:
        return None
    return None if not v else round(sum(v) / len(v) if mean else v[-1], 1)


def miss(tag, what, m):
    G3F.capture(tag, what, m)
    raise G3F.Miss(tag)


def cell_of(gc, iid):
    """(x, y) of id `iid` on gc's ground (x 1000000 = parked off the page), None when it is not on the screen's tile."""
    for g in inv_view(gc).get("ground") or []:
        if g.get("id") == iid:
            return (g.get("x"), g.get("y"))
    return None


def ends(gc):
    e = (holds(gc) or {}).get("ends") or {}
    return {k: e.get(k) or 0 for k in ENDS}


def of_type(gc, t):
    """Ids of type `t` on gc's screen tile in TILE ORDER (inventory_view.ground lists the tile inventory in order)."""
    its = items_by_id(gc)
    return [g["id"] for g in (inv_view(gc).get("ground") or []) if (its.get(g["id"]) or {}).get("type") == t]


def settled(host, client, uid):
    """`uid`'s items and the pile equal on both machines, nothing in flight on the client."""
    ih, ic = items_by_id(host), items_by_id(client)
    pile = [sorted(i for i, it in its.items() if on_pile(it)) for its in (ih, ic)]
    return unit_items(ih, uid) == unit_items(ic, uid) and pile[0] == pile[1] and es(client).get("inFlight") is None


def where(host, client, iid, uid):
    """`iid` on PILE on both machines and on `uid` on neither: (ok, record)."""
    ih, ic = items_by_id(host), items_by_id(client)
    rec = {"pile": [on_pile(ih.get(iid)), on_pile(ic.get(iid))],
           "unit": {"host": unit_brief(ih, uid), "client": unit_brief(ic, uid)}}
    return rec["pile"] == [True, True] and all(iid not in [i[0] for i in u] for u in rec["unit"].values()), rec


def pick(gc, cell, want):
    """Left-click ground `cell` with an empty cursor; one of `want` must land on the cursor (else the row's precondition fails)."""
    if cell is None:
        raise AssertionError(f"precondition: no ground cell for {want} on {gc.name}'s screen")
    rec = {"machine": gc.name, "cell": cell, "atCell": at_cell(gc, cell), "cursorBefore": cursor(gc)}
    rec["click"] = click(gc, slot=GROUND, x=cell[0], y=cell[1])
    got, rec["waited"] = wait_until(lambda: cursor(gc) not in (None, -1), CLICK_WAIT_S)
    rec["picked"] = cursor(gc) if got else None
    if rec["picked"] not in want:
        raise AssertionError(f"precondition: {gc.name}'s pick at {cell} put {rec['picked']} on its cursor (want one of {want}; "
                             f"{rec})")
    return rec["picked"], rec


def held_by(host, seat, iid, ev):
    """Precondition: the host's holds.table[seat] = iid within W_HOLD (the hold table's grant, or the host's own
    sample)."""
    _, ev["tableWithin"] = wait_until(lambda: table(host)[seat] == iid, W_HOLD)
    ev["hostTable"] = table(host)
    if ev["hostTable"][seat] != iid:
        raise AssertionError(f"precondition: host holds.table {ev['hostTable']} (want [{seat}] = {iid} within {W_HOLD} s)")


def give_back(gc, ev, k):
    """The holder's right-click (vanilla's return), only with an item on the cursor (an empty-cursor right-click primes)."""
    if cursor(gc) not in (None, -1):
        ev[k] = click(gc, slot=GROUND, x=0, y=0, button="right")
        wait_until(lambda: cursor(gc) == -1, CLICK_WAIT_S)
    return cursor(gc) == -1


def cleanup(host, client, ctx, ev):
    ok = give_back(client, ev, "clientReturn") and give_back(host, ev, "hostReturn")
    ev["cursorsAfter"] = [cursor(host), cursor(client)]
    if not ok:
        ctx["broken"] = f"cursors host/client {ev['cursorsAfter']} after the cleanup"


def ready(host, client, ctx):
    """A row's head: both pre-battle screens up, both cursors empty."""
    if ctx.get("broken"):
        raise AssertionError(f"not reached: an earlier row's cleanup failed ({ctx['broken']})")
    if not (screen_up(host) and screen_up(client)):
        raise AssertionError(f"precondition: screens up host {screen_up(host)} client {screen_up(client)} (stacks {stack(host)} / "
                             f"{stack(client)})")
    if cursor(client) != -1 or cursor(host) != -1:
        raise AssertionError(f"precondition: cursors host {cursor(host)} client {cursor(client)} (want empty)")


def look(host, client):
    return {gc.name: ({"top": stack(gc)[-1:], "view": {k: v for k, v in inv_view(gc).items() if k != "ground"},
                       "holds": holds(gc), "drawn": drawn(gc), "peerAbsent": authority(gc).get("peerAbsent")}
                      if alive(gc) else "not running") for gc in (host, client)}


def spine(host, client, tag, extra):
    m = (host, client)
    ctx = {"m": m, "boot": {}}
    G3F.guarded(tag, lambda: bring_up_lobby_roster_pinned(host, client, KEY_C), m)
    seated = {}
    G3F.guarded(tag, lambda: session.bring_up_to_briefings(
        host, client, seated, seat_count=2, pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    hb = battle_state(host)
    sid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    got = {"mapFingerprint": hb.get("mapFingerprint"), "seated": [sid.get(s) for s in seated.get("soldierIds", [])],
           "hIds": sorted(u["id"] for u in hb.get("units", []) if u.get("coop") == 0 and u.get("faction") == 0
                          and not u.get("isOut"))}
    ctx["boot"].update(got)
    if (got["mapFingerprint"], got["seated"], got["hIds"]) != (MAP_FP, C_IDS, H_IDS):
        miss(tag, f"the spine: {got} (want MAP_FP {MAP_FP}, seated {C_IDS}, H {H_IDS})", m)
    ok, ctx["boot"]["clientBriefingS"] = wait_until(lambda: any("BriefingState" in s for s in stack(client))
                                                    and battle_state(client).get("inBattle") is True, BRIEFING_WAIT_S,
                                                    0.1)
    if not ok:
        miss(tag, f"no client BriefingState with its battle within {BRIEFING_WAIT_S} s", m)
    G3F.guarded(tag, lambda: session.wait_seq_barrier(host, client), m)   # the host's first evs applied before staging

    def stage():
        rec = {"stripped": {uid: strip_both(host, client, uid) for uid in (C1, C2)}, "ids": {}}
        for t in STAGE_TYPES + (HOLD_EXTRA,) + tuple(extra):
            rec["ids"].setdefault(t, []).append(both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1],
                                                                     "z": PILE[2], "item": t}, ("ids",))["ids"][0])
        rec["diff"] = diff_buckets(host, client)
        return rec
    st = ctx["boot"]["staged"] = G3F.guarded(tag, stage, m)
    if st["diff"]:
        miss(tag, f"buckets differ after the staging: {st['diff']}", m)
    ctx["boot"]["clientClose"] = client.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    if not ok:
        miss(tag, f"the client's pre-battle screen not up within {ENTRY_WAIT_S} s after its briefing closed", m)
    ctx["boot"]["hostClose"] = host.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss(tag, f"the host's pre-battle screen not up within {SCREEN_S} s after its briefing closed", m)
    ctx["seat"] = authority(client).get("localSeat")
    ctx["units"] = [inv_view(gc).get("unitId") for gc in m]
    lay = {gc.name: {i: cell_of(gc, i) for ids in st["ids"].values() for i in ids} for gc in m}
    ctx["boot"].update(seatClient=ctx["seat"], units=ctx["units"], layout=lay)
    if ctx["units"] != [H1, C1] or lay["host"] != lay["client"] or \
            not all(c and 0 <= c[0] < GROUND_COLS for c in lay["host"].values()):
        miss(tag, f"screens on {ctx['units']} (want [{H1}, {C1}]); staged cells {lay} (want equal page-1 cells on both)", m)
    ctx["autoKey"] = {gc.name: (gc.cmd({"cmd": "equip_layouts", "index": 0}).get("keys") or {}).get("keyInvAutoEquip")
                      for gc in m}
    ctx["ids"] = st["ids"]
    print(f"[test_equip_hold_ends] boot {tag}: {json.dumps(ctx['boot'], sort_keys=True,
                                                           default=str)} keys {ctx['autoKey']}", flush=True)
    return ctx


def boot_holder_leaves(host, client):
    ctx = spine(host, client, "holder_leaves", ())
    c = cell_of(client, ctx["ids"][CLIP_T][0])
    ctx["stack"] = {"client": c, "host": cell_of(host, ctx["ids"][CLIP_T][0]), "ids": sorted(at_cell(client, c))}
    if ctx["stack"]["ids"] != sorted(ctx["ids"][CLIP_T]) or sorted(at_cell(host, ctx["stack"]["host"])) != ctx["stack"]["ids"]:
        miss("holder_leaves",
             f"the 2-clip cell: {ctx['stack']} (want the two staged clips at one cell on both screens)", ctx["m"])
    return ctx


def row_holder_leaves(host, client, ctx, ev):
    ready(host, client, ctx)
    x, ev["pick"] = pick(client, ctx["stack"]["client"], ctx["stack"]["ids"])
    held_by(host, ctx["seat"], x, ev)
    ev["hostCount"] = [len(at_cell(host, ctx["stack"]["host"]))]
    inv = client.cmd({"cmd": "cursor_pos"})
    want = [inv.get("invX", 0) + CLIENT_PT[0], inv.get("invY", 0) + CLIENT_PT[1]]
    ev["motion"] = client.cmd({"cmd": "inject_input", "kind": "motion", "x": want[0] * SCALE, "y": want[1] * SCALE}).get("ok")
    _, ev["drawnWithin"] = wait_until(lambda: drawn(host).get("ptr") is True, W_PTR)
    ev["drawnBefore"] = drawn(host)
    if ev["drawnBefore"].get("ptr") is not True:
        raise AssertionError(f"precondition: the client's pointer not drawn on the host within {W_PTR} s ({ev['drawnBefore']}; "
                             f"motion to {want})")
    e0 = ends(host)
    client.kill()
    got, ev["peerAbsentWithin"] = wait_until(lambda: authority(host).get("peerAbsent") is True, DROP_WAIT_S)
    if not got:
        raise AssertionError(f"precondition: the host's authority.peerAbsent not true within {DROP_WAIT_S} s of the kill")
    back = off = None
    t0 = time.time()
    while time.time() - t0 <= W_END and (back is None or off is None):
        if back is None and on_page(host, x):
            back = round(time.time() - t0, 3)
        if off is None and drawn(host).get("ptr") is not True:
            off = round(time.time() - t0, 3)
        time.sleep(POLL_S)
    time.sleep(SETTLE_S)
    d = delta(ends(host), e0)
    ev["hostCount"].append(len(at_cell(host, ctx["stack"]["host"])))
    ev.update(x=x, backWithin=back, ptrOffWithin=off, hostCellOfX=cell_of(host, x), endsDelta=d, look=look(host, client))
    return {"holder_leaves-back": (back is not None,
                                   f"{x} on the host's ground at {ev['hostCellOfX']} (want a page cell within "
                                   f"{W_END} s of peerAbsent; back after {back} s; the stack cell's count "
                                   f"{ev['hostCount']})"),
            "holder_leaves-once": (d["leave"] == 1 and all(v == 0 for k, v in d.items() if k != "leave"),
                                   f"host ends delta over holder_leaves {d} (want leave 1, every other 0; "
                                   f"absent = 0)"),
            "holder_leaves-ptr": (off is not None,
                                  f"the host's drawn.ptr false after {off} s (want within {W_END} s of peerAbsent)")}


def first_clip(host, client, ctx, ev):
    """The client picks the first STR_RIFLE_CLIP in tile order; the host's table holds it. Returns its id."""
    clips = of_type(client, CLIP_T)
    ev["clipsTileOrder"] = clips
    x, ev["pick"] = pick(client, cell_of(client, clips[0]) if clips else None, clips[:1])
    held_by(host, ctx["seat"], x, ev)
    return x


def row_auto_equip(host, client, ctx, ev):
    ready(host, client, ctx)
    ev["strip"] = strip_both(host, client, H1)
    ev["armed"] = both(host, client, {"cmd": "battle_give", "unit": H1, "item": RIFLE_T}, ("weaponId",)).get("weaponId")
    ev["h1Before"] = unit_brief(items_by_id(host), H1)
    x = first_clip(host, client, ctx, ev)
    ev["press"] = key(host, ctx["autoKey"]["host"])
    time.sleep(KEY_SETTLE_S)
    _, ev["settledWithin"] = wait_until(lambda: settled(host, client, H1), LAND_WAIT_S, 0.1)
    ok, ev["x"] = where(host, client, x, H1)
    ev.update(look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"auto_equip-skips_held": (ok, f"held clip {x}: on PILE host/client {ev['x']['pile']} (want both); H1 after "
                                          f"the host's auto-equip {ev['x']['unit']['host']} (want without {x})")}


def row_template_apply(host, client, ctx, ev):
    ready(host, client, ctx)
    ev["strip1"] = strip_both(host, client, H1)
    ev["given"] = [both(host, client, dict({"cmd": "battle_give", "unit": H1, "item": t}, **kw), ("weaponId",)).get("weaponId")
                   for t, kw in ((RIFLE_T, {}), (CLIP_T, {"slot": BELT, "slotX": 0, "slotY": 0}))]
    time.sleep(KEY_SETTLE_S)
    ev["create"] = click(host, widget="create_template")
    time.sleep(KEY_SETTLE_S)
    ev["strip2"] = strip_both(host, client, H1)
    ev["riflesOnPile"] = of_type(host, RIFLE_T)
    if not ev["riflesOnPile"]:
        raise AssertionError("precondition: no STR_RIFLE on the pile for the template's rifle")
    x = first_clip(host, client, ctx, ev)
    ev["onlyClip"] = only = of_type(host, CLIP_T) == [x]
    t0, seen = time.time(), None
    ev["apply"] = click(host, widget="apply_template")
    while seen is None and time.time() - t0 <= CLICK_WAIT_S + LINE_READ_S:
        v = inv_view(host)
        if v.get("lineText") == TEXT_SHORT and v.get("lineVisible") is True:
            seen = round(time.time() - t0, 3)
        time.sleep(POLL_S)
    _, ev["settledWithin"] = wait_until(lambda: settled(host, client, H1), LAND_WAIT_S, 0.1)
    ok, ev["x"] = where(host, client, x, H1)
    ev.update(lineSeen=seen, look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"template_apply-skips_held": (
        ok and (seen is not None) == only,
        f"held clip {x}: on PILE host/client {ev['x']['pile']} (want both); H1 after the apply "
        f"{ev['x']['unit']['host']} (want without {x}); {TEXT_SHORT!r} seen after {seen} s (want shown exactly "
        f"when the held clip was the only one on the pile: {only})")}


def row_bulk_order(host, client, ctx, ev):
    ready(host, client, ctx)
    gs = of_type(host, GRENADE_T)
    g, ev["pick"] = pick(host, cell_of(host, gs[0]) if gs else None, gs[:1])
    if inv_view(client).get("unitId") != C1:
        raise AssertionError(f"precondition: the client's screen on {inv_view(client).get('unitId')} (want C1 {C1})")

    def log():
        return [e for e in (es(host).get("intentsReceivedLog") or []) if e.get("kind") == "inv_bulk"]
    n0 = len(log())
    ev["press"] = key(client, ctx["autoKey"]["client"])
    got, ev["answerWithin"] = wait_until(lambda: len(log()) > n0 and es(client).get("inFlight") is None, W_HOLD)
    _, ev["settledWithin"] = wait_until(lambda: settled(host, client, C1), LAND_WAIT_S, 0.1)
    ih, ic = items_by_id(host), items_by_id(client)
    ev["c1"] = {"host": unit_brief(ih, C1), "client": unit_brief(ic, C1)}
    ev.update(g=g, hostLog=log()[n0:], look=look(host, client))
    cleanup(host, client, ctx, ev)
    off = all(g not in [i[0] for i in u] for u in ev["c1"].values())
    return {"bulk_order-skips_held": (
        bool(got) and off,
        f"the client's inv_bulk answered after {ev['answerWithin']} s (want within {W_HOLD} s: {bool(got)}); "
        f"C1 {ev['c1']['host']} (want without the host's held grenade {g} on both: {off})")}


def row_turn_start(host, client, ctx, ev):
    ready(host, client, ctx)
    gs = [i for i in of_type(client, GRENADE_T) if on_page(client, i) and on_page(host, i)
          and at_cell(client, cell_of(client, i)) == [i] and at_cell(host, cell_of(host, i)) == [i]]   # one entry, page 1
    ev["grenades"] = gs
    ev["clientOk"] = click(client, widget="ok")
    _, ev["hostSawReadyS"] = wait_until(lambda: (equip(host).get("ready") or [None] * 4)[ctx["seat"]] is True, ANSWER_WAIT_S)
    if (equip(host).get("ready") or [None] * 4)[ctx["seat"]] is not True:
        raise AssertionError(f"precondition: the host's equip.ready {equip(host).get('ready')} after the client's OK (want "
                             f"[{ctx['seat']}] true)")
    t, ev["pick"] = pick(client, cell_of(client, gs[0]) if gs else None, gs[:1])
    held_by(host, ctx["seat"], t, ev)
    e0 = ends(host)
    ev["hostOk"] = click(host, widget="ok")
    got, ev["turn1Within"] = wait_until(lambda: turn(host) == 1 and turn(client) == 1, TURN_WAIT_S)
    if not got:
        raise AssertionError(f"precondition: turn host/client {[turn(host), turn(client)]} {TURN_WAIT_S} s after both OK presses")
    closed, ev["clientClosedWithin"] = wait_until(lambda: inv_view(client).get("open") is False, TURN_WAIT_S)
    time.sleep(SETTLE_S)
    d = delta(ends(host), e0)
    ih, ic = items_by_id(host), items_by_id(client)
    pile = [on_pile(ih.get(t)), on_pile(ic.get(t))]
    ch = holds(client) or {}
    tab, lh = ch.get("table") or [-1, -1, -1, -1], ch.get("localHeld", -1)
    ev.update(t=t, endsDelta=d, pile=pile, clientHolds=ch, look=look(host, client), hash=G3F.hash_now(host, client))
    return {"turn_start-once": (d["start"] == 1, f"host ends delta over turn_start {d} (want start 1; absent = 0)"),
            "turn_start-pile": (pile == [True, True], f"{t} on PILE host/client {pile} at turn 1 (want both)"),
            "turn_start-clear": (tab == [-1, -1, -1, -1] and lh == -1 and bool(closed),
                                 f"the client's holds.table {tab}, localHeld {lh} after its screen closed "
                                 f"({bool(closed)} after {ev['clientClosedWithin']} s; want all -1 and -1)")}


def run_row(row, order, fn, host, client, ctx):
    ev = {"cpu": cpu_pct()}
    try:
        cells_ = fn(host, client, ctx, ev)
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
        cells_ = {}
    return G3F.verdict(row, order, cells_, ev)


def run_boot(tag, rows, setup, fns, host_dir, client_dir, alive_at_end):
    """One boot: setup (a miss fails every row "boot"), then every row in order, each after any failure."""
    host = GameClient("host", None, make_user_dir(host_dir))
    client = GameClient("client", None, make_user_dir(client_dir))
    try:
        try:
            ctx = setup(host, client)
        except Exception as e:
            if not isinstance(e, G3F.Miss):
                G3F.capture(tag, f"{type(e).__name__}: {str(e)[:600]}", (host, client))
            alive_at_end[tag] = alive(host)
            return G3F.fail_all(rows, f"boot (setup failure, see the CAPTURE {tag} line)")
        fails = sum(run_row(row, order, fns[row], host, client, ctx) for row, order in rows)
        alive_at_end[tag] = alive(host)
        return fails
    finally:
        rc = {}
        for gc in (host, client):
            try:
                if gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown(expected_returncodes=EXPECTED_RC)
                rc[gc.name] = gc.proc.returncode if gc.proc is not None else None
            except Exception as e:
                rc[gc.name] = f"shutdown: {type(e).__name__}: {str(e)[:200]}"
        print(f"[test_equip_hold_ends] boot {tag} shut down: {rc}", flush=True)


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    cpu = None
    try:
        cpu = subprocess.Popen(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-y", "-f", "CSV",
                                "-o", CPU_CSV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[test_equip_hold_ends] typeperf not started: {e}", flush=True)
    up = {}
    try:
        fails = run_boot("holder_leaves", ROWS_L, boot_holder_leaves, {"holder_leaves": row_holder_leaves},
                         "equip_hold_ends_leave_host", "equip_hold_ends_leave_client", up)
        fails += run_boot("tools_and_turn", ROWS_S, lambda h, c: spine(h, c, "tools_and_turn", EXTRA_S),
                          {"auto_equip": row_auto_equip, "template_apply": row_template_apply,
                           "bulk_order": row_bulk_order, "turn_start": row_turn_start},
                          "equip_hold_ends_tools_host", "equip_hold_ends_tools_client", up)
        crash = sorted(session._crash_log_snapshot() - crash0)
        fails += G3F.verdict("END", ROWS_X[0][1], {"no_crash": (
            not crash and up.get("holder_leaves") is True and up.get("tools_and_turn") is True,
            f"new crash files {crash} (want none); host alive at the end of "
            f"boot holder_leaves {up.get('holder_leaves')}, boot tools_and_turn {up.get('tools_and_turn')}")},
                             {"crash": crash, "hostAlive": up, "cpu": cpu_pct()})
    finally:
        if cpu is not None:
            cpu.terminate()
            cpu.wait(timeout=10)
    n = sum(len(order) for _, order in ROWS_L + ROWS_S + ROWS_X)
    print(f"\ntest_equip_hold_ends: {n - fails}/{n} cells passed ({'PASS' if not fails else 'FAIL'}) in "
          f"{time.time() - t0:.1f}s; CPU mean {cpu_pct(True)} %; typeperf rc {cpu.returncode if cpu else None}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
