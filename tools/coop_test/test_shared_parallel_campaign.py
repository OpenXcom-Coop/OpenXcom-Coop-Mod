"""SHARED campaign + parallel battlescape turns: the full
geoscape -> battle -> debrief -> return cycle.

THE VALIDATION GAP THIS CLOSES. Two co-op features had never been exercised
together by any suite entry or soak:

  * the SHARED economy campaign (one host-authoritative world; test_shared_*),
    which flies a real geoscape mission into a co-op battle, and
  * parallel battlescape turns (EnableCoopParallelTurns; test_parallel_*),
    which lets BOTH players act during the same player side via the thin-client
    intent loop (client ships `action_intent`, host executes, both display).

The parallel tests all use the SKIRMISH fixture or the SEPARATE-campaign soak;
the SHARED tests all run the CLASSIC (alternating-sub-turn) battle. This test is
the one place the two meet - the combination the manager flagged as a very
common real-play scenario that must never break.

THE HEADLINE QUESTION, answered by running this: does parallel actually ACTIVATE
in a SHARED battle? connectionTCP::parallelTurnActive() gates on
`_enable_parallel_turns && getCoopStatic() && !hotseat && (gamemode==1||4)`. A
SHARED co-op campaign mission is gamemode 1 (PVE), and the host's option
propagates across the COOP_READY_HOST handshake, so it SHOULD. If it does not,
that itself is the finding: this test STOPS with the observed gamemode +
parallelActive/activeSync evidence rather than forcing anything.

WHAT IT DRIVES, in one battle:
  1. SHARED campaign bring-up with the host on EnableCoopParallelTurns (its option
     decides the mode for both machines), client off.
  2. A deterministic terror site flown from the shared craft into a co-op battle
     (the test_shared_battle recipe), seed-pinned right before map generation
     (host SEED, client SEED+1 - different streams, so an outcome-shipping
     regression cannot coincidentally agree).
  3. Both seats acting in parallel: a client-intent walk and shot (routed to the
     host), a host walk and shot (executor-local), with the per-action sync-check
     clean (zero ALARM across all ten promoted buckets), the item census equal and
     the drift tripwire silent after every action. The client's wait banner is
     observed opportunistically (nice-to-have, never fatal).
  4. A voted ABORT -> debriefing that scores IDENTICALLY on both machines
     (test_coop_debrief_sync's assertion) -> both back on the campaign geoscape.
  5. The clean SHARED return: one identical shared world (funds/bases/research),
     the replica never touched disk, and no desync bundle / crash marker / dump
     was written.

DELIBERATE DE-FLAKE. The actions are driven within the FIRST player side and the
mission is then aborted - the test does NOT cycle a full turn, so it never walks
into the P8 side-close "Waiting for HostPlayer" handshake that is the campaign
soak's documented flake. That turn-cycle path is already covered by
test_parallel_soak --profile campaign (SEPARATE); this test's job is the SHARED +
parallel combination and the geoscape->debrief->return cycle around it.

Run:  python tools/coop_test/test_shared_parallel_campaign.py
Exit 0 = pass; 2 = failure (STOP-AND-REPORT findings print with a STOP marker).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session
import test_parallel_intents as PI  # parallel drive helpers (intent/pos/settle/idle)
import test_battle_tripwire as TW
import test_shared_battle as SB
import test_coop_debrief_sync as DB

# Unused fixed pair + coop tuple (grep-checked against the suite: free).
HOST_PORT, CLIENT_PORT, COOP_PORT = 48948, 48949, 47967

# Seed-pin recipe (test_battle_tripwire / test_coop_debrief_sync): the host is the
# only machine that generates the map, so its seed fixes the map/deployment/stats;
# the client gets SEED+1 (a different stream). Overridable for a seed search.
SEED = int(os.environ.get("SHARED_PARALLEL_SEED", "424242"))

BATTLE_OPTS = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}


# ---- readouts --------------------------------------------------------------

def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


# ---- geoscape -> a shared terror battle ------------------------------------

def assign_and_fly(host, client):
    """Assign a mixed-ownership squad to the shared Skyranger and fly it to a
    seeded terror site until the host gets the landing prompt. Mirrors
    test_shared_battle's geoscape half, but deploys 2 host-owned (seat 0) + 2
    client-owned (seat 1) soldiers so parallel driving has a candidate of each
    seat with a fallback."""
    b0 = SB._base0(host)
    blon, blat = b0["lon"], b0["lat"]
    cid = SB._skyranger(host)["id"]
    rh = sorted(s["id"] for s in SB._roster(host))
    assert len(rh) >= 4, (
        f"the starting base has only {len(rh)} soldiers; the parallel split needs "
        f">= 4 (2 host-owned + 2 client-owned)")
    squad = rh[:4]
    owners = {squad[0]: 0, squad[1]: 0, squad[2]: 1, squad[3]: 1}

    # Ownership is stamped identically on BOTH machines (the split rides the
    # shared battlehost blob; a one-sided owner would deploy a different coop map).
    for gc in (host, client):
        for sid, seat in owners.items():
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": sid, "owner": seat})
    # Empty the craft, then board exactly the squad (host is craft-authoritative).
    for sid in rh:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in squad:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})

    def _aboard(gc):
        return sorted(s["id"] for s in SB._roster(gc) if s["craftId"] == cid)

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} squad aboard",
                    lambda gc=gc: (_aboard(gc) == sorted(squad)) or None,
                    timeout=40, interval=0.5)
    print(f"squad {squad} (owners {owners}) aboard shared craft {cid} on both")

    # A deterministic terror site next to the base, and teleport the shared craft
    # onto it (no flight-time RNG) - the exact test_shared_battle lever.
    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                    "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    host.wait_for("site on host",
                  lambda: any(s["id"] == site_id for s in SB._geo(host)["missionSites"]) or None,
                  timeout=30)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site_id}",
             "fuel": 999999, "lowFuel": False})

    def _landing_prompt():
        if SB._has(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})  # not geo_run: it auto-declines
        return None

    host.wait_for("ConfirmLandingState on host", _landing_prompt, timeout=90, interval=0.5)
    print("shared craft reached the site; host has the landing prompt")
    return cid, squad, owners


def enter_battle(host, client):
    """Seed-pin, confirm the landing, and drive both machines through
    briefing -> pre-battle inventory -> tactical to the co-op battle-init
    handshake. ConfirmLandingState is modal, so the seed set here is the RNG
    state the host generates the map from."""
    # Seeded right before generation: nothing advances the geoscape while the
    # modal landing prompt is up.
    host.ok({"cmd": "set_seed", "seed": SEED})
    client.ok({"cmd": "set_seed", "seed": SEED + 1})
    host.ok({"cmd": "confirm_landing"})

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} entered the battle",
                    lambda gc=gc: battle(gc).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} briefing", lambda gc=gc: SB._has(gc, "BriefingState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} pre-battle inventory",
                    lambda gc=gc: SB._has(gc, "InventoryState") or None,
                    timeout=120, interval=0.5)
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} tactical map",
                    lambda gc=gc: SB._has(gc, "BattlescapeState") or None,
                    timeout=120, interval=0.5)
    # Drain the turn-init "Your Turn" NextTurnState off both stacks (the client
    # has no skipNextTurnScreen, so it must be dismissed) - exactly what
    # TW.bring_up_battle does before waiting on the co-op init handshake.
    TW.drain_to_tactical(host, client)
    # Nothing replicates until the co-op turn-init handshake has run.
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} co-op battle init",
                    lambda gc=gc: battle(gc).get("battleInit") or None,
                    timeout=120, interval=1.0)
    time.sleep(3)
    print("both machines reached the SHARED battlescape (co-op battle init done)")


# ---- the headline: does parallel activate in a SHARED battle? --------------

def assert_parallel_active(host, client):
    """STOP-AND-REPORT gate. Parallel turns must be LIVE on both machines and the
    PRD-P5 executor invariant (`_isActivePlayerSync == getHost()`: host true /
    client false) must hold, or nothing below is testing the intended path. A miss
    is the FINDING, reported with the gamemode + the raw flags - not forced."""
    hb, cb = battle(host), battle(client)
    gm = hb.get("coopGamemode")
    ev = {
        "host": {"gamemode": gm, "parallelActive": hb.get("parallelActive"),
                 "parallelEnabled": hb.get("parallelEnabled"),
                 "activeSync": hb.get("activeSync")},
        "client": {"gamemode": cb.get("coopGamemode"),
                   "parallelActive": cb.get("parallelActive"),
                   "parallelEnabled": cb.get("parallelEnabled"),
                   "activeSync": cb.get("activeSync")},
    }
    if not (hb.get("parallelActive") is True and cb.get("parallelActive") is True):
        raise AssertionError(
            "STOP-AND-REPORT: parallel turns did NOT activate in a SHARED battle. "
            f"parallelTurnActive() needs gamemode 1 (PVE) or 4 (PVE2); observed "
            f"gamemode={gm}. Full evidence: {ev}")
    if not (hb.get("activeSync") is True and cb.get("activeSync") is False):
        raise AssertionError(
            "STOP-AND-REPORT: the PRD-P5 executor invariant does NOT hold in a "
            "SHARED parallel battle (host activeSync must be True, client False, "
            f"since _isActivePlayerSync == getHost()). Evidence: {ev}")
    print(f"PASS parallel-active: the SHARED battle is PARALLEL on BOTH machines "
          f"(gamemode={gm}=PVE, activeSync host=True/client=False)")
    return gm


# ---- per-action synchrony check --------------------------------------------

def check_sync(host, client, what):
    """After every driven action: the item terms agree (never drift), every
    promoted sync-check bucket agrees (zero ALARM), and the drift tripwire is
    silent."""
    PI.settle(host, client)
    session.assert_battle_synced(host, client, what)   # item-id counter + census
    session.assert_sync_clean(host, client, what)      # per-action buckets, zero ALARM
    assert not TW.desync_seen(host) and not TW.desync_seen(client), \
        f"the PRD-P2 drift tripwire fired {what}"


# ---- driving BOTH seats ----------------------------------------------------

def _robust_walk(host, client, mover, sender, tag, tries=8):
    """Walk `mover` one tile until it ACTUALLY moves, re-picking the destination
    (and re-placing a boxed-in unit) between tries. `sender` is the machine the
    action is issued from: the client (a routed intent) or the host (executor-
    local). A terror map is dense, and a walk can be interrupted the instant it
    starts (a unit spotted mid-step, a reaction shot) so that NOTHING moves - the
    same stall TW.drive_walk tolerates. Each such attempt still runs a complete
    chain (it is admitted, executed and sync-compared), so this is fixture
    hardening, not a masked bug; a truly un-executed intent raises after `tries`.

    Returns (before, landed, banner_seen) - banner_seen is the client wait banner
    caught opportunistically during the display window (nice-to-have, never
    asserted here)."""
    routed_expect = (sender is client)
    banner_seen = ""
    for attempt in range(1, tries + 1):
        PI.top_up(host, client, mover)
        dest = PI.step_dest(host, client, mover)   # re-places a boxed-in unit
        if not dest:
            continue
        before = PI.pos(battle(host), mover)
        r = PI.intent(sender, action="move", unit=mover, x=dest[0], y=dest[1], z=dest[2])
        assert r.get("ok"), f"{tag}: could not build the walk intent: {r}"
        assert r.get("routed") is routed_expect, (
            f"{tag}: routed={r.get('routed')} want {routed_expect} - a client intent "
            f"must route to the host; a host action must run locally")
        # Wait for the chain to finish, polling the client wait banner meanwhile.
        deadline = time.time() + 60
        while time.time() < deadline:
            b = PI.parallel(client).get("coopWaitBanner", "") or ""
            if "please wait" in b.lower() and not banner_seen:
                banner_seen = b
            if (PI.parallel(host).get("canAdmit") is True
                    and PI.parallel(client)["pendingReqId"] == 0):
                break
            time.sleep(0.1)
        PI.settle(host, client)
        landed = PI.pos(battle(host), mover)
        if landed != before:
            assert PI.wait_until(lambda: PI.pos(battle(client), mover) == landed, 45), (
                f"{tag}: the walk did not display on the client: host {landed} "
                f"client {PI.pos(battle(client), mover)}")
            return before, landed, banner_seen
        print(f"    ({tag} walk stalled at {before}, attempt {attempt}/{tries} - "
              f"interrupted; the chain ran, re-trying a fresh step)")
    raise AssertionError(
        f"{tag}: unit {mover} never moved over {tries} walk attempts. Each chain "
        f"completed (admitted + sync-compared), so this is a stalled/interrupted "
        f"walk on a dense map, not an un-executed intent - re-check the driver "
        f"placement, not the intent path.")


def drive_client_walk(host, client, mover):
    """A client-intent walk (routed to the host, both display)."""
    print("-- client-intent walk: host executes, both display --")
    before, landed, _ = _robust_walk(host, client, mover, client, "client-intent")
    session.assert_battle_synced(host, client, "after the client-intent walk")
    print(f"PASS client-intent walk: unit {mover} {before} -> {landed} on both machines")


def drive_host_walk(host, client, mover):
    """The host walks its OWN unit: executor runs it locally, client displays.
    Observes the client wait banner naming the host - nice-to-have, never fatal."""
    print("-- host walk: executor runs locally, client displays --")
    host.cmd({"cmd": "battle_camera", "unit": mover, "visible": True})
    before, landed, banner = _robust_walk(host, client, mover, host, "host")
    session.assert_battle_synced(host, client, "after the host walk")
    if banner:
        print(f"    PASS (nice-to-have): client wait banner during the host action = {banner!r}")
    else:
        print("    NOTE (nice-to-have): client wait banner not caught this run "
              "(timing) - non-fatal; test_coop_wait_banner covers it directly")
    print(f"PASS host walk: unit {mover} {before} -> {landed}, displayed on both")


def drive_client_shot(host, client, mover):
    """A client-intent shot at a TILE (not a kill - the battle must survive to the
    abort). PI.drive ships the intent, waits for the host to execute, and asserts
    the census + tripwire quiet."""
    print("-- client-intent shot: host executes, both display --")
    PI.top_up(host, client, mover)
    wid = PI.give_both(host, client, mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    here = PI.pos(battle(client), mover)
    PI.drive(host, client, "shoot(client)", action="shoot", unit=mover, mode="snap",
             weapon_id=wid, x=here[0] + 2, y=here[1] + 2, z=here[2])


def drive_host_shot(host, client, mover):
    """A host shot at a TILE, executor-local (routed False)."""
    print("-- host shot: executor runs locally, both display --")
    PI.top_up(host, client, mover)
    wid = PI.give_both(host, client, mover, "STR_RIFLE", "STR_RIFLE_CLIP")
    here = PI.pos(battle(host), mover)
    seq0 = PI.parallel(host)["actionSeq"]
    r = PI.intent(host, action="shoot", unit=mover, mode="snap", weapon_id=wid,
                  x=here[0] + 2, y=here[1] + 2, z=here[2])
    assert r.get("ok"), f"the host could not build the shot: {r}"
    assert r.get("routed") is False, \
        f"the host shipped an intent for its OWN shot ({r})"
    assert PI.idle(host), f"the host shot chain never ended: {PI.parallel(host)}"
    print(f"PASS host shot: unit {mover} fired (actionSeq {seq0} -> "
          f"{PI.parallel(host)['actionSeq']})")


# ---- ending: abort -> debrief identical -> geoscape ------------------------

def end_via_abort_and_compare_debrief(host, client):
    """A voted ABANDON MISSION, then the debriefing must score IDENTICALLY on both
    machines (test_coop_debrief_sync's assertion), then both drain back to the
    campaign geoscape."""
    print("-- voted ABORT -> debriefing (identical) -> geoscape --")
    DB.vote_abort_to_debriefing(host, client)
    dh = DB.wait_debrief(host, "host")
    dc = DB.wait_debrief(client, "client")
    print(f"    host   rows={dh['rows']} total={dh['total']}")
    print(f"    client rows={dc['rows']} total={dc['total']}")
    assert dh["rows"] == dc["rows"], (
        f"the debriefing score ROWS differ - host {dh['rows']} client {dc['rows']}. "
        f"Each machine builds the score page from its local battle save; a "
        f"difference is a SHARED+parallel debrief desync.")
    assert dh["scores"] == dc["scores"], (
        f"the debriefing POINTS differ: host {dh['scores']} client {dc['scores']}")
    assert dh["total"] == dc["total"], (
        f"the mission TOTAL differs: host {dh['total']} client {dc['total']}")
    print(f"PASS debrief: identical on both machines (rows={dh['rows']}, "
          f"total={dh['total']})")

    # Campaign debriefing returns to the GEOSCAPE (not the skirmish main menu).
    deadline = time.time() + 220
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} geoscape after debrief",
                    lambda gc=gc: session.drain_to_geoscape(gc, deadline),
                    timeout=240, interval=1.0)
    print("PASS return: both machines back on the campaign geoscape after debrief")


def assert_no_crash_artifacts(host, client, js):
    """No desync bundle, no crash-pending marker, no minidump on either machine."""
    for gc, tag, d in ((host, "host", js.host_dir), (client, "client", js.client_dir)):
        zips = TW.report_zips(gc)
        assert not zips, f"{tag}: a desync bundle was written during the cycle: {zips}"
        marker = os.path.join(d, "crash-pending.json")
        assert not os.path.exists(marker), \
            f"{tag}: a crash-pending marker was written: {marker}"
        dmps = [f for f in os.listdir(d) if f.endswith(".dmp")]
        assert not dmps, f"{tag}: crash dump(s) written: {dmps}"
    print("PASS clean: no desync bundle, no crash-pending marker, no dump on either machine")


def dump_debug(js):
    if js is None:
        return
    for tag, gc in (("host", js.host), ("client", js.client)):
        try:
            print(f"  DBG {tag} top: {session.states(gc)[-3:]}")
            b = gc.cmd({"cmd": "battle_state"})
            print(f"  DBG {tag} battle: inBattle={b.get('inBattle')} "
                  f"gm={b.get('coopGamemode')} parallelActive={b.get('parallelActive')} "
                  f"activeSync={b.get('activeSync')} desyncSeen={b.get('desyncSeen')}")
            print(f"  DBG {tag} parallel: {PI.parallel(gc)}")
        except Exception as de:
            print(f"  DBG {tag} dump failed: {de}")


# ---- main ------------------------------------------------------------------

def main():
    fail = None
    js = None
    try:
        js = shared_fixture.bring_up(
            "sharedpar", (HOST_PORT, CLIENT_PORT, COOP_PORT),
            host_options=dict(BATTLE_OPTS, skipNextTurnScreen=True,
                              EnableCoopParallelTurns=True),
            client_options=dict(BATTLE_OPTS, EnableCoopParallelTurns=False))
        host, client = js.host, js.client
        print("SHARED campaign up on the geoscape (host: parallel turns ON)")
        js.assert_world_equal("campaign start", timeout=60)

        # geoscape -> shared terror battle (seed-pinned generation)
        assign_and_fly(host, client)
        enter_battle(host, client)

        # THE HEADLINE FINDING
        gm = assert_parallel_active(host, client)

        # the ownership split deployed a driver of each seat
        cseat = client.ok({"cmd": "get_coop"})["localSeat"]
        client_mover = PI.pick_driver(host, client, cseat, "client")
        host_mover = PI.pick_driver(host, client, 0, "host")
        session.assert_battle_synced(host, client, "at battle start")
        session.assert_sync_clean(host, client, "at battle start")
        print(f"drivers placed: client seat {cseat} unit {client_mover}, "
              f"host seat 0 unit {host_mover}")

        # drive BOTH seats in parallel, per-action sync clean
        drive_host_walk(host, client, host_mover)
        check_sync(host, client, "after the host walk")
        drive_client_walk(host, client, client_mover)
        check_sync(host, client, "after the client-intent walk")
        drive_host_shot(host, client, host_mover)
        check_sync(host, client, "after the host shot")
        drive_client_shot(host, client, client_mover)
        check_sync(host, client, "after the client-intent shot")
        print("PASS parallel driving: both seats acted, per-action sync clean")

        # end: abort -> debrief identical -> geoscape return
        end_via_abort_and_compare_debrief(host, client)

        # the clean SHARED return
        js.assert_world_equal("post-battle SHARED world", timeout=120)
        session.assert_client_zero_disk(js.client_dir)
        print("PASS zero-disk: the SHARED replica never wrote save data")
        assert_no_crash_artifacts(host, client, js)

        print(f"\nSHARED-PARALLEL CAMPAIGN CYCLE PASSED (gamemode {gm}, seed {SEED}): "
              f"geoscape -> parallel battle -> identical debrief -> shared geoscape return")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        dump_debug(js)
    finally:
        if js is not None:
            js.shutdown()
    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
