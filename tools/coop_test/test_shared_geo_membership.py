"""Shared/Separate geoscape snapshot: spawns and despawns are detected by real id.

The host's position snapshot rides a last-write-wins conflation slot, which can
drop the intermediate snapshots. A UFO or mission site that spawns and despawns
between two delivered snapshots would then never reach the replica, so the host
also sends the snapshot on the reliable FIFO lane whenever its UFO/mission
membership changes (connectionTCP::geoMembershipChanged).

That check read the legacy mirror snapshot's keys (`ufo_id` / `mission_id`). The
Shared/Separate snapshot carries `id` / `uniqueId` for UFOs and `id` for mission
sites, so every key read as 0: each set collapsed to {0} (or {} when empty) and
the reliable resend fired only on empty <-> non-empty transitions. Adding a
second UFO or site, or removing one while others remain, went unnoticed.

Which snapshot slips through the conflation slot is a timing race, so this test
does not chase a dropped snapshot. It reads the host's recorded membership
(the `geo_membership` test command) and asserts, deterministically, that it is
keyed by the ids the replica matches on and that every spawn / despawn into a
non-empty set is flagged for the reliable resend:

  UFOS     two undetected UFOs (both display id 0) are recorded by unique id,
           and the second spawn counts as a change.
  DESPAWN  a third UFO destroyed and removed by the host leaves the set while
           the other two stay, and counts as a change.
  SITES    two mission sites are recorded by site id, and the second spawn
           counts as a change.

Run:  python tools/coop_test/test_shared_geo_membership.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import geo

UFO = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH",
       "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID", "trajectory": "P0",
       "hours": 240}


def _geo(gc):
    return gc.ok({"cmd": "geo_state"})


def _base0(gc):
    for b in _geo(gc)["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base in geo_state")


def _membership(gc):
    m = gc.ok({"cmd": "geo_membership"})
    return set(m["ufoIds"]), set(m["missionIds"]), m["changes"]


def _wait_membership(host, what, pred, timeout=30):
    """Poll the host's recorded membership until pred(ufoIds, missionIds, changes)."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = _membership(host)
        if pred(*last):
            return last
        # The host builds the snapshot only while the geoscape is the top screen.
        geo.drain_popups(host)
        time.sleep(0.3)
    ufos, sites, changes = last
    raise AssertionError(
        f"{what}: never satisfied - host recorded ufoIds={sorted(ufos)} "
        f"missionIds={sorted(sites)} changes={changes}")


def _ufo_ids(gc):
    return {u["uniqueId"] for u in _geo(gc)["ufos"]}


def main():
    js = shared_fixture.bring_up("jgeomem", (49260, 49262, 48460))
    host, client = js.host, js.client
    try:
        hb = _base0(host)
        _, _, changes0 = _membership(host)

        # ---- UFOS: recorded by unique id, the second spawn is a change -------
        # Undetected UFOs all carry display id 0, so only the unique id tells
        # them apart (it is also what the replica matches them by).
        a = host.ok(dict(UFO, state="flying", speed=1, detected=False,
                         lon=hb["lon"] - 1.0, lat=hb["lat"] + 0.2))
        ua = a["unique_id"]
        _, _, changes_a = _wait_membership(
            host, f"host records UFO A by unique id {ua}",
            lambda u, s, cnt: ua in u and cnt > changes0)
        print(f"PASS ufo-a: UFO A recorded by unique id {ua}")

        b = host.ok(dict(UFO, state="flying", speed=1, detected=False,
                         lon=hb["lon"] - 1.2, lat=hb["lat"] + 0.3))
        ub = b["unique_id"]
        assert a["ufo_id"] == b["ufo_id"] == 0, \
            f"premise: undetected UFOs share display id 0 (A={a}, B={b})"
        _, _, changes_b = _wait_membership(
            host, f"host records UFO B ({ub}) beside A ({ua}) as a membership change",
            lambda u, s, cnt: {ua, ub} <= u and cnt > changes_a)
        print(f"PASS ufo-b: second UFO {ub} flagged for the reliable resend")

        # Both reach the replica, keyed by the same unique ids.
        client.wait_for("client holds both spawned UFOs",
                        lambda: {ua, ub} <= _ufo_ids(client) or None,
                        timeout=30, interval=0.3)
        print("PASS replica: client holds both UFOs")

        # ---- DESPAWN: a removed UFO leaves the set while others remain -------
        crashed = host.ok(dict(UFO, state="crashed", speed=0,
                               lon=hb["lon"] + 1.4, lat=hb["lat"] - 0.25))
        uc = crashed["unique_id"]
        _, _, changes_c = _wait_membership(
            host, f"host records UFO C ({uc})",
            lambda u, s, cnt: {ua, ub, uc} <= u and cnt > changes_b)
        # The skip below also polls its stop condition on the client, so C must
        # be there first or the skip would stop before the host removed it.
        client.wait_for("client holds UFO C", lambda: uc in _ufo_ids(client) or None,
                        timeout=30, interval=0.3)

        # Destroyed UFOs are deleted on the host's next 5-second tick; run the
        # clock until that happens (it is left stopped, popups closed).
        host.ok({"cmd": "set_ufo_damage", "ufo_id": crashed["ufo_id"], "damage": 1000000})
        geo.skip_ingame_time(
            host, client, minutes=60, speed_idx=2,
            interest=geo.geo_when(
                lambda g: not any(u["uniqueId"] == uc for u in g["ufos"])),
            real_timeout=60)
        assert uc not in _ufo_ids(host), \
            f"premise: the host never removed destroyed UFO {uc}"
        _, _, changes_gone = _wait_membership(
            host, f"host drops UFO {uc} from the set while A and B remain",
            lambda u, s, cnt: uc not in u and {ua, ub} <= u and cnt > changes_c)
        print(f"PASS despawn: removed UFO {uc} flagged for the reliable resend")

        # ---- SITES: recorded by site id, the second spawn is a change --------
        site = {"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                "deployment": "STR_TERROR_MISSION", "race": "STR_SECTOID", "hours": 48}
        s1 = host.ok(dict(site, lon=hb["lon"] + 0.4, lat=hb["lat"] + 0.1))["site_id"]
        _, _, changes_s1 = _wait_membership(
            host, f"host records mission site {s1} by site id",
            lambda u, s, cnt: s1 in s and cnt > changes_gone)
        s2 = host.ok(dict(site, lon=hb["lon"] + 0.6, lat=hb["lat"] + 0.2))["site_id"]
        assert s1 != s2, f"premise: distinct site ids ({s1}, {s2})"
        _wait_membership(
            host, f"host records site {s2} beside {s1} as a membership change",
            lambda u, s, cnt: {s1, s2} <= s and cnt > changes_s1)
        print(f"PASS sites: second site {s2} flagged for the reliable resend")

        js.finish()
        print("ALL SHARED GEO-MEMBERSHIP TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
