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


def idle(gc, timeout=120):
    return PI.wait_until(
        lambda: parallel(gc).get("canAdmit") is True
        and not parallel(gc).get("pendingAdmits"), timeout)


def quiet(host, client, what):
    PI.settle(host, client)
    session.assert_battle_synced(host, client, what)
    assert not TW.desync_seen(host) and not TW.desync_seen(client), \
        f"the PRD-P2 drift tripwire fired {what}"


def long_walk_target(gc, uid, radius=4):
    """The furthest tile `uid` can reach - a one-tile step is over before the skip
    can make any observable difference."""
    for r in range(radius, 0, -1):
        dest = PI.far_step(gc, uid, radius=r)
        if dest:
            here = pos(battle(gc), uid)
            if max(abs(dest[0] - here[0]), abs(dest[1] - here[1])) >= 2:
                return dest
    return PI.free_step(gc, uid)


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
    print("-- 1: client input during a host WALK -> deferred + fast-forwarded --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    PI.top_up(host, client, host_mover)
    PI.top_up(host, client, client_mover)
    # Both destinations resolved while everything is idle: probe_step refuses
    # mid-chain (Pathfinding is a singleton the running walk dequeues from).
    client_dest = PI.free_step_both(host, client, client_mover)
    assert client_dest, f"client soldier {client_mover} cannot step anywhere"
    speed(host, SLOW_WALK_MS)
    assert look_at(host, host_mover), (
        f"the host's camera would not frame unit {host_mover}; an off-screen walk "
        f"runs at interval 0 regardless and the timing below would be meaningless")

    # Baseline: the SAME walk, uncontended. Self-calibrating - the animation cost
    # depends on the armor's phase count and on how many tiles the pathfinder
    # found, neither of which a constant in this file can know.
    host_dest = long_walk_target(host, host_mover)
    assert host_dest, f"host soldier {host_mover} cannot step anywhere"
    baseline = timed_walk(host, host_mover, host_dest,
                          parallel(host)["actionSeq"])
    PI.settle(host, client, seconds=3)
    print(f"    baseline: an unskipped walk at {SLOW_WALK_MS} ms/frame took "
          f"{baseline:.1f}s")

    PI.top_up(host, client, host_mover)
    assert look_at(host, host_mover), "the host's camera lost the walker"
    host_dest = long_walk_target(host, host_mover)
    assert host_dest, f"host soldier {host_mover} cannot step again"
    h_from = pos(battle(host), host_mover)
    c_from = pos(battle(host), client_mover)
    seq_before = parallel(host)["actionSeq"]

    started = time.time()
    assert PI.intent(host, action="move", unit=host_mover,
                     x=host_dest[0], y=host_dest[1], z=host_dest[2]).get("ok")
    # Synchronous on the host, so the walk is queued the instant the RPC returns.
    ps = parallel(host)
    assert ps.get("chainSkippable") is True, (
        f"a plain player walk did not classify as skippable ({ps}) - nothing "
        f"below is testing the skip")

    r = PI.intent(client, action="move", unit=client_mover,
                  x=client_dest[0], y=client_dest[1], z=client_dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    ff = poll(lambda: parallel(host).get("fastForward") is True, 8)
    pend = poll(lambda: bool(parallel(host).get("pendingAdmits")), 8)
    # The deferred intent is admitted at the drain, so action_seq +2 IS the drain.
    admitted = poll(lambda: parallel(host).get("actionSeq", 0) >= seq_before + 2, 90)
    elapsed = time.time() - started
    assert admitted, (
        f"the DEFERRED client intent was never admitted: host={parallel(host)} "
        f"client={parallel(client)} warning={PI.warning_of(client)!r}")

    assert PI.wait_until(
        lambda: pos(battle(host), client_mover) != c_from, 60), (
        f"the admitted client walk never ran: host={parallel(host)}")
    speed(host, 2)
    assert idle(host), f"the host never went idle: {parallel(host)}"
    PI.settle(host, client, seconds=6)

    seen = PI.warning_of(client)
    assert BUSY_TEXT.lower() not in (seen or "").lower(), (
        f"the client was refused {seen!r} - PRD-P7 must DEFER an input that "
        f"arrives behind a chain of pure locomotion, not refuse it")
    assert pend or ff, (
        f"neither a pending slot nor the fast-forward was ever visible on the "
        f"host, so the deferral cannot be told apart from a lucky race: "
        f"{parallel(host)}")
    if baseline >= 1.5:
        assert ff or elapsed < baseline * 0.6, (
            f"the contended walk took {elapsed:.1f}s against an uncontended "
            f"baseline of {baseline:.1f}s and the fast-forward was never "
            f"observed - the interval-0 seam is not firing")
    else:
        print(f"    (the baseline walk was only {baseline:.1f}s, so the timing "
              f"comparison is not meaningful; fastForward={bool(ff)} carries it)")
        assert ff, (
            f"the walk was too short to time and the fast-forward was never "
            f"observed either: {parallel(host)}")

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


# ---- 2. contention on a shot: never skipped ---------------------------------

def scenario_shot_never_skipped(host, client, host_mover, client_mover):
    print("-- 2: client input during a host SHOT -> refused busy, no skip --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    PI.top_up(host, client, host_mover)
    PI.top_up(host, client, client_mover)
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
    r = PI.intent(client, action="move", unit=client_mover,
                  x=client_dest[0], y=client_dest[1], z=client_dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    seen = PI.wait_for_text(client, BUSY_TEXT, timeout=25)
    speed(host, 2)
    assert seen, (
        f"no STR_COOP_PLAYER_BUSY flash after an intent sent into a running SHOT "
        f"(widget shows {PI.warning_of(client)!r}). A shot is exactly the chain "
        f"PRD-P7 must keep refusing.")
    assert not parallel(host).get("pendingAdmits"), (
        f"the intent was DEFERRED behind a shot: {parallel(host)}")
    assert pos(battle(host), client_mover) == c_before, (
        f"a refused intent still moved unit {client_mover} "
        f"({c_before} -> {pos(battle(host), client_mover)})")
    assert PI.wait_until(lambda: parallel(client)["pendingReqId"] == 0, 15), \
        "the deny did not clear the client's pending slot"
    assert idle(host), f"the shot chain never ended: {parallel(host)}"
    quiet(host, client, "after the refused shot contention")
    print(f"PASS 2: the shot was never skipped and the client was refused {seen}")


# ---- 3. reaction fire cancels the skip --------------------------------------

def scenario_reaction_cancels(host, client, host_mover, client_mover):
    print("-- 3: a shot joining a fast-forwarded walk cancels it --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    PI.top_up(host, client, host_mover)
    PI.top_up(host, client, client_mover)
    client_dest = PI.free_step_both(host, client, client_mover)
    assert client_dest, f"client soldier {client_mover} cannot step anywhere"
    wid = PI.give_both(host, client, host_mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    PI.top_up(host, client, host_mover)
    speed(host, SLOW_WALK_MS)
    assert look_at(host, host_mover), "the host's camera would not frame the walker"
    host_dest = long_walk_target(host, host_mover)
    assert host_dest, f"host soldier {host_mover} cannot step anywhere"

    c_before = pos(battle(host), client_mover)
    assert PI.intent(host, action="move", unit=host_mover,
                     x=host_dest[0], y=host_dest[1], z=host_dest[2]).get("ok")
    r = PI.intent(client, action="move", unit=client_mover,
                  x=client_dest[0], y=client_dest[1], z=client_dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"
    armed = poll(lambda: parallel(host).get("fastForward") is True
                 and bool(parallel(host).get("pendingAdmits")), 8)
    if not armed:
        speed(host, 2)
    assert armed, (
        f"the walk was never fast-forwarded with a pending input, so there is "
        f"nothing for the interruption to cancel: {parallel(host)}")

    # The interruption. `battle_fire` statePushBack()s a ProjectileFlyBState onto
    # the running chain - the same push TileEngine::checkReactionFire makes.
    aim = PI.aim_away(host, host_mover)
    host.cmd({"cmd": "battle_fire", "unit": host_mover, "mode": "snap",
              "weapon_id": wid, "tu": 200,
              "x": aim[0], "y": aim[1], "z": aim[2]})

    assert parallel(host).get("fastForward") is False, (
        f"the fast-forward survived a shot state joining the chain: "
        f"{parallel(host)}")
    assert not parallel(host).get("pendingAdmits"), (
        f"the pending input survived the interruption: {parallel(host)}")
    seen = PI.wait_for_text(client, BUSY_TEXT, timeout=25)
    speed(host, 2)
    assert seen, (
        f"the interrupted pending intent was dropped without telling the client "
        f"(widget shows {PI.warning_of(client)!r}) - the player would wait for an "
        f"action that is never coming")
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
          f"{seen}, and the census stayed symmetric")


# ---- 4. fast-forwarded walk over a primed proximity grenade ------------------

def scenario_proximity(host, client, host_mover, client_mover):
    print("-- 4: a fast-forwarded walk over a PRIMED proximity grenade --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    PI.top_up(host, client, host_mover)
    PI.top_up(host, client, client_mover)
    client_dest = PI.free_step_both(host, client, client_mover)
    assert client_dest, f"client soldier {client_mover} cannot step anywhere"
    speed(host, SLOW_WALK_MS)
    assert look_at(host, host_mover), "the host's camera would not frame the walker"
    host_dest = long_walk_target(host, host_mover)
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
    poll(lambda: parallel(host).get("fastForward") is True, 8)
    assert idle(host, timeout=180), f"the chain never ended: {parallel(host)}"
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
          f"{hi['total']} items on each)")


# ---- 5. rider: active_grenade's fuse is an int, not a bool -------------------

def scenario_fuse_width(host, client, client_mover):
    print("-- 5: a primed fuse arrives at its real value, not clipped to 1 --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    PI.top_up(host, client, client_mover)
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

        scenario_walk_skip(host, client, host_mover, client_mover)
        scenario_shot_never_skipped(host, client, host_mover, client_mover)
        scenario_reaction_cancels(host, client, host_mover, client_mover)
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
