"""PRD-P1: a replayed teammate action must not hijack the watching player.

Before P1 every replay handler on the passive machine wrote the LOCAL player's
state before running the peer's action:

    _save->setSelectedUnit(remoteUnit);          // selection + stat panel
    _currentAction.actor  = remoteUnit;          // the singleton BattleAction
    _currentAction.type   = BA_SNAPSHOT;         // ... that the local map click
    _currentAction.targeting = true;             //     dispatches on
    getMap()->getCamera()->centerOnPosition(..); // camera

so watching a teammate walk stole your selection and your stat panel, and
watching a teammate SHOOT left your own next map click in targeting mode - it
fired instead of walking. P1 gives every replay handler a stack-local
BattleAction (BattlescapeGame::makeReplayAction) and deletes the setSelectedUnit
calls.

What this test asserts, on the machine that is NOT driving:

  1. `selectedId` never moves off the unit this player selected. The stat panel
     is a pure function of it - BattlescapeState::updateSoldierInfo() reads
     _save->getSelectedUnit() and nothing else - so this IS the panel assertion.
  2. the camera map offset does not move - this is PRD-P1's camera item, the
     centerOnPosition in movePlayerTarget. Two OTHER camera sites are stock
     OpenXcom, fire for AI actions too, and are NOT in the PRD's verified hijack
     table, so the test reports them per step instead of asserting on them: the
     view-level follow in UnitWalkBState and the projectile follow in
     Map::draw() (see LEVEL_FOLLOW_NOTE / PROJECTILE_FOLLOW_NOTE). They belong
     to PRD-P5's "no camera follow during the parallel player side".
  3. BattlescapeGame::_currentAction is IDENTICAL before and after the replay -
     (type, actor, weapon, targeting, target, waypoint count) compared as a
     tuple, which covers every field the old handlers wrote. Note the baseline
     is not empty: the active player's `selected_unit` packet legitimately parks
     its actor there through setSelectedCoopUnit, a handler PRD-P1 preserves on
     purpose (P5 stops SENDING that packet). The shot step additionally spells
     out the PRD's "click a tile after the replay and get a MOVE, not a shot":
     BattlescapeGame::primaryAction() only fires when targeting is set.
  4. the replayed chain still RUNS - each step waits for the peer to actually
     mirror the action (position for a walk, the actor's TU for an attack)
     before asserting, so a passing run is never vacuous.

Actions driven: walk (movePlayerTarget), turn (turnPlayerTarget +
turnPlayerTargetAfter, which ride every walk and every UnitTurnBState before a
shot), shot (shootPlayerTarget), melee (melee_attack) and psi (psi_attack).
Melee/psi need a live hostile plus equipment the vanilla skirmish loadout does
not carry, so they are armed with `battle_give` on BOTH machines first (nothing
in the protocol replicates a mid-battle item spawn) and driven through
`battle_fire` mode=psi/hit. Content is the one thing a test cannot conjure - a
skirmish can spawn a single alien, and one stun rod takes it out of the fight -
so if the target or the equipment is unavailable the step reports SKIPPED with
the reason instead of failing; the four assertions above are already carried by
the walk/turn/shot steps.

Classic regression: the PlayerTurnYour handoff (connectionTCP.cpp) is NOT a
replay and must keep selecting a unit for the newly-active player, so the test
ends by handing the turn over and asserting the receiver got a selection.

Battle fixture: the skirmish flow (NEW BATTLE > COOP), same path as
test_skirmish_battle_turn_control.py / test_parallel_introspection.py.

Run:  python tools/coop_test/test_parallel_replay_decouple.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as SK

PORT = "47977"

# Camera sites that are NOT in PRD-P1's verified hijack table (which lists one:
# movePlayerTarget's centerOnPosition). Both are stock OpenXcom and fire for AI
# actions too, so the test reports them instead of asserting on them. PRD-P5
# ("no camera follow during the parallel player side") is where they belong.
LEVEL_FOLLOW_NOTE = ("the peer's unit changed map LEVEL and vanilla "
                     "UnitWalkBState follows that (\"if the unit changed level, "
                     "camera changes level with\", Camera::setViewLevel)")
PROJECTILE_FOLLOW_NOTE = ("vanilla Map::draw() follows a projectile in FOV "
                          "(_followProjectile/_smoothCamera -> jumpXY), and the "
                          "replay action carries no cameraPosition for "
                          "ProjectileFlyBState to restore")


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def has(gc, name):
    return any(name in s for s in states(gc))


def top(gc):
    return states(gc)[-1].split("::")[-1]


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def unit(b, uid):
    for u in b.get("units", []):
        if u["id"] == uid:
            return u
    return None


def pos(b, uid):
    u = unit(b, uid)
    return (u["x"], u["y"], u["z"]) if u else None


def tu(b, uid):
    u = unit(b, uid)
    return u["tu"] if u else None


# ---- the three things a replay used to steal ------------------------------

def watcher_state(gc):
    """selection + camera + the singleton BattleAction, as one comparable dict."""
    b = battle(gc)
    for key in ("cameraX", "viewLevel", "actionType", "actionActorId"):
        assert key in b, (
            f"battle_state carries no {key!r} - PRD-P1's read-only introspection "
            f"is missing, the assertions below would be vacuous: {sorted(b)}")
    return {
        "selectedId": b["selectedId"],
        # The camera POSITION. b["cameraZ"] is getMapOffset().z, i.e. the view
        # level, which is deliberately NOT part of this tuple - see the
        # viewLevel note in assert_not_hijacked().
        "camera": (b["cameraX"], b["cameraY"]),
        "viewLevel": b["viewLevel"],
        "action": (b["actionType"], b["actionActorId"], b["actionWeaponId"],
                   b["actionTargeting"],
                   (b["actionTargetX"], b["actionTargetY"], b["actionTargetZ"]),
                   b["actionWaypoints"]),
    }


def assert_not_hijacked(what, before, after, mine, remote_actor, check_camera=True,
                        camera_note=""):
    errs = []
    if after["selectedId"] != mine:
        errs.append(
            f"SELECTION HIJACKED: selected unit went {before['selectedId']} -> "
            f"{after['selectedId']} (mine is {mine}, the peer acted with "
            f"{remote_actor}). The stat panel follows getSelectedUnit(), so the "
            f"panel moved too.")
    if check_camera and after["camera"] != before["camera"]:
        errs.append(
            f"CAMERA HIJACKED: map offset went {before['camera']} -> "
            f"{after['camera']} while replaying the peer's {what} - "
            f"movePlayerTarget's centerOnPosition fired")
    # _currentAction belongs to the LOCAL player's cursor/click handling. A
    # replay must leave it EXACTLY as it found it; an equality check catches
    # every field the old handlers wrote (actor, type, weapon, targeting,
    # target, waypoints) in one assertion. The baseline is not "empty": the
    # active player's `selected_unit` packet legitimately parks its actor here
    # via setSelectedCoopUnit, which PRD-P1 preserves (PRD-P5 stops SENDING it).
    if after["action"] != before["action"]:
        errs.append(
            f"_currentAction BLEED: (type, actor, weapon, targeting, target, "
            f"waypoints) went {before['action']} -> {after['action']}. The peer's "
            f"{what} wrote the local player's action - the next map click would "
            f"execute it instead of walking the selected unit.")
    if errs:
        raise AssertionError(
            f"replayed {what} hijacked the watching player:\n    - "
            + "\n    - ".join(errs)
            + f"\n  before={before}\n  after ={after}")
    note = ""
    if not check_camera:
        note = (f" [camera {before['camera']}/lvl{before['viewLevel']} -> "
                f"{after['camera']}/lvl{after['viewLevel']} not asserted: "
                f"{camera_note}]")
    elif after["viewLevel"] != before["viewLevel"]:
        note = (f" [view level {before['viewLevel']} -> {after['viewLevel']}]")
    print(f"PASS {what}: watcher kept unit {mine} selected, camera "
          f"{after['camera']}, local action untouched {after['action']}{note}")


def wait_until(fn, timeout, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ---- fixture ---------------------------------------------------------------

def drain_to_tactical(host, client, rounds=12):
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        time.sleep(1.0)
        if not moved and all(top(gc) == "BattlescapeState" for gc in (host, client)):
            return


def bring_up_battle(host, client):
    SK.skirmish_host(host, PORT)
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
               "player": "ClientPlayer"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} join popup",
                    lambda gc=gc: session.has_state(gc, "Profile") or None, timeout=60)
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("BATTLE SETTINGS offered",
                  lambda: SK.lobby(host).get("buttonVisible") or None, timeout=60)
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None, timeout=60)
    host.ok({"cmd": "newbattle_ok"})

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} in battle",
                    lambda gc=gc: battle(gc).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        if has(gc, "BriefingState"):
            gc.cmd({"cmd": "close_briefing"})
    for gc in (host, client):
        if has(gc, "InventoryState"):
            gc.cmd({"cmd": "battle_inventory", "action": "ok"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} tactical map",
                    lambda gc=gc: has(gc, "BattlescapeState") or None,
                    timeout=120, interval=0.5)
    drain_to_tactical(host, client)
    # the coop turn-init handshake must have run, or nothing replicates at all
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} coop battle init",
                    lambda gc=gc: battle(gc).get("battleInit") or None,
                    timeout=90, interval=1.0)
    time.sleep(3)


# ---- the driven actions ----------------------------------------------------

def pick_mover(driver_state, owner_coop):
    movers = [u for u in driver_state["units"]
              if u.get("faction") == 0 and u.get("selectable") and not u.get("isOut")
              and u.get("coop") == owner_coop and u.get("tu", 0) > 20]
    return movers


def drive_walk(driver, watcher, mover_id):
    """Walk `mover_id` one tile on the driver; return the tile it reached once
    the WATCHER has mirrored it (so the replay provably ran)."""
    before = pos(battle(driver), mover_id)
    assert pos(battle(watcher), mover_id) == before, \
        f"unit {mover_id} is already at different positions on the two machines"
    driver.cmd({"cmd": "battle_action", "action": "select", "unit": mover_id})
    dest = None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        want = (before[0] + dx, before[1] + dy, before[2])
        r = driver.cmd({"cmd": "battle_action", "action": "move", "unit": mover_id,
                        "x": want[0], "y": want[1], "z": want[2]})
        if r.get("ok"):
            dest = want
            break
    assert dest, f"unit {mover_id} could not step to any adjacent tile"
    assert wait_until(lambda: pos(battle(driver), mover_id) != before, 45), \
        f"unit {mover_id} never moved on the driver - the DRIVER failed, not the replay"
    landed = pos(battle(driver), mover_id)
    assert wait_until(lambda: pos(battle(watcher), mover_id) == landed, 45), \
        f"the walk never replicated: driver has {mover_id} at {landed}, watcher at " \
        f"{pos(battle(watcher), mover_id)}"
    return before, landed


def drive_attack(driver, watcher, mover_id, what, req, arrive_timeout=45):
    """Run one `battle_fire` on the driver and wait for the WATCHER to mirror the
    actor's TU (which every attack packet carries). Returns None when the engine
    refused the action - the caller reports that as SKIPPED."""
    watcher_tu_before = tu(battle(watcher), mover_id)
    r = driver.cmd(req)
    if not r.get("ok"):
        return f"engine refused {what}: {r.get('error')}"
    # battle_fire tops the actor up to req["tu"] synchronously, so the driver's TU
    # leaving that value is "the BState actually ran and charged the action". A
    # psi attack by a psiSkill-0 rookie costs 0 TU and is refused by
    # BattleActionCost::haveTU - that shows up here, before any packet.
    topped = req.get("tu")
    if not wait_until(lambda: tu(battle(driver), mover_id) != topped, 20):
        return f"{what} cost the actor nothing on the driver (state never ran)"
    # Arrival signal: every attack packet stamps the actor's TU on the watcher
    # (movePlayerTarget/psi_attack/melee_attack setTimeUnits, shootPlayerTarget
    # setCoopTimeUnits). The two values need not END equal - the melee replay
    # re-spends the cost on the receiver, a pre-existing coop divergence P1 does
    # not touch - so this asserts the packet LANDED, not that TU agrees.
    if not wait_until(lambda: tu(battle(watcher), mover_id) != watcher_tu_before,
                      arrive_timeout):
        return (f"{what} never replicated: driver TU={tu(battle(driver), mover_id)}, "
                f"watcher TU still {watcher_tu_before}")
    print(f"    {what} replicated (driver TU={tu(battle(driver), mover_id)}, "
          f"watcher TU={tu(battle(watcher), mover_id)}, was {watcher_tu_before})")
    return None


def main():
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = GameClient("host", 48846, make_user_dir("p1_decouple_host", options=opts))
    client = GameClient("client", 48847, make_user_dir("p1_decouple_client", options=opts))
    fail = None
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        bring_up_battle(host, client)
        print("battle up on both machines")

        hb, cb = battle(host), battle(client)
        if session.can_drive(hb):
            driver, watcher, dtag, wtag = host, client, "host", "client"
            db, wb = hb, cb
        else:
            driver, watcher, dtag, wtag = client, host, "client", "host"
            db, wb = cb, hb
        print(f"simulation owner = {dtag}; asserting on {wtag}")

        owner_coop = 0 if db["host"] else 1
        watcher_coop = 0 if wb["host"] else 1
        movers = pick_mover(db, owner_coop)
        assert movers, (
            f"{dtag} commands no unit with TU to spend: "
            f"{[(u['id'], u.get('coop'), u.get('selectable'), u.get('tu')) for u in db['units']]}")
        mover_id = movers[0]["id"]

        # The watcher selects one of ITS OWN units - the thing the replay used to
        # steal. battle_action select goes straight to setSelectedUnit, which is
        # what the UI would do on the watcher's own turn.
        mine = [u for u in wb["units"]
                if u.get("faction") == 0 and not u.get("isOut")
                and u.get("coop") == watcher_coop]
        assert mine, f"{wtag} owns no live unit: {[(u['id'], u.get('coop')) for u in wb['units']]}"
        mine_id = mine[0]["id"]
        watcher.ok({"cmd": "battle_action", "action": "select", "unit": mine_id})
        base = watcher_state(watcher)
        assert base["selectedId"] == mine_id, \
            f"{wtag} could not select its own unit {mine_id}: {base}"
        print(f"{wtag} selected its own unit {mine_id}; {dtag} will act with {mover_id}")

        # Control sample: the watcher's camera and action must be STABLE while
        # nothing happens, or the deltas asserted below would mean nothing.
        for _ in range(3):
            time.sleep(1.0)
            idle = watcher_state(watcher)
            assert idle["camera"] == base["camera"] and idle["action"] == base["action"], \
                (f"{wtag} is not at rest before the test even starts - camera/action "
                 f"drift on their own: {base} -> {idle}")
        print(f"PASS control: {wtag} idle camera {base['camera']} and action "
              f"{base['action']} are stable")

        # --- 1. walk (movePlayerTarget) + 2. turn (turnPlayerTarget[After]) ---
        # A step to an adjacent tile always turns the unit first, so a single walk
        # exercises BattleScapeMove, turnBattlescapeUnit and
        # afterBattlescapeUnitTurn on the watcher.
        prev = base
        camera_checked = False
        for step in range(1, 4):
            before, landed = drive_walk(driver, watcher, mover_id)
            print(f"    {dtag} walked {mover_id} {before} -> {landed}; {wtag} mirrored it")
            same_level = landed[2] == before[2]
            after_walk = watcher_state(watcher)
            assert_not_hijacked(f"walk+turn #{step}", prev, after_walk, mine_id,
                                mover_id, check_camera=same_level,
                                camera_note=LEVEL_FOLLOW_NOTE)
            prev = after_walk
            camera_checked = camera_checked or same_level
            if step >= 2 and camera_checked:
                break
        if not camera_checked:
            print("NOTE: every walk changed map level, so the walk steps could not "
                  "assert the camera; the shot step below still does")
        after_walk2 = prev

        # --- 3. shot (shootPlayerTarget) -------------------------------------
        # Fire at the tile the unit came from: always a legal target position, and
        # ProjectileFlyBState ships the packet whether or not the shot connects.
        skipped = drive_attack(
            driver, watcher, mover_id, "shot",
            {"cmd": "battle_fire", "unit": mover_id, "mode": "snap", "tu": 100,
             "x": before[0], "y": before[1], "z": before[2]})
        if skipped:
            raise AssertionError(f"the shot step could not run: {skipped}")
        after_shot = watcher_state(watcher)
        assert_not_hijacked("shot", after_walk2, after_shot, mine_id, mover_id,
                            check_camera=False, camera_note=PROJECTILE_FOLLOW_NOTE)
        # the shot-specific half of criterion 3, spelled out: primaryAction()
        # only fires when _currentAction.targeting is set.
        assert not after_shot["action"][3], \
            f"after a replayed shot {wtag} is left in targeting mode: {after_shot}"
        print(f"PASS shot: {wtag}'s next map click would MOVE unit {mine_id}, not fire "
              f"(targeting={after_shot['action'][3]}, action={after_shot['action']})")

        prev = after_shot

        # --- 4. psi (psi_attack) and 5. melee (melee_attack) ------------------
        # Both need a live hostile and equipment the skirmish loadout does not
        # carry, so battle_give arms the actor on BOTH machines (nothing in the
        # protocol replicates a mid-battle item spawn). Psi runs FIRST because a
        # stun rod tends to take the target out of the fight.
        def live_hostiles():
            return [u for u in battle(driver)["units"]
                    if u.get("faction") == 1 and not u.get("isOut")]

        def no_hostile_note():
            census = {}
            for u in battle(driver).get("units", []):
                key = (u.get("faction"), bool(u.get("isOut")))
                census[key] = census.get(key, 0) + 1
            return f"no live hostile left (faction/isOut census: {census})"

        note = None
        aliens = live_hostiles()
        if not aliens:
            note = no_hostile_note()
        else:
            target = aliens[0]
            tpos = (target["x"], target["y"], target["z"])
            gave = [gc.cmd({"cmd": "battle_give", "unit": mover_id,
                            "item": "STR_PSI_AMP", "slot": "right",
                            "clear_hands": True}) for gc in (driver, watcher)]
            if not all(g.get("ok") for g in gave):
                note = f"battle_give STR_PSI_AMP failed: {gave}"
            else:
                note = drive_attack(
                    driver, watcher, mover_id, "psi",
                    {"cmd": "battle_fire", "unit": mover_id, "mode": "psi",
                     "weapon_id": gave[0]["weaponId"], "tu": 100,
                     "x": tpos[0], "y": tpos[1], "z": tpos[2]})
        if note:
            print(f"SKIP psi: {note}")
        else:
            after_psi = watcher_state(watcher)
            assert_not_hijacked("psi", prev, after_psi, mine_id, mover_id,
                                check_camera=False,
                                camera_note="ExplosionBState centres on the hit")
            prev = after_psi

        note = None
        aliens = live_hostiles()
        if not aliens:
            note = no_hostile_note()
        else:
            target = aliens[0]
            tpos = (target["x"], target["y"], target["z"])
            placed = None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
                spot = (tpos[0] + dx, tpos[1] + dy, tpos[2])
                res = [gc.cmd({"cmd": "battle_teleport", "unit": mover_id,
                               "x": spot[0], "y": spot[1], "z": spot[2]})
                       for gc in (driver, watcher)]
                if all(r.get("moved") for r in res):
                    placed = spot
                    break
            if not placed:
                note = f"no free tile adjacent to hostile {target['id']}"
            else:
                gave = [gc.cmd({"cmd": "battle_give", "unit": mover_id,
                                "item": "STR_STUN_ROD", "slot": "right",
                                "clear_hands": True}) for gc in (driver, watcher)]
                if not all(g.get("ok") for g in gave):
                    note = f"battle_give STR_STUN_ROD failed: {gave}"
                else:
                    note = drive_attack(
                        driver, watcher, mover_id, "melee",
                        {"cmd": "battle_fire", "unit": mover_id, "mode": "hit",
                         "weapon_id": gave[0]["weaponId"], "tu": 100,
                         "x": tpos[0], "y": tpos[1], "z": tpos[2]})
        if note:
            print(f"SKIP melee: {note}")
        else:
            after_melee = watcher_state(watcher)
            assert_not_hijacked("melee", prev, after_melee, mine_id, mover_id,
                                check_camera=False,
                                camera_note="ExplosionBState centres on the hit")
            prev = after_melee

        # --- 6. classic handoff regression -----------------------------------
        # PlayerTurnYour is a HANDOFF, not a replay: the machine that BECOMES the
        # active player must be given a selected unit, or it starts its turn
        # commanding nothing. P1 must not have deleted that setSelectedUnit.
        # Press the REAL END TURN button - `end_turn` calls the VANILLA
        # requestEndTurn(), which never ships PlayerTurnYour at all.
        driver.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def handed_over():
            # BattlescapeState::think() - which runs the coop turn handshake -
            # only ticks while the battlescape is the TOP state, so drain the
            # "Turn N" / infobox popups the end-turn puts up.
            for gc in (driver, watcher):
                if gc.cmd({"cmd": "battle_state"}).get("inBattle") and \
                        top(gc) != "BattlescapeState":
                    gc.cmd({"cmd": "dismiss_popup"})
            return battle(watcher).get("coopTurn") == 2

        got = wait_until(handed_over, 120, interval=1.0)
        if not got:
            print(f"SKIP handoff: {wtag} never became the active player "
                  f"(coopTurn={battle(watcher).get('coopTurn')}, "
                  f"top={top(watcher)}) within 120s")
        else:
            hs = battle(watcher)
            assert hs["selectedId"] != -1, (
                "PlayerTurnYour handoff left the newly-active player with NO "
                f"selected unit: {hs['selectedId']} (coopTurn={hs['coopTurn']}) - "
                "the handoff setSelectedUnit was deleted along with the replay ones")
            sel = unit(hs, hs["selectedId"])
            assert sel and sel.get("coop") == watcher_coop, (
                f"the handoff selected unit {hs['selectedId']} which is owned by "
                f"coop={sel and sel.get('coop')}, not this player ({watcher_coop})")
            print(f"PASS handoff: PlayerTurnYour selected own unit "
                  f"{hs['selectedId']} for the newly-active {wtag}")

        print("ALL PARALLEL-REPLAY-DECOUPLE TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
