"""SHARED: sorting the Soldiers screen and soldier transformations (PR #213).

main sorts the roster and runs a soldier transformation on the local machine
only, so the two machines' rosters drift apart. Both go through the host now:

  S1 sort       the client sorts its own soldiers by name -> both machines
                hold the same order; picking the original order restores it
  S2 transform  the client transforms its own soldier -> the host world has
                the result and the shared funds pay once
  S3 transform  the host transforms its own soldier -> the client's replica
                shows it

Exit 0 = every row passed. Any other rc is a failure.
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

TRANSFORM = "STR_COOP_TEST_TRANSFORM_PAID"
COST = 20000
FIRING = 7

MOD_NAME = "coop_shared_transform"
METADATA = """\
name: "Coop shared transformation test"
version: 1.0
description: "Test-only: a paid soldier transformation open to every live soldier."
author: coop harness

master: xcom1
"""
RULESET = f"""\
soldierTransformation:
  - name: {TRANSFORM}
    allowsLiveSoldiers: true
    allowsWoundedSoldiers: true
    keepSoldierArmor: true
    allowedSoldierTypes:
      - STR_SOLDIER
    cost: {COST}
    flatOverallStatChange:
      firing: {FIRING}
"""

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


def make_mod(root):
    mod = os.path.join(root, MOD_NAME)
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "transform.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


def roster(gc, base):
    bases = gc.ok({"cmd": "get_soldiers"})["bases"]
    return next(b["soldiers"] for b in bases if b["name"] == base)


def ids(gc, base, owner=None):
    return [s["id"] for s in roster(gc, base) if owner is None or s["owner"] == owner]


def names(gc, base, owner):
    return [s["name"] for s in roster(gc, base) if s["owner"] == owner]


def firing(gc, base, sid):
    return next((s["firing"] for s in roster(gc, base) if s["id"] == sid), None)


def funds(gc):
    return gc.ok({"cmd": "geo_state"})["funds"]


def repairs(gc):
    """World repairs this replica asked for since the last reset: a change that
    reached it only through a checksum resync did not travel as a command."""
    return gc.ok({"cmd": "shared_resync_stats"})["requests"]


def own_base(gc, owner):
    """A base holding at least three of <owner>'s soldiers."""
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if sum(1 for s in b["soldiers"] if s["owner"] == owner) >= 3:
            return b["name"]
    return None


def row_sort(host, client, base):
    own = ids(client, base, 1)
    renamed = ["Coop Zulu", "Coop Mike", "Coop Alpha"]
    for sid, name in zip(own, renamed):
        client.ok({"cmd": "soldier_rename", "soldierId": sid, "name": name})
    assert poll(lambda: all(n in names(gc, base, 1) for gc in (host, client)
                            for n in renamed) or None), \
        ("premise: renames landed", names(host, base, 1))
    before = ids(host, base, 1)
    assert before == ids(client, base, 1), (before, ids(client, base, 1))
    client.ok({"cmd": "shared_reset_resync_stats"})
    client.ok({"cmd": "open_soldiers", "base": base})
    client.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 2})

    def sorted_on(gc):
        return [n for n in names(gc, base, 1) if n in renamed] == sorted(renamed)
    got = poll(lambda: (sorted_on(host) and ids(host, base) == ids(client, base)) or None)
    check("S1 sort: sorting by name reorders both machines the same way",
          bool(got) and ids(host, base, 1) != before,
          f"before={before} host={names(host, base, 1)} client={names(client, base, 1)}")
    client.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 0})
    got = poll(lambda: (ids(host, base, 1) == before and ids(client, base, 1) == before) or None)
    client.ok({"cmd": "soldiers_ok"})
    check("S1 sort: the original order comes back on both machines",
          bool(got), f"before={before} host={ids(host, base, 1)} client={ids(client, base, 1)}")
    check("S1 sort: both machines hold the same full roster order, with no world repair",
          ids(host, base) == ids(client, base) and repairs(client) == 0,
          f"host={ids(host, base)} client={ids(client, base)} repairs={repairs(client)}")


def row_transform(host, client, gc, owner, row):
    base = own_base(host, owner)
    sid = ids(host, base, owner)[0]
    f0 = firing(host, base, sid)
    assert f0 == firing(client, base, sid), (f0, firing(client, base, sid))
    funds0 = funds(host)
    assert funds0 == funds(client), (funds0, funds(client))
    client.ok({"cmd": "shared_reset_resync_stats"})
    gc.ok({"cmd": "soldier_transform", "base": base, "soldierId": sid, "rule": TRANSFORM})
    want = f0 + FIRING
    landed = poll(lambda: (firing(host, base, sid) == want
                           and firing(client, base, sid) == want) or None)
    check(f"{row} transform: {gc.name}'s transformation reaches both machines, with no world repair",
          bool(landed) and repairs(client) == 0, f"want={want} host={firing(host, base, sid)} "
          f"client={firing(client, base, sid)} repairs={repairs(client)}")
    paid = poll(lambda: (funds(host) == funds0 - COST and funds(client) == funds0 - COST) or None,
                timeout=10)
    check(f"{row} transform: the shared funds pay the cost once, the same on both machines",
          bool(paid), f"funds0={funds0} host={funds(host)} client={funds(client)}")


def main():
    tmp = tempfile.mkdtemp(prefix="coop_shared_transform_")
    try:
        mod = make_mod(tmp)
        js = shared_fixture.bring_up("jsorttr", (49774, 49775, 49074), mods=[mod])
        host, client = js.host, js.client
        try:
            base = own_base(client, 1)
            assert base, ("premise: a base with three client soldiers",
                          client.ok({"cmd": "get_soldiers"})["bases"])
            row_sort(host, client, base)
            row_transform(host, client, client, 1, "S2")
            row_transform(host, client, host, 0, "S3")
        finally:
            js.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print(f"FAIL {len(failures)} row(s): {failures}")
        sys.exit(3)
    print("PASS SHARED soldier sort and transformation")


if __name__ == "__main__":
    main()
