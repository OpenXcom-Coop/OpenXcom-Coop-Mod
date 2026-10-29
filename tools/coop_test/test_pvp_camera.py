"""R5-U1 S-B rows K1, K2, K3 (boot B2, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers,
seat 0): on the alien player's machine an X-COM shot counts as "in view" only when its own side sees it, and its camera
centres on its own alien hit by an X-COM psi attack (owner D222 (a) gaps 1-2, D131 / D171, AUD-A16; QU1-2 (a)).

Spec: docs repo rewrite/prompts/r5u1_pvp_fog_camera.md section (f) test_pvp_camera.py, with the orchestrator rulings
AMENDMENT U1-1 (here A-3: every shooter gets give_both(rifle, clip) + set_tu_both before the press; K1-pre is the exact
distance precondition).
Constants: rewrite/r5u1-task0/sb/CONSTANTS.md (TASK 0 boots Ba, Bb; every pin equal).

Boot B2 (key 48918, dirs r5u1_b2_host / _client): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live
unit's reactions 0, RM.TILES (K1_TILE and K2_TILE also checked open ground), the settle cycle (host END TURN, client END
TURN -> side 0 turn 2). Every order is a host REAL-UI order: tab_select, the right-hand box, the action key, HOME, the
host's set_seed right before ONE map_tile_click. HU = the HOST's union of visibleUnits over the live hostile
units. Camera cells read the offset after the catch-up (host idle, the client applied every host seq, its combat ghosts
ended), never a move record's `after`; offsets compare x / y (z is the view level).
  K1  an X-COM shot no alien sees does not move the alien player's camera (gap 1): client camera staged on A; 13's
      rifle + TU; host set_seed SEED_K1; the host's real-UI SNAP of 13 at K1_TILE. K1-shot (one new host context {host,
      shoot, 13}; the client applied every seq of its chain), K1-pre (13 not in HU; every tile of the segment 13 ->
      K1_TILE farther than the max view distance from every live hostile unit), K1-cam (the client's offset == staged).
  K2  a shot the aliens see is followed (control): client camera at FAR; 9's rifle + TU; the host's real-UI SNAP of 9 at
      K2_TILE. K2-pre (9 in HU), K2-cam (the client's offset != staged).
  K3  the alien player's camera centres on its own alien hit by an X-COM psi attack: client camera at FAR; the
      amp on 8, 8 psiSkill 100, A psiStrength 0, 8's TU; host set_seed SEED_K3; the host's real-UI PANIC by 8 on A.
      K3-psi (one new host context {host, psi, 8}; its psi cue {actor 8, unit A, action panic} applied on the client),
      K3-centre (one client camera.moves record {reason hit_centre, unit A}; the offset centred on A's tile: A_CENTRE).
      K3 is the last row (A may panic).
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
RED at B1: K1-cam, K3-centre; every other cell PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the
row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row
"boot"; a staging step past its bound fails the rows that need it "staging". Lever pairs go to the client first;
ids come from lever replies (S25). run in the foreground to completion. ONE run is the
result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_camera.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_host_combat as HC  # noqa: E402
from test_seat_pacing import tab_select, SDLK_HOME  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
from test_client_shoot import new_contexts, set_tu_both, RHAND_CENTRE  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402
from test_messages import poll_host_box  # noqa: E402

KEY = "48918"
A_ID = RM.A_ID                    # 1000000: the only alien (STR_SECTOID_SOLDIER), the client's seat 1
A_TILE = RM.TILES[A_ID][0]        # (15,2,0) facing 4: sees 8, 9, 10, 11
U13, S9, S8 = 13, 9, 8
K1_TILE = (33, 30, 0)             # open, 3 tiles north of 13 (33,33,0): 13 and the tile out of A's sight
K2_TILE = (17, 8, 0)              # open, in A's sight, Chebyshev 2 from 9 (18,6,0)
FAR = (36, 36, 0)                 # camera staging far from every order
A_CENTRE = (-48, -64)             # the offset x / y centred on A's tile (stage_camera(A_TILE), Ba, Bb, Bc, Bd)
SEED_K1 = SEED_K2 = SEED_K3 = 1
RIFLE, CLIP = "STR_RIFLE", "STR_RIFLE_CLIP"
TU_MAX = 255                      # clamped to the unit's max TU (13 61, 9 58, 8 64)
KEY_SNAP, CT_AIM, RIFLE_ROWS = 50, 2, 4
KEY_PANIC, CT_PSI, PSI_ROWS = 50, 3, 3
MAX_VIEW_SQ = 20 * 20             # Mod::_maxViewDistance default (Mod.cpp :424); no ruleset override
STEP_S, CATCH_S = 30, 15
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("K1", ("K1-shot", "K1-pre", "K1-cam", "K1-common")),
        ("K2", ("K2-pre", "K2-cam", "K2-common")),
        ("K3", ("K3-psi", "K3-centre", "K3-common")))

units, pos, es, ctxs, cv = G3F.units, G3F.pos, RM.es, RM.ctxs, RM.cv


# ===================== shared helpers (test_pvp_camera_gm3 imports them) =====================


def hu(host):
    """The HOST's union of visibleUnits over the live hostile units (the side's sight as the host holds it)."""
    s = set()
    for u in units(host).values():
        if u.get("faction") == FACTION_HOSTILE and not u.get("isOut"):
            s.update(u.get("visibleUnits") or [])
    return sorted(s)


def line2d(a, b):
    """The tiles of a 2D Bresenham line from a to b, both ends included."""
    x0, y0, x1, y1 = a[0], a[1], b[0], b[1]
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err, pts = dx + dy, []
    while True:
        pts.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return pts
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def far_pre(host, shooter, tile, ev):
    """`shooter` not in HU, and every tile of the segment shooter -> tile farther (2D, squared) than MAX_VIEW_SQ
    from every live hostile unit (coopTileSeenHere tests that distance first, so its tile-sight term is false)."""
    h = hu(host)
    hos = {i: (u["x"], u["y"]) for i, u in units(host).items()
           if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")}
    seg = line2d(pos(host, shooter), tile)
    mn = min(((t[0] - p[0]) ** 2 + (t[1] - p[1]) ** 2 for t in seg for p in hos.values()), default=None)
    ev.update(HU=h, hostile=hos, segment=seg, minDistSq=mn)
    return (shooter not in h and mn is not None and mn > MAX_VIEW_SQ,
            f"HU {h} (want {shooter} not in it); min squared 2D distance from the segment {seg[0]}->{seg[-1]} to the "
            f"live hostile units {hos}: {mn} (want > {MAX_VIEW_SQ})")


def same_xy(a, b):
    return a is not None and b is not None and tuple(a[:2]) == tuple(b[:2])


def cam_cell(off, staged, want_equal, who):
    ok = same_xy(off, staged) if want_equal else (off is not None and staged is not None and not same_xy(off, staged))
    return ok, f"{who} camera offset {off} after the order (want x / y {'==' if want_equal else '!='} staged {staged})"


def chain_applied(host, client, new, seq0):
    """(host evs of the new context's chain, the seqs the client lacks)."""
    aid = new[0].get("actionId") if len(new) == 1 else None
    hev = [(e["seq"], e["kind"], e["actionId"]) for e in evs_since(host, seq0) if e["actionId"] == aid]
    cev = {(e["seq"], e["kind"], e["actionId"]) for e in evs_since(client, seq0)}
    return hev, [s for s in hev if s not in cev]


def cue_cell(host, client, new, seq0, kind, want, ev):
    """Exactly one `kind` cue in the new context's chain whose payload carries `want`, applied on the client."""
    hev, lacks = chain_applied(host, client, new, seq0)
    seqs = [s for s, k, _a in hev if k == kind]
    pl = host_payloads(host, seqs, timeout=3) if seqs else {}
    cues = [(s, {k: (v.get("payload") or {}).get(k) for k in ("actor", "unit", "action", "success")})
            for s, v in sorted(pl.items())]
    ev.update(chain=hev, lacks=lacks, cues=cues)
    ok = len(cues) == 1 and {k: cues[0][1].get(k) for k in want} == want and not lacks
    return ok, f"{kind} cues {cues} (want one carrying {want}); the client lacks {lacks} (want none)"


# ===================== the host's real-UI orders =====================


def ghost_live(gc):
    return (es(gc, "combatGhost") or {}).get("live") or 0


def catch_up(host, client, ev):
    """Host idle, then the client applied every host seq and its combat ghosts ended (bounded)."""
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    ok, secs = RM.wait_until(lambda: (es(client, "lastSeqApplied") or 0) >= (es(host, "lastSeqEmitted") or 0)
                             and not ghost_live(client), CATCH_S, 0.1)
    ev["catchUp"] = [ok, secs]


def hand_key(host, uid, key, rows, cursor, ev):
    """tab_select(host, uid); the right-hand box (self-verified) -> ActionMenuState with `rows` rows; `key` -> `cursor`."""
    ev["tab"] = tab_select(host, uid)
    assert battle_state(host).get("selectedId") == uid, f"host selectedId {battle_state(host).get('selectedId')} " \
                                                        f"(want {uid})"
    if battle_state(host).get("cursorType") in RM.CURSOR_TARGETING:
        click_nth(host, RHAND_NTH)   # this click only cancels a leftover aim
    r = click_nth(host, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    ok, _s = RM.wait_until(lambda: G3F.top(host) == "ActionMenuState", 5, 0.1)
    assert ok, f"no ActionMenuState on the host (stack {G3F.stack(host)})"
    ev["rows"] = len([w for w in host.cmd({"cmd": "list_widgets"}).get("widgets", [])
                      if w.get("visible") and "ActionMenuItem" in w.get("type", "")])
    assert ev["rows"] == rows, f"action menu rows {ev['rows']} (want {rows})"
    host.ok({"cmd": "inject_input", "kind": "key", "key": key})
    RM.wait_until(lambda: G3F.top(host) == "BattlescapeState", 5, 0.1)
    ev["cursorAfterKey"] = battle_state(host).get("cursorType")
    assert ev["cursorAfterKey"] == cursor, f"key {key}: host cursorType {ev['cursorAfterKey']} (want {cursor})"


def click_tile(host, tile, seed, ev):
    """HOME, the host's set_seed right before the click, ONE map_tile_click on `tile`."""
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_HOME})
    time.sleep(0.15)
    host.ok({"cmd": "set_seed", "seed": seed})
    r = host.cmd({"cmd": "map_tile_click", "x": tile[0], "y": tile[1], "z": tile[2]})
    ev["click"] = (r.get("winX"), r.get("winY"), r.get("verified"), r.get("clicked"))
    assert r.get("verified") and r.get("clicked"), f"map_tile_click {tile} on the host: {r}"


def host_order(host, client, ctx0, ev):
    """After the click: a bounded wait for one new host context and the host free, host boxes closed host-only, then
    the catch-up. Returns the new contexts."""
    rec = {"hostBoxes": []}
    RM.wait_until(lambda: (poll_host_box(host, rec, "order") or True) and len(new_contexts(ctx0, ctxs(host))) >= 1
                  and es(host, "busyOwnerSeat") == -1, STEP_S, 0.1)
    catch_up(host, client, ev)
    poll_host_box(host, rec, "order after")
    ev["hostBoxes"] = [b.get("texts") for b in rec["hostBoxes"]]
    return new_contexts(ctx0, ctxs(host))


def host_snap(host, client, shooter, tile, seed, ev):
    """A-3 staging (the rifle by lever, both machines; the shooter's TU), then the host's real-UI SNAP of `shooter` at
    `tile`. Returns (new contexts, seq0)."""
    g = RM.give_both(host, client, shooter, RIFLE, CLIP)
    ev["rifle"] = (g.get("weaponId"), g.get("ammoId"))
    ev["tu"] = set_tu_both(host, client, shooter, TU_MAX)
    hand_key(host, shooter, KEY_SNAP, RIFLE_ROWS, CT_AIM, ev)
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    try:
        click_tile(host, tile, seed, ev)
    except Exception as e:
        ev["clickError"] = str(e)[:300]
    new = host_order(host, client, ctx0, ev)
    ev["newCtx"] = [cv(c) for c in new]
    return new, seq0


# ===================== rows =====================


def row_k1(host, client, crash0):
    ev, cells = {}, {}
    staged = ev["staged"] = HC.cam_offset(HC.stage_camera(client, A_TILE))
    pre = far_pre(host, U13, K1_TILE, ev)
    new, seq0 = host_snap(host, client, U13, K1_TILE, SEED_K1, ev)
    cam = HC.camera_of(client)
    off = HC.cam_offset(cam)
    hev, lacks = chain_applied(host, client, new, seq0)
    ev.update(chain=hev, lacks=lacks, camera=HC.cam_view(cam, seq0))
    cells["K1-shot"] = (RM.ctx_ok(new, "host", "shoot", U13) and bool(hev) and not lacks,
                        f"new host contexts {ev['newCtx']} (want one {{host, shoot, {U13}}}); chain {hev}; the client "
                        f"lacks {lacks} (want none)")
    cells["K1-pre"] = pre
    cells["K1-cam"] = cam_cell(off, staged, True, "client")
    cells["K1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_k2(host, client, crash0):
    ev, cells = {}, {}
    staged = ev["staged"] = HC.cam_offset(HC.stage_camera(client, FAR))
    h = ev["HU"] = hu(host)
    new, seq0 = host_snap(host, client, S9, K2_TILE, SEED_K2, ev)
    cam = HC.camera_of(client)
    ev["camera"] = HC.cam_view(cam, seq0)
    cells["K2-pre"] = (S9 in h, f"HU {h} (want {S9} in it); the order's contexts {ev['newCtx']}")
    cells["K2-cam"] = cam_cell(HC.cam_offset(cam), staged, False, "client")
    cells["K2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_k3(host, client, crash0):
    ev, cells = {}, {}
    ev["staged"] = HC.cam_offset(HC.stage_camera(client, FAR))
    ev["amp"] = RM.give_both(host, client, S8, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, S8, "psiSkill", 100)
    RM.stat_both(host, client, A_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, S8, TU_MAX)
    ev["spotted"] = battle_state(host).get("spotted")
    hand_key(host, S8, KEY_PANIC, PSI_ROWS, CT_PSI, ev)
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    try:
        click_tile(host, A_TILE, SEED_K3, ev)
    except Exception as e:
        ev["clickError"] = str(e)[:300]
    mc = ev["mc"] = {}
    new = RM.mc_order(host, client, ctx0, A_ID, mc)
    catch_up(host, client, ev)
    cam = HC.camera_of(client)
    off = HC.cam_offset(cam)
    hc = [m for m in HC.cam_moves(cam, seq0) if m.get("reason") == "hit_centre"]
    ev.update(newCtx=[cv(c) for c in new], camera=HC.cam_view(cam, seq0),
              aMorale=[(units(gc).get(A_ID) or {}).get("morale") for gc in (host, client)])
    ok, txt = cue_cell(host, client, new, seq0, "psi", {"actor": S8, "unit": A_ID, "action": "panic"}, ev)
    cells["K3-psi"] = (RM.ctx_ok(new, "host", "psi", S8) and ok,
                       f"new host contexts {ev['newCtx']} (want one {{host, psi, {S8}}}); {txt}")
    cells["K3-centre"] = (len(hc) == 1 and hc[0].get("unit") == A_ID and same_xy(off, A_CENTRE),
                          f"client hit_centre records since seq {seq0}: {[HC.mv(m) + (m.get('unit'),) for m in hc]} "
                          f"(want one with unit {A_ID}); client offset {off} (want x / y {A_CENTRE}, centred on A)")
    cells["K3-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot B2 =====================


def stage(host, client):
    m, ev = (host, client), {}
    ev["placed"] = RM.stage_tiles(host, client, RM.TILES, (K1_TILE, K2_TILE))
    sv = ev["settle"] = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_HOSTILE, 1, sv.setdefault("a", {})), m)
    G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_PLAYER, 2, sv.setdefault("b", {})), m)
    ev["HU"] = hu(host)
    ev["hash"] = G3F.hash_now(host, client)
    return ev


def boot_b2():
    host = GameClient("host", None, make_user_dir("r5u1_b2_host"))
    client = GameClient("client", None, make_user_dir("r5u1_b2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("B2", lambda: BER.boot_pvp(host, client, KEY), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("B2", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE B2 line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("K1", rows["K1"], lambda: row_k1(host, client, crash0))
        fails += G3F.run_row("K2", rows["K2"], lambda: row_k2(host, client, crash0))
        fails += G3F.run_row("K3", rows["K3"], lambda: row_k3(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_b2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_camera: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
