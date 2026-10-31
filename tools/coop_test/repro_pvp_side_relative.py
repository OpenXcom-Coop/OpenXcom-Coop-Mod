"""repro_pvp_side_relative.py: side-relative play in PvP. A gm2 client SEES,
SELECTS and COMMANDS its own alien units on its own side, renders only its
own side's fog, and none of it moves a hash bucket.

AI-NEUTRAL PINNING: this file imports the SHARED session.pin_ai_neutral()
helper rather than re-implementing it. In gm2 the pin legitimately finds
ZERO - the client's own aliens sit at coop seat 1, not COOP_SEAT_NONE, so the
host's AI is suppressed for them by the think() guard
(coopSuppressNonPlayerThink, BattleAuthority.h) instead of by this pin. This
file prints the pinned count and never asserts it is non-zero.

POLARITY (read twice): `battle_state.hiddenMovementShown` is
`Map::hiddenMovementShown()`, the hidden-movement predicate `Map::draw` acts
on (vanilla's test plus the co-op edits). TRUE means the terrain IS drawn
(the HIDDEN MOVEMENT banner is NOT shown); FALSE means the banner IS up.

THE CLICK-SELECT PHASE's CAMERA-SETTLE RACE: `map_tile_click_pos` re-centres
the camera to verify a click (`centered: true`), and a camera that is still
moving when the SEPARATE `inject_input` call is handled can resolve the click
to a different tile than the one the probe verified (seen as `unit=-1`, an
empty-ground miss). The fix is a FIXED TWO-PASS sequence, never a loop: a
first ("settling") click lets the camera come to rest, and a second probe on
the now-stationary camera reports `centered: false` - the signal that this
run's geometry is sound. The CLICK-SELECT PHASE below asserts
`centered is False` on its measured passes; a True there is a fixture
problem to report, not a case to re-roll.

PHASES, fixed order (the order matters - the PLAYER-SIDE BANNER PHASE reads
the player-side value BEFORE anything selects a unit, and the CORRUPT-BUCKET
PHASE is last because its divergence is permanent):
  BOOT PHASE - boot gm2, pin_ai_neutral, the non-vacuity gate (one live
      seat-1 FACTION_HOSTILE unit, coop==1 on both machines), authority
      sanity.
  PLAYER-SIDE BANNER PHASE - hidden movement on the PLAYER side (host
      asserted, client only printed - not a discriminator here, see the
      OWN-SIDE BANNER CHECK).
  PLAYER-SIDE END-TURN PHASE - allowButtons() on the PLAYER side: the client
      cannot reach the HOST's own end-turn readiness tally.
  OWN-SIDE PHASE - cross to the client's OWN (hostile) side:
      OWN-SIDE BANNER CHECK - hidden movement, the discriminating pair;
      OWN-SIDE FOG CHECK - per-side fog census, both sets EQUAL across
         machines and NOT equal to each other (non-degeneracy);
      OWN-SIDE BUCKET CHECK - all hash buckets EQUAL (assert_hash_clean).
  CLICK-SELECT PHASE - the client SEES and can click-SELECT its own alien: a
      settling click (camera-settle race above), then the same-boot control
      - rule OFF the click is refused (falls through to the commanding arm
      and bumps coopLocalExecBlocked), rule ON the SAME click selects the
      alien and does not bump the counter.
  OWN-SIDE END-TURN PHASE - allowButtons() on the client's OWN side: it CAN
      end its own side.
  VISIBILITY-RULE HASH PHASE - the hash-free proof: all buckets EQUAL with
      the `battle_visibility_rule` test command ON and OFF, and the two
      snapshots equal each other.
  CORRUPT-BUCKET PHASE - LAST, irreversible: corrupt_bucket{revealHostile}
      is still caught by hash_now.

Run:  python tools/coop_test/repro_pvp_side_relative.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, pin_ai_neutral, assert_hash_clean,
                      FACTION_PLAYER, FACTION_HOSTILE)
import repro_atom_side_transition as sid
from repro_atom_side_begin import row_for as gm2_row_for, drive_side_change

MISSION = "STR_SMALL_SCOUT"
SEED = 1


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def drive_to_gm2_battlescape(host, client):
    """`repro_atom_side_begin.run_gm2()`'s own NewBattleState-inline drive
    (gm2 assigns seats automatically via assignSeatsAndFactions() -
    session.drive_to_battlescape's seat_count loop is a CLASSIC-only
    mechanism), plus the STR_SMALL_SCOUT mission pin and the pinned seed
    (`set_seed` sent right before `newbattle_ok`)."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"
    r = host.cmd({"cmd": "newbattle_mission", "type": MISSION})
    assert r.get("ok"), (
        f"this build's NEW BATTLE screen does not offer {MISSION!r} in gm2 - "
        f"offered: {r.get('missionTypes')}")

    host.ok({"cmd": "set_seed", "seed": SEED})
    host.ok({"cmd": "newbattle_ok"})
    # the shared battle-entry spine (both briefings, the host's
    # pre-battle equip screen - the alien seat has nothing to equip - and both
    # Turn-1 screens).
    session.briefings_to_battlescape(host, client)


def phase_boot(host, client):
    """BOOT PHASE - boot and non-vacuity gate."""
    sid.bring_up_lobby(host, client, "48175")

    row = gm2_row_for(host, "ClientPlayer")
    r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
    assert r.get("gamemode") == 2, (
        f"BOOT PHASE: expected gamemode 2 (PVP, client=Alien), got {r.get('gamemode')}")
    time.sleep(1)  # let the change_team broadcast settle on the client (pvp_fixture.py precedent)

    drive_to_gm2_battlescape(host, client)

    hs0 = battle_state(host)
    cs0 = battle_state(client)
    assert hs0.get("coopGamemode") == 2 and cs0.get("coopGamemode") == 2, (
        f"BOOT PHASE: expected coopGamemode 2 on both machines: "
        f"host={hs0.get('coopGamemode')} client={cs0.get('coopGamemode')}")

    ha = hs0.get("authority", {})
    ca = cs0.get("authority", {})
    assert ha.get("localSeat") == 0 and ha.get("hostSim") is True, (
        f"BOOT PHASE: host authority expected localSeat=0 hostSim=True, got {ha}")
    assert ca.get("localSeat") == 1 and ca.get("hostSim") is False, (
        f"BOOT PHASE: client authority expected localSeat=1 hostSim=False, got {ca}")
    print(f"BOOT PHASE: authority sane - host={ha} client={ca}")

    pinned = pin_ai_neutral(host, client, tag="pvp-side-relative")
    print(f"BOOT PHASE: pin_ai_neutral pinned {len(pinned)} unit(s) - 0 is legal in "
          "gm2 (the client's aliens sit at seat 1, not NONE)")

    # non-vacuity gate: fail when the fixture cannot produce a live seat-1
    # FACTION_HOSTILE unit on both machines.
    h_hostiles = [u for u in hs0["units"]
                  if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
    c_hostiles = [u for u in cs0["units"]
                  if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
    assert h_hostiles, (
        f"BOOT PHASE: no live FACTION_HOSTILE unit on the host: {hs0['units']}")
    assert c_hostiles, (
        f"BOOT PHASE: no live FACTION_HOSTILE unit on the client: {cs0['units']}")
    h_ids = {u["id"] for u in h_hostiles}
    c_ids = {u["id"] for u in c_hostiles}
    assert h_ids == c_ids, (
        f"BOOT PHASE: hostile id sets differ across machines: "
        f"host={h_ids} client={c_ids}")
    assert all(u.get("coop") == 1 for u in h_hostiles), (
        f"BOOT PHASE: a host-side hostile unit is not coop==1: {h_hostiles}")
    assert all(u.get("coop") == 1 for u in c_hostiles), (
        f"BOOT PHASE: a client-side hostile unit is not coop==1: {c_hostiles}")
    print(f"BOOT PHASE: live FACTION_HOSTILE units (host view): "
          f"{[(u['id'], session.unit_pos(u), u['tu']) for u in h_hostiles]}")
    print(f"BOOT PHASE: live FACTION_HOSTILE units (client view): "
          f"{[(u['id'], session.unit_pos(u), u['tu']) for u in c_hostiles]}")

    alien = h_hostiles[0]
    alien_id = alien["id"]
    alien_pos = session.unit_pos(alien)

    soldiers = [u for u in hs0["units"]
                if u.get("coop") == 0 and u.get("faction") == FACTION_PLAYER
                and not u.get("isOut")]
    assert soldiers, (
        f"BOOT PHASE: host has no live coop==0 FACTION_PLAYER soldier (needed by "
        f"CLICK-SELECT PHASE): {hs0['units']}")
    soldier_id = soldiers[0]["id"]

    print(f"BOOT PHASE: recorded alien_id={alien_id} pos={alien_pos}; "
          f"seat-0 soldier_id={soldier_id} (for CLICK-SELECT PHASE)")
    print("PASS: BOOT PHASE (boot + non-vacuity gate)")
    return alien_id, alien_pos, soldier_id


def phase_hidden_movement_player_side(host, client):
    """PLAYER-SIDE BANNER PHASE - hidden movement on the PLAYER side, read
    BEFORE anything selects a unit. Polarity: TRUE == terrain drawn, HIDDEN
    MOVEMENT banner NOT shown; FALSE == the banner IS up
    (Map::hiddenMovementShown(), the predicate Map::draw acts on)."""
    hs = battle_state(host)
    assert hs.get("hiddenMovementShown") is True, (
        f"PLAYER-SIDE BANNER PHASE: host hiddenMovementShown expected True (the host's seat "
        f"commands the active PLAYER side) - got {hs.get('hiddenMovementShown')}")

    cs = battle_state(client)
    print(f"PLAYER-SIDE BANNER PHASE: client hiddenMovementShown={cs.get('hiddenMovementShown')} "
          "- NOT asserted here: on the player side the client's own selected "
          "unit may be a FACTION_PLAYER soldier, whose getVisible() "
          "short-circuits true, so that term alone can satisfy the gate and "
          "the value is not a discriminator. The discriminating pair is "
          "OWN-SIDE BANNER CHECK.")
    print("PASS: PLAYER-SIDE BANNER PHASE (hidden movement, player side)")


def phase_allow_buttons_player_side(host, client):
    """PLAYER-SIDE END-TURN PHASE - allowButtons() on the PLAYER side: the
    client must NOT be able to end the HOST's side.

    If allowButtons() were TRUE for the client on the player side, the press
    would reach CoopEndTurn::toggleReady, which ships a bt_end_turn_ready on
    the wire, and coopEndTurnTalliesSeen would move 0 -> 1 on BOTH machines:
    a gm2 client could reach the readiness tally of the HOST's own side. A
    press allowButtons() refuses can never reach toggleReady and so can never
    move that counter; that is why this counter, not the arm state, is the
    check.
    """
    seen0_h = event_state(host).get("coopEndTurnTalliesSeen")
    seen0_c = event_state(client).get("coopEndTurnTalliesSeen")

    client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    time.sleep(2.0)

    seen1_h = event_state(host).get("coopEndTurnTalliesSeen")
    seen1_c = event_state(client).get("coopEndTurnTalliesSeen")
    assert seen1_h == seen0_h, (
        f"PLAYER-SIDE END-TURN PHASE: host coopEndTurnTalliesSeen CHANGED on a player-side "
        f"press the client's allowButtons() should refuse: {seen0_h} -> {seen1_h}")
    assert seen1_c == seen0_c, (
        f"PLAYER-SIDE END-TURN PHASE: client coopEndTurnTalliesSeen CHANGED on a player-side "
        f"press the client's allowButtons() should refuse: {seen0_c} -> {seen1_c}")

    cs = battle_state(client)
    assert cs.get("coopEndTurnArmed") is False, (
        f"PLAYER-SIDE END-TURN PHASE: client coopEndTurnArmed expected False, got {cs.get('coopEndTurnArmed')}")
    assert cs.get("coopEndTurnText") == "", (
        f"PLAYER-SIDE END-TURN PHASE: client coopEndTurnText expected empty, got {cs.get('coopEndTurnText')!r}")
    print(f"PLAYER-SIDE END-TURN PHASE: coopEndTurnTalliesSeen unchanged on both machines "
          f"(host {seen0_h}->{seen1_h}, client {seen0_c}->{seen1_c}); "
          "client armed=False text=''")
    print("PASS: PLAYER-SIDE END-TURN PHASE (allowButtons refuses the client on the player side)")


def phase_cross_to_hostile_side(host, client):
    """OWN-SIDE PHASE - cross to the client's OWN (hostile) side, then the
    banner, fog and bucket checks."""
    host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    drive_side_change(host, client, FACTION_HOSTILE, timeout=40)

    # OWN-SIDE BANNER CHECK - hidden movement, the discriminating pair. On the
    # client's own side every other term of Map::hiddenMovementShown() is
    # false here (its selected unit is its own alien, whose getVisible() is
    # _visible==false; no unit dying, no projectile, no explosion, debug off),
    # so only the side-relative term (coopSideIsMine) keeps the terrain drawn.
    # A vanilla getSide()==FACTION_PLAYER test is false here and would show
    # HIDDEN MOVEMENT on the client's own turn.
    cs = battle_state(client)
    hs = battle_state(host)
    assert cs.get("hiddenMovementShown") is True, (
        f"OWN-SIDE BANNER CHECK: client hiddenMovementShown expected True (its own side, "
        f"terrain drawn) - got {cs.get('hiddenMovementShown')}")
    assert hs.get("hiddenMovementShown") is False, (
        f"OWN-SIDE BANNER CHECK: host hiddenMovementShown expected False (not its side, "
        f"banner up) - got {hs.get('hiddenMovementShown')}")
    print(f"OWN-SIDE BANNER CHECK: client hiddenMovementShown=True (own side), host=False "
          "(not its side) - the discriminating pair")

    # OWN-SIDE FOG CHECK - per-side fog: each machine keeps a player set and a
    # hostile set, and reads the set of the side it plays.
    hr = host.cmd({"cmd": "reveal_state"})
    cr = client.cmd({"cmd": "reveal_state"})
    assert hr.get("ok") and cr.get("ok"), (
        f"OWN-SIDE FOG CHECK: reveal_state unusable: host={hr} client={cr}")

    h_hostile = hr["hostile"]
    c_hostile = cr["hostile"]
    assert h_hostile.get("allocated") is True and c_hostile.get("allocated") is True, (
        f"OWN-SIDE FOG CHECK: hostile['allocated'] expected True on both: "
        f"host={h_hostile.get('allocated')} client={c_hostile.get('allocated')}")
    assert h_hostile.get("size") == c_hostile.get("size"), (
        f"OWN-SIDE FOG CHECK: hostile['size'] differs: host={h_hostile.get('size')} "
        f"client={c_hostile.get('size')}")

    parts = ("floor", "westwall", "northwall")
    h_player_census = {k: hr["player"][k] for k in parts}
    c_player_census = {k: cr["player"][k] for k in parts}
    assert h_player_census == c_player_census, (
        f"OWN-SIDE FOG CHECK: player census differs across machines: "
        f"host={h_player_census} client={c_player_census}")

    h_hostile_census = {k: h_hostile[k] for k in parts}
    c_hostile_census = {k: c_hostile[k] for k in parts}
    assert h_hostile_census == c_hostile_census, (
        f"OWN-SIDE FOG CHECK: hostile census differs across machines: "
        f"host={h_hostile_census} client={c_hostile_census}")

    # non-degeneracy: the hostile set is a genuinely different set, not a
    # copy of the player set (measured: player floor 1895 vs hostile floor
    # 318 on this fixture).
    assert h_hostile_census != h_player_census, (
        f"OWN-SIDE FOG CHECK: non-degeneracy failed - hostile census equals player "
        f"census: {h_hostile_census}")

    print(f"OWN-SIDE FOG CHECK: player census={h_player_census} (both machines), "
          f"hostile census={h_hostile_census} (both machines), "
          f"hostile allocated=True size={h_hostile.get('size')} (both machines)")

    # OWN-SIDE BUCKET CHECK - revealHostile and saveBlob EQUAL, like every
    # other bucket.
    hh, ch = assert_hash_clean(host, client, full=True, what="hostile side")
    print(f"OWN-SIDE BUCKET CHECK: all {len(hh)} bucket(s) EQUAL: {hh}")

    print("PASS: OWN-SIDE PHASE (cross to the client's own side: banner, fog, buckets)")


def phase_client_click_selects_own_alien(host, client, alien_id, alien_pos, soldier_id):
    """CLICK-SELECT PHASE - the client SEES and can click-SELECT its own alien.

    CAMERA-SETTLE RACE (module docstring): `map_tile_click_pos` re-centres
    the camera to verify a click, and a camera that is still moving makes
    the SEPARATE `inject_input` call that follows land on a DIFFERENT tile
    than the one just verified (seen as unit=-1, an empty-ground miss - a
    harness recipe defect, not an engine one). The fix is a FIXED TWO-PASS
    sequence, never a loop: a first ("settling") click lets the camera come
    to rest; the SECOND probe, on a now-stationary camera, reports
    `centered: false` - this file asserts that explicitly, so a fixture
    problem (camera still moving) reports itself as a named failure rather
    than a silent miss.

    THE SAME-BOOT CONTROL needs no second build: with the rule OFF the
    settled click is REFUSED (coopUnitVisibleHere false -> the select arm's
    condition fails -> falls through to the commanding arm ->
    coopBlockWalkArm refuses it, bumping coopLocalExecBlocked,
    BattlescapeGame.cpp's walk-confirm arm); with the rule ON the SAME
    settled click SELECTS the alien and does not bump the counter. One boot,
    one build, one fixture, differing in exactly one term.
    """
    cs = battle_state(client)
    assert cs.get("selectedId") == alien_id, (
        f"CLICK-SELECT PHASE: client selectedId {cs.get('selectedId')} != alien_id "
        f"{alien_id} at the start of its own side")
    # a bare click here would be vacuous: selection-by-cycle goes through
    # coopMaySelectUnit, which is true for a seat-1 unit on a seat-1 machine
    # and never consults getVisible(); the fixture deploys only one alien.
    print(f"CLICK-SELECT PHASE: client already has its own alien {alien_id} selected by "
          "the cycle - a click WITHOUT first pointing elsewhere would be "
          "vacuous")

    # point the client's selection elsewhere with the EXISTING one-sided
    # select command - repro_atom_side_begin.py also selects DIFFERENT units
    # on host and client, and selectedUnit is saveBlob-EXCLUDED
    # (SharedEcon.cpp's saveBlobExcludedTopKey) so this is hash-neutral. The
    # target is the seat-0 soldier BOOT PHASE recorded from the host dump.
    r = client.cmd({"cmd": "battle_action", "action": "select", "unit": soldier_id})
    assert r.get("ok"), f"CLICK-SELECT PHASE: client select of seat-0 soldier {soldier_id} failed: {r}"
    cs = battle_state(client)
    assert cs.get("selectedId") == soldier_id, (
        f"CLICK-SELECT PHASE: client selectedId did not move to the seat-0 soldier "
        f"{soldier_id}: {cs.get('selectedId')}")
    print(f"CLICK-SELECT PHASE: client selection pointed elsewhere - now soldier {soldier_id}")
    time.sleep(2.0)

    # mapClick's three pre-primaryAction gates (BattlescapeState.cpp:1147/
    # :1151) - asserting them makes a swallowed click distinguishable from a
    # refused one.
    assert cs.get("mouseOverIcons") is False, (
        f"CLICK-SELECT PHASE: client mouseOverIcons expected False, got {cs.get('mouseOverIcons')}")
    assert cs.get("cursorType") != 0, (
        f"CLICK-SELECT PHASE: client cursorType expected != 0 (CT_NONE), got {cs.get('cursorType')}")
    assert cs.get("isBusy") is False, (
        f"CLICK-SELECT PHASE: client isBusy expected False, got {cs.get('isBusy')}")
    print(f"CLICK-SELECT PHASE: mapClick pre-gates OK: mouseOverIcons=False "
          f"cursorType={cs.get('cursorType')} isBusy=False")

    # SETTLING PASS (one fixed extra pass, see module docstring): ONE probe,
    # ONE click, to let the camera finish moving. Its job is only to settle
    # the camera; what it does to selection is NOT asserted.
    pr_settle = client.ok({"cmd": "map_tile_click_pos",
                            "x": alien_pos[0], "y": alien_pos[1], "z": alien_pos[2]})
    assert pr_settle.get("verified"), (
        f"CLICK-SELECT PHASE: settling map_tile_click_pos not verified for the "
        f"alien's tile {alien_pos}: {pr_settle}")
    client.ok({"cmd": "inject_input", "kind": "click",
               "x": pr_settle["winX"], "y": pr_settle["winY"], "button": "left"})
    time.sleep(0.8)
    print("CLICK-SELECT PHASE: settling pass done (camera-settle race, module docstring)")

    # with the harness's battleEdgeScroll: 0 the camera does not drift after
    # the probe centres it, so the settling click lands ON the alien's tile
    # and, rule still ON, SELECTS the alien without touching
    # coopLocalExecBlocked (seen: selectedId 8 -> 1000000, counter 0 -> 0;
    # a drifting camera made it an empty-ground miss). Undo that with the
    # same one-sided select command as above - setSelectedUnit only, the
    # camera and so the settled geometry are untouched - so the rule-OFF click
    # again starts from "soldier selected, alien not selected".
    settle_sel = battle_state(client).get("selectedId")
    r = client.cmd({"cmd": "battle_action", "action": "select", "unit": soldier_id})
    assert r.get("ok"), (
        f"CLICK-SELECT PHASE: client re-select of seat-0 soldier {soldier_id} after the "
        f"settling pass failed: {r}")
    cs = battle_state(client)
    assert cs.get("selectedId") == soldier_id, (
        f"CLICK-SELECT PHASE: client selectedId did not move back to the seat-0 soldier "
        f"{soldier_id} after the settling pass: {cs.get('selectedId')}")
    print(f"CLICK-SELECT PHASE: settling click left selectedId={settle_sel}; selection "
          f"pointed back at soldier {soldier_id}")

    # the baseline is taken AFTER the settling pass and the re-point: what the
    # settling click did to coopLocalExecBlocked is not part of what this
    # phase measures.
    blocked_before = event_state(client).get("coopLocalExecBlocked")
    print(f"CLICK-SELECT PHASE: client coopLocalExecBlocked after the settling pass = {blocked_before}")

    # CONTROL, rule OFF: the same settled click must be REFUSED.
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_visibility_rule", "on": False})
        assert r.get("ok") and r.get("on") is False, (
            f"CLICK-SELECT PHASE: rule OFF failed on {gc.name}: {r}")

    pr_off = client.ok({"cmd": "map_tile_click_pos",
                         "x": alien_pos[0], "y": alien_pos[1], "z": alien_pos[2]})
    assert pr_off.get("verified"), (
        f"CLICK-SELECT PHASE: map_tile_click_pos (rule OFF) not verified for "
        f"the alien's tile {alien_pos}: {pr_off}")
    assert pr_off.get("centered") is False, (
        f"CLICK-SELECT PHASE: map_tile_click_pos (rule OFF) reports centered=True - the "
        f"camera is STILL MOVING after the settling pass. This is a fixture "
        f"problem to report, not a case to re-roll: {pr_off}")
    client.ok({"cmd": "inject_input", "kind": "click",
               "x": pr_off["winX"], "y": pr_off["winY"], "button": "left"})
    time.sleep(0.8)

    cs = battle_state(client)
    assert cs.get("selectedId") == soldier_id, (
        f"CLICK-SELECT PHASE CONTROL (rule OFF): the click selected something other "
        f"than the still-armed soldier {soldier_id}: selectedId="
        f"{cs.get('selectedId')} - the rule-OFF click should be REFUSED")
    print(f"CLICK-SELECT PHASE CONTROL (rule OFF): the settled click on the alien's "
          f"own tile was REFUSED - selectedId stayed {soldier_id}")

    # rule ON: the SAME settled click now SELECTS the alien.
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_visibility_rule", "on": True})
        assert r.get("ok") and r.get("on") is True, (
            f"CLICK-SELECT PHASE: rule ON failed on {gc.name}: {r}")

    blocked_before_rule_on = event_state(client).get("coopLocalExecBlocked")

    pr_on = client.ok({"cmd": "map_tile_click_pos",
                        "x": alien_pos[0], "y": alien_pos[1], "z": alien_pos[2]})
    assert pr_on.get("verified"), (
        f"CLICK-SELECT PHASE: map_tile_click_pos (rule ON) not verified for "
        f"the alien's tile {alien_pos}: {pr_on}")
    assert pr_on.get("centered") is False, (
        f"CLICK-SELECT PHASE: map_tile_click_pos (rule ON) reports centered=True - the "
        f"camera is STILL MOVING - a fixture problem to report, not a case "
        f"to re-roll: {pr_on}")
    client.ok({"cmd": "inject_input", "kind": "click",
               "x": pr_on["winX"], "y": pr_on["winY"], "button": "left"})
    time.sleep(0.8)

    cs = battle_state(client)
    assert cs.get("selectedId") == alien_id, (
        f"CLICK-SELECT PHASE (rule ON): the click did NOT select its own alien: "
        f"selectedId={cs.get('selectedId')} expected {alien_id}")
    print(f"CLICK-SELECT PHASE (rule ON): the settled click selected its own "
          f"alien {alien_id}")

    blocked_after_rule_on = event_state(client).get("coopLocalExecBlocked")
    assert blocked_after_rule_on == blocked_before_rule_on, (
        f"CLICK-SELECT PHASE (rule ON): coopLocalExecBlocked ROSE "
        f"({blocked_before_rule_on} -> {blocked_after_rule_on}) - the click was "
        "REFUSED, not accepted")
    print(f"CLICK-SELECT PHASE (rule ON): coopLocalExecBlocked unchanged "
          f"({blocked_before_rule_on} -> {blocked_after_rule_on}) - the click "
          "was ACCEPTED")
    print("PASS: CLICK-SELECT PHASE (settle + same-boot control: OFF refuses, "
          "ON selects the client's own alien)")


def phase_allow_buttons_own_side(host, client):
    """OWN-SIDE END-TURN PHASE - allowButtons() on the client's OWN side: it
    CAN end its own side.

    If allowButtons() were FALSE here, the same press would move nothing
    (nothing armed, nothing on the wire) and the client could not end its own
    side.
    """
    seen0_h = event_state(host).get("coopEndTurnTalliesSeen")
    seen0_c = event_state(client).get("coopEndTurnTalliesSeen")

    client.ok({"cmd": "battle_action", "action": "end_turn_button"})

    def _tallies_rose():
        h = event_state(host).get("coopEndTurnTalliesSeen")
        c = event_state(client).get("coopEndTurnTalliesSeen")
        if h > seen0_h and c > seen0_c:
            return (h, c)
        return None

    after = host.wait_for(
        "coopEndTurnTalliesSeen rises on both machines after the client's "
        "own-side press", _tallies_rose, timeout=15)
    print(f"OWN-SIDE END-TURN PHASE: coopEndTurnTalliesSeen before=({seen0_h},{seen0_c}) "
          f"after={after}")
    # Deliberately no assertion here about the side or turn after this
    # press.
    print("PASS: OWN-SIDE END-TURN PHASE (allowButtons admits the client on its own side)")


def phase_hash_free_on_off(host, client):
    """VISIBILITY-RULE HASH PHASE - the hash-free proof: all buckets EQUAL
    with the visibility rule ON and OFF (the rule is a READ-SWITCH;
    coopUnitVisibleHere is its ONLY reader). Leaves the rule ON at the end."""
    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_visibility_rule", "on": False})
        assert r.get("ok") and r.get("on") is False, (
            f"VISIBILITY-RULE HASH PHASE: rule OFF failed on {gc.name}: {r}")
    off_h, off_c = assert_hash_clean(host, client, full=True, what="visibility rule OFF")

    for gc in (host, client):
        r = gc.cmd({"cmd": "battle_visibility_rule", "on": True})
        assert r.get("ok") and r.get("on") is True, (
            f"VISIBILITY-RULE HASH PHASE: rule ON failed on {gc.name}: {r}")
    on_h, on_c = assert_hash_clean(host, client, full=True, what="visibility rule ON")

    assert off_h == on_h, (
        f"VISIBILITY-RULE HASH PHASE: buckets differ ON vs OFF - off={off_h} on={on_h}")
    print(f"VISIBILITY-RULE HASH PHASE: OFF buckets = {off_h}")
    print(f"VISIBILITY-RULE HASH PHASE: ON  buckets = {on_h}")
    print("PASS: VISIBILITY-RULE HASH PHASE (hash-free proof, rule ON/OFF)")


def phase_corrupt_bucket_still_caught(host, client):
    """CORRUPT-BUCKET PHASE - LAST, irreversible: the desync detector still
    catches a corrupted hostile set. CoopFog::corrupt() pokes the bitmap
    directly, bypassing emit; this phase is last because the divergence is
    permanent.

    Pokes the CLIENT, not the host: TestServer.cpp's own coopCorruptBucket()
    comment is explicit that poking the HOST leaves the corrupted bits merely
    "live but unpublished", and the coop reveal quiescent flush ships (heals)
    them on the very next delta - seen here too (a host-side poke left the
    buckets EQUAL, healed). The client has no such flush to heal it."""
    client.ok({"cmd": "corrupt_bucket", "name": "revealHostile"})

    hr = host.cmd({"cmd": "hash_now", "full": True})
    cr = client.cmd({"cmd": "hash_now", "full": True})
    assert hr.get("ok") and cr.get("ok"), (
        f"CORRUPT-BUCKET PHASE: hash_now failed: host={hr} client={cr}")
    hh = hr.get("h", {})
    ch = cr.get("h", {})
    diff = {k: (hh[k], ch[k]) for k in hh if hh.get(k) != ch.get(k)}
    assert diff, (
        f"CORRUPT-BUCKET PHASE: corrupt_bucket{{revealHostile}} produced NO bucket "
        f"difference: host={hh} client={ch}")
    assert "revealHostile" in diff, (
        f"CORRUPT-BUCKET PHASE: revealHostile is not among the differing buckets: {diff}")
    print(f"CORRUPT-BUCKET PHASE: differing bucket(s) after corrupt_bucket: {diff}")
    print("PASS: CORRUPT-BUCKET PHASE (a corrupted hostile set is still caught)")


def main():
    host_dir = make_user_dir("pvp_side_relative_host")
    client_dir = make_user_dir("pvp_side_relative_client")
    host = GameClient("host", 49568, host_dir)
    client = GameClient("client", 49569, client_dir)
    try:
        alien_id, alien_pos, soldier_id = phase_boot(host, client)
        phase_hidden_movement_player_side(host, client)
        phase_allow_buttons_player_side(host, client)
        phase_cross_to_hostile_side(host, client)
        phase_client_click_selects_own_alien(host, client, alien_id, alien_pos, soldier_id)
        phase_allow_buttons_own_side(host, client)
        phase_hash_free_on_off(host, client)
        phase_corrupt_bucket_still_caught(host, client)
        print("ALL PvP SIDE-RELATIVE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("repro_pvp_side_relative", e.tracking, str(e))
        print(f"\nrepro_pvp_side_relative: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\nrepro_pvp_side_relative: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\nrepro_pvp_side_relative: FAIL\nTimeoutError: {e}")
        sys.exit(2)
