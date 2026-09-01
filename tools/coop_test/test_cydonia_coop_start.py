"""Regression: Cydonia must stream its Mars map to both campaign players.

ConfirmCydoniaState is a separate final-mission entry point; it does not pass
through ConfirmLandingState. Cover both campaign models so this path cannot
silently fall back to a host-only battle again.

R4-P2 (SPIKE-RUNBOOK.md SS2.7, RB-D18): re-pointed onto the SAME battle-start
handshake R4-P1 built (CoopHandshake::offerBattle) - ConfirmCydoniaState no
longer runs the legacy SEPARATE changeHost hand-off / CoopState(88) wait
dialog (deleted, no restored carrier); vanilla generates the battle exactly
like SP, then offerBattle() ships it, for BOTH "coop" (SEPARATE) and "shared"
campaigns alike (both are gamemode 0/1 "classic" under RB-D18 - PvP/PvE2 are
the only gamemodes the interim handshake refuses).

TRIM (RW-TRIAGE, this packet): the pre-rewrite version of this test waited for
BriefingState on BOTH machines. Under the R4-P1 handshake the CLIENT never
gets a BriefingState - CoopHandshake::onBlobChunkAppended pushes
BattlescapeState directly once the streamed blob is verified+loaded (the
LoadGameState.cpp "loaded save with a live battle" precedent), so only the
HOST still sees BriefingState (pushed unconditionally, exactly like vanilla
SP) and must click OK to reach BattlescapeState. Assertions below mirror
test_rw_handshake.py: phase-Active log lines on both machines + BattlescapeState
in the state stack on both machines. The saveBlob hash comparison itself is
SOFT-GATED pending R2-P9 (owner-approved 2026-09-01, see test_rw_handshake.py's
docstring for why) - this test does not assert saveBlob equality, only that
onReady() ran to completion and phase reached Active regardless of outcome.
The missionType/mapSizeXYZ/mapFingerprint equality checks are KEPT (not an
in-battle atom - a pure read-only query against the vanilla-restored
SavedBattleGame/Tile that proves both machines loaded the SAME streamed map,
squarely inside "entry + battle_ready parity").

Run:  python tools/coop_test/test_cydonia_coop_start.py
Exit 0 = pass; 2 = failure.
"""

import os
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


def _has(gc, name):
    return session.has_state(gc, name)


def _base(gc):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"]
                if not b.get("coopBase") and not b.get("coopIcon"))


def _craft_and_soldiers(gc):
    base = _base(gc)
    craft = next(c for c in base["crafts"] if "SKYRANGER" in c["type"])
    roster = gc.ok({"cmd": "get_soldiers"})["bases"]
    soldiers = next(b["soldiers"] for b in roster
                    if not b.get("coopBaseFlag"))
    return craft["id"], [s["id"] for s in soldiers]


def _seat(gc, craft_id, soldier_ids):
    for sid in soldier_ids:
        gc.ok({"cmd": "craft_assign", "craft_id": craft_id,
               "soldier_id": sid, "on": False})
    for sid in soldier_ids[:2]:
        gc.ok({"cmd": "craft_assign", "craft_id": craft_id,
               "soldier_id": sid, "on": True})


def _aboard(gc, craft_id):
    return sorted(s["id"] for b in gc.ok({"cmd": "get_soldiers"})["bases"]
                  for s in b["soldiers"] if s["craftId"] == craft_id)


def log_lines(user_dir):
    log = os.path.join(user_dir, "openxcom.log")
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def grep_lines(lines, needle):
    return [l.rstrip("\n") for l in lines if needle in l]


def run_mode(mode, test_ports, coop_port):
    print(f"\n===== Cydonia {mode.upper()} =====")
    host_dir = make_user_dir(f"cydonia_{mode}_host")
    client_dir = make_user_dir(f"cydonia_{mode}_client")
    host = GameClient("host", test_ports[0], host_dir)
    client = GameClient("client", test_ports[1], client_dir)
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        session.new_campaign(host, client, port=str(coop_port), campaign_mode=mode)

        host_craft, host_roster = _craft_and_soldiers(host)
        _seat(host, host_craft, host_roster)
        if mode == "coop":
            client_craft, client_roster = _craft_and_soldiers(client)
            _seat(client, client_craft, client_roster)
        else:
            # Give the shared squad one unit from each seat and wait until the
            # replicated ownership/assignment commands have settled.
            for gc in (host, client):
                gc.ok({"cmd": "set_soldier_owner", "soldier_id": host_roster[0], "owner": 0})
                gc.ok({"cmd": "set_soldier_owner", "soldier_id": host_roster[1], "owner": 1})
            host.wait_for("shared squad seated",
                          lambda: (_aboard(host, host_craft) == sorted(host_roster[:2])) or None,
                          timeout=30)

        host.ok({"cmd": "open_cydonia", "craft_id": host_craft})
        host.wait_for("Cydonia confirmation",
                      lambda: _has(host, "ConfirmCydoniaState") or None)
        host.ok({"cmd": "confirm_cydonia"})

        # R4-P2: host pushes BriefingState unconditionally right after vanilla
        # generation (exactly like SP - offerBattle() is a pure network side
        # effect and never touches the state stack, see CoopHandshake.h).
        host.wait_for("host briefing", lambda: _has(host, "BriefingState"), timeout=60)
        print("PASS: host reached BriefingState (vanilla push, unconditional)")

        # client: CoopHandshake::onBlobChunkAppended() pushes BattlescapeState
        # directly once the blob is received+verified+loaded - no client-side
        # BriefingState (LoadGameState.cpp precedent).
        client.wait_for("client battlescape",
                        lambda: _has(client, "BattlescapeState"), timeout=180)
        print("PASS: client reached BattlescapeState directly (offer/accept/"
              "stream/blobSha-verify/load all succeeded)")

        time.sleep(3)  # let both logs flush the handshake lines

        host_log = log_lines(host_dir)
        client_log = log_lines(client_dir)

        offer_lines = grep_lines(host_log, "[coop-handshake] battle_offer sent")
        accept_lines = grep_lines(host_log, "[coop-handshake] battle_accept received")
        client_active_lines = grep_lines(client_log, "[coop-handshake] CLIENT phase Active")
        host_active_lines = grep_lines(host_log, "[coop-handshake] HOST phase Active")
        equal_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob EQUAL")
        differ_lines = grep_lines(host_log, "[coop-handshake] battle_ready saveBlob differs")

        assert offer_lines, "host log missing 'battle_offer sent' line"
        assert accept_lines, "host log missing 'battle_accept received' line"
        assert client_active_lines, "client log missing 'CLIENT phase Active' line"
        # SOFT GATE (RW-TODO(R2-P9)): onReady() proceeds to phase Active whether
        # the raw saveBlob matched or (as is normal pre-R2-P9) differed on
        # machine-local FOV/discovered state - see test_rw_handshake.py's
        # docstring for the full trace. Only require ONE of the two outcome
        # lines to prove onReady() ran to completion.
        assert host_active_lines, \
            "host did not reach phase Active - onReady()'s soft gate should " \
            "proceed regardless of the saveBlob comparison"
        assert equal_lines or differ_lines, \
            "battle_ready arrived but neither 'saveBlob EQUAL' nor 'saveBlob " \
            "differs' was logged - onReady() did not run to completion"
        print("PASS: handshake log lines present on both machines "
              "(offer/accept/ready, host+client phase Active)")

        # Host is still in BriefingState (pushed unconditionally); OK proceeds
        # to BattlescapeState exactly like the SP path.
        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape",
                      lambda: _has(host, "BattlescapeState"), timeout=60)
        assert _has(host, "BattlescapeState"), \
            f"host should reach BattlescapeState after OK, stack={states(host)}"
        print("PASS: BOTH machines in BattlescapeState, host+client phase Active")

        battles = [gc.ok({"cmd": "battle_state"}) for gc in (host, client)]
        assert battles[0]["missionType"] == battles[1]["missionType"], battles
        assert battles[0]["mapSizeXYZ"] == battles[1]["mapSizeXYZ"], battles
        assert battles[0]["mapFingerprint"] == battles[1]["mapFingerprint"], battles
        print(f"PASS {mode}: both players loaded {battles[0]['missionType']} "
              f"with identical Mars map fingerprint {battles[0]['mapFingerprint']}")
    finally:
        host.shutdown(); client.shutdown()


def main():
    failures = []
    for mode, ports, coop_port in (
            ("coop", (48930, 48931), 48130),
            ("shared", (48932, 48933), 48132)):
        try:
            run_mode(mode, ports, coop_port)
        except Exception as exc:
            print(f"[FAIL] {mode}: {exc}")
            failures.append(f"{mode}: {exc}")

    if failures:
        print("\nCydonia co-op regression failures:", failures)
        sys.exit(2)
    print("\nCydonia co-op start passed in SEPARATE and SHARED campaigns.")


if __name__ == "__main__":
    main()
