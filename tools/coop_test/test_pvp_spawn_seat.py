"""R5-U4 rows Z2 and Z3 (owner D235 (a); D235-VL1 / R5-V2, VL-U4-3): in PvP a unit created mid-battle takes the seat of
its side's player and, like that side's other units, has no AI module. Two boots, one row each.

Spec: docs repo rewrite/prompts/r5u4_ownerless_units.md section (f) test_pvp_spawn_seat.py (QU4-4 (a), QU4-5 (a)),
with the orchestrator rulings R-U4-A-1 (the shooter staged onto open ground, hash-gated), R-U4-A-4 (one TAB before the
click that selects Z3), R-U4-A-5 / R-U4-A-7 (Z3's victim staged onto open ground first, facing Z3's walk) and R-9B-2
(boot P3's lobby key 48697). Constants: rewrite/r5u4-task0/CONSTANTS.md (TASK 0 boots P2a / P2b, P3a-P3d).

Boot P2 (gm2: the partner plays the aliens; key 48689, dirs r5u4_p2_host / _client): test_battle_end_rules.boot_e6;
every live unit's reactions 0.
  Z2  side 0: X2's rifle, X2 onto open ground, X's spawn staging (STR_ZOMBIE, spawnUnitFaction 1), host set_seed, the
      host-local lever snap shot of X2 at FLOOR_Z2 converts X into the zombie Z2 on X-COM's side: Z2-spawn, Z2-seat (the
      alien player's seat 1), Z2-ai (no AI module), Z2-cmd (after the host's END TURN the partner turns Z2), Z2-common.
Boot P3 (gm3: the host plays the aliens; key 48697, dirs r5u4_p3_host / _client), after P2 is shut down:
test_pvp_gm3.bring_up; reactions 0; the partner's END TURN hands side 1 (the aliens) to the host.
  Z3  side 1: A's plasma pistol, X then A onto open ground, X's spawn staging (STR_ZOMBIE, 1), host set_seed, A's lever
      snap shot at FLOOR_Z3 converts X into Z3: Z3-spawn, Z3-seat (the host's seat 0), Z3-ai, Z3-sel (one TAB, then
      one click on Z3), Z3-walk (the host's real click walk), Z3-deny (the partner's turn intent refused), Z3-common.
Red at A1 (the unchanged build): Z2-seat, Z2-ai, Z2-cmd, Z3-seat, Z3-ai, Z3-walk FAIL; every other cell PASS.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails its row "boot"; a staging step past its bound fails the row
"staging"; a cell whose precondition cell failed FAILs "not reached". Common cell: every hash bucket EQUAL, desyncSeen
false on both, no new crash file. Lever pairs go to the client first (F607); ids come from probes (S25).
WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_spawn_seat.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_ownerless_units as OU  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import both  # noqa: E402

P2_KEY, P3_KEY = "48689", "48697"         # R-9B-2: 48696 is RV-U2's
SEED_Z2, SEED_Z3 = 1, 1                   # host set_seed right before each lever shot
STEP_S = OU.STEP_S
ZOMBIE = "STR_ZOMBIE"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
A_ID = 1000000                            # the alien (gm2: the partner's seat 1; gm3: the host's seat 0)
X, X2 = 8, 9                              # the lowest X-COM ids: the victim, the gm2 shooter (P2a / P2b, P3a-P3d)
STAGE_X2, X2_DIR = (20, 19, 0), 4         # R-U4-A-1: gm2's shooter
FLOOR_Z2 = (24, 19, 0)                    # the FLOOR rule's target from STAGE_X2 (k 4, d 2)
STAGE_X, X_DIR = (20, 19, 0), 0           # R-U4-A-5 / R-U4-A-7: gm3's victim, facing Z3_DEST
STAGE_A, A_DIR = (24, 19, 0), 5           # R-U4-A-1: gm3's shooter; a clear ray west to STAGE_X
FLOOR_Z3 = (28, 19, 0)                    # the FLOOR rule's target from STAGE_A (k 4, d 2)
Z3_TU = 30
Z3_DEST = (20, 18, 0)                     # 1 tile north of STAGE_X: path_probe steps 1, tuCost 4 on both
Z2_ORDER = ("Z2-spawn", "Z2-seat", "Z2-ai", "Z2-cmd", "Z2-common")
Z3_ORDER = ("Z3-spawn", "Z3-seat", "Z3-ai", "Z3-sel", "Z3-walk", "Z3-deny", "Z3-common")
WANT_ZOMBIE = {"type": ZOMBIE, "faction": FACTION_HOSTILE, "originalFaction": FACTION_HOSTILE,
               "isPlayerSoldier": False}

units, es = G3F.units, G3F.es


# ===================== boot P2 (gm2) =====================


def stage_z2(host, client):
    m, ev = (host, client), {}
    ev["rifle"] = G3F.guarded("Z2 staging", lambda: OU.give(host, client, X2, "STR_RIFLE", "STR_RIFLE_CLIP")
                              .get("weaponId"), m)
    ev["X2"] = G3F.guarded("Z2 staging", lambda: OU.tele(host, client, X2, STAGE_X2, X2_DIR, "r5u4 Z2 shooter")
                           .get("to"), m)
    ev["spawn"] = G3F.guarded("Z2 staging", lambda: OU.spawn_staging(host, client, X, ZOMBIE, FACTION_HOSTILE)
                              .get("spawnUnit"), m)
    return ev


def row_z2(host, client, crash0, st):
    cells, ev = {}, {"staging": st}
    z2, new, spawns = OU.convert(host, client, X2, FLOOR_Z2, SEED_Z2, ev)
    cells["Z2-spawn"] = OU.spawn_cell(new, X2, spawns, z2, X, host, client, WANT_ZOMBIE)
    if not cells["Z2-spawn"][0]:
        OU.not_reached(cells, ("Z2-seat", "Z2-ai", "Z2-cmd"), "Z2-spawn failed")
    else:
        cells["Z2-seat"] = OU.both_fields(host, client, z2, "coop", 1)
        cells["Z2-ai"] = OU.both_fields(host, client, z2, "hasAI", False)
        ev["press"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        try:
            drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
            session.wait_host_idle(host, client, timeout=STEP_S)
            ev["drive"] = "ok"
        except Exception as e:
            ev["drive"] = str(e)[:300]
        ev["atSide1"] = [{k: (units(gc).get(z2) or {}).get(k) for k in ("tu", "direction", "coop", "hasAI")}
                         for gc in (host, client)]
        d2 = ((units(client).get(z2) or {}).get("direction", 0) + 2) % 8
        t = OU.partner_turn(host, client, z2, d2, ev.setdefault("cmd", {"toDir": d2}))
        c_ok, c_txt = OU.ctx_cell(t["newCtx"], "intent", "turn", z2)
        sides = [OU.side_turn(gc)[0] for gc in (host, client)]
        cells["Z2-cmd"] = (ev["drive"] == "ok" and c_ok and t["dirs"] == [d2, d2] and t["lastDeny"] == t["lastDeny0"],
                           f"side change to 1: {ev['drive']} (sides {sides}); {c_txt}; Z2 direction host/partner "
                           f"{t['dirs']} (want {d2} on both); partner lastDeny {t['lastDeny0']} -> {t['lastDeny']} "
                           f"(want unchanged)")
    cells["Z2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def boot_p2():
    host = GameClient("host", None, make_user_dir("r5u4_p2_host"))
    client = GameClient("client", None, make_user_dir("r5u4_p2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("P2", lambda: BER.boot_e6(host, client, P2_KEY), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("P2", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all((("Z2", Z2_ORDER),), "boot (FIXTURE-STOP, see the CAPTURE P2 line)")
        try:
            st = stage_z2(host, client)
        except G3F.Miss:
            return G3F.fail_all((("Z2", Z2_ORDER),), "staging (see the CAPTURE Z2 staging line)")
        return G3F.run_row("Z2", Z2_ORDER, lambda: row_z2(host, client, crash0, st))
    finally:
        G3F.shut(host, client)


# ===================== boot P3 (gm3) =====================


def stage_z3(host, client):
    m, ev = (host, client), {}
    ev["pistol"] = G3F.guarded("Z3 staging", lambda: OU.give(host, client, A_ID, "STR_PLASMA_PISTOL",
                                                             "STR_PLASMA_PISTOL_CLIP").get("weaponId"), m)
    ev["X"] = G3F.guarded("Z3 staging", lambda: OU.tele(host, client, X, STAGE_X, X_DIR, "r5u4 Z3 victim").get("to"), m)
    ev["A"] = G3F.guarded("Z3 staging", lambda: OU.tele(host, client, A_ID, STAGE_A, A_DIR, "r5u4 Z3 shooter")
                          .get("to"), m)
    ev["spawn"] = G3F.guarded("Z3 staging", lambda: OU.spawn_staging(host, client, X, ZOMBIE, FACTION_HOSTILE)
                              .get("spawnUnit"), m)
    return ev


def row_z3(host, client, crash0, st):
    cells, ev = {}, {"staging": st}
    z3, new, spawns = OU.convert(host, client, A_ID, FLOOR_Z3, SEED_Z3, ev)
    cells["Z3-spawn"] = OU.spawn_cell(new, A_ID, spawns, z3, X, host, client, WANT_ZOMBIE)
    if not cells["Z3-spawn"][0]:
        OU.not_reached(cells, ("Z3-seat", "Z3-ai", "Z3-sel", "Z3-walk", "Z3-deny"), "Z3-spawn failed")
    else:
        cells["Z3-seat"] = OU.both_fields(host, client, z3, "coop", 0)
        cells["Z3-ai"] = OU.both_fields(host, client, z3, "hasAI", False)
        ev["Z3"] = [{k: (units(gc).get(z3) or {}).get(k) for k in ("tu", "direction", "x", "y", "z")}
                    for gc in (host, client)]
        ev["tu"] = both(host, client, {"cmd": "battle_set_unit_state", "unit": z3, "tu": Z3_TU}, ("tu",)).get("tu")
        cells["Z3-sel"] = OU.tab_then_click(host, z3, ev.setdefault("sel", {}))
        if not cells["Z3-sel"][0]:
            G3F.capture("Z3 sel", cells["Z3-sel"][1], (host, client))
            OU.not_reached(cells, ("Z3-walk",), "Z3-sel failed")
        else:
            cells["Z3-walk"] = OU.host_walk(host, client, z3, Z3_DEST, ev.setdefault("walk", {}))
        to = ((units(client).get(z3) or {}).get("direction", 0) + 2) % 8
        cells["Z3-deny"] = OU.deny_cell(OU.partner_turn(host, client, z3, to, ev.setdefault("deny", {"toDir": to})), z3)
    cells["Z3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def boot_p3():
    host = GameClient("host", None, make_user_dir("r5u4_p3_host"))
    client = GameClient("client", None, make_user_dir("r5u4_p3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, P3_KEY, "P3")
            G3F.guarded("P3", lambda: G3F.reactions_zero(host, client), m)

            def to_side1():
                client.ok({"cmd": "battle_action", "action": "end_turn_button"})
                drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
                session.wait_host_idle(host, client, timeout=STEP_S)
                st = [OU.side_turn(gc) for gc in m]
                assert boot["lobbyGamemode"] == 3 and st == [(1, 1), (1, 1)], (
                    f"lobby gamemode {boot['lobbyGamemode']} (want 3); (side, turn) host/partner {st} (want (1, 1))")
            G3F.guarded("P3", to_side1, m)
        except G3F.Miss:
            return G3F.fail_all((("Z3", Z3_ORDER),), "boot (FIXTURE-STOP, see the CAPTURE P3 line)")
        try:
            st = stage_z3(host, client)
        except G3F.Miss:
            return G3F.fail_all((("Z3", Z3_ORDER),), "staging (see the CAPTURE Z3 staging line)")
        return G3F.run_row("Z3", Z3_ORDER, lambda: row_z3(host, client, crash0, st))
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_p2()
    fails += boot_p3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_spawn_seat: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
