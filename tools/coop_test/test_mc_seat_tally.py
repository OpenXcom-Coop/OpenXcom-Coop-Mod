"""W2-H29 rows MA (boot H) and MX (boot X): END TURN counts a mind-controlled unit for the seat that commands it now
(R-U3-B-1, owner D53 "a live COMMANDABLE unit", MJ-8; F11588, F11671, F11674).

Spec: docs repo rewrite/prompts/w2h29_mc_unit_seat.md section (f) test_mc_seat_tally.py (QH29-1..QH29-7 (a)).
Constants: rewrite/w2h29-task0/CONSTANTS.md (TASK 0 boots Ha / Hb, Xa / Xb).

Boot H (gm2 parallel, key 48737; the client plays the aliens, seat 1): BER.boot_e6, every unit's reactions 0, R5-U3 S-B's
B2 staging, host END TURN (side 1 turn 1), R2 (SEED_R2: S3 reacts to the client's walk of A), client END TURN (side 0
turn 2), R1 (SEED_R1: A reacts to the host's real-UI walk of S), host END TURN (side 1 turn 2). R2 / R1 are staging.
  MA  the alien seat mind-controls the X-COM soldier S4 through the client's psi intent lever (SEED_MA):
      MA-mc    (precondition) one new host context {intent, psi, A}; S4 faction 1, mcId A, coop 0 on both
      MA-end   the client's END TURN alone ends the alien side: side 0 turn 3 on both within SIDE_S
      MA-xcom  S4 still controlled at X-COM's side; the host's press alone: side 1 turn 3 within SIDE_S
      MA-back  S4 reverted at its controller side's next start: faction 0, coop 0 on both
      MA-own   the alien seat's turn order on S4 is denied not_your_unit; no new host context
      MA-end2  the client's press alone: side 0 turn 4 within SIDE_S
      MA-common every bucket EQUAL after the row's last settled side change, desyncSeen false, no new crash file
Boot X (gm2 traditional, key 48738): BER.boot_e6 with set_mode(host, traditional) after host.connect(), reactions 0,
the B2 staging.
  MX  X-COM's S mind-controls the alien seat's unit A through the host psi_attack lever (SEED_MX), continued by
      W2-H31 (rewrite/prompts/w2h31_mc_side_never_ends.md; rewrite/w2h31-task0/CONSTANTS.md, boots Xa / Xb):
      MX-mode  (precondition) turnMode traditional and coopActiveSeat 0 on both before the lever
      MX-mc    (precondition) A faction 0, mcId S, coop 1 on both
      MX-end   the host's END TURN alone ends X-COM's side (the baton's last pass): the host's side-phase counter +1
               within SIDE_S (W2-H31 section A.10: the alien side, with no live seat, now passes at once)
      MX-skip  with no further press both machines on side 0 turn 2 within SIDE_S, and exactly one
               '[coop-endturn] no seat has a live unit on the active side' host log line
      MX-back  A faction 1, coop 1 on both at side 0 turn 2 (released at its controller side's start)
      MX-alien the host's press: side 1 turn 2; host tally {needed 1, activeSeat 1} and coopActiveSeat 1 on both
               within PAINT_S; the partner's press alone: side 0 turn 3
      MX-common every bucket EQUAL right before the press, desyncSeen false, no new crash file
Every InfoboxState is dismissed on its own machine before any END TURN press (only the top state thinks, F11689).

One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails that boot's rows "boot"; a staging step fails them "staging".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_mc_seat_tally.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from test_pvp_gm3 import Miss, units, pos, es, top, guarded, verdict, fail_all, shut, log_count  # noqa: E402
from repro_atom_side_begin import drive_side_change  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_client_shoot import new_contexts, send_intent, set_tu_both, place, jt  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk  # noqa: E402
from test_turn_mode import set_mode, TRADITIONAL  # noqa: E402

KEY_H, KEY_X = "48737", "48738"
A_ID = 1000000                    # the alien (gm2: the client's, seat 1)
S_ID, S3_ID, S2_ID, S4_ID, S5_ID = 8, 9, 10, 11, 12
TILES = {   # R5-U3 S-B B2 staging (open ground, z 0): (tile, dir)
    A_ID: ((15, 2, 0), 4), S3_ID: ((18, 6, 0), 7), S_ID: ((15, 9, 0), 0), S2_ID: ((12, 7, 0), 0),
    S4_ID: ((18, 8, 0), 0), S5_ID: ((36, 36, 0), 0), 13: ((33, 33, 0), 0), 14: ((34, 33, 0), 0)}
R2_DEST, R1_DEST = (15, 4, 0), (17, 9, 0)
A_TU = 54
SEED_R2, SEED_R1, SEED_MA, SEED_MX = 1, 1, 1, 1   # TASK 0 Ha / Hb, Xa / Xb (A and S not out; both conversions)
PSI_AMP = "STR_PSI_AMP"
STEP_S, SIDE_S, HOLD_S, PAINT_S = 30, 15, 3, 15
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
PRESS = {"cmd": "battle_action", "action": "end_turn_button"}
MA_ROWS = (("MA", ("MA-mc", "MA-end", "MA-xcom", "MA-back", "MA-own", "MA-end2", "MA-common")),)
MX_ROWS = (("MX", ("MX-mode", "MX-mc", "MX-end", "MX-skip", "MX-back", "MX-alien", "MX-common")),)


# ===================== probes and boxes (shared with test_mc_seat_coop) =====================


def mcv(gc, uid):
    u = units(gc).get(uid) or {}
    return (u.get("faction"), u.get("mindControllerId"), u.get("coop"), u.get("isOut"), u.get("status"))


def unit_rows(gc):
    """Every live unit's (id, coop, faction, originalFaction, mcId)."""
    return sorted((i, u.get("coop"), u.get("faction"), u.get("originalFaction"), u.get("mindControllerId"))
                  for i, u in units(gc).items() if not u.get("isOut"))


def tally_view(gc):
    e, b = event_state(gc), battle_state(gc)
    t = e.get("coopEndTurnTally") or {}
    return {"tally": {k: t.get(k) for k in ("count", "needed", "ready", "side", "activeSeat")},
            "pc": e.get("coopEndTurnPhaseCounter"), "seen": e.get("coopEndTurnTalliesSeen"),
            "active": e.get("coopActiveSeat"), "mode": e.get("turnMode"), "text": b.get("coopEndTurnText"),
            "turnSide": (b.get("turn"), b.get("side"))}


def msgs(gc):
    m = event_state(gc).get("messages") or {}
    return {"counts": m.get("counts"), "ring": (m.get("ring") or [])[-3:]}


def turn_side(gc):
    b = battle_state(gc)
    return (b.get("turn"), b.get("side"))


def texts_of(gc):
    return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]


def poll_box(gc, rec, where):
    """test_messages.poll_host_box with the machine as parameter: an infobox on top of `gc` is recorded and closed on
    ITS OWN machine (InfoboxOKState by its OK button, any other by dismiss_popup). True when one was handled."""
    t = top(gc) or ""
    if "Infobox" not in t:
        return False
    e = {"machine": gc.name, "where": where, "top": t, "texts": texts_of(gc)}
    if t == "InfoboxOKState":
        r = gc.cmd({"cmd": "click_widget", "match": "OK"})
        e["closed"] = ("ok button", r.get("ok"))
    else:
        r = gc.cmd({"cmd": "dismiss_popup"})
        e["closed"] = ("dismiss_popup", r.get("handled"))
    rec.setdefault("boxes", []).append(e)
    return True


def boxes_window(m, rec, where, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        for gc in m:
            poll_box(gc, rec, where)
        time.sleep(0.1)


def tops_ready(m, rec, where, timeout=10):
    """Every infobox dismissed on its own machine, NextTurnStates closed, both tops BattlescapeState."""
    def ok():
        for gc in m:
            poll_box(gc, rec, where)
            if top(gc) == "NextTurnState":
                gc.cmd({"cmd": "close_nextturn"})
        return all(top(gc) == "BattlescapeState" for gc in m)
    return BER.wait_until(ok, timeout, 0.1)[0]


def settle(host, client, rec, where):
    session.wait_host_idle(host, client, timeout=STEP_S)
    boxes_window((host, client), rec, where, 1.0)
    return tops_ready((host, client), rec, where)


def press_to(host, client, presser, side, turn, rec, timeout):
    """Boxes dismissed, `presser`'s END TURN, both machines on (side, >= turn) within `timeout`, screens closed.
    Returns (ok, seconds or error)."""
    tops_ready((host, client), rec, f"before press side {side}")
    t0 = time.time()
    presser.cmd(dict(PRESS))
    try:
        drive_side_change(host, client, side, want_turn_min=turn, timeout=timeout)
    except TimeoutError as e:
        return False, str(e)[:160]
    s = round(time.time() - t0, 2)
    settle(host, client, rec, f"side {side} turn {turn}")
    return True, s


def set_stat_both(host, client, uid, stat, value, refill=False):
    req = {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat, "value": value}
    if refill:
        req["refill"] = True
    return both(host, client, req, ("tu",))


def give_amp(host, client, uid):
    return both(host, client, {"cmd": "battle_give", "unit": uid, "item": PSI_AMP, "slot": "right",
                               "clear_hands": True}, ("weaponId",))["weaponId"]


def psi_lever(host, client, actor, target, amp, seed, want_faction, rec, where):
    """The host-local psi_attack lever right after the host's set_seed; bounded wait for the target's faction on the
    host and the host idle, boxes dismissed on their own machines. Returns the lever reply and the wait."""
    host.ok({"cmd": "set_seed", "seed": seed})
    r = host.cmd({"cmd": "battle_action", "action": "psi_attack", "unit": actor, "target": target, "weapon_id": amp})
    ok, s = BER.wait_until(lambda: (poll_box(host, rec, where) or True) and (poll_box(client, rec, where) or True)
                           and es(host, "busyOwnerSeat") == -1 and not battle_state(host).get("isBusy")
                           and (units(host).get(target) or {}).get("faction") == want_faction, STEP_S, 0.2)
    settle(host, client, rec, where)
    return {"lever": {k: r.get(k) for k in ("ok", "tuCost", "tuHave", "error")}, "wait": (ok, s)}


def common(host, client, crash0, at):
    ok, detail = G3F.common(host, client, crash0)
    return ok, f"{detail} (taken {at})"


# ===================== staging =====================


def stage_b2(host, client):
    """The B2 staging by rule: every tile open ground on both machines, every unit placed (none on its own tile, S2),
    A's plasma pistol and S3's rifle by lever (S25); every bucket EQUAL."""
    th = {(t["x"], t["y"]): t for t in host.ok({"cmd": "tile_census", "x0": 0, "x1": 39, "y0": 0, "y1": 39,
                                                 "z0": 0, "z1": 0})["tiles"] if t}
    tc = {(t["x"], t["y"]): t for t in client.ok({"cmd": "tile_census", "x0": 0, "x1": 39, "y0": 0, "y1": 39,
                                                   "z0": 0, "z1": 0})["tiles"] if t}
    parts = lambda t: tuple((t or {}).get("parts", {}).get(p, {}).get("mapDataID")
                            for p in ("floor", "westwall", "northwall", "object"))
    for t in [td[0] for td in TILES.values()] + [R2_DEST, R1_DEST]:
        ph, pc = parts(th.get(t[:2])), parts(tc.get(t[:2]))
        assert ph == pc and ph[0] not in (None, -1) and ph[3] == -1, f"tile {t} parts host {ph} client {pc}"
    for uid, (t, d) in TILES.items():
        place(host, client, uid, t, d)
    both(host, client, {"cmd": "battle_give", "unit": A_ID, "item": "STR_PLASMA_PISTOL",
                        "ammo": "STR_PLASMA_PISTOL_CLIP", "slot": "right", "clear_hands": True}, ("weaponId", "ammoId"))
    both(host, client, {"cmd": "battle_give", "unit": S3_ID, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                        "slot": "right", "clear_hands": True}, ("weaponId", "ammoId"))
    assert_hash_clean(host, client, full=True, what="B2 staging")


def staging_h(host, client, rec):
    """Boot H's chain to side 1 turn 2: B2, R2, R1 (TASK 0 pins). Raises on a missed step."""
    stage_b2(host, client)
    ok, s = press_to(host, client, host, FACTION_HOSTILE, 1, rec, STEP_S)
    assert ok, f"host END TURN -> side 1 turn 1: {s}"
    set_stat_both(host, client, S3_ID, "reactions", 100)
    set_stat_both(host, client, S3_ID, "firing", 0)
    set_tu_both(host, client, S3_ID, 255)
    prev = session.walk_action_id(host)
    host.ok({"cmd": "set_seed", "seed": SEED_R2})
    session.send_walk(client, A_ID, R2_DEST)
    session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert not any((units(gc).get(A_ID) or {}).get("isOut") for gc in (host, client)), "A out after R2"
    set_stat_both(host, client, S3_ID, "reactions", 0)
    ok, s = press_to(host, client, client, FACTION_PLAYER, 2, rec, STEP_S)
    assert ok, f"client END TURN -> side 0 turn 2: {s}"
    set_stat_both(host, client, A_ID, "reactions", 100)
    set_stat_both(host, client, A_ID, "firing", 0)
    set_stat_both(host, client, A_ID, "tu", A_TU, refill=True)
    assert A_ID in ((units(host).get(S_ID) or {}).get("spottedThisTurn") or []), "S does not see A (R1 premise)"
    prev = session.walk_action_id(host)
    assert tab_select(host, S_ID), "tab_select S"
    host.ok({"cmd": "set_seed", "seed": SEED_R1})
    real_click_walk(host, R1_DEST)
    session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert not any((units(gc).get(S_ID) or {}).get("isOut") for gc in (host, client)), "S out after R1"
    set_stat_both(host, client, A_ID, "reactions", 0)
    ok, s = press_to(host, client, host, FACTION_HOSTILE, 2, rec, STEP_S)
    assert ok, f"host END TURN -> side 1 turn 2: {s}"


# ===================== row MA =====================


def row_ma(host, client, crash0, rec):
    ev, cells = {}, {}
    amp = give_amp(host, client, A_ID)
    set_stat_both(host, client, A_ID, "psiSkill", 100)
    set_stat_both(host, client, S4_ID, "psiStrength", 0)
    set_tu_both(host, client, A_ID, A_TU)
    ev["amp"] = amp
    ev["aSees"] = (units(host).get(A_ID) or {}).get("spottedThisTurn")
    ctx0 = es(host, "closedContexts") or []
    req = {"cmd": "battle_intent", "kind": "psi", "actor": A_ID,
           "plan": {"action": "mc", "weapon": amp, "target": jt(pos(host, S4_ID)), "targetUnit": S4_ID}}
    notes = []
    host.ok({"cmd": "set_seed", "seed": SEED_MA})
    si = send_intent(host, client, req, notes, timeout=STEP_S)
    ok, s = BER.wait_until(lambda: (poll_box(host, rec, "MA") or True) and (poll_box(client, rec, "MA") or True)
                           and es(host, "busyOwnerSeat") == -1 and not battle_state(host).get("isBusy")
                           and (units(host).get(S4_ID) or {}).get("faction") == FACTION_HOSTILE, STEP_S, 0.2)
    tops = settle(host, client, rec, "MA")
    new = [{k: c.get(k) for k in ("origin", "kind", "actorId")} for c in new_contexts(ctx0, es(host, "closedContexts"))]
    s4 = [mcv(host, S4_ID), mcv(client, S4_ID)]
    ev.update(intent={k: si.get(k) for k in ("sent", "iseq", "answer")}, notes=notes, wait=(ok, s), newCtx=new, s4=s4,
              lastDeny=es(client, "lastDeny"))
    want_s4 = (FACTION_HOSTILE, A_ID, 0, False, 0)
    cells["MA-mc"] = (new == [{"origin": "intent", "kind": "psi", "actorId": A_ID}] and s4 == [want_s4, want_s4] and tops,
                      f"new host contexts {new} (want one {{intent, psi, {A_ID}}}); S4 host/client {s4} (want "
                      f"{want_s4}); both tops BattlescapeState {tops}")
    first = None if cells["MA-mc"][0] else "MA-mc"

    def gate(name, fn):
        nonlocal first
        if first:
            cells[name] = (False, f"not reached ({first} failed)")
            return
        try:
            cells[name] = fn()
        except Exception as e:
            cells[name] = (False, f"{type(e).__name__}: {str(e)[:300]}")
        if not cells[name][0]:
            first = name

    def ma_end():
        ev["preEnd"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)],
                        "msgs": [msgs(host), msgs(client)]}
        ok_, s_ = press_to(host, client, client, FACTION_PLAYER, 3, rec, SIDE_S)
        ev["postEnd"] = {"ok": ok_, "s": s_, "tally": [tally_view(host), tally_view(client)]}
        return ok_, (f"client END TURN: side 0 turn 3 on both in {s_} s" if ok_ else
                     f"client END TURN: no side 0 turn 3 within {SIDE_S} s; host tally {tally_view(host)}; "
                     f"client tally {tally_view(client)}")

    def ma_xcom():
        s4x = [mcv(host, S4_ID)[:2], mcv(client, S4_ID)[:2]]
        ev["preXcom"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)]}
        ok_, s_ = press_to(host, client, host, FACTION_HOSTILE, 3, rec, SIDE_S)
        good = s4x == [(FACTION_HOSTILE, A_ID)] * 2
        return good and ok_, (f"S4 (faction, mcId) at side 0 turn 3 host/client {s4x} (want ({FACTION_HOSTILE}, "
                              f"{A_ID})); host END TURN alone -> side 1 turn 3: {ok_} ({s_}); host tally "
                              f"{tally_view(host)}")

    def ma_back():
        v = [mcv(host, S4_ID)[:3:2], mcv(client, S4_ID)[:3:2]]
        return v == [(FACTION_PLAYER, 0)] * 2, f"S4 (faction, coop) at side 1 turn 3 host/client {v} (want (0, 0))"

    def ma_own():
        c0 = es(host, "closedContexts") or []
        d0 = (units(client).get(S4_ID) or {}).get("direction")
        n = []
        r = send_intent(host, client, {"cmd": "battle_intent", "kind": "turn", "actor": S4_ID, "toDir": (d0 + 2) % 8},
                        n, timeout=STEP_S)
        ld = es(client, "lastDeny") or {}
        nc = new_contexts(c0, es(host, "closedContexts"))
        ev["own"] = {"intent": {k: r.get(k) for k in ("sent", "iseq", "answer")}, "lastDeny": ld, "notes": n}
        return (ld.get("reason") == "not_your_unit" and ld.get("iseq") == r.get("iseq") and not nc,
                f"client turn order on S4: lastDeny {ld} (want not_your_unit for iseq {r.get('iseq')}); new host "
                f"contexts {nc} (want none)")

    def ma_end2():
        ev["preEnd2"] = {"tally": [tally_view(host), tally_view(client)]}
        ok_, s_ = press_to(host, client, client, FACTION_PLAYER, 4, rec, SIDE_S)
        return ok_, f"client END TURN alone -> side 0 turn 4: {ok_} ({s_}); host tally {tally_view(host)}"

    for name, fn in (("MA-end", ma_end), ("MA-xcom", ma_xcom), ("MA-back", ma_back), ("MA-own", ma_own),
                     ("MA-end2", ma_end2)):
        gate(name, fn)
    ev["turnSide"] = [turn_side(host), turn_side(client)]
    cells["MA-common"] = common(host, client, crash0, f"at (turn, side) {ev['turnSide']}")
    ev["boxes"] = rec.get("boxes")
    return cells, ev


# ===================== boot X and row MX =====================


def boot_e6_mode(host, client, port, mode):
    """BER.boot_e6 (test_battle_end_rules :822-:862) with ONE added line: set_mode(host, mode) right after
    host.connect() (F10917 copy pattern; F11686: the host's CoopTurnMode is stamped at the offer)."""
    raw = BER.raw
    host.spawn(); host.connect()
    set_mode(host, mode)
    client.spawn(); client.connect()
    host.ok({"cmd": "set_seed", "seed": BER.SEED_MAP})
    raw.skirmish_host(host, port)
    raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, raw.CLIENT_PLAYER), "team": "Alien"})
    assert r.get("gamemode") == BER.GAMEMODE_PVP, f"lobby_set_team Alien answered gamemode {r.get('gamemode')}"
    time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative PHASE 0)
    BER.drive_to_gm2_battlescape(host, client)
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("coopGamemode") == BER.GAMEMODE_PVP and cs.get("coopGamemode") == BER.GAMEMODE_PVP, (
        f"coopGamemode host={hs.get('coopGamemode')} client={cs.get('coopGamemode')}")
    assert hs.get("mapFingerprint") == BER.MAP_FP and cs.get("mapFingerprint") == BER.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}")
    ha, ca = hs.get("authority") or {}, cs.get("authority") or {}
    assert (ha.get("localSeat"), ha.get("hostSim"), ca.get("localSeat"), ca.get("hostSim")) == (0, True, 1, False), (
        f"authority host={ha} client={ca}")
    a = session.units_by_id(hs).get(A_ID) or {}
    assert (a.get("faction"), a.get("coop"), a.get("isOut")) == (FACTION_HOSTILE, 1, False), f"alien at bring-up {a}"
    pinned = pin_ai_neutral(host, client, tag="w2h29-gm2-mode")   # 0 is legal in gm2
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="gm2 bring-up")
    return {"mode": mode, "pinned": pinned}


def row_mx(host, client, crash0, rec):
    ev, cells = {}, {}
    mode = [(es(gc, "turnMode"), es(gc, "coopActiveSeat")) for gc in (host, client)]
    ev["mode"] = mode
    cells["MX-mode"] = (mode == [(TRADITIONAL, 0)] * 2,
                        f"(turnMode, coopActiveSeat) host/client {mode} (want ({TRADITIONAL!r}, 0))")
    amp = give_amp(host, client, S_ID)
    set_stat_both(host, client, S_ID, "psiSkill", 100)
    set_stat_both(host, client, A_ID, "psiStrength", 0)
    ev["sTu"] = set_tu_both(host, client, S_ID, 255)
    ev["amp"] = amp
    ev.update(psi_lever(host, client, S_ID, A_ID, amp, SEED_MX, FACTION_PLAYER, rec, "MX"))
    a = [mcv(host, A_ID), mcv(client, A_ID)]
    tops = tops_ready((host, client), rec, "before MX-end press")
    want_a = (FACTION_PLAYER, S_ID, 1, False, 0)
    cells["MX-mc"] = (a == [want_a] * 2 and tops,
                      f"A host/client {a} (want {want_a}); both tops BattlescapeState {tops}")
    ev["preEnd"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)],
                    "msgs": [msgs(host), msgs(client)]}
    cells["MX-common"] = common(host, client, crash0, "right before the host's press")
    first = None if cells["MX-mode"][0] and cells["MX-mc"][0] else ("MX-mode" if not cells["MX-mode"][0] else "MX-mc")
    w2h31, pc = ("[coop-endturn] no seat has a live unit on the active side",
                 lambda: es(host, "coopEndTurnPhaseCounter") or 0)

    def mx_end():   # W2-H31 (section A.10, F12376): the side-phase counter, as side 1 now passes at once
        tops_ready((host, client), rec, "before MX-end press")
        p0 = pc()
        host.cmd(dict(PRESS))
        ok, s = BER.wait_until(lambda: pc() >= p0 + 1, SIDE_S, 0.1)
        ev["postEnd"] = {"ok": ok, "s": s, "tally": [tally_view(host), tally_view(client)],
                         "tops": [top(host), top(client)]}
        return ok, f"host END TURN alone: host side-phase counter {p0} -> {pc()} within {SIDE_S} s: {ok} ({s} s)"

    def mx_skip():
        t0 = time.time()
        try:
            drive_side_change(host, client, FACTION_PLAYER, want_turn_min=2, timeout=SIDE_S)
            moved = round(time.time() - t0, 2)
        except TimeoutError:
            moved = None
        BER.wait_until(lambda: log_count(host, w2h31) >= 1, HOLD_S, 0.25)
        n = log_count(host, w2h31)
        ev["skip"] = {"tally": [tally_view(host), tally_view(client)], "lines": n}
        return moved is not None and n == 1, (f"no further press: both machines on side 0 turn 2 within {SIDE_S} s: "
                                              f"{moved is not None} ({moved} s; (turn, side) host/client "
                                              f"{[turn_side(host), turn_side(client)]}); host '{w2h31}' lines {n} "
                                              f"(want exactly 1)")

    def mx_back():
        settle(host, client, rec, "MX side 0 turn 2")
        v = [mcv(host, A_ID)[:3:2], mcv(client, A_ID)[:3:2]]
        return v == [(FACTION_HOSTILE, 1)] * 2, f"A (faction, coop) at side 0 turn 2 host/client {v} (want (1, 1))"

    def mx_alien():
        want = {"needed": 1, "activeSeat": 1}
        ok1, s1 = press_to(host, client, host, FACTION_HOSTILE, 2, rec, SIDE_S)
        pt, sp = BER.wait_until(lambda: {k: (es(host, "coopEndTurnTally") or {}).get(k) for k in want} == want and
                                es(host, "coopActiveSeat") == 1 == es(client, "coopActiveSeat"), PAINT_S, 0.1) \
            if ok1 else (False, None)
        ok2, s2 = press_to(host, client, client, FACTION_PLAYER, 3, rec, SIDE_S) if pt else (False, "not pressed")
        return ok1 and pt and ok2, (f"host END TURN -> side 1 turn 2: {ok1} ({s1}); host tally {want} and "
                                    f"coopActiveSeat 1 on both within {PAINT_S} s: {pt} ({sp} s; {tally_view(host)}); "
                                    f"the partner's END TURN alone -> side 0 turn 3: {ok2} ({s2})")

    for name, fn in (("MX-end", mx_end), ("MX-skip", mx_skip), ("MX-back", mx_back), ("MX-alien", mx_alien)):
        if first:
            cells[name] = (False, f"not reached ({first} failed)")
            continue
        try:
            cells[name] = fn()
        except Exception as e:
            cells[name] = (False, f"{type(e).__name__}: {str(e)[:300]}")
        first = None if cells[name][0] else name
    ev["boxes"] = rec.get("boxes")
    return cells, ev


# ===================== main =====================


def run_row(row, order, fn, host, client, crash0, rec):
    """G3F.run_row, except that the row's -common cell (its last) is evaluated in every case."""
    try:
        cells, ev = fn(host, client, crash0, rec)
    except Exception as e:
        cells, ev = {}, {"error": f"{type(e).__name__}: {str(e)[:600]}", "boxes": rec.get("boxes")}
    if order[-1] not in cells:
        cells[order[-1]] = common(host, client, crash0, "after the row's error")
    return verdict(row, order, cells, ev)


def run_boot(tag, key, boot_fn, staging_fn, rows, row_fns):
    host = GameClient("host", None, make_user_dir(f"w2h29_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"w2h29_{tag}_client"))
    m, rec, fails = (host, client), {"boxes": []}, 0
    try:
        try:
            guarded(f"boot {tag.upper()}", lambda: (boot_fn(host, client, key), G3F.reactions_zero(host, client)), m)
        except Miss:
            return fail_all(rows, "boot")
        crash0 = session._crash_log_snapshot()
        try:
            guarded(f"staging {tag.upper()}", lambda: staging_fn(host, client, rec), m)
        except Miss:
            return fail_all(rows, "staging")
        for (row, order), fn in zip(rows, row_fns):
            fails += run_row(row, order, fn, host, client, crash0, rec)
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("h", KEY_H, BER.boot_e6, staging_h, MA_ROWS, (row_ma,))
    fails += run_boot("x", KEY_X, lambda h, c, k: boot_e6_mode(h, c, k, TRADITIONAL),
                      lambda h, c, rec: stage_b2(h, c), MX_ROWS, (row_mx,))
    print(f"test_mc_seat_tally: {'PASS' if not fails else 'FAIL'} ({fails} failing cell(s)) wall "
          f"{time.time() - t0:.1f} s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
