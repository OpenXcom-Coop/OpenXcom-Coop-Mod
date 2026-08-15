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

# --- K-slot parallel harness ------------------------------------------------
# OXC_HARNESS_SLOT=k opens an independent, non-colliding harness lane so K test
# processes can run at once (tools/coop_test/run_parallel.py drives them). A
# lane shifts every TCP port it binds - the TestServer control ports (this
# GameClient's own `port`) AND the coop game-to-game ports carried in
# host_tcp/join_tcp/host_udp/join_udp - by slot*PORT_BLOCK, keys its machine
# lock per slot, and prefixes its user dirs with s{slot}_. Slot 0 is the legacy
# lane: it uses the ORIGINAL lock name and unshifted ports, so a non-slotted
# caller and an old (pre-slot) harness checked out in another worktree still
# mutually exclude on the same lock file. PORT_BLOCK=4000 exceeds the measured
# ~3900-wide base-port span (45999..49901 across the whole suite), so adjacent
# lanes' port bands are disjoint (lane s spans base+s*4000): lane 1 starts at
# 49999 above lane 0's 49901 top, and lane 3 tops out at 61901. A 5th lane
# would clear the 65535 ceiling, so the safe maximum is K=4 (also the
# run_parallel default). See run_parallel.py for the assignment/pin model.
HARNESS_SLOT = int(os.environ.get("OXC_HARNESS_SLOT", "0"))
PORT_BLOCK = 4000
# Commands whose `port` (and, for UDP, `localport`) name the coop game-to-game
# socket rather than the TestServer control socket; GameClient.cmd shifts these
# by the lane offset transparently, so every caller - the classic 47900 default,
# the module-global PORT reassigners, session.new_campaign - lands in-lane with
# no per-test edits. This is the COMPLETE set of port-reading commands in
# TestServer.cpp (host_tcp/host_udp/join_tcp/join_udp + host_menu_host, the
# NEW BATTLE > COOP skirmish-host path); a host_menu_host with no port (the
# UDP-public variant) is left untouched by the `port in obj` guard below.
_PORT_SHIFT_CMDS = frozenset(("host_tcp", "join_tcp", "host_udp", "join_udp",
                              "host_menu_host"))

# Per-slot harness lock: suites are stateful (fixed TCP ports per test, shared
# TEST_ROOT under %TEMP%), so two runs on the SAME slot would collide. First
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

    def __init__(self, name, port, user_dir):
        self.name = name
        # Lane offset (0 for the legacy slot). Applied here to the TestServer
        # control port and, in cmd(), to the coop game-to-game port.
        self._port_shift = HARNESS_SLOT * PORT_BLOCK
        self.port = int(port) + self._port_shift
        self.user_dir = user_dir
        self.proc = None
        self.sock = None
        self.buf = b""

    def spawn(self, extra_args=()):
        _acquire_machine_lock()
        env = os.environ.copy()
        env["OXC_TEST_PORT"] = str(self.port)
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

    def connect(self, timeout=60):
        deadline = time.time() + timeout
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

    def cmd(self, obj):
        # Lane offset for the coop game-to-game port. Rewrites a COPY so a
        # caller that reuses the same dict (a retry loop) is not double-shifted.
        # Accepts int or str port values and preserves the type on the wire.
        if self._port_shift and obj.get("cmd") in _PORT_SHIFT_CMDS:
            obj = dict(obj)
            for key in ("port", "localport"):
                if key in obj:
                    v = obj[key]
                    obj[key] = (str(int(v) + self._port_shift)
                                if isinstance(v, str)
                                else int(v) + self._port_shift)
        self.sock.sendall((json.dumps(obj) + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError(f"{self.name}: socket closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

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
