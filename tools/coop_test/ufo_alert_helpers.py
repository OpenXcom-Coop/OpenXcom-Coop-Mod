"""ufo_alert_helpers.py: the UFO-alert steps shared by the hyper-wave alert tests (issue #183).

A Shared or Separate campaign is ONE host-authoritative world. The host simulates it, radar
detection included, and announces each new detection with the reliable ufo_popup packet that
the UfoDetectedState ctor sends (type, race, ufo_id, hyperDetected). The client is a
simulation-frozen replica: it raises its own UFO window for the UFO with that id and otherwise
mirrors the host's UFOs from the host's position snapshot (target_positions, shared:true).

Everything is asserted through what the harness reports of each machine:
  screen_state   the UFO window on top ("ufo_detected"), whether it was built with the
                 hyper-wave details (craft type, race, mission, zone) and which UFO it shows
                 (ufoId / ufoCoopId);
  geo_state      every UFO's detected / hyperDetected flags. A replica's flags must equal the
                 host's.

run_hyperwave_scenarios runs, in ONE bring-up, one UFO per scenario:
  hyperwave_alert     the host raises a hyper-wave alert -> the client's window is the hyper-wave
                      one, and the client's UFO is hyper-wave detected like the host's.
  conventional_alert  the host raises a conventional alert -> the client's window is the
                      conventional one, and the client's UFO is not hyper-wave detected.
  stale_flag          hyper-wave alert; the host loses the UFO (detected and hyperDetected
                      cleared, as GeoscapeState::ufoDetection does out of radar cover); once the
                      client shows it undetected the host re-detects it conventionally -> the
                      client's fresh window is the conventional one AND the client's UFO is no
                      longer hyper-wave detected (it matches the host).
  gained_later        conventional alert, window closed; the host's decoder then decodes the
                      tracked UFO without a window (ufoDetection's already-tracked branch) ->
                      the client's UFO becomes hyper-wave detected, and no window opens.

Determinism. Both clocks run at the slowest step (geo.slow_clock), and the host's radar sweep
(ufoDetection, every 30 game minutes) runs whenever both players are on the geoscape. Every UFO here is spawned on the HOST ONLY, beside the host's base,
inside its starting small radar's cover, and reaches the client through the snapshot (so the
client's UFO is a real replica, never a copy the client made itself). A UFO radar already
tracks stays tracked there (the tracked check is a certainty), and the starting base has no
hyper-wave decoder, so the sweep never changes a tracked UFO's flags. The one untracked
stretch, stale_flag's lost UFO, is run while the client's previous UFO window is still open:
an open window on the client holds the host's clock (test_popup_clock), so no sweep can
re-detect the UFO behind the test's back. The snapshot keeps flowing meanwhile, so the
client's flags still follow the host's. spawn_ufo's throwaway missions are in North America,
far from every base, so a wave UFO one of them launches at a 30-minute mark stays off radar
(display id 0, never alerted) and cannot raise a window of its own.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo

UFO = dict(type="STR_MEDIUM_SCOUT", mission="STR_ALIEN_RESEARCH",
           region="STR_NORTH_AMERICA", race="STR_SECTOID",
           trajectory="P0", state="flying", speed=1)

WAIT_S = 30       # a UFO replicating, a UFO window opening
CONVERGE_S = 15   # a replica's flag reaching the host's value
SETTLE_S = 1.0    # a converged flag is read again after this, so a value that only passes by fails
HOLD_GRACE_S = 1.5  # > the host's 1000 ms grace for a stopped client heartbeat (GeoscapeState::timeAdvance)
POLL_S = 0.25


# ---- reads ----------------------------------------------------------------

def find_ufo(gc, **match):
    """The first geo_state UFO entry of `gc` whose fields equal every item of `match`, else None."""
    for u in gc.ok({"cmd": "geo_state"})["ufos"]:
        if all(u.get(k) == v for k, v in match.items()):
            return u
    return None


def wait_ufo(gc, label, timeout=CONVERGE_S, **match):
    """Wait until find_ufo(gc, **match) finds an entry and return it. `match` names the UFO
    (id=... or coopId=...) and the flags it must hold (detected=..., hyperDetected=...)."""
    deadline = time.time() + timeout
    while True:
        found = find_ufo(gc, **match)
        if found:
            return found
        if time.time() >= deadline:
            key = {k: v for k, v in match.items() if k in ("id", "coopId")}
            raise AssertionError(f"{gc.name}: {label}: no UFO holding {match} within {timeout}s "
                                 f"(the UFO now: {find_ufo(gc, **key) if key else None})")
        time.sleep(POLL_S)


def ufo_window(gc):
    """The screen_state reply of `gc` while a UFO window (UfoDetectedState) is on top, else None."""
    state = gc.ok({"cmd": "screen_state"})
    return state if state.get("top") == "ufo_detected" else None


def wait_ufo_window(gc, label, timeout=WAIT_S, **match):
    """Wait for a UFO window on top of `gc` whose screen_state fields equal every item of
    `match` (ufoId=... / ufoCoopId=...), and return its screen_state."""
    def shown():
        window = ufo_window(gc)
        if window and all(window.get(k) == v for k, v in match.items()):
            return window
        return None
    return gc.wait_for(label, shown, timeout=timeout, interval=POLL_S)


# ---- actions --------------------------------------------------------------

def close_window(gc, ufo_id, label):
    """Close the UFO window for display id `ufo_id` on top of `gc` (its Cancel button)."""
    window = ufo_window(gc)
    assert window and window.get("ufoId") == ufo_id, \
        f"{label}: {gc.name} shows no UFO window for UFO {ufo_id} to close (screen_state={window})"
    closed = gc.ok({"cmd": "dismiss_popup"})
    assert closed.get("handled") == "UfoDetectedState", f"{label}: {closed}"


def close_ufo_windows(gc, seconds=2.0):
    """After a failed scenario: close every UFO window that is or comes on top of `gc` within
    `seconds`, so the next scenario starts on the geoscape."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if ufo_window(gc):
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.2)


def spawn_host_ufo(host, client, base_name, offset):
    """A detected flying UFO spawned on the HOST ONLY at `base_name`'s position + `offset`
    (inside the base's radar cover). Waits until the client's replica of it, arrived through
    the host's snapshot, shows that display id detected. Returns the display id."""
    base = next(b for b in host.ok({"cmd": "geo_state"})["bases"] if b["name"] == base_name)
    spawned = host.ok({"cmd": "spawn_ufo", **UFO,
                       "lon": base["lon"] + offset[0], "lat": base["lat"] + offset[1]})
    ufo_id = spawned["ufo_id"]
    wait_ufo(client, f"the client's replica of the host's UFO {ufo_id}", timeout=WAIT_S,
             id=ufo_id, detected=True)
    return ufo_id


def alert(host, ufo_id, hyperwave):
    """The host raises its new-UFO alert for `ufo_id` (ufo_alert: the ufo_popup broadcast)."""
    sent = host.ok({"cmd": "ufo_alert", "ufo_id": ufo_id, "hyperwave": hyperwave})
    assert sent["ufo_id"] == ufo_id and sent["hyperDetected"] is hyperwave, sent
    return sent


def set_detection(host, ufo_id, **flags):
    """The host changes the UFO's radar flags without a window (set_ufo_detection) and the
    flags must hold afterwards."""
    done = host.ok({"cmd": "set_ufo_detection", "ufo_id": ufo_id, **flags})
    for k, v in flags.items():
        assert done[k] is v, f"host set_ufo_detection {flags}: {done}"
    return done


def assert_replica_hyper(host, client, ufo_id, expect, label):
    """The host's UFO is hyper-wave detected exactly when `expect`, and the client's replica
    reaches the host's value within CONVERGE_S and still holds it SETTLE_S later."""
    h = find_ufo(host, id=ufo_id)
    assert h and h["hyperDetected"] is expect, f"{label}: host UFO {ufo_id}: {h}"
    wait_ufo(client, f"{label}: client UFO {ufo_id} hyperDetected == host's ({expect})",
             id=ufo_id, hyperDetected=h["hyperDetected"])
    time.sleep(SETTLE_S)
    c = find_ufo(client, id=ufo_id)
    assert c and c["hyperDetected"] == h["hyperDetected"], \
        f"{label}: client UFO {ufo_id} did not keep the host's hyperDetected: host={h} client={c}"


# ---- scenarios ------------------------------------------------------------

def hyperwave_alert(host, client, ufo_id, label):
    alert(host, ufo_id, True)
    window = wait_ufo_window(client, f"{label}: client UFO window", ufoId=ufo_id)
    assert window["hyperwave"] is True, f"{label}: client window is the conventional one: {window}"
    assert_replica_hyper(host, client, ufo_id, True, label)
    close_window(client, ufo_id, label)


def conventional_alert(host, client, ufo_id, label):
    alert(host, ufo_id, False)
    window = wait_ufo_window(client, f"{label}: client UFO window", ufoId=ufo_id)
    assert window["hyperwave"] is False, f"{label}: client window is the hyper-wave one: {window}"
    assert_replica_hyper(host, client, ufo_id, False, label)
    close_window(client, ufo_id, label)


def stale_flag(host, client, ufo_id, label):
    alert(host, ufo_id, True)
    first = wait_ufo_window(client, f"{label}: client hyper-wave UFO window", ufoId=ufo_id)
    assert first["hyperwave"] is True, f"{label}: first client window: {first}"
    # The first window stays open until the UFO is tracked again: it holds the host's clock,
    # so no radar sweep runs while the UFO is untracked. Its hold reaches the host at once
    # (the client's heartbeat / focus) and at the latest when the host's grace for a stopped
    # client heartbeat runs out, so wait that long before the UFO goes untracked.
    time.sleep(HOLD_GRACE_S)
    set_detection(host, ufo_id, detected=False, hyperDetected=False)
    lost = wait_ufo(client, f"{label}: client shows the lost UFO undetected", id=ufo_id,
                    detected=False)
    print(f"EVIDENCE {label}: client UFO while lost: {lost}", flush=True)
    set_detection(host, ufo_id, detected=True)
    alert(host, ufo_id, False)
    wait_ufo(client, f"{label}: client shows the UFO detected again", id=ufo_id, detected=True)
    # Close the first window; the re-detection's window must be a fresh one.
    close_window(client, ufo_id, label)
    fresh = wait_ufo_window(client, f"{label}: client UFO window for the re-detection",
                            ufoId=ufo_id)
    assert fresh["hyperwave"] is False, \
        f"{label}: client window for a conventional re-detection is the hyper-wave one: {fresh}"
    assert_replica_hyper(host, client, ufo_id, False, label)
    close_window(client, ufo_id, label)


def gained_later(host, client, ufo_id, label):
    alert(host, ufo_id, False)
    window = wait_ufo_window(client, f"{label}: client UFO window", ufoId=ufo_id)
    assert window["hyperwave"] is False, f"{label}: client window: {window}"
    close_window(client, ufo_id, label)
    set_detection(host, ufo_id, hyperDetected=True)
    assert_replica_hyper(host, client, ufo_id, True, label)
    assert ufo_window(client) is None, \
        f"{label}: decoding a tracked UFO opened a UFO window on the client: {ufo_window(client)}"


# one UFO per scenario, each at its own offset from the host's base (radians; all well inside
# the starting small radar's 1695 nautical miles, about 0.49 rad)
SCENARIOS = (
    ("hyperwave_alert", hyperwave_alert, (0.03, 0.02)),
    ("conventional_alert", conventional_alert, (0.05, 0.02)),
    ("stale_flag", stale_flag, (0.03, 0.05)),
    ("gained_later", gained_later, (0.05, 0.05)),
)


def run_hyperwave_scenarios(host, client, mode, base_name="HostBase"):
    """Spawn one host-only UFO per scenario beside `base_name`, then run every scenario in
    order. A failed scenario prints FAIL, closes the client's UFO windows and the next one
    still runs. Returns the names of the failed scenarios."""
    geo.slow_clock(host, client)
    ids = [spawn_host_ufo(host, client, base_name, offset) for _, _, offset in SCENARIOS]
    print(f"PASS {mode} setup: host-only UFOs {ids} replicated to the client, detected", flush=True)
    failed = []
    for (name, scenario, _), ufo_id in zip(SCENARIOS, ids):
        label = f"{mode} {name}"
        try:
            scenario(host, client, ufo_id, label)
            print(f"PASS {label}", flush=True)
        except (AssertionError, TimeoutError) as e:
            print(f"FAIL {label}: {e}", flush=True)
            failed.append(name)
            close_ufo_windows(client)
    return failed


def report(mode, failed):
    """The summary line and the exit code: 0 when every scenario passed, else 2."""
    if failed:
        print(f"FAILED {mode} hyper-wave UFO alert scenarios: {failed}", flush=True)
        sys.exit(2)
    print(f"ALL {mode} HYPER-WAVE UFO ALERT SCENARIOS PASSED", flush=True)
