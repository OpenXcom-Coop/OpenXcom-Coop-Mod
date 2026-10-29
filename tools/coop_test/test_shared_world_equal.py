"""PRD-J11: the shared world-equality helper itself, and what it can see.

The helper (shared_fixture.assert_world_equal) is wired into every SHARED test's
final state, so it has to be trustworthy in BOTH directions: it must pass on an
equal world, and - the part that actually matters - it must FAIL on an unequal
one. A helper that only ever passes proves nothing.

  EQUAL     a freshly bootstrapped SHARED world compares equal, and stays equal
            across a real mutation (a client buy) once the round-trip lands.
  SENSITIVE force a count-preserving content divergence and prove the helper
            catches it: 7 rifles on the host, 7 pistols on the client. Every
            checksum COUNT (items, soldiers, transfers, production) stays
            identical; only the stores content term chkStores differs, so the
            auto-repair fires only after its debounce. The world-diff helper
            compares exact CONTENTS and catches it inside that window: this is
            the honest negative control.
  REPAIR    force_resync re-streams the authoritative world and equality returns.

Run:  python tools/coop_test/test_shared_world_equal.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

RIFLE = "STR_RIFLE"
PISTOL = "STR_PISTOL"


def _rifles(gc):
    return gc.ok({"cmd": "incoming_transfers"})["items"].get(RIFLE, 0)


def main():
    js = shared_fixture.bring_up("jweq", (48780, 48781, 48080))
    host, client = js.host, js.client
    try:
        # ---- EQUAL: the bootstrap world ----------------------------------
        js.assert_world_equal("bootstrap")

        # the dump is not vacuous: it must actually carry the shared world.
        d = shared_fixture.world_dump(host)
        assert d["campaignType"] == 1, f"fixture dump says not SHARED: {d['campaignType']}"
        assert len(d["bases"]) == 1, f"expected the one shared base, got {len(d['bases'])}"
        b = d["bases"][0]
        assert b["soldiers"], "dump carries no soldier roster"
        assert b["items"], "dump carries no base stores"
        assert b["facilities"], "dump carries no facility grid"
        assert b["crafts"], "dump carries no craft list"
        print(f"PASS dump: funds={d['funds']} bases=1 soldiers={len(b['soldiers'])} "
              f"items={len(b['items'])} facilities={len(b['facilities'])} "
              f"crafts={len(b['crafts'])}")

        # ---- EQUAL: across a real mutation --------------------------------
        r = client.ok({"cmd": "buy", "item": RIFLE, "count": 4})
        assert r.get("sent"), f"client buy not sent: {r}"
        host.wait_for("host applied the client buy",
                      lambda: _rifles(host) == 4 or None, timeout=30, interval=0.5)
        js.assert_world_equal("after a client buy")

        # ---- SENSITIVE: a count-preserving content drift ------------------
        # +7 rifles on the host, +7 pistols on the client. Every checksum count is
        # identical (+7 items on both); only the stores content term differs. The
        # auto-repair needs the mismatch to survive RESYNC_DEBOUNCE_MS (3 s), so
        # the helper below runs inside that window. Only the chk* terms are
        # compared: the response also echoes a per-machine request id.
        def chk(gc):
            return {k: v for k, v in gc.ok({"cmd": "shared_checksum"}).items()
                    if k.startswith("chk")}
        chk_before = chk(host)
        host.ok({"cmd": "give_items", "item": RIFLE, "count": 7})
        client.ok({"cmd": "give_items", "item": PISTOL, "count": 7})
        # chkStores is recomputed at most every 250 ms on each machine.
        deadline = time.time() + 2
        while True:
            chk_h, chk_c = chk(host), chk(client)
            differs = sorted(k for k in chk_h if chk_h[k] != chk_c.get(k))
            if differs == ["chkStores"] or time.time() > deadline:
                break
            time.sleep(0.1)
        assert differs == ["chkStores"], \
            (f"a count-preserving content drift must move only chkStores: "
             f"differs={differs} host={chk_h} client={chk_c}")
        assert chk_h["chkItems"] == chk_before["chkItems"] + 7, \
            f"widened checksum did not track the added items: {chk_before} -> {chk_h}"
        print("PASS content-drift: 7 rifles on the host vs 7 pistols on the client; every "
              "checksum count IDENTICAL, only chkStores differs")

        diff = shared_fixture.world_diff(host, client)
        assert diff, ("the equality helper did NOT catch a content divergence - "
                      "it is not sensitive enough to be worth asserting")
        assert any("items" in d for d in diff), \
            f"caught a divergence, but not the stores one: {diff}"
        print(f"PASS sensitive: helper caught the divergence ({len(diff)} field(s)): "
              f"{diff[0]}")

        # and it is a REAL failure, not just a truthy diff: the assert must raise.
        try:
            shared_fixture.assert_world_equal(host, client, "negative control", timeout=1)
        except AssertionError as e:
            assert "DIVERGED" in str(e), f"unexpected assertion text: {e}"
            print("PASS negative-control: assert_world_equal RAISES on an unequal world")
        else:
            raise AssertionError(
                "assert_world_equal PASSED on a knowingly divergent world - every "
                "'PASS world equality' line in this suite would be worthless")

        # ---- REPAIR: force_resync heals past the checksum's reach ---------
        host.ok({"cmd": "force_resync"})
        shared_fixture.assert_world_equal(host, client, "after force_resync", timeout=90)
        print("PASS repair: force_resync re-streamed the authoritative world; the "
              "store drift is gone")

        js.finish()
        print("ALL SHARED WORLD-EQUALITY TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
