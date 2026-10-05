"""W2-P7 S-C-F - test_w2_campaign_second_battle.py: a SHARED campaign plays a SECOND battle in the same session after
its first battle's return - entry, one ending and the return again, with the per-battle record reset (docs
rewrite/prompts/w2p7_sc_design.md section 3.8, AMENDMENT P7-8 section 4.3 row C28S-2, PR-53; N29/F1340; owner D156 (a),
D175, D176; mechanism rulings MR1-MR3).

ACCEPTANCE (S-C-F proves, it does not fix): every S-C stage it covers (A, B1, B2, B2.3, C, D1, D2, E1, E2) is
integrated under it, so the row is expected green; a red row is a defect of the stage that owns the code (R7 capture
and STOP, P8-12), never a fix here.

Fixture (one boot, port 47266, AMENDMENT P7-8 section 4 S26): shared_fixture.bring_up(tag, (0, 0, PORT)); battle 1 =
test_w2_battle_end_campaign.stage (FX-S: SEED_S, MAP_FP_S, autoEnd, the 15 hostiles, the HOST_DEBRIEF pin; its
pre-cell is a FIXTURE-STOP); battle 2 = session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1},
pre_landing=camp.seed_pin) on the SAME session, ended by a local copy of camp.stage's ending WITHOUT the HOST_DEBRIEF pin
(FX-ST's precedent, test_w2_shared_forced_storage.stage_x): autoEnd on, kill_unit_real {faction: 1} kills every live
hostile, the host's NextTurnState closed, the host's DebriefingState.

Row C28S-2. The cells are checked in order; a failed cell ends the row (every later cell depends on it) and the rest
are reported "not reached":
  B1  battle 1: the client's display-only debriefing, its in-place adoption, the client's OK, the host's OK + drain;
      both tops GeoscapeState.
  (1) battle 2: event_state.phase Idle on both before the host's offer (it is not refused); both enter (the host's
      battle_state.inBattle and the client's BattlescapeState); the client's battleEnd.worldAdopted and the host's
      worldPushed read at entry (the record reset at initBattleAuthority: 0 expected).
  (2) battle 2's ending (no debrief pin; every live hostile killed, the host's debriefing, fatalVote.armed 0); both
      debriefings equal on the seven content fields with page-2 names prefix-stripped (PR-10), the client's
      display-only.
  (3) the client's worldAdopted == 1 within ADOPT_S (entry + 1, not 2: the reset), the host's worldPushed == 1,
      shared_checksum chk* equal.
  (4) the client's OK, then the host's OK + drain: both GeoscapeState; no CoopState / LoadGameState pushed on the
      client since battle 2's kill (log count, P6-4); phase Idle and researchMode.coopBattle false on both; chk*
      equal; debriefOkBranch "campaign-host" / "campaign-client-shared"; the client zero-disk; worldAdopted still 1.
Guard over the row: no new crash log; host fatalVote.armed 0 at both endings. The EVIDENCE line carries both
machines' battleEnd records (page3, worldAdoptDeferredPasses, forced, adoptFailed among them), sel_state and the
per-battle walls.

ONE "EVIDENCE C28S-2:" line, then "PASS C28S-2" or "FAIL C28S-2: <message>". WV-D95/D99/D100: ONE foreground run, no
skip path; exit 0 only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_campaign_second_battle.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
import test_w2_battle_end_campaign as camp

PORT = "47266"                       # AMENDMENT P7-8 section 4 (S26, F6118): F = 47266 (S2), 47267 (P2)
TAG = "w2p7scf_s2"
ADOPT_S = camp.ADOPT_S               # 15 s (CONSTANTS T0-S2)
DEBRIEF_S = camp.DEBRIEF_S           # 60 s: the host's DebriefingState after the kill
LOADGAME_PUSH = camp.LOADGAME_PUSH   # "push class OpenXcom::LoadGameState" (Game.cpp :599 [coop-ui] push line)
COOPSTATE_PUSH = "push class OpenXcom::CoopState depth="   # the same line for a CoopState (exact class name)
RECORD_KEYS = ("worldAdopted", "worldPushed", "worldHeld", "returnPending", "okDeferred", "debriefDisplayOnly",
               "debriefOkBranch", "page3", "worldAdoptDeferredPasses", "forced", "adoptFailed", "chain")


def stack(gc):
    return camp.stack(gc)


def top(gc):
    return camp.top(gc)


def record(gc):
    return camp.record(gc)


def rec_keys(gc):
    r = record(gc)
    return {k: r.get(k) for k in RECORD_KEYS}


def sel_state(gc):
    r = gc.cmd({"cmd": "sel_state"})
    return {k: r.get(k) for k in ("ok", "localSeat", "keys", "error")}


def capture_line(name, err, machines):
    """R7 capture of a failed battle-2 step: every machine's stack, event_state, battle flags and debrief_state
    (whole), printed as ONE CAPTURE line (does not raise; the cell reports the failure)."""
    cap = {}
    for gc in machines:
        try:
            bs = battle_state(gc)
            cap[gc.name] = {"stack": stack(gc), "event_state": event_state(gc),
                            "battle": {k: bs.get(k) for k in ("inBattle", "isBusy", "pendingStates", "turn", "phase",
                                                              "mapFingerprint")},
                            "debrief": gc.cmd({"cmd": "debrief_state"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {camp.short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


# ===================== battle 1 (FX-S, camp.stage is the pre-cell) =====================


def cell_battle1(host, client, ctx):
    """B1: battle 1's two returns - the client's display-only debriefing, its adoption, its OK, the host's OK + drain;
    both tops GeoscapeState."""
    f = camp.cell_debriefs(host, client, ctx)
    if f:
        return f
    f = camp.cell_adopted(host, client, ctx, False)
    if f:
        return f
    f = camp.client_ok_clean(client, ctx, "clientOk")
    if f:
        return f
    f = camp.host_ok_drain(host, ctx, "hostOk")
    tops = {"host": top(host), "client": top(client)}
    ctx["battle1Tops"] = tops
    f += [f"{n} top={t} after battle 1's OKs (want GeoscapeState)" for n, t in tops.items() if t != "GeoscapeState"]
    ctx["battle1Records"] = {"host": rec_keys(host), "client": rec_keys(client)}
    ctx["t"]["battle1End"] = round(time.time() - ctx["t"]["t0"], 1)
    return f


# ===================== battle 2 =====================


def cell_enter2(js, ctx2, t):
    """(1) phase Idle on both before the offer; both enter battle 2; the entry records."""
    host, client = js.host, js.client
    t["battle2Start"] = round(time.time() - t["t0"], 1)
    phases = {"host": event_state(host).get("phase"), "client": event_state(client).get("phase")}
    ctx2["phaseBefore"] = phases
    f = [f"{n} event_state.phase={p!r} before battle 2's offer (want 'Idle')" for n, p in phases.items() if p != "Idle"]
    if f:
        return f
    try:
        _h, _c, squad = session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, pre_landing=camp.seed_pin)
    except Exception as e:
        capture_line("battle 2 bring_up_shared_mixed_battle", camp.short(e, 800), (host, client))
        return [f"battle 2 bring-up: {camp.short(e, 800)}"]
    ctx2["squad"] = squad
    hb = battle_state(host)
    ctx2["entry"] = {"hostInBattle": hb.get("inBattle"), "clientTop": top(client),
                     "mapFingerprint": (hb.get("mapFingerprint"), battle_state(client).get("mapFingerprint")),
                     "hostRecord": rec_keys(host), "clientRecord": rec_keys(client)}
    if hb.get("inBattle") is not True:
        f.append(f"host battle_state.inBattle={hb.get('inBattle')!r} after battle 2's bring-up (want True)")
    if top(client) != "BattlescapeState":
        f.append(f"client top={top(client)} after battle 2's bring-up (want BattlescapeState)")
    return f


def ending2(host, client, ctx2):
    """camp.stage's ending without the HOST_DEBRIEF pin (FX-ST's precedent): autoEnd on, kill every live hostile, the
    host's NextTurnState closed, its DebriefingState. Returns failure strings (a CAPTURE line printed on failure)."""
    m = (host, client)
    ae = host.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    ctx2["autoEnd"] = ae.get("value")
    if ae.get("value") is not True:
        capture_line("battle 2 battleAutoEnd", f"host set_option answered {ae}", m)
        return [f"battle 2: host set_option battleAutoEnd answered {ae}"]
    ctx2["loadGamePushes0"] = camp.log_count(client, LOADGAME_PUSH)
    ctx2["coopStatePushes0"] = {gc.name: camp.log_count(gc, COOPSTATE_PUSH) for gc in m}
    live = sorted(u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    ctx2["kill"] = {"live": live, "equalsFxS": live == camp.HOSTILES,
                    "resp": {k2: k.get(k2) for k2 in ("ok", "killed", "error")}}
    if not k.get("ok") or not live or sorted(k.get("killed") or []) != live:
        capture_line("battle 2 kill", f"kill_unit_real faction 1 answered {ctx2['kill']}", m)
        return [f"battle 2: kill_unit_real faction 1 answered {ctx2['kill']['resp']} (want every live hostile {live})"]
    t0, closes, samples, last = time.time(), [], [], None
    while time.time() - t0 < DEBRIEF_S:
        hst = stack(host)
        if "DebriefingState" in hst:
            break
        s = (hst[-1] if hst else None, top(client))
        if s != last:
            samples.append((round(time.time() - t0, 2),) + s)
            last = s
        if hst and hst[-1] == "NextTurnState":
            closes.append(host.cmd({"cmd": "dismiss_popup"}).get("handled"))
        time.sleep(0.1)
    ctx2["ending"] = {"secs": round(time.time() - t0, 2), "closes": closes, "samples": samples}
    if "DebriefingState" not in stack(host):
        capture_line("battle 2 host debriefing", f"no host DebriefingState within {DEBRIEF_S}s", m)
        return [f"battle 2: no host DebriefingState within {DEBRIEF_S}s of the kill ({ctx2['ending']})"]
    hdeb = host.cmd({"cmd": "debrief_state"})
    ctx2["hostDebrief"] = camp.pin_view(hdeb)
    bad = [f"battle 2 host debrief_state.{k2}={hdeb.get(k2)!r} (want {w!r})"
           for k2, w in (("shown", True), ("onTop", True), ("displayOnly", False)) if hdeb.get(k2) is not w]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        bad.append(f"battle 2 host fatalVote.armed={armed!r} (want 0: no S-V vote, F4544)")
    if bad:
        capture_line("battle 2 host debriefing", "; ".join(bad), m)
    return bad


def cell_debriefs2(host, client, ctx2):
    """(2) battle 2's ending, then both debriefings equal (PR-10 stripped), the client's display-only."""
    f = ending2(host, client, ctx2)
    if f:
        return f
    return camp.cell_debriefs(host, client, ctx2)


def cell_adopted2(host, client, ctx2):
    """(3) the client's worldAdopted == 1 (entry + 1; the record reset at initBattleAuthority, not 2), the host's
    worldPushed == 1, chk* equal."""
    e = ctx2.get("entry") or {}
    a0 = (e.get("clientRecord") or {}).get("worldAdopted")
    p0 = (e.get("hostRecord") or {}).get("worldPushed")
    a0 = a0 if isinstance(a0, int) else 0
    p0 = p0 if isinstance(p0, int) else 0
    ok, secs = camp.wait_until(lambda: record(client).get("worldAdopted") == a0 + 1
                               and record(host).get("worldPushed") == p0 + 1, ADOPT_S)
    crec, hrec = record(client), record(host)
    ctx2["adopt"] = {"waited": secs, "entry": {"worldAdopted": a0, "worldPushed": p0},
                     "client": {k: crec.get(k) for k in ("returnPending", "worldHeld", "worldAdopted",
                                                         "heldAppliesAtAdopt", "okDeferred")},
                     "host": {k: hrec.get(k) for k in ("worldPushed", "worldPushBytes", "worldPushDeferredPasses")}}
    f = []
    if crec.get("worldAdopted") != 1:
        f.append(f"client battleEnd.worldAdopted={crec.get('worldAdopted')!r} after {secs}s (want 1: entry {a0} + one "
                 f"adoption; the record reset at initBattleAuthority, not 2)")
    if hrec.get("worldPushed") != 1:
        f.append(f"host battleEnd.worldPushed={hrec.get('worldPushed')!r} after {secs}s (want 1, entry {p0})")
    if f:
        return f
    eq, esecs, hc, cc = camp.chk_equal(host, client)
    ctx2["adopt"]["chk"] = {"equal": eq, "secs": esecs, "host": hc, "client": cc}
    return [] if eq else [f"shared_checksum chk* host {hc} != client {cc} after {camp.EQUAL_S}s"]


def cell_returns2(host, client, ctx2, t):
    """(4) the client's OK, then the host's OK + drain: both GeoscapeState, no CoopState / LoadGameState pushed on the
    client since battle 2's kill, phase Idle / coopBattle false on both, chk* equal, the OK branches, zero-disk."""
    f = camp.client_ok_clean(client, ctx2, "clientOk")
    if f:
        return f
    f = camp.host_ok_drain(host, ctx2, "hostOk")
    tops = {"host": top(host), "client": top(client)}
    f += [f"{n} top={tp} after battle 2's OKs (want GeoscapeState)" for n, tp in tops.items() if tp != "GeoscapeState"]
    pushes = {gc.name: camp.log_count(gc, COOPSTATE_PUSH) - ctx2["coopStatePushes0"][gc.name] for gc in (host, client)}
    ctx2["coopStatePushes"] = pushes
    if pushes["client"] != 0:
        f.append(f"client pushed {pushes['client']} CoopState(s) since battle 2's kill (want 0: in-place return, P6-4)")
    f += camp.end_checks(host, client, ctx2)
    if record(client).get("worldAdopted") != 1:
        f.append(f"client battleEnd.worldAdopted={record(client).get('worldAdopted')!r} after the OKs (want still 1)")
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        f.append(f"host fatalVote.armed={armed!r} after battle 2 (want 0)")
    ctx2["records"] = {"host": rec_keys(host), "client": rec_keys(client)}
    ctx2["selState"] = {"host": sel_state(host), "client": sel_state(client)}
    t["battle2End"] = round(time.time() - t["t0"], 1)
    return f


def stage(rid, js, ctx):
    ctx["t"] = {"t0": time.time()}
    camp.stage(rid, js, ctx)
    ctx["t"]["battle1Debrief"] = round(time.time() - ctx["t"]["t0"], 1)


def cells(host, client, ctx, js):
    ctx2 = ctx.setdefault("battle2", {})
    t = ctx["t"]
    return [
        ("B1 battle 1: both OKs, both on the geoscape", lambda: cell_battle1(host, client, ctx)),
        ("1 battle 2: phase Idle before the offer, both enter", lambda: cell_enter2(js, ctx2, t)),
        ("2 battle 2's ending; both debriefings equal, the client's display-only",
         lambda: cell_debriefs2(host, client, ctx2)),
        ("3 battle 2: the client adopted once (1, not 2), the host pushed once, chk* equal",
         lambda: cell_adopted2(host, client, ctx2)),
        ("4 battle 2: the client's OK, the host's OK + drain, both on the geoscape",
         lambda: cell_returns2(host, client, ctx2, t)),
    ]


def main():
    t0, results, walls = time.time(), {}, {}
    holder = {}

    def stage_fn(rid, js, ctx):
        holder["js"] = js
        stage(rid, js, ctx)

    camp.run_row("C28S-2", TAG, PORT, stage_fn, lambda h, c, ctx: cells(h, c, ctx, holder["js"]), results, walls)
    ok = bool(results.get("C28S-2"))
    print(f"\ntest_w2_campaign_second_battle: {1 if ok else 0}/1 passed (pass={['C28S-2'] if ok else []} "
          f"fail={[] if ok else ['C28S-2']}) in {time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
