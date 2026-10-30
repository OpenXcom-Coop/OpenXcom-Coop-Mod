"""SHARED: moving a base in the mini strip keeps one base order.

A SHARED player can move the selected base left in the mini base strip.
Commands name a base by its place in the base list, so the move goes through
the host and both machines apply it in the same order:

  - the client moves the last base left -> both machines show the new order
  - a buy the client sends right after the move, naming the base that was in
     front of it, lands in that base on both machines

Exit 0 = every row passed. Any other rc is a failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

RIFLE = "STR_RIFLE"

failures = []


def check(row, ok, detail):
    print(("PASS " if ok else "[FAIL] ") + row + ("" if ok else f": {detail}"))
    if not ok:
        failures.append(row)


def poll(fn, timeout=20.0, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(interval)
    return None


def base_order(gc):
    return [b["name"] for b in gc.ok({"cmd": "geo_state"})["bases"]]


def incoming(gc, base):
    return gc.ok({"cmd": "incoming_transfers", "base": base})["items"].get(RIFLE, 0)


def main():
    js = shared_fixture.bring_up("jbaseorder", (49766, 49767, 49066))
    host, client = js.host, js.client
    try:
        for gc in (host, client):
            gc.ok({"cmd": "add_base", "name": "SharedSecond", "lon": 0.1, "lat": -0.9,
                   "coopbaseid": 72000})
        start = base_order(host)
        assert start == base_order(client), (start, base_order(client))
        assert len(start) >= 2 and start[-1] == "SharedSecond", start
        target = start[-2]
        before = {gc.name: incoming(gc, target) for gc in (host, client)}

        client.ok({"cmd": "open_screen", "screen": "basescape", "base": "SharedSecond"})
        # One write: the client runs both in the same frame, so the buy names
        # <target> by its index from before the move, which then means SharedSecond.
        resps = client.cmd_together(
            {"cmd": "basescape_move_base_left", "base": "SharedSecond"},
            {"cmd": "buy", "item": RIFLE, "count": 1, "base": target})
        assert all(r.get("ok") for r in resps), resps
        client.ok({"cmd": "leave_base"})

        want = start[:-2] + ["SharedSecond", target]
        moved = poll(lambda: (base_order(host) == want and base_order(client) == want) or None)
        check("the moved base is one place left on both machines", bool(moved),
              f"want={want} host={base_order(host)} client={base_order(client)}")
        landed = poll(lambda: all(incoming(gc, target) == before[gc.name] + 1
                                  for gc in (host, client)) or None)
        check(f"the buy sent right after the move lands in {target} on both machines",
              bool(landed) and incoming(host, "SharedSecond") == 0
              and incoming(client, "SharedSecond") == 0,
              {f"{gc.name}:{b}": incoming(gc, b) for gc in (host, client)
               for b in (target, "SharedSecond")})
    finally:
        js.shutdown()
    if failures:
        print(f"FAIL {len(failures)} row(s): {failures}")
        sys.exit(3)
    print("PASS SHARED base order")


if __name__ == "__main__":
    main()
