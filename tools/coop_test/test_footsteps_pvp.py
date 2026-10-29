"""R5-U6 S-B rows FP1-FP4 (boot BP, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0)
with "Enable Other Player Footstep Sounds" at its default ON on both machines, the HOST's `strafe` option on (an Alt click
is a sneak only with it, F14785) and the CLIENT's "Enable Reaction Fire in PvP" off (never applies: the host's value
decides): the opponent's walk plays its step sounds and start voice on this machine, its sneak (Alt) walk is silent here
whatever the option, and each machine hears its own walks.

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md section (f) test_footsteps_pvp.py, AMENDMENT U6-1 (U6-1.3, U6-1.7)
and the orchestrator ruling R-U6-SB-1 (FP2-sneak and FP4-sneak dropped: no probe reads a walk_step payload; the sneak's
per-step energy equals a walk's on stock armor, so energy is EVIDENCE only - TASK 0's capture proved both walks BAM_SNEAK).
Constants: rewrite/r5u6-task0/sb/CONSTANTS.md (TASK 0 boots BPa = BPb). Probe and D(gc, uid): see test_footsteps.py.

Boot BP (key 49062): test_battle_end_rules.boot_e6 (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's
reactions 0, R5-U3's staging (test_pvp_react_mc.stage: TILES, A's pistol, S3's rifle, the host's END TURN -> side 1).
  FP1  the opponent's walk plays on the host; the client hears its own; the client's own reaction setting never applies:
       S3 reactions 100, firing 0, TU 255; both cameras on (15,3,0); host set_seed SEED_FP1; the client's send_walk of A
       to R2_DEST.
       FP1-react  one `reaction` by S3 nested in A's walk (RF3)
       FP1-host   D(host, A): steps > 0, stepsSilenced 0
       FP1-hvoice D(host, A): voices 1
       FP1-own    D(client, A): steps > 0
  FP2  the opponent's sneak walk is silent on the host: S3 reactions 0; A back on (15,2,0) facing 4, TU A_TU; both cameras
       on (15,3,0); the client's send_walk of A to FP2_DEST with sneak.
       FP2-walk   one {intent, walk, A}; the client's coopIntentsSent.walk +1; A on FP2_DEST on both
       FP2-host   D(host, A): stepsSilenced > 0 and steps 0
       FP2-hvoice D(host, A): voicesSilenced 1, voices 0
       FP2-own    D(client, A): steps > 0 (its own sneak plays)
  (then) A back on (15,2,0) facing 4, reactions 0; the client's END TURN -> side 0 turn 2; S (8) on (15,9,0) facing 0.
  FP3  the opponent's walk plays on the client: both cameras on (16,9,0); the host TABs to S; real-UI walk to R1_DEST.
       FP3-client D(client, 8): steps > 0, stepsSilenced 0
       FP3-cvoice D(client, 8): voices 1
  FP4  the opponent's sneak walk is silent on the client: S back on (15,9,0) facing 0, TU refilled; both cameras on
       (16,9,0); the host's Alt real-UI walk to FP4_DEST (modstate alt, HOME + click, modstate none).
       FP4-client D(client, 8): stepsSilenced > 0 and steps 0
       FP4-cvoice D(client, 8): voicesSilenced 1, voices 0
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: contexts, executed paths, per-step energy, the walker on both machines, cameras, visibility.

RED on the probe build (commit B1): FP1-hvoice, FP1-own, FP2-host, FP2-hvoice, FP2-own, FP3-client, FP3-cvoice,
FP4-client, FP4-cvoice; every other cell PASS. One EVIDENCE line per row, one PASS/FAIL line per cell, then the row
verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every row "boot";
a staging step that fails fails its row's cells (the side change: FP3's and FP4's). run in the foreground to
completion. ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_footsteps_pvp.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_footsteps as FS  # noqa: E402
from test_client_shoot import set_tu_both, place  # noqa: E402

KEY = "49062"
HOST_OPTIONS = {"strafe": True}                   # vanilla takes an Alt click as a sneak only with it
CLIENT_OPTIONS = {"EnableReactionFirePvp": False}  # the client's own option never applies (the host's value decides)
A_ID, S_ID, S3_ID = RM.A_ID, RM.S_ID, RM.S3_ID     # the alien (client, seat 1); FP3 / FP4's walker; FP1's reactor
A_HOME, A_DIR = RM.TILES[A_ID]                    # (15,2,0) facing 4
S_HOME, S_DIR = RM.TILES[S_ID]                    # (15,9,0) facing 0
SEED_FP1 = 1                                      # S3's four snaps hit the floor, A unhurt (health 30)
A_FIRST = (15, 3, 0)                              # FP1 / FP2's first step tile
FP2_DEST = (15, 4, 0)                             # TASK 0 (rule (d) T0-5 (3)): two steps, A visible on the host at each
S_FIRST = (16, 9, 0)                              # FP3 / FP4's first step tile
FP4_DEST = RM.R1_DEST                             # (17,9,0), TASK 0 (rule (d) T0-5 (5)): two steps in A's view
S_TU = 64                                         # S's TU stat (its turn's full TU, TASK 0): FP4's refill value
ROWS = (("FP1", ("FP1-react", "FP1-host", "FP1-hvoice", "FP1-own", "FP1-common")),
        ("FP2", ("FP2-walk", "FP2-host", "FP2-hvoice", "FP2-own", "FP2-common")),
        ("FP3", ("FP3-client", "FP3-cvoice", "FP3-common")),
        ("FP4", ("FP4-client", "FP4-cvoice", "FP4-common")))


# ===================== rows =====================


def row_fp1(host, client, crash0):
    ev = {}
    FS.staged("S3", lambda: (RM.stat_both(host, client, S3_ID, "reactions", 100),
                             RM.stat_both(host, client, S3_ID, "firing", 0)))
    ev["s3Tu"] = FS.staged("S3 TU", lambda: set_tu_both(host, client, S3_ID, 255))
    ev["A"] = [FS.uview(host, A_ID), FS.uview(client, A_ID)]

    def order():
        host.ok({"cmd": "set_seed", "seed": SEED_FP1})
        return session.send_walk(client, A_ID, RM.R2_DEST)

    new, d = FS.watched_walk(host, client, A_ID, A_FIRST, order, ev)
    cells = {"FP1-react": FS.react_cell(new, "intent", A_ID, S3_ID),
             "FP1-host": FS.heard_cell(d["host"], "host", A_ID),
             "FP1-hvoice": FS.voice_heard_cell(d["host"], "host", A_ID),
             "FP1-own": FS.heard_cell(d["client"], "client", A_ID, silenced_zero=False),
             "FP1-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_fp2(host, client, crash0):
    ev = {}
    FS.staged("S3", lambda: RM.stat_both(host, client, S3_ID, "reactions", 0))
    ev["place"] = FS.staged("A", lambda: place(host, client, A_ID, A_HOME, A_DIR))   # S2: kept when already there
    ev["aTu"] = FS.staged("A TU", lambda: set_tu_both(host, client, A_ID, RM.A_TU))
    new, d = FS.watched_walk(host, client, A_ID, A_FIRST, lambda: session.send_walk(client, A_ID, FP2_DEST, sneak=True),
                             ev)
    walks = FS.ctx_of(new, "intent", "walk", A_ID)
    at = [G3F.pos(gc, A_ID) for gc in (host, client)]
    bad = []
    if len(walks) != 1:
        bad.append(f"new host contexts {ev['newCtx']} (want exactly one {{intent, walk, {A_ID}}})")
    if ev["intentsSent"] != 1:
        bad.append(f"client coopIntentsSent.walk +{ev['intentsSent']} (want +1)")
    if at != [FP2_DEST] * 2:
        bad.append(f"A on host/client {at} (want {FP2_DEST} on both)")
    cells = {"FP2-walk": (not bad, "; ".join(bad) or f"one {{intent, walk, {A_ID}}}, walk +1, A on {FP2_DEST} on both"),
             "FP2-host": FS.silenced_cell(d["host"], "host", A_ID),
             "FP2-hvoice": FS.voice_silenced_cell(d["host"], "host", A_ID),
             "FP2-own": FS.heard_cell(d["client"], "client", A_ID, silenced_zero=False),
             "FP2-common": G3F.common(host, client, crash0)}
    return cells, ev


def side_stage(host, client):
    """(then): A home facing 4 and reactions 0, the client's END TURN -> side 0 turn 2, S on its tile facing 0."""
    ev = {"placeA": place(host, client, A_ID, A_HOME, A_DIR)}
    RM.stat_both(host, client, A_ID, "reactions", 0)
    RM.side_change(host, client, client, RM.FACTION_PLAYER, 2, ev)
    ev["placeS"] = place(host, client, S_ID, S_HOME, S_DIR)
    ev["S"] = [FS.uview(host, S_ID), FS.uview(client, S_ID)]
    print(f"EVIDENCE side: {ev}", flush=True)


def row_fp3(host, client, crash0):
    ev = {"S": [FS.uview(host, S_ID), FS.uview(client, S_ID)]}
    new, d = FS.watched_walk(host, client, S_ID, S_FIRST, lambda: FS.host_click_walk(host, S_ID, RM.R1_DEST), ev)
    ev["walkCtx"] = [FS.cv(c) for c in FS.ctx_of(new, "host", "walk", S_ID)]
    cells = {"FP3-client": FS.heard_cell(d["client"], "client", S_ID),
             "FP3-cvoice": FS.voice_heard_cell(d["client"], "client", S_ID),
             "FP3-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_fp4(host, client, crash0):
    ev = {"place": FS.staged("S", lambda: place(host, client, S_ID, S_HOME, S_DIR))}
    ev["refill"] = FS.staged("S TU", lambda: RM.stat_both(host, client, S_ID, "tu", S_TU, refill=True)["tu"])
    ev["S"] = [FS.uview(host, S_ID), FS.uview(client, S_ID)]
    new, d = FS.watched_walk(host, client, S_ID, S_FIRST,
                             lambda: FS.host_click_walk(host, S_ID, FP4_DEST, alt=True), ev)
    ev["walkCtx"] = [FS.cv(c) for c in FS.ctx_of(new, "host", "walk", S_ID)]
    cells = {"FP4-client": FS.silenced_cell(d["client"], "client", S_ID),
             "FP4-cvoice": FS.voice_silenced_cell(d["client"], "client", S_ID),
             "FP4-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== boot BP =====================


def opt_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "options.cfg"), encoding="utf-8") as f:
            return [ln.strip() for ln in f if any(k in ln for k in ("strafe", "EnableReactionFirePvp",
                                                                     "EnableOtherPlayerFootsteps"))]
    except OSError as e:
        return [f"unreadable: {e}"]


def boot_bp():
    host = GameClient("host", None, make_user_dir("r5u6_bp_host", options=HOST_OPTIONS))
    client = GameClient("client", None, make_user_dir("r5u6_bp_client", options=CLIENT_OPTIONS))
    m = (host, client)
    try:
        print(f"EVIDENCE options: host {opt_lines(host)} client {opt_lines(client)}", flush=True)
        try:
            G3F.guarded("BP", lambda: BER.boot_e6(host, client, KEY), m)
            G3F.guarded("BP", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
            print(f"EVIDENCE boot: walkSounds host {FS.sounds(host)} client {FS.sounds(client)}", flush=True)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE BP line)")
        try:
            st = RM.stage(host, client)
            print(f"EVIDENCE stage: {st}; (turn, side) "
                  f"{[(battle_state(gc).get('turn'), battle_state(gc).get('side')) for gc in m]}", flush=True)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("FP1", rows["FP1"], lambda: row_fp1(host, client, crash0))
        fails += G3F.run_row("FP2", rows["FP2"], lambda: row_fp2(host, client, crash0))
        try:
            G3F.guarded("side", lambda: side_stage(host, client), m)
        except G3F.Miss:
            return fails + G3F.fail_all(ROWS[2:], "staging (the side change, see the CAPTURE side line)")
        fails += G3F.run_row("FP3", rows["FP3"], lambda: row_fp3(host, client, crash0))
        fails += G3F.run_row("FP4", rows["FP4"], lambda: row_fp4(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_bp()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_footsteps_pvp: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
