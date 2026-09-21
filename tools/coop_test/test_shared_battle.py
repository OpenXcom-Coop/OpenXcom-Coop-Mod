"""PRD-J09 AC2/AC3 - SHARED squad battle + single-world post-battle merge.

In a SHARED campaign there is ONE shared world. A mission flown from a shared
craft must:

  1. START host-side from the shared world with NO two-world merge (the SEPARATE
     CoopState(88)/sendCraft/"battleclient" dance would duplicate the shared
     soldiers). The host generates the battle and ships "battlehost"; the client
     loads it and both run the existing lockstep coop battle.
  2. Split control by OWNERSHIP: each BattleUnit inherits _coop from its
     soldier's ownerPlayerId (seat 0 -> host control, any other seat -> client).
     Asserted on BOTH machines (the split rides the shared battlehost blob).
  3. After debriefing, both worlds are IDENTICAL (funds, roster, base stores).
     The host's lockstep-debriefed world is authoritative and is restreamed whole
     to the replica (the PRD's sledgehammer merge). Crucially the host's SEPARATE
     "delete the other player's battle copies" cleanup must NOT run: in SHARED the
     client-owned soldiers carry _coop=1 but are legitimate members of the single
     world and must survive.

Two scenarios:
  mixed       AC2 - host-owned (seat 0) + client-owned (seat 1) soldier aboard;
                    units split coop=0 / coop=1 on both machines.
  solo_client AC3 - only CLIENT-owned soldiers aboard; every deployed unit is
                    coop=1 (the host controls none) and the worlds still merge.
                    NOTE: in the host-authoritative SHARED model the host is the
                    battle authority even for a solo-seat squad, so it enters the
                    battle as a unit-less spectator rather than staying on the
                    geoscape - see session-notes-9.md (PRD-anchor discrepancy).

SPEC 19 (W1-P20) S2 (un-skipped, re-pointed): the bring-up now goes through
`session.bring_up_shared_mixed_battle` (F355's briefing-close-first ordering -
the old :165-191 shape waited for the client's `inBattle` BEFORE the host
closed its briefing, which hangs forever, F362), and each scenario now runs
the spec (f) common tail after the existing control-split assertion:
T-SPLIT, T-CMD (the host leg only in `mixed` - `solo_client` skips it BY
CONSTRUCTION, REV E.48 C.4's connected-seat-with-no-live-unit case: the host
owns no unit to be refused on), T-EXIT.

STOP note (evidence, not a guess): T-EXIT calls `session.coop_abort_battle`,
which drives the pre-rewrite ABANDON-MISSION VOTE. At this tip that vote does
not exist any more: `BattlescapeState::btnAbortClick` (BattlescapeState.cpp
:1652-1663) refuses only the CLIENT's press and otherwise pushes the vanilla
`AbortMissionState` unconditionally ("W1-P5 ruling D8/WV-D14: ABORT MISSION
ends in setAborted()+finishBattle() - a battle-wide, host-authoritative
decision. The multiplayer VOTE... is r4 T3 (executeVoteAction('abandon_
mission') is still a logging stub)"), and `AbortMissionState::btnOkClick`
(AbortMissionState.cpp:198-220) confirms: no `requestVote` call anywhere.
Captured directly: the host's own log shows `push class
OpenXcom::AbortMissionState depth=3` where `coop_abort_battle` expects a
`VoteMenu`, so its `vote_state` poll times out. EVERY existing caller of
`session.coop_abort_battle` in this suite (test_vote_abort_battle.py,
test_shared_base_defense.py, test_skirmish_end_main_menu.py,
test_coop_debrief_sync.py, test_shared_soldier_gift_dup.py,
test_shared_month_run.py) is independently `SKIP-PENDING` at this tip, so this
is not something S2 broke - the helper has never been exercised against a
live rewrite-era battle. This blocks T-EXIT (and therefore the post-battle
world-equality legs after it) identically in both scenarios; it is r4 T3's
gap, not a battle-ENTRY defect, so it is reported here rather than routed
around with an unsanctioned lever.

Run:  python tools/coop_test/test_shared_battle.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session
import geo


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
            print(f"  DBG {tag} states: {_states(gc)[-3:]}")
            c = gc.cmd({"cmd": "get_coop"})
            print(f"  DBG {tag} coop: host={c.get('host')} shared={c.get('shared')} "
                  f"missionEnd={c.get('coopMissionEnd')} dialog={c.get('coopDialog')}")
            bs = _battle(gc)
            if bs.get("inBattle"):
                print(f"  DBG {tag} units(soldier,coop,owner): "
                      f"{[(u['soldierId'], u['coop'], u['owner']) for u in bs['units'] if u['soldierId'] != -1]}")
            print(f"  DBG {tag} world: {_world_fingerprint(gc)}")
        except Exception as e:
            print(f"  DBG {tag} dump failed: {e}")


def run_scenario(label, owners, want_coop, ports, fail, host_has_unit):
    """owners: {slot: seat} for the two squad soldiers (slot 0/1 of the roster).
       want_coop: {slot: expected BattleUnit _coop}.
       host_has_unit: whether the host owns a unit in this squad - T-CMD's host
       leg (click-select refusal) runs only when True; `solo_client` passes
       False and skips it BY CONSTRUCTION (no host-owned unit to refuse on)."""
    print(f"\n===== scenario '{label}' =====")
    js = shared_fixture.bring_up(f"jbat_{label}", ports)
    host, client = js.host, js.client
    try:
        _, _, squad = session.bring_up_shared_mixed_battle(js, owners)
        seats = {sid: owners[i] for i, sid in enumerate(squad)}
        print(f"PASS squad: {seats} aboard the shared craft; battle entered live "
              f"(F355 briefing-close-first ordering)")

        # ---- control split = ownership, on BOTH machines ------------------
        for tag, gc in (("host", host), ("client", client)):
            us = {u["soldierId"]: u for u in _battle(gc)["units"] if u["soldierId"] != -1}
            assert sorted(us) == sorted(squad), \
                f"{tag}: deployed {sorted(us)} want {sorted(squad)} (two-world merge duplicated?)"
            for i, sid in enumerate(squad):
                assert us[sid]["coop"] == want_coop[i], \
                    f"{tag}: soldier {sid} (seat {owners[i]}) coop={us[sid]['coop']} want {want_coop[i]}"
        if set(want_coop.values()) == {1}:
            print("PASS control-split: every deployed unit is coop=1 (client-controlled) on "
                  "BOTH machines - the host commands none of this solo-seat squad")
        else:
            print("PASS control-split: on BOTH machines the host-owned unit is coop=0 and the "
                  "client-owned unit is coop=1; exactly the squad deployed")

        # ---- SPEC 19 (W1-P20) common tail: T-SPLIT / T-CMD / T-EXIT --------
        expected_seats = {sid: want_coop[i] for i, sid in enumerate(squad)}
        session.assert_t_split(host, client, expected_seats, what=f"S2 {label}")

        seat1_actor = next(sid for i, sid in enumerate(squad) if want_coop[i] == 1)
        seat0_actor = next((sid for i, sid in enumerate(squad) if want_coop[i] == 0), None)
        session.assert_t_cmd(host, client, seat1_actor, seat0_actor,
                             host_check=host_has_unit, what=f"S2 {label}")

        session.assert_t_exit(host, client, what=f"S2 {label}")

        # ---- single-world post-battle merge: worlds identical -------------
        def _equal():
            return True if _world_fingerprint(host) == _world_fingerprint(client) else None

        host.wait_for("post-battle worlds identical (restream settled)", _equal,
                      timeout=150, interval=1.0)
        fh = _world_fingerprint(host)
        ids = [s for s, _ in fh["roster"]]
        for i, sid in enumerate(squad):
            assert sid in ids, \
                f"squad soldier {sid} (seat {owners[i]}) was deleted post-battle (guest cleanup ran!)"
        print(f"PASS merge: post-battle worlds IDENTICAL on both machines "
              f"(funds={fh['funds']}, roster={ids}); every squad soldier survived")

        # PRD-J11: the shared final-state assertions. Strictly stronger than the
        # local fingerprint above (facilities/stores/transfers/research/craft
        # identity too), so the post-battle restream is checked whole.
        js.finish()

        print(f"scenario '{label}': PASSED")
    except Exception as e:
        print(f"[FAIL] {label}: {e}")
        fail.append(f"{label}: {e}")
        _dbg(host, client)
    finally:
        js.shutdown()


def main():
    fail = []
    # AC2: mixed squad - one host-owned (seat 0) + one client-owned (seat 1).
    run_scenario("mixed", {0: 0, 1: 1}, {0: 0, 1: 1}, (48770, 48771, 48070), fail,
                 host_has_unit=True)
    # AC3: solo-seat squad - only CLIENT-owned soldiers aboard.
    run_scenario("solo_client", {0: 1, 1: 1}, {0: 1, 1: 1}, (48772, 48773, 48072), fail,
                 host_has_unit=False)

    print("\n==== PRD-J09 / SPEC 19 (W1-P20) S2 battle summary ====")
    if fail:
        print(f"  FAILURES: {fail}")
        sys.exit(2)
    print("  mixed + solo_client: SHARED battles start host-side from the shared world, "
          "split control by ownership on both machines, admit/deny commands per T-CMD, "
          "and merge to identical worlds.")
    sys.exit(0)


if __name__ == "__main__":
    main()
