"""RV-U5 S-B rows WB-C and WB-H (boot W): the "Please wait for <player>'s action to finish" line on both machines in a
classic co-op parallel-turns skirmish, the scenarios of the legacy test_coop_wait_banner (owner D229 (a) + hard gate;
design-D7; QV5-1 (a), QV5-9 (a)). OW1 is ruled (b) by design-D7: S-E's E1 enables WB4 with (b)'s value and adds
WB4-seat and WB4-clear. RED at E1: WB4, WB4-seat, WB4-clear; GREEN at E2: every cell.

Spec: docs repo rewrite/prompts/rvu5_quarantine_gate.md section (f) test_wait_cover.py, with the orchestrator ruling
R-RV5-SB-1 (WB-C's camera step) and AMENDMENT RV5-E E.8 (WB4, WB4-seat, WB4-clear). Constants:
rewrite/rvu5-task0/sb/CONSTANTS.md (TASK 0 boots Wa / Wb, re-dispatch) and rewrite/rvu5-task0/se/CONSTANTS.md (Ea / Eb).

Boot W (key 49711, dirs rv5_w_host / rv5_w_client, both user dirs battleXcomSpeed WB_SPEED): MCC.boot_seated
(BER.boot_classic with the one alien pinned AI-neutral; seats S0 [10..14] host, S1 [8, 9] client; turnMode parallel on
both). Sampling: the host's event_state.busyOwnerSeat and both machines' battle_state.coopWaitText every 0.1 s from the
order until the walk's host context is in closedContexts, then 2 s more (bounded 30 s); WB-H also reads the client's
event_state (busyOwnerSeat, lastSeqApplied) once per sample. "Inside" = a sample taken before the context closed; "the
window" = every sample, the 2 s tail included. WB-H's record window = the samples whose client lastSeqApplied lies in
[the walk's first walk_step seq, its bt_action_end seq) (host event_log; EVIDENCE only).
  WB-C  the client's walk: 8 placed on WB_C_TILE, TU 255 on both, the host's battle_camera_center on WB_C_TILE
        (R-RV5-SB-1: vanilla fast-forwards a walk off the host's screen), then the client's send_walk to WB_C_DEST.
        WB1-open   >= 3 host samples inside with busyOwnerSeat 1 (non-vacuity: the host runs the client's walk)
        WB1-text   >= 1 host sample inside == TEXT_WAIT_CLIENT
        WB2-clear  the host's text is "" within 2 s after the context closed and in every later sample
        WB5-own    no client sample in the window starts with "Please wait for "
  WB-H  the host's walk: 10 placed on WB_H_TILE, TU 255 on both, the host's TAB selection and one real-UI click.
        WB3-open   >= 3 host samples inside with the context {origin host, kind walk, actorId 10} open (non-vacuity)
        WB3-own    no host sample in the window starts with "Please wait for "
        WB4        >= 1 client sample inside == TEXT_WAIT_HOST (OW1 (b): the second player's line names the host)
        WB4-seat   >= 1 client sample inside with the client's busyOwnerSeat 0 (the attribution as data)
        WB4-clear  WB4's text seen inside, the client's text "" within 2 s after the context closed and in every later
                   sample, and the last sample's client busyOwnerSeat -1 (close path C1)
Staging per row: the walk's straight path open on both machines (floor, no wall, no object, equal per tile), no other
live unit within 3 tiles of it, X 1000000 at Chebyshev >= 20 (the pin's rule); a miss fails the row "staging".
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new crash file.

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure. A
boot step past its bound prints ONE CAPTURE line and fails both rows "boot". run in the foreground to
completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

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

W_KEY = "49711"
WB_SPEED = 100                     # battleXcomSpeed on both (TASK 0 Wa / Wb 33 / 32 inside; Ea / Eb WB-H 24 / 25)
X_ID = 1000000                     # the one alien, pinned AI-neutral
WB_C_TILE, WB_C_DEST, WB_C_DIR = (0, 0, 0), (6, 0, 0), 2   # rule: open z 0, straight 6 steps (Wa = Wb)
WB_H_TILE, WB_H_DEST, WB_H_DIR = (0, 0, 0), (0, 6, 0), 4   # same rule, 8 counted on WB_C_DEST (Wa = Wb)
TEXT_WAIT_CLIENT = "Please wait for ClientPlayer's action to finish"   # TASK 0 Wa / Wb (raw.CLIENT_PLAYER)
TEXT_WAIT_HOST = "Please wait for HostPlayer's action to finish"       # CANDIDATE (raw.HOST_PLAYER); WB4 cells
WAIT_PREFIX = "Please wait for "
NEAR, FAR_X = 3, 20                # no other unit within NEAR of the path; X at Chebyshev >= FAR_X
SAMPLE_S, TAIL_S, WINDOW_S, STEP_S = 0.1, 2.0, 30.0, 30
W_ROWS = (("WB-C", ("WB1-open", "WB1-text", "WB2-clear", "WB5-own", "WB-C-common")),
          ("WB-H", ("WB3-open", "WB3-own", "WB4", "WB4-seat", "WB4-clear", "WB-H-common")))


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
    """The pin's rule at run time: the straight path open and equal on both, no other live unit within NEAR, X far."""
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
    """Place `uid`, TU 255 on both, the path check, the host's camera (WB-C only); the host idle. Raises Miss."""
    m, tag = (host, client), "W staging"
    ev = {"place": guarded(tag, lambda: place(host, client, uid, tile, d), m)}
    ev["tu"] = guarded(tag, lambda: set_tu_both(host, client, uid, 255), m)   # clamped per boot (S25): EVIDENCE
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
    `ext` (WB-H): ONE client event_state read per sample (busyOwnerSeat, lastSeqApplied)."""
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
    """WB-H EVIDENCE: the walk's first walk_step and bt_action_end seqs (host event_log), the count of samples whose
    client lastSeqApplied lies in [first, end), and the client's distinct (t, text, busyOwnerSeat) values."""
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
    """WB2 / WB4-clear: the first tail sample from which every later `key` text is "", within TAIL_S of the close."""
    k = len(tail)
    while k > 0 and tail[k - 1][key] == "":
        k -= 1
    at = round(tail[k]["t"] - closed_at, 3) if closed_at is not None and k < len(tail) else None
    return at is not None and at <= TAIL_S, at


def row_c(host, client, crash0, staged):
    ev = dict(staged)
    inside, tail, closed_at = walk(host, client, 8, "intent", lambda: session.send_walk(client, 8, WB_C_DEST), ev)
    n_busy = sum(1 for s in inside if s["busy"] == 1)
    n_text = sum(1 for s in inside if s["host"] == TEXT_WAIT_CLIENT)
    ok_clear, at = cleared(tail, closed_at)
    own = [s for s in inside + tail if (s["client"] or "").startswith(WAIT_PREFIX)]
    return {"WB1-open": (n_busy >= 3, f"host samples inside with busyOwnerSeat 1: {n_busy} of {len(inside)} "
                                      f"(want >= 3; window {closed_at} s)"),
            "WB1-text": (n_text >= 1, f"host samples inside == {TEXT_WAIT_CLIENT!r}: {n_text} (want >= 1); host texts "
                                      f"inside {ev['insideHost']}"),
            "WB2-clear": (ok_clear, f"host text '' from {at} s after the close on (want <= {TAIL_S} s and every later "
                                    f"sample ''); tail host texts {ev['tailHost']}"),
            "WB5-own": (not own, f"client samples starting {WAIT_PREFIX!r}: {[(s['t'], s['client']) for s in own]} "
                                 f"(want none); client texts inside {ev['insideClient']}, tail {ev['tailClient']}"),
            "WB-C-common": common(host, client, crash0)}, ev


def row_h(host, client, crash0, staged):
    ev = dict(staged)

    def order():
        sel = tab_select(host, 10)
        assert sel, f"the host's TAB never selected 10 (selectedId {battle_state(host).get('selectedId')})"
        real_click_walk(host, WB_H_DEST)
        return {"tabSelect": sel}
    inside, tail, closed_at = walk(host, client, 10, "host", order, ev, ext=True)
    own = [s for s in inside + tail if (s["host"] or "").startswith(WAIT_PREFIX)]
    n_host = sum(1 for s in inside if s["client"] == TEXT_WAIT_HOST)
    n_seat = sum(1 for s in inside if s["cBusy"] == 0)
    ok_clear, at = cleared(tail, closed_at, "client")
    last_seat = (inside + tail)[-1]["cBusy"] if inside or tail else None
    return {"WB3-open": (len(inside) >= 3 and closed_at is not None,
                         f"host samples inside with the context {{host, walk, 10}} open: {len(inside)} (want >= 3; "
                         f"closed at {closed_at} s)"),
            "WB3-own": (not own, f"host samples starting {WAIT_PREFIX!r}: {[(s['t'], s['host']) for s in own]} (want "
                                 f"none); host texts inside {ev['insideHost']}, tail {ev['tailHost']}"),
            "WB4": (n_host >= 1, f"client samples inside == {TEXT_WAIT_HOST!r}: {n_host} of {len(inside)} (want >= 1); "
                                 f"client texts inside {ev['insideClient']}"),
            "WB4-seat": (n_seat >= 1, f"client samples inside with busyOwnerSeat 0: {n_seat} of {len(inside)} (want "
                                      f">= 1); client seats inside {ev['insideClientBusy']}"),
            "WB4-clear": (n_host >= 1 and ok_clear and last_seat == -1,
                          f"WB4's text seen inside {n_host} (want >= 1); client text '' from {at} s after the close on "
                          f"(want <= {TAIL_S} s and every later sample ''); last client busyOwnerSeat {last_seat} "
                          f"(want -1); tail client texts {ev['tailClient']}, seats {ev['tailClientBusy']}"),
            "WB-H-common": common(host, client, crash0)}, ev


def boot_w():
    opts = {"battleXcomSpeed": WB_SPEED}
    host = GameClient("host", None, make_user_dir("rv5_w_host", options=opts))
    client = GameClient("client", None, make_user_dir("rv5_w_client", options=opts))
    try:
        crash0 = session._crash_log_snapshot()
        try:
            guarded("W", lambda: MCC.boot_seated(host, client, W_KEY), (host, client))
        except Miss:
            return fail_all(W_ROWS, "boot (setup failure, see the CAPTURE W line)")
        rows, fails = dict(W_ROWS), 0
        for row, uid, tile, dest, d, fn in (("WB-C", 8, WB_C_TILE, WB_C_DEST, WB_C_DIR, row_c),
                                            ("WB-H", 10, WB_H_TILE, WB_H_DEST, WB_H_DIR, row_h)):
            try:
                staged = stage(host, client, uid, tile, dest, d, row == "WB-C")
            except Miss:
                fails += fail_all(((row, rows[row]),), "staging (see the CAPTURE W staging line)")
                continue
            fails += run_row(row, rows[row], lambda: fn(host, client, crash0, staged))
        return fails
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = boot_w()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_wait_cover: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
