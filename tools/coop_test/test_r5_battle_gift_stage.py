"""R5-U5 S-B row M1 (boot M; owner D235-VL4: a gift lasts until the mission ends): a tank the host gave and a soldier the
client gave keep their seats into stage 2 of a multi-stage mission. Boot M: classic co-op on the stage test mod
Coop_MultiStage_Test (both machines), lobby key 48648, dirs r5u5_m_host / r5u5_m_client.

Spec: docs repo rewrite/prompts/r5u5_battle_gift_order.md section (f) test_r5_battle_gift_stage.py (ORCHESTRATOR RULINGS
QU5-1 .. QU5-11 (a), QU5-10 (a); ruling R-U5-SB-1). Constants: rewrite/r5u5-task0/sb/CONSTANTS.md (boots Ma, Mb).

Boot M = test_w2_multistage_end.boot_classic (raw.bring_up_lobby, drive_to_battlescape on STR_COOP_MULTISTAGE_TEST with
set_seed 1 right before newbattle_ok), copied with the lobby key and a pre_seat hook (boot G's Skyranger crew cut to C1 8 /
C2 9 (seat 1) and H 10 (seat 0) plus one STR_TANK_CANNON, test_r5_battle_gift_keep.pre_seat_hook) as parameters (F10917);
the pins are TASK 0's (MAP_FP_M, the seats with TANK 1000000, the stage-1 alien 1000001); MSE's mod and deployment lines on
both logs; pin_ai_neutral; hash clean.
  M1  the host gives TANK to the client and the client gives C1 to the host (levers), then MSE's stage change (stage
      guards, kill_all, close_end_turn, entry_cells on STR_COOP_MULTISTAGE_TEST_P2, run_spine): M1-gifts (precondition:
      TANK coop 1, C1 coop 0 on both), M1-entry (precondition: the stage cells pass; both turn 1 on _P2, battleId equal
      and > b1), M1-seats (in stage 2 on both: TANK present with coop 1, C1 present with coop 0), M1-cmd (the client's
      turn of TANK admitted), M1-common.
Red at B1: M1-seats (TANK coop 0: the stage's seat pass re-seats an ownerless unit to the host, F12909) and M1-cmd
(not_your_unit). Every other cell PASS. Each receiver presses OK on its gift notice (EVIDENCE).

"The order lands" = the unit's coop is the target on both machines within STEP_S. "Admitted" = one new host context
{intent, turn, TANK} and TANK faces the new direction on both. One EVIDENCE line, then one PASS/FAIL line per cell, then
the row verdict. A boot step past its bound prints ONE CAPTURE line and fails the row "boot"; a cell whose precondition
failed FAILs "not reached". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come
from probes (S25). WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path;
exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_r5_battle_gift_stage.py
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
import test_r5_pvp_gm3 as G3F  # noqa: E402
import test_r5_ownerless_units as OWN  # noqa: E402
import test_r5_battle_gift as GF  # noqa: E402
import test_r5_battle_gift_keep as KEEP  # noqa: E402
import test_w2_multistage as MS  # noqa: E402
import test_w2_multistage_end as MSE  # noqa: E402

KEY = "48648"
STEP_S = 30                               # every bounded wait (TASK 0: each step <= 3 s; MSE's ENTRY_S bounds the entry)
SEED = MSE.SEED_C                         # 1, right before newbattle_ok
MISSION_1, MISSION_2 = MSE.MISSION_C1, MSE.MISSION_C2
MAP_FP_M = 2.509715288832488e+18          # stage 1, both machines (Ma, Mb)
TANK, C1, C2, H = GF.TANK, GF.C1, GF.C2, GF.H
SEATS_M = {TANK: 0, C1: 1, C2: 1, H: 0}   # X-COM id -> seat at bring-up (Ma, Mb)
ALIEN_1 = 1000001                         # the stage-1 alien (Ma, Mb)
ROWS = (("M1", ("M1-gifts", "M1-entry", "M1-seats", "M1-cmd", "M1-common")),)

units = G3F.units
not_reached = OWN.not_reached


def bring_up(host, client, key):
    """test_w2_multistage_end.boot_classic with the lobby key and the pre_seat hook as parameters (F10917), TASK 0's pins,
    then MSE's mod / deployment check (boot_c)."""
    m, pre, seated = (host, client), {}, {}
    GF.guarded("M", lambda: RAW.bring_up_lobby(host, client, key), m)
    GF.guarded("M", lambda: session.drive_to_battlescape(
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
    want = {"kept": GF.KEPT, "seated": [C1, C2], "vehicles": {GF.TANK_ITEM: 1}, "mapFp": [MAP_FP_M, MAP_FP_M],
            "start": [(0, 1, MISSION_1)] * 2, "seats": [SEATS_M, SEATS_M], "aliens": [[ALIEN_1], [ALIEN_1]],
            "mod": {"host": (True, [], True), "client": (True, [], True)}}

    def pins():
        assert view == want, f"boot M pins {view} (want {want})"
    GF.guarded("M", pins, m)
    pinned = GF.guarded("M", lambda: session.pin_ai_neutral(host, client, tag="r5u5"), m)

    def pinned_ok():
        assert sorted(pinned) == [ALIEN_1], f"pin_ai_neutral pinned {pinned} (want [{ALIEN_1}])"
    GF.guarded("M", pinned_ok, m)
    GF.guarded("M", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    GF.guarded("M", lambda: assert_hash_clean(host, client, full=True, what="boot M"), m)
    return dict(view, pinned=pinned), crash0


def stage_entry(host, client, ctx):
    """MSE's stage change on the kill-all route (ms3's steps up to the stage-2 spine) and the stage-2 entry pins. Returns
    the failure list (empty = both machines on stage 2 turn 1)."""
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


def row_m1(host, client, crash0):
    cells, ev, ctx = {}, {"sel0": GF.sels(host, client)}, {}
    landed, miss = KEEP.lever_gifts([(host, TANK, 1), (client, C1, 0)], host, client, ev)
    got = [GF.coops(host, client, TANK), GF.coops(host, client, C1)]
    cells["M1-gifts"] = (landed and got == [[1, 1], [0, 0]],
                         f"TANK / C1 coop host/client {got} (want [1, 1] / [0, 0], each landing within {STEP_S} s)"
                         f"{'; ' + miss if miss else ''}")
    if not cells["M1-gifts"][0]:
        not_reached(cells, ("M1-entry", "M1-seats", "M1-cmd"), "M1-gifts failed")
    else:
        ev["hash1"] = G3F.hash_now(host, client)
        try:
            f = stage_entry(host, client, ctx)
        except Exception as e:
            f = [f"stage steps: {MS.short(e, 600)}"]
        cells["M1-entry"] = (not f, "; ".join(f) if f else (
            f"stage 1 killed {ctx.get('killed')}; the client's stage-2 briefing {ctx.get('clientBriefingS')} s after the "
            f"close; spine {ctx.get('spineS')} s; both turn 1 on {MISSION_2}; battleId b1 {ctx.get('b1')} -> "
            f"{(ctx.get('stage2') or {}).get('host', {}).get('battleId')}"))
        if f:
            not_reached(cells, ("M1-seats", "M1-cmd"), "M1-entry failed")
        else:
            want = [(GF.TANK_ITEM, False, 1), ("SOLDIER", False, 0)]
            got2 = [[((units(gc).get(i) or {}).get("type"), (units(gc).get(i) or {}).get("isOut"),
                      (units(gc).get(i) or {}).get("coop")) for i in (TANK, C1)] for gc in (host, client)]
            cells["M1-seats"] = (got2 == [want, want],
                                 f"stage 2 (type, isOut, coop) of TANK / C1 host {got2[0]}, client {got2[1]} (want "
                                 f"{want} on both)")
            cells["M1-cmd"] = KEEP.turn_cell(host, client, TANK, ev)
    ev["stage"] = {k: v for k, v in ctx.items() if k != "t_close"}
    ev["sel"], ev["giftLines"] = GF.sels(host, client), GF.gift_lines(host)[-4:]
    cells["M1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u5_m_host", mods=[MSE.MOD_DIR]))
    client = GameClient("client", None, make_user_dir("r5u5_m_client", mods=[MSE.MOD_DIR]))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client, KEY)
            print(f"[r5u5] boot M: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE M line)")
        else:
            fails += G3F.run_row("M1", rows["M1"], lambda: row_m1(host, client, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_battle_gift_stage: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
