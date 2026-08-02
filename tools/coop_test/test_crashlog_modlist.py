"""issue #124 groundwork: the crash log now records the active mod list.

Mod-specific crashes (like the reported UDP heap corruption) can't be reproduced
without knowing which mods were loaded, and a minidump doesn't capture the game's
mod list. So Options::updateMods() now snapshots the active mods into the crash
handler, and every crash log prints a "Mods:" line.

This test writes a probe crash log through the real CrashHandler::log path and
asserts the header records the active master mod.

Run:  python tools/coop_test/test_crashlog_modlist.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir

PORT = 48970


def _newest_crashlog(d):
    if not os.path.isdir(d):
        return None
    logs = [os.path.join(d, f) for f in os.listdir(d)
            if f.startswith("crash_") and f.endswith(".log")]
    return max(logs, key=os.path.getmtime) if logs else None


def main():
    gc = GameClient("host", PORT, make_user_dir("crashmods"))
    gc.spawn()
    try:
        gc.connect()
        r = gc.ok({"cmd": "crashlog_probe", "note": "modlist-verify-probe"})
        d = r.get("dir")
        assert d, f"crashlog_probe returned no dir: {r}"

        log = _newest_crashlog(d)
        assert log, f"no crash_*.log written under {d!r}"
        text = open(log, "r", encoding="utf-8", errors="replace").read()

        mods_line = next((ln for ln in text.splitlines() if ln.startswith("Mods:")), None)
        assert mods_line is not None, (
            f"crash log has no 'Mods:' line (mod list not recorded):\n{text[:600]}")
        # the hermetic harness pins the stock xcom1 master, so it MUST appear.
        assert "xcom1" in mods_line, f"active master not recorded in: {mods_line!r}"
        assert "(not captured)" not in mods_line, (
            "mod list was never snapshotted (Options::updateMods hook not wired)")
        assert "modlist-verify-probe" in text, "probe note missing (wrong log matched)"

        print(f"PASS: crash log records the mod list -> {mods_line!r}")
        print("CRASHLOG MODLIST TEST PASSED")
    finally:
        gc.shutdown()


if __name__ == "__main__":
    main()
