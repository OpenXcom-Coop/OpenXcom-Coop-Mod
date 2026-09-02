"""Parallel PVE2: client input waits for the host's PLAYER turn screen.

Both players are on the Alien team (gamemode 4).  The client can reach the
tactical map before the host dismisses NextTurnState; an action intent sent in
that window must be denied by the host.  Once the host closes the screen, the
same real move intent must be admitted.

Run: python tools/coop_test/test_parallel_pve2_turn_screen_gate.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP
import session
import test_skirmish_flow as SK


PORT = "47999"


def top(gc):
    return PVP._top(gc)


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def unit(gc, uid):
    return next((u for u in battle(gc).get("units", []) if u.get("id") == uid), None)


def position(gc, uid):
    u = unit(gc, uid)
    return (u["x"], u["y"], u["z"]) if u else None


def bring_up_pve2_at_boundary(host, client):
    PVP.start_pvp_skirmish_lobby(host, client, PORT, alien_player="client")
    host_row = PVP.row_for(host, "HostPlayer")
    mode = host.ok({"cmd": "lobby_set_team", "row": host_row,
                    "team": "Alien"}).get("gamemode")
    assert mode == 4, f"both Alien rows did not select PVE2/gamemode 4: {mode}"

    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: not session.has_state(host, "LobbyMenu") or None)
    host.ok({"cmd": "newbattle_ok"})

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} battle flow",
                    lambda gc=gc: (session.has_state(gc, "BriefingState")
                                   or session.has_state(gc, "InventoryState")
                                   or session.has_state(gc, "BattlescapeState")) or None,
                    timeout=180, interval=0.5)
        if session.has_state(gc, "BriefingState"):
            gc.ok({"cmd": "close_briefing"})

    # Clear inventory/briefing only.  Deliberately preserve the host's first
    # NextTurnState: that modal is the regression window under test.
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            if session.has_state(gc, "InventoryState"):
                gc.ok({"cmd": "battle_inventory", "action": "ok"})
            elif top(gc) not in ("BattlescapeState", "NextTurnState"):
                gc.cmd({"cmd": "dismiss_popup"})
        if top(host) == "NextTurnState" and top(client) == "NextTurnState":
            client.ok({"cmd": "dismiss_popup"})
            client.wait_for("client closed its PLAYER screen first",
                            lambda: top(client) == "BattlescapeState" or None,
                            timeout=30, interval=0.2)
            assert top(host) == "NextTurnState", \
                "client click unexpectedly closed the host PLAYER screen"
            return
        time.sleep(0.25)
    raise TimeoutError(
        f"PVE2 boundary shape not reached: host={session.states(host)}, "
        f"client={session.states(client)}")


def main():
    host = GameClient(
        "host", 48920,
        make_user_dir("parallel_pve2_screen_host",
                      options={"EnableCoopParallelTurns": True}))
    client = GameClient(
        "client", 48921,
        make_user_dir("parallel_pve2_screen_client",
                      options={"EnableCoopParallelTurns": True}))
    failure = None
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        bring_up_pve2_at_boundary(host, client)

        hb, cb = battle(host), battle(client)
        assert hb.get("coopGamemode") == 4 and cb.get("coopGamemode") == 4, \
            f"fixture is not PVE2: host={hb.get('coopGamemode')} client={cb.get('coopGamemode')}"
        assert hb.get("parallelActive") and cb.get("parallelActive"), \
            f"parallel turns inactive: host={hb} client={cb}"

        candidates = [u for u in cb.get("units", [])
                      if not u.get("isOut") and u.get("faction") == 0
                      and u.get("coop") == 1 and u.get("tu", 0) > 0]
        assert candidates, f"client has no owned PVE2 alien: {cb.get('units')}"

        mover = dest = None
        for candidate in candidates:
            probe = client.cmd({"cmd": "battle_intent", "action": "probe_step",
                                "unit": candidate["id"], "radius": 4, "max": 400})
            if probe.get("ok") and probe.get("steps"):
                mover = candidate["id"]
                step = probe["steps"][0]
                dest = (step["x"], step["y"], step["z"])
                break
        assert mover is not None, "no client-owned PVE2 alien has a walkable tile"

        before_h = position(host, mover)
        before_c = position(client, mover)
        assert before_h == before_c, f"fixture positions differ: {before_h} vs {before_c}"

        denied = client.ok({"cmd": "battle_intent", "action": "move",
                            "unit": mover, "x": dest[0], "y": dest[1], "z": dest[2]})
        time.sleep(3)
        assert position(host, mover) == before_h and position(client, mover) == before_c, (
            "PVE2 client moved while host still had PLAYER NextTurnState: "
            f"host {before_h}->{position(host, mover)}, "
            f"client {before_c}->{position(client, mover)}, response={denied}")
        gate = host.ok({"cmd": "parallel_state"})
        assert gate.get("admitBlocked") == "not_top_state", \
            f"host did not reject the early intent on its modal screen: {gate}"
        print("PASS closed: client intent denied while host PLAYER screen is open")

        host.ok({"cmd": "dismiss_popup"})

        # Closing the PLAYER screen starts the normal PVE2 opponent-AI cycle;
        # it does not immediately reopen the shared player side.  Drive its
        # NextTurn screens and wait for the following PLAYER battlescape.
        deadline = time.time() + 180
        while time.time() < deadline:
            for gc in (host, client):
                state = top(gc)
                if state == "NextTurnState":
                    gc.cmd({"cmd": "dismiss_popup"})
                elif state != "BattlescapeState":
                    gc.cmd({"cmd": "dismiss_popup"})
            hb = battle(host)
            cb = battle(client)
            if (top(host) == "BattlescapeState"
                    and top(client) == "BattlescapeState"
                    and hb.get("side") == 0 and cb.get("side") == 0
                    and hb.get("battleInit") and cb.get("battleInit")
                    and host.ok({"cmd": "parallel_state"}).get("canAdmit")):
                break
            time.sleep(0.5)
        else:
            raise TimeoutError(
                f"next PVE2 player side did not open: host={battle(host)}, "
                f"client={battle(client)}")

        # The AI cycle can change occupancy, so resolve a fresh legal step for
        # the same client-owned alien before checking that admission reopened.
        probe = client.cmd({"cmd": "battle_intent", "action": "probe_step",
                            "unit": mover, "radius": 4, "max": 400})
        assert probe.get("ok") and probe.get("steps"), \
            f"client alien has no step on the reopened player side: {probe}"
        step = probe["steps"][0]
        dest = (step["x"], step["y"], step["z"])
        before_h = position(host, mover)

        client.ok({"cmd": "battle_intent", "action": "move",
                   "unit": mover, "x": dest[0], "y": dest[1], "z": dest[2]})
        host.wait_for("same client move admitted after host closes screen",
                      lambda: position(host, mover) != before_h or None,
                      timeout=30, interval=0.2)
        print("PASS open: same client intent admitted after host closed PLAYER screen")
    except Exception as exc:
        failure = exc
        print(f"[FAIL] {exc}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  {tag} stack: {session.states(gc)}")
                print(f"  {tag} battle: {battle(gc)}")
            except Exception as debug_exc:
                print(f"  {tag} debug failed: {debug_exc}")
    finally:
        host.shutdown(); client.shutdown()

    if failure:
        raise SystemExit(2)
    print("ALL PARALLEL PVE2 TURN-SCREEN GATE TESTS PASSED")


if __name__ == "__main__":
    main()
