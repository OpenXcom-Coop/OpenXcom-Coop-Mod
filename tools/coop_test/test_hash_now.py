"""Joint determinism check at battle start.

Boot a coop skirmish battle (the same lobby-flow drive test_handshake.py's
main() uses - see that file's docstring for why the drive is narrower than
test_skirmish_flow.py's), then assert `hash_now {"full":true}` is
bucket-for-bucket EQUAL on both machines at t=0 (before any ACTION), and that
`event_state` reports a sane, matching picture of the same live battle from
each machine's own side (phase Active both, hostSim true only on the host,
distinct localSeat per machine, and a seq stream that has emitted exactly the
bring-up traffic and nothing else, fully applied, queue drained).

THE t=0 SEQ BASELINE. "t=0" does not mean
"nothing has been emitted": revealed tiles are game state, and the host's
own bring-up (BriefingState OK -> BattlescapeState -> equip-screen dismissal ->
startFirstTurn's recalculateFOV) discovers several hundred tiles AFTER the
handshake blob was snapshotted. Those ship as standalone `bt_ev{kind:"reveal"}`
envelopes from the quiescent flush (CoopReveal::flushQuiescent), and the
pre-battle equip phase adds its own `sync` evs, so by the time this check runs
the host has emitted REVEAL_SEQS_AT_T0 seqs and the client has applied every
one. What "t=0" still means, and what this file asserts, is:
no ACTION has run, the two seq counters agree, and the queue is drained on both
machines. See the constant's own comment for why the count is what it is.

FOG IN THE HASH: with no binTiles fog mask in the
saveBlob bucket (SharedEcon.cpp), the per-tile `discovered` bits are INSIDE
the hash rather than masked out of it, and `mapDiscoveredFloor` equality is
asserted directly alongside it as the human-readable witness.

THE HOSTILE REVEAL SET: the per-side reveal model gives the HOSTILE side its
own coop-owned byte-per-tile bitmap with its own `revealHostile` bucket, hashed
out of band (it is not a BattleHashSet member). The bucket is OMITTED, key
absent, in SP / any non-coop battle / wherever the storage is unallocated, so
an equal key set holding it on both machines at t=0 is itself evidence that
both machines allocated the hostile set at the same lifecycle point.

Uses session.py's assert_hash_clean() rather than duplicating the hash_now
round-trip.

BRIEFING LABELS: `strTarget` and `strCraftOrBase` are DISPLAY-ONLY
briefing/HUD labels ("LANDING SITE-0", "CRAFT> SKYRANGER-1") that BriefingState
sets (BriefingState.cpp, its constructor). Both keys are in
SharedEcon::saveBlobExcludedTopKey, so they never move saveBlob. battle_offer
carries the two labels and the client applies them on blob load, so both
machines agree on them in real play - see test_mission_labels.py. The
exclusion keeps carrying them hash-neutral by construction.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

# How many seqs the HOST has emitted at t=0 (after the whole entry chain,
# before any ACTION). The reveal envelopes come from the host's quiescent
# flush: one per QUIESCENT TICK that finds something newly discovered, and
# everything a single frame discovers coalesces into ONE delta - so this is a
# small constant, not "one per revealed tile". The battle offer goes out at
# PREPARE at turn 0 and turn 1 starts at the pre-battle equip barrier, so the
# count includes the equip phase's forced syncs too. Measured host log, two
# runs:
#   seq 1  side:"hostile" absolute `base` restate at phase Active. The hostile
#          set is coop-owned storage with NO save representation, so it cannot
#          ride the handshake blob; the host seeds its published mirror EMPTY
#          and the whole set ships here.
#   seq 2  side:"player" delta - the VOID-TILE baseline catch-up (631 / 642
#          tiles). SavedBattleGame::save skips void tiles
#          (SavedBattleGame.cpp:568-579), so discovered bits on empty air tiles
#          never ride the blob; CoopReveal::seedPublished deliberately leaves
#          them unpublished and this flush ships them.
#   seq 3  side:"player" delta - the host's BattlescapeState entry FOV at its
#          briefing OK (57 tiles), not coalesced with seq 2 because the host
#          reaches Active while still in its briefing.
#   seq 4  `sync` equip {open} - the equip-open announce.
#   seq 5  `sync` equip {ready} - the host's own ready press (this fixture's
#          client owns no soldier, so it never readies).
#   seq 6  `sync` equip {end} - the barrier's turn-1 sync.
#
# Asserted EXACTLY (not >=): a change that starts spraying reveal traffic per
# tick, or that silently drops the hostile baseline, must be a test failure
# rather than a silent regression. A different value here is not automatically
# a bug - it means the host's bring-up reveals landed on a different number of
# quiescent ticks - but it IS a change worth looking at deliberately. The
# invariants that matter (emitted == applied, nothing left unpublished on
# either side, per-part parity for BOTH sets, all buckets EQUAL) are asserted
# separately below and do not depend on this count.
REVEAL_SEQS_AT_T0 = 6


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
    host_dir = make_user_dir("hash_now_host")
    client_dir = make_user_dir("hash_now_client")
    host = GameClient("host", 48790, host_dir)
    client = GameClient("client", 48791, client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # --- lobby bring-up + battle start (test_handshake.py's own drive) ---
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

        # The coop blob snapshot and the battle_offer go out at PREPARE
        # (newbattle_ok), at turn 0, so both briefings are up at once;
        # session.briefings_to_battlescape passes both briefings, both
        # pre-battle equip screens (turn 1 starts on the host when both are
        # ready and reaches the client as one `sync`) and both Turn-1 screens.
        # "t=0" below is therefore "after the whole entry chain, before any
        # ACTION".
        session.briefings_to_battlescape(host, client)
        assert session.has_state(host, "BattlescapeState"), \
            f"host should reach BattlescapeState, stack={session.states(host)}"
        assert top_state(host) == "BattlescapeState", \
            f"host battle-start overlays never cleared, stack={session.states(host)}"
        print("PASS: both machines in BattlescapeState (handshake complete)")

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
        # t=0 (no ACTION has run): the only seq traffic is the host's
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
                f"client={client_rs[part]} (of {host_rs['mapSizeXYZ']} tiles) - the reveal sync "
                "did not converge the two machines' fog of war")
        # BOTH sides' reveal sets, per part, on both machines.
        for side in ("player", "hostile"):
            for part in ("floor", "westwall", "northwall"):
                assert host_rs[side][part] == client_rs[side][part], (
                    f"{side}-side discovered {part} differs at t=0: "
                    f"host={host_rs[side][part]} client={client_rs[side][part]}")
        assert host_rs["hostile"]["allocated"] and client_rs["hostile"]["allocated"], (
            "the HOSTILE reveal set is not allocated on both machines at t=0 - the "
            f"hostile baseline never landed: host={host_rs['hostile']} client={client_rs['hostile']}")
        assert host_rs["hostile"]["floor"] > 0, (
            "the hostile reveal set is EMPTY at t=0, so every hostile-side assertion in "
            f"this file would be vacuous: {host_rs['hostile']}")
        assert host_rs["unpublishedHostile"] is False, (
            f"host still owes hostile-side reveal bits at t=0: {host_rs}")
        print(f"PASS reveal_state: floor/westwall/northwall = {host_rs['floor']}/"
              f"{host_rs['westwall']}/{host_rs['northwall']} on BOTH machines, "
              "host has nothing unpublished")
        print(f"PASS reveal_state (both sides' sets): hostile set floor/west/north = "
              f"{host_rs['hostile']['floor']}/{host_rs['hostile']['westwall']}/"
              f"{host_rs['hostile']['northwall']} of {host_rs['hostile']['size']} tiles, "
              "EQUAL on both machines")
        # The void-tile hash hole: player-side fog on tiles that are
        # Tile::isVoid() on both machines is inside no hash bucket at all - it is
        # covered only by these aggregate counts, which is why this assert
        # exists and must not be removed as redundant.
        assert host_rs["discoveredVoid"] == client_rs["discoveredVoid"], (
            f"discoveredVoid differs at t=0: host={host_rs['discoveredVoid']} "
            f"client={client_rs['discoveredVoid']} - a fog divergence CONFINED TO VOID "
            "TILES, which no hash bucket can see")
        print(f"MEASURED: discoveredVoid = "
              f"{host_rs['discoveredVoid']} of {host_rs['mapSizeXYZ']} tiles on BOTH "
              "machines - the saveBlob void-tile fog hole IS populated, so this "
              "aggregate census is load-bearing coverage, not a redundancy")

        assert host_es["lastSeqEmitted"] == REVEAL_SEQS_AT_T0, (
            f"host lastSeqEmitted should be exactly {REVEAL_SEQS_AT_T0} at t=0 (the "
            f"hostile BASELINE restate, two player bring-up flushes and the equip "
            f"open/ready/end syncs) - see the constant's comment: {host_es}")
        assert client_es["lastSeqApplied"] == host_es["lastSeqEmitted"], (
            f"client lastSeqApplied should equal the host's {host_es['lastSeqEmitted']} at t=0 (every bring-up "
            f"reveal applied): {client_es}")
        assert host_es["queueDepth"] == 0 and client_es["queueDepth"] == 0, \
            f"queueDepth should be 0 on both at t=0: host={host_es} client={client_es}"

        print("PASS event_state: phase Active both, hostSim host=True client=False, "
              f"localSeat host={host_es['localSeat']} client={client_es['localSeat']}, "
              f"battleId={host_es['battleId']}, lastSeqEmitted={host_es['lastSeqEmitted']}, "
              f"lastSeqApplied={client_es['lastSeqApplied']}, queueDepth=0/0")
        print("HOST event_state:", json.dumps(host_es, sort_keys=True))
        print("CLIENT event_state:", json.dumps(client_es, sort_keys=True))

        # --- the human-readable witness for the unmasked fog hash ---
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
        # The sweep is ten buckets: the 7 BattleHashSet members + saveBlob +
        # revealHostile + synced. assert_hash_clean has already proved the KEY
        # SETS are identical on both machines, so naming revealHostile and synced
        # here is what makes the count non-vacuous.
        assert "revealHostile" in host_h, (
            f"hash_now full did not carry the revealHostile bucket ({sorted(host_h)}) - "
            "the hostile reveal storage was unallocated, so hash_now omitted it")
        # itemIdCtr must not silently disappear from the sweep - it stays a
        # compared bucket even though the ADOPT hook makes it agree by
        # construction (see test_item_id_ctr.py).
        assert "itemIdCtr" in host_h and "itemIdCtr" in client_h, (
            f"itemIdCtr bucket missing from hash_now full: "
            f"host={sorted(host_h)} client={sorted(client_h)}")
        assert len(host_h) == 10 and "synced" in host_h, (
            f"hash_now full returned {len(host_h)} buckets, expected 10 ({sorted(host_h)}) - "
            "the bucket set changed under this test")

        print("PASS: hash_now full=true EQUAL on both machines at t=0 "
              f"({len(host_h)}/10 buckets incl. revealHostile, saveBlob UNMASKED over binTiles)")
        print("HOST   h:", json.dumps(host_h, indent=2, sort_keys=True))
        print("CLIENT h:", json.dumps(client_h, indent=2, sort_keys=True))

        print("ALL JOINT DETERMINISM CHECKS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
