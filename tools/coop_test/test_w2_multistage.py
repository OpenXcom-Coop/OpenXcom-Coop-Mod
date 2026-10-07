"""MG-A S-A1 - test_w2_multistage.py: a co-op stage change hands the next stage to both players (owner D158 (a),
D226 (a); spec docs rewrite/prompts/mga_multistage_handoff.md (f) rows MS1 and MS4 as AMENDMENT MG-A-1 section 5
restates them for stage S-A1; TASK 0 constants docs rewrite/mga-task0/a1/CONSTANTS.md).

ONE boot (boot A, lobby PORT_A): the classic parallel skirmish on the stock Cydonia landing
(STR_MARS_CYDONIA_LANDING, 50x50x4, 12 aliens), set_seed SEED_A right before newbattle_ok, MAP_FP_A pinned,
pin_ai_neutral (every alien), hash clean. MS4 continues MS1's boot.

  MS1  stage 2 for both players, the kill-all route. The host kills every alien (kill_unit_real faction 1, the
       real UnitDieBState chain), both machines settle, END TURN client then host, the host closes its
       NextTurnState (NextTurnState::close -> finishBattle(false, 7) -> vanilla's next-stage branch). Stage-entry
       cells: the client shows the stage-2 BriefingState within ENTRY_S of the host's close, its missionType is
       STR_MARS_THE_FINAL_ASSAULT, the client's `stage` record applied 1, the host's emitted 1 (read right after the
       close). Then the stage-2 spine (session.briefings_to_battlescape: both briefings at once, D210 b; both equip
       screens, D174 a / D205 a; turn 1) and the green cells: the host's record (emitted 1, nextStage, fromBattleId
       b1, aborted false, inExitArea 7, hBuckets = the 9 action-end names, toBattleId b2), the client's (applied 1,
       the host's seq, hashVerify {seq, kind stage_end, buckets}, latchedMs > 0, tornDownMs >= latchedMs, loadedMs
       >= tornDownMs, toBattleId b2); both battleId b2 > b1 and equal; both equip screens pressed, equip ended,
       turn 1; missionType, mapSizeXYZ STAGE2_TILES and mapFingerprint equal; the living X-COM ids == the stage-1
       survivors on both, seat tags kept; hash_now full all buckets EQUAL; desyncSeen false on both; the client's
       selection is its own soldier; one client soldier walks (pick_and_walk) and lands on the same tile on both;
       the host is alive; no new crash file. M1 (T0-6): the host's researchMode.seats[1].count equals its liveCount
       in a custom battle, so the count across the stage is EVIDENCE only, never a cell.
  MS4  a rejoin inside stage 2 (MS1's boot): precondition "both machines in stage 2" (alive, a BattlescapeState on
       top, missionType STR_MARS_THE_FINAL_ASSAULT, battleId b2); then the SPEC 16 leave + in-memory rejoin + RESUME
       (test_w2_rejoin_reveal_rearm's steps: the client leaves, a fresh process client2 rejoins, the host presses
       RESUME). Cells: client2 in stage 2 (missionType), battleId b2 kept, mapFingerprint equal to the host's and to
       MS1's stage-2 print, hash clean, desyncSeen false on both.

RED on S-A1's commit 1 (no stage writer; TASK 0 T0-3 measured on the unchanged build, 3/3): the client never shows a
stage-2 briefing (its missionType stays the landing), both `stage` records read zeros, and the host dies after the
stage change (F5081, CoopReveal::flushQuiescent reading the freed stage-1 BattlescapeState; died at 1 / 5 / 36 s, so
host liveness is EVIDENCE only) after its reveal ev seq 48, authored on the stage-2 map, desynced the client. MS4
fails its precondition. The host's battle_state is never probed unless a BattlescapeState is on its stack (F9920:
a vanilla next-stage briefing keeps a STALE _battleState that the battle_state probe dereferences).

Each row prints ONE "EVIDENCE <id>:" line before its verdict, then "PASS <id>" or "FAIL <id>: <cells>" and, on a
FAIL, ONE "CAPTURE <id>:" line (both machines' event_state, battle_state, stack and log tail). A bring-up step past
its bound fails every row `boot` with one CAPTURE line. Every row runs after a failure. WV-D95 / WV-D99 / WV-D100:
ONE foreground run, no skip path; exit 0 only when both rows pass, 2 otherwise.

Run:  python tools/coop_test/test_w2_multistage.py
"""

import ast
import contextlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_skirmish_rejoin_battle import (drop_client_mid_battle, rejoin_skirmish, dialog, in_battle_save,
                                         COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)

# ----- boot A (TASK 0 T0-4: SEED_A 1, stage-1 fingerprint identical on 5/5 boots, host == client) -----
PORT_A = "48571"
GC_PORTS = (49674, 49675)
MISSION_1, MISSION_2 = "STR_MARS_CYDONIA_LANDING", "STR_MARS_THE_FINAL_ASSAULT"
SEED_A = 1
MAP_FP_A = 2.509715288832488e+18
ALIEN_IDS = list(range(1000000, 1000012))           # the 12 landing aliens (T0-3)
SEATS_A = {8: 1, 9: 1, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0}   # X-COM id -> coop seat at bring-up (T0-3)
STAGE2_TILES = 7200                                  # the final assault map, 60x60x2 (T0-2, 3/3)
WALKER = 8                                           # a client (seat 1) soldier
H_BUCKETS = sorted(["terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr", "synced",
                    "saveBlob"])
ENTRY_S = 90          # the client's stage-2 briefing after the host's close (spec (f) MS1)
IDLE_S = 30
FACTION_PLAYER, FACTION_HOSTILE, STATUS_DEAD = 0, 1, 6


class FixtureMiss(Exception):
    pass


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def rc(gc):
    return None if gc.proc is None else gc.proc.poll()


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:
        return f"probe failed ({short(e, 120)}), process rc={rc(gc)}"


def has_bstate(st):
    return isinstance(st, list) and any("BattlescapeState" in s for s in st)


def bview(gc):
    """battle_state, only while a BattlescapeState is on the stack (F9920)."""
    st = stack(gc)
    if not has_bstate(st):
        return {"skipped": f"no BattlescapeState on the stack (F9920): {st}"}
    b = battle_state(gc)
    units = b.get("units") or []
    return {"missionType": b.get("missionType"), "mapSizeXYZ": b.get("mapSizeXYZ"),
            "mapFingerprint": b.get("mapFingerprint"), "turn": b.get("turn"), "side": b.get("side"),
            "selectedId": b.get("selectedId"), "phase": b.get("phase"),
            "battleId": (b.get("authority") or {}).get("battleId"),
            "xcom": {u["id"]: u.get("coop") for u in units if u.get("faction") == FACTION_PLAYER and not u.get("isOut")},
            "aliens": sorted(u["id"] for u in units if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")),
            "pos": {u["id"]: (u.get("x"), u.get("y"), u.get("z")) for u in units if u["id"] == WALKER},
            "pendingStates": b.get("pendingStates"), "isBusy": b.get("isBusy")}


def eview(gc):
    try:
        e = event_state(gc)
    except Exception as ex:
        return {"unreadable": f"{short(ex, 120)}, process rc={rc(gc)}"}
    rm = e.get("researchMode") or {}
    return {"phase": e.get("phase"), "battleId": e.get("battleId"), "desyncSeen": e.get("desyncSeen"),
            "lastSeqEmitted": e.get("lastSeqEmitted"), "lastSeqApplied": e.get("lastSeqApplied"),
            "queueDepth": e.get("queueDepth"), "stage": e.get("stage"), "equip": e.get("equip"),
            "stageSkips": (e.get("battleEnd") or {}).get("stageSkips"),
            "seat1Research": ((rm.get("seats") or [{}, {}])[1] or {}).get("count"), "liveResearch": rm.get("liveCount")}


def log_tail(gc, n=12):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n").split("\t")[-1] for ln in f]
    except OSError:
        return []
    return [ln for ln in lines if "[coop-battle-end]" in ln][-4:] + lines[-n:]


def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def capture(rid, machines, why):
    cap = {}
    for gc in machines:
        cap[gc.name] = {"rc": rc(gc), "stack": stack(gc), "event_state": eview(gc), "log": log_tail(gc)}
        try:
            cap[gc.name]["battle_state"] = bview(gc)
        except Exception as e:
            cap[gc.name]["battle_state"] = f"probe failed: {short(e)}"
    print(f"CAPTURE {rid} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


def wait_until(pred, timeout, interval=0.25):
    t0 = time.time()
    while True:
        try:
            if pred():
                return True, round(time.time() - t0, 2)
        except Exception:
            pass
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def step(name, fn, machines):
    try:
        return fn()
    except Exception as e:
        raise FixtureMiss(f"{name}: {short(e, 600)}") from None


# ===================== boot A =====================


def boot_a(host, client):
    m = [host, client]
    step("bring_up_lobby", lambda: raw.bring_up_lobby(host, client, PORT_A), m)
    step("drive_to_battlescape", lambda: session.drive_to_battlescape(
        host, client, {}, mission=MISSION_1, seat_count=2,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_A})), m)
    hb, cb = bview(host), bview(client)
    bad = []
    if hb.get("mapFingerprint") != MAP_FP_A or cb.get("mapFingerprint") != MAP_FP_A:
        bad.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client={cb.get('mapFingerprint')!r} "
                   f"(baked {MAP_FP_A!r}, SEED_A {SEED_A})")
    if (hb.get("side"), hb.get("turn")) != (FACTION_PLAYER, 1) or hb.get("missionType") != MISSION_1:
        bad.append(f"host (side, turn, mission)={(hb.get('side'), hb.get('turn'), hb.get('missionType'))}")
    if hb.get("xcom") != SEATS_A or cb.get("xcom") != SEATS_A:
        bad.append(f"X-COM seats host={hb.get('xcom')} client={cb.get('xcom')} (want {SEATS_A})")
    if bad:
        raise FixtureMiss("bring-up pins: " + "; ".join(bad))
    pinned = step("pin_ai_neutral", lambda: pin_ai_neutral(host, client, tag="mga-a1"), m)
    if sorted(pinned) != ALIEN_IDS:
        raise FixtureMiss(f"pin_ai_neutral pinned {pinned} (want {ALIEN_IDS})")
    step("wait_host_idle", lambda: session.wait_host_idle(host, client, timeout=IDLE_S), m)
    step("hash clean at bring-up", lambda: assert_hash_clean(host, client, full=True, what="bring-up"), m)
    return {"mapFingerprint": hb.get("mapFingerprint"), "pinned": len(pinned)}


# ===================== MS1 =====================


def ms1_trigger(host, client, ctx):
    """Pre-stage cells (guards) + the kill-all trigger. Returns the list of guard failures."""
    g = []
    he, ce = eview(host), eview(client)
    ctx["b1"] = he.get("battleId")
    ctx["research1"] = {"seat1": he.get("seat1Research"), "live": he.get("liveResearch")}
    for name, e in (("host", he), ("client", ce)):
        st = e.get("stage")
        if not isinstance(st, dict) or st.get("emitted") != 0 or st.get("applied") != 0:
            g.append(f"{name} event_state.stage before the stage = {st} (want the record, emitted 0, applied 0)")
    if not isinstance(ctx["b1"], int) or ctx["b1"] <= 0 or ce.get("battleId") != ctx["b1"]:
        g.append(f"battleId host={ctx['b1']} client={ce.get('battleId')} (want equal, > 0)")
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_HOSTILE})
    if not r.get("ok") or sorted(r.get("killed") or []) != ALIEN_IDS:
        g.append(f"kill_unit_real faction 1 answered {r} (want ok, killed {ALIEN_IDS})")
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
    ctx["S"] = sorted(hb.get("xcom") or {})
    if hb.get("xcom") != SEATS_A or cb.get("xcom") != SEATS_A:
        g.append(f"survivors host={hb.get('xcom')} client={cb.get('xcom')} (want {SEATS_A})")
    for name, gc in (("host", host), ("client", client)):
        if eview(gc).get("desyncSeen") is not False:
            g.append(f"{name} desyncSeen before END TURN (want false)")
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
    ctx["t_close"] = time.time()
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        g.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    ctx["hostStageAtClose"] = eview(host).get("stage")      # finishBattle ran inside dismiss_popup
    ctx["hostRcAtClose"] = rc(host)
    return g


def ms1_entry(host, client, ctx):
    """The stage-entry cells (RED on commit 1). Returns the list of failed entry cells."""
    seen, secs = wait_until(lambda: any("BriefingState" in s for s in stack(client)),
                            max(0.0, ENTRY_S - (time.time() - ctx["t_close"])), 0.25)
    ctx["clientBriefingS"] = round(time.time() - ctx["t_close"], 2) if seen else None
    cb, ce = bview(client), eview(client)
    ctx["entry"] = {"clientBriefing": seen, "clientStack": stack(client), "clientMission": cb.get("missionType"),
                    "clientStage": ce.get("stage"), "hostStageAtClose": ctx["hostStageAtClose"],
                    "hostRcAtClose": ctx["hostRcAtClose"], "hostRcAfterWait": rc(host),
                    "clientDesyncSeen": ce.get("desyncSeen"), "clientPhase": ce.get("phase")}
    f = []
    if not seen:
        f.append(f"client never showed the stage-2 BriefingState within {ENTRY_S}s of the host's NextTurnState close "
                 f"(stack {ctx['entry']['clientStack']})")
    if cb.get("missionType") != MISSION_2:
        f.append(f"client missionType={cb.get('missionType')!r} (want {MISSION_2!r})")
    if (ce.get("stage") or {}).get("applied") != 1:
        f.append(f"client stage.applied={(ce.get('stage') or {}).get('applied')} (want 1)")
    hs = ctx["hostStageAtClose"]
    if not isinstance(hs, dict) or hs.get("emitted") != 1:
        f.append(f"host stage.emitted={hs.get('emitted') if isinstance(hs, dict) else hs} at the close (want 1)")
    return f


def run_spine(host, client):
    """session.briefings_to_battlescape, its stdout teed so the equip presses are read back."""
    buf = io.StringIO()

    class Tee(io.TextIOBase):
        def write(self, s):
            buf.write(s)
            return sys.__stdout__.write(s)

    t0 = time.time()
    with contextlib.redirect_stdout(Tee()):
        session.briefings_to_battlescape(host, client)
    pressed = None
    for ln in buf.getvalue().splitlines():
        if ln.startswith("[equip_both_ready] pressed="):
            pressed = ast.literal_eval(ln.split("pressed=", 1)[1].split(" host equip.counted=")[0])
    return pressed, round(time.time() - t0, 2)


def ms1_green(host, client, ctx):
    f = []
    pressed, ctx["spineS"] = run_spine(host, client)
    he, ce = eview(host), eview(client)
    hb, cb = bview(host), bview(client)
    hs, cs = he.get("stage") or {}, ce.get("stage") or {}
    b1, b2 = ctx["b1"], he.get("battleId")
    ctx["b2"], ctx["fp2"] = b2, hb.get("mapFingerprint")
    want_h = {"emitted": 1, "nextStage": MISSION_2, "fromBattleId": b1, "aborted": False, "inExitArea": len(ctx["S"]),
              "toBattleId": b2}
    for k, v in want_h.items():
        if hs.get(k) != v:
            f.append(f"host stage.{k}={hs.get(k)!r} (want {v!r})")
    if sorted(hs.get("hBuckets") or []) != H_BUCKETS or not hs.get("seq"):
        f.append(f"host stage.hBuckets={hs.get('hBuckets')} seq={hs.get('seq')} (want the 9 action-end names, seq > 0)")
    if cs.get("applied") != 1 or cs.get("seq") != hs.get("seq") or cs.get("toBattleId") != b2:
        f.append(f"client stage applied/seq/toBattleId={cs.get('applied')}/{cs.get('seq')}/{cs.get('toBattleId')} "
                 f"(want 1/{hs.get('seq')}/{b2})")
    hv = cs.get("hashVerify") if isinstance(cs.get("hashVerify"), dict) else {}
    if hv.get("seq") != hs.get("seq") or hv.get("kind") != "stage_end" or sorted(hv.get("buckets") or []) != H_BUCKETS:
        f.append(f"client stage.hashVerify={cs.get('hashVerify')} (want seq {hs.get('seq')}, kind stage_end, the 9 buckets)")
    lat, td, ld = cs.get("latchedMs") or 0, cs.get("tornDownMs") or 0, cs.get("loadedMs") or 0
    if not (lat > 0 and td >= lat and ld >= td):
        f.append(f"client stage latchedMs/tornDownMs/loadedMs={lat}/{td}/{ld} (want > 0, >= latched, >= tornDown)")
    if not (isinstance(b2, int) and isinstance(b1, int) and b2 > b1 and ce.get("battleId") == b2):
        f.append(f"battleId host={b2} client={ce.get('battleId')} (want equal and > b1 {b1})")
    if pressed != {"host": "ready", "client": "ready"}:
        f.append(f"stage-2 equip presses {pressed} (want both machines' pre-battle equip screen pressed ready)")
    hq, cq = he.get("equip") or {}, ce.get("equip") or {}
    if hq.get("phase") != "ended" or cq.get("phase") != "ended" or (hq.get("counted") or [])[:2] != [True, True]:
        f.append(f"equip phase host={hq.get('phase')} client={cq.get('phase')} counted={hq.get('counted')} "
                 f"(want ended, ended, seats 0 and 1 counted)")
    for name, b in (("host", hb), ("client", cb)):
        if b.get("turn") != 1 or b.get("missionType") != MISSION_2 or b.get("mapSizeXYZ") != STAGE2_TILES:
            f.append(f"{name} turn/missionType/mapSizeXYZ={b.get('turn')}/{b.get('missionType')}/{b.get('mapSizeXYZ')} "
                     f"(want 1/{MISSION_2}/{STAGE2_TILES})")
        if b.get("xcom") != SEATS_A:
            f.append(f"{name} living X-COM id -> seat {b.get('xcom')} (want the stage-1 survivors {SEATS_A})")
    if hb.get("mapFingerprint") is None or hb.get("mapFingerprint") != cb.get("mapFingerprint"):
        f.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client={cb.get('mapFingerprint')!r} (want equal)")
    if SEATS_A.get(cb.get("selectedId")) != 1:
        f.append(f"client selectedId={cb.get('selectedId')} (want one of its own seat-1 soldiers)")
    try:
        assert_hash_clean(host, client, full=True, what="stage 2 turn 1")
    except AssertionError as e:
        f.append(f"hash at stage-2 turn 1: {short(e, 500)}")
    pw = session.pick_and_walk(host, client, WALKER, "MS1 stage-2 walk")
    hp, cp = bview(host).get("pos", {}).get(WALKER), bview(client).get("pos", {}).get(WALKER)
    ctx["walk"] = {"result": pw is not None, "from": hb.get("pos", {}).get(WALKER), "host": hp, "client": cp}
    if pw is None or hp != cp or hp == hb.get("pos", {}).get(WALKER):
        f.append(f"client soldier {WALKER} walk: ordered={pw is not None} pos before={ctx['walk']['from']} "
                 f"host={hp} client={cp} (want a walk applied on both)")
    for name, gc in (("host", host), ("client", client)):
        if eview(gc).get("desyncSeen") is not False:
            f.append(f"{name} desyncSeen true after the stage")
    ctx["research2"] = {"seat1": eview(host).get("seat1Research"), "live": eview(host).get("liveResearch")}
    return f, {"pressed": pressed, "host": {"event": he, "battle": hb}, "client": {"event": ce, "battle": cb}}


def ms1(host, client, ctx, crash0):
    fails = ms1_trigger(host, client, ctx)
    if fails:
        evidence("MS1", {"guards": fails, "ctx": ctx})
        return [f"pre-stage: {m}" for m in fails]
    fails = ms1_entry(host, client, ctx)
    green = {}
    if not fails:
        ctx["inStage2"] = True
        try:
            fails, green = ms1_green(host, client, ctx)
        except Exception as e:
            fails = [f"stage-2 spine / cells: {short(e, 600)}"]
    # host liveness and crash files are GREEN cells once stage 2 is reached; before it (the red, T0-3: the host died
    # at 1 / 5 / 36 s after the close) they are EVIDENCE only
    new_crash = sorted(os.path.basename(p) for p in session._crash_log_snapshot() - crash0)
    if ctx.get("inStage2") and rc(host) is not None:
        fails.append(f"host process exited rc={rc(host)}")
    if ctx.get("inStage2") and new_crash:
        fails.append(f"new crash file(s) {new_crash}")
    evidence("MS1", {"b1": ctx.get("b1"), "S": ctx.get("S"), "entry": ctx.get("entry"),
                     "clientBriefingS": ctx.get("clientBriefingS"), "spineS": ctx.get("spineS"), "green": green,
                     "walk": ctx.get("walk"), "hostRc": rc(host), "newCrashFiles": new_crash,
                     "M1research": {"stage1": ctx.get("research1"), "stage2": ctx.get("research2"),
                                    "note": "evidence only (T0-6: seats[1].count == liveCount)"}})
    return fails


# ===================== MS4 =====================


def ms4(host, client, ctx):
    hst, cst = stack(host), stack(client)
    pre = []
    if not ctx.get("inStage2"):
        pre.append("MS1 never reached stage 2")
    for name, gc, st in (("host", host, hst), ("client", client, cst)):
        if rc(gc) is not None:
            pre.append(f"{name} process exited rc={rc(gc)}")
        elif not (isinstance(st, list) and st and st[-1] == "BattlescapeState"):
            pre.append(f"{name} top is not BattlescapeState: {st}")
        elif bview(gc).get("missionType") != MISSION_2 or eview(gc).get("battleId") != ctx.get("b2"):
            pre.append(f"{name} missionType={bview(gc).get('missionType')!r} battleId={eview(gc).get('battleId')} "
                       f"(want {MISSION_2!r}, b2 {ctx.get('b2')})")
    if pre:
        evidence("MS4", {"precondition": pre, "hostStack": hst, "clientStack": cst})
        return [f"precondition 'in stage 2' missing: {'; '.join(pre)}"]
    m = [host, client]
    step("1 drop_client_mid_battle", lambda: drop_client_mid_battle(host, client), m)
    client2 = ctx["client2"] = GameClient("rejoin", None, make_user_dir("mga_ms_a_rejoin"))
    step("3 client2 spawn and connect", lambda: (client2.spawn(), client2.connect()), m)
    step("4 rejoin_skirmish", lambda: rejoin_skirmish(client2, PORT_A), m)

    def held():
        client2.wait_for("client2 back in the battle", lambda: in_battle_save(client2) or None, timeout=240)
        client2.wait_for("client2 held on dialog 68 over BattlescapeState",
                         lambda: (has_bstate(stack(client2))
                                  and dialog(client2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None,
                         timeout=60, interval=0.5)

    def offered():
        if session.has_state(host, "Profile"):
            return host.cmd({"cmd": "profile_ok"}) and None
        return dialog(host).get("backVisible") or None

    def resume():
        assert dialog(host).get("code") == COOP_DLG_WAIT_PLAYERS, f"host dialog {dialog(host)}"
        host.ok({"cmd": "coop_dialog_back"})
        for gc in (host, client2):
            gc.wait_for(f"{gc.name} top BattlescapeState", lambda gc=gc: (stack(gc)[-1] == "BattlescapeState") or None,
                        timeout=120, interval=0.5)
            gc.wait_for(f"{gc.name} phase Active", lambda gc=gc: (battle_state(gc).get("phase") == "Active") or None,
                        timeout=120, interval=0.5)

    step("5 client2 in the battle, held on dialog 68", held, m + [client2])
    step("6 host offers RESUME", lambda: host.wait_for("host dialog offers RESUME", offered, timeout=120,
                                                         interval=0.5), m + [client2])
    step("7 RESUME, both tops BattlescapeState, phase Active", resume, m + [client2])
    step("9 wait_host_idle(host, client2)", lambda: session.wait_host_idle(host, client2, timeout=IDLE_S),
         m + [client2])
    hb, c2b = bview(host), bview(client2)
    he, c2e = eview(host), eview(client2)
    f = []
    if c2b.get("missionType") != MISSION_2:
        f.append(f"client2 missionType={c2b.get('missionType')!r} (want {MISSION_2!r})")
    if not (he.get("battleId") == c2e.get("battleId") == ctx.get("b2")):
        f.append(f"battleId host={he.get('battleId')} client2={c2e.get('battleId')} (want b2 {ctx.get('b2')} kept)")
    if not (hb.get("mapFingerprint") == c2b.get("mapFingerprint") == ctx.get("fp2")):
        f.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client2={c2b.get('mapFingerprint')!r} "
                 f"(want MS1's stage-2 print {ctx.get('fp2')!r})")
    try:
        assert_hash_clean(host, client2, full=True, what="after the stage-2 rejoin")
    except AssertionError as e:
        f.append(f"hash after the rejoin: {short(e, 500)}")
    for name, e in (("host", he), ("client2", c2e)):
        if e.get("desyncSeen") is not False:
            f.append(f"{name} desyncSeen={e.get('desyncSeen')} (want false)")
    evidence("MS4", {"host": {"battle": hb, "event": he}, "client2": {"battle": c2b, "event": c2e}})
    return f


# ===================== main =====================


def main():
    t0 = time.time()
    results, ctx = {}, {}
    host = GameClient("host", GC_PORTS[0], make_user_dir("mga_ms_a_host"))
    client = GameClient("client", GC_PORTS[1], make_user_dir("mga_ms_a_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            info = boot_a(host, client)
            print(f"[mga-a1] boot A ok: {info}", flush=True)
        except Exception as e:
            capture("boot", [host, client], short(e, 600))
            for rid in ("MS1", "MS4"):
                results[rid] = False
                print(f"FAIL {rid}: boot (FIXTURE-STOP) {short(e, 600)}", flush=True)
            return 2
        for rid, fn in (("MS1", lambda: ms1(host, client, ctx, crash0)), ("MS4", lambda: ms4(host, client, ctx))):
            try:
                fails = fn()
            except FixtureMiss as e:
                fails = [f"FIXTURE-STOP {e}"]
            except Exception as e:
                fails = [short(e, 600)]
            results[rid] = not fails
            if fails:
                print(f"FAIL {rid}: {len(fails)} cell(s): " + " | ".join(fails), flush=True)
                capture(rid, [g for g in (host, client, ctx.get("client2")) if g is not None], "row failed")
            else:
                print(f"PASS {rid}", flush=True)
    finally:
        for gc in [g for g in (host, client, ctx.get("client2")) if g is not None]:
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[mga-a1] shutdown {gc.name}: {short(e)}", flush=True)
    order = ["MS1", "MS4"]
    passed = [r for r in order if results.get(r)]
    failed = [r for r in order if not results.get(r)]
    print(f"\ntest_w2_multistage: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
