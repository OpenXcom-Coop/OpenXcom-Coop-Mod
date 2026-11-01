"""test_wait_cover.py: the "Please wait for <player>'s action to finish" line on both machines in a classic co-op
parallel-turns skirmish. While one player's unit walks, the other player's machine shows the line naming the acting
player, the acting player's own machine never shows it, and the line clears once the walk ends. Without the client's
line for the host's actions, host_walk-client_line, host_walk-client_seat and host_walk-client_clears fail.

The boot (key 49711, dirs wait_cover_host / wait_cover_client, both user dirs battleXcomSpeed XCOM_SPEED):
MCC.boot_seated (BER.boot_classic with the one alien pinned AI-neutral; seat 0 [10..14] host, seat 1 [8, 9] client;
turnMode parallel on both). Sampling: the host's event_state.busyOwnerSeat and both machines'
battle_state.coopWaitText every 0.1 s from the order until the walk's host context is in closedContexts, then 2 s more
(bounded 30 s); host_walk also reads the client's event_state (busyOwnerSeat, lastSeqApplied) once per sample.
"Inside" = a sample taken before the context closed; "the window" = every sample, the 2 s tail included. host_walk's
record window = the samples whose client lastSeqApplied lies in [the walk's first walk_step seq, its bt_action_end
seq) (host event_log; EVIDENCE only).
  client_walk  the client's walk: 8 placed on CLIENT_WALK_TILE, TU 255 on both, the host's battle_camera_center on
      CLIENT_WALK_TILE (vanilla fast-forwards a walk off the host's screen), then the client's send_walk to
      CLIENT_WALK_DEST.
      client_walk-host_busy    >= 3 host samples inside with busyOwnerSeat 1 (non-vacuity: the host runs the client's
                               walk)
      client_walk-host_line    >= 1 host sample inside == TEXT_WAIT_CLIENT
      client_walk-host_clears  the host's text is "" within 2 s after the context closed and in every later sample
      client_walk-no_own_line  no client sample in the window starts with "Please wait for "
  host_walk  the host's walk: 10 placed on HOST_WALK_TILE, TU 255 on both, the host's TAB selection and one real-UI
      click.
      host_walk-context_open   >= 3 host samples inside with the context {origin host, kind walk, actorId 10} open
                               (non-vacuity)
      host_walk-no_own_line    no host sample in the window starts with "Please wait for "
      host_walk-client_line    >= 1 client sample inside == TEXT_WAIT_HOST (the second player's line names the host)
      host_walk-client_seat    >= 1 client sample inside with the client's busyOwnerSeat 0 (the attribution as data)
      host_walk-client_clears  host_walk-client_line's text seen inside, the client's text "" within 2 s after the
                               context closed and in every later sample, and the last sample's client busyOwnerSeat -1
                               (cleared when the walk's bt_action_end is applied)
Staging per row: the walk's straight path open on both machines (floor, no wall, no object, equal per tile), no other
live unit within 3 tiles of it, and the alien X 1000000 at Chebyshev distance >= 20 from it; a miss fails the row
"staging". Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash
file.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A
boot step past its bound prints ONE CAPTURE line and fails both rows "boot". Run in the foreground to completion. ONE
run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_wait_cover.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import test_mc_seat_coop as MCC  # noqa: E402
from test_pvp_gm3 import Miss, units, pos, es, guarded, common, run_row, fail_all, shut  # noqa: E402
from test_client_shoot import place, set_tu_both, new_contexts  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk  # noqa: E402

KEY = "49711"
XCOM_SPEED = 100                   # battleXcomSpeed on both; each walk then spans about 25-50 samples (measured)
X_ID = 1000000                     # the one alien, pinned AI-neutral
# Tile rule for both walks: open ground at z 0 and a straight 6-step path; host_walk's path is checked with 8 standing
# on CLIENT_WALK_DEST.
CLIENT_WALK_TILE, CLIENT_WALK_DEST, CLIENT_WALK_DIR = (0, 0, 0), (6, 0, 0), 2
HOST_WALK_TILE, HOST_WALK_DEST, HOST_WALK_DIR = (0, 0, 0), (0, 6, 0), 4
TEXT_WAIT_CLIENT = "Please wait for ClientPlayer's action to finish"   # on the host (repro_atom_walk.CLIENT_PLAYER)
TEXT_WAIT_HOST = "Please wait for HostPlayer's action to finish"       # on the client (repro_atom_walk.HOST_PLAYER)
WAIT_PREFIX = "Please wait for "
NEAR, FAR_X = 3, 20                # no other unit within NEAR of the path; X at Chebyshev >= FAR_X
SAMPLE_S, TAIL_S, WINDOW_S, STEP_S = 0.1, 2.0, 30.0, 30
ROWS = (("client_walk", ("client_walk-host_busy", "client_walk-host_line", "client_walk-host_clears",
                         "client_walk-no_own_line", "client_walk-common")),
        ("host_walk", ("host_walk-context_open", "host_walk-no_own_line", "host_walk-client_line",
                       "host_walk-client_seat", "host_walk-client_clears", "host_walk-common")))


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def path_of(tile, dest):
    n = cheb(tile, dest)
    dx, dy = (dest[0] - tile[0]) // max(n, 1), (dest[1] - tile[1]) // max(n, 1)
    return [(tile[0] + dx * k, tile[1] + dy * k) for k in range(n + 1)]


def parts_map(gc, path):
    xs, ys = [p[0] for p in path], [p[1] for p in path]
    r = gc.ok({"cmd": "tile_census", "x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys), "z0": 0, "z1": 0})
    return {(t["x"], t["y"]): tuple(t["parts"][p]["mapDataID"] for p in ("floor", "westwall", "northwall", "object"))
            for t in r["tiles"] if t}


def path_open(host, client, uid, tile, dest):
    """The tile rule, checked at run time: the straight path open and equal on both, no other live unit within NEAR,
    X far."""
    path = path_of(tile, dest)
    ph, pc = parts_map(host, path), parts_map(client, path)
    bad = [p for p in path
           if ph.get(p) != pc.get(p) or ph.get(p) is None or ph[p][0] == -1 or ph[p][1:] != (-1, -1, -1)]
    live = {i: (u["x"], u["y"]) for i, u in units(host).items() if not u.get("isOut") and i != uid}
    near = sorted(i for i, p in live.items() if i != X_ID and any(cheb(p, q) <= NEAR for q in path))
    xd = min(cheb(live[X_ID], q) for q in path) if X_ID in live else None
    assert not bad and not near and xd is not None and xd >= FAR_X, (
        f"path {path} not open: tiles {[(p, ph.get(p), pc.get(p)) for p in bad]} (want floor, no wall / object, "
        f"equal), units within {NEAR} {near} (want none), X Chebyshev {xd} (want >= {FAR_X})")
    return {"path": [path[0], path[-1]], "xDist": xd}


def stage(host, client, uid, tile, dest, d, camera):
    """Place `uid`, TU 255 on both, the path check, the host's camera (client_walk only); the host idle. Raises Miss."""
    m, tag = (host, client), "staging"
    ev = {"place": guarded(tag, lambda: place(host, client, uid, tile, d), m)}
    ev["tu"] = guarded(tag, lambda: set_tu_both(host, client, uid, 255), m)   # clamped per boot: EVIDENCE only
    ev["path"] = guarded(tag, lambda: path_open(host, client, uid, tile, dest), m)
    if camera:
        cam = guarded(tag, lambda: host.ok({"cmd": "battle_camera_center", "x": tile[0], "y": tile[1],
                                            "z": tile[2]}), m)
        ev["camera"] = (cam.get("centerX"), cam.get("centerY"), cam.get("centerZ"))
    guarded(tag, lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    ev["pre"] = {"hostBusy": es(host, "busyOwnerSeat"),
                 "texts": [battle_state(host).get("coopWaitText"), battle_state(client).get("coopWaitText")]}
    return ev


def sample_walk(host, client, ctx0, origin, uid, ext=False):
    """Samples every SAMPLE_S from the order until the host context {origin, walk, uid} closed, then TAIL_S more.
    `ext` (host_walk): ONE client event_state read per sample (busyOwnerSeat, lastSeqApplied)."""
    samples, t0, closed_at = [], time.time(), None
    while time.time() - t0 < WINDOW_S:
        eh, bh, bc = event_state(host), battle_state(host), battle_state(client)
        ec = event_state(client) if ext else None
        t = round(time.time() - t0, 3)
        hit = [c for c in new_contexts(ctx0, eh.get("closedContexts") or [])
               if (c.get("origin"), c.get("kind"), c.get("actorId")) == (origin, "walk", uid)]
        if hit and closed_at is None:
            closed_at = t
        samples.append({"t": t, "busy": eh.get("busyOwnerSeat"), "host": bh.get("coopWaitText"),
                        "client": bc.get("coopWaitText"), "closed": bool(hit)})
        if ext:
            samples[-1].update(cBusy=ec.get("busyOwnerSeat"), cSeq=ec.get("lastSeqApplied"))
        if closed_at is not None and t - closed_at >= TAIL_S:
            break
        time.sleep(max(0.0, SAMPLE_S * len(samples) - (time.time() - t0)))
    return samples, closed_at


def counts(samples, key):
    out = {}
    for s in samples:
        out[s[key]] = out.get(s[key], 0) + 1
    return out


def record_window(host, new, origin, uid, samples):
    """host_walk EVIDENCE: the walk's first walk_step and bt_action_end seqs (host event_log), the count of samples
    whose client lastSeqApplied lies in [first, end), and the client's distinct (t, text, busyOwnerSeat) values."""
    aid = next((c.get("actionId") for c in new
                if (c.get("origin"), c.get("kind"), c.get("actorId")) == (origin, "walk", uid)), None)
    evs = [(e.get("seq"), e.get("kind")) for e in host.cmd({"cmd": "event_log", "tail": 200}).get("events", [])
           if aid is not None and e.get("actionId") == aid]
    first = next((s for s, k in evs if k == "walk_step"), None)
    end = next((s for s, k in evs if k == "bt_action_end"), None)
    rec = [s for s in samples if first is not None and end is not None and first <= (s["cSeq"] or 0) < end]
    distinct, last = [], None
    for s in samples:
        if (s["client"], s["cBusy"]) != last:
            last = (s["client"], s["cBusy"])
            distinct.append((s["t"], s["client"], s["cBusy"]))
    return {"actionId": aid, "walkSeqs": [first, end], "recordWindow": len(rec), "clientDistinct": distinct}


def walk(host, client, uid, origin, order, ev, ext=False):
    """The order, the sampled window, the host idle; fills `ev`; returns (inside, tail, closed_at)."""
    ctx0 = es(host, "closedContexts") or []
    wp0 = [(es(gc, "walkPace") or {}).get(str(uid)) or {} for gc in (host, client)]
    ev["order"] = order()
    samples, closed_at = sample_walk(host, client, ctx0, origin, uid, ext)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    wp1 = [(es(gc, "walkPace") or {}).get(str(uid)) or {} for gc in (host, client)]
    inside = [s for s in samples if not s["closed"]]
    tail = [s for s in samples if s["closed"]]
    ev.update(closedAt=closed_at, nInside=len(inside), nTail=len(tail), pos=[pos(host, uid), pos(client, uid)],
              newCtx=[{k: c.get(k) for k in ("actionId", "origin", "kind", "actorId")}
                      for c in new_contexts(ctx0, es(host, "closedContexts") or [])],
              walkPace={gc: {k: (wp1[i].get(k) or 0) - (wp0[i].get(k) or 0) for k in ("animated", "instant")}
                        for i, gc in enumerate(("host", "client"))},
              insideBusy=counts(inside, "busy"), insideHost=counts(inside, "host"),
              insideClient=counts(inside, "client"),
              tailHost=counts(tail, "host"), tailClient=counts(tail, "client"))
    if ext:
        ev.update(insideClientBusy=counts(inside, "cBusy"), tailClientBusy=counts(tail, "cBusy"),
                  **record_window(host, ev["newCtx"], origin, uid, samples))
    return inside, tail, closed_at


def cleared(tail, closed_at, key="host"):
    """client_walk-host_clears / host_walk-client_clears: the first tail sample from which every later `key` text is
    "", within TAIL_S of the close."""
    k = len(tail)
    while k > 0 and tail[k - 1][key] == "":
        k -= 1
    at = round(tail[k]["t"] - closed_at, 3) if closed_at is not None and k < len(tail) else None
    return at is not None and at <= TAIL_S, at


def row_client_walk(host, client, crash0, staged):
    ev = dict(staged)
    inside, tail, closed_at = walk(host, client, 8, "intent", lambda: session.send_walk(client, 8, CLIENT_WALK_DEST),
                                   ev)
    n_busy = sum(1 for s in inside if s["busy"] == 1)
    n_text = sum(1 for s in inside if s["host"] == TEXT_WAIT_CLIENT)
    ok_clear, at = cleared(tail, closed_at)
    own = [s for s in inside + tail if (s["client"] or "").startswith(WAIT_PREFIX)]
    return {"client_walk-host_busy": (n_busy >= 3, f"host samples inside with busyOwnerSeat 1: {n_busy} of "
                                                   f"{len(inside)} (want >= 3; window {closed_at} s)"),
            "client_walk-host_line": (n_text >= 1, f"host samples inside == {TEXT_WAIT_CLIENT!r}: {n_text} "
                                                   f"(want >= 1); host texts inside {ev['insideHost']}"),
            "client_walk-host_clears": (ok_clear, f"host text '' from {at} s after the close on (want <= {TAIL_S} s "
                                                  f"and every later sample ''); tail host texts {ev['tailHost']}"),
            "client_walk-no_own_line": (not own, f"client samples starting {WAIT_PREFIX!r}: "
                                                 f"{[(s['t'], s['client']) for s in own]} (want none); client texts "
                                                 f"inside {ev['insideClient']}, tail {ev['tailClient']}"),
            "client_walk-common": common(host, client, crash0)}, ev


def row_host_walk(host, client, crash0, staged):
    ev = dict(staged)

    def order():
        sel = tab_select(host, 10)
        assert sel, f"the host's TAB never selected 10 (selectedId {battle_state(host).get('selectedId')})"
        real_click_walk(host, HOST_WALK_DEST)
        return {"tabSelect": sel}
    inside, tail, closed_at = walk(host, client, 10, "host", order, ev, ext=True)
    own = [s for s in inside + tail if (s["host"] or "").startswith(WAIT_PREFIX)]
    n_host = sum(1 for s in inside if s["client"] == TEXT_WAIT_HOST)
    n_seat = sum(1 for s in inside if s["cBusy"] == 0)
    ok_clear, at = cleared(tail, closed_at, "client")
    last_seat = (inside + tail)[-1]["cBusy"] if inside or tail else None
    return {"host_walk-context_open": (len(inside) >= 3 and closed_at is not None,
                                       f"host samples inside with the context {{host, walk, 10}} open: {len(inside)} "
                                       f"(want >= 3; closed at {closed_at} s)"),
            "host_walk-no_own_line": (not own, f"host samples starting {WAIT_PREFIX!r}: "
                                               f"{[(s['t'], s['host']) for s in own]} (want none); host texts inside "
                                               f"{ev['insideHost']}, tail {ev['tailHost']}"),
            "host_walk-client_line": (n_host >= 1, f"client samples inside == {TEXT_WAIT_HOST!r}: {n_host} of "
                                                   f"{len(inside)} (want >= 1); client texts inside "
                                                   f"{ev['insideClient']}"),
            "host_walk-client_seat": (n_seat >= 1, f"client samples inside with busyOwnerSeat 0: {n_seat} of "
                                                   f"{len(inside)} (want >= 1); client seats inside "
                                                   f"{ev['insideClientBusy']}"),
            "host_walk-client_clears": (n_host >= 1 and ok_clear and last_seat == -1,
                                        f"host_walk-client_line's text seen inside {n_host} (want >= 1); client text "
                                        f"'' from {at} s after the close on (want <= {TAIL_S} s and every later sample "
                                        f"''); last client busyOwnerSeat {last_seat} (want -1); tail client texts "
                                        f"{ev['tailClient']}, seats {ev['tailClientBusy']}"),
            "host_walk-common": common(host, client, crash0)}, ev


def run_boot():
    opts = {"battleXcomSpeed": XCOM_SPEED}
    host = GameClient("host", None, make_user_dir("wait_cover_host", options=opts))
    client = GameClient("client", None, make_user_dir("wait_cover_client", options=opts))
    try:
        crash0 = session._crash_log_snapshot()
        try:
            guarded("boot", lambda: MCC.boot_seated(host, client, KEY), (host, client))
        except Miss:
            return fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        rows, fails = dict(ROWS), 0
        for row, uid, tile, dest, d, fn in (
                ("client_walk", 8, CLIENT_WALK_TILE, CLIENT_WALK_DEST, CLIENT_WALK_DIR, row_client_walk),
                ("host_walk", 10, HOST_WALK_TILE, HOST_WALK_DEST, HOST_WALK_DIR, row_host_walk)):
            try:
                staged = stage(host, client, uid, tile, dest, d, row == "client_walk")
            except Miss:
                fails += fail_all(((row, rows[row]),), "staging (see the CAPTURE staging line)")
                continue
            fails += run_row(row, rows[row], lambda: fn(host, client, crash0, staged))
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_wait_cover: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
