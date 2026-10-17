#!/usr/bin/env python3
"""Classic co-op: a lethal early auto-shot round must collapse before later rounds.

The client parks the killing ExplosionBState with `_hasHitUnit == 1`.  A classic
`unit_death` packet must pass the receive-order gate, queue UnitDieBState directly
after that explosion, and release the explosion immediately.  The queued collapse
then runs before ProjectileFlyBState may create the remaining round(s).  The final
`after_unit_death` state must not overtake that display sequence.

This is a red/green regression test. On the broken baseline, the opener-order
barrier parks classic `unit_death` behind `hit_unit`, while subject-less
`hasHitUnit` overtakes both; the next client round therefore starts before a
UnitDieBState was even queued. The test samples the client rapidly and proves
the required ordering with two independent observations: a real intermediate
collapse frame was displayed, and ammunition still remained to be consumed
when that collapse began. The broken baseline must fail; the corrected Classic
ordering must pass the same assertions.

Run:  python tools/coop_test/test_classic_autoshot_death_pacing.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW

PORT = "48962"
STATUS_COLLAPSING = 5


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def unit(gc, uid):
    return next((u for u in battle(gc).get("units", []) if u["id"] == uid), None)


def ammo_qty(gc, ammo_id):
    items = gc.ok({"cmd": "battle_items"})["items"]
    item = next((i for i in items if i["id"] == ammo_id), None)
    return None if item is None else item["qty"]


def main():
    opts = {"battleXcomSpeed": 1, "battleAlienSpeed": 1}
    host = client = None
    fail = None
    try:
        host = GameClient("host", 48960,
                          make_user_dir("classic_autoshot_host", options=opts))
        client = GameClient("client", 48961,
                            make_user_dir("classic_autoshot_client", options=opts))
        for gc in (host, client):
            TW.write_battle_fixture(gc.user_dir)
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        TW.PORT = PORT
        TW.bring_up_battle(host, client, seed=771931)

        for gc, tag in ((host, "host"), (client, "client")):
            bs = battle(gc)
            assert bs.get("parallelActive") is False, \
                f"{tag}: fixture is not Classic Turns: {bs}"
            assert all("fallPhase" in u for u in bs["units"]), \
                f"{tag}: battle_state has no fallPhase; executable predates this test"

        driver, watcher, driver_tag, _, db = TW.pick_driver(host, client)
        shooters = [u for u in db["units"] if u.get("faction") == 0
                    and u.get("selectable") and not u.get("isOut")]
        victims = [u for u in db["units"] if u.get("faction") == 1
                   and not u.get("isOut")]
        assert shooters and victims, "fixture has no controllable shooter or live hostile"
        shooter, victim = shooters[0], victims[0]

        # Put the target next to the shooter on both copies. At this range firing
        # 1000 makes the first round deterministic while still exercising the real
        # BA_AUTOSHOT/ExplosionBState/unit_death path. A rifle with a finite clip is
        # used so the sample can prove whether another round was consumed yet;
        # laser weapons report the permanent sentinel quantity 255.
        placed = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (-1, -1), (1, -1), (-1, 1)):
            want = (shooter["x"] + dx, shooter["y"] + dy, shooter["z"])
            results = [gc.cmd({"cmd": "battle_teleport", "unit": victim["id"],
                               "x": want[0], "y": want[1], "z": want[2]})
                       for gc in (host, client)]
            if all(r.get("moved") for r in results):
                placed = want
                break
        assert placed is not None, "no common adjacent tile for the deterministic shot"

        armed = []
        for gc in (host, client):
            gc.ok({"cmd": "battle_action", "action": "set_stat",
                   "unit": shooter["id"], "stat": "firing", "value": 1000,
                   "refill": True})
            gc.ok({"cmd": "battle_action", "action": "set_stat",
                   "unit": victim["id"], "health": 1})
            armed.append(gc.ok({"cmd": "battle_give", "unit": shooter["id"],
                                "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                                "slot": "right",
                                "clear_hands": True}))
        assert armed[0]["weaponId"] == armed[1]["weaponId"], \
            f"weapon ids differ: {armed}"
        weapon_id = armed[0]["weaponId"]
        assert armed[0]["ammoId"] >= 0 and armed[0]["ammoId"] == armed[1]["ammoId"], \
            f"loaded rifle clip ids differ or are missing: {armed}"
        ammo_id = armed[0]["ammoId"]
        initial_qty = ammo_qty(client, ammo_id)

        shot = driver.ok({"cmd": "battle_fire", "unit": shooter["id"],
                          "target": victim["id"], "mode": "auto",
                          "weapon_id": weapon_id, "tu": 200})
        assert shot.get("ammoId", -1) == ammo_id, \
            f"rifle did not fire the staged clip {ammo_id}: {shot}"

        frames = []
        first_collapse_qty = None
        deadline = time.time() + 45
        saw_out = False
        stable = 0
        previous_final = None
        while time.time() < deadline:
            vu = unit(client, victim["id"])
            assert vu is not None, "victim disappeared from client unit list"
            qty = ammo_qty(client, ammo_id)
            snap = (vu["status"], vu["fallPhase"], qty)
            if not frames or frames[-1] != snap:
                frames.append(snap)
            if vu["status"] == STATUS_COLLAPSING and vu["fallPhase"] > 0:
                if first_collapse_qty is None:
                    first_collapse_qty = qty
            saw_out = saw_out or vu.get("isOut", False)
            current_final = (vu["status"], vu["fallPhase"], qty)
            final_pose = saw_out and vu["status"] != STATUS_COLLAPSING
            stable = stable + 1 if final_pose and current_final == previous_final else 0
            previous_final = current_final
            if stable >= 20:
                break
            time.sleep(0.02)

        final_qty = ammo_qty(client, ammo_id)
        assert saw_out, f"auto shot did not kill the staged 1-HP victim; frames={frames}"
        assert first_collapse_qty is not None, \
            f"client displayed no intermediate UnitDieBState collapse frame: {frames}"
        assert final_qty is not None and first_collapse_qty > final_qty, (
            "client consumed every remaining auto-shot round before the collapse "
            f"began (collapse qty={first_collapse_qty}, final qty={final_qty}, "
            f"initial qty={initial_qty}, frames={frames})")
        assert stable >= 20, "auto-shot/death chain did not settle"
        print("PASS: Classic client collapsed the victim before consuming the "
              f"remaining auto-shot rounds (ammo {initial_qty} -> "
              f"{first_collapse_qty} during collapse -> {final_qty}).")
    except Exception as exc:
        fail = exc
        print(f"[FAIL] {exc}")
    finally:
        if host is not None:
            host.shutdown()
        if client is not None:
            client.shutdown()
    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
