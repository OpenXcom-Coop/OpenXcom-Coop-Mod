"""Separate Campaign: losing bases in the one host-authoritative world.

The campaign is lost only when NO player has a base left. A player whose
last base falls stays in the campaign. A destroyed base belongs to its
owner; another player's base is never held until the HOST clicks OK.

A throwaway mod gives the Battleship a nuclear payload (missilePower < 0), the
vanilla full-destruction path, so a base is lost without a battle.

  1. HostBase falls (the host dismisses its own dialog): the client still has
     ClientBase, so the campaign continues on both machines.
  2. ClientBase falls: no dialog on the host, the base is gone on both without
     any host click, the client is told, and the campaign ends in defeat on
     both machines (no base left).

ClientBase cannot fall first here: the harness places both bases on the same
spot, and an arriving UFO then resolves to the first base there (HostBase).

Run:  py -3 tools/coop_test/test_separate_campaign_base_loss.py
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import separate_campaign_fixture as fixture

METADATA = """\
name: "Coop nuclear UFO test"
version: 1.0
description: "Test-only: the Battleship destroys a base with a nuclear payload."
author: coop harness

master: xcom1
"""

RULESET = """\
ufos:
  - type: STR_BATTLESHIP
    missilePower: -1
"""


def make_mod(root):
    mod = os.path.join(root, "Coop_Nuclear_UFO_Test")
    os.makedirs(os.path.join(mod, "Ruleset"))
    with open(os.path.join(mod, "metadata.yml"), "w", encoding="utf-8") as f:
        f.write(METADATA)
    with open(os.path.join(mod, "Ruleset", "nuclear_ufo.rul"), "w", encoding="utf-8") as f:
        f.write(RULESET)
    return mod


def states(gc):
    return gc.cmd({"cmd": "get_state"}).get("states", [])


# The campaign's end screens are never popped raw (a raw pop of the lose
# cutscene crashed the host at Game.cpp:209); drains stop at them.
END_SCREENS = ("CutsceneState", "StatisticsState")


def drain(gc, *keep):
    geo.drain_popups(gc, interest=geo.popup(*(END_SCREENS + keep)))


def base_names(gc):
    return {b["name"] for b in fixture.geo(gc)["bases"]}


def ending(gc):
    return gc.ok({"cmd": "ending_state"})["ending"]


def destroy(host, client, base_name, owner):
    """Nuke `base_name` and run both clocks until it is gone everywhere.

    Only the owner's popups are clicked; the other machine's popups are
    clicked too, EXCEPT a BaseDestroyedState, which a non-owner must never get.
    Returns what each machine was shown."""
    # A retaliation mission would send its next UFO at the region's FIRST base
    # (HostBase), whichever base this UFO targets; a research mission adds no
    # base attacks of its own, so only `base_name` is hit.
    host.ok({"cmd": "spawn_base_assault", "base": base_name, "type": "STR_BATTLESHIP",
             "mission": "STR_ALIEN_RESEARCH"})
    seen = {"host": set(), "client": set()}
    non_owner = client if owner is host else host
    deadline = time.time() + 120
    while time.time() < deadline:
        for gc in (host, client):
            for s in states(gc):
                for name in ("BaseDestroyedState", "ErrorMessageState"):
                    if name in s:
                        seen[gc.name].add(name)
        if "BaseDestroyedState" in seen[non_owner.name]:
            raise AssertionError(
                f"{non_owner.name} was shown the {owner.name}'s base loss dialog "
                f"(base still present: {base_name in base_names(host)}); "
                f"host states={states(host)}")
        if base_name not in base_names(host) and base_name not in base_names(client):
            return seen
        if ending(host) or ending(client):
            return seen
        for gc in (host, client):
            # Leave a non-owner's loss dialog open so the next poll reports it.
            if gc is non_owner:
                drain(gc, "BaseDestroyedState")
            else:
                drain(gc)
            if geo.on_geoscape(gc):
                gc.ok({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.3)
    raise AssertionError(f"{base_name} was never destroyed: host bases={base_names(host)}")


def run_clock(host, client, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        for gc in (host, client):
            drain(gc)
            if geo.on_geoscape(gc):
                gc.ok({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.3)
    for gc in (host, client):
        if geo.on_geoscape(gc):
            gc.ok({"cmd": "geo_set_speed", "idx": 0})


def expect_campaign_continues(host, client, label):
    run_clock(host, client, 8)
    endings = {gc.name: ending(gc) for gc in (host, client)}
    assert endings == {"host": 0, "client": 0}, (
        f"{label}: a player losing its last base ended the campaign "
        f"while the other player still has a base", endings)


def expect_defeat(host, client, label):
    deadline = time.time() + 60
    endings = {}
    while time.time() < deadline:
        endings = {gc.name: ending(gc) for gc in (host, client)}
        if endings == {"host": 2, "client": 2}:
            return
        for gc in (host, client):
            drain(gc)
        time.sleep(0.5)
    raise AssertionError(f"{label}: no base left must end the campaign on both: {endings}")


def scenario(tag, ports, mod, order):
    js = fixture.bring_up(tag, ports, mods=[mod])
    host, client = js.host, js.client
    try:
        fixture.assert_fresh_named_world(host, client)
        geo.slow_clock(host, client)
        owners = {"HostBase": host, "ClientBase": client}
        first, second = order
        seen = destroy(host, client, first, owners[first])
        if first == "ClientBase":
            assert "ErrorMessageState" in seen["client"] or "BaseDestroyedState" in seen["client"], (
                "the client was not told its base was destroyed", seen)
        expect_campaign_continues(host, client, f"{first} lost")
        assert base_names(host) == base_names(client) == {second}, (
            base_names(host), base_names(client))
        print(f"PASS {tag}: {first} lost; the campaign continues for both players")

        seen = destroy(host, client, second, owners[second])
        if second == "ClientBase":
            assert "ErrorMessageState" in seen["client"] or "BaseDestroyedState" in seen["client"], (
                "the client was not told its base was destroyed", seen)
        expect_defeat(host, client, f"{second} lost")
        print(f"PASS {tag}: {second} lost; no base left ends the campaign on both")
    finally:
        js.shutdown()


def main():
    tmp = tempfile.mkdtemp(prefix="coop_nuclear_mod_")
    failures = []
    try:
        mod = make_mod(tmp)
        for tag, ports, order in (
                ("sep_base_loss_host_first", (49710, 49711, 49010), ("HostBase", "ClientBase")),):
            try:
                scenario(tag, ports, mod, order)
            except AssertionError as exc:
                failures.append(tag)
                print(f"FAIL {tag}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print(f"FAILED scenarios: {failures}")
        sys.exit(1)
    print("PASS Separate base loss: owner-only notices, defeat only with no base left")


if __name__ == "__main__":
    main()
