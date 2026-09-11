"""issue #124: a crash must produce a minidump (and a log recording the mods).

The reporter's heap-corruption crash produced a crash .log but NO .dmp, because
the crash handler only wrote a dump for a hand-maintained whitelist of exception
codes (0xC0000374 was not on it). The dump policy is now: dump for ANY exception
the crash handler writes a log for. This test proves it end to end - it forces a
real fault and asserts a fresh crash_*.dmp appears, alongside a crash_*.log whose
header records the active mod list.

Run:  python tools/coop_test/test_crash_produces_dump.py
"""

import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir

PORT = 48971
# The Windows fixture exits 3; 0xC0000005 is the fault recorded in its crash log,
# not the process exit code. POSIX signalLogger exits with EXIT_FAILURE.
CRASH_RETURN_CODE = 3 if os.name == "nt" else 1


def _dmps(d):
    return set(f for f in os.listdir(d)
              if f.startswith("crash_") and f.endswith(".dmp")) if os.path.isdir(d) else set()


def _newest_crashlog(d):
    logs = [os.path.join(d, f) for f in os.listdir(d)
            if f.startswith("crash_") and f.endswith(".log")]
    return max(logs, key=os.path.getmtime) if logs else None


def main():
    gc = GameClient("host", PORT, make_user_dir("crashdump"))
    gc.spawn()
    crash_requested = False
    try:
        gc.connect()
        crash_dir = gc.ok({"cmd": "crashlog_probe"})["dir"]
        assert crash_dir and os.path.isdir(crash_dir), f"bad crash dir: {crash_dir!r}"
        before = _dmps(crash_dir)

        # Force a real access violation. The response never arrives - the process
        # faults inside the command handler - so a dropped socket IS the success path.
        crashed = False
        try:
            crash_requested = True
            gc.cmd({"cmd": "force_crash"})
        except (ConnectionError, OSError, socket.timeout):
            crashed = True
        # give the in-thread minidump write + process teardown a moment.
        returncode = gc.proc.wait(timeout=20)
        assert returncode == CRASH_RETURN_CODE, f"unexpected crash exit: {returncode}"
        assert crashed or gc.proc.poll() is not None, "force_crash did not bring the process down"
        print("PASS: instance faulted as intended")

        # a fresh minidump must have been written for this (previously non-dumping) crash.
        new = None
        for _ in range(20):
            added = _dmps(crash_dir) - before
            if added:
                new = added
                break
            time.sleep(0.5)
        assert new, (f"NO new crash_*.dmp after the fault (dump policy regressed): "
                     f"dir={crash_dir} before={len(before)} now={len(_dmps(crash_dir))}")
        print(f"PASS: crash produced a minidump: {sorted(new)}")

        log = _newest_crashlog(crash_dir)
        assert log, "no crash log written"
        text = open(log, "r", encoding="utf-8", errors="replace").read()
        assert "Mods:" in text and "xcom1" in text, \
            f"crash log missing the mod list:\n{text[:600]}"
        if os.name == "nt":
            assert "Code = 0xC0000005" in text, f"wrong intentional fault:\n{text}"
        print("PASS: crash log records the mod list")
        print("CRASH-PRODUCES-DUMP TEST PASSED")
    finally:
        gc.shutdown(expected_returncodes=(CRASH_RETURN_CODE,) if crash_requested else (0,))


if __name__ == "__main__":
    main()
