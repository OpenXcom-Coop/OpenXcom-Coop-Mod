"""Shared helpers for focused schema-3 Separate campaign live tests."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture


def bring_up(tag, ports, host_options=None, client_options=None, mods=()):
    return shared_fixture.bring_up(
        tag, ports, campaign_mode="coop",
        host_base="HostBase", client_base="ClientBase", mods=mods,
        host_options=host_options, client_options=client_options)


def geo(gc):
    return gc.ok({"cmd": "geo_state"})


def soldiers_at(gc, base_name):
    bases = gc.ok({"cmd": "get_soldiers"})["bases"]
    return next(base["soldiers"] for base in bases if base["name"] == base_name)


def canonical_world(gc):
    dump = shared_fixture.world_dump(gc)
    state = geo(gc)
    live = state["bases"]
    # `funds` is deliberately seat-local in Separate. Compare the complete
    # persisted wallet map instead, which must be identical on both replicas.
    dump.pop("funds", None)
    dump["playerFunds"] = gc.ok({"cmd": "month_report"})["playerFunds"]
    for i, base in enumerate(dump["bases"]):
        base.pop("coopBase", None)
        base.pop("coopIcon", None)
        base["ownerPlayerName"] = live[i].get("ownerPlayerName", "")
    return dump


def assert_same_world(host, client, label, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        h, c = canonical_world(host), canonical_world(client)
        if h == c:
            print(f"PASS {label}: full host/client world is identical")
            return h
        time.sleep(0.5)
    raise AssertionError(
        f"{label}: Separate replicas did not converge\n"
        f"host={canonical_world(host)!r}\nclient={canonical_world(client)!r}")


def assert_fresh_named_world(host, client):
    for gc in (host, client):
        state = geo(gc)
        assert state["campaignType"] == 0, state
        assert len(state["bases"]) == 2, state
        assert {b["ownerPlayerName"] for b in state["bases"]} == {
            "HostPlayer", "ClientPlayer"
        }
        for base_name, owner in (("HostBase", 0), ("ClientBase", 1)):
            roster = soldiers_at(gc, base_name)
            assert roster and all(s["owner"] == owner for s in roster), roster
    assert_same_world(host, client, "fresh Separate")


def _states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def fly_to_new_site(host, client, lander, craft_type="STR_SKYRANGER", timeout=120,
                    wait=True, site=("STR_ALIEN_TERROR", "STR_TERROR_MISSION", "STR_SECTOID")):
    """Single-world landing: the HOST spawns a mission site next to the lander's
    own base and the lander's transport is forced en route on BOTH machines (the
    host simulates the flight; the replica only mirrors it). Runs both clocks
    until the landing prompt opens on the lander (the craft owner) and returns
    the craft. The caller answers it (confirm_landing). wait=False returns right
    after the craft is placed at the site (it arrives on the next host tick).
    site = (mission, deployment, race) of the spawned site, a terror site by
    default."""
    base_name = "HostBase" if lander is host else "ClientBase"
    base = next(b for b in geo(host)["bases"] if b["name"] == base_name)
    craft = next(c for c in base["crafts"] if c["type"] == craft_type)
    site_id = host.ok({"cmd": "spawn_mission_site", "mission": site[0],
                       "deployment": site[1],
                       "lon": base["lon"] + 0.35, "lat": base["lat"] + 0.10,
                       "race": site[2], "hours": 240})["site_id"]
    client.wait_for("mission site replicated",
                    lambda: any(s["id"] == site_id for s in geo(client)["missionSites"]) or None,
                    timeout=30, interval=0.3)
    # An empty transport may skip the landing prompt (OXCE option): put one real
    # item aboard through the owner's own command lane.
    equipped = lander.ok({"cmd": "craft_equip", "base": base_name, "craft_id": craft["id"],
                          "item": "STR_RIFLE", "count": 1})
    assert equipped.get("moved") or equipped.get("ok"), equipped
    host.wait_for(
        "craft equipment reaches the host",
        lambda: (lambda r: r if next(c for c in r["crafts"] if c["id"] == craft["id"])
                 ["items"].get("STR_RIFLE", 0) >= 1 else None)(
            host.ok({"cmd": "base_report", "base": base_name})),
        timeout=30, interval=0.3)
    for gc in (client, host):
        forced = gc.ok({"cmd": "craft_force", "base": base_name, "craft_id": craft["id"],
                        "craft_type": craft["type"], "status": "STR_OUT",
                        "fuel": 999999, "lowFuel": False,
                        "lon": base["lon"] + 0.34, "lat": base["lat"] + 0.10,
                        "dest": f"site:{site_id}"})
        assert forced["status"] == "STR_OUT", forced
    if not wait:
        return craft

    def landing():
        if any("ConfirmLandingState" in s for s in _states(lander)):
            return True
        for gc in (host, client):
            t = _states(gc)[-1]
            if "CoopState" in t:
                gc.cmd({"cmd": "coop_dialog_back"})
            elif "GeoscapeState" not in t and "ConfirmLandingState" not in t:
                gc.cmd({"cmd": "dismiss_popup"})
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    lander.wait_for(lander.name + " landing prompt", landing, timeout=timeout, interval=0.5)
    for gc in (host, client):
        gc.cmd({"cmd": "geo_set_speed", "idx": 0})
    return craft
