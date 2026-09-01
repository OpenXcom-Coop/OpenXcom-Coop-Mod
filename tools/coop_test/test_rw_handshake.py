"""R4-P1 (rewrite spike, SPIKE-RUNBOOK.md SS2.7): battle-start handshake probe.

Drives a real 2-player skirmish co-op battle start through the harness lobby
flow (host: NEW BATTLE > COOP > Host > START HOST -> lobby -> BATTLE SETTINGS
-> OK), the same UI path test_skirmish_flow.py's test_skirmish_full_flow()
uses for its own steps 1-7 (that test stays SKIP-PENDING(R4-P1) - it also
exercises the EQUIP CRAFT craft-lock broadcast, a separate, still-quarantined
piece of choreography outside this packet's scope; this probe is deliberately
narrower: only the SS2.7 handshake itself).

Asserts:
  - the client reaches BattlescapeState directly (CoopHandshake::
    onBlobChunkAppended's LoadGameState.cpp-precedent push) - proves offer/
    accept/stream(blobBytes-gated)/blobSha-verify/load all worked.
  - the host's battle_offer/battle_accept/battle_ready log lines are present
    (the wire round-trip completed both directions).
  - BOTH machines reach phase Active and BattlescapeState (host drives its
    BriefingState OK; client is pushed there directly).

SAVEBLOB IS SOFT-GATED PENDING R2-P9 (owner-approved 2026-09-01). The R4-P1
saveBlob is a RAW FNV over the emitted battle YAML, so it necessarily includes
machine-local FOV/discovered state - unit "visible"/"turnsSinceSpotted*" and the
tile boolFields byte (= per-part terrain "discovered" flags, Tile.cpp:207, packed
inside binTiles). Those legitimately differ per machine (each computes its own
FOV), so the raw saveBlob differs on essentially every run. This was TRACED
2026-09-01 by decoding both binTiles: 0 terrain / 0 smoke / 0 fire / 0 unit-core
divergence, only 190 tile discovered-flag diffs + 7 unit "visible" diffs - i.e.
purely FOV, NOT a real desync (and NOT the tile-load bug an earlier revision of
this docstring wrongly blamed - the reorder fix in CoopHandshake::onBlobChunkAppended
materialises tiles before hashing). onReady() therefore LOGS the difference and
proceeds (see its RW-TODO(R2-P9) soft-gate comment). R2-P9 replaces the raw hash
with the canonical filtered SS2.8 bucket set (excluding those FOV fields per
R2-P10's cr1-field-audit.md) and RESTORES the hard mismatch->teardown gate; this
test then asserts EQUAL without otherwise changing.

Run:  python tools/coop_test/test_rw_handshake.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
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


def log_lines(user_dir):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def grep_lines(lines, needle):
    return [l.rstrip("\n") for l in lines if needle in l]


def main():
    port = "47985"
    host_dir = make_user_dir("rw_handshake_host")
    client_dir = make_user_dir("rw_handshake_client")
    host = GameClient("host", 48780, host_dir)
    client = GameClient("client", 48781, client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # --- lobby bring-up (test_skirmish_flow.py steps 1-4, minus the
        # EQUIP CRAFT detour - not this packet's concern) ---
        skirmish_host(host, port)
        skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"})
        client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)
        print("PASS lobby bring-up: host+client joined, popups dismissed")

        # --- step 5: host steps out to BATTLE SETTINGS (NewBattleState) ---
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        assert top_state(host) == "NewBattleState", \
            f"host should land on the NEW BATTLE setup screen, stack={states(host)}"
        print("PASS step 5: host at BATTLE SETTINGS")

        # --- R4-P1: OK drives NewBattleState::btnOkClick, which now runs
        # vanilla bgen.run() then CoopHandshake::offerBattle() as a side
        # effect (BriefingState is still pushed immediately, unconditionally,
        # exactly like vanilla - see CoopHandshake.h's top doc comment) ---
        host.ok({"cmd": "newbattle_ok"})

        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
        print("PASS: host reached BriefingState (vanilla push, unconditional)")

        # client: CoopHandshake::onBlobChunkAppended() pushes BattlescapeState
        # directly once the blob is received+verified+loaded (no client-side
        # BriefingState - LoadGameState.cpp's "loaded save with a live
        # battle" precedent). Unconditional - proves offer/accept/stream/
        # blobSha-verify/load all worked regardless of the saveBlob outcome.
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=60)
        print("PASS: client reached BattlescapeState directly (offer/accept/stream/"
              "blobSha-verify/load all succeeded)")

        # settle so both logs have flushed the handshake lines before reading them
        time.sleep(3)

        host_log = log_lines(host_dir)
        client_log = log_lines(client_dir)

        offer_lines = grep_lines(host_log, "[coop-handshake] battle_offer sent")
        accept_lines = grep_lines(host_log, "[coop-handshake] battle_accept received")
        client_active_lines = grep_lines(client_log, "[coop-handshake] CLIENT phase Active")
        equal_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob EQUAL")
        differ_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob differs")
        host_active_lines = grep_lines(host_log, "[coop-handshake] HOST phase Active")

        assert offer_lines, "host log missing 'battle_offer sent' line"
        assert accept_lines, "host log missing 'battle_accept received' line"
        assert client_active_lines, "client log missing 'CLIENT phase Active' line"

        print("HOST LOG:", offer_lines[-1])
        print("HOST LOG:", accept_lines[-1])
        print("CLIENT LOG:", client_active_lines[-1])

        # SOFT GATE (RW-TODO(R2-P9)): the host proceeds to phase Active whether the
        # raw saveBlob matched or (as is normal pre-R2-P9) differed on machine-local
        # FOV/discovered state - see this module's docstring.
        assert host_active_lines, \
            "host did not reach phase Active - onReady()'s soft gate should proceed " \
            "regardless of the saveBlob comparison"
        if equal_lines:
            print("HOST LOG:", equal_lines[-1])
            print("NOTE: saveBlob EQUAL this run (FOV happened to coincide).")
        else:
            assert differ_lines, \
                "battle_ready arrived but neither 'saveBlob EQUAL' nor 'saveBlob differs' " \
                "was logged - onReady() did not run to completion"
            print("HOST LOG:", differ_lines[-1])
            print("NOTE: saveBlob differs = EXPECTED pre-R2-P9 (benign machine-local FOV/"
                  "discovered state; 0 real divergence, traced 2026-09-01). Soft gate proceeds.")
        print("HOST LOG:", host_active_lines[-1])

        # Host is still in BriefingState (pushed unconditionally after bgen.run());
        # its OK proceeds to BattlescapeState exactly like the SP path.
        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)
        # BattlescapeState in-stack (a NextTurnState/InventoryState deploy screen
        # normally sits on top at battle start) - same in-stack check the client uses.
        assert session.has_state(host, "BattlescapeState"), \
            f"host should reach BattlescapeState after OK, stack={states(host)}"
        print("PASS: BOTH machines in BattlescapeState, host+client phase Active "
              "(saveBlob soft-gated pending R2-P9 canonical hash)")

        print("ALL R4-P1 HANDSHAKE TESTS PASSED")
    finally:
        host.shutdown()
        client.shutdown()


if __name__ == "__main__":
    main()
