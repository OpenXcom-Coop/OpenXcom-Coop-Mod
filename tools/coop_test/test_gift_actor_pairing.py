"""W2-H43 rows R1, R2, R3, R4 (boot C, classic co-op, gamemode 1): after a gift moves the co-op HOST's selection (it
gave away the soldier it held, or it held none and received one), the host's battle action follows the new selection
at once, an aim it had open ends and the cursor is set up again, as vanilla's Tab does (lead L-H40-2, CONFIRMED by
lh402-capture F16920-F16932; orchestrator ruling R-H43-0; W2-H6-SEL on the host; design-D6).

Spec: docs repo rewrite/prompts/w2h43_gift_actor_pairing.md section (f), orchestrator rulings QH43-1 .. QH43-7 (a).
Constants: rewrite/w2h43-task0/sa/CONSTANTS.md (TASK 0 boots a, b on the unchanged build fe1fa1468, equal on every read;
boot c with E1-E3 applied; every pin kept).

Boot C (key 49046, dirs w2h43_c_host / _client, default options = parallel): test_coop_panic_selection.boot's chain
with the key as a parameter (F10917; asserts map fingerprint, seated [8, 9], unit order, gamemode 1, pinned [A]). Ids
are read at run time (S25): G, N, N2, N3, N4 = the host seat's live units from its entry hold on, C1 = the client's
hold, C2 its next. Staging: G, N, N2, C1 stripped (client first, F16954), then a rifle + clip in the right hand;
hash EQUAL.
Steps: hold(H) = real Tab presses (>= 1) until H is selected; give(H) = the give-unit key GIVE_KEY, the GiftSoldierMenu
click, reads A / B at READ_A / READ_B, the order lands, the host's apply line, the receiver's notice (dismissed);
menu(U) = camera on TARGET (host only), the right-hand key, ActionMenuState, read C; snap = the SNAP row, read D;
act(U) = set_seed SEED_SHOT, one map click on TARGET, the new host closed contexts within ACT_S, read E; unaim = one
right click on TARGET only while the host's cursorType is 2 (in normal mode it would turn the unit).
  R1  (turn 1) hold(G), give(G), menu(N), snap, act(N), unaim. R1-hold, R1-give (preconditions), R1-sel (host selectedId
      N at A and B), R1-pair (actor N and cursorType 1 at A and B), R1-menu (ActionMenuState, actor N at C), R1-act
      (exactly one new context {host, shoot, N}, the client applied its endSeq, A neither dead nor unconscious).
  R2  (turn 2 after TCU.cycle, no note) as R1 with (N, N2).
  R3  hold(N2), menu(N2), snap (the aim stays open), give(N2) while aiming, unaim. R3-aim (precondition: cursorType 2,
      actor and selection N2), R3-give, R3-sel (N3 at A and B), R3-pair (actor N3 at A and B), R3-cursor (1 at A and B).
  R4  (LAST) the host gives N3 and N4 by the battle_gift lever: R4-none (host selectedId and actor -1). The client's
      lever notices dismissed, its real Tab onto C1, its key and menu: R4-recv (C1 seat 0, the host's notice, host
      selectedId C1 at A), R4-pair (actor C1, cursorType 1 at A), R4-client (client selectedId C2 = its actor at A),
      menu(C1) -> R4-menu, snap, act(C1) -> R4-act.
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.

RED on the unchanged build (commit R1): R1-pair, R1-menu, R1-act, R2-pair, R2-menu, R2-act, R3-pair, R3-cursor,
R4-none, R4-pair, R4-menu, R4-act (12 of 27 cells). GREEN (G1, E1-E3): every cell PASS. One EVIDENCE line per row, one
PASS/FAIL line per cell, then the row verdict; every row runs after a failure; a precondition miss ends its row (later
cells "not reached"); a boot miss prints ONE CAPTURE line and fails every row "boot". run in the foreground to
completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_gift_actor_pairing.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, pin_ai_neutral  # noqa: E402
from test_ai_origins import bring_up_lobby_roster_pinned  # noqa: E402
import test_turn_cues as TCU  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_host_combat as HC  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_battle_gift as TBG  # noqa: E402
import test_client_shoot as CSH  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_coop_panic_selection as PS  # noqa: E402
from test_seat_pacing import SDLK_TAB  # noqa: E402

KEY = "49046"
HOST_DIR, CLIENT_DIR = "w2h43_c_host", "w2h43_c_client"    # default options (parallel)
GAMEMODE = 1                      # classic co-op skirmish
A_ID = TCU.A_ID                   # 1000000, the only alien (pinned neutral); TARGET = its tile, (27,12,0) in TASK 0
RIFLE, CLIP = "STR_RIFLE", "STR_RIFLE_CLIP"   # STAGED on G, N, N2, C1 after the strip
GIVE_KEY = 258                    # Options::giveUnit, SDLK_KP2 (also opens the menu while aiming, TASK 0 a / b / c)
KEY_RHAND = 101                   # keyBattleUseRightHand, SDLK_e (ActionMenuState in 0.05 s)
SNAP_NTH = 2                      # the rifle's rows THROW, AUTO, SNAP, AIMED: the SNAP row is the 3rd (cursorType 2)
CT_NORMAL, CT_AIM = 1, 2
SEED_SHOT = 1                     # host set_seed right before each act click (A alive after every act, boot c)
READ_A, READ_B = 0.3, 1.3         # after the gift click (R4: after the notice dismissal, then +1.0 s)
MENU_S, ACT_S, STEP_S = 5, 10, 30
TAB_MAX = 16
DEAD, UNCONSCIOUS = 6, 7          # UnitStatus
HOST_NAME, CLIENT_NAME = TBG.HOST_NAME, TBG.CLIENT_NAME
VIEW = ("side", "turn", "selectedId", "currentActionActorId", "giftSelectedId", "cursorType", "warningText",
        "coopWaitText", "hud")
ROWS = (("R1", ("R1-hold", "R1-give", "R1-sel", "R1-pair", "R1-menu", "R1-act", "R1-common")),
        ("R2", ("R2-hold", "R2-give", "R2-sel", "R2-pair", "R2-menu", "R2-act", "R2-common")),
        ("R3", ("R3-aim", "R3-give", "R3-sel", "R3-pair", "R3-cursor", "R3-common")),
        ("R4", ("R4-none", "R4-recv", "R4-pair", "R4-client", "R4-menu", "R4-act", "R4-common")))

top, units, es = G3F.top, G3F.units, G3F.es
not_reached = OWN.not_reached


def wait_until(pred, timeout, interval=0.05):
    return RM.wait_until(pred, timeout, interval)


def boot(host, client):
    """test_coop_panic_selection.boot's chain with this file's lobby key (F10917: copied with the key)."""
    bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": TCU.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    fp = [hs.get("mapFingerprint"), cs.get("mapFingerprint")]
    assert fp == [TCU.MAP_FP] * 2, f"mapFingerprint host/client {fp} (want {TCU.MAP_FP} on both)"
    assert seated.get("soldierIds") == TCU.SEATED, f"seated {seated.get('soldierIds')} (want {TCU.SEATED})"
    order = [[u["id"] for u in hs.get("units", [])], [u["id"] for u in cs.get("units", [])]]
    assert order == [TCU.UNIT_ORDER] * 2, f"unit order host/client {order} (want {TCU.UNIT_ORDER} on both)"
    gm = [hs.get("coopGamemode"), cs.get("coopGamemode")]
    assert gm == [GAMEMODE] * 2, f"coopGamemode host/client {gm} (want {GAMEMODE} on both)"
    pinned = pin_ai_neutral(host, client, tag="w2h43")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    session.wait_host_idle(host, client, timeout=30)
    return {"mapFP": fp, "seated": seated.get("soldierIds"), "pinned": pinned, "gamemode": gm}


def seat_units(gc, seat):
    return [u["id"] for u in battle_state(gc).get("units", [])
            if u.get("coop") == seat and u.get("faction") == 0 and not u.get("isOut") and u["id"] != A_ID]


def view(gc):
    b = battle_state(gc)
    return dict({k: b.get(k) for k in VIEW}, stack=G3F.stack(gc))


def reads(host, client):
    return {"host": view(host), "client": view(client)}


def hold(gc, uid):
    """Real Tab presses on gc until it holds uid: at least one press, at most TAB_MAX + 1. Returns the presses."""
    presses = []
    for i in range(TAB_MAX + 1):
        if i and presses[-1] == uid:
            break
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.2)
        presses.append(battle_state(gc).get("selectedId"))
    return presses


def at_reads(ev, who, key, want):
    got = [ev[r][who][key] for r in ("A", "B")]
    return got == [want, want], got


def give(host, client, h, ev):
    """give(H) by the host to the client: key, menu, click, reads A / B, lands, the apply line, the notice."""
    n0, l0 = TBG.notices(client), len(TBG.gift_lines(host))
    host.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
    m_ok, m_txt = TBG.menu_cell(host, h, CLIENT_NAME, ev.setdefault("menu", {}))
    if not m_ok:
        return False, f"menu: {m_txt}"
    t0 = time.time()
    clicked = TBG.give_by_menu(host, CLIENT_NAME, ev)
    time.sleep(max(0.0, t0 + READ_A - time.time()))
    ev["A"] = reads(host, client)
    time.sleep(max(0.0, t0 + READ_B - time.time()))
    ev["B"] = reads(host, client)
    landed, l_txt = TBG.lands(host, client, h, 1, ev)
    want = f"host applied gift iseq 0: unit {h} seat 0 -> 1"
    line_ok, _ = wait_until(lambda: any(want in ln for ln in TBG.gift_lines(host)[l0:]), 5, 0.2)
    n_ok, n_txt = TBG.notice_cell(client, host, n0, f"{HOST_NAME} gave {TBG.name_of(client, h)} to you.", ev)
    return (clicked and landed and line_ok and n_ok,
            f"{m_txt}; click {ev['click']}; {l_txt}; host log {want!r} {'seen' if line_ok else 'absent'}; {n_txt}")


def menu(host, target, uid, ev):
    """menu(U): camera on TARGET (host only), the right-hand key, ActionMenuState within MENU_S, read C."""
    ev["cam"] = HC.cam_offset(HC.stage_camera(host, target))
    time.sleep(0.3)
    host.ok({"cmd": "inject_input", "kind": "key", "key": KEY_RHAND})
    ok, s = wait_until(lambda: top(host) == "ActionMenuState", MENU_S)
    ev["C"] = view(host)
    wl = host.cmd({"cmd": "list_widgets"}).get("widgets") or []
    vis = [x for x in wl if x.get("visible") and x.get("interactive")]
    rows = [x for x in vis if "ActionMenuItem" in (x.get("type") or "")]
    ev["menuRows"] = [(x.get("idx"), x.get("x"), x.get("y")) for x in rows]
    ev["snapNth"] = vis.index(rows[SNAP_NTH]) if len(rows) > SNAP_NTH else None
    actor = ev["C"]["currentActionActorId"]
    return (ok and actor == uid, f"host top {ev['C']['stack'][-1:]} {s} s after the right-hand key (want "
                                 f"ActionMenuState within {MENU_S} s); host currentActionActorId {actor} at C "
                                 f"(want {uid})")


def snap(host, ev):
    if ev.get("snapNth") is not None:
        ev["rowClick"] = host.cmd({"cmd": "click_widget", "match": "", "nth": ev["snapNth"]})
        wait_until(lambda: top(host) == "BattlescapeState", MENU_S)
        time.sleep(0.2)
    ev["D"] = view(host)


def act(host, client, target, uid, ev):
    """act(U) after snap: (precondition D cursorType 2, click verified + clicked) exactly one new host context
    {host, shoot, U} within ACT_S, the client applied its endSeq within STEP_S, A neither dead nor unconscious."""
    if ev["D"]["cursorType"] != CT_AIM:
        return False, f"precondition: host cursorType {ev['D']['cursorType']} at D (want {CT_AIM}: aiming)"
    ctx0, seq0 = es(host, "closedContexts") or [], es(host, "lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_SHOT})
    ev["mapClick"] = clk = host.cmd({"cmd": "map_tile_click", "x": target[0], "y": target[1], "z": target[2]})
    if not (clk.get("verified") and clk.get("clicked")):
        return False, f"precondition: map_tile_click {target} {clk} (want verified and clicked)"
    _, ev["ctxS"] = wait_until(lambda: bool(CSH.new_contexts(ctx0, es(host, "closedContexts"))), ACT_S, 0.1)
    new = ev["newCtx"] = CSH.new_contexts(ctx0, es(host, "closedContexts"))
    end_seq = max([c.get("endSeq") or 0 for c in new] or [0])
    applied, ev["appliedS"] = wait_until(lambda: (es(client, "lastSeqApplied") or 0) >= end_seq, STEP_S, 0.1)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    ev["E"] = reads(host, client)
    ev["hostEvs"] = [(e["seq"], e["kind"], e["actionId"]) for e in HC.evs_since(host, seq0)]
    ev["alien"] = [{k: (units(gc).get(A_ID) or {}).get(k) for k in ("status", "health", "stun", "isOut")}
                   for gc in (host, client)]
    ev["tu"] = [(units(gc).get(uid) or {}).get("tu") for gc in (host, client)]
    alive = all(a["status"] not in (DEAD, UNCONSCIOUS) and not a["isOut"] for a in ev["alien"])
    one = len(new) == 1 and len(CSH.mine(new, "host", "shoot", uid)) == 1
    return (one and applied and alive,
            f"new host closedContexts {new} within {ACT_S} s (want exactly one {{origin host, kind shoot, actorId "
            f"{uid}}}); client lastSeqApplied >= endSeq {end_seq}: {applied}; A host/client {ev['alien']} (want "
            f"neither dead nor unconscious); host evs {ev['hostEvs']}; warningText {ev['E']['host']['warningText']!r}")


def unaim(host, target, ev):
    ev["unaimCursor"] = cur = battle_state(host).get("cursorType")
    if cur == CT_AIM:
        ev["unaim"] = host.cmd({"cmd": "map_tile_click", "x": target[0], "y": target[1], "z": target[2],
                                "button": "right"})
        time.sleep(0.5)
        ev["afterUnaim"] = view(host)


# ===================== rows =====================


def row_give(host, client, crash0, row, ids, target, h, nxt, pre=None):
    """R1 / R2: hold(H), give(H), menu(next), snap, act(next), unaim."""
    cells, ev = {}, {"ids": ids, "target": target}
    names = dict(ROWS)[row]
    if pre:
        not_reached(cells, names[1:-1], pre)
        cells[f"{row}-hold"] = (False, pre)
    else:
        ev["hold"] = hold(host, h)
        ev["held"] = view(host)
        held = tuple(ev["held"][k] for k in ("selectedId", "currentActionActorId", "giftSelectedId"))
        cells[f"{row}-hold"] = (held == (h, h, h), f"host Tab presses {ev['hold']}; host selectedId / "
                                                     f"currentActionActorId / giftSelectedId {held} (want {h} / {h} / "
                                                     f"{h})")
        if not cells[f"{row}-hold"][0]:
            not_reached(cells, names[1:-1], f"{row}-hold failed")
        else:
            cells[f"{row}-give"] = give(host, client, h, ev)
            if not cells[f"{row}-give"][0]:
                not_reached(cells, names[2:-1], f"{row}-give failed")
            else:
                ok, got = at_reads(ev, "host", "selectedId", nxt)
                cells[f"{row}-sel"] = (ok, f"host selectedId at A / B {got} (want {nxt})")
                a, b = at_reads(ev, "host", "currentActionActorId", nxt), at_reads(ev, "host", "cursorType", CT_NORMAL)
                cells[f"{row}-pair"] = (a[0] and b[0], f"host currentActionActorId at A / B {a[1]} (want {nxt}; "
                                                       f"unchanged build: {h}); cursorType {b[1]} (want {CT_NORMAL})")
                cells[f"{row}-menu"] = menu(host, target, nxt, ev)
                snap(host, ev)
                cells[f"{row}-act"] = act(host, client, target, nxt, ev)
                unaim(host, target, ev)
    cells[f"{row}-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_r3(host, client, crash0, ids, target):
    cells, ev = {}, {"ids": ids}
    n2, n3 = ids["N2"], ids["N3"]
    names = dict(ROWS)["R3"]
    ev["hold"] = hold(host, n2)
    ev["menuOk"] = menu(host, target, n2, ev)
    snap(host, ev)
    aim = tuple(ev["D"][k] for k in ("cursorType", "currentActionActorId", "selectedId"))
    cells["R3-aim"] = (aim == (CT_AIM, n2, n2), f"host Tab presses {ev['hold']}; before the key host cursorType / "
                                                f"currentActionActorId / selectedId {aim} (want {CT_AIM} / {n2} / "
                                                f"{n2})")
    if not cells["R3-aim"][0]:
        not_reached(cells, names[1:-1], "R3-aim failed")
    else:
        cells["R3-give"] = give(host, client, n2, ev)
        if not cells["R3-give"][0]:
            not_reached(cells, names[2:-1], "R3-give failed")
        else:
            ok, got = at_reads(ev, "host", "selectedId", n3)
            cells["R3-sel"] = (ok, f"host selectedId at A / B {got} (want {n3})")
            ok, got = at_reads(ev, "host", "currentActionActorId", n3)
            cells["R3-pair"] = (ok, f"host currentActionActorId at A / B {got} (want {n3}; unchanged build: {n2})")
            ok, got = at_reads(ev, "host", "cursorType", CT_NORMAL)
            cells["R3-cursor"] = (ok, f"host cursorType at A / B {got} (want {CT_NORMAL}: the aim ended; unchanged "
                                      f"build: {CT_AIM})")
    unaim(host, target, ev)
    cells["R3-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_r4(host, client, crash0, ids, target):
    cells, ev = {}, {"ids": ids}
    names = dict(ROWS)["R4"]
    n3, n4, c1, c2 = ids["N3"], ids["N4"], ids["C1"], ids["C2"]
    nl0 = TBG.notices(client)
    lv = ev["levers"] = []
    for u in (n3, n4):
        r = host.cmd({"cmd": "battle_gift", "unit_id": u, "owner": 1})
        lv.append([u, r.get("ok"), r.get("error"), TBG.lands(host, client, u, 1, ev.setdefault(f"land{u}", {}))])
    t0 = time.time()
    time.sleep(max(0.0, t0 + READ_B - time.time()))
    ev["none"] = reads(host, client)
    if not all(x[1] and x[3][0] for x in lv):
        cells["R4-none"] = (False, f"precondition: lever gifts [unit, ok, error, lands] {lv} (want ok and landed)")
        not_reached(cells, names[1:-1], "R4 lever gifts")
    else:
        got = (ev["none"]["host"]["selectedId"], ev["none"]["host"]["currentActionActorId"])
        cells["R4-none"] = (got == (-1, -1), f"after the lever gifts of {n3}, {n4} (landed) host selectedId / "
                                             f"currentActionActorId {got} at READ_B (want -1 / -1; unchanged build: "
                                             f"-1 / {n3})")
        ev["leverNotices"] = TBG.notices(client)[len(nl0):]
        ev["clientCleared"] = TBG.clear_popups(client)
        n0 = TBG.notices(host)
        ev["clientHold"] = hold(client, c1)
        ch = [battle_state(client).get(k) for k in ("selectedId", "giftSelectedId")]
        parts = [f"client Tab presses {ev['clientHold']}; client selectedId / giftSelectedId {ch} (want {c1})"]
        ok = False
        if ch == [c1, c1]:
            client.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
            m_ok, m_txt = TBG.menu_cell(client, c1, HOST_NAME, ev.setdefault("menu", {}))
            parts.append(m_txt)
            if m_ok:
                clicked = TBG.give_by_menu(client, HOST_NAME, ev)
                landed, l_txt = TBG.lands(host, client, c1, 0, ev)
                text = f"{CLIENT_NAME} gave {TBG.name_of(host, c1)} to you."
                n_ok, n_txt = TBG.notice_cell(host, client, n0, text, ev)
                t1 = time.time()
                ev["A"] = reads(host, client)
                parts += [f"click {ev['click']}", l_txt, n_txt,
                          f"host selectedId at A {ev['A']['host']['selectedId']}"]
                ok = clicked and landed and n_ok and ev["A"]["host"]["selectedId"] == c1
                time.sleep(max(0.0, t1 + 1.0 - time.time()))
                ev["B"] = reads(host, client)
        cells["R4-recv"] = (ok, "; ".join(parts) + f" (want {c1})")
        if not ok:
            not_reached(cells, names[2:-1], "R4-recv failed")
        else:
            a = ev["A"]["host"]
            cells["R4-pair"] = ((a["currentActionActorId"], a["cursorType"]) == (c1, CT_NORMAL),
                                f"host currentActionActorId / cursorType at A {a['currentActionActorId']} / "
                                f"{a['cursorType']} (want {c1} / {CT_NORMAL}; unchanged build: {n3})")
            c = ev["A"]["client"]
            cells["R4-client"] = (c["selectedId"] == c2 == c["currentActionActorId"],
                                  f"client selectedId / currentActionActorId at A {c['selectedId']} / "
                                  f"{c['currentActionActorId']} (want {c2} / {c2})")
            cells["R4-menu"] = menu(host, target, c1, ev)
            snap(host, ev)
            cells["R4-act"] = act(host, client, target, c1, ev)
    cells["R4-common"] = G3F.common(host, client, crash0)
    return cells, ev


# ===================== boot C =====================


def stage(host, client):
    hs, cs = seat_units(host, 0), seat_units(host, 1)
    g = battle_state(host).get("selectedId")
    c1 = battle_state(client).get("selectedId")
    i = hs.index(g)
    order = hs[i:] + hs[:i]
    assert len(order) == 5 and c1 in cs and len(cs) == 2, f"host seat {hs} (entry {g}), client seat {cs} (hold {c1})"
    ids = dict(zip(("G", "N", "N2", "N3", "N4"), order), C1=c1, C2=[u for u in cs if u != c1][0])
    st = {"ids": ids, "target": G3F.pos(host, A_ID), "strip": {}, "give": {}}
    for u in (ids["G"], ids["N"], ids["N2"], ids["C1"]):
        st["strip"][u] = PS.strip(host, client, u)
        st["give"][u] = RM.give_both(host, client, u, RIFLE, CLIP)
    st["hash"] = G3F.hash_now(host, client)
    assert st["hash"] == "all buckets EQUAL", f"hash after staging: {st['hash']}"
    st["tu"] = {u: [(units(gc).get(u) or {}).get("tu") for gc in (host, client)] for u in order + [ids["C1"]]}
    return st


def boot_c(host, client):
    m = (host, client)
    try:
        info = G3F.guarded("C", lambda: boot(host, client), m)
    except G3F.Miss:
        return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE C line)")
    crash0 = session._crash_log_snapshot()
    try:
        st = G3F.guarded("C staging", lambda: stage(host, client), m)
    except G3F.Miss:
        st = None
    print(f"EVIDENCE C staging: {json.dumps({'boot': info, 'staging': st}, sort_keys=True, default=str)}", flush=True)
    if st is None:
        return G3F.fail_all(ROWS, "staging (see the CAPTURE C staging line)")
    ids, target = st["ids"], st["target"]
    rows = dict(ROWS)
    fails = G3F.run_row("R1", rows["R1"], lambda: row_give(host, client, crash0, "R1", ids, target, ids["G"],
                                                           ids["N"]))
    rec, cleared, sides = {"notes": [], "dismissed": [], "cycles": []}, None, None
    try:
        cleared = {"host": TBG.clear_popups(host), "client": TBG.clear_popups(client)}
        TCU.cycle(host, client, None, rec, "R2")
        sides = [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in m]
    except Exception as e:
        rec["notes"].append(f"between R1 and R2: {type(e).__name__}: {str(e)[:300]}")
    print(f"EVIDENCE cycle: {json.dumps({'cleared': cleared, 'rec': rec, 'sides': sides}, default=str)}", flush=True)
    pre = None if (not rec["notes"] and sides == [(0, 2)] * 2) else (
        f"precondition: the cycle notes {rec['notes']}, (side, turn) host/client {sides} (want none, (0, 2))")
    fails += G3F.run_row("R2", rows["R2"], lambda: row_give(host, client, crash0, "R2", ids, target, ids["N"],
                                                            ids["N2"], pre))
    fails += G3F.run_row("R3", rows["R3"], lambda: row_r3(host, client, crash0, ids, target))
    fails += G3F.run_row("R4", rows["R4"], lambda: row_r4(host, client, crash0, ids, target))
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    try:
        fails = boot_c(host, client)
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_gift_actor_pairing: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
