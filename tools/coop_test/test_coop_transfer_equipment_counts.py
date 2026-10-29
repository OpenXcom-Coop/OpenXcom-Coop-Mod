"""Validates that a soldier's equipped items move with it when it is transferred
to the other player's base, driven by the "Alternate craft equipment
management" option, in the single host-owned SEPARATE world (PR #213):

  C1 ON  (the host sends its soldier to ClientBase): the gear leaves HostBase's
     stores when the soldier is sent, travels on the same transfer as the
     soldier, and lands in ClientBase's stores when the soldier arrives; the
     world total of each item is unchanged. Checked on both machines.
  C2 OFF (the client sends its soldier to HostBase): no item moves - neither
     base's stores change and nothing but the soldier is en route.

Several distinct items are equipped (a rocket in one hand, a pistol in the
other) so multi-item transfer is covered too.

Replaced rows (two-world premise gone):
  - "ON: the gear arrives IMMEDIATELY (a 0-hour transfer matching the instant
    soldier move; the paused clock never moves)" -> a transfer is no longer
    instant for the soldier either: it is a timed host-world transfer. The
    single-world equivalent is C1: the gear rides the soldier's own transfer
    and arrives with it, never before or after.

Run:  python tools/coop_test/test_coop_transfer_equipment_counts.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_coop_transferred_equipment as T

# item -> inventory slot; both are present in a fresh starting base.
GEAR = {"STR_SMALL_ROCKET": "left", "STR_PISTOL": "right"}


def snapshot(gc):
    return {b: {i: T.stored(gc, b, i) for i in GEAR} for b in (T.HB, T.CB)}


def gear_en_route(gc, base):
    return {i: T.incoming(gc, base)["items"].get(i, 0) for i in GEAR}


def run(sender, host, client, seat, src, dst, alt_on, name):
    label = "ON" if alt_on else "OFF"
    T.set_alt(host, client, alt_on)
    sid = T.free_soldier(sender, host, client, src, seat)
    T.rename(sender, host, client, src, sid, name)
    for item, slot in GEAR.items():
        T.give_layout(host, client, src, name, item, slot)
    s0 = {gc.name: snapshot(gc) for gc in (host, client)}
    for gc in (host, client):
        for i in GEAR:
            assert s0[gc.name][src][i] >= 1, f"{src} needs a {i} (has {s0[gc.name][src][i]})"

    T.send_soldier(sender, host, client, sid, src, dst)
    for gc in (host, client):
        s = snapshot(gc)
        moving = gear_en_route(gc, dst)
        for i in GEAR:
            want = 1 if alt_on else 0
            assert s[src][i] == s0[gc.name][src][i] - want, (
                f"{label}: {gc.name}: {src} {i} {s0[gc.name][src][i]} -> {s[src][i]}, expected -{want}")
            assert moving[i] == want, (
                f"{label}: {gc.name}: {i} en route to {dst} = {moving[i]}, expected {want} "
                f"(on the soldier's own transfer)")
            assert s[dst][i] == s0[gc.name][dst][i], (
                f"{label}: {gc.name}: {dst} {i} changed before the soldier arrived")
    T.arrive(host, client, dst, sid)
    for gc in (host, client):
        s = snapshot(gc)
        assert gear_en_route(gc, dst) == {i: 0 for i in GEAR}, f"{label}: {gc.name}: gear still en route"
        for i in GEAR:
            want = 1 if alt_on else 0
            assert s[dst][i] == s0[gc.name][dst][i] + want, (
                f"{label}: {gc.name}: {dst} {i} {s0[gc.name][dst][i]} -> {s[dst][i]}, expected +{want}")
            assert s[src][i] + s[dst][i] == s0[gc.name][src][i] + s0[gc.name][dst][i], (
                f"{label}: {gc.name}: world {i} total changed")
    if alt_on:
        print(f"PASS C1 ON: {list(GEAR)} each left {src} with the soldier, travelled on its "
              f"transfer and reached {dst} with it; world conserved on both machines")
    else:
        print(f"PASS C2 OFF: nothing moved ({src} and {dst} stores unchanged for "
              f"{list(GEAR)}, only the soldier en route) on both machines")


def main():
    js = T.bring_up("xeqcount")
    host, client = js.host, js.client
    try:
        run(host, host, client, 0, T.HB, T.CB, True, "Zzz On")
        run(client, host, client, 1, T.CB, T.HB, False, "Zzz Off")
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
