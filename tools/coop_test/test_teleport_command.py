"""Acceptance test for the deterministic placement test commands - TestServer.cpp's `battle_teleport_unit` /
`battle_teleport_all` - and their session.py helpers (`place_deterministic`, `contact_free_ufo_door_setup`).

AI-neutral: t=0 only; contact-free by construction (every live hostile is teleported away before anything else happens -
no walk, no shot, no AI turn ever runs in this file). Deterministic fixture: the situation is built by the placement
commands plus the hash-equality gate, never by a map-generator re-roll loop.

Two legs:
  - terror (STR_TERROR_MISSION with floaters, which brings live 2x2 reapers): `battle_teleport_all {faction:"hostile",
    corner:"SE"}` moves each 2x2 hostile whole into the SE corner quarter, its footprint overlapping no other unit, and
    hash_now full is ALL BUCKETS EQUAL after the move.
  - supplyship (STR_SUPPLY_SHIP, no live 2x2 hostile):
    - `battle_teleport_all {faction:"hostile"}` moves every live hostile on BOTH machines, with IDENTICAL replies.
    - `battle_teleport_unit` (via `contact_free_ufo_door_setup`) moves one seat-1 soldier onto the standable tile next
      to a UFO door, facing it.
    - `hash_now {full:true}` is ALL BUCKETS EQUAL after every placement (the gate every deterministic fixture must pass
      before its measured action - `place_deterministic`'s own assert).
    - A REFUSED call (an occupied destination tile) changes NOTHING and the hash stays equal.
    - `battle_state` reports IDENTICAL `{x,y,z,direction}` for every moved unit on both machines.
The SP smoke path (`sp_smoke.py`) is not exercised here: the teleport commands add no code on any path `sp_smoke.py`
touches.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from harness import shutdown_clients  # bring_up's cleanup
import session
from session import assert_hash_clean, place_deterministic, contact_free_ufo_door_setup
import repro_atom_walk as W

FACTION_PLAYER = 0
FACTION_HOSTILE = 1


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def bring_up(tag, mission, game_port, host_test_port, client_test_port, pre_seat=None):
    host_dir = make_user_dir(f"teleport_{tag}_host")
    client_dir = make_user_dir(f"teleport_{tag}_client")
    host = GameClient(f"{tag}-host", host_test_port, host_dir)
    client = GameClient(f"{tag}-client", client_test_port, client_dir)
    try:
        W.bring_up_lobby(host, client, game_port)
        seated = {}
        session.drive_to_battlescape(host, client, seated, mission=mission, pre_seat=pre_seat)
    except BaseException:
        # run_fixture's try/finally starts only after this returns, so a failed bring-up shuts
        # down the games it spawned here before the error propagates (shared_fixture.bring_up's form)
        shutdown_clients(host, client)
        raise
    return host, client, seated


def run_fixture(tag, mission, game_port, host_test_port, client_test_port,
               pre_seat=None, expect_2x2=False):
    host, client, _seated = bring_up(tag, mission, game_port, host_test_port, client_test_port,
                                     pre_seat=pre_seat)
    try:
        # ---- t=0 baseline: BOTH machines start from an equal document ----
        assert_hash_clean(host, client, full=True, what=f"{tag} t=0")

        hs0 = battle_state(host)
        assert hs0.get("ok") and hs0.get("inBattle"), f"{tag}: battle_state unusable on host: {hs0}"
        hostile_units = [u for u in hs0.get("units", [])
                         if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        assert hostile_units, f"FIXTURE: {tag}: no live hostile on this generated map"
        has_2x2 = any(u.get("armorSize", 1) != 1 for u in hostile_units)

        if expect_2x2:
            # a floater terror mission brings at least two live reapers,
            # so this leg proves the whole move of a 2x2 unit.
            assert has_2x2, (
                f"FIXTURE: {tag}: expected a live 2x2 hostile (floater terror), "
                f"found none: {hostile_units}")

            [(moved, _c_moved)] = place_deterministic(
                host, client,
                [{"cmd": "battle_teleport_all", "faction": "hostile",
                  "corner": "SE", "facing": 3}],
                what=f"{tag} 2x2 whole move")

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

            assert_hash_clean(host, client, full=True, what=f"{tag} after 2x2 whole move")
            print(f"{tag}: teleport command 2x2 whole-move fixture PASSED - "
                  f"{len(big_movers)} size-2 hostile(s) moved")
            return

        assert not has_2x2, f"FIXTURE: {tag}: expected no live 2x2 hostile, found one: {hostile_units}"

        n_hostile_before = len(hostile_units)

        # ---- battle_teleport_all: every live hostile, IDENTICAL replies ----
        [(hr_all, _cr_all)] = place_deterministic(
            host, client,
            [{"cmd": "battle_teleport_all", "faction": "hostile", "corner": "SE", "facing": 3}],
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

        print(f"{tag}: teleport command fixture PASSED - "
              f"{hr_all['count']} hostile(s) moved, actor {actor_id} placed at "
              f"{near} facing door {door}")
        return
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run_fixture("terror", "STR_TERROR_MISSION", "47991", 48991, 48992,
               pre_seat=lambda h: h.ok({"cmd": "newbattle_race", "race": "STR_FLOATER"}),
               expect_2x2=True)
    run_fixture("supplyship", "STR_SUPPLY_SHIP", "47993", 48993, 48994)
    print("ALL TELEPORT COMMAND TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_teleport_command", e.tracking, str(e))
        print(f"\ntest_teleport_command: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        if str(e).startswith("FIXTURE:"):
            print(f"\ntest_teleport_command: FAIL (fixture not constructed) - {e}")
            sys.exit(2)
        print(f"\ntest_teleport_command: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_teleport_command: FAIL\nTimeoutError: {e}")
        sys.exit(2)
