"""SPEC 17 (W1-P18) - test_rw_seat_pacing.py: per-seat animation pacing
(CoopSpeed) - the per-seat speed table, the floor fallback for unowned
(alien) units, the three set_option dial arms, the Ctrl-S "Usain Bolt"
quick-mode gate (parallel/traditional/alien-side/solo), and the ghost
pacing derivation (frames x the acting seat's dial == ms) landed by
Builders A/B's 7 commits on rwsettle2-wip (M1-M6). Ten scenarios (S1-S10)
across four boots, pinned by the R1 findings below (measured against the
tip's src/CoopMod/CoopSpeed.h / connectionTCP.cpp / TestServer.cpp and
src/Battlescape/BattlescapeState.cpp - never re-derived here):

  1. floor = MAX xcom, MAX alien, MIN fire (CoopSpeed::floor()) - the
     slower-of-the-two-machines value wins for xcom/alien speed dials, and
     the FASTER machine's fire-speed number (numerically lower = faster
     animation) wins there.
  2. ghost frames: 8 for a straight or vertical (z-change) walk step, 16
     for a diagonal one; 1 frame per turn octant (shorter modular arc);
     kneel is a fixed 100 ms (untouched by this packet). ms == frames x
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
     map_tile_click_pos + inject_input click) - SS2.5's "host-local input
     never enters the intent path" (repro_atom_walk.py phase6b_host_origin
     precedent). A client-owned unit walks via battle_intent/send_walk.
  5. The raw drive_to_battlescape spawn has no walkable, contact-free
     tile (units packed in the Skyranger, random-map aliens in view).
     Every walk/turn fixture below stages its actor first via
     session.stage_open_ground_actor (WV-D86) - never re-rolled.
  6. Ctrl-S: inject_input {kind:"key",key:115,mod:"ctrl"}, cleared with
     {kind:"modstate",mod:"none"}. warningText renders OXCE's own
     STR_QUICK_MODE_ACTIVATED / STR_QUICK_MODE_DEACTIVATED strings (read
     ONCE at runtime from Boot D's solo activate/deactivate below and
     reused everywhere else - never a hardcoded guess). set_option and
     Ctrl-S are memory-only; options.cfg never changes (S6's H0 proof).

Reused verbatim (imported, not re-implemented):
  - repro_atom_side_transition.bring_up_lobby (Boot B, test_rw_ai_origin_
    stream.py's own bring-up).
  - test_rw_turn_baton.bring_up_lobby / pre_ok_traditional (Boot C).
  - session.stage_open_ground_actor / send_walk / wait_walk_settled /
    settle_reveal / assert_hash_clean (every boot).
  - sp_smoke's solo (no-coop) bring-up shape (Boot D).

Binding rules followed (SPEC 17 W1-P18 orch48 brief, section A.8): no
exit(3) control flow added here, no tries=/attempt/retry/reroll, no "not
exercised" path, no wall-clock duration asserted (every timing assertion
is a probe EQUALITY, ms == frames x value). A fixture that cannot reach
its precondition on one construction attempt is a FIXTURE: AssertionError,
never a second design or a retry.

Run:  python tools/coop_test/test_rw_seat_pacing.py
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
from test_rw_turn_baton import bring_up_lobby as tb_bring_up_lobby, pre_ok_traditional

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
    """The W1-P2 chord pattern (brief-pinned): press Ctrl+S, then clear the
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
    phase6b_host_origin and repro_atom_turn.py's run_ui_variant both use to
    reach a KNOWN state (there is no select-by-id lever for the host's real
    UI). A single deterministic pass over an enumerable list, never a
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
    never retried (W1-P6)."""
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
    soldier `soldier_id`, staged fresh via stage_open_ground_actor (WV-D86:
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
    corridor (R1: _RING_DIRS is cardinal-only), so the diagonal
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
    turn distance, so even a one-tile-off camera landing (W1-P6's own
    documented quirk for a different click shape) still lands >= 3
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
    """ONE real battle_intent walk (>= `steps` tiles, straight - WV-D86's
    _RING_DIRS is cardinal-only) for the CLIENT-owned soldier `soldier_id`,
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


# ===================== BOOT D: solo control (S10) =====================


def run_boot_d():
    """SOLO, one instance, NO coop (sp_smoke's own bring-up shape). Captures
    the ACTUAL rendered activate/deactivate warningText strings ONCE here -
    every later boot's Ctrl-S assertions reuse these captured values rather
    than a hardcoded guess (R1 finding 6)."""
    user = make_user_dir("seat_pacing_d_solo", options={"battleXcomSpeed": 22})
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
            f"boot D: could not reach BattlescapeState: {battle_state(host)}")

        bs0 = battle_state(host)
        assert bs0.get("side") == FACTION_PLAYER, (
            f"boot D premise: a fresh SP battle should start on the player side: "
            f"{bs0.get('side')}")

        speed0 = speed_of(host)
        assert speed0["seats"] == [], (
            f"S10 premise: speed.seats is not empty in a plain SP battle: {speed0['seats']}")
        assert speed0["local"]["xcom"] == 22, (
            f"S10 premise: local.xcom is not the configured 22: {speed0['local']}")
        xcom_before = speed0["local"]["xcom"]

        ctrl_s(host)
        host.wait_for("S10: local.xcom == 1 after the first Ctrl-S",
                     lambda: True if speed_of(host)["local"]["xcom"] == 1 else None, timeout=15)
        activate_text = battle_state(host).get("warningText", "")
        assert activate_text, "S10: warningText is empty right after the activating Ctrl-S"
        assert "activated" in activate_text.lower(), (
            f"S10: the activate warningText does not look like an activation message: "
            f"{activate_text!r}")
        print(f"[S10] captured ACTIVATE text: {activate_text!r}")

        ctrl_s(host)
        host.wait_for(f"S10: local.xcom restored to {xcom_before} after the second Ctrl-S",
                     lambda: True if speed_of(host)["local"]["xcom"] == xcom_before else None,
                     timeout=15)
        deactivate_text = battle_state(host).get("warningText", "")
        assert deactivate_text, "S10: warningText is empty right after the deactivating Ctrl-S"
        assert "deactivated" in deactivate_text.lower(), (
            f"S10: the deactivate warningText does not look like a deactivation message: "
            f"{deactivate_text!r}")
        print(f"[S10] captured DEACTIVATE text: {deactivate_text!r}")

        speed1 = speed_of(host)
        assert speed1["seats"] == [], (
            f"S10: speed.seats is no longer empty after Ctrl-S in a plain SP battle: "
            f"{speed1['seats']}")

        print(f"PASS S10: solo control - Ctrl-S activates (local.xcom 1) and restores "
              f"(local.xcom {xcom_before}); speed.seats stays empty throughout (not a "
              f"co-op battle); warningText activate={activate_text!r} "
              f"deactivate={deactivate_text!r}")
        return activate_text, deactivate_text
    finally:
        host.shutdown()


# ===================== BOOT A: parallel (S1,S2,S3,S4,S7,S6) =====================


def run_boot_a(activate_text, deactivate_text):
    port = "48480"
    host_dir = make_user_dir("seat_pacing_a_host",
                             options={"battleXcomSpeed": 10, "battleAlienSpeed": 10,
                                      "battleFireSpeed": 12})
    client_dir = make_user_dir("seat_pacing_a_client",
                               options={"battleXcomSpeed": 30, "battleAlienSpeed": 5,
                                        "battleFireSpeed": 4})
    host = GameClient("host", 49780, host_dir)
    client = GameClient("client", 49781, client_dir)
    seated = {}
    try:
        raw.bring_up_lobby(host, client, port)
        # H0 is captured HERE (after the host has spawned, connected and done
        # its own one-time mod-scan startup normalization - Mod.cpp's own
        # Options::save() calls, which write the full discovered-mod list and
        # every default option key back over the minimal HERMETIC_OPTIONS
        # file), NOT before spawning - a diagnostic capture before the
        # process even starts always disagrees with the post-boot file for
        # reasons that have nothing to do with set_option/Ctrl-S (F: traced
        # empirically - see the R1 finding this leg actually tests: once
        # booted, options.cfg is stable across set_option, Ctrl-S and an
        # entire battle, changing again only at process shutdown).
        with open(os.path.join(host_dir, "options.cfg"), "rb") as f:
            h0 = hashlib.sha256(f.read()).hexdigest()

        session.drive_to_battlescape(host, client, seated, seat_count=5)

        hs0 = battle_state(host)
        host_units = [u for u in hs0["units"] if u.get("coop") == COOP_SEAT_0
                      and u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        assert host_units, "boot A fixture: seat 0 (host) has no live player unit"
        host_soldier_id = host_units[0]["soldierId"]
        client_soldier_ids = seated["soldierIds"]
        assert client_soldier_ids, "boot A fixture: no client-seated soldier"
        client_soldier_id = client_soldier_ids[0]

        # ----- S1: the table at entry -----
        expected_seats = {0: (10, 10, 12), 1: (30, 5, 4)}

        def s1_ready():
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
        host.wait_for("S1: the speed table converged on both machines", s1_ready, timeout=30)

        hsp, csp = speed_of(host), speed_of(client)
        assert seats_map(hsp) == expected_seats, f"S1: host seats == {hsp['seats']}"
        assert seats_map(csp) == expected_seats, f"S1: client seats == {csp['seats']}"
        assert hsp["synced"] and csp["synced"], (
            f"S1: synced is not True on both: host={hsp['synced']} client={csp['synced']}")
        expected_floor = {"xcom": 30, "alien": 10, "fire": 4}
        assert hsp["floor"] == expected_floor, f"S1: host floor == {hsp['floor']}"
        assert csp["floor"] == expected_floor, (
            f"S1: client floor == {csp['floor']}, expected {expected_floor}. TRACED root "
            f"cause (orch48 builder C, not a fixture issue - src/CoopMod/connectionTCP.cpp): "
            f"CoopSpeed::coopSeatConnected() (~line 8754) is a 'byte-equivalent hoist' of the "
            f"HOST-ONLY coopEndTurnSeatConnected() (~line 6312, seat==0 always true, seat>0 "
            f"answered by connectionTCP::session.clientInLobby - a flag ONLY ever set true by "
            f"CoopSession::clientAttached(), called exclusively on the HOST's own process). "
            f"On the CLIENT's own process this makes coopSeatConnected(1) - asking about the "
            f"client's OWN seat - permanently false, so CoopSpeed::floor()'s loop "
            f"('if (!coopSeatConnected(s) || !g_seatValid[s]) continue;') silently skips the "
            f"client's own seat: floor() on the client degrades to exactly the HOST's raw "
            f"local triple (confirmed: {csp['floor']} == this boot's host options {{xcom:10, "
            f"alien:10, fire:12}}), never seeing its own (higher) dial. speed.seats itself is "
            f"unaffected (gated on seatValid only, no coopSeatConnected call) - this is why "
            f"S1's seats_map assertions above already passed. Same root cause reaches S4g's "
            f"client floor.alien check and S5's client-side ghost pacing for an UNOWNED unit "
            f"(paceMsFor's floor() fallback runs on the client, where onEvApplied() lives). "
            f"Requires a src/CoopMod/connectionTCP.cpp fix (Builder A/B territory, out of "
            f"this tests-only builder's remit) - not a test-fixture defect, no relaxed "
            f"assertion applied.")
        assert hsp["seq"] == csp["seq"] and hsp["seq"] >= 1, (
            f"S1: seq not equal/>=1: host={hsp['seq']} client={csp['seq']}")
        assert csp["reportsSent"] >= 1 and csp["tablesRecv"] >= 1, (
            f"S1: client reportsSent/tablesRecv too low: {csp['reportsSent']}/{csp['tablesRecv']}")
        print(f"[S1] entry table converged: seats={expected_seats} floor={expected_floor} "
              f"seq={hsp['seq']} client reportsSent={csp['reportsSent']} "
              f"tablesRecv={csp['tablesRecv']}")
        print("PASS S1")

        # ----- S2: a HOST unit paces at the host's own setting -----
        straight_ghost, straight_lr, _ = host_walk_leg(host, client, host_soldier_id,
                                                       "s2-straight", run_length=1)
        assert straight_ghost["kind"] == "walk_step" and straight_ghost["seat"] == 0, (
            f"S2 straight: unexpected ghostLast: {straight_ghost}")
        assert straight_ghost["frames"] == 8, (
            f"S2 straight: expected 8 frames (straight step), got {straight_ghost}")
        assert straight_ghost["ms"] == straight_ghost["frames"] * 10, (
            f"S2 straight: ms != frames*10: {straight_ghost}")
        assert straight_lr == {"which": "xcom", "value": 10, "seat": 0}, (
            f"S2 straight: host lastRead == {straight_lr}")
        assert_hash_clean(host, client, full=True, what="S2 after the straight host walk")

        diag_ghost, diag_lr = host_walk_diagonal_leg(host, client, host_soldier_id, "s2-diagonal")
        assert diag_ghost["kind"] == "walk_step" and diag_ghost["seat"] == 0, (
            f"S2 diagonal: unexpected ghostLast: {diag_ghost}")
        assert diag_ghost["frames"] == 16, (
            f"S2 diagonal: expected 16 frames (diagonal step), got {diag_ghost}")
        assert diag_ghost["ms"] == diag_ghost["frames"] * 10, (
            f"S2 diagonal: ms != frames*10: {diag_ghost}")
        assert diag_lr == {"which": "xcom", "value": 10, "seat": 0}, (
            f"S2 diagonal: host lastRead == {diag_lr}")
        assert_hash_clean(host, client, full=True, what="S2 after the diagonal host walk")

        turn_ghost, octants = host_turn_leg(host, client, host_soldier_id, "s2-turn")
        assert turn_ghost["kind"] == "turn" and turn_ghost["seat"] == 0, (
            f"S2 turn: unexpected ghostLast: {turn_ghost}")
        assert turn_ghost["frames"] == octants, (
            f"S2 turn: frames {turn_ghost['frames']} != the {octants} octants actually turned")
        assert turn_ghost["ms"] == octants * 10, f"S2 turn: ms != octants*10: {turn_ghost}"
        assert_hash_clean(host, client, full=True, what="S2 after the host turn")
        print(f"[S2] host unit paced at 10: straight={straight_ghost} diagonal={diag_ghost} "
              f"turn={turn_ghost} (octants={octants})")
        print("PASS S2")

        # ----- S3: a CLIENT unit paces at the client's own setting -----
        c_ghost, c_lr, c_steps = client_walk_leg(host, client, client_soldier_id, "s3-client-walk",
                                                 steps=2)
        assert c_ghost["kind"] == "walk_step" and c_ghost["seat"] == 1, (
            f"S3: unexpected ghostLast: {c_ghost}")
        assert c_ghost["ms"] == c_ghost["frames"] * 30, f"S3: ms != frames*30: {c_ghost}"
        assert c_lr == {"which": "xcom", "value": 30, "seat": 1}, f"S3: host lastRead == {c_lr}"
        assert_hash_clean(host, client, full=True, what="S3 after the client walk")
        print(f"[S3] client unit ({c_steps} step(s)) paced at 30: ghostLast={c_ghost} lastRead={c_lr}")
        print("PASS S3")

        # ----- S4: per-seat + independent -----
        seq_h0, seq_c0 = speed_of(host)["seq"], speed_of(client)["seq"]
        client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 40})
        wait_seat_dial(host, client, 1, 0, 40, timeout=15)
        assert speed_of(host)["seq"] > seq_h0 and speed_of(client)["seq"] > seq_c0, (
            "S4a: seq did not strictly increase on both machines after the client's "
            f"set_option: host {seq_h0}->{speed_of(host)['seq']} "
            f"client {seq_c0}->{speed_of(client)['seq']}")
        assert speed_of(client)["synced"], "S4a: client synced is not True after set_option"

        g40, lr40, _ = client_walk_leg(host, client, client_soldier_id, "s4-client-40", steps=2)
        assert g40["ms"] == g40["frames"] * 40, f"S4b: client ghost ms != frames*40: {g40}"
        assert lr40 == {"which": "xcom", "value": 40, "seat": 1}, f"S4b: host lastRead == {lr40}"

        gh10, lr10, _ = host_walk_leg(host, client, host_soldier_id, "s4c-host-still-10")
        assert gh10["ms"] == gh10["frames"] * 10, (
            f"S4c: host unit's pace changed after the CLIENT's speed bump: {gh10}")
        assert lr10 == {"which": "xcom", "value": 10, "seat": 0}, f"S4c: host lastRead == {lr10}"

        seq_h1, seq_c1 = speed_of(host)["seq"], speed_of(client)["seq"]
        host.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 20})
        wait_seat_dial(host, client, 0, 0, 20, timeout=15)
        assert speed_of(host)["seq"] > seq_h1 and speed_of(client)["seq"] > seq_c1, (
            "S4d: seq did not strictly increase on both machines after the host's set_option")

        gh20, lr20, _ = host_walk_leg(host, client, host_soldier_id, "s4e-host-20")
        assert gh20["ms"] == gh20["frames"] * 20, f"S4e: host ghost ms != frames*20: {gh20}"
        assert lr20 == {"which": "xcom", "value": 20, "seat": 0}, f"S4e: host lastRead == {lr20}"

        # S4f: the vacuity guard - setting the SAME value again produces NO
        # table change (onLocalChanged only reports/republishes on a real
        # local diff), so seq must stay put. A short settle window (not an
        # asserted duration) stands in for "wait for a change that must not
        # happen" - there is nothing to wait_for here.
        seq_h2, seq_c2 = speed_of(host)["seq"], speed_of(client)["seq"]
        client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 40})
        time.sleep(1.0)
        assert speed_of(host)["seq"] == seq_h2 and speed_of(client)["seq"] == seq_c2, (
            f"S4f vacuity guard FAILED: re-setting the SAME value moved seq: "
            f"host {seq_h2}->{speed_of(host)['seq']} client {seq_c2}->{speed_of(client)['seq']}")

        seq_h3, seq_c3 = speed_of(host)["seq"], speed_of(client)["seq"]
        client.ok({"cmd": "set_option", "name": "battleAlienSpeed", "value": 40})
        host.wait_for("S4g: floor.alien == 40 on the host",
                     lambda: True if speed_of(host).get("floor", {}).get("alien") == 40
                     else None, timeout=15)
        assert speed_of(host)["seq"] > seq_h3 and speed_of(client)["seq"] > seq_c3, (
            "S4g: seq did not strictly increase after the client's alien-speed change")
        assert speed_of(client).get("floor", {}).get("alien") == 40, (
            f"S4g: client floor.alien == {speed_of(client).get('floor', {}).get('alien')}, "
            f"expected 40 - the SAME traced CoopSpeed::coopSeatConnected() defect as S1's "
            f"client floor assertion (see that assertion's message for the full root-cause "
            f"trace): the client's own floor() permanently excludes its own seat, so it never "
            f"sees its OWN 40 and reports only the host's alien dial.")
        print(f"[S4] independent per-seat dials: client->40 (ghost {g40}), host unaffected "
              f"(ghost {gh10}), host->20 (ghost {gh20}), redundant re-set produced no seq "
              f"change (vacuity), client alien->40 raised floor.alien to 40 on both")
        print("PASS S4")

        # ----- S7: Ctrl-S on your own turn speeds only your own units -----
        qmi_h0 = speed_of(host)["quickModeIgnored"]
        qmi_c0 = speed_of(client)["quickModeIgnored"]

        before_host_xcom = speed_of(host)["local"]["xcom"]
        assert before_host_xcom == 20, (
            f"S7 premise: expected the host's xcom dial to still be 20 from S4d, got "
            f"{before_host_xcom}")
        seq_h4, seq_c4 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, 1, timeout=15)
        assert speed_of(host)["local"]["xcom"] == 1, "S7: host local.xcom != 1 after Ctrl-S"
        assert speed_of(host)["seq"] > seq_h4 and speed_of(client)["seq"] > seq_c4, (
            "S7: seq did not strictly increase on both after the host's activating Ctrl-S")
        assert battle_state(host).get("warningText") == activate_text, (
            f"S7: host warningText == {battle_state(host).get('warningText')!r}, "
            f"expected the captured activate text {activate_text!r}")

        gh1, lr1, _ = host_walk_leg(host, client, host_soldier_id, "s7-host-quick")
        assert gh1["ms"] == gh1["frames"] * 1, f"S7: host quick-mode ghost ms != frames*1: {gh1}"
        assert lr1 == {"which": "xcom", "value": 1, "seat": 0}, f"S7: host lastRead == {lr1}"

        seq_h5, seq_c5 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, before_host_xcom, timeout=15)
        assert speed_of(host)["seq"] > seq_h5 and speed_of(client)["seq"] > seq_c5, (
            "S7: seq did not strictly increase on both after the host's restoring Ctrl-S")
        assert battle_state(host).get("warningText") == deactivate_text, (
            f"S7: host warningText == {battle_state(host).get('warningText')!r}, "
            f"expected the captured deactivate text {deactivate_text!r}")

        before_client_xcom = speed_of(client)["local"]["xcom"]
        seq_h6, seq_c6 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, 1, timeout=15)
        assert speed_of(client)["local"]["xcom"] == 1, "S7: client local.xcom != 1 after Ctrl-S"
        assert speed_of(host)["seq"] > seq_h6 and speed_of(client)["seq"] > seq_c6, (
            "S7: seq did not strictly increase on both after the client's activating Ctrl-S")

        gc1, lrc1, _ = client_walk_leg(host, client, client_soldier_id, "s7-client-quick",
                                       steps=2)
        assert gc1["ms"] == gc1["frames"] * 1, f"S7: client quick-mode ghost ms != frames*1: {gc1}"
        assert lrc1 == {"which": "xcom", "value": 1, "seat": 1}, f"S7: host lastRead == {lrc1}"

        gh20b, lr20b, _ = host_walk_leg(host, client, host_soldier_id, "s7-host-still-20")
        assert gh20b["ms"] == gh20b["frames"] * before_host_xcom, (
            f"S7: host pace changed while the CLIENT was in quick mode: {gh20b}")
        assert lr20b == {"which": "xcom", "value": before_host_xcom, "seat": 0}, (
            f"S7: host lastRead == {lr20b}")

        seq_h7, seq_c7 = speed_of(host)["seq"], speed_of(client)["seq"]
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, before_client_xcom, timeout=15)
        assert speed_of(host)["seq"] > seq_h7 and speed_of(client)["seq"] > seq_c7, (
            "S7: seq did not strictly increase on both after the client's restoring Ctrl-S")

        assert speed_of(host)["quickModeIgnored"] == qmi_h0, (
            "S7: quickModeIgnored moved on the host during allowed own-turn Ctrl-S presses: "
            f"{qmi_h0} -> {speed_of(host)['quickModeIgnored']}")
        assert speed_of(client)["quickModeIgnored"] == qmi_c0, (
            "S7: quickModeIgnored moved on the client during allowed own-turn Ctrl-S presses: "
            f"{qmi_c0} -> {speed_of(client)['quickModeIgnored']}")
        print(f"[S7] parallel own-turn Ctrl-S: host 1x <-> {before_host_xcom}, client "
              f"1x <-> {before_client_xcom}, cross-seat isolation held (gh10 during client "
              f"quick mode: {gh20b}); quickModeIgnored unchanged both sides "
              f"(host={qmi_h0} client={qmi_c0})")
        print("PASS S7")

        # ----- S6: restore -----
        host.ok({"cmd": "disconnect_to_menu"})
        client.ok({"cmd": "disconnect_to_menu"})
        host.wait_for("S6: host speed table cleared after disconnect",
                     lambda: True if speed_of(host).get("seats") == [] else None, timeout=20)
        client.wait_for("S6: client speed table cleared after disconnect",
                        lambda: True if speed_of(client).get("seats") == [] else None, timeout=20)
        assert speed_of(host)["floor"] is None, (
            f"S6: host floor is not null outside a coop battle: {speed_of(host)['floor']}")
        with open(os.path.join(host_dir, "options.cfg"), "rb") as f:
            h_after = hashlib.sha256(f.read()).hexdigest()
        assert h_after == h0, (
            "S6: host options.cfg changed across the whole boot (set_option/Ctrl-S must be "
            f"memory-only): before={h0} after={h_after}")
        print(f"[S6] both machines' speed.seats cleared, host floor null, host options.cfg "
              f"sha256 unchanged ({h0[:12]}...)")
        print("PASS S6")
    finally:
        host.shutdown()
        client.shutdown()


# ===================== BOOT B: unowned/alien-side (S5, S8) =====================


def run_boot_b(activate_text, deactivate_text):
    """F374's M-12 fixture, verbatim (test_rw_ai_origin_stream.py's own
    bring-up/pin/strip recipe) - mission STR_SMALL_SCOUT, race STR_FLOATER,
    seed 1, every live hostile stripped + psiSkill 0 on both machines."""
    port = "48481"
    host_dir = make_user_dir("seat_pacing_b_host", options={"battleAlienSpeed": 12})
    client_dir = make_user_dir("seat_pacing_b_client", options={"battleAlienSpeed": 33})
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
        assert hostile_ids, f"boot B fixture: no live hostile on the pinned seed {SEED_AI}"
        for uid in hostile_ids:
            rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
            rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})
            assert rh.get("ok") and rc.get("ok"), (
                f"boot B fixture: battle_strip_unit failed for {uid}: host={rh} client={rc}")
            host.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})
            client.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})

        wc0 = (event_state(host).get("lastWalk") or {}).get("actionId", 0)
        turn0 = battle_state(host)["turn"]

        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        host.wait_for("host paints END TURN 1/2 after the client's arm", host_shows_1_of_2,
                     timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        # ----- S8: Ctrl-S during the non-player side is ignored (D112) -----
        # RE-POINTED (orch48 owner ruling D112, F403): S8's original spec text
        # assumed the alien-side ignore is M6's quickModeAllowed() gate
        # (predicting quickModeIgnored +1). Instrumented captures (orch48
        # builder C, TASK 2, 4 fresh boots + a duration probe) DISPROVE that
        # mechanism: a NextTurnState popup sits on top of the state stack the
        # instant the side leaves the player side, and BattlescapeState::
        # handle() (:3007) gates ALL key dispatch on
        # `_game->getCursor()->getVisible() || rightClick` (:3031) - while
        # that popup owns the stack the cursor is hidden and a keydown never
        # reaches BattlescapeState's own Ctrl-S branch (M6) at all (SPEC 18's
        # F403). Two live captures (both machines) pressing Ctrl-S at this
        # exact moment measured quickModeIgnored UNCHANGED (delta 0, not +1)
        # and local.alien UNCHANGED, with the top state read as NextTurnState
        # immediately before the press both times; a THIRD and FOURTH capture
        # (both machines) tried to catch "mid AI-walk, isBusy" instead and
        # found it unreachable within 15s of 5ms-interval polling - left
        # completely undisturbed the alien side does not progress AT ALL (a
        # 20s duration probe with zero dismiss calls never saw it return to
        # the player side either), so the AI only ever runs once something
        # dismisses the popup, and then the whole side (transition in, every
        # AI step, transition out) resolves within the same handful of
        # command round trips - too fast to also catch "mid-walk" externally.
        # D112's RULED OUTCOME (alien-side Ctrl-S is ignored: local.alien
        # unchanged, no quick-mode text) HOLDS - only the mechanism the
        # original text assumed was wrong. M6's quickModeAllowed() gate is a
        # defensive backstop for this side (never reached here) and is
        # independently PROVEN by S9's off-baton case in Boot C.
        #
        # Non-vacuity (§A.8): each press's "unchanged" assertions are
        # meaningless unless the key had a live consumer - proven by reading
        # the top state (get_palettes) immediately BEFORE the press and
        # requiring it to be NextTurnState (a popup that actually owns input
        # focus), the same state confirmed present in both successful
        # captures above. The CLIENT leg runs FIRST: captured evidence shows
        # client-side reads/injects never advance the HOST's own simulation
        # (the client's own side stayed put through a full capture+press
        # cycle in isolation), whereas the HOST's own command processing
        # reliably advances the side as a side effect of being read - so the
        # client's window is tested while still guaranteed undisturbed, and
        # the host leg (which does move the side on) runs last, right before
        # S5 needs it to move on anyway.
        def side_not_player_minimal(gc, timeout=15, interval=0.005):
            """Minimal-read tight poll (battle_state ONLY) - the moment-(a)
            recipe TASK 2 measured stable (side leaves the player side within
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
            "FIXTURE: S8: client battle_state.side never left the player side within 15s")
        top_c_before = top_state_of(client)
        assert top_c_before and "NextTurnState" in top_c_before, (
            f"FIXTURE: S8 non-vacuity: client top state at press time is {top_c_before!r}, "
            "not NextTurnState - the press would have no live consumer to prove ignored")
        alien_c0 = speed_of(client)["local"]["alien"]
        qmi_c0 = speed_of(client)["quickModeIgnored"]
        ctrl_s(client)
        assert speed_of(client)["local"]["alien"] == alien_c0, (
            f"S8: client local.alien moved on the non-player side: {alien_c0} -> "
            f"{speed_of(client)['local']['alien']}")
        assert speed_of(client)["quickModeIgnored"] == qmi_c0, (
            f"S8: client quickModeIgnored moved (delta should be 0 - the press never "
            f"reaches M6): {qmi_c0} -> {speed_of(client)['quickModeIgnored']}")
        assert activate_text not in (battle_state(client).get("warningText") or ""), (
            f"S8: client warningText shows the quick-mode activate text on the non-player "
            f"side: {battle_state(client).get('warningText')!r}")

        # ----- host leg -----
        bs_h = side_not_player_minimal(host)
        assert bs_h is not None, (
            "FIXTURE: S8: host battle_state.side never left the player side within 15s")
        top_h_before = top_state_of(host)
        assert top_h_before and "NextTurnState" in top_h_before, (
            f"FIXTURE: S8 non-vacuity: host top state at press time is {top_h_before!r}, "
            "not NextTurnState - the press would have no live consumer to prove ignored")
        alien_h0 = speed_of(host)["local"]["alien"]
        qmi_h0 = speed_of(host)["quickModeIgnored"]
        ctrl_s(host)
        assert speed_of(host)["local"]["alien"] == alien_h0, (
            f"S8: host local.alien moved on the non-player side: {alien_h0} -> "
            f"{speed_of(host)['local']['alien']}")
        assert speed_of(host)["quickModeIgnored"] == qmi_h0, (
            f"S8: host quickModeIgnored moved (delta should be 0 - the press never reaches "
            f"M6): {qmi_h0} -> {speed_of(host)['quickModeIgnored']}")
        assert activate_text not in (battle_state(host).get("warningText") or ""), (
            f"S8: host warningText shows the quick-mode activate text on the non-player "
            f"side: {battle_state(host).get('warningText')!r}")

        print(f"[S8] D112 holds on both machines: client top-state-before="
              f"{top_c_before!r}, local.alien unchanged ({alien_c0}), quickModeIgnored "
              f"unchanged ({qmi_c0}); host top-state-before={top_h_before!r}, local.alien "
              f"unchanged ({alien_h0}), quickModeIgnored unchanged ({qmi_h0}) - ignored via "
              f"the NextTurnState/cursor-hidden input gate (F403), never reaching M6")
        print("PASS S8")

        # ----- S5: unowned units pace at the slower (floor) alien setting -----
        # NOW dismiss the NextTurnState banner (both machines, every poll) and
        # wait for the host's first AI-origin walk chain to settle - the same
        # wait_walk_settled() shape every other boot uses, with the popup
        # dismissal folded in (the alien side cannot even start moving while
        # it stands).
        def ai_walk_settled():
            sid.dismiss_next_turn_if_present(host)
            sid.dismiss_next_turn_if_present(client)
            hs, cs = event_state(host), event_state(client)
            hw = hs.get("lastWalk") or {}
            return bool(hs.get("ok") and cs.get("ok")
                        and hw and hw.get("actionId", 0) != wc0
                        and hw.get("origin") == "ai" and hw.get("active") is False
                        and hw.get("restate")
                        and cs.get("lastSeqApplied", 0) == hs.get("lastSeqEmitted", 0)
                        and cs.get("queueDepth") == 0 and hs.get("queueDepth") == 0)
        host.wait_for("S5: the host's first AI-origin walk settles (NextTurnState "
                     "dismissed on both machines to let it run)", ai_walk_settled, timeout=30)
        settle_reveal(host, client)

        hw = event_state(host).get("lastWalk") or {}
        assert hw.get("origin") == "ai", f"S5: host lastWalk.origin is not 'ai': {hw}"
        lr = speed_of(host)["lastRead"]
        assert lr == {"which": "alien", "value": 33, "seat": -1}, (
            f"S5: host lastRead == {lr}, expected the FLOOR (max(12,33)=33), seat -1 (unowned)")

        gl = event_state(client)["ghostLast"]
        assert gl["kind"] == "walk_step" and gl["seat"] == -1, (
            f"S5: unexpected CLIENT ghostLast: {gl}")
        assert gl["ms"] == gl["frames"] * 33, (
            f"S5: client ghostLast ms != frames*33: {gl}. CONFIRMED same traced root cause "
            f"as S1's client floor assertion (CoopSpeed::coopSeatConnected() permanently "
            f"false for the client's own seat on its own process, connectionTCP.cpp ~8754): "
            f"CoopGhost::onEvApplied()'s paceMsFor() -> CoopSpeed::speedFor() falls through "
            f"to floor() for this UNOWNED alien unit, and the CLIENT's own floor() sees only "
            f"the HOST's alien dial (12) - measured ms == frames*12, not frames*33.")

        hd = event_state(host).get("desyncSeen")
        cd = event_state(client).get("desyncSeen")
        assert hd is False and cd is False, (
            f"S5: desyncSeen is not False on both machines: host={hd} client={cd}")
        assert_hash_clean(host, client, full=True, what="S5 after the host's first AI walk")
        print(f"[S5] unowned alien unit paced at the floor (33): host lastRead={lr} "
              f"client ghostLast={gl}; desyncSeen False on both, hash clean")
        print("PASS S5")

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


# ===================== BOOT C: traditional baton (S9) =====================


def run_boot_c(activate_text, deactivate_text):
    port = "48482"
    host_dir = make_user_dir("seat_pacing_c_host", options={"battleXcomSpeed": 20})
    client_dir = make_user_dir("seat_pacing_c_client", options={"battleXcomSpeed": 25})
    host = GameClient("host", 49784, host_dir)
    client = GameClient("client", 49785, client_dir)
    seated = {}
    try:
        tb_bring_up_lobby(host, client, port)
        session.drive_to_battlescape(host, client, seated, seat_count=2,
                                     pre_ok=pre_ok_traditional)

        assert event_state(host).get("turnMode") == "traditional", (
            f"boot C fixture: host turnMode is not 'traditional': "
            f"{event_state(host).get('turnMode')}")
        assert event_state(client).get("turnMode") == "traditional", (
            f"boot C fixture: client turnMode is not 'traditional': "
            f"{event_state(client).get('turnMode')}")
        assert event_state(host).get("coopActiveSeat") == 0, (
            f"S9 premise: coopActiveSeat is not 0 at entry on the host: "
            f"{event_state(host).get('coopActiveSeat')}")
        assert event_state(client).get("coopActiveSeat") == 0, (
            f"S9 premise: coopActiveSeat is not 0 at entry on the client: "
            f"{event_state(client).get('coopActiveSeat')}")

        # ----- off-baton (seat 1/client) Ctrl-S: ignored -----
        xcom_c0 = speed_of(client)["local"]["xcom"]
        qmi_c0 = speed_of(client)["quickModeIgnored"]
        ctrl_s(client)
        assert speed_of(client)["local"]["xcom"] == xcom_c0, (
            f"S9: off-baton client local.xcom moved: {xcom_c0} -> "
            f"{speed_of(client)['local']['xcom']}")
        assert speed_of(client)["quickModeIgnored"] == qmi_c0 + 1, (
            f"S9: off-baton client quickModeIgnored did not rise by 1: {qmi_c0} -> "
            f"{speed_of(client)['quickModeIgnored']}")

        # ----- on-baton (seat 0/host) Ctrl-S: allowed, both directions -----
        xcom_h0 = speed_of(host)["local"]["xcom"]
        assert xcom_h0 == 20, f"S9 premise: expected the host's xcom dial to start at 20, got {xcom_h0}"
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, 1, timeout=15)
        assert speed_of(host)["local"]["xcom"] == 1, "S9: on-baton host local.xcom != 1"
        ctrl_s(host)
        wait_seat_dial(host, client, 0, 0, xcom_h0, timeout=15)
        assert speed_of(host)["local"]["xcom"] == xcom_h0, (
            f"S9: on-baton host local.xcom did not restore to {xcom_h0}")
        print(f"[S9 seat0] off-baton client Ctrl-S ignored (xcom unchanged {xcom_c0}, "
              f"quickModeIgnored {qmi_c0}->{speed_of(client)['quickModeIgnored']}); "
              f"on-baton host Ctrl-S allowed (1x <-> {xcom_h0})")

        # ----- pass the baton (host's END TURN, D-23) -----
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def baton_at_seat_1():
            return True if (event_state(host).get("coopActiveSeat") == 1
                             and event_state(client).get("coopActiveSeat") == 1) else None
        host.wait_for("S9: the host's END TURN hands the baton to seat 1 on both machines",
                     baton_at_seat_1, timeout=15)

        # ----- now off-baton (seat 0/host) Ctrl-S: ignored -----
        xcom_h1 = speed_of(host)["local"]["xcom"]
        qmi_h1 = speed_of(host)["quickModeIgnored"]
        ctrl_s(host)
        assert speed_of(host)["local"]["xcom"] == xcom_h1, (
            f"S9: off-baton host local.xcom moved after the pass: {xcom_h1} -> "
            f"{speed_of(host)['local']['xcom']}")
        assert speed_of(host)["quickModeIgnored"] == qmi_h1 + 1, (
            f"S9: off-baton host quickModeIgnored did not rise by 1 after the pass: {qmi_h1} -> "
            f"{speed_of(host)['quickModeIgnored']}")

        # ----- now on-baton (seat 1/client) Ctrl-S: allowed, both directions -----
        xcom_c1 = speed_of(client)["local"]["xcom"]
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, 1, timeout=15)
        assert speed_of(client)["local"]["xcom"] == 1, "S9: on-baton client local.xcom != 1"
        ctrl_s(client)
        wait_seat_dial(host, client, 1, 0, xcom_c1, timeout=15)
        assert speed_of(client)["local"]["xcom"] == xcom_c1, (
            f"S9: on-baton client local.xcom did not restore to {xcom_c1}")
        print(f"[S9 seat1] off-baton host Ctrl-S ignored (xcom unchanged {xcom_h1}, "
              f"quickModeIgnored {qmi_h1}->{speed_of(host)['quickModeIgnored']}); "
              f"on-baton client Ctrl-S allowed (1x <-> {xcom_c1})")
        print("PASS S9")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    t0 = time.time()
    activate_text, deactivate_text = run_boot_d()
    run_boot_a(activate_text, deactivate_text)
    run_boot_b(activate_text, deactivate_text)
    run_boot_c(activate_text, deactivate_text)
    print(f"\nALL SPEC 17 test_rw_seat_pacing TESTS PASSED ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_seat_pacing", e.tracking, str(e))
        print(f"\ntest_rw_seat_pacing: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_rw_seat_pacing: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_rw_seat_pacing: FAIL\nTimeoutError: {e}")
        sys.exit(2)
