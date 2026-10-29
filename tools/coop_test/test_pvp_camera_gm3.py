"""R5-U1 S-B rows K4, K5, K6, K8 (boot B3, gm3: the HOST plays the aliens, seat 0; the partner the seven X-COM soldiers,
seat 1): on the alien host an X-COM shot counts as "in view" only when its own side sees it, its camera centres on a
seen X-COM walker off screen and on its own alien hit by an X-COM psi attack (owner D222 (a) gaps 1-2, D131 / D171,
AUD-A16; QU1-2 (a)).

Spec: docs repo rewrite/prompts/r5u1_pvp_fog_camera.md section (f) test_pvp_camera_gm3.py, with the orchestrator
rulings AMENDMENT U1-1 (here A-3: K5's shooter gets give_both(rifle, clip) + set_tu_both before the press; K4-pre is the
exact distance precondition).
Constants: rewrite/r5u1-task0/sb/CONSTANTS.md (TASK 0 boots Bc, Bd; every pin equal).

Boot B3 (key 48919, dirs r5u1_b3_host / _client): G3F.bring_up (the HOST on the Alien team, STR_SMALL_SCOUT, map seed
1), every live unit's reactions 0, RM.TILES (K1_TILE, K2_TILE, K6_DEST also checked open ground), the settle cycle (the
partner's END TURN, the host's END TURN -> side 0 turn 2). Partner orders are intents (CSH.send_intent, session.send_walk).
HU = the HOST's union of visibleUnits over the live hostile units. Camera cells read the host's offset after the host is
idle; offsets compare x / y (z is the view level).
  K4  an X-COM shot no alien sees does not move the alien host's camera (gap 1): host camera on A; the rifle on 13
      (give_both); host set_seed SEED_K4; the partner's lever snap of 13 at K1_TILE. K4-shot (one new host context
      {intent, shoot, 13}; coopIntentsSent.shoot +1), K4-pre (13 not in HU; every tile of the segment 13 -> K1_TILE
      farther than the max view distance from every live hostile unit), K4-cam (the host's offset == staged).
  K5  a seen shot is followed (control): host camera at FAR; 9's rifle + TU; host set_seed SEED_K5; the partner's lever
      snap of 9 at K2_TILE. K5-cam (the host's offset != staged).
  K6  the alien host's camera centres on a seen X-COM walker off screen (gap 2): host camera at FAR; the partner's
      send_walk(8, K6_DEST). K6-walk (one new host context {intent, walk, 8}; walk +1; 8 on K6_DEST on both), K6-pre (8
      in HU after), K6-centre (the host's offset != staged and 8's tile on the host's screen: map_tile_screen_pos inside
      the map surface).
  K8  the alien host's camera centres on its own alien hit by an X-COM psi attack: the partner's END TURN ->
      side 1 turn 2, the host's END TURN -> side 0 turn 3; host camera at FAR; the amp on 11, 11 psiSkill 100, A
      psiStrength 0, 11's TU; host set_seed SEED_K8; the partner's lever psi {panic, A}. K8-psi (one new host context
      {intent, psi, 11}; psi +1), K8-centre (the host's offset centred on A's tile: A_CENTRE). K8 is the last row.
  (No K7: the own-walker direction of EB6 has no row, spec (d) S-B.)
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
RED at B1: K4-cam, K6-centre, K8-centre; every other cell PASS. One EVIDENCE line per row, one PASS/FAIL line per cell,
then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every
row "boot"; a staging step past its bound fails the rows that need it "staging". Lever pairs go to the client first;
ids come from lever replies (S25). run in the foreground to completion. ONE run is the
result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_camera_gm3.py
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
from test_client_shoot import new_contexts, send_intent, shoot_req, set_tu_both, jt  # noqa: E402

KEY = "48919"
A_ID, A_TILE = K.A_ID, K.A_TILE   # 1000000 on (15,2,0) facing 4: the host's alien (seat 0)
U13, S9, S8, S11 = 13, 9, 8, 11
K1_TILE, K2_TILE, FAR, A_CENTRE = K.K1_TILE, K.K2_TILE, K.FAR, K.A_CENTRE
K6_DEST = (15, 12, 0)             # 8 (15,9,0) walks 3 tiles south inside A's sight, off the staged screen
SEED_K4 = SEED_K5 = SEED_K8 = 1
STEP_S = 30
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS = (("K4", ("K4-shot", "K4-pre", "K4-cam", "K4-common")),
        ("K5", ("K5-cam", "K5-common")),
        ("K6", ("K6-walk", "K6-pre", "K6-centre", "K6-common")),
        ("K8", ("K8-psi", "K8-centre", "K8-common")))

units, pos, es, ctxs, cv, hu = G3F.units, G3F.pos, RM.es, RM.ctxs, RM.cv, K.hu


def idle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]


def sent_delta(client, sent0, kind):
    return (es(client, "coopIntentsSent") or {}).get(kind, 0) - (sent0 or {}).get(kind, 0)


def admitted(new, sent, origin, kind, actor):
    return (RM.ctx_ok(new, origin, kind, actor) and sent == 1,
            f"new host contexts {[cv(c) for c in new]} (want one {{{origin}, {kind}, {actor}}}); the partner's "
            f"coopIntentsSent.{kind} +{sent} (want +1)")


def partner_snap(host, client, shooter, tile, seed, ev):
    """The partner's lever snap of `shooter` (its rifle from the give_both reply) at `tile`, the host's set_seed right
    before it; returns (new contexts, coopIntentsSent.shoot delta)."""
    ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
    seq0 = es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": seed})
    notes = []
    si = send_intent(host, client, shoot_req(shooter, "snap", ev["rifle"][0], ev["rifle"][1], tile), notes,
                     timeout=STEP_S)
    idle(host, client, ev)
    new = new_contexts(ctx0, ctxs(host))
    hev, lacks = K.chain_applied(host, client, new, seq0)
    ev.update(iseq=si.get("iseq"), answer=si.get("answer"), notes=notes, newCtx=[cv(c) for c in new], chain=hev,
              lacks=lacks, seq0=seq0)
    return new, sent_delta(client, sent0, "shoot")


def on_screen(gc, t):
    r = gc.cmd({"cmd": "map_tile_screen_pos", "x": t[0], "y": t[1], "z": t[2]})
    sx, sy, w, h = (r.get(k) for k in ("screenX", "screenY", "mapWidth", "mapHeight"))
    ok = None not in (sx, sy, w, h) and 0 <= sx < w and 0 <= sy < h
    return ok, (sx, sy, w, h)


# ===================== rows =====================


def row_k4(host, client, crash0):
    ev, cells = {}, {}
    staged = ev["staged"] = HC.cam_offset(HC.stage_camera(host, A_TILE))
    g = RM.give_both(host, client, U13, K.RIFLE, K.CLIP)
    ev["rifle"] = (g.get("weaponId"), g.get("ammoId"))
    pre = K.far_pre(host, U13, K1_TILE, ev)
    new, sent = partner_snap(host, client, U13, K1_TILE, SEED_K4, ev)
    cam = HC.camera_of(host)
    ev["camera"] = HC.cam_view(cam)
    cells["K4-shot"] = admitted(new, sent, "intent", "shoot", U13)
    cells["K4-pre"] = pre
    cells["K4-cam"] = K.cam_cell(HC.cam_offset(cam), staged, True, "host")
    cells["K4-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_k5(host, client, crash0):
    ev, cells = {}, {}
    staged = ev["staged"] = HC.cam_offset(HC.stage_camera(host, FAR))
    g = RM.give_both(host, client, S9, K.RIFLE, K.CLIP)
    ev["rifle"] = (g.get("weaponId"), g.get("ammoId"))
    ev["tu"] = set_tu_both(host, client, S9, K.TU_MAX)
    ev["HU"] = hu(host)
    new, sent = partner_snap(host, client, S9, K2_TILE, SEED_K5, ev)
    ev["sent"] = sent
    cam = HC.camera_of(host)
    ev["camera"] = HC.cam_view(cam)
    cells["K5-cam"] = K.cam_cell(HC.cam_offset(cam), staged, False, "host")
    cells["K5-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_k6(host, client, crash0):
    ev, cells = {}, {}
    staged = ev["staged"] = HC.cam_offset(HC.stage_camera(host, FAR))
    ev["screenAtStage"] = on_screen(host, pos(host, S8))
    ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
    ev["resp"] = session.send_walk(client, S8, K6_DEST)
    done = G3F.walk_done(host, client, S8, K6_DEST, ev)
    new = new_contexts(ctx0, ctxs(host))
    at = [pos(host, S8), pos(client, S8)]
    h = hu(host)
    cam = HC.camera_of(host)
    off = HC.cam_offset(cam)
    seen, scr = on_screen(host, at[0])
    ev.update(newCtx=[cv(c) for c in new], at=at, HU=h, camera=HC.cam_view(cam), screenAfter=scr,
              restate=[(es(gc, "lastWalk") or {}).get("restate") for gc in (host, client)])
    ok, txt = admitted(new, sent_delta(client, sent0, "walk"), "intent", "walk", S8)
    cells["K6-walk"] = (ok and done and at == [K6_DEST, K6_DEST],
                        f"{txt}; 8 host/client {at} (want {K6_DEST} on both)")
    cells["K6-pre"] = (S8 in h, f"HU {h} after the walk (want {S8} in it)")
    cells["K6-centre"] = (off is not None and not K.same_xy(off, staged) and seen,
                          f"host camera offset {off} (want x / y != staged {staged}); 8's tile {at[0]} on the host's "
                          f"screen (screenX, screenY, mapWidth, mapHeight) {scr} (want inside)")
    cells["K6-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_k8(host, client, crash0):
    ev, cells = {}, {}
    side = ev["side"] = {}
    RM.side_change(host, client, client, FACTION_HOSTILE, 2, side.setdefault("a", {}))
    RM.side_change(host, client, host, FACTION_PLAYER, 3, side.setdefault("b", {}))
    ev["staged"] = HC.cam_offset(HC.stage_camera(host, FAR))
    amp = ev["amp"] = RM.give_both(host, client, S11, RM.PSI_AMP)["weaponId"]
    RM.stat_both(host, client, S11, "psiSkill", 100)
    RM.stat_both(host, client, A_ID, "psiStrength", 0)
    ev["tu"] = set_tu_both(host, client, S11, K.TU_MAX)
    ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
    seq0 = es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_K8})
    notes = []
    si = send_intent(host, client, {"cmd": "battle_intent", "kind": "psi", "actor": S11,
                                    "plan": {"action": "panic", "weapon": amp, "target": jt(A_TILE),
                                             "targetUnit": A_ID}}, notes, timeout=STEP_S)
    mc = ev["mc"] = {}
    new = RM.mc_order(host, client, ctx0, A_ID, mc)
    cam = HC.camera_of(host)
    off = HC.cam_offset(cam)
    ev["cue"] = K.cue_cell(host, client, new, seq0, "psi", {"actor": S11, "unit": A_ID, "action": "panic"}, ev)[1]
    ev.update(iseq=si.get("iseq"), answer=si.get("answer"), notes=notes, camera=HC.cam_view(cam),
              aMorale=[(units(gc).get(A_ID) or {}).get("morale") for gc in (host, client)])
    cells["K8-psi"] = admitted(new, sent_delta(client, sent0, "psi"), "intent", "psi", S11)
    cells["K8-centre"] = (K.same_xy(off, A_CENTRE),
                          f"host camera offset {off} after the psi (want x / y {A_CENTRE}, centred on A; staged "
                          f"{ev['staged']})")
    cells["K8-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot B3 =====================


def stage(host, client):
    m, ev = (host, client), {}
    ev["placed"] = RM.stage_tiles(host, client, RM.TILES, (K1_TILE, K2_TILE, K6_DEST))
    sv = ev["settle"] = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_HOSTILE, 1, sv.setdefault("a", {})), m)
    G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_PLAYER, 2, sv.setdefault("b", {})), m)
    ev["HU"] = hu(host)
    ev["hash"] = G3F.hash_now(host, client)
    return ev


def boot_b3():
    host = GameClient("host", None, make_user_dir("r5u1_b3_host"))
    client = GameClient("client", None, make_user_dir("r5u1_b3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, KEY, "B3")
            G3F.guarded("B3", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE B3 line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        st["boot"] = boot
        print(f"EVIDENCE staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("K4", rows["K4"], lambda: row_k4(host, client, crash0))
        fails += G3F.run_row("K5", rows["K5"], lambda: row_k5(host, client, crash0))
        fails += G3F.run_row("K6", rows["K6"], lambda: row_k6(host, client, crash0))
        fails += G3F.run_row("K8", rows["K8"], lambda: row_k8(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_b3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_camera_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
