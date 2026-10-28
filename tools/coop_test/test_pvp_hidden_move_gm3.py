"""R5-U1 S-D rows H5, H6, H9, H7 (boot D3, gm3: the HOST plays the aliens, seat 0; the partner the seven X-COM soldiers,
seat 1): off its own side a PvP player sees vanilla's HIDDEN MOVEMENT screen, lifted only while an opponent unit its side
sees acts (owner PvP model ruling "Off-turn: hidden-movement screen except where own units have LOS"; QU1-3 (a)).

Spec: docs repo rewrite/prompts/r5u1_pvp_fog_camera.md section (f) test_pvp_hidden_move_gm3.py, with the orchestrator
rulings AMENDMENT U1-1 (here A-4: row H9, an X-COM shot no alien sees keeps the alien host's screen, a guard) and R-U1-SC-1
(H5 re-measured on a base holding W2-H36).
Constants: rewrite/r5u1-task0/sd/CONSTANTS.md (TASK 0 boots Dh, Di; every pin equal).

Probe polarity and the sampler: test_pvp_hidden_move (TRUE = the map is drawn, FALSE = the HIDDEN MOVEMENT screen).

Boot D3 (key 48957, dirs r5u1_d3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT, map seed 1),
every live unit's reactions 0, RM.TILES (H2_DEST, K1_TILE checked open ground) at side 0 turn 1 (the partner's). Partner
orders are intents (session.send_walk, a battle_intent shoot lever).
  H5  off its own side the alien host sees the screen (a guard; side 0 turn 1, the host idle). H5-screen (the host's
      hiddenMovementShown False; its selectedId printed).
  H6  the alien host sees a seen X-COM soldier walk: the host camera staged on 9 (TASK 0: the lever staging leaves the
      host's sight lists stale at turn 1, so an off-screen walk runs in one frame); the partner's send_walk(9, H2_DEST).
      W2-U9 re-point (R-U9-0, F21063): since R5-U2 S-B (58a185218, QU1-6) the alien host animates a walk only while
      the aliens see the walker (an unseen enemy walks unanimated, as vanilla does for the player), and the staged
      tile (18,6,0) is not in the aliens' sight lists, so the 2-tile walk ran unanimated in 50 ms and closed before the
      first sample. Staging now starts the walk SEEN: the partner's one-tile send_walk(9, H6_START) first (a real
      step recomputes the aliens' sight; staging precondition: 9 in the host's HU before the press, else the row
      fails "staging"), then the 2-tile send_walk(9, H2_DEST) the cells sample. Every cell is unchanged.
      H6-during (>= 1 host sample True before the host chain closed), H6-after (every host sample False from LAG_S s
      after it closed).
  H9  an X-COM shot no alien sees keeps the alien host's screen (a guard: S-B's tile sight already keeps it): 13's rifle
      + TU (give_both); the distance precondition (else "staging"); host set_seed SEED_H9; the partner's lever snap of 13
      at K1_TILE. H9-shot (one new host context {intent, shoot, 13}; coopIntentsSent.shoot +1), H9-hidden (every host
      sample False).
  H7  off its own side the X-COM partner sees the screen: the partner's END TURN -> side 1 turn 1; the client idle.
      H7-screen (the client's hiddenMovementShown False; its selectedId printed). H7 is the last row.
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
RED at D1: H6-during, H7-screen; every other cell PASS (H5-screen and H9-hidden are guards). One EVIDENCE line per row,
one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE
CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it "staging". Lever
pairs go to the client first (F607); ids come from lever replies (S25). WV-D95: run in the foreground to completion.
WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_hidden_move_gm3.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_pvp_camera as K  # noqa: E402
import test_pvp_hidden_move as HM  # noqa: E402
from test_client_shoot import new_contexts, shoot_req  # noqa: E402

KEY = "48957"
A_ID = HM.A_ID                    # 1000000 on (15,2,0) facing 4: the host's alien (seat 0)
S9, U13 = 9, 13
H2_DEST, K1_TILE = HM.H2_DEST, HM.K1_TILE   # (16,8,0) two tiles from 9 inside A's view sector; (33,30,0)
# W2-U9 (F21063): 9's seen start tile, one step S of its staged (18,6,0) and two tiles from H2_DEST. Replacement rule:
# the nearest open-ground tile one step from (18,6,0) that is two tiles from H2_DEST and puts 9 in the host's HU.
H6_START = (18, 7, 0)
SEED_H9 = 1
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("H5", ("H5-screen", "H5-common")),
        ("H6", ("H6-during", "H6-after", "H6-common")),
        ("H9", ("H9-shot", "H9-hidden", "H9-common")),
        ("H7", ("H7-screen", "H7-common")))

pos, es, ctxs, cv = G3F.pos, RM.es, RM.ctxs, RM.cv


def sent_delta(client, sent0, kind):
    return (es(client, "coopIntentsSent") or {}).get(kind, 0) - (sent0 or {}).get(kind, 0)


# ===================== rows =====================


def row_h5(host, client, crash0):
    cells = {}
    cells["H5-screen"], ev = HM.screen_cell(host, "host")
    ev["client"] = HM.screen_cell(client, "client")[1]
    cells["H5-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_h6(host, client, crash0):
    ev, cells = {}, {}
    # W2-U9 (F21063): start the H6 walk on a tile the aliens see (a real one-tile step refreshes their sight lists).
    ev["pre"] = {"resp": session.send_walk(client, S9, H6_START)}
    ev["pre"]["done"] = G3F.walk_done(host, client, S9, H6_START, ev["pre"])
    ev["pre"].update(at=[pos(host, S9), pos(client, S9)], HU=K.hu(host))
    if not ev["pre"]["done"] or S9 not in ev["pre"]["HU"]:
        raise AssertionError(f"staging: 9's pre-walk to {H6_START} {ev['pre']} (want 9 on {H6_START} on both and in "
                             f"the host's HU before the H6 press)")
    ev["staged"] = HC.cam_offset(HC.stage_camera(host, pos(host, S9)))
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    sent0 = dict(es(client, "coopIntentsSent") or {})
    ev["resp"] = session.send_walk(client, S9, H2_DEST)
    res = HM.sample_order(host, host, ctx0, seq0, "intent", "walk", S9)
    HM.idle(host, client, ev)
    ev.update(HM.res_ev(res), at=[pos(host, S9), pos(client, S9)], HU=K.hu(host), sent=sent_delta(client, sent0, "walk"))
    cells["H6-during"] = HM.during_cell(res, "host", "the host chain closed")
    cells["H6-after"] = HM.after_cell(res, "host", "it closed")
    cells["H6-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_h9(host, client, crash0):
    ev, cells = {}, {}
    HM.lever_snap_pre(host, client, U13, K1_TILE, ev)
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    sent0 = dict(es(client, "coopIntentsSent") or {})
    host.ok({"cmd": "set_seed", "seed": SEED_H9})
    r = client.cmd(shoot_req(U13, "snap", ev["rifle"][0], ev["rifle"][1], K1_TILE))
    res = HM.sample_order(host, host, ctx0, seq0, "intent", "shoot", U13)
    HM.idle(host, client, ev)
    new = new_contexts(ctx0, ctxs(host))
    sent = sent_delta(client, sent0, "shoot")
    ev.update(HM.res_ev(res), iseq=r.get("iseq"), newCtx=[cv(c) for c in new], sent=sent,
              chain=[(e["seq"], e["kind"]) for e in HM.evs_since(host, seq0)])
    cells["H9-shot"] = (RM.ctx_ok(new, "intent", "shoot", U13) and sent == 1,
                        f"new host contexts {ev['newCtx']} (want one {{intent, shoot, {U13}}}); the partner's "
                        f"coopIntentsSent.shoot +{sent} (want +1)")
    cells["H9-hidden"] = HM.hidden_cell(res, "host")
    cells["H9-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_h7(host, client, crash0):
    side = {}
    RM.side_change(host, client, client, FACTION_HOSTILE, 1, side)
    cells = {}
    cells["H7-screen"], ev = HM.screen_cell(client, "client")
    ev.update(host=HM.screen_cell(host, "host")[1], side=side.get("turnSide"))
    cells["H7-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot D3 =====================


def boot_d3():
    host = GameClient("host", None, make_user_dir("r5u1_d3_host"))
    client = GameClient("client", None, make_user_dir("r5u1_d3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, KEY, "D3")
            G3F.guarded("D3", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE D3 line)")
        try:
            st = {"boot": boot, "placed": RM.stage_tiles(host, client, RM.TILES, (H2_DEST, K1_TILE, H6_START)),
                  "turnSide": [(G3F.bview(g).get("turn"), G3F.bview(g).get("side")) for g in m],
                  "hash": G3F.hash_now(host, client)}
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("H5", rows["H5"], lambda: row_h5(host, client, crash0))
        fails += G3F.run_row("H6", rows["H6"], lambda: row_h6(host, client, crash0))
        fails += G3F.run_row("H9", rows["H9"], lambda: row_h9(host, client, crash0))
        fails += G3F.run_row("H7", rows["H7"], lambda: row_h7(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_d3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_hidden_move_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
