"""Shared helpers for focused schema-3 Separate campaign live tests."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture


def bring_up(tag, ports):
    return shared_fixture.bring_up(
        tag, ports, campaign_mode="coop",
        host_base="HostBase", client_base="ClientBase")


def geo(gc):
    return gc.ok({"cmd": "geo_state"})


def soldiers_at(gc, base_name):
    bases = gc.ok({"cmd": "get_soldiers"})["bases"]
    return next(base["soldiers"] for base in bases if base["name"] == base_name)


def canonical_world(gc):
    dump = shared_fixture.world_dump(gc)
    live = geo(gc)["bases"]
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

