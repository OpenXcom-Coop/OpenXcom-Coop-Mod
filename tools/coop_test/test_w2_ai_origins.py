"""W2-P3 S-A - test_w2_ai_origins.py: an alien's attack and the grenades that
go off when a side ends each run as a named action - with its own action
context, its own `bt_action_end`, and (for a ranged or thrown AI attack) the
alien's turn toward its target sent as a normal `turn` event first (spec
rewrite/prompts/w2p3_nonplayer_origins.md section (f) "test_w2_ai_origins.py
(S-A)", sections (b)1-6 and (b)13 for the `ai` and `endturn` origins,
amendments B1 (RQ5, RQ6, RQ7, RQ15) and B2 (C6, C7); owner ruling D128 = (b)).

Before W2-P3 these chains already reach the second player through W2-P2's
delta and `sync` evs, so nothing freezes - but they are anonymous: their cues
carry actionId 0, nothing marks where they start and end, and the AI's turn
toward its target is visible only by sampling the unit.

Three scenarios, ONE boot, in this order (the W2-P3 TASK 0a one-boot order):

  C3e  end-turn detonation. A primed fuse-0 STR_GRENADE and two
       STR_RIFLE_CLIPs lie on C3E_TILE (battle_drop, BOTH). Both machines press
       END TURN (host set_seed SEED_C6 right before its press - the same cycle
       carries C6); the grenade explodes at the end of the player side, before
       the first side_transition. GREEN: the explosion carries an `endturn`
       context's id (host closedContexts {origin endturn, kind endturn,
       actorId -1, nestedIn 0, hasFinal false}); every combat cue before that
       side_transition carries it; its one bt_action_end (no `final`) has a
       lower seq than the side_transition, whose actionId is 0; the grenade
       and >= 1 clip absent on both. RED (W2-P3 base, TASK 0d): (4 explosion 0)
       (5 side_transition 0), no bt_action_end between them, no context.
  C6   the alien shoots at C (same cycle). A (the only alien) on C6_A_TILE
       facing C6_A_DIR, one octant off the direction to C on C6_C_TILE, A tu
       base A_TU (BOTH). SEED_C6's alien side runs three AI actions (snap,
       snap, a one-step walk; B2.2 / F812). GREEN: three `ai` contexts
       {kind shoot, shoot, walk; actorId A; hasFinal true}; the FIRST one's evs
       in both logs are turn (unit A, fromDir C6_A_DIR, toDir C6_TURN_TO) ->
       shot (actor A) -> >= 1 hit -> bt_action_end, with no `sync` between its
       first ev and its end; it is the only context with a `turn` ev; every
       AI action on that side opens and closes its own context; A tu/direction
       and C health equal on both. RED (TASK 0d): (8 shot 0)(9 hit 0)(10 sync
       0)(11 shot 0)(12 hit 0)(13 sync 0)(14 walk_step 1)(15 bt_action_end 1),
       no `ai` context, no `turn` ev (A turned 3 -> 4, visible only by
       sampling).
  C7   the alien throws a grenade (battle turn 3; the AI throws grenades only
       from turn 3, turnAIUseGrenade, F807). Cycle 2 is a plain cycle with A
       re-pinned (tu 0 + refill, BOTH). Then A is stripped (battle_strip_unit,
       BOTH, deleted ids compared as SETS - F882) and given a STR_GRENADE on
       its belt (battle_give, BOTH), A/C/C2 staged (BOTH), A tu base A_TU
       (BOTH); host set_seed SEED_C7 right before its END TURN press. GREEN
       (B2.1 / F808): the first `ai` context on the alien side is {kind throw,
       actorId A, hasFinal true} and its evs are exactly turn (unit A,
       fromDir C7_A_DIR, toDir C7_TURN_TO) -> shot (action throw, `arc`
       present, actor A, the grenade) -> bt_action_end; the grenade explodes
       at the END of the alien side inside an `endturn` context (explosion
       seq after the throw's end; the context's bt_action_end, no `final`,
       before the side_transition, whose actionId is 0); every AI action on
       that side runs in its own context; the grenade absent on both. RED
       (TASK 0d): (30 shot 0, throw)(31 sync 0)(32 walk_step 2)(33
       bt_action_end 2)(34 explosion 0)(35 side_transition 0), no `ai` or
       `endturn` context.

Common asserts (spec (f) as amended by B1 RQ5; each scenario's cycle settled
with wait_host_idle): W2-P2's common asserts (hash_now {full:true} ALL buckets
EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing, deltaAddExisting 0 on both); host contextBeginRefused 0;
contextsClosedAtEndTurn is a DIAGNOSTIC (printed, never asserted, RQ5); every
side_transition carries actionId 0 and no action context spans one (each
context's bt_action_end precedes the next side_transition); every context the
scenario opens has exactly one bt_action_end, its last ev, and is recorded in
closedContexts (endSeq = that ev's seq); contextsOpened grew by exactly the
number of contexts closed; the client log holds the host's seqs/kinds/
actionIds. armingDeferrals is printed (F890), never asserted.

Probes (commit S-A.1, amendment B1 RQ7): event_state contextsOpened,
closedContexts (with hasFinal), contextsClosedAtEndTurn, contextBeginRefused
(host; commit S-A.2 writes them); battle_state units[].type; the host's
`[coop-turn] turn seq <n> actionId <id>: <payload>` log line (event_log
carries no payload) next to coopEmitCue's `[coop-cue]` line, both read from
the host's own openxcom.log.

Bring-up (deterministic, never searched here; ledger `## W2-P3 TASK 0a`,
scratch w2p3/T0a/constants.md): set_seed SEED_ROSTER on the HOST right before
its open_new_battle (the roster repeats, F501); the DEFAULT NEW BATTLE map (no
mission pin) with set_seed SEED_MAP right before newbattle_ok, seat_count=2,
the baked MAP_FP asserted on both; session.pin_ai_neutral (pins A); RQ15:
every live player unit's reactions 0 on BOTH. Every lever pair applies to the
CLIENT first, then the HOST (F607), with the responses asserted equal; every
item a lever creates is created on both machines with equal ids. set_seed on
the HOST immediately before the press that starts the chain.

RED-THEN-GREEN (spec (d) row S-A). Commit S-A.1 (this file + the probe
storage; product behaviour unchanged) is run ONCE and every scenario must
FAIL with the RED above; commit S-A.2 (the `ai`/`endturn` contexts) is run
ONCE and every scenario must PASS. Each scenario prints ONE "EVIDENCE <id>:"
line with both machines' fields BEFORE its green conditions are checked;
main() runs every scenario even after an earlier one failed and prints
"PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that
times out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all three scenarios pass, 2
otherwise (a bring-up failure is also 2). WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_w2_ai_origins.py
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
from test_rw_turn_baton import drive_full_cycle
from test_w2_delta_core import (probes, diff_buckets, desync_record, short, both, tele_both,
                                settle_on_battlescape, common_fails, finish, delta_view)
from test_w2_delta_items import items_by_id, unit_view
from test_w2_host_combat import evs_since, ev_tuples, cue_probes, cue_delta

# ----- bring-up (W2-P3 TASK 0a, ledger `## W2-P3 TASK 0a`) -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok; DEFAULT NEW BATTLE (no mission)
MAP_FP = -4.48310638993e+18      # host AND client battle_state.mapFingerprint (STR_UFO_GROUND_ASSAULT, small scout)
SEATED = [8, 9]                  # the client seat's soldiers
A_ID = 1000000                   # the only alien: Sectoid Soldier, plasma pistol 56 (ammo 57), clip 58, mind probe 59
A_TYPE = "STR_SECTOID_SOLDIER"   # battle_state units[].type (B1 RQ7)
C_ID, C2_ID = 8, 9               # client seat: C (rifle, belt grenade) and C2
A_TU = 54                        # set_stat tu (no refill): recovered at A's side start
PORT = "48628"
FACTION_PLAYER = 0

# ----- C3e + C6: ONE cycle, battle turn 1 -----
C3E_TILE = (7, 3, 0)             # battle_drop STR_GRENADE {prime, fuse 0} + STR_RIFLE_CLIP x2 (T0a ids 60, 61, 62)
C6_A_TILE, C6_A_DIR = (15, 3, 0), 3
C6_C_TILE, C6_C_DIR = (15, 8, 0), 4    # C faces away from A
C6_TURN_TO = 4                   # the direction A (15,3) -> C (15,8); A turns 3 -> 4 before its first snap
SEED_C6 = 15                     # host set_seed right before its END TURN press (after the client's press)
C6_AI_KINDS = ["shoot", "shoot", "walk"]   # snap + hit, snap + hit, a one-step AI walk (B2.2 / F812)

# ----- C7: cycle 2 (turn 2, plain) + cycle 3 (turn 3) -----
C7_A_TILE, C7_A_DIR = (15, 2, 0), 3
C7_C_TILE, C7_C_DIR = (15, 9, 0), 4
C7_C2_TILE, C7_C2_DIR = (16, 9, 0), 4  # C and C2 adjacent: 2 enemies inside the grenade's radius
C7_TURN_TO = 4                   # the direction A (15,2) -> C (15,9); A turns 3 -> 4 before the throw (T0a)
SEED_C7 = 3                      # host set_seed right before its END TURN press

# The ev kinds a named chain emits (the combat cues + the wave-1 action kinds);
# `sync`, `reveal`, `side_*`, `door` and `spot` are not chain evs here.
CHAIN_KINDS = ("turn", "walk_step", "kneel", "shot", "hit", "explosion", "melee", "psi", "death", "corpse",
               "prime", "fall", "revive", "spawn", "panic", "prox_trigger", "medikit", "scanner")
COMBAT_CUES = ("shot", "hit", "explosion", "melee", "psi", "death", "corpse")
# The host's own log lines (connectionTCP.cpp): coopEmitCue's `[coop-cue]` and
# coopOnUnitTurnFinished's `[coop-turn] turn` (commit S-A.1, B1 RQ7).
PAYLOAD_RE = re.compile(r"\[coop-(?:cue|turn)\] (\S+) seq (\d+) actionId (\d+): (\{.*\})\s*$", re.M)


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def ctx_probes(gc):
    """The S-A.1 context probes + armingDeferrals (host-written; a client
    reports its own empty values)."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {"contextsOpened": es.get("contextsOpened") or {}, "closedContexts": es.get("closedContexts") or [],
            "contextsClosedAtEndTurn": es.get("contextsClosedAtEndTurn"),
            "contextBeginRefused": es.get("contextBeginRefused"), "armingDeferrals": es.get("armingDeferrals")}


def host_payloads(host, seqs, timeout=5.0):
    """{seq: {kind, actionId, payload}} from the HOST's own openxcom.log
    `[coop-cue]` / `[coop-turn]` lines for every seq in `seqs`, read with a
    bounded wait for the log write to land."""
    path = os.path.join(host.user_dir, "openxcom.log")
    want = set(seqs)
    deadline = time.time() + timeout
    found = {}
    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        found = {}
        for m in PAYLOAD_RE.finditer(text):
            s = int(m.group(2))
            if s in want:
                try:
                    payload = json.loads(m.group(4))
                except ValueError as e:
                    payload = {"unparsed": m.group(4)[:300], "error": str(e)}
                found[s] = {"kind": m.group(1), "actionId": int(m.group(3)), "payload": payload}
        if want <= set(found) or time.time() >= deadline:
            return found


def voxel_tile(v):
    if not isinstance(v, dict):
        return None
    return (v.get("x", 0) // 16, v.get("y", 0) // 16, v.get("z", 0) // 24)


def sv(evs):
    """(seq, kind, actionId) view."""
    return [(e["seq"], e["kind"], e["actionId"]) for e in evs]


def by_seq(evs):
    return {e["seq"]: e for e in evs}


def st_seqs(evs):
    return [e["seq"] for e in evs if e["kind"] == "side_transition"]


def new_closed(cb, ca):
    """closedContexts entries added since `cb` (action ids are never reused)."""
    before = {c.get("actionId") for c in cb["closedContexts"]}
    return [c for c in ca["closedContexts"] if c.get("actionId") not in before]


def opened_delta(cb, ca):
    a, b = cb["contextsOpened"], ca["contextsOpened"]
    return {k: (b.get(k) or 0) - (a.get(k) or 0) for k in sorted(set(a) | set(b)) if (b.get(k) or 0) != (a.get(k) or 0)}


def ctx_of(closed, aid):
    for c in closed:
        if c.get("actionId") == aid:
            return c
    return None


def ctx_view(c):
    if not c:
        return None
    return {k: c.get(k) for k in ("actionId", "origin", "kind", "actorId", "nestedIn", "endSeq", "hasFinal")}


# ===================== driving =====================


def end_turn_cycle(host, client, seed, notes, timeout=90):
    """Both machines press END TURN (the client first; the host presses once
    it paints END TURN 1/2, with set_seed `seed` on the HOST right before its
    press when `seed` is not None), then the full side cycle back to the
    player side (NextTurnState closed via close_nextturn on both), both
    machines settled on BattlescapeState, the host idle and the client caught
    up. Every wait is bounded; a timeout is recorded in `notes`."""
    turn0 = battle_state(host).get("turn")
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None, timeout=20)
        if seed is not None:
            host.ok({"cmd": "set_seed", "seed": seed})
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        drive_full_cycle(host, client, turn0, timeout=timeout)
        settle_on_battlescape(host)
        settle_on_battlescape(client)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"end-turn cycle: {short(e)}")
    return turn0


def run_cycle(host, client, seed, notes):
    """One END TURN cycle with the probes read before and after. Returns the
    cycle record (host/client evs since the host's last seq before the press)."""
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": ctx_probes(host), "client": ctx_probes(client)}
    kb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    turn0 = end_turn_cycle(host, client, seed, notes)
    hs, cs = battle_state(host), battle_state(client)
    ph, pc = probes(host), probes(client)
    ca = {"host": ctx_probes(host), "client": ctx_probes(client)}
    ka = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    return {"seed": seed, "notes": notes, "before": before, "cb": cb, "ca": ca, "kb": kb, "ka": ka,
            "seq0": seq0, "turn0": turn0, "hs": hs, "cs": cs, "ph": ph, "pc": pc, "hev": hev, "cev": cev,
            "closed": new_closed(cb["host"], ca["host"]), "opened": opened_delta(cb["host"], ca["host"]),
            "diff": diff_buckets(host, client), "desync": desync_record(client, pc["desyncSeen"])}


# ===================== context checks =====================


def turn_fails(rec, what):
    """Both machines back on player turn turn0 + 1."""
    hs, cs, t = rec["hs"], rec["cs"], rec["turn0"]
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (t + 1, FACTION_PLAYER, t + 1,
                                                                           FACTION_PLAYER):
        return [f"{what}: not on player turn {t + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                f"client=({cs.get('turn')},{cs.get('side')})"]
    return []


def segment_context_fails(hev, cev, closed, what):
    """Spec (f) common asserts as amended by B1 RQ5, over one segment of host
    evs: every side_transition carries actionId 0 (on both machines); every
    non-zero actionId has exactly one bt_action_end, as its last ev, with no
    side_transition between its first ev and that end, and is recorded in
    closedContexts with endSeq = that ev's seq; the client log holds the
    host's seq/kind/actionId for every ev of every context."""
    fails = []
    cmap = by_seq(cev)
    sts = st_seqs(hev)
    for e in hev:
        if e["kind"] != "side_transition":
            continue
        ce = cmap.get(e["seq"])
        if e["actionId"] != 0 or not ce or ce["kind"] != "side_transition" or ce["actionId"] != 0:
            fails.append(f"{what}: side_transition seq {e['seq']} host actionId {e['actionId']} client entry "
                         f"{ce and (ce['seq'], ce['kind'], ce['actionId'])} (want actionId 0 on both)")
    for aid in sorted({e["actionId"] for e in hev if e["actionId"]}):
        evs = [e for e in hev if e["actionId"] == aid]
        kinds = [e["kind"] for e in evs]
        if kinds.count("bt_action_end") != 1 or kinds[-1] != "bt_action_end":
            fails.append(f"{what}: context {aid} evs {sv(evs)} (want exactly one bt_action_end, its last ev)")
        lo, hi = evs[0]["seq"], evs[-1]["seq"]
        span = [s for s in sts if lo < s < hi]
        if span:
            fails.append(f"{what}: context {aid} ({lo}..{hi}) spans side_transition seq(s) {span} (want its "
                         f"bt_action_end before the next side_transition)")
        c = ctx_of(closed, aid)
        if not c:
            fails.append(f"{what}: context {aid} (evs {sv(evs)}) is not in the host's closedContexts "
                         f"(new entries {[ctx_view(x) for x in closed]})")
        elif c.get("endSeq") != hi or kinds[-1] != "bt_action_end":
            fails.append(f"{what}: closedContexts {ctx_view(c)} endSeq != its bt_action_end seq {hi}")
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"]) and (cmap[e["seq"]]["kind"], cmap[e["seq"]]["actionId"]))
               for e in evs if not cmap.get(e["seq"]) or cmap[e["seq"]]["kind"] != e["kind"]
               or cmap[e["seq"]]["actionId"] != aid]
        if bad:
            fails.append(f"{what}: client event_log does not hold the host's evs of context {aid}: "
                         f"(seq, host kind, client (kind, actionId))={bad}")
    return fails


def cycle_context_fails(rec, what):
    """Per cycle: contextBeginRefused 0 on the host; contextsOpened grew by
    exactly the number of contexts closed (every context the cycle opened was
    closed and recorded); every recorded close's endSeq is a bt_action_end of
    that actionId in the host log."""
    fails = []
    ca = rec["ca"]["host"]
    if ca["contextBeginRefused"] != 0:
        fails.append(f"{what}: host contextBeginRefused={ca['contextBeginRefused']} (want 0)")
    n_open = sum(rec["opened"].values())
    if n_open != len(rec["closed"]):
        fails.append(f"{what}: host contextsOpened +{n_open} {rec['opened']} but closedContexts +"
                     f"{len(rec['closed'])} (want every context opened in the cycle closed and recorded)")
    for c in rec["closed"]:
        ends = [e["seq"] for e in rec["hev"] if e["actionId"] == c.get("actionId") and e["kind"] == "bt_action_end"]
        if ends != [c.get("endSeq")]:
            fails.append(f"{what}: closedContexts {ctx_view(c)} - its bt_action_end seq(s) in the host log = "
                         f"{ends} (want exactly [endSeq])")
    return fails


def ai_actions_fails(side, closed, what):
    """B2.2: every AI action on the side opens and closes its own context -
    every chain ev on the side carries the id of a context in closedContexts
    whose origin is `ai` (or `endturn` for an explosion) - and no `sync` falls
    between a context's first ev and its end."""
    fails = []
    ok_origin = {"ai"}
    for e in side:
        if e["kind"] not in CHAIN_KINDS:
            continue
        c = ctx_of(closed, e["actionId"]) if e["actionId"] else None
        allowed = ok_origin | ({"endturn"} if e["kind"] in ("explosion", "hit", "death", "corpse") else set())
        if not c or c.get("origin") not in allowed:
            fails.append(f"{what}: {e['kind']} seq {e['seq']} carries actionId {e['actionId']} "
                         f"(context {ctx_view(c)}; want an `ai` context's id)")
    syncs = [e["seq"] for e in side if e["kind"] == "sync"]
    for aid in sorted({e["actionId"] for e in side if e["actionId"]}):
        evs = [e for e in side if e["actionId"] == aid]
        inside = [s for s in syncs if evs[0]["seq"] < s < evs[-1]["seq"]]
        if inside:
            fails.append(f"{what}: `sync` seq(s) {inside} inside context {aid} ({sv(evs)}) (want none)")
    return fails


def context_evidence(rec):
    cb, ca = rec["cb"]["host"], rec["ca"]["host"]
    return {"closedContexts(new, host)": [ctx_view(c) for c in rec["closed"]],
            "contextsOpened delta(host)": rec["opened"],
            "contextsClosedAtEndTurn(host, diagnostic)": f"{cb['contextsClosedAtEndTurn']}->"
                                                         f"{ca['contextsClosedAtEndTurn']}",
            "contextBeginRefused(host)": ca["contextBeginRefused"],
            "armingDeferrals(host)": f"{cb['armingDeferrals']}->{ca['armingDeferrals']}",
            "client probes": {"closedContexts": len(rec["ca"]["client"]["closedContexts"]),
                              "contextsOpened": rec["ca"]["client"]["contextsOpened"]}}


def cycle_evidence(rec):
    ph, pc = rec["ph"], rec["pc"]
    return (f"seed={rec['seed']} turn {rec['turn0']} -> host=({rec['hs'].get('turn')},{rec['hs'].get('side')}) "
            f"client=({rec['cs'].get('turn')},{rec['cs'].get('side')}); cueCounts delta host="
            f"{cue_delta(rec['kb']['host']['cueCounts'], rec['ka']['host']['cueCounts'])} client="
            f"{cue_delta(rec['kb']['client']['cueCounts'], rec['ka']['client']['cueCounts'])}; client desyncSeen="
            f"{pc['desyncSeen']} desync={rec['desync']} host desyncSeen={ph['desyncSeen']}; diffAfterCycle="
            f"{rec['diff']}; host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; host "
            f"{delta_view(rec['before']['host'])}->{delta_view(ph)}; client {delta_view(rec['before']['client'])}"
            f"->{delta_view(pc)}; notes={rec['notes']}")


# ===================== scenarios =====================


def c3e_endturn(host, client, ctx):
    """C3e staging + C6 staging, then the ONE cycle both scenarios read."""
    notes = []
    g = both(host, client, {"cmd": "battle_drop", "x": C3E_TILE[0], "y": C3E_TILE[1], "z": C3E_TILE[2],
                            "item": "STR_GRENADE", "prime": True, "fuse": 0}, ("ids",))["ids"]
    clips = both(host, client, {"cmd": "battle_drop", "x": C3E_TILE[0], "y": C3E_TILE[1], "z": C3E_TILE[2],
                                "item": "STR_RIFLE_CLIP", "count": 2}, ("ids",))["ids"]
    tele_both(host, client, C_ID, C6_C_TILE, C6_C_DIR)
    tele_both(host, client, A_ID, C6_A_TILE, C6_A_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                        "value": A_TU}, ("tu",))
    staged_diff = diff_buckets(host, client)
    uh0 = units(host)
    ctx["c6_staged"] = {"A": (uh0.get(A_ID) or {}).get("direction"), "C": unit_view(uh0.get(C_ID)),
                        "stagedDiff": staged_diff}
    rec = run_cycle(host, client, SEED_C6, notes)
    ctx["cycle1"] = rec
    hev, cev = rec["hev"], rec["cev"]
    sts = st_seqs(hev)
    st1 = sts[0] if sts else None
    seg = [e for e in hev if st1 is None or e["seq"] <= st1]
    cseg = [e for e in cev if st1 is None or e["seq"] <= st1]
    expl = [e for e in seg if e["kind"] == "explosion"]
    pl = host_payloads(host, [e["seq"] for e in expl])
    mine = [e for e in expl if voxel_tile(((pl.get(e["seq"]) or {}).get("payload") or {}).get("centreVoxel"))
            == C3E_TILE]
    x = mine[0] if mine else None
    aid = x["actionId"] if x else None
    c = ctx_of(rec["closed"], aid) if aid else None
    xevs = [e for e in seg if aid and e["actionId"] == aid]
    ends = [e for e in xevs if e["kind"] == "bt_action_end"]
    ih, ic = items_by_id(host), items_by_id(client)
    gone = {i: {"host": i not in ih, "client": i not in ic} for i in g + clips}
    print(f"EVIDENCE C3e: staged grenade={g} clips={clips} on {C3E_TILE} stagedDiff={staged_diff}; "
          f"{cycle_evidence(rec)}; host evs since seq {rec['seq0']}={ev_tuples(hev)} client evs="
          f"{ev_tuples(cev)} (seq, kind, actionId, h); segment to the first side_transition (seq {st1}) host="
          f"{sv(seg)} client={sv(cseg)}; explosions (seq, actionId, payload)="
          f"{[(e['seq'], e['actionId'], (pl.get(e['seq']) or {}).get('payload')) for e in expl]}; C3e explosion="
          f"{x and (x['seq'], x['actionId'])} its context={ctx_view(c)} its evs={sv(xevs)}; "
          f"{context_evidence(rec)}; items gone={gone}; notes={notes}", flush=True)
    fails = list(notes)
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += turn_fails(rec, "cycle 1")
    if st1 is None:
        fails.append(f"no side_transition in the cycle's host log (host evs {sv(hev)})")
    if not x:
        fails.append(f"no host `explosion` ev centred on {C3E_TILE} before the first side_transition "
                     f"(explosions {[(e['seq'], e['actionId']) for e in expl]})")
    else:
        if aid == 0:
            fails.append(f"the C3e explosion (seq {x['seq']}) carries actionId 0 (want an `endturn` context's id)")
        elif not c or (c.get("origin"), c.get("kind"), c.get("actorId"), c.get("nestedIn"), c.get("hasFinal")) != (
                "endturn", "endturn", -1, 0, False):
            fails.append(f"the C3e explosion's context {aid} = {ctx_view(c)} in closedContexts (want origin endturn, "
                         f"kind endturn, actorId -1, nestedIn 0, hasFinal false)")
        if aid and (len(ends) != 1 or st1 is None or ends[0]["seq"] >= st1):
            fails.append(f"context {aid}'s bt_action_end(s) {sv(ends)} (want exactly one, seq < the "
                         f"side_transition seq {st1})")
        between = [e for e in seg if e["kind"] == "bt_action_end" and x["seq"] < e["seq"]]
        if not aid and not between:
            fails.append(f"no bt_action_end between the explosion (seq {x['seq']}) and the side_transition "
                         f"(seq {st1}): segment {sv(seg)}")
        bad = [(e["seq"], e["kind"], e["actionId"]) for e in seg
               if e["kind"] in COMBAT_CUES and (not aid or e["actionId"] != aid)]
        if bad:
            fails.append(f"combat cue(s) before the side_transition not on the C3e context {aid}: {bad}")
    for i in g:
        if not gone[i]["host"] or not gone[i]["client"]:
            fails.append(f"grenade {i} present after the cycle host={not gone[i]['host']} "
                         f"client={not gone[i]['client']} (want absent on both)")
    if not any(gone[i]["host"] and gone[i]["client"] for i in clips):
        fails.append(f"no clip of {clips} absent on both after the cycle: {gone}")
    fails += segment_context_fails(seg, cev, rec["closed"], "C3e")
    fails += cycle_context_fails(rec, "cycle 1")
    fails += common_fails(host, client, rec["before"], {}, "C3e")
    finish(fails)


def c6_ai_shot(host, client, ctx):
    rec = ctx.get("cycle1")
    if rec is None:
        print(f"EVIDENCE C6: no cycle-1 record (C3e's staging failed before the cycle); staged="
              f"{ctx.get('c6_staged')}", flush=True)
        raise AssertionError("cycle 1 never ran (C3e's staging failed) - C6 has no alien side to check")
    hev, cev = rec["hev"], rec["cev"]
    sts = st_seqs(hev)
    st1 = sts[0] if len(sts) >= 1 else None
    st2 = sts[1] if len(sts) >= 2 else None
    seg = [e for e in hev if st1 is not None and e["seq"] > st1]
    side = [e for e in seg if st2 is None or e["seq"] < st2]
    cside = [e for e in cev if st1 is not None and st1 < e["seq"] and (st2 is None or e["seq"] < st2)]
    ai = sorted([c for c in rec["closed"] if c.get("origin") == "ai"
                 and any(e["actionId"] == c.get("actionId") for e in side)], key=lambda c: c.get("endSeq") or 0)
    c1 = ai[0] if ai else None
    c1evs = [e for e in side if c1 and e["actionId"] == c1.get("actionId")]
    shots = [e for e in side if e["kind"] == "shot"]
    turns = [e for e in side if e["kind"] == "turn"]
    pl = host_payloads(host, [e["seq"] for e in side if e["kind"] in ("turn", "shot", "hit")])
    first_shot = shots[0] if shots else None
    fsp = (pl.get(first_shot["seq"]) or {}).get("payload") or {} if first_shot else {}
    t1 = [e for e in c1evs if e["kind"] == "turn"]
    tpl = (pl.get(t1[0]["seq"]) or {}).get("payload") or {} if t1 else {}
    s1 = [e for e in c1evs if e["kind"] == "shot"]
    spl = (pl.get(s1[0]["seq"]) or {}).get("payload") or {} if s1 else {}
    uh, uc = units(host), units(client)
    ah, ac = uh.get(A_ID) or {}, uc.get(A_ID) or {}
    ch, cc = uh.get(C_ID) or {}, uc.get(C_ID) or {}
    print(f"EVIDENCE C6: staged={ctx.get('c6_staged')} A {C6_A_TILE}/{C6_A_DIR} C {C6_C_TILE}/{C6_C_DIR}; "
          f"side_transitions={sts}; alien side host={sv(side)} client={sv(cside)}; first shot="
          f"{first_shot and (first_shot['seq'], first_shot['actionId'])} payload={fsp}; turn evs on the side="
          f"{sv(turns)} payloads={[(e['seq'], (pl.get(e['seq']) or {}).get('payload')) for e in turns]}; "
          f"ai contexts={[ctx_view(c) for c in ai]}; first ai context evs={sv(c1evs)}; its turn payload={tpl} "
          f"shot payload={spl}; A host=(tu {ah.get('tu')}, dir {ah.get('direction')}, pos "
          f"({ah.get('x')},{ah.get('y')},{ah.get('z')})) client=(tu {ac.get('tu')}, dir {ac.get('direction')}, "
          f"pos ({ac.get('x')},{ac.get('y')},{ac.get('z')})); C health host={ch.get('health')} client="
          f"{cc.get('health')}; {context_evidence(rec)}; {cycle_evidence(rec)}", flush=True)
    fails = list(rec["notes"])
    fails += turn_fails(rec, "cycle 1")
    if st1 is None or st2 is None:
        fails.append(f"cycle 1's host log has side_transitions {sts} (want >= 2: player->hostile, "
                     f"hostile->neutral)")
    if not first_shot:
        fails.append(f"no `shot` ev on the alien side (host side evs {sv(side)})")
    elif first_shot["actionId"] == 0:
        fails.append(f"A's first shot (seq {first_shot['seq']}) carries actionId 0 (want its `ai` context's id)")
    if first_shot and fsp.get("actor") != A_ID:
        fails.append(f"the first shot's payload actor {fsp.get('actor')} (want A {A_ID}); payload={fsp}")
    kinds = [c.get("kind") for c in ai]
    if kinds != C6_AI_KINDS or any((c.get("actorId"), c.get("nestedIn"), c.get("hasFinal")) != (A_ID, 0, True)
                                   for c in ai):
        fails.append(f"`ai` contexts on the alien side {[ctx_view(c) for c in ai]} (want kinds {C6_AI_KINDS}, "
                     f"each actorId {A_ID}, nestedIn 0, hasFinal true)")
    if c1:
        ck = [e["kind"] for e in c1evs]
        if (len(ck) < 4 or ck[0] != "turn" or ck[1] != "shot" or ck[-1] != "bt_action_end"
                or any(k != "hit" for k in ck[2:-1])):
            fails.append(f"the first `ai` context {c1.get('actionId')} evs {sv(c1evs)} (want turn -> shot -> "
                         f">= 1 hit -> bt_action_end)")
        if (tpl.get("unit"), tpl.get("fromDir"), tpl.get("toDir")) != (A_ID, C6_A_DIR, C6_TURN_TO):
            fails.append(f"the first `ai` context's turn payload {tpl or None} (want unit {A_ID}, fromDir "
                         f"{C6_A_DIR}, toDir {C6_TURN_TO})")
        if spl.get("actor") != A_ID:
            fails.append(f"the first `ai` context's shot payload actor {spl.get('actor')} (want {A_ID})")
    if not turns:
        fails.append(f"no `turn` ev for A on the alien side (want one, in the first `ai` context)")
    elif len(turns) != 1 or not c1 or turns[0]["actionId"] != c1.get("actionId"):
        fails.append(f"turn evs on the alien side {sv(turns)} (want exactly one, in the first `ai` context "
                     f"{c1 and c1.get('actionId')})")
    fails += ai_actions_fails(side, rec["closed"], "C6")
    if (ah.get("tu"), ah.get("direction")) != (ac.get("tu"), ac.get("direction")):
        fails.append(f"A tu/direction host=({ah.get('tu')},{ah.get('direction')}) client=({ac.get('tu')},"
                     f"{ac.get('direction')}) (want equal)")
    if ch.get("health") != cc.get("health"):
        fails.append(f"C health host={ch.get('health')} client={cc.get('health')} (want equal)")
    fails += segment_context_fails(seg, cev, rec["closed"], "C6")
    fails += cycle_context_fails(rec, "cycle 1")
    fails += common_fails(host, client, rec["before"], {}, "C6")
    finish(fails)


def c7_ai_throw(host, client, ctx):
    notes2 = []
    # cycle 2 (battle turn 2): a plain cycle with A re-pinned (the AI throws grenades only from turn 3, F807)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu", "value": 0,
                        "refill": True}, ("tu",))
    rec2 = run_cycle(host, client, None, notes2)
    # cycle 3 staging
    strip_c = client.cmd({"cmd": "battle_strip_unit", "unit": A_ID})
    strip_h = host.cmd({"cmd": "battle_strip_unit", "unit": A_ID})
    assert strip_h.get("ok") and strip_c.get("ok"), f"battle_strip_unit A: host={strip_h} client={strip_c}"
    assert sorted(strip_h.get("deleted") or []) == sorted(strip_c.get("deleted") or []), (
        f"battle_strip_unit A deleted ids differ as sets (F882): host={strip_h.get('deleted')} "
        f"client={strip_c.get('deleted')}")
    gw = both(host, client, {"cmd": "battle_give", "unit": A_ID, "item": "STR_GRENADE", "slot": "STR_BELT"},
              ("weaponId", "ammoId", "weaponSlot"))
    gid = gw.get("weaponId")
    tele_both(host, client, A_ID, C7_A_TILE, C7_A_DIR)
    tele_both(host, client, C_ID, C7_C_TILE, C7_C_DIR)
    tele_both(host, client, C2_ID, C7_C2_TILE, C7_C2_DIR)
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "stat": "tu",
                        "value": A_TU}, ("tu",))
    staged_diff = diff_buckets(host, client)
    notes = []
    rec = run_cycle(host, client, SEED_C7, notes)
    hev, cev = rec["hev"], rec["cev"]
    sts = st_seqs(hev)
    st1 = sts[0] if len(sts) >= 1 else None
    st2 = sts[1] if len(sts) >= 2 else None
    side = [e for e in hev if st1 is not None and st1 < e["seq"] and (st2 is None or e["seq"] < st2)]
    cside = [e for e in cev if st1 is not None and st1 < e["seq"] and (st2 is None or e["seq"] < st2)]
    ai = sorted([c for c in rec["closed"] if c.get("origin") == "ai"
                 and any(e["actionId"] == c.get("actionId") for e in side)], key=lambda c: c.get("endSeq") or 0)
    c1 = ai[0] if ai else None
    c1evs = [e for e in side if c1 and e["actionId"] == c1.get("actionId")]
    shots = [e for e in side if e["kind"] == "shot"]
    expl = [e for e in side if e["kind"] == "explosion"]
    pl = host_payloads(host, [e["seq"] for e in side if e["kind"] in ("turn", "shot", "explosion")])
    throw = shots[0] if shots else None
    tp = (pl.get(throw["seq"]) or {}).get("payload") or {} if throw else {}
    t1 = [e for e in c1evs if e["kind"] == "turn"]
    tpl = (pl.get(t1[0]["seq"]) or {}).get("payload") or {} if t1 else {}
    c1end = c1evs[-1]["seq"] if c1evs else None
    ih, ic = items_by_id(host), items_by_id(client)
    g_gone = {"host": gid not in ih, "client": gid not in ic}
    print(f"EVIDENCE C7: cycle 2 {cycle_evidence(rec2)} host evs={sv(rec2['hev'])} client evs={sv(rec2['cev'])} "
          f"closedContexts(new)={[ctx_view(c) for c in rec2['closed']]}; strip host={strip_h.get('deleted')} "
          f"client={strip_c.get('deleted')}; grenade={gid} ({gw.get('weaponSlot')}); A {C7_A_TILE}/{C7_A_DIR} "
          f"C {C7_C_TILE}/{C7_C_DIR} C2 {C7_C2_TILE}/{C7_C2_DIR} stagedDiff={staged_diff}; cycle 3 "
          f"side_transitions={sts}; host evs since seq {rec['seq0']}={ev_tuples(hev)} client evs={ev_tuples(cev)} "
          f"(seq, kind, actionId, h); alien side host={sv(side)} client={sv(cside)}; throw="
          f"{throw and (throw['seq'], throw['actionId'])} payload={tp}; ai contexts={[ctx_view(c) for c in ai]}; "
          f"first ai context evs={sv(c1evs)} turn payload={tpl}; explosions (seq, actionId, context, payload)="
          f"{[(e['seq'], e['actionId'], ctx_view(ctx_of(rec['closed'], e['actionId'])), (pl.get(e['seq']) or {}).get('payload')) for e in expl]}; "
          f"grenade gone={g_gone}; {context_evidence(rec)}; {cycle_evidence(rec)}", flush=True)
    fails = list(notes2) + list(notes)
    fails += turn_fails(rec2, "cycle 2")
    if rec2["diff"]:
        fails.append(f"buckets differ after cycle 2: {rec2['diff']} (want none)")
    if staged_diff:
        fails.append(f"buckets differ after the cycle-3 staging: {staged_diff} (want none)")
    fails += turn_fails(rec, "cycle 3")
    if st1 is None or st2 is None:
        fails.append(f"cycle 3's host log has side_transitions {sts} (want >= 2: player->hostile, "
                     f"hostile->neutral)")
    if not throw:
        fails.append(f"no `shot` ev on the alien side (host side evs {sv(side)})")
    else:
        if throw["actionId"] == 0:
            fails.append(f"A's throw (seq {throw['seq']}) carries actionId 0 (want its `ai` context's id)")
        if tp.get("action") != "throw" or not isinstance(tp.get("arc"), dict) or tp.get("actor") != A_ID \
                or tp.get("weapon") != gid:
            fails.append(f"the throw's payload {tp or None} (want action throw with an arc, actor {A_ID}, weapon "
                         f"{gid})")
    if not c1 or (c1.get("kind"), c1.get("actorId"), c1.get("nestedIn"), c1.get("hasFinal")) != (
            "throw", A_ID, 0, True):
        fails.append(f"the first `ai` context on the alien side = {ctx_view(c1)} (want kind throw, actorId {A_ID}, "
                     f"nestedIn 0, hasFinal true; all ai contexts {[ctx_view(c) for c in ai]})")
    if c1:
        if [e["kind"] for e in c1evs] != ["turn", "shot", "bt_action_end"]:
            fails.append(f"the throw context {c1.get('actionId')} evs {sv(c1evs)} (want exactly turn -> shot -> "
                         f"bt_action_end; the grenade explodes at the end of the side, F808)")
        if (tpl.get("unit"), tpl.get("fromDir"), tpl.get("toDir")) != (A_ID, C7_A_DIR, C7_TURN_TO):
            fails.append(f"the throw context's turn payload {tpl or None} (want unit {A_ID}, fromDir {C7_A_DIR}, "
                         f"toDir {C7_TURN_TO})")
        if throw and throw["actionId"] != c1.get("actionId"):
            fails.append(f"the throw (seq {throw['seq']}) carries {throw['actionId']}, not the first `ai` context "
                         f"{c1.get('actionId')}")
    if not expl:
        fails.append(f"no `explosion` ev on the alien side (host side evs {sv(side)})")
    for e in expl:
        c = ctx_of(rec["closed"], e["actionId"]) if e["actionId"] else None
        if not c or (c.get("origin"), c.get("kind"), c.get("actorId"), c.get("nestedIn"), c.get("hasFinal")) != (
                "endturn", "endturn", -1, 0, False):
            fails.append(f"explosion seq {e['seq']} carries actionId {e['actionId']} (context {ctx_view(c)}; want an "
                         f"`endturn` context: origin endturn, kind endturn, actorId -1, nestedIn 0, hasFinal false)")
            continue
        eevs = [x for x in hev if x["actionId"] == e["actionId"]]
        eend = [x["seq"] for x in eevs if x["kind"] == "bt_action_end"]
        if len(eend) != 1 or st2 is None or not (e["seq"] < eend[0] < st2):
            fails.append(f"endturn context {e['actionId']} evs {sv(eevs)}: its bt_action_end must follow the "
                         f"explosion and precede the side_transition seq {st2}")
        if c1end is not None and e["seq"] < c1end:
            fails.append(f"explosion seq {e['seq']} lies inside the throw context (ends seq {c1end}); want it at "
                         f"the end of the alien side (F808)")
    if not g_gone["host"] or not g_gone["client"]:
        fails.append(f"grenade {gid} present after the cycle host={not g_gone['host']} client="
                     f"{not g_gone['client']} (want absent on both)")
    fails += ai_actions_fails(side, rec["closed"], "C7")
    fails += segment_context_fails(hev, cev, rec["closed"], "C7")
    fails += cycle_context_fails(rec, "cycle 3")
    fails += common_fails(host, client, rec["before"], {}, "C7")
    finish(fails)


SCENARIOS = (("C3e", c3e_endturn), ("C6", c6_ai_shot), ("C7", c7_ai_throw))


# ===================== bring-up =====================


def bring_up_lobby_roster_pinned(host, client, port):
    """raw.bring_up_lobby with ONE added call (W2-P2 amendment A2.2): set_seed
    SEED_ROSTER on the HOST immediately before its open_new_battle."""
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
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, baked "
        f"MAP_FP={MAP_FP!r} (default NEW BATTLE, SEED_MAP {SEED_MAP})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    pinned = pin_ai_neutral(host, client, tag="w2p3-sa")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    types = ((uh.get(A_ID) or {}).get("type"), (uc.get(A_ID) or {}).get("type"))
    assert types == (A_TYPE, A_TYPE), f"A {A_ID} battle_state type host/client={types} (want {A_TYPE})"
    # RQ15: every live player unit's reactions 0 on BOTH machines (no reaction fire in the AI rows)
    rz = []
    for uid, u in sorted(uh.items()):
        if u.get("faction") == FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
            rz.append(uid)
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("contextsOpened"), dict) and isinstance(es.get("closedContexts"), list)
                and isinstance(es.get("contextsClosedAtEndTurn"), int)
                and isinstance(es.get("contextBeginRefused"), int)
                and isinstance(es.get("armingDeferrals"), int)), (
            f"{gc.name} event_state lacks the S-A.1 context probes: contextsOpened={es.get('contextsOpened')!r} "
            f"closedContexts={es.get('closedContexts')!r} contextsClosedAtEndTurn="
            f"{es.get('contextsClosedAtEndTurn')!r} contextBeginRefused={es.get('contextBeginRefused')!r} "
            f"armingDeferrals={es.get('armingDeferrals')!r}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p3-sa] boot ok: SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={SEATED} "
          f"pinned={pinned} A type={types[0]} reactions 0 (both) for {rz} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49852, make_user_dir("w2p3_ai_origins_host"))
    client = GameClient("client", 49853, make_user_dir("w2p3_ai_origins_client"))
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
                print(f"[w2p3-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_ai_origins: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
