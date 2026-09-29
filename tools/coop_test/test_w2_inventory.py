"""W2-P8 S-A + S-B - test_w2_inventory.py: the second player opens its own soldier's
inventory in battle and moves, loads and unloads items; the host checks and performs
every placement (spec docs rewrite/prompts/w2p8_inventory.md: owner D130; AMENDMENT
P8-1 (ST1-ST5, OR1-OR3); the W2-P8 PLAN REVIEW section 2 (the assertion map), section
8.2 (this file's pinned text) and section 9 (S-B); AMENDMENT P8-2 (the TASK 0
constants and rulings F2090-F2093, F2097); AMENDMENT P8-3 (the re-pin at 63324d66b)).

Before S-A the second player cannot open the inventory at all: the INVENTORY key
and battle_open_inventory are refused with "Only the host can open the inventory"
and no InventoryState opens (TASK 0 T0-8, F2096). After S-A the screen opens on
the client for a soldier its seat commands. Picking an item up is local (it rides
the cursor only). Every placement is an `inv_move` intent (op move) that the host
admits with vanilla's own checks and performs with vanilla's own effect and time
unit cost, inside an `intent` action context ending in one bt_action_end. The
client writes no hashed state: the Q11 backstop count `invLocalWrites` stays 0 and
the `invGuard` probe names the decision each inventory execution point took
(ST3 (a)).

Rows (ONE boot; each row ONE run, in this order; every row first restages C on its
own T0-1 tile, ST5 (a): tele_both(C, tile, 2), strip_both(C), the row's kit through
client-first lever pairs with the ids read from the replies, C's TU to max):
  IV1   open + look. TAB-select C on the client, the INVENTORY key (keyBattleInventory
        from the client's own options.cfg), then the key again. RED: the client
        banner reads "Only the host can open the inventory" (read within 0.5 s of
        the press, F2097) and no InventoryState opens. GREEN: InventoryState on the
        client only (inventory_view {open, top, unitId C}), nothing sent, every
        bucket EQUAL while it is open and after the second key closes it.
  IV2   pick-up is local. Open (battle_open_inventory C), inventory_click STR_BELT
        (1,0), then a right-click. RED: the open is refused. GREEN: selectedItem =
        the grenade, then -1; nothing sent; EQUAL with the item on the cursor and
        after.
  IV3   C29b, grenade belt (1,0) -> STR_LEFT_HAND with the in-flight window (ST4):
        host defer_intents {ms 2000, count 1} before the drop. Inside the window:
        client inFlight.kind inv_move, selectedItem = the grenade, the grenade still
        STR_BELT (1,0) owner C on both, C's TU unchanged on both, EQUAL; a second
        drop click -> invGuard.last.decision "inflight" and coopIntentsSent.inv_move
        unchanged. After the answer: admitted, grenade STR_LEFT_HAND owner C on
        both, C TU 64 - 4 on both.
  IV4   the ground rifle clip (its client `ground` cell) -> STR_BELT (2,0):
        admitted, clip owner C, off the tile, (2,0) on both; C TU 64 - 12.
  IV5   rifle RH + grenade LH on an empty tile; grenade LH -> ground cell (0,0):
        admitted, grenade on C's tile, owner -1, STR_GROUND, on both; C TU 64 - 2.
  IV11  host denies, move ops (lever, screen open): battle_intent kind inv_move
        with tuBasisOverride 99 -> cost_changed; H's grenade -> item_missing;
        actor H -> not_your_unit; grenade -> belt (0,0) holding the clip ->
        invalid_target (silent: invLastWarning unchanged); set_tu_both(C, 1) and
        belt -> LH basis 4 -> no_tu. Each: lastDeny {iseq, reason}, the exact
        rendered text on invLastWarning, nothing executed. RED: every order "not
        sent" (sendClientIntent drops the unknown kind).
  IV12  local TU refusal: set_tu_both(C, 1); a real drop belt (1,0) -> LH:
        invGuard.last {site drop, op move, decision vanilla_refused}, nothing sent,
        the grenade still on the cursor and in STR_BELT (1,0) on both, TU 1 on
        both; the right-click returns it (selectedItem -1); EQUAL.
  IV13  real-UI host deny (ST4): host defer_intents {ms 2000, count 1}; the client
        drops the grenade belt (1,0) -> LH; inside the window set_tu_both(C, 1);
        the answer is no_tu: selectedItem -1, the grenade STR_BELT (1,0) owner C on
        both, invLastWarning "Not Enough Time Units!", C TU 1 on both.
  RED (commit S-A.1): IV1 on the refusal; IV2-IV5, IV12, IV13 at their open step;
  IV11 on "battle_intent: not sent" (its open step also fails at red and is
  recorded).

S-B rows (section 9; run after IV13; each on its own T0-1 tile with the kit its T0-1b host-vanilla
twin ran on; the expectations are T0-1b's baked host-vanilla outcome, ST2 (a): no
live host twin before S-C1's host sync):
  IV6   C29a load: rifle (empty) RH, rifle clip belt (0,0); pick the clip, drop it on
        the rifle. GREEN: admitted (invGuard.last {site load, op load, decision
        sent}), rifle ammo [clip, r, r, r], the clip owner -1 slot "" off the tile,
        on both (F2091/F2092); C TU 64 - 15; the cursor empty after the answer.
  IV7   Shift-unload: rifle RH loaded, LH free; a Shift+click on the rifle. GREEN:
        admitted (site unload, op unload), the clip in STR_LEFT_HAND owner C, rifle
        ammo [r, r, r], on both; C TU 64 - 8.
  IV8   Ctrl auto-place: rifle RH, a grenade on the tile; a Ctrl+click on the
        grenade's ground cell. GREEN: admitted (site ctrl_fit, op move), the grenade
        in STR_BELT (0,0) owner C, on both; C TU 64 - 12.
  IV9   UNLOAD unprime: rifle RH, a primed grenade (fuse 0) belt (3,0), LH free;
        pick the grenade, the UNLOAD button. GREEN: admitted (site unload, op
        unload), fuse -1 and the grenade in STR_LEFT_HAND owner C, on both; C TU 64
        - 20 (RULING F2090 (a): max(1, floor(base TU x 25 / 100)) + 4 on C's
        run-time base TU, asserted 64); the cursor empty after the answer.
  IV10  paperdoll drop (boot option on): grenade belt (1,0); pick it, click the
        paperdoll. GREEN: admitted (site paperdoll, op move), the grenade on C's
        tile, owner -1, STR_GROUND, on both; C TU 64 - 6; the cursor empty.
  IV11b host denies, load/unload ops (lever, screen open; ST1 (a)): K0 plus a
        grenade in STR_LEFT_HAND and a loaded rifle in STR_BACK_PACK (0,0). The
        pistol clip -> the empty RH rifle: wrong_ammo "Wrong Ammunition for this
        Weapon!"; the belt clip -> the loaded backpack rifle, swap false:
        already_loaded "Weapon is already loaded!"; unload the backpack rifle with
        both hands full: one_hand_empty "At least one hand must be empty!" (vanilla
        counts the unloaded weapon's own hand as free, Inventory.cpp :1365-:1389, so
        the weapon sits outside the hands); unload the empty RH rifle:
        no_ammo_loaded "No Ammunition Loaded!". Each: lastDeny {iseq, reason}, the
        exact text on invLastWarning, nothing executed.
  RED (commit S-B.1, S-A's interim rule, spec (b)11): IV6-IV10 refused on the
  client (invGuard.last {site <the row's>, decision interim}, nothing sent, items
  and TU unchanged on both, every bucket EQUAL); IV11b answered `invalid_target`
  (S-A's host answer to op load / unload, ST1 (a)). IV1-IV5, IV11-IV13 stay green.

S-R rows (W2-P8 S-R, owner D167 = c: an in-battle rename is an order the host applies
and both players see it; AMENDMENT P8-4 section 4.3 (R-1..R-5), the draft
rewrite/prompts/w2p8_sc2_sr_sd_draft.md section 2.6, AMENDMENT P8-4c (the S-R TASK 0
pins and rulings 1-3, F2944-F2952)). RN0 runs FIRST (at battle start); RN1-RN4 run
after IV11b, in this order. Only RN4 stages (typing needs no kit; C and H stay where
the earlier rows left them). The typing recipe (P8-4c T0-R2, F2949):
battle_open_inventory <unit>; 0.3 s; ONE inject_input click at (266, 29) (the name
TextEdit (28,6,210,17) centre x 2); 0.3 s; each letter one inject_input key, 0.3 s
between; the screen closes only through battle_close_inventory (ruling 2, F2951: ESC
or the INVENTORY key with the field focused blanks the name).
  RN0   names at battle start (ruling 1, F2948; before S-R.2 hashes them, R-5):
        battle_state units' `_name` (the unit's own stored name) and `rawName` (its
        geoscape Soldier's raw name, "" without one) on both machines. Every unit's
        `name`, `_name` and `rawName` equal on both, `_name` empty for every
        non-SOLDIER unit, `rawName` empty for every unit without a Soldier. Declared
        GREEN at red (the probes are S-R.1's). A non-empty `_name` on a non-soldier
        is a STOP (ruling 1), never a fixture change.
  RN1   the client renames C: opens C's inventory, clicks the name field, types "xy",
        then End (ruling 3, F2952: a key that changes nothing), closes. RED: client
        coopIntentsSent.rename +0, C's name changed on the client only. GREEN:
        coopIntentsSent.rename +2, client renames.sent +2 and unchanged by End
        (Q3 a), host renames.applied +2, C's name, _name and rawName = the old name
        + "xy" on both, client inFlight null; EQUAL.
  RN2   the host renames H the same way on its own screen. RED: the client's H name
        unchanged. GREEN: host invHostDirty.sets.rename +2, host syncEvsEmitted
        +>= 1, the client's H names = the host's (the old name + "xy") while the
        host's screen is still open; EQUAL.
  RN3   forged rename: client battle_intent {kind rename, actor H, name "x"}. RED:
        not sent (sendClientIntent drops the unknown kind). GREEN: client lastDeny
        {iseq, reason not_your_unit}, H's names unchanged on both, host
        renames.applied +0; EQUAL.
  RN4   a rename never waits (R-M2), in the T0-4 window (test_w2_inventory_held.py
        IH1a's pins: the host's snap shot at fire dial 1; C K0 on (2,33,0)): the
        client clicks C's name field before the fire and types "z" on its first
        `shot` cue. RED: as RN1. GREEN: host renames.applied +1 while the host's
        shot still runs (host busyOwnerSeat != -1 at the apply), host
        syncEvsEmitted +0 over the row and invHostDirty.heldByGate +> 0 (the name
        rode the shot's evs), client coopPendingIntent null at every sample (never
        held), C's names = the old name + "z" on both; EQUAL.
  RED (commit S-R.1): RN1-RN4 fail on their RED cells; RN0, IV1-IV13 and the S-B
  rows pass.

Common asserts, every row (after wait_host_idle): hash_now {full:true} every bucket
EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and host 0;
client invLocalWrites 0; host inventory_view.open false; client invGuard as the row
names it (counts delta and `last`). An ADMITTED placement also: host closedContexts
gains exactly one {origin intent, kind inv_move, actorId C}; that actionId's host evs
are exactly [bt_action_end] and every one of them is in the client's log with the
same seq, kind and actionId; the only other host ev allowed since the drop is one
`reveal` with actionId 0 (F2093); client coopIntentsSent.inv_move +1; host
intentsReceived.inv_move.admitted +1; client lastAftermath {actionId, kind inv_move};
client inFlight null and intentTimeouts unchanged; client selectedItem -1; the moved
item's fields and C's TU equal on both and equal to T0-1b's host-vanilla value. A
REFUSED placement: nothing sent (client coopIntentsSent unchanged, inFlight null,
host lastSeqEmitted and intentsReceived unchanged) and state unchanged on both.

Constants (AMENDMENT P8-2; P8-3 section 3.4: they hold at 63324d66b by code reading):
the row tiles (T0-1, two runs identical, F2086), C's max TU 64 (T0-1), the costs
belt->LH 4, ground clip->belt 12, LH->ground 2, load 15, Shift-unload 8, Ctrl
auto-place 12, paperdoll 6 (T0-1b on H, F2089; slot/item costs, unit-independent),
IV9's unprime 20 on C (F2090), each moved item's outcome (T0-1b, docs
rewrite/w2p8-task0/run2_t0_1_3_1b.log ops 4-8, ids substituted), the texts (en-US). The boot is the roster-pinned terror boot of
test_w2_host_combat.py with `oxceInventoryDropItemOverPaperdoll: true` on both
(section 8.2). Every lever pair goes to the CLIENT first (F607). Item ids are read at
run time from the lever replies, never baked.

Each row prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its
conditions are checked; main() runs every row even after an earlier one failed and
prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that runs
out is recorded in the EVIDENCE line and fails the row. WV-D99 / WV-D100: one run is
the result; no skip path, no second boot. Exit 0 only when every row passes, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_inventory.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_seat_pacing import tab_select
from test_w2_delta_core import diff_buckets, desync_record, short, both, tele_both
from test_w2_delta_items import items_by_id, unit_view
from test_w2_host_combat import bring_up_lobby_roster_pinned, evs_since, ev_tuples
from test_w2_client_items import strip_both
from test_w2_client_shoot import set_tu_both

# ----- bring-up (plan review section 5: the roster-pinned terror boot) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1 (T0a; P8-2 T0-1)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
PORT = "48741"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
OPTS = {"oxceInventoryDropItemOverPaperdoll": True}   # section 8.2: the boot option on both
TU_MAX = 255                      # battle_set_unit_state tu: clamped to the unit's max TU
C_TU_MAX = 64                     # P8-2 T0-1: "Max TU C 64"

# ----- row tiles (P8-2 T0-1, all z 0; ST5 (a): one per row) and H's staging tile -----
ROW_TILE = {"IV1": (0, 33, 0), "IV2": (0, 34, 0), "IV3": (49, 25, 0), "IV4": (1, 33, 0),
            "IV5": (49, 24, 0), "IV11": (3, 32, 0), "IV12": (49, 23, 0), "IV13": (49, 26, 0),
            # S-B (P8-2 T0-1)
            "IV6": (0, 32, 0), "IV7": (1, 32, 0), "IV8": (0, 35, 0), "IV9": (2, 32, 0), "IV10": (48, 25, 0),
            "IV11b": (1, 34, 0),
            # S-R (P8-3b T0-4 window A: "C K0 on STAGE_C (2,33,0)", test_w2_inventory_held.py IH1A_TILE)
            "RN4": (2, 33, 0)}
STAGE_H = (48, 24, 0)             # P8-2 T0-1 STAGE_H
ROW_DIR = 2                       # section 8.2: tele_both(C, <row tile>, 2)

# ----- T0-1b host-vanilla costs on H (P8-2, F2089) -----
TU_BELT_TO_HAND = 4               # op1 belt (1,0) -> LH
TU_GROUND_TO_BELT = 12            # op2 ground rifle clip -> belt (2,0)
TU_HAND_TO_GROUND = 2             # op3 LH -> ground
# S-B (P8-2 T0-1b: "load 15; Shift-unload 8 (clip to LH); unprime + UNLOAD 18 = max(1, floor(58 x 25 / 100))
# 14 + 4 (BattleUnit.cpp:2232); Ctrl auto-place 12 (belt (0,0)); paperdoll drop 6"; run2_t0_1_3_1b.log ops 4-8)
TU_LOAD = 15                      # op4 clip belt (0,0) -> the rifle in RH (IV6)
TU_SHIFT_UNLOAD = 8               # op5 Shift+click the loaded rifle in RH, LH free: the clip -> LH (IV7)
TU_CTRL_FIT = 12                  # op7 Ctrl+click the ground grenade -> belt (0,0) (IV8)
TU_PAPERDOLL = 6                  # op8 grenade belt (1,0) + the paperdoll -> ground (IV10)
UNPRIME_PCT = 25                  # op6: the grenade's unprime cost, a % of the unit's base TU (F2090)
TU_UNPRIME_TO_HAND = 4            # op6: + the move belt (3,0) -> the free LH (F2090)
TU_UNPRIME_C = 20                 # RULING F2090 (a): max(1, floor(64 x 25 / 100)) + 4 on C (IV9)

# ----- the K0 kit (P8-2 T0-1 / plan review section 5) -----
RIFLE, RIFLE_CLIP, PISTOL_CLIP, GRENADE = "STR_RIFLE", "STR_RIFLE_CLIP", "STR_PISTOL_CLIP", "STR_GRENADE"
BELT, LH, RH, GROUND = "STR_BELT", "STR_LEFT_HAND", "STR_RIGHT_HAND", "STR_GROUND"
BACK_PACK = "STR_BACK_PACK"

# ----- texts (bin/common + xcom1 en-US; exact text, never non-emptiness) -----
TEXT_HOST_ONLY = "Only the host can open the inventory"   # STR_COOP_INVENTORY_HOST_ONLY (RED; retired at S-A.2)
TEXT_DENY = {
    "cost_changed": "Order cancelled - cost changed",        # STR_COOP_DENY_COST_CHANGED
    "item_missing": "Order cancelled - item unavailable",    # STR_COOP_DENY_ITEM_MISSING (S-A.2, Q4 a)
    "not_your_unit": "Not one of your soldiers",             # STR_COOP_DENY_NOT_YOUR_UNIT
    "no_tu": "Not Enough Time Units!",                       # xcom1 STR_NOT_ENOUGH_TIME_UNITS
    # S-B (IV11b; the S-A.2 deny rows, Q4 a)
    "wrong_ammo": "Wrong Ammunition for this Weapon!",       # xcom1 STR_WRONG_AMMUNITION_FOR_THIS_WEAPON
    "already_loaded": "Weapon is already loaded!",           # xcom1 STR_WEAPON_IS_ALREADY_LOADED
    "one_hand_empty": "At least one hand must be empty!",    # OXCE STR_ONE_HAND_MUST_BE_EMPTY
    "no_ammo_loaded": "No Ammunition Loaded!",               # xcom1 STR_NO_AMMUNITION_LOADED
}
TU_BASIS_BAD = 99                 # F1956: "tuBasis -1" cannot be sent (-1 = recompute); pinned 99

# ----- S-R (AMENDMENT P8-4 section 4.3; AMENDMENT P8-4c = ledger `## W2-P8 S-R TASK 0`, docs
# rewrite/w2p8-task0/sr/t0_sr.py and run_par.log: "battle_open_inventory {unit}; 0.3 s settle; ONE inject_input
# {kind click, x 266, y 29} (the name TextEdit (28,6,210,17) centre x 2); 0.3 s; keys one per inject_input {kind
# key} with 0.3 s between; close with battle_close_inventory only. Each letter changes the typist's name within
# 0.101 s") -----
NAME_FIELD_RECT = (28, 6, 210, 17)  # InventoryState.cpp :114 `new TextEdit(this, 210, 17, 28, 6)` (list_widgets x,y,w,h)
NAME_CLICK = (266, 29)              # P8-4c T0-R2: the rect's centre x 2 (the harness window is 640x400)
RN_LETTERS = (("x", 120), ("y", 121))   # T0-R2's two letters; the inject_input key = the SDL sym (unicode = sym < 128)
RN4_LETTERS = (("z", 122),)         # draft section 2.6 RN4: one letter
SDLK_END = 279                      # deps/include/SDL/SDL_keysym.h; P8-4c ruling 3 (F2952): End changes no text
RN3_NAME = "x"                      # draft section 2.6 RN3
KEY_SETTLE_S = 0.3                  # F2888 / T0-R2: after the open, after the click, between keys
NAME_CHANGE_S = 2.0                 # T0-R2: 0.101 s per letter on the typist; a bounded record, never a condition
NAME_SYNC_S = 3.0                   # GREEN: the other machine shows the typist's name within this
END_QUIET_S = 1.0                   # ruling 3: End's change handler runs in the key's own frame; sampled 1 s later
RN_KEYS = ("renames", "invHostDirty", "syncEvsEmitted", "syncEvsApplied")
NAME_KEYS = ("name", "_name", "rawName")

# ----- windows and waits -----
DEFER_MS = 2000                   # plan review section 2 IV3 / IV13 (the C23b5 precedent)
POLL_S = 0.05
BANNER_READ_S = 0.5               # F2097: a refusal text is read within 0.5 s of the press
CLICK_WAIT_S = 2.0                # a click's local effect (cursor, screen) shows within this
SENT_WAIT_S = 2.0                 # how long a drop gets to show as sent
ORDER_TIMEOUT_S = 20
ANSWER_TIMEOUT_S = 15

PROBE_KEYS = ("desyncSeen", "coopClientBStatePushes", "coopLocalExecBlocked", "lastSeqEmitted",
              "lastSeqApplied", "queueDepth", "inFlight", "intentTimeouts", "lastDeny", "busyOwnerSeat",
              "coopIntentsSent", "intentsReceived", "lastAftermath", "closedContexts", "invLocalWrites",
              "invLastWarning", "invGuard")
INV_PROBES = ("invLocalWrites", "invLastWarning", "invGuard")
GUARD_KEYS = ("sent", "inflight", "baton", "interim", "vanilla_refused", "host_vanilla")
ITEM_VIEW = ("type", "owner", "slot", "slotX", "slotY", "onTile", "tx", "ty", "tz", "ammo", "fuse")


# ===================== small probes =====================


def stack(gc):
    return session.states_stripped(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def probes(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in PROBE_KEYS}


def banner(gc):
    return battle_state(gc).get("coopWaitText")


def inv_view(gc):
    """inventory_view without the static `slots` table."""
    r = gc.cmd({"cmd": "inventory_view"})
    if not r.get("ok"):
        return {"error": r.get("error"), "open": None}
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "rect", "ground")}


def snap(host, client):
    return {"host": probes(host), "client": probes(client)}


def tu_of(gc, uid):
    return (units(gc).get(uid) or {}).get("tu")


def iview(its, iid):
    it = its.get(iid)
    return {k: it.get(k) for k in ITEM_VIEW if it.get(k) is not None} if it else None


def count_of(d, kind):
    return (d or {}).get(kind) or 0


def recv_of(d, kind, field):
    return ((d or {}).get(kind) or {}).get(field) or 0


def guard_counts(p):
    g = (p.get("invGuard") or {}).get("counts") or {}
    return {k: g.get(k) for k in GUARD_KEYS}


def guard_last(p):
    return (p.get("invGuard") or {}).get("last")


def new_contexts(before, after):
    seen = {c.get("actionId") for c in (before or [])}
    return [c for c in (after or []) if c.get("actionId") not in seen]


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


def read_inventory_key(user_dir):
    """Options::keyBattleInventory as the process wrote it to its own options.cfg at
    startup (test_w2_thin_client_tripwire.read_reload_key's pattern)."""
    with open(os.path.join(user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        m = re.search(r"^\s*keyBattleInventory:\s*(-?\d+)\s*$", f.read(), re.M)
    assert m, f"PREMISE: no keyBattleInventory in {user_dir}/options.cfg"
    return int(m.group(1))


def order_done(host, client):
    """The order is over: the client's slot is empty and nothing is held, the host has
    no action context and no BState, the client has applied everything."""
    ec, eh = event_state(client), event_state(host)
    return (ec.get("inFlight") is None and battle_state(client).get("coopPendingIntent") is None
            and eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0)


# ===================== staging (client first, F607) =====================


def give(host, client, uid, item, slot, sx=0, sy=0):
    return both(host, client, {"cmd": "battle_give", "unit": uid, "item": item, "slot": slot, "slotX": sx,
                               "slotY": sy}, ("weaponId", "ammoId", "weaponSlot"))["weaponId"]


def drop(host, client, tile, item):
    r = both(host, client, {"cmd": "battle_drop", "x": tile[0], "y": tile[1], "z": tile[2], "item": item},
             ("ids",))
    return r["ids"][0]


def give_loaded(host, client, uid, item, slot, ammo, sx=0, sy=0):
    """battle_give with `ammo` loaded into ammo slot 0 (both ids equal on both)."""
    r = both(host, client, {"cmd": "battle_give", "unit": uid, "item": item, "slot": slot, "slotX": sx,
                            "slotY": sy, "ammo": ammo}, ("weaponId", "ammoId", "weaponSlot"))
    return r["weaponId"], r["ammoId"]


def give_primed(host, client, uid, sx, sy):
    r = both(host, client, {"cmd": "battle_give", "unit": uid, "item": GRENADE, "slot": BELT, "slotX": sx,
                            "slotY": sy, "fuse": 0}, ("weaponId",))
    return r["weaponId"]


def restage(host, client, row, kit):
    """ST5 (a): C onto the row's own tile facing 2, stripped, the row's kit, TU max.
    kit "K0": rifle (no ammo) RH, rifle clip belt (0,0), grenade belt (1,0), primed
    grenade belt (3,0) (fuse 0), a rifle clip and a pistol clip dropped on the tile.
    kit "RH_LH": rifle RH, grenade LH (IV5).
    S-B kits = the kit each row's T0-1b host-vanilla twin ran on (t0_1_3_1b.py ops 4-8):
    "IV6" rifle RH + rifle clip belt (0,0); "IV7" rifle RH loaded (clip in ammo slot
    0); "IV8" rifle RH + a grenade on the tile; "IV9" rifle RH + primed grenade belt
    (3,0); "IV10" grenade belt (1,0); "IV11b" K0 + a grenade LH + a loaded rifle
    STR_BACK_PACK (0,0). Returns the staging record with the ids."""
    tile = ROW_TILE[row]
    rec = {"tile": tile}
    t = tele_both(host, client, C_ID, tile, ROW_DIR)
    rec["tele"] = {"to": t.get("to"), "dir": t.get("dir")}
    rec["stripped"] = strip_both(host, client, C_ID)
    ids = {}
    if kit in ("K0", "IV11b"):
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, C_ID, RIFLE_CLIP, BELT, 0, 0)
        ids["grenade"] = give(host, client, C_ID, GRENADE, BELT, 1, 0)
        ids["primed"] = give_primed(host, client, C_ID, 3, 0)
        ids["groundClip"] = drop(host, client, tile, RIFLE_CLIP)
        ids["groundPistolClip"] = drop(host, client, tile, PISTOL_CLIP)
        if kit == "IV11b":
            ids["lhGrenade"] = give(host, client, C_ID, GRENADE, "left")
            ids["bpRifle"], ids["bpClip"] = give_loaded(host, client, C_ID, RIFLE, BACK_PACK, RIFLE_CLIP, 0, 0)
    elif kit == "RH_LH":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["grenade"] = give(host, client, C_ID, GRENADE, "left")
    elif kit == "IV6":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, C_ID, RIFLE_CLIP, BELT, 0, 0)
    elif kit == "IV7":
        ids["rifle"], ids["clip"] = give_loaded(host, client, C_ID, RIFLE, "right", RIFLE_CLIP)
    elif kit == "IV8":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["grenade"] = drop(host, client, tile, GRENADE)
    elif kit == "IV9":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["primed"] = give_primed(host, client, C_ID, 3, 0)
    elif kit == "IV10":
        ids["grenade"] = give(host, client, C_ID, GRENADE, BELT, 1, 0)
    else:
        raise AssertionError(f"unknown kit {kit!r}")
    rec["ids"] = ids
    rec["tu"] = set_tu_both(host, client, C_ID, TU_MAX)
    return rec


def staged_fails(rec, diff):
    fails = []
    if diff:
        fails.append(f"buckets differ after the staging: {diff} (want none)")
    if rec["tu"] != C_TU_MAX:
        fails.append(f"precondition: C's TU after the staging {rec['tu']} (want {C_TU_MAX}, P8-2 T0-1)")
    return fails


# ===================== the client's inventory =====================


def open_client(client, ev):
    """battle_open_inventory C on the client (the REAL btnInventoryClick). Fills `ev`;
    returns True when the screen is open on the client, on C, on top."""
    r = client.cmd({"cmd": "battle_open_inventory", "unit": C_ID})
    ev["open"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    ev["openBanner"] = banner(client)          # F2097: read right after the press
    v = inv_view(client)
    ev["openView"] = {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    ev["openStack"] = stack(client)
    return bool(r.get("opened")) and v.get("open") is True and v.get("top") is True and v.get("unitId") == C_ID


def open_fails(ev, what):
    return [f"{what}: the client's inventory did not open on C at the open step (battle_open_inventory "
            f"{ev.get('open')}, client banner {ev.get('openBanner')!r}, inventory_view {ev.get('openView')}, "
            f"client stack {ev.get('openStack')})"]


def click(client, **kw):
    """inventory_click on the client. Returns the reply's point (or its error)."""
    req = {"cmd": "inventory_click"}
    req.update(kw)
    r = client.cmd(req)
    if kw.get("mod"):
        client.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    if not r.get("ok"):
        return {"req": kw, "error": r.get("error")}
    return {"req": kw, "base": (r.get("baseX"), r.get("baseY")), "win": (r.get("winX"), r.get("winY"))}


def selected(client):
    return inv_view(client).get("selectedItem")


def pick(client, ev, key, slot, x, y, want):
    """Click (slot, x, y) with an empty cursor; waits for `want` on the cursor."""
    ev[key] = click(client, slot=slot, x=x, y=y)
    got, dt = wait_until(lambda: selected(client) == want, CLICK_WAIT_S)
    ev[key]["cursor"] = selected(client)
    ev[key]["waited"] = dt
    return bool(got)


def right_click_return(client, ev, key, slot, x, y):
    """A right-click on the inventory with an item on the cursor returns it."""
    ev[key] = click(client, slot=slot, x=x, y=y, button="right")
    got, dt = wait_until(lambda: selected(client) == -1, CLICK_WAIT_S)
    ev[key]["cursor"] = selected(client)
    ev[key]["waited"] = dt
    return bool(got)


def close_client(client, ev):
    """battle_close_inventory (btnOkClick) with an empty cursor; the screen must go."""
    if not inv_view(client).get("open"):
        ev["close"] = "not open"
        return True
    r = client.cmd({"cmd": "battle_close_inventory"})
    got, dt = wait_until(lambda: "InventoryState" not in stack(client), CLICK_WAIT_S)
    ev["close"] = {"ok": r.get("ok"), "error": r.get("error"), "closed": bool(got), "waited": dt}
    return bool(got)


def wait_sent(host, client, before):
    """Up to SENT_WAIT_S for a drop to show as sent (client inFlight set, client
    coopIntentsSent moved or the host emitted). Returns {state, t, inFlight}."""
    t0 = time.time()
    while time.time() - t0 < SENT_WAIT_S:
        ec = event_state(client)
        if ec.get("inFlight") or ec.get("coopIntentsSent") != before["client"]["coopIntentsSent"]:
            return {"state": "sent", "t": round(time.time() - t0, 3), "inFlight": ec.get("inFlight")}
        if event_state(host).get("lastSeqEmitted") != before["host"]["lastSeqEmitted"]:
            return {"state": "hostEmitted", "t": round(time.time() - t0, 3), "inFlight": ec.get("inFlight")}
        time.sleep(POLL_S)
    return {"state": "quiet", "t": round(time.time() - t0, 3), "inFlight": event_state(client).get("inFlight")}


def wait_order(host, client, notes):
    got, dt = wait_until(lambda: order_done(host, client), ORDER_TIMEOUT_S, 0.1)
    if not got:
        notes.append(f"the order never finished in {ORDER_TIMEOUT_S} s")
    return dt


def ensure_closed(client, notes):
    """Leftovers of an earlier failed row: a cursor item is returned with ONE
    right-click, then the screen is closed. Recorded, never silent."""
    v = inv_view(client)
    if not v.get("open"):
        return None
    rec = {"view": {k: v.get(k) for k in ("top", "unitId", "selectedItem")}}
    if v.get("selectedItem", -1) != -1:
        rec["return"] = click(client, slot=BELT, x=0, y=0, button="right")
        wait_until(lambda: selected(client) == -1, CLICK_WAIT_S)
    r = client.cmd({"cmd": "battle_close_inventory"})
    got, _ = wait_until(lambda: "InventoryState" not in stack(client), CLICK_WAIT_S)
    rec["close"] = {"ok": r.get("ok"), "closed": bool(got)}
    notes.append(f"an earlier row left the client's inventory open: {rec}")
    return rec


# ===================== record + checks =====================


def collect(host, client, seq0):
    rec = {"host": probes(host), "client": probes(client), "hev": evs_since(host, seq0),
           "cev": evs_since(client, seq0), "uh": units(host), "uc": units(client), "ih": items_by_id(host),
           "ic": items_by_id(client), "hview": inv_view(host), "cview": inv_view(client),
           "diff": diff_buckets(host, client)}
    rec["dsc"] = desync_record(client, rec["client"]["desyncSeen"])
    return rec


def rec_view(before, rec, ids):
    """The EVIDENCE fields of one row: both machines."""
    b, a = before, rec
    return {
        "items": {n: {"host": iview(rec["ih"], i), "client": iview(rec["ic"], i)} for n, i in ids.items()},
        "C": {"host": (rec["uh"].get(C_ID) or {}).get("tu"), "client": (rec["uc"].get(C_ID) or {}).get("tu"),
              "hostPos": unit_view(rec["uh"].get(C_ID)), "clientPos": unit_view(rec["uc"].get(C_ID))},
        "sent": (b["client"]["coopIntentsSent"], a["client"]["coopIntentsSent"]),
        "received": (b["host"]["intentsReceived"], a["host"]["intentsReceived"]),
        "hostSeq": (b["host"]["lastSeqEmitted"], a["host"]["lastSeqEmitted"]),
        "inFlight": a["client"]["inFlight"], "lastDeny": a["client"]["lastDeny"],
        "lastAftermath": a["client"]["lastAftermath"],
        "timeouts": (b["client"]["intentTimeouts"], a["client"]["intentTimeouts"]),
        "pushes": (b["client"]["coopClientBStatePushes"], a["client"]["coopClientBStatePushes"],
                   a["host"]["coopClientBStatePushes"]),
        "blocked": (b["client"]["coopLocalExecBlocked"], a["client"]["coopLocalExecBlocked"]),
        "inv": {"client": {k: a["client"][k] for k in INV_PROBES}, "host": {k: a["host"][k] for k in INV_PROBES}},
        "guardBefore": {"client": b["client"]["invGuard"]},
        "views": {"host": rec["hview"], "client": rec["cview"]},
        "newContexts": new_contexts(b["host"]["closedContexts"], a["host"]["closedContexts"]),
        "hostEvs": ev_tuples(rec["hev"]), "clientEvs": ev_tuples(rec["cev"]),
        "diff": rec["diff"], "desync": rec["dsc"]}


def guard_fails(before, rec, delta, last, what):
    """The client's invGuard: counts moved by exactly `delta`; `last` as named
    (None = unchanged from before the row)."""
    fails = []
    c0, c1 = guard_counts(before["client"]), guard_counts(rec["client"])
    want = {k: (c0[k] or 0) + delta.get(k, 0) for k in GUARD_KEYS}
    got = {k: c1[k] for k in GUARD_KEYS}
    if got != want:
        fails.append(f"{what}: client invGuard.counts {c0} -> {c1} (want {want})")
    l0, l1 = guard_last(before["client"]), guard_last(rec["client"])
    if last is None:
        if l1 != l0:
            fails.append(f"{what}: client invGuard.last {l0} -> {l1} (want unchanged: no execution point reached)")
    else:
        gl = {k: (l1 or {}).get(k) for k in last}
        if gl != last:
            fails.append(f"{what}: client invGuard.last {l1} (want {last})")
    return fails


def common_fails(host, client, before, guard_delta, guard_last_want, what):
    """Section 2 / (f) common asserts, after wait_host_idle."""
    fails = []
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        fails.append(f"{what}: host never idle / client never caught up: {short(e)}")
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"{what}: hash_now full not clean: {short(e, 600)}")
    ph, pc = probes(host), probes(client)
    if ph["desyncSeen"] or pc["desyncSeen"]:
        fails.append(f"{what}: desyncSeen host={ph['desyncSeen']} client={pc['desyncSeen']} (want false on both)")
    if pc["coopClientBStatePushes"] != before["client"]["coopClientBStatePushes"]:
        fails.append(f"{what}: client coopClientBStatePushes {before['client']['coopClientBStatePushes']}"
                     f"->{pc['coopClientBStatePushes']} (want unchanged)")
    if ph["coopClientBStatePushes"] != 0:
        fails.append(f"{what}: host coopClientBStatePushes={ph['coopClientBStatePushes']} (want 0)")
    if pc["invLocalWrites"] != 0:
        fails.append(f"{what}: client invLocalWrites={pc['invLocalWrites']} (want 0: the Q11 backstop refused a "
                     f"local moveItem)")
    hv = inv_view(host)
    if hv.get("open") is not False:
        fails.append(f"{what}: host inventory_view.open={hv.get('open')} (want false in a client row)")
    fails += guard_fails(before, {"client": pc}, guard_delta, guard_last_want, what)
    return fails


def nothing_sent_fails(before, rec, what):
    fails = []
    b, a = before, rec
    if a["client"]["coopIntentsSent"] != b["client"]["coopIntentsSent"]:
        fails.append(f"{what}: client coopIntentsSent {b['client']['coopIntentsSent']}->"
                     f"{a['client']['coopIntentsSent']} (want unchanged: nothing sent)")
    if a["client"]["inFlight"] is not None:
        fails.append(f"{what}: client inFlight {a['client']['inFlight']} (want null)")
    if a["host"]["lastSeqEmitted"] != b["host"]["lastSeqEmitted"]:
        fails.append(f"{what}: host lastSeqEmitted {b['host']['lastSeqEmitted']}->{a['host']['lastSeqEmitted']} "
                     f"(want unchanged)")
    if a["host"]["intentsReceived"] != b["host"]["intentsReceived"]:
        fails.append(f"{what}: host intentsReceived {b['host']['intentsReceived']}->{a['host']['intentsReceived']} "
                     f"(want unchanged)")
    return fails


def admitted_fails(before, rec, what):
    """An ADMITTED inv_move. Returns (fails, ctx)."""
    fails = []
    new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
    hits = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "inv_move"
            and c.get("actorId") == C_ID]
    ctx = hits[0] if len(hits) == 1 else None
    if len(hits) != 1:
        fails.append(f"{what}: host closedContexts gained {len(hits)} {{origin intent, kind inv_move, actorId {C_ID}}} "
                     f"(want exactly 1; new contexts={new})")
    aid = ctx.get("actionId") if ctx else None
    if ctx:
        chain = [e for e in rec["hev"] if e["actionId"] == aid]
        if [e["kind"] for e in chain] != ["bt_action_end"]:
            fails.append(f"{what}: host evs of actionId {aid} = {ev_tuples(chain)} (want exactly [bt_action_end])")
        cmap = {e["seq"]: e for e in rec["cev"]}
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
               if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
        if bad:
            fails.append(f"{what}: client event_log does not hold the host's evs of actionId {aid}: {bad}")
    extra = [e for e in rec["hev"] if e["actionId"] != aid]
    reveals = [e for e in extra if e["kind"] == "reveal" and e["actionId"] == 0]
    others = [e for e in extra if not (e["kind"] == "reveal" and e["actionId"] == 0)]
    if others or len(reveals) > 1:
        fails.append(f"{what}: host evs beside the inv_move context {ev_tuples(extra)} (want at most one `reveal` "
                     f"with actionId 0, F2093)")
    d = count_of(rec["client"]["coopIntentsSent"], "inv_move") - count_of(before["client"]["coopIntentsSent"],
                                                                          "inv_move")
    if d != 1:
        fails.append(f"{what}: client coopIntentsSent.inv_move +{d} (want +1)")
    da = recv_of(rec["host"]["intentsReceived"], "inv_move", "admitted") - recv_of(
        before["host"]["intentsReceived"], "inv_move", "admitted")
    if da != 1:
        fails.append(f"{what}: host intentsReceived.inv_move.admitted +{da} (want +1)")
    la = rec["client"]["lastAftermath"] or {}
    if aid is None or la.get("actionId") != aid or la.get("kind") != "inv_move":
        fails.append(f"{what}: client lastAftermath={rec['client']['lastAftermath']} (want {{actionId {aid}, "
                     f"kind inv_move}})")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"{what}: client inFlight at the end {rec['client']['inFlight']} (want null)")
    if rec["client"]["intentTimeouts"] != before["client"]["intentTimeouts"]:
        fails.append(f"{what}: client intentTimeouts {before['client']['intentTimeouts']}->"
                     f"{rec['client']['intentTimeouts']} (want unchanged)")
    if rec["cview"].get("selectedItem") != -1:
        fails.append(f"{what}: client inventory_view.selectedItem={rec['cview'].get('selectedItem')} after the "
                     f"answer (want -1)")
    return fails, ctx


def item_fails(rec, iid, want, what):
    """The item's fields equal on both machines and equal to `want`."""
    ih, ic = iview(rec["ih"], iid), iview(rec["ic"], iid)
    got_h = {k: (ih or {}).get(k) for k in want}
    got_c = {k: (ic or {}).get(k) for k in want}
    if got_h != want or got_c != want:
        return [f"{what}: item {iid} host={ih} client={ic} (want {want} on both)"]
    return []


def tu_fails(rec, want, what):
    th, tc = (rec["uh"].get(C_ID) or {}).get("tu"), (rec["uc"].get(C_ID) or {}).get("tu")
    if th != want or tc != want:
        return [f"{what}: C tu host={th} client={tc} (want {want} on both)"]
    return []


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


def evidence(row, fields):
    print(f"EVIDENCE {row}: " + json.dumps(fields, sort_keys=True, default=str), flush=True)


# ===================== rows =====================


def iv1_open_look(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV1", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    ev = {"leftover": leftover, "tab": tab_select(client, C_ID)}
    key = read_inventory_key(client.user_dir)
    ev["key"] = key
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    t0 = time.time()
    client.ok({"cmd": "inject_input", "kind": "key", "key": key})
    b_hit, b_dt = wait_until(lambda: banner(client) == TEXT_HOST_ONLY, BANNER_READ_S)
    ev["bannerWithin05s"] = {"text": banner(client), "hostOnlyAt": b_dt if b_hit else None}
    opened, dt = wait_until(lambda: inv_view(client).get("open") is True, CLICK_WAIT_S)
    ev["firstKey"] = {"opened": bool(opened), "waited": dt, "view": inv_view(client), "stack": stack(client),
                      "hostView": inv_view(host), "tSincePress": round(time.time() - t0, 3)}
    open_diff = diff_buckets(host, client) if opened else None
    mid = snap(host, client)
    ev["whileOpen"] = {"diff": open_diff, "sent": mid["client"]["coopIntentsSent"],
                       "hostSeq": mid["host"]["lastSeqEmitted"], "inFlight": mid["client"]["inFlight"]}
    if opened:
        client.ok({"cmd": "inject_input", "kind": "key", "key": key})
        closed, dt2 = wait_until(lambda: "InventoryState" not in stack(client), CLICK_WAIT_S)
        ev["secondKey"] = {"closed": bool(closed), "waited": dt2, "stack": stack(client)}
    else:
        ev["secondKey"] = "not pressed: the first key opened nothing"
    rec = collect(host, client, seq0)
    evidence("IV1", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                     "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not ev["tab"]:
        fails.append(f"precondition: TAB never selected C on the client (selectedId "
                     f"{battle_state(client).get('selectedId')})")
    if not opened:
        fails.append(f"IV1: the client's INVENTORY key (key {key}) opened no InventoryState (client stack "
                     f"{ev['firstKey']['stack']}, client banner within {BANNER_READ_S} s "
                     f"{ev['bannerWithin05s']['text']!r})")
    else:
        v = ev["firstKey"]["view"]
        if not (v.get("top") is True and v.get("unitId") == C_ID and v.get("selectedItem") == -1):
            fails.append(f"IV1: client inventory_view after the key {v} (want open, top, unitId {C_ID}, "
                         f"selectedItem -1)")
        if ev["firstKey"]["hostView"].get("open") is not False:
            fails.append(f"IV1: host inventory_view {ev['firstKey']['hostView']} (want open false: client only)")
        if open_diff:
            fails.append(f"IV1: buckets differ with the client's screen open: {open_diff} (want none)")
        if not ev["secondKey"]["closed"]:
            fails.append(f"IV1: the second INVENTORY key did not close the client's screen "
                         f"(stack {ev['secondKey']['stack']})")
    fails += nothing_sent_fails(before, rec, "IV1")
    fails += common_fails(host, client, before, {}, None, "IV1")
    finish(fails)


def iv2_pickup_local(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV2", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = returned = False
    cursor_diff = None
    if opened:
        picked = pick(client, ev, "pick", BELT, 1, 0, g)
        cursor_diff = diff_buckets(host, client)
        mid = snap(host, client)
        ev["withCursor"] = {"diff": cursor_diff, "sent": mid["client"]["coopIntentsSent"],
                            "hostSeq": mid["host"]["lastSeqEmitted"]}
        returned = right_click_return(client, ev, "rightClick", BELT, 1, 0)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV2", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                     "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IV2")
    else:
        if not picked:
            fails.append(f"IV2: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor "
                         f"(want the grenade {g}; click {ev['pick']})")
        if cursor_diff:
            fails.append(f"IV2: buckets differ with the grenade on the cursor: {cursor_diff} (want none)")
        if not returned:
            fails.append(f"IV2: the right-click left {ev['rightClick'].get('cursor')} on the cursor (want -1)")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IV2: the client's screen did not close: {ev.get('close')}")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IV2")
    fails += tu_fails(rec, C_TU_MAX, "IV2")
    fails += nothing_sent_fails(before, rec, "IV2")
    fails += common_fails(host, client, before, {}, None, "IV2")
    finish(fails)


def iv3_grenade_to_hand(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV3", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = False
    win = {}
    dr = disarm = None
    if opened:
        picked = pick(client, ev, "pick", BELT, 1, 0, g)
        if picked:
            dr = host.ok({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})
            t0 = time.time()
            ev["drop"] = click(client, slot=LH, x=0, y=0)
            win["sent"] = wait_sent(host, client, before)
            # the in-flight window (ST4): sampled while the host holds the order
            ec = event_state(client)
            win["inFlight"] = ec.get("inFlight")
            win["cursor"] = selected(client)
            ih_w, ic_w = items_by_id(host), items_by_id(client)
            win["grenade"] = {"host": iview(ih_w, g), "client": iview(ic_w, g)}
            win["tu"] = {"host": tu_of(host, C_ID), "client": tu_of(client, C_ID)}
            win["diff"] = diff_buckets(host, client)
            win["sentAt"] = ec.get("coopIntentsSent")
            g_counts1 = guard_counts(probes(client))
            ev["drop2"] = click(client, slot=LH, x=0, y=0)
            _, win["drop2Waited"] = wait_until(lambda: guard_counts(probes(client)) != g_counts1, CLICK_WAIT_S)
            ec2 = event_state(client)
            win["afterSecond"] = {"invGuardLast": (ec2.get("invGuard") or {}).get("last"),
                                  "sent": ec2.get("coopIntentsSent"), "inFlight": ec2.get("inFlight")}
            win["sampledInS"] = round(time.time() - t0, 3)
            win["orderWait"] = wait_order(host, client, notes)
            disarm = host.ok({"cmd": "defer_intents", "ms": 0, "count": 0})  # never outlives the row
            time.sleep(0.3)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV3", {"staging": st, "stagedDiff": staged, "ui": ev, "defer": dr, "disarm": disarm, "window": win,
                     "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IV3")
        fails += nothing_sent_fails(before, rec, "IV3")
        fails += common_fails(host, client, before, {}, None, "IV3")
        finish(fails)
    if not picked:
        fails.append(f"IV3: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want {g})")
    else:
        # inside the window
        fl = win.get("inFlight") or {}
        if win["sent"]["state"] != "sent" or fl.get("kind") != "inv_move":
            fails.append(f"IV3 window: the drop on STR_LEFT_HAND is not in flight as inv_move (sent {win['sent']}, "
                         f"client inFlight {win.get('inFlight')})")
        if win.get("cursor") != g:
            fails.append(f"IV3 window: client selectedItem {win.get('cursor')} while in flight (want {g}: Q2 a)")
        want_belt = {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
        for m in ("host", "client"):
            got = {k: (win["grenade"][m] or {}).get(k) for k in want_belt}
            if got != want_belt:
                fails.append(f"IV3 window: {m} grenade {win['grenade'][m]} while in flight (want {want_belt})")
        if win["tu"] != {"host": C_TU_MAX, "client": C_TU_MAX}:
            fails.append(f"IV3 window: C tu {win['tu']} while in flight (want {C_TU_MAX} on both)")
        if win.get("diff"):
            fails.append(f"IV3 window: buckets differ while the order is held: {win['diff']} (want none)")
        a2 = win.get("afterSecond") or {}
        if (a2.get("invGuardLast") or {}).get("decision") != "inflight":
            fails.append(f"IV3 window: client invGuard.last after the second drop {a2.get('invGuardLast')} "
                         f"(want decision inflight, D150)")
        if count_of(a2.get("sent"), "inv_move") != count_of(win.get("sentAt"), "inv_move"):
            fails.append(f"IV3 window: coopIntentsSent.inv_move {win.get('sentAt')} -> {a2.get('sent')} after the "
                         f"second drop (want unchanged)")
        if not a2.get("inFlight"):
            fails.append(f"precondition: the second drop did not land while the first was in flight "
                         f"(window {win})")
        # after the answer
        f, cx = admitted_fails(before, rec, "IV3")
        fails += f
        fails += item_fails(rec, g, {"owner": C_ID, "slot": LH, "onTile": False}, "IV3")
        fails += tu_fails(rec, C_TU_MAX - TU_BELT_TO_HAND, "IV3")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IV3: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1, "inflight": 1},
                          {"site": "drop", "op": "move", "decision": "inflight", "itemId": g, "actorId": C_ID}, "IV3")
    finish(fails)


def iv4_ground_to_belt(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV4", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    clip = st["ids"]["groundClip"]
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = False
    cell = None
    if opened:
        ground = inv_view(client).get("ground") or []
        ev["ground"] = ground
        hit = [gi for gi in ground if gi.get("id") == clip]
        cell = (hit[0]["x"], hit[0]["y"]) if hit else None
        if cell is not None:
            picked = pick(client, ev, "pick", GROUND, cell[0], cell[1], clip)
        if picked:
            ev["drop"] = click(client, slot=BELT, x=2, y=0)
            ev["sent"] = wait_sent(host, client, before)
            ev["orderWait"] = wait_order(host, client, notes)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV4", {"staging": st, "stagedDiff": staged, "ui": ev, "clipCell": cell,
                     "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IV4")
        fails += nothing_sent_fails(before, rec, "IV4")
        fails += common_fails(host, client, before, {}, None, "IV4")
        finish(fails)
    if cell is None:
        fails.append(f"precondition: the ground rifle clip {clip} is not in the client's inventory_view.ground "
                     f"{ev.get('ground')}")
    elif not picked:
        fails.append(f"IV4: the click on the clip's ground cell {cell} put {ev['pick'].get('cursor')} on the cursor "
                     f"(want {clip})")
    else:
        f, cx = admitted_fails(before, rec, "IV4")
        fails += f
        fails += item_fails(rec, clip, {"owner": C_ID, "slot": BELT, "slotX": 2, "slotY": 0, "onTile": False}, "IV4")
        fails += tu_fails(rec, C_TU_MAX - TU_GROUND_TO_BELT, "IV4")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IV4: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": clip, "actorId": C_ID}, "IV4")
    finish(fails)


def iv5_hand_to_ground(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV5", "RH_LH")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    tile = ROW_TILE["IV5"]
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = False
    if opened:
        ev["groundBefore"] = inv_view(client).get("ground")
        picked = pick(client, ev, "pick", LH, 0, 0, g)
        if picked:
            ev["drop"] = click(client, slot=GROUND, x=0, y=0)
            ev["sent"] = wait_sent(host, client, before)
            ev["orderWait"] = wait_order(host, client, notes)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV5", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                     "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IV5")
        fails += nothing_sent_fails(before, rec, "IV5")
        fails += common_fails(host, client, before, {}, None, "IV5")
        finish(fails)
    if ev.get("groundBefore"):
        fails.append(f"precondition: IV5's tile {tile} holds items {ev['groundBefore']} (want an empty tile)")
    if not picked:
        fails.append(f"IV5: the click on STR_LEFT_HAND put {ev['pick'].get('cursor')} on the cursor (want {g})")
    else:
        f, cx = admitted_fails(before, rec, "IV5")
        fails += f
        fails += item_fails(rec, g, {"owner": -1, "slot": GROUND, "onTile": True, "tx": tile[0], "ty": tile[1],
                                     "tz": tile[2]}, "IV5")
        fails += tu_fails(rec, C_TU_MAX - TU_HAND_TO_GROUND, "IV5")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IV5: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID}, "IV5")
    finish(fails)


def inv_req(actor, item, slot, x, y, tu_override=None):
    """battle_intent's `inv_move` request (section 8.2: plan {op, item, to {slot, x, y}})."""
    req = {"cmd": "battle_intent", "kind": "inv_move", "actor": actor,
           "plan": {"op": "move", "item": item, "to": {"slot": slot, "x": x, "y": y}}}
    if tu_override is not None:
        req["tuBasisOverride"] = tu_override
    return req


def send_intent(host, client, req, notes):
    """One lever order; when sent, waits (bounded) for the host's answer: its deny
    (client lastDeny.iseq) or the end of the order."""
    r = client.cmd(dict(req))
    iseq = r.get("iseq") if r.get("ok") else None
    out = {"resp": r, "sent": bool(iseq), "iseq": iseq, "answer": None}
    if not iseq:
        return out

    def answered():
        ld = event_state(client).get("lastDeny") or {}
        if ld.get("iseq") == iseq:
            return "deny"
        if order_done(host, client):
            ld = event_state(client).get("lastDeny") or {}
            return "deny" if ld.get("iseq") == iseq else "end"
        return None
    got, dt = wait_until(answered, ANSWER_TIMEOUT_S, 0.1)
    out["answer"], out["waited"] = got, dt
    if not got:
        notes.append(f"no answer to iseq {iseq} in {ANSWER_TIMEOUT_S} s")
    return out


def iv11_host_denies(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    # H's kit: H onto STAGE_H, stripped, one grenade on its belt (the item_missing order's item)
    th = tele_both(host, client, H_ID, STAGE_H, ROW_DIR)
    h_stripped = strip_both(host, client, H_ID)
    h_gren = give(host, client, H_ID, GRENADE, BELT, 1, 0)
    st = restage(host, client, "IV11", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g, clip = st["ids"]["grenade"], st["ids"]["beltClip"]
    first = snap(host, client)
    seq0 = first["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover, "H": {"tele": th.get("to"), "stripped": h_stripped, "grenade": h_gren}}
    opened = open_client(client, ev)
    variants = [
        ("cost_changed", f"tuBasisOverride {TU_BASIS_BAD}", None,
         inv_req(C_ID, g, LH, 0, 0, tu_override=TU_BASIS_BAD)),
        ("item_missing", f"H's grenade {h_gren}", None, inv_req(C_ID, h_gren, LH, 0, 0)),
        ("not_your_unit", f"actor H {H_ID}", None, inv_req(H_ID, h_gren, LH, 0, 0)),
        ("invalid_target", f"grenade -> STR_BELT (0,0) holding the clip {clip}", None, inv_req(C_ID, g, BELT, 0, 0)),
        ("no_tu", f"C TU 1, belt -> LH basis {TU_BELT_TO_HAND}", 1,
         inv_req(C_ID, g, LH, 0, 0, tu_override=TU_BELT_TO_HAND)),
    ]
    rows = []
    for reason, name, tu_set, req in variants:
        tu_now = set_tu_both(host, client, C_ID, tu_set) if tu_set is not None else None
        b = snap(host, client)
        si = send_intent(host, client, req, notes)
        a = snap(host, client)
        ih, ic = items_by_id(host), items_by_id(client)
        rows.append({"want": reason, "name": name, "req": req, "tuSet": tu_now, "intent": si,
                     "lastDeny": a["client"]["lastDeny"],
                     "invLastWarning": (b["client"]["invLastWarning"], a["client"]["invLastWarning"]),
                     "hostSeq": (b["host"]["lastSeqEmitted"], a["host"]["lastSeqEmitted"]),
                     "newContexts": new_contexts(b["host"]["closedContexts"], a["host"]["closedContexts"]),
                     "inFlight": a["client"]["inFlight"],
                     "sent": count_of(a["client"]["coopIntentsSent"], "inv_move")
                     - count_of(b["client"]["coopIntentsSent"], "inv_move"),
                     "denied": recv_of(a["host"]["intentsReceived"], "inv_move", "denied")
                     - recv_of(b["host"]["intentsReceived"], "inv_move", "denied"),
                     "admitted": recv_of(a["host"]["intentsReceived"], "inv_move", "admitted")
                     - recv_of(b["host"]["intentsReceived"], "inv_move", "admitted"),
                     "items": {n: {"host": iview(ih, i), "client": iview(ic, i)}
                               for n, i in (("grenade", g), ("hGrenade", h_gren), ("beltClip", clip))},
                     "cTu": (tu_of(host, C_ID), tu_of(client, C_ID))})
    close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV11", {"staging": st, "stagedDiff": staged, "ui": ev,
                      "variants": [{k: v for k, v in r.items() if k != "req"} for r in rows],
                      "requests": [r["req"] for r in rows], "row": rec_view(first, rec, st["ids"]),
                      "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    want_items = {"grenade": {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                  "hGrenade": {"owner": H_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                  "beltClip": {"owner": C_ID, "slot": BELT, "slotX": 0, "slotY": 0, "onTile": False}}
    last_text = None
    for r in rows:
        tag = f"IV11 {r['want']} ({r['name']})"
        si = r["intent"]
        if not si["sent"]:
            fails.append(f"{tag}: battle_intent answered {si['resp']} (want sent: an iseq)")
            continue
        ld = r["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != r["want"]:
            fails.append(f"{tag}: client lastDeny {r['lastDeny']} (want {{iseq {si['iseq']}, reason {r['want']}}})")
        w0, w1 = r["invLastWarning"]
        want_text = TEXT_DENY.get(r["want"], w0)   # a silent reason leaves the line unchanged
        if w1 != want_text:
            fails.append(f"{tag}: client invLastWarning {w0!r} -> {w1!r} (want {want_text!r})")
        if r["want"] == "invalid_target" and last_text is None:
            fails.append(f"{tag}: precondition: no earlier variant set invLastWarning, so 'unchanged' is vacuous")
        last_text = w1 or last_text
        if r["hostSeq"][0] != r["hostSeq"][1] or r["newContexts"]:
            fails.append(f"{tag}: host lastSeqEmitted {r['hostSeq'][0]}->{r['hostSeq'][1]} newContexts="
                         f"{r['newContexts']} (want nothing executed)")
        if r["inFlight"] is not None:
            fails.append(f"{tag}: client inFlight after the deny {r['inFlight']} (want null)")
        if (r["sent"], r["denied"], r["admitted"]) != (1, 1, 0):
            fails.append(f"{tag}: client coopIntentsSent.inv_move +{r['sent']} host intentsReceived.inv_move "
                         f"denied +{r['denied']} admitted +{r['admitted']} (want +1 / +1 / +0)")
        for n, want in want_items.items():
            for m in ("host", "client"):
                got = {k: (r["items"][n][m] or {}).get(k) for k in want}
                if got != want:
                    fails.append(f"{tag}: {m} {n} {r['items'][n][m]} (want {want}: nothing executed)")
        want_tu = 1 if r["want"] == "no_tu" else C_TU_MAX
        if r["cTu"] != (want_tu, want_tu):
            fails.append(f"{tag}: C tu host/client {r['cTu']} (want {want_tu} on both)")
    if not opened:
        fails += open_fails(ev, "IV11")
    fails += common_fails(host, client, first, {}, None, "IV11")
    finish(fails)


def iv12_local_tu_refusal(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV12", "K0")
    st["tuSet"] = set_tu_both(host, client, C_ID, 1)
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = returned = False
    if opened:
        picked = pick(client, ev, "pick", BELT, 1, 0, g)
        if picked:
            ev["drop"] = click(client, slot=LH, x=0, y=0)
            ev["sent"] = wait_sent(host, client, before)
            ec = event_state(client)
            ev["afterDrop"] = {"cursor": selected(client), "invGuardLast": (ec.get("invGuard") or {}).get("last"),
                               "tu": {"host": tu_of(host, C_ID), "client": tu_of(client, C_ID)},
                               "grenade": {"host": iview(items_by_id(host), g),
                                           "client": iview(items_by_id(client), g)}}
            returned = right_click_return(client, ev, "rightClick", BELT, 1, 0)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV12", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                      "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if st["tuSet"] != 1:
        fails.append(f"precondition: C's TU {st['tuSet']} after set_tu_both 1 (want 1)")
    if not opened:
        fails += open_fails(ev, "IV12")
        fails += nothing_sent_fails(before, rec, "IV12")
        fails += common_fails(host, client, before, {}, None, "IV12")
        finish(fails)
    if not picked:
        fails.append(f"IV12: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want {g})")
    else:
        ad = ev["afterDrop"]
        if ad["cursor"] != g:
            fails.append(f"IV12: client selectedItem {ad['cursor']} after the refused drop (want {g}: still selected)")
        if ev["sent"]["state"] != "quiet":
            fails.append(f"IV12: the refused drop {ev['sent']} (want nothing sent)")
        if not returned:
            fails.append(f"IV12: the right-click left {ev['rightClick'].get('cursor')} on the cursor (want -1)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IV12")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IV12: the client's screen did not close: {ev.get('close')}")
    fails += tu_fails(rec, 1, "IV12")
    fails += nothing_sent_fails(before, rec, "IV12")
    fails += common_fails(host, client, before, {"vanilla_refused": 1},
                          {"site": "drop", "op": "move", "decision": "vanilla_refused", "itemId": g,
                           "actorId": C_ID}, "IV12")
    finish(fails)


def iv13_real_ui_deny(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV13", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = False
    win = {}
    dr = disarm = None
    if opened:
        picked = pick(client, ev, "pick", BELT, 1, 0, g)
        if picked:
            dr = host.ok({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})
            t0 = time.time()
            ev["drop"] = click(client, slot=LH, x=0, y=0)
            win["sent"] = wait_sent(host, client, before)
            win["tuSet"] = set_tu_both(host, client, C_ID, 1)
            win["tuSetAtS"] = round(time.time() - t0, 3)
            win["inFlightAfterTuSet"] = event_state(client).get("inFlight")
            iseq = (win["sent"].get("inFlight") or {}).get("iseq")
            win["iseq"] = iseq

            def denied():
                ld = event_state(client).get("lastDeny") or {}
                return ld if (iseq is not None and ld.get("iseq") == iseq) else None
            got, dt = wait_until(denied, ANSWER_TIMEOUT_S, 0.1)
            win["answer"], win["answerAtS"] = got, round(time.time() - t0, 3)
            if not got:
                notes.append(f"no deny for iseq {iseq} in {ANSWER_TIMEOUT_S} s")
            win["orderWait"] = wait_order(host, client, notes)
            disarm = host.ok({"cmd": "defer_intents", "ms": 0, "count": 0})  # never outlives the row
            time.sleep(0.3)
            win["cursor"] = selected(client)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV13", {"staging": st, "stagedDiff": staged, "ui": ev, "defer": dr, "disarm": disarm, "window": win,
                      "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IV13")
        fails += nothing_sent_fails(before, rec, "IV13")
        fails += common_fails(host, client, before, {}, None, "IV13")
        finish(fails)
    if not picked:
        fails.append(f"IV13: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want {g})")
    else:
        if win["sent"]["state"] != "sent" or not win.get("inFlightAfterTuSet"):
            fails.append(f"precondition: set_tu_both(C, 1) did not land inside the held order's window "
                         f"(sent {win['sent']}, inFlight after the TU lever {win.get('inFlightAfterTuSet')}, "
                         f"at {win.get('tuSetAtS')} s)")
        if win["tuSet"] != 1:
            fails.append(f"IV13: C's TU {win['tuSet']} after set_tu_both 1 (want 1)")
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("reason") != "no_tu" or ld.get("iseq") != win.get("iseq"):
            fails.append(f"IV13: client lastDeny {rec['client']['lastDeny']} (want {{iseq {win.get('iseq')}, "
                         f"reason no_tu}})")
        if rec["client"]["invLastWarning"] != TEXT_DENY["no_tu"]:
            fails.append(f"IV13: client invLastWarning {rec['client']['invLastWarning']!r} "
                         f"(want {TEXT_DENY['no_tu']!r})")
        if win.get("cursor") != -1:
            fails.append(f"IV13: client selectedItem {win.get('cursor')} after the deny (want -1: the item returned)")
        d = count_of(rec["client"]["coopIntentsSent"], "inv_move") - count_of(before["client"]["coopIntentsSent"],
                                                                              "inv_move")
        dd = recv_of(rec["host"]["intentsReceived"], "inv_move", "denied") - recv_of(
            before["host"]["intentsReceived"], "inv_move", "denied")
        if (d, dd) != (1, 1):
            fails.append(f"IV13: client coopIntentsSent.inv_move +{d} host intentsReceived.inv_move.denied +{dd} "
                         f"(want +1 / +1)")
        new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
        if new or rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
            fails.append(f"IV13: host lastSeqEmitted {before['host']['lastSeqEmitted']}->"
                         f"{rec['host']['lastSeqEmitted']} newContexts={new} (want nothing executed)")
        if rec["client"]["inFlight"] is not None:
            fails.append(f"IV13: client inFlight after the deny {rec['client']['inFlight']} (want null)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IV13")
        fails += tu_fails(rec, 1, "IV13")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IV13: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID}, "IV13")
    finish(fails)


# ===================== S-B rows (section 9) =====================


def items_both(host, client, ids):
    ih, ic = items_by_id(host), items_by_id(client)
    return {n: {"host": iview(ih, i), "client": iview(ic, i)} for n, i in ids.items()}


def staged_item_fails(st_items, wants, what):
    """A staging precondition: each named item as the kit put it, on both machines."""
    fails = []
    for n, want in wants.items():
        for m in ("host", "client"):
            got = {k: (st_items[n][m] or {}).get(k) for k in want}
            if got != want:
                fails.append(f"precondition: {what} staged {m} {n} {st_items[n][m]} (want {want})")
    return fails


def sb_client_row(host, client, row, do_op, what, guard, tu_spent, outcome, staged_want=None):
    """IV6-IV10: one real-UI inventory op of the client on its own C.
    do_op(client, ev, ids) makes the row's clicks and returns True when its own
    precondition held (the pick landed, the cell was found). Then: up to
    SENT_WAIT_S for the order to show as sent and, when sent, the end of the order;
    the cursor, invGuard and inFlight right after; an item still on the cursor then
    goes back with ONE right-click (recorded; the interim refusal keeps it there) and
    the screen closes. guard = (site, op, the ids key of the order's item);
    tu_spent = T0-1b's cost, or cost(st) -> (cost, precondition fails) (IV9, F2090);
    outcome(ids, tile) = {ids key: the item's T0-1b host-vanilla outcome}."""
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, row, row)
    cost_fails = []
    if callable(tu_spent):
        tu_spent, cost_fails = tu_spent(st)
    st["tuSpentWant"] = tu_spent
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    ids = st["ids"]
    tile = ROW_TILE[row]
    st_items = items_both(host, client, ids)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    reached = False
    if opened:
        reached = do_op(client, ev, ids)
        if reached:
            ev["sent"] = wait_sent(host, client, before)
            if ev["sent"]["state"] != "quiet":
                ev["orderWait"] = wait_order(host, client, notes)
            ec = event_state(client)
            ev["afterOp"] = {"cursor": selected(client), "invGuardLast": (ec.get("invGuard") or {}).get("last"),
                             "inFlight": ec.get("inFlight"), "invLastWarning": ec.get("invLastWarning")}
        if selected(client) != -1:
            right_click_return(client, ev, "cleanupReturn", BELT, 0, 0)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence(row, {"staging": st, "stagedDiff": staged, "stagedItems": st_items, "ui": ev,
                   "row": rec_view(before, rec, ids), "notes": notes})
    fails = list(notes) + staged_fails(st, staged) + cost_fails
    if staged_want:
        fails += staged_item_fails(st_items, staged_want(ids, tile), row)
    if not opened:
        fails += open_fails(ev, row)
        fails += nothing_sent_fails(before, rec, row)
        fails += common_fails(host, client, before, {}, None, row)
        finish(fails)
    if not reached:
        fails.append(f"precondition: {row}'s {what} never reached its execution point (ui {ev})")
    else:
        ao = ev["afterOp"]
        if ev["sent"]["state"] != "sent":
            fails.append(f"{row}: the {what} was not sent as inv_move (sent {ev['sent']}; client invGuard.last "
                         f"{ao['invGuardLast']}; want decision sent)")
        f, cx = admitted_fails(before, rec, row)
        fails += f
        if ao["cursor"] != -1:
            fails.append(f"{row}: client selectedItem {ao['cursor']} after the order (want -1: the answer clears "
                         f"the cursor)")
        for n, want in outcome(ids, tile).items():
            fails += item_fails(rec, ids[n], want, f"{row} {n}")
        fails += tu_fails(rec, C_TU_MAX - tu_spent, row)
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"{row}: the client's screen did not close: {ev.get('close')}")
    site, op, key = guard
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": site, "op": op, "decision": "sent", "itemId": ids[key], "actorId": C_ID}, row)
    finish(fails)


def iv6_load(host, client, ctx):
    """C29a: the belt clip dropped on the empty rifle in RH (T0-1b op4)."""
    def do_op(cl, ev, ids):
        if not pick(cl, ev, "pick", BELT, 0, 0, ids["beltClip"]):
            return False
        ev["drop"] = click(cl, slot=RH, x=0, y=0)
        return "error" not in ev["drop"]

    def staged_want(ids, tile):
        r = ids["rifle"]
        return {"rifle": {"owner": C_ID, "slot": RH, "onTile": False, "ammo": [r, r, r], "fuse": -1},
                "beltClip": {"owner": C_ID, "slot": BELT, "slotX": 0, "slotY": 0, "onTile": False, "fuse": -1}}

    def outcome(ids, tile):
        r, c = ids["rifle"], ids["beltClip"]
        return {"rifle": {"owner": C_ID, "slot": RH, "onTile": False, "ammo": [c, r, r, r], "fuse": -1},
                "beltClip": {"owner": -1, "slot": "", "onTile": False, "ammo": [], "fuse": -1}}
    sb_client_row(host, client, "IV6", do_op, "load (clip belt (0,0) -> the rifle in STR_RIGHT_HAND)",
                  ("load", "load", "beltClip"), TU_LOAD, outcome, staged_want)


def iv7_shift_unload(host, client, ctx):
    """Shift+click the loaded rifle in RH with LH free (T0-1b op5)."""
    def do_op(cl, ev, ids):
        g0 = (probes(cl).get("invGuard") or {}).get("last")
        ev["shiftClick"] = click(cl, slot=RH, x=0, y=0, mod="shift")
        _, ev["shiftClick"]["waited"] = wait_until(
            lambda: (probes(cl).get("invGuard") or {}).get("last") != g0, CLICK_WAIT_S)
        return "error" not in ev["shiftClick"]

    def staged_want(ids, tile):
        r, c = ids["rifle"], ids["clip"]
        return {"rifle": {"owner": C_ID, "slot": RH, "onTile": False, "ammo": [c, r, r, r], "fuse": -1},
                "clip": {"owner": -1, "slot": "", "onTile": False}}

    def outcome(ids, tile):
        r, c = ids["rifle"], ids["clip"]
        return {"rifle": {"owner": C_ID, "slot": RH, "onTile": False, "ammo": [r, r, r], "fuse": -1},
                "clip": {"owner": C_ID, "slot": LH, "onTile": False, "ammo": [], "fuse": -1}}
    sb_client_row(host, client, "IV7", do_op, "Shift+click unload of the rifle in STR_RIGHT_HAND",
                  ("unload", "unload", "rifle"), TU_SHIFT_UNLOAD, outcome, staged_want)


def iv8_ctrl_autoplace(host, client, ctx):
    """Ctrl+click the grenade on the ground (T0-1b op7): vanilla's first fitting cell."""
    def do_op(cl, ev, ids):
        ground = inv_view(cl).get("ground") or []
        ev["ground"] = ground
        if [gi.get("id") for gi in ground] != [ids["grenade"]]:
            return False
        cell = (ground[0]["x"], ground[0]["y"])
        ev["cell"] = cell
        g0 = (probes(cl).get("invGuard") or {}).get("last")
        ev["ctrlClick"] = click(cl, slot=GROUND, x=cell[0], y=cell[1], mod="ctrl")
        _, ev["ctrlClick"]["waited"] = wait_until(
            lambda: (probes(cl).get("invGuard") or {}).get("last") != g0, CLICK_WAIT_S)
        return "error" not in ev["ctrlClick"]

    def staged_want(ids, tile):
        return {"grenade": {"owner": -1, "slot": GROUND, "onTile": True, "tx": tile[0], "ty": tile[1],
                            "tz": tile[2], "fuse": -1}}

    def outcome(ids, tile):
        return {"grenade": {"owner": C_ID, "slot": BELT, "slotX": 0, "slotY": 0, "onTile": False, "ammo": [],
                            "fuse": -1}}
    sb_client_row(host, client, "IV8", do_op, "Ctrl+click auto-place of the ground grenade",
                  ("ctrl_fit", "move", "grenade"), TU_CTRL_FIT, outcome, staged_want)


def iv9_unload_unprime(host, client, ctx):
    """The primed grenade picked from belt (3,0), then the UNLOAD button, LH free
    (T0-1b op6). The cost is a % of C's base TU: RULING F2090 (a)."""
    def do_op(cl, ev, ids):
        if not pick(cl, ev, "pick", BELT, 3, 0, ids["primed"]):
            return False
        ev["unload"] = click(cl, widget="unload")
        return "error" not in ev["unload"]

    def staged_want(ids, tile):
        return {"primed": {"owner": C_ID, "slot": BELT, "slotX": 3, "slotY": 0, "onTile": False, "fuse": 0}}

    def outcome(ids, tile):
        return {"primed": {"owner": C_ID, "slot": LH, "onTile": False, "ammo": [], "fuse": -1}}

    def unprime_cost(st):
        # F2090 (a): the formula on C's run-time base TU (restage's battle_set_unit_state tu 255
        # clamps to getBaseStats()->tu, asserted 64 by staged_fails) must give the pinned 20.
        base = st["tu"]
        spent = max(1, (base * UNPRIME_PCT) // 100) + TU_UNPRIME_TO_HAND
        bad = [] if spent == TU_UNPRIME_C else [
            f"precondition: C's base TU {base} gives the unprime cost {spent} (want {TU_UNPRIME_C}, F2090)"]
        return spent, bad
    sb_client_row(host, client, "IV9", do_op, "UNLOAD unprime of the primed grenade",
                  ("unload", "unload", "primed"), unprime_cost, outcome, staged_want)


def iv10_paperdoll(host, client, ctx):
    """The grenade picked from belt (1,0), then a click on the paperdoll with
    oxceInventoryDropItemOverPaperdoll on (T0-1b op8)."""
    def do_op(cl, ev, ids):
        if not pick(cl, ev, "pick", BELT, 1, 0, ids["grenade"]):
            return False
        ev["paperdoll"] = click(cl, widget="paperdoll")
        return "error" not in ev["paperdoll"]

    def staged_want(ids, tile):
        return {"grenade": {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False, "fuse": -1}}

    def outcome(ids, tile):
        return {"grenade": {"owner": -1, "slot": GROUND, "onTile": True, "tx": tile[0], "ty": tile[1],
                            "tz": tile[2], "ammo": [], "fuse": -1}}
    sb_client_row(host, client, "IV10", do_op, "paperdoll drop of the grenade",
                  ("paperdoll", "move", "grenade"), TU_PAPERDOLL, outcome, staged_want)


def inv_load_req(actor, item, weapon, swap=False):
    """battle_intent's `inv_move` load (section 8.2: plan {op, item, weapon, swap})."""
    return {"cmd": "battle_intent", "kind": "inv_move", "actor": actor,
            "plan": {"op": "load", "item": item, "weapon": weapon, "swap": swap}}


def inv_unload_req(actor, item):
    return {"cmd": "battle_intent", "kind": "inv_move", "actor": actor, "plan": {"op": "unload", "item": item}}


def iv11b_load_unload_denies(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "IV11b", "IV11b")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    ids = st["ids"]
    tile = ROW_TILE["IV11b"]
    r, rb, bc, pc, gl = ids["rifle"], ids["bpRifle"], ids["beltClip"], ids["groundPistolClip"], ids["lhGrenade"]
    want_items = {
        "rifle": {"owner": C_ID, "slot": RH, "onTile": False, "ammo": [r, r, r], "fuse": -1},
        "bpRifle": {"owner": C_ID, "slot": BACK_PACK, "slotX": 0, "slotY": 0, "onTile": False,
                    "ammo": [ids["bpClip"], rb, rb, rb], "fuse": -1},
        "bpClip": {"owner": -1, "slot": "", "onTile": False},
        "beltClip": {"owner": C_ID, "slot": BELT, "slotX": 0, "slotY": 0, "onTile": False},
        "groundPistolClip": {"owner": -1, "slot": GROUND, "onTile": True, "tx": tile[0], "ty": tile[1],
                             "tz": tile[2]},
        "lhGrenade": {"owner": C_ID, "slot": LH, "onTile": False, "fuse": -1}}
    st_items = items_both(host, client, {n: ids[n] for n in want_items})
    first = snap(host, client)
    seq0 = first["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    variants = [
        ("wrong_ammo", f"pistol clip {pc} -> the empty rifle {r} in STR_RIGHT_HAND", inv_load_req(C_ID, pc, r)),
        ("already_loaded", f"rifle clip {bc} -> the loaded rifle {rb} in STR_BACK_PACK, swap false",
         inv_load_req(C_ID, bc, rb, False)),
        ("one_hand_empty", f"unload the loaded rifle {rb} in STR_BACK_PACK, both hands full (rifle {r} RH, "
                           f"grenade {gl} LH)", inv_unload_req(C_ID, rb)),
        ("no_ammo_loaded", f"unload the empty rifle {r} in STR_RIGHT_HAND", inv_unload_req(C_ID, r)),
    ]
    rows = []
    for reason, name, req in variants:
        b = snap(host, client)
        si = send_intent(host, client, req, notes)
        a = snap(host, client)
        rows.append({"want": reason, "name": name, "req": req, "intent": si,
                     "lastDeny": a["client"]["lastDeny"],
                     "invLastWarning": (b["client"]["invLastWarning"], a["client"]["invLastWarning"]),
                     "hostSeq": (b["host"]["lastSeqEmitted"], a["host"]["lastSeqEmitted"]),
                     "newContexts": new_contexts(b["host"]["closedContexts"], a["host"]["closedContexts"]),
                     "inFlight": a["client"]["inFlight"],
                     "sent": count_of(a["client"]["coopIntentsSent"], "inv_move")
                     - count_of(b["client"]["coopIntentsSent"], "inv_move"),
                     "denied": recv_of(a["host"]["intentsReceived"], "inv_move", "denied")
                     - recv_of(b["host"]["intentsReceived"], "inv_move", "denied"),
                     "admitted": recv_of(a["host"]["intentsReceived"], "inv_move", "admitted")
                     - recv_of(b["host"]["intentsReceived"], "inv_move", "admitted"),
                     "items": items_both(host, client, {n: ids[n] for n in want_items}),
                     "cTu": (tu_of(host, C_ID), tu_of(client, C_ID))})
    close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IV11b", {"staging": st, "stagedDiff": staged, "stagedItems": st_items, "ui": ev,
                       "variants": [{k: v for k, v in x.items() if k != "req"} for x in rows],
                       "requests": [x["req"] for x in rows], "row": rec_view(first, rec, ids), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    fails += staged_item_fails(st_items, want_items, "IV11b")
    for x in rows:
        tag = f"IV11b {x['want']} ({x['name']})"
        si = x["intent"]
        if not si["sent"]:
            fails.append(f"{tag}: battle_intent answered {si['resp']} (want sent: an iseq)")
            continue
        ld = x["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != x["want"]:
            fails.append(f"{tag}: client lastDeny {x['lastDeny']} (want {{iseq {si['iseq']}, reason {x['want']}}})")
        w0, w1 = x["invLastWarning"]
        if w1 != TEXT_DENY[x["want"]]:
            fails.append(f"{tag}: client invLastWarning {w0!r} -> {w1!r} (want {TEXT_DENY[x['want']]!r})")
        if x["hostSeq"][0] != x["hostSeq"][1] or x["newContexts"]:
            fails.append(f"{tag}: host lastSeqEmitted {x['hostSeq'][0]}->{x['hostSeq'][1]} newContexts="
                         f"{x['newContexts']} (want nothing executed)")
        if x["inFlight"] is not None:
            fails.append(f"{tag}: client inFlight after the deny {x['inFlight']} (want null)")
        if (x["sent"], x["denied"], x["admitted"]) != (1, 1, 0):
            fails.append(f"{tag}: client coopIntentsSent.inv_move +{x['sent']} host intentsReceived.inv_move "
                         f"denied +{x['denied']} admitted +{x['admitted']} (want +1 / +1 / +0)")
        for n, want in want_items.items():
            for m in ("host", "client"):
                got = {k: (x["items"][n][m] or {}).get(k) for k in want}
                if got != want:
                    fails.append(f"{tag}: {m} {n} {x['items'][n][m]} (want {want}: nothing executed)")
        if x["cTu"] != (C_TU_MAX, C_TU_MAX):
            fails.append(f"{tag}: C tu host/client {x['cTu']} (want {C_TU_MAX} on both)")
    if not opened:
        fails += open_fails(ev, "IV11b")
    fails += common_fails(host, client, first, {}, None, "IV11b")
    finish(fails)


# ===================== S-R rows (AMENDMENT P8-4 section 4.3, AMENDMENT P8-4c) =====================


def probes_rn(gc):
    """probes()' keys plus the S-C1 latch probes and S-R's `renames` (zeros on commit S-R.1)."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in PROBE_KEYS + RN_KEYS}


def snap_rn(host, client):
    return {"host": probes_rn(host), "client": probes_rn(client)}


def collect_rn(host, client, seq0):
    rec = collect(host, client, seq0)
    rec["host"], rec["client"] = probes_rn(host), probes_rn(client)
    return rec


def names_of(gc, uid):
    """battle_state's `name`, `_name` and `rawName` of `uid` on `gc` (S-R.1's probes, P8-4c ruling 1)."""
    u = units(gc).get(uid) or {}
    return {k: u.get(k) for k in NAME_KEYS}


def names_both(host, client, uid):
    return {"host": names_of(host, uid), "client": names_of(client, uid)}


def rn_of(p, key):
    return ((p or {}).get("renames") or {}).get(key)


def dirty_of(p, key):
    d = (p or {}).get("invHostDirty") or {}
    return (d.get("sets") or {}).get("rename") if key == "setsRename" else d.get(key)


def dnum(a, b):
    """b - a for two probe numbers (None when either is missing: the probe is absent)."""
    return (b - a) if isinstance(a, int) and isinstance(b, int) else None


def rn_view(before, rec):
    """The S-R EVIDENCE fields of one row: both machines' rename probes and counters."""
    b, a = before, rec
    return {"renames": {m: (b[m]["renames"], a[m]["renames"]) for m in ("host", "client")},
            "sentRename": (count_of(b["client"]["coopIntentsSent"], "rename"),
                           count_of(a["client"]["coopIntentsSent"], "rename")),
            "hostSetsRename": (dirty_of(b["host"], "setsRename"), dirty_of(a["host"], "setsRename")),
            "heldByGate": (dirty_of(b["host"], "heldByGate"), dirty_of(a["host"], "heldByGate")),
            "syncEvsEmitted": (b["host"]["syncEvsEmitted"], a["host"]["syncEvsEmitted"]),
            "syncEvsApplied": (b["client"]["syncEvsApplied"], a["client"]["syncEvsApplied"]),
            "lastDeny": (b["client"]["lastDeny"], a["client"]["lastDeny"]), "inFlight": a["client"]["inFlight"],
            "blocked": (b["client"]["coopLocalExecBlocked"], a["client"]["coopLocalExecBlocked"]),
            "hostSeq": (b["host"]["lastSeqEmitted"], a["host"]["lastSeqEmitted"]),
            "hostEvs": ev_tuples(rec["hev"]), "clientEvs": ev_tuples(rec["cev"]), "diff": rec["diff"],
            "desync": rec["dsc"]}


def open_name_field(gc, uid, ev):
    """P8-4c T0-R2 (F2949): battle_open_inventory <uid> on `gc`; KEY_SETTLE_S; the one visible TextEdit must sit on
    NAME_FIELD_RECT; ONE inject_input click on NAME_CLICK; KEY_SETTLE_S. Fills `ev`; returns True when the click
    was made on `uid`'s open screen."""
    r = gc.cmd({"cmd": "battle_open_inventory", "unit": uid})
    ev["open"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    v = inv_view(gc)
    ev["openView"] = {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    ev["openStack"] = stack(gc)
    if not (r.get("opened") and v.get("open") is True and v.get("top") is True and v.get("unitId") == uid):
        return False
    time.sleep(KEY_SETTLE_S)
    lw = gc.cmd({"cmd": "list_widgets"})
    ev["nameField"] = [[w.get("x"), w.get("y"), w.get("w"), w.get("h")] for w in lw.get("widgets", [])
                       if "TextEdit" in str(w.get("type")) and w.get("visible")]
    if ev["nameField"] != [list(NAME_FIELD_RECT)]:
        return False
    c = gc.cmd({"cmd": "inject_input", "kind": "click", "x": NAME_CLICK[0], "y": NAME_CLICK[1]})
    ev["click"] = {k: c.get(k) for k in ("ok", "error")}
    time.sleep(KEY_SETTLE_S)
    return bool(c.get("ok"))


def type_letters(gc, uid, letters, ev):
    """One inject_input key per letter, KEY_SETTLE_S between (T0-R2). After each key, a bounded record
    (NAME_CHANGE_S) of when `gc`'s own `name` of `uid` became the old name + the letters so far: on the host and at
    red that is vanilla's own write; at GREEN the client's own name follows the host's apply."""
    base = names_of(gc, uid).get("name") or ""
    typed, out = "", []
    for ch, sym in letters:
        typed += ch
        want = base + typed
        t0 = time.time()
        r = gc.cmd({"cmd": "inject_input", "kind": "key", "key": sym})
        got, dt = wait_until(lambda: names_of(gc, uid).get("name") == want, NAME_CHANGE_S)
        out.append({"letter": ch, "sym": sym, "ok": r.get("ok"), "ownNameAtS": dt if got else None,
                    "sinceKeyS": round(time.time() - t0, 3)})
        time.sleep(KEY_SETTLE_S)
    ev["keys"] = out
    return out


def wait_names(gc, uid, want):
    """Bounded (NAME_SYNC_S): `gc`'s name, _name and rawName of `uid` all equal `want`. Seconds, or None."""
    got, dt = wait_until(lambda: all(v == want for v in names_of(gc, uid).values()), NAME_SYNC_S)
    return dt if got else None


def names_fails(names, want, what, who="C"):
    fails = []
    for m in ("host", "client"):
        if any(names[m].get(k) != want for k in NAME_KEYS):
            fails.append(f"{what}: {m} {who} names {names[m]} (want name, _name and rawName {want!r} on both)")
    return fails


def rename_order_fails(before, rec, n, what):
    """n letters typed by the client: n `rename` orders sent (R-1) and n applied by the host (R-4)."""
    b, a = before, rec
    ds = count_of(a["client"]["coopIntentsSent"], "rename") - count_of(b["client"]["coopIntentsSent"], "rename")
    dr = dnum(rn_of(b["client"], "sent"), rn_of(a["client"], "sent"))
    da = dnum(rn_of(b["host"], "applied"), rn_of(a["host"], "applied"))
    fails = []
    if (ds, dr, da) != (n, n, n):
        fails.append(f"{what}: client coopIntentsSent.rename +{ds} renames.sent +{dr}, host renames.applied +{da} "
                     f"(want +{n} / +{n} / +{n})")
    if a["client"]["inFlight"] is not None:
        fails.append(f"{what}: client inFlight {a['client']['inFlight']} (want null: a rename is untracked, R-1)")
    return fails


def pre_fails(pre_diff):
    return [f"precondition: buckets differ before the row: {pre_diff} (want none)"] if pre_diff else []


def field_fails(ev, what, who):
    return [f"{what}: {who}'s name field was not reached (open {ev.get('open')}, view {ev.get('openView')}, stack "
            f"{ev.get('openStack')}, visible TextEdits {ev.get('nameField')} (want [{list(NAME_FIELD_RECT)}]), "
            f"click {ev.get('click')})"]


def closed_fails(ev, what, who):
    if isinstance(ev.get("close"), dict) and ev["close"]["closed"]:
        return []
    return [f"{what}: {who}'s screen did not close: {ev.get('close')}"]


def rn0_names_at_start(host, client, ctx):
    """P8-4c ruling 1 (F2948): read-only, the first row (battle start)."""
    bh, bc = battle_state(host), battle_state(client)
    uh, uc = session.units_by_id(bh), session.units_by_id(bc)
    rows = []
    for uid in sorted(set(uh) | set(uc)):
        a, b = uh.get(uid) or {}, uc.get(uid) or {}
        r = {"id": uid, "type": a.get("type") or b.get("type"),
             "soldier": [a.get("isPlayerSoldier"), b.get("isPlayerSoldier")]}
        for k in NAME_KEYS:
            r[k] = [a.get(k), b.get(k)]
        rows.append(r)
    non_soldiers = [r for r in rows if r["type"] != "SOLDIER"]
    no_soldier = [r for r in rows if r["soldier"] == [False, False]]
    evidence("RN0", {"turn": [bh.get("turn"), bc.get("turn")], "units": len(rows), "nonSoldiers": len(non_soldiers),
                     "withoutSoldier": len(no_soldier), "rows": rows})
    fails = []
    if set(uh) != set(uc):
        fails.append(f"RN0: unit ids differ: host-only {sorted(set(uh) - set(uc))} client-only "
                     f"{sorted(set(uc) - set(uh))}")
    missing = [r["id"] for r in rows if any(not isinstance(v, str) for k in ("_name", "rawName") for v in r[k])]
    if missing:
        fails.append(f"RN0: unit(s) {missing} lack battle_state `_name` / `rawName` on a machine (want both strings on "
                     f"every unit)")
    unequal = [(r["id"], k, r[k]) for r in rows for k in NAME_KEYS if r[k][0] != r[k][1]]
    if unequal:
        fails.append(f"RN0: names differ between the machines at battle start: {unequal}")
    bad = [(r["id"], r["type"], r["_name"]) for r in non_soldiers if r["_name"] != ["", ""]]
    if bad:
        fails.append(f"RN0: `_name` not empty on non-SOLDIER unit(s) {bad} (P8-4c ruling 1: STOP)")
    bad_raw = [(r["id"], r["rawName"]) for r in no_soldier if r["rawName"] != ["", ""]]
    if bad_raw:
        fails.append(f"RN0: `rawName` not empty on unit(s) without a geoscape Soldier {bad_raw}")
    if not non_soldiers:
        fails.append("precondition: no non-SOLDIER unit at battle start (the check would be vacuous)")
    finish(fails)


def rn1_client_rename(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    session.wait_host_idle(host, client, timeout=30)
    pre = diff_buckets(host, client)
    n0 = names_both(host, client, C_ID)
    want = (n0["client"]["name"] or "") + "".join(ch for ch, _ in RN_LETTERS)
    before = snap_rn(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    end = {}
    ready = open_name_field(client, C_ID, ev)
    if ready:
        type_letters(client, C_ID, RN_LETTERS, ev)
        # P8-4c ruling 3 (F2952, Q3 a): End runs the change handler (F2868) but changes no text
        e0 = probes_rn(client)
        end["before"] = {"sent": rn_of(e0, "sent"), "rename": count_of(e0["coopIntentsSent"], "rename"),
                         "names": names_of(client, C_ID)}
        r = client.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_END})
        end["key"] = {"sym": SDLK_END, "ok": r.get("ok")}
        time.sleep(END_QUIET_S)
        e1 = probes_rn(client)
        end["after"] = {"sent": rn_of(e1, "sent"), "rename": count_of(e1["coopIntentsSent"], "rename"),
                        "names": names_of(client, C_ID)}
    close_client(client, ev)
    ev["hostNamesAtS"] = wait_names(host, C_ID, want) if ready else None
    rec = collect_rn(host, client, seq0)
    n1 = names_both(host, client, C_ID)
    evidence("RN1", {"preDiff": pre, "namesBefore": n0, "namesAfter": n1, "want": want, "ui": ev, "end": end,
                     "rn": rn_view(before, rec), "notes": notes})
    fails = list(notes) + pre_fails(pre)
    if not ready:
        fails += field_fails(ev, "RN1", "the client")
    else:
        fails += rename_order_fails(before, rec, len(RN_LETTERS), "RN1")
        fails += names_fails(n1, want, "RN1")
        eb, ea = end["before"], end["after"]
        if (ea["sent"], ea["rename"]) != (eb["sent"], eb["rename"]):
            fails.append(f"RN1 End (Q3 a, F2952): client renames.sent {eb['sent']}->{ea['sent']}, "
                         f"coopIntentsSent.rename {eb['rename']}->{ea['rename']} (want unchanged: the text did not "
                         f"change)")
        if ea["names"] != eb["names"]:
            fails.append(f"RN1 End: client C names {eb['names']} -> {ea['names']} (want unchanged)")
        fails += closed_fails(ev, "RN1", "the client")
    fails += common_fails(host, client, before, {}, None, "RN1")
    finish(fails)


def rn2_host_rename(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    session.wait_host_idle(host, client, timeout=30)
    pre = diff_buckets(host, client)
    n0 = names_both(host, client, H_ID)
    want = (n0["host"]["name"] or "") + "".join(ch for ch, _ in RN_LETTERS)
    before = snap_rn(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    open_at = None
    ready = open_name_field(host, H_ID, ev)
    if ready:
        type_letters(host, H_ID, RN_LETTERS, ev)
        # sampled with the host's screen still open (draft section 2.6 RN2 GREEN)
        at = wait_names(client, H_ID, want)
        eh = probes_rn(host)
        open_at = {"clientNamesAtS": at, "hostOpen": inv_view(host).get("open"), "hostStack": stack(host),
                   "names": names_both(host, client, H_ID), "hostSetsRename": dirty_of(eh, "setsRename"),
                   "syncEvsEmitted": eh.get("syncEvsEmitted")}
    close_client(host, ev)
    rec = collect_rn(host, client, seq0)
    n1 = names_both(host, client, H_ID)
    evidence("RN2", {"preDiff": pre, "namesBefore": n0, "namesAfter": n1, "want": want, "ui": ev,
                     "whileOpen": open_at, "rn": rn_view(before, rec), "notes": notes})
    fails = list(notes) + pre_fails(pre)
    if not ready:
        fails += field_fails(ev, "RN2", "the host")
    else:
        slow = [k for k in ev["keys"] if k["ownNameAtS"] is None]
        if slow:
            fails.append(f"precondition (RN2): the host's own H name did not take the letter(s) {slow} within "
                         f"{NAME_CHANGE_S} s (the T0-R2 typing recipe)")
        ds = dnum(dirty_of(before["host"], "setsRename"), dirty_of(rec["host"], "setsRename"))
        if ds != len(RN_LETTERS):
            fails.append(f"RN2: host invHostDirty.sets.rename +{ds} (want +{len(RN_LETTERS)})")
        dsync = dnum(before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"])
        if dsync is None or dsync < 1:
            fails.append(f"RN2: host syncEvsEmitted +{dsync} (want +>= 1)")
        if open_at["clientNamesAtS"] is None or open_at["hostOpen"] is not True:
            fails.append(f"RN2: the client's H names {open_at['names']['client']} with the host's screen open "
                         f"{open_at['hostOpen']} (want {want!r}, the host's, within {NAME_SYNC_S} s while it is open)")
        fails += names_fails(n1, want, "RN2", "H")
        fails += closed_fails(ev, "RN2", "the host")
    fails += common_fails(host, client, before, {}, None, "RN2")
    finish(fails)


def rn3_forged_rename(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    session.wait_host_idle(host, client, timeout=30)
    pre = diff_buckets(host, client)
    n0 = names_both(host, client, H_ID)
    before = snap_rn(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    req = {"cmd": "battle_intent", "kind": "rename", "actor": H_ID, "name": RN3_NAME}
    r = client.cmd(dict(req))
    iseq = r.get("iseq") if r.get("ok") else None
    si = {"resp": r, "sent": bool(iseq), "iseq": iseq, "deny": None}
    if iseq:
        def denied():
            ld = event_state(client).get("lastDeny") or {}
            return ld if ld.get("iseq") == iseq else None
        got, dt = wait_until(denied, ANSWER_TIMEOUT_S, 0.1)
        si["deny"], si["waited"] = got, dt
        if not got:
            notes.append(f"no deny for iseq {iseq} in {ANSWER_TIMEOUT_S} s")
    rec = collect_rn(host, client, seq0)
    n1 = names_both(host, client, H_ID)
    evidence("RN3", {"preDiff": pre, "req": req, "intent": si, "namesBefore": n0, "namesAfter": n1,
                     "rn": rn_view(before, rec), "leftover": leftover, "notes": notes})
    fails = list(notes) + pre_fails(pre)
    if not si["sent"]:
        fails.append(f"RN3: battle_intent answered {r} (want sent: an iseq)")
    else:
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("iseq") != iseq or ld.get("reason") != "not_your_unit":
            fails.append(f"RN3: client lastDeny {rec['client']['lastDeny']} (want {{iseq {iseq}, reason "
                         f"not_your_unit}})")
        if rec["client"]["inFlight"] is not None:
            fails.append(f"RN3: client inFlight {rec['client']['inFlight']} (want null)")
    for m in ("host", "client"):
        if n1[m] != n0[m]:
            fails.append(f"RN3: {m} H names {n0[m]} -> {n1[m]} (want unchanged)")
    da = dnum(rn_of(before["host"], "applied"), rn_of(rec["host"], "applied"))
    if da != 0:
        fails.append(f"RN3: host renames.applied +{da} (want +0)")
    fails += common_fails(host, client, before, {}, None, "RN3")
    finish(fails)


def rn4_rename_in_window(host, client, ctx):
    # Imported here: test_w2_inventory_held imports this module (its T0-4 fire helpers, P8-3b T0-4 row).
    import test_w2_inventory_held as held
    notes = []
    leftover = ensure_closed(client, notes)
    ws = held.fire_setup(host, client)
    st = restage(host, client, "RN4", "K0")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    n0 = names_both(host, client, C_ID)
    want = (n0["client"]["name"] or "") + "".join(ch for ch, _ in RN4_LETTERS)
    before = snap_rn(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    win = {}
    ready = open_name_field(client, C_ID, ev)
    if ready:
        t_cue = held.fire_and_cue(host, client, win)
        if t_cue:
            ch, sym = RN4_LETTERS[0]
            r = client.cmd({"cmd": "inject_input", "kind": "key", "key": sym})
            t_key = time.time()
            win["key"] = {"letter": ch, "sym": sym, "ok": r.get("ok"), "afterCueMs": held.ms_since(t_cue)}
            samples, applied_at = [], None
            while time.time() - t_key < NAME_CHANGE_S:
                eh = event_state(host)
                s = {"t": round(time.time() - t_key, 3), "applied": rn_of(eh, "applied"),
                     "hostBusy": eh.get("busyOwnerSeat"),
                     "pending": battle_state(client).get("coopPendingIntent")}
                samples.append(s)
                if dnum(rn_of(before["host"], "applied"), s["applied"]) == 1:
                    s["hostNames"] = names_of(host, C_ID)
                    applied_at = s
                    break
                time.sleep(POLL_S)
            win["samples"] = len(samples)
            win["firstSample"], win["lastSample"] = samples[0], samples[-1]
            win["appliedAt"] = applied_at
            win["pendingSeen"] = [s for s in samples if s["pending"] is not None]
        win["orderWait"] = wait_order(host, client, notes)
        win["endPending"] = battle_state(client).get("coopPendingIntent")
    close_client(client, ev)
    ev["hostNamesAtS"] = wait_names(host, C_ID, want) if ready else None
    rec = collect_rn(host, client, seq0)
    n1 = names_both(host, client, C_ID)
    evidence("RN4", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "namesBefore": n0, "namesAfter": n1,
                     "want": want, "ui": ev, "window": win, "rn": rn_view(before, rec), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not ready:
        fails += field_fails(ev, "RN4", "the client")
    else:
        fails += held.fire_fails(win, "RN4")
        if not win.get("key"):
            fails.append("precondition (RN4): no letter typed (no client `shot` cue)")
        else:
            fails += rename_order_fails(before, rec, len(RN4_LETTERS), "RN4")
            at = win.get("appliedAt")
            if not at or at.get("hostBusy") in (None, -1):
                fails.append(f"RN4: host renames.applied +1 not seen while the host's shot ran (at {at}; last sample "
                             f"{win.get('lastSample')}; want +1 within {NAME_CHANGE_S} s of the key with host "
                             f"busyOwnerSeat != -1: a rename never waits, R-M2)")
            dsync = dnum(before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"])
            if dsync != 0:
                fails.append(f"RN4: host syncEvsEmitted +{dsync} over the row (want +0: the name rides the shot's evs)")
            dg = dnum(dirty_of(before["host"], "heldByGate"), dirty_of(rec["host"], "heldByGate"))
            if dg is None or dg <= 0:
                fails.append(f"RN4: host invHostDirty.heldByGate +{dg} (want +> 0: the latch held by the shot's "
                             f"context)")
            if win.get("pendingSeen") or win.get("endPending") is not None:
                fails.append(f"RN4: client coopPendingIntent {win.get('pendingSeen')} / at the end "
                             f"{win.get('endPending')} (want null throughout: a rename is never held)")
        fails += names_fails(n1, want, "RN4")
        fails += closed_fails(ev, "RN4", "the client")
    fails += common_fails(host, client, before, {}, None, "RN4")
    finish(fails)


SCENARIOS = (("RN0", rn0_names_at_start),   # S-R (P8-4c ruling 1): at battle start, before every other row
             ("IV1", iv1_open_look), ("IV2", iv2_pickup_local), ("IV3", iv3_grenade_to_hand),
             ("IV4", iv4_ground_to_belt), ("IV5", iv5_hand_to_ground), ("IV11", iv11_host_denies),
             ("IV12", iv12_local_tu_refusal), ("IV13", iv13_real_ui_deny),
             # S-B (section 9)
             ("IV6", iv6_load), ("IV7", iv7_shift_unload), ("IV8", iv8_ctrl_autoplace),
             ("IV9", iv9_unload_unprime), ("IV10", iv10_paperdoll), ("IV11b", iv11b_load_unload_denies),
             # S-R (AMENDMENT P8-4 section 4.3; the draft section 2.6)
             ("RN1", rn1_client_rename), ("RN2", rn2_host_rename), ("RN3", rn3_forged_rename),
             ("RN4", rn4_rename_in_window))


# ===================== bring-up =====================


def n31(gc):
    """N31 = F1950: every on-tile item holds STR_GROUND (arrangeGround writes it on open)."""
    return sorted((i, it.get("slot")) for i, it in items_by_id(gc).items()
                  if it.get("onTile") and it.get("slot") != GROUND)


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p8-sa")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("invLocalWrites"), int) and isinstance(es.get("invLastWarning"), str)
                and isinstance(es.get("invGuard"), dict)), (
            f"{gc.name} event_state lacks the W2-P8 probes: invLocalWrites={es.get('invLocalWrites')!r} "
            f"invLastWarning={es.get('invLastWarning')!r} invGuard={es.get('invGuard')!r}")
        assert gc.cmd({"cmd": "inventory_view"}).get("ok"), f"{gc.name}: inventory_view is not a known command"
    bad = {gc.name: n31(gc) for gc in (host, client)}
    assert not bad["host"] and not bad["client"], f"N31 (F1950): on-tile items not in STR_GROUND: {bad}"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ub = session.units_by_id(hs)
    print(f"[w2p8-sa] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={seated_uids} H={H_ID} "
          f"pinned={len(pinned)} C={unit_view(ub.get(C_ID))} turnMode host/client="
          f"{event_state(host).get('turnMode')}/{event_state(client).get('turnMode')} "
          f"invGuard client={event_state(client).get('invGuard')}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49910, make_user_dir("w2p8_inventory_host", options=OPTS))
    client = GameClient("client", 49911, make_user_dir("w2p8_inventory_client", options=OPTS))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p8-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_inventory: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
