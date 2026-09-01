"""R2-P11 (rewrite spike, SPIKE-RUNBOOK.md RB-D32) joint determinism check.

This doubles as the G4 determinism check the runbook's R2-P11 acceptance asks
for: boot a G3-path coop skirmish battle (the exact same lobby-flow drive
test_rw_handshake.py's main() uses for its own steps 1-7 - see that file's
docstring for why the drive is narrower than test_skirmish_flow.py's), then
assert `hash_now {"full":true}` is bucket-for-bucket EQUAL on both machines at
t=0 (before the first bt_ev - SS2.8's own boundary-sweep language), and that
`event_state` reports a sane, matching picture of the same live battle from
each machine's own side (phase Active both, hostSim true only on the host,
distinct localSeat per machine, lastSeqEmitted/lastSeqApplied/queueDepth all
at their fresh-battle defaults since nothing has been emitted yet).

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
        # t=0: nothing has been emitted/applied/queued yet on either machine
        assert host_es["lastSeqEmitted"] == 0, f"host lastSeqEmitted should be 0 at t=0: {host_es}"
        assert client_es["lastSeqApplied"] == 0, f"client lastSeqApplied should be 0 at t=0: {client_es}"
        assert host_es["queueDepth"] == 0 and client_es["queueDepth"] == 0, \
            f"queueDepth should be 0 on both at t=0: host={host_es} client={client_es}"

        print("PASS event_state: phase Active both, hostSim host=True client=False, "
              f"localSeat host={host_es['localSeat']} client={client_es['localSeat']}, "
              f"battleId={host_es['battleId']}, lastSeqEmitted={host_es['lastSeqEmitted']}, "
              f"lastSeqApplied={client_es['lastSeqApplied']}, queueDepth=0/0")
        print("HOST event_state:", json.dumps(host_es, sort_keys=True))
        print("CLIENT event_state:", json.dumps(client_es, sort_keys=True))

        # --- joint determinism check: hash_now {full:true} equal on both machines ---
        host_h, client_h = session.assert_hash_clean(host, client, full=True, what="t=0 joint determinism")

        print("PASS: hash_now full=true EQUAL on both machines at t=0 "
              f"({len(host_h)} buckets)")
        print("HOST   h:", json.dumps(host_h, indent=2, sort_keys=True))
        print("CLIENT h:", json.dumps(client_h, indent=2, sort_keys=True))

        print("ALL R2-P11 JOINT DETERMINISM CHECKS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
