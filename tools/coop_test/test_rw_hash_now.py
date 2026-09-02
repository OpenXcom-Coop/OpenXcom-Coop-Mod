"""R2-P11 (rewrite spike, SPIKE-RUNBOOK.md RB-D32) joint determinism check.

This doubles as the G4 determinism check the runbook's R2-P11 acceptance asks
for: boot a G3-path coop skirmish battle (the exact same lobby-flow drive
test_rw_handshake.py's main() uses for its own steps 1-7 - see that file's
docstring for why the drive is narrower than test_skirmish_flow.py's), then
assert `hash_now {"full":true}` is bucket-for-bucket EQUAL on both machines at
t=0 (before any ACTION - SS2.8's own boundary-sweep language), and that
`event_state` reports a sane, matching picture of the same live battle from
each machine's own side (phase Active both, hostSim true only on the host,
distinct localSeat per machine, and a seq stream that has emitted exactly the
bring-up reveal traffic and nothing else, fully applied, queue drained).

RW-REVEAL-SYNC (SS2.4a) CHANGED THE t=0 SEQ BASELINE. "t=0" no longer means
"nothing has been emitted": revealed tiles are game state now, and the host's
own bring-up (BriefingState OK -> BattlescapeState -> equip-screen dismissal ->
startFirstTurn's recalculateFOV) discovers several hundred tiles AFTER the
handshake blob was snapshotted. Those ship as standalone `bt_ev{kind:"reveal"}`
envelopes from the quiescent flush (CoopReveal::flushQuiescent), so by the time
this check runs the host has emitted REVEAL_SEQS_AT_T0 of them and the client
has applied every one. What "t=0" still means, and what this file asserts, is:
no ACTION has run, the two seq counters agree, and the queue is drained on both
machines. See the constant's own comment for why the count is what it is.

RESOLVED FINDING (RW-REVEAL-SYNC): with the binTiles fog mask removed from the
saveBlob bucket (SharedEcon.cpp), the per-tile `discovered` bits are now INSIDE
the hash rather than masked out of it - so the 8/8 equality below is a strictly
stronger statement than it used to be, and `mapDiscoveredFloor` equality is
asserted directly alongside it as the human-readable witness (before this packet
the two machines sat at host=1044 vs client=536 and the hash could not see it).

Uses session.py's assert_hash_clean() (R2-P11's successor of the legacy
assert_sync_clean()) rather than duplicating the hash_now round-trip.

RESOLVED FINDING (orchestrator, post-R2-P11): all 7 BattleHashSet buckets
(terrain/fire/smoke/items/unitsCore/unitsStats/itemIdCtr) were byte-for-byte
EQUAL from the start; only `saveBlob` reproducibly mismatched. Root-caused by
dumping+diffing the two machines' emitted battle YAML: the SOLE unexcluded
divergence was `strTarget` + `strCraftOrBase` - two DISPLAY-ONLY briefing/HUD
labels ("LANDING SITE-0", "CRAFT> SKYRANGER-1") set EXCLUSIVELY by BriefingState
(BriefingState.cpp:159-185). The host runs BriefingState; the thin client loads
the streamed blob straight to BattlescapeState (no briefing), so they stay empty
on the client. No sim effect. Fixed by adding both keys to
SharedEcon::saveBlobExcludedTopKey (same per-battle display class as the CR-1
sec-6 fields). Client HUD showing an empty mission/craft name is a cosmetic
real-play gap (r3/r4 polish), not a determinism defect. With that exclusion this
check is 8/8-bucket EQUAL.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

# RW-REVEAL-SYNC: how many standalone `bt_ev{kind:"reveal"}` envelopes the HOST's
# quiescent flush ships during bring-up. One per QUIESCENT TICK that finds
# something newly discovered, and everything a single frame discovers coalesces
# into ONE delta - so this is a small constant, not "one per revealed tile".
#
# Why exactly TWO on this fixture (measured 2026-09-02, and structurally
# expected - the host log names both):
#   seq 1, the moment the host reaches phase Active (onReady, still sitting in
#          BriefingState): the VOID-TILE baseline catch-up. SavedBattleGame::save
#          skips void tiles (SavedBattleGame.cpp:568-580), so discovered bits on
#          empty air tiles never ride the handshake blob; CoopReveal::
#          seedPublished deliberately leaves them unpublished and the first flush
#          ships them. Measured 668 tiles on this fixture.
#   seq 2, the equip-screen dismissal burst: BriefingState::btnOkClick stacks
#          NextTurnState + InventoryState ON TOP of BattlescapeState and
#          Game::run() only init()s/think()s _states.back(), so the host's own
#          bring-up FOV (InventoryState dtor recalculateFOV + startFirstTurn +
#          BattlescapeState::init -> updateSoldierInfo(checkFOV)) all happens at
#          dismissal. Measured 784 tiles.
#
# Asserted exactly (not >=) so a change that starts spraying reveal traffic per
# tick is a test failure, not a silent regression. A different value here is not
# automatically a bug - it means the host's bring-up reveals landed on a
# different number of quiescent ticks - but it IS a change worth looking at
# deliberately. The load-bearing invariants (emitted == applied, nothing left
# unpublished, per-part parity, 8/8 hash) are asserted separately below and do
# not depend on this count.
REVEAL_SEQS_AT_T0 = 2


def top_state(gc):
    st = [s.replace("class OpenXcom::", "") for s in session.states(gc)]
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


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


def main():
    port = "47986"
    host_dir = make_user_dir("rw_hashnow_host")
    client_dir = make_user_dir("rw_hashnow_client")
    host = GameClient("host", 48790, host_dir)
    client = GameClient("client", 48791, client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # --- lobby bring-up + battle start (test_rw_handshake.py's own drive) ---
        skirmish_host(host, port)
        skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"})
        client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)

        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={session.states(host)}"

        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=60)

        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)
        assert session.has_state(host, "BattlescapeState"), \
            f"host should reach BattlescapeState, stack={session.states(host)}"
        print("PASS: both machines in BattlescapeState (G3-path handshake complete)")

        # RW-FIX-TURN (R1): dismiss the host's battle-start overlays
        # (NextTurnState + InventoryState, pushed by BriefingState::btnOkClick)
        # BEFORE the full compare. The client mirrors the first-turn counter
        # (turn 0->1) right after sending battle_ready; the host reaches 1
        # only when its equip screen closes (InventoryState::btnOkClick ->
        # startFirstTurn). Comparing pre-dismissal would red saveBlob on the
        # turn key alone. Post-dismissal is the STRONGER assertion (8/8 at
        # the point that was previously known-divergent), and t=0 semantics
        # survive: dismissal emits no evs, lastSeqEmitted stays 0.
        def _top(gc):
            st = session.states(gc)
            return st[-1].replace("class OpenXcom::", "") if st else ""

        deadline = time.time() + 10
        while time.time() < deadline and _top(host) != "BattlescapeState":
            host.ok({"cmd": "inject_input", "kind": "key", "key": 27})
            time.sleep(0.3)
        assert _top(host) == "BattlescapeState", \
            f"host battle-start overlays never cleared, stack={session.states(host)}"

        # settle so both sides' battle_ready/onReady bookkeeping (phase -> Active)
        # has landed before the introspection reads below
        time.sleep(2)

        # --- event_state: both machines, live battle, t=0 (nothing emitted yet) ---
        host_es = host.cmd({"cmd": "event_state"})
        client_es = client.cmd({"cmd": "event_state"})
        assert host_es.get("ok") and client_es.get("ok"), \
            f"event_state failed: host={host_es} client={client_es}"

        assert host_es["phase"] == "Active", f"host phase should be Active: {host_es}"
        assert client_es["phase"] == "Active", f"client phase should be Active: {client_es}"
        assert host_es["hostSim"] is True, f"host hostSim should be true: {host_es}"
        assert client_es["hostSim"] is False, f"client hostSim should be false: {client_es}"
        assert host_es["localSeat"] != client_es["localSeat"], \
            f"host/client localSeat should differ: host={host_es['localSeat']} client={client_es['localSeat']}"
        assert host_es["battleId"] == client_es["battleId"] and host_es["battleId"] != 0, \
            f"host/client battleId should match and be nonzero: host={host_es} client={client_es}"
        assert host_es["desyncSeen"] is False and client_es["desyncSeen"] is False, \
            f"neither machine should have desynced yet: host={host_es} client={client_es}"
        # t=0 (no ACTION has run): the only seq traffic is RW-REVEAL-SYNC's
        # bring-up reveal flush, fully emitted on the host and fully applied on
        # the client, with nothing left queued on either side.
        host_rs = host.cmd({"cmd": "reveal_state"})
        client_rs = client.cmd({"cmd": "reveal_state"})
        print("HOST reveal_state:  ", json.dumps(host_rs, sort_keys=True))
        print("CLIENT reveal_state:", json.dumps(client_rs, sort_keys=True))
        assert host_rs.get("ok") and client_rs.get("ok"), \
            f"reveal_state failed: host={host_rs} client={client_rs}"
        # The load-bearing pair, independent of REVEAL_SEQS_AT_T0's exact value:
        # the host has nothing left to publish, and the client applied every seq
        # the host emitted.
        assert host_rs["unpublished"] is False, (
            f"host still has unpublished reveal bits at t=0 - the quiescent flush "
            f"did not run or did not drain: {host_rs}")
        assert client_es["lastSeqApplied"] == host_es["lastSeqEmitted"], (
            f"client applied {client_es['lastSeqApplied']} of the host's "
            f"{host_es['lastSeqEmitted']} emitted seqs at t=0: host={host_es} client={client_es}")
        for part in ("floor", "westwall", "northwall"):
            assert host_rs[part] == client_rs[part], (
                f"discovered {part} count differs at t=0: host={host_rs[part]} "
                f"client={client_rs[part]} (of {host_rs['mapSizeXYZ']} tiles) - RW-REVEAL-SYNC "
                "did not converge the two machines' fog of war")
        print(f"PASS reveal_state: floor/westwall/northwall = {host_rs['floor']}/"
              f"{host_rs['westwall']}/{host_rs['northwall']} on BOTH machines, "
              "host has nothing unpublished")

        assert host_es["lastSeqEmitted"] == REVEAL_SEQS_AT_T0, (
            f"host lastSeqEmitted should be {REVEAL_SEQS_AT_T0} at t=0 (the bring-up reveal "
            f"flush, RW-REVEAL-SYNC) - see REVEAL_SEQS_AT_T0's comment: {host_es}")
        assert client_es["lastSeqApplied"] == REVEAL_SEQS_AT_T0, (
            f"client lastSeqApplied should be {REVEAL_SEQS_AT_T0} at t=0 (every bring-up "
            f"reveal applied): {client_es}")
        assert host_es["queueDepth"] == 0 and client_es["queueDepth"] == 0, \
            f"queueDepth should be 0 on both at t=0: host={host_es} client={client_es}"

        print("PASS event_state: phase Active both, hostSim host=True client=False, "
              f"localSeat host={host_es['localSeat']} client={client_es['localSeat']}, "
              f"battleId={host_es['battleId']}, lastSeqEmitted={host_es['lastSeqEmitted']}, "
              f"lastSeqApplied={client_es['lastSeqApplied']}, queueDepth=0/0")
        print("HOST event_state:", json.dumps(host_es, sort_keys=True))
        print("CLIENT event_state:", json.dumps(client_es, sort_keys=True))

        # --- RW-REVEAL-SYNC: the human-readable witness for the unmasked hash ---
        hb = host.cmd({"cmd": "battle_state"})
        cb = client.cmd({"cmd": "battle_state"})
        assert hb.get("mapDiscoveredFloor") == cb.get("mapDiscoveredFloor"), (
            f"mapDiscoveredFloor differs at t=0: host={hb.get('mapDiscoveredFloor')} "
            f"client={cb.get('mapDiscoveredFloor')} (of {hb.get('mapSizeXYZ')} tiles) - the "
            "host's bring-up reveals did not reach the client, or the client computed its own")
        print(f"PASS reveal parity: mapDiscoveredFloor == {hb.get('mapDiscoveredFloor')} on both "
              f"machines ({hb.get('mapSizeXYZ')} tiles total)")

        # --- joint determinism check: hash_now {full:true} equal on both machines ---
        host_h, client_h = session.assert_hash_clean(host, client, full=True, what="t=0 joint determinism")
        assert len(host_h) == 8, (
            f"hash_now full returned {len(host_h)} buckets, expected 8 ({sorted(host_h)}) - "
            "the spike bucket set changed under this test")

        print("PASS: hash_now full=true EQUAL on both machines at t=0 "
              f"({len(host_h)}/8 buckets, saveBlob now UNMASKED over binTiles)")
        print("HOST   h:", json.dumps(host_h, indent=2, sort_keys=True))
        print("CLIENT h:", json.dumps(client_h, indent=2, sort_keys=True))

        print("ALL R2-P11 JOINT DETERMINISM CHECKS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
