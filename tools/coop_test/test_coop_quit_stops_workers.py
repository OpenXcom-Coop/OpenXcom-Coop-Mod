"""Quitting stops the co-op worker threads before SDL shuts down.

Every game runs a co-op data-loop thread (connectionTCP::loopData), plus a TCP host
or client thread (startTCPHost / startTCPClient) while a session is up. Nothing
stopped them on quit: Game never deletes its connectionTCP, so the destructor
that sets the stop flags and joins the threads never ran. The threads kept calling
SDL and SDL_net while Game::~Game ran SDL_Quit() and the process went through
exit(). On Linux, where SDL 1.2 is sdl12-compat forwarding into SDL2, the host
intermittently died with SIGSEGV in SDL_SetError (called from SDLNet_TCP_Accept in
startTCPHost) and SDL_Delay (from loopData), both jumping to address 0.

Game::~Game logs which worker threads are still running just before SDL_Quit():

    [coop-shutdown] worker threads running at SDL_Quit: none

This test brings up a Shared session, puts a UFO on the geoscape (the state the
crash was seen in), quits both games through the harness, and asserts that line
reads `none` on both machines. The harness's own exit-code check catches the crash
itself, but only some of the time; the log line is checked on every run.

Run:  python tools/coop_test/test_coop_quit_stops_workers.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

REPORT = "[coop-shutdown] worker threads running at SDL_Quit: "


def _report(user_dir):
    """The worker-thread report the game logged on quit, or None."""
    path = os.path.join(user_dir, "openxcom.log")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [ln for ln in f if REPORT in ln]
    except OSError:
        return None
    return lines[-1].split(REPORT, 1)[1].strip() if lines else None


def main():
    js = shared_fixture.bring_up("jquitworkers", (49266, 49267, 48466))
    host, client = js.host, js.client
    shutdown_error = None
    try:
        b0 = next(b for b in host.ok({"cmd": "geo_state"})["bases"]
                  if not b.get("coopBase") and not b.get("coopIcon"))
        host.ok({"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH",
                 "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID", "trajectory": "P0",
                 "state": "flying", "speed": 1, "detected": False,
                 "lon": b0["lon"] - 1.0, "lat": b0["lat"] + 0.2})
        client.wait_for("client holds the UFO",
                        lambda: client.ok({"cmd": "geo_state"})["ufos"] or None,
                        timeout=30, interval=0.3)
        print("PASS setup: Shared session up, one UFO on both geoscapes")
    finally:
        # Quit both games (host first, as every test does). A crash on quit makes
        # this raise; the logs are checked first so the report says why.
        try:
            js.shutdown()
        except RuntimeError as exc:
            shutdown_error = exc

    for name, user_dir in (("host", js.host_dir), ("client", js.client_dir)):
        running = _report(user_dir)
        assert running is not None, \
            f"{name}: no '{REPORT.strip()}' line in its log - the shutdown never reported its worker threads"
        assert running == "none", \
            f"{name}: co-op worker threads still running at SDL_Quit: {running}"
        print(f"PASS {name}: no co-op worker thread running at SDL_Quit")

    if shutdown_error is not None:
        raise shutdown_error
    print("PASS exit: both games exited with code 0")
    print("ALL QUIT-STOPS-WORKERS TESTS PASSED")


if __name__ == "__main__":
    main()
