"""W2-P7 S-C-A - test_w2_battle_end_campaign_fence.py: the stream fence (MR3, F2129, F2496). A shared command the
host submits while its post-battle world streams to the second player is neither lost nor doubled: the host defers
it until the stream's completion message has left (the fence's HOST half, T0-S1 CONFIRMED F4760/F4761), the client
holds the resulting shared_apply until it has adopted the streamed world in place, then applies it onto that world
(docs rewrite/prompts/w2p7_sc_design.md section 3.1 step 7, AMENDMENT P7-6 section 4.1 row C28S-f, PR-6, PR-11, the
P7-6 TASK 0 RULINGS; owner D156 (a), D176; MR1, MR3).

Fixture (one boot; the C28S fixture of test_w2_battle_end_campaign.py, imported): the SHARED battle on SEED_S, then,
before the ending, the two TEST-ONLY holds (AMENDMENT P7-6 PR-11): host hold_world_stream {on: true} (the streamer
parks before its final MAP_RESULT_LOAD_PROGRESS, so sendFileClient stays set and the host log says "[coop-test]
hold_world_stream: holding"), client hold_world_adopt {on: true} (S-C-A.2's adoption step skips). The item is T0-6's
recovered SELL_ITEM ("Plasma Pistol", 8 recovered: CONSTANTS T0-6 (ii) / HOST_DEBRIEF) - base 0 holds none before the
battle, so its count at the host's debriefing is the debriefing's own (DEBRIEF_QTY, checked pre-cell).

Row C28S-f (AMENDMENT P7-6 section 4.1). GREEN cells, in order; a failed cell ends the row ("not reached" after it):
  (1) both debrief_state equal (PR-10 stripped); the client's shown, on top and display-only (as C28S (1)).
  (2) the host's stream is parked (the hold line in the host log within ADOPT_S); the host's `sell {SELL_ITEM, 1}`
      from a base screen; host battleEnd.fenceDeferredPasses >= 1 within FENCE_S while the host's count stays
      DEBRIEF_QTY (the command waits behind the fence).
  (3) release the host hold; the client's shared_stats.applyQueued >= 1 within ADOPT_S while its hold is armed, with
      worldHeld >= 1 and worldAdopted 0.
  (4) release the client hold; its battleEnd.worldAdopted 1 and heldAppliesAtAdopt >= 1 within ADOPT_S.
  (5) after the adoption: SELL_ITEM's base-0 count and the funds equal on both machines within EQUAL_S, and the
      count is exactly DEBRIEF_QTY - 1 (the sale neither lost nor doubled).
Pre-cell guard as test_w2_battle_end_campaign.py, plus the holds armed and the host's base-0 SELL_ITEM count ==
DEBRIEF_QTY at its debriefing; over the whole row: no new crash log.

RED (commit S-C-A.1): the row fails on exactly cell 1 - the client never shows a DebriefingState. The holds are inert
on that build (no post-battle push, no adoption step). GREEN (commit S-C-A.2): the row passes.
ONE "EVIDENCE C28S-f:" line, then "PASS C28S-f" or "FAIL C28S-f: <message>". WV-D95/D99/D100: ONE foreground run,
no skip path; exit 0 only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_battle_end_campaign_fence.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_w2_battle_end_campaign as camp
from test_w2_battle_end_campaign import (record, wait_until, log_count, capture, cell_debriefs, ADOPT_S, EQUAL_S,
                                         HOST_DEBRIEF)

PORT = "47216"               # AMENDMENT P7-6 section 4 (F4545): the fence file = 47216-47218
TAG = "w2p7sca_c28sf"
BASE = "HostBase"            # shared_fixture.bring_up's host_base (base 0)
SELL_ITEM = "STR_PLASMA_PISTOL"
DEBRIEF_QTY = next(r["qty"] for r in HOST_DEBRIEF["recovered"] if r["item"] == "Plasma Pistol")   # 8 (T0-6 (ii))
FENCE_S = 3                  # host fenceDeferredPasses >= 1 after the sell (one pump pass is ~16 ms)
HOLD_LINE = "[coop-test] hold_world_stream: holding"


def base_count(gc):
    for b in gc.cmd({"cmd": "geo_state"}).get("bases", []) or []:
        if b.get("name") == BASE:
            return (b.get("items") or {}).get(SELL_ITEM, 0)
    return None


def funds(gc):
    return gc.cmd({"cmd": "geo_state"}).get("funds")


def stage_fence(rid, js, ctx):
    """The C28S stage with both holds armed before the ending, then the debriefing's SELL_ITEM count on the host."""
    camp.stage(rid, js, ctx, wound=False, holds=True)
    d = base_count(js.host)
    ctx["debriefQty"] = d
    if d != DEBRIEF_QTY:
        capture("debriefing count", f"host {BASE} {SELL_ITEM}={d!r} at its debriefing (want {DEBRIEF_QTY})",
                (js.host, js.client))


def fence_cells(host, client, ctx):
    def parked_sell():
        ok, secs = wait_until(lambda: log_count(host, HOLD_LINE) >= 1, ADOPT_S)
        ctx["parked"] = {"reached": ok, "secs": secs}
        if not ok:
            return [f"the host's world stream never parked within {ADOPT_S}s (no '{HOLD_LINE}' line)"]
        r = host.cmd({"cmd": "sell", "item": SELL_ITEM, "count": 1, "base": BASE})
        ok, secs = wait_until(lambda: (record(host).get("fenceDeferredPasses") or 0) >= 1, FENCE_S, 0.1)
        n, c = record(host).get("fenceDeferredPasses"), base_count(host)
        ctx["sell"] = {"resp": {k: r.get(k) for k in ("ok", "sent", "error")}, "fenceDeferredPasses": n,
                       "hostCount": c, "secs": secs}
        f = [] if r.get("ok") and r.get("sent") else [f"host sell answered {ctx['sell']['resp']}"]
        if not ok:
            f.append(f"host battleEnd.fenceDeferredPasses={n!r} {FENCE_S}s after the sell (want >= 1)")
        if c != DEBRIEF_QTY:
            f.append(f"host {SELL_ITEM}={c!r} while the stream is parked (want {DEBRIEF_QTY}: the sale waits)")
        return f

    def release_host():
        ctx["releaseHost"] = host.cmd({"cmd": "hold_world_stream", "on": False})
        ok, secs = wait_until(lambda: (client.cmd({"cmd": "shared_stats"}).get("applyQueued") or 0) >= 1, ADOPT_S)
        q, crec = client.cmd({"cmd": "shared_stats"}).get("applyQueued"), record(client)
        ctx["queued"] = {"applyQueued": q, "secs": secs, "worldHeld": crec.get("worldHeld"),
                         "worldAdopted": crec.get("worldAdopted")}
        f = [] if ok else [f"client shared_stats.applyQueued={q!r} {ADOPT_S}s after the host's release (want >= 1)"]
        if not isinstance(crec.get("worldHeld"), int) or crec.get("worldHeld") < 1:
            f.append(f"client battleEnd.worldHeld={crec.get('worldHeld')!r} (want >= 1)")
        if crec.get("worldAdopted") != 0:
            f.append(f"client battleEnd.worldAdopted={crec.get('worldAdopted')!r} while its hold is armed (want 0)")
        return f

    def release_client():
        ctx["releaseClient"] = client.cmd({"cmd": "hold_world_adopt", "on": False})
        ok, secs = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
        crec = record(client)
        ctx["adopt"] = {"secs": secs, "worldAdopted": crec.get("worldAdopted"),
                        "heldAppliesAtAdopt": crec.get("heldAppliesAtAdopt")}
        f = [] if ok else [f"client battleEnd.worldAdopted={crec.get('worldAdopted')!r} {ADOPT_S}s after its release "
                           f"(want 1)"]
        h = crec.get("heldAppliesAtAdopt")
        if not isinstance(h, int) or h < 1:
            f.append(f"client battleEnd.heldAppliesAtAdopt={h!r} (want >= 1)")
        return f

    def equal_after():
        last = {}

        def same():
            last["h"], last["c"] = (base_count(host), funds(host)), (base_count(client), funds(client))
            return last["h"] == last["c"] and last["h"][0] == DEBRIEF_QTY - 1
        ok, secs = wait_until(same, EQUAL_S)
        ctx["after"] = {"secs": secs, "host": last.get("h"), "client": last.get("c")}
        if ok:
            return []
        return [f"(SELL_ITEM count, funds) host {last.get('h')} client {last.get('c')} after {EQUAL_S}s (want equal, "
                f"count {DEBRIEF_QTY - 1}: the sale neither lost nor doubled)"]

    return [
        ("1 both debriefings, the client's display-only", lambda: cell_debriefs(host, client, ctx)),
        ("2 the host sells while its world stream is parked; the fence defers it", parked_sell),
        ("3 the host's release; the client queues the apply while it holds the adoption", release_host),
        ("4 the client's release; it adopts with the queued apply held", release_client),
        ("5 the sale landed once on both machines", equal_after),
    ]


def main():
    t0, results, walls = time.time(), {}, {}
    # test_w2_battle_end_campaign.run_row: the same EVIDENCE / PASS / FAIL shape; it releases both holds before the
    # shutdown.
    camp.run_row("C28S-f", TAG, PORT, stage_fence, fence_cells, results, walls, holds=True)
    ok = bool(results.get("C28S-f"))
    print(f"\ntest_w2_battle_end_campaign_fence: {int(ok)}/1 passed (pass={['C28S-f'] if ok else []} "
          f"fail={[] if ok else ['C28S-f']}) in {time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
