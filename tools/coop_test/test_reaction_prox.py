"""test_reaction_prox.py: reaction fire at the second player's walking soldier, and a proximity mine going off under
that walker, each run as its own named action NESTED inside the walk.

Without the fix the host cancels every reaction shot aimed at a client soldier (ProjectileFlyBState::init compares the
target with the HOST's selected unit) while the reaction check still stops the walk, so the second player's soldier
halts with "path blocked" and the alien never fires. A proximity mine under the walker explodes inside the walk's
action with no `prox_trigger` cue, and the walk also reports "path blocked". With the fix the host compares the
reaction target with the triggering unit, and the reaction and the mine each run as a context nested in the walk.

Three scenarios, ONE boot, in this order:

  reaction_fire   reaction fire halts the client's walk. A (the only alien) on HALTED_WALK_A_TILE facing
       HALTED_WALK_A_DIR, C on HALTED_WALK_C_TILE facing A; one END TURN cycle (no seed) so the player-side FOV puts A
       in C's spottedThisTurn (no new-spot halt at walk start); A reactions 100 + tu A_TU refilled (BOTH); the client
       TAB-selects C, the host set_seed HALTED_WALK_SEED, the client clicks HALTED_WALK_DEST (real UI, 3 planned steps).
       PASS: A's reaction shots happen and run under the walk W - inside ONE `reaction` context R {actorId A,
       nestedIn W}: R's evs are shot (actor A) -> hit(s) -> R's one bt_action_end, before W's end; every A shot/hit
       carries R; W {origin intent, kind walk, actorId C} halts after HALTED_WALK_EXECUTED with reason "reaction" on
       both machines; the client banner reads BANNER_UNDER_FIRE; C's outcome per the seed (health
       HALTED_WALK_C_HEALTH, not out) equal on both; A tu equal on both.
       Without the fix: (walk_step W)(bt_action_end W) only - no shot, no hit, A tu A_TU -> A_TU, halted "blocked",
       path HALTED_WALK_EXECUTED, banner "Move stopped - path blocked".
       The reaction_camera check: the host camera is staged on HOST_FAR_TILE (view level 1) before the click. PASS:
       host camera.suppressed follow == R's shot count and walkLevel == 2 x W's walk_step count (UnitWalkBState's
       off-screen step writes the view level twice), the host offset still the staged one, view level 1; client
       camera.moves hold {reaction_follow} per R shot, {restore} at R's bt_action_end whose `after` equals the offset
       at R's first shot, and {own_walker_level} per W step. Without the camera fix: counters 0, the host offset and
       view level moved, no client move. One "EVIDENCE reaction_camera:" line.
       The hit_log_mirror check: the hit log, both machines in English. At the quiescent point after the prep END
       TURN cycle (before the staging) the host holds one pending entry (the cycle's NEW_TURN) and both logs render
       equal; after the walk the client's hitLog text and diary == the host's, the host's text holds
       "Reaction fire...", the host sent HIT_LOG_ENTRIES since the quiescent point (counted per entry) and the client
       applied every entry the host sent. Without the hit-log mirror: the two logs differ after the walk (the client
       keeps its own "New Turn"), the mirror counters stay 0. One "EVIDENCE hit_log_mirror:" line.
  kneeled_walker   the kneeling walker. A reactions 0 (BOTH); C health C_MAX_HEALTH + tu TU_MAX (BOTH); C and A back
       on the reaction_fire tiles (BOTH); the client kneels C (real SDLK_k); A reactions 100 + tu A_TU refilled
       (BOTH); host set_seed KNEEL_SEED; the client clicks HALTED_WALK_DEST. The walk stands C up first (kneel() runs
       the reaction check for the stand-up).
       PASS: the stand-up `kneel` ev and every walk_step carry W (hooks owned by the base chain read the walk's own
       id); >= 1 `reaction` context nested in W (actorId A), one of them with no `shot` cue - the stand-up reaction,
       aimed at C's old tile and cancelled; every A shot/hit carries a `reaction` context nested in W, never W
       itself; W halts after KNEEL_EXECUTED with reason "reaction" (resolved in the catch-all) on both; banner
       BANNER_UNDER_FIRE; C's outcome per the seed (health KNEEL_C_HEALTH, not out) equal on both; A tu equal on
       both.
       Without the fix: (kneel W)(walk_step W)(bt_action_end W), no shot, halted "blocked".
  proximity_mine   a proximity mine under the walker. C health + tu (BOTH), C on MINE_C_TILE (BOTH, out of A's
       view); a primed fuse-0 STR_PROXIMITY_GRENADE G on MINE_TILE beside the path (battle_drop, BOTH, equal ids);
       host set_seed MINE_SEED; the client clicks MINE_DEST. The step adjacent to G (step 2) triggers it.
       PASS: ONE `prox` context P {actorId C, nestedIn W}: prox_trigger {unit C, item G, pos MINE_TILE} ->
       explosion -> ... -> P's one bt_action_end, before W's end; every explosion carries P; W halts after
       MINE_EXECUTED with reason "prox" on both; G absent on both; the client shows NO halt banner (a proximity-mine
       halt has no message, as in vanilla).
       Without the fix: (walk_step W)(walk_step W)(explosion W)(bt_action_end W), no prox_trigger, halted "blocked",
       banner "Move stopped - path blocked".

Common checks (each walk settled with wait_walk_settled + wait_host_idle): common_fails from test_delta_core (hash_now
{full:true} ALL buckets EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and host 0; client
deltaEvsApplied increased; deltaUnresolved, deltaUnsupported, deltaRemoveMissing, deltaAddExisting 0 on both); host
contextBeginRefused 0; contextsClosedAtEndTurn is a DIAGNOSTIC (printed, never asserted); every chain ev of the
scenario carries the id of a context the scenario closed; every context has exactly one bt_action_end, its last ev,
recorded in closedContexts (endSeq = that ev's seq); a nested context's end precedes its base's end; no `sync` inside
a context; contextsOpened grew by exactly the number of contexts closed; the client log holds the host's
seqs/kinds/actionIds. armingDeferrals is printed, never asserted.

Probes: event_state contextsOpened, closedContexts {actionId, origin, kind, actorId, nestedIn, endSeq, hasFinal},
contextsClosedAtEndTurn, contextBeginRefused, lastWalk {actionId, executed, restate {path, halted, reason}} on both
machines; event_log (seq, kind, actionId); the host's `[coop-cue] <kind> seq <n> actionId <id>: <payload>` log line
(coopEmitCue) for cue payloads; battle_state units and the client's coopWaitText banner; battle_items.

Bring-up (deterministic, never searched here): set_seed SEED_ROSTER on the HOST right before its open_new_battle; the
DEFAULT NEW BATTLE map with set_seed SEED_MAP right before newbattle_ok, seat_count=2, MAP_FP asserted on both;
session.pin_ai_neutral (pins A); every live player unit's reactions 0 on BOTH. Every test command pair applies to the
CLIENT first, then the HOST, responses asserted equal. The seeds were found with the host selecting C (host
`battle_action select`), which hides the bug; this test does NOT select C on the host, so only the fix makes it pass.

Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields BEFORE its pass conditions are checked;
main() runs every scenario even after an earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every
wait is bounded; a wait that times out is recorded in the EVIDENCE line and fails the scenario.

One run is the result. No skip path, no second boot, no alternative map or actor. Exit 0 only when all three
scenarios pass, 2 otherwise (a bring-up failure is also 2). Run in the foreground to completion.

Run:  python tools/coop_test/test_reaction_prox.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_seat_pacing import tab_select, real_click_walk
from test_delta_core import probes, diff_buckets, desync_record, short, both, tele_both, common_fails, finish, \
    delta_view
from test_delta_items import items_by_id
from test_host_combat import evs_since, ev_tuples, cue_probes, cue_delta
from test_host_combat import camera_of, cam_snap, cam_offset, stage_camera, cam_moves, mv, cam_suppressed_delta,     cam_view
from test_ai_origins import (host_payloads, ctx_probes, new_closed, opened_delta, ctx_of, ctx_view, sv, by_seq,
                                CHAIN_KINDS, end_turn_cycle, bring_up_lobby_roster_pinned)
from test_hit_log import hl_snap, hl_view, hl_count, hl_delta, STRINGS_EN

# ----- bring-up -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok; DEFAULT NEW BATTLE (no mission)
MAP_FP = -4.48310638993e+18      # host AND client battle_state.mapFingerprint (STR_UFO_GROUND_ASSAULT, small scout)
SEATED = [8, 9]                  # the client seat's soldiers
A_ID = 1000000                   # the only alien: Sectoid Soldier, plasma pistol 56 (ammo 57)
A_TYPE = "STR_SECTOID_SOLDIER"   # battle_state units[].type
C_ID = 8                         # the client's walker C ("Henryk Pawlowski", tu 64, health 40)
C_MAX_HEALTH = 40
TU_MAX = 255                     # battle_set_unit_state tu: clamped to the unit's max TU
A_TU = 54                        # set_stat tu 54 + refill (A's current bar)
A_REACTIONS = 100
SDLK_K = 107                     # Options::keyBattleKneel default (repro_atom_kneel.py)
PORT = "48629"
FACTION_PLAYER = 0

# ----- reaction_fire -----
HALTED_WALK_A_TILE, HALTED_WALK_A_DIR = (15, 2, 0), 4    # A faces south, C on its axis
HALTED_WALK_C_TILE, HALTED_WALK_C_DIR = (15, 7, 0), 0    # C faces A
HALTED_WALK_DEST = (18, 7, 0)                   # planned (16,7) (17,7) (18,7): every tile in A's view sector
HALTED_WALK_SEED = 3                            # host set_seed right before the client's click
HALTED_WALK_EXECUTED = [(16, 7, 0)]             # halted after step 1
HALTED_WALK_C_HEALTH = 21                       # two of A's three snaps hit C (40 -> 21), C standing
# reaction_camera: the host camera's staging
HOST_FAR_TILE = (38, 38, 1)            # the host camera at view level 1, > 1 screen from A, C and the walk (40x40x4)
WALK_LEVEL_WRITES_PER_STEP = 2         # with the host camera staged far the walker is off screen, so UnitWalkBState
                                       # runs keepWalking(..., false) (end = 2) and writes the view level (:204) on both
                                       # calls of each step (traced over the 4 steps of the three scenarios); the
                                       # guard counts every write it suppresses (no dedupe)
# hit_log_mirror (measured)
HIT_LOG_ENTRIES = 10                   # from the quiescent point after reaction_fire's END TURN cycle to the walk's end
                                       # the host sends the cycle's pending NEW_TURN + 9 chain entries (REACTION_FIRE
                                       # x4, NEW_SHOT, NEW_SHOT, BIG_DAMAGE, NEW_SHOT, NO_DAMAGE) on 6 evs, counted per
                                       # entry
HIT_LOG_PENDING_AT_QUIET = 1           # the cycle's NEW_TURN waits for the host's next emit

# ----- kneeled_walker -----
KNEEL_SEED = 2                         # host set_seed right before the client's click
KNEEL_EXECUTED = [(16, 7, 0)]          # halted after step 1
KNEEL_C_HEALTH = 40                    # A's three snaps land on terrain

# ----- proximity_mine -----
MINE_C_TILE, MINE_C_DIR = (2, 34, 0), 2   # SW field, > 20 tiles from A (out of A's view)
MINE_TILE = (5, 35, 0)                 # battle_drop STR_PROXIMITY_GRENADE {prime, fuse 0}, beside the path
MINE_DEST = (6, 34, 0)                 # planned (3,34) (4,34) (5,34) (6,34); step 2 (4,34) is adjacent to G
MINE_SEED = 5                          # host set_seed right before the client's click
MINE_EXECUTED = [(3, 34, 0), (4, 34, 0)]

# The client's halt banners (connectionTCP.cpp showWalkHalt's table, rendered en-US).
BANNER_UNDER_FIRE = "Order cancelled - unit under fire"   # STR_COOP_CANCEL_UNIT_UNDER_FIRE (reason `reaction`)
BANNER_BLOCKED = "Move stopped - path blocked"            # STR_COOP_HALT_PATH_BLOCKED (reason `blocked`)
HALT_BANNERS = ("Order cancelled - enemy spotted", BANNER_UNDER_FIRE, "Order cancelled - unit down",
                "Not Enough Time Units!", "Not Enough Energy!", BANNER_BLOCKED)
PAYLOAD_KINDS = ("shot", "hit", "explosion", "prox_trigger", "death", "corpse")


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def xyz(p):
    if not isinstance(p, dict):
        return None
    return (p.get("x"), p.get("y"), p.get("z"))


def path_of(lst):
    return [xyz(p) for p in (lst or [])]


def uview(u):
    if not u:
        return None
    return {k: u.get(k) for k in ("x", "y", "z", "direction", "tu", "health", "stun", "status", "isOut",
                                  "kneeled", "reactions")}


def walk_view(w):
    r = w.get("restate") or {}
    return {"actionId": w.get("actionId"), "unit": w.get("unit"), "executed": path_of(w.get("executed")),
            "plannedLen": w.get("plannedLen"), "active": w.get("active"),
            "restate": {"halted": r.get("halted"), "reason": r.get("reason"), "path": path_of(r.get("path"))}}


def restate_of(w):
    r = (w or {}).get("restate") or {}
    return (r.get("halted"), r.get("reason"), path_of(r.get("path")))


# ===================== the walk =====================


def client_walk(host, client, seed, dest, notes):
    """ONE real-UI walk order for C on the CLIENT: TAB-select C, host set_seed
    `seed` right before the click, one click on `dest`. Waits, bounded, for a
    NEW host walk chain to finish with the client caught up, then for the host
    to go idle. Returns the scenario record (probes before/after, both event
    logs since the host's last seq before the click, the host's cue payloads,
    both lastWalk records, both unit tables, the client's banner)."""
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": ctx_probes(host), "client": ctx_probes(client)}
    kb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    prev = session.walk_action_id(host)
    uh0, uc0 = units(host), units(client)
    try:
        if not tab_select(client, C_ID):
            notes.append(f"TAB never selected C on the client (selectedId "
                         f"{battle_state(client).get('selectedId')})")
        else:
            host.ok({"cmd": "set_seed", "seed": seed})
            real_click_walk(client, dest)
            session.wait_walk_settled(host, client, prev, timeout=30)
    except Exception as e:
        notes.append(f"walk: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the walk: {short(e)}")
    ph, pc = probes(host), probes(client)
    ca = {"host": ctx_probes(host), "client": ctx_probes(client)}
    ka = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    hw, cw = session.last_walk(host), session.last_walk(client)
    walk_id = hw.get("actionId") if hw.get("actionId", 0) != prev else None
    pl = host_payloads(host, [e["seq"] for e in hev if e["kind"] in PAYLOAD_KINDS])
    return {"seed": seed, "notes": notes, "before": before, "cb": cb, "ca": ca, "kb": kb, "ka": ka, "seq0": seq0,
            "prevWalk": prev, "W": walk_id, "hev": hev, "cev": cev, "pl": pl, "hw": hw, "cw": cw,
            "uh0": uh0, "uc0": uc0, "uh": units(host), "uc": units(client), "ph": ph, "pc": pc,
            "banner": battle_state(client).get("coopWaitText"), "hostBanner": battle_state(host).get("coopWaitText"),
            "closed": new_closed(cb["host"], ca["host"]), "opened": opened_delta(cb["host"], ca["host"]),
            "diff": diff_buckets(host, client), "desync": desync_record(client, pc["desyncSeen"])}


def payload(rec, e):
    return (rec["pl"].get(e["seq"]) or {}).get("payload") or {}


def evs_of(rec, aid):
    return [e for e in rec["hev"] if aid and e["actionId"] == aid]


def nested_in(rec, w):
    return [c for c in rec["closed"] if w and c.get("nestedIn") == w]


# ===================== evidence =====================


def walk_evidence(rec, what):
    ph, pc = rec["ph"], rec["pc"]
    cb, ca = rec["cb"]["host"], rec["ca"]["host"]
    cues = [(e["seq"], e["kind"], e["actionId"], payload(rec, e)) for e in rec["hev"] if e["kind"] in PAYLOAD_KINDS]
    ah0, ah, ac = rec["uh0"].get(A_ID) or {}, rec["uh"].get(A_ID) or {}, rec["uc"].get(A_ID) or {}
    ch, cc = rec["uh"].get(C_ID) or {}, rec["uc"].get(C_ID) or {}
    return (f"{what} seed={rec['seed']} walk W={rec['W']} (prev {rec['prevWalk']}); host evs since seq {rec['seq0']}="
            f"{ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])} (seq, kind, actionId, h); host cues (seq, "
            f"kind, actionId, payload)={cues}; closedContexts(new, host)={[ctx_view(c) for c in rec['closed']]}; "
            f"contextsOpened delta(host)={rec['opened']}; contextsClosedAtEndTurn(host, diagnostic)="
            f"{cb['contextsClosedAtEndTurn']}->{ca['contextsClosedAtEndTurn']}; contextBeginRefused(host)="
            f"{ca['contextBeginRefused']}; armingDeferrals(host)={cb['armingDeferrals']}->{ca['armingDeferrals']}; "
            f"client context probes: closedContexts {len(rec['ca']['client']['closedContexts'])} contextsOpened "
            f"{rec['ca']['client']['contextsOpened']}; lastWalk host={walk_view(rec['hw'])} client="
            f"{walk_view(rec['cw'])}; banner client={rec['banner']!r} host={rec['hostBanner']!r}; A host "
            f"tu {ah0.get('tu')}->{ah.get('tu')} {uview(ah)} client {uview(ac)}; C host {uview(ch)} client "
            f"{uview(cc)}; cueCounts delta host="
            f"{cue_delta(rec['kb']['host']['cueCounts'], rec['ka']['host']['cueCounts'])} client="
            f"{cue_delta(rec['kb']['client']['cueCounts'], rec['ka']['client']['cueCounts'])}; diffAfter="
            f"{rec['diff']}; desyncSeen host={ph['desyncSeen']} client={pc['desyncSeen']} desync={rec['desync']}; "
            f"host {delta_view(rec['before']['host'])}->{delta_view(ph)}; client "
            f"{delta_view(rec['before']['client'])}->{delta_view(pc)}; host lastDelta={ph['lastDelta']}; "
            f"notes={rec['notes']}")


# ===================== common checks =====================


def context_fails(rec, what):
    """The common checks on the context side, over the host evs of one
    scenario: contextBeginRefused 0 on the host; contextsOpened grew by
    exactly the number of contexts closed; every chain ev carries the id of a
    context this scenario closed; every actionId has exactly one
    bt_action_end, its last ev, recorded in closedContexts with endSeq = its
    seq; a nested context's end precedes its base's end; no `sync` inside a
    context; every side_transition carries actionId 0; the client log holds
    the host's seq/kind/actionId for every ev of every context."""
    fails = []
    hev, cev, closed = rec["hev"], rec["cev"], rec["closed"]
    ca = rec["ca"]["host"]
    if ca["contextBeginRefused"] != 0:
        fails.append(f"{what}: host contextBeginRefused={ca['contextBeginRefused']} (want 0)")
    n_open = sum(rec["opened"].values())
    if n_open != len(closed):
        fails.append(f"{what}: host contextsOpened +{n_open} {rec['opened']} but closedContexts +{len(closed)} "
                     f"(want every context the scenario opened closed and recorded)")
    ids = {c.get("actionId") for c in closed}
    for e in hev:
        if e["kind"] == "side_transition" and e["actionId"] != 0:
            fails.append(f"{what}: side_transition seq {e['seq']} carries actionId {e['actionId']} (want 0)")
        if e["kind"] in CHAIN_KINDS and (not e["actionId"] or e["actionId"] not in ids):
            fails.append(f"{what}: {e['kind']} seq {e['seq']} carries actionId {e['actionId']} (want the id of a "
                         f"context this scenario closed: {sorted(ids)})")
    cmap = by_seq(cev)
    syncs = [e["seq"] for e in hev if e["kind"] == "sync"]
    for aid in sorted({e["actionId"] for e in hev if e["actionId"]}):
        evs = evs_of(rec, aid)
        kinds = [e["kind"] for e in evs]
        if kinds.count("bt_action_end") != 1 or kinds[-1] != "bt_action_end":
            fails.append(f"{what}: context {aid} evs {sv(evs)} (want exactly one bt_action_end, its last ev)")
        c = ctx_of(closed, aid)
        if not c:
            fails.append(f"{what}: context {aid} (evs {sv(evs)}) is not in the host's closedContexts (new entries "
                         f"{[ctx_view(x) for x in closed]})")
        elif c.get("endSeq") != evs[-1]["seq"]:
            fails.append(f"{what}: closedContexts {ctx_view(c)} endSeq != its last ev seq {evs[-1]['seq']}")
        inside = [s for s in syncs if evs[0]["seq"] < s < evs[-1]["seq"]]
        if inside:
            fails.append(f"{what}: `sync` seq(s) {inside} inside context {aid} ({sv(evs)}) (want none)")
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"]) and (cmap[e["seq"]]["kind"], cmap[e["seq"]]["actionId"]))
               for e in evs if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"]
               or cmap[e["seq"]]["actionId"] != aid]
        if bad:
            fails.append(f"{what}: client event_log does not hold the host's evs of context {aid}: "
                         f"(seq, host kind, client (kind, actionId))={bad}")
    for c in closed:
        ends = [e["seq"] for e in hev if e["actionId"] == c.get("actionId") and e["kind"] == "bt_action_end"]
        if ends != [c.get("endSeq")]:
            fails.append(f"{what}: closedContexts {ctx_view(c)} - its bt_action_end seq(s) in the host log = {ends} "
                         f"(want exactly [endSeq])")
        if c.get("nestedIn"):
            base = ctx_of(closed, c.get("nestedIn"))
            if not base:
                fails.append(f"{what}: {ctx_view(c)} is nested in {c.get('nestedIn')}, not a context this scenario "
                             f"closed")
            elif not (c.get("endSeq") or 0) < (base.get("endSeq") or 0):
                fails.append(f"{what}: nested {ctx_view(c)} ends at seq {c.get('endSeq')}, not before its base "
                             f"{ctx_view(base)}")
    return fails


def walk_context_fails(rec, executed, what):
    """W: a NEW host walk chain, recorded as {origin intent, kind walk, actorId
    C, nestedIn 0, hasFinal true}; its walk_step evs (one per executed step)
    carry W; the executed prefix is `executed`."""
    fails = []
    w = rec["W"]
    if not w:
        return [f"{what}: no new host walk chain (lastWalk {walk_view(rec['hw'])}, previous {rec['prevWalk']})"]
    wc = ctx_of(rec["closed"], w)
    if not wc or (wc.get("origin"), wc.get("kind"), wc.get("actorId"), wc.get("nestedIn"), wc.get("hasFinal")) != (
            "intent", "walk", C_ID, 0, True):
        fails.append(f"{what}: the walk context {w} = {ctx_view(wc)} (want origin intent, kind walk, actorId {C_ID}, "
                     f"nestedIn 0, hasFinal true)")
    steps = [e for e in rec["hev"] if e["kind"] == "walk_step"]
    if len(steps) != len(executed) or any(e["actionId"] != w for e in steps):
        fails.append(f"{what}: walk_step evs {sv(steps)} (want {len(executed)}, each carrying W {w})")
    ex = path_of(rec["hw"].get("executed"))
    if ex != executed:
        fails.append(f"{what}: host executed path {ex} (want {executed})")
    return fails


def halt_fails(rec, reason, executed, what):
    """W's end, on BOTH machines' lastWalk: halted, `reason`, path = the
    executed prefix."""
    fails = []
    want = (True, reason, executed)
    for name, lw in (("host", rec["hw"]), ("client", rec["cw"])):
        if rec["W"] and lw.get("actionId") != rec["W"]:
            fails.append(f"{what}: {name} lastWalk actionId {lw.get('actionId')} (want W {rec['W']})")
        got = restate_of(lw)
        if got != want:
            fails.append(f"{what}: {name} walk end (halted, reason, path)={got} (want {want})")
    return fails


def equal_fails(rec, what):
    """C pos/TU/health and A TU equal on both machines."""
    fails = []
    ch, cc = rec["uh"].get(C_ID) or {}, rec["uc"].get(C_ID) or {}
    ah, ac = rec["uh"].get(A_ID) or {}, rec["uc"].get(A_ID) or {}
    kc = ("x", "y", "z", "tu", "health", "stun", "status", "isOut")
    if tuple(ch.get(k) for k in kc) != tuple(cc.get(k) for k in kc):
        fails.append(f"{what}: C host {uview(ch)} client {uview(cc)} (want pos/TU/health equal)")
    if ah.get("tu") != ac.get("tu"):
        fails.append(f"{what}: A tu host={ah.get('tu')} client={ac.get('tu')} (want equal)")
    return fails


def reaction_fails(rec, what):
    """A fired: >= 1 `shot` cue with actor A and >= 1 `hit`; every
    shot/hit carries a `reaction` context {actorId A} nested in W - never W
    itself, never 0; every reaction context nested in W has actorId A.
    Returns (fails, the reaction contexts nested in W)."""
    fails = []
    w = rec["W"]
    ah0, ah = rec["uh0"].get(A_ID) or {}, rec["uh"].get(A_ID) or {}
    shots = [e for e in rec["hev"] if e["kind"] == "shot"]
    hits = [e for e in rec["hev"] if e["kind"] == "hit"]
    ashots = [e for e in shots if payload(rec, e).get("actor") == A_ID]
    nested = nested_in(rec, w)
    rctx = [c for c in nested if c.get("origin") == "reaction"]
    rids = {c.get("actionId") for c in rctx}
    if not ashots:
        fails.append(f"{what}: A never fired - no `shot` cue with actor {A_ID} (A tu {ah0.get('tu')}->{ah.get('tu')} "
                     f"on the host; host evs {sv(rec['hev'])})")
    if not hits:
        fails.append(f"{what}: no `hit` cue in the scenario (host evs {sv(rec['hev'])})")
    if not rctx:
        fails.append(f"{what}: no `reaction` context nested in W {w} (new closedContexts "
                     f"{[ctx_view(c) for c in rec['closed']]})")
    for c in rctx:
        if c.get("actorId") != A_ID:
            fails.append(f"{what}: reaction context {ctx_view(c)} (want actorId {A_ID})")
    for e in shots:
        pa = payload(rec, e).get("actor")
        if e["actionId"] not in rids or pa != A_ID:
            fails.append(f"{what}: shot seq {e['seq']} carries actionId {e['actionId']} actor {pa} (want a `reaction` "
                         f"context nested in W {w}: {sorted(rids)}, actor {A_ID})")
    for e in hits:
        if e["actionId"] not in rids:
            fails.append(f"{what}: hit seq {e['seq']} carries actionId {e['actionId']} (want a `reaction` context "
                         f"nested in W {w}: {sorted(rids)})")
    return fails, rctx


def outcome_fails(rec, health, what):
    """C's outcome per the seed: health `health`, not out, on both."""
    fails = []
    for name, u in (("host", rec["uh"].get(C_ID) or {}), ("client", rec["uc"].get(C_ID) or {})):
        if u.get("health") != health or u.get("isOut"):
            fails.append(f"{what}: C on the {name} {uview(u)} (want health {health}, not out - the seed's outcome)")
    return fails


def camera_fails(rec, staged, cam0, cam1):
    """reaction_camera: reaction fire at the client's walker. HOST (the walk W is the partner's order, R is nested
    in it): camera.suppressed.follow == R's `shot` count, suppressed.walkLevel == WALK_LEVEL_WRITES_PER_STEP x W's
    `walk_step` count, the offset still the staged one and the view level 1. CLIENT: {reaction_follow} at each R
    shot seq; {restore} at R's bt_action_end seq whose `after` equals the `before` of the reaction_follow record at
    R's first shot (the offset saved for the restore); {own_walker_level} at each W walk_step seq. Prints one
    "EVIDENCE reaction_camera:" line."""
    w = rec["W"]
    rctx = [c for c in nested_in(rec, w) if c.get("origin") == "reaction"]
    r = rctx[0].get("actionId") if len(rctx) == 1 else None
    revs = evs_of(rec, r)
    r_shots = [e["seq"] for e in revs if e["kind"] == "shot"]
    r_end = [e["seq"] for e in revs if e["kind"] == "bt_action_end"]
    w_steps = [e["seq"] for e in rec["hev"] if e["kind"] == "walk_step" and w and e["actionId"] == w]
    sup = cam_suppressed_delta(cam0["host"], cam1["host"])
    moves = cam_moves(cam1["client"], rec["seq0"])
    print(f"EVIDENCE reaction_camera: R={r} shot seqs={r_shots} end={r_end}; W={w} walk_step seqs={w_steps}; host "
          f"staged={cam_offset(staged)} before={cam_view(cam0['host'])} after={cam_view(cam1['host'])} suppressed "
          f"delta={sup}; client before={cam_view(cam0['client'], rec['seq0'])} "
          f"after={cam_view(cam1['client'], rec['seq0'])}", flush=True)
    fails = []
    if r is None or not r_shots or len(r_end) != 1 or not w_steps:
        fails.append(f"reaction_camera: precondition: R {r} shots {r_shots} end {r_end}, W {w} steps {w_steps} (want "
                     f"one reaction context with >= 1 shot and its bt_action_end, and >= 1 walk_step of W)")
    if (sup["follow"], sup["walkLevel"]) != (len(r_shots), WALK_LEVEL_WRITES_PER_STEP * len(w_steps)):
        fails.append(f"reaction_camera: host camera.suppressed delta follow {sup['follow']} walkLevel "
                     f"{sup['walkLevel']} (want {len(r_shots)} = R's shots, "
                     f"{WALK_LEVEL_WRITES_PER_STEP * len(w_steps)} = {WALK_LEVEL_WRITES_PER_STEP} x W's {len(w_steps)} "
                     f"steps)")
    if cam_offset(cam1["host"]) != cam_offset(staged) or cam1["host"].get("viewLevel") != HOST_FAR_TILE[2]:
        fails.append(f"reaction_camera: host camera offset {cam_offset(cam1['host'])} viewLevel "
                     f"{cam1['host'].get('viewLevel')} after the walk (want the staged {cam_offset(staged)}, view "
                     f"level {HOST_FAR_TILE[2]}: the partner's walk and the reaction inside it never move the host's "
                     f"camera)")
    got = [mv(m) for m in moves]
    need = [(s, "reaction_follow") for s in r_shots] + [(s, "restore") for s in r_end] +         [(s, "own_walker_level") for s in w_steps]
    missing = [x for x in need if x not in got]
    if missing:
        fails.append(f"reaction_camera: client camera.moves lack {missing} (want {need}; moves {got})")
    rf = [m for m in moves if r_shots and mv(m) == (r_shots[0], "reaction_follow")]
    rs = [m for m in moves if r_end and mv(m) == (r_end[0], "restore")]
    if rf and rs and rs[0].get("after") != rf[0].get("before"):
        fails.append(f"reaction_camera: client restore after={rs[0].get('after')} (want the offset at R's first shot "
                     f"{rf[0].get('before')})")
    return fails


def hit_log_fails(hl_a, hl_q, hl_b):
    """hit_log_mirror: the reaction fire at the client's walker in the hit log, both machines in English. At the
    quiescent point after reaction_fire's END TURN cycle (before its staging): the host holds exactly
    HIT_LOG_PENDING_AT_QUIET pending entry (the cycle's NEW_TURN) and both logs render equal. After the walk: the
    client's hitLog text and diary == the host's, the host's text holds "Reaction fire...", the host sent
    HIT_LOG_ENTRIES entries since the quiescent point (counted per entry), nothing is pending and the client applied
    every entry the host sent (applied == sent). Prints one "EVIDENCE hit_log_mirror:" line."""
    hq, cq = hl_q["host"], hl_q["client"]
    hb, cb = hl_b["host"], hl_b["client"]
    sent = hl_delta(hl_q, hl_b, "host", "sent")
    print(f"EVIDENCE hit_log_mirror: before the cycle {hl_view(hl_a)}; quiescent point {hl_view(hl_q)}; after the walk "
          f"{hl_view(hl_b)}", flush=True)
    fails = []
    if cb["log"] != hb["log"]:
        fails.append(f"hit_log_mirror: client hitLog {cb['log']} != host {hb['log']} after the walk (want the same "
                     f"text and diary: the host's log mirrored)")
    if STRINGS_EN["REACTION_FIRE"] not in (hb["log"].get("text") or ""):
        fails.append(f"hit_log_mirror: host hitLog text {hb['log'].get('text')!r} (want it to hold "
                     f"{STRINGS_EN['REACTION_FIRE']!r})")
    if hl_count(hq["mirror"], "pending") != HIT_LOG_PENDING_AT_QUIET:
        fails.append(f"hit_log_mirror: the host's pending entries at the quiescent point after the cycle "
                     f"{hl_count(hq['mirror'], 'pending')} (want {HIT_LOG_PENDING_AT_QUIET}: the cycle's NEW_TURN)")
    if cq["log"] != hq["log"]:
        fails.append(f"hit_log_mirror: client hitLog {cq['log']} != host {hq['log']} at the quiescent point after the "
                     f"cycle (want equal renders)")
    if sent != HIT_LOG_ENTRIES or hl_count(hb["mirror"], "pending"):
        fails.append(f"hit_log_mirror: the host sent +{sent} entries from the quiescent point to the walk's end, "
                     f"pending {hl_count(hb['mirror'], 'pending')} (want +{HIT_LOG_ENTRIES}, 0)")
    if hl_count(cb["mirror"], "applied") != hl_count(hb["mirror"], "sent"):
        fails.append(f"hit_log_mirror: client applied {hl_count(cb['mirror'], 'applied')} != host sent "
                     f"{hl_count(hb['mirror'], 'sent')} after the walk (want equal)")
    return fails


# ===================== scenarios =====================


def run_reaction_fire(host, client, ctx):
    notes = []
    # prep: A and C face each other; one END TURN cycle (no seed) so the player-side FOV
    # recalculation puts A in C's spottedThisTurn (a teleport skips calculateFOV).
    tele_both(host, client, A_ID, HALTED_WALK_A_TILE, HALTED_WALK_A_DIR)
    tele_both(host, client, C_ID, HALTED_WALK_C_TILE, HALTED_WALK_C_DIR)
    hl_a = hl_snap(host, client)   # hit_log_mirror: before the prep cycle
    turn0 = end_turn_cycle(host, client, None, notes)
    hs, cs = battle_state(host), battle_state(client)
    spotted = (units(host).get(C_ID) or {}).get("spottedThisTurn")
    prep_diff = diff_buckets(host, client)
    ctx["prep"] = {"turn": (turn0, hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")),
                   "spotted": spotted, "diff": prep_diff}
    hl_q = hl_snap(host, client)   # hit_log_mirror: the quiescent point after the cycle, before the staging
    # reaction_fire staging
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "reactions",
                        "value": A_REACTIONS}, ("tu",))
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU,
                        "refill": True}, ("tu",))
    staged_diff = diff_buckets(host, client)
    camera_staged = stage_camera(host, HOST_FAR_TILE)   # reaction_camera: the host camera far, view level 1
    cam0 = cam_snap(host, client)
    rec = client_walk(host, client, HALTED_WALK_SEED, HALTED_WALK_DEST, notes)
    cam1 = cam_snap(host, client)
    hl_b = hl_snap(host, client)   # hit_log_mirror: after the walk
    w = rec["W"]
    print(f"EVIDENCE reaction_fire: prep {ctx['prep']}; A {HALTED_WALK_A_TILE}/{HALTED_WALK_A_DIR} "
          f"C {HALTED_WALK_C_TILE}/{HALTED_WALK_C_DIR} dest {HALTED_WALK_DEST} "
          f"stagedDiff={staged_diff}; {walk_evidence(rec, 'reaction_fire')}", flush=True)
    camera_checks = camera_fails(rec, camera_staged, cam0, cam1)
    hit_log_checks = hit_log_fails(hl_a, hl_q, hl_b)
    fails = list(notes)
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER, turn0 + 1,
                                                                           FACTION_PLAYER):
        fails.append(f"prep cycle: not on player turn {turn0 + 1} on both: {ctx['prep']['turn']}")
    if A_ID not in (spotted or []):
        fails.append(f"prep cycle: host C spottedThisTurn={spotted} (want A {A_ID} in it: no new-spot halt)")
    if prep_diff or staged_diff:
        fails.append(f"buckets differ after the staging: prep={prep_diff} staged={staged_diff} (want none)")
    fails += walk_context_fails(rec, HALTED_WALK_EXECUTED, "reaction_fire")
    rf, rctx = reaction_fails(rec, "reaction_fire")
    fails += rf
    nested = nested_in(rec, w)
    if len(nested) != 1 or len(rctx) != 1:
        fails.append(f"reaction_fire: contexts nested in W {w} = {[ctx_view(c) for c in nested]} (want exactly one: R "
                     f"{{origin reaction, actorId {A_ID}, nestedIn {w}}})")
    if rctx:
        r = rctx[0]
        rk = [e["kind"] for e in evs_of(rec, r.get("actionId"))]
        if (not rk or rk[0] != "shot" or rk[-1] != "bt_action_end" or "hit" not in rk
                or any(k not in ("shot", "hit") for k in rk[:-1])):
            fails.append(f"reaction_fire: R {r.get('actionId')} evs {sv(evs_of(rec, r.get('actionId')))} (want shot "
                         f"(actor A) -> hit(s) -> bt_action_end)")
    fails += halt_fails(rec, "reaction", HALTED_WALK_EXECUTED, "reaction_fire")
    if rec["banner"] != BANNER_UNDER_FIRE:
        fails.append(f"reaction_fire: client banner {rec['banner']!r} (want {BANNER_UNDER_FIRE!r})")
    fails += outcome_fails(rec, HALTED_WALK_C_HEALTH, "reaction_fire")
    fails += equal_fails(rec, "reaction_fire")
    fails += context_fails(rec, "reaction_fire")
    fails += common_fails(host, client, rec["before"], {}, "reaction_fire")
    fails += camera_checks
    fails += hit_log_checks
    finish(fails)


def run_kneeled_walker(host, client, ctx):
    notes = []
    # re-stage: A quiet, C healed, both back on the reaction_fire tiles, C kneels (real UI)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "reactions",
                        "value": 0}, ("tu",))
    both(host, client, {"cmd": "battle_set_unit_state", "unit": C_ID, "health": C_MAX_HEALTH, "tu": TU_MAX},
         ("health", "stun", "status", "tu"))
    tele_both(host, client, C_ID, HALTED_WALK_C_TILE, HALTED_WALK_C_DIR)
    tele_both(host, client, A_ID, HALTED_WALK_A_TILE, HALTED_WALK_A_DIR)
    kseq0 = probes(host)["lastSeqEmitted"] or 0
    try:
        if not tab_select(client, C_ID):
            notes.append(f"TAB never selected C on the client for the kneel (selectedId "
                         f"{battle_state(client).get('selectedId')})")
        else:
            client.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
            client.wait_for("C kneeled on both",
                            lambda: ((units(host).get(C_ID) or {}).get("kneeled")
                                     and (units(client).get(C_ID) or {}).get("kneeled")) or None, timeout=10)
            session.wait_host_idle(host, client, timeout=20)
    except Exception as e:
        notes.append(f"kneel: {short(e)}")
    kneel_evs = sv(evs_since(host, kseq0))
    kneeled = ((units(host).get(C_ID) or {}).get("kneeled"), (units(client).get(C_ID) or {}).get("kneeled"))
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "reactions",
                        "value": A_REACTIONS}, ("tu",))
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU,
                        "refill": True}, ("tu",))
    staged_diff = diff_buckets(host, client)
    rec = client_walk(host, client, KNEEL_SEED, HALTED_WALK_DEST, notes)
    w = rec["W"]
    kneels = [e for e in rec["hev"] if e["kind"] == "kneel"]
    steps = [e for e in rec["hev"] if e["kind"] == "walk_step"]
    print(f"EVIDENCE kneeled_walker: kneel staging evs={kneel_evs} kneeled host/client={kneeled} "
          f"stagedDiff={staged_diff}; {walk_evidence(rec, 'kneeled_walker')}", flush=True)
    fails = list(notes)
    if kneeled != (True, True):
        fails.append(f"kneeled_walker staging: C kneeled host/client={kneeled} before the walk (want True on both)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += walk_context_fails(rec, KNEEL_EXECUTED, "kneeled_walker")
    if len(kneels) != 1 or kneels[0]["actionId"] != w or not steps or kneels[0]["seq"] > steps[0]["seq"]:
        fails.append(f"kneeled_walker: the stand-up kneel evs {sv(kneels)} (want exactly one, carrying W {w}, before "
                     f"the first walk_step {sv(steps[:1])})")
    rf, rctx = reaction_fails(rec, "kneeled_walker")
    fails += rf
    nested = nested_in(rec, w)
    other = [c for c in nested if c.get("origin") != "reaction"]
    if other:
        fails.append(f"kneeled_walker: non-reaction contexts nested in W {w}: {[ctx_view(c) for c in other]} "
                     f"(want none)")
    shot_ids = {e["actionId"] for e in rec["hev"] if e["kind"] == "shot"}
    quiet = [c for c in rctx if c.get("actionId") not in shot_ids]
    if not quiet:
        fails.append(f"kneeled_walker: no `reaction` context nested in W {w} without a `shot` cue (want the stand-up "
                     f"reaction, cancelled; reaction contexts {[ctx_view(c) for c in rctx]})")
    fails += halt_fails(rec, "reaction", KNEEL_EXECUTED, "kneeled_walker")
    if rec["banner"] != BANNER_UNDER_FIRE:
        fails.append(f"kneeled_walker: client banner {rec['banner']!r} (want {BANNER_UNDER_FIRE!r})")
    fails += outcome_fails(rec, KNEEL_C_HEALTH, "kneeled_walker")
    fails += equal_fails(rec, "kneeled_walker")
    fails += context_fails(rec, "kneeled_walker")
    fails += common_fails(host, client, rec["before"], {}, "kneeled_walker")
    finish(fails)


def run_proximity_mine(host, client, ctx):
    notes = []
    both(host, client, {"cmd": "battle_set_unit_state", "unit": C_ID, "health": C_MAX_HEALTH, "tu": TU_MAX},
         ("health", "stun", "status", "tu"))
    tele_both(host, client, C_ID, MINE_C_TILE, MINE_C_DIR)
    g = both(host, client, {"cmd": "battle_drop", "x": MINE_TILE[0], "y": MINE_TILE[1],
                            "z": MINE_TILE[2], "item": "STR_PROXIMITY_GRENADE", "prime": True, "fuse": 0},
             ("ids",))["ids"]
    gid = g[0] if g else None
    staged_diff = diff_buckets(host, client)
    rec = client_walk(host, client, MINE_SEED, MINE_DEST, notes)
    w = rec["W"]
    ih, ic = items_by_id(host), items_by_id(client)
    g_gone = {"host": gid not in ih, "client": gid not in ic}
    nested = nested_in(rec, w)
    pctx = [c for c in nested if c.get("origin") == "prox"]
    p = pctx[0] if pctx else None
    pevs = evs_of(rec, p.get("actionId")) if p else []
    trig = [e for e in rec["hev"] if e["kind"] == "prox_trigger"]
    expl = [e for e in rec["hev"] if e["kind"] == "explosion"]
    print(f"EVIDENCE proximity_mine: grenade G={g} on {MINE_TILE} C {MINE_C_TILE}/{MINE_C_DIR} dest {MINE_DEST} "
          f"stagedDiff={staged_diff}; prox context={ctx_view(p)} its evs={sv(pevs)}; prox_trigger evs="
          f"{[(e['seq'], e['actionId'], payload(rec, e)) for e in trig]}; G gone={g_gone}; "
          f"{walk_evidence(rec, 'proximity_mine')}", flush=True)
    fails = list(notes)
    if len(g) != 1:
        fails.append(f"battle_drop returned ids {g} (want exactly one grenade)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += walk_context_fails(rec, MINE_EXECUTED, "proximity_mine")
    if len(nested) != 1 or not p or (p.get("origin"), p.get("actorId")) != ("prox", C_ID):
        fails.append(f"proximity_mine: contexts nested in W {w} = {[ctx_view(c) for c in nested]} (want exactly one: "
                     f"P {{origin prox, actorId {C_ID}, nestedIn {w}}})")
    if len(trig) != 1:
        fails.append(f"proximity_mine: prox_trigger evs {sv(trig)} (want exactly one)")
    if p:
        pk = [e["kind"] for e in pevs]
        if len(pk) < 3 or pk[0] != "prox_trigger" or pk[1] != "explosion" or pk[-1] != "bt_action_end":
            fails.append(f"proximity_mine: P {p.get('actionId')} evs {sv(pevs)} (want prox_trigger -> explosion -> "
                         f"... -> bt_action_end)")
        if pevs and pevs[0]["kind"] == "prox_trigger":
            tp = payload(rec, pevs[0])
            if (tp.get("unit"), tp.get("item"), xyz(tp.get("pos"))) != (C_ID, gid, MINE_TILE):
                fails.append(f"proximity_mine: prox_trigger payload {tp or None} (want unit {C_ID}, item {gid}, pos "
                             f"{MINE_TILE})")
    if not expl:
        fails.append(f"proximity_mine: no `explosion` ev in the scenario (host evs {sv(rec['hev'])})")
    for e in expl:
        if not p or e["actionId"] != p.get("actionId"):
            fails.append(f"proximity_mine: explosion seq {e['seq']} carries actionId {e['actionId']} (W is {w}; want "
                         f"the `prox` context {p and p.get('actionId')})")
    fails += halt_fails(rec, "prox", MINE_EXECUTED, "proximity_mine")
    if rec["banner"] in HALT_BANNERS:
        fails.append(f"proximity_mine: client banner {rec['banner']!r} (want no halt banner - a proximity-mine halt "
                     f"shows no message)")
    if not g_gone["host"] or not g_gone["client"]:
        fails.append(f"proximity_mine: grenade {gid} present after the walk host={not g_gone['host']} client="
                     f"{not g_gone['client']} (want absent on both)")
    fails += equal_fails(rec, "proximity_mine")
    fails += context_fails(rec, "proximity_mine")
    fails += common_fails(host, client, rec["before"], {}, "proximity_mine")
    finish(fails)


SCENARIOS = (("reaction_fire", run_reaction_fire), ("kneeled_walker", run_kneeled_walker),
             ("proximity_mine", run_proximity_mine))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, baked "
        f"MAP_FP={MAP_FP!r} (default NEW BATTLE, SEED_MAP {SEED_MAP})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    pinned = pin_ai_neutral(host, client, tag="reaction_prox")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A {A_ID} battle_state type host/client={types} (want {A_TYPE})"
    # every live player unit's reactions 0 on BOTH machines (A's reactions are the scenarios' own staging)
    rz = []
    for uid, u in sorted(uh.items()):
        if u.get("faction") == FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
            rz.append(uid)
    for gc in (host, client):
        es = event_state(gc)
        # lastWalk is null until the battle's first walk (connectionTCP.cpp g_coopLastWalk), so it is not checked here
        assert (isinstance(es.get("contextsOpened"), dict) and isinstance(es.get("closedContexts"), list)
                and isinstance(es.get("contextsClosedAtEndTurn"), int)
                and isinstance(es.get("contextBeginRefused"), int)), (
            f"{gc.name} event_state lacks the context probes: contextsOpened={es.get('contextsOpened')!r} "
            f"closedContexts={es.get('closedContexts')!r} contextsClosedAtEndTurn="
            f"{es.get('contextsClosedAtEndTurn')!r} contextBeginRefused={es.get('contextBeginRefused')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[reaction_prox] boot ok: SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={SEATED} "
          f"pinned={pinned} A type={types[0]} reactions 0 (both) for {rz} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49854, make_user_dir("reaction_prox_host"))
    client = GameClient("client", 49855, make_user_dir("reaction_prox_client"))
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
                print(f"[reaction_prox] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_reaction_prox: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
