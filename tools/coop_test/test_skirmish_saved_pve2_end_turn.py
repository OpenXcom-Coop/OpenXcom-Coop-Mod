"""R5-U8 S-D rows SD1, SD2: a saved PvE2 (gamemode 4) co-op Custom Battle, loaded from the menu, hosted from the battle's pause
menu and continued with CONTINUE BATTLE, comes back on the players' side of the same turn with every unit's record and every
alien's built values intact, and both players' END TURN then cross the X-COM AI side (owner D233 (a); QU8-5 (a): main #181's
test of this name, re-pointed in place on the rewrite's probes; QU8B-5 (a); Q283-5 (a) / QSD-1 (a): MG-B's row CB2,
test_skirmish_saved_pve2_continue.py, owns the resume's arrival, whose reads are boot preconditions or EVIDENCE here).

Spec: docs repo rewrite/prompts/r5u8_sd_merge_main.md (stage S-D, section (f); rulings QSD-1 .. QSD-6 (a)). Constants:
rewrite/r5u8-task0/sd/CONSTANTS.md (TASK 0 boot pairs Da, Db at 0b5cdefb6). Lobby key 48864.

Boot D1 (dirs r5u8_d_host / r5u8_d_client): R5-U8's gm4 bring-up (test_pve2 / test_pve2_turns): the host sets
SEED_ROSTER, the client on Alien (gamemode 2), the host's own row on Alien (gamemode 4); STR_MEDIUM_SCOUT on map seed SEED_MAP;
both briefings and both pre-battle equip screens; pin_ai_neutral and every live unit's reactions 0; both Turn 1 screens closed
(client first) and the stable settle on side 0 of turn SAVE_TURN (the opening ran once); C1 staged; the record P read on both
machines; every bucket EQUAL; the host saves, then the host exits, then the client.
Boot D2 (the host reuses boot D1's dir, never re-made: make_user_dir would delete the save; a clean client r5u8_d_client2):
the host's load_save_menu, open_pause_coop, host_menu_host; the client joins; CONTINUE BATTLE; both phase Active and both tops
BattlescapeState, no dialog 62 / 68, held 2 s (MG-B's arrival: a miss is CAPTURE D2).
  SD1  SD1-record  every unit's (originalFaction, type, direction) host == client == P
       SD1-built   every alien's darkVision and armorMax host == client == P
       SD1-hold    the resumed host's split line 0; side / turn unchanged on both for HOLD_S with no press
       SD1-order   the client's walk for its alien C1 runs at once (one intent context, no deny, C1 on C1_DEST on both)
       SD1-common
  SD2  SD2-cycle   client END TURN, host "END TURN 1/2", host END TURN, each machine closes its own NextTurnState:
                   side 0 of turn SAVE_TURN + 1 on both, the host's ev kinds = T4_KINDS
       SD2-once    the host's opening line count stays 0 across the cycle
       SD2-common
Common cell: every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.

One EVIDENCE line per row, one PASS/FAIL line per cell, the row verdict; every row runs after a failure. A boot step past its
bound prints ONE CAPTURE D1 / CAPTURE D2 line and fails every cell "boot". run in the foreground to completion.
ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_skirmish_saved_pve2_end_turn.py
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
import test_skirmish_flow as SK  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_pvp_gm3 import (Miss, stack, top, log_lines, log_count, bview, pos, es, tele_both, reactions_zero,  # noqa: E402
                             hash_now, common, ctx_cell, run_row, fail_all, shut)
from test_pve2_turns import side_turn, drive_to_side0, cut_kinds, walk_done, T4_KINDS  # noqa: E402

KEY = "48864"
HOST_DIR, CLIENT_DIR, CLIENT2_DIR = "r5u8_d_host", "r5u8_d_client", "r5u8_d_client2"
SAVE = "r5u8_d_pve2.sav"
SEED_ROSTER, SEED_MAP, MISSION = 1, 1, "STR_MEDIUM_SCOUT"   # R5-U8's gm4 pins (TASK 0 Da = Db)
GAMEMODE_PVE2 = 4
SAVE_TURN = 2                     # the first players' side after the opening (QSD-6 (a); Da = Db)
C1, C1_TILE, C1_DIR, C1_DEST, C1_TU = 1000000, (27, 11, 0), 2, (28, 11, 0), 54   # min(SEAT1_IDS); S-A's C1 staging
BOOT_S, LOAD_S, LOBBY_S, RESUME_S = 60, 60, 60, 120   # briefing <= 1.3 s, load 0.1 s, join 2.1 s, arrival 1.8 s
STEP_S, SIDE_S, HOLD_S, HELD_S = 30, 60, 5, 2.0       # END TURN 1/2 0.05 s, walk 0.15 s, cycle 2.6 s
DLG_WAIT_PLAYERS, DLG_RESUME_HOLD = 62, 68
N_SPLIT = "PvE2 split:"                     # the host's split line (generation pass)
N_OPENING = "PvE2 opening"           # the host's opening line
N_EQUAL = "[coop-handshake] battle_ready saveBlob EQUAL"
N_REFUSE_RX = "battle_refuse received"
FIELDS = ("faction", "originalFaction", "coop", "type", "isOut", "x", "y", "z", "direction", "darkVision", "armorMax",
          "hasAI", "tu")
RECORD, BUILT, CB2 = ("originalFaction", "type", "direction"), ("darkVision", "armorMax"), ("coop", "faction", "isOut", "x",
                                                                                           "y", "z")
ROWS = (("SD1", ("SD1-record", "SD1-built", "SD1-hold", "SD1-order", "SD1-common")),
        ("SD2", ("SD2-cycle", "SD2-once", "SD2-common")))


def dialog(gc):
    d = gc.cmd({"cmd": "coop_dialog_info"})
    return d.get("code") if d.get("present") else None


def table(gc):
    return {str(u["id"]): {k: u.get(k) for k in FIELDS} for u in battle_state(gc).get("units", [])}


def pick(t, uid, keys):
    return [(t.get(uid) or {}).get(k) for k in keys]


def differ(tables, keys, ids):
    """{id: [host, client, P]} for every id whose `keys` are not equal in all three tables."""
    return {i: [pick(t, i, keys) for t in tables] for i in ids
            if not pick(tables[0], i, keys) == pick(tables[1], i, keys) == pick(tables[2], i, keys)}


def capture(tag, err, machines):
    """ONE CAPTURE line: each machine's stack, battle view, get_coop, coop_dialog_info, event_state picks, last 40 log lines."""
    cap = {}
    for gc in machines:
        d = {}
        for k, fn in (("stack", stack), ("battle", bview), ("coop", lambda g: g.cmd({"cmd": "get_coop"})),
                      ("dialog", lambda g: g.cmd({"cmd": "coop_dialog_info"})),
                      ("es", lambda g: {k2: es(g, k2) for k2 in ("phase", "turnMode", "desyncSeen", "lastSeqEmitted")}),
                      ("logTail", lambda g: log_lines(g)[-40:])):
            try:
                d[k] = fn(gc)
            except Exception as e:
                d[k] = f"probe failed: {type(e).__name__}: {e}"
        cap[gc.name] = d
    print(f"CAPTURE {tag}: missed {err}; {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def miss(tag, err, machines):
    capture(tag, err, machines)
    raise Miss(tag)


def guarded(tag, fn, machines):
    try:
        return fn()
    except Miss:
        raise
    except Exception as e:
        miss(tag, f"{type(e).__name__}: {str(e)[:600]}", machines)


def settle(host, client):
    """PV's stable settle: every 0.25 s close any NextTurnState on either machine (each its own); done when, on two polls
    1.0 s apart, side 0 on both, both tops BattlescapeState, the host's pendingStates 0 and not isBusy, and turn SAVE_TURN."""
    t, hits, last, closes = time.time(), [], None, []
    while time.time() - t < BOOT_S:
        for gc in (host, client):
            if top(gc) == "NextTurnState":
                closes.append((gc.name, round(time.time() - t, 2), gc.cmd({"cmd": "close_nextturn"}).get("handled")))
        last = side_turn(host, client)
        if (last["side"] == [0, 0] and last["turn"] == [SAVE_TURN] * 2 and last["tops"] == ["BattlescapeState"] * 2
                and last["pending"] == 0 and not last["busy"]):
            hits.append(round(time.time() - t, 2))
            if hits[-1] - hits[0] >= 1.0:
                return {"settleS": hits[-1], "closes": closes, "opening": log_count(host, N_OPENING)}
            time.sleep(1.0)
            continue
        hits = []
        time.sleep(0.25)
    miss("D1", f"step 8: the stable settle (side 0, turn {SAVE_TURN}) not reached in {BOOT_S} s: {last}", (host, client))


def boot_d1(host, client):
    """Steps (1)-(11); returns the record P (host and client tables, top, turn mode, the save greps)."""
    m, boot = (host, client), {}
    guarded("D1", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("D1", lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    boot["gm2"] = guarded("D1", lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client"), m)[0]
    gm = guarded("D1", lambda: host.ok({"cmd": "lobby_set_team", "row": PF.row_for(host, "HostPlayer"),
                                        "team": "Alien"}), m).get("gamemode")
    ok, secs = wait_until(lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                          and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], 10, 0.25)
    if not ok or gm != GAMEMODE_PVE2:
        miss("D1", f"step 3: gamemode {gm} (want 4); both lobby rows Alien {ok} in {secs} s", m)
    guarded("D1", lambda: host.ok({"cmd": "lobby_action"}), m)
    guarded("D1", lambda: host.wait_for("host at battle settings",
                                        lambda: (not session.has_state(host, "LobbyMenu")) or None), m)
    if top(host) != "NewBattleState":
        miss("D1", f"step 4: host stack {stack(host)} (want NewBattleState on top)", m)
    guarded("D1", lambda: host.ok({"cmd": "newbattle_mission", "type": MISSION}), m)
    guarded("D1", lambda: host.ok({"cmd": "set_seed", "seed": SEED_MAP}), m)
    guarded("D1", lambda: host.ok({"cmd": "newbattle_ok"}), m)
    for gc in m:   # step 5: a refusal ends the wait at once
        ok, secs = wait_until(lambda gc=gc: session.has_state(gc, "BriefingState") or log_count(host, N_REFUSE_RX) > 0,
                              BOOT_S, 0.1)
        if not ok or log_count(host, N_REFUSE_RX) > 0:
            miss("D1", f"step 5: {gc.name} BriefingState {ok} after {secs} s; host '{N_REFUSE_RX}' "
                       f"{log_count(host, N_REFUSE_RX)}", m)
    guarded("D1", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)   # step 6
    guarded("D1", lambda: session.dismiss_client_briefing(client), m)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            session.equip_both_ready(host, client)
    except Exception as e:
        print(buf.getvalue(), end="", flush=True)
        miss("D1", f"step 6: equip_both_ready: {type(e).__name__}: {str(e)[:500]}", m)
    boot["equal"] = log_count(host, N_EQUAL)
    boot["pinned"] = guarded("D1", lambda: session.pin_ai_neutral(host, client, tag="r5u8d"), m)   # step 7
    guarded("D1", lambda: reactions_zero(host, client), m)
    guarded("D1", lambda: session.dismiss_battle_start_overlays(client), m)   # step 8: the client's Turn 1 close first
    guarded("D1", lambda: session.dismiss_battle_start_overlays(host), m)
    boot["settle"] = settle(host, client)
    if boot["settle"]["opening"] != 1:
        miss("D1", f"step 8: host '{N_OPENING}' lines {boot['settle']['opening']} at the settle (want 1)", m)
    boot["c1From"] = pos(host, C1)
    guarded("D1", lambda: tele_both(host, client, C1, C1_TILE, C1_DIR), m)   # step 9
    guarded("D1", lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": C1, "stat": "tu",
                                              "value": C1_TU, "refill": True}, ("tu",)), m)
    guarded("D1", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    P = {"host": table(host), "client": table(client), "top": [bview(host), bview(client)],
         "turnMode": [es(host, "turnMode"), es(client, "turnMode")], "split": log_count(host, N_SPLIT)}   # step 10
    P["diff"] = {i: [P["host"].get(i), P["client"].get(i)] for i in set(P["host"]) | set(P["client"])
                 if P["host"].get(i) != P["client"].get(i)}
    hashed = hash_now(host, client)
    if hashed != "all buckets EQUAL":
        miss("D1", f"step 10: hash before the save: {hashed}", m)
    guarded("D1", lambda: host.ok({"cmd": "save_game", "file": SAVE}), m)   # step 11
    path = os.path.join(host.user_dir, "xcom1", SAVE)
    if not wait_until(lambda: os.path.exists(path), 10, 0.2)[0]:
        miss("D1", f"step 11: save_game wrote no {path} in 10 s", m)
    time.sleep(1.0)
    with open(path, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    P["greps"] = {k: txt.count(k) for k in ("coop_gamemode: 4", "coopDark:", "coopMaxArmor:", "genUnitType: MALE_CIVILIAN",
                                            "genUnitType: FEMALE_CIVILIAN", "coopTurnMode: parallel")}
    P["boot"] = boot
    return P


def boot_d2(host, client):
    """Steps (R1)-(R7) on the resume pair; returns the arrival evidence and the crash baseline."""
    m, ev = (host, client), {}
    guarded("D2", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("D2", lambda: host.ok({"cmd": "load_save_menu", "file": SAVE}), m)   # R1
    ok, secs = wait_until(lambda: battle_state(host).get("inBattle") and top(host) == "BattlescapeState", LOAD_S, 0.25)
    locked = host.cmd({"cmd": "get_coop"}).get("sessionLocked")
    if not ok or locked:
        miss("D2", f"R1: the loaded battle on top {ok} in {secs} s; sessionLocked {locked} (want False)", m)
    guarded("D2", lambda: host.ok({"cmd": "open_pause_coop"}), m)   # R2
    ok, secs = wait_until(lambda: session.has_state(host, "HostMenu"), LOBBY_S, 0.25)
    pend = host.cmd({"cmd": "get_coop"}).get("customBattleResumePending")
    if not ok or pend is not True:
        miss("D2", f"R2: HostMenu {ok} in {secs} s; customBattleResumePending {pend} (want True)", m)
    guarded("D2", lambda: host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SavedPVE2", "port": KEY,
                                   "player": "HostPlayer"}), m)   # R3
    if not wait_until(lambda: session.has_state(host, "LobbyMenu"), LOBBY_S, 0.25)[0]:
        miss("D2", f"R3: host LobbyMenu not shown in {LOBBY_S} s", m)

    def join():   # R4
        SK.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
        for gc in m:
            gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=LOBBY_S)
            gc.ok({"cmd": "profile_ok"})
    guarded("D2", join, m)
    ok, secs = wait_until(lambda: (lambda ls: ls.get("buttonVisible") and ls.get("buttonText") == "CONTINUE BATTLE")(
        host.cmd({"cmd": "lobby_state"})), LOBBY_S, 0.25)
    ev["button"] = host.cmd({"cmd": "lobby_state"}).get("buttonText")
    if not ok:
        miss("D2", f"R4: CONTINUE BATTLE not offered in {secs} s (button {ev['button']!r})", m)
    guarded("D2", lambda: host.ok({"cmd": "lobby_action"}), m)   # R5
    t, first, trace = time.time(), None, []
    while time.time() - t < RESUME_S:   # R6: held HELD_S continuously
        row = [[es(host, "phase"), es(client, "phase")], [top(host), top(client)], [dialog(host), dialog(client)]]
        if not trace or trace[-1][1:] != row:
            trace.append([round(time.time() - t, 2)] + row)
        if (row[0] == ["Active", "Active"] and row[1] == ["BattlescapeState"] * 2 and row[2][0] != DLG_WAIT_PLAYERS
                and row[2][1] != DLG_RESUME_HOLD):
            first = time.time() if first is None else first
            if time.time() - first >= HELD_S:
                break
        else:
            first = None
        time.sleep(0.25)
    ev["arrival"] = trace
    if first is None or time.time() - first < HELD_S:
        miss("D2", f"R6: both Active, both tops BattlescapeState, no dialog {DLG_WAIT_PLAYERS} / {DLG_RESUME_HOLD} not held "
                   f"{HELD_S} s within {RESUME_S} s: {trace}", m)
    crash0 = session._crash_log_snapshot()   # R7
    ev.update(dialogs=[dialog(host), dialog(client)], clientStack=stack(client),
              turnMode=[[es(g, "turnMode"), es(g, "optionTurnMode")] for g in m],
              coopSession=client.cmd({"cmd": "get_coop"}).get("coopSession"))
    return ev, crash0


def row_sd1(host, client, P, arrival, crash0):
    th, tc, ph = table(host), table(client), P["host"]
    ids = sorted(set(th) | set(tc) | set(ph))
    aliens = sorted(i for i, u in ph.items() if u["faction"] == 0)
    rec, built = differ((th, tc, ph), RECORD, ids), differ((th, tc, ph), BUILT, aliens)
    split = log_count(host, N_SPLIT)
    ev = {"P": {"top": P["top"], "turnMode": P["turnMode"], "diff": P["diff"], "greps": P["greps"], "boot": P["boot"],
                "split": P["split"]}, "arrival": arrival,
          "resumed": [bview(host), bview(client)], "cb2Diff": differ((th, tc, ph), CB2, ids),
          "hasAI": {i: [pick(th, i, ("hasAI",))[0], pick(tc, i, ("hasAI",))[0]] for i in ids
                    if (ph.get(i) or {}).get("faction") == 1},
          "logs": {"split": split, "opening": log_count(host, N_OPENING), "equal": log_count(host, N_EQUAL)}}
    want = [P["top"][0].get("side"), P["top"][0].get("turn")]
    polls, t = [], time.time()
    while time.time() - t < HOLD_S:
        polls.append([[battle_state(g).get("side"), battle_state(g).get("turn")] for g in (host, client)])
        time.sleep(0.25)
    off = [p for p in polls if p != [want, want]]
    b_ctx = es(host, "closedContexts") or []
    r = session.send_walk(client, C1, C1_DEST)
    walk_done(host, client, C1, C1_DEST, ev)
    new = new_contexts(b_ctx, es(host, "closedContexts"))
    deny, ps = es(client, "lastDeny") or {}, [pos(host, C1), pos(client, C1)]
    cok, cdetail = ctx_cell(new, "intent", C1)
    ev.update(walk=r, newCtx=new, lastDeny=deny, polls=len(polls))
    return {"SD1-record": (not rec, f"(originalFaction, type, direction) differing host/client/P {rec} (want none, "
                                    f"{len(ids)} units)"),
            "SD1-built": (bool(aliens) and not built, f"aliens {aliens}: (darkVision, armorMax) differing host/client/P "
                                                      f"{built} (want none)"),
            "SD1-hold": (split == 0 and bool(polls) and not off,
                         f"host '{N_SPLIT}' lines after the resume {split} (want 0); {len(polls)} polls over {HOLD_S} s "
                         f"with no press, off side/turn {want} on either machine {off[:3]} (want none)"),
            "SD1-order": (cok and deny.get("iseq") != r.get("iseq") and ps == [C1_DEST, C1_DEST],
                          f"{cdetail}; client lastDeny {deny} for the walk's iseq {r.get('iseq')} (want none); C1 "
                          f"host/client {ps} (want {C1_DEST} on both; {ev.get('walkS')} s)"),
            "SD1-common": common(host, client, crash0)}, ev


def row_sd2(host, client, crash0, crash_start):
    ev, steps = {}, []
    mark, oc0 = es(host, "lastSeqEmitted"), log_count(host, N_OPENING)
    ev["pressClient"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    ok, ev["endTurn12S"] = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", STEP_S, 0.1)
    if not ok:
        steps.append(f"host END TURN text {battle_state(host).get('coopEndTurnText')!r} {ev['endTurn12S']} s after the "
                     f"client's press (want 'END TURN 1/2')")
    ev["pressHost"] = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    want = SAVE_TURN + 1
    done, secs, closes, last = drive_to_side0(host, client, want, SIDE_S)
    kinds = [e["kind"] for e in cut_kinds(evs_since(host, mark))]
    oc1 = log_count(host, N_OPENING)
    ev.update(mark=mark, closes=closes, kinds=kinds, opening=[oc0, oc1],
              clientSaves=session.save_files(client.user_dir),
              crashSinceStart=sorted(session._crash_log_snapshot() - crash_start))
    return {"SD2-cycle": (done and last["side"] == [0, 0] and last["turn"] == [want, want]
                          and last["tops"] == ["BattlescapeState"] * 2 and kinds == T4_KINDS and not steps,
                          f"side {last['side']} turn {last['turn']} tops {last['tops']} (want 0 / {want} / BattlescapeState "
                          f"on both; settled {done} in {secs} s, bound {SIDE_S}); host ev kinds {kinds} (want {T4_KINDS}); "
                          f"{steps or 'END TURN 1/2 shown'}"),
            "SD2-once": (oc0 == oc1 == 0, f"host '{N_OPENING}' lines {oc0} -> {oc1} across the cycle (want 0 -> 0)"),
            "SD2-common": common(host, client, crash0)}, ev


def main():
    t0 = time.time()
    crash_start = session._crash_log_snapshot()
    rows = dict(ROWS)
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    P = arrival = None
    try:
        P = boot_d1(host, client)
    except Miss:
        pass
    except Exception as e:
        capture("D1", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
    finally:
        shut(host)     # the host first: it never takes a partner drop
        shut(client)
    if P is None:
        fails = fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE D1 line)")
    else:
        host = GameClient("host", None, host.user_dir)   # boot D1's dir, NOT re-made
        client = GameClient("client", None, make_user_dir(CLIENT2_DIR))
        try:
            try:
                arrival, crash0 = boot_d2(host, client)
            except Miss:
                pass
            except Exception as e:
                capture("D2", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
            if arrival is None:
                fails = fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE D2 line)")
            else:
                fails = run_row("SD1", rows["SD1"], lambda: row_sd1(host, client, P, arrival, crash0))
                fails += run_row("SD2", rows["SD2"], lambda: row_sd2(host, client, crash0, crash_start))
        finally:
            shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_skirmish_saved_pve2_end_turn: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
