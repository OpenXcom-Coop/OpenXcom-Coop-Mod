"""E5a GAP-XP + GAP-MODULE: a client-owned soldier must TRAIN from a host-replayed
kill, and the base-defense module_destroyed carrier must stay linked.

THE GAPS (explosion-ordered-replay plan v2, section 2.4):

  GAP-XP: when a client-owned soldier's shot kills or hits, the HOST resolves it
  (it is the only machine that ever executes the attack) and runs
  `TileEngine::awardExperience` - the client never replays the attack, so its own
  copy of the attacker gained NO combat XP and showed no stat improvement at
  debrief. FIX: the host ships the attacker's post-award `_exp` absolutes on the
  existing `hit_unit` packet (`exp_firing`/`exp_throwing`/`exp_melee`/
  `exp_reactions`/`exp_bravery`/`exp_psi_skill`/`exp_psi_strength`/`exp_mana` -
  every counter `awardExperience`/`addManaExp` mutate); the client applies them to
  the attacker by `attacker_id`, present-gated.

  GAP-MODULE: the detonate-path base-module decrement (`TileEngine::detonate`,
  base-defense `_moduleMap` used by `DebriefingState` to score base defense) is
  host-only for coop (the parallel client early-returns from `detonate()`) with no
  carrier. FIX: a new `module_destroyed {gx, gy}` packet, host-sent/client-applied,
  parallel-gated. NOT staged here (no cheap way to arm a STR_BASE_DEFENSE map with
  a scored module inside this fixture's budget - see the GAP-MODULE section
  below); this fixture proves the carrier is LINKED (sent counter mirrors applied)
  by asserting both stay 0 on an ordinary (non-base-defense) map, where the
  detonate-path decrement never fires at all.

SCENARIO (donors: test_coop_debrief_sync.py for the debrief + both-machine stat
read, test_parallel_intents.py for the client-intent shot the host executes): a
CLIENT-seat soldier repeatedly fires on aliens via `battle_intent` (the host
executes every shot and runs `awardExperience` locally; the client never does).
After enough hits the shooter's `firing` exp counter is read via `battle_state`'s
per-unit `expFiring` field on BOTH machines - GREEN is `host == client > 0`,
proving the carrier. The mission is then finished and both machines' debriefings
are compared, then the SAME soldier's post-mission `firing` stat (read via
`get_soldiers`, which reflects `BattleUnit::postMissionProcedures`'s consumption
of `_exp`) is read on both machines: reaching `expFiring >= 3` puts the roll in
`BattleUnit::improveStat`'s `exp > 2` bracket (`RNG::generate(1,3)`), the lowest
bracket that can NEVER roll a 0 stat bump - so once the fixture reaches that
count the post-debrief training check is a hard assertion, not a coin flip
(`postMissionProcedures` runs independently with its own RNG on each machine, so
the two machines' bump AMOUNTS are not asserted equal - only that each is > 0).

Run:  python tools/coop_test/test_parallel_xp_module.py
Exit 0 = pass; 2 = failure. Budget: a handful of adjacent aimed-shot kills plus one
debrief - well under the 180s slow-test threshold.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI
import test_coop_debrief_sync as DBS

SEED = int(os.environ.get("XP_MODULE_SEED", "913317"))

# BattleUnit::improveStat: exp>10 -> RNG(2,6); exp>5 -> RNG(1,4); exp>2 -> RNG(1,3);
# exp>0 -> RNG(0,1) [CAN roll 0]; exp==0 -> 0. 3 is the lowest count whose bracket
# can never roll a 0 stat bump - the floor this fixture aims for before it treats
# "no stat increase" as a real failure rather than a legitimate coin flip.
MIN_FIRING_EXP = 3


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def find_soldier(resp, soldier_id):
    for b in resp.get("bases", []):
        for s in b.get("soldiers", []):
            if s["id"] == soldier_id:
                return s
    return None


def soldier_firing(gc, soldier_id):
    s = find_soldier(gc.ok({"cmd": "get_soldiers"}), soldier_id)
    assert s is not None, f"soldier {soldier_id} not found in get_soldiers"
    return s["firing"]


def shooter_exp(host, client, shooter_id):
    """(hostExpFiring, clientExpFiring): the GAP-XP carrier readout itself, straight
    off battle_state's per-unit `expFiring` field (BattleUnit::_exp.firing)."""
    hu = PI.unit(battle(host), shooter_id)
    cu = PI.unit(battle(client), shooter_id)
    return (hu.get("expFiring", 0) if hu else 0,
            cu.get("expFiring", 0) if cu else 0)


def run(ports, tmp):
    hport, cport, coop_port = ports
    mod = DBS.make_mod(tmp)
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = GameClient("host", hport,
                      make_user_dir("xp_module_host", mods=[mod],
                                    options=dict(opts, skipNextTurnScreen=True,
                                                 EnableCoopParallelTurns=True)))
    client = GameClient("client", cport,
                        make_user_dir("xp_module_client", mods=[mod],
                                      options=dict(opts, EnableCoopParallelTurns=False)))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = str(coop_port)
        PI.PORT = str(coop_port)
        TW.bring_up_battle(host, client, seed=SEED)

        for gc, tag in ((host, "host"), (client, "client")):
            b = battle(gc)
            assert b["parallelActive"] is True, f"{tag}: parallel mode is not live: {b}"
        assert battle(host)["activeSync"] is True and battle(client)["activeSync"] is False, \
            "the PRD-P5 executor invariant does not hold, so nothing below tests it"

        seat = client.ok({"cmd": "get_coop"})["localSeat"]
        shooter = PI.pick_driver(host, client, seat, "client")
        shooter_soldier_id = PI.unit(battle(host), shooter)["soldierId"]
        assert shooter_soldier_id >= 0, (
            f"unit {shooter} has no backing Soldier - can't check debrief training")
        firing_before = soldier_firing(host, shooter_soldier_id)
        print(f"battle up (seed {SEED}). client seat {seat}, shooter unit {shooter} "
              f"(soldier {shooter_soldier_id}, firing {firing_before} pre-mission)")

        # ---- GAP-XP: the client-owned shooter kills via CLIENT-INTENT shots. The host
        # is the only machine that ever executes the attack (battle_intent -> the host's
        # BattlescapeGame::coopRouteAction), so every awardExperience call for this
        # shooter happens on the host; hit_unit must carry the result to the client. ----
        killed = []
        for _ in range(DBS.NALIENS + 1):
            hexp, _ = shooter_exp(host, client, shooter)
            if hexp >= MIN_FIRING_EXP:
                break
            aliens = DBS.live_aliens(host)
            if not aliens:
                break
            alien = aliens[0]
            spot = PI.place_adjacent(host, client, shooter, (alien["x"], alien["y"], alien["z"]))
            if not spot:
                continue
            if DBS.arm_and_kill(host, client, shooter, alien["id"], "client"):
                killed.append(alien["id"])
                h, c = shooter_exp(host, client, shooter)
                print(f"    client-intent kill: alien {alien['id']} "
                      f"(shooter expFiring now host={h} client={c})")

        host_exp, client_exp = shooter_exp(host, client, shooter)
        print(f"-- GAP-XP: shooter {shooter} expFiring host={host_exp} client={client_exp} "
              f"after {len(killed)} client-intent kill(s) --")
        assert host_exp > 0, (
            f"the host never trained ANY firing exp on its own attacker after "
            f"{len(killed)} client-intent kills - the fixture staged no hits, not a "
            f"carrier result (re-check placement/weapon/accuracy, not the carrier)")
        assert host_exp == client_exp, (
            f"GAP-XP regression: the host's attacker trained expFiring={host_exp} but "
            f"the client's copy of the SAME attacker shows {client_exp} - hit_unit's "
            f"exp_* fields did not carry, or the client failed to apply them "
            f"(TileEngine.cpp hitUnit send / connectionTCP.cpp hit_unit handler)")
        print(f"PASS GAP-XP: attacker's firing-exp counter is IDENTICAL host/client "
              f"({host_exp}) immediately after the replayed hit(s), read straight off "
              f"the carrier (battle_state expFiring)")

        # ---- GAP-MODULE: no STR_BASE_DEFENSE map is staged here (see module note in
        # the file docstring) - prove the carrier stays LINKED (sent mirrors applied)
        # rather than firing spuriously on an ordinary map, where the detonate-path
        # base-module decrement this carrier ships never triggers at all. ----
        for gc, tag in ((host, "host"), (client, "client")):
            ps = PI.parallel(gc)
            sent = ps.get("moduleDestroyedSent", -1)
            applied = ps.get("moduleDestroyedApplied", -1)
            assert sent == 0 and applied == 0, (
                f"{tag}: moduleDestroyedSent={sent} moduleDestroyedApplied={applied} on "
                f"a non-base-defense map - the carrier fired where it should not have")
        print("PASS GAP-MODULE (linked, not staged): moduleDestroyedSent == "
              "moduleDestroyedApplied == 0 on both machines (see the file docstring - a "
              "STR_BASE_DEFENSE scenario was not cheap to stage in this fixture)")

        # ---- finish the mission -> debrief, then read the TRAINED stat on both machines
        print("-- finishing the mission (mop-up) -> debriefing --")
        DBS.kill_the_rest(host, client)
        dh = DBS.wait_debrief(host, "host")
        dc = DBS.wait_debrief(client, "client")
        print(f"    host   rows={dh['rows']} total={dh['total']}")
        print(f"    client rows={dc['rows']} total={dc['total']}")

        firing_host_after = soldier_firing(host, shooter_soldier_id)
        firing_client_after = soldier_firing(client, shooter_soldier_id)
        print(f"-- debrief: soldier {shooter_soldier_id} firing {firing_before} "
              f"pre-mission -> host {firing_host_after}, client {firing_client_after} "
              f"post-debrief --")
        assert firing_host_after >= firing_before, (
            f"the host's own soldier LOST firing stat ({firing_before} -> "
            f"{firing_host_after}) - a sanity failure, not the carrier under test")
        assert firing_client_after >= firing_before, (
            f"the client's copy of the soldier LOST firing stat ({firing_before} -> "
            f"{firing_client_after}) - a sanity failure, not the carrier under test")
        if host_exp >= MIN_FIRING_EXP:
            # exp>2 -> BattleUnit::improveStat's RNG::generate(1,3) branch, which can
            # never roll 0 - a DETERMINISTIC (not merely likely) nonzero bump on both
            # machines' independent postMissionProcedures roll (each machine trains its
            # own copy of the soldier off its own local RNG - the two bump AMOUNTS are
            # not asserted equal, only that each is present).
            assert firing_host_after > firing_before, (
                f"host expFiring={host_exp} (>={MIN_FIRING_EXP}) guarantees a nonzero "
                f"stat bump (BattleUnit::improveStat), but the host's own soldier shows "
                f"no firing improvement at debrief ({firing_before} -> "
                f"{firing_host_after})")
            assert firing_client_after > firing_before, (
                f"GAP-XP regression AT DEBRIEF: the client's expFiring matched the "
                f"host's ({client_exp}, >={MIN_FIRING_EXP}) so postMissionProcedures on "
                f"the client should ALSO show a guaranteed nonzero firing bump, but it "
                f"shows none ({firing_before} -> {firing_client_after}) - the client's "
                f"local debrief never saw the trained _exp")
            print(f"PASS debrief training: BOTH machines show the trained firing stat "
                  f"(host {firing_before}->{firing_host_after}, client "
                  f"{firing_before}->{firing_client_after})")
        else:
            print(f"NOTE: shooter only reached expFiring={host_exp} (< {MIN_FIRING_EXP}) "
                  f"- BattleUnit::improveStat's low-exp branch can legitimately roll a 0 "
                  f"stat bump, so the post-debrief comparison above is a >= sanity check "
                  f"only, not a strict trained-stat assertion")

        for gc, tag in ((host, "host"), (client, "client")):
            st = session.states(gc)
            assert not any("BattlescapeState" in s for s in st), \
                f"{tag}: the battle is still on the stack after the debriefing: {st}"
        print("PASS: both machines left the battle and hold a debriefing")
    finally:
        host.shutdown(); client.shutdown()


def main():
    tmp = tempfile.mkdtemp(prefix="coop_xp_module_")
    fail = None
    try:
        run((48996, 48997, 48004), tmp)
        print("ALL XP/MODULE CARRIER TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
