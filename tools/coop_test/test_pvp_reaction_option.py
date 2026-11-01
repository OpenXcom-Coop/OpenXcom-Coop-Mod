"""PvP reaction fire option in gm2 (the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0)
with the HOST's "Enable Reaction Fire in PvP" off (its options.cfg `EnableReactionFirePvp: false`; the client keeps
the default): a walking unit in a PvP battle draws no reaction fire, a kneel still does. The walk step is the one
trigger the option gates, as in the released game (its UnitWalkBState :465); the host's value counts, taken when the
battle starts.

The paths and seeds below were measured without the fix, each on two boots.

Boot (key 49060): BER.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's reactions 0,
test_pvp_react_mc's staging (RM.stage: TILES, A's plasma pistol, S3's rifle, the host's END TURN -> side 1 turn 1).
  xcom_holds_fire  X-COM does not react to the alien seat's walk: S3 reactions 100, firing 0, TU 255; host set_seed
       ALIEN_WALK_SEED; the client's send_walk of A to ALIEN_WALK_DEST.
       xcom_holds_fire-walk  one new host context W {intent, walk, A}; the client's coopIntentsSent.walk +1, inFlight
                             null
       xcom_holds_fire-none  no `reaction` context nested in W; no `shot` ev in the row
       xcom_holds_fire-dest  A's executed path ALIEN_WALK_PATH, not halted, A on ALIEN_WALK_DEST on both;
                             lastWalk.restate equal on both
       After xcom_holds_fire: A back on its TILES tile facing 4; S3 reactions 0.
  alien_holds_fire  the alien does not react to the X-COM host's walk: the client's END TURN -> side 0 turn 2; A's
       pistol (test command), reactions 100, firing 0, TU A_TU; host set_seed SOLDIER_WALK_SEED; the host's real-UI
       walk of S to SOLDIER_WALK_DEST.
       alien_holds_fire-walk  one new host context W {host, walk, S}
       alien_holds_fire-none  no `reaction` context nested in W
       alien_holds_fire-dest  S's executed path SOLDIER_WALK_PATH, not halted, S on SOLDIER_WALK_DEST on both
  kneel_draws_fire  a kneel still draws reaction fire (as in the released game; a guard: it passes with and without
       the fix): S back on its TILES tile facing 0, TU S_TU; A reactions 100 and TU A_TU (refilled); the host TABs to
       S, host set_seed KNEEL_SEED, ONE real kneel key.
       kneel_draws_fire-react  one new {host, kneel, S} and exactly one `reaction` {actorId A, nestedIn it} with a
                               shot by A; S after it = S_AFTER_KNEEL on both
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this
harness slot's crash folder. EVIDENCE only: the host's options.cfg line, host infoboxes, the client's messages, both
cameras. The kneel's reaction burst runs after the kneel context closed, with the host's busyOwnerSeat at -1, so
kneel_draws_fire waits on the chain itself (host isBusy false, no pending state, the client caught up) before it reads
anything.

Without the fix, xcom_holds_fire-none, xcom_holds_fire-dest, alien_holds_fire-none and alien_holds_fire-dest FAIL;
every other cell passes. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs
after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its
bound fails the rows that need it "staging". ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.

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
# A: the alien (client, seat 1); S: alien_holds_fire's walker and kneel_draws_fire's kneeler; S3: xcom_holds_fire's
# reactor
A_ID, S_ID, S3_ID = RM.A_ID, RM.S_ID, RM.S3_ID
A_HOME, A_DIR = RM.TILES[A_ID]                    # (15,2,0) facing 4
S_HOME, S_DIR = RM.TILES[S_ID]                    # (15,9,0) facing 0
ALIEN_WALK_DEST, SOLDIER_WALK_DEST, A_TU = RM.ALIEN_WALK_DEST, RM.SOLDIER_WALK_DEST, RM.A_TU
ALIEN_WALK_PATH = [(15, 3, 0), (15, 4, 0)]        # A's walk with every reactor at reactions 0 (not halted)
SOLDIER_WALK_PATH = [(16, 9, 0), (17, 9, 0)]      # S's walk with every reactor at reactions 0 (not halted)
ALIEN_WALK_SEED = 1                               # test_pvp_react_mc's xcom_reacts seed
SOLDIER_WALK_SEED = 2                             # the first seed that leaves S alive and unhurt without the fix
KNEEL_SEED = 2                                    # the first kneel seed that leaves S standing (seed 1 kills S)
S_TU = 64                                         # S's TU at side 0 turn 2, restored before the kneel
SDLK_K = 107                                      # Options::keyBattleKneel default (test_reaction_prox SDLK_K)
S_AFTER_KNEEL = {"health": 40, "stun": 0, "isOut": False, "kneeled": True}   # three snap shots, S unhurt
STEP_S = RM.STEP_S                                # every bounded wait (30 s)
CHAIN_S = 20                                      # the kneel's reaction burst (measured at 2.9 s)
ROWS = (("xcom_holds_fire", ("xcom_holds_fire-walk", "xcom_holds_fire-none", "xcom_holds_fire-dest",
                             "xcom_holds_fire-common")),
        ("alien_holds_fire", ("alien_holds_fire-walk", "alien_holds_fire-none", "alien_holds_fire-dest",
                              "alien_holds_fire-common")),
        ("kneel_draws_fire", ("kneel_draws_fire-react", "kneel_draws_fire-common")))


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


def row_xcom_holds_fire(host, client, crash0, st):
    ev = dict(st)
    RM.stat_both(host, client, S3_ID, "reactions", 100)
    RM.stat_both(host, client, S3_ID, "firing", 0)
    ev["s3Tu"] = set_tu_both(host, client, S3_ID, 255)
    seq0, ctx0, prev = es(host, "lastSeqEmitted") or 0, RM.ctxs(host), session.walk_action_id(host)
    sent0 = dict(es(client, "coopIntentsSent") or {})
    host.ok({"cmd": "set_seed", "seed": ALIEN_WALK_SEED})
    ev["walk"] = session.send_walk(client, A_ID, ALIEN_WALK_DEST)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    RM.settle(host, client, ev)
    cells = walk_cells("xcom_holds_fire", host, client, ctx0, seq0, "intent", A_ID, ALIEN_WALK_PATH, ALIEN_WALK_DEST,
                       ev, sent0, shots_cell=True)
    cells["xcom_holds_fire-common"] = G3F.common(host, client, crash0)
    ev["cameras"] = cameras(host, client)
    return cells, ev


def row_alien_holds_fire(host, client, crash0):
    ev = {"aBack": place(host, client, A_ID, A_HOME, A_DIR)}   # place sends nothing when A never left its tile
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
        RM.host_walk(host, client, S_ID, SOLDIER_WALK_DEST, ev, seed=SOLDIER_WALK_SEED)
    except Exception as e:
        ev["walkError"] = str(e)[:300]
    cells = walk_cells("alien_holds_fire", host, client, ctx0, seq0, "host", S_ID, SOLDIER_WALK_PATH,
                       SOLDIER_WALK_DEST, ev)
    ev["A"] = [uview(host, A_ID), uview(client, A_ID)]
    cells["alien_holds_fire-common"] = G3F.common(host, client, crash0)
    ev["cameras"] = cameras(host, client)
    return cells, ev


def chain_done(host, client, ctx0):
    kn = [c for c in new_contexts(ctx0, RM.ctxs(host)) if c.get("kind") == "kneel"]
    eh, ec, bh = event_state(host), event_state(client), battle_state(host)
    return (bool(kn) and not bh.get("isBusy") and bh.get("pendingStates") == 0
            and ec.get("lastSeqApplied") == eh.get("lastSeqEmitted") and eh.get("queueDepth") == 0
            and ec.get("queueDepth") == 0)


def row_kneel_draws_fire(host, client, crash0):
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
        host.ok({"cmd": "set_seed", "seed": KNEEL_SEED})
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
        ev["kneeledWait"] = RM.wait_until(lambda: G3F.units(host).get(S_ID, {}).get("kneeled")
                                          and G3F.units(client).get(S_ID, {}).get("kneeled"), 10, 0.1)
        ev["chainWait"] = RM.wait_until(lambda: chain_done(host, client, ctx0), CHAIN_S, 0.1)
    if ev["tab"] and not ev["chainWait"][0]:
        bad.append(f"the kneel's chain not done in {CHAIN_S} s (host isBusy {battle_state(host).get('isBusy')}, "
                   f"pendingStates {battle_state(host).get('pendingStates')})")
    RM.settle(host, client, ev)
    rec = {"hostBoxes": []}
    poll_host_box(host, rec, "kneel_draws_fire")
    new = new_contexts(ctx0, RM.ctxs(host))
    hev = evs_since(host, seq0)
    kn = [c for c in new if (c.get("origin"), c.get("kind"), c.get("actorId")) == ("host", "kneel", S_ID)]
    reacts = [c for c in new if c.get("kind") == "reaction"]
    rid = reacts[0].get("actionId") if len(reacts) == 1 else None
    pl = host_payloads(host, [e["seq"] for e in hev if e["kind"] == "shot" and e["actionId"] == rid], timeout=3)
    after = [{k: uview(gc, S_ID)[k] for k in S_AFTER_KNEEL} for gc in (host, client)]
    ev.update(hostBoxes=rec["hostBoxes"], newCtx=[cv(c) for c in new], after=after, A=[uview(host, A_ID),
              uview(client, A_ID)], hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev],
              shots=[(v["payload"].get("actor"), v["payload"].get("impact")) for v in pl.values()])
    if len(kn) != 1:
        bad.append(f"new host contexts {ev['newCtx']} (want exactly one {{host, kneel, {S_ID}}})")
    if len(reacts) != 1 or reacts[0].get("actorId") != A_ID or not kn or reacts[0].get("nestedIn") != kn[0].get("actionId"):
        bad.append(f"reaction contexts {[cv(c) for c in reacts]} (want exactly one by {A_ID} nested in the kneel)")
    if not any(v["payload"].get("actor") == A_ID for v in pl.values()):
        bad.append(f"shots in the reaction context {ev['shots']} (want a shot by {A_ID})")
    if after != [S_AFTER_KNEEL] * 2:
        bad.append(f"S after the kneel host/client {after} (want {S_AFTER_KNEEL} on both)")
    cells = {"kneel_draws_fire-react": (not bad, "; ".join(bad) or f"one {{host, kneel, {S_ID}}}, one reaction by "
                                                                    f"{A_ID} nested in it with a shot; S "
                                                                    f"{S_AFTER_KNEEL} on both")}
    cells["kneel_draws_fire-common"] = G3F.common(host, client, crash0)
    ev["cameras"] = cameras(host, client)
    return cells, ev


# ===================== boot =====================


def opt_line(gc):
    try:
        with open(os.path.join(gc.user_dir, "options.cfg"), encoding="utf-8") as f:
            return [ln.strip() for ln in f if "EnableReactionFirePvp" in ln]
    except OSError as e:
        return [f"unreadable: {e}"]


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_reaction_option_host", options=HOST_OPTIONS))
    client = GameClient("client", None, make_user_dir("pvp_reaction_option_client"))
    m = (host, client)
    try:
        st = {"optionsCfg": {"host": opt_line(host), "client": opt_line(client)}}
        try:
            G3F.guarded("gm2", lambda: BER.boot_pvp(host, client, KEY), m)
            G3F.guarded("gm2", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE gm2 line)")
        try:
            st["stage"] = RM.stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("xcom_holds_fire", rows["xcom_holds_fire"],
                            lambda: row_xcom_holds_fire(host, client, crash0, st))
        fails += G3F.run_row("alien_holds_fire", rows["alien_holds_fire"],
                             lambda: row_alien_holds_fire(host, client, crash0))
        fails += G3F.run_row("kneel_draws_fire", rows["kneel_draws_fire"],
                             lambda: row_kneel_draws_fire(host, client, crash0))
        print(f"EVIDENCE quiet: {client_quiet(client)}", flush=True)
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_reaction_option: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
