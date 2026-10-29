"""R5-U6 S-A rows RN2, RN1, RNK (boot RA, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers,
seat 0) with the HOST's "Enable Reaction Fire in PvP" off (its options.cfg `EnableReactionFirePvp: false`; the client
keeps the default): a walking unit in a PvP battle draws no reaction fire, a kneel still does (owner D236 (b); QU6-1 (a):
the walk step is the release line's one gated trigger, `main` UnitWalkBState :465; QU6-3 (a): the host's value, taken
when the battle starts).

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md section (f) test_pvp_reaction_option.py, with the orchestrator
ruling R-U6-SA-1 (SEED_R1: S alive and unhurt after RN1 on the unchanged build; A's TU refilled before the kneel).
Constants: rewrite/r5u6-task0/sa/CONSTANTS.md (TASK 0 boots RAa, RAb, rh2, rh2b, rk2, rk2b on the unchanged build).

Boot RA (key 49060): BER.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's reactions 0, R5-U3's
staging (test_pvp_react_mc.stage: TILES, A's plasma pistol, S3's rifle, the host's END TURN -> side 1 turn 1).
  RN2  X-COM does not react to the alien seat's walk: S3 reactions 100, firing 0, TU 255; host set_seed SEED_R2; the
       client's send_walk of A to R2_DEST.
       RN2-walk  one new host context W {intent, walk, A}; the client's coopIntentsSent.walk +1, inFlight null
       RN2-none  no `reaction` context nested in W; no `shot` ev in the row
       RN2-dest  A's executed path RN2_PATH, not halted, A on R2_DEST on both; lastWalk.restate equal on both
       After RN2: A back on its TILES tile facing 4; S3 reactions 0.
  RN1  the alien does not react to the X-COM host's walk: the client's END TURN -> side 0 turn 2; A's pistol (lever),
       reactions 100, firing 0, TU A_TU; host set_seed SEED_R1; the host's real-UI walk of S to R1_DEST.
       RN1-walk  one new host context W {host, walk, S}
       RN1-none  no `reaction` context nested in W
       RN1-dest  S's executed path RN1_PATH, not halted, S on R1_DEST on both
  RNK  a kneel still draws reaction fire (QU6-1 (a), `main` parity, a guard): S back on its TILES tile facing 0, TU S_TU;
       A reactions 100 and TU A_TU; the host TABs to S, host set_seed SEED_RNK, ONE real kneel key.
       RNK-react one new {host, kneel, S} and exactly one `reaction` {actorId A, nestedIn it} with a shot by A; S after
                 it = S_AFTER_RNK on both
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: the host's options.cfg line, host infoboxes, the client's messages, both cameras.
The kneel's reaction burst runs after the kneel context closed, with the host's busyOwnerSeat at -1, so
RNK waits on the chain itself (host isBusy false, no pending state, the client caught up) before it reads anything.

RED on the unchanged build (commit A1): RN2-none, RN2-dest, RN1-none, RN1-dest; every other cell PASS. One EVIDENCE line
per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound
prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it "staging".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_reaction_option.py
"""

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
from test_seat_pacing import tab_select  # noqa: E402
from test_client_shoot import new_contexts, set_tu_both, place  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402
from test_messages import poll_host_box, client_quiet  # noqa: E402

KEY = "49060"
HOST_OPTIONS = {"EnableReactionFirePvp": False}   # the host's option off; the client keeps its default (true)
A_ID, S_ID, S3_ID = RM.A_ID, RM.S_ID, RM.S3_ID     # the alien (client, seat 1); RN1's walker / RNK's kneeler; RN2's reactor
A_HOME, A_DIR = RM.TILES[A_ID]                    # (15,2,0) facing 4
S_HOME, S_DIR = RM.TILES[S_ID]                    # (15,9,0) facing 0
R2_DEST, R1_DEST, A_TU = RM.R2_DEST, RM.R1_DEST, RM.A_TU
RN2_PATH = [(15, 3, 0), (15, 4, 0)]               # TASK 0 RAa: the reactors-0 stand-in's walk of A (not halted)
RN1_PATH = [(16, 9, 0), (17, 9, 0)]               # TASK 0 rh2: the reactors-0 stand-in's walk of S (not halted)
SEED_R2 = 1                                       # R5-U3's R2 recipe
SEED_R1 = 2                                       # the first seed leaving S alive and unhurt on red (rh2 = rh2b)
SEED_RNK = 2                                      # the first kneel seed leaving S in (seed 1 kills S; rk2 = rk2b)
S_TU = 64                                         # S's TU at side 0 turn 2, restored before the kneel
SDLK_K = 107                                      # Options::keyBattleKneel default (test_reaction_prox SDLK_K)
S_AFTER_RNK = {"health": 40, "stun": 0, "isOut": False, "kneeled": True}   # rk2 = rk2b: three snaps, S unhurt
STEP_S = RM.STEP_S                                # every bounded wait (30 s)
CHAIN_S = 20                                      # the kneel's reaction burst (TASK 0: 2.9 s)
ROWS = (("RN2", ("RN2-walk", "RN2-none", "RN2-dest", "RN2-common")),
        ("RN1", ("RN1-walk", "RN1-none", "RN1-dest", "RN1-common")),
        ("RNK", ("RNK-react", "RNK-common")))


def es(gc, key):
    return event_state(gc).get(key)


def cv(c):
    return {k: c.get(k) for k in ("actionId", "origin", "kind", "actorId", "nestedIn")}


def pts(seq):
    return [(p.get("x"), p.get("y"), p.get("z")) for p in (seq or [])]


def walk_view(gc):
    w = es(gc, "lastWalk") or {}
    return {"actionId": w.get("actionId"), "executed": pts(w.get("executed")), "halted": w.get("halted"),
            "reason": w.get("reason"), "restate": w.get("restate")}


def uview(gc, uid):
    u = G3F.units(gc).get(uid) or {}
    return {k: u.get(k) for k in ("x", "y", "z", "direction", "tu", "health", "stun", "isOut", "kneeled", "morale",
                                  "reactions", "status")}


def cameras(host, client):
    return {gc.name: es(gc, "camera") for gc in (host, client)}


def walk_cells(row, host, client, ctx0, seq0, origin, walker, path, dest, ev, sent0=None, shots_cell=False):
    """`<row>-walk`, `<row>-none`, `<row>-dest` of a walk that draws NO reaction (the host's option off)."""
    new = new_contexts(ctx0, RM.ctxs(host))
    hev = evs_since(host, seq0)
    walks = [c for c in new if (c.get("origin"), c.get("kind"), c.get("actorId")) == (origin, "walk", walker)]
    wid = walks[0].get("actionId") if len(walks) == 1 else None
    reacts = [c for c in new if c.get("kind") == "reaction" and (wid is None or c.get("nestedIn") == wid)]
    shots = [e["seq"] for e in hev if e["kind"] == "shot"]
    views = [walk_view(host), walk_view(client)]
    pos = [G3F.pos(gc, walker) for gc in (host, client)]
    ev.update(newCtx=[cv(c) for c in new], hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev],
              lastWalk=views, pos=pos, walker=[uview(host, walker), uview(client, walker)])
    wk = []
    if len(walks) != 1:
        wk.append(f"new host contexts {ev['newCtx']} (want exactly one {{{origin}, walk, {walker}}})")
    if sent0 is not None:
        d = (es(client, "coopIntentsSent") or {}).get("walk", 0) - sent0.get("walk", 0)
        if d != 1 or es(client, "inFlight") is not None:
            wk.append(f"client coopIntentsSent.walk +{d} (want +1), inFlight {es(client, 'inFlight')} (want None)")
    no = []
    if reacts:
        no.append(f"reaction contexts {[cv(c) for c in reacts]} nested in the walk (want none)")
    if shots_cell and shots:
        no.append(f"shot evs {shots} in the row (want none)")
    dd = []
    for gc, v, p in zip((host, client), views, pos):
        rs = v["restate"] or {}
        if (v["actionId"] != wid or v["executed"] != path or v["halted"] is not False or pts(rs.get("path")) != path
                or rs.get("halted") is not False or p != dest):
            dd.append(f"{gc.name}: lastWalk {v['actionId']} executed {v['executed']} halted {v['halted']} "
                      f"({v['reason']}), restate path {pts(rs.get('path'))} halted {rs.get('halted')}, {walker} on {p} "
                      f"(want walk {wid}, path {path}, not halted, on {dest})")
    if views[0]["restate"] != views[1]["restate"]:
        dd.append(f"lastWalk.restate host {views[0]['restate']} != client {views[1]['restate']}")
    return {f"{row}-walk": (not wk, "; ".join(wk) or f"one {{{origin}, walk, {walker}}}"),
            f"{row}-none": (not no, "; ".join(no) or "no reaction nested in the walk" + (", no shot" if shots_cell else "")),
            f"{row}-dest": (not dd, "; ".join(dd) or f"path {path}, not halted, {walker} on {dest} on both, restate equal")}


# ===================== rows =====================


def row_rn2(host, client, crash0, st):
    ev = dict(st)
    RM.stat_both(host, client, S3_ID, "reactions", 100)
    RM.stat_both(host, client, S3_ID, "firing", 0)
    ev["s3Tu"] = set_tu_both(host, client, S3_ID, 255)
    seq0, ctx0, prev = es(host, "lastSeqEmitted") or 0, RM.ctxs(host), session.walk_action_id(host)
    sent0 = dict(es(client, "coopIntentsSent") or {})
    host.ok({"cmd": "set_seed", "seed": SEED_R2})
    ev["walk"] = session.send_walk(client, A_ID, R2_DEST)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    RM.settle(host, client, ev)
    cells = walk_cells("RN2", host, client, ctx0, seq0, "intent", A_ID, RN2_PATH, R2_DEST, ev, sent0, shots_cell=True)
    cells["RN2-common"] = G3F.common(host, client, crash0)
    ev["cameras"] = cameras(host, client)
    return cells, ev


def row_rn1(host, client, crash0):
    ev = {"afterRn2": place(host, client, A_ID, A_HOME, A_DIR)}   # S2: kept when A never left its tile
    RM.stat_both(host, client, S3_ID, "reactions", 0)
    RM.side_change(host, client, client, RM.FACTION_PLAYER, 2, ev)
    g = RM.give_both(host, client, A_ID, RM.PISTOL, RM.CLIP)
    RM.stat_both(host, client, A_ID, "reactions", 100)
    RM.stat_both(host, client, A_ID, "firing", 0)
    ev["aTu"] = RM.stat_both(host, client, A_ID, "tu", A_TU, refill=True)["tu"]
    ev.update(pistol=(g["weaponId"], g["ammoId"]), sBefore=[uview(host, S_ID), uview(client, S_ID)])
    ev["tab"] = tab_select(host, S_ID)
    seq0, ctx0 = es(host, "lastSeqEmitted") or 0, RM.ctxs(host)
    try:
        RM.host_walk(host, client, S_ID, R1_DEST, ev, seed=SEED_R1)
    except Exception as e:
        ev["walkError"] = str(e)[:300]
    cells = walk_cells("RN1", host, client, ctx0, seq0, "host", S_ID, RN1_PATH, R1_DEST, ev)
    ev["A"] = [uview(host, A_ID), uview(client, A_ID)]
    cells["RN1-common"] = G3F.common(host, client, crash0)
    ev["cameras"] = cameras(host, client)
    return cells, ev


def chain_done(host, client, ctx0):
    kn = [c for c in new_contexts(ctx0, RM.ctxs(host)) if c.get("kind") == "kneel"]
    eh, ec, bh = event_state(host), event_state(client), battle_state(host)
    return (bool(kn) and not bh.get("isBusy") and bh.get("pendingStates") == 0
            and ec.get("lastSeqApplied") == eh.get("lastSeqEmitted") and eh.get("queueDepth") == 0
            and ec.get("queueDepth") == 0)


def row_rnk(host, client, crash0):
    ev, bad = {}, []
    ev["placeS"] = place(host, client, S_ID, S_HOME, S_DIR)
    ev["sTu"] = set_tu_both(host, client, S_ID, S_TU)
    RM.stat_both(host, client, A_ID, "reactions", 100)
    ev["aTuRefill"] = RM.stat_both(host, client, A_ID, "tu", A_TU, refill=True)["tu"]
    ev["aTuBoth"] = [uview(host, A_ID)["tu"], uview(client, A_ID)["tu"]]
    ev["sBefore"] = [uview(host, S_ID), uview(client, S_ID)]
    ev["tab"] = tab_select(host, S_ID)
    if not ev["tab"]:
        bad.append(f"TAB never selected S on the host (selectedId {battle_state(host).get('selectedId')})")
    seq0, ctx0 = es(host, "lastSeqEmitted") or 0, RM.ctxs(host)
    if ev["tab"]:
        host.ok({"cmd": "set_seed", "seed": SEED_RNK})
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
        ev["kneeledWait"] = RM.wait_until(lambda: G3F.units(host).get(S_ID, {}).get("kneeled")
                                          and G3F.units(client).get(S_ID, {}).get("kneeled"), 10, 0.1)
        ev["chainWait"] = RM.wait_until(lambda: chain_done(host, client, ctx0), CHAIN_S, 0.1)
    if ev["tab"] and not ev["chainWait"][0]:
        bad.append(f"the kneel's chain not done in {CHAIN_S} s (host isBusy {battle_state(host).get('isBusy')}, "
                   f"pendingStates {battle_state(host).get('pendingStates')})")
    RM.settle(host, client, ev)
    rec = {"hostBoxes": []}
    poll_host_box(host, rec, "rnk")
    new = new_contexts(ctx0, RM.ctxs(host))
    hev = evs_since(host, seq0)
    kn = [c for c in new if (c.get("origin"), c.get("kind"), c.get("actorId")) == ("host", "kneel", S_ID)]
    reacts = [c for c in new if c.get("kind") == "reaction"]
    rid = reacts[0].get("actionId") if len(reacts) == 1 else None
    pl = host_payloads(host, [e["seq"] for e in hev if e["kind"] == "shot" and e["actionId"] == rid], timeout=3)
    after = [{k: uview(gc, S_ID)[k] for k in S_AFTER_RNK} for gc in (host, client)]
    ev.update(hostBoxes=rec["hostBoxes"], newCtx=[cv(c) for c in new], after=after, A=[uview(host, A_ID),
              uview(client, A_ID)], hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev],
              shots=[(v["payload"].get("actor"), v["payload"].get("impact")) for v in pl.values()])
    if len(kn) != 1:
        bad.append(f"new host contexts {ev['newCtx']} (want exactly one {{host, kneel, {S_ID}}})")
    if len(reacts) != 1 or reacts[0].get("actorId") != A_ID or not kn or reacts[0].get("nestedIn") != kn[0].get("actionId"):
        bad.append(f"reaction contexts {[cv(c) for c in reacts]} (want exactly one by {A_ID} nested in the kneel)")
    if not any(v["payload"].get("actor") == A_ID for v in pl.values()):
        bad.append(f"shots in the reaction context {ev['shots']} (want a shot by {A_ID})")
    if after != [S_AFTER_RNK] * 2:
        bad.append(f"S after the kneel host/client {after} (want {S_AFTER_RNK} on both)")
    cells = {"RNK-react": (not bad, "; ".join(bad) or f"one {{host, kneel, {S_ID}}}, one reaction by {A_ID} nested in "
                                                       f"it with a shot; S {S_AFTER_RNK} on both")}
    cells["RNK-common"] = G3F.common(host, client, crash0)
    ev["cameras"] = cameras(host, client)
    return cells, ev


# ===================== boot RA =====================


def opt_line(gc):
    try:
        with open(os.path.join(gc.user_dir, "options.cfg"), encoding="utf-8") as f:
            return [ln.strip() for ln in f if "EnableReactionFirePvp" in ln]
    except OSError as e:
        return [f"unreadable: {e}"]


def boot_ra():
    host = GameClient("host", None, make_user_dir("r5u6_ra_host", options=HOST_OPTIONS))
    client = GameClient("client", None, make_user_dir("r5u6_ra_client"))
    m = (host, client)
    try:
        st = {"optionsCfg": {"host": opt_line(host), "client": opt_line(client)}}
        try:
            G3F.guarded("RA", lambda: BER.boot_e6(host, client, KEY), m)
            G3F.guarded("RA", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE RA line)")
        try:
            st["stage"] = RM.stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("RN2", rows["RN2"], lambda: row_rn2(host, client, crash0, st))
        fails += G3F.run_row("RN1", rows["RN1"], lambda: row_rn1(host, client, crash0))
        fails += G3F.run_row("RNK", rows["RNK"], lambda: row_rnk(host, client, crash0))
        print(f"EVIDENCE quiet: {client_quiet(client)}", flush=True)
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_ra()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_reaction_option: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
