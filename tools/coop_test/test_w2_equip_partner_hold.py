"""EQ-2 S-B - test_w2_equip_partner_hold.py (EQH): an item the co-op partner picks up on the pre-battle equip screen is reserved
at once. Owner D291 (b): the pile count drops at pick-up and nobody else can take it; the reservation ends when the holder puts it
down or cancels; D289 (a), D293 (a): never between PvP opponents. Spec: docs repo rewrite/prompts/eq2b_hold.md (f) with its PIN-PASS
AMENDMENTS, the common file rewrite/prompts/eq2_partner_pointer.md; rulings QEQ2-6 (a), QEQ2-7 (a), QEQ2-12 (a), QEQ2-13 (a) (the
TEST-ONLY host lever `equip_holds_defer`), R-EQ2-3 (a) (gone / back are read by the held item's id: vanilla's ground layout slides the
next stack into a freed cell, VL-EQ2-7). Constants: docs repo rewrite/eq2-task0/sb/CONSTANTS.md (TASK 0 boots a, b, p on HEAD + r1;
c, pc with g1).
Boot A (co-op, key KEY_B, dirs eq2b_a_host / eq2b_a_client): PBE's spine (test_w2_prebattle_equip.py, copied, never imported) and
staging, client first, as soon as both machines hold the battle: C1 and C2 stripped, one each of STAGE_TYPES plus HOLD_EXTRA (a second
STR_RIFLE_CLIP) dropped on PILE; the client closes its briefing (its screen on C1), then the host. Rows in order (real clicks,
inventory_click; a pick = a left-click on a ground cell with an empty cursor):
  H1   the client picks the 2-clip cell: H1-drop (the host's count at that cell 2 -> 1 within W_HOLD), H1-table
  H1b  the host left-clicks the same cell, then right-clicks: H1b-mate (its pick is the stack-mate, never the client's item)
  H2   the client drops its clip on C1's STR_BELT (0,0): H2-land (GUARD), H2-once (ends.move delta 1, every other end 0)
  H3   the host picks the grenade; the client clicks the cell the grenade held: H3-gone (its id off the client's page within
       W_HOLD), H3-noclick (that id never on the client's cursor). The client's cursor is emptied; the host keeps the grenade for H4.
  H4   the host right-clicks: H4-back (H3-gone held, the id back on a page cell of the client's screen within W_HOLD, ends.put 1)
  H5   the client picks the smoke grenade, then right-clicks: H5-back (off the host's page, then back), H5-once (ends.cancel 1)
  H6   the race: host equip_holds_defer on; the host picks the proximity grenade; the client (still listing it) picks it; W_HOLD;
       lever off: H6-deny (the host's denies delta 1), H6-line (the client's cursor empty, its line TEXT_ITEM_MISSING), H6-host (GUARD)
Boot P (PvP gm2, X-COM equipment for aliens on, key KEY_B after boot A's shutdown, dirs eq2b_p_host / eq2b_p_client): RAE's boot DA
(test_r5_alien_equip.py, copied) plus one STR_RIFLE_CLIP dropped on PILE while both briefings are up.
  HP   the alien client picks the clip: HP-none (GUARD: the host's count unchanged, its table all -1, the client's sends delta 0)
  X    after both boots: X-crash (GUARD: no new crash file, both hosts alive)
A count = the number of that screen's inventory_view.ground entries at the cell (x, y); an id is off the page when its ground x is
PARK_X (Inventory::arrangeGround parks it there, F20617); holds = event_state.equip.presence.holds (absent: table -1, counters 0).
Counters read as the row's delta. Every row ends with both cursors empty (the holder's right-click, recorded); a cleanup that fails
ends the boot's later rows "not reached".
RED on HEAD + r1 (commit R1, the hold not built): H1-drop, H1-table, H1b-mate, H2-once, H3-gone, H3-noclick, H4-back, H5-back,
H5-once, H6-deny, H6-line (11 of 15); H2-land, H6-host, HP-none, X-crash PASS.
One EVIDENCE line per row (both tops, both inventory_view briefs, both holds, CPU at the row start, the row's reads), one PASS / FAIL
line per cell, then the row verdict; every row runs after a failure (a precondition miss ends its own row, its cells "not reached");
a boot step past its bound prints ONE CAPTURE line and fails that boot's rows "boot". WV-D95: run in the foreground to completion.
WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_w2_equip_partner_hold.py
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
from test_w2_host_combat import bring_up_lobby_roster_pinned  # noqa: E402
from test_w2_delta_core import both, diff_buckets  # noqa: E402
from test_w2_delta_items import items_by_id  # noqa: E402
from test_w2_client_items import strip_both  # noqa: E402
import test_w2_battle_end_rules as BER  # noqa: E402
import test_r5_pvp_gm3 as G3F  # noqa: E402

# ----- pins (rewrite/eq2-task0/sb/CONSTANTS.md; no value needed its replacement rule) -----
KEY_B = "49284"                    # boot A, then boot P after boot A's shutdown
SEED_MAP = 1                       # PBE: set_seed right before newbattle_ok
MAP_FP = -4.48310638993e+18        # PBE: the host's mapFingerprint at SEED_MAP 1
C_IDS = [8, 9]                     # PBE: the client's seated units
C1, C2 = 8, 9
H_IDS = [10, 11, 12, 13, 14]       # PBE: the host's own soldiers
PILE = (14, 19, 1)                 # PBE / RAE: the craft pile tile at turn 0 (co-op and gm2)
STAGE_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE", "STR_SMOKE_GRENADE")
HOLD_EXTRA = "STR_RIFLE_CLIP"      # a second clip: the clip cell holds a stack of 2
STACK_TYPE = "STR_RIFLE_CLIP"
SINGLES = {"H3": "STR_GRENADE", "H5": "STR_SMOKE_GRENADE", "H6": "STR_PROXIMITY_GRENADE"}
GROUND, BELT = "STR_GROUND", "STR_BELT"
GROUND_COLS, PARK_X = 20, 1000000  # the first ground page; arrangeGround's park column
SEED_PVP, MISSION_PVP = 1, "STR_SMALL_SCOUT"   # RAE boot DA
TEXT_ITEM_MISSING = "Order cancelled - item unavailable"   # STR_COOP_DENY_ITEM_MISSING (QEQ2-7, P8-4-M3)
W_HOLD, CLICK_WAIT_S, LAND_WAIT_S, ANSWER_WAIT_S, SETTLE_S, POLL_S = 2.0, 2.0, 10.0, 3.0, 0.5, 0.05
EQ1_WAIT_S, ENTRY_WAIT_S, SCREEN_S = 30.0, 5.0, 15.0
ENDS = ("put", "answer", "cancel", "deny", "move", "leave", "start")
EXPECTED_RC = (0, 3221226505)
ROWS_A = (("H1", ("H1-drop", "H1-table")), ("H1b", ("H1b-mate",)), ("H2", ("H2-land", "H2-once")),
          ("H3", ("H3-gone", "H3-noclick")), ("H4", ("H4-back",)), ("H5", ("H5-back", "H5-once")),
          ("H6", ("H6-deny", "H6-line", "H6-host")))
ROWS_P = (("HP", ("HP-none",)),)
ROWS_X = (("X", ("X-crash",)),)
CPU_CSV = os.path.join(tempfile.gettempdir(), "eq2b_cpu_s%d.csv" % harness.HARNESS_SLOT)


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # a dead instance
        return [f"<no stack: {str(e)[:120]}>"]


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def has(gc, name):
    return any(name in s for s in stack(gc))


def equip(gc):
    return event_state(gc).get("equip") or {}


def in_battle(gc):
    return battle_state(gc).get("inBattle") is True


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
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "ground", "preBattle", "lineText", "lineVisible")}


def brief(v):
    return {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem", "preBattle", "lineText", "lineVisible", "error")}


def screen_up(gc):
    v = inv_view(gc)
    return v.get("open") is True and v.get("top") is True and v.get("preBattle") is True


def cursor(gc):
    return inv_view(gc).get("selectedItem")


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
    """The newest typeperf sample (% total), or the mean of all; None without one."""
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
    """(x, y) of id `iid` on gc's ground (x PARK_X = off the page), None when it is not on the screen's tile."""
    for g in inv_view(gc).get("ground") or []:
        if g.get("id") == iid:
            return (g.get("x"), g.get("y"))
    return None


def at_cell(gc, cell):
    return [g["id"] for g in (inv_view(gc).get("ground") or []) if (g.get("x"), g.get("y")) == tuple(cell)]


def parked(gc, iid):
    c = cell_of(gc, iid)
    return c is not None and c[0] == PARK_X


def on_page(gc, iid):
    c = cell_of(gc, iid)
    return c is not None and c[0] is not None and 0 <= c[0] < GROUND_COLS


def holds(gc):
    """This machine's presence.holds (None when the build has none)."""
    return (equip(gc).get("presence") or {}).get("holds")


def counter(gc, key):
    return (holds(gc) or {}).get(key) or 0


def ends(gc):
    e = (holds(gc) or {}).get("ends") or {}
    return {k: e.get(k) or 0 for k in ENDS}


def delta(after, before):
    return {k: after[k] - before[k] for k in ENDS}


def table(gc):
    return (holds(gc) or {}).get("table") or [-1, -1, -1, -1]


def click(gc, **kw):
    r = gc.cmd(dict({"cmd": "inventory_click"}, **kw))
    return {"req": kw, "ok": r.get("ok"), "error": r.get("error")}


def pick(gc, cell, want=None):
    """Left-click ground `cell` with an empty cursor; returns (the id on the cursor or None, record). `want` (an id list): the
    pick must put one of them on the cursor, else the row's precondition fails."""
    rec = {"machine": gc.name, "cell": cell, "atCell": at_cell(gc, cell), "cursorBefore": cursor(gc)}
    rec["click"] = click(gc, slot=GROUND, x=cell[0], y=cell[1])
    got, rec["waited"] = wait_until(lambda: cursor(gc) not in (None, -1), CLICK_WAIT_S)
    rec["picked"] = cursor(gc) if got else None
    if want is not None and rec["picked"] not in want:
        raise AssertionError(f"precondition: {gc.name}'s pick at {cell} put {rec['picked']} on its cursor (want one of {want}; "
                             f"{rec})")
    return rec["picked"], rec


def give_back(gc, ev, key):
    """The holder's right-click (vanilla's return), only with an item on the cursor (an empty-cursor right-click primes)."""
    if cursor(gc) not in (None, -1):
        ev[key] = click(gc, slot=GROUND, x=0, y=0, button="right")
        wait_until(lambda: cursor(gc) == -1, CLICK_WAIT_S)
    return cursor(gc) == -1


def look(host, client):
    return {gc.name: {"top": top(gc), "view": brief(inv_view(gc)), "holds": holds(gc)} for gc in (host, client)}


def ready(host, client, ctx, host_empty=True):
    """A row's head: both pre-battle screens up, the client's cursor empty (the host's too unless it holds H3's item)."""
    if ctx.get("broken"):
        raise AssertionError(f"not reached: an earlier row's cleanup failed ({ctx['broken']})")
    if not (screen_up(host) and screen_up(client)):
        raise AssertionError(f"precondition: screens up host {screen_up(host)} client {screen_up(client)} (stacks {stack(host)} / "
                             f"{stack(client)})")
    if cursor(client) != -1 or (host_empty and cursor(host) != -1):
        raise AssertionError(f"precondition: cursors host {cursor(host)} client {cursor(client)} (want empty)")


def cleanup(host, client, ctx, ev, keep_host=False):
    ok = give_back(client, ev, "clientReturn") and (keep_host or give_back(host, ev, "hostReturn"))
    ev["cursorsAfter"] = [cursor(host), cursor(client)]
    if not ok:
        ctx["broken"] = f"cursors host/client {ev['cursorsAfter']} after the cleanup"


# ===================== boot A (PBE's spine and staging, copied) =====================


def stage(host, client):
    """C1 and C2 stripped on both machines, then STAGE_TYPES and HOLD_EXTRA dropped on PILE (client first, F607)."""
    rec = {"stripped": {uid: strip_both(host, client, uid) for uid in (C1, C2)}, "ids": {}}
    for t in STAGE_TYPES:
        rec["ids"][t] = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                             ("ids",))["ids"][0]
    rec["extra"] = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": HOLD_EXTRA},
                        ("ids",))["ids"][0]
    rec["diff"] = diff_buckets(host, client)
    return rec


def cells(host, client, ids, extra, m):
    """The pinned cells on both screens, their preconditions checked (CONSTANTS.md: every pin met its rule)."""
    page1 = lambda c: bool(c) and c[0] is not None and 0 <= c[0] < GROUND_COLS  # noqa: E731
    out = {}
    sc = {gc.name: cell_of(gc, ids[STACK_TYPE]) for gc in (host, client)}
    st = {n: (sorted(at_cell(gc, sc[n])) if sc[n] else []) for n, gc in (("host", host), ("client", client))}
    if not (page1(sc["host"]) and page1(sc["client"]) and st["host"] == st["client"] == sorted([ids[STACK_TYPE], extra])):
        miss("A", f"the stack cell: {sc} holds {st} (want the two staged clips at one page-1 cell on both screens)", m)
    out["stack"] = {"cell": sc, "ids": st["client"]}
    for row, t in SINGLES.items():
        iid = ids[t]
        c = {gc.name: cell_of(gc, iid) for gc in (host, client)}
        if not all(page1(c[n]) and at_cell(gc, c[n]) == [iid] for n, gc in (("host", host), ("client", client))):
            miss("A", f"the {row} cell: {t} {iid} at {c} (want one entry at a page-1 cell on both screens)", m)
        out[row] = {"id": iid, "type": t, "cell": c}
    return out


def boot_a(host, client):
    m = (host, client)
    ctx = {"m": m, "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("A", lambda: bring_up_lobby_roster_pinned(host, client, KEY_B), m)
    seated = {}
    G3F.guarded("A", lambda: session.bring_up_to_briefings(
        host, client, seated, seat_count=2, pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    hb = battle_state(host)
    sid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    got = {"mapFingerprint": hb.get("mapFingerprint"), "seated": [sid.get(s) for s in seated.get("soldierIds", [])],
           "hIds": sorted(u["id"] for u in hb.get("units", []) if u.get("coop") == 0 and u.get("faction") == 0
                          and not u.get("isOut"))}
    ctx["boot"].update(got)
    if (got["mapFingerprint"], got["seated"], got["hIds"]) != (MAP_FP, C_IDS, H_IDS):
        miss("A", f"PBE's spine: {got} (want MAP_FP {MAP_FP}, seated {C_IDS}, H {H_IDS})", m)
    ok, ctx["boot"]["clientBriefingS"] = wait_until(lambda: has(client, "BriefingState") and in_battle(client), EQ1_WAIT_S, 0.1)
    if not ok:
        miss("A", f"no client BriefingState with its battle within {EQ1_WAIT_S} s", m)
    G3F.guarded("A", lambda: session.wait_seq_barrier(host, client), m)   # F21396: the host's first evs applied before staging (R-LT13-1)
    st = ctx["boot"]["staged"] = G3F.guarded("A", lambda: stage(host, client), m)
    if st["diff"]:
        miss("A", f"buckets differ after the staging: {st['diff']}", m)
    ctx["boot"]["clientClose"] = client.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    if not ok:
        miss("A", f"the client's pre-battle screen not up within {ENTRY_WAIT_S} s after its briefing closed", m)
    ctx["boot"]["hostClose"] = host.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("A", f"the host's pre-battle screen not up within {SCREEN_S} s after its briefing closed", m)
    ctx["seat"] = (battle_state(client).get("authority") or {}).get("localSeat")
    ctx["cells"] = cells(host, client, st["ids"], st["extra"], m)
    ctx["boot"].update(cells=ctx["cells"], seatClient=ctx["seat"], units=[inv_view(gc).get("unitId") for gc in m])
    print(f"[eq2b] boot A: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_h1(host, client, ctx, ev):
    ready(host, client, ctx)
    sc = ctx["cells"]["stack"]["cell"]
    n0 = len(at_cell(host, sc["host"]))
    x, ev["pick"] = pick(client, sc["client"], ctx["cells"]["stack"]["ids"])
    ctx["x"] = x
    _, ev["dropWithin"] = wait_until(lambda: len(at_cell(host, sc["host"])) == n0 - 1, W_HOLD)
    n1, tab = len(at_cell(host, sc["host"])), table(host)
    ev.update(hostCount=[n0, n1], hostAtCell=at_cell(host, sc["host"]), hostTable=tab, look=look(host, client))
    return {"H1-drop": (n1 == n0 - 1, f"the host's count at {sc['host']}: {n0} -> {n1} (want {n0} -> {n0 - 1} within {W_HOLD} s; "
                                      f"the client holds {x})"),
            "H1-table": (tab[ctx["seat"]] == x, f"host holds.table {tab} (want [{ctx['seat']}] = the client's item {x}; absent = -1)")}


def row_h1b(host, client, ctx, ev):
    x, sc = ctx.get("x"), ctx["cells"]["stack"]["cell"]
    if x is None or cursor(client) != x or cursor(host) != -1:
        raise AssertionError(f"precondition: the client holds {cursor(client)} (want H1's {x}), the host {cursor(host)} (want empty)")
    mates = [i for i in ctx["cells"]["stack"]["ids"] if i != x]
    y, ev["pick"] = pick(host, sc["host"], ctx["cells"]["stack"]["ids"])
    ev.update(hostItem=y, clientItem=x, mates=mates, look=look(host, client))
    give_back(host, ev, "hostReturn")
    ev["cursorsAfter"] = [cursor(host), cursor(client)]
    if cursor(host) != -1:
        ctx["broken"] = f"the host's cursor {cursor(host)} after H1b's right-click"
    return {"H1b-mate": (y in mates, f"the host's pick {y} (want the stack-mate {mates}, never the client's {x})")}


def row_h2(host, client, ctx, ev):
    x = ctx.get("x")
    if x is None or cursor(client) != x or cursor(host) != -1 or inv_view(client).get("unitId") != C1:
        raise AssertionError(f"precondition: client holds {cursor(client)} on unit {inv_view(client).get('unitId')} (want {x} on "
                             f"C1 {C1}), host holds {cursor(host)}")
    e0 = ends(host)
    ev["drop"] = click(client, slot=BELT, x=0, y=0)
    want = {"owner": C1, "slot": BELT, "slotX": 0, "slotY": 0}

    def where(gc):
        it = items_by_id(gc).get(x) or {}
        return {k: it.get(k) for k in want}
    got, ev["landedWithin"] = wait_until(lambda: where(host) == want and where(client) == want, LAND_WAIT_S, 0.1)
    wait_until(lambda: cursor(client) == -1, ANSWER_WAIT_S)
    time.sleep(SETTLE_S)   # the client's answer sends item -1: a no-op on the host
    d = delta(ends(host), e0)
    ev.update(item={"host": where(host), "client": where(client)}, endsDelta=d, look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"H2-land": (bool(got), f"item {x} host {ev['item']['host']} client {ev['item']['client']} (want {want} on both within "
                                   f"{LAND_WAIT_S} s)"),
            "H2-once": (d["move"] == 1 and all(v == 0 for k, v in d.items() if k != "move"),
                        f"host ends delta over H2 {d} (want move 1, every other 0; absent = 0)")}


def row_h3(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ctx["cells"]["H3"]
    g, ev["pick"] = pick(host, s["cell"]["host"], [s["id"]])
    got, ev["goneWithin"] = wait_until(lambda: parked(client, g), W_HOLD)
    ev["clientCellOfItem"], ev["clientAtOldCell"] = cell_of(client, g), at_cell(client, s["cell"]["client"])
    ctx["H3gone"] = bool(got)
    c, ev["clientPick"] = pick(client, s["cell"]["client"])
    ev["look"] = look(host, client)
    cleanup(host, client, ctx, ev, keep_host=True)
    return {"H3-gone": (bool(got), f"{s['type']} {g} on the client's ground at {ev['clientCellOfItem']} (want off the page, x {PARK_X}, "
                                   f"within {W_HOLD} s; its old cell {s['cell']['client']} now holds {ev['clientAtOldCell']})"),
            "H3-noclick": (c != g, f"the client's click on {s['cell']['client']} put {c} on its cursor (want never {g}, R-EQ2-3)")}


def row_h4(host, client, ctx, ev):
    s = ctx["cells"]["H3"]
    ready(host, client, ctx, host_empty=False)
    if cursor(host) != s["id"]:
        raise AssertionError(f"precondition: the host holds {cursor(host)} (want H3's {s['id']})")
    e0 = ends(host)
    give_back(host, ev, "hostReturn")
    got, ev["backWithin"] = wait_until(lambda: on_page(client, s["id"]), W_HOLD)
    time.sleep(SETTLE_S)
    d = delta(ends(host), e0)
    ev.update(clientCellOfItem=cell_of(client, s["id"]), endsDelta=d, h3Gone=ctx.get("H3gone"), look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"H4-back": (bool(ctx.get("H3gone")) and bool(got) and d["put"] == 1,
                        f"gone after H3's pick {ctx.get('H3gone')}; {s['id']} on the client's page at {ev['clientCellOfItem']} "
                        f"(want a page cell within {W_HOLD} s); host ends.put delta {d['put']} (want 1)")}


def row_h5(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ctx["cells"]["H5"]
    e0 = ends(host)
    k, ev["pick"] = pick(client, s["cell"]["client"], [s["id"]])
    gone, ev["goneWithin"] = wait_until(lambda: parked(host, k), W_HOLD)
    ev["hostCellAfterPick"] = cell_of(host, k)
    give_back(client, ev, "clientReturn")
    back, ev["backWithin"] = wait_until(lambda: on_page(host, k), W_HOLD)
    time.sleep(SETTLE_S)
    d = delta(ends(host), e0)
    ev.update(hostCellAfterCancel=cell_of(host, k), endsDelta=d, look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"H5-back": (bool(gone) and bool(back), f"{k} on the host's ground: {ev['hostCellAfterPick']} after the pick (want x "
                                                   f"{PARK_X}), {ev['hostCellAfterCancel']} after the cancel (want a page cell)"),
            "H5-once": (d["cancel"] == 1, f"host ends delta over H5 {d} (want cancel 1)")}


def row_h6(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ctx["cells"]["H6"]
    d0 = counter(host, "denies")
    r = host.cmd({"cmd": "equip_holds_defer", "on": True})
    ev["deferOn"] = {k: r.get(k) for k in ("ok", "on", "error")}
    if not (r.get("ok") and r.get("on") is True):
        raise AssertionError(f"precondition: equip_holds_defer on answered {ev['deferOn']}")
    p, ev["hostPick"] = pick(host, s["cell"]["host"], [s["id"]])
    if cell_of(client, p) != tuple(s["cell"]["client"]):
        raise AssertionError(f"precondition: the client lists {p} at {cell_of(client, p)} (want {s['cell']['client']})")
    _, ev["clientPick"] = pick(client, s["cell"]["client"], [p])
    time.sleep(W_HOLD)
    r = host.cmd({"cmd": "equip_holds_defer", "on": False})
    ev["deferOff"] = {k: r.get(k) for k in ("ok", "on", "error")}
    _, ev["emptyWithin"] = wait_until(lambda: cursor(client) == -1, W_HOLD)
    v, hc, dd = inv_view(client), cursor(host), counter(host, "denies") - d0
    ev.update(client=brief(v), hostCursor=hc, deniesDelta=dd, look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"H6-deny": (dd == 1, f"host holds.denies delta {dd} (want 1)"),
            "H6-line": (v.get("selectedItem") == -1 and v.get("lineText") == TEXT_ITEM_MISSING,
                        f"client cursor {v.get('selectedItem')}, line {v.get('lineText')!r} (want -1 and {TEXT_ITEM_MISSING!r} within "
                        f"{W_HOLD} s of the lever's off)"),
            "H6-host": (hc == p, f"the host's cursor {hc} (want {p} still on it)")}


def pvp_to_briefings(host, client, key):
    """RAE's lobby_e6 (the client joins and takes the Alien team, gamemode 2) and its drive (Small Scout, set_seed,
    newbattle_ok, both briefings up). Returns the gamemode."""
    BER.raw.skirmish_host(host, key)
    BER.raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": BER.raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: BER.raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, BER.raw.CLIENT_PLAYER), "team": "Alien"})
    time.sleep(1)   # the change_team broadcast settles on the client (PSR PHASE 0)
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    m = host.cmd({"cmd": "newbattle_mission", "type": MISSION_PVP})
    assert m.get("ok"), f"newbattle_mission {MISSION_PVP}: {m}"
    host.ok({"cmd": "set_seed", "seed": SEED_PVP})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)
    return r.get("gamemode")


def boot_p(host, client):
    m = (host, client)
    ctx = {"m": m, "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("P", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded("P", lambda: host.ok({"cmd": "set_seed", "seed": SEED_PVP}), m)
    ctx["boot"]["gm"] = G3F.guarded("P", lambda: pvp_to_briefings(host, client, KEY_B), m)
    if ctx["boot"]["gm"] != 2 or not (in_battle(host) and in_battle(client)):
        miss("P", f"gamemode {ctx['boot']['gm']} (want 2), inBattle host {in_battle(host)} client {in_battle(client)}", m)
    ctx["clip"] = G3F.guarded("P", lambda: both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2],
                                                               "item": STACK_TYPE}, ("ids",))["ids"][0], m)
    G3F.guarded("P", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("P", "the host's pre-battle screen never came up", m)
    G3F.guarded("P", lambda: session.dismiss_client_briefing(client), m)
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), SCREEN_S)
    if not ok:
        miss("P", f"the client's (alien seat) pre-battle screen not up within {SCREEN_S} s", m)
    ctx["cell"] = {gc.name: cell_of(gc, ctx["clip"]) for gc in m}
    if not all(c and c[0] is not None and 0 <= c[0] < GROUND_COLS for c in ctx["cell"].values()):
        miss("P", f"the dropped clip {ctx['clip']} at {ctx['cell']} (want a page-1 cell on both screens)", m)
    ctx["boot"].update(clip=ctx["clip"], cell=ctx["cell"], pile=[equip(gc).get("pile") for gc in m])
    print(f"[eq2b] boot P: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_hp(host, client, ctx, ev):
    ready(host, client, ctx)
    hc, cc = ctx["cell"]["host"], ctx["cell"]["client"]
    n0, s0 = len(at_cell(host, hc)), counter(client, "sends")
    _, ev["pick"] = pick(client, cc, at_cell(client, cc))
    time.sleep(W_HOLD)
    n1, tab, ds = len(at_cell(host, hc)), table(host), counter(client, "sends") - s0
    ev.update(hostCount=[n0, n1], hostTable=tab, clientSendsDelta=ds, look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"HP-none": (n1 == n0 and tab == [-1, -1, -1, -1] and ds == 0,
                        f"the host's count at {hc} {n0} -> {n1} (want unchanged), host table {tab} (want all -1), the client's "
                        f"sends delta {ds} (want 0; absent = -1 / 0: D274, D293)")}


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
            return G3F.fail_all(rows, f"boot (FIXTURE-STOP, see the CAPTURE {tag} line)")
        fails = sum(run_row(row, order, fns[row], host, client, ctx) for row, order in rows)
        alive_at_end[tag] = alive(host)
        return fails
    finally:
        rc = {}
        try:
            host.cmd({"cmd": "equip_holds_defer", "on": False})
        except Exception:
            pass
        for gc in (host, client):
            try:
                if gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown(expected_returncodes=EXPECTED_RC)
                rc[gc.name] = gc.proc.returncode if gc.proc is not None else None
            except Exception as e:
                rc[gc.name] = f"shutdown: {type(e).__name__}: {str(e)[:200]}"
        print(f"[eq2b] boot {tag} shut down: {rc}", flush=True)


FN_A = {"H1": row_h1, "H1b": row_h1b, "H2": row_h2, "H3": row_h3, "H4": row_h4, "H5": row_h5, "H6": row_h6}
FN_P = {"HP": row_hp}


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    cpu = None
    try:
        cpu = subprocess.Popen(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-y", "-f", "CSV",
                                "-o", CPU_CSV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[eq2b] typeperf not started: {e}", flush=True)
    up = {}
    try:
        fails = run_boot("A", ROWS_A, boot_a, FN_A, "eq2b_a_host", "eq2b_a_client", up)
        fails += run_boot("P", ROWS_P, boot_p, FN_P, "eq2b_p_host", "eq2b_p_client", up)
        crash = sorted(session._crash_log_snapshot() - crash0)
        fails += G3F.verdict("X", ROWS_X[0][1], {"X-crash": (not crash and up.get("A") is True and up.get("P") is True,
                                                             f"new crash files {crash} (want none); host alive at the end of "
                                                             f"boot A {up.get('A')}, boot P {up.get('P')}")},
                             {"crash": crash, "hostAlive": up, "cpu": cpu_pct()})
    finally:
        if cpu is not None:
            cpu.terminate()
            cpu.wait(timeout=10)
    n = sum(len(order) for _, order in ROWS_A + ROWS_P + ROWS_X)
    print(f"\ntest_w2_equip_partner_hold: {n - fails}/{n} cells passed ({'PASS' if not fails else 'FAIL'}) in "
          f"{time.time() - t0:.1f}s; CPU mean {cpu_pct(True)} %; typeperf rc {cpu.returncode if cpu else None}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
