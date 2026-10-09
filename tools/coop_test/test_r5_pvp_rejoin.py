"""R5-U9 rows R1-R4 and RX (boot R): in a gm2 PvP battle the alien player's game leaves and a fresh process rejoins;
it is still the alien player with the same units, orders its alien again, and wiping out X-COM afterwards ends the
battle with the alien seat as winner (POST-REWRITE-REVISIT row 10, owner D229; SPEC 16 pause and rejoin; D157 (a);
D219 (b) rides only the common full hash: its revealHostile bucket equal on the host and client2).

Spec: docs repo rewrite/prompts/r5u9_pvp_gm3_fixture.md section (f) test_r5_pvp_rejoin.py (QU9-1 (a), QU9-4 (a)).
Constants: rewrite/r5u9-task0/CONSTANTS.md (TASK 0 boot R).

Boot R (key 48675): test_w2_battle_end_rules.boot_e6's gm2 bring-up (the client on the Alien team: gamemode 2, MAP_FP,
authority, A on seat 1 hostile); census C0; every live unit's reactions 0 on both machines (client first); A on A_TILE.
  R1  the alien player's game leaves mid-battle (disconnect_to_menu): the host holds the battle under its reconnect
      dialog (code 62, no RESUME), peerAbsent true, still in the battle, still gamemode 2.
  R2  a fresh process (client2) rejoins: test_w2_rejoin_end_turn.stage_rejoin steps 3-9 (spawn, rejoin_skirmish, held on
      dialog 68, the host's RESUME offer with its Profile popups cleared), RESUME pressed through
      session.press_back_when_shown(codes=(62,)); both tops BattlescapeState, phase Active, the same battleId,
      peerAbsent false on both.
  R3  the alien seat survives: client2 gamemode 2, authority (seat 1, not hostSim); per unit (faction, coop) equal on the
      host and client2 and equal to C0; seat 1 holds ALIEN_IDS, all hostile.
  R4  the host's END TURN hands the turn to the aliens; client2 orders A to walk (battle_intent); the host runs it.
  RX  the host kills every X-COM soldier on the aliens' side and client2 presses END TURN: soldiersDown, the alien seat
      wins, both end on the host's debriefing, client2's display-only (D157 (a)).
Common cell after each row: every hash bucket EQUAL (host and client2; RX: right before the kill), desyncSeen false, no
new file in the lane crash folder. R1 has no hash pair (the partner left): desyncSeen and the crash folder only.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot"; a rejoin step past its bound fails R2-RX
"rejoin". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0
only when every cell passes, else 2.

Run:  python tools/coop_test/test_r5_pvp_rejoin.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_w2_battle_end_rules import boot_e6  # noqa: E402
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save, has,  # noqa: E402
                                         COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)
from test_w2_client_shoot import new_contexts  # noqa: E402
from test_r5_pvp_gm3 import (Miss, guarded, run_row, fail_all, shut, common, ctx_cell, walk_done, ending,  # noqa: E402
                             reactions_zero, tele_both, units, pos, es, top, stack, bview, A_ID, A_TILE, A_DIR, A_DEST,
                             ALIEN_IDS, XCOM_IDS, FACTION_PLAYER, FACTION_HOSTILE, STEP_S)

R_KEY = "48675"
GAMEMODE_PVP = 2
REJOIN_S = 120                    # each rejoin wait's bound (test_w2_rejoin_end_turn :196-209; TASK 0: 4.9 s in all)
EXPECT_RX = {"reason": "soldiersDown", "aborted": False, "inExitArea": 0, "verdicts": [(0, "lose"), (1, "win")],
             "tally": {"liveAliens": 1, "liveSoldiers": 0, "inExit": 0}}   # TASK 0 boot R
ROWS = (("R1", ("R1-pause", "R1-common")), ("R2", ("R2-back", "R2-common")), ("R3", ("R3-mode", "R3-seats", "R3-common")),
        ("R4", ("R4-ctx", "R4-pos", "R4-common")), ("RX", ("RX-kill", "RX-host", "RX-client", "RX-ends", "RX-common")))


def seats(gc):
    return {i: (u.get("faction"), u.get("coop")) for i, u in units(gc).items()}


def row_r1(host, client, crash0, ev):
    drop_client_mid_battle(host, client)
    d, hb, st = dialog(host), bview(host), stack(host)
    ha = hb.get("authority") or {}
    ev.update(dialog={k: d.get(k) for k in ("present", "code", "backVisible", "title")}, stack=st, host=hb)
    ds, crash = es(host, "desyncSeen"), sorted(session._crash_log_snapshot() - crash0)
    return {"R1-pause": (d.get("code") == COOP_DLG_WAIT_PLAYERS and d.get("backVisible") is False
                         and st[-1:] == ["CoopState"] and "BattlescapeState" in st and ha.get("peerAbsent") is True
                         and hb.get("inBattle") is True and hb.get("coopGamemode") == GAMEMODE_PVP,
                         f"host dialog code {d.get('code')} (want 62) backVisible {d.get('backVisible')} (want False), "
                         f"stack {st} (want CoopState over BattlescapeState), peerAbsent {ha.get('peerAbsent')} (want "
                         f"True), inBattle {hb.get('inBattle')} (want True), coopGamemode {hb.get('coopGamemode')} "
                         f"(want 2)"),
            "R1-common": (ds is False and not crash, f"common: host desyncSeen {ds} (want False); new crash files {crash} "
                                                     f"(want none); no hash pair (the partner left)")}, ev


def rejoin(host, client2, ev):
    """test_w2_rejoin_end_turn.stage_rejoin steps 3-9 (:179-218), the RESUME press through press_back_when_shown."""
    m = (host, client2)
    guarded("R rejoin", lambda: (client2.spawn(), client2.connect()), m)
    guarded("R rejoin", lambda: rejoin_skirmish(client2, R_KEY), m)

    def held():
        client2.wait_for("client2 back in the battle", lambda: in_battle_save(client2) or None, timeout=240)
        client2.wait_for("client2 held on dialog 68 over BattlescapeState",
                         lambda: (has(client2, "BattlescapeState")
                                  and dialog(client2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None,
                         timeout=60, interval=0.5)
        return {"code": dialog(client2).get("code"), "stack": stack(client2)}
    ev["held"] = guarded("R rejoin", held, m)

    def offered():
        def up():
            if session.has_state(host, "Profile"):        # the join's popup sits over the dialog (RET :193-194)
                return host.cmd({"cmd": "profile_ok"}) and None
            return dialog(host).get("backVisible") or None
        host.wait_for("host dialog offers RESUME", up, timeout=REJOIN_S, interval=0.5)
        d = dialog(host)
        assert d.get("code") == COOP_DLG_WAIT_PLAYERS and d.get("backText") == "RESUME", f"host dialog {d}"
        return {k: d.get(k) for k in ("code", "backText", "backVisible")}
    ev["offer"] = guarded("R rejoin", offered, m)
    ev["press"] = guarded("R rejoin", lambda: session.press_back_when_shown(host, "host RESUME",
                                                                            codes=(COOP_DLG_WAIT_PLAYERS,)), m)

    def back():
        for gc in m:
            gc.wait_for(f"{gc.name} top BattlescapeState", lambda gc=gc: (top(gc) == "BattlescapeState") or None,
                        timeout=REJOIN_S, interval=0.5)
        for gc in m:
            gc.wait_for(f"{gc.name} phase Active", lambda gc=gc: (battle_state(gc).get("phase") == "Active") or None,
                        timeout=REJOIN_S, interval=0.5)
        session.wait_host_idle(host, client2, timeout=STEP_S)
    guarded("R rejoin", back, m)


def row_r2(host, client2, bid0, crash0, ev):
    auth = [battle_state(gc).get("authority") or {} for gc in (host, client2)]
    tops, phases = [top(host), top(client2)], [battle_state(gc).get("phase") for gc in (host, client2)]
    bids, absent = [a.get("battleId") for a in auth], [a.get("peerAbsent") for a in auth]
    ev.update(authority=auth, tops=tops, phases=phases)
    return {"R2-back": (ev["held"]["code"] == COOP_DLG_CLIENT_RESUME_HOLD and tops == ["BattlescapeState"] * 2
                        and phases == ["Active"] * 2 and bids == [bid0, bid0] and absent == [False, False],
                        f"client2 held on {ev['held']['code']} before RESUME (want 68); tops {tops}, phases {phases} "
                        f"(want BattlescapeState / Active on both); battleId {bids} (want {bid0} on both); peerAbsent "
                        f"{absent} (want False on both)"),
            "R2-common": common(host, client2, crash0)}, ev


def row_r3(host, client2, c0, crash0):
    cb = bview(client2)
    ca = cb.get("authority") or {}
    sh, s2 = seats(host), seats(client2)
    seat1 = sorted(i for i, (_f, c) in sh.items() if c == 1)
    diff = {i: (c0.get(i), sh.get(i), s2.get(i)) for i in set(c0) | set(sh) | set(s2)
            if not c0.get(i) == sh.get(i) == s2.get(i)}
    return {"R3-mode": (cb.get("coopGamemode") == GAMEMODE_PVP and (ca.get("localSeat"), ca.get("hostSim")) == (1, False),
                        f"client2 coopGamemode {cb.get('coopGamemode')} (want 2), authority {ca} (want localSeat 1 "
                        f"hostSim false)"),
            "R3-seats": (not diff and seat1 == ALIEN_IDS and all(sh[i][0] == FACTION_HOSTILE for i in seat1),
                         f"(faction, coop) C0 / host / client2 differences {diff} (want none); seat 1 {seat1} factions "
                         f"{[sh[i][0] for i in seat1]} (want {ALIEN_IDS}, all {FACTION_HOSTILE})"),
            "R3-common": common(host, client2, crash0)}, {"client2": cb, "C0": c0, "host": sh}


def row_r4(host, client2, crash0):
    ev = {"reactions": reactions_zero(host, client2)}   # every live unit 0 on both before the walk (TASK 0: already 0)
    ev["endTurn"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    try:
        drive_side_change(host, client2, FACTION_HOSTILE, timeout=STEP_S)
        session.wait_host_idle(host, client2, timeout=STEP_S)
    except Exception as e:
        ev["sideError"] = str(e)[:300]
    b_ctx = es(host, "closedContexts") or []
    ev["walk"] = session.send_walk(client2, A_ID, A_DEST)
    walk_done(host, client2, A_ID, A_DEST, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    pa, sides = [pos(host, A_ID), pos(client2, A_ID)], [battle_state(gc).get("side") for gc in (host, client2)]
    ev.update(newCtx=new, lastDeny=es(client2, "lastDeny"))
    return {"R4-ctx": ctx_cell(new, "intent", A_ID),
            "R4-pos": (pa == [A_DEST, A_DEST] and sides == [1, 1],
                       f"A host/client2 {pa} (want {A_DEST} on both; {ev['walkS']} s), side {sides} (want 1 on both)"),
            "R4-common": common(host, client2, crash0)}, ev


def boot_r():
    host = GameClient("host", None, make_user_dir("r5u9_r_host"))
    client = GameClient("client", None, make_user_dir("r5u9_r_client"))
    client2 = GameClient("client2", None, make_user_dir("r5u9_r_client2"))
    rows = dict(ROWS)
    try:
        m = (host, client)
        try:
            boot = guarded("R", lambda: boot_e6(host, client, R_KEY), m)
            c0 = seats(host)
            guarded("R", lambda: reactions_zero(host, client), m)
            guarded("R", lambda: tele_both(host, client, A_ID, A_TILE, A_DIR), m)
            guarded("R", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
            crash0 = session._crash_log_snapshot()
        except Miss:
            return fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE R line)")
        bid0 = (battle_state(host).get("authority") or {}).get("battleId")
        fails = run_row("R1", rows["R1"], lambda: row_r1(host, client, crash0, {"boot": boot, "battleId": bid0,
                                                                                  "A": [pos(host, A_ID), pos(client, A_ID)]}))
        ev = {}
        try:
            rejoin(host, client2, ev)
        except Miss:
            return fails + fail_all(ROWS[1:], "rejoin (FIXTURE-STOP, see the CAPTURE R rejoin line)")
        fails += run_row("R2", rows["R2"], lambda: row_r2(host, client2, bid0, crash0, ev))
        fails += run_row("R3", rows["R3"], lambda: row_r3(host, client2, c0, crash0))
        fails += run_row("R4", rows["R4"], lambda: row_r4(host, client2, crash0))
        fails += run_row("RX", rows["RX"], lambda: ending("RX", host, client2, FACTION_PLAYER, XCOM_IDS, client2,
                                                          EXPECT_RX, crash0))
        return fails
    finally:
        shut(host, client, client2)


def main():
    t0 = time.time()
    fails = boot_r()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_pvp_rejoin: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
