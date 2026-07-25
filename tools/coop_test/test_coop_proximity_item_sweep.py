"""A proximity grenade going off must not sweep the peer's floor clean.

`BattlescapeGame::checkForProximityGrenadesCoop` is the peer-side replay of the
host's proximity check: `connectionTCP` runs it when the host sends a
"checkForProximityGrenades" packet, i.e. after the HOST has already decided a
grenade fired. Its predicate used to read

    if (item->fuseProximityEvent() || 1 == 1)

so it was unconditionally true. The forced trigger is wanted for the grenade
branch (the peer must detonate whatever the host detonated, whatever its own
fuse bookkeeping says), but it also fell through to the ELSE branch, which
`_save->removeItem()`s the item. Result: on the peer machine, every non-grenade
item lying on the 3x3 of tiles around the unit was deleted - loose weapons,
clips, medi-kits, a squad's reserve equipment left on the Skyranger floor - none
of which the host removed. The vanilla twin `checkForProximityGrenades` only
ever removes an item whose own `fuseProximityEvent()` fired.

What this test asserts
----------------------
Ground items around the trigger unit fare IDENTICALLY on both machines: no item
instance that existed before the blast may disappear on one machine while
surviving on the other. Note the assertion is symmetry, not survival - the
detonation itself legitimately destroys some floor items (`TileEngine::explode`
removes a ground item whose armor the blast beats), and it does so on the host
too. Only a one-sided disappearance is a coop bug.

The litter deliberately includes UNPRIMED grenades: forcing the peer's grenade
branch (rather than only its removal branch) detonates spare grenades lying on
the Skyranger deck that the host never touched - the same divergence wearing a
different hat. A control item well outside the swept 3x3 pins the sweep as
positional rather than global.

Run:  python tools/coop_test/test_coop_proximity_item_sweep.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import test_shared_battle as B

PROXY = "STR_PROXIMITY_GRENADE"
# Floor litter on the swept tiles. STR_GRENADE is dropped UNPRIMED on purpose:
# the host leaves it alone, so a peer that force-detonates every grenade in the
# 3x3 diverges just as visibly as one that sweeps the non-grenades away.
LITTER = ["STR_PISTOL", "STR_GRENADE", "STR_MEDI_KIT", "STR_ELECTRO_FLARE"]


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def top(gc):
    return gc.cmd({"cmd": "get_state"})["states"][-1].split("::")[-1]


def census(gc):
    """{itemId: (type, ownerUnitId)} for every BattleItem instance."""
    return {i["id"]: (i["type"], i["owner"]) for i in gc.ok({"cmd": "battle_items"})["items"]}


def enter_battle(js):
    """Fly the shared craft to a terror site and take BOTH machines all the way
    to the tactical map with the coop turn initialised.

    (Same dance as test_coop_alien_launcher_item_loss.py: a NEW BATTLE > COOP
    skirmish never sets _battleInit, so nothing replicates there at all.)
    """
    host, client = js.host, js.client
    b0 = B._base0(host)
    blon, blat = b0["lon"], b0["lat"]
    cid = B._skyranger(host)["id"]
    roster = sorted(s["id"] for s in B._roster(host))
    squad = roster[:3]
    for sid in roster:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in squad:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
    for gc in (host, client):
        gc.wait_for("squad aboard",
                    lambda gc=gc: (sorted(s["id"] for s in B._roster(gc)
                                          if s["craftId"] == cid) == squad) or None,
                    timeout=45, interval=0.5)

    site_id = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                       "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                       "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    host.wait_for("site on host",
                  lambda: any(s["id"] == site_id for s in B._geo(host)["missionSites"]) or None,
                  timeout=30)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": f"site:{site_id}",
             "fuel": 999999, "lowFuel": False})

    def _landing_prompt():
        if B._has(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})   # not geo_run: it auto-declines
        return None

    host.wait_for("ConfirmLandingState on host", _landing_prompt, timeout=90, interval=0.5)
    host.ok({"cmd": "confirm_landing"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} entered the battle",
                    lambda gc=gc: battle(gc).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        gc.wait_for("briefing", lambda gc=gc: B._has(gc, "BriefingState") or None,
                    timeout=60, interval=0.5)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        gc.wait_for("pre-battle inventory",
                    lambda gc=gc: B._has(gc, "InventoryState") or None, timeout=60, interval=0.5)
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for _ in range(10):
        if all(top(gc) == "BattlescapeState" for gc in (host, client)):
            break
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(1.0)
    host.wait_for("the coop turn to initialise",
                  lambda: (battle(host).get("coopTurn") == 2) or None,
                  timeout=90, interval=1.0)
    time.sleep(2)


def drop(gc, x, y, z, item, prime=False):
    """Create one floor item on <x,y,z>; None when that tile does not exist."""
    r = gc.cmd({"cmd": "battle_drop", "x": x, "y": y, "z": z,
                "item": item, "prime": prime})
    if not r.get("ok"):
        return None
    return r["ids"][0]


def settle(host, client, seconds=8, stable_samples=4, max_wait=90):
    """Let the explosion resolve and every packet round-trip.

    Both censuses must hold still for several consecutive samples: the blast can
    kill units, and the death/corpse/drop sequence has pauses longer than one
    sample, so a two-sample check reads a mid-sequence lull as settled.
    """
    time.sleep(seconds)
    prev, same = None, 0
    deadline = time.time() + max_wait
    while time.time() < deadline:
        now = (census(host), census(client))
        same = same + 1 if now == prev else 0
        if same >= stable_samples:
            return
        prev = now
        time.sleep(1.0)


def run(ports, fails):
    js = shared_fixture.bring_up("prox", ports)
    host, client = js.host, js.client
    try:
        enter_battle(js)

        hb, cb = battle(host), battle(client)
        assert [u["id"] for u in hb["units"]] == [u["id"] for u in cb["units"]], \
            "the two machines do not share a unit list"
        unit = next(u for u in hb["units"] if u["faction"] == 0 and not u["isOut"])
        ux, uy, uz = unit["x"], unit["y"], unit["z"]
        print(f"       trigger unit {unit['id']} @({ux},{uy},{uz})")

        # Litter the swept 3x3 with non-grenade items and put ONE primed proximity
        # grenade on a neighbouring tile. Identical calls in an identical order on
        # both machines - nothing in the coop protocol replicates an item spawn, so
        # this is also what keeps the two item-id spaces aligned.
        near = [(-1, -1), (0, -1), (1, 0), (-1, 1)]
        litter, control, grenades = [], [], []
        for (dx, dy), itype in zip(near, LITTER):
            ids = [drop(gc, ux + dx, uy + dy, uz, itype) for gc in (host, client)]
            if ids[0] is None or ids[1] is None:
                continue      # off-map tile; the map is generated, not fixed
            assert ids[0] == ids[1], f"item-id spaces diverged while littering: {ids}"
            litter.append((ids[0], itype, (ux + dx, uy + dy)))
        assert len(litter) >= 2, "could not place floor litter around the unit"

        # A control item FAR outside the 3x3: it must survive under any hypothesis,
        # so it separates "the peer swept the tiles" from "the peer lost items".
        # +8: outside the swept 3x3 AND outside a proximity grenade's blast radius
        # (power 55 -> ~5 tiles), so nothing but a bug can touch it.
        cids = [drop(gc, ux + 8, uy, uz, "STR_PISTOL") for gc in (host, client)]
        if cids[0] is not None and cids[0] == cids[1]:
            control.append(cids[0])

        gid = [drop(gc, ux + 1, uy + 1, uz, PROXY, prime=True) for gc in (host, client)]
        if gid[0] is None:
            gid = [drop(gc, ux, uy, uz, PROXY, prime=True) for gc in (host, client)]
        assert gid[0] is not None and gid[0] == gid[1], \
            f"could not place a primed proximity grenade next to the unit: {gid}"
        grenades.append(gid[0])
        print(f"       litter {[(i, t) for i, t, _ in litter]}, control {control}, "
              f"primed {PROXY} = item {gid[0]}")

        pre_h, pre_c = census(host), census(client)
        assert set(pre_h) == set(pre_c), \
            f"censuses diverged BEFORE the blast: only-host {sorted(set(pre_h) - set(pre_c))}, " \
            f"only-client {sorted(set(pre_c) - set(pre_h))}"
        print(f"PASS pre-blast: {len(pre_h)} item instances, identical on both machines")

        # The real check UnitWalkBState runs after every step - including the
        # host-side "checkForProximityGrenades" packet the peer replays. Only the
        # host sends it (checkForProximityGrenades early-returns on a coop client).
        fired = host.ok({"cmd": "battle_prox", "unit": unit["id"]})
        print(f"       host proximity check -> change={fired['change']} "
              f"(2 = a grenade detonated)")
        if fired["change"] != 2:
            fails.append("the primed proximity grenade did not detonate on the host "
                         f"(change={fired['change']}) - the peer never got a packet, "
                         "so this run proves nothing")
            return

        settle(host, client)

        h, c = census(host), census(client)
        # Only PRE-EXISTING instances: the blast kills units, and the corpses/drops
        # it creates are their own (separately tested) replication question.
        # Symmetry, not survival, is the invariant - the detonation destroys some
        # ground items on BOTH machines, which is vanilla behaviour.
        gone_h = {i for i in pre_h if i not in h}
        gone_c = {i for i in pre_c if i not in c}
        one_sided = (gone_h ^ gone_c)
        for iid in sorted(one_sided):
            side = "client" if iid in gone_c else "host"
            print(f"  [DIVERGE] item {iid} {pre_h[iid][0]} was deleted on the {side} only")
        if one_sided:
            fails.append(f"{len(one_sided)} pre-existing item instance(s) were deleted on "
                         f"one machine but not the other")
        print(f"       blast destroyed {len(gone_h)} floor item(s) on the host, "
              f"{len(gone_c)} on the client")

        for iid, itype, pos in litter + [(i, "STR_PISTOL", "far") for i in control]:
            print(f"       {itype} {iid} on {pos}: host "
                  f"{'kept' if iid in h else 'gone'}, client "
                  f"{'kept' if iid in c else 'gone'}")
        # The control lies well outside the swept 3x3 AND outside the blast, so it
        # is the one item that must survive outright - on both machines.
        for iid in control:
            for tag, cen in (("host", h), ("client", c)):
                if iid not in cen:
                    fails.append(f"{tag}: the control item {iid} well outside the swept "
                                 f"3x3 disappeared")
        for iid in grenades:
            for tag, cen in (("host", h), ("client", c)):
                if iid in cen:
                    fails.append(f"{tag}: the primed {PROXY} (item {iid}) is still there - "
                                 f"it never detonated")

        if not fails:
            print(f"PASS the replayed detonation removed exactly the same item instances "
                  f"on both machines ({len(gone_h)} of {len(pre_h)})")
    except Exception as e:
        fails.append(str(e))
        print(f"[ERROR] {e}")
    finally:
        js.shutdown()


def main():
    fails = []
    run((48802, 48803, 48202), fails)
    print("\n==== proximity item sweep summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  a replayed proximity detonation removes only the grenade - the peer's "
          "floor items survive it exactly as the host's do")
    sys.exit(0)


if __name__ == "__main__":
    main()
