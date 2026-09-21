"""Playtest (co-ownership, END-TO-END): the BOOTSTRAP owner split must actually
split in-battle control - not just the geoscape roster.

test_shared_soldier_ownership.py proved the starting roster's ownerPlayerId is split
0/1. But the earlier battle test stamped owners with set_soldier_owner, so it never
proved the *bootstrap* split reaches the battle. This test relies ONLY on the
bootstrap owners: it takes one seat-0 soldier and one seat-1 soldier straight from
the split roster, flies them to a mission, enters the SHARED battle, and asserts:

  - each deployed BattleUnit's _coop is derived from its soldier's bootstrap owner
    (owner 0 -> coop 0 = host-controlled, owner 1 -> coop 1 = client-controlled),
  - the squad is genuinely SPLIT (not every unit the same coop = "co-owned"),
  - both machines agree.

If this fails, the bootstrap split is not reaching battle control ("all soldiers
co-owned").

SPEC 19 (W1-P20) S3 (un-skipped, re-pointed): the bring-up now goes through
`session.bring_up_shared_mixed_battle(js, owners=None)` (F355's briefing-close-
first ordering), which boards the roster's two LOWEST ids unstamped - exactly
the bootstrap pair this test needs, since consecutive soldier ids alternate
owner under the bootstrap split (SavedGame.cpp:785-795, `getId() % 2`). The
spec (f) common tail (T-SPLIT with expected coop = bootstrap owner, T-CMD)
runs right after the existing battle-control assertion, mid-battle, so the
pre-existing on-load-migration coverage below still runs unconditionally;
T-EXIT is last (it ends the battle) and is where this file currently stops -
see the STOP note.

STOP note (evidence, not a guess): T-EXIT calls `session.coop_abort_battle`,
which drives the pre-rewrite ABANDON-MISSION VOTE. At this tip that vote does
not exist any more - see test_shared_battle.py's own STOP note (same root
cause, same captured evidence: BattlescapeState.cpp:1652-1663,
AbortMissionState.cpp:198-220, every existing `coop_abort_battle` caller
independently SKIP-PENDING). This is r4 T3's gap, not a battle-ENTRY defect.

Run:  python tools/coop_test/test_shared_soldier_ownership_battle.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session


def _roster(gc):
    out = []
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        out.extend(b["soldiers"])
    return out


def main():
    js = shared_fixture.bring_up("jownbat", (48850, 48851, 48150))
    host, client = js.host, js.client
    try:
        # bootstrap owners (NO set_soldier_owner) - must already be split.
        owner = {s["id"]: s["owner"] for s in _roster(host)}
        assert owner == {s["id"]: s["owner"] for s in _roster(client)}, \
            "host/client disagree on bootstrap owners"
        seat0 = sorted(sid for sid, o in owner.items() if o == 0)
        seat1 = sorted(sid for sid, o in owner.items() if o == 1)
        assert seat0 and seat1, f"bootstrap roster not split: seat0={seat0} seat1={seat1}"
        print(f"PASS bootstrap: roster split seat0={seat0} seat1={seat1} (no manual stamping)")

        # board exactly the two bootstrap-owned soldiers on the shared craft and
        # enter the battle LIVE, F355-ordered (session.bring_up_shared_mixed_
        # battle with owners=None: no set_soldier_owner call, existing owners
        # kept, the roster's two LOWEST ids boarded - the bootstrap split's own
        # getId() % 2 rule means those two ids already straddle both seats).
        _, _, squad = session.bring_up_shared_mixed_battle(js, owners=None)
        assert len(squad) == 2 and {owner[squad[0]], owner[squad[1]]} == {0, 1}, (
            f"FIXTURE: the default squad {squad} (owners {[owner[s] for s in squad]}) "
            f"is not one seat-0 + one seat-1 soldier - S3 needs the bootstrap "
            f"split's two LOWEST roster ids to already straddle both seats")
        want_coop = {sid: owner[sid] for sid in squad}
        print(f"PASS entry: bootstrap squad {squad} owners {[owner[s] for s in squad]} "
              f"boarded and the SHARED battle entered live from the bootstrap roster "
              f"(no manual stamping)")

        # THE ASSERTION: bootstrap owner -> battle _coop, split, agreed on both.
        for tag, gc in (("host", host), ("client", client)):
            us = {u["soldierId"]: u for u in session.battle_state(gc)["units"]
                  if u["soldierId"] != -1}
            assert sorted(us) == sorted(squad), \
                f"{tag}: deployed {sorted(us)} want {sorted(squad)}"
            coops = set()
            for sid in squad:
                got = us[sid]["coop"]
                coops.add(got)
                assert got == want_coop[sid], \
                    f"{tag}: soldier {sid} (bootstrap owner {owner[sid]}) coop={got} " \
                    f"want {want_coop[sid]} - bootstrap split did NOT reach battle control"
            assert coops == {0, 1}, \
                f"{tag}: squad not split in battle (coops={coops}) - soldiers co-owned"
        print("PASS split: bootstrap owner 0->coop0(host), 1->coop1(client) on BOTH machines")
        # Requirement #3 (control own soldiers on own turn) is satisfied by this split:
        # SHARED reuses the SEPARATE lockstep verbatim (no isSharedCampaign branch in the
        # battlescape), and the turn machinery gates the active player to its own coop
        # units. The per-unit coop split asserted above is the only SHARED-specific input
        # that path needs, so validating it here guards #3 against ownership regressions.

        # ---- SPEC 19 (W1-P20): T-SPLIT / T-CMD (mid-battle, before T-EXIT) --
        session.assert_t_split(host, client, want_coop, what="S3 bootstrap ownership")
        seat1_actor = next(sid for sid in squad if want_coop[sid] == 1)
        seat0_actor = next(sid for sid in squad if want_coop[sid] == 0)
        session.assert_t_cmd(host, client, seat1_actor, seat0_actor,
                             what="S3 bootstrap ownership")

        # ---- ON-LOAD MIGRATION: an OLD save (pre-split) must heal on load. -----
        # Simulate a save created before the split existed: force every soldier back
        # to the unowned sentinel 999, then round-trip through SavedGame::load.
        for sid in owner:
            host.ok({"cmd": "set_soldier_owner", "soldier_id": sid, "owner": 999})
        rt = host.ok({"cmd": "reload_save_roundtrip"})
        assert rt.get("ok"), f"roundtrip failed: {rt}"
        loaded = {s["id"]: s["owner"] for s in rt["soldiers"]}
        assert loaded, "roundtrip returned no soldiers"
        assert all(o in (0, 1) for o in loaded.values()), \
            f"on-load migration left unowned soldiers: {loaded}"
        n0 = sum(1 for o in loaded.values() if o == 0)
        n1 = sum(1 for o in loaded.values() if o == 1)
        assert abs(n0 - n1) <= 1, f"on-load migration split uneven: seat0={n0} seat1={n1}"
        print(f"PASS migration: a 999-owned (pre-fix) save healed on load -> "
              f"seat0={n0} seat1={n1}, no soldier left co-owned")

        # ---- SPEC 19 (W1-P20): T-EXIT closes the battle - see the module's own
        # STOP note for why this currently blocks (r4 T3, not a battle-entry
        # defect: the abandon-mission vote is unimplemented at this tip).
        session.assert_t_exit(host, client, what="S3 bootstrap ownership")

        print("ALL SPEC 19 (W1-P20) S3 SHARED BOOTSTRAP-OWNERSHIP-IN-BATTLE TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
