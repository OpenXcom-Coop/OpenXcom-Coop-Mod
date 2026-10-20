"""PRD-DF02 (replicated dogfight control): any player COMMANDS a shared dogfight.

Builds on DF01 (host-sims-all + render-only replicas). A CLIENT-commanded intercept
opens the SAME fight on both machines (client = commanding seat -> both full). The
client now issues stance / weapon / disengage commands on its replica-view window;
each is emitted as a df_cmd on the reliable shared_cmd lane, applied by the host to its
authoritative DogfightState in receive-order, and surfaced back to every replica on the
next df_state frame.

Acceptance (PRD-DF02):
  1. CLIENT dogfight_action{aggressive} -> host _mode changes; next df_state reflects
     aggressive on BOTH machines.
  2. Conflicting host+client stances -> deterministic last-received-wins (the later
     command wins), both converge, no crash.
  3. CLIENT weaponToggle disables a weapon -> host + client both render it disabled
     (the fire gate reads _weaponEnabled, streamed in df_state). The client's icon follows the
     host only (owner D301 (b)): no local flip before the host's state, no flicker.
  4. Synced UFO attack-mode marker (ufoStance) renders the SAME posture on both.
  5. CLIENT minimize -> only the client's view minimizes (host window stays full).
  6. CLIENT disengage -> the fight breaks off on BOTH machines.

Run:  python tools/coop_test/test_shared_dogfight_control.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import geo

# df_state wire enum: 0 standoff, 1 cautious, 2 standard, 3 aggressive, 4 disengage.
STANDOFF, CAUTIOUS, STANDARD, AGGRESSIVE, DISENGAGE = 0, 1, 2, 3, 4
ECHO_S = 5.0   # R-CAPGEO-1: bound of AC1's wait for the host's df_state echo on the client (traced 3-6 ms after the press at
               # 2-3 ms test-server calls, inside the press call at 50 ms; cap-geo F23960). A bound, not a pace: replace it
               # only by a larger value. D301 (b): also the bound of AC3's client / host sampling after the weapon click


def _geo(gc):
    return gc.ok({"cmd": "geo_state"})


def _base0(gc):
    for b in _geo(gc)["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base in geo_state")


def _ufo(gc, ufo_id):
    for u in _geo(gc).get("ufos", []):
        if u["id"] == ufo_id:
            return u
    return None


def _df_for(gc, craft_id, ufo_id):
    return _pick_df(gc.ok({"cmd": "dogfight_state"}), craft_id, ufo_id)


def _pick_df(d, craft_id, ufo_id):
    for df in d.get("dogfights", []):
        if df["craftId"] == craft_id and df["ufoId"] == ufo_id:
            return df
    return None


def _pipelined(gc, objs):
    """Send @a objs to one game in ONE write and read their replies in order (D301 (b) AC3): the game's
    TestServer thread queues every line of the write, and its next pump runs them back to back."""
    gc.sock.sendall("".join(json.dumps(o) + "\n" for o in objs).encode())
    out = []
    for _ in objs:
        while b"\n" not in gc.buf:
            chunk = gc.sock.recv(65536)
            if not chunk:
                raise ConnectionError(f"{gc.name}: socket closed")
            gc.buf += chunk
        line, gc.buf = gc.buf.split(b"\n", 1)
        out.append(json.loads(line))
    return out


def _changes(samples):
    """D301 (b) AC3: the (ms, client, host) samples as their count plus every sample whose values differ from the one
    before it (the first and the last always shown)."""
    pts = [s for i, s in enumerate(samples) if i == 0 or i == len(samples) - 1 or s[1:] != samples[i - 1][1:]]
    return f"{len(samples)} samples, changes (ms after the click, client, host) {pts}"


def _pump(host, client, n=1):
    geo.skip_realtime(host, client, n, speed_idx=0, stuck_timeout=None)


def _wait_mode(gc, craft_id, ufo_id, want, label, host=None, client=None, tries=40):
    """Pump until this machine's dogfight reports stance @a want (or fail)."""
    last = None
    for _ in range(tries):
        df = _df_for(gc, craft_id, ufo_id)
        if df is not None:
            last = df["mode"]
            if last == want:
                return df
        if host and client:
            _pump(host, client, 1)
        time.sleep(0.15)
    raise AssertionError(f"{label}: mode never became {want} (last {last})")


def main():
    js = shared_fixture.bring_up("jdfc", (48784, 48785, 48084))
    host, client = js.host, js.client
    try:
        b0 = _base0(host)
        blon, blat = b0["lon"], b0["lat"]

        sc_h = host.ok({"cmd": "spawn_craft", "type": "STR_AVENGER",
                        "weapon": "STR_CANNON_UC"})
        sc_c = client.ok({"cmd": "spawn_craft", "type": "STR_AVENGER",
                          "weapon": "STR_CANNON_UC"})
        assert sc_h["craft_id"] == sc_c["craft_id"], "avenger ids diverged"
        avenger_id = sc_h["craft_id"]

        # A full-hull slow scout near the base: the fight persists (a non-HK intercept
        # opens in STANDOFF and does not auto-fire) so we can drive it through commands.
        ufo = host.ok({"cmd": "spawn_ufo", "type": "STR_MEDIUM_SCOUT",
                       "mission": "STR_ALIEN_RESEARCH",
                       "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID",
                       "trajectory": "P0", "state": "flying", "speed": 1,
                       "lon": blon + 0.03, "lat": blat})
        ufo_id = ufo["ufo_id"]
        print(f"setup: avenger id {avenger_id}; scout id {ufo_id}")

        # Materialise the UFO on the client, then the CLIENT commands the intercept
        # (client = commanding seat -> full window on both machines).
        deadline = time.time() + 45
        while time.time() < deadline and _ufo(client, ufo_id) is None:
            _pump(host, client, 1)
            time.sleep(0.2)
        assert _ufo(client, ufo_id) is not None, "client never materialised the UFO"
        client.ok({"cmd": "craft_order", "order": "target",
                   "craft_id": avenger_id, "craft_type": "STR_AVENGER",
                   "ufo_id": ufo_id})
        print("client commanded the intercept")

        # Both machines open the fight for the same pair.
        deadline = time.time() + 120
        while time.time() < deadline:
            _pump(host, client, 1)
            if _df_for(host, avenger_id, ufo_id) and _df_for(client, avenger_id, ufo_id):
                break
            time.sleep(0.2)
        hd = _df_for(host, avenger_id, ufo_id)
        cd = _df_for(client, avenger_id, ufo_id)
        assert hd and cd, "the intercept did not open on BOTH machines"
        # Presentation policy: a client-commanded craft -> the client IS the commanding
        # seat -> its window is FULL (not minimized); the host is always full.
        assert not cd["minimized"], "client (commanding seat) should open FULL"
        assert cd["replica"] and not hd["replica"], "replica/host role flags wrong"
        print("PASS setup: both opened; client is the commanding seat (full window)")

        # --- AC1: CLIENT issues aggressive -> host _mode changes; both converge. ------
        # The host's echo: a replica's stance button has no local flip (DogfightState.cpp btnAggressivePress
        # `if (_isReplicaView) { emitDfCmd("aggressive"); return; }`; the playtest rule in
        # test_shared_dogfight_shared.py:7-9), so the client's mode follows the host's next df_state frame.
        # R-CAPGEO-1 (cap-geo F23960, cap-battle F23982): wait, bounded, for the client's own mode, then the same check.
        client.ok({"cmd": "dogfight_action", "action": "aggressive"})
        deadline = time.time() + ECHO_S
        cd = _df_for(client, avenger_id, ufo_id)
        while (cd is None or cd["mode"] != AGGRESSIVE) and time.time() < deadline:
            time.sleep(0.02)
            cd = _df_for(client, avenger_id, ufo_id)
        assert cd["mode"] == AGGRESSIVE, \
            f"host echo failed: client mode {cd['mode']} != aggressive"
        # The host applies the df_cmd (receive-order) and streams it back.
        _wait_mode(host, avenger_id, ufo_id, AGGRESSIVE,
                   "AC1 host aggressive", host, client)
        _wait_mode(client, avenger_id, ufo_id, AGGRESSIVE,
                   "AC1 client confirm aggressive", host, client)
        print("PASS AC1: client aggressive -> host _mode aggressive, both converged")

        # --- AC2: conflicting stances -> last-received-wins. -------------------------
        # Host sets standoff (applied locally, immediately). Then the client sets
        # cautious (df_cmd, received by the host AFTER). The later command wins.
        host.ok({"cmd": "dogfight_action", "action": "standoff"})
        client.ok({"cmd": "dogfight_action", "action": "cautious"})
        _wait_mode(host, avenger_id, ufo_id, CAUTIOUS,
                   "AC2 host last-received-wins (cautious)", host, client)
        _wait_mode(client, avenger_id, ufo_id, CAUTIOUS,
                   "AC2 client converge (cautious)", host, client)
        print("PASS AC2: conflicting stances resolved last-received-wins (cautious), "
              "both converged")

        # --- AC4: synced UFO attack-mode marker parity (check while the fight lives). -
        hd = _df_for(host, avenger_id, ufo_id)
        cd = _df_for(client, avenger_id, ufo_id)
        assert hd["ufoStance"] == cd["ufoStance"], (
            f"PRD-DF02 FAILED: ufoStance marker diverged host={hd['ufoStance']} "
            f"client={cd['ufoStance']}")
        print(f"PASS AC4: synced UFO stance marker parity (ufoStance="
              f"{hd['ufoStance']} on both)")

        # --- AC3: CLIENT weaponToggle -> weapon disabled on host + client. -----------
        hd = _df_for(host, avenger_id, ufo_id)
        assert hd["weaponEnabled"] and hd["weaponEnabled"][0], \
            f"weapon 0 not initially enabled on host: {hd['weaponEnabled']}"
        # D301 (b): the client's weapon icon follows the host only, like the stance buttons (a click only sends the request;
        # the icon changes when the host's df_state shows it). The click and the client's first probe go out in ONE send,
        # so the client runs both in the same TestServer pump, before its network drain (Game.cpp: pump() then
        # updateCoopTask()): that probe reads the icon as the click itself left it, before any host frame reached the
        # client. A probe sent after the click's reply comes after that drain, where a host frame sent before the host had
        # the request already undid a local flip (cap-battle F23985). Then client and host are probed in turn (the host
        # right after the client) until both show disabled, bound ECHO_S. (i) No local flip: the client never shows
        # disabled while the host read right after it is still enabled. (ii) No flicker: once the client shows disabled
        # it never shows enabled again.
        t0 = time.time()
        r_click, cd = _pipelined(client, [
            {"cmd": "dogfight_action", "action": "weaponToggle", "arg": 0},
            {"cmd": "dogfight_state"}])
        assert r_click.get("ok"), f"client weaponToggle failed: {r_click.get('error')}"
        cd = _pick_df(cd, avenger_id, ufo_id)
        samples = []  # (ms after the click, client weaponEnabled[0], host weaponEnabled[0] read right after it)
        deadline = t0 + ECHO_S
        while True:
            hd = _df_for(host, avenger_id, ufo_id)
            c0 = cd["weaponEnabled"][0] if cd and cd["weaponEnabled"] else None
            h0 = hd["weaponEnabled"][0] if hd and hd["weaponEnabled"] else None
            samples.append((round((time.time() - t0) * 1000.0, 1), c0, h0))
            if (c0 is False and h0 is False) or time.time() >= deadline:
                break
            cd = _df_for(client, avenger_id, ufo_id)
        trace = _changes(samples)
        early = [s for s in samples if s[1] is False and s[2] is True]
        assert not early, (
            f"D301 (b) FAILED: the client's weapon icon showed disabled before the host's state did (a local flip; the icon "
            f"must follow the host only): first at +{early[0][0]} ms; {trace}")
        first_off = next((i for i, s in enumerate(samples) if s[1] is False), None)
        reverted = [s for s in samples[first_off:] if s[1] is not False] if first_off is not None else []
        assert not reverted, (
            f"D301 (b) FAILED: the client's weapon icon showed enabled again after it showed disabled (flicker): first at "
            f"+{reverted[0][0]} ms; {trace}")
        print(f"D301 (b) AC3 {trace}")
        # host applies + streams; both settle disabled
        ok = False
        for _ in range(40):
            _pump(host, client, 1)
            hd = _df_for(host, avenger_id, ufo_id)
            cd = _df_for(client, avenger_id, ufo_id)
            if hd and cd and hd["weaponEnabled"][0] is False and cd["weaponEnabled"][0] is False:
                ok = True
                break
            time.sleep(0.15)
        assert ok, (f"PRD-DF02 FAILED: weaponToggle did not disable weapon 0 on both "
                    f"(host={hd['weaponEnabled']} client={cd['weaponEnabled']})")
        print("PASS AC3: client weaponToggle disabled weapon 0 on host AND client "
              "(host fire gate reads _weaponEnabled)")

        # --- AC5: CLIENT minimize is view-only (host window stays full). -------------
        client.ok({"cmd": "dogfight_action", "action": "minimize"})
        _pump(host, client, 2)
        cd = _df_for(client, avenger_id, ufo_id)
        hd = _df_for(host, avenger_id, ufo_id)
        assert cd and cd["minimized"], "client view did not minimize"
        assert hd and not hd["minimized"], (
            "PRD-DF02 FAILED: host window minimized from a client-local minimize "
            "(minimize must be per-machine VIEW state)")
        print("PASS AC5: client minimize is local-only; host window stays full "
              "(world clock stays host-gated)")

        # --- AC6: CLIENT disengage -> the fight breaks off on BOTH. ------------------
        client.ok({"cmd": "dogfight_action", "action": "disengage"})
        host_diseng = client_diseng = False
        for _ in range(40):
            _pump(host, client, 1)
            hd = _df_for(host, avenger_id, ufo_id)
            cd = _df_for(client, avenger_id, ufo_id)
            if hd and hd["disengaging"]:
                host_diseng = True
            if cd and cd["disengaging"]:
                client_diseng = True
            # once the fight closes on both, the break-off is complete
            if host_diseng and client_diseng:
                break
            if hd is None and cd is None and host_diseng:
                client_diseng = True  # both windows already closed after break-off
                break
            time.sleep(0.15)
        assert host_diseng, "PRD-DF02 FAILED: host did not break off on client disengage"
        assert client_diseng, "PRD-DF02 FAILED: client did not reflect disengage"
        print("PASS AC6: client disengage broke the fight off on BOTH machines")

        js.finish()
        print("ALL SHARED DOGFIGHT CONTROL TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
