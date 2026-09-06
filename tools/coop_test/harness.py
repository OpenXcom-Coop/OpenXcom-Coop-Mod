"""Test harness driver for the OpenXcom coop mod.

Talks to the in-game TestServer (src/CoopMod/TestServer.cpp), which is enabled
by setting the OXC_TEST_PORT environment variable on a game instance. Protocol:
newline-delimited JSON over TCP on 127.0.0.1:<port>.

Typical use: spawn two instances (host + client) with isolated -user folders,
drive both through save-load / host / join / lobby, then assert on soldiers.
"""

import atexit
import datetime
import json
import errno
import os
import shutil
import socket
import subprocess
import sys
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

# Machine-wide harness lock: suites are stateful (fixed TCP ports per test,
# shared TEST_ROOT under %TEMP%), so concurrent runs — e.g. from two git
# worktrees — would collide. First spawn in a process takes the lock; the OS
# releases it when the process exits (including on crash).
_LOCK_PATH = os.path.join(TEMP_ROOT, "oxc-coop-harness.lock")
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
                print("[harness] machine lock acquired")
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
                print("[harness] waiting for machine-wide harness lock "
                      "(another suite is running)...")
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

    def __init__(self, name, port, user_dir):
        self.name = name
        self.port = port
        self.user_dir = user_dir
        self.proc = None
        self.sock = None
        self.buf = b""

    def spawn(self, extra_args=()):
        _acquire_machine_lock()
        _timelog("spawn", "%s port=%s" % (self.name, self.port))
        env = os.environ.copy()
        env["OXC_TEST_PORT"] = str(self.port)
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
        _timelog("spawn_end", "%s port=%s" % (self.name, self.port))


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
    d = os.path.join(TEST_ROOT, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "xcom1"))
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
    return d


def find_soldier(soldier_lists, name):
    for base in soldier_lists["bases"]:
        for s in base["soldiers"]:
            if name in s["name"]:
                return base, s
    return None, None
