"""SPEC 0e-1 (WV-D87/WV-D88, WAVE1-RUNBOOK.md REV E.17): the Lightning-contact
SPIKE. MEASURES the two staging designs the owner chose - WV-D87 (the door
atom and the spot atom stage on the LIGHTNING craft's own UFO door) and
WV-D88 (non-UFO door coverage and the 2x2 proof stage on STR_TERROR_MISSION +
STR_FLOATER, aliens and civilians in opposite corners) - on LIVE BOOTS, before
SPEC 0e-2/0e-3 rewrite a single test against them. This file is a MEASUREMENT
TOOL, not a regression member (WV-D86's no-reroll rule does not make this a
fixture - there is nothing here to re-roll: a map that cannot support the
staging is itself the finding).

EXIT CODES (binding, spec 0e-1 (i)):
  0 - every measurement was taken (an "expected: X" line is a PREDICTION,
      recorded as CONFIRMED or NOT in the printed RESULT block - a NOT is a
      finding for the supervisor, never a failure of this file);
  2 - at least one measurement's own PRECONDITION could not be met (no
      LIGHTNIN door found, newbattle_craft refused STR_LIGHTNING,
      newbattle_race refused STR_FLOATER, a door has no walk-through sides,
      no standable perpendicular tile, a lever call errored, ...) - the
      printed record IS the STOP-IF report. Every boot still runs (each
      catches its own precondition failure independently) so a single miss
      never hides the other two boots' measurements.

Three boots, each printing one `RESULT` block:
  BOOT A placement=P1  default mission, Lightning craft. Hostile staged
                       STRAIGHT OUT from the door.
  BOOT A placement=P2  same recipe, fresh boot. Hostile staged AROUND THE
                       CORNER from the door.
  BOOT B               STR_TERROR_MISSION + STR_FLOATER + Lightning craft.
                       No walk - a placement-only measurement.

Run:  python tools/coop_test/spike_lightning_contact.py
      (its own harness invocation - the standing rule, one test per
       invocation, machine-wide harness lock.)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import place_deterministic
import repro_atom_walk as W
import repro_atom_spot as SPOT

FACTION_PLAYER = session.FACTION_PLAYER
FACTION_HOSTILE = session.FACTION_HOSTILE
FACTION_NEUTRAL = 2  # session.py's own comment: standard UnitFaction enum (PLAYER=0, HOSTILE=1, NEUTRAL=2)

# WV-D88 (B3): OpenXcom's MAX_VIEW_DISTANCE is 20 tiles - "the sight cap + 1"
# is the smallest Chebyshev distance that guarantees a unit standing at a door
# cannot see a unit standing at the other.
SIGHT_CAP_PLUS_ONE = 21

_OPPOSITE_CORNER = {"NW": "SE", "NE": "SW", "SW": "NE", "SE": "NW"}


class Precondition(AssertionError):
    """A measurement's own precondition could not be met - this file's exit-2
    STOP. Never a fixture reroll (WV-D86): this file re-rolls nothing, it
    reports what the live boot actually did."""


def require(cond, msg):
    if not cond:
        raise Precondition(msg)


def pred(confirmed, actual):
    """One line of the RESULT block for a spec EXPECTATION - never raises,
    never gates anything downstream (spec 0e-1: "a NOT is a finding for the
    supervisor, never a failure and never a reason to change anything")."""
    return {"status": "CONFIRMED" if confirmed else "NOT", "actual": actual}


# ----- small probes ---------------------------------------------------------

def find_doors_raw(gc, **extra):
    r = gc.cmd({"cmd": "find_doors", "limit": 512, **extra})
    require(r.get("ok"), f"find_doors failed: {r}")
    return r


def lightning_door(host, record):
    """A1/WV-D87: the craft's own LIGHTNIN UFO door, by dataset NAME. Hard
    STOP only when NONE is found at all - the situation every later
    measurement in this boot depends on would not exist. Count != 1 / not a
    UFO door / already open at boot are recorded PREDICTIONS (WV-D87's
    decided premise is being MEASURED here, not assumed), never a reason to
    stop; this file proceeds with the first one found either way."""
    raw = find_doors_raw(host)
    lightnin = [d for d in raw["doors"] if d.get("dataSet") == "LIGHTNIN"]
    require(lightnin, "no LIGHTNIN door found by find_doors - WV-D87's staging "
                       "premise (a closed UFO door on every map) does not hold "
                       "on this boot")
    door = lightnin[0]
    record["a1_lightnin_doors"] = lightnin
    record["a1_predictions"] = {
        "exactly_1_lightnin_door": pred(len(lightnin) == 1, len(lightnin)),
        "isUfoDoor_true": pred(door.get("isUfoDoor") is True, door.get("isUfoDoor")),
        "closed_at_boot": pred(door.get("isUfoDoorOpen") is False, door.get("isUfoDoorOpen")),
    }
    return door, raw["mapSizeX"], raw["mapSizeY"], raw["mapSizeZ"]


def far_corner(door, mx, my):
    """Same convention `session.contact_free_ufo_door_setup` uses: the corner
    FARTHEST from the door, by halves of the map."""
    vert = "S" if door["y"] < my / 2.0 else "N"
    horiz = "E" if door["x"] < mx / 2.0 else "W"
    corner = vert + horiz
    return corner, session._CORNER_FACING[corner]


def near_far_sides(door, seat1):
    """A4: `door_sides` gives the two tiles a wall-part door joins; `near` is
    whichever is CLOSER to a seated soldier (the craft interior), `far` the
    other (the exterior)."""
    sides = session.door_sides(door)
    require(sides is not None,
            f"door_sides() returned None for door {door} - not a walk-through wall part")
    side_a, side_b = sides

    def min_dist(tile):
        return min(session.cheb(tile, session.unit_pos(u)) for u in seat1)

    da, db = min_dist(side_a), min_dist(side_b)
    return (side_a, side_b) if da <= db else (side_b, side_a)


def outward_dir(near, far):
    dx = far[0] - near[0]
    dy = far[1] - near[1]
    return session._DIR_FROM_DELTA[(dx, dy)]


def add_delta(pos, d, n=1):
    return (pos[0] + session.DIR_DX[d] * n, pos[1] + session.DIR_DY[d] * n, pos[2])


def opposite_dir(d):
    return (d + 4) % 8


def perpendiculars(d):
    return (d + 2) % 8, (d - 2) % 8


def read_hash(host, client):
    """Non-raising counterpart of session.assert_hash_clean. The POST-ACTION
    hash compare in A6/A7 is a MEASUREMENT, not a staging gate - a mismatch
    there is exactly the kind of finding this spike exists to surface, never
    a spike precondition failure. (Every STAGING move above still goes
    through `place_deterministic`, whose own internal hash gate DOES raise -
    a desynced SITUATION is not a valid experiment.)"""
    hr = host.cmd({"cmd": "hash_now", "full": True})
    cr = client.cmd({"cmd": "hash_now", "full": True})
    hh, ch = hr.get("h", {}), cr.get("h", {})
    equal = bool(hh) and hh == ch
    return equal, hh, ch


# ----- pre_seat callbacks (SPEC 0e-1: mission -> craft -> race -> seats -> ok) ---

def pin_lightning(host):
    r = host.cmd({"cmd": "newbattle_craft", "type": "STR_LIGHTNING"})
    require(r.get("ok"), f"newbattle_craft refused STR_LIGHTNING: {r}")


def pin_lightning_and_floater(host):
    pin_lightning(host)
    r = host.cmd({"cmd": "newbattle_race", "race": "STR_FLOATER"})
    require(r.get("ok"), f"newbattle_race refused STR_FLOATER: {r}")


# ----- BOOT A (WV-D87): default mission, Lightning --------------------------

def boot_a(placement, game_port, host_port, client_port):
    tag = f"lightning_a_{placement.lower()}"
    record = {"boot": "A", "placement": placement}
    host_dir = make_user_dir(f"spike_{tag}_host")
    client_dir = make_user_dir(f"spike_{tag}_client")
    host = GameClient(f"{tag}-host", host_port, host_dir)
    client = GameClient(f"{tag}-client", client_port, client_dir)
    try:
        W.bring_up_lobby(host, client, game_port)
        seated = {}
        session.drive_to_battlescape(host, client, seated, mission=None,
                                      pre_seat=pin_lightning)

        door, mx, my, mz = lightning_door(host, record)
        door_pos = (door["x"], door["y"], door["z"])

        # A2: every seat-1 soldier's Chebyshev distance to the door.
        seat1 = session.seat_units(host)
        require(seat1, "no live seat-1 soldier after bring-up")
        distances = {u["id"]: session.cheb(session.unit_pos(u), door_pos) for u in seat1}
        record["a2_seat1_distance_to_door"] = distances
        record["a2_prediction_all_le_6"] = pred(all(d <= 6 for d in distances.values()),
                                                 distances)

        # A3: spotted sets at turn start.
        bs0 = session.battle_state(host)
        spotted0 = bs0.get("spotted", [])
        player_spotted = {u["id"]: u.get("spottedThisTurn", [])
                           for u in bs0.get("units", [])
                           if u.get("faction") == FACTION_PLAYER and u.get("spottedThisTurn")}
        record["a3_spotted_at_turn_start"] = spotted0
        record["a3_player_spottedThisTurn"] = player_spotted
        record["a3_prediction_all_empty"] = pred(
            not spotted0 and not player_spotted,
            {"spotted": spotted0, "player_spottedThisTurn": player_spotted})

        # A4: near/far + outward direction + its two perpendiculars.
        near, far = near_far_sides(door, seat1)
        d_out = outward_dir(near, far)
        perp1, perp2 = perpendiculars(d_out)
        record["a4_near"] = near
        record["a4_far"] = far
        record["a4_d_out"] = d_out
        record["a4_perpendiculars"] = [perp1, perp2]

        # A5: hostiles to the corner farthest from the door; hash gate.
        corner, facing = far_corner(door, mx, my)
        [(teleport_all_resp, _)] = place_deterministic(
            host, client,
            [{"lever": "battle_teleport_all", "faction": "hostile",
              "corner": corner, "facing": facing}],
            what=f"{tag} A5 hostiles to far corner")
        record["a5_corner"] = corner
        record["a5_teleport_all"] = teleport_all_resp

        # A6/A7: place hostile #1 (lowest id) - P1 straight out, P2 around
        # the corner via the first standable perpendicular.
        live_hostiles = sorted(
            (u for u in session.units(host)
             if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")),
            key=lambda u: u["id"])
        require(live_hostiles, "no live hostile to stage the contact with")
        hostile1 = live_hostiles[0]["id"]

        # Z CORRECTION (REV E.18, traced on 6 boots): the Lightning deck sits at door.z and
        # everything past the door is void at that z; the exit tile is one level DOWN.
        far_ground = (far[0], far[1], far[2] - 1)
        record["a4_far_ground"] = far_ground
        record["a4_far_ground_standable"] = session._tile_standable(host, far_ground)
        if placement == "P1":
            target = add_delta(far_ground, d_out, 1)
        else:
            target = None
            for perp in (perp1, perp2):
                cand = add_delta(add_delta(far_ground, d_out, 1), perp, 2)
                if session._tile_standable(host, cand):
                    target = cand
                    record["a7_perp_used"] = perp
                    break
            require(target is not None,
                    f"neither perpendicular tile near {far} is standable "
                    f"(perp1={perp1}, perp2={perp2})")

        facing_door = opposite_dir(d_out)
        place_deterministic(
            host, client,
            [{"lever": "battle_teleport_unit", "unit": hostile1,
              "x": target[0], "y": target[1], "z": target[2], "dir": facing_door}],
            what=f"{tag} place hostile #{hostile1} at {target}")
        record["a6_hostile_id"] = hostile1
        record["a6_hostile_target"] = target
        record["a6_hostile_facing"] = facing_door

        # reactions pinned to 0 on all non-players, both machines; hash gate
        # (both done inside phase0_pin_reaction_fire).
        SPOT.phase0_pin_reaction_fire(host, client)

        actor = min(seat1, key=lambda u: session.cheb(session.unit_pos(u), near))
        actor_id = actor["id"]
        if session.unit_pos(actor) != near:
            place_deterministic(
                host, client,
                [{"lever": "battle_teleport_unit", "unit": actor_id,
                  "x": near[0], "y": near[1], "z": near[2], "dir": d_out}],
                what=f"{tag} place actor {actor_id} at near={near}")
        record["a6_actor_id"] = actor_id

        status, hw = W.send_walk_outcome(host, client, actor_id, far_ground)
        require(status == "walk",
                f"the contact walk was not executed (status={status!r}, {hw})")

        executed = hw.get("executed", [])
        halted = hw.get("halted")
        reason = hw.get("reason")
        action_id = hw.get("actionId")
        door_ev_present = any(e.get("kind") == "door"
                               for e in session.action_events(host, action_id))
        host_seen = (session.event_state(host).get("lastSpot") or {}).get("seen")
        client_seen = (session.event_state(client).get("lastSpot") or {}).get("seen")
        host_spotted = session.battle_state(host).get("spotted", [])
        client_spotted = session.battle_state(client).get("spotted", [])
        hash_equal, host_h, client_h = read_hash(host, client)

        record["a6_walk"] = {"halted": halted, "reason": reason,
                              "executed_prefix_len": len(executed), "executed": executed}
        record["a6_door_ev_present"] = door_ev_present
        record["a6_seen_host"] = host_seen
        record["a6_seen_client"] = client_seen
        record["a6_spotted_host"] = host_spotted
        record["a6_spotted_client"] = client_spotted
        record["a6_hash_equal"] = hash_equal
        if not hash_equal:
            record["a6_hash_mismatch"] = {
                k: (host_h.get(k), client_h.get(k))
                for k in set(host_h) | set(client_h) if host_h.get(k) != client_h.get(k)}

        if placement == "P1":
            record["a6_prediction_halt_after_1_step_spot"] = pred(
                halted is True and len(executed) == 1 and reason == "spot" and door_ev_present,
                {"halted": halted, "executed_prefix_len": len(executed)})
        else:
            record["a7_prediction_no_halt_outside_vision_cone"] = pred(
                door_ev_present and len(executed) == 1 and halted is False,
                {"door_ev_present": door_ev_present, "executed_prefix_len": len(executed),
                 "halted": halted})

        record["a8_prediction_client_spotted_equals_host"] = pred(
            sorted(host_spotted) == sorted(client_spotted),
            {"host": host_spotted, "client": client_spotted})

        record["stopped"] = False
        return record
    except AssertionError as e:
        record["stopped"] = True
        record["stop_reason"] = f"{type(e).__name__}: {e}"
        return record
    finally:
        host.shutdown()
        client.shutdown()


# ----- BOOT B (WV-D88): STR_TERROR_MISSION + STR_FLOATER + Lightning -------

def boot_b(game_port, host_port, client_port):
    tag = "lightning_b_terror"
    record = {"boot": "B"}
    host_dir = make_user_dir(f"spike_{tag}_host")
    client_dir = make_user_dir(f"spike_{tag}_client")
    host = GameClient(f"{tag}-host", host_port, host_dir)
    client = GameClient(f"{tag}-client", client_port, client_dir)
    try:
        W.bring_up_lobby(host, client, game_port)
        seated = {}
        session.drive_to_battlescape(host, client, seated, mission="STR_TERROR_MISSION",
                                      pre_seat=pin_lightning_and_floater)

        door, mx, my, mz = lightning_door(host, record)

        # B1: hostiles by armor size, civilian count, map size.
        units0 = session.units(host)
        hostiles0 = [u for u in units0 if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        civilians0 = [u for u in units0 if u.get("faction") == FACTION_NEUTRAL and not u.get("isOut")]
        by_size = {}
        for u in hostiles0:
            sz = u.get("armorSize", 1)
            by_size[sz] = by_size.get(sz, 0) + 1
        record["b1_hostiles_by_armor_size"] = by_size
        record["b1_civilian_count"] = len(civilians0)
        record["b1_map_size"] = {"x": mx, "y": my, "z": mz}
        record["b1_prediction_ge_2_size2"] = pred(by_size.get(2, 0) >= 2, by_size.get(2, 0))
        record["b1_civilians_count"] = len(civilians0)  # varies per map (9 and 11 measured); the deployment's 16 is a ceiling, not a guarantee

        # B2: hostiles to the corner farthest from the door; civilians to the
        # diagonally OPPOSITE corner; hash gate.
        hostile_corner, hostile_facing = far_corner(door, mx, my)
        neutral_corner = _OPPOSITE_CORNER[hostile_corner]
        neutral_facing = session._CORNER_FACING[neutral_corner]
        [(hostile_move, _), (neutral_move, _)] = place_deterministic(
            host, client,
            [{"lever": "battle_teleport_all", "faction": "hostile",
              "corner": hostile_corner, "facing": hostile_facing},
             {"lever": "battle_teleport_all", "faction": "neutral",
              "corner": neutral_corner, "facing": neutral_facing}],
            what=f"{tag} B2 hostiles+civilians to opposite corners")
        record["b2_hostile_corner"] = hostile_corner
        record["b2_neutral_corner"] = neutral_corner
        record["b2_hostile_move"] = hostile_move
        record["b2_neutral_move"] = neutral_move
        record["b2_prediction_hostile_count_all"] = pred(
            hostile_move.get("count") == len(hostiles0),
            {"count": hostile_move.get("count"), "expected": len(hostiles0)})
        record["b2_prediction_every_move_has_size"] = pred(
            bool(hostile_move.get("moves")) and all("size" in mv for mv in hostile_move.get("moves", [])),
            hostile_move.get("moves"))

        # B3: non-UFO closed doors; per-door distances; the one that
        # maximises min-distance-to-hostiles.
        raw_all = find_doors_raw(host)
        non_ufo = [d for d in raw_all["doors"] if not d.get("isUfoDoor")]
        require(non_ufo, "no non-UFO door found on this URBAN terror map - "
                          "WV-D88's non-UFO-door-coverage premise does not hold "
                          "on this boot")

        post_units = session.units(host)
        live_hostiles = [u for u in post_units if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        live_civilians = [u for u in post_units if u.get("faction") == FACTION_NEUTRAL and not u.get("isOut")]

        def min_dist(door_d, unit_list):
            if not unit_list:
                return None
            dp = (door_d["x"], door_d["y"], door_d["z"])
            return min(session.cheb(dp, session.unit_pos(u)) for u in unit_list)

        per_door = []
        for d in non_ufo:
            per_door.append({
                "door": {"x": d["x"], "y": d["y"], "z": d["z"], "part": d["part"]},
                "min_dist_hostile": min_dist(d, live_hostiles),
                "min_dist_civilian": min_dist(d, live_civilians),
            })
        record["b3_non_ufo_door_count"] = len(non_ufo)
        record["b3_per_door"] = per_door
        best = max(per_door,
                   key=lambda e: (e["min_dist_hostile"] is not None, e["min_dist_hostile"] or -1))
        record["b3_best_door"] = best
        record["b3_prediction_best_ge_21"] = pred(
            best["min_dist_hostile"] is not None and best["min_dist_hostile"] >= SIGHT_CAP_PLUS_ONE,
            best["min_dist_hostile"])

        # B4: spotted sets on both machines after the moves. No walk in boot B.
        record["b4_spotted_host"] = session.battle_state(host).get("spotted", [])
        record["b4_spotted_client"] = session.battle_state(client).get("spotted", [])

        record["stopped"] = False
        return record
    except AssertionError as e:
        record["stopped"] = True
        record["stop_reason"] = f"{type(e).__name__}: {e}"
        return record
    finally:
        host.shutdown()
        client.shutdown()


# ----- reporting -------------------------------------------------------------

def print_result(record):
    boot = record.get("boot")
    placement = record.get("placement")
    header = f"RESULT boot={boot}" + (f" placement={placement}" if placement else "")
    print(header)
    print(json.dumps(record, indent=2, sort_keys=True, default=str))
    print(f"END {header}")


def main():
    results = []

    results.append(boot_a("P1", "48210", 48211, 48212))
    print_result(results[-1])

    results.append(boot_a("P2", "48220", 48221, 48222))
    print_result(results[-1])

    results.append(boot_b("48230", 48231, 48232))
    print_result(results[-1])

    if any(r.get("stopped") for r in results):
        print("\nspike_lightning_contact: STOP - at least one measurement's "
              "own precondition could not be met (see stop_reason above)")
        sys.exit(2)

    print("\nspike_lightning_contact: every measurement taken")
    sys.exit(0)


if __name__ == "__main__":
    main()
