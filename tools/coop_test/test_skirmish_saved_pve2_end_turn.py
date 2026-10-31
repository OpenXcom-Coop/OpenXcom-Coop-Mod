"""Rows resume_intact and end_turn_cycle: a saved PvE2 (gamemode 4) co-op Custom Battle, loaded from the menu, hosted
from the battle's pause menu and continued with CONTINUE BATTLE, comes back on the players' side of the same turn with
every unit's record and every alien's built values intact, and both players' END TURN then cross the X-COM AI side.
The file keeps the name of main's test from #181, on the current probes. test_skirmish_saved_pve2_continue.py owns the
resume's arrival, whose reads are boot preconditions or EVIDENCE here. Lobby key 48864.

Boot seed_boot (dirs pve2_end_turn_host / pve2_end_turn_client), in the steps its CAPTURE lines name: the gm4 bring-up
of test_pve2 / test_pve2_turns: the host sets SEED_ROSTER, the client on Alien (gamemode 2), the host's own row on Alien
(gamemode 4) (3: both lobby rows Alien); STR_MEDIUM_SCOUT on map seed SEED_MAP (4); both briefings (5) and both
pre-battle equip screens (6); pin_ai_neutral and every live unit's reactions 0 (7); both Turn 1 screens closed (client
first) and the stable settle on side 0 of turn SAVE_TURN, the opening ran once (8); C1 staged (9); the record P read on
both machines, every bucket EQUAL (10); the host saves (11), then the host exits, then the client.
Boot resume_boot (the host reuses seed_boot's dir, never re-made: make_user_dir would delete the save; a clean client
pve2_end_turn_client2), in the resume steps its CAPTURE lines name: the host's load_save_menu (1), open_pause_coop (2),
host_menu_host (3); the client joins (4); CONTINUE BATTLE (5); both phase Active and both tops BattlescapeState, no
dialog 62 / 68, held 2 s (6: the arrival of test_skirmish_saved_pve2_continue); the crash-folder snapshot (7).
  resume_intact   unit_record_kept    every unit's (originalFaction, type, direction) host == client == P
                  alien_built_kept    every alien's darkVision and armorMax host == client == P
                  resume_holds_still  the resumed host's split line 0; side / turn unchanged on both for HOLD_S with no
                                      press
                  client_walk_runs    the client's walk for its alien C1 runs at once (one intent context, no deny, C1
                                      on C1_DEST on both)
                  resume_common
  end_turn_cycle  turn_cycle_runs     client END TURN, host "END TURN 1/2", host END TURN, each machine closes its own
                                      NextTurnState: side 0 of turn SAVE_TURN + 1 on both, the host's ev kinds =
                                      CYCLE_KINDS
                  opening_not_rerun   the host's opening line count stays 0 across the cycle
                  cycle_common
Common cell: every hash bucket EQUAL, desyncSeen false on both, no new file in the lane crash folder.

One EVIDENCE line per row, one PASS/FAIL line per cell, the row verdict; every row runs after a failure. A boot step
past its bound prints ONE CAPTURE seed_boot / CAPTURE resume_boot line and fails every cell "boot". Run it in the
foreground to completion. There is no skip path; exit 0 only when every cell passes, else 2.

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
from test_pve2_turns import side_turn, drive_to_side0, cut_kinds, walk_done, CYCLE_KINDS  # noqa: E402

KEY = "48864"
HOST_DIR, CLIENT_DIR, CLIENT2_DIR = "pve2_end_turn_host", "pve2_end_turn_client", "pve2_end_turn_client2"
SAVE = "pve2_end_turn.sav"
SEED_ROSTER, SEED_MAP, MISSION = 1, 1, "STR_MEDIUM_SCOUT"   # the gm4 constants of test_pve2_turns
GAMEMODE_PVE2 = 4
SAVE_TURN = 2                     # the first players' side after the opening
# C1 = min(test_pve2.SEAT1_IDS), staged as test_pve2 stages it
C1, C1_TILE, C1_DIR, C1_DEST, C1_TU = 1000000, (27, 11, 0), 2, (28, 11, 0), 54
BOOT_S, LOAD_S, LOBBY_S, RESUME_S = 60, 60, 60, 120   # briefing <= 1.3 s, load 0.1 s, join 2.1 s, arrival 1.8 s
STEP_S, SIDE_S, HOLD_S, HELD_S = 30, 60, 5, 2.0       # END TURN 1/2 0.05 s, walk 0.15 s, cycle 2.6 s
DLG_WAIT_PLAYERS, DLG_RESUME_HOLD = 62, 68
N_SPLIT = "PvE2 split:"                     # the host's split line (generation pass)
N_OPENING = "PvE2 opening"           # the host's opening line
N_EQUAL = "[coop-handshake] battle_ready saveBlob EQUAL"
N_REFUSE_RX = "battle_refuse received"
FIELDS = ("faction", "originalFaction", "coop", "type", "isOut", "x", "y", "z", "direction", "darkVision", "armorMax",
          "hasAI", "tu")
RECORD, BUILT, PLACEMENT = (("originalFaction", "type", "direction"), ("darkVision", "armorMax"),
                            ("coop", "faction", "isOut", "x", "y", "z"))
ROWS = (("resume_intact",
         ("unit_record_kept", "alien_built_kept", "resume_holds_still", "client_walk_runs", "resume_common")),
        ("end_turn_cycle", ("turn_cycle_runs", "opening_not_rerun", "cycle_common")))


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
    """test_pve2's stable settle: every 0.25 s close any NextTurnState on either machine (each its own); done when,
    on two polls 1.0 s apart, side 0 on both, both tops BattlescapeState, the host's pendingStates 0 and not isBusy,
    and turn SAVE_TURN."""
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
    miss("seed_boot", f"step 8: the stable settle (side 0, turn {SAVE_TURN}) not reached in {BOOT_S} s: {last}",
         (host, client))


def boot_seed(host, client):
    """Boot steps 1-11; returns the record P (host and client tables, top, turn mode, the save greps)."""
    m, boot = (host, client), {}
    guarded("seed_boot", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("seed_boot", lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    boot["gm2"] = guarded("seed_boot", lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client"),
                          m)[0]
    gm = guarded("seed_boot", lambda: host.ok({"cmd": "lobby_set_team", "row": PF.row_for(host, "HostPlayer"),
                                               "team": "Alien"}), m).get("gamemode")
    ok, secs = wait_until(lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                          and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], 10, 0.25)
    if not ok or gm != GAMEMODE_PVE2:
        miss("seed_boot", f"step 3: gamemode {gm} (want 4); both lobby rows Alien {ok} in {secs} s", m)
    guarded("seed_boot", lambda: host.ok({"cmd": "lobby_action"}), m)
    guarded("seed_boot", lambda: host.wait_for("host at battle settings",
                                               lambda: (not session.has_state(host, "LobbyMenu")) or None), m)
    if top(host) != "NewBattleState":
        miss("seed_boot", f"step 4: host stack {stack(host)} (want NewBattleState on top)", m)
    guarded("seed_boot", lambda: host.ok({"cmd": "newbattle_mission", "type": MISSION}), m)
    guarded("seed_boot", lambda: host.ok({"cmd": "set_seed", "seed": SEED_MAP}), m)
    guarded("seed_boot", lambda: host.ok({"cmd": "newbattle_ok"}), m)
    for gc in m:   # step 5: a refusal ends the wait at once
        ok, secs = wait_until(lambda gc=gc: session.has_state(gc, "BriefingState") or log_count(host, N_REFUSE_RX) > 0,
                              BOOT_S, 0.1)
        if not ok or log_count(host, N_REFUSE_RX) > 0:
            miss("seed_boot", f"step 5: {gc.name} BriefingState {ok} after {secs} s; host '{N_REFUSE_RX}' "
                              f"{log_count(host, N_REFUSE_RX)}", m)
    guarded("seed_boot", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)   # step 6
    guarded("seed_boot", lambda: session.dismiss_client_briefing(client), m)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            session.equip_both_ready(host, client)
    except Exception as e:
        print(buf.getvalue(), end="", flush=True)
        miss("seed_boot", f"step 6: equip_both_ready: {type(e).__name__}: {str(e)[:500]}", m)
    boot["equal"] = log_count(host, N_EQUAL)
    # step 7
    boot["pinned"] = guarded("seed_boot", lambda: session.pin_ai_neutral(host, client, tag="pve2_end_turn"), m)
    guarded("seed_boot", lambda: reactions_zero(host, client), m)
    # step 8: the client's Turn 1 close first
    guarded("seed_boot", lambda: session.dismiss_battle_start_overlays(client), m)
    guarded("seed_boot", lambda: session.dismiss_battle_start_overlays(host), m)
    boot["settle"] = settle(host, client)
    if boot["settle"]["opening"] != 1:
        miss("seed_boot", f"step 8: host '{N_OPENING}' lines {boot['settle']['opening']} at the settle (want 1)", m)
    boot["c1From"] = pos(host, C1)
    guarded("seed_boot", lambda: tele_both(host, client, C1, C1_TILE, C1_DIR), m)   # step 9
    guarded("seed_boot",
            lambda: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": C1, "stat": "tu",
                                        "value": C1_TU, "refill": True}, ("tu",)), m)
    guarded("seed_boot", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    P = {"host": table(host), "client": table(client), "top": [bview(host), bview(client)],
         "turnMode": [es(host, "turnMode"), es(client, "turnMode")], "split": log_count(host, N_SPLIT)}   # step 10
    P["diff"] = {i: [P["host"].get(i), P["client"].get(i)] for i in set(P["host"]) | set(P["client"])
                 if P["host"].get(i) != P["client"].get(i)}
    hashed = hash_now(host, client)
    if hashed != "all buckets EQUAL":
        miss("seed_boot", f"step 10: hash before the save: {hashed}", m)
    guarded("seed_boot", lambda: host.ok({"cmd": "save_game", "file": SAVE}), m)   # step 11
    path = os.path.join(host.user_dir, "xcom1", SAVE)
    if not wait_until(lambda: os.path.exists(path), 10, 0.2)[0]:
        miss("seed_boot", f"step 11: save_game wrote no {path} in 10 s", m)
    time.sleep(1.0)
    with open(path, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    P["greps"] = {k: txt.count(k) for k in ("coop_gamemode: 4", "coopDark:", "coopMaxArmor:", "genUnitType: MALE_CIVILIAN",
                                            "genUnitType: FEMALE_CIVILIAN", "coopTurnMode: parallel")}
    P["boot"] = boot
    return P


def boot_resume(host, client):
    """Resume steps 1-7 on the resume pair; returns the arrival evidence and the crash baseline."""
    m, ev = (host, client), {}
    guarded("resume_boot", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("resume_boot", lambda: host.ok({"cmd": "load_save_menu", "file": SAVE}), m)   # resume step 1
    ok, secs = wait_until(lambda: battle_state(host).get("inBattle") and top(host) == "BattlescapeState", LOAD_S, 0.25)
    locked = host.cmd({"cmd": "get_coop"}).get("sessionLocked")
    if not ok or locked:
        miss("resume_boot",
             f"resume step 1: the loaded battle on top {ok} in {secs} s; sessionLocked {locked} (want False)", m)
    guarded("resume_boot", lambda: host.ok({"cmd": "open_pause_coop"}), m)   # resume step 2
    ok, secs = wait_until(lambda: session.has_state(host, "HostMenu"), LOBBY_S, 0.25)
    pend = host.cmd({"cmd": "get_coop"}).get("customBattleResumePending")
    if not ok or pend is not True:
        miss("resume_boot", f"resume step 2: HostMenu {ok} in {secs} s; customBattleResumePending {pend} (want True)",
             m)
    guarded("resume_boot",
            lambda: host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SavedPVE2", "port": KEY,
                             "player": "HostPlayer"}), m)   # resume step 3
    if not wait_until(lambda: session.has_state(host, "LobbyMenu"), LOBBY_S, 0.25)[0]:
        miss("resume_boot", f"resume step 3: host LobbyMenu not shown in {LOBBY_S} s", m)

    def join():   # resume step 4
        SK.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
        for gc in m:
            gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=LOBBY_S)
            gc.ok({"cmd": "profile_ok"})
    guarded("resume_boot", join, m)
    ok, secs = wait_until(lambda: (lambda ls: ls.get("buttonVisible") and ls.get("buttonText") == "CONTINUE BATTLE")(
        host.cmd({"cmd": "lobby_state"})), LOBBY_S, 0.25)
    ev["button"] = host.cmd({"cmd": "lobby_state"}).get("buttonText")
    if not ok:
        miss("resume_boot", f"resume step 4: CONTINUE BATTLE not offered in {secs} s (button {ev['button']!r})", m)
    guarded("resume_boot", lambda: host.ok({"cmd": "lobby_action"}), m)   # resume step 5
    t, first, trace = time.time(), None, []
    while time.time() - t < RESUME_S:   # resume step 6: held HELD_S continuously
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
        miss("resume_boot", f"resume step 6: both Active, both tops BattlescapeState, no dialog {DLG_WAIT_PLAYERS} / "
                            f"{DLG_RESUME_HOLD} not held {HELD_S} s within {RESUME_S} s: {trace}", m)
    crash0 = session._crash_log_snapshot()   # resume step 7
    ev.update(dialogs=[dialog(host), dialog(client)], clientStack=stack(client),
              turnMode=[[es(g, "turnMode"), es(g, "optionTurnMode")] for g in m],
              coopSession=client.cmd({"cmd": "get_coop"}).get("coopSession"))
    return ev, crash0


def row_resume_intact(host, client, P, arrival, crash0):
    th, tc, ph = table(host), table(client), P["host"]
    ids = sorted(set(th) | set(tc) | set(ph))
    aliens = sorted(i for i, u in ph.items() if u["faction"] == 0)
    rec, built = differ((th, tc, ph), RECORD, ids), differ((th, tc, ph), BUILT, aliens)
    split = log_count(host, N_SPLIT)
    ev = {"P": {"top": P["top"], "turnMode": P["turnMode"], "diff": P["diff"], "greps": P["greps"], "boot": P["boot"],
                "split": P["split"]}, "arrival": arrival,
          "resumed": [bview(host), bview(client)], "placementDiff": differ((th, tc, ph), PLACEMENT, ids),
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
    return {"unit_record_kept": (not rec,
                                 f"(originalFaction, type, direction) differing host/client/P {rec} (want none, "
                                 f"{len(ids)} units)"),
            "alien_built_kept": (bool(aliens) and not built,
                                 f"aliens {aliens}: (darkVision, armorMax) differing host/client/P "
                                 f"{built} (want none)"),
            "resume_holds_still": (split == 0 and bool(polls) and not off,
                                   f"host '{N_SPLIT}' lines after the resume {split} (want 0); {len(polls)} polls "
                                   f"over {HOLD_S} s with no press, off side/turn {want} on either machine "
                                   f"{off[:3]} (want none)"),
            "client_walk_runs": (cok and deny.get("iseq") != r.get("iseq") and ps == [C1_DEST, C1_DEST],
                                 f"{cdetail}; client lastDeny {deny} for the walk's iseq {r.get('iseq')} "
                                 f"(want none); C1 host/client {ps} (want {C1_DEST} on both; {ev.get('walkS')} s)"),
            "resume_common": common(host, client, crash0)}, ev


def row_end_turn_cycle(host, client, crash0, crash_start):
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
    return {"turn_cycle_runs": (done and last["side"] == [0, 0] and last["turn"] == [want, want]
                                and last["tops"] == ["BattlescapeState"] * 2 and kinds == CYCLE_KINDS and not steps,
                                f"side {last['side']} turn {last['turn']} tops {last['tops']} (want 0 / {want} / "
                                f"BattlescapeState on both; settled {done} in {secs} s, bound {SIDE_S}); host ev "
                                f"kinds {kinds} (want {CYCLE_KINDS}); {steps or 'END TURN 1/2 shown'}"),
            "opening_not_rerun": (oc0 == oc1 == 0,
                                  f"host '{N_OPENING}' lines {oc0} -> {oc1} across the cycle (want 0 -> 0)"),
            "cycle_common": common(host, client, crash0)}, ev


def main():
    t0 = time.time()
    crash_start = session._crash_log_snapshot()
    rows = dict(ROWS)
    host = GameClient("host", None, make_user_dir(HOST_DIR))
    client = GameClient("client", None, make_user_dir(CLIENT_DIR))
    P = arrival = None
    try:
        P = boot_seed(host, client)
    except Miss:
        pass
    except Exception as e:
        capture("seed_boot", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
    finally:
        shut(host)     # the host first: it never takes a partner drop
        shut(client)
    if P is None:
        fails = fail_all(ROWS, "boot (setup failure, see the CAPTURE seed_boot line)")
    else:
        host = GameClient("host", None, host.user_dir)   # the seed boot's dir, NOT re-made
        client = GameClient("client", None, make_user_dir(CLIENT2_DIR))
        try:
            try:
                arrival, crash0 = boot_resume(host, client)
            except Miss:
                pass
            except Exception as e:
                capture("resume_boot", f"{type(e).__name__}: {str(e)[:600]}", (host, client))
            if arrival is None:
                fails = fail_all(ROWS, "boot (setup failure, see the CAPTURE resume_boot line)")
            else:
                fails = run_row("resume_intact", rows["resume_intact"],
                                lambda: row_resume_intact(host, client, P, arrival, crash0))
                fails += run_row("end_turn_cycle", rows["end_turn_cycle"],
                                 lambda: row_end_turn_cycle(host, client, crash0, crash_start))
        finally:
            shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_skirmish_saved_pve2_end_turn: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
