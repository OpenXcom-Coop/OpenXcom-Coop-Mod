"""Issue #91, second door into the same dead end: a `request_load_progress`
restream arms NO release at all.

test_shared_resync_storm.py pins the ONE-SHOT release flag. This test pins the
other half of the same missing invariant: the third site that streams the
authoritative world mid-session,

    connectionTCP.cpp:3787   if (savedGame && !sendFileClient && isSharedCampaign())
                                 streamSharedWorldToClient();

sets neither sharedResyncRestream nor sharedPostBattleRestream. Its release is a
HUMAN: the host's COOP_DLG_WAIT_PLAYERS turns into RESUME once resume_ack lands
and that click sends campaign_begun (CoopState.cpp:1168). The client, though,
parks in COOP_DLG_CLIENT_RESUME_HOLD (68) for EVERY streamed world it adopts
(LoadGameState.cpp:305) - so when this packet is served while the host has no wait
dialog on its stack, the client holds a perfectly good world behind a buttonless,
timeout-less dialog and nothing on either machine will ever release it.

HOW A PLAYER GETS THERE (no wait dialog, live session)
  * the bounded retry at CoopState.cpp:1010 - the host answered "busy" (its
    single-slot streamer was mid-transfer) and the client re-asks for up to ~30s.
    The host can well have finished its own resume and popped the dialog by then.
  * a drop the host never classified as one (onConnect != -2), so the freeze
    dialog at connectionTCP.cpp:10714 was never pushed, followed by the client's
    join asking for the world (Profile.cpp:141).

The harness sends exactly the packet those paths send (`client_reload_progress` is
the client branch of Profile::buttonOK) with the host settled on its geoscape.

  ASSERT  the client is released, and the host's log carries a release for the
          restream it served. Today: neither.

Expected result TODAY: fails - client parked in dialog 68, host on GeoscapeState.

Run:  python tools/coop_test/test_shared_reload_hold.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import geo

COOP_DLG_CLIENT_RESUME_HOLD = 68
STREAM_LINE = "[coop-shared] streaming authoritative world to client"
RELEASE_LINE = "restream adopted; released the client hold"


def _coop(gc):
    return gc.ok({"cmd": "get_coop"})


def _held(gc):
    return _coop(gc)["coopDialog"] == COOP_DLG_CLIENT_RESUME_HOLD


def _log_tail(user_dir, offset):
    with open(os.path.join(user_dir, "openxcom.log"), "r",
              encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        return f.read()


def main():
    js = shared_fixture.bring_up("j91r", (49028, 49029, 48328))
    host, client = js.host, js.client
    try:
        geo.slow_clock(host, client)
        geo.drain_popups(host)
        geo.drain_popups(client)

        # The precondition that makes this a bug and not a handshake: the host is
        # on its geoscape with no wait dialog, so there is no RESUME to click.
        assert _coop(host)["coopDialog"] == -1, \
            f"host already has a coop dialog: {_coop(host)}"
        assert geo.on_geoscape(host), f"host not on the geoscape: {geo.top_state(host)}"
        assert _coop(client)["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD, \
            "client held before the test even started"
        print("PASS setup: session live, host on the geoscape with no wait dialog")

        log = os.path.join(js.host_dir, "openxcom.log")
        offset = os.path.getsize(log)

        # Exactly the packet Profile::buttonOK's client branch sends.
        client.ok({"cmd": "client_reload_progress"})
        host.wait_for("host streamed the authoritative world",
                      lambda: (STREAM_LINE in _log_tail(js.host_dir, offset)) or None,
                      timeout=60, interval=0.5)
        print("PASS serve: host streamed its world for the reload request")

        # The client parks in dialog 68 for every streamed world it adopts
        # (LoadGameState.cpp:305), but do NOT gate on seeing it: a working host
        # releases it within a think gate or two, which a poll can miss entirely
        # (it did, on CI). What must be true is the OUTCOME - the client is not
        # left holding, and the host sent a release for the world it streamed.
        held_seen = False
        released = False
        deadline = time.time() + 45
        while time.time() < deadline:
            if _held(client):
                held_seen = True
            elif RELEASE_LINE in _log_tail(js.host_dir, offset):
                released = True
                break
            time.sleep(0.25)

        if not released:
            tail = _log_tail(js.host_dir, offset)
            raise AssertionError(
                "ISSUE #91 (second door) REPRODUCED: the client adopted a world "
                "streamed by the request_load_progress path, which arms no release "
                "flag (connectionTCP.cpp:3787), and the host has no wait dialog to "
                "turn into a RESUME - so no campaign_begun exists to be sent. The "
                "client is stranded in COOP_DLG_CLIENT_RESUME_HOLD "
                f"({_coop(client)['coopDialog']}) - \"Waiting for host to resume the "
                "game.\" - with no button and no timeout, while the host sits on "
                f"{geo.top_state(host)}. Host log since the request: "
                f"{tail.count(STREAM_LINE)} restream(s), "
                f"{tail.count(RELEASE_LINE)} release(s).\n"
                f"  client={_coop(client)}\n  host={_coop(host)}")

        tail = _log_tail(js.host_dir, offset)
        assert tail.count(RELEASE_LINE) >= tail.count(STREAM_LINE), (
            f"host served {tail.count(STREAM_LINE)} restream(s) but sent only "
            f"{tail.count(RELEASE_LINE)} release(s)")
        assert not _held(client), (
            "the host sent a release but the client is still holding: "
            f"{_coop(client)}")
        print(f"PASS release: host released the adopted world and the client is not "
              f"holding (dialog={_coop(client)['coopDialog']}, "
              f"hold observed in flight: {held_seen})")

        js.finish()
        print("ALL SHARED RELOAD HOLD TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
