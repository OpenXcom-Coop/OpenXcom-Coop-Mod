"""SPEC 6d (P10-ACCEPT, REV E.8, WV-D78/WV-D79): the PURPOSE-BUILT
deterministic door test, its OWN file rather than a retrofit onto
repro_atom_door.py (NOT touched here) - five prior cycles collided with that
file's map-rolled SEARCH machinery, never with coop door behaviour (WV-D78).
The WV-D63 placement lever removes the need to search: teleport every
hostile away, teleport a soldier next to a named closed UFO door, walk it
through, and re-prove WV-D59 (the host must not apply its own TU reserve to
a client-origin door) in both directions, with a host-origin control leg.

DETERMINISTIC fixture (WV-D65): the SITUATION comes from
`contact_free_ufo_door_setup` (the WV-D63 lever) plus its own hash-equality
gate, never a map re-roll loop - bar is 3 CONSECUTIVE GREEN, not 10. A
`FIXTURE:`-prefixed staging failure re-boots up to MAX_BOOTS(3) and SKIPs
(exit 3, WV-D72); anything else is a real FAIL (exit 2).

THE TRAP AVOIDED (WV-D77): `event_log`'s probe is a fixed-size POD (`seq`,
`actionId`, `kind`, `h`, no `payload` - BattlePump.h:206-219 /
TestServer.cpp:4524-4542), so the door ev is matched on `kind == "door"`
alone; the OPEN is proved by the counter deltas and the door's own
`isUfoDoorOpen` False->True transition.

SPEC 6e (REV E.9) EXTENSION - three more phases, same battle, still no
search. Phase A (leg (a) above) additionally proves the door ev's STREAM
POSITION on both machines (`D.assert_door_between_steps`) and a door-census
change + parity (`D.door_census`/`D.assert_door_parity`). Phase B
right-clicks a SECOND, DIFFERENT UFO door with a SECOND soldier; phase C
right-clicks a THIRD, NON-UFO door with a THIRD soldier. Two facts, both
verified in source and cited at their use sites below: (1) a right-click is
a HOST-ORIGIN `battle_action`, but the facing turn that must precede it has
to ride a CLIENT `battle_intent kind:"turn"` - a bare host rotation has no
coop action context, emits no ev, and `direction` lives in saveBlob
(repro_atom_door.py:942/:1038); (2) a UFO door STAYS in the census and flips
`isUfoDoorOpen`, a NORMAL door LEAVES the census entirely because
`Tile::openDoor` clears the part's map data (`door_census`'s own docstring).
No bucket name is hard-coded for the right-click legs: only "at least one
moved, printed by name" is asserted (a prior leg's `moving_bucket` constant
was never measured against a UFO right-click and would be a guess).

Run:  python tools/coop_test/repro_door_deterministic.py (one harness run at
      a time, machine-wide).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, contact_free_ufo_door_setup, place_deterministic
import repro_atom_walk as W
import repro_atom_door as D

MISSION = "STR_SUPPLY_SHIP"
MAX_BOOTS = 3
# LEG (a) needs enough TU to walk the approach step AND pay the door: 60 is ample.
LEG_A_TU = 60
# LEG (b) MUST be pinned LOW or the control proves nothing. Tile::openDoor computes
# affordability as BattleActionCost(reserve, unit, weapon).haveTU() (Tile.cpp:367-401),
# which folds the RESERVED action's own cost in on top of the door's TUCost - so a
# richly-stocked actor opens the door under an aimed+kneel reserve anyway and the
# refusal we are trying to observe never happens. repro_atom_door.py's own proven
# control leg pins CONTROL_LEG_TU = RIGHT_CLICK_TU = 8 for exactly this reason
# ("a refusal at the control step is evidence the RESERVE changed the outcome, not
# that the actor was merely short on TU"). Same value, same reason.
LEG_B_TU = 8
EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3
BASE_GAME_PORT = 47997
BASE_TEST_PORT = 48997


class FixtureExhausted(Exception):
    """MAX_BOOTS fresh boots, none staged a SITUATION - a lever/fixture finding (WV-D72), never a regression."""


def is_fixture_error(e):
    return str(e).startswith("FIXTURE:")

def bring_up(attempt):
    """test_rw_teleport_lever.py's own bring_up(), verbatim in shape."""
    port = str(BASE_GAME_PORT + attempt)
    host = GameClient("det-host", BASE_TEST_PORT + attempt * 2,
                      make_user_dir(f"door_det_host_{attempt}"))
    client = GameClient("det-client", BASE_TEST_PORT + 1 + attempt * 2,
                        make_user_dir(f"door_det_client_{attempt}"))
    W.bring_up_lobby(host, client, port)
    seated = {}
    D.drive_to_battlescape(host, client, seated, mission=MISSION)
    return host, client


def pin_tu(host, client, actor_id, tu):
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": actor_id,
                   "stat": "tu", "value": tu, "refill": True})
        assert r.get("ok"), f"pin_tu({gc.name}): set_stat failed: {r}"


def wait_counter(host, pred, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred(D.event_state(host)):
            return True
        time.sleep(0.1)
    return False

def dump_record(what, host, actor_id, pos_before, tu_before, door_at, open_before,
                action_id=None, restate=None):
    """WV-D77's instrumented record: actor id, position/TU before/after, the
    door's `isUfoDoorOpen` before/after, ev-kind sequence, halted, reason."""
    units = {u["id"]: u for u in D.battle_state(host).get("units", [])}
    after = units.get(actor_id)
    door_after = D.door_lookup(host, door_at)
    kinds = ([e["kind"] for e in D.action_events(host, action_id)]
             if action_id is not None else [])
    restate = restate or {}
    print(f"    [{what} INSTRUMENTED RECORD - WV-D77]")
    print(f"      actor {actor_id} pos before={pos_before} "
          f"after={D.unit_pos(after) if after else 'UNIT NOT FOUND'}; "
          f"tu before={tu_before} after={after.get('tu') if after else None}")
    print(f"      door {door_at} isUfoDoorOpen before={open_before} "
          f"after={door_after.get('isUfoDoorOpen') if door_after else 'DOOR NOT FOUND'}")
    print(f"      ev-kind sequence: {kinds}")
    print(f"      restate: halted={restate.get('halted')} reason={restate.get('reason')} "
          f"path={restate.get('path')}")


# ===== SPEC 6e (REV E.9) phases B/C: right-click on a NAMED, PLACED door ===
# with its OWN soldier - a plain exclusion filter over D.closed_doors() /
# D.seat_units(), never a ranked/qualified candidate search. Shared by both
# phases; `want_ufo` selects which of the two documented census behaviours
# (FACT 2, `door_census`'s own docstring) the phase asserts.

def pick_door(host, want_ufo, exclude_keys, tag):
    """The first CLOSED door of the requested kind whose (x,y,z,part) is not
    already spoken for - not a ranking, a plain exclusion. Missing on this
    map roll => FIXTURE (WV-D72), never a red."""
    kind = "UFO" if want_ufo else "non-UFO"
    candidates = [d for d in D.closed_doors(host) if bool(d["isUfoDoor"]) == want_ufo]
    for d in candidates:
        key = (d["x"], d["y"], d["z"], d["part"])
        if key not in exclude_keys:
            return d, key
    raise AssertionError(
        f"FIXTURE: {tag}: no closed {kind} door distinct from {sorted(exclude_keys)} "
        f"on this map roll ({len(candidates)} closed {kind} door(s) total)")


def pick_soldier(host, client, used_actors, tag):
    """The next live seat-1 id not already used by an earlier phase/leg."""
    live_h = sorted(u["id"] for u in D.seat_units(host) if u["id"] not in used_actors)
    if not live_h:
        raise AssertionError(
            f"FIXTURE: {tag}: no live seat-1 soldier left (already used: "
            f"{sorted(used_actors)})")
    actor_id = live_h[0]
    live_c = {u["id"] for u in D.seat_units(client)}
    assert actor_id in live_c, (
        f"{tag}: soldier {actor_id} is live seat-1 on the host but not the client")
    return actor_id


def standable_side(host, door, tag):
    """Which of the door's two sides (D.door_sides) has a floor and nobody on
    it - D.tile_walkable against live occupancy, SPEC 6e's own named helper
    for exactly this."""
    a, b = D.door_sides(door)  # never None: door came from D.closed_doors()
    occupied = {D.unit_pos(u) for u in D.battle_state(host).get("units", [])
                if not u.get("isOut")}
    if D.tile_walkable(host, a, occupied):
        return a, b
    if D.tile_walkable(host, b, occupied):
        return b, a
    raise AssertionError(f"FIXTURE: {tag}: neither side of door {door} looks standable")


def wait_facing_applied(host, client, timeout=30):
    """The same 'host emitted caught up on the client' predicate
    repro_atom_door.phase_right_click uses around its own facing turn
    (D.wait_host_idle is broader and outside SPEC 6e's allowed-primitive
    list; event_state alone is sufficient here since nothing else is in
    flight)."""
    client.wait_for(
        "facing turn applied on both machines",
        lambda: (D.event_state(client).get("lastSeqApplied", 0)
                 == D.event_state(host).get("lastSeqEmitted", 0)
                 and D.event_state(client).get("queueDepth") == 0) or None,
        timeout=timeout)


def face_door_via_intent(host, client, actor_id, want_dir, tag):
    """FACT 1 (repro_atom_door.py:942/:1038): the right-click itself is a
    HOST-ORIGIN battle_action, but the facing turn that precedes it MUST
    ride a CLIENT battle_intent kind:"turn" - a bare host rotation has no
    coop action context, emits no ev, and `direction` lives in saveBlob.
    Sent UNCONDITIONALLY (session.place_deterministic's own `dir` already
    points the placement at the door) so this phase genuinely exercises the
    client-origin turn atom rather than relying on the placement lever
    having already gotten it right."""
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": actor_id,
                    "toDir": want_dir})
    assert r.get("iseq"), f"{tag}: the facing turn intent did not ship: {r}"
    wait_facing_applied(host, client)
    hunits = {u["id"]: u for u in D.battle_state(host).get("units", [])}
    cunits = {u["id"]: u for u in D.battle_state(client).get("units", [])}
    hdir = hunits.get(actor_id, {}).get("direction")
    cdir = cunits.get(actor_id, {}).get("direction")
    assert hdir == want_dir, (
        f"{tag}: HOST shows actor {actor_id} facing {hdir} after the turn intent, "
        f"expected {want_dir}")
    assert cdir == want_dir, (
        f"{tag}: CLIENT shows actor {actor_id} facing {cdir} after the turn intent, "
        f"expected {want_dir} - the turn did not apply on both machines")


def wait_door_fired(host, client, before_emitted, timeout=30):
    """repro_atom_door.phase_right_click's own bounded poll, reimplemented
    locally (its D.wait_host_idle sibling is outside SPEC 6e's allow-list):
    the host emitted a NEW door ev AND the client has caught all the way up.
    Bounded so a refusal REPORTS instead of hanging to a bare TimeoutError."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hs, cs = D.event_state(host), D.event_state(client)
        if (hs["coopDoorEvsEmitted"] > before_emitted
                and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                and cs.get("queueDepth") == 0):
            return True
        time.sleep(0.1)
    return False


def phase_right_click_door(host, client, tag, want_ufo, exclude_door_keys, used_actors):
    """SPEC 6e phases B ('want_ufo=True') and C ('want_ufo=False'): a
    HOST-ORIGIN right-click `battle_action` on a NAMED, PLACED door and
    soldier. Returns (actor_id, door_key) so a later phase can exclude both."""
    door, door_key = pick_door(host, want_ufo, exclude_door_keys, tag)
    actor_id = pick_soldier(host, client, used_actors, tag)
    stand, through = standable_side(host, door, tag)
    want_dir = D.dir_between(stand, through)

    place_deterministic(host, client, [
        {"lever": "battle_teleport_unit", "unit": actor_id,
         "x": stand[0], "y": stand[1], "z": stand[2], "dir": want_dir},
    ], what=f"{tag} place actor {actor_id} at door {door_key}")

    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, actor_id, LEG_A_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag} TU pinned")

    face_door_via_intent(host, client, actor_id, want_dir, tag)
    assert_hash_clean(host, client, full=True, what=f"{tag} after facing the door")

    census_before = D.door_census(host)
    before_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    before_emitted = D.event_state(host)["coopDoorEvsEmitted"]
    door_before = D.door_lookup(host, door_key)
    assert door_before is not None and door_before.get("isUfoDoorOpen") is False, (
        f"{tag}: door {door_key} is not closed right before the right-click: {door_before}")

    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": actor_id,
                  "x": through[0], "y": through[1], "z": through[2]})
    assert ra.get("ok"), f"{tag}: battle_action door failed: {ra}"
    fired = wait_door_fired(host, client, before_emitted)
    W.settle_reveal(host, client)
    if not fired:
        dump_record(tag, host, actor_id, stand, LEG_A_TU, door_key,
                   door_before.get("isUfoDoorOpen"), action_id=0)
        raise AssertionError(
            f"{tag}: STOP-IF - the right-click on door {door_key} by actor {actor_id} "
            f"facing {want_dir} emitted NO `door` ev within 30s (host emitted "
            f"{D.event_state(host)['coopDoorEvsEmitted']}, was {before_emitted})")

    door_kind_evs = [e for e in D.action_events(host, 0) if e["kind"] == "door"]
    assert door_kind_evs, (
        f"{tag}: STOP-IF - coopDoorEvsEmitted moved but no `door`-kind ev is in the "
        "actionId-0 stream (WV-D50: the right-click path rides actionId 0)")

    census_after = D.door_census(host)
    assert census_after != census_before, (
        f"{tag} NON-VACUITY: door census did not change across the right-click open")

    door_after = D.door_lookup(host, door_key)
    if want_ufo:
        assert door_after is not None, (
            f"{tag}: STOP-IF - UFO door {door_key} left the census entirely; "
            "door_census's documented rule is that a UFO door STAYS and flips "
            "isUfoDoorOpen - this contradicts it")
        assert door_after.get("isUfoDoorOpen") is True, (
            f"{tag}: STOP-IF - UFO door {door_key} did not flip isUfoDoorOpen "
            f"False -> True: {door_after}")
    else:
        assert door_after is None, (
            f"{tag}: STOP-IF - NON-UFO door {door_key} is still in the census after "
            f"opening ({door_after}); door_census's documented rule is that a normal "
            "door LEAVES the census entirely (Tile::openDoor clears the part's map "
            "data) - this contradicts it")

    D.assert_door_parity(host, client, what=f"{tag} census")

    after_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    moved = sorted(k for k in before_h if before_h[k] != after_h.get(k))
    assert moved, (
        f"{tag} NON-VACUITY: no hash bucket moved on the host across the right-click "
        f"open - before={before_h} after={after_h}")

    assert_hash_clean(host, client, full=True, what=f"{tag} after the right-click")

    after_emitted = D.event_state(host)["coopDoorEvsEmitted"]
    print(f"[{tag}] right-click {'UFO' if want_ufo else 'non-UFO'} door {door_key} "
          f"actor {actor_id}: coopDoorEvsEmitted {before_emitted} -> {after_emitted}; "
          f"bucket(s) moved={moved}; census "
          f"{'stayed (isUfoDoorOpen True)' if want_ufo else 'LEFT (normal door)'}")
    return actor_id, door_key


def run_scenario(host, client, tag):
    # ---- step 2: build the situation with ONE call (WV-D63 lever) ----
    actor_a, near, far, door = contact_free_ufo_door_setup(host, client, what=f"{tag} leg-a")
    door_at = (door["x"], door["y"], door["z"], door["part"])

    # ---- step 3: assert the SITUATION explicitly ----
    d0 = D.door_lookup(host, door_at)
    assert d0 is not None and d0.get("isUfoDoorOpen") is False, (
        f"{tag}: door {door_at} is not closed after placement: {d0}")
    units0 = {u["id"]: u for u in D.battle_state(host).get("units", [])}
    a0 = units0[actor_a]
    assert D.unit_pos(a0) == near, (
        f"{tag}: actor {actor_a} sits at {D.unit_pos(a0)}, expected {near}")
    want_dir = D.dir_between(near, far)
    assert a0.get("direction") == want_dir, (
        f"{tag}: actor {actor_a} faces {a0.get('direction')}, expected {want_dir} "
        f"(toward {far})")
    spotted_now = D.battle_state(host).get("spotted")
    assert not spotted_now, (
        f"FIXTURE: {tag}: the host still has a spotted hostile after placement "
        f"({spotted_now}) - contact-free is a PREMISE of this fixture, so this map "
        "roll is unusable; re-boot (WV-D72)")
    assert_hash_clean(host, client, full=True, what=f"{tag} after placement")

    # ---- step 4: LEG (a) - CLIENT-origin crossing, HOST reserve aimed+kneel ----
    W.set_reserve(host, mode="aimed", kneel=True)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, actor_a, LEG_A_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag}(a) TU pinned")

    emitted0 = D.event_state(host)["coopDoorEvsEmitted"]
    waived0 = D.event_state(host)["coopDoorReserveWaived"]
    census_before_a = D.door_census(host)  # SPEC 6e item 6: non-vacuity control

    prev = W.walk_action_id(host)
    resp = W.send_walk(client, actor_a, far)
    assert resp.get("iseq"), f"{tag}(a): the client-origin walk intent did not ship: {resp}"
    W.wait_walk_settled(host, client, prev)
    W.settle_reveal(host, client)

    hw = W.last_walk(host)
    action_id = hw.get("actionId")
    evs = D.action_events(host, action_id)
    door_evs = [e for e in evs if e["kind"] == "door"]
    if not door_evs:
        dump_record(f"{tag}(a)", host, actor_a, near, LEG_A_TU, door_at, False,
                   action_id=action_id, restate=hw.get("restate"))
        raise AssertionError(
            f"{tag}(a): STOP-IF - the client-origin crossing emitted NO `door` ev "
            f"under the host's aimed+kneel reserve (stream kinds: "
            f"{[e['kind'] for e in evs]})")

    # ---- SPEC 6e phase A additions (owner item 1 + item 6): the door ev's
    # STREAM POSITION on BOTH machines, plus a door-census change + parity.
    # Purely additive - leg (a)'s own accepted assertions below are unchanged.
    D.assert_door_between_steps(host, action_id, what=f"{tag}(a) stream position (host)")
    D.assert_door_between_steps(client, action_id, what=f"{tag}(a) stream position (client)")
    census_after_a = D.door_census(host)
    assert census_after_a != census_before_a, (
        f"{tag}(a) NON-VACUITY: door census did not change across the crossing")
    D.assert_door_parity(host, client, what=f"{tag}(a) census")

    d1 = D.door_lookup(host, door_at)
    assert d1 is not None and d1.get("isUfoDoorOpen") is True, (
        f"{tag}(a): door {door_at} did not go isUfoDoorOpen False -> True: {d1}")
    hs = D.event_state(host)
    emitted_a = hs["coopDoorEvsEmitted"]
    waived_a = hs["coopDoorReserveWaived"]
    assert emitted_a > emitted0, (
        f"{tag}(a): coopDoorEvsEmitted did not increase ({emitted0} -> {emitted_a})")
    assert waived_a > waived0, (
        f"{tag}(a): STOP-IF - coopDoorReserveWaived did not increase ({waived0} -> "
        f"{waived_a}) - the host's own reserve was not neutralised for a "
        "client-origin door")
    units_after_a = {u["id"]: u for u in D.battle_state(host).get("units", [])}
    final_pos = D.unit_pos(units_after_a[actor_a])
    assert final_pos == far, (
        f"{tag}(a): actor {actor_a} ended at {final_pos}, expected {far}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after leg (a)")
    print(f"[{tag}] leg (a): coopDoorEvsEmitted {emitted0} -> {emitted_a}, "
          f"coopDoorReserveWaived {waived0} -> {waived_a}")

    # ---- step 5: LEG (b) - HOST-origin control, SAME host reserve ----
    rc = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rc.get("ok"), f"{tag}(b): battle_close_ufo_doors failed: {rc}"
    d2 = D.door_lookup(host, door_at)
    assert d2 is not None and d2.get("isUfoDoorOpen") is False, (
        f"{tag}(b): door {door_at} did not re-close: {d2}")

    others = sorted(u["id"] for u in D.seat_units(host) if u["id"] != actor_a)
    assert others, f"FIXTURE: {tag}(b): no second live seat-1 soldier for the control leg"
    second_id = others[0]

    second_id, near_b, far_b, door_b = contact_free_ufo_door_setup(
        host, client,
        door_pick_rule=lambda ds: next(d for d in ds
                                       if (d["x"], d["y"], d["z"], d["part"]) == door_at),
        actor_id=second_id, teleport_hostiles=False, what=f"{tag} leg-b")

    # ---- b1 BASELINE: reserve=none, does this actor/door/TU open at all? ----
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, second_id, LEG_B_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag}(b) baseline TU pinned")

    emitted_base0 = D.event_state(host)["coopDoorEvsEmitted"]
    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": second_id,
                  "x": far_b[0], "y": far_b[1], "z": far_b[2]})
    assert ra.get("ok"), f"{tag}(b) baseline: battle_action door failed: {ra}"
    opened = wait_counter(host, lambda es: es["coopDoorEvsEmitted"] > emitted_base0)
    W.settle_reveal(host, client)
    if not opened:
        dump_record(f"{tag}(b) baseline", host, second_id, near_b, LEG_B_TU, door_at,
                   False)
        raise AssertionError(
            f"{tag}(b): STOP-IF - the baseline host-origin order (reserve=none) did "
            f"NOT open door {door_at} - the fixture, not the rule, is wrong")
    assert_hash_clean(host, client, full=True, what=f"{tag}(b) baseline opened")
    emitted_base1 = D.event_state(host)["coopDoorEvsEmitted"]
    print(f"[{tag}] leg (b) baseline: coopDoorEvsEmitted {emitted_base0} -> "
          f"{emitted_base1}")

    # ---- re-arm: close it again, re-pin TU, only the reserve changes next ----
    rc = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rc.get("ok"), f"{tag}(b): re-close failed: {rc}"
    pin_tu(host, client, second_id, LEG_B_TU)
    d3 = D.door_lookup(host, door_at)
    assert d3 is not None and d3.get("isUfoDoorOpen") is False, (
        f"{tag}(b): door {door_at} did not re-close before the control: {d3}")
    assert_hash_clean(host, client, full=True, what=f"{tag}(b) re-armed for control")

    # ---- b2 CONTROL: SAME host reserve, IDENTICAL host-origin order ----
    W.set_reserve(host, mode="aimed", kneel=True)
    W.set_reserve(client, mode="none", kneel=False)
    waived_b0 = D.event_state(host)["coopDoorReserveWaived"]
    emitted_b0 = D.event_state(host)["coopDoorEvsEmitted"]
    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": second_id,
                  "x": far_b[0], "y": far_b[1], "z": far_b[2]})
    assert ra.get("ok"), f"{tag}(b) control: battle_action door failed: {ra}"
    opened = wait_counter(host, lambda es: es["coopDoorEvsEmitted"] > emitted_b0, timeout=5)
    time.sleep(1.0)
    W.settle_reveal(host, client)
    hs = D.event_state(host)
    door_opened = opened or hs["coopDoorEvsEmitted"] != emitted_b0
    waive_fired = hs["coopDoorReserveWaived"] != waived_b0
    # WV-D77: check BOTH signals before raising - a door opened WITHOUT the
    # waive moving is a TU-affordability outcome (Tile::openDoor's own cost
    # check), not proof the waive predicate fired for a HOST-origin action.
    if door_opened or waive_fired:
        dump_record(f"{tag}(b) control", host, second_id, near_b, LEG_B_TU, door_at,
                   False)
        print(f"      coopDoorReserveWaived before={waived_b0} after={hs['coopDoorReserveWaived']}")
        if waive_fired:
            raise AssertionError(
                f"{tag}(b): STOP-IF - coopDoorReserveWaived moved ({waived_b0} -> "
                f"{hs['coopDoorReserveWaived']}) for a HOST-origin door - the waive "
                "predicate fired when it must not have (origin was not \"intent\")")
        raise AssertionError(
            f"{tag}(b): the control leg OPENED the door under the IDENTICAL host "
            f"reserve that the baseline needed reserve=none to clear, but "
            f"coopDoorReserveWaived did NOT move ({waived_b0} unchanged) - NOT the "
            "WV-D59 waive; LEG_B_TU is affordable for Tile::openDoor's own "
            "BattleActionCost(reserve).haveTU() check regardless of origin")
    d4 = D.door_lookup(host, door_at)
    assert d4 is not None and d4.get("isUfoDoorOpen") is False, (
        f"{tag}(b): door {door_at} is open after the refused control: {d4}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after leg (b)")
    print(f"[{tag}] leg (b) control: coopDoorEvsEmitted stayed {emitted_b0}, "
          f"coopDoorReserveWaived stayed {waived_b0} (REFUSED)")

    # ---- step 6: restore + final hash gate ----
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    assert_hash_clean(host, client, full=True, what=f"{tag} final")

    # ---- SPEC 6e Phase B: RIGHT-CLICK on a SECOND UFO door, a SECOND soldier ----
    used_actors = {actor_a, second_id}
    actor2, door2_key = phase_right_click_door(
        host, client, f"{tag} phase B", want_ufo=True,
        exclude_door_keys={door_at}, used_actors=used_actors)

    # ---- SPEC 6e Phase C: RIGHT-CLICK on a THIRD, NON-UFO door, a THIRD soldier ----
    used_actors.add(actor2)
    phase_right_click_door(
        host, client, f"{tag} phase C", want_ufo=False,
        exclude_door_keys={door_at, door2_key}, used_actors=used_actors)


def run_fixture(tag):
    attempts = []
    for attempt in range(1, MAX_BOOTS + 1):
        host, client = bring_up(attempt)
        try:
            run_scenario(host, client, f"{tag}#{attempt}")
            print(f"[{tag}] PASSED on boot {attempt}/{MAX_BOOTS}")
            return
        except AssertionError as e:
            if is_fixture_error(e):
                attempts.append(str(e))
                print(f"[{tag}] FIXTURE miss on boot {attempt}/{MAX_BOOTS}: {e}")
                continue
            raise
        finally:
            host.shutdown()
            client.shutdown()
    raise FixtureExhausted(
        f"[{tag}] {MAX_BOOTS} fresh boot(s), none staged the SITUATION:\n  "
        + "\n  ".join(attempts))


def main():
    run_fixture("door_det")
    print("repro_door_deterministic: PASS")


if __name__ == "__main__":
    try:
        main()
    except FixtureExhausted as e:
        print(f"\nrepro_door_deterministic: SKIP (fixture exhausted)\n{e}")
        sys.exit(EXIT_SKIP)
    except (AssertionError, TimeoutError) as e:
        print(f"\nrepro_door_deterministic: FAIL\n{type(e).__name__}: {e}")
        sys.exit(EXIT_FAIL)
