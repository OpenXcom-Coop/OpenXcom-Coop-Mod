"""Separate Campaign: every id in the one host world is unique, and the replica
holds the host's ids.

Separate is one host-owned world. Each player's starting base used to come from
its own new-game world with its own id counters, so both bases held
STR_SKYRANGER-1 and STR_INTERCEPTOR-1/2. Vanilla names a craft by (type, id)
across the whole world (craft and UFO destinations, escorts, interceptions), so
the host renumbers the merged crafts and owns every later craft id. The replica
takes the ids the host sends; it never mints its own.

  FRESH   a fresh campaign has no repeated (type, id) craft pair, no repeated
          soldier id and no repeated base coop id, on both machines, and both
          machines list the same crafts.
  LATER   crafts built later keep the host's ids on the replica: the client
          manufactures two crafts at its base and the host buys one between the
          two units. The host builds unit 1 in an hourly step the replica never
          sees, so a replica that counts ids itself falls one id behind.
  PERUNIT each finished unit of a two-craft batch reaches the replica when the
          host builds it, not only when the whole batch finishes.
  SHIPPED a craft and an item produced with a transfer time go into a transfer
          on the replica, as on the host, instead of straight into the base.
  UFOS    the replica's UFOs carry the host's identity: unique id, display id,
          coop id, status and altitude. Two undetected UFOs (display id 0) stay
          two UFOs on the replica, and a crashed UFO stays crashed.
  DESPAWN a UFO the host removes leaves the replica's list too (no status-3
          leftover until a restream).

A throwaway mod (generated into the isolated user dirs, same on both machines)
adds research-free manufactures that build an interceptor, and an interceptor
and a rifle that ship with a transfer time. Rows run in order and every failure
is reported before the exit code.

Run:  py -3 tools/coop_test/test_separate_world_ids.py
"""

import os
import shutil
import sys
import tempfile
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture

MOD_NAME = "Coop_WorldIds_Test"
BUILD = "STR_COOP_WORLDIDS_INTERCEPTOR"
BUILD_TIME = 5
CRAFT = "STR_INTERCEPTOR"
TRANSFER_ITEM = 0
TRANSFER_CRAFT = 1
# A production whose output ships: the host puts each unit in a transfer.
BUILD_SHIPPED = "STR_COOP_WORLDIDS_INTERCEPTOR_SHIPPED"
RIFLE_SHIPPED = "STR_COOP_WORLDIDS_RIFLE_SHIPPED"
RIFLE = "STR_RIFLE"
SHIP_HOURS = 48

METADATA = """\
name: "Coop world ids test"
version: 1.0
description: "Test-only: a research-free manufacture that builds an interceptor."
author: coop harness

master: xcom1
"""

RULESET = f"""\
manufacture:
  - name: {BUILD}
    category: STR_CRAFT
    space: 1
    time: {BUILD_TIME}
    cost: 1000
    producedItems:
      {CRAFT}: 1
  - name: {BUILD_SHIPPED}
    category: STR_CRAFT
    space: 1
    time: {BUILD_TIME}
    cost: 1000
    transferTimes: [{SHIP_HOURS}, 1, {SHIP_HOURS}]
    producedItems:
      {CRAFT}: 1
  - name: {RIFLE_SHIPPED}
    category: STR_WEAPON
    space: 1
    time: {BUILD_TIME}
    cost: 100
    transferTimes: [{SHIP_HOURS}, 1, {SHIP_HOURS}]
    producedItems:
      {RIFLE}: 1
"""

FAILURES = []


def make_mod(root):
    mod = os.path.join(root, MOD_NAME)
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "worldids.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


def row(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except (AssertionError, TimeoutError) as exc:
        FAILURES.append(name)
        print(f"FAIL {name}: {exc}")


def crafts(gc):
    """Every live craft in the world as (base, type, id): docked and in transit."""
    out = []
    for b in fixture.geo(gc)["bases"]:
        out += [(b["name"], c["type"], c["id"]) for c in b["crafts"]]
    return sorted(out)


def repeated(values):
    return sorted(v for v, n in Counter(values).items() if n > 1)


def assert_unique_ids(gc):
    pairs = [(t, i) for _, t, i in crafts(gc)]
    assert not repeated(pairs), f"{gc.name}: repeated craft (type, id): {repeated(pairs)} in {crafts(gc)}"
    roster = gc.ok({"cmd": "get_soldiers"})["bases"]
    soldier_ids = [s["id"] for b in roster for s in b["soldiers"]]
    assert not repeated(soldier_ids), f"{gc.name}: repeated soldier ids: {repeated(soldier_ids)}"
    base_ids = [b["coopBaseId"] for b in fixture.geo(gc)["bases"]]
    assert not repeated(base_ids), f"{gc.name}: repeated base coop ids: {base_ids}"


def base_index(gc, name):
    return next(i for i, b in enumerate(fixture.geo(gc)["bases"]) if b["name"] == name)


def base_crafts(gc, name):
    return [c for b, t, i in crafts(gc) if b == name for c in [(t, i)]]


def wait_both(host, client, what, pred, timeout=30):
    for gc in (host, client):
        gc.wait_for(f"{gc.name}: {what}", lambda gc=gc: pred(gc) or None,
                    timeout=timeout, interval=0.3)


def client_production(gc):
    base = next(b for b in fixture.geo(gc)["bases"] if b["name"] == "ClientBase")
    return next((p for p in base.get("productions", []) if p["item"] == BUILD), None)


def run_clock(host, client, until, seconds, speed_idx=2):
    """Advance both geoscapes until `until()` holds, closing popups through
    their OK handlers."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if until():
            return True
        for gc in (host, client):
            geo.drain_popups(gc)
            if geo.on_geoscape(gc):
                gc.ok({"cmd": "geo_set_speed", "idx": speed_idx})
        time.sleep(0.3)
    return until()


def stop_clock(host, client):
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})


def sell_crafts(seller, observers, base, count):
    """Sell `count` interceptors from `base` through the real sell command."""
    ids = [i for t, i in base_crafts(seller, base) if t == CRAFT][:count]
    assert len(ids) == count, (base, base_crafts(seller, base))
    seller.ok({"cmd": "shared_cmd", "jcmd": "sell", "baseId": base_index(seller, base),
               "payload": {"crafts": [{"id": i, "type": CRAFT} for i in ids]}})
    for gc in observers:
        gc.wait_for(f"{gc.name}: {base} sold {count} interceptor(s)",
                    lambda gc=gc: not any(t == CRAFT and i in ids
                                          for t, i in base_crafts(gc, base)) or None,
                    timeout=30, interval=0.3)


def production(gc, base, item):
    b = next(b for b in fixture.geo(gc)["bases"] if b["name"] == base)
    return next((p for p in b.get("productions", []) if p["item"] == item), None)


def base_output(gc, base):
    """What production puts at a base: docked crafts, stores and transfers in
    (type, rule, qty; a frozen replica never counts hours down)."""
    b = next(b for b in fixture.geo(gc)["bases"] if b["name"] == base)
    return (sorted((c["type"], c["id"]) for c in b["crafts"]),
            {k: v for k, v in b["items"].items() if v},
            sorted((t["type"], t["rule"], t["qty"]) for t in b["transfers"]))


def repairs(gc):
    """World repairs this replica asked for since the last reset: a change that
    reached it only through a checksum restream did not travel as a result."""
    return gc.ok({"cmd": "shared_resync_stats"})["requests"]


def ufo_keys(gc):
    return {u["uniqueId"]: u["status"] for u in fixture.geo(gc)["ufos"]}


def ufo_identity(gc):
    return sorted((u["uniqueId"], u["id"], u["coopId"], u["type"], u["status"],
                   u["altitude"], u["detected"])
                  for u in fixture.geo(gc)["ufos"] if u["status"] != 3)


def main():
    tmp = tempfile.mkdtemp(prefix="coop_worldids_")
    try:
        mod = make_mod(tmp)
        js = fixture.bring_up("sep_worldids", (49720, 49721, 49020), mods=[mod])
        host, client = js.host, js.client
        try:
            fixture.assert_fresh_named_world(host, client)
            geo.slow_clock(host, client)

            # FRESH --------------------------------------------------------
            def fresh():
                for gc in (host, client):
                    assert_unique_ids(gc)
                assert crafts(host) == crafts(client), (crafts(host), crafts(client))
                print(f"  crafts: {crafts(host)}")
            row("FRESH no repeated craft, soldier or base ids in the one world", fresh)

            # LATER --------------------------------------------------------
            def later():
                for player in ("HostPlayer", "ClientPlayer"):
                    for gc in (host, client):
                        gc.ok({"cmd": "set_funds", "player": player, "value": 50000000})
                # Free two hangars at the client's base for the production and
                # one at the host's base for the purchase.
                sell_crafts(client, (host, client), "ClientBase", 2)
                sell_crafts(host, (host, client), "HostBase", 1)
                before = crafts(host)

                started = client.ok({"cmd": "manufacture_start", "base": "ClientBase",
                                     "item": BUILD, "engineers": 5, "qty": 2})
                assert started.get("sent"), started
                host.wait_for("client production reaches the host",
                              lambda: client_production(host) or None,
                              timeout=30, interval=0.3)
                # One engineer-hour finishes unit 1 in the host's hourly step.
                host.ok({"cmd": "set_production_progress", "base": "ClientBase",
                         "item": BUILD, "timeSpent": BUILD_TIME - 1})
                built = run_clock(host, client,
                                  lambda: (client_production(host) or {}).get("produced", 0) >= 1,
                                  60)
                stop_clock(host, client)
                assert built, f"unit 1 was not built: {client_production(host)}"

                # The host buys an interceptor between the two units.
                host.ok({"cmd": "shared_cmd", "jcmd": "buy",
                         "baseId": base_index(host, "HostBase"),
                         "payload": {"items": [{"type": TRANSFER_CRAFT, "rule": CRAFT, "qty": 1}]}})
                wait_both(host, client, "purchased interceptor in transit",
                          lambda gc: gc.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                          .get("crafts", 0) >= 1 or any(
                              t["type"] == TRANSFER_CRAFT for b in fixture.geo(gc)["bases"]
                              if b["name"] == "HostBase" for t in b["transfers"]))
                arrived = host.ok({"cmd": "force_transfer_arrivals", "base": "HostBase"})
                assert arrived["rows"] >= 1, arrived
                wait_both(host, client, "purchased interceptor docked at HostBase",
                          lambda gc: len([1 for t, i in base_crafts(gc, "HostBase") if t == CRAFT]) == 2)

                # Unit 2 finishes the batch; the replica builds both units now.
                host.ok({"cmd": "set_production_progress", "base": "ClientBase",
                         "item": BUILD, "timeSpent": 2 * BUILD_TIME - 1})
                done = run_clock(host, client,
                                 lambda: client_production(host) is None
                                 and client_production(client) is None, 60)
                stop_clock(host, client)
                assert done, (f"batch did not finish: host={client_production(host)} "
                              f"client={client_production(client)}")
                geo.drain_popups(host)
                geo.drain_popups(client)
                print(f"  before: {before}")
                print(f"  host:   {crafts(host)}")
                print(f"  client: {crafts(client)}")
                for gc in (host, client):
                    assert_unique_ids(gc)
                assert len([1 for t, i in base_crafts(host, "ClientBase") if t == CRAFT]) == 2, \
                    crafts(host)
                assert crafts(host) == crafts(client), \
                    f"replica crafts differ from the host's: host={crafts(host)} client={crafts(client)}"
            row("LATER purchase and production keep the host's craft ids on the replica", later)

            # PERUNIT ------------------------------------------------------
            def perunit():
                sell_crafts(client, (host, client), "ClientBase", 2)
                client.ok({"cmd": "shared_reset_resync_stats"})
                started = client.ok({"cmd": "manufacture_start", "base": "ClientBase",
                                     "item": BUILD, "engineers": 5, "qty": 2})
                assert started.get("sent"), started
                host.wait_for("client production reaches the host",
                              lambda: production(host, "ClientBase", BUILD) or None,
                              timeout=30, interval=0.3)
                host.ok({"cmd": "set_production_progress", "base": "ClientBase",
                         "item": BUILD, "timeSpent": BUILD_TIME - 1})
                built = run_clock(host, client,
                                  lambda: (production(host, "ClientBase", BUILD) or {})
                                  .get("produced", 0) >= 1, 60)
                stop_clock(host, client)
                assert built, f"unit 1 was not built: {production(host, 'ClientBase', BUILD)}"
                assert production(host, "ClientBase", BUILD), "premise: the batch is still running"
                deadline = time.time() + 15
                while time.time() < deadline and \
                        base_output(client, "ClientBase") != base_output(host, "ClientBase"):
                    time.sleep(0.5)
                h, c = base_output(host, "ClientBase"), base_output(client, "ClientBase")
                assert h == c and repairs(client) == 0, (
                    f"after unit 1 the replica's base differs from the host's, or matched only "
                    f"through a world repair ({repairs(client)}):\n host={h}\n client={c}")
                host.ok({"cmd": "set_production_progress", "base": "ClientBase",
                         "item": BUILD, "timeSpent": 2 * BUILD_TIME - 1})
                done = run_clock(host, client,
                                 lambda: production(host, "ClientBase", BUILD) is None
                                 and production(client, "ClientBase", BUILD) is None, 60)
                stop_clock(host, client)
                geo.drain_popups(host)
                geo.drain_popups(client)
                assert done, "batch did not finish on both machines"
                assert crafts(host) == crafts(client) and repairs(client) == 0, \
                    (f"replica crafts differ from the host's, or matched only through a world "
                     f"repair ({repairs(client)}): host={crafts(host)} client={crafts(client)}")
            row("PERUNIT each finished unit of a craft batch reaches the replica", perunit)

            # SHIPPED ------------------------------------------------------
            def shipped():
                # Free every interceptor hangar (an earlier red row may leave one).
                sell_crafts(client, (host, client), "ClientBase",
                            len([1 for t, i in base_crafts(client, "ClientBase") if t == CRAFT]))
                client.ok({"cmd": "shared_reset_resync_stats"})
                for item in (BUILD_SHIPPED, RIFLE_SHIPPED):
                    started = client.ok({"cmd": "manufacture_start", "base": "ClientBase",
                                         "item": item, "engineers": 2, "qty": 1})
                    assert started.get("sent"), (item, started)
                    host.wait_for(f"{item} reaches the host",
                                  lambda item=item: production(host, "ClientBase", item) or None,
                                  timeout=30, interval=0.3)
                    host.ok({"cmd": "set_production_progress", "base": "ClientBase",
                             "item": item, "timeSpent": BUILD_TIME - 1})
                done = run_clock(host, client,
                                 lambda: production(host, "ClientBase", BUILD_SHIPPED) is None
                                 and production(host, "ClientBase", RIFLE_SHIPPED) is None, 60)
                stop_clock(host, client)
                geo.drain_popups(host)
                geo.drain_popups(client)
                assert done, "the shipped productions did not finish on the host"
                h = base_output(host, "ClientBase")
                assert (TRANSFER_CRAFT, CRAFT, 1) in h[2] and (TRANSFER_ITEM, RIFLE, 1) in h[2], \
                    f"premise: the host ships the outputs: {h}"
                deadline = time.time() + 15
                while time.time() < deadline and base_output(client, "ClientBase") != h:
                    time.sleep(0.5)
                    h = base_output(host, "ClientBase")
                c = base_output(client, "ClientBase")
                assert h == c and repairs(client) == 0, (
                    f"the replica did not ship the outputs like the host, or matched only "
                    f"through a world repair ({repairs(client)}):\n host={h}\n client={c}")
            row("SHIPPED a production with a transfer time ships on the replica too", shipped)

            # UFOS ---------------------------------------------------------
            def ufos():
                hb = next(b for b in fixture.geo(host)["bases"] if b["name"] == "HostBase")
                common = {"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
                          "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                          "race": "STR_SECTOID", "trajectory": "P0", "hours": 240}
                spawned = [
                    host.ok(dict(common, state="crashed", speed=0,
                                 lon=hb["lon"] + 1.4, lat=hb["lat"] - 0.25)),
                    host.ok(dict(common, state="flying", speed=1, detected=False,
                                 lon=hb["lon"] - 1.0, lat=hb["lat"] + 0.2)),
                    host.ok(dict(common, state="flying", speed=1, detected=False,
                                 lon=hb["lon"] - 1.2, lat=hb["lat"] + 0.3)),
                ]
                uniques = {s["unique_id"] for s in spawned}
                for gc in (host, client):
                    gc.wait_for(f"{gc.name}: three spawned UFOs listed",
                                lambda gc=gc: uniques.issubset(
                                    {u[0] for u in ufo_identity(gc)}) or None,
                                timeout=30, interval=0.3)
                deadline = time.time() + 20
                while time.time() < deadline and ufo_identity(host) != ufo_identity(client):
                    time.sleep(0.5)
                assert ufo_identity(host) == ufo_identity(client), \
                    (f"replica UFO identity differs:\n host={ufo_identity(host)}\n"
                     f" client={ufo_identity(client)}")
                print(f"  ufos: {ufo_identity(host)}")
            row("UFOS replica UFOs carry the host's ids, coop id and status", ufos)

            # DESPAWN ------------------------------------------------------
            def despawn():
                hb = next(b for b in fixture.geo(host)["bases"] if b["name"] == "HostBase")
                s = host.ok({"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
                             "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                             "race": "STR_SECTOID", "trajectory": "P0", "hours": 240,
                             "state": "crashed", "speed": 0,
                             "lon": hb["lon"] + 2.0, "lat": hb["lat"] - 0.5})
                uid = s["unique_id"]
                wait_both(host, client, "the spawned UFO is listed", lambda gc: uid in ufo_keys(gc))
                host.ok({"cmd": "set_ufo_damage", "ufo_id": s["ufo_id"], "damage": 1000000})
                gone = run_clock(host, client, lambda: uid not in ufo_keys(host), 60)
                stop_clock(host, client)
                assert gone, f"premise: the host never removed the UFO: {ufo_keys(host).get(uid)}"
                deadline = time.time() + 15
                while time.time() < deadline and uid in ufo_keys(client):
                    time.sleep(0.5)
                assert uid not in ufo_keys(client), \
                    (f"the replica still lists the host's removed UFO {uid} "
                     f"(status {ufo_keys(client).get(uid)})")
                assert ufo_identity(host) == ufo_identity(client), \
                    (f"replica UFO identity differs:\n host={ufo_identity(host)}\n"
                     f" client={ufo_identity(client)}")
            row("DESPAWN a UFO the host removes leaves the replica's list too", despawn)
        finally:
            js.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print(f"FAILED ROWS: {FAILURES}")
        sys.exit(1)
    print("ALL WORLD ID ROWS PASSED")


if __name__ == "__main__":
    main()
