"""W2-U8h - test_w2_crash_attribution.py (docs rewrite/prompts/w2u8h_crash_attribution.md (f), rulings Q1 (b), Q2-Q8 (a)):
F9495 / F9399, every game started from one exe writes its crash files into ONE <exe dir>/crashlogs, and the lane crash
readers count every NEW file there as their own crash, so a crash in one K-lane fails another lane's crash cells (F9399
captured it at K=2). The fix: the coop crash handler honours OXC_CRASHLOG_DIR, the harness gives each lane
crashlogs/s<slot>, every lane reader and the regression runner follow (F9563, F9564).
U8h-ENV: a game this test starts with its own Popen and OXC_CRASHLOG_DIR set writes its crashlog_probe log there.
U8h-DEF (players unchanged): the same without the variable keeps <exe dir>/crashlogs. U8h-DIR: a harness game (game b,
up through X) reports this lane's crashlogs/s<slot>. U8h-X: a real child Python on slot + 50 (lane A) force-crashes its
game; none of the 13 lane readers (spec R3 C) may list lane A's files as new in this lane. U8h-B: game b force-crashes;
every reader sees this lane's own crash (non-vacuity). U8h-RR: a synthetic run_regression census attributes a lane
folder's file to that slot's test and keeps the time window for a root file.
A crash is identified only by the dump's MiscInfo pid, then its .log beside it. On a fully passing run the test deletes
exactly its own crash files and its temp root (Q8); on any failure it keeps everything (S27).
Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard or boot miss adds one "CAPTURE <id>:"
line. ONE foreground run, no skip, every row runs after a failure; exit 0 only when all pass, else 2.
Run: python tools/coop_test/test_w2_crash_attribution.py
"""
import inspect, json, os, shutil, struct, subprocess, sys, tempfile, time, types  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402
import session  # noqa: E402
import run_regression as rr  # noqa: E402
import test_w2_inventory_held as ih  # noqa: E402
import test_w2_host_screens as hs  # noqa: E402
import test_w2_client_landing as cl  # noqa: E402
import test_w2_client_landing_controls as clc  # noqa: E402
import test_w2_client_selection as csel  # noqa: E402
import test_w2_preview_restream as pv  # noqa: E402
import test_w2_restream_open_inventory as roi  # noqa: E402
import test_w2_select_destination_recopy as sdr  # noqa: E402
import test_w2_udp_rejoin as udp  # noqa: E402
import test_w2_shared_craft_loads as scl  # noqa: E402
import test_coop_basedef_temp_ufo_uaf as bd  # noqa: E402
import test_geoscape_sync as gs  # noqa: E402
CRASH_RC = 3  # the force_crash exit code on Windows (test_crash_produces_dump.py :24)
EXE_DIR = os.path.dirname(os.path.abspath(harness.EXE))
CRASHLOGS = os.path.join(EXE_DIR, "crashlogs")
SLOT_B, SLOT_A = harness.HARNESS_SLOT, harness.HARNESS_SLOT + 50
DIR_A, DIR_B = os.path.join(CRASHLOGS, "s%d" % SLOT_A), os.path.join(CRASHLOGS, "s%d" % SLOT_B)
B_DIR = os.path.join(harness.TEST_ROOT, "s%d_w2u8h_b" % SLOT_B)  # game b's user dir (make_user_dir's own rule)
JS = types.SimpleNamespace(host_dir=B_DIR, client_dir=B_DIR)  # R11's stand-in for its js
READERS = (  # spec R3 C: every lane reader of crash files at the tip, called exactly as its test calls it
    ("R1", lambda: session._crash_log_snapshot()),
    ("R2", lambda: ih.crash_files()),
    ("R3", lambda: hs.crash_census()),
    ("R4", lambda: cl.crash_files()),
    ("R5", lambda: clc.crash_files()),
    ("R6", lambda: csel.crash_files()),
    ("R7", lambda: pv.crash_names()),
    ("R8", lambda: roi.crash_names()),
    ("R9", lambda: sdr.crash_names()),
    ("R10", lambda: set(os.listdir(udp.CRASH_DIR)) if os.path.isdir(udp.CRASH_DIR) else set()),  # teardown's lambda :237
    ("R11", lambda: scl.crash_logs(JS)),
    ("R12", lambda: bd.crash_logs()),
    ("R13", lambda: set(gs.scan_logs({}, "w2u8h")["crash_files"])),
)
def census():  # {reader: set of basenames} right now
    return {rid: {os.path.basename(p) for p in fn()} for rid, fn in READERS}
def walk():  # {path: mtime} of every file under <exe dir>/crashlogs, any depth
    return {os.path.join(d, f): os.path.getmtime(os.path.join(d, f)) for d, _, fs in os.walk(CRASHLOGS) for f in fs}
def dmp_pid(path):
    """The ProcessId in a minidump's MiscInfo stream (type 15; F9561: every CrashHandler dump carries it), or None."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        sig, _ver, n, rva = struct.unpack_from("<IIII", data, 0)
        if sig != 0x504D444D:
            return None
        for i in range(n):
            stype, _size, srva = struct.unpack_from("<III", data, rva + 12 * i)
            if stype == 15:
                _sz, flags1, pid = struct.unpack_from("<III", data, srva)
                return pid if flags1 & 1 else None
    except (OSError, struct.error):
        return None
    return None
def crash_of(pid, w0, t_req, wait_s=10.0):
    """A crash's files: the new .dmp whose pid is `pid`, and every new .log beside it written since t_req - 1 s that holds
    'Code = 0xC0000005' (the VEH writes the log first, CH :387-:411)."""
    t_end, dmps, new = time.time() + wait_s, [], {}
    while True:
        new = {p: m for p, m in walk().items() if p not in w0}
        dmps = [p for p in new if p.endswith(".dmp") and dmp_pid(p) == pid]
        if dmps or time.time() >= t_end:
            break
        time.sleep(0.25)
    folder = os.path.dirname(dmps[0]) if len(dmps) == 1 else None
    logs = [p for p, m in new.items() if folder and p.endswith(".log") and os.path.dirname(p) == folder and m >= t_req - 1.0
            and "Code = 0xC0000005" in open(p, encoding="utf-8", errors="replace").read()]
    return {"dmp": dmps, "logs": logs, "folder": folder}
def own_spawn(gc, extra=None):
    """A game started the way a player or manual_session.py starts one (this test's own Popen, never GameClient.spawn, so
    the harness sets no OXC_CRASHLOG_DIR), headless like the harness; `extra` adds env keys."""
    env = {k: v for k, v in os.environ.items() if k != "OXC_CRASHLOG_DIR"}
    env.update(OXC_TEST_PORT="0", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", **(extra or {}))
    gc.proc = subprocess.Popen([harness.EXE, "-user", gc.user_dir], env=env, cwd=os.path.dirname(harness.EXE) or ".")

# ---- the frame (test_w2_cleanup_chain_reaper.py) ----
SITES = (session._crash_log_snapshot, ih.crash_files, hs.crash_census, cl.crash_files, clc.crash_files, csel.crash_files,
         pv.crash_names, roi.crash_names, sdr.crash_names, udp.teardown, scl.crash_logs, bd.crash_logs, gs.scan_logs)
def site(i):  # "<file>:<line>" of reader i's function at this tip
    try: return "%s:%d" % (os.path.basename(inspect.getsourcefile(SITES[i])), inspect.getsourcelines(SITES[i])[1])
    except (OSError, TypeError): return "?"
RUN = {"root": None, "b": None, "bErr": None, "probe": {}, "files": {}}  # this run's root, game b, probe / crash files
class GuardMiss(Exception): pass  # a guard cell failed: FIXTURE-STOP
class BootMiss(Exception): pass  # a spawn / connect failed
def short(x, n=300):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."
def safe(f):
    try: return f()
    except Exception as e: return "unreachable: %s" % short(str(e))
def tail(path, n=15):
    try:
        with open(path, encoding="utf-8", errors="replace") as f: return [x.rstrip() for x in f.readlines()][-n:]
    except OSError as e: return ["unreadable: %s" % e]
def nc(p): return os.path.normcase(os.path.abspath(p))
def same(a, b): return bool(a) and nc(a) == nc(b)
def under(p, d): return nc(p).startswith(nc(d) + os.sep)
def alive(gc): return gc is not None and gc.proc is not None and gc.proc.poll() is None
def timed(fn):  # (result, ms)
    t = time.perf_counter()
    out = fn()
    return out, round((time.perf_counter() - t) * 1000, 1)
class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.err, self.cap = rid, [], {}, None, None
        self.machines, self.seen, self.expect, self.child_out = [], [], {}, None  # machines: shut down at the row's end
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok: self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
    def guards(self, checks):  # every guard is judged and recorded; any miss stops the row before its named cells
        for name, ok, detail in checks: self.cell(name, ok, detail, guard=True)
        missed = [c["cell"] for c in self.cells if c["guard"] and not c["pass"]]
        if missed: raise GuardMiss("; ".join(missed))
def boot(r, gc, start):  # start() launches gc's game; a spawn / connect miss is a BootMiss
    t0 = time.time()
    try: start(); gc.connect()
    except Exception as e: raise BootMiss("%s: %s: %s" % (gc.name, type(e).__name__, short(str(e), 600)))
    r.ev.setdefault("bootS", {})[gc.name] = round(time.time() - t0, 1)
def holders(note, w0, roots=()):
    """The files holding `note`: every file new under crashlogs since w0 (any depth; a probe writes a new file) plus every
    file under `roots`."""
    cands = [p for p in walk() if p not in w0] + [os.path.join(d, f) for x in roots for d, _, fs in os.walk(x) for f in fs]
    out = []
    for p in cands:
        try:
            with open(p, "rb") as f:
                if note.encode("ascii") in f.read(): out.append(p)
        except OSError: pass
    return out
def probe(r, gc, rid, roots=()):  # crashlog_probe with a unique note; the reply and the files that hold the note
    note = "w2u8h %s probe %d %d" % (rid, os.getpid(), time.time_ns())
    w0 = walk()
    resp = safe(lambda: gc.cmd({"cmd": "crashlog_probe", "note": note}))
    RUN["probe"][rid] = hold = holders(note, w0, roots)
    r.ev.update(pid=gc.proc.pid, note=note, probe=resp, holders=hold)
    return resp if isinstance(resp, dict) else {}

# ---- U8h-ENV / -DEF / -DIR: where a game's crashlog_probe log lands ----
def u8h_env(r):
    env_dir = os.path.join(RUN["root"], "env_crashlogs")  # NOT created by the test
    e = harness.GameClient("u8h-env", 49791, harness.make_user_dir("w2u8h_env"))
    r.machines.append(e)
    boot(r, e, lambda: own_spawn(e, {"OXC_CRASHLOG_DIR": env_dir}))
    resp = probe(r, e, "ENV", (env_dir,))
    d, hold = resp.get("dir") or "", RUN["probe"]["ENV"]
    r.ev["envDir"] = env_dir
    r.guards([("ENV-G1: the probe replied ok", resp.get("ok") is True, r.ev["probe"])])
    r.cell("ENV-dir: the probe dir is OXC_CRASHLOG_DIR", same(d, env_dir), {"dir": d, "envDir": env_dir},
           "the crash handler ignores OXC_CRASHLOG_DIR: it reported %s (F9563)" % d)
    r.cell("ENV-file: exactly one file under OXC_CRASHLOG_DIR holds the note, none under crashlogs",
           len([p for p in hold if under(p, env_dir)]) == 1 and not [p for p in hold if under(p, CRASHLOGS)], hold,
           "the probe log is not in OXC_CRASHLOG_DIR alone (F9563)")
def u8h_def(r):
    g = harness.GameClient("u8h-def", 49792, harness.make_user_dir("w2u8h_def"))
    r.machines.append(g)
    boot(r, g, lambda: own_spawn(g))
    resp = probe(r, g, "DEF")
    d, hold = resp.get("dir") or "", RUN["probe"]["DEF"]
    r.guards([("DEF-G1: the probe replied ok", resp.get("ok") is True, r.ev["probe"])])
    r.cell("DEF-dir: without the variable the probe dir is <exe dir>/crashlogs", same(d, CRASHLOGS), d,
           "a game started without the harness left <exe dir>/crashlogs (players changed)")
    r.cell("DEF-file: the file holding the note is directly in crashlogs", len(hold) == 1
           and same(os.path.dirname(hold[0]), CRASHLOGS), hold, "the probe log is not directly in <exe dir>/crashlogs")
def u8h_dir(r):
    b = harness.GameClient("u8h-b", 49793, harness.make_user_dir("w2u8h_b"))
    r.machines.append(b)  # a boot miss shuts it down here; booted, it stays up through X and row B owns its shutdown
    try: boot(r, b, b.spawn)
    except BootMiss as e:
        RUN["bErr"] = str(e)
        raise
    r.machines.remove(b), r.seen.append(b)
    RUN["b"] = b
    resp = probe(r, b, "DIR")
    d, hold, cd = resp.get("dir") or "", RUN["probe"]["DIR"], getattr(harness, "CRASH_DIR", None)
    r.ev.update(crashDir=cd, userDir=b.user_dir)
    r.guards([("DIR-G1: game b booted and the probe replied ok", resp.get("ok") is True, r.ev["probe"])])
    r.cell("DIR-dir: harness.CRASH_DIR and the probe dir are crashlogs/s%d" % SLOT_B, same(cd, DIR_B) and same(d, DIR_B),
           {"CRASH_DIR": cd, "dir": d},
           "the harness gives this lane no crash folder: CRASH_DIR=%s, the game reported %s (F9563)" % (cd, d))
    r.cell("DIR-file: the file holding the note is in crashlogs/s%d" % SLOT_B, len(hold) == 1
           and same(os.path.dirname(hold[0]), DIR_B), hold,
           "this lane's probe log landed outside crashlogs/s%d (F9563)" % SLOT_B)

# ---- U8h-X: lane A's real crash; U8h-B: this lane's own crash ----
CHILD = '''import json, os, sys, time
sys.path.insert(0, %r)
import harness
a = harness.GameClient("u8h-a", 49794, harness.make_user_dir("w2u8h_a"))
a.spawn()
a.connect()
with open(sys.argv[1] + ".tmp", "w") as f:
    json.dump({"pid": a.proc.pid, "slot": harness.HARNESS_SLOT, "crashDir": getattr(harness, "CRASH_DIR", None)}, f)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
t = time.time()
try:
    a.cmd({"cmd": "force_crash"})
except Exception:
    pass
rc = a.proc.wait(timeout=30)
with open(sys.argv[2] + ".tmp", "w") as f:
    json.dump({"rc": rc, "requested": t}, f)
os.replace(sys.argv[2] + ".tmp", sys.argv[2])
a.shutdown(expected_returncodes=(3,))
'''
def files_ev(c):  # a crash's files for EVIDENCE: names, folder, the dump's pid
    return {"dmp": [os.path.basename(p) for p in c["dmp"]], "logs": [os.path.basename(p) for p in c["logs"]],
            "folder": c["folder"], "dumpPid": [dmp_pid(p) for p in c["dmp"]]}
def around(r, act):  # census, runner snapshot and walk before / after act(w0); act returns the crash's files
    w0 = walk()
    c0, ms0 = timed(census)
    r0 = rr.crash_snapshot(EXE_DIR)
    c = act(w0)
    c1, ms1 = timed(census)
    r1 = rr.crash_snapshot(EXE_DIR)
    new = {rid: sorted(c1[rid] - c0[rid]) for rid, _ in READERS}
    r.ev.update(readerNew=new, censusMs=[ms0, ms1], runnerNew=sorted(p for p in set(r1) - set(r0) if under(p, CRASHLOGS)))
    return c, new, r0, r1
def u8h_x(r):
    b, root = RUN["b"], RUN["root"]
    r.seen.append(b)
    child, pidf, donef, out = (os.path.join(root, n) for n in ("u8h_child.py", "u8h_pid.json", "u8h_done.json", "child.out"))
    r.child_out = out
    with open(child, "w", encoding="ascii", newline="\n") as f: f.write(CHILD % HERE)
    env = {k: v for k, v in os.environ.items() if k not in ("OXC_TIMELOG", "OXC_TIMELOG_SPAWNS", "OXC_CRASHLOG_DIR")}
    env["OXC_HARNESS_SLOT"] = str(SLOT_A)
    def act(w0):
        with open(out, "wb") as f:
            p = subprocess.Popen([sys.executable, child, pidf, donef], stdout=f, stderr=subprocess.STDOUT, cwd=root, env=env)
        try: r.ev["childRc"] = p.wait(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill(), p.wait(15)
            r.ev["childRc"] = "timeout (killed)"
        for k, path in (("childPid", pidf), ("childDone", donef)):
            r.ev[k] = safe(lambda: json.load(open(path, encoding="utf-8"))) if os.path.exists(path) else None
        pj, dj = r.ev["childPid"], r.ev["childDone"]
        ok = isinstance(pj, dict) and isinstance(dj, dict)
        return crash_of(pj["pid"], w0, dj["requested"]) if ok else {"dmp": [], "logs": [], "folder": None}
    A, new, r0, r1 = around(r, act)
    RUN["files"]["A"] = A["dmp"] + A["logs"]
    pj, dj = r.ev["childPid"], r.ev["childDone"]
    r.ev.update(A=files_ev(A), bAlive=alive(b), childOutTail=tail(out, 4))
    r.guards([("X-G1: the child exited 0, wrote its pid, and its game's rc == %d" % CRASH_RC, r.ev["childRc"] == 0
               and isinstance(pj, dict) and isinstance(dj, dict) and dj.get("rc") == CRASH_RC,
               {"childRc": r.ev["childRc"], "pid": pj, "done": dj}),
              ("X-G2: one new .dmp carries lane A's game pid", len(A["dmp"]) == 1, r.ev["A"]),
              ("X-G3: one new lane-A .log (Code = 0xC0000005) beside it", len(A["logs"]) == 1, r.ev["A"]),
              ("X-G4: game b alive", r.ev["bAlive"], r.ev["bAlive"])])
    r.cell("X-folder: lane A's .dmp and .log are in crashlogs/s%d" % SLOT_A, same(A["folder"], DIR_A), A["folder"],
           "lane A's crash files are not in crashlogs/s%d: %s (F9563)" % (SLOT_A, A["folder"]))
    for i, (rid, _) in enumerate(READERS):
        r.cell("X-%s: %s lists nothing new in lane B" % (rid, site(i)), not new[rid], new[rid],
               "%s (%s) counts lane A's crash %s as new in lane B (F9399, F9495)" % (rid, site(i), new[rid]))
    r.cell("X-runner: the runner's census holds lane A's .dmp and .log",
           all(p in r1 and p not in r0 for p in RUN["files"]["A"]), r.ev["runnerNew"],
           "run_regression.crash_snapshot misses lane A's crash files")
def u8h_b(r):
    b = RUN["b"]
    r.machines.append(b)  # row B owns game b's shutdown, expecting the crash code
    r.expect[b.name] = (CRASH_RC,)
    def act(w0):
        t = time.time()
        try: b.cmd({"cmd": "force_crash"})
        except Exception as e: r.ev["cmdErr"] = "%s: %s" % (type(e).__name__, short(str(e)))
        try: r.ev["rc"] = b.proc.wait(timeout=30)
        except subprocess.TimeoutExpired: r.ev["rc"] = "alive after 30 s"
        return crash_of(b.proc.pid, w0, t)
    B, new, r0, r1 = around(r, act)
    RUN["files"]["B"] = B["dmp"] + B["logs"]
    name = os.path.basename(B["logs"][0]) if len(B["logs"]) == 1 else None
    r.ev.update(pid=b.proc.pid, B=files_ev(B))
    r.guards([("B-G1: game b's rc == %d" % CRASH_RC, r.ev["rc"] == CRASH_RC, r.ev["rc"]),
              ("B-G2: one new .dmp carries game b's pid", len(B["dmp"]) == 1, r.ev["B"]),
              ("B-G3: one new .log (Code = 0xC0000005) beside it", len(B["logs"]) == 1, r.ev["B"])])
    r.cell("B-folder: game b's .dmp and .log are in crashlogs/s%d" % SLOT_B, same(B["folder"], DIR_B), B["folder"],
           "this lane's crash files are not in crashlogs/s%d: %s (F9563)" % (SLOT_B, B["folder"]))
    for i, (rid, _) in enumerate(READERS):
        r.cell("B-%s: %s lists this lane's own crash log as new" % (rid, site(i)), name in new[rid], new[rid],
               "%s (%s) does not see this lane's own crash %s (a vacuous reader, F9563)" % (rid, site(i), name))
    r.cell("B-runner: the runner's census holds game b's .dmp and .log",
           all(p in r1 and p not in r0 for p in RUN["files"]["B"]), r.ev["runnerNew"],
           "run_regression.crash_snapshot misses this lane's crash files")

# ---- U8h-RR: the regression runner's census on a fake exe dir ----
def u8h_rr(r):
    fake = os.path.join(RUN["root"], "rr_exe")
    for s in ("s20", "s21"): os.makedirs(os.path.join(fake, "crashlogs", s))
    run = rr.Run(types.SimpleNamespace(exclusive=[], out=os.path.join(RUN["root"], "rr_out")), "REGRESSION-U8H",
                 {1: ["tA", "tB"]}, [20], None)
    run.exe_dir = fake
    run.crash_before = rr.crash_snapshot(fake)
    for rel in (("s20", "crash_u8h_a.log"), ("s21", "crash_u8h_b.log"), ("crash_u8h_root.log",)):
        with open(os.path.join(fake, "crashlogs", *rel), "w", encoding="ascii", newline="\n") as f:
            f.write("==== Crash/Log ====\nW2-U8h synthetic\n")
    t = time.time()
    run.batches[0].data = {"results": [{"test": "tA", "slot": 20, "start_epoch": t - 30, "end_epoch": t + 30},
                                       {"test": "tB", "slot": 21, "start_epoch": t - 30, "end_epoch": t + 30}]}
    run.crash_census()
    rows = {os.path.basename(p): sorted(test for _, test in then) for p, _s, _m, _l, then, _tag in run.crash_rows}
    r.ev.update(rows=rows, crashBefore=sorted(run.crash_before))
    r.cell("RR-census: the census lists the two lane-folder files and the root file", set(rows) == {
           "crash_u8h_a.log", "crash_u8h_b.log", "crash_u8h_root.log"}, rows,
           "the runner's census does not walk the lane folders (F9563)")
    r.cell("RR-slot: a lane folder's file names only that slot's test", rows.get("crash_u8h_a.log") == ["tA"]
           and rows.get("crash_u8h_b.log") == ["tB"], rows,
           "the runner does not attribute a lane folder's file to the test on that slot (F9563)")
    r.cell("RR-root: a root file keeps the time window (both tests)", rows.get("crash_u8h_root.log") == ["tA", "tB"], rows,
           "a crashlogs root file lost its time-window attribution")

ROWS = (("U8h-ENV", u8h_env), ("U8h-DEF", u8h_def), ("U8h-DIR", u8h_dir), ("U8h-X", u8h_x), ("U8h-B", u8h_b),
        ("U8h-RR", u8h_rr))
def capture(r):  # FIXTURE-STOP dump: each machine's state and log tail (+ X's child output)
    cap = {"childOut": tail(r.child_out, 25)} if r.child_out else {}
    for gc in r.seen + r.machines:
        p = gc.proc
        up = alive(gc) and gc.sock is not None
        st = safe(lambda: harness.GameClient._send(gc, {"cmd": "get_state"})) if up else "down"
        cap[gc.name] = {"pid": p and p.pid, "rc": p and p.poll(), "states": st.get("states", [])[-4:] if isinstance(st, dict)
                        else st, "logTail": tail(os.path.join(gc.user_dir, "openxcom.log"))}
    return cap
def exec_row(rid, fn):
    r, t0 = Row(rid), time.time()
    if rid in ("U8h-X", "U8h-B") and RUN["b"] is None:
        r.err = "boot (game b): %s" % (RUN["bErr"] or "row U8h-DIR did not boot it")
    else:
        try: fn(r)
        except GuardMiss as e: r.err = "GUARD %s" % e
        except BootMiss as e: r.err = "boot (%s)" % e
        except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
        r.cap = safe(lambda: capture(r)) if r.err else None  # while the machines still run
    for gc in r.machines:  # the row's own machines down before the next row (game b only in row B)
        if gc.proc is None or gc._shutdown_proc is gc.proc: continue
        try: gc.shutdown(expected_returncodes=r.expect.get(gc.name, (0,)))
        except Exception as e:
            r.err = (r.err + " | " if r.err else "") + "shutdown: %s" % short(str(e), 600)
            r.cap = r.cap or safe(lambda: capture(r))
    r.ev.update(rcAfterRow={gc.name: gc.proc and gc.proc.poll() for gc in r.machines + r.seen},
                wall=round(time.time() - t0, 1))
    return r
def report(r, results):
    r.ev["cells"] = [[c["cell"], "guard" if c["guard"] else "row", c["pass"]] for c in r.cells]
    print("EVIDENCE %s: %s" % (r.rid, json.dumps(r.ev, default=str)), flush=True)
    if r.cap is not None:
        print("CAPTURE %s: %s" % (r.rid, json.dumps(r.cap, default=str)), flush=True)
    fails = ["%s%s: %s" % ("GUARD " if c["guard"] else "", c["cell"], c["msg"]) for c in r.cells if not c["pass"]]
    fails += [r.err] if r.err and not r.err.startswith("GUARD") else []
    results[r.rid] = not fails
    print("PASS %s" % r.rid if not fails else "FAIL %s: %s" % (r.rid, " || ".join(fails)), flush=True)
def b_down():  # game b, if a row did not shut it down: its own Popen handle only
    b = RUN["b"]
    if alive(b):
        try: b.shutdown(expected_returncodes=(0, CRASH_RC))
        except Exception as e: print("game b shutdown: %s" % short(str(e)), flush=True)
def cleanup(passed):  # Q8: only on a fully passing run, exactly this test's own crash files and its root
    own = RUN["files"].get("A", []) + RUN["files"].get("B", []) + RUN["probe"].get("DIR", []) + RUN["probe"].get("DEF", [])
    if not passed:
        print("EVIDENCE U8h-cleanup: %s" % json.dumps({"deleted": [], "kept": own + RUN["probe"].get("ENV", []),
              "root": RUN["root"]}), flush=True)
        return
    gone = []
    for p in own:
        try: os.remove(p); gone.append(p)
        except OSError as e: print("cleanup %s: %s" % (p, e), flush=True)
    shutil.rmtree(RUN["root"], ignore_errors=True)
    print("EVIDENCE U8h-cleanup: %s" % json.dumps({"deleted": gone, "rootRemoved": not os.path.exists(RUN["root"]),
          "root": RUN["root"]}), flush=True)

def main():
    t0, results = time.time(), {}
    RUN["root"] = root = tempfile.mkdtemp(prefix="w2u8h_")  # outside TEST_ROOT
    os.makedirs(DIR_A, exist_ok=True)  # before the first row: no listdir reader ever sees a new folder name
    os.makedirs(DIR_B, exist_ok=True)
    print("EVIDENCE U8h-root: %s" % json.dumps({"root": root, "slotA": SLOT_A, "slotB": SLOT_B, "crashlogs": CRASHLOGS}),
          flush=True)
    try:
        for rid, fn in ROWS: report(exec_row(rid, fn), results)
    finally:
        b_down()
    passed, failed = [x for x, _ in ROWS if results.get(x)], [x for x, _ in ROWS if not results.get(x)]
    cleanup(not failed)
    print("\ntest_w2_crash_attribution: %d/%d passed (pass=%s fail=%s) in %.1fs (crash files %s)" % (len(passed), len(ROWS),
          passed, failed, time.time() - t0, "removed" if not failed else "kept"), flush=True)
    return 0 if not failed else 2
if __name__ == "__main__":
    sys.exit(main())
