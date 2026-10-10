#!/usr/bin/env python
"""RV-U7 - test_shared_autoend_crashsite.py: a SHARED craft that lands on a crashed UFO whose crew died at generation
ends cleanly for both players on the rewrite (POST-REWRITE-REVISIT row 18; owner D123, D229 (a) + gate, D210 (b), D156
(a); P8b-1 V4; spec docs rewrite/prompts/rvu7_autoend_crash_proof.md; constants docs rewrite/rvu7-task0/CONSTANTS.md).

In August a player's SHARED game crashed on such a landing: the old SHARED mission start set the host's battle screen
up without showing it, the empty battle ended at once and BattlescapeState::finishBattle popped an empty state stack
(0xC0000374 heap corruption, host only); main fixed it in #154 (c93d1ad4d). The rewrite shows every battle screen it
sets up, and a battle that starts with no live alien goes to vanilla's AliensCrashState on both machines (D210 (b),
P8b-1 V4). This file lands there from the player's own SHARED save, fixtures/auto_end_crash.sav (its Skyranger flies
to the crashed UFO 23), through the rewrite's SHARED resume and landing.

Row R18 (ONE boot). Pre-cell (a miss is a FIXTURE-STOP: one CAPTURE line, then "FAIL R18: pre-cell ..."):
  P1  session.resume_campaign on the fixture; both tops GeoscapeState; save_markers.campaignType 1 on both.
  P2  host geo_set_speed {idx 2} every 0.5 s until ConfirmLandingState is on the host's stack (<= LAND_S).
  P3  [set_seed SEED when pinned] host confirm_landing; host inBattle (<= 180 s); host BriefingState (<= 60 s).
  P4  the host's faction-1 units at its BriefingState == CREW_IDS, every one dead at generation (health <= 0, or
      stun >= health, or isOut).
  P5  the client's BriefingState (<= 30 s); host phase Active (<= 30 s); client close_briefing -> CLIENT_SCREEN on
      top (<= 5 s); the host's top still BriefingState; host battleEnd.emitted 0.
Cells (in order; a failed cell ends the row, later cells "not reached"):
  C1  host close_briefing -> its top AliensCrashState (<= 5 s); no host stack sample since P3 held a
      BattlescapeState; host battleEnd emitted 1, reason aliensCrashed.
  C2  the host's OK (handled AliensCrashState) -> its DebriefingState (<= 10 s); resultSent 1 (<= 5 s).
  C3  the client's top AliensCrashState within 20 s of the host's DebriefingState; its OK (handled AliensCrashState)
      -> its debriefing on top, display-only (<= 10 s); worldAdopted 1 (<= 15 s); shared_checksum chk* equal.
  C4  both OKs (test_w2_battle_end_campaign's client_ok_clean / host_ok_drain) -> both on GeoscapeState, no CoopState.
Guards: no new crash file (none with 0xC0000374 / finishBattle); both processes alive; host fatalVote.armed 0; the
client zero-disk. Prints ONE "EVIDENCE R18:" line, then "PASS R18" or "FAIL R18: <message>". WV-D95: run in the
foreground to completion. WV-D99 / WV-D100: ONE run, no skip path; exit 0 only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_shared_autoend_crashsite.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients
import session
from session import battle_state, event_state
import test_w2_battle_end_campaign as camp

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "auto_end_crash.sav")
SAVE = os.path.basename(FIXTURE)
PORT = "47943"                      # this file's lobby key (unique in tools/coop_test, F10753)
HOST_LABEL, CLIENT_LABEL = 49668, 49669

# ----- TASK 0 pins (docs rewrite/rvu7-task0/CONSTANTS.md: boots A1 = A2 on the fixture's own RNG) -----
SEED = None                         # the fixture's own RNG kills the whole crew at generation (no seed hunt needed)
CREW_IDS = [1000001, 1000002, 1000003, 1000004, 1000005]   # 3 snakeman soldiers + 2 navigators, health 0 on both boots
CLIENT_SCREEN = "InventoryState"    # the client's seat owns 5 soldiers aboard: its pre-battle equip screen (D215 a)
LAND_S = 66                         # P2: 32.68 s on A1 and A2, x 2

ENTER_S, HOST_BRIEF_S = 180, 60     # P3: session.bring_up_shared_mixed_battle's bounds
BRIEF_S, ACTIVE_S, SCREEN_S = 30, 30, 5   # P5: test_w2_prebattle_equip_end's EQ1 / ACTIVE / ENTRY waits
CRASH_HOST_S, DEBRIEF_S, RESULT_S = 5, 10, 5   # C1 / C2: test_w2_prebattle_equip_end's CRASH / DEBRIEF / RESULT waits
CRASH_S = 20                        # C3: the client's AliensCrashState after the host's DebriefingState (SCR row D1d)
ADOPT_S = camp.ADOPT_S              # 15 s
FACTION_HOSTILE = 1
CRASH_SIGNATURES = ("0xC0000374", "finishBattle")   # #154's crash signature in a crash_*.log
REC_KEYS = ("emitted", "applied", "seq", "reason", "aborted", "tally", "resultSent", "resultReceived", "returnPending",
            "worldPushed", "worldHeld", "worldAdopted", "debriefDisplayOnly", "debriefCampaign", "debriefOkBranch")
short, record, stack = camp.short, camp.record, session.states_stripped


class FixtureMiss(Exception):
    pass


def top(gc):
    return (stack(gc) or [None])[-1]


def rec_keys(gc):
    r = record(gc)
    return {k: r.get(k) for k in REC_KEYS}


# The host's stack is sampled on every wait round from P3 to C1 (C1: no sample may hold a BattlescapeState).
SAMPLES = {"host": None, "on": False, "t0": 0.0, "n": 0, "bs": 0, "log": [], "last": None}


def sample():
    if not SAMPLES["on"]:
        return
    st = stack(SAMPLES["host"])
    SAMPLES["n"] += 1
    SAMPLES["bs"] += int(any("BattlescapeState" in s for s in st))
    if st != SAMPLES["last"]:
        SAMPLES["log"].append([round(time.time() - SAMPLES["t0"], 2), st])
        SAMPLES["last"] = st


def wait_until(pred, timeout, interval=0.1):
    """Poll `pred` (bounded), sampling the host's stack each round. Returns (ok, seconds)."""
    t0 = time.time()
    while True:
        sample()
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def crew(gc):
    return [{k: u.get(k) for k in ("id", "type", "health", "stun", "status", "isOut")}
            for u in battle_state(gc).get("units", []) or [] if u.get("faction") == FACTION_HOSTILE]


def dead(u):
    h, s = u.get("health"), u.get("stun")
    return (isinstance(h, int) and (h <= 0 or (isinstance(s, int) and s >= h))) or u.get("isOut") is True


def capture(name, err, machines):
    """FIXTURE-STOP: one CAPTURE line (both machines' stacks, event_state, battle_state flags, debrief_state)."""
    cap = {}
    for gc in machines:
        try:
            bs = battle_state(gc)
            cap[gc.name] = {"stack": stack(gc), "event_state": event_state(gc),
                            "battle": {k: bs.get(k) for k in ("inBattle", "turn", "phase", "mapFingerprint")},
                            "debrief": gc.cmd({"cmd": "debrief_state"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err[:600]}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


def pre_cell(host, client, ctx):
    m = (host, client)
    t = time.time()
    try:
        session.resume_campaign(host, client, SAVE, port=PORT)
    except Exception as e:
        capture("P1 resume", short(e, 800), m)
    ct = {gc.name: gc.cmd({"cmd": "save_markers"}).get("campaignType") for gc in m}
    ctx["P1"] = {"secs": round(time.time() - t, 2), "host": stack(host), "client": stack(client), "campaignType": ct}
    if top(host) != "GeoscapeState" or top(client) != "GeoscapeState" or ct != {"host": 1, "client": 1}:
        capture("P1 resume", f"{ctx['P1']} (want both tops GeoscapeState, campaignType 1 on both)", m)

    def landing():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    g, d = wait_until(landing, LAND_S, 0.5)
    ctx["P2"] = {"landS": d, "host": stack(host), "client": stack(client)}
    if not g:
        capture("P2 landing", f"no ConfirmLandingState on the host within {LAND_S}s ({ctx['P2']})", m)
    SAMPLES.update(on=True, t0=time.time())
    if SEED is not None:
        ctx["seed"] = host.cmd({"cmd": "set_seed", "seed": SEED}).get("seed")
    cl = host.cmd({"cmd": "confirm_landing"})
    g1, d1 = wait_until(lambda: battle_state(host).get("inBattle"), ENTER_S, 0.25)
    g2, d2 = wait_until(lambda: "BriefingState" in stack(host), HOST_BRIEF_S) if g1 else (False, 0)
    ctx["P3"] = {"confirm": {k: cl.get(k) for k in ("ok", "error")}, "inBattleS": d1 if g1 else None,
                 "briefingS": d2 if g2 else None, "host": stack(host), "client": stack(client)}
    if not (cl.get("ok") and g1 and g2):
        capture("P3 enter", f"{ctx['P3']} (want confirm ok, inBattle, the host's BriefingState)", m)
    c = crew(host)
    ctx["P4"] = {"crew": c, "hostTop": top(host)}
    if [u["id"] for u in c] != CREW_IDS or not all(dead(u) for u in c):
        capture("P4 the crew dead at generation", f"host faction-1 units {c} (want ids {CREW_IDS}, every one dead)", m)
    g0, d0 = wait_until(lambda: "BriefingState" in stack(client), BRIEF_S)
    ga, da = wait_until(lambda: event_state(host).get("phase") == "Active", ACTIVE_S)
    cc = client.cmd({"cmd": "close_briefing"}) if g0 else {"error": "no client BriefingState"}
    gs, ds = wait_until(lambda: top(client) == CLIENT_SCREEN, SCREEN_S, 0.05)
    ctx["P5"] = {"clientBriefingS": d0 if g0 else None, "hostActiveS": da if ga else None,
                 "clientClose": {k: cc.get(k) for k in ("ok", "error")}, "clientScreen": top(client),
                 "clientScreenS": ds if gs else None, "clientStack": stack(client), "clientCrew": crew(client),
                 "hostTop": top(host), "hostEmitted": record(host).get("emitted")}
    ctx["loadGamePushes0"] = camp.log_count(client, camp.LOADGAME_PUSH)
    if not (g0 and ga and gs and ctx["P5"]["hostTop"] == "BriefingState" and ctx["P5"]["hostEmitted"] == 0):
        capture("P5 spine", f"{ctx['P5']} (want the client's {CLIENT_SCREEN}, the host Active in its "
                f"BriefingState, emitted 0)", m)


def cells(host, client, ctx):
    def c1():
        hc = host.cmd({"cmd": "close_briefing"})
        g, d = wait_until(lambda: top(host) == "AliensCrashState", CRASH_HOST_S, 0.05)
        sample()
        SAMPLES["on"] = False
        hr = rec_keys(host)
        ctx["C1"] = {"close": {k: hc.get(k) for k in ("ok", "error")}, "secs": d if g else None,
                     "hostStack": stack(host), "samples": SAMPLES["n"], "bsSamples": SAMPLES["bs"], "hostRecord": hr}
        f = [] if g else [f"the host's stack {stack(host)} {CRASH_HOST_S}s after its OK (want top AliensCrashState)"]
        if SAMPLES["bs"]:
            f.append(f"{SAMPLES['bs']} of {SAMPLES['n']} host stack samples since P3 held a BattlescapeState")
        if hr.get("emitted") != 1 or hr.get("reason") != "aliensCrashed":
            f.append(f"host battleEnd {hr} (want emitted 1, reason aliensCrashed)")
        return f

    def c2():
        hp = host.cmd({"cmd": "dismiss_popup"})
        g, d = wait_until(lambda: top(host) == "DebriefingState", DEBRIEF_S, 0.05)
        ctx["hostDebriefAt"] = time.time()
        g2, d2 = wait_until(lambda: record(host).get("resultSent") == 1, RESULT_S, 0.05)
        ctx["C2"] = {"press": {k: hp.get(k) for k in ("ok", "handled", "error")}, "debriefS": d if g else None,
                     "resultSentS": d2 if g2 else None, "hostStack": stack(host), "hostRecord": rec_keys(host)}
        f = [] if hp.get("handled") == "AliensCrashState" else [
            f"the host's OK answered {ctx['C2']['press']} (want handled AliensCrashState)"]
        if not g:
            f.append(f"no host DebriefingState within {DEBRIEF_S}s (stack {stack(host)})")
        if not g2:
            f.append(f"host battleEnd.resultSent={record(host).get('resultSent')!r} after {RESULT_S}s (want 1)")
        return f

    def c3():
        left = max(0.0, CRASH_S - (time.time() - ctx["hostDebriefAt"]))
        g, d = wait_until(lambda: top(client) == "AliensCrashState", left)
        ctx["C3"] = {"secsAfterHostDebrief": round(time.time() - ctx["hostDebriefAt"], 2), "stack": stack(client),
                     "clientRecord": rec_keys(client), "clientCrew": crew(client)}
        if not g:
            return [f"the client's stack {stack(client)} {CRASH_S}s after the host's DebriefingState (want top "
                    f"AliensCrashState)"]
        cp = client.cmd({"cmd": "dismiss_popup"})
        gd, dd = wait_until(lambda: (lambda x: x.get("onTop") is True and x.get("displayOnly") is True)(
            client.cmd({"cmd": "debrief_state"})), DEBRIEF_S)
        ga, da = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
        ctx["C3"].update({"press": {k: cp.get(k) for k in ("ok", "handled", "error")}, "debriefS": dd if gd else None,
                          "adoptS": da if ga else None, "stackAfter": stack(client)})
        f = [] if cp.get("handled") == "AliensCrashState" else [
            f"the client's OK answered {ctx['C3']['press']} (want handled AliensCrashState)"]
        if not gd:
            f.append(f"no client display-only DebriefingState on top within {DEBRIEF_S}s (stack {stack(client)})")
        if not ga:
            f.append(f"client worldAdopted={record(client).get('worldAdopted')!r} after {ADOPT_S}s (want 1)")
        if f:
            return f
        eq, esecs, hc, cc = camp.chk_equal(host, client)
        ctx["C3"]["chk"] = {"equal": eq, "secs": esecs, "host": hc, "client": cc}
        return [] if eq else [f"shared_checksum chk* host {hc} != client {cc}"]

    def c4():
        f = camp.client_ok_clean(client, ctx, "clientOk") + camp.host_ok_drain(host, ctx, "hostOk")
        for gc in (host, client):
            st = stack(gc)
            if not st or st[-1] != "GeoscapeState" or any("CoopState" in s for s in st):
                f.append(f"{gc.name} stack {st} (want top GeoscapeState, no CoopState)")
        return f

    return [("C1 the host's AliensCrashState, no battle screen", c1), ("C2 the host's debriefing", c2),
            ("C3 the client's AliensCrashState and display-only debriefing", c3), ("C4 both on the geoscape", c4)]


def signature(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return any(s in f.read() for s in CRASH_SIGNATURES)
    except OSError:
        return False


def end_view(gc):
    es = event_state(gc)
    return {"stack": stack(gc), "phase": es.get("phase"), "battleEnd": rec_keys(gc),
            "coopBattle": (es.get("researchMode") or {}).get("coopBattle")}


def main():
    t0, ctx, verdict = time.time(), {"row": "R18"}, None
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", HOST_LABEL, make_user_dir("rvu7_host", saves=[FIXTURE]))
    client = GameClient("client", CLIENT_LABEL, make_user_dir("rvu7_client"))
    SAMPLES["host"] = host
    try:
        try:
            host.spawn()
            client.spawn()
            host.connect()
            client.connect()
            pre_cell(host, client, ctx)
        except Exception as e:
            verdict = f"pre-cell (FIXTURE-STOP) {e if isinstance(e, FixtureMiss) else short(e, 800)}"
        if verdict is None:
            cl = cells(host, client, ctx)
            ctx["cells"] = []
            for i, (name, fn) in enumerate(cl):
                try:
                    f = fn()
                except Exception as e:
                    f = [f"{type(e).__name__}: {short(e, 600)}"]
                ctx["cells"].append({"cell": name, "pass": not f, "fails": f})
                if f:
                    rest = [c[0].split(" ")[0] for c in cl[i + 1:]]
                    verdict = f"cell {name}: " + "; ".join(f) + (f" | cells {rest} not reached" if rest else "")
                    break
        ctx["hostSamples"] = SAMPLES["log"]
        g = [f"{gc.name} process gone (rc {gc.proc.poll() if gc.proc else None})" for gc in (host, client)
             if gc.proc is None or gc.proc.poll() is not None]
        try:
            armed = (event_state(host).get("fatalVote") or {}).get("armed")
            ctx["end"] = {gc.name: end_view(gc) for gc in (host, client)}
        except Exception as e:
            armed, ctx["end"] = f"probe failed: {short(e)}", None
        if armed != 0:
            g.append(f"host fatalVote.armed={armed!r} (want 0)")
        try:
            session.assert_client_zero_disk(client.user_dir)
        except AssertionError as e:
            g.append(str(e))
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["crashCensus"] = {"new": new_crash, "signature": [p for p in new_crash if signature(p)]}
        if new_crash:
            g.append(f"new crash file(s) {new_crash} (with 0xC0000374 / finishBattle: "
                     f"{ctx['crashCensus']['signature']})")
        if g:
            verdict = (verdict + " | " if verdict else "") + "guard: " + "; ".join(g)
        ctx.pop("hostDebriefAt", None)
        camp.evidence("R18", ctx)
        print("PASS R18" if verdict is None else f"FAIL R18: {verdict}", flush=True)
    finally:
        try:
            shutdown_clients(host, client)
        except Exception as e:
            print(f"[rvu7] shutdown: {short(e)}", flush=True)
    print(f"\ntest_shared_autoend_crashsite: {0 if verdict else 1}/1 passed in {time.time() - t0:.1f}s", flush=True)
    return 0 if verdict is None else 2


if __name__ == "__main__":
    sys.exit(main())
