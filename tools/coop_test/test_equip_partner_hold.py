"""test_equip_partner_hold.py: an item the co-op partner picks up on the pre-battle equip screen is reserved at once.
The pile count drops at pick-up and nobody else can take it; the reservation ends when the holder puts it down or
cancels. Between PvP opponents nothing is reserved. Gone / back are read by the held item's id, never by its cell:
vanilla's ground layout slides the next stack into a freed cell. While the host's test command `equip_holds_defer` is
on, the host's hold table is not sent, so the partner's click can land on an item the host already holds.
Boot coop (co-op, LOBBY_KEY, dirs equip_partner_hold_coop_host / equip_partner_hold_coop_client):
test_prebattle_equip.py's spine (copied, never imported) and staging, client first, as soon as both machines hold the
battle: C1 and C2 stripped, one each of STAGE_TYPES plus HOLD_EXTRA (a second STR_RIFLE_CLIP) dropped on PILE; the
client closes its briefing (its screen on C1), then the host. Rows in order (real clicks, inventory_click; a pick = a
left-click on a ground cell with an empty cursor):
  client_pick     the client picks the 2-clip cell: client_pick-count_drops (the host's count at that cell 2 -> 1
                  within W_HOLD), client_pick-table
  host_same_cell  the host left-clicks the same cell, then right-clicks: host_same_cell-mate (its pick is the
                  stack-mate, never the client's item)
  client_drop     the client drops its clip on C1's STR_BELT (0,0): client_drop-land (GUARD), client_drop-once
                  (ends.move delta 1, every other end 0)
  host_pick       the host picks the grenade; the client clicks the cell the grenade held: host_pick-gone (its id off
                  the client's page within W_HOLD), host_pick-noclick (that id never on the client's cursor). The
                  client's cursor is emptied; the host keeps the grenade for host_returns.
  host_returns    the host right-clicks: host_returns-back (host_pick-gone held, the id back on a page cell of the
                  client's screen within W_HOLD, ends.put 1)
  client_cancel   the client picks the smoke grenade, then right-clicks: client_cancel-back (off the host's page, then
                  back), client_cancel-once (ends.cancel 1)
  pick_race       the race: host equip_holds_defer on; the host picks the proximity grenade; the client (still listing
                  it) picks it; W_HOLD; equip_holds_defer off: pick_race-deny (the host's denies delta 1),
                  pick_race-line (the client's cursor empty, its line TEXT_ITEM_MISSING), pick_race-host (GUARD)
Boot pvp (PvP gm2, X-COM equipment for aliens on, LOBBY_KEY after boot coop's shutdown, dirs
equip_partner_hold_pvp_host / equip_partner_hold_pvp_client): test_alien_equip.py's boot client_aliens (copied) plus
one STR_RIFLE_CLIP dropped on PILE while both briefings are up, once the client has applied the host's first evs.
  pvp_pick        the alien client picks the clip: pvp_pick-no_hold (GUARD: the host's count unchanged, its table all
                  -1, the client's sends delta 0)
  END             after both boots: no_crash (GUARD: no new crash file, both hosts alive)
A count = the number of that screen's inventory_view.ground entries at the cell (x, y); an id is off the page when its
ground x is PARK_X (Inventory::arrangeGround parks it there); holds = event_state.equip.presence.holds (absent: table
-1, counters 0). Counters read as the row's delta. Every row ends with both cursors empty (the holder's right-click,
recorded); a cleanup that fails ends the boot's later rows "not reached".
A build without the hold fails client_pick-count_drops, client_pick-table, host_same_cell-mate, client_drop-once,
host_pick-gone, host_pick-noclick, host_returns-back, client_cancel-back, client_cancel-once, pick_race-deny and
pick_race-line (11 of 15) and passes client_drop-land, pick_race-host, pvp_pick-no_hold and no_crash.
One EVIDENCE line per row (both tops, both inventory_view briefs, both holds, CPU at the row start, the row's reads),
one PASS / FAIL line per cell, then the row verdict; every row runs after a failure (a precondition miss ends its own
row, its cells "not reached"); a boot step past its bound prints ONE CAPTURE line and fails that boot's rows "boot".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_equip_partner_hold.py
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
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

# ----- pinned setup values (the spine's as in test_prebattle_equip.py) -----
LOBBY_KEY = "49284"                # boot coop, then boot pvp after its shutdown
SEED_MAP = 1                       # set_seed right before newbattle_ok
MAP_FP = -4.48310638993e+18        # the host's mapFingerprint at SEED_MAP 1
C_IDS = [8, 9]                     # the client's seated units
C1, C2 = 8, 9
H_IDS = [10, 11, 12, 13, 14]       # the host's own soldiers
PILE = (14, 19, 1)                 # the craft pile tile at turn 0 (co-op and gm2)
STAGE_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE", "STR_SMOKE_GRENADE")
HOLD_EXTRA = "STR_RIFLE_CLIP"      # a second clip: the clip cell holds a stack of 2
STACK_TYPE = "STR_RIFLE_CLIP"
SINGLES = {"host_pick": "STR_GRENADE", "client_cancel": "STR_SMOKE_GRENADE", "pick_race": "STR_PROXIMITY_GRENADE"}
GROUND, BELT = "STR_GROUND", "STR_BELT"
GROUND_COLS, PARK_X = 20, 1000000  # the first ground page; arrangeGround's park column
SEED_PVP, MISSION_PVP = 1, "STR_SMALL_SCOUT"   # test_alien_equip.py's boot client_aliens
TEXT_ITEM_MISSING = "Order cancelled - item unavailable"   # STR_COOP_DENY_ITEM_MISSING
W_HOLD, CLICK_WAIT_S, LAND_WAIT_S, ANSWER_WAIT_S, SETTLE_S, POLL_S = 2.0, 2.0, 10.0, 3.0, 0.5, 0.05
BRIEFING_WAIT_S, ENTRY_WAIT_S, SCREEN_S = 30.0, 5.0, 15.0
ENDS = ("put", "answer", "cancel", "deny", "move", "leave", "start")
EXPECTED_RC = (0, 3221226505)
ROWS_COOP = (("client_pick", ("client_pick-count_drops", "client_pick-table")),
             ("host_same_cell", ("host_same_cell-mate",)),
             ("client_drop", ("client_drop-land", "client_drop-once")),
             ("host_pick", ("host_pick-gone", "host_pick-noclick")),
             ("host_returns", ("host_returns-back",)),
             ("client_cancel", ("client_cancel-back", "client_cancel-once")),
             ("pick_race", ("pick_race-deny", "pick_race-line", "pick_race-host")))
ROWS_PVP = (("pvp_pick", ("pvp_pick-no_hold",)),)
ROWS_END = (("END", ("no_crash",)),)
CPU_CSV = os.path.join(tempfile.gettempdir(), "equip_partner_hold_cpu_s%d.csv" % harness.HARNESS_SLOT)


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
    """A row's head: both pre-battle screens up, the client's cursor empty (the host's too unless it holds
    host_pick's item)."""
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


# ===================== boot coop (test_prebattle_equip.py's spine and staging, copied) =====================


def stage(host, client):
    """C1 and C2 stripped on both machines, then STAGE_TYPES and HOLD_EXTRA dropped on PILE (client first)."""
    rec = {"stripped": {uid: strip_both(host, client, uid) for uid in (C1, C2)}, "ids": {}}
    for t in STAGE_TYPES:
        rec["ids"][t] = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                             ("ids",))["ids"][0]
    rec["extra"] = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": HOLD_EXTRA},
                        ("ids",))["ids"][0]
    rec["diff"] = diff_buckets(host, client)
    return rec


def cells(host, client, ids, extra, m):
    """The pinned cells on both screens, their preconditions checked."""
    page1 = lambda c: bool(c) and c[0] is not None and 0 <= c[0] < GROUND_COLS  # noqa: E731
    out = {}
    sc = {gc.name: cell_of(gc, ids[STACK_TYPE]) for gc in (host, client)}
    st = {n: (sorted(at_cell(gc, sc[n])) if sc[n] else []) for n, gc in (("host", host), ("client", client))}
    if not (page1(sc["host"]) and page1(sc["client"]) and st["host"] == st["client"] == sorted([ids[STACK_TYPE], extra])):
        miss("coop", f"the stack cell: {sc} holds {st} (want the two staged clips at one page-1 cell on both "
             f"screens)", m)
    out["stack"] = {"cell": sc, "ids": st["client"]}
    for row, t in SINGLES.items():
        iid = ids[t]
        c = {gc.name: cell_of(gc, iid) for gc in (host, client)}
        if not all(page1(c[n]) and at_cell(gc, c[n]) == [iid] for n, gc in (("host", host), ("client", client))):
            miss("coop", f"the {row} cell: {t} {iid} at {c} (want one entry at a page-1 cell on both screens)", m)
        out[row] = {"id": iid, "type": t, "cell": c}
    return out


def boot_coop(host, client):
    m = (host, client)
    ctx = {"m": m, "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("coop", lambda: bring_up_lobby_roster_pinned(host, client, LOBBY_KEY), m)
    seated = {}
    G3F.guarded("coop", lambda: session.bring_up_to_briefings(
        host, client, seated, seat_count=2, pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    hb = battle_state(host)
    sid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    got = {"mapFingerprint": hb.get("mapFingerprint"), "seated": [sid.get(s) for s in seated.get("soldierIds", [])],
           "hIds": sorted(u["id"] for u in hb.get("units", []) if u.get("coop") == 0 and u.get("faction") == 0
                          and not u.get("isOut"))}
    ctx["boot"].update(got)
    if (got["mapFingerprint"], got["seated"], got["hIds"]) != (MAP_FP, C_IDS, H_IDS):
        miss("coop", f"the spine: {got} (want MAP_FP {MAP_FP}, seated {C_IDS}, H {H_IDS})", m)
    ok, ctx["boot"]["clientBriefingS"] = wait_until(lambda: has(client, "BriefingState") and in_battle(client),
                                                    BRIEFING_WAIT_S, 0.1)
    if not ok:
        miss("coop", f"no client BriefingState with its battle within {BRIEFING_WAIT_S} s", m)
    # the host's first evs applied before staging
    G3F.guarded("coop", lambda: session.wait_seq_barrier(host, client), m)
    st = ctx["boot"]["staged"] = G3F.guarded("coop", lambda: stage(host, client), m)
    if st["diff"]:
        miss("coop", f"buckets differ after the staging: {st['diff']}", m)
    ctx["boot"]["clientClose"] = client.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    if not ok:
        miss("coop", f"the client's pre-battle screen not up within {ENTRY_WAIT_S} s after its briefing closed", m)
    ctx["boot"]["hostClose"] = host.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("coop", f"the host's pre-battle screen not up within {SCREEN_S} s after its briefing closed", m)
    ctx["seat"] = (battle_state(client).get("authority") or {}).get("localSeat")
    ctx["cells"] = cells(host, client, st["ids"], st["extra"], m)
    ctx["boot"].update(cells=ctx["cells"], seatClient=ctx["seat"], units=[inv_view(gc).get("unitId") for gc in m])
    print(f"[test_equip_partner_hold] boot coop: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_client_pick(host, client, ctx, ev):
    ready(host, client, ctx)
    sc = ctx["cells"]["stack"]["cell"]
    n0 = len(at_cell(host, sc["host"]))
    x, ev["pick"] = pick(client, sc["client"], ctx["cells"]["stack"]["ids"])
    ctx["x"] = x
    _, ev["dropWithin"] = wait_until(lambda: len(at_cell(host, sc["host"])) == n0 - 1, W_HOLD)
    n1, tab = len(at_cell(host, sc["host"])), table(host)
    ev.update(hostCount=[n0, n1], hostAtCell=at_cell(host, sc["host"]), hostTable=tab, look=look(host, client))
    return {"client_pick-count_drops": (n1 == n0 - 1, f"the host's count at {sc['host']}: {n0} -> {n1} (want {n0} -> "
                                                      f"{n0 - 1} within {W_HOLD} s; the client holds {x})"),
            "client_pick-table": (tab[ctx["seat"]] == x, f"host holds.table {tab} (want [{ctx['seat']}] = the client's "
                                                         f"item {x}; absent = -1)")}


def row_host_same_cell(host, client, ctx, ev):
    x, sc = ctx.get("x"), ctx["cells"]["stack"]["cell"]
    if x is None or cursor(client) != x or cursor(host) != -1:
        raise AssertionError(f"precondition: the client holds {cursor(client)} (want client_pick's {x}), the host "
                             f"{cursor(host)} (want empty)")
    mates = [i for i in ctx["cells"]["stack"]["ids"] if i != x]
    y, ev["pick"] = pick(host, sc["host"], ctx["cells"]["stack"]["ids"])
    ev.update(hostItem=y, clientItem=x, mates=mates, look=look(host, client))
    give_back(host, ev, "hostReturn")
    ev["cursorsAfter"] = [cursor(host), cursor(client)]
    if cursor(host) != -1:
        ctx["broken"] = f"the host's cursor {cursor(host)} after host_same_cell's right-click"
    return {"host_same_cell-mate": (y in mates, f"the host's pick {y} (want the stack-mate {mates}, never the client's "
                                                f"{x})")}


def row_client_drop(host, client, ctx, ev):
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
    return {"client_drop-land": (bool(got), f"item {x} host {ev['item']['host']} client {ev['item']['client']} (want "
                                            f"{want} on both within {LAND_WAIT_S} s)"),
            "client_drop-once": (d["move"] == 1 and all(v == 0 for k, v in d.items() if k != "move"),
                                 f"host ends delta over client_drop {d} (want move 1, every other 0; absent = 0)")}


def row_host_pick(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ctx["cells"]["host_pick"]
    g, ev["pick"] = pick(host, s["cell"]["host"], [s["id"]])
    got, ev["goneWithin"] = wait_until(lambda: parked(client, g), W_HOLD)
    ev["clientCellOfItem"], ev["clientAtOldCell"] = cell_of(client, g), at_cell(client, s["cell"]["client"])
    ctx["host_pick_gone"] = bool(got)
    c, ev["clientPick"] = pick(client, s["cell"]["client"])
    ev["look"] = look(host, client)
    cleanup(host, client, ctx, ev, keep_host=True)
    return {"host_pick-gone": (bool(got), f"{s['type']} {g} on the client's ground at {ev['clientCellOfItem']} "
                                          f"(want off the page, x {PARK_X}, within {W_HOLD} s; its old cell "
                                          f"{s['cell']['client']} now holds {ev['clientAtOldCell']})"),
            "host_pick-noclick": (c != g, f"the client's click on {s['cell']['client']} put {c} on its cursor (want "
                                          f"never {g})")}


def row_host_returns(host, client, ctx, ev):
    s = ctx["cells"]["host_pick"]
    ready(host, client, ctx, host_empty=False)
    if cursor(host) != s["id"]:
        raise AssertionError(f"precondition: the host holds {cursor(host)} (want host_pick's {s['id']})")
    e0 = ends(host)
    give_back(host, ev, "hostReturn")
    got, ev["backWithin"] = wait_until(lambda: on_page(client, s["id"]), W_HOLD)
    time.sleep(SETTLE_S)
    d = delta(ends(host), e0)
    ev.update(clientCellOfItem=cell_of(client, s["id"]), endsDelta=d, hostPickGone=ctx.get("host_pick_gone"),
              look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"host_returns-back": (bool(ctx.get("host_pick_gone")) and bool(got) and d["put"] == 1,
                        f"gone after host_pick's pick {ctx.get('host_pick_gone')}; {s['id']} on the client's page at "
                        f"{ev['clientCellOfItem']} (want a page cell within {W_HOLD} s); host ends.put delta "
                        f"{d['put']} (want 1)")}


def row_client_cancel(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ctx["cells"]["client_cancel"]
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
    return {"client_cancel-back": (bool(gone) and bool(back),
                                   f"{k} on the host's ground: {ev['hostCellAfterPick']} after the pick (want x "
                                   f"{PARK_X}), {ev['hostCellAfterCancel']} after the cancel (want a page cell)"),
            "client_cancel-once": (d["cancel"] == 1, f"host ends delta over client_cancel {d} (want cancel 1)")}


def row_pick_race(host, client, ctx, ev):
    ready(host, client, ctx)
    s = ctx["cells"]["pick_race"]
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
    return {"pick_race-deny": (dd == 1, f"host holds.denies delta {dd} (want 1)"),
            "pick_race-line": (v.get("selectedItem") == -1 and v.get("lineText") == TEXT_ITEM_MISSING,
                        f"client cursor {v.get('selectedItem')}, line {v.get('lineText')!r} (want -1 and {TEXT_ITEM_MISSING!r} within "
                        f"{W_HOLD} s of equip_holds_defer off)"),
            "pick_race-host": (hc == p, f"the host's cursor {hc} (want {p} still on it)")}


def pvp_to_briefings(host, client, key):
    """test_alien_equip.py's lobby_client_aliens (the client joins and takes the Alien team, gamemode 2) and its drive
    (Small Scout, set_seed, newbattle_ok, both briefings up). Returns the gamemode."""
    BER.raw.skirmish_host(host, key)
    BER.raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": BER.raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: BER.raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, BER.raw.CLIENT_PLAYER), "team": "Alien"})
    time.sleep(1)   # the change_team broadcast settles on the client
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    m = host.cmd({"cmd": "newbattle_mission", "type": MISSION_PVP})
    assert m.get("ok"), f"newbattle_mission {MISSION_PVP}: {m}"
    host.ok({"cmd": "set_seed", "seed": SEED_PVP})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)
    return r.get("gamemode")


def boot_pvp(host, client):
    m = (host, client)
    ctx = {"m": m, "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("pvp", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded("pvp", lambda: host.ok({"cmd": "set_seed", "seed": SEED_PVP}), m)
    ctx["boot"]["gm"] = G3F.guarded("pvp", lambda: pvp_to_briefings(host, client, LOBBY_KEY), m)
    if ctx["boot"]["gm"] != 2 or not (in_battle(host) and in_battle(client)):
        miss("pvp", f"gamemode {ctx['boot']['gm']} (want 2), inBattle host {in_battle(host)} client "
             f"{in_battle(client)}", m)
    # the host's first evs applied before staging: the drop runs on each machine on its own, so a drop that lands
    # on the client before an ev already on its way puts the clip in that ev's hash check on the client only
    G3F.guarded("pvp", lambda: session.wait_seq_barrier(host, client), m)
    ctx["clip"] = G3F.guarded("pvp", lambda: both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1],
                                                                 "z": PILE[2], "item": STACK_TYPE},
                                                  ("ids",))["ids"][0], m)
    G3F.guarded("pvp", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("pvp", "the host's pre-battle screen never came up", m)
    G3F.guarded("pvp", lambda: session.dismiss_client_briefing(client), m)
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), SCREEN_S)
    if not ok:
        miss("pvp", f"the client's (alien seat) pre-battle screen not up within {SCREEN_S} s", m)
    ctx["cell"] = {gc.name: cell_of(gc, ctx["clip"]) for gc in m}
    if not all(c and c[0] is not None and 0 <= c[0] < GROUND_COLS for c in ctx["cell"].values()):
        miss("pvp", f"the dropped clip {ctx['clip']} at {ctx['cell']} (want a page-1 cell on both screens)", m)
    ctx["boot"].update(clip=ctx["clip"], cell=ctx["cell"], pile=[equip(gc).get("pile") for gc in m])
    print(f"[test_equip_partner_hold] boot pvp: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_pvp_pick(host, client, ctx, ev):
    ready(host, client, ctx)
    hc, cc = ctx["cell"]["host"], ctx["cell"]["client"]
    n0, s0 = len(at_cell(host, hc)), counter(client, "sends")
    _, ev["pick"] = pick(client, cc, at_cell(client, cc))
    time.sleep(W_HOLD)
    n1, tab, ds = len(at_cell(host, hc)), table(host), counter(client, "sends") - s0
    ev.update(hostCount=[n0, n1], hostTable=tab, clientSendsDelta=ds, look=look(host, client))
    cleanup(host, client, ctx, ev)
    return {"pvp_pick-no_hold": (n1 == n0 and tab == [-1, -1, -1, -1] and ds == 0,
                        f"the host's count at {hc} {n0} -> {n1} (want unchanged), host table {tab} (want all -1), the client's "
                        f"sends delta {ds} (want 0; absent = -1 / 0)")}


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
        print(f"[test_equip_partner_hold] boot {tag} shut down: {rc}", flush=True)


FN_COOP = {"client_pick": row_client_pick, "host_same_cell": row_host_same_cell, "client_drop": row_client_drop,
           "host_pick": row_host_pick, "host_returns": row_host_returns, "client_cancel": row_client_cancel,
           "pick_race": row_pick_race}
FN_PVP = {"pvp_pick": row_pvp_pick}


def main():
    t0 = time.time()
    crash0 = session._crash_log_snapshot()
    cpu = None
    try:
        cpu = subprocess.Popen(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-y", "-f", "CSV",
                                "-o", CPU_CSV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[test_equip_partner_hold] typeperf not started: {e}", flush=True)
    up = {}
    try:
        fails = run_boot("coop", ROWS_COOP, boot_coop, FN_COOP, "equip_partner_hold_coop_host",
                         "equip_partner_hold_coop_client", up)
        fails += run_boot("pvp", ROWS_PVP, boot_pvp, FN_PVP, "equip_partner_hold_pvp_host",
                          "equip_partner_hold_pvp_client", up)
        crash = sorted(session._crash_log_snapshot() - crash0)
        fails += G3F.verdict("END", ROWS_END[0][1],
                             {"no_crash": (not crash and up.get("coop") is True and up.get("pvp") is True,
                                           f"new crash files {crash} (want none); host alive at the end of "
                                           f"boot coop {up.get('coop')}, boot pvp {up.get('pvp')}")},
                             {"crash": crash, "hostAlive": up, "cpu": cpu_pct()})
    finally:
        if cpu is not None:
            cpu.terminate()
            cpu.wait(timeout=10)
    n = sum(len(order) for _, order in ROWS_COOP + ROWS_PVP + ROWS_END)
    print(f"\ntest_equip_partner_hold: {n - fails}/{n} cells passed ({'PASS' if not fails else 'FAIL'}) in "
          f"{time.time() - t0:.1f}s; CPU mean {cpu_pct(True)} %; typeperf rc {cpu.returncode if cpu else None}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
