"""test_drop_dialog_first_frame.py: when the second player drops in a co-op campaign, disconnectTCP()'s host arm pushes
the waiting window 62 BEFORE CoopSession::onClientDrop() clears resumeAck and clientInLobby. A 62 that read its state
once in its constructor and then only on the 500 ms gate every CoopState shares would read "All players connected"
with RESUME and no SAVE & QUIT / ABANDON GAME for ~0.2-0.3 s, and a 62 already up and ready would keep RESUME the same
way after a drop. These rows check that the host's 62 reads fresh from its first read on.
The reading: a poll thread on the host, started right before each kill, runs get_coop THEN coop_dialog_info every
POLL_S. A 62 read is fresh when "to reconnect" is in the title, RESUME is hidden and SAVE & QUIT and ABANDON GAME are
shown; any other 62 read is stale. rejoin_drop counts a read only when its get_coop returned resumeAck false. Needles
count from the host log's line count read just before the kill.
  separate_drop (SEPARATE; key "49203", dirs drop_dialog_separate_drop_*): session.new_campaign; the poll;
  client.kill(); TRAIL_S. Cells separate_drop-seen GUARD, separate_drop-first FIX, separate_drop-stale FIX,
  separate_drop-late GUARD, separate_drop-log GUARD (FREEZE +1, DROP +1).
  rejoin_drop (continues separate_drop's host): N_CYCLES x a fresh client (drop_dialog_rejoin<c>_client) join_tcp
  (KEY, "ClientPlayer") -> its 68 within HOLD_S -> the host acks it, its join Profile is dismissed (profile_ok, as
  test_reconnect_dialog; only the top state thinks) -> the host's 62 ready within READY_S; the poll; the kill;
  TRAIL_S. Cells rejoin_drop-ready GUARD, rejoin_drop-stale FIX, rejoin_drop-late GUARD, rejoin_drop-log GUARD (SUPP
  +1, DROP +1, FREEZE +0 per cycle).
  shared_begin_drop (SHARED; dirs drop_dialog_shared_begin_drop_*): as separate_drop, but the kill right after the
  host's BEGIN press (a copy of new_campaign's body: once new_campaign returns, the gate is already ~570 ms old).
  Cells shared_begin_drop-seen, -first FIX, -stale FIX, -late, -log.
  quiet_drop (quiet control, SEPARATE; dirs drop_dialog_quiet_drop_*): as separate_drop, after QUIET_S with
  coop_dialog_info.present false at every 0.1 s check (the gate is open). Cells quiet_drop-seen, -first, -log
  (GUARDs: fresh on any build).
A build whose 62 shows stale reads after a drop exits 2 and fails exactly separate_drop-first, separate_drop-stale,
rejoin_drop-stale, shared_begin_drop-first and shared_begin_drop-stale. Nothing is clicked on the 62. A precondition
miss ends its row (cells "not reached"); a boot miss fails the row "boot" with ONE CAPTURE line. ONE EVIDENCE line per
row, one PASS / FAIL line per cell, the row verdict; exit 0 only when every cell passes, else 2. One foreground run per
invocation.
Run: python tools/coop_test/test_drop_dialog_first_frame.py
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
    """the pair poll: a thread on the host started right before client.kill(); get_coop THEN coop_dialog_info every
    POLL_S, until TRAIL_S / LATE_S after the first 62 read (separate_drop, shared_begin_drop, quiet_drop) or after the
    first read the drop is booked for (rejoin_drop, booked=True); SEEN_S without"""
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
    """first / stale / late over the 62 reads (rejoin_drop: only the counted ones, resumeAck false)"""
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
    """the kill point: a copy of session.new_campaign's body (SHARED, tcp) ending at the host's BEGIN press"""
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
    """host + client (dirs drop_dialog_<rid>_*), the campaign up to the kill point; quiet_drop: QUIET_S with no
    CoopState on the host (else x.err)"""
    x = SimpleNamespace(rid=rid, host=None, client=None, err=None, cpu=cpu())
    try:
        x.host = GameClient("host", None, make_user_dir("drop_dialog_%s_host" % rid))
        x.client = GameClient("client", None, make_user_dir("drop_dialog_%s_client" % rid))
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
                raise Stop("quiet_drop: coop_dialog_info.present not false at every 0.1 s check for %.0f s (%s)"
                           % (QUIET_S, x.quiet))
    except Exception as e:
        x.err = short(e, 600)
        cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc)} for n, gc in (("host", x.host), ("client", x.client))
               if alive(gc)}
        print("CAPTURE %s boot: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
    return x

def row_kill(x, rid, cells, results, walls):
    """separate_drop / shared_begin_drop / quiet_drop: the pair poll, the kill, the cells"""
    r = Row(rid, [rid + "-" + c for c in cells])
    if x.err:
        return r.boot_miss(x, results, walls)
    h, ev = x.host, r.ev
    r.host, r.client = h, x.client
    try:  # no probe between the kill point and the kill (each costs ~50 ms of the shared gate's 500)
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
        kind = "GUARD" if rid == "quiet_drop" else "FIX"
        r.cell(rid + "-first", kind, "the first 62 read is fresh (\"%s\", RESUME hidden, SAVE & QUIT and ABANDON GAME "
               "shown; a stale read shows \"%s\" + RESUME)" % (WAITING, READY) if kind == "FIX"
               else "the first 62 read is fresh (the gate is open: no CoopState for %.0f s)" % QUIET_S,
               fresh(rd["first"]))
        if "stale" in cells:
            r.cell(rid + "-stale", "FIX", "0 stale reads in the trail", rd["stale"] == 0)
        if "late" in cells:
            r.cell(rid + "-late", "GUARD", "the read at %.1f s after the first 62 read is fresh" % LATE_S, rd["late"] is not None and fresh(rd["late"]))
        n = ev["needles"]
        r.cell(rid + "-log", "GUARD", "FREEZE +1, DROP +1", n["FREEZE"] == 1 and n["DROP"] == 1)
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_rejoin_drop(x, results, walls, extra):
    """rejoin_drop: N_CYCLES rejoin-then-kill cycles on separate_drop's host"""
    r = Row("rejoin_drop", ["rejoin_drop-ready", "rejoin_drop-stale", "rejoin_drop-late", "rejoin_drop-log"])
    if x.err or not alive(x.host):
        x.err = x.err or "separate_drop's host is not running"
        return r.boot_miss(x, results, walls)
    h, ev = x.host, r.ev
    r.host, ev["cpu"], ev["cycles"] = h, cpu(), []
    try:
        for c in range(1, N_CYCLES + 1):
            cy = {"cycle": c}
            ev["cycles"].append(cy)
            cl = GameClient("client", None, make_user_dir("drop_dialog_rejoin%d_client" % c))
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
                r.cell("rejoin_drop-ready", "GUARD", "cycle %d: the rejoiner's 68 within %.0f s, the host's 62 ready "
                       "(\"%s\", RESUME) within %.0f s"
                       % (c, HOLD_S, READY, READY_S), False)
                raise Stop("rejoin_drop-ready: cycle %d: %s" % (c, cy["stop"]))
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
        r.cell("rejoin_drop-ready", "GUARD", "each cycle: the rejoiner's 68, the host's 62 ready (\"%s\", RESUME) "
               "before the kill" % READY, True)
        r.cell("rejoin_drop-stale", "FIX", "0 stale counted reads (resumeAck false) over the %d cycles" % N_CYCLES,
               sum(cy["_stale"] for cy in cys) == 0)
        r.cell("rejoin_drop-late", "GUARD", "each cycle: fresh at %.1f s after the drop is booked" % LATE_S,
               all(cy["_late"] for cy in cys))
        r.cell("rejoin_drop-log", "GUARD", "each cycle: SUPP +1, DROP +1, FREEZE +0",
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
    x = boot("separate_drop", "coop", False)
    walls["separate_drop boot"], extra = round(time.time() - tb, 1), []
    try:
        row_kill(x, "separate_drop", ["seen", "first", "stale", "late", "log"], results, walls)
        row_rejoin_drop(x, results, walls, extra)
    finally:
        failed += shut(x.client, *extra) + shut(x.host)
    for rid, mode, quiet, cells in (("shared_begin_drop", "shared", False, ["seen", "first", "stale", "late", "log"]),
                                    ("quiet_drop", "coop", True, ["seen", "first", "log"])):
        tb = time.time()
        x = boot(rid, mode, quiet)
        walls[rid + " boot"] = round(time.time() - tb, 1)
        try:
            row_kill(x, rid, cells, results, walls)
        finally:
            failed += shut(x.client, x.host)
    passed, total = sum(v[0] for v in results.values()), sum(v[1] for v in results.values())
    fails = [c for v in results.values() for c in v[2]]
    print("\ntest_drop_dialog_first_frame: %d/%d cells passed (fail=%s%s) walls %s in %.1fs" % (
        passed, total, fails, (" shutdown=%s" % failed) if failed else "", json.dumps(walls), time.time() - t0), flush=True)
    return 2 if fails or failed or total != 17 else 0

if __name__ == "__main__":
    sys.exit(main())
