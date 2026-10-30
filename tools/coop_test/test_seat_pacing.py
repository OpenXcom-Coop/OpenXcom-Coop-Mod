"""test_seat_pacing.py: per-seat animation pacing
(CoopSpeed) - the per-seat speed table, the floor fallback for unowned
(alien) units, the three set_option dial arms, the Ctrl-S "Usain Bolt"
quick-mode gate (parallel/traditional/alien-side/solo), and the ghost
pacing derivation (frames x the acting seat's dial == ms). Ten scenarios
across four boots (solo, parallel, alien-side, baton), built on the facts
below (read from src/CoopMod/CoopSpeed.h / connectionTCP.cpp /
TestServer.cpp and src/Battlescape/BattlescapeState.cpp - never
re-derived here):

  1. floor = MAX xcom, MAX alien, MIN fire (CoopSpeed::floor()) - the
     slower-of-the-two-machines value wins for xcom/alien speed dials, and
     the FASTER machine's fire-speed number (numerically lower = faster
     animation) wins there.
  2. ghost frames: 8 for a straight or vertical (z-change) walk step, 16
     for a diagonal one; 1 frame per turn octant (shorter modular arc);
     kneel is a fixed 100 ms. ms == frames x
     paceMsFor(unit) == frames x the OWNER's raw dial value (or the floor
     when the acting unit is unowned) - the dial IS the per-frame ms, not
     a lookup table.
  3. CoopGhost::onEvApplied() (ghostLast's source) fires only on the
     machine that APPLIES an incoming ev - the client. The host is the
     sole real-sim runner and never applies its own evs, so the host's own
     ghostLast never updates for its own actions; every ghostLast
     assertion below reads the CLIENT, and the HOST side is checked via
     CoopSpeed::lastRead() (speed.lastRead) instead - the dial/seat the
     most recent speedFor() call actually used.
  4. A host-owned unit's walk/turn goes through the REAL UI (TAB-select +
     map_tile_click_pos + inject_input click): host-local input never
     enters the intent path (repro_atom_walk.py phase_host_origin
     precedent). A client-owned unit walks via battle_intent/send_walk.
  5. The raw drive_to_battlescape spawn has no walkable, contact-free
     tile (units packed in the Skyranger, random-map aliens in view).
     Every walk/turn fixture below stages its actor first via
     session.stage_open_ground_actor - never re-rolled.
  6. Ctrl-S: inject_input {kind:"key",key:115,mod:"ctrl"}, cleared with
     {kind:"modstate",mod:"none"}. warningText renders OXCE's own
     STR_QUICK_MODE_ACTIVATED / STR_QUICK_MODE_DEACTIVATED strings (read
     ONCE at runtime from the solo boot's activate/deactivate below and
     reused everywhere else - never a hardcoded guess). set_option and
     Ctrl-S are memory-only; options.cfg never changes (restore_on_leave's
     options.cfg hash check).

Reused verbatim (imported, not re-implemented):
  - repro_atom_side_transition.bring_up_lobby (the alien-side boot,
    test_ai_origin_stream.py's own bring-up).
  - test_turn_baton.bring_up_lobby / pre_ok_traditional (the baton boot).
  - session.stage_open_ground_actor / send_walk / wait_walk_settled /
    settle_reveal / assert_hash_clean (every boot).
  - sp_smoke's solo (no-coop) bring-up shape (the solo boot).

Rules: no exit(3) control flow, no tries=/attempt/retry/reroll, no "not
exercised" path, no wall-clock duration asserted (every timing assertion
is a probe EQUALITY, ms == frames x value). A fixture that cannot reach
its precondition on one construction attempt is a FIXTURE: AssertionError,
never a second design or a retry.

Run:  python tools/coop_test/test_seat_pacing.py
"""

import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, assert_hash_clean,
                      stage_open_ground_actor, send_walk, wait_walk_settled,
                      walk_action_id, last_walk, unit_pos, tile_walkable,
                      settle_reveal, DIR_DX, DIR_DY,
                      FACTION_PLAYER, FACTION_HOSTILE)
import repro_atom_walk as raw
import repro_atom_side_transition as sid
from test_turn_baton import bring_up_lobby as tb_bring_up_lobby, pre_ok_traditional

SDLK_TAB = 9      # Options::keyBattleNextUnit default
SDLK_HOME = 278   # Options::keyBattleCenterUnit default
SDLK_S = 115      # SDLK_s

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1

MISSION_AI = "STR_SMALL_SCOUT"
RACE_AI = "STR_FLOATER"
SEED_AI = 1
TALLY_TEXT_1_OF_2 = "END TURN 1/2"


# ===================== small, general, single-attempt helpers =====================


def ctrl_s(gc):
    """The chord pattern: press Ctrl+S, then clear the
    modifier state so it does not bleed into the next inject_input call."""
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_S, "mod": "ctrl"})
    gc.ok({"cmd": "inject_input", "kind": "modstate", "mod": "none"})


def speed_of(gc):
    return event_state(gc)["speed"]


def seats_map(speed):
    return {e["seat"]: (e["xcom"], e["alien"], e["fire"]) for e in speed["seats"]}


def tab_select(gc, uid, cycles=16):
    """TAB-cycle the REAL UI selection onto unit `uid` - a fixed, bounded
    pass over the (finite) roster, the same idiom repro_atom_walk.py's
    phase_host_origin and repro_atom_turn.py's run_ui_variant both use to
    reach a KNOWN state (there is no select-by-id test command for the host's
    real UI). A single deterministic pass over an enumerable list, never a
    repeated attempt at the SAME failing action."""
    for _ in range(cycles):
        if battle_state(gc).get("selectedId") == uid:
            return True
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
    return battle_state(gc).get("selectedId") == uid


def real_click_walk(host, tile):
    """ONE real-UI left-click walk order for the host's currently-selected
    unit, onto `tile` (guaranteed open by the caller's own staging). The
    map_tile_click_pos probe self-verifies before the injected click; a
    verified:false result is a FIXTURE precondition failure, reported once,
    never retried."""
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    pr = host.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert pr.get("verified"), (
        f"FIXTURE: real_click_walk: map_tile_click_pos did not verify tile {tile}: {pr}")
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"],
             "button": "left"})


def unit_of(gc, uid):
    for u in battle_state(gc)["units"]:
        if u["id"] == uid:
            return u
    return None


def host_walk_leg(host, client, soldier_id, tag, run_length=1):
    """One straight (cardinal) N-tile real-UI walk for the host-owned
    soldier `soldier_id`, staged fresh via stage_open_ground_actor (its
    _RING_DIRS is (N,E,S,W) only, so run_dir is always a STRAIGHT
    direction). Returns (ghostLast on the CLIENT, lastRead on the HOST,
    step_count) after the walk settles on both machines."""
    unit, tile, run_dir = stage_open_ground_actor(host, client, [soldier_id], tag,
                                                  run_length=run_length)
    ok = tab_select(host, unit["id"])
    assert ok, f"FIXTURE: {tag}: could not TAB-select host unit {unit['id']}"
    dest = (tile[0] + DIR_DX[run_dir] * run_length, tile[1] + DIR_DY[run_dir] * run_length, tile[2])
    prev = walk_action_id(host)
    ge0 = event_state(client)["ghostEnqueued"]
    real_click_walk(host, dest)
    wait_walk_settled(host, client, prev, timeout=20)
    settle_reveal(host, client)
    hw = last_walk(host)
    step_count = len(hw.get("steps") or [])
    ge1 = event_state(client)["ghostEnqueued"]
    assert step_count > 0, f"{tag}: the host-origin walk carries no steps: {hw}"
    assert ge1 - ge0 == step_count, (
        f"{tag}: ghostEnqueued advanced by {ge1 - ge0}, expected exactly the "
        f"{step_count} step(s) just walked")
    return event_state(client)["ghostLast"], speed_of(host)["lastRead"], step_count


def host_walk_diagonal_leg(host, client, soldier_id, tag):
    """ONE single-tile diagonal real-UI walk for the host-owned soldier
    `soldier_id`. stage_open_ground_actor only guarantees a STRAIGHT
    corridor (_RING_DIRS is cardinal-only), so the diagonal
    destination is picked by a single deterministic scan of all FOUR
    diagonal directions (a fixed candidate scan over static tile data, in
    the same shape stage_open_ground_actor's own ring scan uses - never a
    retry of an action) - the field was already cleared of every
    hostile/neutral by the staging call, so most are expected to be open;
    a map-edge corner is the only thing that can narrow this down."""
    unit, tile, run_dir = stage_open_ground_actor(host, client, [soldier_id], tag, run_length=1)
    ok = tab_select(host, unit["id"])
    assert ok, f"FIXTURE: {tag}: could not TAB-select host unit {unit['id']}"
    st = battle_state(host)
    occupied = {unit_pos(u) for u in st["units"] if not u.get("isOut")}
    dest = None
    for d in (1, 3, 5, 7):  # NE, SE, SW, NW - every diagonal, fixed order
        t = (tile[0] + DIR_DX[d], tile[1] + DIR_DY[d], tile[2])
        if tile_walkable(host, t, occupied):
            dest = t
            break
    assert dest is not None, (
        f"FIXTURE: {tag}: none of the four diagonal neighbours of the staged tile "
        f"{tile} (straight dir {run_dir}) is walkable")
    prev = walk_action_id(host)
    ge0 = event_state(client)["ghostEnqueued"]
    real_click_walk(host, dest)
    wait_walk_settled(host, client, prev, timeout=20)
    settle_reveal(host, client)
    hw = last_walk(host)
    step_count = len(hw.get("steps") or [])
    ge1 = event_state(client)["ghostEnqueued"]
    assert step_count > 0, f"{tag}: the diagonal host-origin walk carries no steps: {hw}"
    assert ge1 - ge0 == step_count, (
        f"{tag}: ghostEnqueued advanced by {ge1 - ge0}, expected exactly {step_count}")
    return event_state(client)["ghostLast"], speed_of(host)["lastRead"]


def host_turn_leg(host, client, soldier_id, tag):
    """ONE real-UI right-click body turn for the host-owned soldier
    `soldier_id`, staged in place (run_length=0: the field is cleared of
    contact, no movement needed). The click target is the OPPOSITE octant
    from the unit's current facing (4 octants away) - the maximum possible
    turn distance, so even a one-tile-off camera landing (a known quirk
    of a different click shape) still lands >= 3
    octants, comfortably over this leg's >= 2 bar. The ACTUAL landed
    octant count is read back and returned, never assumed."""
    unit, tile, _ = stage_open_ground_actor(host, client, [soldier_id], tag, run_length=0)
    ok = tab_select(host, unit["id"])
    assert ok, f"FIXTURE: {tag}: could not TAB-select host unit {unit['id']}"
    live = unit_of(host, unit["id"])
    before_dir = live["direction"]
    target_dir = (before_dir + 4) % 8
    ttile = (live["x"] + DIR_DX[target_dir], live["y"] + DIR_DY[target_dir], live["z"])

    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    pr = host.cmd({"cmd": "map_tile_click_pos", "x": ttile[0], "y": ttile[1], "z": ttile[2]})
    assert pr.get("verified"), (
        f"FIXTURE: {tag}: turn target tile {ttile} (opposite octant {target_dir}) "
        f"not verified: {pr}")

    ge0 = event_state(client)["ghostEnqueued"]
    host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"],
             "button": "right"})

    def turned():
        u2 = unit_of(host, unit["id"])
        return True if (u2 and u2["direction"] != before_dir) else None
    host.wait_for(f"{tag}: host unit turned", turned, timeout=15)
    # `turned` holds from the first octant on; the facing read below is the LANDED one, so the host's turn state
    # must have ended first (with the old 0.1 s wait_for poll it had, by poll slack only)
    host.wait_for(f"{tag}: host turn landed", lambda: (lambda b: (b.get("isBusy") is False and b.get("pendingStates") == 0)
                                                       or None)(session.battle_state(host)), timeout=15)
    settle_reveal(host, client)

    after_dir = unit_of(host, unit["id"])["direction"]
    cw = (after_dir - before_dir) % 8
    octants = min(cw, 8 - cw)
    assert octants >= 2, (
        f"{tag}: the turn only moved {octants} octant(s) ({before_dir} -> {after_dir}), "
        "expected >= 2")
    ge1 = event_state(client)["ghostEnqueued"]
    assert ge1 > ge0, f"{tag}: ghostEnqueued did not advance across the turn"
    return event_state(client)["ghostLast"], octants


def client_walk_leg(host, client, soldier_id, tag, steps=2):
    """ONE real battle_intent walk (>= `steps` tiles, straight -
    stage_open_ground_actor's _RING_DIRS is cardinal-only) for the CLIENT-owned soldier `soldier_id`,
    staged fresh. Returns (ghostLast on the CLIENT, lastRead on the HOST,
    step_count)."""
    unit, tile, run_dir = stage_open_ground_actor(host, client, [soldier_id], tag,
                                                  run_length=steps)
    dest = (tile[0] + DIR_DX[run_dir] * steps, tile[1] + DIR_DY[run_dir] * steps, tile[2])
    prev = walk_action_id(host)
    ge0 = event_state(client)["ghostEnqueued"]
    resp = send_walk(client, unit["id"], dest)
    assert resp.get("iseq"), f"FIXTURE: {tag}: client walk to {dest} was not admitted: {resp}"
    wait_walk_settled(host, client, prev, timeout=20)
    settle_reveal(host, client)
    hw = last_walk(host)
    step_count = len(hw.get("steps") or [])
    ge1 = event_state(client)["ghostEnqueued"]
    assert step_count >= 2, f"{tag}: client walk carries only {step_count} step(s), expected >= 2"
    assert ge1 - ge0 == step_count, (
        f"{tag}: ghostEnqueued advanced by {ge1 - ge0}, expected exactly {step_count}")
    return event_state(client)["ghostLast"], speed_of(host)["lastRead"], step_count


def wait_seat_dial(host, client, seat, field_idx, value, timeout=15):
    """Wait for seat `seat`'s `field_idx`-th dial (0=xcom/1=alien/2=fire) to
    read `value` in BOTH machines' own view of the table - the per-tick
    pump (onLocalChanged) plus the wire round trip are not instantaneous."""
    def done():
        h = seats_map(speed_of(host)).get(seat)
        c = seats_map(speed_of(client)).get(seat)
        return True if (h and c and h[field_idx] == value and c[field_idx] == value) else None
    host.wait_for(f"seat {seat} dial[{field_idx}] == {value} on both machines", done,
                 timeout=timeout)


# ===================== solo boot: solo control (solo_quick_mode) =====================


def run_solo_boot():
    """SOLO, one instance, NO coop (sp_smoke's own bring-up shape). Captures
    the ACTUAL rendered activate/deactivate warningText strings ONCE here -
    every later boot's Ctrl-S assertions reuse these captured values rather
    than a hardcoded guess (fact 6 in the module docstring)."""
    user = make_user_dir("seat_pacing_solo", options={"battleXcomSpeed": 22})
    host = GameClient("solo", 47992, user)
    try:
        host.spawn()
        host.connect()

        host.ok({"cmd": "open_new_battle"})
        host.wait_for("NewBattleState", lambda: session.has_state(host, "NewBattleState"),
                     timeout=60)
        host.ok({"cmd": "newbattle_ok"})
        host.wait_for(
            "SP battle generated",
            lambda: (session.has_state(host, "BriefingState")
                     or session.has_state(host, "InventoryState")
                     or session.has_state(host, "BattlescapeState")) or None,
            timeout=180, interval=0.5)
        if session.has_state(host, "BriefingState"):
            host.ok({"cmd": "close_briefing"})
        session.dismiss_battle_start_overlays(host)
        assert session.has_state(host, "BattlescapeState"), (
            f"solo boot: could not reach BattlescapeState: {battle_state(host)}")

        bs0 = battle_state(host)
        assert bs0.get("side") == FACTION_PLAYER, (
            f"solo boot premise: a fresh SP battle should start on the player side: "
            f"{bs0.get('side')}")

        speed0 = speed_of(host)
        assert speed0["seats"] == [], (
            f"solo_quick_mode premise: speed.seats is not empty in a plain SP battle: {speed0['seats']}")
        assert speed0["local"]["xcom"] == 22, (
            f"solo_quick_mode premise: local.xcom is not the configured 22: {speed0['local']}")
        xcom_before = speed0["local"]["xcom"]

        ctrl_s(host)
        host.wait_for("solo_quick_mode: local.xcom == 1 after the first Ctrl-S",
                     lambda: True if speed_of(host)["local"]["xcom"] == 1 else None, timeout=15)
        activate_text = battle_state(host).get("warningText", "")
        assert activate_text, "solo_quick_mode: warningText is empty right after the activating Ctrl-S"
        assert "activated" in activate_text.lower(), (
            f"solo_quick_mode: the activate warningText does not look like an activation message: "
            f"{activate_text!r}")
        print(f"[solo_quick_mode] captured ACTIVATE text: {activate_text!r}")

        ctrl_s(host)
        host.wait_for(f"solo_quick_mode: local.xcom restored to {xcom_before} after the second Ctrl-S",
                     lambda: True if speed_of(host)["local"]["xcom"] == xcom_before else None,
                     timeout=15)
        deactivate_text = battle_state(host).get("warningText", "")
        assert deactivate_text, "solo_quick_mode: warningText is empty right after the deactivating Ctrl-S"
        assert "deactivated" in deactivate_text.lower(), (
            f"solo_quick_mode: the deactivate warningText does not look like a deactivation message: "
            f"{deactivate_text!r}")
        print(f"[solo_quick_mode] captured DEACTIVATE text: {deactivate_text!r}")

        speed1 = speed_of(host)
        assert speed1["seats"] == [], (
            f"solo_quick_mode: speed.seats is no longer empty after Ctrl-S in a plain SP battle: "
            f"{speed1['seats']}")

        print(f"PASS solo_quick_mode: solo control - Ctrl-S activates (local.xcom 1) and restores "
              f"(local.xcom {xcom_before}); speed.seats stays empty throughout (not a "
              f"co-op battle); warningText activate={activate_text!r} "
              f"deactivate={deactivate_text!r}")
        return activate_text, deactivate_text
    finally:
        host.shutdown()


# ===================== parallel boot =====================
# entry_table, host_unit_pace, client_unit_pace, independent_dials, own_turn_quick_mode, restore_on_leave


def run_parallel_boot(activate_text, deactivate_text):
    port = "48480"
    host_dir = make_user_dir("seat_pacing_parallel_host",
                             options={"battleXcomSpeed": 10, "battleAlienSpeed": 10,
                                      "battleFireSpeed": 12})
    client_dir = make_user_dir("seat_pacing_parallel_client",
                               options={"battleXcomSpeed": 30, "battleAlienSpeed": 5,
                                        "battleFireSpeed": 4})
    host = GameClient("host", 49780, host_dir)
    client = GameClient("client", 49781, client_dir)
    seated = {}
    try:
        raw.bring_up_lobby(host, client, port)
        # h0 is captured HERE (after the host has spawned, connected and done
        # its own one-time mod-scan startup normalization - Mod.cpp's own
        # Options::save() calls, which write the full discovered-mod list and
        # every default option key back over the minimal HERMETIC_OPTIONS
        # file), NOT before spawning - a diagnostic capture before the
        # process even starts always disagrees with the post-boot file for
        # reasons that have nothing to do with set_option/Ctrl-S (traced
        # empirically: once
        # booted, options.cfg is stable across set_option, Ctrl-S and an
        # entire battle, changing again only at process shutdown).
        with open(os.path.join(host_dir, "options.cfg"), "rb") as f:
            h0 = hashlib.sha256(f.read()).hexdigest()

        session.drive_to_battlescape(host, client, seated, seat_count=5)

        hs0 = battle_state(host)
        host_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                      and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert host_units, "parallel boot fixture: seat 0 (host) has no live player unit"
        host_soldier_id = host_units[0]["soldierId"]
        client_soldier_ids = seated["soldierIds"]
        assert client_soldier_ids, "parallel boot fixture: no client-seated soldier"
        client_soldier_id = client_soldier_ids[0]

        # ----- entry_table: the table at entry -----
        expected_seats = {0: (10, 10, 12), 1: (30, 5, 4)}

        def entry_table_ready():
            hsp, csp = speed_of(host), speed_of(client)
            if seats_map(hsp) != expected_seats or seats_map(csp) != expected_seats:
                return None
            if not (hsp.get("synced") and csp.get("synced")):
                return None
            if csp.get("reportsSent", 0) < 1 or csp.get("tablesRecv", 0) < 1:
                return None
            if hsp.get("seq", 0) < 1 or csp.get("seq", 0) < 1:
                return None
            return True
        host.wait_for("entry_table: the speed table converged on both machines", entry_table_ready, timeout=30)

        hsp, csp = speed_of(host), speed_of(client)
        assert seats_map(hsp) == expected_seats, f"entry_table: host seats == {hsp['seats']}"
        assert seats_map(csp) == expected_seats, f"entry_table: client seats == {csp['seats']}"
        assert hsp["synced"] and csp["synced"], (
            f"entry_table: synced is not True on both: host={hsp['synced']} client={csp['synced']}")
        expected_floor = {"xcom": 30, "alien": 10, "fire": 4}
        assert hsp["floor"] == expected_floor, f"entry_table: host floor == {hsp['floor']}"
        assert csp["floor"] == expected_floor, (
            f"entry_table: client floor == {csp['floor']}, expected {expected_floor}. If floor() on the "
            f"client skips the client's own seat (CoopSpeed::coopSeatConnected() answers seat > 0 from "
            f"connectionTCP::session.clientInLobby, set only on the HOST's process by "
            f"CoopSession::clientAttached()), the client's floor is exactly this boot's host options "
            f"{{xcom:10, alien:10, fire:12}}. speed.seats is gated on seatValid only, so the seats_map "
            f"checks above pass either way; the same cause breaks alien_floor_raised's client floor.alien "
            f"check and unowned_floor_pace's client-side ghost pacing for an UNOWNED unit.")
        assert hsp["seq"] == csp["seq"] and hsp["seq"] >= 1, (
            f"entry_table: seq not equal/>=1: host={hsp['seq']} client={csp['seq']}")
        assert csp["reportsSent"] >= 1 and csp["tablesRecv"] >= 1, (
            f"entry_table: client reportsSent/tablesRecv too low: {csp['reportsSent']}/{csp['tablesRecv']}")
        print(f"[entry_table] entry table converged: seats={expected_seats} floor={expected_floor} "
              f"seq={hsp['seq']} client reportsSent={csp['reportsSent']} "
              f"tablesRecv={csp['tablesRecv']}")
        print("PASS entry_table")

        # ----- host_unit_pace: a HOST unit paces at the host's own setting -----
        straight_ghost, straight_lr, _ = host_walk_leg(host, client, host_soldier_id,
                                                       "host_pace_straight", run_length=1)
        assert straight_ghost["kind"] == "walk_step" and straight_ghost["seat"] == 0, (
            f"host_unit_pace straight: unexpected ghostLast: {straight_ghost}")
        assert straight_ghost["frames"] == 8, (
            f"host_unit_pace straight: expected 8 frames (straight step), got {straight_ghost}")
        assert straight_ghost["ms"] == straight_ghost["frames"] * 10, (
            f"host_unit_pace straight: ms != frames*10: {straight_ghost}")
        assert straight_lr == {"which": "xcom", "value": 10, "seat": 0}, (
            f"host_unit_pace straight: host lastRead == {straight_lr}")
        assert_hash_clean(host, client, full=True, what="host_unit_pace after the straight host walk")

        diag_ghost, diag_lr = host_walk_diagonal_leg(host, client, host_soldier_id, "host_pace_diagonal")
        assert diag_ghost["kind"] == "walk_step" and diag_ghost["seat"] == 0, (
            f"host_unit_pace diagonal: unexpected ghostLast: {diag_ghost}")
        assert diag_ghost["frames"] == 16, (
            f"host_unit_pace diagonal: expected 16 frames (diagonal step), got {diag_ghost}")
        assert diag_ghost["ms"] == diag_ghost["frames"] * 10, (
            f"host_unit_pace diagonal: ms != frames*10: {diag_ghost}")
        assert diag_lr == {"which": "xcom", "value": 10, "seat": 0}, (
            f"host_unit_pace diagonal: host lastRead == {diag_lr}")
        assert_hash_clean(host, client, full=True, what="host_unit_pace after the diagonal host walk")

        turn_ghost, octants = host_turn_leg(host, client, host_soldier_id, "host_pace_turn")
        assert turn_ghost["kind"] == "turn" and turn_ghost["seat"] == 0, (
            f"host_unit_pace turn: unexpected ghostLast: {turn_ghost}")
        assert turn_ghost["frames"] == octants, (
            f"host_unit_pace turn: frames {turn_ghost['frames']} != the {octants} octants actually turned")
        assert turn_ghost["ms"] == octants * 10, f"host_unit_pace turn: ms != octants*10: {turn_ghost}"
        assert_hash_clean(host, client, full=True, what="host_unit_pace after the host turn")
        print(f"[host_unit_pace] host unit paced at 10: straight={straight_ghost} diagonal={diag_ghost} "
              f"turn={turn_ghost} (octants={octants})")
        print("PASS host_unit_pace")

        # ----- client_unit_pace: a CLIENT unit paces at the client's own setting -----
        c_ghost, c_lr, c_steps = client_walk_leg(host, client, client_soldier_id, "client_pace_walk",
                                                 steps=2)
        assert c_ghost["kind"] == "walk_step" and c_ghost["seat"] == 1, (
            f"client_unit_pace: unexpected ghostLast: {c_ghost}")
        assert c_ghost["ms"] == c_ghost["frames"] * 30, f"client_unit_pace: ms != frames*30: {c_ghost}"
        assert c_lr == {"which": "xcom", "value": 30, "seat": 1}, f"client_unit_pace: host lastRead == {c_lr}"
        assert_hash_clean(host, client, full=True, what="client_unit_pace after the client walk")
        print(f"[client_unit_pace] client unit ({c_steps} step(s)) paced at 30: ghostLast={c_ghost} lastRead={c_lr}")
        print("PASS client_unit_pace")

        # ----- independent_dials: per-seat + independent -----
        seq_h0, seq_c0 = speed_of(host)["seq"], speed_of(client)["seq"]
        client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 40})
        wait_seat_dial(host, client, 1, 0, 40, timeout=15)
        assert speed_of(host)["seq"] > seq_h0 and speed_of(client)["seq"] > seq_c0, (
            "client_dial_seq: seq did not strictly increase on both machines after the client's "
            f"set_option: host {seq_h0}->{speed_of(host)['seq']} "
            f"client {seq_c0}->{speed_of(client)['seq']}")
        assert speed_of(client)["synced"], "client_dial_seq: client synced is not True after set_option"

        g40, lr40, _ = client_walk_leg(host, client, client_soldier_id, "client_dial_40", steps=2)
        assert g40["ms"] == g40["frames"] * 40, f"client_dial_pace: client ghost ms != frames*40: {g40}"
        assert lr40 == {"which": "xcom", "value": 40, "seat": 1}, f"client_dial_pace: host lastRead == {lr40}"

        gh10, lr10, _ = host_walk_leg(host, client, host_soldier_id, "host_still_10")
        assert gh10["ms"] == gh10["frames"] * 10, (
            f"host_pace_unchanged: host unit's pace changed after the CLIENT's speed bump: {gh10}")
        assert lr10 == {"which": "xcom", "value": 10, "seat": 0}, f"host_pace_unchanged: host lastRead == {lr10}"

        seq_h1, seq_c1 = speed_of(host)["seq"], speed_of(client)["seq"]
        host.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 20})
        wait_seat_dial(host, client, 0, 0, 20, timeout=15)
        assert speed_of(host)["seq"] > seq_h1 and speed_of(client)["seq"] > seq_c1, (
            "host_dial_seq: seq did not strictly increase on both machines after the host's set_option")

        gh20, lr20, _ = host_walk_leg(host, client, host_soldier_id, "host_dial_20")
        assert gh20["ms"] == gh20["frames"] * 20, f"host_dial_pace: host ghost ms != frames*20: {gh20}"
        assert lr20 == {"which": "xcom", "value": 20, "seat": 0}, f"host_dial_pace: host lastRead == {lr20}"

        # same_value_no_seq: the vacuity guard - setting the SAME value again produces NO
        # table change (onLocalChanged only reports/republishes on a real
        # local diff), so seq must stay put. A short settle window (not an
        # asserted duration) stands in for "wait for a change that must not
        # happen" - there is nothing to wait_for here.
        seq_h2, seq_c2 = speed_of(host)["seq"], speed_of(client)["seq"]
        client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 40})
        time.sleep(1.0)
        assert speed_of(host)["seq"] == seq_h2 and speed_of(client)["seq"] == seq_c2, (
            f"same_value_no_seq vacuity guard FAILED: re-setting the SAME value moved seq: "
            f"host {seq_h2}->{speed_of(host)['seq']} client {seq_c2}->{speed_of(client)['seq']}")

        seq_h3, seq_c3 = speed_of(host)["seq"], speed_of(client)["seq"]
        client.ok({"cmd": "set_option", "name": "battleAlienSpeed", "value": 40})
        host.wait_for("alien_floor_raised: floor.alien == 40 on the host",
                     lambda: True if speed_of(host).get("floor", {}).get("alien") == 40
                     else None, timeout=15)
        assert speed_of(host)["seq"] > seq_h3 and speed_of(client)["seq"] > seq_c3, (
            "alien_floor_raised: seq did not strictly increase after the client's alien-speed change")
        assert speed_of(client).get("floor", {}).get("alien") == 40, (
            f"alien_floor_raised: client floor.alien == {speed_of(client).get('floor', {}).get('alien')}, "
            f"expected 40 - the same cause as entry_table's client floor check (see its message): a "
            f"client floor() that skips the client's own seat never sees its OWN 40 and reports only the "
            f"host's alien dial.")
        print(f"[independent_dials] independent per-seat dials: client->40 (ghost {g40}), host unaffected "
              f"(ghost {gh10}), host->20 (ghost {gh20}), redundant re-set produced no seq "
              f"change (vacuity), client alien->40 raised floor.alien to 40 on both")
        print("PASS independent_dials")

        # ----- own_turn_quick_mode: Ctrl-S on your own turn speeds only your own units -----
        qmi_h0 = speed_of(host)["quickModeIgnored"]
        qmi_c0 = speed_of(client)["quickModeIgnored"]

        before_host_xcom = speed_of(host)["local"]["xcom"]
        assert before_host_xcom == 20, (
            f"own_turn_quick_mode premise: expected the host's xcom dial to still be 20 from host_dial_seq, got "
            f"{before_host_xcom}")
        seq_h4, seq_c4 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, 1, timeout=15)
        assert speed_of(host)["local"]["xcom"] == 1, "own_turn_quick_mode: host local.xcom != 1 after Ctrl-S"
        assert speed_of(host)["seq"] > seq_h4 and speed_of(client)["seq"] > seq_c4, (
            "own_turn_quick_mode: seq did not strictly increase on both after the host's activating Ctrl-S")
        assert battle_state(host).get("warningText") == activate_text, (
            f"own_turn_quick_mode: host warningText == {battle_state(host).get('warningText')!r}, "
            f"expected the captured activate text {activate_text!r}")

        gh1, lr1, _ = host_walk_leg(host, client, host_soldier_id, "host_quick")
        assert gh1["ms"] == gh1["frames"] * 1, f"own_turn_quick_mode: host quick-mode ghost ms != frames*1: {gh1}"
        assert lr1 == {"which": "xcom", "value": 1, "seat": 0}, f"own_turn_quick_mode: host lastRead == {lr1}"

        seq_h5, seq_c5 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, before_host_xcom, timeout=15)
        assert speed_of(host)["seq"] > seq_h5 and speed_of(client)["seq"] > seq_c5, (
            "own_turn_quick_mode: seq did not strictly increase on both after the host's restoring Ctrl-S")
        assert battle_state(host).get("warningText") == deactivate_text, (
            f"own_turn_quick_mode: host warningText == {battle_state(host).get('warningText')!r}, "
            f"expected the captured deactivate text {deactivate_text!r}")

        before_client_xcom = speed_of(client)["local"]["xcom"]
        seq_h6, seq_c6 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, 1, timeout=15)
        assert speed_of(client)["local"]["xcom"] == 1, "own_turn_quick_mode: client local.xcom != 1 after Ctrl-S"
        assert speed_of(host)["seq"] > seq_h6 and speed_of(client)["seq"] > seq_c6, (
            "own_turn_quick_mode: seq did not strictly increase on both after the client's activating Ctrl-S")

        gc1, lrc1, _ = client_walk_leg(host, client, client_soldier_id, "client_quick",
                                       steps=2)
        assert gc1["ms"] == gc1["frames"] * 1, f"own_turn_quick_mode: client quick-mode ghost ms != frames*1: {gc1}"
        assert lrc1 == {"which": "xcom", "value": 1, "seat": 1}, f"own_turn_quick_mode: host lastRead == {lrc1}"

        gh20b, lr20b, _ = host_walk_leg(host, client, host_soldier_id, "host_still_20")
        assert gh20b["ms"] == gh20b["frames"] * before_host_xcom, (
            f"own_turn_quick_mode: host pace changed while the CLIENT was in quick mode: {gh20b}")
        assert lr20b == {"which": "xcom", "value": before_host_xcom, "seat": 0}, (
            f"own_turn_quick_mode: host lastRead == {lr20b}")

        seq_h7, seq_c7 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, before_client_xcom, timeout=15)
        assert speed_of(host)["seq"] > seq_h7 and speed_of(client)["seq"] > seq_c7, (
            "own_turn_quick_mode: seq did not strictly increase on both after the client's restoring Ctrl-S")

        assert speed_of(host)["quickModeIgnored"] == qmi_h0, (
            "own_turn_quick_mode: quickModeIgnored moved on the host during allowed own-turn Ctrl-S presses: "
            f"{qmi_h0} -> {speed_of(host)['quickModeIgnored']}")
        assert speed_of(client)["quickModeIgnored"] == qmi_c0, (
            "own_turn_quick_mode: quickModeIgnored moved on the client during allowed own-turn Ctrl-S presses: "
            f"{qmi_c0} -> {speed_of(client)['quickModeIgnored']}")
        print(f"[own_turn_quick_mode] parallel own-turn Ctrl-S: host 1x <-> {before_host_xcom}, client "
              f"1x <-> {before_client_xcom}, cross-seat isolation held (gh10 during client "
              f"quick mode: {gh20b}); quickModeIgnored unchanged both sides "
              f"(host={qmi_h0} client={qmi_c0})")
        print("PASS own_turn_quick_mode")

        # ----- restore_on_leave: restore -----
        host.ok({"cmd": "disconnect_to_menu"})
        client.ok({"cmd": "disconnect_to_menu"})
        host.wait_for("restore_on_leave: host speed table cleared after disconnect",
                     lambda: True if speed_of(host).get("seats") == [] else None, timeout=20)
        client.wait_for("restore_on_leave: client speed table cleared after disconnect",
                        lambda: True if speed_of(client).get("seats") == [] else None, timeout=20)
        assert speed_of(host)["floor"] is None, (
            f"restore_on_leave: host floor is not null outside a coop battle: {speed_of(host)['floor']}")
        with open(os.path.join(host_dir, "options.cfg"), "rb") as f:
            h_after = hashlib.sha256(f.read()).hexdigest()
        assert h_after == h0, (
            "restore_on_leave: host options.cfg changed across the whole boot (set_option/Ctrl-S must be "
            f"memory-only): before={h0} after={h_after}")
        print(f"[restore_on_leave] both machines' speed.seats cleared, host floor null, host options.cfg "
              f"sha256 unchanged ({h0[:12]}...)")
        print("PASS restore_on_leave")
    finally:
        host.shutdown()
        client.shutdown()


# ===================== alien-side boot: unowned units =====================
# alien_side_quick_ignored, unowned_floor_pace


def run_alien_side_boot(activate_text, deactivate_text):
    """test_ai_origin_stream.py's fixture, verbatim (its own
    bring-up/pin/strip recipe) - mission STR_SMALL_SCOUT, race STR_FLOATER,
    seed 1, every live hostile stripped + psiSkill 0 on both machines."""
    port = "48481"
    host_dir = make_user_dir("seat_pacing_alien_side_host", options={"battleAlienSpeed": 12})
    client_dir = make_user_dir("seat_pacing_alien_side_client", options={"battleAlienSpeed": 33})
    host = GameClient("host", 49782, host_dir)
    client = GameClient("client", 49783, client_dir)
    seated = {}
    try:
        sid.bring_up_lobby(host, client, port)
        session.drive_to_battlescape(
            host, client, seated, mission=MISSION_AI, seat_count=2,
            pre_seat=lambda h: h.ok({"cmd": "newbattle_race", "race": RACE_AI}),
            pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_AI}))

        hostiles = [u for u in battle_state(host)["units"]
                    if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        hostile_ids = [u["id"] for u in hostiles]
        assert hostile_ids, f"alien-side boot fixture: no live hostile on the pinned seed {SEED_AI}"
        for uid in hostile_ids:
            rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})  # client first
            rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
            assert rh.get("ok") and rc.get("ok"), (
                f"alien-side boot fixture: battle_strip_unit failed for {uid}: host={rh} client={rc}")
            session.wait_seq_barrier(host, client)
            client.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})
            host.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})
            session.wait_seq_barrier(host, client)

        wc0 = (event_state(host).get("lastWalk") or {}).get("actionId", 0)
        turn0 = battle_state(host)["turn"]

        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        host.wait_for("host paints END TURN 1/2 after the client's arm", host_shows_1_of_2,
                     timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        # ----- alien_side_quick_ignored: Ctrl-S during the non-player side is ignored -----
        # The ignore does not come from CoopSpeed::quickModeAllowed(): a NextTurnState popup sits on
        # top of the state stack the instant the side leaves the player side, and
        # BattlescapeState::handle() gates ALL key dispatch on
        # `_game->getCursor()->getVisible() || rightClick` - while that popup owns the stack the
        # cursor is hidden and a keydown never reaches BattlescapeState's own Ctrl-S branch at all.
        # Captures on both machines pressing Ctrl-S at this exact moment measured quickModeIgnored
        # UNCHANGED (delta 0, not +1) and local.alien UNCHANGED, with NextTurnState on top right
        # before the press. "Mid AI-walk, isBusy" cannot be caught instead: left undisturbed the
        # alien side does not progress AT ALL (a 20 s probe with no dismiss call never saw it return
        # to the player side), so the AI only runs once something dismisses the popup, and then the
        # whole side resolves within a handful of command round trips. The ignore (local.alien
        # unchanged, no quick-mode text) holds either way; quickModeAllowed() is a defensive backstop
        # for this side (never reached here), proven by baton_quick_mode's off-baton case in the
        # baton boot.
        #
        # Non-vacuity: each press's "unchanged" assertions are meaningless unless the key had a live
        # consumer - proven by reading the top state (get_palettes) immediately BEFORE the press and
        # requiring it to be NextTurnState (a popup that actually owns input focus). The CLIENT leg
        # runs FIRST: client-side reads/injects never advance the HOST's own simulation, whereas the
        # HOST's own command processing reliably advances the side as a side effect of being read -
        # so the client's window is tested while still undisturbed, and the host leg (which does move
        # the side on) runs last, right before unowned_floor_pace needs it to move on anyway.
        def side_not_player_minimal(gc, timeout=15, interval=0.005):
            """Minimal-read tight poll (battle_state ONLY), measured
            stable (side leaves the player side within
            ~50ms of the 2nd end_turn press and stays there indefinitely with
            no other command sent)."""
            t0 = time.time()
            while time.time() - t0 < timeout:
                bs = battle_state(gc)
                if bs.get("side") != FACTION_PLAYER:
                    return bs
                time.sleep(interval)
            return None

        def top_state_of(gc):
            r = gc.cmd({"cmd": "get_palettes"})
            states = [e.get("state") for e in r.get("states", [])]
            return states[-1] if states else None

        # ----- client leg -----
        bs_c = side_not_player_minimal(client)
        assert bs_c is not None, (
            "FIXTURE: alien_side_quick_ignored: client battle_state.side never left the player side within 15s")
        top_c_before = top_state_of(client)
        assert top_c_before and "NextTurnState" in top_c_before, (
            f"FIXTURE: alien_side_quick_ignored non-vacuity: client top state at press time is {top_c_before!r}, "
            "not NextTurnState - the press would have no live consumer to prove ignored")
        alien_c0 = speed_of(client)["local"]["alien"]
        qmi_c0 = speed_of(client)["quickModeIgnored"]
        ctrl_s(client)
        assert speed_of(client)["local"]["alien"] == alien_c0, (
            f"alien_side_quick_ignored: client local.alien moved on the non-player side: {alien_c0} -> "
            f"{speed_of(client)['local']['alien']}")
        assert speed_of(client)["quickModeIgnored"] == qmi_c0, (
            f"alien_side_quick_ignored: client quickModeIgnored moved (delta should be 0 - the press never "
            f"reaches the quick-mode gate): {qmi_c0} -> {speed_of(client)['quickModeIgnored']}")
        assert activate_text not in (battle_state(client).get("warningText") or ""), (
            f"alien_side_quick_ignored: client warningText shows the quick-mode activate text on the non-player "
            f"side: {battle_state(client).get('warningText')!r}")

        # ----- host leg -----
        bs_h = side_not_player_minimal(host)
        assert bs_h is not None, (
            "FIXTURE: alien_side_quick_ignored: host battle_state.side never left the player side within 15s")
        top_h_before = top_state_of(host)
        assert top_h_before and "NextTurnState" in top_h_before, (
            f"FIXTURE: alien_side_quick_ignored non-vacuity: host top state at press time is {top_h_before!r}, "
            "not NextTurnState - the press would have no live consumer to prove ignored")
        alien_h0 = speed_of(host)["local"]["alien"]
        qmi_h0 = speed_of(host)["quickModeIgnored"]
        ctrl_s(host)
        assert speed_of(host)["local"]["alien"] == alien_h0, (
            f"alien_side_quick_ignored: host local.alien moved on the non-player side: {alien_h0} -> "
            f"{speed_of(host)['local']['alien']}")
        assert speed_of(host)["quickModeIgnored"] == qmi_h0, (
            f"alien_side_quick_ignored: host quickModeIgnored moved (delta should be 0 - the press never reaches "
            f"the quick-mode gate): {qmi_h0} -> {speed_of(host)['quickModeIgnored']}")
        assert activate_text not in (battle_state(host).get("warningText") or ""), (
            f"alien_side_quick_ignored: host warningText shows the quick-mode activate text on the non-player "
            f"side: {battle_state(host).get('warningText')!r}")

        print(f"[alien_side_quick_ignored] the ignore holds on both machines: client top-state-before="
              f"{top_c_before!r}, local.alien unchanged ({alien_c0}), quickModeIgnored "
              f"unchanged ({qmi_c0}); host top-state-before={top_h_before!r}, local.alien "
              f"unchanged ({alien_h0}), quickModeIgnored unchanged ({qmi_h0}) - ignored via "
              f"the NextTurnState/cursor-hidden input gate, never reaching the quick-mode gate")
        print("PASS alien_side_quick_ignored")

        # ----- unowned_floor_pace: unowned units pace at the slower (floor) alien setting -----
        # NOW dismiss the NextTurnState banner (both machines, every poll) and
        # wait for the host's first AI-origin walk chain to settle - the same
        # wait_walk_settled() shape every other boot uses, with the popup
        # dismissal folded in (the alien side cannot even start moving while
        # it stands).
        def ai_walk_settled():
            sid.dismiss_next_turn_if_present(host)
            sid.dismiss_next_turn_if_present(client)
            cs, hs = event_state(client), event_state(host)  # the client is read first
            hw = hs.get("lastWalk") or {}
            return bool(hs.get("ok") and cs.get("ok")
                        and hw and hw.get("actionId", 0) != wc0
                        and hw.get("origin") == "ai" and hw.get("active") is False
                        and hw.get("restate")
                        and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                        and cs.get("queueDepth") == 0 and hs.get("queueDepth") == 0)
        host.wait_for("unowned_floor_pace: the host's first AI-origin walk settles (NextTurnState "
                     "dismissed on both machines to let it run)", ai_walk_settled, timeout=30)
        settle_reveal(host, client)

        hw = event_state(host).get("lastWalk") or {}
        assert hw.get("origin") == "ai", f"unowned_floor_pace: host lastWalk.origin is not 'ai': {hw}"
        lr = speed_of(host)["lastRead"]
        assert lr == {"which": "alien", "value": 33, "seat": -1}, (
            f"unowned_floor_pace: host lastRead == {lr}, expected the FLOOR (max(12,33)=33), seat -1 (unowned)")

        gl = event_state(client)["ghostLast"]
        assert gl["kind"] == "walk_step" and gl["seat"] == -1, (
            f"unowned_floor_pace: unexpected CLIENT ghostLast: {gl}")
        assert gl["ms"] == gl["frames"] * 33, (
            f"unowned_floor_pace: client ghostLast ms != frames*33: {gl}. The same cause as entry_table's "
            f"client floor check: CoopGhost::onEvApplied()'s paceMsFor() -> CoopSpeed::speedFor() falls "
            f"through to floor() for this UNOWNED alien unit, and a client floor() that skips the "
            f"client's own seat sees only the HOST's alien dial (12): ms == frames*12, not frames*33.")

        hd = event_state(host).get("desyncSeen")
        cd = event_state(client).get("desyncSeen")
        assert hd is False and cd is False, (
            f"unowned_floor_pace: desyncSeen is not False on both machines: host={hd} client={cd}")
        assert_hash_clean(host, client, full=True, what="unowned_floor_pace after the host's first AI walk")
        print(f"[unowned_floor_pace] unowned alien unit paced at the floor (33): host lastRead={lr} "
              f"client ghostLast={gl}; desyncSeen False on both, hash clean")
        print("PASS unowned_floor_pace")

        # ----- drain the rest of the alien side before shutdown -----
        deadline = time.time() + 60
        while time.time() < deadline:
            sid.dismiss_next_turn_if_present(host)
            hs = battle_state(host)
            if hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1:
                break
            time.sleep(0.1)
    finally:
        host.shutdown()
        client.shutdown()


# ===================== baton boot: traditional baton (baton_quick_mode) =====================


def run_baton_boot(activate_text, deactivate_text):
    port = "48482"
    host_dir = make_user_dir("seat_pacing_baton_host", options={"battleXcomSpeed": 20})
    client_dir = make_user_dir("seat_pacing_baton_client", options={"battleXcomSpeed": 25})
    host = GameClient("host", 49784, host_dir)
    client = GameClient("client", 49785, client_dir)
    seated = {}
    try:
        tb_bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, seat_count=2,
                                     pre_ok=pre_ok_traditional)

        assert event_state(host).get("turnMode") == "traditional", (
            f"baton boot fixture: host turnMode is not 'traditional': "
            f"{event_state(host).get('turnMode')}")
        assert event_state(client).get("turnMode") == "traditional", (
            f"baton boot fixture: client turnMode is not 'traditional': "
            f"{event_state(client).get('turnMode')}")
        assert event_state(host).get("coopActiveSeat") == 0, (
            f"baton_quick_mode premise: coopActiveSeat is not 0 at entry on the host: "
            f"{event_state(host).get('coopActiveSeat')}")
        assert event_state(client).get("coopActiveSeat") == 0, (
            f"baton_quick_mode premise: coopActiveSeat is not 0 at entry on the client: "
            f"{event_state(client).get('coopActiveSeat')}")

        # ----- off-baton (seat 1/client) Ctrl-S: ignored -----
        xcom_c0 = speed_of(client)["local"]["xcom"]
        qmi_c0 = speed_of(client)["quickModeIgnored"]
        ctrl_s(client)
        assert speed_of(client)["local"]["xcom"] == xcom_c0, (
            f"baton_quick_mode: off-baton client local.xcom moved: {xcom_c0} -> "
            f"{speed_of(client)['local']['xcom']}")
        assert speed_of(client)["quickModeIgnored"] == qmi_c0 + 1, (
            f"baton_quick_mode: off-baton client quickModeIgnored did not rise by 1: {qmi_c0} -> "
            f"{speed_of(client)['quickModeIgnored']}")

        # ----- on-baton (seat 0/host) Ctrl-S: allowed, both directions -----
        xcom_h0 = speed_of(host)["local"]["xcom"]
        assert xcom_h0 == 20, f"baton_quick_mode premise: expected the host's xcom dial to start at 20, got {xcom_h0}"
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, 1, timeout=15)
        assert speed_of(host)["local"]["xcom"] == 1, "baton_quick_mode: on-baton host local.xcom != 1"
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, xcom_h0, timeout=15)
        assert speed_of(host)["local"]["xcom"] == xcom_h0, (
            f"baton_quick_mode: on-baton host local.xcom did not restore to {xcom_h0}")
        print(f"[baton_quick_mode seat0] off-baton client Ctrl-S ignored (xcom unchanged {xcom_c0}, "
              f"quickModeIgnored {qmi_c0}->{speed_of(client)['quickModeIgnored']}); "
              f"on-baton host Ctrl-S allowed (1x <-> {xcom_h0})")

        # ----- pass the baton (host's END TURN) -----
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def baton_at_seat_1():
            return True if (event_state(host).get("coopActiveSeat") == 1
                             and event_state(client).get("coopActiveSeat") == 1) else None
        host.wait_for("baton_quick_mode: the host's END TURN hands the baton to seat 1 on both machines",
                     baton_at_seat_1, timeout=15)

        # ----- now off-baton (seat 0/host) Ctrl-S: ignored -----
        xcom_h1 = speed_of(host)["local"]["xcom"]
        qmi_h1 = speed_of(host)["quickModeIgnored"]
        ctrl_s(host)
        assert speed_of(host)["local"]["xcom"] == xcom_h1, (
            f"baton_quick_mode: off-baton host local.xcom moved after the pass: {xcom_h1} -> "
            f"{speed_of(host)['local']['xcom']}")
        assert speed_of(host)["quickModeIgnored"] == qmi_h1 + 1, (
            f"baton_quick_mode: off-baton host quickModeIgnored did not rise by 1 after the pass: {qmi_h1} -> "
            f"{speed_of(host)['quickModeIgnored']}")

        # ----- now on-baton (seat 1/client) Ctrl-S: allowed, both directions -----
        xcom_c1 = speed_of(client)["local"]["xcom"]
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, 1, timeout=15)
        assert speed_of(client)["local"]["xcom"] == 1, "baton_quick_mode: on-baton client local.xcom != 1"
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, xcom_c1, timeout=15)
        assert speed_of(client)["local"]["xcom"] == xcom_c1, (
            f"baton_quick_mode: on-baton client local.xcom did not restore to {xcom_c1}")
        print(f"[baton_quick_mode seat1] off-baton host Ctrl-S ignored (xcom unchanged {xcom_h1}, "
              f"quickModeIgnored {qmi_h1}->{speed_of(host)['quickModeIgnored']}); "
              f"on-baton client Ctrl-S allowed (1x <-> {xcom_c1})")
        print("PASS baton_quick_mode")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    t0 = time.time()
    activate_text, deactivate_text = run_solo_boot()
    run_parallel_boot(activate_text, deactivate_text)
    run_alien_side_boot(activate_text, deactivate_text)
    run_baton_boot(activate_text, deactivate_text)
    print(f"\nALL test_seat_pacing TESTS PASSED ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_seat_pacing", e.tracking, str(e))
        print(f"\ntest_seat_pacing: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_seat_pacing: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_seat_pacing: FAIL\nTimeoutError: {e}")
        sys.exit(2)
