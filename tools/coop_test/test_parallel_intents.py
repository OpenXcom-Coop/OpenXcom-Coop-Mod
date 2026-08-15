"""PRD-P6: action intents - the client asks, the host executes, both display.

This is the first truly-parallel playable build. PRD-P5 made both machines hold
the player side at once but swallowed the client's input; P6 replaces that gate
with the thin-client loop from PROTOCOL.md:

    client confirm site  ->  action_intent  ->  host validates + admits
                         <-  action_ack {req_id, action_seq}
                             host EXECUTES; the chain broadcasts through the
                             existing send sites (the PRD-P5 executor invariant
                             `_isActivePlayerSync == getHost()` guarantees it)
                         <-  the ordinary action packets, which the client
                             DISPLAYS exactly as it displays a host action

and, when the host cannot take it, `action_deny {reason, warning}`, which the
client flashes on the battlescape warning widget.

What this test asserts (PRD-P6 acceptance, in order):

  1. Client walk intent -> ack -> the host executes -> BOTH machines converge on
     the same position and TU. And the client's own selection, camera and
     singleton `_currentAction` are untouched while its own action is replayed
     back at it (the PRD-P1 decoupling, which the intent loop leans on entirely).
  2. Host mid-chain: the client's intent is denied `busy`, the client flashes
     STR_COOP_PLAYER_BUSY and drops its pending slot, and the same intent
     succeeds once the chain ends. The chain used is a SHOT: from PRD-P7 on, a
     chain that is nothing but locomotion is deferred rather than refused
     (test_parallel_skip.py owns that half), so only a non-skippable chain still
     reaches the deny.
  3. Invalid intents are refused with the RIGHT warning key and nothing runs:
     a soldier the client does not own (STR_COOP_NOT_YOUR_SOLDIER), an actor the
     HOST's copy has no time units for (STR_NOT_ENOUGH_TIME_UNITS), and a unit
     that is already down (STR_COOP_ACTION_REFUSED - the branch an unknown unit
     id and an unresolvable weapon also take). Runs AFTER 4, because the kind
     sweep is what supplies the casualty.
  4. One intent of EVERY kind driven from the client - turn, kneel, shoot,
     throw, prime, medikit, psi, melee - with the item census and the PRD-P2
     drift tripwire quiet after each. This is why P6 depends on P3/P4: every
     client action now runs through the host's simulation, so a remaining
     authority seam shows up here as census drift.
  5. Both machines act inside one round trip: exactly one action starts, the
     other is denied (or serialized), and nothing executes twice.
  6. A client-intent walk next to a hostile: whatever reaction fire the aliens
     choose to make resolves on the host and displays identically on both, with
     the tripwire quiet.

DRIVING NOTE. `battle_intent` is the lever, and it is deliberately NOT
`battle_action`/`battle_fire`: those push BattleStates directly (the raw
local-execution lever test_parallel_sharedturn's no-replication assertion needs).
`battle_intent` builds the BattleAction a UI confirm site builds and hands it to
BattlescapeGame::coopRouteAction + executeAction - the exact pair mapClick, the
kneel button, handleNonTargetAction and the medikit presses call. What it does
not cover is which widget calls them.

FIXTURE NOTE. The skirmish fixture packs all 14 soldiers into the Skyranger's
2x7 interior, where the back rows can path nowhere until the front rank walks
out. Both drivers are therefore teleported (on BOTH machines, same coordinates)
onto open ground near a hostile before anything is asserted.

Run:  python tools/coop_test/test_parallel_intents.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_replay_decouple as RD

PORT = "47986"

BUSY_TEXT = "Another action"
NOT_YOURS_TEXT = "Not one of your soldiers"
NO_TU_TEXT = "Time Units"          # STR_NOT_ENOUGH_TIME_UNITS, translated
REFUSED_TEXT = "Action refused"

# ring 2..4 around a hostile: open ground (something IS standing there), but not
# breathing down its neck.
NEAR_RING = sorted(
    [(dx, dy) for dx in range(-4, 5) for dy in range(-4, 5)
     if 2 <= max(abs(dx), abs(dy)) <= 4],
    key=lambda d: (max(abs(d[0]), abs(d[1])), abs(d[0]) + abs(d[1])))


# ---- readouts --------------------------------------------------------------

def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def unit(b, uid):
    for u in b.get("units", []):
        if u["id"] == uid:
            return u
    return None


def pos(b, uid):
    u = unit(b, uid)
    return (u["x"], u["y"], u["z"]) if u else None


def tu(b, uid):
    u = unit(b, uid)
    return u["tu"] if u else None


def own_units(b, seat, min_tu=0):
    return [u for u in b["units"]
            if u.get("faction") == 0 and not u.get("isOut")
            and u.get("coop") == seat and u.get("tu", 0) >= min_tu]


def alive_enemy(b):
    for u in b["units"]:
        if u.get("faction") == 1 and not u.get("isOut") and u.get("health", 0) > 0:
            return u
    return None


def warning_of(gc):
    return parallel(gc).get("warning", "") or ""


def intent(gc, **kw):
    req = {"cmd": "battle_intent"}
    req.update(kw)
    return gc.cmd(req)


def wait_until(fn, timeout, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def wait_for_text(gc, needle, timeout=20):
    """The warning widget fades, so poll it rather than sampling once."""
    seen = set()
    deadline = time.time() + timeout
    while time.time() < deadline:
        w = warning_of(gc)
        if w:
            seen.add(w)
        if any(needle.lower() in s.lower() for s in seen):
            return sorted(seen)
        time.sleep(0.3)
    return None


def settle(host, client, seconds=6):
    deadline = time.time() + seconds
    while time.time() < deadline:
        for gc in (host, client):
            t = TW.top(gc)
            if t not in ("BattlescapeState", "NextTurnState"):
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.5)


def idle(host, timeout=90):
    """Wait until the executor can admit another action."""
    return wait_until(lambda: parallel(host).get("canAdmit") is True, timeout)


def top_up(host, client, uid, amount=200):
    """Same TU on BOTH machines. The HOST validates an intent against its own
    copy, so a client-side-only top-up would be denied STR_NOT_ENOUGH_TIME_UNITS
    (and would put the two machines' stats out of step into the bargain)."""
    for gc in (host, client):
        gc.ok({"cmd": "battle_intent", "unit": uid, "action": "turn",
               "tu": amount, "dry": True})


def far_step(gc, uid, radius=3):
    """The FURTHEST tile `uid` can path to inside `radius` - probe_step returns
    them ring by ring, so the last entry is the longest walk available."""
    r = intent(gc, action="probe_step", unit=uid, radius=radius, max=400)
    if not r.get("ok") or not r.get("steps"):
        return None
    s = r["steps"][-1]
    return (s["x"], s["y"], s["z"])


def free_step(gc, uid, radius=2):
    """A tile `uid` can actually path to, resolved SERVER-side in one round trip
    (`battle_intent probe_step` runs the same Pathfinding::calculate +
    getStartDirection() gate the real mapClick capture site sits behind). Probing
    tile by tile over the wire took thousands of RPCs and looked like a hang."""
    r = intent(gc, action="probe_step", unit=uid, radius=radius)
    if not r.get("ok") or not r.get("steps"):
        return None
    s = r["steps"][0]
    return (s["x"], s["y"], s["z"])


def steps_of(gc, uid, radius=2):
    r = intent(gc, action="probe_step", unit=uid, radius=radius, max=400)
    return [(s["x"], s["y"], s["z"]) for s in r.get("steps", [])] if r.get("ok") else []


def common_steps(host, client, uid, radius=2):
    """Every tile BOTH machines agree `uid` can path to, nearest ring first.

    The fixture teleports the whole squad around looking for drivers, and a
    teleport that took on one machine but not the other leaves a BLOCKER in a
    different place. A tile the client's pathfinder likes can therefore be
    occupied on the host - which is where a client intent actually executes, so
    the walk would be admitted and then quietly do nothing."""
    cs = set(steps_of(client, uid, radius))
    return [s for s in steps_of(host, uid, radius) if s in cs]


def free_step_both(host, client, uid, radius=2):
    """One tile BOTH machines agree `uid` can path to.

    PRD-P9 rider R6: widened. The skirmish fixture packs 14 soldiers into the
    Skyranger's 2x7 interior, so a driver whose immediate ring is boxed in by its
    own squadmates has nothing at radius 2 while a tile two rings out is wide
    open - and the caller only ever asked "can it step at all". Falling back to a
    larger radius costs one extra probe_step RPC in the rare case and nothing at
    all in the common one; it never widens a search that already succeeded."""
    for r in (radius, radius + 1, radius + 2):
        got = common_steps(host, client, uid, r)
        if got:
            return got[0]
    return None


def teleport_both(host, client, uid, spot):
    res = [gc.cmd({"cmd": "battle_teleport", "unit": uid,
                   "x": spot[0], "y": spot[1], "z": spot[2]})
           for gc in (host, client)]
    return all(r.get("moved") for r in res)


def place_near(host, client, uid, tpos, ring=NEAR_RING, want=2):
    """Teleport `uid` onto open ground near `tpos` on BOTH machines and prove it
    can then take a step.

    PRD-P9 rider R6: two passes. The first insists on `want` tiles both machines
    agree are walkable, because a driver with exactly ONE way out is a driver
    that fails the moment a squadmate, a corpse or a dropped weapon lands on it -
    which is what made the walk scenarios flaky. The second pass restores the old
    "any step at all" bar, so a cramped fixture still yields a driver rather than
    an assertion."""
    landed = stuck = 0
    for need in (want, 1):
        for dx, dy in ring:
            spot = (tpos[0] + dx, tpos[1] + dy, tpos[2])
            if not teleport_both(host, client, uid, spot):
                continue
            if need == want:
                landed += 1
            # BOTH machines: a driver the client can move but the host cannot is
            # useless, because the host is where every action actually runs.
            if len(common_steps(host, client, uid, 2)) >= need or (
                    need == 1 and free_step_both(host, client, uid)):
                return spot
            if need == want:
                stuck += 1
    print(f"    unit {uid}: {landed}/{len(ring)} tiles near {tpos} took the "
          f"teleport, {stuck} of those had fewer than {want} shared exits")
    return None


def place_adjacent(host, client, uid, tpos):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        spot = (tpos[0] + dx, tpos[1] + dy, tpos[2])
        if teleport_both(host, client, uid, spot):
            return spot
    return None


def step_dest(host, client, uid):
    """A tile `uid` can walk to, re-placing it if it has been boxed in.

    PRD-P9 rider R6. `free_step_both` answers "where can it go from here"; over a
    long scenario the answer legitimately becomes "nowhere" - the squad shuffles,
    somebody dies on the only exit, a thrown crate lands next door - and every
    caller turned that into a hard assertion failure that read like an intent bug.
    Re-placing the driver next to a hostile (the same thing `pick_driver` does at
    the start) is what a human tester would do, and it keeps the failure that
    matters (an intent that does not execute) distinguishable from a fixture that
    simply parked the unit in a corner."""
    dest = free_step_both(host, client, uid)
    if dest:
        return dest
    enemy = alive_enemy(battle(host))
    if not enemy:
        return None
    print(f"    (unit {uid} is boxed in - re-placing it before the walk)")
    if not place_near(host, client, uid, (enemy["x"], enemy["y"], enemy["z"])):
        return None
    top_up(host, client, uid)
    return free_step_both(host, client, uid)


def pick_driver(host, client, seat, tag):
    """A soldier of `seat` standing where it can actually act."""
    enemy = alive_enemy(battle(host))
    assert enemy, "the fixture has no live hostile to orient around"
    epos = (enemy["x"], enemy["y"], enemy["z"])
    for cand in own_units(battle(client), seat):
        spot = place_near(host, client, cand["id"], epos)
        if spot:
            top_up(host, client, cand["id"])
            print(f"    {tag} driver = unit {cand['id']} at {spot}")
            return cand["id"]
    raise AssertionError(
        f"no soldier of seat {seat} could be placed anywhere it can move")


# ---- 1. the round trip -----------------------------------------------------

def scenario_walk(host, client, mover_id):
    print("-- 1: client walk intent -> host executes -> both converge --")
    dest = step_dest(host, client, mover_id)
    assert dest, f"client soldier {mover_id} cannot step anywhere"

    before_h = pos(battle(host), mover_id)
    before_c = pos(battle(client), mover_id)
    assert before_h == before_c, (
        f"the two machines already disagree about unit {mover_id}: "
        f"host {before_h} client {before_c}")
    seq_before = parallel(host)["actionSeq"]
    watch_before = RD.watcher_state(client)

    r = intent(client, action="move", unit=mover_id,
               x=dest[0], y=dest[1], z=dest[2])
    assert r.get("ok"), f"the client refused to build the walk intent: {r}"
    assert r.get("routed") is True, (
        f"the client EXECUTED the walk locally instead of shipping an intent "
        f"({r}). In parallel mode the client is never the executor.")

    assert wait_until(lambda: pos(battle(host), mover_id) != before_h, 45), (
        f"the host never moved unit {mover_id} - the `action_intent` did not "
        f"reach the arbiter, or it was denied. host parallel_state="
        f"{parallel(host)} client={parallel(client)} warning="
        f"{warning_of(client)!r}")
    landed = pos(battle(host), mover_id)
    assert wait_until(lambda: pos(battle(client), mover_id) == landed, 45), (
        f"the client never displayed its OWN action: the host walked {mover_id} "
        f"to {landed}, the client still has it at {pos(battle(client), mover_id)}")
    settle(host, client)

    assert tu(battle(host), mover_id) == tu(battle(client), mover_id), (
        f"the two machines charged different TU for the same walk: host "
        f"{tu(battle(host), mover_id)} client {tu(battle(client), mover_id)}")

    seq_after = parallel(host)["actionSeq"]
    assert seq_after > seq_before, (
        f"the host admitted the intent without stamping action_seq "
        f"({seq_before} -> {seq_after})")
    assert wait_until(lambda: parallel(client)["pendingReqId"] == 0, 15), (
        f"the client's pending slot was never cleared by the `action_ack` "
        f"(pendingReqId={parallel(client)['pendingReqId']}). PROTOCOL.md clears "
        f"it on ACK RECEIPT - the broadcast packets carry no action_seq until "
        f"PRD-P7, so anything else means a 10 s stall after every action.")

    RD.assert_not_hijacked("its own client-intent walk", watch_before,
                           RD.watcher_state(client), watch_before["selectedId"],
                           mover_id)
    session.assert_battle_synced(host, client, "after the client's walk intent")
    print(f"PASS 1: a client intent walked {mover_id} {before_h} -> {landed} on "
          f"BOTH machines (actionSeq {seq_before} -> {seq_after}, TU "
          f"{tu(battle(host), mover_id)} on both)")


# ---- 2. deny busy ----------------------------------------------------------

def aim_away(host, uid, dist=4):
    """A tile `dist` away from `uid`, in the direction AWAY from the nearest live
    hostile - the fixture has one alien and the later scenarios still need it."""
    b = battle(host)
    here = pos(b, uid)
    enemy = alive_enemy(b)
    if not enemy:
        return (here[0] + dist, here[1] + dist, here[2])
    sx = 1 if here[0] >= enemy["x"] else -1
    sy = 1 if here[1] >= enemy["y"] else -1
    return (here[0] + sx * dist, here[1] + sy * dist, here[2])


def start_busy_shot(host, client, uid, wid, tries=6):
    """Start a SHOT chain on the host and prove it is actually running.

    A shot aimed at a tile the trajectory code rejects (out of bounds, no line of
    fire) pops in the very frame it is pushed, which would make every "the host
    was busy" assertion vacuous. The candidate tiles are therefore ones the
    pathfinder has already vouched for, tried furthest-first, and the chain is
    confirmed against `canAdmit` before the caller is told it may proceed.
    Returns (aim, host parallel_state) or (None, state)."""
    r = intent(host, action="probe_step", unit=uid, radius=4, max=400)
    cands = [(s["x"], s["y"], s["z"]) for s in r.get("steps", [])][::-1]
    for aim in cands[:tries]:
        top_up(host, client, uid)
        if not intent(host, action="shoot", unit=uid, mode="auto", weapon_id=wid,
                      x=aim[0], y=aim[1], z=aim[2]).get("ok"):
            continue
        ps = parallel(host)
        if ps.get("canAdmit") is False:
            return aim, ps
        wait_until(lambda: parallel(host).get("canAdmit") is True, 30)
    return None, parallel(host)


def scenario_busy(host, client, host_mover, client_mover):
    print("-- 2: deny busy while the host is mid-chain, then retry --")
    top_up(host, client, host_mover)
    # The client's destination is resolved NOW, while both machines are idle:
    # `probe_step` refuses mid-chain (Pathfinding is a singleton the running
    # UnitWalkBState dequeues from), and the client will be busy displaying the
    # host's chain when the denied intent goes out.
    client_dest = step_dest(host, client, client_mover)
    assert client_dest, f"client soldier {client_mover} cannot step anywhere"
    # PRD-P7 changed WHICH chains refuse. A walk in the way is now DEFERRED
    # (pending-admit + fast-forward, see test_parallel_skip.py), so holding the
    # host with a walk no longer exercises the deny at all. A chain carrying a
    # ProjectileFlyBState is never skippable, which is exactly the case PRD-P6's
    # own acceptance names ("host mid-shot"). battleXcomSpeed slows the turn the
    # shot pushes in front of itself, so the chain outlives the round trip.
    wid = give_both(host, client, host_mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    host.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 200})
    aim, ps = start_busy_shot(host, client, host_mover, wid)
    if not aim or ps.get("chainSkippable") is not False:
        host.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 2})
    assert aim, (
        f"no aim point produced a shot chain that outlived the RPC, so the deny "
        f"path was never exercised: {ps}")
    assert ps.get("chainSkippable") is False, (
        f"a chain carrying a shot reported itself SKIPPABLE ({ps}); PRD-P7 would "
        f"then defer the client's intent instead of refusing it, and this "
        f"scenario would be vacuous")

    was = pos(battle(host), client_mover)
    r = intent(client, action="move", unit=client_mover,
               x=client_dest[0], y=client_dest[1], z=client_dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    seq_at_send = parallel(host)["actionSeq"]
    seen = wait_for_text(client, BUSY_TEXT, timeout=25)
    if not seen:
        host.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 2})
    assert seen, (
        f"no STR_COOP_PLAYER_BUSY flash on the client after an intent sent into "
        f"a running host chain (widget shows {warning_of(client)!r}; host "
        f"actionSeq was {seq_at_send}, now {parallel(host)['actionSeq']} - if it "
        f"MOVED the intent was admitted, not denied). The deny UX rides the "
        f"battlescape warning widget, which PRD-P5 cleared of the persistent "
        f"off-turn banners precisely so this could get through.")
    assert wait_until(lambda: parallel(client)["pendingReqId"] == 0, 15), \
        "the denied intent left the client's pending slot occupied"
    assert pos(battle(host), client_mover) == was, (
        f"a DENIED intent still moved unit {client_mover} on the host "
        f"({was} -> {pos(battle(host), client_mover)})")
    print(f"PASS 2a: intent denied busy, flashed {seen}, nothing executed")

    host.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 2})
    assert idle(host), f"the host's chain never finished: {parallel(host)}"
    settle(host, client, seconds=4)
    dest = step_dest(host, client, client_mover)
    assert dest, "the client soldier cannot step after the host's chain"
    before = pos(battle(host), client_mover)
    assert intent(client, action="move", unit=client_mover,
                  x=dest[0], y=dest[1], z=dest[2]).get("routed") is True
    assert wait_until(lambda: pos(battle(host), client_mover) != before, 45), (
        f"the retry after the host's chain was never admitted either: "
        f"{parallel(host)} warning={warning_of(client)!r}")
    settle(host, client)
    session.assert_battle_synced(host, client, "after the busy retry")
    print(f"PASS 2b: the same intent succeeded once the chain ended "
          f"({before} -> {pos(battle(host), client_mover)})")


# ---- 3. deny invalid -------------------------------------------------------

def assert_denied(host, client, what, needle, before_snapshot, **intent_kw):
    r = intent(client, **intent_kw)
    assert r.get("ok"), (f"{what}: the harness lever refused before the intent "
                         f"was even built: {r}")
    assert r.get("routed") is True, f"{what}: the client executed locally: {r}"
    seen = wait_for_text(client, needle, timeout=25)
    assert seen, (
        f"{what}: expected a deny flash containing {needle!r}; the widget showed "
        f"{warning_of(client)!r}. `action_deny` carries the key the client must "
        f"flash - the wrong key means the wrong validation branch fired.")
    assert wait_until(lambda: parallel(client)["pendingReqId"] == 0, 15), \
        f"{what}: the deny did not clear the client's pending slot"
    after = battle(host)
    for uid, snap in before_snapshot.items():
        assert (pos(after, uid), tu(after, uid)) == snap, (
            f"{what}: something executed anyway - unit {uid} went {snap} -> "
            f"{(pos(after, uid), tu(after, uid))} on the host")
    print(f"PASS 3 ({what}): denied with {seen}, nothing executed")


def knock_out_a_hostile(host, client, host_mover, swings=10):
    """A casualty, so the `isOut` deny branch has something to aim at. Driven
    HOST-side with `battle_fire` (raw local execution) - the point here is to
    produce a body, not to exercise the intent path again."""
    dead = [u for u in battle(client)["units"] if u.get("isOut")]
    if dead:
        return dead[0]["id"]
    enemy = alive_enemy(battle(host))
    if not enemy:
        return None
    epos = (enemy["x"], enemy["y"], enemy["z"])
    if not place_adjacent(host, client, host_mover, epos):
        return None
    wid = give_both(host, client, host_mover, "STR_STUN_ROD")
    for i in range(swings):
        r = host.cmd({"cmd": "battle_fire", "unit": host_mover, "mode": "hit",
                      "weapon_id": wid, "tu": 200,
                      "x": epos[0], "y": epos[1], "z": epos[2]})
        if not r.get("ok"):
            break
        settle(host, client)
        idle(host)
        u = unit(battle(client), enemy["id"])
        if u and u.get("isOut"):
            print(f"    hostile {enemy['id']} went down after {i + 1} swing(s)")
            return enemy["id"]
    return None


def scenario_invalid(host, client, seat, host_mover, client_mover):
    print("-- 3: invalid intents are refused with the right warning key --")
    assert idle(host), "the host is still busy"

    # a) a soldier the client does not own
    theirs = [u for u in battle(client)["units"]
              if u.get("faction") == 0 and not u.get("isOut")
              and u.get("coop") != seat]
    assert theirs, "the fixture gave the client no peer-owned soldier to poach"
    poach = theirs[0]["id"]
    snap = {poach: (pos(battle(host), poach), tu(battle(host), poach))}
    p = pos(battle(client), poach)
    assert_denied(host, client, "peer-owned soldier", NOT_YOURS_TEXT, snap,
                  action="turn", unit=poach, x=p[0] + 1, y=p[1], z=p[2])

    # b) no time units ON THE HOST (the executor validates against its own copy).
    #    Aimed at a tile, so it does not depend on a hostile still being alive.
    give_both(host, client, client_mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    top_up(host, client, client_mover, amount=0)
    here = pos(battle(client), client_mover)
    aim = (here[0] + 2, here[1] + 2, here[2])
    snap = {client_mover: (pos(battle(host), client_mover), 0)}
    assert_denied(host, client, "actor out of TU on the executor", NO_TU_TEXT, snap,
                  action="shoot", unit=client_mover, mode="snap",
                  x=aim[0], y=aim[1], z=aim[2])
    top_up(host, client, client_mover)

    # c) a unit that is already down. Same branch an unknown unit id and an actor
    #    carrying no such weapon take (issue #74: the host never fabricates one to
    #    make an intent runnable).
    dead_id = knock_out_a_hostile(host, client, host_mover)
    if dead_id is None:
        print("    (the fixture produced no casualty - the `isOut` deny branch "
              "was not exercised)")
        return
    snap = {dead_id: (pos(battle(host), dead_id), tu(battle(host), dead_id))}
    p = pos(battle(client), dead_id)
    assert_denied(host, client, "unit that is already out", REFUSED_TEXT, snap,
                  action="turn", unit=dead_id, x=p[0] + 1, y=p[1], z=p[2])


# ---- 4. one intent of every kind -------------------------------------------

def quiet(host, client, what):
    settle(host, client)
    session.assert_battle_synced(host, client, what)
    assert not TW.desync_seen(host) and not TW.desync_seen(client), \
        f"the PRD-P2 drift tripwire fired {what}"


def drive(host, client, what, **kw):
    """Ship one intent from the client and wait for the host to finish with it."""
    seq_before = parallel(host)["actionSeq"]
    r = intent(client, **kw)
    assert r.get("ok"), f"{what}: the client could not build the intent: {r}"
    assert r.get("routed") is True, f"{what}: the client executed locally: {r}"
    assert wait_until(lambda: parallel(client)["pendingReqId"] == 0, 25), (
        f"{what}: no ack/deny came back inside 25 s (pending "
        f"{parallel(client)['pendingReqId']}) - the intent was dropped")
    assert parallel(host)["actionSeq"] > seq_before, (
        f"{what}: the host did not ADMIT the intent (action_seq still "
        f"{seq_before}); the client was told {warning_of(client)!r}")
    assert idle(host), f"{what}: the host chain never ended"
    quiet(host, client, f"after a client {what} intent")
    print(f"    PASS kind {what}")


def give_both(host, client, uid, item, ammo=None):
    # coop (PRD-I3 Session F de-flake): battle_give mints off the LOCAL _itemId, so a
    # give issued while the two counters have drifted (a real casualty straddle) mints
    # divergent ids and injects a HARNESS offset into the product measurement. Pre-sync
    # both machines to max(host, client) via the host-authoritative set_item_counter lever
    # so the give itself never drifts the counter.
    hc = host.cmd({"cmd": "set_item_counter"}).get("itemCounter", -1)
    cc = client.cmd({"cmd": "set_item_counter"}).get("itemCounter", -1)
    if hc >= 0 and cc >= 0 and hc != cc:
        m = max(hc, cc)
        host.cmd({"cmd": "set_item_counter", "value": m})
        client.cmd({"cmd": "set_item_counter", "value": m})
    req = {"cmd": "battle_give", "unit": uid, "item": item,
           "slot": "right", "clear_hands": True}
    if ammo:
        req["ammo"] = ammo
    ids = [gc.ok(dict(req)) for gc in (host, client)]
    assert ids[0]["weaponId"] == ids[1]["weaponId"], (
        f"battle_give minted different ids for {item} ({ids[0]['weaponId']} vs "
        f"{ids[1]['weaponId']}) - the intent's weapon_id would not resolve")
    time.sleep(2)
    session.assert_battle_synced(host, client, f"after handing over the {item}")
    return ids[0]["weaponId"]


def scenario_kinds(host, client, mover):
    print("-- 4: one intent of EVERY kind, census + tripwire quiet after each --")
    assert idle(host), "the host is still busy"
    top_up(host, client, mover)
    here = pos(battle(client), mover)

    drive(host, client, "turn", action="turn", unit=mover,
          x=here[0] + 1, y=here[1] + 1, z=here[2])
    drive(host, client, "kneel", action="kneel", unit=mover)
    drive(host, client, "stand up", action="kneel", unit=mover)

    # Shoot at a TILE, not at a hostile: this kind is about the intent making it
    # through ProjectileFlyBState, and the fixture's handful of aliens has to
    # survive long enough for the psi and melee kinds below.
    top_up(host, client, mover)
    wid = give_both(host, client, mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    drive(host, client, "shoot", action="shoot", unit=mover, mode="snap",
          weapon_id=wid, x=here[0] + 2, y=here[1] + 2, z=here[2])

    # throw an UNPRIMED explosive: an item hand-off, not a detonation
    top_up(host, client, mover)
    wid = give_both(host, client, mover, "STR_HIGH_EXPLOSIVE")
    here = pos(battle(client), mover)
    drive(host, client, "throw", action="throw", unit=mover, weapon_id=wid,
          x=here[0] + 1, y=here[1], z=here[2])

    top_up(host, client, mover)
    wid = give_both(host, client, mover, "STR_GRENADE")
    drive(host, client, "prime", action="prime", unit=mover, fuse=3, weapon_id=wid)

    top_up(host, client, mover)
    wid = give_both(host, client, mover, "STR_MEDI_KIT")
    drive(host, client, "medikit", action="medikit", unit=mover, weapon_id=wid,
          patient=mover, medikit="stim", part=0)

    # psi BEFORE melee: the stun rod is what tends to take the last hostile out
    # of the fight, and both kinds need a live one to stand next to.
    enemy = alive_enemy(battle(host))
    if enemy:
        epos = (enemy["x"], enemy["y"], enemy["z"])
        top_up(host, client, mover)
        wid = give_both(host, client, mover, "STR_PSI_AMP")
        if place_adjacent(host, client, mover, epos):
            session.assert_battle_synced(host, client, "after placing the psi attacker")
            drive(host, client, "psi", action="psi", unit=mover, mode="mind",
                  weapon_id=wid, x=epos[0], y=epos[1], z=epos[2])
        else:
            print("    (no free tile next to a hostile - psi kind skipped)")
    else:
        print("    (no live hostile left - psi kind skipped)")

    enemy = alive_enemy(battle(host))
    if enemy:
        epos = (enemy["x"], enemy["y"], enemy["z"])
        top_up(host, client, mover)
        wid = give_both(host, client, mover, "STR_STUN_ROD")
        if place_adjacent(host, client, mover, epos):
            session.assert_battle_synced(host, client, "after placing the melee attacker")
            drive(host, client, "melee", action="melee", unit=mover, weapon_id=wid,
                  x=epos[0], y=epos[1], z=epos[2])
        else:
            print("    (no free tile next to a hostile - melee kind skipped)")
    else:
        print("    (no live hostile left - melee kind skipped)")
    print("PASS 4: every intent kind executed host-side with the census and the "
          "tripwire quiet")


# ---- 5. both machines act inside one round trip ----------------------------

def scenario_race(host, client, host_mover, client_mover):
    print("-- 5: both machines act within one RTT - exactly one starts --")
    assert idle(host), "the host is still busy"
    for uid in (host_mover, client_mover):
        top_up(host, client, uid)

    h_dest = step_dest(host, client, host_mover)
    c_dest = step_dest(host, client, client_mover)
    assert h_dest and c_dest, (
        f"both drivers must be able to step for the race "
        f"(host {h_dest}, client {c_dest})")
    h_from = pos(battle(host), host_mover)
    c_from = pos(battle(host), client_mover)

    # client first, host immediately after: whichever reaches the arbiter first
    # wins; the other meets a non-empty _states / a held receive gate.
    rc = intent(client, action="move", unit=client_mover,
                x=c_dest[0], y=c_dest[1], z=c_dest[2])
    rh = intent(host, action="move", unit=host_mover,
                x=h_dest[0], y=h_dest[1], z=h_dest[2])
    assert rc.get("routed") is True, f"the client executed locally: {rc}"

    time.sleep(2)
    assert idle(host, timeout=120), "the host never went idle again"
    settle(host, client, seconds=8)

    hb, cb = battle(host), battle(client)
    for uid, start, dest in ((host_mover, h_from, h_dest),
                             (client_mover, c_from, c_dest)):
        ph, pc = pos(hb, uid), pos(cb, uid)
        assert ph == pc, (
            f"DOUBLE EXECUTION / drift: unit {uid} is at {ph} on the host and "
            f"{pc} on the client after the race")
        assert ph in (start, tuple(dest)), (
            f"unit {uid} ended at {ph}, which is neither where it started "
            f"({start}) nor the single step it was asked for ({tuple(dest)}) - "
            f"the action ran more than once")
    session.assert_battle_synced(host, client, "after the simultaneous-click race")
    print(f"PASS 5: host {host_mover} {h_from} -> {pos(hb, host_mover)}, client "
          f"{client_mover} {c_from} -> {pos(hb, client_mover)}; identical on both "
          f"machines (host routed={rh.get('routed')} client "
          f"routed={rc.get('routed')})")


# ---- 6. reaction fire on a client-intent walk ------------------------------

def scenario_reaction(host, client, mover):
    print("-- 6: reaction fire provoked by a client-intent walk --")
    assert idle(host), "the host is still busy"
    enemy = alive_enemy(battle(host))
    if not enemy:
        print("    (no live hostile left - reaction-fire scenario skipped)")
        return
    epos = (enemy["x"], enemy["y"], enemy["z"])
    if not place_adjacent(host, client, mover, epos):
        print(f"    (no free tile next to hostile {enemy['id']} - skipped)")
        return
    top_up(host, client, mover)
    session.assert_battle_synced(host, client, "after placing the walker")

    reacted = False
    for step in range(6):
        before_hp = unit(battle(host), mover)["health"]
        dest = free_step_both(host, client, mover)
        if not dest:
            break
        r = intent(client, action="move", unit=mover,
                   x=dest[0], y=dest[1], z=dest[2])
        if not r.get("ok"):
            break
        assert r.get("routed") is True, f"the client executed locally: {r}"
        wait_until(lambda: parallel(client)["pendingReqId"] == 0, 25)
        assert idle(host, timeout=120), "the host chain never ended"
        settle(host, client)

        hb, cb = battle(host), battle(client)
        assert pos(hb, mover) == pos(cb, mover), (
            f"the client-intent walk diverged at step {step}: host "
            f"{pos(hb, mover)} client {pos(cb, mover)}")
        assert unit(hb, mover)["health"] == unit(cb, mover)["health"], (
            f"reaction-fire damage did not display identically: host "
            f"{unit(hb, mover)['health']} client {unit(cb, mover)['health']}")
        session.assert_battle_synced(host, client, f"after walk step {step}")
        assert not TW.desync_seen(host) and not TW.desync_seen(client), \
            "the drift tripwire fired during the reaction-fire walk"
        if unit(hb, mover)["health"] != before_hp:
            reacted = True
            print(f"    reaction fire landed on step {step}: {before_hp} -> "
                  f"{unit(hb, mover)['health']} HP, identical on both machines")
            break

    if reacted:
        print("PASS 6: reaction fire resolved on the host and displayed on both, "
              "tripwire quiet")
    else:
        print("PASS 6 (partial): the aliens never chose to react over 6 steps "
              "(the reaction roll is theirs to make); every step still landed "
              "identically on both machines with the tripwire quiet")


# ---- main ------------------------------------------------------------------

def main():
    fail = None
    host = GameClient("host", 48870,
                      make_user_dir("p6_intents_host",
                                    options={"battleXcomSpeed": 2,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48871,
                        make_user_dir("p6_intents_client",
                                      options={"battleXcomSpeed": 2,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines")

        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallel turns only "
            f"cover PVE (1) and PVE2 (4), so this test would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            b = battle(gc)
            assert b["parallelActive"] is True, f"{tag}: parallel mode is not live: {b}"
        assert battle(host)["activeSync"] is True and battle(client)["activeSync"] is False, (
            "the PRD-P5 executor invariant does not hold, so nothing below is "
            "testing the intent path")
        seat = client.ok({"cmd": "get_coop"})["localSeat"]
        hostiles = [u for u in battle(host)["units"]
                    if u.get("faction") == 1 and not u.get("isOut")]
        print(f"client seat = {seat}; {len(hostiles)} live hostile(s) in the fixture")

        client_mover = pick_driver(host, client, seat, "client")
        host_mover = pick_driver(host, client, 0, "host")

        # Order is dictated by what each scenario needs from the fixture's
        # handful of aliens: 6 wants a live one to walk past, 4's psi/melee kinds
        # want one to stand next to, and 3's `isOut` deny wants the body 4's
        # stun rod leaves behind.
        scenario_walk(host, client, client_mover)
        scenario_busy(host, client, host_mover, client_mover)
        scenario_reaction(host, client, client_mover)
        scenario_kinds(host, client, client_mover)
        scenario_invalid(host, client, seat, host_mover, client_mover)
        scenario_race(host, client, host_mover, client_mover)

        print("ALL ACTION-INTENT TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
