"""PvP win/lose end-to-end: both machines leave the battle with the right verdict.

In a PvP skirmish BOTH sides are player-controlled, so vanilla "one side out"
end-conditions never fire when the ENEMY PLAYER's units die.  The [P1] fix makes
the end-turn scan (BattlescapeState::btnEndTurnClick) detect a wiped side, stamp
`battle:true` + `pvp_win` into the PlayerTurnYour packet, and drive finishBattle
LOCALLY; the receiver mirrors the verdict from the packet and runs its own
finishBattle.  Result: when one side is fully eliminated, BOTH machines leave the
battlescape into Debriefing with the same win/lose verdict.

Verdict values (_coopPVPwin, surfaced as battle_state.pvpWin):
    0 = unset, 1 = XCOM wins, 2 = alien/UFO wins.

Four deterministic sub-cases (units killed host-side via the harness kill_unit
command, coop_side: 0=host-side, 1=client-side):
    1. gm2, kill CLIENT-side (coop 1 = aliens)  -> pvpWin 1 (XCOM wins).
    2. gm2, kill HOST-side   (coop 0 = XCOM)     -> pvpWin 2 (alien wins).
    3. gm3, kill CLIENT-side (coop 1 = XCOM)     -> pvpWin 2 (alien wins).
    4. gm3, kill HOST-side   (coop 0 = aliens)   -> pvpWin 1 (XCOM wins).

For each: assert BOTH machines left the battlescape (battle_state.inBattle False,
i.e. reached Debriefing) AND pvpWin == expected AND equal on both machines.

Note: per-machine cutscene identity (win vs lose movie) is NOT introspectable
through the harness, so we assert the reachable invariants (both left + verdict
equal+correct); the cutscene is chosen from that same _coopPVPwin by the
finishBattle override, so an equal+correct verdict is the load-bearing signal.

Run:  python tools/coop_test/test_pvp_skirmish_win_lose.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "47999"


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def _in_battle(gc):
    return bool(battle(gc).get("inBattle"))


def _wait_left_battle(gc, timeout=40):
    """Poll until this machine has left the battlescape (Debriefing/geoscape)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _in_battle(gc):
            return True
        time.sleep(0.5)
    return False


def test_win_lose(fails, tag, alien_player, gamemode, kill_side, expect_win,
                  host_port, client_port):
    print(f"\n--- win/lose {tag} (gm{gamemode}, kill coop_side {kill_side}, "
          f"expect pvpWin {expect_win}) ---")

    host = GameClient("host", host_port, make_user_dir(f"pvp_wl_{tag}_host"))
    client = GameClient("client", client_port, make_user_dir(f"pvp_wl_{tag}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT,
                                           alien_player=alien_player)
        if gm != gamemode:
            _fail(fails, f"{tag}: expected gamemode {gamemode}, got {gm}")
            return

        # The executor (coopTurn==2) is the machine whose end-turn scan computes
        # the verdict and sends the terminating packet.  gm2 -> host, gm3 -> client.
        hb = battle(host)
        executor = host if hb.get("coopTurn") == 2 else client
        peer = client if executor is host else host
        exec_tag = "host" if executor is host else "client"
        print(f"    executor = {exec_tag}")

        # Sanity: how many living combatants on the side we're about to wipe.
        eb = battle(executor)
        living_side = [u for u in eb.get("units", [])
                       if u.get("coop") == kill_side and not u.get("isOut")
                       and u.get("faction") != 2]  # 2 = FACTION_NEUTRAL
        if not living_side:
            _fail(fails, f"{tag}: no living coop_side {kill_side} units to kill")
            return

        # Deterministic host-authority elimination of the whole target side.
        r = executor.cmd({"cmd": "battle_action", "action": "kill_unit",
                          "coop_side": kill_side})
        killed = r.get("killed", [])
        print(f"    killed {len(killed)} coop_side {kill_side} unit(s): {killed}")
        if not r.get("ok") or not killed:
            _fail(fails, f"{tag}: kill_unit failed or killed nothing ({r})")
            return

        # Confirm the target side is actually wiped on the executor.
        eb2 = battle(executor)
        still = [u["id"] for u in eb2.get("units", [])
                 if u.get("coop") == kill_side and not u.get("isOut")
                 and u.get("faction") != 2]
        if still:
            _fail(fails, f"{tag}: coop_side {kill_side} still has living units "
                  f"after kill: {still}")
            return

        # End the executor's turn -> the scan sees a wiped side and terminates.
        executor.ok({"cmd": "battle_action", "action": "end_turn_button"})

        # Both machines should leave the battlescape (their own finishBattle).
        host_left = _wait_left_battle(host)
        client_left = _wait_left_battle(client)
        print(f"    left battle: host={host_left} client={client_left}")
        if not host_left:
            _fail(fails, f"{tag}: HOST did not leave the battlescape")
        if not client_left:
            _fail(fails, f"{tag}: CLIENT did not leave the battlescape")

        # Read the verdict on both machines (pvpWin is exposed in both the
        # in-battle and no-battle branches of battle_state).
        hv = battle(host).get("pvpWin")
        cv = battle(client).get("pvpWin")
        print(f"    pvpWin: host={hv} client={cv} (expected {expect_win})")

        if hv != expect_win:
            _fail(fails, f"{tag}: host pvpWin {hv} != expected {expect_win}")
        if cv != expect_win:
            _fail(fails, f"{tag}: client pvpWin {cv} != expected {expect_win}")
        if hv != cv:
            _fail(fails, f"{tag}: pvpWin mismatch host={hv} client={cv}")

        if host_left and client_left and hv == cv == expect_win:
            print(f"PASS {tag}: both left battle, pvpWin=={expect_win} on both")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, f"{tag}: {e}")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    cases = [
        # tag, alien_player, gamemode, kill_side, expect_win, host_port, client_port
        ("gm2_kill_client", "client", 2, 1, 1, 48970, 48971),
        ("gm2_kill_host",   "client", 2, 0, 2, 48972, 48973),
        ("gm3_kill_client", "host",   3, 1, 2, 48974, 48975),
        ("gm3_kill_host",   "host",   3, 0, 1, 48976, 48977),
    ]
    for (tag, ap, gmode, ks, ew, hp, cp) in cases:
        test_win_lose(fails, tag, ap, gmode, ks, ew, hp, cp)

    print("\n==== PvP win/lose summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  all 4 sub-cases: both machines left the battle with the correct, "
          "matching pvpWin verdict")
    sys.exit(0)


if __name__ == "__main__":
    main()
