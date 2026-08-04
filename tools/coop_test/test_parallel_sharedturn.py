"""PRD-P5: the parallel shared player side.

With `EnableCoopParallelTurns` on, a co-op PVE battle stops alternating sub-turns:
both machines hold the player side at once, with full UI, for the whole side. The
piece that makes that cheap is the EXECUTOR INVARIANT (PROTOCOL.md "Core
invariant"):

    _isActivePlayerSync == getHost()      - permanently, host TRUE / client FALSE

Every executor-gated site in the battle (BState packet sends, the projectile RNG
pre-rolls, reaction fire, the ambient sim) is therefore correct with no per-site
refactor: the host always executes and broadcasts, the client never does. Until
PRD-P6 lands `action_intent`, the client's own input is simply swallowed - that
is a shippable intermediate (host-only acting), not the finished feature.

What this test asserts (PRD-P5 acceptance):

  1. Option on, PVE battle: `battle_state.coopTurn == 2` on BOTH machines,
     `activeSync` true on the host and FALSE on the client (the invariant, NOT a
     driver-selection flag any more), `parallelActive` true on both. The client's
     OWN option value is irrelevant - here it is deliberately off, and the client
     still runs in parallel mode because the host's value rode the handshake.
  2. No off-turn banners on either machine. They are persistent
     (`showCoopWarning` -> `showMessage(msg, -1)`, repainted every frame), so one
     left behind would squat on the warning widget for the rest of the battle and
     block the deny/ready flashes P6/P8 put through it.
  3. `clientInputBlocked` (= "this machine is a parallel CLIENT") is true on the
     client and false on the host; the client's REAL END TURN button still does
     nothing, because END TURN stays host-only until PRD-P8's readiness tally;
     and a LOCALLY EXECUTED client action does not replicate (the send guards
     read `_isActivePlayerSync`, which the client holds false). PRD-P6 removed
     the blanket input gate and the `coopParallelDebugClientInput` debug switch
     that went with it - a client's real input now travels as an `action_intent`
     (test_parallel_intents.py); `battle_action move` deliberately still executes
     locally, which is what makes it the right lever for this assertion.
  4. A full side boundary: the host ends the turn (there is no mid-side hand-off
     left - no `PlayerTurnYour`), the alien side runs, and the player side comes
     back with the invariant re-asserted. A host shot after the boundary lands
     identically on both machines.
  5. Old-build degrade (phase A, its own short-lived pair, no battle): a host that
     never asks for parallel turns leaves BOTH machines classic even when the
     client's own option is on. An older peer sends no `enable_parallel_turns`
     key at all, which the receiver reads as false - the same outcome.

NOTE on driving: `battle_action move` pushes a UnitWalkBState directly and so
bypasses BattlescapeState::mapClick, where PRD-P6's intent capture lives. That
makes it the right lever for the "does a LOCAL action REPLICATE" half of 3, and
the wrong one for anything about the capture path - that is
test_parallel_intents.py's `battle_intent` lever. The END TURN half is asserted
through a real handler the harness can press
(`battle_action end_turn_button` -> btnEndTurnClick).

Battle fixture: the skirmish flow (NEW BATTLE > COOP), same path as
test_battle_tripwire.py / test_parallel_introspection.py.

Run:  python tools/coop_test/test_parallel_sharedturn.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as SK
import test_battle_tripwire as TW

PORT = "47983"       # phase B (the battle)
PORT_DEGRADE = "47984"  # phase A (lobby only)

# Every persistent banner PRD-P5 §3 drops for the parallel player side. Matched
# as substrings against battle_state["warning"], which is "" when the warning
# widget is hidden.
FORBIDDEN_BANNERS = ("'s Turn", "Waiting for", "spectator mode")


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def unit(b, uid):
    for u in b.get("units", []):
        if u["id"] == uid:
            return u
    return None


def pos(b, uid):
    u = unit(b, uid)
    return (u["x"], u["y"], u["z"]) if u else None


def health(b, uid):
    u = unit(b, uid)
    return u["health"] if u else None


def own_units(state, seat):
    return [u for u in state["units"]
            if u.get("faction") == 0 and not u.get("isOut")
            and u.get("coop") == seat and u.get("tu", 0) > 20]


def alive_enemy(state):
    for u in state["units"]:
        if u.get("faction") == 1 and not u.get("isOut") and u.get("health", 0) > 0:
            return u
    return None


def wait_until(fn, timeout, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def settle(host, client, seconds=8):
    """Let both state machines drain. NextTurnState and the battlescape itself are
    never dismissed (session.NO_DISMISS_STATES + the host's NextTurnState must
    self-close, it is what ships `next_turn`)."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        for gc in (host, client):
            t = TW.top(gc)
            if t not in ("BattlescapeState", "NextTurnState"):
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.5)


# ---- phase A: the host's option decides; a host that never asks stays classic --

def phase_degrade():
    """A host with the option OFF (which is also what an older build is - it sends
    no `enable_parallel_turns` key at all, and the receiver defaults it to false)
    leaves BOTH machines classic, even though this client's own option is ON.
    Lobby only: the mode is frozen by the COOP_READY_HOST handshake at JOIN time,
    long before a battle exists, so no battle is needed to prove it."""
    host = GameClient("host", 48862,
                      make_user_dir("p5_degrade_host",
                                    options={"EnableCoopParallelTurns": False}))
    client = GameClient("client", 48863,
                        make_user_dir("p5_degrade_client",
                                      options={"EnableCoopParallelTurns": True}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # Pin the client's OWN option ON before the handshake - otherwise the
        # assertion below (that the client still ends up classic) proves nothing.
        got = client.ok({"cmd": "set_option", "name": "EnableCoopParallelTurns",
                         "value": True})
        assert got.get("value") is True, (
            f"could not turn the client's own EnableCoopParallelTurns on: {got}")

        SK.skirmish_host(host, PORT_DEGRADE)
        SK.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT_DEGRADE,
                   "player": "ClientPlayer"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} join popup",
                        lambda gc=gc: session.has_state(gc, "Profile") or None,
                        timeout=60)
            gc.ok({"cmd": "profile_ok"})
        host.wait_for("BATTLE SETTINGS offered",
                      lambda: SK.lobby(host).get("buttonVisible") or None, timeout=60)
        # the handshake has crossed by now
        time.sleep(3)

        # `parallel_state` needs a live battle; the mode is a SESSION property, so
        # read it off get_coop while both machines sit in the lobby.
        for gc, tag in ((host, "host"), (client, "client")):
            ps = gc.ok({"cmd": "get_coop"})
            assert ps["parallelEnabled"] is False, (
                f"{tag}: the session mirrored parallelEnabled=True although the "
                f"HOST's option is off - the client's own option must never "
                f"decide the mode: {ps}")
            assert ps["parallelActive"] is False, \
                f"{tag}: parallelActive true with the mode off: {ps}"
            assert ps["clientInputBlocked"] is False, \
                f"{tag}: the §4 input gate is armed in classic mode: {ps}"
        print("PASS degrade: a host that does not ask for parallel turns leaves "
              "BOTH machines classic (an older peer sends no key at all, which "
              "reads the same) - the client's own option is ignored")
    finally:
        host.shutdown(); client.shutdown()


# ---- phase B assertions ----------------------------------------------------

def assert_invariant(host, client, what):
    hb, cb = battle(host), battle(client)
    for b, tag in ((hb, "host"), (cb, "client")):
        assert b.get("inBattle"), f"{tag}: not in a battle {what}: {b.get('inBattle')}"
        assert b["parallelActive"] is True, \
            f"{tag}: parallelActive is not true {what}: {b['parallelActive']}"
        assert b["parallelEnabled"] is True, \
            f"{tag}: the handshake mirror is off {what}: {b['parallelEnabled']}"
        assert b["coopTurn"] == 2, (
            f"{tag}: coopTurn is {b['coopTurn']}, not 2 {what} - in parallel mode "
            f"BOTH machines hold the player side (1 = the peer's turn, 3 = waiting "
            f"for battle init, 4 = spectator)")
    assert hb["activeSync"] is True, (
        f"EXECUTOR INVARIANT broken {what}: the host is not the executor "
        f"(activeSync={hb['activeSync']}). Every BState send guard and RNG pre-roll "
        f"reads this flag; with it false the host stops broadcasting.")
    assert cb["activeSync"] is False, (
        f"EXECUTOR INVARIANT broken {what}: the CLIENT is an executor "
        f"(activeSync={cb['activeSync']}). Both machines would then broadcast and "
        f"author RNG - the battle-wide divergence PRD-P5 exists to prevent.")
    return hb, cb


def assert_no_banners(host, client, what, seconds=8.0):
    """Sampled, not a single snapshot: think() re-posts a persistent banner every
    frame, so one that is being posted shows up on ANY sample."""
    deadline = time.time() + seconds
    seen = {"host": set(), "client": set()}
    while time.time() < deadline:
        for gc, tag in ((host, "host"), (client, "client")):
            w = battle(gc).get("warning", "")
            if w:
                seen[tag].add(w)
        time.sleep(0.5)
    for tag in ("host", "client"):
        bad = [w for w in seen[tag]
               if any(f in w for f in FORBIDDEN_BANNERS)]
        assert not bad, (
            f"{tag}: an off-turn banner is on screen {what}: {bad}. These are "
            f"posted with showMessage(msg, -1) - they never fade, so they squat "
            f"on the warning widget for the rest of the battle and swallow the "
            f"deny flashes PRD-P6 sends through it.")
    print(f"PASS banners {what}: none of {FORBIDDEN_BANNERS} on either machine "
          f"(host saw {sorted(seen['host']) or 'nothing'}, client saw "
          f"{sorted(seen['client']) or 'nothing'})")


def assert_client_gate(host, client):
    hp, cp = parallel(host), parallel(client)
    assert hp["clientInputBlocked"] is False, \
        f"the HOST's input is gated - the host always acts in parallel mode: {hp}"
    assert cp["clientInputBlocked"] is True, \
        f"the client's input gate is open with the debug override off: {cp}"

    # the REAL END TURN button (btnEndTurnClick), the one gated handler the
    # harness can press. It must not close the side.
    turn_before = battle(host).get("turn")
    client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    time.sleep(4)
    hb, cb = battle(host), battle(client)
    assert hb.get("turn") == turn_before, (
        f"the client's END TURN closed the side: turn {turn_before} -> "
        f"{hb.get('turn')}. Only the host closes a parallel side until PRD-P8's "
        f"readiness gate lands.")
    assert hb["coopTurn"] == 2 and cb["coopTurn"] == 2, (
        f"the client's END TURN moved the turn state: host={hb['coopTurn']} "
        f"client={cb['coopTurn']}")
    print("PASS gate: the client's END TURN button is swallowed (host stays on "
          f"turn {turn_before}, both machines still at coopTurn 2) - END TURN "
          f"stays host-only until PRD-P8's readiness tally")


# Candidate destinations, nearest first. A soldier can start boxed into the craft
# with every ADJACENT tile a hull wall (which is exactly where the client's seat
# tends to sit in the skirmish fixture), so the search widens rather than giving
# up at radius 1.
STEPS = sorted(
    [(dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if (dx, dy) != (0, 0)],
    key=lambda d: (max(abs(d[0]), abs(d[1])), abs(d[0]) + abs(d[1])))


def replication_candidates(client):
    """Live player-faction units on the client that could physically take a step,
    the client's OWN seat first.

    The skirmish fixture packs all 14 soldiers into the Skyranger's 2x7 interior,
    so the back rows - which is where the client's seat sits - are boxed in by
    their own squad-mates and can path nowhere until the front rank walks out.
    The assertion below is about the DIRECTION a packet travels, not about
    ownership (that is asserted separately from `selectable`), so any unit the
    client can actually drive is a valid lever."""
    b = battle(client)
    mine = own_units(b, 1)
    others = [u for u in b["units"]
              if u.get("faction") == 0 and not u.get("isOut")
              and u.get("coop") != 1 and u.get("tu", 0) > 20]
    return mine + others


def assert_client_does_not_replicate(host, client, movers):
    """The other half of the invariant: whatever the client executes, it does not
    BROADCAST. The send sites are `_isActivePlayerSync`-gated and the client holds
    false, so the host must not see the move. (This is also exactly what the debug
    input mode does - the divergence PRD-P5 §4 says to expect.)"""
    mover_id = None
    client_before = host_before = None
    errors = []
    for cand in movers:
        uid = cand["id"]
        client_before = pos(battle(client), uid)
        host_before = pos(battle(host), uid)
        if client_before != host_before:
            errors.append(f"{uid}: machines disagree {host_before} vs {client_before}")
            continue
        for dx, dy in STEPS:
            want = (client_before[0] + dx, client_before[1] + dy, client_before[2])
            r = client.cmd({"cmd": "battle_action", "action": "move", "unit": uid,
                            "x": want[0], "y": want[1], "z": want[2]})
            if r.get("ok"):
                mover_id = uid
                break
            errors.append(f"{uid}->{want}: {r.get('error')}")
        if mover_id is not None:
            break
    assert mover_id is not None, (
        f"none of the {len(movers)} units the client could drive was able to step "
        f"anywhere: {errors[:12]}")
    wait_until(lambda: pos(battle(client), mover_id) != client_before, 30)
    time.sleep(6)  # generous: a packet, if one were sent, has long arrived

    assert pos(battle(host), mover_id) == host_before, (
        f"a CLIENT-driven action replicated to the host ({host_before} -> "
        f"{pos(battle(host), mover_id)}). In parallel mode the client is never the "
        f"executor: `_isActivePlayerSync` is false there, so no BState may ship a "
        f"packet from it.")
    print(f"PASS no-replication: the client moved {mover_id} locally "
          f"({client_before} -> {pos(battle(client), mover_id)}) and the host's "
          f"copy never budged from {host_before} - nothing was broadcast")

    # REPAIR the divergence this assertion just created, on the client only.
    # The step above is a DELIBERATE one-sided state change - that is the whole
    # point of it - and PRD-P2's unit term (`chkBattleUnits`, added after this
    # test was last touched) hashes every unit's POSITION. Left standing, the
    # next `next_turn` compare correctly reports it, `desyncSeen` latches, and
    # the post-boundary tripwire assertion below fails on this test's own lever
    # instead of on anything the boundary or the shot did. `battle_teleport` is
    # local-only (no packet - test_coop_outcome_gaps/place_adjacent has to call
    # it on BOTH machines to keep them in step), so one call puts the client's
    # copy back where the host has always had it. TU/energy are excluded from
    # the term by design, so position parity is full parity for it.
    back = client.cmd({"cmd": "battle_teleport", "unit": mover_id,
                       "x": host_before[0], "y": host_before[1],
                       "z": host_before[2]})
    assert back.get("moved"), (
        f"could not put the client's copy of {mover_id} back on the host's tile "
        f"{host_before} after the no-replication probe ({back}) - the deliberate "
        f"drift would then trip PRD-P2's unit term at the next boundary")
    assert pos(battle(host), mover_id) == pos(battle(client), mover_id), (
        f"the repair teleport left the machines apart: host "
        f"{pos(battle(host), mover_id)} client {pos(battle(client), mover_id)}")


def cycle_side(host, client, timeout=300):
    """Close the player side from the HOST (the only machine that may) and wait for
    the alien side to run and the player side to come back.

    In parallel mode btnEndTurnClick skips the `PlayerTurnYour` sub-turn hand-off
    entirely and closes the whole side: `endTurn` (carrying the boundary RNG seed)
    then, after the alien side, `next_turn` with the bulk unit/tile state."""
    start = battle(host).get("turn")
    host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    deadline = time.time() + timeout
    stalled = {}
    while time.time() < deadline:
        for gc in (host, client):
            b = battle(gc)
            if not b.get("inBattle"):
                return None
            state = TW.top(gc)
            if state == "NextTurnState":
                # The HOST's NextTurnState must close ITSELF - close() is where the
                # `next_turn` packet is built. skipNextTurnScreen (host only) does
                # that on a timer; a turn message can suppress the timer, so pop it
                # after a while rather than hang.
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
        if (now.get("turn") is not None and start is not None
                and now["turn"] > start and now.get("coopTurn") == 2
                and battle(client).get("coopTurn") == 2):
            return now["turn"]
        time.sleep(1.0)
    return False


def place_adjacent(host, client, mover_id, tpos):
    """Teleport `mover_id` to a free tile next to `tpos` on BOTH machines (same
    coordinates, so the two stay in step). Same lever as
    test_coop_outcome_gaps.place_adjacent - point blank is the only reliably
    HITTING shot the harness can drive."""
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        spot = (tpos[0] + dx, tpos[1] + dy, tpos[2])
        res = [gc.cmd({"cmd": "battle_teleport", "unit": mover_id,
                       "x": spot[0], "y": spot[1], "z": spot[2]})
               for gc in (host, client)]
        if all(r.get("moved") for r in res):
            return spot
    return None


def assert_shot_identical(host, client, shooter_id, target):
    """A host shot after the boundary must land identically on both machines."""
    target_id = target["id"]
    spot = place_adjacent(host, client, shooter_id,
                          (target["x"], target["y"], target["z"]))
    assert spot, f"no free tile adjacent to hostile {target_id} to shoot from"
    for gc in (host, client):
        gc.ok({"cmd": "battle_give", "unit": shooter_id, "item": "STR_RIFLE",
               "ammo": "STR_RIFLE_CLIP", "slot": "right", "clear_hands": True})
    time.sleep(2)
    session.assert_battle_synced(host, client, "after arming the shooter")

    damaged = False
    for shot in (1, 2, 3, 4, 5):
        before_h = health(battle(host), target_id)
        r = host.cmd({"cmd": "battle_fire", "unit": shooter_id, "mode": "snap",
                      "tu": 200, "target": target_id})
        assert r.get("ok"), f"the host could not fire: {r}"
        settle(host, client, seconds=10)

        after_h = health(battle(host), target_id)
        after_c = health(battle(client), target_id)
        assert after_h == after_c, (
            f"post-boundary shot #{shot} did NOT land identically: the host has "
            f"unit {target_id} at {after_h} HP, the client at {after_c}. The "
            f"outcome must be host-authored and applied verbatim.")
        session.assert_battle_synced(host, client, f"after post-boundary shot #{shot}")
        if after_h != before_h:
            damaged = True
            print(f"PASS shot #{shot}: {before_h} -> {after_h} HP, identical on "
                  f"both machines")
            break
        print(f"    shot #{shot} missed ({before_h} HP unchanged) - identical on "
              f"both machines, firing again")
    assert damaged, (
        f"five point-blank snap shots at unit {target_id} all missed - the "
        f"'identical damage' assertion never got real damage to compare")
    assert not TW.desync_seen(host) and not TW.desync_seen(client), \
        "the drift tripwire fired on the post-boundary shot"


# ---- main ------------------------------------------------------------------

def main():
    fail = None
    try:
        phase_degrade()
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(2)

    # HOST on, CLIENT off: the host's value is the session's, and the client must
    # end up in parallel mode anyway. skipNextTurnScreen on the host only - its
    # NextTurnState::close() is what ships `next_turn` (see test_battle_tripwire).
    host = GameClient("host", 48860,
                      make_user_dir("p5_sharedturn_host",
                                    options={"battleXcomSpeed": 2,
                                             "battleAlienSpeed": 2,
                                             "skipNextTurnScreen": True,
                                             "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48861,
                        make_user_dir("p5_sharedturn_client",
                                      options={"battleXcomSpeed": 2,
                                               "battleAlienSpeed": 2,
                                               "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        # bring_up_battle() hosts on test_battle_tripwire's own port constant
        TW.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines")

        gm = battle(host).get("coopGamemode")
        assert gm in (1, 4), (
            f"the skirmish fixture came up in gamemode {gm}; parallelTurnActive() "
            f"only covers PVE (1) and PVE2 (4), so this test would be vacuous")

        # --- 1. the invariant ------------------------------------------------
        hb, cb = assert_invariant(host, client, "at the start of the player side")
        assert cb["parallelEnabled"] is True, (
            "the client did not adopt the HOST's parallel-turns setting - its own "
            "option is deliberately OFF here, so this proves the handshake mirror")
        print(f"PASS invariant: both machines coopTurn=2, parallelActive=True; "
              f"activeSync host={hb['activeSync']} client={cb['activeSync']} "
              f"(_isActivePlayerSync == getHost())")

        # both machines must actually be able to command their OWN soldiers
        for b, tag, seat in ((hb, "host", 0), (cb, "client", 1)):
            mine = [u for u in b["units"] if u.get("coop") == seat
                    and u.get("faction") == 0 and not u.get("isOut")]
            sel = [u for u in mine if u.get("selectable")]
            assert sel, (
                f"{tag}: none of its own {len(mine)} soldiers is selectable during "
                f"the parallel player side - isSelectable()/playableUnitSelected() "
                f"still gate on the executor flag somewhere")
            theirs = [u for u in b["units"] if u.get("coop") != seat
                      and u.get("faction") == 0 and u.get("selectable")]
            assert not theirs, (
                f"{tag}: it can also select {len(theirs)} of the PEER's soldiers - "
                f"parallel turns must not merge the two rosters")
        print("PASS ownership: each machine commands exactly its own seat's "
              "soldiers, both at the same time")

        # --- 2. no banners ---------------------------------------------------
        assert_no_banners(host, client, "during the parallel player side")

        # --- 3. the temporary client input gate ------------------------------
        assert_client_gate(host, client)
        assert own_units(battle(client), 1), \
            "the client commands no soldier with TU to spend"
        assert_client_does_not_replicate(host, client,
                                         replication_candidates(client))

        # --- 4. the side boundary --------------------------------------------
        turn = cycle_side(host, client)
        assert turn, (
            f"the side never closed / never came back (turn="
            f"{battle(host).get('turn')}, host top={TW.top(host)}, client "
            f"top={TW.top(client)}). In parallel mode the host's END TURN must "
            f"close the WHOLE side - there is no `PlayerTurnYour` hand-off left.")
        print(f"side boundary crossed: the alien side ran and the player side came "
              f"back on turn {turn}")
        assert_invariant(host, client, f"back on the player side (turn {turn})")
        assert_no_banners(host, client, f"after the boundary (turn {turn})",
                          seconds=5.0)
        print("PASS boundary: invariant re-asserted after the AI phase")

        target = alive_enemy(battle(host))
        assert target, "no live hostile left to shoot at after the boundary"
        shooters = own_units(battle(host), 0)
        assert shooters, "the host commands no unit able to shoot after the boundary"
        assert_shot_identical(host, client, shooters[0]["id"], target)

        print("ALL PARALLEL SHARED-TURN TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
