"""Test harness driver for the OpenXcom coop mod.

Talks to the in-game TestServer (src/CoopMod/TestServer.cpp), which is enabled
by setting the OXC_TEST_PORT environment variable on a game instance. Protocol:
newline-delimited JSON over TCP on 127.0.0.1:<port>.

Typical use: spawn two instances (host + client) with isolated -user folders,
drive both through save-load / host / join / lobby, then assert on soldiers.

Port-file failures preserve a bounded operation history, post-failure metadata
and up to 64 KiB of the game log in TEMP/oxc-coop-port-diagnostics. The report
path is printed; diagnostics do not retry a denied read or change its failure.
"""

import atexit
from collections import deque
import datetime
import json
import errno
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    # kernel32 with use_last_error so a failed CreateFileW below surfaces its
    # own GetLastError - the actual failing call's code, not a later reopen's.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _CreateFileW.restype = wintypes.HANDLE  # c_void_p; avoids c_int truncation
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = (wintypes.HANDLE,)
    _CloseHandle.restype = wintypes.BOOL

    _GENERIC_READ = 0x80000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_SHARE_DELETE = 0x00000004
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x00000080
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def _port_file_opener(path, flags):
        """Read while the publisher's rename handle still holds DELETE access.

        Ordinary Windows open() omits FILE_SHARE_DELETE and can collide with
        that handle after the final name becomes visible. Granting the missing
        share bit removes this race without suppressing genuine access errors.
        """
        # lpSecurityAttributes = NULL -> the returned handle is non-inheritable.
        handle = _CreateFileW(
            path, _GENERIC_READ,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            None, _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None)
        if handle is None or handle == _INVALID_HANDLE_VALUE:
            error = ctypes.WinError(ctypes.get_last_error())
            error.filename = path
            raise error
        owns_handle = True
        try:
            # Ownership transfers to the fd; closing the file object (fd) closes
            # the handle. O_NOINHERIT keeps the CRT fd non-inheritable too.
            fd = msvcrt.open_osfhandle(handle, flags | os.O_NOINHERIT)
            owns_handle = False
            return fd
        finally:
            if owns_handle and not _CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())
else:
    # Non-Windows: open(..., opener=None) is the default open, unchanged.
    _port_file_opener = None

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# OXC_TEST_EXE points the whole suite at a different build - e.g.
# bin/x64/Release-nofix/OpenXcom.exe, to watch a regression test go red against
# a binary without the fix. The exe's own directory supplies the game data, so
# that tree has to be staged (tools/worktree_bootstrap.ps1).
EXE = os.environ.get("OXC_TEST_EXE") or os.path.join(REPO, "bin", "x64", "Release", "OpenXcom.exe")
TEMP_ROOT = os.environ.get("TEMP") or os.environ.get("TMPDIR") or tempfile.gettempdir()
TEST_ROOT = os.path.join(TEMP_ROOT, "oxc-coop-test")

# --- Ephemeral-port model (both socket kinds are OS-assigned) ----------------
# There are NO fixed ports any more. Two socket kinds, both ephemeral:
#
#   1. TestServer control socket. The game is always spawned with
#      OXC_TEST_PORT=0, so it binds an OS-assigned port and writes the actual
#      value to <user_dir>/testserver_port.txt (atomic write+rename). connect()
#      polls that file, then dials the reported port - it never guesses. The
#      integer still passed positionally to GameClient(name, N, dir) is now just
#      a label; it does NOT bind (see GameClient.__init__). A GameClient built
#      with user_dir=None keeps the old fixed-port behaviour so a repro tool can
#      attach to a pre-spawned instance on a known port.
#
#   2. Coop game-to-game sockets (TCP + UDP). The host binds ephemeral and the
#      EXISTING TestServer responses report the actual bound port; cmd() below
#      does this transparently: a host_tcp/host_udp/host_menu_host is rewritten
#      to ask for port "0", and the actual port from the response is stashed
#      under the ORIGINAL port value the test passed (which the paired
#      join_tcp/join_udp reuses as a rendezvous KEY, not a socket). So every
#      caller - session.new_campaign, the module-global PORT constants, the
#      pvp/shared/skirmish fixtures - migrates to ephemeral with no per-test
#      edits: the literal they pass is only an in-process key linking a host to
#      its client. UDP `localport` is forced to "0" too (OS-assigned client bind).
#
# This kills the fixed-port collision/linger class outright (CI 31999655291:
# "test server not reachable on :49900" was a prior scenario's instance still
# holding the port). The lane machinery below keeps only what still names
# shared state: the per-slot machine lock and the s{slot}_ user-dir prefix. No
# port bands, so K is no longer capped by the 65535 ceiling.
HARNESS_SLOT = int(os.environ.get("OXC_HARNESS_SLOT", "0"))

# Coop bring-up commands whose response carries the host's actual (ephemeral)
# bound port, and the join commands that must reuse it. cmd() bridges the two,
# keyed on the (now inert) port literal the test passes to both sides.
_COOP_HOST_CMDS = frozenset(("host_tcp", "host_udp", "host_menu_host"))
_COOP_JOIN_CMDS = frozenset(("join_tcp", "join_udp"))
# {rendezvous_key -> actual ephemeral coop port}. Process-global: a test's host
# and client GameClients share it; run_parallel gives each test its own process,
# so keys never cross runs. Distinct live pairs must use distinct keys (the same
# invariant the old per-port model relied on).
_EPHEMERAL_COOP_PORTS = {}
PORT_FILE_NAME = "testserver_port.txt"
KILLED_RETURN_CODE = 1 if os.name == "nt" else -signal.SIGKILL

# Per-slot harness lock: suites are stateful (shared TEST_ROOT under %TEMP%, one
# game instance per s{slot}_ user dir), so two runs on the SAME slot would
# collide on those user dirs even though ports are now ephemeral. First
# spawn in a process takes its slot's lock; the OS releases it when the process
# exits (including on crash). Slot 0 keeps the historical lock name so it still
# serialises against a non-slotted / old-harness run — e.g. two git worktrees.
_LOCK_PATH = os.path.join(
    TEMP_ROOT,
    "oxc-coop-harness.lock" if HARNESS_SLOT == 0
    else "oxc-coop-harness.slot%d.lock" % HARNESS_SLOT)
_lock_handle = None
_PORT_FILE_HISTORY = deque(maxlen=128)


def _port_file_event(operation, **fields):
    event = dict(fields, operation=operation,
                 wall=datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"),
                 monotonic=time.monotonic(), pid=os.getpid(),
                 tid=threading.get_native_id(), slot=HARNESS_SLOT,
                 lock_held=_lock_handle is not None)
    _PORT_FILE_HISTORY.append(event)
    return event


def _port_file_error(exc):
    return {"type": type(exc).__name__, "message": str(exc),
            "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
            "filename": getattr(exc, "filename", None)}


def _report_port_file_error(operation, exc, user_dir, **fields):
    event = _port_file_event(operation, error=_port_file_error(exc),
                             user_dir=user_dir, **fields)
    payload = {"failure": event, "history": list(_PORT_FILE_HISTORY),
               "test": os.path.abspath(sys.argv[0]), "exe": EXE,
               "lock_path": _LOCK_PATH, "post_failure_metadata": []}
    port_file = os.path.join(user_dir, PORT_FILE_NAME)
    for path in (user_dir, port_file, port_file + ".tmp"):
        observation = {"path": path, "monotonic": time.monotonic()}
        try:
            st = os.stat(path)
            observation.update(size=st.st_size, mode=st.st_mode,
                               mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns,
                               device=st.st_dev, inode=st.st_ino,
                               file_attributes=getattr(st, "st_file_attributes", None))
        except OSError as snapshot_error:
            observation["error"] = _port_file_error(snapshot_error)
        payload["post_failure_metadata"].append(observation)
    try:
        with open(os.path.join(user_dir, "openxcom.log"), "rb") as game_log:
            game_log.seek(0, os.SEEK_END)
            size = game_log.tell()
            game_log.seek(max(0, size - 65536))
            payload["game_log_tail"] = game_log.read(65536).decode("utf-8", errors="replace")
            payload["game_log_tail_truncated"] = size > 65536
    except OSError as log_error:
        payload["game_log_error"] = _port_file_error(log_error)
    # Outside the instance directory: the next make_user_dir() must not erase it.
    diagnostics_dir = os.path.join(TEMP_ROOT, "oxc-coop-port-diagnostics")
    report_path = os.path.join(diagnostics_dir, f"port-file-{os.getpid()}-{time.time_ns()}.json")
    try:
        os.makedirs(diagnostics_dir, exist_ok=True)
        with open(report_path, "x", encoding="utf-8") as report:
            json.dump(payload, report, indent=2)
    except OSError as report_error:
        print("[harness-port-file] diagnostic-write-failed " +
              json.dumps(_port_file_error(report_error)), file=sys.stderr, flush=True)
        print("[harness-port-file] " + json.dumps(payload), file=sys.stderr, flush=True)
    else:
        print("[harness-port-file] " + json.dumps(dict(event, report=report_path)),
              file=sys.stderr, flush=True)


def _acquire_machine_lock(timeout=3600):
    global _lock_handle
    if _lock_handle is not None:
        return
    h = open(_LOCK_PATH, "a")
    deadline = time.time() + timeout
    waited = False
    while True:
        try:
            if os.name == "nt":
                msvcrt.locking(h.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(h.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_handle = h  # held for process lifetime
            if waited:
                print("[harness] slot-%d lock acquired" % HARNESS_SLOT)
            return
        except OSError as exc:
            if os.name != "nt" and exc.errno not in (errno.EACCES, errno.EAGAIN):
                h.close()
                raise
            if time.time() > deadline:
                h.close()
                raise TimeoutError(
                    "another coop harness run holds " + _LOCK_PATH)
            if not waited:
                print("[harness] waiting for slot-%d harness lock "
                      "(another run holds it)..." % HARNESS_SLOT)
                waited = True
            time.sleep(5)

# WV-D64 / SPEC 0b time accounting: when OXC_TIMELOG is set, append one CSV
# row per event to that file (header ts_iso,agent,role,event,detail - the same
# file every builder/orchestrator TL one-liner writes to, see
# rewrite/wave1-timelog.csv in the docs repo). Tagged with OXC_AGENT (default
# "unknown"); role is fixed "harness" so these automatic rows are visually
# distinct from the manual "agent" rows a builder's own TL calls write. NEVER
# raises - a timing-accounting failure must not fail a test.
_TIMELOG_EXIT_CODE = [0]


def _timelog(event, detail=""):
    path = os.environ.get("OXC_TIMELOG")
    if not path:
        return
    # WV-D70: ~690 of the ~790 rows a session writes are the spawn tier and only
    # SPEC 0c's boot analysis needed them; OFF unless OXC_TIMELOG_SPAWNS=1.
    # test_start/test_end keep emitting under OXC_TIMELOG.
    if event in ("spawn", "spawn_end") and not os.environ.get("OXC_TIMELOG_SPAWNS"):
        return
    try:
        agent = os.environ.get("OXC_AGENT", "unknown")
        ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        row = "%s,%s,%s,%s,%s\n" % (
            ts, agent, "harness", event, str(detail).replace(",", ";"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(row)
    except OSError:
        pass


_orig_sys_exit = sys.exit


def _tracking_sys_exit(code=None):
    # sys.exit(None) / sys.exit() means success (0); sys.exit("message")
    # prints the message and the PROCESS exit code is 1, not the string -
    # mirror that so test_end's detail reports the real process exit code.
    if code is None:
        _TIMELOG_EXIT_CODE[0] = 0
    elif isinstance(code, int):
        _TIMELOG_EXIT_CODE[0] = code
    else:
        _TIMELOG_EXIT_CODE[0] = 1
    _orig_sys_exit(code)


sys.exit = _tracking_sys_exit


def _timelog_test_end():
    _timelog("test_end", "%s exit=%s" % (
        os.path.basename(sys.argv[0]), _TIMELOG_EXIT_CODE[0]))


# "at harness import" - this module body runs exactly once per process
# (import caching), the first time any test script imports it.
_timelog("test_start", os.path.basename(sys.argv[0]))
atexit.register(_timelog_test_end)

# A known-good land tile for first-base placement (place_first_base rejects
# water). Shared by the fresh-campaign tests so they need no pre-existing save.
LAND_LON, LAND_LAT = 0.7063353365604198, -0.5070346730015731

# Hermetic options.cfg: pin the stock `xcom1` master (no external mods, no
# reading of the machine's real config) with intro/audio/mouse-capture off and
# a small windowed display. OpenXcom defaults every unspecified key and rescans
# the other stock mods as inactive. Data (UFO/TFTD/standard/common) resolves
# from the exe's own dir, so this runs on any machine with a built OpenXcom.exe.
HERMETIC_OPTIONS = """\
mods:
  - active: true
    id: xcom1
options:
  displayWidth: 640
  displayHeight: 400
  fullscreen: false
  borderless: false
  captureMouse: false
  playIntro: false
  musicVolume: 0
  soundVolume: 0
  uiVolume: 0
"""


class GameClient:
    """One running game instance + its command socket."""

    def __init__(self, name, port=None, user_dir=None):
        self.name = name
        self.user_dir = user_dir
        # Control socket is OS-assigned ephemeral: the game binds port 0 and
        # writes the actual port to <user_dir>/PORT_FILE_NAME, which connect()
        # reads back. The positional `port` is now only a label and does NOT
        # bind - EXCEPT for the attach-to-a-running-instance case (user_dir is
        # None), where there is no file to read so the caller's port is used
        # directly (repro tooling). self.port is the resolved port, filled in by
        # connect().
        self._fixed_port = int(port) if (user_dir is None and port) else None
        self.port = self._fixed_port
        self.proc = None
        self._shutdown_proc = None
        self.sock = None
        self.buf = b""

    @property
    def _port_file(self):
        return os.path.join(self.user_dir, PORT_FILE_NAME) if self.user_dir else None

    def spawn(self, extra_args=()):
        _port_file_event("spawn_requested", user_dir=self.user_dir,
                         previous_game_pid=self.proc.pid if self.proc else None,
                         previous_returncode=self.proc.poll() if self.proc else None)
        _acquire_machine_lock()
        _port_file_event("spawn_lock_acquired", user_dir=self.user_dir)
        _timelog("spawn", "%s port=%s" % (self.name, self.port))
        env = os.environ.copy()
        # Ephemeral by default (OXC_TEST_PORT=0 -> the game picks a free control
        # port and reports it via PORT_FILE_NAME). Remove any stale port file
        # first so connect() cannot read a value from a previous spawn. A
        # fixed-port GameClient (user_dir=None) keeps its explicit port.
        if self._fixed_port is None:
            env["OXC_TEST_PORT"] = "0"
            _port_file_event("stale_file_check", path=self._port_file)
            if self._port_file and os.path.exists(self._port_file):
                removal = _port_file_event("stale_file_remove_begin", path=self._port_file)
                try:
                    os.remove(self._port_file)
                except OSError as exc:
                    _report_port_file_error("stale_file_remove_failed", exc, self.user_dir)
                else:
                    event = _port_file_event("stale_file_removed", path=self._port_file,
                                             started=removal["wall"],
                                             started_monotonic=removal["monotonic"])
                    print("[harness-port-file] " + json.dumps(event), flush=True)
            else:
                _port_file_event("stale_file_not_observed", path=self._port_file)
        else:
            env["OXC_TEST_PORT"] = str(self._fixed_port)
        # HEADLESS BY DEFAULT (owner standing rule). Every boot_check, repro_*,
        # test_rw_* and SP-smoke run funnels through this one spawn(), and it
        # used to inherit whatever the caller happened to export - which nothing
        # did, so every harness instance opened a real window and STOLE FOCUS
        # from whoever was using the machine. A fixture re-roll boots two
        # instances per attempt and a proof bar does ten-plus attempts, so this
        # is the whole blast radius.
        #
        # Windowed is now an explicit OPT-IN, using the same predicate
        # run_parallel.py:300-303 already established, so the repo has one
        # convention. The owner-smoke launcher sets OXC_HARNESS_WINDOWED=1 when
        # the owner actually wants to watch; no test ever should.
        if not env.get("OXC_HARNESS_WINDOWED"):
            env["SDL_VIDEODRIVER"] = "dummy"
            env["SDL_AUDIODRIVER"] = "dummy"
        # Kept for the opt-in windowed path: harmless under the dummy driver,
        # and it is what the owner-smoke path wants when it is used.
        env["SDL_VIDEO_WINDOW_POS"] = "0,40" if "host" in self.name else "660,40"
        exe_dir = os.path.dirname(EXE) or "."
        if os.name == "nt":
            # Preserve the existing Windows launch path.
            launch_exe = EXE
        else:
            # POSIX resolves this relative to exe_dir after changing cwd.
            launch_exe = os.path.join(".", os.path.basename(EXE))
        args = [launch_exe, "-user", self.user_dir] + list(extra_args)
        popen_kwargs = {}
        if os.name == "nt":
            # Best-effort: ask Windows to start the window without activating it.
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
            popen_kwargs["startupinfo"] = si
        self.proc = subprocess.Popen(
            args, env=env, cwd=exe_dir, **popen_kwargs)
        _port_file_event("spawned", user_dir=self.user_dir, game_pid=self.proc.pid)

    def _resolve_port(self, deadline):
        """The control port to dial: the fixed one, or the ephemeral port the
        game reported by writing PORT_FILE_NAME. Polls the file within the same
        boot budget (no port-guessing)."""
        if self._fixed_port is not None:
            return self._fixed_port
        attempt = 0
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                exc = RuntimeError(f"{self.name}: game exited early rc={self.proc.returncode}")
                _report_port_file_error("port_wait_game_exited", exc, self.user_dir,
                                        game_pid=self.proc.pid, game_returncode=self.proc.returncode)
                raise exc
            attempt += 1
            stage = "open"
            _port_file_event("port_read_begin", path=self._port_file, attempt=attempt,
                             game_pid=self.proc.pid if self.proc else None)
            try:
                with open(self._port_file, encoding="utf-8",
                          opener=_port_file_opener) as f:
                    stage = "read"
                    txt = f.read().strip()
                    stage = "close"
                stage = "parse"
                if txt:
                    p = int(txt)
                    if p > 0:
                        _port_file_event("port_resolved", path=self._port_file,
                                         attempt=attempt, port=p)
                        return p
                _port_file_event("port_not_ready", path=self._port_file, attempt=attempt,
                                 value=txt[:80])
            except (FileNotFoundError, ValueError) as exc:
                _port_file_event("port_not_ready", path=self._port_file, attempt=attempt,
                                 stage=stage, error=_port_file_error(exc))
            except OSError as exc:
                _report_port_file_error("port_read_failed", exc, self.user_dir,
                                        stage=stage, attempt=attempt,
                                        game_pid=self.proc.pid if self.proc else None,
                                        game_returncode=self.proc.poll() if self.proc else None)
                raise
            time.sleep(0.2)
        exc = TimeoutError(
            f"{self.name}: game never reported its test-server port "
            f"(no {self._port_file})")
        _report_port_file_error("port_wait_timeout", exc, self.user_dir, attempts=attempt,
                                game_pid=self.proc.pid if self.proc else None)
        raise exc

    def connect(self, timeout=60):
        deadline = time.time() + timeout
        # Boot budget is now spent purely on the game coming up and reporting its
        # port, then on the socket accepting - never on guessing a port.
        self.port = self._resolve_port(deadline)
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(f"{self.name}: game exited early rc={self.proc.returncode}")
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                self.sock.settimeout(30)
                if self.cmd({"cmd": "ping"}).get("pong"):
                    print(f"[{self.name}] connected on :{self.port}")
                    # Wire-order lever matrix hook (boundary epoch-reset ruling
                    # 2026-08-26): OXC_WIRE_ORDER=1 engages the wire_order_state
                    # lever on EVERY instance the harness boots, so the whole
                    # targeted suite runs lever-on unmodified (the Phase 5/6
                    # both-lever matrix). Unset/0 = lever-off default, untouched.
                    if os.environ.get("OXC_WIRE_ORDER", "").lower() in ("1", "true"):
                        self.cmd({"cmd": "parallel_state", "wire_order_state": True})
                        got = self.cmd({"cmd": "parallel_state"}).get("wireOrderState")
                        if got is not True:
                            raise RuntimeError(
                                f"{self.name}: OXC_WIRE_ORDER=1 but wire_order_state "
                                f"lever did not engage (readback={got!r})")
                        print(f"[{self.name}] wire_order_state lever ON (OXC_WIRE_ORDER)")
                    return
            except (ConnectionRefusedError, socket.timeout, OSError):
                self.sock = None
                time.sleep(0.1)
        raise TimeoutError(f"{self.name}: test server not reachable on :{self.port}")

    def _send(self, obj):
        self.sock.sendall((json.dumps(obj) + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError(f"{self.name}: socket closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def cmd(self, obj):
        # Ephemeral coop ports (see the module header). A coop HOST command is
        # rewritten to ask for an OS-assigned port ("0"); the actual port from
        # the response is stashed under the ORIGINAL literal so the paired JOIN
        # command (given the same literal by the test) dials the real one. The
        # literal is thus an in-process rendezvous key, never a bound port. A
        # COPY is rewritten so a caller reusing the dict in a retry loop is
        # unaffected.
        name = obj.get("cmd")
        if name in _COOP_HOST_CMDS and str(obj.get("port", "")) != "":
            key = str(obj["port"])
            obj = dict(obj)
            obj["port"] = "0"
            if "localport" in obj:
                obj["localport"] = "0"
            resp = self._send(obj)
            actual = resp.get("port")
            if actual:
                _EPHEMERAL_COOP_PORTS[key] = str(actual)
            return resp
        if name in _COOP_JOIN_CMDS and str(obj.get("port", "")) != "":
            key = str(obj["port"])
            obj = dict(obj)
            obj["port"] = _EPHEMERAL_COOP_PORTS.get(key, obj["port"])
            if "localport" in obj:
                obj["localport"] = "0"
            return self._send(obj)
        return self._send(obj)

    def ok(self, obj):
        r = self.cmd(obj)
        if not r.get("ok"):
            raise RuntimeError(f"{self.name}: {obj.get('cmd')} failed: {r.get('error')}")
        return r

    # SPEC 0c / WV-D82: measured 2026-09-06, 1.0 s rounding cost ~2.2 s per battle
    # setup; 0.1 s is the measured value, not a guess.
    def wait_for(self, desc, predicate, timeout=90, interval=0.1):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(interval)
        raise TimeoutError(f"{self.name}: timed out waiting for {desc} (last={last!r})")

    def kill(self):
        """Deliberately drop this test peer, validating and reaping the killed process."""
        if not self.proc or self.proc.poll() is not None:
            raise RuntimeError(f"{self.name}: cannot kill a game that is not running")
        _port_file_event("intentional_kill", user_dir=self.user_dir, game_pid=self.proc.pid)
        self.proc.kill()
        self.proc.wait(timeout=15)
        self.shutdown(expected_returncodes=(KILLED_RETURN_CODE,))

    def shutdown(self, *, expected_returncodes=(0,)):
        """Quit and reap the game; abnormal exits require an explicit expectation."""
        if self.proc is not None and self.proc is self._shutdown_proc:
            return
        shutdown = _port_file_event("shutdown_requested", user_dir=self.user_dir,
                                    game_pid=self.proc.pid if self.proc else None,
                                    expected_returncodes=expected_returncodes)
        forced_kill = False
        try:
            try:
                if self.sock and (not self.proc or self.proc.poll() is None):
                    self.sock.sendall((json.dumps({"cmd": "quit"}) + "\n").encode())
            except OSError as exc:
                _port_file_event("shutdown_quit_failed", user_dir=self.user_dir,
                                 error=_port_file_error(exc))
            if self.proc:
                try:
                    self.proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    forced_kill = True
                    _port_file_event("shutdown_wait_timeout", user_dir=self.user_dir,
                                     game_pid=self.proc.pid)
                    self.proc.kill()
                    self.proc.wait(timeout=15)
        finally:
            if self.sock:
                self.sock.close()
                self.sock = None
                self.buf = b""
            returncode = self.proc.poll() if self.proc else None
            event = _port_file_event("shutdown_complete", user_dir=self.user_dir,
                                     game_pid=self.proc.pid if self.proc else None,
                                     game_returncode=returncode,
                                     forced_kill=forced_kill, started=shutdown["wall"],
                                     started_monotonic=shutdown["monotonic"])
            print("[harness-port-file] " + json.dumps(event), flush=True)
            _timelog("spawn_end", "%s port=%s" % (self.name, self.port))
        if self.proc and (forced_kill or returncode not in expected_returncodes):
            exc = RuntimeError(
                f"{self.name}: shutdown failed: rc={returncode}, "
                f"expected={expected_returncodes}, forced_kill={forced_kill}")
            _report_port_file_error("shutdown_failed", exc, self.user_dir,
                                    game_pid=self.proc.pid, game_returncode=returncode,
                                    forced_kill=forced_kill)
            raise exc
        self._shutdown_proc = self.proc


def shutdown_clients(*clients):
    """Clean up every supplied peer before propagating any shutdown failures."""
    errors = []
    for client in clients:
        if client is None:
            continue
        try:
            client.shutdown()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(exc)
    if errors:
        raise RuntimeError("peer shutdown failed: " + "; ".join(map(str, errors))) from errors[0]


def make_user_dir(name, saves=(), mods=(), options=None):
    """Hermetic, isolated user folder: a freshly written options.cfg pinning
    the stock `xcom1` master (see HERMETIC_OPTIONS) with no external mods and
    no dependence on the machine's real config. `saves` are copied into the
    master's save subfolder (xcom1/).

    `mods` are paths to mod folders to install AND activate for this run. They are
    copied into <userdir>/mods/ - the user mod location; note that the shipped
    standard/ directory is a protected allowlist and silently rejects anything
    else ("Invalid standard mod '<name>', skipping."). Both machines in a co-op
    pair must get the SAME mods or their rulesets diverge.

    `options` is a dict of extra options.cfg keys spliced into HERMETIC_OPTIONS'
    `options:` block, e.g. {"battleXcomSpeed": 1}. Unlike the set_option command
    (which flips a value mid-test) these are in force from the instance's very
    first frame, and they are PER INSTANCE - a test can start the host slow and
    the client fast. Booleans are written as YAML true/false."""
    # Lane prefix: two runs on different slots must never share a user dir, since
    # this rmtree's `d` on entry (accidental concurrency would silently destroy
    # the other lane's run). Slot 0 is prefixed s0_ too, so every live instance
    # is tagged by lane in %TEMP%\oxc-coop-test — the marker the parallel runner
    # uses to identify its own processes and never touch a foreign session's.
    name = "s%d_%s" % (HARNESS_SLOT, name)
    d = os.path.join(TEST_ROOT, name)
    _port_file_event("user_dir_prepare", user_dir=d)
    if os.path.exists(d):
        removal = _port_file_event("user_dir_remove_begin", user_dir=d)
        try:
            shutil.rmtree(d)
        except OSError as exc:
            _report_port_file_error("user_dir_remove_failed", exc, d)
            raise
        event = _port_file_event("user_dir_removed", user_dir=d, started=removal["wall"],
                                 started_monotonic=removal["monotonic"])
        print("[harness-port-file] " + json.dumps(event), flush=True)
    try:
        os.makedirs(os.path.join(d, "xcom1"))
    except OSError as exc:
        _report_port_file_error("user_dir_create_failed", exc, d)
        raise
    _port_file_event("user_dir_created", user_dir=d)
    # OXC_TEST_EXTRA_MOD (mod-loaded regression, GAP-10): a path - or an os.pathsep-
    # joined list of paths - to mod folder(s) appended to EVERY instance's mod set,
    # so any existing test can be run with an extra mod active without editing it.
    # The env is process-wide, so both machines in a pair get the same mods (their
    # rulesets must match). Used to prove the promoted battle-hash buckets do not
    # false-alarm when a battle script is loaded.
    env_mod = os.environ.get("OXC_TEST_EXTRA_MOD")
    if env_mod:
        mods = list(mods) + [p for p in env_mod.split(os.pathsep) if p]
    extra = ""
    for src in mods:
        mod_id = os.path.basename(os.path.normpath(src))
        shutil.copytree(src, os.path.join(d, "mods", mod_id))
        extra += "  - active: true\n    id: " + mod_id + "\n"
    opts = HERMETIC_OPTIONS
    if extra:
        opts = opts.replace("options:\n", extra + "options:\n", 1)
    all_options = dict(options) if options else {}
    # W1-P12 REGRESSION acceptance (SPEC 7 (g)): "REGRESSION twice - once ON,
    # once OFF". None of the 18 regression tests know anything about
    # coopGhostStepper, so this is the mechanism for the OFF pass without
    # editing any of them: a PYTHON-side (not OXC_*, and not a new game-process
    # env var - WAVE1-RUNBOOK.md SS4b's own "OXC_* is not the mechanism" note)
    # opt-in that forces the option off in EVERY generated options.cfg, for
    # this harness process only. A caller's own explicit `options` dict entry
    # (none of the 18 pass one today) still wins.
    if os.environ.get("COOP_GHOST_STEPPER_OFF") and "coopGhostStepper" not in all_options:
        all_options["coopGhostStepper"] = False
    if all_options:
        extra_opts = ""
        for key, value in all_options.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            extra_opts += "  %s: %s\n" % (key, value)
        opts = opts.replace("options:\n", "options:\n" + extra_opts, 1)
    with open(os.path.join(d, "options.cfg"), "w", encoding="utf-8") as f:
        f.write(opts)
    for save in saves:
        shutil.copy(save, os.path.join(d, "xcom1"))
    _port_file_event("user_dir_ready", user_dir=d)
    return d


def find_soldier(soldier_lists, name):
    for base in soldier_lists["bases"]:
        for s in base["soldiers"]:
            if name in s["name"]:
                return base, s
    return None, None
