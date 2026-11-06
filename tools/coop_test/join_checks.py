"""Shared steps of the lobby join-check tests (test_join_checks_tcp.py, test_join_checks_udp.py).

A join between two games that differ in build version or mod list must be refused before the joiner reaches the
lobby, on every join path, with the incompatible-mods screen (ModCheckMenu) and never the password prompt.

Machines: a host loading Coop_JoinCheck_A_Test 1.0 then Coop_JoinCheck_B_Test 1.0, and three clients:
  same    the host's mods                                        (build / empty-string / match cells)
  modver  Coop_JoinCheck_A2_Test: mod A at metadata version 2.0  (mod_version cells)
  order   B loaded before A                                      (load_order cells)
The build-version and empty-string cells use set_reported_identity (a test-server command) to replace what one game
reports about itself.

Every cell starts with both machines on a fresh main menu (disconnect_to_menu), hosts a new lobby, joins once and
watches the joiner's screen stack until it settles:
  refused   ModCheckMenu on top, and LobbyMenu, Profile and PasswordCheckMenu never seen, and the session down;
            the screen names what differs (expected_screen)
  joined    LobbyMenu or the join popup (Profile) seen
  password  PasswordCheckMenu on top (a refused cell must never show it)
"""

import json
import os
import time

import session
from harness import GameClient, make_user_dir, CRASH_DIR

HOST_TERM_RC = 0xC0000409      # a known, accepted host exit after hosting a rendezvous room (test_udp_rejoin.py)
TERM_LINE = "std::terminate called (no active exception)."
CRASH_HEAD = ("==== Crash/Log", "Time:", "Version:", "Compiled:", "Module:", "ImageBase:", "Mods:")

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(HERE, "mods")
MOD_A1 = os.path.join(MODS, "Coop_JoinCheck_A_Test")
MOD_A2 = os.path.join(MODS, "Coop_JoinCheck_A2_Test")
MOD_B1 = os.path.join(MODS, "Coop_JoinCheck_B_Test")

OTHER_BUILD = "9.9.9.9"          # a build version no real game reports
SETTLE_S = 1.0                   # after a refusal: the session must be down and no lobby may follow
JOIN_WATCH_S = 20.0              # a TCP or UDP join settles well inside this on an idle machine

ENABLED = "This mod is enabled."


def expected_screen(kind, real_build, build_shown=True):
    """What the incompatible-mods screen shows for a refused cell: {row name: status} and the line under the title.
    kind is the cell's one difference; real_build is the build version both games really report. Every joiner loads
    the host's mods by name, so no row is missing or extra. build_shown False: the screen was opened from the server
    browser's row, which carries no build version (the list only shows rooms on the joiner's own build)."""
    rows = {"xcom1 (UFO Defense)": ENABLED, "Coop_JoinCheck_A_Test": ENABLED, "Coop_JoinCheck_B_Test": ENABLED}
    line = ""
    if kind == "empty_mods":
        rows = {}
    elif kind == "mod_version":
        rows["Coop_JoinCheck_A_Test"] = "Different version (host 1.0)."
    elif kind == "load_order":
        rows["Coop_JoinCheck_A_Test"] = rows["Coop_JoinCheck_B_Test"] = "Different load order."
    elif kind == "build" and build_shown:
        line = "Host build %s, your build %s." % (real_build, OTHER_BUILD)
    elif kind == "empty_build" and build_shown:
        line = "Host build unknown, your build %s." % real_build
    return rows, line


def machines(tag):
    """The four games of a join-check test (not yet spawned)."""
    host = GameClient("host", None, make_user_dir("%s_host" % tag, mods=(MOD_A1, MOD_B1)))
    same = GameClient("same", None, make_user_dir("%s_same" % tag, mods=(MOD_A1, MOD_B1)))
    modver = GameClient("modver", None, make_user_dir("%s_modver" % tag, mods=(MOD_A2, MOD_B1)))
    order = GameClient("order", None, make_user_dir("%s_order" % tag, mods=(MOD_B1, MOD_A1)))
    return host, same, modver, order


def shutdown(host, clients, rendezvous_host=False):
    """Every client exits 0. The host exits 0, or, when it hosted a rendezvous room, 0xC0000409 with exactly one
    crash log holding only TERM_LINE (the exit test_udp_rejoin.py accepts). Returns the failure list."""
    fails = []
    crash_files = lambda: set(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else set()  # noqa: E731
    for gc in clients:
        if gc.proc is None:
            continue
        try:
            gc.shutdown()
        except Exception as e:
            fails.append("%s shutdown: %s" % (gc.name, e))
    if host.proc is not None:
        before = crash_files()
        try:
            host.shutdown(expected_returncodes=(0, HOST_TERM_RC) if rendezvous_host else (0,))
        except Exception as e:
            fails.append("host shutdown: %s" % e)
        rc, new = host.proc.returncode, sorted(crash_files() - before)
        logs = [n for n in new if n.endswith(".log")]
        body = [ln.strip() for n in logs for ln in open(os.path.join(CRASH_DIR, n), "r", errors="replace").read()
                .splitlines() if ln.strip() and not ln.startswith(CRASH_HEAD)]
        evidence("host_exit", {"rc": rc, "crashLogs": logs, "crashText": body})
        if rc == HOST_TERM_RC and (len(logs) != 1 or body != [TERM_LINE]):
            fails.append("host rc 0xC0000409 with crash text %s in %s (accepted only with %r)" % (body, logs, TERM_LINE))
    for f in fails:
        print("FAIL teardown: %s" % f, flush=True)
    return fails


def short(states):
    return [s.rsplit("::", 1)[-1] for s in states]


def stack(gc):
    return short(session.states(gc))


def evidence(name, obj):
    print("EVIDENCE %s: %s" % (name, json.dumps(obj, sort_keys=True, default=str)), flush=True)


def identity(gc, **kw):
    """set_reported_identity; returns what the game now reports (version, mods)."""
    r = gc.ok(dict({"cmd": "set_reported_identity"}, **kw))
    return {"version": r.get("version"), "mods": r.get("mods")}


def to_menu(*gcs):
    """Both machines back on a fresh main menu with no session and their real build and mods."""
    for gc in gcs:
        gc.ok({"cmd": "disconnect_to_menu"})
    for gc in gcs:
        gc.wait_for("%s main menu" % gc.name,
                    lambda gc=gc: (stack(gc)[-1:] == ["MainMenuState"]
                                   and not gc.cmd({"cmd": "get_state"}).get("mainMenuInitPending")
                                   and gc.cmd({"cmd": "get_coop"}).get("coopSession") is False) or None,
                    timeout=30)
        identity(gc, clear=True)


def watch(gc, timeout=JOIN_WATCH_S):
    """Poll the joiner's stack until the join settles. Returns (outcome, every state seen, last stack)."""
    seen, last, end = set(), [], time.time() + timeout
    while time.time() < end:
        last = stack(gc)
        seen.update(last)
        if "LobbyMenu" in last or "Profile" in last:
            return "joined", seen, last
        if last[-1:] == ["ModCheckMenu"]:
            return "refused", seen, last
        if last[-1:] == ["PasswordCheckMenu"]:
            return "password", seen, last
        time.sleep(0.02)
    return "timeout", seen, last


def settle_refused(gc, seen):
    """After a refusal: SETTLE_S of watching in which no lobby appears; then the session must be down."""
    end = time.time() + SETTLE_S
    while time.time() < end:
        seen.update(stack(gc))
        time.sleep(0.02)
    c = gc.cmd({"cmd": "get_coop"})
    return {k: c.get(k) for k in ("onConnect", "coopSession", "udpActive", "rendezvousActive")}


def judge(name, want, outcome, seen, last, gc, extra=None, screen=None):
    """One cell's verdict line. want = "refused" or "joined"; screen = expected_screen(...) for a refused cell.
    Returns the failure list."""
    info = gc.cmd({"cmd": "mod_check_info"})
    coop = settle_refused(gc, seen) if outcome == "refused" else None
    rec = {"want": want, "outcome": outcome, "seen": sorted(seen), "last": last,
           "modCheck": {k: info.get(k) for k in ("present", "top", "title", "buildLine", "modHash", "rows")},
           "coop": coop}
    if extra:
        rec.update(extra)
    evidence(name, rec)
    f = []
    if want == "refused":
        if outcome != "refused":
            f.append("join was not refused: outcome %s, stack %s" % (outcome, last))
        for s in ("LobbyMenu", "Profile", "PasswordCheckMenu"):
            if s in seen:
                f.append("%s shown" % s)
        if coop and (coop.get("coopSession") or coop.get("onConnect") == 1):
            f.append("session still up after the refusal: %s" % coop)
        # the screen names what differs: each host mod once with its status, and the build line
        want_rows, want_line = screen
        rows = [(r.get("name"), r.get("status")) for r in (info.get("rows") or [])]
        if len(rows) != len(want_rows) or dict(rows) != want_rows:
            f.append("screen rows %s (want %s)" % (rows, sorted(want_rows.items())))
        if (info.get("buildLine") or "") != want_line:
            f.append("screen build line %r (want %r)" % (info.get("buildLine"), want_line))
    elif outcome != "joined":
        f.append("matching games did not join: outcome %s, stack %s" % (outcome, last))
    print("%s %s%s" % ("PASS" if not f else "FAIL", name, "" if not f else ": " + "; ".join(f)), flush=True)
    return f
