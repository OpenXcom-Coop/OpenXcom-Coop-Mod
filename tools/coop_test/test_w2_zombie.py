"""W2-P3 S-E - test_w2_zombie.py: a chryssalid's AI melee turns the second
player's soldier into a zombie, and the new unit appears on both machines with
the host's id - the whole chain one named `ai` action (spec
rewrite/prompts/w2p3_nonplayer_origins.md section (f) "test_w2_zombie.py (S-E;
terror + snakeman)", sections (b)1-(b)6 (the `ai` origin), (b)9 (the `spawn`
cue, V16 `convert`), (b)10 (unitsAdded: the client builds the unit through the
battle-load path); amendment B1 (RQ5, RQ7, RQ15); ledger `## W2-P3 TASK 0c`
(F871-F873) and `## W2-P3 TASK 0d` (F872); owner ruling D128 = (b)).

S-E is test-only: the product (S-A..S-D) is complete for this scenario. Its RED
is TASK 0d's C12b row, run on the W2-P3 base exe (`27bdec94e`): the conversion
rode a context-less `sync` (host (7 melee 0)(8 death 0)(9 sync 0)), the host
logged the unit add as deltaUnsupported 1, and the client froze at seq 9 on the
`items` bucket (F872). Since S-C the conversion rides a `spawn` cue in the
chryssalid's `ai` context and the zombie reaches the client through
`unitsAdded`.

One scenario, ONE boot:

  C12b  chryssalid zombie (cycle 1, battle turn 1 -> 2). The terror mission
        with the snakeman race (chryssalid terror units), map seed SEED_MAP.
        C (client seat soldier) on C_TILE facing Ch, Ch (the chryssalid)
        adjacent on CH_TILE facing C (no pre-attack turn), both on BOTH
        machines; C health C_HEALTH (BOTH); Ch unpinned with base tu CH_TU
        (BOTH, no refill: recovered at its side start) = exactly one BA_HIT
        (F873). Both machines press END TURN; host set_seed SEED_C12B right
        before its press. Ch's AI melee kills C without overkill and
        UnitDieBState converts C into the zombie Z = Z_ID (TASK 0c: Z owns
        ZOMBIE_WEAPON Z_WEAPON_ID; C's four items drop on C_TILE).
        GREEN: exactly one host context for Ch {origin ai, kind melee,
        actorId Ch, nestedIn 0, hasFinal true}; its evs are exactly melee
        {actor Ch, unit C} -> death {unit C} -> spawn {unit Z, cause convert,
        from C} -> bt_action_end (host log; the client log holds them); no
        `turn` ev for Ch (N4: AIModule::meleeAttack pre-turns the attacker
        directly); the only new unit on BOTH machines is Z with id Z_ID and
        type STR_ZOMBIE; C DEAD on both.
        W2-P6b S-D row D5 (spec rewrite/prompts/w2p6_display_two.md section 8,
        the P6b review's section 2 D5; AMENDMENTS P6b-1 and P6b-2): the
        client holds ONE death record for C's `death` ev {unit C, respawn
        true, isOutMs == tc (a respawn victim consumes every collapse frame in
        one tick), phasesShown [], endedBy "out" (the spawn's delta takes C off
        its tile)}, its schedule equal to test_w2_host_combat.death_schedule()
        for its own inputs, its `front` equal to the payload's; the common S-D
        asserts (client rngSeed unchanged, host displayTwo all zero, client
        completed + cut == enqueued, D-S3 sound lists / deathFrames /
        overKill). coopGhostStepper is pinned true in both instances. RED
        (commit S-D.1): C12b fails only on D5 (no record). One "EVIDENCE D5:"
        line.

Common asserts (spec (f) as amended by B1 RQ5, after the chain settled):
W2-P2's common asserts (hash_now {full:true} ALL buckets EQUAL; desyncSeen
false on both; client coopClientBStatePushes unchanged and host 0; client
deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing, deltaAddExisting 0 on both; staging writes on BOTH with
equal responses); host contextBeginRefused 0; contextsOpened grew by exactly
the number of contexts the scenario closed; every chain ev carries the id of a
context the scenario closed (a `fall`/`revive`/`spawn` outside a chain may
carry 0); every context has exactly one bt_action_end, its last ev, recorded
in closedContexts (endSeq); no `sync` and no side_transition inside a
context; every side_transition carries actionId 0; the client log holds the
host's seqs/kinds/actionIds. contextsClosedAtEndTurn is a diagnostic
(printed, never asserted, RQ5).

Probes: event_state closedContexts, contextsOpened, contextBeginRefused,
contextsClosedAtEndTurn, cueCounts, deltaRing (the host's attached deltas by
seq with unitsAddedIds / itemsAddedIds), lastDelta, the W2-P2 delta counters;
battle_state units (type, faction, status, isOut, onTile, position, tu,
health, stun); battle_items (type, owner, slot, tile); the host's own
`[coop-cue]` / `[coop-turn]` log lines for the payloads (event_log carries no
payload); hash_now {full:true}.

Bring-up (deterministic, never searched here; ledger `## W2-P3 TASK 0c`,
scratch w2p3/T0c/constants.md, 3 boots identical plus a 2.6 s NextTurnState
dwell variant): set_seed SEED_ROSTER on the HOST right before its
open_new_battle; newbattle_mission STR_TERROR_MISSION, then newbattle_race
STR_SNAKEMAN (pre_seat), set_seed SEED_MAP right before newbattle_ok,
seat_count=2, MAP_FP asserted on both; session.pin_ai_neutral (the 23
non-player units); RQ15: every live player unit's reactions 0 on BOTH. Every
lever pair applies to the CLIENT first, then the HOST (F607). The seed is set
on the HOST immediately before the press that starts the chain.

The scenario prints ONE "EVIDENCE C12b:" line with both machines' fields
BEFORE its green conditions are checked, then "PASS C12b" / "FAIL C12b:
<message>". Every wait is bounded; a wait that times out is recorded in the
EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when the scenario passes, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_zombie.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_w2_delta_core import diff_buckets, short, both, tele_both, common_fails, finish, hashes
from test_w2_ai_origins import host_payloads, ctx_probes, ctx_view, sv, bring_up_lobby_roster_pinned
from test_w2_unit_spawn import ring_at, ring_view
from test_w2_turn_cues import (begin, end, cycle, rec_evidence, cycle_fails, context_fails, payload, held_by_client,
                               items, st_seqs)
from test_w2_host_combat import (death_snap, death_row, wait_death_ghosts_ended, DEATH_IS_TURN, SOLDIER_DEATH_SOUNDS,
                                 OVERKILL_NONE)

# ----- bring-up (W2-P3 TASK 0c, T0c constants.md "Common bring-up" + "C12b") -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok
MISSION, RACE = "STR_TERROR_MISSION", "STR_SNAKEMAN"   # newbattle_mission, then newbattle_race (pre_seat)
MAP_FP = -3.451266327757785e+18  # host AND client battle_state.mapFingerprint (50x50x4 city map)
SEATED = [8, 9]                  # the client seat's soldiers
PINNED = list(range(1000000, 1000023))   # pin_ai_neutral: the 23 non-player units (30 units at start)
START_ITEMS = 91                 # 91 items at start (ids 0..90)
PORT = "48637"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus

# ----- C12b (T0c constants.md "C12b"; F871-F873) -----
C_ID = 8                         # client seat soldier (converted)
CH_ID = 1000009                  # the chryssalid (spawn (8,0,0) dir 4)
CH_TYPE, CH_ARMOR = "STR_CHRYSSALID_TERRORIST", "CHRYSSALID_ARMOR"
C_TILE, C_DIR = (24, 24, 0), 2   # open street, faces Ch
CH_TILE, CH_DIR = (25, 24, 0), 6  # adjacent, faces C (the direction Ch -> C is 6: no pre-attack turn)
C_HEALTH = 10                    # battle_set_unit_state {unit C, health} on both
CH_TU = 15                       # set_stat tu (no refill): exactly one BA_HIT at the hostile side (F873)
SEED_C12B = 2                    # host set_seed right before its END TURN press (after the client's press)
Z_ID, Z_TYPE = 1000023, "STR_ZOMBIE"   # the new unit = last unit id + 1
Z_WEAPON_ID = 91                 # ZOMBIE_WEAPON, owner Z (itemIdCtr 91 -> 92); printed
CHAIN = ["melee", "death", "spawn", "bt_action_end"]
PAYLOAD_EXTRA = ("turn",)        # payloads read beyond test_w2_turn_cues.end()'s kinds
# W2-P6b S-D row D5 (review section 2): C's death record on the client
D5_DEATH = {"unit": C_ID, "outcome": "dead", "instant": False}   # the death payload subset (no overkill: converts)
D5_OCTANTS = (3 - C_DIR) % 8     # 1: C faces 2 at the death (staged; the chryssalid pre-turns only itself, N4)
UNIT_KEYS = ("type", "faction", "originalFaction", "status", "isOut", "onTile", "x", "y", "z", "direction", "tu",
             "health", "stun", "spawnUnit", "respawn", "specialWeapons")


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def xyz(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def uview(u):
    if not u:
        return None
    return {k: u.get(k) for k in UNIT_KEYS}


def iview(it):
    if not it:
        return None
    return {k: it.get(k) for k in ("type", "owner", "slot", "special", "onTile", "tx", "ty", "tz")}


def units_evidence(rec, ids):
    return {uid: {"host": uview(rec["uh"].get(uid)), "client": uview(rec["uc"].get(uid))} for uid in ids}


def items_evidence(rec, ids):
    return {iid: {"host": iview(rec["ih"].get(iid)), "client": iview(rec["ic"].get(iid))} for iid in ids}


# ===================== the scenario =====================


def c12b_zombie(host, client, ctx):
    rec = begin(host, client)
    tele_both(host, client, C_ID, C_TILE, C_DIR)
    tele_both(host, client, CH_ID, CH_TILE, CH_DIR)
    hr = both(host, client, {"cmd": "battle_set_unit_state", "unit": C_ID, "health": C_HEALTH},
              ("health", "stun", "status", "tu"))
    tr = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": CH_ID, "stat": "tu",
                             "value": CH_TU}, ("tu",))
    staged_diff = diff_buckets(host, client)
    uh0, uc0 = units(host), units(client)
    ih0 = items(host)
    c_items = sorted(i for i, it in ih0.items() if it.get("owner") == C_ID)
    staged = {"C": {"host": uview(uh0.get(C_ID)), "client": uview(uc0.get(C_ID))},
              "Ch": {"host": uview(uh0.get(CH_ID)), "client": uview(uc0.get(CH_ID))}}
    snap_d = death_snap(host, client)   # W2-P6b S-D row D5
    cycle(host, client, SEED_C12B, rec, "cycle 1")
    wait_death_ghosts_ended(client, rec["notes"])
    end(host, client, rec)
    hev = rec["hev"]
    rec["pl"].update(host_payloads(host, [e["seq"] for e in hev if e["kind"] in PAYLOAD_EXTRA]))
    hh, hc = hashes(host), hashes(client)
    item_ctr = (hh.get("itemIdCtr"), hc.get("itemIdCtr"))
    new_h = sorted(set(rec["uh"]) - set(uh0))
    new_c = sorted(set(rec["uc"]) - set(uc0))
    ai_ch = sorted([c for c in rec["closed"] if c.get("origin") == "ai" and c.get("actorId") == CH_ID],
                   key=lambda c: c.get("endSeq") or 0)
    c1 = ai_ch[0] if len(ai_ch) == 1 else None
    cevs = [e for e in hev if c1 and e["actionId"] == c1.get("actionId")]
    melee = [e for e in cevs if e["kind"] == "melee"]
    death = [e for e in cevs if e["kind"] == "death"]
    spawn = [e for e in cevs if e["kind"] == "spawn"]
    turns = [e for e in hev if e["kind"] == "turn"]
    sring = ring_view(ring_at(rec["ring"], spawn[0]["seq"])) if spawn else None
    print(f"EVIDENCE C12b: C {C_TILE}/{C_DIR} health response={hr.get('health')} Ch {CH_TILE}/{CH_DIR} tu response="
          f"{tr.get('tu')} stagedDiff={staged_diff} staged={staged} C's items before={c_items}; seed {SEED_C12B}; "
          f"cycle side_transitions={st_seqs(hev)}; Ch's ai contexts={[ctx_view(c) for c in ai_ch]} its evs={sv(cevs)} "
          f"payloads (seq, kind, actionId, payload)={[(e['seq'], e['kind'], e['actionId'], payload(rec, e)) for e in cevs]}; "
          f"turn evs (seq, actionId, payload)={[(e['seq'], e['actionId'], payload(rec, e)) for e in turns]}; the spawn "
          f"ev's delta={sring}; new units host={new_h} client={new_c}; units="
          f"{units_evidence(rec, [C_ID, CH_ID, Z_ID])}; items={items_evidence(rec, [Z_WEAPON_ID] + c_items)}; "
          f"itemIdCtr host/client={item_ctr}; {rec_evidence(rec)}", flush=True)
    # W2-P6b S-D row D5 (review section 2): C's death record (a respawn victim) on the client
    md_seqs = [e["seq"] for e in melee + death]
    md_ring = [r for r in (rec["ring"] or []) if r.get("seq") in md_seqs]   # C's pre-death facing evidence
    d5 = death_row("D5", host, client, snap_d, extra={"stagedC": staged["C"], "hostDeltaRingMeleeDeath": md_ring},
                   wants=[
        {"seq": death[0]["seq"] if death else None, "actionId": c1.get("actionId") if c1 else None, "unit": C_ID,
         "payload": D5_DEATH, "front": None, "payloadFront": False, "fromDir": C_DIR, "octants": D5_OCTANTS,
         "respawn": True, "Is": DEATH_IS_TURN, "sounds": SOLDIER_DEATH_SOUNDS, "startedAfterSeq": 0,
         "overKill": OVERKILL_NONE, "endedBy": "out", "unitDyingSet": True, "phasesShown": []}])
    fails = list(rec["notes"])
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    if hr.get("health") != C_HEALTH:
        fails.append(f"staging response C health={hr.get('health')} (want {C_HEALTH})")
    fails += cycle_fails(rec, "C12b")
    if len(ai_ch) != 1:
        fails.append(f"host closedContexts with origin ai and actorId {CH_ID} = {[ctx_view(c) for c in ai_ch]} (want "
                     f"exactly one: {{origin ai, kind melee, actorId {CH_ID}}}; new entries "
                     f"{[ctx_view(c) for c in rec['closed']]})")
    if c1:
        if (c1.get("kind"), c1.get("nestedIn"), c1.get("hasFinal")) != ("melee", 0, True):
            fails.append(f"Ch's context {ctx_view(c1)} (want kind melee, nestedIn 0, hasFinal true)")
        if [e["kind"] for e in cevs] != CHAIN:
            fails.append(f"Ch's context {c1.get('actionId')} evs {sv(cevs)} (want exactly {CHAIN})")
        mp = payload(rec, melee[0]) if melee else {}
        if (mp.get("actor"), mp.get("unit")) != (CH_ID, C_ID):
            fails.append(f"the melee payload {mp or None} (want actor {CH_ID}, unit {C_ID})")
        dp = payload(rec, death[0]) if death else {}
        if dp.get("unit") != C_ID:
            fails.append(f"the death payload {dp or None} (want unit {C_ID})")
        sp = payload(rec, spawn[0]) if spawn else {}
        if (sp.get("unit"), sp.get("cause"), sp.get("from")) != (Z_ID, "convert", C_ID):
            fails.append(f"the spawn payload {sp or None} (want unit {Z_ID}, cause convert, from {C_ID})")
        missing = [e["seq"] for e in cevs if not held_by_client(rec, e)]
        if missing:
            fails.append(f"the client log does not hold Ch's context evs at seq(s) {missing}")
    bad_turns = [(e["seq"], payload(rec, e) or None) for e in turns
                 if not payload(rec, e) or payload(rec, e).get("unit") == CH_ID]
    if bad_turns:
        fails.append(f"`turn` evs for Ch (or without a payload) {bad_turns} (want no `turn` ev for Ch, N4)")
    if new_h != [Z_ID] or new_c != [Z_ID]:
        fails.append(f"new units host={new_h} client={new_c} (want exactly [{Z_ID}] on both)")
    for name, u in (("host", rec["uh"].get(Z_ID)), ("client", rec["uc"].get(Z_ID))):
        if not u or u.get("type") != Z_TYPE:
            fails.append(f"Z {Z_ID} on the {name} {uview(u)} (want type {Z_TYPE})")
    for name, u in (("host", rec["uh"].get(C_ID)), ("client", rec["uc"].get(C_ID))):
        if not u or u.get("status") != STATUS_DEAD:
            fails.append(f"C {C_ID} on the {name} {uview(u)} (want status DEAD)")
    fails += context_fails(rec, "C12b")
    fails += d5
    fails += common_fails(host, client, rec["before"], {}, "C12b")
    finish(fails)


SCENARIOS = (("C12b", c12b_zombie),)


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}

    def pre_seat(h):
        r = h.cmd({"cmd": "newbattle_race", "race": RACE})
        assert r.get("ok"), f"newbattle_race {RACE} refused: {r}"

    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2, pre_seat=pre_seat,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, baked "
        f"MAP_FP={MAP_FP!r} ({MISSION} + {RACE}, SEED_MAP {SEED_MAP})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    pinned = pin_ai_neutral(host, client, tag="w2p3-se-zombie")
    assert pinned == PINNED, f"pin_ai_neutral pinned {pinned} (baked {PINNED[0]}..{PINNED[-1]})"
    uh, uc = session.units_by_id(hs), session.units_by_id(cs)
    ch = ((uh.get(CH_ID) or {}).get("type"), (uc.get(CH_ID) or {}).get("type"),
          (uh.get(CH_ID) or {}).get("armor"), (uc.get(CH_ID) or {}).get("armor"))
    assert ch == (CH_TYPE, CH_TYPE, CH_ARMOR, CH_ARMOR), (
        f"Ch {CH_ID} type/armor host, client={ch} (want {CH_TYPE}, {CH_ARMOR})")
    assert Z_ID not in uh and Z_ID not in uc and max(uh) == Z_ID - 1 and max(uc) == Z_ID - 1, (
        f"unit ids at start host max={max(uh)} client max={max(uc)} (want {Z_ID - 1}: Z = last id + 1)")
    ih, ic = items(host), items(client)
    assert (len(ih), max(ih) + 1, len(ic), max(ic) + 1) == (START_ITEMS,) * 4, (
        f"items at start host n={len(ih)} max={max(ih)} client n={len(ic)} max={max(ic)} (baked {START_ITEMS} "
        f"items, ids 0..{START_ITEMS - 1})")
    # RQ15: every live player unit's reactions 0 on BOTH machines (no reaction to the chryssalid)
    rz = []
    for uid, u in sorted(uh.items()):
        if u.get("faction") == FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
            rz.append(uid)
    for gc in (host, client):
        es = event_state(gc)
        u0 = session.units_by_id(battle_state(gc)).get(C_ID) or {}
        assert (isinstance(es.get("deltaRing"), list) and isinstance(es.get("closedContexts"), list)
                and isinstance(es.get("contextsOpened"), dict) and isinstance(es.get("cueCounts"), dict)
                and isinstance(es.get("contextBeginRefused"), int)
                and all(k in u0 for k in ("type", "status", "onTile", "spawnUnit"))), (
            f"{gc.name} lacks a probe: deltaRing={es.get('deltaRing')!r} closedContexts={es.get('closedContexts')!r} "
            f"contextsOpened={es.get('contextsOpened')!r} contextBeginRefused={es.get('contextBeginRefused')!r} "
            f"unit {C_ID} keys={sorted(u0)}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p3-se] boot ok: {MISSION} + {RACE} SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} missionType="
          f"{hs.get('missionType')} turn={hs['turn']} seated={SEATED} pinned={len(pinned)} ({pinned[0]}..{pinned[-1]}) "
          f"Ch={ch[0]}/{ch[2]} items={len(ih)} reactions 0 (both) for {rz} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    # W2-P6b S-D: coopGhostStepper pinned true in both instances (row D5 needs the client's death ghost)
    host = GameClient("host", 49862, make_user_dir("w2p3_zombie_host", options={"coopGhostStepper": True}))
    client = GameClient("client", 49863, make_user_dir("w2p3_zombie_client", options={"coopGhostStepper": True}))
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
                print(f"[w2p3-se] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_zombie: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
