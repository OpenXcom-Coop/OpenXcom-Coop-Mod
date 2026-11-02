"""test_footsteps_pvp.py: rows alien_walk_heard, alien_sneak_silent, soldier_walk_heard, soldier_sneak_silent (one
boot, gm2: the client plays the aliens, seat 1; the host the seven X-COM soldiers, seat 0) with "Enable Other Player
Footstep Sounds" at its default ON on both machines, the HOST's `strafe` option on (an Alt click is a sneak only with
it) and the CLIENT's "Enable Reaction Fire in PvP" off (never applies: the host's value decides): the opponent's walk
plays its step sounds and start voice on this machine, its sneak (Alt) walk is silent here whatever the option, and
each machine hears its own walks.

No cell checks that a walk is a sneak: no probe reads a walk_step payload, and the sneak's per-step energy equals a
walk's on stock armor, so energy is EVIDENCE only (a capture showed both sneak walks as BAM_SNEAK). The constants below
were measured equal on two boots. Probe and D(gc, uid): see test_footsteps.py.

The boot (key 49062): test_battle_end_rules.boot_pvp (STR_SMALL_SCOUT, map seed 1, gamemode 2), every live unit's
reactions 0, test_pvp_react_mc's staging (stage: TILES, A's pistol, S3's rifle, the host's END TURN -> side 1).
  alien_walk_heard  the opponent's walk plays on the host; the client hears its own; the client's own reaction setting
       never applies: S3 reactions 100, firing 0, TU 255; both cameras on (15,3,0); host set_seed ALIEN_WALK_SEED; the
       client's send_walk of A to ALIEN_WALK_DEST.
       alien_walk_heard-react       one `reaction` by S3 nested in A's walk
       alien_walk_heard-host        D(host, A): steps > 0, stepsSilenced 0
       alien_walk_heard-host_voice  D(host, A): voices 1
       alien_walk_heard-own         D(client, A): steps > 0
  alien_sneak_silent  the opponent's sneak walk is silent on the host: S3 reactions 0; A back on (15,2,0) facing 4,
       TU A_TU; both cameras on (15,3,0); the client's send_walk of A to ALIEN_SNEAK_DEST with sneak.
       alien_sneak_silent-walk        one {intent, walk, A}; the client's coopIntentsSent.walk +1; A on
                                      ALIEN_SNEAK_DEST on both
       alien_sneak_silent-host        D(host, A): stepsSilenced > 0 and steps 0
       alien_sneak_silent-host_voice  D(host, A): voicesSilenced 1, voices 0
       alien_sneak_silent-own         D(client, A): steps > 0 (its own sneak plays)
  (then) A back on (15,2,0) facing 4, reactions 0; the client's END TURN -> side 0 turn 2; S (8) on (15,9,0) facing 0.
  soldier_walk_heard  the opponent's walk plays on the client: both cameras on (16,9,0); the host TABs to S; real-UI
       walk to SOLDIER_WALK_DEST.
       soldier_walk_heard-client        D(client, 8): steps > 0, stepsSilenced 0
       soldier_walk_heard-client_voice  D(client, 8): voices 1
  soldier_sneak_silent  the opponent's sneak walk is silent on the client: S back on (15,9,0) facing 0, TU refilled;
       both cameras on (16,9,0); the host's Alt real-UI walk to SOLDIER_SNEAK_DEST (modstate alt, HOME + click,
       modstate none).
       soldier_sneak_silent-client        D(client, 8): stepsSilenced > 0 and steps 0
       soldier_sneak_silent-client_voice  D(client, 8): voicesSilenced 1, voices 0
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new file in the lane
crash folder. EVIDENCE only: contexts, executed paths, per-step energy, the walker on both machines, cameras, visibility.

A build with the walkSounds probe but without the footstep option fails alien_walk_heard-host_voice,
alien_walk_heard-own, alien_sneak_silent-host, alien_sneak_silent-host_voice, alien_sneak_silent-own,
soldier_walk_heard-client, soldier_walk_heard-client_voice, soldier_sneak_silent-client and
soldier_sneak_silent-client_voice, and passes every other cell. One EVIDENCE line per row, one PASS/FAIL line per cell,
then the row verdict; every row runs after a failure. A boot step past its bound prints ONE CAPTURE line and fails every
row "boot"; a staging step that fails fails its row's cells (the side change: soldier_walk_heard's and
soldier_sneak_silent's). run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

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
A_ID, S_ID, S3_ID = RM.A_ID, RM.S_ID, RM.S3_ID     # the alien (client, seat 1); the soldier rows' walker; the
                                                  # alien_walk_heard reactor
A_HOME, A_DIR = RM.TILES[A_ID]                    # (15,2,0) facing 4
S_HOME, S_DIR = RM.TILES[S_ID]                    # (15,9,0) facing 0
ALIEN_WALK_SEED = 1                               # S3's four snaps hit the floor, A unhurt (health 30)
A_FIRST = (15, 3, 0)                              # the alien rows' first step tile
ALIEN_SNEAK_DEST = (15, 4, 0)                     # two steps, A visible on the host at each
S_FIRST = (16, 9, 0)                              # the soldier rows' first step tile
SOLDIER_SNEAK_DEST = RM.SOLDIER_WALK_DEST         # (17,9,0): two steps in A's view
S_TU = 64                                         # S's TU stat (its turn's full TU, measured): soldier_sneak_silent's
                                                  # refill value
ROWS = (("alien_walk_heard", ("alien_walk_heard-react", "alien_walk_heard-host", "alien_walk_heard-host_voice",
                              "alien_walk_heard-own", "alien_walk_heard-common")),
        ("alien_sneak_silent", ("alien_sneak_silent-walk", "alien_sneak_silent-host", "alien_sneak_silent-host_voice",
                                "alien_sneak_silent-own", "alien_sneak_silent-common")),
        ("soldier_walk_heard", ("soldier_walk_heard-client", "soldier_walk_heard-client_voice",
                                "soldier_walk_heard-common")),
        ("soldier_sneak_silent", ("soldier_sneak_silent-client", "soldier_sneak_silent-client_voice",
                                  "soldier_sneak_silent-common")))


# ===================== rows =====================


def row_alien_walk_heard(host, client, crash0):
    ev = {}
    FS.staged("S3", lambda: (RM.stat_both(host, client, S3_ID, "reactions", 100),
                             RM.stat_both(host, client, S3_ID, "firing", 0)))
    ev["s3Tu"] = FS.staged("S3 TU", lambda: set_tu_both(host, client, S3_ID, 255))
    ev["A"] = [FS.uview(host, A_ID), FS.uview(client, A_ID)]

    def order():
        host.ok({"cmd": "set_seed", "seed": ALIEN_WALK_SEED})
        return session.send_walk(client, A_ID, RM.ALIEN_WALK_DEST)

    new, d = FS.watched_walk(host, client, A_ID, A_FIRST, order, ev)
    cells = {"alien_walk_heard-react": FS.react_cell(new, "intent", A_ID, S3_ID),
             "alien_walk_heard-host": FS.heard_cell(d["host"], "host", A_ID),
             "alien_walk_heard-host_voice": FS.voice_heard_cell(d["host"], "host", A_ID),
             "alien_walk_heard-own": FS.heard_cell(d["client"], "client", A_ID, silenced_zero=False),
             "alien_walk_heard-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_alien_sneak_silent(host, client, crash0):
    ev = {}
    FS.staged("S3", lambda: RM.stat_both(host, client, S3_ID, "reactions", 0))
    ev["place"] = FS.staged("A", lambda: place(host, client, A_ID, A_HOME, A_DIR))   # kept when already there
    ev["aTu"] = FS.staged("A TU", lambda: set_tu_both(host, client, A_ID, RM.A_TU))
    new, d = FS.watched_walk(host, client, A_ID, A_FIRST,
                             lambda: session.send_walk(client, A_ID, ALIEN_SNEAK_DEST, sneak=True),
                             ev)
    walks = FS.ctx_of(new, "intent", "walk", A_ID)
    at = [G3F.pos(gc, A_ID) for gc in (host, client)]
    bad = []
    if len(walks) != 1:
        bad.append(f"new host contexts {ev['newCtx']} (want exactly one {{intent, walk, {A_ID}}})")
    if ev["intentsSent"] != 1:
        bad.append(f"client coopIntentsSent.walk +{ev['intentsSent']} (want +1)")
    if at != [ALIEN_SNEAK_DEST] * 2:
        bad.append(f"A on host/client {at} (want {ALIEN_SNEAK_DEST} on both)")
    cells = {"alien_sneak_silent-walk": (not bad, "; ".join(bad)
                                         or f"one {{intent, walk, {A_ID}}}, walk +1, A on {ALIEN_SNEAK_DEST} on both"),
             "alien_sneak_silent-host": FS.silenced_cell(d["host"], "host", A_ID),
             "alien_sneak_silent-host_voice": FS.voice_silenced_cell(d["host"], "host", A_ID),
             "alien_sneak_silent-own": FS.heard_cell(d["client"], "client", A_ID, silenced_zero=False),
             "alien_sneak_silent-common": G3F.common(host, client, crash0)}
    return cells, ev


def side_stage(host, client):
    """(then): A home facing 4 and reactions 0, the client's END TURN -> side 0 turn 2, S on its tile facing 0."""
    ev = {"placeA": place(host, client, A_ID, A_HOME, A_DIR)}
    RM.stat_both(host, client, A_ID, "reactions", 0)
    RM.side_change(host, client, client, RM.FACTION_PLAYER, 2, ev)
    ev["placeS"] = place(host, client, S_ID, S_HOME, S_DIR)
    ev["S"] = [FS.uview(host, S_ID), FS.uview(client, S_ID)]
    print(f"EVIDENCE side: {ev}", flush=True)


def row_soldier_walk_heard(host, client, crash0):
    ev = {"S": [FS.uview(host, S_ID), FS.uview(client, S_ID)]}
    new, d = FS.watched_walk(host, client, S_ID, S_FIRST, lambda: FS.host_click_walk(host, S_ID, RM.SOLDIER_WALK_DEST),
                             ev)
    ev["walkCtx"] = [FS.cv(c) for c in FS.ctx_of(new, "host", "walk", S_ID)]
    cells = {"soldier_walk_heard-client": FS.heard_cell(d["client"], "client", S_ID),
             "soldier_walk_heard-client_voice": FS.voice_heard_cell(d["client"], "client", S_ID),
             "soldier_walk_heard-common": G3F.common(host, client, crash0)}
    return cells, ev


def row_soldier_sneak_silent(host, client, crash0):
    ev = {"place": FS.staged("S", lambda: place(host, client, S_ID, S_HOME, S_DIR))}
    ev["refill"] = FS.staged("S TU", lambda: RM.stat_both(host, client, S_ID, "tu", S_TU, refill=True)["tu"])
    ev["S"] = [FS.uview(host, S_ID), FS.uview(client, S_ID)]
    new, d = FS.watched_walk(host, client, S_ID, S_FIRST,
                             lambda: FS.host_click_walk(host, S_ID, SOLDIER_SNEAK_DEST, alt=True), ev)
    ev["walkCtx"] = [FS.cv(c) for c in FS.ctx_of(new, "host", "walk", S_ID)]
    cells = {"soldier_sneak_silent-client": FS.silenced_cell(d["client"], "client", S_ID),
             "soldier_sneak_silent-client_voice": FS.voice_silenced_cell(d["client"], "client", S_ID),
             "soldier_sneak_silent-common": G3F.common(host, client, crash0)}
    return cells, ev


# ===================== the boot =====================


def opt_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "options.cfg"), encoding="utf-8") as f:
            return [ln.strip() for ln in f if any(k in ln for k in ("strafe", "EnableReactionFirePvp",
                                                                     "EnableOtherPlayerFootsteps"))]
    except OSError as e:
        return [f"unreadable: {e}"]


def run_boot():
    host = GameClient("host", None, make_user_dir("footsteps_pvp_host", options=HOST_OPTIONS))
    client = GameClient("client", None, make_user_dir("footsteps_pvp_client", options=CLIENT_OPTIONS))
    m = (host, client)
    try:
        print(f"EVIDENCE options: host {opt_lines(host)} client {opt_lines(client)}", flush=True)
        try:
            G3F.guarded("boot", lambda: BER.boot_pvp(host, client, KEY), m)
            G3F.guarded("boot", lambda: G3F.reactions_zero(host, client), m)
            crash0 = session._crash_log_snapshot()
            print(f"EVIDENCE boot: walkSounds host {FS.sounds(host)} client {FS.sounds(client)}", flush=True)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        try:
            st = RM.stage(host, client)
            print(f"EVIDENCE stage: {st}; (turn, side) "
                  f"{[(battle_state(gc).get('turn'), battle_state(gc).get('side')) for gc in m]}", flush=True)
        except G3F.Miss:
            return G3F.fail_all(ROWS, "staging (see the CAPTURE staging line)")
        rows = dict(ROWS)
        fails = G3F.run_row("alien_walk_heard", rows["alien_walk_heard"],
                            lambda: row_alien_walk_heard(host, client, crash0))
        fails += G3F.run_row("alien_sneak_silent", rows["alien_sneak_silent"],
                             lambda: row_alien_sneak_silent(host, client, crash0))
        try:
            G3F.guarded("side", lambda: side_stage(host, client), m)
        except G3F.Miss:
            return fails + G3F.fail_all(ROWS[2:], "staging (the side change, see the CAPTURE side line)")
        fails += G3F.run_row("soldier_walk_heard", rows["soldier_walk_heard"],
                             lambda: row_soldier_walk_heard(host, client, crash0))
        fails += G3F.run_row("soldier_sneak_silent", rows["soldier_sneak_silent"],
                             lambda: row_soldier_sneak_silent(host, client, crash0))
        return fails
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_footsteps_pvp: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
