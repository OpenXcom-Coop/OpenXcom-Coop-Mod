"""test_gift_receiver_arm.py (classic co-op, gamemode 1): the co-op gift's RECEIVER arm. (A) A soldier the partner gives
the HOST in the aliens' turn must not become its selection (it holds the AI's alien there), so the host's alien AI never
runs a player soldier. (B) The line "You command no soldiers - spectator mode" goes the moment its player commands a
soldier again, on any side, on both machines. Setup gifts go in battle_state.units order.

The boot (key 49120, dirs gift_receiver_arm_host / _client, default options): test_battle_gift.bring_up copied with the
key as a parameter and WITHOUT session.pin_ai_neutral; reactions 0. Ids at run time (they vary per boot): HOLD0 = the
host's selection before alien_turn_gift, A_ID = its selection at the HOSTILE start.
  alien_turn_gift  turn 1 -> aliens -> turn 2: both press END TURN; the client's gift intent of GU (C2) the moment the
         host's side reads 1; HOLD_S with nothing closed or dismissed. Then the pin (== [A_ID]; a miss fails the rows
         below).
  host_line_clears  turn 2: the host gives all its units by battle_gift, then receives C1 by the client's real
         Tab, give key and menu.
  client_line_clears  turn 2: the client mirror by battle_gift (it gives all, then receives GU by the host's
         battle_gift).
  alien_turn_line_clears  turn 2 -> aliens -> turn 3 (LAST): the host gives all by battle_gift, the client's END
         TURN alone, X (C1) at side 1.
Common cell after each row: every hash bucket EQUAL, desyncSeen false on both, no new crash file. Without the fix:
alien_turn_gift-sel, alien_turn_gift-ai, host_line_clears-clear, client_line_clears-clear,
alien_turn_line_clears-clear, alien_turn_line_clears-sel and alien_turn_line_clears-ai FAIL (7 of 22);
with it every cell PASSES. One EVIDENCE line per row, one PASS/FAIL line per cell, the row verdict; every row runs after
a failure; a precondition miss ends its row ("not reached"); a boot miss prints ONE CAPTURE line and fails every row
"boot". foreground run to completion. ONE run is the result, no skip path; exit 0 only when all cells pass, else 2.
Run:  python tools/coop_test/test_gift_receiver_arm.py
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
import test_battle_gift as TBG  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
from test_seat_pacing import SDLK_TAB  # noqa: E402

KEY = "49120"
HOST_DIR, CLIENT_DIR = "gift_receiver_arm_host", "gift_receiver_arm_client"    # default options
GU, X = TBG.C2, TBG.C1            # 9 (alien_turn_gift's gift to the host, client_line_clears's to the client) /
                                  # 8 (host_line_clears's and alien_turn_line_clears's)
GIVE_KEY = 258                    # Options::giveUnit (SDLK_KP2)
TEXT_SPECTATOR = "You command no soldiers - spectator mode"     # STR_COOP_SPECTATOR_MODE (en-US)
HOSTILE_S, STEP_S, ALIEN_S, NOTICE_S = 30, 30, 60, 5      # 0.05 / 0.10 / ~4 (incl. the hold) / 0.05 s
SAMPLE_S, HOLD_S, READ_N, BAN_S = 0.1, 2.0, 3, 2.0       # 8 side-1 host samples per hold; green clear 0.05 s
TAB_MAX = 16
HOST_NAME, CLIENT_NAME = TBG.HOST_NAME, TBG.CLIENT_NAME
UF = ("coop", "x", "y", "z", "tu", "direction", "hasAI")
ROWS = (("alien_turn_gift", ("alien_turn_gift-turn", "alien_turn_gift-land", "alien_turn_gift-sel",
                             "alien_turn_gift-ai", "alien_turn_gift-next", "alien_turn_gift-common")),
        ("host_line_clears", ("host_line_clears-spectator", "host_line_clears-recv", "host_line_clears-clear",
                              "host_line_clears-sel", "host_line_clears-common")),
        ("client_line_clears", ("client_line_clears-spectator", "client_line_clears-clear", "client_line_clears-sel",
                                "client_line_clears-common")),
        ("alien_turn_line_clears", ("alien_turn_line_clears-spectator", "alien_turn_line_clears-land",
                                    "alien_turn_line_clears-clear", "alien_turn_line_clears-sel",
                                    "alien_turn_line_clears-ai", "alien_turn_line_clears-next",
                                    "alien_turn_line_clears-common")))

not_reached = OWN.not_reached
T0 = [time.time()]


def W(text):
    return "SPECTATOR" if text == TEXT_SPECTATOR else text


def sample(gc, uid, a_id=None):
    """battle_state -> {t, side, turn, selectedId, actor, the line, the unit's / the alien's fields, the stack's top 3}."""
    b = battle_state(gc)
    us = {u["id"]: u for u in b.get("units") or []}
    return {"t": time.time(), "side": b.get("side"), "turn": b.get("turn"), "sel": b.get("selectedId"),
            "actor": b.get("currentActionActorId"), "wait": b.get("coopWaitText"),
            "u": {k: (us.get(uid) or {}).get(k) for k in UF}, "stack": session.states_stripped(gc)[-3:],
            "alien": [(us.get(a_id) or {}).get(k) for k in ("x", "y", "z", "tu", "status")] if a_id is not None else None}


def cs(s):
    """A sample, compact: [t, side, turn, sel, actor, line, [coop, x, y, z, tu, dir, hasAI], top, alien]."""
    return s and [round(s["t"] - T0[0], 2), s["side"], s["turn"], s["sel"], s["actor"], W(s["wait"]),
                  [s["u"][k] for k in UF], (s["stack"] or [""])[-1], s["alien"]]


def tile(s):
    return [s["u"][k] for k in ("x", "y", "z", "tu", "direction")] if s else None


def reads(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("selectedId", "currentActionActorId", "giftSelectedId", "cursorType", "coopWaitText")}


def dismiss_new(gc, before):
    """gc's notices that came after `before`, each dismissed; returns (them, the dismiss replies)."""
    m = TBG.notices(gc)
    got, done = (m[len(before):] if m[:len(before)] == before else m), []
    for _ in got:
        done.append(gc.cmd({"cmd": "dismiss_notice"}).get("ok"))
        time.sleep(0.3)
    return got, done


def hold(gc, uid):
    """test_gift_actor_pairing.hold (copied): real Tab presses until gc holds uid, at least one press."""
    presses = []
    for i in range(TAB_MAX + 1):
        if i and presses[-1] == uid:
            break
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.2)
        presses.append(battle_state(gc).get("selectedId"))
    return presses


def aliens_cycle(host, client, subject, a_id, c):
    """Host side 1 (50 ms poll), the client's gift intent at once, the landing, HOLD_S with nothing closed or dismissed,
    the host's new notices dismissed, then samples (close_nextturn on a NextTurnState top) until the next turn +
    1.5 s."""
    turn0 = battle_state(host).get("turn") or 0
    c["hostileOk"], c["hostileS"] = RM.wait_until(lambda: battle_state(host).get("side") == 1, HOSTILE_S, 0.05)
    c["hostile"] = sample(host, subject, a_id)
    if not c["hostileOk"]:
        return
    hn0, l0 = TBG.notices(host), len(TBG.gift_lines(host))
    c["giftReply"] = client.cmd({"cmd": "battle_intent", "kind": "gift", "actor": subject, "target": 0})
    c["landOk"], c["landS"] = RM.wait_until(lambda: TBG.coops(host, client, subject) == [0, 0], STEP_S, 0.05)
    tl = time.time()
    c.update(land=sample(host, subject, a_id), landClient=sample(client, subject), holdHost=[], holdClient=[])
    while time.time() - tl < HOLD_S:
        c["holdHost"].append(dict(sample(host, subject, a_id), dt=time.time() - tl))
        if len(c["holdHost"]) % 2:
            c["holdClient"].append(sample(client, subject))
        time.sleep(SAMPLE_S)
    c["notices"], c["dismiss"] = dismiss_new(host, hn0)
    c.update(giftLines=TBG.gift_lines(host)[l0:], post=[], postClient=[], closes=[], nextHost=None, nextClient=None)
    end, done = time.time() + ALIEN_S, None
    while time.time() < end and (done is None or time.time() - done <= 1.5):
        s, sc = sample(host, subject, a_id), sample(client, subject)
        c["post"].append(s)
        c["postClient"].append(sc)
        for key, gc, x in (("nextHost", host, s), ("nextClient", client, sc)):
            if c[key] is None and x["side"] == 0 and (x["turn"] or 0) >= turn0 + 1:
                c[key] = x
            if x["stack"] and "NextTurnState" in x["stack"][-1]:
                c["closes"].append([gc.name, round(time.time() - T0[0], 2), gc.cmd({"cmd": "close_nextturn"}).get("ok")])
        done = time.time() if (done is None and c["nextHost"] and c["nextClient"]) else done
        time.sleep(0.03)
    c["nextOk"] = done is not None


def cycle_ev(c):
    ev = {k: c.get(k) for k in ("hostileS", "giftReply", "landS", "notices", "dismiss", "giftLines", "closes")}
    ev.update({k: cs(c.get(k)) for k in ("hostile", "land", "landClient", "nextHost", "nextClient")})
    ev.update(landStack=(c.get("land") or {}).get("stack"), holdClient=[cs(s) for s in c.get("holdClient") or []],
              holdHost=[[round(s["dt"], 2)] + cs(s) for s in c.get("holdHost") or []],
              post=[cs(s) for s in c.get("post") or []], postClient=[cs(s) for s in (c.get("postClient") or [])[::3]])
    return ev


def land_cell(host, c, subject):
    want, land = f"{CLIENT_NAME} gave {TBG.name_of(host, subject)} to you.", c.get("land") or {}
    ok = (bool((c.get("giftReply") or {}).get("ok")) and c.get("landOk") and land.get("side") == 1
          and any("NextTurnState" in x for x in land.get("stack") or []) and c.get("notices") == [want])
    return ok, (f"giftReply {c.get('giftReply')}; unit {subject} coop 0 on both within {STEP_S} s: {c.get('landOk')} "
                f"({c.get('landS')} s); landing side {land.get('side')} (want 1), host stack {land.get('stack')} (want a "
                f"NextTurnState); host new notices {c.get('notices')} (want [{want!r}])")


def sel_cell(c, subject):
    s1 = [s for s in [c["land"]] + c["holdHost"] + c["post"] if s["side"] == 1]
    h1 = [s for s in c["holdHost"] if s["side"] == 1]
    return (len(h1) >= READ_N and all(s["sel"] != subject for s in s1),
            f"host selectedId in the {len(s1)} side-1 samples from the landing {sorted({s['sel'] for s in s1})} (want "
            f"never {subject}; {len(h1)} inside the hold, want >= {READ_N}; without the fix: {subject})")


def ai_cell(c, subject, extra=()):
    """`subject`'s hasAI in every host sample from the landing through the first next-turn sample (+ `extra`)."""
    i = next((k for k, s in enumerate(c["post"]) if s is c["nextHost"]), len(c["post"]) - 1)
    thr = [c["land"]] + c["holdHost"] + c["post"][:i + 1]
    bad = [round(s["t"] - T0[0], 2) for s in list(thr) + list(extra) if s["u"]["hasAI"] is not False]
    return (not bad and c["nextHost"] is not None,
            f"unit {subject} hasAI not false at {bad[:4]} in {len(thr)} host samples (landing .. first next-turn sample) "
            f"and {len(extra)} client samples (want none; without the fix: true on the host once its NextTurnState "
            f"closes)")


def gift_all(host, client, giver, seat_to, ev):
    """The giver's live units of its seat in battle_state.units order, each by battle_gift, each lands; the receiver's
    new notices dismissed (TBG clear_popups); then the giver's line within NOTICE_S and its selectedId -1."""
    receiver, seat = (client, 0) if giver is host else (host, 1)
    ids = [u["id"] for u in battle_state(host).get("units") or []
           if u.get("coop") == seat and u.get("faction") == 0 and not u.get("isOut")]
    ev["giftReplies"] = []
    for uid in ids:
        r = (host.cmd({"cmd": "battle_gift", "unit_id": uid, "owner": seat_to}) if giver is host else
             client.cmd({"cmd": "battle_intent", "kind": "gift", "actor": uid, "target": seat_to}))
        ev["giftReplies"].append([uid, r.get("ok"), r.get("error"), TBG.lands(host, client, uid, seat_to, {})[0]])
    ev["receiverNotices"], ev["cleared"] = TBG.notices(receiver), TBG.clear_popups(receiver)
    line, ev["lineS"] = RM.wait_until(lambda: battle_state(giver).get("coopWaitText") == TEXT_SPECTATOR, NOTICE_S, 0.05)
    g = ev["giver"] = reads(giver)
    return (bool(ids) and all(x[1] and x[3] for x in ev["giftReplies"]) and line and g["selectedId"] == -1,
            f"{giver.name} battle_gift replies [unit, ok, error, landed] {ev['giftReplies']} (want ok and landed); its "
            f"coopWaitText {W(g['coopWaitText'])!r} after {ev['lineS']} s (want the line within {NOTICE_S} s); "
            f"selectedId {g['selectedId']} (want -1)")


def clear_cell(gc):
    """From a landing: gc's coopWaitText every 0.05 s for BAN_S; passes on the first ''."""
    t1, got, first = time.time(), [], None
    while time.time() - t1 < BAN_S:
        w = battle_state(gc).get("coopWaitText")
        got.append(W(w))
        first = round(time.time() - t1, 3) if (w == "" and first is None) else first
        time.sleep(0.05)
    return (first is not None, f"{gc.name} coopWaitText first '' at {first} s (want within {BAN_S} s of the landing; "
                               f"{len(got)} reads, values {sorted(set(got), key=str)}; without the fix: the line "
                               f"throughout)")


def row_alien_turn_gift(host, client, crash0, ids):
    cells, ev, names = {}, {}, dict(ROWS)["alien_turn_gift"]
    ids["HOLD0"] = ev["HOLD0"] = battle_state(host).get("selectedId")
    ev["pressClient"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok12, ev["endTurnS"] = RM.wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20, 0.05)
    ev["endTurnText"] = [battle_state(gc).get("coopEndTurnText") for gc in (host, client)]
    ev["pressHost"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    c = {}
    aliens_cycle(host, client, GU, ids["aliens"][0] if ids["aliens"] else None, c)
    ev["cycle"] = cycle_ev(c)
    a_id = c["hostile"]["sel"]
    au = G3F.units(host).get(a_id) or {}
    ids["A_ID"] = a_id if (au.get("coop"), au.get("faction")) == (-1, 1) else None
    ok = ev["pressClient"].get("ok") and ok12 and ev["pressHost"].get("ok") and c["hostileOk"] and ids["A_ID"] is not None
    cells["alien_turn_gift-turn"] = (ok, f"presses client {ev['pressClient']} / host {ev['pressHost']}; END TURN "
                                         f"texts host/client {ev['endTurnText']} (want 'END TURN 1/2' within 20 s); "
                                         f"host side 1 within {HOSTILE_S} s: {c['hostileOk']} ({c['hostileS']} s); "
                                         f"host selectedId at its first side-1 sample {a_id}, coop / faction "
                                         f"{(au.get('coop'), au.get('faction'))} (want an alien: -1 / 1)")
    if not ok:
        not_reached(cells, names[1:-1], "alien_turn_gift-turn failed")
    else:
        l_ok, l_txt = land_cell(host, c, GU)
        want = f": unit {GU} seat 1 -> 0"
        line = [ln for ln in c["giftLines"] if ln.startswith("host applied gift iseq ") and ln.endswith(want)]
        cells["alien_turn_gift-land"] = (l_ok and len(line) == 1,
                                         f"{l_txt}; host line 'host applied gift iseq <n>{want}' {line}")
        if not cells["alien_turn_gift-land"][0]:
            not_reached(cells, names[2:-1], "alien_turn_gift-land failed")
        else:
            cells["alien_turn_gift-sel"] = sel_cell(c, GU)
            cells["alien_turn_gift-ai"] = ai_cell(c, GU, [c["landClient"]] + c["holdClient"] + c["postClient"])
            nh, nc = c["nextHost"], c["nextClient"]
            ev["walkLines"] = sum(1 for ln in G3F.log_lines(host) if "Walking from" in ln)
            ok = c["nextOk"] and nh["sel"] == ids["HOLD0"] and [tile(nh), tile(nc)] == [tile(c["land"]), tile(c["landClient"])]
            cells["alien_turn_gift-next"] = (ok, f"both side 0 turn 2 within {ALIEN_S} s: {c['nextOk']}; host "
                                                 f"selectedId at its first turn-2 sample {nh and nh['sel']} (want "
                                                 f"HOLD0 {ids['HOLD0']}); GU x/y/z/tu/dir host {tile(nh)} client "
                                                 f"{tile(nc)} (want the landing's {tile(c['land'])} / "
                                                 f"{tile(c['landClient'])}); EVIDENCE host 'Walking from' lines "
                                                 f"{ev['walkLines']}")
    cells["alien_turn_gift-common"] = G3F.common(host, client, crash0)
    return cells, ev


def between(host, client, ids):
    """Popups cleared, NextTurnStates closed, host idle, the pin == [A_ID], hash EQUAL. Returns a miss text or None."""
    ev = {"cleared": [TBG.clear_popups(host), TBG.clear_popups(client)], "closes": []}
    for _ in range(6):
        tops = [gc for gc in (host, client) if "NextTurnState" in (G3F.top(gc) or "")]
        if not tops:
            break
        ev["closes"] += [[gc.name, gc.cmd({"cmd": "close_nextturn"}).get("ok")] for gc in tops]
        time.sleep(0.3)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
        ev["pin"] = session.pin_ai_neutral(host, client, tag="gift_receiver_arm")
    except Exception as e:
        ev["pin"] = f"{type(e).__name__}: {str(e)[:300]}"
    ev.update(hash=G3F.hash_now(host, client), want=[ids["A_ID"]] if ids.get("A_ID") is not None else ids["aliens"])
    print(f"EVIDENCE between: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    if ev["pin"] == ev["want"] and ev["hash"] == "all buckets EQUAL":
        return None
    return f"precondition: the pin {ev['pin']} (want {ev['want']}), hash {ev['hash']} (want all buckets EQUAL)"


def row_host_line_clears(host, client, crash0, ids):
    cells, ev, names = {}, {}, dict(ROWS)["host_line_clears"]
    cells["host_line_clears-spectator"] = gift_all(host, client, host, 1, ev.setdefault("giftReplies", {}))
    if not cells["host_line_clears-spectator"][0]:
        not_reached(cells, names[1:-1], "host_line_clears-spectator failed")
    else:
        ev["tab"] = hold(client, X)
        held, n0 = [battle_state(client).get(k) for k in ("selectedId", "giftSelectedId")], TBG.notices(host)
        client.ok({"cmd": "inject_input", "kind": "key", "key": GIVE_KEY})
        m_ok, m_txt = TBG.menu_cell(client, X, HOST_NAME, ev.setdefault("menu", {}))
        landed, l_txt = False, "not clicked"
        if m_ok:
            clicked = TBG.give_by_menu(client, HOST_NAME, ev)
            landed, l_txt = TBG.lands(host, client, X, 0, ev.setdefault("land", {}))
            landed = landed and clicked
        cells["host_line_clears-recv"] = (held == [X, X] and len(ev["tab"]) >= 1 and m_ok and landed,
                                          f"client Tab presses {ev['tab']}; client selectedId / giftSelectedId {held} "
                                          f"(want {X}); {m_txt}; click {ev.get('click')}; {l_txt}")
        if not cells["host_line_clears-recv"][0]:
            not_reached(cells, names[2:-1], "host_line_clears-recv failed")
        else:
            cells["host_line_clears-clear"] = clear_cell(host)
            n_ok, n_txt = TBG.notice_cell(host, client, n0, f"{CLIENT_NAME} gave {TBG.name_of(host, X)} to you.",
                                          ev.setdefault("notice", {}))
            a = ev["A"] = reads(host)
            cells["host_line_clears-sel"] = (n_ok and a["selectedId"] == X == a["currentActionActorId"]
                                             and a["cursorType"] == 1,
                                             f"{n_txt}; at A host selectedId / currentActionActorId / cursorType "
                                             f"{a['selectedId']} / {a['currentActionActorId']} / {a['cursorType']} "
                                             f"(want {X} / {X} / 1)")
    ev.update(giftLines=TBG.gift_lines(host)[-4:], client=reads(client))
    cells["host_line_clears-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_client_line_clears(host, client, crash0, ids):
    cells, ev, names = {}, {}, dict(ROWS)["client_line_clears"]
    cells["client_line_clears-spectator"] = gift_all(host, client, client, 0, ev.setdefault("giftReplies", {}))
    if not cells["client_line_clears-spectator"][0]:
        not_reached(cells, names[1:-1], "client_line_clears-spectator failed")
    else:
        cn0 = TBG.notices(client)
        ev["giftReply"] = host.cmd({"cmd": "battle_gift", "unit_id": GU, "owner": 1})
        landed, l_txt = TBG.lands(host, client, GU, 1, ev.setdefault("land", {}))
        if not (ev["giftReply"].get("ok") and landed):
            cells["client_line_clears-clear"] = (False, f"precondition: host battle_gift {GU} -> 1 {ev['giftReply']}; "
                                                        f"{l_txt}")
            not_reached(cells, names[2:-1], "client_line_clears-clear's precondition failed")
        else:
            cells["client_line_clears-clear"] = clear_cell(client)
            got, ev["dismiss"] = dismiss_new(client, cn0)
            a, want = reads(client), f"{HOST_NAME} gave {TBG.name_of(client, GU)} to you."
            ev.update(notices=got, A=a)
            cells["client_line_clears-sel"] = (got == [want] and a["selectedId"] == GU == a["currentActionActorId"],
                                               f"client new notices {got} (want [{want!r}]); at A client selectedId / "
                                               f"currentActionActorId {a['selectedId']} / {a['currentActionActorId']} "
                                               f"(want {GU} / {GU})")
    ev.update(giftLines=TBG.gift_lines(host)[-4:], host=reads(host))
    cells["client_line_clears-common"] = G3F.common(host, client, crash0)
    return cells, ev


def row_alien_turn_line_clears(host, client, crash0, ids):
    cells, ev, names = {}, {}, dict(ROWS)["alien_turn_line_clears"]
    s_ok, s_txt = gift_all(host, client, host, 1, ev.setdefault("giftReplies", {}))
    xh = ev["xHost"] = (G3F.units(host).get(X) or {}).get("hasAI")
    cells["alien_turn_line_clears-spectator"] = (s_ok and xh is False, f"{s_txt}; X {X} host hasAI {xh} (want false)")
    if not cells["alien_turn_line_clears-spectator"][0]:
        not_reached(cells, names[1:-1], "alien_turn_line_clears-spectator failed")
    else:
        ev.update(cleared=[TBG.clear_popups(host), TBG.clear_popups(client)], tally=G3F.es(host, "coopEndTurnTally"))
        ev["press"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        ev["endTurnHost"], c = battle_state(host).get("coopEndTurnText"), {}
        aliens_cycle(host, client, X, ids.get("A_ID"), c)
        ev["cycle"] = cycle_ev(c)
        l_ok, l_txt = land_cell(host, c, X) if c["hostileOk"] else (False, f"host side 1 within {HOSTILE_S} s: False")
        cells["alien_turn_line_clears-land"] = (bool(ev["press"].get("ok")) and l_ok,
                                                f"client press {ev['press']} (host tally {ev['tally']}); side 1 in "
                                                f"{c['hostileS']} s; {l_txt}")
        if not cells["alien_turn_line_clears-land"][0]:
            not_reached(cells, names[2:-1], "alien_turn_line_clears-land failed")
        else:
            h1 = [s for s in c["holdHost"] if s["side"] == 1 and s["dt"] <= BAN_S]
            clr, vals = [round(s["dt"], 2) for s in h1 if s["wait"] == ""], sorted({str(W(s["wait"])) for s in h1})
            cells["alien_turn_line_clears-clear"] = (bool(clr), f"host coopWaitText '' in side-1 hold samples at {clr} "
                                                                f"s after the landing ({len(h1)} within {BAN_S} s, "
                                                                f"values {vals}; without the fix: the line)")
            cells["alien_turn_line_clears-sel"], cells["alien_turn_line_clears-ai"], nh = (
                sel_cell(c, X), ai_cell(c, X), c["nextHost"])
            cells["alien_turn_line_clears-next"] = (c["nextOk"] and nh["sel"] == X and nh["wait"] == "",
                                                    f"both side 0 turn 3 within {ALIEN_S} s: {c['nextOk']}; host "
                                                    f"selectedId / line at its first turn-3 sample {nh and nh['sel']} "
                                                    f"/ {nh and W(nh['wait'])!r} (want {X} / '')")
    ev["giftLines"] = TBG.gift_lines(host)[-4:]
    cells["alien_turn_line_clears-common"] = G3F.common(host, client, crash0)
    return cells, ev


def pin_missed(row, pre, host, client, crash0):
    """A pin miss: the row's first cell FAILs `pre`, its later cells "not reached"; the common cell still runs."""
    names = dict(ROWS)[row]
    cells = {names[0]: (False, pre), names[-1]: G3F.common(host, client, crash0)}
    not_reached(cells, names[1:-1], pre)
    return cells, {"error": pre}


def bring_up(host, client, key):
    """test_battle_gift.bring_up with the key as a parameter and WITHOUT session.pin_ai_neutral: roster seed
    1, map seed 1, STR_SMALL_SCOUT, the Skyranger crew cut to KEPT, one tank; reactions 0; host idle."""
    m, pre, seated = (host, client), {}, {}

    def lobby():
        host.spawn(); host.connect(); client.spawn(); client.connect()
        host.ok({"cmd": "set_seed", "seed": TBG.SEED_ROSTER})
        RAW.skirmish_host(host, key)
        RAW.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": RAW.CLIENT_PLAYER})
        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"}); client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: RAW.lobby(host).get("buttonVisible") or None)

    def pre_seat(h):
        r = h.cmd({"cmd": "newbattle_craft", "type": TBG.CRAFT})
        assert r.get("ok"), f"newbattle_craft {TBG.CRAFT}: {r}"
        br = h.cmd({"cmd": "base_report"})
        sky = [c for c in br.get("crafts") or [] if c.get("type") == TBG.CRAFT]
        assert len(sky) == 1, f"base_report crafts {br.get('crafts')} (want exactly one {TBG.CRAFT})"
        cid = sky[0]["id"]
        crew = [s["id"] for s in br.get("soldiers") or [] if s.get("craft") == cid]
        pre.update(craft=cid, crew=crew, kept=crew[:3], cut=[])
        for sid in crew[3:]:
            a = h.cmd({"cmd": "craft_assign", "soldier_id": sid, "craft_id": cid, "on": False})
            assert a.get("ok") and a.get("seated") is False, f"craft_assign {sid} off: {a}"
            pre["cut"].append(sid)
        eq = h.cmd({"cmd": "craft_equip", "item": TBG.TANK_ITEM, "count": 1, "craft_id": cid})
        assert eq.get("moved") is True, f"craft_equip {TBG.TANK_ITEM}: {eq}"
        cv = h.cmd({"cmd": "base_screen_op", "op": "craft_vehicles", "craft_id": cid, "craft_type": TBG.CRAFT})
        pre["vehicles"] = cv.get("vehicles")
        assert (cv.get("vehicles") or {}).get(TBG.TANK_ITEM) == 1, f"craft_vehicles: {cv}"

    TBG.guarded("boot", lobby, m)
    TBG.guarded("boot", lambda: session.drive_to_battlescape(
        host, client, seated, mission=TBG.MISSION, seat_count=2, pre_seat=pre_seat,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": TBG.SEED_MAP})), m)
    crash0 = session._crash_log_snapshot()
    hb, cb = battle_state(host), battle_state(client)
    view = {"kept": pre.get("kept"), "seated": seated.get("soldierIds"), "vehicles": pre.get("vehicles"),
            "mapFp": [hb.get("mapFingerprint"), cb.get("mapFingerprint")],
            "sides": [(hb.get("side"), hb.get("turn")), (cb.get("side"), cb.get("turn"))],
            "seats": [[(G3F.units(gc).get(i) or {}).get("coop") for i in (TBG.TANK, TBG.C1, TBG.C2, TBG.H)] for gc in m]}
    want = {"kept": TBG.KEPT, "seated": [TBG.C1, TBG.C2], "vehicles": {TBG.TANK_ITEM: 1},
            "mapFp": [TBG.MAP_FP, TBG.MAP_FP], "sides": [(0, 1), (0, 1)], "seats": [[0, 1, 1, 0], [0, 1, 1, 0]]}

    def pins():
        assert view == want, f"boot pins {view} (want {want})"
    TBG.guarded("boot", pins, m)
    TBG.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
    TBG.guarded("boot", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    view["aliens"] = [u["id"] for u in hb.get("units") or [] if (u.get("coop"), u.get("faction")) == (-1, 1)]
    return view, crash0


def main():
    T0[0] = time.time()
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    fails = 0
    try:
        try:
            boot, crash0 = bring_up(host, client, KEY)
            print(f"EVIDENCE boot: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            ids, rows = {"aliens": boot["aliens"]}, dict(ROWS)
            fails += G3F.run_row("alien_turn_gift", rows["alien_turn_gift"],
                                 lambda: row_alien_turn_gift(host, client, crash0, ids))
            try:
                pre = between(host, client, ids)
            except Exception as e:
                pre = f"precondition: the pin ({type(e).__name__}: {str(e)[:300]})"
            for row, fn in (("host_line_clears", row_host_line_clears), ("client_line_clears", row_client_line_clears),
                            ("alien_turn_line_clears", row_alien_turn_line_clears)):
                fails += G3F.run_row(row, rows[row], lambda: pin_missed(row, pre, host, client, crash0) if pre else
                                     fn(host, client, crash0, ids))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_gift_receiver_arm: {'PASS' if not fails else 'FAIL'} in {time.time() - T0[0]:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
