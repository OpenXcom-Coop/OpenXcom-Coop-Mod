"""Regression test: taking a guest soldier OFF a craft at the other player's
base must stick, in the single host-owned SEPARATE world.

Reported from a SEPARATE playtest: "when I unassign some soldiers from the
Skyranger in another player's base and then exit to the geoscape, when I come
back to the equip craft screen immediately after then they are re-assigned to
the skyranger again".

Each direction: the visitor transfers an equipped soldier of its own to the
partner's base, then at that base

  seat:   seats it on the partner's Skyranger -> both machines show it aboard;
  unseat: takes it off again and closes the Soldiers screen -> both machines show
     it off the craft (the host world holds the unseat);
  reopen: goes back to the geoscape, then opens that base's Soldiers screen again
     -> it is still off the craft on both machines.

Run:  python tools/coop_test/test_coop_guest_craft_seat.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_coop_transferred_equipment as T

GEAR = [("STR_RIFLE", "right", 1), ("STR_PISTOL", "left", 1), ("STR_SMALL_ROCKET", "backpack", 2)]


def cycle_soldiers_screen(gc, base):
    gc.ok({"cmd": "open_soldiers", "base": base})
    gc.wait_for("soldiers screen", lambda: T._has_state(gc, "SoldiersState") or None, timeout=30)
    gc.ok({"cmd": "soldiers_ok"})
    gc.wait_for("soldiers screen closed",
                lambda: (not T._has_state(gc, "SoldiersState")) or None, timeout=30)


def seats(host, client, base, sid, cid):
    return {gc.name: ((T.soldier_at(gc, base, sid) or {}).get("craft"), T.crew(gc, base, cid))
            for gc in (host, client)}


def run(visitor, host, client, seat, home, peer, name, label):
    print(f"--- {label} ---")
    sid = T.free_soldier(visitor, host, client, home, seat)
    T.rename(visitor, host, client, home, sid, name)
    for item, slot, qty in GEAR:
        T.give_layout(host, client, home, name, item, slot, qty)
    T.send_soldier(visitor, host, client, sid, home, peer)
    T.arrive(host, client, peer, sid)
    cid = T.craft_id(host, peer)
    crew0 = T.crew(host, peer, cid)

    T.seat(visitor, host, client, peer, sid, cid, True)
    cycle_soldiers_screen(visitor, peer)
    s = seats(host, client, peer, sid, cid)
    assert all(v == (cid, crew0 + 1) for v in s.values()), (
        f"{label}: the seat did not take on both machines: {s}")
    print(f"PASS {label} seat: seated on the partner's Skyranger {cid} on both machines {s}")

    T.seat(visitor, host, client, peer, sid, cid, False)
    cycle_soldiers_screen(visitor, peer)
    s = seats(host, client, peer, sid, cid)
    assert all(v == (-1, crew0) for v in s.values()), (
        f"{label}: the unseat did not take on both machines: {s}")
    print(f"PASS {label} unseat: taken off the craft on both machines {s}")

    T.settle(visitor)
    cycle_soldiers_screen(visitor, peer)
    s = seats(host, client, peer, sid, cid)
    assert all(v == (-1, crew0) for v in s.values()), (
        f"{label}: RE-ASSIGNED after leaving and reopening the base: {s}")
    print(f"PASS {label} reopen: still off the craft after leaving and reopening {s}")


def main():
    js = T.bring_up("xeqseat")
    host, client = js.host, js.client
    try:
        T.set_alt(host, client, True)
        run(host, host, client, 0, T.HB, T.CB, "Zzz Hostguest", "host visiting the client's base")
        run(client, host, client, 1, T.CB, T.HB, "Zzz Clientguest", "client visiting the host's base")
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
