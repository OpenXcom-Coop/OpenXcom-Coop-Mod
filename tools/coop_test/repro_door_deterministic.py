"""The deterministic door test. The placement test command (battle_teleport_*)
removes the need to search: teleport every hostile away, teleport a soldier
next to a named closed UFO door, walk it through, and prove that the host does
not apply its own TU reserve to a client-origin door, with a host-origin
control leg.

DETERMINISTIC fixture: the SITUATION comes from the Lightning craft's own UFO
door plus place_deterministic's own hash-equality gate. There is no map
search: ONE boot, no retry of any kind. A `FIXTURE:`-prefixed staging failure
is a FAIL (exit 2), like any other failure.

THE TRAP AVOIDED: `event_log`'s probe is a fixed-size POD (`seq`,
`actionId`, `kind`, `h`, no `payload` - BattlePump.h:206-219 /
TestServer.cpp:4524-4542), so the door ev is matched on `kind == "door"`
alone; the OPEN is proved by the counter deltas and the door's own
`isUfoDoorOpen` False->True transition.

MORE PHASES, same battle, still no search. The client leg additionally proves
the door ev's STREAM POSITION on both machines
(`session.assert_door_between_steps`) and a door-census change + parity
(`session.door_census`/`session.assert_door_parity`). The craft-door phase
opens the craft UFO door again with another soldier; the normal-door phase
opens a NON-UFO door with another soldier. A UFO door STAYS in the census and
flips `isUfoDoorOpen`; a NORMAL door LEAVES the census entirely because
`Tile::openDoor` clears the part's map data (`door_census`'s own docstring).
No bucket name is hard-coded: only "at least one moved, printed by name" is
asserted. The walk-through phase WALKS through a NON-UFO door.

The client leg's actor starts one tile back of `near`, so the crossing is
back->near->far with a walk_step either side of the door. The boundary-close
phase closes the open UFO doors at a real end of turn (MUTATING: the craft-door
phase leaves a UFO door open), the repeat-close phase checks the no-op repeat,
and the client-refusal phase checks the client's host-only refusal. Which
door(s) are open at the boundary close is MEASURED, never assumed.

THE TURN IS THE RIGHT-CLICK. `UnitTurnBState::init()` (UnitTurnBState.cpp:74-98),
when `_chargeTUs` (default true) and `_action.type == BA_NONE` (the client turn
intent's default, connectionTCP.cpp:3720-3732), calls
`coopUnitOpensDoor(te, unit, rClick=true, dir=-1)` once the unit is no longer
turning - there is no separate right-click action in vanilla; facing a door IS
opening it. The craft-door and normal-door phases therefore place their actor
FACING AWAY and open the door with client `battle_intent {kind:"turn"}` alone
(see phase_turn_opens_door) - no `battle_action {action:"door"}` follows it.

Run:  python tools/coop_test/repro_door_deterministic.py (one harness run at
      a time, machine-wide).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from harness import shutdown_clients  # bring_up's cleanup
import session
from session import assert_hash_clean, contact_free_ufo_door_setup, place_deterministic
import repro_atom_walk as W

MISSION = "STR_TERROR_MISSION"
RACE = "STR_FLOATER"
CRAFT = "STR_LIGHTNING"
# CLIENT LEG needs enough TU to walk the approach step AND pay the door: 60 is ample.
CLIENT_LEG_TU = 60
# HOST LEG MUST be pinned LOW or the control proves nothing. Tile::openDoor computes
# affordability as BattleActionCost(reserve, unit, weapon).haveTU() (Tile.cpp:367-401),
# which folds the RESERVED action's own cost in on top of the door's TUCost - so a
# richly-stocked actor opens the door under an aimed+kneel reserve anyway and the
# refusal we are trying to observe never happens. At 8 TU a refusal at the control
# step is evidence the RESERVE changed the outcome, not that the actor was merely
# short on TU.
HOST_LEG_TU = 8
EXIT_PASS, EXIT_FAIL = 0, 2
BASE_GAME_PORT = 47997
BASE_TEST_PORT = 48997


def is_fixture_error(e):
    return str(e).startswith("FIXTURE:")


def _pin(h):
    """Pin the Lightning craft, then the floater
    race - order matters, drive_to_battlescape calls this AFTER the mission
    pin (cbxMissionChange has already rebuilt the race list by then) and
    BEFORE any seat is picked."""
    h.ok({"cmd": "newbattle_craft", "type": CRAFT})
    h.ok({"cmd": "newbattle_race", "race": RACE})


def bring_up():
    """One boot, no retry; the port and user-dir offsets are fixed."""
    port = str(BASE_GAME_PORT + 1)
    host = GameClient("det-host", BASE_TEST_PORT + 2,
                      make_user_dir("door_det_host_1"))
    client = GameClient("det-client", BASE_TEST_PORT + 3,
                        make_user_dir("door_det_client_1"))
    try:
        W.bring_up_lobby(host, client, port)
        seated = {}
        session.drive_to_battlescape(host, client, seated, mission=MISSION, pre_seat=_pin)
        # The boundary-close phase presses a REAL end-of-turn, which needs the
        # alien side inert so the boundary crosses deterministically (the
        # AI-neutral pin the other boundary-crossing tests use too).
        pinned = session.pin_ai_neutral(host, client, tag="door_det")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on this "
            f"CLASSIC {MISSION} boot - the premise is unexercised")
    except BaseException:
        # run_fixture's try/finally starts only after this returns, so a failed bring-up shuts
        # down the games it spawned here before the error propagates (shared_fixture.bring_up's form)
        shutdown_clients(host, client)
        raise
    return host, client


def pin_tu(host, client, actor_id, tu):
    for gc in (client, host):  # client first, then host
        r = gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": actor_id,
                   "stat": "tu", "value": tu, "refill": True})
        assert r.get("ok"), f"pin_tu({gc.name}): set_stat failed: {r}"
    session.wait_seq_barrier(host, client)


def wait_counter(host, pred, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred(session.event_state(host)):
            return True
        time.sleep(0.1)
    return False

def dump_record(what, host, actor_id, pos_before, tu_before, door_at, open_before,
                action_id=None, restate=None):
    """The instrumented record: actor id, position/TU before/after, the
    door's `isUfoDoorOpen` before/after, ev-kind sequence, halted, reason."""
    units = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    after = units.get(actor_id)
    door_after = session.door_lookup(host, door_at)
    kinds = ([e["kind"] for e in session.action_events(host, action_id)]
             if action_id is not None else [])
    restate = restate or {}
    print(f"    [{what} INSTRUMENTED RECORD]")
    print(f"      actor {actor_id} pos before={pos_before} "
          f"after={session.unit_pos(after) if after else 'UNIT NOT FOUND'}; "
          f"tu before={tu_before} after={after.get('tu') if after else None}")
    print(f"      door {door_at} isUfoDoorOpen before={open_before} "
          f"after={door_after.get('isUfoDoorOpen') if door_after else 'DOOR NOT FOUND'}")
    print(f"      ev-kind sequence: {kinds}")
    print(f"      restate: halted={restate.get('halted')} reason={restate.get('reason')} "
          f"path={restate.get('path')}")


# ===== the Lightning craft's own UFO door: the client leg, the host leg ====
# and the craft-door phase all stage on this ONE door.

lightning_door = session.lightning_door


def lightning_setup(host, client, tag, actor_id=None, move_factions=True):
    """Staging on the craft door. Returns (actor_id, near, far, far_ground, door).
    near = the standable side (deck), far = the void side at door z, far_ground = far one level
    down (the exit tile). Hostiles -> the corner farthest from the door, neutrals -> the
    opposite corner, both machines, hash gate; the actor -> near, facing far."""
    door, mx, my = lightning_door(host)
    a, b = session.door_sides(door)
    if session._tile_standable(host, a):
        near, far = a, b
    elif session._tile_standable(host, b):
        near, far = b, a
    else:
        raise AssertionError(f"FIXTURE: {tag}: neither side of the LIGHTNIN door is standable")
    far_ground = (far[0], far[1], far[2] - 1)
    assert session._tile_standable(host, far_ground), (
        f"FIXTURE: {tag}: the exit tile {far_ground} below the door is not standable")
    corner = ("S" if door["y"] < my / 2.0 else "N") + ("E" if door["x"] < mx / 2.0 else "W")
    opposite = {"NW": "SE", "NE": "SW", "SW": "NE", "SE": "NW"}[corner]
    moves = []
    st = session.battle_state(host)
    if move_factions:
        if any(u.get("faction") == session.FACTION_HOSTILE and not u.get("isOut") for u in st["units"]):
            moves.append({"lever": "battle_teleport_all", "faction": "hostile",
                          "corner": corner, "facing": session._CORNER_FACING[corner]})
        if any(u.get("faction") == 2 and not u.get("isOut") for u in st["units"]):
            moves.append({"lever": "battle_teleport_all", "faction": "neutral",
                          "corner": opposite, "facing": session._CORNER_FACING[opposite]})
    seat1 = sorted(u["id"] for u in session.seat_units(host))
    assert seat1, f"FIXTURE: {tag}: no live seat-1 soldier"
    if actor_id is None:
        actor_id = seat1[0]
    assert actor_id in seat1, f"FIXTURE: {tag}: actor {actor_id} is not a live seat-1 soldier"
    occupant = next((u for u in st["units"] if session.unit_pos(u) == near and u["id"] != actor_id
                     and not u.get("isOut")), None)
    if occupant is not None:
        deck = [(x, y, near[2]) for y in range(door["y"] - 4, door["y"] + 5)
                for x in range(door["x"] - 4, door["x"] + 5)]
        occupied = {session.unit_pos(u) for u in st["units"] if not u.get("isOut")}
        free = next((t for t in deck if t not in (near, far) and session.tile_walkable(host, t, occupied)), None)
        assert free is not None, f"FIXTURE: {tag}: no free deck tile to move unit {occupant['id']} off {near}"
        moves.append({"lever": "battle_teleport_unit", "unit": occupant["id"],
                      "x": free[0], "y": free[1], "z": free[2], "dir": occupant.get("direction", 0)})
    moves.append({"lever": "battle_teleport_unit", "unit": actor_id,
                  "x": near[0], "y": near[1], "z": near[2], "dir": session.dir_between(near, far)})
    place_deterministic(host, client, moves, what=f"lightning_setup {tag}")
    st = session.battle_state(host)
    me = next(u for u in st["units"] if u["id"] == actor_id)
    hostile_d = min((((u["x"] - me["x"]) ** 2 + (u["y"] - me["y"]) ** 2 + (u["z"] - me["z"]) ** 2) ** 0.5
                     for u in st["units"] if u.get("faction") == session.FACTION_HOSTILE and not u.get("isOut")),
                    default=None)
    assert hostile_d is None or hostile_d > session.MAX_VIEW_DISTANCE, (
        f"FIXTURE: {tag}: a hostile is {hostile_d:.1f} tiles from the actor after the corner move")
    return actor_id, near, far, far_ground, door


# ===== craft-door and normal-door phases: THE TURN IS THE RIGHT-CLICK, on a ====
# NAMED, PLACED door with its OWN soldier - a plain exclusion filter over
# session.closed_doors() / session.seat_units(), never a ranked/qualified candidate
# search. Shared by both phases; `want_ufo` selects which of the two
# documented census behaviours (`door_census`'s own docstring) the phase
# asserts.

def pick_door(host, want_ufo, exclude_keys, tag):
    """The first CLOSED door of the requested kind whose (x,y,z,part) is not
    already spoken for and is more than session.MAX_VIEW_DISTANCE tiles
    (Chebyshev, position-based, from battle_state) from every living hostile
    (the actor must not spot on its approach) - not a ranking, a plain
    exclusion. Missing on this map roll => a `FIXTURE:` failure."""
    kind = "UFO" if want_ufo else "non-UFO"
    candidates = [d for d in session.closed_doors(host) if bool(d["isUfoDoor"]) == want_ufo]
    hostiles = [u for u in session.battle_state(host).get("units", [])
                if u.get("faction") == session.FACTION_HOSTILE and not u.get("isOut")]
    considered = 0
    best_dist = None
    for d in candidates:
        key = (d["x"], d["y"], d["z"], d["part"])
        if key in exclude_keys:
            continue
        considered += 1
        if hostiles:
            dist = min(session.cheb((d["x"], d["y"], d["z"]), session.unit_pos(h)) for h in hostiles)
            if dist <= session.MAX_VIEW_DISTANCE:
                best_dist = dist if best_dist is None else max(best_dist, dist)
                continue
        return d, key
    raise AssertionError(
        f"FIXTURE: {tag}: no closed {kind} door distinct from {sorted(exclude_keys)} and "
        f"more than {session.MAX_VIEW_DISTANCE} tiles (Chebyshev) from every living hostile "
        f"on this map roll ({considered} candidate(s) considered, best hostile distance "
        f"{best_dist})")


def pick_soldier(host, client, used_actors, tag):
    """The next live seat-1 id not already used by an earlier phase/leg."""
    live_h = sorted(u["id"] for u in session.seat_units(host) if u["id"] not in used_actors)
    if not live_h:
        raise AssertionError(
            f"FIXTURE: {tag}: no live seat-1 soldier left (already used: "
            f"{sorted(used_actors)})")
    actor_id = live_h[0]
    live_c = {u["id"] for u in session.seat_units(client)}
    assert actor_id in live_c, (
        f"{tag}: soldier {actor_id} is live seat-1 on the host but not the client")
    return actor_id


def standable_side(host, door, tag):
    """Which of the door's two sides (session.door_sides) has a floor and nobody on
    it - session.tile_walkable against live occupancy, the helper for exactly
    this."""
    a, b = session.door_sides(door)  # never None: door came from session.closed_doors()
    occupied = {session.unit_pos(u) for u in session.battle_state(host).get("units", [])
                if not u.get("isOut")}
    if session.tile_walkable(host, a, occupied):
        return a, b
    if session.tile_walkable(host, b, occupied):
        return b, a
    raise AssertionError(f"FIXTURE: {tag}: neither side of door {door} looks standable")


def wait_facing(host, client, actor_id, want_dir, timeout=30):
    """Poll until BOTH machines report `actor_id` actually FACING `want_dir`.

    A seq-based wait (`lastSeqApplied == lastSeqEmitted and queueDepth == 0`)
    is VACUOUSLY TRUE in the window between shipping the intent and the host
    emitting anything for it - so it can return mid-turn.
    Observed: a rotation 2 -> 6 sampled at facing 3 (one step in), failing 1 run
    in 3. UnitTurnBState turns one step per tick, so the only non-racy predicate
    is the FACING ITSELF. Same lesson as the `payload.op` filter: never gate on a
    condition that can hold before the action has happened."""
    deadline = time.time() + timeout
    last = (None, None)
    while time.time() < deadline:
        hu = {u["id"]: u for u in session.battle_state(host).get("units", [])}
        cu = {u["id"]: u for u in session.battle_state(client).get("units", [])}
        hd = hu.get(actor_id, {}).get("direction")
        cd = cu.get(actor_id, {}).get("direction")
        last = (hd, cd)
        if hd == want_dir and cd == want_dir:
            cs = session.event_state(client)
            hs = session.event_state(host)
            if (cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                    and cs.get("queueDepth") == 0):
                return True
        time.sleep(0.1)
    raise AssertionError(
        f"wait_facing: actor {actor_id} never reached facing {want_dir} on both "
        f"machines within {timeout}s (last seen host={last[0]} client={last[1]})")


def wait_door_fired(host, client, before_emitted, timeout=30):
    """A local bounded poll: the host emitted a NEW door ev AND the client has
    caught all the way up. Bounded so a refusal REPORTS instead of hanging to
    a bare TimeoutError. Used by the turn phases and the boundary close."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        cs, hs = session.event_state(client), session.event_state(host)  # the client is read first
        if (hs["coopDoorEvsEmitted"] > before_emitted
                and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                and cs.get("queueDepth") == 0):
            return True
        time.sleep(0.1)
    return False


def phase_turn_opens_door(host, client, tag, want_ufo, exclude_door_keys, used_actors,
                          door_pick=None):
    """The craft-door phase ('want_ufo=True') and the normal-door phase
    ('want_ufo=False'): THE TURN IS THE RIGHT-CLICK, but ONLY on a ZERO-TICK
    re-issue. Actor is
    placed FACING AWAY from a NAMED, PLACED door, then: (1) a turn intent
    toward the door ROTATES it and must NOT open the door - the negative
    control, because lookAt() sets STATUS_TURNING and UnitTurnBState.cpp:74
    gates the door-open on `getStatus() != STATUS_TURNING`; (2) the SAME turn
    intent re-issued is now zero-tick and MUST open it
    (connectionTCP.cpp:4912, "zero-tick door-open branch"). No separate
    `battle_action {action:"door"}` is involved. Returns (actor_id, door_key) so
    a later phase can exclude both.

    `door_pick(host) -> (door, door_key)`, when given, replaces
    `pick_door(...)` - the craft-door phase uses it to stay on the Lightning's
    own craft door."""
    if door_pick is not None:
        door, door_key = door_pick(host)
    else:
        door, door_key = pick_door(host, want_ufo, exclude_door_keys, tag)
    actor_id = pick_soldier(host, client, used_actors, tag)
    if door_pick is not None:
        # the craft door has ONE standable side - the deck tile `near` -
        # and host leg's actor may still be standing on it. lightning_setup moves that
        # occupant to a free deck tile and places THIS actor on `near` facing the door;
        # `through` is the void tile at door z (the direction the door faces). The
        # facing-away teleport below re-places the actor on the SAME tile with the new
        # facing (the test command accepts a unit's own footprint, SavedBattleGame.cpp:2708).
        actor_id, stand, through, _far_ground, door = lightning_setup(
            host, client, tag, actor_id=actor_id, move_factions=False)
    else:
        stand, through = standable_side(host, door, tag)
    want_dir = session.dir_between(stand, through)
    away_dir = (want_dir + 4) % 8  # any facing that is NOT toward the door

    place_deterministic(host, client, [
        {"lever": "battle_teleport_unit", "unit": actor_id,
         "x": stand[0], "y": stand[1], "z": stand[2], "dir": away_dir},
    ], what=f"{tag} place actor {actor_id} at door {door_key} facing away")

    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, actor_id, CLIENT_LEG_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag} TU pinned")

    hunits0 = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    start_dir = hunits0.get(actor_id, {}).get("direction")
    assert start_dir == away_dir, (
        f"{tag}: actor {actor_id} starts facing {start_dir}, expected {away_dir} "
        f"(away from door {door_key})")

    census_before = session.door_census(host)
    before_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    before_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    before_seq = session.event_state(host)["lastSeqEmitted"]
    door_before = session.door_lookup(host, door_key)
    assert door_before is not None and door_before.get("isUfoDoorOpen") is False, (
        f"{tag}: door {door_key} is not closed before the turn: {door_before}")

    # ---- STEP 1, THE NEGATIVE CONTROL: a REAL rotation must NOT open the door.
    # UnitTurnBState::init() calls lookAt() FIRST (UnitTurnBState.cpp:73), and
    # BattleUnit::lookAt sets STATUS_TURNING whenever the facing actually CHANGES
    # (BattleUnit.cpp:1248-1270). The door-open branch is then gated on
    # `_chargeTUs && getStatus() != STATUS_TURNING` (:74), so a rotation that
    # really turns can never open a door - only the ZERO-TICK re-issue does.
    # connectionTCP.cpp:4912 names it: "UnitTurnBState::init()'s zero-tick
    # door-open branch". That is vanilla's real right-click behaviour: right-click
    # a door you are NOT facing and you only turn; right-click again and it opens.
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": actor_id,
                    "toDir": want_dir})
    assert r.get("iseq"), f"{tag}: the facing turn intent did not ship: {r}"
    wait_facing(host, client, actor_id, want_dir)
    W.settle_reveal(host, client)

    hunits = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    cunits = {u["id"]: u for u in session.battle_state(client).get("units", [])}
    hdir = hunits.get(actor_id, {}).get("direction")
    cdir = cunits.get(actor_id, {}).get("direction")
    assert hdir == want_dir and cdir == want_dir, (
        f"{tag}: actor {actor_id} facing host={hdir} client={cdir} after the turn, "
        f"expected {want_dir} on both machines")

    mid_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    assert mid_emitted == before_emitted, (
        f"{tag} NEGATIVE CONTROL: a REAL rotation ({start_dir} -> {want_dir}) opened "
        f"a door (coopDoorEvsEmitted {before_emitted} -> {mid_emitted}). That "
        "contradicts UnitTurnBState.cpp:74's STATUS_TURNING gate.")
    door_mid = session.door_lookup(host, door_key)
    assert door_mid is not None and door_mid.get("isUfoDoorOpen") is False, (
        f"{tag} NEGATIVE CONTROL: door {door_key} is no longer closed after a turn "
        f"that only rotated the actor: {door_mid}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after the rotation")
    print(f"    [{tag}] negative control OK: the rotation {start_dir} -> {want_dir} "
          f"turned the actor and left the door CLOSED (coopDoorEvsEmitted "
          f"{before_emitted})")

    # ---- STEP 2, THE ACTION UNDER TEST: the ZERO-TICK re-issue opens the door.
    before_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    before_emitted = mid_emitted
    before_seq = session.event_state(host)["lastSeqEmitted"]
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": actor_id,
                    "toDir": want_dir})
    assert r.get("iseq"), f"{tag}: the zero-tick turn intent did not ship: {r}"
    fired = wait_door_fired(host, client, before_emitted)
    W.settle_reveal(host, client)

    after_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    evs_since = [e for e in session.event_log(host, 160) if e["seq"] > before_seq]
    action_id = evs_since[0]["actionId"] if evs_since else None
    if after_emitted <= before_emitted:
        dump_record(tag, host, actor_id, stand, CLIENT_LEG_TU, door_key,
                   door_before.get("isUfoDoorOpen"), action_id=action_id)
        raise AssertionError(
            f"{tag}: the ZERO-TICK re-issue (actor already facing {want_dir}) "
            f"did NOT open the door (coopDoorEvsEmitted stayed {before_emitted}; "
            f"stream: {[e['kind'] for e in evs_since]}) - this contradicts "
            "UnitTurnBState.cpp:74-98's zero-tick door-open branch")

    door_kind_evs = [e for e in evs_since if e["kind"] == "door"]
    assert door_kind_evs, (
        f"{tag}: coopDoorEvsEmitted moved but no `door`-kind ev is in "
        f"the turn's own stream (stream: {[e['kind'] for e in evs_since]})")

    census_after = session.door_census(host)
    assert census_after != census_before, (
        f"{tag} NON-VACUITY: door census did not change across the turn-opens-door")

    door_after = session.door_lookup(host, door_key)
    if want_ufo:
        assert door_after is not None, (
            f"{tag}: UFO door {door_key} left the census entirely; "
            "door_census's documented rule is that a UFO door STAYS and flips "
            "isUfoDoorOpen - this contradicts it")
        assert door_after.get("isUfoDoorOpen") is True, (
            f"{tag}: UFO door {door_key} did not flip isUfoDoorOpen "
            f"False -> True: {door_after}")
    else:
        assert door_after is None, (
            f"{tag}: NON-UFO door {door_key} is still in the census after "
            f"opening ({door_after}); door_census's documented rule is that a normal "
            "door LEAVES the census entirely (Tile::openDoor clears the part's map "
            "data) - this contradicts it")

    session.assert_door_parity(host, client, what=f"{tag} census")

    after_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    moved = sorted(k for k in before_h if before_h[k] != after_h.get(k))
    assert moved, (
        f"{tag} NON-VACUITY: no hash bucket moved on the host across the "
        f"turn-opens-door - before={before_h} after={after_h}")

    assert_hash_clean(host, client, full=True, what=f"{tag} after the turn")

    print(f"[{tag}] turn-opens-{'UFO' if want_ufo else 'non-UFO'} door {door_key} "
          f"actor {actor_id}: {start_dir} -> {want_dir}; coopDoorEvsEmitted "
          f"{before_emitted} -> {after_emitted}; bucket(s) moved={moved}; census "
          f"{'stayed (isUfoDoorOpen True)' if want_ufo else 'LEFT (normal door)'}")
    return actor_id, door_key


# ===== the turn-boundary close, its no-op repeat, and the client refusal ====
# The craft-door phase leaves a UFO door open, so the boundary close has
# something to close and it mutates. The repeat-close and client-refusal phases
# drive the `battle_close_ufo_doors` test command.

def pick_walkthrough_door(host, want_ufo, exclude_keys, tag):
    """A door that can actually be WALKED through, not merely right-clicked.

    `standable_side()` only requires the NEAR side to be walkable, which is all a
    right-click needs. A walk-through additionally needs (1) the FAR side to be a
    real, walkable tile and (2) a walkable approach tile one step behind the near
    side, so the door ev lands BETWEEN two walk steps. Map-edge doors fail (1):
    a westwall door at x=0 has a far side of (-1, y, z), off the map, so the walk
    intent has no destination and legitimately never ships ("actorId does not
    resolve / no route"); observed 3 runs in 3 without this filter.

    Also skips any door whose Chebyshev distance to the nearest
    living hostile (position-based, from battle_state) is
    <= session.MAX_VIEW_DISTANCE - walk-through phase's actor must not spot on its
    approach walk.
    """
    occupied = {session.unit_pos(u) for u in session.battle_state(host).get("units", [])
                if not u.get("isOut")}
    hostiles = [u for u in session.battle_state(host).get("units", [])
                if u.get("faction") == session.FACTION_HOSTILE and not u.get("isOut")]
    rejected = []
    considered = 0
    best_dist = None
    for d in session.closed_doors(host):
        if bool(d.get("isUfoDoor")) != want_ufo:
            continue
        key = (d["x"], d["y"], d["z"], d["part"])
        if key in exclude_keys:
            continue
        considered += 1
        if hostiles:
            dist = min(session.cheb((d["x"], d["y"], d["z"]), session.unit_pos(h)) for h in hostiles)
            if dist <= session.MAX_VIEW_DISTANCE:
                best_dist = dist if best_dist is None else max(best_dist, dist)
                rejected.append(f"{key}: {dist} tiles from the nearest hostile "
                                f"(<= {session.MAX_VIEW_DISTANCE})")
                continue
        sides = session.door_sides(d)
        if not sides:
            continue
        for stand, through in (sides, (sides[1], sides[0])):
            if not session.tile_walkable(host, stand, occupied):
                continue
            if not session.tile_walkable(host, through, occupied):
                rejected.append(f"{key}: far side {through} not walkable (map edge?)")
                continue
            back = (stand[0] + (stand[0] - through[0]),
                    stand[1] + (stand[1] - through[1]), stand[2])
            if not session.tile_walkable(host, back, occupied):
                rejected.append(f"{key}: approach {back} not walkable")
                continue
            # A solid wall part on the approach edge back->stand (seen once: back's northwall,
            # mapDataID 65) makes the pathfinder detour, so the crossing is not the 2-step shape
            # walk-through phase asserts. Reject such a candidate up front.
            # Moving north crosses back's north edge; south crosses stand's north edge; west
            # crosses back's west edge; east crosses stand's west edge.
            ti_back = host.cmd({"cmd": "tile_info", "x": back[0], "y": back[1], "z": back[2]}).get("parts", {})
            ti_stand = host.cmd({"cmd": "tile_info", "x": stand[0], "y": stand[1], "z": stand[2]}).get("parts", {})
            dx, dy = stand[0] - back[0], stand[1] - back[1]
            if dx < 0:
                edge = ti_back.get("westwall", {})
            elif dx > 0:
                edge = ti_stand.get("westwall", {})
            elif dy < 0:
                edge = ti_back.get("northwall", {})
            else:
                edge = ti_stand.get("northwall", {})
            if edge.get("mapDataID", -1) >= 0:
                rejected.append(f"{key}: wall part (mapDataID {edge.get('mapDataID')}) on the "
                                f"approach edge {back}->{stand} (the pathfinder would detour)")
                continue
            return d, key, stand, through, back
    raise AssertionError(
        f"FIXTURE: {tag}: no closed {'UFO' if want_ufo else 'non-UFO'} door on this "
        f"map roll can be walked through (both sides + an approach tile) and is more "
        f"than {session.MAX_VIEW_DISTANCE} tiles from every living hostile "
        f"({considered} candidate(s) considered, best hostile distance {best_dist}). "
        f"Rejected: {rejected[:6]}")


def phase_walk_through_normal_door(host, client, tag, exclude_door_keys, used_actors):
    """WALK THROUGH a NON-UFO door.

    The client leg walks through a UFO door (which STAYS in the census and moves
    saveBlob/unitsStats); normal-door phase RIGHT-CLICKS a normal door (which LEAVES the
    census and moves terrain). This phase is the fourth corner: a normal door
    crossed by WALKING.

    Geometry is the client leg's: the actor starts ONE tile back from the near side so
    the door ev lands BETWEEN two walk steps (a one-step crossing cannot produce
    a walk_step before the door ev - session.py:881-890 makes the two sides
    exactly one tile apart).
    """
    door, door_key, stand, through, back = pick_walkthrough_door(
        host, False, exclude_door_keys, tag)
    actor_id = pick_soldier(host, client, used_actors, tag)

    place_deterministic(host, client, [
        {"lever": "battle_teleport_unit", "unit": actor_id,
         "x": back[0], "y": back[1], "z": back[2],
         "dir": session.dir_between(back, stand)},
    ], what=f"{tag} place actor {actor_id} one tile behind normal door {door_key}")

    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, actor_id, CLIENT_LEG_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag} TU pinned")

    census_before = session.door_census(host)
    before_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    before_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    door_before = session.door_lookup(host, door_key)
    assert door_before is not None, f"{tag}: normal door {door_key} vanished before the walk"

    prev = W.walk_action_id(host)
    resp = W.send_walk(client, actor_id, through)
    assert resp.get("iseq"), f"{tag}: the client-origin walk intent did not ship: {resp}"
    W.wait_walk_settled(host, client, prev)
    W.settle_reveal(host, client)

    hw = W.last_walk(host)
    action_id = hw.get("actionId")
    evs = session.action_events(host, action_id)

    # The KNOWN detour. Plain walk, then the check: the
    # crossing of THIS door is exactly two steps and the door leaves the census. Anything else
    # is the known flaky scenario -> full evidence record, loud banner, exit 2. Never retried.
    executed = hw.get("executed", [])
    planned_len = hw.get("plannedLen")
    door_after = session.door_lookup(host, door_key)
    if planned_len != 2 or len(executed) != 2 or door_after is not None:
        def _parts(t):
            ti = host.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
            return ti.get("parts") if ti.get("ok") else ti
        doors_resp = host.cmd({"cmd": "find_doors", "limit": 512})
        record = {
            "test": "repro_door_deterministic", "phase": tag, "tracking": "normal_door_walk_detour",
            "door": door_key, "door_before": door_before, "door_after": door_after,
            "stand": stand, "through": through, "back": back,
            "tiles": {"stand": _parts(stand), "through": _parts(through), "back": _parts(back)},
            "units_within_3": session.units_near(host, [stand, through, back], radius=3),
            "units_within_3_client": session.units_near(client, [stand, through, back], radius=3),
            "walk": {"actor": actor_id, "plannedLen": planned_len, "executed": executed,
                     "steps": hw.get("steps"), "restate": hw.get("restate")},
            "door_evs": [e for e in evs if e.get("kind") == "door"],
            "event_kinds": [e.get("kind") for e in evs],
            "map": {"x": doors_resp.get("mapSizeX"), "y": doors_resp.get("mapSizeY"),
                    "z": doors_resp.get("mapSizeZ")},
            "closed_doors_now": [(d["x"], d["y"], d["z"], d["part"]) for d in session.closed_doors(host)],
            "hash_equal": host.cmd({"cmd": "hash_now", "full": True}).get("h")
                          == client.cmd({"cmd": "hash_now", "full": True}).get("h"),
        }
        session.known_flake(
            "repro_door_deterministic", "normal_door_walk_detour",
            f"walk-through phase walk back->through of terrain door {door_key} was not a direct 2-step "
            f"crossing (planned {planned_len}, executed {len(executed)}, door still present: "
            f"{door_after is not None})",
            record)

    if not [e for e in evs if e["kind"] == "door"]:
        dump_record(tag, host, actor_id, back, CLIENT_LEG_TU, door_key,
                   door_before.get("isUfoDoorOpen"), action_id=action_id,
                   restate=hw.get("restate"))
        raise AssertionError(
            f"{tag}: walking through normal door {door_key} emitted NO "
            f"`door` ev (stream kinds: {[e['kind'] for e in evs]})")

    # the atom criterion, on BOTH machines
    session.assert_door_between_steps(host, action_id, what=f"{tag} stream position (host)")
    session.assert_door_between_steps(client, action_id, what=f"{tag} stream position (client)")

    after_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    assert after_emitted > before_emitted, (
        f"{tag}: coopDoorEvsEmitted did not advance ({before_emitted})")

    census_after = session.door_census(host)
    assert census_after != census_before, (
        f"{tag} NON-VACUITY: the door census did not change across the crossing")
    assert session.door_lookup(host, door_key) is None, (
        f"{tag}: NON-UFO door {door_key} is still in the census after being "
        "walked through; door_census's documented rule is that a normal door LEAVES "
        "it (Tile::openDoor clears the part's map data)")
    session.assert_door_parity(host, client, what=f"{tag} census")

    after_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    moved = sorted(k for k in before_h if before_h[k] != after_h.get(k))
    assert moved, f"{tag} NON-VACUITY: no hash bucket moved on the host"
    assert_hash_clean(host, client, full=True, what=f"{tag} after the crossing")

    hu = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    assert session.unit_pos(hu[actor_id]) == through, (
        f"{tag}: actor {actor_id} ended at {session.unit_pos(hu[actor_id])}, expected {through}")

    print(f"[{tag}] walk-through-non-UFO door {door_key} actor {actor_id}: "
          f"{back} -> {stand} -> {through}; coopDoorEvsEmitted {before_emitted} -> "
          f"{after_emitted}; bucket(s) moved={moved}; census LEFT (normal door)")
    return actor_id, door_key


def phase_boundary_close(host, client, tag):
    """Boundary-close phase, the MUTATING half, at a REAL end-of-turn:
    `BattlescapeGame::endTurn()` runs `coopCloseUfoDoors()` unconditionally on
    every call (guarded only by an idempotency latch `_triggerProcessed`, not
    by which side is being entered - `BattlescapeGame.cpp:576`), so the
    end-turn press(es) cross this boundary on the FIRST transition. Snapshot
    every OPEN UFO door the host reports (never a hard-coded key - which doors
    are open is measured), press through the boundary, and prove each of THOSE
    doors shut on both machines. A real end-of-turn press has no reply to
    check, so the failure signal is "no door ev reached the client within 30s"
    (`wait_door_fired`) plus the door-state assertions below.

    WHICH SEATS PRESS. `needed` counts LIVE seats. `bring_up()`'s craft
    (Lightning, `soldiers: 12`) only carries SIX soldiers in THIS mission/race
    combination (STR_TERROR_MISSION / STR_FLOATER), all six seated to
    COOP_SEAT_1 by `session.drive_to_battlescape`'s seat loop (`seat_count=8`
    default, stops the moment `newbattle_seat_soldier` fails) - a diagnostic
    boot of this exact fixture showed `seat0 (host) live player units: []`,
    `seat1 (client) live player units: [8, 9, 10, 11, 12, 13]`. Every actor in
    every phase is drawn from `session.seat_units(host)` (= seat 1). With ZERO
    live seat-0 units, `needed` is 1, so the CLIENT's OWN press alone completes
    readiness and the boundary transitions immediately - a host press waiting
    for an "END TURN 1/2" that this build (correctly) never paints would time
    out. The press below therefore measures which seats are actually live and
    never hard-codes needed==2."""
    print(f"\n== {tag}: boundary close (mutating, real end-of-turn) ==")
    open_before = {(d["x"], d["y"], d["z"], d["part"]): d
                   for d in session.find_doors(host) if d["isUfoDoorOpen"]}
    assert open_before, (
        f"{tag}: no UFO door is open entering boundary-close phase, although "
        "craft-door phase's own assertions left one open - something closed it in between")
    census_before = session.door_census(host)
    before_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    before_seq = session.event_state(host)["lastSeqEmitted"]
    side0 = session.battle_state(host)["side"]

    # ---- the real end-of-turn button press(es): seat 0 (host) is measured
    # live or not FIRST, never assumed - the client always arms through its
    # own real button; the host additionally presses ONLY when it holds a
    # live seat (after it paints "END TURN 1/2"), since a host press with no
    # live seat would never be counted toward `needed` in the first place. ----
    units0 = session.battle_state(host)["units"]
    host_live = [u for u in units0 if u.get("coop") == 0
                and u.get("faction") == session.FACTION_PLAYER and not u.get("isOut")]
    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    if host_live:
        def _host_shows_1_of_2():
            return True if session.battle_state(host).get("coopEndTurnText") == "END TURN 1/2" else None
        host.wait_for(f"{tag}: host paints END TURN 1/2 after the client's arm",
                      _host_shows_1_of_2, timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    else:
        print(f"[{tag}] host holds no live seat-0 unit (measured, not "
              f"assumed) - needed==1, the client's own press alone crosses "
              "the boundary")

    # ---- drive the host through the boundary ----
    if not wait_door_fired(host, client, before_emitted):
        dump_record(tag, host, None, None, None, next(iter(open_before)), True)
        raise AssertionError(
            f"{tag}: no door ev reached the client within 30s "
            "(a real end-of-turn press has no reply to check)")

    def _side_changed():
        return True if session.battle_state(host).get("side") != side0 else None
    host.wait_for(f"{tag}: host crosses the side boundary", _side_changed, timeout=30)

    after_by_key = {k: session.door_lookup(host, k) for k in open_before}
    still_open = {k: v for k, v in after_by_key.items()
                  if not v or v.get("isUfoDoorOpen") is not False}
    assert not still_open, (
        f"{tag}: {len(still_open)} previously-open UFO door(s) did not "
        f"read isUfoDoorOpen==False on the HOST after the close: {still_open}")
    after_by_key_c = {k: session.door_lookup(client, k) for k in open_before}
    still_open_c = {k: v for k, v in after_by_key_c.items()
                    if not v or v.get("isUfoDoorOpen") is not False}
    assert not still_open_c, (
        f"{tag}: {len(still_open_c)} previously-open UFO door(s) did "
        f"not read isUfoDoorOpen==False on the CLIENT after the close: "
        f"{still_open_c}")

    census_after = session.door_census(host)
    assert census_after != census_before, (
        f"{tag} NON-VACUITY: door census did not change across the boundary close")

    door_kind_evs = [e for e in session.action_events(host, 0) if e["kind"] == "door"]
    assert door_kind_evs, (
        f"{tag}: coopDoorEvsEmitted moved but no `door`-kind ev is in "
        "the actionId-0 stream")

    # ---- every `door` ev precedes EVERY `side_transition` ev in seq order, and there is
    # exactly one `door` ev per previously-open door. Boundary `door` evs ride
    # actionId 0 with no `unit`. ----
    boundary_evs = [e for e in session.event_log(client, tail=256) if e["seq"] > before_seq]
    triples = [(e["seq"], e["kind"], e["actionId"]) for e in boundary_evs]
    print(f"[{tag}] boundary window (client event_log, seq>{before_seq}): {triples}")
    client_door_evs = [e for e in boundary_evs if e["kind"] == "door" and e["actionId"] == 0]
    side_transition_evs = [e for e in boundary_evs if e["kind"] == "side_transition"]
    assert client_door_evs, (
        f"{tag}: no `door` ev (actionId 0) in the client's boundary "
        f"window: {triples}")
    assert side_transition_evs, (
        f"{tag}: no `side_transition` ev in the client's boundary "
        f"window: {triples}")
    assert len(client_door_evs) == len(open_before), (
        f"{tag}: expected exactly one `door` ev per previously-open "
        f"door ({len(open_before)}), got {len(client_door_evs)}: {client_door_evs}")
    max_door_seq = max(e["seq"] for e in client_door_evs)
    min_side_transition_seq = min(e["seq"] for e in side_transition_evs)
    assert max_door_seq < min_side_transition_seq, (
        f"{tag}: the boundary `door` ev(s) do NOT all precede every "
        f"`side_transition` ev in seq order - max door seq "
        f"{max_door_seq} >= min side_transition seq {min_side_transition_seq}: "
        f"{triples}")

    session.assert_door_parity(host, client, what=f"{tag} census")
    assert_hash_clean(host, client, full=True, what=f"{tag} after boundary close")
    after_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    print(f"[{tag}] real end-of-turn closed {len(open_before)} previously-open "
          f"UFO door(s) {sorted(open_before)}; coopDoorEvsEmitted {before_emitted} "
          f"-> {after_emitted}; door ev(s) all precede side_transition (max door "
          f"seq {max_door_seq} < min side_transition seq {min_side_transition_seq})")
    return census_after, after_emitted


def phase_boundary_close_noop(host, client, tag, census_before, emitted_before):
    """Repeat-close phase: 'nothing mutated => nothing emitted' - a real assertion, not
    a shrug, or every turn boundary would put an empty `door` ev on the wire."""
    print(f"\n== {tag}: boundary close (no-op) ==")
    before_seq = session.event_state(host)["lastSeqEmitted"]
    r = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert r.get("ok"), f"{tag}: battle_close_ufo_doors (no-op) failed: {r}"
    assert r.get("closed", -1) == 0, (
        f"{tag}: the no-op close reports closed={r.get('closed')}, "
        "expected 0 (every UFO door was already shut by boundary-close phase)")
    time.sleep(1.0)
    hs = session.event_state(host)
    assert hs["coopDoorEvsEmitted"] == emitted_before, (
        f"{tag}: coopDoorEvsEmitted moved ({emitted_before} -> "
        f"{hs['coopDoorEvsEmitted']}) although the test command mutated nothing")
    assert hs["lastSeqEmitted"] == before_seq, (
        f"{tag}: the no-op close minted a seq ({before_seq} -> "
        f"{hs['lastSeqEmitted']}) without mutating anything")
    census_after = session.door_census(host)
    assert census_after == census_before, (
        f"{tag}: door census changed on a no-op close - "
        f"before={census_before} after={census_after}")
    session.assert_door_parity(host, client, what=f"{tag} census")
    assert_hash_clean(host, client, full=True, what=f"{tag} after no-op close")
    print(f"[{tag}] closed=0, coopDoorEvsEmitted stayed {emitted_before} (NO-OP)")


def phase_client_refused(host, client, tag, census_before):
    """Client-refusal phase: the host-authoritative terrain guard (TestServer.cpp:4057).
    A refusal that still mutated would be the desync it exists to prevent."""
    print(f"\n== {tag}: client refusal ==")
    hs0 = session.event_state(host)["lastSeqEmitted"]
    cs0 = session.event_state(client)["coopDoorEvsEmitted"]
    r = client.cmd({"cmd": "battle_close_ufo_doors"})
    assert not r.get("ok"), (
        f"{tag}: a CLIENT was allowed to run battle_close_ufo_doors: {r}")
    assert "host-only" in r.get("error", ""), (
        f"{tag}: unexpected refusal reason: {r}")
    time.sleep(0.5)
    hs, cs = session.event_state(host), session.event_state(client)
    assert hs["lastSeqEmitted"] == hs0, (
        f"{tag}: the HOST minted a seq after a refused client call "
        f"({hs0} -> {hs['lastSeqEmitted']})")
    assert cs["coopDoorEvsEmitted"] == cs0, (
        f"{tag}: the CLIENT's own door-ev counter moved after its "
        f"refused local call ({cs0} -> {cs['coopDoorEvsEmitted']})")
    census_h, census_c = session.door_census(host), session.door_census(client)
    assert census_h == census_before, (
        f"{tag}: the HOST's door census changed after a refused "
        f"client call - before={census_before} after={census_h}")
    assert census_c == census_before, (
        f"{tag}: the CLIENT's door census changed after its own "
        f"refused call - before={census_before} after={census_c}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after client refusal")
    print(f"[{tag}] client refused ({r['error']!r}); nothing mutated on either machine")


def run_scenario(host, client, tag):
    # ---- step 2: build the situation on the Lightning's own UFO door ----
    client_actor, near, far, far_ground, door = lightning_setup(host, client, f"{tag} client-leg")
    door_at = (door["x"], door["y"], door["z"], door["part"])

    # ---- step 3: assert the SITUATION explicitly ----
    d0 = session.door_lookup(host, door_at)
    assert d0 is not None and d0.get("isUfoDoorOpen") is False, (
        f"{tag}: door {door_at} is not closed after placement: {d0}")
    units0 = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    a0 = units0[client_actor]
    assert session.unit_pos(a0) == near, (
        f"{tag}: actor {client_actor} sits at {session.unit_pos(a0)}, expected {near}")
    want_dir = session.dir_between(near, far)
    assert a0.get("direction") == want_dir, (
        f"{tag}: actor {client_actor} faces {a0.get('direction')}, expected {want_dir} "
        f"(toward {far})")
    # lightning_setup's own hostile-distance assertion (position-based,
    # HOSTILE-only, on battle_state) already covers the no-contact premise.
    assert_hash_clean(host, client, full=True, what=f"{tag} after placement")

    # ---- step 3.5: back the actor up ONE
    # tile so the door ev lands BETWEEN two walk steps. near/far are always
    # exactly one tile apart (session.py:881-890), so a one-step walk cannot
    # produce a walk_step BEFORE the door ev; the crossing becomes
    # back -> near -> far: step, door, step.
    back = (near[0] + (near[0] - far[0]), near[1] + (near[1] - far[1]), near[2])
    st = session.battle_state(host)
    occupied = {session.unit_pos(u) for u in st["units"] if not u.get("isOut")}
    moves = []
    back_occupant = next((u for u in st["units"] if session.unit_pos(u) == back
                          and u["id"] != client_actor and not u.get("isOut")), None)
    if back_occupant is not None:
        # The same occupant-move lightning_setup does for `near`, using
        # a local copy of its own deck-scan, applied here for `back`.
        deck = [(x, y, near[2]) for y in range(door["y"] - 4, door["y"] + 5)
                for x in range(door["x"] - 4, door["x"] + 5)]
        free = next((t for t in deck if t not in (near, far, back)
                     and session.tile_walkable(host, t, occupied)), None)
        assert free is not None, (
            f"FIXTURE: {tag} client leg: no free deck tile to move unit {back_occupant['id']} off {back}")
        moves.append({"lever": "battle_teleport_unit", "unit": back_occupant["id"],
                      "x": free[0], "y": free[1], "z": free[2],
                      "dir": back_occupant.get("direction", 0)})
        occupied = occupied - {back}
    if not session.tile_walkable(host, back, occupied):
        raise AssertionError(
            f"FIXTURE: {tag} client leg: the one-tile-back approach {back} is not "
            "walkable or is occupied - this map roll cannot supply client leg's "
            "door-between-steps geometry")
    moves.append({"lever": "battle_teleport_unit", "unit": client_actor,
                  "x": back[0], "y": back[1], "z": back[2], "dir": session.dir_between(back, near)})
    place_deterministic(host, client, moves,
                        what=f"{tag} client leg back up one tile for the door-between-steps geometry")
    # place_deterministic's own gate already re-asserts assert_hash_clean(full=True).

    # ---- step 4: CLIENT LEG - CLIENT-origin crossing, HOST reserve aimed+kneel ----
    W.set_reserve(host, mode="aimed", kneel=True)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, client_actor, CLIENT_LEG_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag} client leg TU pinned")

    emitted0 = session.event_state(host)["coopDoorEvsEmitted"]
    waived0 = session.event_state(host)["coopDoorReserveWaived"]
    census_before_client = session.door_census(host)  # non-vacuity control

    prev = W.walk_action_id(host)
    resp = W.send_walk(client, client_actor, far_ground)
    assert resp.get("iseq"), f"{tag} client leg: the client-origin walk intent did not ship: {resp}"
    W.wait_walk_settled(host, client, prev)
    W.settle_reveal(host, client)

    hw = W.last_walk(host)
    action_id = hw.get("actionId")
    evs = session.action_events(host, action_id)
    door_evs = [e for e in evs if e["kind"] == "door"]
    if not door_evs:
        dump_record(f"{tag} client leg", host, client_actor, back, CLIENT_LEG_TU, door_at, False,
                   action_id=action_id, restate=hw.get("restate"))
        raise AssertionError(
            f"{tag} client leg: the client-origin crossing emitted NO `door` ev "
            f"under the host's aimed+kneel reserve (stream kinds: "
            f"{[e['kind'] for e in evs]})")

    # ---- the door ev's STREAM POSITION on BOTH machines, plus a door-census
    # change + parity. On a failure here (the one-tile-back geometry did not
    # produce a leading walk_step), print the instrumented record before
    # propagating.
    try:
        session.assert_door_between_steps(host, action_id, what=f"{tag} client leg stream position (host)")
        session.assert_door_between_steps(client, action_id, what=f"{tag} client leg stream position (client)")
    except AssertionError:
        dump_record(f"{tag} client leg stream-position", host, client_actor, back, CLIENT_LEG_TU,
                   door_at, False, action_id=action_id, restate=hw.get("restate"))
        raise
    census_after_client = session.door_census(host)
    assert census_after_client != census_before_client, (
        f"{tag} client leg NON-VACUITY: door census did not change across the crossing")
    session.assert_door_parity(host, client, what=f"{tag} client leg census")

    d1 = session.door_lookup(host, door_at)
    assert d1 is not None and d1.get("isUfoDoorOpen") is True, (
        f"{tag} client leg: door {door_at} did not go isUfoDoorOpen False -> True: {d1}")
    hs = session.event_state(host)
    emitted_client = hs["coopDoorEvsEmitted"]
    waived_client = hs["coopDoorReserveWaived"]
    assert emitted_client > emitted0, (
        f"{tag} client leg: coopDoorEvsEmitted did not increase ({emitted0} -> {emitted_client})")
    assert waived_client > waived0, (
        f"{tag} client leg: coopDoorReserveWaived did not increase ({waived0} -> "
        f"{waived_client}) - the host's own reserve was not neutralised for a "
        "client-origin door")
    units_after_client = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    final_pos = session.unit_pos(units_after_client[client_actor])
    assert final_pos == far_ground, (
        f"{tag} client leg: actor {client_actor} ended at {final_pos}, expected {far_ground}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after client leg")
    print(f"[{tag}] client leg: coopDoorEvsEmitted {emitted0} -> {emitted_client}, "
          f"coopDoorReserveWaived {waived0} -> {waived_client}")

    # ---- step 5: HOST LEG - HOST-origin control, SAME host reserve ----
    rc = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rc.get("ok"), f"{tag} host leg: battle_close_ufo_doors failed: {rc}"
    d2 = session.door_lookup(host, door_at)
    assert d2 is not None and d2.get("isUfoDoorOpen") is False, (
        f"{tag} host leg: door {door_at} did not re-close: {d2}")

    others = sorted(u["id"] for u in session.seat_units(host) if u["id"] != client_actor)
    assert others, f"FIXTURE: {tag} host leg: no second live seat-1 soldier for the control leg"
    second_id = others[0]

    second_id, host_near, host_far, host_far_ground, host_door = lightning_setup(
        host, client, f"{tag} host-leg", actor_id=second_id, move_factions=False)
    assert (host_door["x"], host_door["y"], host_door["z"], host_door["part"]) == door_at, (
        f"{tag} host leg: the host leg staged on a different door {host_door} than the "
        f"client leg's {door_at}; a Lightning map carries exactly one craft door")

    # ---- BASELINE: reserve=none, does this actor/door/TU open at all? ----
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, second_id, HOST_LEG_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag} host leg baseline TU pinned")

    emitted_base0 = session.event_state(host)["coopDoorEvsEmitted"]
    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": second_id,
                  "x": host_far[0], "y": host_far[1], "z": host_far[2]})
    assert ra.get("ok"), f"{tag} host leg baseline: battle_action door failed: {ra}"
    opened = wait_counter(host, lambda es: es["coopDoorEvsEmitted"] > emitted_base0)
    W.settle_reveal(host, client)
    if not opened:
        dump_record(f"{tag} host leg baseline", host, second_id, host_near, HOST_LEG_TU, door_at,
                   False)
        raise AssertionError(
            f"{tag} host leg: the baseline host-origin order (reserve=none) did "
            f"NOT open door {door_at} - the fixture, not the rule, is wrong")
    assert_hash_clean(host, client, full=True, what=f"{tag} host leg baseline opened")
    emitted_base1 = session.event_state(host)["coopDoorEvsEmitted"]
    print(f"[{tag}] host leg baseline: coopDoorEvsEmitted {emitted_base0} -> "
          f"{emitted_base1}")

    # ---- re-arm: close it again, re-pin TU, only the reserve changes next ----
    rc = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rc.get("ok"), f"{tag} host leg: re-close failed: {rc}"
    # pin_tu sets the CLIENT's TU first. Wait until the client has applied the
    # re-close's door ev (seq barrier) first: that ev's unitsStats hash carries the TU the baseline left, so a
    # client TU write landing before it is a DESYNC and an automatic repair.
    session.wait_seq_barrier(host, client)
    pin_tu(host, client, second_id, HOST_LEG_TU)
    d3 = session.door_lookup(host, door_at)
    assert d3 is not None and d3.get("isUfoDoorOpen") is False, (
        f"{tag} host leg: door {door_at} did not re-close before the control: {d3}")
    assert_hash_clean(host, client, full=True, what=f"{tag} host leg re-armed for control")

    # ---- CONTROL: SAME host reserve, IDENTICAL host-origin order ----
    W.set_reserve(host, mode="aimed", kneel=True)
    W.set_reserve(client, mode="none", kneel=False)
    waived_control0 = session.event_state(host)["coopDoorReserveWaived"]
    emitted_control0 = session.event_state(host)["coopDoorEvsEmitted"]
    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": second_id,
                  "x": host_far[0], "y": host_far[1], "z": host_far[2]})
    assert ra.get("ok"), f"{tag} host leg control: battle_action door failed: {ra}"
    opened = wait_counter(host, lambda es: es["coopDoorEvsEmitted"] > emitted_control0, timeout=5)
    time.sleep(1.0)
    W.settle_reveal(host, client)
    hs = session.event_state(host)
    door_opened = opened or hs["coopDoorEvsEmitted"] != emitted_control0
    waive_fired = hs["coopDoorReserveWaived"] != waived_control0
    # check BOTH signals before raising - a door opened WITHOUT the
    # waive moving is a TU-affordability outcome (Tile::openDoor's own cost
    # check), not proof the waive predicate fired for a HOST-origin action.
    if door_opened or waive_fired:
        dump_record(f"{tag} host leg control", host, second_id, host_near, HOST_LEG_TU, door_at,
                   False)
        print(f"      coopDoorReserveWaived before={waived_control0} after={hs['coopDoorReserveWaived']}")
        if waive_fired:
            raise AssertionError(
                f"{tag} host leg: coopDoorReserveWaived moved ({waived_control0} -> "
                f"{hs['coopDoorReserveWaived']}) for a HOST-origin door - the waive "
                "predicate fired when it must not have (origin was not \"intent\")")
        raise AssertionError(
            f"{tag} host leg: the control leg OPENED the door under the IDENTICAL host "
            f"reserve that the baseline needed reserve=none to clear, but "
            f"coopDoorReserveWaived did NOT move ({waived_control0} unchanged) - NOT the "
            "client-origin reserve waive; HOST_LEG_TU is affordable for Tile::openDoor's own "
            "BattleActionCost(reserve).haveTU() check regardless of origin")
    d4 = session.door_lookup(host, door_at)
    assert d4 is not None and d4.get("isUfoDoorOpen") is False, (
        f"{tag} host leg: door {door_at} is open after the refused control: {d4}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after host leg")
    print(f"[{tag}] host leg control: coopDoorEvsEmitted stayed {emitted_control0}, "
          f"coopDoorReserveWaived stayed {waived_control0} (REFUSED)")

    # ---- step 6: restore + final hash gate ----
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    assert_hash_clean(host, client, full=True, what=f"{tag} final")

    # ---- Craft-door phase: THE TURN IS THE RIGHT-CLICK on the SAME craft door, another
    # soldier - re-close it first (host leg's control left it closed already,
    # but this is the fixture's own precondition, not an assumption).
    def _craft_door_pick(h):
        d, _, _ = lightning_door(h)
        return d, (d["x"], d["y"], d["z"], d["part"])

    rb = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rb.get("ok"), f"{tag} craft-door phase: battle_close_ufo_doors failed: {rb}"
    d5 = session.door_lookup(host, door_at)
    assert d5 is not None and d5.get("isUfoDoorOpen") is False, (
        f"{tag} craft-door phase: the craft door {door_at} is not closed before "
        f"craft-door phase: {d5}")

    used_actors = {client_actor, second_id}
    craft_turn_actor, craft_turn_door_key = phase_turn_opens_door(
        host, client, f"{tag} craft-door phase", want_ufo=True,
        exclude_door_keys=set(), used_actors=used_actors, door_pick=_craft_door_pick)

    # ---- Normal-door phase: same shape on a NON-UFO door, another soldier ----
    used_actors.add(craft_turn_actor)
    normal_turn_actor, normal_turn_door_key = phase_turn_opens_door(
        host, client, f"{tag} normal-door phase", want_ufo=False,
        exclude_door_keys={door_at, craft_turn_door_key}, used_actors=used_actors)
    used_actors.add(normal_turn_actor)

    # ---- Walk-through phase, then Boundary-close phase: BOUNDARY CLOSE, the mutating half ----
    print(f"\n== {tag} walk-through phase: WALK through a NON-UFO door ==")
    walk_actor, walk_door_key = phase_walk_through_normal_door(
        host, client, f"{tag} walk-through phase",
        exclude_door_keys={door_at, craft_turn_door_key, normal_turn_door_key}, used_actors=used_actors)
    used_actors.add(walk_actor)

    census_after_close, emitted_after_close = phase_boundary_close(host, client, f"{tag} boundary-close phase")

    # ---- Repeat-close phase: the immediate NO-OP repeat ----
    phase_boundary_close_noop(host, client, f"{tag} repeat-close phase", census_after_close, emitted_after_close)

    # ---- Client-refusal phase: CLIENT REFUSAL (host-authoritative terrain guard) ----
    phase_client_refused(host, client, f"{tag} client-refusal phase", census_after_close)


def run_fixture(tag):
    """One boot, no retry - a `FIXTURE:` staging failure
    propagates straight to `__main__`'s is_fixture_error mapping (exit 2)
    instead of being caught and retried here."""
    host, client = bring_up()
    try:
        run_scenario(host, client, tag)
        print(f"[{tag}] PASSED")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_fixture("door_det")
    print("repro_door_deterministic: PASS")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("repro_door_deterministic", e.tracking, str(e))
        print(f"\nrepro_door_deterministic: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(EXIT_FAIL)
    except AssertionError as e:
        if is_fixture_error(e):
            print(f"\nrepro_door_deterministic: FAIL (fixture not constructed) - {e}")
            sys.exit(EXIT_FAIL)
        print(f"\nrepro_door_deterministic: FAIL\nAssertionError: {e}")
        sys.exit(EXIT_FAIL)
    except TimeoutError as e:
        print(f"\nrepro_door_deterministic: FAIL\nTimeoutError: {e}")
        sys.exit(EXIT_FAIL)
