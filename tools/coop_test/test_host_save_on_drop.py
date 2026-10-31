"""test_host_save_on_drop.py: in a PvP co-op campaign (each player keeps its own world) every host geoscape save is deferred
- SaveGameState arms it and shows "Saving..." (CoopState 54) until the second player's world arrives. A Shared or
Separate campaign has one world and its host saves at once. When that player drops while the 54 is up, the host
writes the armed save at once, with the partner's world it already holds, and the drop's wait dialog 62 is left on top
of the stack the save started from. When broken, the drop path pushes the 62 over the 54 and
CoopSession::onClientDrop() clears the armed name (a main-thread -3 keeps it armed under a READY 62): the file is never
written. Five rows, one fresh boot pair each (key "49197", dirs save_on_drop_<row>_host / _client;
pvp_fixture.start_pvp_campaign gm3 tcp, the host on the Alien team; both tops GeoscapeState unchanged STABLE_S within
BOOT_S):
  quick_kill: quick save + client.kill(); auto_kill: auto_geoscape + kill; send_failure: quick + host
  force_send_failure (the host's next PING fails: the canonical drop); server_error: quick + host force_server_error (a
  test command: a main-thread -3 with the socket open, taken by updateCoopTask's -3 campaign arm); client_running: quick,
  the client running (control, LAST).
The drop rows suspend the client (NtSuspendProcess by its own GameClient pid; resumed or killed in finally) at the
host's first sight of the 54 and read the host HOLD_S after the drop event (send_failure: after SEND_LOST_GEO,
server_error: after the 62; then the client is killed); client_running reads 1 s after the 54 is gone and the file
written.
Cells, named <row>-<check>: -pre GUARD (the 54 on top within SEEN54_S, the armed name = the row's file; drop rows: CLEAR
+0 at the 54, the suspend rc 0; quick_kill, auto_kill: the client exited; send_failure: armed + ARMED +1 +
SEND_LOST_GEO +1 within W_LOST; server_error: SERVER +1 + the 62 within W_62); -file FIX (written: present, mtime newer
than the baseline's); -dialog FIX (the baseline stack + [CoopState], code 62); -blob FIX (quick_kill, auto_kill,
send_failure, server_error: one coopClientSaves entry, key host_<saveID at the 54>_<baseline clientName>.data, its
FNV-1a 64 = the baseline coop_file_info fnv1a64); -name GUARD (pendingHostSaveName ""; a FIX for server_error);
-path FIX ((DEFERRED_DROP, CLEAR, FREEZE, DROP) = (1, 1, 1, 1); server_error (1, 1, 1, 0) and SERVER 1); -common GUARD
(host alive, no new crash_*.log since the baseline). client_running's -file / -dialog / -blob / -path are GUARDs
(written, the baseline stack within W_SAVE, the single entry at the saveID after with coop_file_info's fnv after the
write, (0, 1, 0, 0)). 35 cells. When broken: exit 2, failing exactly the -file, -dialog, -blob and -path cells of
quick_kill, auto_kill and send_failure, and server_error's -file, -dialog, -name, -blob and -path (17).
A precondition miss ends its row (cells "not reached"); a boot miss fails the row "boot" with ONE CAPTURE line. ONE
EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; exit 0 only when every cell passes, else 2. one
foreground run per invocation.
Run: python tools/coop_test/test_host_save_on_drop.py
"""
import base64, ctypes, glob, json, os, sys, time  # noqa: E401
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml  # noqa: E402
import session  # noqa: E402
import pvp_fixture as PF  # noqa: E402
from harness import GameClient, make_user_dir, cpu_load, cpu_text  # noqa: E402

KEY = "49197"
QUICK, AUTO = "_quick_.asav", "_autogeo_.asav"
POLL_S, POLL54_S, SEEN54_S, HOLD_S, W_LOST, W_62, W_SAVE, STABLE_S, BOOT_S = 0.1, 0.005, 10.0, 5.0, 5.0, 5.0, 10.0, 2.0, 60.0
RC_OK = (0, 3221226505)
NEEDLES = {"DEFERRED_DROP": "[coop] the partner dropped during the host's deferred save",
           "CLEAR": "[coop-session] clearDeferredSave",
           "FREEZE": "[coop-session] freeze (lobbyMode=", "DROP": "[coop-session] onClientDrop", "ARMED": "[coop-test] force_send_failure: armed",
           "SEND_LOST_GEO": "[coop] the partner was lost on a failed send - the canonical drop",
           "SERVER": "[coop-test] force_server_error: onConnect -3 (main thread)"}
PATH4 = ("DEFERRED_DROP", "CLEAR", "FREEZE", "DROP")

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
    return pick(q(gc, {"cmd": "get_coop"}), ("pendingHostSaveName", "saveID", "clientName", "onConnect", "resumeAck", "coopSession", "shared",
                                             "error"))

def dlg(gc):
    return pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "backVisible", "error"))

def blobinfo(gc):
    return pick(q(gc, {"cmd": "coop_file_info", "role": "host_copy_of_client"}), ("key", "present", "bytes", "fnv1a64", "error"))

def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def counts(gc, n0):
    lines = log(gc)[n0:]
    return {k: sum(1 for ln in lines if v in ln) for k, v in NEEDLES.items()}

def wait(desc, pred, timeout, interval=POLL_S):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(interval)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))

def cpu():
    return cpu_text(cpu_load()["cpu"])

def files(gc):
    """the host's master save folder <user_dir>/xcom1: name -> [bytes, mtime_ns]"""
    out = {}
    for p in sorted(glob.glob(os.path.join(gc.user_dir, "xcom1", "*"))):
        try:
            if os.path.isfile(p):
                st = os.stat(p)
                out[os.path.basename(p)] = [st.st_size, st.st_mtime_ns]
        except FileNotFoundError:  # renamed after the listing (the save's .bak -> .asav move)
            pass
    return out

def written(folder, before, f):
    """f present in the folder and its mtime_ns newer than in before (or absent there)"""
    a, b = folder.get(f), before.get(f)
    return bool(a and (b is None or a[1] > b[1]))

def fnv(b):
    """FNV-1a 64 (offset 1469598103934665603, prime 1099511628211, mod 2^64; TestServer coop_file_info), 16 hex digits"""
    h = 1469598103934665603
    for ch in b:
        h = ((h ^ ch) * 1099511628211) % (1 << 64)
    return "%016x" % h

def blobs(path):
    """the save's coopClientSaves entries (key, bytes, fnv1a64): PyYAML load_all (CSafeLoader when present), the blob base64 (a str) or
    binary (bytes), as test_craft_peer_craft_target.py read_save does (copied)"""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    except Exception as e:  # a value
        return {"error": short(e, 300)}
    out = []
    for d in docs:
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            b = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw or b"")
            out.append({"key": e.get("key"), "bytes": len(b), "fnv1a64": fnv(b)})
    return {"entries": out}

_K32, _NT = ctypes.windll.kernel32, ctypes.windll.ntdll

def _nt(gc, fn):
    """NtSuspendProcess / NtResumeProcess on THIS GameClient's own pid (never by image name: other harness slots run
    games) -> rc"""
    _K32.OpenProcess.restype = ctypes.c_void_p
    h = _K32.OpenProcess(0x0800, False, gc.proc.pid)  # PROCESS_SUSPEND_RESUME
    rc = fn(ctypes.c_void_p(h))
    _K32.CloseHandle(ctypes.c_void_p(h))
    return rc

def suspend(gc):
    return _nt(gc, _NT.NtSuspendProcess)

def resume(gc):
    return _nt(gc, _NT.NtResumeProcess)

class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0, self.n_h = rid, cells, x, [], set(), time.time(), 0
        self.cr0, self.ev = session._crash_log_snapshot(), {}

    def evidence(self):
        print("EVIDENCE %s: %s" % (self.rid, json.dumps(self.ev, sort_keys=True, default=str)), flush=True)

    def cell(self, cid, kind, label, ok):
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)

    def end(self, results, walls, cap=None):
        """ONE CAPTURE line when a cell failed (never probing a suspended client), then the row verdict"""
        x, walls[self.rid] = self.x, round(time.time() - self.t0, 1)
        if self.fails:
            if cap is None:
                cap = {n: {"stack": stack(gc), "get_coop": coop(gc), "coop_dialog_info": dlg(gc)} for n, gc in (("host", x.host), ("client", x.client))
                       if alive(gc) and not (gc is x.client and x.held)}
                if alive(x.host):
                    cap["host needle deltas"] = counts(x.host, self.n_h)
                    cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(x.host) if "[coop" in ln][-12:]
                    cap["host folder"] = files(x.host)
                cap["new crash"] = sorted(session._crash_log_snapshot() - self.cr0)
            print("CAPTURE %s: %s" % (self.rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)

    def boot_miss(self, results, walls):
        print("FAIL %s boot: the boot did not reach both tops GeoscapeState unchanged %.0f s (%s)" % (self.rid, STABLE_S, self.x.err), flush=True)
        self.fails.append("boot")
        self.stop("boot")
        self.end(results, walls, cap=self.x.cap)

def baseline(r, x, shared):
    """The baseline, just before the trigger: crash snapshot, the host log's line count, stack, get_coop, coop_file_info
    (SEPARATE), the folder"""
    r.cr0, r.n_h = session._crash_log_snapshot(), len(log(x.host))
    r.ev["baseline"] = {"stack": stack(x.host), "get_coop": coop(x.host), "folder": files(x.host)}
    if not shared:
        r.ev["baseline"]["coop_file_info"] = blobinfo(x.host)
    return r.ev["baseline"]

def at54(r, x, stype, hold):
    """trigger(type), then poll every POLL54_S up to SEEN54_S: the host's top CoopState with coop_dialog_info.code 54 -> suspend the
    client at once (hold) -> the host's get_coop (name, saveID), stack and CLEAR count. None when the 54 was not seen."""
    h, ev = x.host, r.ev
    tt = time.time()
    ev["trigger"] = pick(q(h, {"cmd": "save_game_ui", "type": stype}), ("ok", "error"))
    while time.time() - tt < SEEN54_S:
        s = stack(h)
        if s and s[-1] == "CoopState" and dlg(h).get("code") == 54:
            a = {"s": round(time.time() - tt, 3)}
            if hold:
                x.held = True
                a["suspend rc"] = suspend(x.client)
            cp = coop(h)
            a.update({"name": cp.get("pendingHostSaveName"), "saveID": cp.get("saveID"), "stack": stack(h), "CLEAR": counts(h, r.n_h)["CLEAR"]})
            ev["at54"] = a
            return tt, a
        time.sleep(POLL54_S)
    ev["at54"] = {"missed": "the host's 54 not on top within %.0f s" % SEEN54_S, "stack": stack(h), "dialog": dlg(h), "get_coop": coop(h)}
    return tt, None

def read(r, x, f, base, tt):
    h = x.host
    rd = {"t": round(time.time() - tt, 2), "stack": stack(h), "dialog": dlg(h), "get_coop": coop(h), "folder": files(h),
          "needles": counts(h, r.n_h), "alive": alive(h), "new crash": sorted(session._crash_log_snapshot() - r.cr0)}
    rd["written"] = written(rd["folder"], base["folder"], f)
    rd["blob"] = blobs(os.path.join(h.user_dir, "xcom1", f)) if rd["written"] else None
    return rd

def blob_ok(rd, key, fv):
    e = (rd.get("blob") or {}).get("entries")
    return bool(rd["written"] and e is not None and len(e) == 1 and e[0]["key"] == key and e[0]["fnv1a64"] == fv)

def drop_kill(r, x, tt):
    t = time.time()
    x.client.kill()
    x.held = False
    r.ev["drop"] = {"event": "client.kill()", "s": round(t - tt, 3), "reaped s": round(time.time() - t, 3), "rc": x.client.proc.poll()}
    return not alive(x.client), "the client process exited"

def drop_send(r, x, tt):
    h, d = x.host, r.ev.setdefault("drop", {})
    d["reply"] = pick(q(h, {"cmd": "force_send_failure"}), ("ok", "armed", "error"))
    d["s"] = round(time.time() - tt, 3)
    try:
        d["SEND_LOST_GEO s"] = wait("SEND_LOST_GEO +1", lambda: counts(h, r.n_h)["SEND_LOST_GEO"] >= 1, W_LOST, 0.05)
    except Stop as e:
        d["stop"] = str(e)
    n = counts(h, r.n_h)
    return (d["reply"].get("armed") is True and n["ARMED"] == 1 and n["SEND_LOST_GEO"] == 1 and "stop" not in d,
            "armed true, ARMED +1, SEND_LOST_GEO +1 within %.0f s" % W_LOST)

def drop_server(r, x, tt):
    h, d = x.host, r.ev.setdefault("drop", {})
    d["reply"] = pick(q(h, {"cmd": "force_server_error"}), ("ok", "error"))
    d["s"] = round(time.time() - tt, 3)
    try:
        d["62 s"] = wait("the host's 62 on a top CoopState", lambda: (stack(h) or [None])[-1] == "CoopState" and dlg(h).get("code") == 62, W_62,
                         0.05)
    except Stop as e:
        d["stop"] = str(e)
    return (d["reply"].get("ok") is True and counts(h, r.n_h)["SERVER"] == 1 and "stop" not in d,
            "ok, SERVER +1, the host's 62 on top within %.0f s" % W_62)

def drop_row(x, results, walls, rid, p, stype, f, drop, shared=False):
    """The drop rows: trigger, at54 (suspend), the drop event, read at HOLD_S, the cells"""
    blob = p in "quick_kill auto_kill send_failure server_error"
    cells = ["%s-%s" % (p, c) for c in (("pre", "file", "dialog") + (("blob",) if blob else ()) + ("name", "path", "common"))]
    r = Row(rid, cells, x)
    if x.err:
        return r.boot_miss(results, walls)
    h, ev = x.host, r.ev
    try:
        ev["cpu"] = x.cpu
        base = baseline(r, x, shared)
        tt, a = at54(r, x, stype, True)
        pre = "the 54 on top within %.0f s, the armed name %s, CLEAR +0 at the 54, the suspend rc 0" % (SEEN54_S, f)
        if a is None or a["name"] != f or a["CLEAR"] != 0 or a.get("suspend rc") != 0:
            r.evidence()
            r.cell(p + "-pre", "GUARD", pre, False)
            raise Stop("%s-pre: at54 %s" % (p, ev["at54"]))
        ok, what = drop(r, x, tt)
        if not ok:
            ev["needles"] = counts(h, r.n_h)
            r.evidence()
            r.cell(p + "-pre", "GUARD", pre + "; " + what, False)
            raise Stop("%s-pre: %s" % (p, ev["drop"]))
        td = time.time()
        while time.time() - td < HOLD_S:
            time.sleep(0.05)
        rd = ev["read"] = read(r, x, f, base, tt)
        if alive(x.client):
            x.client.kill()
            x.held = False
            ev["drop"]["client killed after the read"] = True
        r.evidence()
        r.cell(p + "-pre", "GUARD", pre + "; " + what, True)
        n = rd["needles"]
        r.cell(p + "-file", "FIX", "%s written (present, mtime newer than the baseline's) %.0f s after the drop "
               "(when broken: not written)" % (f, HOLD_S), rd["written"])
        r.cell(p + "-dialog", "FIX", "the host stack = the baseline's + [CoopState] with code 62 (when broken: the "
               "baseline + [CoopState, CoopState], the 54 under the 62)",
               rd["stack"] == base["stack"] + ["CoopState"] and rd["dialog"].get("code") == 62)
        if blob:
            key = "host_%s_%s.data" % (a["saveID"], base["get_coop"].get("clientName"))
            r.cell(p + "-blob", "FIX", "the file's coopClientSaves: 1 entry, key %s, FNV-1a 64 = the baseline "
                   "coop_file_info %s (when broken: no file)" % (key, base["coop_file_info"].get("fnv1a64")),
                   blob_ok(rd, key, base["coop_file_info"].get("fnv1a64")))
        if p == "server_error":
            r.cell("server_error-name", "FIX", "pendingHostSaveName \"\" at the read (when broken: still armed, the "
                   "main-thread -3 arm calls no onClientDrop)", rd["get_coop"].get("pendingHostSaveName") == "")
            r.cell("server_error-path", "FIX", "(DEFERRED_DROP, CLEAR, FREEZE, DROP) = (1, 1, 1, 0) and SERVER 1 since "
                   "the baseline (when broken: (0, 0, 1, 0))",
                   tuple(n[k] for k in PATH4) == (1, 1, 1, 0) and n["SERVER"] == 1)
        else:
            r.cell(p + "-name", "GUARD", "pendingHostSaveName \"\" at the read (onClientDrop clears it)",
                   rd["get_coop"].get("pendingHostSaveName") == "")
            r.cell(p + "-path", "FIX", "(DEFERRED_DROP, CLEAR, FREEZE, DROP) = (1, 1, 1, 1) since the baseline "
                   "(when broken: (0, 0, 1, 1))", tuple(n[k] for k in PATH4) == (1, 1, 1, 1))
        r.cell(p + "-common", "GUARD", "the host alive at the read, no new crash_*.log since the baseline",
               rd["alive"] and not rd["new crash"])
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def row_quick_kill(x, results, walls):
    drop_row(x, results, walls, "quick_kill", "quick_kill", "quick", QUICK, drop_kill)

def row_auto_kill(x, results, walls):
    drop_row(x, results, walls, "auto_kill", "auto_kill", "auto_geoscape", AUTO, drop_kill)

def row_send_failure(x, results, walls):
    drop_row(x, results, walls, "send_failure", "send_failure", "quick", QUICK, drop_send)

def row_server_error(x, results, walls):
    drop_row(x, results, walls, "server_error", "server_error", "quick", QUICK, drop_server)


def row_client_running(x, results, walls):
    """the control (LAST): the quick save with the client running - the 54 closes and QUICK is written when its world arrives"""
    r = Row("client_running", ["client_running-pre", "client_running-file", "client_running-dialog",
                               "client_running-blob", "client_running-name", "client_running-path",
                               "client_running-common"], x)
    if x.err:
        return r.boot_miss(results, walls)
    h, ev = x.host, r.ev
    try:
        ev["cpu"] = x.cpu
        base = baseline(r, x, False)
        tt, a = at54(r, x, "quick", False)
        pre = "the 54 on top within %.0f s, the armed name %s (no suspend; CLEAR at the 54 recorded)" % (SEEN54_S, QUICK)
        if a is None or a["name"] != QUICK:
            r.evidence()
            r.cell("client_running-pre", "GUARD", pre, False)
            raise Stop("client_running-pre: at54 %s" % ev["at54"])
        try:
            ev["54 gone + written s"] = wait("the 54 gone, the baseline stack and %s written" % QUICK,
                                             lambda: stack(h) == base["stack"] and written(files(h), base["folder"],
                                                                                           QUICK), W_SAVE, 0.05)
        except Stop as e:
            ev["wait"] = str(e)
        time.sleep(1.0)
        rd = ev["read"] = read(r, x, QUICK, base, tt)
        rd["coop_file_info after"] = blobinfo(h)
        met = "wait" not in ev
        r.evidence()
        r.cell("client_running-pre", "GUARD", pre, True)
        n = rd["needles"]
        r.cell("client_running-file", "GUARD", "%s written within %.0f s" % (QUICK, W_SAVE), met and rd["written"])
        r.cell("client_running-dialog", "GUARD",
               "the host stack = the baseline's within %.0f s and at the read" % W_SAVE,
               met and rd["stack"] == base["stack"])
        key = "host_%s_%s.data" % (rd["get_coop"].get("saveID"), base["get_coop"].get("clientName"))
        fv = rd["coop_file_info after"].get("fnv1a64")
        r.cell("client_running-blob", "GUARD", "the file's single coopClientSaves entry: key %s, the FNV of "
               "coop_file_info after the write %s" % (key, fv),
               blob_ok(rd, key, fv))
        r.cell("client_running-name", "GUARD", "pendingHostSaveName \"\" at the read",
               rd["get_coop"].get("pendingHostSaveName") == "")
        r.cell("client_running-path", "GUARD", "(DEFERRED_DROP, CLEAR, FREEZE, DROP) = (0, 1, 0, 0) since the baseline",
               tuple(n[k] for k in PATH4) == (0, 1, 0, 0))
        r.cell("client_running-common", "GUARD", "the host alive at the read, no new crash_*.log since the baseline",
               rd["alive"] and not rd["new crash"])
    except Exception as e:  # Stop, or a probe that raised: the row ends here
        r.stop(e)
    r.end(results, walls)

def boot(rid, tag, shared):
    """CPU, host + client spawn, connect, a PvP campaign (port=KEY), both tops GeoscapeState unchanged STABLE_S within BOOT_S
    (else x.err and x.cap: both stacks, coop_dialog_info, get_coop)"""
    x = SimpleNamespace(rid=rid, tag=tag, host=None, client=None, err=None, cap=None, held=False, cpu=cpu())
    try:
        x.host, x.client = GameClient("host", None, make_user_dir(tag + "_host")), GameClient("client", None, make_user_dir(tag + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        PF.start_pvp_campaign(x.host, x.client, KEY, alien_player="host")
        t0, last, tch = time.time(), None, time.time()
        while True:
            s = (tuple(stack(x.host)), tuple(stack(x.client)))
            if s != last:
                last, tch = s, time.time()
            if s[0] and s[1] and s[0][-1] == s[1][-1] == "GeoscapeState" and time.time() - tch >= STABLE_S:
                break
            if time.time() - t0 > BOOT_S:
                raise Stop("both tops GeoscapeState unchanged %.0f s: not within %.0f s" % (STABLE_S, BOOT_S))
            time.sleep(POLL_S)
    except Exception as e:
        x.err = short(e, 600)
        x.cap = {n: {"stack": stack(gc), "coop_dialog_info": dlg(gc), "get_coop": coop(gc)} for n, gc in (("host", x.host), ("client", x.client))
                 if alive(gc)}
    return x

def shut(x):
    """resume a suspended client, then every machine of the boot (a killed client was reaped by kill()) -> the shutdown failures"""
    failed = []
    if x.held and alive(x.client):
        print("NOTE %s: the suspended client resumed before its shutdown (rc %s)" % (x.tag, resume(x.client)), flush=True)
        x.held = False
    for gc in (x.client, x.host):
        try:
            if gc is not None and gc.proc is not None:
                gc.shutdown(expected_returncodes=RC_OK)
        except Exception as e:
            print("FAIL %s shutdown (%s): %s" % (x.tag, gc.name, short(e, 300)), flush=True)
            failed.append("%s shutdown %s" % (x.tag, gc.name))
    return failed

ROWS = (("quick_kill", "save_on_drop_quick_kill", row_quick_kill, False),
        ("auto_kill", "save_on_drop_auto_kill", row_auto_kill, False),
        ("send_failure", "save_on_drop_send_failure", row_send_failure, False),
        ("server_error", "save_on_drop_server_error", row_server_error, False),
        ("client_running", "save_on_drop_client_running", row_client_running, False))

def main():
    t0, results, walls, failed = time.time(), {}, {}, []
    for rid, tag, row, shared in ROWS:
        tb = time.time()
        x = boot(rid, tag, shared)
        walls[tag + " boot"] = round(time.time() - tb, 1)
        try:
            row(x, results, walls)
        finally:
            failed += shut(x)
        walls[tag] = round(time.time() - tb, 1)
    failed += [rid for rid, _t, _r, _s in ROWS if not results.get(rid)]
    print("\ntest_host_save_on_drop: %d/%d rows passed (fail=%s) walls %s in %.1fs" % (
        sum(1 for rid, _t, _r, _s in ROWS if results.get(rid)), len(ROWS), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
