#!/usr/bin/env python3
# RW-TRIAGE: TOOLING-PENDING(W6)
"""Run the coop test suite across K non-colliding harness lanes at once.

Each lane is a slot (OXC_HARNESS_SLOT=k) that harness.py isolates: a per-slot
machine lock and s{slot}_-prefixed user dirs (see harness.py). Ports are now
OS-assigned ephemeral for every instance, so lanes no longer need disjoint port
bands - the isolation is purely the lock + user dirs. This runner owns all K
slots for the duration of a run; another session on the same machine can still
run its own lane(s) because a different slot never shares user dirs or lock with
this one, and slot 0 keeps the legacy lock so it serialises against a
non-slotted / old-harness run.

    python tools/coop_test/run_parallel.py                 # whole suite, K=4
    python tools/coop_test/run_parallel.py -k 4 test_shared_battle test_geoscape_sync
    python tools/coop_test/run_parallel.py --file batch.txt --json out.json
    python tools/coop_test/run_parallel.py --list-only      # print the plan

Assignment: timing-sensitive families (PINNED, below) are locked to slot 0 - the
serial lane - so contention from the other lanes never perturbs a clock- or
dogfight-timing assertion. Everything else is greedy-LPT bin-packed across all K
lanes by measured weight (tools/ci/test_weights.json, same table the CI shard
planner uses). Each lane runs its queue serially as subprocesses; a nonzero exit
is retried once (flake tolerance, matching tools/ci/run_coop_suite.ps1) and only
the last attempt's duration is reported. Exit 0 iff every test ended PASS.

Headless is forced on every lane (SDL_VIDEODRIVER/AUDIODRIVER=dummy) unless
OXC_HARNESS_WINDOWED=1 is exported for interactive debugging.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

TESTDIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTDIR))
WEIGHTS_FILE = os.path.join(REPO, "tools", "ci", "test_weights.json")
BUDGET_FILE = os.path.join(TESTDIR, "slow_test_exceptions.json")

# Per-test time budgets (seconds), the same ones tools/ci/run_coop_suite.ps1 enforces
# in CI (both read slow_test_exceptions.json). A test that FINISHES over its budget
# fails even if it passed; a test still running at hard-kill x its budget is killed
# (with its game subtree) and failed, so a hang is always bounded. These are the
# fallbacks if the JSON is missing.
DEFAULT_BUDGET = 180.0
HARD_KILL_MULT = 2.0
MAX_BUDGET = 900.0

# --- PINNED: timing-sensitive families locked to slot 0 (the serial lane) ----
# These either deliberately measure timing (speed_skew), drive a real-time
# minigame that both machines animate in lockstep (the heavy dogfights), lean on
# the geoscape clock (month_run), or carry a documented clock-race flake
# (ufo_notice, manufacture, commerce). Run concurrently with the parallel lanes
# their assertions go soft under CPU contention, so they run one-at-a-time on
# slot 0 instead. The A/B flake-parity validation (see the session report) is
# what promotes a family here: any test that flakes only at K>1 gets added.
#
# NOTE the two "joint_*" families named in the original audit were renamed
# SHARED long ago (see MEMORY: joint->shared 2026-07-21); the live tests are
# test_shared_disconnect / test_shared_resync.
#
# NOT pinned wholesale: ~21 tests import geo.skip_realtime (mostly short
# geoscape/dogfight checks that skip only a few seconds and tolerate contention).
# Pinning all of them would make slot 0 the long pole and gut the speedup. The
# A/B batch measures parity and promotes the ones that actually need it; the
# candidate list (skip_realtime users) is recorded in the session report.
PINNED = frozenset((
    "test_parallel_soak",
    "test_parallel_speed_skew",
    "test_sync_check",
    "test_shared_month_run",
    "test_shared_intercept_spectate",
    "test_shared_hk_dogfight",
    "test_shared_dogfight_concurrent",
    "test_ufo_notice",
    "test_shared_manufacture",
    "test_shared_commerce",
    "test_shared_disconnect",   # audit's test_joint_disconnect (renamed)
    "test_shared_resync",       # audit's test_joint_resync (renamed)
))

# Ports are ephemeral now, so there is no port-band ceiling on K. The default
# cap stays 4 as a machine-resource guard: each lane runs a live host+client
# game pair, so K lanes = 2K game processes contending for CPU. Raise it if the
# host has the cores/RAM to spare.
MAX_SAFE_SLOTS = 4


def discover():
    """boot_check + every test_*.py, by basename, sorted. Same discovery as
    tools/ci/run_coop_suite.ps1 so the two runners can never disagree."""
    names = []
    boot = os.path.join(TESTDIR, "boot_check.py")
    if os.path.exists(boot):
        names.append("boot_check")
    for fn in sorted(os.listdir(TESTDIR)):
        if fn.startswith("test_") and fn.endswith(".py"):
            names.append(fn[:-3])
    return names


def load_weights():
    try:
        with open(WEIGHTS_FILE, encoding="utf-8") as f:
            return {k: float(v) for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def load_budget():
    """Read slow_test_exceptions.json -> (default_budget, hard_kill_mult, {test: budget}).
    Shared verbatim with tools/ci/run_coop_suite.ps1. Errors out if any exception
    exceeds max_budget_s - there are no unlimited budgets."""
    default_budget, hard_mult, max_budget = DEFAULT_BUDGET, HARD_KILL_MULT, MAX_BUDGET
    exceptions = {}
    try:
        with open(BUDGET_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return default_budget, hard_mult, exceptions
    default_budget = float(cfg.get("default_budget_s", default_budget))
    hard_mult = float(cfg.get("hard_kill_multiplier", hard_mult))
    max_budget = float(cfg.get("max_budget_s", max_budget))
    for name, spec in (cfg.get("exceptions") or {}).items():
        b = float(spec["budget_s"])
        if b > max_budget:
            raise SystemExit("slow_test_exceptions.json: %s budget %gs exceeds "
                             "max_budget_s %gs (no unlimited budgets)" % (name, b, max_budget))
        exceptions[name] = b
    return default_budget, hard_mult, exceptions


def assign(tests, slots, weights):
    """Pinned tests -> slot 0 (serial lane); the rest greedy-LPT across all K
    lanes by weight. Returns a list of K queues (each a list of test names)."""
    median = 10.0
    known = sorted(weights[t] for t in tests if t in weights)
    if known:
        median = known[len(known) // 2]
    wt = lambda t: weights.get(t, median)

    queues = [[] for _ in range(slots)]
    load = [0.0] * slots

    pinned = sorted((t for t in tests if t in PINNED), key=wt, reverse=True)
    for t in pinned:
        queues[0].append(t)
        load[0] += wt(t)

    rest = sorted((t for t in tests if t not in PINNED), key=wt, reverse=True)
    for t in rest:
        i = min(range(slots), key=lambda k: load[k])   # lightest lane
        queues[i].append(t)
        load[i] += wt(t)
    return queues, load, median


def _kill_tree(proc):
    """Kill the timed-out test process AND the game subtree it spawned - only
    this runner's own descendants, never a foreign session's."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=15)
    except Exception:
        proc.kill()


def _run_once(name, slot, base_env, hard_timeout):
    path = os.path.join(TESTDIR, name + ".py")
    env = dict(base_env)
    env["OXC_HARNESS_SLOT"] = str(slot)
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, path], env=env)
    try:
        rc = proc.wait(timeout=hard_timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        rc = 124
        timed_out = True
    return rc, round(time.time() - t0, 1), timed_out


def _run_lane(slot, queue, base_env, results, lock, run_start, quiet, budget_cfg):
    default_budget, hard_mult, exceptions = budget_cfg
    for name in queue:
        budget = exceptions.get(name, default_budget)
        hard = max(1.0, budget * hard_mult)
        s0 = round(time.time() - run_start, 1)
        rc, secs, timed_out = _run_once(name, slot, base_env, hard)
        attempts = 1
        if rc != 0 and not timed_out:   # retry a real failure once; never retry a hang
            rc, secs, timed_out = _run_once(name, slot, base_env, hard)
            attempts = 2
        e0 = round(time.time() - run_start, 1)
        over_budget = (rc == 0 and not timed_out and secs > budget)
        status = "FAIL" if (timed_out or rc != 0 or over_budget) else "PASS"
        reason = None
        if timed_out:
            reason = ("BUDGET HARD-KILL: %s still running after %.1fs (%gx its %gs "
                      "budget) - killed as a hung test"
                      % (name, budget * hard_mult, hard_mult, budget))
        elif over_budget:
            reason = ("BUDGET EXCEEDED: %s took %.1fs > %gs budget - re-engineer the "
                      "test or add a justified exception" % (name, secs, budget))
        rec = {"test": name, "slot": slot, "status": status, "seconds": secs,
               "attempts": attempts, "rc": rc, "timed_out": timed_out,
               "budget": budget, "over_budget": over_budget, "reason": reason,
               "start": s0, "end": e0}
        with lock:
            results.append(rec)
            if not quiet:
                note = []
                if attempts > 1:
                    note.append("retried")
                if timed_out:
                    note.append("HANG rc=124")
                elif rc != 0:
                    note.append("rc=%d" % rc)
                elif over_budget:
                    note.append("over %gs budget" % budget)
                suffix = " (%s)" % ", ".join(note) if note else ""
                print("[slot %d] %-11s %8.1fs  %s%s"
                      % (slot, status, secs, name, suffix), flush=True)
                if reason:
                    print("  !! %s" % reason, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tests", nargs="*", help="test names/paths; default = whole suite")
    ap.add_argument("-k", "--slots", type=int, default=MAX_SAFE_SLOTS,
                    help="number of lanes (default %d; >%d is CPU-bound, not "
                         "port-bound)" % (MAX_SAFE_SLOTS, MAX_SAFE_SLOTS))
    ap.add_argument("--file", help="read test names from this file, one per line")
    ap.add_argument("--json", help="write machine-readable results here")
    ap.add_argument("--list-only", action="store_true", help="print the plan and exit")
    ap.add_argument("--quiet", action="store_true", help="suppress the per-test lines")
    args = ap.parse_args()

    if args.slots < 1:
        ap.error("--slots must be >= 1")
    if args.slots > MAX_SAFE_SLOTS:
        print("WARNING: K=%d exceeds the default %d lanes; ports are ephemeral so "
              "this is a CPU/RAM concern (2K game processes), not a port limit - "
              "proceeding as asked." % (args.slots, MAX_SAFE_SLOTS),
              file=sys.stderr)

    names = []
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            names += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    names += list(args.tests)
    names = [n[:-3] if n.endswith(".py") else os.path.basename(n) for n in names]
    if not names:
        names = discover()
    # de-dup, keep order
    seen = set()
    tests = [n for n in names if not (n in seen or seen.add(n))]

    missing = [t for t in tests if not os.path.exists(os.path.join(TESTDIR, t + ".py"))]
    if missing:
        ap.error("no such test(s): %s" % ", ".join(missing))

    weights = load_weights()
    budget_cfg = load_budget()
    default_budget, hard_mult, exceptions = budget_cfg
    queues, load, median = assign(tests, args.slots, weights)

    print("plan: %d test(s) -> %d lane(s), weights from %s (median %.0fs)"
          % (len(tests), args.slots,
             os.path.relpath(WEIGHTS_FILE, REPO) if weights else "none", median))
    print("budgets: default %gs, hard-kill %gx, %d exception(s) from %s"
          % (default_budget, hard_mult, len(exceptions),
             os.path.relpath(BUDGET_FILE, REPO) if exceptions else "defaults"))
    for k in range(args.slots):
        pinned_here = sum(1 for t in queues[k] if t in PINNED)
        print("  slot %d: %2d test(s), ~%6.0fs%s"
              % (k, len(queues[k]), load[k],
                 "  (%d pinned)" % pinned_here if pinned_here else ""))
    if args.list_only:
        for k in range(args.slots):
            print("--- slot %d ---" % k)
            for t in queues[k]:
                print("  %s%s" % (t, "  [PIN]" if t in PINNED else ""))
        return 0

    base_env = os.environ.copy()
    if not base_env.get("OXC_HARNESS_WINDOWED"):
        base_env["SDL_VIDEODRIVER"] = "dummy"
        base_env["SDL_AUDIODRIVER"] = "dummy"

    results = []
    lock = threading.Lock()
    run_start = time.time()
    threads = [threading.Thread(target=_run_lane,
                                args=(k, queues[k], base_env, results, lock,
                                      run_start, args.quiet, budget_cfg))
               for k in range(args.slots) if queues[k]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = round(time.time() - run_start, 1)

    results.sort(key=lambda r: r["seconds"], reverse=True)
    fails = [r for r in results if r["status"] != "PASS"]
    serial = round(sum(r["seconds"] for r in results), 1)
    lane_busy = [round(sum(r["seconds"] for r in results if r["slot"] == k), 1)
                 for k in range(args.slots)]

    print("\n%-30s %-6s %8s %8s %4s %s"
          % ("TEST", "VERD", "SECS", "BUDGET", "ATT", "SLOT"))
    for r in results:
        print("%-30s %-6s %8.1f %8g %4d   %d%s"
              % (r["test"], r["status"], r["seconds"], r["budget"], r["attempts"],
                 r["slot"], "  <-- FAIL" if r["status"] != "PASS" else ""))

    print("\n%d test(s): %d passed, %d failed" % (len(results),
          len(results) - len(fails), len(fails)))
    print("wall-clock %.1fs | serial-sum %.1fs | speedup %.2fx | lanes %s"
          % (wall, serial, (serial / wall if wall else 0),
             "/".join("%.0f" % b for b in lane_busy)))
    if fails:
        print("FAILED: %s" % ", ".join(r["test"] for r in fails))
        for r in fails:
            if r.get("reason"):
                print("  !! %s" % r["reason"])

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"slots": args.slots, "wall": wall, "serial": serial,
                       "speedup": round(serial / wall, 3) if wall else 0,
                       "lane_busy": lane_busy, "results": results}, f, indent=2)
        print("wrote %s" % args.json)

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
