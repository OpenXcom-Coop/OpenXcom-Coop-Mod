#!/usr/bin/env python3
"""Run the whole REGRESSION suite unattended and keep ONE summary file current (W2-U13, owner E5 + P2).

    python tools/coop_test/run_regression.py --batches <docs>/rewrite/REGRESSION-BATCHES.md --out <dir>
    python tools/coop_test/run_regression.py --batches <md> --pairs 0,2 --out <dir>   # K=4: two K=2 streams
    python tools/coop_test/run_regression.py --batches <md> --list-only               # resolve + check only

Blocks `## REGRESSION-<n>` hold deltas (`- batch N: names` defines, `- batch N += names` appends), applied
oldest (last in the file) -> newest up to --block (default: the first). Each batch = ONE `run_parallel.py
-k 2 --slot-base <pair>` subprocess (per-test logs, S27 fail copies). With two pairs a free stream takes the
lowest pending batch that conflicts() with no running batch (an EXCLUSIVE test on either side, or a family
on both: s26 test_w2_inventory* / test_w2_host_screens*, s16s2 spec16_s2 / harness_truth, u6 test_coop_peer_equip_screens /
test_unload_weapon_crash). Refused before anything runs (exit 4): a missing test, two family members in a
batch, bad --pairs, a non-empty --out, a busy slot; unless --allow-stale, an exe older than the newest src
file or unstaged bin/common, bin/standard. --out gets SUMMARY.md (rewritten after preflight, every batch and
the end), batches/, logs/ (per-test + run_parallel.out), fail/ (S27), crash/ (new crash files), census.ps1.
CPU: GetSystemTimes every 5 s, a census every 30 s (processes > 10 %, OpenXcom by slot), a gate before a
batch that starts alone (3 s average <= 50 %, every 30 s, <= --cpu-wait-min). No waiver, no class: the
reader classifies. Exit 0 all batches exit 0; 1 any batch exit != 0; 4 refused; 5 aborted after the start.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, time  # noqa: E401

TESTDIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTDIR))
RUN_PARALLEL = os.path.join(TESTDIR, "run_parallel.py")
EXCLUSIVE_TESTS = ("test_w2_udp_rejoin",)
FAMILY_PREFIXES = {"s26": ("test_w2_inventory", "test_w2_host_screens")}  # S26 (F2912)
FAMILY_NAMES = {"u6": ("test_coop_peer_equip_screens", "test_unload_weapon_crash"),  # U6 Q5
                "s16s2": ("test_spec16_pause_on_leave_s2", "test_w2_harness_truth")}  # W2-G1 Q5 (F8463): lobby 49970
HEADING_RE = re.compile(r"^##\s+(REGRESSION-\d+)\b")
BATCH_RE = re.compile(r"^-\s+batch\s+(\d+)\s*(\+=|:)\s*(.*)$")
H13_T1_LINE = "std::terminate called (no active exception)."
CRASH_HEADER = ("==== Crash/Log", "Time:", "Version:", "Compiled:", "Module:", "ImageBase:", "Mods:")
CPU_SAMPLE_S, CENSUS_S, GATE_POLL_S, GATE_PCT, WATCH_S, TAIL_LINES = 5.0, 30.0, 30.0, 50.0, 150.0, 30
# The Q7 slot probe: harness's own lock call in a child; rc 0 = the slot is free (F7931).
PROBE = "import sys; sys.path.insert(0, sys.argv[1]); import harness; harness._acquire_machine_lock(timeout=0)"
CENSUS_PS1 = r"""# run_regression.py census (cpu_check.ps1 method, F4445): processes above 10 % of the machine and the
# OpenXcom instances by harness slot, one line each: PROC <name> <pct> / OXC s<slot> / OXC other.
$n = [Environment]::ProcessorCount
(Get-Counter '\Process(*)\% Processor Time' -SampleInterval 1 -MaxSamples 1 -ErrorAction SilentlyContinue).CounterSamples |
    Where-Object { $_.InstanceName -ne '_total' -and $_.InstanceName -ne 'idle' -and ($_.CookedValue / $n) -gt 10 } |
    ForEach-Object { 'PROC {0} {1}' -f $_.InstanceName, [math]::Round($_.CookedValue / $n, 1) }
Get-CimInstance Win32_Process -Filter "Name LIKE 'OpenXcom%'" | ForEach-Object {
    if ($_.CommandLine -match 'oxc-coop-test[\\/]s(\d+)_') { 'OXC s' + $Matches[1] } else { 'OXC other' } }
"""

def parse_blocks(text):
    """[(REGRESSION-<n>, [(batch, op, [names])])] in file order (newest first)."""
    blocks = []
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m or line.startswith("## "):  # any other '## ' heading ends a block
            blocks.append((m.group(1) if m else None, []))
            continue
        b = BATCH_RE.match(line.strip())
        if b and blocks and blocks[-1][0]:
            blocks[-1][1].append((int(b.group(1)), b.group(2), b.group(3).split()))
    return [blk for blk in blocks if blk[0]]

def resolve(blocks, block=None):
    """Apply the blocks oldest -> newest up to `block` (default: the newest) -> (name, {batch: [names]})."""
    names = [blk[0] for blk in blocks]
    if not names or (block is not None and block not in names):
        raise ValueError("no block %s (blocks: %s)" % (block or "'## REGRESSION-<n>'", ", ".join(names) or "none"))
    idx = 0 if block is None else names.index(block)
    batches = {}
    for _, entries in reversed(blocks[idx:]):
        for num, op, tests in entries:
            if op == ":":
                batches[num] = list(tests)
            else:
                batches.setdefault(num, []).extend(tests)
    return names[idx], dict(sorted(batches.items()))

def families(names):
    out = set()
    for n in names:
        out.update(f for f, prefixes in FAMILY_PREFIXES.items() if n.startswith(prefixes))
        out.update(f for f, exact in FAMILY_NAMES.items() if n in exact)
    return out

def conflicts(a_names, b_names, exclusive=EXCLUSIVE_TESTS):
    """Two batches may not run at once: an exclusive test on either side, or a family on both."""
    if set(exclusive or ()) & (set(a_names) | set(b_names)):
        return True
    return bool(families(a_names) & families(b_names))

def parse_pairs(text):
    try:
        pairs = [int(x) for x in str(text).split(",")]
    except ValueError:
        return None, "--pairs %r is not 1 or 2 slot bases" % text
    if not 1 <= len(pairs) <= 2 or min(pairs) < 0:
        return None, "--pairs %r: give 1 or 2 slot bases >= 0" % text
    if len(pairs) == 2 and abs(pairs[0] - pairs[1]) < 2:
        return None, "--pairs %r: the two pairs overlap (|a - b| < 2)" % text
    return pairs, None

def iso(t):
    return datetime.datetime.fromtimestamp(t).isoformat(timespec="seconds") if t else "-"
def fmt(v):
    return "n/a" if v is None else "%.1f" % v
def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)

def _systimes():  # [epoch, idle, kernel, user] from kernel32 GetSystemTimes (stdlib ctypes; psutil is absent, F7925)
    import ctypes
    from ctypes import wintypes
    ft = [wintypes.FILETIME() for _ in range(3)]
    ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(f) for f in ft])
    return [time.time()] + [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in ft]

def _busy(a, b):  # total CPU % between two readings (kernel time includes idle time)
    idle, total = b[1] - a[1], (b[2] - a[2]) + (b[3] - a[3])
    return round(100.0 * (total - idle) / total, 1) if total > 0 else 0.0

class Cpu(object):
    """Total CPU %; every value is None off Windows (the summary prints n/a)."""
    def __init__(self):
        self.ok = os.name == "nt"
        self.last = _systimes() if self.ok else None

    def window(self, seconds):  # a fresh average over `seconds` (blocking)
        a = _systimes() if self.ok else None
        time.sleep(seconds if self.ok else 0)
        return _busy(a, _systimes()) if self.ok else None

    def tick(self):  # the average since the previous tick (a 1 s window if that was < 0.2 s ago)
        now = _systimes() if self.ok else None
        if now is None or now[0] - self.last[0] < 0.2:
            return self.window(1.0)
        pct, self.last = _busy(self.last, now), now
        return pct

class Batch(object):
    def __init__(self, num, names):
        self.num, self.names, self.tag = num, list(names), "b%02d" % num
        self.pair = self.proc = self.outf = self.rc = self.data = self.t0 = self.t1 = None
        self.pre = self.waited = self.crash = None
        self.samples, self.foreign = [], {}

    def results(self):
        return self.data.get("results", []) if isinstance(self.data, dict) else []

def slot_free(slot):
    env = {k: v for k, v in os.environ.items() if k not in ("OXC_HARNESS_SLOT", "OXC_TIMELOG")}
    env["OXC_HARNESS_SLOT"] = str(slot)
    try:
        return subprocess.run([sys.executable, "-c", PROBE, TESTDIR], env=env, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False

def newest_file(root):
    best = (0.0, None)
    for d, _, files in os.walk(root):
        for fn in files:
            try:
                best = max(best, (os.path.getmtime(os.path.join(d, fn)), os.path.join(d, fn)))
            except OSError:
                pass
    return best

def unstaged(exe_dir):
    """bin/common and bin/standard files whose copy under the exe dir differs in size or mtime (robocopy /l)."""
    bad = []
    for sub in ("common", "standard"):
        src = os.path.join(REPO, "bin", sub)
        for d, _, files in os.walk(src):
            for fn in files:
                a = os.path.join(d, fn)
                try:
                    sa, sb = os.stat(a), os.stat(os.path.join(exe_dir, sub, os.path.relpath(a, src)))
                    if sa.st_size == sb.st_size and abs(sa.st_mtime - sb.st_mtime) < 2.0:
                        continue
                except OSError:
                    pass
                bad.append(os.path.relpath(a, REPO))
    return bad

def git_tip():
    try:
        git = lambda *a: subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True, timeout=120).stdout
        sha, st = git("rev-parse", "HEAD").strip(), git("status", "--porcelain").splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        return "unknown (git failed: %s)" % exc
    return "%s (%s)" % (sha or "unknown", "clean" if not st else "dirty: %d files" % len(st))

def crash_snapshot(exe_dir):
    """{path: mtime} of every file under <exe dir>/crashlogs (its root and each lane's s<slot> folder, W2-U8h) plus
    every <exe dir>/**/*.dmp."""
    cdir = os.path.join(exe_dir, "crashlogs")
    paths = [os.path.join(d, fn) for d, _, fs in os.walk(cdir) for fn in fs]
    paths += [os.path.join(d, fn) for d, _, fs in os.walk(exe_dir) for fn in fs if fn.lower().endswith(".dmp")]
    return {p: os.path.getmtime(p) for p in paths if os.path.isfile(p)}

def crash_slot(path, exe_dir):
    """W2-U8h (F9563): the harness slot whose games wrote `path` (a file in <exe dir>/crashlogs/s<slot>), else None."""
    parent = os.path.dirname(os.path.abspath(path))
    m = re.match(r"^s(\d+)$", os.path.basename(parent))
    crashlogs = os.path.normcase(os.path.join(os.path.abspath(exe_dir), "crashlogs"))
    return int(m.group(1)) if m and os.path.normcase(os.path.dirname(parent)) == crashlogs else None

def first_line(path):
    """The first non-empty line after the crash header ('(minidump)' for a .dmp, '-' if unreadable)."""
    if path.lower().endswith(".dmp"):
        return "(minidump)"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return next((ln.strip()[:200] for ln in f if ln.strip() and not ln.strip().startswith(CRASH_HEADER)), "-")
    except OSError:
        return "-"

def tail(path, n=TAIL_LINES):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [ln.rstrip() for ln in f.read().splitlines()[-n:]]
    except OSError as exc:
        return ["(unreadable: %s)" % exc]

def dir_mb(path, cache={}):
    if path not in cache:
        cache[path] = sum(os.path.getsize(os.path.join(d, fn)) for d, _, fs in os.walk(path) for fn in fs) / 1e6
    return cache[path]

def kill_tree(proc):
    """End one of this runner's own children and its game subtree (by its pid, never by image name)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        else:
            proc.terminate()
        proc.wait(timeout=30)
    except Exception:
        pass

class Run(object):
    def __init__(self, args, block, batches, pairs, pairs_error):
        self.args, self.block, self.pairs, self.pairs_error = args, block, pairs, pairs_error
        self.batches = [Batch(n, names) for n, names in batches.items()]
        self.total = sum(len(b.names) for b in self.batches)
        self.exclusive = list(dict.fromkeys(list(EXCLUSIVE_TESTS) + list(args.exclusive)))
        self.out = os.path.abspath(args.out) if args.out else None
        # The exe the harness drives, as harness.py :94 (copied: this runner never imports harness).
        self.exe = os.environ.get("OXC_TEST_EXE") or os.path.join(REPO, "bin", "x64", "Release", "OpenXcom.exe")
        self.exe_dir = os.path.dirname(os.path.abspath(self.exe))
        self.run_slots = sorted(set(s for p in (pairs or []) for s in (p, p + 1)))
        self.out_usable, self.tip, self.exe_line, self.cpu = True, "-", "-", None
        self.started = self.ended = self.crash_rows = self.crash_error = None
        self.crash_before = {}

    def preflight(self, full):  # Q7: every reason, joined; full=False is --list-only's checks 1-3
        reasons = []
        missing = sorted({n for b in self.batches for n in b.names
                          if not os.path.isfile(os.path.join(TESTDIR, n + ".py"))})
        if missing:
            reasons.append("no tools/coop_test/<name>.py for: %s" % ", ".join(missing))
        for b in self.batches:
            for fam in sorted(families(b.names)):
                members = [n for n in b.names if fam in families([n])]
                if len(members) > 1:
                    reasons.append("batch %d holds %d members of family %s: %s" % (
                        b.num, len(members), fam, ", ".join(members)))
        if self.pairs_error:
            reasons.append(self.pairs_error)
        if not full:
            return reasons
        if os.path.exists(self.out) and (not os.path.isdir(self.out) or os.listdir(self.out)):
            reasons.append("out dir %s exists and is not empty" % self.out)
            self.out_usable = False
        reasons += ["slot %d busy (another run holds its harness lock)" % s for s in self.run_slots if not slot_free(s)]
        self.tip = git_tip()
        exe_m = os.path.getmtime(self.exe) if os.path.isfile(self.exe) else None
        src_m, src_f = newest_file(os.path.join(REPO, "src"))
        verdict = "not checked: --allow-stale" if self.args.allow_stale else "fresh"
        if not self.args.allow_stale and (exe_m is None or exe_m < src_m):
            verdict = "STALE"
            reasons.append("exe STALE: %s %s" % (self.exe, "does not exist" if exe_m is None else
                           "mtime %s older than newest src %s (%s)" % (iso(exe_m), iso(src_m),
                                                                      os.path.relpath(src_f, REPO))))
        self.exe_line = "%s (mtime %s; newest src %s; %s)" % (self.exe, iso(exe_m) if exe_m else "missing",
                                                              iso(src_m), verdict)
        bad = [] if self.args.allow_stale else unstaged(self.exe_dir)
        if bad:
            reasons.append("data not staged: %d file(s) of bin/common, bin/standard differ from %s (first: %s)"
                           % (len(bad), self.exe_dir, bad[0]))
        return reasons

    def schedule(self):  # Q3: one stream per pair; a free stream takes the lowest non-conflicting pending batch
        pending, running, census = list(self.batches), {}, None
        last_sample = last_census = time.time()
        try:
            while pending or running:
                for pair in self.pairs:
                    nxt = None if pair in running else next((b for b in pending if not any(
                        conflicts(b.names, r.names, self.exclusive) for r in running.values())), None)
                    if nxt is not None:
                        pending.remove(nxt)
                        self.start(nxt, pair, alone=not running)
                        last_sample = time.time() if not running else last_sample
                        running[pair] = nxt
                now = time.time()
                if running and now - last_sample >= CPU_SAMPLE_S:
                    pct, last_sample = self.cpu.tick(), now
                    for r in running.values():
                        r.samples.append(pct)
                if census is None and running and self.cpu.ok and now - last_census >= CENSUS_S:
                    last_census = now
                    try:
                        census = (subprocess.Popen(["powershell", "-NoProfile", "-File", os.path.join(
                            self.out, "census.ps1")], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True),
                            list(running.values()))
                    except OSError as exc:
                        print("census not started: %s" % exc, flush=True)
                if census is not None and census[0].poll() is not None:
                    self.take_census(census[0].communicate()[0], set(census[1]) | set(running.values()))
                    census = None
                for pair, b in list(running.items()):
                    if b.proc.poll() is not None:
                        del running[pair]
                        self.finish(b, running)
                time.sleep(0.5)
        finally:  # an abort: end this run's own batches; collect a census still running
            for b in running.values():
                kill_tree(b.proc)
                b.outf.close()
                b.rc, b.t1 = b.proc.returncode, time.time()
            if census is not None:
                try:
                    self.take_census(census[0].communicate(timeout=20)[0], set(census[1]))
                except Exception:
                    kill_tree(census[0])

    def take_census(self, text, batches):
        for ln in (text or "").splitlines():
            if ln.startswith("PROC ") and len(ln.split()) >= 3:
                name, pct = ln[5:].rsplit(None, 1)
                name = name.strip().split("#")[0]
                try:
                    pct = float(pct.replace(",", "."))
                except ValueError:
                    continue
                if not name.lower().startswith("openxcom"):  # OpenXcom instances are counted by slot below
                    for b in batches:
                        b.foreign[name] = max(pct, b.foreign.get(name) or 0.0)
            elif ln.startswith("OXC ") and ln.split()[1] not in ["s%d" % s for s in self.run_slots]:
                for b in batches:
                    b.foreign["OpenXcom " + ln.split()[1]] = None

    def gate(self):
        """S24: before a batch that starts alone, wait (<= --cpu-wait-min) for a 3 s average <= 50 %."""
        if not self.cpu.ok or self.args.cpu_wait_min <= 0:
            return self.cpu.window(1.0), 0.0
        t0 = time.time()
        while True:
            pct = self.cpu.window(3.0)
            if pct <= GATE_PCT or time.time() - t0 >= self.args.cpu_wait_min * 60:
                return pct, max(0.0, round(time.time() - t0 - 3.0, 1))
            print("cpu gate: %.1f %% > %g %%, polling again in %g s" % (pct, GATE_PCT, GATE_POLL_S), flush=True)
            time.sleep(GATE_POLL_S - 3.0)

    def start(self, b, pair, alone):
        b.pair = pair
        b.pre, b.waited = self.gate() if alone else (self.cpu.window(1.0), 0.0)
        if alone and self.cpu.ok:
            self.cpu.tick()  # the in-run samples start at this batch's start
        logs = os.path.join(self.out, "logs", b.tag)
        os.makedirs(logs, exist_ok=True)
        cmd = [sys.executable, RUN_PARALLEL, "-k", "2", "--slot-base", str(pair),
               "--json", os.path.join(self.out, "batches", b.tag + ".json"), "--log-dir", logs,
               "--fail-copy-dir", os.path.join(self.out, "fail", b.tag)] + b.names
        env = {k: v for k, v in os.environ.items() if k != "OXC_HARNESS_SLOT"}
        b.outf = open(os.path.join(logs, "run_parallel.out"), "w", encoding="utf-8")
        b.t0 = time.time()
        b.proc = subprocess.Popen(cmd, env=env, stdout=b.outf, stderr=subprocess.STDOUT)
        print("[%s] start %s slots %d,%d (cpu pre %s %%, waited %s s): %s" % (
            iso(b.t0), b.tag, pair, pair + 1, fmt(b.pre), b.waited, " ".join(b.names)), flush=True)
        self.write("RUNNING %d/%d batches" % (self.done(), len(self.batches)))

    def finish(self, b, running):
        b.rc, b.t1 = b.proc.returncode, time.time()
        b.outf.close()
        if not b.samples:  # a batch shorter than one sample period still gets a number (F7993)
            pct = self.cpu.tick()
            for r in [b] + list(running.values()):
                r.samples.append(pct)
        try:
            with open(os.path.join(self.out, "batches", b.tag + ".json"), encoding="utf-8") as f:
                b.data = json.load(f)
        except (OSError, ValueError):
            b.data = None
        print("[%s] end   %s exit %d wall %s s" % (iso(b.t1), b.tag, b.rc, self.wall(b)), flush=True)
        self.write("RUNNING %d/%d batches" % (self.done(), len(self.batches)))

    def done(self):
        return sum(1 for b in self.batches if b.rc is not None)

    def wall(self, b):  # the run_parallel JSON wall
        w = b.data.get("wall") if isinstance(b.data, dict) else None
        return ("%.1f" % w) if is_num(w) else ("n/a" if b.rc is not None else "-")

    def crash_census(self):
        after = crash_snapshot(self.exe_dir)
        new = sorted((p for p in after if p not in self.crash_before), key=lambda p: after[p])
        tests = [(b, r) for b in self.batches for r in b.results()
                 if is_num(r.get("start_epoch")) and is_num(r.get("end_epoch"))]
        rows = []
        for p in new:
            os.makedirs(os.path.join(self.out, "crash"), exist_ok=True)
            shutil.copy2(p, os.path.join(self.out, "crash", os.path.basename(p)))
            m, line, slot = after[p], first_line(p), crash_slot(p, self.exe_dir)
            # W2-U8h: a file in a lane's s<slot> folder belongs to the test on that slot; a root file keeps the time window
            then = [(b, r["test"]) for b, r in tests if r["start_epoch"] - 2 <= m <= r["end_epoch"] + 2
                    and (slot is None or r.get("slot") == slot)]
            benign = line == H13_T1_LINE and any(t == "test_w2_udp_rejoin" for _, t in then)
            rows.append((p, os.path.getsize(p), m, line, then, "H13-T1 (known benign)" if benign else "-"))
        self.crash_rows = rows
        for b in self.batches:
            b.crash = sum(1 for row in rows if any(x is b for x, _ in row[4]))

    def text(self, status):  # SUMMARY.md: the line order and the table columns are the contract (spec (b)3)
        done = [b for b in self.batches if b.rc is not None]
        nbad = sum(1 for b in done if b.rc != 0)
        verdict = "none" if status != "COMPLETE" else (
            "PASS" if not nbad else "FAIL (%d of %d batches exit != 0)" % (nbad, len(self.batches)))
        res = [(b, r) for b in done for r in b.results()]
        n = {"PASS": 0, "FAIL": 0, "SKIP": 0, "hung": 0, "over": 0}
        for _, r in res:
            key = "hung" if r.get("timed_out") else "over" if r.get("over_budget") else r.get("status")
            n[key] = n.get(key, 0) + 1
        missing = (self.total - len(res)) if status.startswith(("COMPLETE", "ABORTED")) else 0
        pairs = self.pairs or []
        L = ["# REGRESSION RUN SUMMARY", "STATUS: " + status, "VERDICT: " + verdict,
             "block: %s from %s (%d batches, %d tests)" % (self.block, os.path.abspath(self.args.batches),
                                                           len(self.batches), self.total),
             "tip: " + self.tip, "exe: " + self.exe_line,
             "mode: K=%d pairs [%s]; exclusive [%s]; started %s; ended %s; wall %s s" % (
                 2 * len(pairs), ", ".join(str(p) for p in pairs), ", ".join(self.exclusive), iso(self.started),
                 iso(self.ended), ("%.1f" % ((self.ended or time.time()) - self.started)) if self.started else "-"),
             "totals: %d tests: %d passed, %d failed, %d skipped, %d hung, %d over budget%s" % (
                 self.total, n["PASS"], n["FAIL"], n["SKIP"], n["hung"], n["over"],
                 (", %d no result" % missing) if missing > 0 else ""),
             "walls (batch order): " + "/".join(self.wall(b) for b in self.batches),
             "| batch | tests | exit | wall s | slots | cpu pre % | cpu avg % | cpu max % | samples >50% "
             "| waited s | foreign | new crash files |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in self.batches:
            s, started = [x for x in b.samples if x is not None], b.pair is not None
            cpu = ([fmt(b.pre), fmt(sum(s) / len(s)) if s else "n/a", fmt(max(s)) if s else "n/a",
                    "%d/%d" % (sum(1 for x in s if x > GATE_PCT), len(s))] if self.cpu and self.cpu.ok and started
                   else ["n/a" if started else "-"] * 4)
            foreign = ", ".join(k if v is None else "%s %.1f%%" % (k, v) for k, v in sorted(b.foreign.items()))
            L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s |" % (
                b.tag, len(b.names), b.rc if b.rc is not None else ("running" if started else "pending"),
                self.wall(b), "%d,%d" % (b.pair, b.pair + 1) if started else "-", " | ".join(cpu),
                fmt(b.waited) if started else "-", (foreign or "-") if started else "-",
                b.crash if b.crash is not None else "-"))
        L.append("## Failing tests")
        nfail = 0
        for b in done:
            bad = [r for r in b.results() if r.get("status") != "PASS"] or ([None] if b.rc != 0 else [])
            for r in bad:
                nfail += 1
                if r is None:  # run_parallel itself failed (no JSON, or no non-PASS result in it)
                    log = os.path.join(self.out, "logs", b.tag, "run_parallel.out")
                    L += ["### %s run_parallel exit %s (no failing test in its JSON)" % (b.tag, b.rc), "log: " + log]
                else:
                    log, copy = r.get("log"), r.get("fail_copy")
                    L.append("### %s %s (slot %s, %s rc=%s, %s s)" % (
                        b.tag, r.get("test"), r.get("slot"), r.get("status"), r.get("rc"), r.get("seconds")))
                    L += ["reason: " + r["reason"]] if r.get("reason") else []
                    L.append("log: %s; copy: %s" % (log, ("%s (%.1f MB)" % (copy, dir_mb(copy))) if copy else "none"))
                L += ["```"] + (tail(log) if log else ["(no log)"]) + ["```"]
        L += [] if nfail else ["none"]
        if self.crash_rows is None:
            L.append("## Crash census: pending (%d crash file(s) under %s before the run; compared at the end)%s" % (
                len(self.crash_before), self.exe_dir, (" - error: %s" % self.crash_error) if self.crash_error else ""))
        else:
            L += ["## Crash census: %d new file(s)" % len(self.crash_rows),
                  "| file | size | mtime | first line | running then | tag |", "|---|---|---|---|---|---|"]
            for p, size, m, line, then, tag in self.crash_rows:
                L.append("| %s | %d | %s | %s | %s | %s |" % (
                    os.path.basename(p), size, iso(m), line.replace("|", "/"),
                    ", ".join("%s (%s)" % (t, b.tag) for b, t in then) or "-", tag))
            L += ["copies: %s (from %s)" % (os.path.join(self.out, "crash"), self.exe_dir)] if self.crash_rows else []
        watch = sorted(((r["seconds"], r.get("test"), b.tag) for b, r in res
                        if is_num(r.get("seconds")) and r["seconds"] > WATCH_S), reverse=True)
        L += ["## Watch: tests over %g s" % WATCH_S,
              "; ".join("%s %.1f s (%s)" % (t, s, tag) for s, t, tag in watch) or "none"]
        return "\n".join(L) + "\n"

    def write(self, status):
        path = os.path.join(self.out, "SUMMARY.md")
        with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            f.write(self.text(status))
        os.replace(path + ".tmp", path)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batches", required=True, help="REGRESSION-BATCHES.md (or any file with its headings and lines)")
    ap.add_argument("--block", help="resolve up to this REGRESSION-<n> block (default: the first heading)")
    ap.add_argument("--pairs", default="0", help="slot base of each K=2 stream: '0' = K=2 (default), '0,2' = K=4")
    ap.add_argument("--out", help="output dir, new or empty (required unless --list-only)")
    ap.add_argument("--exclusive", nargs="+", action="extend", default=[], metavar="NAME",
                    help="more tests whose batch never runs beside another batch (built in: %s)"
                    % ", ".join(EXCLUSIVE_TESTS))
    ap.add_argument("--cpu-wait-min", type=float, default=10.0,
                    help="pre-batch CPU gate: wait at most this many minutes for <= 50 %% (0 = no gate; default 10)")
    ap.add_argument("--allow-stale", action="store_true", help="skip the exe-age and data-staging refusals")
    ap.add_argument("--list-only", action="store_true", help="resolve and check (tests, families, pairs); run nothing")
    args = ap.parse_args(argv)
    if not args.list_only and not args.out:
        ap.error("--out is required unless --list-only")
    try:
        with open(args.batches, encoding="utf-8") as f:
            block, batches = resolve(parse_blocks(f.read()), args.block)
    except (OSError, ValueError) as exc:
        print("STATUS: REFUSED: --batches %s: %s" % (args.batches, exc), flush=True)
        return 4
    run = Run(args, block, batches, *parse_pairs(args.pairs))
    if args.list_only:
        print("block %s: %d batches, %d tests" % (block, len(run.batches), run.total))
        for b in run.batches:
            print("batch %d: %s%s%s" % (b.num, " ".join(b.names), " [exclusive]" if set(b.names) & set(run.exclusive)
                                         else "", "".join(" [%s]" % f for f in sorted(families(b.names)))))
        reasons = run.preflight(full=False)
        if reasons:
            print("STATUS: REFUSED: " + "; ".join(reasons), flush=True)
        return 4 if reasons else 0
    reasons = run.preflight(full=True)
    if reasons:
        status = "REFUSED: " + "; ".join(reasons)
        print("STATUS: " + status, flush=True)
        if run.out_usable:  # never write into a foreign non-empty dir
            os.makedirs(run.out, exist_ok=True)
            run.write(status)
        return 4
    for sub in ("batches", "logs", "fail"):
        os.makedirs(os.path.join(run.out, sub), exist_ok=True)
    with open(os.path.join(run.out, "census.ps1"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(CENSUS_PS1)
    run.cpu, run.crash_before, run.started = Cpu(), crash_snapshot(run.exe_dir), time.time()
    run.write("RUNNING 0/%d batches" % len(run.batches))
    status = "ABORTED: unknown"
    try:
        run.schedule()
        status = "COMPLETE"
    except BaseException as exc:  # an exception or an interrupt after the start
        status = "ABORTED: %s%s" % (type(exc).__name__, (": %s" % exc) if str(exc) else "")
    finally:
        run.ended = time.time()
        try:
            run.crash_census()
        except Exception as exc:
            run.crash_error = repr(exc)
        run.write(status)
        print("STATUS: %s | %s" % (status, os.path.join(run.out, "SUMMARY.md")), flush=True)
    if status != "COMPLETE":
        return 5
    return 0 if all(b.rc == 0 for b in run.batches) else 1

if __name__ == "__main__":
    sys.exit(main())
