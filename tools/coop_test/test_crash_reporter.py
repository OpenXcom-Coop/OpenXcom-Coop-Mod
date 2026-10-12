"""RV-U9 (spec rewrite/prompts/rvu9_crash_report_prompt.md (f); owner D228 (a), D229 (a) + gate; QV9-3..QV9-6 (a); TASK 0
rewrite/rvu9-task0/CONSTANTS.md): `main`'s next-launch crash-report prompt (PRD-I5 Pattern A, aud-E1-26) over the main menu after a crash,
"Previous crash detected" with BUNDLE (zip into <user>/crash-reports, then the "CRASH REPORT BUNDLED" notice = R4-L3 S-C's
CoopDesyncNoticeState read through `desync_dialog`) / NOT NOW (asks again next launch) / NEVER (never again for that crash), from both
sources: the marker <user>/crash-pending.json and an unseen crash dump in harness.CRASH_DIR (the lane folder the game reads through
OXC_CRASHLOG_DIR; QV9-4: the ledger pre-marks every dump already there seen; the row deletes its own pair whatever its verdict).
One game at a time, GameClient(name, None, d) (no lobby key); user folder rvu9_<row> made ONCE per row (a relaunch reuses it). Rows:
  N0 nothing planted: N0-menu, N0-ledger, N0-crash          MB marker, BUNDLE: MB-prompt, MB-zip, MB-marker, MB-notice, MB-crash
  MN marker, NOT NOW: MN-prompt, MN-keep, MN-crash          MV marker, NEVER, relaunch: MV-prompt, MV-drop, MV-again, MV-crash
  CB dump, BUNDLE: CB-prompt, CB-zip, CB-seen, CB-notice, CB-crash
  CN dump, NOT NOW, relaunch: CN-prompt, CN-keep, CN-again, CN-crash    CV dump, NEVER, relaunch: CV-prompt, CV-drop, CV-again, CV-crash
Every click waits for its TextButton visible and NOT hidden (`ready`: a click during the popup is dropped, F12475, F12711). A cell after
a row's -prompt cell is judged only when that cell passed, else it FAILs "no prompt" (its actions are not run). A boot not settled on
MainMenuState or the prompt within 60 s is a FIXTURE-STOP of its row: ONE CAPTURE line, every cell not yet judged FAILs "boot".
<row>-crash: no new crash_* in harness.CRASH_DIR since the row began but the row's own pair, and every game of the row exited 0.
Per row: ONE EVIDENCE line, one PASS/FAIL line per cell, the row verdict. Polls 0.25 s, waits bounded. Red (A1, the unchanged build with
C2): N0-ledger, every -prompt cell and the cells behind it FAIL (20); N0-menu and the seven -crash cells PASS. Green (A2): 28/28.
ONE run (WV-D95: no wait-hook, run to completion in the foreground; WV-D99 / WV-D100: no SKIP path, no exit 3); exit 0 iff every cell
passes, else 2.
"""
import ctypes
import glob
import json
import os
import sys
import time
import zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

POLL, W_BOOT, W_SETTLE, W_READY, W_LEAVE, W_ZIP = 0.25, 60.0, 60.0, 10.0, 10.0, 10.0
PROMPT, MENU, NOTICE = "CoopCrashPromptState", "MainMenuState", "CoopDesyncNoticeState"
HEADLINE = "Previous crash detected"                 # STR_COOP_CRASH_REPORT_HEADLINE (US = GB)
PROMPT_BODY = "OpenXcom crashed the last time it ran."  # STR_COOP_CRASH_REPORT_PROMPT, first line
NOTICE_BODY = "CRASH REPORT BUNDLED"                 # STR_COOP_CRASH_REPORT_SAVED, first line
BUTTONS = ("BUNDLE", "NOT NOW", "NEVER")
NOTICE_BUTTONS = ["OK", "OPEN FOLDER", "REPORT ON GITHUB"]
ISSUE_URL = "https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues/new?title=%5Bcoop%20crash%5D"
MARKER_TS, MARKER_EXC = "15-08-2026_10-00-00", "0xC0000005"
DUMP_BYTES = b"FAKE-MINIDUMP-CONTENT-FOR-I5-TEST\n" * 32
LOG_TAGS = ("[coop-ui]", "[COOP]")


class BootMiss(Exception):
    """a boot did not settle on MainMenuState or the prompt: FIXTURE-STOP of the row"""


def short(e, n=300):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def js(v):
    return json.dumps(v, sort_keys=True, default=str)


def q(g, obj):
    try:
        return g.cmd(obj)
    except Exception as e:  # a dead or gone game is a value
        return {"error": short(e, 200)}


def bare(name):
    return (name or "").replace("class OpenXcom::", "")


def stack(g):
    return [bare(s) for s in q(g, {"cmd": "get_state"}).get("states", [])]


def lw(g):
    r = q(g, {"cmd": "list_widgets"})
    return bare(r.get("state")) if r.get("ok") else "error: %s" % r.get("error"), r.get("widgets") or []


def captions(widgets):
    return [[bare(w.get("type")), w.get("text"), w.get("visible"), w.get("hidden"), w.get("interactive")]
            for w in widgets if "text" in w]


def cpu_now():
    from ctypes import wintypes
    ft = [wintypes.FILETIME() for _ in range(3)]
    ctypes.windll.kernel32.GetSystemTimes(*[ctypes.byref(f) for f in ft])
    return [(f.dwHighDateTime << 32) | f.dwLowDateTime for f in ft]


def cpu_pct(a, b):
    idle, total = b[0] - a[0], (b[1] - a[1]) + (b[2] - a[2])
    return round(100.0 * (total - idle) / total, 1) if total > 0 else None


def npath(p):
    return os.path.normcase(os.path.abspath(p)) if p else None


def read_bytes(p):
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None


def listing(d):
    out = []
    for root, _dirs, files in os.walk(d):
        out += [os.path.relpath(os.path.join(root, n), d).replace("\\", "/") for n in files]
    return sorted(out)


def log_lines(d, tags=LOG_TAGS, n=None):
    p = os.path.join(d, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        lines = [ln.rstrip("\n").split("\t")[-1][:200] for ln in f if tags is None or any(t in ln for t in tags)]
    return lines[-n:] if n else lines


def crash_names():
    d = harness.CRASH_DIR
    return set(n for n in os.listdir(d) if n.startswith("crash_")) if os.path.isdir(d) else set()


def zips(d):
    return sorted(glob.glob(os.path.join(d, "crash-reports", "crash-*.zip")))


def zip_read(p):
    z = {"path": p}
    try:
        with zipfile.ZipFile(p) as zf:
            z["members"] = sorted(zf.namelist())
            for m in ("crash.dmp", "crash-log.txt"):
                if m in z["members"]:
                    z[m] = zf.read(m)
            if "crash-info.json" in z["members"]:
                z["info"] = json.loads(zf.read("crash-info.json").decode("utf-8", errors="replace"))
    except Exception as e:
        z["error"] = short(e, 200)
    return z


def ledger(d):
    p = os.path.join(d, "crash-seen.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return "unreadable: %s" % short(e, 120)


def raises(dd):
    return (dd.get("last") or {}).get("raiseCount")


# ---- the planted crash sources (`main`'s CR :52-:65 and :140-:150; the crash folder is harness.CRASH_DIR, QV9-4) ----
def plant_marker(user_dir, ts, exc="0xC0000005"):
    dump = os.path.join(user_dir, ts + ".dmp")
    log = os.path.join(user_dir, "openxcom.log")
    with open(dump, "wb") as f:
        f.write(b"FAKE-MINIDUMP-CONTENT-FOR-I5-TEST\n" * 32)
    if not os.path.exists(log):
        with open(log, "w", encoding="utf-8") as f:
            f.write("stub openxcom.log planted by test_crash_reporter\n")
    marker = os.path.join(user_dir, "crash-pending.json")
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "dump": dump, "log": log,
                   "version": "Extended 8.4.2 (i5-test)", "exception": exc}, f, indent=2)
    return marker


def fab_crashlog(nonce):
    os.makedirs(harness.CRASH_DIR, exist_ok=True)
    base = "crash_%s_123_%d" % (time.strftime("%Y%m%d_%H%M%S"), nonce)
    dmp = os.path.join(harness.CRASH_DIR, base + ".dmp")
    log = os.path.join(harness.CRASH_DIR, base + ".log")
    with open(dmp, "wb") as f:
        f.write(b"FAKE-VEH-MINIDUMP-%d\n" % nonce * 16)
    with open(log, "w", encoding="utf-8") as f:
        f.write("==== Crash/Log ====\nUNHANDLED SEH. Code = 0xC0000005 (fabricated VEH crashlog)\nMods: xcom1\n")
    return dmp, log


def write_ledger(user_dir):
    """the row's ledger: baseline one minute ago, every crash_*.dmp already in the lane folder seen"""
    seen = sorted(n for n in crash_names() if n.endswith(".dmp"))
    with open(os.path.join(user_dir, "crash-seen.json"), "w", encoding="utf-8") as f:
        json.dump({"baseline": int(time.time()) - 60, "seen": seen}, f)
    return len(seen)


# ---- driving the game ----
def settle(g, timeout=W_SETTLE):
    """poll list_widgets until the top is the prompt or the main menu (exact names: GoToMainMenuState is neither)"""
    seq, t0 = [], time.time()
    while time.time() - t0 < timeout:
        st = lw(g)[0]
        if not seq or seq[-1][0] != st:
            seq.append([st, round(time.time() - t0, 2)])
        if st in (PROMPT, MENU):
            return ("prompt" if st == PROMPT else "menu"), seq
        time.sleep(POLL)
    return None, seq


def ready(g, label, timeout=W_READY):
    """seconds until the TextButton captioned `label` is visible and not hidden (F12475), or None"""
    t0, hidden_seen = time.time(), False
    while time.time() - t0 < timeout:
        bs = [w for w in lw(g)[1] if bare(w.get("type")) == "TextButton" and w.get("text") == label]
        if bs and bs[0].get("visible") and not bs[0].get("hidden"):
            return round(time.time() - t0, 2), hidden_seen
        hidden_seen = hidden_seen or bool(bs and bs[0].get("hidden"))
        time.sleep(POLL)
    return None, hidden_seen


def press(g, label, leaving):
    """ready, click_widget {match: label.lower()}, then wait <= 10 s for `leaving` to leave the top; returns the evidence"""
    ev = {"label": label}
    ev["ready s"], ev["hidden seen"] = ready(g, label)
    if ev["ready s"] is None:
        ev["error"] = "not ready within %.0f s" % W_READY
        ev["top"] = lw(g)[0]
        return ev
    rep = q(g, {"cmd": "click_widget", "match": label.lower()})
    ev["click"] = {k: rep.get(k) for k in ("ok", "text", "error") if k in rep}
    t0 = time.time()
    while time.time() - t0 < W_LEAVE:
        st = lw(g)[0]
        if st != leaving:
            ev["left s"], ev["top"] = round(time.time() - t0, 2), st
            return ev
        time.sleep(POLL)
    ev["error"], ev["top"] = "%s still on top after %.0f s" % (leaving, W_LEAVE), lw(g)[0]
    return ev


def wait_zip(d):
    t0 = time.time()
    while time.time() - t0 < W_ZIP and not zips(d):
        time.sleep(POLL)
    return zips(d)


class Row:
    def __init__(self, rid, cells):
        self.rid, self.cells, self.res, self.games, self.own, self.pair = rid, cells, {}, [], set(), ()
        self.t0, self.cpu0, self.crash0, self.d = time.time(), cpu_now(), crash_names(), None
        self.ev = {"boots": [], "presses": [], "logs": {}, "rc": []}

    def cell(self, cid, label, ok, seen=None):
        if cid not in self.res:
            self.res[cid] = (bool(ok), label if ok else "%s (seen: %s)" % (label, js(seen)[:300]))

    def rest(self, why, crash_too=False):
        for c in self.cells:
            if c not in self.res and (crash_too or not c.endswith("-crash")):
                self.res[c] = (False, why)

    def boot(self, name, d):
        g = GameClient(name, None, d)
        self.games.append(g)
        t0, b = time.time(), {"name": name}
        self.ev["boots"].append(b)
        try:
            g.spawn()
            g.connect(timeout=W_BOOT)
            t1 = time.time()
            which, seq = settle(g)
        except Exception as e:
            t1, which, seq = time.time(), None, [["error", short(e)]]
        b.update({"spawn->connect s": round(t1 - t0, 2), "connect->settle s": round(time.time() - t1, 2), "settled": which,
                  "tops": seq})
        self.t_boot = (t0, time.time())
        if which is None:
            raise BootMiss(g)
        return g, which

    def shut(self, g):
        if g.proc is None or any(r[0] == g.name for r in self.ev["rc"]):
            return
        err = None
        try:
            g.shutdown()
        except Exception as e:
            err = short(e, 200)
        self.ev["rc"].append([g.name, g.proc.poll(), err])
        self.ev["logs"][g.name] = log_lines(g.user_dir)

    def prompt(self, g, which, cid):
        """the -prompt cell; on a miss every later cell but -crash FAILs "no prompt" (no vacuous pass)"""
        st, ws = lw(g)
        caps = captions(ws)
        self.ev["prompt captions"] = caps
        btn = {b: [c for c in caps if c[0] == "TextButton" and c[1] == b] for b in BUTTONS}
        txt = [c[1] or "" for c in caps if c[0] == "Text"]
        ok = (which == "prompt" and st == PROMPT and all(len(v) == 1 and v[0][2] and v[0][4] for v in btn.values())
              and HEADLINE in txt and any(t.startswith(PROMPT_BODY) for t in txt))
        self.cell(cid, "top %s; BUNDLE / NOT NOW / NEVER once each, visible + interactive; Texts %r and one starting %r"
                  % (PROMPT, HEADLINE, PROMPT_BODY), ok, {"settled": which, "top": st, "captions": caps})
        if not ok:
            self.rest("no prompt (%s failed)" % cid)
        return ok

    def notice(self, g, cid, zs):
        """the BUNDLE result: desync_dialog on the notice, then OK -> MainMenuState"""
        dd = q(g, {"cmd": "desync_dialog"})
        zp, msg = (zs[0] if len(zs) == 1 else None), dd.get("message") or ""
        tgt = dd.get("openFolderTarget") or ""
        chk = {"live": dd.get("live") is True, "headline": dd.get("headline") == HEADLINE,
               "message": msg.startswith(NOTICE_BODY) and bool(dd.get("zipPath")) and dd.get("zipPath") in msg.replace("\n", ""),
               "zipPath": zp is not None and npath(dd.get("zipPath")) == zp,
               "openFolderTarget": zp is not None and npath(tgt) == os.path.dirname(zp)
               and tgt.replace("\\", "/").rstrip("/").endswith("crash-reports"),
               "reportUrl": (dd.get("reportUrl") or "").startswith(ISSUE_URL),
               "buttons": [b.get("text") for b in dd.get("buttons") or []] == NOTICE_BUTTONS, "raiseCount": raises(dd) == 1}
        self.ev["desync_dialog"] = {k: dd.get(k) for k in ("ok", "error", "live", "headline", "message", "zipPath", "openFolderTarget",
                                                           "buttons")}
        self.ev["desync_dialog"].update({"reportUrl": (dd.get("reportUrl") or "")[:120], "last.raiseCount": raises(dd)})
        pe = press(g, "OK", NOTICE)
        self.ev["presses"].append(pe)
        chk["OK -> MainMenuState"] = pe.get("top") == MENU and "error" not in pe
        self.cell(cid, "desync_dialog: live, headline, message holds zipPath, zipPath / openFolderTarget = the zip / its crash-reports "
                  "folder, GitHub issue URL, OK / OPEN FOLDER / REPORT ON GITHUB, last.raiseCount 1; OK -> %s" % MENU,
                  all(chk.values()), [k for k, v in chk.items() if not v])


def zip_ok(z, members, dmp_bytes, source, extra=None):
    info = z.get("info") or {}
    ok = (not z.get("error") and set(members) <= set(z.get("members") or []) and z.get("crash.dmp") == dmp_bytes
          and info.get("source") == source)
    for k, v in (extra or {}).items():
        ok = ok and v
    return ok


def ev_zip(z):
    info = z.get("info") or {}
    return {"path": z.get("path"), "members": z.get("members"), "error": z.get("error"), "report": info.get("report"),
            "source": info.get("source"), "crash": info.get("crash"), "crash.dmp bytes": len(z.get("crash.dmp") or b""),
            "crash-log.txt bytes": len(z.get("crash-log.txt") or b"")}


# ---- rows ----
def row_n0(r):
    d = r.d = make_user_dir("rvu9_n0")
    g, which = r.boot("rvu9-n0", d)
    ts, tset = r.t_boot
    st, led = stack(g), ledger(d)
    r.ev.update({"stack": st, "ledger": led})
    r.cell("N0-menu", "%s; get_state holds no %s" % (MENU, PROMPT), which == "menu" and st[-1:] == [MENU] and PROMPT not in st,
           {"settled": which, "stack": st})
    base = led.get("baseline") if isinstance(led, dict) else None
    ok = (isinstance(led, dict) and isinstance(base, int) and not isinstance(base, bool)
          and ts - 5 <= base <= tset + 5 and led.get("seen") == [])
    r.cell("N0-ledger", "crash-seen.json a JSON object; baseline an integer in [spawn - 5, settle + 5]; seen []", ok,
           {"ledger": led, "spawn": int(ts), "settle": int(tset)})


def marker_row(r, tag, choice):
    d = r.d = make_user_dir("rvu9_" + tag)
    marker = plant_marker(d, MARKER_TS, MARKER_EXC)
    mbytes = read_bytes(marker)
    g, which = r.boot("rvu9-" + tag, d)
    rid = tag.upper()
    if not r.prompt(g, which, rid + "-prompt"):
        return
    pe = press(g, choice, PROMPT)
    r.ev["presses"].append(pe)
    if choice == "BUNDLE":
        zs = wait_zip(d)
        z = zip_read(zs[0]) if len(zs) == 1 else {}
        r.ev["zip"] = ev_zip(z)
        ok = len(zs) == 1 and zip_ok(z, ("crash-info.json", "crash.dmp", "openxcom.log"), DUMP_BYTES, "crashdump-marker",
                                     {"report": (z.get("info") or {}).get("report") == "crash",
                                      "exc": ((z.get("info") or {}).get("crash") or {}).get("exception") == MARKER_EXC})
        r.cell("MB-zip", "BUNDLE: exactly one crash-reports/crash-*.zip within %.0f s holding crash-info.json, crash.dmp (= the planted "
               "dump), openxcom.log; report crash, source crashdump-marker, crash.exception %s" % (W_ZIP, MARKER_EXC), ok,
               {"press": pe, "zips": zs})
        r.cell("MB-marker", "crash-pending.json gone", not os.path.exists(marker), {"marker": os.path.exists(marker)})
        r.notice(g, "MB-notice", [npath(p) for p in zs])
        return
    zs, dd = zips(d), q(g, {"cmd": "desync_dialog"})
    seen = {"press": pe, "marker": os.path.exists(marker), "zips": zs, "last.raiseCount": raises(dd)}
    if choice == "NOT NOW":
        r.cell("MN-keep", "NOT NOW: top %s; the marker present and byte-equal; no zip; last.raiseCount 0" % MENU,
               pe.get("top") == MENU and read_bytes(marker) == mbytes and not zs and raises(dd) == 0, seen)
        return
    r.cell("MV-drop", "NEVER: top %s; the marker gone; no zip; last.raiseCount 0" % MENU,
           pe.get("top") == MENU and not os.path.exists(marker) and not zs and raises(dd) == 0, seen)
    r.shut(g)
    g2, which2 = r.boot("rvu9-mv-2", d)
    st2 = stack(g2)
    r.cell("MV-again", "relaunch of the same folder settles on %s (no prompt)" % MENU, which2 == "menu" and PROMPT not in st2,
           {"settled": which2, "stack": st2})


def dump_row(r, tag, nonce, choice):
    d = r.d = make_user_dir("rvu9_" + tag)
    r.ev["ledger seen at plant"] = write_ledger(d)
    dmp, log = fab_crashlog(nonce)
    r.pair, name = (dmp, log), os.path.basename(dmp)
    r.own = {name, os.path.basename(log)}
    dbytes, lbytes = read_bytes(dmp), read_bytes(log)
    g, which = r.boot("rvu9-" + tag, d)
    rid = tag.upper()
    if not r.prompt(g, which, rid + "-prompt"):
        return
    pe = press(g, choice, PROMPT)
    r.ev["presses"].append(pe)
    led = r.ev["ledger"] = ledger(d)
    sn = led.get("seen") if isinstance(led, dict) else None
    if choice == "BUNDLE":
        zs = wait_zip(d)
        z = zip_read(zs[0]) if len(zs) == 1 else {}
        r.ev["zip"] = ev_zip(z)
        ok = len(zs) == 1 and zip_ok(z, ("crash-info.json", "crash.dmp", "crash-log.txt", "openxcom.log"), dbytes, "veh-crashlog",
                                     {"log": z.get("crash-log.txt") == lbytes})
        r.cell("CB-zip", "BUNDLE: exactly one zip holding crash-info.json, crash.dmp, crash-log.txt (= the fabricated pair's bytes), "
               "openxcom.log; source veh-crashlog", ok, {"press": pe, "zips": zs})
        r.cell("CB-seen", "%s in crash-seen.json seen" % name, isinstance(sn, list) and name in sn, {"seen has it": bool(sn) and name in sn})
        r.notice(g, "CB-notice", [npath(p) for p in zs])
        return
    zs = zips(d)
    seen = {"press": pe, "zips": zs, "in seen": isinstance(sn, list) and name in sn}
    if choice == "NOT NOW":
        r.cell("CN-keep", "NOT NOW: top %s; no zip; %s NOT in seen" % (MENU, name),
               pe.get("top") == MENU and not zs and isinstance(sn, list) and name not in sn, seen)
    else:
        r.cell("CV-drop", "NEVER: top %s; no zip; %s in seen" % (MENU, name),
               pe.get("top") == MENU and not zs and isinstance(sn, list) and name in sn, seen)
    r.shut(g)
    g2, which2 = r.boot("rvu9-%s-2" % tag, d)
    if choice == "NOT NOW":
        r.cell("CN-again", "relaunch of the same folder settles on %s (asked again)" % PROMPT, which2 == "prompt", {"settled": which2})
    else:
        r.cell("CV-again", "relaunch of the same folder settles on %s (no prompt)" % MENU, which2 == "menu", {"settled": which2})


def capture(g, d):
    alive = g is not None and g.proc is not None and g.proc.poll() is None
    st, ws = lw(g) if alive else ("not running (rc %s)" % (g.proc.poll() if g is not None and g.proc else None), [])
    return {"get_state": stack(g) if alive else None, "list_widgets": {"state": st, "captions": captions(ws)},
            "listing": listing(d) if d else None, "openxcom.log tail": log_lines(d, tags=None, n=40) if d else None}


def run_row(rid, cells, fn):
    r = Row(rid, cells)
    try:
        fn(r)
    except BootMiss as e:
        print("CAPTURE %s: %s" % (rid, js(capture(e.args[0], r.d))), flush=True)
        r.rest("boot", crash_too=True)
    except Exception as e:
        r.ev["error"] = short(e, 400)
        r.rest("error: %s" % short(e, 200))
    finally:
        for g in r.games:
            r.shut(g)
        new = sorted(crash_names() - r.crash0 - r.own)
        r.cell(rid + "-crash", "CRASH: no new crash_* file in harness.CRASH_DIR but the row's own pair; every game exited 0",
               not new and all(x[1] == 0 for x in r.ev["rc"]), {"new": new, "rc": r.ev["rc"]})
        for p in r.pair:
            try:
                os.remove(p)
            except OSError as e:
                r.ev.setdefault("pair delete", []).append(short(e, 120))
    r.ev.update({"listing": listing(r.d) if r.d else None, "ledger at end": ledger(r.d) if r.d else None, "own pair": sorted(r.own),
                 "wall s": round(time.time() - r.t0, 1),
                 "cpu %": cpu_pct(r.cpu0, cpu_now())})
    print("EVIDENCE %s: %s" % (rid, js(r.ev)), flush=True)
    for c in cells:
        ok, label = r.res.get(c, (False, "not judged"))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", c, label), flush=True)
    fails = [c for c in cells if not r.res.get(c, (False,))[0]]
    print(("PASS %s" % rid) if not fails else ("FAIL %s: %s" % (rid, " ".join(fails))), flush=True)
    return {c: r.res.get(c, (False,))[0] for c in cells}, r.ev["wall s"]


ROWS = (
    ("N0", ["N0-menu", "N0-ledger", "N0-crash"], row_n0),
    ("MB", ["MB-prompt", "MB-zip", "MB-marker", "MB-notice", "MB-crash"], lambda r: marker_row(r, "mb", "BUNDLE")),
    ("MN", ["MN-prompt", "MN-keep", "MN-crash"], lambda r: marker_row(r, "mn", "NOT NOW")),
    ("MV", ["MV-prompt", "MV-drop", "MV-again", "MV-crash"], lambda r: marker_row(r, "mv", "NEVER")),
    ("CB", ["CB-prompt", "CB-zip", "CB-seen", "CB-notice", "CB-crash"], lambda r: dump_row(r, "cb", 99001, "BUNDLE")),
    ("CN", ["CN-prompt", "CN-keep", "CN-again", "CN-crash"], lambda r: dump_row(r, "cn", 99010, "NOT NOW")),
    ("CV", ["CV-prompt", "CV-drop", "CV-again", "CV-crash"], lambda r: dump_row(r, "cv", 99011, "NEVER")),
)


def main():
    t0, c0, results, walls = time.time(), cpu_now(), {}, {}
    print("[rvu9] slot %d, CRASH_DIR %s (%d crash_* files), exe %s" % (harness.HARNESS_SLOT, harness.CRASH_DIR, len(crash_names()),
                                                                     harness.EXE), flush=True)
    for rid, cells, fn in ROWS:
        try:
            res, walls[rid] = run_row(rid, cells, fn)
        except Exception as e:  # never reached by design; a row that cannot even report fails whole
            print("FAIL %s: row harness error %s" % (rid, short(e, 300)), flush=True)
            res = {c: False for c in cells}
        results.update(res)
    failed = [c for c, ok in results.items() if not ok]
    print("\ntest_crash_reporter: %d/%d cells passed (fail=%s) walls %s in %.1fs, cpu %s %%" % (
        len(results) - len(failed), len(results), failed, js(walls), time.time() - t0, cpu_pct(c0, cpu_now())), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
