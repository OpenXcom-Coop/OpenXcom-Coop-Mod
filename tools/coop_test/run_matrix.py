"""VALIDATION L2/L3 burn-in matrix runner + per-bucket promotion scoreboard.

Drives `test_parallel_soak.py --profile <p>` repeatedly (optionally K lanes at
once, one per OXC_HARNESS_SLOT, same shift model as run_parallel.py) and scores
the result against the L3 promotion program:

  A bucket promotes when, ON ONE UNCHANGED BUILD: 10 consecutive clean baseline
  soaks + 2 clean runs of every other profile + 0 report-only hits across all of
  it. Any hit resets that bucket's streak.

This runner does NOT flip any BATTLE_HASH_ALARM row (that is a product code change
done separately, after the pass). It measures and reports.

Buckets scored: the 9 in the compile-time BATTLE_HASH_ALARM table plus saveBlob
(terrain, fire, smoke, items, unitsCore, unitsStats, itemIdCtr, unitsCombat,
unitsRegen, saveBlob).

Usage:
  python tools/coop_test/run_matrix.py --ab                 # soak-at-K A/B
  python tools/coop_test/run_matrix.py --full [-k K]        # 10 baseline + 2x each
  python tools/coop_test/run_matrix.py --jobs baseline:3,psi:2 [-k K]
  python tools/coop_test/run_matrix.py --resume             # continue the persisted board

State persists to a JSON scoreboard so the (multi-hour) pass can run in bounded
foreground chunks; --resume picks up where it left off.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOAK = os.path.join(HERE, "test_parallel_soak.py")

BUCKETS = ["terrain", "fire", "smoke", "items", "unitsCore", "unitsStats",
           "itemIdCtr", "unitsCombat", "unitsRegen", "saveBlob"]

SKIRMISH = ["baseline", "speed-skew", "backlog", "incendiary", "psi",
            "spawn-blast", "gifting"]
OTHER = ["speed-skew", "backlog", "incendiary", "psi", "spawn-blast", "gifting",
         "campaign", "resume"]
ALL_PROFILES = ["baseline"] + OTHER

NOTE_RE = re.compile(r"report-only sync-check buckets differ:\s*(\{[^}]*\})")
CLEAN_RE = re.compile(r"ALL PARALLEL SOAK TESTS PASSED")
FAIL_RE = re.compile(r"^\[FAIL\]\s*(.*)$", re.M)

# Known-residual ledger (VALIDATION / HANDOFF). A report-only hit that matches one
# of these is a KNOWN signature: logged, does NOT stop the pass, but per L3 still
# resets the affected bucket's streak. Anything else is a NEW seam -> STOP.
KNOWN_SIGNATURES = {
    "unitsCombat": "SEAM-7/8 casualty combat-state straddle at blast/casualty seqs",
    "unitsRegen": "SEAM-7/8 deferred-regen straddle (ai-seq/endturn boundary-allowed)",
    "smoke": "SEAM-3 smoke_ai ~1/10 mid-side explosion class",
    "saveBlob": "PRD-I2 whole-save superset: subsumes any report-only bucket at a boundary",
    "terrain": "SEAM-3 destroy_tile delivery straddle (heals by sidestart)",
    "items": "SEAM-7/8 casualty item-drop straddle at blast seqs",
    "unitsCore": "SEAM-7/8 casualty liveness/position straddle at blast seqs",
    "itemIdCtr": "SEAM-3/7 blast item-id counter straddle at blast seqs",
}


def parse_run(out):
    """Extract (clean, fail_reason, buckethits) from one soak's stdout."""
    clean = bool(CLEAN_RE.search(out))
    fm = FAIL_RE.search(out)
    fail = fm.group(1).strip() if fm else None
    hits = {}
    for m in NOTE_RE.finditer(out):
        try:
            d = ast.literal_eval(m.group(1))
        except Exception:
            continue
        for k, v in d.items():
            hits[k] = max(hits.get(k, 0), int(v))
    return clean, fail, hits


def run_one(profile, slot, turns, actions, seed):
    env = dict(os.environ)
    env["OXC_HARNESS_SLOT"] = str(slot)
    cmd = [sys.executable, SOAK, "--profile", profile]
    if turns:
        cmd += ["--turns", str(turns)]
    if actions:
        cmd += ["--actions", str(actions)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    t0 = time.time()
    p = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True)
    dt = time.time() - t0
    clean, fail, hits = parse_run(p.stdout or "")
    # a non-zero exit with no [FAIL] line is a crash/harness drop, not a divergence
    if not clean and not fail and p.returncode != 0:
        fail = "no ALL-PASSED and no [FAIL] (rc=%d) - crash/harness drop" % p.returncode
    return {"profile": profile, "slot": slot, "clean": clean, "fail": fail,
            "hits": hits, "rc": p.returncode, "secs": round(dt, 1),
            "tail": "\n".join((p.stdout or "").splitlines()[-25:])}


def run_batch(jobs, k, turns, actions, seed, slot_base=0):
    """jobs = list of profile names; run up to k concurrently across
    slots slot_base..slot_base+k-1 (slot_base lets a chunk dodge a busy slot)."""
    results = []
    i = 0
    while i < len(jobs):
        chunk = jobs[i:i + k]
        procs = []
        for off, profile in enumerate(chunk):
            slot = slot_base + off
            env = dict(os.environ)
            env["OXC_HARNESS_SLOT"] = str(slot)
            cmd = [sys.executable, SOAK, "--profile", profile]
            if turns:
                cmd += ["--turns", str(turns)]
            if actions:
                cmd += ["--actions", str(actions)]
            if seed is not None:
                cmd += ["--seed", str(seed)]
            t0 = time.time()
            p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, universal_newlines=True)
            procs.append((profile, slot, p, t0))
        for profile, slot, p, t0 in procs:
            out, _ = p.communicate()
            dt = time.time() - t0
            clean, fail, hits = parse_run(out or "")
            if not clean and not fail and p.returncode != 0:
                fail = "no ALL-PASSED and no [FAIL] (rc=%d)" % p.returncode
            r = {"profile": profile, "slot": slot, "clean": clean, "fail": fail,
                 "hits": hits, "rc": p.returncode, "secs": round(dt, 1),
                 "tail": "\n".join((out or "").splitlines()[-25:])}
            results.append(r)
            flag = "CLEAN" if clean else "FAIL "
            print(f"  [{flag}] {profile:12s} slot{slot} {dt:5.0f}s "
                  f"hits={r['hits'] or '-'}"
                  + (f"  FAIL: {fail[:80]}" if fail else ""))
        i += k
    return results


def classify(hits):
    """Split a run's report-only bucket hits into (known, unknown)."""
    known, unknown = {}, {}
    for b, c in hits.items():
        if b in KNOWN_SIGNATURES:
            known[b] = c
        else:
            unknown[b] = c
    return known, unknown


def scoreboard(runs):
    """Build the per-bucket promotion scoreboard from a flat list of run dicts."""
    board = {b: {"baseline_streak": 0, "streak_broken_by": None,
                 "profile_clean": {}, "report_hits": []} for b in BUCKETS}
    # baseline consecutive-clean streak per bucket
    baseline_runs = [r for r in runs if r["profile"] == "baseline"]
    for b in BUCKETS:
        streak = 0
        broke = None
        for idx, r in enumerate(baseline_runs):
            hit = r["hits"].get(b, 0) > 0
            if r["clean"] and not hit:
                streak += 1
            else:
                if streak >= 0:
                    broke = ("run#%d " % (idx + 1)) + (
                        "FAIL:%s" % r["fail"] if not r["clean"]
                        else "report-only hit %d" % r["hits"].get(b, 0))
                streak = 0
        board[b]["baseline_streak"] = streak
        board[b]["streak_broken_by"] = broke
    # per-profile clean-run counts (clean run with NO hit for that bucket)
    for b in BUCKETS:
        for prof in ALL_PROFILES:
            pruns = [r for r in runs if r["profile"] == prof]
            good = sum(1 for r in pruns if r["clean"] and r["hits"].get(b, 0) == 0)
            board[b]["profile_clean"][prof] = "%d/%d" % (good, len(pruns))
    # every report-only hit, with classification
    for r in runs:
        known, unknown = classify(r["hits"])
        for b, c in r["hits"].items():
            board[b]["report_hits"].append({
                "profile": r["profile"], "count": c,
                "signature": KNOWN_SIGNATURES.get(b, "*** UNKNOWN (NEW SEAM) ***")})
    return board


def promotion_ready(board, runs):
    """L3: 10 consecutive clean baseline + >=2 clean of every other profile + 0
    report-only hits for that bucket across ALL of it."""
    ready = {}
    for b in BUCKETS:
        base_ok = board[b]["baseline_streak"] >= 10
        others_ok = all(int(board[b]["profile_clean"][p].split("/")[0]) >= 2
                        for p in OTHER)
        no_hits = all(r["hits"].get(b, 0) == 0 for r in runs)
        ready[b] = base_ok and others_ok and no_hits
    return ready


def save_board(path, runs, board, ready, build_sha):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"build_sha": build_sha, "runs": runs, "board": board,
                   "ready": ready, "ts": time.time()}, f, indent=2)


def print_board(board, ready, runs):
    print("\n=== PER-BUCKET PROMOTION SCOREBOARD "
          "(baseline consecutive-clean streak, per-profile clean, hits) ===")
    for b in BUCKETS:
        pc = board[b]["profile_clean"]
        hits = board[b]["report_hits"]
        nunknown = sum(1 for h in hits if h["signature"].startswith("***"))
        print(f"\n{b}:")
        print(f"  baseline streak: {board[b]['baseline_streak']}/10"
              + (f"  (broken by {board[b]['streak_broken_by']})"
                 if board[b]["streak_broken_by"] else ""))
        print("  profile clean: " + " ".join(f"{p}={pc[p]}" for p in ALL_PROFILES))
        if hits:
            print(f"  report-only hits: {len(hits)}"
                  + (f"  *** {nunknown} UNKNOWN-SIGNATURE ***" if nunknown else ""))
        print(f"  PROMOTION READY: {'YES' if ready[b] else 'no'}")
    print("\n=== SUMMARY ===")
    print("  PROMOTE:", [b for b in BUCKETS if ready[b]] or "(none)")
    total = len(runs)
    clean = sum(1 for r in runs if r["clean"])
    print(f"  runs: {total}  clean: {clean}  failed: {total - clean}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ab", action="store_true", help="soak-at-K A/B (item 3)")
    ap.add_argument("--ab-k4", type=int, default=1,
                    help="number of 4-lane K=4 batches in the A/B (default 1 = 4 runs)")
    ap.add_argument("--full", action="store_true",
                    help="the full L3 program: 10 baseline + 2x each other profile")
    ap.add_argument("--jobs", help='"profile:count,profile:count,..."')
    ap.add_argument("-k", type=int, default=1, help="concurrent lanes (<=4)")
    ap.add_argument("--turns", type=int, default=None)
    ap.add_argument("--actions", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--board", default=os.path.join(tempfile.gettempdir(),
                    "coop_matrix_scoreboard.json"),
                    help="scoreboard JSON path (persisted across chunks; default = temp)")
    ap.add_argument("--resume", action="store_true",
                    help="append to the persisted board instead of starting fresh")
    args = ap.parse_args()

    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE,
                                      universal_newlines=True).strip()
    except Exception:
        sha = "unknown"

    prior = []
    if args.resume and os.path.exists(args.board):
        with open(args.board, encoding="utf-8") as f:
            saved = json.load(f)
        prior = saved.get("runs", [])
        if saved.get("build_sha") not in (sha, "unknown"):
            print(f"WARNING: persisted board is build {saved.get('build_sha')} "
                  f"but HEAD is {sha} - L3 wants ONE unchanged build")

    if args.ab:
        # Bounded A/B: baseline K=1 x3 (serial) vs K=4 x1 batch (4 concurrent lanes).
        # --ab-k4 batches widens the K=4 sample. The parallel soak's ~40% casualty-
        # straddle census flake (a pre-existing SEAM-7/8 residual) is the dominant
        # noise, so this measures whether 4-wide CONTENTION worsens the rate, not the
        # absolute rate (which needs a quiet-build seam fix to stabilise).
        nb = args.ab_k4 * 4
        print(f"== SOAK-AT-K A/B: baseline K=1 x3 vs K=4 x{args.ab_k4} batch(es) ==")
        print("-- K=1 (serial) x3 --")
        k1 = run_batch(["baseline"] * 3, 1, args.turns, args.actions, args.seed)
        print(f"-- K=4 ({nb} runs in {args.ab_k4} batch(es) of 4 concurrent lanes) --")
        k4 = run_batch(["baseline"] * nb, 4, args.turns, args.actions, args.seed)
        def rate(rs):
            return sum(1 for r in rs if r["clean"]), len(rs)
        c1, n1 = rate(k1)
        c4, n4 = rate(k4)
        print(f"\nA/B RESULT: K=1 clean {c1}/{n1} (avg {sum(r['secs'] for r in k1)/max(1,n1):.0f}s) "
              f"| K=4 clean {c4}/{n4} (avg {sum(r['secs'] for r in k4)/max(1,n4):.0f}s)")
        allruns = prior + k1 + k4
        board = scoreboard(allruns)
        ready = promotion_ready(board, allruns)
        save_board(args.board, allruns, board, ready, sha)
        print_board(board, ready, allruns)
        return

    if args.full:
        jobs = ["baseline"] * 10 + [p for p in OTHER for _ in range(2)]
    elif args.jobs:
        jobs = []
        for tok in args.jobs.split(","):
            name, _, cnt = tok.partition(":")
            jobs += [name.strip()] * int(cnt or 1)
    else:
        ap.error("one of --ab / --full / --jobs is required")

    print(f"== matrix batch: {len(jobs)} runs, K={args.k}, build {sha[:9]} ==")
    runs = prior + run_batch(jobs, args.k, args.turns, args.actions, args.seed)
    board = scoreboard(runs)
    ready = promotion_ready(board, runs)
    save_board(args.board, runs, board, ready, sha)
    print_board(board, ready, runs)


if __name__ == "__main__":
    main()
