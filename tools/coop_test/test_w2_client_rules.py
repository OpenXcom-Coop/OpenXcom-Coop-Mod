"""W2-P4 S-E - test_w2_client_rules.py: the second player's spray autoshot and
its own force-fire key (spec rewrite/prompts/w2p4_client_combat_intents.md
section (f) "test_w2_client_rules.py (S-E)", sections (b)1 (the `shoot` kind's
`spray` and `forceFire` fields), (b)5 (K2) and (b)8 (F423, the per-player
half), as amended by AMENDMENT C2 (N34: set_touch_modifiers exists since S-A)
and AMENDMENT C4 (PR-Q20: K1 keeps refusing the spray start until S-E; F1168:
no lever could start a spray before S-E, so SEED_C18 was hunted on S-E1's red
build with the NEW battle_fire `spray` stand-in).

S-E1 writes C18 and C16f. S-E2 adds the skill rows (D147) to this file later:
SCENARIOS below is where they go.

Before S-E the second player cannot spray: its Ctrl+Shift click that starts a
spray (BattlescapeGame::primaryAction, an AUTO shot with a `sprayWaypoints`
weapon) is refused at K1 (client coopLocalExecBlocked +1, nothing sent). And the
host applies its OWN force-fire key to the partner's shot: inside the host's
execution of a client `shoot` order, the four force-fire terms F1-F4
(ProjectileFlyBState.cpp, Projectile.cpp x2, TileEngine.cpp) read
Options::forceFire && the HOST's isCtrlPressed(true). After S-E the spray is a
`shoot` intent carrying vanilla's spread voxels, and inside an `intent` context
F1-F4 read the order's own `forceFire` (the ordering machine's Options::forceFire
&& its own Ctrl), never the host's keys.

Two scenarios, ONE boot (the Coop_Spray_Test mod on both machines: STR_RIFLE
has sprayWaypoints 2), in this order:

  C18    the spray. C gets a rifle + clip (lever, both, clear hands), C ->
         C_TILE facing east (dir 2), C TU max, C firing 120 (all on BOTH).
         Client: TAB-select C, the right-hand box, key 51 (AUTO), HOME, the
         client's own touch Ctrl + Shift ON (set_touch_modifiers on the client),
         one left click on SPRAY_W0 (starts the spray), host set_seed SEED_C18,
         one left click on SPRAY_W1 (vanilla fires: battleConfirmFireMode is off
         and Ctrl+Shift are held), then the client's touch flags OFF. RED: the
         spray start is refused at K1 (client coopLocalExecBlocked +1 at the
         SPRAY_W0 click; the flags stay latched, so the SPRAY_W1 click is a
         spray start too and is refused again), nothing sent. GREEN: the
         SPRAY_W0 click is local display (coopLocalExecBlocked unchanged,
         nothing sent); the SPRAY_W1 click is ONE order: host closedContexts
         gains {origin intent, kind shoot, actorId C} whose evs are exactly
         C18_CHAIN; its three `shot` cues have shotIndex 1, 2, 3 and
         waypointsLeft 2, 1, 0 (the spray shape), impactVoxels C18_IMPACTS, and
         each passes over its own spread waypoint's tile (C18_SPRAY, vanilla's
         spread of SPRAY_W0..SPRAY_W1); C TU C18_TU_AFTER and the clip
         C18_CLIP_AFTER on both.
  C16f   force-fire belongs to the ordering player. C gets a fresh rifle + clip
         (lever, both), C stays on C_TILE facing east (the turn C18 left),
         TU max, firing 120; A -> C16F_A_TILE facing west, A visible on both
         (set_stat visible). The HOST's touch Ctrl is ON for both legs. Leg 1:
         the client's real-UI snap at A's tile with its own Ctrl OFF (forceFire
         false), host set_seed SEED_C16F right before the click. Leg 2: C TU
         max (both), the same snap with the client's own touch Ctrl ON (set
         right before the click; forceFire true). At SEED_C16F the unforced shot
         (aimed at A) lands at C16F_UNFORCED and the forced one (the tile centre)
         at C16F_FORCED (T0-9f, measured with the host stand-in: host Ctrl OFF /
         ON). RED: with the host's Ctrl ON the partner's unforced leg-1 shot gets
         the FORCED value. GREEN: leg 1 -> C16F_UNFORCED, leg 2 -> C16F_FORCED,
         both with the host's Ctrl ON (the value follows the ordering player's
         key, not the host's); each leg one {intent, shoot, C} context with
         C16F_CHAIN, C TU C16F_TU_AFTER on both. A survives both legs in either
         order (T0-9f: health 30 -> 19 -> 7, standing).

C16f runs after C18 on purpose: at SEED_C18 the spray changes no terrain and
hits no unit (T0-9f / SEED_C18 proofs), so C16f meets the same world on the red
build (the spray refused) and on the green build (the spray fired), and C18's
last shot leaves C facing east either way.

Common asserts (spec (f), after wait_host_idle): hash_now {full:true} - every
bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged
and host 0; the W2-P2 delta must-be-0 counters on both; every lever item created
on both machines with equal ids (both()). For an admitted order: host
closedContexts gains exactly one {origin intent, kind K, actorId C}; every host
ev of that actionId is in the client's log with the same seq, kind and
actionId; exactly one bt_action_end; client coopIntentsSent[K] +1; client
inFlight null at the end; no STR_COOP_ACTION_TIMEOUT. For a refused press:
nothing sent (client inFlight null, host lastSeqEmitted unchanged, host
intentsReceived unchanged, client coopIntentsSent unchanged).

FIXTURE (TASK 0 T0-10 = T0c, T0-9f and SEED_C18 on S-E1's red build; the
roster-pinned terror boot of test_w2_host_combat.py with the mod on both):
set_seed SEED_ROSTER on the HOST right before its open_new_battle, mission
STR_TERROR_MISSION, set_seed SEED_MAP right before newbattle_ok, seat_count 2,
MAP_FP asserted on both (the mod leaves it unchanged, F1164), the seated unit
ids asserted, pin_ai_neutral. Every lever pair goes to the CLIENT first (F607).
Item ids are read at run time from the lever replies (F1107). Seeds were found
with HOST stand-ins (battle_fire {mode spray} / {mode snap, target A}) that run
the executor's states in its order; the green build proves them again (N18 =
F1085).

RED-THEN-GREEN (spec (d) row S-E). Commit S-E1.1 (this file and the battle_fire
spray stand-in) is run ONCE and every scenario must FAIL with its RED evidence.
Commit S-E1.2 is run ONCE and every scenario must PASS. Each scenario prints ONE
"EVIDENCE <id>:" line with both machines' fields BEFORE its green conditions are
checked; main() runs every scenario even after an earlier one failed and prints
"PASS <id>" / "FAIL <id>: <message>". Every wait is bounded; a wait that times
out is recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when every scenario passes, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_client_rules.py
"""

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import diff_buckets, short, both
from test_w2_host_combat import bring_up_lobby_roster_pinned, ev_tuples
from test_w2_client_shoot import (top, snap, ubrief, press, menu_rows, mine, give_both, place,
                                  set_tu_both, set_firing_both, cancel_client_aim, aim_click, await_press,
                                  collect, ctx_view, chain_of, admitted_fails, forwarded_fails, tu_fails,
                                  qty_fails, common_fails, finish, press_view, ui_view, shot_payloads,
                                  RHAND_CENTRE, TU_MAX, C_TU_FULL, CURSOR_AIM, POLL_S, KEY_SNAP, KEY_AUTO)
from test_w2_client_grenade import mod_log, hurt_map, hurt_delta

# ----- bring-up (TASK 0: the roster-pinned terror boot, the mod on both) -----
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18   # host battle_state.mapFingerprint on SEED_MAP 1, unmodded and modded (F1164)
SEATED = [8, 9]                   # the client's seated units: C and C2
C_ID = 8
H_ID = 10                         # first host-seat soldier
A_ID, A2_ID = 1000000, 1000001    # Sectoid Soldiers
PORT = "48715"
COOP_SEAT_0 = 0
FACTION_PLAYER = 0
STATUS_STANDING = 0               # src/Mod/Unit.h enum UnitStatus
MOD_NAME = "Coop_Spray_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_Spray_Test v1.0"

# ----- C18 (T0-10 = T0c: F1168; SEED_C18 hunted on S-E1's red build) -----
C_TILE, C18_C_DIR = (12, 26, 0), 2
SPRAY_W0, SPRAY_W1 = (24, 24, 0), (24, 27, 0)
SEED_C18 = 4                      # seeds 1-3: a shot off its waypoint tile (and 1, 2 changed terrain)
C18_ROWS = 4                      # the modded rifle's menu (T0c)
C18_SPRAY = [(392, 392, 12), (392, 416, 12), (392, 440, 12)]   # vanilla's spread voxels, shot 1..3
C18_IMPACTS = [(499, 386, 1), (718, 402, 1), (538, 450, 1)]    # the three shots' impactVoxel (floor)
C18_WAYPOINTS_LEFT = [2, 1, 0]
C18_CHAIN = ["shot", "hit", "shot", "hit", "shot", "hit", "bt_action_end"]
AUTO_TU = 22
C18_TU_AFTER = C_TU_FULL - AUTO_TU   # 42: no pre-shot turn (C faces east)
CLIP_FULL = 20
C18_CLIP_AFTER = 17
TILE_HALF = 8                     # voxels: passing over a tile = within 8 voxels (x/y) of its centre

# ----- C16f (T0-9f on S-E1's red build) -----
C16F_A_TILE, C16F_A_DIR = (20, 26, 0), 6
SEED_C16F = 1
C16F_UNFORCED = (326, 424, 8)     # aimed at A: the unit's centre (host Ctrl OFF)
C16F_FORCED = (326, 424, 12)      # force-fire at A's tile: the tile centre (host Ctrl ON)
SNAP_TU = 16
C16F_TU_AFTER = C_TU_FULL - SNAP_TU  # 48: no pre-shot turn
C16F_CHAIN = ["shot", "hit", "bt_action_end"]

# ----- UI -----
CLICK_WAIT_S = 1.5                # how long a waypoint click gets to show as refused or sent


# ===================== small helpers =====================


def touch(gc, **flags):
    """set_touch_modifiers on ONE machine (no keys = read back only)."""
    req = {"cmd": "set_touch_modifiers"}
    req.update(flags)
    r = gc.ok(req)
    return {k: r.get(k) for k in ("ctrl", "alt", "shift")}


def vox(d):
    return (d.get("x"), d.get("y"), d.get("z")) if isinstance(d, dict) else None


def over_tile(origin, impact, target):
    """Whether the straight shot origin -> impact passes over `target`'s tile:
    the x/y distance of `target` from the segment (voxels), the segment
    parameter of the closest point (0..1 = between the muzzle and the impact)
    and the shot's height there. Returns (distance, t, z)."""
    ox, oy, oz = origin
    ix, iy, iz = impact
    px, py, _ = target
    dx, dy = ix - ox, iy - oy
    l2 = dx * dx + dy * dy
    t = ((px - ox) * dx + (py - oy) * dy) / l2 if l2 else 0.0
    return (round(math.hypot(px - (ox + t * dx), py - (oy + t * dy)), 2), round(t, 3), round(oz + t * (iz - oz), 1))


def spray_rows(shots):
    rows = []
    for k, (s, p) in enumerate(shots):
        p = p or {}
        o, i = vox(p.get("originVoxel")), vox(p.get("impactVoxel"))
        tgt = C18_SPRAY[k] if k < len(C18_SPRAY) else None
        rows.append({"seq": s, "shotIndex": p.get("shotIndex"), "waypointsLeft": p.get("waypointsLeft"),
                     "action": p.get("action"), "origin": o, "impact": i, "impactPart": p.get("impact"),
                     "target": tgt, "over": over_tile(o, i, tgt) if (o and i and tgt) else None})
    return rows


def click_state(host, client, before):
    """Up to CLICK_WAIT_S after one waypoint click: `refused` (client
    coopLocalExecBlocked moved), `sent` (client inFlight / coopIntentsSent moved
    or the host emitted) or `quiet`."""
    t0 = time.time()
    while time.time() - t0 < CLICK_WAIT_S:
        ec, eh = event_state(client), event_state(host)
        if (ec.get("inFlight") or ec.get("coopIntentsSent") != before["client"]["coopIntentsSent"]
                or eh.get("lastSeqEmitted") != before["host"]["lastSeqEmitted"]):
            return {"state": "sent", "t": round(time.time() - t0, 3)}
        if ec.get("coopLocalExecBlocked") != before["client"]["coopLocalExecBlocked"]:
            return {"state": "refused", "t": round(time.time() - t0, 3)}
        time.sleep(POLL_S)
    return {"state": "quiet", "t": round(time.time() - t0, 3)}


def nothing_sent_fails(before, rec, what):
    fails = []
    if rec["client"]["inFlight"] is not None:
        fails.append(f"{what}: client inFlight {rec['client']['inFlight']} (want null)")
    if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
        fails.append(f"{what}: host lastSeqEmitted {before['host']['lastSeqEmitted']}->"
                     f"{rec['host']['lastSeqEmitted']} (want unchanged)")
    if rec["client"]["coopIntentsSent"] != before["client"]["coopIntentsSent"]:
        fails.append(f"{what}: client coopIntentsSent {before['client']['coopIntentsSent']}->"
                     f"{rec['client']['coopIntentsSent']} (want unchanged)")
    if rec["host"]["intentsReceived"] != before["host"]["intentsReceived"]:
        fails.append(f"{what}: host intentsReceived {before['host']['intentsReceived']}->"
                     f"{rec['host']['intentsReceived']} (want unchanged)")
    return fails


def blocked(p):
    return p["client"]["coopLocalExecBlocked"]


# ===================== scenarios =====================


def c18_spray(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C18_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    staged = diff_buckets(host, client)
    hm0 = touch(host)
    hurt0 = {"host": hurt_map(host), "client": hurt_map(client)}
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {}
    mid = None
    out0, out1 = {}, {}
    try:
        ev["tab"] = tab_select(client, C_ID)
        assert ev["tab"], f"TAB never selected C on the client (selectedId {battle_state(client).get('selectedId')})"
        if battle_state(client).get("cursorType") == CURSOR_AIM:
            click_nth(client, RHAND_NTH)   # F503: this click only cancels the aim
            ev["aimCancelled"] = battle_state(client).get("cursorType")
        r = click_nth(client, RHAND_NTH)
        assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
        client.wait_for("client ActionMenuState on top",
                        lambda: client.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState")
                        or None, timeout=5)
        ev["rows"] = menu_rows(client)
        press(client, KEY_AUTO)
        client.wait_for("client BattlescapeState on top after the AUTO key",
                        lambda: top(client) == "BattlescapeState" or None, timeout=5)
        ev["cursorAfterKey"] = battle_state(client).get("cursorType")
        assert ev["cursorAfterKey"] == CURSOR_AIM, (
            f"key {KEY_AUTO} did not start targeting on the client (cursorType {ev['cursorAfterKey']})")
        press(client, SDLK_HOME)
        time.sleep(0.15)
        pos = {}
        for name, t in (("W0", SPRAY_W0), ("W1", SPRAY_W1)):
            pr = client.cmd({"cmd": "map_tile_click_pos", "x": t[0], "y": t[1], "z": t[2]})
            pos[name] = pr
        ev["clickPos"] = {n: {k: p.get(k) for k in ("verified", "winX", "winY", "centered")} for n, p in pos.items()}
        assert pos["W0"].get("verified") and pos["W1"].get("verified"), (
            f"precondition: map_tile_click_pos did not verify both spray waypoints on the client: {ev['clickPos']}")
        ev["clientMods"] = touch(client, ctrl=True, shift=True)
        client.ok({"cmd": "inject_input", "kind": "click", "x": pos["W0"]["winX"], "y": pos["W0"]["winY"],
                   "button": "left"})
        out0 = click_state(host, client, before)
        mid = snap(host, client)
        host.ok({"cmd": "set_seed", "seed": SEED_C18})
        client.ok({"cmd": "inject_input", "kind": "click", "x": pos["W1"]["winX"], "y": pos["W1"]["winY"],
                   "button": "left"})
        out1 = await_press(host, client, mid, notes)
    except Exception as e:
        notes.append(f"real-UI spray: {short(e)}")
    finally:
        try:
            ev["clientModsAfter"] = touch(client, ctrl=False, shift=False)
        except Exception as e:
            notes.append(f"client touch flags off: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    rows = spray_rows(shot_payloads(host, chain))
    hurt1 = {"host": hurt_map(host), "client": hurt_map(client)}
    hurt = {n: hurt_delta(hurt0[n], hurt1[n]) for n in ("host", "client")}
    w0 = {"blocked": (blocked(before), blocked(mid)) if mid else None,
          "hostSeq": (before["host"]["lastSeqEmitted"], mid["host"]["lastSeqEmitted"]) if mid else None,
          "inFlight": mid["client"]["inFlight"] if mid else None,
          "sent": (before["client"]["coopIntentsSent"], mid["client"]["coopIntentsSent"]) if mid else None}
    print(f"EVIDENCE C18: staged rifle={rifle} clip={clip} C={pc_} stagedDiff={staged} aimCancel={aim0} "
          f"hostMods={hm0} ui={ev} W0click={out0} W0={w0} W1click={out1}; {press_view(before, rec)}; "
          f"ui={ui_view(before, rec)}; newContexts={new}; action={aid} chain={[(e['seq'], e['kind']) for e in chain]}; "
          f"shots={rows}; host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; "
          f"C host={ubrief(rec['uh'].get(C_ID))} client={ubrief(rec['uc'].get(C_ID))}; items="
          f"{ {i: ((rec['ih'].get(i) or {}).get('qty'), (rec['ic'].get(i) or {}).get('qty')) for i in (rifle, clip)} }; "
          f"hurt={hurt}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if any(hm0.values()):
        fails.append(f"precondition: host touch flags {hm0} (want all off)")
    if mid is None:
        fails.append("the SPRAY_W0 click never ran")
    else:
        if blocked(mid) != blocked(before):
            fails.append(f"SPRAY_W0 click: client coopLocalExecBlocked {blocked(before)}->{blocked(mid)} (want "
                         f"unchanged: the spray start is local display, not a K1 refusal)")
        fails += nothing_sent_fails(before, mid, "SPRAY_W0 click")
        fails += forwarded_fails(mid, rec)
    f, cx = admitted_fails(before, rec, "shoot", C_ID)
    fails += f
    kinds = [e["kind"] for e in chain]
    if cx and kinds != C18_CHAIN:
        fails.append(f"host evs of actionId {aid} = {kinds} (want exactly {C18_CHAIN})")
    if cx:
        got = [(r["shotIndex"], r["waypointsLeft"], r["impact"]) for r in rows]
        want = [(k + 1, C18_WAYPOINTS_LEFT[k], C18_IMPACTS[k]) for k in range(len(C18_IMPACTS))]
        if got != want:
            fails.append(f"`shot` cues of actionId {aid} (shotIndex, waypointsLeft, impactVoxel) = {got} "
                         f"(want {want}: the spray at SEED_C18)")
        for r in rows:
            ov = r["over"]
            if not ov or ov[0] > TILE_HALF or not (0.0 <= ov[1] <= 1.0):
                fails.append(f"shot {r['shotIndex']} does not pass over its spread waypoint {r['target']}: "
                             f"(distance, t, z) = {ov} (want distance <= {TILE_HALF}, 0 <= t <= 1)")
    fails += tu_fails(rec, C_ID, C18_TU_AFTER)
    fails += qty_fails(rec, clip, C18_CLIP_AFTER, "clip")
    if hurt["host"] or hurt["client"]:
        fails.append(f"units changed (health, stun, status): {hurt} (want none)")
    fails += common_fails(host, client, before, "C18")
    finish(fails)


def c16f_leg(host, client, client_ctrl, notes):
    """One real-UI snap from C at A's tile, the host's set_seed right before the
    click; the client's own touch Ctrl set ON right before it when
    `client_ctrl` (and OFF again after the order). Returns the leg's record."""
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    leg = {"before": before, "hostMods": touch(host), "clientMods": touch(client)}

    def before_click():
        host.ok({"cmd": "set_seed", "seed": SEED_C16F})
        if client_ctrl:
            leg["clientMods"] = touch(client, ctrl=True)
    pv = {}
    try:
        pv = aim_click(client, KEY_SNAP, C16F_A_TILE, before_click)
    except Exception as e:
        notes.append(f"real-UI snap (client Ctrl {'ON' if client_ctrl else 'OFF'}): {short(e)}")
    leg["press"] = {k: v for k, v in pv.items() if k != "clickAt"}
    leg["outcome"] = await_press(host, client, before, notes)
    if client_ctrl:
        try:
            leg["clientModsAfter"] = touch(client, ctrl=False)
        except Exception as e:
            notes.append(f"client touch Ctrl off: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", C_ID)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    shots = shot_payloads(host, chain)
    leg.update({"rec": rec, "new": new, "aid": aid, "chain": chain,
                "shots": [(s, {k: (p or {}).get(k) for k in ("action", "weapon", "ammo", "shotIndex", "originVoxel",
                                                              "impactVoxel", "impact")}) for s, p in shots],
                "impact": vox((shots[0][1] or {}).get("impactVoxel")) if shots else None,
                "A": {"host": ubrief(rec["uh"].get(A_ID)), "client": ubrief(rec["uc"].get(A_ID))}})
    return leg


def leg_view(leg):
    return {"hostMods": leg["hostMods"], "clientMods": leg["clientMods"],
            "clientModsAfter": leg.get("clientModsAfter"), "press": leg["press"], "outcome": leg["outcome"],
            "counters": press_view(leg["before"], leg["rec"]), "newContexts": leg["new"], "action": leg["aid"],
            "chain": [(e["seq"], e["kind"]) for e in leg["chain"]], "shots": leg["shots"], "impact": leg["impact"],
            "C": {"host": ubrief(leg["rec"]["uh"].get(C_ID)), "client": ubrief(leg["rec"]["uc"].get(C_ID))},
            "A": leg["A"], "diff": leg["rec"]["diff"], "desync": leg["rec"]["dsc"]}


def c16f_leg_fails(host, client, leg, want, what):
    fails = []
    if not leg["hostMods"].get("ctrl"):
        fails.append(f"{what}: host touch Ctrl {leg['hostMods']} at the press (want ON)")
    fails += forwarded_fails(leg["before"], leg["rec"])
    f, cx = admitted_fails(leg["before"], leg["rec"], "shoot", C_ID)
    fails += [f"{what}: {m}" for m in f]
    kinds = [e["kind"] for e in leg["chain"]]
    if cx and kinds != C16F_CHAIN:
        fails.append(f"{what}: host evs of actionId {leg['aid']} = {kinds} (want exactly {C16F_CHAIN})")
    if leg["impact"] != want:
        fails.append(f"{what}: the shot's impactVoxel {leg['impact']} (want {want})")
    fails += [f"{what}: {m}" for m in tu_fails(leg["rec"], C_ID, C16F_TU_AFTER)]
    for n in ("host", "client"):
        a = leg["A"][n] or {}
        if a.get("status") != STATUS_STANDING:
            fails.append(f"{what}: {n} A {a} (want standing)")
    fails += [f"{what}: {m}" for m in common_fails(host, client, leg["before"], what)]
    return fails


def c16f_force_fire(host, client, ctx):
    notes = []
    aim0 = cancel_client_aim(client)
    rifle, clip = give_both(host, client, C_ID, "STR_RIFLE", "STR_RIFLE_CLIP")
    pc_ = place(host, client, C_ID, C_TILE, C18_C_DIR)
    set_tu_both(host, client, C_ID, TU_MAX)
    set_firing_both(host, client, C_ID)
    pa_ = place(host, client, A_ID, C16F_A_TILE, C16F_A_DIR)
    vis = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": A_ID, "visible": True},
               ("visible",)).get("visible")
    staged = diff_buckets(host, client)
    legs = {}
    try:
        legs["hostCtrlOn"] = touch(host, ctrl=True)
        legs["L1"] = c16f_leg(host, client, False, notes)
        set_tu_both(host, client, C_ID, TU_MAX)
        legs["L2"] = c16f_leg(host, client, True, notes)
    except Exception as e:
        notes.append(f"C16f drive: {short(e)}")
    finally:
        try:
            legs["hostCtrlOff"] = touch(host, ctrl=False)
        except Exception as e:
            notes.append(f"host touch Ctrl off: {short(e)}")
    print(f"EVIDENCE C16f: staged rifle={rifle} clip={clip} C={pc_} A={pa_} Avisible={vis} stagedDiff={staged} "
          f"aimCancel={aim0} hostCtrlOn={legs.get('hostCtrlOn')} hostCtrlOff={legs.get('hostCtrlOff')}; "
          f"LEG1 (client Ctrl OFF, want {C16F_UNFORCED})="
          f"{leg_view(legs['L1']) if 'L1' in legs else None}; LEG2 (client Ctrl ON, want {C16F_FORCED})="
          f"{leg_view(legs['L2']) if 'L2' in legs else None}; notes={notes}", flush=True)
    fails = list(notes)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if vis is not True:
        fails.append(f"precondition: A visible {vis} after set_stat (want true on both)")
    if "L1" in legs:
        fails += c16f_leg_fails(host, client, legs["L1"], C16F_UNFORCED, "leg 1 (client Ctrl OFF)")
    else:
        fails.append("leg 1 never ran")
    if "L2" in legs:
        fails += c16f_leg_fails(host, client, legs["L2"], C16F_FORCED, "leg 2 (client Ctrl ON)")
    else:
        fails.append("leg 2 never ran")
    finish(fails)


# S-E2 appends its skill rows (D147) here.
SCENARIOS = (("C18", c18_spray), ("C16f", c16f_force_fire))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    ml = {gc.name: mod_log(gc) for gc in (host, client)}
    for name, m in ml.items():
        assert MOD_ACTIVE_LINE in (m.get("active") or []) and not m.get("invalid"), (
            f"{name}: {MOD_NAME} not active (active lines {m.get('active')}, invalid {m.get('invalid')}, "
            f"error {m.get('error')})")
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} ({MISSION}, SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p4-se")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == SEATED, f"seated client units {seated_uids} (baked {SEATED})"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    ub = session.units_by_id(hs)
    assert (ub.get(C_ID) or {}).get("tu") == C_TU_FULL, f"C at bring-up {ubrief(ub.get(C_ID))} (baked TU {C_TU_FULL})"
    a = ub.get(A_ID) or {}
    assert a.get("status") == STATUS_STANDING and not a.get("isOut"), f"A at bring-up {ubrief(a)} (want standing)"
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("coopIntentsSent"), dict) and isinstance(es.get("intentsReceived"), dict)
                and "lastActionHalt" in es and "lastAftermath" in es), (
            f"{gc.name} event_state lacks the W2-P4 probes: coopIntentsSent={es.get('coopIntentsSent')!r} "
            f"intentsReceived={es.get('intentsReceived')!r}")
    mods = {gc.name: touch(gc) for gc in (host, client)}
    assert not any(v for m in mods.values() for v in m.values()), f"touch flags at bring-up {mods} (want all off)"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p4-se] boot ok: {MISSION} MAP_FP={MAP_FP!r} mod={ml} turn={hs['turn']} seated={seated_uids} "
          f"H={H_ID} pinned={len(pinned)} touch={mods} C={ubrief(ub.get(C_ID))} A={ubrief(ub.get(A_ID))} "
          f"A2={ubrief(ub.get(A2_ID))}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49878, make_user_dir("w2p4_client_rules_host", mods=[MOD_DIR]))
    client = GameClient("client", 49879, make_user_dir("w2p4_client_rules_client", mods=[MOD_DIR]))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p4-se] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_rules: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
