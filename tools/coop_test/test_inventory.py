"""The second player opens its own soldier's inventory in battle and moves, loads and
unloads items; the host checks and performs every placement.

The screen opens on the client for a soldier its seat commands. Picking an item up is
local (it rides the cursor only). Every placement is an `inv_move` intent (op move)
that the host admits with vanilla's own checks and performs with vanilla's own effect
and time unit cost, inside an `intent` action context ending in one bt_action_end. The
client writes no hashed state: the backstop count `invLocalWrites` stays 0 and the
`invGuard` probe names the decision each inventory execution point took.

Rows (ONE boot; each row ONE run, in this order; every row first restages C on its
own measured tile: tele_both(C, tile, 2), strip_both(C), the row's kit through
client-first test-command pairs with the ids read from the replies, C's TU to max):
  open_and_look: TAB-select C on the client, the INVENTORY key (keyBattleInventory
      from the client's own options.cfg), then the key again. Passes: InventoryState
      on the client only (inventory_view {open, top, unitId C}), nothing sent, every
      bucket EQUAL while it is open and after the second key closes it. When broken
      the client banner reads "Only the host can open the inventory" (read within
      0.5 s of the press) and no InventoryState opens.
  pickup_is_local: open (battle_open_inventory C), inventory_click STR_BELT (1,0),
      then a right-click: selectedItem = the grenade, then -1; nothing sent; EQUAL
      with the item on the cursor and after.
  grenade_to_hand: grenade belt (1,0) -> STR_LEFT_HAND with the in-flight window:
      host defer_intents {ms 2000, count 1} before the drop. Inside the window:
      client inFlight.kind inv_move, selectedItem = the grenade, the grenade still
      STR_BELT (1,0) owner C on both, C's TU unchanged on both, EQUAL; a second drop
      click -> invGuard.last.decision "inflight" and coopIntentsSent.inv_move
      unchanged. After the answer: admitted, grenade STR_LEFT_HAND owner C on both,
      C TU 64 - 4 on both.
  ground_to_belt: the ground rifle clip (its client `ground` cell) -> STR_BELT
      (2,0): admitted, clip owner C, off the tile, (2,0) on both; C TU 64 - 12.
  hand_to_ground: rifle RH + grenade LH on an empty tile; grenade LH -> ground cell
      (0,0): admitted, grenade on C's tile, owner -1, STR_GROUND, on both; C TU
      64 - 2.
  host_denies_moves: host denies, move ops (test command, screen open):
      battle_intent kind inv_move with tuBasisOverride 99 -> cost_changed; H's
      grenade -> item_missing; actor H -> not_your_unit; grenade -> belt (0,0)
      holding the clip -> invalid_target (silent: invLastWarning unchanged);
      set_tu_both(C, 1) and belt -> LH basis 4 -> no_tu. Each: lastDeny {iseq,
      reason}, the exact rendered text on invLastWarning, nothing executed. When
      broken every order is "not sent" (sendClientIntent drops the unknown kind).
  local_tu_refusal: set_tu_both(C, 1); a real drop belt (1,0) -> LH: invGuard.last
      {site drop, op move, decision vanilla_refused}, nothing sent, the grenade
      still on the cursor and in STR_BELT (1,0) on both, TU 1 on both; the
      right-click returns it (selectedItem -1); EQUAL.
  real_ui_deny: real-UI host deny: host defer_intents {ms 2000, count 1}; the
      client drops the grenade belt (1,0) -> LH; inside the window
      set_tu_both(C, 1); the answer is no_tu: selectedItem -1, the grenade STR_BELT
      (1,0) owner C on both, invLastWarning "Not Enough Time Units!", C TU 1 on
      both.
  When the client cannot open the screen: open_and_look fails on the refusal;
  pickup_is_local, grenade_to_hand, ground_to_belt, hand_to_ground,
  local_tu_refusal and real_ui_deny at their open step; host_denies_moves on
  "battle_intent: not sent" (its open step also fails and is recorded).

Load / unload rows (run after real_ui_deny; each on its own measured tile with the kit
a host-vanilla run of the same op used; the expectations are that run's outcome,
baked here, as there is no live host twin):
  load_rifle: rifle (empty) RH, rifle clip belt (0,0); pick the clip, drop it on the
      rifle. Passes: admitted (invGuard.last {site load, op load, decision sent}),
      rifle ammo [clip, r, r, r], the clip owner -1 slot "" off the tile, on both;
      C TU 64 - 15; the cursor empty after the answer.
  shift_unload: rifle RH loaded, LH free; a Shift+click on the rifle. Passes:
      admitted (site unload, op unload), the clip in STR_LEFT_HAND owner C, rifle
      ammo [r, r, r], on both; C TU 64 - 8.
  ctrl_autoplace: rifle RH, a grenade on the tile; a Ctrl+click on the grenade's
      ground cell. Passes: admitted (site ctrl_fit, op move), the grenade in
      STR_BELT (0,0) owner C, on both; C TU 64 - 12.
  unload_unprime: rifle RH, a primed grenade (fuse 0) belt (3,0), LH free; pick the
      grenade, the UNLOAD button. Passes: admitted (site unload, op unload), fuse -1
      and the grenade in STR_LEFT_HAND owner C, on both; C TU 64 - 20
      (max(1, floor(base TU x 25 / 100)) + 4 on C's run-time base TU, asserted
      64); the cursor empty after the answer.
  paperdoll_drop: (boot option on) grenade belt (1,0); pick it, click the
      paperdoll. Passes: admitted (site paperdoll, op move), the grenade on C's
      tile, owner -1, STR_GROUND, on both; C TU 64 - 6; the cursor empty.
  host_denies_load_unload: host denies, load/unload ops (test command, screen
      open): belt_and_ground plus a grenade in STR_LEFT_HAND and a loaded rifle in
      STR_BACK_PACK (0,0). The pistol clip -> the empty RH rifle: wrong_ammo "Wrong
      Ammunition for this Weapon!"; the belt clip -> the loaded backpack rifle,
      swap false: already_loaded "Weapon is already loaded!"; unload the backpack
      rifle with both hands full: one_hand_empty "At least one hand must be empty!"
      (vanilla counts the unloaded weapon's own hand as free, Inventory.cpp
      :1365-:1389, so the weapon sits outside the hands); unload the empty RH
      rifle: no_ammo_loaded "No Ammunition Loaded!". Each: lastDeny {iseq, reason},
      the exact text on invLastWarning, nothing executed.
  When the client refuses load and unload itself (invGuard.last {site <the row's>,
  decision `interim`}): load_rifle to paperdoll_drop fail with nothing sent, items
  and TU unchanged on both and every bucket EQUAL, and the host answers
  host_denies_load_unload with `invalid_target`; the move rows still pass.

Rename rows (an in-battle rename is an order the host applies, and both players see
it). names_at_start runs FIRST (at battle start); client_rename to rename_in_window
run after host_denies_load_unload, in this order. Only rename_in_window stages
(typing needs no kit; C and H stay where the earlier rows left them). The typing
recipe: battle_open_inventory <unit>; 0.3 s; ONE inject_input click at (266, 29) (the
name TextEdit (28,6,210,17) centre x 2); 0.3 s; each letter one inject_input key,
0.3 s between; the screen closes only through battle_close_inventory (ESC or the
INVENTORY key with the field focused blanks the name).
  names_at_start: battle_state units' `_name` (the unit's own stored name) and
      `rawName` (its geoscape Soldier's raw name, "" without one) on both machines.
      Every unit's `name`, `_name` and `rawName` equal on both, `_name` empty for
      every non-SOLDIER unit, `rawName` empty for every unit without a Soldier.
      This row also passes without the rename order. A non-empty `_name` on a
      non-soldier is a product failure, never a reason to change the fixture.
  client_rename: the client renames C: opens C's inventory, clicks the name field,
      types "xy", then End (a key that changes nothing), closes. Passes:
      coopIntentsSent.rename +2, client renames.sent +2 and unchanged by End, host
      renames.applied +2, C's name, _name and rawName = the old name + "xy" on
      both, client inFlight null; EQUAL. When broken: client
      coopIntentsSent.rename +0, C's name changed on the client only.
  host_rename: the host renames H the same way on its own screen. Passes: host
      invHostDirty.sets.rename +2, host syncEvsEmitted +>= 1, the client's H names
      = the host's (the old name + "xy") while the host's screen is still open;
      EQUAL. When broken the client's H name is unchanged.
  forged_rename: client battle_intent {kind rename, actor H, name "x"}. Passes:
      client lastDeny {iseq, reason not_your_unit}, H's names unchanged on both,
      host renames.applied +0; EQUAL. When broken it is not sent
      (sendClientIntent drops the unknown kind).
  rename_in_window: a rename never waits for a host shot to end (the window
      test_inventory_held.py measured: the host's snap shot at fire dial 1; C with
      kit belt_and_ground on (2,33,0)): the client clicks C's name field before
      the fire and types "z" on its first `shot` cue. Passes: host
      renames.applied +1 while the host's shot still runs (host busyOwnerSeat
      != -1 at the apply), host syncEvsEmitted +0 over the row and
      invHostDirty.heldByGate +> 0 (the name rode the shot's evs), client
      coopPendingIntent null at every sample (never held), C's names = the old
      name + "z" on both; EQUAL. When broken: as client_rename.
  Without the rename order, client_rename to rename_in_window fail; every other row
  passes.

Common asserts, every row (after wait_host_idle): hash_now {full:true} every bucket
EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and host 0;
client invLocalWrites 0; host inventory_view.open false; client invGuard as the row
names it (counts delta and `last`). An ADMITTED placement also: host closedContexts
gains exactly one {origin intent, kind inv_move, actorId C}; that actionId's host evs
are exactly [bt_action_end] and every one of them is in the client's log with the
same seq, kind and actionId; the only other host ev allowed since the drop is one
`reveal` with actionId 0; client coopIntentsSent.inv_move +1; host
intentsReceived.inv_move.admitted +1; client lastAftermath {actionId, kind inv_move};
client inFlight null and intentTimeouts unchanged; client selectedItem -1; the moved
item's fields and C's TU equal on both and equal to the measured host-vanilla value.
A REFUSED placement: nothing sent (client coopIntentsSent unchanged, inFlight null,
host lastSeqEmitted and intentsReceived unchanged) and state unchanged on both.

Measured constants: the row tiles (two runs identical), C's max TU 64, the costs
belt->LH 4, ground clip->belt 12, LH->ground 2, load 15, Shift-unload 8, Ctrl
auto-place 12, paperdoll 6 (measured on H; slot/item costs, unit-independent),
unload_unprime's unprime 20 on C, each moved item's outcome (from a host-vanilla run
of each op, ids substituted), the texts (en-US). The boot is the roster-pinned terror
boot of test_host_combat.py with `oxceInventoryDropItemOverPaperdoll: true` on both.
Every test-command pair goes to the CLIENT first. Item ids are read at run time from
the command replies, never baked.

Each row prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its
conditions are checked; main() runs every row even after an earlier one failed and
prints "PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that runs
out is recorded in the EVIDENCE line and fails the row. one run is
the result; no skip path, no second boot. Exit 0 only when every row passes, 2
otherwise (a bring-up failure is also 2). run in the foreground to
completion.

Run:  python tools/coop_test/test_inventory.py
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
from test_seat_pacing import tab_select
from test_delta_core import diff_buckets, desync_record, short, both, tele_both
from test_delta_items import items_by_id, unit_view
from test_host_combat import bring_up_lobby_roster_pinned, evs_since, ev_tuples
from test_client_items import strip_both
from test_client_shoot import set_tu_both

# ----- bring-up (the roster-pinned terror boot) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1 (measured)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
PORT = "48741"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
OPTS = {"oxceInventoryDropItemOverPaperdoll": True}   # the boot option on both
TU_MAX = 255                      # battle_set_unit_state tu: clamped to the unit's max TU
C_TU_MAX = 64                     # measured: "Max TU C 64"

# ----- row tiles (measured, all z 0; one per row) and H's staging tile -----
ROW_TILE = {"open_and_look": (0, 33, 0), "pickup_is_local": (0, 34, 0), "grenade_to_hand": (49, 25, 0),
            "ground_to_belt": (1, 33, 0), "hand_to_ground": (49, 24, 0), "host_denies_moves": (3, 32, 0),
            "local_tu_refusal": (49, 23, 0), "real_ui_deny": (49, 26, 0),
            # load / unload rows
            "load_rifle": (0, 32, 0), "shift_unload": (1, 32, 0), "ctrl_autoplace": (0, 35, 0),
            "unload_unprime": (2, 32, 0), "paperdoll_drop": (48, 25, 0), "host_denies_load_unload": (1, 34, 0),
            # rename_in_window: the tile test_inventory_held.py measures its host-shot window on
            "rename_in_window": (2, 33, 0)}
STAGE_H = (48, 24, 0)             # measured
ROW_DIR = 2                       # tele_both(C, <row tile>, 2)

# ----- host-vanilla costs, measured on H -----
TU_BELT_TO_HAND = 4               # belt (1,0) -> LH
TU_GROUND_TO_BELT = 12            # ground rifle clip -> belt (2,0)
TU_HAND_TO_GROUND = 2             # LH -> ground
# load / unload rows, measured on H: "load 15; Shift-unload 8 (clip to LH); unprime + UNLOAD 18 = max(1, floor(58 x 25
# / 100)) 14 + 4 (BattleUnit.cpp:2232); Ctrl auto-place 12 (belt (0,0)); paperdoll drop 6"
TU_LOAD = 15                      # clip belt (0,0) -> the rifle in RH (load_rifle)
TU_SHIFT_UNLOAD = 8               # Shift+click the loaded rifle in RH, LH free: the clip -> LH (shift_unload)
TU_CTRL_FIT = 12                  # Ctrl+click the ground grenade -> belt (0,0) (ctrl_autoplace)
TU_PAPERDOLL = 6                  # grenade belt (1,0) + the paperdoll -> ground (paperdoll_drop)
UNPRIME_PCT = 25                  # the grenade's unprime cost, a % of the unit's base TU
TU_UNPRIME_TO_HAND = 4            # + the move belt (3,0) -> the free LH
TU_UNPRIME_C = 20                 # max(1, floor(64 x 25 / 100)) + 4 on C (unload_unprime): the % is of C's own base TU

# ----- the belt_and_ground kit -----
RIFLE, RIFLE_CLIP, PISTOL_CLIP, GRENADE = "STR_RIFLE", "STR_RIFLE_CLIP", "STR_PISTOL_CLIP", "STR_GRENADE"
BELT, LH, RH, GROUND = "STR_BELT", "STR_LEFT_HAND", "STR_RIGHT_HAND", "STR_GROUND"
BACK_PACK = "STR_BACK_PACK"

# ----- texts (bin/common + xcom1 en-US; exact text, never non-emptiness) -----
TEXT_HOST_ONLY = "Only the host can open the inventory"   # STR_COOP_INVENTORY_HOST_ONLY (shown only when broken)
TEXT_DENY = {
    "cost_changed": "Order cancelled - cost changed",        # STR_COOP_DENY_COST_CHANGED
    "item_missing": "Order cancelled - item unavailable",    # STR_COOP_DENY_ITEM_MISSING
    "not_your_unit": "Not one of your soldiers",             # STR_COOP_DENY_NOT_YOUR_UNIT
    "no_tu": "Not Enough Time Units!",                       # xcom1 STR_NOT_ENOUGH_TIME_UNITS
    # host_denies_load_unload
    "wrong_ammo": "Wrong Ammunition for this Weapon!",       # xcom1 STR_WRONG_AMMUNITION_FOR_THIS_WEAPON
    "already_loaded": "Weapon is already loaded!",           # xcom1 STR_WEAPON_IS_ALREADY_LOADED
    "one_hand_empty": "At least one hand must be empty!",    # OXCE STR_ONE_HAND_MUST_BE_EMPTY
    "no_ammo_loaded": "No Ammunition Loaded!",               # xcom1 STR_NO_AMMUNITION_LOADED
}
TU_BASIS_BAD = 99                 # "tuBasis -1" cannot be sent (-1 = recompute); pinned 99

# ----- rename rows. The measured typing recipe: "battle_open_inventory {unit}; 0.3 s settle; ONE inject_input
# {kind click, x 266, y 29} (the name TextEdit (28,6,210,17) centre x 2); 0.3 s; keys one per inject_input {kind
# key} with 0.3 s between; close with battle_close_inventory only. Each letter changes the typist's name within
# 0.101 s") -----
NAME_FIELD_RECT = (28, 6, 210, 17)  # InventoryState.cpp :114 `new TextEdit(this, 210, 17, 28, 6)` (list_widgets x,y,w,h)
NAME_CLICK = (266, 29)              # the rect's centre x 2 (the harness window is 640x400)
RN_LETTERS = (("x", 120), ("y", 121))   # the two measured letters; the inject_input key = the SDL sym
#                                         (unicode = sym < 128)
RENAME_IN_WINDOW_LETTERS = (("z", 122),)  # rename_in_window: one letter
SDLK_END = 279                      # deps/include/SDL/SDL_keysym.h; End changes no text
FORGED_NAME = "x"                   # forged_rename's name
KEY_SETTLE_S = 0.3                  # after the open, after the click, between keys
NAME_CHANGE_S = 2.0                 # measured 0.101 s per letter on the typist; a bounded record, never a condition
NAME_SYNC_S = 3.0                   # the other machine shows the typist's name within this
END_QUIET_S = 1.0                   # End's change handler runs in the key's own frame; sampled 1 s later
RN_KEYS = ("renames", "invHostDirty", "syncEvsEmitted", "syncEvsApplied")
NAME_KEYS = ("name", "_name", "rawName")

# ----- windows and waits -----
DEFER_MS = 2000                   # grenade_to_hand / real_ui_deny (as test_client_items press_while_in_flight)
POLL_S = 0.05
BANNER_READ_S = 0.5               # a refusal text is read within 0.5 s of the press
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
    startup (test_thin_client_tripwire.read_reload_key's pattern)."""
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


# ===================== staging (client first: a host-first teleport can latch a client desync) ======


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
    """C onto the row's own tile facing 2, stripped, the row's kit, TU max.
    kit "belt_and_ground": rifle (no ammo) RH, rifle clip belt (0,0), grenade belt (1,0), primed
    grenade belt (3,0) (fuse 0), a rifle clip and a pistol clip dropped on the tile.
    kit "RH_LH": rifle RH, grenade LH (hand_to_ground).
    Load / unload kits = the kit each row's measured host-vanilla run used:
    "load_rifle" rifle RH + rifle clip belt (0,0); "shift_unload" rifle RH loaded (clip in ammo slot
    0); "ctrl_autoplace" rifle RH + a grenade on the tile; "unload_unprime" rifle RH + primed grenade belt
    (3,0); "paperdoll_drop" grenade belt (1,0); "host_denies_load_unload" belt_and_ground + a grenade LH + a
    loaded rifle STR_BACK_PACK (0,0). Returns the staging record with the ids."""
    tile = ROW_TILE[row]
    rec = {"tile": tile}
    t = tele_both(host, client, C_ID, tile, ROW_DIR)
    rec["tele"] = {"to": t.get("to"), "dir": t.get("dir")}
    rec["stripped"] = strip_both(host, client, C_ID)
    ids = {}
    if kit in ("belt_and_ground", "host_denies_load_unload"):
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, C_ID, RIFLE_CLIP, BELT, 0, 0)
        ids["grenade"] = give(host, client, C_ID, GRENADE, BELT, 1, 0)
        ids["primed"] = give_primed(host, client, C_ID, 3, 0)
        ids["groundClip"] = drop(host, client, tile, RIFLE_CLIP)
        ids["groundPistolClip"] = drop(host, client, tile, PISTOL_CLIP)
        if kit == "host_denies_load_unload":
            ids["lhGrenade"] = give(host, client, C_ID, GRENADE, "left")
            ids["bpRifle"], ids["bpClip"] = give_loaded(host, client, C_ID, RIFLE, BACK_PACK, RIFLE_CLIP, 0, 0)
    elif kit == "RH_LH":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["grenade"] = give(host, client, C_ID, GRENADE, "left")
    elif kit == "load_rifle":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, C_ID, RIFLE_CLIP, BELT, 0, 0)
    elif kit == "shift_unload":
        ids["rifle"], ids["clip"] = give_loaded(host, client, C_ID, RIFLE, "right", RIFLE_CLIP)
    elif kit == "ctrl_autoplace":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["grenade"] = drop(host, client, tile, GRENADE)
    elif kit == "unload_unprime":
        ids["rifle"] = give(host, client, C_ID, RIFLE, "right")
        ids["primed"] = give_primed(host, client, C_ID, 3, 0)
    elif kit == "paperdoll_drop":
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
        fails.append(f"precondition: C's TU after the staging {rec['tu']} (want {C_TU_MAX})")
    return fails


# ===================== the client's inventory =====================


def open_client(client, ev):
    """battle_open_inventory C on the client (the REAL btnInventoryClick). Fills `ev`;
    returns True when the screen is open on the client, on C, on top."""
    r = client.cmd({"cmd": "battle_open_inventory", "unit": C_ID})
    ev["open"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    ev["openBanner"] = banner(client)          # read right after the press
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
    """The common asserts of every row (module docstring), after wait_host_idle."""
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
        fails.append(f"{what}: client invLocalWrites={pc['invLocalWrites']} (want 0: the backstop refused a "
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
                     f"with actionId 0)")
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


def open_and_look(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "open_and_look", "belt_and_ground")
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
    evidence("open_and_look", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                     "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not ev["tab"]:
        fails.append(f"precondition: TAB never selected C on the client (selectedId "
                     f"{battle_state(client).get('selectedId')})")
    if not opened:
        fails.append(f"open_and_look: the client's INVENTORY key (key {key}) opened no InventoryState (client stack "
                     f"{ev['firstKey']['stack']}, client banner within {BANNER_READ_S} s "
                     f"{ev['bannerWithin05s']['text']!r})")
    else:
        v = ev["firstKey"]["view"]
        if not (v.get("top") is True and v.get("unitId") == C_ID and v.get("selectedItem") == -1):
            fails.append(f"open_and_look: client inventory_view after the key {v} (want open, top, unitId {C_ID}, "
                         f"selectedItem -1)")
        if ev["firstKey"]["hostView"].get("open") is not False:
            fails.append(f"open_and_look: host inventory_view {ev['firstKey']['hostView']} (want open false: client "
                         f"only)")
        if open_diff:
            fails.append(f"open_and_look: buckets differ with the client's screen open: {open_diff} (want none)")
        if not ev["secondKey"]["closed"]:
            fails.append(f"open_and_look: the second INVENTORY key did not close the client's screen "
                         f"(stack {ev['secondKey']['stack']})")
    fails += nothing_sent_fails(before, rec, "open_and_look")
    fails += common_fails(host, client, before, {}, None, "open_and_look")
    finish(fails)


def pickup_is_local(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "pickup_is_local", "belt_and_ground")
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
    evidence("pickup_is_local", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                     "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "pickup_is_local")
    else:
        if not picked:
            fails.append(f"pickup_is_local: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor "
                         f"(want the grenade {g}; click {ev['pick']})")
        if cursor_diff:
            fails.append(f"pickup_is_local: buckets differ with the grenade on the cursor: {cursor_diff} (want none)")
        if not returned:
            fails.append(f"pickup_is_local: the right-click left {ev['rightClick'].get('cursor')} on the cursor (want "
                         f"-1)")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"pickup_is_local: the client's screen did not close: {ev.get('close')}")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                            "pickup_is_local")
    fails += tu_fails(rec, C_TU_MAX, "pickup_is_local")
    fails += nothing_sent_fails(before, rec, "pickup_is_local")
    fails += common_fails(host, client, before, {}, None, "pickup_is_local")
    finish(fails)


def grenade_to_hand(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "grenade_to_hand", "belt_and_ground")
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
            # the in-flight window: sampled while the host holds the order
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
    evidence("grenade_to_hand",
             {"staging": st, "stagedDiff": staged, "ui": ev, "defer": dr, "disarm": disarm, "window": win,
                     "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "grenade_to_hand")
        fails += nothing_sent_fails(before, rec, "grenade_to_hand")
        fails += common_fails(host, client, before, {}, None, "grenade_to_hand")
        finish(fails)
    if not picked:
        fails.append(f"grenade_to_hand: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want "
                     f"{g})")
    else:
        # inside the window
        fl = win.get("inFlight") or {}
        if win["sent"]["state"] != "sent" or fl.get("kind") != "inv_move":
            fails.append(f"grenade_to_hand window: the drop on STR_LEFT_HAND is not in flight as inv_move (sent "
                         f"{win['sent']}, client inFlight {win.get('inFlight')})")
        if win.get("cursor") != g:
            fails.append(f"grenade_to_hand window: client selectedItem {win.get('cursor')} while in flight (want {g})")
        want_belt = {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
        for m in ("host", "client"):
            got = {k: (win["grenade"][m] or {}).get(k) for k in want_belt}
            if got != want_belt:
                fails.append(f"grenade_to_hand window: {m} grenade {win['grenade'][m]} while in flight (want "
                             f"{want_belt})")
        if win["tu"] != {"host": C_TU_MAX, "client": C_TU_MAX}:
            fails.append(f"grenade_to_hand window: C tu {win['tu']} while in flight (want {C_TU_MAX} on both)")
        if win.get("diff"):
            fails.append(f"grenade_to_hand window: buckets differ while the order is held: {win['diff']} (want none)")
        a2 = win.get("afterSecond") or {}
        if (a2.get("invGuardLast") or {}).get("decision") != "inflight":
            fails.append(f"grenade_to_hand window: client invGuard.last after the second drop {a2.get('invGuardLast')} "
                         f"(want decision inflight)")
        if count_of(a2.get("sent"), "inv_move") != count_of(win.get("sentAt"), "inv_move"):
            fails.append(f"grenade_to_hand window: coopIntentsSent.inv_move {win.get('sentAt')} -> {a2.get('sent')} "
                         f"after the second drop (want unchanged)")
        if not a2.get("inFlight"):
            fails.append(f"precondition: the second drop did not land while the first was in flight "
                         f"(window {win})")
        # after the answer
        f, cx = admitted_fails(before, rec, "grenade_to_hand")
        fails += f
        fails += item_fails(rec, g, {"owner": C_ID, "slot": LH, "onTile": False}, "grenade_to_hand")
        fails += tu_fails(rec, C_TU_MAX - TU_BELT_TO_HAND, "grenade_to_hand")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"grenade_to_hand: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1, "inflight": 1},
                          {"site": "drop", "op": "move", "decision": "inflight", "itemId": g, "actorId": C_ID},
                          "grenade_to_hand")
    finish(fails)


def ground_to_belt(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "ground_to_belt", "belt_and_ground")
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
    evidence("ground_to_belt", {"staging": st, "stagedDiff": staged, "ui": ev, "clipCell": cell,
                     "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "ground_to_belt")
        fails += nothing_sent_fails(before, rec, "ground_to_belt")
        fails += common_fails(host, client, before, {}, None, "ground_to_belt")
        finish(fails)
    if cell is None:
        fails.append(f"precondition: the ground rifle clip {clip} is not in the client's inventory_view.ground "
                     f"{ev.get('ground')}")
    elif not picked:
        fails.append(f"ground_to_belt: the click on the clip's ground cell {cell} put {ev['pick'].get('cursor')} on "
                     f"the cursor (want {clip})")
    else:
        f, cx = admitted_fails(before, rec, "ground_to_belt")
        fails += f
        fails += item_fails(rec, clip, {"owner": C_ID, "slot": BELT, "slotX": 2, "slotY": 0, "onTile": False},
                            "ground_to_belt")
        fails += tu_fails(rec, C_TU_MAX - TU_GROUND_TO_BELT, "ground_to_belt")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"ground_to_belt: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": clip, "actorId": C_ID},
                          "ground_to_belt")
    finish(fails)


def hand_to_ground(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "hand_to_ground", "RH_LH")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    tile = ROW_TILE["hand_to_ground"]
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
    evidence("hand_to_ground", {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                     "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "hand_to_ground")
        fails += nothing_sent_fails(before, rec, "hand_to_ground")
        fails += common_fails(host, client, before, {}, None, "hand_to_ground")
        finish(fails)
    if ev.get("groundBefore"):
        fails.append(f"precondition: hand_to_ground's tile {tile} holds items {ev['groundBefore']} (want an empty "
                     f"tile)")
    if not picked:
        fails.append(f"hand_to_ground: the click on STR_LEFT_HAND put {ev['pick'].get('cursor')} on the cursor (want "
                     f"{g})")
    else:
        f, cx = admitted_fails(before, rec, "hand_to_ground")
        fails += f
        fails += item_fails(rec, g, {"owner": -1, "slot": GROUND, "onTile": True, "tx": tile[0], "ty": tile[1],
                                     "tz": tile[2]}, "hand_to_ground")
        fails += tu_fails(rec, C_TU_MAX - TU_HAND_TO_GROUND, "hand_to_ground")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"hand_to_ground: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID},
                          "hand_to_ground")
    finish(fails)


def inv_req(actor, item, slot, x, y, tu_override=None):
    """battle_intent's `inv_move` request (plan {op, item, to {slot, x, y}})."""
    req = {"cmd": "battle_intent", "kind": "inv_move", "actor": actor,
           "plan": {"op": "move", "item": item, "to": {"slot": slot, "x": x, "y": y}}}
    if tu_override is not None:
        req["tuBasisOverride"] = tu_override
    return req


def send_intent(host, client, req, notes):
    """One test-command order; when sent, waits (bounded) for the host's answer: its deny
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


def host_denies_moves(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    # H's kit: H onto STAGE_H, stripped, one grenade on its belt (the item_missing order's item)
    th = tele_both(host, client, H_ID, STAGE_H, ROW_DIR)
    h_stripped = strip_both(host, client, H_ID)
    h_gren = give(host, client, H_ID, GRENADE, BELT, 1, 0)
    st = restage(host, client, "host_denies_moves", "belt_and_ground")
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
    evidence("host_denies_moves", {"staging": st, "stagedDiff": staged, "ui": ev,
                      "variants": [{k: v for k, v in r.items() if k != "req"} for r in rows],
                      "requests": [r["req"] for r in rows], "row": rec_view(first, rec, st["ids"]),
                      "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    want_items = {"grenade": {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                  "hGrenade": {"owner": H_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                  "beltClip": {"owner": C_ID, "slot": BELT, "slotX": 0, "slotY": 0, "onTile": False}}
    last_text = None
    for r in rows:
        tag = f"host_denies_moves {r['want']} ({r['name']})"
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
        fails += open_fails(ev, "host_denies_moves")
    fails += common_fails(host, client, first, {}, None, "host_denies_moves")
    finish(fails)


def local_tu_refusal(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "local_tu_refusal", "belt_and_ground")
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
    evidence("local_tu_refusal",
             {"staging": st, "stagedDiff": staged, "ui": ev, "row": rec_view(before, rec, st["ids"]),
                      "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if st["tuSet"] != 1:
        fails.append(f"precondition: C's TU {st['tuSet']} after set_tu_both 1 (want 1)")
    if not opened:
        fails += open_fails(ev, "local_tu_refusal")
        fails += nothing_sent_fails(before, rec, "local_tu_refusal")
        fails += common_fails(host, client, before, {}, None, "local_tu_refusal")
        finish(fails)
    if not picked:
        fails.append(f"local_tu_refusal: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor "
                     f"(want {g})")
    else:
        ad = ev["afterDrop"]
        if ad["cursor"] != g:
            fails.append(f"local_tu_refusal: client selectedItem {ad['cursor']} after the refused drop (want {g}: "
                         f"still selected)")
        if ev["sent"]["state"] != "quiet":
            fails.append(f"local_tu_refusal: the refused drop {ev['sent']} (want nothing sent)")
        if not returned:
            fails.append(f"local_tu_refusal: the right-click left {ev['rightClick'].get('cursor')} on the cursor (want "
                         f"-1)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                            "local_tu_refusal")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"local_tu_refusal: the client's screen did not close: {ev.get('close')}")
    fails += tu_fails(rec, 1, "local_tu_refusal")
    fails += nothing_sent_fails(before, rec, "local_tu_refusal")
    fails += common_fails(host, client, before, {"vanilla_refused": 1},
                          {"site": "drop", "op": "move", "decision": "vanilla_refused", "itemId": g,
                           "actorId": C_ID}, "local_tu_refusal")
    finish(fails)


def real_ui_deny(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "real_ui_deny", "belt_and_ground")
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
    evidence("real_ui_deny",
             {"staging": st, "stagedDiff": staged, "ui": ev, "defer": dr, "disarm": disarm, "window": win,
                      "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "real_ui_deny")
        fails += nothing_sent_fails(before, rec, "real_ui_deny")
        fails += common_fails(host, client, before, {}, None, "real_ui_deny")
        finish(fails)
    if not picked:
        fails.append(f"real_ui_deny: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want "
                     f"{g})")
    else:
        if win["sent"]["state"] != "sent" or not win.get("inFlightAfterTuSet"):
            fails.append(f"precondition: set_tu_both(C, 1) did not land inside the held order's window "
                         f"(sent {win['sent']}, inFlight after the TU command {win.get('inFlightAfterTuSet')}, "
                         f"at {win.get('tuSetAtS')} s)")
        if win["tuSet"] != 1:
            fails.append(f"real_ui_deny: C's TU {win['tuSet']} after set_tu_both 1 (want 1)")
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("reason") != "no_tu" or ld.get("iseq") != win.get("iseq"):
            fails.append(f"real_ui_deny: client lastDeny {rec['client']['lastDeny']} (want {{iseq {win.get('iseq')}, "
                         f"reason no_tu}})")
        if rec["client"]["invLastWarning"] != TEXT_DENY["no_tu"]:
            fails.append(f"real_ui_deny: client invLastWarning {rec['client']['invLastWarning']!r} "
                         f"(want {TEXT_DENY['no_tu']!r})")
        if win.get("cursor") != -1:
            fails.append(f"real_ui_deny: client selectedItem {win.get('cursor')} after the deny (want -1: the item "
                         f"returned)")
        d = count_of(rec["client"]["coopIntentsSent"], "inv_move") - count_of(before["client"]["coopIntentsSent"],
                                                                              "inv_move")
        dd = recv_of(rec["host"]["intentsReceived"], "inv_move", "denied") - recv_of(
            before["host"]["intentsReceived"], "inv_move", "denied")
        if (d, dd) != (1, 1):
            fails.append(f"real_ui_deny: client coopIntentsSent.inv_move +{d} host intentsReceived.inv_move.denied "
                         f"+{dd} (want +1 / +1)")
        new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
        if new or rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
            fails.append(f"real_ui_deny: host lastSeqEmitted {before['host']['lastSeqEmitted']}->"
                         f"{rec['host']['lastSeqEmitted']} newContexts={new} (want nothing executed)")
        if rec["client"]["inFlight"] is not None:
            fails.append(f"real_ui_deny: client inFlight after the deny {rec['client']['inFlight']} (want null)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                            "real_ui_deny")
        fails += tu_fails(rec, 1, "real_ui_deny")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"real_ui_deny: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID},
                          "real_ui_deny")
    finish(fails)


# ===================== load / unload rows =====================


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


def client_ui_row(host, client, row, do_op, what, guard, tu_spent, outcome, staged_want=None):
    """load_rifle to paperdoll_drop: one real-UI inventory op of the client on its own C.
    do_op(client, ev, ids) makes the row's clicks and returns True when its own
    precondition held (the pick landed, the cell was found). Then: up to
    SENT_WAIT_S for the order to show as sent and, when sent, the end of the order;
    the cursor, invGuard and inFlight right after; an item still on the cursor then
    goes back with ONE right-click (recorded; a client-side refusal keeps it there) and
    the screen closes. guard = (site, op, the ids key of the order's item);
    tu_spent = the measured host-vanilla cost, or cost(st) -> (cost, precondition fails) (unload_unprime);
    outcome(ids, tile) = {ids key: the item's measured host-vanilla outcome}."""
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


def load_rifle(host, client, ctx):
    """The belt clip dropped on the empty rifle in RH."""
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
    client_ui_row(host, client, "load_rifle", do_op, "load (clip belt (0,0) -> the rifle in STR_RIGHT_HAND)",
                  ("load", "load", "beltClip"), TU_LOAD, outcome, staged_want)


def shift_unload(host, client, ctx):
    """Shift+click the loaded rifle in RH with LH free."""
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
    client_ui_row(host, client, "shift_unload", do_op, "Shift+click unload of the rifle in STR_RIGHT_HAND",
                  ("unload", "unload", "rifle"), TU_SHIFT_UNLOAD, outcome, staged_want)


def ctrl_autoplace(host, client, ctx):
    """Ctrl+click the grenade on the ground: vanilla's first fitting cell."""
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
    client_ui_row(host, client, "ctrl_autoplace", do_op, "Ctrl+click auto-place of the ground grenade",
                  ("ctrl_fit", "move", "grenade"), TU_CTRL_FIT, outcome, staged_want)


def unload_unprime(host, client, ctx):
    """The primed grenade picked from belt (3,0), then the UNLOAD button, LH free
    The cost is a % of C's own base TU."""
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
        # the formula on C's run-time base TU (restage's battle_set_unit_state tu 255
        # clamps to getBaseStats()->tu, asserted 64 by staged_fails) must give the pinned 20.
        base = st["tu"]
        spent = max(1, (base * UNPRIME_PCT) // 100) + TU_UNPRIME_TO_HAND
        bad = [] if spent == TU_UNPRIME_C else [
            f"precondition: C's base TU {base} gives the unprime cost {spent} (want {TU_UNPRIME_C})"]
        return spent, bad
    client_ui_row(host, client, "unload_unprime", do_op, "UNLOAD unprime of the primed grenade",
                  ("unload", "unload", "primed"), unprime_cost, outcome, staged_want)


def paperdoll_drop(host, client, ctx):
    """The grenade picked from belt (1,0), then a click on the paperdoll with
    oxceInventoryDropItemOverPaperdoll on."""
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
    client_ui_row(host, client, "paperdoll_drop", do_op, "paperdoll drop of the grenade",
                  ("paperdoll", "move", "grenade"), TU_PAPERDOLL, outcome, staged_want)


def inv_load_req(actor, item, weapon, swap=False):
    """battle_intent's `inv_move` load (plan {op, item, weapon, swap})."""
    return {"cmd": "battle_intent", "kind": "inv_move", "actor": actor,
            "plan": {"op": "load", "item": item, "weapon": weapon, "swap": swap}}


def inv_unload_req(actor, item):
    return {"cmd": "battle_intent", "kind": "inv_move", "actor": actor, "plan": {"op": "unload", "item": item}}


def host_denies_load_unload(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    st = restage(host, client, "host_denies_load_unload", "host_denies_load_unload")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    ids = st["ids"]
    tile = ROW_TILE["host_denies_load_unload"]
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
    evidence("host_denies_load_unload", {"staging": st, "stagedDiff": staged, "stagedItems": st_items, "ui": ev,
                       "variants": [{k: v for k, v in x.items() if k != "req"} for x in rows],
                       "requests": [x["req"] for x in rows], "row": rec_view(first, rec, ids), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    fails += staged_item_fails(st_items, want_items, "host_denies_load_unload")
    for x in rows:
        tag = f"host_denies_load_unload {x['want']} ({x['name']})"
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
        fails += open_fails(ev, "host_denies_load_unload")
    fails += common_fails(host, client, first, {}, None, "host_denies_load_unload")
    finish(fails)


# ===================== rename rows =====================


def probes_rn(gc):
    """probes()' keys plus the held-inventory latch probes and the `renames` counters."""
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
    """battle_state's `name`, `_name` and `rawName` of `uid` on `gc`."""
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
    """The rename EVIDENCE fields of one row: both machines' rename probes and counters."""
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
    """The measured recipe: battle_open_inventory <uid> on `gc`; KEY_SETTLE_S; the one visible TextEdit must sit on
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
    """One inject_input key per letter, KEY_SETTLE_S between. After each key, a bounded record
    (NAME_CHANGE_S) of when `gc`'s own `name` of `uid` became the old name + the letters so far: on the host, and on
    a client without the rename order, that is vanilla's own write; otherwise the client's own name follows the
    host's apply."""
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
    """n letters typed by the client: n `rename` orders sent and n applied by the host."""
    b, a = before, rec
    ds = count_of(a["client"]["coopIntentsSent"], "rename") - count_of(b["client"]["coopIntentsSent"], "rename")
    dr = dnum(rn_of(b["client"], "sent"), rn_of(a["client"], "sent"))
    da = dnum(rn_of(b["host"], "applied"), rn_of(a["host"], "applied"))
    fails = []
    if (ds, dr, da) != (n, n, n):
        fails.append(f"{what}: client coopIntentsSent.rename +{ds} renames.sent +{dr}, host renames.applied +{da} "
                     f"(want +{n} / +{n} / +{n})")
    if a["client"]["inFlight"] is not None:
        fails.append(f"{what}: client inFlight {a['client']['inFlight']} (want null: a rename is untracked)")
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


def names_at_start(host, client, ctx):
    """Read-only, the first row (battle start)."""
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
    evidence("names_at_start",
             {"turn": [bh.get("turn"), bc.get("turn")], "units": len(rows), "nonSoldiers": len(non_soldiers),
                     "withoutSoldier": len(no_soldier), "rows": rows})
    fails = []
    if set(uh) != set(uc):
        fails.append(f"names_at_start: unit ids differ: host-only {sorted(set(uh) - set(uc))} client-only "
                     f"{sorted(set(uc) - set(uh))}")
    missing = [r["id"] for r in rows if any(not isinstance(v, str) for k in ("_name", "rawName") for v in r[k])]
    if missing:
        fails.append(f"names_at_start: unit(s) {missing} lack battle_state `_name` / `rawName` on a machine (want both "
                     f"strings on every unit)")
    unequal = [(r["id"], k, r[k]) for r in rows for k in NAME_KEYS if r[k][0] != r[k][1]]
    if unequal:
        fails.append(f"names_at_start: names differ between the machines at battle start: {unequal}")
    bad = [(r["id"], r["type"], r["_name"]) for r in non_soldiers if r["_name"] != ["", ""]]
    if bad:
        fails.append(f"names_at_start: `_name` not empty on non-SOLDIER unit(s) {bad} (a product failure, not a "
                     f"fixture problem)")
    bad_raw = [(r["id"], r["rawName"]) for r in no_soldier if r["rawName"] != ["", ""]]
    if bad_raw:
        fails.append(f"names_at_start: `rawName` not empty on unit(s) without a geoscape Soldier {bad_raw}")
    if not non_soldiers:
        fails.append("precondition: no non-SOLDIER unit at battle start (the check would be vacuous)")
    finish(fails)


def client_rename(host, client, ctx):
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
        # End runs the change handler but changes no text
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
    evidence("client_rename", {"preDiff": pre, "namesBefore": n0, "namesAfter": n1, "want": want, "ui": ev, "end": end,
                     "rn": rn_view(before, rec), "notes": notes})
    fails = list(notes) + pre_fails(pre)
    if not ready:
        fails += field_fails(ev, "client_rename", "the client")
    else:
        fails += rename_order_fails(before, rec, len(RN_LETTERS), "client_rename")
        fails += names_fails(n1, want, "client_rename")
        eb, ea = end["before"], end["after"]
        if (ea["sent"], ea["rename"]) != (eb["sent"], eb["rename"]):
            fails.append(f"client_rename End: client renames.sent {eb['sent']}->{ea['sent']}, "
                         f"coopIntentsSent.rename {eb['rename']}->{ea['rename']} (want unchanged: the text did not "
                         f"change)")
        if ea["names"] != eb["names"]:
            fails.append(f"client_rename End: client C names {eb['names']} -> {ea['names']} (want unchanged)")
        fails += closed_fails(ev, "client_rename", "the client")
    fails += common_fails(host, client, before, {}, None, "client_rename")
    finish(fails)


def host_rename(host, client, ctx):
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
        # sampled with the host's screen still open
        at = wait_names(client, H_ID, want)
        eh = probes_rn(host)
        open_at = {"clientNamesAtS": at, "hostOpen": inv_view(host).get("open"), "hostStack": stack(host),
                   "names": names_both(host, client, H_ID), "hostSetsRename": dirty_of(eh, "setsRename"),
                   "syncEvsEmitted": eh.get("syncEvsEmitted")}
    close_client(host, ev)
    rec = collect_rn(host, client, seq0)
    n1 = names_both(host, client, H_ID)
    evidence("host_rename", {"preDiff": pre, "namesBefore": n0, "namesAfter": n1, "want": want, "ui": ev,
                     "whileOpen": open_at, "rn": rn_view(before, rec), "notes": notes})
    fails = list(notes) + pre_fails(pre)
    if not ready:
        fails += field_fails(ev, "host_rename", "the host")
    else:
        slow = [k for k in ev["keys"] if k["ownNameAtS"] is None]
        if slow:
            fails.append(f"precondition (host_rename): the host's own H name did not take the letter(s) {slow} within "
                         f"{NAME_CHANGE_S} s (the measured typing recipe)")
        ds = dnum(dirty_of(before["host"], "setsRename"), dirty_of(rec["host"], "setsRename"))
        if ds != len(RN_LETTERS):
            fails.append(f"host_rename: host invHostDirty.sets.rename +{ds} (want +{len(RN_LETTERS)})")
        dsync = dnum(before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"])
        if dsync is None or dsync < 1:
            fails.append(f"host_rename: host syncEvsEmitted +{dsync} (want +>= 1)")
        if open_at["clientNamesAtS"] is None or open_at["hostOpen"] is not True:
            fails.append(f"host_rename: the client's H names {open_at['names']['client']} with the host's screen open "
                         f"{open_at['hostOpen']} (want {want!r}, the host's, within {NAME_SYNC_S} s while it is open)")
        fails += names_fails(n1, want, "host_rename", "H")
        fails += closed_fails(ev, "host_rename", "the host")
    fails += common_fails(host, client, before, {}, None, "host_rename")
    finish(fails)


def forged_rename(host, client, ctx):
    notes = []
    leftover = ensure_closed(client, notes)
    session.wait_host_idle(host, client, timeout=30)
    pre = diff_buckets(host, client)
    n0 = names_both(host, client, H_ID)
    before = snap_rn(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    req = {"cmd": "battle_intent", "kind": "rename", "actor": H_ID, "name": FORGED_NAME}
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
    evidence("forged_rename", {"preDiff": pre, "req": req, "intent": si, "namesBefore": n0, "namesAfter": n1,
                     "rn": rn_view(before, rec), "leftover": leftover, "notes": notes})
    fails = list(notes) + pre_fails(pre)
    if not si["sent"]:
        fails.append(f"forged_rename: battle_intent answered {r} (want sent: an iseq)")
    else:
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("iseq") != iseq or ld.get("reason") != "not_your_unit":
            fails.append(f"forged_rename: client lastDeny {rec['client']['lastDeny']} (want {{iseq {iseq}, reason "
                         f"not_your_unit}})")
        if rec["client"]["inFlight"] is not None:
            fails.append(f"forged_rename: client inFlight {rec['client']['inFlight']} (want null)")
    for m in ("host", "client"):
        if n1[m] != n0[m]:
            fails.append(f"forged_rename: {m} H names {n0[m]} -> {n1[m]} (want unchanged)")
    da = dnum(rn_of(before["host"], "applied"), rn_of(rec["host"], "applied"))
    if da != 0:
        fails.append(f"forged_rename: host renames.applied +{da} (want +0)")
    fails += common_fails(host, client, before, {}, None, "forged_rename")
    finish(fails)


def rename_in_window(host, client, ctx):
    # Imported here: test_inventory_held imports this module (this row uses its host-shot helpers).
    import test_inventory_held as held
    notes = []
    leftover = ensure_closed(client, notes)
    ws = held.fire_setup(host, client)
    st = restage(host, client, "rename_in_window", "belt_and_ground")
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    n0 = names_both(host, client, C_ID)
    want = (n0["client"]["name"] or "") + "".join(ch for ch, _ in RENAME_IN_WINDOW_LETTERS)
    before = snap_rn(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    win = {}
    ready = open_name_field(client, C_ID, ev)
    if ready:
        t_cue = held.fire_and_cue(host, client, win)
        if t_cue:
            ch, sym = RENAME_IN_WINDOW_LETTERS[0]
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
    evidence("rename_in_window",
             {"fireSetup": ws, "staging": st, "stagedDiff": staged, "namesBefore": n0, "namesAfter": n1,
                     "want": want, "ui": ev, "window": win, "rn": rn_view(before, rec), "notes": notes})
    fails = list(notes) + staged_fails(st, staged)
    if not ready:
        fails += field_fails(ev, "rename_in_window", "the client")
    else:
        fails += held.fire_fails(win, "rename_in_window")
        if not win.get("key"):
            fails.append("precondition (rename_in_window): no letter typed (no client `shot` cue)")
        else:
            fails += rename_order_fails(before, rec, len(RENAME_IN_WINDOW_LETTERS), "rename_in_window")
            at = win.get("appliedAt")
            if not at or at.get("hostBusy") in (None, -1):
                fails.append(f"rename_in_window: host renames.applied +1 not seen while the host's shot ran (at {at}; "
                             f"last sample "
                             f"{win.get('lastSample')}; want +1 within {NAME_CHANGE_S} s of the key with host "
                             f"busyOwnerSeat != -1: a rename never waits)")
            dsync = dnum(before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"])
            if dsync != 0:
                fails.append(f"rename_in_window: host syncEvsEmitted +{dsync} over the row (want +0: the name rides "
                             f"the shot's evs)")
            dg = dnum(dirty_of(before["host"], "heldByGate"), dirty_of(rec["host"], "heldByGate"))
            if dg is None or dg <= 0:
                fails.append(f"rename_in_window: host invHostDirty.heldByGate +{dg} (want +> 0: the latch held by the "
                             f"shot's context)")
            if win.get("pendingSeen") or win.get("endPending") is not None:
                fails.append(f"rename_in_window: client coopPendingIntent {win.get('pendingSeen')} / at the end "
                             f"{win.get('endPending')} (want null throughout: a rename is never held)")
        fails += names_fails(n1, want, "rename_in_window")
        fails += closed_fails(ev, "rename_in_window", "the client")
    fails += common_fails(host, client, before, {}, None, "rename_in_window")
    finish(fails)


SCENARIOS = (("names_at_start", names_at_start),   # at battle start, before every other row
             ("open_and_look", open_and_look), ("pickup_is_local", pickup_is_local),
             ("grenade_to_hand", grenade_to_hand),
             ("ground_to_belt", ground_to_belt), ("hand_to_ground", hand_to_ground),
             ("host_denies_moves", host_denies_moves),
             ("local_tu_refusal", local_tu_refusal), ("real_ui_deny", real_ui_deny),
             # load / unload rows
             ("load_rifle", load_rifle), ("shift_unload", shift_unload), ("ctrl_autoplace", ctrl_autoplace),
             ("unload_unprime", unload_unprime), ("paperdoll_drop", paperdoll_drop),
             ("host_denies_load_unload", host_denies_load_unload),
             # rename rows
             ("client_rename", client_rename), ("host_rename", host_rename), ("forged_rename", forged_rename),
             ("rename_in_window", rename_in_window))


# ===================== bring-up =====================


def off_ground_slots(gc):
    """On-tile items not in STR_GROUND: every on-tile item holds STR_GROUND (arrangeGround writes it on open)."""
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
    pinned = pin_ai_neutral(host, client, tag="inventory")
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
            f"{gc.name} event_state lacks the inventory probes: invLocalWrites={es.get('invLocalWrites')!r} "
            f"invLastWarning={es.get('invLastWarning')!r} invGuard={es.get('invGuard')!r}")
        assert gc.cmd({"cmd": "inventory_view"}).get("ok"), f"{gc.name}: inventory_view is not a known command"
    bad = {gc.name: off_ground_slots(gc) for gc in (host, client)}
    assert not bad["host"] and not bad["client"], f"on-tile items not in STR_GROUND: {bad}"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ub = session.units_by_id(hs)
    print(f"[inventory] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={seated_uids} H={H_ID} "
          f"pinned={len(pinned)} C={unit_view(ub.get(C_ID))} turnMode host/client="
          f"{event_state(host).get('turnMode')}/{event_state(client).get('turnMode')} "
          f"invGuard client={event_state(client).get('invGuard')}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49910, make_user_dir("inventory_host", options=OPTS))
    client = GameClient("client", 49911, make_user_dir("inventory_client", options=OPTS))
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
                print(f"[inventory] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_inventory: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
