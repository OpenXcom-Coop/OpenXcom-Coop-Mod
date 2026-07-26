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

2. THE E2E
   With the hammer survived, finish the mission the way a player does, through
   session.coop_abort_battle(): the peer votes YES, the 2/2 majority passes,
   the host runs abortMissionByVote -> finishBattle -> DebriefingState and the
   client follows via EndCoopBattle. Both machines land back on the geoscape
   holding ONE identical shared world.

Only ONE vote is started for the whole test (the second battle_action/abort
inside coop_abort_battle is absorbed by requestVote, which just re-shows the
already-active vote), so the host's 60-second vote-starter cooldown is never
reached and no second battle is needed.

Run:  python tools/coop_test/test_vote_abort_battle.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

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

        # ==== 3. E2E: the peer votes YES -> debriefing -> geoscape ==========
        # Reuses the already-open vote; no second vote is started, so the
        # 60-second vote-starter cooldown never comes into play.
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
