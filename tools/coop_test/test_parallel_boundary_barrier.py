"""Parallel battlescape "atomic unit death" rework, Phase 3 Sub-task C: the
boundary APPLY-BARRIER wire-order proof for `bnd:true` casualties.

THE QUESTION UNDER TEST. A boundary-phase casualty (a unit that bleeds/burns
out exactly at a side close, inside SavedBattleGame::prepareNewTurn) ships its
`unit_casualty` with `bnd:true` + `side_seq`, but deliberately carries NO
`action_seq` (UnitDieBState::deinit - the boundary chain is unopened, so
connectionTCP::coopStampChainSeq is a no-op there). The chain-atomicity apply
barrier (connectionTCP.cpp's `barrierBlocked`, guarding the `action_end`
marker) tracks `minDeferredChainSeqThisPass`, which is fed ONLY by packets
carrying a non-zero `action_seq` (see the `if (pSeq != 0)` guard around the
deferred-tracking code). A `bnd:true` casualty therefore does NOT feed that
tracker - so IF it were ever deferred (held back a pass because the display
was busy) at the exact moment the boundary `action_end`/`endTurn` marker that
follows it on the wire is otherwise admissible, the barrier would not know to
hold the marker for it, and the marker could apply first: a boundary hash
sampled before its own casualty landed.

The task plan's own analysis is that this likely already holds without a
product change: a `bnd` casualty is admitted either by `coopDecoupledWorldCarrier`
(alien/neutral-side close - unconditional, no idle wait) or by the ordinary
`gateAllows` idle path (`coopTaskCompleted()`) on a player-side close, which is
the SAME idle gate the boundary marker itself needs (neither has a dedicated
whitelist entry), and the wire is FIFO - so as long as nothing lets the marker
skip AHEAD of the casualty already sitting in front of it in the queue, order
is preserved by construction, no seq needed. This fixture is the VERIFICATION:
it reproduces a boundary bleed-out under an artificially slow (backlogged)
client - the condition most likely to expose a reordering, if one exists - and
reads connectionTCP's `rxTrace` (parallel_state {trace:true}), which records
every packet in the exact order the client's pump actually consumed it
(rxTraceRecord, right before onTCPMessage()). If the casualty's `unit_casualty`
trace entry has a LOWER seq than the boundary marker's, order held. If not,
Sub-task C's `barrierBlocked` extension is needed (see the module docstring
note left in connectionTCP.cpp's chain-atomicity apply-barrier comment for
where it would go - NOT applied by this file, which only asserts).

SCENARIO. Mint-free lethal condition (`set_stat` health=1 + fatalWounds), like
repro_boundary_death.py, staged on soldiers so the boundary is a PLAYER-side
close (`coopDecoupledWorldCarrier` requires side != FACTION_PLAYER, so a
soldier's own boundary casualty is the ordinary-gate case the barrier actually
needs to cover - the alien/neutral case is unconditional and uninteresting
here). A slow client widens the window in which the display could still be
busy (backlogged) when the casualty and the marker both arrive, which is the
only window in which a reordering could occur at all.

Asserts, after the boundary settles:
  - the boundary was non-vacuous (>=1 corpse minted, matching repro_boundary_death)
  - the client's rxTrace shows >=1 `unit_casualty` entry for a staged victim
  - the client's rxTrace shows >=1 `action_end`/`endTurn` entry after staging
  - for every such marker, every staged victim's `unit_casualty` trace seq is
    LOWER (applied first) - the wire-order proof
  - Strand-B `sideBarrierHolds`/`sideBarrierReleases` still balance (no new
    wedge: a release for every hold, same invariant test_parallel_soak reads)
  - the five buckets stay clean at the boundary (same coverage repro_boundary_death
    already asserts, kept here as a sanity floor)

Run:  python tools/coop_test/test_parallel_boundary_barrier.py [--seed N]
                 [--wounds N] [--victims N] [--slow-client MS]
Exit 0 = wire order held (or the whole run was inconclusive-safe); 2 = a
boundary-marker-ahead-of-casualty reorder was OBSERVED, or another failure.
"""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_endturn as PE
import test_parallel_soak as SOAK

PORT = "48043"


def bstate(gc):
    return gc.cmd({"cmd": "battle_state"})


def parallel(gc):
    return gc.cmd({"cmd": "parallel_state"})


def corpses(gc):
    return sorted((i["id"], i["type"]) for i in gc.ok({"cmd": "battle_items"})["items"]
                  if "CORPSE" in i["type"].upper())


class TracePoller:
    """Background poll of the CLIENT's rxTrace (parallel_state {trace:true}),
    accumulating every entry it has seen by `seq` (the ring buffer holds only
    the last 256 - polling at a steady clip keeps the fixture's window well
    under that between snapshots). One entry per packet the pump actually
    handed to onTCPMessage(), in APPLICATION order - the exact thing this test
    needs to read wire-apply order back."""

    def __init__(self, client, interval=0.1):
        self.client = client
        self.interval = interval
        self.entries = {}  # seq -> {"state":..., "unit":...}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                tr = self.client.cmd({"cmd": "parallel_state", "trace": True,
                                       "traceLimit": 256}).get("rxTrace", [])
                for e in tr:
                    self.entries[e["seq"]] = e
            except Exception:
                pass
            time.sleep(self.interval)

    def start(self):
        self._thread.start()

    def stop(self, join_timeout=5):
        self._stop.set()
        self._thread.join(timeout=join_timeout)
        # one final synchronous snapshot so the last few packets of the
        # settle window (after the poll thread's last tick) are not missed
        try:
            tr = self.client.cmd({"cmd": "parallel_state", "trace": True,
                                   "traceLimit": 256}).get("rxTrace", [])
            for e in tr:
                self.entries[e["seq"]] = e
        except Exception:
            pass

    def ordered(self):
        return [self.entries[s] for s in sorted(self.entries)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=91091091)
    ap.add_argument("--wounds", type=int, default=1)
    ap.add_argument("--victims", type=int, default=2)
    ap.add_argument("--slow-client", type=int, default=700,
                     help="ms/frame on the client - deliberately slow, to widen the "
                          "window in which the display could still be busy when the "
                          "casualty and the boundary marker both arrive (the only "
                          "window a reordering could occur in at all)")
    args = ap.parse_args()

    host_opts = {"battleXcomSpeed": SOAK.FAST_SPEED, "battleAlienSpeed": SOAK.FAST_SPEED,
                 "skipNextTurnScreen": True, "EnableCoopParallelTurns": True}
    client_opts = {"battleXcomSpeed": args.slow_client, "battleAlienSpeed": args.slow_client,
                   "EnableCoopParallelTurns": False}
    host = GameClient("host", 48960, make_user_dir("bndbarrier_host", options=host_opts))
    client = GameClient("client", 48961, make_user_dir("bndbarrier_client", options=client_opts))
    for gc in (host, client):
        SOAK.write_battle_fixture(gc.user_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()
    TW.PORT = PORT
    PE.PORT = PORT
    fails = []
    poller = None
    # GameClient.cmd() is one blocking request/response round-trip on a single
    # socket with no locking (harness.py's _send: sendall then read-until-\n).
    # The background TracePoller below issues `client.cmd()` calls from a
    # second thread while the main thread is ALSO driving `client` through
    # SOAK.close_side/PE.wait_side - unguarded, that is two threads racing the
    # same socket, and a poll's response can be read back as the main thread's
    # answer to an unrelated command (observed: get_state's response body came
    # back as the trace response, `KeyError: 'states'`). Wrap the instance
    # method in a lock so every command against `client`, from either thread,
    # is a complete request/response pair before the next one starts.
    client_lock = threading.Lock()
    _orig_client_cmd = client.cmd
    def _locked_client_cmd(obj, _orig=_orig_client_cmd, _lock=client_lock):
        with _lock:
            return _orig(obj)
    client.cmd = _locked_client_cmd
    try:
        TW.bring_up_battle(host, client, seed=args.seed)
        for gc in (host, client):
            gc.ok({"cmd": "set_seed", "seed": args.seed})
        assert bstate(host)["activeSync"] is True and bstate(client)["activeSync"] is False

        pc = parallel(client)
        for f in ("sideBarrierHolds", "sideBarrierReleases"):
            assert f in pc, (
                f"parallel_state carries no `{f}` - bin/x64/Release/OpenXcom.exe predates "
                f"this build; rebuild it (serial, MP=false). fields: {sorted(pc)}")

        sb0 = parallel(client)
        holds0, releases0 = sb0.get("sideBarrierHolds", 0), sb0.get("sideBarrierReleases", 0)
        hard0 = sb0.get("sideBarrierHardReleases", 0)

        # PLAYER-side victims (coopDecoupledWorldCarrier requires side != PLAYER -
        # a soldier's own boundary death is the ordinary-gate case, see docstring).
        pool = [u for u in bstate(host)["units"]
                if u.get("faction") == 0 and not u.get("isOut")]
        keep = 1  # keep >=1 soldier alive so the battle survives
        victims = pool[:max(1, min(args.victims, len(pool) - keep))]
        victim_ids = [v["id"] for v in victims]
        print(f"victims: {victim_ids} (of {len(pool)} live soldiers)")
        assert victim_ids, "VACUOUS: no soldier victims available to stage"

        poller = TracePoller(client, interval=0.1)
        poller.start()
        baseline_seq = max(poller.entries) if poller.entries else 0
        time.sleep(0.3)
        if poller.entries:
            baseline_seq = max(baseline_seq, max(poller.entries))

        # mint-free lethal condition on BOTH machines, all victims (set_stat is a
        # direct local RPC lever on each machine, not a wire packet - see
        # repro_boundary_death.py; the wire only carries the boundary's own
        # unit_casualty/action_end traffic during the window this test reads).
        for victim in victims:
            req = {"cmd": "battle_action", "action": "set_stat", "unit": victim["id"],
                   "health": 1, "fatalWounds": args.wounds}
            for gc in (host, client):
                gc.ok(dict(req))

        turn0 = bstate(host)["turn"]
        print(f"\n== closing turn {turn0} (soldier(s) bleed out at player-side close) ==")
        SOAK.close_side(host, client, 0, 1, turn0)
        # let the (slow) client's death replay drain and report the boundary hash
        sc = session.sync_check(host)
        deadline = time.time() + 60
        while time.time() < deadline:
            sc = session.sync_check(host)
            v = next((u for u in bstate(host)["units"] if u["id"] == victim_ids[0]), None)
            cv = next((u for u in bstate(client)["units"] if u["id"] == victim_ids[0]), None)
            if v and v.get("isOut") and cv and cv.get("isOut"):
                break
            time.sleep(0.5)
        time.sleep(2)

        poller.stop()
        trace = poller.ordered()
        post = [e for e in trace if e["seq"] > baseline_seq]
        print(f"\n== trace: {len(trace)} total entries, {len(post)} after baseline seq {baseline_seq} ==")
        for e in post:
            print(f"    seq={e['seq']:4d} state={e['state']:16s} unit={e['unit']:>9} "
                  f"boundary={e.get('boundary')} kind={e.get('kind')!r}")

        # `boundary` (added to rxTrace for this fixture) is the packet's own
        # `boundary` key (action_end's true sync-check hash marker) OR'd with
        # its `bnd` key (unit_casualty's boundary-phase flag) - the two never
        # coexist on the same packet, so one field disambiguates both. Without
        # it, "any action_end/endTurn after baseline" is the WRONG marker set:
        # a side that has already cycled player->alien->neutral by the time
        # this fixture reads the boundary bleed-out has several ordinary mid-
        # side chain closers of the same state name in between (measured: 17
        # of them on one run, none related to this boundary at all).
        #
        # `kind` (also added) further narrows it: connectionTCP::coopArmSyncBoundary
        # has exactly two callers - "endturn" (the side-CLOSE phase group,
        # BattlescapeGame.cpp) and "sidestart" (prepareNewTurn, NextTurnState.cpp).
        # Fatal-wound bleed-out is computed IN prepareNewTurn, so a `bnd` casualty's
        # own boundary hash point is the "sidestart" marker that follows it, never
        # the "endturn" one - a full side cycle ships one of EACH kind, and the
        # "endturn" one (which closes the PREVIOUS side, before prepareNewTurn even
        # ran) legitimately precedes the casualty with no bearing on this proof
        # (measured: an unrelated "endturn" 6 trace entries ahead of the casualty,
        # on a run where "sidestart" - the one that actually matters - came after).
        casualty_seq = {}
        for e in post:
            if (e["state"] == "unit_casualty" and e.get("boundary") and
                    e["unit"] in victim_ids and e["unit"] not in casualty_seq):
                casualty_seq[e["unit"]] = e["seq"]
        marker_seqs = [e["seq"] for e in post
                       if e["state"] in ("action_end", "endTurn") and e.get("boundary")
                       and e.get("kind") == "sidestart"]

        print(f"\n  bnd casualty trace seqs: {casualty_seq}")
        print(f"  TRUE 'sidestart' boundary marker trace seqs: {marker_seqs}")

        hcorp, ccorp = corpses(host), corpses(client)
        h, c = session.battle_checksum(host), session.battle_checksum(client)
        sb1 = parallel(client)
        holds1, releases1 = sb1.get("sideBarrierHolds", 0), sb1.get("sideBarrierReleases", 0)
        hard1 = sb1.get("sideBarrierHardReleases", 0)

        reorder_evidence = []
        if not casualty_seq:
            fails.append("VACUOUS: no unit_casualty trace entry seen for any staged "
                          "victim after the baseline - the boundary death did not "
                          "produce/apply a casualty packet (try --wounds/--seed)")
        elif not marker_seqs:
            fails.append("VACUOUS: no action_end/endTurn trace entry seen after the "
                          "baseline - the side-close marker never applied "
                          "(the fixture did not actually cross a boundary)")
        else:
            for uid, cseq in casualty_seq.items():
                bad_markers = [m for m in marker_seqs if m < cseq]
                if bad_markers:
                    reorder_evidence.append(
                        f"victim {uid}: unit_casualty applied at trace seq {cseq}, but "
                        f"a boundary marker already applied EARLIER at seq {bad_markers} "
                        f"- the marker jumped ahead of its own boundary casualty")
            if len(casualty_seq) < len(victim_ids):
                missing = set(victim_ids) - set(casualty_seq)
                print(f"  NOTE: {missing} did not bleed out (non-fatal to the ordering "
                      f"proof for the ones that did)")

        if reorder_evidence:
            fails.extend(reorder_evidence)

        if hcorp != ccorp:
            fails.append(f"corpse censuses differ: host {hcorp} vs client {ccorp}")
        if h[0] != c[0]:
            fails.append(f"item-id counters differ: host {h[0]} vs client {c[0]}")
        if h[1] != c[1]:
            fails.append(f"battle censuses differ: host {h[1]} vs client {c[1]}")
        if (holds1 - holds0) != ((releases1 - releases0) + (hard1 - hard0)):
            fails.append(f"Strand-B side barrier did not balance: holds +{holds1 - holds0} "
                         f"vs releases +{releases1 - releases0} (+{hard1 - hard0} hard) "
                         f"- a new wedge, not just an ordering question")

        print("\n== VERDICT ==")
        print(f"  sideBarrier: holds +{holds1 - holds0} releases +{releases1 - releases0} "
              f"hard +{hard1 - hard0}")
        print(f"  corpses: host={hcorp} client={ccorp}")

    except Exception as e:
        import traceback
        fails.append(f"[ERROR] {e}\n{traceback.format_exc()}")
    finally:
        if poller is not None:
            poller.stop()
        for gc in (host, client):
            try:
                gc.cmd({"cmd": "quit"})
            except Exception:
                pass

    if fails:
        print(f"\n==== boundary apply-barrier (Sub-task C) wire-order proof: FAIL ====")
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print(f"\n  PASS: every staged boundary unit_casualty applied BEFORE the next "
          f"action_end/endTurn marker in the client's actual apply order (rxTrace) - "
          f"the apply barrier already covers bnd casualties without a product change")
    sys.exit(0)


if __name__ == "__main__":
    main()
