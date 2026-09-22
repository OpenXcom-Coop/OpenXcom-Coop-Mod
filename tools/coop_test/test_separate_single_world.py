"""Schema-3 SEPARATE regression: one authoritative host save, named bases.

Requires a freshly built executable.  It covers the dangerous conversion target
also used by upgraded legacy saves: two real bases in one world, no durable client
blob, opposite local/foreign presentation, and a host save that resumes by
streaming that same unified world.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT


SAVE = "separate_schema3_resume.sav"
RIFLE = "STR_RIFLE"


def geo(gc):
    return gc.ok({"cmd": "geo_state"})


def canonical_bases(gc):
    return sorted(
        (b["name"], b.get("ownerPlayerName", ""), b["lon"], b["lat"],
         tuple(sorted((c["id"], c["type"]) for c in b["crafts"])))
        for b in geo(gc)["bases"]
    )


def canonical_world(gc):
    """Full one-world invariant, ignoring only seat-local presentation flags."""
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


def assert_own_soldiers_visible(gc, own_base):
    rosters = gc.ok({"cmd": "get_soldiers"})["bases"]
    raw = next(b for b in rosters if b["name"] == own_base)["soldiers"]
    expected = sorted(s["id"] for s in raw)
    assert expected, f"{own_base}: test precondition has no soldiers"
    gc.ok({"cmd": "open_soldiers", "base": own_base})
    try:
        gc.wait_for(
            f"{own_base} soldier screen",
            lambda: (gc.cmd({"cmd": "screen_state"}).get("top") == "soldiers") or None,
            timeout=15, interval=0.3)
        shown = sorted(gc.ok({"cmd": "screen_state"}).get("displayed", []))
        assert shown == expected, \
            f"{own_base}: soldier screen lost/added soldiers: {shown} != {expected}"
    finally:
        gc.ok({"cmd": "soldiers_ok"})


def assert_unified(host, client):
    hg, cg = geo(host), geo(client)
    assert hg["campaignType"] == 0 and cg["campaignType"] == 0
    assert len(hg["bases"]) == 2 and len(cg["bases"]) == 2
    assert canonical_bases(host) == canonical_bases(client)
    assert {b.get("ownerPlayerName") for b in hg["bases"]} == {
        "HostPlayer", "ClientPlayer"
    }
    assert not any(b.get("coopIcon") for b in hg["bases"] + cg["bases"])

    # _coopBase is only a local foreign-base presentation flag: opposite seats
    # must each see exactly one own and one foreign base.
    for gc in (host, client):
        bases = geo(gc)["bases"]
        assert sum(bool(b.get("coopBase")) for b in bases) == 1, \
            f"{gc.name}: expected one foreign presentation base, got {bases!r}"


def main():
    js = shared_fixture.bring_up(
        "sep3", (48920, 48921, 48220), campaign_mode="coop",
        host_base="HostBase", client_base="ClientBase")
    host, client = js.host, js.client
    host_dir, client_dir = js.host_dir, js.client_dir
    try:
        assert_unified(host, client)
        assert_own_soldiers_visible(host, "HostBase")
        assert_own_soldiers_visible(client, "ClientBase")
        initial_world = assert_same_world(host, client, "fresh Separate")

        # A client may buy into the host's base, but may not build facilities
        # there. Both checks travel through the real Separate command protocol;
        # the latter is rejected by the host before command validation.
        client.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "shared_cmd", "jcmd": "fac_build", "baseId": 0,
                   "payload": {}})
        client.wait_for(
            "foreign facility rejected",
            lambda: (client.ok({"cmd": "shared_stats"})["failCount"] >= 1) or None,
            timeout=30, interval=0.5)
        fail = client.ok({"cmd": "shared_stats"})["lastFail"]
        assert "HostPlayer" in fail, f"wrong foreign-base rejection: {fail!r}"
        try:
            client.ok({"cmd": "coop_dialog_back"})
        except Exception:
            pass

        before_incoming = host.ok(
            {"cmd": "incoming_transfers", "base": "HostBase"})["items"].get(RIFLE, 0)
        client.ok({"cmd": "buy", "item": RIFLE, "count": 1, "base": "HostBase"})
        host.wait_for(
            "foreign purchase reached host base",
            lambda: (host.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                     ["items"].get(RIFLE, 0) == before_incoming + 1) or None,
            timeout=30, interval=0.5)
        client.wait_for(
            "foreign purchase replicated",
            lambda: (client.ok({"cmd": "incoming_transfers", "base": "HostBase"})
                     ["items"].get(RIFLE, 0) == before_incoming + 1) or None,
            timeout=30, interval=0.5)
        print("PASS ownership: foreign buy allowed, foreign facility build rejected")

        saved_world = assert_same_world(host, client, "pre-save Separate")
        key = f"host_{host.ok({'cmd': 'save_markers'})['saveID']}_ClientPlayer.data"
        assert not host.ok({"cmd": "has_coop_file", "key": key})["present"], \
            "schema-3 SEPARATE retained a durable client-world blob"

        host.ok({"cmd": "save_game", "file": SAVE})
        assert any(os.path.basename(path) == SAVE for path in session.save_files(host_dir))
        session.assert_client_zero_disk(client_dir)
        print("PASS fresh: two named real bases, one host save, zero client disk/blob")
    finally:
        js.shutdown()

    # Resume in fresh processes from the host file.  Copy only the authoritative
    # save; the client directory intentionally stays empty.
    host = GameClient("host", 48922, host_dir)
    client = GameClient("client", 48923, make_user_dir("sep3_resume_client"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.resume_campaign(host, client, SAVE, port="48221")
        assert_unified(host, client)
        assert_own_soldiers_visible(host, "HostBase")
        assert_own_soldiers_visible(client, "ClientBase")
        resumed_world = assert_same_world(host, client, "resumed Separate")
        assert resumed_world == saved_world, \
            "save/resume changed bases, soldiers, crafts, facilities, stores or economy"
        assert canonical_world(host) != initial_world, \
            "foreign purchase did not become part of the persisted world"
        key = f"host_{host.ok({'cmd': 'save_markers'})['saveID']}_ClientPlayer.data"
        assert not host.ok({"cmd": "has_coop_file", "key": key})["present"], \
            "resumed schema-3 SEPARATE recreated a client-world blob"
        session.assert_client_zero_disk(client.user_dir)
        print("PASS resume: every strategic object survived in one host save")

        # Fill the unified world to eight named-owner bases with deterministic
        # harness fixtures, then prove the ninth real base_new is host-rejected.
        for i in range(6):
            owner = "HostPlayer" if i % 2 == 0 else "ClientPlayer"
            req = {"cmd": "add_base", "name": f"LimitBase{i}",
                   "lon": 0.4 + i * 0.05, "lat": 0.2,
                   "coopbaseid": 500000 + i, "ownerPlayerName": owner}
            host.ok(req)
            client.ok(req)
        assert len(geo(host)["bases"]) == len(geo(client)["bases"]) == 8
        client.ok({"cmd": "shared_reset_stats"})
        client.ok({"cmd": "build_new_base", "lon": LAND_LON, "lat": LAND_LAT,
                   "name": "ForbiddenNinth", "liftX": 2, "liftY": 2})
        client.wait_for(
            "ninth base rejected",
            lambda: (client.ok({"cmd": "shared_stats"})["failCount"] >= 1) or None,
            timeout=30, interval=0.5)
        assert len(geo(host)["bases"]) == len(geo(client)["bases"]) == 8
        assert "MAXIMUM_NUMBER_OF_BASES" in client.ok(
            {"cmd": "shared_stats"})["lastFail"]
        print("PASS base cap: eight total bases allowed, ninth rejected globally")
    finally:
        host.shutdown(); client.shutdown()

    print("ALL SINGLE-WORLD SEPARATE TESTS PASSED")


if __name__ == "__main__":
    main()
