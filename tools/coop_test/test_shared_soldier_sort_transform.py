"""SHARED: sorting the Soldiers screen and soldier transformations.

A roster sort or a soldier transformation that runs on the local machine only
lets the two machines' rosters drift apart. Both go through the host:

  sort              the client sorts its own soldiers by name -> both machines
                    hold the same order; picking the original order restores it
  client transform  the client transforms its own soldier -> the host world has
                    the result and the shared funds pay once
  host transform    the host transforms its own soldier -> the client's replica
                    shows it
  training sort     a name sort (and the original order) on the martial / psi
                    training screen leaves the shared order alone: the screen
                    keeps listing the client's own soldiers in roster order and
                    both machines keep the same roster order
  craft armor       the crew armor screen's name sort and original order reorder
                    both machines the same way
  craft crew        the host sorts its soldiers while the client's craft crew
                    screen is open; the client's original order then keeps both
                    machines the same
  training          the client's martial / psi training screen puts its own
                    soldier into training and out again through the host: both
                    machines end with the same flags. Each player trains only
                    their own soldiers: a host soldier is not on the client's
                    screen and its training stays off on both machines

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
description: "Test-only: a paid soldier transformation open to every live soldier, and a gym and psi lab in every access lift."
author: coop harness

master: xcom1
"""
RULESET = f"""\
facilities:
  - type: STR_ACCESS_LIFT
    trainingRooms: 10
    psiLabs: 10
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
    check("sort: sorting by name reorders both machines the same way",
          bool(got) and ids(host, base, 1) != before,
          f"before={before} host={names(host, base, 1)} client={names(client, base, 1)}")
    client.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 0})
    got = poll(lambda: (ids(host, base, 1) == before and ids(client, base, 1) == before) or None)
    client.ok({"cmd": "soldiers_ok"})
    check("sort: the original order comes back on both machines",
          bool(got), f"before={before} host={ids(host, base, 1)} client={ids(client, base, 1)}")
    check("sort: both machines hold the same full roster order, with no world repair",
          ids(host, base) == ids(client, base) and repairs(client) == 0,
          f"host={ids(host, base)} client={ids(client, base)} repairs={repairs(client)}")


RENAMED = ["Coop Zulu", "Coop Mike", "Coop Alpha"]


def settled_same(host, client, base, seconds=2.0):
    """Both machines' full roster order after a short settle (a host-routed
    order lands well inside it)."""
    time.sleep(seconds)
    return ids(host, base) == ids(client, base)


def shown_names(gc, base, shown):
    by_id = {s["id"]: s["name"] for s in roster(gc, base)}
    return [by_id.get(i) for i in shown]


def row_training_sort(host, client, base, screen, row):
    """A name sort on a training screen leaves the shared order alone: the
    screen keeps the client's own soldiers in roster order, and both machines
    keep the same roster order."""
    full = ids(host, base)
    assert full == ids(client, base), (full, ids(client, base))
    client.ok({"cmd": "open_screen", "screen": screen, "base": base})
    r = client.ok({"cmd": "roster_screen", "action": "sort", "sort": 2})
    names_shown = [n for n in shown_names(client, base, r["displayed"]) if n in RENAMED]
    same = settled_same(host, client, base)
    check(f"{row} {screen}: a name sort leaves both machines with the same roster order",
          same, f"host={ids(host, base)} client={ids(client, base)}")
    own = ids(client, base, 1)
    check(f"{row} {screen}: the screen keeps the client's own soldiers in roster order",
          r["displayed"] == own and ids(host, base) == full,
          f"shown={r['displayed']} names={names_shown} own={own} roster={full} host={ids(host, base)}")
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    same = settled_same(host, client, base)
    client.ok({"cmd": "close_screens"})
    check(f"{row} {screen}: the original order leaves both machines the same",
          same, f"host={ids(host, base)} client={ids(client, base)}")


def row_training(host, client, screen, key, row):
    """The client's training screen changes its own soldier's training flag
    through the host; a host soldier is not on the client's screen (each
    player trains only their own soldiers) and its flag stays off."""
    def flag(gc, base, sid):
        return next((s[key] for s in roster(gc, base) if s["id"] == sid), None)

    for base, owner in ((own_base(client, 1), 1), (own_base(client, 0), 0)):
        sid = ids(host, base, owner)[0]
        if owner == 0:
            client.ok({"cmd": "open_screen", "screen": screen, "base": base})
            r = client.cmd({"cmd": "roster_screen", "action": "toggle", "soldier_id": sid})
            client.ok({"cmd": "close_screens"})
            time.sleep(2.0)
            check(f"{row} {screen}: a host soldier is not on the client's screen and its training "
                  f"stays off on both machines",
                  not r.get("ok") and flag(host, base, sid) is False and flag(client, base, sid) is False,
                  f"resp={r} host={flag(host, base, sid)} client={flag(client, base, sid)}")
            continue
        for want in (True, False):
            client.ok({"cmd": "open_screen", "screen": screen, "base": base})
            r = client.cmd({"cmd": "roster_screen", "action": "toggle", "soldier_id": sid})
            got = poll(lambda: (flag(host, base, sid) == want
                                and flag(client, base, sid) == want) or None, timeout=10)
            client.ok({"cmd": "close_screens"})
            check(f"{row} {screen}: the client sets its own soldier's training to {want} on both machines",
                  bool(got) and r.get("ok"),
                  f"resp={r} host={flag(host, base, sid)} client={flag(client, base, sid)}")


def craft_id(gc, base):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"]
                if b["name"] == base)["crafts"][0]["id"]


def row_armor_sort(host, client, base):
    """The crew armor screen's name sort and original order go through the
    host, so both machines hold the same order."""
    before = ids(host, base, 1)
    assert before == ids(client, base, 1), (before, ids(client, base, 1))
    client.ok({"cmd": "open_screen", "screen": "craft_armor", "base": base,
               "craft_id": craft_id(client, base)})
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 2})

    def sorted_on(gc):
        return [n for n in names(gc, base, 1) if n in RENAMED] == sorted(RENAMED)
    got = poll(lambda: (sorted_on(host) and ids(host, base) == ids(client, base)) or None,
               timeout=10)
    check("craft armor: a name sort reorders both machines the same way",
          bool(got), f"before={before} host={names(host, base, 1)} client={names(client, base, 1)}")
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    got = poll(lambda: (ids(host, base, 1) == before and ids(client, base, 1) == before) or None,
               timeout=10)
    client.ok({"cmd": "close_screens"})
    check("craft armor: the original order comes back on both machines",
          bool(got) and ids(host, base) == ids(client, base),
          f"before={before} host={ids(host, base, 1)} client={ids(client, base, 1)}")


def row_crew_original(host, client, base):
    """The partner sorts its own soldiers while the client's crew screen is
    open; the client's original order then leaves the partner's order alone."""
    own = ids(host, base, 0)
    assert len(own) >= 3, ("premise: three host soldiers", own)
    host_names = ["Host Zulu", "Host Mike", "Host Alpha"]
    for sid, name in zip(own, host_names):
        host.ok({"cmd": "soldier_rename", "soldierId": sid, "name": name})
    assert poll(lambda: all(n in names(gc, base, 0) for gc in (host, client)
                            for n in host_names) or None), \
        ("premise: host renames landed", names(client, base, 0))
    client.ok({"cmd": "open_screen", "screen": "craft_soldiers", "base": base,
               "craft_id": craft_id(client, base)})
    host.ok({"cmd": "open_soldiers", "base": base})
    host.ok({"cmd": "soldiers_reorder", "action": "sort", "sort": 2})
    moved = poll(lambda: ([n for n in names(client, base, 0) if n in host_names]
                          == sorted(host_names) and ids(host, base) == ids(client, base)) or None)
    host.ok({"cmd": "soldiers_ok"})
    assert moved, ("premise: the host's sort reached both machines",
                   names(host, base, 0), names(client, base, 0))
    client.ok({"cmd": "roster_screen", "action": "sort", "sort": 0})
    same = settled_same(host, client, base)
    client.ok({"cmd": "close_screens"})
    check("craft crew: the original order leaves both machines with the same roster order",
          same, f"host={names(host, base, 0)} client={names(client, base, 0)}")


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
            row_training_sort(host, client, base, "training", "martial training sort")
            row_training_sort(host, client, base, "psi_training", "psi training sort")
            row_training(host, client, "training", "training", "martial training")
            row_training(host, client, "psi_training", "psiTraining", "psi training")
            row_armor_sort(host, client, base)
            row_crew_original(host, client, base)
            row_transform(host, client, client, 1, "client transform")
            row_transform(host, client, host, 0, "host transform")
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
