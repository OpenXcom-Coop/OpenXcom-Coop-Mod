"""R5-U5 S-A rows G0, G1, G3, G4, G2 (boot G; owner D235 (a), D240 (a); r5-T8 / the issue #126 fence): every in-battle
gift is one order the host checks - the host writes the seat, the partner applies it from the delta, the receiver gets
the notice and the unit as its gift target, the giver's selection moves on - and the give-unit key's gift target comes
back (the battle screen's first init, a left click, a selection change). Boot G: classic co-op (gamemode 1), lobby key
48617, dirs r5u5_g_host / r5u5_g_client.

Spec: docs repo rewrite/prompts/r5u5_battle_gift_order.md section (f) test_battle_gift.py, as amended by AMENDMENT
R5U5-A1 (A1-1 WALK_G4 on C1's own level, A1-2 G2-cmd's client TAB first; ORCHESTRATOR RULINGS QU5-1 .. QU5-11 (a),
QU5-A1-1 .. QU5-A1-4 (a)). Constants: rewrite/r5u5-task0/sa/CONSTANTS.md (boots Ga, Gb; re-dispatch Ga2, Gb2, Gc2, Gn2).

Boot G = R5-U4's boot C (test_ownerless_units.bring_up, copied with the lobby key as a parameter, F10917): roster seed
1, the Skyranger's crew cut to C1 8 / C2 9 (seat 1) and H 10 (seat 0), one STR_TANK_CANNON (TANK 1000000, seat 0), map
seed 1; pin_ai_neutral; every live unit's reactions 0.
  G0  the gift targets: G0-init (host's in {H, TANK}, client's in {C1, C2}), G0-click (one TAB, one click on TANK: the
      host's target TANK), G0-tab (the host's TAB onto H: target H), G0-common.
  G1  the host gives H by the give-unit key (258) and the menu: G1-menu, G1-give (H seat 1 on both, the `gift` latch +1,
      the host's apply line), G1-recv (the client's notice and target H), G1-giver (the host's selection leaves H),
      G1-cmd (the partner turns H; the host's TAB skips H), G1-common.
  G3  the client gives C2 by its key and menu, the host gives it straight back with no selection step:
      G3-menu, G3-send, G3-seat, G3-recv, G3-back, G3-common.
  G4  three refused gifts by the client's lever: G4-self (target its own seat), G4-partner (the host's TANK:
      not_your_unit), G4-acting (C1 right after its walk to WALK_G4), G4-common.
  G2  the host gives TANK by lever (D235 Part B; LAST: on the unchanged build it desyncs the client): G2-seat, G2-cmd (the
      client's TAB reaches TANK, then the partner turns it, then the host's TAB skips it), G2-notice, G2-tally (the
      host's END TURN tally needs 1), G2-common.
G2-notice is read (and the notice dismissed) right after G2-seat, before G2-cmd's client TAB: a TAB under a
GiftNoticeState never reaches the battle (TASK 0 Gn2, F13425); the cells print in the spec's order.
Red at A1 (the unchanged build + T1-T5): every cell except G0-common, G1-common, G3-common, G4-common.

"The order lands" = the unit's coop is the target on both machines within STEP_S. "The notice" = the receiver's
get_notices holds exactly one new message "<giver caption> gave <name> to you." and the giver's none; the receiver then
dismisses it. "A refusal" = the client's coopIntentsSent.gift +1, the host's intentsReceived.gift.denied +1 within
STEP_S, the unit's coop unchanged on both after wait_host_idle; the host's refusal line and its reason are EVIDENCE.
"The menu" = list_widgets: GiftSoldierMenu, the Text "Gift <name> to another player?", the buttons [<caption>, Cancel]
shown (a POPUP_BOTH window hides them for ~0.25 s, F13206).

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot"; a cell whose precondition cell failed FAILs "not
reached". Common cell: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Ids come from probes (S25).
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_battle_gift.py
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
from test_seat_pacing import tab_select  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402

KEY = "48617"
GIVE_KEY = 258                            # Options::giveUnit, default SDLK_KP2 (Options.cpp :629)
SEED_ROSTER, SEED_MAP = 1, 1              # host set_seed before the lobby / right before newbattle_ok
STEP_S = 30                               # every bounded wait
MENU_S = 5                                # the gift menu after the key (TASK 0: 0.05 s; buttons shown at 0.25 s)
MISSION, CRAFT, TANK_ITEM = "STR_SMALL_SCOUT", "STR_SKYRANGER", "STR_TANK_CANNON"
MAP_FP_C = -4.48310638993e+18             # both machines (Ga, Gb, Ga2, Gb2, Gc2, Gn2)
TANK = 1000000                            # STR_TANK_CANNON, 2 x 2, (14,19,1), seat 0, soldierId -1, name "Tank/Cannon"
KEPT, C1, C2, H = [8, 9, 10], 8, 9, 10    # C1 (14,21,1) / C2 (15,21,1) seat 1, H (14,22,1) seat 0
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"   # the gift menu's target captions (TASK 0 (4))
WALK_G4 = (14, 25, 1)                     # AMENDMENT R5U5-A1 A1-1: C1's level, path_probe steps 4, tuCost 22 on both
ROWS = (("G0", ("G0-init", "G0-click", "G0-tab", "G0-common")),
        ("G1", ("G1-menu", "G1-give", "G1-recv", "G1-giver", "G1-cmd", "G1-common")),
        ("G3", ("G3-menu", "G3-send", "G3-seat", "G3-recv", "G3-back", "G3-common")),
        ("G4", ("G4-self", "G4-partner", "G4-acting", "G4-common")),
        ("G2", ("G2-seat", "G2-cmd", "G2-notice", "G2-tally", "G2-common")))

units, pos, es, top = G3F.units, G3F.pos, G3F.es, G3F.top
not_reached = OWN.not_reached


# ===================== probes (shared with test_battle_gift_pvp.py) =====================


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle_state side / turn / seats, event_state phase / battleId,
    coop_dialog_info, the last 40 engine log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", session.states_stripped),
                      ("battle", lambda g: {k: battle_state(g).get(k) for k in ("side", "turn", "selectedId",
                                                                               "giftSelectedId")}),
                      ("seats", lambda g: {i: u.get("coop") for i, u in units(g).items()}),
                      ("event", lambda g: {k: es(g, k) for k in ("phase", "battleId", "desyncSeen")}),
                      ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
                      ("logTail", lambda g: G3F.log_lines(g)[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def guarded(tag, fn, machines):
    try:
        return fn()
    except Exception as e:
        capture(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)
        raise G3F.Miss(tag)


def gsel(gc):
    b = battle_state(gc)
    return [b.get("selectedId"), b.get("giftSelectedId")]


def sels(host, client):
    return {"host": gsel(host), "client": gsel(client)}


def coops(host, client, uid):
    return [(units(gc).get(uid) or {}).get("coop") for gc in (host, client)]


def name_of(gc, uid):
    u = units(gc).get(uid) or {}
    return u.get("rawName") or u.get("name")


def gift_lines(gc):
    return [ln.split("[coop-gift] ", 1)[1] for ln in G3F.log_lines(gc) if "[coop-gift] " in ln]


def gift_counts(host, client):
    """(the client's coopIntentsSent.gift, the host's intentsReceived.gift admitted, denied)."""
    r = (es(host, "intentsReceived") or {}).get("gift") or {}
    return [(es(client, "coopIntentsSent") or {}).get("gift", 0), r.get("admitted", 0), r.get("denied", 0)]


def dirty_gift(host):
    return ((es(host, "invHostDirty") or {}).get("sets") or {}).get("gift", 0)


def notices(gc):
    return gc.cmd({"cmd": "get_notices"}).get("messages") or []


def idle(host, client, ev):
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]


def clear_popups(gc):
    """Between rows: close a menu or a notice a failed cell left open (recorded)."""
    left = []
    for _ in range(4):
        t = top(gc) or ""
        if "GiftSoldierMenu" in t:
            left.append(gc.cmd({"cmd": "cancel_dialog"}))
        elif "GiftNoticeState" in t:
            left.append(gc.cmd({"cmd": "dismiss_notice"}))
        else:
            break
        time.sleep(0.3)
    return left


def refusal(host, client, actor, target, ev):
    """The client's lever gift {actor, target}: a refusal (module docstring). Fills ev; returns the cell."""
    c0, coop0, n0 = gift_counts(host, client), coops(host, client, actor), len(gift_lines(host))
    r = client.cmd({"cmd": "battle_intent", "kind": "gift", "actor": actor, "target": target})
    ev.update(lever=r, counts0=c0, coop0=coop0)
    if not r.get("ok"):
        return False, f"lever battle_intent gift {{actor {actor}, target {target}}}: {r.get('error')} (want sent)"
    ok, ev["deniedS"] = wait_until(lambda: gift_counts(host, client)[2] >= c0[2] + 1, STEP_S, 0.1)
    idle(host, client, ev)
    c1, coop1 = gift_counts(host, client), coops(host, client, actor)
    want = f"host refused gift iseq {r.get('iseq')} of unit {actor} "
    ev["refusedLine"] = [ln for ln in gift_lines(host)[n0:] if want in ln]
    ev["reason"] = ev["refusedLine"][-1].rsplit(": ", 1)[-1] if ev["refusedLine"] else None
    return (c1[0] == c0[0] + 1 and c1[2] == c0[2] + 1 and c1[1] == c0[1] and coop1 == coop0,
            f"client sent / host admitted / denied {c0} -> {c1} (want sent +1, denied +1 within {STEP_S} s, "
            f"admitted +0); unit {actor} coop host/client {coop0} -> {coop1} (want unchanged); EVIDENCE reason "
            f"{ev['reason']!r}")


# ===================== gift steps =====================


def widgets(gc):
    r = gc.cmd({"cmd": "list_widgets"})
    return r.get("state") or "", [w for w in r.get("widgets") or [] if "text" in w]


def buttons_shown(gc):
    st, w = widgets(gc)
    tb = [x for x in w if "TextButton" in (x.get("type") or "")]
    return bool(tb) and all(x.get("visible") and not x.get("hidden") for x in tb)


def menu_cell(gc, uid, caption, ev):
    """The menu on `gc` for unit `uid` with the one target `caption`, its buttons shown."""
    ok, ev["menuS"] = wait_until(lambda: "GiftSoldierMenu" in (top(gc) or ""), MENU_S, 0.1)
    if not ok:
        return False, (f"{gc.name} stack {session.states_stripped(gc)} {ev['menuS']} s after the key (want a "
                       f"GiftSoldierMenu)")
    shown, ev["shownS"] = wait_until(lambda: buttons_shown(gc), MENU_S, 0.05)
    st, w = widgets(gc)
    texts = [x["text"] for x in w if "TextButton" not in (x.get("type") or "")]
    btns = [x["text"] for x in w if "TextButton" in (x.get("type") or "")]
    title = f"Gift {name_of(gc, uid)} to another player?"
    ev.update(state=st, texts=texts, buttons=btns)
    return ("GiftSoldierMenu" in st and title in texts and btns == [caption, "Cancel"] and shown,
            f"{gc.name} {st}: texts {texts} (want {title!r}), buttons {btns} (want [{caption!r}, 'Cancel']), shown "
            f"{shown} ({ev['shownS']} s)")


def lands(host, client, uid, target, ev, bound=STEP_S):
    ok, ev["landS"] = wait_until(lambda: coops(host, client, uid) == [target, target], bound, 0.2)
    got = coops(host, client, uid)
    return ok, f"unit {uid} coop host/client {got} (want {target} on both within {bound} s; {ev['landS']} s)"


def notice_cell(receiver, giver, before, text, ev, bound=STEP_S):
    """`before` = the receiver's messages before the gift. Dismisses whatever new notice came (the definition)."""
    def new():
        m = notices(receiver)
        return m[len(before):] if m[:len(before)] == before else m
    wait_until(lambda: bool(new()), bound, 0.2)
    got, gm = new(), notices(giver)
    ev.update(notice=got, giverNotices=gm)
    for _ in got:
        receiver.cmd({"cmd": "dismiss_notice"})
        time.sleep(0.3)
    ev["afterDismiss"] = session.states_stripped(receiver)
    return (got == [text] and gm == [],
            f"{receiver.name} new notices {got} (want [{text!r}]); {giver.name} notices {gm} (want none)")


def cmd_cell(host, client, uid, ev, client_tab=False):
    """[G2: the client's TAB reaches uid first;] the partner's turn on uid: one new host context {intent, turn, uid},
    uid faces it on both; then the host's TAB never reaches uid (16 TABs)."""
    parts, ok = [], True
    if client_tab:
        ev["clientTab"] = tab_select(client, uid)
        ev["clientSel"] = battle_state(client).get("selectedId")
        ok = ev["clientTab"]
        parts.append(f"tab_select(client, {uid}) {ev['clientTab']} (selectedId {ev['clientSel']}; want {uid})")
    to = ((units(client).get(uid) or {}).get("direction", 0) + 2) % 8
    pt = OWN.partner_turn(host, client, uid, to, ev.setdefault("turn", {"toDir": to}))
    c_ok, c_txt = OWN.ctx_cell(pt["newCtx"], "intent", "turn", uid)
    ev["hostTab"] = tab_select(host, uid)
    ok = ok and c_ok and pt["dirs"] == [to, to] and not ev["hostTab"]
    parts += [f"{c_txt}; directions host/client {pt['dirs']} (want {to}); partner lastDeny {pt['lastDeny']}",
              f"tab_select(host, {uid}) {ev['hostTab']} (want false)"]
    return ok, "; ".join(parts)


def give_by_menu(gc, caption, ev):
    ev["click"] = gc.cmd({"cmd": "click_widget", "match": caption})
    return ev["click"].get("ok") is not False and not ev["click"].get("error")


# ===================== boot G =====================


def bring_up(host, client, key):
    """test_ownerless_units.bring_up (boot C) with the lobby key as a parameter."""
    m, pre, seated = (host, client), {}, {}

    def lobby():
        host.spawn(); host.connect(); client.spawn(); client.connect()
        host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
        RAW.skirmish_host(host, key)
        RAW.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": RAW.CLIENT_PLAYER})
        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"}); client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: RAW.lobby(host).get("buttonVisible") or None)

    def pre_seat(h):
        """After the craft pin: the Skyranger, every crew soldier after the first three off it, one tank on it."""
        r = h.cmd({"cmd": "newbattle_craft", "type": CRAFT})
        assert r.get("ok"), f"newbattle_craft {CRAFT}: {r}"
        br = h.cmd({"cmd": "base_report"})
        sky = [c for c in br.get("crafts") or [] if c.get("type") == CRAFT]
        assert len(sky) == 1, f"base_report crafts {br.get('crafts')} (want exactly one {CRAFT})"
        cid = sky[0]["id"]
        crew = [s["id"] for s in br.get("soldiers") or [] if s.get("craft") == cid]
        pre.update(craft=cid, crew=crew, kept=crew[:3], cut=[])
        for sid in crew[3:]:
            a = h.cmd({"cmd": "craft_assign", "soldier_id": sid, "craft_id": cid, "on": False})
            assert a.get("ok") and a.get("seated") is False, f"craft_assign {sid} off: {a}"
            pre["cut"].append(sid)
        eq = h.cmd({"cmd": "craft_equip", "item": TANK_ITEM, "count": 1, "craft_id": cid})
        assert eq.get("moved") is True, f"craft_equip {TANK_ITEM}: {eq}"
        cv = h.cmd({"cmd": "base_screen_op", "op": "craft_vehicles", "craft_id": cid, "craft_type": CRAFT})
        pre["vehicles"] = cv.get("vehicles")
        assert (cv.get("vehicles") or {}).get(TANK_ITEM) == 1, f"craft_vehicles: {cv}"

    guarded("G", lobby, m)
    guarded("G", lambda: session.drive_to_battlescape(
        host, client, seated, mission=MISSION, seat_count=2, pre_seat=pre_seat,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    crash0 = session._crash_log_snapshot()
    hb, cb = battle_state(host), battle_state(client)
    view = {"kept": pre.get("kept"), "seated": seated.get("soldierIds"), "vehicles": pre.get("vehicles"),
            "mapFp": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
            "sides": [(hb.get("side"), hb.get("turn")), (cb.get("side"), cb.get("turn"))],
            "seats": [[(units(gc).get(i) or {}).get("coop") for i in (TANK, C1, C2, H)] for gc in m]}
    want = {"kept": KEPT, "seated": [C1, C2], "vehicles": {TANK_ITEM: 1}, "mapFp": [MAP_FP_C, MAP_FP_C],
            "sides": [(0, 1), (0, 1)], "seats": [[0, 1, 1, 0], [0, 1, 1, 0]]}

    def pins():
        assert view == want, f"boot G pins {view} (want {want})"
    guarded("G", pins, m)
    pinned = guarded("G", lambda: session.pin_ai_neutral(host, client, tag="r5u5"), m)
    guarded("G", lambda: G3F.reactions_zero(host, client), m)
    guarded("G", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return dict(view, pinned=pinned), crash0


def row_g0(host, client, crash0):
    cells, ev = {}, {"sel0": sels(host, client)}
    h, c = ev["sel0"]["host"][1], ev["sel0"]["client"][1]
    cells["G0-init"] = (h in (H, TANK) and c in (C1, C2),
                        f"giftSelectedId host {h} (want {H} or {TANK}), client {c} (want {C1} or {C2})")
    tc = OWN.tab_then_click(host, TANK, ev.setdefault("click", {}))
    ok, ev["clickGiftS"] = wait_until(lambda: gsel(host)[1] == TANK, 2, 0.1)
    cells["G0-click"] = (tc[0] and ok, f"tab_then_click(host, {TANK}): {tc[1]}; host [selectedId, giftSelectedId] "
                                       f"{gsel(host)} (want gift {TANK})")
    ev["tabH"] = tab_select(host, H)
    ok, ev["tabGiftS"] = wait_until(lambda: gsel(host)[1] == H, 2, 0.1)
    cells["G0-tab"] = (ev["tabH"] and ok, f"tab_select(host, {H}) {ev['tabH']}; host [selectedId, giftSelectedId] "
                                          f"{gsel(host)} (want gift {H})")
    ev["sel"] = sels(host, client)
    cells["G0-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_g1(host, client, crash0):
    cells, ev = {}, {"sel0": sels(host, client)}
    d0, n0, lines0 = dirty_gift(host), notices(client), len(gift_lines(host))
    host.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
    cells["G1-menu"] = menu_cell(host, H, CLIENT_NAME, ev.setdefault("menu", {}))
    landed = False
    if not cells["G1-menu"][0]:
        not_reached(cells, ("G1-give", "G1-recv", "G1-giver", "G1-cmd"), "G1-menu failed")
    else:
        clicked = give_by_menu(host, CLIENT_NAME, ev)
        landed, l_txt = lands(host, client, H, 1, ev)
        want = f"host applied gift iseq 0: unit {H} seat 0 -> 1"
        line_ok, _ = wait_until(lambda: any(want in ln for ln in gift_lines(host)[lines0:]), 5, 0.2)
        dok, _ = wait_until(lambda: dirty_gift(host) == d0 + 1, 5, 0.1)
        ev.update(sel=sels(host, client), dirty=[d0, dirty_gift(host)], giftLines=gift_lines(host)[lines0:])
        cells["G1-give"] = (clicked and landed and dok and line_ok,
                            f"click_widget {CLIENT_NAME!r} {ev['click']}; {l_txt}; host invHostDirty.sets.gift "
                            f"{ev['dirty']} (want +1); host log {want!r} {'seen' if line_ok else 'absent'}")
    if landed:
        cells["G1-recv"] = notice_cell(client, host, n0, f"{HOST_NAME} gave {name_of(client, H)} to you.", ev)
        ok, _ = wait_until(lambda: gsel(client)[1] == H, 5, 0.1)
        cells["G1-recv"] = (cells["G1-recv"][0] and ok,
                            f"{cells['G1-recv'][1]}; client giftSelectedId {gsel(client)[1]} (want {H})")
        cells["G1-giver"] = (gsel(host)[0] != H, f"host selectedId {gsel(host)[0]} (want not {H})")
        cells["G1-cmd"] = cmd_cell(host, client, H, ev.setdefault("cmd", {}))
    elif cells["G1-menu"][0]:
        not_reached(cells, ("G1-recv", "G1-giver", "G1-cmd"), "G1-give failed: the order did not land")
    ev["selEnd"], ev["cleared"] = sels(host, client), [clear_popups(host), clear_popups(client)]
    ev["invHostDirty"] = es(host, "invHostDirty")
    cells["G1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_g3(host, client, crash0):
    cells, ev = {}, {}
    ev["tabC2"] = tab_select(client, C2)
    ev["sel0"], c0, n0 = sels(host, client), gift_counts(host, client), notices(host)
    client.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
    m_ok, m_txt = menu_cell(client, C2, HOST_NAME, ev.setdefault("menu", {}))
    cells["G3-menu"] = (ev["tabC2"] and m_ok, f"tab_select(client, {C2}) {ev['tabC2']}; {m_txt}")
    landed = False
    if not cells["G3-menu"][0]:
        not_reached(cells, ("G3-send", "G3-seat", "G3-recv", "G3-back"), "G3-menu failed")
    else:
        clicked = give_by_menu(client, HOST_NAME, ev)
        ok, ev["sendS"] = wait_until(lambda: gift_counts(host, client)[:2] == [c0[0] + 1, c0[1] + 1], STEP_S, 0.1)
        c1 = gift_counts(host, client)
        cells["G3-send"] = (clicked and c1[0] == c0[0] + 1 and c1[1] == c0[1] + 1,
                            f"click_widget {HOST_NAME!r} {ev['click']}; client sent / host admitted / denied {c0} -> "
                            f"{c1} (want sent +1, admitted +1 within {STEP_S} s)")
        cells["G3-seat"] = lands(host, client, C2, 0, ev.setdefault("seat", {}))
        landed = cells["G3-seat"][0]
        ev["selSeat"] = sels(host, client)
    if landed:
        r_ok, r_txt = notice_cell(host, client, n0, f"{CLIENT_NAME} gave {name_of(host, C2)} to you.", ev)
        ok, _ = wait_until(lambda: gsel(host)[1] == C2, 5, 0.1)
        cells["G3-recv"] = (r_ok and ok, f"{r_txt}; host giftSelectedId {gsel(host)[1]} (want {C2})")
        b, nb = ev.setdefault("back", {}), notices(client)
        host.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
        bm_ok, bm_txt = menu_cell(host, C2, CLIENT_NAME, b)
        if not bm_ok:
            cells["G3-back"] = (False, f"no selection step, host key: {bm_txt}")
        else:
            clicked = give_by_menu(host, CLIENT_NAME, b)
            bl_ok, bl_txt = lands(host, client, C2, 1, b)
            bn_ok, bn_txt = notice_cell(client, host, nb, f"{HOST_NAME} gave {name_of(client, C2)} to you.", b)
            cells["G3-back"] = (clicked and bl_ok and bn_ok, f"no selection step, host key: {bm_txt}; click "
                                                             f"{b['click']}; {bl_txt}; {bn_txt}")
        b["sel"] = sels(host, client)
    elif cells["G3-menu"][0]:
        not_reached(cells, ("G3-recv", "G3-back"), "G3-seat failed: the order did not land")
    ev["giftLines"], ev["invHostDirty"] = gift_lines(host)[-6:], es(host, "invHostDirty")
    ev["selEnd"], ev["cleared"] = sels(host, client), [clear_popups(host), clear_popups(client)]
    cells["G3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_g4(host, client, crash0):
    cells, ev = {}, {}
    cells["G4-self"] = refusal(host, client, C1, 1, ev.setdefault("self", {}))
    p, d0 = ev.setdefault("partner", {}), es(client, "lastDeny")
    c0 = gift_counts(host, client)
    p["lever"] = client.cmd({"cmd": "battle_intent", "kind": "gift", "actor": TANK, "target": 1})
    if not p["lever"].get("ok"):
        cells["G4-partner"] = (False, f"lever battle_intent gift {{actor {TANK}, target 1}}: {p['lever'].get('error')} "
                                      f"(want sent)")
    else:
        wait_until(lambda: es(client, "lastDeny") != d0, STEP_S, 0.1)
        idle(host, client, p)
        d, c1 = es(client, "lastDeny") or {}, gift_counts(host, client)
        cells["G4-partner"] = (d != d0 and d.get("reason") == "not_your_unit" and c1[2] == c0[2] + 1
                               and coops(host, client, TANK) == [0, 0],
                               f"client lastDeny {d0} -> {d} (want a new not_your_unit); host gift denied {c0[2]} -> "
                               f"{c1[2]} (want +1); TANK coop host/client {coops(host, client, TANK)} (want 0 on both)")
    a = ev.setdefault("acting", {})
    ctx0, c0, coop0 = es(host, "closedContexts") or [], gift_counts(host, client), coops(host, client, C1)
    a["path"] = OWN.path_both(host, client, C1, WALK_G4)
    a["walk"] = client.cmd({"cmd": "battle_intent", "kind": "walk", "actor": C1,
                            "dest": {"x": WALK_G4[0], "y": WALK_G4[1], "z": WALK_G4[2]}})
    a["gift"] = client.cmd({"cmd": "battle_intent", "kind": "gift", "actor": C1, "target": 0})
    ok, a["walkS"] = wait_until(lambda: pos(host, C1) == WALK_G4 and pos(client, C1) == WALK_G4
                                and es(client, "inFlight") is None, STEP_S, 0.1)
    if a["gift"].get("ok"):
        wait_until(lambda: gift_counts(host, client)[2] >= c0[2] + 1, STEP_S, 0.1)
    idle(host, client, a)
    new = new_contexts(ctx0, es(host, "closedContexts") or [])
    c1, coop1 = gift_counts(host, client), coops(host, client, C1)
    x_ok, x_txt = OWN.ctx_cell(new, "intent", "walk", C1)
    at = [pos(host, C1), pos(client, C1)]
    a.update(counts=[c0, c1], at=at, newCtx=new, refused=[ln for ln in gift_lines(host)[-4:] if "refused" in ln])
    r_ok = (a["gift"].get("ok") is True and c1[0] == c0[0] + 1 and c1[2] == c0[2] + 1 and c1[1] == c0[1])
    cells["G4-acting"] = (r_ok and x_ok and at == [WALK_G4, WALK_G4] and coop1 == [1, 1],
                          f"walk lever {a['walk']}; gift lever {a['gift']}; client sent / host admitted / denied {c0} "
                          f"-> {c1} (want sent +1, denied +1); {x_txt}; C1 host/client {at} (want {WALK_G4}); C1 coop "
                          f"{coop0} -> {coop1} (want 1 on both); EVIDENCE refused {a['refused']}")
    ev["selEnd"] = sels(host, client)
    cells["G4-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_g2(host, client, crash0):
    cells, ev = {}, {"sel0": sels(host, client)}
    n0 = notices(client)
    ev["lever"] = host.cmd({"cmd": "battle_gift", "unit_id": TANK, "owner": 1})
    cells["G2-seat"] = lands(host, client, TANK, 1, ev.setdefault("seat", {}))
    ev["selSeat"] = sels(host, client)
    # the notice first (read, then dismissed): a TAB under a GiftNoticeState never reaches the battle
    cells["G2-notice"] = notice_cell(client, host, n0, f"{HOST_NAME} gave {name_of(client, TANK)} to you.",
                                     ev.setdefault("notice", {}), bound=STEP_S if cells["G2-seat"][0] else 0)
    cells["G2-cmd"] = cmd_cell(host, client, TANK, ev.setdefault("cmd", {}), client_tab=True)
    idle(host, client, ev)
    t = es(host, "coopEndTurnTally") or {}
    ev["tally"] = [t, es(client, "coopEndTurnTally")]
    cells["G2-tally"] = (t.get("needed") == 1, f"host coopEndTurnTally {t} (want needed 1: no live unit of the host's)")
    ev.update(selEnd=sels(host, client), giftLines=gift_lines(host)[-6:], invHostDirty=es(host, "invHostDirty"),
              clientDesync=[ln for ln in G3F.log_lines(client) if "[coop-hash] DESYNC" in ln][-2:])
    cells["G2-common"] = G3F.common(host, client, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u5_g_host"))
    client = GameClient("client", None, make_user_dir("r5u5_g_client"))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client, KEY)
            print(f"[r5u5] boot G: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE G line)")
        else:
            fails += G3F.run_row("G0", rows["G0"], lambda: row_g0(host, client, crash0))
            fails += G3F.run_row("G1", rows["G1"], lambda: row_g1(host, client, crash0))
            fails += G3F.run_row("G3", rows["G3"], lambda: row_g3(host, client, crash0))
            fails += G3F.run_row("G4", rows["G4"], lambda: row_g4(host, client, crash0))
            fails += G3F.run_row("G2", rows["G2"], lambda: row_g2(host, client, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
