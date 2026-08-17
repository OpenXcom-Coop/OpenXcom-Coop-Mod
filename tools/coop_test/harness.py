"""Test harness driver for the OpenXcom coop mod.

Talks to the in-game TestServer (src/CoopMod/TestServer.cpp), which is enabled
by setting the OXC_TEST_PORT environment variable on a game instance. Protocol:
newline-delimited JSON over TCP on 127.0.0.1:<port>.

Typical use: spawn two instances (host + client) with isolated -user folders,
drive both through save-load / host / join / lobby, then assert on soldiers.
"""

import json
import errno
import os
import shutil
import socket
import subprocess
import tempfile
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl

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
        self.sock = None
        self.buf = b""

    @property
    def _port_file(self):
        return os.path.join(self.user_dir, PORT_FILE_NAME) if self.user_dir else None

    def spawn(self, extra_args=()):
        _acquire_machine_lock()
        env = os.environ.copy()
        # Ephemeral by default (OXC_TEST_PORT=0 -> the game picks a free control
        # port and reports it via PORT_FILE_NAME). Remove any stale port file
        # first so connect() cannot read a value from a previous spawn. A
        # fixed-port GameClient (user_dir=None) keeps its explicit port.
        if self._fixed_port is None:
            env["OXC_TEST_PORT"] = "0"
            if self._port_file and os.path.exists(self._port_file):
                try:
                    os.remove(self._port_file)
                except OSError:
                    pass
        else:
            env["OXC_TEST_PORT"] = str(self._fixed_port)
        # Headless under the parallel runner (any lane sets OXC_HARNESS_SLOT) or
        # on demand (OXC_HARNESS_HEADLESS): no on-screen window, so no vsync cap,
        # window-focus fights or audio-device contention between K concurrent
        # game processes. OXC_HARNESS_WINDOWED=1 forces the window back for
        # interactive debugging even under the runner; a caller that already
        # exported an SDL driver wins (setdefault). A plain single-test dev run
        # (no slot, no headless flag) keeps its window, unchanged.
        if ((os.environ.get("OXC_HARNESS_SLOT") is not None
             or os.environ.get("OXC_HARNESS_HEADLESS"))
                and not os.environ.get("OXC_HARNESS_WINDOWED")):
            env.setdefault("SDL_VIDEODRIVER", "dummy")
            env.setdefault("SDL_AUDIODRIVER", "dummy")
        # tuck the window into a corner (host left, client right of it)
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

    def _resolve_port(self, deadline):
        """The control port to dial: the fixed one, or the ephemeral port the
        game reported by writing PORT_FILE_NAME. Polls the file within the same
        boot budget (no port-guessing)."""
        if self._fixed_port is not None:
            return self._fixed_port
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(f"{self.name}: game exited early rc={self.proc.returncode}")
            try:
                with open(self._port_file, encoding="utf-8") as f:
                    txt = f.read().strip()
                if txt:
                    p = int(txt)
                    if p > 0:
                        return p
            except (FileNotFoundError, ValueError):
                pass
            time.sleep(0.2)
        raise TimeoutError(
            f"{self.name}: game never reported its test-server port "
            f"(no {self._port_file})")

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
                    return
            except (ConnectionRefusedError, socket.timeout, OSError):
                self.sock = None
                time.sleep(1)
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

    def wait_for(self, desc, predicate, timeout=90, interval=1.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(interval)
        raise TimeoutError(f"{self.name}: timed out waiting for {desc} (last={last!r})")

    def shutdown(self):
        try:
            if self.sock:
                self.sock.sendall((json.dumps({"cmd": "quit"}) + "\n").encode())
        except OSError:
            pass
        if self.proc:
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()


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
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "xcom1"))
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
    if options:
        extra_opts = ""
        for key, value in options.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            extra_opts += "  %s: %s\n" % (key, value)
        opts = opts.replace("options:\n", "options:\n" + extra_opts, 1)
    with open(os.path.join(d, "options.cfg"), "w", encoding="utf-8") as f:
        f.write(opts)
    for save in saves:
        shutil.copy(save, os.path.join(d, "xcom1"))
    return d


def find_soldier(soldier_lists, name):
    for base in soldier_lists["bases"]:
        for s in base["soldiers"]:
            if name in s["name"]:
                return base, s
    return None, None
