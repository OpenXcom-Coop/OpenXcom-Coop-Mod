"""coop (parallel turns): the persistent "Please wait for <player>'s action to
finish" banner (BattlescapeState::updateCoopWaitBanner + getPrimaryBusyActor).
Asserts:

  1. SHOWS + owner: while the HOST executes a CLIENT's forwarded walk, the host is
     busy with a unit it does NOT own, so the host's wait banner is non-empty
     ("Please wait for ... action to finish").
  2. CLEARS: once the host goes idle again the banner is empty.
  3. SUPPRESSED for own action (host): while the host executes its OWN walk the
     banner stays empty for the whole busy window - you are not waiting on anyone.
  4. CLIENT SHOWS + latch stability: while the CLIENT replays the HOST's own walk,
     the client's banner names the host and the owner never flips mid-window (the
     per-window owner latch, item 1). This is the most common player-facing case.
  5. CLIENT SUPPRESSED for own echoed action: while the client replays ITS OWN
     action back at it, its banner stays empty (mirror of 3, client-side).

Driven through the isBusy() path (a slowed, on-screen walk keeps the busy machine
busy for a pollable window), NOT the transient click-sync ticks, so it is not
frame-timing-sensitive.

Run:  python tools/coop_test/test_coop_wait_banner.py
Exit 0 = pass; 2 = failure.
"""
import os
import re
import sys
import time

# RW-TRIAGE: SKIP-PENDING(R3-P1)
# R2-P6 built the STR table + _txtCoopWait widget + CoopBattleUi deny/cancel
# presenter, but the 5 scenarios below drive the OLD P5 busy-owner banner
# (getPrimaryBusyActor()/isBusy() owner-latch, TestServer parallel()
# coopWaitBanner field, STR_COOP_WAIT_FOR_PLAYER_ACTION) - that driving logic
# is explicitly dead (ADDENDUM 1.3(f): "COPY NONE of the driving logic ...
# all of that is dead"), not the new deny/cancel presenter. Needs the R3-P1
# client bt_deny wiring (and likely a scenario rewrite against the new
# admission model) before it can run. Relabeled from SKIP-PENDING(R2-P6).
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_battle_tripwire as TW
import test_parallel_intents as PI

PORT = "47991"


def banner(gc):
    return PI.parallel(gc).get("coopWaitBanner", "") or ""


def busy(gc):
    return bool(gc.cmd({"cmd": "battle_state"}).get("isBusy"))


def owner_name(b):
    m = re.search(r"for (.+)'s action to finish", b)
    return m.group(1).strip() if m else None


def slow(gc):
    gc.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": 200})


def long_walk_dest(gc, uid):
    for radius in (8, 6, 4, 2):
        d = PI.far_step(gc, uid, radius=radius)
        if d:
            return d
    return None


def scenario_shows_and_clears(host, client, client_mover):
    print("-- 1+2: host executes CLIENT walk -> host banner names owner, then clears --")
    assert PI.idle(host), "host not idle before the client walk"
    slow(host)
    host.cmd({"cmd": "battle_camera", "unit": client_mover, "visible": True})
    PI.top_up(host, client, client_mover)
    dest = long_walk_dest(host, client_mover)
    assert dest, f"client soldier {client_mover} cannot walk anywhere"

    r = PI.intent(client, action="move", unit=client_mover,
                  x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    # while the host runs the client's walk it is busy with a unit it does NOT own
    got = PI.wait_until(lambda: "please wait" in banner(host).lower(), 30)
    b = banner(host)
    assert got, (
        f"host wait banner never showed while executing the client's walk "
        f"(banner={b!r}, host canAdmit={PI.parallel(host).get('canAdmit')}). "
        f"getPrimaryBusyActor()/owner-seat resolution or the updateCoopWaitBanner "
        f"guards are wrong.")
    assert "action to finish" in b.lower(), f"unexpected banner wording: {b!r}"
    # the owner NAME must be resolved (not blank) - seatName() is empty in a
    # skirmish battle, so this guards the getCurrentClientName() fallback.
    m = re.search(r"for (.+)'s action to finish", b)
    assert m and m.group(1).strip(), f"banner has no player name: {b!r}"
    print(f"PASS 1: host banner while executing the client's walk = {b!r}")

    assert PI.idle(host, timeout=120), "host walk never finished"
    PI.settle(host, client)
    assert PI.wait_until(lambda: banner(host) == "", 15), (
        f"host wait banner did not clear after going idle (still {banner(host)!r})")
    print("PASS 2: banner cleared once the host went idle")


def scenario_own_action_suppressed(host, client, host_mover):
    print("-- 3: host's OWN walk -> banner suppressed the whole busy window --")
    assert PI.idle(host), "host not idle before its own walk"
    slow(host)
    host.cmd({"cmd": "battle_camera", "unit": host_mover, "visible": True})
    PI.top_up(host, client, host_mover)
    dest = long_walk_dest(host, host_mover)
    assert dest, f"host soldier {host_mover} cannot walk anywhere"

    r = PI.intent(host, action="move", unit=host_mover, x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is False, (
        f"the host did not execute its own walk locally (routed={r.get('routed')}); "
        f"the executor must run its own action, not ship an intent")

    busy_samples = 0
    deadline = time.time() + 30
    while time.time() < deadline:
        ps = PI.parallel(host)
        b = banner(host)
        if ps.get("canAdmit") is False:
            busy_samples += 1
            assert b == "", (
                f"host wait banner lit for the host's OWN action (banner={b!r}); "
                f"owner==localSeat must be suppressed")
        elif busy_samples > 0:
            break
        time.sleep(0.05)
    assert busy_samples > 0, "never observed the host busy during its own walk (test vacuous)"
    PI.settle(host, client)
    print(f"PASS 3: banner stayed empty across {busy_samples} busy sample(s) of the host's own walk")


def scenario_client_sees_host(host, client, host_mover):
    print("-- 4: client replays HOST's own walk -> client banner names the host, latch stable --")
    assert PI.idle(host), "host not idle before its own walk"
    slow(client)  # slow the CLIENT so its replay of the host's walk is a pollable window
    client.cmd({"cmd": "battle_camera", "unit": host_mover, "visible": True})
    PI.top_up(host, client, host_mover)
    dest = long_walk_dest(host, host_mover)
    assert dest, f"host soldier {host_mover} cannot walk anywhere"

    r = PI.intent(host, action="move", unit=host_mover, x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is False, (
        f"the host did not execute its own walk locally (routed={r.get('routed')})")

    # while the client REPLAYS the host's action it is busy with a unit it does NOT own
    got = PI.wait_until(lambda: "please wait" in banner(client).lower(), 30)
    b = banner(client)
    assert got, (
        f"client wait banner never showed while replaying the host's walk "
        f"(banner={b!r}, client isBusy={busy(client)}). This is the common "
        f"player-facing case - the client-side isBusy/owner path is broken.")
    assert "action to finish" in b.lower(), f"unexpected banner wording: {b!r}"
    first = owner_name(b)
    assert first, f"client banner has no player name: {b!r}"

    # item-1 latch: the owner must not flip mid-window (a consequence state pushed
    # to the front must not re-attribute the banner). A kill-free walk pushes none,
    # so this is a stability proxy, not a casualty test (deliberately - the review
    # ruled a kill-based edge too flaky to assert).
    names = {first}
    while busy(client):
        bn = banner(client)
        if bn:
            names.add(owner_name(bn))
        time.sleep(0.05)
    assert names == {first}, f"client banner owner changed mid-window (latch broken): {names}"
    print(f"PASS 4: client banner while replaying the host's walk = {b!r} (owner stable)")

    PI.wait_until(lambda: not busy(client), 120)
    PI.settle(host, client)
    assert PI.wait_until(lambda: banner(client) == "", 15), (
        f"client wait banner did not clear after the replay ended (still {banner(client)!r})")
    print("PASS 4b: client banner cleared once the replay ended")


def scenario_client_own_suppressed(host, client, client_mover):
    print("-- 5: client replays its OWN echoed action -> banner suppressed the whole window --")
    assert PI.idle(host), "host not idle before the client walk"
    slow(client)
    client.cmd({"cmd": "battle_camera", "unit": client_mover, "visible": True})
    PI.top_up(host, client, client_mover)
    dest = long_walk_dest(host, client_mover)  # host-pathable: the host is the executor
    assert dest, f"client soldier {client_mover} cannot walk anywhere"

    r = PI.intent(client, action="move", unit=client_mover, x=dest[0], y=dest[1], z=dest[2])
    assert r.get("routed") is True, f"the client executed locally: {r}"

    busy_samples = 0
    deadline = time.time() + 30
    while time.time() < deadline:
        b = banner(client)
        if busy(client):
            busy_samples += 1
            assert b == "", (
                f"client wait banner lit for its OWN echoed action (banner={b!r}); "
                f"owner==localSeat must be suppressed")
        elif busy_samples > 0:
            break
        time.sleep(0.05)
    assert busy_samples > 0, "never observed the client busy replaying its own walk (test vacuous)"
    PI.settle(host, client)
    print(f"PASS 5: client banner stayed empty across {busy_samples} busy sample(s) of its own action")


def main():
    fail = None
    host = GameClient("host", 48930, make_user_dir(
        "waitbn_reg_host", options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                    "skipNextTurnScreen": True,
                                    "EnableCoopParallelTurns": True}))
    client = GameClient("client", 48931, make_user_dir(
        "waitbn_reg_client", options={"battleXcomSpeed": 2, "battleAlienSpeed": 2,
                                      "EnableCoopParallelTurns": False}))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        TW.bring_up_battle(host, client)
        print("battle up on both machines")

        for gc, tag in ((host, "host"), (client, "client")):
            assert PI.battle(gc)["parallelActive"] is True, f"{tag}: parallel not live"
        assert PI.battle(host)["activeSync"] is True and PI.battle(client)["activeSync"] is False, \
            "executor invariant broken - nothing below tests the intended path"

        seat = client.ok({"cmd": "get_coop"})["localSeat"]
        client_mover = PI.pick_driver(host, client, seat, "client")
        host_mover = PI.pick_driver(host, client, 0, "host")

        scenario_shows_and_clears(host, client, client_mover)
        scenario_own_action_suppressed(host, client, host_mover)
        scenario_client_sees_host(host, client, host_mover)
        scenario_client_own_suppressed(host, client, client_mover)

        print("ALL WAIT-BANNER TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
