"""SPEC 14 (W1-P16): the EDGE PASS - four deterministic phases on the
Lightning-craft roof fixture (repro_ghost_stepper.bring_up_roof_battle),
each using a fresh seat-1 actor teleported to the baked roof lane
(GS.teleport_to_lane / GS.lane_dest). TEST-ONLY.

  PHASE 1  low-TU walk admit/deny boundaries, upright and kneeled, plus the
           no_tu halt (an admitted walk that executes only its affordable
           prefix).
  PHASE 2  a zero-step walk (battle_halt_walk_before_step), upright and
           kneeled - the kneeled leg is the non-vacuous one: the host spends
           the mandatory stand-up TU before the lever aborts the first step,
           so `final` has something real to carry.
  PHASE 3  a zero-step SPOT: an actor placed at the lane MIDDLE tile,
           KEEPING its own pre-teleport spawn facing F (read at runtime,
           never hardcoded), is ordered 1 tile back-left - a move whose
           first-step turn sweeps a single-tile hostile staged 2 tiles to
           the actor's left - and halts on contact before executing any
           step (haltStep == 0). Replaces cycle 1's "face the map centre"
           construction, which placed the hostile off the map edge
           (WV-D77).
  PHASE 4  an unaffordable UFO-door open (the zero-tick right-click):
           tu=3 (door cost - 1) refuses, tu=5 (door cost + 1) opens - the
           non-vacuity control.

PINNED R1 VALUES (measured on this tip; see each phase for where they are
used): roof-lane upright per-step cost 4 TU; kneeled first-step cost 12 TU
(mandatory stand-up 8 + step 4); a 3-step lane plan at tu=7 executes exactly
1 step then halts no_tu; the LIGHTNING UFO-door open cost is 4 TU. PHASE 3's
own directions (left/back/backleft) are all relative to the actor's own
COMPUTED spawn facing F, read at runtime via `unit_of(host, actor)
["direction"]` before any teleport - never hardcoded - since
bring_up_roof_battle does not rotate soldiers, F is the craft template's own
soldier-slot facing rather than anything derived from the map's absolute
placement.

There is no exit-3 SKIP and no retry/reroll of any kind (REV E.48 SS.A.2 /
SS.A.8, WV-D100): a phase that cannot be constructed on the pinned values is
a RED (exit 2) naming the failed step.

Run:  python tools/coop_test/repro_edge_pass.py
"""

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import repro_ghost_stepper as GS
import repro_atom_walk as W
from repro_walk_zero_step import zero_step_walk, kneel_actor, assert_final_landed

EXIT_PASS, EXIT_FAIL = 0, 2

STR_DENY_COST_CHANGED = "Order cancelled - cost changed"
STR_NOT_ENOUGH_TU = "Not Enough Time Units!"

UPRIGHT_STEP_COST = 4
KNEELED_FIRST_STEP_COST = 12
NO_TU_HALT_TU = 7
NO_TU_HALT_PLAN_LEN = 3
DOOR_OPEN_COST = 4


# ----- small probes (thin wrappers, sibling-file convention) ---------------

def battle_state(gc):
    return session.battle_state(gc)


def event_state(gc):
    return session.event_state(gc)


def unit_of(gc, uid):
    return session.unit_of(gc, uid)


def banner(gc):
    return battle_state(gc).get("coopWaitText", "")


def not_frozen(gc):
    return battle_state(gc)["authority"]["desyncFrozen"] is False


def off(pos, d, n=1):
    """Tile @a pos offset @a n steps in OpenXcom facing @a d (session.DIR_DX/
    DIR_DY convention)."""
    return (pos[0] + session.DIR_DX[d] * n, pos[1] + session.DIR_DY[d] * n, pos[2])


def in_sector(direction, dX, dY):
    """BattleUnit.cpp:5197 checkViewSector, inlined per the SPEC 14 brief.
    dX = pos.x - actor.x, dY = actor.y - pos.y."""
    return {
        0: dX + dY >= 0 and dY - dX >= 0,
        1: dX >= 0 and dY >= 0,
        2: dX + dY >= 0 and dY - dX <= 0,
        3: dY <= 0 and dX >= 0,
        4: dX + dY <= 0 and dY - dX <= 0,
        5: dX <= 0 and dY <= 0,
        6: dX + dY <= 0 and dY - dX >= 0,
        7: dY >= 0 and dX <= 0,
    }[direction]


def set_tu_both(host, client, actor_id, tu, exact=True):
    """The SS.B.5 lever `battle_set_unit_state`, applied to EACH machine with
    the SAME absolute arg, then hash-gated. `BattleUnit::setTimeUnits` clamps
    (`_tu = Clamp(tu, 0, stats.tu)`, BattleUnit.cpp:4752 - WV-D77 traced: a
    60-TU top-up landed at 57 for a soldier whose own max is 57), so
    `exact=False` accepts whatever value both machines land on instead of
    demanding the literal request - used only for an ample-TU top-up where
    the landed value does not matter, so long as it is the SAME on both
    machines. Every boundary call in this file keeps the default `exact=True`,
    since the whole point there is the PRECISE TU value."""
    landed = {}
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_set_unit_state", "unit": actor_id, "tu": tu})
        assert r.get("ok"), (
            f"battle_set_unit_state(unit={actor_id}, tu={tu}) failed on "
            f"{'host' if gc is host else 'client'}: {r}")
        if exact:
            assert r.get("tu") == tu, (
                f"battle_set_unit_state(unit={actor_id}, tu={tu}) did not stick on "
                f"{'host' if gc is host else 'client'}: {r}")
        landed[gc] = r.get("tu")
    assert landed[host] == landed[client], (
        f"battle_set_unit_state(unit={actor_id}, tu={tu}) landed at different values - "
        f"host={landed[host]} client={landed[client]}")
    session.assert_hash_clean(host, client, full=True,
                              what=f"after setting unit {actor_id} tu={tu}")
    return landed[host]


def order_walk_outcome(host, client, actor_id, dest, what):
    """Order ONE walk and classify it without ever calling
    session.wait_walk_settled on a possibly-denied walk (a deny emits no
    restate and that call would HANG). Returns ("walk", hostLastWalk) or
    ("deny:<reason>", None)."""
    prev = session.walk_action_id(host)
    resp = session.send_walk(client, actor_id, dest)
    assert resp.get("iseq"), f"{what}: the walk intent did not ship: {resp}"
    outcome = None
    for _ in range(200):
        hw = session.last_walk(host)
        if hw.get("actionId", 0) != prev and hw.get("active") is False and hw.get("restate"):
            outcome = "walk"
            break
        ld = session.event_state(client).get("lastDeny")
        if ld and ld.get("iseq") == resp["iseq"]:
            outcome = "deny:" + str(ld.get("reason"))
            break
        time.sleep(0.05)
    assert outcome, f"{what}: the walk was neither executed nor denied within the poll window"
    if outcome == "walk":
        session.settle_reveal(host, client)
        return "walk", session.last_walk(host)
    return outcome, None


# ----- PHASE 1 --------------------------------------------------------------

def phase1_low_tu_walk(host, client, actor_id, door):
    print("\n== PHASE 1: low-TU walk boundaries (upright + kneeled) + no_tu HALT ==")
    GS.teleport_to_lane(host, client, actor_id, door)
    before = unit_of(host, actor_id)
    assert before["kneeled"] is False, "PHASE 1: the fresh lane actor must start upright"

    # ---- UPRIGHT boundary: cost-1 denies, cost admits -----------------
    set_tu_both(host, client, actor_id, UPRIGHT_STEP_COST - 1)
    dest1 = GS.lane_dest(host, actor_id, 1)
    kind, _ = order_walk_outcome(host, client, actor_id, dest1, "PHASE 1 upright cost-1")
    assert kind == "deny:cost_changed", (
        f"PHASE 1: upright tu={UPRIGHT_STEP_COST - 1} expected deny:cost_changed, got {kind}")
    after1 = unit_of(host, actor_id)
    assert (after1["x"], after1["y"], after1["z"]) == (before["x"], before["y"], before["z"]), (
        "PHASE 1: a denied upright walk moved the actor")
    assert banner(client) == STR_DENY_COST_CHANGED, (
        f"PHASE 1: ordering seat banner {banner(client)!r}, expected {STR_DENY_COST_CHANGED!r}")
    assert banner(host) != STR_DENY_COST_CHANGED, (
        "PHASE 1: the OBSERVING machine (host) printed the ordering seat's deny banner")
    session.assert_hash_clean(host, client, full=True, what="PHASE 1 after upright cost-1 deny")
    print(f"    [PHASE 1] upright DENY boundary: tu={UPRIGHT_STEP_COST - 1} -> "
          f"deny:cost_changed, unmoved, only the ordering seat's banner changed")

    set_tu_both(host, client, actor_id, UPRIGHT_STEP_COST)
    kind, hw = order_walk_outcome(host, client, actor_id, dest1, "PHASE 1 upright cost")
    assert kind == "walk", f"PHASE 1: upright tu={UPRIGHT_STEP_COST} expected ADMIT, got {kind}"
    assert hw.get("steps"), "PHASE 1: upright admit executed zero steps"
    print(f"    [PHASE 1] upright ADMIT boundary: tu={UPRIGHT_STEP_COST} -> executed "
          f"{len(hw['steps'])} step(s)")

    # ---- KNEELED boundary: cost-1 denies, cost admits -----------------
    # The upright ADMIT boundary just spent exactly UPRIGHT_STEP_COST TU
    # (WV-D77 traced: the actor lands here at tu=0, and a kneel intent with
    # no TU to spend is never admitted - top up generously before kneeling).
    set_tu_both(host, client, actor_id, 60, exact=False)
    kneel_actor(host, client, actor_id, "PHASE 1")
    kneeled_before = unit_of(host, actor_id)
    assert kneeled_before["kneeled"] is True, "PHASE 1: the actor did not kneel"
    set_tu_both(host, client, actor_id, KNEELED_FIRST_STEP_COST - 1)
    dest2 = GS.lane_dest(host, actor_id, 1)
    kind, _ = order_walk_outcome(host, client, actor_id, dest2, "PHASE 1 kneeled cost-1")
    assert kind == "deny:cost_changed", (
        f"PHASE 1: kneeled tu={KNEELED_FIRST_STEP_COST - 1} expected deny:cost_changed, "
        f"got {kind}")
    after2 = unit_of(host, actor_id)
    assert after2["kneeled"] is True, "PHASE 1: a denied kneeled walk stood the actor up"
    assert (after2["x"], after2["y"], after2["z"]) == \
           (kneeled_before["x"], kneeled_before["y"], kneeled_before["z"]), (
        "PHASE 1: a denied kneeled walk moved the actor")
    assert banner(client) == STR_DENY_COST_CHANGED, (
        f"PHASE 1: kneeled deny ordering-seat banner {banner(client)!r}, expected "
        f"{STR_DENY_COST_CHANGED!r}")
    assert banner(host) != STR_DENY_COST_CHANGED, (
        "PHASE 1: the OBSERVING machine printed the kneeled deny banner")
    session.assert_hash_clean(host, client, full=True, what="PHASE 1 after kneeled cost-1 deny")
    print(f"    [PHASE 1] kneeled DENY boundary: tu={KNEELED_FIRST_STEP_COST - 1} -> "
          f"deny:cost_changed, unmoved and still kneeled")

    set_tu_both(host, client, actor_id, KNEELED_FIRST_STEP_COST)
    kind, hw = order_walk_outcome(host, client, actor_id, dest2, "PHASE 1 kneeled cost")
    assert kind == "walk", (
        f"PHASE 1: kneeled tu={KNEELED_FIRST_STEP_COST} expected ADMIT, got {kind}")
    assert hw.get("steps"), "PHASE 1: kneeled admit executed zero steps"
    landed = unit_of(host, actor_id)
    assert landed["kneeled"] is False, (
        "PHASE 1: the kneeled admit did not stand the actor up before its first step")
    print(f"    [PHASE 1] kneeled ADMIT boundary: tu={KNEELED_FIRST_STEP_COST} -> executed "
          f"{len(hw['steps'])} step(s), actor stood up")

    # ---- no_tu HALT (upright): an admitted walk executes only its ----
    # affordable prefix.
    GS.teleport_to_lane(host, client, actor_id, door)
    set_tu_both(host, client, actor_id, NO_TU_HALT_TU)
    dest3 = GS.lane_dest(host, actor_id, NO_TU_HALT_PLAN_LEN)
    kind, hw = order_walk_outcome(host, client, actor_id, dest3, "PHASE 1 no_tu")
    assert kind == "walk", f"PHASE 1: no_tu case expected an executed (halted) walk, got {kind}"
    restate = hw.get("restate") or {}
    steps = hw.get("steps") or []
    assert len(steps) == 1, f"PHASE 1: no_tu case executed {len(steps)} step(s), expected exactly 1"
    assert restate.get("halted") is True, "PHASE 1: no_tu case restate is not marked halted"
    assert restate.get("reason") == "no_tu", (
        f"PHASE 1: no_tu case restate reason {restate.get('reason')!r}, expected 'no_tu'")
    executed_prefix = [W.tpos(s["to"]) for s in steps]
    restate_path = [W.tpos(p) for p in (restate.get("path") or [])]
    assert restate_path == executed_prefix, (
        f"PHASE 1: no_tu restate.path {restate_path} != the executed prefix {executed_prefix}")
    assert banner(client) == STR_NOT_ENOUGH_TU, (
        f"PHASE 1: no_tu ordering-seat banner {banner(client)!r}, expected "
        f"{STR_NOT_ENOUGH_TU!r}")
    session.assert_hash_clean(host, client, full=True, what="PHASE 1 after the no_tu halt")
    print(f"    [PHASE 1] no_tu HALT: tu={NO_TU_HALT_TU} on a {NO_TU_HALT_PLAN_LEN}-tile plan "
          f"-> executed {len(steps)} step(s), restate halted=True reason='no_tu', "
          "path == executed prefix")
    print("EXERCISED P1")


# ----- PHASE 2 --------------------------------------------------------------

def phase2_zero_step_walk(host, client, door, upright_actor, kneeled_actor):
    print("\n== PHASE 2: zero-step walk (upright + kneeled) ==")
    for k, (tag, actor_id, do_kneel) in enumerate(
            (("upright", upright_actor, False), ("kneeled", kneeled_actor, True)), start=1):
        GS.teleport_to_lane(host, client, actor_id, door)
        set_tu_both(host, client, actor_id, 60, exact=False)
        if do_kneel:
            kneel_actor(host, client, actor_id, f"PHASE 2 {tag}")
            assert unit_of(host, actor_id)["kneeled"] is True, (
                f"PHASE 2 {tag}: the actor did not kneel before the zero-step walk")
        assert host.cmd({"cmd": "battle_halt_walk_before_step"}).get("ok"), (
            f"PHASE 2 {tag}: battle_halt_walk_before_step lever refused")
        dest = GS.lane_dest(host, actor_id, 1)
        zero_step_walk(host, client, actor_id, dest, f"PHASE 2 {tag}")
        assert_final_landed(host, client, actor_id, f"PHASE 2 {tag}")
        print(f"    [PHASE 2] {tag} leg PASS: actor {actor_id} zero-step walk landed "
              "identically on both machines")
        # A zero-step walk never moves the actor off the lane-start tile - park
        # it (WV-D77 traced: the kneeled leg's own teleport_to_lane otherwise
        # refuses "destination footprint not placeable", the upright leg's
        # actor still sitting there) before the NEXT leg claims that tile.
        GS.park(host, client, actor_id, door, k)
    print("EXERCISED P2")


# ----- PHASE 3 --------------------------------------------------------------

def phase3_zero_step_spot(host, client, actor_id, door):
    print("\n== PHASE 3: zero-step SPOT (lane-middle spot, back-left turn sweeps a "
          "left-staged hostile) ==")

    # 1. the actor's OWN pre-teleport spawn facing - read BEFORE any move
    # (bring_up_roof_battle does not rotate soldiers), never hardcoded.
    F = unit_of(host, actor_id)["direction"]
    left = (F + 6) % 8
    back = (F + 4) % 8
    backleft = (F + 5) % 8

    # 2. teleport to the lane MIDDLE tile, KEEPING facing F.
    spot = (door["x"] + GS.LANE_DX_START + 3, door["y"] + GS.LANE_DY, door["z"] + GS.ROOF_DZ)
    session.place_deterministic(
        host, client,
        [{"lever": "battle_teleport_unit", "unit": actor_id,
          "x": spot[0], "y": spot[1], "z": spot[2], "dir": F}],
        what="PHASE 3 soldier roof spot")

    # 3. a single-tile hostile, staged 2 tiles to the actor's LEFT, facing
    # AWAY from the actor (left).
    st = battle_state(host)
    hostiles = sorted((u for u in st["units"]
                        if u.get("faction") == session.FACTION_HOSTILE and not u.get("isOut")
                        and u.get("armorSize", 1) == 1),
                       key=lambda u: u["id"])
    assert hostiles, "PHASE 3: FIXTURE PREMISE BROKE: no living single-tile hostile to stage"
    alien_id = hostiles[0]["id"]
    enemy_tile = off(spot, left, 2)
    session.place_deterministic(
        host, client,
        [{"lever": "battle_teleport_unit", "unit": alien_id,
          "x": enemy_tile[0], "y": enemy_tile[1], "z": enemy_tile[2], "dir": left}],
        what="PHASE 3 hostile placement")
    for gc, tag in ((host, "host"), (client, "client")):
        r = gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": alien_id,
                    "stat": "reactions", "value": 0})
        assert r.get("ok"), f"PHASE 3: could not zero hostile {alien_id} reactions on {tag}: {r}"
    session.assert_hash_clean(host, client, full=True, what="PHASE 3 after staging")

    # VERIFY, NEVER INFER: re-read both units at the tip rather than trusting
    # the commanded coordinates.
    au = unit_of(host, actor_id)
    hu = unit_of(host, alien_id)
    assert (au["x"], au["y"], au["z"]) == spot and au["direction"] == F, (
        f"PHASE 3: FIXTURE PREMISE BROKE: actor {actor_id} reads back at "
        f"{(au['x'], au['y'], au['z'])} dir={au['direction']}, expected {spot} dir={F}")
    assert (hu["x"], hu["y"], hu["z"]) == enemy_tile, (
        f"PHASE 3: FIXTURE PREMISE BROKE: hostile {alien_id} reads back at "
        f"{(hu['x'], hu['y'], hu['z'])}, expected {enemy_tile}")

    # 4. premises, BEFORE the move.
    for gc, tag in ((host, "host"), (client, "client")):
        spotted = unit_of(gc, actor_id).get("spottedThisTurn")
        assert spotted == [], (
            f"PHASE 3: FIXTURE PREMISE BROKE: actor {actor_id} spottedThisTurn is "
            f"{spotted!r} on {tag}, expected []")
    dX = hu["x"] - au["x"]
    dY = au["y"] - hu["y"]
    assert not in_sector(F, dX, dY), (
        f"PHASE 3: FIXTURE PREMISE BROKE: the hostile at {enemy_tile} is ALREADY inside "
        f"actor {actor_id}'s facing-{F} sector before the move (dX={dX} dY={dY})")
    dist = session.cheb((au["x"], au["y"], au["z"]), (hu["x"], hu["y"], hu["z"]))
    assert dist <= session.MAX_VIEW_DISTANCE, (
        f"PHASE 3: FIXTURE PREMISE BROKE: the hostile is {dist} tiles away, beyond "
        f"MAX_VIEW_DISTANCE={session.MAX_VIEW_DISTANCE}")

    # 5. a move to the back-left diagonal - a first-step turn (3/8 CCW) that
    # sweeps the hostile staged at the actor's left into view.
    target = off(spot, backleft, 1)
    kind, hw = order_walk_outcome(host, client, actor_id, target, "PHASE 3")
    assert kind == "walk", f"PHASE 3: expected an executed (halted) walk, got {kind}"
    restate = hw.get("restate") or {}
    assert not (hw.get("steps") or []), (
        f"PHASE 3: the walk executed {len(hw.get('steps') or [])} step(s), expected 0")
    assert restate.get("halted") is True, "PHASE 3: restate is not marked halted"
    assert restate.get("reason") == "spot", (
        f"PHASE 3: restate reason {restate.get('reason')!r}, expected 'spot'")

    # 6. the ev PAYLOAD (both machines) and the hash gate.
    action_id = hw.get("actionId")
    host_spot_seq = None
    for gc, tag in ((host, "host"), (client, "client")):
        entries = session.action_events(gc, action_id)
        spots = [e for e in entries if e["kind"] == "spot"]
        assert len(spots) == 1, (
            f"PHASE 3: {tag} actionId {action_id} carries {len(spots)} `spot` ev(s), expected "
            f"exactly 1: {[(e['seq'], e['kind']) for e in entries]}")
        ls = event_state(gc).get("lastSpot") or {}
        assert ls.get("haltStep") == 0, (
            f"PHASE 3: {tag}'s lastSpot.haltStep is {ls.get('haltStep')}, expected 0")
        assert ls.get("seq") == spots[0]["seq"], (
            f"PHASE 3: {tag}'s lastSpot.seq {ls.get('seq')} != the ring's spot seq "
            f"{spots[0]['seq']}")
        seen = list(ls.get("seen") or [])
        assert alien_id in seen, (
            f"PHASE 3: {tag}'s lastSpot.seen {seen} does not contain hostile {alien_id}")
        if gc is host:
            host_spot_seq = spots[0]["seq"]

    session.assert_hash_clean(host, client, full=True, what="PHASE 3 at the zero-step spot halt")

    for gc, tag in ((host, "host"), (client, "client")):
        u = unit_of(gc, actor_id)
        assert u.get("turnBeforeFirstStep") is False, (
            f"PHASE 3: {tag}'s actor {actor_id} has turnBeforeFirstStep="
            f"{u.get('turnBeforeFirstStep')!r}, expected False")
        spotted = u.get("spottedThisTurn") or []
        assert alien_id in spotted, (
            f"PHASE 3: {tag}'s actor {actor_id} spottedThisTurn {spotted} does not contain "
            f"hostile {alien_id}")

    print(f"    [PHASE 3] actor {actor_id} spawn facing F={F} (left={left} back={back} "
          f"backleft={backleft}); spot={spot}; hostile {alien_id} at {enemy_tile} (2 left); "
          f"target={target} (1 back-left); zero-step spot halt at seq {host_spot_seq}, "
          f"haltStep=0, seen contains {alien_id}, all buckets EQUAL, turnBeforeFirstStep "
          "False, spottedThisTurn contains the hostile on both machines")
    print("EXERCISED P3")


# ----- PHASE 4 --------------------------------------------------------------

def phase4_unaffordable_door(host, client, client_ids):
    print("\n== PHASE 4: unaffordable UFO-door open (tu=3 refuses, tu=5 opens) ==")
    dactor, near, far, ddoor = session.contact_free_ufo_door_setup(
        host, client, what="p4", actor_id=client_ids[4])
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    door_key = (ddoor["x"], ddoor["y"], ddoor["z"], ddoor["part"])

    door0 = session.door_lookup(host, door_key)
    assert door0 is not None and door0.get("isUfoDoorOpen") is False, (
        f"PHASE 4: FIXTURE PREMISE BROKE: door {door_key} is not closed to start: {door0}")
    facing = unit_of(host, dactor)["direction"]

    # ---- tu = cost - 1: the open must be REFUSED --------------------------
    set_tu_both(host, client, dactor, DOOR_OPEN_COST - 1)
    before_emitted = event_state(host)["coopDoorEvsEmitted"]
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": dactor, "toDir": facing})
    assert r.get("iseq"), f"PHASE 4: the tu={DOOR_OPEN_COST - 1} turn intent did not ship: {r}"
    time.sleep(2)
    session.settle_reveal(host, client)
    after_emitted = event_state(host)["coopDoorEvsEmitted"]
    assert after_emitted == before_emitted, (
        f"PHASE 4: tu={DOOR_OPEN_COST - 1} coopDoorEvsEmitted moved ({before_emitted} -> "
        f"{after_emitted}) - an unaffordable door-open must not open it")
    for gc, tag in ((host, "host"), (client, "client")):
        d = session.door_lookup(gc, door_key)
        assert d is not None and d.get("isUfoDoorOpen") is False, (
            f"PHASE 4: tu={DOOR_OPEN_COST - 1}: door {door_key} is not closed on {tag}: {d}")
        assert not_frozen(gc), f"PHASE 4: tu={DOOR_OPEN_COST - 1}: {tag} is DESYNC-FROZEN"
    session.assert_hash_clean(host, client, full=True,
                              what=f"PHASE 4 after the tu={DOOR_OPEN_COST - 1} refusal")
    print(f"    [PHASE 4] tu={DOOR_OPEN_COST - 1}: door-open REFUSED, coopDoorEvsEmitted "
          f"stayed {before_emitted}, door closed on both machines, all buckets EQUAL")

    # ---- tu = cost + 1: the open must SUCCEED (non-vacuity control) -------
    set_tu_both(host, client, dactor, DOOR_OPEN_COST + 1)
    before_emitted = event_state(host)["coopDoorEvsEmitted"]
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": dactor, "toDir": facing})
    assert r.get("iseq"), f"PHASE 4: the tu={DOOR_OPEN_COST + 1} turn intent did not ship: {r}"
    time.sleep(2)
    session.settle_reveal(host, client)
    after_emitted = event_state(host)["coopDoorEvsEmitted"]
    assert after_emitted == before_emitted + 1, (
        f"PHASE 4: tu={DOOR_OPEN_COST + 1} coopDoorEvsEmitted did not advance by exactly 1 "
        f"({before_emitted} -> {after_emitted})")
    for gc, tag in ((host, "host"), (client, "client")):
        d = session.door_lookup(gc, door_key)
        assert d is not None and d.get("isUfoDoorOpen") is True, (
            f"PHASE 4: tu={DOOR_OPEN_COST + 1}: door {door_key} did not open on {tag}: {d}")
    session.assert_hash_clean(host, client, full=True,
                              what=f"PHASE 4 after the tu={DOOR_OPEN_COST + 1} open")
    print(f"    [PHASE 4] tu={DOOR_OPEN_COST + 1}: door OPENED, coopDoorEvsEmitted "
          f"{before_emitted} -> {after_emitted}, isUfoDoorOpen True on both machines "
          "(non-vacuity control)")
    print("EXERCISED P4")


# ----- main ------------------------------------------------------------------

def main():
    t0 = time.time()
    host, client, client_ids, host_ids, door = GS.bring_up_roof_battle(8, "edgepass")
    try:
        assert len(client_ids) >= 5, (
            f"FIXTURE PREMISE BROKE: only {len(client_ids)} live seat-1 unit(s); this "
            "fixture needs 5 (P1, P2 upright, P2 kneeled, P3, P4 each want their own fresh "
            "actor)")
        session.pin_ai_neutral(host, client, tag="edgepass")

        phase1_low_tu_walk(host, client, client_ids[0], door)
        GS.park(host, client, client_ids[0], door, 0)

        phase2_zero_step_walk(host, client, door, client_ids[1], client_ids[2])

        phase3_zero_step_spot(host, client, client_ids[3], door)
        GS.park(host, client, client_ids[3], door, 3)

        phase4_unaffordable_door(host, client, client_ids)

        print(f"\nrepro_edge_pass: PASS ({time.time() - t0:.1f}s)")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    try:
        main()
        sys.exit(EXIT_PASS)
    except (AssertionError, TimeoutError) as e:
        print(f"\nrepro_edge_pass: FAIL\n{type(e).__name__}: {e}")
        print("")
        print("--- traceback (classification aid) ---")
        traceback.print_exc()
        sys.exit(EXIT_FAIL)
