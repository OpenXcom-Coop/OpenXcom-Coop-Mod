"""PRD-J10: desync detection is upgraded from log-only (J04) to automatic repair.

The host stamps a world checksum (funds + base count + discovered tech) onto the
periodic geoscape `time` heartbeat. J04 logged a mismatch and moved on. J10 makes
the replica ASK for a fresh world (shared_resync_request); the host re-streams the
authoritative world down the J02 bootstrap lane AND releases the client's resume
hold, and the replica adopts it whole.

  DETECT   corrupt the replica's funds directly (set_funds on the client only) ->
           the next checksum mismatches, the replica requests a resync, the host
           re-streams, and the replica's funds match the host's again.
  RELEASE  the repaired client must NOT be parked in COOP_DLG_CLIENT_RESUME_HOLD
           (68). LoadGameState holds EVERY client that adopts a streamed world
           until a campaign_begun arrives, and mid-session nobody clicks BEGIN -
           this is the deadlock PRD-J09 hit after battles. Asserted explicitly.
  LIVE     after the repair the session still works: a client buy still round-
           trips through the protocol into both worlds.
  FORCE    the TestServer force_resync hook (the PRD's debug trigger) re-streams
           on demand, past the throttle, and leaves the client released again.
  RACE     the host makes a result (a buy) while a restream is in flight, after
           it took the restream's snapshot. The replica must apply that result
           exactly once, to the world it adopts: ONE restream leaves both worlds
           equal and the replica never asks for a second one.

Run:  python tools/coop_test/test_shared_resync.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session
import geo

RIFLE = "STR_RIFLE"
COOP_DLG_CLIENT_RESUME_HOLD = 68
DEBOUNCE_S = 3.0  # SharedEcon RESYNC_DEBOUNCE_MS: a mismatch must survive this
STREAM_LINE = "[coop-shared] streaming authoritative world to client"
BUSY_LINE = "[coop-shared] resync request dropped: streamer busy"
RELEASE_LINE = "restream adopted; released the client hold"
HELD_LINE = "result(s) held during the restream"


class _Log:
    """What an engine log gained since this object was made."""

    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "openxcom.log")
        self.offset = os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def tail(self):
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            return f.read()

    def count(self, text):
        return self.tail().count(text)


def _funds(gc):
    return gc.ok({"cmd": "geo_state"})["funds"]


def _resync(gc):
    return gc.ok({"cmd": "shared_resync_stats"})


def _coop(gc):
    return gc.ok({"cmd": "get_coop"})


def _rifles(gc):
    return gc.ok({"cmd": "incoming_transfers"})["items"].get(RIFLE, 0)


def _assert_released(gc, tag):
    """The client must not be parked in the resume hold (the J09 deadlock)."""
    c = _coop(gc)
    assert c["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD, (
        f"{tag}: client is stuck in COOP_DLG_CLIENT_RESUME_HOLD (68) - the "
        f"restream adopted a world but nothing released the hold. get_coop={c}")


def main():
    js = shared_fixture.bring_up("jrsy", (48740, 48741, 48040))
    host, client = js.host, js.client
    try:
        f0 = _funds(host)
        assert f0 == _funds(client), f"bootstrap funds differ: {f0} vs {_funds(client)}"
        _assert_released(client, "bootstrap")
        print(f"PASS setup: identical funds {f0}, client released")

        # ================================================================
        # 1) DETECT + REPAIR. Corrupting the REPLICA's funds is the cleanest
        #    forced mismatch: it changes exactly one checksum field, and only
        #    the repair can put it back (nothing else writes replica funds
        #    while no commands are running).
        # ================================================================
        host.ok({"cmd": "shared_reset_resync_stats"})
        client.ok({"cmd": "shared_reset_resync_stats"})

        BOGUS = 12345
        client.ok({"cmd": "set_funds", "value": BOGUS})
        assert _funds(client) == BOGUS, "replica funds not corrupted"
        assert _funds(host) == f0, "host funds must be untouched"
        print(f"PASS corrupt: replica funds forced to {BOGUS} (host still {f0})")

        client.wait_for("replica noticed the checksum mismatch",
                        lambda: (_resync(client)["mismatches"] >= 1) or None,
                        timeout=60, interval=0.5)
        client.wait_for("replica asked the host for a resync",
                        lambda: (_resync(client)["requests"] >= 1) or None,
                        timeout=60, interval=0.5)
        print(f"PASS detect: {_resync(client)['mismatches']} mismatch(es) -> "
              f"shared_resync_request sent")

        # The host serves it by re-streaming the authoritative world; the replica
        # adopts it through the same bootstrap path (CoopState 555 -> LoadGameState).
        client.wait_for("replica adopted the re-streamed world",
                        lambda: (_funds(client) == _funds(host)) or None,
                        timeout=90, interval=0.5)
        f1_h, f1_c = _funds(host), _funds(client)
        assert f1_c == f1_h, f"resync did not converge: host={f1_h} client={f1_c}"
        assert f1_c != BOGUS, "replica still holds the corrupted funds"
        hs = _resync(host)
        assert hs["requests"] >= 1, f"host did not serve a resync request: {hs}"
        print(f"PASS repair: replica funds {BOGUS} -> {f1_c} == host {f1_h} "
              f"(host served {hs['requests']} request(s))")

        # ================================================================
        # 2) RELEASE. THE regression guard for the J09 deadlock: adopting a
        #    streamed world always pushes the resume hold, and only the host's
        #    campaign_begun clears it.
        # ================================================================
        client.wait_for("client released from the resume hold",
                        lambda: (_coop(client)["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD) or None,
                        timeout=60, interval=0.5)
        _assert_released(client, "after auto-resync")
        rs = _resync(client)
        assert not rs["pending"], f"resync guard never cleared: {rs}"
        assert not rs["gaveUp"], f"replica gave up on a repairable desync: {rs}"
        print(f"PASS release: client not held (dialog="
              f"{_coop(client)['coopDialog']}), resync guard cleared")

        # ================================================================
        # 3) LIVE. The repaired replica is a working replica, not just a
        #    correct one: the protocol still round-trips both ways.
        # ================================================================
        rifles_pre = _rifles(host)
        r = client.ok({"cmd": "buy", "item": RIFLE, "count": 3})
        assert r.get("sent"), f"client buy not sent after resync: {r}"
        host.wait_for("host applied the post-resync client buy",
                      lambda: (_rifles(host) == rifles_pre + 3) or None,
                      timeout=30, interval=0.5)
        client.wait_for("client applied the post-resync shared_apply",
                        lambda: (_rifles(client) == rifles_pre + 3) or None,
                        timeout=30, interval=0.5)
        assert _funds(host) == _funds(client), "funds diverged after the post-resync buy"
        print(f"PASS live: post-resync buy round-tripped, funds equal "
              f"({_funds(host)}) on both")

        # ================================================================
        # 4) FORCE. The PRD's manual/debug trigger, past the throttle.
        # ================================================================
        client.ok({"cmd": "shared_reset_resync_stats"})
        host.ok({"cmd": "shared_reset_resync_stats"})
        r = client.ok({"cmd": "force_resync"})
        assert r.get("role") == "replica" and r.get("sent"), f"force_resync not sent: {r}"
        host.wait_for("host served the forced resync",
                      lambda: (_resync(host)["requests"] >= 1) or None,
                      timeout=60, interval=0.5)
        client.wait_for("client adopted the forced re-stream",
                        lambda: (not _resync(client)["pending"]) or None,
                        timeout=90, interval=0.5)
        # `pending` clears at world ADOPTION (LoadGameState calls
        # notifyWorldAdopted before it even pushes the resume hold), but the
        # RELEASE rides the resume_ack -> campaign_begun round-trip after it.
        # Wait for it like the auto-resync phase does, or a slow runner asserts
        # mid-handshake (seen on hosted CI: resumeAck=False, dialog=68).
        client.wait_for("client released after the forced resync",
                        lambda: (_coop(client)["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD) or None,
                        timeout=60, interval=0.5)
        _assert_released(client, "after force_resync")
        assert _funds(host) == _funds(client), "forced resync left the worlds unequal"
        assert client.cmd({"cmd": "ping"}).get("pong"), "client unresponsive after force_resync"
        assert host.cmd({"cmd": "ping"}).get("pong"), "host unresponsive after force_resync"
        print("PASS force: force_resync re-streamed on demand, client released, "
              "worlds equal, both alive")

        # ================================================================
        # 5) RACE. The host snapshots its world when it serves a restream. A
        #    result it makes after that snapshot is not in it, so the replica
        #    must apply that result to the world it adopts, once. The fixture:
        #    the host's own force_resync takes the snapshot and starts the
        #    stream, the host buys at once, and a second force_resync proves the
        #    stream was still in flight after the buy (it is dropped as busy).
        # ================================================================
        for gc in (host, client):
            gc.ok({"cmd": "shared_reset_resync_stats"})
        hlog, clog = _Log(js.host_dir), _Log(js.client_dir)
        rifles_pre = _rifles(host)
        r = host.ok({"cmd": "force_resync"})
        assert r.get("role") == "host", f"race: host force_resync failed: {r}"
        r = host.ok({"cmd": "buy", "item": RIFLE, "count": 2})
        assert r.get("sent"), f"race: host buy not made: {r}"
        host.ok({"cmd": "force_resync"})
        assert hlog.count(STREAM_LINE) == 1 and hlog.count(BUSY_LINE) == 1, (
            f"race fixture: the stream was not in flight after the buy "
            f"(streams={hlog.count(STREAM_LINE)}, busy drops={hlog.count(BUSY_LINE)})")
        assert _rifles(host) == rifles_pre + 2, "race: the host did not apply its buy"
        host.wait_for("the replica adopted the restream (host released it)",
                      lambda: (hlog.count(RELEASE_LINE) >= 1) or None,
                      timeout=60, interval=0.1)
        client.wait_for("client released after the race restream",
                        lambda: (_coop(client)["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD) or None,
                        timeout=60, interval=0.25)
        # A lost result shows as a mismatch that must survive the debounce
        # before the replica asks again; wait well past it.
        time.sleep(2 * DEBOUNCE_S + 1.0)
        rs, streams = _resync(client), hlog.count(STREAM_LINE)
        assert streams == 1 and rs["requests"] == 0 and not rs["gaveUp"], (
            f"race: the result made during the restream was lost; it took "
            f"{streams} restream(s) and {rs['requests']} replica request(s) "
            f"(gaveUp={rs['gaveUp']}) instead of one restream")
        assert _rifles(client) == rifles_pre + 2 and _funds(client) == _funds(host), (
            f"race: worlds differ after the restream: rifles host={_rifles(host)} "
            f"client={_rifles(client)}, funds host={_funds(host)} client={_funds(client)}")
        assert clog.count(HELD_LINE) >= 1, (
            "race: the replica did not report holding the result until the "
            "adoption, so the buy did not arrive during the stream")
        print(f"PASS race: a host result made during the restream was applied "
              f"once after the adoption; 1 restream, 0 replica requests, rifles "
              f"{rifles_pre}+2 and funds {_funds(host)} on both")

        # PRD-J11: the shared final-state assertions (world equality +
        # the replica's zero-disk invariant).
        js.finish()

        print("ALL SHARED RESYNC TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
