"""Regression test: coop base-defense must not crash on a dangling `temp_ufo`.

Bug (reported as "save crashes on month end"): GeoscapeState::handleBaseDefense
stashes the attacking retaliation UFO in the file-scope global `temp_ufo` and
DEFERS the coop base-defense through a host<->client handshake. The UFO is freed
during that window (retaliation cleanup / despawn), so GeoscapeState::
startCoopMission dereferences a dangling pointer -> access violation. See
GeoscapeState.cpp:169 / :6009 / :565 and .agents/repro/coop-basedef-uaf/.

Scenario: host resumes the fixture coop save (a retaliation is inbound to a base),
the registered client joins, then time advances until the base defense fires.
The fixture is a SEPARATE campaign attack on the HOST's own base: the host runs
the base defense and the client receives the streamed battle.

  * PASS (exit 0): base-defense flow reaches the briefing/battle on both machines
    (via the battle-start handshake) with NO process crash -> the `temp_ufo` read is safe.
  * FAIL (exit 2): a game process crashes (the UAF) -> bug present.
  * FAIL (exit 3): the base defense never fired within the budget -> fixture/flow
    regressed; the test proved nothing (do not treat as green).
  * FAIL (exit 4): the base defense fired and neither machine crashed (the UAF
    fix holds), but the battle-start handshake did not complete on both machines.

RED before the fix (crashes ~every run, verified), GREEN after.

GeoscapeState::startCoopMission() (the deferred battle-start the CoopBaseDefense
snapshot feeds) runs the co-op battle-start handshake (CoopHandshake::offerBattle).
offerBattle()'s host push of BriefingState is unconditional (exactly like
vanilla SP, see CoopHandshake.h's top doc comment) while the client is pushed
straight into BattlescapeState by CoopHandshake::onBlobChunkAppended (no
client-side BriefingState - the LoadGameState.cpp "loaded save with a live
battle" precedent), so one machine leaving the geoscape does not prove that
both completed the handshake. The assertions below wait for BOTH machines (as
test_handshake.py / test_cydonia_coop_start.py do): host reaches BriefingState
then BattlescapeState after an OK click, client reaches BattlescapeState
directly, and the host+client "[coop-handshake] ... phase Active" log lines are
both present. The saveBlob hashes are not compared here (test_handshake.py
checks them): only that onReady() ran to completion is asserted.
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
    for root in (harness.CRASH_DIR,):  # this harness slot's own crash folder
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
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
    except BaseException:
        # main's cleanup runs only after its try below, so a failed spawn or connect shuts
        # down the games started here before the error propagates (shared_fixture.bring_up's form)
        harness.shutdown_clients(host, client)
        raise

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
        session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        time.sleep(2.0)
        geo.drain_popups(host); geo.drain_popups(client)

        # Advance until the base defense fires (interest) or the budget elapses.
        res = geo.skip_ingame_time(
            host, client, minutes=12 * 24 * 60,
            interest=geo.popup(*BATTLE_STATES),
            dismiss=True, real_timeout=180, stuck_timeout=None)
        print("skip_ingame_time result:", res)
        battle_reached = res.get("hit") is not None or in_battle(host) or in_battle(client)

        # skip_ingame_time HALTS at the base-defense BriefingState (the interest
        # carries .keep via geo.popup), so it is still on the host's stack here. CoopHandshake::emitPreparedOffer() runs
        # from BriefingState::btnOkClick/close_briefing, so the client offer is not
        # SENT until the HOST closes its own briefing FIRST; waiting for the client's
        # BattlescapeState before that hangs. session.drive_both_to_tactical closes
        # the host BriefingState via close_briefing, then drains BOTH machines through
        # Briefing/Inventory/CoopState popups to BattlescapeState.
        if battle_reached:
            assert session.drive_both_to_tactical(host, client), (
                f"drive_both_to_tactical timed out host={session.states(host)[-3:]} "
                f"client={session.states(client)[-3:]}")
            print("PASS: BOTH machines in BattlescapeState (host briefing closed "
                  "first via close_briefing)")

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
              "holds) but the battle-start handshake did not complete on both "
              "machines - see note/log lines above")
        sys.exit(4)
    print("PASS: coop base-defense reached the battle on both machines via "
          "the handshake with no crash")
    sys.exit(0)


if __name__ == "__main__":
    main()
