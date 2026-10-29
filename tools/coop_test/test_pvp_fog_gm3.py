"""PvP fog, gm3 (the HOST plays the aliens, seat 0; the partner the seven X-COM soldiers, seat 1): the alien host
draws, on its map and minimap, only its own units and the X-COM soldiers its side sees now (fog is per side; on the
host that is the side's live visible lists).

Boot (key 48917, dirs pvp_fog_gm3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT, map seed
1), every live unit's reactions 0, RM.TILES with W (12) on W_OUT facing W_DIR, the settle cycle (the partner's END
TURN, the host's END TURN -> side 0 turn 2). Partner orders are intents (session.send_walk); host orders are real-UI.
VH(gc, id) = battle_state(gc).units[id].visibleHere; HU = the HOST's union of visibleUnits over the live hostile
units; X-COM ids = the live FACTION_PLAYER units at the read.
  unseen_not_drawn  the alien host does not draw X-COM soldiers its side does not see (side 0 turn 2), after the
      settle cycle: unseen_not_drawn-pre (HU == SEEN_IDS), unseen_not_drawn-hide (VH(host, id) false for UNSEEN_IDS),
      unseen_not_drawn-show (true for A and SEEN_IDS), unseen_not_drawn-client (on the client visibleHere == visible
      for every unit).
  seen_drawn  drawn once its aliens see it: the partner's send_walk(W, W_IN). seen_drawn-walk (one new host context
      {intent, walk, W}, coopIntentsSent.walk +1), seen_drawn-pre (W in HU), seen_drawn-agree (every X-COM id:
      VH(host, id) == id in HU).
  left_sight_hidden  hidden once it leaves their sight: the partner's send_walk(11, S4_OUT). left_sight_hidden-walk,
      left_sight_hidden-pre (11 not in HU), left_sight_hidden-hide (VH(host, 11) false).
  own_walk_hides  the host's own alien walk hides what it stops seeing: the partner's END TURN -> side 1 turn 2; one
      TAB + tab_select(host, A); the host's real-UI walk of A to A_DEST. own_walk_hides-walk ({host, walk, A}; A on
      A_DEST on both), own_walk_hides-hide (VH(host, id) false for every X-COM id not in HU). Then EVIDENCE visible:
      every unit's `visible` on both machines (no cell).
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this harness slot's crash
folder.
Without the fix, unseen_not_drawn-hide, seen_drawn-agree, left_sight_hidden-hide and own_walk_hides-hide FAIL; every
other cell passes. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a
failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound
fails the rows that need it "staging". Test-command pairs go to the client first. ONE run is the result, no skip path;
exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_fog_gm3.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_ownerless_units as OU  # noqa: E402
from test_seat_pacing import tab_select, SDLK_TAB  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402

KEY = "48917"
A_ID = RM.A_ID                    # 1000000: the host's alien (seat 0)
W_ID, S4_ID = 12, 11
W_OUT, W_DIR = (19, 2, 0), 6
W_IN = (17, 5, 0)
S4_OUT = (24, 8, 0)
A_DEST = (15, 1, 0)              # one tile north of A: A faces north and loses its southern sight
TILES = dict(RM.TILES)
TILES[W_ID] = (W_OUT, W_DIR)
SEEN_IDS, UNSEEN_IDS = [8, 9, 10, 11], [12, 13, 14]   # HU and the unseen X-COM ids after the settle cycle
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("unseen_not_drawn",
         ("unseen_not_drawn-pre", "unseen_not_drawn-hide", "unseen_not_drawn-show", "unseen_not_drawn-client",
          "unseen_not_drawn-common")),
        ("seen_drawn", ("seen_drawn-walk", "seen_drawn-pre", "seen_drawn-agree", "seen_drawn-common")),
        ("left_sight_hidden",
         ("left_sight_hidden-walk", "left_sight_hidden-pre", "left_sight_hidden-hide", "left_sight_hidden-common")),
        ("own_walk_hides", ("own_walk_hides-walk", "own_walk_hides-hide", "own_walk_hides-common")))

units, pos, es, ctxs, cv = G3F.units, G3F.pos, RM.es, RM.ctxs, RM.cv


def vh(gc, uid):
    return (units(gc).get(uid) or {}).get("visibleHere")


def hu(host):
    """The HOST's union of visibleUnits over the live hostile units (the side's sight as the host holds it)."""
    s = set()
    for u in units(host).values():
        if u.get("faction") == FACTION_HOSTILE and not u.get("isOut"):
            s.update(u.get("visibleUnits") or [])
    return sorted(s)


def xcom_ids(gc):
    return sorted(i for i, u in units(gc).items() if u.get("faction") == FACTION_PLAYER and not u.get("isOut"))


def sight(gc):
    return {i: [u.get("visible"), u.get("visibleHere"), u.get("visibleUnits")] for i, u in sorted(units(gc).items())}


def partner_walk(host, client, uid, dest, ev):
    """The partner's send_walk(uid, dest), bounded until uid stands on dest on both and the host is idle; returns
    (new host contexts, coopIntentsSent.walk delta)."""
    ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
    ev["resp"] = session.send_walk(client, uid, dest)
    ev["done"] = G3F.walk_done(host, client, uid, dest, ev)
    new = new_contexts(ctx0, ctxs(host))
    sent = (es(client, "coopIntentsSent") or {}).get("walk", 0) - sent0.get("walk", 0)
    ev.update(newCtx=[cv(c) for c in new], sent=sent, at=[pos(host, uid), pos(client, uid)],
              restate=[(es(gc, "lastWalk") or {}).get("restate") for gc in (host, client)])
    return new, sent


def walk_cell(new, sent, uid):
    ok, txt = OU.ctx_cell(new, "intent", "walk", uid)
    return ok and sent == 1, f"{txt}; partner coopIntentsSent.walk +{sent} (want +1)"


# ===================== rows =====================


def row_unseen_not_drawn(host, client, crash0):
    cells = {}
    h, xc = hu(host), xcom_ids(host)
    ev = {"HU": h, "UNSEEN_IDS": [i for i in xc if i not in h], "xcom": xc, "sightHost": sight(host),
          "sightClient": sight(client), "sel": [battle_state(gc).get("selectedId") for gc in (host, client)]}
    cells["unseen_not_drawn-pre"] = (h == SEEN_IDS, f"HU {h} (want {SEEN_IDS})")
    got = {i: vh(host, i) for i in UNSEEN_IDS}
    cells["unseen_not_drawn-hide"] = (all(v is False for v in got.values()),
                                      f"VH(host, id) for UNSEEN_IDS: {got} (want False for each)")
    shows = {i: vh(host, i) for i in [A_ID] + SEEN_IDS}
    cells["unseen_not_drawn-show"] = (all(v is True for v in shows.values()),
                                      f"VH(host, id) for A and SEEN_IDS: {shows} (want True)")
    diff = {i: [u.get("visible"), u.get("visibleHere")] for i, u in units(client).items()
            if u.get("visibleHere") != u.get("visible")}
    cells["unseen_not_drawn-client"] = (not diff, f"client units with visibleHere != visible: {diff} (want none)")
    cells["unseen_not_drawn-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_seen_drawn(host, client, crash0):
    ev, cells = {}, {}
    new, sent = partner_walk(host, client, W_ID, W_IN, ev)
    h, xc = hu(host), xcom_ids(host)
    ev.update(HU=h, xcom=xc, sightHost=sight(host))
    cells["seen_drawn-walk"] = walk_cell(new, sent, W_ID)
    cells["seen_drawn-pre"] = (W_ID in h, f"HU {h} (want W {W_ID} in it)")
    bad = {i: [vh(host, i), i in h] for i in xc if vh(host, i) != (i in h)}
    cells["seen_drawn-agree"] = (not bad, f"X-COM ids {xc} with VH(host, id) != (id in HU {h}): {bad} (want none)")
    cells["seen_drawn-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_left_sight_hidden(host, client, crash0):
    ev, cells = {}, {}
    new, sent = partner_walk(host, client, S4_ID, S4_OUT, ev)
    h = hu(host)
    ev.update(HU=h, u11=[vh(host, S4_ID), vh(client, S4_ID)])
    cells["left_sight_hidden-walk"] = walk_cell(new, sent, S4_ID)
    cells["left_sight_hidden-pre"] = (S4_ID not in h, f"HU {h} (want 11 not in it)")
    v = vh(host, S4_ID)
    cells["left_sight_hidden-hide"] = (v is False, f"VH(host, 11) {v} (want False)")
    cells["left_sight_hidden-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_own_walk_hides(host, client, crash0):
    ev, cells = {}, {}
    side = ev["side"] = {}
    RM.side_change(host, client, client, FACTION_HOSTILE, 2, side)
    ev.update(sel0=battle_state(host).get("selectedId"), HUbefore=hu(host))
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
    time.sleep(0.15)
    ev["tab"] = tab_select(host, A_ID)
    ctx0 = ctxs(host)
    try:
        new = RM.host_walk(host, client, A_ID, A_DEST, ev)
    except Exception as e:
        new, ev["walkError"] = new_contexts(ctx0, ctxs(host)), str(e)[:300]
    at = [pos(host, A_ID), pos(client, A_ID)]
    h, xc = hu(host), xcom_ids(host)
    ev.update(newCtx=[cv(c) for c in new], at=at, HU=h, xcom=xc, sightHost=sight(host),
              aDir=[(units(gc).get(A_ID) or {}).get("direction") for gc in (host, client)])
    ok, txt = OU.ctx_cell(new, "host", "walk", A_ID)
    cells["own_walk_hides-walk"] = (ok and at == [A_DEST, A_DEST], f"{txt}; A host/client {at} (want {A_DEST} on both)")
    got = {i: vh(host, i) for i in xc if i not in h}
    cells["own_walk_hides-hide"] = (all(v is False for v in got.values()),
                        f"VH(host, id) for every X-COM id not in HU {h}: {got} (want False for each)")
    cells["own_walk_hides-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def stage(host, client):
    m, ev = (host, client), {}
    ev["placed"] = RM.stage_tiles(host, client, TILES, (W_IN, S4_OUT, A_DEST))
    sv = ev["settle"] = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_HOSTILE, 1, sv.setdefault("a", {})), m)
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_PLAYER, 2, sv.setdefault("b", {})), m)
    ev["hash"] = G3F.hash_now(host, client)
    return ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_fog_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_fog_gm3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, KEY, "boot")
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        st["boot"] = boot
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("unseen_not_drawn", rows["unseen_not_drawn"],
                            lambda: row_unseen_not_drawn(host, client, crash0))
        fails += G3F.run_row("seen_drawn", rows["seen_drawn"], lambda: row_seen_drawn(host, client, crash0))
        fails += G3F.run_row("left_sight_hidden", rows["left_sight_hidden"],
                             lambda: row_left_sight_hidden(host, client, crash0))
        fails += G3F.run_row("own_walk_hides", rows["own_walk_hides"], lambda: row_own_walk_hides(host, client, crash0))
        try:
            vis = {gc.name: {i: u.get("visible") for i, u in sorted(units(gc).items())} for gc in m}
        except Exception as e:
            vis = f"probe failed: {type(e).__name__}: {e}"
        print(f"EVIDENCE visible: {json.dumps(vis, sort_keys=True, default=str)}", flush=True)
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_fog_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
