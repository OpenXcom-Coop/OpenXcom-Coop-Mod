"""PvP hidden movement, gm2 (the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0): off its
own side a PvP player sees vanilla's HIDDEN MOVEMENT screen, lifted only while an opponent unit its side sees acts
(off-turn, the hidden-movement screen shows except where the player's own units have line of sight).

Probe polarity: battle_state.hiddenMovementShown TRUE = the map is drawn; FALSE = the HIDDEN MOVEMENT screen is shown.
The sampler: from right after the press, every POLL_S s, the watching machine's hiddenMovementShown, until
the order's host context has closed (host free) AND the watching client applied that context's bt_action_end (or, for
the host, the chain is idle), then TAIL_S s more. A window that never closes (bounded) fails the row's sample cells.

Boot (key 48956, dirs pvp_hidden_move_host / _client): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every
live unit's reactions 0, RM.TILES (SEEN_WALK_DEST, UNSEEN_WALK_DEST, ALIEN_WALK_DEST, UNSEEN_TILE checked open ground),
the host's END TURN -> side 1 turn 1, the client's END TURN -> side 0 turn 2. Host orders are REAL-UI orders
(tab_select, the walk click; the snap through the right-hand box, key, HOME, set_seed, one map_tile_click); the
client's order is an intent (session.send_walk).
  alien_offturn_screen  off its own side the alien player sees the screen (side 0 turn 2, the client idle).
      alien_offturn_screen-screen (the client's hiddenMovementShown False; its selectedId printed).
  seen_walk  it sees an X-COM soldier its side sees walk: the host's real-UI walk of 9 to SEEN_WALK_DEST (two tiles,
      in A's sight). seen_walk-during (>= 1 client sample True before the client applied the walk's bt_action_end),
      seen_walk-after (every client sample False from LAG_S s after that apply).
  unseen_walk  it does not see an unseen X-COM soldier walk: the host's real-UI walk of 13 to UNSEEN_WALK_DEST.
      unseen_walk-hidden (every client sample False).
  unseen_shot  an X-COM shot no alien sees keeps its screen: 13's rifle + TU (give_both); the distance precondition
      (every tile of the segment 13 -> UNSEEN_TILE farther than the max view distance from every live hostile unit,
      else the row fails "staging"); host set_seed SHOT_SEED; the host's real-UI SNAP of 13 at UNSEEN_TILE.
      unseen_shot-shot (one new host context {host, shoot, 13}), unseen_shot-hidden (every client sample False).
  xcom_sees_alien_walk  the X-COM host sees the alien it sees walk: the host's END TURN -> side 1 turn 2; A in the
      host's spotted (else "staging"); the client's send_walk(A, ALIEN_WALK_DEST). xcom_sees_alien_walk-during (>= 1
      host sample True before the host chain closed), xcom_sees_alien_walk-after (every host sample False from LAG_S s
      after it closed). xcom_sees_alien_walk is the last row.
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's crash
folder.
Without the fix, alien_offturn_screen-screen, seen_walk-after, unseen_walk-hidden, unseen_shot-hidden and
xcom_sees_alien_walk-during FAIL; every other cell passes. One EVIDENCE line per row, one PASS/FAIL line per cell, then
the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row
"boot"; a staging step past its bound fails the rows that need it "staging". Test-command pairs go to the client first;
ids come from test-command replies. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_hidden_move.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_pvp_camera as CAM  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk  # noqa: E402
from test_client_shoot import new_contexts, set_tu_both  # noqa: E402
from test_host_combat import evs_since  # noqa: E402

KEY = "48956"
A_ID = RM.A_ID                    # 1000000: the only alien (STR_SECTOID_SOLDIER), the client's seat 1
S9, U13 = 9, 13
# 9 (18,6,0) two tiles SW, inside A's view sector (a one-tile walk leaves no window)
SEEN_WALK_DEST = (16, 8, 0)
UNSEEN_WALK_DEST = (31, 33, 0)    # 13 (33,33,0) two tiles W, out of A's sight
ALIEN_WALK_DEST = (15, 4, 0)      # A (15,2,0) two tiles S, inside 8's view sector
UNSEEN_TILE = CAM.UNSEEN_TILE     # (33,30,0): 13 and the tile out of A's sight
SHOT_SEED = 1
POLL_S, TAIL_S, LAG_S = 0.1, 2.0, 0.5
STEP_S = 30
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("alien_offturn_screen", ("alien_offturn_screen-screen", "alien_offturn_screen-common")),
        ("seen_walk", ("seen_walk-during", "seen_walk-after", "seen_walk-common")),
        ("unseen_walk", ("unseen_walk-hidden", "unseen_walk-common")),
        ("unseen_shot", ("unseen_shot-shot", "unseen_shot-hidden", "unseen_shot-common")),
        ("xcom_sees_alien_walk", ("xcom_sees_alien_walk-during", "xcom_sees_alien_walk-after",
                                  "xcom_sees_alien_walk-common")))

units, pos, es, ctxs, cv = G3F.units, G3F.pos, RM.es, RM.ctxs, RM.cv


# ===================== shared helpers (test_pvp_hidden_move_gm3 imports them) =====================


def sample_order(watch, host, ctx0, seq0, origin, kind, actor):
    """Poll `watch`'s hiddenMovementShown every POLL_S s from now (right after the press) until the host
    context {origin, kind, actor} closed with the host free AND, for a client watcher, the client applied that context's
    bt_action_end; then TAIL_S s more. Returns {samples [(t, hm, sel)], tEnd, endSeq, ghostAtEnd, ctx}; tEnd None = the
    window never closed within STEP_S."""
    t0, samples = time.time(), []
    t_end = end_seq = ctx = gq = None
    while True:
        a = time.time()
        b, e = battle_state(watch), event_state(watch)
        t = round(a - t0, 2)
        samples.append((t, b.get("hiddenMovementShown"), b.get("selectedId")))
        if t_end is None:
            he = e if watch is host else event_state(host)
            hit = [c for c in new_contexts(ctx0, he.get("closedContexts"))
                   if (c.get("origin"), c.get("kind"), c.get("actorId")) == (origin, kind, actor)]
            if hit and he.get("busyOwnerSeat") == -1:
                ctx = cv(hit[0])
                if watch is host:
                    t_end = t
                else:
                    if end_seq is None:
                        end_seq = next((x["seq"] for x in evs_since(host, seq0)
                                        if x["kind"] == "bt_action_end" and x["actionId"] == ctx["actionId"]), None)
                    if end_seq is not None and (e.get("lastSeqApplied") or 0) >= end_seq:
                        t_end, gq = t, e.get("ghostQueueDepth")
        elif t >= t_end + TAIL_S:
            break
        if t > STEP_S:
            break
        time.sleep(max(0.0, POLL_S - (time.time() - a)))
    return {"samples": samples, "tEnd": t_end, "endSeq": end_seq, "ghostAtEnd": gq, "ctx": ctx}


def hm_of(res, lo=None, hi=None):
    """The (t, hiddenMovementShown) samples with lo <= t < hi."""
    return [(t, v) for t, v, _s in res["samples"] if (lo is None or t >= lo) and (hi is None or t < hi)]


def fmt(samples):
    return " ".join(f"{t:.2f}{'T' if v is True else 'F' if v is False else '?'}" for t, v in samples) or "none"


def no_window(res):
    return None if res["tEnd"] is not None else \
        f"the order's window never closed within {STEP_S} s (context {res['ctx']}, end seq {res['endSeq']})"


def during_cell(res, who, what):
    w = no_window(res)
    d = [] if w else hm_of(res, hi=res["tEnd"])
    return (not w and any(v is True for _t, v in d),
            w or f"{who} hiddenMovementShown before {what} (t < {res['tEnd']} s): {fmt(d)} (want >= 1 True)")


def after_cell(res, who, what):
    w = no_window(res)
    a = [] if w else hm_of(res, lo=res["tEnd"] + LAG_S)
    return (not w and bool(a) and all(v is False for _t, v in a),
            w or f"{who} hiddenMovementShown from {LAG_S} s after {what} (t >= {res['tEnd'] + LAG_S:.2f} s): {fmt(a)} "
                 f"(want every one False)")


def hidden_cell(res, who):
    w = no_window(res)
    s = hm_of(res)
    return (not w and bool(s) and all(v is False for _t, v in s),
            w or f"{who} hiddenMovementShown from the press to {TAIL_S} s after the order: {fmt(s)} (want every one False)")


def res_ev(res):
    return {"ctx": res["ctx"], "tEnd": res["tEnd"], "endSeq": res["endSeq"], "ghostAtEnd": res["ghostAtEnd"],
            "n": len(res["samples"]), "sel": sorted({str(s) for _t, _v, s in res["samples"]}),
            "samples": fmt(hm_of(res))}


def idle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]


def screen_cell(gc, who):
    b = battle_state(gc)
    hm, sel = b.get("hiddenMovementShown"), b.get("selectedId")
    return (hm is False, f"{who} hiddenMovementShown {hm} (want False: the HIDDEN MOVEMENT screen); its selectedId {sel}"), \
        {"hm": hm, "sel": sel, "side": b.get("side"), "turn": b.get("turn"), "top": G3F.top(gc)}


def snap_pre(host, client, shooter, tile, ev):
    """The shooter's rifle (ids from the reply) + TU on both, then the distance precondition (a miss raises: the row's
    cells fail "staging")."""
    g = RM.give_both(host, client, shooter, CAM.RIFLE, CAM.CLIP)
    ev["rifle"] = (g.get("weaponId"), g.get("ammoId"))
    ev["tu"] = set_tu_both(host, client, shooter, CAM.TU_MAX)
    ok, txt = CAM.far_pre(host, shooter, tile, ev)
    if not ok:
        raise AssertionError(f"staging: {txt}")


# ===================== rows =====================


def row_alien_offturn_screen(host, client, crash0):
    cells = {}
    cells["alien_offturn_screen-screen"], ev = screen_cell(client, "client")
    ev["host"] = screen_cell(host, "host")[1]
    cells["alien_offturn_screen-common"] = G3F.common(host, client, crash0)
    return cells, ev


def host_walk_rows(host, client, crash0, uid, dest, ev):
    """tab_select(host, uid); the host's real-UI walk of uid to dest; the CLIENT's samples."""
    ev["tab"] = tab_select(host, uid)
    assert battle_state(host).get("selectedId") == uid, f"host selectedId {battle_state(host).get('selectedId')} " \
                                                        f"(want {uid})"
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    real_click_walk(host, dest)
    res = sample_order(client, host, ctx0, seq0, "host", "walk", uid)
    idle(host, client, ev)
    ev.update(res_ev(res), at=[pos(host, uid), pos(client, uid)], HU=CAM.hu(host))
    return res


def row_seen_walk(host, client, crash0):
    ev, cells = {}, {}
    res = host_walk_rows(host, client, crash0, S9, SEEN_WALK_DEST, ev)
    cells["seen_walk-during"] = during_cell(res, "client", "it applied the walk's bt_action_end")
    cells["seen_walk-after"] = after_cell(res, "client", "that apply")
    cells["seen_walk-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_unseen_walk(host, client, crash0):
    ev, cells = {}, {}
    res = host_walk_rows(host, client, crash0, U13, UNSEEN_WALK_DEST, ev)
    cells["unseen_walk-hidden"] = hidden_cell(res, "client")
    cells["unseen_walk-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_unseen_shot(host, client, crash0):
    ev, cells = {}, {}
    snap_pre(host, client, U13, UNSEEN_TILE, ev)
    CAM.hand_key(host, U13, CAM.KEY_SNAP, CAM.RIFLE_ROWS, CAM.CT_AIM, ev)
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    CAM.click_tile(host, UNSEEN_TILE, SHOT_SEED, ev)
    res = sample_order(client, host, ctx0, seq0, "host", "shoot", U13)
    idle(host, client, ev)
    new = new_contexts(ctx0, ctxs(host))
    ev.update(res_ev(res), newCtx=[cv(c) for c in new],
              chain=[(e["seq"], e["kind"]) for e in evs_since(host, seq0)])
    cells["unseen_shot-shot"] = (RM.ctx_ok(new, "host", "shoot", U13),
                        f"new host contexts {ev['newCtx']} (want one {{host, shoot, {U13}}})")
    cells["unseen_shot-hidden"] = hidden_cell(res, "client")
    cells["unseen_shot-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_xcom_sees_alien_walk(host, client, crash0):
    ev, cells = {"side": {}}, {}
    RM.side_change(host, client, host, FACTION_HOSTILE, 2, ev["side"])
    sp = ev["spotted"] = battle_state(host).get("spotted")
    if A_ID not in (sp or []):
        raise AssertionError(f"staging: X-COM's spotted {sp} (want {A_ID} in it)")
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    sent0 = dict(es(client, "coopIntentsSent") or {})
    ev["resp"] = session.send_walk(client, A_ID, ALIEN_WALK_DEST)
    res = sample_order(host, host, ctx0, seq0, "intent", "walk", A_ID)
    idle(host, client, ev)
    ev.update(res_ev(res), at=[pos(host, A_ID), pos(client, A_ID)],
              sent=(es(client, "coopIntentsSent") or {}).get("walk", 0) - sent0.get("walk", 0))
    cells["xcom_sees_alien_walk-during"] = during_cell(res, "host", "the host chain closed")
    cells["xcom_sees_alien_walk-after"] = after_cell(res, "host", "it closed")
    cells["xcom_sees_alien_walk-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def stage(host, client):
    m, ev = (host, client), {}
    ev["placed"] = RM.stage_tiles(host, client, RM.TILES,
                                  (SEEN_WALK_DEST, UNSEEN_WALK_DEST, ALIEN_WALK_DEST, UNSEEN_TILE))
    sv = ev["settle"] = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_HOSTILE, 1, sv.setdefault("a", {})), m)
    G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_PLAYER, 2, sv.setdefault("b", {})), m)
    ev["HU"] = CAM.hu(host)
    ev["hash"] = G3F.hash_now(host, client)
    return ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_hidden_move_host"))
    client = GameClient("client", None, make_user_dir("pvp_hidden_move_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("boot", lambda: BER.boot_pvp(host, client, KEY), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("alien_offturn_screen", rows["alien_offturn_screen"],
                            lambda: row_alien_offturn_screen(host, client, crash0))
        fails += G3F.run_row("seen_walk", rows["seen_walk"], lambda: row_seen_walk(host, client, crash0))
        fails += G3F.run_row("unseen_walk", rows["unseen_walk"], lambda: row_unseen_walk(host, client, crash0))
        fails += G3F.run_row("unseen_shot", rows["unseen_shot"], lambda: row_unseen_shot(host, client, crash0))
        fails += G3F.run_row("xcom_sees_alien_walk", rows["xcom_sees_alien_walk"],
                             lambda: row_xcom_sees_alien_walk(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_hidden_move: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
