"""Regression test for issue #33 in the single host-owned SEPARATE world (PR #213):

  "Units at a friend's base can see equipment that is assigned to friend's
   soldiers (unavailable, but visible)."

A soldier's equipment layout does not decrement base storage - the items stay
in storage and the layout is a re-equip blueprint - so the base inventory's
ground pane leaks every item reserved by a soldier that is not deployed there.

Setup: each player sends one of its soldiers to the other player's base. At
each base the stock of STR_PISTOL_CLIP (8) is reserved exactly: 7 on the base
owner's soldiers and 1 on the guest. Whoever opens that base's inventory then
deploys only its own soldiers, which carry their own clips, so the ground must
hold none:

  case1 the host opens ClientBase (as a visitor, through its guest there)
  case2 the client opens HostBase (as a visitor)
  case3 the client opens its own ClientBase, which houses the host's guest
  case4 the host opens its own HostBase, which houses the client's guest

Each case asserts: (a) none of the other player's soldiers is deployed on the
viewer's inventory screen (they are not the viewer's to equip), and (b) no
clip reserved by them shows on the ground pane.

Replaced rows (two-world premise gone):
  - cases 1/2 "visiting a peer base hides the peer's reserved items from the
    visited storage" (insideCoopBase, base_report coop) -> the visitor opens
    the partner's real base inventory through its own soldier there.
  - cases 3/4 "a stripped guest (set_coop_base) at the own base" -> a real
    guest of the other player, sent by a host-world transfer.

Run:  python tools/coop_test/test_coop_base_equip_visibility.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_coop_transferred_equipment as T

CLIP = "STR_PISTOL_CLIP"


def reserve(host, client, base, owner_names, guest_name):
    """7 clips on the owner's soldiers, 1 on the guest: the whole stock."""
    stock = T.stored(host, base, CLIP)
    assert stock == len(owner_names) + 1, f"{base}: premise {CLIP} stock {stock}"
    for name in owner_names + [guest_name]:
        T.give_layout(host, client, base, name, CLIP, "belt")
    for gc in (host, client):
        r = T.report(gc, base)
        assert r["reserved"].get(CLIP, 0) == stock, f"{gc.name}: {base} reserved {r['reserved']}"


def check_case(viewer, viewer_seat, base, label):
    r = T.report(viewer, base)
    others = {s["id"] for s in r["soldiers"] if s["owner"] != viewer_seat}
    g = T.base_equip_screen(viewer, base)
    shown = [u["id"] for u in g["soldiers"]]
    leaked = g["items"].get(CLIP, 0)
    exposed = sorted(set(shown) & others)
    assert not exposed and leaked == 0, (
        f"{label}: the other player's soldiers {exposed} are on the viewer's inventory "
        f"screen and/or {leaked} of their reserved {CLIP} lie free on the ground pane")
    print(f"PASS {label}: only the viewer's soldiers shown ({len(shown)}), "
          f"no reserved {CLIP} on the ground")


def main():
    js = T.bring_up("xeqvis")
    host, client = js.host, js.client
    try:
        hguest = T.free_soldier(host, host, client, T.HB, 0)
        cguest = T.free_soldier(client, host, client, T.CB, 1)
        T.rename(host, host, client, T.HB, hguest, "Zzz Hguest")
        T.rename(client, host, client, T.CB, cguest, "Zzz Cguest")
        T.send_soldier(host, host, client, hguest, T.HB, T.CB)
        T.send_soldier(client, host, client, cguest, T.CB, T.HB)
        T.arrive(host, client, T.CB, hguest)
        T.arrive(host, client, T.HB, cguest)

        for base, seat, guest in ((T.HB, 0, "Zzz Cguest"), (T.CB, 1, "Zzz Hguest")):
            owners = [s["name"] for s in T.report(host, base)["soldiers"]
                      if s["owner"] == seat][:7]
            reserve(host, client, base, owners, guest)
        print(f"reserved the whole {CLIP} stock at both bases (7 owner soldiers + 1 guest)")

        check_case(host, 0, T.CB, "case1 host@client-base")
        check_case(client, 1, T.HB, "case2 client@host-base")
        check_case(client, 1, T.CB, "case3 client-own-base with the host's guest")
        check_case(host, 0, T.HB, "case4 host-own-base with the client's guest")
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
