"""Regression test: the "Alternate craft equipment management" option
(Options::oxceAlternateCraftEquipmentManagement) drives whether a soldier's
equipment travels with it when it is transferred to the other player's base,
in the single host-owned SEPARATE world (PR #213).

  E1 ON  (the host sends its soldier to ClientBase): the layout travels with
     the soldier; it is still equipped at the partner's base, on both machines.
  E2 OFF (the client sends its soldier to HostBase): the soldier's gear does
     not travel, so it arrives at the partner's base with an EMPTY layout (it
     does not silently re-equip from the partner's stores), on both machines.

This test checks the soldier's layout only. The matching item-count movement
is covered by test_coop_transfer_equipment_counts.py.

Replaced rows (two-world premise gone):
  - "the host visits the peer base and reads the guest there" (insideCoopBase)
    -> both machines read the soldier at the partner's real base.
  - one fresh session per mode (one transferable soldier per base) -> one
    session: each player sends its own base-resident soldier.

Run:  python tools/coop_test/test_coop_transfer_equipment_option.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_coop_transferred_equipment as T

ROCKET = "STR_SMALL_ROCKET"


def run(sender, host, client, seat, src, dst, alt_on, name):
    T.set_alt(host, client, alt_on)
    sid = T.free_soldier(sender, host, client, src, seat)
    T.rename(sender, host, client, src, sid, name)
    T.give_layout(host, client, src, name, ROCKET, "left")
    T.send_soldier(sender, host, client, sid, src, dst)
    T.arrive(host, client, dst, sid)
    return {gc.name: T.soldier_at(gc, dst, sid)["layout"] for gc in (host, client)}


def main():
    js = T.bring_up("xeqopt")
    host, client = js.host, js.client
    try:
        on = run(host, host, client, 0, T.HB, T.CB, True, "Zzz On")
        assert all(ROCKET in lo for lo in on.values()), (
            f"E1 ON: expected the soldier to keep its {ROCKET} at the partner's base, got {on}")
        print(f"PASS E1 ON: the soldier kept its loadout at the partner's base {on}")

        off = run(client, host, client, 1, T.CB, T.HB, False, "Zzz Off")
        assert all(lo == [] for lo in off.values()), (
            f"E2 OFF: expected the soldier stripped (empty layout) at the partner's base, got {off}")
        print(f"PASS E2 OFF: the soldier arrived stripped at the partner's base {off}")
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
