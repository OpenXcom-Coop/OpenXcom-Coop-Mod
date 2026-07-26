"""Issue #91: the client is stranded on "Waiting for host to resume the game."
while the host plays on, after time fast-forwarding in a SHARED campaign.

THE MECHANISM (static read, then reproduced below)
--------------------------------------------------
Every world restream parks the replica: LoadGameState adopts the streamed world,
sends `resume_ack` and pushes COOP_DLG_CLIENT_RESUME_HOLD (68) - a dialog with no
button (CoopState.cpp:334) and no timeout. Mid-session nobody clicks BEGIN, so the
ONLY thing that can ever release it is the host's `campaign_begun`, and the only
mid-session sender of that packet is the host's `resume_ack` handler:

    connectionTCP.cpp:3179
        if ((sharedPostBattleRestream || sharedResyncRestream) && ...)
        {
            sharedPostBattleRestream = false;
            sharedResyncRestream = false;      // <- ONE-SHOT, not per stream
            ... send campaign_begun ...
        }

That release flag is a single bool shared by ALL restreams, and the streamer frees
itself the instant the last chunk goes out (connectionTCP.cpp:906,
`sendFileClient = false`) - long before the replica has adopted anything. The
replica needs ~10 LoadGameState think ticks plus a whole GeoscapeState build to
get to its ack. Any SECOND restream started inside that window shares the one flag
with the first: ack #1 consumes it, and ack #2 finds it already false. No
`campaign_begun` is ever sent for the world the client is actually holding, so the
client sits in dialog 68 forever - while the host, which needs nothing from that
handshake, keeps running its geoscape. Exactly the screenshot in the issue.

WHY FAST-FORWARDING IS WHAT SETS IT OFF
---------------------------------------
A replica does not simulate: GeoscapeState::timeAdvance() runs `getTime()->advance()`
on both machines, but the whole effects block returns early for a replica
(GeoscapeState.cpp:2467), so its world only moves when a host broadcast moves it.
Under fast-forward the host burns a game DAY per 80ms tick, and a multi-chunk world
stream takes seconds, so the snapshot the replica finally adopts is already stale -
and the broadcasts that landed during the transfer were applied to the world that
the adopt just threw away. The replica therefore keeps mismatching, and asks again:

    SharedEcon.cpp:3630   cooling = now - g_lastResyncGameMin < 60   // GAME minutes

Phase 1 below measures that gate: at speed 5 the clock moves far more than 60 game
minutes per REAL second, so the "one auto-resync per game hour" throttle expires
between two polls. Back-to-back resync requests are the normal case while fast-
forwarding, not an exotic one - and back-to-back restreams are what strand the
client.

WHAT THIS TEST DOES
-------------------
  1) THROTTLE   at fast-forward speed, measure the replica's game-minutes-per-real-
                second. Anything over 60 means RESYNC_COOLDOWN_MINUTES cannot
                serialise two resyncs. (Deterministic; no networking involved.)
  2) STORM      authoritative restreams back to back, so a later one starts
                before the previous one's ack lands - what the throttle above
                stops holding back. A request that arrives while the streamer is
                busy is simply dropped, so ASKING REPEATEDLY for about one
                stream's worth of time gets the next restream served the instant
                the previous one's last chunk goes out: squarely inside the
                un-acked window, with no timing luck. Then silence, so the
                unreleased world is the one the client is left holding.
  3) ASSERT     two ways, after every pair:
                  * the client is not parked in dialog 68, and
                  * the host's log has one "released the client hold" for every
                    "streaming authoritative world" - the invariant the one-shot
                    flag breaks. This one trips even in the runs where a later
                    restream's release happens to rescue the client.

Expected result TODAY: fails on the first or second pair (the client left holding
dialog 68 while the host sits on a plain GeoscapeState, or a restream adopted with
no release sent). It passes once a restream's release stops being a single shared
bool.

Run:  python tools/coop_test/test_shared_resync_storm.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import geo

COOP_DLG_CLIENT_RESUME_HOLD = 68
RESYNC_COOLDOWN_MINUTES = 60   # SharedEcon.cpp:3458
FAST = 5                       # geoscape speed index: 1 day per tick


def _coop(gc):
    return gc.ok({"cmd": "get_coop"})


def _resync(gc):
    return gc.ok({"cmd": "shared_resync_stats"})


def _funds(gc):
    return gc.ok({"cmd": "geo_state"})["funds"]


def _snapshot(host, client, tag):
    """Everything needed to tell "stranded" apart from "still working"."""
    c, h = _coop(client), _coop(host)
    return (f"{tag}: client(dialog={c['coopDialog']} isLoadProgress={c['isLoadProgress']} "
            f"resync={_resync(client)}) host(dialog={h['coopDialog']} "
            f"resumeAck={h['resumeAck']} clock={geo.game_minutes(host)} "
            f"resync={_resync(host)})")


class HostLog:
    """The host's own account of the restream handshake, from the point this
    object is created (so the bootstrap stream - released by the operator's BEGIN,
    not by the resync path - is never counted).

    Two lines, one invariant: every "streaming authoritative world" that a client
    adopts owes exactly one "released the client hold".
    """

    STREAM = "[coop-shared] streaming authoritative world to client"
    RELEASE = "restream adopted; released the client hold"

    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "openxcom.log")
        self.offset = os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def tail(self):
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            return f.read()

    def counts(self):
        t = self.tail()
        return t.count(self.STREAM), t.count(self.RELEASE)


def _held(client):
    return _coop(client)["coopDialog"] == COOP_DLG_CLIENT_RESUME_HOLD


def _settle(client, seconds=12.0, poll=0.25):
    """Let the restreams in flight land. Returns True if the client is STILL in
    the resume hold at the end of the window AND was for the last 3s of it - i.e.
    stranded, not merely mid-adopt."""
    deadline = time.time() + seconds
    held_since = None
    while time.time() < deadline:
        if _held(client):
            held_since = held_since or time.time()
        else:
            held_since = None
        time.sleep(poll)
    return held_since is not None and (time.time() - held_since) >= 3.0


def _strand_report(host, client, log, how):
    """The failure the issue describes, with the evidence that identifies it."""
    streams, releases = log.counts()
    if _held(client):
        # The host is NOT in a dialog of its own - it is sitting on its geoscape,
        # exactly as reported, while the client waits for a resume nobody will
        # send. (The host's CLOCK does stop too, but for an unrelated reason: a
        # client parked in the hold emits no `time` heartbeat, and the host freezes
        # the shared clock when the peer goes quiet - GeoscapeState.cpp:2376.)
        symptom = (
            "The client is stranded in COOP_DLG_CLIENT_RESUME_HOLD "
            f"({_coop(client)['coopDialog']}) - \"Waiting for host to resume the "
            "game.\" - a dialog with no button and no timeout. The host is not "
            f"waiting for anything: it is on {geo.top_state(host)} with no dialog "
            "of its own. This is the issue's screenshot exactly.")
    else:
        symptom = (
            "The client escaped only because a LATER restream happened to carry a "
            "release with it; each unmatched restream above left it holding a world "
            "that nothing would ever release, which in play (where no further "
            "restream follows) is the permanent hang.")
    return AssertionError(
        f"ISSUE #91 REPRODUCED ({how}): restreams ran back to back, so a later one "
        "started before the previous one's resume_ack landed. The first ack "
        "consumed the one-shot release flag (connectionTCP.cpp:3183) and the next "
        "found it already false, so no campaign_begun was sent for the world the "
        f"client had just adopted: {streams} restream(s) served, {releases} "
        f"release(s) sent. {symptom}\n  {_snapshot(host, client, 'stranded')}")


def main():
    js = shared_fixture.bring_up("j91", (49020, 49021, 48320))
    host, client = js.host, js.client
    try:
        assert _funds(host) == _funds(client), "bootstrap worlds already differ"
        assert _coop(client)["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD, \
            "client held before the test even started"
        print(f"PASS setup: SHARED session live, funds {_funds(host)}, client released")

        # ================================================================
        # 1) THROTTLE. The auto-resync cooldown is measured in GAME minutes,
        #    so fast-forward evaporates it. Measured, not asserted from theory.
        # ================================================================
        t0, m0 = time.time(), geo.game_minutes(client)
        geo.skip_realtime(host, client, 4.0, speed_idx=FAST, poll=0.25)
        elapsed, moved = time.time() - t0, geo.game_minutes(client) - m0
        per_sec = moved / max(elapsed, 0.001)
        assert per_sec > RESYNC_COOLDOWN_MINUTES, (
            f"replica clock moved only {per_sec:.0f} game-min/s at speed {FAST}; "
            f"the {RESYNC_COOLDOWN_MINUTES}-game-minute resync throttle would still "
            f"hold, so this build cannot show the storm this way")
        print(f"PASS throttle: replica clock runs {per_sec:.0f} game-min per real "
              f"second at speed {FAST} - the {RESYNC_COOLDOWN_MINUTES}-game-minute "
              f"resync cooldown expires between two polls, so the replica re-asks "
              f"while a restream is still in flight")

        host.ok({"cmd": "shared_reset_resync_stats"})
        client.ok({"cmd": "shared_reset_resync_stats"})
        log = HostLog(js.host_dir)

        # Stop the world for the repro itself. The overlap is a packet-ordering
        # bug; a racing sim only adds noise (and popups) to the diagnosis. What
        # fast-forward contributes - the throttle that stops holding restreams
        # apart - is measured above and constructed directly below.
        geo.slow_clock(host, client)
        geo.drain_popups(host)
        geo.drain_popups(client)

        # ================================================================
        # 2+3) STORM + ASSERT. Restreams that run back to back, so a later one
        #      starts before the previous one's resume_ack lands. force_resync on
        #      the HOST is the same sharedResyncStream() call a replica request
        #      drives, so this is the replica's storm without its timing noise.
        # ================================================================
        # A PAIR, then silence. force_resync is dropped outright while the streamer
        # is busy (connectionTCP.cpp:9540), so asking repeatedly for ~one stream's
        # worth of time gets exactly one more restream served - and it is served
        # the instant the first one's last chunk goes out, i.e. squarely inside the
        # un-acked window. Nothing follows it, so the second world is the one the
        # client is left holding: the permanent hang, not a transient one.
        # The ask window is swept a little because a stream's length (and so the
        # moment the streamer frees) depends on the world's size and the machine;
        # the last, longest entry saturates outright and produces the same overlap
        # several times over, which the release accounting catches even in the runs
        # where the client's final adopt happens to be the one that gets released.
        for ask_for in (0.40, 0.55, 0.30, 0.70, 3.00):
            host.cmd({"cmd": "force_resync"})                 # restream A
            t_end = time.time() + ask_for
            while time.time() < t_end:                        # restream B, ASAP
                host.cmd({"cmd": "force_resync"})
                time.sleep(0.01)

            stranded = _settle(client)
            streams, releases = log.counts()
            print(f"  pair(ask {ask_for:.2f}s): client dialog="
                  f"{_coop(client)['coopDialog']}, host log: {streams} restream(s) "
                  f"/ {releases} release(s)")

            if stranded or releases < streams:
                raise _strand_report(host, client, log, "back-to-back restreams")

        streams, releases = log.counts()
        assert releases >= streams, (
            f"host served {streams} restream(s) but sent only {releases} release(s)")
        print(f"PASS storm: {streams} restream(s), {releases} release(s), client "
              f"never stranded (dialog={_coop(client)['coopDialog']})")
        js.finish()
        print("ALL SHARED RESYNC STORM TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
