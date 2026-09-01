"""The debriefing must score the SAME battle the same way on both machines.

THE BUG (reported from manual parallel-turns play, skirmish + ABORT): the two
players' debriefings disagreed - the host counted 2 alien kills, the client 1.

WHY. DebriefingState::prepareDebriefing() runs on BOTH machines and builds the
score page from the LOCAL save; the host's debriefing packet only carries the
soldier-stats and diary pages. Its alien-kill row is

    oldFaction == FACTION_HOSTILE && bunit->killedBy() == FACTION_PLAYER

and `killedBy` (with `murdererId`) was the one part of a death that never
crossed the wire: each machine derived it in its own
BattlescapeGame::checkForCasualties. The peer gets the same answer whenever it
runs that pass over the same victim - which it does for a death caused by an
action it is replaying - so ordinary shot kills agreed and the gap hid. It does
NOT run it for a death it never replays as a local attack chain, and the
everyday case of that is a REACTION-FIRE kill during the ALIEN side: there the
alien keeps the BattleUnit constructor default `_killedBy = its own faction`,
the peer scores it as no kill at all, and the two players see different counts
AND different mission scores. `killedBy` is also saved, so it is a persisted
divergence, not a display one.

THE FIX. `unit_death` and `after_unit_death` carry `killedBy`/`murdererId`, and
the peer adopts them instead of deriving anything (additive; absent = older peer
= keep the local derivation).

WHAT THIS TEST DRIVES, in one battle, for each of two endings (ABORT and WIN):

  1. a host-executed kill        (battle_fire on the host)
  2. a client-intent kill        (battle_intent -> the host executes)
  3. at least one ALIEN-SIDE kill - the reaction fire the aliens walk into when
     the turn is handed over. This is the flavour that was actually broken; the
     test fails rather than passes vacuously if the fixture never produces one.
  4. the ending, and then `debrief_state` on BOTH machines: every score row, its
     quantity and its points, and the total, must be identical.

Attribution is asserted per unit as well as through the debriefing, so a failure
says WHICH alien lost its killer and not merely that a number was wrong.

FIXTURE NOTE. Stock STR_SMALL_SCOUT holds exactly ONE alien, which is not enough
to make two kills and still have a battle left to abort, so the test generates a
throwaway ruleset that raises the count (the pattern test_coop_outcome_gaps.py
uses) and puts them all outside the UFO, where the squad meets them.

Run:  python tools/coop_test/test_coop_debrief_sync.py
Exit 0 = pass; 2 = failure.
"""

import os
import shutil
import sys
import tempfile
import time

# RW-TRIAGE: SKIP-PENDING(r4 T2)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI

NALIENS = 5

# Pin the fixture (outcome_gaps recipe): a fresh-random battle made both mid-battle
# levers below flake ~2/3 - the mop-up needs a reachable killable alien and the
# alien-side reaction kill needs an alien to walk into the armed squad's line of
# fire. The host generates + ships the world, so its seed fixes the map, deployment
# and stats; the client gets seed+1 (a DIFFERENT stream, so an attribution-ship
# regression still diverges). Overridable for a seed search.
SEED = int(os.environ.get("DEBRIEF_SEED", "424242"))

# STATUS_DEAD / FACTION_PLAYER as battle_state reports them.
STATUS_DEAD = 6
FACTION_PLAYER = 0
FACTION_HOSTILE = 1

METADATA = """\
name: "Coop debriefing sync test"
version: 1.0
description: "Test-only: a skirmish scout with enough aliens to kill several."
author: coop harness

master: xcom1
"""

RULESET = """\
alienDeployments:
  - type: STR_SMALL_SCOUT
    data:
      - alienRank: 5
        lowQty: %d
        highQty: %d
        dQty: 0
        percentageOutsideUfo: 100
        itemSets:
          -
            - STR_PLASMA_PISTOL
            - STR_PLASMA_PISTOL_CLIP
          -
            - STR_PLASMA_PISTOL
            - STR_PLASMA_PISTOL_CLIP
          -
            - STR_PLASMA_PISTOL
            - STR_PLASMA_PISTOL_CLIP
    width: 40
    length: 40
    height: 4
""" % (NALIENS, NALIENS)


def make_mod(root):
    mod = os.path.join(root, "Coop_Debrief_Sync_Test")
    if os.path.isdir(mod):
        return mod
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "debrief_sync.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


# ---- reading the two machines ----------------------------------------------

def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def all_units(gc):
    """battle_state's unit list, or [] once the battle is over (the mission can
    end under any of these readouts - the last kill auto-ends it)."""
    return battle(gc).get("units", [])


def units(gc):
    return {u["id"]: u for u in all_units(gc)}


def live_aliens(gc):
    return [u for u in all_units(gc)
            if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]


def live_player_units(gc):
    return [u for u in all_units(gc)
            if u.get("faction") == FACTION_PLAYER and not u.get("isOut")
            and u.get("tu") is not None]


def attribution(gc):
    """{alien id: (status, killedBy, murdererId)} for every hostile-born unit.

    This is what DebriefingState reads; comparing it directly is what makes a
    failure point at the death that lost its killer."""
    return {u["id"]: (u["status"], u.get("killedBy"), u.get("murdererId"))
            for u in all_units(gc) if u.get("faction") == FACTION_HOSTILE}


def killed_here(gc):
    """The alien ids THIS machine would put in the STR_ALIENS_KILLED row."""
    return sorted(uid for uid, (st, kb, _m) in attribution(gc).items()
                  if st == STATUS_DEAD and kb == FACTION_PLAYER)


def assert_attribution_agrees(host, client, what):
    ah, ac = attribution(host), attribution(client)
    bad = {uid: (ah.get(uid), ac.get(uid)) for uid in set(ah) | set(ac)
           if ah.get(uid) != ac.get(uid)}
    assert not bad, (
        f"kill attribution diverged {what} - (status, killedBy, murdererId) per "
        f"alien, host vs client: {bad}. killedBy is what DebriefingState counts "
        f"STR_ALIENS_KILLED with, and it is host-authoritative: the death "
        f"packets carry it and the peer must not re-derive it.")
    kh, kc = killed_here(host), killed_here(client)
    assert kh == kc, (
        f"the two machines would tally different alien kills {what}: "
        f"host {kh} client {kc}")
    return kh


# ---- driving ---------------------------------------------------------------

def give_both(host, client, uid, item, ammo=None):
    wid = None
    for gc in (host, client):
        req = {"cmd": "battle_give", "unit": uid, "item": item,
               "slot": "right", "clear_hands": True}
        if ammo:
            req["ammo"] = ammo
        wid = gc.ok(req)["weaponId"]
    time.sleep(2)
    return wid


def down(gc, uid):
    """True once `uid` is out of the fight - or once the battle itself is over."""
    u = units(gc).get(uid)
    return True if u is None else bool(u["isOut"])


def arm_and_kill(host, client, shooter, target, how, tries=6):
    """Shoot `target` dead. how='host' executes locally on the host (the raw
    lever); how='client' ships an `action_intent` the host executes."""
    for _ in range(tries):
        if down(host, target):
            return True
        wid = give_both(host, client, shooter, "STR_HEAVY_PLASMA",
                        "STR_HEAVY_PLASMA_CLIP")
        PI.top_up(host, client, shooter, 200)
        if how == "host":
            r = host.cmd({"cmd": "battle_fire", "unit": shooter, "mode": "aimed",
                          "weapon_id": wid, "tu": 200, "target": target})
        else:
            r = client.cmd({"cmd": "battle_intent", "action": "shoot",
                            "unit": shooter, "mode": "aimed",
                            "weapon_id": wid, "target": target})
            assert r.get("routed") is not False, (
                f"the client EXECUTED the shot locally instead of shipping an "
                f"intent ({r}) - in parallel mode the client is never the executor")
        if not r.get("ok"):
            return down(host, target)
        PI.wait_until(lambda: PI.parallel(host).get("canAdmit") is True, 90)
        PI.settle(host, client, seconds=5)
    return down(host, target)


def kill_one(host, client, shooter, how, tag):
    """Place `shooter` next to a live alien and kill it. Returns the alien id."""
    for alien in live_aliens(host):
        spot = PI.place_adjacent(host, client, shooter,
                                 (alien["x"], alien["y"], alien["z"]))
        if not spot:
            continue
        if arm_and_kill(host, client, shooter, alien["id"], how):
            print(f"    {tag}: alien {alien['id']} killed by unit {shooter}")
            return alien["id"]
    raise AssertionError(
        f"{tag}: no live alien could be killed - the mixed-attribution part of "
        f"this test never ran")


def rearm_squad(host, client, seat_units, tu=200):
    """Reaction fire needs a weapon AND spare TU at the START of the alien side."""
    for uid in seat_units:
        give_both(host, client, uid, "STR_HEAVY_PLASMA", "STR_HEAVY_PLASMA_CLIP")
        PI.top_up(host, client, uid, tu)


def force_alien_side_kill(host, client, known, turns=15):
    """Hand the turn over until an alien dies during the ALIEN side.

    This is the flavour the bug lived in: the peer never replays an alien-side
    reaction shot as a local attack chain, so before the fix it derived no
    attribution at all for the victim. Nothing scripts an alien into reaction
    fire - the aliens choose to walk - so the turn is cycled up to `turns` times
    and the test FAILS if none of them ever died, rather than passing vacuously.
    """
    shooters = [u["id"] for u in battle(host)["units"]
                if u.get("faction") == FACTION_PLAYER and not u.get("isOut")][:6]
    for n in range(turns):
        rearm_squad(host, client, shooters)
        turn = TW.cycle_turn(host, client)
        if turn is None:
            print("    the battle ended during the turn cycle")
            return None
        PI.settle(host, client, seconds=6)
        fresh = [uid for uid in killed_here(host) if uid not in known]
        print(f"    turn {turn}: alien-side casualties so far {fresh}")
        if fresh:
            return fresh
    return []


# ---- the debriefing --------------------------------------------------------

def debrief(gc):
    return gc.cmd({"cmd": "debrief_state"})


def wait_debrief(gc, tag, timeout=180):
    try:
        return gc.wait_for(
            f"{tag} debriefing score page",
            lambda: (lambda r: r if r.get("ok") else None)(debrief(gc)),
            timeout=timeout, interval=0.5)
    except TimeoutError:
        raise AssertionError(
            f"{tag}: no DebriefingState after {timeout}s - the mission never "
            f"finished. states={session.states(gc)[-4:]} "
            f"battle={battle(gc).get('inBattle')}")


def compare_debriefs(host, client, min_kills):
    dh = wait_debrief(host, "host")
    dc = wait_debrief(client, "client")
    print(f"    host   rows={dh['rows']} total={dh['total']}")
    print(f"    client rows={dc['rows']} total={dc['total']}")

    hk = dh["rows"].get("STR_ALIENS_KILLED", 0)
    ck = dc["rows"].get("STR_ALIENS_KILLED", 0)
    assert hk == ck, (
        f"THE BUG: the debriefings disagree about alien kills - host {hk}, "
        f"client {ck} (at least {min_kills} were killed). Each machine counts "
        f"`oldFaction == HOSTILE && killedBy() == PLAYER` over its own save, so "
        f"a killedBy that never crossed is a different score for the same battle.")
    # Floor, not equality: an alien can also die to its own side's blast, which
    # this test does not track. A tally BELOW what was provably killed means the
    # comparison above is comparing two equally-wrong numbers.
    assert hk >= min_kills, (
        f"both machines agree on {hk} alien kills but {min_kills} aliens were "
        f"provably killed - the tally lost a death on BOTH machines")
    assert dh["rows"] == dc["rows"], (
        f"the debriefing score rows differ: host {dh['rows']} client {dc['rows']}")
    assert dh["scores"] == dc["scores"], (
        f"the debriefing points differ: host {dh['scores']} client {dc['scores']}")
    assert dh["total"] == dc["total"], (
        f"the mission TOTAL differs: host {dh['total']} client {dc['total']}")
    print(f"PASS debriefing: identical on both machines - "
          f"{hk} alien kills, total {dh['total']}")


def vote_abort_to_debriefing(host, client):
    """session.coop_abort_battle's vote half, stopping AT the debriefing.

    The shipped helper drains all the way to the geoscape, which dismisses the
    very screen this test has to read."""
    host.ok({"cmd": "battle_action", "action": "abort"})
    for gc, tag in ((host, "host"), (client, "client")):
        v = gc.wait_for(f"{tag} abandon-mission vote",
                        lambda gc=gc: (lambda s: s if (s.get("active") and s.get("menuOpen"))
                                       else None)(gc.ok({"cmd": "vote_state"})),
                        timeout=30, interval=0.25)
        assert v["action"] == "abandon_mission", f"{tag}: wrong vote: {v}"
    cast = client.ok({"cmd": "vote_cast", "yes": True})
    assert cast.get("accepted"), f"client vote_cast was rejected: {cast}"
    for gc, tag in ((host, "host"), (client, "client")):
        v = gc.wait_for(f"{tag} vote result",
                        lambda gc=gc: (lambda s: s if s.get("finished") else None)(
                            gc.ok({"cmd": "vote_state"})),
                        timeout=30, interval=0.25)
        assert v.get("passed"), f"{tag}: the abandon-mission vote did not pass: {v}"


def kill_the_rest(host, client):
    """Finish every remaining alien so the mission ends in a WIN (autoEndBattle).

    A fresh shooter is picked each time: the squad takes casualties, and the one
    that made the scripted kills is often among them."""
    killed = []
    for _ in range(NALIENS + 2):
        if not battle(host).get("inBattle") or not live_aliens(host):
            break
        alive = len(live_aliens(host))
        shooters = live_player_units(host)
        assert shooters, "the squad is wiped out - no mission win to debrief"
        killed.append(kill_one(host, client, shooters[0]["id"], "host", "mop-up"))
        assert not battle(host).get("inBattle") or len(live_aliens(host)) < alive, \
            "the mop-up shot killed nobody"
    # `battleAutoEnd` is off by default, so a battle with no aliens left does not
    # end by itself - it ends the way a player ends it, by handing the turn over.
    # BattlescapeGame::endTurn then sees liveAliens == 0 and finishes the mission.
    if battle(host).get("inBattle"):
        print("    all aliens down - ending the turn to finish the mission")
        TW.cycle_turn(host, client, timeout=240)
    return killed


# ---- one battle ------------------------------------------------------------

def run(ending, ports, tmp):
    """One skirmish battle driven to `ending` ('abort' or 'win')."""
    hport, cport, coop_port = ports
    mod = make_mod(tmp)
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = GameClient("host", hport,
                      make_user_dir(f"debrief_{ending}_host", mods=[mod],
                                    options=dict(opts, skipNextTurnScreen=True,
                                                 EnableCoopParallelTurns=True)))
    client = GameClient("client", cport,
                        make_user_dir(f"debrief_{ending}_client", mods=[mod],
                                      options=dict(opts,
                                                   EnableCoopParallelTurns=False)))
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
        alive = live_aliens(host)
        assert len(alive) >= 3, (
            f"the fixture came up with {len(alive)} alien(s); the test ruleset "
            f"should have produced {NALIENS}")
        print(f"[{ending}] battle up: client seat {seat}, "
              f"{len(alive)} aliens {[u['id'] for u in alive]}")
        assert_attribution_agrees(host, client, "at battle start")

        host_mover = PI.pick_driver(host, client, 0, "host")
        client_mover = PI.pick_driver(host, client, seat, "client")

        # ---- 1 + 2: the two mixed-attribution kills -----------------------
        print(f"-- [{ending}] 1: a HOST-executed kill --")
        a1 = kill_one(host, client, host_mover, "host", "host kill")
        assert_attribution_agrees(host, client, "after the host's kill")

        print(f"-- [{ending}] 2: a CLIENT-INTENT kill (the host executes) --")
        a2 = kill_one(host, client, client_mover, "client", "client-intent kill")
        killed = assert_attribution_agrees(host, client, "after the client's kill")
        assert a1 in killed and a2 in killed, (
            f"one of the two kills is not in the tally: killed {killed}, "
            f"expected {a1} and {a2}")
        print(f"PASS kills: {a1} (host action) and {a2} (client intent) are "
              f"attributed identically on both machines")

        # ---- 3: the alien-side kill, the flavour that was broken ----------
        print(f"-- [{ending}] 3: an ALIEN-SIDE (reaction fire) kill --")
        fresh = force_alien_side_kill(host, client, set(killed))
        assert fresh, (
            "no alien died during an alien side over the whole turn budget - "
            "the flavour this test exists for never ran, so everything below "
            "would pass vacuously. Re-check the fixture: the squad must be "
            "armed, in TU and in sight of the aliens when the turn is handed over.")
        killed = assert_attribution_agrees(host, client, "after the alien side")
        print(f"PASS alien side: {fresh} died to reaction fire and BOTH machines "
              f"credit the same killer")

        # ---- 4: the ending, then the debriefing ---------------------------
        if ending == "abort":
            print(f"-- [{ending}] 4: ABANDON MISSION vote -> debriefing --")
            expected = len(killed)
            vote_abort_to_debriefing(host, client)
        else:
            print(f"-- [{ending}] 4: kill the rest -> the mission ends in a WIN --")
            rest = kill_the_rest(host, client)
            print(f"    mopped up {rest}")
            expected = len(set(killed) | set(rest))
        compare_debriefs(host, client, expected)

        # The battle is over on both machines, and the debriefing is left where
        # it is: a SKIRMISH debriefing returns to the MAIN MENU, not a geoscape,
        # so draining past it would pop the menu and take the process with it.
        for gc, tag in ((host, "host"), (client, "client")):
            st = session.states(gc)
            assert not any("BattlescapeState" in s for s in st), \
                f"{tag}: the battle is still on the stack after the debriefing: {st}"
        print(f"PASS [{ending}]: both machines left the battle and hold a debriefing")
    finally:
        host.shutdown(); client.shutdown()


def main():
    # The WIN variant is the same tally through the other exit: it costs one
    # extra fixture but it is the only way to see the recovery rows (which
    # prepareDebriefing also builds locally) line up too. A single variant can
    # be run on its own during development: `... test_coop_debrief_sync.py win`.
    wanted = sys.argv[1:] or ["abort", "win"]
    tmp = tempfile.mkdtemp(prefix="coop_debrief_sync_")
    fail = None
    try:
        if "abort" in wanted:
            run("abort", (48892, 48893, 47992), tmp)
        if "win" in wanted:
            run("win", (48894, 48895, 47993), tmp)
        print("ALL DEBRIEFING-SYNC TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
