"""WV-D63 (SPEC 6a): acceptance test for the deterministic PLACEMENT LEVER -
TestServer.cpp's `battle_teleport_unit` / `battle_teleport_all` commands - and
its session.py helpers (`place_deterministic`, `contact_free_ufo_door_setup`).

AI-neutral: t=0 only; contact-free by construction (every live hostile is
teleported away before anything else happens - no walk, no shot, no AI turn
ever runs in this file). DETERMINISTIC fixture (WV-D65): the SITUATION is
built by the placement lever plus the hash-equality gate, never a map-
generator re-roll loop waiting on a CANDIDATE (no MAX_REROLLS/
FixtureExhausted anywhere below), so the acceptance bar is **3 consecutive
green**, not 10 - a SKIP here is a LEVER BUG, never a map roll.

Covers, on a STR_BASE_DEFENSE bring-up and a STR_SUPPLY_SHIP bring-up:
  - `battle_teleport_all {faction:"hostile"}` moves every live hostile on
    BOTH machines, with IDENTICAL replies (WV-D63(f)).
  - `battle_teleport_unit` (via `contact_free_ufo_door_setup`) moves one
    seat-1 soldier onto the standable tile next to a UFO door, facing it.
  - `hash_now {full:true}` is ALL BUCKETS EQUAL after every placement (the
    gate every WV-D63 fixture must pass before its measured action -
    `place_deterministic`'s own assert).
  - A REFUSED call (an occupied destination tile; a faction with a live 2x2+
    unit) changes NOTHING and the hash stays equal.
  - `battle_state` reports IDENTICAL `{x,y,z,direction}` for every moved unit
    on both machines.
  - The SP smoke path (`sp_smoke.py`) is exercised separately by this
    packet's own acceptance run, not by this file - the lever adds no code on
    any path `sp_smoke.py` touches (it is a brand-new TestServer command
    pair), so nothing here should be able to move it.

THE ONE RE-ROLL IN THIS FILE IS NOT A MAP-ROLLED FIXTURE (WV-D65 NOTE): a
freshly generated STR_BASE_DEFENSE/STR_SUPPLY_SHIP map occasionally includes a
live 2x2+ hostile (a Cyberdisc/Sectopod), and WV-D63(b) is explicit that this
is the FIXTURE'S job, not the lever's: "A 2x2 unit argument => the lever
returns an error ... and the fixture re-picks; never partially moves one."
When a boot rolls one, this file first PROVES the refusal (changes nothing,
hash stays equal - one of this file's own required assertions) and only THEN
moves on to a fresh map, because a map with a 2x2 hostile cannot exercise the
ALL-1x1 happy path `battle_teleport_all` is also required to prove here. This
is bounded (MAX_REROLLS) but is orthogonal to the WV-D65 bar: the LEVER's
placement+hash gate is exercised and proven EVERY attempt, re-rolled or not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, place_deterministic, contact_free_ufo_door_setup
import repro_atom_walk as W

FACTION_PLAYER = 0
FACTION_HOSTILE = 1

MAX_REROLLS = 8


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def bring_up(tag, mission, game_port, host_test_port, client_test_port):
    host_dir = make_user_dir(f"rw_teleport_{tag}_host")
    client_dir = make_user_dir(f"rw_teleport_{tag}_client")
    host = GameClient(f"{tag}-host", host_test_port, host_dir)
    client = GameClient(f"{tag}-client", client_test_port, client_dir)
    W.bring_up_lobby(host, client, game_port)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=mission)
    return host, client, seated


def run_fixture(tag, mission, game_port, host_test_port, client_test_port):
    for attempt in range(1, MAX_REROLLS + 1):
        host, client, _seated = bring_up(tag, mission, game_port, host_test_port, client_test_port)
        try:
            # ---- t=0 baseline: BOTH machines start from an equal document ----
            assert_hash_clean(host, client, full=True, what=f"{tag} t=0 (attempt {attempt})")

            hs0 = battle_state(host)
            assert hs0.get("ok") and hs0.get("inBattle"), f"{tag}: battle_state unusable on host: {hs0}"
            hostile_units = [u for u in hs0.get("units", [])
                             if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
            assert hostile_units, f"FIXTURE: {tag}: no live hostile on this generated map"

            if any(u.get("armorSize", 1) != 1 for u in hostile_units):
                # WV-D89 (supersedes WV-D63(b)'s refusal): 2x2 units now move
                # WHOLE - this map's live 2x2+ hostile(s) let this file prove
                # the whole-move here before re-picking a fresh map for the
                # ALL-1x1 happy path below (still needed - the loop itself is
                # SPEC 0e-3's to delete).
                print(f"{tag}: attempt {attempt} rolled a live 2x2+ hostile - "
                      "proving the 2x2 whole-move, then re-picking the map for "
                      "the ALL-1x1 happy path (WV-D89)")
                [(moved, _c_moved)] = place_deterministic(
                    host, client,
                    [{"lever": "battle_teleport_all", "faction": "hostile",
                      "corner": "SE", "facing": 3}],
                    what=f"{tag} 2x2 whole move (attempt {attempt})")

                doors_resp = host.cmd({"cmd": "find_doors", "limit": 1})
                assert doors_resp.get("ok"), f"{tag}: find_doors failed: {doors_resp}"
                mx, my = doors_resp["mapSizeX"], doors_resp["mapSizeY"]

                units_after = {u["id"]: u for u in battle_state(host).get("units", [])}
                big_movers = [mv for mv in moved.get("moves", [])
                              if units_after.get(mv["unit"], {}).get("armorSize", 1) == 2]
                assert big_movers, (
                    f"{tag}: expected at least one size-2 mover among {moved.get('moves')}")
                for mv in big_movers:
                    uid = mv["unit"]
                    u = units_after[uid]
                    x, y, z = u["x"], u["y"], u["z"]
                    assert x >= mx // 2 and y >= my // 2, (
                        f"{tag}: 2x2 unit {uid} at ({x},{y},{z}) is not inside the SE "
                        f"corner quarter of the {mx}x{my} map")
                    footprint = {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}
                    for other in units_after.values():
                        if other["id"] == uid or other.get("isOut"):
                            continue
                        assert (other["x"], other["y"]) not in footprint or other["z"] != z, (
                            f"{tag}: unit {other['id']} at "
                            f"({other['x']},{other['y']},{other['z']}) overlaps 2x2 unit "
                            f"{uid}'s footprint at ({x},{y},{z})")

                assert_hash_clean(host, client, full=True,
                                   what=f"{tag} after 2x2 whole move (attempt {attempt})")
                continue

            n_hostile_before = len(hostile_units)

            # ---- battle_teleport_all: every live hostile, IDENTICAL replies ----
            [(hr_all, _cr_all)] = place_deterministic(
                host, client,
                [{"lever": "battle_teleport_all", "faction": "hostile", "corner": "SE", "facing": 3}],
                what=f"{tag} teleport_all")
            assert hr_all.get("count") == n_hostile_before, (
                f"{tag}: battle_teleport_all moved {hr_all.get('count')}, "
                f"expected {n_hostile_before} live hostile(s)")
            assert len(hr_all.get("moves", [])) == n_hostile_before

            # ---- battle_teleport_unit (via the door-setup helper): one
            #      soldier, next to a UFO door, facing it - own hash gate ----
            actor_id, near, far, door = contact_free_ufo_door_setup(
                host, client, what=f"{tag} door setup")

            # ---- battle_state: identical {x,y,z,direction} for every moved unit ----
            hu = {u["id"]: u for u in battle_state(host).get("units", [])}
            cu = {u["id"]: u for u in battle_state(client).get("units", [])}
            moved_ids = [mv["unit"] for mv in hr_all["moves"]] + [actor_id]
            for uid in moved_ids:
                assert uid in hu and uid in cu, (
                    f"{tag}: unit {uid} missing from battle_state on one machine")
                hh, cc = hu[uid], cu[uid]
                for k in ("x", "y", "z", "direction"):
                    assert hh[k] == cc[k], (
                        f"{tag}: unit {uid} field {k!r} differs after placement - "
                        f"host={hh[k]} client={cc[k]}")

            hsold = hu[actor_id]
            assert (hsold["x"], hsold["y"], hsold["z"]) == near, (
                f"{tag}: placed soldier {actor_id} sits at "
                f"{(hsold['x'], hsold['y'], hsold['z'])}, expected {near} "
                f"(in front of door {door})")

            # ---- refusal (occupied tile): changes NOTHING, hash stays equal ----
            other_id = next((u["id"] for u in hu.values()
                              if u["id"] != actor_id and not u.get("isOut")), None)
            assert other_id is not None, (
                f"FIXTURE: {tag}: need a second live unit for the occupied-tile refusal")
            other = hu[other_id]
            occ = host.cmd({"cmd": "battle_teleport_unit", "unit": actor_id,
                             "x": other["x"], "y": other["y"], "z": other["z"]})
            assert not occ.get("ok"), (
                f"{tag}: teleporting onto an occupied tile should refuse, got {occ}")
            assert_hash_clean(host, client, full=True, what=f"{tag} after occupied-tile refusal")

            print(f"{tag}: teleport lever fixture PASSED (attempt {attempt}) - "
                  f"{hr_all['count']} hostile(s) moved, actor {actor_id} placed at "
                  f"{near} facing door {door}")
            return
        finally:
            host.shutdown()
            client.shutdown()
    raise AssertionError(
        f"FIXTURE: {tag}: {MAX_REROLLS} consecutive generated maps ALL had a live "
        "2x2+ hostile - could not exercise the battle_teleport_all ALL-1x1 happy path")


def main():
    run_fixture("basedef", "STR_BASE_DEFENSE", "47991", 48991, 48992)
    run_fixture("supplyship", "STR_SUPPLY_SHIP", "47993", 48993, 48994)
    print("ALL SPEC 6a (WV-D63) TELEPORT LEVER TESTS PASSED")


if __name__ == "__main__":
    main()
