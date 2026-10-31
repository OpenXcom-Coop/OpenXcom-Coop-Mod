"""PvP spawn seat: in PvP a unit created mid-battle takes the seat of its side's player and, like that side's other
units, has no AI module. Two boots, one row each.

The shooters and victims stand on open ground first (hash-gated teleports); the gm3 victim faces the zombie's walk;
one TAB comes before the click that selects the gm3 zombie. The ids and tiles were measured without the fix on six
boots.

gm2 boot (the partner plays the aliens; key 48689, dirs pvp_spawn_seat_gm2_host / _client):
test_battle_end_rules.boot_pvp; every live unit's reactions 0.
  gm2_zombie  side 0: X2's rifle, X2 onto open ground, X's spawn staging (STR_ZOMBIE, spawnUnitFaction 1), host
      set_seed, the host-local snap shot of X2 at GM2_FLOOR (test command) converts X into the zombie on X-COM's side:
      gm2_zombie-spawn, gm2_zombie-seat (the alien player's seat 1), gm2_zombie-ai (no AI module), gm2_zombie-cmd
      (after the host's END TURN the partner turns the zombie), gm2_zombie-common.
gm3 boot (the host plays the aliens; key 48697, dirs pvp_spawn_seat_gm3_host / _client), after the gm2 boot is shut
down: test_pvp_gm3.bring_up; reactions 0; the partner's END TURN hands side 1 (the aliens) to the host.
  gm3_zombie  side 1: A's plasma pistol, X then A onto open ground, X's spawn staging (STR_ZOMBIE, 1), host set_seed,
      A's snap shot at GM3_FLOOR (test command) converts X into the zombie: gm3_zombie-spawn, gm3_zombie-seat (the
      host's seat 0), gm3_zombie-ai, gm3_zombie-sel (one TAB, then one click on the zombie), gm3_zombie-walk (the
      host's real click walk), gm3_zombie-deny (the partner's turn intent refused), gm3_zombie-common.
Without the fix, gm2_zombie-seat, gm2_zombie-ai, gm2_zombie-cmd, gm3_zombie-seat, gm3_zombie-ai and gm3_zombie-walk
FAIL; every other cell passes.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A
boot step past its bound prints ONE CAPTURE line and fails its row "boot"; a staging step past its bound fails the row
"staging"; a cell whose precondition cell failed FAILs "not reached". Common cell: every hash bucket EQUAL, desyncSeen
false on both, no new crash file. Test-command pairs go to the client first; ids come from probes (item ids vary per
boot). ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

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

GM2_KEY, GM3_KEY = "48689", "48697"       # 48696 is test_tile_click's
GM2_SEED, GM3_SEED = 1, 1                 # host set_seed right before each converting shot
STEP_S = OU.STEP_S
ZOMBIE = "STR_ZOMBIE"
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
A_ID = 1000000                            # the alien (gm2: the partner's seat 1; gm3: the host's seat 0)
X, X2 = 8, 9                              # the lowest X-COM ids: the victim, the gm2 shooter
STAGE_X2, X2_DIR = (20, 19, 0), 4         # gm2's shooter
GM2_FLOOR = (24, 19, 0)                   # a floor tile 4 tiles east of STAGE_X2 (direction 2)
STAGE_X, X_DIR = (20, 19, 0), 0           # gm3's victim, facing ZOMBIE_DEST
STAGE_A, A_DIR = (24, 19, 0), 5           # gm3's shooter; a clear ray west to STAGE_X
GM3_FLOOR = (28, 19, 0)                   # a floor tile 4 tiles east of STAGE_A (direction 2)
ZOMBIE_TU = 30
ZOMBIE_DEST = (20, 18, 0)                 # 1 tile north of STAGE_X: path_probe steps 1, tuCost 4 on both
GM2_ORDER = ("gm2_zombie-spawn", "gm2_zombie-seat", "gm2_zombie-ai", "gm2_zombie-cmd", "gm2_zombie-common")
GM3_ORDER = ("gm3_zombie-spawn", "gm3_zombie-seat", "gm3_zombie-ai", "gm3_zombie-sel", "gm3_zombie-walk",
             "gm3_zombie-deny", "gm3_zombie-common")
WANT_ZOMBIE = {"type": ZOMBIE, "faction": FACTION_HOSTILE, "originalFaction": FACTION_HOSTILE,
               "isPlayerSoldier": False}

units, es = G3F.units, G3F.es


# ===================== gm2 boot =====================


def stage_gm2(host, client):
    m, ev = (host, client), {}
    ev["rifle"] = G3F.guarded("gm2_zombie staging", lambda: OU.give(host, client, X2, "STR_RIFLE", "STR_RIFLE_CLIP")
                              .get("weaponId"), m)
    ev["X2"] = G3F.guarded("gm2_zombie staging", lambda: OU.tele(host, client, X2, STAGE_X2, X2_DIR, "gm2 shooter")
                           .get("to"), m)
    ev["spawn"] = G3F.guarded("gm2_zombie staging",
                              lambda: OU.spawn_staging(host, client, X, ZOMBIE, FACTION_HOSTILE).get("spawnUnit"), m)
    return ev


def row_gm2_zombie(host, client, crash0, st):
    cells, ev = {}, {"staging": st}
    zombie_gm2, new, spawns = OU.convert(host, client, X2, GM2_FLOOR, GM2_SEED, ev)
    cells["gm2_zombie-spawn"] = OU.spawn_cell(new, X2, spawns, zombie_gm2, X, host, client, WANT_ZOMBIE)
    if not cells["gm2_zombie-spawn"][0]:
        OU.not_reached(cells, ("gm2_zombie-seat", "gm2_zombie-ai", "gm2_zombie-cmd"), "gm2_zombie-spawn failed")
    else:
        cells["gm2_zombie-seat"] = OU.both_fields(host, client, zombie_gm2, "coop", 1)
        cells["gm2_zombie-ai"] = OU.both_fields(host, client, zombie_gm2, "hasAI", False)
        ev["press"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        try:
            drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
            session.wait_host_idle(host, client, timeout=STEP_S)
            ev["drive"] = "ok"
        except Exception as e:
            ev["drive"] = str(e)[:300]
        ev["atSide1"] = [{k: (units(gc).get(zombie_gm2) or {}).get(k) for k in ("tu", "direction", "coop", "hasAI")}
                         for gc in (host, client)]
        d2 = ((units(client).get(zombie_gm2) or {}).get("direction", 0) + 2) % 8
        t = OU.partner_turn(host, client, zombie_gm2, d2, ev.setdefault("cmd", {"toDir": d2}))
        c_ok, c_txt = OU.ctx_cell(t["newCtx"], "intent", "turn", zombie_gm2)
        sides = [OU.side_turn(gc)[0] for gc in (host, client)]
        cells["gm2_zombie-cmd"] = (ev["drive"] == "ok" and c_ok and t["dirs"] == [d2, d2]
                                   and t["lastDeny"] == t["lastDeny0"],
                                   f"side change to 1: {ev['drive']} (sides {sides}); {c_txt}; gm2_zombie "
                                   f"direction host/partner {t['dirs']} (want {d2} on both); partner lastDeny "
                                   f"{t['lastDeny0']} -> {t['lastDeny']} (want unchanged)")
    cells["gm2_zombie-common"] = G3F.common(host, client, crash0)
    return cells, ev


def run_gm2_boot():
    host = GameClient("host", None, make_user_dir("pvp_spawn_seat_gm2_host"))
    client = GameClient("client", None, make_user_dir("pvp_spawn_seat_gm2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("gm2", lambda: BER.boot_pvp(host, client, GM2_KEY), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("gm2", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all((("gm2_zombie", GM2_ORDER),), "boot (setup failure, see the CAPTURE gm2 line)")
        try:
            st = stage_gm2(host, client)
        except G3F.Miss:
            return G3F.fail_all((("gm2_zombie", GM2_ORDER),), "staging (see the CAPTURE gm2_zombie staging line)")
        return G3F.run_row("gm2_zombie", GM2_ORDER, lambda: row_gm2_zombie(host, client, crash0, st))
    finally:
        G3F.shut(host, client)


# ===================== gm3 boot =====================


def stage_gm3(host, client):
    m, ev = (host, client), {}
    ev["pistol"] = G3F.guarded("gm3_zombie staging", lambda: OU.give(host, client, A_ID, "STR_PLASMA_PISTOL",
                                                                     "STR_PLASMA_PISTOL_CLIP").get("weaponId"), m)
    ev["X"] = G3F.guarded("gm3_zombie staging", lambda: OU.tele(host, client, X, STAGE_X, X_DIR, "gm3 victim")
                          .get("to"), m)
    ev["A"] = G3F.guarded("gm3_zombie staging", lambda: OU.tele(host, client, A_ID, STAGE_A, A_DIR, "gm3 shooter")
                          .get("to"), m)
    ev["spawn"] = G3F.guarded("gm3_zombie staging",
                              lambda: OU.spawn_staging(host, client, X, ZOMBIE, FACTION_HOSTILE).get("spawnUnit"), m)
    return ev


def row_gm3_zombie(host, client, crash0, st):
    cells, ev = {}, {"staging": st}
    zombie_gm3, new, spawns = OU.convert(host, client, A_ID, GM3_FLOOR, GM3_SEED, ev)
    cells["gm3_zombie-spawn"] = OU.spawn_cell(new, A_ID, spawns, zombie_gm3, X, host, client, WANT_ZOMBIE)
    if not cells["gm3_zombie-spawn"][0]:
        OU.not_reached(cells, ("gm3_zombie-seat", "gm3_zombie-ai", "gm3_zombie-sel", "gm3_zombie-walk",
                               "gm3_zombie-deny"), "gm3_zombie-spawn failed")
    else:
        cells["gm3_zombie-seat"] = OU.both_fields(host, client, zombie_gm3, "coop", 0)
        cells["gm3_zombie-ai"] = OU.both_fields(host, client, zombie_gm3, "hasAI", False)
        ev["gm3_zombie"] = [{k: (units(gc).get(zombie_gm3) or {}).get(k) for k in ("tu", "direction", "x", "y", "z")}
                            for gc in (host, client)]
        ev["tu"] = both(host, client, {"cmd": "battle_set_unit_state", "unit": zombie_gm3, "tu": ZOMBIE_TU},
                        ("tu",)).get("tu")
        cells["gm3_zombie-sel"] = OU.tab_then_click(host, zombie_gm3, ev.setdefault("sel", {}))
        if not cells["gm3_zombie-sel"][0]:
            G3F.capture("gm3_zombie sel", cells["gm3_zombie-sel"][1], (host, client))
            OU.not_reached(cells, ("gm3_zombie-walk",), "gm3_zombie-sel failed")
        else:
            cells["gm3_zombie-walk"] = OU.host_walk(host, client, zombie_gm3, ZOMBIE_DEST, ev.setdefault("walk", {}))
        to = ((units(client).get(zombie_gm3) or {}).get("direction", 0) + 2) % 8
        cells["gm3_zombie-deny"] = OU.deny_cell(OU.partner_turn(host, client, zombie_gm3, to,
                                                                ev.setdefault("deny", {"toDir": to})), zombie_gm3)
    cells["gm3_zombie-common"] = G3F.common(host, client, crash0)
    return cells, ev


def run_gm3_boot():
    host = GameClient("host", None, make_user_dir("pvp_spawn_seat_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_spawn_seat_gm3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, GM3_KEY, "gm3")
            G3F.guarded("gm3", lambda: G3F.reactions_zero(host, client), m)

            def to_side1():
                client.ok({"cmd": "battle_action", "action": "end_turn_button"})
                drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
                session.wait_host_idle(host, client, timeout=STEP_S)
                st = [OU.side_turn(gc) for gc in m]
                assert boot["lobbyGamemode"] == 3 and st == [(1, 1), (1, 1)], (
                    f"lobby gamemode {boot['lobbyGamemode']} (want 3); (side, turn) host/partner {st} (want (1, 1))")
            G3F.guarded("gm3", to_side1, m)
        except G3F.Miss:
            return G3F.fail_all((("gm3_zombie", GM3_ORDER),), "boot (setup failure, see the CAPTURE gm3 line)")
        try:
            st = stage_gm3(host, client)
        except G3F.Miss:
            return G3F.fail_all((("gm3_zombie", GM3_ORDER),), "staging (see the CAPTURE gm3_zombie staging line)")
        return G3F.run_row("gm3_zombie", GM3_ORDER, lambda: row_gm3_zombie(host, client, crash0, st))
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_gm2_boot()
    fails += run_gm3_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_spawn_seat: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
