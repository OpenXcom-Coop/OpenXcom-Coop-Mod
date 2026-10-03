"""W2-P7 S-C-D1 - test_w2_shared_crash_return.py: a SHARED campaign battle that ends with no live alien (the
aliens-crashed ending, P8b SE-2) still takes the host's post-battle world IN PLACE on the second player while its
AliensCrashState is up, never through today's CoopState(555) -> LoadGameState path (docs
rewrite/prompts/w2p7_sc_design.md AMENDMENT P7-7 PR-27, row D1d = SK2; carried F5236; owner D154, D156 + MR1, D176).

F5236 (CANDIDATE): PR-4's world hold covers the campaign display-only debriefing and a BattlescapeState on the
stack, not AliensCrashState; the client's consumer setState()s AliensCrashState first in this ending, so a world
that arrives while it is up would take the CoopState(555) path. PR-27: this row decides it - red at the red build
(worldHeld 0 and a LoadGameState push) -> S-C-D1.2 adds AliensCrashState to coopReturnHoldStack's scan; green at
the red build -> no product change, the row stays as a guard.

Fixture FX-X (AMENDMENT P7-7 section 3; P8b's EQ24c recipe, test_w2_prebattle_equip_end.py Boots E2/E3, ruling SE-4):
shared_fixture.bring_up(tag, (0, 0, PORT)); session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1},
to_tactical=False, pre_landing = host set_seed SEED_S + the client's hold_battle_ready {on: true} (Q16 a), so the
host stays in phase Handshake); the client's BriefingState (its battle_ready held); every live alien ->
battle_set_unit_state {status: STATUS_DEAD} on both machines, client first (test_w2_prebattle_equip_end.stage_aliens,
P8b T0-5); the host's close_briefing -> its AliensCrashState; the host's OK on it -> its DebriefingState with V5's
result held (phase Handshake, resultSent 0, SE-4); the client's close_briefing (that test's spine); then the client's
hold_battle_ready {on: false} releases battle_ready -> the host's onReady sends the held result, then the PR-3 world
push. Pre-cell (a failure is a FIXTURE-STOP: one CAPTURE line, then the row FAILs "pre-cell").

Row D1d (the GREEN cells, in order; a failed cell ends the row):
  (1) the client's top AliensCrashState within CRASH_S of the host's DebriefingState.
  (2) keep it up (no OK pressed): the host's battleEnd.worldPushed 1 and the client's worldHeld >= 1 within HELD_S;
      no "push class OpenXcom::LoadGameState" line in the client log over the row.
  (3) the client's OK on its AliensCrashState -> its display-only DebriefingState; worldAdopted 1; chk* equal.
  (4) both OKs -> both GeoscapeState, no CoopState on either stack.
Guard: host event_state.fatalVote.armed 0; no new crash log; the client zero-disk at the end.

RED (commit S-C-D1.1): CANDIDATE - cell 2 red (worldHeld 0 and a LoadGameState push) or green; either verdict is
reported and PR-27 follows it. Prints ONE "EVIDENCE D1d:" line, then "PASS D1d" or "FAIL D1d: <message>".
WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_crash_return.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
import shared_fixture
import test_w2_battle_end_campaign as camp
import test_w2_prebattle_equip_end as pe

PORT = "47252"            # AMENDMENT P7-7 section 3 (S26, F5582): D1 = 47250-47252
TAG = "w2p7scd1_x"
SEED_S = camp.SEED_S      # 1 (CONSTANTS T0-6 (i))
BRIEF_S = 30              # the client's BriefingState after the host's (P8b EQ1_WAIT_S)
CRASH_HOST_S = 5          # the host's AliensCrashState after its briefing OK (P8b CRASH_WAIT_S)
DEBRIEF_S = 10            # a DebriefingState after an AliensCrashState OK (P8b DEBRIEF_WAIT_S)
LEAVE_S = 10              # the client's briefing gone after its close_briefing
CRASH_S = 20              # P7-7 D1d cell 1: "within 20 s of the host's DebriefingState"
HELD_S = 15               # P7-7 D1d cell 2: "within 15 s"
ADOPT_S = camp.ADOPT_S    # 15 s (CONSTANTS T0-S2)
OK_S = camp.OK_S          # 10 s
LOADGAME_PUSH = camp.LOADGAME_PUSH


class FixtureMiss(Exception):
    pass


def short(e, n=400):
    return camp.short(e, n)


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=0.1):
    return camp.wait_until(pred, timeout, interval)


def record(gc):
    return camp.record(gc)


def rec_keys(gc):
    r = record(gc)
    return {k: r.get(k) for k in ("emitted", "applied", "reason", "resultSent", "resultReceived", "returnPending",
                                  "worldPushed", "worldPushBytes", "worldHeld", "worldAdopted", "heldAppliesAtAdopt",
                                  "okDeferred", "debriefDisplayOnly", "debriefCampaign", "debriefOkBranch", "page3",
                                  "worldAdoptDeferredPasses", "forced", "adoptFailed")}


def view(gc):
    es = event_state(gc)
    return {"stack": stack(gc), "phase": es.get("phase"), "record": rec_keys(gc),
            "abortPending": (es.get("equip") or {}).get("abortPending")}


def hold(gc, **kw):
    req = {"cmd": "hold_battle_ready"}
    req.update(kw)
    r = gc.cmd(req)
    return {k: r.get(k) for k in ("ok", "error", "armed", "held", "sent")}


def capture(name, err, machines, ctx):
    cap = {}
    for gc in machines:
        try:
            bs = battle_state(gc)
            cap[gc.name] = {"view": view(gc), "event_state": event_state(gc),
                            "battle": {k: bs.get(k) for k in ("inBattle", "isBusy", "pendingStates", "turn", "phase",
                                                              "mapFingerprint")},
                            "debrief": gc.cmd({"cmd": "debrief_state"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


# ===================== FX-X (pre-cell) =====================


def fx_x(js, ctx):
    host, client = js.host, js.client
    m = (host, client)

    def pre_landing(h, c):
        h.ok({"cmd": "set_seed", "seed": SEED_S})
        ctx["arm"] = hold(c, on=True)

    try:
        session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, to_tactical=False, pre_landing=pre_landing)
    except Exception as e:
        capture("bring_up_shared_mixed_battle", short(e, 800), m, ctx)
    if not (ctx.get("arm", {}).get("ok") and ctx["arm"].get("armed") is True):
        capture("hold_battle_ready arm", f"answered {ctx.get('arm')}", m, ctx)
    g, d = wait_until(lambda: "BriefingState" in stack(client), BRIEF_S)
    ctx["clientBriefing"] = {"ok": g, "secs": d, "hold": hold(client), "hostPhase": event_state(host).get("phase"),
                             "mapFingerprint": [battle_state(host).get("mapFingerprint"),
                                                battle_state(client).get("mapFingerprint")]}
    if not (g and ctx["clientBriefing"]["hold"].get("held") is True and ctx["clientBriefing"]["hostPhase"] == "Handshake"
            and top(host) == "BriefingState"):
        capture("client briefing (battle_ready held)", f"{ctx['clientBriefing']} host stack {stack(host)}", m, ctx)
    s = pe.stage_aliens(host, client, ctx)   # every live alien STATUS_DEAD on both, client first (P8b T0-5)
    la = s.get("liveAfter") or {}
    bad = [f"{side} {a}: {r}" for side in ("client", "host") for a, r in (s.get(side) or {}).items()
           if not r.get("ok") or r.get("status") != pe.STATUS_DEAD]
    if s.get("error") or not s.get("ids") or bad or s.get("diff") or (s.get("hashNote") or {}).get("error") \
            or la.get("host") or la.get("client"):
        capture("alien staging", f"stage_aliens record {s} (bad {bad})", m, ctx)
    hc = host.cmd({"cmd": "close_briefing"})
    g, d = wait_until(lambda: top(host) == "AliensCrashState", CRASH_HOST_S)
    ctx["hostClose"] = {"close": {k: hc.get(k) for k in ("ok", "error")}, "ok": g, "secs": d, "view": view(host)}
    if not g:
        capture("host AliensCrashState", f"host top {top(host)!r} after close_briefing", m, ctx)
    hp = host.cmd({"cmd": "dismiss_popup"})
    g, d = wait_until(lambda: top(host) == "DebriefingState", DEBRIEF_S)
    ctx["hostDebriefAt"] = time.time()
    hv = view(host)
    ctx["hostOk"] = {"press": {k: hp.get(k) for k in ("ok", "handled", "error")}, "ok": g, "secs": d, "view": hv}
    if not (g and hp.get("handled") == "AliensCrashState" and hv["phase"] == "Handshake"
            and hv["record"].get("resultSent") == 0):
        capture("host DebriefingState (V5 held, SE-4)", f"{ctx['hostOk']}", m, ctx)
    cc = client.cmd({"cmd": "close_briefing"})
    g, d = wait_until(lambda: "BriefingState" not in stack(client), LEAVE_S)
    ctx["clientClose"] = {"close": {k: cc.get(k) for k in ("ok", "error")}, "ok": g, "secs": d, "stack": stack(client)}
    if not g:
        capture("client close_briefing", f"{ctx['clientClose']}", m, ctx)
    ctx["loadGamePushes0"] = camp.log_count(client, LOADGAME_PUSH)
    ctx["release"] = hold(client, on=False)
    ctx["releasedAt"] = round(time.time() - ctx["hostDebriefAt"], 2)
    if not (ctx["release"].get("ok") and ctx["release"].get("sent") is True):
        capture("hold_battle_ready release", f"answered {ctx['release']}", m, ctx)


# ===================== cells =====================


def cells(host, client, ctx):
    def c1():
        left = max(0.0, CRASH_S - (time.time() - ctx["hostDebriefAt"]))
        g, d = wait_until(lambda: top(client) == "AliensCrashState", left)
        ctx["clientCrash"] = {"ok": g, "secsAfterHostDebrief": round(time.time() - ctx["hostDebriefAt"], 2),
                              "stack": stack(client), "record": rec_keys(client)}
        return [] if g else [f"the client's top {top(client)!r} {CRASH_S}s after the host's DebriefingState (want "
                             f"AliensCrashState; stack {stack(client)})"]

    def c2():
        tops = []

        def held():
            t = top(client)
            if t not in tops:
                tops.append(t)
            return record(host).get("worldPushed") == 1 and (record(client).get("worldHeld") or 0) >= 1
        g, d = wait_until(held, HELD_S)
        pushes = camp.log_count(client, LOADGAME_PUSH) - ctx["loadGamePushes0"]
        ctx["held"] = {"ok": g, "secs": d, "tops": tops, "loadGamePushes": pushes, "host": rec_keys(host),
                       "client": rec_keys(client), "clientStack": stack(client)}
        f = []
        if not g:
            f.append(f"host worldPushed={record(host).get('worldPushed')!r} client worldHeld="
                     f"{record(client).get('worldHeld')!r} after {HELD_S}s (want 1 and >= 1; client tops {tops})")
        if pushes != 0:
            f.append(f"the client pushed {pushes} LoadGameState(s) while its AliensCrashState was up (want 0, P6-4)")
        return f

    def c3():
        t = top(client)
        cp = client.cmd({"cmd": "dismiss_popup"}) if t == "AliensCrashState" else {"note": f"client top {t}"}
        g, d = wait_until(lambda: (lambda x: x.get("onTop") is True and x.get("displayOnly") is True)(
            client.cmd({"cmd": "debrief_state"})), DEBRIEF_S)
        ga, da = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
        ctx["clientOkCrash"] = {"press": {k: cp.get(k) for k in ("ok", "handled", "error", "note")}, "debrief": g,
                                "secs": d, "adopted": ga, "adoptSecs": da, "stack": stack(client)}
        f = []
        if cp.get("handled") != "AliensCrashState":
            f.append(f"the client's OK answered {ctx['clientOkCrash']['press']} (want handled AliensCrashState)")
        if not g:
            f.append(f"no client display-only DebriefingState on top within {DEBRIEF_S}s (stack {stack(client)})")
        if not ga:
            f.append(f"client worldAdopted={record(client).get('worldAdopted')!r} after {ADOPT_S}s (want 1)")
        if f:
            return f
        eq, esecs, hc, cc = camp.chk_equal(host, client)
        ctx["clientOkCrash"]["chk"] = {"equal": eq, "secs": esecs, "host": hc, "client": cc}
        return [] if eq else [f"shared_checksum chk* host {hc} != client {cc}"]

    def c4():
        f = camp.client_ok_clean(client, ctx, "clientOk") + camp.host_ok_drain(host, ctx, "hostOk2")
        for gc in (host, client):
            st = stack(gc)
            if not st or st[-1] != "GeoscapeState" or any("CoopState" in s for s in st):
                f.append(f"{gc.name} stack {st} (want top GeoscapeState, no CoopState)")
        return f

    return [
        ("1 the client's AliensCrashState", c1),
        ("2 the world held under it, no LoadGameState", c2),
        ("3 the client's OK -> its display-only debriefing on the adopted world", c3),
        ("4 both OKs -> both on the geoscape", c4),
    ]


def main():
    t0, ctx, js, verdict = time.time(), {"row": "D1d"}, None, None
    crash0 = session._crash_log_snapshot()
    try:
        try:
            js = shared_fixture.bring_up(TAG, (0, 0, PORT))
            fx_x(js, ctx)
        except Exception as e:
            verdict = f"pre-cell (FIXTURE-STOP) {e if isinstance(e, FixtureMiss) else short(e, 800)}"
        if verdict is None:
            host, client = js.host, js.client
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
            g = []
            armed = (event_state(host).get("fatalVote") or {}).get("armed")
            if armed != 0:
                g.append(f"host fatalVote.armed={armed!r} (want 0, F4544)")
            try:
                session.assert_client_zero_disk(client.user_dir)
            except AssertionError as e:
                g.append(str(e))
            if g:
                verdict = (verdict + " | " if verdict else "") + "guard: " + "; ".join(g)
            try:
                ctx["end"] = {"host": view(host), "client": view(client)}
            except Exception as e:
                ctx["end"] = f"probe failed: {short(e)}"
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["newCrashLogs"] = new_crash
        if new_crash:
            verdict = (verdict + " | " if verdict else "") + f"new crash log(s): {new_crash}"
        ctx.pop("hostDebriefAt", None)
        camp.evidence("D1d", ctx)
        print("PASS D1d" if verdict is None else f"FAIL D1d: {verdict}", flush=True)
    finally:
        if js is not None:
            try:
                hold(js.client, on=False)
            except Exception as e:
                print(f"[w2p7-scd1] release hold_battle_ready: {short(e)}", flush=True)
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2p7-scd1] shutdown: {short(e)}", flush=True)
    print(f"\ntest_w2_shared_crash_return: {0 if verdict else 1}/1 passed in {time.time() - t0:.1f}s", flush=True)
    return 0 if verdict is None else 2


if __name__ == "__main__":
    sys.exit(main())
