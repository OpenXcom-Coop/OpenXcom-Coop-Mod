#!/usr/bin/env python3
"""Run the coop test suite across K non-colliding harness lanes at once.

Lane k runs on harness slot BASE+k (OXC_HARNESS_SLOT=BASE+k; BASE = --slot-base,
else the inherited OXC_HARNESS_SLOT, else 0, so a lane that exports its own slot,
e.g. lane 2's 4, runs K=2 on its own pair 4/5). harness.py isolates a slot by a per-slot
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
    python tools/coop_test/run_parallel.py -k 2 --slot-base 4 <names>   # slots 4/5
    python tools/coop_test/run_parallel.py -k 2 --log-dir L --fail-copy-dir F <names>

--log-dir L writes each test's stdout+stderr to L/<test>.log (unbuffered); without
it the K lanes interleave in one stream. --fail-copy-dir F copies, after a non-PASS
test and before its lane's next test, every s<slot>_* user dir of that lane whose
openxcom.log changed since the test started to F/<test>/ (S27).

Assignment: timing-sensitive families (PINNED, below) are locked to slot 0 - the
serial lane - so contention from the other lanes never perturbs a clock- or
dogfight-timing assertion. Everything else is greedy-LPT bin-packed across all K
lanes by measured weight (tools/ci/test_weights.json, same table the CI shard
planner uses). Each lane runs its queue serially as subprocesses. Exit taxonomy
(WV-D100/WV-D101, D59): 0 = PASS, any other exit code = FAIL. There is no SKIP
status: a fixture that cannot be built is a red (WV-D100: every test must exercise
its scenario 100% of the time; a test that cannot is rewritten with owner-supplied
fixture steps, never re-run). NOTHING is ever retried (WV-D101: "reruns just hide
flakiness"). A file whose column-0 guard prints SKIP-PENDING and exits 0 (the
W1_TRIAGE.md quarantine) is QUARANTINED (D62, D229): never counted as a pass,
listed and counted apart, and it does not fail the run. Exit 0 iff no test ended FAIL.

Headless is forced on every lane (SDL_VIDEODRIVER/AUDIODRIVER=dummy) unless
OXC_HARNESS_WINDOWED=1 is exported for interactive debugging.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

TESTDIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTDIR))
# The harness user-dir root, copied from harness.py :95-96 (this runner never imports harness).
TEMP_ROOT = os.environ.get("TEMP") or os.environ.get("TMPDIR") or tempfile.gettempdir()
TEST_ROOT = os.path.join(TEMP_ROOT, "oxc-coop-test")
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


def _copy_fail_dirs(name, slot, t0, fail_dir):
    """S27: copy this lane's s<slot>_* user dirs whose openxcom.log changed at or
    after the test's start - 1 s to fail_dir/<test>/<dir>. Returns the path or None."""
    dest = os.path.join(fail_dir, name)
    for d in sorted(glob.glob(os.path.join(TEST_ROOT, "s%d_*" % slot))):
        try:
            if os.path.getmtime(os.path.join(d, "openxcom.log")) >= t0 - 1.0:
                shutil.copytree(d, os.path.join(dest, os.path.basename(d)), dirs_exist_ok=True)
        except OSError as exc:  # no openxcom.log = not this test's dir; else a partial copy
            if os.path.isdir(os.path.join(dest, os.path.basename(d))):
                print("  !! fail copy of %s incomplete: %s" % (d, exc), flush=True)
    return dest if os.path.isdir(dest) else None


# D62 / D229: a quarantined file (W1_TRIAGE.md, RB-D21) carries a column-0 guard
# `print("SKIP-PENDING..."); sys.exit(0)`; such a file that exits 0 is QUARANTINED,
# never PASS. The guard is read from the source, so the status is the same with or
# without --log-dir (this runner captures a test's stdout only with --log-dir).
GUARD_RE = re.compile(r"""^print\(\s*["']SKIP-PENDING""")


def quarantine_marker(name):
    """The file's triage tag (its first line holding 'SKIP-PENDING(', stripped) when
    it has a column-0 SKIP-PENDING guard print; else None."""
    try:
        with open(os.path.join(TESTDIR, name + ".py"), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    if not any(GUARD_RE.match(ln) for ln in lines):
        return None
    return next((ln.strip() for ln in lines if "SKIP-PENDING(" in ln), "SKIP-PENDING")


def _run_once(name, slot, base_env, hard_timeout, log_path=None):
    path = os.path.join(TESTDIR, name + ".py")
    env = dict(base_env)
    env["OXC_HARNESS_SLOT"] = str(slot)
    t0 = time.time()
    if log_path is None:
        proc = subprocess.Popen([sys.executable, path], env=env)
    else:  # --log-dir: its own file, unbuffered so a hard-killed test keeps its tail
        env["PYTHONUNBUFFERED"] = "1"
        with open(log_path, "w", encoding="utf-8") as logf:
            proc = subprocess.Popen([sys.executable, path], env=env,
                                    stdout=logf, stderr=subprocess.STDOUT)
    try:
        rc = proc.wait(timeout=hard_timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        rc = 124
        timed_out = True
    return rc, round(time.time() - t0, 1), timed_out


def _run_lane(slot, queue, base_env, results, lock, run_start, quiet, budget_cfg,
              log_dir=None, fail_dir=None):
    default_budget, hard_mult, exceptions = budget_cfg
    for name in queue:
        budget = exceptions.get(name, default_budget)
        hard = max(1.0, budget * hard_mult)
        s0 = round(time.time() - run_start, 1)
        log_path = os.path.join(log_dir, name + ".log") if log_dir else None
        start_epoch = time.time()
        rc, secs, timed_out = _run_once(name, slot, base_env, hard, log_path)
        end_epoch = time.time()
        rc_attempts = [rc]
        # WV-D101: NOTHING is retried, by anyone, ever. rc_attempts/attempts and
        # the ATT column stay (part of the --json schema) but are now always 1.
        attempts = len(rc_attempts)
        e0 = round(time.time() - run_start, 1)
        over_budget = (rc == 0 and not timed_out and secs > budget)
        quarantine = (quarantine_marker(name)
                      if (rc == 0 and not timed_out and not over_budget) else None)
        status = "FAIL" if (timed_out or rc != 0 or over_budget) else ("QUARANTINED" if quarantine else "PASS")
        reason = None
        if timed_out:
            reason = ("BUDGET HARD-KILL: %s still running after %.1fs (%gx its %gs "
                      "budget) - killed as a hung test"
                      % (name, budget * hard_mult, hard_mult, budget))
        elif over_budget:
            reason = ("BUDGET EXCEEDED: %s took %.1fs > %gs budget - re-engineer the "
                      "test or add a justified exception" % (name, secs, budget))
        fail_copy = (_copy_fail_dirs(name, slot, start_epoch, fail_dir)
                     if fail_dir and status == "FAIL" else None)
        rec = {"test": name, "slot": slot, "status": status, "seconds": secs,
               "attempts": attempts, "rc": rc, "rc_attempts": rc_attempts,
               "timed_out": timed_out,
               "budget": budget, "over_budget": over_budget, "reason": reason,
               "start": s0, "end": e0, "start_epoch": round(start_epoch, 3),
               "end_epoch": round(end_epoch, 3), "log": log_path, "fail_copy": fail_copy,
               "quarantine": quarantine}
        with lock:
            results.append(rec)
            if not quiet:
                note = []
                if timed_out:
                    note.append("HANG rc=124")
                elif rc != 0:
                    note.append("rc=%d" % rc)
                elif over_budget:
                    note.append("over %gs budget" % budget)
                elif quarantine:
                    note.append("quarantined")
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
    ap.add_argument("--slot-base", type=int, default=None, help="lane k runs on harness "
                    "slot SLOT_BASE+k (default: the inherited OXC_HARNESS_SLOT, else 0)")
    ap.add_argument("--log-dir", help="write each test's stdout+stderr to LOG_DIR/<test>.log")
    ap.add_argument("--fail-copy-dir", help="after a non-PASS test, copy its lane's fresh "
                    "s<slot>_* user dirs to FAIL_COPY_DIR/<test>/ (S27)")
    args = ap.parse_args()
    base = (args.slot_base if args.slot_base is not None
            else int(os.environ.get("OXC_HARNESS_SLOT", "0")))
    if base < 0:
        ap.error("--slot-base must be >= 0")

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
              % (base + k, len(queues[k]), load[k],
                 "  (%d pinned)" % pinned_here if pinned_here else ""))
    if args.list_only:
        for k in range(args.slots):
            print("--- slot %d ---" % (base + k))
            for t in queues[k]:
                print("  %s%s" % (t, "  [PIN]" if t in PINNED else ""))
        return 0

    base_env = os.environ.copy()
    if not base_env.get("OXC_HARNESS_WINDOWED"):
        base_env["SDL_VIDEODRIVER"] = "dummy"
        base_env["SDL_AUDIODRIVER"] = "dummy"
    log_dir, fail_dir = [os.path.abspath(p) if p else None for p in (args.log_dir, args.fail_copy_dir)]
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    results = []
    lock = threading.Lock()
    run_start = time.time()
    threads = [threading.Thread(target=_run_lane,
                                args=(base + k, queues[k], base_env, results, lock,
                                      run_start, args.quiet, budget_cfg, log_dir, fail_dir))
               for k in range(args.slots) if queues[k]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = round(time.time() - run_start, 1)

    results.sort(key=lambda r: r["seconds"], reverse=True)
    # D59 / WV-D100: any nonzero exit is a FAIL (exit 3 is no longer a separate SKIP).
    # D62 / D229: a QUARANTINED file is listed and counted apart, never as a pass,
    # and does not fail the run.
    fails = [r for r in results if r["status"] == "FAIL"]
    quars = [r for r in results if r["status"] == "QUARANTINED"]
    serial = round(sum(r["seconds"] for r in results), 1)
    lane_busy = [round(sum(r["seconds"] for r in results if r["slot"] == base + k), 1)
                 for k in range(args.slots)]

    print("\n%-30s %-6s %8s %8s %4s %s"
          % ("TEST", "VERD", "SECS", "BUDGET", "ATT", "SLOT"))
    for r in results:
        print("%-30s %-6s %8.1f %8g %4d   %d%s"
              % (r["test"], r["status"], r["seconds"], r["budget"], r["attempts"],
                 r["slot"], "  <-- FAIL" if r["status"] == "FAIL" else ""))

    print("\n%d test(s): %d passed, %d quarantined, %d failed" % (len(results),
          len(results) - len(fails) - len(quars), len(quars), len(fails)))
    print("wall-clock %.1fs | serial-sum %.1fs | speedup %.2fx | lanes %s"
          % (wall, serial, (serial / wall if wall else 0),
             "/".join("%.0f" % b for b in lane_busy)))
    if fails:
        print("FAILED: %s" % ", ".join(r["test"] for r in fails))
        for r in fails:
            if r.get("reason"):
                print("  !! %s" % r["reason"])
    if quars:
        print("QUARANTINED: %s" % ", ".join(r["test"] for r in quars))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"slots": args.slots, "slot_base": base,
                       "slots_used": [base + k for k in range(args.slots) if queues[k]],
                       "wall": wall, "serial": serial,
                       "speedup": round(serial / wall, 3) if wall else 0,
                       "lane_busy": lane_busy, "results": results}, f, indent=2)
        print("wrote %s" % args.json)

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
