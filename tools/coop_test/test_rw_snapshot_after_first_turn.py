"""FX-1 (WAVE1-RUNBOOK.md REV E.1, WV-D56): the coop blob SNAPSHOT + the
`battle_offer` that advertises it move to AFTER `SavedBattleGame::
startFirstTurn()`, so the blob the client loads already carries `_turn == 1`
and the POST-`randomizeItemLocations()` item positions - not the pre-turn-1
state offerBattle() used to snapshot at battle-generation time.

AI-neutral by construction: t=0 only, no side ever advances; contact-free and
door-free are irrelevant because nothing walks.

WHY BASE DEFENSE, SPECIFICALLY. `SavedBattleGame::startFirstTurn()`'s
`randomizeItemLocations()` is a NO-OP unless the battle carries a non-empty
`_storageSpace` - the base's item-storage tile list, which only a
`STR_BASE_DEFENSE` mission generates (a craft-entry mission has no base
storage to scatter). Every other mission class in this build's stock ruleset
would make this file's core regression - "the client's item positions match
the HOST's POST-randomize positions" - vacuously true (nothing moved on
EITHER machine, so "equal" proves nothing about WHEN the snapshot was taken).
This is the same reasoning W1-P10's door atom fixture (repro_atom_door.py)
used to REJECT a candidate mission with no doors; here the "feature" the
fixture must exercise is randomizeItemLocations() itself.

THE EXACT REGRESSION THIS FILE GUARDS (measured, pre-fix, on a build with the
snapshot still taken inside offerBattle()): the client's `battle_items` census
showed at least one item at a DIFFERENT `(tx,ty,tz)` than the host's own copy
of the same item id - `{'tx':8,'ty':7,'tz':8}` on one machine against a
different tile on the other - because the client's blob was frozen BEFORE
`randomizeItemLocations()` scattered the base's stores, while the host kept
simulating past that point. `items` and `saveBlob` are the two hash buckets
that regression breaks; this file asserts both are explicitly present and
EQUAL in the `hash_now {full:true}` sweep, not merely "the sweep passed".

RW-FIX-TURN BECOMES A TRIPWIRE (WV-D56 consequence 1): under the new
sequencing the client's blob already carries `turn == 1`, so
`coopClientMirrorFirstTurnCounter()`'s compensating write is now UNREACHABLE
in the normal case - reaching it (a non-zero `event_state.turnMirrorFired` on
the client) means the snapshot was taken too early, i.e. this file's own
fix regressed. Asserted at zero, not merely "the client shows turn 1" (which
the tripwire's compensating write would ALSO produce, silently).

Run:  python tools/coop_test/test_rw_snapshot_after_first_turn.py
      (its own shell invocation - one harness run at a time, machine-wide.)

EXIT CODES: 0 pass, 2 FAIL, 3 SKIP (this build's NEW BATTLE screen does not
offer STR_BASE_DEFENSE - a fact about the loaded ruleset, never about FX-1).
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

EXIT_PASS, EXIT_FAIL, EXIT_SKIP = 0, 2, 3

MISSION = "STR_BASE_DEFENSE"


# ---------------------------------------------------------------- helpers ---
def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def battle_state(gc):
    return gc.cmd({"cmd": "battle_state"})


def event_state(gc):
    return gc.cmd({"cmd": "event_state"})


def skirmish_host(host, port, player="HostPlayer"):
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": port, "player": player})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))


def skirmish_client_at_browser(client):
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))


def bring_up_lobby(host, client, port):
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    skirmish_host(host, port)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


def battle_items(gc):
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed: {r}"
    return r


# ------------------------------------------------------------------- main ---
def main():
    port = "47998"
    host_dir = make_user_dir("rw_snap_host")
    client_dir = make_user_dir("rw_snap_client")
    host = GameClient("host", 48860, host_dir)
    client = GameClient("client", 48861, client_dir)
    try:
        bring_up_lobby(host, client, port)

        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

        # === fixture gate: this build must offer STR_BASE_DEFENSE ============
        mr = host.cmd({"cmd": "newbattle_mission", "type": MISSION})
        if not mr.get("ok"):
            print(f"SKIP: this build's NEW BATTLE screen does not offer {MISSION!r} - "
                  f"offered: {mr.get('missionTypes')}")
            sys.exit(EXIT_SKIP)
        print(f"fixture: {MISSION} selected (offered types: {mr.get('missionTypes')})")

        # === generate the battle; host into BriefingState ====================
        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"),
                      timeout=30)

        bs_pre = battle_state(host)
        assert bs_pre.get("phase") == "Handshake", (
            f"host phase should be Handshake before the briefing OK click - "
            f"prepareBattleOffer() should have run with nothing sent yet: {bs_pre}")
        assert bs_pre.get("missionType") == MISSION, (
            f"host generated missionType={bs_pre.get('missionType')!r}, expected "
            f"{MISSION!r}")
        print(f"PASS: host generated {MISSION}, phase=Handshake (nothing sent yet)")

        # === dismiss the host's briefing - this is where emitPreparedOffer() ==
        # === actually fires, AFTER startFirstTurn() (WV-D56) =================
        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)
        session.dismiss_battle_start_overlays(host)   # NextTurnState only (equip frozen)
        assert top_state(host) == "BattlescapeState", \
            f"host should be on BattlescapeState after dismissing overlays, stack={states(host)}"

        # === 2. host.battle_state.turn == 1 right after closing the briefing =
        hbs = battle_state(host)
        assert hbs.get("turn") == 1, (
            f"host battle_state.turn == {hbs.get('turn')}, expected 1 - "
            "SavedBattleGame::startFirstTurn() did not run (or did not set _turn) "
            "in BriefingState::btnOkClick's freeze branch")
        print("PASS: host battle_state.turn == 1 right after closing the briefing")

        # === client: reaches inBattle + turn==1 (its blob already carries it) =
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=60)
        time.sleep(1)  # let both logs/handshake bookkeeping settle
        session.dismiss_client_briefing(client)   # W1-P3 read-only entry briefing

        cbs = battle_state(client)
        assert cbs.get("inBattle") is True, f"client inBattle should be True: {cbs}"
        assert cbs.get("turn") == 1, (
            f"client battle_state.turn == {cbs.get('turn')}, expected 1 - the "
            f"loaded blob should already carry turn 1 under WV-D56: {cbs}")
        print("PASS: client inBattle=True, battle_state.turn == 1 (the loaded blob "
              "already carried it - WV-D56)")

        # === 3. RW-FIX-TURN tripwire: must NOT have fired on the client =======
        ces = event_state(client)
        assert ces.get("turnMirrorFired") == 0, (
            f"client event_state.turnMirrorFired == {ces.get('turnMirrorFired')}, "
            "expected 0 - the WV-D56 tripwire fired, meaning the loaded blob "
            "carried turn 0 and the host's snapshot was taken BEFORE "
            f"startFirstTurn(): {ces}")
        print("PASS: event_state.turnMirrorFired == 0 on the client (the WV-D56 "
              "tripwire never fired)")

        # === both machines reach phase Active =================================
        host.wait_for("host phase Active",
                      lambda: (battle_state(host).get("phase") == "Active") or None,
                      timeout=30)
        client.wait_for("client phase Active",
                        lambda: (battle_state(client).get("phase") == "Active") or None,
                        timeout=30)
        hes = event_state(host)
        ces = event_state(client)
        assert hes.get("phase") == "Active" and ces.get("phase") == "Active", (
            f"event_state.phase should be Active on both: host={hes.get('phase')} "
            f"client={ces.get('phase')}")
        print("PASS: event_state.phase == 'Active' on both machines")

        # === 5. hash_now full:true - all buckets EQUAL, items+saveBlob present
        hh, ch = session.assert_hash_clean(host, client, full=True,
                                           what="t=0, post-startFirstTurn snapshot")
        assert "items" in hh, f"hash_now full did not carry the 'items' bucket: {sorted(hh)}"
        assert "saveBlob" in hh, f"hash_now full did not carry the 'saveBlob' bucket: {sorted(hh)}"
        print(f"PASS: hash_now full=true - ALL {len(hh)} buckets EQUAL "
              f"(incl. items, saveBlob): {sorted(hh)}")

        # === 6. battle_items: census counts equal, every item's (tx,ty,tz) ====
        # === matches - the exact {'tx':8,'ty':7,'tz':8}-class regression =====
        hi = battle_items(host)
        ci = battle_items(client)
        assert hi["total"] == ci["total"], (
            f"battle_items total differs: host={hi['total']} client={ci['total']}")
        assert hi["counts"] == ci["counts"], (
            f"battle_items per-type counts differ: host={hi['counts']} "
            f"client={ci['counts']}")

        h_by_id = {it["id"]: it for it in hi["items"]}
        c_by_id = {it["id"]: it for it in ci["items"]}
        assert set(h_by_id) == set(c_by_id), (
            f"battle_items id SETS differ: host-only={sorted(set(h_by_id) - set(c_by_id))} "
            f"client-only={sorted(set(c_by_id) - set(h_by_id))}")

        pos_mismatches = []
        for iid, hit in h_by_id.items():
            cit = c_by_id[iid]
            h_pos = (hit.get("tx"), hit.get("ty"), hit.get("tz"), hit.get("onTile"))
            c_pos = (cit.get("tx"), cit.get("ty"), cit.get("tz"), cit.get("onTile"))
            if h_pos != c_pos:
                pos_mismatches.append((iid, hit.get("type"), h_pos, c_pos))
        assert not pos_mismatches, (
            f"{len(pos_mismatches)} item(s) sit at a DIFFERENT (tx,ty,tz) on the two "
            f"machines - the exact pre-fix regression this file guards (item ids ride "
            f"the same blob, so a position mismatch here means the two machines "
            f"snapshotted at different points in randomizeItemLocations()): "
            f"{pos_mismatches[:10]}")
        print(f"PASS: battle_items - {hi['total']} items on both machines, counts "
              f"EQUAL ({hi['counts']}), every item's (tx,ty,tz,onTile) matches")

        print("ALL FX-1 SNAPSHOT-AFTER-FIRST-TURN CHECKS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
