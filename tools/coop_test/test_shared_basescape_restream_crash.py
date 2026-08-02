"""issue #124: SHARED client crashes deleting a BasescapeState after a world restream.

EXACT crash (byte-identical symbolication of the reporter's nightly 57cdf069c):
    Game::run (Game.cpp:201, deferred state delete)
      -> BasescapeState::~BasescapeState
        -> delete _base  (Base : Target)
          -> free -> 0xC0000374 (heap corruption / double free)

ROOT CAUSE: ~BasescapeState frees _base whenever _base is not found in
getSavedGame()->getBases() (its "temporary base" heuristic, BasescapeState.cpp:275).
In a SHARED campaign the post-mission world RESTREAM replaces the whole SavedGame
(Game::setSavedGame does `delete _save`, freeing the old Base objects and building
new ones). A BasescapeState that was open across that restream now holds a _base
pointing at an ALREADY-FREED old Base that is no longer in the (new) base list, so
the heuristic misfires and `delete _base` double-frees it.

The reporter hit this by opening the base/purchase screen after a mission (the
post-battle restream) on a UDP session, but the transport is incidental - this
reproduces over plain TCP.

Repro: client opens the base screen -> force a world restream (force_resync) ->
the stale BasescapeState is torn down -> pre-fix the client crashes; post-fix it
survives.

Run:  python tools/coop_test/test_shared_basescape_restream_crash.py
Exit 0 = pass (fixed); 2 = the crash reproduced (unfixed).
"""

import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session


def _alive(gc):
    if gc.proc and gc.proc.poll() is not None:
        return False
    try:
        return bool(gc.cmd({"cmd": "ping"}).get("pong"))
    except (ConnectionError, OSError, socket.timeout):
        return False


def _states(gc):
    try:
        return gc.cmd({"cmd": "get_state"})["states"]
    except (ConnectionError, OSError, socket.timeout):
        return None


def _resync_reqs(gc):
    return gc.ok({"cmd": "shared_resync_stats"}).get("requests", 0)


def main():
    js = shared_fixture.bring_up("jbasecrash", (48974, 48975, 48274))
    host, client = js.host, js.client
    try:
        # 1) client opens the base management screen (BasescapeState), _base = a real base.
        r = client.ok({"cmd": "open_screen", "screen": "basescape"})
        assert r.get("ok"), f"open_screen basescape failed: {r}"
        st = _states(client)
        assert st and any("BasescapeState" in s for s in st), \
            f"BasescapeState not on the client stack: {st}"
        print(f"PASS setup: client has a BasescapeState open (top={st[-1]})")

        # 2) force a whole-world restream: the host re-serializes and streams its world,
        #    the client adopts it via setSavedGame(new) - freeing the old Base that the
        #    open BasescapeState still points at.
        reqs0 = _resync_reqs(client)
        crashed_during = False
        try:
            client.ok({"cmd": "force_resync"})
            # let the restream land + the client adopt the new world (and tear down /
            # re-stack states around the adoption).
            client.wait_for("client asked for + received the restream",
                            lambda: (_resync_reqs(client) > reqs0) or None,
                            timeout=30, interval=0.5)
            time.sleep(2.0)
        except (ConnectionError, OSError, socket.timeout) as e:
            crashed_during = True
            err = str(e)

        # 3) close the (now stale) base screen - this is where ~BasescapeState runs.
        crashed_close = False
        if not crashed_during:
            try:
                client.cmd({"cmd": "close_screens"})
                time.sleep(1.0)
            except (ConnectionError, OSError, socket.timeout) as e:
                crashed_close = True
                err = str(e)

        if crashed_during or crashed_close or not _alive(client):
            where = "during restream adoption" if crashed_during else "tearing down BasescapeState"
            raise AssertionError(
                f"issue #124 REPRODUCED: client crashed {where} - ~BasescapeState "
                f"double-freed a _base the world restream had already freed "
                f"(Game.cpp:201 -> ~BasescapeState -> delete _base -> 0xC0000374)")

        assert _alive(host), "host crashed"
        print("PASS: client survived the restream + BasescapeState teardown")

        # sanity: worlds still converge and both are responsive.
        js.finish(timeout=90)
        print("BASESCAPE-RESTREAM CRASH TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"[REPRO] {e}")
        sys.exit(2)
