"""W2-P7 S-A - test_w2_battle_end.py: when a co-op battle ends on the host, the
host sends one terminal `battle_end` event and the skirmish client leaves the
battle with it (spec rewrite/prompts/w2p7_battle_end.md sections (a), (b)2-6,
(b)9, (f) and the W2-P7 plan review's section 2 assertion map and PINNED S-A
stage text; AMENDMENT P7-1 rulings ST1-ST8; owner ruling D129 = (a)).

Today only the host leaves: the host reaches its DebriefingState and the
client stays on the battle map (F387, F431; TASK 0 T0-1 = F1980/F1981). After
stage S-A the host's one hook at the top of BattlescapeState::finishBattle
emits `battle_end` {reason, aborted, inExitArea, perSeatVerdict, tally, h}
through CoopEmit::sendEv; the client's applier only records it and arms a
latch, and the pump consumer after the drain takes the teardown snapshots and
sends the client to GoToMainMenuState (never from the apply path). Two rows,
ONE boot each (one ending per boot):

  E1  T1, the last alien down, battleAutoEnd OFF (the default). The host runs
      battle_action kill_unit_real on A (the default map's only alien; ST7 (a),
      the W2-P2 SB1 lever), then END TURN client then host, then the host
      closes its NextTurnState (dismiss_popup -> NextTurnState::close ->
      finishBattle(false, liveSoldiers)). Expected record (T0-2, F1982):
      reason aliensDown, aborted false, inExitArea 7, verdict win for seats 0
      and 1, tally {liveAliens 0, liveSoldiers 7, inExit 0}.
  E2  T6, the host aborts. battle_action abort -> AbortMissionState ->
      dismiss_popup (AbortMissionState::btnOkClick -> setAborted(true) +
      finishBattle(true, inExit)). Expected record (T0-2, F1983): reason abort,
      aborted true, inExitArea 0, verdict abort for seats 0 and 1, tally
      {liveAliens 1, liveSoldiers 7, inExit 0}.

The `battleEnd` record (event_state.battleEnd, CoopDelta.h) is SESSION-
LIFETIME (ST4 (a), F1895): cleared only by initBattleAuthority(), so it is
still readable after both machines' disconnect resets at a skirmish end.

Pre-ending checks (every row; a failure here is a bring-up or staging failure,
reported with the prefix "pre-ending", never the row's verdict): the pinned
map (MAP_FP), pin_ai_neutral, hash_now {full:true} ALL buckets EQUAL on both
machines right before the ending action, desyncSeen false on both, the host's
coopClientBStatePushes 0, the client's read as b0, both machines' battleEnd
record present with emitted 0 and applied 0. The ending's own steps (END TURN
presses, the host's NextTurnState / AbortMissionState confirm) and the host's
DebriefingState within DEBRIEF_S are reported with the prefix "ending".

Row verdict (the S-A assertion set, review section 2):
  host    battleEnd emitted 1, seq > 0, reason / aborted / inExitArea /
          perSeatVerdict / tally as the row expects, actionIdAtEmit 0,
          evsAfter 0, stageSkips 0, hBuckets = the 9 action-end bucket names
          (8 structured + saveBlob); quiescentAtEmit is recorded only (F1911);
          the host's stack still holds DebriefingState (its top is NOT asserted:
          F1896, D156 - S-B owns the host's popup rule); coopClientBStatePushes
          0 and desyncSeen false.
  client  battleEnd applied 1 with the host's seq and the row's reason /
          aborted / inExitArea / perSeatVerdict / tally, skirmish true,
          teardownInDrain false, latchedMs > 0 and tornDownMs >= latchedMs
          (F1909: latch and teardown share one pump pass), desyncAtTeardown
          false, bstatePushesAtTeardown == b0, queueDepthAtTeardown 0,
          lastSeqApplied == the host's seq, hashVerify {seq = the host's seq,
          kind battle_end, buckets = the host's hBuckets}; top MainMenuState
          within CLIENT_LEAVE_S of the host's DebriefingState, world_state
          has_save false, battle_state inBattle false, event_state phase Idle.
  both    no client save file (assert_client_zero_disk), no new crash log.

RED-THEN-GREEN (spec (d), review section 3 DONE-WHEN). Commit S-A.1 (this file,
the battleEnd record + its reader, the drain-depth and evsAfter probes, the
teardown snapshot, the set_option battleAutoEnd lever - no product behaviour)
is run ONCE: each row fails on host battleEnd.emitted 0 AND the client still in
battle (inBattle true, top BattlescapeState or NextTurnState) CLIENT_LEAVE_S
after the host's DebriefingState, with every pre-ending check passing. Commit
S-A.2 (the product) is run ONCE and both rows pass. Each row prints ONE
"EVIDENCE <id>:" line with both machines' records, tops and the pre-ending
census BEFORE its verdict is checked; main() runs every row even after an
earlier one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait
is bounded; a wait that runs out is recorded and fails the row.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot per
row, no alternative map or actor. Exit 0 only when both rows pass, 2 otherwise.

Run:  python tools/coop_test/test_w2_battle_end.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw

# ----- the default NEW BATTLE map, pinned (W2-P2 TASK 0a round 1; test_w2_delta_items) -----
SEED_MAP = 1
MAP_FP = -4.48310638993e+18      # host battle_state.mapFingerprint on SEED_MAP 1
A_ID = 1000000                   # the only alien: Sectoid Soldier, spawn (27,12,0) dir 5, health 30
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus

# ----- W2-P7 constants -----
# The `h` every bt_action_end carries (coopBuildActionEndHash): the 8 structured
# buckets (SharedEcon battleHashBucketName) + saveBlob.
H_BUCKETS = sorted(["terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr", "synced",
                    "saveBlob"])
DEBRIEF_S = 30        # host DebriefingState after the ending's confirm (T0-1: <= 0.05 s)
CLIENT_LEAVE_S = 30   # client MainMenuState after the host's DebriefingState (review section 2)
ROW_EXPECT = {
    # T0-2 (F1982): finishBattle(false, 7) from NextTurnState::close, isAborted() false.
    "E1": {"reason": "aliensDown", "aborted": False, "inExitArea": 7,
           "verdicts": [(0, "win"), (1, "win")],
           "tally": {"liveAliens": 0, "liveSoldiers": 7, "inExit": 0}},
    # T0-2 (F1983): finishBattle(true, 0) from AbortMissionState::btnOkClick, isAborted() true.
    "E2": {"reason": "abort", "aborted": True, "inExitArea": 0,
           "verdicts": [(0, "abort"), (1, "abort")],
           "tally": {"liveAliens": 1, "liveSoldiers": 7, "inExit": 0}},
}
ROW_PORT = {"E1": "48766", "E2": "48767"}
IN_BATTLE_TOPS = ("BattlescapeState", "NextTurnState")


# ===================== small probes =====================


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 300 else s[:300] + "..."


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval):
    """Poll `pred` until truthy or `timeout` seconds pass. Returns (ok, seconds)."""
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def record(gc):
    """This machine's event_state.battleEnd (None when the field is absent)."""
    return event_state(gc).get("battleEnd")


def verdicts(rec):
    pv = (rec or {}).get("perSeatVerdict") or []
    return sorted((e.get("seat"), e.get("verdict")) for e in pv if isinstance(e, dict))


def tally(rec):
    t = (rec or {}).get("tally") or {}
    return {k: t.get(k) for k in ("liveAliens", "liveSoldiers", "inExit")}


def machine_view(gc):
    es = event_state(gc)
    bs = battle_state(gc)
    ws = gc.cmd({"cmd": "world_state"})
    return {"top": top(gc), "stack": stack(gc), "inBattle": bs.get("inBattle"), "phase": es.get("phase"),
            "desyncSeen": es.get("desyncSeen"), "bstatePushes": es.get("coopClientBStatePushes"),
            "lastSeqEmitted": es.get("lastSeqEmitted"), "lastSeqApplied": es.get("lastSeqApplied"),
            "queueDepth": es.get("queueDepth"), "hasSave": ws.get("has_save"), "battleEnd": es.get("battleEnd")}


def host_chain_done(host):
    """HOST only: A is DEAD, no BState is queued or running, BattlescapeState on top."""
    bs = battle_state(host)
    a = session.units_by_id(bs).get(A_ID) or {}
    return (a.get("status") == STATUS_DEAD and bs.get("pendingStates") == 0 and not bs.get("isBusy")
            and top(host) == "BattlescapeState")


# ===================== the rows' staging and endings =====================


def stage_e1(host, client, pre):
    """E1 staging: the host kills A (the map's only alien) through the real
    UnitDieBState chain and both machines settle."""
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": A_ID})
    if not r.get("ok") or r.get("killed") != [A_ID]:
        pre.append(f"kill_unit_real answered {r} (want ok, killed [{A_ID}])")
    ok, secs = wait_until(lambda: host_chain_done(host), 30, 0.1)
    if not ok:
        pre.append(f"host kill chain not finished (A DEAD, no BState, BattlescapeState on top) within {secs}s")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        pre.append(f"wait_host_idle after the kill: {short(e)}")
    return {"kill": r, "chainS": secs}


def end_e1(host, client, ending):
    """E1 ending: END TURN client then host; the host's NextTurnState closes
    (NextTurnState::close -> finishBattle)."""
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        ending.append(f"client end_turn_button: {short(e)}")
    ok, secs = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20, 0.1)
    if not ok:
        ending.append(f"host never painted END TURN 1/2 after the client's press ({secs}s)")
    try:
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
    except Exception as e:
        ending.append(f"host end_turn_button: {short(e)}")
    ok, secs = wait_until(lambda: "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", ""), 30, 0.1)
    if not ok:
        ending.append(f"host NextTurnState not up within {secs}s after both END TURN presses")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "NextTurnState->close":
        ending.append(f"host dismiss_popup answered {d} (want handled NextTurnState->close)")
    return {"close": d}


def stage_e2(host, client, pre):
    """E2 staging: none (the abort ends the battle as it stands)."""
    return {}


def end_e2(host, client, ending):
    """E2 ending: the host's abort and its confirm (AbortMissionState::btnOkClick
    -> setAborted(true) + finishBattle(true, inExit))."""
    try:
        host.ok({"cmd": "battle_action", "action": "abort"})
    except Exception as e:
        ending.append(f"host battle_action abort: {short(e)}")
    ok, secs = wait_until(lambda: any("AbortMissionState" in s for s in stack(host)), 30, 0.1)
    if not ok:
        ending.append(f"host AbortMissionState not up within {secs}s")
    d = host.cmd({"cmd": "dismiss_popup"})
    if d.get("handled") != "AbortMissionState":
        ending.append(f"host dismiss_popup answered {d} (want handled AbortMissionState)")
    return {"confirm": d}


# ===================== one row =====================


def pre_census(host, client, pre):
    """The pre-ending census: hash clean, desync, b0, host pushes, both records at zero."""
    census = {}
    try:
        hh, _ch = assert_hash_clean(host, client, full=True, what="before the ending")
        census["hashBuckets"] = sorted(hh.keys())
    except AssertionError as e:
        pre.append(f"hash_now full before the ending: {e}")
    census["host"] = machine_view(host)
    census["client"] = machine_view(client)
    for name in ("host", "client"):
        v = census[name]
        if v["desyncSeen"] is not False:
            pre.append(f"{name} desyncSeen={v['desyncSeen']} before the ending (want false)")
        rec = v["battleEnd"]
        if not isinstance(rec, dict) or rec.get("emitted") != 0 or rec.get("applied") != 0:
            pre.append(f"{name} battleEnd before the ending = {rec} (want the record with emitted 0, applied 0)")
    if census["host"]["bstatePushes"] != 0:
        pre.append(f"host coopClientBStatePushes={census['host']['bstatePushes']} before the ending (want 0)")
    census["b0"] = census["client"]["bstatePushes"]
    if not isinstance(census["b0"], int):
        pre.append(f"client coopClientBStatePushes={census['b0']!r} before the ending (want an int)")
    return census


def census_view(c):
    return {"hashBuckets": c.get("hashBuckets"), "b0": c.get("b0"),
            **{f"{n}": {k: c[n][k] for k in ("top", "inBattle", "phase", "desyncSeen", "bstatePushes",
                                               "lastSeqEmitted", "lastSeqApplied", "queueDepth")}
               for n in ("host", "client")}}


def row_verdict(rid, expect, hrec, crec, cend, hend, b0, cleft, extra):
    """Every S-A assertion of the row; returns the list of failures (empty = pass)."""
    f = []
    hrec = hrec if isinstance(hrec, dict) else {}
    crec = crec if isinstance(crec, dict) else {}
    # --- the named red's two halves first: the host's emission, the client's leave ---
    if hrec.get("emitted") != 1:
        f.append(f"host battleEnd.emitted={hrec.get('emitted')} (want 1)")
    if not cleft["ok"]:
        f.append(f"client still in battle {cleft['secs']}s after the host's DebriefingState: top={cend['top']} "
                 f"inBattle={cend['inBattle']} (want MainMenuState within {CLIENT_LEAVE_S}s)")
    # --- host record ---
    hseq = hrec.get("seq")
    if not isinstance(hseq, int) or hseq <= 0:
        f.append(f"host battleEnd.seq={hseq} (want > 0)")
    for k in ("reason", "aborted", "inExitArea"):
        if hrec.get(k) != expect[k]:
            f.append(f"host battleEnd.{k}={hrec.get(k)!r} (want {expect[k]!r})")
    if verdicts(hrec) != expect["verdicts"]:
        f.append(f"host battleEnd.perSeatVerdict={hrec.get('perSeatVerdict')} (want {expect['verdicts']})")
    if tally(hrec) != expect["tally"]:
        f.append(f"host battleEnd.tally={hrec.get('tally')} (want {expect['tally']})")
    for k, want in (("actionIdAtEmit", 0), ("evsAfter", 0), ("stageSkips", 0)):
        if hrec.get(k) != want:
            f.append(f"host battleEnd.{k}={hrec.get(k)} (want {want})")
    if sorted(hrec.get("hBuckets") or []) != H_BUCKETS:
        f.append(f"host battleEnd.hBuckets={hrec.get('hBuckets')} (want {H_BUCKETS})")
    if not any("DebriefingState" in s for s in hend["stack"]):
        f.append(f"host stack {hend['stack']} holds no DebriefingState")
    if hend["bstatePushes"] != 0:
        f.append(f"host coopClientBStatePushes={hend['bstatePushes']} (want 0)")
    if hend["desyncSeen"] is not False:
        f.append(f"host desyncSeen={hend['desyncSeen']} (want false)")
    # --- client record ---
    if crec.get("applied") != 1:
        f.append(f"client battleEnd.applied={crec.get('applied')} (want 1)")
    if crec.get("seq") != hseq:
        f.append(f"client battleEnd.seq={crec.get('seq')} (want the host's {hseq})")
    for k in ("reason", "aborted", "inExitArea"):
        if crec.get(k) != expect[k]:
            f.append(f"client battleEnd.{k}={crec.get(k)!r} (want {expect[k]!r})")
    if verdicts(crec) != expect["verdicts"]:
        f.append(f"client battleEnd.perSeatVerdict={crec.get('perSeatVerdict')} (want {expect['verdicts']})")
    if tally(crec) != expect["tally"]:
        f.append(f"client battleEnd.tally={crec.get('tally')} (want {expect['tally']})")
    for k, want in (("skirmish", True), ("teardownInDrain", False), ("desyncAtTeardown", False),
                    ("queueDepthAtTeardown", 0)):
        if crec.get(k) != want:
            f.append(f"client battleEnd.{k}={crec.get(k)!r} (want {want!r})")
    lat, tdn = crec.get("latchedMs"), crec.get("tornDownMs")
    if not isinstance(lat, int) or lat <= 0 or not isinstance(tdn, int) or tdn < lat:
        f.append(f"client battleEnd latchedMs={lat} tornDownMs={tdn} (want latchedMs > 0, tornDownMs >= latchedMs)")
    if crec.get("bstatePushesAtTeardown") != b0:
        f.append(f"client battleEnd.bstatePushesAtTeardown={crec.get('bstatePushesAtTeardown')} (want b0 {b0})")
    if crec.get("lastSeqApplied") != hseq:
        f.append(f"client battleEnd.lastSeqApplied={crec.get('lastSeqApplied')} (want the host's seq {hseq})")
    hv = crec.get("hashVerify") if isinstance(crec.get("hashVerify"), dict) else {}
    if (hv.get("seq") != hseq or hv.get("kind") != "battle_end"
            or sorted(hv.get("buckets") or []) != sorted(hrec.get("hBuckets") or [])):
        f.append(f"client battleEnd.hashVerify={crec.get('hashVerify')} (want seq {hseq}, kind battle_end, "
                 f"buckets = the host's hBuckets)")
    # --- client end state ---
    if cend["top"] != "MainMenuState":
        f.append(f"client top={cend['top']} (want MainMenuState)")
    if cend["hasSave"] is not False:
        f.append(f"client world_state.has_save={cend['hasSave']} (want false)")
    if cend["inBattle"] is not False:
        f.append(f"client battle_state.inBattle={cend['inBattle']} (want false)")
    if cend["phase"] != "Idle":
        f.append(f"client event_state.phase={cend['phase']} (want Idle)")
    f += extra
    return f


def run_row(rid, stage_fn, end_fn, results):
    expect = ROW_EXPECT[rid]
    host = GameClient("host", 49892, make_user_dir(f"w2p7_battle_end_{rid}_host"))
    client = GameClient("client", 49893, make_user_dir(f"w2p7_battle_end_{rid}_client"))
    try:
        try:
            boot(host, client, ROW_PORT[rid])
        except Exception as e:
            results[rid] = False
            print(f"FAIL {rid}: pre-ending (bring-up) {short(e)}", flush=True)
            return
        try:
            pre, ending = [], []
            staging = stage_fn(host, client, pre)
            census = pre_census(host, client, pre)
            crash0 = session._crash_log_snapshot()
            t_end = time.time()
            ending_resp = end_fn(host, client, ending)
            deb_ok, deb_s = wait_until(lambda: any("DebriefingState" in s for s in stack(host)), DEBRIEF_S, 0.1)
            if not deb_ok:
                ending.append(f"host DebriefingState not reached within {deb_s}s of the ending's confirm")
            deb_after = round(time.time() - t_end, 2)
            left_ok, left_s = wait_until(lambda: top(client) == "MainMenuState", CLIENT_LEAVE_S, 0.25)
            cleft = {"ok": left_ok, "secs": left_s}
            hend, cend = machine_view(host), machine_view(client)
            crash1 = session._crash_log_snapshot()
            extra = []
            new_crash = sorted(crash1 - crash0)
            if new_crash:
                extra.append(f"new crash log(s): {new_crash}")
            try:
                session.assert_client_zero_disk(client.user_dir)
            except AssertionError as e:
                extra.append(str(e))
            hrec, crec = hend.pop("battleEnd"), cend.pop("battleEnd")
            print(f"EVIDENCE {rid}: host DebriefingState reached={deb_ok} after {deb_s}s ({deb_after}s from the "
                  f"ending's first step); host battleEnd.emitted={(hrec or {}).get('emitted')}; client at the "
                  f"end of the {CLIENT_LEAVE_S}s window: left={left_ok} after {left_s}s top={cend['top']} "
                  f"inBattle={cend['inBattle']}; pre-ending fails={pre}; ending fails={ending}; "
                  f"staging={staging}; ending={ending_resp}; pre-ending census={census_view(census)}; "
                  f"host battleEnd={hrec}; client battleEnd={crec}; host end={hend}; client end={cend}; "
                  f"newCrashLogs={new_crash}", flush=True)
            fails = [f"pre-ending: {m}" for m in pre] + [f"ending: {m}" for m in ending]
            fails += row_verdict(rid, expect, hrec, crec, cend, hend, census.get("b0"), cleft, extra)
            if fails:
                raise AssertionError(f"{len(fails)} failure(s): " + " | ".join(fails))
            results[rid] = True
            print(f"PASS {rid}", flush=True)
        except Exception as e:
            results[rid] = False
            kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
            print(f"FAIL {rid}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p7-sa] shutdown {gc.name}: {short(e)}", flush=True)


# ===================== bring-up =====================


def boot(host, client, port):
    """The classic parallel skirmish bring-up (raw.bring_up_lobby +
    session.drive_to_battlescape, seat_count=2), pinned with set_seed SEED_MAP
    right before newbattle_ok, asserted against the baked MAP_FP, then
    session.pin_ai_neutral (A cannot act), then hash-clean (W2-P2 SB1's boot)."""
    raw.bring_up_lobby(host, client, port)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p7-sa")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p7-sa] boot ok: MAP_FP={MAP_FP!r} turn={hs.get('turn')} pinned={pinned}", flush=True)


# ===================== main =====================


ROWS = (("E1", stage_e1, end_e1), ("E2", stage_e2, end_e2))


def main():
    t0 = time.time()
    results = {}
    for rid, stage_fn, end_fn in ROWS:
        run_row(rid, stage_fn, end_fn, results)
    order = [r[0] for r in ROWS]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_battle_end: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
