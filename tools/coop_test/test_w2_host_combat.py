"""W2-P2 S-C - test_w2_host_combat.py: the host's own combat runs as proper
actions with cue events, so the second player sees a clean start and end
(spec rewrite/prompts/w2p2_delta_core.md section (f) "test_w2_host_combat.py
(S-C)", sections (b)11-14 and (b)16; orchestrator rulings Q2 = (a) and
Q4 = (b), amendments A1 and A2; owner ruling D128 = (b)).

After stage S-B the host's combat RESULT already reaches the client: the
chain ends context-less, onChainQuiesced's empty-stack branch runs
CoopDelta::flushSync(), and one `sync` ev carries the delta (units, items,
the corpse with the host's id). What is missing is the ACTION: no context is
opened for the host's shot or stun, so no cue ev (`shot`, `hit`, `melee`,
`death`, `corpse`) is sent and no `bt_action_end` closes it. After stage S-C
the host opens a host-local combat context (CoopArbiter::beginHostLocalCombat,
spec (b)13), the six vanilla cue hooks emit their cues with the action's id and
`h`, and the chain's end emits the action's `bt_action_end`. Three scenarios,
ONE boot, in this order:

  C1  host real-UI snap shot kills alien A. H gets a rifle + clip
      (battle_give on BOTH, ids equal), H -> C1_H_TILE facing C1_H_DIR (one
      octant off A: the shot's own UnitTurnBState recalculates FOV and A
      becomes visible), A -> C1_A_TILE, A health 1, H TU max, H firing 120
      (all on BOTH). Host: TAB-select H, click the right-hand box
      (ActionMenuState), key 50 (SNAP), set_seed SEED_C1, one left click on
      A's tile. RED (commit S-C.1): the state is equal on both machines (the
      S-B `sync`), but host hostCombatContexts +0, no shot/hit/death/corpse
      ev in either event log, no bt_action_end for the shot. GREEN: host
      hostCombatContexts +1; the host event_log for that actionId is exactly
      shot -> hit -> death -> corpse -> bt_action_end, every one with `h`; the
      client event_log holds the same seqs with the same kinds and actionId;
      client lastCue = corpse (payload.unit A, payload.corpses = [the corpse
      id]); SB1's item / morale / onTile asserts; H tu and the clip's qty
      equal on both; the common asserts.
  C5  host stun rod knocks alien A2 unconscious. H gets a stun rod (BOTH),
      H -> C5_H_TILE facing A2 at C5_A2_TILE, A2 health 5, H TU max (BOTH).
      Host: TAB-select H, click the right-hand box once more first when H is
      still in aim mode after C1 (cursorType 2, amendment A2.3 / F503), click
      it (ActionMenuState), set_seed SEED_C5, key 52 (STUN). RED: as C1 - no
      context, no melee/death/corpse ev. GREEN: host hostCombatContexts +1;
      the host event_log for that actionId is exactly melee -> death ->
      corpse -> bt_action_end, every one with `h`; the client log holds the
      same seqs and kinds; client lastCue = corpse (payload.unit A2,
      payload.corpses = [the body item id]); A2 status UNCONSCIOUS and stun
      equal on both; the body item (unitLink A2) equal on both; A2's weapon
      on the ground on both; the common asserts.
  D3  (W2-P6b S-D, the NEW last scenario) a two-victim death burst. C (8) ->
      D3_C_TILE facing D3_C_DIR, C2 (9) -> D3_C2_TILE facing D3_C2_DIR (BOTH),
      then the HOST's battle_action kill_unit_real {coop_side: 1}; bounded waits
      for both DEAD on the host with no BState (F823) and the client caught up.
      The lever runs on an empty host state stack, so C's UnitDieBState is the
      host's front state and C2's queues behind it (TASK 0b T0b-2: host evs
      exactly D3_EVS, the D3_DEATHS / D3_CORPSES payloads, 6 runs identical).
      W2-P6b S-D.3 (AMENDMENT P6b-4, F1793/F1798/F1800): the CLIENT's test-only
      battle_action death_apply_hold {on: true} before the lever ({on: false}
      after the row) forces the race order - C's ghost has started when C2's
      death is enqueued - in every run, and seq 21's record (seq 16 before
      the W2-P8b S-A equip evs, F3426) must say so (headStartedAtEnqueue
      true), so D3 never passes vacuously in the other order.

W2-P6b S-D (spec rewrite/prompts/w2p6_display_two.md section 8 and the P6b plan
review's section 2 rows D1-D3; AMENDMENT P6b-1; AMENDMENT P6b-2 = TASK 0b's
traced host schedule, which replaces section 8's tick model): the watching
machine plays each animated death as the host does. D1 (C1's kill of A) and D2
(C5's stun of A2) each want ONE client record for the death ev's seq in
event_state displayTwo.death.ring, D3 wants two (V1 = C, V2 = C2, in the host's
order), and every `death` payload carries the additive `front` (the host's
state stack was empty at the push). Each record's schedule (Ic, tc, isOutMs,
popMs) equals death_schedule() for its own inputs; its frames, sound and
overKill match both machines' battle_state (D-S3) and the pins. Common to the
three rows: the client's rngSeed unchanged across the row, the host's
displayTwo all zero, the client's completed + cut == enqueued once its death
ghosts ended (a bounded wait). coopGhostStepper is pinned true in both
instances' options (the W2-P5 ghost-file precedent). RED (commit S-D.1: the
probes exist, nothing writes them): C1, C5 and D3 fail only on
displayTwo.death (no record) and the payload's missing `front`. Each row
prints ONE "EVIDENCE D<n>:" line.

W2-P6b S-E (spec section 9 and the P6b review's section 2 row E1; AMENDMENTS
P6b-1..P6b-3): C5's stun-rod swing plays on the watching machine as a melee
ghost. Row E1 wants ONE client combatGhost ring record of kind melee for the
`melee` ev's seq whose frame, frames, intervalMs, ms, sound and soundEnd equal
the rule chain impact_expect() computes from both machines' display_rules
(ExplosionBState's hit branch; the pins in EFFECT_PINS), client
combatGhost.enqueued.melee +1, and the S-E common asserts (client rngSeed
unchanged, host displayTwo / combatGhost all zero, completed + cut == enqueued
per S-E kind). The S-E helpers below are shared by the other S-E files. RED
(commit S-E.1: the melee slot and the effect probes exist, nothing writes
them): only C5 fails, on E1 (no melee record, enqueued.melee +0). One
"EVIDENCE E1:" line.

Both scenarios also check the cueCounts probe against the event logs (for
each cue kind the scenario expects: host cueCounts delta == `kind` evs the
host emitted since the scenario's first seq, client cueCounts delta == evs
the client applied) - spec (b)16's "host emitted, client applied".

Per-cue payloads other than the last one (shot actor H, hit unit A, death
outcome) have no probe of their own: event_log carries seq/kind/actionId/h
only and lastCue holds the last cue. They are covered by the state asserts
(A DEAD / A2 UNCONSCIOUS on both) and by H's tu equal on both (the client
maps the action's bt_action_end `final` onto the FIRST cue's actor, spec
(b)12; a wrong mapping writes H's final onto the victim and the hash sees it).

Common asserts (spec (f), after the action settles with wait_host_idle):
hash_now {full:true} - ALL buckets EQUAL on both machines (never a hard-coded
count); desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing and deltaAddExisting all 0 on both. The spec's C1/C5 rows
name no lastDelta class counts: at GREEN the action's delta is split over its
cues, so which classes the LAST non-empty one holds depends on the split; the
item and unit equality asserts prove the item/unit halves instead.

FIXTURE (deterministic, never searched here; W2-P2 TASK 0a-2 precalc,
amendment A2). STR_TERROR_MISSION, map seed SEED_MAP 1. The roster is pinned
too: set_seed SEED_ROSTER on the HOST immediately before its open_new_battle
(names and stats repeat, amendment A2.2 / F501) - a local bring-up helper, not
raw.bring_up_lobby unchanged - then session.drive_to_battlescape with the
mission pin and set_seed SEED_MAP right before newbattle_ok, the baked MAP_FP
asserted on both, session.pin_ai_neutral. Every lever pair applies to the
CLIENT first, then the HOST (F607, S-H.1a), with the responses asserted equal;
every item a lever creates is created on both machines with ids asserted
equal. set_seed on the HOST immediately before each action.

RED-THEN-GREEN (spec (d), Q4 = b; W2-P6b S-D: the D rows above). Commit S-C.1 (this file and the
event_state probes hostCombatContexts / cueCounts / lastCue - storage and
readers only, nothing writes them) is run ONCE and both scenarios must FAIL
with their named red evidence while the state is already equal. Commit S-C.2
(contexts, cue hooks, prime action) is run ONCE and both must PASS. Each
scenario prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its
green conditions are checked; main() runs every scenario even after an earlier
one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is
bounded; a wait that times out is recorded in the EVIDENCE line and fails the
scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when every scenario passes, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_host_combat.py
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
import repro_atom_walk as raw
from test_rw_turn_baton import RHAND_RECT, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import (probes, diff_buckets, desync_record, short, both, tele_both, tu_both,
                                common_fails, finish, delta_view)
from test_w2_delta_items import items_by_id, item_diff, tile_of, unit_view

# ----- common (test_w2_host_combat.py and test_w2_host_combat_terrain.py; TASK 0a-2) -----
MISSION = "STR_TERROR_MISSION"
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
H_ID = 10                        # first host-seat soldier; with SEED_ROSTER 1 = "Henryk Kaminski",
                                 # tu 58, health 37, firing 46, throwing 73, melee 25, strength 45
RHAND_NTH = 25                   # click_widget nth of the right-hand box
KEY_ITEM1, KEY_ITEM2, KEY_ITEM4, KEY_FUSE_0 = 49, 50, 52, 48   # PRIME/AIMED, SNAP, STUN, fuse 0
TU_MAX = 255                     # battle_set_unit_state / battle_fire tu: clamped to the unit's max TU
FIRST_LEVER_ITEM_ID = 96         # 96 items at start on both maps (ids 0..95)

# ----- test_w2_host_combat.py (S-C): C1 + C5 -----
SEED_MAP = 1                     # first terror map seed (>= 2 capturable 1x1 aliens on every seed)
MAP_FP = -3.451266327757785e+18  # host battle_state.mapFingerprint
A_ID = 1000000                   # Sectoid Soldier, spawn (37,38,0) dir 2; STR_PLASMA_PISTOL id 56 (RIGHT_HAND),
                                 # STR_PLASMA_PISTOL_CLIP id 58 (BELT)
A2_ID = 1000001                  # Sectoid Soldier, spawn (33,45,0) dir 0; STR_PLASMA_RIFLE id 59 (RIGHT_HAND),
                                 # STR_ALIEN_GRENADE id 61, STR_PLASMA_RIFLE_CLIP id 62 (BELT)
A_CORPSE = "STR_SECTOID_CORPSE"
C1_H_TILE, C1_H_DIR = (12, 26, 0), 1   # open road; one octant off A (the shot's turn recalculates FOV)
C1_A_TILE, C1_A_DIR = (12, 23, 0), 4
C1_A_HEALTH = 1                  # battle_set_unit_state {unit: A, health: 1} on both
C1_ITEMS = ("STR_RIFLE", "STR_RIFLE_CLIP")   # give_both clear_hands -> ids 96, 97; set_stat firing 120 on both
SEED_C1 = 1                      # snap (key 50) + click A's tile: A DEAD, clip 20 -> 19, H tu 58 -> 43,
                                 # corpse id 98; host spotted [] -> [1000000, 1000005]  (3/3 standalone + 3/3 one-boot)
C5_H_TILE, C5_H_DIR = (24, 24, 0), 0   # H faces A2 on the tile north
C5_A2_TILE, C5_A2_DIR = (24, 23, 0), 4
C5_A2_HEALTH = 5                 # battle_set_unit_state {unit: A2, health: 5} on both (measured with H tu = max too)
SEED_C5 = 1                      # STUN (key 52): A2 UNCONSCIOUS, stun 120, health 5, H tu 58 -> 41
                                 # standalone: rod 96, body 97 (3/3); one-boot after C1: rod 99, body 100 (3/3)

A_WEAPON = 56                    # A's right-hand STR_PLASMA_PISTOL
A2_WEAPON = 59                   # A2's right-hand STR_PLASMA_RIFLE
FIRING_120 = 120

# ----- W2-P6b S-D (section 8 + review section 2 rows D1-D3; AMENDMENTS P6b-1 and P6b-2; TASK 0b) -----
DEATH_IS_TURN = 33               # the UnitDieBState ctor's last interval for a victim that must turn
                                 # (DEFAULT_ANIM_SPEED / 3, UnitDieBState.cpp :100/:103; F1768)
DEATH_IC = 100                   # DEFAULT_ANIM_SPEED: the collapse interval the pirouette's end sets (:183)
DEATH_F = 3                      # deathFrames of SECTOID_ARMOR0 and STR_NONE_UC (T0b-3 on the S-D.1 build, both
                                 # machines, terror seed 1 and the default map; F1768)
SECTOID_DEATH_SOUNDS = [10]      # battle_state deathSounds of A and A2 (T0b-3, equal on both machines)
SOLDIER_DEATH_SOUNDS = [41, 42, 43]   # every soldier of the pinned roster: C, C2, H, U (T0b-3, both machines)
NO_SOUND = -1                    # a stun's record sound: the host plays none (N6 = F1655)
OVERKILL_NONE = 0                # getOverKillDamage() after C1, C5 and the D3 lever deaths (T0b-1, T0b-3, F1767)
DIRS_4_TO_3 = [4, 5, 6, 7, 0, 1, 2, 3]   # the drawn directions of a 7-octant pirouette from dir 4 (D1, D2)
PHASES_ALL = list(range(DEATH_F))        # [0, 1, 2]: every collapse frame drawn
C1_DEATH = {"unit": A_ID, "outcome": "dead", "instant": False, "damageType": 1}          # T0b-1 (seq 7; 12 since S-A)
C5_DEATH = {"unit": A2_ID, "outcome": "unconscious", "instant": False, "damageType": 0}  # T0b-1 (seq 12; 17 since S-A)
DEATH_KEYS = ("unit", "outcome", "instant", "damageType")
DEATH_SETTLE_S = 5.0             # bounded wait for the client's death ghosts to end after the chain settled
# D3 (TASK 0b T0b-2 = F1767/F1769: 6 runs identical, 26.6 s per boot)
C_ID, C2_ID = 8, 9               # the client seat's soldiers
D3_C_TILE, D3_C_DIR = (12, 26, 0), 4     # open road (H left it at C5)
D3_C2_TILE, D3_C2_DIR = (12, 27, 0), 1   # open road
# W2-P8b S-A's pre-battle equip phase moved every absolute seq +5 (F3426; W2-P8b S-H.3, chain rule A.10: the
# D3 seqs below re-pointed to the values measured on the S-A build, 2 runs identical, F3446/F3447). Traced on
# both machines' event_log rings and logs (F3445), the evs before turn 1 are now:
#   seq 1 reveal  hostile base restate (SS2.W4)                                  - as before S-A (seq 1)
#   seq 2 reveal  player, the 587 VOID tiles the blob does not carry             - as before S-A (seq 2)
#   seq 3 reveal  player, the 655 tiles of the SS2.W5 battle-entry FOV restate   - NEW: it now runs at the equip
#                 open, after seq 2 went out (before S-A both rode seq 2: 1242 = 587 + 655 tiles)
#   seq 4 sync    equip {open}                                                   - NEW
#   seq 5 sync    equip {ready} seat 0 (host)                                    - NEW
#   seq 6 sync    equip {ready} seat 1 (client)                                  - NEW
#   seq 7 sync    equip {end} + battle.turn 1 (the offer's snapshot is turn 0)   - NEW
# so C1's staging reveal is seq 8 (was 3), C1 runs 9..14 (was 4..9), C5 15..19 (was 10..14).
D3_SEQ0 = 19                     # host lastSeqEmitted right before the lever (after C1 and C5; 14 before S-A)
D3_KILLED = [C_ID, C2_ID]        # the lever's answer
D3_EVS = [(20, "death", 0), (21, "death", 0), (22, "corpse", 0), (23, "corpse", 0)]   # host = client
D3_DEATHS = {20: {"unit": C_ID, "outcome": "dead", "instant": False, "damageType": 1, "front": True},
             21: {"unit": C2_ID, "outcome": "dead", "instant": False, "damageType": 1, "front": False}}
D3_CORPSES = {22: {"unit": C_ID, "corpses": [101]}, 23: {"unit": C2_ID, "corpses": [102]}}
DIR_FACING_3 = 3                 # a collapsed unit's final direction (the corpse ev's DEAD carrier, F1767)

PORT = "48625"
FACTION_PLAYER = 0
FACTION_HOSTILE = 1
COOP_SEAT_0 = 0
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus
STATUS_UNCONSCIOUS = 7
CURSOR_AIM = 2                   # battle_state.cursorType CT_AIM: H still targeting after a shot (F503)
# spec (b)11: the 16 frozen cue kinds; `sync` is the context-less flush, not a combat cue.
CUE_KINDS = ("shot", "hit", "explosion", "melee", "psi", "death", "corpse", "prime", "sync", "fall",
             "revive", "spawn", "panic", "prox_trigger", "medikit", "scanner")
COMBAT_CUES = tuple(k for k in CUE_KINDS if k != "sync")
C1_CHAIN = ["turn", "shot", "hit", "death", "corpse", "bt_action_end"]   # W2-P5 S-T (D151, E3): the pre-shot turn
C5_CHAIN = ["melee", "death", "corpse", "bt_action_end"]
LOG_TAIL = 256                   # CoopEventLog::kCapacity


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def cue_probes(gc):
    """The S-C event_state probes: hostCombatContexts, cueCounts, lastCue."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {"hostCombatContexts": es.get("hostCombatContexts"), "cueCounts": es.get("cueCounts") or {},
            "lastCue": es.get("lastCue")}


def evs_since(gc, seq0):
    """This machine's event ring (host: emitted, client: applied) after seq0,
    as [{seq, kind, actionId, h}] in ring order."""
    r = gc.cmd({"cmd": "event_log", "tail": LOG_TAIL})
    assert r.get("ok"), f"event_log failed on {gc.name}: {r}"
    return [{"seq": e.get("seq"), "kind": e.get("kind"), "actionId": e.get("actionId"), "h": e.get("h")}
            for e in r.get("events", []) if (e.get("seq") or 0) > seq0]


def ev_tuples(evs):
    return [(e["seq"], e["kind"], e["actionId"], e["h"]) for e in evs]


def unit_brief(u):
    v = unit_view(u)
    if v is not None:
        v["tu"] = u.get("tu")
        v["direction"] = u.get("direction")
    return v


def host_chain_done(host, uid, status):
    """HOST only: `uid` has `status`, no BState is queued or running,
    BattlescapeState on top."""
    bs = battle_state(host)
    u = session.units_by_id(bs).get(uid) or {}
    return (u.get("status") == status and bs.get("pendingStates") == 0 and not bs.get("isBusy")
            and top(host) == "BattlescapeState") or None


def open_hand_menu_host(host):
    """TAB-select H on the host, then click the right-hand box so
    ActionMenuState opens: ONE extra click first when H is still in aim mode
    (cursorType 2) after an earlier shot - that click only cancels the
    targeting (BattlescapeState's hand-click handler, amendment A2.3 / F503).
    Returns [cursorType before the clicks] or, with the extra click,
    [before, after the extra click] (evidence only)."""
    assert tab_select(host, H_ID), (f"TAB never selected H on the host (selectedId "
                                    f"{battle_state(host).get('selectedId')})")
    want = (RHAND_RECT[0] + RHAND_RECT[2] // 2, RHAND_RECT[1] + RHAND_RECT[3] // 2)
    cursor = [battle_state(host).get("cursorType")]
    if cursor[0] == CURSOR_AIM:
        r = click_nth(host, RHAND_NTH)
        assert (r.get("baseX"), r.get("baseY")) == want, f"right-hand click landed off the box: {r}"
        cursor.append(battle_state(host).get("cursorType"))
    r = click_nth(host, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == want, f"right-hand click landed off the box: {r}"
    host.wait_for("host ActionMenuState on top",
                  lambda: host.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState") or None,
                  timeout=5)
    return cursor


def press(gc, key):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})


# ===================== action-chain checks =====================


def chain_of(host_evs, first_kind):
    """The action whose FIRST `first_kind` ev appears in the host log: its
    actionId and every host ev carrying that actionId. (None, []) when the
    host emitted no `first_kind` ev."""
    firsts = [e for e in host_evs if e["kind"] == first_kind]
    if not firsts:
        return None, []
    aid = firsts[0]["actionId"]
    return aid, [e for e in host_evs if e["actionId"] == aid]


def chain_fails(host_evs, client_evs, first_kind, want_kinds, seq0):
    """Spec (f) GREEN: the host log for the action = exactly `want_kinds`, all
    with `h`, and the client log holds the same seqs with the same kinds and
    actionId. Returns (actionId, chain, fails)."""
    fails = []
    aid, chain = chain_of(host_evs, first_kind)
    if aid is None:
        fails.append(f"host event_log has no `{first_kind}` ev since seq {seq0} (want the action's first "
                     f"cue; host evs since then={ev_tuples(host_evs)})")
        return aid, chain, fails
    if aid == 0:
        fails.append(f"the host's first `{first_kind}` ev carries actionId 0 (want the host-local combat "
                     f"context's id)")
    kinds = [e["kind"] for e in chain]
    if kinds != want_kinds:
        fails.append(f"host event_log for actionId {aid} = {kinds} (want exactly {want_kinds})")
    noh = [e["seq"] for e in chain if not e["h"]]
    if noh:
        fails.append(f"host evs of actionId {aid} without `h`: seqs {noh} (want every one with h)")
    cmap = {e["seq"]: e for e in client_evs}
    bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in chain
           if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"]
           or cmap[e["seq"]]["actionId"] != aid]
    if bad:
        fails.append(f"client event_log does not hold the host's seqs/kinds for actionId {aid}: "
                     f"(seq, host kind, client entry)={bad}")
    return aid, chain, fails


def seq_of(chain, kind):
    for e in chain:
        if e["kind"] == kind:
            return e["seq"]
    return None


def cue_count_fails(name, before, after, evs, kinds, seq0):
    """spec (b)16: cueCounts = host emitted / client applied. For each kind the
    scenario expects, the delta equals this machine's own `kind` evs since seq0."""
    fails = []
    for k in kinds:
        d = (after.get(k) or 0) - (before.get(k) or 0)
        n = sum(1 for e in evs if e["kind"] == k)
        if d != n:
            fails.append(f"{name} cueCounts.{k} +{d} but its event_log has {n} `{k}` ev(s) since seq {seq0} "
                         f"(want equal)")
    return fails


def last_cue_fails(lc, aid, seq, unit_id, corpse_ids):
    lc = lc or {}
    pl = lc.get("payload") or {}
    if (lc.get("kind") != "corpse" or aid is None or lc.get("actionId") != aid or lc.get("seq") != seq
            or pl.get("unit") != unit_id or pl.get("corpses") != corpse_ids):
        return [f"client lastCue={lc or None} (want kind corpse, actionId {aid}, seq {seq}, payload.unit "
                f"{unit_id}, payload.corpses {corpse_ids})"]
    return []


def context_fails(cb, ca):
    d = (ca["host"]["hostCombatContexts"] or 0) - (cb["host"]["hostCombatContexts"] or 0)
    if d != 1:
        return [f"host hostCombatContexts {cb['host']['hostCombatContexts']}->{ca['host']['hostCombatContexts']} "
                f"(+{d}; want +1)"]
    return []


def red_view(host_evs, client_evs):
    """The spec's red evidence in one dict: cue and bt_action_end evs per log."""
    return {"hostCues": [(e["seq"], e["kind"], e["actionId"]) for e in host_evs if e["kind"] in COMBAT_CUES],
            "clientCues": [(e["seq"], e["kind"], e["actionId"]) for e in client_evs if e["kind"] in COMBAT_CUES],
            "hostActionEnds": [(e["seq"], e["actionId"]) for e in host_evs if e["kind"] == "bt_action_end"],
            "clientActionEnds": [(e["seq"], e["actionId"]) for e in client_evs if e["kind"] == "bt_action_end"],
            "hostSyncs": [e["seq"] for e in host_evs if e["kind"] == "sync"],
            "clientSyncs": [e["seq"] for e in client_evs if e["kind"] == "sync"]}


def cue_delta(before, after):
    keys = sorted(set(before) | set(after))
    return {k: (after.get(k) or 0) - (before.get(k) or 0) for k in keys if (after.get(k) or 0) != (before.get(k) or 0)}


# ===================== W2-P6b S-D: the death records =====================

# The host's own coopEmitCue log line (connectionTCP.cpp): `[coop-cue] <kind> seq <n> actionId <a>: <payload>`.
CUE_RE = re.compile(r"\[coop-cue\] (\S+) seq (\d+) actionId (\d+): (\{.*\})\s*$", re.M)
DEATH_COUNT_KEYS = ("enqueued", "started", "completed", "cut", "instant")


def cue_payloads(host, seqs, timeout=5.0):
    """{seq: payload} from the HOST's own openxcom.log `[coop-cue]` lines for every seq in `seqs`, read with a
    bounded wait for the log write to land (event_log carries no payload)."""
    path = os.path.join(host.user_dir, "openxcom.log")
    want = set(s for s in seqs if s is not None)
    deadline = time.time() + timeout
    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        found = {}
        for m in CUE_RE.finditer(text):
            s = int(m.group(2))
            if s in want:
                try:
                    found[s] = json.loads(m.group(4))
                except ValueError as e:
                    found[s] = {"unparsed": m.group(4)[:300], "error": str(e)}
        if want <= set(found) or time.time() >= deadline:
            return found


def display_two(gc):
    """event_state displayTwo (W2-P6b S-D.1) of this machine ({} when absent)."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return es.get("displayTwo") or {}


def death_of(dt):
    return (dt or {}).get("death") or {}


def death_counts(dt):
    c = death_of(dt).get("counts") or {}
    return {k: c.get(k) for k in DEATH_COUNT_KEYS}


def rng_of(gc):
    return event_state(gc).get("rngSeed")


def death_snap(host, client):
    """The row's S-D starting point: both machines' displayTwo and the client's rngSeed."""
    return {"dt": {"host": display_two(host), "client": display_two(client)}, "rng": rng_of(client)}


def death_schedule(front, octants, is_ms, frames, respawn):
    """AMENDMENT P6b-2 (TASK 0b, F1764/F1765; replaces section 8 D-e's tick model): the host's traced death
    schedule in ms from the victim's first think. A `front` death (the host's state stack was empty at the push)
    turns its first octant at +0, a queued head at +Is; later octants every Is; the last octant -> startFalling
    (tc) takes 2 x Ic - Is; isOut = tc + F x Ic (a respawn victim consumes every frame in tc's own tick, so
    isOut = tc); pop = isOut + 2 x Ic. Ic = DEATH_IC after a pirouette (UnitDieBState :183); a victim already
    facing 3 (no pirouette, recorded untested) keeps the inherited Is and falls at its first think."""
    if octants > 0:
        ic = DEATH_IC
        tc = (0 if front else is_ms) + (octants - 1) * is_ms + 2 * ic - is_ms
    else:
        ic = is_ms
        tc = 0 if front else is_ms
    is_out = tc if respawn else tc + frames * ic
    return {"Ic": ic, "tc": tc, "isOutMs": is_out, "popMs": is_out + 2 * ic}


def wait_death_ghosts_ended(client, notes, timeout=DEATH_SETTLE_S):
    """Bounded: every death ghost the client enqueued has ended (completed + cut == enqueued)."""
    def ended():
        c = death_counts(display_two(client))
        return ((c["completed"] or 0) + (c["cut"] or 0) == (c["enqueued"] or 0)) or None
    try:
        client.wait_for("the client's death ghosts ended (completed + cut == enqueued)", ended, timeout=timeout,
                        interval=0.1)
    except Exception as e:
        notes.append(f"client death ghosts: {short(e)}")


def death_row(tag, host, client, snap0, wants=(), extra=None):
    """Section 2 rows D1-D5 after the row's chain settled. `wants` = the expected client death records in the
    host's queue order, each {seq, actionId, unit, payload (the pinned subset), front (None = only equal to the
    payload's), fromDir, octants, respawn, Is, sounds, startedAfterSeq, overKill, endedBy, and optionally
    unitDyingSet, unitDyingCleared, dirsShown, phasesShown, headStartedAtEnqueue (S-D.3, D3 only), payloadFront
    (False: the payload's `front` is checked through the record only)}. Prints ONE "EVIDENCE <tag>:" line, returns
    fails.
    Common (section 2 "All rows"): the client's rngSeed unchanged across the row, the host's displayTwo all zero,
    the client's completed + cut == enqueued; D-S3: frames, sound lists and overKill equal on both machines and
    equal the pins."""
    dt1 = {"host": display_two(host), "client": display_two(client)}
    rng1 = rng_of(client)
    uh, uc = units(host), units(client)
    pl = cue_payloads(host, [w["seq"] for w in wants])
    ring = death_of(dt1["client"]).get("ring") or []
    c0, c1 = death_counts(snap0["dt"]["client"]), death_counts(dt1["client"])
    hd = death_of(dt1["host"])
    recs = {w["seq"]: [r for r in ring if w["seq"] is not None and r.get("seq") == w["seq"]] for w in wants}
    lists = {w["unit"]: {n: {k: (u.get(w["unit"]) or {}).get(k) for k in ("deathSounds", "deathFrames", "overKill",
                                                                          "fallPhase", "status", "health")}
                         for n, u in (("host", uh), ("client", uc))} for w in wants}
    print(f"EVIDENCE {tag}: " + json.dumps({
        "payloads": {str(s): pl.get(s) for s in recs}, "records": {str(s): r for s, r in recs.items()},
        "clientCounts": {"before": c0, "after": c1},
        "clientQueued": death_of(dt1["client"]).get("queued"), "ringSeqs": [r.get("seq") for r in ring],
        "hostDisplayTwo": dt1["host"], "units": {str(u): v for u, v in lists.items()},
        "rngClient": {"before": snap0["rng"], "after": rng1},
        "want": wants, "extra": extra}, sort_keys=True, default=str), flush=True)
    fails = []
    # the additive `front` on each death payload (ST1 a) and the pinned payload subset
    for w in wants:
        p = pl.get(w["seq"]) if w["seq"] is not None else None
        if p is None:
            fails.append(f"{tag}: no host `death` payload for seq {w['seq']}")
            continue
        sub = {k: p.get(k) for k in w["payload"]}
        if sub != w["payload"]:
            fails.append(f"{tag}: host death payload seq {w['seq']} {sub} (want {w['payload']})")
        if not w.get("payloadFront", True):
            continue   # D5: `front` is read through its record only (record front == payload front)
        if "front" not in p or not isinstance(p.get("front"), bool):
            want_f = "a bool" if w["front"] is None else str(w["front"]).lower()
            fails.append(f"{tag}: host death payload seq {w['seq']} has no `front` (want {want_f}; payload {p})")
        elif w["front"] is not None and p["front"] is not w["front"]:
            fails.append(f"{tag}: host death payload seq {w['seq']} front={p['front']} (want {w['front']})")
    # the client's death records
    missing = [w["seq"] for w in wants if len(recs[w["seq"]]) != 1]
    if missing:
        fails.append(f"{tag}: client displayTwo.death has no single record for the death seq(s) {missing} (records "
                     f"per seq {[(s, len(r)) for s, r in recs.items()]}; ring seqs {[r.get('seq') for r in ring]}; "
                     f"counts {c0} -> {c1}; want exactly one record per death and enqueued +{len(wants)})")
    else:
        d_enq = (c1["enqueued"] or 0) - (c0["enqueued"] or 0)
        d_inst = (c1["instant"] or 0) - (c0["instant"] or 0)
        if d_enq != len(wants) or d_inst != 0:
            fails.append(f"{tag}: client displayTwo.death counts {c0} -> {c1} (want enqueued +{len(wants)}, "
                         f"instant +0)")
        if (c1["completed"] or 0) + (c1["cut"] or 0) != (c1["enqueued"] or 0):
            fails.append(f"{tag}: client displayTwo.death counts {c1} (want completed + cut == enqueued)")
        for w in wants:
            r = recs[w["seq"]][0]
            p = pl.get(w["seq"]) or {}
            unit_c = uc.get(w["unit"]) or {}
            frames = unit_c.get("deathFrames")
            want = {"actionId": w["actionId"], "unit": w["unit"], "instant": False, "outcome": w["payload"]["outcome"],
                    "front": p.get("front") if w["front"] is None else w["front"], "fromDir": w["fromDir"],
                    "octants": w["octants"], "frames": DEATH_F, "respawn": w["respawn"], "Is": w["Is"],
                    "startedAfterSeq": w["startedAfterSeq"], "overKill": w["overKill"], "endedBy": w["endedBy"]}
            want.update(death_schedule(want["front"], w["octants"], w["Is"], DEATH_F, w["respawn"]))
            for k in ("unitDyingSet", "unitDyingCleared", "dirsShown", "phasesShown", "headStartedAtEnqueue"):
                if k in w:
                    want[k] = w[k]
            got = {k: r.get(k) for k in want}
            bad = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
            if bad:
                fails.append(f"{tag}: client death record seq {w['seq']} (got, want) {bad} (record {r})")
            if not w.get("payloadFront", True) and not isinstance(p.get("front"), bool):
                fails.append(f"{tag}: host death payload seq {w['seq']} front={p.get('front')!r} (want a bool)")
            if (3 - (r.get("fromDir") or 0)) % 8 != r.get("octants"):
                fails.append(f"{tag}: record seq {w['seq']} octants {r.get('octants')} != (3 - fromDir "
                             f"{r.get('fromDir')}) mod 8")
            if frames != DEATH_F:
                fails.append(f"{tag}: client battle_state deathFrames of {w['unit']} = {frames} (want {DEATH_F})")
            snd = r.get("sound")
            if w["payload"]["outcome"] == "dead":
                if snd not in w["sounds"]:
                    fails.append(f"{tag}: record seq {w['seq']} sound {snd} (want one of {w['sounds']})")
            elif snd != NO_SOUND:
                fails.append(f"{tag}: record seq {w['seq']} sound {snd} (want {NO_SOUND}: a stun plays none)")
    # D-S3: the watcher's inputs equal the host's and the pins
    for w in wants:
        lh, lc = lists[w["unit"]]["host"], lists[w["unit"]]["client"]
        if lh["deathSounds"] != w["sounds"] or lc["deathSounds"] != w["sounds"]:
            fails.append(f"{tag}: deathSounds of {w['unit']} host={lh['deathSounds']} client={lc['deathSounds']} "
                         f"(want {w['sounds']} on both: D-S3)")
        if lh["deathFrames"] != DEATH_F or lc["deathFrames"] != DEATH_F:
            fails.append(f"{tag}: deathFrames of {w['unit']} host={lh['deathFrames']} client={lc['deathFrames']} "
                         f"(want {DEATH_F} on both: D-S3)")
        if lh["overKill"] != w["overKill"] or lc["overKill"] != w["overKill"]:
            fails.append(f"{tag}: overKill of {w['unit']} host={lh['overKill']} client={lc['overKill']} "
                         f"(want {w['overKill']} on both: D-S3, ST4)")
    # common: the host never ghosts, the client's sim RNG untouched
    hc_ = hd.get("counts") or {}
    if (not hd or any((hc_.get(k) or 0) != 0 for k in DEATH_COUNT_KEYS) or (hd.get("queued") or 0) != 0
            or hd.get("ring")):
        fails.append(f"{tag}: host displayTwo {dt1['host']} (want the death counts all 0, queued 0, no record)")
    if snap0["rng"] is None or rng1 != snap0["rng"]:
        fails.append(f"{tag}: client rngSeed {snap0['rng']} -> {rng1} (want unchanged: V4)")
    return fails


# ===================== W2-P6b S-E: the effect records =====================
# Spec rewrite/prompts/w2p6_display_two.md section 9 (S-E) and the P6b review's section 2 rows E1-E6, as ruled by
# AMENDMENTS P6b-1..P6b-3. Shared by test_w2_host_combat (E1 on C5), test_w2_client_melee_psi (E1 on C21, E2 on
# C22, the C23d rngSeed guard), test_w2_psi (E2), test_w2_client_items (E3), test_w2_client_grenade (E4) and
# test_w2_turn_cues (E5, E6). "All rows" (review section 2): the client's rngSeed unchanged across the row (V4), the
# host's displayTwo and combatGhost all zero (the host plays vanilla's own), and completed + cut == enqueued per S-E
# record kind on the client. No wall-clock duration is asserted: every schedule field equals the rule chain
# computed here from display_rules (E-S1 = STOP).

HIT_FRAMES = 4                   # Explosion::HIT_FRAMES (display_rules constants on the S-E.1 build, both machines)
HALF_ANIM_MS = 50                # BattlescapeState::DEFAULT_ANIM_SPEED / 2 (ExplosionBState.cpp :277)
# display_rules on the S-E.1 build (main menu, bare and with Coop_Spray_Test: identical; both machines per row):
# the fields the melee / psi / medikit / prime chains read.
EFFECT_PINS = {
    "STR_STUN_ROD": {"meleeAnimation": 0, "meleeAnimationFrames": -1, "explosionSpeed": 0,
                     "soundLists": {"meleeSound": [54], "meleeHitSound": []}},
    "STR_PSI_AMP": {"meleeAnimation": 0, "meleeAnimationFrames": -1, "psiAnimation": -1, "psiAnimationFrames": -1,
                    "explosionSpeed": 0, "soundLists": {"hitSound": [36], "psiSound": []}},
    "ALIEN_PSI_WEAPON": {"meleeAnimation": 0, "meleeAnimationFrames": -1, "psiAnimation": -1,
                         "psiAnimationFrames": -1, "explosionSpeed": 0,
                         "soundLists": {"hitSound": [36], "psiSound": []}},
    "STR_MEDI_KIT": {"soundLists": {"hitSound": []}},
    "STR_GRENADE": {"soundLists": {"primeSound": [], "unprimeSound": []}},
}
FALL_KEYS = ("enqueued", "completed", "cut")


def effects_of(dt):
    return (dt or {}).get("effects") or {}


def combat_ghost(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return es.get("combatGhost") or {}


def effect_snap(host, client):
    """An S-E row's starting point: both machines' displayTwo and combatGhost, and the client's rngSeed."""
    return {"dt": {"host": display_two(host), "client": display_two(client)},
            "cg": {"host": combat_ghost(host), "client": combat_ghost(client)}, "rng": rng_of(client)}


def effect_rules(host, client, types):
    """display_rules of `types` on BOTH machines. Returns (the client's items, fails): the machines must agree, the
    constants carry HIT_FRAMES, and every EFFECT_PINS field of a pinned type equals its pin."""
    types = sorted(set(t for t in types if t))
    rc = client.cmd({"cmd": "display_rules", "types": types})
    rh = host.cmd({"cmd": "display_rules", "types": types})
    fails = []
    if not rc.get("ok") or not rh.get("ok"):
        return {}, [f"display_rules {types} failed: host={rh} client={rc}"]
    items = rc.get("items") or {}
    if items != rh.get("items") or rc.get("constants") != rh.get("constants"):
        fails.append(f"display_rules {types} differ host={rh} client={rc} (want equal)")
    if (rc.get("constants") or {}).get("HIT_FRAMES") != HIT_FRAMES:
        fails.append(f"display_rules constants {rc.get('constants')} (want HIT_FRAMES {HIT_FRAMES})")
    for t in types:
        it = items.get(t)
        if it is None:
            fails.append(f"display_rules knows no {t}")
            continue
        pin = EFFECT_PINS.get(t) or {}
        got = {k: it.get(k) for k in pin if k != "soundLists"}
        want = {k: v for k, v in pin.items() if k != "soundLists"}
        got["soundLists"] = {k: (it.get("soundLists") or {}).get(k) for k in pin.get("soundLists", {})}
        want["soundLists"] = pin.get("soundLists", {})
        if got != want:
            fails.append(f"display_rules {t} {got} (want the pins {want})")
    return items, fails


def pick_ok(got, ids):
    """A sound picked from the raw list `ids` (F1512 / V4): -1 for an empty list (vanilla plays none), the id for a
    one-id list, one of the ids otherwise (F1539)."""
    if not ids:
        return got == NO_SOUND
    return got == ids[0] if len(ids) == 1 else got in ids


def pick_want(ids):
    return NO_SOUND if not ids else (ids[0] if len(ids) == 1 else f"one of {ids}")


def opt_value(old, new):
    """ExplosionBState::optValue: take `new` unless it is -1."""
    return new if new != -1 else old


def impact_expect(rules, kind, payload):
    """Section 9 E-b (ExplosionBState.cpp :277-:365 and :438-:444, the hit branch, success true): the melee / psi
    record's rule chain from the payload's weaponType / itemType. melee: the weapon's melee animation / frames /
    sound, each optValue'd by the damage item's when itemType != weaponType; soundEnd = the melee hit sound (the
    damage item's when set) iff power > 0. psi: the weapon's melee animation / frames, then its psi ones; sound =
    the weapon's hit sound, then its psi sound. intervalMs = max(1, 50 - 10 x explosionSpeed(itemType)); frames =
    animFrames when > 0 else HIT_FRAMES; ms = frames x intervalMs."""
    wt = payload.get("weaponType")
    it = payload.get("itemType") or wt
    w = rules.get(wt) or {}
    d = (rules.get(it) or {}) if it != wt else None
    wl = w.get("soundLists") or {}
    anim = w.get("meleeAnimation", -1)
    frames = w.get("meleeAnimationFrames", -1)
    ends = []
    if kind == "psi":
        sounds = wl.get("hitSound") or []
        anim = opt_value(anim, w.get("psiAnimation", -1))
        frames = opt_value(frames, w.get("psiAnimationFrames", -1))
        if wl.get("psiSound"):
            sounds = wl["psiSound"]
    else:
        sounds = wl.get("meleeSound") or []
        dl = (d or {}).get("soundLists") or {}
        if d is not None:
            anim = opt_value(anim, d.get("meleeAnimation", -1))
            frames = opt_value(frames, d.get("meleeAnimationFrames", -1))
            if dl.get("meleeSound"):
                sounds = dl["meleeSound"]
        if (payload.get("power") or 0) > 0:
            ends = wl.get("meleeHitSound") or []
            if d is not None and dl.get("meleeHitSound"):
                ends = dl["meleeHitSound"]
    interval = max(1, HALF_ANIM_MS - 10 * ((rules.get(it) or {}).get("explosionSpeed") or 0))
    n = frames if frames > 0 else HIT_FRAMES
    return {"frame": anim, "frames": n, "intervalMs": interval, "ms": n * interval, "sounds": sounds,
            "soundEnds": ends}


def effect_common_fails(tag, host, client, snap0, dt1=None, cg1=None):
    """Section 2 "All rows" for S-E: the client's rngSeed unchanged across the row (V4); the host's displayTwo (death
    and effects) and combatGhost all zero (the host plays vanilla's own display); on the client completed + cut ==
    enqueued for combatGhost melee / psi and displayTwo.effects.fall."""
    fails = []
    dt1 = dt1 or {"host": display_two(host), "client": display_two(client)}
    cg1 = cg1 or {"host": combat_ghost(host), "client": combat_ghost(client)}
    rng1 = rng_of(client)
    if snap0["rng"] is None or rng1 != snap0["rng"]:
        fails.append(f"{tag}: client rngSeed {snap0['rng']} -> {rng1} (want unchanged: V4)")
    hd, he = death_of(dt1["host"]), effects_of(dt1["host"])
    hdc = hd.get("counts") or {}
    hz = (all((hdc.get(k) or 0) == 0 for k in DEATH_COUNT_KEYS) and not (hd.get("queued") or 0) and not hd.get("ring")
          and all(((he.get(k) or {}).get("count") or 0) == 0 and not (he.get(k) or {}).get("ring")
                  for k in ("medikit", "prime", "panic"))
          and all(((he.get("fall") or {}).get(k) or 0) == 0 for k in FALL_KEYS)
          and not (he.get("fall") or {}).get("ring") and not (he.get("fall") or {}).get("seen"))
    if not dt1["host"] or not he or not hz:
        fails.append(f"{tag}: host displayTwo {dt1['host']} (want every death / effect count 0 and no record: the "
                     f"host never ghosts)")
    hc = cg1["host"]
    kinds = ("shot", "hit", "explosion", "melee", "psi")
    hcz = all(((hc.get(g) or {}).get(k) or 0) == 0 for g in ("enqueued", "completed", "cut") for k in kinds) \
        and not (hc.get("live") or 0) and not hc.get("ring")
    if not hc or not hcz:
        fails.append(f"{tag}: host combatGhost {{enqueued {hc.get('enqueued')}, completed {hc.get('completed')}, cut "
                     f"{hc.get('cut')}, live {hc.get('live')}, ring {len(hc.get('ring') or [])}}} (want all zero)")
    cc = cg1["client"]
    for k in ("melee", "psi"):
        e, c, u = ((cc.get(g) or {}).get(k) for g in ("enqueued", "completed", "cut"))
        if e is None or c is None or u is None or c + u != e:
            fails.append(f"{tag}: client combatGhost {k}: enqueued {e} completed {c} cut {u} (want the slot present "
                         f"and completed + cut == enqueued)")
    cf = (effects_of(dt1["client"]).get("fall") or {})
    e, c, u = (cf.get(k) for k in FALL_KEYS)
    if e is None or c is None or u is None or c + u != e:
        fails.append(f"{tag}: client displayTwo.effects.fall {{enqueued {e}, completed {c}, cut {u}}} (want present, "
                     f"completed + cut == enqueued)")
    return fails


def impact_row(tag, host, client, snap0, cues, weapon):
    """Rows E1 (melee) / E2 (psi) (review section 2; section 9 E-b): `cues` = [(seq, kind)] of the row's host melee /
    psi cues (payloads from the host's `[coop-cue]` lines). Each wants ONE client combatGhost ring record of that seq
    and kind, unresolved / noMap false, with the rule chain's frame, frames, intervalMs, ms and sound (melee: and
    soundEnd; psi: `voxel` == the payload's voxel, Q11 - the payload gains it at S-E.2), and the payload's
    weaponType == `weapon`, success true; client combatGhost.enqueued.<kind> +1 per cue; the S-E common asserts.
    Prints ONE "EVIDENCE <tag>:" line, returns fails."""
    dt1 = {"host": display_two(host), "client": display_two(client)}
    cg1 = {"host": combat_ghost(host), "client": combat_ghost(client)}
    pl = cue_payloads(host, [s for s, _ in cues])
    types = {weapon} | {(pl.get(s) or {}).get(k) for s, _ in cues for k in ("weaponType", "itemType")}
    rules, rfails = effect_rules(host, client, types)
    ring = cg1["client"].get("ring") or []
    recs = {s: [r for r in ring if r.get("seq") == s and s is not None] for s, _ in cues}
    exp = {s: impact_expect(rules, k, pl.get(s) or {}) for s, k in cues}
    enq0 = {k: ((snap0["cg"]["client"].get("enqueued") or {}).get(k)) for k in ("melee", "psi")}
    enq1 = {k: ((cg1["client"].get("enqueued") or {}).get(k)) for k in ("melee", "psi")}
    print(f"EVIDENCE {tag}: " + json.dumps({
        "cues": [(s, k) for s, k in cues], "payloads": {str(s): pl.get(s) for s, _ in cues},
        "records": {str(s): r for s, r in recs.items()}, "expected": {str(s): e for s, e in exp.items()},
        "clientEnqueued": {"before": enq0, "after": enq1}, "ringSeqs": [(r.get("seq"), r.get("kind")) for r in ring],
        "rules": rules, "hostCombatGhost": {k: cg1["host"].get(k) for k in ("enqueued", "completed", "cut", "live")},
        "hostEffects": effects_of(dt1["host"]), "rngClient": {"before": snap0["rng"], "after": rng_of(client)}},
        sort_keys=True, default=str), flush=True)
    fails = list(rfails)
    if not cues or any(s is None for s, _ in cues):
        fails.append(f"{tag}: the row's host melee / psi cues {cues} (want each with a seq)")
    for s, k in cues:
        p = pl.get(s) or {}
        if p.get("weaponType") != weapon or p.get("success") is not True:
            fails.append(f"{tag}: host {k} payload seq {s} weaponType={p.get('weaponType')} success={p.get('success')} "
                         f"(want {weapon}, true)")
        if k == "psi" and not isinstance(p.get("voxel"), dict):
            fails.append(f"{tag}: host psi payload seq {s} has no `voxel` (want the additive voxel, Q11; payload {p})")
        if len(recs[s]) != 1:
            fails.append(f"{tag}: client combatGhost ring has {len(recs[s])} record(s) for the {k} seq {s} (want "
                         f"exactly one of kind {k}; ring (seq, kind) {[(r.get('seq'), r.get('kind')) for r in ring]})")
            continue
        r, e = recs[s][0], exp[s]
        got = {x: r.get(x) for x in ("kind", "unresolved", "noMap", "frame", "frames", "intervalMs", "ms")}
        want = {"kind": k, "unresolved": False, "noMap": False, "frame": e["frame"], "frames": e["frames"],
                "intervalMs": e["intervalMs"], "ms": e["ms"]}
        if got != want:
            fails.append(f"{tag}: client {k} record seq {s} {got} (want {want}: the rule chain, E-S1)")
        if not pick_ok(r.get("sound"), e["sounds"]):
            fails.append(f"{tag}: client {k} record seq {s} sound {r.get('sound')} (want {pick_want(e['sounds'])})")
        if k == "melee" and not pick_ok(r.get("soundEnd"), e["soundEnds"]):
            fails.append(f"{tag}: client melee record seq {s} soundEnd {r.get('soundEnd')} (want "
                         f"{pick_want(e['soundEnds'])}: the melee hit sound iff power > 0)")
        if k == "psi" and (r.get("voxel") is None or r.get("voxel") != p.get("voxel")):
            fails.append(f"{tag}: client psi record seq {s} voxel {r.get('voxel')} (want the payload's {p.get('voxel')})")
    for k in ("melee", "psi"):
        n = sum(1 for _, kk in cues if kk == k)
        d = (enq1[k] or 0) - (enq0[k] or 0)
        if d != n:
            fails.append(f"{tag}: client combatGhost.enqueued.{k} {enq0[k]} -> {enq1[k]} (+{d}; want +{n}: one ghost "
                         f"per applied `{k}` cue)")
    fails += effect_common_fails(tag, host, client, snap0, dt1, cg1)
    return fails


def sound_row(tag, host, client, snap0, kind, wants, extra=None):
    """Rows E3 (medikit), E4 (prime), E5 (panic) (review section 2; section 9 E-c/E-d/E-e): the client's
    displayTwo.effects.<kind>.count +len(wants); per want ONE client record - matched by `match` (its seq) when the
    want has one, else the row's i-th new record in order (the prime aftermath has no seq) - whose `fields` equal
    the want's and whose sound is picked from `sounds` (-1 for an empty list, F1782); the host's count 0 (it plays
    vanilla's own); the S-E common asserts. Prints ONE "EVIDENCE <tag>:" line, returns fails."""
    dt1 = {"host": display_two(host), "client": display_two(client)}
    c0 = (effects_of(snap0["dt"]["client"]).get(kind) or {}).get("count")
    ce = effects_of(dt1["client"]).get(kind) or {}
    ring = ce.get("ring") or []
    d_new = (ce.get("count") or 0) - (c0 or 0)
    new = ring[-d_new:] if d_new > 0 else []
    found = []
    for i, w in enumerate(wants):
        if "match" in w:
            found.append([r for r in ring if all(r.get(k) == v and v is not None for k, v in w["match"].items())])
        else:
            found.append(new[i:i + 1])
    print(f"EVIDENCE {tag}: " + json.dumps({
        "kind": kind, "want": wants, "records": found, "clientCount": {"before": c0, "after": ce.get("count")},
        "clientRing": ring, "hostEffects": effects_of(dt1["host"]), "extra": extra,
        "rngClient": {"before": snap0["rng"], "after": rng_of(client)}}, sort_keys=True, default=str), flush=True)
    fails = []
    d = (ce.get("count") or 0) - (c0 or 0)
    if c0 is None or ce.get("count") is None or d != len(wants):
        fails.append(f"{tag}: client displayTwo.effects.{kind}.count {c0} -> {ce.get('count')} (want +{len(wants)}: one "
                     f"record per applied cue)")
    for i, (w, rs) in enumerate(zip(wants, found)):
        which = w.get("match") or f"new record #{i + 1}"
        if len(rs) != 1:
            fails.append(f"{tag}: client effects.{kind} records for {which}: {len(rs)} (want exactly one; ring {ring})")
            continue
        r = rs[0]
        got = {k: r.get(k) for k in w["fields"]}
        if got != w["fields"]:
            fails.append(f"{tag}: client effects.{kind} record {which} {got} (want {w['fields']})")
        if not pick_ok(r.get("sound"), w["sounds"]):
            fails.append(f"{tag}: client effects.{kind} record {which} sound {r.get('sound')} (want "
                         f"{pick_want(w['sounds'])})")
    fails += effect_common_fails(tag, host, client, snap0, dt1)
    return fails


# ===================== scenarios =====================


def c1_snap_kill(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": C1_ITEMS[0], "ammo": C1_ITEMS[1],
                            "clear_hands": True}, ("weaponId", "ammoId"))
    rifle, clip = g["weaponId"], g["ammoId"]
    tele_both(host, client, H_ID, C1_H_TILE, C1_H_DIR)
    tele_both(host, client, A_ID, C1_A_TILE, C1_A_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "health": C1_A_HEALTH},
         ("health", "stun", "status"))
    tu_both(host, client, H_ID)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": H_ID, "stat": "firing",
                        "value": FIRING_120}, ("tu",))
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    aliens = sorted(uid for uid, u in uh0.items() if u.get("faction") == FACTION_HOSTILE)
    morale0 = {uid: uh0[uid].get("morale") for uid in aliens}
    ih0, ic0 = items_by_id(host), items_by_id(client)
    w0 = {"host": ih0.get(A_WEAPON), "client": ic0.get(A_WEAPON)}
    spotted0 = battle_state(host).get("spotted")
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    snap_d = death_snap(host, client)   # W2-P6b S-D row D1
    seq0 = before["host"]["lastSeqEmitted"] or 0
    cursor0 = None
    try:
        cursor0 = open_hand_menu_host(host)
        press(host, KEY_ITEM2)
        host.wait_for("host BattlescapeState on top after SNAP", lambda: top(host) == "BattlescapeState" or None,
                      timeout=5)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": C1_A_TILE[0], "y": C1_A_TILE[1], "z": C1_A_TILE[2]})
        assert pr.get("verified"), f"map_tile_click_pos did not verify A's tile {C1_A_TILE}: {pr}"
        host.ok({"cmd": "set_seed", "seed": SEED_C1})
        host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        host.wait_for("host shot chain finished (A DEAD, no BState)",
                      lambda: host_chain_done(host, A_ID, STATUS_DEAD), timeout=30)
    except Exception as e:
        notes.append(f"host snap shot: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the shot: {short(e)}")
    wait_death_ghosts_ended(client, notes)
    uh, uc = units(host), units(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    corpses = {"host": [i for i in ih.values() if i["type"] == A_CORPSE and i.get("unitLink") == A_ID],
               "client": [i for i in ic.values() if i["type"] == A_CORPSE and i.get("unitLink") == A_ID]}
    w1 = {"host": ih.get(A_WEAPON), "client": ic.get(A_WEAPON)}
    clip1 = {"host": (ih.get(clip) or {}).get("qty"), "client": (ic.get(clip) or {}).get("qty")}
    morale1 = {uid: {"host": (uh.get(uid) or {}).get("morale"), "client": (uc.get(uid) or {}).get("morale")}
               for uid in aliens}
    idiff = item_diff(ih, ic)
    aid, chain, cfails = chain_fails(hev, cev, "shot", C1_CHAIN, seq0)
    print(f"EVIDENCE C1: staged rifle={rifle} clip={clip} H->{C1_H_TILE}/{C1_H_DIR} A->{C1_A_TILE}/{C1_A_DIR} "
          f"stagedDiff={staged_diff} cursorType(before[, after the aim-cancel click])={cursor0} spotted {spotted0}->"
          f"{battle_state(host).get('spotted')}; hostCombatContexts host {cb['host']['hostCombatContexts']}->"
          f"{ca['host']['hostCombatContexts']} client {cb['client']['hostCombatContexts']}->"
          f"{ca['client']['hostCombatContexts']}; host evs since seq {seq0}={ev_tuples(hev)} "
          f"client evs={ev_tuples(cev)} (seq, kind, actionId, h); red view={red_view(hev, cev)}; "
          f"action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; cueCounts delta host="
          f"{cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} client="
          f"{cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue host="
          f"{ca['host']['lastCue']} client={ca['client']['lastCue']}; A before host={unit_brief(uh0.get(A_ID))} "
          f"after host={unit_brief(uh.get(A_ID))} client={unit_brief(uc.get(A_ID))}; H after host="
          f"{unit_brief(uh.get(H_ID))} client={unit_brief(uc.get(H_ID))}; clip {clip} qty={clip1}; corpses="
          f"{corpses}; weapon {A_WEAPON} before={w0} after={w1}; items total host={len(ih)} client={len(ic)} "
          f"hostOnly={sorted(idiff['hostOnly'])} clientOnly={sorted(idiff['clientOnly'])} "
          f"differ={idiff['differ']}; morale before(host)={morale0} after={morale1}; client desyncSeen="
          f"{pc['desyncSeen']} desync={dsc} host desyncSeen={ph['desyncSeen']}; diffAfterShot={end_diff}; "
          f"host syncEvsEmitted {before['host']['syncEvsEmitted']}->{ph['syncEvsEmitted']} client "
          f"syncEvsApplied {before['client']['syncEvsApplied']}->{pc['syncEvsApplied']}; host lastDelta="
          f"{ph['lastDelta']} client lastDelta={pc['lastDelta']}; host {delta_view(before['host'])}->"
          f"{delta_view(ph)}; client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}",
          flush=True)
    # W2-P6b S-D row D1 (review section 2; AMENDMENT P6b-2's schedule): A's animated death on the client
    d1 = death_row("D1", host, client, snap_d, [
        {"seq": seq_of(chain, "death"), "actionId": aid, "unit": A_ID, "payload": C1_DEATH, "front": False,
         "fromDir": C1_A_DIR, "octants": 7, "respawn": False, "Is": DEATH_IS_TURN, "sounds": SECTOID_DEATH_SOUNDS,
         "startedAfterSeq": 0, "overKill": OVERKILL_NONE, "endedBy": "out", "unitDyingSet": False,
         "dirsShown": DIRS_4_TO_3, "phasesShown": PHASES_ALL}])
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    for name, it in w0.items():
        if not it or it.get("owner") != A_ID:
            fails.append(f"{name} weapon {A_WEAPON} before the shot {it} (want held by A)")
    # the action (spec (f) C1 GREEN)
    fails += context_fails(cb, ca)
    fails += cfails
    corpse_ids = [i["id"] for i in corpses["host"]]
    fails += last_cue_fails(ca["client"]["lastCue"], aid, seq_of(chain, "corpse"), A_ID, corpse_ids)
    fails += cue_count_fails("host", cb["host"]["cueCounts"], ca["host"]["cueCounts"], hev, C1_CHAIN[1:-1], seq0)
    fails += cue_count_fails("client", cb["client"]["cueCounts"], ca["client"]["cueCounts"], cev, C1_CHAIN[1:-1],
                             seq0)
    # SB1's item / morale / onTile asserts
    if idiff["hostOnly"] or idiff["clientOnly"] or idiff["differ"]:
        fails.append(f"battle_items differ: hostOnly={sorted(idiff['hostOnly'])} "
                     f"clientOnly={sorted(idiff['clientOnly'])} differ={idiff['differ']} (want equal)")
    if len(corpse_ids) != 1:
        fails.append(f"host corpses linked to A: {corpse_ids} (want exactly 1 {A_CORPSE} with unitLink {A_ID})")
    for cid in corpse_ids:
        hcp, ccp = ih.get(cid), ic.get(cid)
        if not ccp:
            fails.append(f"corpse {cid} missing on the client (host {hcp})")
        elif (ccp.get("unitLink") != A_ID or ccp.get("type") != A_CORPSE or tile_of(ccp) != tile_of(hcp)
              or tile_of(hcp) is None):
            fails.append(f"corpse {cid} host={hcp} client={ccp} (want {A_CORPSE}, unitLink {A_ID}, the same "
                         f"tile on both)")
    for name, it in w1.items():
        if not it or it.get("owner") != -1 or not it.get("onTile") or it.get("previousOwner") != A_ID:
            fails.append(f"{name} weapon {A_WEAPON} after the shot {it} (want owner -1, onTile, previousOwner "
                         f"{A_ID})")
    if tile_of(w1["host"]) != tile_of(w1["client"]):
        fails.append(f"weapon {A_WEAPON} tile host={tile_of(w1['host'])} client={tile_of(w1['client'])} "
                     f"(want the same)")
    for name, u in (("host", uh.get(A_ID)), ("client", uc.get(A_ID))):
        if not u or u.get("status") != STATUS_DEAD or u.get("onTile") is not False:
            fails.append(f"{name} A {unit_view(u)} (want status DEAD ({STATUS_DEAD}), onTile false)")
    lowered = [uid for uid in aliens if (morale1[uid]["host"] is not None and morale0[uid] is not None
                                         and morale1[uid]["host"] < morale0[uid])]
    if not lowered:
        fails.append(f"no alien's morale lower on the host after the kill: before={morale0} after={morale1}")
    for uid in lowered:
        if morale1[uid]["host"] != morale1[uid]["client"]:
            fails.append(f"alien {uid} morale host={morale1[uid]['host']} client={morale1[uid]['client']} "
                         f"(want equal)")
    # H tu and the clip's qty equal on both
    th, tc = (uh.get(H_ID) or {}).get("tu"), (uc.get(H_ID) or {}).get("tu")
    if th is None or th != tc:
        fails.append(f"H tu host={th} client={tc} (want equal)")
    if clip1["host"] is None or clip1["host"] != clip1["client"]:
        fails.append(f"clip {clip} qty host={clip1['host']} client={clip1['client']} (want equal)")
    fails += d1
    fails += common_fails(host, client, before, {}, "C1")
    finish(fails)


def c5_stun(host, client, ctx):
    notes = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_STUN_ROD", "clear_hands": True},
             ("weaponId", "ammoId"))
    rod = g["weaponId"]
    tele_both(host, client, H_ID, C5_H_TILE, C5_H_DIR)
    tele_both(host, client, A2_ID, C5_A2_TILE, C5_A2_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": A2_ID, "health": C5_A2_HEALTH},
         ("health", "stun", "status"))
    tu_both(host, client, H_ID)
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    ih0, ic0 = items_by_id(host), items_by_id(client)
    w0 = {"host": ih0.get(A2_WEAPON), "client": ic0.get(A2_WEAPON)}
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": cue_probes(host), "client": cue_probes(client)}
    snap_d = death_snap(host, client)   # W2-P6b S-D row D2
    snap_e = effect_snap(host, client)  # W2-P6b S-E row E1
    seq0 = before["host"]["lastSeqEmitted"] or 0
    cursor0 = None
    try:
        cursor0 = open_hand_menu_host(host)
        host.ok({"cmd": "set_seed", "seed": SEED_C5})
        press(host, KEY_ITEM4)
        host.wait_for("host stun chain finished (A2 UNCONSCIOUS, no BState)",
                      lambda: host_chain_done(host, A2_ID, STATUS_UNCONSCIOUS), timeout=30)
    except Exception as e:
        notes.append(f"host stun: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the stun: {short(e)}")
    wait_death_ghosts_ended(client, notes)
    uh, uc = units(host), units(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    bodies = {"host": [i for i in ih.values() if i.get("unitLink") == A2_ID],
              "client": [i for i in ic.values() if i.get("unitLink") == A2_ID]}
    w1 = {"host": ih.get(A2_WEAPON), "client": ic.get(A2_WEAPON)}
    idiff = item_diff(ih, ic)
    aid, chain, cfails = chain_fails(hev, cev, "melee", C5_CHAIN, seq0)
    print(f"EVIDENCE C5: staged rod={rod} H->{C5_H_TILE}/{C5_H_DIR} A2->{C5_A2_TILE}/{C5_A2_DIR} "
          f"stagedDiff={staged_diff} cursorType(before[, after the aim-cancel click])={cursor0}; hostCombatContexts host "
          f"{cb['host']['hostCombatContexts']}->{ca['host']['hostCombatContexts']} client "
          f"{cb['client']['hostCombatContexts']}->{ca['client']['hostCombatContexts']}; host evs since seq "
          f"{seq0}={ev_tuples(hev)} client evs={ev_tuples(cev)} (seq, kind, actionId, h); red view="
          f"{red_view(hev, cev)}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; cueCounts delta "
          f"host={cue_delta(cb['host']['cueCounts'], ca['host']['cueCounts'])} client="
          f"{cue_delta(cb['client']['cueCounts'], ca['client']['cueCounts'])}; lastCue host="
          f"{ca['host']['lastCue']} client={ca['client']['lastCue']}; A2 before host={unit_brief(uh0.get(A2_ID))} "
          f"after host={unit_brief(uh.get(A2_ID))} client={unit_brief(uc.get(A2_ID))}; H after host="
          f"{unit_brief(uh.get(H_ID))} client={unit_brief(uc.get(H_ID))}; bodies={bodies}; weapon {A2_WEAPON} "
          f"before={w0} after={w1}; items total host={len(ih)} client={len(ic)} "
          f"hostOnly={sorted(idiff['hostOnly'])} clientOnly={sorted(idiff['clientOnly'])} "
          f"differ={idiff['differ']}; client desyncSeen={pc['desyncSeen']} desync={dsc} host desyncSeen="
          f"{ph['desyncSeen']}; diffAfterStun={end_diff}; host syncEvsEmitted {before['host']['syncEvsEmitted']}"
          f"->{ph['syncEvsEmitted']} client syncEvsApplied {before['client']['syncEvsApplied']}->"
          f"{pc['syncEvsApplied']}; host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; "
          f"host {delta_view(before['host'])}->{delta_view(ph)}; client {delta_view(before['client'])}->"
          f"{delta_view(pc)}; notes={notes}", flush=True)
    # W2-P6b S-D row D2 (review section 2): A2's animated stun collapse on the client, no sound (N6)
    d2 = death_row("D2", host, client, snap_d, [
        {"seq": seq_of(chain, "death"), "actionId": aid, "unit": A2_ID, "payload": C5_DEATH, "front": False,
         "fromDir": C5_A2_DIR, "octants": 7, "respawn": False, "Is": DEATH_IS_TURN, "sounds": SECTOID_DEATH_SOUNDS,
         "startedAfterSeq": 0, "overKill": OVERKILL_NONE, "endedBy": "out", "unitDyingSet": False,
         "dirsShown": DIRS_4_TO_3, "phasesShown": PHASES_ALL}])
    # W2-P6b S-E row E1 (review section 2; section 9 E-b): the host's stun-rod swing as a melee ghost on the client
    e1 = impact_row("E1", host, client, snap_e, [(seq_of(chain, "melee"), "melee")], "STR_STUN_ROD")
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    for name, it in w0.items():
        if not it or it.get("owner") != A2_ID:
            fails.append(f"{name} weapon {A2_WEAPON} before the stun {it} (want held by A2)")
    # the action (spec (f) C5 GREEN)
    fails += context_fails(cb, ca)
    fails += cfails
    body_ids = [i["id"] for i in bodies["host"]]
    fails += last_cue_fails(ca["client"]["lastCue"], aid, seq_of(chain, "corpse"), A2_ID, body_ids)
    fails += cue_count_fails("host", cb["host"]["cueCounts"], ca["host"]["cueCounts"], hev, C5_CHAIN[:-1], seq0)
    fails += cue_count_fails("client", cb["client"]["cueCounts"], ca["client"]["cueCounts"], cev, C5_CHAIN[:-1],
                             seq0)
    # A2 UNCONSCIOUS and stun equal on both
    sh, sc = uh.get(A2_ID) or {}, uc.get(A2_ID) or {}
    for name, u in (("host", sh), ("client", sc)):
        if u.get("status") != STATUS_UNCONSCIOUS:
            fails.append(f"{name} A2 {unit_view(u)} (want status UNCONSCIOUS ({STATUS_UNCONSCIOUS}))")
    if sh.get("stun") is None or sh.get("stun") != sc.get("stun"):
        fails.append(f"A2 stun host={sh.get('stun')} client={sc.get('stun')} (want equal)")
    # the body item (unitLink A2) equal on both
    if len(body_ids) != 1:
        fails.append(f"host items linked to A2: {body_ids} (want exactly 1 body item with unitLink {A2_ID})")
    for bid in body_ids:
        hb, cbd = ih.get(bid), ic.get(bid)
        if not cbd or hb != cbd or tile_of(hb) is None:
            fails.append(f"body item {bid} host={hb} client={cbd} (want equal on both, on a tile)")
    # A2's weapon on the ground on both
    for name, it in w1.items():
        if not it or it.get("owner") != -1 or not it.get("onTile"):
            fails.append(f"{name} weapon {A2_WEAPON} after the stun {it} (want owner -1, onTile)")
    if tile_of(w1["host"]) != tile_of(w1["client"]):
        fails.append(f"weapon {A2_WEAPON} tile host={tile_of(w1['host'])} client={tile_of(w1['client'])} "
                     f"(want the same)")
    fails += d2
    fails += e1
    fails += common_fails(host, client, before, {}, "C5")
    finish(fails)


def host_both_dead_idle(host, uids):
    """HOST only: every unit in `uids` DEAD, no BState queued or running (F823)."""
    bs = battle_state(host)
    ub = session.units_by_id(bs)
    return (all((ub.get(u) or {}).get("status") == STATUS_DEAD for u in uids) and bs.get("pendingStates") == 0
            and not bs.get("isBusy")) or None


def d3_burst(host, client, ctx):
    """W2-P6b S-D row D3 (review section 2, OR1 (a); AMENDMENT P6b-2 / T0b-2 = F1767): the kill-lever burst of
    seat 1. The host's evs are exactly D3_EVS (actionId 0: the lever opens no context); C's death is the host's
    front state (payload front true), C2's queues behind it (front false) and starts at C's pop with the
    interval C's pirouette left (Is 100). Client: V1 = C {startedAfterSeq 0, Is 33, 7 octants}, V2 = C2
    {startedAfterSeq = V1's seq, Is 100, 2 octants}; both set the Map's dying flag (player victims), V1's release
    clears it (V2's then finds it cleared); both end "out" at their own corpse ev.
    W2-P6b S-D.3 (AMENDMENT P6b-4, F1798/F1800): the client's death_apply_hold lever is on from before the kill
    lever to the end of the row, so V1 has started when V2 is enqueued in every run (the race order);
    V2's record headStartedAtEnqueue must be true."""
    notes = []
    uh0 = units(host)
    own = [uid for uid, t in ((C_ID, D3_C_TILE), (C2_ID, D3_C2_TILE))
           if ((uh0.get(uid) or {}).get("x"), (uh0.get(uid) or {}).get("y"), (uh0.get(uid) or {}).get("z")) == t]
    tele = {}
    if not own:   # S2: a unit is never teleported onto its own tile
        tele["C"] = tele_both(host, client, C_ID, D3_C_TILE, D3_C_DIR)
        tele["C2"] = tele_both(host, client, C2_ID, D3_C2_TILE, D3_C2_DIR)
    staged_diff = diff_buckets(host, client)
    staged = {n: {uid: unit_brief(u.get(uid)) for uid in (C_ID, C2_ID)}
              for n, u in (("host", units(host)), ("client", units(client)))}
    before = {"host": probes(host), "client": probes(client)}
    snap_d = death_snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    tops0 = (top(host), top(client))
    # S-D.3 (AMENDMENT P6b-4): the client's test-only hold, on before the kill lever
    hold_on = client.cmd({"cmd": "battle_action", "action": "death_apply_hold", "on": True})
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "coop_side": 1})
    try:
        host.wait_for("host C and C2 DEAD, no BState", lambda: host_both_dead_idle(host, (C_ID, C2_ID)), timeout=30)
    except Exception as e:
        notes.append(f"host kill chain: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the lever: {short(e)}")
    wait_death_ghosts_ended(client, notes)
    uh, uc = units(host), units(client)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    pl = cue_payloads(host, [e["seq"] for e in hev if e["kind"] in ("death", "corpse")])
    end_diff = diff_buckets(host, client)
    ph, pc = probes(host), probes(client)
    dsc = desync_record(client, pc["desyncSeen"])
    chain_ev = {"staged": {"C": (C_ID, D3_C_TILE, D3_C_DIR), "C2": (C2_ID, D3_C2_TILE, D3_C2_DIR), "tele": tele,
                           "ownTile": own, "stagedDiff": staged_diff, "units": staged},
                "topsBefore": tops0, "holdOn": hold_on, "lever": k, "seq0": seq0,
                "hostEvs": [(e["seq"], e["kind"], e["actionId"]) for e in hev],
                "clientEvs": [(e["seq"], e["kind"], e["actionId"]) for e in cev],
                "cuePayloads": {str(s): p for s, p in pl.items()},
                "after": {"host": {uid: unit_brief(uh.get(uid)) for uid in (C_ID, C2_ID)},
                          "client": {uid: unit_brief(uc.get(uid)) for uid in (C_ID, C2_ID)}},
                "topsAfter": (top(host), top(client)), "diff": end_diff, "desync": dsc,
                "hostDesyncSeen": ph["desyncSeen"], "notes": list(notes)}
    s1, s2 = (D3_EVS[0][0], D3_EVS[1][0])
    try:
        d3 = death_row("D3", host, client, snap_d, extra=chain_ev, wants=[
            {"seq": s1, "actionId": 0, "unit": C_ID, "payload": {k_: D3_DEATHS[s1][k_] for k_ in DEATH_KEYS},
             "front": True, "fromDir": D3_C_DIR, "octants": 7, "respawn": False, "Is": DEATH_IS_TURN,
             "sounds": SOLDIER_DEATH_SOUNDS, "startedAfterSeq": 0, "overKill": OVERKILL_NONE, "endedBy": "out",
             "unitDyingSet": True, "unitDyingCleared": True},
            {"seq": s2, "actionId": 0, "unit": C2_ID, "payload": {k_: D3_DEATHS[s2][k_] for k_ in DEATH_KEYS},
             "front": False, "fromDir": D3_C2_DIR, "octants": 2, "respawn": False, "Is": DEATH_IC,
             "sounds": SOLDIER_DEATH_SOUNDS, "startedAfterSeq": s1, "overKill": OVERKILL_NONE, "endedBy": "out",
             "unitDyingSet": True, "unitDyingCleared": False, "headStartedAtEnqueue": True}])
    finally:
        # S-D.3 (AMENDMENT P6b-4): the client's hold off after the row
        hold_off = client.cmd({"cmd": "battle_action", "action": "death_apply_hold", "on": False})
    fails = list(notes)
    if hold_on.get("ok") is not True or hold_on.get("on") is not True:
        fails.append(f"client death_apply_hold {{on: true}} answered {hold_on} (want ok, on true)")
    if hold_off.get("ok") is not True or hold_off.get("on") is not False:
        fails.append(f"client death_apply_hold {{on: false}} answered {hold_off} (want ok, on false)")
    if own:
        fails.append(f"units {own} already stand on their D3 tile (S2: never teleported onto their own tile)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    if seq0 != D3_SEQ0:
        fails.append(f"host lastSeqEmitted before the lever {seq0} (want {D3_SEQ0}: T0b-2)")
    if not k.get("ok") or k.get("killed") != D3_KILLED:
        fails.append(f"kill_unit_real {{coop_side: 1}} answered {k} (want ok, killed {D3_KILLED})")
    hv = [(e["seq"], e["kind"], e["actionId"]) for e in hev]
    cv = [(e["seq"], e["kind"], e["actionId"]) for e in cev]
    if hv != D3_EVS or cv != D3_EVS:
        fails.append(f"evs since seq {seq0} host={hv} client={cv} (want exactly {D3_EVS} on both)")
    for s, want in D3_CORPSES.items():
        got = {k_: (pl.get(s) or {}).get(k_) for k_ in want}
        if got != want:
            fails.append(f"host corpse payload seq {s} {got} (want {want})")
    for name, u in (("host", uh), ("client", uc)):
        for uid in (C_ID, C2_ID):
            v = u.get(uid) or {}
            if (v.get("status"), v.get("onTile"), v.get("direction")) != (STATUS_DEAD, False, DIR_FACING_3):
                fails.append(f"{name} unit {uid} {unit_brief(v)} (want status DEAD ({STATUS_DEAD}), onTile false, "
                             f"direction {DIR_FACING_3})")
    fails += d3
    fails += common_fails(host, client, before, {}, "D3")
    finish(fails)


SCENARIOS = (("C1", c1_snap_kill), ("C5", c5_stun), ("D3", d3_burst))


# ===================== bring-up =====================


def bring_up_lobby_roster_pinned(host, client, port):
    """raw.bring_up_lobby with ONE added call (amendment A2.2): set_seed
    SEED_ROSTER on the HOST immediately before its open_new_battle, so the
    roster (names and stats) the NEW BATTLE screen generates repeats."""
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
    raw.skirmish_host(host, port)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p2-sc")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
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
        assert (isinstance(es.get("hostCombatContexts"), int) and isinstance(es.get("cueCounts"), dict)
                and "lastCue" in es), (
            f"{gc.name} event_state lacks the S-C probes: hostCombatContexts={es.get('hostCombatContexts')!r} "
            f"cueCounts={es.get('cueCounts')!r} lastCue present={'lastCue' in es}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ph = probes(host)
    print(f"[w2p2-sc] boot ok: {MISSION} MAP_FP={MAP_FP!r} turn={hs['turn']} H={H_ID} "
          f"({(ub.get(H_ID) or {}).get('name')}) pinned={len(pinned)} host deltaArmed={ph['deltaArmed']} "
          f"deltaSeeds={ph['deltaSeeds']} probes host={cue_probes(host)} client={cue_probes(client)}",
          flush=True)
    return {}


def main():
    t0 = time.time()
    # W2-P6b S-D: coopGhostStepper pinned true in both instances (the D rows need the client's death ghosts)
    host = GameClient("host", 49846, make_user_dir("w2p2_host_combat_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49847, make_user_dir("w2p2_host_combat_client",
                                                       options={"coopGhostStepper": True}))
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
                print(f"[w2p2-sc] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_host_combat: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
