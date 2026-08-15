"""PRD-I5: next-launch crash reporter (consent + bundle).

Not a two-instance coop test - a single instance at the main menu. We fabricate a
crash-pending.json (plus a dummy dump + a stub log) in a harness user dir BEFORE
launch, then let the REAL boot hook (GoToMainMenuState::init ->
SharedEcon::maybeReportPreviousCrash) fire and drive the consent dialog through the
generic widget levers (list_widgets / click_widget - no new TestServer command, so
the Session-F top-level-dispatch quirk never bites). Asserts:

  BUNDLE  -> a valid <user>/crash-reports/crash-<ts>.zip with all members, the
             marker gone, and the CoopDesyncNoticeState result raised (path + OPEN
             FOLDER at crash-reports + a prefilled GitHub url);
  NOT NOW -> the marker is KEPT (would ask again next launch), no zip;
  NEVER   -> the marker is DELETED, no zip;
  no marker -> boot lands straight on MainMenuState (the O(1)-stat fast path).
"""
import os, sys, time, json, glob, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir

BASE_PORT = 45999  # single control port; GameClient applies the per-slot shift


def top_state(g):
    r = g.cmd({"cmd": "list_widgets"})
    return r.get("state", ""), r.get("widgets", [])


def wait_top(g, needle, timeout=180):
    return g.wait_for(
        "top state %r" % needle,
        lambda: (lambda s: s if needle in s[0] else None)(top_state(g)),
        timeout=timeout, interval=1.0)


def plant_marker(user_dir, ts, exc="0xC0000005"):
    """Write crash-pending.json + a dummy dump + a stub log into user_dir, exactly
    as CrossPlatform::crashDump would (full paths, JSON). Returns (marker, dump, log)."""
    dump = os.path.join(user_dir, ts + ".dmp")
    log = os.path.join(user_dir, "openxcom.log")
    with open(dump, "wb") as f:
        f.write(b"FAKE-MINIDUMP-CONTENT-FOR-I5-TEST\n" * 32)
    if not os.path.exists(log):  # the game will append its own boot log to this
        with open(log, "w", encoding="utf-8") as f:
            f.write("stub openxcom.log planted by test_crash_reporter\n")
    marker = os.path.join(user_dir, "crash-pending.json")
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "dump": dump, "log": log,
                   "version": "Extended 8.4.2 (i5-test)", "exception": exc}, f, indent=2)
    return marker, dump, log


def assert_prompt_buttons(widgets):
    labels = [w.get("text", "") for w in widgets if "text" in w]
    for want in ("BUNDLE", "NOT NOW", "NEVER"):
        hits = [w for w in widgets if w.get("text") == want]
        assert hits, "consent dialog has no %r button - labels seen: %s" % (want, labels)
        b = hits[0]
        assert b.get("visible") and b.get("interactive"), \
            "the %r button is not visible+interactive: %s" % (want, b)


def scenario_bundle():
    d = make_user_dir("crash_bundle")
    ts = "15-08-2026_10-00-00"
    marker, dump, log = plant_marker(d, ts)
    reports_dir = os.path.join(d, "crash-reports")
    g = GameClient("crash-bundle", BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        st, widgets = wait_top(g, "CoopCrashPromptState")
        assert_prompt_buttons(widgets)
        print("PASS bundle-1: consent dialog raised with BUNDLE / NOT NOW / NEVER")

        g.ok({"cmd": "click_widget", "match": "bundle"})
        # Poll for the on-disk proof: a zip appeared and the marker is gone.
        def bundled():
            zips = glob.glob(os.path.join(reports_dir, "crash-*.zip"))
            return zips if (zips and not os.path.exists(marker)) else None
        zips = g.wait_for("crash bundle written + marker deleted", bundled,
                          timeout=60, interval=1.0)
        assert len(zips) == 1, "expected exactly one crash zip, got %s" % zips
        zp = zips[0]

        # The zip is valid and carries every member.
        with zipfile.ZipFile(zp) as z:
            names = set(z.namelist())
            for m in ("crash-info.json", "crash.dmp", "openxcom.log"):
                assert m in names, "crash zip missing member %r; has %s" % (m, sorted(names))
            info = json.loads(z.read("crash-info.json").decode("utf-8", "replace"))
            assert info.get("report") == "crash", "crash-info.json report != crash: %s" % info
            assert info.get("build", {}).get("version"), "crash-info.json has no build.version"
            assert isinstance(info.get("mods"), list), "crash-info.json mods is not a list"
            assert info.get("crash", {}).get("exception") == "0xC0000005", \
                "crash-info.json did not echo the marker exception: %s" % info.get("crash")
            assert len(z.read("crash.dmp")) > 0, "bundled dump is empty"
        assert not os.path.exists(marker), "marker survived a successful bundle"
        print("PASS bundle-2: valid zip (crash-info.json + crash.dmp + openxcom.log), "
              "marker deleted -> %s" % os.path.basename(zp))

        # The I4 result dialog carries the crash path + one-click UX.
        dd = g.cmd({"cmd": "desync_dialog"})
        last = dd.get("last", {})
        assert last.get("raiseCount", 0) >= 1, "no result notice was ever raised: %s" % dd
        zpath = (last.get("zipPath") or "").replace("\\", "/")
        assert zpath.endswith(os.path.basename(zp)), \
            "result notice zipPath %r != the zip we found %r" % (zpath, zp)
        target = (last.get("openFolderTarget") or "").replace("\\", "/")
        assert target.endswith("crash-reports"), "OPEN FOLDER target not crash-reports: %r" % target
        url = last.get("reportUrl", "")
        assert url.startswith("https://github.com/OpenXcom-Coop/OpenXcom-Coop-Mod/issues/new") \
            and "title=" in url and "body=" in url, "result notice report url wrong: %r" % url
        print("PASS bundle-3: result notice shows the path + OPEN FOLDER (crash-reports) "
              "+ prefilled GitHub url")
    finally:
        time.sleep(0.5)
        g.shutdown()


def scenario_keep_or_delete(name, choice, expect_marker):
    d = make_user_dir(name)
    ts = "15-08-2026_11-00-00"
    marker, dump, log = plant_marker(d, ts)
    reports_dir = os.path.join(d, "crash-reports")
    g = GameClient(name, BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        wait_top(g, "CoopCrashPromptState")
        g.ok({"cmd": "click_widget", "match": choice})
        # The prompt pops back to the menu (no result dialog on this branch).
        wait_top(g, "MainMenuState", timeout=30)
        time.sleep(1.0)  # let any (unexpected) deferred bundle settle
        present = os.path.exists(marker)
        assert present == expect_marker, \
            "%s: marker present=%s but expected present=%s" % (name, present, expect_marker)
        zips = glob.glob(os.path.join(reports_dir, "crash-*.zip"))
        assert not zips, "%s must not write a crash zip, found %s" % (name, zips)
        print("PASS %s: click %r -> marker %s, no zip"
              % (name, choice, "kept" if expect_marker else "deleted"))
    finally:
        time.sleep(0.5)
        g.shutdown()


def scenario_no_marker():
    d = make_user_dir("crash_nomarker")  # deliberately NO crash-pending.json
    g = GameClient("crash-nomarker", BASE_PORT, d)
    g.spawn()
    try:
        g.connect(timeout=180)
        st, _ = wait_top(g, "MainMenuState")
        assert "CoopCrashPromptState" not in st, \
            "consent dialog appeared with no marker present: %s" % st
        assert not os.path.exists(os.path.join(d, "crash-reports")), \
            "a crash-reports dir was created with no marker"
        print("PASS no-marker: boot lands on MainMenuState, no prompt (O(1) fast path)")
    finally:
        time.sleep(0.5)
        g.shutdown()


def main():
    scenario_no_marker()
    scenario_bundle()
    scenario_keep_or_delete("crash_notnow", "not now", expect_marker=True)
    scenario_keep_or_delete("crash_never", "never", expect_marker=False)
    print("ALL PASS: crash reporter consent + bundle (BUNDLE / NOT NOW / NEVER / no-marker)")


if __name__ == "__main__":
    main()
