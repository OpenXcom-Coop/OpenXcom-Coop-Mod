"""PRD-P7: walk fast-forward + pending-admit.

PRD-P6 made the two players act into one arbiter, but every contention answer was
"no": an input that arrived while ANY chain was running was refused `busy` and the
player had to click again. Most of what a chain is, though, is a walk animation
nobody is waiting for. P7 splits contention in two:

    chain is pure locomotion  ->  DEFER the input (one pending slot per seat),
                                  arm the fast-forward, admit + ack on drain
    anything else             ->  PRD-P6's `busy` refusal, unchanged

`BattlescapeGame::chainIsSkippable()` is the classifier: every queued state must
be a UnitWalk/UnitTurn/UnitFallBState of a FACTION_PLAYER unit. A shot, an
explosion, a death, a melee or psi state, the end-turn sentinel, or an AI actor
all make it false - so the moment reaction fire pushes a ProjectileFlyBState into
a fast-forwarded walk, the skip lapses and the deferred inputs are refused.

What this test asserts (PRD-P7 acceptance, in order):

  1. Contention on a WALK: the host is walking, the client's intent arrives - no
     deny, the host's walk finishes fast (`parallel_state.fastForward`, with a
     wall-clock bound as the backstop), the client's action runs next, and both
     machines end on identical positions and TU.
  2. Contention on a SHOT: never skipped. `chainSkippable` is false, the client's
     intent is refused `busy`, nothing is deferred and nothing executes.
  3. Reaction fire cancels the skip: a shot state joining a fast-forwarded walk
     clears the fast-forward and refuses the pending input. Driven with
     `battle_fire`, which pushes exactly what TileEngine::checkReactionFire pushes
     (`statePushBack(new ProjectileFlyBState)`, TileEngine.cpp:2949) - the
     aliens' own reaction roll is theirs to make and cannot be scripted.
  4. A fast-forwarded walk over a PRIMED PROXIMITY GRENADE resolves identically on
     both machines - the interval-0 seam must not change what the sweep
     (PRD-P3's host-decided `checkForProximityGrenades`) does.
  5. RIDER (PRD-P6 finding): `active_grenade`'s receive read the fuse into a
     `bool` before handing it to an `int` parameter, so every fuse > 1 arrived as
     1 and the -1 an unprime ships arrived as 1 as well - the peer armed a grenade
     the executor had just disarmed. Primed fuses must now match on both machines.

TIMING NOTE. Scenarios 1, 3 and 4 all need the host to still be walking when the
client's intent reaches the arbiter. That window is the walk animation, and the
fixture roll decides how long it is - a two-tile shuffle is over inside the
intent's own round trip. It is therefore MEASURED (an uncontended run of the very
same walk) and escalated - speed and path length together - until it clears a
floor; see THE DEFER WINDOW below. Nothing about the window is asserted as a
product property: the assertions are the deferral, the fast-forward, the
admission after the drain and the two machines agreeing.

Run:  python tools/coop_test/test_parallel_skip.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI

PORT = "47987"

BUSY_TEXT = "Another action"

# The host walks at this while the skip is being exercised. It only bites while
# the walker is ON SCREEN - UnitWalkBState already runs an off-screen walk at
# interval 0 - so every scenario below points the host's camera at its walker
# first, and the timing assertion is made against a measured baseline rather than
# a magic constant.
SLOW_WALK_MS = 200

# THE DEFER WINDOW. Scenarios 1 and 3 are about what happens to an input that
# arrives WHILE a walk chain is draining, so the client's `action_intent` has to
# reach the arbiter before the host's walk is over. That window used to be
# whatever the fixture roll handed out: a driver whose only path is a two-tile
# shuffle walks for about a second, which is inside the intent's own round trip -
# the chain drains first, there is nothing to defer, the intent resolves against
# an idle arbiter and the scenario fails on an assertion that never had a chance.
# (Rolls that produced 15-18 s baselines passed every time, same binary, same
# test - the flake was the fixture, not the product.)
#
# So the window is MEASURED, not hoped for: scenario 1 times an UNCONTENDED run
# of the very same walk and re-rolls it until the walk is big enough, on both of
# the axes that matter. They are NOT interchangeable:
#
#   TILES TRAVELLED is the dominant one. The fast-forward pins the walk interval
#     to 0, so what is left of the chain after the client's intent lands is drawn
#     as fast as the game loop can draw it - a handful of milliseconds per tile.
#     One tile left over means `fastForward`/`pendingAdmits` are true for ~50 ms,
#     which no poll over a socket is going to see; six tiles left over is a window
#     of seconds. A destination probe_step vouched for is NOT a distance walked:
#     the pathfinder re-plans at execution and the walk aborts on a fresh sighting,
#     so the traversal is measured after the fact (WALK_MIN_TILES).
#   WALL-CLOCK DURATION only decides whether the intent gets there before the
#     chain ends at all, and the frame delay is what buys it. It is the second
#     dial because slowing the animation makes every later walk in the run longer.
#
# Hence two escalation dials, cheapest first: WIDEN re-rolls a longer path (one
# probe RPC), SLOW doubles the frame delay. The pair that worked is remembered in
# WALK_SLOW/WALK_WIDE, so scenarios 3 and 4 arm at it instead of re-discovering it.
WALK_RADIUS = 6         # probe_step radius for the first roll
WALK_WIDEN = 3          # tiles added to that radius per re-roll
WALK_WIDE_MAX = 2       # radius 6 -> 9 -> 12
WALK_SLOW_MAX = 2       # 200 -> 400 -> 800 ms/frame
WALK_MIN_TILES = 4      # tiles the baseline must actually cover
WALK_FLOOR_S = 4.0
WALK_ATTEMPTS = 10
WALK_SLOW = 0
WALK_WIDE = 0

# Host drivers that will not walk anywhere any more - knocked out, or stuck in a
# spot the pathfinder keeps approving and the walk keeps declining.
SPENT = set()


def battle(gc):
    return PI.battle(gc)


def parallel(gc):
    return PI.parallel(gc)


def pos(b, uid):
    return PI.pos(b, uid)


def tu(b, uid):
    return PI.tu(b, uid)


def unit(b, uid):
    return PI.unit(b, uid)


def items(gc):
    return gc.ok({"cmd": "battle_items"})


def fuse_of(gc, item_id):
    for it in items(gc)["items"]:
        if it["id"] == item_id:
            return it["fuse"]
    return None


def poll(fn, timeout, interval=0.03):
    """Tight poll - the fast-forwarded window is short by construction."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(interval)
    return None


def speed(gc, ms):
    gc.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": ms})


def look_at(gc, uid):
    """Put `uid` in view. Without this the walk runs at interval 0 anyway (the
    pre-existing off-screen seam) and 'it finished fast' proves nothing."""
    return gc.ok({"cmd": "battle_camera", "unit": uid}).get("onScreen")


def walk_ms(slow):
    return SLOW_WALK_MS * (2 ** slow)


def arm_walk(host, uid, slow=None, wide=None):
    """Open the defer window and hand back the destination that fills it.

    Defaults to the (slow, wide) pair scenario 1 measured for this fixture, so a
    later scenario arming the same way gets the same window for free."""
    slow = WALK_SLOW if slow is None else slow
    wide = WALK_WIDE if wide is None else wide
    speed(host, walk_ms(slow))
    assert look_at(host, uid), (
        f"the host's camera would not frame unit {uid}; an off-screen walk runs "
        f"at interval 0 regardless and the timing below would be meaningless")
    return long_walk_target(host, uid, radius=WALK_RADIUS + WALK_WIDEN * wide)


def clear_deny(gc):
    """Reset the client's last-deny latch. It is the only NON-transient readout
    of a refusal (the warning widget fades in 3 s), so a retry has to start it
    empty or it reports the previous attempt's answer."""
    gc.cmd({"cmd": "parallel_state", "clear_deny": True})


def tiles(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) if a and b else 0


def top_up(host, client, uid, tu=200, energy=200):
    """Same TU **and ENERGY** on both machines.

    `PI.top_up` restores TU only, and energy is what actually runs out first: a
    soldier with 200 TU and no energy refuses to move at all. Every scenario here
    drives the SAME soldier through several deliberately long walks in a row, so
    by the third one the walk covers no ground - it is admitted, drains in about a
    second and nothing happens. That is the "1 s baseline" this file's defer
    window kept losing to, and it is a fixture accident all the way down; the
    `energy` field exists on `battle_intent` for exactly this (TestServer.cpp,
    PRD-P9), and test_parallel_soak.py hit it first."""
    for gc in (host, client):
        gc.ok({"cmd": "battle_intent", "unit": uid, "action": "turn",
               "tu": tu, "energy": energy, "dry": True})


def armed_now(host):
    """Fast-forward armed AND something deferred behind it, read from ONE query -
    two `parallel()` calls would be two round trips straddling the transition."""
    ps = parallel(host)
    return ps.get("fastForward") is True and bool(ps.get("pendingAdmits"))


def watch_defer(host, seq_before, timeout, grace=1.5):
    """Sample the whole deferral in one poll loop: was the fast-forward armed, was
    anything deferred, and did action_seq reach the +2 that IS the drain.

    One loop rather than three, because the first two are transient by design -
    an 8 s poll for `fastForward` is 8 s during which `pendingAdmits` comes and
    goes unseen, and both are gone by the time a third poll starts.

    It also gives up early on the answer that never arrives. A deferred intent can
    be REFUSED instead of admitted (reaction fire joins the chain, the skip lapses,
    PRD-P7 denies the pending slot - scenario 3's subject, and the aliens may
    choose it here too), and then +2 never comes: once the host is idle with its
    own walk counted and nothing deferred, waiting out the timeout learns nothing.
    `grace` covers the ordinary case of an intent still in flight at that moment.
    Returns (ff, pend, admitted)."""
    ff = pend = False
    idle_since = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        ps = parallel(host)
        ff = ff or ps.get("fastForward") is True
        pend = pend or bool(ps.get("pendingAdmits"))
        seq = ps.get("actionSeq", 0)
        if seq >= seq_before + 2:
            return ff, pend, True
        if (ps.get("canAdmit") is True and not ps.get("pendingAdmits")
                and seq == seq_before + 1):
            idle_since = idle_since or time.time()
            if time.time() - idle_since >= grace:
                break
        else:
            idle_since = None
        time.sleep(0.02)
    return ff, pend, False


def idle(gc, timeout=240):
    # Generous on purpose: the walks here are deliberately slowed (see THE DEFER
    # WINDOW), and an interrupted one loses its fast-forward and finishes drawing
    # every remaining tile at the slowed frame rate.
    return PI.wait_until(
        lambda: parallel(gc).get("canAdmit") is True
        and not parallel(gc).get("pendingAdmits"), timeout)


def quiet(host, client, what):
    PI.settle(host, client)
    session.assert_battle_synced(host, client, what)
    assert not TW.desync_seen(host) and not TW.desync_seen(client), \
        f"the PRD-P2 drift tripwire fired {what}"


def fresh_driver(host, client, seat=0):
    """A DIFFERENT soldier of `seat`, placed where it can act.

    `PI.pick_driver` always hands back the first candidate that can be placed,
    which is the one we are trying to get away from - hence SPENT."""
    enemy = PI.alive_enemy(battle(host))
    if not enemy:
        return None
    epos = (enemy["x"], enemy["y"], enemy["z"])
    for cand in PI.own_units(battle(client), seat):
        if cand["id"] in SPENT:
            continue
        spot = PI.place_near(host, client, cand["id"], epos)
        if spot:
            top_up(host, client, cand["id"])
            print(f"    (host driver switched to unit {cand['id']} at {spot})")
            return cand["id"]
    return None


def live_driver(host, client, uid, seat=0):
    """`uid` if it is still on its feet, otherwise a replacement.

    The host's walker is marched past hostiles over and over and (scenario 4)
    straight over a primed grenade, so it gets knocked out - `status` 6,
    UNCONSCIOUS - fairly often. A casualty does not walk, and no re-roll, no
    wider radius and no teleport changes that: every scenario after the one that
    dropped it would otherwise fail on a walk that never starts, reported as a
    fast-forward that never fired."""
    u = unit(battle(host), uid)
    if u and not u.get("isOut"):
        return uid
    SPENT.add(uid)
    nxt = fresh_driver(host, client, seat)
    assert nxt, (
        f"host driver {uid} is out of the fight and no other host soldier could "
        f"be placed where it can act either")
    return nxt


def nearest_enemy(b, here):
    live = [u for u in b.get("units", [])
            if u.get("faction") == 1 and not u.get("isOut")
            and u.get("health", 0) > 0]
    return min(live, key=lambda u: tiles(here, (u["x"], u["y"]))) if live else None


def long_walk_target(gc, uid, radius=WALK_RADIUS):
    """The furthest tile `uid` can reach, preferring one that walks AWAY from the
    nearest hostile.

    Distance is what makes the walk long enough to defer an intent behind; the
    DIRECTION is what keeps that deferral alive. A walk that closes on an alien
    draws reaction fire, reaction fire pushes a ProjectileFlyBState into the
    chain, and a chain carrying a shot is not skippable - so PRD-P7 correctly
    cancels the fast-forward and refuses the pending intent. That is scenario 3's
    subject, and in scenario 1 it is just a wasted roll (four in a row, once).
    The aliens' reaction roll is theirs to make, but which way we walk is ours."""
    b = battle(gc)
    here = pos(b, uid)
    cands = PI.steps_of(gc, uid, radius)
    if not cands:
        return PI.free_step(gc, uid)
    far = [t for t in cands if tiles(here, t) >= WALK_MIN_TILES]
    enemy = nearest_enemy(b, here)
    if not far:
        return max(cands, key=lambda t: tiles(here, t))
    if not enemy:
        return max(far, key=lambda t: tiles(here, t))
    epos = (enemy["x"], enemy["y"])
    return max(far, key=lambda t: (tiles(epos, t), tiles(here, t)))


def timed_walk(host, uid, dest, seq_before, timeout=150):
    """Drive one host walk and return how long the chain took to drain. The clock
    stops when action_seq has moved and the arbiter will take another action,
    which is the drain point - not when the harness next happens to poll."""
    started = time.time()
    r = PI.intent(host, action="move", unit=uid,
                  x=dest[0], y=dest[1], z=dest[2])
    assert r.get("ok"), f"the walk lever refused: {r}"
    assert r.get("routed") is False, (
        f"the host's own walk was not admitted ({r}); parallel_state="
        f"{parallel(host)}")
    done = poll(lambda: parallel(host).get("actionSeq", 0) > seq_before
                and parallel(host).get("canAdmit") is True, timeout, 0.1)
    assert done, (
        f"the host walk of unit {uid} to {dest} never drained: "
        f"{parallel(host)} at {pos(battle(host), uid)}")
    return time.time() - started


# ---- 1. contention on a walk: deferred, skipped, both machines agree ---------

def scenario_walk_skip(host, client, host_mover, client_mover):
    global WALK_SLOW, WALK_WIDE
    print("-- 1: client input during a host WALK -> deferred + fast-forwarded --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    top_up(host, client, host_mover)
    top_up(host, client, client_mover)

    # Baseline: the SAME walk, uncontended. Self-calibrating - the animation cost
    # depends on the armor's phase count and on how many tiles the pathfinder
    # found, neither of which a constant in this file can know - and escalating,
    # because a walk that is over in a second leaves the client's intent nothing
    # to arrive behind (see THE DEFER WINDOW at the top of this file).
    baseline = 0.0
    h_origin = h_landed = host_dest = None
    covered = zeros = stuck = 0
    for attempt in range(WALK_ATTEMPTS):
        nxt = live_driver(host, client, host_mover)
        if nxt != host_mover:
            host_mover, stuck, zeros = nxt, 0, 0
        top_up(host, client, host_mover)
        h_origin = pos(battle(host), host_mover)
        host_dest = arm_walk(host, host_mover, WALK_SLOW, WALK_WIDE)
        assert host_dest, f"host soldier {host_mover} cannot step anywhere"
        baseline = timed_walk(host, host_mover, host_dest,
                              parallel(host)["actionSeq"],
                              timeout=150 + 150 * WALK_SLOW)
        PI.settle(host, client, seconds=3)
        h_landed = pos(battle(host), host_mover)
        covered = tiles(h_origin, h_landed)
        print(f"    baseline {attempt}: an unskipped {h_origin} -> {host_dest} "
              f"walk at {walk_ms(WALK_SLOW)} ms/frame (radius "
              f"{WALK_RADIUS + WALK_WIDEN * WALK_WIDE}) covered {covered} tile(s) "
              f"to {h_landed} in {baseline:.1f}s (unit {host_mover} status "
              f"{(unit(battle(host), host_mover) or {}).get('status')})")
        if covered >= WALK_MIN_TILES and baseline >= WALK_FLOOR_S:
            break
        zeros = zeros + 1 if covered == 0 else 0
        if zeros >= 2:
            # Not merely short of options - STUCK. probe_step keeps vouching for
            # a destination the walk then declines to start on (it re-plans at
            # execution, and `getStartDirection() != -1` is not the same question
            # as `getTUCost() != INVALID_MOVE_COST`), and from the same tile every
            # further roll returns the same answer, so widening is just a slower
            # way to fail. Two escapes, in order: put the driver back on open
            # ground (PRD-P9's rider R6 answer to a boxed-in unit), and, if it
            # STILL will not walk - the condition follows the unit, not the tile -
            # drive a different soldier for the rest of the test.
            # WALK_WIDE is deliberately NOT reset: how far a driver has to
            # aim to find a real walk is a property of the map, not of the
            # soldier, so the dial only ever ratchets up.
            stuck += 1
            zeros = 0
            if stuck == 1:
                enemy = PI.alive_enemy(battle(host))
                spot = PI.place_near(host, client, host_mover,
                                     (enemy["x"], enemy["y"], enemy["z"])) \
                    if enemy else None
                print(f"    (unit {host_mover} would not leave {h_landed}; "
                      f"re-placed at {spot})")
            else:
                SPENT.add(host_mover)
                nxt = fresh_driver(host, client)
                assert nxt, (
                    f"unit {host_mover} has stopped walking and no other host "
                    f"soldier could be placed where it can act either - the "
                    f"fixture has no driver left to time a walk with")
                host_mover, stuck = nxt, 0
            continue
        # Widen first (one probe RPC); spend the frame delay only when the walk
        # DID cover the ground and was merely quick. See THE DEFER WINDOW above.
        if covered < WALK_MIN_TILES:
            WALK_WIDE = min(WALK_WIDE + 1, WALK_WIDE_MAX)
        else:
            WALK_SLOW = min(WALK_SLOW + 1, WALK_SLOW_MAX)
    assert covered >= WALK_MIN_TILES and baseline >= WALK_FLOOR_S, (
        f"in {WALK_ATTEMPTS} rolls no walk unit {host_mover} can make covers "
        f"{WALK_MIN_TILES} tiles and lasts {WALK_FLOOR_S}s (best {covered} "
        f"tile(s) in {baseline:.1f}s, at up to {walk_ms(WALK_SLOW_MAX)} ms/frame "
        f"out to radius {WALK_RADIUS + WALK_WIDEN * WALK_WIDE_MAX}). A chain that "
        f"short leaves nothing to fast-forward once the client's intent lands, so "
        f"the deferral below would be a coin flip rather than a test")

    ff = pend = None
    elapsed = 0.0
    h_from = c_from = None
    for attempt in range(5):
        assert idle(host), f"the host is still busy: {parallel(host)}"
        host_mover = live_driver(host, client, host_mover)
        top_up(host, client, host_mover)
        top_up(host, client, client_mover)
        # The client's destination is resolved while everything is idle:
        # probe_step refuses mid-chain (Pathfinding is a singleton the running
        # walk dequeues from). Re-resolved per attempt, because a retry means
        # the client's soldier may have moved after all.
        client_dest = PI.free_step_both(host, client, client_mover)
        assert client_dest, f"client soldier {client_mover} cannot step anywhere"
        speed(host, walk_ms(WALK_SLOW))
        assert look_at(host, host_mover), "the host's camera lost the walker"
        # The RETURN LEG of the walk just timed: the same tiles in the opposite
        # order, so the window that was measured IS the window the client's
        # intent lands in. A fresh `long_walk_target` roll would be of unknown
        # length again, which is the whole bug.
        dest = h_origin if attempt == 0 else arm_walk(host, host_mover)
        assert dest, f"host soldier {host_mover} cannot step again"
        h_from = pos(battle(host), host_mover)
        c_from = pos(battle(host), client_mover)
        seq_before = parallel(host)["actionSeq"]
        clear_deny(client)

        started = time.time()
        r = PI.intent(host, action="move", unit=host_mover,
                      x=dest[0], y=dest[1], z=dest[2])
        if not r.get("ok") and attempt == 0:
            print(f"    (something moved onto the return leg: {r}; rolling a "
                  f"fresh path of the same length instead)")
            continue
        assert r.get("ok"), f"the walk lever refused: {r}"
        assert r.get("routed") is False, (
            f"the host's own walk was not admitted ({r}); parallel_state="
            f"{parallel(host)}")
        # Synchronous on the host, so the walk is queued the instant the RPC
        # returns - and chainIsSkippable() is FALSE on an empty state list
        # (BattlescapeGame.cpp:2210), so this doubles as proof that a chain is
        # actually running right now.
        ps = parallel(host)
        assert ps.get("chainSkippable") is True, (
            f"a plain player walk did not classify as skippable ({ps}) - nothing "
            f"below is testing the skip")

        rc = PI.intent(client, action="move", unit=client_mover,
                       x=client_dest[0], y=client_dest[1], z=client_dest[2])
        assert rc.get("routed") is True, f"the client executed locally: {rc}"

        # The deferred intent is admitted at the drain, so action_seq +2 IS the
        # drain - but +2 ALONE is not proof of a deferral: an intent that arrives
        # after the walk ended is admitted straight away and reaches the same
        # count. `ff`/`pend` are what tell the two apart, so all three come out
        # of the same poll and all three have to hold.
        ff, pend, admitted = watch_defer(host, seq_before, 150)
        elapsed = time.time() - started
        if admitted and (ff or pend):
            # ...and BOTH walks have to have gone somewhere, which is a separate
            # question from whether they were admitted. Every destination here
            # has to be resolved before the host's walk starts (probe_step
            # refuses mid-chain), so each is a tile chosen against a board that
            # has since moved: the pathfinder re-plans at execution and can
            # decline to start, and the host's own walker spends the whole window
            # crossing tiles. Either walk can then be admitted, execute, and
            # cover no ground - a fixture accident, not a PRD-P7 answer, so roll
            # the whole contention again rather than assert on it.
            h_walked = tiles(h_from, pos(battle(host), host_mover))
            c_moved = bool(h_walked) and PI.wait_until(
                lambda: pos(battle(host), client_mover) != c_from, 45)
            if h_walked and c_moved:
                break
            print(f"    (a deferral happened but a walk went nowhere: the host "
                  f"covered {h_walked} tile(s) from {h_from}, the client "
                  f"{'moved' if c_moved else 'did not move'} from {c_from} "
                  f"towards {client_dest}; rolling again)")
            idle(host)
            PI.settle(host, client, seconds=3)
            continue

        # Two different misses, and only one of them is about the window.
        assert parallel(host).get("actionSeq", 0) > seq_before, (
            f"the host's OWN walk was never admitted, so the arbiter - not the "
            f"timing - is what went wrong: host={parallel(host)} "
            f"client={parallel(client)}")
        PI.wait_until(lambda: parallel(client)["pendingReqId"] == 0, 20)
        walked = tiles(h_from, pos(battle(host), host_mover))
        deny = parallel(client).get("lastDenyReason") or ""
        if ff or pend:
            # The intent WAS deferred and then refused: something non-skippable
            # joined the chain, which is PRD-P7 behaving exactly as specified
            # (scenario 3 drives that case on purpose - here it is the aliens'
            # own reaction roll, and it is theirs to make). Nothing to escalate;
            # roll the walk again.
            print(f"    (the deferral was cancelled {walked} tile(s) in - "
                  f"deny={deny!r}; something joined the chain, rolling again)")
        else:
            # Nothing was ever deferred: this one IS the window. Same two dials
            # as the baseline, cheapest first.
            if walked < WALK_MIN_TILES:
                WALK_WIDE = min(WALK_WIDE + 1, WALK_WIDE_MAX)
            else:
                WALK_SLOW = min(WALK_SLOW + 1, WALK_SLOW_MAX)
            print(f"    (a {walked}-tile contended walk closed before the "
                  f"client's intent was deferred - admitted={admitted} "
                  f"deny={deny!r}; re-arming at {walk_ms(WALK_SLOW)} ms/frame, "
                  f"radius {WALK_RADIUS + WALK_WIDEN * WALK_WIDE})")
        idle(host)
        PI.settle(host, client, seconds=3)
    else:
        raise AssertionError(
            f"in 5 attempts the client's intent was never both DEFERRED behind "
            f"the host's walk and then admitted into a walk that moved: "
            f"host={parallel(host)} client={parallel(client)} "
            f"warning={PI.warning_of(client)!r}")

    speed(host, 2)
    assert idle(host), f"the host never went idle: {parallel(host)}"
    PI.settle(host, client, seconds=6)

    seen = PI.warning_of(client)
    assert BUSY_TEXT.lower() not in (seen or "").lower(), (
        f"the client was refused {seen!r} - PRD-P7 must DEFER an input that "
        f"arrives behind a chain of pure locomotion, not refuse it")
    # The widget text fades after 3 s and this read can land late; the deny latch
    # does not fade and was cleared immediately before the intent went out, so it
    # is the assertion that actually holds the line.
    assert parallel(client).get("lastDenyReason") != "busy", (
        f"the client's intent was latched as refused busy "
        f"({parallel(client).get('lastDenyWarning')!r}) even though it ran - "
        f"PRD-P7 must DEFER an input that arrives behind pure locomotion")
    assert pend or ff, (
        f"neither a pending slot nor the fast-forward was ever visible on the "
        f"host, so the deferral cannot be told apart from a lucky race: "
        f"{parallel(host)}")
    assert ff or elapsed < baseline * 0.6, (
        f"the contended walk took {elapsed:.1f}s against an uncontended "
        f"baseline of {baseline:.1f}s and the fast-forward was never "
        f"observed - the interval-0 seam is not firing")

    hb, cb = battle(host), battle(client)
    for uid, start in ((host_mover, h_from), (client_mover, c_from)):
        assert pos(hb, uid) == pos(cb, uid), (
            f"unit {uid} ended at {pos(hb, uid)} on the host and {pos(cb, uid)} "
            f"on the client - the fast-forward changed the OUTCOME, not just how "
            f"long it took to draw")
        assert tu(hb, uid) == tu(cb, uid), (
            f"unit {uid} was charged {tu(hb, uid)} TU on the host and "
            f"{tu(cb, uid)} on the client")
        assert pos(hb, uid) != start, f"unit {uid} never moved at all"
    quiet(host, client, "after the fast-forwarded walk contention")
    print(f"PASS 1: host walk {h_from} -> {pos(hb, host_mover)} fast-forwarded "
          f"(fastForward seen={bool(ff)}, pending seen={bool(pend)}, "
          f"{elapsed:.1f}s vs a {baseline:.1f}s baseline), the deferred client "
          f"walk ran next, both machines identical")
    # The walker may have been swapped out along the way; the later scenarios arm
    # the same way and want the driver that is known to still walk.
    return host_mover


# ---- 2. contention on a shot: never skipped ---------------------------------

def scenario_shot_never_skipped(host, client, host_mover, client_mover):
    print("-- 2: client input during a host SHOT -> refused busy, no skip --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    host_mover = live_driver(host, client, host_mover)
    top_up(host, client, host_mover)
    top_up(host, client, client_mover)
    client_dest = PI.free_step_both(host, client, client_mover)
    assert client_dest, f"client soldier {client_mover} cannot step anywhere"
    wid = PI.give_both(host, client, host_mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    speed(host, 200)
    aim, ps = PI.start_busy_shot(host, client, host_mover, wid)
    if not aim:
        speed(host, 2)
    assert aim, (
        f"no aim point produced a shot chain that outlived the RPC, so the deny "
        f"path cannot be exercised: {ps}")
    assert ps.get("chainSkippable") is False, (
        f"a chain carrying a ProjectileFlyBState classified as SKIPPABLE: {ps}")
    assert ps.get("fastForward") is False, (
        f"the fast-forward was armed for a shot chain: {ps}")

    c_before = pos(battle(host), client_mover)
    clear_deny(client)
    r = PI.intent(client, action="move", unit=client_mover,
                  x=client_dest[0], y=client_dest[1], z=client_dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    # The flash is the UX and the latch is the record. This deny is sent the
    # moment the intent is received (unlike scenario 3's, which waits for the
    # interruption), so the widget read is normally the one that answers - but
    # the same 3 s fade applies, so accept either.
    seen = PI.wait_for_text(client, BUSY_TEXT, timeout=25)
    latched = poll(lambda: parallel(client).get("lastDenyReason") == "busy", 10)
    speed(host, 2)
    assert seen or latched, (
        f"no STR_COOP_PLAYER_BUSY flash after an intent sent into a running SHOT "
        f"(widget shows {PI.warning_of(client)!r}, lastDenyReason="
        f"{parallel(client).get('lastDenyReason')!r}). A shot is exactly the "
        f"chain PRD-P7 must keep refusing.")
    assert not parallel(host).get("pendingAdmits"), (
        f"the intent was DEFERRED behind a shot: {parallel(host)}")
    assert pos(battle(host), client_mover) == c_before, (
        f"a refused intent still moved unit {client_mover} "
        f"({c_before} -> {pos(battle(host), client_mover)})")
    assert PI.wait_until(lambda: parallel(client)["pendingReqId"] == 0, 15), \
        "the deny did not clear the client's pending slot"
    assert idle(host), f"the shot chain never ended: {parallel(host)}"
    quiet(host, client, "after the refused shot contention")
    print(f"PASS 2: the shot was never skipped and the client was refused "
          f"{seen if seen else parallel(client).get('lastDenyWarning')!r}")
    return host_mover


# ---- 3. reaction fire cancels the skip --------------------------------------

def scenario_reaction_cancels(host, client, host_mover, client_mover):
    print("-- 3: a shot joining a fast-forwarded walk cancels it --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    host_mover = live_driver(host, client, host_mover)
    top_up(host, client, host_mover)
    top_up(host, client, client_mover)
    wid = PI.give_both(host, client, host_mover, "STR_RIFLE", "STR_RIFLE_CLIP")

    # This scenario arms exactly the way scenario 1 does, so it carries the same
    # short-roll hazard - and one more of its own. There are TWO windows to hit
    # here, and the second is the tight one:
    #
    #   (a) the client's intent has to land while the walk is still running, same
    #       as scenario 1 -> same answer, arm at the (slow, wide) pair scenario 1
    #       measured, escalate on a miss.
    #   (b) the interruption has to land while that deferred intent is STILL
    #       pending. Arming the fast-forward pins the walk to interval 0, so the
    #       whole remaining chain drains in well under a second and the pending
    #       intent is then ADMITTED rather than cancelled - there is nothing left
    #       to interrupt and no deny is owed to anyone. The aim point is therefore
    #       resolved BEFORE the walk starts (a `battle_state` dump between the
    #       fast-forward and the shot is by itself enough to miss the window), and
    #       a miss re-arms instead of asserting.
    armed = c_before = seen = deny_latched = None
    for attempt in range(3):
        assert idle(host), f"the host is still busy: {parallel(host)}"
        top_up(host, client, host_mover)
        top_up(host, client, client_mover)
        client_dest = PI.free_step_both(host, client, client_mover)
        assert client_dest, f"client soldier {client_mover} cannot step anywhere"
        slow = min(WALK_SLOW + attempt, WALK_SLOW_MAX)
        wide = min(WALK_WIDE + attempt, WALK_WIDE_MAX)
        host_dest = arm_walk(host, host_mover, slow, wide)
        assert host_dest, f"host soldier {host_mover} cannot step anywhere"
        aim = PI.aim_away(host, host_mover)

        c_before = pos(battle(host), client_mover)
        clear_deny(client)
        assert PI.intent(host, action="move", unit=host_mover,
                         x=host_dest[0], y=host_dest[1], z=host_dest[2]).get("ok")
        r = PI.intent(client, action="move", unit=client_mover,
                      x=client_dest[0], y=client_dest[1], z=client_dest[2])
        assert r.get("routed") is True, f"the client executed locally: {r}"
        armed = poll(lambda: armed_now(host), 12, 0.02)
        if not armed:
            print(f"    (the {walk_ms(slow)} ms/frame walk drained before the "
                  f"intent landed; re-arming wider and slower)")
            PI.wait_until(lambda: parallel(client)["pendingReqId"] == 0, 20)
            idle(host, timeout=240)
            PI.settle(host, client, seconds=3)
            continue

        # The interruption, issued the instant the arming is seen and in ONE RPC.
        # `battle_fire` statePushBack()s a ProjectileFlyBState onto the running
        # chain - the same push TileEngine::checkReactionFire makes.
        host.cmd({"cmd": "battle_fire", "unit": host_mover, "mode": "snap",
                  "weapon_id": wid, "tu": 200,
                  "x": aim[0], "y": aim[1], "z": aim[2]})

        assert parallel(host).get("fastForward") is False, (
            f"the fast-forward survived a shot state joining the chain: "
            f"{parallel(host)}")
        assert not parallel(host).get("pendingAdmits"), (
            f"the pending input survived the interruption: {parallel(host)}")
        # The flash lives 3 s and this poll can start late, so the transient
        # widget text is corroborating evidence, not the arbiter. The deny's
        # arrival is latched in parallel_state.lastDenyReason (PRD-P8); a
        # genuinely dropped deny leaves the latch empty and the pending slot set
        # until the client's 10 s watchdog fires a TIMEOUT instead - which the
        # pending-slot assert below still catches.
        seen = PI.wait_for_text(client, BUSY_TEXT, timeout=15)
        deny_latched = poll(
            lambda: (parallel(client).get("lastDenyReason") == "busy"
                     and parallel(client)["pendingReqId"] == 0), 15)
        if seen or deny_latched:
            break
        # Nobody was refused because nobody was still pending: the interval-0
        # drain beat the shot to it and the deferred intent was admitted. Window
        # (b) missed - not a product answer, so re-arm rather than assert.
        assert pos(battle(host), client_mover) != c_before, (
            f"the pending intent was neither denied NOR executed - it was "
            f"silently dropped: host={parallel(host)} client={parallel(client)}")
        print(f"    (the fast-forward drained the walk before the shot could "
              f"join it, so the deferred intent was admitted instead of "
              f"cancelled; re-arming)")
        idle(host, timeout=240)
        PI.settle(host, client, seconds=3)
    speed(host, 2)
    assert armed, (
        f"the walk was never fast-forwarded with a pending input, in 3 attempts, "
        f"so there is nothing for the interruption to cancel: {parallel(host)}")
    assert seen or deny_latched, (
        f"the interrupted pending intent was dropped without telling the client "
        f"(widget shows {PI.warning_of(client)!r}, "
        f"lastDenyReason={parallel(client).get('lastDenyReason')!r}) - the "
        f"player would wait for an action that is never coming")
    assert PI.wait_until(lambda: parallel(client)["pendingReqId"] == 0, 15), \
        "the deny did not clear the client's pending slot"
    assert pos(battle(host), client_mover) == c_before, (
        f"the DENIED pending intent executed anyway: unit {client_mover} "
        f"{c_before} -> {pos(battle(host), client_mover)}")

    assert idle(host), f"the interrupted chain never ended: {parallel(host)}"
    quiet(host, client, "after the interrupted fast-forward")
    hb, cb = battle(host), battle(client)
    assert pos(hb, host_mover) == pos(cb, host_mover), (
        f"the interrupted walk diverged: host {pos(hb, host_mover)} client "
        f"{pos(cb, host_mover)}")
    print(f"PASS 3: the shot cancelled the skip, the pending input was refused "
          f"{seen if seen else parallel(client).get('lastDenyWarning')!r}, and "
          f"the census stayed symmetric")
    return host_mover


# ---- 4. fast-forwarded walk over a primed proximity grenade ------------------

def scenario_proximity(host, client, host_mover, client_mover):
    print("-- 4: a fast-forwarded walk over a PRIMED proximity grenade --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    host_mover = live_driver(host, client, host_mover)
    top_up(host, client, host_mover)
    top_up(host, client, client_mover)
    client_dest = PI.free_step_both(host, client, client_mover)
    assert client_dest, f"client soldier {client_mover} cannot step anywhere"
    # Same arming as 1 and 3. Nothing here ASSERTS on the fast-forward - the
    # subject is the sweep's outcome, not the skip - but a walk that is over
    # before the client's intent lands never enters the interval-0 seam at all,
    # which is the seam this scenario exists to walk a primed grenade through.
    host_dest = arm_walk(host, host_mover)
    assert host_dest, f"host soldier {host_mover} cannot step anywhere"

    # An armed proximity grenade on the destination tile, minted identically on
    # both machines (the ids must match or the sweep's removal list resolves to
    # nothing on the peer).
    drop = [host.ok({"cmd": "battle_give", "unit": host_mover,
                     "item": "STR_PROXIMITY_GRENADE", "slot": "ground", "fuse": 0,
                     "x": host_dest[0], "y": host_dest[1], "z": host_dest[2]}),
            client.ok({"cmd": "battle_give", "unit": host_mover,
                       "item": "STR_PROXIMITY_GRENADE", "slot": "ground", "fuse": 0,
                       "x": host_dest[0], "y": host_dest[1], "z": host_dest[2]})]
    assert drop[0]["weaponId"] == drop[1]["weaponId"], (
        f"the two machines minted different ids for the proximity grenade "
        f"({drop[0]['weaponId']} vs {drop[1]['weaponId']})")
    grenade = drop[0]["weaponId"]
    time.sleep(2)
    assert fuse_of(host, grenade) == fuse_of(client, grenade) == 0, (
        f"the planted fuse does not match: host {fuse_of(host, grenade)} client "
        f"{fuse_of(client, grenade)}")

    h_hp = unit(battle(host), host_mover)["health"]
    assert PI.intent(host, action="move", unit=host_mover,
                     x=host_dest[0], y=host_dest[1], z=host_dest[2]).get("ok")
    PI.intent(client, action="move", unit=client_mover,
              x=client_dest[0], y=client_dest[1], z=client_dest[2])
    ff = poll(lambda: parallel(host).get("fastForward") is True, 8)
    assert idle(host, timeout=300), f"the chain never ended: {parallel(host)}"
    speed(host, 2)
    PI.settle(host, client, seconds=8)

    hb, cb = battle(host), battle(client)
    hi, ci = items(host), items(client)
    assert hi["counts"].get("STR_PROXIMITY_GRENADE", 0) == \
        ci["counts"].get("STR_PROXIMITY_GRENADE", 0), (
        f"the grenade survived on one machine only: host "
        f"{hi['counts'].get('STR_PROXIMITY_GRENADE', 0)} client "
        f"{ci['counts'].get('STR_PROXIMITY_GRENADE', 0)}")
    assert hi["total"] == ci["total"], (
        f"item census diverged over the fast-forwarded walk: host {hi['total']} "
        f"client {ci['total']}")
    for uid in (host_mover, client_mover):
        assert pos(hb, uid) == pos(cb, uid), \
            f"unit {uid} diverged: host {pos(hb, uid)} client {pos(cb, uid)}"
        assert unit(hb, uid)["health"] == unit(cb, uid)["health"], (
            f"unit {uid} took different damage: host "
            f"{unit(hb, uid)['health']} client {unit(cb, uid)['health']}")
    quiet(host, client, "after the fast-forwarded walk over a primed grenade")
    print(f"PASS 4: identical outcome on both machines (walker HP {h_hp} -> "
          f"{unit(hb, host_mover)['health']}, "
          f"{hi['total']} items on each, fastForward seen={bool(ff)})")


# ---- 5. rider: active_grenade's fuse is an int, not a bool -------------------

def scenario_fuse_width(host, client, client_mover):
    print("-- 5: a primed fuse arrives at its real value, not clipped to 1 --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    top_up(host, client, client_mover)
    wid = PI.give_both(host, client, client_mover, "STR_GRENADE")
    seq_before = parallel(host)["actionSeq"]
    r = PI.intent(client, action="prime", unit=client_mover, fuse=5, weapon_id=wid)
    assert r.get("ok") and r.get("routed") is True, f"the prime did not ship: {r}"
    assert PI.wait_until(lambda: parallel(client)["pendingReqId"] == 0, 25), \
        "the prime intent got no ack/deny"
    assert parallel(host)["actionSeq"] > seq_before, (
        f"the prime was never admitted; the client was told "
        f"{PI.warning_of(client)!r}")
    assert idle(host), "the prime chain never ended"
    PI.settle(host, client, seconds=4)

    hf, cf = fuse_of(host, wid), fuse_of(client, wid)
    assert hf == 5, f"the host primed the grenade to {hf}, not 5"
    assert cf == hf, (
        f"the client's copy of item {wid} carries fuse {cf}, the host's {hf}. "
        f"`active_grenade`'s receive read the value into a bool, so every fuse "
        f"above 1 arrived as 1 (and the -1 an unprime ships arrived as 1 too, "
        f"arming a grenade the executor had disarmed).")
    quiet(host, client, "after the primed-fuse round trip")
    print(f"PASS 5: fuse {hf} on both machines")


# ---- main ------------------------------------------------------------------

def main():
    fail = None
    host = GameClient("host", 48874,
                      make_user_dir("p7_skip_host",
                                    options={"battleXcomSpeed": 2,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48875,
                        make_user_dir("p7_skip_client",
                                      options={"battleXcomSpeed": 2,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines")

        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallel turns only "
            f"cover PVE (1) and PVE2 (4), so this test would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"
        assert battle(host)["activeSync"] is True and battle(client)["activeSync"] is False, \
            "the PRD-P5 executor invariant does not hold"
        ps = parallel(host)
        for key in ("fastForward", "chainSkippable", "displayBacklog",
                    "pendingAdmits"):
            assert key in ps, (
                f"parallel_state carries no {key!r} - PRD-P7's introspection is "
                f"missing and every assertion below would be vacuous: {sorted(ps)}")

        seat = client.ok({"cmd": "get_coop"})["localSeat"]
        client_mover = PI.pick_driver(host, client, seat, "client")
        host_mover = PI.pick_driver(host, client, 0, "host")

        host_mover = scenario_walk_skip(host, client, host_mover, client_mover)
        host_mover = scenario_shot_never_skipped(
            host, client, host_mover, client_mover)
        host_mover = scenario_reaction_cancels(
            host, client, host_mover, client_mover)
        scenario_proximity(host, client, host_mover, client_mover)
        scenario_fuse_width(host, client, client_mover)

        print("ALL WALK FAST-FORWARD TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
