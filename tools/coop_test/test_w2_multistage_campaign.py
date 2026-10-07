"""MG-A S-A2 - test_w2_multistage_campaign.py: a SHARED co-op campaign's Cydonia stage change hands stage 2 to both
players (owner D158 (a), D226 (a); spec docs rewrite/prompts/mga_multistage_handoff.md (f) row MS5 as AMENDMENT
MG-A-1 section 5 restates it for stage S-A2, with the M1 research cell (section 3.10, D149); TASK 0 constants docs
rewrite/mga-task0/a2/CONSTANTS.md).

ONE boot (boot D): test_cydonia_coop_start.py's SHARED bring-up - session.new_campaign(campaign_mode="shared") on
lobby PORT_D, the squad split (the host's Skyranger CRAFT_D seats SQUAD_D; set_soldier_owner gives the first to
seat 0 and the second to seat 1 on both machines), discover_research RESEARCH_D on BOTH machines (orchestrator ruling
R-MGA-A2-T-1 (a): a fresh SHARED campaign has no discovered research, F10011, so the M1 cell needs a non-zero count),
open_cydonia, set_seed SEED_D right before confirm_cydonia - then the stage-1 spine (session.briefings_to_battlescape:
both briefings, both equip screens, turn 1). MAP_FP_D pinned, pin_ai_neutral (the 12 landing aliens), hash clean; the
client's stack bottom is GeoscapeState; the host's researchMode.seats[1].count is RESEARCH_COUNT_D and equals both
machines' liveCount (a pre-stage guard, TASK 0 3/3).

  MS5  stage 2 for both players in a SHARED campaign, the kill-all route (as MS1): the host kills every alien
       (kill_unit_real faction 1), the chain settles, END TURN client then host, the host closes its NextTurnState
       (finishBattle(false, 2) -> vanilla's next-stage branch). Stage-entry cells (MS1's): the client shows the
       stage-2 BriefingState within ENTRY_S of the host's close, its missionType is STR_MARS_THE_FINAL_ASSAULT, the
       client's `stage` record applied 1, the host's emitted 1 (read right after the close). Then the stage-2 spine
       and the green cells: both turn 1 on STR_MARS_THE_FINAL_ASSAULT; the client's stack bottom is still
       GeoscapeState; desyncSeen false on both; M1: the host's event_state.researchMode.seats[1].count at stage 2 is
       > 0 and equals its stage-1 count (RESEARCH_COUNT_D); the host is alive; no new crash file.

RED on S-A2's commit 1 (S-A1's red base, no stage writer; the TASK 0 red pre-walk on this build): the four
stage-entry cells fail (the host died 1.0 s after its close, F5081, and the client left to [GoToMainMenuState,
CoopState], so its missionType reads None); every pre-stage cell passes. Host liveness and crash files are EVIDENCE
only until stage 2 is reached (F10010: the host's own event_state read can fault on the freed stage-1 screen).
M1 is a stage-2 cell: on the red its stage-1 half reads RESEARCH_COUNT_D and its stage-2 half is never reached.

The row prints ONE "EVIDENCE MS5:" line before its verdict, then "PASS MS5" or "FAIL MS5: <cells>" and, on a FAIL,
ONE "CAPTURE MS5:" line (both machines' event_state, battle_state, stack and log tail). A bring-up step past its
bound fails the row `boot` with one CAPTURE line. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0
only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_multistage_campaign.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import pin_ai_neutral, assert_hash_clean
from test_cydonia_coop_start import _craft_and_soldiers, _seat, _aboard
from test_w2_multistage import (FixtureMiss, short, rc, stack, eview, evidence, capture, step, run_spine, IDLE_S,
                                FACTION_PLAYER)
from test_w2_multistage_end import (bview, stage_guards, kill_all, close_end_turn, entry_cells, record_cells,
                                    liveness_cells, MISSION_LANDING, MISSION_FINAL)

# ----- boot D (TASK 0 T0-4: SEED_D 1 set right before confirm_cydonia, fingerprint 4/4) -----
PORT_D, GC_D = "48574", (49680, 49681)
SEED_D = 1
MAP_FP_D = -3.7087676953867494e+18
CRAFT_D, SQUAD_D = 1, [1, 2]                     # the host's Skyranger and the first two of its roster
SEATS_D = {1: 0, 2: 1}                           # X-COM id -> coop seat (the squad split)
ALIENS_D = list(range(1000000, 1000012))
RESEARCH_D = ["STR_PLASMA_PISTOL"]               # R-MGA-A2-T-1 (a); the test_w2_client_research precedent
RESEARCH_COUNT_D = 1                             # liveCount on both machines and the host's seats[1].count (TASK 0 3/3)


def bottom(gc):
    st = stack(gc)
    return st[0] if isinstance(st, list) and st else st


def boot_d(host, client):
    m = [host, client]
    step("spawn + connect", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    step("new_campaign shared", lambda: session.new_campaign(host, client, port=PORT_D, campaign_mode="shared"), m)
    craft, roster = step("craft and roster", lambda: _craft_and_soldiers(host), m)
    if craft != CRAFT_D or roster[:2] != SQUAD_D:
        raise FixtureMiss(f"craft {craft} roster {roster} (want craft {CRAFT_D}, roster starting {SQUAD_D})")

    def split():
        _seat(host, craft, roster)
        for gc in (host, client):
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": roster[0], "owner": 0})
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": roster[1], "owner": 1})
        host.wait_for("shared squad seated", lambda: (_aboard(host, craft) == SQUAD_D) or None, timeout=30)

    step("squad split", split, m)

    def research():
        for gc in (host, client):
            for topic in RESEARCH_D:
                r = gc.cmd({"cmd": "discover_research", "topic": topic})
                if not (r.get("ok") and r.get("researched") is True):
                    raise FixtureMiss(f"{gc.name} discover_research {topic}: {r}")

    step("discover_research on both machines", research, m)

    def cydonia():
        host.ok({"cmd": "open_cydonia", "craft_id": craft})
        host.wait_for("Cydonia confirmation", lambda: session.has_state(host, "ConfirmCydoniaState") or None)
        host.ok({"cmd": "set_seed", "seed": SEED_D})
        host.ok({"cmd": "confirm_cydonia"})

    step("open_cydonia + set_seed + confirm_cydonia", cydonia, m)
    step("stage-1 spine", lambda: session.briefings_to_battlescape(host, client), m)
    hb, cb = bview(host), bview(client)
    bad = []
    if hb.get("mapFingerprint") != MAP_FP_D or cb.get("mapFingerprint") != MAP_FP_D:
        bad.append(f"mapFingerprint host={hb.get('mapFingerprint')!r} client={cb.get('mapFingerprint')!r} "
                   f"(baked {MAP_FP_D!r}, SEED_D {SEED_D})")
    if (hb.get("side"), hb.get("turn"), hb.get("missionType")) != (FACTION_PLAYER, 1, MISSION_LANDING):
        bad.append(f"host (side, turn, mission)={(hb.get('side'), hb.get('turn'), hb.get('missionType'))}")
    if hb.get("xcom") != SEATS_D or cb.get("xcom") != SEATS_D:
        bad.append(f"X-COM seats host={hb.get('xcom')} client={cb.get('xcom')} (want {SEATS_D})")
    if bad:
        raise FixtureMiss("bring-up pins: " + "; ".join(bad))
    pinned = step("pin_ai_neutral", lambda: pin_ai_neutral(host, client, tag="mga-a2-d"), m)
    if sorted(pinned) != ALIENS_D:
        raise FixtureMiss(f"pin_ai_neutral pinned {pinned} (want {ALIENS_D})")
    step("wait_host_idle", lambda: session.wait_host_idle(host, client, timeout=IDLE_S), m)
    step("hash clean at bring-up", lambda: assert_hash_clean(host, client, full=True, what="bring-up"), m)
    return {"mapFingerprint": hb.get("mapFingerprint"), "pinned": len(pinned), "clientStack": stack(client)}


def ms5(host, client, ctx, crash0):
    g = []
    stage_guards(host, client, ctx, g)
    ctx["bottom1"] = bottom(client)
    if ctx["bottom1"] != "GeoscapeState":
        g.append(f"client stack bottom before the stage {stack(client)} (want GeoscapeState)")
    he, ce = eview(host), eview(client)
    ctx["research1"] = he.get("seat1Research")
    ctx["live1"] = [he.get("liveResearch"), ce.get("liveResearch")]
    if ctx["research1"] != RESEARCH_COUNT_D or ctx["live1"] != [RESEARCH_COUNT_D, RESEARCH_COUNT_D]:
        g.append(f"research before the stage: host seats[1].count {ctx['research1']}, liveCount host/client "
                 f"{ctx['live1']} (want {RESEARCH_COUNT_D} each, R-MGA-A2-T-1)")
    kill_all(host, client, ALIENS_D, g, "stage 1")
    hb, cb = bview(host), bview(client)
    if hb.get("xcom") != SEATS_D or cb.get("xcom") != SEATS_D:
        g.append(f"survivors host={hb.get('xcom')} client={cb.get('xcom')} (want {SEATS_D})")
    ctx["t_close"] = close_end_turn(host, client, g)
    ctx["hostStageAtClose"] = eview(host).get("stage")    # finishBattle ran inside dismiss_popup
    ctx["hostRcAtClose"] = rc(host)
    if g:
        evidence("MS5", {"guards": g, "ctx": ctx})
        return [f"pre-stage: {m}" for m in g]
    fails = entry_cells(host, client, ctx, MISSION_FINAL)
    green = {}
    if not fails:
        ctx["inStage2"] = True
        try:
            _pressed, ctx["spineS"] = run_spine(host, client)
            green = record_cells(host, client, ctx, fails, {})
            hb, cb = bview(host), bview(client)
            green["battle"] = {"host": hb, "client": cb}
            for name, b in (("host", hb), ("client", cb)):
                if b.get("turn") != 1 or b.get("missionType") != MISSION_FINAL:
                    fails.append(f"{name} turn/missionType={b.get('turn')}/{b.get('missionType')} "
                                 f"(want 1/{MISSION_FINAL})")
            ctx["bottom2"] = bottom(client)
            if ctx["bottom2"] != "GeoscapeState":
                fails.append(f"client stack bottom after the stage {stack(client)} (want GeoscapeState)")
            ctx["research2"] = eview(host).get("seat1Research")
            r1, r2 = ctx["research1"], ctx["research2"]
            if not (isinstance(r2, int) and r2 > 0 and r2 == r1):
                fails.append(f"M1: host researchMode.seats[1].count stage 1 {r1} -> stage 2 {r2} (want > 0 and equal)")
        except Exception as e:
            fails.append(f"stage-2 spine / cells: {short(e, 600)}")
    liveness_cells(host, ctx, crash0, fails)
    evidence("MS5", {"b1": ctx.get("b1"), "bottom": [ctx.get("bottom1"), ctx.get("bottom2")],
                     "M1research": [ctx.get("research1"), ctx.get("research2")], "live1": ctx.get("live1"),
                     "entry": ctx.get("entry"),
                     "clientBriefingS": ctx.get("clientBriefingS"), "spineS": ctx.get("spineS"), "green": green,
                     "hostRc": rc(host), "newCrashFiles": ctx.get("newCrashFiles")})
    return fails


def main():
    t0 = time.time()
    host = GameClient("host", GC_D[0], make_user_dir("mga_ms_d_host"))
    client = GameClient("client", GC_D[1], make_user_dir("mga_ms_d_client"))
    crash0 = session._crash_log_snapshot()
    ctx, ok = {}, False
    try:
        try:
            info = boot_d(host, client)
            print(f"[mga-a2] boot D ok: {info}", flush=True)
        except Exception as e:
            print(f"FAIL MS5: boot (FIXTURE-STOP) {short(e, 600)}", flush=True)
            capture("MS5", [host, client], short(e, 600))
            info = None
        if info is not None:
            try:
                fails = ms5(host, client, ctx, crash0)
            except FixtureMiss as e:
                fails = [f"FIXTURE-STOP {e}"]
                evidence("MS5", {"fixtureStop": str(e), "ctx": ctx})
            except Exception as e:
                fails = [short(e, 600)]
                evidence("MS5", {"exception": short(e, 600), "ctx": ctx})
            ok = not fails
            if fails:
                print(f"FAIL MS5: {len(fails)} cell(s): " + " | ".join(fails), flush=True)
                capture("MS5", [host, client], "row failed")
            else:
                print("PASS MS5", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[mga-a2] shutdown {gc.name}: {short(e)}", flush=True)
    print(f"\ntest_w2_multistage_campaign: {1 if ok else 0}/1 passed (pass={['MS5'] if ok else []} "
          f"fail={[] if ok else ['MS5']}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
