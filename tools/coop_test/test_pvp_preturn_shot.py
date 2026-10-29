"""R5-U1 S-C rows P1, P2, P4 (boot C2, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat
0) and P3 (boot C3, gm3: the HOST plays the aliens, seat 0; the partner the X-COM soldiers, seat 1): on a PvP host whose
own selection is empty, the opponent's or partner's shot that needs a turn first, and the reaction shots an order draws,
fly in full - an empty selection never cancels a running remote order (owner D222 (a) gap 3, F4205; F12699).

Spec: docs repo rewrite/prompts/r5u1_pvp_fog_camera.md section (f) test_pvp_preturn_shot.py, with the orchestrator
rulings AMENDMENT U1-1 (here A-1: row P4, the reaction shot an order draws) and R-U1-SC-1 (P3 at side 0 turn 2 after the
settle cycle, where the gm3 host's selection is empty; P4's red is +4, one per reaction shot).
Constants: rewrite/r5u1-task0/sc/CONSTANTS.md (TASK 0 boots Ca = Cb for gm2, Ce = Cf for gm3; every pin equal).
Probe: event_state.projectileSkips (EC1-EC4, TEST-ONLY): the HOST's count of ProjectileFlyBState::cancel() skipping a
flying projectile; never reset, the cells read deltas.

Boot C2 (key 48954, dirs r5u1_c2_host / _client): BER.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live
unit's reactions 0, RM.TILES with A facing P1_DIR 0 (away from P_TILE; P_TILE and P4_DEST also checked open ground), the
host's END TURN -> side 1 turn 1 (the host's selection is empty there).
  P1  the alien player's shot that needs a turn flies in full on the host (gap 3): A's pistol (lever), TU; host set_seed
      SEED_P1; the client's lever snap at P_TILE. P1-order (A faces away on both and the host's selection is empty
      (precondition); one new host context {intent, shoot, A}; coopIntentsSent.shoot +1; its evs hold `turn` before
      `shot`), P1-skip (the host's projectileSkips delta 0; RED: +1).
  P2  the same shot with no turn (control): A faces P_TILE (P1's turn); a fresh pistol, TU; the same snap. P2-order (A
      faces P_TILE on both; one {intent, shoot, A}; shoot +1; no `turn` ev), P2-skip (delta 0).
  P4  an X-COM reaction to the alien player's walk flies in full on the host: RM row R2's staging (9 reactions
      100, firing 0, 9's rifle, TU); A on (15,2,0) (place, kept) and its TU; host set_seed SEED_P4; the client's
      send_walk(A, P4_DEST). P4-react (the host's selection empty; one {intent, walk, A} and one `reaction` context
      {actorId 9, nestedIn that walk} holding a shot by 9, halted `reaction` on both: RM.walk_react), P4-skip (delta 0;
      RED: +4, one per reaction shot: 9 fires four), P4-alive (A not out, health equal). P4 is the last row of C2.
Boot C3 (key 48955, dirs r5u1_c3_host / _client): G3F.bring_up, reactions 0, RM.TILES (P3_TILE also checked open
ground), the settle cycle (the partner's END TURN, the host's END TURN -> side 0 turn 2; R-U1-SC-1).
  P3  the partner's shot that needs a turn flies in full on the alien host: 8 faces away (RM.TILES dir 0); its rifle,
      TU; host set_seed SEED_P3; the partner's lever snap at P3_TILE. P3-order (8 faces away on both and the host's
      selection is empty (precondition); one {intent, shoot, 8}; shoot +1; `turn` before `shot`), P3-skip (delta 0;
      RED: +1).
Common cell (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.
EVIDENCE only: the host camera before / after each order. RED at C1: P1-skip, P3-skip, P4-skip; every other cell PASS.
One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails that boot's rows "boot"; a staging step past its bound fails them
"staging". Lever pairs go to the client first; ids come from lever replies (S25). run in the foreground
to completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_preturn_shot.py
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
from test_client_shoot import new_contexts, send_intent, shoot_req, set_tu_both, place  # noqa: E402
from test_host_combat import evs_since  # noqa: E402

KEY_C2, KEY_C3 = "48954", "48955"
A_ID, S9, S8 = RM.A_ID, RM.S3_ID, RM.S_ID   # 1000000 the alien; 9 P4's reactor; 8 P3's shooter
A_TILE = RM.TILES[A_ID][0]                 # (15,2,0)
P_TILE = (15, 7, 0)                        # open, 5 tiles south of A, nothing on the line
P1_DIR, P2_DIR = 0, 4                      # A faces away for P1; P1's turn leaves it facing P_TILE
P4_DEST = RM.R2_DEST                       # (15,4,0); SEED_P4 halts A after (15,3,0) on 9's reaction
P3_TILE = (15, 13, 0)                      # open, 4 tiles south of 8 (15,9,0) facing 0
SEED_P1 = SEED_P2 = SEED_P4 = SEED_P3 = 1
PISTOL, CLIP = RM.PISTOL, RM.CLIP          # STR_PLASMA_PISTOL / _CLIP
RIFLE, RCLIP = "STR_RIFLE", "STR_RIFLE_CLIP"
TU_MAX = 255                               # clamped to the unit's max (A 54, 9 58, 8 64)
STEP_S, CATCH_S = 30, 15
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ROWS_C2 = (("P1", ("P1-order", "P1-skip", "P1-common")),
           ("P2", ("P2-order", "P2-skip", "P2-common")),
           ("P4", ("P4-react", "P4-skip", "P4-alive", "P4-common")))
ROWS_C3 = (("P3", ("P3-order", "P3-skip", "P3-common")),)

es, ctxs, cv, uv = RM.es, RM.ctxs, RM.cv, RM.uv


def skips(host):
    return es(host, "projectileSkips")


def sel(host):
    return battle_state(host).get("selectedId")


def dirs(host, client, uid):
    return [uv(gc, uid)["direction"] for gc in (host, client)]


def catch_up(host, client, ev):
    """Host idle, then the client applied every host seq and its combat ghosts ended (bounded)."""
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    ok, secs = RM.wait_until(lambda: (es(client, "lastSeqApplied") or 0) >= (es(host, "lastSeqEmitted") or 0)
                             and not ((es(client, "combatGhost") or {}).get("live") or 0), CATCH_S, 0.1)
    ev["catchUp"] = [ok, secs]


def skip_cell(sk0, sk1, red):
    d = None if None in (sk0, sk1) else sk1 - sk0
    return (d == 0, f"host projectileSkips {sk0} -> {sk1}: delta {d} (want 0; FIX at C1: {red})")


def lever_snap(host, client, shooter, weapon, tile, seed, ev):
    """The client's lever snap of `shooter` at `tile` (weapon = (id, ammo id) from the give_both reply), the host's
    set_seed right before it. Returns (new contexts, coopIntentsSent.shoot delta, the context's ev kinds, skips)."""
    ctx0, seq0 = ctxs(host), es(host, "lastSeqEmitted") or 0
    sent0, sk0 = dict(es(client, "coopIntentsSent") or {}), skips(host)
    cam0 = HC.camera_of(host)
    host.ok({"cmd": "set_seed", "seed": seed})
    notes = []
    si = send_intent(host, client, shoot_req(shooter, "snap", weapon[0], weapon[1], tile), notes, timeout=STEP_S)
    catch_up(host, client, ev)
    new = new_contexts(ctx0, ctxs(host))
    aid = new[0].get("actionId") if len(new) == 1 else None
    hev = [(e["seq"], e["kind"]) for e in evs_since(host, seq0) if e["actionId"] == aid]
    cseqs = {e["seq"] for e in evs_since(client, seq0)}
    sent = (es(client, "coopIntentsSent") or {}).get("shoot", 0) - sent0.get("shoot", 0)
    sk1 = skips(host)
    ev.update(iseq=si.get("iseq"), answer=si.get("answer"), notes=notes, newCtx=[cv(c) for c in new], chain=hev,
              clientLacks=[s for s, _k in hev if s not in cseqs], skips=[sk0, sk1, skips(client)],
              hostCamBefore=HC.cam_view(cam0), hostCamAfter=HC.cam_view(HC.camera_of(host), seq0))
    return new, sent, [k for _s, k in hev], (sk0, sk1)


def order_cell(new, sent, kinds, actor, want_turn, pre):
    """`pre` = (ok, text) of the row's precondition."""
    if want_turn:
        seq_ok = "turn" in kinds and "shot" in kinds and kinds.index("turn") < kinds.index("shot")
    else:
        seq_ok = "turn" not in kinds and "shot" in kinds
    ok = pre[0] and RM.ctx_ok(new, "intent", "shoot", actor) and sent == 1 and seq_ok
    want = "turn before shot" if want_turn else "a shot, no turn"
    return ok, (f"{pre[1]}; new host contexts {[cv(c) for c in new]} (want one {{intent, shoot, {actor}}}); "
                f"coopIntentsSent.shoot +{sent} (want +1); evs {kinds} (want {want})")


# ===================== rows =====================


def row_shot(row, host, client, crash0, shooter, item, tile, seed, want_dir, want_turn, red, need_empty):
    ev, cells = {}, {}
    g = RM.give_both(host, client, shooter, item[0], item[1])
    weapon = (g.get("weaponId"), g.get("ammoId"))
    ev.update(weapon=weapon, tu=set_tu_both(host, client, shooter, TU_MAX), dirBefore=dirs(host, client, shooter),
              sel=[sel(host), sel(client)])
    bad = []
    if ev["dirBefore"] != [want_dir, want_dir]:
        bad.append(f"{shooter} direction host/client {ev['dirBefore']} (want {want_dir} on both)")
    if need_empty and ev["sel"][0] != -1:
        bad.append(f"host selectedId {ev['sel'][0]} (want -1: an empty selection)")
    pre = (not bad, "; ".join(bad) or f"precondition: {shooter} faces {want_dir}"
           + (", host selection empty" if need_empty else ""))
    new, sent, kinds, sk = lever_snap(host, client, shooter, weapon, tile, seed, ev)
    ev["dirAfter"] = dirs(host, client, shooter)
    cells[f"{row}-order"] = order_cell(new, sent, kinds, shooter, want_turn, pre)
    cells[f"{row}-skip"] = skip_cell(sk[0], sk[1], red)
    cells[f"{row}-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_p4(host, client, crash0):
    ev, cells = {}, {}
    RM.stat_both(host, client, S9, "reactions", 100)
    RM.stat_both(host, client, S9, "firing", 0)
    g = RM.give_both(host, client, S9, RIFLE, RCLIP)
    ev.update(rifle=(g.get("weaponId"), g.get("ammoId")), s9Tu=set_tu_both(host, client, S9, TU_MAX),
              placeA=place(host, client, A_ID, A_TILE, P2_DIR), aTu=set_tu_both(host, client, A_ID, TU_MAX),
              sel=[sel(host), sel(client)])
    seq0, ctx0, prev = es(host, "lastSeqEmitted") or 0, ctxs(host), session.walk_action_id(host)
    sent0, sk0 = dict(es(client, "coopIntentsSent") or {}), skips(host)
    cam0 = HC.camera_of(host)
    host.ok({"cmd": "set_seed", "seed": SEED_P4})
    ev["walk"] = session.send_walk(client, A_ID, P4_DEST)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    catch_up(host, client, ev)
    wr = RM.walk_react("P4", host, client, ctx0, seq0, "intent", A_ID, S9, ev, sent0)
    sk1 = skips(host)
    ev.update(skips=[sk0, sk1, skips(client)], A=[uv(host, A_ID), uv(client, A_ID)],
              hostCamBefore=HC.cam_view(cam0), hostCamAfter=HC.cam_view(HC.camera_of(host), seq0))
    pre_ok = ev["sel"][0] == -1
    ok = pre_ok and wr["P4-walk"][0] and wr["P4-react"][0]
    cells["P4-react"] = (ok, f"host selectedId {ev['sel'][0]} (want -1); {wr['P4-walk'][1]}; {wr['P4-react'][1]}")
    cells["P4-skip"] = skip_cell(sk0, sk1, "+4, one per reaction shot")
    cells["P4-alive"] = RM.alive_cell(host, client, A_ID)
    cells["P4-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boots =====================


def boot_c2():
    host = GameClient("host", None, make_user_dir("r5u1_c2_host"))
    client = GameClient("client", None, make_user_dir("r5u1_c2_client"))
    m = (host, client)
    try:
        try:
            G3F.guarded("C2", lambda: BER.boot_e6(host, client, KEY_C2), m)
            crash0 = session._crash_log_snapshot()
            G3F.guarded("C2", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS_C2, "boot (FIXTURE-STOP, see the CAPTURE C2 line)")
        st = {}
        try:
            tiles = dict(RM.TILES)
            tiles[A_ID] = (A_TILE, P1_DIR)
            st["placed"] = RM.stage_tiles(host, client, tiles, (P_TILE, P4_DEST))
            sv = st.setdefault("side", {})
            G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_HOSTILE, 1, sv), m)
            st.update(sel=[sel(host), sel(client)], probe=[skips(host), skips(client)], hash=G3F.hash_now(host, client))
        except G3F.Miss:
            return G3F.fail_all(ROWS_C2, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE C2 staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        rows = dict(ROWS_C2)
        fails = G3F.run_row("P1", rows["P1"], lambda: row_shot("P1", host, client, crash0, A_ID, (PISTOL, CLIP), P_TILE,
                                                               SEED_P1, P1_DIR, True, "+1", True))
        fails += G3F.run_row("P2", rows["P2"], lambda: row_shot("P2", host, client, crash0, A_ID, (PISTOL, CLIP),
                                                                P_TILE, SEED_P2, P2_DIR, False, "+0", False))
        fails += G3F.run_row("P4", rows["P4"], lambda: row_p4(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def boot_c3():
    host = GameClient("host", None, make_user_dir("r5u1_c3_host"))
    client = GameClient("client", None, make_user_dir("r5u1_c3_client"))
    m = (host, client)
    try:
        try:
            boot, crash0 = G3F.bring_up(host, client, KEY_C3, "C3")
            G3F.guarded("C3", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS_C3, "boot (FIXTURE-STOP, see the CAPTURE C3 line)")
        st = {"boot": boot}
        try:
            st["placed"] = RM.stage_tiles(host, client, RM.TILES, (P3_TILE,))
            sa, sb = st.setdefault("a", {}), st.setdefault("b", {})
            G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_HOSTILE, 1, sa), m)
            G3F.guarded("staging", lambda: RM.side_change(host, client, host, FACTION_PLAYER, 2, sb), m)
            st.update(sel=[sel(host), sel(client)], probe=[skips(host), skips(client)], hash=G3F.hash_now(host, client))
        except G3F.Miss:
            return G3F.fail_all(ROWS_C3, "staging (see the CAPTURE staging line)")
        print(f"EVIDENCE C3 staging: {json.dumps(st, sort_keys=True, default=str)}", flush=True)
        return G3F.run_row("P3", ROWS_C3[0][1], lambda: row_shot("P3", host, client, crash0, S8, (RIFLE, RCLIP),
                                                                 P3_TILE, SEED_P3, 0, True, "+1", True))
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_c2()
    fails += boot_c3()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_preturn_shot: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
