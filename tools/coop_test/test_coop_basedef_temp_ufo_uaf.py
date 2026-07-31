"""Regression test: coop base-defense must not crash on a dangling `temp_ufo`.

Bug (reported as "save crashes on month end"): GeoscapeState::handleBaseDefense
stashes the attacking retaliation UFO in the file-scope global `temp_ufo` and
DEFERS the coop base-defense through a host<->client handshake. The UFO is freed
during that window (retaliation cleanup / despawn), so GeoscapeState::
startCoopMission dereferences a dangling pointer -> access violation. See
GeoscapeState.cpp:169 / :6009 / :565 and .agents/repro/coop-basedef-uaf/.

Scenario: host resumes the fixture coop save (a retaliation is inbound to a base),
the registered client joins, then time advances until the base defense fires.

  * PASS (exit 0): base-defense flow reaches the briefing/battle on both machines
    with NO process crash -> the `temp_ufo` read is safe.
  * FAIL (exit 2): a game process crashes (the UAF) -> bug present.
  * FAIL (exit 3): the base defense never fired within the budget -> fixture/flow
    regressed; the test proved nothing (do not treat as green).

RED before the fix (crashes ~every run, verified), GREEN after.
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
    note = None
    try:
        host.ok({"cmd": "load_save_menu", "file": FIXTURE})
        host.wait_for("host window", lambda: session._has_state(host, "HostMenu"))
        host.ok({"cmd": "host_tcp", "server": "TestSrv", "port": PORT, "player": "HostPlayer"})
        host.wait_for("resume lobby", lambda: session._has_state(host, "LobbyMenu"))

        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT, "player": "ClientPlayer"})
        client.wait_for("client lobby", lambda: session._has_state(client, "LobbyMenu"))

        host.wait_for("resume accepted",
                      lambda: host.cmd({"cmd": "lobby_resume_campaign"}).get("ok") or None,
                      timeout=60, interval=2.0)
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
        battle_reached = res.get("hit") is not None or in_battle(host) or in_battle(client)
    except (ConnectionError, OSError) as e:
        note = f"{type(e).__name__}: {e}"   # socket dropped mid-command == a crash
    except Exception as e:
        note = f"{type(e).__name__}: {e}"

    time.sleep(1.5)
    new_logs = sorted(crash_logs() - pre)
    rc_host, rc_client = host.proc.poll(), client.proc.poll()
    crashed = (rc_host is not None) or (rc_client is not None) or bool(new_logs)

    print("==== RESULT ====")
    print("battle_reached:", bool(battle_reached), "| crashed:", crashed,
          "| host rc:", rc_host, "client rc:", rc_client, "| note:", note)
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
    print("PASS: coop base-defense reached the battle with no crash")
    sys.exit(0)


if __name__ == "__main__":
    main()
