"""Separate campaign, private research (the default): every research check uses
the right player's research, and research is credited to the right player.

The Separate campaign is one host-owned world. With Shared Research off, each
player's discoveries live in that player's profile, not in the global list.

Rows (vanilla rules plus the test mod Coop_SeparateResearch_Test):
  UI gates        each machine's research checks (isResearched, as used by the
                  purchase, facility, armor and other screens) and its Ufopaedia
                  article availability follow the LOCAL player's private research.
  disables        the host completes a topic that disables another. The topic
                  stays available to the client's base.
  site expiry     a client-owned terror site expires on the host. The research it
                  unlocks (topic plus one getOneFree bonus) goes to the client's
                  profile only, on both machines.
  option          re-applying the unchanged private option (as every load and
                  every option sync does) does not copy the global list into the
                  player profiles again.

  * PASS (exit 0): every row holds.
  * FAIL (exit 1/2): a row failed or a game process crashed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geo  # noqa: E402
import shared_fixture  # noqa: E402

MOD = os.path.join(HERE, "mods", "Coop_SeparateResearch_Test")
DESPAWN = "STR_COOP_SR_DESPAWN_TOPIC"
FREE = {"STR_COOP_SR_FREE_1", "STR_COOP_SR_FREE_2"}


def profiles(gc):
    state = gc.ok({"cmd": "separate_profile_state"})
    return state, {p["name"]: set(p.get("completedResearch", [])) for p in state["players"]}


def gates(gc, topic):
    return gc.ok({"cmd": "research_gates", "topic": topic})


def base_of(gc, name):
    return next(b for b in gc.ok({"cmd": "geo_state"})["bases"] if b["name"] == name)


def row_ui_gates(host, client):
    for gc in (host, client):
        gc.ok({"cmd": "separate_profile_set", "player": "HostPlayer",
               "research": "STR_LASER_PISTOL"})
        gc.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
               "research": "STR_MEDI_KIT"})
    seen = {gc.name: {t: gates(gc, t) for t in ("STR_LASER_PISTOL", "STR_MEDI_KIT")}
            for gc in (host, client)}
    want = {"host": {"STR_LASER_PISTOL": True, "STR_MEDI_KIT": False},
            "client": {"STR_LASER_PISTOL": False, "STR_MEDI_KIT": True}}
    for name, topics in want.items():
        for topic, expected in topics.items():
            got = seen[name][topic]
            assert got["researched"] is expected, ("UI gates: researched", name, topic, got)
            assert got["articleExists"] is True, ("UI gates: article missing", name, topic, got)
            assert got["articleAvailable"] is expected, ("UI gates: article", name, topic, got)
    print("PASS UI gates: each machine reads its own player's private research")


def row_disables(host, client):
    before = host.ok({"cmd": "available_research", "base": "ClientBase"})["topics"]
    assert "STR_COOP_SR_BRANCH" in before, ("disables: precondition", before)
    done = host.ok({"cmd": "discover_research", "topic": "STR_COOP_SR_DISABLER"})
    assert done["ok"], done
    _, prof = profiles(host)
    assert "STR_COOP_SR_DISABLER" in prof["HostPlayer"], ("disables: precondition", prof)
    host_list = host.ok({"cmd": "available_research", "base": "HostBase"})["topics"]
    client_list = host.ok({"cmd": "available_research", "base": "ClientBase"})["topics"]
    assert "STR_COOP_SR_BRANCH" not in host_list, ("disables: host still offered", host_list)
    assert "STR_COOP_SR_BRANCH" in client_list, ("disables: client lost the topic", client_list)
    print("PASS disables: the host's branch choice leaves the client's tree alone")


def row_site_expiry(host, client):
    geo.slow_clock(host, client)
    cb = base_of(host, "ClientBase")
    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": cb["lon"] + 0.35,
                    "lat": cb["lat"] + 0.10, "race": "STR_SECTOID", "hours": 1,
                    "owner": "ClientPlayer"})
    assert site.get("site_id") is not None, site
    geo.skip_ingame_time(host, client, minutes=4 * 60, speed_idx=4,
                         real_timeout=90, stuck_timeout=40)
    geo.slow_clock(host, client)
    for gc in (host, client):
        geo.drain_popups(gc)

    def learned(gc):
        _, prof = profiles(gc)
        return {p: (DESPAWN in prof[p], sorted(prof[p] & FREE)) for p in prof}

    host_view = learned(host)
    assert host_view["ClientPlayer"][0] and len(host_view["ClientPlayer"][1]) == 1, \
        ("site expiry: the site owner did not get the topic and one bonus", host_view)
    assert host_view["HostPlayer"] == (False, []), ("site expiry: host credited", host_view)
    client.wait_for("client replica learns the site research",
                    lambda: learned(client) == host_view or None,
                    timeout=20, interval=0.5)
    print(f"PASS site expiry: research went to the site owner only: {host_view}")


def row_option_resync(host):
    topic = "STR_COOP_SR_SHARED_TOPIC"
    host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": True})
    host.ok({"cmd": "discover_research", "topic": topic})
    host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
    _, prof = profiles(host)
    assert all(topic in prof[p] for p in prof), ("option: switch did not seed profiles", prof)
    # A later private-only change: the client's profile no longer holds the topic.
    host.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
             "removeResearch": topic})
    host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
    _, prof = profiles(host)
    assert topic not in prof["ClientPlayer"], \
        ("option: unchanged option re-copied the global list into a profile", prof)
    print("PASS option: only a real switch copies research between stores")


def main():
    js = shared_fixture.bring_up(
        "sep_private_research", (49061, 49062, 48361), mods=[MOD],
        campaign_mode="coop", host_base="HostBase", client_base="ClientBase")
    host, client = js.host, js.client
    failed = []
    try:
        state, _ = profiles(host)
        assert state["researchSharingEnabled"] is False, state
        rows = (("UI gates", lambda: row_ui_gates(host, client)),
                ("disables", lambda: row_disables(host, client)),
                ("site expiry", lambda: row_site_expiry(host, client)),
                ("option", lambda: row_option_resync(host)))
        for name, row in rows:
            try:
                row()
            except AssertionError as e:
                failed.append(name)
                print(f"FAIL {name}: {e}")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    if not alive:
        print("FAIL: a game process died")
        sys.exit(2)
    if failed:
        print("FAIL rows: " + ", ".join(failed))
        sys.exit(1)
    print("PASS: Separate private research is checked and credited per player")


if __name__ == "__main__":
    main()
