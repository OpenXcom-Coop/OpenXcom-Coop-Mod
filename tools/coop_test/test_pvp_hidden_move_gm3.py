"""PvP hidden movement, gm3 (the HOST plays the aliens, seat 0; the partner the seven X-COM soldiers, seat 1): off its
own side a PvP player sees vanilla's HIDDEN MOVEMENT screen, lifted only while an opponent unit its side sees acts
(off-turn, the hidden-movement screen shows except where the player's own units have line of sight).

Probe polarity and the sampler: test_pvp_hidden_move (TRUE = the map is drawn, FALSE = the HIDDEN MOVEMENT screen).

Boot (key 48957, dirs pvp_hidden_move_gm3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT,
map seed 1), every live unit's reactions 0, RM.TILES (SEEN_WALK_DEST, UNSEEN_TILE checked open ground) at side 0 turn
1 (the partner's). Partner orders are intents (session.send_walk, a battle_intent shoot sent by test command).
  alien_offturn_screen  off its own side the alien host sees the screen (a guard; side 0 turn 1, the host idle).
      alien_offturn_screen-screen (the host's hiddenMovementShown False; its selectedId printed).
  seen_walk  the alien host sees a seen X-COM soldier walk: the host camera staged on 9 (the test-command staging
      leaves the host's sight lists stale at turn 1, so an off-screen walk runs in one frame). The alien host animates
      a walk only while the aliens see the walker (an unseen enemy walks unanimated, as vanilla does for the player),
      and the staged tile (18,6,0) is not in the aliens' sight lists, so a 2-tile walk from there runs unanimated in
      about 50 ms and closes before the first sample. The walk therefore starts SEEN: the partner's one-tile
      send_walk(9, SEEN_START) first (a real step recomputes the aliens' sight; staging precondition: 9 in the host's
      HU before the press, else the row fails "staging"), then the 2-tile send_walk(9, SEEN_WALK_DEST) the cells
      sample. seen_walk-during (>= 1 host sample True before the host chain closed), seen_walk-after (every host
      sample False from LAG_S s after it closed).
  unseen_shot  an X-COM shot no alien sees keeps the alien host's screen (a guard: the sight rule above already keeps
      it): 13's rifle + TU (give_both); the distance precondition (else "staging"); host set_seed SHOT_SEED; the
      partner's snap of 13 at UNSEEN_TILE. unseen_shot-shot (one new host context {intent, shoot, 13};
      coopIntentsSent.shoot +1), unseen_shot-hidden (every host sample False).
  xcom_offturn_screen  off its own side the X-COM partner sees the screen: the partner's END TURN -> side 1 turn 1;
      the client idle. xcom_offturn_screen-screen (the client's hiddenMovementShown False; its selectedId printed).
      xcom_offturn_screen is the last row.
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's crash
folder.
Without the fix, seen_walk-during and xcom_offturn_screen-screen FAIL; every other cell passes
(alien_offturn_screen-screen and unseen_shot-hidden are guards). One EVIDENCE line per row, one PASS/FAIL line per
cell, then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and
fails every row "boot"; a staging step past its bound fails the rows that need it "staging". Test-command pairs go to
the client first; ids come from test-command replies. ONE run is the result, no skip path; exit 0 only when every cell
passes, else 2.

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
import test_pvp_camera as CAM  # noqa: E402
import test_pvp_hidden_move as HM  # noqa: E402
from test_client_shoot import new_contexts, shoot_req  # noqa: E402

KEY = "48957"
A_ID = HM.A_ID                    # 1000000 on (15,2,0) facing 4: the host's alien (seat 0)
S9, U13 = 9, 13
# (16,8,0) two tiles from 9 inside A's view sector; (33,30,0)
SEEN_WALK_DEST, UNSEEN_TILE = HM.SEEN_WALK_DEST, HM.UNSEEN_TILE
# 9's seen start tile: open ground one step S of its staged (18,6,0), two tiles from SEEN_WALK_DEST, and 9 on it is in
# the host's HU.
SEEN_START = (18, 7, 0)
SHOT_SEED = 1
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("alien_offturn_screen", ("alien_offturn_screen-screen", "alien_offturn_screen-common")),
        ("seen_walk", ("seen_walk-during", "seen_walk-after", "seen_walk-common")),
        ("unseen_shot", ("unseen_shot-shot", "unseen_shot-hidden", "unseen_shot-common")),
        ("xcom_offturn_screen", ("xcom_offturn_screen-screen", "xcom_offturn_screen-common")))

pos, es, ctxs, cv = G3F.pos, RM.es, RM.ctxs, RM.cv


def sent_delta(client, sent0, kind):
    return (es(client, "coopIntentsSent") or {}).get(kind, 0) - (sent0 or {}).get(kind, 0)


# ===================== rows =====================


def row_alien_offturn_screen(host, client, crash0):
    cells = {}
    cells["alien_offturn_screen-screen"], ev = HM.screen_cell(host, "host")
    ev["client"] = HM.screen_cell(client, "client")[1]
    cells["alien_offturn_screen-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_seen_walk(host, client, crash0):
    ev, cells = {}, {}
    # start the walk on a tile the aliens see (a real one-tile step refreshes their sight lists).
    ev["pre"] = {"resp": session.send_walk(client, S9, SEEN_START)}
    ev["pre"]["done"] = G3F.walk_done(host, client, S9, SEEN_START, ev["pre"])
    ev["pre"].update(at=[pos(host, S9), pos(client, S9)], HU=CAM.hu(host))
    if not ev["pre"]["done"] or S9 not in ev["pre"]["HU"]:
        raise AssertionError(f"staging: 9's pre-walk to {SEEN_START} {ev['pre']} (want 9 on {SEEN_START} on both and "
                             f"in the host's HU before the seen_walk press)")
    ev["staged"] = HC.cam_offset(HC.stage_camera(host, pos(host, S9)))
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    sent0 = dict(es(client, "coopIntentsSent") or {})
    ev["resp"] = session.send_walk(client, S9, SEEN_WALK_DEST)
    res = HM.sample_order(host, host, ctx0, seq0, "intent", "walk", S9)
    HM.idle(host, client, ev)
    ev.update(HM.res_ev(res), at=[pos(host, S9), pos(client, S9)], HU=CAM.hu(host),
              sent=sent_delta(client, sent0, "walk"))
    cells["seen_walk-during"] = HM.during_cell(res, "host", "the host chain closed")
    cells["seen_walk-after"] = HM.after_cell(res, "host", "it closed")
    cells["seen_walk-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_unseen_shot(host, client, crash0):
    ev, cells = {}, {}
    HM.snap_pre(host, client, U13, UNSEEN_TILE, ev)
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    sent0 = dict(es(client, "coopIntentsSent") or {})
    host.ok({"cmd": "set_seed", "seed": SHOT_SEED})
    r = client.cmd(shoot_req(U13, "snap", ev["rifle"][0], ev["rifle"][1], UNSEEN_TILE))
    res = HM.sample_order(host, host, ctx0, seq0, "intent", "shoot", U13)
    HM.idle(host, client, ev)
    new = new_contexts(ctx0, ctxs(host))
    sent = sent_delta(client, sent0, "shoot")
    ev.update(HM.res_ev(res), iseq=r.get("iseq"), newCtx=[cv(c) for c in new], sent=sent,
              chain=[(e["seq"], e["kind"]) for e in HM.evs_since(host, seq0)])
    cells["unseen_shot-shot"] = (RM.ctx_ok(new, "intent", "shoot", U13) and sent == 1,
                        f"new host contexts {ev['newCtx']} (want one {{intent, shoot, {U13}}}); the partner's "
                        f"coopIntentsSent.shoot +{sent} (want +1)")
    cells["unseen_shot-hidden"] = HM.hidden_cell(res, "host")
    cells["unseen_shot-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_xcom_offturn_screen(host, client, crash0):
    side = {}
    RM.side_change(host, client, client, FACTION_HOSTILE, 1, side)
    cells = {}
    cells["xcom_offturn_screen-screen"], ev = HM.screen_cell(client, "client")
    ev.update(host=HM.screen_cell(host, "host")[1], side=side.get("turnSide"))
    cells["xcom_offturn_screen-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_hidden_move_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_hidden_move_gm3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, KEY, "boot")
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = {"boot": boot,
                  "placed": RM.stage_tiles(host, client, RM.TILES, (SEEN_WALK_DEST, UNSEEN_TILE, SEEN_START)),
                  "turnSide": [(G3F.bview(g).get("turn"), G3F.bview(g).get("side")) for g in m],
                  "hash": G3F.hash_now(host, client)}
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("alien_offturn_screen", rows["alien_offturn_screen"],
                            lambda: row_alien_offturn_screen(host, client, crash0))
        fails += G3F.run_row("seen_walk", rows["seen_walk"], lambda: row_seen_walk(host, client, crash0))
        fails += G3F.run_row("unseen_shot", rows["unseen_shot"], lambda: row_unseen_shot(host, client, crash0))
        fails += G3F.run_row("xcom_offturn_screen", rows["xcom_offturn_screen"],
                             lambda: row_xcom_offturn_screen(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_hidden_move_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
