"""test_footsteps.py: rows client_walk_muted, host_walk_muted (one boot, classic co-op: the client commands soldiers 8
and 9, the host the other five) with the HOST's "Enable Other Player Footstep Sounds" off and its "Enable Reaction Fire
in PvP" off (its options.cfg `EnableOtherPlayerFootsteps: false`, `EnableReactionFirePvp: false`; the client keeps the
defaults): the partner's walk makes no step sound and no "start moving" voice on this machine, each machine hears its
own walks, and the PvP option never touches co-op reaction fire. The host's value applies on both machines; the
client's walk ghost plays vanilla's step sounds and the start voice.

Probe: event_state.walkSounds {walker id: {steps, stepsSilenced, voices, voicesSilenced}} (TEST-ONLY): one entry
per walk-sound decision this machine made (a step-sound phase past vanilla's sight / screen gate, or a start voice).
D(gc, uid) = that entry after the row minus before (missing = all 0), read after the client's walk ghost drained.
The constants below were measured equal on two boots.

The boot (key 49061): test_reaction_prox's bring-up (roster seed 1, map seed 1, seat_count 2, pin_ai_neutral, every
player unit's reactions 0), copied with the key as a parameter.
  client_walk_muted  the partner's walk is silent on the host; the client hears its own: A on HALTED_WALK_A_TILE
       facing 4, C (8) on HALTED_WALK_C_TILE facing 0, one END TURN cycle, A reactions 100 and TU A_TU (refill);
       both cameras on (16,7,0); host set_seed HALTED_WALK_SEED; the client's send_walk of C to HALTED_WALK_DEST.
       client_walk_muted-react       one `reaction` context by A nested in C's walk (the PvP option never touches
                                     co-op)
       client_walk_muted-host        D(host, C): stepsSilenced > 0 and steps 0
       client_walk_muted-host_voice  D(host, C): voicesSilenced 1, voices 0
       client_walk_muted-own         D(client, C): steps > 0, stepsSilenced 0
       client_walk_muted-own_voice   D(client, C): voices 1
  host_walk_muted  the host's walk is silent on the client: H (10) on HOST_WALK_TILE facing 2; both cameras on the
       walk's first step tile; the host TABs to H; the host's real-UI walk to HOST_WALK_DEST.
       host_walk_muted-own           D(host, 10): steps > 0, stepsSilenced 0
       host_walk_muted-client        D(client, 10): stepsSilenced > 0 and steps 0
       host_walk_muted-client_voice  D(client, 10): voicesSilenced 1, voices 0
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: contexts, executed paths, the walker on both machines, cameras, visibility, ghost counters.

A build with the walkSounds probe but without the footstep silencing fails client_walk_muted-host,
client_walk_muted-host_voice, client_walk_muted-own, client_walk_muted-own_voice, host_walk_muted-client and
host_walk_muted-client_voice, and passes every other cell. One EVIDENCE line per row, one PASS/FAIL line per cell, then
the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row
"boot"; a staging step that fails fails its row's cells. run in the foreground to completion. ONE run is the result, no
skip path; exit 0 only when every cell passes, else 2. test_footsteps_pvp.py imports this file's helpers.

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
HALTED_WALK_SEED = RPX.HALTED_WALK_SEED        # 3: two of A's three snaps hit C (40 -> 21), C standing
CLIENT_WALK_FIRST = (16, 7, 0)                 # C's first step tile, both cameras centred on it
HOST_WALK_TILE, HOST_WALK_DIR = (7, 38, 0), 2  # open ground, Chebyshev >= 21 from A
HOST_WALK_DEST = (9, 38, 0)                    # two steps east, executed [(8,38,0), (9,38,0)]
HOST_WALK_FIRST = (8, 38, 0)
STEP_S, GHOST_S = 30, 10                       # every bounded wait; the client's ghost drain (measured: 0.05 s)
SOUND_KEYS = ("steps", "stepsSilenced", "voices", "voicesSilenced")
ROWS = (("client_walk_muted", ("client_walk_muted-react", "client_walk_muted-host", "client_walk_muted-host_voice",
                               "client_walk_muted-own", "client_walk_muted-own_voice", "client_walk_muted-common")),
        ("host_walk_muted", ("host_walk_muted-own", "host_walk_muted-client", "host_walk_muted-client_voice",
                             "host_walk_muted-common")))


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


def row_client_walk_muted(host, client, crash0):
    ev = {}
    staged("tiles", lambda: (RPX.tele_both(host, client, A_ID, RPX.HALTED_WALK_A_TILE, RPX.HALTED_WALK_A_DIR),
                             RPX.tele_both(host, client, C_ID, RPX.HALTED_WALK_C_TILE, RPX.HALTED_WALK_C_DIR)))
    notes = []
    ev["turn0"] = end_turn_cycle(host, client, None, notes)
    ev["turnSide"] = [(battle_state(gc).get("turn"), battle_state(gc).get("side")) for gc in (host, client)]
    if notes or ev["turnSide"] != [(ev["turn0"] + 1, RPX.FACTION_PLAYER)] * 2:
        raise RuntimeError(f"staging (END TURN cycle): notes {notes}, (turn, side) {ev['turnSide']}")
    staged("A", lambda: (RM.stat_both(host, client, A_ID, "reactions", RPX.A_REACTIONS),
                         RM.stat_both(host, client, A_ID, "tu", RPX.A_TU, refill=True)))
    ev["A"] = [uview(host, A_ID), uview(client, A_ID)]

    def order():
        host.ok({"cmd": "set_seed", "seed": HALTED_WALK_SEED})
        return session.send_walk(client, C_ID, RPX.HALTED_WALK_DEST)

    new, d = watched_walk(host, client, C_ID, CLIENT_WALK_FIRST, order, ev)
    cells = {"client_walk_muted-react": react_cell(new, "intent", C_ID, A_ID),
             "client_walk_muted-host": silenced_cell(d["host"], "host", C_ID),
             "client_walk_muted-host_voice": voice_silenced_cell(d["host"], "host", C_ID),
             "client_walk_muted-own": heard_cell(d["client"], "client", C_ID),
             "client_walk_muted-own_voice": voice_heard_cell(d["client"], "client", C_ID),
             "client_walk_muted-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_host_walk_muted(host, client, crash0):
    ev = {"place": staged("H", lambda: place(host, client, H_ID, HOST_WALK_TILE, HOST_WALK_DIR))}
    ev["H"] = [uview(host, H_ID), uview(client, H_ID)]
    new, d = watched_walk(host, client, H_ID, HOST_WALK_FIRST, lambda: host_click_walk(host, H_ID, HOST_WALK_DEST), ev)
    ev["walkCtx"] = [cv(c) for c in ctx_of(new, "host", "walk", H_ID)]
    cells = {"host_walk_muted-own": heard_cell(d["host"], "host", H_ID),
             "host_walk_muted-client": silenced_cell(d["client"], "client", H_ID),
             "host_walk_muted-client_voice": voice_silenced_cell(d["client"], "client", H_ID),
             "host_walk_muted-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== the boot =====================


def bring_up(host, client):
    """test_reaction_prox.boot, copied with the lobby key as a parameter."""
    bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": RPX.SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == RPX.MAP_FP and cs.get("mapFingerprint") == RPX.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r} (want {RPX.MAP_FP!r})")
    assert seated.get("soldierIds") == RPX.SEATED, f"seated {seated.get('soldierIds')} (want {RPX.SEATED})"
    pinned = pin_ai_neutral(host, client, tag="footsteps")
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


def run_boot():
    host = GameClient("host", None, make_user_dir("footsteps_host", options=HOST_OPTIONS))
    client = GameClient("client", None, make_user_dir("footsteps_client"))
    m = (host, client)
    try:
        print(f"EVIDENCE options: host {opt_lines(host)} client {opt_lines(client)}", flush=True)
        try:
            info = G3F.guarded("boot", lambda: bring_up(host, client), m)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        print(f"EVIDENCE boot: {info}", flush=True)
        rows = dict(ROWS)
        fails = G3F.run_row("client_walk_muted", rows["client_walk_muted"],
                            lambda: row_client_walk_muted(host, client, crash0))
        fails += G3F.run_row("host_walk_muted", rows["host_walk_muted"],
                             lambda: row_host_walk_muted(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_footsteps: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
