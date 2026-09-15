"""SPEC 12 (W1-P13d) - test_rw_level_change_gate.py: REV E.48 SS.E.3 as
amended by REV E.58 E58.2 (D84) and REV E.61 (D88 = (b)) - WV-D58: the two
caption-less unit up/down buttons (`BattlescapeState::btnUnitUpClick` /
`btnUnitDownClick`) no longer bypass every coop gate. CLIENT = REFUSAL via
`CoopBattleUi::refuseControl(Control::LevelChange, ...)`, the FIRST statement
of each button (`connectionTCP.cpp:8007`, Term 1 AUTHORITY, `!hostSim`) -
armor-independent, refused whatever the selected unit is wearing (F269).
HOST = the same walk-emit path via `coopInterceptWalkConfirm`, immediately
before `moveUpDown`'s own `statePushBack(new UnitWalkBState(...))`
(`BattlescapeGame.cpp:2311`) - so a HOST-origin level change streams to the
client exactly like any other walk.

FIXTURE (REV E.61 E61.1/E61.2, D88 = (b), the supervisor's SECOND amendment;
D88's first version put the flying suit on a SEAT-1 soldier for BOTH legs and
was REFUTED BY TRACE - the host cannot command a seat-1 unit at all,
`refuseControl` Term 2 OWNERSHIP refuses it with `STR_COOP_DENY_NOT_YOUR_UNIT`
("Not one of your soldiers"), regardless of WV-D58). TWO flying suits
(`STR_FLYING_SUIT_UC`, F235 - the armors.rul `type:` key, not the store item)
are seeded in ONE `pre_ok` window on the Lightning roof fixture
(`repro_ghost_stepper.bring_up_roof_battle`, additively extended here with a
`pre_ok=None` keyword - F278, the two existing callers left byte-unchanged):
  (i)  the FIRST seat-1 soldier - the CLIENT leg's unit, the exact soldier
       REV E.48 SS.E.3 names;
  (ii) the band `max(seatIds)+1 .. max(seatIds)+11` - only soldiers ABOARD
       the craft become battle units (F271), so this band is seeded BLIND
       and the HOST leg's unit is picked from the battle roster afterward:
       the FIRST live unit with `armor == "STR_FLYING_SUIT_UC" and coop ==
       0` (a roster with none is a RED naming the step, SS.A.8 - never a
       skip).
`bring_up_roof_battle` does not expose its own internal `seated` dict to the
`pre_ok` window it now forwards (only the ONE additive keyword was added,
F278) - the seat-1 id list is read back independently via `get_soldiers`,
the SAME live SavedGame state `session.py`'s own `seated["soldierIds"]` is
itself just a cached copy of (R3-P1's `NewBattleState::harnessSeatOneSoldier`
stamps `Soldier::setCoop()` on the real base roster before `pre_ok` fires).

Both units are staged on the SAME lane row, two tiles apart (S2: never onto
each other's tile) - the exact door-relative tiles orch43d measured a
successful z+1 level change on BEFORE this unit existed (NC2/F266 for the
lane start, CAPTURE 2/F270 for lane start + 2), which is what makes the
CLIENT leg's `z`-unchanged assertion NON-vacuous: that unit COULD have
flown.

`click_widget`'s `match` only matches TextButton captions; the up/down
buttons are caption-less `BattlescapeButton`s (`BattlescapeState.cpp:155-156`)
and are pressed by `nth` among the VISIBLE INTERACTIVE surfaces in
`list_widgets` order (F267.3/F276) - resolved at RUN TIME per machine (never
hard-coded) and then ASSERTED to equal the pinned values (2 UP / 3 DOWN,
measured on this build) - a different resolution is a RED that prints the
whole filtered list, never a silent adaptation.

Cites WV-D58, REV E.48 SS.E.3, REV E.58 E58.2 (D84), REV E.61 E61.1-E61.2
(D88 = (b)), F235, F267, F269, F270, F271, F274, F276, F278, F279.

Run:  python tools/coop_test/test_rw_level_change_gate.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: F401 (parity w/ sibling repros)
import session
from session import battle_state, event_state, assert_hash_clean, pin_ai_neutral, action_events
import repro_ghost_stepper as gs

ARMOR = "STR_FLYING_SUIT_UC"
SEAT_COUNT = 2
COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
REFUSAL_TEXT = "Only the host can move a unit between levels"


def resolve_up_down_nth(gc):
    """F267.3/F276's RULE: keep `interactive and visible` entries, IN
    list_widgets ORDER (never `idx`, which counts non-visible/non-interactive
    surfaces too); among those keep the 32x16 entries; the smallest `x`
    column's two entries are the pair, smaller `y` = UP, larger `y` = DOWN.
    Returns (up_nth, down_nth) and ASSERTS the resolution matches the pinned
    values (2, 3) - a mismatch prints the whole filtered list and fails,
    never a silent adaptation."""
    lw = gc.cmd({"cmd": "list_widgets"})
    assert lw.get("ok"), f"{gc.name}: list_widgets failed: {lw}"
    widgets = lw.get("widgets", [])
    filtered = [w for w in widgets if w.get("interactive") and w.get("visible")]
    sized = [(i, w) for i, w in enumerate(filtered) if w.get("w") == 32 and w.get("h") == 16]
    assert len(sized) >= 2, (
        f"{gc.name}: fewer than two 32x16 interactive+visible surfaces found - "
        f"cannot resolve the up/down pair. filtered list: {filtered}")
    min_x = min(w["x"] for _, w in sized)
    column = sorted([(i, w) for i, w in sized if w["x"] == min_x], key=lambda iw: iw[1]["y"])
    assert len(column) >= 2, (
        f"{gc.name}: fewer than two 32x16 surfaces in the smallest-x column - "
        f"cannot resolve UP/DOWN. column: {column}, filtered list: {filtered}")
    up_nth, down_nth = column[0][0], column[1][0]
    assert up_nth == 2 and down_nth == 3, (
        f"{gc.name}: click_widget nth resolution did NOT match the pinned "
        f"values (UP=2, DOWN=3, F267/F276) - got UP={up_nth} DOWN={down_nth}. "
        f"filtered interactive+visible list: {filtered}")
    return up_nth, down_nth


def unit_snapshot(gc, uid):
    u = next((uu for uu in battle_state(gc)["units"] if uu["id"] == uid), None)
    assert u is not None, f"{gc.name}: unit {uid} not found in battle_state"
    return (u["x"], u["y"], u["z"], u["tu"])


def run():
    seed_state = {}

    def seed_two_suits(h):
        """REV E.61 E61.1: seeds STR_FLYING_SUIT_UC on (i) the first seat-1
        soldier (the CLIENT leg's unit) and (ii) the band
        max(seatIds)+1..max(seatIds)+11 (F271: only soldiers ABOARD the craft
        become battle units, so this band is seeded blind). Runs in the
        `pre_ok` window - AFTER `newbattle_seat_soldier` has stamped
        `Soldier::setCoop()` on the real base roster, BEFORE `newbattle_ok`
        snapshots it into the battle - so `get_soldiers` already reports the
        live seat tags (F272's ordering, read a different way since
        `bring_up_roof_battle` does not expose its own `seated` dict, F278)."""
        gs_resp = h.cmd({"cmd": "get_soldiers"})
        assert gs_resp.get("ok"), f"get_soldiers failed: {gs_resp}"
        seat1_ids = sorted(
            s["id"] for b in gs_resp.get("bases", []) for s in b.get("soldiers", [])
            if s.get("coop") == COOP_SEAT_1)
        assert seat1_ids, (
            f"FIXTURE PREMISE BROKE: no seat-1 soldier stamped before the "
            f"pre_ok window: {gs_resp}")
        seed_state["client_soldier_id"] = seat1_ids[0]

        r = h.cmd({"cmd": "seed_soldier_armor", "soldier_id": seat1_ids[0], "armor": ARMOR})
        assert r.get("ok") and r.get("armor") == ARMOR, (
            f"seed_soldier_armor failed for the seat-1 soldier {seat1_ids[0]}: {r}")

        band_lo = max(seat1_ids) + 1
        band_hi = max(seat1_ids) + 11
        for sid in range(band_lo, band_hi + 1):
            rr = h.cmd({"cmd": "seed_soldier_armor", "soldier_id": sid, "armor": ARMOR})
            # F273: a miss is a NAMED error, not silent - printed, never
            # asserted (not every id in the band need exist).
            if not rr.get("ok"):
                print(f"[seed_two_suits] band id {sid}: {rr.get('error')}")
        print(f"[seed_two_suits] seeded seat-1 soldier {seat1_ids[0]} and band "
              f"{band_lo}..{band_hi} with {ARMOR}")

    host, client, client_ids, host_ids, door = gs.bring_up_roof_battle(
        SEAT_COUNT, "levelgate", pre_ok=seed_two_suits)
    try:
        pinned = pin_ai_neutral(host, client, tag="level_change_gate")
        assert len(pinned) > 0, (
            f"pin_ai_neutral pinned ZERO NONE-seat non-player units on a "
            f"CLASSIC roof boot - the premise is unexercised (M9a-3)")

        assert "client_soldier_id" in seed_state, "seed_two_suits never ran"
        client_soldier_id = seed_state["client_soldier_id"]

        hs0 = battle_state(host)
        client_leg_unit = next(
            (u for u in hs0["units"] if u.get("soldierId") == client_soldier_id), None)
        assert client_leg_unit is not None, (
            f"FIXTURE PREMISE BROKE: no battle unit with soldierId "
            f"{client_soldier_id} (the seeded seat-1 soldier) - roster: "
            f"{[(u['id'], u.get('soldierId'), u.get('coop')) for u in hs0['units']]}")
        client_leg_id = client_leg_unit["id"]
        assert client_leg_unit.get("coop") == COOP_SEAT_1, (
            f"CLIENT leg unit {client_leg_id} is not coop==1: {client_leg_unit}")
        assert client_leg_unit.get("armor") == ARMOR, (
            f"CLIENT leg unit {client_leg_id} armor is not {ARMOR!r}: "
            f"{client_leg_unit.get('armor')!r}")

        host_leg_unit = next(
            (u for u in hs0["units"]
             if u.get("armor") == ARMOR and u.get("coop") == COOP_SEAT_0
             and not u.get("isOut")), None)
        assert host_leg_unit is not None, (
            f"RED (SS.A.8): no live unit in the battle roster has armor=={ARMOR!r} "
            f"and coop==0 - roster: "
            f"{[(u['id'], u.get('soldierId'), u.get('coop'), u.get('armor')) for u in hs0['units']]}")
        host_leg_id = host_leg_unit["id"]

        for gc in (host, client):
            us = {u["id"]: u for u in battle_state(gc)["units"]}
            assert us[client_leg_id]["armor"] == ARMOR, (
                f"{gc.name}: CLIENT leg unit {client_leg_id} armor is not "
                f"{ARMOR!r}: {us[client_leg_id].get('armor')!r}")
            assert us[host_leg_id]["armor"] == ARMOR, (
                f"{gc.name}: HOST leg unit {host_leg_id} armor is not {ARMOR!r}: "
                f"{us[host_leg_id].get('armor')!r}")

        # ---- staging: the two measured roof tiles, two apart on the SAME
        # lane row (S2: never teleport a unit onto its own tile or the
        # other's) ----
        client_tile = gs.teleport_to_lane(host, client, client_leg_id, door)
        host_tile = (door["x"] + gs.LANE_DX_START + 2, door["y"] + gs.LANE_DY, door["z"] + gs.ROOF_DZ)
        session.place_deterministic(
            host, client,
            [{"lever": "battle_teleport_unit", "unit": host_leg_id,
              "x": host_tile[0], "y": host_tile[1], "z": host_tile[2], "dir": 2}],
            what="level_change_gate HOST leg unit lane start + 2")

        hu = {u["id"]: u for u in battle_state(host)["units"]}
        print(f"[staging] CLIENT leg unit {client_leg_id} "
              f"(soldierId={hu[client_leg_id].get('soldierId')} coop="
              f"{hu[client_leg_id].get('coop')} armor={hu[client_leg_id].get('armor')}) "
              f"tile={client_tile} pos="
              f"{(hu[client_leg_id]['x'], hu[client_leg_id]['y'], hu[client_leg_id]['z'])} "
              f"tu={hu[client_leg_id]['tu']}")
        print(f"[staging] HOST leg unit {host_leg_id} "
              f"(soldierId={hu[host_leg_id].get('soldierId')} coop="
              f"{hu[host_leg_id].get('coop')} armor={hu[host_leg_id].get('armor')}) "
              f"tile={host_tile} pos="
              f"{(hu[host_leg_id]['x'], hu[host_leg_id]['y'], hu[host_leg_id]['z'])} "
              f"tu={hu[host_leg_id]['tu']}")

        # ================= CLIENT LEG =================
        r = client.cmd({"cmd": "battle_action", "action": "select", "unit": client_leg_id})
        assert r.get("ok"), f"CLIENT leg: select failed: {r}"
        assert battle_state(client).get("selectedId") == client_leg_id, (
            f"CLIENT leg: selectedId is not {client_leg_id}: "
            f"{battle_state(client).get('selectedId')}")

        before_client = unit_snapshot(client, client_leg_id)
        before_host_view = unit_snapshot(host, client_leg_id)
        before_lw_h = event_state(host).get("lastWalk")
        before_lw_c = event_state(client).get("lastWalk")
        before_desync_h = event_state(host).get("desyncSeen")
        before_desync_c = event_state(client).get("desyncSeen")
        before_banner = battle_state(client).get("coopWaitText")
        print(f"[CLIENT leg] BEFORE: client={before_client} host_view={before_host_view} "
              f"lastWalk host={before_lw_h} client={before_lw_c} "
              f"desyncSeen host={before_desync_h} client={before_desync_c} "
              f"coopWaitText={before_banner!r}")

        up_nth_c, _down_nth_c = resolve_up_down_nth(client)
        press = client.cmd({"cmd": "click_widget", "nth": up_nth_c})
        assert press.get("ok"), f"CLIENT leg: click_widget UP (nth={up_nth_c}) failed: {press}"

        after_banner = battle_state(client).get("coopWaitText")
        assert after_banner != before_banner and after_banner == REFUSAL_TEXT, (
            f"CLIENT leg: coopWaitText did not change to the exact "
            f"{REFUSAL_TEXT!r} - before={before_banner!r} after={after_banner!r}")
        print(f"[CLIENT leg] banner BEFORE={before_banner!r} -> AFTER={after_banner!r} "
              "(the refused up press)")

        after_client = unit_snapshot(client, client_leg_id)
        after_host_view = unit_snapshot(host, client_leg_id)
        assert after_client == before_client, (
            f"CLIENT leg: the refused press MOVED the unit on the client - "
            f"before={before_client} after={after_client}")
        assert after_host_view == before_host_view, (
            f"CLIENT leg: the refused press MOVED the unit on the host's view - "
            f"before={before_host_view} after={after_host_view}")
        after_lw_h = event_state(host).get("lastWalk")
        after_lw_c = event_state(client).get("lastWalk")
        assert after_lw_h == before_lw_h, (
            f"CLIENT leg: host event_state.lastWalk CHANGED: {before_lw_h} -> {after_lw_h}")
        assert after_lw_c == before_lw_c, (
            f"CLIENT leg: client event_state.lastWalk CHANGED: {before_lw_c} -> {after_lw_c}")
        after_desync_h = event_state(host).get("desyncSeen")
        after_desync_c = event_state(client).get("desyncSeen")
        assert after_desync_h is False and after_desync_c is False, (
            f"CLIENT leg: desyncSeen is not False on both machines: "
            f"host={after_desync_h} client={after_desync_c}")
        assert_hash_clean(host, client, full=True,
                          what="CLIENT leg after the refused client up press")
        print(f"[CLIENT leg] PASS: mints nothing - position/TU unchanged on both "
              f"machines (z stayed {before_client[2]}), lastWalk unchanged, "
              "desyncSeen False, all buckets EQUAL")

        # ================= HOST LEG =================
        r = host.cmd({"cmd": "battle_action", "action": "select", "unit": host_leg_id})
        assert r.get("ok"), f"HOST leg: select failed: {r}"
        assert battle_state(host).get("selectedId") == host_leg_id, (
            f"HOST leg: selectedId is not {host_leg_id}: "
            f"{battle_state(host).get('selectedId')}")

        before_host = unit_snapshot(host, host_leg_id)
        before_client_view = unit_snapshot(client, host_leg_id)
        print(f"[HOST leg] BEFORE: host={before_host} client_view={before_client_view}")

        up_nth_h, down_nth_h = resolve_up_down_nth(host)
        press_up = host.cmd({"cmd": "click_widget", "nth": up_nth_h})
        assert press_up.get("ok"), f"HOST leg: click_widget UP (nth={up_nth_h}) failed: {press_up}"

        session.wait_host_idle(host, client, timeout=30)
        session.settle_reveal(host, client)

        after_up_host = unit_snapshot(host, host_leg_id)
        after_up_client = unit_snapshot(client, host_leg_id)
        assert after_up_host[2] == before_host[2] + 1, (
            f"HOST leg UP: host z did not go +1 - before={before_host} "
            f"after={after_up_host}")
        assert after_up_client[:3] == after_up_host[:3], (
            f"HOST leg UP: the client's copy does not agree on (x,y,z) - "
            f"host={after_up_host[:3]} client={after_up_client[:3]}")

        lw_h = event_state(host).get("lastWalk")
        lw_c = event_state(client).get("lastWalk")
        assert lw_h, f"HOST leg UP: host lastWalk is null: {lw_h}"
        assert lw_c, f"HOST leg UP: client lastWalk is null: {lw_c}"
        assert lw_h.get("actionId") == lw_c.get("actionId"), (
            f"HOST leg UP: lastWalk actionId differs - host={lw_h.get('actionId')} "
            f"client={lw_c.get('actionId')}")
        up_action_id = lw_h.get("actionId")
        step_evs = action_events(client, up_action_id)
        walk_step_evs = [e for e in step_evs if e.get("kind") == "walk_step"]
        assert walk_step_evs, (
            f"HOST leg UP: no walk_step ev in the client's event_log for "
            f"actionId {up_action_id}: {[e.get('kind') for e in step_evs]}")
        without_h = [e for e in walk_step_evs if not e.get("h")]
        assert not without_h, f"HOST leg UP: walk_step ev(s) without h: {without_h}"
        print(f"[HOST leg UP] lastWalk host={lw_h} client={lw_c}")
        print(f"[HOST leg UP] {len(walk_step_evs)} walk_step ev(s) for actionId "
              f"{up_action_id}, ALL carry h")

        assert_hash_clean(host, client, full=True, what="HOST leg after the up press")
        print(f"[HOST leg UP] PASS: z {before_host[2]} -> {after_up_host[2]}, "
              "client agrees, all buckets EQUAL")

        # ---- HOST DOWN ----
        press_down = host.cmd({"cmd": "click_widget", "nth": down_nth_h})
        assert press_down.get("ok"), (
            f"HOST leg: click_widget DOWN (nth={down_nth_h}) failed: {press_down}")

        session.wait_host_idle(host, client, timeout=30)
        session.settle_reveal(host, client)

        after_down_host = unit_snapshot(host, host_leg_id)
        after_down_client = unit_snapshot(client, host_leg_id)
        assert after_down_host[2] == before_host[2], (
            f"HOST leg DOWN: host z did not return to {before_host[2]}: "
            f"{after_down_host}")
        assert after_down_client[2] == before_host[2], (
            f"HOST leg DOWN: client z did not return to {before_host[2]}: "
            f"{after_down_client}")
        assert_hash_clean(host, client, full=True, what="HOST leg after the down press")
        print(f"[HOST leg DOWN] PASS: z {after_up_host[2]} -> {after_down_host[2]} "
              f"(back to {before_host[2]}), all buckets EQUAL")

        print("PASS: test_rw_level_change_gate")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run()
    print("ALL SPEC 12 test_rw_level_change_gate TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_rw_level_change_gate", e.tracking, str(e))
        print(f"\ntest_rw_level_change_gate: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_rw_level_change_gate: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_rw_level_change_gate: FAIL\nTimeoutError: {e}")
        sys.exit(2)
