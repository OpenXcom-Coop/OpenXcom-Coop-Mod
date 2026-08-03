"""PRD-P8: the end-turn readiness gate, its tally UI and reserve localization.

A parallel side has no owner. PRD-P5 let the HOST close it unilaterally, which
was fine while the client could not act at all; from PRD-P6 on the client is
playing, so one player's END TURN press must not cut the other one off
mid-thought. P8 replaces the press with a latching READINESS toggle:

    both machines press END TURN  ->  `end_turn_ready {seat, ready, side_seq}`
                                  <-  `end_turn_tally {ready_seats, auto_seats}`
    executor tick: every seat ready
                   AND canAdmitAction()          (no chain, gate open)
                   AND peer display backlog 0    (`action_done` drained)
                   -> the P5 side close, exactly once

and a seat that commands nothing live is AUTO-ready, so a wiped-out player never
has to keep pressing a button to let the other one play.

What this test asserts (PRD-P8 acceptance, in order):

  1. Toggle both directions from BOTH machines; the tally is identical on both.
  2. Auto-clear: a ready client ships a walk intent -> the host clears that
     seat's ready and the echo reaches the client.
  7. Reserve localization: `TU_COOP` / `kneel_reserved` stop crossing, so the two
     machines hold DIFFERENT reserve modes at the same time; the client's mode
     rides its intent and the host's own setting is unchanged afterwards.
  6. Drain barrier: a client that has DISPLAYED a chain but is holding its
     `action_done` back holds the commit off (`commitBlocked ==
     "display_backlog"`) until the report lands - only then does the side
     close. Held on demand with the `hold_action_done` lever rather than by
     trying to make the client slow, which cannot work (see hold_done).
  4. Commit: both ready -> the side ends EXACTLY once, `sideSeq` bumps, and the
     next player side comes back with both machines on `coopTurn == 2`.
  5. E14: intent vs commit, BOTH orders, each forced rather than raced -
     intent-first clears the acting seat's ready so the commit is not owed, and
     commit-first refuses the intent `turn_over` with nothing executed.
  3. Auto-ready: strip the client's seat down to its last unit and knock it out
     -> the seat goes auto-ready; gift one back -> auto clears.
  8. E16 coexistence: with a readiness tally live, ABANDON MISSION still opens a
     VoteMenu on both machines, the commit is HELD while the menu is up (the
     battlescape is not the top state), and a passing abandon supersedes the
     tally cleanly.

Order is dictated by the fixture: 3 gives the client's soldiers away, so
everything that needs a client-owned driver runs first, and 8 ends the mission.

Run:  python tools/coop_test/test_parallel_endturn.py
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

PORT = "47989"

BA_NONE = 0
BA_AIMEDSHOT = 9

FAST_SPEED = 2

# How long scenario 4+6 holds the peer's display report back, and how many
# samples inside that window must show the commit stuck behind it. Both are
# free parameters now that the barrier is held rather than raced.
HOLD_WINDOW = 12.0
MIN_HELD_SAMPLES = 10

TURN_OVER_TEXT = "turn has already ended"


# ---- readouts --------------------------------------------------------------

def battle(gc):
    return PI.battle(gc)


def parallel(gc):
    return PI.parallel(gc)


def tally(gc):
    """(explicit-ready seats, auto seats, readyCount, seatCount) as this machine
    sees it. The host owns the truth; a client holds the echoed tally plus its
    own optimistic bit."""
    p = parallel(gc)
    return (sorted(p.get("readySeats", [])), sorted(p.get("autoSeats", [])),
            p.get("readyCount"), p.get("seatCount"))


def arm(gc):
    """Press the REAL END TURN button (btnEndTurnClick), which in parallel mode
    is the readiness toggle and nothing else."""
    return gc.cmd({"cmd": "battle_action", "action": "end_turn_button"})


def wait_tally(host, client, explicit, what, timeout=30):
    """Both machines must agree on the EXPLICIT ready set."""
    want = sorted(explicit)
    ok = PI.wait_until(
        lambda: tally(host)[0] == want and tally(client)[0] == want, timeout)
    assert ok, (
        f"{what}: the two machines disagree about who is ready (wanted {want}) - "
        f"host {tally(host)} client {tally(client)}. `end_turn_tally` is the only "
        f"thing that carries the host's tally to the peer.")


def settle(host, client, seconds=6):
    PI.settle(host, client, seconds)


def turn_of(gc):
    return battle(gc).get("turn")


def hush(host, client, keep=()):
    """Zero the TU of every X-Com unit except `keep`, on BOTH machines.

    Fixture protection, not an assertion. This test closes the player side three
    times, and the skirmish fixture ships a HANDFUL of aliens: the first run of
    it lost its last hostile to reaction fire during the very first alien side,
    which ended the mission and made everything after it vacuous. Reaction fire
    costs TU, so a squad with none cannot shoot the fixture out from under the
    test. TU regenerate at the next turn, so this only covers the alien side that
    immediately follows - which is the only one that matters.
    """
    b = battle(host)
    assert b.get("inBattle"), (
        "the fixture's mission has already ended (its single hostile went "
        "down) - the scenario that was running had nothing left to assert")
    ids = [u["id"] for u in b["units"]
           if u.get("faction") == 0 and not u.get("isOut") and u["id"] not in keep]
    for uid in ids:
        for gc in (host, client):
            gc.cmd({"cmd": "battle_intent", "unit": uid, "action": "turn",
                    "tu": 0, "dry": True})
    return len(ids)


def hostiles(gc):
    return [u["id"] for u in battle(gc)["units"]
            if u.get("faction") == 1 and not u.get("isOut")]


def usable(gc, uid, seat):
    u = PI.unit(battle(gc), uid)
    return bool(u) and not u.get("isOut") and u.get("coop") == seat


def ensure_driver(host, client, seat, tag, current):
    """A live, correctly-owned, can-actually-move soldier of `seat`.

    Every closed side is an alien side, and the alien gets to shoot: a driver
    that was fine before the boundary can be a casualty after it, and the host's
    validator then refuses its intents (`invalid`/`unit_out`) with no obvious
    connection to what the scenario was testing."""
    if (current is not None and usable(host, current, seat)
            and usable(client, current, seat)):
        return current
    print(f"    (the {tag} driver {current} did not survive the boundary - "
          f"picking another)")
    return PI.pick_driver(host, client, seat, tag)


# ---- 1. the toggle ---------------------------------------------------------

def scenario_toggle(host, client, hseat, cseat):
    print("-- 1: toggle both directions, tally consistent on both machines --")
    wait_tally(host, client, [], "at the start of the side")

    arm(client)
    wait_tally(host, client, [cseat], "after the client armed")
    assert parallel(client)["localReady"] is True, \
        "the client does not consider ITSELF ready after its own press"
    assert parallel(host)["localReady"] is False, \
        "the host became ready because the CLIENT pressed END TURN"
    print(f"    client armed: tally {tally(host)[2]}/{tally(host)[3]} on both")

    arm(client)
    wait_tally(host, client, [], "after the client disarmed")
    print("    client disarmed: back to 0 on both")

    arm(host)
    wait_tally(host, client, [hseat], "after the host armed")
    assert turn_of(host) is not None
    print(f"    host armed: tally {tally(host)[2]}/{tally(host)[3]} on both")

    arm(host)
    wait_tally(host, client, [], "after the host disarmed")
    assert parallel(host)["commitBlocked"] in ("not_ready", "", "side_commit"), \
        f"the commit is blocked by something unexpected: {parallel(host)}"
    print("PASS 1: END TURN is a latching per-seat toggle on BOTH machines and "
          "the tally is identical on both")


# ---- 2. an admitted action clears that seat's ready -------------------------

def scenario_auto_clear(host, client, cseat, mover):
    print("-- 2: an admitted intent clears that seat's explicit ready --")
    assert PI.idle(host), "the host is still busy"
    PI.top_up(host, client, mover)
    dest = PI.free_step_both(host, client, mover)
    assert dest, f"client soldier {mover} cannot step anywhere"

    arm(client)
    wait_tally(host, client, [cseat], "before the intent")

    before = PI.pos(battle(host), mover)
    r = PI.intent(client, action="move", unit=mover,
                  x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"
    assert PI.wait_until(lambda: PI.pos(battle(host), mover) != before, 45), (
        f"the walk intent never ran on the host: {parallel(host)} "
        f"warning={PI.warning_of(client)!r}")
    wait_tally(host, client, [],
               "after the ready client's intent was admitted")
    assert PI.idle(host, timeout=90), "the host chain never ended"
    settle(host, client, seconds=4)
    print("PASS 2: the seat that acted is no longer ready, on BOTH machines "
          "(the echo carried it back)")


# ---- 7. reserve localization ------------------------------------------------

def reserve(gc, **kw):
    req = {"cmd": "battle_reserve"}
    req.update(kw)
    return gc.ok(req)


def scenario_reserve(host, client, mover):
    print("-- 7: reserve is per-machine and rides the intent --")
    assert PI.idle(host), "the host is still busy"
    reserve(host, mode="none", kneel=False)
    reserve(client, mode="none", kneel=False)
    time.sleep(2)

    # a) the setting stops crossing. In classic co-op btnReserveClick ships
    #    `TU_COOP` and the peer applies it, so this would converge.
    got = reserve(client, mode="aimed")
    assert got["reserve"] == BA_AIMEDSHOT, f"the client would not take it: {got}"
    time.sleep(4)
    hres = reserve(host)["reserve"]
    cres = reserve(client)["reserve"]
    assert cres == BA_AIMEDSHOT and hres == BA_NONE, (
        f"the reserve mirror still crosses in parallel mode: host {hres} "
        f"client {cres}. PRD-P8 §5 suppresses `TU_COOP`/`kneel_reserved` there "
        f"and ignores them on receipt - reserve is a per-machine setting when "
        f"both players are acting at once.")
    print(f"    per-machine: host reserve {hres}, client reserve {cres}, "
          f"held apart for 4 s")

    # b) the client's mode rides its intent, and the HOST's own setting is put
    #    back afterwards. `chainReserve` is the override installed for the
    #    running chain - sampled, because a short walk can be over inside one
    #    RPC round trip.
    PI.top_up(host, client, mover)
    dest = PI.far_step(host, mover, radius=3) or PI.free_step_both(host, client, mover)
    assert dest, f"client soldier {mover} cannot step anywhere"
    before = PI.pos(battle(host), mover)
    r = PI.intent(client, action="move", unit=mover,
                  x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    seen_override = None
    deadline = time.time() + 45
    while time.time() < deadline:
        ps = parallel(host)
        if ps.get("chainReserve", -1) == BA_AIMEDSHOT:
            seen_override = ps.get("chainReserveUnit")
            break
        if PI.pos(battle(host), mover) != before and ps.get("canAdmit") is True:
            break
        time.sleep(0.05)
    assert PI.idle(host, timeout=90), "the host chain never ended"
    settle(host, client, seconds=4)

    assert reserve(host)["reserve"] == BA_NONE, (
        f"executing a client intent left the HOST holding the client's reserve "
        f"({reserve(host)['reserve']}) - the override must be scoped to the "
        f"chain, not swapped into the host's own setting")
    assert reserve(client)["reserve"] == BA_AIMEDSHOT, \
        "the client's own reserve was changed by its intent running remotely"
    if seen_override is not None:
        assert seen_override == mover, (
            f"the reserve override was keyed on unit {seen_override}, not on "
            f"the intent's actor {mover} - it could reach another soldier")
        print(f"    caught the chain-scoped override live: reserve "
              f"{BA_AIMEDSHOT} keyed on unit {seen_override}")
    else:
        print("    (the chain was over before a sample landed - the override's "
              "presence is not asserted, only that it did not leak)")

    reserve(client, mode="none")
    reserve(host, mode="none")
    print("PASS 7: reserve is per-machine, the client's rides its intent and "
          "the host's own setting survives it untouched")


# ---- 4 + 6. the commit, and the display drain barrier in front of it --------

def hold_done(client, hold):
    """TestServer `hold_action_done`: while held, the CLIENT parks its
    `action_done` reports instead of shipping them. Releasing ships the newest
    parked seq, which subsumes every older one.

    The barrier below is real, but its natural window is ONE network round trip
    (~200 ms) and no fixture can widen it, so it has to be held open instead of
    raced. Making the client slow does not work: `battleXcomSpeed` paces only
    UnitWalk/UnitTurn/UnitFall, and PRD-P7's client-side display fast-forward
    pins exactly those to interval 0 whenever a gated packet is waiting (and
    `action_end` always is), while ProjectileFlyBState fixes its own interval and
    never reads the option at all. Freezing the client's battlescape under a
    modal does not work either - the background replay keeps draining through
    handleStateCoop and `action_done` is emitted from the gated drain in
    updateCoopTask. So the REPORT is held, not the display: same packet, same
    single emit point, it just leaves when this test says so.

    `heldActionDones` is what makes the scenario non-vacuous: it counts the
    reports parked since the hold was engaged, i.e. the chains the client really
    did finish displaying. 0 would mean the client is merely behind, which is a
    different (and untested) reason for the commit to be held.
    """
    r = client.ok({"cmd": "hold_action_done", "hold": bool(hold)})
    assert r.get("hold") is bool(hold), \
        f"the `hold_action_done` lever did not take (wanted {hold}): {r}"
    return r


def wait_side(host, client, start_turn, timeout=300):
    """Wait for the player side to close and come back, draining the turn screens
    exactly the way test_parallel_sharedturn.cycle_side does (the HOST's
    NextTurnState must self-close - close() is what ships `next_turn`)."""
    deadline = time.time() + timeout
    stalled = {}
    while time.time() < deadline:
        for gc in (host, client):
            b = battle(gc)
            if not b.get("inBattle"):
                return None
            state = TW.top(gc)
            if state == "NextTurnState":
                if gc is host:
                    first = stalled.setdefault(id(gc), time.time())
                    if time.time() - first > 25:
                        gc.cmd({"cmd": "dismiss_popup"})
                        stalled.pop(id(gc), None)
                    continue
                gc.cmd({"cmd": "dismiss_popup"})
                continue
            stalled.pop(id(gc), None)
            if state != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        now = battle(host)
        if (now.get("turn") is not None and start_turn is not None
                and now["turn"] > start_turn and now.get("coopTurn") == 2
                and battle(client).get("coopTurn") == 2):
            return now["turn"]
        time.sleep(0.5)
    return False


def scenario_commit_and_drain(host, client, hmover, hseat, cseat):
    """PRD-P8 acceptance 4 (the commit) and 6 (the drain barrier in front of it).

    Deliberately ONE side close for both: the fixture ships a handful of aliens
    and every closed side is another chance for the mission to end under the
    test (see hush()). The barrier is what delays THIS commit, and the commit's
    own properties are asserted when it finally lands.

    Shape: park the peer's display report (hold_done) -> the host runs ONE chain
    -> both seats ready -> the commit is stuck on `display_backlog` for as long
    as the hold lasts -> release -> it fires exactly once. A single chain is the
    point: the arbiter refuses to ADMIT at a backlog of 2, so one outstanding
    chain is the only state in which `canAdmit` is true and the display report is
    provably the last thing standing between two ready seats and the side close.
    """
    print("-- 4 + 6: both ready, commit deferred until the peer's display drains --")
    assert PI.idle(host), "the host is still busy"
    turn_before = turn_of(host)
    side_before = parallel(host)["sideSeq"]

    # one seat ready is not enough, whatever else is true
    arm(client)
    wait_tally(host, client, [cseat], "with only the client ready")
    time.sleep(2)
    assert turn_of(host) == turn_before, (
        f"the side closed on ONE seat's readiness (turn {turn_before} -> "
        f"{turn_of(host)}) - every seat has to be ready")
    assert parallel(host)["commitBlocked"] == "not_ready", (
        f"the commit was held for the wrong reason with one seat ready: "
        f"{parallel(host)}")
    print("    one seat ready: commit held on `not_ready`")

    # Nothing from the scenarios above may still be undisplayed: the arbiter
    # refuses to admit at a backlog of 2, so with a stale chain outstanding the
    # one below would never start.
    assert PI.wait_until(lambda: parallel(host)["displayBacklog"] == 0, 30), (
        f"an EARLIER chain is still undisplayed - this scenario has to own the "
        f"only outstanding one: {parallel(host)}")

    hold_done(client, True)
    held = 0
    blocked_reasons = set()
    released_at = None
    try:
        PI.top_up(host, client, hmover)
        # Everyone but the walker is hushed BEFORE the commit can fire - the
        # alien side that follows it is the one that has to stay non-lethal, and
        # by the time the poll loop below exits that side has already run.
        hush(host, client, keep=(hmover,))
        dest = PI.free_step_both(host, client, hmover)
        assert dest, f"host soldier {hmover} cannot step anywhere"
        before = PI.pos(battle(host), hmover)
        seq_before = parallel(host)["actionSeq"]
        # A plain walk, and with the report held that IS enough. Before the lever
        # this had to be a SHOT, because a walk the client fast-forwards leaves no
        # measurable window (measured: 0 samples) - the shot was a workaround for
        # the missing hold, not something the barrier cares about.
        r = PI.intent(host, action="move", unit=hmover,
                      x=dest[0], y=dest[1], z=dest[2])
        assert r.get("ok"), f"the host lever refused the walk: {r}"
        assert PI.wait_until(
            lambda: parallel(host)["actionSeq"] > seq_before, 30), (
            f"the walk was never admitted, so no chain exists for the peer to "
            f"owe a display report on: {parallel(host)}")
        assert PI.idle(host, timeout=90), "the host chain never ended"
        assert PI.pos(battle(host), hmover) != before, (
            f"the chain the barrier is about never moved unit {hmover}")

        # The client HAS displayed the chain and is WITHHOLDING the report.
        # Without this the barrier below would be indistinguishable from a peer
        # that simply never received the packet.
        assert PI.wait_until(
            lambda: parallel(client)["heldActionDones"] >= 1, 60), (
            f"the client never finished displaying the chain, so nothing was "
            f"parked and the barrier is not what would be holding the commit: "
            f"client={parallel(client)} host={parallel(host)}")
        assert parallel(host)["displayBacklog"] >= 1, (
            f"the client parked its report but the host sees no undisplayed "
            f"chain: {parallel(host)}")

        # Armed AFTER the walk was admitted - admitting clears the acting seat's
        # explicit ready, so arming first would just be undone.
        arm(host)
        hush(host, client)   # the walker too, now that its chain is over
        wait_tally(host, client, [hseat, cseat],
                   "with both seats ready behind the drain barrier")

        deadline = time.time() + HOLD_WINDOW
        while time.time() < deadline:
            ph = parallel(host)
            if ph.get("commitBlocked"):
                blocked_reasons.add(ph["commitBlocked"])
            backlog = ph.get("displayBacklog", 0)
            now = turn_of(host)
            assert now == turn_before, (
                f"the side closed with {backlog} chain(s) the peer has not "
                f"reported DISPLAYED (turn {turn_before} -> {now}). "
                f"PROTOCOL.md ordering invariant 4 makes the commit wait for "
                f"`action_done` to drain: host={ph} client={parallel(client)}")
            if (backlog > 0 and ph.get("canAdmit") is True
                    and ph.get("commitBlocked") == "display_backlog"):
                # states drained, gate open, both seats ready: the ONLY thing
                # left between them and the side close is the peer's report.
                held += 1
            time.sleep(0.25)
        assert "display_backlog" in blocked_reasons, (
            f"the commit was never held on the drain barrier - reasons seen "
            f"{sorted(blocked_reasons)}: host={parallel(host)}")
        assert held >= MIN_HELD_SAMPLES, (
            f"the barrier was barely exercised: only {held} sample(s) over "
            f"{HOLD_WINDOW} s had an idle executor, a ready tally and an "
            f"undisplayed backlog (wanted >= {MIN_HELD_SAMPLES}); reasons seen "
            f"{sorted(blocked_reasons)}. host={parallel(host)} "
            f"client={parallel(client)}")
        print(f"    the commit was held on `display_backlog` for {held} "
              f"sample(s) over {HOLD_WINDOW:.0f} s with both seats ready and "
              f"the executor idle "
              f"({parallel(client)['heldActionDones']} report(s) parked)")
    finally:
        try:
            hold_done(client, False)
            released_at = time.time()
        except Exception as he:   # never mask the real failure
            print(f"    (releasing the `action_done` hold failed: {he})")

    turn = wait_side(host, client, turn_before)
    assert turn, (
        f"the parked report was released with both seats ready and the side "
        f"still never closed: host={parallel(host)} client={parallel(client)}, "
        f"host top={TW.top(host)} client top={TW.top(client)}")
    assert turn == turn_before + 1, (
        f"the side closed more than once: turn {turn_before} -> {turn}")
    if released_at is not None:
        print(f"    ...and closed {time.time() - released_at:.1f} s after the "
              f"report was released, having sat still for {HOLD_WINDOW:.0f} s "
              f"before it")

    side_after = parallel(host)["sideSeq"]
    assert side_after > side_before, (
        f"`side_seq` did not advance across the commit ({side_before} -> "
        f"{side_after}) - every client intent would still carry the old token")
    for gc, tag in ((host, "host"), (client, "client")):
        b = battle(gc)
        assert b["coopTurn"] == 2, \
            f"{tag}: coopTurn is {b['coopTurn']}, not 2, on the new player side"
    wait_tally(host, client, [], "on the new player side")
    assert parallel(client)["sideSeq"] == side_after, (
        f"the client did not adopt the new side token (host {side_after}, "
        f"client {parallel(client)['sideSeq']}) - its next intent would be "
        f"denied `turn_over`")
    assert parallel(client)["holdActionDone"] is False, (
        f"the test lever is still engaged after the scenario - every later "
        f"chain would wedge the executor: {parallel(client)}")
    print(f"PASS 4+6: the barrier held the commit until the peer's report was "
          f"released, then the side closed ONCE (turn {turn_before} -> {turn}), "
          f"sideSeq {side_before} -> {side_after}, both machines back on "
          f"coopTurn 2 with the tally cleared")

# ---- 5. the E14 race --------------------------------------------------------

def scenario_race(host, client, hseat, cseat, mover):
    """PRD-P8 E14, both halves, DETERMINISTICALLY.

    The PRD words this as a race ("client intent vs host commit -> exactly one
    of..."), and a genuine race decides which half gets exercised by coin flip.
    Both halves are worth an assertion and neither is worth a flaky one, so each
    is forced instead: (a) admit the intent first and prove the pending commit
    cannot fire, (b) let the commit start first and prove the intent that follows
    executes NOTHING.
    """
    print("-- 5 (E14): intent vs commit, both orders --")
    assert PI.idle(host), "the host is still busy"
    PI.top_up(host, client, mover)
    dest = PI.free_step_both(host, client, mover)
    assert dest, f"client soldier {mover} cannot step anywhere"
    before = PI.pos(battle(host), mover)
    turn_before = turn_of(host)

    # (a) intent first: the admit clears that seat's ready, so the commit the
    #     other seat is about to ask for simply is not owed.
    arm(client)
    wait_tally(host, client, [cseat], "before the intent-first half")
    seq_before = parallel(host)["actionSeq"]
    r = PI.intent(client, action="move", unit=mover,
                  x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"
    assert PI.wait_until(
        lambda: parallel(host)["actionSeq"] > seq_before, 45), (
        f"the intent was never admitted: {parallel(host)} "
        f"warning={PI.warning_of(client)!r}")
    wait_tally(host, client, [], "after the ready client acted")
    arm(host)
    wait_tally(host, client, [hseat], "with only the host ready")
    time.sleep(4)
    assert turn_of(host) == turn_before, (
        f"the side closed although the client's ready had been cleared by its "
        f"own action (turn {turn_before} -> {turn_of(host)})")
    assert PI.pos(battle(host), mover) != before, \
        "the intent-first half never actually moved anything"
    print(f"    (a) intent-first: the walk ran, the client's ready was cleared "
          f"and the host's pending commit is held on "
          f"`{parallel(host)['commitBlocked']}`")

    # (b) commit first: the intent loses, and it loses by being REFUSED - nothing
    #     of it may execute on the side that is closing.
    #
    #     Forced rather than raced. The window in which `_sideCommitInProgress`
    #     is true is a frame or two wide (the end-turn sentinel pops almost
    #     immediately), and an intent that misses it is stamped with the NEXT
    #     side's token and legitimately runs there - which is a pass that looks
    #     like a failure. The side no longer belonging to the player is the same
    #     first branch of the intent handler that a mid-commit arrival takes
    #     (`stale side_seq || not FACTION_PLAYER || _sideCommitInProgress` ->
    #     `turn_over`), and it is seconds wide instead of milliseconds.
    assert PI.idle(host, timeout=90), "the host chain never ended"
    settle(host, client, seconds=4)
    PI.top_up(host, client, mover)
    dest2 = PI.free_step_both(host, client, mover)
    assert dest2, f"client soldier {mover} cannot step anywhere for the (b) half"
    # the mover is hushed too: `turn_over` is decided before the intent is ever
    # validated, so it needs no TU to be refused - and a driver left holding 200
    # TU next to the fixture's ONE alien reaction-fires it dead over the coming
    # alien side, which ends the mission and the test with it (measured).
    hush(host, client)
    client.cmd({"cmd": "parallel_state", "clear_deny": True})
    # the host is STILL armed from (a) - nothing since has been admitted for its
    # seat - so one client press is all it takes to make the tally complete.
    assert tally(host)[0] == [hseat], \
        f"the host lost its readiness between the two halves: {tally(host)}"
    arm(client)
    assert PI.wait_until(
        lambda: parallel(host)["sideCommit"] is True
        or battle(host).get("side") != 0, 90), (
        f"the commit never started with both seats ready: {parallel(host)}")
    before2 = PI.pos(battle(host), mover)
    r = PI.intent(client, action="move", unit=mover,
                  x=dest2[0], y=dest2[1], z=dest2[2])
    assert r.get("ok") and r.get("routed") is True, \
        f"the client would not ship the intent into the closing side: {r}"
    assert PI.wait_until(
        lambda: parallel(client)["lastDenyReason"] != "", 25), (
        f"the intent shipped into a committing/closed side was never refused: "
        f"{parallel(client)}")
    got = parallel(client)["lastDenyReason"]
    assert got == "turn_over", (
        f"the intent was refused `{got}`, not `turn_over` - PROTOCOL.md keeps "
        f"`turn_over` for exactly this (side committed / AI phase): "
        f"{parallel(client)}")
    assert PI.pos(battle(host), mover) == before2, (
        f"a REFUSED intent still moved unit {mover} on the host: {before2} -> "
        f"{PI.pos(battle(host), mover)}")
    turn = wait_side(host, client, turn_before, timeout=240)
    assert turn, (
        f"the commit-first half never closed the side: host={parallel(host)}")
    print(f"    (b) commit-first: the intent was refused `{got}` "
          f"({parallel(client)['lastDenyWarning']}) and executed nothing; the "
          f"side closed (turn -> {turn})")
    print("PASS 5: both E14 orders resolve cleanly - never both outcomes")


# ---- 3. auto-ready ----------------------------------------------------------

def client_units(host, client, cseat):
    return [u["id"] for u in battle(client)["units"]
            if u.get("faction") == 0 and not u.get("isOut")
            and u.get("coop") == cseat]


def gift(gc, uid, owner):
    return gc.cmd({"cmd": "battle_gift", "unit_id": uid, "owner": owner})


def knock_out(host, client, hmover, victim, swings=12):
    """Stun-rod the victim from a host soldier - the deterministic knockout the
    PRD-P4 test lever settled on (it cannot miss and cannot overkill)."""
    vpos = PI.pos(battle(host), victim)
    if not PI.place_adjacent(host, client, hmover, vpos):
        return False
    wid = PI.give_both(host, client, hmover, "STR_STUN_ROD")
    for i in range(swings):
        r = host.cmd({"cmd": "battle_fire", "unit": hmover, "mode": "hit",
                      "weapon_id": wid, "tu": 200,
                      "x": vpos[0], "y": vpos[1], "z": vpos[2]})
        if not r.get("ok"):
            break
        settle(host, client, seconds=3)
        PI.idle(host)
        u = PI.unit(battle(host), victim)
        if u and u.get("isOut"):
            print(f"    unit {victim} went down after {i + 1} swing(s)")
            return True
    return False


def scenario_auto_ready(host, client, hseat, cseat, hmover):
    print("-- 3: a seat with nothing left to command is AUTO-ready --")
    assert PI.idle(host), "the host is still busy"
    assert tally(host)[1] == [], \
        f"a seat was already auto-ready before the roster was touched: {tally(host)}"

    mine = client_units(host, client, cseat)
    assert len(mine) >= 2, (
        f"the fixture gave the client only {len(mine)} unit(s) - the last-unit "
        f"scenario needs at least two")
    keep = mine[0]
    for uid in mine[1:]:
        gift(client, uid, hseat)
    settle(host, client, seconds=6)
    left = client_units(host, client, cseat)
    assert left == [keep], (
        f"the gift-away left the client seat holding {left}, not just {[keep]}")
    assert tally(host)[1] == [], (
        f"the client seat is auto-ready while it still commands {left}: "
        f"{tally(host)}")
    print(f"    client seat stripped to one unit ({keep}); still not auto-ready")

    down = knock_out(host, client, hmover, keep)
    if not down:
        print(f"    (the stun rod could not reach unit {keep} - giving it away "
              f"instead; the auto predicate is the same 'no live commandable "
              f"unit of this seat')")
        gift(client, keep, hseat)
        settle(host, client, seconds=6)

    assert PI.wait_until(lambda: tally(host)[1] == [cseat], 40), (
        f"the client seat commands nothing live and is still not auto-ready: "
        f"host {tally(host)} (units left: {client_units(host, client, cseat)})")
    assert PI.wait_until(lambda: tally(client)[1] == [cseat], 30), (
        f"the auto-ready never reached the client: {tally(client)}")
    assert parallel(host)["readyCount"] == 1, (
        f"auto readiness did not count towards the tally: {parallel(host)}")
    print(f"    the emptied client seat is AUTO-ready on both machines "
          f"({tally(host)[2]}/{tally(host)[3]})")

    # gaining a unit clears it again - the auto bit is derived, not remembered
    theirs = [u["id"] for u in battle(host)["units"]
              if u.get("faction") == 0 and not u.get("isOut")
              and u.get("coop") == hseat]
    assert theirs, "the host commands nothing to gift back"
    gift(host, theirs[0], cseat)
    settle(host, client, seconds=6)
    assert PI.wait_until(lambda: tally(host)[1] == [], 40), (
        f"the client seat is still auto-ready after being gifted unit "
        f"{theirs[0]}: host {tally(host)}, client units "
        f"{client_units(host, client, cseat)}")
    print(f"PASS 3: auto-ready followed the roster in both directions "
          f"(emptied -> ready, gifted unit {theirs[0]} back -> cleared)")


# ---- 8. E16: the abandon vote coexists with the tally -----------------------

def vote(gc):
    return gc.ok({"cmd": "vote_state"})


def scenario_vote(host, client, hseat, cseat):
    print("-- 8 (E16): abandon-mission vote alongside a live readiness tally --")
    assert PI.idle(host), "the host is still busy"
    arm(client)
    wait_tally(host, client, [cseat], "before the vote")

    host.ok({"cmd": "battle_action", "action": "abort"})
    for gc, tag in ((host, "host"), (client, "client")):
        v = gc.wait_for(
            f"{tag} abandon-mission VoteMenu",
            lambda gc=gc: (lambda s: s if (s.get("active") and s.get("menuOpen"))
                           else None)(gc.ok({"cmd": "vote_state"})),
            timeout=30, interval=0.25)
        assert v["action"] == "abandon_mission", f"{tag}: wrong vote: {v}"
    print("    the VoteMenu opened on both machines with the tally still live")

    # With the menu up, the battlescape is not the top state, so the commit is
    # HELD even once every seat is ready - the vote supersedes it by construction.
    turn_before = turn_of(host)
    hush(host, client)
    arm(host)
    time.sleep(4)
    ph = parallel(host)
    assert turn_of(host) == turn_before, (
        f"the side committed underneath an open VoteMenu (turn {turn_before} -> "
        f"{turn_of(host)}) - the player is looking at the vote, not the battle")
    assert ph["commitBlocked"] == "not_top_state", (
        f"the commit was held for the wrong reason while the vote was open: "
        f"{ph['commitBlocked']}")
    print(f"    both seats ready ({ph['readyCount']}/{ph['seatCount']}) and the "
          f"commit is held on `{ph['commitBlocked']}` - the vote wins")

    # a NO leaves everything exactly as it was: battle, tally and all
    cast = client.ok({"cmd": "vote_cast", "yes": False})
    assert cast.get("accepted"), f"the client's NO was rejected: {cast}"
    for gc, tag in ((host, "host"), (client, "client")):
        v = gc.wait_for(f"{tag} failed vote",
                        lambda gc=gc: (lambda s: s if s.get("finished") else None)(
                            gc.ok({"cmd": "vote_state"})),
                        timeout=30, interval=0.25)
        assert v["passed"] is False, f"{tag}: a 1-1 split passed: {v}"
        assert battle(gc).get("inBattle"), f"{tag}: a FAILED vote ended the battle"
    for gc in (host, client):
        gc.ok({"cmd": "vote_close"})
    host.ok({"cmd": "vote_clear_cooldown"})
    print("    the NO failed the vote and the battle survived it")

    # the tally survived the vote too, so the commit resumes the moment the menu
    # is gone - which is the same thing as "a failed abandon changes nothing".
    got = wait_side(host, client, turn_before, timeout=240)
    assert got, (
        f"the held commit never resumed once the VoteMenu closed: "
        f"host={parallel(host)} top={TW.top(host)}")
    print(f"    the held commit resumed once the menu closed (turn {got})")

    # ...and a PASSING abandon supersedes the tally. The vote is opened FIRST and
    # the seats armed underneath it: arming first would complete the tally and
    # close the side before ABORT could be pressed (btnAbortClick needs
    # allowButtons(), which is false off the player side).
    assert PI.idle(host), "the host is still busy"
    turn_before = turn_of(host)
    stale_id = host.ok({"cmd": "vote_state"})["id"]
    host.ok({"cmd": "battle_action", "action": "abort"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} second VoteMenu",
                    lambda gc=gc: (lambda s: s if (s.get("active") and s.get("menuOpen")
                                                   and not s.get("finished")
                                                   and s.get("id") != stale_id) else None)(
                        gc.ok({"cmd": "vote_state"})),
                    timeout=30, interval=0.25)
    arm(host)
    if not parallel(client)["localReady"]:
        arm(client)
    assert PI.wait_until(lambda: parallel(host)["allReady"] is True, 30), (
        f"the tally is not complete under the open menu, so 'the abandon "
        f"supersedes it' would prove nothing: {parallel(host)}")
    assert turn_of(host) == turn_before, (
        f"the side committed under the second VoteMenu (turn {turn_before} -> "
        f"{turn_of(host)})")
    client.ok({"cmd": "vote_cast", "yes": True})
    ended = PI.wait_until(lambda: not battle(host).get("inBattle"), 180, interval=1.0)
    assert ended, (
        f"the passing abandon vote did not end the mission: host "
        f"top={TW.top(host)} battle={battle(host).get('inBattle')}")
    print("PASS 8: the abandon vote and the readiness tally coexist - the menu "
          "holds the commit, a NO changes nothing, and a passing abandon "
          "supersedes the tally and ends the mission")


# ---- main ------------------------------------------------------------------

def main():
    fail = None
    host = GameClient("host", 48878,
                      make_user_dir("p8_endturn_host",
                                    options={"battleXcomSpeed": FAST_SPEED,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48879,
                        make_user_dir("p8_endturn_client",
                                      options={"battleXcomSpeed": FAST_SPEED,
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
        ps = parallel(host)
        for field in ("readySeats", "autoSeats", "sideSeq", "readyCount",
                      "seatCount", "commitBlocked"):
            assert field in ps, (
                f"parallel_state carries no `{field}` - every assertion below "
                f"would be vacuous: {sorted(ps)}")
        hseat = parallel(host)["localSeat"]
        cseat = parallel(client)["localSeat"]
        assert hseat != cseat, f"both machines report seat {hseat}"
        print(f"seats: host {hseat}, client {cseat}; "
              f"{parallel(host)['seatCount']} seat(s) in the roster; "
              f"{len(hostiles(host))} live hostile(s) in the fixture")

        cmover = PI.pick_driver(host, client, cseat, "client")
        hmover = PI.pick_driver(host, client, hseat, "host")

        # Order is fixture-driven: the scenarios that close a side come before
        # the one that gives the client's soldiers away, and the one that ends
        # the mission is last.
        scenario_toggle(host, client, hseat, cseat)
        scenario_auto_clear(host, client, cseat, cmover)
        scenario_reserve(host, client, cmover)
        scenario_commit_and_drain(host, client, hmover, hseat, cseat)
        assert battle(host).get("inBattle"), (
            "the fixture's mission ended during the first side close (its last "
            "hostile went down) - nothing below could be asserted")
        cmover = ensure_driver(host, client, cseat, "client", cmover)
        scenario_race(host, client, hseat, cseat, cmover)
        assert battle(host).get("inBattle"), \
            "the fixture's mission ended during the E14 scenario"
        session.assert_battle_synced(host, client, "after the readiness scenarios")
        assert not TW.desync_seen(host) and not TW.desync_seen(client), \
            "the PRD-P2 drift tripwire fired during the readiness scenarios"
        hmover = ensure_driver(host, client, hseat, "host", hmover)
        scenario_auto_ready(host, client, hseat, cseat, hmover)
        scenario_vote(host, client, hseat, cseat)

        print("ALL END-TURN READINESS TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} parallel: {parallel(gc)}")
                print(f"  DBG {tag} top:      {TW.top(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
