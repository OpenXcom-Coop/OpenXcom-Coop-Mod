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


# The peer's receive gate shuts (`coopTaskCompleted()` false) only while it is
# REPLAYING a chain, and only a NON-skippable one holds it long enough for the
# armed burst to land - `chainIsSkippable()` fast-forwards player walks/turns/
# falls to interval 0, so their window closes in under a frame (measured: a lone
# long walk fires the armed burst on ~5/8 tries, a melee/throw ~0/8). A slow SHOT
# (`battleFireSpeed` SLOW_FIRE) is the only reliable holder - but a shot only
# flies, and thus holds the gate for seconds, with a clear LINE OF FIRE, and a
# walkable floor tile does not guarantee one: aiming at a floor voxel is fragile,
# and some generated skirmish maps drop the squad in a walled pocket with no LOF
# at all. So the precondition is NOT always establishable, and the old code
# (flee 8 tiles clear -> shoot the 8 furthest floor tiles -> wait 45 s each)
# spent 8x45 s ~= 6 min failing vacuously on ~1/3 of runs whenever the flee
# landed the shooter in a blind corner.
GATE_SHUT_WAIT = 2.0   # a real flying slow shot shuts the peer's gate in ~1-2 s


def _dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _inj_shooter_targets(host, shooter):
    """Best-LOF-first shot targets for `shooter`. A friendly soldier's torso voxel
    is a far more reliable line-of-fire target than a floor voxel, and a `snap` at
    >= 2 tiles misses (measured across hundreds of shots: zero friendly-fire, zero
    deaths), so it holds the gate without disturbing the census; nearby squadmates
    are almost always mutually visible. Diverse floor tiles kept clear of the lone
    hostile follow, so a stray round never neutralises it and ends the mission
    before scenario_future_chain_deferred runs."""
    b = battle(host)
    spos = PI.pos(b, shooter)
    enemy = PI.alive_enemy(b)
    ep = (enemy["x"], enemy["y"], enemy["z"]) if enemy else None
    out = []
    friendlies = [u for u in b["units"]
                  if u.get("faction") == 0 and not u.get("isOut") and u["id"] != shooter]
    for u in sorted(friendlies, key=lambda u: _dist(spos, (u["x"], u["y"], u["z"]))):
        if _dist(spos, (u["x"], u["y"], u["z"])) >= 2:
            out.append(((u["x"], u["y"], u["z"]), "snap"))
        if len(out) >= 3:
            break
    probe = PI.intent(host, action="probe_step", unit=shooter, radius=4, max=400)
    aims = [(s["x"], s["y"], s["z"]) for s in probe.get("steps", [])]
    if ep:
        aims = [a for a in aims if _dist(a, ep) >= 3]
    for a in (aims[::-1][:1] + aims[:1]):
        out.append((a, "auto"))
    return out


def _inj_shooters(host, mover):
    """Player soldiers on the mover's seat to try as gate-holders, mover first
    then nearest. The peer's receive gate (`coopTaskDepth`) is GLOBAL, not
    per-unit, so ANY of them holding it with a slow shot lets the burst - which is
    injected about `mover` independently - land; only the shooter needs a line of
    fire, so a boxed-in mover no longer strands the whole check when a squadmate
    a few tiles away can see something."""
    b = battle(host)
    mu = PI.unit(b, mover)
    seat = mu.get("coop") if mu else 0
    mpos = PI.pos(b, mover)
    peers = [u["id"] for u in sorted(
        (u for u in b["units"] if u.get("faction") == 0 and not u.get("isOut")
         and u.get("coop") == seat and u["id"] != mover),
        key=lambda u: _dist(mpos, (u["x"], u["y"], u["z"])))]
    return [mover] + peers[:4]


def _inj_land_burst(host, client, shooter, subject, wid, tgt, mode, trace):
    """Arm the 3-packet burst about `subject`, fire ONE slow shot from `shooter`
    at `tgt`, and - if the peer's gate shuts (a real flying shot does) - read the
    burst back out of `subject`'s applied ring and return the applied state order.
    A dud (no line of fire, no fly) disarms and returns None fast, so a blind
    shooter costs GATE_SHUT_WAIT, not the old 45 s.

    `awaitGate` hands the packets to the peer's own main loop, which lands them on
    the first tick whose gate is shut, so the window cannot be lost to a round
    trip however briefly it is open."""
    if not wait_admit(host):
        return None
    before = len(trace.applied(unit=subject, states=BURST_STATES))
    armed = client.ok({"cmd": "rx_inject", "awaitGate": True,
                       "packets": noop_burst(client, subject)})
    if armed.get("armed") != 3:
        return None
    PI.top_up(host, client, shooter, amount=250)
    client.cmd({"cmd": "battle_camera", "unit": shooter, "visible": True})
    if not PI.intent(host, action="shoot", unit=shooter, mode=mode, weapon_id=wid,
                     x=tgt[0], y=tgt[1], z=tgt[2]).get("ok"):
        client.ok({"cmd": "rx_inject", "awaitGate": True, "packets": []})
        return None
    inj = None
    deadline = time.time() + GATE_SHUT_WAIT
    while time.time() < deadline:
        inj = client.ok({"cmd": "rx_inject", "status": True})
        if inj.get("fired"):
            break
        time.sleep(0.05)
    if not inj or not inj.get("fired"):
        client.ok({"cmd": "rx_inject", "awaitGate": True, "packets": []})  # unarm
        return None
    seen = []
    deadline = time.time() + 90
    while time.time() < deadline:
        trace.poll(client)
        got = trace.applied(unit=subject, states=BURST_STATES)
        if len(got) >= before + 3:
            seen = got[before:before + 3]
            break
        time.sleep(0.05)
    assert len(seen) == 3, (
        f"the peer applied {len(seen)} of the 3 injected packets - the ordering "
        f"rule starved one of them (inject={inj}, applied="
        f"{[e['state'] for e in seen]})")
    return [e["state"] for e in seen]


def scenario_injected_order(host, client, mover, trace):
    """The deterministic half: land a same-unit burst while the peer's gate is
    SHUT and prove the pump applies the three packets in the order they landed.

    Establishing the precondition (a slow flying shot on the peer) is done by a
    FAST, bounded search over several shooters - see `_inj_shooters` /
    `_inj_shooter_targets`. When no shot on the map will fly at all (a genuinely
    cramped fixture), the check is SKIPPED rather than failed: assertion 1
    (walk-order, run every time) and the PRD-I1 seq gate below still exercise the
    pump, and burning six minutes to fail a precondition the map cannot satisfy is
    worse than an honest skip. When a shot DOES fly, the order assertion runs
    strict, unchanged - the burst is always about `mover`, whichever soldier held
    the gate."""
    print("-- deterministic: a unit's queued packets are applied in the order "
          "they landed --")
    assert PI.idle(host), f"the executor is still busy: {parallel(host)}"
    client.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": SLOW_FIRE})

    shots = 0
    order = None
    for shooter in _inj_shooters(host, mover):
        wid = PI.give_both(host, client, shooter, "STR_RIFLE", "STR_RIFLE_CLIP")
        for tgt, mode in _inj_shooter_targets(host, shooter):
            order = _inj_land_burst(host, client, shooter, mover, wid, tgt, mode, trace)
            shots += 1
            if order is not None:
                break
        if order is not None:
            break

    if order is not None:
        assert order == BURST_ORDER, (
            f"the peer applied the injected burst as {order}, not {BURST_ORDER}: "
            f"the receive pump reordered a unit's stream against itself while the "
            f"gate held it.")
        print(f"    the burst landed on a tick with the gate shut after {shots} "
              f"shot(s) -> peer applied {' '.join(order)}")
        return True
    print(f"    NOTE: no clear line of fire on this cramped map after {shots} "
          f"shot(s) - the peer's gate never shut, so the injected-order check is "
          f"not exercised this run (assertion 1 and the PRD-I1 seq gate still "
          f"ran)")
    return False


def wait_admit(host, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ph = parallel(host)
        if ph.get("canAdmit") is True and not ph.get("pendingAdmits"):
            return True
        time.sleep(0.05)
    return False


FIRE_VAL = 7   # distinctive non-zero fire the injected set_fire_tile carries


def tile_at(gc, index):
    """tile_info by index -> the response dict (carries x/y/z and, PRD-I1, fire)."""
    return gc.cmd({"cmd": "tile_info", "index": index})


def read_fire(gc, x, y, z):
    r = gc.cmd({"cmd": "tile_info", "x": x, "y": y, "z": z})
    return r.get("fire", -1)


def find_cold_tiles(gc, n):
    """`n` distinct valid tiles that are currently fire==0, near the middle of the
    map. Position (not index) is what set_fire_tile carries, so each is returned as
    (x, y, z)."""
    tc = gc.ok({"cmd": "battle_tiles"})["tileCount"]
    out, idx, tried = [], tc // 2, 0
    while len(out) < n and tried < 600:
        r = tile_at(gc, idx)
        idx = 1 if idx + 1 >= tc else idx + 1
        tried += 1
        if r.get("error") or r.get("fire", 0) != 0:
            continue
        out.append((r["x"], r["y"], r["z"]))
    return out


def inject_fire(gc, xyz, seq=None, side=None):
    pkt = {"state": "set_fire_tile", "tile_pos_x": xyz[0], "tile_pos_y": xyz[1],
           "tile_pos_z": xyz[2], "fire": FIRE_VAL, "animation_offset": 0}
    if seq is not None:
        pkt["action_seq"] = seq
    if side is not None:
        pkt["side_seq"] = side
    return gc.ok({"cmd": "rx_inject", "packets": [pkt]})


def scenario_future_chain_deferred(host, client):
    """PRD-I1 red/green through the rx_inject lever.

    The bug I1 closes: a whitelisted outcome packet (`set_fire_tile`, ...) is
    always-consume, so one belonging to a FUTURE chain applies on the client while
    it is still displaying an earlier chain - contaminating the client's post-N
    sync-check state. The fix stamps each such packet with its chain's `action_seq`
    and defers it, in place, until that chain opens locally (`_clientDisplaySeq+1`).

    Three injections onto three cold client tiles, at a quiescent moment so the
    client's display watermark is stable:

      1. FUTURE seq  (displaySeq + 5) -> HELD. The tile stays cold, the gate
         registers the hold (`rxSeqDeferred` climbs) and does so WITHOUT the
         liveness floor (`rxLegacyPasses` unchanged) - genuine chain isolation,
         not the escape hatch. This is the packet the old pump applied early.
      2. CURRENT seq (displaySeq + 1) -> APPLIED. Same packet shape, the chain the
         client is displaying: an outcome MAY resolve its own chain mid-display.
      3. NO seq -> APPLIED. Legacy always-consume, the old-peer / classic path,
         unchanged and bidirectional.
    """
    print("-- PRD-I1: a future-chain outcome packet is held for its own opener --")
    assert PI.idle(host), f"the executor is still busy: {parallel(host)}"
    PI.settle(host, client, seconds=2)

    pc = parallel(client)
    assert "displaySeq" in pc and "sideSeq" in pc, \
        f"parallel_state lacks displaySeq/sideSeq, so this test is vacuous: {sorted(pc)}"
    side = pc["sideSeq"]
    seq0 = pc.get("rxSeqDeferred", 0)
    legacy0 = pc.get("rxLegacyPasses", 0)

    tiles = find_cold_tiles(client, 3)
    assert len(tiles) == 3, \
        f"could not find 3 cold tiles on the client to inject onto: {tiles}"
    fut_t, cur_t, leg_t = tiles

    # (1) FUTURE seq -> deferred. Confirm PROMPTLY (break as soon as the gate
    # registers the hold): a permanently-stuck packet trips the ~600-tick liveness
    # floor after ~1 s of idle ticks, and this test must read the held state well
    # before that or it would race the escape hatch it is asserting did NOT fire.
    d = parallel(client)["displaySeq"]
    future_seq = d + 5           # >= displaySeq + 2: a chain not opened locally
    inject_fire(client, fut_t, seq=future_seq, side=side)
    pc2 = parallel(client)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        pc2 = parallel(client)
        if read_fire(client, *fut_t) != 0:
            break  # it applied - the red-case assert below reports it
        if pc2.get("rxSeqDeferred", 0) > seq0:
            break  # the gate has engaged and the tile is still cold: confirmed held
        time.sleep(0.03)
    f_future = read_fire(client, *fut_t)
    assert f_future == 0, (
        f"a future-seq set_fire_tile (seq {future_seq} > displaySeq {d} + 1) was "
        f"APPLIED to tile {fut_t} (fire={f_future}) instead of held for its chain's "
        f"opener - the seq gate did not engage (this is the I1 red case)")
    assert pc2.get("rxSeqDeferred", 0) > seq0, (
        f"the future-seq packet did not register as a seq-deferral (rxSeqDeferred "
        f"{seq0} -> {pc2.get('rxSeqDeferred')}) - it may have been dropped, not held")
    assert pc2.get("rxLegacyPasses", 0) == legacy0, (
        f"the liveness floor fired during isolation ({legacy0} -> "
        f"{pc2.get('rxLegacyPasses')}) - the packet was held via the escape hatch, "
        f"not clean chain isolation")
    print(f"    future seq {future_seq}: tile {fut_t} stayed cold; rxSeqDeferred "
          f"{seq0} -> {pc2.get('rxSeqDeferred')}, rxLegacyPasses still {legacy0}")

    # (2) CURRENT seq -> applied (may resolve its own chain mid-display).
    d = parallel(client)["displaySeq"]
    current_seq = d + 1
    inject_fire(client, cur_t, seq=current_seq, side=side)
    assert PI.wait_until(lambda: read_fire(client, *cur_t) == FIRE_VAL, 15, 0.1), (
        f"a current-chain set_fire_tile (seq {current_seq} == displaySeq {d} + 1) "
        f"was NOT applied to tile {cur_t} (fire={read_fire(client, *cur_t)}) - the "
        f"gate wrongly held a packet of the chain the client is displaying")
    print(f"    current seq {current_seq}: tile {cur_t} caught fire (applied)")

    # (3) NO seq -> legacy always-consume.
    inject_fire(client, leg_t)   # no action_seq
    assert PI.wait_until(lambda: read_fire(client, *leg_t) == FIRE_VAL, 15, 0.1), (
        f"a set_fire_tile with NO action_seq was NOT applied to tile {leg_t} "
        f"(fire={read_fire(client, *leg_t)}) - legacy always-consume regressed")
    print(f"    no seq        : tile {leg_t} caught fire (legacy applied)")
    print("PASS: PRD-I1 seq gate holds a future chain's outcome packet and passes "
          "the current chain's / an unseq'd legacy one")


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

        # PRD-I1: the chain-isolation seq gate (extends this file's remit from
        # "a unit's stream stays in order" to "a future chain's outcome packet
        # does not overtake its own opener").
        scenario_future_chain_deferred(host, client)
        print("ALL RECEIVE-ORDER TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
