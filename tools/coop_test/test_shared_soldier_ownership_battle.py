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

The bring-up goes through `session.bring_up_shared_mixed_battle(js, owners=None)`
(the briefing closes first), which boards the roster's two LOWEST ids unstamped -
exactly the bootstrap pair this test needs, since consecutive soldier ids
alternate owner under the bootstrap split (SavedGame.cpp:785-795, `getId() % 2`).
The shared battle checks (the control split with expected coop = bootstrap owner,
then the seat commands) run right after the battle-control assertion, mid-battle,
so the on-load-migration coverage below still runs unconditionally; the battle
exit is last (it ends the battle).

Battle exit: `session.coop_abort_battle` uses the host-authoritative abort (host
btnAbortClick -> vanilla AbortMissionState -> confirm -> finishBattle ->
geoscape). SHARED finishBattle returns BOTH machines (both on GeoscapeState, no
crash, no desyncSeen).

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


def _failure_dump(host, client, when):
    """ONE evidence block on a failure of the seat-command check or
    of the on-load-migration set_soldier_owner loop - both machines' player
    units and base rosters, from the existing battle_state / get_soldiers
    probes. Never raises: the caller re-raises the original failure."""
    print(f"EVIDENCE FAILURE-DUMP BEGIN ({when})", flush=True)
    for tag, gc in (("host", host), ("client", client)):
        try:
            bs = session.battle_state(gc)
            units = [(u.get("id"), u.get("soldierId"), u.get("status"), u.get("health"),
                      u.get("stun"), u.get("coop"), u.get("owner"),
                      (u.get("x"), u.get("y"), u.get("z")), u.get("isOut"))
                     for u in bs.get("units", [])
                     if u.get("originalFaction") == session.FACTION_PLAYER
                     or u.get("soldierId", -1) != -1]
            print(f"  {tag}: selectedId={bs.get('selectedId')} turn={bs.get('turn')} "
                  f"side={bs.get('side')} playerUnits(id,soldierId,status,health,stun,"
                  f"coop,owner,pos,isOut)={units}", flush=True)
        except Exception as e:  # noqa: BLE001 - evidence only, never masks the failure
            print(f"  {tag}: battle_state probe failed: {e!r}", flush=True)
        try:
            for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
                print(f"  {tag}: base {b.get('name')!r} roster(id,owner,dead)="
                      f"{[(s['id'], s['owner'], s.get('dead')) for s in b['soldiers']]}",
                      flush=True)
        except Exception as e:  # noqa: BLE001 - evidence only, never masks the failure
            print(f"  {tag}: get_soldiers probe failed: {e!r}", flush=True)
    print("EVIDENCE FAILURE-DUMP END", flush=True)


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
        # enter the battle LIVE, the briefing closed first (session.bring_up_shared_mixed_
        # battle with owners=None: no set_soldier_owner call, existing owners
        # kept, the roster's two LOWEST ids boarded - the bootstrap split's own
        # getId() % 2 rule means those two ids already straddle both seats).
        _, _, squad = session.bring_up_shared_mixed_battle(js, owners=None)
        assert len(squad) == 2 and {owner[squad[0]], owner[squad[1]]} == {0, 1}, (
            f"FIXTURE: the default squad {squad} (owners {[owner[s] for s in squad]}) "
            f"is not one seat-0 + one seat-1 soldier - this test needs the bootstrap "
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

        # ---- control split / seat commands (mid-battle, before the battle exit) --
        session.assert_control_split(host, client, want_coop, what="bootstrap ownership")
        seat1_actor = next(sid for sid in squad if want_coop[sid] == 1)
        seat0_actor = next(sid for sid in squad if want_coop[sid] == 0)
        try:
            session.assert_seat_commands(host, client, seat1_actor, seat0_actor,
                                 what="bootstrap ownership")
        except Exception:
            _failure_dump(host, client, "seat-command check failed")
            raise
        print(f"after the seat-command check: host selectedId="
              f"{session.battle_state(host).get('selectedId')} client selectedId="
              f"{session.battle_state(client).get('selectedId')}", flush=True)

        # ---- ON-LOAD MIGRATION: an OLD save (pre-split) must heal on load. -----
        # Simulate a save created before the split existed: force every soldier back
        # to the unowned sentinel 999, then round-trip through SavedGame::load.
        for sid in owner:
            try:
                host.ok({"cmd": "set_soldier_owner", "soldier_id": sid, "owner": 999})
            except Exception:
                _failure_dump(host, client, f"set_soldier_owner {sid} failed")
                raise
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

        # ---- the battle exit closes the battle via the host-authoritative
        # abort: SHARED finishBattle returns BOTH machines cleanly.
        session.assert_battle_exit(host, client, what="bootstrap ownership")

        print("ALL SHARED BOOTSTRAP-OWNERSHIP-IN-BATTLE TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
