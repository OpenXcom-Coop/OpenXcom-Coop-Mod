"""W1-P12 (WAVE1-RUNBOOK.md SPEC 7, ruling D-3 = WV-D27/WV-D49/A4): the S3
GHOST STEPPER - a partner's turn/kneel/walk ANIMATES on the observing machine
instead of snapping, display-only, without moving a single hash bucket.

FIXTURE: reuses repro_atom_walk.py's fixture WHOLESALE
(bring_up_qualifying_battle / qualifying_actor / pick_and_walk / straight_runs
/ the battle_halt_walk lever) rather than re-deriving path-finding - walk's
own qualifying rule (open ground, no door, contact-free - WV-D18) is a
STRICT SUPERSET of what a turn/kneel fixture needs, so one qualifying actor
drives all three ghost verbs. AI-neutral by construction (t=0, one player
side, no side transition) and contact-free per
session.actor_is_contact_free (walk_atom's own qualifying_actor already
enforces it, transitively, through session.actor_is_contact_free); door-free
is NOT required by THIS file's own contract - a door ev is not a ghost verb
and must be ignored by the stepper - but walk_atom's fixture happens to be
door-free anyway (WV-D18), so no door ev crosses the wire in any run below.

WHY EVERY ASSERTION READS THE CLIENT (never the host) - "the observing
machine" is always the CLIENT in this wave's two-seat topology, and this is
load-bearing, not a convenience: `CoopPump::enqueue()` (and therefore
`CoopPump::drainApplyQueue()` / `CoopDisplayQueue::onApplied()`, the ghost
stepper's ONE call site) is reached only from connectionTCP.cpp's
network-receive path - the HOST always executes an action directly through
real vanilla simulation and never loops its own emitted ev back through its
own apply queue (the mirror image of WV-D40 "no client-side local execution,
ever": the host never client-side-APPLIES its own already-executed action
either). So the ghost never runs on the host, regardless of which seat
originated the action - a HOST-origin turn/kneel/walk is exactly as
observable on the client's event_state counters as a CLIENT-origin one.

SESSION SHAPE (two bring-ups, in this order):
  test_ghost_verbs_e2e()      - ONE session: the OFF negative control FIRST
                                 (while ghostEnqueued is still literally 0 -
                                 see its own docstring for why the ORDER
                                 matters), then the ON positive controls
                                 (turn/kneel/walk), the halted-walk prefix
                                 proof, and the kneel-before-walk ordering
                                 case.
  test_desync_lever_still_detects() - a SEPARATE, freshly-booted session
                                 (SS2.8 "no partial repair": a desync-frozen
                                 battle has no path back, so this session is
                                 torn down, never reused - repro_atom_kneel.py's
                                 own test_forced_mismatch precedent).

Exit codes: 0 PASS - 2 FAIL - 3 SKIP (fixture exhausted - repro_atom_spot.py's
own 2026-09-03 SKIP-ruling precedent: a boot/route/candidate-set that the
underlying map geometry simply did not provide is not this packet's product
under test and must not count as a red).

Run:  python tools/coop_test/repro_ghost_stepper.py
"""

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: F401 (re-exported for parity with sibling repros)
import session
from session import assert_hash_clean

import repro_atom_walk as walkmod

EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3


class FixtureExhausted(Exception):
    """The underlying map/actor geometry did not provide what a phase needed
    (a routable multi-step walk, a genuine partial-prefix halt, a fresh
    qualifying TU-rich actor) - repro_atom_spot.py's own precedent: this is a
    SKIP, not a product FAIL."""


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def units_by_id(resp):
    return {u["id"]: u for u in resp.get("units", [])}


def pick_fresh_actor(host, soldier_ids, exclude_ids, min_tu=45):
    """A DIFFERENT client-owned soldier (from the fixture's own `soldier_ids`
    list - repro_atom_walk.py's drive_to_battlescape seats several so a
    later phase never has to share one actor's dwindling TU with an earlier
    one) with at least `min_tu` TU left, no door within
    walkmod.WALK_DOOR_RADIUS, and contact-free (session.actor_is_contact_free).

    WHY THIS EXISTS: this file drives turn+kneel+kneel-restore+a multi-step
    walk on ONE actor before halted_walk_prefix()/kneel_before_walk_ordering()
    run - both of which ALSO need a multi-step walk, and a soldier's TU budget
    (~50-70) does not comfortably cover all of that on one unit. Every seated
    soldier started in the SAME tight cluster the original qualifying_actor()
    verified (all of them within a few tiles of it), so the SAME
    nearest-alien-distance margin applies - this is a re-check, not a
    re-roll: no second boot, no second lobby flow."""
    st = battle_state(host)
    candidates = [u for u in st["units"]
                  if u.get("soldierId") in soldier_ids and u["id"] not in exclude_ids
                  and not u.get("isOut") and u.get("tu", 0) >= min_tu]
    candidates.sort(key=lambda u: -u["tu"])
    for u in candidates:
        if walkmod.has_door_within(host, u["x"], u["y"], u["z"], walkmod.WALK_DOOR_RADIUS):
            continue
        if not session.actor_is_contact_free(st, u, "ghost-fresh-actor"):
            continue
        return u
    return None


def unit_of(gc, uid):
    return units_by_id(battle_state(gc))[uid]


def set_ghost_option(gc, value):
    """Round-trip set (TestServer.cpp's coopGhostStepper set_option branch,
    W1-P12): asserts the write actually landed rather than trusting the
    request bounced back unchanged."""
    r = gc.ok({"cmd": "set_option", "name": "coopGhostStepper", "value": value})
    assert r.get("value") == value, f"set_option coopGhostStepper did not stick: {r}"
    return r


def read_ghost_option(gc):
    r = gc.ok({"cmd": "set_option", "name": "coopGhostStepper"})  # no "value" = pure read
    return r.get("value")


def event_seq_baseline(client):
    return event_state(client).get("lastSeqApplied", 0)


def wait_action_settled(host, client, baseline, timeout=15):
    """queueDepth 0 on BOTH machines AND the client's lastSeqApplied has
    advanced past `baseline` - the repro_atom_kneel.py precedent, generalized
    (this file's actions span all three verbs)."""
    def settled():
        hs = event_state(host)
        cs = event_state(client)
        return bool(hs.get("ok") and cs.get("ok")
                    and hs.get("queueDepth") == 0 and cs.get("queueDepth") == 0
                    and cs.get("lastSeqApplied", 0) > baseline)
    client.wait_for("action settled (new seq applied, queueDepth 0 on both machines)",
                     settled, timeout=timeout)


def wait_ghost_drained(client, expect_completed, timeout=10):
    """Waits until event_state.ghostCompleted has reached at least
    `expect_completed` AND ghostQueueDepth is back to 0 - i.e. every ghost
    this call is waiting on has finished its interpolation and been popped
    (CoopGhost::advance(), driven every frame from
    BattlescapeState::think()'s per-frame path, step 5). The (6e) constants
    cap any single ghost well under 1s (kneel 100ms, one walk_step 120ms, a
    full 180-degree turn 4*60=240ms), so the default timeout is generous."""
    def done():
        es = event_state(client)
        return es if (es.get("ok")
                      and es.get("ghostCompleted", 0) >= expect_completed
                      and es.get("ghostQueueDepth", 0) == 0) else None
    return client.wait_for(
        f"ghost queue drains to 0 with ghostCompleted >= {expect_completed}",
        done, timeout=timeout)


def do_turn(host, client, actor_id):
    """A 180-degree body turn (guaranteed to actually move - never a
    turretOnly no-op) via battle_intent. Returns (host_unit_after,
    client_unit_after) post-settle."""
    before = unit_of(client, actor_id)
    to_dir = (before["direction"] + 4) % 8
    baseline = event_seq_baseline(client)
    resp = client.ok({"cmd": "battle_intent", "kind": "turn", "actor": actor_id, "toDir": to_dir})
    assert resp.get("iseq"), f"turn intent did not ship: {resp}"
    wait_action_settled(host, client, baseline)
    return unit_of(host, actor_id), unit_of(client, actor_id)


def do_kneel(host, client, actor_id):
    """Toggles kneeled via battle_intent. Returns (host_unit_after,
    client_unit_after) post-settle."""
    before = unit_of(client, actor_id)
    baseline = event_seq_baseline(client)
    resp = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_id,
                       "kneel": not before["kneeled"]})
    assert resp.get("iseq"), f"kneel intent did not ship: {resp}"
    wait_action_settled(host, client, baseline)
    return unit_of(host, actor_id), unit_of(client, actor_id)


def pick_and_walk_resilient(host, client, actor_id, what, soldier_ids=None, used=None,
                             max_actor_retries=2, **kw):
    """walkmod.pick_and_walk(), retried on a FRESH actor when the assigned
    one cannot route ANYTHING (measured empirically to be a per-ACTOR
    position problem far more often than a per-battle one). Returns
    (result, actor_id_actually_used); result is None only after every retry
    is exhausted."""
    tried = [actor_id]
    while True:
        result = walkmod.pick_and_walk(host, client, tried[-1], what, **kw)
        if result is not None or soldier_ids is None or len(tried) > max_actor_retries:
            return result, tried[-1]
        replacement = pick_fresh_actor(host, soldier_ids, exclude_ids=set(tried) | (used or set()))
        if replacement is None:
            return None, tried[-1]
        if used is not None:
            used.add(replacement["id"])
        print(f"[repro_ghost_stepper] {what}: unit {tried[-1]} could not route any walk - "
              f"retrying on a fresh unit {replacement['id']} (tu={replacement['tu']})")
        tried.append(replacement["id"])


def negative_control(host, client, actor_id, soldier_ids=None, used=None):
    """DONE-WHEN 6 / SPEC 7(f)'s "ON/OFF equivalence" negative control - run
    FIRST, deliberately, while event_state.ghostEnqueued is still literally 0
    on a freshly-booted battle (it is a monotone per-battle counter,
    CoopGhost::reset() only ever runs at battle teardown), so "assert ...
    ghostEnqueued == 0" (the packet text's own exact wording) is the LITERAL
    counter value, not a before/after delta computed against a nonzero
    baseline. Running the positive controls first would make a literal-zero
    assertion impossible to satisfy honestly; this file avoids that instead
    of reinterpreting the assertion.

    `soldier_ids`/`used` (optional): when given, a `pick_and_walk()` failure
    on `actor_id` is retried on a FRESH actor from the pool (up to twice)
    before this is treated as fixture exhaustion - measured empirically the
    single flakiest step in this file (an actor that cannot route even a
    1-tile walk is a per-ACTOR position problem, not a per-BATTLE one, so a
    different actor routinely succeeds where the first could not)."""
    for name, value in (("coopGhostStepper", False),):
        set_ghost_option(host, value)
        set_ghost_option(client, value)
    assert read_ghost_option(client) is False, "coopGhostStepper did not read back False on client"

    es0 = event_state(client)
    assert es0.get("ghostEnqueued", -1) == 0, (
        f"negative control must start from a genuinely fresh ghost counter, got {es0}")

    tried = [actor_id]
    result = None
    while True:
        do_turn(host, client, tried[-1])
        do_kneel(host, client, tried[-1])
        result = walkmod.pick_and_walk(host, client, tried[-1], "negative control",
                                        lengths=(1, 2, 3), min_steps=1, require_unhalted=True,
                                        rounds=6)
        if result is not None or soldier_ids is None or len(tried) >= 3:
            break
        replacement = pick_fresh_actor(host, soldier_ids, exclude_ids=set(tried) | (used or set()))
        if replacement is None:
            break
        if used is not None:
            used.add(replacement["id"])
        print(f"[repro_ghost_stepper] negative_control: unit {tried[-1]} could not route any "
              f"walk - retrying on a fresh unit {replacement['id']} (tu={replacement['tu']})")
        tried.append(replacement["id"])

    if result is None:
        raise FixtureExhausted(
            f"negative control: fixture could not produce any unhalted walk on any of {tried}")
    hw, cw = result
    assert hw.get("steps"), "negative control: the walk fixture produced no executed steps at all"

    es1 = event_state(client)
    assert es1.get("ghostEnqueued", -1) == 0, (
        f"OPTION OFF still enqueued a ghost - ghostEnqueued={es1.get('ghostEnqueued')} "
        f"after a turn+kneel+{len(hw['steps'])}-step walk with coopGhostStepper=false")
    assert_hash_clean(host, client, full=True, what="negative control (option OFF)")
    print(f"PASS negative_control: coopGhostStepper=false enqueued NOTHING across a turn, a "
          f"kneel and a {len(hw['steps'])}-step walk (ghostEnqueued stayed at 0); hash_now full "
          "EQUAL")
    return es1  # hash pair is asserted above; returned for the report


def positive_turn(host, client, actor_id):
    before = event_state(client)
    enq0, comp0 = before.get("ghostEnqueued", 0), before.get("ghostCompleted", 0)

    hu, cu = do_turn(host, client, actor_id)
    assert hu["direction"] == cu["direction"], (
        f"host/client direction differ after the turn: host={hu['direction']} client={cu['direction']}")

    mid = event_state(client)
    assert mid.get("ghostEnqueued", 0) == enq0 + 1, (
        f"a partner TURN must raise ghostEnqueued by EXACTLY 1: before={enq0} after={mid.get('ghostEnqueued')}")

    wait_ghost_drained(client, comp0 + 1)
    hh, ch = assert_hash_clean(host, client, full=True, what="post-turn (ghost ON)")
    print(f"PASS positive_turn: ghostEnqueued {enq0}->{enq0+1}, ghostCompleted reached "
          f"{comp0+1}, direction {cu['direction']}, {len(hh)}/{len(hh)} buckets EQUAL")
    return hh, ch


def positive_kneel(host, client, actor_id):
    before = event_state(client)
    enq0, comp0 = before.get("ghostEnqueued", 0), before.get("ghostCompleted", 0)

    hu, cu = do_kneel(host, client, actor_id)
    assert hu["kneeled"] == cu["kneeled"], (
        f"host/client kneeled differ after the kneel: host={hu['kneeled']} client={cu['kneeled']}")

    mid = event_state(client)
    assert mid.get("ghostEnqueued", 0) == enq0 + 1, (
        f"a partner KNEEL must raise ghostEnqueued by EXACTLY 1: before={enq0} after={mid.get('ghostEnqueued')}")

    wait_ghost_drained(client, comp0 + 1)
    hh, ch = assert_hash_clean(host, client, full=True, what="post-kneel (ghost ON)")
    print(f"PASS positive_kneel: ghostEnqueued {enq0}->{enq0+1}, ghostCompleted reached "
          f"{comp0+1}, kneeled={cu['kneeled']}, {len(hh)}/{len(hh)} buckets EQUAL")

    # Restore the ORIGINAL (not-kneeled) state: kneel_before_walk_ordering()
    # is this file's own dedicated test for "a walk that begins kneeled" -
    # positive_walk() right after this call wants a clean, not-kneeled
    # baseline so its own "one ghost per walk_step, nothing else" assertion
    # holds without an extra stand-up kneel ghost folded in. Settled (not just
    # sent) before returning, so the counters positive_walk() samples next are
    # not mid-flight.
    do_kneel(host, client, actor_id)
    wait_ghost_drained(client, comp0 + 2)
    return hh, ch


def positive_walk(host, client, actor_id, soldier_ids=None, used=None):
    before = event_state(client)
    enq0, comp0 = before.get("ghostEnqueued", 0), before.get("ghostCompleted", 0)
    seq0 = before.get("lastSeqApplied", 0)

    result, actor_id = pick_and_walk_resilient(
        host, client, actor_id, "positive_walk", soldier_ids=soldier_ids, used=used,
        lengths=(2, 3, 1), min_steps=1, require_unhalted=True, rounds=6)
    if result is None:
        raise FixtureExhausted("positive_walk: fixture could not produce any unhalted walk")
    hw, cw = result
    steps = hw.get("steps") or []
    assert steps, "positive_walk: the settled walk executed zero steps"

    # EXPECTED is every turn/kneel/walk_step ev since seq0, NOT just the
    # FINAL accepted walk's own `steps` - TWO reasons, both legitimate and
    # both real ghost-worthy evs this assertion must not miss:
    #   (1) pick_and_walk() (repro_atom_walk.py, opaque here) can execute and
    #       reject an earlier HALTED candidate before landing the unhalted
    #       one this function asserts on - that earlier candidate's steps
    #       are real walk_step evs that really did enqueue a ghost each;
    #   (2) vanilla turns a unit to face its path's first step BEFORE it
    #       walks whenever the actor is not already facing that way - a real
    #       `turn` ev (and, if the actor started kneeled, a real `kneel`
    #       stand-up ev too - the W1-P9 follow-up kneel_before_walk_ordering()
    #       covers on its own) - each of which enqueues its OWN ghost, same
    #       as any other partner action.
    # Re-deriving the true expected count from the event ring (which - unlike
    # the ghost counters - carries a seq/actionId per entry) is what makes
    # this assertion correct regardless of how many attempts pick_and_walk()
    # needed and regardless of the actor's incoming facing/kneeled state.
    log = client.cmd({"cmd": "event_log", "tail": 200}).get("events", [])
    ghost_kinds = ("turn", "kneel", "walk_step")
    expected = sum(1 for e in log if e.get("seq", 0) > seq0 and e.get("kind") in ghost_kinds)
    walk_step_count = sum(1 for e in log if e.get("seq", 0) > seq0 and e.get("kind") == "walk_step")
    assert walk_step_count >= len(steps), (
        f"positive_walk: event_log shows only {walk_step_count} walk_step ev(s) since seq "
        f"{seq0}, fewer than the accepted walk's own {len(steps)} - test bookkeeping bug, not "
        "a product one (the ring should always see AT LEAST the accepted walk's steps)")

    mid = event_state(client)
    got = mid.get("ghostEnqueued", 0) - enq0
    assert got == expected, (
        f"a WALK must enqueue exactly one ghost per turn/kneel/walk_step ev: expected {expected} "
        f"(event_log turn+kneel+walk_step count since this phase began), got a ghostEnqueued "
        f"delta of {got}")

    wait_ghost_drained(client, comp0 + expected)
    hh, ch = assert_hash_clean(host, client, full=True, what="post-walk (ghost ON)")
    print(f"PASS positive_walk: {len(steps)}-step accepted walk ({walk_step_count} walk_step "
          f"ev(s), {expected} ghost-worthy ev(s) total including any pre-walk turn/kneel) "
          f"enqueued exactly {expected} ghost(s) (ghostEnqueued {enq0}->{enq0+expected}), all "
          f"completed, {len(hh)}/{len(hh)} buckets EQUAL")
    return hh, ch


def halted_walk_prefix(host, client, actor_id, soldier_ids=None, used=None):
    """SPEC 7(f): "a HALTED walk animates only the executed prefix" -
    ghostEnqueued must equal len(lastWalk['steps']) (the EXECUTED prefix),
    never the intent's planned path length. Uses the SAME battle_halt_walk
    one-shot TestServer lever repro_atom_walk.py's own PHASE 3 uses.

    `soldier_ids`/`used` (optional): retries on a FRESH actor (up to twice)
    when EVERY candidate for the current one fails to produce a genuine
    partial-prefix halt - pick_and_walk_resilient()'s own precedent, for the
    same reason (a per-actor position problem, not a per-battle one)."""
    tried = [actor_id]
    hw = cw = None
    enq0 = comp0 = seq0 = None  # captured freshly per ATTEMPT - see below for why
    cands_tried_total = 0
    while True:
        actor_id = tried[-1]
        # WIDE length set (repro_atom_walk.py's own PHASE 3 uses just
        # (WALK_RUN, 2) = (3, 2)): a "3-tile straight run" destination can
        # still resolve to a SHORT (even 1-step) pathfinder route around
        # obstacles, so this needs enough candidates that at least one keeps
        # plannedLen>=2 - the property under test (a genuine PARTIAL-prefix
        # halt) is meaningless below that.
        cands = walkmod.walk_candidates(host, actor_id, lengths=(5, 4, 3, 2))
        cands_tried_total += len(cands)

        for dest in cands:
            # Snapshotted PER ATTEMPT, not once at the top of the function: an
            # earlier candidate that ran to FULL completion without halting
            # (tried and rejected below, but very much executed and very much
            # ghost-enqueued) must not be folded into the delta this function
            # ultimately asserts for the ONE candidate that actually produced
            # the halt under test.
            attempt_es = event_state(client)
            enq_attempt = attempt_es.get("ghostEnqueued", 0)
            comp_attempt = attempt_es.get("ghostCompleted", 0)
            seq_attempt = attempt_es.get("lastSeqApplied", 0)

            prev = walkmod.walk_action_id(host)
            host.ok({"cmd": "battle_halt_walk"})  # armed BEFORE the send - see PHASE 3's own comment
            resp = walkmod.send_walk(client, actor_id, dest)
            if not resp.get("iseq"):
                continue  # nothing left this machine (no route / a first-step reserve refusal)
            iseq = resp["iseq"]

            # DENY-AWARE wait (repro_atom_walk.py's own send_walk_outcome()
            # precedent): a candidate can legitimately come back denied
            # (`cost_changed` on an actor this file's own earlier tests have
            # already spent TU on) rather than executed - waiting on
            # wait_walk_settled() alone for such a candidate would hang for
            # its full timeout instead of moving on to the next one.
            deadline = time.time() + 15
            outcome = None
            while time.time() < deadline:
                hw_poll = walkmod.last_walk(host)
                if (hw_poll.get("actionId", 0) != prev and hw_poll.get("active") is False
                        and hw_poll.get("restate")):
                    outcome = "walk"
                    break
                ld = event_state(client).get("lastDeny")
                if ld and ld.get("iseq") == iseq:
                    outcome = "deny"
                    break
                time.sleep(0.05)
            if outcome != "walk":
                continue  # denied, or neither within the window - try the next candidate

            walkmod.settle_reveal(host, client)
            hw, cw = walkmod.last_walk(host), walkmod.last_walk(client)
            if hw["plannedLen"] >= 2 and 0 < len(hw["steps"]) < hw["plannedLen"]:
                enq0, comp0, seq0 = enq_attempt, comp_attempt, seq_attempt
                break
            hw = cw = None  # this candidate ran but did not produce a genuine partial halt - keep trying

        if hw is not None or soldier_ids is None or len(tried) > 2:
            break
        replacement = pick_fresh_actor(host, soldier_ids, exclude_ids=set(tried) | (used or set()))
        if replacement is None:
            break
        if used is not None:
            used.add(replacement["id"])
        print(f"[repro_ghost_stepper] halted_walk_prefix: unit {actor_id} produced no genuine "
              f"partial-prefix halt across {len(cands)} candidate(s) - retrying on a fresh unit "
              f"{replacement['id']} (tu={replacement['tu']})")
        tried.append(replacement["id"])

    if hw is None:
        raise FixtureExhausted(
            f"halted_walk_prefix: could not produce a genuine partial-prefix halt from any of "
            f"{cands_tried_total} candidate(s) across unit(s) {tried}")

    executed = hw["steps"]

    # EXPECTED counts turn/kneel/walk_step evs since the WINNING attempt's own
    # seq baseline, not just len(executed) - the same pre-walk-turn/stand-up
    # reasoning as positive_walk()'s own doc comment: vanilla turns (and, if
    # kneeled, stands up) the actor to face the path BEFORE walking whenever
    # needed, and each of those is its own real ghost-worthy ev.
    log = client.cmd({"cmd": "event_log", "tail": 200}).get("events", [])
    ghost_kinds = ("turn", "kneel", "walk_step")
    expected = sum(1 for e in log if e.get("seq", 0) > seq0 and e.get("kind") in ghost_kinds)
    walk_step_count = sum(1 for e in log if e.get("seq", 0) > seq0 and e.get("kind") == "walk_step")
    assert walk_step_count == len(executed), (
        f"halted_walk_prefix: event_log shows {walk_step_count} walk_step ev(s) since the "
        f"winning attempt began, expected exactly the executed prefix's {len(executed)} - test "
        "bookkeeping bug, not a product one")

    mid = event_state(client)
    got = mid.get("ghostEnqueued", 0) - enq0
    assert got == expected, (
        f"a HALTED walk must animate only the EXECUTED prefix plus any real pre-walk turn/kneel "
        f"({expected} ghost-worthy ev(s) total, {len(executed)} of them walk_step), never the "
        f"intent's planned length ({hw['plannedLen']}) - ghostEnqueued delta was {got}")

    wait_ghost_drained(client, comp0 + expected)
    assert_hash_clean(host, client, full=True, what="post-halted-walk (ghost ON)")
    print(f"PASS halted_walk_prefix: a {hw['plannedLen']}-step plan halted after "
          f"{len(executed)} executed step(s) (reason={hw['restate']['reason']!r}); ghostEnqueued "
          f"advanced by exactly {expected} (the executed prefix plus any real pre-walk turn/kneel), "
          f"never the planned {hw['plannedLen']}; hash_now full EQUAL")


def kneel_before_walk_ordering(host, client, actor_id):
    """W1-P9 follow-up (2026-09-03, cited verbatim in SPEC 7(b)): "a kneel ev
    now arrives BEFORE the first walk_step of a walk that began kneeled ...
    Animate it as the stand-up flip it is; it is NOT a walk-stream
    violation." Kneels the actor DOWN if it is not already, orders a walk,
    and asserts the CLIENT's own event_log shows the stand-up `kneel` kind
    strictly before the walk's `walk_step` kinds, in seq order."""
    cu = unit_of(client, actor_id)
    if not cu["kneeled"]:
        do_kneel(host, client, actor_id)
        cu = unit_of(client, actor_id)
    assert cu["kneeled"], "kneel_before_walk_ordering: could not get the actor kneeled to begin with"

    seq_before = event_seq_baseline(client)
    result = walkmod.pick_and_walk(host, client, actor_id, "kneel-then-walk",
                                    lengths=(1, 2, 3), min_steps=1, require_unhalted=True,
                                    rounds=6)
    if result is None:
        raise FixtureExhausted("kneel_before_walk_ordering: fixture could not produce an unhalted walk")
    hw, cw = result
    assert not cw["restate"]["halted"], "kneel_before_walk_ordering: the walk halted - not the case under test"

    hu = unit_of(host, actor_id)
    assert not hu["kneeled"], (
        "kneel_before_walk_ordering: the actor is still kneeled after a completed walk - "
        "vanilla always stands a unit up before it walks")

    log = client.cmd({"cmd": "event_log", "tail": 200}).get("events", [])
    relevant = [e for e in log if e.get("seq", 0) > seq_before]
    kneel_idxs = [i for i, e in enumerate(relevant) if e.get("kind") == "kneel"]
    walk_idxs = [i for i, e in enumerate(relevant) if e.get("kind") == "walk_step"]
    assert kneel_idxs, (
        f"kneel_before_walk_ordering: no 'kneel' ev observed after seq {seq_before} in "
        f"{relevant} - the stand-up must ride its own kneel ev (W1-P9 follow-up)")
    assert walk_idxs, f"kneel_before_walk_ordering: no 'walk_step' ev observed: {relevant}"
    assert max(kneel_idxs) < min(walk_idxs), (
        f"the stand-up 'kneel' ev must precede every 'walk_step' ev in the seq stream - "
        f"kneel positions {kneel_idxs}, walk_step positions {walk_idxs}: {relevant}")

    log_path = os.path.join(client.user_dir, "openxcom.log")
    with open(log_path, "r", errors="replace") as f:
        client_log = f.read()
    assert "stream violation" not in client_log.lower(), (
        "kneel_before_walk_ordering: the client log recorded a stream violation - the "
        "stand-up-before-walk case must be treated as ordinary, not an error")

    print(f"PASS kneel_before_walk_ordering: stand-up 'kneel' ev (position "
          f"{max(kneel_idxs)}) precedes every 'walk_step' ev (first at position "
          f"{min(walk_idxs)}) in the seq stream; no stream-violation logged")


def test_ghost_verbs_e2e():
    try:
        host, client, actor, soldier_ids = walkmod.bring_up_qualifying_battle()
    except RuntimeError as e:
        raise FixtureExhausted(str(e)) from e
    try:
        actor_id = actor["id"]
        assert_hash_clean(host, client, full=True, what="at t=0 (pre-action)")

        # ONE DEDICATED ACTOR PER WALK-CONSUMING PHASE (pick_fresh_actor()'s
        # own doc comment explains why): a soldier's TU budget (~50-70) does
        # not comfortably cover more than one multi-step walk, and this file
        # drives FOUR separate ones (negative_control, positive_walk,
        # halted_walk_prefix, kneel_before_walk_ordering) - the fixture seats
        # exactly enough soldiers (SEAT1_SOLDIERS=5) for one each, with
        # `actor` itself reserved for the two WALK-FREE phases
        # (positive_turn/positive_kneel, which spend only a few TU each).
        # `used` excludes ONLY `actor_id` itself (positive_turn/
        # positive_kneel's dedicated actor, and later reused by
        # kneel_before_walk_ordering - its state must stay predictable). It
        # deliberately does NOT grow as each phase claims a soldier: a
        # soldier a COMPLETED earlier phase touched is perfectly reusable by
        # a later one as long as it currently has enough TU
        # (pick_fresh_actor()'s own live re-check) - the fixture's
        # SEAT1_SOLDIERS=5 pool is comfortable for that, but NOT for five
        # phases each permanently claiming a distinct soldier plus retries on
        # top, which starved late phases of any spare soldier at all
        # (measured: repeated SKIPs on the LAST phase to run).
        used = {actor_id}

        def next_actor(tag):
            u = pick_fresh_actor(host, soldier_ids, exclude_ids=used)
            if u is None:
                raise FixtureExhausted(f"no fresh, qualifying, TU-rich actor left for {tag}")
            print(f"[repro_ghost_stepper] {tag} will use unit {u['id']} (tu={u['tu']})")
            return u["id"]
        neg_actor_id = next_actor("negative_control")
        off_es = negative_control(host, client, neg_actor_id, soldier_ids=soldier_ids, used=used)

        # Option back ON (the default - WV-D5-style explicit re-arm rather
        # than assuming a prior branch left it that way).
        set_ghost_option(host, True)
        set_ghost_option(client, True)
        assert read_ghost_option(client) is True, "coopGhostStepper did not read back True on client"

        on_hh, on_ch = positive_turn(host, client, actor_id)
        positive_kneel(host, client, actor_id)

        walk_actor_id = next_actor("positive_walk")
        positive_walk(host, client, walk_actor_id, soldier_ids=soldier_ids, used=used)

        halt_actor_id = next_actor("halted_walk_prefix")
        halted_walk_prefix(host, client, halt_actor_id, soldier_ids=soldier_ids, used=used)

        # REUSES `actor_id` (positive_turn/positive_kneel's own actor)
        # instead of claiming a further fresh soldier: it has spent TU on
        # only three cheap actions (a turn, a kneel, positive_kneel's own
        # restore-kneel) and positive_kneel() already leaves it back in its
        # ORIGINAL not-kneeled state, so it is exactly as usable here as a
        # brand-new soldier - and not claiming one leaves more of the
        # SEAT1_SOLDIERS=5 pool free for the walk-heavy phases' own
        # retry-on-a-fresh-actor paths above, which need it far more.
        kneel_before_walk_ordering(host, client, actor_id)

        final_es = event_state(client)
        print(f"PASS test_ghost_verbs_e2e: ALL scenarios passed in one session "
              f"(final ghostEnqueued={final_es.get('ghostEnqueued')}, "
              f"ghostCompleted={final_es.get('ghostCompleted')}, "
              f"ghostQueueDepth={final_es.get('ghostQueueDepth')})")
        print(f"ON/OFF BUCKET-EQUALITY PAIR: OFF-pass ghostEnqueued={off_es.get('ghostEnqueued')} "
              f"(hash_now full EQUAL, asserted in negative_control); ON-pass hash_now full: "
              f"host={on_hh} client={on_ch}")
    finally:
        host.shutdown()
        client.shutdown()


def corrupted_unit_id(host, client):
    """repro_atom_kneel.py's own corrupted_unit_id() precedent: runs
    corrupt_bucket{unitsStats} on the HOST and diffs per-unit TU to find
    which unit id it touched, so the caller can act on a DIFFERENT unit (an
    absolute-value applier on the SAME unit would resync the corruption the
    instant that unit's own action applied, masking it)."""
    before = {u["id"]: u["tu"] for u in host.cmd({"cmd": "battle_state"})["units"]}
    resp = host.ok({"cmd": "corrupt_bucket", "name": "unitsStats"})
    assert resp.get("ok"), f"corrupt_bucket failed: {resp}"
    after = {u["id"]: u["tu"] for u in host.cmd({"cmd": "battle_state"})["units"]}
    diffs = [uid for uid, tu in after.items() if before.get(uid) != tu]
    assert len(diffs) == 1, f"corrupt_bucket touched {len(diffs)} unit(s), expected exactly 1: {diffs}"
    return diffs[0]


SDLK_TAB = 9   # Options::keyBattleNextUnit default
SDLK_K = 107   # Options::keyBattleKneel default (SDLK_k, Options.cpp:337)


def select_away_from(host, avoid_id, max_tabs=12):
    """repro_atom_kneel.py's own select_away_from() precedent: Tab-cycles the
    HOST's own selection until it lands on a HOST-OWNED unit (coop==0) other
    than `avoid_id` - the battle's inherited initial selection is not itself
    seat-filtered, so a naive first-read can land on a CLIENT-owned unit the
    host does not command."""
    for _ in range(max_tabs):
        st = host.cmd({"cmd": "battle_state"})
        sel = st.get("selectedId")
        if sel and sel != avoid_id:
            unit = units_by_id(st).get(sel)
            if unit and unit.get("coop") == 0:
                return sel
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.1)
    raise AssertionError(f"could not select a HOST-OWNED unit other than {avoid_id} within {max_tabs} tabs")


def test_desync_lever_still_detects():
    """SPEC 7(f)'s last bullet: "desync levers still detect: corrupt_bucket
    unitsStats with the stepper ON still freezes the client and writes a
    bundle." A SEPARATE, freshly-booted session (SS2.8 "no partial repair" -
    repro_atom_kneel.py's own test_forced_mismatch precedent): a
    desync-frozen battle has no path back, so this session is torn down,
    never reused.

    THE HOST'S OWN ACTION IS A REAL KEYPRESS, NOT battle_intent
    (repro_atom_kneel.py's own precedent): `battle_intent` is the CLIENT's
    network-intent path (admitted, validated, then executed BY THE HOST) -
    the host itself never "intents" anything, it executes directly, so its
    local action must be driven the same way a real player would
    (inject_input), exactly like every other host-origin action in this
    file's sibling repros."""
    import glob

    try:
        host, client, actor, soldier_ids = walkmod.bring_up_qualifying_battle()
    except RuntimeError as e:
        raise FixtureExhausted(str(e)) from e
    try:
        assert read_ghost_option(client) is True, "coopGhostStepper must default to ON for this proof"
        assert_hash_clean(host, client, full=True, what="at t=0 (pre-corruption)")

        corrupted_id = corrupted_unit_id(host, client)

        # A KNEEL on a DIFFERENT unit via the HOST's own local keypress
        # (origin=host) so the ghost-carrying ev is exactly the one that must
        # trip the freeze - corrupted_unit_id()'s own doc comment explains why
        # it must not be the corrupted unit itself.
        kneel_actor_id = select_away_from(host, corrupted_id)
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})

        def client_desynced():
            return event_state(client).get("desyncSeen") or None

        client.wait_for("client event_state.desyncSeen becomes true", client_desynced, timeout=15)
        es = event_state(client)
        assert es.get("desyncSeen") is True, f"client did not latch desyncSeen: {es}"

        bundle_glob = os.path.join(client.user_dir, "desync-reports", "desync-*.zip")
        bundles = glob.glob(bundle_glob)
        assert bundles, f"no desync bundle file found under {bundle_glob}"

        print(f"PASS test_desync_lever_still_detects: corrupt_bucket(unitsStats) on the host "
              f"(unit {corrupted_id}) followed by a ghost-carrying host-origin kneel (unit "
              f"{kneel_actor_id}) still froze the client (desyncSeen=True) and wrote a bundle: "
              f"{bundles[0]}")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    test_ghost_verbs_e2e()
    test_desync_lever_still_detects()
    print("ALL W1-P12 GHOST STEPPER TESTS PASSED")


if __name__ == "__main__":
    # Exit-code convention verbatim from repro_atom_spot.py (2026-09-03 SKIP
    # ruling): 0 PASS, 2 FAIL (a red), 3 SKIP (fixture exhausted - not a red).
    try:
        main()
        sys.exit(EXIT_PASS)
    except FixtureExhausted as e:
        print(f"\nrepro_ghost_stepper: SKIP (fixture exhausted)\n{e}")
        sys.exit(EXIT_SKIP)
    except (AssertionError, TimeoutError) as e:
        print(f"\nrepro_ghost_stepper: FAIL\n{type(e).__name__}: {e}")
        print("")
        print("--- traceback (classification aid) ---")
        traceback.print_exc()
        sys.exit(EXIT_FAIL)
