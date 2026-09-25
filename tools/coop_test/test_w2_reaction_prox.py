"""W2-P3 S-B - test_w2_reaction_prox.py: reaction fire at the second player's
walking soldier, and a proximity mine going off under that walker, each run as
its own named action NESTED inside the walk (spec
rewrite/prompts/w2p3_nonplayer_origins.md section (f) "test_w2_reaction_prox.py
(S-B)", sections (b)2-3 nesting and (b)8 latches, amendments B1 (RQ4, RQ5,
RQ8, RQ15) and B3 (owner ruling D145 = a); D139).

Before S-B, on the W2-P3 base, the host cancels every reaction shot aimed at a
client soldier (ProjectileFlyBState::init compares the target with the HOST's
selected unit, F810) while the reaction check still stops the walk, so the
second player's soldier halts with "path blocked" and the alien never fires.
A proximity mine under the walker explodes inside the walk's action with no
`prox_trigger` cue, and the walk also reports "path blocked".

Three scenarios, ONE boot, in this order (TASK 0a / 0c one-boot order):

  C8   reaction fire halts the client's walk (revisit row 6). A (the only
       alien) on C8_A_TILE facing C8_A_DIR, C on C8_C_TILE facing A; one END
       TURN cycle (no seed) so the player-side FOV puts A in C's
       spottedThisTurn (no new-spot halt at walk start); A reactions 100 + tu
       A_TU refilled (BOTH); the client TAB-selects C, the host set_seed
       SEED_C8, the client clicks C8_DEST (real UI, 3 planned steps).
       GREEN (B3 + (f)): A's reaction shots happen (D145) and run under the
       walk W - inside ONE `reaction` context R {actorId A, nestedIn W}: R's
       evs are shot (actor A) -> hit(s) -> R's one bt_action_end, before W's
       end; every A shot/hit carries R; W {origin intent, kind walk, actorId
       C} halts after C8_EXECUTED with reason "reaction" on both machines; the
       client banner reads BANNER_UNDER_FIRE; C's outcome per the seed (health
       C8_C_HEALTH, not out) equal on both; A tu equal on both.
       RED (TASK 0d / F810): (walk_step W)(bt_action_end W) only - no shot,
       no hit, A tu A_TU -> A_TU, halted "blocked", path C8_EXECUTED, banner
       "Move stopped - path blocked".
  C8k  the kneeling walker (B1 RQ4 (a)). A reactions 0 (BOTH); C health
       C_MAX_HEALTH + tu TU_MAX (BOTH); C and A back on the C8 tiles (BOTH);
       the client kneels C (real SDLK_k); A reactions 100 + tu A_TU refilled
       (BOTH); host set_seed SEED_C8K; the client clicks C8_DEST. The walk
       stands C up first (kneel() runs the reaction check for the stand-up).
       GREEN: the stand-up `kneel` ev and every walk_step carry W (hooks owned
       by the base chain read the walk's own id); >= 1 `reaction` context
       nested in W (actorId A), one of them with no `shot` cue - the stand-up
       reaction, aimed at C's old tile and cancelled (F881); every A shot/hit
       carries a `reaction` context nested in W, never W itself; W halts after
       C8K_EXECUTED with reason "reaction" (resolved in the catch-all) on both;
       banner BANNER_UNDER_FIRE; C's outcome per the seed (health
       C8K_C_HEALTH, not out) equal on both; A tu equal on both.
       RED (TASK 0d): (kneel W)(walk_step W)(bt_action_end W), no shot,
       halted "blocked".
  C11  proximity mine under the walker. C health + tu (BOTH), C on
       C11_C_TILE (BOTH, out of A's view); a primed fuse-0
       STR_PROXIMITY_GRENADE G on C11_PROX_TILE beside the path (battle_drop,
       BOTH, equal ids); host set_seed SEED_C11; the client clicks C11_DEST.
       The step adjacent to G (step 2) triggers it.
       GREEN: ONE `prox` context P {actorId C, nestedIn W}: prox_trigger
       {unit C, item G, pos C11_PROX_TILE} -> explosion -> ... -> P's one
       bt_action_end, before W's end; every explosion carries P; W halts after
       C11_EXECUTED with reason "prox" on both; G absent on both; the client
       shows NO halt banner (RQ8 + D139: a proximity-mine halt has no
       message).
       RED (TASK 0d): (walk_step W)(walk_step W)(explosion W)(bt_action_end
       W), no prox_trigger, halted "blocked", banner "Move stopped - path
       blocked".

Common asserts (spec (f) as amended by B1 RQ5; each walk settled with
wait_walk_settled + wait_host_idle): W2-P2's common asserts (hash_now
{full:true} ALL buckets EQUAL; desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; client deltaEvsApplied increased;
deltaUnresolved, deltaUnsupported, deltaRemoveMissing, deltaAddExisting 0 on
both); host contextBeginRefused 0; contextsClosedAtEndTurn is a DIAGNOSTIC
(printed, never asserted, RQ5); every chain ev of the scenario carries the id
of a context the scenario closed; every context has exactly one
bt_action_end, its last ev, recorded in closedContexts (endSeq = that ev's
seq); a nested context's end precedes its base's end; no `sync` inside a
context; contextsOpened grew by exactly the number of contexts closed; the
client log holds the host's seqs/kinds/actionIds. armingDeferrals is printed,
never asserted.

Probes (all exist at S-A 5e1326c19): event_state contextsOpened,
closedContexts {actionId, origin, kind, actorId, nestedIn, endSeq, hasFinal},
contextsClosedAtEndTurn, contextBeginRefused, lastWalk {actionId, executed,
restate {path, halted, reason}} on both machines; event_log (seq, kind,
actionId); the host's `[coop-cue] <kind> seq <n> actionId <id>: <payload>`
log line (coopEmitCue) for cue payloads; battle_state units and the client's
coopWaitText banner; battle_items.

Bring-up (deterministic, never searched here; ledger `## W2-P3 TASK 0a` and
`## W2-P3 TASK 0c`, scratch w2p3/T0a and w2p3/T0c constants.md): set_seed
SEED_ROSTER on the HOST right before its open_new_battle; the DEFAULT NEW
BATTLE map with set_seed SEED_MAP right before newbattle_ok, seat_count=2,
MAP_FP asserted on both; session.pin_ai_neutral (pins A); RQ15: every live
player unit's reactions 0 on BOTH. Every lever pair applies to the CLIENT
first, then the HOST (F607), responses asserted equal. The seeds were found
with the host-selection stand-in (host `battle_action select` of C, F880);
this test does NOT use it - the product fix (D145) is what GREEN tests.

RED-THEN-GREEN (spec (d) row S-B). Commit S-B.1 (this file; product
unchanged) is run ONCE and every scenario must FAIL with the RED above; commit
S-B.2 (nested reaction/prox contexts + the D145 fix) is run ONCE and every
scenario must PASS. Each scenario prints ONE "EVIDENCE <id>:" line with both
machines' fields BEFORE its green conditions are checked; main() runs every
scenario even after an earlier one failed and prints "PASS <id>" /
"FAIL <id>: <message>". Every wait is bounded; a wait that times out is
recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all three scenarios pass, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_reaction_prox.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_seat_pacing import tab_select, real_click_walk
from test_w2_delta_core import probes, diff_buckets, desync_record, short, both, tele_both, common_fails, finish, \
    delta_view
from test_w2_delta_items import items_by_id
from test_w2_host_combat import evs_since, ev_tuples, cue_probes, cue_delta
from test_w2_ai_origins import (host_payloads, ctx_probes, new_closed, opened_delta, ctx_of, ctx_view, sv, by_seq,
                                CHAIN_KINDS, end_turn_cycle, bring_up_lobby_roster_pinned)

# ----- bring-up (W2-P3 TASK 0a, ledger `## W2-P3 TASK 0a`) -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
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

# ----- C8 (ledger `## W2-P3 TASK 0c`, T0c constants.md "C8") -----
C8_A_TILE, C8_A_DIR = (15, 2, 0), 4    # A faces south, C on its axis
C8_C_TILE, C8_C_DIR = (15, 7, 0), 0    # C faces A
C8_DEST = (18, 7, 0)                   # planned (16,7) (17,7) (18,7): every tile in A's view sector
SEED_C8 = 3                            # host set_seed right before the client's click
C8_EXECUTED = [(16, 7, 0)]             # halted after step 1 (C8_REACT_STEP 1)
C8_C_HEALTH = 21                       # C8_C_HEALTH_AFTER: two of A's three snaps hit C (40 -> 21), C standing

# ----- C8k (T0c constants.md "C8k") -----
SEED_C8K = 2                           # host set_seed right before the client's click
C8K_EXECUTED = [(16, 7, 0)]            # halted after step 1
C8K_C_HEALTH = 40                      # C8K_C_HEALTH_AFTER: A's three snaps land on terrain

# ----- C11 (ledger `## W2-P3 TASK 0a`, T0a constants.md "C11") -----
C11_C_TILE, C11_C_DIR = (2, 34, 0), 2  # SW field, > 20 tiles from A (out of A's view)
C11_PROX_TILE = (5, 35, 0)             # battle_drop STR_PROXIMITY_GRENADE {prime, fuse 0}, beside the path
C11_DEST = (6, 34, 0)                  # planned (3,34) (4,34) (5,34) (6,34); step 2 (4,34) is adjacent to G
SEED_C11 = 5                           # host set_seed right before the client's click
C11_EXECUTED = [(3, 34, 0), (4, 34, 0)]

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
    """Spec (f) common asserts on the context side (B1 RQ5), over the host evs
    of one scenario: contextBeginRefused 0 on the host; contextsOpened grew by
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
    """A fired (D145): >= 1 `shot` cue with actor A and >= 1 `hit`; every
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
    """C's outcome per the seed (B3): health `health`, not out, on both."""
    fails = []
    for name, u in (("host", rec["uh"].get(C_ID) or {}), ("client", rec["uc"].get(C_ID) or {})):
        if u.get("health") != health or u.get("isOut"):
            fails.append(f"{what}: C on the {name} {uview(u)} (want health {health}, not out - the seed's outcome)")
    return fails


# ===================== scenarios =====================


def c8_reaction(host, client, ctx):
    notes = []
    # prep: A and C face each other; one END TURN cycle (no seed) so the player-side FOV
    # recalculation puts A in C's spottedThisTurn (a teleport skips calculateFOV).
    tele_both(host, client, A_ID, C8_A_TILE, C8_A_DIR)
    tele_both(host, client, C_ID, C8_C_TILE, C8_C_DIR)
    turn0 = end_turn_cycle(host, client, None, notes)
    hs, cs = battle_state(host), battle_state(client)
    spotted = (units(host).get(C_ID) or {}).get("spottedThisTurn")
    prep_diff = diff_buckets(host, client)
    ctx["prep"] = {"turn": (turn0, hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")),
                   "spotted": spotted, "diff": prep_diff}
    # C8 staging
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "reactions",
                        "value": A_REACTIONS}, ("tu",))
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": A_TU,
                        "refill": True}, ("tu",))
    staged_diff = diff_buckets(host, client)
    rec = client_walk(host, client, SEED_C8, C8_DEST, notes)
    w = rec["W"]
    print(f"EVIDENCE C8: prep {ctx['prep']}; A {C8_A_TILE}/{C8_A_DIR} C {C8_C_TILE}/{C8_C_DIR} dest {C8_DEST} "
          f"stagedDiff={staged_diff}; {walk_evidence(rec, 'C8')}", flush=True)
    fails = list(notes)
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER, turn0 + 1,
                                                                           FACTION_PLAYER):
        fails.append(f"prep cycle: not on player turn {turn0 + 1} on both: {ctx['prep']['turn']}")
    if A_ID not in (spotted or []):
        fails.append(f"prep cycle: host C spottedThisTurn={spotted} (want A {A_ID} in it: no new-spot halt)")
    if prep_diff or staged_diff:
        fails.append(f"buckets differ after the staging: prep={prep_diff} staged={staged_diff} (want none)")
    fails += walk_context_fails(rec, C8_EXECUTED, "C8")
    rf, rctx = reaction_fails(rec, "C8")
    fails += rf
    nested = nested_in(rec, w)
    if len(nested) != 1 or len(rctx) != 1:
        fails.append(f"C8: contexts nested in W {w} = {[ctx_view(c) for c in nested]} (want exactly one: R {{origin "
                     f"reaction, actorId {A_ID}, nestedIn {w}}})")
    if rctx:
        r = rctx[0]
        rk = [e["kind"] for e in evs_of(rec, r.get("actionId"))]
        if (not rk or rk[0] != "shot" or rk[-1] != "bt_action_end" or "hit" not in rk
                or any(k not in ("shot", "hit") for k in rk[:-1])):
            fails.append(f"C8: R {r.get('actionId')} evs {sv(evs_of(rec, r.get('actionId')))} (want shot (actor A) -> "
                         f"hit(s) -> bt_action_end)")
    fails += halt_fails(rec, "reaction", C8_EXECUTED, "C8")
    if rec["banner"] != BANNER_UNDER_FIRE:
        fails.append(f"C8: client banner {rec['banner']!r} (want {BANNER_UNDER_FIRE!r})")
    fails += outcome_fails(rec, C8_C_HEALTH, "C8")
    fails += equal_fails(rec, "C8")
    fails += context_fails(rec, "C8")
    fails += common_fails(host, client, rec["before"], {}, "C8")
    finish(fails)


def c8k_kneeled(host, client, ctx):
    notes = []
    # re-stage: A quiet, C healed, both back on the C8 tiles, C kneels (real UI)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "reactions",
                        "value": 0}, ("tu",))
    both(host, client, {"cmd": "battle_set_unit_state", "unit": C_ID, "health": C_MAX_HEALTH, "tu": TU_MAX},
         ("health", "stun", "status", "tu"))
    tele_both(host, client, C_ID, C8_C_TILE, C8_C_DIR)
    tele_both(host, client, A_ID, C8_A_TILE, C8_A_DIR)
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
    rec = client_walk(host, client, SEED_C8K, C8_DEST, notes)
    w = rec["W"]
    kneels = [e for e in rec["hev"] if e["kind"] == "kneel"]
    steps = [e for e in rec["hev"] if e["kind"] == "walk_step"]
    print(f"EVIDENCE C8k: kneel staging evs={kneel_evs} kneeled host/client={kneeled} stagedDiff={staged_diff}; "
          f"{walk_evidence(rec, 'C8k')}", flush=True)
    fails = list(notes)
    if kneeled != (True, True):
        fails.append(f"C8k staging: C kneeled host/client={kneeled} before the walk (want True on both)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += walk_context_fails(rec, C8K_EXECUTED, "C8k")
    if len(kneels) != 1 or kneels[0]["actionId"] != w or not steps or kneels[0]["seq"] > steps[0]["seq"]:
        fails.append(f"C8k: the stand-up kneel evs {sv(kneels)} (want exactly one, carrying W {w}, before the first "
                     f"walk_step {sv(steps[:1])})")
    rf, rctx = reaction_fails(rec, "C8k")
    fails += rf
    nested = nested_in(rec, w)
    other = [c for c in nested if c.get("origin") != "reaction"]
    if other:
        fails.append(f"C8k: non-reaction contexts nested in W {w}: {[ctx_view(c) for c in other]} (want none)")
    shot_ids = {e["actionId"] for e in rec["hev"] if e["kind"] == "shot"}
    quiet = [c for c in rctx if c.get("actionId") not in shot_ids]
    if not quiet:
        fails.append(f"C8k: no `reaction` context nested in W {w} without a `shot` cue (want the stand-up reaction, "
                     f"cancelled, F881; reaction contexts {[ctx_view(c) for c in rctx]})")
    fails += halt_fails(rec, "reaction", C8K_EXECUTED, "C8k")
    if rec["banner"] != BANNER_UNDER_FIRE:
        fails.append(f"C8k: client banner {rec['banner']!r} (want {BANNER_UNDER_FIRE!r})")
    fails += outcome_fails(rec, C8K_C_HEALTH, "C8k")
    fails += equal_fails(rec, "C8k")
    fails += context_fails(rec, "C8k")
    fails += common_fails(host, client, rec["before"], {}, "C8k")
    finish(fails)


def c11_prox(host, client, ctx):
    notes = []
    both(host, client, {"cmd": "battle_set_unit_state", "unit": C_ID, "health": C_MAX_HEALTH, "tu": TU_MAX},
         ("health", "stun", "status", "tu"))
    tele_both(host, client, C_ID, C11_C_TILE, C11_C_DIR)
    g = both(host, client, {"cmd": "battle_drop", "x": C11_PROX_TILE[0], "y": C11_PROX_TILE[1],
                            "z": C11_PROX_TILE[2], "item": "STR_PROXIMITY_GRENADE", "prime": True, "fuse": 0},
             ("ids",))["ids"]
    gid = g[0] if g else None
    staged_diff = diff_buckets(host, client)
    rec = client_walk(host, client, SEED_C11, C11_DEST, notes)
    w = rec["W"]
    ih, ic = items_by_id(host), items_by_id(client)
    g_gone = {"host": gid not in ih, "client": gid not in ic}
    nested = nested_in(rec, w)
    pctx = [c for c in nested if c.get("origin") == "prox"]
    p = pctx[0] if pctx else None
    pevs = evs_of(rec, p.get("actionId")) if p else []
    trig = [e for e in rec["hev"] if e["kind"] == "prox_trigger"]
    expl = [e for e in rec["hev"] if e["kind"] == "explosion"]
    print(f"EVIDENCE C11: grenade G={g} on {C11_PROX_TILE} C {C11_C_TILE}/{C11_C_DIR} dest {C11_DEST} stagedDiff="
          f"{staged_diff}; prox context={ctx_view(p)} its evs={sv(pevs)}; prox_trigger evs="
          f"{[(e['seq'], e['actionId'], payload(rec, e)) for e in trig]}; G gone={g_gone}; "
          f"{walk_evidence(rec, 'C11')}", flush=True)
    fails = list(notes)
    if len(g) != 1:
        fails.append(f"battle_drop returned ids {g} (want exactly one grenade)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += walk_context_fails(rec, C11_EXECUTED, "C11")
    if len(nested) != 1 or not p or (p.get("origin"), p.get("actorId")) != ("prox", C_ID):
        fails.append(f"C11: contexts nested in W {w} = {[ctx_view(c) for c in nested]} (want exactly one: P {{origin "
                     f"prox, actorId {C_ID}, nestedIn {w}}})")
    if len(trig) != 1:
        fails.append(f"C11: prox_trigger evs {sv(trig)} (want exactly one)")
    if p:
        pk = [e["kind"] for e in pevs]
        if len(pk) < 3 or pk[0] != "prox_trigger" or pk[1] != "explosion" or pk[-1] != "bt_action_end":
            fails.append(f"C11: P {p.get('actionId')} evs {sv(pevs)} (want prox_trigger -> explosion -> ... -> "
                         f"bt_action_end)")
        if pevs and pevs[0]["kind"] == "prox_trigger":
            tp = payload(rec, pevs[0])
            if (tp.get("unit"), tp.get("item"), xyz(tp.get("pos"))) != (C_ID, gid, C11_PROX_TILE):
                fails.append(f"C11: prox_trigger payload {tp or None} (want unit {C_ID}, item {gid}, pos "
                             f"{C11_PROX_TILE})")
    if not expl:
        fails.append(f"C11: no `explosion` ev in the scenario (host evs {sv(rec['hev'])})")
    for e in expl:
        if not p or e["actionId"] != p.get("actionId"):
            fails.append(f"C11: explosion seq {e['seq']} carries actionId {e['actionId']} (W is {w}; want the `prox` "
                         f"context {p and p.get('actionId')})")
    fails += halt_fails(rec, "prox", C11_EXECUTED, "C11")
    if rec["banner"] in HALT_BANNERS:
        fails.append(f"C11: client banner {rec['banner']!r} (want no halt banner - a proximity-mine halt shows no "
                     f"message, RQ8 / D139)")
    if not g_gone["host"] or not g_gone["client"]:
        fails.append(f"C11: grenade {gid} present after the walk host={not g_gone['host']} client="
                     f"{not g_gone['client']} (want absent on both)")
    fails += equal_fails(rec, "C11")
    fails += context_fails(rec, "C11")
    fails += common_fails(host, client, rec["before"], {}, "C11")
    finish(fails)


SCENARIOS = (("C8", c8_reaction), ("C8k", c8k_kneeled), ("C11", c11_prox))


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
    pinned = pin_ai_neutral(host, client, tag="w2p3-sb")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A {A_ID} battle_state type host/client={types} (want {A_TYPE})"
    # RQ15: every live player unit's reactions 0 on BOTH machines (A's reactions are the scenarios' own staging)
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
    print(f"[w2p3-sb] boot ok: SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={SEATED} "
          f"pinned={pinned} A type={types[0]} reactions 0 (both) for {rz} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49854, make_user_dir("w2p3_reaction_prox_host"))
    client = GameClient("client", 49855, make_user_dir("w2p3_reaction_prox_client"))
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
                print(f"[w2p3-sb] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_reaction_prox: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
