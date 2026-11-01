"""test_ai_origin_stream.py: the alien WALK the host's AI runs
(`handleAI`'s `origin:"ai"` mint at `BattlescapeGame.cpp:307`, streamed by
`CoopArbiter::beginAiWalk`) reaches the client as a real, hashed walk chain:
same actionId, seq-ordered `walk_step` evs each carrying `h`, zero
shot/hit/explosion evs (the test covers the AI walk only: the fixture strips
every alien and sets its psiSkill to 0), all nine hash buckets EQUAL after the
whole alien side, and the client never latches `desyncSeen`.

Fixture, seed 1: mission STR_SMALL_SCOUT, `newbattle_race STR_FLOATER` in
`pre_seat`, `set_seed 1` in `pre_ok`, `battle_strip_unit` + `set_stat
{psiSkill:0}` on every live hostile at t=0 on BOTH machines (no TU pin), then
the client's END TURN and the host's once it shows END TURN 1/2.

Measured on this fixture without the AI walk stream: the host walked the alien
7 tiles spending 47 TU, the client's copy never moved, ticked its own TU to 44,
and latched `desyncSeen` True while the host stayed False. With it: host
`lastWalk.origin == 'ai'`, client same actionId 3, 8 `walk_step` evs all with
`h`, zero shot/hit/explosion, final positions AGREE, `desyncSeen` False on
both. This file checks that in ONE run.

The origin is asserted on the HOST ONLY - `event_state.lastWalk.origin == "ai"`
(`publishLastWalk`, `connectionTCP.cpp:3554`, fed by the host-side
`beginWalkChain`, `:3511`). The client's own `lastWalk.origin` is "" by
construction (it never runs AI) and is printed, never asserted either way.

Checks (each prints its name): host_walk_origin_ai, client_same_walk,
walk_steps_hashed, no_combat_evs, buckets_equal, no_desync, alien_moved (a
non-vacuity gate, asserted first).

Run:  python tools/coop_test/test_ai_origin_stream.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import (battle_state, event_state, event_log, assert_hash_clean,
                      FACTION_HOSTILE, FACTION_PLAYER)
import repro_atom_side_transition as sid

MISSION = "STR_SMALL_SCOUT"
RACE = "STR_FLOATER"
SEED = 1
TALLY_TEXT_1_OF_2 = "END TURN 1/2"
CYCLE_TIMEOUT = 60


def run():
    port = "48172"
    host_dir = make_user_dir("ai_origin_stream_host")
    client_dir = make_user_dir("ai_origin_stream_client")
    host = GameClient("host", 49564, host_dir)
    client = GameClient("client", 49565, client_dir)
    seated = {}
    try:
        sid.bring_up_lobby(host, client, port)
        session.drive_to_battlescape(
            host, client, seated, mission=MISSION, seat_count=2,
            pre_seat=lambda h: h.ok({"cmd": "newbattle_race", "race": RACE}),
            pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED}))

        hostiles = [u for u in battle_state(host)["units"]
                    if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        hostile_ids = [u["id"] for u in hostiles]
        assert hostile_ids, f"no live hostile on the pinned seed {SEED}"

        for uid in hostile_ids:
            rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})  # client first
            rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
            assert rh.get("ok") and rc.get("ok"), (
                f"battle_strip_unit failed for unit {uid}: host={rh} client={rc}")
            assert rh.get("deleted") == rc.get("deleted"), (
                f"the two machines' deleted item id lists differ for unit "
                f"{uid}: host={rh.get('deleted')} client={rc.get('deleted')}")
            session.wait_seq_barrier(host, client)
            client.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})
            host.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "psiSkill": 0})
            session.wait_seq_barrier(host, client)

        # ---- non-vacuity capture, BEFORE the verdict: position/TU before ----
        before_pos = {u["id"]: session.unit_pos(u) for u in hostiles}
        before_tu = {u["id"]: u["tu"] for u in hostiles}
        print(f"[before] hostile(s) {hostile_ids}: pos={before_pos} tu={before_tu}")

        turn0 = battle_state(host)["turn"]

        client.ok({"cmd": "battle_action", "action": "end_turn_button"})

        def _host_shows_1_of_2():
            return True if battle_state(host).get("coopEndTurnText") == TALLY_TEXT_1_OF_2 else None
        host.wait_for("host paints END TURN 1/2 after the client's arm",
                      _host_shows_1_of_2, timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})

        deadline = time.time() + CYCLE_TIMEOUT
        returned = False
        while time.time() < deadline:
            sid.dismiss_next_turn_if_present(host)
            hs = battle_state(host)
            if hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1:
                returned = True
                break
            time.sleep(0.05)
        assert returned, (
            f"host did not return to the player side within {CYCLE_TIMEOUT}s: "
            f"{battle_state(host)}")

        session.wait_host_idle(host, client, timeout=30)
        session.settle_reveal(host, client)

        # ---- alien_moved / non-vacuity gate: at least one live hostile's
        # position CHANGED across the cycle (asserted BEFORE the verdict) ----
        after_units = {u["id"]: u for u in battle_state(host)["units"]}
        after_pos = {uid: session.unit_pos(after_units[uid]) for uid in hostile_ids
                     if uid in after_units}
        after_tu = {uid: after_units[uid]["tu"] for uid in hostile_ids if uid in after_units}
        moved = [uid for uid in before_pos
                 if uid in after_pos and before_pos[uid] != after_pos[uid]]
        print(f"[after]  hostile(s) {hostile_ids}: pos={after_pos} tu={after_tu}")
        assert moved, (
            f"non-vacuity gate FAILED: no live hostile's position changed across "
            f"the alien side - before={before_pos} after={after_pos}")

        # ---- host_walk_origin_ai: HOST lastWalk.origin == 'ai' ----
        hw = event_state(host).get("lastWalk")
        assert hw and hw.get("origin") == "ai", (
            f"HOST event_state.lastWalk.origin is not 'ai': {hw}")
        host_action_id = hw.get("actionId")

        # ---- client_same_walk: CLIENT lastWalk, SAME actionId, seq-ordered steps ----
        cw = event_state(client).get("lastWalk")
        assert cw and cw.get("actionId") == host_action_id, (
            f"CLIENT event_state.lastWalk.actionId does not match the host's "
            f"({host_action_id}): {cw}")
        c_steps = cw.get("steps") or []
        assert c_steps, f"CLIENT lastWalk carries no steps: {cw}"
        seqs = [s.get("seq") for s in c_steps]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
            f"CLIENT lastWalk.steps are not strictly increasing in seq: {seqs}")
        step_indices = [s.get("stepIndex") for s in c_steps]
        assert step_indices == sorted(step_indices), (
            f"CLIENT lastWalk.steps' stepIndex is not non-decreasing: {step_indices}")
        # the client's own origin is "" by construction - printed,
        # NEVER asserted either way.
        print(f"[host_walk_origin_ai + client_same_walk] HOST lastWalk.origin='ai' actionId={host_action_id}; "
              f"CLIENT lastWalk actionId={cw.get('actionId')} "
              f"origin={cw.get('origin')!r} (printed only, not asserted) "
              f"steps seq={seqs} stepIndex={step_indices}")

        # ---- walk_steps_hashed: every walk_step ev in the CLIENT's event_log
        # (for this actionId) carries h ----
        log = event_log(client, tail=256)
        walk_step_evs = [e for e in log if e.get("actionId") == host_action_id
                         and e.get("kind") == "walk_step"]
        assert walk_step_evs, (
            f"no walk_step ev found in the client's event_log for actionId "
            f"{host_action_id}: {[e.get('kind') for e in log]}")
        without_h = [e for e in walk_step_evs if not e.get("h")]
        assert not without_h, f"{len(without_h)} walk_step ev(s) carry no h: {without_h}"
        print(f"[walk_steps_hashed] {len(walk_step_evs)} walk_step ev(s) for actionId "
              f"{host_action_id}, ALL carry h")

        # ---- no_combat_evs: ZERO shot/hit/explosion evs in the client's event_log ----
        kinds_hist = {}
        for e in log:
            kinds_hist[e.get("kind")] = kinds_hist.get(e.get("kind"), 0) + 1
        forbidden = {"shot", "hit", "explosion"}
        forbidden_count = sum(v for k, v in kinds_hist.items() if k in forbidden)
        assert forbidden_count == 0, (
            f"{forbidden_count} shot/hit/explosion ev(s) found in the client's "
            f"event_log - the stripped aliens (psiSkill 0) may only walk: "
            f"{kinds_hist}")
        print(f"[no_combat_evs] zero shot/hit/explosion evs; full kind histogram: "
              f"{kinds_hist}")

        # ---- buckets_equal: all nine buckets EQUAL after the alien side ----
        hh, ch = assert_hash_clean(host, client, full=True, what="after the alien side")
        print(f"[buckets_equal] {len(hh)}/{len(hh)} buckets EQUAL")

        # ---- no_desync: the client is NOT frozen ----
        hd = event_state(host).get("desyncSeen")
        cd = event_state(client).get("desyncSeen")
        assert cd is False and hd is False, (
            f"desyncSeen is not False on both machines: host={hd} client={cd}")
        print(f"[no_desync] desyncSeen False on both machines (host={hd} client={cd})")

        print(f"[alien_moved / non-vacuity] hostile(s) that moved: {moved}")

        print("PASS: test_ai_origin_stream")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    run()
    print("ALL test_ai_origin_stream TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except session.KnownFlake as e:
        session.print_known_flake_banner("test_ai_origin_stream", e.tracking, str(e))
        print(f"\ntest_ai_origin_stream: FAIL (KNOWN FLAKE, evidence recorded)\n{e}")
        sys.exit(2)
    except AssertionError as e:
        print(f"\ntest_ai_origin_stream: FAIL\nAssertionError: {e}")
        sys.exit(2)
    except TimeoutError as e:
        print(f"\ntest_ai_origin_stream: FAIL\nTimeoutError: {e}")
        sys.exit(2)
