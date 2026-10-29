"""test_pve2_turns.py: in PvE2 (gamemode 4) the AI-run X-COM side moves first, as the released game plays it, and an
alien order given before that is refused.

The boot (key 48863): test_pve2's gm4 bring-up, its steps named as there: the host sets SEED_ROSTER, the lobby puts the
client on Alien (gamemode 2), then the host's own row on Alien (gamemode 4); STR_MEDIUM_SCOUT on map seed SEED_MAP;
both briefings and both pre-battle equip screens; pin_ai_neutral and every live unit's reactions 0 with both Turn 1
screens up; then ONE X-COM soldier, S_AI, is un-pinned (its bring-up TU) and staged far from every alien; only the
client's Turn 1 screen is closed (the host keeps its own up for row early_order_refused).
  early_order_refused  with the host's Turn 1 screen up, the client's walk order for its alien C1 is refused
      turn_over; C1 stays put.
  xcom_moves_first  the host closes its Turn 1 screen: the players' turn-1 side ends by itself (one opening line), the
      X-COM AI moves S_AI, both machines reach side 0 of turn 2; no player order runs before the first side
      transition.
  turn2_walk  on turn 2 the client's walk for C1 is admitted and runs.
  end_turn_cycle  an ordinary END TURN cycle (S_AI pinned again): side 0 of the next turn on both, no second opening.
  aliens_wiped  the host kills every alien: the players' side ends by itself, soldiersDown, both seats lose, both
      machines end on the host's debriefing (the client's is display-only).
Common cell after each row: every hash bucket EQUAL (aliens_wiped: right before the kill), desyncSeen false on both, no
new file in the lane crash folder.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict (early_order_refused's verdict prints
after xcom_moves_first's actions: its C1 read is taken 3 s after the host's close). Every row runs after a failure. A
boot step past its bound prints ONE CAPTURE boot line and fails every cell "boot"; a staging step past its bound fails
early_order_refused "staging". run in the foreground to completion. ONE run is the result, no skip path; exit 0 only
when every cell passes, else 2.

Run:  python tools/coop_test/test_pve2_turns.py
"""

import contextlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import pvp_fixture as PF  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_battle_end_rules import host_dead_settled, host_next_turn_up, wait_until  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_pvp_gm3 import (Miss, stack, top, log_lines, log_count, bview, units, pos, es, capture, guarded,  # noqa: E402
                             tele_both, reactions_zero, hash_now, common, ctx_cell, verdict, run_row, fail_all, shut,
                             record_view)

KEY = "48863"
SEED_ROSTER = 1                   # set_seed on the host before its lobby
SEED_MAP = 1                      # set_seed on the host right before newbattle_ok
OPENING_SEED = 1                  # set_seed on the host right before its Turn 1 close (measured: S_AI walks, no shot)
MISSION = "STR_MEDIUM_SCOUT"
GAMEMODE_PVE2 = 4
MAP_FP = 7.136941435423656e+17    # both machines' mapFingerprint
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ALIEN_IDS = [1000000, 1000001, 1000002, 1000003, 1000004]   # the players' aliens (as in test_pve2)
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]                       # the AI-run X-COM soldiers
S_AI, S_AI_TILE, S_AI_DIR, TU_S_AI = 8, (1, 6, 0), 7, 64    # min(XCOM_IDS); open ground >= 21 from every alien
C1, C1_TILE, C1_DIR, C1_DEST, C1_TU = 1000000, (27, 11, 0), 2, (28, 11, 0), 54   # test_pve2's C1 staging
C1_DEST2 = (28, 12, 0)            # C1_DEST's south neighbour (its east neighbour carries a west wall)
OPENING_KINDS = (["side_transition", "side_begin", "reveal"] + ["walk_step"] * 7 + ["bt_action_end"] * 4
                 + ["side_transition", "side_begin", "side_transition", "side_begin"])   # measured
AI_SHAPE = [("ai", "walk", S_AI)] * 4   # the X-COM AI's new host contexts on the opening side (measured)
CYCLE_KINDS = ["side_transition", "side_begin"] * 3   # the X-COM side and the neutral side, back to side 0 (measured)
N_XCOM_LIVE = 7
EXPECT_ENDING = {"reason": "soldiersDown", "aborted": False, "inExitArea": 0, "verdicts": [(0, "lose"), (1, "lose")],
             "tally": {"liveAliens": N_XCOM_LIVE, "liveSoldiers": 0, "inExit": 0}}
STEP_S = 30                       # each staging / order / ending step's bound (measured: <= 5.1 s)
BOOT_S = 60                       # each briefing wait (measured: <= 1.1 s)
SIDE_S = 60                       # side 0 of the next turn on both after a side change (measured: <= 2.9 s)
DENY_S = 5                        # early_order_refused's deny (measured: 0.05 s)
SELF_END_S = 15                   # aliens_wiped: the host's NextTurnState with no press (measured: 0.06 s)
N_EQUAL = "[coop-handshake] battle_ready saveBlob EQUAL"
N_REFUSED = "refused: unsupported"          # the client's battle_offer refusal (on a build that refuses gm4)
N_REFUSE_RX = "battle_refuse received"      # the host's unwind on it
N_OPENING = "PvE2 opening"           # the host's opening line
ROWS = (("early_order_refused", ("early_order_refused-hold", "early_order_refused-deny", "early_order_refused-common")),
        ("xcom_moves_first",
         ("xcom_moves_first-once", "xcom_moves_first-order", "xcom_moves_first-ai", "xcom_moves_first-back",
          "xcom_moves_first-common")),
        ("turn2_walk", ("turn2_walk-turn", "turn2_walk-walk", "turn2_walk-common")),
        ("end_turn_cycle", ("end_turn_cycle-cycle", "end_turn_cycle-once", "end_turn_cycle-common")),
        ("aliens_wiped",
         ("aliens_wiped-kill", "aliens_wiped-host", "aliens_wiped-client", "aliens_wiped-debrief",
          "aliens_wiped-common")))


def grep(gc, needle):
    return [line for line in log_lines(gc) if needle in line]


def miss(tag, err, machines):
    capture(tag, err, machines)
    raise Miss(tag)


def ctx3(c):
    return (c.get("origin"), c.get("kind"), c.get("actorId"))


def walk_done(host, other, uid, dest, ev):
    """Bounded: `uid` on `dest` on both machines and the other's order slot empty, then the host idle (test_pvp_gm3's
    walk_done, copied with this file's STEP_S)."""
    ok, ev["walkS"] = wait_until(lambda: pos(host, uid) == dest and pos(other, uid) == dest
                                 and es(other, "inFlight") is None, STEP_S, 0.2)
    try:
        session.wait_host_idle(host, other, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    return ok


def side_turn(host, client):
    hb, cb = battle_state(host), battle_state(client)
    return {"side": [hb.get("side"), cb.get("side")], "turn": [hb.get("turn"), cb.get("turn")],
            "tops": [top(host), top(client)], "pending": hb.get("pendingStates"), "busy": hb.get("isBusy")}


def drive_to_side0(host, client, want_turn, bound, at3=None):
    """Every 0.25 s close any NextTurnState on either machine; done when, on two polls 1.0 s apart, side 0 and turn
    `want_turn` on both, both tops BattlescapeState, the host's pendingStates 0 and not isBusy. `at3` = (t_ref, out):
    C1's position on both machines is read once 3 s after t_ref (early_order_refused-deny)."""
    t, hits, closes, last, done = time.time(), [], [], None, False
    while time.time() - t < bound:
        if at3 and "c1" not in at3[1] and time.time() - at3[0] >= 3.0:
            at3[1]["c1"] = [pos(host, C1), pos(client, C1)]
        for gc in (host, client):
            if top(gc) == "NextTurnState":
                b = battle_state(gc)
                closes.append((gc.name, round(time.time() - t, 2), b.get("side"), b.get("turn"),
                               gc.cmd({"cmd": "close_nextturn"}).get("handled")))
        last = side_turn(host, client)
        if (last["side"] == [0, 0] and last["turn"] == [want_turn, want_turn] and last["pending"] == 0
                and not last["busy"] and last["tops"] == ["BattlescapeState", "BattlescapeState"]):
            hits.append(round(time.time() - t, 2))
            if len(hits) >= 2 and hits[-1] - hits[0] >= 1.0:
                done = True
                break
            time.sleep(1.0)
            continue
        hits = []
        time.sleep(0.25)
    if at3 and "c1" not in at3[1]:
        wait_until(lambda: time.time() - at3[0] >= 3.0, 4, 0.1)
        at3[1]["c1"] = [pos(host, C1), pos(client, C1)]
    return done, round(time.time() - t, 2), closes, last


def cut_kinds(evs):
    """The host's evs from the mark through the LAST side_begin (side 0's when side 0 is current); all when none."""
    idx = [i for i, e in enumerate(evs) if e["kind"] == "side_begin"]
    return evs[: idx[-1] + 1] if idx else evs


# ===================== the gm4 bring-up (steps 1-9) =====================


def bring_up(host, client):
    m, boot = (host, client), {}
    guarded("boot", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("boot", lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    boot["gm2"] = guarded("boot", lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client"), m)[0]
    row = guarded("boot", lambda: PF.row_for(host, "HostPlayer"), m)
    boot["lobbyGamemode"] = guarded("boot", lambda: host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"}),
                                    m).get("gamemode")
    ok, secs = wait_until(lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                          and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], 10, 0.25)
    if not ok or boot["lobbyGamemode"] != GAMEMODE_PVE2:
        miss("boot", f"step 3: gamemode {boot['lobbyGamemode']} (want 4); both lobby rows Alien {ok} in {secs} s", m)
    guarded("boot", lambda: host.ok({"cmd": "lobby_action"}), m)
    guarded("boot", lambda: host.wait_for("host at battle settings",
                                       lambda: (not session.has_state(host, "LobbyMenu")) or None), m)
    if top(host) != "NewBattleState":
        miss("boot", f"step 4: host stack {stack(host)} (want NewBattleState on top)", m)
    guarded("boot", lambda: host.ok({"cmd": "newbattle_mission", "type": MISSION}), m)
    guarded("boot", lambda: host.ok({"cmd": "set_seed", "seed": SEED_MAP}), m)
    t_ok = time.time()
    guarded("boot", lambda: host.ok({"cmd": "newbattle_ok"}), m)
    for gc in (host, client):   # step 5: the host's BriefingState, then the client's; a refusal ends the wait at once
        ok, secs = wait_until(lambda gc=gc: session.has_state(gc, "BriefingState") or log_count(host, N_REFUSE_RX) > 0,
                              BOOT_S, 0.1)
        if not ok or log_count(host, N_REFUSE_RX) > 0:
            wait_until(lambda: log_count(client, N_REFUSED) > 0, 3, 0.1)   # bounded log flush
            refusal = {"sinceNewbattleOkS": round(time.time() - t_ok, 2), "client": grep(client, N_REFUSED),
                       "host": grep(host, N_REFUSE_RX)}
            miss("boot", f"step 5: {gc.name} BriefingState {ok} after {secs} s; refusal {json.dumps(refusal)}", m)
    boot["briefingS"] = round(time.time() - t_ok, 2)
    guarded("boot", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)   # step 6
    guarded("boot", lambda: session.dismiss_client_briefing(client), m)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            session.equip_both_ready(host, client)
    except Exception as e:
        print(buf.getvalue(), end="", flush=True)
        miss("boot", f"step 6: equip_both_ready: {type(e).__name__}: {str(e)[:500]}", m)
    boot["equip"] = buf.getvalue().strip()
    hb, cb = bview(host), bview(client)
    boot["mode"] = {"equal": log_count(host, N_EQUAL), "coopGamemode": [hb["coopGamemode"], cb["coopGamemode"]],
                    "mapFingerprint": [hb["mapFingerprint"], cb["mapFingerprint"]]}
    tu = [(units(gc).get(S_AI) or {}).get("tu") for gc in m]
    if tu != [TU_S_AI, TU_S_AI] or boot["mode"]["equal"] != 1 or hb["mapFingerprint"] != MAP_FP:
        miss("boot", f"step 6: S_AI tu {tu} (want {TU_S_AI} on both), {boot['mode']} (want EQUAL 1, MAP_FP "
                     f"{MAP_FP})", m)
    boot["pinned"] = guarded("boot", lambda: session.pin_ai_neutral(host, client, tag="pve2_turns"), m)   # step 7
    guarded("boot", lambda: reactions_zero(host, client), m)
    boot["unpin"] = guarded("boot", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat",
                                                                "unit": S_AI, "stat": "tu", "value": TU_S_AI,
                                                                "refill": True},
                                                 ("tu",)).get("tu"), m)
    boot["sAi"] = guarded("boot", lambda: tele_both(host, client, S_AI, S_AI_TILE, S_AI_DIR).get("to"), m)
    guarded("boot", lambda: session.dismiss_battle_start_overlays(client), m)   # step 8: the client's Turn 1 close only
    return boot, session._crash_log_snapshot()   # step 9


# ===================== the rows =====================


def early_order_act(host, client, boot, crash0):
    """Row early_order_refused's actions (its C1 read 3 s after the host's close is taken by xcom_moves_first): C1
    staged and its TU refilled, the hold read, the client's walk, the deny wait (DENY_S), the common cell with the
    host's Turn 1 screen up."""
    m, st = (host, client), {"ev": {"boot": boot}}
    try:
        st["ev"]["tele"] = guarded("staging", lambda: tele_both(host, client, C1, C1_TILE, C1_DIR).get("to"), m)
        st["ev"]["tu"] = guarded("staging", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat",
                                                                          "unit": C1, "stat": "tu", "value": C1_TU,
                                                                          "refill": True}, ("tu",)).get("tu"), m)
    except Miss:
        st["staging"] = True
        return st
    hold = side_turn(host, client)
    st["ev"]["hold"] = hold
    st["hold"] = (hold["tops"] == ["NextTurnState", "BattlescapeState"] and hold["side"] == [0, 0]
                  and hold["turn"] == [1, 1],
                  f"tops host/client {hold['tops']} (want NextTurnState / BattlescapeState), side {hold['side']} turn "
                  f"{hold['turn']} (want 0 / 1 on both), read before the walk")
    b_ctx, b_sent = es(host, "closedContexts") or [], es(client, "coopIntentsSent") or {}
    r = session.send_walk(client, C1, C1_DEST)
    ok, secs = wait_until(lambda: (es(client, "lastDeny") or {}).get("iseq") == r.get("iseq"), DENY_S, 0.1)
    st["deny"], st["iseq"], st["denyS"] = es(client, "lastDeny") or {}, r.get("iseq"), secs
    st["newCtx"] = new_contexts(b_ctx, es(host, "closedContexts"))
    st["ev"].update(resp=r, lastDeny=st["deny"], denyS=secs, newCtx=st["newCtx"],
                    sent=[b_sent, es(client, "coopIntentsSent")], inFlight=es(client, "inFlight"),
                    c1Before=[pos(host, C1), pos(client, C1)])
    st["common"] = common(host, client, crash0)
    return st


def early_order_cells(st):
    if st.get("staging"):
        return {n: (False, "staging (see the CAPTURE staging line)")
                for n in ("early_order_refused-hold", "early_order_refused-deny",
                          "early_order_refused-common")}, st["ev"]
    c1 = st.get("c1")
    st["ev"]["c1At3s"] = c1
    deny_ok = (st["deny"].get("iseq") == st["iseq"] and st["deny"].get("reason") == "turn_over" and not st["newCtx"]
               and c1 == [C1_TILE, C1_TILE])
    return {"early_order_refused-hold": st["hold"],
            "early_order_refused-deny": (
                deny_ok, f"client lastDeny {st['deny']} for the walk's iseq {st['iseq']} ({st['denyS']} s; want "
                         f"reason turn_over within {DENY_S} s); new host contexts {st['newCtx']} (want none); C1 "
                         f"host/client 3 s after the host's close {c1} (want {C1_TILE} on both)"),
            "early_order_refused-common": st["common"]}, st["ev"]


def row_xcom_moves_first(host, client, crash0, early_state):
    m, ev = (host, client), {}
    ev["seed"] = guarded("boot", lambda: host.ok({"cmd": "set_seed", "seed": OPENING_SEED}), m)
    mark = es(host, "lastSeqEmitted")
    b_ctx = es(host, "closedContexts") or []
    t_close = time.time()
    ev["close"] = host.cmd({"cmd": "dismiss_popup"})
    done, secs, closes, last = drive_to_side0(host, client, 2, SIDE_S, (t_close, early_state))
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    evs = evs_since(host, mark)
    kinds = [e["kind"] for e in cut_kinds(evs)]
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    st_seqs = [e["seq"] for e in evs if e["kind"] == "side_transition"]
    st0 = st_seqs[0] if st_seqs else None
    early = [ctx3(c) for c in new if c.get("origin") in ("intent", "host")
             and (st0 is None or (c.get("endSeq") or 0) < st0)]
    ai = [ctx3(c) for c in new if c.get("origin") == "ai"]
    sa = [pos(host, S_AI), pos(client, S_AI)]
    ol = grep(host, N_OPENING)
    outs = {i: [(units(gc).get(i) or {}).get("isOut") for gc in m] for i in ALIEN_IDS}
    now = side_turn(host, client)
    ev.update(mark=mark, done=done, secs=secs, closes=closes, last=last, kinds=kinds, firstSideTransition=st0,
              newCtx=[ctx3(c) for c in new], sAi=sa, openingLines=ol)
    return {"xcom_moves_first-once": (len(ol) == 1, f"host log '{N_OPENING}' lines {len(ol)} (want 1)"),
            "xcom_moves_first-order": (
                kinds == OPENING_KINDS and not early,
                f"host ev kinds after the mark {mark} through the side-0 side_begin {kinds} (want "
                f"OPENING_KINDS {OPENING_KINDS}); intent / host contexts closed before the first side_transition"
                f" (seq {st0}) {early} (want none)"),
            "xcom_moves_first-ai": (
                ai == AI_SHAPE and sa[0] == sa[1] and sa[0] != S_AI_TILE,
                f"new ai contexts {ai} (want {AI_SHAPE}); S_AI host/client {sa} (want equal and != {S_AI_TILE})"),
            "xcom_moves_first-back": (
                done and now["side"] == [0, 0] and now["turn"] == [2, 2]
                and now["tops"] == ["BattlescapeState", "BattlescapeState"]
                and all(v == [False, False] for v in outs.values()),
                f"side {now['side']} turn {now['turn']} tops {now['tops']} (want 0 / 2 / BattlescapeState on "
                f"both; settled {done} in {secs} s, bound {SIDE_S}); aliens isOut host/client {outs} (want none)"),
            "xcom_moves_first-common": common(host, client, crash0)}, ev


def row_turn2_walk(host, client, crash0):
    pre = side_turn(host, client)
    b_ctx = es(host, "closedContexts") or []
    ev = {"pre": pre, "c1Before": [pos(host, C1), pos(client, C1)], "resp": session.send_walk(client, C1, C1_DEST2)}
    walk_done(host, client, C1, C1_DEST2, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    ps = [pos(host, C1), pos(client, C1)]
    ok, d = ctx_cell(new, "intent", C1)
    ev.update(newCtx=new, lastDeny=es(client, "lastDeny"))
    return {"turn2_walk-turn": (pre["side"] == [0, 0] and pre["turn"] == [2, 2],
                                f"side {pre['side']} turn {pre['turn']} (want 0 / 2 on both), read before the walk"),
            "turn2_walk-walk": (ok and ps == [C1_DEST2, C1_DEST2],
                                f"{d}; C1 host/client {ps} (want {C1_DEST2} on both; {ev['walkS']} s)"),
            "turn2_walk-common": common(host, client, crash0)}, ev


def row_end_turn_cycle(host, client, crash0):
    m, ev, steps = (host, client), {}, []
    ev["pin"] = guarded("boot", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": S_AI,
                                                         "stat": "tu", "value": 0, "refill": True}, ("tu",)).get("tu"), m)
    turn0 = battle_state(host).get("turn")
    mark, oc0 = es(host, "lastSeqEmitted"), log_count(host, N_OPENING)
    ev["pressClient"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", STEP_S, 0.1)
    if not ok:
        steps.append(f"host END TURN text {battle_state(host).get('coopEndTurnText')!r} {secs} s after the client's "
                     f"press (want 'END TURN 1/2')")
    ev["pressHost"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    want = (turn0 or 0) + 1
    done, secs, closes, last = drive_to_side0(host, client, want, SIDE_S)
    kinds = [e["kind"] for e in cut_kinds(evs_since(host, mark))]
    oc1 = log_count(host, N_OPENING)
    ev.update(turn0=turn0, mark=mark, done=done, secs=secs, closes=closes, kinds=kinds, opening=[oc0, oc1])
    return {"end_turn_cycle-cycle": (
                done and last["side"] == [0, 0] and last["turn"] == [want, want] and kinds == CYCLE_KINDS
                and not steps,
                f"side {last['side']} turn {last['turn']} (want 0 / T + 1 = {want} on both; settled {done} in "
                f"{secs} s); host ev kinds {kinds} (want {CYCLE_KINDS}); {steps or 'END TURN 1/2 shown'}"),
            "end_turn_cycle-once": (oc1 == oc0,
                                    f"host '{N_OPENING}' lines {oc0} -> {oc1} across the cycle (want unchanged)"),
            "end_turn_cycle-common": common(host, client, crash0)}, ev


def row_aliens_wiped(host, client, crash0):
    """The ending, in test_battle_end_rules all_xcom_down's no-press shape: records at 0 and the hash taken; host
    kill_unit_real {faction 0}; the kill settles; the players' side ends by itself; the host's NextTurnState closed
    by dismiss_popup; both DebriefingStates."""
    m, ev, ends = (host, client), {}, []
    live = sorted(i for i in ALIEN_IDS if not (units(host).get(i) or {}).get("isOut"))
    pre = {gc.name: {k: (es(gc, "battleEnd") or {}).get(k) for k in ("emitted", "applied")} for gc in m}
    hashed = hash_now(host, client)
    kill = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_PLAYER})
    settled, ev["settleS"] = wait_until(lambda: host_dead_settled(host, live), STEP_S, 0.1)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    ev.update(live=live, pre=pre, hashBefore=hashed, kill=kill)
    pre_ok = all(v == {"emitted": 0, "applied": 0} for v in pre.values())
    kill_cell = (kill.get("ok") is True and sorted(kill.get("killed") or []) == live and settled and pre_ok,
                 f"killed {kill.get('killed')} (want every live alien {live}); settled {settled} in "
                 f"{ev['settleS']} s (bound {STEP_S}); pre-ending records {pre} (want emitted 0 / applied 0 on both)")
    ok, secs = wait_until(lambda: host_next_turn_up(host), SELF_END_S, 0.1)
    hbs = battle_state(host)
    ev["nextTurn"] = {"up": ok, "s": secs, "side": hbs.get("side"), "turn": hbs.get("turn")}
    if not ok:
        ends.append(f"host NextTurnState not up {secs} s after the kill with no press (the side's self-end)")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ends.append(f"host dismiss_popup handled {d.get('handled')!r} (want 'NextTurnState->close')")
    hok, hs = wait_until(lambda: any("DebriefingState" in s for s in stack(host)), STEP_S, 0.1)
    cok, csec = wait_until(lambda: top(client) == "DebriefingState"
                           and (es(client, "battleEnd") or {}).get("debriefDisplayOnly") == 1, STEP_S, 0.25)
    hrec, crec = es(host, "battleEnd") or {}, es(client, "battleEnd") or {}
    hv, cv = record_view(hrec), record_view(crec)
    dh, dc = host.cmd({"cmd": "debrief_state"}), client.cmd({"cmd": "debrief_state"})
    ev.update(host=hv, client=cv, tops=[stack(host), stack(client)], hostDebriefS=hs, clientEndS=csec,
              debrief={"host": {k: dh.get(k) for k in ("title", "rows", "rating", "total")},
                       "client": {k: dc.get(k) for k in ("title", "rows", "rating", "total")}})
    if not hok or top(host) != "DebriefingState":
        ends.append(f"host stack {stack(host)} {hs} s after the close (want DebriefingState on top)")
    if not cok or top(client) != "DebriefingState" or crec.get("debriefDisplayOnly") != 1:
        ends.append(f"client top {top(client)}, battleEnd.debriefDisplayOnly {crec.get('debriefDisplayOnly')} {csec} s "
                    f"after the host's debriefing (want DebriefingState, 1)")
    if (dh.get("title"), dh.get("rows")) != (dc.get("title"), dc.get("rows")) or not dh.get("title"):
        ends.append(f"debrief_state title/rows host {dh.get('title')!r} {dh.get('rows')} vs client {dc.get('title')!r} "
                    f"{dc.get('rows')} (want equal, non-empty)")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        ends.append(str(e)[:300])
    want = {k: EXPECT_ENDING[k] for k in ("reason", "aborted", "inExitArea", "verdicts", "tally")}
    return {"aliens_wiped-kill": kill_cell,
            "aliens_wiped-host": (hrec.get("emitted") == 1 and isinstance(hv["seq"], int) and hv["seq"] > 0
                                  and {k: hv[k] for k in want} == want,
                                  f"host battleEnd emitted {hrec.get('emitted')} (want 1) {hv} (want seq > 0 and "
                                  f"{want})"),
            "aliens_wiped-client": (crec.get("applied") == 1 and cv == hv,
                                    f"client battleEnd applied {crec.get('applied')} (want 1) {cv} (want the host's)"),
            "aliens_wiped-debrief": (not ends,
                                     f"{ends or 'both tops DebriefingState, the client display-only, debrief_state '}"
                                     f"{'' if ends else 'titles and rows equal, no client save'}"),
            "aliens_wiped-common": common(host, client, crash0, hashed)}, ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pve2_turns_host"))
    client = GameClient("client", None, make_user_dir("pve2_turns_client"))
    rows = dict(ROWS)
    try:
        try:
            boot, crash0 = bring_up(host, client)
        except Miss:
            return fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            early_state = early_order_act(host, client, boot, crash0)
        except Exception as e:
            early_state = {"ev": {"error": f"{type(e).__name__}: {str(e)[:600]}"}, "staging": True}
        first_result = {}
        try:
            first_result = row_xcom_moves_first(host, client, crash0, early_state)
        except Exception as e:
            first_result = ({}, {"error": f"{type(e).__name__}: {str(e)[:600]}"})
        try:
            early_cells, early_ev = early_order_cells(early_state)
        except Exception as e:
            early_cells, early_ev = {}, {"error": f"{type(e).__name__}: {str(e)[:600]}"}
        fails = verdict("early_order_refused", rows["early_order_refused"], early_cells, early_ev)
        fails += verdict("xcom_moves_first", rows["xcom_moves_first"], first_result[0], first_result[1])
        fails += run_row("turn2_walk", rows["turn2_walk"], lambda: row_turn2_walk(host, client, crash0))
        fails += run_row("end_turn_cycle", rows["end_turn_cycle"], lambda: row_end_turn_cycle(host, client, crash0))
        fails += run_row("aliens_wiped", rows["aliens_wiped"], lambda: row_aliens_wiped(host, client, crash0))
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pve2_turns: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
