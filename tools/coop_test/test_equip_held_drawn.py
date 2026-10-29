"""test_equip_held_drawn.py: on the pre-battle equip screen the co-op partner's held item is drawn under the
partner's pointer, centred on it as vanilla centres its own cursor item, and an item the partner lifts from its own
soldier is not drawn on that soldier's paperdoll in the read-only view while it is held. Held items are read by id,
never by pile cell.
One boot (co-op, LOBBY_KEY, dirs equip_held_drawn_*): test_prebattle_equip.py's spine plus a staging (copied, never
imported; client first, after the client applied the host's first evs): C1, C2 stripped; STAGE_TYPES + HOLD_EXTRA on
PILE; C1 given an STR_RIFLE (right hand).
  client_holds  the client picks the single STR_GRENADE cell (precondition: the host's holds.table[clientSeat] = it
       within W_HOLD), its pointer to CLIENT_PT (drawn on the host): client_holds-drawn (the host's
       presence.drawn.held = the grenade id), client_holds-centred ((heldX, heldY) = (drawn.x - 16, drawn.y - 24):
       half of RuleInventory::HAND_W x SLOT_W, HAND_H x SLOT_H, vanilla's _selection)
  host_holds  the host picks the single STR_SMOKE_GRENADE cell (precondition: the client's holds.table[hostSeat] =
       it), its pointer to HOST_PT: host_holds-drawn (the client's drawn.held = the smoke id, centred on the host's
       pointer)
  DROP the client picks the grenade again and drops it on C1's STR_BELT (0,0) (lands on both): drop-gone (the
       host's drawn.held = the grenade before the drop, then -1 within W_HOLD), drop-ptr (GUARD: the host's
       drawn.ptr still true)
  DOLL the host presses NEXT (<= CYCLE_CAP) until it shows C1 (precondition: C1's rifle in the host's
       inventory_view.drawnSlots, the TEST-ONLY record of what drawItems() drew); the client lifts the rifle from
       C1's right hand (precondition: the host's holds.table[clientSeat] = it): doll-gone (absent from the host's
       drawnSlots within W_HOLD while held), doll-back (GUARD: present again within W_HOLD after the client's
       right-click)
  END  no_crash (GUARD: no new crash file; host and client alive at the end)
presence = event_state.equip.presence; an absent `held` reads FAIL. Every row ends with both cursors empty (a failed
cleanup ends the later rows "not reached"). A build with no held drawing and no paperdoll skip fails
client_holds-drawn, client_holds-centred, host_holds-drawn, drop-gone and doll-gone (5 of 8). One EVIDENCE line per
row, one PASS / FAIL line per cell, the row verdict; every row runs after a failure; a boot step past its bound prints
ONE CAPTURE line and fails every row "boot". run in the foreground to completion.
ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_equip_held_drawn.py
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
LOBBY_KEY = "49286"                # lobby key
SEED_MAP = 1                       # set_seed right before newbattle_ok
MAP_FP = -4.48310638993e+18        # the host's mapFingerprint at SEED_MAP 1
C_IDS, H_IDS = [8, 9], [10, 11, 12, 13, 14]   # the client's seated units, the host's own soldiers
C1, C2, H1 = 8, 9, 10              # C1 = the client's screen, H1 = the host's screen
PILE = (14, 19, 1)                 # the craft pile tile at turn 0
STAGE_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE", "STR_SMOKE_GRENADE")
HOLD_EXTRA = "STR_RIFLE_CLIP"      # the clip cell holds a stack of 2
RIFLE_T, GRENADE_T, SMOKE_T = "STR_RIFLE", "STR_GRENADE", "STR_SMOKE_GRENADE"
GROUND, BELT, RIGHT_HAND, LEFT_HAND = "STR_GROUND", "STR_BELT", "STR_RIGHT_HAND", "STR_LEFT_HAND"
GROUND_COLS = 20                   # the first ground page (a held item is parked at x 1000000)
# SCALE = window / logical pixels; CLIENT_PT / HOST_PT = the client's / host's pointer on the Inventory surface
SCALE, CLIENT_PT, HOST_PT = 2, (150, 120), (60, 150)
HALF = (2 * 16 // 2, 3 * 16 // 2)  # RuleInventory::HAND_W x SLOT_W / 2, HAND_H x SLOT_H / 2 (vanilla _selection)
W_HOLD, W_PTR, MOTION_S = 2.0, 2.0, 1.0       # hold / pointer windows (every change measured within 0.05 s)
CLICK_WAIT_S, LAND_WAIT_S, POLL_S = 2.0, 10.0, 0.05
BRIEFING_WAIT_S, ENTRY_WAIT_S, SCREEN_S = 30.0, 5.0, 15.0
CYCLE_CAP = 16                     # NEXT press bound (as test_prebattle_equip.py's goto_unit)
EXPECTED_RC = (0, 3221226505)
ROWS = (("client_holds", ("client_holds-drawn", "client_holds-centred")), ("host_holds", ("host_holds-drawn",)),
        ("DROP", ("drop-gone", "drop-ptr")), ("DOLL", ("doll-gone", "doll-back")))
ROWS_X = (("END", ("no_crash",)),)
CPU_CSV = os.path.join(tempfile.gettempdir(), "equip_held_drawn_cpu_s%d.csv" % harness.HARNESS_SLOT)

es = event_state
authority = lambda gc: battle_state(gc).get("authority") or {}  # noqa: E731
presence = lambda gc: (es(gc).get("equip") or {}).get("presence") or {}  # noqa: E731
table = lambda gc: (presence(gc).get("holds") or {}).get("table") or [-1, -1, -1, -1]  # noqa: E731
drawn = lambda gc: presence(gc).get("drawn") or {}  # noqa: E731
cursor = lambda gc: inv_view(gc).get("selectedItem")  # noqa: E731
drawn_slots = lambda gc: inv_view(gc).get("drawnSlots") or []  # noqa: E731
screen_up = lambda gc: (lambda v: v.get("open") is True and v.get("top") is True and v.get("preBattle") is True)(  # noqa: E731
    inv_view(gc))
at_cell = lambda gc, cell: [g["id"] for g in (inv_view(gc).get("ground") or [])  # noqa: E731
                            if (g.get("x"), g.get("y")) == tuple(cell)]
click = lambda gc, **kw: (lambda r: {"req": kw, "ok": r.get("ok"), "error": r.get("error")})(  # noqa: E731
    gc.cmd(dict({"cmd": "inventory_click"}, **kw)))
hand_items = lambda gc, uid, slot: sorted(i for i, it in items_by_id(gc).items()  # noqa: E731
                                          if it.get("owner") == uid and it.get("slot") == slot)


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # a dead instance
        return [f"<no stack: {str(e)[:120]}>"]


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
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "ground", "preBattle", "drawnSlots")}


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


def single_cell(gc, iid):
    """Precondition (pin: a single-entry cell on page 1): the cell holding only `iid` on gc's screen."""
    c = cell_of(gc, iid)
    if c is None or c[0] is None or not 0 <= c[0] < GROUND_COLS or at_cell(gc, c) != [iid]:
        raise AssertionError(f"precondition: {iid} on {gc.name}'s page 1 alone at its cell (cell {c}, "
                             f"{at_cell(gc, c) if c else None})")
    return c


def pick(gc, cell, iid, ev):
    """Left-click ground `cell` with an empty cursor; `iid` must land on the cursor (else the row's precondition fails)."""
    ev["pick"] = {"machine": gc.name, "cell": cell, "click": click(gc, slot=GROUND, x=cell[0], y=cell[1])}
    wait_until(lambda: cursor(gc) == iid, CLICK_WAIT_S)
    ev["pick"]["picked"] = cursor(gc)
    if ev["pick"]["picked"] != iid:
        raise AssertionError(f"precondition: {gc.name}'s pick at {cell} put {ev['pick']['picked']} on its cursor (want {iid})")


def held_on(gc, seat, iid, ev, k):
    """Precondition: gc's holds.table[seat] = iid within W_HOLD (the hold table's grant, or the host's own sample)."""
    _, ev[k + "Within"] = wait_until(lambda: table(gc)[seat] == iid, W_HOLD)
    ev[k] = table(gc)
    if ev[k][seat] != iid:
        raise AssertionError(f"precondition: {gc.name} holds.table {ev[k]} (want [{seat}] = {iid} within {W_HOLD} s)")


def point(gc, viewer, pt, ev):
    """gc's pointer moved to `pt` on the Inventory surface (a real motion event); precondition: drawn there on `viewer`
    within W_PTR."""
    c = gc.cmd({"cmd": "cursor_pos"})
    want = [c.get("invX", 0) + pt[0], c.get("invY", 0) + pt[1]]
    ev["motion"] = gc.cmd({"cmd": "inject_input", "kind": "motion", "x": want[0] * SCALE, "y": want[1] * SCALE}).get("ok")
    got, ev["ptrWithin"] = wait_until(lambda: (lambda d: d.get("ptr") is True and [d.get("x"), d.get("y")] == list(pt))(
        drawn(viewer)), W_PTR)
    if not got:
        raise AssertionError(f"precondition: {gc.name}'s pointer not drawn at {pt} on {viewer.name} within {W_PTR} s "
                             f"({drawn(viewer)}; motion to {want})")


def held_read(gc, iid):
    """gc's presence.drawn once its `held` = iid (bounded by W_HOLD): the record; an absent `held` stays absent (and
    fails the cell)."""
    wait_until(lambda: drawn(gc).get("held") == iid, W_HOLD)
    return drawn(gc)


centred = lambda d: d.get("held") is not None and (d.get("heldX"), d.get("heldY")) == (  # noqa: E731
    (d.get("x") or 0) - HALF[0], (d.get("y") or 0) - HALF[1])
show = lambda d: {k: d.get(k) for k in ("ptr", "x", "y", "held", "heldX", "heldY")}  # noqa: E731


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


def spine(host, client):
    m, tag = (host, client), "boot"
    ctx = {"boot": {}}
    G3F.guarded(tag, lambda: bring_up_lobby_roster_pinned(host, client, LOBBY_KEY), m)
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
        for t in STAGE_TYPES + (HOLD_EXTRA,):
            rec["ids"].setdefault(t, []).append(both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1],
                                                                     "z": PILE[2], "item": t}, ("ids",))["ids"][0])
        r = both(host, client, {"cmd": "battle_give", "unit": C1, "item": RIFLE_T}, ("weaponId", "weaponSlot"))
        rec["c1Rifle"] = [r.get("weaponId"), r.get("weaponSlot")]
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
    ctx["seat"], ctx["hostSeat"] = authority(client).get("localSeat"), authority(host).get("localSeat")
    ctx["units"] = [inv_view(gc).get("unitId") for gc in m]
    ctx["boot"].update(seats=[ctx["hostSeat"], ctx["seat"]], units=ctx["units"])
    if ctx["units"] != [H1, C1] or ctx["seat"] == ctx["hostSeat"] or None in (ctx["seat"], ctx["hostSeat"]):
        miss(tag, f"screens on {ctx['units']} (want [{H1}, {C1}]); seats host/client {ctx['boot']['seats']}", m)
    ctx["ids"] = st["ids"]
    print(f"[test_equip_held_drawn] boot: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_client_holds(host, client, ctx, ev):
    ready(host, client, ctx)
    g = ev["g"] = ctx["ids"][GRENADE_T][0]
    pick(client, single_cell(client, g), g, ev)
    held_on(host, ctx["seat"], g, ev, "hostTable")
    point(client, host, CLIENT_PT, ev)
    d = ev["hostDrawn"] = held_read(host, g)
    cleanup(host, client, ctx, ev)
    return {"client_holds-drawn": (d.get("held") == g, f"the host's drawn.held {d.get('held')} (want {g} within "
                                                       f"{W_HOLD} s; absent = FAIL)"),
            "client_holds-centred": (d.get("held") == g and centred(d),
                                     f"the host's drawn {show(d)} (want held {g} at (x - {HALF[0]}, y - {HALF[1]}))")}


def row_host_holds(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ev["s"] = ctx["ids"][SMOKE_T][0]
    pick(host, single_cell(host, s), s, ev)
    held_on(client, ctx["hostSeat"], s, ev, "clientTable")
    point(host, client, HOST_PT, ev)
    d = ev["clientDrawn"] = held_read(client, s)
    cleanup(host, client, ctx, ev)
    return {"host_holds-drawn": (d.get("held") == s and centred(d),
                                 f"the client's drawn {show(d)} (want held {s} centred on the host's pointer: "
                                 f"(x - {HALF[0]}, y - {HALF[1]}))")}


def row_drop(host, client, ctx, ev):
    ready(host, client, ctx)
    g = ev["g"] = ctx["ids"][GRENADE_T][0]
    pick(client, single_cell(client, g), g, ev)
    held_on(host, ctx["seat"], g, ev, "hostTable")
    before = ev["drawnBefore"] = held_read(host, g)
    ev["drop"] = click(client, slot=BELT, x=0, y=0)
    landed = lambda: all((lambda it: (it.get("owner"), it.get("slot")) == (C1, BELT))(  # noqa: E731
        items_by_id(gc).get(g) or {}) for gc in (host, client))
    ok, ev["landedWithin"] = wait_until(landed, LAND_WAIT_S, 0.1)
    if not ok:
        raise AssertionError(f"precondition: {g} not on C1's {BELT} on both within {LAND_WAIT_S} s")
    _, ev["goneWithin"] = wait_until(lambda: drawn(host).get("held") == -1, W_HOLD)
    after = ev["drawnAfter"] = drawn(host)
    cleanup(host, client, ctx, ev)
    return {"drop-gone": (before.get("held") == g and after.get("held") == -1,
                          f"the host's drawn.held {before.get('held')} before the belt drop, {after.get('held')} after (want {g}, "
                          f"then -1 within {W_HOLD} s)"),
            "drop-ptr": (after.get("ptr") is True, f"the host's drawn.ptr {after.get('ptr')} after the drop (want True)")}


def row_doll(host, client, ctx, ev):
    ready(host, client, ctx)
    hands = [hand_items(gc, C1, RIGHT_HAND) or hand_items(gc, C1, LEFT_HAND) for gc in (host, client)]
    ev["c1Hand"] = hands
    if not hands[0] or hands[0] != hands[1]:
        raise AssertionError(f"precondition: a hand item on C1, equal on both (host/client {hands})")
    r = ev["r"] = hands[0][0]
    slot = RIGHT_HAND if r in hand_items(client, C1, RIGHT_HAND) else LEFT_HAND
    nav = ev["nav"] = [inv_view(host).get("unitId")]      # NEXT until C1, at most CYCLE_CAP presses
    while nav[-1] != C1 and len(nav) <= CYCLE_CAP:
        click(host, widget="next")
        wait_until(lambda: inv_view(host).get("unitId") != nav[-1], CLICK_WAIT_S)
        nav.append(inv_view(host).get("unitId"))
    if inv_view(host).get("unitId") != C1:
        raise AssertionError(f"precondition: the host's NEXT never showed C1 {C1} (visited {ev['nav']})")
    got, ev["drawnWithin"] = wait_until(lambda: r in drawn_slots(host), W_HOLD)
    ev["drawnBefore"] = drawn_slots(host)
    if not got or inv_view(client).get("unitId") != C1:
        raise AssertionError(f"precondition: {r} in the host's drawnSlots {ev['drawnBefore']} on C1, the client on C1 "
                             f"({inv_view(client).get('unitId')})")
    ev["lift"] = click(client, slot=slot, x=0, y=0)
    wait_until(lambda: cursor(client) == r, CLICK_WAIT_S)
    if cursor(client) != r:
        raise AssertionError(f"precondition: the client's click on C1's {slot} put {cursor(client)} on its cursor (want {r})")
    held_on(host, ctx["seat"], r, ev, "hostTable")
    gone, ev["goneWithin"] = wait_until(lambda: r not in drawn_slots(host), W_HOLD)
    ev["drawnHeld"] = drawn_slots(host)
    cleanup(host, client, ctx, ev)
    back, ev["backWithin"] = wait_until(lambda: r in drawn_slots(host), W_HOLD)
    ev["drawnAfter"] = drawn_slots(host)
    ev["hash"] = G3F.hash_now(host, client)
    return {"doll-gone": (bool(gone), f"C1's {r} in the host's drawnSlots while the client holds it: {ev['drawnHeld']} (want "
                                      f"absent within {W_HOLD} s)"),
            "doll-back": (bool(back), f"the host's drawnSlots after the client's right-click: {ev['drawnAfter']} (want {r} "
                                      f"within {W_HOLD} s)")}


def run_row(row, order, fn, host, client, ctx):
    ev = {"cpu": cpu_pct()}
    try:
        cells_ = fn(host, client, ctx, ev)
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
        cells_ = {}
        try:  # a precondition miss still ends with both cursors empty (the holder's right-click), recorded
            ctx.get("broken") or cleanup(host, client, ctx, ev)
        except Exception as e2:
            ctx["broken"] = ev["cleanupError"] = f"{type(e2).__name__}: {str(e2)[:200]}"
    return G3F.verdict(row, order, cells_, ev)


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    cpu = None
    try:
        cpu = subprocess.Popen(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-y", "-f", "CSV",
                                "-o", CPU_CSV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[test_equip_held_drawn] typeperf not started: {e}", flush=True)
    host = GameClient("host", None, make_user_dir("equip_held_drawn_host"))
    client = GameClient("client", None, make_user_dir("equip_held_drawn_client"))
    up = [None, None]
    try:
        try:
            ctx = spine(host, client)
            fns = {"client_holds": row_client_holds, "host_holds": row_host_holds, "DROP": row_drop, "DOLL": row_doll}
            fails = sum(run_row(row, order, fns[row], host, client, ctx) for row, order in ROWS)
        except Exception as e:
            if not isinstance(e, G3F.Miss):
                G3F.capture("boot", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        up = [alive(host), alive(client)]
    finally:
        rc = {}
        for gc in (host, client):
            try:
                if gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown(expected_returncodes=EXPECTED_RC)
                rc[gc.name] = gc.proc.returncode if gc.proc is not None else None
            except Exception as e:
                rc[gc.name] = f"shutdown: {type(e).__name__}: {str(e)[:200]}"
        print(f"[test_equip_held_drawn] boot shut down: {rc}", flush=True)
        if cpu is not None:
            cpu.terminate()
            cpu.wait(timeout=10)
    crash = sorted(session._crash_log_snapshot() - crash0)
    fails += G3F.verdict("END", ROWS_X[0][1], {"no_crash": (not crash and up == [True, True],
                                                         f"new crash files {crash} (want none); host/client alive at the end "
                                                         f"{up}")}, {"crash": crash, "alive": up, "rc": rc})
    n = sum(len(order) for _, order in ROWS + ROWS_X)
    print(f"\ntest_equip_held_drawn: {n - fails}/{n} cells passed ({'PASS' if not fails else 'FAIL'}) in "
          f"{time.time() - t0:.1f}s; CPU mean {cpu_pct(True)} %; typeperf rc {cpu.returncode if cpu else None}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
