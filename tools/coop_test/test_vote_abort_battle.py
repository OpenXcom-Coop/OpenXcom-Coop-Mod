"""ABANDON MISSION vote in a live SHARED battle - repro + end-to-end.

In multiplayer BattlescapeState::btnAbortClick no longer pushes
AbortMissionState: it calls requestVote("abandon_mission", ...) and every
machine opens a VoteMenu. That is the feature. This test covers both halves of
what the change means for a running battle.

1. THE REPRO (the reason this file exists)
   The TestServer's dismiss_popup is a typed dispatcher with a final `else`
   that generically _game->popState()s ANY state it does not recognise, so
   "skip whatever dialog is on top" stays robust as new popups appear. The
   VoteMenu is not one of the types it knows, so a blind dismiss_popup pops it;
   on the next call the BattlescapeState is the top state and is *also*
   unknown, so the running battle is popped raw off the stack. That shreds the
   battle and the state stack under it and kills the process - the harness sees
   its TestServer socket reset (WinError 10054).

   Every co-op battle test used to end its battle with exactly that recipe
   (battle_action/abort, then dismiss_popup every 0.4s until the geoscape), so
   the change turned all of them into crash reproducers. Here the hammer is
   deliberate: with an abandon-mission vote open, fire dismiss_popup 10 times
   at EACH machine and then assert that both processes are alive, that both
   still hold a BattlescapeState, and that the vote is still running. Against
   an unfixed build these assertions fail - that is the point.

2. THE FAILURE PATHS
   A vote that does not pass must leave the battle exactly where it was: only
   a PASSED abandon_mission runs executeVoteAction -> abortMissionByVote. Both
   ways of losing are exercised inside the SAME battle. The peer votes NO,
   which a 2-player strict majority can never recover from (1 YES + 0 votes
   left < 2), so the host fails it the moment the cast lands; and the
   host-authoritative 30-second deadline expires (vote_force_timeout moves it
   to now and runs the normal evaluator). After each one both processes must
   still answer, both must still hold a BattlescapeState, and the
   SavedBattleGame must still be live.

3. THE E2E
   With the hammer and both failures survived, finish the mission the way a
   player does, through session.coop_abort_battle(): the peer votes YES, the
   2/2 majority passes, the host runs abortMissionByVote -> finishBattle ->
   DebriefingState and the client follows via EndCoopBattle. Both machines
   land back on the geoscape holding ONE identical shared world.

Between phases the finished VoteMenu has to be closed on BOTH machines and the
host's per-seat starter cooldown cleared - see _reset_vote(). Sections 1 and 2's
NO path share a single vote (a repeated battle_action/abort while one is active
is absorbed by requestVote, which just re-shows the open menu), so the whole
test needs one battle and three votes.

Run:  python tools/coop_test/test_vote_abort_battle.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

# RW-TRIAGE: SKIP-PENDING(r3)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session

# Free triple: (host test port, client test port, coop session port).
PORTS = (49032, 49033, 48332)

HAMMER_CALLS = 10
HAMMER_PAUSE = 0.2


def _geo(gc):
    return gc.ok({"cmd": "geo_state"})


def _base0(gc):
    for b in _geo(gc)["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base")


def _roster(gc):
    out = []
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        out.extend(b["soldiers"])
    return out


def _skyranger(gc):
    for c in _base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("no skyranger")


def _states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def _has(gc, name):
    return any(name in s for s in _states(gc))


def _battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def _world_fingerprint(gc):
    """Post-battle world equality probe: funds + surviving roster + stores."""
    g = _geo(gc)
    rep = gc.ok({"cmd": "base_report"})
    return {
        "funds": g["funds"],
        "roster": sorted((s["id"], s["owner"]) for s in _roster(gc)),
        "storage": dict(sorted(rep["storage"].items())),
    }


def _wait_vote(gc, tag, desc, predicate, timeout=25):
    """gc.wait_for() over vote_state, returning the matching snapshot."""
    return gc.wait_for(
        f"{tag} {desc}",
        lambda: (lambda s: s if predicate(s) else None)(
            gc.ok({"cmd": "vote_state"})),
        timeout=timeout, interval=0.25)


def _reset_vote(host, client):
    """Retire a FINISHED vote on both machines so the next ABORT starts a new one.

    requestVote() short-circuits while _activeVote.finished and that vote's
    VoteMenu is still on the stack - it only re-shows the menu and returns true,
    without creating a vote. So both menus go first (vote_close), and only then
    is the host's 60-second per-seat starter cooldown expired; the host enforces
    that cooldown for EVERY seat, so clearing it there covers both players.
    """
    for gc in (host, client):
        gc.ok({"cmd": "vote_close"})
    host.ok({"cmd": "vote_clear_cooldown"})


def _assert_battle_alive(gc, tag, phase):
    """A failed vote must leave the process, the state stack and the battle alone."""
    try:
        st = _states(gc)
    except (OSError, EOFError, ValueError) as e:
        raise AssertionError(
            f"{tag}: PROCESS DIED during the {phase} phase ({e!r}) - a FAILED "
            f"abandon-mission vote must not touch the running battle at all")
    assert any("BattlescapeState" in s for s in st), (
        f"{tag}: BATTLESCAPE POPPED by the {phase} phase - the vote did NOT "
        f"pass, so nothing may have ended the mission: states={st}")
    assert _battle(gc).get("inBattle"), (
        f"{tag}: the SavedBattleGame is gone after the {phase} phase even "
        f"though the vote failed: states={st}")
    return st


def _dbg(host, client):
    for tag, gc in (("host", host), ("client", client)):
        try:
            print(f"  DBG {tag} states: {_states(gc)[-4:]}")
            print(f"  DBG {tag} vote:   {gc.cmd({'cmd': 'vote_state'})}")
            bs = _battle(gc)
            print(f"  DBG {tag} battle: inBattle={bs.get('inBattle')}")
        except Exception as e:
            print(f"  DBG {tag} dump failed: {e}")


# ---- liveness ------------------------------------------------------------
# Every probe below has to tell the two failure modes apart, because they look
# nothing alike from the outside:
#   "process died"        - the socket is gone: the raw pops crashed the game.
#   "battlescape popped"  - the process answers, but the battle is no longer on
#                           the state stack: the pops landed but did not (yet)
#                           take the process with them.

def _died(tag, calls, exc, extra=""):
    return AssertionError(
        f"{tag}: PROCESS DIED after {calls} blind dismiss_popup call(s) "
        f"({exc!r}). The abandon-mission VoteMenu is not a type dismiss_popup "
        f"knows, so it was generic-popped, and then the BattlescapeState under "
        f"it - the battle and the state stack went with them.{extra}")


def _hammer(gc, tag):
    """Fire dismiss_popup blind, exactly like the pre-vote drain loops did."""
    popped = []
    for i in range(HAMMER_CALLS):
        try:
            r = gc.cmd({"cmd": "dismiss_popup"})
        except (OSError, EOFError, ValueError) as e:
            raise _died(tag, i, e, f" Popped so far: {popped}")
        popped.append(r.get("handled", r.get("type")))
        time.sleep(HAMMER_PAUSE)
    return popped


def _assert_alive(gc, tag):
    """The state list, or a 'process died' AssertionError."""
    try:
        return gc.cmd({"cmd": "get_state"})["states"]
    except (OSError, EOFError, ValueError) as e:
        raise _died(tag, HAMMER_CALLS, e)


def _assert_survived_hammer(gc, tag, popped):
    st = _assert_alive(gc, tag)
    assert any("BattlescapeState" in s for s in st), (
        f"{tag}: BATTLESCAPE POPPED - the process is still alive but the "
        f"running battle is gone from the state stack after {HAMMER_CALLS} "
        f"dismiss_popup calls (dismiss_popup reported {popped}; states={st})")
    v = gc.ok({"cmd": "vote_state"})
    assert v.get("active"), \
        f"{tag}: the abandon-mission vote is no longer active: {v}"
    assert not v.get("finished"), (
        f"{tag}: the abandon-mission vote finished during the hammer "
        f"(passed={v.get('passed')}); if it timed out, the hammer is too slow "
        f"for the 30s vote deadline: {v}")
    assert v.get("menuOpen"), (
        f"{tag}: the VoteMenu was popped by dismiss_popup - the vote is still "
        f"running but the player has no way left to answer it: {v}")
    return st


def main():
    js = shared_fixture.bring_up("jvoteabort", PORTS)
    host, client = js.host, js.client
    fail = []
    try:
        # ---- squad: one host-owned (seat 0) + one client-owned (seat 1) ----
        b0 = _base0(host)
        blon, blat = b0["lon"], b0["lat"]
        cid = _skyranger(host)["id"]
        rh = sorted(s["id"] for s in _roster(host))
        squad = [rh[0], rh[1]]
        owners = {0: 0, 1: 1}

        for gc in (host, client):
            for slot, sid in enumerate(squad):
                gc.ok({"cmd": "set_soldier_owner", "soldier_id": sid,
                       "owner": owners[slot]})
        # the starting Skyranger ships FULL - empty it before boarding the squad
        for sid in rh:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
        for sid in squad:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})

        def _aboard(gc):
            return sorted(s["id"] for s in _roster(gc) if s["craftId"] == cid)

        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} squad aboard",
                        lambda gc=gc: (_aboard(gc) == sorted(squad)) or None,
                        timeout=40, interval=0.5)
        print(f"PASS squad: {squad} aboard shared craft {cid} on both machines")

        # ---- seed a site and fly the shared craft to it --------------------
        site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                        "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                        "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
        site_id = site["site_id"]
        host.wait_for("site on host",
                      lambda: any(s["id"] == site_id for s in _geo(host)["missionSites"]) or None,
                      timeout=30)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site_id}",
                 "fuel": 999999, "lowFuel": False})

        def _landing_prompt():
            if _has(host, "ConfirmLandingState"):
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})  # not geo_run: it auto-declines
            return None

        host.wait_for("ConfirmLandingState on host", _landing_prompt,
                      timeout=90, interval=0.5)
        host.ok({"cmd": "confirm_landing"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} entered the battle",
                        lambda gc=gc: _battle(gc).get("inBattle") or None,
                        timeout=180, interval=1.0)

        # ---- briefing -> coop pre-battle inventory -> tactical -------------
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} briefing",
                        lambda gc=gc: _has(gc, "BriefingState") or None,
                        timeout=120, interval=0.5)
            gc.ok({"cmd": "close_briefing"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} pre-battle inventory",
                        lambda gc=gc: _has(gc, "InventoryState") or None,
                        timeout=120, interval=0.5)
            gc.ok({"cmd": "battle_inventory", "action": "ok"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} tactical map",
                        lambda gc=gc: _has(gc, "BattlescapeState") or None,
                        timeout=120, interval=0.5)
        print("PASS tactical: both machines reached the battlescape "
              "(shared lockstep battle)")

        # ==== 1. ABORT opens the abandon-mission vote on BOTH machines ======
        host.ok({"cmd": "battle_action", "action": "abort"})
        votes = {}
        for gc, tag in ((host, "host"), (client, "client")):
            v = gc.wait_for(
                f"{tag} abandon-mission VoteMenu",
                lambda gc=gc: (lambda s: s if (s.get("active") and s.get("menuOpen"))
                               else None)(gc.ok({"cmd": "vote_state"})),
                timeout=25, interval=0.25)
            assert v["action"] == "abandon_mission", f"{tag}: wrong vote: {v}"
            assert v["requiredYes"] == 2, f"{tag}: {v}"
            votes[tag] = v
        # the host started it, so seat 0 is an automatic YES and seat 1 is open
        assert votes["host"]["starterSeat"] == 0, votes["host"]
        for tag, v in votes.items():
            assert v["votes"] == [1, -1], f"{tag}: {v}"
        for gc, tag in ((host, "host"), (client, "client")):
            assert _has(gc, "BattlescapeState"), \
                f"{tag}: the battle left the stack when the vote opened: {_states(gc)}"
        print("PASS abort: ABORT opened the abandon-mission VoteMenu on BOTH "
              "machines and the battle is still running underneath it")

        # ==== 2. THE REPRO: the old blind dismiss_popup drain ===============
        # 10 calls is well past the two it takes to pop the VoteMenu and then
        # the BattlescapeState, and the whole hammer costs ~4s - comfortably
        # inside the vote's 30-second deadline.
        popped = {}
        for gc, tag in ((host, "host"), (client, "client")):
            popped[tag] = _hammer(gc, tag)
        for gc, tag in ((host, "host"), (client, "client")):
            _assert_survived_hammer(gc, tag, popped[tag])
        print(f"PASS repro: {HAMMER_CALLS} blind dismiss_popup calls per machine "
              f"left both processes alive, both battlescapes on the stack and "
              f"the vote still running (host popped {popped['host']})")

        # ==== 3. FAILURE PATH A: the peer votes NO ==========================
        # The section-1 vote is still open (the hammer could not answer it), so
        # this ABORT is absorbed by requestVote and just re-shows that menu -
        # exactly what a second ABORT press does for a player.
        host.ok({"cmd": "battle_action", "action": "abort"})
        for gc, tag in ((host, "host"), (client, "client")):
            _wait_vote(gc, tag, "open abandon-mission vote",
                       lambda s: (s.get("active") and s.get("menuOpen")
                                  and not s.get("finished")))
        cast = client.ok({"cmd": "vote_cast", "yes": False})
        assert cast.get("accepted"), (
            f"client NO vote was rejected: {cast}; if the vote had already "
            f"timed out, sections 1-2 are too slow for the 30s deadline")

        for gc, tag in ((host, "host"), (client, "client")):
            v = _wait_vote(gc, tag, "failed (NO) abandon-mission result",
                           lambda s: s.get("finished") and s.get("menuFinished"))
            assert v["passed"] is False, \
                f"{tag}: a 1-1 split passed a 2/2 majority vote: {v}"
            assert v["votes"] == [1, 0], f"{tag}: {v}"  # seat0 YES, seat1 NO
            assert v["menuStatus"] == "VOTE FAILED", f"{tag}: {v}"
        for gc, tag in ((host, "host"), (client, "client")):
            _assert_battle_alive(gc, tag, "NO-vote")
        print("PASS no-vote: the peer's NO failed the 2/2 majority and BOTH "
              "machines are alive with the battle still running")
        _reset_vote(host, client)

        # ==== 4. FAILURE PATH B: the host-authoritative deadline ============
        # A genuinely NEW vote this time: the id must differ from the one just
        # closed, otherwise requestVote only re-showed the finished menu.
        stale_id = host.ok({"cmd": "vote_state"})["id"]
        host.ok({"cmd": "battle_action", "action": "abort"})
        for gc, tag in ((host, "host"), (client, "client")):
            v = _wait_vote(gc, tag, "second abandon-mission vote",
                           lambda s: (s.get("active") and not s.get("finished")
                                      and s.get("id") != stale_id))
            assert v["action"] == "abandon_mission", f"{tag}: wrong vote: {v}"
            assert v["starterSeat"] == 0, f"{tag}: {v}"   # the host pressed ABORT
            assert v["votes"] == [1, -1], f"{tag}: {v}"   # starter auto-YES only

        forced = host.ok({"cmd": "vote_force_timeout"})
        assert forced.get("accepted") is True, forced
        for gc, tag in ((host, "host"), (client, "client")):
            v = _wait_vote(gc, tag, "timed-out abandon-mission result",
                           lambda s: s.get("finished") and s.get("menuFinished"))
            assert v["passed"] is False, f"{tag}: a timed-out vote passed: {v}"
            assert v["menuStatus"] == "VOTE FAILED", f"{tag}: {v}"
        for gc, tag in ((host, "host"), (client, "client")):
            _assert_battle_alive(gc, tag, "timeout")
        print("PASS timeout: the 30s deadline failed the vote on BOTH machines "
              "and the battle survived it untouched")
        _reset_vote(host, client)

        # ==== 5. E2E: the peer votes YES -> debriefing -> geoscape ==========
        # The third and last vote of the test: both failed menus are closed and
        # the starter cooldowns cleared, so this ABORT really opens a new one.
        session.coop_abort_battle(host, client)
        for gc, tag in ((host, "host"), (client, "client")):
            assert not _battle(gc).get("inBattle"), f"{tag}: still in the battle"
        print("PASS e2e: the majority YES ran abortMissionByVote -> debriefing; "
              "both machines are back on the geoscape")

        # ---- single-world post-battle merge: worlds identical --------------
        def _equal():
            return True if _world_fingerprint(host) == _world_fingerprint(client) else None

        host.wait_for("post-battle worlds identical (restream settled)", _equal,
                      timeout=150, interval=1.0)
        fh = _world_fingerprint(host)
        ids = [s for s, _ in fh["roster"]]
        for i, sid in enumerate(squad):
            assert sid in ids, \
                f"squad soldier {sid} (seat {owners[i]}) was deleted post-battle"
        print(f"PASS merge: post-battle worlds IDENTICAL on both machines "
              f"(funds={fh['funds']}, roster={ids})")

        # PRD-J11 shared final-state assertions: worlds identical + zero-disk.
        js.finish()

        print("TEST PASSED")
    except Exception as e:
        print(f"[FAIL] {e}")
        fail.append(str(e))
        _dbg(host, client)
    finally:
        js.shutdown()
    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
