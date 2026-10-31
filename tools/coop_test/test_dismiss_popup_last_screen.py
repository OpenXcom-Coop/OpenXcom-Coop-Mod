"""The test server's dismiss_popup never pops the last screen.

dismiss_popup closes a top screen it has no handler for with a raw pop. When that screen is the only one left (a
drain that already closed everything down to the main menu), the pop leaves the game with no screen at all, and the
engine crashes on its next frame. The command must answer an error instead and leave the screen in place.

One machine, no co-op session (label 47981, user dir dismiss_last_screen). Row lone_main_menu:
  guard: the stack is the main menu alone   the boot stack is [MainMenuState]
  refused                                    dismiss_popup answers ok false with an error
  still running                              the game answers get_state at every poll for 1 s after the reply, with the
                                             stack still [MainMenuState], and its process has not exited
  clean shutdown                             the game shuts down with its normal exit code
Prints "EVIDENCE lone_main_menu:" then "PASS lone_main_menu" or "FAIL lone_main_menu: ...".
ONE run; exit 0 iff the row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402

MAIN_MENU = ["MainMenuState"]


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # a dead socket is evidence, not a test error
        return f"<get_state: {type(e).__name__}: {str(e)[:160]}>"


def main():
    t0 = time.time()
    gc = harness.GameClient("dismiss_last_screen", 47981, harness.make_user_dir("dismiss_last_screen"))
    try:
        gc.spawn()
        gc.connect()
    except BaseException:
        harness.shutdown_clients(gc)
        raise
    ev, fails = {}, []

    def cell(name, ok, detail=""):
        if not ok:
            fails.append(f"{name}: {detail}")
        return ok

    try:
        deadline = time.time() + 10.0
        while stack(gc) != MAIN_MENU and time.time() < deadline:
            time.sleep(0.1)
        ev["before"] = stack(gc)
        if cell("guard: the stack is the main menu alone", ev["before"] == MAIN_MENU, ev["before"]):
            try:
                rep = gc.cmd({"cmd": "dismiss_popup"})
            except Exception as e:
                rep = {"exception": f"{type(e).__name__}: {str(e)[:160]}"}
            ev["reply"] = rep
            cell("refused", rep.get("ok") is False and bool(rep.get("error")), rep)
            polls, t1 = [], time.time()
            while time.time() - t1 < 1.0:
                polls.append(stack(gc))
                time.sleep(0.1)
            ev["polls"] = polls
            ev["exited"] = gc.proc.poll() if gc.proc else None
            cell("still running", all(p == MAIN_MENU for p in polls) and ev["exited"] is None,
                 f"polls {polls} exit {ev['exited']}")
    finally:
        try:   # a game that crashed fails its shutdown: evidence, not a test error
            harness.shutdown_clients(gc)
        except Exception as e:
            ev["shutdown"] = f"{type(e).__name__}: {str(e)[:200]}"
    cell("clean shutdown", "shutdown" not in ev, ev.get("shutdown"))
    ev["wall"] = round(time.time() - t0, 1)
    print(f"EVIDENCE lone_main_menu: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    print("PASS lone_main_menu" if not fails else f"FAIL lone_main_menu: {len(fails)} cell(s): " + " | ".join(fails),
          flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
