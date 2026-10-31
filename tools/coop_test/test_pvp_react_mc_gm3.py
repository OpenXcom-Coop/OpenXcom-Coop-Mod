"""PvP reaction fire and mind control both ways in gm3 (the HOST plays the aliens, seat 0; the partner the seven X-COM
soldiers, seat 1), and the host's own alien side panicking at its start: the human alien side plays by the player-side
rules vanilla gives X-COM.

The helpers, tiles and most constants come from test_pvp_react_mc.py (the gm2 version of this test). Every real-UI
order the host gives after its own alien acted starts with `reset` (one right click on NEXT-SOLDIER, one TAB,
tab_select), so the order does not depend on the cursor the previous one left behind. The ids and tiles were measured
equal on two boots without the fix.

Boot (key 48679): G3F.bring_up (gm3, STR_SMALL_SCOUT, map seed 1), every live unit's reactions 0, the staging
(test_pvp_react_mc's tiles; S6 = xcom_mc's psi attacker), the partner's END TURN -> side 1 turn 1 (the host's aliens).
  xcom_reacts  X-COM reacts to the host's alien walk: S3 reactions 100, firing 0, TU; one TAB + tab_select(A); host
      set_seed XCOM_REACT_SEED; the host's real-UI walk of A.
      xcom_reacts-walk / xcom_reacts-react / xcom_reacts-alive   W {host, walk, A}; one reaction {S3, nestedIn W} with
                         a shot by S3, halted `reaction` on both; A not out, health equal
  alien_mc  the host's alien mind-controls the partner's soldier and the host commands it: S3 reactions 0; the amp on
      A, A psiSkill 100, S2 psiStrength 0, TU; S2 in A's spottedThisTurn on the host (staging); the reset.
      alien_mc-ui        the host's real-UI MIND CONTROL on S2 (set_seed ALIEN_MC_SEED): one new host context {host,
                         psi, A}; S2 faction 1, mindControllerId A on both
      alien_mc-ctrl      S2's TU cap refilled; the reset onto S2; the host's real-UI walk of S2 to
                         CONTROLLED_WALK_DEST: {host, walk, S2}, S2 on CONTROLLED_WALK_DEST on both; the partner's
                         battle_intent turn for S2 denied not_your_unit
      After alien_mc: S2 TU 0, reactions 0 (both).
  alien_reacts  the host's alien reacts to the partner's walk: the host's END TURN -> side 0 turn 2; A's pistol back
      (test command); A reactions 100, firing 0, TU; host set_seed ALIEN_REACT_SEED; the partner's send_walk of S.
      alien_reacts-walk / alien_reacts-react / alien_reacts-alive   W {intent, walk, S} (+1 sent); one reaction {A,
                         nestedIn W}, a shot by A, halted `reaction`; S not out, health equal
      alien_reacts-ai    hasAI false for A on both
  alien_panic  the host's own alien side panics at its start: A reactions 0, morale 0 (both); host set_seed PANIC_SEED
      right before the partner's END TURN; A read on both before any NextTurnState closes; drive_side_change to side
      1; a bounded wait (PANIC_S) for the host's `panic` ev; host infoboxes host-only.
      alien_panic-roll   A status 8 (PANICKING) on both at the roll (precondition)
      alien_panic-act    exactly one host `panic` ev {unit A, mode flee or freeze} and its bt_action_end on the same
                         actionId; the client applied the same seqs
      alien_panic-after  A status 0, TU 0, morale ROLL_MORALE + 15 on both
  xcom_mc  the partner's soldier mind-controls the host's alien and commands it: A set back to {status 0, TU, morale
      100} (both); the host's END TURN -> side 0 turn 3; the amp on S6, S6 psiSkill 100, A psiStrength 0, S6's TU.
      xcom_mc-ui         the partner's real-UI MIND CONTROL on A (set_seed XCOM_MC_SEED): one new host context
                         {intent, psi, S6}; psi +1; A faction 0, mindControllerId S6 on both
      xcom_mc-ctrl       A's TU cap refilled; the partner's battle_intent turn for A admitted {intent, turn, A}; A's
                         facing changed and equal on both
      xcom_mc is the last row (no END TURN after it).
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in this
harness slot's crash folder. Every mind-control order waits out the client's own message box (RM.mc_order).

Without the fix, alien_mc-ui, alien_mc-ctrl and alien_reacts-ai FAIL; every other cell passes. One EVIDENCE line per
row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its bound
prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails the rows that need it
"staging". ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pvp_react_mc_gm3.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_seat_pacing import tab_select, SDLK_TAB  # noqa: E402
from test_turn_baton import RHAND_NTH, click_nth  # noqa: E402
from test_client_shoot import set_tu_both  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402
from test_messages import poll_host_box, client_quiet  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
from test_pvp_react_mc import es, ctxs, unit, uv, cv, wait_until, settle, stat_both, give_both  # noqa: E402

KEY = "48679"
A_ID = RM.A_ID                    # the host's alien (gm3 seat 0, FACTION_HOSTILE)
# S: alien_reacts' walker; S3: xcom_reacts' reactor; S2: alien_mc's target; S6: xcom_mc's psi attacker
S_ID, S3_ID, S2_ID, S6_ID = 8, 9, 10, 11
TILES = {uid: RM.TILES[uid] for uid in (A_ID, S_ID, S3_ID, S2_ID, 12, 13, 14)}
TILES[S6_ID] = RM.TILES[11]       # test_pvp_react_mc's S4 tile (18,8,0) dir 0
ALIEN_WALK_DEST = RM.ALIEN_WALK_DEST       # (15,4,0): XCOM_REACT_SEED halts A after (15,3,0)
SOLDIER_WALK_DEST = RM.SOLDIER_WALK_DEST   # (17,9,0): ALIEN_REACT_SEED halts S after (16,9,0)
CONTROLLED_WALK_DEST = (11, 7, 0)          # S2 one tile west
A_TU, S2_TU = RM.A_TU, RM.S2_TU   # 54 / 58
XCOM_REACT_SEED = ALIEN_MC_SEED = ALIEN_REACT_SEED = PANIC_SEED = XCOM_MC_SEED = 1
ROLL_MORALE = 0                   # A's morale after the panic roll; alien_panic-after wants ROLL_MORALE + 15
STATUS_STANDING, STATUS_PANICKING = 0, 8
FACTION_PLAYER, FACTION_HOSTILE = RM.FACTION_PLAYER, RM.FACTION_HOSTILE
PANIC_S, STEP_S, ORDER_S = 15, RM.STEP_S, RM.ORDER_S
ROWS = (("xcom_reacts", ("xcom_reacts-walk", "xcom_reacts-react", "xcom_reacts-alive", "xcom_reacts-common")),
        ("alien_mc", ("alien_mc-ui", "alien_mc-ctrl", "alien_mc-common")),
        ("alien_reacts", ("alien_reacts-walk", "alien_reacts-react", "alien_reacts-alive", "alien_reacts-ai",
                          "alien_reacts-common")),
        ("alien_panic", ("alien_panic-roll", "alien_panic-act", "alien_panic-after", "alien_panic-common")),
        ("xcom_mc", ("xcom_mc-ui", "xcom_mc-ctrl", "xcom_mc-common")))


def probe(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("cursorType", "selectedId", "warningText")}


def icon_nth(gc, col_i, row_i):
    """The click_widget nth of the icon in column `col_i`, row `row_i` (0 upper) of the seven 32x16 icon columns
    (test_pvp_host_cursor's rule); NEXT-SOLDIER = (4, 0), BattlescapeState.cpp :164."""
    ws = gc.cmd({"cmd": "list_widgets"}).get("widgets", [])
    cands = [w for w in ws if w.get("w") == 32 and w.get("h") == 16 and w.get("interactive") and w.get("visible")]
    xs = sorted({w["x"] for w in cands})
    assert len(xs) == 7, f"icon columns {xs} (want 7)"
    col = sorted([w for w in cands if w["x"] == xs[col_i]], key=lambda w: w["y"])
    assert len(col) == 2, f"icon column {col_i}: {col}"
    nth = 0
    for w in ws:
        if w["idx"] == col[row_i]["idx"]:
            return nth
        if w.get("visible") and w.get("interactive"):
            nth += 1
    raise AssertionError("icon vanished")


def reset(host, uid, ev):
    """ONE right click on NEXT-SOLDIER (the one input a hidden pointer lets through), ONE TAB, tab_select(uid): the
    host has its cursor back with `uid` selected. Records the host's probe before / after and the selected unit."""
    ev["before"] = probe(host)
    click_nth(host, icon_nth(host, 4, 0), "right")
    ev["afterRight"] = probe(host)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
    time.sleep(0.15)
    ev["tab"] = tab_select(host, uid)
    ev["after"] = probe(host)


# ===================== rows =====================


def row_xcom_reacts(host, client, crash0, st):
    ev = dict(st)
    stat_both(host, client, S3_ID, "reactions", 100)
    stat_both(host, client, S3_ID, "firing", 0)
    ev["s3Tu"] = set_tu_both(host, client, S3_ID, 255)
    ev["sel0"] = probe(host)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})   # ONE TAB first, as test_pvp_gm3's host_ui_walk
    time.sleep(0.15)
    ev["tab"] = tab_select(host, A_ID)
    seq0, ctx0 = es(host, "lastSeqEmitted") or 0, ctxs(host)
    try:
        RM.host_walk(host, client, A_ID, ALIEN_WALK_DEST, ev, seed=XCOM_REACT_SEED)
    except Exception as e:
        ev["walkError"] = str(e)[:300]
    cells = RM.walk_react("xcom_reacts", host, client, ctx0, seq0, "host", A_ID, S3_ID, ev)
    cells["xcom_reacts-alive"] = RM.alive_cell(host, client, A_ID)
    ev.update(A=[uv(host, A_ID), uv(client, A_ID)], probeAfter=probe(host))
    stat_both(host, client, S3_ID, "reactions", 0)
    cells["xcom_reacts-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_alien_mc(host, client, crash0):
    ev, cells = {}, {}
    ev["amp"] = give_both(host, client, A_ID, RM.PSI_AMP)["weaponId"]
    stat_both(host, client, A_ID, "psiSkill", 100)
    stat_both(host, client, S2_ID, "psiStrength", 0)
    set_tu_both(host, client, A_ID, A_TU)
    seen = ev["aSpotted"] = unit(host, A_ID).get("spottedThisTurn") or []
    if S2_ID not in seen:
        why = f"staging (A spottedThisTurn on the host {seen} lacks S2 {S2_ID})"
        cells = {n: (False, why) for n in ("alien_mc-ui", "alien_mc-ctrl")}
        cells["alien_mc-common"] = G3F.common(host, client, crash0)
        return cells, ev
    ui = ev["ui"] = {}
    reset(host, A_ID, ui.setdefault("reset", {}))
    ctx0 = ctxs(host)
    try:
        assert ui["reset"]["after"]["selectedId"] == A_ID, f"host selectedId after the reset {ui['reset']['after']}"
        RM.psi_press(host, host, RM.TILES[S2_ID][0], ALIEN_MC_SEED, ui)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = RM.mc_order(host, client, ctx0, S2_ID, ui)
    ui["probeAfter"] = probe(host)
    cells["alien_mc-ui"] = RM.mc_cell(new, "host", A_ID, host, client, S2_ID, FACTION_HOSTILE, ui)
    ctl = ev["ctrl"] = {}
    s2 = [(uv(gc, S2_ID)["faction"], uv(gc, S2_ID)["mindControllerId"]) for gc in (host, client)]
    mced = s2 == [(FACTION_HOSTILE, A_ID)] * 2
    reset(host, S2_ID if mced else A_ID, ctl.setdefault("reset", {}))   # also ends a leftover psi targeting
    if not mced:
        cells["alien_mc-ctrl"] = (False, f"S2 (faction, mindControllerId) host/client {s2} (want (1, {A_ID})): not "
                                         f"mind-controlled, no order sent")
    else:
        cap = stat_both(host, client, S2_ID, "tu", S2_TU, refill=True)["tu"]
        try:
            wnew = RM.host_walk(host, client, S2_ID, CONTROLLED_WALK_DEST, ctl)
        except Exception as e:
            wnew, ctl["walkError"] = [], str(e)[:300]
        ps = [G3F.pos(gc, S2_ID) for gc in (host, client)]
        tnew, deny = RM.turn_order(host, client, S2_ID, (uv(client, S2_ID)["direction"] + 2) % 8, ctl)
        ctl.update(cap=cap, walkCtx=[cv(c) for c in wnew], pos=ps, turnCtx=[cv(c) for c in tnew])
        cells["alien_mc-ctrl"] = (cap == S2_TU and RM.ctx_ok(wnew, "host", "walk", S2_ID)
                                  and ps == [CONTROLLED_WALK_DEST] * 2 and not tnew
                                  and (deny or {}).get("reason") == "not_your_unit",
                                  f"S2 TU refill {cap} (want {S2_TU}); walk contexts {ctl['walkCtx']} (want one "
                                  f"{{host, walk, {S2_ID}}}); S2 host/partner {ps} (want {CONTROLLED_WALK_DEST}); "
                                  f"the partner's turn: contexts {ctl['turnCtx']} (want none), deny {deny} (want "
                                  f"not_your_unit)")
    set_tu_both(host, client, S2_ID, 0)
    stat_both(host, client, S2_ID, "reactions", 0)
    cells["alien_mc-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_alien_reacts(host, client, crash0):
    ev = {}
    RM.side_change(host, client, host, FACTION_PLAYER, 2, ev)
    g = give_both(host, client, A_ID, RM.PISTOL, RM.CLIP)
    stat_both(host, client, A_ID, "reactions", 100)
    stat_both(host, client, A_ID, "firing", 0)
    stat_both(host, client, A_ID, "tu", A_TU, refill=True)
    ev["pistol"] = (g["weaponId"], g["ammoId"])
    seq0, ctx0, prev = es(host, "lastSeqEmitted") or 0, ctxs(host), session.walk_action_id(host)
    sent0 = dict(es(client, "coopIntentsSent") or {})
    host.ok({"cmd": "set_seed", "seed": ALIEN_REACT_SEED})
    ev["walk"] = session.send_walk(client, S_ID, SOLDIER_WALK_DEST)
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    settle(host, client, ev)
    cells = RM.walk_react("alien_reacts", host, client, ctx0, seq0, "intent", S_ID, A_ID, ev, sent0)
    cells["alien_reacts-alive"] = RM.alive_cell(host, client, S_ID)
    cells["alien_reacts-ai"] = RM.ai_cell(host, client)
    ev["S"] = [uv(host, S_ID), uv(client, S_ID)]
    cells["alien_reacts-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_alien_panic(host, client, crash0):
    ev, cells = {}, {}
    stat_both(host, client, A_ID, "reactions", 0)
    RM.both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "morale": 0}, ("morale",))
    seq0 = es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": PANIC_SEED})
    ev["press"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, ev["sideS"] = wait_until(lambda: battle_state(host).get("side") == 1 and battle_state(client).get("side") == 1,
                                 STEP_S, 0.1)
    roll = [uv(host, A_ID), uv(client, A_ID)]
    ev.update(roll=roll, rollStacks=[G3F.stack(host), G3F.stack(client)])
    cells["alien_panic-roll"] = (ok and [r["status"] for r in roll] == [STATUS_PANICKING] * 2,
                                 f"side 1 on both {ok} ({ev['sideS']} s); A status host/client at the roll "
                                 f"{[r['status'] for r in roll]} (want [8, 8], PANIC_SEED {PANIC_SEED})")
    try:
        drive_side_change(host, client, FACTION_HOSTILE, timeout=STEP_S)
    except Exception as e:
        ev["sideError"] = str(e)[:300]
    rec, closed = {"hostBoxes": []}, []

    def panic_done():
        poll_host_box(host, rec, "alien_panic")
        for gc in (host, client):
            if G3F.top(gc) == "NextTurnState":
                gc.cmd({"cmd": "close_nextturn"})
                closed.append(gc.name)
        hev = evs_since(host, seq0)
        pids = [e["actionId"] for e in hev if e["kind"] == "panic"]
        return bool(pids) and any(e["kind"] == "bt_action_end" and e["actionId"] == pids[0] for e in hev) \
            and es(host, "busyOwnerSeat") == -1
    ev["panicWait"] = wait_until(panic_done, PANIC_S)
    settle(host, client, ev)
    poll_host_box(host, rec, "alien_panic after")
    ev["quiet"] = client_quiet(client)
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    cmap = {e["seq"]: (e["kind"], e["actionId"]) for e in cev}
    panics = [e for e in hev if e["kind"] == "panic"]
    pl = host_payloads(host, [e["seq"] for e in panics], timeout=3) if panics else {}
    ev.update(hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev], hostBoxes=rec["hostBoxes"],
              leftoverClosed=closed, panicPayloads={s: v.get("payload") for s, v in pl.items()},
              warningText=[battle_state(gc).get("warningText") for gc in (host, client)])
    act = []
    if len(panics) != 1:
        act.append(f"host panic evs {[(e['seq'], e['actionId']) for e in panics]} (want exactly one)")
    else:
        aid = panics[0]["actionId"]
        payload = (pl.get(panics[0]["seq"]) or {}).get("payload") or {}
        mine = [e for e in hev if e["actionId"] == aid]
        ends = [e["seq"] for e in mine if e["kind"] == "bt_action_end"]
        if payload.get("unit") != A_ID or payload.get("mode") not in ("flee", "freeze"):
            act.append(f"panic payload {payload} (want unit {A_ID}, mode flee or freeze)")
        if len(ends) != 1:
            act.append(f"bt_action_end evs of actionId {aid}: {ends} (want exactly one)")
        bad = [(e["seq"], e["kind"], cmap.get(e["seq"])) for e in mine if cmap.get(e["seq"]) != (e["kind"], aid)]
        if bad:
            act.append(f"client log lacks the host's evs of actionId {aid}: (seq, kind, client entry) {bad}")
    cells["alien_panic-act"] = (not act, "; ".join(act) or f"one panic ev {ev['panicPayloads']} and its "
                                                           f"bt_action_end, the client the same seqs")
    after = [uv(host, A_ID), uv(client, A_ID)]
    ev["after"] = after
    want = (STATUS_STANDING, 0, ROLL_MORALE + 15)
    got = [(a["status"], a["tu"], a["morale"]) for a in after]
    cells["alien_panic-after"] = (got == [want, want],
                                  f"A (status, TU, morale) host/client {got} (want {want} on both)")
    cells["alien_panic-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_xcom_mc(host, client, crash0):
    ev, cells = {}, {}
    RM.both(host, client, {"cmd": "battle_set_unit_state", "unit": A_ID, "status": STATUS_STANDING, "tu": A_TU,
                           "morale": 100}, ("status", "tu", "morale"))
    RM.side_change(host, client, host, FACTION_PLAYER, 3, ev)
    ev["amp"] = give_both(host, client, S6_ID, RM.PSI_AMP)["weaponId"]
    stat_both(host, client, S6_ID, "psiSkill", 100)
    stat_both(host, client, A_ID, "psiStrength", 0)
    ev["s6Tu"] = set_tu_both(host, client, S6_ID, 255)
    ev.update(spotted=battle_state(host).get("spotted"), A=[uv(host, A_ID), uv(client, A_ID)])
    ui = ev["ui"] = {}
    ctx0, sent0 = ctxs(host), dict(es(client, "coopIntentsSent") or {})
    try:
        ui["tab"] = tab_select(client, S6_ID)
        RM.psi_press(client, host, G3F.pos(host, A_ID), XCOM_MC_SEED, ui)
    except Exception as e:
        ui["pressError"] = str(e)[:300]
    new = RM.mc_order(host, client, ctx0, A_ID, ui)
    c1 = battle_state(client).get("cursorType")
    if c1 in RM.CURSOR_TARGETING and ui["clientMap"][0]:
        click_nth(client, RHAND_NTH)
    ui["cancel"] = [c1, battle_state(client).get("cursorType")]
    sent = (es(client, "coopIntentsSent") or {}).get("psi", 0) - sent0.get("psi", 0)
    cells["xcom_mc-ui"] = RM.mc_cell(new, "intent", S6_ID, host, client, A_ID, FACTION_PLAYER, ui, sent)
    ctl = ev["ctrl"] = {}
    a = [(uv(gc, A_ID)["faction"], uv(gc, A_ID)["mindControllerId"]) for gc in (host, client)]
    if a != [(FACTION_PLAYER, S6_ID)] * 2:
        cells["xcom_mc-ctrl"] = (False, f"A (faction, mindControllerId) host/partner {a} (want (0, {S6_ID})): not "
                                        f"mind-controlled, no order sent")
    else:
        ctl["tuBefore"] = [uv(gc, A_ID)["tu"] for gc in (host, client)]
        cap = stat_both(host, client, A_ID, "tu", A_TU, refill=True)["tu"]
        d0 = uv(client, A_ID)["direction"]
        tnew, deny = RM.turn_order(host, client, A_ID, (d0 + 2) % 8, ctl)
        dirs = [uv(gc, A_ID)["direction"] for gc in (host, client)]
        ctl.update(cap=cap, d0=d0, dirs=dirs, turnCtx=[cv(c) for c in tnew])
        cells["xcom_mc-ctrl"] = (cap == A_TU and RM.ctx_ok(tnew, "intent", "turn", A_ID) and deny is None
                                 and dirs[0] == dirs[1] != d0,
                                 f"A TU refill {cap} (want {A_TU}); turn contexts {ctl['turnCtx']} (want one "
                                 f"{{intent, turn, {A_ID}}}), deny {deny} (want none); direction {d0} -> host/partner "
                                 f"{dirs} (want changed and equal)")
    cells["xcom_mc-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot =====================


def stage(host, client):
    ev = {"placed": RM.stage_tiles(host, client, TILES, (ALIEN_WALK_DEST, SOLDIER_WALK_DEST, CONTROLLED_WALK_DEST))}
    m = (host, client)
    g = G3F.guarded("staging", lambda: give_both(host, client, A_ID, RM.PISTOL, RM.CLIP), m)
    ev["aPistol"] = (g["weaponId"], g["ammoId"])
    g = G3F.guarded("staging", lambda: give_both(host, client, S3_ID, "STR_RIFLE", "STR_RIFLE_CLIP"), m)
    ev["s3Rifle"] = (g["weaponId"], g["ammoId"])
    side = {}
    G3F.guarded("staging", lambda: RM.side_change(host, client, client, FACTION_HOSTILE, 1, side), m)
    ev.update(side=side, hash=G3F.hash_now(host, client))
    return ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pvp_react_mc_gm3_host"))
    client = GameClient("client", None, make_user_dir("pvp_react_mc_gm3_client"))
    m = (host, client)
    try:
        try:
            _boot, crash0 = G3F.bring_up(host, client, KEY, "gm3")
            G3F.guarded("gm3", lambda: G3F.reactions_zero(host, client), m)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE gm3 line)")
        try:
            st = stage(host, client)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("xcom_reacts", rows["xcom_reacts"], lambda: row_xcom_reacts(host, client, crash0, st))
        fails += G3F.run_row("alien_mc", rows["alien_mc"], lambda: row_alien_mc(host, client, crash0))
        fails += G3F.run_row("alien_reacts", rows["alien_reacts"], lambda: row_alien_reacts(host, client, crash0))
        fails += G3F.run_row("alien_panic", rows["alien_panic"], lambda: row_alien_panic(host, client, crash0))
        fails += G3F.run_row("xcom_mc", rows["xcom_mc"], lambda: row_xcom_mc(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pvp_react_mc_gm3: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
