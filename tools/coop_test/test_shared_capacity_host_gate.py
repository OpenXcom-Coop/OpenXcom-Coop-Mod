"""issue #121: the SHARED host validators must RE-CHECK craft capacity.

In SHARED either player can command/edit any craft, so the client-side capacity gate
is not enough: player B's client validates against B's (possibly stale) local view, the
request passes B's gate, reaches the host, and pre-fix the host applied it WITHOUT re-
checking -> an over-capacity craft that can desync or fault a later deployment.

This exercises both host validators with a throwaway mod (activated on BOTH machines):

  1. craftRearmValidate  - a craft weapon whose getBonusStats() demands 100 cargo the
                           Interceptor (0 unit capacity) cannot give -> STR_NOT_ENOUGH_-
                           CARGO_SPACE.
  2. soldierArmorValidate - a Skyranger with zero large-unit capacity, a soldier aboard,
                           then asked to wear a size-2 (2x2) armor that cannot fit ->
                           STR_NOT_ENOUGH_CRAFT_SPACE (Craft::validateArmorChange).

Each gate is checked twice:

  CLIENT GATE (faithful) - drive the REAL screen path WITHOUT `force`: the harness now
                           runs the same client gate a player's screen runs, so the
                           request is refused locally and never sent (resp["gate"]).
  HOST GATE  (the fix)   - drive it WITH `force`, which bypasses the client gate exactly
                           as a stale replica whose local view passed would. The request
                           reaches the host un-gated; the host must REJECT it (shared_fail
                           with the STR_ reason) and leave BOTH worlds unchanged / equal.
                           Pre-fix the host applied the over-capacity change and the two
                           worlds diverged.

Run:  python tools/coop_test/test_shared_capacity_host_gate.py
      python tools/coop_test/test_shared_capacity_host_gate.py weapon
      python tools/coop_test/test_shared_capacity_host_gate.py armor
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture

# --- the throwaway mod ------------------------------------------------------
# A craft weapon that costs 100 cargo (a capacity PENALTY no stock craft weapon has), a
# single-seat Skyranger, and a size-2 Personal Armor. None of this ships with OXCE, and
# the capacity gates are dead code on stock data (stock craft weapons carry no bonus
# stats and every stock soldier armor is size 1), so - like test_shared_missile_bombardment
# - we generate the ruleset into the harness's isolated user dirs and activate it on both.
CAPKILLER = "STR_COOP_TEST_CAPKILLER"       # the over-capacity craft weapon
LAUNCHER = "STR_STINGRAY_LAUNCHER"          # a real stock item, reused as its launcher
ARMOR = "STR_PERSONAL_ARMOR_UC"             # patched to size 2 by the mod
ARMOR_ITEM = "STR_PERSONAL_ARMOR"
DEFAULT_ARMOR = "STR_NONE_UC"
STOCK = 2

METADATA = """\
name: "Coop capacity host-gate test"
version: 1.0
description: "Test-only: an over-capacity craft weapon, a 1-seat Skyranger, a size-2 armor."
author: coop harness

master: xcom1
"""

RULESET = f"""\
craftWeapons:
  - type: {CAPKILLER}
    launcher: {LAUNCHER}
    weaponType: 0
    stats:
      soldiers: -100
crafts:
  - type: STR_SKYRANGER
    vehicles: 0        # zero large-unit capacity -> a 2x2 armor never fits
armors:
  - type: {ARMOR}
    size: 2
    corpseBattle:      # a 2x2 armor needs size*size battle corpse items
      - STR_CORPSE_ARMOR
      - STR_CORPSE_ARMOR
      - STR_CORPSE_ARMOR
      - STR_CORPSE_ARMOR
    loftempsSet: [3, 3, 3, 3]   # ... and size*size LOFT templates
"""


def _make_mod(root):
    mod = os.path.join(root, "Coop_Capacity_HostGate_Test")
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "capacity.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


# --- helpers ----------------------------------------------------------------

def _base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base")


def _base_items(gc, item):
    return _base0(gc)["items"].get(item, 0)


def _interceptor(gc, craft_id):
    for c in _base0(gc)["crafts"]:
        if c["id"] == craft_id:
            return c
    return None


def _skyranger(gc):
    for c in _base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("no skyranger")


def _soldier(gc, sid):
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        for s in b["soldiers"]:
            if s["id"] == sid:
                return s
    return None


def _stats(gc):
    return gc.ok({"cmd": "shared_stats"})


def _reset_stats(host, client):
    host.ok({"cmd": "shared_reset_stats"})
    client.ok({"cmd": "shared_reset_stats"})


def _dismiss(gc):
    # Drop the host-rejection popup so it does not block the clock advance.
    try:
        gc.ok({"cmd": "coop_dialog_back"})
    except Exception:
        pass


# ======================================================================
# 1. craftRearmValidate: an over-capacity craft weapon on an Interceptor.
# ======================================================================
def test_weapon(ports, mod):
    js = shared_fixture.bring_up("jcaphgw", ports, mods=[mod])
    host, client = js.host, js.client
    try:
        # Seed identical worlds: an EMPTY interceptor + the launcher stock on both.
        craft_ids = set()
        for gc in (host, client):
            r = gc.ok({"cmd": "spawn_craft", "type": "STR_INTERCEPTOR", "weapon": "STR_NONE"})
            craft_ids.add(r["craft_id"])
            gc.ok({"cmd": "give_items", "item": LAUNCHER, "count": STOCK})
        assert len(craft_ids) == 1, f"spawn_craft gave different ids per machine: {craft_ids}"
        cid = craft_ids.pop()
        js.assert_world_equal("bootstrap + empty interceptor + launchers")

        base0 = _base_items(host, LAUNCHER)
        assert _interceptor(host, cid)["weaponLoadout"][0] == "", "premise: slot 0 not empty"
        print(f"PASS setup: empty interceptor slot 0, {base0} launchers, world equal")

        # --- CLIENT GATE (faithful): the harness now runs the client capacity gate, so
        # a normal (un-forced) request is refused locally and never sent.
        r = client.cmd({"cmd": "craft_rearm", "weapon": CAPKILLER, "slot": 0, "craft_id": cid})
        assert not r.get("ok") and not r.get("moved"), f"client gate did not block: {r}"
        assert r.get("gate") == "STR_NOT_ENOUGH_CARGO_SPACE", f"unexpected client gate: {r}"
        assert _interceptor(host, cid)["weaponLoadout"][0] == "", "world changed on a blocked (unsent) rearm"
        print(f"PASS client-gate: over-capacity rearm refused locally '{r['gate']}', nothing sent")

        # --- HOST GATE (the fix): force past the client gate (a stale-replica request),
        # the host must REJECT it and leave both worlds unchanged.
        _reset_stats(host, client)
        r = client.ok({"cmd": "craft_rearm", "weapon": CAPKILLER, "slot": 0, "craft_id": cid, "force": True})
        assert r.get("moved"), f"forced rearm not sent: {r}"
        client.wait_for("client received the host's rejection",
                        lambda: (_stats(client)["failCount"] >= 1) or None,
                        timeout=30, interval=0.5)
        cs = _stats(client)
        assert cs["lastFail"] == "STR_NOT_ENOUGH_CARGO_SPACE", f"unexpected host reason: {cs}"
        # world UNCHANGED on both sides: slot still empty, launcher stock intact.
        for name, gc in (("host", host), ("client", client)):
            assert _interceptor(gc, cid)["weaponLoadout"][0] == "", \
                f"{name}: host applied an over-capacity rearm: {_interceptor(gc, cid)['weaponLoadout']}"
            assert _base_items(gc, LAUNCHER) == base0, f"{name}: launcher stock moved on a rejected rearm"
        print(f"PASS host-gate: host rejected the forced over-capacity rearm '{cs['lastFail']}', "
              "both worlds unchanged")
        _dismiss(client)

        js.assert_world_equal("after rejected over-capacity rearm (worlds equal)")
        js.finish()
        print("ALL CRAFT-REARM HOST-GATE TESTS PASSED")
    finally:
        js.shutdown()


# ======================================================================
# 2. soldierArmorValidate: a size-2 armor that no longer fits a full craft.
# ======================================================================
def test_armor(ports, mod):
    js = shared_fixture.bring_up("jcaphga", ports, mods=[mod])
    host, client = js.host, js.client
    try:
        for gc in (host, client):
            gc.ok({"cmd": "give_items", "item": ARMOR_ITEM, "count": STOCK})
        js.assert_world_equal("bootstrap + personal-armor stock")

        # The mod zeroed the Skyranger's large-unit capacity. Board ONE (host-owned)
        # soldier so a switch to the size-2 armor is validated against the craft.
        cid = _skyranger(host)["id"]
        roster = host.ok({"cmd": "get_soldiers"})["bases"][0]["soldiers"]
        sid = next(s["id"] for s in roster if s["owner"] == 0)
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} soldier aboard the skyranger",
                        lambda gc=gc: (_soldier(gc, sid)["craftId"] == cid) or None,
                        timeout=40, interval=0.5)
        assert _soldier(host, sid)["armor"] == DEFAULT_ARMOR, "premise: soldier not in default armor"
        base0 = _base_items(host, ARMOR_ITEM)
        print(f"PASS setup: soldier {sid} aboard the skyranger (no large-unit room), "
              f"{base0} armor in stock, world equal")

        # --- CLIENT GATE (faithful).
        r = client.cmd({"cmd": "soldier_armor", "soldier_id": sid, "armor": ARMOR})
        assert not r.get("ok") and not r.get("moved"), f"client gate did not block: {r}"
        assert r.get("gate") == "STR_NOT_ENOUGH_CRAFT_SPACE", f"unexpected client gate: {r}"
        assert _soldier(host, sid)["armor"] == DEFAULT_ARMOR, "world changed on a blocked (unsent) armor swap"
        print(f"PASS client-gate: over-capacity armor swap refused locally '{r['gate']}', nothing sent")

        # --- HOST GATE (the fix).
        _reset_stats(host, client)
        r = client.ok({"cmd": "soldier_armor", "soldier_id": sid, "armor": ARMOR, "force": True})
        assert r.get("moved"), f"forced armor swap not sent: {r}"
        client.wait_for("client received the host's rejection",
                        lambda: (_stats(client)["failCount"] >= 1) or None,
                        timeout=30, interval=0.5)
        cs = _stats(client)
        assert cs["lastFail"] == "STR_NOT_ENOUGH_CRAFT_SPACE", f"unexpected host reason: {cs}"
        for name, gc in (("host", host), ("client", client)):
            assert _soldier(gc, sid)["armor"] == DEFAULT_ARMOR, \
                f"{name}: host applied an over-capacity armor swap: {_soldier(gc, sid)['armor']}"
            assert _base_items(gc, ARMOR_ITEM) == base0, f"{name}: armor stock moved on a rejected swap"
        print(f"PASS host-gate: host rejected the forced over-capacity armor swap '{cs['lastFail']}', "
              "both worlds unchanged")
        _dismiss(client)

        js.assert_world_equal("after rejected over-capacity armor swap (worlds equal)")
        js.finish()
        print("ALL SOLDIER-ARMOR HOST-GATE TESTS PASSED")
    finally:
        js.shutdown()


SECTIONS = {
    "weapon": (test_weapon, (48980, 48981, 48280)),
    "armor":  (test_armor,  (48982, 48983, 48282)),
}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    tmp = tempfile.mkdtemp(prefix="coop_caphgate_mod_")
    try:
        mod = _make_mod(tmp)
        if which:
            fn, ports = SECTIONS[which]
            fn(ports, mod)
        else:
            for name in ("weapon", "armor"):
                fn, ports = SECTIONS[name]
                print(f"\n==== issue #121 host-gate section: {name} ====")
                fn(ports, mod)
        print("\nALL SHARED CAPACITY HOST-GATE TESTS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
