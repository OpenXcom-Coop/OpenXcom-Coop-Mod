"""MG-A S-E - test_w2_cydonia_ending.py: Cydonia's game-ending end on both machines (owner D239 (a), V5; D158 (a),
D226 (a)) and the stage offer that overtakes its stage_end (F9992). Spec docs rewrite/prompts/mga_multistage_handoff.md
(f), AMENDMENT MG-A-1 section 5 stage S-E (rows MS6, MS7) plus the F9992 row MS8 (orchestrator ruling, R3); TASK 0
constants docs rewrite/mga-task0/e/CONSTANTS.md (pins, the D239 (a) cell table, the walls).

Boot E (custom battle, lobby PORT_E): raw.bring_up_lobby + drive_to_battlescape(STR_MARS_CYDONIA_LANDING, seat_count 2,
pre_ok set_seed SEED_E), MAP_FP_E pinned, pin_ai_neutral (the 12 aliens), hash clean. MS6 continues MS8's boot.
Boot F (SHARED campaign, lobby PORT_F): new_campaign shared, the squad split (seat 0 / seat 1), open_cydonia, set_seed
SEED_F, confirm_cydonia, the stage-1 spine, MAP_FP_F pinned, pin_ai_neutral, hash clean.

  MS8  the stage offer is stashed and replayed (F9992). Kill-all, END TURN client then host; the stash lever: the
       client's TEST-ONLY read-only `hash_timing {reps}` (reps from a 1-rep measurement, a ~STASH_BLOCK_S block of its
       main thread) is sent on a harness thread, STASH_LEAD_S later the host closes its NextTurnState, so `stage_end`
       and the stage offer reach the client in one pull (guard: the block outlasts the host's close). Cells: the
       client's stage-2 BriefingState within ENTRY_S; its `stage` record offerStashed 1, offerReplayed 1, applied 1;
       its log names the stash; after the spine both machines turn 1 on STR_MARS_THE_FINAL_ASSAULT, mapSizeXYZ 7200,
       mapFingerprint equal, battleId b2 > b1 equal; hash_now full all buckets EQUAL; desyncSeen false; both alive.
  MS6  custom battle, stage 2: the host aborts and the partner votes YES (R4-L1) with nobody on an exit ("0 Units in
       Target Exit") ->
       abortCutscene loseGame. Polled every POLL_S until both machines show the main menu (MENU_S bound), never a
       dismiss_popup (W2-H17b keep list). Cells: the partner applies `battle_end` (applied 1, reason abort, aborted,
       inExitArea 0, the host's seq) hash-clean (desyncSeen false; the teardown snapshot battleEnd.hashVerify, else
       lastHashVerify, is {kind battle_end, the host's seq}); no DebriefingState on either machine at any poll; both
       play the host's ending (a SlideshowState on both); both reach the main menu; the partner alive, no new crash
       file; the partner's battle scope is reset: event_state phase not Active at SCOPE_T1 and
       battleEnd.resultWaitPasses equal at SCOPE_T1 and SCOPE_T2 (s after the OK).
  MS7  SHARED campaign, stage 1: the host aborts and the partner votes YES (R4-L1) with nobody on an END_POINT tile
       ("0 Units in Target Exit"; both
       soldiers in the craft) -> loseGame. Polled until SCOPE_T2. Cells: ending_state ending END_LOSE and statistics
       on both; no DebriefingState at any poll; a SlideshowState on both; the partner applies `battle_end` hash-clean;
       the partner alive, no new crash file; the partner's battle scope reset (MS6's two cells).

RED on S-E's commit 1 (= S-A1's green build; TASK 0 T0-E1 4/4, T0-E2 3/3): MS6 and MS7 fail ONLY their two scope cells
- the partner's battle_end consumer waits for a debrief result the host never sends (no DebriefingState::init under a
game-ending cutscene, F9814), so its phase stays Active and resultWaitPasses grows every frame; every other cell holds.
MS8 has no red cell (S-A1's stash / replay is in this base): it PASSES on the red build.

Each row prints ONE "EVIDENCE <id>:" line before its verdict, then "PASS <id>" or "FAIL <id>: <cells>" and, on a FAIL,
ONE "CAPTURE <id>:" line (both machines' event_state, battle_state, stack and log tail). A bring-up step past its bound
fails its boot's rows `boot` with one CAPTURE line. Every row runs after a failure. WV-D95 / WV-D99 / WV-D100: ONE
foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_cydonia_ending.py
"""

import json
import math
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_cydonia_coop_start import _craft_and_soldiers, _seat, _aboard
from test_w2_multistage import (FixtureMiss, short, rc, stack, has_bstate, evidence, wait_until, step, run_spine,
                                ENTRY_S, IDLE_S, FACTION_PLAYER, FACTION_HOSTILE)

# ----- boot E (TASK 0: SEED_E 1, stage-1 fingerprint 5/5, stage-2 fingerprint 5/5, host == client) -----
PORT_E, GC_E = "48575", (49682, 49683)
SEED_E = 1
MAP_FP_E = 2.509715288832488e+18
ALIENS_E = list(range(1000000, 1000012))
SEATS_E = {8: 1, 9: 1, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0}
# ----- boot F (TASK 0: SEED_F 1 right before confirm_cydonia, fingerprint 3/3) -----
PORT_F, GC_F = "48576", (49684, 49685)
SEED_F = 1
MAP_FP_F = -3.7087676953867494e+18
SEATS_F = {1: 0, 2: 1}
ALIENS_F = list(range(1000000, 1000012))
MISSION_1, MISSION_2 = "STR_MARS_CYDONIA_LANDING", "STR_MARS_THE_FINAL_ASSAULT"
STAGE2_TILES = 7200
STASH_BLOCK_S, STASH_LEAD_S = 2.0, 0.3   # the client's hash_timing block, the host's close this long into it
MENU_S = 100            # the OK -> both main menus (TASK 0: 89.8-90.4 s, loseGame's 3 x 30 s slideshow)
SCOPE_T1, SCOPE_T2 = 5.0, 10.0          # the partner's scope reads, s after the OK
POLL_S = 0.5
END_LOSE = 2
NO_EXIT = "0 Units in Target Exit"
END_STATES = ("CutsceneState", "StatisticsState", "SlideshowState", "VideoState")   # W2-H17b keep list


def bview(gc):
    """battle_state, only while a BattlescapeState is on the stack (F9920)."""
    st = stack(gc)
    if not has_bstate(st):
        return {"skipped": f"no BattlescapeState on the stack (F9920): {st}"}
    b = battle_state(gc)
    units = b.get("units") or []
    return {"missionType": b.get("missionType"), "mapSizeXYZ": b.get("mapSizeXYZ"),
            "mapFingerprint": b.get("mapFingerprint"), "turn": b.get("turn"), "side": b.get("side"),
            "battleId": (b.get("authority") or {}).get("battleId"), "pendingStates": b.get("pendingStates"),
            "isBusy": b.get("isBusy"),
            "xcom": {u["id"]: u.get("coop") for u in units if u.get("faction") == FACTION_PLAYER and not u.get("isOut")},
            "aliens": sorted(u["id"] for u in units if u.get("faction") == FACTION_HOSTILE and not u.get("isOut"))}


BE_KEYS = ("emitted", "applied", "seq", "reason", "aborted", "inExitArea", "latchedMs", "tornDownMs",
           "resultWaitPasses", "resultReceived", "resultSent", "campaign", "skirmish", "hashVerify")


def eview(gc):
    try:
        e = event_state(gc)
    except Exception as ex:
        return {"unreadable": f"{short(ex, 120)}, process rc={rc(gc)}"}
    be = e.get("battleEnd") or {}
    return {"phase": e.get("phase"), "battleId": e.get("battleId"), "desyncSeen": e.get("desyncSeen"),
            "lastSeqApplied": e.get("lastSeqApplied"), "lastHashVerify": e.get("lastHashVerify"),
            "stage": e.get("stage"), "battleEnd": {k: be.get(k) for k in BE_KEYS}}


def ending(gc):
    try:
        r = gc.cmd({"cmd": "ending_state"})
    except Exception as ex:
        return {"unreadable": short(ex, 120)}
    return {k: r.get(k) for k in ("hasSave", "ending", "statistics", "campaignEnded", "mainMenu")}


def log_lines(gc, needle=None, n=12):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n").split("\t")[-1] for ln in f]
    except OSError:
        return []
    if needle is not None:
        return [ln for ln in lines if needle in ln]
    return [ln for ln in lines if "[coop-battle-end]" in ln][-4:] + lines[-n:]


def capture(rid, machines, why):
    cap = {}
    for gc in machines:
        cap[gc.name] = {"rc": rc(gc), "stack": stack(gc), "event_state": eview(gc), "log": log_lines(gc)}
        try:
            cap[gc.name]["battle_state"] = bview(gc)
        except Exception as e:
            cap[gc.name]["battle_state"] = f"probe failed: {short(e)}"
    print(f"CAPTURE {rid} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def pins(host, client, fp, seats, aliens, tag):
    hb, cb = bview(host), bview(client)
    bad = []
    if hb.get("mapFingerprint") != fp or cb.get("mapFingerprint") != fp:
        bad.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client={cb.get('mapFingerprint')!r} (pinned {fp!r})")
    if (hb.get("side"), hb.get("turn"), hb.get("missionType")) != (FACTION_PLAYER, 1, MISSION_1):
        bad.append(f"host (side, turn, mission)={(hb.get('side'), hb.get('turn'), hb.get('missionType'))}")
    if hb.get("xcom") != seats or cb.get("xcom") != seats:
        bad.append(f"X-COM seats host={hb.get('xcom')} client={cb.get('xcom')} (want {seats})")
    if bad:
        raise FixtureMiss("bring-up pins: " + "; ".join(bad))
    pinned = step("pin_ai_neutral", lambda: pin_ai_neutral(host, client, tag=tag), [host, client])
    if sorted(pinned) != aliens:
        raise FixtureMiss(f"pin_ai_neutral pinned {pinned} (want {aliens})")
    step("wait_host_idle", lambda: session.wait_host_idle(host, client, timeout=IDLE_S), [host, client])
    step("hash clean at bring-up", lambda: assert_hash_clean(host, client, full=True, what="bring-up"), [host, client])
    return {"mapFingerprint": hb.get("mapFingerprint"), "pinned": len(pinned)}


def boot_e(host, client):
    m = [host, client]
    step("bring_up_lobby", lambda: raw.bring_up_lobby(host, client, PORT_E), m)
    step("drive_to_battlescape", lambda: session.drive_to_battlescape(
        host, client, {}, mission=MISSION_1, seat_count=2,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_E})), m)
    return pins(host, client, MAP_FP_E, SEATS_E, ALIENS_E, "mga-e")


def boot_f(host, client):
    m = [host, client]
    step("spawn + connect", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    step("new_campaign shared", lambda: session.new_campaign(host, client, port=PORT_F, campaign_mode="shared"), m)
    craft, roster = step("craft and roster", lambda: _craft_and_soldiers(host), m)

    def split():
        _seat(host, craft, roster)
        for gc in (host, client):
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": roster[0], "owner": 0})
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": roster[1], "owner": 1})
        host.wait_for("shared squad seated", lambda: (_aboard(host, craft) == sorted(roster[:2])) or None, timeout=30)
    step("squad split", split, m)

    def cydonia():
        host.ok({"cmd": "open_cydonia", "craft_id": craft})
        host.wait_for("Cydonia confirmation", lambda: session.has_state(host, "ConfirmCydoniaState") or None)
        host.ok({"cmd": "set_seed", "seed": SEED_F})
        host.ok({"cmd": "confirm_cydonia"})
    step("open + confirm Cydonia", cydonia, m)
    step("stage-1 spine", lambda: run_spine(host, client), m)
    if (stack(client) or [None])[0] != "GeoscapeState":
        raise FixtureMiss(f"client stack {stack(client)} (want GeoscapeState at the bottom)")
    return dict(pins(host, client, MAP_FP_F, SEATS_F, ALIENS_F, "mga-e-f"), craft=craft, squad=roster[:2])


# ===================== MS8 (boot E): the stage offer stashed and replayed =====================


def kill_and_end_turn(host, client, seats):
    """Kill-all, settle, hash clean, END TURN client then host; the host's NextTurnState up. Guard failures."""
    g = []
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_HOSTILE})
    if not r.get("ok") or sorted(r.get("killed") or []) != ALIENS_E:
        g.append(f"kill_unit_real faction 1 answered {r} (want ok, killed {ALIENS_E})")
    ok, secs = wait_until(lambda: (not bview(host).get("aliens") and bview(host).get("pendingStates") == 0
                                   and not bview(host).get("isBusy") and stack(host)[-1] == "BattlescapeState"),
                          60, 0.2)
    if not ok:
        g.append(f"host kill chain not settled within {secs}s: host stack {stack(host)}")
    try:
        session.wait_host_idle(host, client, timeout=IDLE_S)
        assert_hash_clean(host, client, full=True, what="before END TURN")
    except Exception as e:
        g.append(f"settle / hash before END TURN: {short(e, 500)}")
    hb, cb = bview(host), bview(client)
    if hb.get("xcom") != seats or cb.get("xcom") != seats:
        g.append(f"survivors host={hb.get('xcom')} client={cb.get('xcom')} (want {seats})")
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        ok, secs = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20, 0.1)
        if not ok:
            g.append(f"host never painted END TURN 1/2 after the client's press ({secs}s)")
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        g.append(f"END TURN presses: {short(e)}")
    ok, secs = wait_until(lambda: "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", ""), 30, 0.1)
    if not ok:
        g.append(f"host NextTurnState not up within {secs}s after both END TURN presses")
    return g


def stash_close(host, client, ctx):
    """The F9992 lever around the host's NextTurnState close. Guard failures."""
    g, lv = [], {}
    one = client.cmd({"cmd": "hash_timing", "reps": 1})
    per = ((one.get("sweepUs") or {}).get("mean") or 0) + ((one.get("saveBlobUs") or {}).get("mean") or 0)
    lv["perRepUs"], lv["reps"] = per, max(1, min(1000, int(math.ceil(STASH_BLOCK_S * 1e6 / max(per, 1.0)))))
    if not one.get("ok"):
        g.append(f"client hash_timing reps 1 answered {one}")

    def block():
        lv["sent"] = time.time()
        r = client.cmd({"cmd": "hash_timing", "reps": lv["reps"]})
        lv["answered"], lv["ok"] = time.time(), r.get("ok")
    th = threading.Thread(target=block, daemon=True)
    th.start()
    time.sleep(STASH_LEAD_S)
    ctx["t_close"] = lv["close"] = time.time()
    d = host.cmd({"cmd": "dismiss_popup"})
    lv["closeAnswered"] = time.time()
    ctx["hostStageAtClose"] = eview(host).get("stage")
    th.join(timeout=30)
    if d.get("handled") != "NextTurnState->close":
        g.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    if not (lv.get("ok") and lv["sent"] < lv["close"] and lv.get("answered", 0) > lv["closeAnswered"]):
        g.append(f"the client's hash_timing block did not outlast the host's close: {lv}")
    ctx["lever"] = {k: (round(v - lv["sent"], 2) if k in ("close", "closeAnswered", "answered") else v)
                    for k, v in lv.items() if k != "sent"}
    return g


def ms8(host, client, ctx, crash0):
    he, ce = eview(host), eview(client)
    ctx["b1"] = he.get("battleId")
    g = []
    for name, e in (("host", he), ("client", ce)):
        st = e.get("stage")
        if not isinstance(st, dict) or st.get("emitted") != 0 or st.get("applied") != 0 or st.get("offerStashed") != 0:
            g.append(f"{name} event_state.stage before the stage = {st} (want emitted 0, applied 0, offerStashed 0)")
    if not isinstance(ctx["b1"], int) or ctx["b1"] <= 0 or ce.get("battleId") != ctx["b1"]:
        g.append(f"battleId host={ctx['b1']} client={ce.get('battleId')} (want equal, > 0)")
    g += kill_and_end_turn(host, client, SEATS_E)
    if not g:
        g += stash_close(host, client, ctx)
    if g:
        evidence("MS8", {"guards": g, "ctx": ctx})
        return [f"pre-stage: {m}" for m in g]
    f = []
    seen, _s = wait_until(lambda: any("BriefingState" in s for s in stack(client)),
                          max(0.0, ENTRY_S - (time.time() - ctx["t_close"])), 0.25)
    ctx["clientBriefingS"] = round(time.time() - ctx["t_close"], 2) if seen else None
    cs = eview(client).get("stage") or {}
    stash_log = [ln for ln in log_lines(client, "stashed: the next stage of battle")]
    if not seen:
        f.append(f"client never showed the stage-2 BriefingState within {ENTRY_S}s (stack {stack(client)})")
    if cs.get("offerStashed") != 1 or cs.get("offerReplayed") != 1 or cs.get("applied") != 1:
        f.append(f"client stage offerStashed/offerReplayed/applied={cs.get('offerStashed')}/{cs.get('offerReplayed')}/"
                 f"{cs.get('applied')} (want 1/1/1)")
    if not any(f"battle {ctx['b1']}" in ln for ln in stash_log):
        f.append(f"client log never names the stash of battle {ctx['b1']}'s next stage: {stash_log}")
    hs = ctx.get("hostStageAtClose") or {}
    if hs.get("emitted") != 1:
        f.append(f"host stage.emitted={hs.get('emitted')} at the close (want 1)")
    green = {}
    if seen:
        try:
            ctx["pressed"], ctx["spineS"] = run_spine(host, client)
            hb, cb = bview(host), bview(client)
            green = {"host": hb, "client": cb}
            b2 = eview(host).get("battleId")
            ctx["b2"] = b2
            for name, b in (("host", hb), ("client", cb)):
                if (b.get("turn"), b.get("missionType"), b.get("mapSizeXYZ")) != (1, MISSION_2, STAGE2_TILES):
                    f.append(f"{name} turn/missionType/mapSizeXYZ={b.get('turn')}/{b.get('missionType')}/"
                             f"{b.get('mapSizeXYZ')} (want 1/{MISSION_2}/{STAGE2_TILES})")
            if hb.get("mapFingerprint") is None or hb.get("mapFingerprint") != cb.get("mapFingerprint"):
                f.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client={cb.get('mapFingerprint')!r}")
            if not (isinstance(b2, int) and b2 > ctx["b1"] and eview(client).get("battleId") == b2):
                f.append(f"battleId host={b2} client={eview(client).get('battleId')} (want equal and > b1 {ctx['b1']})")
            ctx["inStage2"] = all(b.get("missionType") == MISSION_2 for b in (hb, cb))
            assert_hash_clean(host, client, full=True, what="stage 2 turn 1 after the stash")
        except Exception as e:
            f.append(f"stage-2 spine / cells: {short(e, 600)}")
    for name, gc in (("host", host), ("client", client)):
        if rc(gc) is not None:
            f.append(f"{name} process exited rc={rc(gc)}")
        elif eview(gc).get("desyncSeen") is not False:
            f.append(f"{name} desyncSeen true after the stage")
    new_crash = sorted(os.path.basename(p) for p in session._crash_log_snapshot() - crash0)
    if new_crash:
        f.append(f"new crash file(s) {new_crash}")
    evidence("MS8", {"b1": ctx.get("b1"), "b2": ctx.get("b2"), "lever": ctx.get("lever"),
                     "clientBriefingS": ctx.get("clientBriefingS"), "clientStage": cs, "hostStageAtClose": hs,
                     "stashLog": stash_log, "spineS": ctx.get("spineS"), "pressed": ctx.get("pressed"),
                     "green": green, "newCrashFiles": new_crash})
    return f


# ===================== MS6 / MS7: the game-ending end =====================


def abort_ok(host, client, rid, ctx):
    """The host's abort, its AbortMissionState read, the OK. Guard failures; ctx['t_ok']."""
    g = []
    r = host.cmd({"cmd": "battle_action", "action": "abort"})
    ok, secs = wait_until(lambda: stack(host)[-1] == "AbortMissionState", 10, 0.1)
    if not ok:
        return [f"host AbortMissionState not on top within {secs}s ({r}); stack {stack(host)}"]
    texts = [w.get("text") for w in (host.cmd({"cmd": "list_widgets"}).get("widgets") or []) if w.get("text")]
    ctx["abortDialog"] = texts
    if NO_EXIT not in texts:
        g.append(f"AbortMissionState texts {texts} (want {NO_EXIT!r}: nobody on an exit)")
        return g
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "AbortMissionState":
        g.append(f"host dismiss_popup answered {d} (want handled AbortMissionState)")
        return g
    try:
        session.abort_vote_yes(host, client)
    except Exception as e:
        g.append(str(e))
        return g
    ok, secs = wait_until(lambda: (event_state(host).get("abortVote") or {}).get("applies") == 1, 10, 0.1)
    if not ok:
        g.append(f"the host's abortVote.applies never reached 1 within {secs}s of the partner's YES")
    ctx["t_ok"] = time.time()
    return g


def poll_end(host, client, ctx, until):
    """Every POLL_S after the OK: both stacks; the partner's scope at SCOPE_T1 / SCOPE_T2; never a dismiss_popup."""
    p = ctx["poll"] = {"debrief": {}, "slideshow": {}, "mainMenuS": {}, "endTops": {}, "n": 0}
    t_ok = ctx["t_ok"]
    while True:
        t = time.time() - t_ok
        for gc in (host, client):
            st = stack(gc)
            if isinstance(st, list):
                if any("DebriefingState" in s for s in st):
                    p["debrief"].setdefault(gc.name, round(t, 2))
                if "SlideshowState" in st:
                    p["slideshow"].setdefault(gc.name, round(t, 2))
                if st == ["MainMenuState"]:
                    p["mainMenuS"].setdefault(gc.name, round(t, 2))
                if st and st[-1] in END_STATES:
                    p["endTops"][gc.name] = st[-1]
        if "scope1" not in ctx and t >= SCOPE_T1:
            ctx["scope1"] = {"client": eview(client), "host": eview(host), "t": round(t, 2)}
        if "scope2" not in ctx and t >= SCOPE_T2:
            ctx["scope2"] = {"client": eview(client), "host": eview(host), "t": round(t, 2)}
        p["n"] += 1
        if (t >= SCOPE_T2 and "scope2" in ctx and until(p)) or t >= MENU_S:
            break
        time.sleep(max(0.0, t_ok + p["n"] * POLL_S - time.time()))


def end_cells(host, client, ctx, crash0):
    """The D239 (a) cells both rows share."""
    f, p = [], ctx["poll"]
    s1, s2 = ctx.get("scope1") or {}, ctx.get("scope2") or {}
    ce1, he1 = s1.get("client") or {}, s1.get("host") or {}
    cbe, hbe = ce1.get("battleEnd") or {}, he1.get("battleEnd") or {}
    want = {"applied": 1, "reason": "abort", "aborted": True, "inExitArea": 0, "seq": hbe.get("seq")}
    if hbe.get("emitted") != 1 or any(cbe.get(k) != v for k, v in want.items()):
        f.append(f"partner battle_end applied/reason/aborted/inExitArea/seq={[cbe.get(k) for k in want]} "
                 f"(want {list(want.values())}; host emitted {hbe.get('emitted')})")
    hv = cbe.get("hashVerify") if isinstance(cbe.get("hashVerify"), dict) else ce1.get("lastHashVerify")
    if ce1.get("desyncSeen") is not False or not isinstance(hv, dict) or hv.get("kind") != "battle_end" \
            or hv.get("seq") != hbe.get("seq"):
        f.append(f"partner battle_end not hash-clean: desyncSeen {ce1.get('desyncSeen')}, verify {hv} "
                 f"(want kind battle_end seq {hbe.get('seq')})")
    if p["debrief"]:
        f.append(f"a DebriefingState was on a stack (s after the OK): {p['debrief']}")
    if sorted(p["slideshow"]) != ["client", "host"]:
        f.append(f"the host's ending did not play on both machines: SlideshowState seen at {p['slideshow']}")
    if rc(client) is not None:
        f.append(f"partner process exited rc={rc(client)}")
    new_crash = sorted(os.path.basename(x) for x in session._crash_log_snapshot() - crash0)
    ctx["newCrashFiles"] = new_crash
    if new_crash:
        f.append(f"new crash file(s) {new_crash}")
    # RED on commit 1 (TASK 0): the partner's battle scope stays live under the end screens (F9814)
    if ce1.get("phase") == "Active" or "phase" not in ce1:
        f.append(f"partner battle scope not reset: event_state phase {ce1.get('phase')!r} at {s1.get('t')}s "
                 f"after the OK (want not Active)")
    w1 = cbe.get("resultWaitPasses")
    w2 = ((s2.get("client") or {}).get("battleEnd") or {}).get("resultWaitPasses")
    if w1 is None or w1 != w2:
        f.append(f"partner battle_end latch still waiting: resultWaitPasses {w1} at {s1.get('t')}s -> {w2} at "
                 f"{s2.get('t')}s (want not growing)")
    return f


def ms6(host, client, ctx):
    hst, cst = stack(host), stack(client)
    pre = []
    if not ctx.get("inStage2"):
        pre.append("MS8 never brought both machines into stage 2")
    for name, gc, st in (("host", host, hst), ("client", client, cst)):
        if rc(gc) is not None:
            pre.append(f"{name} process exited rc={rc(gc)}")
        elif not (isinstance(st, list) and st and st[-1] == "BattlescapeState"):
            pre.append(f"{name} top is not BattlescapeState: {st}")
        elif bview(gc).get("missionType") != MISSION_2:
            pre.append(f"{name} missionType={bview(gc).get('missionType')!r} (want {MISSION_2!r})")
    if pre:
        evidence("MS6", {"precondition": pre, "hostStack": hst, "clientStack": cst})
        return [f"precondition 'both in stage 2' missing: {'; '.join(pre)}"]
    crash0 = session._crash_log_snapshot()
    g = abort_ok(host, client, "MS6", ctx)
    if g:
        evidence("MS6", {"guards": g, "abortDialog": ctx.get("abortDialog")})
        return [f"guard: {m}" for m in g]
    poll_end(host, client, ctx, lambda p: sorted(p["mainMenuS"]) == ["client", "host"])
    f = end_cells(host, client, ctx, crash0)
    if sorted(ctx["poll"]["mainMenuS"]) != ["client", "host"]:
        f.append(f"both machines never reached the main menu within {MENU_S}s of the OK: main menu at "
                 f"{ctx['poll']['mainMenuS']}, stacks host {stack(host)} client {stack(client)}")
    evidence("MS6", {"abortDialog": ctx.get("abortDialog"), "poll": ctx["poll"], "scope1": ctx.get("scope1"),
                     "scope2": ctx.get("scope2"), "end": {"host": stack(host), "client": stack(client)},
                     "newCrashFiles": ctx.get("newCrashFiles")})
    return f


def ms7(host, client, ctx):
    crash0 = session._crash_log_snapshot()
    ctx["b1"] = eview(host).get("battleId")
    g = abort_ok(host, client, "MS7", ctx)
    if g:
        evidence("MS7", {"guards": g, "abortDialog": ctx.get("abortDialog")})
        return [f"guard: {m}" for m in g]
    ends = ctx["endings"] = {}

    def statistics(p):
        for gc in (host, client):
            e = ending(gc)
            if e.get("ending") == END_LOSE and e.get("statistics"):
                ends.setdefault(gc.name, dict(e, t=round(time.time() - ctx["t_ok"], 2)))
        return sorted(ends) == ["client", "host"]
    poll_end(host, client, ctx, statistics)
    f = end_cells(host, client, ctx, crash0)
    if sorted(ends) != ["client", "host"]:
        f.append(f"ending_state ending {END_LOSE} + statistics not on both: {ends}; last host {ending(host)} "
                 f"client {ending(client)}")
    evidence("MS7", {"b1": ctx.get("b1"), "abortDialog": ctx.get("abortDialog"), "endings": ends,
                     "poll": ctx["poll"], "scope1": ctx.get("scope1"), "scope2": ctx.get("scope2"),
                     "end": {"host": stack(host), "client": stack(client)}, "newCrashFiles": ctx.get("newCrashFiles")})
    return f


# ===================== main =====================


def run_boot(tag, ports, up, rows, results):
    host = GameClient("host", ports[0], make_user_dir(f"mga_e_{tag}_host"))
    client = GameClient("client", ports[1], make_user_dir(f"mga_e_{tag}_client"))
    try:
        try:
            info = up(host, client)
            print(f"[mga-e] boot {tag} ok: {info}", flush=True)
        except Exception as e:
            capture("boot", [host, client], short(e, 600))
            for rid, _fn in rows:
                results[rid] = False
                print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot (FIXTURE-STOP) {short(e, 600)}",
                      flush=True)
            return
        for rid, fn in rows:
            try:
                fails = fn(host, client)
            except FixtureMiss as e:
                fails = [f"FIXTURE-STOP {e}"]
            except Exception as e:
                fails = [short(e, 600)]
            results[rid] = not fails
            if fails:
                print(f"FAIL {rid}: {len(fails)} cell(s): " + " | ".join(fails), flush=True)
                capture(rid, [host, client], "row failed")
            else:
                print(f"PASS {rid}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[mga-e] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results, ctx_e, ctx_f = {}, {}, {}
    crash0 = session._crash_log_snapshot()
    run_boot("E", GC_E, boot_e, (("MS8", lambda h, c: ms8(h, c, ctx_e, crash0)),
                                 ("MS6", lambda h, c: ms6(h, c, ctx_e))), results)
    run_boot("F", GC_F, boot_f, (("MS7", lambda h, c: ms7(h, c, ctx_f)),), results)
    order = ["MS8", "MS6", "MS7"]
    passed = [r for r in order if results.get(r)]
    failed = [r for r in order if not results.get(r)]
    print(f"\ntest_w2_cydonia_ending: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
