"""SPEC 6d (P10-ACCEPT, REV E.8, WV-D78/WV-D79): the PURPOSE-BUILT
deterministic door test, its OWN file rather than a retrofit onto
repro_atom_door.py (NOT touched here) - five prior cycles collided with that
file's map-rolled SEARCH machinery, never with coop door behaviour (WV-D78).
The WV-D63 placement lever removes the need to search: teleport every
hostile away, teleport a soldier next to a named closed UFO door, walk it
through, and re-prove WV-D59 (the host must not apply its own TU reserve to
a client-origin door) in both directions, with a host-origin control leg.

DETERMINISTIC fixture (WV-D65): the SITUATION comes from the Lightning
craft's own UFO door (WV-D87) plus place_deterministic's own hash-equality
gate - bar is 3 CONSECUTIVE GREEN, not 10. SPEC 0e-2 (WV-D86) removes the
map search entirely: ONE boot, no retry of any kind. A `FIXTURE:`-prefixed
staging failure SKIPs (exit 3, WV-D72); anything else is a real FAIL (exit 2).

THE TRAP AVOIDED (WV-D77): `event_log`'s probe is a fixed-size POD (`seq`,
`actionId`, `kind`, `h`, no `payload` - BattlePump.h:206-219 /
TestServer.cpp:4524-4542), so the door ev is matched on `kind == "door"`
alone; the OPEN is proved by the counter deltas and the door's own
`isUfoDoorOpen` False->True transition.

SPEC 6e (REV E.9) EXTENSION - three more phases, same battle, still no
search. Phase A (leg (a) above) additionally proves the door ev's STREAM
POSITION on both machines (`session.assert_door_between_steps`) and a door-census
change + parity (`session.door_census`/`session.assert_door_parity`). Phase B opens a
SECOND, DIFFERENT UFO door with a SECOND soldier; phase C opens a THIRD,
NON-UFO door with a THIRD soldier. A UFO door STAYS in the census and flips
`isUfoDoorOpen`; a NORMAL door LEAVES the census entirely because
`Tile::openDoor` clears the part's map data (`door_census`'s own docstring).
No bucket name is hard-coded: only "at least one moved, printed by name" is
asserted.

SPEC 6f AMENDMENT (REV E.11) - fixes leg (a)'s geometry (actor starts one tile
back of `near` so the crossing is back->near->far with a walk_step either
side of the door) and adds phases D/D2/E: the WV-D50 boundary close (MUTATING
- phase B leaves a UFO door open, unlike repro_atom_door.py's own fixture),
its no-op repeat, and the client's host-only refusal. Which door(s) are open
at D is MEASURED, never assumed.

SPEC 6f AMENDMENT 2 (REV E.12) - THE TURN IS THE RIGHT-CLICK. Verified at
source: `UnitTurnBState::init()` (UnitTurnBState.cpp:74-98), when
`_chargeTUs` (default true) and `_action.type == BA_NONE` (the client turn
intent's default, connectionTCP.cpp:3720-3732), UNCONDITIONALLY calls
`coopUnitOpensDoor(te, unit, rClick=true, dir=-1)` - there is no separate
right-click action in vanilla; facing a door IS opening it. Phases B/C
therefore place their actor FACING AWAY and open the door with exactly ONE
client `battle_intent {kind:"turn"}` - no `battle_action {action:"door"}`
follows it.

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

MISSION = "STR_TERROR_MISSION"
RACE = "STR_FLOATER"
CRAFT = "STR_LIGHTNING"
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


def is_fixture_error(e):
    return str(e).startswith("FIXTURE:")


def _pin(h):
    """SPEC 0e-2 (WV-D87/WV-D88): pin the Lightning craft, then the floater
    race - order matters, drive_to_battlescape calls this AFTER the mission
    pin (cbxMissionChange has already rebuilt the race list by then) and
    BEFORE any seat is picked."""
    h.ok({"cmd": "newbattle_craft", "type": CRAFT})
    h.ok({"cmd": "newbattle_race", "race": RACE})


def bring_up():
    """SPEC 0e-2 (WV-D86): one boot, no retry - ports/dirs keep the same
    offsets the single remaining attempt (1) used."""
    port = str(BASE_GAME_PORT + 1)
    host = GameClient("det-host", BASE_TEST_PORT + 2,
                      make_user_dir("door_det_host_1"))
    client = GameClient("det-client", BASE_TEST_PORT + 3,
                        make_user_dir("door_det_client_1"))
    W.bring_up_lobby(host, client, port)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, pre_seat=_pin)
    return host, client


def pin_tu(host, client, actor_id, tu):
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_action", "action": "set_stat", "unit": actor_id,
                   "stat": "tu", "value": tu, "refill": True})
        assert r.get("ok"), f"pin_tu({gc.name}): set_stat failed: {r}"


def wait_counter(host, pred, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred(session.event_state(host)):
            return True
        time.sleep(0.1)
    return False

def dump_record(what, host, actor_id, pos_before, tu_before, door_at, open_before,
                action_id=None, restate=None):
    """WV-D77's instrumented record: actor id, position/TU before/after, the
    door's `isUfoDoorOpen` before/after, ev-kind sequence, halted, reason."""
    units = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    after = units.get(actor_id)
    door_after = session.door_lookup(host, door_at)
    kinds = ([e["kind"] for e in session.action_events(host, action_id)]
             if action_id is not None else [])
    restate = restate or {}
    print(f"    [{what} INSTRUMENTED RECORD - WV-D77]")
    print(f"      actor {actor_id} pos before={pos_before} "
          f"after={session.unit_pos(after) if after else 'UNIT NOT FOUND'}; "
          f"tu before={tu_before} after={after.get('tu') if after else None}")
    print(f"      door {door_at} isUfoDoorOpen before={open_before} "
          f"after={door_after.get('isUfoDoorOpen') if door_after else 'DOOR NOT FOUND'}")
    print(f"      ev-kind sequence: {kinds}")
    print(f"      restate: halted={restate.get('halted')} reason={restate.get('reason')} "
          f"path={restate.get('path')}")


# ===== SPEC 0e-2 (WV-D87): the Lightning craft's own UFO door - legs (a)/(b) ====
# and phase B all stage on this ONE door now, replacing contact_free_ufo_door_setup.

lightning_door = session.lightning_door


def lightning_setup(host, client, tag, actor_id=None, move_factions=True):
    """WV-D87 staging on the craft door. Returns (actor_id, near, far, far_ground, door).
    near = the standable side (deck), far = the void side at door z, far_ground = far one level
    down (the exit tile). Hostiles -> the corner farthest from the door, neutrals -> the
    opposite corner (WV-D88), both machines, hash gate; the actor -> near, facing far."""
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


# ===== SPEC 6f AMENDMENT 2 phases B/C: THE TURN IS THE RIGHT-CLICK, on a ====
# NAMED, PLACED door with its OWN soldier - a plain exclusion filter over
# session.closed_doors() / session.seat_units(), never a ranked/qualified candidate
# search. Shared by both phases; `want_ufo` selects which of the two
# documented census behaviours (`door_census`'s own docstring) the phase
# asserts.

def pick_door(host, want_ufo, exclude_keys, tag):
    """The first CLOSED door of the requested kind whose (x,y,z,part) is not
    already spoken for and is more than session.MAX_VIEW_DISTANCE tiles
    (Chebyshev, position-based, from battle_state) from every living hostile
    (SPEC 0e-2: the actor must not spot on its approach) - not a ranking, a
    plain exclusion. Missing on this map roll => FIXTURE (WV-D72), never a red."""
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
    it - session.tile_walkable against live occupancy, SPEC 6e's own named helper
    for exactly this."""
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
    """The OLD file's own bounded poll for its right-click phase, reimplemented
    locally (its session.wait_host_idle sibling is outside SPEC 6e's allow-list):
    the host emitted a NEW door ev AND the client has caught all the way up.
    Bounded so a refusal REPORTS instead of hanging to a bare TimeoutError.
    Still used by phase D (SPEC 6f's boundary close)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hs, cs = session.event_state(host), session.event_state(client)
        if (hs["coopDoorEvsEmitted"] > before_emitted
                and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                and cs.get("queueDepth") == 0):
            return True
        time.sleep(0.1)
    return False


def phase_turn_opens_door(host, client, tag, want_ufo, exclude_door_keys, used_actors,
                          door_pick=None):
    """SPEC 6f AMENDMENT 2 phases B ('want_ufo=True') and C ('want_ufo=False'):
    THE TURN IS THE RIGHT-CLICK, but ONLY on a ZERO-TICK re-issue. Actor is
    placed FACING AWAY from a NAMED, PLACED door, then: (1) a turn intent
    toward the door ROTATES it and must NOT open the door - the negative
    control, because lookAt() sets STATUS_TURNING and UnitTurnBState.cpp:74
    gates the door-open on `getStatus() != STATUS_TURNING`; (2) the SAME turn
    intent re-issued is now zero-tick and MUST open it
    (connectionTCP.cpp:4912, "zero-tick door-open branch"). No separate
    `battle_action {action:"door"}` is involved. Returns (actor_id, door_key) so
    a later phase can exclude both.

    SPEC 0e-2: `door_pick(host) -> (door, door_key)`, when given, replaces
    `pick_door(...)` - phase B uses it to stay on the Lightning's own craft
    door (WV-D87) instead of picking a second one."""
    if door_pick is not None:
        door, door_key = door_pick(host)
    else:
        door, door_key = pick_door(host, want_ufo, exclude_door_keys, tag)
    actor_id = pick_soldier(host, client, used_actors, tag)
    if door_pick is not None:
        # REV E.20 (WV-D87): the craft door has ONE standable side - the deck tile `near` -
        # and leg (b)'s actor may still be standing on it. lightning_setup moves that
        # occupant to a free deck tile and places THIS actor on `near` facing the door;
        # `through` is the void tile at door z (the direction the door faces). The
        # facing-away teleport below re-places the actor on the SAME tile with the new
        # facing (the lever accepts a unit's own footprint, SavedBattleGame.cpp:2708).
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
    pin_tu(host, client, actor_id, LEG_A_TU)
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
        dump_record(tag, host, actor_id, stand, LEG_A_TU, door_key,
                   door_before.get("isUfoDoorOpen"), action_id=action_id)
        raise AssertionError(
            f"{tag}: STOP-IF - the ZERO-TICK re-issue (actor already facing {want_dir}) "
            f"did NOT open the door (coopDoorEvsEmitted stayed {before_emitted}; "
            f"stream: {[e['kind'] for e in evs_since]}) - this contradicts "
            "UnitTurnBState.cpp:74-98's zero-tick door-open branch")

    door_kind_evs = [e for e in evs_since if e["kind"] == "door"]
    assert door_kind_evs, (
        f"{tag}: STOP-IF - coopDoorEvsEmitted moved but no `door`-kind ev is in "
        f"the turn's own stream (stream: {[e['kind'] for e in evs_since]})")

    census_after = session.door_census(host)
    assert census_after != census_before, (
        f"{tag} NON-VACUITY: door census did not change across the turn-opens-door")

    door_after = session.door_lookup(host, door_key)
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


# ===== SPEC 6f phases D/D2/E: the WV-D50 turn-boundary close, its no-op ====
# repeat, and the client refusal - repro_atom_door.py's own fixture never had
# an open UFO door, so its boundary phase could only ever be a no-op; here
# phase B leaves one open, so this drives the SAME `battle_close_ufo_doors`
# lever (real endTurn wiring is W1-P13's, per CoopDoor.h:65-67) and it mutates.

def pick_walkthrough_door(host, want_ufo, exclude_keys, tag):
    """A door that can actually be WALKED through, not merely right-clicked.

    `standable_side()` only requires the NEAR side to be walkable, which is all a
    right-click needs. A walk-through additionally needs (1) the FAR side to be a
    real, walkable tile and (2) a walkable approach tile one step behind the near
    side, so the door ev lands BETWEEN two walk steps. Map-edge doors fail (1):
    a westwall door at x=0 has a far side of (-1, y, z), off the map, so the walk
    intent has no destination and legitimately never ships ("actorId does not
    resolve / no route"). Observed 3/3 before this filter existed.

    SPEC 0e-2: also skips any door whose Chebyshev distance to the nearest
    living hostile (position-based, from battle_state) is
    <= session.MAX_VIEW_DISTANCE - phase F's actor must not spot on its
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
            return d, key, stand, through, back
    raise AssertionError(
        f"FIXTURE: {tag}: no closed {'UFO' if want_ufo else 'non-UFO'} door on this "
        f"map roll can be walked through (both sides + an approach tile) and is more "
        f"than {session.MAX_VIEW_DISTANCE} tiles from every living hostile "
        f"({considered} candidate(s) considered, best hostile distance {best_dist}). "
        f"Rejected: {rejected[:6]}")


def phase_walk_through_normal_door(host, client, tag, exclude_door_keys, used_actors):
    """SPEC 6g step 0: WALK THROUGH a NON-UFO door.

    The last combination `repro_atom_door.py` covered that this file did not.
    Phase A walks through a UFO door (which STAYS in the census and moves
    saveBlob/unitsStats); phase C RIGHT-CLICKS a normal door (which LEAVES the
    census and moves terrain). This phase is the fourth corner: a normal door
    crossed by WALKING, which is what the old file's small-scout leg did with
    `moving_bucket="terrain"`.

    Geometry is phase A's: the actor starts ONE tile back from the near side so
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
    pin_tu(host, client, actor_id, LEG_A_TU)
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

    # WV-D90 (owner D13, 2026-09-06): the KNOWN detour. Plain walk, then the check: the
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
            "test": "repro_door_deterministic", "phase": tag, "tracking": "WV-D90",
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
            "repro_door_deterministic", "WV-D90",
            f"phase F walk back->through of terrain door {door_key} was not a direct 2-step "
            f"crossing (planned {planned_len}, executed {len(executed)}, door still present: "
            f"{door_after is not None})",
            record)

    if not [e for e in evs if e["kind"] == "door"]:
        dump_record(tag, host, actor_id, back, LEG_A_TU, door_key,
                   door_before.get("isUfoDoorOpen"), action_id=action_id,
                   restate=hw.get("restate"))
        raise AssertionError(
            f"{tag}: STOP-IF - walking through normal door {door_key} emitted NO "
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
        f"{tag}: STOP-IF - NON-UFO door {door_key} is still in the census after being "
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
    """Phase D, the MUTATING half: snapshot every OPEN UFO door the host
    reports (never a hard-coded key - which doors are open is measured), close
    them, and prove each of THOSE doors shut."""
    print(f"\n== {tag}: boundary close (mutating) ==")
    open_before = {(d["x"], d["y"], d["z"], d["part"]): d
                   for d in session.find_doors(host) if d["isUfoDoorOpen"]}
    assert open_before, (
        f"{tag}: STOP-IF - no UFO door is open entering phase D, although "
        "phase B's own assertions left one open - something closed it in between")
    census_before = session.door_census(host)
    before_emitted = session.event_state(host)["coopDoorEvsEmitted"]

    r = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert r.get("ok"), f"{tag}: battle_close_ufo_doors failed: {r}"
    closed = r.get("closed", 0)
    assert closed > 0, (
        f"{tag}: STOP-IF - the lever reports ok but closed={closed} while "
        f"{len(open_before)} UFO door(s) were open: {sorted(open_before)}")

    if not wait_door_fired(host, client, before_emitted):
        dump_record(tag, host, None, None, None, next(iter(open_before)), True)
        raise AssertionError(
            f"{tag}: STOP-IF - closed={closed} but no door ev reached the client "
            "within 30s")

    after_by_key = {k: session.door_lookup(host, k) for k in open_before}
    still_open = {k: v for k, v in after_by_key.items()
                  if not v or v.get("isUfoDoorOpen") is not False}
    assert not still_open, (
        f"{tag}: STOP-IF - {len(still_open)} previously-open UFO door(s) did not "
        f"read isUfoDoorOpen==False after the close: {still_open}")

    census_after = session.door_census(host)
    assert census_after != census_before, (
        f"{tag} NON-VACUITY: door census did not change across the boundary close")

    door_kind_evs = [e for e in session.action_events(host, 0) if e["kind"] == "door"]
    assert door_kind_evs, (
        f"{tag}: STOP-IF - coopDoorEvsEmitted moved but no `door`-kind ev is in "
        "the actionId-0 stream")

    session.assert_door_parity(host, client, what=f"{tag} census")
    assert_hash_clean(host, client, full=True, what=f"{tag} after boundary close")
    after_emitted = session.event_state(host)["coopDoorEvsEmitted"]
    print(f"[{tag}] closed={closed} previously-open UFO door(s) "
          f"{sorted(open_before)}; coopDoorEvsEmitted {before_emitted} -> {after_emitted}")
    return census_after, after_emitted


def phase_boundary_close_noop(host, client, tag, census_before, emitted_before):
    """Phase D2: 'nothing mutated => nothing emitted' - a real assertion, not
    a shrug, or every turn boundary would put an empty `door` ev on the wire."""
    print(f"\n== {tag}: boundary close (no-op) ==")
    before_seq = session.event_state(host)["lastSeqEmitted"]
    r = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert r.get("ok"), f"{tag}: battle_close_ufo_doors (no-op) failed: {r}"
    assert r.get("closed", -1) == 0, (
        f"{tag}: STOP-IF - the no-op close reports closed={r.get('closed')}, "
        "expected 0 (every UFO door was already shut by phase D)")
    time.sleep(1.0)
    hs = session.event_state(host)
    assert hs["coopDoorEvsEmitted"] == emitted_before, (
        f"{tag}: STOP-IF - coopDoorEvsEmitted moved ({emitted_before} -> "
        f"{hs['coopDoorEvsEmitted']}) although the lever mutated nothing")
    assert hs["lastSeqEmitted"] == before_seq, (
        f"{tag}: STOP-IF - the no-op close minted a seq ({before_seq} -> "
        f"{hs['lastSeqEmitted']}) without mutating anything")
    census_after = session.door_census(host)
    assert census_after == census_before, (
        f"{tag}: STOP-IF - door census changed on a no-op close - "
        f"before={census_before} after={census_after}")
    session.assert_door_parity(host, client, what=f"{tag} census")
    assert_hash_clean(host, client, full=True, what=f"{tag} after no-op close")
    print(f"[{tag}] closed=0, coopDoorEvsEmitted stayed {emitted_before} (NO-OP)")


def phase_client_refused(host, client, tag, census_before):
    """Phase E: the host-authoritative terrain guard (TestServer.cpp:4057).
    A refusal that still mutated would be the desync it exists to prevent."""
    print(f"\n== {tag}: client refusal ==")
    hs0 = session.event_state(host)["lastSeqEmitted"]
    cs0 = session.event_state(client)["coopDoorEvsEmitted"]
    r = client.cmd({"cmd": "battle_close_ufo_doors"})
    assert not r.get("ok"), (
        f"{tag}: STOP-IF - a CLIENT was allowed to run battle_close_ufo_doors: {r}")
    assert "host-only" in r.get("error", ""), (
        f"{tag}: STOP-IF - unexpected refusal reason: {r}")
    time.sleep(0.5)
    hs, cs = session.event_state(host), session.event_state(client)
    assert hs["lastSeqEmitted"] == hs0, (
        f"{tag}: STOP-IF - the HOST minted a seq after a refused client call "
        f"({hs0} -> {hs['lastSeqEmitted']})")
    assert cs["coopDoorEvsEmitted"] == cs0, (
        f"{tag}: STOP-IF - the CLIENT's own door-ev counter moved after its "
        f"refused local call ({cs0} -> {cs['coopDoorEvsEmitted']})")
    census_h, census_c = session.door_census(host), session.door_census(client)
    assert census_h == census_before, (
        f"{tag}: STOP-IF - the HOST's door census changed after a refused "
        f"client call - before={census_before} after={census_h}")
    assert census_c == census_before, (
        f"{tag}: STOP-IF - the CLIENT's door census changed after its own "
        f"refused call - before={census_before} after={census_c}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after client refusal")
    print(f"[{tag}] client refused ({r['error']!r}); nothing mutated on either machine")


def run_scenario(host, client, tag):
    # ---- step 2: build the situation on the Lightning's own UFO door (WV-D87) ----
    actor_a, near, far, far_ground, door = lightning_setup(host, client, f"{tag} leg-a")
    door_at = (door["x"], door["y"], door["z"], door["part"])

    # ---- step 3: assert the SITUATION explicitly ----
    d0 = session.door_lookup(host, door_at)
    assert d0 is not None and d0.get("isUfoDoorOpen") is False, (
        f"{tag}: door {door_at} is not closed after placement: {d0}")
    units0 = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    a0 = units0[actor_a]
    assert session.unit_pos(a0) == near, (
        f"{tag}: actor {actor_a} sits at {session.unit_pos(a0)}, expected {near}")
    want_dir = session.dir_between(near, far)
    assert a0.get("direction") == want_dir, (
        f"{tag}: actor {actor_a} faces {a0.get('direction')}, expected {want_dir} "
        f"(toward {far})")
    # SPEC 0e-2: lightning_setup's own hostile-distance assertion (position-based,
    # HOSTILE-only, on battle_state) already replaces the old stale-`spotted` check.
    assert_hash_clean(host, client, full=True, what=f"{tag} after placement")

    # ---- step 3.5 (SPEC 6f STEP 0, WV-D63/WV-D72): back the actor up ONE
    # tile so the door ev lands BETWEEN two walk steps. near/far are always
    # exactly one tile apart (session.py:881-890), so a one-step walk cannot
    # produce a walk_step BEFORE the door ev; the crossing becomes
    # back -> near -> far: step, door, step.
    back = (near[0] + (near[0] - far[0]), near[1] + (near[1] - far[1]), near[2])
    st = session.battle_state(host)
    occupied = {session.unit_pos(u) for u in st["units"] if not u.get("isOut")}
    moves = []
    back_occupant = next((u for u in st["units"] if session.unit_pos(u) == back
                          and u["id"] != actor_a and not u.get("isOut")), None)
    if back_occupant is not None:
        # SPEC 0e-2: the same occupant-move lightning_setup does for `near`, using
        # a local copy of its own deck-scan, applied here for `back`.
        deck = [(x, y, near[2]) for y in range(door["y"] - 4, door["y"] + 5)
                for x in range(door["x"] - 4, door["x"] + 5)]
        free = next((t for t in deck if t not in (near, far, back)
                     and session.tile_walkable(host, t, occupied)), None)
        assert free is not None, (
            f"FIXTURE: {tag}(a): no free deck tile to move unit {back_occupant['id']} off {back}")
        moves.append({"lever": "battle_teleport_unit", "unit": back_occupant["id"],
                      "x": free[0], "y": free[1], "z": free[2],
                      "dir": back_occupant.get("direction", 0)})
        occupied = occupied - {back}
    if not session.tile_walkable(host, back, occupied):
        raise AssertionError(
            f"FIXTURE: {tag}(a): the one-tile-back approach {back} is not "
            "walkable or is occupied - this map roll cannot supply leg (a)'s "
            "door-between-steps geometry (WV-D72)")
    moves.append({"lever": "battle_teleport_unit", "unit": actor_a,
                  "x": back[0], "y": back[1], "z": back[2], "dir": session.dir_between(back, near)})
    place_deterministic(host, client, moves,
                        what=f"{tag}(a) back up one tile for the door-between-steps geometry")
    # place_deterministic's own gate already re-asserts assert_hash_clean(full=True).

    # ---- step 4: LEG (a) - CLIENT-origin crossing, HOST reserve aimed+kneel ----
    W.set_reserve(host, mode="aimed", kneel=True)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, actor_a, LEG_A_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag}(a) TU pinned")

    emitted0 = session.event_state(host)["coopDoorEvsEmitted"]
    waived0 = session.event_state(host)["coopDoorReserveWaived"]
    census_before_a = session.door_census(host)  # SPEC 6e item 6: non-vacuity control

    prev = W.walk_action_id(host)
    resp = W.send_walk(client, actor_a, far_ground)
    assert resp.get("iseq"), f"{tag}(a): the client-origin walk intent did not ship: {resp}"
    W.wait_walk_settled(host, client, prev)
    W.settle_reveal(host, client)

    hw = W.last_walk(host)
    action_id = hw.get("actionId")
    evs = session.action_events(host, action_id)
    door_evs = [e for e in evs if e["kind"] == "door"]
    if not door_evs:
        dump_record(f"{tag}(a)", host, actor_a, back, LEG_A_TU, door_at, False,
                   action_id=action_id, restate=hw.get("restate"))
        raise AssertionError(
            f"{tag}(a): STOP-IF - the client-origin crossing emitted NO `door` ev "
            f"under the host's aimed+kneel reserve (stream kinds: "
            f"{[e['kind'] for e in evs]})")

    # ---- SPEC 6e phase A additions (owner item 1 + item 6): the door ev's
    # STREAM POSITION on BOTH machines, plus a door-census change + parity.
    # Purely additive - leg (a)'s own accepted assertions below are unchanged.
    # WV-D77: on a STOP-IF here (the geometry fix did not produce a leading
    # walk_step), paste the instrumented record before propagating.
    try:
        session.assert_door_between_steps(host, action_id, what=f"{tag}(a) stream position (host)")
        session.assert_door_between_steps(client, action_id, what=f"{tag}(a) stream position (client)")
    except AssertionError:
        dump_record(f"{tag}(a) stream-position", host, actor_a, back, LEG_A_TU,
                   door_at, False, action_id=action_id, restate=hw.get("restate"))
        raise
    census_after_a = session.door_census(host)
    assert census_after_a != census_before_a, (
        f"{tag}(a) NON-VACUITY: door census did not change across the crossing")
    session.assert_door_parity(host, client, what=f"{tag}(a) census")

    d1 = session.door_lookup(host, door_at)
    assert d1 is not None and d1.get("isUfoDoorOpen") is True, (
        f"{tag}(a): door {door_at} did not go isUfoDoorOpen False -> True: {d1}")
    hs = session.event_state(host)
    emitted_a = hs["coopDoorEvsEmitted"]
    waived_a = hs["coopDoorReserveWaived"]
    assert emitted_a > emitted0, (
        f"{tag}(a): coopDoorEvsEmitted did not increase ({emitted0} -> {emitted_a})")
    assert waived_a > waived0, (
        f"{tag}(a): STOP-IF - coopDoorReserveWaived did not increase ({waived0} -> "
        f"{waived_a}) - the host's own reserve was not neutralised for a "
        "client-origin door")
    units_after_a = {u["id"]: u for u in session.battle_state(host).get("units", [])}
    final_pos = session.unit_pos(units_after_a[actor_a])
    assert final_pos == far_ground, (
        f"{tag}(a): actor {actor_a} ended at {final_pos}, expected {far_ground}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after leg (a)")
    print(f"[{tag}] leg (a): coopDoorEvsEmitted {emitted0} -> {emitted_a}, "
          f"coopDoorReserveWaived {waived0} -> {waived_a}")

    # ---- step 5: LEG (b) - HOST-origin control, SAME host reserve ----
    rc = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rc.get("ok"), f"{tag}(b): battle_close_ufo_doors failed: {rc}"
    d2 = session.door_lookup(host, door_at)
    assert d2 is not None and d2.get("isUfoDoorOpen") is False, (
        f"{tag}(b): door {door_at} did not re-close: {d2}")

    others = sorted(u["id"] for u in session.seat_units(host) if u["id"] != actor_a)
    assert others, f"FIXTURE: {tag}(b): no second live seat-1 soldier for the control leg"
    second_id = others[0]

    second_id, near_b, far_b, far_ground_b, door_b = lightning_setup(
        host, client, f"{tag} leg-b", actor_id=second_id, move_factions=False)
    assert (door_b["x"], door_b["y"], door_b["z"], door_b["part"]) == door_at, (
        f"{tag}(b): STOP-IF - leg-b staged on a different door {door_b} than leg-a's "
        f"{door_at}; WV-D87 says a Lightning map carries exactly one")

    # ---- b1 BASELINE: reserve=none, does this actor/door/TU open at all? ----
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    pin_tu(host, client, second_id, LEG_B_TU)
    assert_hash_clean(host, client, full=True, what=f"{tag}(b) baseline TU pinned")

    emitted_base0 = session.event_state(host)["coopDoorEvsEmitted"]
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
    emitted_base1 = session.event_state(host)["coopDoorEvsEmitted"]
    print(f"[{tag}] leg (b) baseline: coopDoorEvsEmitted {emitted_base0} -> "
          f"{emitted_base1}")

    # ---- re-arm: close it again, re-pin TU, only the reserve changes next ----
    rc = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rc.get("ok"), f"{tag}(b): re-close failed: {rc}"
    pin_tu(host, client, second_id, LEG_B_TU)
    d3 = session.door_lookup(host, door_at)
    assert d3 is not None and d3.get("isUfoDoorOpen") is False, (
        f"{tag}(b): door {door_at} did not re-close before the control: {d3}")
    assert_hash_clean(host, client, full=True, what=f"{tag}(b) re-armed for control")

    # ---- b2 CONTROL: SAME host reserve, IDENTICAL host-origin order ----
    W.set_reserve(host, mode="aimed", kneel=True)
    W.set_reserve(client, mode="none", kneel=False)
    waived_b0 = session.event_state(host)["coopDoorReserveWaived"]
    emitted_b0 = session.event_state(host)["coopDoorEvsEmitted"]
    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": second_id,
                  "x": far_b[0], "y": far_b[1], "z": far_b[2]})
    assert ra.get("ok"), f"{tag}(b) control: battle_action door failed: {ra}"
    opened = wait_counter(host, lambda es: es["coopDoorEvsEmitted"] > emitted_b0, timeout=5)
    time.sleep(1.0)
    W.settle_reveal(host, client)
    hs = session.event_state(host)
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
    d4 = session.door_lookup(host, door_at)
    assert d4 is not None and d4.get("isUfoDoorOpen") is False, (
        f"{tag}(b): door {door_at} is open after the refused control: {d4}")
    assert_hash_clean(host, client, full=True, what=f"{tag} after leg (b)")
    print(f"[{tag}] leg (b) control: coopDoorEvsEmitted stayed {emitted_b0}, "
          f"coopDoorReserveWaived stayed {waived_b0} (REFUSED)")

    # ---- step 6: restore + final hash gate ----
    W.set_reserve(host, mode="none", kneel=False)
    W.set_reserve(client, mode="none", kneel=False)
    assert_hash_clean(host, client, full=True, what=f"{tag} final")

    # ---- Phase B: THE TURN IS THE RIGHT-CLICK on the SAME craft door (WV-D87), a
    # SECOND soldier - re-close it first (leg (b)'s control left it closed already,
    # but this is the fixture's own precondition, not an assumption).
    def _phase_b_door(h):
        d, _, _ = lightning_door(h)
        return d, (d["x"], d["y"], d["z"], d["part"])

    rb = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert rb.get("ok"), f"{tag} phase B: battle_close_ufo_doors failed: {rb}"
    d5 = session.door_lookup(host, door_at)
    assert d5 is not None and d5.get("isUfoDoorOpen") is False, (
        f"{tag} phase B: STOP-IF - the craft door {door_at} is not closed before "
        f"phase B: {d5}")

    used_actors = {actor_a, second_id}
    actor2, door2_key = phase_turn_opens_door(
        host, client, f"{tag} phase B", want_ufo=True,
        exclude_door_keys=set(), used_actors=used_actors, door_pick=_phase_b_door)

    # ---- Phase C: same shape on a THIRD, NON-UFO door, a THIRD soldier ----
    used_actors.add(actor2)
    actor3, door3_key = phase_turn_opens_door(
        host, client, f"{tag} phase C", want_ufo=False,
        exclude_door_keys={door_at, door2_key}, used_actors=used_actors)
    used_actors.add(actor3)

    # ---- SPEC 6f Phase D: BOUNDARY CLOSE, the mutating half (WV-D50) ----
    print(f"\n== {tag} phase F: WALK through a NON-UFO door ==")
    actor4, door4_key = phase_walk_through_normal_door(
        host, client, f"{tag} phase F",
        exclude_door_keys={door_at, door2_key, door3_key}, used_actors=used_actors)
    used_actors.add(actor4)

    census_d, emitted_d = phase_boundary_close(host, client, f"{tag} phase D")

    # ---- SPEC 6f Phase D2: the immediate NO-OP repeat ----
    phase_boundary_close_noop(host, client, f"{tag} phase D2", census_d, emitted_d)

    # ---- SPEC 6f Phase E: CLIENT REFUSAL (host-authoritative terrain guard) ----
    phase_client_refused(host, client, f"{tag} phase E", census_d)


def run_fixture(tag):
    """SPEC 0e-2 (WV-D86): one boot, no retry - a `FIXTURE:` staging failure
    propagates straight to `__main__`'s is_fixture_error mapping (exit 3)
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
        session.print_known_flake_banner("repro_door_deterministic", "WV-D90", str(e))
        print(f"\nrepro_door_deterministic: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(EXIT_FAIL)
    except AssertionError as e:
        if is_fixture_error(e):
            print(f"\nrepro_door_deterministic: SKIP (fixture) - {e}")
            sys.exit(EXIT_SKIP)
        print(f"\nrepro_door_deterministic: FAIL\nAssertionError: {e}")
        sys.exit(EXIT_FAIL)
    except TimeoutError as e:
        print(f"\nrepro_door_deterministic: FAIL\nTimeoutError: {e}")
        sys.exit(EXIT_FAIL)
