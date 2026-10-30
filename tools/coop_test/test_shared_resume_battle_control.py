"""SHARED mid-battle save / resume: the SHARED twin of test_coop_resume_battle_control.py.

Same invariant, same craft-roof mid-walk fixture, on a SHARED
campaign: seat 0 (host-owned, coop==0) + seat 1 (client-owned, coop==1) on
the SAME shared craft - no two-world merge, so the seat-1 soldier is the
CLIENT's own roster entry directly rather than a merged battle copy. The
SHARED arm of `request_load_progress` (connectionTCP.cpp) is what this
scenario proves reaches the SAME disk-resume fork as SEPARATE.

Reuses test_coop_resume_battle_control's split_report/assert_split/
settle_and_assert and its stage_alien_and_walk/_sav_status_pos helpers
(the craft-roof recipe is identical once a live battle exists - only the
BRING-UP differs between SEPARATE and SHARED).

Run:  python tools/coop_test/test_shared_resume_battle_control.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import shared_fixture
import session
# reuse the split probe/assertion + the craft-roof staging helpers
# from the SEPARATE test (SAME invariant, same fixture recipe).
import test_coop_resume_battle_control as rc

PORTS = (48780, 48781, 48082)   # host test / client test / coop session
RESUME_PORT = "48083"


def _roster(gc):
    out = []
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        out.extend(b["soldiers"])
    return out


def bring_up_craft_roof_shared(js):
    """SHARED twin of test_coop_resume_battle_control.bring_up_craft_roof_separate
    (the SHARED bring-up hits the same clustered-spawn problem on a rolled
    map - the same Skyranger + landed-UFO recipe fixes it here).

    Returns (host_squad_id, client_seat_id, name_by_squad): the shared craft's
    seat-0 (host) and seat-1 (client) soldier ids, and {name: seat} for
    assert_split's `expected` (no merge - the seat-1 soldier is the CLIENT's
    own roster entry, identified the same way by name)."""
    host, client = js.host, js.client
    b0 = session._campaign_base0(host)
    craft_id = session._campaign_skyranger(host)["id"]

    name_by_id = {s["id"]: s["name"] for s in _roster(host)}
    rh = sorted(name_by_id)
    squad = [rh[0], rh[1]]
    owners = {0: 0, 1: 1}   # seat 0 -> host, seat 1 -> client
    for gc in (host, client):
        for slot, sid in enumerate(squad):
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": sid, "owner": owners[slot]})
    for sid in rh:
        host.ok({"cmd": "craft_assign", "craft_id": craft_id, "craft_type": "STR_SKYRANGER",
                 "soldier_id": sid, "on": False})
    for sid in squad:
        host.ok({"cmd": "craft_assign", "craft_id": craft_id, "craft_type": "STR_SKYRANGER",
                 "soldier_id": sid, "on": True})

    def _aboard(gc):
        return sorted(s["id"] for s in _roster(gc)
                      if s["craftId"] == craft_id and s["craft"] == "STR_SKYRANGER")

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} squad aboard",
                    lambda gc=gc: (_aboard(gc) == sorted(squad)) or None, timeout=40, interval=0.5)
    print(f"shared squad {squad} aboard Skyranger {craft_id} "
          f"(seat0->host coop0, seat1->client coop1)")

    ufo = host.cmd({"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH",
                    "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID", "trajectory": "P0",
                    "state": "landed", "lon": b0["lon"] + 0.30, "lat": b0["lat"] + 0.10, "hours": 240})
    assert ufo.get("ok") and ufo.get("ufo_id") is not None, f"spawn_ufo failed: {ufo}"
    ufo_id = ufo["ufo_id"]
    host.ok({"cmd": "craft_force", "craft_id": craft_id, "craft_type": "STR_SKYRANGER", "status": "STR_OUT",
             "lon": b0["lon"] + 0.29, "lat": b0["lat"] + 0.10, "dest": f"ufo:{ufo_id}",
             "fuel": 999999, "lowFuel": False})

    def _landing_prompt():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    host.wait_for("ConfirmLandingState on host", _landing_prompt, timeout=90, interval=0.5)
    host.ok({"cmd": "confirm_landing"})
    host.wait_for("host entered", lambda: session.battle_state(host).get("inBattle") or None,
                  timeout=180, interval=1.0)
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState") or None,
                  timeout=60, interval=0.5)
    assert session.drive_both_to_tactical(host, client), (
        f"drive_both_to_tactical timed out host={session.states(host)[-3:]} "
        f"client={session.states(client)[-3:]}")
    print("both machines reached the battlescape (live SHARED craft-roof battle)")

    name_by_squad = {name_by_id[squad[0]]: 0, name_by_id[squad[1]]: 1}
    return squad[0], squad[1], name_by_squad


def main():
    js = shared_fixture.bring_up("srbc", PORTS, host_options={"battleXcomSpeed": 200, "battlescapeScale": 5})
    host, client = js.host, js.client
    host_dir = js.host_dir
    fail = None
    host2 = client2 = None
    try:
        host_seat_id, client_seat_id, expected_names = bring_up_craft_roof_shared(js)

        expected_seats = {host_seat_id: 0, client_seat_id: 1}
        session.assert_control_split(host, client, expected_seats, what="shared_resume pre-save live split")

        walker_id = next(u["id"] for u in rc.battle(host)["units"]
                         if u.get("soldierId") == host_seat_id and not u.get("isOut"))
        walker_before = next(u for u in rc.battle(host)["units"] if u["id"] == walker_id)
        pos_before = (walker_before["x"], walker_before["y"], walker_before["z"])

        elevator, dest, lw, pending = rc.stage_alien_and_walk(host, client, walker_id)

        before_files = set(session.save_files(host_dir))
        deferrals_before = rc.battle(host).get("coopSaveDeferrals")
        r = host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        # DEFERRAL (mid_walk_save), read from the game's own record. Observing
        # the latch armed with no file yet is not reliable: that window closes
        # when the walk drains - an off-screen walk that halts on TU drains
        # within ~25-200 ms, and each battle_state reply reaches the test
        # after the game handled it, so the first look can land after the
        # deferred write. The game records every deferral
        # (`coopSaveDeferrals`) and the tick of the deferred write
        # (`coopSaveDeferredWrittenAt`); the host's `lastWalk.endTick` is the
        # tick its walk ended. Wait for the new file (30 s:
        # SaveGameState::think()'s 10-frame warmup runs first and two tests
        # at once slow frames), assert the save was deferred exactly
        # once across the request, and - after the file exists (below) - that
        # the deferred write came no earlier than the walk's end. Same shape
        # as the SEPARATE twin test_coop_resume_battle_control.py.
        immediate_files = set()
        poll_iters = 0
        t_start = time.time()
        deadline = t_start + 30.0
        while time.time() < deadline:
            poll_iters += 1
            immediate_files = set(session.save_files(host_dir)) - before_files
            if immediate_files:
                break
            time.sleep(0.1)
        elapsed = time.time() - t_start
        deferrals_after = rc.battle(host).get("coopSaveDeferrals")
        assert isinstance(deferrals_before, int) and deferrals_after == deferrals_before + 1, (
            f"mid_walk_save VACUITY: the mid-walk save request (pending={pending}) was not deferred "
            f"exactly once - coopSaveDeferrals {deferrals_before} -> {deferrals_after} "
            f"after {poll_iters} poll(s)/{elapsed:.1f}s: {r}")
        print(f"PASS mid_walk_save deferral: coopSaveDeferrals {deferrals_before} -> {deferrals_after} "
              f"(pending={pending}, new file after {poll_iters} poll(s)/{elapsed:.1f}s)")

        for _ in range(150):
            if not (session.event_state(host).get("lastWalk") or {}).get("active"):
                break
            time.sleep(0.2)
        time.sleep(0.5)
        walker_after = next(u for u in rc.battle(host)["units"] if u["id"] == walker_id)
        pos_after = (walker_after["x"], walker_after["y"], walker_after["z"])
        assert pos_after != pos_before, "VACUITY: the walk never changed the walker's tile"

        sp_after = None
        new_files = set()
        for _ in range(50):
            sp_after = rc.battle(host).get("coopSavePending")
            new_files = set(session.save_files(host_dir)) - before_files
            if sp_after is False and new_files:
                break
            time.sleep(0.2)
        assert sp_after is False, f"mid_walk_save: coopSavePending never cleared: {sp_after}"
        assert len(new_files) == 1, f"mid_walk_save: expected exactly one new save file, got {sorted(new_files)}"
        savpath = os.path.join(host_dir, next(iter(new_files)))

        # the deferred write came no earlier than the walk's end -
        # both are the host's own SDL_GetTicks(), read once the file exists.
        rec = rc.battle(host)
        walk_end = (session.event_state(host).get("lastWalk") or {}).get("endTick")
        written_at = rec.get("coopSaveDeferredWrittenAt")
        assert (isinstance(walk_end, int) and walk_end > 0 and isinstance(written_at, int)
                and written_at >= walk_end), (
            f"mid_walk_save: the deferred save was not written after the walk ended (deferral broken): "
            f"coopSaveDeferredWrittenAt={written_at} lastWalk.endTick={walk_end} "
            f"coopSaveDeferredAt={rec.get('coopSaveDeferredAt')}")
        print(f"PASS mid_walk_save write-after-walk-end: coopSaveDeferredWrittenAt={written_at} >= "
              f"lastWalk.endTick={walk_end} (deferred at {rec.get('coopSaveDeferredAt')})")

        sav_status, sav_pos, sav_block = rc._sav_status_pos(savpath, walker_id)
        assert sav_status == rc.STATUS_STANDING, (
            f"mid_walk_save: written save walker status={sav_status} (want STANDING), file does not hold "
            f"the post-walk state:\n{sav_block}")
        assert sav_pos == pos_after, (
            f"mid_walk_save: written save walker pos={sav_pos} != live post-drain pos {pos_after}:\n{sav_block}")
        print(f"PASS mid_walk_save: the .sav holds the walker's exact post-drain state "
              f"(status={sav_status}, pos={sav_pos})")

        def _snapshot(gc):
            bs = rc.battle(gc)
            es = session.event_state(gc)
            wu = next(u for u in bs["units"] if u["id"] == walker_id)
            return {
                "walker_pos": (wu["x"], wu["y"], wu["z"]),
                "walker_tu": wu["tu"],
                "walker_status": wu["status"],
                "turn": bs.get("turn"),
                "side": bs.get("side"),
                "mapFingerprint": bs.get("mapFingerprint"),
                "unit_ids": sorted(u["id"] for u in bs["units"]),
                "turnMode": es.get("turnMode"),
                "deployment": bs.get("deployment"),
            }

        post_host = _snapshot(host)
        post_client = _snapshot(client)
        assert post_host == post_client, (
            f"pre-quit snapshots differ between machines:\n  host={post_host}\n  client={post_client}")
        post = post_host

        session.assert_client_zero_disk(client.user_dir)
        js.shutdown()

        host2 = GameClient("host", 48782, host_dir)
        client2 = GameClient("client", 48783, make_user_dir("srbc_client2"))
        host2.spawn(); client2.spawn()
        host2.connect(); client2.connect()

        session.resume_campaign_battle(host2, client2, os.path.basename(savpath),
                                       port=RESUME_PORT, timeout=180)

        for gc, tag in ((host2, "host"), (client2, "client")):
            bs = rc.battle(gc)
            assert bs.get("inBattle"), f"{tag}: not inBattle after resume: {bs}"
            assert bs.get("phase") == "Active", f"{tag}: phase={bs.get('phase')!r} after resume"
        auth_h = rc.battle(host2).get("authority", {})
        auth_c = rc.battle(client2).get("authority", {})
        assert auth_h.get("battleId") and auth_h.get("battleId") == auth_c.get("battleId"), (
            f"battleId not equal/non-zero after resume: host={auth_h.get('battleId')} "
            f"client={auth_c.get('battleId')}")

        logp = os.path.join(host2.user_dir, "openxcom.log")
        lines = []
        if os.path.exists(logp):
            with open(logp, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        mism = [ln for ln in lines if "battle_ready saveBlob MISMATCH" in ln]
        eq = [ln for ln in lines if "battle_ready saveBlob EQUAL" in ln]
        assert not mism, f"host log carries a battle_ready saveBlob MISMATCH: {mism[-1]}"
        assert eq, "host log never logged 'battle_ready saveBlob EQUAL' after resume"
        for gc, tag in ((host2, "host"), (client2, "client")):
            assert not session.event_state(gc).get("desyncSeen"), f"{tag}: desyncSeen after resume"
        print(f"PASS resume hash: {eq[-1].strip()}, desyncSeen false both")

        rc.settle_and_assert(host2, client2, "after resume", expected_names)

        for gc, tag in ((host2, "host"), (client2, "client")):
            snap = _snapshot(gc)
            assert snap == post, (
                f"{tag}: post-resume snapshot != pre-quit `post`:\n  post={post}\n  {tag}={snap}")
        # "never replay the walk": see test_coop_resume_battle_control.py's
        # own note - lastSeqApplied is not 0 after a resume (the battle-entry
        # side-begin reveal restate legitimately advances it);
        # the snapshot equality above already proves no WALK replay, and this
        # confirms no walk EVENT was applied on the client either.
        client_events = session.event_log(client2, tail=100)
        walk_replays = [e for e in client_events if e.get("kind") == "walk"]
        assert not walk_replays, (
            f"client applied walk event(s) after resume (a replay): {walk_replays}")
        print("PASS resumed state == post-drain snapshot on both machines; no walk replay")

        # PARALLEL mode reset-default tally (see test_coop_resume_battle_
        # control.py's own note; parallel emits nothing at entry, as
        # test_end_turn_tally.py also checks).
        RESET_TALLY = {"turn": 0, "side": "", "count": 0, "needed": 0, "ready": [], "activeSeat": -1}
        for gc, tag in ((host2, "host"), (client2, "client")):
            tally = session.event_state(gc).get("coopEndTurnTally", {})
            assert tally == RESET_TALLY, (
                f"{tag}: PARALLEL-mode tally after resume is not the reset() default "
                f"{RESET_TALLY}: {tally}")

        session.press_back_when_shown(host2, "host RESUME", codes=(60, 62))
        for gc, tag in ((host2, "host"), (client2, "client")):
            gc.wait_for(f"{tag} on BattlescapeState after RESUME",
                        lambda gc=gc: (rc.top(gc) == "BattlescapeState") or None, timeout=60, interval=0.5)
            assert not rc.has(gc, "HostMenu") and not rc.has(gc, "LobbyMenu"), (
                f"{tag}: HostMenu/LobbyMenu still on stack after RESUME: {rc.states(gc)}")
        print("PASS resume_click: both machines on BattlescapeState after RESUME, no HostMenu/LobbyMenu")

        # Only the ADMIT + DENY legs of the seat-command check run here (the
        # host's click-select refusal leg is covered on a fresh battle entry) -
        # see test_coop_resume_battle_control.py's own note.
        session.assert_seat_commands(host2, client2, client_seat_id, host_seat_id,
                             host_check=False, what="shared_resume after resume")

        session.assert_client_zero_disk(client2.user_dir)
        print("PASS zero-disk: resumed client user dir clean")
        print("ALL SHARED MID-BATTLE RESUME TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        if host2:
            host2.shutdown()
        if client2:
            client2.shutdown()
        js.shutdown()

    if fail:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
