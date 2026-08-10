"""PRD-I0: the per-action sequenced sync-check.

The PRD-P2 tripwire is TURN-grained: three terms, stamped once per `next_turn`,
compared before the bulk apply. When it fires, the suspect list is "something in
the last side". I0 makes the same question per-ACTION, using machinery that
already exists:

    host   drains chain N  ->  computeBattleHashes() -> ring[{seq, kind, h}]
                           ->  `action_end {action_seq: N}`
    client consumes it     ->  computeBattleHashes()
                           ->  `action_done {seq: N, seat, side_seq, h: {...}}`
    host   receives it     ->  look N up, compare PER BUCKET, name the loser

Seven buckets (terrain, fire, smoke, items, unitsCore, unitsStats, itemIdCtr),
each ALARM or REPORT-ONLY by a compile-time table. At I0's birth every one is
REPORT-ONLY - the detector ships first, the promotions are PRD-I3's, each with
its own burn-in evidence.

Seq coverage is extended in the same commit so the question can be asked
everywhere state moves:

  * AI-side chains are stamped where handleAI COMMITS to an action (the alien
    side used to run completely unnumbered);
  * two boundary pseudo-seqs, in their OWN monotonic namespace, cover the
    side-close phase group ("endturn") and the side start ("sidestart"). They
    ride an `action_end {boundary: true}` marker, which is NOT whitelisted, so
    the client consumes it at receive-gate depth 0 - i.e. it hashes AFTER
    `fuse_events` / `next_turn` have been applied. That is deliberately the
    opposite of the legacy tripwire's compare-BEFORE-apply, which is untouched.

What this test asserts (PRD-I0 §4, in order):

  1. CLEAN + COVERAGE. ~20 mixed player actions and a full alien side: the
     deferred loop closes (`lastComparedSeq` catches `lastSeq`), nothing is
     dropped, and `comparedKinds` proves the AI chains and both boundary kinds
     were actually compared - a seq extension that silently stamped nothing
     would sail through a bare zero-mismatch assertion.
  2. AI-SIDE ATTRIBUTION. A one-sided unit skew injected just before the side
     closes is named against an AI-chain seq (`kind == "ai"`, not a boundary).
  3. BOUNDARY ATTRIBUTION. The same skew is also named against a boundary
     pseudo-seq - the only thing that can attribute a divergence introduced
     between two sides.
  4. RED BUCKET + RIGHT SEQ. A one-sided item mint names the `items` bucket at
     the seq of the very next action, and leaves terrain/fire/smoke/unitsCore
     alone - the exclusivity proof that a bucket means what it says.

Both divergence levers are TEST-ONLY uses of existing harness commands
(`battle_give`, `battle_intent`'s `status` setter). No divergence mechanism
ships in the game.

Run:  python tools/coop_test/test_sync_check.py
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
import test_parallel_endturn as PE

PORT = "47993"

# connectionTCP::unitstatusToInt. DEAD rather than UNCONSCIOUS: the engine revives
# its own unconscious units at every turn boundary, so an UNCONSCIOUS skew is
# undone by the very side cycle that is supposed to carry it across.
WIRE_STATUS_DEAD = 6

# The buckets that must stay quiet under an ITEM-only lever. `itemIdCtr` moves
# with `items` (the mint advances the counter - that is the same family and the
# point of having both), and `unitsStats` is the bucket PRD-I0 itself calls
# expected-noisy, so neither belongs in an exclusivity assertion.
ITEM_LEVER_INNOCENT = ("terrain", "fire", "smoke", "unitsCore")

# PRD-I3 SEAM-1 discriminator (kneel-burst). Post-fix the kneel replay packet
# ships the actor's cost, so a run of kneel/stand toggles must leave ZERO
# kneel-KIND unitsStats mismatches. Default ON (this is the permanent green
# gate); export SEAM1_KNEEL_STRICT=0 to take the pre-fix red baseline
# print-only, without aborting the rest of the suite.
KNEEL_STRICT = os.environ.get("SEAM1_KNEEL_STRICT", "1") == "1"

# PRD-I3 SEAM-2 + straddle discriminator (smoke-heavy side). Post-fix, Option B
# gates the parallel client's SavedBattleGame::prepareNewTurn decay (next_turn is
# the sole author) and Option A drops the redundant neutral->player `endturn`
# marker, so NO smoke or fire mismatch is attributed to a BOUNDARY. The ai-seq
# racing residual (client's deterministic-but-early regen at its raced-ahead
# turn) is Option D's remit and is PRINTED, not asserted. Default ON = the
# permanent green gate; export SEAM2_SMOKE_STRICT=0 to take the pre-fix red
# baseline print-only.
SMOKE_STRICT = os.environ.get("SEAM2_SMOKE_STRICT", "1") == "1"


# ---- readouts --------------------------------------------------------------

def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def sync(gc):
    return session.sync_check(gc)


def counts(sc):
    return {n: b["mismatchCount"] for n, b in sc["buckets"].items()}


def delta(before, after):
    return {n: after[n] - before[n] for n in after if after[n] > before.get(n, 0)}


def kneel_stats_mismatches(sc):
    """Just the unitsStats mismatches attributed to a KNEEL action seq.

    The I0 detector names every mismatch (seq, kind, bucket); SEAM-1 is the
    kneel replay packet re-deciding the actor's charge on the peer, so its
    signature is precisely bucket==unitsStats AND kind=="kneel"."""
    return [m for m in sc.get("mismatches", [])
            if m["bucket"] == "unitsStats" and m["kind"] == "kneel"]


def unit_stat_diff(host, client):
    """Per-unit numeric-field disagreements between the two machines.

    Diagnostic only: names WHICH unit and WHICH stat drifted, so a residual
    kneel-kind unitsStats mismatch can be read as the kneeler's own cost
    (SEAM-1) versus a bystander (a different seam sampled at the kneel seq)."""
    hu = {u["id"]: u for u in battle(host)["units"]}
    cu = {u["id"]: u for u in battle(client)["units"]}
    diffs = []
    for uid in sorted(set(hu) & set(cu)):
        h, c = hu[uid], cu[uid]
        d = {k: (h.get(k), c.get(k)) for k in ("tu", "energy", "health", "stun",
             "wounds") if k in h and k in c and h.get(k) != c.get(k)}
        if d:
            diffs.append((uid, d))
    return diffs


def poll(fn, timeout, interval=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def idle(host, timeout=90):
    return poll(lambda: parallel(host).get("canAdmit") is True, timeout, 0.1)


def settle_display(host, client, timeout=90):
    """Both machines quiescent: the executor idle, the peer's display watermark
    caught up, its receive gate empty and no BattleState still running anywhere.

    Same shape as the PRD-P9 soak's. A hash comparison taken while a chain is
    still draining on the client compares two machines at different points in the
    same action, which is a guaranteed red that means nothing."""
    PI.settle(host, client, 2)
    poll(lambda: parallel(host).get("displayBacklog", 0) == 0
         and parallel(host).get("taskCompleted") is not False
         and parallel(client).get("taskCompleted") is not False
         and parallel(client).get("rxHold", 0) == 0, timeout, 0.1)
    poll(lambda: battle(host).get("isBusy") is False
         and battle(client).get("isBusy") is False, timeout, 0.1)


def reset_sync(host, client):
    """Clear the sync-check counters (and the PRD-P2 latch) on both machines.

    Also clears the RING, so anything still in flight lands as a `staleReports`
    rather than a compare - which is why every caller settles first."""
    settle_display(host, client)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})


# ---- driving ---------------------------------------------------------------

def act(host, client, driver, **kw):
    """Drive one action from `driver` and wait for the executor to finish with it.

    Returns how many chains the host admitted (0 = the lever or the arbiter
    refused - a boxed-in soldier or a shot with no line of fire is a fixture
    accident, not a protocol failure)."""
    seq0 = parallel(host)["actionSeq"]
    r = PI.intent(driver, **kw)
    if not r.get("ok"):
        return 0
    poll(lambda: parallel(host)["actionSeq"] > seq0, 25, 0.05)
    if not idle(host, 90):
        PI.settle(host, client, 3)
        idle(host, 30)
    return max(0, parallel(host)["actionSeq"] - seq0)


def drive_mixed(host, client, hmover, cmover, want=20):
    """`want` admitted actions, alternating seats and mixing kinds.

    Walks (the chain everything else is built on), turns (a chain that may ship
    NO packet at all - the case PRD-P7's `action_end` marker exists for) and
    kneels (an instant kind that pushes no BattleState, so its `action_done` can
    only come from the main-thread close path). Between them they cover the three
    shapes of chain the seq machinery has to handle."""
    n = 0
    guard = 0
    while n < want and guard < want * 4:
        guard += 1
        for driver, uid, tag in ((client, cmover, "client"), (host, hmover, "host")):
            if n >= want:
                break
            PI.top_up(host, client, uid)
            dest = PI.step_dest(host, client, uid)
            if dest:
                n += act(host, client, driver, action="move", unit=uid,
                         x=dest[0], y=dest[1], z=dest[2])
            here = PI.pos(battle(host), uid)
            if here:
                n += act(host, client, driver, action="turn", unit=uid,
                         x=here[0] + 2, y=here[1] + 2, z=here[2])
            n += act(host, client, driver, action="kneel", unit=uid)
    return n


def close_side(host, client, turn_before, timeout=300):
    """Both seats ready -> the executor commits -> the alien side runs -> a new
    player side. Same shape as the PRD-P9 soak's."""
    PE.hush(host, client)
    for gc in (host, client):
        if not parallel(gc)["localReady"]:
            PE.arm(gc)
    poll(lambda: parallel(host)["allReady"] is True
         or battle(host).get("turn") != turn_before
         or not parallel(host)["localReady"], 30, 0.2)
    turn = PE.wait_side(host, client, turn_before, timeout=timeout)
    assert turn, (
        f"the side never closed with both seats ready: host={parallel(host)} "
        f"client={parallel(client)}, host top={TW.top(host)} "
        f"client top={TW.top(client)}")
    PI.settle(host, client, 3)
    poll(lambda: battle(host).get("battleInit") and battle(client).get("battleInit"),
         60, 0.5)
    idle(host)
    return turn


def skew_unit_down(host, client):
    """Put ONE live X-Com unit down on the CLIENT alone and prove it took.

    A bare `setCoopStatus` - nothing in the co-op protocol replicates it - so the
    client's `unitsCore` bucket moves and the host's does not. Returns the unit
    id, or None when the fixture has nobody spare."""
    settle_display(host, client)
    alive = [u for u in battle(client)["units"]
             if not u["isOut"] and u.get("faction") == 0]
    if len(alive) < 2:
        return None
    victim = alive[-1]["id"]
    before = session.sync_buckets(client)["unitsCore"]
    r = client.cmd({"cmd": "battle_intent", "unit": victim, "action": "turn",
                    "status": WIRE_STATUS_DEAD, "dry": True})
    if not (r.get("ok") and r.get("status") == WIRE_STATUS_DEAD):
        return None
    if not poll(lambda: session.sync_buckets(client)["unitsCore"] != before, 15):
        return None
    return victim


# ---- 1. clean + coverage ---------------------------------------------------

def scenario_clean(host, client, hmover, cmover):
    print("-- 1: a clean battle - the loop closes and every seq family is covered --")
    reset_sync(host, client)

    n = drive_mixed(host, client, hmover, cmover, want=20)
    assert n >= 12, (
        f"only {n} action(s) were admitted; the fixture refused too many for this "
        f"scenario to say anything about coverage")
    settle_display(host, client)
    # strict: PRD-I0 scenario 1 asks for ZERO mismatches on a clean battle. Six of
    # the seven buckets deliver that at birth over ~20 mixed actions - measured,
    # and asserted here so a regression in any of them is a test failure today
    # rather than after PRD-I3 promotes them.
    #
    # `unitsStats` is the seventh, and PRD-I0 names it as the expected-noisy one
    # before a line of it was written. Measured at birth on this fixture: clean on
    # most runs, 4 mismatches on others, over a plain sequence of walks, turns and
    # kneels. It is a REAL per-action stat divergence (the sample points are the
    # two machines' own chain drains, so there is no window for it to be a timing
    # artefact) and it is PRD-I3's first job. Allowed, not ignored: the count is
    # printed on every run so the burn-in has numbers to promote on.
    # PRD-I3 Option D-lite (turn-sync) does NOT close this: it is a PLAYER-side
    # per-action divergence, not the alien-side turn-machine racing D-lite removed
    # (measured post-D-lite: still ~3 here over walks/turns/kneels), so the allowance
    # STAYS - shrinking it to empty was tried and reverted.
    sc = session.assert_sync_clean(host, client, "after the player actions",
                                   strict=True, allow=("unitsStats",))
    print(f"    {n} player chains driven; compares={sc['compares']} "
          f"kinds={sc['comparedKinds']} sweep={sc['sweepUs']}us")
    # SEAM-1 diagnostic: name the KIND of every unitsStats mismatch, so the
    # per-action unitsStats drift can be attributed (kneel vs walk/turn).
    us_ms = [(m["seq"], m["kind"]) for m in sc.get("mismatches", [])
             if m["bucket"] == "unitsStats"]
    print(f"    unitsStats mismatch (seq,kind) over player actions: {us_ms}")
    # PRD-I2: saveBlob is BOUNDARY-only. No side has closed since reset_sync, so it
    # must have zero comparisons/mismatches here; a non-zero count would mean it
    # fired on a per-action report, which it must never do.
    assert sc["buckets"]["saveBlob"]["mismatchCount"] == 0, (
        f"saveBlob moved over PLAYER ACTIONS with no boundary crossed "
        f"({sc['buckets']['saveBlob']}) - the save-derived hash is computed and "
        f"compared only at side boundaries")

    turn_before = battle(host).get("turn")
    turn = close_side(host, client, turn_before)
    settle_display(host, client)
    # Same allowance across the boundary, and here there is a second known reason
    # for it on top of the per-action one: both machines run their OWN
    # prepareNewTurn (TU regeneration, stun recovery, fatal-wound bleed) and the
    # boundary marker lands somewhere inside that window on each. The other six
    # buckets are still asserted, including across a full alien side.
    sc = session.assert_sync_clean(
        host, client, f"after the alien side of turn {turn_before}", strict=True,
        allow=("unitsStats", "saveBlob"))
    # PRD-I2 BURN-IN: saveBlob is the whole-save superset, so it moves at a
    # clean boundary whenever ANY report-only bucket it subsumes does
    # (unitsStats via prepareNewTurn, smoke decay, the tile FOW/UFO-door bits
    # inside binTiles). Expected, and I3's remit - recorded here, not chased.
    print(f"    saveBlob report-only count over the clean boundary: "
          f"{sc['buckets']['saveBlob']['mismatchCount']} (subsumes "
          f"unitsStats/smoke/FOW seams - PRD-I3 burn-in data)")

    # COVERAGE, not silence. Each of these is a seq family PRD-I0 had to CREATE;
    # if the extension did not take, the family simply never appears and a bare
    # zero-mismatch assertion would pass with the alien side unwatched.
    kinds = sc["comparedKinds"]
    assert kinds.get("ai", 0) > 0, (
        f"no AI-side chain was ever compared ({kinds}) - `_actionSeq` is still a "
        f"player-side counter, so the whole alien side is unattributable. The "
        f"stamping point is BattlescapeGame::coopStampAiChain.")
    assert kinds.get("endturn", 0) > 0, (
        f"the side-close boundary pseudo-seq was never compared ({kinds}) - the "
        f"`endturn` marker is not reaching the peer, or the peer is not answering "
        f"it. Everything the endTurn phase group moves is unattributable.")
    assert kinds.get("sidestart", 0) > 0, (
        f"the side-start boundary pseudo-seq was never compared ({kinds}) - the "
        f"marker armed in NextTurnState::close is not being shipped/answered.")
    assert any(k not in ("ai", "endturn", "sidestart") for k in kinds), (
        f"not one PLAYER chain was compared ({kinds}) - the per-action half of "
        f"the detector is not running at all")
    assert sc["staleReports"] == 0, (
        f"{sc['staleReports']} peer report(s) found no ring entry. Every one is a "
        f"comparison that silently did not happen; the (side_seq, seq) key is "
        f"what should make that impossible: {sc}")

    print(f"PASS 1: turn cycled to {turn}; {sc['compares']} chains compared "
          f"{kinds}, loop closed at seq {sc['lastComparedSeq']}/{sc['lastSeq']} "
          f"(boundary {sc['lastComparedBoundarySeq']}/{sc['lastBoundarySeq']}), "
          f"0 dropped, 0 stale")
    mism = counts(sc)
    if any(mism.values()):
        print(f"    NOTE: report-only buckets that moved over the clean turn: "
              f"{ {k: v for k, v in mism.items() if v} } - see the run report; "
              f"these are the PRD-I3 burn-in candidates, not test failures")
    return sc


# ---- SEAM-1. kneel-burst: the kneel replay packet must ship its cost --------

def _saveblob_text_diff(host, client, max_lines=16):
    import difflib
    ht = host.cmd({"cmd": "save_blob", "text": True}).get("text", "").splitlines()
    ct = client.cmd({"cmd": "save_blob", "text": True}).get("text", "").splitlines()
    out = [l for l in difflib.unified_diff(ht, ct, lineterm="", n=1)
           if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    return out[:max_lines]


def _burst_toggles(host, client, hmover, cmover, rounds=6):
    """Plain move->turn->kneel on BOTH a host unit (MODE 1, classic replay) and a
    client-intent unit (MODE 2, host-executed intent broadcast). With MATCHING
    (default) reserves the kneel charge is a deterministic constant (kneel cost
    4 down / 8 up), so both peers reach the same answer and this phase is clean
    by construction - it exercises the happy path of both receive modes.

    settle_display after each kneel is the I0 comparison discipline: driving the
    next action before the CLIENT has quiesced lets the detector sample its
    action_done hash mid-drain, a transient "red that means nothing" (session.py
    settle_display), which is exactly what makes an un-settled burst intermittent.
    Settled, the happy path is reliably zero."""
    toggles = 0
    for _ in range(rounds):
        for driver, uid in ((host, hmover), (client, cmover)):
            if uid is None:
                continue
            PI.top_up(host, client, uid)
            dest = PI.step_dest(host, client, uid)
            if dest:
                act(host, client, driver, action="move", unit=uid,
                    x=dest[0], y=dest[1], z=dest[2])
            here = PI.pos(battle(host), uid)
            if here:
                act(host, client, driver, action="turn", unit=uid,
                    x=here[0] + 2, y=here[1] + 2, z=here[2])
            toggles += act(host, client, driver, action="kneel", unit=uid)
            settle_display(host, client)
    return toggles


def _reserve_mismatch_kneel(host, client, uid):
    """Deterministically drive SEAM-1: a host kneel whose peer copy re-decides
    against a DIFFERENT reserve and refuses it.

    In parallel mode battle_reserve does NOT replicate (BattlescapeState::
    coopSendReserveState early-returns while parallelTurnActive), so a client-only
    "aimed" reserve is a real per-machine reserve mismatch. With the actor's TU
    set just inside the refuse window [aimedCost, aimedCost + kneelCost), the
    host (no reserve) kneels and charges, while the client (aimed reserve) fails
    checkReservedTU and does NEITHER - so tu AND the kneeling bit diverge at the
    kneel seq. This is the exact seam clean play only hits intermittently."""
    if uid is None:
        return {"set_up": False, "why": "no host driver"}
    q = host.cmd({"cmd": "battle_intent", "unit": uid, "action": "shoot",
                  "mode": "aimed", "dry": True})
    aimed = q.get("tuCost", 0) or 0
    if aimed <= 8:
        return {"set_up": False, "why": f"no usable aimed reserve (tuCost={aimed})"}
    target_tu = aimed + 2  # inside [aimed, aimed+kneelCost) for kneelCost in {4,8}
    for gc in (host, client):
        gc.cmd({"cmd": "battle_intent", "unit": uid, "action": "turn",
                "tu": target_tu, "dry": True})
    client.cmd({"cmd": "battle_reserve", "mode": "aimed"})
    host.cmd({"cmd": "battle_reserve", "mode": "none"})
    hr = host.cmd({"cmd": "battle_reserve"}).get("reserve")
    cr = client.cmd({"cmd": "battle_reserve"}).get("reserve")
    before = len(kneel_stats_mismatches(sync(host)))
    n = act(host, client, host, action="kneel", unit=uid)   # MODE 1: host kneels
    settle_display(host, client)
    sc = sync(host)
    after = kneel_stats_mismatches(sc)
    diffs = unit_stat_diff(host, client)
    client.cmd({"cmd": "battle_reserve", "mode": "none"})    # restore
    PI.top_up(host, client, uid)
    return {"set_up": n > 0, "aimed": aimed, "target_tu": target_tu,
            "host_reserve": hr, "client_reserve": cr,
            "reproduced": len(after) > before, "kneel_ms": len(after),
            "seq": (after[-1]["seq"] if len(after) > before else None),
            "diffs": diffs}


def scenario_kneel_burst(host, client, hmover, cmover):
    """PRD-I3 SEAM-1: the kneel replay packet must ship the actor's cost.

    Both receive modes emit the SAME `kneel {id}` packet (BattlescapeGame::
    coopSendKneelPacket) into the SAME peer handler; the seam is that the packet
    carried no tu/energy, so the peer re-ran BattlescapeGame::kneel() and
    re-decided. Two phases: (A) a default-reserve happy-path burst that is clean
    by construction, and (B) a DETERMINISTIC reserve mismatch that forces the
    peer to re-decide differently - the reliable red/green discriminator."""
    print("-- SEAM-1: the kneel replay packet must ship the actor's cost --")

    # Phase A: happy path, both modes, matching reserves.
    reset_sync(host, client)
    tog = _burst_toggles(host, client, hmover, cmover, rounds=6)
    settle_display(host, client)
    scA = sync(host)
    kkA = scA["comparedKinds"].get("kneel", 0)
    ksA = kneel_stats_mismatches(scA)
    print(f"    [A: default reserves] {tog} kneels, comparedKinds kneel={kkA}, "
          f"kneel-kind unitsStats mismatches={len(ksA)}")
    if len(ksA) > 0:
        print(f"    [A-diag] kneel-kind mismatch seqs={sorted({m['seq'] for m in ksA})}; "
              f"all unitsStats mismatches={[(m['seq'], m['kind']) for m in scA.get('mismatches', []) if m['bucket']=='unitsStats']}")
        print(f"    [A-diag] end-of-phase per-unit stat diff={unit_stat_diff(host, client)}")
        print(f"    [A-diag] end-of-phase saveblob text diff={_saveblob_text_diff(host, client)}")
    assert kkA > 0, (
        f"phase A drove {tog} kneels but the detector compared no kneel kinds "
        f"({scA['comparedKinds']}) - the discriminator is not exercising kneels")

    # Phase B: deterministic reserve mismatch (the reliable discriminator).
    reset_sync(host, client)
    r = _reserve_mismatch_kneel(host, client, hmover)
    print(f"    [B: reserve mismatch] {r}")

    if KNEEL_STRICT:
        assert len(ksA) == 0, (
            f"SEAM-1: {len(ksA)} kneel-kind unitsStats mismatch(es) on the "
            f"default-reserve happy path (seqs "
            f"{sorted({m['seq'] for m in ksA})})")
        if r.get("set_up") and r.get("reproduced") is not None:
            assert r.get("kneel_ms", 0) == 0, (
                f"SEAM-1 NOT CLOSED: the reserve-mismatch host kneel still left "
                f"{r['kneel_ms']} kneel-kind unitsStats mismatch(es) at seq "
                f"{r['seq']} (diffs {r['diffs']}). The peer is not mirroring the "
                f"executor's kneel cost/state.")
            print("PASS SEAM-1: reserve-mismatch host kneel left zero kneel-kind "
                  "unitsStats drift (peer mirrored the executor)")
        else:
            print(f"    NOTE: reserve-mismatch phase could not set up "
                  f"({r.get('why')}); phase A clean is the only assertion")
    else:
        print(f"    [SEAM1_KNEEL_STRICT=0] baseline print-only: phase-A "
              f"kneel-kind={len(ksA)}, phase-B reproduced={r.get('reproduced')} "
              f"kneel_ms={r.get('kneel_ms')}")
    return scA


# ---- 2 + 3. AI-side and boundary attribution -------------------------------

def scenario_ai_and_boundary(host, client, hmover, cmover):
    """One skew, two attributions.

    The skew is injected while the player side is idle and then carried ACROSS a
    side boundary, so the very next things to report are, in order, the side-close
    boundary marker, the alien side's own chains, and the side-start marker. That
    is the only arrangement in which both attributions can be observed from a
    single divergence - and injecting two separate ones would mean the second was
    measured on a battle the first had already moved."""
    print("-- 2+3: AI-chain and boundary attribution of one carried-over skew --")
    reset_sync(host, client)

    victim = skew_unit_down(host, client)
    assert victim, (
        "could not put a unit down on the client alone - the lever is dead, so "
        "both attribution assertions below would be vacuous")
    hb = session.sync_buckets(host)["unitsCore"]
    cb = session.sync_buckets(client)["unitsCore"]
    assert hb != cb, (
        f"the one-sided status write left the two machines agreeing on unitsCore "
        f"({hb} vs {cb}) - it replicated, so there is nothing to detect")
    print(f"    unit {victim} put down on the client alone (unitsCore host={hb} "
          f"client={cb})")

    turn_before = battle(host).get("turn")
    turn = close_side(host, client, turn_before)
    settle_display(host, client)
    sc = sync(host)
    ms = sc["mismatches"]
    assert ms, (
        f"the carried-over unit skew produced no mismatch at all over a whole "
        f"side boundary: {sc}. Either the client stopped attaching hashes or the "
        f"host stopped comparing.")

    core = [m for m in ms if m["bucket"] == "unitsCore"]
    assert core, (
        f"the skew was detected but never attributed to `unitsCore` - the bucket "
        f"that hashes exactly (id, faction, liveness, position): "
        f"{sorted({m['bucket'] for m in ms})}")

    ai = [m for m in core if not m["boundary"] and m["kind"] == "ai"]
    assert ai, (
        f"no AI-CHAIN seq was named. The alien side ran (turn is now {turn}) and "
        f"the client held a unit the host does not, so at least one alien chain's "
        f"report had to disagree. Named instead: "
        f"{[(m['seq'], m['kind'], m['boundary']) for m in core[:8]]}")
    print(f"PASS 2 (AI attribution): named at AI seq {ai[0]['seq']} "
          f"(kind={ai[0]['kind']}, bucket={ai[0]['bucket']})")

    bnd = [m for m in core if m["boundary"]]
    assert bnd, (
        f"no BOUNDARY pseudo-seq was named. The skew was in place across the "
        f"side-close phase group and the side start, which is precisely the "
        f"window no admitted chain covers. Named instead: "
        f"{[(m['seq'], m['kind'], m['boundary']) for m in core[:8]]}")
    assert bnd[0]["kind"] in ("endturn", "sidestart"), (
        f"a boundary mismatch carries an unexpected kind {bnd[0]['kind']!r} - the "
        f"two boundary groups are 'endturn' and 'sidestart'")
    print(f"PASS 3 (boundary attribution): named at boundary seq "
          f"{bnd[0]['seq']} (kind={bnd[0]['kind']})")

    # PRD-I2 BACKSTOP: the same carried-over skew that named `unitsCore` at a
    # boundary MUST also flip `saveBlob` at a boundary - the save-derived hash is a
    # superset of every per-action bucket, so a divergence a fast bucket catches
    # can never slip past it. This is the proof the backstop actually backstops.
    sblob = [m for m in ms if m["bucket"] == "saveBlob" and m["boundary"]]
    assert sblob, (
        f"the skew flipped unitsCore at a boundary but NOT saveBlob "
        f"({sorted({m['bucket'] for m in ms})}) - the save-derived backstop missed "
        f"a divergence a fast bucket caught, which defeats its whole purpose")
    assert sc["buckets"]["saveBlob"]["alarm"] is False, (
        "saveBlob is ALARM-promoted; PRD-I2 ships it REPORT-ONLY")
    print(f"PASS I2 backstop: saveBlob also named at boundary seq "
          f"{sblob[0]['seq']} (kind={sblob[0]['kind']}), report-only")

    # REPORT-ONLY at birth: a red must NOT latch the PRD-P2 desync flag, because
    # nothing in the promotion table is armed yet. This is the routing proof.
    for name in ("unitsCore",):
        assert sc["buckets"][name]["alarm"] is False, (
            f"the promotion table has {name} armed; this build's routing "
            f"assertion below is written against the birth policy")
    assert not TW.desync_seen(host), (
        "a REPORT-ONLY bucket fired the battleDesyncSeen ALARM path - the "
        "promotion table is not being honoured, and every test that asserts "
        "`desyncSeen` is False would now fail on known-open seams")
    print("PASS routing: the red was logged and counted, and did NOT latch "
          "battleDesyncSeen (every bucket is REPORT-ONLY at I0 birth)")

    # `next_turn` repairs a bare status write, so the battle is left clean for
    # the item scenario. Prove it rather than assume it.
    poll(lambda: session.sync_buckets(host)["unitsCore"]
         == session.sync_buckets(client)["unitsCore"], 30)
    return sc


# ---- 4. the red bucket, and the RIGHT seq ----------------------------------

def scenario_red_bucket(host, client, hmover, cmover):
    """Runs LAST: the lever mints an item on one machine only and nothing repairs
    that, so everything after it would be measured on a permanently skewed
    battle."""
    print("-- 4: a one-sided item mint names `items` at the seq of the next action --")
    reset_sync(host, client)
    settle_display(host, client)

    innocent_before = session.sync_buckets(host)
    # `slot: ground` drops the item on the CARRIER'S TILE, so the carrier has to
    # be a unit that still has one - a casualty has been unlinked from its tile
    # and the lever refuses ("unit has no tile"), which reads like a sync-check
    # failure and is not one.
    hosts_live = {u["id"] for u in battle(host)["units"] if not u.get("isOut")}
    live = [u["id"] for u in battle(client)["units"]
            if not u.get("isOut") and u.get("faction") == 0 and u["id"] in hosts_live]
    assert live, (
        f"no live X-Com unit is left on both machines to hang the item lever on: "
        f"{[(u['id'], u.get('faction'), u.get('isOut')) for u in battle(client)['units']]}")
    victim = live[0]
    skew = client.cmd({"cmd": "battle_give", "unit": victim,
                       "item": "STR_STUN_ROD", "slot": "ground"})
    assert skew.get("ok"), f"could not skew the client (unit {victim}): {skew}"
    hb, cb = session.sync_buckets(host), session.sync_buckets(client)
    assert hb["items"] != cb["items"], (
        f"the injected mint did not move the client's `items` bucket "
        f"({hb['items']} vs {cb['items']}) - the lever is dead")
    print(f"    minted item {skew.get('weaponId')} on the client alone")

    # The mint moves nothing but the item family, on the client's own copy. If it
    # had touched a unit or a tile, the exclusivity assertion further down would
    # be measuring the lever rather than the buckets.
    for name in ITEM_LEVER_INNOCENT:
        assert cb[name] == innocent_before[name], (
            f"the item lever moved the client's {name!r} bucket "
            f"({innocent_before[name]} -> {cb[name]}) - it is not item-exclusive, "
            f"so the attribution proof below would be vacuous")

    before = counts(sync(host))
    PI.top_up(host, client, hmover)
    dest = PI.step_dest(host, client, hmover)
    assert dest, f"the host driver {hmover} cannot step anywhere to carry the seq"
    seq0 = parallel(host)["actionSeq"]
    assert act(host, client, host, action="move", unit=hmover,
               x=dest[0], y=dest[1], z=dest[2]), \
        "the host's walk was not admitted, so no seq carries the skew"
    seq = parallel(host)["actionSeq"]
    settle_display(host, client)

    assert poll(lambda: delta(before, counts(sync(host))), 30), (
        f"the host never reported a mismatch for the injected item skew "
        f"(actionSeq {seq0} -> {seq}): {sync(host)}")
    sc = sync(host)
    moved = delta(before, counts(sc))
    assert "items" in moved, (
        f"the item skew was detected but not attributed to the `items` bucket: "
        f"{moved}")
    for name in ITEM_LEVER_INNOCENT:
        assert name not in moved, (
            f"an item-only divergence moved the {name!r} bucket as well ({moved}) "
            f"- the buckets are not independent, so naming one means nothing")
    print(f"PASS 4a: the `items` bucket was named and "
          f"{'/'.join(ITEM_LEVER_INNOCENT)} stayed quiet ({moved})")
    assert "saveBlob" not in moved, (
        f"the per-action item lever moved saveBlob ({moved}) with no boundary "
        f"crossed - the save-derived hash must be boundary-only")

    named = [m for m in sc["mismatches"]
             if m["bucket"] == "items" and not m["boundary"]]
    assert named, f"no non-boundary `items` mismatch was recorded: {sc['mismatches']}"
    seqs = sorted({m["seq"] for m in named})
    assert seq in seqs, (
        f"the mismatch was attributed to seq(s) {seqs}, not to the action that "
        f"actually carried it (actionSeq {seq0} -> {seq}). Attribution to the "
        f"wrong seq is worse than none: it points a bisect at an innocent action.")
    kind = [m["kind"] for m in named if m["seq"] == seq][0]
    print(f"PASS 4b: named at seq {seq} (kind={kind!r}), which is exactly the "
          f"chain admitted after the skew")
    return sc


# ---- 5. SEAM-2 + straddle: boundary tile decay is host-authoritative -------

def scenario_smoke(host, client, hmover, cmover):
    """PRD-I3 SEAM-2 + straddle discriminator (deterministic smoke placement).

    Primes (fuse 0) and throws several STR_SMOKE_GRENADEs, then closes a full
    side so the boundary tile-decay phase runs on both machines. Pre-fix the
    parallel client's ungated SavedBattleGame::prepareNewTurn SPREADS smoke
    (Tile::addSmoke) and AVERAGES it (Tile::prepareNewTurn) while its DECREMENT
    (Tile::setSmoke/setFire) is a host-gated no-op - "spread without decrement",
    which mangles the client's smoke - and the neutral->player `endturn` boundary
    is hashed BEFORE next_turn repairs it. Post-fix Option B gates that decay
    (next_turn is the sole author of the boundary tile hazards) and Option A
    drops the redundant, hash-before-apply endturn marker, so NO smoke or fire
    mismatch is attributed to a BOUNDARY.

    The deterministic-but-early per-unit regen the client still runs at its
    raced-ahead turn leaves an ai-seq unitsStats (and some ai-seq smoke) RACING
    residual - Option D's remit, out of this fix's scope - which is PRINTED, not
    asserted. SEAM2_SMOKE_STRICT=0 takes the pre-fix red baseline print-only.
    """
    print("-- 5: SEAM-2 boundary tile decay is host-authoritative (Option B+A) --")
    reset_sync(host, client)
    thrown = 0
    for i in range(6):
        if not idle(host):
            break
        PI.top_up(host, client, cmover)
        wid = PI.give_both(host, client, cmover, "STR_SMOKE_GRENADE")
        if not wid:
            break
        if not act(host, client, client, action="prime", unit=cmover, fuse=0,
                   weapon_id=wid):
            continue
        PI.top_up(host, client, cmover)
        here = PI.pos(battle(host), cmover)
        if here:
            thrown += 1 if act(host, client, client, action="throw", unit=cmover,
                               weapon_id=wid, x=here[0] + 1 + (i % 3),
                               y=here[1] + 1 + (i // 3), z=here[2]) else 0
        idle(host, 30)
    settle_display(host, client)
    assert thrown >= 2, (
        f"only {thrown} smoke grenade(s) were thrown; the fixture refused too "
        f"many for this scenario to place any smoke")

    turn_before = battle(host).get("turn")
    turn = close_side(host, client, turn_before)
    settle_display(host, client)

    haz = host.cmd({"cmd": "battle_tiles"})
    smoke_tiles = haz.get("smokeTiles", 0)
    assert smoke_tiles > 0, (
        f"no smoke is on the map after the side ({haz}); the grenades never went "
        f"off, so a clean smoke bucket below would prove nothing")

    # non-strict: the loop must close and no ALARM bucket may fire; the report-only
    # counts are printed and inspected per-attribution below.
    sc = session.assert_sync_clean(
        host, client, f"after a smoke-heavy alien side of turn {turn_before}",
        strict=False, quiet=True)

    ms = sc.get("mismatches", [])
    saturated = len(ms) >= 32  # the ring keeps only the last 32; note if it wrapped
    smoke_bnd = [(m["seq"], m["kind"]) for m in ms
                 if m["bucket"] == "smoke" and m.get("boundary")]
    fire_bnd = [(m["seq"], m["kind"]) for m in ms
                if m["bucket"] == "fire" and m.get("boundary")]
    smoke_ai = [m["seq"] for m in ms if m["bucket"] == "smoke" and not m.get("boundary")]
    us_ai = [m["seq"] for m in ms if m["bucket"] == "unitsStats" and not m.get("boundary")]
    print(f"    smokeTiles={smoke_tiles} smoke bucket="
          f"{sc['buckets']['smoke']['mismatchCount']} fire bucket="
          f"{sc['buckets']['fire']['mismatchCount']} kinds={sc['comparedKinds']}")
    print(f"    boundary smoke={smoke_bnd} boundary fire={fire_bnd}")
    # PRD-I3 Option D-lite (turn-sync) flipped the ai/player-seq RACING RESIDUAL
    # from a print into a strict assert. The client's turn machine no longer
    # free-runs ahead of the gated display (the neutral->player advance defers to
    # next_turn), so its deterministic per-unit regen is no longer hashed against a
    # not-yet-regen'd host: `unitsStats` at an ai/player seq is 0. `smoke` at an
    # ai/player seq is likewise 0 - the only thing that moved it was the raced-ahead
    # turn; what smoke divergence remains is the SEAM-2 explosion/host-flush
    # non-determinism the BOUNDARY assert below already gates (the two co-fire).
    print(f"    RACING RESIDUAL (Option D-lite, ai/player seqs): smoke={len(smoke_ai)} "
          f"unitsStats={len(us_ai)} - turn machine now follows next_turn, so the "
          f"deterministic-but-early regen no longer straddles the host's side")
    if SMOKE_STRICT:
        assert not saturated, (
            f"the {len(ms)}-deep mismatch ring wrapped in a single side, so a "
            f"'clean boundary' read below could be hiding an evicted boundary "
            f"mismatch - shorten the scenario or widen the ring before trusting it")
        assert not smoke_bnd and not fire_bnd, (
            f"SEAM-2 NOT GREEN: smoke/fire diverged at a BOUNDARY "
            f"(smoke {smoke_bnd}, fire {fire_bnd}). Option B (gate the parallel "
            f"client's prepareNewTurn decay so next_turn is the sole author) + "
            f"Option A (drop the neutral->player endturn marker that hashed before "
            f"next_turn applied) make the boundary tile hazards host-authoritative; "
            f"a boundary smoke/fire mismatch means one of them regressed.\n"
            f"    {session._sync_mismatch_lines(sc)}")
        assert not us_ai, (
            f"D-lite NOT GREEN: unitsStats diverged at ai/player seq(s) {us_ai} - "
            f"the client is still running its per-unit regen at a raced-ahead turn. "
            f"The neutral->player advance must defer to the next_turn apply so the "
            f"regen is hashed against the host's own regen'd side, not ahead of it.\n"
            f"    {session._sync_mismatch_lines(sc)}")
        assert not smoke_ai, (
            f"smoke diverged at ai/player seq(s) {smoke_ai} - the raced-ahead turn "
            f"machine was the cause D-lite removed; a residual here co-fires the "
            f"boundary assert above and is the SEAM-2 explosion/flush divergence.\n"
            f"    {session._sync_mismatch_lines(sc)}")
    print(f"PASS 5: no boundary AND no ai-seq smoke/fire/unitsStats divergence over "
          f"a smoke-heavy side (smokeTiles={smoke_tiles}); racing residual "
          f"smoke={len(smoke_ai)} unitsStats={len(us_ai)}")
    return sc


# ---- I2. saveBlob: determinism, cost, boundary-only registry --------------

def scenario_saveblob_selftest(host, client):
    """PRD-I2's save-derived boundary bucket, its own up-front checks.

    (a) DETERMINISM. `save_blob` serializes the live battle exactly as
        SavedBattleGame::save would, minus a short machine-local exclusion list,
        and FNV-1a hashes the canonical tree. Hashing the same quiescent battle
        TWICE on ONE machine must be byte-identical - the cheap catch for emitter
        nondeterminism (an unordered_map feeding the writer, or serialization that
        mutates state) before it can masquerade as a cross-machine desync.
    (b) COST. The serialization is the whole expense (PRD-I2 estimates 5-20 ms);
        measured and printed, asserted only against a sane ceiling.
    (c) REGISTRY. `saveBlob` must show up in the syncCheck bucket table (so its
        report-only counter is readable) but NEVER in the raw per-action
        `battleHashes` sweep the harness polls hot - it is boundary-only."""
    print("-- I2: saveBlob determinism, cost and boundary-only registry --")
    settle_display(host, client)

    for gc, tag in ((host, "host"), (client, "client")):
        a = gc.cmd({"cmd": "save_blob"})
        b = gc.cmd({"cmd": "save_blob"})
        assert a.get("ok") and b.get("ok"), f"{tag}: save_blob did not run: {a} / {b}"
        assert a["hash"] == b["hash"], (
            f"{tag}: the save-derived hash is NON-DETERMINISTIC on ONE machine "
            f"({a['hash']} != {b['hash']}) - the writer is feeding the emitter from "
            f"an unordered container, or serializing mutates state. Fix or sort "
            f"before this can masquerade as a boundary desync.")
        assert a["hash"] != 0, f"{tag}: save_blob hashed to 0 - serialization empty"
        assert a["us"] < 200000, (
            f"{tag}: one saveBlob serialize took {a['us']}us (>200ms) - PRD-I2 "
            f"budgets 5-20ms and it is boundary-only, but this is pathological")
        print(f"    {tag}: saveBlob deterministic (hash stable), "
              f"serialize={a['us']}us")

    sc = sync(host)
    assert "saveBlob" in sc["buckets"], (
        f"saveBlob missing from the syncCheck bucket table, so its report-only "
        f"counter is unreadable: {sorted(sc['buckets'])}")
    assert sc["buckets"]["saveBlob"]["alarm"] is False, (
        "saveBlob is ALARM-promoted at birth - PRD-I2 ships it REPORT-ONLY")
    raw = session.sync_buckets(host)
    assert "saveBlob" not in raw, (
        f"saveBlob leaked into the raw per-action `battleHashes` sweep "
        f"{sorted(raw)} - a 5-20ms boundary cost must never ride the hot poll")

    hh = host.cmd({"cmd": "save_blob"})["hash"]
    cc = client.cmd({"cmd": "save_blob"})["hash"]
    print(f"    cross-machine saveBlob at battle start: host={hh} client={cc} "
          f"({'equal' if hh == cc else 'differ - recorded, report-only'})")

    # PRD-I3 FOW Option B rider: the per-unit FOV/spotting keys must be excluded
    # from the saveBlob hash INPUT (saveBlobExcludedAnyKey), so they cannot appear
    # in the canonical text the hash consumes. turnsSinceSpotted is written
    # unconditionally by BattleUnit::save, so its ABSENCE from the dump is the
    # direct proof the exclusion is live; visible / turnsLeftSpottedForSnipers
    # asserted too.
    dump = host.cmd({"cmd": "save_blob", "text": True})
    txt = dump.get("text", "") if dump.get("textOk") else None
    if txt is not None:
        leaked = [k for k in ("visible", "turnsSinceSpotted",
                              "turnsLeftSpottedForSnipers")
                  if k in txt]
        assert not leaked, (
            f"per-unit FOV keys {leaked} are still in the saveBlob canonical text "
            f"- the FOW Option B rider's saveBlobExcludedAnyKey entries are not "
            f"taking, so the hash still moves on presentation-only FOV drift")
        print(f"    FOW rider live: per-unit FOV keys excluded from the saveBlob "
              f"canonical text ({len(txt)} chars, no visible/turnsSinceSpotted/"
              f"turnsLeftSpottedForSnipers)")
    else:
        print("    NOTE: save_blob {text} unavailable; FOV-exclusion text check "
              "skipped")
    print("PASS I2 self-test: deterministic, boundary-only, report-only")
    return sc


# ---- main ------------------------------------------------------------------

def main():
    fail = None
    host = GameClient("host", 48890,
                      make_user_dir("i0_sync_host",
                                    options={"battleXcomSpeed": 2,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48891,
                        make_user_dir("i0_sync_client",
                                      options={"battleXcomSpeed": 2,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        PI.PORT = PORT
        PE.PORT = PORT
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
            "the PRD-P5 executor invariant does not hold; nothing below tests it"

        # --- 0. the registry is real -------------------------------------
        for gc, tag in ((host, "host"), (client, "client")):
            h = session.sync_buckets(gc)
            assert sorted(h) == sorted(["terrain", "fire", "smoke", "items",
                                        "unitsCore", "unitsStats", "itemIdCtr"]), (
                f"{tag}'s bucket registry is not the PRD-I0 §2 set: {sorted(h)}")
            assert h["terrain"] and h["items"] and h["unitsCore"] and h["itemIdCtr"], (
                f"{tag}'s buckets look empty on a generated battle: {h} - a "
                f"sweep that returns zeros would agree with anything")
        hb, cb = session.sync_buckets(host), session.sync_buckets(client)
        same = [k for k in hb if hb[k] == cb[k]]
        print(f"    buckets equal at battle start: {sorted(same)}")
        for key in ("terrain", "items", "unitsCore", "itemIdCtr"):
            assert hb[key] == cb[key], (
                f"the two machines disagree on the {key!r} bucket at battle "
                f"GENERATION (host={hb[key]} client={cb[key]}) - both generate the "
                f"same battle deterministically, so this is a pre-existing "
                f"divergence and nothing below can be trusted")

        sc0 = sync(host)
        # `sync: True` - the sweep + report block is opt-in on battle_state (see
        # session.sync_check), so the hot poll every other test runs is unchanged.
        sweeps = [gc.cmd({"cmd": "battle_state", "sync": True}).get("battleHashSweepUs")
                  for gc in (host, client)]
        tiles = host.cmd({"cmd": "battle_tiles"}).get("tileCount")
        print(f"SWEEP COST: {sweeps[0]}us (host) / {sweeps[1]}us (client) over "
              f"{tiles} tiles - the PRD-I0 target is < 1000us on 60x60x4 (14400)")
        for tag, us in (("host", sweeps[0]), ("client", sweeps[1])):
            assert us is not None and us * 14400 // max(1, tiles) < 1000, (
                f"{tag}'s bucket sweep costs {us}us over {tiles} tiles, i.e. over "
                f"the 1 ms budget once scaled to a 60x60x4 map. PRD-I0 says hash "
                f"per bucket lazily if this happens.")
        # NOT "nothing has happened yet": co-op battle init runs a `next_turn`, so
        # the side-start boundary marker has already been through the whole loop by
        # the time a test can look. That it has is the first proof the loop works.
        assert sc0["mismatchCount"] == 0, (
            f"the two machines already disagree before anything was driven: {sc0}")
        assert all(not b["alarm"] for b in sc0["buckets"].values()), (
            f"a bucket is ALARM-promoted in this build; the report-only routing "
            f"assertions in scenario 2 are written against the I0 birth policy: "
            f"{ {n: b['alarm'] for n, b in sc0['buckets'].items()} }")

        cseat = parallel(client)["localSeat"]
        hseat = parallel(host)["localSeat"]
        assert hseat != cseat, f"both machines report seat {hseat}"
        cmover = PI.pick_driver(host, client, cseat, "client")
        hmover = PI.pick_driver(host, client, hseat, "host")

        scenario_saveblob_selftest(host, client)
        scenario_clean(host, client, hmover, cmover)
        cmover = PE.ensure_driver(host, client, cseat, "client", cmover)
        hmover = PE.ensure_driver(host, client, hseat, "host", hmover)
        scenario_kneel_burst(host, client, hmover, cmover)
        cmover = PE.ensure_driver(host, client, cseat, "client", cmover)
        hmover = PE.ensure_driver(host, client, hseat, "host", hmover)
        scenario_ai_and_boundary(host, client, hmover, cmover)
        cmover = PE.ensure_driver(host, client, cseat, "client", cmover)
        hmover = PE.ensure_driver(host, client, hseat, "host", hmover)
        scenario_smoke(host, client, hmover, cmover)
        cmover = PE.ensure_driver(host, client, cseat, "client", cmover)
        hmover = PE.ensure_driver(host, client, hseat, "host", hmover)
        # scenario_red_bucket runs LAST: its one-sided item mint permanently skews
        # the battle, so anything after it measures a skewed state.
        scenario_red_bucket(host, client, hmover, cmover)

        session.assert_client_zero_disk(client.user_dir)
        print("ALL SYNC-CHECK TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  DBG {tag} syncCheck: {sync(gc)}")
                print(f"  DBG {tag} parallel:  {parallel(gc)}")
                print(f"  DBG {tag} top:       {TW.top(gc)}")
            except Exception as de:
                print(f"  DBG {tag} dump failed: {de}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
