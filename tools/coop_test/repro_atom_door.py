"""W1-P10 (rewrite wave 1, WAVE1-RUNBOOK.md SS4 "ATOM door", WV-D26/WV-D50):
the DOOR atom end to end - host-authoritative terrain apply, in the seq stream,
at the exact position vanilla mutated it.

WHAT SS4's ACCEPTANCE REQUIRES, and where each requirement is asserted:

  PHASE 1  A WALK THROUGH A DOOR emits the `ev door` AT ITS EXACT POSITION IN
           THE STREAM - strictly between the `walk_step` ev of the step before
           the doorway and the one after it (SS2.W2 rule 6), inside the SAME
           actionId, on BOTH machines' event rings. Every bucket EQUAL after it,
           the full door CENSUS identical, and the client's applied count equal
           to the host's emitted count (a DELIVERY proof, not two machines
           happening to agree). NON-VACUOUS IN THE SAME PHASE: the census must
           have CHANGED and the host's `terrain` bucket must have MOVED - a
           NORMAL door moves `terrain` because opening one rewrites the tile's
           mapDataID/SetID (Tile.cpp:388-390), which is exactly what that bucket
           sums (SharedEcon.cpp:3843-3848). This is where the packet's
           "`terrain` bucket EQUAL after every ev" is asserted somewhere it
           could actually FAIL.
  PHASE 2  THE RIGHT-CLICK DOOR PATH (the path SS2.4 reserved a `door` field on
           the turn ev for). The terrain now rides its own `ev door`, emitted
           with `actionId 0` from a bare UnitTurnBState with NO walk and NO coop
           action context - which is also half of WV-D50's binding
           "callable outside a walk" property. SS2.4's "RW-UNSUPPORTED
           door-in-turn" fallback is RETIRED for this path, and the retirement is
           asserted POSITIVELY: the tripwire counter is ZERO on both machines
           WHILE the door part really did SWING on both and `terrain` really did
           move. (A vanilla SWINGING door does not have an "open" bit: opening
           one MOVES its MCD from one wall part to the other -
           Tile::openDoor's setMapData pair, Tile.cpp:388-390 - so right-clicking
           the door PHASE 1 walked through swings it back, and the census delta
           printed by each phase shows exactly that: part 1 / mapDataID 17
           becomes part 2 / mapDataID 18, and back. Both machines agree on the
           swap in both directions, which is a sharper proof than an open bit
           would have been.)
  PHASE 3  WV-D50's OTHER HALF - `coopCloseUfoDoors()`, the boundary entry point
           W1-P13 will call from BattlescapeGame::endTurn
           (BattlescapeGame.cpp:549), driven through `battle_close_ufo_doors`:
           it RUNS on the host, is REFUSED on a client (which would otherwise
           mutate terrain locally), and - with no open ufo door on the map -
           mutates nothing and emits nothing. That last half is a real
           assertion: it is the journal's "nothing mutated => nothing emitted"
           rule, without which every turn boundary would put an empty `door` ev
           and a minted seq on the wire.

WHAT THIS FILE DOES **NOT** COVER, stated rather than glossed:
  * A boundary close that ACTUALLY SHUTS an open ufo door and ships
    `op:"close"`, and a walk through a UFO door (whose open bit is in NO
    BattleHashSet bucket - it is a binTiles boolField, Tile.cpp:209-210, plus an
    `openDoorWest`/`openDoorNorth` key, Tile.cpp:180-186, i.e. `saveBlob`
    only). Both need a ufo door a wave-1 squad can reach and open in ONE turn,
    and no fixture this wave can generate provides one. THREE WERE MEASURED:
      - STR_BASE_DEFENSE: perfect geometry (51 doors, all ufo, Chebyshev 0..4)
        but the battle is ALREADY DIVERGENT at t=0 in `items` + `saveBlob`
        before anything moves - an adjacent, pre-existing coop bug reported with
        this packet and deliberately NOT fixed here;
      - STR_ALIEN_BASE_ASSAULT: clean at t=0, nearest ufo door Chebyshev 6 with
        a hostile 6 tiles from it - every approach walk SPOTTED one;
      - STR_MARS_THE_FINAL_ASSAULT: clean at t=0, 23 ufo doors, nearest
        Chebyshev 4 with the nearest hostile 12.8 tiles away - but Chebyshev
        distance is not path cost there, and the approach walks arrived with 1
        and 3 TU left, unable to act.
    This is exactly the case the runbook already schedules for W1-P13: G3
    criterion 2 and owner manual-playtest item 12, both a UFO map with a door
    opened, walked through and then END TURNed.

THE FIXTURE (measured, never assumed): STR_SMALL_SCOUT, pinned rather than left
on the combo box's remembered value (NewBattleState::load reads `battle.cfg`,
NewBattleState.cpp:479). Four boots produced 2/7/11/16 doors, EVERY one a NORMAL
(swinging) door, nearest at Chebyshev 5..17 from a soldier.

  CONTACT: repro_atom_walk's static contact pin (session.MAX_VIEW_DISTANCE) and
  "a door within walking reach" are almost never the same door on these maps -
  one boot had doors at Chebyshev 5/6/7/7/8 with the single alien 19.7/17.1/
  19.3/17.5/19.7 tiles away, every one inside the cap. A hard filter would be a
  fixture that never runs. So the pin is a PREFERENCE in the candidate ordering
  (contact-free crossings first, then the ones furthest from contact) and the
  premise itself is enforced as a VERIFIED OUTCOME: the spotted set must not
  change across a door walk, and a candidate that changes it is DISCARDED, never
  absorbed. Nothing asserted is weakened - `assert_hash_clean(full=True)` still
  has to pass on every candidate that is actually used, so anything unmodelled
  (a reaction shot, a spot halt) REDS rather than slipping through.

WHY THESE ASSERTIONS ARE NOT VACUOUS - the checks that would go RED:
  * WRONG STREAM POSITION: PHASE 1 requires a `walk_step` with seq STRICTLY
    BELOW the door ev's and another STRICTLY ABOVE it, all inside the walk's own
    actionId, on BOTH machines. An emitter that flushed the door at the
    completion restate has no step after it; one that flushed it before the walk
    began stepping has none before it. Either way the assert fails and names
    which side is missing.
  * CLIENT SILENTLY NOT APPLYING: three independent, non-absence assertions
    catch it - the full door CENSUS (every door part's open state and mapDataID)
    must be IDENTICAL on the two machines; `hash_now full` must have every
    bucket EQUAL; and `event_state.coopDoorEvsApplied` on the CLIENT must equal
    `coopDoorEvsEmitted` on the HOST. PROVEN BY A CONTROL BUILD (run and
    reverted): with the applier's mutation loop removed, PHASE 1 reds with the
    client DESYNC-FROZEN and `terrain` 9cbd79cf3a8240cc on the host against
    f6873e03ef831f07 on the client.
  * NOTHING ACTUALLY HAPPENED: PHASES 1 and 2 both assert the census CHANGED and
    that the `terrain` bucket MOVED on the host. "EQUAL" after an event that
    changed nothing would prove nothing.
  * RETIREMENT CLAIMED BUT NOT DELIVERED: PHASE 2 asserts the tripwire counter
    at zero AND that the door part swung on both machines. Deleting the fallback
    branch would satisfy the counter alone, which is why it is never asserted on
    its own.

Run:  python tools/coop_test/repro_atom_door.py
      (in its OWN shell invocation - the standing harness rule, one harness run
       at a time, machine-wide.)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean
import repro_atom_walk as W

COOP_SEAT_1 = 1
FACTION_PLAYER = 0

O_FLOOR, O_WESTWALL, O_NORTHWALL, O_OBJECT = 0, 1, 2, 3

MAX_REROLLS = 40

# THE PIN THAT MAKES THE CROSSING RELIABLE, and it is a MEASURED number.
#
# 12 instrumented boots of this fixture produced these candidate-crossing counts
# against the nearest closed wall-door: 27, 5, 1, 1, 1, 0, 0, 0, 0 (three boots
# had no wall-door at all). The 27 and the 5 came from doors 4 and 5 tiles from
# the squad; every "1" was a door 7 tiles out.
#
# Every observed fixture red - four in a ten-run proof, plus the one that opened
# this investigation - happened on a ONE-CANDIDATE boot: a single marginal
# crossing, no retry, and the walk either found no route at all or arrived with
# 7-18 TU of the 22 a crossing costs. The boots with 5+ candidates never failed:
# a door that close is reachable, and the spare candidates absorb a pathfinder
# that routes around one of them.
#
# So the premise this fixture needs is not "a door exists" (which is what it used
# to check, and which a 7-tile door satisfies while being uncrossable) - it is
# "enough crossings that one of them must work". Re-rolling for that is the
# honest place for the lottery, and MAX_REROLLS is sized for it: ~20% of boots
# qualify, so 40 boots makes exhaustion a ~0.06% event instead of the ~25-40%
# red rate this pin replaces.
MIN_CROSSINGS = 5

# PHASE 2 walks an actor up to a door only to right-click it, so its approach is
# pure overhead and a long one defeats the phase: traced, four actors walked
# seven tiles and arrived with 1-3 TU, unable to turn or open anything.
RIGHT_CLICK_APPROACH_MAX = 4

# TU an actor must still hold to RIGHT-CLICK a door open. Tile::openDoor charges
# the part's own getTUCost PLUS a kneel-reserve term and returns 4 - mutating
# NOTHING and emitting NOTHING - when the actor cannot afford it, which is what
# two traced runs hung on. Raising this to the door's true cost (16) was tried
# and MEASURED WORSE (2/9 green against 6/10): it starved the pick list on a
# squad this fixture has already partly spent. It stays at the permissive value,
# because the fix that mattered was making the wait BOUNDED - a too-poor actor is
# now diagnosed and skipped rather than hung on.
RIGHT_CLICK_TU = 8

# THE FIXTURE. Pinned to STR_SMALL_SCOUT rather than left on "whatever the combo
# box defaults to": NewBattleState::load() takes the mission from `battle.cfg`
# (NewBattleState.cpp:479), so an unpinned fixture's door population depends on a
# config file rather than on this test. Measured over four boots of this mission
# class: 2/7/11/16 doors, EVERY one of them a NORMAL (swinging) door, the nearest
# at Chebyshev 5..17 from a soldier.
#
# The real reach limit is the per-candidate TU MARGIN in
# walk_through_candidates(), not this number: a soldier holds ~55 TU and a tile
# costs 4-8 (more across a level change, and a real route is longer than its
# Chebyshev distance), so a candidate is only kept when the actor can still ACT
# after getting there - which caps the effective approach at ~6. This is the
# outer bound on the search. Loosening either of them was tried and measured:
# every candidate 9-10 tiles out shipped NOTHING ("no route"), so the fixture
# qualified and then had nothing to walk.
DOOR_MISSION = "STR_SMALL_SCOUT"
NORMAL_APPROACH_MAX = 7

DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


# ----- small probes -------------------------------------------------------

def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def event_log(gc, tail=120):
    return gc.cmd({"cmd": "event_log", "tail": tail}).get("events", [])


def find_doors(gc):
    r = gc.cmd({"cmd": "find_doors", "limit": 512})
    assert r.get("ok"), f"find_doors failed: {r}"
    return r["doors"]


def door_census(gc):
    """Every door part this machine knows about, as a comparable set. Used two
    ways: HOST vs CLIENT (they must be identical - that is the terrain-sync
    assertion) and BEFORE vs AFTER (they must differ - that is the non-vacuity
    control). A NORMAL door that opens leaves the census entirely, because
    Tile::openDoor clears the part's map data; a UFO door stays and flips
    isUfoDoorOpen."""
    return sorted((d["x"], d["y"], d["z"], d["part"], d["isUfoDoor"],
                   d["isUfoDoorOpen"], d["mapDataID"]) for d in find_doors(gc))


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def units(gc):
    return battle_state(gc).get("units", [])


def unit_pos(u):
    return (u["x"], u["y"], u["z"])


def seat_units(gc, seat=COOP_SEAT_1):
    return [u for u in units(gc)
            if u.get("faction") == FACTION_PLAYER and not u.get("isOut")
            and u.get("coop") == seat]


def spotted(gc):
    return sorted(battle_state(gc).get("spotted") or [])


def dir_between(a, b):
    dx = (b[0] > a[0]) - (b[0] < a[0])
    dy = (b[1] > a[1]) - (b[1] < a[1])
    for d in range(8):
        if DIR_DX[d] == dx and DIR_DY[d] == dy:
            return d
    return None


# ----- fixture bring-up ---------------------------------------------------

def drive_to_battlescape(host, client, seated, mission=None, seat_count=8):
    """repro_atom_walk.drive_to_battlescape plus the mission pin. Kept local
    rather than parameterising the walk repro's copy: that file carries a
    stop-line criterion and this packet must not change how it boots."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert W.top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={W.states(host)}"
    if mission:
        r = host.cmd({"cmd": "newbattle_mission", "type": mission})
        assert r.get("ok"), (
            f"FIXTURE: this build's NEW BATTLE screen does not offer {mission!r} "
            f"- offered: {r.get('missionTypes')}")

    soldier_ids = []
    for i in range(seat_count):
        r = host.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        if not r.get("ok"):
            break
        soldier_ids.append(r["soldierId"])
    assert len(soldier_ids) >= 2, (
        f"FIXTURE: newbattle_seat_soldier stamped only {len(soldier_ids)} soldier(s) "
        "to seat 1 - this repro needs client-owned actors to walk")
    seated["soldierIds"] = soldier_ids

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"),
                  timeout=60)
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=90)
    time.sleep(3)
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=40)
    session.dismiss_battle_start_overlays(host)
    session.dismiss_client_briefing(client)


def door_sides(d):
    """The two tiles a wall-part door joins. O_WESTWALL is the west face of its
    own tile, O_NORTHWALL the north face (TileEngine::unitOpensDoor's own
    checkPositions table, TileEngine.cpp:4108-4177). Floor/object doors are
    skipped: this file only reasons about doors you WALK THROUGH."""
    t = (d["x"], d["y"], d["z"])
    if d["part"] == O_WESTWALL:
        return t, (d["x"] - 1, d["y"], d["z"])
    if d["part"] == O_NORTHWALL:
        return t, (d["x"], d["y"] - 1, d["z"])
    return None


def closed_doors(gc):
    out = []
    for d in find_doors(gc):
        if d["isUfoDoor"] and d["isUfoDoorOpen"]:
            continue
        if door_sides(d) is None:
            continue
        out.append(d)
    return out


def tile_walkable(gc, t, occupied):
    """Cheap conservative screen for a STAGING tile: it exists, it has a floor,
    and nobody is standing on it. Pathfinding stays the real judge - a staging
    tile that survives this and yields no route is simply skipped."""
    if t in occupied:
        return False
    ti = gc.cmd({"cmd": "tile_info", "x": t[0], "y": t[1], "z": t[2]})
    if not ti.get("ok"):
        return False
    return ti.get("parts", {}).get("floor", {}).get("mapDataID", -1) >= 0


def staging_tiles(gc, near, far, occupied, self_pos=None):
    """EVERY tile from which a walk to @a far is a two-step crossing through the
    door: adjacent to `near`, exactly two steps from `far`, walkable, and free.

    A LIST, not a single tile, and that is the point. When this returned only the
    first match, one actor parking on it made the same door unusable for all six
    other soldiers - four of the seven rejections in a traced red were "no
    walkable staging tile", for a tile that existed and was simply occupied by
    the previous candidate. @a self_pos is excused from the occupancy test for
    the same reason: an actor standing on a staging tile IS staged.

    The two-step requirement is not decoration either: a neighbour of `near` that
    is also a DIAGONAL neighbour of `far` lets Pathfinding cut the corner and
    never touch the wall the door is in (observed as a one-step "routed WITHOUT
    crossing a door")."""
    dx, dy = near[0] - far[0], near[1] - far[1]
    ordered = [(near[0] + dx, near[1] + dy, near[2])]          # collinear first
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            if ox or oy:
                ordered.append((near[0] + ox, near[1] + oy, near[2]))
    out = []
    for t in ordered:
        if t in (near, far) or t in out:
            continue
        if cheb(t, far) != 2:
            continue
        if t != self_pos and not tile_walkable(gc, t, occupied):
            continue
        out.append(t)
    return out


def walk_through_candidates(gc, approach_max, want_ufo=None, min_approach=1,
                            clean_only=False):
    """(actor_id, near, far, door) triples for a walk that must cross a door.

    `min_approach >= 1` is the DEFAULT and it is load-bearing: the acceptance is
    that the door ev lands BETWEEN the step evs either side of it, and an actor
    that already stands on the near tile produces no step before the door at
    all.

    ORDERING is repro_atom_walk's own contact pin used as a PREFERENCE rather
    than a filter, and the reason is measured, not stylistic: on the maps these
    fixtures produce, a door within walking reach and a crossing whose whole
    approach box clears session.MAX_VIEW_DISTANCE are almost never the same
    door (one boot: doors at Chebyshev 5/6/7/7/8 with the single alien 19.7,
    17.1, 19.3, 17.5 and 19.7 tiles away - every one inside the cap). A filter
    would be a fixture that never runs. So crossings that DO clear the cap are
    tried FIRST, then the ones furthest from contact - and the premise itself is
    enforced downstream as a VERIFIED OUTCOME (the spotted set must not change
    across the walk; a candidate that changes it is discarded, never absorbed).
    Nothing asserted is weakened by this: every bucket must still be EQUAL after
    every candidate that is actually used."""
    st = battle_state(gc)
    occupied = {unit_pos(u) for u in st.get("units", []) if not u.get("isOut")}
    aliens = W.living_non_players(st)
    actors = [u for u in st.get("units", [])
              if u.get("faction") == FACTION_PLAYER and not u.get("isOut")
              and u.get("coop") == COOP_SEAT_1 and u.get("tu", 0) > 20]
    out = []
    for d in closed_doors(gc):
        if want_ufo is not None and bool(d["isUfoDoor"]) != want_ufo:
            continue
        a, b = door_sides(d)
        for actor in actors:
            p = unit_pos(actor)
            near, far = (a, b) if cheb(p, a) <= cheb(p, b) else (b, a)
            approach = cheb(p, near)
            if approach < min_approach or approach > approach_max:
                continue
            # TU MARGIN, and it is load-bearing rather than tidy: a candidate is
            # only useful if the actor can still ACT once it gets there. A tile
            # costs 4-8 TU (more across a level change), and the right-click
            # phase then needs a turn plus the door's own cost. Observed without
            # this: a 6-tile approach left the actor on 1 TU and the phase had
            # nothing left to drive.
            if actor.get("tu", 0) < 6 * approach + 16:
                continue
            if far in occupied or near in occupied:
                continue
            clean = 0 if W.region_is_contact_free(aliens, actor, far, pad=2) else 1
            if clean_only and clean:
                continue
            room = W.min_dist_to(aliens, far)
            out.append((clean, approach, -(room if room is not None else 1e9),
                        actor["id"], near, far, d))
    out.sort(key=lambda e: (e[0], e[1], e[2]))
    return [(e[3], e[4], e[5], e[6]) for e in out]


# ----- PHASES -------------------------------------------------------------

def action_events(gc, action_id, tail=160):
    return [e for e in event_log(gc, tail) if e.get("actionId") == action_id]


def wait_host_idle(host, client, timeout=30):
    """The host has NO action context open and NO live BState chain, and the
    client has caught up.

    `lastSeqApplied == lastSeqEmitted` ALONE IS NOT ENOUGH, and this cost a run:
    a turn emits its `bt_ev` from UnitTurnBState and its `bt_action_end` from
    CoopArbiter::onChainQuiesced() one chain-unwind LATER, so the two counters
    are transiently EQUAL in the gap between them - and
    CoopArbiter::popActionContext() runs inside onChainQuiesced
    (connectionTCP.cpp:3737). Anything driven in that window inherits the
    previous action's actionId, which is exactly how PHASE 2's `actionId 0`
    assertion first failed (it observed 3). `busyOwnerSeat == -1` on the HOST is
    the shipped predicate for BOTH halves at once:
    `!bg->isBusy() && currentActionId() == 0` (connectionTCP.cpp:4545-4551)."""
    client.wait_for("host idle (no action context, no BState chain), client caught up",
                    lambda: (event_state(host).get("busyOwnerSeat") == -1
                             and event_state(client).get("lastSeqApplied", 0)
                             == event_state(host).get("lastSeqEmitted", 0)
                             and event_state(client).get("queueDepth") == 0
                             and event_state(host).get("queueDepth") == 0) or None,
                    timeout=timeout)


def assert_door_between_steps(gc, action_id, what):
    """SS2.W2 rule 6 / SS4's acceptance: the `door` ev takes its place in the
    seq stream BETWEEN the walk step evs either side of the doorway."""
    evs = action_events(gc, action_id)
    kinds = [(e["seq"], e["kind"]) for e in evs]
    doors = [e for e in evs if e["kind"] == "door"]
    steps = [e for e in evs if e["kind"] == "walk_step"]
    assert doors, (
        f"{what}: actionId {action_id} emitted NO `door` ev - the walk did not "
        f"cross a door (stream: {kinds})")
    d0 = doors[0]
    before = [s for s in steps if s["seq"] < d0["seq"]]
    after = [s for s in steps if s["seq"] > d0["seq"]]
    assert before, (
        f"{what}: the `door` ev (seq {d0['seq']}) has NO walk_step BEFORE it in "
        f"actionId {action_id} - it was emitted before the walk began stepping, "
        f"not at the doorway (stream: {kinds})")
    assert after, (
        f"{what}: the `door` ev (seq {d0['seq']}) has NO walk_step AFTER it in "
        f"actionId {action_id} - it was flushed at the END of the walk instead of "
        f"at its own position in the stream (stream: {kinds})")
    print(f"    [{what}] stream: {kinds}")
    print(f"    [{what}] door ev seq={d0['seq']} sits between {len(before)} step(s) "
          f"before and {len(after)} after, all in actionId {action_id}")
    return d0


def assert_door_parity(host, client, what):
    hc, cc = door_census(host), door_census(client)
    if hc != cc:
        only_h = [e for e in hc if e not in cc]
        only_c = [e for e in cc if e not in hc]
        raise AssertionError(
            f"{what}: the two machines' DOOR CENSUS differ - "
            f"{len(only_h)} entr(ies) only on the host {only_h[:6]}, "
            f"{len(only_c)} only on the client {only_c[:6]}. The client did not "
            "apply the host's terrain change.")
    return hc


def assert_delivery(host, client, what):
    hs, cs = event_state(host), event_state(client)
    he = hs["coopDoorEvsEmitted"]
    ca = cs["coopDoorEvsApplied"]
    assert he >= 1, f"{what}: the host emitted NO door ev at all"
    assert ca == he, (
        f"{what}: the host EMITTED {he} door ev(s) but the client APPLIED {ca} - "
        "the terrain agreement below would be a coincidence, not a delivery")
    for tag, s in (("host", hs), ("client", cs)):
        assert s["coopDoorInTurnUnsupported"] == 0, (
            f"{what}: the {tag} hit the RETIRED SS2.4 'RW-UNSUPPORTED door-in-turn' "
            f"fallback {s['coopDoorInTurnUnsupported']} time(s) - a peer emitted the "
            "retired shape, or the door atom did not take over this path")
    assert battle_state(host)["authority"]["desyncFrozen"] is False, \
        f"{what}: the HOST is desync-frozen"
    assert battle_state(client)["authority"]["desyncFrozen"] is False, \
        f"{what}: the CLIENT is desync-frozen - a post-apply hash compare FAILED"
    return he, ca


# TU a crossing needs once the actor is standing on the staging tile: two steps
# (4-8 each) plus the door's own cost. Checked BEFORE the crossing is ordered, so
# "the actor ran dry mid-crossing" is a retry on the next candidate and never a
# red - that halt was one of the two mechanisms behind the observed flake.
CROSSING_TU = 22


def phase_walk_through(host, client, want_ufo, approach_max, tag, moving_bucket):
    """A WALK THROUGH A DOOR. @a moving_bucket is the bucket that MUST have moved
    on the host across the crossing - the non-vacuity control that stops every
    "EQUAL" assertion below from being equal-because-nothing-happened. It is
    `terrain` for a NORMAL door (Tile::openDoor rewrites mapDataID/SetID,
    Tile.cpp:388-390, which is what SharedEcon.cpp:3843-3848 sums).

    HOW A CROSSING IS MADE TO HAPPEN, and why the two obvious ways do not work.
    Ordering a walk AT the far tile and hoping Pathfinding goes through the door
    is a lottery, and it lost: a traced red had the pathfinder walk EIGHT steps
    around the module and never touch the door. Shipping an explicit two-tile
    `path` override instead does not fix it either - the host RECOMPUTES its own
    route and requires it tile-for-tile (SS2.W2's no-silent-reroute rule,
    connectionTCP.cpp:3399-3423), so a plan the pathfinder disagrees with is
    answered `path_changed`, by design.

    So the crossing is STAGED and every precondition is VERIFIED before it is
    ordered: the actor is walked onto the tile behind `near` (collinear, exactly
    two steps from `far`), confirmed to BE there, confirmed to still hold
    CROSSING_TU, the spotted set is confirmed unchanged, and the door is
    confirmed still CLOSED. Only then is the crossing ordered. Anything that does
    not hold moves to the NEXT candidate with a freshly derived list - never a
    failure, because none of it is a statement about the door atom.

    THE ONE THING THIS FILE USED TO DO THAT POISONED ITSELF: it tried the direct
    (route-and-hope) form FIRST, on the same candidate, which walked the actor
    eight tiles away and drained it - so the staged retry then ran from the wrong
    tile with no TU and produced a one-step halt, and the phase reported "no
    candidate crossing routed through a door". The direct form is gone.

    Every rejection is RECORDED and printed if the phase runs out of candidates,
    so a fixture red says which test failed and with what numbers instead of
    having to be reproduced to be understood."""
    print(f"\n== {tag}: a walk THROUGH a "
          f"{'ufo' if want_ufo else 'normal'} door ==")
    spot0 = (spotted(host), spotted(client))
    print(f"    spotted before: host={spot0[0]} client={spot0[1]}")
    assert_hash_clean(host, client, full=True, what=f"{tag} t=0")

    tried = set()
    rejected = []
    seen = 0
    for _ in range(18):
        cands = [c for c in walk_through_candidates(host, approach_max,
                                                    want_ufo=want_ufo)
                 if (c[0], c[1], c[2],
                     unit_pos(W.unit_of(host, c[0]))) not in tried]
        if not cands:
            break
        actor_id, near, far, d = cands[0]
        at = unit_pos(W.unit_of(host, actor_id))
        tried.add((actor_id, near, far, at))
        seen += 1
        door_at = (d["x"], d["y"], d["z"], d["part"])
        tu = W.unit_of(host, actor_id).get("tu", 0)
        occupied = {unit_pos(u) for u in battle_state(host).get("units", [])
                    if not u.get("isOut")}
        staged = at in staging_tiles(host, near, far, occupied, self_pos=at)

        # THE ONE WALK. Whether the actor is already staged or not, the order is
        # the same: walk AT `far`. That is what makes this loop terminate without
        # wasting TU - a walk that fails to cross has still carried the actor
        # TOWARDS the door, so the next iteration re-derives from a better
        # position, and the (actor, door, POSITION) key means the same pair is
        # never retried from the same tile.
        #
        # A SEPARATE staging leg was tried first and was worse on every count: it
        # spent the TU the crossing then needed (traced: actors arriving on the
        # staging tile with 7-18 TU of the 22 a crossing costs), it could fail
        # with no route to one specific tile while the crossing itself was fine
        # (traced twice), and it parked actors on the very tiles the next
        # candidate needed.
        if staged and tu < CROSSING_TU:
            rejected.append(f"actor {actor_id} door {door_at}: staged at {at} but "
                            f"only {tu} TU, a crossing needs {CROSSING_TU}")
            continue
        if not closed_door_at(host, door_at):
            rejected.append(f"actor {actor_id} door {door_at}: no longer closed when "
                            "its crossing was due")
            continue

        before_census = door_census(host)
        before_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
        prev = W.walk_action_id(host)
        resp = W.send_walk(client, actor_id, far)
        if not resp.get("iseq"):
            rejected.append(f"actor {actor_id} door {door_at}: no intent shipped from "
                            f"{at} with {tu} TU ({resp.get('error')})")
            continue
        try:
            W.wait_walk_settled(host, client, prev)
        except Exception as e:
            # A walk that never settles is almost always a client that FROZE:
            # CoopHashCheck::verify() raises the SS2.8 desync on the first bucket
            # mismatch and the pump then stops draining, so lastSeqApplied never
            # catches up. Say so, with the buckets, or the control build for this
            # very test reads as a hang.
            raise AssertionError(
                f"{tag}: crossing for actor {actor_id} never settled: {e}\n"
                f"  host desyncSeen={event_state(host).get('desyncSeen')} "
                f"client desyncSeen={event_state(client).get('desyncSeen')}\n"
                f"  host   h={host.cmd({'cmd': 'hash_now', 'full': True}).get('h')}\n"
                f"  client h={client.cmd({'cmd': 'hash_now', 'full': True}).get('h')}")
        W.settle_reveal(host, client)
        hw = W.last_walk(host)
        # EVERY walk this phase orders is hash-checked, not just the one that
        # ends up crossing a door. The earlier shape only checked the separate
        # staging leg, so a failed crossing attempt went unchecked before the
        # next candidate was tried - a walk that diverged the buckets could then
        # be silently walked away from.
        assert_hash_clean(host, client, full=True,
                          what=f"{tag} after a crossing attempt")

        if (spotted(host), spotted(client)) != spot0:
            rejected.append(f"actor {actor_id} door {door_at}: the walk CHANGED the "
                            f"spotted set {spot0} -> "
                            f"{(spotted(host), spotted(client))} (a `spot` halt is "
                            "W1-P11's atom, not this one)")
            spot0 = (spotted(host), spotted(client))
            continue
        evs = action_events(host, hw["actionId"])
        if not any(e["kind"] == "door" for e in evs):
            restate = hw.get("restate") or {}
            rejected.append(f"actor {actor_id} door {door_at}: walk from {at} "
                            f"(staged={staged}, {tu} TU) did not open it - "
                            f"{len([e for e in evs if e['kind'] == 'walk_step'])} "
                            f"step(s), halted={restate.get('halted')} "
                            f"reason={restate.get('reason')}; now at "
                            f"{unit_pos(W.unit_of(host, actor_id))} with "
                            f"{W.unit_of(host, actor_id).get('tu')} TU")
            continue

        print(f"    crossing door {door_at} ufo={d['isUfoDoor']} via actor "
              f"{actor_id} from {at} (staged={staged}, {tu} TU) -> {far}")
        d0 = assert_door_between_steps(host, hw["actionId"], f"{tag} host")
        assert_door_between_steps(client, hw["actionId"], f"{tag} client")

        after_census = assert_door_parity(host, client, tag)
        print(f"    census delta: "
              f"gone={[e for e in before_census if e not in after_census]} "
              f"new={[e for e in after_census if e not in before_census]}")
        assert after_census != before_census, (
            f"{tag} NON-VACUITY: the door census did not change across the walk - "
            "no door actually opened, so 'the two machines agree' proves nothing")
        after_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
        assert after_h[moving_bucket] != before_h[moving_bucket], (
            f"{tag} NON-VACUITY: the host's `{moving_bucket}` bucket did not move "
            "across the door open, although that is the bucket this door kind "
            "writes - so the EQUAL assertions would be "
            "equal-because-nothing-happened")
        assert_hash_clean(host, client, full=True, what=f"{tag} after the door walk")
        he, ca = assert_delivery(host, client, tag)
        print(f"    PASS: door ev seq {d0['seq']} in actionId {hw['actionId']}; host "
              f"emitted {he}, client applied {ca}; `{moving_bucket}` moved "
              f"{before_h[moving_bucket]} -> {after_h[moving_bucket]} on the host "
              f"and the CLIENT matches it; census identical "
              f"({len(after_census)} parts) and CHANGED "
              f"({len(rejected)} attempt(s) rejected first)")
        return actor_id

    detail = ("\n      ".join(rejected)) if rejected else "(no candidate at all)"
    raise AssertionError(
        f"FIXTURE: {seen} crossing attempt(s), none opened a door - fixture "
        f"failure, not a result about the door atom.\n      {detail}")


def closed_door_at(gc, door_at):
    return any((x["x"], x["y"], x["z"], x["part"]) == door_at
               for x in closed_doors(gc))


def phase_right_click(host, client, approach_max, want_ufo, tag, moving_bucket):
    print(f"\n== {tag}: the RIGHT-CLICK door path (SS2.4's retired fallback) ==")

    def adjacent_pick():
        occupied = {unit_pos(u) for u in battle_state(host).get("units", [])
                    if not u.get("isOut")}
        for d in closed_doors(host):
            if want_ufo is not None and bool(d["isUfoDoor"]) != want_ufo:
                continue
            a, b = door_sides(d)
            for u in seat_units(host):
                p = unit_pos(u)
                # Enough TU left to actually open it: a right-click door costs
                # tile->getTUCost(part, movementType) (TileEngine.cpp:4225), i.e.
                # 4-8 on foot, and the facing turn is skipped when the actor
                # already faces the door.
                if u.get("tu", 0) < RIGHT_CLICK_TU:
                    continue
                for stand, through in ((a, b), (b, a)):
                    if p != stand or through in occupied or p[2] != through[2]:
                        continue
                    dd = dir_between(p, through)
                    if dd is not None:
                        return (u["id"], p, through, dd, d)
        return None

    pick = adjacent_pick()
    if not pick:
        # SHORT APPROACHES FIRST, and the reason is a traced red: at the full
        # radius this phase walked four actors seven tiles each and every one of
        # them arrived with 1-3 TU - not enough to turn and open anything - so
        # the phase failed with a map full of doors and a squad too tired to use
        # them. MIN_CROSSINGS guarantees a door CLUSTER within a few tiles, so a
        # short approach almost always exists; the full radius stays as a
        # fallback rather than a first choice.
        approach = walk_through_candidates(host, RIGHT_CLICK_APPROACH_MAX,
                                           want_ufo=want_ufo)
        if not approach:
            approach = walk_through_candidates(host, approach_max,
                                               want_ufo=want_ufo)
        print(f"    no seat-1 soldier is adjacent to a closed "
              f"{'ufo' if want_ufo else 'normal'} door; "
              f"{len(approach)} approach candidate(s) "
              f"(short cap {RIGHT_CLICK_APPROACH_MAX}, full cap {approach_max})")
        # Nothing says a seat-1 soldier must ALREADY stand next to a closed door,
        # so walk one up to a NEAR tile first. That approach walk stops ON the
        # near tile and therefore does not cross the door, so this phase still
        # drives the right-click path and not the walk phase again.
        spot0 = (spotted(host), spotted(client))
        for actor_id, near, far, d in approach[:8]:
            # send_walk_outcome, NOT send_walk + wait_walk_settled: a drained
            # actor is legitimately answered `cost_changed`, which opens no walk
            # chain at all, and waiting for one just times out (observed).
            outcome, _ = W.send_walk_outcome(host, client, actor_id, near, timeout=25)
            at = unit_pos(W.unit_of(host, actor_id))
            if outcome != "walk" or at != near:
                print(f"    approach for actor {actor_id} -> {near}: {outcome}, ended "
                      f"at {at} with {W.unit_of(host, actor_id).get('tu')} TU")
                continue
            if (spotted(host), spotted(client)) != spot0:
                print(f"    approach for actor {actor_id} CHANGED the spotted set - "
                      "discarding this candidate (a spot is W1-P11's atom)")
                spot0 = (spotted(host), spotted(client))
                continue
            pick = adjacent_pick()
            if pick:
                break
            print(f"    actor {actor_id} reached {near} but no closed door is "
                  "right-clickable from there")
        assert pick, (
            "FIXTURE: could not put a seat-1 soldier on a tile adjacent to a CLOSED "
            f"door ({len(approach)} approach candidate(s) tried, "
            f"{len(closed_doors(host))} closed door(s) on the map, seat-1 units "
            f"{[(u['id'], unit_pos(u), u.get('tu')) for u in seat_units(host)]}), so "
            "the right-click door path cannot be driven")
        assert_hash_clean(host, client, full=True,
                          what=f"{tag} after the approach walk")

    actor_id, stand, through, facing, d = pick
    print(f"    actor {actor_id} at {stand} will face dir {facing} and right-click the "
          f"door at ({d['x']},{d['y']},{d['z']}) part {d['part']} "
          f"(ufo={d['isUfoDoor']})")

    # FACE IT THROUGH THE SYNCED TURN ATOM, never by letting UnitTurnBState turn
    # locally: a bare statePushBack has no coop action context, so a host-local
    # rotation emits no ev at all, and `direction` is inside saveBlob - the
    # buckets would then diverge for a reason that has nothing to do with doors.
    # (Skipped entirely when the actor already faces the door - an approach walk
    # leaves it facing its last step, which is often exactly right, and the turn
    # costs TU the door itself then needs.)
    before = event_state(host)["coopDoorEvsEmitted"]
    if W.unit_of(host, actor_id).get("direction") != facing:
        r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": actor_id,
                        "toDir": facing})
        assert r.get("iseq"), f"{tag}: the facing turn intent did not ship: {r}"
        client.wait_for("facing turn applied on both machines",
                        lambda: (event_state(client).get("lastSeqApplied", 0)
                                 == event_state(host).get("lastSeqEmitted", 0)
                                 and event_state(client).get("queueDepth") == 0) or None,
                        timeout=30)
    wait_host_idle(host, client)
    W.settle_reveal(host, client)
    assert_hash_clean(host, client, full=True, what=f"{tag} after facing the door")
    got = W.unit_of(host, actor_id).get("direction")
    assert got == facing, (
        f"{tag}: the actor faces {got}, not {facing} - the right-click would check the "
        "wrong wall (TileEngine::unitOpensDoor reads unit->getDirection() when "
        "dir == -1, TileEngine.cpp:4095)")

    before_census = door_census(host)
    before_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    ra = host.cmd({"cmd": "battle_action", "action": "door", "unit": actor_id,
                   "x": through[0], "y": through[1], "z": through[2]})
    assert ra.get("ok"), f"{tag}: battle_action door failed: {ra}"
    # BOUNDED, and it REPORTS rather than hanging. `unitOpensDoor` mutates
    # nothing and emits nothing when the actor cannot pay the door's TU
    # (Tile::openDoor returns 4) or when the geometry does not match, and the
    # unbounded wait this replaces then ran to a TimeoutError that escaped
    # main()'s AssertionError handler entirely - exit 1 with a traceback, twice,
    # instead of a diagnosis. A HARNESS defect, not a product one: both
    # processes were alive and neither machine was desync-frozen.
    deadline = time.time() + 30
    fired = False
    while time.time() < deadline:
        hs, cs = event_state(host), event_state(client)
        if (hs["coopDoorEvsEmitted"] > before
                and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                and cs.get("queueDepth") == 0):
            fired = True
            break
        time.sleep(0.1)
    assert fired, (
        f"{tag}: the right-click on door ({d['x']},{d['y']},{d['z']}) part {d['part']} "
        f"by actor {actor_id} at {stand} facing {facing} emitted NO door ev within 30s"
        f" - host emitted {event_state(host)['coopDoorEvsEmitted']} (was {before}), "
        f"actor TU {W.unit_of(host, actor_id).get('tu')}, battle_action said {ra}. "
        "Either the actor could not pay the door's TU (Tile::openDoor returns 4 and "
        "mutates nothing) or it faced the wrong wall")
    W.settle_reveal(host, client)

    wait_host_idle(host, client)

    # WV-D50, half one: this door ev carries NO walk and NO action context.
    door_evs = [e for e in event_log(host, 60) if e["kind"] == "door"]
    assert door_evs, f"{tag}: no door ev in the host's event ring"
    last_door = door_evs[-1]
    assert last_door["actionId"] == 0, (
        f"{tag}: the right-click door ev rode actionId {last_door['actionId']}, not 0 - "
        "the emitter is assuming an action context it must not need (WV-D50)")

    after_census = assert_door_parity(host, client, tag)
    print(f"    census delta: gone={[e for e in before_census if e not in after_census]} "
          f"new={[e for e in after_census if e not in before_census]}")
    assert after_census != before_census, (
        f"{tag} NON-VACUITY: no door changed state, so the retirement assertion would "
        "pass with nothing having happened")
    after_h = host.cmd({"cmd": "hash_now", "full": True})["h"]
    assert after_h[moving_bucket] != before_h[moving_bucket], (
        f"{tag} NON-VACUITY: the host's `{moving_bucket}` bucket did not move across "
        "the door open, although that is the bucket this door kind writes - so the "
        "EQUAL assertions would be equal-because-nothing-happened")
    assert_hash_clean(host, client, full=True, what=f"{tag} after the right-click door")
    assert_delivery(host, client, tag)
    print(f"    PASS: right-click door ev at seq {last_door['seq']} rode actionId 0 (no "
          f"walk, no action context); `{moving_bucket}` moved "
          f"{before_h[moving_bucket]} -> {after_h[moving_bucket]} on the host and the "
          "CLIENT matches it; census identical and CHANGED; coopDoorInTurnUnsupported "
          "== 0 on BOTH machines while the door part really did SWING on both - "
          "SS2.4's fallback is retired for this path")


def phase_boundary_close(host, client, tag):
    """WV-D50: coopCloseUfoDoors() - the function W1-P13 will call from
    BattlescapeGame::endTurn (BattlescapeGame.cpp:549) instead of
    `_save->getTileEngine()->closeUfoDoors()` - driven through the
    `battle_close_ufo_doors` lever so that "callable outside a walk" is an
    EXERCISED entry point and not a claim about code nobody ran.

    WHAT THIS PROVES: the entry point runs on the host, is refused on a client
    (phase_client_boundary_refused), and - since this fixture has no OPEN ufo
    door - mutates nothing and therefore emits nothing. That last half is a real
    assertion, not a shrug: it is the journal's "nothing mutated => nothing
    emitted" rule, and without it every single turn boundary in a real battle
    would put an empty `door` ev (and a minted seq) on the wire.

    WHAT THIS DOES NOT PROVE, stated rather than glossed: the EMITTING arm - a
    boundary close that actually shuts an open ufo door and ships `op:"close"`.
    That needs a ufo door a wave-1 squad can open, and no fixture this wave can
    generate provides one (see the module docstring's FIXTURES section for the
    three that were measured and why each failed). It is exactly the case the
    runbook already schedules for W1-P13 - G3 criterion 2 and owner
    manual-playtest item 12, both a UFO map with a door opened, walked through
    and then END TURNed."""
    print(f"\n== {tag}: WV-D50 - the TURN-BOUNDARY close, callable outside a walk ==")
    wait_host_idle(host, client)
    open_before = [d for d in find_doors(host) if d["isUfoDoorOpen"]]
    assert not open_before, (
        f"{tag}: this fixture was expected to contain no OPEN ufo door, but "
        f"{len(open_before)} are open - the silent-boundary assertion below would be "
        "asserting the wrong thing")
    before = event_state(host)["coopDoorEvsEmitted"]
    before_seq = event_state(host)["lastSeqEmitted"]

    r = host.cmd({"cmd": "battle_close_ufo_doors"})
    assert r.get("ok"), f"{tag}: battle_close_ufo_doors failed: {r}"
    assert r["closed"] == 0, f"{tag}: closed {r['closed']} doors out of nowhere"
    time.sleep(1.0)
    hs = event_state(host)
    assert hs["coopDoorEvsEmitted"] == before, (
        f"{tag}: coopCloseUfoDoors() emitted a `door` ev although it mutated NOTHING - "
        "the journal's 'nothing mutated => nothing emitted' rule is broken and every "
        "turn boundary would put an empty ev on the wire")
    assert hs["lastSeqEmitted"] == before_seq, (
        f"{tag}: the boundary call minted a seq ({before_seq} -> "
        f"{hs['lastSeqEmitted']}) without mutating anything")
    assert_hash_clean(host, client, full=True, what=f"{tag} after a no-op boundary")
    assert_door_parity(host, client, tag)
    print("    PASS: the boundary entry point RUNS on the host, is refused on a client, "
          "and mutated + emitted NOTHING with no open ufo door on the map")


def phase_client_boundary_refused(host, client, tag):
    """The boundary lever is HOST-ONLY. On a client the wrapper degrades to the
    plain vanilla call, which would be a machine-local terrain mutation - i.e. a
    deliberate desync. Asserted so the guard cannot rot."""
    r = client.cmd({"cmd": "battle_close_ufo_doors"})
    assert not r.get("ok"), (
        f"{tag}: a CLIENT was allowed to run coopCloseUfoDoors() locally: {r}")
    assert "host-only" in r.get("error", ""), \
        f"{tag}: unexpected refusal reason: {r}"
    print(f"    [{tag}] the boundary lever is refused on the client: {r['error']}")


# ----- fixtures -----------------------------------------------------------

def bring_up(tag, mission, qualifies, base_port, base_probe):
    why_log = []
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(base_port + attempt)
        host = GameClient("host", base_probe + attempt * 2,
                          make_user_dir(f"repro_atom_door_{tag}_host_{attempt}"))
        client = GameClient("client", base_probe + 1 + attempt * 2,
                            make_user_dir(f"repro_atom_door_{tag}_client_{attempt}"))
        seated = {}
        try:
            W.bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated, mission=mission)
            why = qualifies(host, client)
            if why is None:
                print(f"[repro_atom_door] {tag} fixture qualifies on attempt "
                      f"{attempt}/{MAX_REROLLS} ({attempt - 1} re-roll(s))")
                return host, client
            why_log.append(why)
            print(f"[repro_atom_door] {tag} re-roll {attempt}/{MAX_REROLLS}: {why}")
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
    raise AssertionError(
        f"FIXTURE: no qualifying {tag} fixture in {MAX_REROLLS} boots - this is a "
        f"fixture failure, not a result about the door atom.\n      "
        f"rejection tally: {tally}\n      last: {why_log[-1] if why_log else None}")


def make_qualifier(want_ufo, approach_max):
    """A boot QUALIFIES only if it can actually be driven.

    Every clause here answers a question PHASE 1 would otherwise have to
    discover the expensive way, and each one reports the NUMBERS it saw. The
    staging-tile clause is the one this file learned the hard way: a boot whose
    only candidate has no walkable staging tile qualified, and then the phase
    failed as a FIXTURE red instead of being re-rolled - which is what turned a
    map-roll property into a 1-in-4 red on a packet's own acceptance repro."""
    def q(host, client):
        st = battle_state(host)
        if not st.get("inBattle"):
            return "no battle"
        # (a) NOTHING SPOTTED ON THE HOST - repro_atom_turn's own rule, and a
        # HARD disqualifier proven the expensive way: a roll whose host set was
        # already {1000000} desynced on the FIRST door walk (`items`,
        # `unitsStats`, `revealHostile`, `saveBlob` all moved apart while
        # `terrain` stayed EQUAL) - i.e. the host reaction-fired, and no wave-1
        # wire carries a shot. The HOST's set is the one that matters because
        # the host is the only machine that simulates.
        if spotted(host):
            return f"a hostile is already visible to the host at t=0: {spotted(host)}"
        # The CLIENT's set differing is NOT a re-roll reason: `battle_state.spotted`
        # is the union of getVisibleUnits() over living player units
        # (TestServer.cpp:6235-6243) and `visible` is saveBlob-EXCLUDED (SS2.8's D4
        # per-unit FOV exclusion), so a client whose blob was snapshotted before
        # the host's own startFirstTurn FOV settled can legitimately carry a
        # different set with every bucket EQUAL. This file pins STABILITY (it
        # compares the PAIR before and after each walk), not equality.
        if spotted(client):
            print(f"    note: the client's t=0 spotted set is {spotted(client)} while "
                  "the host's is empty - hash-excluded, and stability is what is pinned")
        if any(hh != ch for hh, ch in _bucket_pairs(host, client)):
            return ("the fixture is ALREADY divergent at t=0 in "
                    f"{_divergent_buckets(host, client)}")

        seats = seat_units(host)
        doors = closed_doors(host)
        want = "ufo" if want_ufo else "normal"
        kind = [d for d in doors if bool(d["isUfoDoor"]) == want_ufo]
        if not kind:
            return (f"no CLOSED {want} wall-door on the map at all "
                    f"({len(find_doors(host))} door part(s) found, "
                    f"{len(doors)} of them closed wall-doors)")

        cands = walk_through_candidates(host, approach_max, want_ufo=want_ufo)
        if not cands:
            near = _nearest_door_report(seats, kind)
            return (f"{len(kind)} closed {want} door(s), but none is 1..{approach_max} "
                    f"tiles from a seat-1 soldier with the TU to reach it and still "
                    f"act; nearest side per soldier: {near}")

        # THE CLAUSE THE FLAKE TAUGHT: the phase stages every crossing, so a
        # candidate without a walkable staging tile is not a candidate.
        occupied = {unit_pos(u) for u in st.get("units", []) if not u.get("isOut")}

        def _stageable(cs):
            return [c for c in cs
                    if staging_tiles(host, c[1], c[2], occupied,
                                     self_pos=unit_pos(W.unit_of(host, c[0])))]

        # CONTACT-FREE CROSSINGS ARE PREFERRED, WITH A FALLBACK. A crossing walk
        # that moves INTO view can draw reaction fire, and no wave-1 wire carries
        # a shot: the one desync this fixture has ever produced on a good build
        # had `terrain` and `revealHostile` EQUAL while `items`, `unitsCore`,
        # `unitsStats` and `saveBlob` all moved apart - the shot signature, not a
        # door one. So when the map can supply MIN_CROSSINGS crossings whose
        # whole approach box clears session.MAX_VIEW_DISTANCE, this fixture uses
        # ONLY those. It is a preference and not a filter because on most rolls
        # of this map class nothing clears that cap at walking distance, and a
        # hard filter would be a fixture that never runs.
        clean = _stageable(walk_through_candidates(host, approach_max,
                                                   want_ufo=want_ufo,
                                                   clean_only=True))
        stageable = clean if len(clean) >= MIN_CROSSINGS else _stageable(cands)
        if len(stageable) < MIN_CROSSINGS:
            near = _nearest_door_report(seats, kind)
            return (f"only {len(stageable)} stageable crossing(s) of {len(cands)} "
                    f"candidate(s) - MIN_CROSSINGS is {MIN_CROSSINGS}, because every "
                    "observed red was a one-candidate boot whose single marginal "
                    f"crossing had no route; nearest door side per soldier: {near}")
        print(f"    fixture: {len(find_doors(host))} door part(s), {len(kind)} closed "
              f"{want}, {len(cands)} candidate crossing(s), {len(stageable)} of them "
              f"stageable, {len(clean)} contact-free (MIN_CROSSINGS {MIN_CROSSINGS})")
        return None
    return q


def _bucket_pairs(host, client):
    hh = host.cmd({"cmd": "hash_now", "full": True}).get("h", {})
    ch = client.cmd({"cmd": "hash_now", "full": True}).get("h", {})
    return [(hh[k], ch.get(k)) for k in hh]


def _divergent_buckets(host, client):
    hh = host.cmd({"cmd": "hash_now", "full": True}).get("h", {})
    ch = client.cmd({"cmd": "hash_now", "full": True}).get("h", {})
    return [k for k in hh if hh[k] != ch.get(k)]


def _nearest_door_report(seats, doors):
    """(soldier id, TU, Chebyshev distance to the nearest door side) - the numbers
    a fixture rejection has to print so it does not need reproducing."""
    out = []
    for u in seats:
        p = unit_pos(u)
        best = None
        for d in doors:
            sides = door_sides(d)
            if sides is None:
                continue
            for t in sides:
                c = cheb(p, t)
                if best is None or c < best:
                    best = c
        out.append((u["id"], u.get("tu"), best))
    return out


def main():
    t0 = time.time()
    print(f"=== FIXTURE: {DOOR_MISSION} (NORMAL doors - the `terrain` bucket) ===")
    host, client = bring_up("door", DOOR_MISSION,
                            make_qualifier(False, NORMAL_APPROACH_MAX), 48820, 49820)
    try:
        # PHASE ORDER: walk first. Wave 1 has no side transition, so TU never
        # regenerate and whichever phase runs second inherits a spent squad -
        # running the right-click first was tried and MEASURED WORSE (1/7 green
        # against 6/10), because its approach loop walks several actors before
        # it finds one it can use and the walk phase was then left with no
        # candidate at all. The coupling is real in both directions; this is the
        # cheaper end of it.
        phase_walk_through(host, client, want_ufo=False,
                           approach_max=NORMAL_APPROACH_MAX,
                           tag="PHASE 1", moving_bucket="terrain")
        phase_right_click(host, client, NORMAL_APPROACH_MAX, want_ufo=False,
                          tag="PHASE 2", moving_bucket="terrain")
        phase_client_boundary_refused(host, client, "PHASE 3")
        phase_boundary_close(host, client, "PHASE 3")
    finally:
        host.shutdown()
        client.shutdown()
    print(f"\nrepro_atom_door: PASS ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, TimeoutError) as e:
        # TimeoutError too: a bare `wait_for` timeout is still a FAILED RUN
        # and must be reported as one (exit 2, with the message), not as an
        # exit-1 traceback that reads like a crash.
        print(f"\nrepro_atom_door: FAIL\n{type(e).__name__}: {e}")
        sys.exit(2)
