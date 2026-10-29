"""Regression test: the base that HOUSES a soldier is the base that pays for it,
in the single host-owned SEPARATE world.

A transfer to the other player's base keeps the soldier's owner (a gift changes
it). The soldier must leave the sender's living quarters and occupy the
receiver's from the moment it is sent (personnel en route count), on BOTH
machines, and the world total is conserved. Three soldiers move each way, not
one: a single transfer would not show a roster pruned between moves.

  host -> client: 3 of the host's soldiers move to ClientBase; HostBase
     quarters drop by 3 and ClientBase's rise by 3 on both machines.
  visitor's view: ClientBase seen from the host's machine counts the
     host's soldiers housed there, the same number the client sees.
  client -> host and the client's view of HostBase, the same way.

Run:  python tools/coop_test/test_coop_quarters_accounting.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_coop_transferred_equipment as T


def quarters(gc, base):
    return T.report(gc, base)["usedQuarters"]


def run_direction(sender, host, client, seat, send_base, recv_base, label, moves=3):
    s0 = {gc.name: quarters(gc, send_base) for gc in (host, client)}
    r0 = {gc.name: quarters(gc, recv_base) for gc in (host, client)}
    print(f"{label}: before - {send_base}={s0} {recv_base}={r0}")
    moved = []
    for n in range(1, moves + 1):
        sid = T.free_soldier(sender, host, client, send_base, seat, exclude=moved)
        T.send_soldier(sender, host, client, sid, send_base, recv_base)
        moved.append(sid)
        for gc in (host, client):
            gc.wait_for(f"{label}: {gc.name} sees {n} soldier(s) moved",
                        lambda gc=gc, n=n: (quarters(gc, send_base) == s0[gc.name] - n
                                            and quarters(gc, recv_base) == r0[gc.name] + n)
                        or None, timeout=30, interval=0.3)
        print(f"{label}: after {n} transfer(s) - {send_base}={quarters(host, send_base)}, "
              f"{recv_base}={quarters(host, recv_base)} (both machines agree)")
    for sid in moved:
        T.arrive(host, client, recv_base, sid)
    for gc in (host, client):
        total = quarters(gc, send_base) + quarters(gc, recv_base)
        assert total == s0[gc.name] + r0[gc.name], (
            f"{label}: {gc.name}: living quarters not conserved - "
            f"{s0[gc.name]}+{r0[gc.name]} -> {total}")
        assert quarters(gc, recv_base) == r0[gc.name] + moves, (
            f"{label}: {gc.name}: {recv_base} lost guests on arrival: "
            f"{r0[gc.name]} -> {quarters(gc, recv_base)}")
    print(f"PASS {label}: {moves} soldier(s) moved from the sender's quarters to the "
          f"receiver's on both machines, world total conserved")
    return moved


def visitor_view(visitor, owner, base, guests, label):
    v, o = quarters(visitor, base), quarters(owner, base)
    housed = [s for s in T.report(visitor, base)["soldiers"] if s["id"] in guests]
    assert len(housed) == len(guests), f"{label}: guests missing at {base}: {housed}"
    assert v == o and v >= len(guests), (
        f"{label}: {base} used quarters - visitor sees {v}, owner sees {o}, "
        f"{len(guests)} of the visitor's soldiers live there")
    print(f"PASS {label}: {base} counts its {len(guests)} guest(s) on both machines "
          f"(usedQuarters={v})")


def main():
    js = T.bring_up("xeqquar")
    host, client = js.host, js.client
    try:
        to_client = run_direction(host, host, client, 0, T.HB, T.CB, "host -> client")
        visitor_view(host, client, T.CB, to_client, "host's view of ClientBase")
        to_host = run_direction(client, host, client, 1, T.CB, T.HB, "client -> host")
        visitor_view(client, host, T.HB, to_host, "client's view of HostBase")
        print("TEST PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
