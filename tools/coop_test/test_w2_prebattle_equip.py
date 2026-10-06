"""W2-P8b - test_w2_prebattle_equip.py: pre-battle equip for both players. Both
briefings show at once, each player lands on the vanilla pre-battle equip screen for
its own soldiers, every change the second player makes is an order the host
performs, OK is a 'ready' toggle, and turn 1 starts on the host when every seat
that has something to equip is ready (spec docs rewrite/prompts/w2p8b_prebattle_equip.md:
owner D174 a, D205 a, D206 c, D207 a, D208 a, D210 b, D215 a, D216 c; the draft's
(f); AMENDMENT P8b-1 section 4 (the pinned stage text), section 5 (this file's rows,
fixtures, probes and RED/GREEN cells) and section 8; P8b-1 RULINGS Q15 (a), Q16 (a);
AMENDMENT P8b-2 (the TASK 0 constants F3314-F3331)).

Before S-A.2 (product untouched, commit S-A.1) the host's battle file goes out only
when the host closes its own briefing, the host's pre-battle equip is frozen (its
briefing OK starts turn 1 at once, "Pre-battle equipment is locked in co-op") and the
second player never gets an equip screen.

Boot A (ONE boot; rows in this order; each row ONE run): the roster-pinned lobby
(set_seed SEED_ROSTER before open_new_battle), session.bring_up_to_briefings (the
client seated C1, C2; the host keeps H), set_seed SEED_MAP right before newbattle_ok,
the host's mapFingerprint = MAP_FP. The fixture spine is fixed at red and green:
  bring_up_to_briefings -> EQ1 -> [staging, as soon as both machines hold the
  battle; then S-B's staging] -> EQ2 -> EQ3b -> [EQ3's hold] -> EQ9 -> [spine: host
  close_briefing; a client BriefingState still up is closed; staging if not done yet]
  -> EQ3 (the held order lands) -> EQ4 -> EQ5 -> EQ6 -> EQ15 -> EQ10 -> EQ11 -> EQ12
  -> EQ14 -> T0-6 -> [spine: the client's screen back on C2, where S-A's EQ7 finds it]
  -> EQ7 (with EQ7b) -> EQ8.
Staging (client first, F607; P8b-2: staged ids, never stock ids): C1 and C2 stripped on
both machines, then one each of STAGE_TYPES dropped on the pile PILE. A row reads its
item's ground cell from inventory_view.ground and moves the item actually picked
(a stack-mate of the staged id at that cell, recorded).
S-B's staging (stage W2-P8b S-B, right after S-A's, client first): C1 gets a rifle
loaded with a clip in STR_BACK_PACK (0,0) (battle_give; the ids recorded), and
SB_PILE_DROPS go on PILE (types S-A already staged, so they stack in S-A's ground cells
and move no S-A item's cell). An S-B row looks its pile item up by type at run time:
vanilla's pick returns the first item in tile-inventory order at the clicked cell
(BattleUnit::getItem), which is the first ground entry of that type in inventory_view.
S-B rows (AMENDMENT P8b-1 section 4 S-B and section 5; owner D205 a, D207 a: pre-battle
placements are host orders with no TU cost and vanilla's `!_tu` rules). The client's
screen shows C1; C1's TU is read on both machines before and after each row.
  EQ10  TU-free move: the client moves a pile rifle clip to C1's STR_RIGHT_LEG (0,0).
        GREEN: it lands there on both, C1's tu unchanged on both. RED: the battle move
        cost (ground -> leg 10, xcom1 inventories.rul) spent on both.
  EQ11  Shift-load (vanilla `!_tu` quick-swap): the client picks a pile rifle clip N
        and Shift-drops it on C1's loaded rifle R in STR_BACK_PACK. GREEN: R holds N,
        R's old clip on the ground at PILE on both, C1's tu unchanged. RED: the host
        refuses it by the battle rules (in battle only a weapon held in a hand
        quick-swaps: `invalid_target`, silent), R keeps its old clip.
  EQ12  UNLOAD widget: the client picks R from STR_BACK_PACK, then UNLOAD. GREEN: R in
        STR_RIGHT_HAND, its clip in STR_LEFT_HAND on both, C1's tu unchanged. RED: the
        battle cost (the unload plus the move to the hand) spent on both.
  EQ14  the host's cursor item (F3125): the host picks Y (the first pile grenade, the
        same id first at its cell on both machines) onto its cursor; the client picks
        Y and drops it on C1's STR_LEFT_LEG (0,0). GREEN: the client's line text =
        STR_COOP_DENY_ITEM_MISSING's (invWarningWrites +1, lastDeny item_missing), Y
        still on the host's cursor and on the pile on both; then the host's right-click
        returns Y. RED: the host executes the order (Y on C1 on both).
  T0-6  the pile holds (P8b-2's T0-6 ruling, STOP-IF 8): the host Ctrl-clicks a pile
        rifle clip onto its own soldier (a host equip placement at turn 0). GREEN (and
        at S-B.1: S-A built it): the clip on that H soldier on both, the client applied
        the host's evs, and the client's pre-battle ground ids = the host's pile ids =
        the host screen's ground ids.
  RED (commit S-B.1): exactly EQ10, EQ11, EQ12, EQ14 fail, each on its RED cell; every
  other row passes.
  EQ1   both briefings (D210 b): the host's BriefingState is up; wait <= 30 s for the
        client's. GREEN: the client's BriefingState up while the host's is up, turn 0
        on both, the client's mapFingerprint = MAP_FP. RED: the wait fails (no offer
        before the host's OK).
  EQ2   client first (D174): client close_briefing. GREEN: client top InventoryState,
        preBattle, unitId in C, its `ground` ids = the host's battle_items on PILE, the
        client's equip.pile (the offer's pile) = PILE, the host still on its briefing. RED: precondition
        absent (no client battle).
  EQ3b  a rename in the window (F3108): NEXT to C2, click the name field (P8-4c T0-R2),
        one letter, then PREV back to C1 - run just BEFORE EQ3's pick, because vanilla
        refuses PREV/NEXT while an item rides the cursor (InventoryState.cpp
        btnNextClick) and EQ3 holds its clip there. GREEN: C2's name, _name and rawName
        = the old name + the letter on both, host renames.applied +1, host alive, turn 0.
  EQ3   held until open (Q3 a): the client picks the staged clip from the pile and drops
        it on C1's belt (0,0) while the host reads its briefing. GREEN: the client's
        invLastWarning = STR_COOP_DENY_BUSY's text (invWarningWrites +1), host
        equip.heldUntilOpen 1, host alive; after the spine's host close_briefing the
        host's screen shows a unit in H, and within 10 s the clip is on C1's belt (0,0)
        on both.
  EQ9   END TURN in the window (b8), during EQ3's hold: the client's
        battle_end_turn_ready {ready: true}. GREEN: host alive, equip.endTurnIgnored 1,
        turn 0 on both.
  EQ4   own units only: each machine inventory_click {widget: next} x its own count.
        GREEN: the visited ids = the own set on each machine. RED: no client screen
        (the freeze text on the banner).
  EQ5   ready toggle (D206 c, D216 c): client inventory_click {widget: ok} x3. GREEN:
        press 1 -> host equip.ready[1] true, client okPressed true, the client's screen
        still on top, turn 0, and at +1.5 s its line "Waiting for HostPlayer to finish
        equipping" visible; press 2 -> all false, the line not visible at +1.5 s;
        press 3 -> as 1.
  EQ6   edit after ready: the ready client moves the staged grenade to C2's belt (0,0).
        GREEN: it lands on both, still ready, the D216 line back within 1.5 s.
  EQ15  host refresh: the client moves the staged rifle to C2's right hand, no host
        input. GREEN: the host's inventory_view.ground loses the rifle and its
        hostScreens.refreshes +1 or more (M4 counts one refresh per pump pass after a host
        emission; HS4's bar).
  EQ7   the barrier (Q4 a, Q5 a) with EQ7b: a. client ok (un-ready) b. host ok (ready)
        c. the host picks X (the staged proximity grenade) d. host defer_intents {ms 3000,
        count 1}, the client Ctrl-clicks Z (the staged smoke grenade; no cursor) e.
        client ok. GREEN: b: the host's line "Waiting for ClientPlayer to finish
        equipping" visible at +1.5 s; e: X back on the pile on both, both screens gone,
        host barrierDone; +3.5 s after d: host lateDenied 1, Z on the pile on both, the
        client's lastDeny reason invalid_target, its invLastWarning unchanged.
  EQ8   turn 1: turn 1 on both, one host `sync` with equip.end (host endSyncs 1, the
        client applied 1), the host's turn right after its briefing OK was 0, the
        client's equip entries 1; the client's NextTurnState on top, then its
        BattlescapeState after one real key; the client's battle_open_inventory C1, then
        C2, each shows the soldier's own tile (= the host's battle_items there; C1 is the
        generator's first soldier and stands on the ramp tile that is the pile, so C2 -
        off the pile, asserted - carries the proof); hostCovered, hostScreens.closes
        and invForcedCloses unchanged since EQ2, forceCloseSkips 0; the host's
        selectedId in H. RED: the host's turn 1 at its briefing OK (freeze), the client
        never on an equip screen.
  RED (commit S-A.1): every row above fails on its RED cell (EQ7b inside EQ7).

Common asserts, every row (with both machines in the battle): hash_now {full:true}
every bucket EQUAL after the queues drain; desyncSeen false on both; the client's
turnMirrorFired 0; coopClientBStatePushes 0 on both; the client's invLocalWrites 0;
while the client's pre-battle screen is open, its ground ids = the host's pile ids
(STOP-IF 8).

Constants (AMENDMENT P8b-2 / docs rewrite/w2p8b-task0/t0/logs, F3326): SEED_ROSTER 1,
SEED_MAP 1 (tseed.py), MAP_FP (tseed_parallel.log / t01_default.log), C [8, 9], H
[10..14], PILE (14, 19, 1) (tseed_parallel.log "[seed] pile=[14, 19, 1] C=[8, 9]
H=[10, 11, 12, 13, 14]"), the texts (en-US; exact text).

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked; main()
runs every row even after an earlier one failed and prints "PASS <id>" / "FAIL <id>:
<message>". Every wait is bounded. WV-D99 / WV-D100: one run is the result; no skip
path, no second boot. Exit 0 only when every row passes, 2 otherwise (a bring-up or
spine failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_prebattle_equip.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
from test_w2_delta_core import diff_buckets, desync_record, short, both
from test_w2_delta_items import items_by_id
from test_w2_host_combat import bring_up_lobby_roster_pinned
from test_w2_client_items import strip_both

# ----- bring-up (AMENDMENT P8b-2 / TASK 0, F3326) -----
PORT = "48791"                     # this file's lobby port (unused by every other test file)
SEED_MAP = 1                       # set_seed right before newbattle_ok (tseed.py)
MAP_FP = -4.48310638993e+18        # host = client mapFingerprint at SEED_MAP 1 (tseed_parallel.log)
C_IDS = [8, 9]                     # the client's seated units (F3326)
C1, C2 = 8, 9
H_IDS = [10, 11, 12, 13, 14]       # the host's own soldiers (F3326)
PILE = (14, 19, 1)                 # the craft pile tile at turn 0 (F3326)
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
STAGE_TYPES = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE", "STR_SMOKE_GRENADE")
GROUND = "STR_GROUND"
BELT = "STR_BELT"
RIGHT_HAND = "STR_RIGHT_HAND"
GROUND_COLS = 20                   # Inventory::_groundSlotsX = (320 - STR_GROUND x 0) / 16: the first ground page

# ----- S-B (AMENDMENT P8b-1 section 4 S-B, section 5 rows EQ10-EQ12, EQ14; P8b-2's T0-6 ruling) -----
RIFLE_T, CLIP_T, GRENADE_T = "STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE"
SB_PILE_DROPS = (CLIP_T, CLIP_T, CLIP_T, GRENADE_T)   # EQ10's, EQ11's and T0-6's clips; EQ14's Y
BACK_PACK = "STR_BACK_PACK"
LEFT_HAND = "STR_LEFT_HAND"
RIGHT_LEG = "STR_RIGHT_LEG"
LEFT_LEG = "STR_LEFT_LEG"
TU_GROUND_TO_LEG = 10              # xcom1 inventories.rul STR_GROUND -> STR_RIGHT_LEG / STR_LEFT_LEG (RED evidence)

# ----- texts (en-US; exact text) -----
TEXT_FROZEN = "Pre-battle equipment is locked in co-op"     # STR_COOP_EQUIP_FROZEN (the freeze; RED)
TEXT_BUSY = "Waiting - another action is in progress"      # STR_COOP_DENY_BUSY (Q3 a: the held order)
TEXT_WAIT_HOST = "Waiting for HostPlayer to finish equipping"      # D216 c on the client ({0} = the host)
TEXT_WAIT_CLIENT = "Waiting for ClientPlayer to finish equipping"  # D216 c on the host ({0} = the client)
TEXT_ITEM_MISSING = "Order cancelled - item unavailable"   # STR_COOP_DENY_ITEM_MISSING (EQ14, F3125)

# ----- the rename recipe (P8-4c T0-R2, test_w2_inventory.py) -----
NAME_FIELD_RECT = (28, 6, 210, 17)  # InventoryState.cpp `new TextEdit(this, 210, 17, 28, 6)`
NAME_CLICK = (266, 29)              # the rect's centre x 2 (the harness window is 640x400)
UNFOCUS_CLICK = (520, 150)          # base (260, 75) x 2: text only (the stat lines), no button; the focused
                                    # name field is modal and takes this click to drop its focus
RENAME_LETTER = ("x", 120)          # the inject_input key = the SDL sym
KEY_SETTLE_S = 0.3
NAME_SYNC_S = 3.0
SDLK_RETURN = 13                    # the "one real key" that closes the client's Turn-1 screen (EQ8)

# ----- waits -----
EQ1_WAIT_S = 30.0                  # EQ1 cell: "wait <= 30 s for the client's BriefingState"
CLIENT_BATTLE_WAIT_S = 90.0        # the spine: the client's battle after the host's OK (drive_to_battlescape's 90 s)
ENTRY_WAIT_S = 5.0                 # the client's equip screen after its briefing closes
CLICK_WAIT_S = 2.0
ANSWER_WAIT_S = 3.0                # a held deny / a ready flag / a counter reaches the other machine
LAND_WAIT_S = 10.0                 # EQ3 cell: "within 10 s the clip is on C1's belt on both"
LINE_READ_S = 1.5                  # F3112: the line fades in 1.2 s; read 1.5 s after the event
BARRIER_WAIT_S = 5.0
DEFER_MS = 3000                    # EQ7b: defer_intents {ms 3000, count 1}
LATE_READ_S = 3.5                  # EQ7 cell: "+3.5 s: lateDenied 1" (the first read)
LATE_WAIT_S = 6.0                  # ... bounded: the deferred order is dispatched DEFER_MS after the host took it
TURN_WAIT_S = 5.0
DRAIN_WAIT_S = 10.0
POLL_S = 0.05


# ===================== small probes =====================


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # a dead instance
        return [f"<no stack: {short(e, 120)}>"]


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def has(gc, name):
    return any(name in s for s in stack(gc))


def es(gc):
    return event_state(gc)


def equip(gc):
    return es(gc).get("equip") or {}


def turn(gc):
    return battle_state(gc).get("turn")


def in_battle(gc):
    return battle_state(gc).get("inBattle") is True


def alive(gc):
    running = gc.proc is not None and gc.proc.poll() is None
    if not running:
        return False
    try:
        return bool(gc.cmd({"cmd": "ping"}).get("pong"))
    except Exception:
        return False


def inv_view(gc):
    """inventory_view without the static `slots` table."""
    r = gc.cmd({"cmd": "inventory_view"})
    if not r.get("ok"):
        return {"error": r.get("error"), "open": None, "ground": []}
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "ground", "preBattle", "okPressed",
                                  "lineText", "lineVisible")}


def view_brief(v):
    return {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem", "preBattle", "okPressed", "lineText",
                                  "lineVisible", "error")}


def screen_up(gc):
    """This machine's pre-battle equip screen is open and on top."""
    v = inv_view(gc)
    return v.get("open") is True and v.get("top") is True and v.get("preBattle") is True


def ground_ids(v):
    return sorted(g["id"] for g in (v.get("ground") or []))


def pile_ids(its):
    return sorted(i for i, it in its.items() if it.get("onTile") and (it.get("tx"), it.get("ty"), it.get("tz")) == PILE)


def item_view(its, iid):
    it = its.get(iid)
    return {k: it.get(k) for k in ("type", "owner", "slot", "slotX", "slotY", "onTile", "tx", "ty", "tz")} if it else None


def on_pile(it):
    return bool(it) and it.get("onTile") is True and it.get("owner") in (None, -1) \
        and (it.get("tx"), it.get("ty"), it.get("tz")) == PILE


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


def evidence(row, fields):
    print(f"EVIDENCE {row}: " + json.dumps(fields, sort_keys=True, default=str), flush=True)


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


# ===================== inventory clicks =====================


def click(gc, **kw):
    req = {"cmd": "inventory_click"}
    req.update(kw)
    r = gc.cmd(req)
    if kw.get("mod"):
        gc.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    return {"req": kw, "ok": r.get("ok"), "error": r.get("error"), "base": (r.get("baseX"), r.get("baseY"))}


def cell_of(v, iid):
    for g in v.get("ground") or []:
        if g.get("id") == iid:
            return (g.get("x"), g.get("y"))
    return None


def mates_at(v, cell):
    return sorted(g["id"] for g in (v.get("ground") or []) if (g.get("x"), g.get("y")) == cell)


def pick_ground(gc, iid, rec):
    """Click the ground cell of staged item `iid` on `gc`'s top InventoryState with an empty cursor. Returns the
    id actually picked (the staged id or a stack-mate at its cell), or None; fills `rec`."""
    v = inv_view(gc)
    cell = cell_of(v, iid)
    rec["cell"] = cell
    rec["cursorBefore"] = v.get("selectedItem")
    if cell is None:
        rec["error"] = f"staged item {iid} is not on this screen's ground {ground_ids(v)}"
        return None
    if cell[0] is None or cell[0] >= GROUND_COLS:
        rec["error"] = f"staged item {iid} lies at ground column {cell[0]}, off the first ground page"
        return None
    rec["mates"] = mates_at(v, cell)
    rec["click"] = click(gc, slot=GROUND, x=cell[0], y=cell[1])
    got, dt = wait_until(lambda: inv_view(gc).get("selectedItem") not in (None, -1), CLICK_WAIT_S)
    picked = inv_view(gc).get("selectedItem")
    rec["picked"] = picked
    rec["waited"] = dt
    if not got or picked not in rec["mates"]:
        rec["error"] = f"the pick left {picked} on the cursor (want one of {rec['mates']})"
        return None
    return picked


def next_press(gc, rec_list):
    before = inv_view(gc).get("unitId")
    c = click(gc, widget="next")
    wait_until(lambda: inv_view(gc).get("unitId") != before, CLICK_WAIT_S)
    after = inv_view(gc).get("unitId")
    rec_list.append({"from": before, "to": after, "click": c.get("error") or c.get("ok")})
    return after


def goto_unit(gc, uid, own, rec_list):
    """NEXT until the screen shows `uid` (at most len(own) presses). True when reached."""
    if inv_view(gc).get("unitId") == uid:
        return True
    for _ in range(len(own)):
        if next_press(gc, rec_list) == uid:
            return True
    return False


def ok_press(gc):
    return click(gc, widget="ok")


# ===================== the common tail =====================


def drained(host, client):
    ec, eh = es(client), es(host)  # W2-U8c (F6561): the client is read first
    return (ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0) and ec.get("queueDepth") == 0
            and eh.get("queueDepth") == 0)


def tail_fails(host, client, what):
    """The per-row common asserts. Needs both machines in the battle (a row whose precondition is absent
    records that instead)."""
    if not (in_battle(host) and in_battle(client)):
        return [f"{what}: common asserts not run - a machine holds no battle (host inBattle "
                f"{in_battle(host)}, client inBattle {in_battle(client)})"]
    fails = []
    got, _ = wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    if not got:
        fails.append(f"{what}: the client never caught up (host lastSeqEmitted {es(host).get('lastSeqEmitted')}, "
                     f"client lastSeqApplied {es(client).get('lastSeqApplied')})")
    d = diff_buckets(host, client)
    if d:
        fails.append(f"{what}: hash_now full buckets differ: {d} (want every bucket EQUAL)")
    eh, ec = es(host), es(client)
    if eh.get("desyncSeen") or ec.get("desyncSeen"):
        fails.append(f"{what}: desyncSeen host={eh.get('desyncSeen')} client={ec.get('desyncSeen')} "
                     f"({desync_record(client, ec.get('desyncSeen'))}; want false on both)")
    if ec.get("turnMirrorFired") != 0:
        fails.append(f"{what}: client turnMirrorFired={ec.get('turnMirrorFired')} (want 0)")
    if ec.get("coopClientBStatePushes") != 0 or eh.get("coopClientBStatePushes") != 0:
        fails.append(f"{what}: coopClientBStatePushes host={eh.get('coopClientBStatePushes')} "
                     f"client={ec.get('coopClientBStatePushes')} (want 0 on both)")
    if ec.get("invLocalWrites") != 0:
        fails.append(f"{what}: client invLocalWrites={ec.get('invLocalWrites')} (want 0)")
    cv = inv_view(client)
    if cv.get("open") and cv.get("preBattle"):
        hp = pile_ids(items_by_id(host))
        if ground_ids(cv) != hp:
            fails.append(f"{what}: STOP-IF 8 - the client's pre-battle ground {ground_ids(cv)} != the host's pile "
                         f"ids {hp}")
    return fails


def pre_screen_fails(host, client, what, host_too=False):
    """The RED precondition of every row after EQ2: the client's (and the host's) pre-battle screen."""
    fails = []
    cv = inv_view(client)
    if not (cv.get("open") and cv.get("top") and cv.get("preBattle")):
        fails.append(f"{what}: no client equip screen (client stack {stack(client)}, inventory_view "
                     f"{view_brief(cv)}, client banner {battle_state(client).get('coopWaitText')!r}, freeze text "
                     f"{TEXT_FROZEN!r})")
    if host_too:
        hv = inv_view(host)
        if not (hv.get("open") and hv.get("top") and hv.get("preBattle")):
            fails.append(f"{what}: no host equip screen (host stack {stack(host)}, inventory_view "
                         f"{view_brief(hv)}, host turn {turn(host)})")
    return fails


# ===================== staging (client first, F607) =====================


def stage(host, client, ctx, when):
    """C1 and C2 stripped on both machines, then one each of STAGE_TYPES dropped on PILE (client first). The
    staging record = the ids (P8b-2: never stock ids)."""
    rec = {"when": when}
    try:
        rec["stripped"] = {uid: strip_both(host, client, uid) for uid in (C1, C2)}
        ids = {}
        for t in STAGE_TYPES:
            r = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                     ("ids",))
            ids[t] = r["ids"][0]
        rec["ids"] = ids
        rec["diff"] = diff_buckets(host, client)
        rec["turn"] = [turn(host), turn(client)]
    except Exception as e:
        rec["error"] = short(e, 400)
    ctx["staged"] = rec
    print(f"STAGE {json.dumps(rec, sort_keys=True, default=str)}", flush=True)


def staged_id(ctx, t):
    return ((ctx.get("staged") or {}).get("ids") or {}).get(t)


def staged_fails(ctx, what):
    s = ctx.get("staged")
    if not s:
        return [f"{what}: nothing staged yet (the client held no battle)"]
    if s.get("error"):
        return [f"{what}: the staging failed: {s['error']}"]
    if s.get("diff"):
        return [f"{what}: buckets differ after the staging: {s['diff']}"]
    return []


# ===================== rows =====================


def eq1_both_briefings(host, client, ctx):
    got, dt = wait_until(lambda: has(client, "BriefingState"), EQ1_WAIT_S, 0.1)
    hb, cb = battle_state(host), battle_state(client)
    ev = {"clientBriefingWithin": dt if got else None, "clientStack": stack(client), "hostStack": stack(host),
          "hostPhase": es(host).get("phase"), "clientPhase": es(client).get("phase"),
          "turn": [hb.get("turn"), cb.get("turn")], "inBattle": [hb.get("inBattle"), cb.get("inBattle")],
          "mapFingerprint": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
          "equip": {"host": equip(host), "client": equip(client)}}
    evidence("EQ1", ev)
    fails = []
    if not got:
        fails.append(f"EQ1: no client BriefingState within {EQ1_WAIT_S} s while the host's is up (client stack "
                     f"{ev['clientStack']}, client inBattle {cb.get('inBattle')}, host phase {ev['hostPhase']}; RED: "
                     f"no offer before the host's OK)")
        finish(fails)
    if not has(host, "BriefingState"):
        fails.append(f"EQ1: the host's BriefingState is gone (host stack {ev['hostStack']})")
    if ev["turn"] != [0, 0]:
        fails.append(f"EQ1: turn host/client {ev['turn']} (want 0 on both)")
    if cb.get("mapFingerprint") != MAP_FP:
        fails.append(f"EQ1: client mapFingerprint {cb.get('mapFingerprint')!r} (want {MAP_FP!r})")
    fails += tail_fails(host, client, "EQ1")
    finish(fails)


def spine_stage_early(host, client, ctx):
    """Staging as soon as both machines hold the battle: here (after EQ1) when the client already does."""
    if in_battle(client) and in_battle(host):
        stage(host, client, ctx, "after EQ1 (both machines hold the battle)")
    else:
        print(f"STAGE deferred: the client holds no battle yet (client stack {stack(client)})", flush=True)


def eq2_client_first(host, client, ctx):
    pre = in_battle(client) and has(client, "BriefingState")
    ev = {"pre": {"clientInBattle": in_battle(client), "clientStack": stack(client), "hostStack": stack(host)}}
    if not pre:
        evidence("EQ2", ev)
        finish([f"EQ2: precondition absent - the client has no battle / no BriefingState (client stack "
                f"{ev['pre']['clientStack']}; RED: no client battle before the host's OK)"])
    ctx["baseline"] = {"hostCovered": es(host).get("hostCovered"),
                       "hostScreensCloses": (es(host).get("hostScreens") or {}).get("closes"),
                       "invForcedCloses": es(client).get("invForcedCloses")}
    r = client.cmd({"cmd": "close_briefing"})
    ev["close"] = {k: r.get(k) for k in ("ok", "error")}
    got, dt = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    v = inv_view(client)
    hp = pile_ids(items_by_id(host))
    eh = equip(host)
    ec2 = equip(client)
    ev.update({"entryWithin": dt if got else None, "clientStack": stack(client), "view": view_brief(v),
               "clientGround": ground_ids(v), "hostPile": hp, "clientEquipPile": ec2.get("pile"),
               "hostEquipPile": eh.get("pile"), "hostStack": stack(host), "turn": [turn(host), turn(client)],
               "equip": {"host": eh, "client": ec2},
               "clientBanner": battle_state(client).get("coopWaitText"), "baseline": ctx["baseline"]})
    evidence("EQ2", ev)
    fails = []
    if not got:
        fails.append(f"EQ2: the client's top is {top(client)!r} {ENTRY_WAIT_S} s after its briefing closed (want "
                     f"its pre-battle InventoryState; banner {ev['clientBanner']!r})")
    if v.get("preBattle") is not True:
        fails.append(f"EQ2: client inventory_view.preBattle={v.get('preBattle')} (want true)")
    if v.get("unitId") not in C_IDS:
        fails.append(f"EQ2: client inventory_view.unitId={v.get('unitId')} (want one of C {C_IDS})")
    if ground_ids(v) != hp:
        fails.append(f"EQ2: client ground ids {ground_ids(v)} != the host's battle_items on {PILE} {hp}")
    if ec2.get("pile") != list(PILE):
        fails.append(f"EQ2: client equip.pile={ec2.get('pile')} (want {list(PILE)}: the offer's pile)")
    if top(host) != "BriefingState":
        fails.append(f"EQ2: host stack {ev['hostStack']} (want its briefing still on top)")
    fails += staged_fails(ctx, "EQ2")
    fails += tail_fails(host, client, "EQ2")
    finish(fails)


def eq3b_rename_in_window(host, client, ctx):
    ev = {}
    fails = pre_screen_fails(host, client, "EQ3b")
    if fails:
        ev["pre"] = {"clientStack": stack(client), "hostStack": stack(host)}
        evidence("EQ3b", ev)
        finish([f.replace("EQ3b: ", "EQ3b: precondition absent - ") for f in fails])
    rh0 = (es(host).get("renames") or {}).get("applied")
    base = (session.units_by_id(battle_state(client)).get(C2) or {}).get("name") or ""
    want = base + RENAME_LETTER[0]
    nav = []
    reached = goto_unit(client, C2, C_IDS, nav)
    ev["toC2"] = {"reached": reached, "presses": nav}
    ready_field = False
    if reached:
        time.sleep(KEY_SETTLE_S)
        lw = client.cmd({"cmd": "list_widgets"})
        ev["nameField"] = [[w.get("x"), w.get("y"), w.get("w"), w.get("h")] for w in lw.get("widgets", [])
                           if "TextEdit" in str(w.get("type")) and w.get("visible")]
        if list(NAME_FIELD_RECT) in ev["nameField"]:
            c = client.cmd({"cmd": "inject_input", "kind": "click", "x": NAME_CLICK[0], "y": NAME_CLICK[1]})
            ev["fieldClick"] = {k: c.get(k) for k in ("ok", "error")}
            time.sleep(KEY_SETTLE_S)
            k = client.cmd({"cmd": "inject_input", "kind": "key", "key": RENAME_LETTER[1]})
            ev["key"] = {"letter": RENAME_LETTER[0], "ok": k.get("ok")}
            ready_field = bool(c.get("ok")) and bool(k.get("ok"))
            time.sleep(KEY_SETTLE_S)
            u = client.cmd({"cmd": "inject_input", "kind": "click", "x": UNFOCUS_CLICK[0], "y": UNFOCUS_CLICK[1]})
            ev["unfocus"] = {k2: u.get(k2) for k2 in ("ok", "error")}
            time.sleep(KEY_SETTLE_S)

    def names_equal():
        uh = session.units_by_id(battle_state(host)).get(C2) or {}
        uc = session.units_by_id(battle_state(client)).get(C2) or {}
        return all(uh.get(k2) == want and uc.get(k2) == want for k2 in ("name", "_name", "rawName"))

    got, dt = wait_until(names_equal, NAME_SYNC_S, 0.1) if ready_field else (None, None)
    back = []
    ev["backToC1"] = {"reached": goto_unit(client, C1, C_IDS, back) if reached else None, "presses": back}
    uh = session.units_by_id(battle_state(host)).get(C2) or {}
    uc = session.units_by_id(battle_state(client)).get(C2) or {}
    rh1 = (es(host).get("renames") or {}).get("applied")
    ev.update({"want": want, "namesWithin": dt, "hostNames": {k2: uh.get(k2) for k2 in ("name", "_name", "rawName")},
               "clientNames": {k2: uc.get(k2) for k2 in ("name", "_name", "rawName")},
               "hostRenamesApplied": [rh0, rh1], "hostAlive": alive(host), "hostStack": stack(host),
               "turn": [turn(host), turn(client)]})
    evidence("EQ3b", ev)
    fails = []
    if not reached:
        fails.append(f"EQ3b: NEXT never reached C2 ({nav})")
    elif not ready_field:
        fails.append(f"EQ3b: the name field was not reached (visible TextEdits {ev.get('nameField')}, want "
                     f"{list(NAME_FIELD_RECT)}; click {ev.get('fieldClick')}; key {ev.get('key')})")
    if not ev["hostAlive"]:
        fails.append("EQ3b: the host died (F2744: onIntent's `bg` read with no BattlescapeState)")
        finish(fails)
    if not got:
        fails.append(f"EQ3b: C2's names host={ev['hostNames']} client={ev['clientNames']} (want name, _name and "
                     f"rawName {want!r} on both within {NAME_SYNC_S} s)")
    if not (isinstance(rh0, int) and isinstance(rh1, int) and rh1 - rh0 == 1):
        fails.append(f"EQ3b: host renames.applied {rh0} -> {rh1} (want +1)")
    if ev["turn"] != [0, 0]:
        fails.append(f"EQ3b: turn host/client {ev['turn']} (want 0 on both)")
    if top(host) != "BriefingState":
        fails.append(f"EQ3b: host stack {ev['hostStack']} (want its briefing still on top: the window)")
    if not ev["backToC1"]["reached"]:
        fails.append(f"EQ3b: PREV/NEXT never returned to C1 ({back})")
    fails += tail_fails(host, client, "EQ3b")
    finish(fails)


def eq3_hold(host, client, ctx):
    """EQ3's first half (no PASS/FAIL line of its own): the held order. Records ctx['eq3']."""
    rec = {}
    ctx["eq3"] = rec
    pre = pre_screen_fails(host, client, "EQ3") + staged_fails(ctx, "EQ3")
    if not pre and inv_view(client).get("unitId") != C1:
        pre.append(f"EQ3: the client's screen shows {inv_view(client).get('unitId')} (want C1 {C1})")
    if not pre and top(host) != "BriefingState":
        pre.append(f"EQ3: the host's briefing is gone (host stack {stack(host)})")
    if pre:
        rec["pre"] = pre
        print(f"EQ3 hold: precondition absent: {pre}", flush=True)
        return
    ec0, eh0 = es(client), es(host)
    rec["before"] = {"invWarningWrites": ec0.get("invWarningWrites"), "invLastWarning": ec0.get("invLastWarning"),
                     "heldUntilOpen": (eh0.get("equip") or {}).get("heldUntilOpen")}
    clip = staged_id(ctx, "STR_RIFLE_CLIP")
    rec["pick"] = {}
    item = pick_ground(client, clip, rec["pick"])
    rec["item"] = item
    if item is None:
        rec["pre"] = [f"EQ3: the staged clip {clip} was not picked: {rec['pick']}"]
        return
    rec["drop"] = click(client, slot=BELT, x=0, y=0)
    rec["tDrop"] = time.time()

    def held():
        ec, eh = es(client), es(host)
        return ((ec.get("invWarningWrites") or 0) > (rec["before"]["invWarningWrites"] or 0)
                and (eh.get("equip") or {}).get("heldUntilOpen", 0) >= 1)

    got, dt = wait_until(held, ANSWER_WAIT_S)
    ec, eh = es(client), es(host)
    rec["hold"] = {"within": dt if got else None, "invWarningWrites": ec.get("invWarningWrites"),
                   "invLastWarning": ec.get("invLastWarning"),
                   "heldUntilOpen": (eh.get("equip") or {}).get("heldUntilOpen"),
                   "pending": battle_state(client).get("coopPendingIntent"), "lastDeny": ec.get("lastDeny"),
                   "cursor": inv_view(client).get("selectedItem"), "hostAlive": alive(host),
                   "hostStack": stack(host), "turn": [turn(host), turn(client)]}
    print(f"EQ3 hold: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)


def eq9_end_turn_in_window(host, client, ctx):
    hold = ctx.get("eq3") or {}
    ev = {"eq3Hold": hold.get("hold"), "eq3Pre": hold.get("pre")}
    if hold.get("pre") or not hold.get("hold"):
        evidence("EQ9", ev)
        finish([f"EQ9: precondition absent - no EQ3 hold ({hold.get('pre')})"])
    before = (equip(host)).get("endTurnIgnored")
    counter = es(client).get("coopEndTurnPhaseCounter")
    r = client.cmd({"cmd": "battle_end_turn_ready", "turn": counter if isinstance(counter, int) else 0,
                    "ready": True})
    ev["send"] = {"ok": r.get("ok"), "error": r.get("error"), "turnArg": counter}
    got, dt = wait_until(lambda: alive(host) and (equip(host).get("endTurnIgnored") or 0) > (before or 0),
                         ANSWER_WAIT_S)
    ev["hostAlive"] = alive(host)
    after = equip(host).get("endTurnIgnored") if ev["hostAlive"] else None
    ev.update({"endTurnIgnored": [before, after], "within": dt if got else None, "hostStack": stack(host),
               "turn": [turn(host), turn(client)] if ev["hostAlive"] else None})
    evidence("EQ9", ev)
    fails = []
    if not ev["hostAlive"]:
        fails.append("EQ9: the host died after the client's END TURN in the window (tryCommit's unguarded reads)")
        finish(fails)
    if after != 1:
        fails.append(f"EQ9: host equip.endTurnIgnored {before} -> {after} (want 1)")
    if ev["turn"] != [0, 0]:
        fails.append(f"EQ9: turn host/client {ev['turn']} (want 0 on both)")
    if top(host) != "BriefingState":
        fails.append(f"EQ9: host stack {ev['hostStack']} (want its briefing still on top)")
    fails += tail_fails(host, client, "EQ9")
    finish(fails)


def spine_host_close(host, client, ctx):
    """The spine: the host closes its briefing; a client BriefingState still up is closed (red only has one);
    staging if not done yet. Records the host's turn right after its OK (EQ8's RED evidence)."""
    rec = {}
    ctx["spine"] = rec
    r = host.cmd({"cmd": "close_briefing"})
    rec["close"] = {k: r.get(k) for k in ("ok", "error")}
    got, dt = wait_until(lambda: not has(host, "BriefingState"), 10.0)
    rec["hostBriefingGoneWithin"] = dt if got else None
    rec["hostTurnAfterOk"] = turn(host)
    rec["hostStackAfterOk"] = stack(host)
    rec["hostEquipAfterOk"] = equip(host)
    got, dt = wait_until(lambda: in_battle(client), CLIENT_BATTLE_WAIT_S, 0.2)
    rec["clientBattleWithin"] = dt if got else None
    if got and has(client, "BriefingState"):
        wait_until(lambda: top(client) == "BriefingState", 10.0)
        c = client.cmd({"cmd": "close_briefing"})
        g2, d2 = wait_until(lambda: not has(client, "BriefingState"), 10.0)
        rec["clientBriefingClosed"] = {"ok": c.get("ok"), "error": c.get("error"), "gone": bool(g2), "within": d2}
    rec["clientStack"] = stack(client)
    rec["turn"] = [turn(host), turn(client)]
    print(f"SPINE host close_briefing: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not ctx.get("staged") and in_battle(client):
        stage(host, client, ctx, "after the host's briefing OK (the client held no battle before)")
    if not got:
        raise AssertionError(f"spine: the client never held the battle within {CLIENT_BATTLE_WAIT_S} s "
                             f"(client stack {stack(client)})")


def eq3_lands(host, client, ctx):
    rec = ctx.get("eq3") or {}
    ev = {"hold": rec.get("hold"), "pre": rec.get("pre"), "pick": rec.get("pick"), "drop": rec.get("drop")}
    if rec.get("pre") or not rec.get("hold"):
        evidence("EQ3", ev)
        finish([f"EQ3: precondition absent - {rec.get('pre')}"])
    fails = []
    h = rec["hold"]
    if h["within"] is None:
        fails.append(f"EQ3: no held deny within {ANSWER_WAIT_S} s of the drop (client invWarningWrites "
                     f"{rec['before']['invWarningWrites']} -> {h['invWarningWrites']}, host heldUntilOpen "
                     f"{h['heldUntilOpen']})")
    if h["invLastWarning"] != TEXT_BUSY:
        fails.append(f"EQ3: the client's line during the hold {h['invLastWarning']!r} (want {TEXT_BUSY!r})")
    if (h["invWarningWrites"] or 0) - (rec["before"]["invWarningWrites"] or 0) != 1:
        fails.append(f"EQ3: client invWarningWrites {rec['before']['invWarningWrites']} -> {h['invWarningWrites']} "
                     f"(want +1)")
    if h["heldUntilOpen"] != 1:
        fails.append(f"EQ3: host equip.heldUntilOpen={h['heldUntilOpen']} during the hold (want 1)")
    if not h["hostAlive"]:
        fails.append("EQ3: the host died during the hold")
        evidence("EQ3", ev)
        finish(fails)
    item = rec["item"]
    got, dt = wait_until(lambda: top(host) == "InventoryState", 5.0)
    hv = inv_view(host)
    ev["hostScreen"] = {"within": dt if got else None, "view": view_brief(hv), "stack": stack(host)}

    def landed():
        a, b = item_view(items_by_id(host), item), item_view(items_by_id(client), item)
        want = {"owner": C1, "slot": BELT, "slotX": 0, "slotY": 0}
        return all(a and b and a.get(k) == v and b.get(k) == v for k, v in want.items())

    got2, dt2 = wait_until(landed, LAND_WAIT_S, 0.1)
    ih, ic = items_by_id(host), items_by_id(client)
    ev.update({"item": item, "landedWithin": dt2 if got2 else None,
               "itemHost": item_view(ih, item), "itemClient": item_view(ic, item),
               "clientCursor": inv_view(client).get("selectedItem"),
               "clientPending": battle_state(client).get("coopPendingIntent"),
               "heldUntilOpenAfter": equip(host).get("heldUntilOpen"), "turn": [turn(host), turn(client)]})
    evidence("EQ3", ev)
    if hv.get("unitId") not in H_IDS:
        fails.append(f"EQ3: after the host's briefing OK its screen shows {hv.get('unitId')} (want one of H {H_IDS}; "
                     f"host stack {ev['hostScreen']['stack']})")
    if not got2:
        fails.append(f"EQ3: the held clip {item} host={ev['itemHost']} client={ev['itemClient']} (want owner C1 {C1}, "
                     f"{BELT} (0,0) on both within {LAND_WAIT_S} s of the host's OK)")
    if ev["clientCursor"] != -1:
        fails.append(f"EQ3: client selectedItem={ev['clientCursor']} after the landing (want -1)")
    fails += tail_fails(host, client, "EQ3")
    finish(fails)


def eq4_own_units(host, client, ctx):
    ev = {}
    fails = pre_screen_fails(host, client, "EQ4", host_too=True)
    if fails:
        ev["pre"] = {"clientStack": stack(client), "hostStack": stack(host),
                     "clientBanner": battle_state(client).get("coopWaitText")}
        evidence("EQ4", ev)
        finish(fails)
    for gc, own in ((host, H_IDS), (client, C_IDS)):
        start = inv_view(gc).get("unitId")
        presses = []
        for _ in range(len(own)):
            next_press(gc, presses)
        seen = [start] + [p["to"] for p in presses]
        ev[gc.name] = {"start": start, "presses": presses, "seen": seen}
    evidence("EQ4", ev)
    for gc, own in ((host, H_IDS), (client, C_IDS)):
        seen = ev[gc.name]["seen"]
        if set(seen) != set(own):
            fails.append(f"EQ4: {gc.name} NEXT x{len(own)} visited {seen} (want exactly its own set {own})")
    fails += tail_fails(host, client, "EQ4")
    finish(fails)


def eq5_ready_toggle(host, client, ctx):
    ev = {"presses": []}
    fails = pre_screen_fails(host, client, "EQ5")
    if fails:
        evidence("EQ5", ev)
        finish(fails)
    for n in (1, 2, 3):
        want = (n % 2 == 1)
        t = time.time()
        c = ok_press(client)
        got, dt = wait_until(lambda: (equip(host).get("ready") or [None, None])[1] is want, ANSWER_WAIT_S)
        rest = LINE_READ_S - (time.time() - t)
        if rest > 0:
            time.sleep(rest)
        v = inv_view(client)
        p = {"n": n, "want": want, "click": c.get("error") or c.get("ok"), "hostReadyWithin": dt if got else None,
             "hostReady": equip(host).get("ready"), "clientReady": equip(client).get("ready"),
             "view": view_brief(v), "clientTop": top(client), "turn": [turn(host), turn(client)],
             "readAtS": round(time.time() - t, 3)}
        ev["presses"].append(p)
    evidence("EQ5", ev)
    for p in ev["presses"]:
        n, want, v = p["n"], p["want"], p["view"]
        if (p["hostReady"] or [None, None])[1] is not want:
            fails.append(f"EQ5 press {n}: host equip.ready[1]={(p['hostReady'] or [None, None])[1]} (want {want})")
        if v.get("okPressed") is not want:
            fails.append(f"EQ5 press {n}: client okPressed={v.get('okPressed')} (want {want})")
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"EQ5 press {n}: the client's pre-battle screen is not on top (view {v}, top {p['clientTop']})")
        if p["turn"] != [0, 0]:
            fails.append(f"EQ5 press {n}: turn host/client {p['turn']} (want 0 on both)")
        if want and not (v.get("lineText") == TEXT_WAIT_HOST and v.get("lineVisible") is True):
            fails.append(f"EQ5 press {n}: the client's line at +{LINE_READ_S} s {v.get('lineText')!r} visible="
                         f"{v.get('lineVisible')} (want {TEXT_WAIT_HOST!r} visible)")
        if not want and v.get("lineVisible") is not False:
            fails.append(f"EQ5 press {n}: the client's line at +{LINE_READ_S} s visible={v.get('lineVisible')} "
                         f"({v.get('lineText')!r}; want not visible)")
    fails += tail_fails(host, client, "EQ5")
    finish(fails)


def client_move(host, client, ctx, stype, uid, slot, x, y, ev):
    """The client moves staged `stype` from the pile onto `uid`'s slot (x, y). Returns (item, landed)."""
    nav = []
    ev["toUnit"] = {"reached": goto_unit(client, uid, C_IDS, nav), "presses": nav}
    if not ev["toUnit"]["reached"]:
        return None, False
    ev["pick"] = {}
    item = pick_ground(client, staged_id(ctx, stype), ev["pick"])
    if item is None:
        return None, False
    ev["drop"] = click(client, slot=slot, x=x, y=y)
    want = {"owner": uid, "slot": slot}
    if slot == BELT:
        want.update({"slotX": x, "slotY": y})

    def landed():
        a, b = item_view(items_by_id(host), item), item_view(items_by_id(client), item)
        return all(a and b and a.get(k) == v and b.get(k) == v for k, v in want.items())

    got, dt = wait_until(landed, LAND_WAIT_S, 0.1)
    ev["want"] = want
    ev["landedWithin"] = dt if got else None
    return item, bool(got)


def eq6_edit_after_ready(host, client, ctx):
    ev = {}
    fails = pre_screen_fails(host, client, "EQ6") + staged_fails(ctx, "EQ6")
    if fails:
        evidence("EQ6", ev)
        finish(fails)
    ev["readyBefore"] = {"host": equip(host).get("ready"), "clientOkPressed": inv_view(client).get("okPressed")}
    item, landed = client_move(host, client, ctx, "STR_GRENADE", C2, BELT, 0, 0, ev)
    t = time.time()
    got, dt = wait_until(lambda: inv_view(client).get("lineText") == TEXT_WAIT_HOST
                         and inv_view(client).get("lineVisible") is True, LINE_READ_S)
    v = inv_view(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ev.update({"item": item, "itemHost": item_view(ih, item), "itemClient": item_view(ic, item),
               "lineBackWithin": dt if got else None, "view": view_brief(v),
               "hostReady": equip(host).get("ready"), "turn": [turn(host), turn(client)],
               "sinceLand": round(time.time() - t, 3)})
    evidence("EQ6", ev)
    if item is None:
        fails.append(f"EQ6: the staged grenade was not picked for C2 (nav {ev.get('toUnit')}, pick {ev.get('pick')})")
    elif not landed:
        fails.append(f"EQ6: the grenade {item} host={ev['itemHost']} client={ev['itemClient']} (want owner C2 {C2}, "
                     f"{BELT} (0,0) on both within {LAND_WAIT_S} s)")
    if (ev["hostReady"] or [None, None])[1] is not True or v.get("okPressed") is not True:
        fails.append(f"EQ6: ready after the edit: host equip.ready[1]={(ev['hostReady'] or [None, None])[1]} client "
                     f"okPressed={v.get('okPressed')} (want still ready on both)")
    if not got:
        fails.append(f"EQ6: the client's line {v.get('lineText')!r} visible={v.get('lineVisible')} (want "
                     f"{TEXT_WAIT_HOST!r} back within {LINE_READ_S} s of the landing)")
    if ev["turn"] != [0, 0]:
        fails.append(f"EQ6: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, "EQ6")
    finish(fails)


def eq15_host_refresh(host, client, ctx):
    ev = {}
    fails = pre_screen_fails(host, client, "EQ15", host_too=True) + staged_fails(ctx, "EQ15")
    if fails:
        evidence("EQ15", ev)
        finish(fails)
    hv0 = inv_view(host)
    ref0 = (es(host).get("hostScreens") or {}).get("refreshes")
    ev["hostBefore"] = {"view": view_brief(hv0), "ground": ground_ids(hv0), "refreshes": ref0}
    unit = inv_view(client).get("unitId")
    item, landed = client_move(host, client, ctx, "STR_RIFLE", unit if unit in C_IDS else C2, RIGHT_HAND, 0, 0, ev)

    def refreshed():
        v = inv_view(host)
        r = (es(host).get("hostScreens") or {}).get("refreshes")
        return item is not None and item not in ground_ids(v) and isinstance(r, int) and isinstance(ref0, int) \
            and r > ref0

    got, dt = wait_until(refreshed, ANSWER_WAIT_S) if landed else (None, None)
    hv1 = inv_view(host)
    ref1 = (es(host).get("hostScreens") or {}).get("refreshes")
    ih, ic = items_by_id(host), items_by_id(client)
    ev.update({"item": item, "itemHost": item_view(ih, item), "itemClient": item_view(ic, item),
               "hostAfter": {"view": view_brief(hv1), "ground": ground_ids(hv1), "refreshes": ref1},
               "refreshWithin": dt if got else None, "turn": [turn(host), turn(client)]})
    evidence("EQ15", ev)
    if item is None:
        fails.append(f"EQ15: the staged rifle was not picked (nav {ev.get('toUnit')}, pick {ev.get('pick')})")
    elif not landed:
        fails.append(f"EQ15: the rifle {item} host={ev['itemHost']} client={ev['itemClient']} (want in the client "
                     f"unit's {RIGHT_HAND} on both within {LAND_WAIT_S} s)")
    else:
        if item in ground_ids(hv1) or ground_ids(hv1) == ground_ids(hv0):
            fails.append(f"EQ15: the host's ground {ground_ids(hv0)} -> {ground_ids(hv1)} (want the rifle {item} gone "
                         f"with no host input)")
        # coopHostScreenCheck's M4 counts one refresh per pump pass after which the host emitted (the order's
        # bt_action_end, plus e.g. F2093's `reveal`), so one client order is >= +1 (test_w2_host_screens.py HS4's bar)
        if not (isinstance(ref0, int) and isinstance(ref1, int) and ref1 - ref0 >= 1):
            fails.append(f"EQ15: host hostScreens.refreshes {ref0} -> {ref1} (want +1 or more: the refresh ran)")
    fails += tail_fails(host, client, "EQ15")
    finish(fails)


# ===================== S-B: TU-free placements, quick-swap, unload, the host's cursor item =====================


def stage_sb(host, client, ctx):
    """S-B's staging, right after S-A's (both machines hold the battle, both briefings up; client first, F607):
    C1 gets a rifle loaded with a clip in STR_BACK_PACK (0,0), then SB_PILE_DROPS on PILE. Records ctx['sb']."""
    rec = {}
    ctx["sb"] = rec
    if not ((ctx.get("staged") or {}).get("ids")):
        rec["error"] = "S-A's staging did not run (the client held no battle after EQ1)"
        print(f"STAGE S-B skipped: {rec['error']}", flush=True)
        return
    try:
        r = both(host, client, {"cmd": "battle_give", "unit": C1, "item": RIFLE_T, "slot": BACK_PACK, "slotX": 0,
                                "slotY": 0, "ammo": CLIP_T}, ("weaponId", "ammoId", "weaponSlot"))
        rec["rifle"], rec["rifleAmmo"] = r["weaponId"], r["ammoId"]
        drops = []
        for t in SB_PILE_DROPS:
            d = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                     ("ids",))
            drops.append([t, d["ids"][0]])
        rec["drops"] = drops
        rec["diff"] = diff_buckets(host, client)
        rec["turn"] = [turn(host), turn(client)]
    except Exception as e:
        rec["error"] = short(e, 400)
    print(f"STAGE S-B {json.dumps(rec, sort_keys=True, default=str)}", flush=True)


def sb_staged_fails(ctx, what):
    s = ctx.get("sb")
    if not s:
        return [f"{what}: S-B's staging never ran"]
    if s.get("error"):
        return [f"{what}: S-B's staging failed: {s['error']}"]
    if s.get("diff"):
        return [f"{what}: buckets differ after S-B's staging: {s['diff']}"]
    return []


def tu_of(gc, uid):
    return (session.units_by_id(battle_state(gc)).get(uid) or {}).get("tu")


def tus(host, client, uid):
    return [tu_of(host, uid), tu_of(client, uid)]


def first_of_type(gc, t):
    """The id vanilla's pick returns at the ground cell of item type `t` on `gc`'s open screen: the first ground
    entry of that type (inventory_view lists the tile inventory in order; BattleUnit::getItem returns the first item
    at the cell, and one ground cell holds one type's stack). None when the ground holds no `t`."""
    its = items_by_id(gc)
    for g in inv_view(gc).get("ground") or []:
        if (its.get(g["id"]) or {}).get("type") == t:
            return g["id"]
    return None


def ammo_of(it, own):
    """A weapon's loaded ammo ids (F2091: the battle_items `ammo` list holds the weapon's own id in slots it needs
    no ammo for)."""
    return [a for a in ((it or {}).get("ammo") or []) if a != own]


def weapon_view(its, iid):
    it = its.get(iid)
    return dict(item_view(its, iid) or {}, ammo=ammo_of(it, iid)) if it else None


def sb_pre(host, client, ctx, row, host_too=False):
    """S-B's row head: both machines' pre-battle screens (the client's always), both stagings, then the client's
    screen on C1 with an empty cursor. Returns (fails, nav)."""
    fails = pre_screen_fails(host, client, row, host_too=host_too) + staged_fails(ctx, row) + sb_staged_fails(ctx, row)
    nav = []
    if not fails:
        if not goto_unit(client, C1, C_IDS, nav):
            fails.append(f"{row}: PREV/NEXT never reached C1 on the client ({nav})")
        elif inv_view(client).get("selectedItem") != -1:
            fails.append(f"{row}: the client's cursor holds {inv_view(client).get('selectedItem')} (want empty)")
    return fails, nav


def eq10_tu_free_move(host, client, ctx):
    fails, nav = sb_pre(host, client, ctx, "EQ10")
    ev = {"toC1": nav}
    if fails:
        evidence("EQ10", ev)
        finish([f.replace("EQ10: ", "EQ10: precondition absent - ") for f in fails])
    tu0 = tus(host, client, C1)
    clip = first_of_type(client, CLIP_T)
    ev["pick"] = {}
    item = pick_ground(client, clip, ev["pick"]) if clip is not None else None
    want = {"owner": C1, "slot": RIGHT_LEG, "slotX": 0, "slotY": 0}
    got = None
    if item is not None:
        ev["drop"] = click(client, slot=RIGHT_LEG, x=0, y=0)

        def landed():
            a, b = item_view(items_by_id(host), item), item_view(items_by_id(client), item)
            return all(a and b and a.get(k) == v and b.get(k) == v for k, v in want.items())

        got, dt = wait_until(landed, LAND_WAIT_S, 0.1)
        ev["landedWithin"] = dt if got else None
    ih, ic = items_by_id(host), items_by_id(client)
    tu1 = tus(host, client, C1)
    ev.update({"clipOnPile": clip, "item": item, "want": want, "itemHost": item_view(ih, item),
               "itemClient": item_view(ic, item), "c1Tu": [tu0, tu1],
               "clientCursor": inv_view(client).get("selectedItem"),
               "invGuardLast": (es(client).get("invGuard") or {}).get("last"), "turn": [turn(host), turn(client)]})
    evidence("EQ10", ev)
    if clip is None:
        fails.append(f"EQ10: precondition absent - no {CLIP_T} on the client's pile ground")
    elif item is None:
        fails.append(f"EQ10: the pile clip was not picked ({ev['pick']})")
    elif not got:
        fails.append(f"EQ10: the clip {item} host={ev['itemHost']} client={ev['itemClient']} (want {want} on both "
                     f"within {LAND_WAIT_S} s)")
    if tu1 != tu0:
        fails.append(f"EQ10: C1's tu host/client {tu0} -> {tu1} (want unchanged on both: a pre-battle placement "
                     f"costs no TU, D205 a; RED: the battle move cost, ground -> leg {TU_GROUND_TO_LEG}, spent)")
    if ev["clientCursor"] != -1:
        fails.append(f"EQ10: the client's cursor holds {ev['clientCursor']} after the move (want empty)")
    fails += tail_fails(host, client, "EQ10")
    finish(fails)


def eq11_shift_load(host, client, ctx):
    fails, nav = sb_pre(host, client, ctx, "EQ11")
    sb = ctx.get("sb") or {}
    rifle, old = sb.get("rifle"), sb.get("rifleAmmo")
    ev = {"toC1": nav, "rifle": rifle, "oldClip": old}
    if not fails:
        ih, ic = items_by_id(host), items_by_id(client)
        ev["rifleBefore"] = {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)}
        for side in ("host", "client"):
            w = ev["rifleBefore"][side] or {}
            if not (w.get("owner") == C1 and w.get("slot") == BACK_PACK and w.get("ammo") == [old]):
                fails.append(f"EQ11: the {side}'s rifle {rifle} {w} (want C1's, in {BACK_PACK}, loaded with {old})")
    if fails:
        evidence("EQ11", ev)
        finish([f.replace("EQ11: ", "EQ11: precondition absent - ") for f in fails])
    tu0 = tus(host, client, C1)
    deny0 = es(client).get("lastDeny")
    clip = first_of_type(client, CLIP_T)
    ev["pick"] = {}
    new = pick_ground(client, clip, ev["pick"]) if clip is not None else None
    got = None
    if new is not None:
        ev["shiftDrop"] = click(client, slot=BACK_PACK, x=0, y=0, mod="shift")

        def swapped():
            ih2, ic2 = items_by_id(host), items_by_id(client)
            return all(ammo_of(its.get(rifle), rifle) == [new] and on_pile(item_view(its, old)) for its in (ih2, ic2))

        def answered():
            return swapped() or es(client).get("lastDeny") != deny0

        got, dt = wait_until(answered, LAND_WAIT_S, 0.1)
        ev["answeredWithin"] = dt if got else None
        got = swapped()
    ih, ic = items_by_id(host), items_by_id(client)
    tu1 = tus(host, client, C1)
    ev.update({"newClip": new, "rifleAfter": {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)},
               "oldClipAfter": {"host": item_view(ih, old), "client": item_view(ic, old)},
               "newClipAfter": {"host": item_view(ih, new), "client": item_view(ic, new)},
               "lastDeny": [deny0, es(client).get("lastDeny")], "c1Tu": [tu0, tu1],
               "clientCursor": inv_view(client).get("selectedItem"),
               "invGuardLast": (es(client).get("invGuard") or {}).get("last"), "turn": [turn(host), turn(client)]})
    evidence("EQ11", ev)
    if clip is None:
        fails.append(f"EQ11: precondition absent - no {CLIP_T} on the client's pile ground")
    elif new is None:
        fails.append(f"EQ11: the pile clip was not picked ({ev['pick']})")
    elif not got:
        fails.append(f"EQ11: after the Shift-drop of {new} on the loaded rifle {rifle}: rifle ammo host/client "
                     f"{(ev['rifleAfter']['host'] or {}).get('ammo')}/{(ev['rifleAfter']['client'] or {}).get('ammo')}, "
                     f"old clip {old} host={ev['oldClipAfter']['host']} client={ev['oldClipAfter']['client']} (want "
                     f"[{new}] loaded and {old} on the ground at {PILE} on both: vanilla's pre-battle quick-swap; RED: "
                     f"the host refuses it by the battle rules, client lastDeny {ev['lastDeny'][1]})")
    if tu1 != tu0:
        fails.append(f"EQ11: C1's tu host/client {tu0} -> {tu1} (want unchanged on both)")
    if ev["clientCursor"] != -1:
        fails.append(f"EQ11: the client's cursor holds {ev['clientCursor']} after the answer (want empty)")
    fails += tail_fails(host, client, "EQ11")
    finish(fails)


def eq12_unload_widget(host, client, ctx):
    fails, nav = sb_pre(host, client, ctx, "EQ12")
    rifle = (ctx.get("sb") or {}).get("rifle")
    ev = {"toC1": nav, "rifle": rifle}
    loaded = None
    if not fails:
        ih, ic = items_by_id(host), items_by_id(client)
        ev["rifleBefore"] = {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)}
        wh, wc = ev["rifleBefore"]["host"] or {}, ev["rifleBefore"]["client"] or {}
        if not (wh.get("owner") == C1 and wh.get("slot") == BACK_PACK and len(wh.get("ammo") or []) == 1
                and wh == wc):
            fails.append(f"EQ12: the rifle {rifle} host={wh} client={wc} (want C1's, in {BACK_PACK}, loaded, equal on "
                         f"both)")
        else:
            loaded = wh["ammo"][0]
    if fails:
        evidence("EQ12", ev)
        finish([f.replace("EQ12: ", "EQ12: precondition absent - ") for f in fails])
    tu0 = tus(host, client, C1)
    ev["pick"] = click(client, slot=BACK_PACK, x=0, y=0)
    picked, dt = wait_until(lambda: inv_view(client).get("selectedItem") == rifle, CLICK_WAIT_S)
    ev["pickedWithin"] = dt if picked else None
    want = {rifle: {"owner": C1, "slot": RIGHT_HAND}, loaded: {"owner": C1, "slot": LEFT_HAND}}
    got = None
    if picked:
        ev["unload"] = click(client, widget="unload")

        def placed():
            ih2, ic2 = items_by_id(host), items_by_id(client)
            return all(item_view(its, i) and all(item_view(its, i).get(k) == v for k, v in w.items())
                       for its in (ih2, ic2) for i, w in want.items())

        got, dt2 = wait_until(placed, LAND_WAIT_S, 0.1)
        ev["placedWithin"] = dt2 if got else None
    ih, ic = items_by_id(host), items_by_id(client)
    tu1 = tus(host, client, C1)
    ev.update({"clip": loaded, "rifleAfter": {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)},
               "clipAfter": {"host": item_view(ih, loaded), "client": item_view(ic, loaded)}, "c1Tu": [tu0, tu1],
               "clientCursor": inv_view(client).get("selectedItem"), "lastDeny": es(client).get("lastDeny"),
               "invGuardLast": (es(client).get("invGuard") or {}).get("last"), "turn": [turn(host), turn(client)]})
    evidence("EQ12", ev)
    if not picked:
        fails.append(f"EQ12: the client's pick left {inv_view(client).get('selectedItem')} on the cursor (want the "
                     f"rifle {rifle})")
    elif not got:
        fails.append(f"EQ12: after UNLOAD rifle host={ev['rifleAfter']['host']} client={ev['rifleAfter']['client']}, "
                     f"clip {loaded} host={ev['clipAfter']['host']} client={ev['clipAfter']['client']} (want the rifle "
                     f"in {RIGHT_HAND} and the clip in {LEFT_HAND}, C1's, on both within {LAND_WAIT_S} s)")
    if tu1 != tu0:
        fails.append(f"EQ12: C1's tu host/client {tu0} -> {tu1} (want unchanged on both: TU-free, D205 a; RED: the "
                     f"battle unload cost spent)")
    if ev["clientCursor"] != -1:
        fails.append(f"EQ12: the client's cursor holds {ev['clientCursor']} after the unload (want empty)")
    fails += tail_fails(host, client, "EQ12")
    finish(fails)


def eq14_host_cursor_item(host, client, ctx):
    fails, nav = sb_pre(host, client, ctx, "EQ14", host_too=True)
    ev = {"toC1": nav}
    y_host = y_client = None
    if not fails:
        if inv_view(host).get("selectedItem") != -1:
            fails.append(f"EQ14: the host's cursor holds {inv_view(host).get('selectedItem')} (want empty)")
        y_host, y_client = first_of_type(host, GRENADE_T), first_of_type(client, GRENADE_T)
        ev["yFirstAtCell"] = {"host": y_host, "client": y_client}
        if y_host is None or y_host != y_client:
            fails.append(f"EQ14: the first pile {GRENADE_T} host={y_host} client={y_client} (want one id, the same on "
                         f"both machines)")
    if fails:
        evidence("EQ14", ev)
        finish([f.replace("EQ14: ", "EQ14: precondition absent - ") for f in fails])
    y = y_host
    ev["hostPick"], ev["clientPick"] = {}, {}
    hp = pick_ground(host, y, ev["hostPick"])
    cp = pick_ground(client, y, ev["clientPick"]) if hp == y else None
    ec0 = es(client)
    before = {"invWarningWrites": ec0.get("invWarningWrites"), "invLastWarning": ec0.get("invLastWarning"),
              "lastDeny": ec0.get("lastDeny")}
    ev["before"] = before
    answer = None
    if hp == y and cp == y:
        ev["drop"] = click(client, slot=LEFT_LEG, x=0, y=0)

        def answered():
            return (es(client).get("lastDeny") != before["lastDeny"]
                    or (item_view(items_by_id(host), y) or {}).get("owner") == C1)

        got, dt = wait_until(answered, ANSWER_WAIT_S, 0.1)
        ec, ih, ic = es(client), items_by_id(host), items_by_id(client)
        answer = {"within": dt if got else None, "invLastWarning": ec.get("invLastWarning"),
                  "invWarningWrites": ec.get("invWarningWrites"), "lastDeny": ec.get("lastDeny"),
                  "hostCursor": inv_view(host).get("selectedItem"), "clientCursor": inv_view(client).get("selectedItem"),
                  "yHost": item_view(ih, y), "yClient": item_view(ic, y), "hostLine": inv_view(host).get("lineText"),
                  "hostCursorReturned": (es(host).get("hostScreens") or {}).get("cursorReturned")}
    ev["answer"] = answer
    # the host's cursor goes back (vanilla's right-click return; a pick is display only, the item never left the
    # pile). Only with an item on it: a right-click with an empty cursor on the pre-battle screen primes a grenade.
    if inv_view(host).get("selectedItem") != -1:
        ev["hostReturn"] = click(host, slot=GROUND, x=0, y=0, button="right")
        wait_until(lambda: inv_view(host).get("selectedItem") == -1, CLICK_WAIT_S)
    if inv_view(client).get("selectedItem") != -1:
        ev["clientReturn"] = click(client, slot=GROUND, x=0, y=0, button="right")
        wait_until(lambda: inv_view(client).get("selectedItem") == -1, CLICK_WAIT_S)
    ih, ic = items_by_id(host), items_by_id(client)
    ev.update({"y": y, "after": {"hostCursor": inv_view(host).get("selectedItem"),
                                 "clientCursor": inv_view(client).get("selectedItem"),
                                 "yHost": item_view(ih, y), "yClient": item_view(ic, y)},
               "c1Tu": tus(host, client, C1), "turn": [turn(host), turn(client)]})
    evidence("EQ14", ev)
    if hp != y or cp != y:
        fails.append(f"EQ14: the picks put host={hp} client={cp} on the cursors (want Y {y} on both: host "
                     f"{ev['hostPick']}, client {ev['clientPick']})")
    else:
        a = answer
        writes = (a["invWarningWrites"] or 0) - (before["invWarningWrites"] or 0)
        if a["invLastWarning"] != TEXT_ITEM_MISSING or writes != 1:
            fails.append(f"EQ14: the client's line {before['invLastWarning']!r} -> {a['invLastWarning']!r}, "
                         f"invWarningWrites {before['invWarningWrites']} -> {a['invWarningWrites']} (want "
                         f"{TEXT_ITEM_MISSING!r}, +1)")
        if (a["lastDeny"] or {}).get("reason") != "item_missing" or a["lastDeny"] == before["lastDeny"]:
            fails.append(f"EQ14: client lastDeny {before['lastDeny']} -> {a['lastDeny']} (want a new item_missing)")
        if a["hostCursor"] != y:
            fails.append(f"EQ14: the host's cursor holds {a['hostCursor']} at the answer (want Y {y} still on it)")
        if not (on_pile(a["yHost"]) and on_pile(a["yClient"])):
            fails.append(f"EQ14: Y {y} host={a['yHost']} client={a['yClient']} at the answer (want on the pile {PILE} on "
                         f"both; RED: the host executes the order on its cursor item)")
        if a["clientCursor"] != -1:
            fails.append(f"EQ14: the client's cursor holds {a['clientCursor']} after the answer (want empty)")
    if ev["after"]["hostCursor"] != -1:
        fails.append(f"EQ14: the host's cursor holds {ev['after']['hostCursor']} after its right-click (want empty)")
    fails += tail_fails(host, client, "EQ14")
    finish(fails)


def t06_pile_holds(host, client, ctx):
    fails = pre_screen_fails(host, client, "T0-6", host_too=True) + staged_fails(ctx, "T0-6") \
        + sb_staged_fails(ctx, "T0-6")
    ev = {}
    unit = inv_view(host).get("unitId")
    if not fails:
        if unit not in H_IDS:
            fails.append(f"T0-6: the host's screen shows {unit} (want one of H {H_IDS})")
        if inv_view(host).get("selectedItem") != -1:
            fails.append(f"T0-6: the host's cursor holds {inv_view(host).get('selectedItem')} (want empty)")
    q = first_of_type(host, CLIP_T) if not fails else None
    hv0 = inv_view(host)
    cell = cell_of(hv0, q) if q is not None else None
    if not fails and (cell is None or cell[0] is None or cell[0] >= GROUND_COLS):
        fails.append(f"T0-6: no {CLIP_T} on the host's first ground page (first {q}, cell {cell})")
    if fails:
        evidence("T0-6", ev)
        finish([f.replace("T0-6: ", "T0-6: precondition absent - ") for f in fails])
    seq0 = [es(host).get("lastSeqEmitted"), es(client).get("lastSeqApplied")]
    ev.update({"unit": unit, "clip": q, "cell": cell, "hostGroundBefore": ground_ids(hv0)})
    ev["ctrlClick"] = click(host, slot=GROUND, x=cell[0], y=cell[1], mod="ctrl")

    def placed():
        a, b = item_view(items_by_id(host), q), item_view(items_by_id(client), q)
        return a and b and a.get("owner") == unit and b.get("owner") == unit

    got, dt = wait_until(placed, LAND_WAIT_S, 0.1)
    wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    ih, ic = items_by_id(host), items_by_id(client)
    hv, cv = inv_view(host), inv_view(client)
    seq1 = [es(host).get("lastSeqEmitted"), es(client).get("lastSeqApplied")]
    ev.update({"placedWithin": dt if got else None, "clipHost": item_view(ih, q), "clipClient": item_view(ic, q),
               "seq": [seq0, seq1], "hostPile": pile_ids(ih), "hostScreenGround": ground_ids(hv),
               "clientGround": ground_ids(cv), "clientView": view_brief(cv), "hostView": view_brief(hv),
               "turn": [turn(host), turn(client)]})
    evidence("T0-6", ev)
    if not got:
        fails.append(f"T0-6: the host's Ctrl-click left clip {q} host={ev['clipHost']} client={ev['clipClient']} (want "
                     f"on the host's soldier {unit} on both within {LAND_WAIT_S} s)")
    if not (isinstance(seq1[1], int) and isinstance(seq0[1], int) and seq1[1] > seq0[1]):
        fails.append(f"T0-6: the client applied no host ev (lastSeqApplied {seq0[1]} -> {seq1[1]})")
    if not (cv.get("open") and cv.get("top") and cv.get("preBattle")):
        fails.append(f"T0-6: the client's pre-battle screen is gone ({view_brief(cv)})")
    if ev["clientGround"] != ev["hostPile"] or ev["clientGround"] != ev["hostScreenGround"]:
        fails.append(f"T0-6: STOP-IF 8 - after the host's placement the client's pre-battle ground {ev['clientGround']} "
                     f"(want = the host's pile ids {ev['hostPile']} = the host screen's ground {ev['hostScreenGround']})")
    if q in ev["clientGround"]:
        fails.append(f"T0-6: the placed clip {q} is still on the client's ground")
    if ev["turn"] != [0, 0]:
        fails.append(f"T0-6: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, "T0-6")
    finish(fails)


def sb_client_back_to_c2(host, client, ctx):
    """The spine after S-B's rows: the client's screen back on C2 (EQ15 left it there; S-A's EQ7 Ctrl-clicks Z for
    the screen's unit)."""
    nav = []
    ok = goto_unit(client, C2, C_IDS, nav)
    print(f"SPINE client back to C2: reached {ok} {nav}", flush=True)
    if not ok:
        raise AssertionError(f"spine: PREV/NEXT never reached C2 on the client ({nav})")


def eq7_barrier(host, client, ctx):
    ev = {}
    fails = pre_screen_fails(host, client, "EQ7", host_too=True) + staged_fails(ctx, "EQ7")
    if fails:
        evidence("EQ7", ev)
        finish(fails)
    # a. client ok (un-ready)
    a = ok_press(client)
    got, dt = wait_until(lambda: (equip(host).get("ready") or [None, None])[1] is False, ANSWER_WAIT_S)
    ev["a"] = {"click": a.get("error") or a.get("ok"), "hostReady": equip(host).get("ready"),
               "within": dt if got else None, "clientOkPressed": inv_view(client).get("okPressed")}
    # b. host ok (ready)
    tb = time.time()
    b = ok_press(host)
    rest = LINE_READ_S - (time.time() - tb)
    if rest > 0:
        time.sleep(rest)
    hv = inv_view(host)
    ev["b"] = {"click": b.get("error") or b.get("ok"), "hostReady": equip(host).get("ready"), "hostView": view_brief(hv),
               "turn": [turn(host), turn(client)], "readAtS": round(time.time() - tb, 3)}
    # c. the host picks X (the staged proximity grenade) from its ground
    ev["c"] = {}
    x_id = pick_ground(host, staged_id(ctx, "STR_PROXIMITY_GRENADE"), ev["c"])
    ev["c"]["X"] = x_id
    ev["c"]["xBefore"] = {"host": item_view(items_by_id(host), x_id), "client": item_view(items_by_id(client), x_id)}
    # d. host defer_intents; the client Ctrl-clicks Z (no cursor)
    ec0 = es(client)
    d_rec = {"lateDeniedBefore": equip(host).get("lateDenied"), "invLastWarningBefore": ec0.get("invLastWarning"),
             "invWarningWritesBefore": ec0.get("invWarningWrites"), "sentBefore": ec0.get("coopIntentsSent")}
    dr = host.cmd({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})
    d_rec["defer"] = {k: dr.get(k) for k in ("ok", "error", "ms", "count")}
    cv = inv_view(client)
    z_staged = staged_id(ctx, "STR_SMOKE_GRENADE")
    z_cell = cell_of(cv, z_staged)
    d_rec["zStaged"] = z_staged
    d_rec["zCell"] = z_cell
    d_rec["zMates"] = mates_at(cv, z_cell) if z_cell else []
    td = time.time()
    if z_cell and z_cell[0] is not None and z_cell[0] < GROUND_COLS and inv_view(client).get("selectedItem") == -1:
        d_rec["ctrlClick"] = click(client, slot=GROUND, x=z_cell[0], y=z_cell[1], mod="ctrl")
        got, dt = wait_until(lambda: (es(client).get("inFlight") or {}).get("kind") == "inv_move", CLICK_WAIT_S)
        d_rec["sentWithin"] = dt if got else None
        d_rec["inFlight"] = es(client).get("inFlight")
    ev["d"] = d_rec
    # e. client ok (ready) -> the barrier
    te = time.time()
    e = ok_press(client)

    def barrier_done():
        return (not has(host, "InventoryState") and not has(client, "InventoryState")
                and equip(host).get("barrierDone") is True)

    got, dt = wait_until(barrier_done, BARRIER_WAIT_S, 0.1)
    ih, ic = items_by_id(host), items_by_id(client)
    ev["e"] = {"click": e.get("error") or e.get("ok"), "barrierWithin": dt if got else None,
               "sinceD": round(te - td, 3), "hostStack": stack(host), "clientStack": stack(client),
               "hostEquip": equip(host), "xAfter": {"host": item_view(ih, x_id), "client": item_view(ic, x_id)},
               "turn": [turn(host), turn(client)]}
    # +3.5 s after d (the cell's read time; bounded at LATE_WAIT_S): the late order
    rest = LATE_READ_S - (time.time() - td)
    if rest > 0:
        time.sleep(rest)
    wait_until(lambda: (equip(host).get("lateDenied") or 0) >= 1, max(0.0, LATE_WAIT_S - (time.time() - td)))
    ec = es(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ev["late"] = {"readAtS": round(time.time() - td, 3), "lateDenied": equip(host).get("lateDenied"),
                  "clientLastDeny": ec.get("lastDeny"), "clientInvLastWarning": ec.get("invLastWarning"),
                  "clientInvWarningWrites": ec.get("invWarningWrites"),
                  "z": {i: {"host": item_view(ih, i), "client": item_view(ic, i)} for i in d_rec["zMates"]}}
    evidence("EQ7", ev)
    if ev["a"]["within"] is None:
        fails.append(f"EQ7 a: host equip.ready[1] {ev['a']['hostReady']} after the client's un-ready press (want false)")
    hb = ev["b"]["hostView"]
    if not (hb.get("lineText") == TEXT_WAIT_CLIENT and hb.get("lineVisible") is True):
        fails.append(f"EQ7 b: the host's line at +{LINE_READ_S} s {hb.get('lineText')!r} visible="
                     f"{hb.get('lineVisible')} (want {TEXT_WAIT_CLIENT!r} visible)")
    if (ev["b"]["hostReady"] or [None])[0] is not True:
        fails.append(f"EQ7 b: host equip.ready[0]={(ev['b']['hostReady'] or [None])[0]} (want true)")
    if x_id is None:
        fails.append(f"EQ7 c: the host did not pick X ({ev['c']})")
    if not d_rec.get("ctrlClick") or d_rec.get("sentWithin") is None:
        fails.append(f"EQ7 d: the client's Ctrl-click on Z was not sent as an inv_move ({d_rec})")
    if ev["e"]["barrierWithin"] is None:
        fails.append(f"EQ7 e: the barrier did not close both screens within {BARRIER_WAIT_S} s (host stack "
                     f"{ev['e']['hostStack']}, client stack {ev['e']['clientStack']}, host barrierDone "
                     f"{ev['e']['hostEquip'].get('barrierDone')})")
    if x_id is not None and not (on_pile(ev["e"]["xAfter"]["host"]) and on_pile(ev["e"]["xAfter"]["client"])):
        fails.append(f"EQ7 e: X {x_id} host={ev['e']['xAfter']['host']} client={ev['e']['xAfter']['client']} (want "
                     f"back on the pile {PILE} on both)")
    if ev["late"]["lateDenied"] != 1:
        fails.append(f"EQ7b: host equip.lateDenied {d_rec['lateDeniedBefore']} -> {ev['late']['lateDenied']} at "
                     f"+{ev['late']['readAtS']} s (want 1 from +{LATE_READ_S} s, bounded at +{LATE_WAIT_S} s)")
    ld = ev["late"]["clientLastDeny"] or {}
    if ld.get("reason") != "invalid_target":
        fails.append(f"EQ7b: client lastDeny {ld} (want reason invalid_target: the silent late deny)")
    if not d_rec["zMates"] or not all(on_pile(z["host"]) and on_pile(z["client"]) for z in ev["late"]["z"].values()):
        fails.append(f"EQ7b: Z's cell {d_rec['zMates']}: {ev['late']['z']} (want every item on the pile on both)")
    if ev["late"]["clientInvLastWarning"] != d_rec["invLastWarningBefore"]:
        fails.append(f"EQ7b: client invLastWarning {d_rec['invLastWarningBefore']!r} -> "
                     f"{ev['late']['clientInvLastWarning']!r} (want unchanged: a silent deny)")
    fails += tail_fails(host, client, "EQ7")
    finish(fails)


def eq8_turn_one(host, client, ctx):
    spine = ctx.get("spine") or {}
    got, dt = wait_until(lambda: turn(host) == 1 and turn(client) == 1, TURN_WAIT_S)
    eh, ec = es(host), es(client)
    qh, qc = eh.get("equip") or {}, ec.get("equip") or {}
    ev = {"turnWithin": dt if got else None, "turn": [turn(host), turn(client)],
          "hostTurnAfterBriefingOk": spine.get("hostTurnAfterOk"), "hostStackAfterBriefingOk":
          spine.get("hostStackAfterOk"), "equip": {"host": qh, "client": qc},
          "clientStack": stack(client), "hostStack": stack(host)}
    fails = []
    if spine.get("hostTurnAfterOk") != 0:
        fails.append(f"EQ8: the host's turn right after its briefing OK = {spine.get('hostTurnAfterOk')} (want 0; RED: "
                     f"the freeze starts turn 1 at the host's briefing OK; host stack then "
                     f"{spine.get('hostStackAfterOk')})")
    if qc.get("entries") != 1:
        fails.append(f"EQ8: client equip.entries={qc.get('entries')} (want 1; RED: the client never on an equip "
                     f"screen)")
    if not got:
        fails.append(f"EQ8: turn host/client {ev['turn']} (want 1 on both within {TURN_WAIT_S} s)")
    if qh.get("endSyncs") != 1 or qc.get("endSyncs") != 1:
        fails.append(f"EQ8: equip.endSyncs host={qh.get('endSyncs')} client={qc.get('endSyncs')} (want one host "
                     f"`sync` with equip.end, applied once)")
    if qh.get("phase") != "ended" or qc.get("phase") != "ended":
        fails.append(f"EQ8: equip.phase host={qh.get('phase')} client={qc.get('phase')} (want ended on both)")
    # the client's Turn-1 screen, then its map after one real key
    ev["clientTopBeforeKey"] = top(client)
    if ev["clientTopBeforeKey"] == "NextTurnState":
        k = client.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN})
        g2, d2 = wait_until(lambda: top(client) == "BattlescapeState", 3.0)
        ev["clientKey"] = {"ok": k.get("ok"), "battlescapeWithin": d2 if g2 else None, "stack": stack(client)}
    else:
        fails.append(f"EQ8: the client's top after the equip end is {ev['clientTopBeforeKey']!r} (want NextTurnState; "
                     f"client stack {stack(client)})")
    if ev.get("clientKey") and ev["clientKey"]["battlescapeWithin"] is None:
        fails.append(f"EQ8: one real key left the client on {ev['clientKey']['stack']} (want BattlescapeState on top)")
    # the host's own Turn-1 screen (recorded)
    ev["hostTopAfterEnd"] = top(host)
    if ev["hostTopAfterEnd"] == "NextTurnState":
        k = host.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN})
        g3, d3 = wait_until(lambda: top(host) == "BattlescapeState", 3.0)
        ev["hostKey"] = {"ok": k.get("ok"), "battlescapeWithin": d3 if g3 else None, "stack": stack(host)}
    # the client's own inventory shows each soldier's own tile (b7's resetUnitTiles), equal to the host's view.
    # C1 (unit 8, the generator's first soldier) stands on the ramp tile that IS the pile (S-A.1 red run: host C1
    # tile = PILE), so its check cannot tell the pile from its own tile; C2 stands elsewhere and carries the proof.
    ev["ownTiles"] = {}
    for uid in (C1, C2):
        if top(client) != "BattlescapeState":
            break
        r = client.cmd({"cmd": "battle_open_inventory", "unit": uid})
        g4, _ = wait_until(lambda: top(client) == "InventoryState", CLICK_WAIT_S)
        v = inv_view(client)
        hu = session.units_by_id(battle_state(host)).get(uid) or {}
        tile = (hu.get("x"), hu.get("y"), hu.get("z"))
        ih = items_by_id(host)
        host_ids = sorted(i for i, it in ih.items() if it.get("onTile")
                          and (it.get("tx"), it.get("ty"), it.get("tz")) == tile)
        rec = {"open": {k2: r.get(k2) for k2 in ("ok", "opened", "error")}, "view": view_brief(v),
               "ground": ground_ids(v), "hostTile": tile, "hostTileIds": host_ids, "onPile": tile == PILE}
        ev["ownTiles"][uid] = rec
        if not (g4 and v.get("unitId") == uid):
            fails.append(f"EQ8: battle_open_inventory {uid} on the client {rec['open']} view {view_brief(v)} (want "
                         f"its inventory open)")
        elif ground_ids(v) != host_ids:
            fails.append(f"EQ8: the client's ground for {uid} {ground_ids(v)} != the host's items on its tile {tile} "
                         f"{host_ids}")
        if has(client, "InventoryState"):
            c = client.cmd({"cmd": "battle_close_inventory"})
            g5, _ = wait_until(lambda: not has(client, "InventoryState"), CLICK_WAIT_S)
            rec["close"] = {"ok": c.get("ok"), "closed": bool(g5)}
    if not (ev["ownTiles"].get(C2) or {}).get("hostTile") or ev["ownTiles"][C2]["onPile"]:
        fails.append(f"EQ8: FIXTURE - C2's own tile {(ev['ownTiles'].get(C2) or {}).get('hostTile')} is not a tile "
                     f"off the pile {PILE} (the own-tile check needs one)")
    base = ctx.get("baseline") or {}
    eh, ec = es(host), es(client)
    ev["probes"] = {"hostCovered": [base.get("hostCovered"), eh.get("hostCovered")],
                    "hostScreensCloses": [base.get("hostScreensCloses"), (eh.get("hostScreens") or {}).get("closes")],
                    "invForcedCloses": [base.get("invForcedCloses"), ec.get("invForcedCloses")],
                    "forceCloseSkips": (ec.get("equip") or {}).get("forceCloseSkips"),
                    "readySyncs": (eh.get("equip") or {}).get("readySyncs")}
    got6, dt6 = wait_until(lambda: battle_state(host).get("selectedId") in H_IDS, 3.0)
    ev["hostSelected"] = {"id": battle_state(host).get("selectedId"), "within": dt6 if got6 else None}
    evidence("EQ8", ev)
    if not base:
        fails.append("EQ8: no EQ2 baseline for hostCovered / hostScreens / invForcedCloses (EQ2 never ran its "
                     "entry)")
    else:
        for k2 in ("hostCovered", "hostScreensCloses", "invForcedCloses"):
            b0, b1 = ev["probes"][k2]
            if b0 != b1:
                fails.append(f"EQ8: {k2} changed across the equip phase: {b0} -> {b1} (want unchanged)")
    if ev["probes"]["forceCloseSkips"] != 0:
        fails.append(f"EQ8: client equip.forceCloseSkips={ev['probes']['forceCloseSkips']} (want 0)")
    if not got6:
        fails.append(f"EQ8: the host's selectedId {ev['hostSelected']['id']} after turn 1 (want one of H {H_IDS}, "
                     f"F3127)")
    fails += tail_fails(host, client, "EQ8")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine (a failure there fails
# the run, and the rows after it fail on their own preconditions).
STEPS = (("EQ1", eq1_both_briefings),
         (None, spine_stage_early),
         (None, stage_sb),
         ("EQ2", eq2_client_first),
         ("EQ3b", eq3b_rename_in_window),
         (None, eq3_hold),
         ("EQ9", eq9_end_turn_in_window),
         (None, spine_host_close),
         ("EQ3", eq3_lands),
         ("EQ4", eq4_own_units),
         ("EQ5", eq5_ready_toggle),
         ("EQ6", eq6_edit_after_ready),
         ("EQ15", eq15_host_refresh),
         ("EQ10", eq10_tu_free_move),
         ("EQ11", eq11_shift_load),
         ("EQ12", eq12_unload_widget),
         ("EQ14", eq14_host_cursor_item),
         ("T0-6", t06_pile_holds),
         (None, sb_client_back_to_c2),
         ("EQ7", eq7_barrier),
         ("EQ8", eq8_turn_one))
ROWS = [n for n, _ in STEPS if n]


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.bring_up_to_briefings(host, client, seated, seat_count=2,
                                  pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hb = battle_state(host)
    assert hb.get("mapFingerprint") == MAP_FP, (
        f"host mapFingerprint {hb.get('mapFingerprint')!r} (baked MAP_FP {MAP_FP!r}, SEED_MAP {SEED_MAP})")
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == C_IDS, f"seated client units {seated_uids} (baked C {C_IDS})"
    h_ids = sorted(u["id"] for u in hb["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids == H_IDS, f"host-seat soldiers {h_ids} (baked H {H_IDS})"
    for gc in (host, client):
        q = event_state(gc).get("equip")
        assert isinstance(q, dict) and "phase" in q and "heldUntilOpen" in q, (
            f"{gc.name} event_state lacks the W2-P8b equip probe: {q!r}")
    print(f"[w2p8b-sa] boot ok: MAP_FP={MAP_FP!r} mission={hb.get('missionType')} seated={seated_uids} H={h_ids} "
          f"host stack={stack(host)} client stack={stack(client)} host equip={event_state(host).get('equip')}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49920, make_user_dir("w2p8b_prebattle_equip_host"))
    client = GameClient("client", 49921, make_user_dir("w2p8b_prebattle_equip_client"))
    results = {}
    spine_ok = True
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in STEPS:
            try:
                fn(host, client, ctx)
                if name:
                    results[name] = True
                    print(f"PASS {name}", flush=True)
            except Exception as e:
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                if name:
                    results[name] = False
                    print(f"FAIL {name}: {kind}{e}", flush=True)
                else:
                    spine_ok = False
                    print(f"SPINE FAIL {fn.__name__}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p8b-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n in ROWS if results.get(n)]
    failed = [n for n in ROWS if not results.get(n)]
    print(f"\ntest_w2_prebattle_equip: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}"
          f"{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (not failed and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
