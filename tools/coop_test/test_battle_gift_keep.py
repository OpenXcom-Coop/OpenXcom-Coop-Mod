"""test_battle_gift_keep.py: in traditional mode a player gives one of its units while it is not its go, the holder
that gives away its last unit passes the go, and a rejoin keeps every gift (a battle gift lasts until the mission ends).
One boot: classic co-op (gamemode 1) with the HOST in TRADITIONAL mode (its user dir made with CoopTurnMode
traditional), lobby key 48619, dirs battle_gift_keep_host / battle_gift_keep_client / battle_gift_keep_client2.

The boot is test_battle_gift.bring_up's recipe (itself test_ownerless_units.bring_up), copied here with the lobby key
and the CAPTURE tag as parameters: roster seed 1, the Skyranger's crew cut to C1 8 / C2 9 (seat 1) and H 10 (seat 0),
one STR_TANK_CANNON (TANK 1000000, seat 0), map seed 1; both machines in traditional mode; pin_ai_neutral; every live
unit's reactions 0.
  gift_off_turn  a gift while it is not the giver's go: baton_at_host (precondition: the baton at seat 0 on both),
      client_gives_off_turn (the off-baton client's give-unit key on its gift target GIFT_UNIT, its menu, a click on
      HostPlayer: the order lands, the host admits it, the client's lastDeny unchanged), off_turn_common.
  last_unit_passes_turn  the holder gives away its last unit: host battle_gift gifts of TANK, H and GIFT_UNIT, each
      landing before the next: all_units_given, baton_passes (the baton at seat 1 on both within STEP_S, the client's
      bar not gray), client_commands_tank (the client's turn of TANK admitted), last_unit_common.
  rejoin_keeps_gifts  a rejoin keeps every gift: the host's seat map M, the client leaves (SRB drop_client_mid_battle),
      a fresh client2 rejoins (SRB rejoin_skirmish, clear_popups), the host RESUMEs (SRB scenario_rejoin_and_resume's
      step): client2_rejoined (precondition: client2's top BattlescapeState, its battleId the host's), seats_kept
      (client2 per unit == the host == M), client2_commands_tank (client2's turn of TANK admitted), rejoin_common (host
      and client2). The last row.
Each receiver presses OK on its gift notices (EVIDENCE).

"The order lands" = the unit's coop is the target on both machines within STEP_S. "Admitted" = one new host context
{intent, turn, <unit>} and the unit faces the new direction on both. One EVIDENCE line per row, then one PASS/FAIL line
per cell, then the row verdict. Every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and
fails every row "boot"; a cell whose precondition failed FAILs "not reached"; a missed rejoin_keeps_gifts staging step
fails client2_rejoined with its CAPTURE line. Common cell: every hash bucket EQUAL, desyncSeen false on both, no new
crash file. Ids come from probes. No skip path; exit 0 only when every cell passes, else 2.

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
STEP_S = 30                               # every bounded wait (measured: each step <= 3 s, the rejoin 5.5 s in all)
TRADITIONAL = "traditional"
TANK, C1, C2, H = GF.TANK, GF.C1, GF.C2, GF.H   # test_battle_gift's ids
GIFT_UNIT = 8                             # the client's gift target at bring-up (the refill picks C1)
HOST_NAME = GF.HOST_NAME                  # the client's menu target caption
ROWS = (("gift_off_turn", ("baton_at_host", "client_gives_off_turn", "off_turn_common")),
        ("last_unit_passes_turn", ("all_units_given", "baton_passes", "client_commands_tank", "last_unit_common")),
        ("rejoin_keeps_gifts", ("client2_rejoined", "seats_kept", "client2_commands_tank", "rejoin_common")))

units, es, top = G3F.units, G3F.es, G3F.top
not_reached = OWN.not_reached


# ===================== shared with test_battle_gift_stage.py / _resume.py =====================


def pre_seat_hook(pre):
    """test_battle_gift.bring_up's pre_seat: after the craft pin, the Skyranger, every crew soldier after the first
    three off it, one tank on it. Fills `pre`."""
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


def gifts_in_order(giver_receiver, a, b, ev):
    """battle_gift test-command gifts [(giver, unit, owner), ...] in order on machines a / b, each landing before the
    next; each receiver presses OK on its new notices (EVIDENCE). Returns (all landed, the first miss)."""
    for giver, uid, owner in giver_receiver:
        receiver = b if giver is a else a
        g, n0 = {"unit": uid, "owner": owner}, GF.notices(receiver)
        g["reply"] = giver.cmd({"cmd": "battle_gift", "unit_id": uid, "owner": owner})
        ok, txt = GF.lands(a, b, uid, owner, g)
        if ok:
            wait_until(lambda: len(GF.notices(receiver)) > len(n0), 5, 0.2)
        g["notices"], g["cleared"] = GF.notices(receiver)[len(n0):], GF.clear_popups(receiver)
        ev.setdefault("gifts", []).append(g)
        if not ok:
            return False, f"{giver.name} battle_gift {{{uid}, owner {owner}}} {g['reply']}: {txt}"
    return True, None


# ===================== the boot =====================


def tally(gc):
    return es(gc, "coopEndTurnTally") or {}


def batons(host, other):
    return [tally(host).get("activeSeat"), tally(other).get("activeSeat")]


def seats(gc):
    return {i: u.get("coop") for i, u in units(gc).items()}


def bring_up(host, client, key, tag):
    """test_battle_gift.bring_up with the lobby key and the CAPTURE tag as parameters, plus the live mode pin
    (traditional on both)."""
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
    want = {"kept": GF.KEPT, "seated": [C1, C2], "vehicles": {GF.TANK_ITEM: 1}, "mapFp": [GF.MAP_FP, GF.MAP_FP],
            "sides": [(0, 1), (0, 1)], "seats": [[0, 1, 1, 0], [0, 1, 1, 0]], "turnMode": [TRADITIONAL, TRADITIONAL]}

    def pins():
        assert view == want, f"the {tag} pins {view} (want {want})"
    GF.guarded(tag, pins, m)
    pinned = GF.guarded(tag, lambda: session.pin_ai_neutral(host, client, tag="test_battle_gift_keep"), m)
    GF.guarded(tag, lambda: G3F.reactions_zero(host, client), m)
    GF.guarded(tag, lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return dict(view, pinned=pinned), crash0


def row_gift_off_turn(host, client, crash0):
    cells, ev = {}, {"sel0": GF.sels(host, client), "tally0": [tally(host), tally(client)]}
    a = batons(host, client)
    cells["baton_at_host"] = (a == [0, 0], f"coopEndTurnTally.activeSeat host/client {a} (want 0 on both: the host's "
                                           f"seat goes first)")
    if not cells["baton_at_host"][0]:
        not_reached(cells, ("client_gives_off_turn",), "baton_at_host failed")
    else:
        g = GF.gsel(client)[1]
        c0, d0, n0 = GF.gift_counts(host, client), es(client, "lastDeny"), GF.notices(host)
        client.ok({"cmd": "inject_input", "kind": "key", "key": GF.GIVE_KEY})
        m_ok, m_txt = GF.menu_cell(client, GIFT_UNIT, HOST_NAME, ev.setdefault("menu", {}))
        if not m_ok:
            cells["client_gives_off_turn"] = (False, f"client giftSelectedId {g} (want {GIFT_UNIT}); key 258: {m_txt}")
        else:
            clicked = GF.give_by_menu(client, HOST_NAME, ev)
            l_ok, l_txt = GF.lands(host, client, GIFT_UNIT, 0, ev)
            wait_until(lambda: GF.gift_counts(host, client)[1] >= c0[1] + 1, STEP_S, 0.1)
            c1, d1 = GF.gift_counts(host, client), es(client, "lastDeny")
            if l_ok:
                wait_until(lambda: len(GF.notices(host)) > len(n0), 5, 0.2)
            ev["hostNotices"] = GF.notices(host)[len(n0):]
            cells["client_gives_off_turn"] = (g == GIFT_UNIT and clicked and l_ok and c1[1] == c0[1] + 1 and d1 == d0,
                                              f"client giftSelectedId {g} (want {GIFT_UNIT}); key 258: {m_txt}; "
                                              f"click_widget {HOST_NAME!r} {ev['click']}; {l_txt}; client sent / host "
                                              f"admitted / denied {c0} -> {c1} (want admitted +1); client lastDeny "
                                              f"{d0} -> {d1} (want unchanged)")
    ev.update(cleared=[GF.clear_popups(host), GF.clear_popups(client)], giftLines=GF.gift_lines(host)[-3:],
              tally=[tally(host), tally(client)], sel=GF.sels(host, client))
    cells["off_turn_common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_last_unit(host, client, crash0):
    cells, ev = {}, {"sel0": GF.sels(host, client)}
    landed, miss = gifts_in_order([(host, u, 1) for u in (TANK, H, GIFT_UNIT)], host, client, ev)
    got = {u: GF.coops(host, client, u) for u in (TANK, H, GIFT_UNIT)}
    cells["all_units_given"] = (landed and all(v == [1, 1] for v in got.values()),
                                f"TANK / H / GIFT_UNIT coop host/client {got} (want 1 on both, each landing within "
                                f"{STEP_S} s before the next){'; ' + miss if miss else ''}")
    if not cells["all_units_given"][0]:
        not_reached(cells, ("baton_passes", "client_commands_tank"), "all_units_given failed")
    else:
        ok, ev["batonS"] = wait_until(lambda: batons(host, client) == [1, 1], STEP_S, 0.1)
        gray = battle_state(client).get("coopOffBatonGray")
        cells["baton_passes"] = (ok and gray is False,
                                 f"activeSeat host/client {batons(host, client)} (want 1 on both within {STEP_S} s; "
                                 f"{ev['batonS']} s); client coopOffBatonGray {gray} (want False)")
        cells["client_commands_tank"] = turn_cell(host, client, TANK, ev)
    ev.update(tally=[tally(host), tally(client)], sel=GF.sels(host, client), giftLines=GF.gift_lines(host)[-4:])
    cells["last_unit_common"] = G3F.common(host, client, crash0)
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


def row_rejoin(host, client, client2, crash0):
    cells, ev = {}, {}
    m = seats(host)
    ev["M"], ev["battleId0"] = m, es(host, "battleId")
    try:
        rejoin(host, client, client2, ev)
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:500]}"
        GF.capture("rejoin_keeps_gifts", err, (host, client2))
        cells["client2_rejoined"] = (False, f"staging: {err}")
    else:
        ok, ev["topsS"] = wait_until(lambda: top(host) == "BattlescapeState" and top(client2) == "BattlescapeState",
                                     STEP_S, 0.25)
        b = [es(host, "battleId"), es(client2, "battleId")]
        cells["client2_rejoined"] = (ok and b[0] == b[1],
                                     f"tops host/client2 {[top(host), top(client2)]} (want BattlescapeState on both "
                                     f"within {STEP_S} s; {ev['topsS']} s); battleId host/client2 {b} (want equal; "
                                     f"before the leave {ev['battleId0']})")
    if not cells["client2_rejoined"][0]:
        not_reached(cells, ("seats_kept", "client2_commands_tank"), "client2_rejoined failed")
    else:
        sh, s2 = seats(host), seats(client2)
        cells["seats_kept"] = (s2 == sh == m, f"client2 seats {s2}; host {sh}; M before the leave {m} (want all equal)")
        cells["client2_commands_tank"] = turn_cell(host, client2, TANK, ev)
    ev.update(tally=[tally(host), tally(client2)], stacks=[session.states_stripped(host), session.states_stripped(client2)],
              offBatonGray=[battle_state(host).get("coopOffBatonGray"), battle_state(client2).get("coopOffBatonGray")])
    cells["rejoin_common"] = G3F.common(host, client2, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("battle_gift_keep_host", options={"CoopTurnMode": TRADITIONAL}))
    client = GameClient("client", None, make_user_dir("battle_gift_keep_client"))
    client2 = GameClient("client2", None, make_user_dir("battle_gift_keep_client2"))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client, KEY, "boot")
            print(f"[test_battle_gift_keep] boot: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            fails += G3F.run_row("gift_off_turn", rows["gift_off_turn"],
                                 lambda: row_gift_off_turn(host, client, crash0))
            fails += G3F.run_row("last_unit_passes_turn", rows["last_unit_passes_turn"],
                                 lambda: row_last_unit(host, client, crash0))
            fails += G3F.run_row("rejoin_keeps_gifts", rows["rejoin_keeps_gifts"],
                                 lambda: row_rejoin(host, client, client2, crash0))
    finally:
        G3F.shut(host, client, client2)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_keep: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
