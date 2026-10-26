"""W2-H54 S-A - test_w2_client_disconnect_crash.py: the second player's Disconnect on a co-op wait window (F17875, R-H54-0; docs
rewrite/prompts/w2h54_client_disconnect_crash.md (f); TASK 0 rewrite/w2h54-task0/sa/CONSTANTS.md). CoopState::previous runs
disconnectTCP(); popState();. On a client that holds a campaign world, disconnectTCP has already replaced the whole stack with
GoToMainMenuState (issue #82), the second pop empties it, and Game::run reads the empty stack (Game.cpp :444, exit 3, a crash log).
Rows, one fresh SEPARATE session.new_campaign boot pair each (key "49178", dirs w2h54_<row>_host / _client):
  R-A the host's save_game_ui auto_geoscape -> the client's 53 "Saving..."; the host suspended at the client's first sight of 53.
      A-pre (GUARD), A-alive / A-nocrash / A-menu (RED), A-host (GUARD: the host's 62 on top after the resume).
  R-B the host suspended FIRST, then the client's visit_coop_base -> its 50 "Synchronizing bases...".
      B-pre (GUARD), B-alive / B-nocrash / B-menu (RED), B-host (GUARD).
  R-C the control, LAST: the client suspended FIRST, then the host's visit_coop_base -> the host's own 50.
      C-pre, C-host (the host keeps its world on [GeoscapeState]), C-client (the client's 21 after the resume): all GUARD.
QH54-1 (a): the held peer is suspended by this test (NtSuspendProcess / NtResumeProcess on its own pid, copied from
rewrite/cr75-cap/cr75.py) - a slow link; a suspended game is never sent a command and is resumed in a finally before any
shutdown. Every press is a REAL click (click_widget {match: "disconnect"}) once list_widgets reads the button visible true,
hidden false on a top CoopState of the row's code; never coop_dialog_back (it presses during the popup, L-H54-3).
RED (commit R1): A-alive, A-nocrash, A-menu, B-alive, B-nocrash, B-menu FAIL, the other 7 cells PASS. GREEN (E1): all 13 PASS.
One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; a precondition miss ends its row (cells "not
reached"); a boot miss fails the row "boot" with ONE CAPTURE line. WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path,
every row runs after a failure; exit 0 only when every cell passes, else 2. Run: python tools/coop_test/<this file>"""

import ctypes
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, cpu_load, cpu_text  # noqa: E402
import session  # noqa: E402

KEY = "49178"
# CONSTANTS.md (TASK 0 boots a, b, c): sight <= 1.23 s, shown <= 3.06 s, red exit <= 4.31 s after the click, green menu 0.10 s.
POLL_S, SEEN_S, SHOWN_S, OUTCOME_S, PEER_S, STABLE_S, BOOT_S = 0.005, 10.0, 20.0, 15.0, 20.0, 2.0, 30.0
CELLS = {"A": ("A-pre", "A-alive", "A-nocrash", "A-menu", "A-host"),
         "B": ("B-pre", "B-alive", "B-nocrash", "B-menu", "B-host"),
         "C": ("C-pre", "C-host", "C-client")}
TITLE = {53: "Saving", 50: "Synchronizing bases"}  # the title animates its dots ("Saving." / ".." / "...", CoopState.cpp)

_K32, _NT = ctypes.windll.kernel32, ctypes.windll.ntdll
_K32.OpenProcess.restype = ctypes.c_void_p


def _nt(gc, fn):  # this test's own game, by pid (copied from cr75.py); 0x0800 = PROCESS_SUSPEND_RESUME
    h = _K32.OpenProcess(0x0800, False, gc.proc.pid)
    rc = fn(ctypes.c_void_p(h))
    _K32.CloseHandle(ctypes.c_void_p(h))
    return rc


def suspend(gc): return _nt(gc, _NT.NtSuspendProcess)
def resume(gc): return _nt(gc, _NT.NtResumeProcess)
def unreachable(e): return "unreachable: %s: %s" % (type(e).__name__, str(e)[:120])
def now(t0): return round(time.time() - t0, 3)


def short(x, n=700):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."


def probe(f, fallback):
    try:
        return f()
    except Exception as e:  # noqa: BLE001
        return fallback(unreachable(e))


def stk(gc):
    if gc.proc is not None and gc.proc.poll() is not None:
        return "<exited %s>" % gc.proc.poll()
    return probe(lambda: session.states_stripped(gc), lambda u: [u])


def info(gc):
    return probe(lambda: {k: v for k, v in gc.cmd({"cmd": "coop_dialog_info"}).items()
                          if k in ("present", "code", "title", "backVisible")}, lambda u: {"error": u})


def has_save(gc): return probe(lambda: gc.cmd({"cmd": "world_state"}).get("has_save"), lambda u: u)


def cpu():
    c = cpu_load()
    return {"cpu": cpu_text(c["cpu"], 0), "foreign": ",".join(c["wardogs"])}


def disc(gc):
    """(top state, the Disconnect TextButton {visible, hidden} or None) from one list_widgets"""
    r = gc.cmd({"cmd": "list_widgets"})
    st = (r.get("state") or "").replace("class OpenXcom::", "")
    w = next((w for w in r.get("widgets", []) if "TextButton" in (w.get("type") or "")
              and (w.get("text") or "").strip().lower() == "disconnect"), None)
    return st, (None if w is None else {"visible": w.get("visible"), "hidden": w.get("hidden")})


def sight(gc, code, t0, ev):
    """poll coop_dialog_info every POLL_S (one RPC per poll) until present and code == code, within SEEN_S"""
    end = time.time() + SEEN_S
    while time.time() < end:
        d = gc.cmd({"cmd": "coop_dialog_info"})
        if d.get("present") and d.get("code") == code:
            ev["sight"] = now(t0)
            ev["dlg"] = {gc.name: {k: d.get(k) for k in ("code", "title", "backVisible")}}
            return True
        time.sleep(POLL_S)
    ev["sight"] = "code %s not seen in %.0f s: %s" % (code, SEEN_S, short(info(gc), 200))
    return False


def shown(gc, code, t0, ev):
    """poll until a top CoopState of `code` shows its Disconnect TextButton visible true, hidden false, within SHOWN_S"""
    trail, end = [], time.time() + SHOWN_S
    ev["trail"] = trail
    while time.time() < end:
        st, w = disc(gc)
        d = gc.cmd({"cmd": "coop_dialog_info"})
        k = [st, d.get("code"), None if w is None else w["visible"], None if w is None else w["hidden"]]
        if not trail or trail[-1][1:] != k:
            trail.append([now(t0)] + k)
        if st != "CoopState" or d.get("code") != code:
            ev["shown"] = "closed before shown at %s" % now(t0)
            return None
        if w is not None and w["visible"] is True and w["hidden"] is False:
            ev["shown"] = now(t0)
            return d.get("title") or ""
        time.sleep(POLL_S)
    ev["shown"] = "Disconnect not shown in %.0f s" % SHOWN_S
    return None


def outcome(gc, t0, ev, want):
    """poll every 0.1 s within OUTCOME_S until the process exits or its stack == want (MainMenuState: and has_save false);
    a probe exception reads "unreachable". Returns True when `want` was reached."""
    end, last = time.time() + OUTCOME_S, None
    while time.time() < end:
        if gc.proc.poll() is not None:
            ev["outcome"] = {"t": now(t0), "exit": gc.proc.poll()}
            return False
        s = stk(gc)
        hs = has_save(gc) if s == want else None
        last = [s, hs]
        if s == want and (want != ["MainMenuState"] or hs is False):
            ev["outcome"] = {"t": now(t0), "stack": s, "has_save": hs}
            return True
        time.sleep(0.1)
    ev["outcome"] = {"miss": "neither an exit nor %s in %.0f s" % (want, OUTCOME_S), "last": last}
    return False


def peer(gc, code, t0, ev):
    """after its resume, within PEER_S: the process alive and its top state a CoopState with coop_dialog_info.code == code"""
    end, last = time.time() + PEER_S, None
    while time.time() < end:
        if gc.proc.poll() is not None:
            ev["peer"] = {"t": now(t0), "exit": gc.proc.poll()}
            return False
        s, d = stk(gc), info(gc)
        last = {"stack": s, "dlg": d}
        if s[-1:] == ["CoopState"] and d.get("code") == code:
            ev["peer"] = dict(last, t=now(t0))
            return True
        time.sleep(0.1)
    ev["peer"] = dict(last or {}, miss="no top CoopState %s in %.0f s" % (code, PEER_S))
    return False


def settle(host, client, ev):
    """both tops GeoscapeState, both stacks unchanged STABLE_S, within BOOT_S"""
    t0, last, since = time.time(), None, time.time()
    while time.time() - t0 < BOOT_S:
        cur = (tuple(stk(host)), tuple(stk(client)))
        if cur != last:
            last, since = cur, time.time()
        if cur[0][-1:] == ("GeoscapeState",) and cur[1][-1:] == ("GeoscapeState",) and time.time() - since >= STABLE_S:
            ev["settle"] = now(t0)
            return True
        time.sleep(0.1)
    return False


def capture(host, client):  # a boot miss: both stacks, coop_dialog_info, get_coop
    return {gc.name: {"stack": stk(gc), "dlg": info(gc), "get_coop": probe(lambda gc=gc: gc.cmd({"cmd": "get_coop"}), lambda u: u)}
            for gc in (host, client)}


def first_frame(p):
    with open(p, encoding="utf-8", errors="replace") as fh:
        return next((ln.strip() for ln in fh if ln.strip().startswith("#0 ")), None)


def crash_lines(paths):  # each new crash_*.log and its #0 line
    return {os.path.basename(p): probe(lambda p=p: first_frame(p), lambda u: u) for p in sorted(paths)}


def press(clicker, other, code, rid, t0, ev, cells, ok):
    """shown -> one REAL click -> the row's pre cell (a GUARD: a miss ends the row)"""
    title = shown(clicker, code, t0, ev) if ok else None
    ev["stackBeforeClick"] = {clicker.name: stk(clicker), other.name: ev["before"][other.name]}  # a held game is never probed
    click = clicker.cmd({"cmd": "click_widget", "match": "disconnect"}) if title is not None else {}
    ev["click"] = {"t": now(t0), "ok": click.get("ok"), "text": click.get("text")} if click else "not sent"
    pre = (title is not None and title.startswith(TITLE[code]) and (ev.get("suspend") or {}).get("rc") == 0
           and click.get("ok") is True and click.get("text") == "Disconnect")
    cells[rid + "-pre"] = (pre, dict({k: ev.get(k) for k in ("trigger", "sight", "suspend", "shown", "click")}, title=title))
    return pre


def finish(clicker, other, rid, t0, ev, cells, held, crash0):
    """outcome -> resume the held peer -> peer -> the crash diff -> the row's cells"""
    reached = outcome(clicker, t0, ev, ["GeoscapeState"] if rid == "C" else ["MainMenuState"])
    alive = clicker.proc.poll() is None
    ev["afterOutcome"] = {clicker.name: stk(clicker)}
    hs = has_save(clicker) if rid == "C" and alive else None
    ev["resume"] = {"t": now(t0), "rc": resume(other)}
    held.remove(other)
    peer_ok = peer(other, 21 if rid == "C" else 62, t0, ev)
    time.sleep(1.0)  # the crash handler's files
    new = session._crash_log_snapshot() - crash0
    ev["newCrash"] = crash_lines(new)
    ev["exit"] = {clicker.name: clicker.proc.poll(), other.name: other.proc.poll()}
    if rid == "C":
        cells["C-host"] = (alive and reached and hs is True and not new, {"outcome": ev["outcome"], "has_save": hs, "new": ev["newCrash"]})
        cells["C-client"] = (peer_ok, ev["peer"])
        return
    cells[rid + "-alive"] = (alive, {"outcome": ev["outcome"], "exit": clicker.proc.poll()})
    cells[rid + "-nocrash"] = (not new, ev["newCrash"])
    cells[rid + "-menu"] = (reached, ev["outcome"])
    cells[rid + "-host"] = (peer_ok, ev["peer"])


def hold_first(gc, ev, held):
    """R-B / R-C: suspend the peer BEFORE the trigger (its 50 cannot close without the held reply); returns t0"""
    ts, rc = time.time(), suspend(gc)
    held.append(gc)
    t0 = time.time()
    ev["suspend"] = {"rc": rc, "t": round(ts - t0, 3)}
    return t0


def row_a(host, client, ev, cells, held, crash0):
    """the host's save -> the client's 53 "Saving..."; the host suspended at the client's first sight of 53 (QH54-2 (a))"""
    t0 = time.time()
    ev["trigger"] = host.cmd({"cmd": "save_game_ui", "type": "auto_geoscape"})
    ok = ev["trigger"].get("ok") is True and sight(client, 53, t0, ev)
    if ok:
        ev["suspend"] = {"rc": suspend(host), "t": now(t0)}
        held.append(host)
    if press(client, host, 53, "A", t0, ev, cells, ok):
        finish(client, host, "A", t0, ev, cells, held, crash0)


def row_b(host, client, ev, cells, held, crash0):
    """the host held FIRST, then the client opens the host's base -> the client's 50 "Synchronizing bases...\""""
    t0 = hold_first(host, ev, held)
    ev["trigger"] = client.cmd({"cmd": "visit_coop_base", "base": ""})
    ok = ev["trigger"].get("ok") is True and sight(client, 50, t0, ev)
    if press(client, host, 50, "B", t0, ev, cells, ok):
        finish(client, host, "B", t0, ev, cells, held, crash0)


def row_c(host, client, ev, cells, held, crash0):
    """the control: the client held FIRST, then the host opens the client's base -> the host's own 50"""
    t0 = hold_first(client, ev, held)
    ev["trigger"] = host.cmd({"cmd": "visit_coop_base", "base": ""})
    ok = ev["trigger"].get("ok") is True and sight(host, 50, t0, ev)
    if press(host, client, 50, "C", t0, ev, cells, ok):
        finish(host, client, "C", t0, ev, cells, held, crash0)


def run_row(rid, body):
    """one fresh SEPARATE boot pair; settle; the row body; every held game resumed, then both shut down"""
    cells, ev, w0, held, boot_capture = {}, {"cpu": cpu()}, time.time(), [], None
    host = GameClient("host", None, make_user_dir("w2h54_%s_host" % rid.lower()))
    client = GameClient("client", None, make_user_dir("w2h54_%s_client" % rid.lower()))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        try:
            session.new_campaign(host, client, port=KEY)
            booted = settle(host, client, ev)
        except Exception as e:  # noqa: BLE001
            booted, ev["bootError"] = False, unreachable(e)
        if not booted:
            boot_capture = capture(host, client)
            return cells, ev, boot_capture
        ev["before"] = {"host": stk(host), "client": stk(client)}
        body(host, client, ev, cells, held, session._crash_log_snapshot())
    except Exception as e:  # noqa: BLE001
        ev["error"] = unreachable(e)
    finally:
        for gc in list(held):
            ev.setdefault("resumeFinally", {})[gc.name] = resume(gc)
        for gc, exp in ((client, (0, 3, 3221226505)), (host, (0, 3221226505))):  # a red client already exited 3
            try:
                if gc.proc is not None:
                    gc.shutdown(expected_returncodes=exp)
            except Exception as e:  # noqa: BLE001
                ev.setdefault("shutdown", {})[gc.name] = str(e)[:200]
        ev["rc"] = {gc.name: gc.proc.poll() if gc.proc is not None else None for gc in (host, client)}
        ev["wall"] = round(time.time() - w0, 1)
    return cells, ev, boot_capture


def report(rid, cells, ev, boot_capture):
    print("EVIDENCE R-%s: %s" % (rid, short(ev, 4000)), flush=True)
    if boot_capture is not None:
        print("FAIL R-%s boot: both tops not GeoscapeState for %.0f s within %.0f s" % (rid, STABLE_S, BOOT_S), flush=True)
        print("CAPTURE R-%s: %s" % (rid, short(boot_capture, 3000)), flush=True)
    passed = []
    for name in CELLS[rid]:
        ok, detail = cells.get(name, (False, "not reached"))
        print(("PASS %s" % name) if ok else ("FAIL %s: %s" % (name, short(detail))), flush=True)
        passed += [name] if ok else []
    print("ROW R-%s: %s (%d/%d cells, wall %s s)" % (rid, "PASS" if len(passed) == len(CELLS[rid]) else "FAIL", len(passed),
                                                    len(CELLS[rid]), ev.get("wall")), flush=True)
    return passed


def main():
    t0, passed, walls = time.time(), [], {}
    for rid, body in (("A", row_a), ("B", row_b), ("C", row_c)):
        cells, ev, boot_capture = run_row(rid, body)
        passed += report(rid, cells, ev, boot_capture)
        walls["R-" + rid] = ev.get("wall")
    failed = [c for rid in ("A", "B", "C") for c in CELLS[rid] if c not in passed]
    print("\ntest_w2_client_disconnect_crash: %d/13 cells passed (fail=%s) walls %s in %.1fs"
          % (13 - len(failed), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
