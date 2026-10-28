"""W2-H58 shared drop / rejoin fixture (tools/coop_test/drop_fixture.py; spec docs rewrite/prompts/w2h58_rejoin_world_kept.md section F,
QH58-1 (a)). Written by S-A's red (w2h58_sa_rekey.md) and imported unchanged by S-B (w2h58_sb_rx_buffer.md).
L-LH54-2-1 (a partner who drops during the host's quick save rejoins into a fresh world, F18420) and L-LH54-2-2 (the host's inbound buffer
keeps a half-sent world through the drop, F18425 / F18428). The shapes are copied from the capture docs rewrite/lh54-2b-cap/lh54b.py (never
imported): the drop at the host's FIRST sight of its "Saving..." (CoopState code 54, 5 ms polls) suspends the partner (NtSuspendProcess),
reads, then kills it; the host's 62 follows. Every rejoiner is a NEW GameClient on a fresh dir that joins the same lobby key by name.
Every function records what it saw in a dict it returns (the test prints it as EVIDENCE); none asserts or exits. Never dismiss_popup,
coop_dialog_back, leave_base or a base placement: a fresh world is evidence, never built on. one foreground run per invocation.
drop_at_54's optional ready(host) is waited for (at most ready_s) between the 54 sight and the suspend (cap-save F23943)."""
import ctypes
import glob
import os
import time

import harness
import session

QUICK, AUTO = "_quick_.asav", "_autogeo_.asav"
NEEDLES = ("[coop-session]", "W2-H58", "onClientDrop", "campaign_start", "Network process exception")

def now(t0):
    return round(time.time() - t0, 3)

def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # noqa: BLE001 - a dead or gone machine is a value
        return {"error": ("%s: %s" % (type(e).__name__, e))[:200]}

def stk(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # noqa: BLE001
        return ["probe failed: %s: %s" % (type(e).__name__, str(e)[:100])]

def top(gc):
    return (stk(gc) or [None])[-1]

def _pick(r, keys):
    return {k: r.get(k) for k in keys if k in r}

def dlg(gc):
    return _pick(q(gc, {"cmd": "coop_dialog_info"}), ("present", "code", "title", "backText", "backVisible", "error"))

def coop(gc):
    return _pick(q(gc, {"cmd": "get_coop"}), ("pendingHostSaveName", "onConnect", "resumeAck", "saveID", "error"))

def sid(gc):
    r = q(gc, {"cmd": "save_markers"})
    return r.get("saveID", r.get("error"))

def key(gc, k):
    return _pick(q(gc, {"cmd": "coop_file_info", "key": k}), ("key", "present", "bytes", "fnv1a64", "error"))

def files(gc):
    """the machine's xcom1 save folder: {name: [size, mtime_ns]}; a file renamed between the listing and its stat (the save's
    .bak -> .asav move) is gone at this read and left out (cap-save F23944)"""
    out = {}
    for p in sorted(glob.glob(os.path.join(gc.user_dir, "xcom1", "*"))):
        try:
            if os.path.isfile(p):
                st = os.stat(p)
                out[os.path.basename(p)] = [st.st_size, st.st_mtime_ns]
        except FileNotFoundError:
            pass
    return out

def crashes():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))

def logl(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []

def lines_since(gc, n0, needles=NEEDLES):
    sel = [ln.split("\t") for ln in logl(gc)[n0:] if any(n in ln for n in needles)]
    return [p[0][-13:-1] + " " + p[-1][:300] for p in sel]

def cpu():
    """\\Processor(_Total)\\% Processor Time (F4445) and any Wardogs* process (the owner's game)"""
    c = harness.cpu_load()
    return {"t": time.strftime("%H:%M:%S"), "cpu": harness.cpu_text(c["cpu"], 0), "wardogs": ",".join(c["wardogs"])}

_K32, _NT = ctypes.windll.kernel32, ctypes.windll.ntdll

def _nt(gc, fn):
    _K32.OpenProcess.restype = ctypes.c_void_p
    h = _K32.OpenProcess(0x0800, False, gc.proc.pid)  # PROCESS_SUSPEND_RESUME
    rc = getattr(_NT, fn)(ctypes.c_void_p(h))
    _K32.CloseHandle(ctypes.c_void_p(h))
    return rc

def suspend(gc):
    return _nt(gc, "NtSuspendProcess")

def resume(gc):
    return _nt(gc, "NtResumeProcess")

def stable_geo(host, client, stable=5.0, timeout=90.0):
    """both tops GeoscapeState and both stacks unchanged for `stable` s"""
    t0, last, prev = time.time(), time.time(), None
    while time.time() - t0 < timeout:
        cur = (tuple(stk(host)), tuple(stk(client)))
        if cur != prev:
            prev, last = cur, time.time()
        if cur[0] and cur[1] and cur[0][-1] == "GeoscapeState" and cur[1][-1] == "GeoscapeState" and time.time() - last >= stable:
            return {"ok": True, "s": now(t0), "host": list(cur[0]), "client": list(cur[1])}
        time.sleep(0.1)
    return {"ok": False, "timeout": now(t0), "host": list(prev[0]) if prev else None, "client": list(prev[1]) if prev else None}

def _button(gc, text):
    r = q(gc, {"cmd": "list_widgets"})
    return r.get("state"), next((w for w in r.get("widgets", []) if (w.get("text") or "").strip().lower() == text.lower()), None)

def real_click(gc, text, timeout=15.0):
    """wait until the widget `text` is visible and not hidden, then ONE click_widget {match}"""
    t0, rec = time.time(), {"text": text, "trail": []}
    while time.time() - t0 < timeout:
        st, w = _button(gc, text)
        k = [(st or "").replace("class OpenXcom::", ""), None if w is None else w.get("visible"), None if w is None else w.get("hidden")]
        if not rec["trail"] or rec["trail"][-1]["k"] != k:
            rec["trail"].append({"t": now(t0), "k": k})
        if w is not None and w.get("visible") is True and w.get("hidden") is False:
            rec.update(stackBefore=stk(gc), dialogBefore=dlg(gc), click=q(gc, {"cmd": "click_widget", "match": text}), tClick=now(t0))
            rec["ok"] = bool(rec["click"].get("ok"))
            return rec
        time.sleep(0.02)
    rec.update(ok=False, timeout="button %r never shown and not hidden within %.0f s" % (text, timeout))
    return rec

def quick_save(host, name=QUICK, timeout=20.0):
    """save_game_ui {type: quick} with the partner running: the 54 seen, then gone; pending ""; `name` written after the trigger"""
    before = files(host).get(name)
    session_s = session.wait_coop_session(host)   # the 54 needs the host's live session
    c = {"filesBefore": files(host), "saveIDBefore": sid(host), "coopBefore": coop(host), "n0": len(logl(host)), "sessionS": session_s}
    t0 = time.time()
    c["trigger"] = q(host, {"cmd": "save_game_ui", "type": "quick"})
    trail, seen = [], False
    while time.time() - t0 < timeout:
        s = {"hostStack": stk(host), "code": dlg(host).get("code"), "pend": coop(host).get("pendingHostSaveName"), "file": files(host).get(name)}
        if not trail or {k: v for k, v in trail[-1].items() if k != "t"} != s:
            trail.append(dict(s, t=now(t0)))
        seen = seen or s["code"] == 54
        written = bool(s["file"] and (not before or s["file"][1] > before[1]))
        if seen and s["hostStack"] and s["hostStack"][-1] == "GeoscapeState" and s["pend"] == "" and written:
            break
        time.sleep(0.02)
    c.update(trail=trail, seen54=seen, t=now(t0), saveIDAfter=sid(host), filesAfter=files(host), coopAfter=coop(host))
    a = c["filesAfter"].get(name)
    c["written"] = bool(a and (not before or a[1] > before[1]))
    c["ok"] = bool(seen and c["written"] and trail and trail[-1]["hostStack"][-1:] == ["GeoscapeState"] and trail[-1]["pend"] == "")
    c["log"] = lines_since(host, c["n0"])[-20:]
    return c

def wait_62(host, timeout=5.0):
    """the host's "Waiting for <name> to reconnect..." (CoopState code 62) on top"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = dlg(host)
        if d.get("code") == 62 and top(host) == "CoopState":
            return {"ok": True, "t": now(t0), "hostStack": stk(host), "dialog": d, "coop": coop(host)}
        time.sleep(0.05)
    return {"ok": False, "timeout": now(t0), "hostStack": stk(host), "dialog": dlg(host), "coop": coop(host)}

def drop_at_54(host, client, savetype, delay_ms=0, probe=None, seen_s=10.0, drop_s=5.0, ready=None, ready_s=2.0):
    """save_game_ui {type}; at the host's first sight of its 54 (then ready(host) true, at most ready_s, when given): suspend the client,
    probe(host), the at-54 reads; kill; the host's 62"""
    session_s = session.wait_coop_session(host)   # the 54 needs the host's live session
    c = {"savetype": savetype, "filesBefore": files(host), "saveIDBefore": sid(host), "coopBefore": coop(host), "n0": len(logl(host)),
         "sessionS": session_s}
    t0 = time.time()
    c["trigger"] = q(host, {"cmd": "save_game_ui", "type": savetype})
    seen = []
    while time.time() - t0 < seen_s:
        s = stk(host)
        if not seen or seen[-1]["stack"] != s:
            seen.append({"t": now(t0), "stack": s})
        if s and s[-1] == "CoopState":
            d = dlg(host)
            if d.get("code") == 54:
                c["seen54"] = now(t0)
                if ready is not None:
                    t1, ok = time.time(), bool(ready(host))
                    while not ok and time.time() - t1 < ready_s:
                        time.sleep(0.002)
                        ok = bool(ready(host))
                    c["ready"] = {"ok": ok, "t": now(t0)}
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                c["suspend"] = {"t": now(t0), "rc": suspend(client), "delayMs": delay_ms}
                if probe is not None:
                    c["probe"] = probe(host)
                c["at54"] = {"t": now(t0), "hostStack": stk(host), "dialog": dlg(host), "coop": coop(host), "saveID": sid(host), "files": files(host)}
                break
        time.sleep(0.005)
    c["seenBefore54"] = seen
    if "suspend" not in c:
        c.update(ok=False, why="the host's 54 never on top within %.0f s" % seen_s)
        return c
    client.proc.kill()
    c["kill"] = {"t": now(t0), "returncode": client.proc.wait(timeout=15)}
    c["after62"] = wait_62(host, drop_s)
    c["ok"] = c["after62"]["ok"]
    if not c["ok"]:
        c["why"] = "no host 62 within %.0f s of the kill" % drop_s
    c["log"] = lines_since(host, c["n0"])[-20:]
    return c

def rejoin(host, gc, port, name, join_s=10.0, ack_s=30.0, at_join=None):
    """spawn + connect a NEW client; join_tcp by name; 0.1 s polls (profile_ok on a Profile top) until the rejoiner's 68 or join_s;
    then up to ack_s for the host's 62 with resumeAck true. A rejoiner left on BuildNewBaseState (a fresh world) gets no ack wait:
    the host acks only once a base is placed, and this fixture never places one."""
    c = {"n0": len(logl(host))}
    t0 = time.time()
    gc.spawn()
    gc.connect()
    c["spawned"] = now(t0)
    if at_join is not None:
        c["atJoin"] = at_join(host)
    tj = time.time()
    c["join_tcp"] = q(gc, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": name})
    c["profile_ok"], trail, c["buildNewBase"], c["t68"], c["ack"] = [], [], None, None, None
    def poll():
        for m in (host, gc):
            if top(m) == "Profile" and (m is host or dlg(gc).get("code") != 52):
                c["profile_ok"].append([m.name, now(tj), q(m, {"cmd": "profile_ok"}).get("ok")])
        cp = coop(host)
        s = {"rj": stk(gc), "rjCode": dlg(gc).get("code"), "host": stk(host), "hostCode": dlg(host).get("code"),
             "resumeAck": cp.get("resumeAck"), "onConnect": cp.get("onConnect")}
        if not trail or {k: v for k, v in trail[-1].items() if k != "t"} != s:
            trail.append(dict(s, t=now(tj)))
        return s
    while c["join_tcp"].get("ok") and time.time() - tj < join_s:
        s = poll()
        if "BuildNewBaseState" in s["rj"] and c["buildNewBase"] is None:
            c["buildNewBase"] = now(tj)
        if s["rj"] == ["GeoscapeState", "CoopState"] and s["rjCode"] == 68:
            c["t68"] = now(tj)
            break
        time.sleep(0.1)
    c["endJoin"] = {"t": now(tj), "rj": stk(gc), "rjDialog": dlg(gc)}
    if c["join_tcp"].get("ok") and top(gc) != "BuildNewBaseState":
        while time.time() - tj < join_s + ack_s:
            s = poll()
            if s["resumeAck"] is True and s["host"][-1:] == ["CoopState"] and s["hostCode"] == 62:
                c["ack"] = now(tj)
                break
            time.sleep(0.1)
    else:
        c["ackSkipped"] = "join_tcp failed" if not c["join_tcp"].get("ok") else "the rejoiner is on BuildNewBaseState (a fresh world)"
    c["trail"] = trail
    c["log"] = lines_since(host, c["n0"])[-25:]
    return c

def resume_and_clear(host):
    """real_click RESUME; if the host's top is then the stale 54, real_click CANCEL; the host's top after up to 5 s"""
    c = {"resume": real_click(host, "RESUME", 15.0)}
    t0 = time.time()
    while time.time() - t0 < 2.0 and dlg(host).get("code") == 62:
        time.sleep(0.05)
    d = dlg(host)
    c["afterResume"] = {"t": now(t0), "hostStack": stk(host), "dialog": d}
    if top(host) == "CoopState" and d.get("code") == 54:
        c["cancel"] = real_click(host, "CANCEL", 15.0)
    t1 = time.time()
    while time.time() - t1 < 5.0 and top(host) != "GeoscapeState":
        time.sleep(0.05)
    c["end"] = {"t": now(t1), "hostStack": stk(host), "dialog": dlg(host), "coop": coop(host)}
    c["ok"] = bool(c["resume"].get("ok") and c["end"]["hostStack"][-1:] == ["GeoscapeState"])
    return c
