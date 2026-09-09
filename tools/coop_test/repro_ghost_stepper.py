"""W1-P12 (WAVE1-RUNBOOK.md SPEC 7, ruling D-3 = WV-D27/WV-D49/A4): the S3
GHOST STEPPER - a partner's turn/kneel/walk ANIMATES on the observing machine
instead of snapping, display-only, without moving a single hash bucket.

FIXTURE (SPEC RW-S4 REV E.47, owner D36 2026-09-09 - REWRITTEN from scratch on
the LIGHTNING-CRAFT ROOF: self-contained, deterministic, map-independent, no
search, no SKIP). The player's Lightning craft has a flat roof except a raised
portion at the very centre. Each fresh actor is teleported (battle_teleport_unit,
applied to BOTH machines through place_deterministic's hash gate) to a baked
OFF-CENTRE roof lane - a straight, flat, unobstructed run along the craft's long
(x) axis - so it has an unobstructed multi-step walk 100% of the time on any map,
because the craft geometry is invariant and only its map placement offset varies.
The lane is located each run from the craft's own LIGHTNIN door
(session.lightning_door), never from absolute coordinates: roof_z = door_z +
ROOF_DZ, lane_y = door_y + LANE_DY, lane_x0 = door_x + LANE_DX_START, walked by
ARITHMETIC (start + n*D), never by scanning. Hostiles/neutrals are corner-placed
far away (WV-D88) so the roof stays contact-free even after a walk recomputes FOV.
The baked constants were measured once by the orchestrator's R1 (three boots, door
at y=25/5/15, identical door-relative craft-roof geometry, hash_now{full} EQUAL on
both machines after every teleport and a 6-step walk). A premise that no longer
holds (a lane tile that is not flat/walkable/free) is a RED naming it (exit 2),
never a SKIP (WV-D100).

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

SESSION SHAPE (two boots, in this order):
  test_ghost_verbs_e2e()      - ONE session: the OFF negative control FIRST
                                 (while ghostEnqueued is still literally 0),
                                 then the ON positive turn/kneel, the
                                 multi-step walk, the halted-walk prefix, and
                                 the kneel-before-walk ordering case - each on
                                 its own fresh client soldier teleported to
                                 the baked roof lane.
  test_desync_lever_still_detects() - a SEPARATE, freshly-booted session
                                 (SS2.8 "no partial repair"), seated to leave
                                 HOST-owned units, proving the desync lever
                                 still fires.

Exit codes: 0 PASS - 2 FAIL (a red, including a broken fixture premise). There
is NO exit-3 SKIP - the roof fixture always provides the lane, and a missing
lane is a RED, not a skip (SPEC RW-S4 REV E.47, WV-D100).

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
from repro_atom_walk import bring_up_lobby

EXIT_PASS, EXIT_FAIL = 0, 2

COOP_SEAT_0 = 0

# SPEC RW-S4 REV E.47: the Lightning craft roof, located each run from the craft's
# own LIGHTNIN door (map-independent; only the craft's placement offset varies).
# Measured by orch38 R1 on three boots (door at y=25 / y=5 / y=15) - identical
# door-relative craft-roof geometry, hash_now{full} EQUAL on both machines after
# every teleport and a 6-step walk.
ROOF_DZ        = 1       # roof_z = door_z + 1
LANE_DY        = 2       # lane row (off-centre), lane_y = door_y + 2   (a proven clear run-7 row)
LANE_DX_START  = -7      # lane_x0 = door_x - 7
ROOF_LANE_LEN  = 7       # 7 tiles => up to a 6-step walk
PARK_DY        = -2      # parking row (off-centre, opposite side; also a proven clear run-7 row)
D              = (1, 0)  # walk east along the craft long (x) axis


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def units_by_id(resp):
    return {u["id"]: u for u in resp.get("units", [])}


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


# ----- roof fixture (SPEC RW-S4 REV E.47) ---------------------------------

def bring_up_roof_battle(seat_count, tag):
    """Boot the two-instance skirmish on the Lightning, corner-place hostiles/
    neutrals far away (WV-D88) so the roof stays contact-free, and return
    (host, client, client_ids, host_ids, door).

    `seat_count` (R1 F89): the base soldier pool is 6; `seat_count` stamps N
    of them to the CLIENT (coop seat 1), leaving the rest on the HOST (coop
    seat 0) - session.drive_to_battlescape's own seat loop stops the moment
    a seat attempt fails, so seat_count directly controls the split."""
    port = str(48448)
    host_dir = make_user_dir(f"repro_ghost_stepper_host_{tag}")
    client_dir = make_user_dir(f"repro_ghost_stepper_client_{tag}")
    host = GameClient("host", 49480, host_dir)
    client = GameClient("client", 49481, client_dir)
    seated = {}
    try:
        bring_up_lobby(host, client, port)
        session.drive_to_battlescape(
            host, client, seated, seat_count=seat_count,
            pre_seat=lambda h: h.ok({"cmd": "newbattle_craft", "type": "STR_LIGHTNING"}))

        door, mapX, mapY = session.lightning_door(host)

        # WV-D88 corner placement (byte-for-byte the block
        # repro_atom_walk.bring_up_pinned_battle uses): hostiles -> the
        # squad's own corner, neutrals -> the opposite one, so the roof stays
        # contact-free.
        st = battle_state(host)
        players = [u for u in st["units"] if u.get("faction") == session.FACTION_PLAYER
                   and not u.get("isOut")]
        assert players, "FIXTURE PREMISE BROKE: bring_up_roof_battle: no live player unit"
        cx = sum(u["x"] for u in players) / len(players)
        cy = sum(u["y"] for u in players) / len(players)
        corner = ("S" if cy < mapY / 2.0 else "N") + ("E" if cx < mapX / 2.0 else "W")
        opp = session._OPPOSITE_CORNER[corner]
        moves = []
        if any(u.get("faction") == session.FACTION_HOSTILE and not u.get("isOut")
               for u in st["units"]):
            moves.append({"lever": "battle_teleport_all", "faction": "hostile",
                          "corner": corner, "facing": session._CORNER_FACING[corner]})
        if any(u.get("faction") == 2 and not u.get("isOut") for u in st["units"]):
            moves.append({"lever": "battle_teleport_all", "faction": "neutral",
                          "corner": opp, "facing": session._CORNER_FACING[opp]})
        if moves:
            session.place_deterministic(host, client, moves, what="ghost-stepper roof corner placement")

        st = battle_state(host)
        client_ids = [u["id"] for u in st["units"]
                      if u.get("coop") == session.COOP_SEAT_1 and not u.get("isOut")]
        host_ids = sorted(u["id"] for u in st["units"]
                          if u.get("coop") == COOP_SEAT_0 and u.get("isPlayerSoldier")
                          and not u.get("isOut"))

        print(f"[repro_ghost_stepper] bring_up_roof_battle(seat_count={seat_count}) qualifies: "
              f"{len(client_ids)} client unit(s) {client_ids}, {len(host_ids)} host unit(s) "
              f"{host_ids}, door={door}")
        return host, client, client_ids, host_ids, door
    except Exception:
        host.shutdown()
        client.shutdown()
        raise


def teleport_to_lane(host, client, actor_id, door):
    """Teleport (both machines, hash gate) to the baked off-centre roof lane's
    start tile, facing east (dir=2) so it faces straight down the lane."""
    start = (door["x"] + LANE_DX_START, door["y"] + LANE_DY, door["z"] + ROOF_DZ)
    session.place_deterministic(
        host, client,
        [{"lever": "battle_teleport_unit", "unit": actor_id,
          "x": start[0], "y": start[1], "z": start[2], "dir": 2}],
        what=f"ghost roof lane-start unit {actor_id}")
    return start


def park(host, client, actor_id, door, k):
    """Move a finished actor off the lane to a distinct parking-row tile so the
    lane is clear for the next fresh actor (the park row is a separate off-centre
    run-7 roof row; k = 0,1,2,... spaces parked actors one tile apart)."""
    p = (door["x"] + LANE_DX_START + k, door["y"] + PARK_DY, door["z"] + ROOF_DZ)
    session.place_deterministic(
        host, client,
        [{"lever": "battle_teleport_unit", "unit": actor_id, "x": p[0], "y": p[1], "z": p[2], "dir": 2}],
        what=f"ghost park unit {actor_id}")


def lane_dest(host, actor_id, n):
    """The unit's CURRENT position + n*D (pure arithmetic, no scan)."""
    u = session.unit_of(host, actor_id)
    return (u["x"] + D[0] * n, u["y"] + D[1] * n, u["z"])


def walk_lane(host, client, actor_id, what, n, require_unhalted=True):
    """ONE send_walk to lane_dest(n); no iseq => a RED naming the premise. Same
    (hw, cw) shape every GS phase's assertions expect (mirrors the RW-S4
    repro_atom_walk.walk_lane)."""
    dest = lane_dest(host, actor_id, n)
    prev = session.walk_action_id(host)
    resp = session.send_walk(client, actor_id, dest)
    assert resp.get("iseq"), (f"FIXTURE PREMISE BROKE: {what}: no route from "
                              f"{session.pos_of(session.unit_of(host, actor_id))} to {dest}; reply={resp}")
    session.wait_walk_settled(host, client, prev)
    session.settle_reveal(host, client)
    hw, cw = session.last_walk(host), session.last_walk(client)
    if require_unhalted and bool((hw.get("restate") or {}).get("halted")):
        raise AssertionError(f"FIXTURE PREMISE BROKE: {what}: walk halted unexpectedly")
    return hw, cw


def negative_control(host, client, actor_id):
    """DONE-WHEN 6 / SPEC 7(f)'s "ON/OFF equivalence" negative control - run
    FIRST, deliberately, while event_state.ghostEnqueued is still literally 0
    on a freshly-booted battle (it is a monotone per-battle counter,
    CoopGhost::reset() only ever runs at battle teardown), so "assert ...
    ghostEnqueued == 0" (the packet text's own exact wording) is the LITERAL
    counter value, not a before/after delta computed against a nonzero
    baseline. Running the positive controls first would make a literal-zero
    assertion impossible to satisfy honestly; this file avoids that instead
    of reinterpreting the assertion."""
    for name, value in (("coopGhostStepper", False),):
        set_ghost_option(host, value)
        set_ghost_option(client, value)
    assert read_ghost_option(client) is False, "coopGhostStepper did not read back False on client"

    es0 = event_state(client)
    assert es0.get("ghostEnqueued", -1) == 0, (
        f"negative control must start from a genuinely fresh ghost counter, got {es0}")

    do_turn(host, client, actor_id)
    do_kneel(host, client, actor_id)
    hw, cw = walk_lane(host, client, actor_id, "negative control", 3)
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


def positive_walk(host, client, actor_id):
    before = event_state(client)
    enq0, comp0 = before.get("ghostEnqueued", 0), before.get("ghostCompleted", 0)
    seq0 = before.get("lastSeqApplied", 0)

    hw, cw = walk_lane(host, client, actor_id, "positive_walk", 5)
    steps = hw.get("steps") or []
    assert steps, "positive_walk: the settled walk executed zero steps"

    # EXPECTED is every turn/kneel/walk_step ev since seq0, NOT just the
    # walk's own `steps` - vanilla turns a unit to face its path's first step
    # BEFORE it walks whenever the actor is not already facing that way (a
    # real `turn` ev, and if the actor started kneeled, a real `kneel`
    # stand-up ev too - the W1-P9 follow-up kneel_before_walk_ordering()
    # covers on its own) - each of which enqueues its OWN ghost, same as any
    # other partner action. Re-deriving the true expected count from the
    # event ring (which - unlike the ghost counters - carries a seq/actionId
    # per entry) is what makes this assertion correct regardless of the
    # actor's incoming facing/kneeled state.
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


def halted_walk_prefix(host, client, actor_id):
    """SPEC 7(f): "a HALTED walk animates only the executed prefix" -
    ghostEnqueued must equal len(lastWalk['steps']) (the EXECUTED prefix),
    never the intent's planned path length. Uses the SAME battle_halt_walk
    one-shot TestServer lever repro_atom_walk.py's own PHASE 3 uses. The roof
    lane's baked ROOF_LANE_LEN gives a 6-step plan every run, so the halt
    lever always has something left to stop."""
    attempt_es = event_state(client)
    enq0 = attempt_es.get("ghostEnqueued", 0)
    comp0 = attempt_es.get("ghostCompleted", 0)
    seq0 = attempt_es.get("lastSeqApplied", 0)

    dest = lane_dest(host, actor_id, ROOF_LANE_LEN - 1)
    prev = session.walk_action_id(host)
    host.ok({"cmd": "battle_halt_walk"})  # armed BEFORE the send - PHASE 3's own precedent
    resp = session.send_walk(client, actor_id, dest)
    assert resp.get("iseq"), (
        f"FIXTURE PREMISE BROKE: halted_walk_prefix: no route from "
        f"{session.pos_of(session.unit_of(host, actor_id))} to {dest}; reply={resp}")
    session.wait_walk_settled(host, client, prev)
    session.settle_reveal(host, client)
    hw, cw = session.last_walk(host), session.last_walk(client)
    assert hw is not None and hw["plannedLen"] >= 2, (
        "halted_walk_prefix: no candidate destination produced a MULTI-STEP plan - a halt can "
        "only be observed on a walk with something left to halt. FIXTURE failure.")

    hsteps = hw["steps"]
    assert 0 < len(hsteps) < hw["plannedLen"], (
        f"halted_walk_prefix: the walk executed {len(hsteps)} of {hw['plannedLen']} planned "
        "step(s) - the halt lever must stop it AFTER at least one step and BEFORE the last")

    executed = hsteps

    # EXPECTED counts turn/kneel/walk_step evs since this attempt's own seq
    # baseline, not just len(executed) - the same pre-walk-turn/stand-up
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
    hw, cw = walk_lane(host, client, actor_id, "kneel-then-walk", 3)
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
    host, client, client_ids, host_ids, door = bring_up_roof_battle(8, "a")
    try:
        assert len(client_ids) >= 5, (
            f"FIXTURE PREMISE BROKE: only {len(client_ids)} live seat-1 unit(s); this fixture "
            "needs 5 (one fresh soldier per phase)")
        assert_hash_clean(host, client, full=True, what="at t=0 (pre-action)")

        # ONE DEDICATED, FRESH CLIENT SOLDIER PER PHASE, all teleported to the
        # SAME baked roof lane in turn and parked on a separate row once done
        # (teleport_to_lane/park's own doc comments) - the lane is always
        # clear at the start of each phase, so there is no search, no retry,
        # no reroll (SPEC RW-S4 REV E.47).
        teleport_to_lane(host, client, client_ids[0], door)
        off_es = negative_control(host, client, client_ids[0])
        park(host, client, client_ids[0], door, 0)

        # Option back ON (the default - WV-D5-style explicit re-arm rather
        # than assuming a prior branch left it that way).
        set_ghost_option(host, True)
        set_ghost_option(client, True)
        assert read_ghost_option(client) is True, "coopGhostStepper did not read back True on client"

        teleport_to_lane(host, client, client_ids[1], door)
        on_hh, on_ch = positive_turn(host, client, client_ids[1])
        positive_kneel(host, client, client_ids[1])
        park(host, client, client_ids[1], door, 1)

        teleport_to_lane(host, client, client_ids[2], door)
        positive_walk(host, client, client_ids[2])
        park(host, client, client_ids[2], door, 2)

        teleport_to_lane(host, client, client_ids[3], door)
        halted_walk_prefix(host, client, client_ids[3])
        park(host, client, client_ids[3], door, 3)

        teleport_to_lane(host, client, client_ids[4], door)
        kneel_before_walk_ordering(host, client, client_ids[4])
        park(host, client, client_ids[4], door, 4)

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
    never reused. Seated to leave HOST-owned units (bring_up_roof_battle(4)):
    GS7 needs a unit the HOST itself can kneel.

    THE HOST'S OWN ACTION IS A REAL KEYPRESS, NOT battle_intent
    (repro_atom_kneel.py's own precedent): `battle_intent` is the CLIENT's
    network-intent path (admitted, validated, then executed BY THE HOST) -
    the host itself never "intents" anything, it executes directly, so its
    local action must be driven the same way a real player would
    (inject_input), exactly like every other host-origin action in this
    file's sibling repros. GS7 does NOT use the roof lane - a kneel does not
    move the unit, and the corner-placed aliens keep it contact-free at its
    default interior tile."""
    import glob

    host, client, client_ids, host_ids, door = bring_up_roof_battle(4, "b")
    try:
        assert host_ids, "FIXTURE PREMISE BROKE: Session B has no host-owned unit to kneel"
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
    # Exit-code convention: 0 PASS, 2 FAIL (a red, including a broken fixture
    # premise). There is NO exit-3 SKIP (SPEC RW-S4 REV E.47, WV-D100) - the
    # roof fixture always provides the lane, so a broken premise is a red
    # naming it, never a skip.
    try:
        main()
        sys.exit(EXIT_PASS)
    except (AssertionError, TimeoutError) as e:
        print(f"\nrepro_ghost_stepper: FAIL\n{type(e).__name__}: {e}")
        print("")
        print("--- traceback (classification aid) ---")
        traceback.print_exc()
        sys.exit(EXIT_FAIL)
