"""W1-P9 follow-up: a walk that executes ZERO steps must still leave the two
machines identical.

THE DEFECT THIS PINS (RCA from a surviving desync bundle,
desync-20260903-153856, plus a deterministic reproduction):

  * `bt_action_end` carries no `unit` - SS2.3 froze it that way - so the CLIENT
    resolves the action's actor from `g_coopClientActionActor`, which is
    populated ONLY when a preceding `bt_ev` carried `payload["unit"]`
    (connectionTCP.cpp:5717-5729).
  * A walk emits that ev per EXECUTED step. A walk that executes ZERO steps
    emits none - and the host still sends the completion restate, because
    `end["path"] = path` is unconditional inside the `wasWalk` branch
    (connectionTCP.cpp:3765-3768) and an empty `executed` is still an array.
  * So the client cannot resolve the actor, silently skips `final`, and every
    field `final` carries - tu, energy, direction, the kneeled bit - stays at
    its pre-action value while the host has moved on. `unitsStats` and
    `saveBlob` diverge and the client desync-freezes.

The same run also exposed a MISLEADING DIAGNOSTIC: the restate-mismatch log
line printed `g_coopWalkChain.steps.size()` without the chain's actionId, so a
STALE chain from a previous action read as a matching one ("does not match the
2 step ev(s) this machine applied" for a walk that applied none of its own).
The chain is only reset inside the `walk_step` applier, which a zero-step walk
never reaches.

HOW A ZERO-STEP WALK IS PRODUCED HERE - deterministically, with a lever, and
why the lever is needed. `battle_halt_walk` cannot do it: it is consumed in
`coopOnWalkStepFinished()`, which by definition runs AFTER a step completed, so
it halts after step 1. `battle_halt_walk_before_step` is its pre-step sibling,
consumed at a call site vanilla already reaches before `startWalking()`.

  THE SAME DEFECT IS REACHABLE WITHOUT ANY LEVER, and that is what was found in
  the wild: vanilla stands a KNEELED walker up before its first step, spending
  `getKneelChangeCost()` (UnitWalkBState.cpp:104-118 -> BattlescapeGame.cpp:488-495),
  while the host's admission gate checks first-step affordability against the
  actor's CURRENT TU only (connectionTCP.cpp:3460). A kneeled actor with enough
  TU for its first step but not for stand-up PLUS that step is therefore
  ADMITTED and then executes zero steps. Reproduced by hand at TU 12:
  `steps=0 halted=True reason=no_tu pathLen=0`, followed immediately by
  `unitsStats` + `saveBlob` diverging. PHASE 2 below pins that route too, with
  no lever at all.

Run:  python tools/coop_test/repro_walk_zero_step.py
      (in its OWN shell invocation - the standing harness rule.)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean
import repro_atom_walk as W



def zero_step_walk(host, client, actor_id, dest, tag):
    """Order one walk and require the host to have executed ZERO steps.

    Returns the host's lastWalk record. Everything here is a PREMISE check, not
    an assertion about the atom - the assertions live in the caller."""
    prev = W.walk_action_id(host)
    resp = None
    for d in (dest if isinstance(dest, list) else [dest]):
        resp = W.send_walk(client, actor_id, d)
        if resp.get("iseq"):
            break
        print(f"    [{tag}] no route to {d} ({resp.get('error')}) - next destination")
    assert resp and resp.get("iseq"), (
        f"{tag}: no candidate destination produced an ADMITTED walk - the zero-step "
        "case cannot be reached without one (FIXTURE, not the defect)")
    W.wait_walk_settled(host, client, prev)
    W.settle_reveal(host, client)
    hw = W.last_walk(host)
    steps = len(hw.get("steps") or [])
    restate = hw.get("restate") or {}
    print(f"    [{tag}] actionId {hw.get('actionId')}: {steps} step(s) executed, "
          f"halted={restate.get('halted')} reason={restate.get('reason')} "
          f"restate path length {len(restate.get('path') or [])}")
    assert steps == 0, (
        f"{tag}: the walk executed {steps} step(s), not zero - this test's whole "
        "subject is the zero-step case and it did not occur, so nothing below "
        "would be testing the defect")
    return hw


def assert_final_landed(host, client, actor_id, tag):
    """THE ASSERTION. The client must hold the host's post-action unit state and
    every bucket must be EQUAL - which is exactly what a dropped `final` breaks."""
    h = W.unit_of(host, actor_id)
    c = W.unit_of(client, actor_id)
    fields = ("tu", "energy", "kneeled", "direction", "x", "y", "z")
    mism = {f: (h.get(f), c.get(f)) for f in fields if h.get(f) != c.get(f)}
    assert not mism, (
        f"{tag}: after a ZERO-STEP walk the client's actor {actor_id} disagrees with "
        f"the host on {mism}. No `bt_ev` carried the actor for this action, so the "
        "client could not resolve bt_action_end's `final` and silently dropped it "
        "(connectionTCP.cpp:5717-5729)")
    assert battle_frozen(host) is False, f"{tag}: the HOST is desync-frozen"
    assert battle_frozen(client) is False, (
        f"{tag}: the CLIENT is desync-frozen - the post-apply hash compare FAILED "
        "after the zero-step walk")
    assert_hash_clean(host, client, full=True, what=f"{tag} after a zero-step walk")
    print(f"    [{tag}] PASS: actor {actor_id} identical on both machines "
          f"(tu={h.get('tu')} energy={h.get('energy')} kneeled={h.get('kneeled')} "
          f"dir={h.get('direction')}), all buckets EQUAL")


def battle_frozen(gc):
    return session.battle_state(gc)["authority"]["desyncFrozen"]


def kneel_actor(host, client, actor_id, tag):
    """Kneel through the SYNCED atom, so both machines agree before the walk."""
    if W.unit_of(host, actor_id).get("kneeled"):
        return
    r = client.cmd({"cmd": "battle_intent", "kind": "kneel", "actor": actor_id,
                    "kneel": True})
    assert r.get("iseq"), f"{tag}: the kneel intent did not ship: {r}"
    client.wait_for("kneel applied on both machines",
                    lambda: (W.unit_of(host, actor_id).get("kneeled") is True
                             and session.event_state(client).get("queueDepth") == 0
                             and session.event_state(client).get("lastSeqApplied", 0)
                             == session.event_state(host).get("lastSeqEmitted", 0)) or None,
                    timeout=30)
    W.settle_reveal(host, client)
    assert_hash_clean(host, client, full=True, what=f"{tag} after kneeling")


def phase1_lever(host, client, actor_id):
    """A zero-step walk that DID change the host's unit state - the case the
    defect actually bites on.

    THE ACTOR IS KNEELED FIRST, and that is the whole point. Vanilla stands a
    kneeled walker up BEFORE its first step, spending getKneelChangeCost()
    (UnitWalkBState.cpp:104-118 -> BattlescapeGame.cpp:488-495), and only then
    reaches the step-cost block where the pre-step lever aborts. So the host
    finishes the action with LESS TU and NOT kneeled, having executed zero steps
    and therefore emitted no `bt_ev` carrying the actor - and the client, unable
    to resolve bt_action_end's `final`, keeps the pre-action values.

    Measured: with the lever alone and an UPRIGHT actor, nothing diverges,
    because a pre-step abort changes nothing for `final` to carry. That variant
    passes on the unfixed build and would have been a vacuous test."""
    print("\n== PHASE 1: zero-step walk that CHANGED host state (kneel + lever) ==")
    assert_hash_clean(host, client, full=True, what="PHASE 1 t=0")
    kneel_actor(host, client, actor_id, "PHASE 1")
    before = W.unit_of(host, actor_id)
    dests = W.walk_candidates(host, actor_id, lengths=(1, 2, 3))
    assert dests, "FIXTURE: no routable destination for the actor"
    assert host.cmd({"cmd": "battle_halt_walk_before_step"}).get("ok"),         "PHASE 1: battle_halt_walk_before_step lever refused"
    hw = zero_step_walk(host, client, actor_id, dests[:8], "PHASE 1")
    assert (hw.get("restate") or {}).get("halted") is True,         "PHASE 1: a zero-step walk must still report halted:true"
    after = W.unit_of(host, actor_id)
    assert (after.get("tu"), after.get("kneeled")) != (before.get("tu"),
                                                       before.get("kneeled")), (
        "PHASE 1 NON-VACUITY: the host's actor state did NOT change across the "
        f"zero-step walk (tu {before.get('tu')}->{after.get('tu')}, kneeled "
        f"{before.get('kneeled')}->{after.get('kneeled')}) - with nothing for "
        "`final` to carry, a dropped `final` is a no-op and the assertion below "
        "would pass whether the defect is present or not")
    print(f"    [PHASE 1] host actor changed across the zero-step walk: "
          f"tu {before.get('tu')} -> {after.get('tu')}, "
          f"kneeled {before.get('kneeled')} -> {after.get('kneeled')}")
    assert_final_landed(host, client, actor_id, "PHASE 1")


def phase2_admission(host, client, actor_id):
    """GAP 1: admission must count the MANDATORY stand-up before step 1.

    Vanilla stands a kneeled walker up before its first step, spending
    getKneelChangeCost() (UnitWalkBState.cpp:104-118 -> BattlescapeGame.cpp:
    488-495). The host's affordability gate used to check the first step against
    CURRENT TU only (connectionTCP.cpp:3460), so a kneeled actor with enough TU
    for the step but not for stand-up PLUS the step was ADMITTED and then
    executed ZERO steps - reproduced by hand at TU 12 before the fix:
    `steps=0 halted=True reason=no_tu pathLen=0`, immediately followed by
    `unitsStats` + `saveBlob` diverging.

    THE ASSERTION: sweeping TU downward, the walk must go from ADMITTED to
    DENIED `cost_changed`. It must never be admitted and then execute nothing -
    that is the 'no silent no-op' SS2.W2's validator bullet forbids, and
    SS2.W2/WR-14 map an admission-time shortfall to exactly that deny."""
    print("\n== PHASE 2: admission counts the stand-up (GAP 1, no lever) ==")
    kneel_actor(host, client, actor_id, "PHASE 2")
    dests = W.walk_candidates(host, actor_id, lengths=(1, 2, 3))
    assert dests, "FIXTURE: no routable destination for the kneeled actor"

    denied = []
    admitted = []
    for tu in (16, 15, 14, 13, 12, 11, 10, 9, 8):
        for gc in (host, client):
            gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": actor_id,
                    "stat": "tu", "value": tu, "refill": True})
        assert_hash_clean(host, client, full=True,
                          what=f"PHASE 2 after a symmetric TU set to {tu}")
        kneel_actor(host, client, actor_id, "PHASE 2")
        for gc in (host, client):
            gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": actor_id,
                    "stat": "tu", "value": tu, "refill": True})
        assert_hash_clean(host, client, full=True,
                          what=f"PHASE 2 after re-kneeling at TU {tu}")

        prev = W.walk_action_id(host)
        shipped = None
        for d in dests[:6]:
            r = W.send_walk(client, actor_id, d)
            if r.get("iseq"):
                shipped = r
                break
        if not shipped:
            print(f"    TU {tu}: no route from here - skipped")
            continue
        outcome = None
        for _ in range(200):
            hw = W.last_walk(host)
            if (hw.get("actionId", 0) != prev and hw.get("active") is False
                    and hw.get("restate")):
                outcome = "walk"
                break
            ld = session.event_state(client).get("lastDeny")
            if ld and ld.get("iseq") == shipped["iseq"]:
                outcome = "deny:" + str(ld.get("reason"))
                break
            time.sleep(0.05)
        assert outcome, f"PHASE 2: TU {tu} was neither executed nor denied"

        if outcome.startswith("deny"):
            denied.append((tu, outcome))
            print(f"    TU {tu}: {outcome}")
            assert outcome == "deny:cost_changed", (
                f"PHASE 2: TU {tu} was denied {outcome}, but an admission-time "
                "shortfall must map to cost_changed (SS2.W2/WR-14)")
        else:
            W.settle_reveal(host, client)
            hw = W.last_walk(host)
            steps = len(hw.get("steps") or [])
            admitted.append((tu, steps))
            print(f"    TU {tu}: admitted, {steps} step(s)")
            assert steps > 0, (
                f"PHASE 2: at TU {tu} the walk was ADMITTED and then executed ZERO "
                "steps. Admission did not count the stand-up cost vanilla charges "
                "before the first step, which is the silent no-op SS2.W2 forbids "
                "and the state loss this file's PHASE 1 pins")
        assert_hash_clean(host, client, full=True,
                          what=f"PHASE 2 after the TU {tu} attempt")

    assert admitted, "FIXTURE: no TU value was admitted at all - nothing was proven"
    assert denied, (
        "FIXTURE: no TU value was DENIED, so the admission boundary was never "
        f"crossed and gap 1 is untested here (admitted: {admitted})")
    print(f"    [PHASE 2] PASS: the boundary is real - admitted {admitted}, "
          f"denied {denied}; no admitted walk executed zero steps")



# ===== SPEC 6g: bring_up moved here from repro_atom_door.py, its ONE remaining
# consumer (AMENDMENT 2). It cannot live in session.py: it calls
# W.bring_up_lobby, and repro_atom_walk imports session, which would cycle. The
# local MAX_REROLLS was 12 and DEAD (single occurrence, nothing imports this
# module); the value bring_up actually uses is repro_atom_door's 60, moved with it.
MAX_REROLLS = 60
DOOR_MISSION = "STR_SMALL_SCOUT"


class FixtureExhausted(Exception):
    """MAX_REROLLS boots produced no qualifying map. Carries the histogram."""

# SPEC 6c2 (d) step 4 / WV-D72. The --deterministic path's own fresh-boot
# retry ceiling - deliberately far below MAX_REROLLS=60, because the WV-D63
# lever PINS the situation instead of searching a map-rolled one for it: a
# staging miss here is a fixture-lever finding to report (rate), never a
# reason to grind through dozens of boots hoping for better luck.


def bring_up(tag, mission, qualifies, base_port, base_probe, max_attempts=None):
    """`max_attempts` (SPEC 6c2 / WV-D72, additive): caps the re-roll/fresh-
    boot loop below the module's own MAX_REROLLS - the --deterministic path
    passes DETERMINISTIC_MAX_BOOTS (3) here, since a WV-D63-staged SITUATION
    that still fails to qualify after a few fresh boots is a lever finding,
    not a map-luck grind. `None` (every existing caller) preserves today's
    MAX_REROLLS behaviour byte-for-byte."""
    limit = MAX_REROLLS if max_attempts is None else max_attempts
    why_log = []
    for attempt in range(1, limit + 1):
        port = str(base_port + attempt)
        host = GameClient("host", base_probe + attempt * 2,
                          make_user_dir(f"repro_atom_door_{tag}_host_{attempt}"))
        client = GameClient("client", base_probe + 1 + attempt * 2,
                            make_user_dir(f"repro_atom_door_{tag}_client_{attempt}"))
        seated = {}
        try:
            W.bring_up_lobby(host, client, port)
            session.drive_to_battlescape(host, client, seated, mission=mission)
            why = qualifies(host, client)
            if why is None:
                print(f"[repro_atom_door] {tag} fixture qualifies on attempt "
                      f"{attempt}/{limit} ({attempt - 1} re-roll(s))")
                return host, client
            why_log.append(why)
            print(f"[repro_atom_door] {tag} re-roll {attempt}/{limit}: {why}")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise
    tally = {}
    for w in why_log:
        key = w.split(":")[0].split("(")[0].strip()
        tally[key] = tally.get(key, 0) + 1
    lines = [f"no qualifying {tag} fixture in {limit} boots - the map "
             "generator never offered a testable situation, which is not a "
             "statement about the door atom",
             "      rejection histogram:"]
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        lines.append(f"      {v:4d}  {k}")
    lines.append(f"      last: {why_log[-1] if why_log else None}")
    raise FixtureExhausted(("\n".join(lines)))


def qualifies(host, client):
    st = session.battle_state(host)
    if not st.get("inBattle"):
        return "no battle"
    if session.spotted(host):
        return f"a hostile is already visible to the host at t=0: {session.spotted(host)}"
    seats = session.seat_units(host)
    if len(seats) < 2:
        return f"only {len(seats)} seat-1 soldier(s)"
    rich = [u for u in seats if u.get("tu", 0) > 30]
    if not rich:
        return f"no seat-1 soldier with TU to spare: {[(u['id'], u.get('tu')) for u in seats]}"
    if not W.walk_candidates(host, rich[0]["id"], lengths=(1, 2, 3)):
        return f"no routable destination for actor {rich[0]['id']}"
    return None


def main():
    t0 = time.time()
    print("=== FIXTURE: the default skirmish (a routable actor is all this needs) ===")
    host, client = bring_up("zerostep", DOOR_MISSION, qualifies, 48780, 49780)
    try:
        seats = [u for u in session.seat_units(host) if u.get("tu", 0) > 30]
        phase1_lever(host, client, seats[0]["id"])
        phase2_admission(host, client,
                         seats[1]["id"] if len(seats) > 1 else seats[0]["id"])
    finally:
        host.shutdown()
        client.shutdown()
    print(f"\nrepro_walk_zero_step: PASS ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, TimeoutError) as e:
        print(f"\nrepro_walk_zero_step: FAIL\n{type(e).__name__}: {e}")
        sys.exit(2)
