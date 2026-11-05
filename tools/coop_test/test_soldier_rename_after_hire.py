"""Issue #144: renaming a soldier must rename that one soldier, on both machines.

Reported steps (a non-host player on UDP), in Base > Soldiers: rename a soldier,
order a new soldier, rename the new soldier. Reported result: two soldiers carried
the new name.

A rename is one host-applied soldier_rename command that finds the soldier by id
at its base (SoldierInfoState::edtSoldierChange -> SharedEcon / SeparateEcon
submitLocalCmd), so two soldiers can only change together when a machine holds two
soldiers with one id. Each rename here is typed into the real Soldier screen the
way a player does it (click the name box, delete the old name, type, Enter, OK);
the name box sends a soldier_rename on every keystroke.

Scenarios, over the real UDP transport (the report's), in both campaign types that
sync a rename (SHARED and SEPARATE). In each campaign the client player runs the
steps first, then the host player:
  1. rename a soldier at the player's base
  2. order one soldier for that base (the real Purchase screen OK path)
  3. while the recruit is in transit, rename another soldier
  4. the recruit arrives (the host's real arrival path)
  5. rename the recruit

After every step, on BOTH machines: soldier ids are unique, the two machines show
the same roster (ids and names) and the same recruit in transit. After every
rename, on both machines: exactly the renamed soldier carries the new name, and
every other soldier kept its name. The campaigns end with the full world check.

Run:  python tools/coop_test/test_soldier_rename_after_hire.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture
import shared_fixture

SDLK_BACKSPACE = 8
SDLK_RETURN = 13
KEY_PAUSE_S = 0.03  # between keystrokes, as a quick typist; each one sends a rename


def _states(gc):
    return gc.ok({"cmd": "get_state"})["states"]


def _top_is(gc, name):
    states = _states(gc)
    return bool(states) and name in states[-1]


def roster(gc):
    """{base name: [(id, name), ...]} of every real base this machine holds."""
    out = {}
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if b.get("coopIcon"):
            continue
        out[b["name"]] = [(s["id"], s["name"]) for s in b["soldiers"]]
    return out


def in_transit(gc, base):
    return sorted((s["id"], s["name"]) for s in
                  gc.ok({"cmd": "incoming_transfers", "base": base})["soldierRows"])


def names_by_id(gc, label):
    """{id: name} over every real base. Fails when one machine holds two soldiers
    with one id (a rename by id would then reach both)."""
    seen = {}
    for base, rows in roster(gc).items():
        for sid, name in rows:
            assert sid not in seen, (
                f"{label}: {gc.name} holds two soldiers with id {sid} "
                f"('{seen[sid][1]}' at {seen[sid][0]}, '{name}' at {base})")
            seen[sid] = (base, name)
    return {sid: name for sid, (_, name) in seen.items()}


def assert_same(host, client, base, label):
    """Unique ids on each machine, and one roster + one recruit list on both."""
    h, c = names_by_id(host, label), names_by_id(client, label)
    assert roster(host) == roster(client), (
        f"{label}: rosters differ\n  host   {roster(host)}\n  client {roster(client)}")
    th, tc = in_transit(host, base), in_transit(client, base)
    assert th == tc, f"{label}: recruits in transit differ: host {th}, client {tc}"
    in_base = set(h)
    for sid, _ in th:
        assert sid not in in_base, f"{label}: recruit id {sid} also belongs to a soldier at a base"
    return h


def rename_on_screen(gc, base, sid, old_name, new_name):
    """Base > Soldiers > <soldier>: click the name box, delete the old name, type the
    new one, Enter, OK, then leave the Soldiers list."""
    gc.ok({"cmd": "open_soldiers", "base": base})
    gc.wait_for("Soldiers list on top", lambda: _top_is(gc, "SoldiersState") or None,
                timeout=10, interval=0.05)
    shown = gc.ok({"cmd": "screen_state"})["displayed"]
    assert sid in shown, f"{gc.name}: soldier {sid} is not in its own Soldiers list {shown}"
    gc.ok({"cmd": "open_soldier_info", "soldierId": sid, "base": base})
    gc.wait_for("Soldier screen on top", lambda: _top_is(gc, "SoldierInfoState") or None,
                timeout=10, interval=0.05)
    widgets = [w for w in gc.ok({"cmd": "list_widgets"})["widgets"]
               if w["interactive"] and w["visible"]]
    box = next(n for n, w in enumerate(widgets) if "TextEdit" in w["type"])
    gc.ok({"cmd": "click_widget", "nth": box})
    time.sleep(0.2)
    for _ in range(len(old_name) + 1):
        gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_BACKSPACE})
        time.sleep(KEY_PAUSE_S)
    for ch in new_name:
        gc.ok({"cmd": "inject_input", "kind": "key", "key": ord(ch)})
        time.sleep(KEY_PAUSE_S)
    gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN})
    time.sleep(0.2)
    gc.ok({"cmd": "click_widget", "match": "OK"})
    gc.wait_for("back on the Soldiers list", lambda: _top_is(gc, "SoldiersState") or None,
                timeout=10, interval=0.05)
    gc.ok({"cmd": "soldiers_ok"})
    gc.wait_for("Soldiers list closed", lambda: not _top_is(gc, "SoldiersState") or None,
                timeout=10, interval=0.05)


def check_rename(host, client, base, before, sid, new_name, label):
    for gc in (host, client):
        gc.wait_for(f"{label}: '{new_name}' shown",
                    lambda gc=gc: names_by_id(gc, label).get(sid) == new_name or None,
                    timeout=30, interval=0.1)
    time.sleep(0.5)  # every keystroke's result has landed; nothing else may change
    now = assert_same(host, client, base, label)
    for gc in (host, client):
        mine = names_by_id(gc, label)
        holders = sorted(i for i, n in mine.items() if n == new_name)
        assert holders == [sid], (
            f"{label}: on {gc.name} the name '{new_name}' is on soldiers {holders}, "
            f"expected only soldier {sid}")
        changed = {i: (before[i], mine.get(i)) for i in before
                   if i != sid and mine.get(i) != before[i]}
        assert not changed, f"{label}: on {gc.name} other soldiers changed name: {changed}"
    print(f"PASS {label}: only soldier {sid} is '{new_name}' on both machines")
    return now


def run_steps(host, client, player, base, picks, tag):
    """The reported steps by `player` (host or client) at `base`. `picks` = two
    soldier ids that player owns there and has not renamed yet."""
    gc = host if player == "host" else client
    label = f"{tag} {player}"
    before = assert_same(host, client, base, f"{label} start")

    a = picks[0]
    rename_on_screen(gc, base, a, before[a], f"{player[0]} first")
    before = check_rename(host, client, base, before, a, f"{player[0]} first",
                          f"{label} 1 rename soldier {a}")

    in_base = set(before)
    gc.ok({"cmd": "buy", "item": "STR_SOLDIER", "count": 1, "kind": "soldier", "base": base})
    for m in (host, client):
        m.wait_for(f"{label}: recruit in transit",
                   lambda m=m: len(in_transit(m, base)) == 1 or None, timeout=30, interval=0.1)
    before = assert_same(host, client, base, f"{label} 2 recruit ordered")
    recruit = in_transit(host, base)[0][0]
    print(f"PASS {label} 2 recruit ordered: id {recruit} in transit on both machines")

    b = picks[1]
    rename_on_screen(gc, base, b, before[b], f"{player[0]} in transit")
    before = check_rename(host, client, base, before, b, f"{player[0]} in transit",
                          f"{label} 3 rename soldier {b} while the recruit travels")

    host.ok({"cmd": "force_transfer_arrivals", "base": base})
    for m in (host, client):
        m.wait_for(f"{label}: recruit arrived",
                   lambda m=m: recruit in names_by_id(m, label) and not in_transit(m, base) or None,
                   timeout=30, interval=0.1)
    geo.drain_popups(host)
    geo.drain_popups(client)
    before = assert_same(host, client, base, f"{label} 4 recruit arrived")
    assert set(before) - in_base == {recruit}, (
        f"{label} 4: expected exactly the recruit {recruit} to join, got {sorted(set(before) - in_base)}")
    print(f"PASS {label} 4 recruit arrived: soldier {recruit} '{before[recruit]}' on both machines")

    rename_on_screen(gc, base, recruit, before[recruit], f"{player[0]} recruit")
    check_rename(host, client, base, before, recruit, f"{player[0]} recruit",
                 f"{label} 5 rename the recruit {recruit}")


def listed_ids(gc, base):
    """The soldier ids this player's own Base > Soldiers list shows (each player
    sees only the soldiers they own)."""
    gc.ok({"cmd": "open_soldiers", "base": base})
    gc.wait_for("Soldiers list on top", lambda: _top_is(gc, "SoldiersState") or None,
                timeout=10, interval=0.05)
    shown = list(gc.ok({"cmd": "screen_state"})["displayed"])
    gc.ok({"cmd": "soldiers_ok"})
    gc.wait_for("Soldiers list closed", lambda: not _top_is(gc, "SoldiersState") or None,
                timeout=10, interval=0.05)
    return shown


def shared_campaign():
    js = shared_fixture.bring_up("rename_hire_sh", (48960, 48961, 48260), transport="udp")
    host, client = js.host, js.client
    try:
        base = next(iter(roster(host)))
        for player, gc in (("client", client), ("host", host)):
            ids = listed_ids(gc, base)
            assert len(ids) >= 2, f"SHARED setup: the {player}'s list at {base} shows {ids}"
            run_steps(host, client, player, base, ids[0:2], "SHARED")
        js.finish()
    finally:
        js.shutdown()


def separate_campaign():
    js = shared_fixture.bring_up("rename_hire_sep", (48962, 48963, 48262), transport="udp",
                                 campaign_mode="coop", host_base="HostBase",
                                 client_base="ClientBase")
    host, client = js.host, js.client
    try:
        separate_campaign_fixture.assert_fresh_named_world(host, client)
        for player, gc, base in (("client", client, "ClientBase"), ("host", host, "HostBase")):
            ids = listed_ids(gc, base)
            assert len(ids) >= 2, f"SEPARATE setup: the {player}'s list at {base} shows {ids}"
            run_steps(host, client, player, base, ids[0:2], "SEPARATE")
        separate_campaign_fixture.assert_same_world(host, client, "SEPARATE final state")
    finally:
        js.shutdown()


def main():
    shared_campaign()
    separate_campaign()
    print("ALL SOLDIER RENAME AFTER HIRE TESTS PASSED")


if __name__ == "__main__":
    main()
