"""W2-U8e - test_w2_bringup_capture.py (docs rewrite/prompts/w2u8e_bringup_capture.md (f)): F8376, a join_tcp sent
before the host's lobby listener opened (the client knocks ONCE, ~1.1 s later; refused = CoopState(16)); F8573, the
host-popup timeout said only last=None; F8563, a game alive 15 s after quit was killed with no trace of its threads.
U8e-G / -J / -K: no game, fakes (real harness.GameClients with a scripted per-instance _send). U8e-L (key 47277): a
LateListener stand-in (bound at once, listening from 8 s, relaying to the real lobby port) + a per-INSTANCE get_coop
rewrite (onConnect -1 until it listens) = a host whose listener opened 8 s late. U8e-A (key 47278): a never-listening
stand-in. U8e-D: a control socket that drops quit, so shutdown() force-kills a live game. harness.TEMP_ROOT points at
this run's own temp dir. Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard or boot miss
adds one "CAPTURE <id>:" line. ONE foreground run, no skip, every row runs after a failure; exit 0 only when all pass,
else 2. Run: python tools/coop_test/test_w2_bringup_capture.py
"""
import contextlib, glob, io, json, os, shutil, socket, struct, subprocess, sys, tempfile, threading, time, types  # noqa
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, session  # noqa: E401,E402
import repro_atom_walk as raw  # noqa: E402
KEY_L, KEY_A = "47277", "47278"
JT = {"cmd": "join_tcp", "ip": "127.0.0.1", "player": "ClientPlayer"}
VIEW = ("onConnect", "coopDialog", "serverOwner", "coopSession", "clientName", "host")
POPUP_MSG = "host: timed out waiting for host popup (last=None)"
LOG = []  # (machine, cmd, request) of every fake GameClient request
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
def jload(path):
    with open(path, encoding="utf-8") as f: return json.load(f)
def ms(t0): return int((time.monotonic() - t0) * 1000)
def forget(key):  # every registry the harness has (the red harness has only the first)
    for name in ("_EPHEMERAL_COOP_PORTS", "_COOP_HOSTS", "_COOP_JOINERS"): getattr(harness, name, {}).pop(key, None)
def diag_dir(): return os.path.join(harness.TEMP_ROOT, "oxc-coop-port-diagnostics")
def events(pid): return [e for e in list(harness._PORT_FILE_HISTORY) if e.get("game_pid") == pid]
class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.err, self.cap, self.tmp, self.machines = rid, [], {}, None, None, None, []
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok: self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
    def guards(self, checks):  # every guard is judged and recorded; any miss stops the row before its named cells
        for name, ok, detail in checks: self.cell(name, ok, detail, guard=True)
        missed = [c["cell"] for c in self.cells if c["guard"] and not c["pass"]]
        if missed: raise GuardMiss("; ".join(missed))

# ---- U8e-G / -J / -K (no game): the fakes are spec (f) code text ----
class FakeProc:
    def __init__(self):
        self.pid, self.returncode = 0, None
    def poll(self):
        return self.returncode
def fake_gc(name, answers, log, user_dir=None):
    """A real harness.GameClient whose _send is scripted per command (a list answers in order, its last repeats);
    any other command is a fixture error."""
    gc = harness.GameClient(name)
    gc.user_dir, gc.proc, gc.sock = user_dir, FakeProc(), object()
    script = {k: (list(v) if isinstance(v, list) else [v]) for k, v in answers.items()}
    def send(self, obj):
        log.append((self.name, obj.get("cmd"), dict(obj)))
        q = script.get(obj.get("cmd"))
        if q is None:
            raise AssertionError("fixture: %s got %r" % (self.name, obj))
        return json.loads(json.dumps(q.pop(0) if len(q) > 1 else q[0]))
    gc._send = types.MethodType(send, gc)
    return gc
def coop(on, owner=True, dlg=-1):
    return {"ok": True, "onConnect": on, "serverOwner": owner, "coopDialog": dlg, "coopSession": False, "clientName": ""}
def fake_pair(host_cmd, port, coops, user_dir=None):
    return (fake_gc("host", {host_cmd: {"ok": True, "port": port}, "get_coop": coops, "get_state": {
                "ok": True, "states": ["MainMenuState", "LobbyMenu"]}}, LOG, user_dir),
            fake_gc("client", {"join_tcp": {"ok": True}, "join_udp": {"ok": True}, "get_coop": coop(-1, False, 16),
                    "get_state": {"ok": True, "states": ["MainMenuState", "NewBattleState", "CoopState"]}}, LOG))
def g_cell(r, cell, host_cmd, port, coops, key=None, req=JT, user_dir=None, dead=False):
    """Host (unless host_cmd is None), clear the log, join through cmd(): what the client got, the host polls."""
    key, (host, client) = key or "U8E-" + cell, fake_pair(host_cmd or "host_tcp", port, coops, user_dir)
    try:
        if host_cmd:
            host.cmd(dict({"cmd": host_cmd, "port": key, "player": "HostPlayer"},
                          **{"host_menu_host": {"visibility": 2}, "host_udp": {"password": "lan"}}.get(host_cmd, {})))
        if dead:
            host.sock = None  # a host that is not running
        rec = fake_join(r, cell, client, key, req)
    finally:
        forget(key)
    return rec
def fake_join(r, cell, client, key, req=JT):  # what the client got, the host polls before the join / in all
    LOG.clear()
    t0, err = time.monotonic(), None
    try: client.cmd(dict(req, port=key))
    except Exception as e: err = "%s: %s" % (type(e).__name__, e)
    seq = [(n, c) for n, c, _ in LOG]
    first = next((i for i, (n, c) in enumerate(seq) if n == "client" and c.startswith("join")), len(seq))
    rec = {"err": err, "ms": ms(t0), "joined": [o for n, c, o in LOG if n == "client" and c.startswith("join")],
           "pollsBefore": seq[:first].count(("host", "get_coop")), "hostPolls": seq.count(("host", "get_coop"))}
    r.ev.setdefault("join", {})[cell] = dict(rec, err=err and short(err))
    return rec
def once(rec, port, cmd="join_tcp"):
    j = rec["joined"]
    return rec["err"] is None and len(j) == 1 and j[0].get("cmd") == cmd and j[0].get("port") == port
def u8e_g(r):
    wait = g_cell(r, "G-wait", "host_tcp", "55001", [coop(-1), coop(-1), coop(-1), coop(1)])
    owner = g_cell(r, "G-owner", "host_tcp", "55002", [coop(1, False), coop(1, True)])
    r.tmp = tempfile.mkdtemp(prefix="w2u8e_g_")  # the G-timeout host's user dir (its listen_wait_failed report)
    with open(os.path.join(r.tmp, "openxcom.log"), "w", encoding="ascii") as f: f.write("[W2-U8e] fake host log\n")
    pat = os.path.join(diag_dir(), "port-file-%d-*.json" % os.getpid())
    before, had, old = set(glob.glob(pat)), hasattr(harness, "LISTEN_WAIT_S"), getattr(harness, "LISTEN_WAIT_S", None)
    setattr(harness, "LISTEN_WAIT_S", 0.5)
    try: tmo = g_cell(r, "G-timeout", "host_tcp", "55003", [coop(-1)], user_dir=r.tmp)
    finally: setattr(harness, "LISTEN_WAIT_S", old) if had else delattr(harness, "LISTEN_WAIT_S")
    tmo["reports"] = r.ev["join"]["G-timeout"]["reports"] = [safe(lambda: jload(p)["failure"]["operation"])
                                                             for p in sorted(set(glob.glob(pat)) - before)]
    fail3 = g_cell(r, "G-fail3", "host_tcp", "55004", [coop(-3)])
    fail440 = g_cell(r, "G-fail440", "host_tcp", "55005", [coop(-1, False, 440)])
    unreg = g_cell(r, "G-unreg", None, "55000", [coop(1)], key="U8E-NOHOST")
    udp = g_cell(r, "G-udp", "host_udp", "55006", [coop(-1)], req={"cmd": "join_udp", "ip": "127.0.0.1",
                 "localport": "1234", "player": "ClientPlayer", "password": "lan"})
    menu = g_cell(r, "G-menuudp", "host_menu_host", "55007", [coop(-1)])
    dead = g_cell(r, "G-dead", "host_tcp", "55008", [coop(-1)], dead=True)
    r.guards([(c, once(rec, port, cmd) and rec["hostPolls"] == 0 and xtra, rec) for c, rec, port, cmd, xtra in (
        ("G-unreg: an unhosted key joins as given, no host poll", unreg, "U8E-NOHOST", "join_tcp", True),
        ("G-udp: join_udp gets the UDP host's port + localport 0, no host poll", udp, "55006", "join_udp",
         bool(udp["joined"]) and udp["joined"][0].get("localport") == "0"),
        ("G-menuudp: a UDP host window's join_tcp goes out, no host poll", menu, "55007", "join_tcp", True),
        ("G-dead: a host that is not running gets no wait", dead, "55008", "join_tcp", True))])
    early = "join_tcp went out before the host reported its lobby listener open (F8376)"
    r.cell("G-wait: one join to 55001 after 4 host polls (-1, -1, -1, 1)", once(wait, "55001")
           and wait["pollsBefore"] == 4, wait, early)
    r.cell("G-owner: one join to 55002 after 2 host polls (1 without serverOwner, 1 with)", once(owner, "55002")
           and owner["pollsBefore"] == 2, owner, early)
    r.cell("G-timeout: no listener report stops the join (RuntimeError < 3 s, a listen_wait_failed report)",
           tmo["err"] is not None and "never reported its lobby listener open" in tmo["err"] and not tmo["joined"]
           and tmo["ms"] < 3000 and "listen_wait_failed" in tmo["reports"], tmo,
           "a host that never reports its listener did not stop the join")
    for cell, rec, what in (("G-fail3", fail3, "onConnect -3"), ("G-fail440", fail440, "coopDialog 440")):
        r.cell("%s: a host at %s stops the join after 1 poll" % (cell, what), rec["err"] is not None
               and what in rec["err"] and rec["hostPolls"] == 1 and not rec["joined"], rec,
               "a host that reported its lobby listener failed (%s) did not stop the join" % what)
def waited(gc, desc, timeout, pred=lambda: None, interval=0.1):  # wait_for to its deadline: (stdout, the raise text)
    buf, err = io.StringIO(), None
    with contextlib.redirect_stdout(buf):
        try: gc.wait_for(desc, pred, timeout=timeout, interval=interval)
        except TimeoutError as e: err = str(e)
    return buf.getvalue(), err
def joiner_16(text, key=None):  # the [harness-join] lines, and whether one is the client's coopDialog 16
    lines = [safe(lambda: json.loads(x[15:])) for x in text.splitlines() if x.startswith("[harness-join] ")]
    return lines, any(isinstance(x, dict) and x.get("role") == "joiner" and x.get("name") == "client"
                      and x.get("coopDialog") == 16 and (key is None or x.get("key") == key) for x in lines)
def u8e_j(r):
    host, client = fake_pair("host_tcp", "55010", [coop(1)])
    try:
        host.cmd({"cmd": "host_tcp", "port": "U8E-J", "player": "HostPlayer"})
        fake_join(r, "J", client, "U8E-J")
        text, err = waited(host, "host popup", 0.3, interval=0.05)
    finally:
        forget("U8E-J")
    text2, err2 = waited(host, "nothing", 0.2, interval=0.05)
    lines, ok = joiner_16(text)
    r.ev.update(captured=text, lines=lines, raised=err, noneCaptured=text2, noneRaised=err2)
    r.guards([("J-msg: the TimeoutError text is unchanged", err == POPUP_MSG, err),
              ("J-none: no joined pair, no [harness-join] line", err2 is not None and "[harness-join]" not in text2,
               text2)])
    r.cell("J-diag: the timeout prints the joiner's line (role joiner, name client, coopDialog 16)", ok, lines,
           "the host-popup timeout did not show the client's connect result (F8573)")
class FakeProcT:  # pid 0 and no _handle; wait() times out until kill()
    def __init__(self): self.pid, self.returncode, self.calls = 0, None, []
    def poll(self): return self.returncode
    def kill(self): self.calls.append("kill")
    def wait(self, timeout=None):
        self.calls.append("wait")
        if "kill" not in self.calls: raise subprocess.TimeoutExpired("u8e-kfake", timeout)
        self.returncode = harness.KILLED_RETURN_CODE
        return self.returncode
class FakeSock:
    def __init__(self): self.sent, self.closed = [], False
    def sendall(self, b): self.sent.append(b)
    def close(self): self.closed = True
def u8e_k(r):
    gc, r.tmp = harness.GameClient("u8e-kfake"), tempfile.mkdtemp(prefix="w2u8e_k_")
    gc.user_dir, gc.proc, gc.sock = r.tmp, FakeProcT(), FakeSock()
    t0, err = time.monotonic(), None
    try: gc.shutdown()
    except RuntimeError as e: err = str(e)
    evs = [e for e in list(harness._PORT_FILE_HISTORY) if e["monotonic"] >= t0]
    r.ev.update(text=err, calls=gc.proc.calls, ms=ms(t0), ops=[e["operation"] for e in evs], dumpEvents=[
        {k: e.get(k) for k in ("dumpSkipped", "dump", "dumpError")} for e in evs if e["operation"] == "shutdown_dump"])
    r.guards([("K-fake: RuntimeError 'shutdown failed' + 'forced_kill=True', calls wait / kill / wait", err is not None
               and "shutdown failed" in err and "forced_kill=True" in err and gc.proc.calls == ["wait", "kill", "wait"],
               r.ev)])

# ---- U8e-L / -A / -D (live): LateListener, NoQuitSock and dump_threads are spec (f) code text ----
class LateListener:
    """W2-U8e stand-in: a loopback port that is BOUND at once (so no other process can take it) but LISTENS only
    from t_open (delay_s None = never), then relays each accepted connection to the host's real lobby port. From
    the client's side: a host whose listener opened late."""
    def __init__(self, target_port, delay_s):
        self.target, self.accepts, self.opened_at = int(target_port), [], None
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.port = self.srv.getsockname()[1]
        self.t_install = time.monotonic()
        self.t_open = None if delay_s is None else self.t_install + delay_s
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
    @staticmethod
    def _pump(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    def _run(self):
        if self.t_open is None:
            return
        while time.monotonic() < self.t_open:
            if self.stop.wait(0.01):
                return
        self.srv.listen(1)
        self.srv.settimeout(0.2)
        self.opened_at = time.monotonic()
        while not self.stop.is_set():
            try:
                c, _ = self.srv.accept()
            except (socket.timeout, OSError):
                continue
            self.accepts.append(time.monotonic())
            u = socket.create_connection(("127.0.0.1", self.target), timeout=10)
            for a, b in ((c, u), (u, c)):
                threading.Thread(target=self._pump, args=(a, b), daemon=True).start()
    def close(self):
        self.stop.set()
        try:
            self.srv.close()
        except OSError:
            pass
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
def dump_threads(path):
    """MINIDUMP_HEADER (Signature 'MDMP', Version, NumberOfStreams, StreamDirectoryRva); MINIDUMP_DIRECTORY
    entries (StreamType, DataSize, Rva); ThreadListStream = 3 starts with ULONG32 NumberOfThreads."""
    with open(path, "rb") as f:
        b = f.read()
    sig, _ver, nstreams, dir_rva = struct.unpack_from("<4sIII", b, 0)
    if sig != b"MDMP":
        return {"sig": repr(sig)}
    types_ = {}
    for i in range(nstreams):
        st, size, rva = struct.unpack_from("<III", b, dir_rva + 12 * i)
        types_[st] = (size, rva)
    threads = struct.unpack_from("<I", b, types_[3][1])[0] if 3 in types_ else None
    return {"sig": "MDMP", "streams": sorted(types_), "threads": threads, "bytes": len(b)}
def boot(r, *specs):  # (name, label, user dir) each: spawn + connect; a miss fails the row "boot"
    t0 = time.time()
    try:
        for name, label, d in specs:
            r.machines.append(harness.GameClient(name, label, harness.make_user_dir(d)))
            r.machines[-1].spawn(), r.machines[-1].connect()
    except Exception as e: raise BootMiss("%s: %s" % (type(e).__name__, short(str(e), 600)))
    r.ev.setdefault("bootS", []).append(round(time.time() - t0, 1))
    return r.machines[-len(specs):]
def lobby_up(r, key, labels, delay, rewrite):  # skirmish host + client at its browser, the stand-in (per INSTANCE)
    tag = r.rid[-1]
    host, client = boot(r, *[(n, lb, "w2u8e_%s_%s" % (tag.lower(), n)) for n, lb in zip(("host", "client"), labels)])
    raw.skirmish_host(host, key)
    raw.skirmish_client_at_browser(client)
    t0, seen = time.monotonic(), {}  # guard: the host's REAL listener is up within 10 s (both builds)
    while ms(t0) < 10000 and not (seen.get("onConnect") == 1 and seen.get("serverOwner") is True):
        seen = harness.GameClient._send(host, {"cmd": "get_coop"})
        time.sleep(0.05)
    up = r.ev["host"] = {"onConnect": seen.get("onConnect"), "serverOwner": seen.get("serverOwner"), "ms": ms(t0),
                         "realPort": harness._EPHEMERAL_COOP_PORTS.get(key)}
    r.guards([("%s-host: the host's real listener is up (get_coop onConnect 1 + serverOwner within 10 s)" % tag,
               up["onConnect"] == 1 and up["serverOwner"] is True, up)])
    st = LateListener(harness._EPHEMERAL_COOP_PORTS[key], delay)
    harness._EPHEMERAL_COOP_PORTS[key] = str(st.port)
    hosts = getattr(harness, "_COOP_HOSTS", {})
    if key in hosts: hosts[key] = (hosts[key][0], str(st.port), hosts[key][2])  # keep the host and its transport
    rec = r.ev["standIn"] = {"port": st.port, "target": st.target, "delayS": delay, "rewrites": 0}
    def hooked(self, obj):  # with rewrite: the host's get_coop reads onConnect -1 until the stand-in listens
        rep = harness.GameClient._send(self, obj)
        if obj.get("cmd") == "get_coop" and st.opened_at is None:
            rec["rewrites"] += 1
            rep = dict(rep, onConnect=-1)
        return rep
    if rewrite: host._send = types.MethodType(hooked, host)
    return host, client, st
def close_stand_in(r, st, key):
    st.close(), forget(key)
    r.ev["standIn"].update(openedMs=None if st.opened_at is None else int((st.opened_at - st.t_install) * 1000),
                           acceptsMs=[int((a - st.t_install) * 1000) for a in st.accepts])
    return r.ev["standIn"]
def u8e_l(r):
    host, client, st = lobby_up(r, KEY_L, (49453, 49454), 8.0, True)
    try:
        t0 = time.monotonic()
        try: client.ok(dict(JT, port=KEY_L, player=raw.CLIENT_PLAYER))
        finally: del host._send
        join_ms, t1, polls, dlg, prof, at16 = ms(t0), time.monotonic(), 0, None, [False, False], None
        while ms(t1) <= 20000 and at16 is None and not all(prof):  # every 0.25 s: the client's dialog, both Profile
            time.sleep(0.25 if polls else 0)
            polls, dlg = polls + 1, client.cmd({"cmd": "get_coop"}).get("coopDialog")
            prof = [bool(session.has_state(gc, "Profile")) for gc in (host, client)]
            at16 = int((time.monotonic() - st.t_install) * 1000) if dlg == 16 else None
        while st.opened_at is None and time.monotonic() - st.t_install < 10:  # the stand-in's own open (both builds)
            time.sleep(0.05)
    finally:
        rec = close_stand_in(r, st, KEY_L)
    outcome = "16" if at16 is not None else ("Profile" if all(prof) else "neither")
    r.ev.update(joinMs=join_ms, installToJoinMs=int((t0 - st.t_install) * 1000), outcome=outcome, sixteenAtMs=at16,
                clientDialog=dlg, profile=prof, polls=polls)
    r.guards([("L-open: the stand-in listened at 7900-9000 ms, no accept before it", rec["openedMs"] is not None
               and 7900 <= rec["openedMs"] <= 9000 and all(a >= st.opened_at for a in st.accepts), rec)])
    r.cell("L-race: the join waits >= 7500 ms, one relayed connection, both Profile, never coopDialog 16",
           join_ms >= 7500 and all(prof) and at16 is None and len(st.accepts) == 1, {"joinMs": join_ms, "outcome":
           outcome, "acceptsMs": rec["acceptsMs"], "openedMs": rec["openedMs"]}, "the join went out %d ms after the "
           "stand-in started, before its listener opened at 8 s: the client's single connect was refused, coopDialog "
           "%s (F8376 / F8566)" % (join_ms, dlg))
def u8e_a(r):
    host, client, st = lobby_up(r, KEY_A, (49455, 49456), None, False)
    try:
        t0 = time.monotonic()
        client.ok(dict(JT, port=KEY_A, player=raw.CLIENT_PLAYER))
        r.ev["joinMs"], dlg = ms(t0), None
        while ms(t0) <= 20000 and dlg != 16:
            time.sleep(0.25 if dlg is not None else 0)
            dlg = client.cmd({"cmd": "get_coop"}).get("coopDialog")
        r.ev.update(sixteenMs=ms(t0) if dlg == 16 else None, clientDialog=dlg)
        r.guards([("A-16: the refused join ends in the client's coopDialog 16 within 20 s", dlg == 16, r.ev)])
        text, err = waited(host, "host popup", 1, lambda: session.has_state(host, "Profile"))
    finally:
        close_stand_in(r, st, KEY_A)
    lines, ok = joiner_16(text, KEY_A)
    r.ev.update(captured=text, lines=lines, raised=err)
    r.guards([("A-msg: the TimeoutError text is unchanged", err == POPUP_MSG, err)])
    r.cell("A-diag: the timeout prints the client's line (key 47278, role joiner, name client, coopDialog 16)", ok,
           lines, "the host-popup timeout did not show the client's refused join (F8573)")
def u8e_d(r):
    gc, = boot(r, ("hostd", 49457, "w2u8e_d"))
    pid, ns, t0, text = gc.proc.pid, NoQuitSock(gc.sock), time.monotonic(), None
    gc.sock = ns
    try: gc.shutdown()
    except RuntimeError as e: text = str(e)
    wall, evs = round(time.monotonic() - t0, 1), events(pid)
    dumps = [e for e in evs if e["operation"] == "shutdown_dump"]
    dump = dumps[0] if len(dumps) == 1 else {}
    path = dump.get("dump") or ""
    parse = safe(lambda: dump_threads(path)) if path else None
    reports = [(p, j) for p, j in ((p, jload(p)) for p in glob.glob(os.path.join(diag_dir(), "port-file-%d-*.json" % (
        os.getpid())))) if j["failure"].get("operation") == "shutdown_failed" and j["failure"].get("game_pid") == pid]
    in_report = [p for p, j in reports if any(h.get("operation") == "shutdown_dump" and h.get("monotonic")
                                               == dump.get("monotonic") for h in j.get("history", []))]
    r.ev.update(pid=pid, shutdownS=wall, text=text, dropped=ns.dropped, rc=gc.proc.returncode, history=[
        e["operation"] for e in evs], dumpEvent={k: v for k, v in dump.items() if k not in (
        "wall", "tid", "slot", "lock_held", "pid")}, parse=parse, reports=[p for p, _ in reports], inReport=in_report)
    gc2, = boot(r, ("hostd2", 49458, "w2u8e_d2"))
    clean = r.ev["clean"] = {"pid": gc2.proc.pid, "text": None}
    try: gc2.shutdown()
    except RuntimeError as e: clean["text"] = str(e)
    clean.update(rc=gc2.proc.returncode, files=glob.glob(os.path.join(diag_dir(), "hang-hostd2-*")),
                 dumpEvents=[e["operation"] for e in events(clean["pid"])].count("shutdown_dump"))
    r.guards([("D-kill: 'shutdown failed' + 'forced_kill=True', rc KILLED_RETURN_CODE, quit dropped once, >= 15 s",
               text is not None and "shutdown failed" in text and "forced_kill=True" in text
               and gc.proc.returncode == harness.KILLED_RETURN_CODE and ns.dropped == 1 and wall >= 15, r.ev),
              ("D-clean: a normal shutdown: rc 0, no shutdown_dump event, no hang-hostd2-* file", clean["text"] is None
               and clean["rc"] == 0 and not clean["dumpEvents"] and not clean["files"], clean)])
    r.cell("D-dump: a minidump (MDMP, >= 2 threads) in the diagnostics dir, carried by the shutdown_failed report",
           len(dumps) == 1 and not dump.get("dumpError") and os.path.dirname(path) == diag_dir()
           and os.path.basename(path).startswith("hang-hostd-%d-" % pid) and path.endswith(".dmp")
           and isinstance(parse, dict) and parse.get("sig") == "MDMP" and (parse.get("threads") or 0) >= 2
           and len(in_report) == 1, {"dumpEvents": len(dumps), "dump": r.ev["dumpEvent"], "inReport": in_report},
           "the forced kill of a game that never heard quit left no dump of its threads (F8563)")
ROWS = (("U8e-G", u8e_g), ("U8e-J", u8e_j), ("U8e-K", u8e_k), ("U8e-L", u8e_l), ("U8e-A", u8e_a), ("U8e-D", u8e_d))
def capture(r):  # FIXTURE-STOP dump: each machine's get_coop + get_state (unhooked), history, log tail
    cap = {"standIn": r.ev.get("standIn"), "fakeLog": None if r.machines else [x[:2] for x in LOG[-20:]]}
    for gc in r.machines:
        up, pid = gc.proc is not None and gc.proc.poll() is None and gc.sock is not None, gc.proc and gc.proc.pid
        co = safe(lambda: harness.GameClient._send(gc, {"cmd": "get_coop"})) if up else "down"
        st = safe(lambda: harness.GameClient._send(gc, {"cmd": "get_state"})) if up else "down"
        cap[gc.name] = {"pid": pid, "rc": gc.proc and gc.proc.poll(), "history": [e["operation"] for e in events(pid)],
                        "getCoop": {k: co.get(k) for k in VIEW} if isinstance(co, dict) else co,
                        "states": st.get("states", [])[-4:] if isinstance(st, dict) else st,
                        "logTail": tail(os.path.join(gc.user_dir, "openxcom.log"))}
    return cap
def exec_row(rid, fn):
    r, t0 = Row(rid), time.time()
    try: fn(r)
    except GuardMiss as e: r.err = "GUARD %s" % e
    except BootMiss as e: r.err = "boot (%s)" % e
    except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    r.cap = safe(lambda: capture(r)) if r.err else None  # while the machines still run
    live = [gc for gc in r.machines if gc.proc is not None and gc.proc.poll() is None]
    try: harness.shutdown_clients(*live)  # every machine down before the next row
    except Exception as e:
        r.err = (r.err + " | " if r.err else "") + "shutdown: %s" % short(str(e), 600)
        r.cap = r.cap or safe(lambda: capture(r))
    r.ev.update(rcs={gc.name: gc.proc and gc.proc.poll() for gc in r.machines}, wall=round(time.time() - t0, 1))
    if r.tmp and not r.err and all(c["pass"] for c in r.cells): shutil.rmtree(r.tmp, ignore_errors=True)
    elif r.tmp: r.ev["kept"] = r.tmp
    return r
def report(r, results):
    r.ev["cells"] = [[c["cell"], "guard" if c["guard"] else "row", c["pass"]] for c in r.cells]
    print("EVIDENCE %s: %s" % (r.rid, json.dumps(r.ev, default=str)), flush=True)
    if r.err:
        print("CAPTURE %s: %s" % (r.rid, json.dumps(r.cap, default=str)), flush=True)
    fails = ["%s%s: %s" % ("GUARD " if c["guard"] else "", c["cell"], c["msg"]) for c in r.cells if not c["pass"]]
    fails += [r.err] if r.err and not r.err.startswith("GUARD") else []
    results[r.rid] = not fails
    print("PASS %s" % r.rid if not fails else "FAIL %s: %s" % (r.rid, " || ".join(fails)), flush=True)

def main():
    t0, results, saved = time.time(), {}, harness.TEMP_ROOT
    root = harness.TEMP_ROOT = tempfile.mkdtemp(prefix="w2u8e_diag_")  # this run's reports and dumps stay here
    print("EVIDENCE U8e-root: %s" % json.dumps({"diagnosticsRoot": root, "slot": harness.HARNESS_SLOT}), flush=True)
    try:
        for rid, fn in ROWS: report(exec_row(rid, fn), results)
    finally:
        harness.TEMP_ROOT = saved
    passed, failed = [x for x, _ in ROWS if results.get(x)], [x for x, _ in ROWS if not results.get(x)]
    if not failed: shutil.rmtree(root, ignore_errors=True)
    print("\ntest_w2_bringup_capture: %d/%d passed (pass=%s fail=%s) in %.1fs (diagnostics %s)" % (len(passed),
          len(ROWS), passed, failed, time.time() - t0, "removed" if not failed else "kept in " + root), flush=True)
    return 0 if not failed else 2
if __name__ == "__main__":
    sys.exit(main())
