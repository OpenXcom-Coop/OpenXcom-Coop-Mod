"""W2-P4 S-E - test_w2_client_rules.py: the second player's spray autoshot and
its own force-fire key (spec rewrite/prompts/w2p4_client_combat_intents.md
section (f) "test_w2_client_rules.py (S-E)", sections (b)1 (the `shoot` kind's
`spray` and `forceFire` fields), (b)5 (K2) and (b)8 (F423, the per-player
half), as amended by AMENDMENT C2 (N34: set_touch_modifiers exists since S-A)
and AMENDMENT C4 (PR-Q20: K1 keeps refusing the spray start until S-E; F1168:
no lever could start a spray before S-E, so SEED_C18 was hunted on S-E1's red
build with the NEW battle_fire `spray` stand-in).

S-E1 writes C18 and C16f. S-E2 (commit S-E2.1) adds the skill rows C23s1,
C23s3 and C23s2 (the owner's D147 = (a), AMENDMENT C3 "D147 - soldier skills
as a two-step `skill` intent" sections 1-5 and its mechanism rulings C3-Q5..Q9;
the rows are C3 section 3's table).

Before S-E the second player cannot spray: its Ctrl+Shift click that starts a
spray (BattlescapeGame::primaryAction, an AUTO shot with a `sprayWaypoints`
weapon) is refused at K1 (client coopLocalExecBlocked +1, nothing sent). And the
host applies its OWN force-fire key to the partner's shot: inside the host's
execution of a client `shoot` order, the four force-fire terms F1-F4
(ProjectileFlyBState.cpp, Projectile.cpp x2, TileEngine.cpp) read
Options::forceFire && the HOST's isCtrlPressed(true). After S-E the spray is a
`shoot` intent carrying vanilla's spread voxels, and inside an `intent` context
F1-F4 read the order's own `forceFire` (the ordering machine's Options::forceFire
&& its own Ctrl), never the host's keys.

Five scenarios, ONE boot (the Coop_Spray_Test mod on both machines: STR_RIFLE
has sprayWaypoints 2, every STR_SOLDIER has the three test skills). C18 and
C16f first, in this order:

  C18    the spray. C gets a rifle + clip (lever, both, clear hands), C ->
         C_TILE facing east (dir 2), C TU max, C firing 120 (all on BOTH).
         Client: TAB-select C, the right-hand box, key 51 (AUTO), HOME, the
         client's own touch Ctrl + Shift ON (set_touch_modifiers on the client),
         one left click on SPRAY_W0 (starts the spray), host set_seed SEED_C18,
         one left click on SPRAY_W1 (vanilla fires: battleConfirmFireMode is off
         and Ctrl+Shift are held), then the client's touch flags OFF. RED: the
         spray start is refused at K1 (client coopLocalExecBlocked +1 at the
         SPRAY_W0 click; the flags stay latched, so the SPRAY_W1 click is a
         spray start too and is refused again), nothing sent. GREEN: the
         SPRAY_W0 click is local display (coopLocalExecBlocked unchanged,
         nothing sent); the SPRAY_W1 click is ONE order: host closedContexts
         gains {origin intent, kind shoot, actorId C} whose evs are exactly
         C18_CHAIN; its three `shot` cues have shotIndex 1, 2, 3 and
         waypointsLeft 2, 1, 0 (the spray shape), impactVoxels C18_IMPACTS, and
         each passes over its own spread waypoint's tile (C18_SPRAY, vanilla's
         spread of SPRAY_W0..SPRAY_W1); C TU C18_TU_AFTER and the clip
         C18_CLIP_AFTER on both.
  C16f   force-fire belongs to the ordering player. C gets a fresh rifle + clip
         (lever, both), C stays on C_TILE facing east (the turn C18 left),
         TU max, firing 120; A -> C16F_A_TILE facing west, A visible on both
         (set_stat visible). The HOST's touch Ctrl is ON for both legs. Leg 1:
         the client's real-UI snap at A's tile with its own Ctrl OFF (forceFire
         false), host set_seed SEED_C16F right before the click. Leg 2: C TU
         max (both), the same snap with the client's own touch Ctrl ON (set
         right before the click; forceFire true). At SEED_C16F the unforced shot
         (aimed at A) lands at C16F_UNFORCED and the forced one (the tile centre)
         at C16F_FORCED (T0-9f, measured with the host stand-in: host Ctrl OFF /
         ON). RED: with the host's Ctrl ON the partner's unforced leg-1 shot gets
         the FORCED value. GREEN: leg 1 -> C16F_UNFORCED, leg 2 -> C16F_FORCED,
         both with the host's Ctrl ON (the value follows the ordering player's
         key, not the host's); each leg one {intent, shoot, C} context with
         C16F_CHAIN, C TU C16F_TU_AFTER on both. A survives both legs in either
         order (T0-9f: health 30 -> 19 -> 7, standing). Leg 3 (S-E1.1b, F1268):
         the HOST's touch Ctrl OFF, A's health restored to its pre-leg-1 value
         and C TU max (both), the same snap with the client's own touch Ctrl ON.
         RED: the host's Ctrl OFF gives the UNFORCED value. GREEN: C16F_FORCED
         (the client's own key forces the shot with the host's key up).

C16f runs after C18 on purpose: at SEED_C18 the spray changes no terrain and
hits no unit (T0-9f / SEED_C18 proofs), so C16f meets the same world on the red
build (the spray refused) and on the green build (the spray fired), and C18's
last shot leaves C facing east either way.

Before S-E2 the second player's SKILLS menu runs the skill script ON ITS OWN
MACHINE (SkillMenuState::btnActionMenuItemClick -> TileEngine::skillUse, then
the instant-grenade fuse write, then ActionMenuState::handleAction): the script's
TU spend and effects and the fuse write land on the client only, and the
follow-up order ships as a plain intent at the weapon's cost. After S-E2 the
skill press is a `skill` intent: the host alone runs the script and answers
`continue` on the order's bt_action_end; on `continue: true` the client enters
its own targeting (a small ActionMenuState continuation, C3-Q5) and the follow-up
order carries `skill`, so the host charges the skill's cost. The mod gives every
STR_SOLDIER three skills (SkillMenuState keys 49, 50, 51; each costs 10 % of
base TU = 6 for C): STR_COOP_TEST_SKILL_GO (snap with a firearm; the script says
continue and spends nothing), STR_COOP_TEST_SKILL_STOP (no follow-up; the script
says stop, spends the cost and sets the unit tag COOP_SKILL_STOP_RAN to 1) and
STR_COOP_TEST_SKILL_GRENADE (throw with a grenade; continue, spend nothing:
vanilla's instant grenade, fuse 0 and enabled, before the throw targeting). The
client opens the menu through its REAL SKILLS button, found by its rect
SKILLS_RECT (F1127 precedent), and presses the row's key. Three rows, after
C16f, in this order (C23s2 LAST: its red leaves C's TU and tag split, the W2-P1
A2.2 precedent):

  C23s1  skill continue. C gets a rifle + clip (lever, both, clear hands), C on
         C_TILE facing east, A back on its bring-up tile A_SPAWN (C16f leaves A
         on (20,26,0), inside the lane: T0-17's first capture was a
         no_line_of_fire halt), C TU max (both). Client: SKILLS, key 49 (GO).
         Step 1 GREEN: ONE `skill` order - host closedContexts gains {origin
         intent, kind skill, actorId C} whose evs are exactly SKILL_CHAIN, its
         end carries continue true / halted false (lastActionHalt on both), the
         client's lastAftermath is {kind skill, continue true} and its cursor is
         aim; C TU C_TU_FULL on both (the script spends nothing); the host's
         intentsReceivedLog holds the order with skill SKILL_GO. Then (only when
         the buckets are equal and the client aims) HOME, host set_seed
         SEED_C23S1, one left click on C23S1_TARGET. Step 2 GREEN: ONE `shoot`
         order carrying skill SKILL_GO; {origin intent, kind shoot, actorId C}
         with evs C23S1_CHAIN whose `shot` cue weapon is the rifle; C TU
         C23S1_TU_AFTER (64 - the skill's 6, not - 16) and the clip
         C23S1_CLIP_AFTER on both. RED (T0-17): the key sends nothing (the
         script runs on the client, targeting starts locally, TU unchanged);
         the click ships a plain `shoot` (skill null) that the host admits at
         the weapon's snap cost: C TU 64 -> 48 on both.
  C23s3  instant-grenade skill. A grenade (unprimed) on C (lever, both, clear
         hands), C -> C23S3_C_TILE facing east (the throw tile is due north: C
         does not face it, F490), C TU max (both). Client: SKILLS, key 51
         (GRENADE). Step 1 GREEN: ONE `skill` order ({intent, skill, C}, evs
         SKILL_CHAIN, continue true), the grenade's fuse 0 / fuseEnabled true on
         BOTH (host-written, delta-carried), the client's cursor throw, C TU
         C_TU_FULL on both. Then (only when the buckets are equal and the client
         targets a throw) HOME, host set_seed SEED_C23S3, one left click on
         C23S3_TILE. Step 2 GREEN: ONE `throw` order carrying skill
         SKILL_GRENADE; {intent, throw, C} with evs C23S3_CHAIN; C TU
         C23S3_TU_AFTER (the skill's cost + 2 octants of pre-throw turn); the
         grenade fuse 0 / enabled on both. RED (T0-17): the key sends nothing
         and writes the fuse on the CLIENT only (client 0 / true, host -1 /
         false: buckets items/synced/saveBlob differ), so step 2 is not sent (a
         throw into that split latched the client's desync halt at the host's
         `shot` ev in T0-17's capture and would end every later row).
         C23S3_TILE is 5 tiles north, not C19's 7: at HOME on C23S3_C_TILE,
         C19's (12,20,0) projects to base (288,44), inside the SKILLS button, and
         the click opens the skill menu (T0-17).
  C23s2  skill stop. C stripped (both: removes C23s3's grenade, whose fuse the
         red build split), C TU max (both). Client: SKILLS; host defer_intents
         {ms DEFER_C23S2_MS, count 1}; key 50 (STOP). GREEN: inside the defer
         window (the host's intentsReceivedLog has not taken the order yet) the
         client's inFlight is the `skill` order and every bucket is equal on
         both (the client ran nothing); after it, {intent, skill, C} with evs
         SKILL_CHAIN whose end carries continue false / halted false (both), the
         client's lastAftermath {kind skill, continue false}, the client not
         targeting, C TU C23S2_TU_AFTER on both and C's tags TAG_STOP_RAN on
         both (the script's non-TU effect reached the client in the delta). RED
         (T0-17): the key sends nothing; client TU 64 -> 58 and tag [1], host
         TU 64 and tag []: buckets saveBlob/synced/unitsStats differ.

Common asserts (spec (f), after wait_host_idle): hash_now {full:true} - every
bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged
and host 0; the W2-P2 delta must-be-0 counters on both; every lever item created
on both machines with equal ids (both()). For an admitted order: host
closedContexts gains exactly one {origin intent, kind K, actorId C}; every host
ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[K] +1; client
inFlight null at the end; no STR_COOP_ACTION_TIMEOUT. For a refused press:
nothing sent (client inFlight null, host lastSeqEmitted unchanged, host
intentsReceived unchanged, client coopIntentsSent unchanged).

FIXTURE (TASK 0 T0-10 = T0c, T0-9f and SEED_C18 on S-E1's red build; the
roster-pinned terror boot of test_w2_host_combat.py with the mod on both):
set_seed SEED_ROSTER on the HOST right before its open_new_battle, mission
STR_TERROR_MISSION, set_seed SEED_MAP right before newbattle_ok, seat_count 2,
MAP_FP asserted on both (the mod leaves it unchanged, F1164), the seated unit
ids asserted, pin_ai_neutral. Every lever pair goes to the CLIENT first (F607).
Item ids are read at run time from the lever replies (F1107). Seeds were found
with HOST stand-ins (battle_fire {mode spray} / {mode snap, target A}) that run
the executor's states in its order; the green build proves them again (N18 =
F1085).

FIXTURE for C23s1-C23s3 (TASK 0 T0-17 on S-E2.1's red build, 3 boots, the
same values): the mod's skills load on both (MAP_FP and the seated ids
unchanged); the SKILLS button is SKILLS_RECT on the client with C selected; the
menu lists SKILL_ROWS rows, keys 49/50/51 in the skill order; C's skill cost is
SKILL_TU; the rule stand-in (the HOST's own skill menu on H, base TU 58, cost 5)
gave GO: TU unchanged at the key, aim, the follow-up snap costs 5; STOP: TU - 5,
tag 1, no ev emitted; GRENADE: fuse 0 / enabled at the key, the throw costs 5 +
2 (turn). hash_now {full} takes 0.05 s per machine, so DEFER_C23S2_MS leaves the
in-window checks a wide margin and stays under coopIntentTimeoutSeconds (10 s).
The probe `intentsReceivedLog` (HOST event_state, S-E2.1) lists the envelopes
onIntent took into its checks with their wire `skill` field.

RED-THEN-GREEN (spec (d) row S-E). Commit S-E1.1 (this file and the battle_fire
spray stand-in) is run ONCE and every scenario must FAIL with its RED evidence.
Commit S-E1.2 is run ONCE and every scenario must PASS. Commit S-E2.1 (the C23s
rows, the mod's skills, the intentsReceivedLog probe) is run ONCE: C18 and C16f
PASS (S-E1 is in) and the C23s rows FAIL with their RED evidence; commit S-E2.2
is run ONCE and every scenario must PASS. Each scenario prints ONE
"EVIDENCE <id>:" line with both machines' fields BEFORE its green conditions are
checked; main() runs every scenario even after an earlier one failed and prints
"PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that times
out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when every scenario passes, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_rules.py
"""

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, short, both
from test_w2_host_combat import bring_up_lobby_roster_pinned, ev_tuples
from test_w2_client_shoot import (top, snap, ubrief, press, menu_rows, mine, give_both, place,
                                  set_tu_both, set_firing_both, cancel_client_aim, aim_click, await_press,
                                  collect, ctx_view, chain_of, admitted_fails, forwarded_fails, tu_fails,
                                  qty_fails, common_fails, finish, press_view, ui_view, shot_payloads,
                                  RHAND_CENTRE, TU_MAX, C_TU_FULL, CURSOR_AIM, POLL_S, KEY_SNAP, KEY_AUTO)
from test_w2_client_grenade import mod_log, hurt_map, hurt_delta
from test_w2_client_shoot import shot_brief, order_done, SENT_WAIT_S, ORDER_TIMEOUT_S
from test_w2_client_grenade import (admitted_fails as admitted_kind_fails, cancel_client_targeting, item_view,
                                    fuse_fails, CURSOR_TARGETING, CURSOR_THROW)
from test_w2_client_items import strip_both
from test_w2_delta_items import items_by_id

# ----- bring-up (TASK 0: the roster-pinned terror boot, the mod on both) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1, unmodded and modded (F1164)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers
PORT = "48715"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
STATUS_STANDING = 0               # src/Mod/Unit.h enum UnitStatus
MOD_NAME = "Coop_Spray_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_Spray_Test v1.0"

# ----- C18 (T0-10 = T0c: F1168; SEED_C18 hunted on S-E1's red build) -----
C_TILE, C18_C_DIR = (12, 26, 0), 2
SPRAY_W0, SPRAY_W1 = (24, 24, 0), (24, 27, 0)
SEED_C18 = 4                      # seeds 1-3: a shot off its waypoint tile (and 1, 2 changed terrain)
C18_ROWS = 4                      # the modded rifle's menu (T0c)
C18_SPRAY = [(392, 392, 12), (392, 416, 12), (392, 440, 12)]   # vanilla's spread voxels, shot 1..3
C18_IMPACTS = [(499, 386, 1), (718, 402, 1), (538, 450, 1)]    # the three shots' impactVoxel (floor)
C18_WAYPOINTS_LEFT = [2, 1, 0]
C18_CHAIN = ["shot", "hit", "shot", "hit", "shot", "hit", "bt_action_end"]
AUTO_TU = 22
C18_TU_AFTER = C_TU_FULL - AUTO_TU   # 42: no pre-shot turn (C faces east)
CLIP_FULL = 20
C18_CLIP_AFTER = 17
TILE_HALF = 8                     # voxels: passing over a tile = within 8 voxels (x/y) of its centre

# ----- C16f (T0-9f on S-E1's red build) -----
C16F_A_TILE, C16F_A_DIR = (20, 26, 0), 6
SEED_C16F = 1
C16F_UNFORCED = (326, 424, 8)     # aimed at A: the unit's centre (host Ctrl OFF)
C16F_FORCED = (326, 424, 12)      # force-fire at A's tile: the tile centre (host Ctrl ON)
SNAP_TU = 16
C16F_TU_AFTER = C_TU_FULL - SNAP_TU  # 48: no pre-shot turn
C16F_CHAIN = ["shot", "hit", "bt_action_end"]

# ----- C23s1-C23s3 (amendment C3 D147 section 3; T0-17 on S-E2.1's red build) -----
SKILL_GO = "STR_COOP_TEST_SKILL_GO"            # snap, continue, spends nothing
SKILL_STOP = "STR_COOP_TEST_SKILL_STOP"        # no follow-up, stop, spends the cost, tag 1
SKILL_GRENADE = "STR_COOP_TEST_SKILL_GRENADE"  # throw, continue, spends nothing (instant grenade)
KEY_SKILL_GO, KEY_SKILL_STOP, KEY_SKILL_GRENADE = 49, 50, 51   # keyBattleActionItem1..3, the skill order
SKILLS_RECT = (288, 25, 32, 24)   # the SKILLS button, special-action slot 0 (T0-17; found by rect, F1127)
SKILL_ROWS = 3
SKILL_TU = 6                      # 10 % of C's base TU 64, floor (T0-17: the red's local drop 64 -> 58)
SKILL_CHAIN = ["bt_action_end"]   # a skill order's own context: no cue (amendment C3 D147 section 1)
A_SPAWN, A_SPAWN_DIR = (37, 38, 0), 2   # A's bring-up tile and facing: off C23s1's lane
C23S1_TARGET = (32, 26, 0)        # T0-3: empty road floor tile, 20 tiles east of C_TILE
SEED_C23S1 = 1                    # SEED_C17 (T0a); T0-17: shot -> hit -> bt_action_end
C23S1_CHAIN = ["shot", "hit", "bt_action_end"]
C23S1_TU_AFTER = C_TU_FULL - SKILL_TU   # 58: the follow-up snap pays the skill's cost (red: 48, the snap's 16)
C23S1_CLIP_AFTER = 19
C23S3_C_TILE, C23S3_C_DIR = (12, 27, 0), 2   # C19's thrower tile, facing east (the throw tile is north, F490)
C23S3_TILE = (12, 22, 0)          # T0-17: base (256,60) at HOME; C19's (12,20,0) is (288,44), under SKILLS
SEED_C23S3 = 2                    # SEED_C19; the rule stand-in's throw at this seed landed on C23S3_TILE
C23S3_CHAIN = ["shot", "bt_action_end"]
C23S3_TU_AFTER = C_TU_FULL - SKILL_TU - 2   # 56: the skill's cost + two octants of pre-throw turn
DEFER_C23S2_MS = 3000             # the in-window checks take ~0.3 s (T0-17); < coopIntentTimeoutSeconds 10 s
C23S2_TU_AFTER = C_TU_FULL - SKILL_TU   # 58
TAG_STOP_RAN = [1]                # field_poke unit tags after the stop script (COOP_SKILL_STOP_RAN = 1)
CURSOR_NORMAL = 1                 # CT_NORMAL
STEP_WAIT_S = 3.0                 # how long the client's cursor gets to reach its targeting mode after step 1

# ----- UI -----
CLICK_WAIT_S = 1.5                # how long a waypoint click gets to show as refused or sent


# ===================== small helpers =====================


def touch(gc, **flags):
    """set_touch_modifiers on ONE machine (no keys = read back only)."""
    req = {"cmd": "set_touch_modifiers"}
    req.update(flags)
    r = gc.ok(req)
    return {k: r.get(k) for k in ("ctrl", "alt", "shift")}


def vox(d):
    return (d.get("x"), d.get("y"), d.get("z")) if isinstance(d, dict) else None


def over_tile(origin, impact, target):
    """Whether the straight shot origin -> impact passes over `target`'s tile:
    the x/y distance of `target` from the segment (voxels), the segment
    parameter of the closest point (0..1 = between the muzzle and the impact)
    and the shot's height there. Returns (distance, t, z)."""
    ox, oy, oz = origin
    ix, iy, iz = impact
    px, py, _ = target
    dx, dy = ix - ox, iy - oy
    l2 = dx * dx + dy * dy
    t = ((px - ox) * dx + (py - oy) * dy) / l2 if l2 else 0.0
    return (round(math.hypot(px - (ox + t * dx), py - (oy + t * dy)), 2), round(t, 3), round(oz + t * (iz - oz), 1))


def spray_rows(shots):
    rows = []
    for k, (s, p) in enumerate(shots):
        p = p or {}
        o, i = vox(p.get("originVoxel")), vox(p.get("impactVoxel"))
        tgt = C18_SPRAY[k] if k < len(C18_SPRAY) else None
        rows.append({"seq": s, "shotIndex": p.get("shotIndex"), "waypointsLeft": p.get("waypointsLeft"),
                     "action": p.get("action"), "origin": o, "impact": i, "impactPart": p.get("impact"),
                     "target": tgt, "over": over_tile(o, i, tgt) if (o and i and tgt) else None})
    return rows


def click_state(host, client, before):
    """Up to CLICK_WAIT_S after one waypoint click: `refused` (client
    coopLocalExecBlocked moved), `sent` (client inFlight / coopIntentsSent moved
    or the host emitted) or `quiet`."""
    t0 = time.time()
    while time.time() - t0 < CLICK_WAIT_S:
        ec, eh = event_state(client), event_state(host)
        if (ec.get("inFlight") or ec.get("coopIntentsSent") != before["client"]["coopIntentsSent"]
                or eh.get("lastSeqEmitted") != before["host"]["lastSeqEmitted"]):
            return {"state": "sent", "t": round(time.time() - t0, 3)}
        if ec.get("coopLocalExecBlocked") != before["client"]["coopLocalExecBlocked"]:
            return {"state": "refused", "t": round(time.time() - t0, 3)}
        time.sleep(POLL_S)
    return {"state": "quiet", "t": round(time.time() - t0, 3)}


def nothing_sent_fails(before, rec, what):
    fails = []
    if rec["client"]["inFlight"] is not None:
        fails.append(f"{what}: client inFlight {rec['client']['inFlight']} (want null)")
    if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
        fails.append(f"{what}: host lastSeqEmitted {before['host']['lastSeqEmitted']}->"
                     f"{rec['host']['lastSeqEmitted']} (want unchanged)")
    if rec["client"]["coopIntentsSent"] != before["client"]["coopIntentsSent"]:
        fails.append(f"{what}: client coopIntentsSent {before['client']['coopIntentsSent']}->"
                     f"{rec['client']['coopIntentsSent']} (want unchanged)")
    if rec["host"]["intentsReceived"] != before["host"]["intentsReceived"]:
        fails.append(f"{what}: host intentsReceived {before['host']['intentsReceived']}->"
                     f"{rec['host']['intentsReceived']} (want unchanged)")
    return fails


def blocked(p):
    return p["client"]["coopLocalExecBlocked"]


# ===================== scenarios =====================


def c18_spray(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C18_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    staged = diff_buckets(host, client)
    hm0 = touch(host)
    hurt0 = {"host": hurt_map(host), "client": hurt_map(client)}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {}
    mid = None
    out0, out1 = {}, {}
    try:
        ev["tab"] = tab_select(client, C_ID)
        assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
        if battle_state(client).get("cursorType") == CURSOR_AIM:
            click_nth(client, RHAND_NTH)   # F503: this click only cancels the aim
            ev["aimCancelled"] = battle_state(client).get("cursorType")
        r = click_nth(client, RHAND_NTH)
        assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
        client.wait_for("client ActionMenuState on top",
                        lambda: client.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState")
                        or None, timeout=5)
        ev["rows"] = menu_rows(client)
        press(client, KEY_AUTO)
        client.wait_for("client BattlescapeState on top after the AUTO key",
                        lambda: top(client) == "BattlescapeState" or None, timeout=5)
        ev["cursorAfterKey"] = battle_state(client).get("cursorType")
        assert ev["cursorAfterKey"] == CURSOR_AIM, (
            f"key {KEY_AUTO} did not start targeting on the client (cursorType {ev['cursorAfterKey']})")
        press(client, SDLK_HOME)
        time.sleep(0.15)
        pos = {}
        for name, t in (("W0", SPRAY_W0), ("W1", SPRAY_W1)):
            pr = client.cmd({"cmd": "map_tile_click_pos", "x": t[0], "y": t[1], "z": t[2]})
            pos[name] = pr
        ev["clickPos"] = {n: {k: p.get(k) for k in ("verified", "winX", "winY", "centered")} for n, p in pos.items()}
        assert pos["W0"].get("verified") and pos["W1"].get("verified"), (
            f"precondition: map_tile_click_pos did not verify both spray waypoints on the client: {ev['clickPos']}")
        ev["clientMods"] = touch(client, ctrl=True, shift=True)
        client.ok({"cmd": "inject_input", "kind": "click", "x": pos["W0"]["winX"], "y": pos["W0"]["winY"],
                   "button": "left"})
        out0 = click_state(host, client, before)
        mid = snap(host, client)
        host.ok({"cmd": "set_seed", "seed": SEED_C18})
        client.ok({"cmd": "inject_input", "kind": "click", "x": pos["W1"]["winX"], "y": pos["W1"]["winY"],
                   "button": "left"})
        out1 = await_press(host, client, mid, notes)
    except Exception as e:
        notes.append(f"real-UI spray: {short(e)}")
    finally:
        try:
            ev["clientModsAfter"] = touch(client, ctrl=False, shift=False)
        except Exception as e:
            notes.append(f"client touch flags off: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    rows = spray_rows(shot_payloads(host, chain))
    hurt1 = {"host": hurt_map(host), "client": hurt_map(client)}
    hurt = {n: hurt_delta(hurt0[n], hurt1[n]) for n in ("host", "client")}
    w0 = {"blocked": (blocked(before), blocked(mid)) if mid else None,
          "hostSeq": (before["host"]["lastSeqEmitted"], mid["host"]["lastSeqEmitted"]) if mid else None,
          "inFlight": mid["client"]["inFlight"] if mid else None,
          "sent": (before["client"]["coopIntentsSent"], mid["client"]["coopIntentsSent"]) if mid else None}
    print(f"EVIDENCE C18: staged rifle={rifle} clip={clip} C={pc_} stagedDiff={staged} aimCancel={aim0} "
          f"hostMods={hm0} ui={ev} W0click={out0} W0={w0} W1click={out1}; {press_view(before, rec)}; "
          f"ui={ui_view(before, rec)}; newContexts={new}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; "
          f"shots={rows}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; items="
          f"{ {i: ((rec['ih'].get(i) or {}).get('qty'), (rec['ic'].get(i) or {}).get('qty')) for i in (rifle, clip)} }; "
          f"hurt={hurt}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if any(hm0.values()):
        fails.append(f"precondition: host touch flags {hm0} (want all off)")
    if mid is None:
        fails.append("the SPRAY_W0 click never ran")
    else:
        if blocked(mid) != blocked(before):
            fails.append(f"SPRAY_W0 click: client coopLocalExecBlocked {blocked(before)}->{blocked(mid)} (want "
                         f"unchanged: the spray start is local display, not a K1 refusal)")
        fails += nothing_sent_fails(before, mid, "SPRAY_W0 click")
        fails += forwarded_fails(mid, rec)
    f, cx = admitted_fails(before, rec, "shoot", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C18_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C18_CHAIN})")
    if cx:
        got = [(r["shotIndex"], r["waypointsLeft"], r["impact"]) for r in rows]
        want = [(k + 1, C18_WAYPOINTS_LEFT[k], C18_IMPACTS[k]) for k in range(len(C18_IMPACTS))]
        if got != want:
            fails.append(f"`shot` cues of actionId {aid} (shotIndex, waypointsLeft, impactVoxel) = {got} "
                         f"(want {want}: the spray at SEED_C18)")
        for r in rows:
            ov = r["over"]
            if not ov or ov[0] > TILE_HALF or not (0.0 <= ov[1] <= 1.0):
                fails.append(f"shot {r['shotIndex']} does not pass over its spread waypoint {r['target']}: "
                             f"(distance, t, z) = {ov} (want distance <= {TILE_HALF}, 0 <= t <= 1)")
    fails += tu_fails(rec, C_ID, C18_TU_AFTER)
    fails += qty_fails(rec, clip, C18_CLIP_AFTER, "clip")
    if hurt["host"] or hurt["client"]:
        fails.append(f"units changed (health, stun, status): {hurt} (want none)")
    fails += common_fails(host, client, before, "C18")
    finish(fails)


def c16f_leg(host, client, client_ctrl, notes):
    """One real-UI snap from C at A's tile, the host's set_seed right before the
    click; the client's own touch Ctrl set ON right before it when
    `client_ctrl` (and OFF again after the order). Returns the leg's record."""
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    leg = {"before": before, "hostMods": touch(host), "clientMods": touch(client)}

    def before_click():
        host.ok({"cmd": "set_seed", "seed": SEED_C16F})
        if client_ctrl:
            leg["clientMods"] = touch(client, ctrl=True)
    pv = {}
    try:
        pv = aim_click(client, KEY_SNAP, C16F_A_TILE, before_click)
    except Exception as e:
        notes.append(f"real-UI snap (client Ctrl {'ON' if client_ctrl else 'OFF'}): {short(e)}")
    leg["press"] = {k: v for k, v in pv.items() if k != "clickAt"}
    leg["outcome"] = await_press(host, client, before, notes)
    if client_ctrl:
        try:
            leg["clientModsAfter"] = touch(client, ctrl=False)
        except Exception as e:
            notes.append(f"client touch Ctrl off: {short(e)}")
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
    leg.update({"rec": rec, "new": new, "aid": aid, "chain": chain,
                "shots": [(s, {k: (p or {}).get(k) for k in ("action", "weapon", "ammo", "shotIndex", "originVoxel",
                                                              "impactVoxel", "impact")}) for s, p in shots],
                "impact": vox((shots[0][1] or {}).get("impactVoxel")) if shots else None,
                "A": {"host": ubrief(rec["uh"].get(A_ID)), "client": ubrief(rec["uc"].get(A_ID))}})
    return leg


def leg_view(leg):
    return {"hostMods": leg["hostMods"], "clientMods": leg["clientMods"],
            "clientModsAfter": leg.get("clientModsAfter"), "press": leg["press"], "outcome": leg["outcome"],
            "counters": press_view(leg["before"], leg["rec"]), "newContexts": leg["new"], "action": leg["aid"],
            "chain": [(e["seq"], e["kind"]) for e in leg["chain"]], "shots": leg["shots"], "impact": leg["impact"],
            "C": {"host": ubrief(leg["rec"]["uh"].get(C_ID)), "client": ubrief(leg["rec"]["uc"].get(C_ID))},
            "A": leg["A"], "diff": leg["rec"]["diff"], "desync": leg["rec"]["dsc"]}


def c16f_leg_fails(host, client, leg, want, what, host_ctrl=True):
    fails = []
    if bool(leg["hostMods"].get("ctrl")) != host_ctrl:
        fails.append(f"{what}: host touch Ctrl {leg['hostMods']} at the press (want {'ON' if host_ctrl else 'OFF'})")
    fails += forwarded_fails(leg["before"], leg["rec"])
    f, cx = admitted_fails(leg["before"], leg["rec"], "shoot", C_ID)
    fails += [f"{what}: {m}" for m in f]
    kinds = [e["kind"] for e in leg["chain"]]
    if cx and kinds != C16F_CHAIN:
        fails.append(f"{what}: host evs of actionId {leg['aid']} = {kinds} (want exactly {C16F_CHAIN})")
    if leg["impact"] != want:
        fails.append(f"{what}: the shot's impactVoxel {leg['impact']} (want {want})")
    fails += [f"{what}: {m}" for m in tu_fails(leg["rec"], C_ID, C16F_TU_AFTER)]
    for n in ("host", "client"):
        a = leg["A"][n] or {}
        if a.get("status") != STATUS_STANDING:
            fails.append(f"{what}: {n} A {a} (want standing)")
    fails += [f"{what}: {m}" for m in common_fails(host, client, leg["before"], what)]
    return fails


def c16f_force_fire(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C18_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    pa_ = place(host, client, A_ID, C16F_A_TILE, C16F_A_DIR)
    vis = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "visible": True},
               ("visible",)).get("visible")
    staged = diff_buckets(host, client)
    a_health0 = (session.units_by_id(battle_state(host)).get(A_ID) or {}).get("health")
    legs = {}
    try:
        legs["hostCtrlOn"] = touch(host, ctrl=True)
        legs["L1"] = c16f_leg(host, client, False, notes)
        set_tu_both(host, client, C_ID, TU_MAX)
        legs["L2"] = c16f_leg(host, client, True, notes)
        # S-E1.1b (F1268): leg 3 - the host's Ctrl OFF, the client's own Ctrl ON.
        legs["hostCtrlOffL3"] = touch(host, ctrl=False)
        legs["Arestored"] = {k: v for k, v in both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID,
                                                                  "health": a_health0},
                                                    ("health", "stun", "status")).items()
                             if k in ("health", "stun", "status")}
        set_tu_both(host, client, C_ID, TU_MAX)
        legs["L3"] = c16f_leg(host, client, True, notes)
    except Exception as e:
        notes.append(f"C16f drive: {short(e)}")
    finally:
        try:
            legs["hostCtrlOff"] = touch(host, ctrl=False)
        except Exception as e:
            notes.append(f"host touch Ctrl off: {short(e)}")
    print(f"EVIDENCE C16f: staged rifle={rifle} clip={clip} C={pc_} A={pa_} Avisible={vis} stagedDiff={staged} "
          f"aimCancel={aim0} hostCtrlOn={legs.get('hostCtrlOn')} hostCtrlOff={legs.get('hostCtrlOff')}; "
          f"LEG1 (client Ctrl OFF, want {C16F_UNFORCED})="
          f"{leg_view(legs['L1']) if 'L1' in legs else None}; LEG2 (client Ctrl ON, want {C16F_FORCED})="
          f"{leg_view(legs['L2']) if 'L2' in legs else None}; A health before leg 1={a_health0} "
          f"hostCtrlOffL3={legs.get('hostCtrlOffL3')} Arestored={legs.get('Arestored')}; LEG3 (host Ctrl OFF, "
          f"client Ctrl ON, want {C16F_FORCED})={leg_view(legs['L3']) if 'L3' in legs else None}; notes={notes}",
          flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if vis is not True:
        fails.append(f"precondition: A visible {vis} after set_stat (want true on both)")
    if "L1" in legs:
        fails += c16f_leg_fails(host, client, legs["L1"], C16F_UNFORCED, "leg 1 (client Ctrl OFF)")
    else:
        fails.append("leg 1 never ran")
    if "L2" in legs:
        fails += c16f_leg_fails(host, client, legs["L2"], C16F_FORCED, "leg 2 (client Ctrl ON)")
    else:
        fails.append("leg 2 never ran")
    if "L3" in legs:
        fails += c16f_leg_fails(host, client, legs["L3"], C16F_FORCED, "leg 3 (host Ctrl OFF, client Ctrl ON)",
                                host_ctrl=False)
    else:
        fails.append("leg 3 never ran")
    finish(fails)


# ===================== the skill rows (S-E2, D147) =====================


def rlog(host):
    """The HOST's intentsReceivedLog: [{iseq, kind, actorId, skill}] (S-E2.1)."""
    return event_state(host).get("intentsReceivedLog") or []


def rlog_new(log0, log1):
    """The intentsReceivedLog entries added after `log0` (by iseq)."""
    seen = max([e.get("iseq", 0) for e in log0] or [0])
    return [e for e in log1 if e.get("iseq", 0) > seen]


def tags_of(gc, uid):
    """The unit's script tags (field_poke peek: nothing written)."""
    r = gc.cmd({"cmd": "field_poke", "class": "unit", "id": uid, "field": "tags"})
    return r.get("before") if r.get("ok") else {"error": r.get("error")}


def c_tu(gc):
    return (session.units_by_id(battle_state(gc)).get(C_ID) or {}).get("tu")


def fuse_view(gc, iid):
    it = items_by_id(gc).get(iid) or {}
    return (it.get("fuse"), it.get("fuseEnabled"))


def skills_nth(gc):
    """The SKILLS button's click nth among the top state's visible interactive
    surfaces, found by its rect (F1127 precedent); None while it is hidden."""
    vis = [w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") and w.get("interactive")]
    for n, w in enumerate(vis):
        if (w.get("x"), w.get("y"), w.get("w"), w.get("h")) == SKILLS_RECT:
            return n
    return None


def open_skill_menu(client, ev):
    """TAB-select C, cancel a leftover targeting (F503), the REAL SKILLS button
    (by its rect): SkillMenuState opens. Fills `ev`."""
    ev["tab"] = tab_select(client, C_ID)
    assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
    ev["targetingCancel"] = cancel_client_targeting(client)
    nth = skills_nth(client)
    ev["skillsNth"] = nth
    assert nth is not None, f"the SKILLS button {SKILLS_RECT} is not visible on the client"
    r = click_nth(client, nth)
    ev["skillsClick"] = (r.get("baseX"), r.get("baseY"))
    client.wait_for("client SkillMenuState on top", lambda: top(client) == "SkillMenuState" or None, timeout=5)
    ev["rows"] = menu_rows(client)


def skill_step(host, client, key, ev, notes):
    """Step 1: the SKILLS button and the row's key; then (bounded) the order's
    end and the client's cursor settling. Returns the press outcome."""
    out = {"state": "not pressed"}
    try:
        open_skill_menu(client, ev)
        before = snap(host, client)
        press(client, key)
        out = await_press(host, client, before, notes)
    except Exception as e:
        notes.append(f"real-UI SKILLS, key {key}: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle (skill step): {short(e)}")
    return out


def wait_cursor(client, want):
    """Up to STEP_WAIT_S for the client's cursor to reach `want` (the
    continuation's targeting after a `continue: true` answer). Returns the
    cursor seen last."""
    t0 = time.time()
    cur = battle_state(client).get("cursorType")
    while cur != want and time.time() - t0 < STEP_WAIT_S:
        time.sleep(POLL_S)
        cur = battle_state(client).get("cursorType")
    return cur


def gate_view(rec, cursor, want):
    """Step 2 is sent only into an equal battle with the client targeting:
    a follow-up into split buckets makes the host's next ev latch the client's
    desync halt, which ends every later row (T0-17's capture)."""
    return {"diff": rec["diff"], "cursor": cursor, "go": not rec["diff"] and cursor == want}


def follow_click(host, client, tile, seed, ev, notes):
    """Step 2: HOME, one self-verified left click on `tile` with the host's
    set_seed right before it; then (bounded) the order's end."""
    before = snap(host, client)
    out = {"state": "not pressed"}
    try:
        press(client, SDLK_HOME)
        time.sleep(0.15)
        pr = client.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
        ev["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY", "centered")}
        assert pr.get("verified"), f"precondition: map_tile_click_pos did not verify {tile} on the client: {pr}"
        host.ok({"cmd": "set_seed", "seed": seed})
        client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        out = await_press(host, client, before, notes)
    except Exception as e:
        notes.append(f"real-UI follow-up click on {tile}: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle (follow-up): {short(e)}")
    return out


def skill_end_fails(rec, aid, cont, what):
    """The skill order's own end: `continue` `cont`, not halted, on both
    machines' lastActionHalt; the client's lastAftermath {kind skill}."""
    fails = []
    for n in ("host", "client"):
        h = rec[n]["lastActionHalt"] or {}
        if aid is None or h.get("actionId") != aid or h.get("continue") is not cont or h.get("halted") is not False:
            fails.append(f"{what}: {n} lastActionHalt={rec[n]['lastActionHalt']} (want {{actionId {aid}, continue "
                         f"{cont}, halted false}})")
    la = rec["client"]["lastAftermath"] or {}
    if aid is None or la.get("actionId") != aid or la.get("kind") != "skill" or la.get("continue") is not cont:
        fails.append(f"{what}: client lastAftermath={rec['client']['lastAftermath']} (want {{actionId {aid}, kind "
                     f"skill, continue {cont}}})")
    return fails


def rlog_fails(new, kind, skill, what):
    got = [(e.get("kind"), e.get("skill")) for e in new]
    if got != [(kind, skill)]:
        return [f"{what}: host intentsReceivedLog gained {new} (want exactly one {{kind {kind}, skill {skill}}})"]
    return []


def chain_fails(rec, aid, want, what):
    kinds = [e["kind"] for e in chain_of(rec, aid)]
    if aid is not None and kinds != want:
        return [f"{what}: host evs of actionId {aid} = {kinds} (want exactly {want})"]
    return []


def c23s1_skill_continue(host, client, ctx):
    notes = []
    tc0 = cancel_client_targeting(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C18_C_DIR)
    pa_ = place(host, client, A_ID, A_SPAWN, A_SPAWN_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    log0 = rlog(host)
    ev1 = {}
    out1 = skill_step(host, client, KEY_SKILL_GO, ev1, notes)
    cur1 = wait_cursor(client, CURSOR_AIM)
    rec1 = collect(host, client, seq0)
    log1 = rlog(host)
    new1 = ctx_view(before, rec1)
    h1 = mine(new1, "intent", "skill", C_ID)
    aid1 = h1[0]["actionId"] if len(h1) == 1 else None
    gate = gate_view(rec1, cur1, CURSOR_AIM)
    mid = snap(host, client)
    seq1 = mid["host"]["lastSeqEmitted"] or 0
    ev2 = {}
    out2 = {"state": "not sent: gate closed"}
    if gate["go"]:
        out2 = follow_click(host, client, C23S1_TARGET, SEED_C23S1, ev2, notes)
    rec2 = collect(host, client, seq1)
    log2 = rlog(host)
    new2 = ctx_view(mid, rec2)
    h2 = mine(new2, "intent", "shoot", C_ID)
    aid2 = h2[0]["actionId"] if len(h2) == 1 else None
    shots = shot_payloads(host, chain_of(rec2, aid2))
    print(f"EVIDENCE C23s1: staged rifle={rifle} clip={clip} C={pc_} A={pa_} stagedDiff={staged} "
          f"targetingCancel={tc0} | STEP 1 (SKILLS, key {KEY_SKILL_GO}) press={ev1} outcome={out1} "
          f"cursor={cur1}; {press_view(before, rec1)}; newContexts={new1}; action={aid1} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec1, aid1)]}; hostLogNew={rlog_new(log0, log1)}; "
          f"C tu host={(rec1['uh'].get(C_ID) or {}).get('tu')} client={(rec1['uc'].get(C_ID) or {}).get('tu')}; "
          f"gate={gate} | STEP 2 (click {C23S1_TARGET}) press={ev2} outcome={out2}; {press_view(mid, rec2)}; "
          f"ui={ui_view(mid, rec2)}; newContexts={new2}; action={aid2} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec2, aid2)]}; shots={shot_brief(shots)}; "
          f"hostLogNew={rlog_new(log1, log2)}; C host={ubrief(rec2['uh'].get(C_ID))} "
          f"client={ubrief(rec2['uc'].get(C_ID))}; clip qty host={(rec2['ih'].get(clip) or {}).get('qty')} "
          f"client={(rec2['ic'].get(clip) or {}).get('qty')}; host evs={ev_tuples(rec2['hev'])} "
          f"client evs={ev_tuples(rec2['cev'])}; diff={rec2['diff']} desync={rec2['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if ev1.get("rows") != SKILL_ROWS:
        fails.append(f"precondition: client skill menu rows {ev1.get('rows')} (want {SKILL_ROWS})")
    # step 1: the skill order
    fails += [f"step 1: {m}" for m in forwarded_fails(before, rec1)]
    f, cx = admitted_kind_fails(before, rec1, "skill", "skill", C_ID)
    fails += [f"step 1: {m}" for m in f]
    fails += chain_fails(rec1, aid1, SKILL_CHAIN, "step 1")
    fails += skill_end_fails(rec1, aid1, True, "step 1")
    fails += rlog_fails(rlog_new(log0, log1), "skill", SKILL_GO, "step 1")
    if cur1 != CURSOR_AIM:
        fails.append(f"step 1: client cursorType {cur1} after the skill order (want {CURSOR_AIM}: the continuation "
                     f"starts vanilla's aim)")
    fails += [f"step 1: {m}" for m in tu_fails(rec1, C_ID, C_TU_FULL)]
    if not gate["go"]:
        fails.append(f"step 2 not sent: {gate} (want equal buckets and the client aiming)")
    # step 2: the follow-up snap carries the skill
    fails += [f"step 2: {m}" for m in forwarded_fails(mid, rec2)]
    f, cx2 = admitted_kind_fails(mid, rec2, "shoot", "shoot", C_ID)
    fails += [f"step 2: {m}" for m in f]
    fails += chain_fails(rec2, aid2, C23S1_CHAIN, "step 2")
    if cx2 and (len(shots) != 1 or (shots[0][1] or {}).get("weapon") != rifle):
        fails.append(f"step 2: `shot` cue(s) {shot_brief(shots)} (want one with weapon {rifle}, the rifle)")
    fails += rlog_fails(rlog_new(log1, log2), "shoot", SKILL_GO, "step 2")
    fails += [f"step 2: {m}" for m in tu_fails(rec2, C_ID, C23S1_TU_AFTER)]
    fails += [f"step 2: {m}" for m in qty_fails(rec2, clip, C23S1_CLIP_AFTER, "clip")]
    fails += common_fails(host, client, before, "C23s1")
    finish(fails)


def c23s3_skill_grenade(host, client, ctx):
    notes = []
    tc0 = cancel_client_targeting(client)
    gid = both(host, client, {"cmd": "battle_give", "unit": C_ID, "item": "STR_GRENADE", "clear_hands": True},
               ("weaponId", "ammoId"))["weaponId"]
    pc_ = place(host, client, C_ID, C23S3_C_TILE, C23S3_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    fuse0 = {"host": fuse_view(host, gid), "client": fuse_view(client, gid)}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    log0 = rlog(host)
    ev1 = {}
    out1 = skill_step(host, client, KEY_SKILL_GRENADE, ev1, notes)
    cur1 = wait_cursor(client, CURSOR_THROW)
    rec1 = collect(host, client, seq0)
    log1 = rlog(host)
    new1 = ctx_view(before, rec1)
    h1 = mine(new1, "intent", "skill", C_ID)
    aid1 = h1[0]["actionId"] if len(h1) == 1 else None
    gate = gate_view(rec1, cur1, CURSOR_THROW)
    mid = snap(host, client)
    seq1 = mid["host"]["lastSeqEmitted"] or 0
    ev2 = {}
    out2 = {"state": "not sent: gate closed"}
    if gate["go"]:
        out2 = follow_click(host, client, C23S3_TILE, SEED_C23S3, ev2, notes)
    rec2 = collect(host, client, seq1)
    log2 = rlog(host)
    new2 = ctx_view(mid, rec2)
    h2 = mine(new2, "intent", "throw", C_ID)
    aid2 = h2[0]["actionId"] if len(h2) == 1 else None
    print(f"EVIDENCE C23s3: staged grenade={gid} C={pc_} stagedDiff={staged} fuse before={fuse0} "
          f"targetingCancel={tc0} | STEP 1 (SKILLS, key {KEY_SKILL_GRENADE}) press={ev1} outcome={out1} "
          f"cursor={cur1}; {press_view(before, rec1)}; newContexts={new1}; action={aid1} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec1, aid1)]}; hostLogNew={rlog_new(log0, log1)}; "
          f"grenade host={item_view(rec1['ih'].get(gid))} client={item_view(rec1['ic'].get(gid))}; "
          f"C tu host={(rec1['uh'].get(C_ID) or {}).get('tu')} client={(rec1['uc'].get(C_ID) or {}).get('tu')}; "
          f"gate={gate} | STEP 2 (throw at {C23S3_TILE}) press={ev2} outcome={out2}; {press_view(mid, rec2)}; "
          f"ui={ui_view(mid, rec2)}; newContexts={new2}; action={aid2} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec2, aid2)]}; "
          f"shots={shot_brief(shot_payloads(host, chain_of(rec2, aid2)))}; hostLogNew={rlog_new(log1, log2)}; "
          f"grenade host={item_view(rec2['ih'].get(gid))} client={item_view(rec2['ic'].get(gid))}; "
          f"C host={ubrief(rec2['uh'].get(C_ID))} client={ubrief(rec2['uc'].get(C_ID))}; host evs="
          f"{ev_tuples(rec2['hev'])} client evs={ev_tuples(rec2['cev'])}; diff={rec2['diff']} desync={rec2['dsc']}; "
          f"notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if fuse0["host"] != (-1, False) or fuse0["client"] != (-1, False):
        fails.append(f"precondition: grenade {gid} (fuse, fuseEnabled) before {fuse0} (want (-1, False) on both)")
    if ev1.get("rows") != SKILL_ROWS:
        fails.append(f"precondition: client skill menu rows {ev1.get('rows')} (want {SKILL_ROWS})")
    # step 1: the skill order; the host writes the instant-grenade fuse
    fails += [f"step 1: {m}" for m in forwarded_fails(before, rec1)]
    f, cx = admitted_kind_fails(before, rec1, "skill", "skill", C_ID)
    fails += [f"step 1: {m}" for m in f]
    fails += chain_fails(rec1, aid1, SKILL_CHAIN, "step 1")
    fails += skill_end_fails(rec1, aid1, True, "step 1")
    fails += rlog_fails(rlog_new(log0, log1), "skill", SKILL_GRENADE, "step 1")
    fails += fuse_fails(rec1, gid, 0, True, "step 1: grenade")
    if cur1 != CURSOR_THROW:
        fails.append(f"step 1: client cursorType {cur1} after the skill order (want {CURSOR_THROW}: the continuation "
                     f"starts vanilla's throw targeting)")
    fails += [f"step 1: {m}" for m in tu_fails(rec1, C_ID, C_TU_FULL)]
    if not gate["go"]:
        fails.append(f"step 2 not sent: {gate} (want equal buckets and the client targeting a throw)")
    # step 2: the throw carries the skill
    fails += [f"step 2: {m}" for m in forwarded_fails(mid, rec2)]
    f, cx2 = admitted_kind_fails(mid, rec2, "throw", "throw", C_ID)
    fails += [f"step 2: {m}" for m in f]
    fails += chain_fails(rec2, aid2, C23S3_CHAIN, "step 2")
    fails += rlog_fails(rlog_new(log1, log2), "throw", SKILL_GRENADE, "step 2")
    fails += [f"step 2: {m}" for m in tu_fails(rec2, C_ID, C23S3_TU_AFTER)]
    fails += fuse_fails(rec2, gid, 0, True, "step 2: grenade")
    fails += common_fails(host, client, before, "C23s3")
    finish(fails)


def c23s2_skill_stop(host, client, ctx):
    notes = []
    tc0 = cancel_client_targeting(client)
    stripped = strip_both(host, client, C_ID)
    set_tu_both(host, client, C_ID, TU_MAX)
    staged = diff_buckets(host, client)
    tags0 = {"host": tags_of(host, C_ID), "client": tags_of(client, C_ID)}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    log0 = rlog(host)
    ev = {}
    win = {}
    dr = None
    out = {"state": "not pressed"}
    try:
        open_skill_menu(client, ev)
        dr = host.ok({"cmd": "defer_intents", "ms": DEFER_C23S2_MS, "count": 1})
        t0 = time.time()
        press(client, KEY_SKILL_STOP)
        flight = None
        while time.time() - t0 < SENT_WAIT_S:
            flight = event_state(client).get("inFlight")
            if flight:
                break
            time.sleep(POLL_S)
        # inside the defer window: the host has not taken the order yet
        win["inFlight"] = flight
        win["hostLogNew"] = rlog_new(log0, rlog(host))
        win["diff"] = diff_buckets(host, client)
        win["tu"] = (c_tu(host), c_tu(client))
        win["tags"] = {"host": tags_of(host, C_ID), "client": tags_of(client, C_ID)}
        win["hostLogNewAfter"] = rlog_new(log0, rlog(host))
        win["t"] = round(time.time() - t0, 3)
        out = {"state": "sent" if flight else "quiet", "t": win["t"]}
        if flight:
            try:
                client.wait_for("the order is over (client slot empty, host idle, client caught up)",
                                lambda: order_done(host, client) or None, timeout=ORDER_TIMEOUT_S, interval=0.1)
            except Exception as e:
                notes.append(f"order never finished: {short(e)}")
        else:
            time.sleep(0.5)
        out["tEnd"] = round(time.time() - t0, 3)
    except Exception as e:
        notes.append(f"real-UI SKILLS, key {KEY_SKILL_STOP}: {short(e)}")
    finally:
        try:
            disarm = host.ok({"cmd": "defer_intents", "ms": 0, "count": 0})   # never outlives C23s2
        except Exception as e:
            disarm = None
            notes.append(f"defer_intents disarm: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    log1 = rlog(host)
    new = ctx_view(before, rec)
    h = mine(new, "intent", "skill", C_ID)
    aid = h[0]["actionId"] if len(h) == 1 else None
    tags1 = {"host": tags_of(host, C_ID), "client": tags_of(client, C_ID)}
    print(f"EVIDENCE C23s2: staged stripped={stripped} stagedDiff={staged} tags before={tags0} "
          f"targetingCancel={tc0} press={ev} defer={dr} disarm={disarm} window={win} outcome={out}; "
          f"{press_view(before, rec)}; ui={ui_view(before, rec)}; newContexts={new}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain_of(rec, aid)]}; hostLogNew={rlog_new(log0, log1)}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; tags after={tags1}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if tags0["host"] != [] or tags0["client"] != []:
        fails.append(f"precondition: C's tags before {tags0} (want [] on both)")
    if ev.get("rows") != SKILL_ROWS:
        fails.append(f"precondition: client skill menu rows {ev.get('rows')} (want {SKILL_ROWS})")
    # inside the defer window
    fl = win.get("inFlight") or {}
    if fl.get("kind") != "skill" or fl.get("actorId") != C_ID:
        fails.append(f"inside the defer window: client inFlight {win.get('inFlight')} (want the `skill` order of C)")
    if win.get("hostLogNew") != [] or win.get("hostLogNewAfter") != []:
        fails.append(f"inside the defer window: the host took the order early (intentsReceivedLog new "
                     f"{win.get('hostLogNew')} / {win.get('hostLogNewAfter')}; want none: the checks ran in the window)")
    if win.get("diff") != []:
        fails.append(f"inside the defer window: buckets differ {win.get('diff')} (want none: the client ran nothing; "
                     f"C tu host/client {win.get('tu')}, tags {win.get('tags')})")
    # after the host's answer
    fails += forwarded_fails(before, rec)
    f, cx = admitted_kind_fails(before, rec, "skill", "skill", C_ID)
    fails += f
    fails += chain_fails(rec, aid, SKILL_CHAIN, "C23s2")
    fails += skill_end_fails(rec, aid, False, "C23s2")
    fails += rlog_fails(rlog_new(log0, log1), "skill", SKILL_STOP, "C23s2")
    if rec["clientUi"]["cursor"] in CURSOR_TARGETING:
        fails.append(f"client cursorType {rec['clientUi']['cursor']} after the stop (want not targeting)")
    fails += tu_fails(rec, C_ID, C23S2_TU_AFTER)
    if tags1["host"] != TAG_STOP_RAN or tags1["client"] != TAG_STOP_RAN:
        fails.append(f"C's tags after {tags1} (want {TAG_STOP_RAN} on both: the stop script's tag, delta-carried)")
    fails += common_fails(host, client, before, "C23s2")
    finish(fails)


# C23s2 runs LAST: its red leaves C's TU and tag split (W2-P1 A2.2 precedent).
SCENARIOS = (("C18", c18_spray), ("C16f", c16f_force_fire), ("C23s1", c23s1_skill_continue),
             ("C23s3", c23s3_skill_grenade), ("C23s2", c23s2_skill_stop))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    ml = {gc.name: mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), (
            f"{name}: {MOD_NAME} not active (active lines {m.get('active')}, invalid {m.get('invalid')}, "
            f"error {m.get('error')})")
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p4-se")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    assert (ub.get(C_ID) or {}).get("tu") == C_TU_FULL, f"C at bring-up {ubrief(ub.get(C_ID))} (baked TU {C_TU_FULL})"
    a = ub.get(A_ID) or {}
    assert a.get("status") == STATUS_STANDING and not a.get("isOut"), f"A at bring-up {ubrief(a)} (want standing)"
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastActionHalt" in es and "lastAftermath" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    mods = {gc.name: touch(gc) for gc in (host, client)}
    assert not any(v for m in mods.values() for v in m.values()), f"touch flags at bring-up {mods} (want all off)"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p4-se] boot ok: {MISSION} MAP_FP={MAP_FP!r} mod={ml} turn={hs['turn']} seated={seated_uids} "
          f"H={H_ID} pinned={len(pinned)} touch={mods} C={ubrief(ub.get(C_ID))} A={ubrief(ub.get(A_ID))} "
          f"A2={ubrief(ub.get(A2_ID))}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49878, make_user_dir("w2p4_client_rules_host", mods=[MOD_DIR]))
    client = GameClient("client", 49879, make_user_dir("w2p4_client_rules_client", mods=[MOD_DIR]))
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
                print(f"[w2p4-se] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_rules: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
