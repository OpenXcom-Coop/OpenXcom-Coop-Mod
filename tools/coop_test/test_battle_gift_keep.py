"""R5-U5 S-B rows K1, K2, K3 (boot K; owner D235-VL4, D240 (a); RV-U8 D-23 / D-24, VL-U5-4): in traditional mode a player
gives one of its units while it is not its go, the holder that gives away its last unit passes the go, and a rejoin keeps
every gift. Boot K: classic co-op (gamemode 1) with the HOST in TRADITIONAL mode (its user dir made with CoopTurnMode
traditional), lobby key 48619, dirs r5u5_k_host / r5u5_k_client / r5u5_k_client2.

Spec: docs repo rewrite/prompts/r5u5_battle_gift_order.md section (f) test_battle_gift_keep.py (ORCHESTRATOR RULINGS
QU5-1 .. QU5-11 (a); ruling R-U5-SB-1). Constants: rewrite/r5u5-task0/sb/CONSTANTS.md (boots Ka, Kb).

Boot K = boot G's recipe (test_battle_gift.bring_up = R5-U4's boot C, copied here with the lobby key and the CAPTURE tag
as parameters, F10917): roster seed 1, the Skyranger's crew cut to C1 8 / C2 9 (seat 1) and H 10 (seat 0), one
STR_TANK_CANNON (TANK 1000000, seat 0), map seed 1; both machines in traditional mode; pin_ai_neutral; every live unit's
reactions 0.
  K1  a gift off the giver's go (main's "while it is not your turn"): K1-baton (precondition: the baton at seat 0 on
      both), K1-give (the off-baton client's give-unit key on its gift target K1_UNIT, its menu, a click on HostPlayer:
      the order lands, the host admits it, the client's lastDeny unchanged), K1-common.
  K2  the holder gives away its last unit: host lever gifts of TANK, H and K1_UNIT, each landing before the next:
      K2-seats, K2-baton (the baton at seat 1 on both within STEP_S, the client's bar not gray), K2-cmd (the client's turn
      of TANK admitted), K2-common.
  K3  a rejoin keeps every gift (D235-VL4): the host's seat map M, the client leaves (SRB drop_client_mid_battle), a fresh
      client2 rejoins (SRB rejoin_skirmish, clear_popups), the host RESUMEs (SRB scenario_rejoin_and_resume's step):
      K3-rejoin (precondition: client2's top BattlescapeState, its battleId the host's), K3-seats (client2 per unit ==
      the host == M), K3-cmd (client2's turn of TANK admitted), K3-common (host and client2). The last row.
Red at B1: none (green on S-A's build; F12908, F12909). Each receiver presses OK on its gift notices (EVIDENCE).

"The order lands" = the unit's coop is the target on both machines within STEP_S. "Admitted" = one new host context
{intent, turn, <unit>} and the unit faces the new direction on both. One EVIDENCE line per row, then one PASS/FAIL line per
cell, then the row verdict. Every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails
every row "boot"; a cell whose precondition failed FAILs "not reached"; a missed K3 staging step fails K3-rejoin with its
CAPTURE line. Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come from probes
(S25). run in the foreground to completion. ONE run is the result, no skip path; exit 0 only
when every cell passes, else 2.

Run:  python tools/coop_test/test_battle_gift_keep.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import repro_atom_walk as RAW  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_battle_gift as GF  # noqa: E402
import test_skirmish_rejoin_battle as SRB  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402

KEY = "48619"
STEP_S = 30                               # every bounded wait (TASK 0: each step <= 3 s, the rejoin 5.5 s in all)
TRADITIONAL = "traditional"
TANK, C1, C2, H = GF.TANK, GF.C1, GF.C2, GF.H   # boot G's ids (Ka, Kb)
K1_UNIT = 8                               # the client's gift target at bring-up (Ka, Kb: the refill picks C1)
HOST_NAME = GF.HOST_NAME                  # the client's menu target caption (S-A TASK 0; Ka, Kb)
ROWS = (("K1", ("K1-baton", "K1-give", "K1-common")),
        ("K2", ("K2-seats", "K2-baton", "K2-cmd", "K2-common")),
        ("K3", ("K3-rejoin", "K3-seats", "K3-cmd", "K3-common")))

units, es, top = G3F.units, G3F.es, G3F.top
not_reached = OWN.not_reached


# ===================== shared with test_battle_gift_stage.py / _resume.py =====================


def pre_seat_hook(pre):
    """Boot G's pre_seat (test_battle_gift.bring_up): after the craft pin, the Skyranger, every crew soldier after the
    first three off it, one tank on it. Fills `pre`."""
    def pre_seat(h):
        r = h.cmd({"cmd": "newbattle_craft", "type": GF.CRAFT})
        assert r.get("ok"), f"newbattle_craft {GF.CRAFT}: {r}"
        br = h.cmd({"cmd": "base_report"})
        sky = [c for c in br.get("crafts") or [] if c.get("type") == GF.CRAFT]
        assert len(sky) == 1, f"base_report crafts {br.get('crafts')} (want exactly one {GF.CRAFT})"
        cid = sky[0]["id"]
        crew = [s["id"] for s in br.get("soldiers") or [] if s.get("craft") == cid]
        pre.update(craft=cid, crew=crew, kept=crew[:3], cut=[])
        for sid in crew[3:]:
            a = h.cmd({"cmd": "craft_assign", "soldier_id": sid, "craft_id": cid, "on": False})
            assert a.get("ok") and a.get("seated") is False, f"craft_assign {sid} off: {a}"
            pre["cut"].append(sid)
        eq = h.cmd({"cmd": "craft_equip", "item": GF.TANK_ITEM, "count": 1, "craft_id": cid})
        assert eq.get("moved") is True, f"craft_equip {GF.TANK_ITEM}: {eq}"
        cv = h.cmd({"cmd": "base_screen_op", "op": "craft_vehicles", "craft_id": cid, "craft_type": GF.CRAFT})
        pre["vehicles"] = cv.get("vehicles")
        assert (cv.get("vehicles") or {}).get(GF.TANK_ITEM) == 1, f"craft_vehicles: {cv}"
    return pre_seat


def turn_cell(host, other, uid, ev):
    """The partner's turn of `uid` (OWN.partner_turn): admitted = one new host context {intent, turn, uid} and uid faces
    the new direction on both machines."""
    to = ((units(other).get(uid) or {}).get("direction", 0) + 2) % 8
    pt = OWN.partner_turn(host, other, uid, to, ev.setdefault("turn", {"toDir": to}))
    c_ok, c_txt = OWN.ctx_cell(pt["newCtx"], "intent", "turn", uid)
    return (c_ok and pt["dirs"] == [to, to],
            f"{c_txt}; unit {uid} directions host/{other.name} {pt['dirs']} (want {to}); {other.name} lastDeny "
            f"{pt['lastDeny0']} -> {pt['lastDeny']}")


def lever_gifts(giver_receiver, a, b, ev):
    """Lever gifts [(giver, unit, owner), ...] in order on machines a / b, each landing before the next; each receiver
    presses OK on its new notices (EVIDENCE). Returns (all landed, the first miss)."""
    for giver, uid, owner in giver_receiver:
        receiver = b if giver is a else a
        g, n0 = {"unit": uid, "owner": owner}, GF.notices(receiver)
        g["lever"] = giver.cmd({"cmd": "battle_gift", "unit_id": uid, "owner": owner})
        ok, txt = GF.lands(a, b, uid, owner, g)
        if ok:
            wait_until(lambda: len(GF.notices(receiver)) > len(n0), 5, 0.2)
        g["notices"], g["cleared"] = GF.notices(receiver)[len(n0):], GF.clear_popups(receiver)
        ev.setdefault("gifts", []).append(g)
        if not ok:
            return False, f"{giver.name} lever battle_gift {{{uid}, owner {owner}}} {g['lever']}: {txt}"
    return True, None


# ===================== boot K =====================


def tally(gc):
    return es(gc, "coopEndTurnTally") or {}


def batons(host, other):
    return [tally(host).get("activeSeat"), tally(other).get("activeSeat")]


def seats(gc):
    return {i: u.get("coop") for i, u in units(gc).items()}


def bring_up(host, client, key, tag):
    """test_battle_gift.bring_up with the lobby key and the CAPTURE tag as parameters, plus boot K's live
    mode pin (traditional on both)."""
    m, pre, seated = (host, client), {}, {}

    def lobby():
        host.spawn(); host.connect(); client.spawn(); client.connect()
        host.ok({"cmd": "set_seed", "seed": GF.SEED_ROSTER})
        RAW.skirmish_host(host, key)
        RAW.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": RAW.CLIENT_PLAYER})
        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"}); client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: RAW.lobby(host).get("buttonVisible") or None)

    GF.guarded(tag, lobby, m)
    GF.guarded(tag, lambda: session.drive_to_battlescape(
        host, client, seated, mission=GF.MISSION, seat_count=2, pre_seat=pre_seat_hook(pre),
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": GF.SEED_MAP})), m)
    crash0 = session._crash_log_snapshot()
    hb, cb = battle_state(host), battle_state(client)
    view = {"kept": pre.get("kept"), "seated": seated.get("soldierIds"), "vehicles": pre.get("vehicles"),
            "mapFp": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
            "sides": [(hb.get("side"), hb.get("turn")), (cb.get("side"), cb.get("turn"))],
            "seats": [[(units(gc).get(i) or {}).get("coop") for i in (TANK, C1, C2, H)] for gc in m],
            "turnMode": [es(host, "turnMode"), es(client, "turnMode")]}
    want = {"kept": GF.KEPT, "seated": [C1, C2], "vehicles": {GF.TANK_ITEM: 1}, "mapFp": [GF.MAP_FP_C, GF.MAP_FP_C],
            "sides": [(0, 1), (0, 1)], "seats": [[0, 1, 1, 0], [0, 1, 1, 0]], "turnMode": [TRADITIONAL, TRADITIONAL]}

    def pins():
        assert view == want, f"boot {tag} pins {view} (want {want})"
    GF.guarded(tag, pins, m)
    pinned = GF.guarded(tag, lambda: session.pin_ai_neutral(host, client, tag="r5u5"), m)
    GF.guarded(tag, lambda: G3F.reactions_zero(host, client), m)
    GF.guarded(tag, lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return dict(view, pinned=pinned), crash0


def row_k1(host, client, crash0):
    cells, ev = {}, {"sel0": GF.sels(host, client), "tally0": [tally(host), tally(client)]}
    a = batons(host, client)
    cells["K1-baton"] = (a == [0, 0], f"coopEndTurnTally.activeSeat host/client {a} (want 0 on both, D-23)")
    if not cells["K1-baton"][0]:
        not_reached(cells, ("K1-give",), "K1-baton failed")
    else:
        g = GF.gsel(client)[1]
        c0, d0, n0 = GF.gift_counts(host, client), es(client, "lastDeny"), GF.notices(host)
        client.ok({"cmd": "inject_input", "kind": "key", "key": GF.GIVE_KEY})
        m_ok, m_txt = GF.menu_cell(client, K1_UNIT, HOST_NAME, ev.setdefault("menu", {}))
        if not m_ok:
            cells["K1-give"] = (False, f"client giftSelectedId {g} (want {K1_UNIT}); key 258: {m_txt}")
        else:
            clicked = GF.give_by_menu(client, HOST_NAME, ev)
            l_ok, l_txt = GF.lands(host, client, K1_UNIT, 0, ev)
            wait_until(lambda: GF.gift_counts(host, client)[1] >= c0[1] + 1, STEP_S, 0.1)
            c1, d1 = GF.gift_counts(host, client), es(client, "lastDeny")
            if l_ok:
                wait_until(lambda: len(GF.notices(host)) > len(n0), 5, 0.2)
            ev["hostNotices"] = GF.notices(host)[len(n0):]
            cells["K1-give"] = (g == K1_UNIT and clicked and l_ok and c1[1] == c0[1] + 1 and d1 == d0,
                                f"client giftSelectedId {g} (want {K1_UNIT}); key 258: {m_txt}; click_widget "
                                f"{HOST_NAME!r} {ev['click']}; {l_txt}; client sent / host admitted / denied {c0} -> "
                                f"{c1} (want admitted +1); client lastDeny {d0} -> {d1} (want unchanged)")
    ev.update(cleared=[GF.clear_popups(host), GF.clear_popups(client)], giftLines=GF.gift_lines(host)[-3:],
              tally=[tally(host), tally(client)], sel=GF.sels(host, client))
    cells["K1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_k2(host, client, crash0):
    cells, ev = {}, {"sel0": GF.sels(host, client)}
    landed, miss = lever_gifts([(host, u, 1) for u in (TANK, H, K1_UNIT)], host, client, ev)
    got = {u: GF.coops(host, client, u) for u in (TANK, H, K1_UNIT)}
    cells["K2-seats"] = (landed and all(v == [1, 1] for v in got.values()),
                         f"TANK / H / K1_UNIT coop host/client {got} (want 1 on both, each landing within {STEP_S} s "
                         f"before the next){'; ' + miss if miss else ''}")
    if not cells["K2-seats"][0]:
        not_reached(cells, ("K2-baton", "K2-cmd"), "K2-seats failed")
    else:
        ok, ev["batonS"] = wait_until(lambda: batons(host, client) == [1, 1], STEP_S, 0.1)
        gray = battle_state(client).get("coopOffBatonGray")
        cells["K2-baton"] = (ok and gray is False,
                             f"activeSeat host/client {batons(host, client)} (want 1 on both within {STEP_S} s; "
                             f"{ev['batonS']} s); client coopOffBatonGray {gray} (want False)")
        cells["K2-cmd"] = turn_cell(host, client, TANK, ev)
    ev.update(tally=[tally(host), tally(client)], sel=GF.sels(host, client), giftLines=GF.gift_lines(host)[-4:])
    cells["K2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def rejoin(host, client, client2, ev):
    """SRB's leave + rejoin + RESUME (test_skirmish_rejoin_battle.scenario_rejoin_and_resume's steps), bounded."""
    t0 = time.time()
    SRB.drop_client_mid_battle(host, client)
    ev["hostDialog"] = SRB.dialog(host)
    client2.spawn(); client2.connect()
    SRB.rejoin_skirmish(client2, KEY)
    client2.wait_for("client2 back in the battle", lambda: SRB.in_battle_save(client2) or None, timeout=STEP_S,
                     interval=0.25)
    SRB.clear_popups(client2)
    ev["client2Hold"] = SRB.dialog(client2)

    def resume_offered():
        if session.has_state(host, "Profile"):
            host.cmd({"cmd": "profile_ok"})
            return None
        return SRB.dialog(host).get("backVisible") or None
    host.wait_for("host dialog offers RESUME", resume_offered, timeout=STEP_S, interval=0.25)
    ev["hostReady"] = SRB.dialog(host)
    ev["resume"] = host.ok({"cmd": "coop_dialog_back"})
    ev["rejoinS"] = round(time.time() - t0, 2)


def row_k3(host, client, client2, crash0):
    cells, ev = {}, {}
    m = seats(host)
    ev["M"], ev["battleId0"] = m, es(host, "battleId")
    try:
        rejoin(host, client, client2, ev)
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:500]}"
        GF.capture("K3", err, (host, client2))
        cells["K3-rejoin"] = (False, f"staging: {err}")
    else:
        ok, ev["topsS"] = wait_until(lambda: top(host) == "BattlescapeState" and top(client2) == "BattlescapeState",
                                     STEP_S, 0.25)
        b = [es(host, "battleId"), es(client2, "battleId")]
        cells["K3-rejoin"] = (ok and b[0] == b[1],
                              f"tops host/client2 {[top(host), top(client2)]} (want BattlescapeState on both within "
                              f"{STEP_S} s; {ev['topsS']} s); battleId host/client2 {b} (want equal; before the leave "
                              f"{ev['battleId0']})")
    if not cells["K3-rejoin"][0]:
        not_reached(cells, ("K3-seats", "K3-cmd"), "K3-rejoin failed")
    else:
        sh, s2 = seats(host), seats(client2)
        cells["K3-seats"] = (s2 == sh == m, f"client2 seats {s2}; host {sh}; M before the leave {m} (want all equal)")
        cells["K3-cmd"] = turn_cell(host, client2, TANK, ev)
    ev.update(tally=[tally(host), tally(client2)], stacks=[session.states_stripped(host), session.states_stripped(client2)],
              offBatonGray=[battle_state(host).get("coopOffBatonGray"), battle_state(client2).get("coopOffBatonGray")])
    cells["K3-common"] = G3F.common(host, client2, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u5_k_host", options={"CoopTurnMode": TRADITIONAL}))
    client = GameClient("client", None, make_user_dir("r5u5_k_client"))
    client2 = GameClient("client2", None, make_user_dir("r5u5_k_client2"))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client, KEY, "K")
            print(f"[r5u5] boot K: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE K line)")
        else:
            fails += G3F.run_row("K1", rows["K1"], lambda: row_k1(host, client, crash0))
            fails += G3F.run_row("K2", rows["K2"], lambda: row_k2(host, client, crash0))
            fails += G3F.run_row("K3", rows["K3"], lambda: row_k3(host, client, client2, crash0))
    finally:
        G3F.shut(host, client, client2)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_keep: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
