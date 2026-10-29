"""test_battle_gift_stage.py: a tank the host gave and a soldier the client gave keep their seats into stage 2 of a
multi-stage mission (a battle gift lasts until the mission ends). One boot: classic co-op on the stage test mod
Coop_MultiStage_Test (both machines), lobby key 48648, dirs battle_gift_stage_host / battle_gift_stage_client.

The boot is test_multistage_end.boot_classic (raw.bring_up_lobby, drive_to_battlescape on STR_COOP_MULTISTAGE_TEST with
set_seed 1 right before newbattle_ok), copied with the lobby key and a pre_seat hook (test_battle_gift's boot: the
Skyranger crew cut to C1 8 / C2 9 (seat 1) and H 10 (seat 0) plus one STR_TANK_CANNON,
test_battle_gift_keep.pre_seat_hook) as parameters; the pins (MAP_FP, the seats with TANK 1000000, the stage-1 alien
1000001) are the same on two capture boots; MSE's mod and deployment lines on both logs; pin_ai_neutral; hash clean.
  gifts_survive_stage  the host gives TANK to the client and the client gives C1 to the host (the battle_gift test
      command), then MSE's stage change (stage guards, kill_all, close_end_turn, entry_cells on
      STR_COOP_MULTISTAGE_TEST_P2, run_spine): gifts_land (precondition: TANK coop 1, C1 coop 0 on both),
      stage2_entered (precondition: the stage cells pass; both turn 1 on _P2, battleId equal and above stage 1's b1),
      seats_kept (in stage 2 on both: TANK present with coop 1, C1 present with coop 0), client_commands_tank (the
      client's turn of TANK admitted), stage_common.
The stage change runs the battle-start seat pass again; a given unit keeps its live seat instead of the pass's default
(the host, for the ownerless tank). Each receiver presses OK on its gift notice (EVIDENCE).

"The order lands" = the unit's coop is the target on both machines within STEP_S. "Admitted" = one new host context
{intent, turn, TANK} and TANK faces the new direction on both. One EVIDENCE line, then one PASS/FAIL line per cell, then
the row verdict. A boot step past its bound prints ONE CAPTURE line and fails the row "boot"; a cell whose precondition
failed FAILs "not reached". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come
from probes. No skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_battle_gift_stage.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import assert_hash_clean  # noqa: E402
import repro_atom_walk as RAW  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_battle_gift as GF  # noqa: E402
import test_battle_gift_keep as KEEP  # noqa: E402
import test_multistage as MS  # noqa: E402
import test_multistage_end as MSE  # noqa: E402

KEY = "48648"
STEP_S = 30                               # every bounded wait (measured: steps <= 3 s; MSE's ENTRY_S bounds the entry)
SEED = MSE.SEED_C                         # 1, right before newbattle_ok
MISSION_1, MISSION_2 = MSE.MISSION_C1, MSE.MISSION_C2
MAP_FP = 2.509715288832488e+18            # stage 1, both machines, on two capture boots
TANK, C1, C2, H = GF.TANK, GF.C1, GF.C2, GF.H
SEATS = {TANK: 0, C1: 1, C2: 1, H: 0}     # X-COM id -> seat at bring-up (two capture boots)
ALIEN_1 = 1000001                         # the stage-1 alien (two capture boots)
ROWS = (("gifts_survive_stage", ("gifts_land", "stage2_entered", "seats_kept", "client_commands_tank",
                                 "stage_common")),)

units = G3F.units
not_reached = OWN.not_reached


def bring_up(host, client, key):
    """test_multistage_end.boot_classic with the lobby key and the pre_seat hook as parameters, the pins, then MSE's
    mod / deployment check (boot_c)."""
    m, pre, seated = (host, client), {}, {}
    GF.guarded("boot", lambda: RAW.bring_up_lobby(host, client, key), m)
    GF.guarded("boot", lambda: session.drive_to_battlescape(
        host, client, seated, mission=MISSION_1, seat_count=2, pre_seat=KEEP.pre_seat_hook(pre),
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED})), m)
    crash0 = session._crash_log_snapshot()
    hb, cb = MSE.bview(host), MSE.bview(client)
    mv = {gc.name: MSE.mod_view(gc) for gc in m}
    view = {"kept": pre.get("kept"), "seated": seated.get("soldierIds"), "vehicles": pre.get("vehicles"),
            "mapFp": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
            "start": [(b.get("side"), b.get("turn"), b.get("missionType")) for b in (hb, cb)],
            "seats": [hb.get("xcom"), cb.get("xcom")], "aliens": [hb.get("aliens"), cb.get("aliens")],
            "mod": {n: (MSE.MOD_ACTIVE_LINE in v["active"], v["invalid"], bool(v["deployment"])) for n, v in mv.items()}}
    want = {"kept": GF.KEPT, "seated": [C1, C2], "vehicles": {GF.TANK_ITEM: 1}, "mapFp": [MAP_FP, MAP_FP],
            "start": [(0, 1, MISSION_1)] * 2, "seats": [SEATS, SEATS], "aliens": [[ALIEN_1], [ALIEN_1]],
            "mod": {"host": (True, [], True), "client": (True, [], True)}}

    def pins():
        assert view == want, f"boot pins {view} (want {want})"
    GF.guarded("boot", pins, m)
    pinned = GF.guarded("boot", lambda: session.pin_ai_neutral(host, client, tag="test_battle_gift_stage"), m)

    def pinned_ok():
        assert sorted(pinned) == [ALIEN_1], f"pin_ai_neutral pinned {pinned} (want [{ALIEN_1}])"
    GF.guarded("boot", pinned_ok, m)
    GF.guarded("boot", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    GF.guarded("boot", lambda: assert_hash_clean(host, client, full=True, what="boot"), m)
    return dict(view, pinned=pinned), crash0


def stage_entry(host, client, ctx):
    """MSE's stage change on the kill-all route (test_multistage_end's final-stage steps up to the stage-2 spine) and
    the stage-2 entry pins. Returns the failure list (empty = both machines on stage 2 turn 1)."""
    g = []
    MSE.stage_guards(host, client, ctx, g)
    ctx["killed"] = MSE.kill_all(host, client, [ALIEN_1], g, "stage 1")
    ctx["t_close"] = MSE.close_end_turn(host, client, g)
    ctx["hostStageAtClose"] = MSE.eview(host).get("stage")
    ctx["hostRcAtClose"] = MSE.rc(host)
    if g:
        return [f"pre-stage: {x}" for x in g]
    f = MSE.entry_cells(host, client, ctx, MISSION_2)
    if f:
        return f
    try:
        ctx["pressed"], ctx["spineS"] = MS.run_spine(host, client)
    except Exception as e:
        return [f"stage-2 spine: {MS.short(e, 500)}"]
    hb, cb = MSE.bview(host), MSE.bview(client)
    ctx["stage2"] = {"host": hb, "client": cb}
    for name, b in (("host", hb), ("client", cb)):
        if b.get("turn") != 1 or b.get("missionType") != MISSION_2:
            f.append(f"{name} turn / missionType {b.get('turn')} / {b.get('missionType')} (want 1 / {MISSION_2})")
    b2 = [hb.get("battleId"), cb.get("battleId")]
    if not (isinstance(b2[0], int) and b2[0] == b2[1] and b2[0] > (ctx.get("b1") or 0)):
        f.append(f"battleId host/client {b2} (want equal and > b1 {ctx.get('b1')})")
    return f


def row_gifts_survive_stage(host, client, crash0):
    cells, ev, ctx = {}, {"sel0": GF.sels(host, client)}, {}
    landed, miss = KEEP.gifts_in_order([(host, TANK, 1), (client, C1, 0)], host, client, ev)
    got = [GF.coops(host, client, TANK), GF.coops(host, client, C1)]
    cells["gifts_land"] = (landed and got == [[1, 1], [0, 0]],
                           f"TANK / C1 coop host/client {got} (want [1, 1] / [0, 0], each landing within {STEP_S} s)"
                           f"{'; ' + miss if miss else ''}")
    if not cells["gifts_land"][0]:
        not_reached(cells, ("stage2_entered", "seats_kept", "client_commands_tank"), "gifts_land failed")
    else:
        ev["hash1"] = G3F.hash_now(host, client)
        try:
            f = stage_entry(host, client, ctx)
        except Exception as e:
            f = [f"stage steps: {MS.short(e, 600)}"]
        cells["stage2_entered"] = (not f, "; ".join(f) if f else (
            f"stage 1 killed {ctx.get('killed')}; the client's stage-2 briefing {ctx.get('clientBriefingS')} s after the "
            f"close; spine {ctx.get('spineS')} s; both turn 1 on {MISSION_2}; battleId b1 {ctx.get('b1')} -> "
            f"{(ctx.get('stage2') or {}).get('host', {}).get('battleId')}"))
        if f:
            not_reached(cells, ("seats_kept", "client_commands_tank"), "stage2_entered failed")
        else:
            want = [(GF.TANK_ITEM, False, 1), ("SOLDIER", False, 0)]
            got2 = [[((units(gc).get(i) or {}).get("type"), (units(gc).get(i) or {}).get("isOut"),
                      (units(gc).get(i) or {}).get("coop")) for i in (TANK, C1)] for gc in (host, client)]
            cells["seats_kept"] = (got2 == [want, want],
                                   f"stage 2 (type, isOut, coop) of TANK / C1 host {got2[0]}, client {got2[1]} (want "
                                   f"{want} on both)")
            cells["client_commands_tank"] = KEEP.turn_cell(host, client, TANK, ev)
    ev["stage"] = {k: v for k, v in ctx.items() if k != "t_close"}
    ev["sel"], ev["giftLines"] = GF.sels(host, client), GF.gift_lines(host)[-4:]
    cells["stage_common"] = G3F.common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("battle_gift_stage_host", mods=[MSE.MOD_DIR]))
    client = GameClient("client", None, make_user_dir("battle_gift_stage_client", mods=[MSE.MOD_DIR]))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client, KEY)
            print(f"[test_battle_gift_stage] boot: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            fails += G3F.run_row("gifts_survive_stage", rows["gifts_survive_stage"],
                                 lambda: row_gifts_survive_stage(host, client, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_stage: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
