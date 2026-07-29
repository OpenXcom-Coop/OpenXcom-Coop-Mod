"""Regression coverage for the host-authoritative multiplayer VoteMenu.

Covers:

1. Production VoteSession rules through TestServer:
   - strict-majority behavior for 3 and 4 players;
   - a 2-2 tie fails;
   - the starter automatically votes YES and cannot vote twice;
   - the production default vote duration is 30 seconds.
2. A real host/client session:
   - real player names are rendered on both VoteMenus;
   - the host-authoritative 30-second deadline fails the vote;
   - the starter receives a 60-second vote-start cooldown;
   - another seat may start a vote while that cooldown is active;
   - the result reaches both machines.
3. Disconnect handling:
   - dropping a peer while VoteMenu is open cancels the popup instead of
     leaving it waiting forever for vote_result.

The timeout test uses an explicit TestServer hook that moves the real
VoteSession deadline to the current tick and runs the normal host evaluator.
This keeps the suite fast without copying the timeout logic into Python.

Run:  python tools/coop_test/test_vote_system.py
Exit 0 = pass; an assertion/exception = failure.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session


VOTE_TIMEOUT_MS = 30_000
VOTE_COOLDOWN_MS = 60_000


def _wait_vote(gc, description, predicate, timeout=30):
    return gc.wait_for(
        description,
        lambda: (lambda state: state if predicate(state) else None)(
            gc.ok({"cmd": "vote_state"})
        ),
        timeout=timeout,
        interval=0.25,
    )


def _wait_dialog(gc, code, description, timeout=15):
    return gc.wait_for(
        description,
        lambda: (lambda state: state if (
            state.get("present") and state.get("code") == code
        ) else None)(gc.ok({"cmd": "coop_dialog_info"})),
        timeout=timeout,
        interval=0.25,
    )


def _assert_rule_probes(host):
    three = host.ok({
        "cmd": "vote_session_probe",
        "players": 3,
        "starter": 0,
        "names": ["Alice", "Bob", "Carol"],
        "casts": [{"seat": 1, "yes": True}],
    })
    assert three["defaultTimeoutMs"] == VOTE_TIMEOUT_MS, three
    assert 0 < three["remainingMs"] <= VOTE_TIMEOUT_MS, three
    assert three["timedOutAtDeadline"] is True, three
    assert three["requiredYes"] == 2, three
    assert three["decision"] == "passed", three
    assert three["votes"] == [1, 1, -1], three
    assert three["playerNames"] == ["Alice", "Bob", "Carol"], three
    print("PASS production vote duration: 30 seconds")
    print("PASS 3-player strict majority: 2 YES votes")

    four_pass = host.ok({
        "cmd": "vote_session_probe",
        "players": 4,
        "starter": 0,
        "names": ["Alice", "Bob", "Carol", "Dave"],
        "casts": [
            {"seat": 1, "yes": True},
            {"seat": 2, "yes": True},
        ],
    })
    assert four_pass["requiredYes"] == 3, four_pass
    assert four_pass["decision"] == "passed", four_pass
    print("PASS 4-player strict majority: 3 YES votes")

    four_tie = host.ok({
        "cmd": "vote_session_probe",
        "players": 4,
        "starter": 0,
        "casts": [
            {"seat": 1, "yes": True},
            {"seat": 2, "yes": False},
            {"seat": 3, "yes": False},
        ],
    })
    assert four_tie["decision"] == "failed", four_tie
    assert four_tie["yesVotes"] == 2 and four_tie["noVotes"] == 2, four_tie
    print("PASS 4-player 2-2 tie fails")

    duplicate = host.ok({
        "cmd": "vote_session_probe",
        "players": 3,
        "starter": 1,
        "casts": [
            {"seat": 1, "yes": False},  # starter already auto-voted YES
            {"seat": 2, "yes": False},
        ],
    })
    assert duplicate["accepted"] == [False, True], duplicate
    assert duplicate["votes"] == [-1, 1, 0], duplicate
    print("PASS duplicate seat vote rejected")


def _assert_network_timeout_cooldown_and_names(host, client):
    host_name = "AliceHost"
    client_name = "BobClient"
    expected_names = [host_name, client_name]

    session.new_campaign(
        host,
        client,
        port="47995",
        host_name=host_name,
        client_name=client_name,
        host_base="Alice Base",
        client_base="Bob Base",
    )

    # Start from the client. Its request is seat 1's automatic YES vote.
    requested = client.ok({
        "cmd": "vote_request",
        "action": "test_vote",
        "title": "PLAYER NAME AND TIMEOUT TEST",
        "question": "Do both machines show the real names?",
    })
    assert requested["accepted"] is True, requested

    host_vote = _wait_vote(
        host,
        "host VoteMenu",
        lambda s: s.get("active") and s.get("menuOpen"),
    )
    client_vote = _wait_vote(
        client,
        "client VoteMenu",
        lambda s: s.get("active") and s.get("menuOpen"),
    )

    for label, state in (("host", host_vote), ("client", client_vote)):
        assert state["defaultTimeoutMs"] == VOTE_TIMEOUT_MS, f"{label}: {state}"
        assert 20_000 <= state["remainingMs"] <= VOTE_TIMEOUT_MS, f"{label}: {state}"
        assert "TIME:" in state["menuStatus"], f"{label}: {state}"
        assert state["playerNames"] == expected_names, f"{label}: {state}"
        assert state["menuPlayerNames"] == expected_names, f"{label}: {state}"
        assert host_name in state["menuRows"], f"{label}: {state}"
        assert client_name in state["menuRows"], f"{label}: {state}"
        assert "PLAYER 1" not in state["menuRows"], f"{label}: {state}"
        assert "PLAYER 2" not in state["menuRows"], f"{label}: {state}"
        assert state["requiredYes"] == 2, f"{label}: {state}"
        assert state["starterSeat"] == 1, f"{label}: {state}"
        assert state["votes"] == [-1, 1], f"{label}: {state}"
    print("PASS both VoteMenus render the locked roster names and countdown")

    # Move the production host deadline to now and run its normal evaluator.
    forced = host.ok({"cmd": "vote_force_timeout"})
    assert forced["accepted"] is True, forced

    host_failed = _wait_vote(
        host,
        "host timed-out vote result",
        lambda s: s.get("finished") and not s.get("passed"),
    )
    client_failed = _wait_vote(
        client,
        "client timed-out vote result",
        lambda s: s.get("finished") and not s.get("passed"),
    )
    for label, state in (("host", host_failed), ("client", client_failed)):
        assert state["menuFinished"] is True, f"{label}: {state}"
        assert state["menuStatus"] == "VOTE FAILED", f"{label}: {state}"
    print("PASS host-authoritative timeout rejects the vote on both machines")

    host.ok({"cmd": "vote_close"})
    client.ok({"cmd": "vote_close"})

    # The original starter was client seat 1. Its host-owned cooldown should be
    # close to a full minute; checking above 50 seconds distinguishes it from
    # the old 30-second implementation without relying on exact scheduler timing.
    cooldown = host.ok({"cmd": "vote_cooldown_state", "seat": 1})
    assert 50_000 <= cooldown["remainingMs"] <= VOTE_COOLDOWN_MS, cooldown
    print("PASS vote starter cooldown: 60 seconds")

    # Client requests again. Locally the packet is accepted for sending, then
    # the host rejects it and returns a targeted CoopState warning.
    retry = client.ok({
        "cmd": "vote_request",
        "action": "test_vote",
        "title": "COOLDOWN TEST",
        "question": "This request should be rejected by the host.",
    })
    assert retry["accepted"] is True, retry

    dialog = _wait_dialog(client, 558, "client vote cooldown dialog")
    match = re.search(r"Please wait (\d+) seconds? before starting another vote\.",
                      dialog["title"])
    assert match, dialog
    shown_seconds = int(match.group(1))
    assert 50 <= shown_seconds <= 60, dialog
    assert dialog["backVisible"] is True, dialog
    print("PASS client receives the vote cooldown CoopState")
    client.ok({"cmd": "coop_dialog_back"})

    # Cooldown is seat-specific. Host seat 0 must still be allowed to start a
    # vote while client seat 1 is cooling down.
    host_request = host.ok({
        "cmd": "vote_request",
        "action": "test_vote",
        "title": "OTHER SEAT TEST",
        "question": "Can another seat start a vote?",
    })
    assert host_request["accepted"] is True, host_request

    host_second = _wait_vote(
        host,
        "host-started vote",
        lambda s: s.get("active") and s.get("starterSeat") == 0,
    )
    client_second = _wait_vote(
        client,
        "client receives host-started vote",
        lambda s: s.get("active") and s.get("starterSeat") == 0,
    )
    assert host_second["votes"] == [1, -1], host_second
    assert client_second["votes"] == [1, -1], client_second
    print("PASS cooldown only blocks the seat that started the previous vote")

    cast = client.ok({"cmd": "vote_cast", "yes": True})
    assert cast["accepted"] is True, cast

    host_done = _wait_vote(
        host,
        "host vote result",
        lambda s: s.get("finished") and s.get("passed"),
    )
    client_done = _wait_vote(
        client,
        "client vote result",
        lambda s: s.get("finished") and s.get("passed"),
    )
    assert host_done["votes"] == [1, 1], host_done
    assert client_done["votes"] == [1, 1], client_done
    assert host_done["menuStatus"] == "VOTE PASSED", host_done
    assert client_done["menuStatus"] == "VOTE PASSED", client_done
    print("PASS host-authoritative result reached both machines")

    host.ok({"cmd": "vote_close"})
    client.ok({"cmd": "vote_close"})

    # Host seat 0 now has its own cooldown. Unlike a client request, a local
    # host rejection is immediate and vote_request returns accepted=false.
    host_retry = host.ok({
        "cmd": "vote_request",
        "action": "test_vote",
        "title": "HOST COOLDOWN TEST",
        "question": "The host should also be rate-limited.",
    })
    assert host_retry["accepted"] is False, host_retry
    host_dialog = _wait_dialog(host, 558, "host vote cooldown dialog")
    assert "before starting another vote" in host_dialog["title"], host_dialog
    host.ok({"cmd": "coop_dialog_back"})
    print("PASS local host receives the same cooldown warning")


def _assert_disconnect_cancels_vote():
    host_dir = make_user_dir("vote_disconnect_host")
    client_dir = make_user_dir("vote_disconnect_client")
    host = GameClient("host_disconnect", 48942, host_dir)
    client = GameClient("client_disconnect", 48943, client_dir)

    try:
        host.spawn()
        client.spawn()
        host.connect()
        client.connect()

        session.new_campaign(
            host,
            client,
            port="47996",
            host_name="DisconnectHost",
            client_name="DisconnectClient",
            host_base="Disconnect Host Base",
            client_base="Disconnect Client Base",
        )

        request = host.ok({
            "cmd": "vote_request",
            "action": "test_vote",
            "title": "DISCONNECT TEST",
            "question": "Cancel this vote if the peer disconnects.",
        })
        assert request["accepted"] is True, request
        opened = _wait_vote(
            host,
            "disconnect-test VoteMenu",
            lambda s: s.get("active") and s.get("menuOpen"),
        )
        vote_id = opened["id"]
        assert vote_id, opened

        # Kill the peer process so the host takes the real transport-drop path.
        if client.proc:
            client.proc.kill()
            client.proc.wait(timeout=10)
        client.sock = None

        cancelled = host.wait_for(
            "VoteMenu cancellation after peer disconnect",
            lambda: (lambda state: state if (
                state.get("menuOpen")
                and state.get("menuFinished")
                and state.get("menuStatus") == "CONNECTION LOST - VOTE CANCELLED"
            ) else None)(host.ok({"cmd": "vote_menu_state", "id": vote_id})),
            timeout=20,
            interval=0.25,
        )
        assert cancelled["menuFinished"] is True, cancelled
        print("PASS peer disconnect cancels an open VoteMenu")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    host_dir = make_user_dir("vote_system_host")
    client_dir = make_user_dir("vote_system_client")
    host = GameClient("host", 48940, host_dir)
    client = GameClient("client", 48941, client_dir)

    try:
        host.spawn()
        client.spawn()
        host.connect()
        client.connect()

        _assert_rule_probes(host)
        _assert_network_timeout_cooldown_and_names(host, client)
        session.assert_client_zero_disk(client_dir)
    finally:
        host.shutdown()
        client.shutdown()

    _assert_disconnect_cancels_vote()
    print("ALL VOTE SYSTEM TESTS PASSED")


if __name__ == "__main__":
    main()
