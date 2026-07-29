"""Regression test for live Battlescape soldier gifting.

Covers:
  * gift selection is local and separate from the remote active selection;
  * an active player's normal selectedUnit is the exact unit shown/gifted by
    GiftSoldierMenu, including a selection made after initial fallback setup;
  * a player may gift their own soldier while it is not their turn;
  * host and client can transfer different soldiers concurrently;
  * the receiver gets a GiftNoticeState containing the real player/soldier names;
  * a player cannot transfer a soldier they do not own;
  * gifting the final soldier off-turn preserves the waiting/active turn state;
  * gifting the final soldier on the local active turn enters spectator mode;
  * a received soldier becomes giftable immediately without a mouse click;
  * receiving a soldier restores control from spectator mode.

The battle setup is shared with the existing mid-battle resume regression test.

Run:  python tools/coop_test/test_battlescape_soldier_gift.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from test_coop_resume_battle_control import bring_up_mixed_battle, settle_and_assert


def battle(gc):
    return gc.ok({"cmd": "battle_state"})


def living_owned(state, seat):
    return [u for u in state["units"]
            if u["faction"] == 0
            and not u["isOut"]
            and u["health"] > 0
            and u["coop"] == seat
            and u["soldierId"] != -1]


def wait_owner(gc, unit_id, owner, timeout=30):
    def probe():
        state = battle(gc)
        unit = next((u for u in state["units"] if u["id"] == unit_id), None)
        return unit if unit and unit["coop"] == owner else None

    return gc.wait_for(f"unit {unit_id} owner={owner}", probe, timeout=timeout, interval=0.2)


def wait_notice(gc, soldier_name, timeout=30):
    def probe():
        response = gc.ok({"cmd": "get_notices"})
        for message in response.get("messages", []):
            if soldier_name in message and " gave " in message and " to you." in message:
                return message
        return None

    return gc.wait_for(f"gift notice for {soldier_name}", probe, timeout=timeout, interval=0.2)


def dismiss_notices(gc):
    for _ in range(64):
        response = gc.ok({"cmd": "get_notices"})
        if not response.get("messages"):
            return
        gc.ok({"cmd": "dismiss_notice"})
        time.sleep(0.1)
    raise AssertionError("GiftNoticeState stack did not drain")


def concurrent_gift(host, client, host_unit, client_unit):
    results = {}
    failures = []

    def run(tag, gc, unit_id, owner):
        try:
            selected = gc.ok({
                "cmd": "battle_gift_select",
                "unit_id": unit_id,
            })
            assert selected["giftSelectedId"] == unit_id, selected
            assert selected["selectedBeforeId"] == selected["selectedAfterId"], selected
            results[tag] = gc.ok({
                "cmd": "battle_gift",
                "owner": owner,
            })
        except BaseException as exc:  # preserve the original harness failure
            failures.append((tag, exc))

    threads = [
        threading.Thread(target=run, args=("host", host, host_unit["id"], 1)),
        threading.Thread(target=run, args=("client", client, client_unit["id"], 0)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads), "concurrent gift command hung"
    if failures:
        raise failures[0][1]
    return results


def main():
    host = GameClient("host", 47871, make_user_dir("battle-gift-host"))
    client = GameClient("client", 47872, make_user_dir("battle-gift-client"))

    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        bring_up_mixed_battle(host, client)
        settle_and_assert(host, client, "battle gift setup")

        hs = battle(host)
        cs = battle(client)
        host_units = living_owned(hs, 0)
        client_units = living_owned(cs, 1)
        assert len(host_units) >= 2, f"need at least two host soldiers: {host_units}"
        assert client_units, f"need a client soldier: {client_units}"

        # The first Battlescape init must create a valid local gift selection on
        # both peers without requiring a mouse click. The normal selectedUnit may
        # belong to the remote active player on the waiting machine, so the gift
        # selection is validated against each peer's own roster instead of being
        # required to match selectedId.
        for initial_gc, initial_state, initial_seat, initial_target in (
            (host, hs, 0, 1),
            (client, cs, 1, 0),
        ):
            gift_selected = next(
                (u for u in initial_state["units"]
                 if u["id"] == initial_state["giftSelectedId"]),
                None,
            )
            assert gift_selected is not None, initial_state
            assert gift_selected["coop"] == initial_seat, gift_selected

            initial_eligibility = initial_gc.ok({
                "cmd": "battle_gift",
                "owner": initial_target,
                "execute": False,
            })
            assert initial_eligibility["canGift"] is True, initial_eligibility
            assert initial_eligibility["unitId"] == gift_selected["id"], initial_eligibility

            # Custom Battle must use the same GiftSoldierMenu as campaign
            # Battlescape instead of immediately sending the unit to an assumed
            # two-player target. The dialog must be backed by the selected
            # BattleUnit and offer the other player's seat.
            dialog = initial_gc.ok({"cmd": "open_battle_gift_dialog"})
            assert dialog["battleUnitGift"] is True, dialog
            assert dialog["unitId"] == gift_selected["id"], dialog
            assert initial_target in dialog["targets"], dialog
            assert gift_selected["name"] in dialog["title"], dialog
            initial_gc.ok({"cmd": "cancel_dialog"})

        print("PASS: initial gift selection and GiftSoldierMenu work on both peers")

        # Reproduce the mission-start ordering bug deterministically. The local
        # gift fallback can be initialized first, and Battlescape may then call
        # SavedBattleGame::setSelectedUnit() with a different soldier for the HUD.
        # No mouse/gift-selection command is used here: setSelectedUnit() itself
        # must synchronize the locally owned gift target. Otherwise the dialog
        # can show and transfer an older soldier than the one visible in the HUD.
        if hs["coopTurn"] == 2:
            active_gc, active_state, active_seat, active_target = host, hs, 0, 1
        else:
            assert cs["coopTurn"] == 2, (hs, cs)
            active_gc, active_state, active_seat, active_target = client, cs, 1, 0

        active_owned = living_owned(active_state, active_seat)
        assert len(active_owned) >= 2, (active_seat, active_owned)
        different_selected = next(
            unit for unit in active_owned
            if unit["id"] != active_state["selectedId"]
        )

        active_gc.ok({
            "cmd": "battle_action",
            "action": "select",
            "unit": different_selected["id"],
        })
        synchronized = battle(active_gc)
        assert synchronized["selectedId"] == different_selected["id"], synchronized
        assert synchronized["giftSelectedId"] == different_selected["id"], synchronized

        synchronized_dialog = active_gc.ok({"cmd": "open_battle_gift_dialog"})
        assert synchronized_dialog["unitId"] == different_selected["id"], synchronized_dialog
        assert different_selected["name"] in synchronized_dialog["title"], synchronized_dialog
        assert active_target in synchronized_dialog["targets"], synchronized_dialog
        active_gc.ok({"cmd": "cancel_dialog"})
        print("PASS: HUD selection and GiftSoldierMenu use the same active soldier")

        # The off-turn machine must still be allowed to transfer one of its own
        # soldiers. This calls the same C++ ownership gate used by Game.cpp.
        if hs["coopTurn"] != 2:
            off_gc, off_unit, target = host, host_units[0], 1
        else:
            assert cs["coopTurn"] != 2, "expected exactly one active player turn"
            off_gc, off_unit, target = client, client_units[0], 0

        local_selection = off_gc.ok({
            "cmd": "battle_gift_select",
            "unit_id": off_unit["id"],
        })
        assert local_selection["coopTurn"] != 2, local_selection
        assert local_selection["giftSelectedId"] == off_unit["id"], local_selection
        assert local_selection["selectedBeforeId"] == local_selection["selectedAfterId"], local_selection

        eligibility = off_gc.ok({
            "cmd": "battle_gift",
            "owner": target,
            "execute": False,
        })
        assert eligibility["coopTurn"] != 2, eligibility
        assert eligibility["unitId"] == off_unit["id"], eligibility
        assert eligibility["canGift"] is True, eligibility
        print("PASS: off-turn gift selection is separate from the active selected unit")

        # Send both directions without waiting for either ownership packet. The
        # transfers concern distinct units and must converge on both replicas.
        host_unit = host_units[0]
        client_unit = client_units[0]
        results = concurrent_gift(host, client, host_unit, client_unit)
        assert results["host"]["beforeOwner"] == 0 and results["host"]["afterOwner"] == 1
        assert results["client"]["beforeOwner"] == 1 and results["client"]["afterOwner"] == 0

        for gc in (host, client):
            wait_owner(gc, host_unit["id"], 1)
            wait_owner(gc, client_unit["id"], 0)

        # Receiving a soldier now intentionally makes that soldier the local
        # gift target. The old test expected the gift selection to be cleared,
        # but that would recreate the bug where the received soldier could not
        # be gifted again until it was clicked with the left mouse button.
        host_after_swap = battle(host)
        client_after_swap = battle(client)
        assert host_after_swap["giftSelectedId"] == client_unit["id"], host_after_swap
        assert client_after_swap["giftSelectedId"] == host_unit["id"], client_after_swap

        host_immediate_return = host.ok({
            "cmd": "battle_gift",
            "owner": 1,
            "execute": False,
        })
        client_immediate_return = client.ok({
            "cmd": "battle_gift",
            "owner": 0,
            "execute": False,
        })
        assert host_immediate_return["unitId"] == client_unit["id"], host_immediate_return
        assert host_immediate_return["canGift"] is True, host_immediate_return
        assert client_immediate_return["unitId"] == host_unit["id"], client_immediate_return
        assert client_immediate_return["canGift"] is True, client_immediate_return
        print("PASS: simultaneous gifts converged and received soldiers are immediately giftable")

        host_notice = wait_notice(host, client_unit["name"])
        client_notice = wait_notice(client, host_unit["name"])
        assert client_unit["name"] in host_notice
        assert host_unit["name"] in client_notice
        print(f"PASS: receiver popups shown: {host_notice!r} / {client_notice!r}")
        dismiss_notices(host)
        dismiss_notices(client)

        # The old owner must not be able to send the same unit again after its
        # ownership changed on that machine.
        rejected = host.cmd({
            "cmd": "battle_gift_select",
            "unit_id": host_unit["id"],
        })
        assert not rejected.get("ok"), rejected
        assert battle(host)["units"]
        wait_owner(host, host_unit["id"], 1)
        print("PASS: a player cannot gift a soldier owned by another seat")

        # Determine which machine currently owns the active turn. The waiting
        # player is allowed to gift soldiers, but gifting the final soldier must
        # NOT replace the still-active remote turn with spectator mode.
        hs = battle(host)
        cs = battle(client)
        assert (hs["coopTurn"] == 2) != (cs["coopTurn"] == 2), (hs, cs)

        if hs["coopTurn"] == 2:
            active_gc, active_peer, active_seat = host, client, 0
            waiting_gc, waiting_peer, waiting_seat = client, host, 1
        else:
            active_gc, active_peer, active_seat = client, host, 1
            waiting_gc, waiting_peer, waiting_seat = host, client, 0

        # A soldier received by the player whose turn is active must become the
        # local gift target immediately. The ownership packet does not run the
        # mouse-click or selectPlayerUnit() paths, so without an explicit update
        # getGiftSelectedBattleUnit() remains null or points at an older unit.
        # Test the exact regression by receiving and returning a soldier without
        # issuing battle_gift_select on the active machine.
        active_receive_candidate = living_owned(battle(waiting_gc), waiting_seat)[0]
        waiting_gc.ok({
            "cmd": "battle_gift_select",
            "unit_id": active_receive_candidate["id"],
        })
        waiting_gc.ok({"cmd": "battle_gift", "owner": active_seat})
        wait_owner(waiting_gc, active_receive_candidate["id"], active_seat)
        wait_owner(active_gc, active_receive_candidate["id"], active_seat)

        received_state = active_gc.wait_for(
            "received soldier becomes active gift selection",
            lambda: (lambda state: state
                     if state["giftSelectedId"] == active_receive_candidate["id"]
                     else None)(battle(active_gc)),
            timeout=30,
            interval=0.2,
        )
        assert received_state["coopTurn"] == 2, received_state

        immediate_return = active_gc.ok({
            "cmd": "battle_gift",
            "owner": waiting_seat,
            "execute": False,
        })
        assert immediate_return["unitId"] == active_receive_candidate["id"], immediate_return
        assert immediate_return["canGift"] is True, immediate_return

        # Return it using the automatically updated gift selection, still with no
        # explicit selection command on the active machine.
        active_gc.ok({"cmd": "battle_gift", "owner": waiting_seat})
        wait_owner(active_gc, active_receive_candidate["id"], waiting_seat)
        wait_owner(waiting_gc, active_receive_candidate["id"], waiting_seat)
        dismiss_notices(active_gc)
        dismiss_notices(waiting_gc)
        print("PASS: active player can immediately re-gift a received soldier")

        waiting_before = battle(waiting_gc)
        assert waiting_before["coopTurn"] != 2, waiting_before
        assert waiting_before["coopTurn"] != 4, waiting_before
        assert waiting_before["playerTurn"] != 4, waiting_before
        waiting_selected_before = waiting_before["selectedId"]

        waiting_units = living_owned(waiting_before, waiting_seat)
        assert waiting_units, "waiting player unexpectedly owns no soldiers"
        last_waiting_given = None
        for unit in waiting_units:
            last_waiting_given = unit
            waiting_gc.ok({"cmd": "battle_gift_select", "unit_id": unit["id"]})
            waiting_gc.ok({"cmd": "battle_gift", "owner": active_seat})
            wait_owner(waiting_gc, unit["id"], active_seat)
            wait_owner(waiting_peer, unit["id"], active_seat)

        waiting_after = battle(waiting_gc)
        assert not living_owned(waiting_after, waiting_seat), waiting_after
        assert waiting_after["coopTurn"] == waiting_before["coopTurn"], (waiting_before, waiting_after)
        assert waiting_after["playerTurn"] == waiting_before["playerTurn"], (waiting_before, waiting_after)
        assert waiting_after["coopTurn"] != 4 and waiting_after["playerTurn"] != 4, waiting_after
        assert waiting_after["selectedId"] == waiting_selected_before, (waiting_before, waiting_after)
        print("PASS: gifting the final soldier off-turn preserves the remote active turn")

        wait_notice(active_gc, last_waiting_given["name"])
        dismiss_notices(active_gc)

        # Return one soldier to the waiting player. Receiving it while off-turn
        # must also preserve the active player's normal selectedUnit and turn.
        active_gc.ok({"cmd": "battle_gift_select", "unit_id": last_waiting_given["id"]})
        active_gc.ok({"cmd": "battle_gift", "owner": waiting_seat})
        wait_owner(active_gc, last_waiting_given["id"], waiting_seat)
        wait_owner(waiting_gc, last_waiting_given["id"], waiting_seat)
        waiting_restored = battle(waiting_gc)
        assert waiting_restored["coopTurn"] == waiting_before["coopTurn"], waiting_restored
        assert waiting_restored["playerTurn"] == waiting_before["playerTurn"], waiting_restored
        assert waiting_restored["selectedId"] == waiting_selected_before, waiting_restored
        wait_notice(waiting_gc, last_waiting_given["name"])
        dismiss_notices(waiting_gc)
        print("PASS: receiving a soldier off-turn preserves the remote active selection")

        # The active player still enters spectator mode immediately when they
        # gift away their final living soldier during their own turn.
        active_before = battle(active_gc)
        assert active_before["coopTurn"] == 2, active_before
        active_units = living_owned(active_before, active_seat)
        assert active_units, "active player unexpectedly owns no soldiers"
        last_active_given = None
        for unit in active_units:
            last_active_given = unit
            active_gc.ok({"cmd": "battle_gift_select", "unit_id": unit["id"]})
            active_gc.ok({"cmd": "battle_gift", "owner": waiting_seat})
            wait_owner(active_gc, unit["id"], waiting_seat)
            wait_owner(active_peer, unit["id"], waiting_seat)

        active_gc.wait_for(
            "active player spectator mode",
            lambda: (lambda state: state if state["coopTurn"] == 4 else None)(battle(active_gc)),
            timeout=30,
            interval=0.2,
        )
        assert not living_owned(battle(active_gc), active_seat)
        print("PASS: gifting the final soldier on-turn enters spectator mode")

        wait_notice(waiting_gc, last_active_given["name"])
        dismiss_notices(waiting_gc)

        # Give one soldier back to the active-turn spectator. The local roster
        # refresh should select it and restore the active turn.
        waiting_gc.ok({"cmd": "battle_gift_select", "unit_id": last_active_given["id"]})
        waiting_gc.ok({"cmd": "battle_gift", "owner": active_seat})
        wait_owner(waiting_gc, last_active_given["id"], active_seat)
        wait_owner(active_gc, last_active_given["id"], active_seat)
        restored_active = active_gc.wait_for(
            "active player leaves spectator mode",
            lambda: (lambda state: state if state["coopTurn"] == 2 else None)(battle(active_gc)),
            timeout=30,
            interval=0.2,
        )

        # Restoring selectedUnit from spectator mode does not pass through the
        # normal click/selectPlayerUnit paths. The separate gift selection must
        # therefore be synchronized by refreshBattleGiftControlState(), otherwise
        # the received soldier cannot be gifted again until it is clicked.
        assert restored_active["selectedId"] == last_active_given["id"], restored_active
        assert restored_active["giftSelectedId"] == last_active_given["id"], restored_active
        immediate_gift = active_gc.ok({
            "cmd": "battle_gift",
            "owner": waiting_seat,
            "execute": False,
        })
        assert immediate_gift["unitId"] == last_active_given["id"], immediate_gift
        assert immediate_gift["canGift"] is True, immediate_gift

        wait_notice(active_gc, last_active_given["name"])
        print("PASS: spectator restore synchronizes gift selection without another click")

        print("ALL BATTLESCAPE SOLDIER GIFT TESTS PASSED")
    finally:
        host.shutdown(); client.shutdown()


if __name__ == "__main__":
    main()
