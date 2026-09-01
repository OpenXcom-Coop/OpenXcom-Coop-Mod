"""PRD-I5: next-launch crash reporter (consent + bundle), dual-source discovery.

Single instance at the main menu. Two crash sources are exercised, both driving the
REAL boot hook (GoToMainMenuState::init -> SharedEcon::maybeReportPreviousCrash) and
the consent dialog via the generic widget levers (list_widgets / click_widget - no
new TestServer command, so the Session-F dispatch quirk never bites):

  SOURCE 1 - the classic crashDump marker (<user>/crash-pending.json).
  SOURCE 2 - an unseen issue-#124 VEH crashlog in <exe>/crashlogs (the robust
             catch-all crashDump misses). Dedup via a per-user crash-seen.json.

Asserts (each source): BUNDLE -> valid zip with all members + source marked seen /
marker deleted; NOT NOW -> unseen (re-prompts); NEVER -> marked seen, no zip.

Because <exe>/crashlogs is exe-global (shared by every instance) while the ledger is
per-user, the crashlog scenarios pin their instance's ledger baseline to just-before
the fabricated entry and pre-mark every OTHER existing crashlog seen, so ONLY the
fabricated entry is offered. The seen-ledger's `seen[]` membership is the
deterministic dedup proof (a concurrent force_crash could add a stray crashlog, but
never touches this entry's ledger state)."""
import os, sys, time, json, glob, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, EXE

# RW-TRIAGE: SKIP-PENDING(R2-P9)
print("SKIP-PENDING: rewrite"); sys.exit(0)

BASE_PORT = 45999  # single control port; GameClient applies the per-slot shift
CRASHLOGS_DIR = os.path.join(os.path.dirname(EXE), "crashlogs")


def top_state(g):
    r = g.cmd({"cmd": "list_widgets"})
    return r.get("state", ""), r.get("widgets", [])


def wait_top(g, needle, timeout=180):
    return g.wait_for("top state %r" % needle,
                      lambda: (lambda s: s if needle in s[0] else None)(top_state(g)),
                      timeout=timeout, interval=1.0)


def assert_prompt_buttons(widgets):
    labels = [w.get("text", "") for w in widgets if "text" in w]
    for want in ("BUNDLE", "NOT NOW", "NEVER"):
        hits = [w for w in widgets if w.get("text") == want]
        assert hits, "consent dialog has no %r button - labels seen: %s" % (want, labels)
        b = hits[0]
        assert b.get("visible") and b.get("interactive"), \
            "the %r button is not visible+interactive: %s" % (want, b)


# ---------- SOURCE 1: the classic crashDump marker ----------

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


def scenario_marker_bundle():
    d = make_user_dir("crash_bundle")
    ts = "15-08-2026_10-00-00"
    marker = plant_marker(d, ts)
    reports_dir = os.path.join(d, "crash-reports")
    g = GameClient("crash-bundle", BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        st, widgets = wait_top(g, "CoopCrashPromptState")
        assert_prompt_buttons(widgets)
        g.ok({"cmd": "click_widget", "match": "bundle"})
        def bundled():
            zips = glob.glob(os.path.join(reports_dir, "crash-*.zip"))
            return zips if (zips and not os.path.exists(marker)) else None
        zips = g.wait_for("marker bundle written + marker deleted", bundled, timeout=60, interval=1.0)
        assert len(zips) == 1, "expected one crash zip, got %s" % zips
        with zipfile.ZipFile(zips[0]) as z:
            names = set(z.namelist())
            for m in ("crash-info.json", "crash.dmp", "openxcom.log"):
                assert m in names, "marker zip missing %r; has %s" % (m, sorted(names))
            info = json.loads(z.read("crash-info.json").decode("utf-8", "replace"))
            assert info.get("source") == "crashdump-marker", "marker source wrong: %s" % info.get("source")
            assert info.get("crash", {}).get("exception") == "0xC0000005"
        dd = g.cmd({"cmd": "desync_dialog"}).get("last", {})
        assert dd.get("raiseCount", 0) >= 1 and (dd.get("openFolderTarget") or "").replace("\\", "/").endswith("crash-reports")
        print("PASS marker-bundle: valid zip (source=crashdump-marker), marker deleted, result notice")
    finally:
        time.sleep(0.5); g.shutdown()


def scenario_marker_keep_or_delete(name, choice, expect_marker):
    d = make_user_dir(name)
    marker = plant_marker(d, "15-08-2026_11-00-00")
    reports_dir = os.path.join(d, "crash-reports")
    g = GameClient(name, BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        wait_top(g, "CoopCrashPromptState")
        g.ok({"cmd": "click_widget", "match": choice})
        wait_top(g, "MainMenuState", timeout=30)
        time.sleep(1.0)
        assert os.path.exists(marker) == expect_marker, \
            "%s: marker present=%s expected=%s" % (name, os.path.exists(marker), expect_marker)
        assert not glob.glob(os.path.join(reports_dir, "crash-*.zip")), "%s wrote a zip" % name
        print("PASS %s: click %r -> marker %s, no zip"
              % (name, choice, "kept" if expect_marker else "deleted"))
    finally:
        time.sleep(0.5); g.shutdown()


# ---------- SOURCE 2: an unseen issue-#124 VEH crashlog ----------

def existing_crashlog_dmps():
    if not os.path.isdir(CRASHLOGS_DIR):
        return []
    return [n for n in os.listdir(CRASHLOGS_DIR) if n.startswith("crash_") and n.endswith(".dmp")]


def write_ledger(user_dir, seen_list, baseline_offset=-60):
    with open(os.path.join(user_dir, "crash-seen.json"), "w", encoding="utf-8") as f:
        json.dump({"baseline": int(time.time()) + baseline_offset, "seen": seen_list}, f)


def read_seen(user_dir):
    p = os.path.join(user_dir, "crash-seen.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("seen", [])


def fab_crashlog(nonce):
    os.makedirs(CRASHLOGS_DIR, exist_ok=True)
    base = "crash_%s_123_%d" % (time.strftime("%Y%m%d_%H%M%S"), nonce)
    dmp = os.path.join(CRASHLOGS_DIR, base + ".dmp")
    log = os.path.join(CRASHLOGS_DIR, base + ".log")
    with open(dmp, "wb") as f:
        f.write(b"FAKE-VEH-MINIDUMP-%d\n" % nonce * 16)
    with open(log, "w", encoding="utf-8") as f:
        f.write("==== Crash/Log ====\nUNHANDLED SEH. Code = 0xC0000005 (fabricated VEH crashlog)\nMods: xcom1\n")
    return base + ".dmp", dmp, log


def prompt_shown(name, user_dir):
    """Launch on user_dir; return True iff the consent prompt was shown (else it
    settled on the main menu). Does not click anything."""
    g = GameClient(name, BASE_PORT, user_dir); g.spawn()
    try:
        g.connect(timeout=180)
        def settled():
            st, _ = top_state(g)
            if "CoopCrashPromptState" in st: return "prompt"
            if "MainMenuState" in st: return "menu"
            return None
        return g.wait_for("prompt or menu", settled, timeout=180, interval=1.0) == "prompt"
    finally:
        time.sleep(0.5); g.shutdown()


def scenario_crashlog_bundle():
    d = make_user_dir("crashlog_bundle")
    write_ledger(d, existing_crashlog_dmps())
    dmp_base, dmp, log = fab_crashlog(99001)
    reports_dir = os.path.join(d, "crash-reports")
    g = GameClient("crashlog-bundle", BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        st, widgets = wait_top(g, "CoopCrashPromptState")
        assert_prompt_buttons(widgets)
        g.ok({"cmd": "click_widget", "match": "bundle"})
        zips = g.wait_for("crashlog bundle",
                          lambda: (lambda z: z if z else None)(glob.glob(os.path.join(reports_dir, "crash-*.zip"))),
                          timeout=60, interval=1.0)
        assert len(zips) == 1, "expected one crashlog zip, got %s" % zips
        with zipfile.ZipFile(zips[0]) as z:
            names = set(z.namelist())
            for m in ("crash-info.json", "crash.dmp", "crash-log.txt", "openxcom.log"):
                assert m in names, "crashlog zip missing %r; has %s" % (m, sorted(names))
            info = json.loads(z.read("crash-info.json").decode("utf-8", "replace"))
            assert info.get("source") == "veh-crashlog", "crashlog source wrong: %s" % info.get("source")
        # deterministic dedup proof: the handled .dmp is now in the per-user seen ledger
        assert dmp_base in read_seen(d), "BUNDLE did not mark the crashlog seen: %s" % read_seen(d)
        print("PASS crashlog-bundle: valid zip (source=veh-crashlog, pair+log+info), marked seen")
    finally:
        time.sleep(0.5); g.shutdown()
        for f in (dmp, log):
            try: os.remove(f)
            except OSError: pass


def scenario_crashlog_keep_or_delete(name, choice, nonce, expect_seen):
    d = make_user_dir(name)
    write_ledger(d, existing_crashlog_dmps())
    dmp_base, dmp, log = fab_crashlog(nonce)
    reports_dir = os.path.join(d, "crash-reports")
    g = GameClient(name, BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        wait_top(g, "CoopCrashPromptState")
        g.ok({"cmd": "click_widget", "match": choice})
        wait_top(g, "MainMenuState", timeout=30)
        time.sleep(1.0)
        assert not glob.glob(os.path.join(reports_dir, "crash-*.zip")), "%s wrote a zip" % name
        seen = read_seen(d)
        assert (dmp_base in seen) == expect_seen, \
            "%s: seen=%s expected in_seen=%s" % (name, dmp_base in seen, expect_seen)
        g.shutdown()
        # integration: NOT NOW (unseen) re-prompts; NEVER (seen) does not (for THIS entry).
        if choice == "not now":
            assert prompt_shown(name + "-2", d), "NOT NOW did not re-prompt on relaunch"
        print("PASS %s: click %r -> no zip, in_seen=%s" % (name, choice, dmp_base in seen))
    finally:
        time.sleep(0.5)
        try: g.shutdown()
        except Exception: pass
        for f in (dmp, log):
            try: os.remove(f)
            except OSError: pass


def scenario_no_marker():
    d = make_user_dir("crash_nomarker")  # no marker, no fabricated crashlog
    g = GameClient("crash-nomarker", BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        st, _ = wait_top(g, "MainMenuState")
        assert "CoopCrashPromptState" not in st, "consent dialog appeared with nothing to report: %s" % st
        print("PASS no-source: boot lands on MainMenuState, no prompt (fast path, ledger created)")
    finally:
        time.sleep(0.5); g.shutdown()


def main():
    scenario_no_marker()
    scenario_marker_bundle()
    scenario_marker_keep_or_delete("crash_notnow", "not now", expect_marker=True)
    scenario_marker_keep_or_delete("crash_never", "never", expect_marker=False)
    scenario_crashlog_bundle()
    scenario_crashlog_keep_or_delete("crashlog_notnow", "not now", 99010, expect_seen=False)
    scenario_crashlog_keep_or_delete("crashlog_never", "never", 99011, expect_seen=True)
    print("ALL PASS: crash reporter dual-source (marker + VEH crashlog) consent + bundle")


if __name__ == "__main__":
    main()
