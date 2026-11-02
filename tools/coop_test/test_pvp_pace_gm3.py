"""PvP walk pace and HUD in gm3 (the HOST plays the aliens, seat 0; the partner the seven X-COM soldiers, seat 1): the
alien host's own alien walks animated on its screen, its HUD lists its own wounded alien and not X-COM's, and an X-COM
soldier its aliens do not see moves instantly on its screen, as hidden aliens do for X-COM; a seen X-COM soldier still
walks animated.

The ids and tiles below were measured equal on two boots without the fix. With OWN_WALK_DEST at (13,2,0) A ended
facing west, blind to 9, so seen_walk's premise failed: OWN_WALK_DEST is (16,4,0). Helpers: test_pvp_hud.py.

Boot (key 48882, dirs pvp_pace_gm3_host / _client): G3F.bring_up (gm3, STR_SMALL_SCOUT, map seed 1), every live
unit's reactions 0, PH.TILES (every X-COM unit facing PH.FACE_AWAY: A's tile and OWN_WALK_DEST outside each view
sector), the settle cycle (the partner's END TURN -> side 1 turn 1, the host's -> side 0 turn 2, the partner's ->
side 1 turn 2: the host's turn, A selected, A unseen by X-COM, A sees 8..11).
  own_walk  the alien host's own alien walks animated: HC.stage_camera(host, A tile); the host's real-UI walk of A to
      OWN_WALK_DEST
      own_walk-walk      one new host context {host, walk, A}; A on OWN_WALK_DEST on both
      own_walk-pre       the host's units[A].visible false before and after (precondition)
      own_walk-pace      WP(host, A) animated >= 1 and instant == 0   (without the fix: animated 0, instant >= 1)
  alien_hud  its HUD lists its own wounded alien, not X-COM's: A and 13 STAGE_WOUNDS (test commands, client first);
      the host's TAB to A
      alien_hud-own      A in HUD(host)      (without the fix: absent)
      alien_hud-opp      13 not in HUD(host) (without the fix: present); then wounds back to 0
  unseen_walk  an X-COM soldier its aliens do not see moves instantly on its screen: the host's END TURN -> side 0
      turn 3; HC.stage_camera(host, 13's tile); the partner's send_walk(13, UNSEEN_WALK_DEST)
      unseen_walk-walk   one new host context {intent, walk, 13}; 13 on UNSEEN_WALK_DEST on both
      unseen_walk-pre    13 not in HU before and after (precondition)
      unseen_walk-pace   WP(host, 13) instant >= 1 and animated == 0  (without the fix: animated >= 1)
  seen_walk  a seen X-COM soldier walks animated (control): HC.stage_camera(host, 9's tile); the partner's
      send_walk(9, SEEN_WALK_DEST)
      seen_walk-pace     9 in HU before and after; WP(host, 9) animated >= 1
      seen_walk is the last row.
WP(gc, id) = the event_state(gc).walkPace[id] delta over the walk (a test-only probe: UnitWalkBState's step starts,
animated or instant); HU = the host's union of visibleUnits over its live hostile units; HUD(host) =
battle_state(host).hudUnits.ids. Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false
on both, no new file in this harness slot's crash folder.

Without the fix, own_walk-pace, alien_hud-own, alien_hud-opp and unseen_walk-pace FAIL; every other cell passes
(seen_walk is a guard). One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs
after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past
its bound fails the rows that need it "staging". ONE run is the result, no skip path; exit 0 only when every cell
passes, else 2.

Run:  python tools/coop_test/test_pvp_pace_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
from session import battle_state  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_host_combat as HC  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_messages import STAGE_WOUNDS  # noqa: E402
import test_pvp_hud as PH  # noqa: E402

KEY = "48882"
A_ID, S9_ID, S13_ID = PH.A_ID, 9, 13
A_TILE = RM.TILES[A_ID][0]        # (15,2,0), facing 4
OWN_WALK_DEST = (16, 4, 0)        # two tiles, open ground, z 0, on the host's screen, outside every X-COM view sector;
                                  # A ends facing 3 and still sees 9 and 11 (measured on two boots)
UNSEEN_WALK_DEST = (31, 33, 0)    # 13 two tiles west, never in A's sight
SEEN_WALK_DEST = (17, 7, 0)       # 9 inside A's sight before and after (measured: HU [9, 11])
STEP_S = 30
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("own_walk", ("own_walk-walk", "own_walk-pre", "own_walk-pace", "own_walk-common")),
        ("alien_hud", ("alien_hud-own", "alien_hud-opp", "alien_hud-common")),
        ("unseen_walk", ("unseen_walk-walk", "unseen_walk-pre", "unseen_walk-pace", "unseen_walk-common")),
        ("seen_walk", ("seen_walk-pace", "seen_walk-common")))


def vis(gc, uid):
    return (G3F.units(gc).get(uid) or {}).get("visible")


def select_a(host):
    """The host holds A at side 1 turn 2 (measured: at once); else ONE TAB + tab_select(A). Returns evidence."""
    s0 = battle_state(host).get("selectedId")
    return {"sel0": s0} if s0 == A_ID else dict(PH.tab_to(host, A_ID), sel0=s0)


def walk_cells(new, origin, uid, dest, host, client):
    got = [G3F.pos(host, uid), G3F.pos(client, uid)]
    ok = RM.ctx_ok(new, origin, "walk", uid) and got == [dest, dest]
    return (ok, f"new host contexts {[RM.cv(c) for c in new]} (want exactly one {{{origin}, walk, {uid}}}); {uid} at "
                f"host/client {got} (want {dest} on both)")


def partner_walk(host, client, uid, dest, ev):
    """The partner's send_walk(uid, dest) (an intent), the walk settled on both; returns the new host contexts."""
    ctx0, prev = RM.ctxs(host), session.walk_action_id(host)
    ev["send"] = session.send_walk(client, uid, dest)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    RM.settle(host, client, ev)
    return new_contexts(ctx0, RM.ctxs(host))


# ===================== rows =====================


def row_own_walk(host, client, crash0):
    ev = {"select": select_a(host)}
    cam = HC.stage_camera(host, A_TILE)
    ev["camera"] = HC.cam_offset(cam)
    w0, v0 = PH.pace(host), vis(host, A_ID)
    new = RM.host_walk(host, client, A_ID, OWN_WALK_DEST, ev)
    w1, v1 = PH.pace(host), vis(host, A_ID)
    d = PH.pace_delta(w0, w1, A_ID)
    ev.update(newCtx=[RM.cv(c) for c in new], pace=d, walkPace=w1.get(str(A_ID)), A=PH.uview(host, [A_ID]),
              HU=PH.hu(host))
    return {"own_walk-walk": walk_cells(new, "host", A_ID, OWN_WALK_DEST, host, client),
            "own_walk-pre": (v0 is False and v1 is False, f"host units[{A_ID}].visible before/after {v0}/{v1} (want "
                                                          f"False/False: X-COM does not see A)"),
            "own_walk-pace": (d["animated"] >= 1 and d["instant"] == 0, f"WP(host, {A_ID}) animated +{d['animated']} "
                                                                        f"instant +{d['instant']} (want animated >= 1, "
                                                                        f"instant 0)"),
            "own_walk-common": G3F.common(host, client, crash0)}, ev


def row_alien_hud(host, client, crash0):
    ev, cells = {}, {}
    try:
        ev["staged"] = {"wA": PH.wounds_both(host, client, A_ID, STAGE_WOUNDS),
                        "w13": PH.wounds_both(host, client, S13_ID, STAGE_WOUNDS)}
        ev["tab"] = PH.tab_to(host, A_ID)
        ids, sel = PH.hud_ids(host), battle_state(host).get("selectedId")
        ev.update(hudHost=PH.hud(host), hudClient=PH.hud(client), sel=sel)
        pre = "" if ids is not None and sel == A_ID else f" (host hudUnits {PH.hud(host)!r}, selectedId {sel}: want " \
                                                         f"the probe and {A_ID})"
        ids = ids or []
        cells["alien_hud-own"] = (A_ID in ids and not pre, f"A ({A_ID}) in HUD(host) {ids}: {A_ID in ids} "
                                                           f"(want True){pre}")
        cells["alien_hud-opp"] = (S13_ID not in ids and not pre, f"13 (X-COM, wounded) in HUD(host) {ids}: "
                                                                 f"{S13_ID in ids} (want False){pre}")
    finally:
        PH.unstage(host, client, ev, (A_ID, S13_ID))
    cells["alien_hud-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_unseen_walk(host, client, crash0, side_ok, side_ev):
    ev = {"side": side_ev}
    if not side_ok:
        why = f"staging (the host's END TURN -> side 0 turn 3: {side_ev.get('sideError')})"
        cells = {n: (False, why) for n in ("unseen_walk-walk", "unseen_walk-pre", "unseen_walk-pace")}
        cells["unseen_walk-common"] = G3F.common(host, client, crash0)
        return cells, ev
    cam = HC.stage_camera(host, G3F.pos(host, S13_ID))
    ev["camera"] = HC.cam_offset(cam)
    hu0, w0 = PH.hu(host), PH.pace(host)
    new = partner_walk(host, client, S13_ID, UNSEEN_WALK_DEST, ev)
    hu1, w1 = PH.hu(host), PH.pace(host)
    d = PH.pace_delta(w0, w1, S13_ID)
    ev.update(newCtx=[RM.cv(c) for c in new], pace=d, walkPace=w1.get(str(S13_ID)), HU=[hu0, hu1],
              S13=PH.uview(host, [S13_ID]))
    return {"unseen_walk-walk": walk_cells(new, "intent", S13_ID, UNSEEN_WALK_DEST, host, client),
            "unseen_walk-pre": (S13_ID not in hu0 and S13_ID not in hu1, f"HU before/after {hu0}/{hu1} (want 13 in "
                                                                         f"neither)"),
            "unseen_walk-pace": (d["instant"] >= 1 and d["animated"] == 0, f"WP(host, 13) animated +{d['animated']} "
                                                                           f"instant +{d['instant']} (want instant "
                                                                           f">= 1, animated 0)"),
            "unseen_walk-common": G3F.common(host, client, crash0)}, ev


def row_seen_walk(host, client, crash0, side_ok):
    ev = {}
    if not side_ok:
        return {"seen_walk-pace": (False, "staging (the host's END TURN -> side 0 turn 3 failed in unseen_walk)"),
                "seen_walk-common": G3F.common(host, client, crash0)}, ev
    cam = HC.stage_camera(host, G3F.pos(host, S9_ID))
    ev["camera"] = HC.cam_offset(cam)
    hu0, w0 = PH.hu(host), PH.pace(host)
    new = partner_walk(host, client, S9_ID, SEEN_WALK_DEST, ev)
    hu1, w1 = PH.hu(host), PH.pace(host)
    d = PH.pace_delta(w0, w1, S9_ID)
    ev.update(newCtx=[RM.cv(c) for c in new], pace=d, walkPace=w1.get(str(S9_ID)), HU=[hu0, hu1],
              S9=PH.uview(host, [S9_ID]), pos=[G3F.pos(host, S9_ID), G3F.pos(client, S9_ID)])
    return {"seen_walk-pace": (S9_ID in hu0 and S9_ID in hu1 and d["animated"] >= 1,
                        f"HU before/after {hu0}/{hu1} (want 9 in both); WP(host, 9) animated +{d['animated']} instant "
                        f"+{d['instant']} (want animated >= 1)"),
            "seen_walk-common": G3F.common(host, client, crash0)}, ev


# ===================== boot =====================


def stage(host, client):
    """PH.TILES (every X-COM unit facing away) on both, the destinations open ground, then the settle cycle -> side 1
    turn 2."""
    m = (host, client)
    ev = {"placed": RM.stage_tiles(host, client, PH.TILES, (OWN_WALK_DEST, UNSEEN_WALK_DEST, SEEN_WALK_DEST)),
          "cycle": []}
    for presser, side, turn in ((client, FACTION_HOSTILE, 1), (host, FACTION_PLAYER, 2), (client, FACTION_HOSTILE, 2)):
        sev = {}
        G3F.guarded("staging", lambda p=presser, s=side, t=turn, e=sev: RM.side_change(host, client, p, s, t, e), m)
        ev["cycle"].append([presser.name, sev.get("turnSide"), sev.get("sideBoxes")])
    ev.update(hash=G3F.hash_now(host, client), HU=PH.hu(host), A=PH.uview(host, [A_ID]))
    return ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_pace_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_pace_gm3_client"))
    m = (host, client)
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "boot")
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {st}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("own_walk", rows["own_walk"], lambda: row_own_walk(host, client, crash0))
        fails += G3F.run_row("alien_hud", rows["alien_hud"], lambda: row_alien_hud(host, client, crash0))
        side_ev = {}
        side_ok = PH.side_to(host, client, host, FACTION_PLAYER, 3, side_ev)
        fails += G3F.run_row("unseen_walk", rows["unseen_walk"],
                             lambda: row_unseen_walk(host, client, crash0, side_ok, side_ev))
        fails += G3F.run_row("seen_walk", rows["seen_walk"], lambda: row_seen_walk(host, client, crash0, side_ok))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_pace_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
