"""PRD-P11: the receive pump applies a unit's packets in the order they were sent.

The P10 soak found the last known battlescape-sync defect, and it was in the
PUMP, not in any handler: `updateCoopTask()` rotated a packet it could not
consume yet to the BACK of the hold queue and carried on applying the
always-consume traffic behind it. A `BattleScapeMove` blocked once could
therefore end up behind its own follow-ups. The captured trace:

    host sent   Move(47) abortPath(37) Move(37) abortPath(27)
    peer applied            abortPath(37) Move(37) abortPath(27) ... Move(47)

- two seconds late, with the peer then walking unit 47 out of a stale position
and nothing left to correct it.

The shape is manufacturable without a 200k backlog. `abortPath` is exempt from
the receive gate while a walk is running (`_coopWalkInit`) because it is what
ENDS that walk, so on a machine that is still finishing walk N:

    Move(u)#N+1   gate closed  -> deferred
    abortPath(u)#N+1  exempt   -> applied, out of order

i.e. the peer teleport-corrects unit u to the end of a walk it has not started,
and then walks it AGAIN from there when the deferred `Move` finally lands.

This test drives one unit through back-to-back walks with the two instances at
opposite ends of the animation-speed range - the same lever PRD-P7/P9 use to make
the peer lag - and reads the peer's APPLIED-PACKET RING (`parallel_state` with
`trace: true`, PRD-P11) to assert the property directly:

  1. ORDER (end to end). Over the peer's whole applied stream, restricted to the
     driver, an `abortPath` never overtakes the `BattleScapeMove` it closes (at no
     prefix do the aborts outnumber the moves).
  2. ORDER (deterministic). Three no-op packets about the driver, all of them
     held by the receive gate, are put into the peer's hold queue while that gate
     is SHUT, and the peer must apply all three in the order they landed - none
     starved, none overtaken. This does not depend on timing: `rx_inject` reports
     the state of the gate at the moment the burst landed, so a missed window is
     retried rather than passed off as a result. It is the assertion that would
     catch a pump that rotates, drops or re-orders what it cannot consume yet.
  3. LIVENESS. `rxLegacyPasses` stays 0 on both machines: the pump's escape hatch
     (per-subject blocking disabled after a long stall) never had to fire, so the
     ordering guarantee held for the whole run without being traded away.
  4. CONVERGENCE. Both machines finish with the same position, and the PRD-P2
     drift tripwire stays quiet.

Neither assertion on its own is a complete proof: whether the walk-level window
in 1 opens at all depends on how fast the peer's display fast-forward closes it,
and 2 is satisfied by any pump that keeps its queue in order. Together they cover
the property the pump has to have - a unit's stream is applied in the order it
was sent, whatever the gate does in between.

Run:  python tools/coop_test/test_parallel_rx_order.py
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
import test_parallel_introspection as TI
import test_parallel_soak as SO

PORT = "47993"

HOST_SPEED = 2       # ms/frame: the executor runs at speed
CLIENT_SPEED = 500   # ms/frame: the peer is a slideshow, so it is always behind
WALKS = 6
WALK_RADIUS = 3
SLOW_FIRE = 1500     # ms/projectile-frame on the peer: what actually slows a SHOT
TRACE_LIMIT = 256    # == kRxTraceMax in connectionTCP.cpp


def battle(gc):
    return PI.battle(gc)


def parallel(gc):
    return PI.parallel(gc)


class Trace:
    """The peer's applied-packet ring, stitched together across polls.

    The ring holds the last 256 applied packets, so a run that applies more than
    that has to be sampled as it goes. Entries are keyed by their monotonic
    `seq`, which also makes a gap (a window that skipped ahead) detectable rather
    than silently papered over.
    """

    def __init__(self):
        self.by_seq = {}
        self.gaps = 0
        self._highest = 0

    def poll(self, gc):
        r = gc.cmd({"cmd": "parallel_state", "trace": True,
                    "traceLimit": TRACE_LIMIT})
        entries = r.get("rxTrace")
        if entries is None:
            raise AssertionError(
                "parallel_state carries no rxTrace, so every order assertion "
                f"below would be vacuous: {sorted(r)}")
        if entries:
            lowest = entries[0]["seq"]
            if self._highest and lowest > self._highest + 1:
                # the ring rolled between polls - say so rather than pretend the
                # stream was contiguous
                self.gaps += 1
            self._highest = max(self._highest, entries[-1]["seq"])
        for e in entries:
            self.by_seq[e["seq"]] = e
        return r

    def applied(self, unit=None, states=None):
        out = [self.by_seq[s] for s in sorted(self.by_seq)]
        if unit is not None:
            out = [e for e in out if e["unit"] == unit]
        if states is not None:
            out = [e for e in out if e["state"] in states]
        return out


WALK_STATES = ("BattleScapeMove", "abortPath")


def order_violations(entries):
    """Every `abortPath` that was applied before the `BattleScapeMove` it closes.

    `UnitWalkBState` sends `BattleScapeMove` from init() and `abortPath` from
    deinit(), always in that order and always paired, so over any prefix of one
    unit's stream the aborts can never outnumber the moves. A re-init (the state
    is re-entered after the UnitFallBState it pushes pops) can ship an EXTRA
    move, which this invariant tolerates by design - the failure mode being
    tested is an abort that ran early, not a move that ran twice.

    Leading aborts are skipped: the ring is process-wide and the first poll can
    land mid-walk, so an abort whose move predates the window is not evidence.
    """
    moves = aborts = 0
    bad = []
    started = False
    for e in entries:
        if e["state"] == "BattleScapeMove":
            started = True
            moves += 1
        elif e["state"] == "abortPath":
            if not started:
                continue
            aborts += 1
            if aborts > moves:
                bad.append(e)
    return bad, moves, aborts


def noop_burst(gc, uid):
    """Three packets about `uid` that change nothing when applied, in a fixed
    order the applied ring can read back.

    All three are held by the receive gate, which is the class the ordering rule
    exists for: a unit's replay stream must be applied in the order it was sent
    however long the gate holds it.

      * `hit_unit` re-applies the unit's CURRENT health/stun. No `fatalWounds`
        key: the handler only walks the array it is given, so leaving it out
        cannot clear wounds the peer already has.
      * `motion_scan` re-applies the CURRENT turn as the unit's scanned turn -
        a motion-scanner display term and nothing else.
    """
    b = battle(gc)
    u = PI.unit(b, uid)
    assert u, f"unit {uid} is not in the peer's battle state"
    hit = {"state": "hit_unit", "unit_id": uid,
           "health": u["health"], "stunlevel": u.get("stun", 0)}
    scan = {"state": "motion_scan", "unit_id": uid, "turn": b.get("turn", 1)}
    return [dict(hit), dict(scan), dict(hit)]


BURST_STATES = ("hit_unit", "motion_scan")
BURST_ORDER = ["hit_unit", "motion_scan", "hit_unit"]


def scenario_injected_order(host, client, mover, trace):
    """The deterministic half: land the burst while the peer's gate is SHUT.

    The gate is held with a SLOW SHOT, not a walk. PRD-P9's soak measured why: a
    lone walk always leaves the gated `action_end` marker in the peer's hold
    queue, which arms PRD-P7's display fast-forward and compresses the animation
    away - the window closes in a frame or two and the injection races it. A
    `ProjectileFlyBState` chain is never skippable, so at `battleFireSpeed`
    SLOW_FIRE the peer's gate is genuinely shut for seconds.

    Deliberately NOT `PI.start_busy_shot`: that helper proves the chain outlives
    the RPC on the EXECUTOR, and the executor here is deliberately the fast
    machine. What this needs is the PEER's gate, which is watched directly.

    The burst is ARMED rather than injected: `rx_inject {awaitGate: true}` hands
    it to the peer's own main loop, which lands it on the first tick whose gate
    is shut. That removes the round trip from the window entirely - the test can
    no longer lose the race it is trying to observe.
    """
    print("-- deterministic: a unit's queued packets are applied in the order "
          "they landed --")
    assert PI.idle(host), f"the executor is still busy: {parallel(host)}"
    SO.move_clear_of_hostiles(host, client, mover)
    client.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": SLOW_FIRE})
    cam = client.ok({"cmd": "battle_camera", "unit": mover, "visible": True})
    assert cam.get("onScreen"), (
        f"the peer's camera would not frame the shooter, so it would draw the "
        f"chain at interval 0 and its gate would barely shut: {cam}")
    wid = PI.give_both(host, client, mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    # Aim points the pathfinder has already vouched for, furthest first: a shot
    # at a tile the trajectory code rejects pops in the frame it is pushed and
    # holds nobody's gate.
    probe = PI.intent(host, action="probe_step", unit=mover, radius=4, max=400)
    aims = [(s["x"], s["y"], s["z"]) for s in probe.get("steps", [])][::-1]
    assert aims, f"the shooter has nowhere to aim at: {probe}"

    for attempt in range(8):
        if not PI.wait_until(lambda: parallel(host).get("canAdmit") is True,
                             60, interval=0.05):
            print(f"    attempt {attempt}: the executor never freed up")
            continue
        # ARM first, then fire the shot. `awaitGate` hands the packets to the
        # peer's own main loop, which lands them on the first tick whose gate is
        # shut - so the window cannot be missed by a round trip, however briefly
        # it is open.
        before = len(trace.applied(unit=mover, states=BURST_STATES))
        armed = client.ok({"cmd": "rx_inject", "awaitGate": True,
                           "packets": noop_burst(client, mover)})
        assert armed.get("armed") == 3, f"rx_inject did not arm: {armed}"

        PI.top_up(host, client, mover)
        aim = aims[attempt % len(aims)]
        shot = PI.intent(host, action="shoot", unit=mover, mode="auto",
                         weapon_id=wid, x=aim[0], y=aim[1], z=aim[2])
        if not shot.get("ok"):
            print(f"    attempt {attempt}: the shot lever refused at {aim} "
                  f"({shot.get('error')}) - retrying")
            continue

        inj = None
        deadline = time.time() + 45
        while time.time() < deadline:
            inj = client.ok({"cmd": "rx_inject", "status": True})
            if inj.get("fired"):
                break
            time.sleep(0.05)
        if not inj or not inj.get("fired"):
            print(f"    attempt {attempt}: the peer's gate never shut during "
                  f"the shot, so the burst never landed - retrying")
            continue

        # Read the burst back out of the applied ring.
        seen = []
        deadline = time.time() + 90
        while time.time() < deadline:
            trace.poll(client)
            got = trace.applied(unit=mover, states=BURST_STATES)
            if len(got) >= before + 3:
                seen = got[before:before + 3]
                break
            time.sleep(0.05)
        assert len(seen) == 3, (
            f"the peer applied {len(seen)} of the 3 injected packets - the "
            f"ordering rule starved one of them (inject={inj}, applied="
            f"{[e['state'] for e in seen]})")
        order = [e["state"] for e in seen]
        assert order == BURST_ORDER, (
            f"the peer applied the injected burst as {order}, not "
            f"{BURST_ORDER}: the receive pump reordered a unit's stream against "
            f"itself while the gate held it. inject={inj}")
        print(f"    attempt {attempt}: the burst landed on a tick with the "
              f"gate shut -> peer applied {' '.join(order)}")
        return True
    raise AssertionError(
        "never managed to land the injected burst while the receive gate was "
        "shut - the ordering window never opened, so this assertion is vacuous")


def wait_admit(host, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ph = parallel(host)
        if ph.get("canAdmit") is True and not ph.get("pendingAdmits"):
            return True
        time.sleep(0.05)
    return False


def main():
    fail = None
    host_dir = make_user_dir("p11_order_host",
                             options={"battleXcomSpeed": HOST_SPEED,
                                      "battleAlienSpeed": 2,
                                      "skipNextTurnScreen": True,
                                      "EnableCoopParallelTurns": True})
    client_dir = make_user_dir("p11_order_client",
                               options={"battleXcomSpeed": CLIENT_SPEED,
                                        "battleAlienSpeed": 2,
                                        "EnableCoopParallelTurns": False})
    TI.assert_options_spliced(host_dir, {"battleXcomSpeed": HOST_SPEED})
    TI.assert_options_spliced(client_dir, {"battleXcomSpeed": CLIENT_SPEED})
    host = GameClient("host", 48886, host_dir)
    client = GameClient("client", 48887, client_dir)
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

        mover = PI.pick_driver(host, client, 0, "host")
        # The skew only bites while the walker is ON SCREEN AND VISIBLE:
        # UnitWalkBState runs an off-screen walk at interval 0 whatever the
        # option says, so without this the "slow" peer displays at frame rate and
        # never falls behind at all - and a peer that is never behind never
        # defers a `BattleScapeMove`, which is the whole hazard.
        aim = client.ok({"cmd": "battle_camera", "unit": mover, "visible": True})
        assert aim["onScreen"] and aim["visible"], \
            f"the client cannot actually watch the walker: {aim}"

        PI.top_up(host, client, mover, amount=250)
        trace = Trace()
        trace.poll(client)
        origin = PI.pos(battle(host), mover)

        walked = 0
        for step in range(WALKS):
            assert wait_admit(host), \
                f"walk {step}: the executor never freed up: {parallel(host)}"
            client.cmd({"cmd": "battle_camera", "unit": mover, "visible": True})
            dest = (PI.far_step(host, mover, radius=WALK_RADIUS)
                    or PI.free_step(host, mover))
            if not dest:
                print(f"    (walk {step}: the mover can path nowhere - stopping "
                      f"after {walked} walk(s))")
                break
            seq_before = parallel(host)["actionSeq"]
            r = PI.intent(host, action="move", unit=mover,
                          x=dest[0], y=dest[1], z=dest[2])
            assert r.get("ok"), f"walk {step}: the lever refused: {r}"

            # Poll the peer HARD while the chain runs. Back-to-back walks of the
            # same unit on a lagging peer are exactly the window in which the old
            # pump let `abortPath` overtake its own `BattleScapeMove`, and the
            # ring is only 256 deep.
            deadline = time.time() + 120
            while time.time() < deadline:
                trace.poll(client)
                ph = parallel(host)
                if ph.get("actionSeq", 0) > seq_before and ph.get("canAdmit") is True:
                    break
                time.sleep(0.05)
            if parallel(host)["actionSeq"] > seq_before:
                walked += 1
            bad, moves, aborts = order_violations(
                trace.applied(unit=mover, states=WALK_STATES))
            print(f"    walk {step}: actionSeq {seq_before} -> "
                  f"{parallel(host)['actionSeq']}, peer applied {moves} move(s) "
                  f"/ {aborts} abort(s) for unit {mover}"
                  + (f"  ** {len(bad)} OUT OF ORDER **" if bad else ""))

        assert walked >= 3, (
            f"only {walked} of {WALKS} walks were admitted - the executor was "
            f"blocked, not merely paced: {parallel(host)}")

        injected = scenario_injected_order(host, client, mover, trace)

        # Let the peer finish drawing, sampling all the way.
        for _ in range(60):
            trace.poll(client)
            if (parallel(host)["peerDisplayAckedSeq"]
                    == parallel(host)["actionSeq"]):
                break
            time.sleep(0.5)
        PI.settle(host, client, seconds=6)
        trace.poll(client)

        # ---- 1. ORDER ------------------------------------------------------
        full = trace.applied(unit=mover)
        print("    peer applied, unit %d: %s"
              % (mover, " ".join(e["state"] for e in full)))
        walk_stream = trace.applied(unit=mover, states=WALK_STATES)
        bad, moves, aborts = order_violations(walk_stream)
        assert moves >= 3, (
            f"the peer only applied {moves} walk packet(s) for unit {mover} over "
            f"{walked} walk(s) - the trace is too thin to prove anything "
            f"(gaps seen: {trace.gaps})")
        assert not bad, (
            f"the peer applied {len(bad)} `abortPath` packet(s) for unit {mover} "
            f"BEFORE the `BattleScapeMove` each one closes - the receive pump "
            f"reordered the stream. Applied order was: "
            f"{[(e['seq'], e['state']) for e in walk_stream]}")

        # ---- 2. LIVENESS ---------------------------------------------------
        for gc, tag in ((host, "host"), (client, "client")):
            ps = parallel(gc)
            assert ps.get("rxLegacyPasses", 0) == 0, (
                f"{tag}: the pump's liveness floor fired "
                f"{ps['rxLegacyPasses']}x - per-subject ordering was disabled to "
                f"keep the queue moving, which means something upstream wedged "
                f"the receive gate: {ps}")

        # ---- 3. CONVERGENCE ------------------------------------------------
        hb, cb = battle(host), battle(client)
        assert PI.pos(hb, mover) == PI.pos(cb, mover), (
            f"the two machines disagree about unit {mover} after the run: host "
            f"{PI.pos(hb, mover)} client {PI.pos(cb, mover)}")
        assert PI.pos(hb, mover) != origin, "the mover never actually moved"
        assert not TW.desync_seen(host) and not TW.desync_seen(client), \
            "the PRD-P2 drift tripwire fired during the ordered-pump run"

        pc = parallel(client)
        print(f"PASS: {walked} back-to-back walk(s) of unit {mover} at a "
              f"{HOST_SPEED}:{CLIENT_SPEED} speed skew - the peer applied "
              f"{moves} move / {aborts} abort packet(s) strictly in order "
              f"(ring gaps {trace.gaps}); peer counters: rxRotates "
              f"{pc.get('rxRotates')}, rxSkippedBlocked "
              f"{pc.get('rxSkippedBlocked')}, rxLegacyPasses "
              f"{pc.get('rxLegacyPasses')}, rxHoldMax {pc.get('rxHoldMax')}"
              + ("; the injected burst landed with the gate shut and was "
                 "applied in order" if injected else "; injection phase skipped"))
        if not pc.get("rxSkippedBlocked"):
            print("    NOTE: per-subject blocking never engaged on the peer this "
                  "run - the ordering held, but this particular run did not "
                  "exercise the new hold")
        print("ALL RECEIVE-ORDER TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
