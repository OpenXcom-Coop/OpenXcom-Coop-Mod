"""test_pve2.py: PvE2 (gamemode 4) - both players command the generated aliens against an AI-run X-COM squad, as the
released game plays it, with the X-COM soldiers re-skinned (re-typed, blank name).

The boot (lobby key 48862), in the steps the CAPTURE lines name:
  1-2  both machines start; the host sets SEED_ROSTER; the lobby puts the client on the Alien team (gamemode 2), then
       the host's own row on Alien (gamemode 4).
  3    both lobby rows show Alien on both machines.
  4    the host at the battle settings: STR_MEDIUM_SCOUT on map seed SEED_MAP.
  5    both briefings (a refusal ends the wait at once).
  6    both briefings closed; both pre-battle equip screens; with both Turn 1 screens up, the unit snapshot and the
       swapped_start-bleed option sequence.
  7    pin_ai_neutral and every live unit's reactions 0.
  8    the client's Turn 1 screen closed, then the host's; the stable settle.
  9    the crash-folder snapshot.
Rows:
  swapped_start  the battle starts swapped and split: battle_ready saveBlob EQUAL once; gamemode 4; authority; every
      alien player-side (faction 0, original 0), SEAT1_IDS on coop 1 and SEAT0_IDS on coop 0; every X-COM soldier
      AI-side (faction 1, original 1, coop -1); no AI module on a player-side unit; the re-skin (type TYPE_BY_ID, a
      blank name, no id offset); the X-COM soldiers' wound rule follows Alien Bleeding (off / on / off) on both
      machines.
  client_orders  the client walks its own alien C1 (one intent context); its order for the host's alien H1 is denied
      not_your_unit.
  host_ui_walk  the host walks its own alien H1 through its UI (one TAB, the TAB cycle lands only on seat-0 aliens, one
      click).
  xcom_wiped  the host kills every X-COM soldier, both seats press END TURN: aliensDown, both seats win, both machines
      end on the host's debriefing (the client's is display-only).
Common cell after each row: every hash bucket EQUAL (xcom_wiped: right before the kill), desyncSeen false on both, no
new file in the lane crash folder.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A boot
step past its bound prints ONE CAPTURE boot line and fails every cell "boot" (on a build that refuses gm4 the client
logs `refused: unsupported` and the host's `battle_refuse received` line ends the briefing wait at once). A staging step
past its bound fails the rows that need it (client_orders, host_ui_walk) "staging". run in the foreground to
completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_pve2.py
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
from test_seat_pacing import real_click_walk, SDLK_TAB  # noqa: E402
from test_battle_end_rules import host_chain_done, host_next_turn_up, wait_until  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_pvp_gm3 import (Miss, stack, top, log_lines, log_count, bview, units, pos, es, capture, guarded,  # noqa: E402
                             tele_both, reactions_zero, hash_now, common, ctx_cell, verdict, run_row, fail_all, shut,
                             record_view)

KEY = "48862"
SEED_ROSTER = 1                   # set_seed on the host before its lobby
SEED_MAP = 1                      # set_seed on the host right before newbattle_ok (N = 5 >= 2: no hunt)
MISSION = "STR_MEDIUM_SCOUT"
GAMEMODE_PVE2 = 4
MAP_FP = 7.136941435423656e+17    # both machines' mapFingerprint
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
ALIEN_IDS = [1000000, 1000001, 1000002, 1000003, 1000004]   # 3 STR_SECTOID_SOLDIER, 2 STR_SECTOID_NAVIGATOR; list order
SEAT1_IDS = [1000000, 1000001]                              # the first floor(5/2) in unit-list order: the client seat
SEAT0_IDS = [1000002, 1000003, 1000004]                     # the rest: the host's seat 0
XCOM_IDS = [8, 9, 10, 11, 12, 13, 14]                       # 7 soldier-linked units, no tank; ids unchanged
TYPE_BY_ID = {i: "MALE_CIVILIAN" for i in XCOM_IDS}         # the host's re-type by each soldier's gender
C1, C1_TILE, C1_DIR, C1_DEST, C1_TU = 1000000, (27, 11, 0), 2, (28, 11, 0), 54   # min(SEAT1_IDS); TU = its bring-up TU
H1, H1_TILE, H1_DIR, H1_DEST, H1_TU = 1000002, (27, 13, 0), 2, (28, 13, 0), 54   # min(SEAT0_IDS)
N_ALIVE = 5                       # the players' live units at the ending (the xcom_wiped record)
EXPECT_ENDING = {"reason": "aliensDown", "aborted": False, "inExitArea": N_ALIVE, "verdicts": [(0, "win"), (1, "win")],
             "tally": {"liveAliens": 0, "liveSoldiers": N_ALIVE, "inExit": 0}}
OPT = "alienBleeding"
STEP_S = 30                       # each staging / order / ending step's bound (measured: <= 6.9 s)
BOOT_S = 60                       # each briefing wait and the stable settle (measured: <= 1.6 s)
OPTION_S = 10                     # each swapped_start-bleed phase (measured: 0.1 s)
DENY_S = 15                       # client_orders-other's deny (measured: 0.06 s)
N_EQUAL = "[coop-handshake] battle_ready saveBlob EQUAL"
N_MISMATCH = "[coop-handshake] battle_ready saveBlob MISMATCH"
N_REFUSED = "refused: unsupported"          # the client's battle_offer refusal
N_REFUSE_RX = "battle_refuse received"      # the host's unwind on it
N_SPLIT = "PvE2 split:"                     # the host's split line
N_OPENING = "PvE2 opening"           # the host's opening line (the settle passes either way)
ROWS = (("swapped_start",
         ("swapped_start-accept", "swapped_start-mode", "swapped_start-auth", "swapped_start-factions",
          "swapped_start-seats", "swapped_start-ai", "swapped_start-reskin", "swapped_start-bleed",
                "swapped_start-common")),
        ("client_orders", ("client_orders-own", "client_orders-other", "client_orders-common")),
        ("host_ui_walk", ("host_ui_walk-sel", "host_ui_walk-walk", "host_ui_walk-common")),
        ("xcom_wiped",
         ("xcom_wiped-kill", "xcom_wiped-host", "xcom_wiped-client", "xcom_wiped-debrief", "xcom_wiped-common")))


def grep(gc, needle):
    return [line for line in log_lines(gc) if needle in line]


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


def option(gc):
    return (gc.cmd({"cmd": "option_values", "ids": [OPT]}).get("values") or {}).get(OPT)


def miss(tag, err, machines):
    capture(tag, err, machines)
    raise Miss(tag)


# ===================== the gm4 bring-up (steps 1-9) =====================


def bleed_sequence(host, client):
    """Step 6's option sequence (the swapped_start-bleed cell): the host submits alienBleeding false / true / false
    through the synced_option_request test command; each phase waits (<= OPTION_S) for both machines' option_values,
    then reads every unit's woundable on both."""
    out = {"start": [option(host), option(client)], "phases": []}
    try:
        for val in (False, True, False):
            t = time.time()
            r = host.cmd({"cmd": "synced_option_request", "id": OPT, "value": val})
            ok, secs = wait_until(lambda: option(host) is val and option(client) is val, OPTION_S, 0.1)
            uh, uc = units(host), units(client)
            out["phases"].append({"value": val, "resp": r, "reached": ok, "secs": secs, "wall": round(time.time() - t, 2),
                                  "options": [option(host), option(client)],
                                  "xcom": {i: [(uh.get(i) or {}).get("woundable"), (uc.get(i) or {}).get("woundable")]
                                           for i in XCOM_IDS},
                                  "alien": {i: [(uh.get(i) or {}).get("woundable"), (uc.get(i) or {}).get("woundable")]
                                            for i in ALIEN_IDS}})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return out


def settle(host, client):
    """Step 8's stable settle: bounded BOOT_S, every 0.25 s close any NextTurnState on either machine; done when,
    on two polls 1.0 s apart, side 0 on both, both tops BattlescapeState, the host's pendingStates 0 and not isBusy, and
    (the host's opening line count is 0 or turn is 2)."""
    t, hits, last, closes = time.time(), [], None, []
    while time.time() - t < BOOT_S:
        for gc in (host, client):
            if top(gc) == "NextTurnState":
                closes.append((gc.name, round(time.time() - t, 2), gc.cmd({"cmd": "close_nextturn"}).get("handled")))
        hb, cb = battle_state(host), battle_state(client)
        oc = log_count(host, N_OPENING)
        last = {"side": [hb.get("side"), cb.get("side")], "turn": [hb.get("turn"), cb.get("turn")], "opening": oc,
                "tops": [top(host), top(client)], "pending": hb.get("pendingStates"), "busy": hb.get("isBusy")}
        if (last["side"] == [0, 0] and last["tops"] == ["BattlescapeState", "BattlescapeState"] and last["pending"] == 0
                and not last["busy"] and (oc == 0 or hb.get("turn") == 2)):
            hits.append(round(time.time() - t, 2))
            if len(hits) >= 2 and hits[-1] - hits[0] >= 1.0:
                return {"settleS": hits[-1], "turn": last["turn"], "opening": oc, "closes": closes}
            time.sleep(1.0)
            continue
        hits = []
        time.sleep(0.25)
    miss("boot", f"step 8: the stable settle not reached in {BOOT_S} s: {last}", (host, client))


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
    if not ok:
        miss("boot", f"step 3: both lobby rows Alien not shown in {secs} s (host {PF._lobby(host).get('playerTeams')}, "
                  f"client {PF._lobby(client).get('playerTeams')})", m)
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
    boot["table"] = {"host": units(host), "client": units(client)}   # the unit snapshot, Turn 1 screens up
    boot["bleed"] = bleed_sequence(host, client)                       # the option sequence
    boot["pinned"] = guarded("boot", lambda: session.pin_ai_neutral(host, client, tag="pve2"), m)   # step 7
    guarded("boot", lambda: reactions_zero(host, client), m)
    # step 8: the client's Turn 1 close first
    guarded("boot", lambda: session.dismiss_battle_start_overlays(client), m)
    guarded("boot", lambda: session.dismiss_battle_start_overlays(host), m)
    boot["settle"] = settle(host, client)
    return boot, session._crash_log_snapshot()   # step 9


# ===================== the rows =====================


def row_swapped_start(host, client, boot, crash0):
    hb, cb = bview(host), bview(client)
    th, tc = boot["table"]["host"], boot["table"]["client"]
    ha, ca = hb.get("authority") or {}, cb.get("authority") or {}

    def f(t, i, *keys):
        return tuple((t.get(i) or {}).get(k) for k in keys)

    eq_n, mm_n = log_count(host, N_EQUAL), log_count(host, N_MISMATCH)
    ref, tops = [log_count(host, N_REFUSE_RX), log_count(client, N_REFUSED)], [top(host), top(client)]
    fo = ("faction", "originalFaction")
    bad_f = {i: [f(th, i, *fo), f(tc, i, *fo)] for i in ALIEN_IDS if f(th, i, *fo) != (0, 0) or f(tc, i, *fo) != (0, 0)}
    bad_f.update({i: [f(th, i, *fo), f(tc, i, *fo)] for i in XCOM_IDS
                  if f(th, i, *fo) != (1, 1) or f(tc, i, *fo) != (1, 1)})
    trip = ("faction", "originalFaction", "coop")
    diff = {i: [f(th, i, *trip), f(tc, i, *trip)] for i in sorted(set(th) | set(tc)) if f(th, i, *trip) != f(tc, i, *trip)}
    want_seat = {**{i: 1 for i in SEAT1_IDS}, **{i: 0 for i in SEAT0_IDS}, **{i: -1 for i in XCOM_IDS}}
    bad_s = {i: [f(th, i, "coop")[0], f(tc, i, "coop")[0]] for i, s in want_seat.items()
             if f(th, i, "coop")[0] != s or f(tc, i, "coop")[0] != s}
    bad_ai = {i: [f(th, i, "hasAI")[0], f(tc, i, "hasAI")[0]] for i in ALIEN_IDS
              if f(th, i, "hasAI")[0] is not False or f(tc, i, "hasAI")[0] is not False}
    bad_ai.update({i: ["-", f(tc, i, "hasAI")[0]] for i in XCOM_IDS if f(tc, i, "hasAI")[0] is not False})
    rk = ("type", "name", "isPlayerSoldier", "soldierId")
    bad_r = {i: [f(th, i, *rk), f(tc, i, *rk)] for i in XCOM_IDS
             if any(f(t, i, *rk) != (TYPE_BY_ID[i], "", True, i) for t in (th, tc))}
    bl = boot["bleed"]
    bad_b = [(p["value"], p["reached"], p["secs"], p["options"], {i: v for i, v in p["xcom"].items() if v != [p["value"]] * 2})
             for p in bl["phases"] if not p["reached"] or any(v != [p["value"]] * 2 for v in p["xcom"].values())]
    bleed_ok = (not bl.get("error") and [p["value"] for p in bl["phases"]] == [False, True, False] and not bad_b)
    cells = {
        "swapped_start-accept": (
            eq_n == 1 and mm_n == 0 and ref == [0, 0] and tops == ["BattlescapeState", "BattlescapeState"],
            f"host log '{N_EQUAL}' {eq_n} (want 1), MISMATCH {mm_n} (want 0); host '{N_REFUSE_RX}' / client "
            f"'{N_REFUSED}' {ref} (want [0, 0]); tops host/client {tops} after the settle (want BattlescapeState)"),
        "swapped_start-mode": (
            boot["lobbyGamemode"] == hb["coopGamemode"] == cb["coopGamemode"] == GAMEMODE_PVE2
            and hb["mapFingerprint"] == cb["mapFingerprint"] == MAP_FP,
            f"lobby gamemode {boot['lobbyGamemode']} (after {boot['gm2']}), coopGamemode host/client "
            f"{hb['coopGamemode']}/{cb['coopGamemode']} (want 4), mapFingerprint {hb['mapFingerprint']}/"
            f"{cb['mapFingerprint']} (want {MAP_FP})"),
        "swapped_start-auth": (
            (ha.get("localSeat"), ha.get("hostSim"), ca.get("localSeat"), ca.get("hostSim")) == (0, True, 1, False),
            f"authority host {ha} client {ca} (want localSeat 0 hostSim true / 1 false)"),
        "swapped_start-factions": (
            not bad_f and not diff and sorted(th) == sorted(tc) == sorted(ALIEN_IDS + XCOM_IDS),
            f"(faction, originalFaction) off (alien want (0, 0), X-COM (1, 1)) host/client {bad_f} (want "
            f"none); (faction, originalFaction, coop) host vs client differences {diff} (want none); ids "
            f"host {sorted(th)} client {sorted(tc)} (want {sorted(ALIEN_IDS + XCOM_IDS)})"),
        "swapped_start-seats": (
            not bad_s, f"coop off host/client {bad_s} (want SEAT1_IDS 1, SEAT0_IDS 0, XCOM_IDS -1 on both)"),
        "swapped_start-ai": (
            not bad_ai, f"hasAI off host/client {bad_ai} (want every alien false on both, every X-COM unit false "
                        f"on the client)"),
        "swapped_start-reskin": (not bad_r, f"(type, name, isPlayerSoldier, soldierId) off host/client {bad_r} (want "
                                            f"(TYPE_BY_ID[id], '', True, id) on both)"),
        "swapped_start-bleed": (
            bleed_ok, f"alienBleeding phases {[p['value'] for p in bl['phases']]} (want [False, True, False]); "
                      f"phases off (value, reached, secs, option_values host/client, X-COM woundable off) "
                      f"{bad_b} (want each within {OPTION_S} s, every X-COM woundable == the value on both); "
                      f"error {bl.get('error')}"),
        "swapped_start-common": common(host, client, crash0)}
    ev = {"split": grep(host, N_SPLIT), "equip": boot["equip"], "briefingS": boot["briefingS"], "settle": boot["settle"],
          "pinned": boot["pinned"], "xcom": {i: {"host": f(th, i, "name", "type", "_name", "rawName", "hasAI"),
                                                "client": f(tc, i, "name", "type", "_name", "rawName")} for i in XCOM_IDS},
          "bleedStart": bl["start"], "bleed": [{"value": p["value"], "secs": p["secs"], "wall": p["wall"],
                                                "alienWoundable": p["alien"]} for p in bl["phases"]],
          "host": hb, "client": cb}
    return cells, ev


def stage(host, client, uid, tile, d, tu):
    m = (host, client)
    ev = {"tele": guarded("staging", lambda: tele_both(host, client, uid, tile, d).get("to"), m)}
    ev["tu"] = guarded("staging", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid,
                                                                "stat": "tu", "value": tu, "refill": True},
                                                 ("tu",)).get("tu"), m)
    guarded("staging", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return ev


def row_client_orders(host, client, staged, crash0):
    b_ctx, b_sent = es(host, "closedContexts") or [], es(client, "coopIntentsSent") or {}
    ev = {"staged": staged, "resp": session.send_walk(client, C1, C1_DEST)}
    walk_done(host, client, C1, C1_DEST, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    sent, infl, ps = es(client, "coopIntentsSent") or {}, es(client, "inFlight"), [pos(host, C1), pos(client, C1)]
    ctx_ok, ctx_d = ctx_cell(new, "intent", C1)
    ev.update(newCtx=new, sent=[b_sent, sent], inFlight=infl)
    own = (ctx_ok and ps == [C1_DEST, C1_DEST] and sent.get("walk", 0) == b_sent.get("walk", 0) + 1 and infl is None,
           f"{ctx_d}; C1 host/client {ps} (want {C1_DEST} on both; {ev['walkS']} s); client coopIntentsSent {b_sent} -> "
           f"{sent} (want walk +1); inFlight {infl} (want None)")
    d0 = [(units(gc).get(H1) or {}).get("direction") for gc in (host, client)]
    b_ctx = es(host, "closedContexts") or []
    r = client.cmd({"cmd": "battle_intent", "kind": "turn", "actor": H1, "toDir": ((d0[0] or 0) + 2) % 8})
    ok, secs = wait_until(lambda: (es(client, "lastDeny") or {}).get("iseq") == r.get("iseq"), DENY_S, 0.1)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError2"] = str(e)[:200]
    time.sleep(1.0)
    deny, new2 = es(client, "lastDeny") or {}, new_contexts(b_ctx, es(host, "closedContexts"))
    d1 = [(units(gc).get(H1) or {}).get("direction") for gc in (host, client)]
    ev.update(otherResp=r, lastDeny=deny, denyS=secs, newCtx2=new2, dirs=[d0, d1])
    other = (deny.get("iseq") == r.get("iseq") and deny.get("reason") == "not_your_unit" and not new2 and d1 == d0,
             f"client lastDeny {deny} for iseq {r.get('iseq')} ({secs} s; want reason not_your_unit); new host contexts "
             f"{new2} (want none); H1 direction host/client {d0} -> {d1} (want unchanged)")
    return {"client_orders-own": own, "client_orders-other": other,
            "client_orders-common": common(host, client, crash0)}, ev


def tab_cycle(host, uid, cycles=16):
    """ONE TAB, then test_seat_pacing tab_select's bounded TAB pass onto `uid`, recording every unit each TAB lands
    on."""
    landed = []
    for _ in range(cycles + 1):
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.15)
        landed.append(battle_state(host).get("selectedId"))
        if landed[-1] == uid:
            break
    return landed


def row_host_ui_walk(host, client, staged, crash0):
    ev = {"staged": staged, "sel0": battle_state(host).get("selectedId")}
    ev["landed"] = tab_cycle(host, H1)
    ev["sel"] = battle_state(host).get("selectedId")
    bad = [i for i in ev["landed"] if i in SEAT1_IDS or i in XCOM_IDS]
    cells = {"host_ui_walk-sel": (ev["sel"] == H1 and not bad,
                                  f"host selectedId {ev['sel']} (want {H1}); TAB landings {ev['landed']}"
                                  f" (from {ev['sel0']}), on a seat-1 alien or X-COM unit {bad} "
                                  f"(want none)")}
    if ev["sel"] != H1:
        cells.update({n: (False, "staging (the host's TAB never selected H1)")
                      for n in ("host_ui_walk-walk", "host_ui_walk-common")})
        return cells, ev
    b_ctx = es(host, "closedContexts") or []
    real_click_walk(host, H1_DEST)
    walk_done(host, client, H1, H1_DEST, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    ps = [pos(host, H1), pos(client, H1)]
    ctx_ok, ctx_d = ctx_cell(new, "host", H1)
    ev["newCtx"] = new
    cells["host_ui_walk-walk"] = (ctx_ok and ps == [H1_DEST, H1_DEST],
                        f"{ctx_d}; H1 host/client {ps} (want {H1_DEST} on both; {ev['walkS']} s)")
    cells["host_ui_walk-common"] = common(host, client, crash0)
    return cells, ev


def row_xcom_wiped(host, client, crash0):
    """The ending, in test_battle_end_rules turn_limit's two-press shape: records at 0 and the hash taken; host
    kill_unit_real {faction 1}; the kill chain; the client's END TURN; the host shows END TURN 1/2; the host's END
    TURN; the host's NextTurnState closed by dismiss_popup; both DebriefingStates."""
    m, ev, ends = (host, client), {}, []
    pre = {gc.name: {k: (es(gc, "battleEnd") or {}).get(k) for k in ("emitted", "applied")} for gc in m}
    hashed = hash_now(host, client)
    kill = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_HOSTILE})
    chain, ev["chainS"] = wait_until(lambda: host_chain_done(host, XCOM_IDS), STEP_S, 0.1)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    ev.update(pre=pre, hashBefore=hashed, kill=kill)
    pre_ok = all(v == {"emitted": 0, "applied": 0} for v in pre.values())
    kill_cell = (kill.get("ok") is True and sorted(kill.get("killed") or []) == XCOM_IDS and chain and pre_ok,
                 f"killed {kill.get('killed')} (want {XCOM_IDS}); chain done {chain} in {ev['chainS']} s (bound {STEP_S});"
                 f" pre-ending records {pre} (want emitted 0 / applied 0 on both)")
    ev["pressClient"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", STEP_S, 0.1)
    ev["endTurn12"] = [ok, secs, battle_state(host).get("coopEndTurnText")]
    if not ok:
        ends.append(f"host END TURN text {ev['endTurn12'][2]!r} {secs} s after the client's press (want 'END TURN 1/2')")
    ev["pressHost"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, secs = wait_until(lambda: host_next_turn_up(host), STEP_S, 0.1)
    hbs = battle_state(host)
    ev["nextTurn"] = {"up": ok, "s": secs, "side": hbs.get("side"), "turn": hbs.get("turn")}
    if not ok:
        ends.append(f"host NextTurnState not up {secs} s after its END TURN")
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
    return {"xcom_wiped-kill": kill_cell,
            "xcom_wiped-host": (hrec.get("emitted") == 1 and isinstance(hv["seq"], int) and hv["seq"] > 0
                                and {k: hv[k] for k in want} == want,
                                f"host battleEnd emitted {hrec.get('emitted')} (want 1) {hv} "
                                f"(want seq > 0 and {want})"),
            "xcom_wiped-client": (crec.get("applied") == 1 and cv == hv,
                                  f"client battleEnd applied {crec.get('applied')} (want 1) {cv} (want the host's)"),
            "xcom_wiped-debrief": (not ends,
                                   f"{ends or 'both tops DebriefingState, the client display-only, debrief_state '}"
                                   f"{'' if ends else 'titles and rows equal, no client save'}"),
            "xcom_wiped-common": common(host, client, crash0, hashed)}, ev


def run_boot():
    host = GameClient("host", None, make_user_dir("pve2_host"))
    client = GameClient("client", None, make_user_dir("pve2_client"))
    try:
        try:
            boot, crash0 = bring_up(host, client)
        except Miss:
            return fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        rows = dict(ROWS)
        fails = run_row("swapped_start", rows["swapped_start"], lambda: row_swapped_start(host, client, boot, crash0))
        try:
            staged = stage(host, client, C1, C1_TILE, C1_DIR, C1_TU)
        except Miss:
            staged = None
        fails += (run_row("client_orders", rows["client_orders"],
                          lambda: row_client_orders(host, client, staged, crash0)) if staged
                  else fail_all((("client_orders", rows["client_orders"]),), "staging (see the CAPTURE staging line)"))
        try:
            staged = stage(host, client, H1, H1_TILE, H1_DIR, H1_TU)
        except Miss:
            staged = None
        fails += (run_row("host_ui_walk", rows["host_ui_walk"],
                          lambda: row_host_ui_walk(host, client, staged, crash0)) if staged
                  else fail_all((("host_ui_walk", rows["host_ui_walk"]),), "staging (see the CAPTURE staging line)"))
        fails += run_row("xcom_wiped", rows["xcom_wiped"], lambda: row_xcom_wiped(host, client, crash0))
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_pve2: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
