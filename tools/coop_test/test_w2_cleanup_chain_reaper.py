"""W2-U8g - test_w2_cleanup_chain_reaper.py (docs rewrite/prompts/w2u8g_cleanup_chain_reaper.md (f), ruling
R-U8g-T0-1 (a)): F9068, a clean-up `host.shutdown(); client.shutdown()` stops at a host shutdown that raises (a crashed
or hung host game), so the client game runs on after Python exits; F9215, three live chains are caught in-process and
the next mode / group runs beside the leaked game (test_cydonia_coop_start.run_mode, shoot_pr87_ui.group_campaign_votes
/ group_skirmish).
U8g-EXIT: a real child Python spawns two games through the harness, kills the host's and runs the chain uncaught; this
process reads each game through an OpenProcess handle opened while it ran (the child env sets OXC_TIMELOG_SPAWNS=1,
R-U8g-T0-1). U8g-CY / -PV / -PS: ChainGC, bound as the module's GameClient, kills the host's game after both connected
and raises, so the function's own clean-up meets a failed host shutdown. U8g-C: the chain in-process, then
harness._reap_spawned_games(). U8g-H: a quit-dropping socket, then the reaper (W2-U8e's hang dump must survive). U8g-X:
the bystander (this test's own Popen, up before CY) is never touched. harness.TEMP_ROOT points at this run's temp dir.
Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard or boot miss adds one "CAPTURE <id>:"
line. ONE foreground run, no skip, every row runs after a failure; exit 0 only when all pass, else 2.
Run: python tools/coop_test/test_w2_cleanup_chain_reaper.py
"""
import ctypes, json, os, shutil, subprocess, sys, tempfile, time  # noqa: E401
from ctypes import wintypes
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402
import test_cydonia_coop_start as cy  # noqa: E402
import shoot_pr87_ui as pr  # noqa: E402
KRC = harness.KILLED_RETURN_CODE
K32 = ctypes.WinDLL("kernel32", use_last_error=True)
K32.OpenProcess.argtypes, K32.OpenProcess.restype = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD), wintypes.HANDLE
K32.WaitForSingleObject.argtypes, K32.WaitForSingleObject.restype = (wintypes.HANDLE, wintypes.DWORD), wintypes.DWORD
K32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
K32.GetExitCodeProcess.restype = wintypes.BOOL
K32.TerminateProcess.argtypes, K32.TerminateProcess.restype = (wintypes.HANDLE, wintypes.UINT), wintypes.BOOL
K32.CloseHandle.argtypes, K32.CloseHandle.restype = (wintypes.HANDLE,), wintypes.BOOL
ACCESS = 0x00100000 | 0x1000 | 0x0001  # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE
BY = {"gc": None, "err": None, "bootS": None, "alive": []}  # the bystander and its liveness after each row
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
def events(pid, op=None):
    return [e for e in list(harness._PORT_FILE_HISTORY) if e.get("game_pid") == pid and op in (None, e["operation"])]
def mach(gc):  # one machine right now: pid, alive, rc, a clean shutdown done
    p = gc.proc
    return {"pid": p and p.pid, "alive": p is not None and p.poll() is None, "rc": p and p.poll(),
            "shutdownDone": p is not None and gc._shutdown_proc is p}
def by_alive():
    return BY["gc"] is not None and BY["gc"].proc is not None and BY["gc"].proc.poll() is None
class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.err, self.cap, self.tmp, self.machines = rid, [], {}, None, None, None, []
        self.child_out = None
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok: self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
    def guards(self, checks):  # every guard is judged and recorded; any miss stops the row before its named cells
        for name, ok, detail in checks: self.cell(name, ok, detail, guard=True)
        missed = [c["cell"] for c in self.cells if c["guard"] and not c["pass"]]
        if missed: raise GuardMiss("; ".join(missed))

# ---- U8g-EXIT: the child is spec (f) code text; liveness through handles opened while the games ran ----
CHILD = '''import json, os, sys
sys.path.insert(0, %r)
import harness
a = harness.GameClient("u8g-x-host", 49766, harness.make_user_dir("w2u8g_exit_host"))
b = harness.GameClient("u8g-x-client", 49767, harness.make_user_dir("w2u8g_exit_client"))
a.spawn(); b.spawn()
with open(sys.argv[1] + ".tmp", "w") as f:
    json.dump({"pids": [a.proc.pid, b.proc.pid]}, f)
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
a.connect(); b.connect()
open(sys.argv[2], "w").close()
sys.stdin.readline()
a.proc.kill(); a.proc.wait(timeout=15)   # the stand-in: the first game is gone, so its shutdown() raises
a.shutdown(); b.shutdown()               # F9068's chain, uncaught: the process exits 1 through atexit
'''
def pstate(h):  # [exited, exit code] of a process handle (code 259 = STILL_ACTIVE)
    code = wintypes.DWORD(0)
    exited = K32.WaitForSingleObject(h, 0) == 0
    K32.GetExitCodeProcess(h, ctypes.byref(code))
    return [exited, code.value]
def u8g_exit(r):
    tmp = r.tmp = tempfile.mkdtemp(prefix="w2u8g_exit_")
    files = ("u8g_exit_child.py", "pids.json", "ready", "child.out", "tl.csv")
    child, pids, ready, out, tl = (os.path.join(tmp, n) for n in files)
    r.child_out = out
    with open(child, "w", encoding="ascii", newline="\n") as f: f.write(CHILD % HERE)
    env = dict(os.environ, OXC_TIMELOG=tl, OXC_AGENT="w2u8g-child", OXC_TIMELOG_SPAWNS="1")  # R-U8g-T0-1 (a)
    with open(out, "wb") as f:
        p = subprocess.Popen([sys.executable, child, pids, ready], stdin=subprocess.PIPE, stdout=f,
                             stderr=subprocess.STDOUT, env=env, cwd=tmp)
    gp, hs, t0, ev = [], [], time.monotonic(), r.ev
    try:
        while not os.path.exists(pids) and p.poll() is None and time.monotonic() - t0 < 60: time.sleep(0.05)
        if os.path.exists(pids):
            with open(pids, encoding="utf-8") as f: gp = json.load(f)["pids"]
        hs = [K32.OpenProcess(ACCESS, False, x) for x in gp]
        ev.update(pids=gp, aliveAtOpen=[bool(h) and not pstate(h)[0] for h in hs])
        t1 = time.monotonic()
        while not os.path.exists(ready) and p.poll() is None and time.monotonic() - t1 < 120: time.sleep(0.05)
        ev["readyS"] = round(time.monotonic() - t0, 1)
        if not os.path.exists(ready):
            raise BootMiss("the child never reported both games connected (child rc %s)" % p.poll())
        try: p.stdin.write(b"\n"), p.stdin.close()
        except OSError as e: ev["stdinError"] = str(e)
        ev["childRc"] = rc = p.wait(timeout=120)
        ev["after"] = after = [pstate(h) if h else None for h in hs]  # right after the child exited
        with open(out, encoding="utf-8", errors="replace") as f: text = f.read()
        reap = [safe(lambda: json.loads(x[len("[harness-reap] "):])) for x in text.splitlines()
                if x.startswith("[harness-reap] ")]
        rows = []
        if os.path.exists(tl):
            with open(tl, encoding="utf-8") as f:
                rows = [x.split(",", 4)[3:] for x in f.read().splitlines() if x.strip()]
        ev.update(reapLines=reap, tlEvents=rows, childOutTail=text.splitlines()[-4:])
        host_line = "u8g-x-host: shutdown failed: rc=%s" % KRC
        r.guards([("EXIT-G1: the child wrote two pids, both games alive when their handles opened", len(gp) == 2
                   and all(ev["aliveAtOpen"]), ev),
                  ("EXIT-G2: the child exited 1 and child.out holds %r" % host_line, rc == 1 and host_line in text,
                   {"childRc": rc, "childOutTail": ev["childOutTail"]}),
                  ("EXIT-G3: the host's game exited with code %s" % KRC, after[0] == [True, KRC], after)])
        r.cell("EXIT-reap: right after the child exited, the client's game has exited with code 0",
               after[1] == [True, 0], after,
               "an uncaught chain raise ended the process and left u8g-x-client running (F9068)")
        names = [x.get("name") if isinstance(x, dict) else x for x in reap]
        evs = [e for e, _ in rows]
        se = [i for i, (e, d) in enumerate(rows) if e == "spawn_end" and d.startswith("u8g-x-client ")]
        te = [i for i, e in enumerate(evs) if e == "test_end"]
        r.cell("EXIT-line: one [harness-reap] line, u8g-x-client rc 0, none for the host; tl.csv: its spawn_end "
               "before test_end",
               len(reap) == 1 and names == ["u8g-x-client"] and reap[0].get("rc") == 0 and "u8g-x-host" not in names
               and len(se) == 1 and len(te) == 1 and se[0] < te[0], {"reapLines": reap, "tlEvents": evs},
               "the child's exit printed no [harness-reap] line for u8g-x-client (F9068)")
    finally:
        ev["terminated"] = []
        for x, h in zip(gp, hs):  # any game still running is ended through ITS handle; every handle closed
            if h and not pstate(h)[0]:
                ok = bool(K32.TerminateProcess(h, 1))
                ev["terminated"].append({"pid": x, "ok": ok, "wait": K32.WaitForSingleObject(h, 15000)})
            if h: K32.CloseHandle(h)
        if p.poll() is None:
            p.kill(), p.wait(15)
        ev["exitWall"] = round(time.monotonic() - t0, 1)

# ---- the bystander, ChainGC and NoQuitSock are spec (f) code text ----
def own_spawn(gc):
    """W2-U8g bystander: started the way manual_session.py / repro74_setup.py start theirs (the test's own Popen, never
    GameClient.spawn), headless like the harness; the reaper must never touch it."""
    env = os.environ.copy()
    env.update(OXC_TEST_PORT="0", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    gc.proc = subprocess.Popen([harness.EXE, "-user", gc.user_dir], env=env, cwd=os.path.dirname(harness.EXE) or ".")
class ChainGC(harness.GameClient):
    """W2-U8g stand-in (test only): records every instance a function builds while installed; right after the real connect()
    of the last of `want` instances it ends the FIRST instance's game (a crash stand-in: rc KILLED_RETURN_CODE, so that
    machine's shutdown() raises) and raises, so the function's own clean-up runs with its first game already gone."""
    made, want, fired, text, alive_at_fire = [], 0, 0, None, None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        ChainGC.made.append(self)

    def connect(self, *a, **k):
        r = super().connect(*a, **k)
        if ChainGC.want and len(ChainGC.made) == ChainGC.want and self is ChainGC.made[-1] and not ChainGC.fired:
            ChainGC.fired += 1
            ChainGC.alive_at_fire = [gc.proc is not None and gc.proc.poll() is None for gc in ChainGC.made]
            first = ChainGC.made[0].proc
            first.kill()
            first.wait(timeout=15)
            raise RuntimeError(ChainGC.text)
        return r
class NoQuitSock:
    """W2-U8e stand-in (per INSTANCE): the game's control socket with the harness's quit line dropped, so the game
    never hears quit and shutdown() runs its 15 s timeout and forced kill against a live game."""
    def __init__(self, s):
        self.s, self.dropped = s, 0
    def sendall(self, b):
        if b'"cmd": "quit"' in b:
            self.dropped += 1
            return None
        return self.s.sendall(b)
    def close(self):
        return self.s.close()
    def __getattr__(self, n):
        return getattr(self.s, n)

# ---- U8g-CY / -PV / -PS: a module chain with its host's game gone ----
def chain_row(r, mod, target, where, nxt):
    ChainGC.made, ChainGC.fired, ChainGC.alive_at_fire, ChainGC.want = [], 0, None, 2
    ChainGC.text = "W2-U8g stand-in: %s failed after both games started (F9215)" % r.rid
    r.machines, orig, raised, tag = ChainGC.made, mod.GameClient, None, r.rid[4:]
    mod.GameClient = ChainGC
    try:
        try: target()
        except Exception as e: raised = [type(e).__name__, str(e)]
        ms, by = [mach(gc) for gc in ChainGC.made], by_alive()  # right after the call, before any clean-up
    finally:
        mod.GameClient = orig
    r.ev.update(standIn={"fired": ChainGC.fired, "aliveAtFire": ChainGC.alive_at_fire, "pids": [m["pid"] for m in ms]},
                raised=raised, machines=dict(zip([gc.name for gc in ChainGC.made], ms)), bystanderAfterCall=by)
    want = "host: shutdown failed: rc=%s" % KRC
    r.guards([("%s-G1: the stand-in fired once" % tag, ChainGC.fired == 1, r.ev["standIn"]),
              ("%s-G2: the call raised a RuntimeError containing %r" % (tag, want), raised is not None
               and raised[0] == "RuntimeError" and want in raised[1], raised),
              ("%s-G3: two machines, each with a proc" % tag, len(ChainGC.made) == 2
               and all(gc.proc is not None for gc in ChainGC.made), ms),
              ("%s-G4: both alive at the fire" % tag, ChainGC.alive_at_fire == [True, True], ChainGC.alive_at_fire),
              ("%s-G5: the bystander alive after the call" % tag, by, by)])
    r.cell("%s-chain: right after the call the client exited rc 0 and shutdownDone" % tag, ms[1]["rc"] == 0
           and ms[1]["shutdownDone"], ms[1], "%s's clean-up stopped at the failed host shutdown and left the client "
           "running beside the next %s (F9215)" % (where, nxt))
def u8g_cy(r):
    chain_row(r, cy, lambda: cy.run_mode("coop", (49761, 49762), 47781), "test_cydonia_coop_start.run_mode", "mode")
def u8g_pv(r): chain_row(r, pr, pr.group_campaign_votes, "shoot_pr87_ui.group_campaign_votes", "group")
def u8g_ps(r): chain_row(r, pr, pr.group_skirmish, "shoot_pr87_ui.group_skirmish", "group")

# ---- U8g-C / -H (in-process): the harness reaper called directly ----
def boot(r, *specs):  # (name, label, user dir) each: spawn + connect; a miss fails the row "boot"
    t0 = time.time()
    try:
        for name, label, d in specs:
            r.machines.append(harness.GameClient(name, label, harness.make_user_dir(d)))
            r.machines[-1].spawn(), r.machines[-1].connect()
    except Exception as e: raise BootMiss("%s: %s" % (type(e).__name__, short(str(e), 600)))
    r.ev.setdefault("bootS", []).append(round(time.time() - t0, 1))
    return r.machines[-len(specs):]
def reap():  # the reaper, or why there is none (AttributeError on the red: the named red, not a crash)
    t0 = time.monotonic()
    try: harness._reap_spawned_games()
    except AttributeError as e: return "AttributeError: %s" % e, round(time.monotonic() - t0, 1)
    return None, round(time.monotonic() - t0, 1)
def u8g_c(r):
    host, client = boot(r, ("u8g-c-host", 49763, "w2u8g_c_host"), ("u8g-c-client", 49764, "w2u8g_c_client"))
    host.proc.kill(); host.proc.wait(timeout=15)
    chain = None
    try: host.shutdown(); client.shutdown()  # F9068's chain, in-process
    except RuntimeError as e: chain = str(e)
    after_chain = mach(client)
    absent, secs = reap()
    by, ms = by_alive(), {gc.name: mach(gc) for gc in (host, client)}
    pids = {"host": host.proc.pid, "client": client.proc.pid, "bystander": BY["gc"].proc.pid if BY["gc"] else None}
    reaped = {k: events(v, "reaped") for k, v in pids.items()}
    r.ev.update(chain=chain, clientAfterChain=after_chain, reaper=absent or "called", reaperS=secs, machines=ms,
                bystanderAfterCall=by, reaped={k: [{x: e.get(x) for x in ("game_returncode", "error")} for e in v]
                                               for k, v in reaped.items()})
    want = "u8g-c-host: shutdown failed: rc=%s" % KRC
    r.guards([("C-G1: the chain raised %r" % want, chain is not None and want in chain, chain),
              ("C-G2: the client alive after the chain (F9068's premise)", after_chain["alive"], after_chain),
              ("C-G3: the bystander alive after the reaper call (or its absence)", by, by)])
    c = ms["u8g-c-client"]
    r.cell("C-reap: the client exited rc 0, shutdownDone, exactly one reaped event carries its pid", c["rc"] == 0
           and c["shutdownDone"] and len(reaped["client"]) == 1, {"client": c, "reaped": r.ev["reaped"]},
           "harness has no _reap_spawned_games: the client is left running after the chain (F9068)" if absent
           else "the reaper did not shut the client down exactly once (F9068)")
    r.cell("C-scope: no reaped event carries the host's or the bystander's pid", not reaped["host"]
           and not reaped["bystander"], r.ev["reaped"], "the reaper touched a game that was not its to shut down")
def u8g_h(r):
    gc, = boot(r, ("u8g-h", 49765, "w2u8g_h"))
    pid, alive0 = gc.proc.pid, gc.proc.poll() is None
    ns = gc.sock = NoQuitSock(gc.sock)
    absent, secs = reap()
    if gc.sock is ns:  # the red (no reaper): the real socket back before the row's clean-up, which then quits normally
        gc.sock = ns.s
    dumps, reaped = events(pid, "shutdown_dump"), events(pid, "reaped")
    d = dumps[0] if len(dumps) == 1 else {}
    r.ev.update(pid=pid, reaper=absent or "called", reaperS=secs, dropped=ns.dropped, rc=gc.proc.poll(),
                dumpEvents=[{k: e.get(k) for k in ("dump", "dumpBytes", "dumpMs", "dumpError")} for e in dumps],
                dumpExists=bool(d.get("dump")) and os.path.exists(d["dump"]),
                reaped=[{k: e.get(k) for k in ("game_returncode", "error")} for e in reaped],
                bystanderAfterCall=by_alive())
    r.guards([("H-G1: the game was alive before the call", alive0, alive0)])
    r.cell("H-dump: the reaper returned, >= 15 s, quit dropped once, rc %s, one dump (> 0 B), one reaped event with "
           "forced_kill=True" % KRC, absent is None and secs >= 15 and ns.dropped == 1 and r.ev["rc"] == KRC
           and r.ev["dumpExists"] and (d.get("dumpBytes") or 0) > 0 and len(reaped) == 1
           and "forced_kill=True" in str(reaped[0].get("error")), r.ev,
           "harness has no _reap_spawned_games: a hung game is left running and never dumped (F8563, F9068)" if absent
           else "the reaper did not keep W2-U8e's dump path for a hung game (F8563, F9068)")

# ---- U8g-X (negative control): the bystander was never touched ----
def u8g_x(r):
    U = BY["gc"]
    reg = U in getattr(harness, "_SPAWNED", [])
    text = None
    try: U.shutdown()
    except RuntimeError as e: text = str(e)
    r.ev.update(pid=U.proc.pid, bootS=BY["bootS"], aliveAfterRows=BY["alive"], registered=reg, shutdownText=text,
                rc=U.proc.poll())
    r.cell("X-alive: the bystander alive after every row", BY["alive"] and all(a for _, a in BY["alive"]), BY["alive"],
           "a game this test started with its own Popen was ended by the harness")
    r.cell("X-unregistered: the bystander is not in harness._SPAWNED", not reg, reg,
           "a hand-started game was registered")
    r.cell("X-own: its own shutdown() gives rc 0", text is None and r.ev["rc"] == 0, {"text": text, "rc": r.ev["rc"]},
           "the bystander did not shut down cleanly")
ROWS = (("U8g-EXIT", u8g_exit), ("U8g-CY", u8g_cy), ("U8g-PV", u8g_pv), ("U8g-PS", u8g_ps), ("U8g-C", u8g_c),
        ("U8g-H", u8g_h), ("U8g-X", u8g_x))
def capture(r):  # FIXTURE-STOP dump: each machine's state, history and log tail (+ the EXIT child's output)
    cap = {"childOut": tail(r.child_out, 25)} if r.child_out else {}
    for gc in r.machines:
        p = gc.proc
        up = p is not None and p.poll() is None and gc.sock is not None
        st = safe(lambda: harness.GameClient._send(gc, {"cmd": "get_state"})) if up else "down"
        hist = [e["operation"] for e in events(p.pid)] if p else []
        cap[gc.name] = {"pid": p and p.pid, "rc": p and p.poll(), "history": hist,
                        "states": st.get("states", [])[-4:] if isinstance(st, dict) else st,
                        "logTail": tail(os.path.join(gc.user_dir, "openxcom.log"))}
    return cap
def exec_row(rid, fn):
    r, t0 = Row(rid), time.time()
    if BY["err"] and rid != "U8g-EXIT":
        r.err = "boot (bystander): %s" % BY["err"]  # its ONE CAPTURE line was printed when it missed
    else:
        try: fn(r)
        except GuardMiss as e: r.err = "GUARD %s" % e
        except BootMiss as e: r.err = "boot (%s)" % e
        except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
        r.cap = safe(lambda: capture(r)) if r.err else None  # while the machines still run
    live = [gc for gc in r.machines if gc.proc is not None and gc.proc.poll() is None]
    try: harness.shutdown_clients(*live)  # every row machine down before the next row; never the bystander
    except Exception as e:
        r.err = (r.err + " | " if r.err else "") + "shutdown: %s" % short(str(e), 600)
        r.cap = r.cap or safe(lambda: capture(r))
    by = by_alive() if BY["gc"] is not None and rid != "U8g-X" else None
    if by is not None: BY["alive"].append((rid, by))
    r.ev.update(bystanderAlive=by, rcAfterCleanup={gc.name: gc.proc and gc.proc.poll() for gc in r.machines},
                events={gc.name: {op: len(events(gc.proc.pid, op)) for op in ("reaped", "shutdown_dump")}
                        for gc in r.machines if gc.proc is not None}, wall=round(time.time() - t0, 1))
    if r.tmp and not r.err and all(c["pass"] for c in r.cells): shutil.rmtree(r.tmp, ignore_errors=True)
    elif r.tmp: r.ev["kept"] = r.tmp
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
def bystander_up():
    t0 = time.time()
    try:
        BY["gc"] = U = harness.GameClient("u8g-bystander", 49768, harness.make_user_dir("w2u8g_bystander"))
        own_spawn(U); U.connect()
        BY["bootS"] = round(time.time() - t0, 1)
    except Exception as e:
        BY["err"] = "%s: %s" % (type(e).__name__, short(str(e), 600))
        U = BY["gc"]
        rec = {"err": BY["err"], "pid": U and U.proc and U.proc.pid, "rc": U and U.proc and U.proc.poll(),
               "logTail": U and tail(os.path.join(U.user_dir, "openxcom.log"))}
        print("CAPTURE U8g-U: %s" % json.dumps(rec, default=str), flush=True)
def bystander_down():  # only if row X did not shut it down: its own Popen, never by image name
    U = BY["gc"]
    if U is not None and U.proc is not None and U.proc.poll() is None:
        try: harness.shutdown_clients(U)
        except Exception as e: print("bystander shutdown: %s" % short(str(e)), flush=True)
        if U.proc.poll() is None: U.proc.kill(), U.proc.wait(15)

def main():
    t0, results, saved = time.time(), {}, harness.TEMP_ROOT
    root = harness.TEMP_ROOT = tempfile.mkdtemp(prefix="w2u8g_diag_")  # this run's reports and dumps stay here
    print("EVIDENCE U8g-root: %s" % json.dumps({"diagnosticsRoot": root, "slot": harness.HARNESS_SLOT}), flush=True)
    try:
        report(exec_row(*ROWS[0]), results)  # first: the child takes the slot lock (F9219)
        bystander_up()
        for rid, fn in ROWS[1:]: report(exec_row(rid, fn), results)
    finally:
        bystander_down()
        harness.TEMP_ROOT = saved
    passed, failed = [x for x, _ in ROWS if results.get(x)], [x for x, _ in ROWS if not results.get(x)]
    if not failed: shutil.rmtree(root, ignore_errors=True)
    print("\ntest_w2_cleanup_chain_reaper: %d/%d passed (pass=%s fail=%s) in %.1fs (diagnostics %s)" % (len(passed),
          len(ROWS), passed, failed, time.time() - t0, "removed" if not failed else "kept in " + root), flush=True)
    return 0 if not failed else 2
if __name__ == "__main__":
    sys.exit(main())
