"""Separate campaign: the world checksum covers every player's private state.

The Separate campaign is one host-owned world. Each player's wallet and private
research live in that player's profile inside the world. The host stamps a world
checksum on its geoscape `time` heartbeat; a replica whose world drifts from it
asks for a fresh world (the same restream as the SHARED desync repair).

The checksum used to compare only the global research list and each machine's
OWN wallet, so drift in a private research profile or in the other player's
wallet was never detected or repaired.

Rows (vanilla rules, private research, clock paused):
  C1 terms    at rest the host and the client compute the same checksum,
              including one wallet and one research count per player (no false
              positive: the replica logged no mismatch).
  C2 research the replica's ClientPlayer profile gains a topic the host world
              does not have. The replica detects it, asks for a resync, and its
              profile equals the host's again.
  C3 wallet   the replica's copy of the OTHER player's wallet (HostPlayer) is
              changed. The replica detects it, asks for a resync, and both
              wallets equal the host's again.
  C4 release  after each repair the client is not parked in the resume hold and
              the whole world is identical on both machines.

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
    assert "chkPlayerFunds" in h and "chkPlayerResearch" in h, ("C1 no player terms", h)
    assert set(h["chkPlayerFunds"]) == {"HostPlayer", "ClientPlayer"}, ("C1 wallets", h)
    assert set(h["chkPlayerResearch"]) == {"HostPlayer", "ClientPlayer"}, ("C1 research", h)
    assert h == c, ("C1 host and client checksums differ at rest", h, c)
    # The bring-up may count mismatching heartbeats while the client still holds
    # its own pre-campaign world, but it must never ask for a repair.
    rs = resync(client)
    assert rs["requests"] == 0, ("C1 bring-up asked for a resync", rs)
    client.ok({"cmd": "shared_reset_resync_stats"})
    time.sleep(2 * DEBOUNCE_S)
    rs = resync(client)
    assert rs["mismatches"] == 0 and rs["requests"] == 0, ("C1 false positive at rest", rs)
    print(f"PASS C1 terms: identical checksum on both machines, no mismatch at rest {h}")


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
    assert DRIFT_TOPIC not in host_view["ClientPlayer"][1], ("C2 precondition", host_view)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    r = client.ok({"cmd": "separate_profile_set", "player": "ClientPlayer",
                   "research": DRIFT_TOPIC})
    assert r.get("researchAdded"), ("C2 drift not made", r)
    assert profiles(client) != host_view, "C2 the replica did not drift"
    repair(host, client, "C2 research",
           lambda: DRIFT_TOPIC in profiles(client)["ClientPlayer"][1])
    assert profiles(client) == host_view, ("C2", host_view, profiles(client))
    print("PASS C2 research: a drifted private research profile is repaired")


def row_wallet(host, client):
    host_view = profiles(host)
    assert host_view["HostPlayer"][0] != BOGUS_FUNDS, ("C3 precondition", host_view)
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_resync_stats"})
    r = client.ok({"cmd": "set_funds", "player": "HostPlayer", "value": BOGUS_FUNDS})
    assert profiles(client)["HostPlayer"][0] == BOGUS_FUNDS, ("C3 drift not made", r)
    repair(host, client, "C3 wallet",
           lambda: profiles(client)["HostPlayer"][0] == BOGUS_FUNDS)
    assert profiles(client) == host_view, ("C3", host_view, profiles(client))
    print("PASS C3 wallet: a drifted wallet of the other player is repaired")


def main():
    js = sep.bring_up("sep_checksum", (49071, 49072, 48371))
    host, client = js.host, js.client
    failed = []
    try:
        geo.slow_clock(host, client)
        for gc in (host, client):
            gc.ok({"cmd": "geo_set_speed", "idx": 0})
        state = host.ok({"cmd": "separate_profile_state"})
        assert state["researchSharingEnabled"] is False, state
        for name, row in (("C1", row_terms), ("C2", row_research), ("C3", row_wallet)):
            try:
                row(host, client)
            except (AssertionError, TimeoutError) as e:
                failed.append(name)
                print(f"FAIL {name}: {e}")
        if not failed:
            print("PASS C4 release: every repair released the client and left one world")
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
