"""test_mc_seat_tally.py (gm2): END TURN counts a mind-controlled unit for the seat that commands it now, so a side
ends on "a live COMMANDABLE unit" of each seat.

The alien_mc boot (gm2 parallel, key 48737; the client plays the aliens, seat 1): BER.boot_pvp, every unit's reactions
0, the open-ground staging, host END TURN (side 1 turn 1), the alien's walk (XCOM_REACT_SEED: S3 reacts to the
client's walk of A), client END TURN (side 0 turn 2), the soldier's walk (ALIEN_REACT_SEED: A reacts to the host's
real-UI walk of S), host END TURN (side 1 turn 2). Both walks are staging.
  alien_takes_soldier  the alien seat mind-controls the X-COM soldier S4 through the client's psi intent
      (SEED_ALIEN_TAKES):
      alien_takes_soldier-held                    (precondition) one new host context {intent, psi, A}; S4 faction 1,
                                                  mcId A, coop 0 on both
      alien_takes_soldier-client_ends_alien_side  the client's END TURN alone ends the alien side: side 0 turn 3 on
                                                  both within SIDE_S
      alien_takes_soldier-held_on_xcom_side       S4 still controlled at X-COM's side; the host's press alone: side 1
                                                  turn 3 within SIDE_S
      alien_takes_soldier-reverts                 S4 reverted at its controller side's next start: faction 0, coop 0 on
                                                  both
      alien_takes_soldier-turn_denied             the alien seat's turn order on S4 is denied not_your_unit; no new
                                                  host context
      alien_takes_soldier-client_ends_again       the client's press alone: side 0 turn 4 within SIDE_S
      alien_takes_soldier-common                  every bucket EQUAL after the row's last settled side change,
                                                  desyncSeen false, no new crash file
The xcom_mc boot (gm2 traditional, key 48738): BER.boot_pvp with set_mode(host, traditional) after host.connect(),
reactions 0, the open-ground staging.
  soldier_takes_alien  X-COM's S mind-controls the alien seat's unit A through the host's psi_attack test command
      (SEED_SOLDIER_TAKES):
      soldier_takes_alien-traditional_mode    (precondition) turnMode traditional and coopActiveSeat 0 on both before
                                              the psi attack
      soldier_takes_alien-held                (precondition) A faction 0, mcId S, coop 1 on both
      soldier_takes_alien-host_ends_xcom_side the host's END TURN alone ends X-COM's side (the baton's last pass): the
                                              host's side-phase counter +1 within SIDE_S (the alien side, with no live
                                              seat, passes at once)
      soldier_takes_alien-alien_side_skipped  with no further press both machines on side 0 turn 2 within SIDE_S, and
                                              exactly one '[coop-endturn] no seat has a live unit on the active side'
                                              host log line
      soldier_takes_alien-released            A faction 1, coop 1 on both at side 0 turn 2 (released at its controller
                                              side's start)
      soldier_takes_alien-alien_side_returns  the host's press: side 1 turn 2; host tally {needed 1, activeSeat 1} and
                                              coopActiveSeat 1 on both within PAINT_S; the partner's press alone: side
                                              0 turn 3
      soldier_takes_alien-common              every bucket EQUAL right before the press, desyncSeen false, no new crash
                                              file
Every InfoboxState is dismissed on its own machine before any END TURN press (only the top state thinks).

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

KEY_ALIEN_MC, KEY_XCOM_MC = "48737", "48738"
A_ID = 1000000                    # the alien (gm2: the client's, seat 1)
S_ID, S3_ID, S2_ID, S4_ID, S5_ID = 8, 9, 10, 11, 12
TILES = {   # the open-ground staging (z 0): (tile, dir)
    A_ID: ((15, 2, 0), 4), S3_ID: ((18, 6, 0), 7), S_ID: ((15, 9, 0), 0), S2_ID: ((12, 7, 0), 0),
    S4_ID: ((18, 8, 0), 0), S5_ID: ((36, 36, 0), 0), 13: ((33, 33, 0), 0), 14: ((34, 33, 0), 0)}
ALIEN_WALK_DEST, SOLDIER_WALK_DEST = (15, 4, 0), (17, 9, 0)
A_TU = 54
XCOM_REACT_SEED, ALIEN_REACT_SEED, SEED_ALIEN_TAKES, SEED_SOLDIER_TAKES = 1, 1, 1, 1   # A and S not out; both
#                                                                                         conversions succeed
PSI_AMP = "STR_PSI_AMP"
STEP_S, SIDE_S, HOLD_S, PAINT_S = 30, 15, 3, 15
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
PRESS = {"cmd": "battle_action", "action": "end_turn_button"}
ALIEN_MC_ROWS = (("alien_takes_soldier", ("alien_takes_soldier-held", "alien_takes_soldier-client_ends_alien_side",
                                          "alien_takes_soldier-held_on_xcom_side", "alien_takes_soldier-reverts",
                                          "alien_takes_soldier-turn_denied", "alien_takes_soldier-client_ends_again",
                                          "alien_takes_soldier-common")),)
XCOM_MC_ROWS = (("soldier_takes_alien", ("soldier_takes_alien-traditional_mode", "soldier_takes_alien-held",
                                         "soldier_takes_alien-host_ends_xcom_side",
                                         "soldier_takes_alien-alien_side_skipped", "soldier_takes_alien-released",
                                         "soldier_takes_alien-alien_side_returns", "soldier_takes_alien-common")),)


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


def psi_attack_seeded(host, client, actor, target, amp, seed, want_faction, rec, where):
    """The host-local psi_attack test command right after the host's set_seed; bounded wait for the target's faction
    on the host and the host idle, boxes dismissed on their own machines. Returns the command's reply and the wait."""
    host.ok({"cmd": "set_seed", "seed": seed})
    r = host.cmd({"cmd": "battle_action", "action": "psi_attack", "unit": actor, "target": target, "weapon_id": amp})
    ok, s = BER.wait_until(lambda: (poll_box(host, rec, where) or True) and (poll_box(client, rec, where) or True)
                           and es(host, "busyOwnerSeat") == -1 and not battle_state(host).get("isBusy")
                           and (units(host).get(target) or {}).get("faction") == want_faction, STEP_S, 0.2)
    settle(host, client, rec, where)
    return {"reply": {k: r.get(k) for k in ("ok", "tuCost", "tuHave", "error")}, "wait": (ok, s)}


def common(host, client, crash0, at):
    ok, detail = G3F.common(host, client, crash0)
    return ok, f"{detail} (taken {at})"


# ===================== staging =====================


def stage_open_ground(host, client):
    """The open-ground staging by rule: every tile open ground on both machines, every unit placed (none on its own
    tile), A's plasma pistol and S3's rifle by test command; every bucket EQUAL."""
    th = {(t["x"], t["y"]): t for t in host.ok({"cmd": "tile_census", "x0": 0, "x1": 39, "y0": 0, "y1": 39,
                                                 "z0": 0, "z1": 0})["tiles"] if t}
    tc = {(t["x"], t["y"]): t for t in client.ok({"cmd": "tile_census", "x0": 0, "x1": 39, "y0": 0, "y1": 39,
                                                   "z0": 0, "z1": 0})["tiles"] if t}
    parts = lambda t: tuple((t or {}).get("parts", {}).get(p, {}).get("mapDataID")
                            for p in ("floor", "westwall", "northwall", "object"))
    for t in [td[0] for td in TILES.values()] + [ALIEN_WALK_DEST, SOLDIER_WALK_DEST]:
        ph, pc = parts(th.get(t[:2])), parts(tc.get(t[:2]))
        assert ph == pc and ph[0] not in (None, -1) and ph[3] == -1, f"tile {t} parts host {ph} client {pc}"
    for uid, (t, d) in TILES.items():
        place(host, client, uid, t, d)
    both(host, client, {"cmd": "battle_give", "unit": A_ID, "item": "STR_PLASMA_PISTOL",
                        "ammo": "STR_PLASMA_PISTOL_CLIP", "slot": "right", "clear_hands": True}, ("weaponId", "ammoId"))
    both(host, client, {"cmd": "battle_give", "unit": S3_ID, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                        "slot": "right", "clear_hands": True}, ("weaponId", "ammoId"))
    assert_hash_clean(host, client, full=True, what="open-ground staging")


def staging_alien_mc(host, client, rec):
    """The alien_mc boot's chain to side 1 turn 2: the staging, the alien's walk, the soldier's walk. Raises on a
    missed step."""
    stage_open_ground(host, client)
    ok, s = press_to(host, client, host, FACTION_HOSTILE, 1, rec, STEP_S)
    assert ok, f"host END TURN -> side 1 turn 1: {s}"
    set_stat_both(host, client, S3_ID, "reactions", 100)
    set_stat_both(host, client, S3_ID, "firing", 0)
    set_tu_both(host, client, S3_ID, 255)
    prev = session.walk_action_id(host)
    host.ok({"cmd": "set_seed", "seed": XCOM_REACT_SEED})
    session.send_walk(client, A_ID, ALIEN_WALK_DEST)
    session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert not any((units(gc).get(A_ID) or {}).get("isOut") for gc in (host, client)), "A out after its walk"
    set_stat_both(host, client, S3_ID, "reactions", 0)
    ok, s = press_to(host, client, client, FACTION_PLAYER, 2, rec, STEP_S)
    assert ok, f"client END TURN -> side 0 turn 2: {s}"
    set_stat_both(host, client, A_ID, "reactions", 100)
    set_stat_both(host, client, A_ID, "firing", 0)
    set_stat_both(host, client, A_ID, "tu", A_TU, refill=True)
    assert A_ID in ((units(host).get(S_ID) or {}).get("spottedThisTurn") or []), (
        "S does not see A (the soldier's walk needs it)")
    prev = session.walk_action_id(host)
    assert tab_select(host, S_ID), "tab_select S"
    host.ok({"cmd": "set_seed", "seed": ALIEN_REACT_SEED})
    real_click_walk(host, SOLDIER_WALK_DEST)
    session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert not any((units(gc).get(S_ID) or {}).get("isOut") for gc in (host, client)), "S out after its walk"
    set_stat_both(host, client, A_ID, "reactions", 0)
    ok, s = press_to(host, client, host, FACTION_HOSTILE, 2, rec, STEP_S)
    assert ok, f"host END TURN -> side 1 turn 2: {s}"


# ===================== row alien_takes_soldier =====================


def row_alien_takes_soldier(host, client, crash0, rec):
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
    host.ok({"cmd": "set_seed", "seed": SEED_ALIEN_TAKES})
    si = send_intent(host, client, req, notes, timeout=STEP_S)
    ok, s = BER.wait_until(lambda: (poll_box(host, rec, "alien_takes_soldier") or True)
                           and (poll_box(client, rec, "alien_takes_soldier") or True)
                           and es(host, "busyOwnerSeat") == -1 and not battle_state(host).get("isBusy")
                           and (units(host).get(S4_ID) or {}).get("faction") == FACTION_HOSTILE, STEP_S, 0.2)
    tops = settle(host, client, rec, "alien_takes_soldier")
    new = [{k: c.get(k) for k in ("origin", "kind", "actorId")} for c in new_contexts(ctx0, es(host, "closedContexts"))]
    s4 = [mcv(host, S4_ID), mcv(client, S4_ID)]
    ev.update(intent={k: si.get(k) for k in ("sent", "iseq", "answer")}, notes=notes, wait=(ok, s), newCtx=new, s4=s4,
              lastDeny=es(client, "lastDeny"))
    want_s4 = (FACTION_HOSTILE, A_ID, 0, False, 0)
    cells["alien_takes_soldier-held"] = (new == [{"origin": "intent", "kind": "psi", "actorId": A_ID}]
                                         and s4 == [want_s4, want_s4] and tops,
                                         f"new host contexts {new} (want one {{intent, psi, {A_ID}}}); S4 "
                                         f"host/client {s4} (want {want_s4}); both tops BattlescapeState {tops}")
    first = None if cells["alien_takes_soldier-held"][0] else "alien_takes_soldier-held"

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

    def client_ends_alien_side():
        ev["preEnd"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)],
                        "msgs": [msgs(host), msgs(client)]}
        ok_, s_ = press_to(host, client, client, FACTION_PLAYER, 3, rec, SIDE_S)
        ev["postEnd"] = {"ok": ok_, "s": s_, "tally": [tally_view(host), tally_view(client)]}
        return ok_, (f"client END TURN: side 0 turn 3 on both in {s_} s" if ok_ else
                     f"client END TURN: no side 0 turn 3 within {SIDE_S} s; host tally {tally_view(host)}; "
                     f"client tally {tally_view(client)}")

    def held_on_xcom_side():
        s4x = [mcv(host, S4_ID)[:2], mcv(client, S4_ID)[:2]]
        ev["preXcom"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)]}
        ok_, s_ = press_to(host, client, host, FACTION_HOSTILE, 3, rec, SIDE_S)
        good = s4x == [(FACTION_HOSTILE, A_ID)] * 2
        return good and ok_, (f"S4 (faction, mcId) at side 0 turn 3 host/client {s4x} (want ({FACTION_HOSTILE}, "
                              f"{A_ID})); host END TURN alone -> side 1 turn 3: {ok_} ({s_}); host tally "
                              f"{tally_view(host)}")

    def reverts():
        v = [mcv(host, S4_ID)[:3:2], mcv(client, S4_ID)[:3:2]]
        return v == [(FACTION_PLAYER, 0)] * 2, f"S4 (faction, coop) at side 1 turn 3 host/client {v} (want (0, 0))"

    def turn_denied():
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

    def client_ends_again():
        ev["preEnd2"] = {"tally": [tally_view(host), tally_view(client)]}
        ok_, s_ = press_to(host, client, client, FACTION_PLAYER, 4, rec, SIDE_S)
        return ok_, f"client END TURN alone -> side 0 turn 4: {ok_} ({s_}); host tally {tally_view(host)}"

    for name, fn in (("alien_takes_soldier-client_ends_alien_side", client_ends_alien_side),
                     ("alien_takes_soldier-held_on_xcom_side", held_on_xcom_side),
                     ("alien_takes_soldier-reverts", reverts), ("alien_takes_soldier-turn_denied", turn_denied),
                     ("alien_takes_soldier-client_ends_again", client_ends_again)):
        gate(name, fn)
    ev["turnSide"] = [turn_side(host), turn_side(client)]
    cells["alien_takes_soldier-common"] = common(host, client, crash0, f"at (turn, side) {ev['turnSide']}")
    ev["boxes"] = rec.get("boxes")
    return cells, ev


# ===================== the xcom_mc boot and row soldier_takes_alien =====================


def boot_pvp_mode(host, client, port, mode):
    """BER.boot_pvp with ONE added line: set_mode(host, mode) right after
    host.connect() (the host's CoopTurnMode is stamped at the offer)."""
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
    time.sleep(1)   # the change_team broadcast settles on the client (repro_pvp_side_relative's boot phase)
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
    pinned = pin_ai_neutral(host, client, tag="mc-seat-gm2-mode")   # 0 is legal in gm2
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="gm2 bring-up")
    return {"mode": mode, "pinned": pinned}


def row_soldier_takes_alien(host, client, crash0, rec):
    ev, cells = {}, {}
    mode = [(es(gc, "turnMode"), es(gc, "coopActiveSeat")) for gc in (host, client)]
    ev["mode"] = mode
    cells["soldier_takes_alien-traditional_mode"] = (mode == [(TRADITIONAL, 0)] * 2,
                        f"(turnMode, coopActiveSeat) host/client {mode} (want ({TRADITIONAL!r}, 0))")
    amp = give_amp(host, client, S_ID)
    set_stat_both(host, client, S_ID, "psiSkill", 100)
    set_stat_both(host, client, A_ID, "psiStrength", 0)
    ev["sTu"] = set_tu_both(host, client, S_ID, 255)
    ev["amp"] = amp
    ev.update(psi_attack_seeded(host, client, S_ID, A_ID, amp, SEED_SOLDIER_TAKES, FACTION_PLAYER, rec,
                                "soldier_takes_alien"))
    a = [mcv(host, A_ID), mcv(client, A_ID)]
    tops = tops_ready((host, client), rec, "before soldier_takes_alien-host_ends_xcom_side press")
    want_a = (FACTION_PLAYER, S_ID, 1, False, 0)
    cells["soldier_takes_alien-held"] = (a == [want_a] * 2 and tops,
                      f"A host/client {a} (want {want_a}); both tops BattlescapeState {tops}")
    ev["preEnd"] = {"tally": [tally_view(host), tally_view(client)], "units": [unit_rows(host), unit_rows(client)],
                    "msgs": [msgs(host), msgs(client)]}
    cells["soldier_takes_alien-common"] = common(host, client, crash0, "right before the host's press")
    first = (None if cells["soldier_takes_alien-traditional_mode"][0] and cells["soldier_takes_alien-held"][0]
             else ("soldier_takes_alien-traditional_mode" if not cells["soldier_takes_alien-traditional_mode"][0]
                   else "soldier_takes_alien-held"))
    no_live_seat_n, pc = ("[coop-endturn] no seat has a live unit on the active side",
                 lambda: es(host, "coopEndTurnPhaseCounter") or 0)

    def host_ends_xcom_side():   # the side-phase counter: side 1, with no live seat, passes at once
        tops_ready((host, client), rec, "before soldier_takes_alien-host_ends_xcom_side press")
        p0 = pc()
        host.cmd(dict(PRESS))
        ok, s = BER.wait_until(lambda: pc() >= p0 + 1, SIDE_S, 0.1)
        ev["postEnd"] = {"ok": ok, "s": s, "tally": [tally_view(host), tally_view(client)],
                         "tops": [top(host), top(client)]}
        return ok, f"host END TURN alone: host side-phase counter {p0} -> {pc()} within {SIDE_S} s: {ok} ({s} s)"

    def alien_side_skipped():
        t0 = time.time()
        try:
            drive_side_change(host, client, FACTION_PLAYER, want_turn_min=2, timeout=SIDE_S)
            moved = round(time.time() - t0, 2)
        except TimeoutError:
            moved = None
        BER.wait_until(lambda: log_count(host, no_live_seat_n) >= 1, HOLD_S, 0.25)
        n = log_count(host, no_live_seat_n)
        ev["skip"] = {"tally": [tally_view(host), tally_view(client)], "lines": n}
        return moved is not None and n == 1, (f"no further press: both machines on side 0 turn 2 within {SIDE_S} s: "
                                              f"{moved is not None} ({moved} s; (turn, side) host/client "
                                              f"{[turn_side(host), turn_side(client)]}); host '{no_live_seat_n}' "
                                              f"lines {n} (want exactly 1)")

    def back_on_controller_side():
        settle(host, client, rec, "soldier_takes_alien side 0 turn 2")
        v = [mcv(host, A_ID)[:3:2], mcv(client, A_ID)[:3:2]]
        return v == [(FACTION_HOSTILE, 1)] * 2, f"A (faction, coop) at side 0 turn 2 host/client {v} (want (1, 1))"

    def alien_side_returns():
        want = {"needed": 1, "activeSeat": 1}
        ok1, s1 = press_to(host, client, host, FACTION_HOSTILE, 2, rec, SIDE_S)
        pt, sp = BER.wait_until(lambda: {k: (es(host, "coopEndTurnTally") or {}).get(k) for k in want} == want and
                                es(host, "coopActiveSeat") == 1 == es(client, "coopActiveSeat"), PAINT_S, 0.1) \
            if ok1 else (False, None)
        ok2, s2 = press_to(host, client, client, FACTION_PLAYER, 3, rec, SIDE_S) if pt else (False, "not pressed")
        return ok1 and pt and ok2, (f"host END TURN -> side 1 turn 2: {ok1} ({s1}); host tally {want} and "
                                    f"coopActiveSeat 1 on both within {PAINT_S} s: {pt} ({sp} s; {tally_view(host)}); "
                                    f"the partner's END TURN alone -> side 0 turn 3: {ok2} ({s2})")

    for name, fn in (("soldier_takes_alien-host_ends_xcom_side", host_ends_xcom_side),
                     ("soldier_takes_alien-alien_side_skipped", alien_side_skipped),
                     ("soldier_takes_alien-released", back_on_controller_side),
                     ("soldier_takes_alien-alien_side_returns", alien_side_returns)):
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
    host = GameClient("host", None, make_user_dir(f"mc_seat_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"mc_seat_{tag}_client"))
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
    fails = run_boot("alien_mc", KEY_ALIEN_MC, BER.boot_pvp, staging_alien_mc, ALIEN_MC_ROWS,
                     (row_alien_takes_soldier,))
    fails += run_boot("xcom_mc", KEY_XCOM_MC, lambda h, c, k: boot_pvp_mode(h, c, k, TRADITIONAL),
                      lambda h, c, rec: stage_open_ground(h, c), XCOM_MC_ROWS, (row_soldier_takes_alien,))
    print(f"test_mc_seat_tally: {'PASS' if not fails else 'FAIL'} ({fails} failing cell(s)) wall "
          f"{time.time() - t0:.1f} s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
