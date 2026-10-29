"""Separate campaign: the world checksum covers every player's private state.

The Separate campaign is one host-owned world. Each player's wallet and private
research live in that player's profile inside the world. The host stamps a world
checksum on its geoscape `time` heartbeat; a replica whose world drifts from it
asks for a fresh world (the same restream as the SHARED desync repair).

Every private term is part of the checksum, so drift in a private research
profile or in the other player's wallet is detected and repaired.

Rows (vanilla rules, private research, clock paused):
  terms          at rest the host and the client compute the same checksum,
                 including one wallet and one research count per player (no false
                 positive: the replica logged no mismatch).
  research       the replica's ClientPlayer profile gains a topic the host world
                 does not have. The replica detects it, asks for a resync, and its
                 profile equals the host's again.
  wallet         the replica's copy of the OTHER player's wallet (HostPlayer) is
                 changed. The replica detects it, asks for a resync, and both
                 wallets equal the host's again.
  release        after each repair the client is not parked in the resume hold and
                 the whole world is identical on both machines.
Drifts that funds and counts alone cannot see, each made on the replica only and
each detected and repaired like the research row:
  stores         one medi-kit more and one rifle fewer at ClientBase (same total).
  projects       a research project only the replica's ClientBase runs.
  counters       a custom counter only the replica holds.
  events         a pending geoscape event only the replica holds.
  soldier stats  one soldier's current stat differs on the replica only
                 (host training raises stats that no result carries). The replica
                 detects it and one request and one restream repair it.
  fast clock     at the fastest clock (a game day per tick) a drift is repaired by
                 exactly one resync request and one restream: the replica waits
                 for the stream it asked for although many game hours pass during
                 it, instead of asking again mid-stream.

  * PASS (exit 0): every row holds.
  * FAIL (exit 1/2): a row failed or a game process crashed.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import separate_campaign_fixture as sep  # noqa: E402

COOP_DLG_CLIENT_RESUME_HOLD = 68
DEBOUNCE_S = 3.0  # SharedEcon RESYNC_DEBOUNCE_MS: a mismatch must survive this
DRIFT_TOPIC = "STR_LASER_WEAPONS"
BOGUS_FUNDS = 12345
FASTEST = 5  # geoscape speed index: one game day per 80 ms tick
BULK_SOLDIERS = 400  # fast clock row: about 1 KB each, so one restream lasts seconds
STREAM_LINE = "[coop-shared] streaming authoritative world to client"
BUSY_LINE = "[coop-shared] resync request dropped: streamer busy"


def checksum(gc):
    r = gc.ok({"cmd": "shared_checksum"})
    return {k: v for k, v in r.items() if k.startswith("chk")}


def profiles(gc):
    state = gc.ok({"cmd": "separate_profile_state"})
    return {p["name"]: (p["funds"], sorted(p.get("completedResearch", [])))
            for p in state["players"]}


def resync(gc):
    return gc.ok({"cmd": "shared_resync_stats"})


def released(gc):
    return gc.ok({"cmd": "get_coop"})["coopDialog"] != COOP_DLG_CLIENT_RESUME_HOLD


def row_terms(host, client):
    h, c = checksum(host), checksum(client)
    assert "chkPlayerFunds" in h and "chkPlayerResearch" in h, ("terms: no player terms", h)
    assert set(h["chkPlayerFunds"]) == {"HostPlayer", "ClientPlayer"}, ("terms: wallets", h)
    assert set(h["chkPlayerResearch"]) == {"HostPlayer", "ClientPlayer"}, ("terms: research", h)
    assert h == c, ("terms: host and client checksums differ at rest", h, c)
    # The bring-up may count mismatching heartbeats while the client still holds
    # its own pre-campaign world, but it must never ask for a repair.
    rs = resync(client)
    assert rs["requests"] == 0, ("terms: bring-up asked for a resync", rs)
    client.ok({"cmd": "shared_reset_resync_stats"})
    time.sleep(2 * DEBOUNCE_S)
    rs = resync(client)
    assert rs["mismatches"] == 0 and rs["requests"] == 0, ("terms: false positive at rest", rs)
    print(f"PASS terms: identical checksum on both machines, no mismatch at rest {h}")


def repair(host, client, label, drifted):
    """Wait for the replica to notice the drift, ask for a resync and adopt the
    host's world. `drifted` says whether the replica still differs."""
    client.wait_for(label + ": replica noticed the drift",
                    lambda: resync(client)["mismatches"] >= 1 or None,
                    timeout=60, interval=0.5)
    client.wait_for(label + ": replica asked for a resync",
                    lambda: resync(client)["requests"] >= 1 or None,
                    timeout=60, interval=0.5)
    client.wait_for(label + ": replica adopted the host's world",
                    lambda: (not drifted()) or None, timeout=90, interval=0.5)
    client.wait_for(label + ": client released from the resume hold",
                    lambda: released(client) or None, timeout=60, interval=0.5)
    assert resync(host)["requests"] >= 1, (label + " host served no resync", resync(host))
    rs = resync(client)
    assert not rs["pending"] and not rs["gaveUp"], (label + " resync guard", rs)
    sep.assert_same_world(host, client, label + " repaired")
    assert profiles(host) == profiles(client), (label, profiles(host), profiles(client))
    # The repair is complete once a heartbeat agrees again (that also re-arms
    # the cooldown, so the next row gets its own repair).
    client.wait_for(label + ": checksums agree",
                    lambda: checksum(host) == checksum(client) or None,
                    timeout=30, interval=0.5)


def row_research(host, client):
    host_view = profiles(host)
    assert DRIFT_TOPIC not in host_view["ClientPlayer"][1], ("research: precondition", host_view)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    r = client.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
                   "research": DRIFT_TOPIC})
    assert r.get("researchAdded"), ("research: drift not made", r)
    assert profiles(client) != host_view, "research: the replica did not drift"
    repair(host, client, "research",
           lambda: DRIFT_TOPIC in profiles(client)["ClientPlayer"][1])
    assert profiles(client) == host_view, ("research", host_view, profiles(client))
    print("PASS research: a drifted private research profile is repaired")


def row_wallet(host, client):
    host_view = profiles(host)
    assert host_view["HostPlayer"][0] != BOGUS_FUNDS, ("wallet: precondition", host_view)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    r = client.ok({"cmd": "set_funds", "player": "HostPlayer", "value": BOGUS_FUNDS})
    assert profiles(client)["HostPlayer"][0] == BOGUS_FUNDS, ("wallet: drift not made", r)
    repair(host, client, "wallet",
           lambda: profiles(client)["HostPlayer"][0] == BOGUS_FUNDS)
    assert profiles(client) == host_view, ("wallet", host_view, profiles(client))
    print("PASS wallet: a drifted wallet of the other player is repaired")


def client_base(gc):
    return next(b for b in sep.canonical_world(gc)["bases"] if b["name"] == "ClientBase")


def drift_repaired(host, client, label, make_drift, drifted):
    """A replica-only drift that the old checksum terms (funds, counts) cannot
    see. The checksum must notice it and the restream must repair it."""
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    make_drift()
    assert drifted(), label + ": the drift was not made"
    repair(host, client, label, drifted)
    print(f"PASS {label}: a drift the old counts missed is detected and repaired")


def row_stores(host, client):
    """One more medi-kit and one rifle fewer at ClientBase: the store total
    (chkItems) is unchanged, the stores are not."""
    rifles = client_base(host)["items"].get("STR_RIFLE", 0)
    assert rifles >= 1, ("stores precondition: ClientBase has a rifle", client_base(host)["items"])

    def make():
        client.ok({"cmd": "give_items", "item": "STR_MEDI_KIT", "count": 1, "base": "ClientBase"})
        client.ok({"cmd": "give_items", "item": "STR_RIFLE", "count": -1, "base": "ClientBase"})
    drift_repaired(host, client, "stores", make,
                   lambda: client_base(client)["items"] != client_base(host)["items"])


def row_projects(host, client):
    """A research project only the replica's ClientBase runs."""
    def make():
        client.ok({"cmd": "start_research", "topic": DRIFT_TOPIC, "cost": 100000,
                   "base": "ClientBase"})
    drift_repaired(host, client, "research projects", make,
                   lambda: client_base(client)["research"] != client_base(host)["research"])


# A counter a rule writes (Coop_EventSync_Test STR_COOP_EV_EFFECTS_TOPIC): the
# checksum covers only rule-named counters, not object ids.
COUNTER = "COOP_EV_COUNTER"


def counters(gc):
    return gc.ok({"cmd": "custom_counters", "names": [COUNTER]})["counters"]


def row_counters(host, client):
    """A value of a rule-named custom counter only the replica holds."""
    drift_repaired(host, client, "custom counters",
                   lambda: client.ok({"cmd": "set_custom_counter", "name": COUNTER,
                                      "value": 7}),
                   lambda: counters(client) != counters(host))


def schedule(gc):
    return sorted((e["name"], e["owner"]) for e in gc.ok({"cmd": "geo_events"})["events"]
                  if not e["over"])


def row_events(host, client):
    """A pending geoscape event only the replica holds."""
    drift_repaired(host, client, "pending events",
                   lambda: client.ok({"cmd": "spawn_event", "name": "STR_COOP_EV_CERTAIN",
                                      "owner": "ClientPlayer"}),
                   lambda: schedule(client) != schedule(host))


class EngineLog:
    """What an engine log gained since this object was made."""

    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "openxcom.log")
        self.offset = os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def count(self, text):
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            return f.read().count(text)


def set_speed(host, client, idx):
    for gc in (host, client):
        gc.ok({"cmd": "geo_set_speed", "idx": idx})


def row_fast(host, client, host_dir):
    """The replica asks once per drift, however fast the clock runs.
    Setup: BULK_SOLDIERS soldiers spawned at HostBase on the host only, so the
    first repair (slow clock) gives both machines a world whose restream takes
    seconds instead of a quarter of one. Then a counter drift on the replica;
    the clock goes to the fastest speed the moment the replica sends its
    request, so the game clock runs many game hours while that long stream is
    in flight. A host popup stops the host's geoscape and its heartbeat, so
    the host closes its popups during the stream, as a player would."""
    host.ok({"cmd": "spawn_soldier", "base": "HostBase", "type": "STR_SOLDIER",
             "owner": 0, "count": BULK_SOLDIERS})
    roster = lambda gc: len(sep.soldiers_at(gc, "HostBase"))  # noqa: E731
    repair(host, client, "fast clock setup (bulk world)", lambda: roster(client) != roster(host))
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    hlog = EngineLog(host_dir)
    client.ok({"cmd": "set_custom_counter", "name": COUNTER, "value": 9})
    assert counters(client) != counters(host), "fast clock: the drift was not made"
    try:
        client.wait_for("fast clock: replica asked for a resync",
                        lambda: resync(client)["requests"] >= 1 or None,
                        timeout=60, interval=0.02)
        asked_at, client_asked_at = geo.game_minutes(host), geo.game_minutes(client)
        set_speed(host, client, FASTEST)
        # The guard is tested only if the replica's own clock (the host's time
        # heartbeat) passes RESYNC_COOLDOWN_MINUTES while its request is pending.
        guard_tested = False
        deadline = time.time() + 90
        while counters(client) != counters(host):
            assert time.time() < deadline, ("fast clock: no repair within 90 s", resync(client))
            if not guard_tested and resync(client)["pending"]:
                guard_tested = geo.game_minutes(client) - client_asked_at >= 60
            geo.drain_popups(host, limit=1)
            time.sleep(0.2)
        stream_minutes = geo.game_minutes(host) - asked_at
    finally:
        set_speed(host, client, 0)
    geo.drain_popups(host)
    geo.drain_popups(client)
    client.wait_for("fast clock: client released from the resume hold",
                    lambda: released(client) or None, timeout=60, interval=0.25)
    client.wait_for("fast clock: checksums agree",
                    lambda: checksum(host) == checksum(client) or None,
                    timeout=30, interval=0.25)
    assert guard_tested, (
        f"fast clock fixture: the replica's clock never passed 60 game minutes while its "
        f"request was pending ({stream_minutes} host minutes during the restream)")
    # A second request needs a surviving mismatch; wait well past the debounce.
    time.sleep(2 * DEBOUNCE_S)
    rs, hs = resync(client), resync(host)
    streams, busy = hlog.count(STREAM_LINE), hlog.count(BUSY_LINE)
    assert rs["requests"] == 1 and hs["requests"] == 1 and streams == 1 and busy == 0, (
        f"fast clock: {stream_minutes} game minutes passed during the restream "
        f"and the replica sent {rs['requests']} resync request(s); the host "
        f"served {hs['requests']}, streamed {streams} time(s) and dropped "
        f"{busy} as busy (want 1 request and 1 stream)")
    assert not rs["pending"] and not rs["gaveUp"], ("fast clock: resync guard", rs)
    sep.assert_same_world(host, client, "fast clock repaired")
    print(f"PASS fast clock: {stream_minutes} game minutes passed during the "
          f"restream, 1 request and 1 stream")


def row_soldier_stats(host, client, host_dir):
    """A soldier stat only the replica holds, with every count equal."""
    def soldier(gc):
        return sep.soldiers_at(gc, "ClientBase")[0]
    target = soldier(host)
    assert soldier(client)["id"] == target["id"], ("soldier stats precondition", target)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    hlog = EngineLog(host_dir)
    client.ok({"cmd": "set_soldier_stat", "base": "ClientBase", "id": target["id"],
               "stat": "firing", "value": target["firing"] + 7})
    assert soldier(client)["firing"] == target["firing"] + 7, "soldier stats: the drift was not made"
    repair(host, client, "soldier stats",
           lambda: soldier(client)["firing"] != soldier(host)["firing"])
    # A second restream needs a surviving mismatch; wait well past the debounce.
    time.sleep(2 * DEBOUNCE_S)
    rs, streams = resync(client), hlog.count(STREAM_LINE)
    assert rs["requests"] == 1 and streams == 1, (
        f"soldier stats: {rs['requests']} request(s) and {streams} restream(s) "
        f"(want 1 and 1)")
    print(f"PASS soldier stats: a drifted soldier stat (firing "
          f"{target['firing']}+7 on the replica) is repaired by one restream")


def main():
    # Coop_EventSync_Test supplies the event the events row schedules; with the clock paused
    # none of its scripted events fires.
    js = sep.bring_up("sep_checksum", (49071, 49072, 48371),
                      mods=[os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "mods", "Coop_EventSync_Test")])
    host, client = js.host, js.client
    failed = []
    try:
        geo.slow_clock(host, client)
        for gc in (host, client):
            gc.ok({"cmd": "geo_set_speed", "idx": 0})
        state = host.ok({"cmd": "separate_profile_state"})
        assert state["researchSharingEnabled"] is False, state
        for name, row in (("terms", row_terms), ("research", row_research), ("wallet", row_wallet),
                          ("stores", row_stores), ("projects", row_projects), ("counters", row_counters),
                          ("events", row_events),
                          ("soldier stats", lambda h, c: row_soldier_stats(h, c, js.host_dir)),
                          ("fast clock", lambda h, c: row_fast(h, c, js.host_dir))):
            try:
                row(host, client)
            except (AssertionError, TimeoutError) as e:
                failed.append(name)
                print(f"FAIL {name}: {e}")
        if not failed:
            print("PASS release: every repair released the client and left one world")
    finally:
        alive = all(gc.proc.poll() is None for gc in (host, client))
        js.shutdown()
    if not alive:
        print("FAIL: a game process died")
        sys.exit(2)
    if failed:
        print("FAIL rows: " + ", ".join(failed))
        sys.exit(1)
    print("PASS: the Separate world checksum detects and repairs per-player drift")


if __name__ == "__main__":
    main()
