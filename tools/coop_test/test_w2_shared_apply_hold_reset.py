"""W2-P7 S-C-D2 - test_w2_shared_apply_hold_reset.py: a SHARED second player that leaves the session while it holds
shared applies (its post-battle world not yet adopted) drops them and the apply hold at the session reset, so they can
never drain into the next session's world (docs rewrite/prompts/w2p7_sc_design.md section 3.6, AMENDMENT P7-7
sections 2-4: PR-34 = SK3, F5237, F5576; MR3).

Before S-C-D2 (F5576): CoopSession::resetSession clears no SharedEcon state - the held shared_apply queue (g_applyQ)
and the PR-6 apply hold (g_applyHold) survive a return to the main menu and drain into the next session's world at its
LoadGameState notifyWorldAdopted().

Fixture (AMENDMENT P7-7 section 3.2 D2g): FX-S with test_w2_battle_end_campaign.stage(..., holds=True) - C28S-f's
construction: the SHARED battle on SEED_S, the host's hold_world_stream and the client's hold_world_adopt armed before
the ending (AMENDMENT P7-6 PR-11), the 15 hostiles killed, the host's debriefing == HOST_DEBRIEF. Pre-cell
(FIXTURE-STOP: one CAPTURE line, the row FAILs "pre-cell"): stage() and the client's display-only DebriefingState on
top within CLIENT_DEBRIEF_S.

Row D2g (the GREEN cells, in order; a failed cell ends the row and the rest are reported "not reached"):
  (1) the host's world stream parked (its "[coop-test] hold_world_stream: holding" line within ADOPT_S); the host's
      `sell {T, 1}` from a base screen is fenced (host battleEnd.fenceDeferredPasses >= 1 within FENCE_S); the host's
      stream hold released: the client's shared_stats.applyQueued >= 1 and applyHold true within ADOPT_S (its
      hold_world_adopt keeps the adoption, and so the hold, pending).
  (2) the client's disconnect_to_menu: within RESET_S its applyQueued 0 and applyHold false (PR-34's
      SharedEcon::resetSessionQueues from CoopSession::resetSession).
  (3) the host's OK + drain reaches its GeoscapeState; no crash.
Guard: host event_state.fatalVote.armed 0; no new crash log; the client zero-disk at the end.

RED (commit S-C-D2.1: levers and rows, product untouched): D2g fails on cell 2 - the client's applyQueued stays >= 1
(F5576). GREEN (commit S-C-D2.2): the row passes.
ONE "EVIDENCE D2g:" line, then "PASS D2g" or "FAIL D2g: <message>". WV-D95/D99/D100: ONE foreground run, no skip
path; exit 0 only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_apply_hold_reset.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_w2_battle_end_campaign as camp
import test_w2_shared_forced_storage as fst
from test_w2_shared_forced_storage import (FixtureMiss, stack, top, wait_until, record, sstats, capture,
                                           run_boot)

T = "STR_SECTOID_CORPSE"           # FX-S's T (AMENDMENT P7-7 section 3)
BASE = "HostBase"                  # shared_fixture.bring_up's host_base (base 0)
PORT = "47258"                     # AMENDMENT P7-7 section 3 (S26, F5582)
TAG = "w2p7scd2_g"
HOLD_LINE = "[coop-test] hold_world_stream: holding"   # S-C-A's host stream hold line (test_w2_battle_end_campaign_fence)
ADOPT_S = camp.ADOPT_S             # 15 s (CONSTANTS T0-S2)
FENCE_S = 3                        # host fenceDeferredPasses >= 1 after the sell (one pump pass is ~16 ms)
RESET_S = 10                       # P7-7 section 3.2 D2g (2): "within 10 s"


def pre_g(js, ctx):
    """FX-S with both holds armed (stage(..., holds=True)), then the client's display-only debriefing on top."""
    try:
        camp.stage("D2g", js, ctx, wound=False, holds=True)
    except camp.FixtureMiss as e:
        raise FixtureMiss(f"camp.stage: {e}")
    ok, secs = wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                   and d.get("displayOnly") is True)(js.client.cmd({"cmd": "debrief_state"})),
                          camp.CLIENT_DEBRIEF_S)
    ctx["clientDebrief"] = {"ok": ok, "secs": secs}
    if not ok:
        capture("client debriefing", f"no client display-only DebriefingState on top within {camp.CLIENT_DEBRIEF_S}s",
                (js.host, js.client))


def queue(gc):
    s = sstats(gc)
    return s.get("applyQueued"), s.get("applyHold")


def d2g_cells(host, client, ctx):
    def c1():
        ok, secs = wait_until(lambda: camp.log_count(host, HOLD_LINE) >= 1, ADOPT_S)
        ctx["parked"] = {"reached": ok, "secs": secs}
        if not ok:
            return [f"the host's world stream never parked within {ADOPT_S}s (no '{HOLD_LINE}' line)"]
        r = host.cmd({"cmd": "sell", "item": T, "count": 1, "base": BASE})
        ok, secs = wait_until(lambda: (record(host).get("fenceDeferredPasses") or 0) >= 1, FENCE_S, 0.1)
        ctx["sell"] = {"resp": {k: r.get(k) for k in ("ok", "sent", "error")},
                       "fenceDeferredPasses": record(host).get("fenceDeferredPasses"), "secs": secs}
        f = [] if r.get("ok") and r.get("sent") else [f"host sell answered {ctx['sell']['resp']}"]
        if not ok:
            f.append(f"host battleEnd.fenceDeferredPasses={ctx['sell']['fenceDeferredPasses']!r} {FENCE_S}s after the "
                     f"sell (want >= 1)")
        if f:
            return f
        ctx["releaseHost"] = host.cmd({"cmd": "hold_world_stream", "on": False})
        last = {}

        def held():
            last["q"], last["h"] = queue(client)
            return isinstance(last["q"], int) and last["q"] >= 1 and last["h"] is True
        ok, secs = wait_until(held, ADOPT_S)
        crec = record(client)
        ctx["held"] = {"applyQueued": last.get("q"), "applyHold": last.get("h"), "secs": secs,
                       "worldHeld": crec.get("worldHeld"), "worldAdopted": crec.get("worldAdopted")}
        return [] if ok else [f"client shared_stats applyQueued={last.get('q')!r} applyHold={last.get('h')!r} "
                              f"{ADOPT_S}s after the host's release (want >= 1 and true)"]

    def c2():
        r = client.cmd({"cmd": "disconnect_to_menu"})
        last = {}

        def reset():
            last["q"], last["h"] = queue(client)
            return last["q"] == 0 and last["h"] is False
        ok, secs = wait_until(reset, RESET_S)
        ctx["reset"] = {"resp": {k: r.get(k) for k in ("ok", "error")}, "applyQueued": last.get("q"),
                        "applyHold": last.get("h"), "secs": secs, "clientStack": stack(client)}
        return [] if ok else [f"the client's applyQueued={last.get('q')!r} applyHold={last.get('h')!r} {RESET_S}s "
                              f"after its disconnect_to_menu (want 0 and false: the session reset drops the held "
                              f"applies, F5576)"]

    def c3():
        tops, t0 = [], time.time()
        while time.time() - t0 < fst.PAGE_S and top(host) != "DebriefingState":
            t = top(host)
            if t not in tops:
                tops.append(t)
            if t == "CoopState":
                ctx.setdefault("hostDialogs", []).append(fst.dialog(host))
                host.cmd({"cmd": "coop_dialog_back"})
            time.sleep(0.25)
        ctx["c3pre"] = {"tops": tops, "stack": stack(host)}
        return camp.host_ok_drain(host, ctx, "hostOk")
    return [
        ("1 the fenced host sale reaches the client's held apply queue", c1),
        ("2 the client's session reset drops the held applies and the hold", c2),
        ("3 the host's OK + drain reaches its geoscape", c3),
    ]


def main():
    t0, results, walls = time.time(), {}, {}
    run_boot("G", TAG, PORT, None, pre_g, (("D2g", d2g_cells),), results, walls)
    ok = bool(results.get("D2g"))
    print(f"\ntest_w2_shared_apply_hold_reset: {int(ok)}/1 passed (pass={['D2g'] if ok else []} "
          f"fail={[] if ok else ['D2g']}) in {time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
