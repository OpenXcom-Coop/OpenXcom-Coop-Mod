"""R5-U6 S-B rows FC1, FC2 (boot BC, classic co-op: the client commands soldiers 8 and 9, the host the other five) with
the HOST's "Enable Other Player Footstep Sounds" off and its "Enable Reaction Fire in PvP" off (its options.cfg
`EnableOtherPlayerFootsteps: false`, `EnableReactionFirePvp: false`; the client keeps the defaults): the partner's walk
makes no step sound and no "start moving" voice on this machine, each machine hears its own walks, and the PvP option
never touches co-op reaction fire (owner D236 (b); QU6-2 (a): the host's value on both machines; QU6-3 (a); QU6-5 (a):
the client's walk ghost plays vanilla's step sounds and the start voice).

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md section (f) test_footsteps.py, AMENDMENT U6-1 (U6-1.3, U6-1.7) and
the orchestrator ruling R-U6-SB-1. Constants: rewrite/r5u6-task0/sb/CONSTANTS.md (TASK 0 boots BCa = BCb on the probe build).
Probe: event_state.walkSounds {walker id: {steps, stepsSilenced, voices, voicesSilenced}} (TEST-ONLY, TB1-TB5): one entry
per walk-sound decision this machine made (a step-sound phase past vanilla's sight / screen gate, or a start voice).
D(gc, uid) = that entry after the row minus before (missing = all 0), read after the client's walk ghost drained.

Boot BC (key 49061): test_reaction_prox's bring-up (roster seed 1, map seed 1, seat_count 2, pin_ai_neutral, every
player unit's reactions 0), copied with the key as a parameter.
  FC1  the partner's walk is silent on the host; the client hears its own: A on C8_A_TILE facing 4, C (8) on C8_C_TILE
       facing 0, one END TURN cycle, A reactions 100 and TU A_TU (refill); both cameras on (16,7,0); host set_seed
       SEED_C8; the client's send_walk of C to C8_DEST.
       FC1-react  one `reaction` context by A nested in C's walk (the PvP option never touches co-op)
       FC1-host   D(host, C): stepsSilenced > 0 and steps 0
       FC1-hvoice D(host, C): voicesSilenced 1, voices 0
       FC1-own    D(client, C): steps > 0, stepsSilenced 0
       FC1-ovoice D(client, C): voices 1
  FC2  the host's walk is silent on the client: H (10) on FC2_TILE facing 2; both cameras on FC2's first step tile; the
       host TABs to H; the host's real-UI walk to FC2_DEST.
       FC2-own    D(host, 10): steps > 0, stepsSilenced 0
       FC2-client D(client, 10): stepsSilenced > 0 and steps 0
       FC2-cvoice D(client, 10): voicesSilenced 1, voices 0
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: contexts, executed paths, the walker on both machines, cameras, visibility, ghost counters.

RED on the probe build (commit B1): FC1-host, FC1-hvoice, FC1-own, FC1-ovoice, FC2-client, FC2-cvoice; every other cell
PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot
step past its bound prints ONE CAPTURE line and fails every row "boot"; a staging step that fails fails its row's cells.
WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2. test_footsteps_pvp.py imports this file's helpers.

Run:  python tools/coop_test/test_footsteps.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_reaction_prox as RPX  # noqa: E402
from test_seat_pacing import tab_select, real_click_walk  # noqa: E402
from test_client_shoot import new_contexts, place  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import end_turn_cycle, bring_up_lobby_roster_pinned  # noqa: E402
from test_delta_core import both  # noqa: E402

KEY = "49061"
HOST_OPTIONS = {"EnableOtherPlayerFootsteps": False, "EnableReactionFirePvp": False}   # the client keeps its defaults
A_ID, C_ID, H_ID = RPX.A_ID, RPX.C_ID, 10      # the only alien (pinned); the client's walker; the host's walker
SEED_C8 = RPX.SEED_C8                         # 3: two of A's three snaps hit C (40 -> 21), C standing (BCa = BCb)
FC1_FIRST = (16, 7, 0)                        # C's first step tile (C8_EXECUTED), both cameras centred on it
FC2_TILE, FC2_DIR = (7, 38, 0), 2             # TASK 0 (rule (d) T0-3 (3)): open ground, Chebyshev >= 21 from A
FC2_DEST = (9, 38, 0)                         # two steps east, executed [(8,38,0), (9,38,0)] (BCa = BCb)
FC2_FIRST = (8, 38, 0)
STEP_S, GHOST_S = 30, 10                      # every bounded wait; the client's ghost drain (TASK 0: 0.05 s)
SOUND_KEYS = ("steps", "stepsSilenced", "voices", "voicesSilenced")
ROWS = (("FC1", ("FC1-react", "FC1-host", "FC1-hvoice", "FC1-own", "FC1-ovoice", "FC1-common")),
        ("FC2", ("FC2-own", "FC2-client", "FC2-cvoice", "FC2-common")))


# ===================== shared helpers (test_footsteps_pvp imports them) =====================


def es(gc, key):
    return event_state(gc).get(key)


def cv(c):
    return {k: c.get(k) for k in ("actionId", "origin", "kind", "actorId", "nestedIn")}


def pts(seq):
    return [(p.get("x"), p.get("y"), p.get("z")) for p in (seq or [])]


def uview(gc, uid):
    u = G3F.units(gc).get(uid) or {}
    return {k: u.get(k) for k in ("x", "y", "z", "direction", "tu", "energy", "health", "isOut", "reactions", "visible",
                                  "visibleHere")}


def walk_view(gc):
    w = es(gc, "lastWalk") or {}
    return {"actionId": w.get("actionId"), "executed": pts(w.get("executed")), "halted": w.get("halted"),
            "reason": w.get("reason"), "enAfter": [s.get("enAfter") for s in (w.get("steps") or [])],
            "tuAfter": [s.get("tuAfter") for s in (w.get("steps") or [])]}


def sounds(gc):
    return es(gc, "walkSounds") or {}


def delta(before, after, uid):
    b, a = before.get(str(uid)) or {}, after.get(str(uid)) or {}
    return {k: a.get(k, 0) - b.get(k, 0) for k in SOUND_KEYS}


def ghost(gc):
    e = event_state(gc)
    return {k: e.get(k) for k in ("ghostEnqueued", "ghostCompleted", "ghostQueueDepth")}


def ghost_drained(gc):
    g = ghost(gc)
    return g["ghostQueueDepth"] == 0 and g["ghostCompleted"] == g["ghostEnqueued"]


def cameras(host, client, tile):
    """battle_camera_center on BOTH machines (client first) on the walk's first step tile; returns both replies."""
    got = {}
    for gc in (client, host):
        r = gc.cmd({"cmd": "battle_camera_center", "x": tile[0], "y": tile[1], "z": tile[2]})
        assert r.get("ok"), f"staging: battle_camera_center {tile} on {gc.name}: {r}"
        got[gc.name] = (r.get("centerX"), r.get("centerY"), r.get("centerZ"), r.get("viewLevel"))
    return got


def staged(what, fn):
    """A staging step: its failure fails the row's cells with `staging: ...`."""
    try:
        return fn()
    except Exception as e:
        raise RuntimeError(f"staging ({what}): {type(e).__name__}: {str(e)[:400]}")


def watched_walk(host, client, uid, first, order, ev):
    """Both cameras on `first`, the walkSounds baselines, `order()`, then the walk settled (a NEW host restate, the
    client caught up), the host idle and the client's walk ghost drained (bounded). Returns (new host contexts, D)."""
    ev["cameras"] = staged("cameras", lambda: cameras(host, client, first))
    ws0 = {"host": sounds(host), "client": sounds(client)}
    seq0, ctx0, prev = es(host, "lastSeqEmitted") or 0, RM.ctxs(host), session.walk_action_id(host)
    sent0 = dict(es(client, "coopIntentsSent") or {})
    before = uview(host, uid)
    ev["order"] = order()
    try:
        session.wait_walk_settled(host, client, prev, timeout=STEP_S)
    except Exception as e:
        ev["walkError"] = str(e)[:200]
    RM.settle(host, client, ev)
    ev["ghostDrain"] = RM.wait_until(lambda: ghost_drained(client), GHOST_S, 0.1)
    ws1 = {"host": sounds(host), "client": sounds(client)}
    d = {gc: delta(ws0[gc], ws1[gc], uid) for gc in ("host", "client")}
    new = new_contexts(ctx0, RM.ctxs(host))
    hw = walk_view(host)
    en = [before.get("energy")] + hw["enAfter"]
    ev.update(D=d, newCtx=[cv(c) for c in new], hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in evs_since(host, seq0)],
              lastWalk=[hw, walk_view(client)], walkerBefore=before, walker=[uview(host, uid), uview(client, uid)],
              energyPerStep=[a - b for a, b in zip(en, en[1:])] if None not in en else None,
              intentsSent=(es(client, "coopIntentsSent") or {}).get("walk", 0) - sent0.get("walk", 0),
              cameraAfter={gc.name: es(gc, "camera") for gc in (host, client)}, ghost=ghost(client))
    return new, d


def ctx_of(new, origin, kind, actor):
    return [c for c in new if (c.get("origin"), c.get("kind"), c.get("actorId")) == (origin, kind, actor)]


def silenced_cell(d, who, uid):
    return (d["stepsSilenced"] > 0 and d["steps"] == 0,
            f"D({who}, {uid}) {d} (want stepsSilenced > 0 and steps 0)")


def heard_cell(d, who, uid, silenced_zero=True):
    ok = d["steps"] > 0 and (not silenced_zero or d["stepsSilenced"] == 0)
    return (ok, f"D({who}, {uid}) {d} (want steps > 0{', stepsSilenced 0' if silenced_zero else ''})")


def voice_silenced_cell(d, who, uid):
    return (d["voicesSilenced"] == 1 and d["voices"] == 0, f"D({who}, {uid}) {d} (want voicesSilenced 1, voices 0)")


def voice_heard_cell(d, who, uid):
    return (d["voices"] == 1, f"D({who}, {uid}) {d} (want voices 1)")


def react_cell(new, walk_origin, walker, reactor):
    walks = ctx_of(new, walk_origin, "walk", walker)
    reacts = [c for c in new if c.get("kind") == "reaction" and c.get("actorId") == reactor]
    ok = len(walks) == 1 and len(reacts) == 1 and reacts[0].get("nestedIn") == walks[0].get("actionId")
    return (ok, f"new host contexts {[cv(c) for c in new]} (want one {{{walk_origin}, walk, {walker}}} and exactly one "
                f"reaction by {reactor} nested in it)")


def host_click_walk(host, uid, dest, alt=False):
    """The host's real-UI walk of `uid`: TAB onto it (asserted), [the Alt latch], HOME + one self-verified click."""
    assert tab_select(host, uid), f"staging: TAB never selected {uid} on the host " \
                                  f"(selectedId {battle_state(host).get('selectedId')})"
    if not alt:
        real_click_walk(host, dest)
        return {"tab": True}
    r = {"tab": True, "alt": host.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "alt"})}
    try:
        real_click_walk(host, dest)
    finally:
        r["none"] = host.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    return r


# ===================== rows =====================


def row_fc1(host, client, crash0):
    ev = {}
    staged("tiles", lambda: (RPX.tele_both(host, client, A_ID, RPX.C8_A_TILE, RPX.C8_A_DIR),
                             RPX.tele_both(host, client, C_ID, RPX.C8_C_TILE, RPX.C8_C_DIR)))
    notes = []
    ev["turn0"] = end_turn_cycle(host, client, None, notes)
    ev["turnSide"] = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    if notes or ev["turnSide"] != [(ev["turn0"] + 1, RPX.FACTION_PLAYER)] * 2:
        raise RuntimeError(f"staging (END TURN cycle): notes {notes}, (turn, side) {ev['turnSide']}")
    staged("A", lambda: (RM.stat_both(host, client, A_ID, "reactions", RPX.A_REACTIONS),
                         RM.stat_both(host, client, A_ID, "tu", RPX.A_TU, refill=True)))
    ev["A"] = [uview(host, A_ID), uview(client, A_ID)]

    def order():
        host.ok({"cmd": "set_seed", "seed": SEED_C8})
        return session.send_walk(client, C_ID, RPX.C8_DEST)

    new, d = watched_walk(host, client, C_ID, FC1_FIRST, order, ev)
    cells = {"FC1-react": react_cell(new, "intent", C_ID, A_ID),
             "FC1-host": silenced_cell(d["host"], "host", C_ID),
             "FC1-hvoice": voice_silenced_cell(d["host"], "host", C_ID),
             "FC1-own": heard_cell(d["client"], "client", C_ID),
             "FC1-ovoice": voice_heard_cell(d["client"], "client", C_ID),
             "FC1-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_fc2(host, client, crash0):
    ev = {"place": staged("H", lambda: place(host, client, H_ID, FC2_TILE, FC2_DIR))}
    ev["H"] = [uview(host, H_ID), uview(client, H_ID)]
    new, d = watched_walk(host, client, H_ID, FC2_FIRST, lambda: host_click_walk(host, H_ID, FC2_DEST), ev)
    ev["walkCtx"] = [cv(c) for c in ctx_of(new, "host", "walk", H_ID)]
    cells = {"FC2-own": heard_cell(d["host"], "host", H_ID),
             "FC2-client": silenced_cell(d["client"], "client", H_ID),
             "FC2-cvoice": voice_silenced_cell(d["client"], "client", H_ID),
             "FC2-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== boot BC =====================


def bring_up(host, client):
    """test_reaction_prox.boot, copied with the lobby key as a parameter (F10917)."""
    bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": RPX.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == RPX.MAP_FP and cs.get("mapFingerprint") == RPX.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (want {RPX.MAP_FP!r})")
    assert seated.get("soldierIds") == RPX.SEATED, f"seated {seated.get('soldierIds')} (want {RPX.SEATED})"
    pinned = pin_ai_neutral(host, client, tag="r5u6-bc")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (want [{A_ID}])"
    uh = session.units_by_id(hs)
    assert (uh.get(A_ID) or {}).get("type") == RPX.A_TYPE, f"A type {(uh.get(A_ID) or {}).get('type')}"
    for uid, u in sorted(uh.items()):
        if u.get("faction") == RPX.FACTION_PLAYER and not u.get("isOut"):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                                "value": 0}, ("tu",))
    session.wait_host_idle(host, client, timeout=STEP_S)
    assert_hash_clean(host, client, full=True, what="bring-up")
    return {"pinned": pinned, "walkSounds": [sounds(host), sounds(client)]}


def opt_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "options.cfg"), encoding="utf-8") as f:
            return [ln.strip() for ln in f if "EnableOtherPlayerFootsteps" in ln or "EnableReactionFirePvp" in ln]
    except OSError as e:
        return [f"unreadable: {e}"]


def boot_bc():
    host = GameClient("host", None, make_user_dir("r5u6_bc_host", options=HOST_OPTIONS))
    client = GameClient("client", None, make_user_dir("r5u6_bc_client"))
    m = (host, client)
    try:
        print(f"EVIDENCE options: host {opt_lines(host)} client {opt_lines(client)}", flush=True)
        try:
            info = G3F.guarded("BC", lambda: bring_up(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE BC line)")
        print(f"EVIDENCE boot: {info}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("FC1", rows["FC1"], lambda: row_fc1(host, client, crash0))
        fails += G3F.run_row("FC2", rows["FC2"], lambda: row_fc2(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_bc()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_footsteps: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
