"""SP battle smoke - the mandatory single-player proof for any packet that
touches a file under src/Battlescape/** or src/Savegame/**.

AUTHORED BY SPEC 1 (P11-ACCEPT) per BLOCK SP-SMOKE's SPEC-1 carve-out
(WAVE1-RUNBOOK.md 4b): FX-1 (SPEC 2) was to write this file, but P11-ACCEPT
runs first and needs the proof (W1-P11 touched src/Battlescape/UnitWalkBState.cpp),
so it lands here with the four assertions and at the path the block fixes.
SPEC 2 finds it already present and only re-runs it - nobody re-invents it in a
scratchpad (that mistake cost this wave two SP-smoke runners).

The four assertions, verbatim from BLOCK SP-SMOKE:
  1. one instance, NO coop, newbattle_ok -> close_briefing;
  2. the state stack after close_briefing is
     ['BattlescapeState','NextTurnState','InventoryState'] - the SP equip
     screen is STILL pushed (this is what keeps W1-P4's freeze provably
     coop-only). The stack probe is get_palettes's states[].state, which
     reports typeid(*state).name(); MSVC renders that as
     'class OpenXcom::BattlescapeState', so it is matched by SUBSTRING.
  3. battle_state.strTarget and strCraftOrBase are non-empty (vanilla minted them);
  4. a real ground click through inject_input kind=click MOVES a unit
     (position changes, TU drops), and event_state.coopWalkArmEntered == 0,
     coopWalkIntentsSent == 0, lastWalk == None.

HEADLESS, single instance, no client, no coop. Exit 0 = PASS, 2 = FAIL (the
harness exit-code convention; there is no fixture-exhaustion path here).
"""
import os
import sys
import time

import harness
import session

FACTION_PLAYER = 0        # BattleUnit::UnitFaction
SDLK_HOME = 278           # Options::keyBattleCenterUnit default
SDLK_TAB = 9              # Options::keyBattleNextUnit default

EXPECTED_STACK = ["BattlescapeState", "NextTurnState", "InventoryState"]

# 8-neighbourhood, same z; a single adjacent step is ~4 TU, trivially affordable
# on a fresh SP squad (TU ~50-60).
NEIGHBORS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
             if not (dx == 0 and dy == 0)]


def palette_stack(gc):
    """The state stack, bottom-to-top (last element is the TOP state), as the
    typeid strings get_palettes reports. dismiss_battle_start_overlays proves
    the ordering: it waits on st[-1] being BattlescapeState (the top)."""
    return [e["state"] for e in gc.ok({"cmd": "get_palettes"})["states"]]


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def estate(gc):
    return gc.cmd({"cmd": "event_state"})


def units_of(gc):
    return bstate(gc).get("units", [])


def unit_by_id(gc, uid):
    for u in units_of(gc):
        if u["id"] == uid:
            return u
    return None


def pos_of(u):
    return (u["x"], u["y"], u["z"])


def select_unit(gc, uid, tries=24):
    for _ in range(tries):
        if bstate(gc).get("selectedId") == uid:
            return True
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
    return bstate(gc).get("selectedId") == uid


def sp_ground_click_walks(gc):
    """PICK a player unit, center on it, click an adjacent open tile, and prove
    the unit MOVED. Tries every player unit and its open neighbours so a single
    blocked squad member is not read as an atom result. Returns (uid, before, after)
    on success, or None if no unit could be walked (which is a FAIL here - a fresh
    SP squad on open ground always has a step available)."""
    st = bstate(gc)
    all_units = st.get("units", [])
    occupied = {pos_of(u) for u in all_units if not u.get("isOut")}
    candidates = [u for u in all_units
                  if u.get("faction") == FACTION_PLAYER
                  and not u.get("isOut") and u.get("tu", 0) >= 8]
    for cu in candidates:
        uid = cu["id"]
        if not select_unit(gc, uid):
            continue
        live = unit_by_id(gc, uid)
        if live is None:
            continue
        x, y, z = pos_of(live)
        for dx, dy in NEIGHBORS:
            tile = (x + dx, y + dy, z)
            if tile in occupied:
                continue
            gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
            time.sleep(0.2)
            pr = gc.cmd({"cmd": "map_tile_click_pos",
                         "x": tile[0], "y": tile[1], "z": tile[2]})
            if not (pr.get("ok") and pr.get("verified")):
                continue
            before = unit_by_id(gc, uid)
            before_pos, before_tu = pos_of(before), before["tu"]
            gc.ok({"cmd": "inject_input", "kind": "click",
                   "x": pr["winX"], "y": pr["winY"], "button": "left"})
            # Poll for the walk to complete: position changes and TU drops.
            deadline = time.time() + 12
            while time.time() < deadline:
                after = unit_by_id(gc, uid)
                if after and pos_of(after) != before_pos and after["tu"] < before_tu:
                    return uid, (before_pos, before_tu), (pos_of(after), after["tu"])
                time.sleep(0.3)
    return None


def main():
    t0 = time.time()
    user = harness.make_user_dir("sp_smoke")
    port = int(os.environ.get("OXC_TEST_PORT", "0")) or 47990
    host = harness.GameClient("sp_smoke_host", port, user)
    host.spawn()
    host.connect()
    try:
        # (1) one instance, NO coop: open the New Battle screen and start it,
        # WITHOUT newbattle_coop (the step that turns it into a coop session).
        host.ok({"cmd": "open_new_battle"})
        host.wait_for("NewBattleState",
                      lambda: session.has_state(host, "NewBattleState"), timeout=60)
        host.ok({"cmd": "newbattle_ok"})
        host.wait_for(
            "SP battle generated",
            lambda: (session.has_state(host, "BriefingState")
                     or session.has_state(host, "InventoryState")
                     or session.has_state(host, "BattlescapeState")) or None,
            timeout=180, interval=0.5)
        if session.has_state(host, "BriefingState"):
            host.ok({"cmd": "close_briefing"})
        # Let the post-briefing stack settle.
        host.wait_for(
            "equip screen up after briefing",
            lambda: session.has_state(host, "InventoryState") or None,
            timeout=30, interval=0.3)

        # This must be a PLAIN SP battle, not a coop session.
        assert bstate(host).get("coopSession") in (False, None, 0), (
            "SP-SMOKE (1): coopSession is truthy - this is not a plain SP battle "
            f"(coopSession={bstate(host).get('coopSession')!r})")
        print("PASS (1): one instance, no coop, newbattle_ok -> close_briefing")

        # (2) the SP equip screen is STILL pushed.
        stack = palette_stack(host)
        classnames = [s.split("::")[-1] for s in stack]
        assert len(stack) == len(EXPECTED_STACK) and all(
            exp in got for exp, got in zip(EXPECTED_STACK, classnames)), (
            "SP-SMOKE (2): the post-briefing SP stack is not "
            f"{EXPECTED_STACK} - got {stack!r}. If InventoryState is absent, "
            "W1-P4's freeze has leaked into SP; if there are extra states, the "
            "SP flow changed and the assertion must be re-pinned to the new "
            "measured stack (not relaxed).")
        print(f"PASS (2): stack after close_briefing = {classnames} "
              "(SP equip screen still pushed)")

        # (3) vanilla minted the two BriefingState labels.
        st = bstate(host)
        target, cob = st.get("strTarget", ""), st.get("strCraftOrBase", "")
        assert target and cob, (
            "SP-SMOKE (3): a BriefingState label is empty "
            f"(strTarget={target!r}, strCraftOrBase={cob!r}) - vanilla did not "
            "mint them")
        print(f"PASS (3): strTarget={target!r} strCraftOrBase={cob!r}")

        # Reach BattlescapeState (dismiss the equip screen + the Turn-1 overlay).
        session.dismiss_battle_start_overlays(host)
        assert session.has_state(host, "BattlescapeState"), (
            "SP-SMOKE: could not reach BattlescapeState to test the ground click, "
            f"stack={palette_stack(host)!r}")

        # (4) a real ground click WALKS a unit, and NO coop counter moved.
        arm0 = estate(host).get("coopWalkArmEntered", 0)
        sent0 = estate(host).get("coopWalkIntentsSent", 0)
        moved = sp_ground_click_walks(host)
        assert moved is not None, (
            "SP-SMOKE (4): no player unit's ground click produced a walk on open "
            "ground - the three UnitWalkBState hooks or the split gate are NOT inert "
            "in SP, OR the click recipe failed")
        uid, before, after = moved
        es = estate(host)
        assert es.get("coopWalkArmEntered", 0) == 0, (
            "SP-SMOKE (4): coopWalkArmEntered moved in SP "
            f"({arm0} -> {es.get('coopWalkArmEntered')}) - the coop walk arm is NOT "
            "guarded off outside co-op")
        assert es.get("coopWalkIntentsSent", 0) == 0, (
            "SP-SMOKE (4): coopWalkIntentsSent moved in SP "
            f"({sent0} -> {es.get('coopWalkIntentsSent')})")
        assert es.get("lastWalk") in (None, {}, 0), (
            f"SP-SMOKE (4): lastWalk is set in SP ({es.get('lastWalk')!r}) - a coop "
            "walk ev was recorded for a single-player walk")
        print(f"PASS (4): unit {uid} walked {before[0]}->{after[0]} "
              f"TU {before[1]}->{after[1]}; coopWalkArmEntered=0 "
              "coopWalkIntentsSent=0 lastWalk=None")
    finally:
        host.shutdown()
    print(f"\nsp_smoke: PASS ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, TimeoutError) as e:
        print(f"\nsp_smoke: FAIL\n{type(e).__name__}: {e}")
        import traceback
        print("")
        print("--- traceback (classification aid) ---")
        traceback.print_exc()
        sys.exit(2)
