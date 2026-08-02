"""Issue #126 regression: a soldier gifted BACK AND FORTH during a SHARED battle
must not DUPLICATE after the mission ends.

Root cause (pre-fix): an in-battle soldier gift queues a SEPARATE-model physical
hand-off in `_pendingSoldierGifts` (connectionTCP::giftSoldier). In a SHARED
campaign the roster is a single host-authoritative world, so the live ownership
flip + the host's post-battle whole-world restream already move the soldier - but
the queued physical hand-off was NOT fenced for SHARED. After a battle it fired
`sendSoldierGiftPacket` + `removeSoldierFromLocalBases`, and the peer
re-materialised the (still-shared) soldier with a fresh id via `new Soldier`,
leaving TWO copies of the same soldier in the shared roster. The reporter's save
showed exactly this: 6 mission soldiers each present twice (original craft-seated
copy + a phantom copy carrying coopcraft=1 and a brand-new id).

Repro shape:
  * SHARED campaign, one host-owned + one client-owned soldier aboard the shared
    craft, fly to a terror site, enter the SHARED battle, reach the battlescape.
  * HOST gifts its own soldier to the CLIENT, then the CLIENT gifts it straight
    back to the HOST (the "back and forth" from the issue title). The gift-back
    leaves a stale pending physical hand-off on the client.
  * Abort the mission -> debriefing -> geoscape on both machines.
  * ASSERT: neither machine's roster grew or gained a duplicate soldier id.

Pre-fix this fails: the host's authoritative roster gains a fresh-id copy of the
gifted soldier (and the client adopts it via the restream). Post-fix the SHARED
in-battle gift is a pure live ownership flip carried by the restream, so the
roster is unchanged.

Run:  python tools/coop_test/test_shared_soldier_gift_dup.py
Exit 0 = pass; non-zero = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session
import test_shared_battle as B  # reuse the vetted SHARED battle-entry helpers


def _living_ids(gc):
    """Every living soldier id across all bases (order-independent)."""
    ids = []
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        for s in b["soldiers"]:
            if not s["dead"]:
                ids.append(s["id"])
    return ids


def _unit_for(gc, soldier_id):
    for u in B._battle(gc)["units"]:
        if u["soldierId"] == soldier_id:
            return u
    return None


def _aboard(gc, cid):
    return sorted(s["id"] for s in B._roster(gc) if s["craftId"] == cid)


def main():
    js = shared_fixture.bring_up("dup126", (48992, 48993, 48292))
    host, client = js.host, js.client
    try:
        b0 = B._base0(host)
        blon, blat = b0["lon"], b0["lat"]
        cid = B._skyranger(host)["id"]

        owner = {s["id"]: s["owner"] for s in B._roster(host)}
        assert owner == {s["id"]: s["owner"] for s in B._roster(client)}, \
            "host/client disagree on bootstrap owners"
        seat0 = sorted(sid for sid, o in owner.items() if o == 0)
        seat1 = sorted(sid for sid, o in owner.items() if o == 1)
        assert seat0 and seat1, f"bootstrap roster not split: seat0={seat0} seat1={seat1}"
        squad = [seat0[0], seat1[0]]  # one host-owned, one client-owned
        host_sid = squad[0]           # the soldier we will bounce back and forth

        # Baseline roster BEFORE the mission (the invariant we protect).
        pre = sorted(_living_ids(host))
        assert pre == sorted(_living_ids(client)), "host/client rosters differ pre-mission"
        assert len(pre) == len(set(pre)), f"pre-mission roster already has dup ids: {pre}"
        print(f"PASS baseline: {len(pre)} soldiers, no duplicates, host==client")

        # ---- board exactly the two-soldier squad on the shared craft ------
        for sid in owner:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
        for sid in squad:
            host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} squad aboard",
                        lambda gc=gc: (_aboard(gc, cid) == sorted(squad)) or None,
                        timeout=40, interval=0.5)

        # ---- fly to a terror site and enter the SHARED battle -------------
        site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                        "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                        "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
        site_id = site["site_id"]
        host.wait_for("site on host",
                      lambda: any(s["id"] == site_id for s in B._geo(host)["missionSites"]) or None,
                      timeout=30)
        host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                 "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site_id}",
                 "fuel": 999999, "lowFuel": False})

        def _landing_prompt():
            if B._has(host, "ConfirmLandingState"):
                return True
            host.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None
        host.wait_for("ConfirmLandingState on host", _landing_prompt, timeout=90, interval=0.5)
        host.ok({"cmd": "confirm_landing"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} entered the battle",
                        lambda gc=gc: B._battle(gc).get("inBattle") or None,
                        timeout=180, interval=1.0)

        # ---- briefing -> pre-battle inventory -> tactical -----------------
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} briefing", lambda gc=gc: B._has(gc, "BriefingState") or None,
                        timeout=120, interval=0.5)
            gc.ok({"cmd": "close_briefing"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} pre-battle inventory",
                        lambda gc=gc: B._has(gc, "InventoryState") or None, timeout=120, interval=0.5)
            gc.ok({"cmd": "battle_inventory", "action": "ok"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} tactical map",
                        lambda gc=gc: B._has(gc, "BattlescapeState") or None, timeout=120, interval=0.5)
        print("PASS entry: both machines reached the SHARED battlescape")

        # ---- THE REPRO: gift the host soldier to the client, then back ----
        hu = _unit_for(host, host_sid)
        assert hu is not None, f"host soldier {host_sid} not deployed as a battle unit"
        host.ok({"cmd": "battle_gift_select", "unit_id": hu["id"]})
        host.ok({"cmd": "battle_gift", "owner": 1})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} sees soldier gifted to client",
                        lambda gc=gc: ((_unit_for(gc, host_sid) or {}).get("coop") == 1) or None,
                        timeout=30, interval=0.3)

        cu = _unit_for(client, host_sid)
        assert cu is not None, f"client did not receive soldier {host_sid} as a battle unit"
        client.ok({"cmd": "battle_gift_select", "unit_id": cu["id"]})
        client.ok({"cmd": "battle_gift", "owner": 0})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} sees soldier gifted back to host",
                        lambda gc=gc: ((_unit_for(gc, host_sid) or {}).get("coop") == 0) or None,
                        timeout=30, interval=0.3)
        print("PASS gift: soldier bounced host -> client -> host in-battle on both machines")

        # ---- end the mission the only supported way (abort -> vote) -------
        session.coop_abort_battle(host, client)

        # ---- the invariant: NO duplication, NO roster growth --------------
        # The post-battle restream is eventual, so poll until the host roster
        # settles (or the deadline forces the final assertions to fire).
        deadline = time.time() + 60
        while time.time() < deadline:
            hl = _living_ids(host)
            if sorted(hl) == pre and len(hl) == len(set(hl)):
                break
            time.sleep(1.0)

        hl = _living_ids(host)
        cl = _living_ids(client)
        assert len(hl) == len(set(hl)), \
            f"HOST roster has DUPLICATE soldier ids (issue #126): {sorted(hl)}"
        assert len(cl) == len(set(cl)), \
            f"CLIENT roster has DUPLICATE soldier ids (issue #126): {sorted(cl)}"
        assert sorted(hl) == pre, \
            f"HOST roster changed after the mission: pre={pre} post={sorted(hl)}"
        assert sorted(cl) == pre, \
            f"CLIENT roster changed after the mission: pre={pre} post={sorted(cl)}"
        print(f"PASS no-dup: rosters unchanged ({len(pre)} soldiers), no duplicate ids on either machine")

        # Belt and suspenders: the two machines still hold ONE identical world.
        js.finish()
        print("ALL ISSUE #126 SHARED SOLDIER-GIFT DUPLICATION TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
