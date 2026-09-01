"""Regression test: coop base-defense must not crash on a dangling `temp_ufo`.

Bug (reported as "save crashes on month end"): GeoscapeState::handleBaseDefense
stashes the attacking retaliation UFO in the file-scope global `temp_ufo` and
DEFERS the coop base-defense through a host<->client handshake. The UFO is freed
during that window (retaliation cleanup / despawn), so GeoscapeState::
startCoopMission dereferences a dangling pointer -> access violation. See
GeoscapeState.cpp:169 / :6009 / :565 and .agents/repro/coop-basedef-uaf/.

Scenario: host resumes the fixture coop save (a retaliation is inbound to a base),
the registered client joins, then time advances until the base defense fires.
The fixture is a SEPARATE campaign attack on the HOST's own base (donor commit
0b0daeafb: "Host-side only (the client receives the streamed battle)").

  * PASS (exit 0): base-defense flow reaches the briefing/battle on both machines
    (via the R4-P2 handshake) with NO process crash -> the `temp_ufo` read is safe.
  * FAIL (exit 2): a game process crashes (the UAF) -> bug present.
  * FAIL (exit 3): the base defense never fired within the budget -> fixture/flow
    regressed; the test proved nothing (do not treat as green).
  * FAIL (exit 4): the base defense fired and neither machine crashed (the UAF
    fix holds), but the R4-P2 handshake did not complete on both machines.

RED before the fix (crashes ~every run, verified), GREEN after.

R4-P2 (SPIKE-RUNBOOK.md SS2.7, RB-D18): GeoscapeState::startCoopMission() (the
deferred battle-start this snapshot feeds) now rides the SAME handshake R4-P1
built (CoopHandshake::offerBattle) instead of the R1-P5 "coop battles
unavailable" popup - the CoopBaseDefense snapshot struct + the UAF fix itself
are UNTOUCHED (R2-M5, kept exactly). TRIM (RW-TRIAGE, this packet): the
pre-rewrite version of this test only required in_battle() to fire once (the
FIRST of host/client to leave the geoscape) via geo.skip_ingame_time's
early-exit, then read `in_battle(host) or in_battle(client)` a second time as a
soft "close enough" check on the other side. Since offerBattle()'s host push of
BriefingState is unconditional (exactly like vanilla SP, see CoopHandshake.h's
top doc comment) while the client is pushed straight into BattlescapeState by
CoopHandshake::onBlobChunkAppended (no client-side BriefingState - the
LoadGameState.cpp "loaded save with a live battle" precedent), a single
interest-fire no longer proves both sides actually completed the handshake.
Assertions below explicitly wait for BOTH machines (mirroring
test_rw_handshake.py / test_cydonia_coop_start.py): host reaches BriefingState
then BattlescapeState after an OK click, client reaches BattlescapeState
directly, and the host+client "[coop-handshake] ... phase Active" log lines are
both present. The saveBlob hash comparison itself stays SOFT-GATED pending
R2-P9 (see test_rw_handshake.py's docstring) - only that onReady() ran to
completion is asserted, not saveBlob equality.
"""
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = "coop_basedef_retaliation.sav"
FIXTURE_PATH = os.path.join(HERE, "fixtures", FIXTURE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, HERE)
import harness  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

PORT = "47934"
RELEASE_DIR = os.path.dirname(harness.EXE)
BATTLE_STATES = ("BriefingState", "BattlescapeState")


def crash_logs():
    hits = []
    for root in (harness.TEST_ROOT, RELEASE_DIR):
        hits += glob.glob(os.path.join(root, "**", "crash_*.log"), recursive=True)
    return set(hits)


def in_battle(gc):
    """Interest: fires once the base-defense flow leaves the geoscape."""
    return any(s in geo.top_state(gc) for s in BATTLE_STATES) or None


def log_lines(user_dir):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def grep_lines(lines, needle):
    return [l.rstrip("\n") for l in lines if needle in l]


def main():
    assert os.path.isfile(harness.EXE), "no exe (set OXC_TEST_EXE): " + harness.EXE
    assert os.path.isfile(FIXTURE_PATH), "missing fixture: " + FIXTURE_PATH
    host_dir = make_user_dir("bduaf_host", saves=[FIXTURE_PATH])
    client_dir = make_user_dir("bduaf_client")
    pre = crash_logs()

    host = GameClient("host", 48831, host_dir)
    client = GameClient("client", 48832, client_dir)
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    battle_reached = False
    handshake_ok = False
    note = None
    try:
        host.ok({"cmd": "load_save_menu", "file": FIXTURE})
        host.wait_for("host window", lambda: session._has_state(host, "HostMenu"))
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": PORT, "player": "HostPlayer"})
        host.wait_for("resume lobby", lambda: session._has_state(host, "LobbyMenu"))

        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT, "player": "ClientPlayer"})
        client.wait_for("client lobby", lambda: session._has_state(client, "LobbyMenu"))

        session.resume_campaign_via_button(host, "ClientPlayer")
        host.wait_for("client world ack",
                      lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None,
                      timeout=120)
        host.ok({"cmd": "coop_dialog_back"})
        time.sleep(2.0)
        geo.drain_popups(host); geo.drain_popups(client)

        # Advance until the base defense fires (interest) or the budget elapses.
        res = geo.skip_ingame_time(
            host, client, minutes=12 * 24 * 60,
            interest=lambda gc: in_battle(gc),
            dismiss=True, real_timeout=180, stuck_timeout=None)
        print("skip_ingame_time result:", res)
        battle_reached = res.get("hit") is not None or in_battle(host) or in_battle(client)

        # R4-P2: the interest above only proves ONE machine left the geoscape
        # first - GeoscapeState::startCoopMission() now offers the battle over
        # the SAME handshake R4-P1 built (CoopHandshake::offerBattle), so both
        # machines are expected to complete it. Wait for both explicitly.
        if battle_reached:
            host.wait_for("host briefing", lambda: session._has_state(host, "BriefingState"),
                          timeout=60)
            print("PASS: host reached BriefingState (vanilla push, unconditional)")

            client.wait_for("client battlescape",
                            lambda: session._has_state(client, "BattlescapeState"),
                            timeout=120)
            print("PASS: client reached BattlescapeState directly (offer/accept/"
                  "stream/blobSha-verify/load all succeeded)")

            host.ok({"cmd": "click_widget", "match": "ok"})
            host.wait_for("host battlescape",
                          lambda: session._has_state(host, "BattlescapeState"), timeout=60)
            print("PASS: BOTH machines in BattlescapeState")

            host_log = log_lines(host_dir)
            client_log = log_lines(client_dir)
            host_active = grep_lines(host_log, "[coop-handshake] HOST phase Active")
            client_active = grep_lines(client_log, "[coop-handshake] CLIENT phase Active")
            if host_active:
                print("HOST LOG:", host_active[-1])
            if client_active:
                print("CLIENT LOG:", client_active[-1])
            handshake_ok = bool(host_active) and bool(client_active)
    except (ConnectionError, OSError) as e:
        note = f"{type(e).__name__}: {e}"   # socket dropped mid-command == a crash
    except Exception as e:
        note = f"{type(e).__name__}: {e}"

    time.sleep(1.5)
    new_logs = sorted(crash_logs() - pre)
    rc_host, rc_client = host.proc.poll(), client.proc.poll()
    crashed = (rc_host is not None) or (rc_client is not None) or bool(new_logs)

    print("==== RESULT ====")
    print("battle_reached:", bool(battle_reached), "| handshake_ok:", handshake_ok,
          "| crashed:", crashed, "| host rc:", rc_host, "client rc:", rc_client,
          "| note:", note)
    if new_logs:
        print("crash logs:", [os.path.basename(x) for x in new_logs])
        with open(new_logs[0], "r", errors="replace") as f:
            sys.stdout.write(f.read())

    for gc in (host, client):
        try:
            gc.shutdown()
        except Exception:
            pass

    if crashed:
        print("FAIL: coop base-defense crashed (temp_ufo use-after-free)")
        sys.exit(2)
    if not battle_reached:
        print("INCONCLUSIVE: base defense never fired within budget")
        sys.exit(3)
    if not handshake_ok:
        print("FAIL: base defense reached the battle (no crash - the UAF fix "
              "holds) but the R4-P2 handshake did not complete on both "
              "machines - see note/log lines above")
        sys.exit(4)
    print("PASS: coop base-defense reached the battle on both machines via "
          "the handshake with no crash")
    sys.exit(0)


if __name__ == "__main__":
    main()
