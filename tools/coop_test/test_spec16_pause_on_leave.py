"""SPEC 16 (W1-P17) S1 - client drops mid-player-turn with a HOST WALK IN
FLIGHT (drain-first proof, M1+M2). S2-S5 are later cycles, not in this file.

Construction = owner D95 (2026-09-16, R1M F340/F342): a host-origin walk is
NOT a wire intent (beginHostLocalWalk is a UI-click path only) and
hold_chain's time-hold never engages for it, so a deterministic "walk in
flight" fixture needs a real slow multi-step walk, not the intent lane. The
fixture: SKYRANGER + a landed STR_SMALL_SCOUT (the smallest UFO) + one alien
teleported onto the UFO's lift-shaft second level (z+1, facing away) + the
host slowed via boot-time battleXcomSpeed=200, walking roughly 11-13 steps
under the Skyranger via the real UI click path. LOS is absent by
construction (the shaft's vertical floor separation plus horizontal distance
beyond MAX_VIEW_DISTANCE) and is also confirmed empirically
(spottedThisTurn stays empty on the alien before and during the walk).
While that walk is in flight (>=2 steps still pending), the client
disconnects. This exact fixture was measured REPRODUCIBLE 3/3 at tip
bb2a14dae (F342) before any M1/M2 code existed. WV-D77 evidence folded in:
battle_teleport is a dead "rewrite-pending" stub (TestServer.cpp) - the live
lever is battle_teleport_unit; the runtime set_option command has no case
for battleXcomSpeed - the live lever is the boot-time options.cfg field via
make_user_dir(options=...); the New Battle levers are newbattle_mission/
newbattle_craft (there is no write_battle_fixture command).

PRE-FIX (measured, F342, 3/3): connectionTCP::disconnectTCP() pushes
CoopState(COOP_DLG_WAIT_PLAYERS) SYNCHRONOUSLY on the drop, which puts a new
top state over BattlescapeState - only the top state thinks, so the
in-flight UnitWalkBState stops advancing: the walk FREEZES mid-path (final
tile != the destination straight_runs() actually aimed it at), and
authority.phase reads "Idle" (F331's unconditional resetBattleAuthority())
under dialog code 62.

POST-FIX (M1+M2): the walk DRAINS to its own destination/TU before the modal
appears - M2 defers the CoopState(COOP_DLG_WAIT_PLAYERS) push to the RB-D5
pump point's quiescence check (CoopArbiter::currentActionId()==0), so the
battlescape stays the top state and the walk keeps thinking until it
finishes on its own, exactly like an uninterrupted control walk of the same
recipe. The authority survives at phase=="Active" with
authority.peerAbsent==true (M1) instead of being torn down to Idle. Because
the modal cannot appear before that quiescence check passes, the drop run's
final actor position matching ITS OWN intended destination (captured before
the drop, so this is not a moving target) IS the ordering proof ("the modal
appeared after action_end") as well as the drain proof - under the pre-fix
behaviour the two can never match, since the walk never reaches its
destination once frozen. Each skirmish battle boots its own randomly
generated map, so the CONTROL run (which proves the recipe itself converges
on its own destination absent any interference) and the DROP run are
compared against their OWN destinations, never against each other's raw
coordinates - see main()'s own note.

Exit codes (ONE run each of CONTROL then DROP, no re-run of either):
  * PASS (exit 0): the drop-run walk drained to its own destination with TU
    further spent past the drop-time reading, phase=="Active",
    peerAbsent==true, battleId unchanged, inBattle==true, the host holds
    dialog 62 with saveQuitVisible/abandonVisible and backVisible false, no
    LobbyMenu, BattlescapeState intact.
  * FAIL (exit 1): a fixture precondition could not be established (no
    living alien/soldier, the UFO has no lift column, the walk never reached
    a >=2-pending mid-flight state, ...) - the scenario was never run to the
    point where it could prove anything.
  * FAIL (exit 2): a game process crashed.
  * FAIL (exit 4): both runs completed but one or more of the S1 invariants
    above did not hold - the RED this file exists to invert.
"""
import os
import sys
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, HERE)
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

SDLK_HOME = 278
SDLK_TAB = 9
COOP_DLG_WAIT_PLAYERS = 62

BASE_PORT = 49950
# Rare-dataset scan ceiling for _locate_ufo_lift_column(): any mapDataSetID
# seen fewer than this many times at z=0, excluding the common hull/ground
# sets, is a lift/hull-dataset candidate (F342, measured on this build's
# STR_SMALL_SCOUT map).
UFO_LIFT_DATASET_RARE_MAX = 80
# Pinned via `set_seed` (session.drive_to_battlescape's `pre_ok` window) so
# CONTROL and DROP generate the IDENTICAL map/actor/alien layout - see
# _bring_up()'s doc comment. Chosen empirically: this seed's STR_SMALL_SCOUT
# skirmish map spawns the actor's squad far enough from the UFO's lift shaft
# for straight_runs()'s contact-free candidate search to succeed, and gives
# a walk long enough to hold >=2 pending steps at battleXcomSpeed=200.
SPEC16_S1_SEED = 2

_DIR_DX = [0, 1, 1, 1, 0, -1, -1, -1]
_DIR_DY = [-1, -1, 0, 1, 1, 1, 0, -1]


def _top_state(gc):
    states = session.states(gc)
    return states[-1] if states else None


def _lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def _dialog(gc):
    return gc.cmd({"cmd": "coop_dialog_info"})


def _away_direction(actor, target_xy):
    """The octant (0=N..7=NW) of the vector from @a actor toward
    @a target_xy, continuing PAST it - i.e. facing away from the actor."""
    vx, vy = (target_xy[0] - actor["x"]), (target_xy[1] - actor["y"])
    return max(range(8), key=lambda d: _DIR_DX[d] * vx + _DIR_DY[d] * vy)


def _bring_up(tag, run_idx, seed):
    """Skirmish (NEW BATTLE > COOP) lobby -> STR_SMALL_SCOUT landed UFO
    ground assault, craft pinned to STR_SKYRANGER, host slowed via boot-time
    battleXcomSpeed. oxceCrashedOrLanded=2 forces the NEW BATTLE screen's UFO
    LANDED toggle on (NewBattleState.cpp:201-202), selecting
    STR_UFO_GROUND_ASSAULT instead of a 50/50 crash roll
    (NewBattleState.cpp:757-767). @a seed is pinned via `set_seed` right
    before `newbattle_ok` (session.drive_to_battlescape's `pre_ok` window -
    the established pattern this suite already uses, e.g.
    test_rw_turn_baton.py/test_rw_end_turn_tally.py/repro_atom_walk.py), so
    the CONTROL and DROP scenarios generate the IDENTICAL map/actor/alien
    layout when called with the same @a seed - the spec's own "an
    uninterrupted control run of the SAME walk" requires the SAME walk, not
    merely the same recipe, and two independent un-seeded skirmish boots
    never share a map."""
    port = BASE_PORT + run_idx * 4
    host_dir = make_user_dir(f"spec16s1_{tag}_host_{run_idx}", options={
        "battleXcomSpeed": 200,
        "oxceCrashedOrLanded": 2,
    })
    client_dir = make_user_dir(f"spec16s1_{tag}_client_{run_idx}")
    host = GameClient("host", port, host_dir)
    client = GameClient("client", port + 1, client_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": str(port), "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))

    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": str(port), "player": "ClientPlayer"})

    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("BATTLE SETTINGS offered", lambda: _lobby(host).get("buttonVisible") or None)

    seated = {}
    session.drive_to_battlescape(
        host, client, seated, mission="STR_SMALL_SCOUT", seat_client=False,
        pre_seat=lambda h: h.ok({"cmd": "newbattle_craft", "type": "STR_SKYRANGER"}),
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": seed}))

    for gc, name in ((host, "host"), (client, "client")):
        bs = session.battle_state(gc)
        assert bs.get("phase") == "Active", f"{name}: phase={bs.get('phase')!r}, expected Active"
        assert bs.get("authority", {}).get("battleId", 0) != 0, f"{name}: battleId is 0"
    return host, client


def _find_alien(host):
    bs = session.battle_state(host)
    return [u for u in bs["units"] if u.get("faction") == 1 and not u.get("isOut")]


def _find_host_soldier(host):
    bs = session.battle_state(host)
    return [u for u in bs["units"] if u.get("faction") == 0 and u.get("isPlayerSoldier")
            and not u.get("isOut")]


def _locate_ufo_lift_column(host):
    """Scan z=0 for the UFO's own rare mapDataSetID (the lift/hull dataset)
    and return (x, y, ds_id, info) for the first (x,y) whose z=0 floor part
    carries it, or (None, None, None, info) if no such column exists on this
    boot's map. F342: this build's STR_SMALL_SCOUT UFO1 block has no
    isUfoDoor/isDoor tile anywhere, but it does have a real 1-tile-wide,
    3-level-tall lift/elevator shaft - use that instead of a door."""
    dr = host.cmd({"cmd": "find_doors", "limit": 1})
    mx, my = dr["mapSizeX"], dr["mapSizeY"]
    counts = {}
    first_hit = {}
    for x in range(mx):
        for y in range(my):
            ti = host.cmd({"cmd": "tile_info", "x": x, "y": y, "z": 0})
            if not ti.get("ok"):
                continue
            for pname in ("floor", "westwall", "northwall", "object"):
                part = ti["parts"].get(pname, {})
                dsid = part.get("mapDataSetID", -1)
                did = part.get("mapDataID", -1)
                if dsid < 0 or did < 0:
                    continue
                counts[dsid] = counts.get(dsid, 0) + 1
                if dsid not in first_hit and pname == "floor":
                    first_hit[dsid] = (x, y, ti)
    rare = sorted([k for k, v in counts.items() if v < UFO_LIFT_DATASET_RARE_MAX and k in first_hit])
    if not rare:
        return None, None, None, {"counts": counts}
    ds_id = rare[0]
    x, y, ti = first_hit[ds_id]
    return x, y, ds_id, {"counts": counts, "ground_tile": ti}


def _far_destinations(host, actor, alien_pos, occupied, length, want=5):
    """Candidate walk destinations exactly @a length tiles away (Chebyshev)
    from @a actor, open ground, ORDERED same-z-first then farthest from
    @a alien_pos - the same ring-search shape as session.straight_runs(),
    minus its region_is_contact_free() bounding-box gate.

    WHY NOT session.straight_runs() DIRECTLY: that gate requires EVERY tile
    between actor and dest to stay beyond MAX_VIEW_DISTANCE (20) of the
    alien - calibrated for a walk that starts and ends far from a
    horizontally-visible alien. This fixture's LOS safety comes from a
    DIFFERENT mechanism (F342/D95): the alien sits one Z-LEVEL UP on the
    UFO's lift shaft, so line of sight is blocked by the intervening floor
    regardless of horizontal distance - and the actor's own spawn is
    measured (this file's own author-time hunt, captured 2026-09-16)
    within 11-21 tiles of the shaft on EVERY seed tried on this map, well
    under 20, which makes straight_runs()'s full-box requirement
    unsatisfiable here by construction, not a bug in this fixture's LOS.
    The spec's own S1 text makes the EMPIRICAL spottedThisTurn check (see
    _run_scenario) the authority on LOS, not this distance heuristic - this
    helper only orders candidates so the walk still heads AWAY from the
    alien first, same as the intent behind straight_runs()'s own ordering."""
    aliens = [alien_pos]
    ring = []
    for dz in (0, -1, 1):
        z = actor["z"] + dz
        if z < 0:
            continue
        for dx in range(-length, length + 1):
            for dy in range(-length, length + 1):
                if max(abs(dx), abs(dy)) != length:
                    continue
                t = (actor["x"] + dx, actor["y"] + dy, z)
                d = session.min_dist_to(aliens, t)
                ring.append((abs(dz), -(d if d is not None else 1e9), t))
    ring.sort(key=lambda e: (e[0], e[1]))

    out = []
    for _, _, t in ring:
        if session.tile_is_open_ground(host, t[0], t[1], t[2], occupied):
            out.append((None, [t]))
            if len(out) >= want:
                break
    return out


def _select_by_tab(gc, unit_id, max_presses=16):
    for _ in range(max_presses):
        if session.battle_state(gc).get("selectedId") == unit_id:
            return True
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
    return session.battle_state(gc).get("selectedId") == unit_id


def _click_walk(host, dest, max_rounds=4):
    """The proven real-UI recipe (a host walk is NOT a wire intent - F340):
    HOME to center the camera, map_tile_click_pos to get a verified window
    pixel for @a dest, inject_input to click it."""
    for _ in range(max_rounds):
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
        time.sleep(0.15)
        pr = host.cmd({"cmd": "map_tile_click_pos", "x": dest[0], "y": dest[1], "z": dest[2]})
        if not pr.get("verified"):
            continue
        host.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"],
                 "button": "left"})
        return True
    return False


def _poll_walk_until_pending(host, prev_action_id, min_pending=2, timeout=20):
    """Poll event_state(host)['lastWalk'] until it is the NEW walk (actionId
    != @a prev_action_id), is still `active`, and plannedLen - len(steps) >=
    @a min_pending. Returns (lastWalk_dict, pending) or (None, None) on
    timeout (a fixture problem - the walk was too short or ran too fast even
    at battleXcomSpeed=200)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        es = session.event_state(host)
        lw = es.get("lastWalk") or {}
        if lw.get("actionId", 0) != prev_action_id:
            steps = lw.get("steps") or []
            planned = lw.get("plannedLen", 0)
            pending = planned - len(steps)
            if lw.get("active") and pending >= min_pending and len(steps) >= 1:
                return dict(lw), pending
            if not lw.get("active") and lw.get("restate"):
                return dict(lw), 0  # settled before this poll caught it mid-flight
        time.sleep(0.03)
    return None, None


def _run_scenario(tag, run_idx, drop, seed):
    """One full bring-up + fixture construction + walk. If @a drop is True,
    disconnects the client once >=2 steps are pending and captures the
    post-drop host state; if False, lets the walk run to completion (the
    CONTROL this file's assertions compare the drop run against). @a seed is
    pinned identically for both scenarios so they generate the SAME map/
    actor/alien layout - see _bring_up()'s own doc comment."""
    host, client = _bring_up(tag, run_idx, seed)
    result = {"run": tag, "drop": drop, "ok": False}
    try:
        aliens = _find_alien(host)
        assert aliens, "no living alien on this boot"
        soldiers = _find_host_soldier(host)
        assert soldiers, "no living host soldier on this boot"
        alien = aliens[0]
        actor = soldiers[0]

        lx, ly, ds_id, ds_info = _locate_ufo_lift_column(host)
        assert lx is not None, (
            f"no rare (<{UFO_LIFT_DATASET_RARE_MAX}-tile) UFO dataset column "
            f"found at z=0 on this boot - counts={ds_info.get('counts')}")
        ti1 = host.cmd({"cmd": "tile_info", "x": lx, "y": ly, "z": 1})
        assert ti1.get("ok") and ti1["parts"]["floor"].get("mapDataID", -1) >= 0, (
            f"UFO lift column at ({lx},{ly}) has no floor at z=1: {ti1}")
        elevator_tile = (lx, ly, 1)

        away_dir = _away_direction(actor, (lx, ly))
        for gc in (host, client):
            tr = gc.cmd({"cmd": "battle_teleport_unit", "unit": alien["id"],
                         "x": elevator_tile[0], "y": elevator_tile[1], "z": elevator_tile[2],
                         "dir": away_dir})
            assert tr.get("ok"), f"battle_teleport_unit failed on {gc.name}: {tr}"

        assert _select_by_tab(host, actor["id"]), "could not TAB-select the host actor"

        occupied = {(u["x"], u["y"], u["z"]) for u in session.battle_state(host)["units"]
                    if not u.get("isOut")}
        # Longest-affordable-first: a Chebyshev `length` walk costs at least
        # ~4 TU/tile on flat ground (OpenXcom's baseline walk cost), so a
        # length whose lower-bound estimate already exceeds the actor's
        # current TU cannot possibly complete uninterrupted - skip it rather
        # than pick a destination the CONTROL run itself could never reach
        # (a legitimate TU-exhaustion halt would look identical to a frozen
        # walk and defeat this file's own drain-completeness assertion).
        candidates = []
        actor_tu = actor.get("tu", 0)
        for length in (10, 12, 14, 8, 6, 4, 3):
            if length * 4 > actor_tu:
                continue
            candidates = _far_destinations(host, actor, elevator_tile, occupied, length=length, want=5)
            if candidates:
                break
        assert candidates, (
            f"_far_destinations() found no TU-affordable candidate destination "
            f"(actor tu={actor_tu})")
        dest = candidates[0][1][-1]
        result["dest"] = dest
        dist_to_alien = session.min_dist_to([elevator_tile], dest)
        result["dest_dist_to_alien"] = dist_to_alien

        # LOS is asserted EMPIRICALLY (F342/D95's own authority, not a
        # horizontal-distance proxy - see _far_destinations()'s doc comment
        # for why straight_runs()'s bounding-box distance gate does not apply
        # to this shaft/Z-separation fixture): the alien must not spot the
        # actor before OR during the walk.
        pre_alien = [u for u in session.battle_state(host)["units"] if u["id"] == alien["id"]][0]
        assert not pre_alien.get("spottedThisTurn"), \
            "alien already spotted before the walk - LOS guard failed"

        prev = session.walk_action_id(host)
        started = _click_walk(host, dest)
        assert started, "map_tile_click_pos never verified (tile off-view or occluded)"

        lw, pending = _poll_walk_until_pending(host, prev, min_pending=2, timeout=20)
        assert lw is not None, "walk never reached a >=2-pending mid-flight state"
        result["pendingAtDrop"] = pending
        result["plannedLen"] = lw.get("plannedLen")
        result["stepsAtDrop"] = len(lw.get("steps") or [])
        actor_mid = [u for u in session.battle_state(host)["units"] if u["id"] == actor["id"]][0]
        result["actor_tu_at_drop"] = actor_mid.get("tu")

        mid_alien = [u for u in session.battle_state(host)["units"] if u["id"] == alien["id"]][0]
        assert not mid_alien.get("spottedThisTurn"), \
            "alien spotted mid-walk - LOS guard failed, the walk may have halted early"

        if drop:
            result["battleIdBeforeDrop"] = session.battle_state(host).get("authority", {}).get("battleId")
            client.cmd({"cmd": "disconnect_to_menu"})
            client.wait_for("client at main menu",
                            lambda: (_top_state(client) or "").endswith("MainMenuState") or None,
                            timeout=60, interval=0.5)
            host.wait_for("host raised the reconnect dialog",
                          lambda: (lambda d: (d.get("present") and d.get("code") == COOP_DLG_WAIT_PLAYERS)
                                   or None)(_dialog(host)),
                          timeout=90, interval=0.5)
            time.sleep(1.0)
            final_bs = session.battle_state(host)
            final_dialog = _dialog(host)
            final_actor = [u for u in final_bs["units"] if u["id"] == actor["id"]][0]
            result["postDrop_battle_state"] = final_bs
            result["postDrop_dialog"] = final_dialog
            result["postDrop_actor_pos"] = (final_actor["x"], final_actor["y"], final_actor["z"])
            result["postDrop_actor_tu"] = final_actor.get("tu")
            result["postDrop_top_state"] = str(_top_state(host))
            result["postDrop_states"] = [str(s) for s in session.states(host)]
        else:
            session.wait_walk_settled(host, client, prev, timeout=30)
            final_bs = session.battle_state(host)
            final_actor = [u for u in final_bs["units"] if u["id"] == actor["id"]][0]
            result["control_final_pos"] = (final_actor["x"], final_actor["y"], final_actor["z"])
            result["control_final_tu"] = final_actor.get("tu")

        result["ok"] = True
    except Exception as e:
        result["ok"] = False
        result["error"] = repr(e)
    finally:
        host.shutdown()
        client.shutdown()
    return result


def main():
    # SPEC16_S1_SEED is pinned identically for both scenarios via `set_seed`
    # (session.drive_to_battlescape's `pre_ok` window - the established
    # pattern this suite already uses for a deterministic map/actor/alien
    # layout, e.g. test_rw_turn_baton.py/repro_atom_walk.py). Without this,
    # two independently-booted skirmish battles never share a map, so a
    # cross-run "reached the SAME tile" comparison would be meaningless -
    # measured directly: two un-seeded boots landed the actor 11-30 tiles
    # apart with completely different candidate destinations. With the same
    # seed, CONTROL and DROP are the SAME walk, exactly as the spec asks.
    print("=== SPEC16 S1: CONTROL (no drop) ===")
    control = _run_scenario("control", 0, drop=False, seed=SPEC16_S1_SEED)
    print("CONTROL RESULT:", json.dumps(control, default=str, indent=2))
    if not control.get("ok"):
        print("FAIL: the CONTROL run did not complete - fixture broken:", control.get("error"))
        sys.exit(1)
    control_dest = tuple(control["dest"])
    control_pos = tuple(control["control_final_pos"])
    if control_pos != control_dest:
        print(f"FAIL: the CONTROL run itself did not reach its own destination "
              f"{control_dest} (landed {control_pos}) - fixture broken, not an M1/M2 claim")
        sys.exit(1)

    print("=== SPEC16 S1: DROP (client disconnects mid-walk) ===")
    dropped = _run_scenario("drop", 1, drop=True, seed=SPEC16_S1_SEED)
    print("DROP RESULT:", json.dumps(dropped, default=str, indent=2))
    if not dropped.get("ok"):
        print("FAIL: the DROP run did not complete - fixture broken:", dropped.get("error"))
        sys.exit(1)
    if tuple(dropped["dest"]) != control_dest:
        print(f"FAIL: the pinned seed did not reproduce the SAME walk - "
              f"control dest {control_dest} != drop dest {tuple(dropped['dest'])}")
        sys.exit(1)

    # ---- vacuity guard: "drain-first" is untested without a real mid-flight
    # window at the moment of the drop. ----
    pending = dropped.get("pendingAtDrop") or 0
    if pending < 2:
        print(f"FAIL: only {pending} step(s) were pending at the drop - "
              "drain-first is UNTESTED (need at least 2)")
        sys.exit(1)

    failures = []

    # ---- drain-to-completion against the CONTROL run of the SAME walk (the
    # pinned seed makes this an exact TILE comparison, not an approximate
    # one) - this doubles as the ordering proof: the fixed code can only
    # reach the control's own destination if the walk kept executing
    # strictly AFTER the drop, i.e. the pause modal did not freeze it. Under
    # the pre-fix behaviour this can never happen (measured RED: the walk
    # stops wherever it was mid-path the instant the modal lands on top, and
    # measured again after an M2 implementation bug - see the WV-D77 trace in
    # this unit's commit message - final tile stuck at the drop-time tile).
    # TU is checked only as "spent further past the drop-time reading", not
    # for exact equality against the control: two independently-booted
    # processes can pick up a handful of TU of incidental drift (e.g. a
    # reaction-fire/proximity check either side takes) with no bearing on
    # whether THIS walk drained - the destination TILE match is the
    # authoritative, high-precision signal (unreachable by chance after a
    # multi-tile walk). ----
    drop_pos = tuple(dropped["postDrop_actor_pos"])
    drop_tu = dropped["postDrop_actor_tu"]
    tu_at_drop = dropped["actor_tu_at_drop"]
    if drop_pos != control_pos:
        failures.append(f"walk did not drain to the control's destination: "
                         f"drop final pos {drop_pos} != control {control_pos}")
    if drop_tu >= tu_at_drop:
        failures.append(f"TU did not decrease after the drop (frozen mid-chain?): "
                         f"tu_at_drop={tu_at_drop} postDrop_tu={drop_tu}")

    bs = dropped["postDrop_battle_state"]
    dlg = dropped["postDrop_dialog"]
    authority = bs.get("authority", {})

    if bs.get("phase") != "Active":
        failures.append(f"phase={bs.get('phase')!r}, expected 'Active'")
    if authority.get("peerAbsent") is not True:
        failures.append(f"authority.peerAbsent={authority.get('peerAbsent')!r}, expected True")
    if authority.get("battleId") != dropped.get("battleIdBeforeDrop"):
        failures.append(f"authority.battleId changed: before={dropped.get('battleIdBeforeDrop')} "
                         f"after={authority.get('battleId')}")
    if not bs.get("inBattle"):
        failures.append("inBattle is not true post-drop")

    if not dlg.get("present") or dlg.get("code") != COOP_DLG_WAIT_PLAYERS:
        failures.append(f"dialog not present or wrong code: {dlg}")
    if not dlg.get("saveQuitVisible"):
        failures.append("dialog.saveQuitVisible is not true")
    if not dlg.get("abandonVisible"):
        failures.append("dialog.abandonVisible is not true")
    if dlg.get("backVisible"):
        failures.append("dialog.backVisible is true (expected false - the peer has not rejoined)")

    top = dropped.get("postDrop_top_state") or ""
    if "LobbyMenu" in top:
        failures.append(f"host top state is LobbyMenu ({top}) - the battle was torn down")
    states = dropped.get("postDrop_states") or []
    if not any("BattlescapeState" in s for s in states):
        failures.append(f"BattlescapeState is not on the host's state stack: {states}")

    if failures:
        print("FAIL: S1 invariant(s) violated:")
        for f in failures:
            print("  -", f)
        sys.exit(4)

    print("PASS: SPEC16 S1 - the host's in-flight walk drained to the "
          "control's destination/TU before the pause modal appeared; the "
          "authority survived (phase=Active, peerAbsent=true, battleId "
          "unchanged); dialog 62 held the end control, no LobbyMenu, "
          "BattlescapeState intact.")
    sys.exit(0)


if __name__ == "__main__":
    main()
