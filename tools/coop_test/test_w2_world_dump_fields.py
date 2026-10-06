"""W2-G1 - test_w2_world_dump_fields.py: the SHARED world check compares each soldier's gear (spec
rewrite/prompts/w2g_fidelity_pass.md section (f) rows G1-6..G1-9, Q3 (a), Q4 (a); F7951, F8265; owner D226 (a);
TASK 0 rewrite/w2g1-task0/CONSTANTS.md row T0-6).

Every SHARED test ends with SharedSession.finish(): shared_fixture.world_dump on both machines, compared. Before
W2-G1 the dump compares each soldier as (id, name, owner, craftId, dead) only, so a soldier's armor, equipment
layout, personal layout and that layout's armor can differ between the machines unseen. W2-G1 adds a per-base `gear`
key ({id, armor, layout, personal, personalArmor} per soldier, sorted by id). Craft loads are not compared yet
(W2-H20b stage B).

ONE boot (Boot A): shared_fixture.bring_up("w2g1a", (49451, 49452, 47953)). S0 (guard): world_diff == [] within
20 s; R0 = both machines' shared_resync_stats.requests (`mismatches` is never asserted, F5510). Soldier X is picked
at run time (S25: names roll per boot): the host's first get_soldiers soldier of base 0 whose name is no substring of
another base-0 soldier's name (give_layout matches names by substring) and whose soldier_layouts layout is [] on both
machines (T0-6: id 1); k = X's index in base 0's gear, sorted by id (T0-6: 0).

  G1-6  a one-machine layout write is seen. The CLIENT gets give_layout {base 0's name, STR_PISTOL, belt, X,
        count 1} (one machine: no route, no store change) -> given 1; 1 s; ONE world_diff read. GREEN: exactly
        T0-6's list LAYOUT_DIFF. RED (commit 1): [] - "world_dump does not compare soldier layouts (F7951)". Then
        the HOST gets the same; world_diff == [] within 5 s (guard).
  G1-7  a one-machine armor write is seen. The CLIENT gets seed_soldier_armor {X, STR_PERSONAL_ARMOR_UC}; 1 s; ONE
        read. GREEN: exactly ARMOR_DIFF with X's start armor (T0-6: 'STR_NONE_UC'). RED: [] - "world_dump does not
        compare soldier armor (F8265)". The HOST the same; [] within 5 s (guard).
  G1-8  the dump carries every soldier's gear: for each machine and base i, world_dump(gc)["bases"][i]["gear"] ==
        that machine's soldier_layouts {base: <name>} joined with its get_soldiers armor, sorted by id, entry for
        entry (id, armor, layout, personal, personalArmor). RED: no `gear` key - "world_dump carries no gear".
  G1-9  (guard, last) js.finish() (world equality + the replica's zero disk); both `requests` == R0 at every read
        of G1-6..G1-8.

EVIDENCE line before each verdict; every row runs after a failure; exit 0 only when all four pass, else 2. A boot
miss fails every row "boot" with one CAPTURE line. WV-D99 / WV-D100: one run is the result, no skip path. WV-D95:
run in the foreground to completion.

Run:  python tools/coop_test/test_w2_world_dump_fields.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

TAG, PORTS = "w2g1a", (49451, 49452, 47953)   # F8467: unused lobby 47953 and labels 49451 / 49452
ITEM, SLOT = "STR_PISTOL", "belt"
ARMOR = "STR_PERSONAL_ARMOR_UC"
S0_S, EQUAL_S, SETTLE_S = 20, 5, 1.0
# T0-6 (rewrite/w2g1-task0/CONSTANTS.md): the exact diffs of the one-machine writes; <k> = X's index in base 0's gear,
# <start> = repr of X's start armor
LAYOUT_DIFF = (".bases[0].gear[<k>].layout: 0 entries != 1 entries (host=[] client=[{'ammo': [], 'fixed': False, "
               "'fuse': -1, 'slot': 'STR_BELT', 'type': 'STR_PISTOL', 'x': 0, 'y': 0}])")
ARMOR_DIFF = ".bases[0].gear[<k>].armor: <start> != 'STR_PERSONAL_ARMOR_UC'"


def requests(gc):
    return gc.ok({"cmd": "shared_resync_stats"}).get("requests")


def reads(host, client, ctx, what):
    """Both machines' shared_resync_stats.requests, recorded for G1-9."""
    r = (requests(host), requests(client))
    ctx["reads"].append((what, r))
    return r


def poll_diff(host, client, timeout):
    t0 = time.time()
    d = shared_fixture.world_diff(host, client)
    while d and time.time() - t0 < timeout:
        time.sleep(0.5)
        d = shared_fixture.world_diff(host, client)
    return d, round(time.time() - t0, 1)


def setup(host, client, ctx):
    """S0, R0 and X (T0-6's rule)."""
    d0, secs = poll_diff(host, client, S0_S)
    ctx["r0"] = (requests(host), requests(client))
    ctx["b0"] = host.ok({"cmd": "geo_state"})["bases"][0]["name"]
    sol = host.ok({"cmd": "get_soldiers"})["bases"][0]["soldiers"]
    names = [s["name"] for s in sol]
    lay = [{s["id"]: s["layout"] for s in gc.ok({"cmd": "soldier_layouts", "base": ctx["b0"]})["soldiers"]}
           for gc in (host, client)]
    for s in sol:
        if names.count(s["name"]) == 1 and not any(s["name"] in o for o in names if o != s["name"]) \
                and all(m.get(s["id"]) == [] for m in lay):
            ctx["x"], ctx["k"] = s, sorted(lay[0]).index(s["id"])
            break
    if d0:
        ctx["s0_fails"].append(f"S0: world_diff {d0} after {secs} s (want [] within {S0_S} s)")
    print(f"[w2g1a] S0 world_diff={d0} in {secs} s; R0 (host, client)={ctx['r0']}; base 0 {ctx['b0']!r}; base-0 "
          f"soldiers (id, name, armor)={[(s['id'], s['name'], s.get('armor')) for s in sol]}; X="
          f"{(ctx['x'] or {}).get('id')} k={ctx['k']}", flush=True)


def one_machine_row(host, client, ctx, what, lever, want, blind):
    """The client gets `lever`; 1 s; ONE world_diff read (== `want`); the host gets the same; [] within 5 s."""
    fails = list(ctx["s0_fails"]) if what == "G1-6" else []
    rc = client.ok(lever)
    time.sleep(SETTLE_S)
    d = shared_fixture.world_diff(host, client)
    r1 = reads(host, client, ctx, f"{what} one machine")
    rh = host.ok(lever)
    de, secs = poll_diff(host, client, EQUAL_S)
    r2 = reads(host, client, ctx, f"{what} equalized")
    print(f"EVIDENCE {what}: X id {ctx['x']['id']} name {ctx['x']['name']!r} k={ctx['k']}; client {lever} -> {rc}; "
          f"after {SETTLE_S} s world_diff={d} want={want}; requests={r1}; host -> {rh}; world_diff after the host's "
          f"write={de} in {secs} s; requests={r2}", flush=True)
    if lever["cmd"] == "give_layout" and (rc.get("given"), rh.get("given")) != (1, 1):
        fails.append(f"{what}: give_layout given client={rc.get('given')} host={rh.get('given')} (want 1 on both)")
    if lever["cmd"] == "seed_soldier_armor" and (rc.get("armor"), rh.get("armor")) != (ARMOR, ARMOR):
        fails.append(f"{what}: seed_soldier_armor armor client={rc.get('armor')} host={rh.get('armor')} (want {ARMOR})")
    if not d:
        fails.append(f"{blind}: world_diff [] after the client-only write (want exactly {want})")
    elif d != want:
        fails.append(f"{what}: world_diff after the client-only write = {d} (want exactly {want})")
    if de:
        fails.append(f"{what}: world_diff after the host's equal write = {de} (want [] within {EQUAL_S} s)")
    return fails


def g1_6(host, client, ctx, js):
    if ctx["x"] is None:
        print(f"EVIDENCE G1-6: no soldier X by the rule in base 0 {ctx['b0']!r}", flush=True)
        return ctx["s0_fails"] + ["G1-6 precondition: no base-0 soldier X with a unique, non-substring name and an "
                                  "empty layout on both machines"]
    lever = {"cmd": "give_layout", "base": ctx["b0"], "item": ITEM, "slot": SLOT, "name": ctx["x"]["name"], "count": 1}
    return one_machine_row(host, client, ctx, "G1-6", lever, [LAYOUT_DIFF.replace("<k>", str(ctx["k"]))],
                           "world_dump does not compare soldier layouts (F7951)")


def g1_7(host, client, ctx, js):
    if ctx["x"] is None:
        print("EVIDENCE G1-7: no soldier X (see G1-6)", flush=True)
        return ["G1-7 precondition: no soldier X"]
    want = [ARMOR_DIFF.replace("<k>", str(ctx["k"])).replace("<start>", repr(ctx["x"].get("armor")))]
    lever = {"cmd": "seed_soldier_armor", "soldier_id": ctx["x"]["id"], "armor": ARMOR}
    return one_machine_row(host, client, ctx, "G1-7", lever, want, "world_dump does not compare soldier armor (F8265)")


def g1_8(host, client, ctx, js):
    fails, ev = [], []
    for gc in (host, client):
        dump = shared_fixture.world_dump(gc)
        roster = gc.ok({"cmd": "get_soldiers"})["bases"]
        for i, b in enumerate(gc.ok({"cmd": "geo_state"})["bases"]):
            arm = {s["id"]: s.get("armor") for s in (roster[i]["soldiers"] if i < len(roster) else [])}
            direct = sorted(({"id": s["id"], "armor": arm.get(s["id"]), "layout": s["layout"], "personal": s["personal"],
                              "personalArmor": s["personalArmor"]}
                             for s in gc.ok({"cmd": "soldier_layouts", "base": b["name"]})["soldiers"]),
                            key=lambda s: s["id"])
            got = dump["bases"][i].get("gear") if i < len(dump["bases"]) else None
            xid = (ctx["x"] or {}).get("id")
            ev.append(f"{gc.name} base {i} {b['name']!r}: gear key={got is not None} n={len(got or [])}/{len(direct)} "
                      f"X dump={[s for s in got or [] if s.get('id') == xid]} direct={[s for s in direct if s['id'] == xid]}")
            if got is None:
                fails.append(f"world_dump carries no gear ({gc.name} base {i} {b['name']!r}: no `gear` key)")
            elif got != direct:
                fails.append(f"G1-8: {gc.name} base {i} world_dump gear {got} != soldier_layouts + get_soldiers armor "
                             f"{direct}")
    r = reads(host, client, ctx, "G1-8")
    print(f"EVIDENCE G1-8: {'; '.join(ev)}; requests={r}", flush=True)
    return fails


def g1_9(host, client, ctx, js):
    fails = []
    try:
        js.finish()
    except AssertionError as e:
        fails.append(f"G1-9: js.finish(): {e}")
    after = (requests(host), requests(client))
    bad = [(w, v) for w, v in ctx["reads"] if v != ctx["r0"]]
    print(f"EVIDENCE G1-9: finish ok={not fails}; R0={ctx['r0']}; requests at the reads of G1-6..G1-8={ctx['reads']}; "
          f"after finish={after}", flush=True)
    if bad:
        fails.append(f"G1-9: shared_resync_stats.requests moved from R0 {ctx['r0']} at {bad} (want flat: no restream)")
    return fails


ROWS = (("G1-6", g1_6), ("G1-7", g1_7), ("G1-8", g1_8), ("G1-9", g1_9))


def main():
    t0 = time.time()
    results = {}
    try:
        js = shared_fixture.bring_up(TAG, PORTS)
    except Exception as e:  # a boot miss fails every row
        print(f"CAPTURE boot: {type(e).__name__}: {e}", flush=True)
        for name, _ in ROWS:
            print(f"FAIL {name}: boot", flush=True)
        print(f"\ntest_w2_world_dump_fields: 0/{len(ROWS)} passed (boot) in {time.time() - t0:.1f}s", flush=True)
        return 2
    host, client = js.host, js.client
    ctx = {"reads": [], "s0_fails": [], "x": None, "k": None, "b0": None, "r0": None}
    try:
        try:
            setup(host, client, ctx)
        except Exception as e:
            ctx["s0_fails"].append(f"S0 / X setup: {type(e).__name__}: {e}")
            print(f"[w2g1a] setup error {type(e).__name__}: {e}", flush=True)
        for name, fn in ROWS:
            try:
                fails = fn(host, client, ctx, js)
            except Exception as e:
                fails = [f"{name}: {type(e).__name__}: {e}"]
            results[name] = not fails
            print(f"PASS {name}" if not fails else f"FAIL {name}: " + " | ".join(fails), flush=True)
    finally:
        js.shutdown()
    passed = [n for n, _ in ROWS if results.get(n)]
    failed = [n for n, _ in ROWS if not results.get(n)]
    print(f"\ntest_w2_world_dump_fields: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
