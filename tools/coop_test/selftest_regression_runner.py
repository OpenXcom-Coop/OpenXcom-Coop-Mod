#!/usr/bin/env python3
"""W2-U13 self-test, rows U13-1..U13-9: run_parallel.py --slot-base / per-test logs and run_regression.py.
Not a test_* file (CI, a default suite and REGRESSION never run it, F7929). Each row runs the tools as subprocesses
by absolute path in its own temp dir (kept on a failure), drives only the regstub_* stubs on slots 20-27 (S29) and
boots no game. EVIDENCE before each verdict; exit 0 only when all nine pass, else 2."""
import glob, json, os, re, shutil, subprocess, sys, tempfile, time  # noqa: E401

TESTDIR = os.path.dirname(os.path.abspath(__file__))
RP, RR = os.path.join(TESTDIR, "run_parallel.py"), os.path.join(TESTDIR, "run_regression.py")
TEST_ROOT = os.path.join(os.environ.get("TEMP") or os.environ.get("TMPDIR") or tempfile.gettempdir(), "oxc-coop-test")
STUB_RE = re.compile(r"^REGSTUB name=(\S+) slot=(\S+) env=(\S+) userdir=(.*) lock=(.*) t0=(\S+) t1=(\S+)$")
TOP_KEYS = ("slots", "wall", "serial", "speedup", "lane_busy", "results")
RES_KEYS = ("test", "slot", "status", "seconds", "attempts", "rc", "rc_attempts", "timed_out", "budget",
            "over_budget", "reason", "start", "end")
QUIET = ["--cpu-wait-min", "0", "--allow-stale"]
R130 = {  # REGRESSION-130 batches (REGRESSION-BATCHES.md + W2i's R-130 block), typed for U13-9
    5: "test_w2_delta_core test_w2_delta_items test_w2_host_combat test_w2_host_combat_terrain test_w2_light_scope "
       "test_w2_hash_coverage test_w2_death_side test_w2_host_screens_turn".split(),
    9: "test_w2_client_research test_w2_inventory_baton test_w2_rejoin_reveal_rearm test_w2_soldier_removal_log".split(),
    16: "test_w2_udp_rejoin test_w2_rejoin_end_turn_clear".split(),
    18: "test_w2_battle_end_campaign test_w2_battle_end_campaign_fence test_w2_synced_options".split(),
    19: "test_w2_synced_options_ui test_w2_synced_campaign_options test_w2_synced_campaign_options_sep".split(),
}
F3 = ("## REGRESSION-3 (fixture)\n- batch 3: regstub_fail regstub_pass_a\n"
      "## REGRESSION-2 (fixture)\n- batch 1 += regstub_pass_b\n"
      "## REGRESSION-1 (fixture root)\n- batch 1: regstub_pass_a\n- batch 2: regstub_pass_a regstub_pass_b\n")
STUB_MD = "## REGRESSION-1 (fixture)\n- batch 1: regstub_pass_a regstub_pass_b\n"
SHARED = {}

class RowStop(Exception):
    pass

class Row:
    def __init__(self, code):
        self.code, self.failed = code, []
        self.tmp = tempfile.mkdtemp(prefix="u13_%s_" % code.replace("-", "").lower())
    def ev(self, text):
        print("EVIDENCE %s: %s" % (self.code, text.replace(self.tmp, "<tmp>").replace(TESTDIR, "<TESTDIR>")), flush=True)
    def cell(self, name, ok, detail=""):
        if not ok:
            self.failed.append(name + (" (%s)" % detail if detail else ""))
    def gate(self, ok, message):  # a cell the later cells depend on: the row stops on its failure
        if not ok:
            self.failed.append(message)
            raise RowStop()
    def path(self, *parts):
        return os.path.join(self.tmp, *parts)
    def write(self, name, text):  # a fixture file: written and read back = a guard cell
        with open(self.path(name), "w", encoding="ascii", newline="\n") as f:
            f.write(text)
        self.gate(read(self.path(name)) == text, "GUARD: fixture %s written" % name)
        return self.path(name)

def env_for(**over):
    drop = ("OXC_HARNESS_SLOT", "OXC_TEST_EXE", "OXC_TIMELOG", "REGSTUB_SLEEP", "REGSTUB_CRASH")
    return dict({k: v for k, v in os.environ.items() if k not in drop}, **over)

def run(row, args, env, over=""):
    t = time.time()
    p = subprocess.run([sys.executable] + args, env=env, cwd=row.tmp, capture_output=True, text=True, timeout=300)
    row.ev("cmd=%s%s rc=%d %.1fs" % ("[%s] " % over if over else "", " ".join(args), p.returncode, time.time() - t))
    if p.returncode != 0 and p.stderr.strip():
        row.ev("stderr last: %s" % " | ".join([ln for ln in p.stderr.splitlines() if ln.strip()][-2:]))
    return p

def read(path):
    return open(path, encoding="utf-8", errors="replace").read() if os.path.isfile(path) else None
def load(path):
    return json.loads(read(path) or "null")
def is_num(s):
    return isinstance(s, (int, float)) or (isinstance(s, str) and re.match(r"^-?\d+(\.\d+)?$", s) is not None)
def lines_of(text):
    return [ln.strip() for ln in (text or "").splitlines()]

def stubs(row, text):
    keys = ("name", "slot", "env", "userdir", "lock", "t0", "t1")
    recs = [dict(zip(keys, m.groups())) for m in map(STUB_RE.match, lines_of(text)) if m]
    row.ev("stub lines: " + ("; ".join("%s slot=%s env=%s userdir=..\\%s lock=..\\%s" % (r["name"], r["slot"], r["env"],
           os.path.basename(r["userdir"]), os.path.basename(r["lock"])) for r in recs) or "none"))
    return recs

def plan_has(text, slots):  # run_parallel's plan lines "  slot <n>: ..." name every slot in `slots`
    plan = [ln for ln in lines_of(text) if re.match(r"^slot \d+:", ln)]
    return plan, all(any(ln.startswith("slot %d:" % k) for ln in plan) for k in slots)

def fake_exe(row, old=False):  # an empty file, never executed (no firewall prompt, S19)
    os.makedirs(row.path("fakeexe"), exist_ok=True)
    exe = row.path("fakeexe", "fake_openxcom.bin")
    open(exe, "wb").close()
    os.utime(exe, (946684800, 946684800) if old else None)  # old = 2000-01-01
    return exe

def runner(row, args, env):  # the runner's absence is the named RED cell of U13-5, -6 and -8
    p = run(row, [RR] + args, env)
    row.gate(os.path.exists(RR), "no regression runner")
    return p

def summary_rows(text):
    return {m.group(1): [c.strip() for c in ln.strip("|").split("|")]
            for ln in lines_of(text) for m in [re.match(r"^\|\s*(b\d\d)\s*\|", ln)] if m}

def u13_1(row):
    j = row.path("J.json")
    p = run(row, [RP, "-k", "2", "--slot-base", "20", "--json", j, "regstub_pass_a", "regstub_pass_b"], env_for())
    row.gate(not (p.returncode == 2 and "unrecognized arguments: --slot-base" in p.stdout + p.stderr),
             "run_parallel cannot run K=2 on slots 20/21 (F4550)")
    recs, J, (plan, plan_ok) = stubs(row, p.stdout), load(j) or {}, plan_has(p.stdout, (20, 21))
    row.ev("plan %s; J slot_base=%s slots_used=%s result slots=%s" % (
        plan, J.get("slot_base"), J.get("slots_used"), sorted(r.get("slot") for r in J.get("results", []))))
    row.cell("exit 0", p.returncode == 0, "rc=%d" % p.returncode)
    row.cell("two REGSTUB lines", sorted(r["name"] for r in recs) == ["regstub_pass_a", "regstub_pass_b"])
    row.cell("stub slots {20, 21}", {r["slot"] for r in recs} == {"20", "21"})
    for r in recs:  # env equal to slot, userdir ...\s<slot>_regstub_*, lock ...oxc-coop-harness.slot<slot>.lock
        row.cell("%s env/userdir/lock follow slot %s" % (r["name"], r["slot"]), r["env"] == r["slot"] and os.path.basename(
            r["userdir"]).startswith("s%s_regstub_" % r["slot"]) and r["lock"].endswith("oxc-coop-harness.slot%s.lock" % r["slot"]))
    row.cell("J slot_base 20", J.get("slot_base") == 20)
    row.cell("J slots_used [20, 21]", J.get("slots_used") == [20, 21])
    row.cell("J result slots {20, 21}", {r.get("slot") for r in J.get("results", [])} == {20, 21})
    row.cell("plan lines name slots 20 and 21", plan_ok)

def u13_2(row):
    j = row.path("J.json")
    p = run(row, [RP, "-k", "2", "--json", j, "regstub_pass_a", "regstub_pass_b"], env_for(OXC_HARNESS_SLOT="22"),
            over="OXC_HARNESS_SLOT=22")
    recs, J = stubs(row, p.stdout), load(j)
    SHARED["u13_2_json"] = J
    res = (J or {}).get("results", [])
    row.ev("J result slots %s rc %s" % (sorted(r.get("slot") for r in res), [r.get("rc") for r in res]))
    row.gate(p.returncode == 0 and len(res) == 2 and all(r.get("rc") == 0 for r in res) and len(recs) == 2,
             "GUARD: the stubs' own exits (run rc %d, %d results, %d REGSTUB lines)" % (p.returncode, len(res), len(recs)))
    slots = {int(r["slot"]) for r in recs}
    row.gate(slots != {0, 1}, "a lane run with OXC_HARNESS_SLOT=22 lands on slots 0/1 (RP :185, F7917)")
    row.cell("stubs report slots {22, 23}", slots == {22, 23}, str(sorted(slots)))
    row.cell("J slots {22, 23}", {r.get("slot") for r in res} == {22, 23})

def u13_3(row):
    p = run(row, [RP, "-k", "2", "--list-only", "regstub_pass_a", "regstub_pass_b"], env_for())
    plan, plan_ok = plan_has(p.stdout, (0, 1))
    row.ev("plan lines %s" % plan)
    row.cell("exit 0", p.returncode == 0, "rc=%d" % p.returncode)
    row.cell("plan lines slot 0: and slot 1:", plan_ok)
    J = SHARED.get("u13_2_json")
    row.gate(isinstance(J, dict), "U13-2's J missing")
    miss_top = [k for k in TOP_KEYS if k not in J]
    miss_res = sorted({k for r in J.get("results", []) for k in RES_KEYS if k not in r})
    row.ev("U13-2 J top keys %s; missing top %s; missing per-result %s" % (sorted(J), miss_top, miss_res))
    row.cell("J holds today's top-level keys", not miss_top, str(miss_top))
    row.cell("J results hold today's keys", bool(J.get("results")) and not miss_res, str(miss_res))

def u13_4(row):
    L, F, j, tl = row.path("L"), row.path("F"), row.path("J.json"), row.path("tl.csv")
    p = run(row, [RP, "-k", "2", "--slot-base", "24", "--log-dir", L, "--fail-copy-dir", F, "--json", j,
                  "regstub_fail", "regstub_pass_a"], env_for(OXC_TIMELOG=tl), over="OXC_TIMELOG=<tmp>\\tl.csv")
    tlr = [ln for ln in lines_of(read(tl)) if ",test_end," in ln and "regstub_fail.py" in ln]
    row.ev("tl.csv test_end row for regstub_fail.py (EVIDENCE only, F7624): %s" % (tlr or "none"))
    row.gate(not (p.returncode == 2 and "unrecognized arguments" in p.stdout + p.stderr), "no per-test logs")
    flog, plog = read(os.path.join(L, "regstub_fail.log")) or "", read(os.path.join(L, "regstub_pass_a.log")) or ""
    rp_stub = [ln for ln in p.stdout.splitlines() if "REGSTUB" in ln]
    status = [ln for ln in lines_of(p.stdout) if re.match(r"^\[slot \d+\] FAIL\s+[\d.]+s\s+regstub_fail\b", ln)]
    copies = glob.glob(os.path.join(F, "regstub_fail", "s2?_regstub_fail", "openxcom.log"))
    rf = ([r for r in (load(j) or {}).get("results", []) if r.get("test") == "regstub_fail"] or [{}])[0]
    row.ev("regstub_fail.log %d lines (line 40 %s, Traceback %s, deliberate %s); regstub_pass_a.log REGSTUB %s" % (
        len(flog.splitlines()), "REGSTUB line 40" in flog, "Traceback" in flog, "REGSTUB deliberate failure" in flog,
        "REGSTUB name=regstub_pass_a" in plog))
    row.ev("stdout REGSTUB lines %d; status %s; copies %s; pass_a copy %s; J regstub_fail %s" % (
        len(rp_stub), status, [c.replace(F, "F") for c in copies], os.path.exists(os.path.join(F, "regstub_pass_a")),
        {k: rf.get(k) for k in ("slot", "status", "rc", "start_epoch", "end_epoch")}))
    row.cell("exit 1", p.returncode == 1, "rc=%d" % p.returncode)
    row.cell("regstub_fail.log holds REGSTUB line 40, Traceback, REGSTUB deliberate failure",
             all(s in flog for s in ("REGSTUB line 40", "Traceback", "REGSTUB deliberate failure")))
    row.cell("regstub_pass_a.log holds its REGSTUB line", "REGSTUB name=regstub_pass_a" in plog)
    row.cell("run_parallel stdout holds no REGSTUB line", not rp_stub, str(len(rp_stub)))
    row.cell("run_parallel stdout holds the FAIL status line of regstub_fail", bool(status))
    row.cell("F\\regstub_fail\\s2?_regstub_fail\\openxcom.log exists", bool(copies))
    row.cell("no copy for regstub_pass_a", not os.path.exists(os.path.join(F, "regstub_pass_a")))
    row.cell("J regstub_fail status FAIL rc 1", rf.get("status") == "FAIL" and rf.get("rc") == 1)
    row.cell("J regstub_fail start_epoch < end_epoch", is_num(rf.get("start_epoch")) and is_num(rf.get("end_epoch"))
             and rf["start_epoch"] < rf["end_epoch"])
    row.cell("J regstub_fail log and fail_copy set", bool(rf.get("log")) and bool(rf.get("fail_copy")))

def u13_5(row):
    md = row.write("F3.md", F3)
    p = runner(row, ["--batches", md, "--list-only"] + QUIET, env_for())
    row.ev("list-only stdout: %s" % " | ".join(lines_of(p.stdout)))
    row.cell("exit 0", p.returncode == 0, "rc=%d" % p.returncode)
    # F3 resolved (F7986): batch 1 = pass_a + pass_b (R-2's +=), batch 2 = 2, batch 3 = 2 -> 6 entries; R-2: 4.
    for want in ("block REGRESSION-3: 3 batches, 6 tests", "batch 1: regstub_pass_a regstub_pass_b",
                 "batch 3: regstub_fail regstub_pass_a"):
        row.cell(want, want in lines_of(p.stdout))
    p2 = run(row, [RR, "--batches", md, "--block", "REGRESSION-2", "--list-only"] + QUIET, env_for())
    row.ev("--block REGRESSION-2 stdout: %s" % " | ".join(lines_of(p2.stdout)))
    row.cell("second exit 0", p2.returncode == 0, "rc=%d" % p2.returncode)
    row.cell("block REGRESSION-2: 2 batches, 4 tests", "block REGRESSION-2: 2 batches, 4 tests" in lines_of(p2.stdout))

def u13_6(row):
    md, out = row.write("F3.md", F3), row.path("O")
    p = runner(row, ["--batches", md, "--pairs", "20", "--out", out] + QUIET,
               env_for(OXC_TEST_EXE=fake_exe(row), REGSTUB_CRASH="1"))
    s = read(os.path.join(out, "SUMMARY.md")) or ""
    lines, srows = lines_of(s), summary_rows(s)
    m = re.search(r"^### b03 regstub_fail[^\n]*\n(.*?)(?=^##|\Z)", s, re.S | re.M)
    tail, crow = (m.group(1) if m else ""), [ln for ln in lines if ln.startswith("|") and "crash_regstub_" in ln]
    cm = re.search(r"copy: (.+?) \(", tail)
    row.ev("SUMMARY: %s" % " | ".join(ln for ln in lines if ln.startswith(("STATUS:", "VERDICT:", "mode:", "## Crash"))))
    row.ev("table %s; b03 block %d lines; copy %s; census rows %s" % (srows, len(tail.splitlines()), cm and cm.group(1), crow))
    row.cell("exit 1", p.returncode == 1, "rc=%d" % p.returncode)
    for want in ("STATUS: COMPLETE", "VERDICT: FAIL (1 of 3 batches exit != 0)", "## Crash census: 1 new file(s)"):
        row.cell(want, want in lines)
    for b, n, e in (("b01", "2", "0"), ("b02", "2", "0"), ("b03", "2", "1")):
        c = srows.get(b, [])
        row.cell("| %s | %s | %s |" % (b, n, e), c[1:3] == [n, e], str(c[:3]))
        row.cell("%s slots 20,21" % b, len(c) > 4 and c[4] == "20,21")
        row.cell("%s CPU columns numeric" % b, len(c) > 8 and all(is_num(x) for x in c[5:8])
                 and re.match(r"^\d+/\d+$", c[8]) is not None, str(c[5:9]))
    row.cell("### b03 regstub_fail tail holds REGSTUB deliberate failure + line 40, not line 05", bool(m)
             and "REGSTUB deliberate failure" in tail and "REGSTUB line 40" in tail and "REGSTUB line 05" not in tail)
    row.cell("b03 copy path exists", bool(cm) and os.path.exists(cm.group(1)))
    row.cell("census row: crash_regstub_<pid>.log, REGSTUB fake crash, regstub_fail, no H13-T1",
             len(crow) == 1 and re.search(r"crash_regstub_\d+\.log", crow[0]) is not None
             and "REGSTUB fake crash" in crow[0] and "regstub_fail" in crow[0] and "H13-T1" not in crow[0])
    row.cell("batches\\b01..b03.json exist", all(os.path.exists(os.path.join(out, "batches", "b0%d.json" % i)) for i in (1, 2, 3)))

def u13_7(row):
    mds = {"i": row.write("i.md", "## REGRESSION-1 (fixture)\n- batch 1: test_w2_inventory test_w2_host_screens\n"),
           "ii": row.write("ii.md", "## REGRESSION-1 (fixture)\n- batch 1: regstub_missing\n"),
           "iii": row.write("iii.md", STUB_MD), "iv": row.write("iv.md", STUB_MD)}
    row.ev("run_regression.py exists: %s" % os.path.exists(RR))
    row.gate(os.path.exists(RR), "no regression runner")
    code = ("import sys, time; sys.path.insert(0, %r); import harness; harness._acquire_machine_lock(); "
            "print('HELD', flush=True); time.sleep(300)" % TESTDIR)
    for case, args, token in (("i", ["--pairs", "20"] + QUIET, "s26"), ("ii", ["--pairs", "20"] + QUIET, "regstub_missing"),
                              ("iii", ["--pairs", "26"] + QUIET, "slot 26"), ("iv", ["--pairs", "20", "--cpu-wait-min", "0"], "STALE")):
        out, holder, env = row.path("O_" + case), None, env_for(OXC_TEST_EXE=fake_exe(row, old=(case == "iv")))
        try:
            if case == "iii":  # a child holds slot 26's lock; ended by its own handle below
                holder = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                                          env=env_for(OXC_HARNESS_SLOT="26"))
                row.ev("(iii) holder pid %d says %r" % (holder.pid, holder.stdout.readline().strip()))
            p = run(row, [RR, "--batches", mds[case]] + args + ["--out", out], env, over="(%s)" % case)
        finally:
            if holder is not None:  # ended by its own handle, never by image name
                holder.terminate()
                row.ev("(iii) holder terminated by its handle, rc %s" % holder.wait(timeout=30))
        st = ([ln for ln in lines_of(read(os.path.join(out, "SUMMARY.md")) or p.stdout + p.stderr)
               if ln.startswith("STATUS: REFUSED:")] or [""])[0]
        jsons = glob.glob(os.path.join(out, "batches", "*.json"))
        row.ev("(%s) %s; batches json %d" % (case, st or "no STATUS: REFUSED line", len(jsons)))
        named = (token in st) if case != "iii" else ("slot" in st.lower() and re.search(r"\b26\b", st) is not None)
        row.cell("(%s) exit 4" % case, p.returncode == 4, "rc=%d" % p.returncode)
        row.cell("(%s) STATUS: REFUSED: naming %s" % (case, token), bool(st) and named)
        row.cell("(%s) no batches json" % case, not jsons)

def u13_8(row):
    md, out = row.write("k4.md", "## REGRESSION-8 (fixture)\n- batch 1: regstub_pass_a regstub_pass_b\n- batch 2: "
                        "regstub_pass_a regstub_pass_b\n- batch 3: regstub_fail regstub_pass_a\n"), row.path("O")
    p = runner(row, ["--batches", md, "--pairs", "20,22", "--exclusive", "regstub_fail", "--out", out] + QUIET,
               env_for(OXC_TEST_EXE=fake_exe(row), REGSTUB_SLEEP="4"))
    res = [((load(os.path.join(out, "batches", "b%02d.json" % i)) or {}).get("results", [])) for i in (1, 2, 3)]
    slots = [sorted(r.get("slot") for r in rs) for rs in res]
    win = [(min(r["start_epoch"] for r in rs), max(r["end_epoch"] for r in rs))
           if rs and all(is_num(r.get("start_epoch")) and is_num(r.get("end_epoch")) for r in rs) else None for rs in res]
    s = read(os.path.join(out, "SUMMARY.md")) or ""
    mode, b03 = [ln for ln in lines_of(s) if ln.startswith("mode:")], summary_rows(s).get("b03", [])
    row.ev("slots %s; windows %s; mode %s; b03 row %s" % (slots, win, mode, b03[:3]))
    row.cell("exit 1", p.returncode == 1, "rc=%d" % p.returncode)
    row.cell("b01/b02 slots {20, 21} and {22, 23}, one each", sorted(slots[:2]) == [[20, 21], [22, 23]], str(slots[:2]))
    row.cell("b01/b02 windows overlap", None not in win[:2] and win[0][0] <= win[1][1] and win[1][0] <= win[0][1])
    row.cell("b03 starts after both windows end", None not in win and win[2][0] >= max(win[0][1], win[1][1]))
    row.cell("mode: K=4 pairs [20, 22]", any(ln.startswith("mode: K=4 pairs [20, 22]") for ln in mode))
    row.cell("b03 exit 1", b03[1:3] == ["2", "1"], str(b03[:3]))

CHILD = r"""
import json, os, subprocess, sys
sys.path.insert(0, sys.argv[1])
root, calls, out = sys.argv[2], [], {}
before = set(os.listdir(root)) if os.path.isdir(root) else set()
class Rec(subprocess.Popen):
    def __init__(self, *a, **k):
        calls.append(repr(a)[:120])
        super().__init__(*a, **k)
subprocess.Popen = Rec
try:
    import run_regression as rr
except ImportError as exc:
    print("U13-9-JSON " + json.dumps({"import_error": "%s: %s" % (type(exc).__name__, exc)}))
    sys.exit(0)
after = set(os.listdir(root)) if os.path.isdir(root) else set()
out.update(new_dirs=sorted(d for d in after - before if d.startswith("s")), popen_calls=calls,
           harness_imported="harness" in sys.modules)
R = json.loads(sys.argv[3])
def safe(f, *a):
    try:
        return f(*a)
    except Exception as exc:
        return "error %r" % exc
for key, names in (("fam_inv", ["test_w2_inventory_held"]), ("fam_hs", ["test_w2_host_screens_turn", "x"]),
                   ("fam_u6", ["test_coop_peer_equip_screens"]), ("fam_none", ["test_w2_client_shoot"])):
    out[key] = safe(lambda n: sorted(rr.families(n)), names)
for key, x, y in (("c16_18", "16", "18"), ("c5_9", "5", "9"), ("c18_19", "18", "19")):
    out[key] = safe(rr.conflicts, R[x], R[y], getattr(rr, "EXCLUSIVE_TESTS", None))
print("U13-9-JSON " + json.dumps(out, default=repr))
"""

def u13_9(row):
    p = run(row, ["-c", CHILD, TESTDIR, TEST_ROOT, json.dumps(R130)], env_for())
    line = ([ln for ln in p.stdout.splitlines() if ln.startswith("U13-9-JSON ")] or [None])[0]
    row.gate(line is not None, "import child printed no result (rc %d)" % p.returncode)
    res = json.loads(line[len("U13-9-JSON "):])
    row.ev("import child: %s" % res)
    row.gate("import_error" not in res, "no regression runner")
    for key, want, name in (("fam_inv", ["s26"], "families inventory_held {s26}"), ("fam_u6", ["u6"], "families peer_equip_screens {u6}"),
                            ("fam_hs", ["s26"], "families host_screens_turn,x {s26}"), ("fam_none", [], "families client_shoot set()"),
                            ("c16_18", True, "conflicts(R130[16], R130[18]) True"), ("c5_9", True, "conflicts(R130[5], R130[9]) True"),
                            ("c18_19", False, "conflicts(R130[18], R130[19]) False")):
        got = res.get(key)
        row.cell(name, got is want if isinstance(want, bool) else got == want, str(got))
    row.cell("import starts nothing (no new s* dir, no subprocess)", not res.get("new_dirs") and not res.get("popen_calls"),
             "%s %s" % (res.get("new_dirs"), res.get("popen_calls")))

def main():
    t0, failed = time.time(), []
    for code, fn in [("U13-%d" % i, globals()["u13_%d" % i]) for i in range(1, 10)]:
        row = Row(code)
        try:
            fn(row)
        except RowStop:
            pass
        except Exception as exc:  # a crash in one row fails that row only
            row.failed.append("exception %s: %s" % (type(exc).__name__, exc))
        if row.failed:
            failed.append(code)
            print("%s FAIL: %s [kept %s]" % (code, "; ".join(row.failed), row.tmp), flush=True)
        else:
            print("%s PASS" % code, flush=True)
            shutil.rmtree(row.tmp, ignore_errors=True)
    print("SELFTEST: %d/9 rows PASS; FAILED: %s; wall %.1f s" % (9 - len(failed), ", ".join(failed) or "none", time.time() - t0))
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
