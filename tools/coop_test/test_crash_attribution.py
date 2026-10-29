"""test_crash_attribution.py: each harness lane's crash files stay in that lane's own folder.
Without a folder per lane, every game started from one exe writes its crash files into ONE <exe dir>/crashlogs, and the
lane crash readers count every NEW file there as their own crash, so a crash in one lane fails another lane's crash
cells when two tests run at once. The coop crash handler honours OXC_CRASHLOG_DIR, the harness gives each lane
crashlogs/s<slot>, and every lane reader and the regression runner follow.
env_var_dir: a game this test starts with its own Popen and OXC_CRASHLOG_DIR set writes its crashlog_probe log there.
default_dir (players unchanged): the same without the variable keeps <exe dir>/crashlogs. lane_dir: a harness game
(game b, up through other_lane_crash) reports this lane's crashlogs/s<slot>. other_lane_crash: a real child Python on
slot + 50 (lane A) force-crashes its game; none of the 13 lane readers may list lane A's files as new in this lane.
own_lane_crash: game b force-crashes; every reader sees this lane's own crash (non-vacuity). runner_census: a synthetic
run_regression census attributes a lane folder's file to that slot's test and keeps the time window for a root file.
A crash is identified only by the dump's MiscInfo pid, then its .log beside it. On a fully passing run the test deletes
exactly its own crash files and its temp root; on any failure it keeps everything.
Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard or boot miss adds one "CAPTURE <id>:"
line. ONE foreground run, no skip, every row runs after a failure; exit 0 only when all pass, else 2.
Run: python tools/coop_test/test_crash_attribution.py
"""
import inspect, json, os, shutil, struct, subprocess, sys, tempfile, time, types  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402
import session  # noqa: E402
import run_regression as rr  # noqa: E402
import test_inventory_held as ih  # noqa: E402
import test_host_screens as hs  # noqa: E402
import test_client_landing as cl  # noqa: E402
import test_client_landing_controls as clc  # noqa: E402
import test_client_selection as csel  # noqa: E402
import test_preview_restream as pv  # noqa: E402
import test_restream_open_inventory as roi  # noqa: E402
import test_select_destination_recopy as sdr  # noqa: E402
import test_udp_rejoin as udp  # noqa: E402
import test_shared_craft_loads as scl  # noqa: E402
import test_coop_basedef_temp_ufo_uaf as bd  # noqa: E402
import test_geoscape_sync as gs  # noqa: E402
CRASH_RC = 3  # the force_crash exit code on Windows (test_crash_produces_dump.py's CRASH_RETURN_CODE)
EXE_DIR = os.path.dirname(os.path.abspath(harness.EXE))
CRASHLOGS = os.path.join(EXE_DIR, "crashlogs")
SLOT_B, SLOT_A = harness.HARNESS_SLOT, harness.HARNESS_SLOT + 50
DIR_A, DIR_B = os.path.join(CRASHLOGS, "s%d" % SLOT_A), os.path.join(CRASHLOGS, "s%d" % SLOT_B)
# game b's user dir (make_user_dir's own rule)
B_DIR = os.path.join(harness.TEST_ROOT, "s%d_crash_attribution_b" % SLOT_B)
JS = types.SimpleNamespace(host_dir=B_DIR, client_dir=B_DIR)  # stands in for the js object scl.crash_logs takes
READERS = (  # every lane reader of crash files, called exactly as its test calls it
    ("session_snapshot", lambda: session._crash_log_snapshot()),
    ("inventory_held", lambda: ih.crash_files()),
    ("host_screens", lambda: hs.crash_census()),
    ("client_landing", lambda: cl.crash_files()),
    ("client_landing_controls", lambda: clc.crash_files()),
    ("client_selection", lambda: csel.crash_files()),
    ("preview_restream", lambda: pv.crash_names()),
    ("restream_open_inventory", lambda: roi.crash_names()),
    ("select_destination_recopy", lambda: sdr.crash_names()),
    # test_udp_rejoin's reader is a lambda inside its teardown: the same listing
    ("udp_rejoin", lambda: set(os.listdir(udp.CRASH_DIR)) if os.path.isdir(udp.CRASH_DIR) else set()),
    ("shared_craft_loads", lambda: scl.crash_logs(JS)),
    ("basedef_temp_ufo", lambda: bd.crash_logs()),
    ("geoscape_sync", lambda: set(gs.scan_logs({}, "crash_attribution")["crash_files"])),
)
def census():  # {reader: set of basenames} right now
    return {rid: {os.path.basename(p) for p in fn()} for rid, fn in READERS}
def walk():  # {path: mtime} of every file under <exe dir>/crashlogs, any depth
    return {os.path.join(d, f): os.path.getmtime(os.path.join(d, f)) for d, _, fs in os.walk(CRASHLOGS) for f in fs}
def dmp_pid(path):
    """The ProcessId in a minidump's MiscInfo stream (type 15; every CrashHandler dump carries it), or None."""
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
    'Code = 0xC0000005' (CrashHandler.cpp's vectoredHandler writes the log before the dump)."""
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

# ---- the frame (test_cleanup_chain_reaper.py) ----
SITES = (session._crash_log_snapshot, ih.crash_files, hs.crash_census, cl.crash_files, clc.crash_files, csel.crash_files,
         pv.crash_names, roi.crash_names, sdr.crash_names, udp.teardown, scl.crash_logs, bd.crash_logs, gs.scan_logs)
def site(i):  # "<file>:<line>" of reader i's function
    try: return "%s:%d" % (os.path.basename(inspect.getsourcefile(SITES[i])), inspect.getsourcelines(SITES[i])[1])
    except (OSError, TypeError): return "?"
RUN = {"root": None, "b": None, "bErr": None, "probe": {}, "files": {}}  # this run's root, game b, probe / crash files
class GuardMiss(Exception): pass  # a guard cell failed: setup failure
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
    note = "crash_attribution %s probe %d %d" % (rid, os.getpid(), time.time_ns())
    w0 = walk()
    resp = safe(lambda: gc.cmd({"cmd": "crashlog_probe", "note": note}))
    RUN["probe"][rid] = hold = holders(note, w0, roots)
    r.ev.update(pid=gc.proc.pid, note=note, probe=resp, holders=hold)
    return resp if isinstance(resp, dict) else {}

# ---- env_var_dir / default_dir / lane_dir: where a game's crashlog_probe log lands ----
def row_env_var_dir(r):
    env_dir = os.path.join(RUN["root"], "env_crashlogs")  # NOT created by the test
    e = harness.GameClient("env-game", 49791, harness.make_user_dir("crash_attribution_env"))
    r.machines.append(e)
    boot(r, e, lambda: own_spawn(e, {"OXC_CRASHLOG_DIR": env_dir}))
    resp = probe(r, e, "env_var_dir", (env_dir,))
    d, hold = resp.get("dir") or "", RUN["probe"]["env_var_dir"]
    r.ev["envDir"] = env_dir
    r.guards([("env-probe_ok: the probe replied ok", resp.get("ok") is True, r.ev["probe"])])
    r.cell("env-dir: the probe dir is OXC_CRASHLOG_DIR", same(d, env_dir), {"dir": d, "envDir": env_dir},
           "the crash handler ignores OXC_CRASHLOG_DIR: it reported %s" % d)
    r.cell("env-file: exactly one file under OXC_CRASHLOG_DIR holds the note, none under crashlogs",
           len([p for p in hold if under(p, env_dir)]) == 1 and not [p for p in hold if under(p, CRASHLOGS)], hold,
           "the probe log is not in OXC_CRASHLOG_DIR alone")
def row_default_dir(r):
    g = harness.GameClient("default-game", 49792, harness.make_user_dir("crash_attribution_default"))
    r.machines.append(g)
    boot(r, g, lambda: own_spawn(g))
    resp = probe(r, g, "default_dir")
    d, hold = resp.get("dir") or "", RUN["probe"]["default_dir"]
    r.guards([("default-probe_ok: the probe replied ok", resp.get("ok") is True, r.ev["probe"])])
    r.cell("default-dir: without the variable the probe dir is <exe dir>/crashlogs", same(d, CRASHLOGS), d,
           "a game started without the harness left <exe dir>/crashlogs (players changed)")
    r.cell("default-file: the file holding the note is directly in crashlogs", len(hold) == 1
           and same(os.path.dirname(hold[0]), CRASHLOGS), hold, "the probe log is not directly in <exe dir>/crashlogs")
def row_lane_dir(r):
    b = harness.GameClient("game-b", 49793, harness.make_user_dir("crash_attribution_b"))
    # a boot miss shuts it down here; booted, it stays up through other_lane_crash, and own_lane_crash owns its shutdown
    r.machines.append(b)
    try: boot(r, b, b.spawn)
    except BootMiss as e:
        RUN["bErr"] = str(e)
        raise
    r.machines.remove(b), r.seen.append(b)
    RUN["b"] = b
    resp = probe(r, b, "lane_dir")
    d, hold, cd = resp.get("dir") or "", RUN["probe"]["lane_dir"], getattr(harness, "CRASH_DIR", None)
    r.ev.update(crashDir=cd, userDir=b.user_dir)
    r.guards([("lane-probe_ok: game b booted and the probe replied ok", resp.get("ok") is True, r.ev["probe"])])
    r.cell("lane-dir: harness.CRASH_DIR and the probe dir are crashlogs/s%d" % SLOT_B,
           same(cd, DIR_B) and same(d, DIR_B),
           {"CRASH_DIR": cd, "dir": d},
           "the harness gives this lane no crash folder: CRASH_DIR=%s, the game reported %s" % (cd, d))
    r.cell("lane-file: the file holding the note is in crashlogs/s%d" % SLOT_B, len(hold) == 1
           and same(os.path.dirname(hold[0]), DIR_B), hold,
           "this lane's probe log landed outside crashlogs/s%d" % SLOT_B)

# ---- other_lane_crash: lane A's real crash; own_lane_crash: this lane's own crash ----
CHILD = '''import json, os, sys, time
sys.path.insert(0, %r)
import harness
a = harness.GameClient("game-a", 49794, harness.make_user_dir("crash_attribution_a"))
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
def row_other_lane_crash(r):
    b, root = RUN["b"], RUN["root"]
    r.seen.append(b)
    child, pidf, donef, out = (os.path.join(root, n)
                               for n in ("lane_a_child.py", "lane_a_pid.json", "lane_a_done.json", "child.out"))
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
    r.guards([("other-child_rc: the child exited 0, wrote its pid, and its game's rc == %d" % CRASH_RC,
               r.ev["childRc"] == 0 and isinstance(pj, dict) and isinstance(dj, dict) and dj.get("rc") == CRASH_RC,
               {"childRc": r.ev["childRc"], "pid": pj, "done": dj}),
              ("other-dump_pid: one new .dmp carries lane A's game pid", len(A["dmp"]) == 1, r.ev["A"]),
              ("other-log: one new lane-A .log (Code = 0xC0000005) beside it", len(A["logs"]) == 1, r.ev["A"]),
              ("other-b_alive: game b alive", r.ev["bAlive"], r.ev["bAlive"])])
    r.cell("other-folder: lane A's .dmp and .log are in crashlogs/s%d" % SLOT_A, same(A["folder"], DIR_A), A["folder"],
           "lane A's crash files are not in crashlogs/s%d: %s" % (SLOT_A, A["folder"]))
    for i, (rid, _) in enumerate(READERS):
        r.cell("other-%s: %s lists nothing new in lane B" % (rid, site(i)), not new[rid], new[rid],
               "%s (%s) counts lane A's crash %s as new in lane B" % (rid, site(i), new[rid]))
    r.cell("other-runner: the runner's census holds lane A's .dmp and .log",
           all(p in r1 and p not in r0 for p in RUN["files"]["A"]), r.ev["runnerNew"],
           "run_regression.crash_snapshot misses lane A's crash files")
def row_own_lane_crash(r):
    b = RUN["b"]
    r.machines.append(b)  # this row owns game b's shutdown, expecting the crash code
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
    r.guards([("own-rc: game b's rc == %d" % CRASH_RC, r.ev["rc"] == CRASH_RC, r.ev["rc"]),
              ("own-dump_pid: one new .dmp carries game b's pid", len(B["dmp"]) == 1, r.ev["B"]),
              ("own-log: one new .log (Code = 0xC0000005) beside it", len(B["logs"]) == 1, r.ev["B"])])
    r.cell("own-folder: game b's .dmp and .log are in crashlogs/s%d" % SLOT_B, same(B["folder"], DIR_B), B["folder"],
           "this lane's crash files are not in crashlogs/s%d: %s" % (SLOT_B, B["folder"]))
    for i, (rid, _) in enumerate(READERS):
        r.cell("own-%s: %s lists this lane's own crash log as new" % (rid, site(i)), name in new[rid], new[rid],
               "%s (%s) does not see this lane's own crash %s (a vacuous reader)" % (rid, site(i), name))
    r.cell("own-runner: the runner's census holds game b's .dmp and .log",
           all(p in r1 and p not in r0 for p in RUN["files"]["B"]), r.ev["runnerNew"],
           "run_regression.crash_snapshot misses this lane's crash files")

# ---- runner_census: the regression runner's census on a fake exe dir ----
def row_runner_census(r):
    fake = os.path.join(RUN["root"], "rr_exe")
    for s in ("s20", "s21"): os.makedirs(os.path.join(fake, "crashlogs", s))
    run = rr.Run(types.SimpleNamespace(exclusive=[], out=os.path.join(RUN["root"], "rr_out")), "crash-attribution",
                 {1: ["tA", "tB"]}, [20], None)
    run.exe_dir = fake
    run.crash_before = rr.crash_snapshot(fake)
    for rel in (("s20", "crash_synthetic_a.log"), ("s21", "crash_synthetic_b.log"), ("crash_synthetic_root.log",)):
        with open(os.path.join(fake, "crashlogs", *rel), "w", encoding="ascii", newline="\n") as f:
            f.write("==== Crash/Log ====\nsynthetic test file\n")
    t = time.time()
    run.batches[0].data = {"results": [{"test": "tA", "slot": 20, "start_epoch": t - 30, "end_epoch": t + 30},
                                       {"test": "tB", "slot": 21, "start_epoch": t - 30, "end_epoch": t + 30}]}
    run.crash_census()
    rows = {os.path.basename(p): sorted(test for _, test in then) for p, _s, _m, _l, then, _tag in run.crash_rows}
    r.ev.update(rows=rows, crashBefore=sorted(run.crash_before))
    r.cell("runner-files: the census lists the two lane-folder files and the root file", set(rows) == {
           "crash_synthetic_a.log", "crash_synthetic_b.log", "crash_synthetic_root.log"}, rows,
           "the runner's census does not walk the lane folders")
    r.cell("runner-slot: a lane folder's file names only that slot's test", rows.get("crash_synthetic_a.log") == ["tA"]
           and rows.get("crash_synthetic_b.log") == ["tB"], rows,
           "the runner does not attribute a lane folder's file to the test on that slot")
    r.cell("runner-root: a root file keeps the time window (both tests)",
           rows.get("crash_synthetic_root.log") == ["tA", "tB"], rows,
           "a crashlogs root file lost its time-window attribution")

ROWS = (("env_var_dir", row_env_var_dir), ("default_dir", row_default_dir), ("lane_dir", row_lane_dir),
        ("other_lane_crash", row_other_lane_crash), ("own_lane_crash", row_own_lane_crash),
        ("runner_census", row_runner_census))
def capture(r):  # Setup-failure dump: each machine's state and log tail (+ other_lane_crash's child output)
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
    if rid in ("other_lane_crash", "own_lane_crash") and RUN["b"] is None:
        r.err = "boot (game b): %s" % (RUN["bErr"] or "row lane_dir did not boot it")
    else:
        try: fn(r)
        except GuardMiss as e: r.err = "GUARD %s" % e
        except BootMiss as e: r.err = "boot (%s)" % e
        except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
        r.cap = safe(lambda: capture(r)) if r.err else None  # while the machines still run
    for gc in r.machines:  # the row's own machines down before the next row (game b only in own_lane_crash)
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
def cleanup(passed):  # only on a fully passing run, exactly this test's own crash files and its root
    own = (RUN["files"].get("A", []) + RUN["files"].get("B", []) + RUN["probe"].get("lane_dir", [])
           + RUN["probe"].get("default_dir", []))
    if not passed:
        print("EVIDENCE crash_file_cleanup: %s" % json.dumps({"deleted": [],
              "kept": own + RUN["probe"].get("env_var_dir", []), "root": RUN["root"]}), flush=True)
        return
    gone = []
    for p in own:
        try: os.remove(p); gone.append(p)
        except OSError as e: print("cleanup %s: %s" % (p, e), flush=True)
    shutil.rmtree(RUN["root"], ignore_errors=True)
    print("EVIDENCE crash_file_cleanup: %s" % json.dumps({"deleted": gone,
          "rootRemoved": not os.path.exists(RUN["root"]), "root": RUN["root"]}), flush=True)

def main():
    t0, results = time.time(), {}
    RUN["root"] = root = tempfile.mkdtemp(prefix="crash_attribution_")  # outside TEST_ROOT
    os.makedirs(DIR_A, exist_ok=True)  # before the first row: no listdir reader ever sees a new folder name
    os.makedirs(DIR_B, exist_ok=True)
    print("EVIDENCE run_root: %s" % json.dumps({"root": root, "slotA": SLOT_A, "slotB": SLOT_B,
                                                "crashlogs": CRASHLOGS}), flush=True)
    try:
        for rid, fn in ROWS: report(exec_row(rid, fn), results)
    finally:
        b_down()
    passed, failed = [x for x, _ in ROWS if results.get(x)], [x for x, _ in ROWS if not results.get(x)]
    cleanup(not failed)
    print("\ntest_crash_attribution: %d/%d passed (pass=%s fail=%s) in %.1fs (crash files %s)" % (len(passed), len(ROWS),
          passed, failed, time.time() - t0, "removed" if not failed else "kept"), flush=True)
    return 0 if not failed else 2
if __name__ == "__main__":
    sys.exit(main())
