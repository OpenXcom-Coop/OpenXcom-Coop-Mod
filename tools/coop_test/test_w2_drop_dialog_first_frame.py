"""W2-H61 stage S-A (spec rewrite/prompts/w2h61_drop_dialog_first_frame.md (f); TASK 0 rewrite/w2h61-task0/sa/CONSTANTS.md; lead
L-H56G-1, ruling R-H61-0, QH61-1..QH61-4 (a); F18629, F18680-F18696, F18880-F18888): when the second player drops in a co-op campaign,
disconnectTCP()'s host arm pushes the waiting window 62 BEFORE CoopSession::onClientDrop() clears resumeAck and clientInLobby; the 62 reads
its state once in its constructor and then only on a 500 ms gate that every CoopState shares, so for ~0.2-0.3 s it reads "All players
connected" with RESUME and no SAVE & QUIT / ABANDON GAME. A 62 already up and ready keeps RESUME the same way after a drop.
The reading (QH61-2 (a)): a poll thread on the host, started right before each kill, runs get_coop THEN coop_dialog_info every POLL_S. A 62
read is fresh when "to reconnect" is in the title, RESUME is hidden and SAVE & QUIT and ABANDON GAME are shown; any other 62 read is stale. R
counts a read only when its get_coop returned resumeAck false. Needles count from the host log's line count read just before the kill.
  Row K (SEPARATE; key "49203", dirs w2h61_K_*): session.new_campaign; the poll; client.kill(); TRAIL_S. Cells K-seen GUARD, K-first RED,
  K-stale RED, K-late GUARD, K-log GUARD (FREEZE +1, DROP +1).
  Row R (continues K's host): N_CYCLES x a fresh client (w2h61_R<c>_client) join_tcp (KEY, "ClientPlayer") -> its 68 within HOLD_S -> the
  host acks it, its join Profile is dismissed (profile_ok, as test_reconnect_dialog; only the top state thinks) -> the host's 62 ready within
  READY_S; the poll; the kill; TRAIL_S. Cells R-ready GUARD, R-stale RED, R-late GUARD, R-log GUARD (SUPP +1, DROP +1, FREEZE +0 per cycle).
  Row H (SHARED; dirs w2h61_H_*): as K, but the kill right after the host's BEGIN press (a copy of new_campaign's body, CONSTANTS.md KILL_AT:
  after new_campaign returns the gate was 570 ms old). Cells H-seen, H-first RED, H-stale RED, H-late, H-log.
  Row Q (quiet control, SEPARATE; dirs w2h61_Q_*): as K, after QUIET_S with coop_dialog_info.present false at every 0.1 s check (the gate is
  open). Cells Q-seen, Q-first, Q-log (GUARDs: fresh on both builds).
Red (commit R1): exit 2, RED exactly on K-first, K-stale, R-stale, H-first, H-stale. Nothing is clicked on the 62. A precondition miss ends
its row (cells "not reached"); a boot miss fails the row "boot" with ONE CAPTURE line. ONE EVIDENCE line per row, one PASS / FAIL line per
cell, the row verdict; exit 0 only when every cell passes, else 2 (WV-D99 / WV-D100). WV-D95: one foreground run per invocation.
Run: python tools/coop_test/test_w2_drop_dialog_first_frame.py
"""
import json, os, sys, threading, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT, cpu_load, cpu_text  # noqa: E402

KEY = "49203"
POLL_S, SEEN_S, TRAIL_S, LATE_S, HOLD_S, READY_S, QUIET_S, N_CYCLES = 0.02, 10.0, 2.0, 2.0, 120.0, 10.0, 2.0, 3
RC_OK = (0, 3221226505)
READY, WAITING = "All players connected", "to reconnect"
NEEDLES = {"FREEZE": "[coop-session] freeze (lobbyMode=", "DROP": "[coop-session] onClientDrop",
           "SUPP": "[coop] freeze dialog suppressed: a campaign"}

class Stop(Exception):
    """a WAIT timed out or a precondition missed: the row ends here"""

def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}

def pick(r, keys):
    return {k: r.get(k) for k in keys}

def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None

def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in q(gc, {"cmd": "get_state"}).get("states", [])]

def coop(gc):
    return pick(q(gc, {"cmd": "get_coop"}), ("resumeAck", "onConnect", "lobbyMode", "lobbyClosed", "clientName", "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backVisible", "saveQuitVisible", "abandonVisible", "error"))

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}

def wait(desc, pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))

def cpu():
    return cpu_text(cpu_load()["cpu"])

def fresh(r):
    return WAITING in (r.get("title") or "") and r.get("back") is False and r.get("sq") is True and r.get("ab") is True

def short_read(r):
    return [r["t"], r.get("ack"), r.get("code"), r.get("title"), r.get("back"), r.get("sq"), r.get("ab")]

def poll_kill(host, client, booked):
    """the pair poll: a thread on the host started right before client.kill(); get_coop THEN coop_dialog_info every POLL_S, until
    TRAIL_S / LATE_S after the first 62 read (K, H, Q) or after the first read the drop is booked for (R, booked=True); SEEN_S without"""
    trail, t0 = [], [None]

    def run():
        while True:
            try:
                c = host.cmd({"cmd": "get_coop"})
                d = host.cmd({"cmd": "coop_dialog_info"})
            except Exception as e:  # a value: the host is gone
                trail.append({"t": round(time.time() - t0[0], 3), "err": short(e, 200)})
                return
            trail.append({"t": round(time.time() - t0[0], 3), "ack": c.get("resumeAck"), "code": d.get("code"), "title": d.get("title"),
                          "back": d.get("backVisible"), "sq": d.get("saveQuitVisible"), "ab": d.get("abandonVisible")})
            ref = [r for r in trail if r.get("code") == 62 and (r.get("ack") is False or not booked)]
            if (ref and trail[-1]["t"] >= ref[0]["t"] + max(TRAIL_S, LATE_S)) or (not ref and trail[-1]["t"] > SEEN_S):
                return
            time.sleep(POLL_S)

    th = threading.Thread(target=run)
    t0[0] = time.time()
    th.start()
    client.kill()
    killed = round(time.time() - t0[0], 3)
    th.join(SEEN_S + TRAIL_S + 15)
    return trail, killed

def reading(trail, booked):
    """first / stale / late over the 62 reads (R: only the counted ones, resumeAck false)"""
    s62 = [r for r in trail if r.get("code") == 62 and (r.get("ack") is False or not booked)]
    late = [r for r in s62 if r["t"] >= s62[0]["t"] + LATE_S] if s62 else []
    return {"first": s62[0] if s62 else None, "stale": sum(1 for r in s62 if not fresh(r)), "reads": len(s62),
            "late": late[0] if late else None, "trail": [short_read(r) for r in s62[:8]], "errors": [r for r in trail if "err" in r]}

class Row:
    def __init__(self, rid, cells):
        self.rid, self.cells, self.fails, self.done, self.t0, self.n_h, self.host, self.client = rid, cells, [], set(), time.time(), 0, None, None
        self.cr0, self.ev = session._crash_log_snapshot(), {}

    def evidence(self):
        self.printed = True
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)

    def cell(self, cid, kind, label, ok):
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)

    def end(self, results, walls):
        """ONE CAPTURE line when a cell failed, then the row verdict"""
        walls[self.rid] = round(time.time() - self.t0, 1)
        if not getattr(self, "printed", False):
            self.evidence()
        if self.fails and not getattr(self, "captured", False):
            cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc)} for n, gc in (("host", self.host),
                                                                                                         ("client", self.client)) if alive(gc)}
            if alive(self.host):
                cap["host needle deltas"] = counts(self.host, self.n_h)
                cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(self.host) if "[coop]" in ln or "coop-session" in ln][-12:]
            cap["new crash"] = sorted(session._crash_log_snapshot() - self.cr0)
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = (len(self.cells) - len([c for c in self.cells if c in self.fails]), len(self.cells), list(self.fails))
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, x, results, walls):
        print("FAIL %s boot: the boot did not reach its kill point (%s)" % (self.rid, x.err), flush=True)
        self.fails.append("boot")
        self.stop("boot")
        self.captured = True  # the boot printed its ONE CAPTURE line
        self.end(results, walls)

def campaign_to_begin(host, client):
    """KILL_AT (CONSTANTS.md): a copy of session.new_campaign's body (SHARED, tcp; no session.py edit) ending at the host's BEGIN press"""
    host.ok({"cmd": "open_new_game", "mode": "shared"})
    host.wait_for("difficulty", lambda: session.has_state(host, "NewGameState"))
    host.ok({"cmd": "newgame_ok"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": KEY, "player": "HostPlayer"})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
    client.wait_for("client lobby", lambda: session.has_state(client, "LobbyMenu"), timeout=120)
    for gc in (host, client):
        gc.wait_for("join popup", lambda gc=gc: session.has_state(gc, "Profile"))
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("start eligible", lambda: host.cmd({"cmd": "lobby_state"}).get("startEligible") or None)
    session.start_campaign_via_button(host)
    host.wait_for("host base placement", lambda: session.has_state(host, "BuildNewBaseState"))
    if not host.cmd({"cmd": "place_first_base", "lon": session.HOST_LON, "lat": session.HOST_LAT, "name": "HostBase"}).get("ok"):
        host.ok({"cmd": "place_first_base", "lon": LAND_LON, "lat": LAND_LAT, "name": "HostBase"})
    host.wait_for("client world ack", lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None, timeout=120)
    session.press_back_when_shown(host, "host BEGIN", codes=(60, 62))

def boot(rid, mode, quiet):
    """host + client (dirs w2h61_<rid>_*), the campaign up to the kill point; Q: QUIET_S with no CoopState on the host (else x.err)"""
    x = SimpleNamespace(rid=rid, host=None, client=None, err=None, cpu=cpu())
    try:
        x.host = GameClient("host", None, make_user_dir("w2h61_%s_host" % rid))
        x.client = GameClient("client", None, make_user_dir("w2h61_%s_client" % rid))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        if mode == "shared":
            campaign_to_begin(x.host, x.client)
        else:
            session.new_campaign(x.host, x.client, port=KEY)
        if quiet:
            t0, seen = time.time(), []
            while time.time() - t0 < QUIET_S:
                seen.append(dlg(x.host).get("present"))
                time.sleep(0.1)
            x.quiet = "%d checks, present true %d" % (len(seen), sum(1 for v in seen if v is not False))
            if any(v is not False for v in seen):
                raise Stop("Q: coop_dialog_info.present not false at every 0.1 s check for %.0f s (%s)" % (QUIET_S, x.quiet))
    except Exception as e:
        x.err = short(e, 600)
        cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc)} for n, gc in (("host", x.host), ("client", x.client))
               if alive(gc)}
        print("CAPTURE %s boot: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    return x

def row_kill(x, rid, cells, results, walls):
    """K / H / Q: the pair poll, the kill, the cells"""
    r = Row(rid, [rid + "-" + c for c in cells])
    if x.err:
        return r.boot_miss(x, results, walls)
    h, ev = x.host, r.ev
    r.host, r.client = h, x.client
    try:  # KILL_AT: no probe between the kill point and the kill (each costs ~50 ms of the shared gate's 500, CONSTANTS.md)
        r.cr0, r.n_h = session._crash_log_snapshot(), len(log(h))
        trail, killed = poll_kill(h, x.client, False)
        rd = reading(trail, False)
        ev.update({"cpu": x.cpu, "kill returned s": killed, "client rc": x.client.proc.returncode, "first 62 read": rd["first"],
                   "stale reads": "%d of %d" % (rd["stale"], rd["reads"]), "late read": rd["late"], "poll errors": rd["errors"],
                   "trail (first 8 62 reads: t, resumeAck, code, title, back, saveQuit, abandon)": rd["trail"], "needles": counts(h, r.n_h),
                   "host stack after": stack(h), "host get_coop after": coop(h), "new crash": sorted(session._crash_log_snapshot() - r.cr0)})
        if hasattr(x, "quiet"):
            ev["quiet"] = x.quiet
        r.evidence()
        r.cell(rid + "-seen", "GUARD", "a 62 read within %.0f s of the kill" % SEEN_S, rd["first"] is not None and rd["first"]["t"] <= SEEN_S)
        if rd["first"] is None:
            raise Stop("%s-seen: no 62 read" % rid)
        kind = "GUARD" if rid == "Q" else "RED"
        r.cell(rid + "-first", kind, "the first 62 read is fresh (\"%s\", RESUME hidden, SAVE & QUIT and ABANDON GAME shown; red today: \"%s\" + "
               "RESUME, F18629)" % (WAITING, READY) if kind == "RED" else "the first 62 read is fresh (the gate is open: no CoopState for "
               "%.0f s)" % QUIET_S, fresh(rd["first"]))
        if "stale" in cells:
            r.cell(rid + "-stale", "RED", "0 stale reads in the trail (red today: >= 1)", rd["stale"] == 0)
        if "late" in cells:
            r.cell(rid + "-late", "GUARD", "the read at %.1f s after the first 62 read is fresh" % LATE_S, rd["late"] is not None and fresh(rd["late"]))
        n = ev["needles"]
        r.cell(rid + "-log", "GUARD", "FREEZE +1, DROP +1", n["FREEZE"] == 1 and n["DROP"] == 1)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_r(x, results, walls, extra):
    """R: N_CYCLES rejoin-then-kill cycles on K's host"""
    r = Row("R", ["R-ready", "R-stale", "R-late", "R-log"])
    if x.err or not alive(x.host):
        x.err = x.err or "K's host is not running"
        return r.boot_miss(x, results, walls)
    h, ev = x.host, r.ev
    r.host, ev["cpu"], ev["cycles"] = h, cpu(), []
    try:
        for c in range(1, N_CYCLES + 1):
            cy = {"cycle": c}
            ev["cycles"].append(cy)
            cl = GameClient("client", None, make_user_dir("w2h61_R%d_client" % c))
            extra.append(cl)
            r.client = cl
            try:
                cl.spawn(); cl.connect()
                cl.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": "ClientPlayer"})
                cy["68 s"] = wait("the rejoiner's 68", lambda: dlg(cl).get("code") == 68, HOLD_S)
                cy["ack s"] = wait("the host's resumeAck true", lambda: coop(h).get("resumeAck") is True, READY_S)
                if "Profile" in stack(h):
                    cy["profile_ok"] = q(h, {"cmd": "profile_ok"}).get("ok")
                cy["ready s"] = wait("the host's 62 ready", lambda: (lambda d: d.get("code") == 62 and d.get("backVisible") is True
                                                                       and d.get("title") == READY)(dlg(h)), READY_S)
                cy["host dialog ready"], cy["host stack ready"] = dlg(h), stack(h)
            except Exception as e:
                cy["stop"] = short(e, 300)
                r.evidence()
                r.cell("R-ready", "GUARD", "cycle %d: the rejoiner's 68 within %.0f s, the host's 62 ready (\"%s\", RESUME) within %.0f s"
                       % (c, HOLD_S, READY, READY_S), False)
                raise Stop("R-ready: cycle %d: %s" % (c, cy["stop"]))
            r.n_h = len(log(h))
            trail, cy["kill returned s"] = poll_kill(h, cl, True)
            rd = reading(trail, True)
            cy.update({"booked read": rd["first"], "stale counted": "%d of %d" % (rd["stale"], rd["reads"]), "late read": rd["late"],
                       "uncounted 62 reads": sum(1 for t in trail if t.get("code") == 62 and t.get("ack") is not False),
                       "trail (first 8 counted)": rd["trail"], "poll errors": rd["errors"], "needles": counts(h, r.n_h)})
            cy["_stale"], cy["_late"] = rd["stale"], rd["late"] is not None and fresh(rd["late"])
        ev["host stack after"], ev["new crash"] = stack(h), sorted(session._crash_log_snapshot() - r.cr0)
        r.evidence()
        cys = ev["cycles"]
        r.cell("R-ready", "GUARD", "each cycle: the rejoiner's 68, the host's 62 ready (\"%s\", RESUME) before the kill" % READY, True)
        r.cell("R-stale", "RED", "0 stale counted reads (resumeAck false) over the %d cycles (red today: >= 1)" % N_CYCLES,
               sum(cy["_stale"] for cy in cys) == 0)
        r.cell("R-late", "GUARD", "each cycle: fresh at %.1f s after the drop is booked" % LATE_S, all(cy["_late"] for cy in cys))
        r.cell("R-log", "GUARD", "each cycle: SUPP +1, DROP +1, FREEZE +0",
               all((cy["needles"]["SUPP"], cy["needles"]["DROP"], cy["needles"]["FREEZE"]) == (1, 1, 0) for cy in cys))
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def shut(*gcs):
    """every machine of the boot (a killed client was reaped by kill()) -> the shutdown failures"""
    failed = []
    for gc in gcs:
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (os.path.basename(gc.user_dir or ""), gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown" % os.path.basename(gc.user_dir or gc.name))
    return failed

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    tb = time.time()
    x = boot("K", "coop", False)
    walls["K boot"], extra = round(time.time() - tb, 1), []
    try:
        row_kill(x, "K", ["seen", "first", "stale", "late", "log"], results, walls)
        row_r(x, results, walls, extra)
    finally:
        failed += shut(x.client, *extra) + shut(x.host)
    for rid, mode, quiet, cells in (("H", "shared", False, ["seen", "first", "stale", "late", "log"]), ("Q", "coop", True, ["seen", "first", "log"])):
        tb = time.time()
        x = boot(rid, mode, quiet)
        walls[rid + " boot"] = round(time.time() - tb, 1)
        try:
            row_kill(x, rid, cells, results, walls)
        finally:
            failed += shut(x.client, x.host)
    passed, total = sum(v[0] for v in results.values()), sum(v[1] for v in results.values())
    fails = [c for v in results.values() for c in v[2]]
    print("\ntest_w2_drop_dialog_first_frame: %d/%d cells passed (fail=%s%s) walls %s in %.1fs" % (
        passed, total, fails, (" shutdown=%s" % failed) if failed else "", json.dumps(walls), time.time() - t0), flush=True)
    return 2 if fails or failed or total != 17 else 0

if __name__ == "__main__":
    sys.exit(main())
