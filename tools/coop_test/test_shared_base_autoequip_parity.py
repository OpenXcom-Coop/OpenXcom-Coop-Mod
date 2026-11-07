"""In SHARED, a base equipment screen hands the same starting gear to the same soldier on both machines.

When a base inventory screen opens, every soldier whose equipment layout is empty is auto-equipped from the screen's
item pool. Both machines hold the same world, so the host's and the client's screens must show each soldier carrying
the same items in the same slots. Without the fix the pool follows each game process's own memory order, which
differs between the two machines and between boots, so the two screens often disagree.

That order comes from memory, so no seed reproduces it: one boot shows the difference only some of the time (on
the unchanged build about 2 boots in 3). The rows therefore count over BOOTS fresh SHARED boots,
bring_up("shared_base_autoequip_parity", (48706, 48707, 47923)) each. Every boot runs every row; a row fails when any
boot fails it.
Per boot, guards before each screen: on both machines oxceAlternateCraftEquipmentManagement and disableAutoEquip are
OFF, and every HostBase soldier's equipment layout is empty (so the screen auto-equips everyone). gear(gc) =
inventory_ground soldiers[] -> {"name#id": sorted ["slot:x,y:item+ammo"]}, read with both machines' screens open at
once. Each screen is closed without OK (pop_state, then the parent screen's OK), so no layout is saved and the next
screen still auto-equips.
  autoequip_parity_1  Bases > Soldiers > Inventory on HostBase, both machines. Non-vacuity per boot: the same soldier
        keys on both (>= 2), every soldier carries >= 1 item on each machine. Verdict: in 0 of BOOTS boots does any
        soldier's gear differ.
  autoequip_parity_2  the same on the SKYRANGER craft equipment screen (its crew, the craft's items).
  autoequip_parity_3  js.finish() in every boot: world equality + replica zero-disk (guard).
One EVIDENCE line per row (per boot: the soldiers whose gear differs; the gear of the first boot that differs) before
its verdict; a failed row prints ONE CAPTURE line (the first failing boot's inventory_ground, soldier_layouts and
stacks on both machines). A boot miss fails that boot's cells "boot". ONE run; exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402

TAG, PORTS, BOOTS = "shared_base_autoequip_parity", (48706, 48707, 47923), 8
HB, GEO = "HostBase", "GeoscapeState"
OPTS = ["oxceAlternateCraftEquipmentManagement", "disableAutoEquip"]
ROWS = ["autoequip_parity_%d" % n for n in range(1, 4)]


def short(e, n=600):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead socket is evidence, not a test error
        return {"error": short(e, 160)}


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:
        return ["<get_state: %s>" % short(e, 120)]


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v
        time.sleep(interval)


def gear(ground):
    """inventory_ground soldiers[] -> {"name#id": sorted ["slot:x,y:item+ammo"]}: what each soldier carries, by place."""
    out = {}
    for s in ground.get("soldiers") or []:
        cells = []
        for slot, entries in (s.get("slots") or {}).items():
            for e in entries or []:
                ammo = ("+" + "+".join(e["ammo"])) if e.get("ammo") else ""
                cells.append(f"{slot}:{e.get('x')},{e.get('y')}:{e.get('item')}{ammo}")
        out[f"{s.get('name')}#{s.get('id')}"] = sorted(cells)
    return out


class Boot:
    """One SHARED boot's cells for one row: fails (cell texts), the differing soldiers, and the gear / capture."""

    def __init__(self, n, x):
        self.n, self.x, self.fails, self.differ, self.gear, self.cap = n, x, [], None, None, {}

    def cell(self, name, ok, detail=""):
        if not ok:
            self.fails.append(f"{name}: {detail}")
        return bool(ok)

    def capture(self):
        if self.x is not None:
            for gc in (self.x.host, self.x.client):
                self.cap[f"{gc.name} soldier_layouts {HB}"] = q(gc, {"cmd": "soldier_layouts", "base": HB})
                self.cap[f"{gc.name} stack"] = stack(gc)


class X:
    def __init__(self, js):
        self.js, self.host, self.client = js, js.host, js.client
        self.sky = None


def guards(x, b):
    """Both machines: the two options OFF and every HostBase soldier's equipment layout empty."""
    ok = True
    for gc in (x.host, x.client):
        vals = q(gc, {"cmd": "option_values", "ids": OPTS}).get("values") or {}
        ok = b.cell(f"guard: {gc.name} options off", all(vals.get(o) is False for o in OPTS), vals) and ok
        sol = q(gc, {"cmd": "soldier_layouts", "base": HB}).get("soldiers") or []
        laid = sorted(s.get("name") for s in sol if s.get("layout"))
        ok = b.cell(f"guard: {gc.name} every {HB} soldier's layout empty", sol and not laid,
                    f"{len(sol)} soldiers, with a layout: {laid}") and ok
    return ok


def open_screen(b, x, gc, craft):
    """open_soldiers -> soldiers_inventory, or open_craft_equipment {HostBase, SKY} -> craft_inventory."""
    if craft:
        rep = q(gc, {"cmd": "open_craft_equipment", "base": HB, "craft_id": x.sky})
        first = rep.get("ok") and rep.get("craftId") == x.sky
        parent, inv = "CraftEquipmentState", "craft_inventory"
    else:
        rep = q(gc, {"cmd": "open_soldiers", "base": HB})
        first = rep.get("ok")
        parent, inv = "SoldiersState", "soldiers_inventory"
    if not b.cell(f"guard: {gc.name} open {parent}", first and wait_until(lambda: parent in stack(gc), 30),
                  [rep, stack(gc)]):
        return False
    rep = q(gc, {"cmd": inv})
    return b.cell(f"guard: {gc.name} {inv}",
                  rep.get("opened") is True and wait_until(lambda: "InventoryState" in stack(gc), 30), [rep, stack(gc)])


def close_without_ok(b, gc, craft):
    """pop_state the InventoryState (no OK: nothing saved), then the parent screen's OK."""
    parent, parent_ok = ("CraftEquipmentState", "craft_equipment_ok") if craft else ("SoldiersState", "soldiers_ok")
    rep = q(gc, {"cmd": "pop_state"})
    b.cell(f"guard: {gc.name} pop_state InventoryState",
           rep.get("ok") and wait_until(lambda: "InventoryState" not in stack(gc), 30), [rep, stack(gc)])
    rep = q(gc, {"cmd": parent_ok})
    b.cell(f"guard: {gc.name} {parent_ok}", rep.get("ok") and wait_until(lambda: parent not in stack(gc), 30),
           [rep, stack(gc)])


def parity(x, b, craft):
    if not guards(x, b):
        return b.capture()
    h, c = x.host, x.client
    opened = all([open_screen(b, x, gc, craft) for gc in (h, c)])
    grounds = {gc.name: q(gc, {"cmd": "inventory_ground"}) for gc in (h, c)}
    b.cap.update({f"{n} inventory_ground": v for n, v in grounds.items()})
    for gc in (h, c):
        if "InventoryState" in stack(gc):
            close_without_ok(b, gc, craft)
    g = {n: gear(v) for n, v in grounds.items()}
    b.gear = g
    if not opened:
        return b.capture()
    keys = sorted(g["host"])
    nv = b.cell("non-vacuity: the same soldiers on both screens (>= 2)",
                len(keys) >= 2 and keys == sorted(g["client"]), [keys, sorted(g["client"])])
    for n in ("host", "client"):
        bare = sorted(k for k, v in g[n].items() if not v)
        nv = b.cell(f"non-vacuity: every soldier carries gear on the {n}'s screen", not bare, bare) and nv
    if nv:
        b.differ = sorted(k for k in keys if g["host"].get(k) != g["client"].get(k))
        b.cell(f"{len(b.differ)} of {len(keys)} soldiers carry different starting gear on the two screens",
               not b.differ, b.differ)
    if b.fails:
        b.capture()


def world_equal(x, b):
    try:
        x.js.finish()
    except AssertionError as e:
        b.cell("js.finish", False, short(e, 1500))
        b.cap["world_diff now"] = shared_fixture.world_diff(x.host, x.client)


def cleanup(x):
    """A stopped cell leaves no screen behind."""
    for gc in (x.host, x.client):
        if (stack(gc) or [""])[-1] != GEO:
            q(gc, {"cmd": "close_screens"})
            wait_until(lambda: (stack(gc) or [""])[-1] == GEO, 5.0)


def one_boot(n, per_row, walls):
    t0, js, x = time.time(), None, None
    try:
        try:
            js = shared_fixture.bring_up(TAG, PORTS)
            x = X(js)
            crafts = q(x.host, {"cmd": "base_report", "base": HB}).get("crafts") or []
            x.sky = next((c.get("id") for c in crafts if c.get("type") == "STR_SKYRANGER"), None)
            if x.sky is None:
                raise RuntimeError(f"fixture: no STR_SKYRANGER at {HB}: {crafts}")
        except Exception as e:  # a boot miss fails this boot's cells "boot"
            for rid in ROWS:
                b = Boot(n, None)
                b.cell("boot", False, short(e, 1500))
                per_row[rid].append(b)
            return
        for rid, fn in zip(ROWS, (lambda b: parity(x, b, False), lambda b: parity(x, b, True),
                                  lambda b: world_equal(x, b))):
            b = Boot(n, x)
            try:
                fn(b)
            except Exception as e:
                b.cell(f"guard: {rid} exception", False, short(e))
                b.capture()
            cleanup(x)
            per_row[rid].append(b)
    finally:
        if js is not None:
            js.shutdown()
        walls[f"boot {n}"] = round(time.time() - t0, 1)


def report(rid, boots, results):
    failed = [b for b in boots if b.fails]
    first_diff = next((b for b in boots if b.differ), None)
    ev = {"boots": len(boots), "differ per boot": {b.n: b.differ for b in boots},
          "failed boots": [b.n for b in failed]}
    if first_diff is not None:
        ev[f"gear boot {first_diff.n}"] = first_diff.gear
    print(f"EVIDENCE {rid}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    if failed:
        print(f"CAPTURE {rid}: {json.dumps({'boot': failed[0].n, **failed[0].cap}, sort_keys=True, default=str)}",
              flush=True)
    results[rid] = not failed and len(boots) == BOOTS
    print(f"PASS {rid}" if results[rid] else
          f"FAIL {rid}: {len(failed)} of {len(boots)} boots failed: "
          + " | ".join(f"boot {b.n}: " + "; ".join(f[:300] for f in b.fails) for b in failed), flush=True)


def main():
    t0, results, walls, per_row = time.time(), {}, {}, {rid: [] for rid in ROWS}
    for n in range(1, BOOTS + 1):
        one_boot(n, per_row, walls)
    for rid in ROWS:
        report(rid, per_row[rid], results)
    failed = [rid for rid in ROWS if not results.get(rid)]
    print(f"\ntest_shared_base_autoequip_parity: {len(ROWS) - len(failed)}/{len(ROWS)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
