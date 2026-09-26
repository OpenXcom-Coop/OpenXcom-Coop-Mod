"""W2-P4 S-A - test_w2_client_shoot.py: the second player's own shots become
orders the host checks and fires (spec rewrite/prompts/w2p4_client_combat_intents.md
section (f) "test_w2_client_shoot.py (S-A)", sections (b)1-5, (b)7 and (b)13, as
amended by AMENDMENT C1 (PR-Q2: K1 keeps refusing every kind S-A does not build;
PR-Q14: C16's seat is read through closedContexts), AMENDMENT C3 (D146: the
research-combined `not_researched` deny and its C16d-r row, the host-only
forget_research lever) and AMENDMENT C4 (PR-Q18: the client-side baton check
belongs to the shoot intercept; PR-Q20: the spray start stays refused at K1).

Before S-A the second player cannot fire. Its click on a target is refused at K1
(BattlescapeGame::primaryAction's targeting arm; client coopLocalExecBlocked +1,
nothing sent) and the battle_intent lever knows no `shoot` kind (the product's
unknown-kind path answers "not sent"). After S-A the click becomes a `shoot`
intent. The host admits it with vanilla's own checks or denies it with a reason,
runs vanilla's UnitTurnBState + ProjectileFlyBState under an `intent` action
context that ends in one bt_action_end, and the ordering client shows the answer.
Eight scenarios, ONE boot, in this order:

  C16    real-UI snap kill. C gets a rifle + clip, C -> C_TILE facing C16_C_DIR
         (one octant off A), A -> A_TILE facing A_DIR with health 1, C TU max,
         C firing 120 (all on BOTH). Client: TAB-select C, the right-hand box,
         key 50 (SNAP), HOME, host set_seed SEED_C16, one left click on A's tile.
         RED: refused at K1 (client coopLocalExecBlocked +1, nothing sent, A
         alive). GREEN: host closedContexts gains {origin intent, kind shoot,
         actorId C} (C's seat is 1: PR-Q14) whose evs are exactly shot -> hit ->
         death -> corpse -> bt_action_end; A dead and one corpse with the same id
         and tile on both; C TU C16_TU_AFTER and the clip C16_CLIP_AFTER on both;
         the client is back in aim mode (cursorType 2) with lastAftermath
         {actionId, kind shoot}.
  C16h   the halt. C's TU = the snap cost SNAP_TU (both); C faces dir 0 (the
         turn C16's shot produced); real-UI snap at the floor tile C16H_TARGET,
         two octants east. The pre-shot turn spends 1 TU per octant, so vanilla's
         own haveTU check (ProjectileFlyBState.cpp:90) refuses the shot (F1109).
         RED: refused at K1. GREEN: {intent, shoot, C} with no `shot` ev and one
         bt_action_end; lastActionHalt {actionId, halted true, reason no_tu} on
         both; the client banner is vanilla's "Not Enough Time Units!"; the host
         shows no warning for it (Q3 = a); C TU C16H_TU_AFTER on both, the clip
         untouched.
  C17    real-UI autoshot at the empty road tile C17_TARGET (C faces it: the
         turn C16h's shot produced), host set_seed SEED_C17. RED: refused at K1.
         GREEN: {intent, shoot, C} holding exactly three `shot` evs with
         shotIndex 1, 2, 3 (host [coop-cue] payloads); C TU C17_TU_AFTER and the
         clip C17_CLIP_AFTER on both.
  C17p   a combat order while the host is busy. The host's fire dial is set to 1
         (seat 0 on both), H gets a rifle + clip at C17P_H_TILE; host set_seed
         SEED_C17P and battle_fire {H, auto} at C17P_H_TARGET: a ~21.4 s host
         context (T0-4 a). Once the client has applied its first shot, the client
         snaps at C17P_SNAP_TARGET through the real UI. RED: refused at K1 during
         the host autoshot. GREEN: client lastDeny busy, coopPendingIntent
         {kind shoot, actorId C}, the wait banner "Please wait for HostPlayer's
         action to finish"; after the host's context closes the held order is sent
         again, admitted and executed ({intent, shoot, C} after the host's end);
         C TU = TU max - SNAP_TU on both (the cost is recomputed).
  C16a   aimed through the lever: battle_intent {kind shoot, plan {action
         aimed, ...}} at the floor tile FLOOR_TARGET. RED: "not sent" (unknown
         kind). GREEN: {intent, shoot, C} whose first `shot` payload has action
         aimed.
  C16d   four denies through the lever: tuBasisOverride SNAP_TU -/+ 1 ->
         cost_changed; a weapon C does not hold (H's right-hand item) ->
         weapon_missing; targetUnit A2 with a targetPos one tile off its spawn ->
         target_moved; H as the actor -> not_your_unit. RED: every variant "not
         sent". GREEN: each variant answers with its deny on the client
         (lastDeny {iseq, reason}) and its text on the banner; the host emits
         nothing and closes no context; C TU unchanged on both.
  C16d-r the research-combined deny (D146, C3). Host-only forget_research
         STR_PLASMA_PISTOL, then a plasma pistol + clip on C (both) and a
         lever snap at FLOOR_TARGET. RED: "not sent". GREEN: lastDeny reason
         not_researched with vanilla's "Unable to use alien artifact until
         researched!" on the banner; nothing executed; C TU and the pistol
         clip unchanged on both.
  C26    F428. Leg 1: the client's walk dial is set to 200 (seat 1 on both),
         the host camera centres on C26_CAMERA and the client walks C to
         C26_WALK_DEST through the lever (8 steps, ~13 s with the default 10 s
         timeout, T0-5). RED: intentTimeouts +1 and "No answer from the host -
         action dropped" at ~10 s while the host still walks (F1118/F1119).
         GREEN: intentTimeouts unchanged, no timeout banner, the client's slot
         (inFlight) held until the walk's bt_action_end, the walk longer than the
         timeout option. Leg 2 (green only, declared: at the base the client
         cannot fire): the client's fire dial is set to 1, C back on C_TILE, host
         set_seed SEED_C17, real-UI autoshot at C17_TARGET (~21 s, F1121):
         likewise no timeout while the slot is held, the order longer than the
         timeout option, three `shot` evs in one {intent, shoot, C} context.

The order puts C16 first on the fresh boot, so it runs exactly on TASK 0's T0-1
staging (lever rifle 96 / clip 97). Every later scenario keeps C on C_TILE with
the facing its last turn produced (CLAUDE.local.md S2: a unit is never
teleported onto its own tile): C16's shot leaves C facing A (dir 0), which makes
C16h's floor target two octants east; C16h's turn leaves C facing east, which is
what C17, C17p, C16a and C26 need. C16h's target is a floor tile because C16
has killed A (T0-2 staged A; the halt path draws no RNG and depends only on C's
TU, facing and the snap cost, F1109). place() teleports only a unit that is not
already on the tile.

Common asserts (spec (f), after wait_host_idle): hash_now {full:true} - every
bucket EQUAL (never a hard-coded count); desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; the W2-P2 delta must-be-0 counters
on both; every lever item created on both machines with equal ids (both()).
For an admitted order: host closedContexts gains exactly one {origin intent,
kind K, actorId C}; every host ev of that actionId is in the client's log with
the same seq, kind and actionId; exactly one bt_action_end; client
coopIntentsSent[K] + the number of intents the scenario sent; client inFlight
null at the end; client intentTimeouts unchanged (no STR_COOP_ACTION_TIMEOUT).

The battle_intent `shoot` contract this file uses (S-A.2 builds it; spec (b)13):
  {cmd: battle_intent, kind: shoot, actor, plan: {action, weapon, ammo, target,
   targetUnit, targetPos?, forceFire}, tuBasisOverride?}
`plan` carries the (b)1 shoot fields except tuBasis and is passed through;
the lever computes tuBasis as the real UI does (the actor's getActionTUs for the
action and weapon) unless tuBasisOverride is given. On commit S-A.1 the lever
still answers "not sent" for the kind (the product's unknown-kind path).

Probes (event_state; spec (b)13): coopIntentsSent (client, kind -> count),
intentsReceived (host, kind -> {admitted, denied}), lastActionHalt (both,
{actionId, halted, reason}) and lastAftermath (client, {actionId, kind}) exist
from commit S-A.1 with no writer; S-A.2 writes them. The existing lastDeny,
inFlight, intentTimeouts, closedContexts, coopPendingIntent, cursorType,
coopWaitText and warningText are read as they are.

FIXTURE (TASK 0 T0-1, T0-2, T0-3, T0-4 a, T0-5; the roster-pinned terror boot of
test_w2_host_combat.py): set_seed SEED_ROSTER on the HOST right before its
open_new_battle, mission STR_TERROR_MISSION, set_seed SEED_MAP right before
newbattle_ok, seat_count 2, MAP_FP asserted on both, the seated unit ids
asserted (SEATED), pin_ai_neutral. Every lever pair goes to the CLIENT first
(F607). Item ids are read at run time from the lever replies or by owner + slot
(F1107), never baked. The seeds were found with HOST stand-ins (battle_fire for
C): S-A's executor build proves them again (N18 = F1085).

RED-THEN-GREEN (spec (d) row S-A). Commit S-A.1 (this file, the probes, the
set_touch_modifiers and forget_research levers) is run ONCE and every scenario
must FAIL with its RED evidence. Commit S-A.2 is run ONCE and every scenario must
PASS. Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields
BEFORE its green conditions are checked; main() runs every scenario even after an
earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is
bounded; a wait that times out is recorded in the EVIDENCE line and fails the
scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all eight scenarios pass, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_shoot.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_turn_baton import RHAND_NTH, RHAND_RECT, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, desync_record, short, both
from test_w2_delta_items import items_by_id, unit_view, tile_of
from test_w2_host_combat import bring_up_lobby_roster_pinned, evs_since, ev_tuples
from test_w2_ai_origins import host_payloads

# ----- bring-up (TASK 0: the roster-pinned terror boot) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1 (T0a, every boot)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID, C2_ID = 8, 9
H_ID = 10                         # first host-seat soldier
A_ID = 1000000                    # Sectoid Soldier, spawn (37,38,0)
A2_ID = 1000001                   # Sectoid Soldier, spawn (33,45,0)
A2_SPAWN = (33, 45, 0)
PORT = "48711"
COOP_SEAT_0 = 0
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
STATUS_DEAD = 6                   # src/Mod/Unit.h enum UnitStatus
TU_MAX = 255                      # battle_set_unit_state tu: clamped to the unit's max TU
C_TU_FULL = 64                    # C's max TU with SEED_ROSTER 1
FIRING_120 = 120

# ----- C16 (T0-1, F1106) -----
C_TILE = (12, 26, 0)              # open road
C16_C_DIR = 1                     # one octant off A
A_TILE, A_DIR = (12, 23, 0), 4
A_HEALTH = 1
A_CORPSE = "STR_SECTOID_CORPSE"
SEED_C16 = 1
SNAP_TU = 16                      # C's rifle snap cost (the stand-in's tuCost)
CLIP_FULL = 20
C16_CHAIN = ["shot", "hit", "death", "corpse", "bt_action_end"]
C16_TU_AFTER = 47                 # 64 - 16 snap - 1 for the one-octant turn
C16_CLIP_AFTER = 19

# ----- C16h (T0-2, F1109) -----
C16H_TARGET = (16, 26, 0)         # floor tile due east of C_TILE: two octants from dir 0
C16H_TU_AFTER = 14                # 16 - 2 octants x 1 TU; the shot never fires
HALT_NO_TU = "no_tu"
TEXT_NO_TU = "Not Enough Time Units!"                 # xcom1 STR_NOT_ENOUGH_TIME_UNITS (en-US)

# ----- C17 (T0-3, F1111) -----
C17_TARGET = (32, 26, 0)          # empty road floor tile, 20 tiles east
SEED_C17 = 1
AUTO_TU = 22
C17_TU_AFTER = 42                 # 64 - 22
C17_CLIP_AFTER = 17
C17_SHOTS = 3

# ----- C17p (T0-4 a, F1113) -----
C17P_HOST_FIRE_DIAL = 1
C17P_H_TILE, C17P_H_DIR = (14, 24, 0), 2
C17P_H_TARGET = (34, 24, 0)       # empty road floor tile
SEED_C17P = 1
C17P_SNAP_TARGET = (16, 26, 0)    # due east of C: no pre-shot turn
C17P_TU_AFTER = C_TU_FULL - SNAP_TU
TEXT_WAIT_HOST = f"Please wait for {raw.HOST_PLAYER}'s action to finish"   # STR_COOP_WAIT_FOR_PLAYER_ACTION

# ----- C16a / C16d / C16d-r (lever orders) -----
FLOOR_TARGET = (24, 26, 0)        # road floor due east of C, past C26's walk
SEED_C16A = 1
A2_OFF_TILE = (33, 44, 0)         # one tile north of A2's spawn (F1108)
RESEARCH_TOPIC = "STR_PLASMA_PISTOL"
PISTOL, PISTOL_CLIP = "STR_PLASMA_PISTOL", "STR_PLASMA_PISTOL_CLIP"
TEXT_DENY = {                     # en-US: bin/common STR_COOP_DENY_* / xcom1 vanilla key
    "cost_changed": "Order cancelled - cost changed",
    "weapon_missing": "Order cancelled - weapon unavailable",
    "target_moved": "Order cancelled - target moved",
    "not_your_unit": "Not one of your soldiers",
    "not_researched": "Unable to use alien artifact until researched!",
}

# ----- C26 (T0-5, F1118-F1121) -----
C26_XCOM_DIAL = 200               # client battleXcomSpeed: seat 1 walk dial
C26_WALK_DEST = (20, 26, 0)
C26_WALK_STEPS = 8
C26_CAMERA = (16, 26, 0)          # host camera on the lane (on-screen pacing, F1120)
C26_FIRE_DIAL = 1                 # client battleFireSpeed for leg 2 (F1121)
TIMEOUT_DEFAULT_S = 10            # Options coopIntentTimeoutSeconds default
TEXT_TIMEOUT = "No answer from the host - action dropped"   # STR_COOP_ACTION_TIMEOUT

# ----- UI -----
KEY_AIMED, KEY_SNAP, KEY_AUTO = 49, 50, 51   # keyBattleActionItem1..3
CURSOR_AIM = 2                    # battle_state.cursorType CT_AIM
RHAND_CENTRE = (RHAND_RECT[0] + RHAND_RECT[2] // 2, RHAND_RECT[1] + RHAND_RECT[3] // 2)
POLL_S = 0.05
SENT_WAIT_S = 2.0                 # how long a press gets to show as sent or refused
ORDER_TIMEOUT_S = 45

ZERO_PROBES = ("deltaUnresolved", "deltaUnsupported", "deltaRemoveMissing", "deltaAddExisting")
PROBE_KEYS = ("desyncSeen", "coopClientBStatePushes", "coopLocalExecBlocked", "lastSeqEmitted",
              "lastSeqApplied", "queueDepth", "inFlight", "intentTimeouts", "lastTimedOutIseq",
              "lateAnswersIgnored", "lastDeny", "busyOwnerSeat", "coopIntentsSent", "intentsReceived",
              "lastActionHalt", "lastAftermath", "closedContexts") + ZERO_PROBES


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def probes(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in PROBE_KEYS}


def ui(gc):
    bs = battle_state(gc)
    return {"banner": bs.get("coopWaitText"), "warning": bs.get("warningText"), "cursor": bs.get("cursorType"),
            "pending": bs.get("coopPendingIntent"), "selectedId": bs.get("selectedId")}


def snap(host, client):
    return {"host": probes(host), "client": probes(client), "hostUi": ui(host), "clientUi": ui(client)}


def jt(t):
    return {"x": t[0], "y": t[1], "z": t[2]}


def upos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def ubrief(u):
    v = unit_view(u)
    if v is not None:
        v["tu"] = u.get("tu")
        v["direction"] = u.get("direction")
    return v


def press(gc, key):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})


def menu_rows(gc):
    return len([w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
                if w.get("visible") and "ActionMenuItem" in w.get("type", "")])


def count_of(d, kind):
    return (d or {}).get(kind) or 0


def recv_of(d, kind, field):
    return ((d or {}).get(kind) or {}).get(field) or 0


def new_contexts(before, after):
    seen = {c.get("actionId") for c in (before or [])}
    return [c for c in (after or []) if c.get("actionId") not in seen]


def mine(ctxs, origin, kind, actor):
    return [c for c in ctxs if c.get("origin") == origin and c.get("kind") == kind and c.get("actorId") == actor]


def halt_view(h):
    return {k: (h or {}).get(k) for k in ("actionId", "halted", "reason")} if h else None


def c_items(ih, ic, ids):
    return {i: {"host": {k: (ih.get(i) or {}).get(k) for k in ("owner", "slot", "qty")},
                "client": {k: (ic.get(i) or {}).get(k) for k in ("owner", "slot", "qty")}} for i in ids}


# ===================== staging (client first, F607) =====================


def give_both(host, client, uid, item, ammo=None):
    req = {"cmd": "battle_give", "unit": uid, "item": item, "clear_hands": True}
    if ammo:
        req["ammo"] = ammo
    g = both(host, client, req, ("weaponId", "ammoId"))
    return g["weaponId"], g["ammoId"]


def place(host, client, uid, tile, d):
    """Teleport `uid` onto `tile` facing `d` on BOTH machines - unless it already
    stands there on both, in which case nothing is sent and the unit keeps the
    facing its last turn produced (CLAUDE.local.md S2). Returns what was done."""
    uh, uc = units(host).get(uid) or {}, units(client).get(uid) or {}
    if upos(uh) == tuple(tile) and upos(uc) == tuple(tile):
        return {"kept": tuple(tile), "dir": (uh.get("direction"), uc.get("direction"))}
    r = both(host, client, {"cmd": "battle_teleport_unit", "unit": uid, "x": tile[0], "y": tile[1], "z": tile[2],
                            "dir": d}, ("to", "dir"))
    return {"teleported": tuple(tile), "dir": r.get("dir")}


def set_tu_both(host, client, uid, tu):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "tu": tu}, ("tu",))["tu"]


def set_firing_both(host, client, uid):
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "firing",
                        "value": FIRING_120}, ("tu",))


def wait_seat_dial(host, client, seat, which, value, timeout=15):
    """Both machines' SPEC 17 speed table hold `value` for `seat`'s `which` dial."""
    def ok():
        for gc in (host, client):
            sp = event_state(gc).get("speed") or {}
            ent = [s for s in sp.get("seats", []) if s.get("seat") == seat]
            if not ent or ent[0].get(which) != value:
                return None
        return True
    host.wait_for(f"seat {seat} {which} dial {value} on both", ok, timeout=timeout, interval=0.2)
    return {gc.name: (event_state(gc).get("speed") or {}).get("seats") for gc in (host, client)}


def cancel_client_aim(client):
    """F503: while the client aims, a hand click only cancels the aim. One such
    click when an earlier scenario left the client aiming, so the staging never
    swaps the weapon under a live aim. Returns [cursor before(, after)]."""
    c0 = battle_state(client).get("cursorType")
    if c0 != CURSOR_AIM:
        return [c0]
    click_nth(client, RHAND_NTH)
    return [c0, battle_state(client).get("cursorType")]


# ===================== the client's real-UI order =====================


def aim_click(client, key, tile, before_click=None):
    """The client's REAL-UI shot order (spec (f)): TAB-select C, the right-hand
    box (ActionMenuState), the row's key (the menu closes and targeting starts),
    HOME, one self-verified left click on `tile`. `before_click` runs right
    before the click (the host's set_seed). Returns the evidence."""
    ev = {}
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    if battle_state(client).get("cursorType") == CURSOR_AIM:
        click_nth(client, RHAND_NTH)   # F503: this click only cancels the aim
        ev["aimCancelled"] = battle_state(client).get("cursorType")
    r = click_nth(client, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    client.wait_for("client ActionMenuState on top",
                    lambda: client.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState") or None,
                    timeout=5)
    ev["rows"] = menu_rows(client)
    press(client, key)
    client.wait_for("client BattlescapeState on top after the row key",
                    lambda: top(client) == "BattlescapeState" or None, timeout=5)
    ev["cursorAfterKey"] = battle_state(client).get("cursorType")
    assert ev["cursorAfterKey"] == CURSOR_AIM, (
        f"row key {key} did not start targeting on the client (cursorType {ev['cursorAfterKey']}, want {CURSOR_AIM})")
    press(client, SDLK_HOME)
    time.sleep(0.15)
    pr = client.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    ev["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY", "centered")}
    assert pr.get("verified"), f"precondition: map_tile_click_pos did not verify {tile} on the client: {pr}"
    if before_click:
        before_click()
    client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
    ev["clickAt"] = time.time()
    return ev


def order_done(host, client):
    """The order is over: the client's slot is empty and nothing is held, the host
    has no action context and no BState, the client has applied everything."""
    ec, eh = event_state(client), event_state(host)
    return (ec.get("inFlight") is None and battle_state(client).get("coopPendingIntent") is None
            and eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0)


def await_press(host, client, before, notes, timeout=ORDER_TIMEOUT_S):
    """After a real-UI press: up to SENT_WAIT_S for the press to show as SENT
    (client inFlight set, client coopIntentsSent moved, or the host emitted) or
    REFUSED at K1 (client coopLocalExecBlocked moved); when sent, until the order
    is over (bounded). Returns {state, t}."""
    t0 = time.time()
    state = "quiet"
    while time.time() - t0 < SENT_WAIT_S:
        ec, eh = event_state(client), event_state(host)
        if (ec.get("inFlight") or ec.get("coopIntentsSent") != before["client"]["coopIntentsSent"]
                or eh.get("lastSeqEmitted") != before["host"]["lastSeqEmitted"]):
            state = "sent"
            break
        if ec.get("coopLocalExecBlocked") != before["client"]["coopLocalExecBlocked"]:
            state = "refusedAtK1"
            break
        time.sleep(POLL_S)
    out = {"state": state, "t": round(time.time() - t0, 3)}
    if state == "sent":
        try:
            client.wait_for("the order is over (client slot empty, host idle, client caught up)",
                            lambda: order_done(host, client) or None, timeout=timeout, interval=0.1)
        except Exception as e:
            notes.append(f"order never finished: {short(e)}")
    else:
        time.sleep(0.5)
    out["tEnd"] = round(time.time() - t0, 3)
    return out


def send_intent(host, client, req, notes, timeout=15):
    """One lever order. When the lever sent it, waits (bounded) for the host's
    answer: its deny (client lastDeny.iseq) or the end of the order. Returns
    {resp, sent, iseq, answer}."""
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
            # F1318: a deny applied between the read above and order_done()'s
            # reads leaves the order done; lastDeny wins, so re-read it once.
            ld = event_state(client).get("lastDeny") or {}
            return "deny" if ld.get("iseq") == iseq else "end"
        return None
    try:
        out["answer"] = client.wait_for(f"the host's answer to iseq {iseq}", answered, timeout=timeout,
                                        interval=0.1)
    except Exception as e:
        notes.append(f"no answer to iseq {iseq}: {short(e)}")
    return out


def shoot_req(actor, action, weapon, ammo, target, target_unit=-1, target_pos=None, tu_override=None):
    """battle_intent's `shoot` request (the contract in the module docstring)."""
    plan = {"action": action, "weapon": weapon, "ammo": ammo, "target": jt(target), "targetUnit": target_unit,
            "forceFire": False}
    if target_pos is not None:
        plan["targetPos"] = jt(target_pos)
    req = {"cmd": "battle_intent", "kind": "shoot", "actor": actor, "plan": plan}
    if tu_override is not None:
        req["tuBasisOverride"] = tu_override
    return req


# ===================== record + checks =====================


def collect(host, client, seq0):
    rec = {"host": probes(host), "client": probes(client), "hostUi": ui(host), "clientUi": ui(client),
           "hev": evs_since(host, seq0), "cev": evs_since(client, seq0), "uh": units(host), "uc": units(client),
           "ih": items_by_id(host), "ic": items_by_id(client), "diff": diff_buckets(host, client)}
    rec["dsc"] = desync_record(client, rec["client"]["desyncSeen"])
    return rec


def ctx_view(before, rec):
    return new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])


def chain_of(rec, aid):
    return [e for e in rec["hev"] if e["actionId"] == aid] if aid is not None else []


def admitted_fails(before, rec, kind, actor, sent=1):
    """Spec (f) common asserts for an ADMITTED order. Returns (fails, ctx)."""
    fails = []
    new = ctx_view(before, rec)
    hits = mine(new, "intent", kind, actor)
    ctx = hits[0] if len(hits) == 1 else None
    if len(hits) != 1:
        fails.append(f"host closedContexts gained {len(hits)} {{origin intent, kind {kind}, actorId {actor}}} "
                     f"(want exactly 1; new contexts={new})")
    if ctx:
        aid = ctx.get("actionId")
        chain = chain_of(rec, aid)
        cmap = {e["seq"]: e for e in rec["cev"]}
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
               if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"] or cmap[e["seq"]]["actionId"] != aid]
        if bad:
            fails.append(f"client event_log does not hold the host's evs of actionId {aid}: "
                         f"(seq, host kind, client entry)={bad}")
        ends = [e["seq"] for e in chain if e["kind"] == "bt_action_end"]
        if len(ends) != 1:
            fails.append(f"host bt_action_end evs of actionId {aid}: {ends} (want exactly 1)")
    d = count_of(rec["client"]["coopIntentsSent"], kind) - count_of(before["client"]["coopIntentsSent"], kind)
    if d != sent:
        fails.append(f"client coopIntentsSent.{kind} +{d} (want +{sent}; before="
                     f"{before['client']['coopIntentsSent']} after={rec['client']['coopIntentsSent']})")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"client inFlight at the end {rec['client']['inFlight']} (want null)")
    if rec["client"]["intentTimeouts"] != before["client"]["intentTimeouts"]:
        fails.append(f"client intentTimeouts {before['client']['intentTimeouts']}->{rec['client']['intentTimeouts']} "
                     f"(want unchanged: no STR_COOP_ACTION_TIMEOUT)")
    return fails, ctx


def forwarded_fails(before, rec):
    """The real-UI press must be forwarded as an order, not refused at K1."""
    b, a = before["client"]["coopLocalExecBlocked"], rec["client"]["coopLocalExecBlocked"]
    if a != b:
        return [f"client coopLocalExecBlocked {b}->{a} (want unchanged: the press is an order, not a K1 refusal)"]
    return []


def tu_fails(rec, uid, want, what="C"):
    th, tc = (rec["uh"].get(uid) or {}).get("tu"), (rec["uc"].get(uid) or {}).get("tu")
    if th != want or tc != want:
        return [f"{what} tu host={th} client={tc} (want {want} on both)"]
    return []


def qty_fails(rec, iid, want, what):
    qh, qc = (rec["ih"].get(iid) or {}).get("qty"), (rec["ic"].get(iid) or {}).get("qty")
    if qh != want or qc != want:
        return [f"{what} {iid} qty host={qh} client={qc} (want {want} on both)"]
    return []


def common_fails(host, client, before, what):
    """Spec (f) common asserts."""
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {short(e, 600)}")
    ph, pc = probes(host), probes(client)
    if ph["desyncSeen"] or pc["desyncSeen"]:
        fails.append(f"desyncSeen host={ph['desyncSeen']} client={pc['desyncSeen']} (want false on both)")
    if pc["coopClientBStatePushes"] != before["client"]["coopClientBStatePushes"]:
        fails.append(f"client coopClientBStatePushes {before['client']['coopClientBStatePushes']}"
                     f"->{pc['coopClientBStatePushes']} (want unchanged)")
    if ph["coopClientBStatePushes"] != 0:
        fails.append(f"host coopClientBStatePushes={ph['coopClientBStatePushes']} (want 0)")
    for k in ZERO_PROBES:
        for name, p in (("host", ph), ("client", pc)):
            if p[k] != 0:
                fails.append(f"{name} {k}={p[k]} (want 0)")
    return fails


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


def press_view(before, rec):
    """The refusal / order counters around one press, both machines."""
    b, a = before, rec
    return {"blocked": (b["client"]["coopLocalExecBlocked"], a["client"]["coopLocalExecBlocked"]),
            "pushes": (b["client"]["coopClientBStatePushes"], a["client"]["coopClientBStatePushes"],
                       a["host"]["coopClientBStatePushes"]),
            "inFlight": a["client"]["inFlight"], "hostSeq": (b["host"]["lastSeqEmitted"], a["host"]["lastSeqEmitted"]),
            "sent": (b["client"]["coopIntentsSent"], a["client"]["coopIntentsSent"]),
            "received": (b["host"]["intentsReceived"], a["host"]["intentsReceived"]),
            "lastDeny": a["client"]["lastDeny"], "timeouts": (b["client"]["intentTimeouts"],
                                                             a["client"]["intentTimeouts"]),
            "lastActionHalt": {"host": a["host"]["lastActionHalt"], "client": a["client"]["lastActionHalt"]},
            "lastAftermath": a["client"]["lastAftermath"]}


def ui_view(before, rec):
    return {"client": {k: (before["clientUi"][k], rec["clientUi"][k]) for k in ("banner", "warning", "cursor",
                                                                                  "pending")},
            "host": {k: (before["hostUi"][k], rec["hostUi"][k]) for k in ("banner", "warning")}}


def shot_payloads(host, chain):
    seqs = [e["seq"] for e in chain if e["kind"] == "shot"]
    pl = host_payloads(host, seqs) if seqs else {}
    return [(s, (pl.get(s) or {}).get("payload")) for s in seqs]


def shot_brief(shots):
    return [(s, {k: (p or {}).get(k) for k in ("action", "shotIndex", "weapon", "ammo", "impactVoxel", "impact")})
            for s, p in shots]


# ===================== scenarios =====================


def c16_snap_kill(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C16_C_DIR)
    pa_ = place(host, client, A_ID, A_TILE, A_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "health": A_HEALTH},
         ("health", "stun", "status"))
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        pv = aim_click(client, KEY_SNAP, A_TILE, lambda: host.ok({"cmd": "set_seed", "seed": SEED_C16}))
    except Exception as e:
        notes.append(f"real-UI snap: {short(e)}")
    out = await_press(host, client, before, notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    corpses = {n: [i for i in its.values() if i.get("type") == A_CORPSE and i.get("unitLink") == A_ID]
               for n, its in (("host", rec["ih"]), ("client", rec["ic"]))}
    print(f"EVIDENCE C16: staged rifle={rifle} clip={clip} C={pc_} A={pa_} stagedDiff={staged} aimCancel={aim0} "
          f"press={pv} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; shots={shot_brief(shot_payloads(host, chain))}; A host="
          f"{ubrief(rec['uh'].get(A_ID))} client={ubrief(rec['uc'].get(A_ID))}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; items={c_items(rec['ih'], rec['ic'], (rifle, clip))}; corpses="
          f"{corpses}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "shoot", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C16_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C16_CHAIN})")
    for n, u in (("host", rec["uh"].get(A_ID)), ("client", rec["uc"].get(A_ID))):
        if not u or u.get("status") != STATUS_DEAD or u.get("onTile") is not False:
            fails.append(f"{n} A {unit_view(u)} (want status DEAD ({STATUS_DEAD}), onTile false)")
    hc, cc = corpses["host"], corpses["client"]
    if len(hc) != 1 or len(cc) != 1 or hc[0].get("id") != cc[0].get("id") or tile_of(hc[0]) != tile_of(cc[0]) \
            or tile_of(hc[0]) is None:
        fails.append(f"corpses of A host={hc} client={cc} (want exactly one {A_CORPSE}, the same id and tile on both)")
    fails += tu_fails(rec, C_ID, C16_TU_AFTER)
    fails += qty_fails(rec, clip, C16_CLIP_AFTER, "clip")
    if rec["clientUi"]["cursor"] != CURSOR_AIM:
        fails.append(f"client cursorType after the order {rec['clientUi']['cursor']} (want {CURSOR_AIM}: vanilla keeps "
                     f"aiming after a shot)")
    la = rec["client"]["lastAftermath"] or {}
    if aid is None or la.get("actionId") != aid or la.get("kind") != "shoot":
        fails.append(f"client lastAftermath={rec['client']['lastAftermath']} (want {{actionId {aid}, kind shoot}})")
    fails += common_fails(host, client, before, "C16")
    finish(fails)


def c16h_halt(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, 0)
    set_tu_both(host, client, C_ID, SNAP_TU)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        pv = aim_click(client, KEY_SNAP, C16H_TARGET)
    except Exception as e:
        notes.append(f"real-UI snap: {short(e)}")
    out = await_press(host, client, before, notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    print(f"EVIDENCE C16h: staged rifle={rifle} clip={clip} C={pc_} tu={SNAP_TU} target={C16H_TARGET} "
          f"stagedDiff={staged} aimCancel={aim0} press={pv} outcome={out}; {press_view(before, rec)}; "
          f"ui={ui_view(before, rec)}; newContexts={new}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; items={c_items(rec['ih'], rec['ic'], (rifle, clip))}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "shoot", C_ID)
    fails += f
    if cx and any(e["kind"] == "shot" for e in chain):
        fails.append(f"host evs of actionId {aid} = {[e['kind'] for e in chain]} (want no `shot`: the halt stops "
                     f"the shot before it fires)")
    want = {"actionId": aid, "halted": True, "reason": HALT_NO_TU}
    for n in ("host", "client"):
        hv = halt_view(rec[n]["lastActionHalt"])
        if aid is None or hv != want:
            fails.append(f"{n} lastActionHalt={rec[n]['lastActionHalt']} (want {want})")
    if rec["clientUi"]["banner"] != TEXT_NO_TU:
        fails.append(f"client banner {rec['clientUi']['banner']!r} (want {TEXT_NO_TU!r})")
    if rec["hostUi"]["warning"] == TEXT_NO_TU:
        fails.append(f"host warningText {rec['hostUi']['warning']!r} (want no warning for the partner's halt, Q3 = a)")
    fails += tu_fails(rec, C_ID, C16H_TU_AFTER)
    fails += qty_fails(rec, clip, CLIP_FULL, "clip")
    fails += common_fails(host, client, before, "C16h")
    finish(fails)


def c17_auto(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, 2)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    try:
        pv = aim_click(client, KEY_AUTO, C17_TARGET, lambda: host.ok({"cmd": "set_seed", "seed": SEED_C17}))
    except Exception as e:
        notes.append(f"real-UI autoshot: {short(e)}")
    out = await_press(host, client, before, notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    shots = shot_payloads(host, chain)
    print(f"EVIDENCE C17: staged rifle={rifle} clip={clip} C={pc_} target={C17_TARGET} stagedDiff={staged} "
          f"aimCancel={aim0} press={pv} outcome={out}; {press_view(before, rec)}; ui={ui_view(before, rec)}; "
          f"newContexts={new}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; shots={shot_brief(shots)}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; C host={ubrief(rec['uh'].get(C_ID))} "
          f"client={ubrief(rec['uc'].get(C_ID))}; items={c_items(rec['ih'], rec['ic'], (rifle, clip))}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    fails += forwarded_fails(before, rec)
    f, cx = admitted_fails(before, rec, "shoot", C_ID)
    fails += f
    idx = [(p or {}).get("shotIndex") for _, p in shots]
    if cx and idx != list(range(1, C17_SHOTS + 1)):
        fails.append(f"`shot` evs of actionId {aid}: shotIndex {idx} (want {list(range(1, C17_SHOTS + 1))} under the "
                     f"one context)")
    fails += tu_fails(rec, C_ID, C17_TU_AFTER)
    fails += qty_fails(rec, clip, C17_CLIP_AFTER, "clip")
    fails += common_fails(host, client, before, "C17")
    finish(fails)


def c17p_pending(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    host.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": C17P_HOST_FIRE_DIAL})
    dial = wait_seat_dial(host, client, COOP_SEAT_0, "fire", C17P_HOST_FIRE_DIAL)
    h_rifle, h_clip = give_both(host, client, H_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    ph_ = place(host, client, H_ID, C17P_H_TILE, C17P_H_DIR)
    set_tu_both(host, client, H_ID, TU_MAX)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, 2)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    t0 = time.time()
    tl = {}
    mid = {"denySeen": None, "pending": None, "banner": None, "hostBusy": None, "inFlightSeen": False}
    pv = {}
    try:
        host.ok({"cmd": "set_seed", "seed": SEED_C17P})
        rf = host.ok({"cmd": "battle_fire", "unit": H_ID, "mode": "auto", "x": C17P_H_TARGET[0],
                      "y": C17P_H_TARGET[1], "z": C17P_H_TARGET[2]})
        tl["hostFire"] = (round(time.time() - t0, 3), rf.get("tuCost"))
        client.wait_for("client applied the host autoshot's first shot",
                        lambda: any(e["kind"] == "shot" for e in evs_since(client, seq0)) or None,
                        timeout=20, interval=POLL_S)
        tl["firstShotApplied"] = round(time.time() - t0, 3)
        pv = aim_click(client, KEY_SNAP, C17P_SNAP_TARGET)
        tl["click"] = round(pv["clickAt"] - t0, 3)
        mid["hostBusy"] = event_state(host).get("busyOwnerSeat")
        # the client's answer while the host still shoots: up to 3 s for the deny, the held order and the banner
        t1 = time.time()
        while time.time() - t1 < 3.0:
            ec, bc = event_state(client), battle_state(client)
            if ec.get("inFlight"):
                mid["inFlightSeen"] = True
            if ec.get("lastDeny") != before["client"]["lastDeny"]:
                mid["denySeen"] = ec.get("lastDeny")
            mid["pending"] = bc.get("coopPendingIntent")
            mid["banner"] = bc.get("coopWaitText")
            if mid["denySeen"] and mid["pending"] and mid["banner"] == TEXT_WAIT_HOST:
                break
            time.sleep(POLL_S)
        tl["midSampled"] = round(time.time() - t0, 3)
        host.wait_for("the host autoshot's context closed",
                      lambda: mine(new_contexts(before["host"]["closedContexts"],
                                                event_state(host).get("closedContexts")), "host", "shoot", H_ID)
                      or None, timeout=60, interval=0.1)
        tl["hostContextClosed"] = round(time.time() - t0, 3)
        if mid["denySeen"] or mid["pending"] or mid["inFlightSeen"]:
            client.wait_for("the held order's context closed",
                            lambda: mine(new_contexts(before["host"]["closedContexts"],
                                                      event_state(host).get("closedContexts")), "intent", "shoot", C_ID)
                            or None, timeout=30, interval=0.1)
            tl["intentContextClosed"] = round(time.time() - t0, 3)
        client.wait_for("the order is over", lambda: order_done(host, client) or None, timeout=30, interval=0.1)
    except Exception as e:
        notes.append(f"C17p drive: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hctx = mine(new, "host", "shoot", H_ID)
    ictx = mine(new, "intent", "shoot", C_ID)
    aid = ictx[0]["actionId"] if len(ictx) == 1 else None
    chain = chain_of(rec, aid)
    print(f"EVIDENCE C17p: dial={dial} staged H rifle={h_rifle} clip={h_clip} H={ph_} C rifle={rifle} clip={clip} "
          f"C={pc_} stagedDiff={staged} aimCancel={aim0} press={pv} timeline={tl}; mid={mid}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; hostContext={hctx} "
          f"intentContext={ictx} chain={[(e['seq'], e['kind']) for e in chain]}; host evs={ev_tuples(rec['hev'])} "
          f"client evs={ev_tuples(rec['cev'])}; C host={ubrief(rec['uh'].get(C_ID))} client="
          f"{ubrief(rec['uc'].get(C_ID))}; H host={ubrief(rec['uh'].get(H_ID))}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if mid["hostBusy"] != COOP_SEAT_0:
        fails.append(f"precondition: host busyOwnerSeat at the client's press {mid['hostBusy']} (want "
                     f"{COOP_SEAT_0}: the press lands inside the host's autoshot)")
    fails += forwarded_fails(before, rec)
    dn = mid["denySeen"] or {}
    if dn.get("reason") != "busy":
        fails.append(f"client lastDeny during the host autoshot {mid['denySeen']} (want reason busy)")
    pd = mid["pending"] or {}
    if pd.get("kind") != "shoot" or pd.get("actorId") != C_ID:
        fails.append(f"client coopPendingIntent during the host autoshot {mid['pending']} (want kind shoot, "
                     f"actorId {C_ID})")
    if mid["banner"] != TEXT_WAIT_HOST:
        fails.append(f"client banner during the host autoshot {mid['banner']!r} (want {TEXT_WAIT_HOST!r})")
    if len(hctx) != 1:
        fails.append(f"host closedContexts gained {len(hctx)} {{origin host, kind shoot, actorId {H_ID}}} "
                     f"(want exactly 1: the blocker)")
    f, cx = admitted_fails(before, rec, "shoot", C_ID, sent=2)
    fails += f
    if cx and hctx and chain and min(e["seq"] for e in chain) <= (hctx[0].get("endSeq") or 0):
        fails.append(f"the held order's first ev seq {min(e['seq'] for e in chain)} is not after the host "
                     f"autoshot's end seq {hctx[0].get('endSeq')} (want it executed after the host's end)")
    fails += tu_fails(rec, C_ID, C17P_TU_AFTER)
    fails += common_fails(host, client, before, "C17p")
    finish(fails)


def c16a_aimed(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, 2)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_C16A})
    req = shoot_req(C_ID, "aimed", rifle, clip, FLOOR_TARGET)
    si = send_intent(host, client, req, notes, timeout=ORDER_TIMEOUT_S)
    if si["sent"] and si["answer"] == "end":
        try:
            session.wait_host_idle(host, client, timeout=30)
        except Exception as e:
            notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    shots = shot_payloads(host, chain)
    print(f"EVIDENCE C16a: staged rifle={rifle} clip={clip} C={pc_} stagedDiff={staged} aimCancel={aim0} "
          f"request={req} intent={si}; {press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; shots={shot_brief(shots)}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if not si["sent"]:
        fails.append(f"battle_intent shoot answered {si['resp']} (want sent: an iseq)")
    f, cx = admitted_fails(before, rec, "shoot", C_ID)
    fails += f
    first = shots[0][1] if shots else None
    if cx and (first or {}).get("action") != "aimed":
        fails.append(f"first `shot` of actionId {aid}: {first} (want payload action aimed)")
    fails += common_fails(host, client, before, "C16a")
    finish(fails)


def c16d_denies(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, 2)
    set_tu_both(host, client, C_ID, TU_MAX)
    ih0 = items_by_id(host)
    h_item = sorted(i for i, it in ih0.items() if it.get("owner") == H_ID and it.get("slot") == "STR_RIGHT_HAND")
    a2 = {"host": upos(units(host).get(A2_ID)), "client": upos(units(client).get(A2_ID))}
    staged = diff_buckets(host, client)
    variants = [
        ("cost_changed", f"tuBasisOverride {SNAP_TU - 1}",
         shoot_req(C_ID, "snap", rifle, clip, FLOOR_TARGET, tu_override=SNAP_TU - 1)),
        ("cost_changed", f"tuBasisOverride {SNAP_TU + 1}",
         shoot_req(C_ID, "snap", rifle, clip, FLOOR_TARGET, tu_override=SNAP_TU + 1)),
        ("weapon_missing", f"H's right-hand item {h_item[:1]}",
         shoot_req(C_ID, "snap", h_item[0] if h_item else -1, clip, FLOOR_TARGET)),
        ("target_moved", f"A2 {A2_ID} with targetPos {A2_OFF_TILE}",
         shoot_req(C_ID, "snap", rifle, clip, A2_OFF_TILE, target_unit=A2_ID, target_pos=A2_OFF_TILE)),
        ("not_your_unit", f"actor H {H_ID}", shoot_req(H_ID, "snap", rifle, clip, FLOOR_TARGET)),
    ]
    first = snap(host, client)
    seq0 = first["host"]["lastSeqEmitted"] or 0
    c_tu0 = ((units(host).get(C_ID) or {}).get("tu"), (units(client).get(C_ID) or {}).get("tu"))
    rows = []
    for reason, name, req in variants:
        b = snap(host, client)
        si = send_intent(host, client, req, notes)
        a = snap(host, client)
        uh, uc = units(host).get(C_ID) or {}, units(client).get(C_ID) or {}
        rows.append({"want": reason, "name": name, "req": req, "intent": si, "lastDeny": a["client"]["lastDeny"],
                     "banner": a["clientUi"]["banner"],
                     "hostSeq": (b["host"]["lastSeqEmitted"], a["host"]["lastSeqEmitted"]),
                     "newContexts": new_contexts(b["host"]["closedContexts"], a["host"]["closedContexts"]),
                     "inFlight": a["client"]["inFlight"],
                     "sent": count_of(a["client"]["coopIntentsSent"], "shoot")
                     - count_of(b["client"]["coopIntentsSent"], "shoot"),
                     "denied": recv_of(a["host"]["intentsReceived"], "shoot", "denied")
                     - recv_of(b["host"]["intentsReceived"], "shoot", "denied"),
                     "admitted": recv_of(a["host"]["intentsReceived"], "shoot", "admitted")
                     - recv_of(b["host"]["intentsReceived"], "shoot", "admitted"),
                     "cTu": (uh.get("tu"), uc.get("tu"))})
    rec = collect(host, client, seq0)
    print(f"EVIDENCE C16d: staged rifle={rifle} clip={clip} C={pc_} H right hand={h_item} A2 at={a2} "
          f"stagedDiff={staged} aimCancel={aim0} C tu before host/client={c_tu0}; "
          f"variants={[{k: v for k, v in r.items() if k != 'req'} for r in rows]}; "
          f"requests={[r['req'] for r in rows]}; {press_view(first, rec)}; host evs={ev_tuples(rec['hev'])}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if not h_item:
        fails.append(f"precondition: H holds no right-hand item on the host (the weapon_missing variant needs one)")
    if a2["host"] != A2_SPAWN or a2["client"] != A2_SPAWN:
        fails.append(f"precondition: A2 at {a2} (want {A2_SPAWN} on both: target_moved ships {A2_OFF_TILE})")
    for r in rows:
        tag = f"{r['want']} ({r['name']})"
        si = r["intent"]
        if not si["sent"]:
            fails.append(f"{tag}: battle_intent answered {si['resp']} (want sent: an iseq)")
            continue
        ld = r["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != r["want"]:
            fails.append(f"{tag}: client lastDeny {r['lastDeny']} (want {{iseq {si['iseq']}, reason {r['want']}}})")
        if r["banner"] != TEXT_DENY[r["want"]]:
            fails.append(f"{tag}: client banner {r['banner']!r} (want {TEXT_DENY[r['want']]!r})")
        if r["hostSeq"][0] != r["hostSeq"][1] or r["newContexts"]:
            fails.append(f"{tag}: host lastSeqEmitted {r['hostSeq'][0]}->{r['hostSeq'][1]} newContexts="
                         f"{r['newContexts']} (want nothing executed)")
        if r["inFlight"] is not None:
            fails.append(f"{tag}: client inFlight after the deny {r['inFlight']} (want null)")
        if (r["sent"], r["denied"], r["admitted"]) != (1, 1, 0):
            fails.append(f"{tag}: client coopIntentsSent.shoot +{r['sent']} host intentsReceived.shoot denied "
                         f"+{r['denied']} admitted +{r['admitted']} (want +1 / +1 / +0)")
        if r["cTu"] != c_tu0 or c_tu0 != (C_TU_FULL, C_TU_FULL):
            fails.append(f"{tag}: C tu host/client {c_tu0}->{r['cTu']} (want {C_TU_FULL} on both, unchanged)")
    fails += common_fails(host, client, first, "C16d")
    finish(fails)


def c16dr_research(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    isr0 = {gc.name: gc.cmd({"cmd": "is_researched", "topic": RESEARCH_TOPIC}).get("researched")
            for gc in (host, client)}
    fr = host.cmd({"cmd": "forget_research", "topic": RESEARCH_TOPIC})
    isr1 = {gc.name: gc.cmd({"cmd": "is_researched", "topic": RESEARCH_TOPIC}).get("researched")
            for gc in (host, client)}
    pistol, pclip = give_both(host, client, C_ID, PISTOL, PISTOL_CLIP)
    pc_ = place(host, client, C_ID, C_TILE, 2)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ih0, ic0 = items_by_id(host), items_by_id(client)
    q0 = ((ih0.get(pclip) or {}).get("qty"), (ic0.get(pclip) or {}).get("qty"))
    req = shoot_req(C_ID, "snap", pistol, pclip, FLOOR_TARGET)
    si = send_intent(host, client, req, notes)
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    q1 = ((rec["ih"].get(pclip) or {}).get("qty"), (rec["ic"].get(pclip) or {}).get("qty"))
    print(f"EVIDENCE C16d-r: isResearched before={isr0} forget_research={fr} after={isr1} staged pistol={pistol} "
          f"clip={pclip} C={pc_} stagedDiff={staged} aimCancel={aim0} request={req} intent={si}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; host evs={ev_tuples(rec['hev'])}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; pistol clip qty {q0}->{q1}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if not fr.get("ok") or fr.get("researched") is not False:
        fails.append(f"host forget_research {RESEARCH_TOPIC} answered {fr} (want ok, researched false)")
    if isr1 != {"host": False, "client": True}:
        fails.append(f"is_researched {RESEARCH_TOPIC} after the host's forget {isr1} (want host false, client true)")
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none: research is in no battle bucket)")
    if not si["sent"]:
        fails.append(f"battle_intent shoot answered {si['resp']} (want sent: an iseq)")
    else:
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != "not_researched":
            fails.append(f"client lastDeny {rec['client']['lastDeny']} (want {{iseq {si['iseq']}, reason "
                         f"not_researched}})")
        if rec["clientUi"]["banner"] != TEXT_DENY["not_researched"]:
            fails.append(f"client banner {rec['clientUi']['banner']!r} (want {TEXT_DENY['not_researched']!r})")
        sd = (count_of(rec["client"]["coopIntentsSent"], "shoot") - count_of(before["client"]["coopIntentsSent"],
                                                                              "shoot"),
              recv_of(rec["host"]["intentsReceived"], "shoot", "denied")
              - recv_of(before["host"]["intentsReceived"], "shoot", "denied"),
              recv_of(rec["host"]["intentsReceived"], "shoot", "admitted")
              - recv_of(before["host"]["intentsReceived"], "shoot", "admitted"))
        if sd != (1, 1, 0):
            fails.append(f"client coopIntentsSent.shoot / host intentsReceived.shoot denied / admitted = +{sd} "
                         f"(want +1 / +1 / +0)")
    if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"] or new:
        fails.append(f"host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                     f"newContexts={new} (want nothing executed)")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"client inFlight at the end {rec['client']['inFlight']} (want null)")
    fails += tu_fails(rec, C_ID, C_TU_FULL)
    if q1 != q0 or q0[0] != q0[1]:
        fails.append(f"pistol clip {pclip} qty host/client {q0}->{q1} (want unchanged and equal)")
    fails += common_fails(host, client, before, "C16d-r")
    finish(fails)


def watch(host, client, t0, done, limit):
    """Samples both machines every POLL_S until done(sample) or `limit` s."""
    out = []
    while True:
        t = round(time.time() - t0, 3)
        ec, eh = event_state(client), event_state(host)
        bc = battle_state(client)
        hw, cw = eh.get("lastWalk") or {}, ec.get("lastWalk") or {}
        s = {"t": t, "inFlight": ec.get("inFlight"), "intentTimeouts": ec.get("intentTimeouts"),
             "banner": bc.get("coopWaitText"), "hostBusy": eh.get("busyOwnerSeat"),
             "hostWalk": (hw.get("actionId"), hw.get("active"), len(hw.get("steps") or [])),
             "clientWalk": (cw.get("actionId"), cw.get("active"), bool(cw.get("restate"))),
             "applied": ec.get("lastSeqApplied"), "emitted": eh.get("lastSeqEmitted")}
        out.append(s)
        if done(s) or t > limit:
            return out
        time.sleep(POLL_S)


def banners(samples):
    seen, out = set(), []
    for s in samples:
        if s["banner"] not in seen:
            seen.add(s["banner"])
            out.append((s["t"], s["banner"]))
    return out


def slot_view(samples, t_end, timeouts0):
    """Timeout / slot facts of one watched order."""
    t_ack = next((s["t"] for s in samples if (s["inFlight"] or {}).get("actionId")), None)
    t_tmo = next((s for s in samples if (s["intentTimeouts"] or 0) > (timeouts0 or 0)), None)
    gaps = [s["t"] for s in samples if s["inFlight"] is None and (t_end is None or s["t"] < t_end)]
    return {"tAck": t_ack, "tTimeout": t_tmo["t"] if t_tmo else None,
            "hostWalkAtTimeout": t_tmo["hostWalk"] if t_tmo else None,
            "slotEmptyBeforeEnd": gaps[:5] + (["..."] if len(gaps) > 5 else []), "gapCount": len(gaps),
            "timeoutBannerSeen": any(s["banner"] == TEXT_TIMEOUT for s in samples)}


def c26_timeout(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    tmo = client.ok({"cmd": "set_option", "name": "coopIntentTimeoutSeconds"}).get("value")
    client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": C26_XCOM_DIAL})
    dial1 = wait_seat_dial(host, client, 1, "xcom", C26_XCOM_DIAL)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, 2)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    pp = host.cmd({"cmd": "path_probe", "unit": C_ID, "x": C26_WALK_DEST[0], "y": C26_WALK_DEST[1],
                   "z": C26_WALK_DEST[2]})
    cam = host.cmd({"cmd": "battle_camera_center", "x": C26_CAMERA[0], "y": C26_CAMERA[1], "z": C26_CAMERA[2]})
    staged = diff_buckets(host, client)
    # ---- leg 1: the long client walk ----
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    cw0 = (event_state(client).get("lastWalk") or {}).get("actionId")
    t0 = time.time()
    rw = client.cmd({"cmd": "battle_intent", "kind": "walk", "actor": C_ID, "dest": jt(C26_WALK_DEST)})
    s1 = []
    if rw.get("ok"):
        s1 = watch(host, client, t0, lambda s: (s["clientWalk"][0] not in (None, cw0) and s["clientWalk"][1] is False
                                                and s["clientWalk"][2] and s["hostBusy"] == -1),
                   ORDER_TIMEOUT_S)
    t_end1 = next((s["t"] for s in s1 if s["clientWalk"][0] not in (None, cw0) and s["clientWalk"][1] is False
                   and s["clientWalk"][2]), None)
    if rw.get("ok") and t_end1 is None:
        notes.append(f"leg 1: the client never applied the walk's end within {ORDER_TIMEOUT_S} s")
    try:
        client.wait_for("leg 1 over", lambda: order_done(host, client) or None, timeout=30, interval=0.1)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"leg 1 settle: {short(e)}")
    rec1 = collect(host, client, seq0)
    sv1 = slot_view(s1, t_end1, before["client"]["intentTimeouts"])
    new1 = ctx_view(before, rec1)
    # ---- leg 2 (green only, declared): the client's own long autoshot ----
    notes2 = []
    dial2, pc2, pv2, s2, t_end2, rec2, before2, sv2 = None, None, {}, [], None, None, None, {}
    try:
        client.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": C26_FIRE_DIAL})
        dial2 = wait_seat_dial(host, client, 1, "fire", C26_FIRE_DIAL)
        pc2 = place(host, client, C_ID, C_TILE, 2)
        set_tu_both(host, client, C_ID, TU_MAX)
        before2 = snap(host, client)
        seq2 = before2["host"]["lastSeqEmitted"] or 0
        pv2 = aim_click(client, KEY_AUTO, C17_TARGET, lambda: host.ok({"cmd": "set_seed", "seed": SEED_C17}))
        t2 = pv2["clickAt"]
        sent = {"v": False}

        def done2(s):
            if s["inFlight"]:
                sent["v"] = True
            if not sent["v"]:
                return s["t"] > SENT_WAIT_S
            return s["inFlight"] is None and s["hostBusy"] == -1 and s["applied"] == s["emitted"]
        s2 = watch(host, client, t2, done2, ORDER_TIMEOUT_S)
        t_end2 = next((s["t"] for s in s2 if sent["v"] and s["inFlight"] is None
                       and any(x["inFlight"] for x in s2 if x["t"] < s["t"])), None)
        client.wait_for("leg 2 over", lambda: order_done(host, client) or None, timeout=30, interval=0.1)
        session.wait_host_idle(host, client, timeout=30)
        rec2 = collect(host, client, seq2)
        sv2 = slot_view(s2, t_end2, before2["client"]["intentTimeouts"])
    except Exception as e:
        notes2.append(f"leg 2: {short(e)}")
    new2 = ctx_view(before2, rec2) if (before2 and rec2) else []
    hits2 = mine(new2, "intent", "shoot", C_ID)
    aid2 = hits2[0]["actionId"] if len(hits2) == 1 else None
    shots2 = shot_payloads(host, chain_of(rec2, aid2)) if rec2 else []
    print(f"EVIDENCE C26: timeoutOption={tmo} walkDial={dial1} staged rifle={rifle} clip={clip} C={pc_} "
          f"path_probe={ {k: pp.get(k) for k in ('reachable', 'steps', 'tuCost')} } camera={cam.get('ok')} "
          f"stagedDiff={staged} aimCancel={aim0}; LEG1 walk intent={rw} tEnd={t_end1} slot={sv1} banners="
          f"{banners(s1)} samples={len(s1)}; {press_view(before, rec1)}; newContexts={new1}; host lastWalk="
          f"{s1[-1]['hostWalk'] if s1 else None}; C host={ubrief(rec1['uh'].get(C_ID))} client="
          f"{ubrief(rec1['uc'].get(C_ID))}; diff={rec1['diff']} desync={rec1['dsc']}; LEG2 fireDial={dial2} C={pc2} "
          f"press={pv2} tEnd={t_end2} slot={sv2} banners={banners(s2)} samples={len(s2)}; "
          f"{press_view(before2, rec2) if (before2 and rec2) else None}; newContexts={new2}; shots="
          f"{shot_brief(shots2)}; diff={rec2['diff'] if rec2 else None}; notes={notes} notes2={notes2}", flush=True)
    fails = list(notes)
    if tmo != TIMEOUT_DEFAULT_S:
        fails.append(f"precondition: client coopIntentTimeoutSeconds {tmo} (want the default {TIMEOUT_DEFAULT_S})")
    if pp.get("steps") != C26_WALK_STEPS:
        fails.append(f"precondition: path_probe C -> {C26_WALK_DEST} {pp} (want {C26_WALK_STEPS} steps)")
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    # leg 1 (F428 on a long walk)
    if not rw.get("ok"):
        fails.append(f"leg 1: battle_intent walk answered {rw} (want sent)")
    if t_end1 is not None and t_end1 <= (tmo or TIMEOUT_DEFAULT_S):
        fails.append(f"leg 1: the walk ended at +{t_end1} s, not after the {tmo} s timeout (the leg proves nothing)")
    if sv1.get("tTimeout") is not None or sv1.get("timeoutBannerSeen"):
        fails.append(f"leg 1: the client timed out at +{sv1.get('tTimeout')} s (banner seen "
                     f"{sv1.get('timeoutBannerSeen')}) while the host walked {sv1.get('hostWalkAtTimeout')} "
                     f"(want no timeout: F428)")
    if sv1.get("gapCount"):
        fails.append(f"leg 1: client inFlight null before the walk's end at +{sv1.get('slotEmptyBeforeEnd')} s "
                     f"(want the slot held until the walk's bt_action_end)")
    for n, u in (("host", rec1["uh"].get(C_ID)), ("client", rec1["uc"].get(C_ID))):
        if upos(u) != C26_WALK_DEST:
            fails.append(f"leg 1: {n} C at {upos(u)} (want {C26_WALK_DEST})")
    f, _ = admitted_fails(before, rec1, "walk", C_ID)
    fails += [f"leg 1: {m}" for m in f]
    fails += [f"leg 1: {m}" for m in common_fails(host, client, before, "C26 leg 1")]
    # leg 2 (green only, declared)
    fails += [f"leg 2: {m}" for m in notes2]
    if rec2 is not None and before2 is not None:
        if t_end2 is None:
            fails.append(f"leg 2: the client's autoshot never held an order to its end (slot={sv2})")
        elif t_end2 <= (tmo or TIMEOUT_DEFAULT_S):
            fails.append(f"leg 2: the order ended at +{t_end2} s, not after the {tmo} s timeout (the leg proves "
                         f"nothing)")
        if sv2.get("tTimeout") is not None or sv2.get("timeoutBannerSeen"):
            fails.append(f"leg 2: the client timed out at +{sv2.get('tTimeout')} s (want no timeout: F428)")
        if t_end2 is not None and sv2.get("gapCount"):
            fails.append(f"leg 2: client inFlight null before the order's end at +{sv2.get('slotEmptyBeforeEnd')} s")
        f2, cx2 = admitted_fails(before2, rec2, "shoot", C_ID)
        fails += [f"leg 2: {m}" for m in f2]
        idx = [(p or {}).get("shotIndex") for _, p in shots2]
        if cx2 and idx != list(range(1, C17_SHOTS + 1)):
            fails.append(f"leg 2: shotIndex {idx} (want {list(range(1, C17_SHOTS + 1))} under one context)")
        fails += forwarded_fails(before2, rec2)
        fails += [f"leg 2: {m}" for m in common_fails(host, client, before2, "C26 leg 2")]
    finish(fails)


SCENARIOS = (("C16", c16_snap_kill), ("C16h", c16h_halt), ("C17", c17_auto), ("C17p", c17p_pending),
             ("C16a", c16a_aimed), ("C16d", c16d_denies), ("C16d-r", c16dr_research), ("C26", c26_timeout))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p4-sa")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    for uid in (A_ID, A2_ID):
        u = ub.get(uid) or {}
        assert u.get("faction") == FACTION_HOSTILE and not u.get("isOut"), (
            f"alien {uid} at bring-up: {unit_view(u)} (want a live FACTION_HOSTILE unit)")
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastActionHalt" in es and "lastAftermath" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r} lastActionHalt present={'lastActionHalt' in es} "
            f"lastAftermath present={'lastAftermath' in es}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p4-sa] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={seated_uids} H={H_ID} "
          f"pinned={len(pinned)} C={ubrief(ub.get(C_ID))} A={ubrief(ub.get(A_ID))} A2={ubrief(ub.get(A2_ID))}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49870, make_user_dir("w2p4_client_shoot_host"))
    client = GameClient("client", 49871, make_user_dir("w2p4_client_shoot_client"))
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
                print(f"[w2p4-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_shoot: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
