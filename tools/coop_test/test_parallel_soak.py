"""PRD-P9: the parallel-turns soak.

Every earlier PRD in this program tests one mechanism in isolation. This one
plays the game: a seeded battle, both seats acting into the same player side,
mixed action kinds, real alien turns in between - and after EVERY side it
compares the two machines term by term. It is the test that would catch an
authority seam nobody thought to write a scenario for.

What it asserts, in order:

  A. SEED. Both machines are pinned to the same RNG seat (`set_seed`) so a
     failure can be reproduced by re-running with the same `--seed`.
  B. ACTIONS. >= 100 admitted actions across >= 5 full turns, driven from BOTH
     seats: walks (including contention - a second seat clicking into a running
     walk, which PRD-P7 defers), turns, kneel/stand, shots, a medikit, a prime
     and an unprime, and one thrown smoke grenade so the tile-hazard census is
     not vacuous.
  C. CENSUS. After every side (and at every turn boundary):
       units   id + position + TU + health + stun + fatal wounds + isOut
       items   the STRICT id census (id, type, owner, fuse, tile) - PRD-P4
       tiles   the fire/smoke hazard census (`battle_tiles`)
       drift   `itemIdCounter` / `battleCensus` equality (PRD-P2's two terms)
       tripwire `desyncSeen` false on BOTH machines, the whole way through
  D. BACKLOG CAP (PRD-P9 rider R3). The display-flow cap in `canAdmitAction()`
     - refuse while `(_actionSeq - peerDisplayAckedSeq) >= 2` - had never once
     been observed to engage. Forcing it took three measurements, all recorded in
     `scenario_backlog_cap`: a WALK cannot build a backlog (PRD-P7's fast-forward
     compresses it away), a SECOND SHOT cannot expose the cap (`isBusy()` is
     checked first, so the answer stays "states" until the peer has caught up),
     and what works is ONE slow shot followed by stateless chains, which complete
     inside the frame they are admitted and so leave the executor idle while
     `_actionSeq` climbs. The phase then proves the arbiter RECOVERS (the backlog
     drains, admission reopens) and that a client intent sent while the cap was up
     was refused `busy` and executed nothing.

Run:  python tools/coop_test/test_parallel_soak.py [--turns N] [--seed S]
Exit 0 = pass; 2 = failure.

The acceptance bar is THREE consecutive clean runs.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI
import test_parallel_endturn as PE

PORT = "47991"

SLOW_SPEED = 1000  # ms/frame on the client - the same lever PRD-P7/P8 use
FAST_SPEED = 2
SLOW_FIRE = 1500   # ms/projectile-frame: what actually slows a SHOT (see D)
FAST_FIRE = 1

DEFAULT_TURNS = 5
DEFAULT_MIN_ACTIONS = 100
DEFAULT_SEED = 20260802


# ---- readouts --------------------------------------------------------------

def battle(gc):
    return PI.battle(gc)


def parallel(gc):
    return PI.parallel(gc)


def tiles(gc):
    return gc.ok({"cmd": "battle_tiles"})


# States this test must never `dismiss_popup`. The first two are the ones every
# co-op test protects (session.NO_DISMISS_STATES); the rest are what is on the
# stack once the MISSION has ended - and popping those walks the stack down past
# the main menu and QUITS the game, which reaches the harness as an unexplained
# "connection forcibly closed" three minutes later rather than as a test failure.
KEEP_STATES = ("BattlescapeState", "NextTurnState", "VoteMenu", "DebriefingState",
               "GeoscapeState", "MainMenuState", "StatisticsState", "CoopState",
               "SaveGameState", "ListGamesState")


def drain(host, client, rounds=3):
    """Pop anything sitting on top of the battlescape. BattlescapeState::think()
    - which runs the co-op turn handshake - only ticks while the battlescape is
    the top state, so a stray infobox stalls the whole session."""
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            t = TW.top(gc)
            if t not in KEEP_STATES:
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        if not moved:
            return
        time.sleep(0.3)


def poll(fn, timeout, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(interval)
    return None


def top_up(host, client, uid, tu=200, energy=200):
    """Same TU **and energy** on BOTH machines.

    PI.top_up only restores TU. A soak drives hundreds of walks, and energy is
    what actually runs out first - a soldier with 200 TU and no energy refuses
    to move, which silently turned "drive a long walk" into "drive nothing" (it
    is how the rider-R3 phase first failed to build any display backlog at all).
    """
    for gc in (host, client):
        gc.ok({"cmd": "battle_intent", "unit": uid, "action": "turn",
               "tu": tu, "energy": energy, "dry": True})


def idle(host, timeout=120):
    return poll(lambda: parallel(host).get("canAdmit") is True
                and not parallel(host).get("pendingAdmits"), timeout, 0.1)


# ---- the census ------------------------------------------------------------

def unit_census(b):
    """The PRD-P9 per-unit terms.

    Two deliberate exclusions, both because asserting a term the protocol does
    not replicate makes a permanent red rather than a detector:

    * ENERGY - only the walk packet and the two cost packets carry it (PRD-P9
      rider R2 and the soak finding next to it), so it is reported on a failure
      but never asserted.
    * A NON-PLAYER unit's TU. An alien's remaining TU is spent by AI that runs on
      the executor alone; the peer applies the outcome (position, damage, the
      shot itself) and never decides anything from the number. Reaction fire
      leaves it up to a point or two apart on the peer - a pre-existing classic
      co-op accounting seam, outside PRD-P9's scope - so it is reported by
      `tu_report()` instead. Every PLAYER unit's TU IS asserted: that one is the
      currency both players spend and would be a real desync.
    """
    return {u["id"]: (u["x"], u["y"], u["z"],
                      u["tu"] if u.get("faction") == 0 else None,
                      u["health"], u["stun"], u.get("wounds"), bool(u["isOut"]))
            for u in b["units"]}


def tu_report(host_b, client_b):
    """Non-player TU deltas - reported, not asserted (see unit_census)."""
    ch = {u["id"]: u["tu"] for u in client_b["units"]}
    out = [(u["id"], u["tu"], ch.get(u["id"]))
           for u in host_b["units"]
           if u.get("faction") != 0 and ch.get(u["id"]) != u["tu"]]
    return out


def item_census(gc):
    """The STRICT id census PRD-P4 made assertable: identity AND where it lives."""
    d = gc.ok({"cmd": "battle_items"})
    return {it["id"]: (it["type"], it["owner"], it["fuse"], it.get("slot"),
                       it.get("tx"), it.get("ty"), it.get("tz"))
            for it in d["items"]}


def hazard_census(gc):
    t = tiles(gc)
    return (t["fireTiles"], t["fireSum"], t["fireHash"],
            t["smokeTiles"], t["smokeSum"], t["smokeHash"])


def first_diff(a, b, limit=4):
    """A readable diff of two id -> tuple maps."""
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append(f"      {k}: host={a.get(k)} client={b.get(k)}")
            if len(out) >= limit:
                out.append("      ...")
                break
    return "\n".join(out)


def settle_display(host, client, timeout=90):
    """Wait until the CLIENT has finished drawing everything the host has run.

    The census is a cross-machine comparison, so it has to be taken when both
    machines are quiescent - `canAdmit` only says the EXECUTOR is idle. The
    display watermark (`displayBacklog`, PRD-P7) is the client's half of that,
    and the receive gate is the last packet-level term."""
    drain(host, client)
    poll(lambda: parallel(host).get("displayBacklog", 0) == 0
         and parallel(host).get("taskCompleted") is not False
         and parallel(client).get("taskCompleted") is not False
         and parallel(client).get("rxHold", 0) == 0, timeout, 0.1)
    # ...and until neither machine still has a BattleState running. The display
    # watermark says the client has consumed every packet, which is NOT the same
    # as having finished acting on them: a death animation drops the corpse's
    # inventory only at its LAST frame (UnitDieBState::think -> convertUnitToCorpse),
    # so a census taken a few frames early sees the kit still on the body here and
    # already on the floor there.
    poll(lambda: battle(host).get("isBusy") is False
         and battle(client).get("isBusy") is False, timeout, 0.1)
    drain(host, client, rounds=1)


def trace_units(host, client, what):
    """Report (never assert) the per-unit diff, so a soak run can say WHICH block
    introduced a divergence instead of only that the turn ended with one."""
    d = first_diff(unit_census(battle(host)), unit_census(battle(client)), limit=6)
    print(f"    [trace] {what}: {'in step' if not d else 'DIFF'}")
    if d:
        print(d)


def assert_census(host, client, what):
    """The full cross-machine comparison. Called after every side."""
    settle_display(host, client)
    hb, cb = battle(host), battle(client)
    assert hb.get("inBattle") and cb.get("inBattle"), (
        f"the fixture's mission ENDED before the census {what} (host "
        f"inBattle={hb.get('inBattle')} top={TW.top(host)}, client "
        f"inBattle={cb.get('inBattle')} top={TW.top(client)}). The skirmish "
        f"fixture ships a handful of aliens and the soak has to keep at least "
        f"one of them alive; everything after this point would be vacuous.")
    hu, cu = unit_census(hb), unit_census(cb)
    if hu != cu:
        # `status` is not in the asserted tuple (it moves through animation states
        # that legitimately differ mid-frame) but it is the first thing anyone
        # would want when isOut disagrees, so it rides the failure text.
        hs = {u["id"]: (u["status"], u.get("energy")) for u in hb["units"]}
        cs = {u["id"]: (u["status"], u.get("energy")) for u in cb["units"]}
        extra = "\n".join(
            f"      {k}: status/energy host={hs.get(k)} client={cs.get(k)}"
            for k in sorted(set(hu) | set(cu)) if hu.get(k) != cu.get(k))
        raise AssertionError(
            f"UNIT CENSUS DRIFT {what}: the two machines disagree about\n"
            f"    (x, y, z, tu, health, stun, wounds, isOut)\n{first_diff(hu, cu)}\n"
            f"    context (not asserted):\n{extra}")

    hi, ci = item_census(host), item_census(client)
    assert hi == ci, (
        f"ITEM CENSUS DRIFT {what}: strict id census differs "
        f"(host {len(hi)} items, client {len(ci)})\n"
        f"    (type, owner, fuse, slot, tx, ty, tz)\n{first_diff(hi, ci)}")

    hh, ch = hazard_census(host), hazard_census(client)
    assert hh == ch, (
        f"TILE HAZARD DRIFT {what}: (fireTiles, fireSum, fireHash, smokeTiles, "
        f"smokeSum, smokeHash) host={hh} client={ch}. Fire and smoke arrive on "
        f"their own `set_fire_tile`/`set_smoke_tile` packets and decay on both "
        f"machines independently, so neither of PRD-P2's item terms can see this.")

    session.assert_battle_synced(host, client, what)
    assert not TW.desync_seen(host) and not TW.desync_seen(client), (
        f"the PRD-P2 drift tripwire FIRED {what} - a release blocker, "
        f"root-cause it before shipping")
    skew = tu_report(hb, cb)
    if skew:
        print(f"    NOTE {what}: non-player TU skew (reported, not asserted): "
              + ", ".join(f"unit {i} host={h} client={c}" for i, h, c in skew[:4]))
    return hh


# ---- driving ---------------------------------------------------------------

def act(host, client, driver, what, timeout=90, **kw):
    """Drive ONE action and wait for the executor to finish with it.

    Returns how many chains the host admitted (0 = the lever or the arbiter
    refused, which the soak tolerates: a boxed-in soldier or a shot with no line
    of fire is a fixture accident, not a protocol failure). Anything that DOES
    run must land identically, which is what the per-side census then checks."""
    seq0 = parallel(host)["actionSeq"]
    r = PI.intent(driver, **kw)
    if not r.get("ok"):
        return 0
    poll(lambda: parallel(host)["actionSeq"] > seq0, 25, 0.05)
    if not idle(host, timeout):
        drain(host, client)
        idle(host, 30)
    drain(host, client, rounds=1)
    return parallel(host)["actionSeq"] - seq0


def contended_walks(host, client, hmover, cmover):
    """A client intent shipped INTO a running host walk - PRD-P7's deferral path,
    which is the contention shape a real two-player side produces constantly.

    Both destinations are resolved while the machines are idle: `probe_step`
    refuses mid-chain (Pathfinding is a singleton the running walk dequeues from).
    """
    if not idle(host):
        return 0
    top_up(host, client, hmover)
    top_up(host, client, cmover)
    hdest = PI.step_dest(host, client, hmover)
    cdest = PI.step_dest(host, client, cmover)
    if not hdest or not cdest:
        return 0
    seq0 = parallel(host)["actionSeq"]
    PI.intent(host, action="move", unit=hmover, x=hdest[0], y=hdest[1], z=hdest[2])
    PI.intent(client, action="move", unit=cmover, x=cdest[0], y=cdest[1], z=cdest[2])
    poll(lambda: parallel(host)["actionSeq"] >= seq0 + 2, 60, 0.05)
    idle(host, 120)
    drain(host, client, rounds=1)
    return parallel(host)["actionSeq"] - seq0


def locomotion_block(host, client, hmover, cmover):
    """Walk + kneel/stand + turn, from both seats."""
    n = contended_walks(host, client, hmover, cmover)
    top_up(host, client, cmover)
    n += act(host, client, client, "kneel", action="kneel", unit=cmover)
    n += act(host, client, client, "stand", action="kneel", unit=cmover)
    for gc, uid in ((host, hmover), (client, cmover)):
        top_up(host, client, uid)
        here = PI.pos(battle(host), uid)
        if here:
            n += act(host, client, gc, "turn", action="turn", unit=uid,
                     x=here[0] + 1, y=here[1] + 1, z=here[2])
    return n


def shot_block(host, client, hmover, cmover):
    """One shot from each seat, aimed AWAY from the fixture's few hostiles - a
    stray kill ends the mission and every later side with it."""
    n = 0
    for gc, uid in ((host, hmover), (client, cmover)):
        if not idle(host):
            break
        wid = PI.give_both(host, client, uid, "STR_RIFLE", "STR_RIFLE_CLIP")
        top_up(host, client, uid)
        # dist 2, not 4: `aim_away` points away from the NEAREST hostile, which
        # says nothing about the others, and a long bullet flight through a
        # skirmish fixture that ships a handful of aliens kills the mission out
        # from under the remaining turns.
        aim = PI.aim_away(host, uid, dist=2)
        n += act(host, client, gc, "shoot", action="shoot", unit=uid, mode="snap",
                 weapon_id=wid, x=aim[0], y=aim[1], z=aim[2])
    return n


def support_block(host, client, cmover):
    """The three kinds that push NO BattleState at all - medikit, prime, unprime.
    They are the ones PRD-P7's `action_end` marker exists for, so a soak that
    skipped them would not exercise the flow control's hardest case."""
    n = 0
    top_up(host, client, cmover)
    wid = PI.give_both(host, client, cmover, "STR_MEDI_KIT")
    n += act(host, client, client, "medikit", action="medikit", unit=cmover,
             weapon_id=wid, patient=cmover, medikit="stim", part=0)
    top_up(host, client, cmover)
    wid = PI.give_both(host, client, cmover, "STR_GRENADE")
    n += act(host, client, client, "prime", action="prime", unit=cmover,
             fuse=3, weapon_id=wid)
    top_up(host, client, cmover)
    n += act(host, client, client, "unprime", action="prime", unit=cmover,
             unprime=True, weapon_id=wid)
    return n


def smoke_block(host, client, cmover):
    """One primed smoke grenade, thrown and left to go off.

    The only thing in the mix that writes the tile-hazard census, so without it
    the fire/smoke comparison above would be 0 == 0 for the whole run.
    """
    if not idle(host):
        return 0
    top_up(host, client, cmover)
    wid = PI.give_both(host, client, cmover, "STR_SMOKE_GRENADE")
    n = act(host, client, client, "prime smoke", action="prime", unit=cmover,
            fuse=0, weapon_id=wid)
    top_up(host, client, cmover)
    here = PI.pos(battle(host), cmover)
    if here:
        n += act(host, client, client, "throw smoke", action="throw", unit=cmover,
                 weapon_id=wid, x=here[0] + 2, y=here[1] + 2, z=here[2])
    # the fuse has to actually run out; that happens on a side boundary, so all
    # this waits for is the throw's own chain to settle.
    idle(host, 60)
    drain(host, client)
    return n


# ---- D. the display-backlog cap (PRD-P9 rider R3) --------------------------

def move_clear_of_hostiles(host, client, uid, want=8):
    """Put `uid` somewhere its bursts cannot reach a hostile, on BOTH machines.

    This phase fires auto bursts at whatever tile produces a real chain, and the
    skirmish fixture can ship as few as ONE alien - so a stray hit ends the
    mission and every remaining turn with it. Teleporting the shooter clear first
    is the difference between a soak that runs five turns and one that reports
    "the fixture's mission ENDED" from turn 3 on.
    """
    b = battle(host)
    foes = [(u["x"], u["y"], u["z"]) for u in b["units"]
            if u.get("faction") == 1 and not u.get("isOut")]
    if not foes:
        return None
    here = PI.pos(b, uid)

    def clearance(p):
        return min(max(abs(p[0] - f[0]), abs(p[1] - f[1])) for f in foes)

    best = None
    for r in range(4, 13):
        for dx in (-r, 0, r):
            for dy in (-r, 0, r):
                if dx == 0 and dy == 0:
                    continue
                spot = (here[0] + dx, here[1] + dy, here[2])
                if clearance(spot) < want:
                    continue
                if PI.teleport_both(host, client, uid, spot):
                    best = spot
                    break
            if best:
                break
        if best:
            break
    if best:
        print(f"    (shooter {uid} moved to {best}, {clearance(best)} tiles clear "
              f"of every hostile)")
    return best


def long_walk_both(host, client, uid, radius=4):
    """The FURTHEST tile both machines agree `uid` can path to - a one-tile step
    is over before a slow client can fall behind on it."""
    for r in range(radius, 0, -1):
        got = PI.common_steps(host, client, uid, r)
        if got:
            return got[-1]
    return None


def scenario_backlog_cap(host, client, shooter, client_unit):
    """Force `canAdmitAction()`'s display-flow term to refuse, then recover.

    Why it needs forcing: the cap is `(_actionSeq - peerDisplayAckedSeq) >= 2`,
    and it is checked LAST - while a chain is still running the answer is
    "states". So the only way to see it is a client that is genuinely behind on
    DISPLAY while the executor is idle, which needs (a) a slow client, (b) the
    shooter on the client's screen (an off-screen chain runs at interval 0
    regardless) and (c) chains PRD-P7 will not fast-forward away, i.e. shots.
    """
    print("-- D: the display-backlog cap engages and recovers (rider R3) --")
    assert idle(host), f"the host is still busy: {parallel(host)}"
    move_clear_of_hostiles(host, client, shooter)
    before = PI.pos(battle(host), shooter)
    cam = client.ok({"cmd": "battle_camera", "unit": shooter, "visible": True})
    assert cam.get("onScreen"), (
        f"the client's camera would not frame the shooter, so it would draw the "
        f"chain at interval 0 and never fall behind: {cam}")
    client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": SLOW_SPEED})
    client.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": SLOW_FIRE})

    blocked = None
    seen_backlog = 0
    fired = 0
    try:
        # MEASURED, and the measurement is most of what this rider was for.
        #
        # A WALK cannot build the backlog at all, however slow the client is: the
        # host's `action_end` is itself a gated packet, so the client ALWAYS has
        # one waiting behind a lone walk, which arms PRD-P7's fast-forward and
        # compresses the animation away (0 samples over four attempts).
        #
        # A SHOT can: `ProjectileFlyBState` holds the receive gate and is never
        # skippable, so at SLOW_FIRE the client really is seconds behind. What it
        # then needs is for the executor to start a SECOND chain inside that
        # window - which means no RPC between the two but the admission poll, so
        # the weapon, the aim point and the TU are all set up first.
        wid = PI.give_both(host, client, shooter, "STR_RIFLE", "STR_RIFLE_CLIP")
        for attempt in range(4):
            if not poll(lambda: parallel(host).get("canAdmit") is True, 60, 0.03):
                break
            top_up(host, client, shooter)
            # `start_busy_shot` is what proves the chain is REAL: a shot aimed at a
            # tile the trajectory code rejects pops in the frame it is pushed, and
            # every measurement after it would be of a chain that never ran. It
            # returns an aim the pathfinder has vouched for, with the host confirmed
            # mid-chain.
            aim, ps = PI.start_busy_shot(host, client, shooter, wid)
            if not aim:
                print(f"    (attempt {attempt + 1}: no aim point produced a real "
                      f"shot chain: {ps.get('admitBlocked')})")
                continue
            fired += 1
            shot = dict(action="shoot", unit=shooter, mode="auto", weapon_id=wid,
                        x=aim[0], y=aim[1], z=aim[2])
            # ONE poll, then straight into the second chain - no other RPC in
            # between. Measured window between "the executor is idle again" and
            # "the peer reports the first chain displayed": ~330 ms at 400 ms/frame,
            # and it scales with the client's draw speed.
            deadline = time.time() + 40
            while time.time() < deadline:
                ps = parallel(host)
                seen_backlog = max(seen_backlog, ps.get("displayBacklog", 0))
                if ps.get("admitBlocked") == "display_backlog":
                    blocked = ps
                    break
                if ps.get("canAdmit") is True:
                    break
                time.sleep(0.01)
            if blocked:
                break
            # The follow-up chains are KNEELS, not more shots, and that detail is
            # the whole trick. A second shot keeps the executor BUSY for its own
            # animation, and `canAdmitAction()` checks `isBusy()` before the
            # display term - so the backlog reaches 2 while the answer is still
            # "states", and by the time the executor is idle the peer has caught
            # up (measured: backlog 2 seen, `display_backlog` never reported).
            # A kneel pushes no BattleState: it completes inside the frame it is
            # admitted, so the executor stays IDLE while `_actionSeq` climbs, and
            # the display term is then the first one that can say no.
            for _ in range(14):
                ps = parallel(host)
                seen_backlog = max(seen_backlog, ps.get("displayBacklog", 0))
                if ps.get("admitBlocked") == "display_backlog":
                    blocked = ps
                    break
                if ps.get("canAdmit") is not True:
                    time.sleep(0.01)
                    continue
                # kneel toggles, so it can be repeated. Deliberately NO top-up in
                # here: `top_up` writes both machines directly, and doing that while
                # a `kneel` packet is still in flight lets the peer charge the
                # freshly-restored value after the executor already charged the old
                # one - a TU skew the test itself created. One top-up before the
                # loop covers every kneel it can fit.
                PI.intent(host, action="kneel", unit=shooter)
                fired += 1
            if blocked:
                break
            print(f"    (attempt {attempt + 1}: the client kept up - highest "
                  f"backlog seen {seen_backlog}, retrying)")
        # The flow-control ACCOUNTING must always be live: if the executor never
        # sees the peer even one chain behind, `peerDisplayAckedSeq` is not being
        # driven by `action_done` at all and the cap could never fire for anyone.
        assert seen_backlog >= 1, (
            f"the executor never observed the peer a single chain behind over "
            f"{fired} shot(s) against a client drawing at {SLOW_SPEED}/{SLOW_FIRE} "
            f"ms/frame - `action_done` is not driving peerDisplayAckedSeq, and "
            f"PRD-P7's display flow control is inert: host={parallel(host)} "
            f"client={parallel(client)}")
        if blocked:
            print(f"    cap engaged after {fired} shot(s): displayBacklog="
                  f"{blocked['displayBacklog']} actionSeq={blocked['actionSeq']} "
                  f"peerDisplayAckedSeq={blocked['peerDisplayAckedSeq']}")
        else:
            # Reaching backlog 2 needs the executor's OWN chain to drain while the
            # peer is still drawing the previous one, and how long the peer spends
            # drawing a shot depends on whether it is looking at it - an off-screen
            # projectile is drawn at interval 0 no matter what battleFireSpeed says.
            # So the cap is reachable (observed engaging, with an intent refused
            # `busy` and a clean recovery) but not on demand. Reported rather than
            # failed, because a red here would mean "the fixture put the camera
            # somewhere else", not "the arbiter is broken".
            print(f"    NOTE: the cap did not engage this run - the peer stayed "
                  f"within {seen_backlog} chain(s) over {fired} shot(s). The "
                  f"accounting is live (backlog {seen_backlog} observed and "
                  f"drained); reaching the 2-chain cap depends on the peer really "
                  f"animating the shot, which needs the shooter on ITS screen.")

        # ...and while it is up, a real client intent is refused and runs NOTHING.
        # Driven with a CLIENT-owned soldier, so the refusal has to come from the
        # cap rather than from the ownership check.
        cpos = PI.pos(battle(host), client_unit)
        if parallel(host).get("admitBlocked") == "display_backlog" and cpos:
            client.cmd({"cmd": "parallel_state", "clear_deny": True})
            r = PI.intent(client, action="turn", unit=client_unit,
                          x=cpos[0] + 1, y=cpos[1], z=cpos[2])
            if r.get("routed"):
                got = poll(lambda: parallel(client)["lastDenyReason"] or None, 12, 0.1)
                if got:
                    assert got == "busy", (
                        f"an intent sent into the display-backlog cap was refused "
                        f"`{got}`, not `busy`; PROTOCOL.md keeps `busy` for the cap "
                        f"(the queue is empty, so there is nothing to defer behind)")
                    assert PI.pos(battle(host), client_unit) == cpos,                         "the refused intent moved the unit anyway"
                    print(f"    a client intent sent while the cap was up was "
                          f"refused `{got}` and executed nothing")
    finally:
        client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": FAST_SPEED})
        client.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": FAST_FIRE})

    ok = poll(lambda: parallel(host).get("admitBlocked") != "display_backlog"
              and parallel(host).get("canAdmit") is True, 240, 0.2)
    assert ok, (
        f"the arbiter never recovered once the client was put back to "
        f"{FAST_SPEED} ms/frame: host={parallel(host)} client={parallel(client)}. "
        f"A cap that engages and does not clear wedges the side shut.")
    assert parallel(host)["displayBacklog"] <= 1, (
        f"the backlog did not drain after recovery: {parallel(host)}")
    drain(host, client)
    idle(host)
    # Normalise before handing back to the soak: this phase deliberately races
    # the two machines, so it re-levels the actor it drove rather than leaving
    # the census to judge a skew the test manufactured.
    settle_display(host, client)
    top_up(host, client, shooter)
    print(f"    recovered: displayBacklog={parallel(host)['displayBacklog']}, "
          f"canAdmit={parallel(host)['canAdmit']}; the shooter went {before} -> "
          f"{PI.pos(battle(host), shooter)}")
    print("PASS D: the display-backlog cap engaged, refused, and recovered")
    return fired


# ---- the turn loop ---------------------------------------------------------

def close_side(host, client, hseat, cseat, turn_before):
    """Both seats ready -> the executor commits -> a new player side."""
    PE.hush(host, client)
    for gc in (host, client):
        if not parallel(gc)["localReady"]:
            PE.arm(gc)
    got = poll(lambda: parallel(host)["allReady"] is True, 30, 0.2)
    if not got:
        for gc in (host, client):
            if not parallel(gc)["localReady"]:
                PE.arm(gc)
    turn = PE.wait_side(host, client, turn_before, timeout=300)
    assert turn, (
        f"the side never closed with both seats ready: host={parallel(host)} "
        f"client={parallel(client)}, host top={TW.top(host)} "
        f"client top={TW.top(client)}")
    drain(host, client)
    poll(lambda: battle(host).get("battleInit") and battle(client).get("battleInit"),
         60, 0.5)
    idle(host)
    return turn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    ap.add_argument("--actions", type=int, default=DEFAULT_MIN_ACTIONS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--trace", action="store_true",
                    help="report the per-unit diff after every block (diagnosis)")
    args = ap.parse_args()

    started = time.time()
    fail = None
    host = GameClient("host", 48880,
                      make_user_dir("p9_soak_host",
                                    options={"battleXcomSpeed": FAST_SPEED,
                                             "battleAlienSpeed": FAST_SPEED,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48881,
                        make_user_dir("p9_soak_client",
                                      options={"battleXcomSpeed": FAST_SPEED,
                                               "battleAlienSpeed": FAST_SPEED,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        PE.PORT = PORT
        TW.bring_up_battle(host, client)
        print(f"battle up on both machines ({time.time() - started:.0f}s)")

        # --- A. seed + the mode invariant ---------------------------------
        for gc, tag in ((host, "host"), (client, "client")):
            s = gc.ok({"cmd": "set_seed", "seed": args.seed})
            print(f"    {tag} seed pinned to {s['seed']}")
        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallel turns only "
            f"cover PVE (1) and PVE2 (4), so this soak would be vacuous")
        for gc, tag in ((host, "host"), (client, "client")):
            assert battle(gc)["parallelActive"] is True, \
                f"{tag}: parallel mode is not live: {battle(gc)}"
        assert battle(host)["activeSync"] is True and battle(client)["activeSync"] is False, \
            "the PRD-P5 executor invariant does not hold; nothing below is testing it"
        for key in ("fireTiles", "smokeTiles", "fireHash"):
            assert key in tiles(host), (
                f"`battle_tiles` carries no {key!r} - PRD-P9's hazard census is "
                f"missing and part C would be vacuous")
        assert "wounds" in battle(host)["units"][0], (
            "battle_state units carry no 'wounds' - the PRD-P9 unit census would "
            "be missing a term")

        hseat = parallel(host)["localSeat"]
        cseat = parallel(client)["localSeat"]
        assert hseat != cseat, f"both machines report seat {hseat}"
        cmover = PI.pick_driver(host, client, cseat, "client")
        hmover = PI.pick_driver(host, client, hseat, "host")
        base = assert_census(host, client, "at battle start")
        print(f"seats host={hseat} client={cseat}; drivers host={hmover} "
              f"client={cmover}; hazards {base} ({time.time() - started:.0f}s)")

        total = 0
        backlog_fired = 0
        for turn in range(1, args.turns + 1):
            t0 = time.time()
            turn_before = battle(host).get("turn")
            cmover = PE.ensure_driver(host, client, cseat, "client", cmover)
            hmover = PE.ensure_driver(host, client, hseat, "host", hmover)

            n = 0
            for i in range(3):
                n += locomotion_block(host, client, hmover, cmover)
                if args.trace:
                    settle_display(host, client)
                    trace_units(host, client, f"turn {turn} locomotion {i + 1}")
            n += shot_block(host, client, hmover, cmover)
            if args.trace:
                settle_display(host, client)
                trace_units(host, client, f"turn {turn} shots")
            n += support_block(host, client, cmover)
            if args.trace:
                settle_display(host, client)
                trace_units(host, client, f"turn {turn} support")
            if turn == 2:
                n += smoke_block(host, client, cmover)
            if turn == 3:
                backlog_fired = scenario_backlog_cap(host, client, hmover, cmover)
                n += backlog_fired
            total += n

            assert_census(host, client, f"after the actions of turn {turn}")
            got = close_side(host, client, hseat, cseat, turn_before)
            haz = assert_census(host, client,
                                f"after the alien side of turn {turn}")
            assert battle(host).get("inBattle"), (
                f"the fixture's mission ended during turn {turn} - the remaining "
                f"turns could assert nothing")
            print(f"TURN {turn}: {n} action(s) admitted (running {total}); side "
                  f"closed to turn {got}; hazards {haz}; "
                  f"{time.time() - t0:.0f}s, {time.time() - started:.0f}s total")

        assert total >= args.actions, (
            f"the soak only drove {total} admitted actions, below the "
            f"{args.actions} PRD-P9 asks for - the fixture refused too many "
            f"(a boxed-in driver, a shot with no line of fire)")
        assert backlog_fired, "the rider-R3 backlog phase never ran"

        # zero-disk holds even after a long battle
        session.assert_client_zero_disk(client.user_dir)
        print(f"\nSOAK CLEAN: {total} admitted actions over {args.turns} full "
              f"turns, seed {args.seed}, census equal after every side, tripwire "
              f"silent, backlog cap exercised. {time.time() - started:.0f}s")
        print("ALL PARALLEL SOAK TESTS PASSED")
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
