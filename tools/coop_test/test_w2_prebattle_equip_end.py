"""W2-P8b - test_w2_prebattle_equip_end.py: a co-op battle that starts with no live
alien ends for BOTH players (spec docs rewrite/prompts/w2p8b_prebattle_equip.md: owner
D210 b, the draft's (b)11 and (f) EQ24; AMENDMENT P8b-1 section 4 S-E (the pinned stage
text: `abandonPreparedOffer` gains the emitted case, the `battle_end` envelope helper
extracted from `coopHostBattleEnd`, reason `aliensCrashed`, aborted false, inExitArea 1,
the X-COM verdict `win`, the Handshake latch `equip.abortPending`; the client's teardown
keeps P7's wait for the host's `bt_debrief_result`, then sets AliensCrashState, whose
vanilla OK pushes the display-only DebriefingState), section 2 (F2757: the client's
force-close never touches the pre-battle screen), section 5 rows EQ24 / EQ24b, section 8;
P8b-1 RULINGS Q16 (a): the test-only client lever `hold_battle_ready`; ORCHESTRATOR
RULING Q10 (a); veto line V4; AMENDMENT P8b-2 T0-5 (F3323) and the TASK 0 constants
F3326). Stage S-F adds its boots F1 (EQ25) and F2 (EQ26) to this file (owner D215 a:
a player with nothing to equip sees vanilla's Turn-1 screen at once and it stays until
the partner is ready; P8b-1 section 4 S-F, section 5 rows EQ25 / EQ26; P8b-2 T0-9).

Before S-E.2 (product untouched, commit S-E.1) the host's battle file is already out
when its briefing OK finds no live alien (the offer goes out at PREPARE, S-A), and
`abandonPreparedOffer` is a no-op once the offer was emitted: the host shows vanilla's
"all aliens killed" screen and nothing reaches the second player, which stays on its
pre-battle equip screen (T0-5, F3323; F2759).

Staging (T0-5's lever, F3323; a FIXTURE note, F3640): battle_set_unit_state {unit,
status: STATUS_DEAD} for every live alien. T0-5 applied it to the host only; the lever
writes no wire message and the host's delta snapshot absorbs it (its own contract:
applied by the harness to EACH machine with the same absolute arguments, client first,
F607), so a host-only write leaves a hashed bucket unequal for the rest of the battle
(T0-6 / F3324's mechanism) and the `battle_end` `h` could never verify. The write goes to
BOTH machines here, client first; the host's half is T0-5's exact recipe. The staging
record keeps the bucket diff after the client's half alone (evidence that the write is
hashed) and after both halves (must be []).

Boot E1 (ONE boot): the roster-pinned lobby (set_seed SEED_ROSTER before
open_new_battle), session.bring_up_to_briefings (the client seated C1, C2; the host keeps
H), set_seed SEED_MAP right before newbattle_ok, the host's mapFingerprint = MAP_FP.
Spine: the client's BriefingState (<= 30 s, D210 b); the host in phase Active (the
client's battle_ready arrived); the client's close_briefing -> its pre-battle screen;
the staging. Then:
  EQ24  (S-E, D210 b, Q10 a) the host's close_briefing with no live alien. GREEN: the
        host's top AliensCrashState (vanilla); the host's battleEnd record emitted 1,
        reason aliensCrashed, aborted false, inExitArea 1, perSeatVerdict win for seats
        0 and 1, tally liveAliens 0, hBuckets = the 9 action-end buckets; the client
        applies it (applied 1, the host's seq, reason, aborted, inExitArea, verdicts and
        tally); the client's pre-battle screen stays on top for HOLD_S (the teardown
        waits for the host's debrief result), equip.forceCloseSkips grows and
        invForcedCloses.count is unchanged (F2757); the host's OK on its AliensCrashState
        -> its DebriefingState, resultSent 1; the client's top AliensCrashState (no
        InventoryState left on its stack) within CLIENT_LEAVE_S; the client's teardown
        record (skirmish, not in the drain, no desync, queue 0, lastSeqApplied = the
        host's seq, hashVerify of the battle_end over the host's hBuckets, bstatePushes
        = b0, resultReceived 1 with the host's bytes, tornDownMs >= resultReceivedMs);
        the client's OK on its AliensCrashState -> its DebriefingState, display-only,
        debriefDisplayOnly 1, the seven content fields equal to the host's debriefing.
        RED: no battle_end reaches the client; it stays on its pre-battle screen.
Boot E2 (ONE boot): as E1, plus pre_newbattle = the CLIENT's hold_battle_ready {on:
true} (Q16 a; test_w2_prebattle_equip_rejoin.py Boot W's recipe), so the host stays in
phase Handshake (the host closes its briefing before the client's battle_ready). Spine:
the client's BriefingState with its battle_ready held; the client's close_briefing ->
its pre-battle screen (the client is Active, the host Handshake); the staging (F3364 /
ruling SA-5: in phase Handshake revealHostile is ABSENT from the host's hash_now, every
other bucket EQUAL). Then:
  EQ24b (S-E, Q16) the host's close_briefing in phase Handshake, then the client's
        hold_battle_ready {on: false}. GREEN: after the close the host's top
        AliensCrashState, phase Handshake, equip.abortPending true, battleEnd.emitted 0
        (nothing goes out before Active); after the release the host leaves Handshake,
        abortPending false, and every EQ24 GREEN cell above. RED: no battle_end reaches
        the client after the release (no Handshake latch; abortPending stays false).
  RED (commit S-E.1): exactly EQ24 and EQ24b fail, each on its RED cell.
Boot E3 (ONE boot; stage S-E.3, P8b-2i ruling SE-4, F3684): Boot E2's bring-up and spine
on its own lobby port (the client's battle_ready held, the host in phase Handshake, the
client on its pre-battle screen, the aliens staged on both machines per SE-1). Then:
  EQ24c (S-E.3, D210 b, SE-4) the host's close_briefing in phase Handshake, then the
        host's OK on its AliensCrashState (dismiss_popup = the real btnOkClick) -> its
        DebriefingState while still in Handshake; snapshot A; then the client's
        hold_battle_ready {on: false}; the host's debriefing OK is never pressed.
        Snapshot A (RED and GREEN): the host's top DebriefingState, phase Handshake,
        equip.abortPending true, battleEnd emitted 0 and resultSent 0; the client
        applied 0, its pre-battle screen on top. GREEN after the release: the host's
        phase Ended, abortPending false, resultSent 1, and the client part of EQ24's
        GREEN cells (the host's battle_end record, the client applies it, F2757, the
        client's AliensCrashState within CLIENT_LEAVE_S, its teardown record, its OK ->
        its display-only DebriefingState equal to the host's). EQ24's client hold and
        its host OK step are not run (the host pressed its OK before the release).
        RED (today, F3684 / F3731): after the release the host's phase Active with
        abortPending true and emitted 0 (its debriefing deleted the battle before the
        latch's send could read it); no battle_end reaches the client, which stays on
        its pre-battle screen.
  RED (commit S-E.3a): exactly EQ24c fails on its RED cell; EQ24 and EQ24b pass.
Boot F1 (ONE boot; stage S-F): Boot E1's bring-up with NO soldier seated to the client
(seat_count 0 = drive_to_battlescape's seat_client=False: a spectator); the host keeps
every craft soldier (ALL_IDS). Spine (spine_f): both briefings (the client's <= 30 s,
D210 b), the host in phase Active, turn 0 on both; nothing closed. Then:
  EQ25  (S-F, D215 a) the client's close_briefing while the host still reads its
        briefing. GREEN: the client's top is vanilla's Turn-1 screen (NextTurnState)
        at once, no equip screen on its stack, turn 0 on both; ONE real key
        (inject_input SDLK_RETURN) and then the close_nextturn lever (the real
        NextTurnState::close; never dismiss_popup, F3113) each leave it on top with
        turn 0 on both and equip.heldTurnScreenPresses +1 (the hold counts every
        close() it swallows); the host's close_briefing -> its pre-battle screen on its
        own soldier while the client's Turn-1 screen stays; the host's OK (the real
        click) -> the barrier: barrierDone, turn 1 on both, the equip phase ended on
        both, no InventoryState left; the client's Turn-1 screen still on top, then ONE
        real key closes it (BattlescapeState, no held press counted); the host's
        hostScreens.closes and hostCovered unchanged since the spine (P8b-1 section 2,
        STOP-IF 12). RED: the client on its map, no Turn-1 screen (S-A's interim:
        nothing is pushed for a seat with nothing to equip).
Boot F2 (ONE boot; stage S-F): Boot E1's bring-up with EVERY craft soldier seated to
the client (P8b-2 T0-9's recipe: seat until newbattle_seat_soldier refuses - SEAT_ALL
seated, index SEAT_ALL refused); the host commands no soldier. Spine: spine_f. Then:
  EQ26  (S-F, D215 a) the host's close_briefing while the client still reads its
        briefing. GREEN: the host's top is its Turn-1 screen, no InventoryState on its
        stack, turn 0 on both; ONE real key and then close_nextturn each leave it on
        top (turn 0, heldTurnScreenPresses +1 each); the client's close_briefing -> its
        pre-battle screen on its own soldier, its ground = the host's pile ids, the
        host's Turn-1 screen still up; the client's OK (the real click) -> the barrier:
        barrierDone, turn 1 on both, the phase ended on both, no InventoryState left;
        the host's Turn-1 screen still on top, then ONE real key closes it; hostScreens
        .closes and hostCovered unchanged since the spine. RED: the host's pre-battle
        equip screen opens on a client soldier (or empty) - the host commands none.
  RED (commit S-F.1): exactly EQ25 and EQ26 fail, each on its RED cell; EQ24, EQ24b and
  EQ24c pass.

Common asserts before each ending (both machines in the battle): hash_now {full:true}
every bucket EQUAL after the queues drain (E2, phase Handshake: SA-5's rule above);
desyncSeen false on both; the client's turnMirrorFired 0; coopClientBStatePushes 0 on
both; the client's invLocalWrites 0; while the client's pre-battle screen is open its
ground ids = the host's pile ids (STOP-IF 8); both battleEnd records at emitted 0 /
applied 0. After the ending the battle is gone on both machines, so the client's
teardown record (hashVerify, desyncAtTeardown, bstatePushesAtTeardown) carries them.

Constants (AMENDMENT P8b-2 / docs rewrite/w2p8b-task0/t0/logs): SEED_ROSTER 1, SEED_MAP 1,
MAP_FP, C [8, 9], H [10..14], PILE (14, 19, 1) (tseed_parallel.log, F3326, through
test_w2_prebattle_equip.py); ALIEN_IDS [1000000] (t05.log: "[T0-5] host live aliens
before staging: [(1000000, 'STR_SECTOID_SOLDIER', 0)]"); the battle_end payload values
(P8b-1 section 4 S-E); H_BUCKETS, DEBRIEF_WIDGETS, DEBRIEF_FIELDS, CLIENT_LEAVE_S and
HOST_HOLD_S from test_w2_battle_end.py (W2-P7). S-F: ALL_IDS [8..14] and SEAT_ALL 7
(P8b-2 T0-9, t09.log: "seated to seat 1: count=7 soldierIds=[8, 9, 10, 11, 12, 13, 14];
refusal at index 7"); Boots F1/F2 keep MAP_FP and PILE (measured at 38a3d5b62 by the
S-F red's scratch bring-up: mapFingerprint = MAP_FP on both machines, equip.pile =
PILE on both, for both seatings). Boots F1/F2 end each row with the common asserts
below (test_w2_prebattle_equip's tail).

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked, then
"PASS <id>" / "FAIL <id>: <message>"; main() runs every boot even after an earlier one
failed; a boot's bring-up or spine failure fails its row. Every wait is bounded.
WV-D99 / WV-D100: one run is the result; no skip path, no re-boot. Exit 0 only when
every row passes, 2 otherwise. WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_prebattle_equip_end.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
from test_w2_delta_core import short, hashes
from test_w2_host_combat import bring_up_lobby_roster_pinned
from test_w2_prebattle_equip import (SEED_MAP, MAP_FP, C_IDS, H_IDS, PILE, COOP_SEAT_0, FACTION_PLAYER,
                                     EQ1_WAIT_S, ENTRY_WAIT_S, DRAIN_WAIT_S, stack, top, has, es, equip, turn,
                                     inv_view, view_brief, screen_up, ground_ids, pile_ids, wait_until, evidence,
                                     finish, drained, tail_fails, ok_press, SDLK_RETURN, CLICK_WAIT_S, BARRIER_WAIT_S)
from test_w2_delta_items import items_by_id
from test_w2_battle_end import (H_BUCKETS, DEBRIEF_WIDGETS, DEBRIEF_FIELDS, CLIENT_LEAVE_S, HOST_HOLD_S, verdicts,
                                tally, debrief_view)

PORT_E1 = "48837"                  # Boot E1's lobby port (unused by every other test file)
PORT_E2 = "48838"                  # Boot E2's lobby port (unused by every other test file)
PORT_E3 = "48839"                  # Boot E3's lobby port (unused by every other test file)
FACTION_HOSTILE = 1
STATUS_DEAD = 6                    # src/Mod/Unit.h enum UnitStatus (T0-5's staging value)
ALIEN_IDS = [1000000]              # t05.log: the host's live aliens before the staging at SEED_MAP 1

# ----- S-F: nothing to equip (owner D215 a; AMENDMENT P8b-1 section 4 S-F, section 5 rows EQ25 / EQ26) -----
PORT_F1 = "48846"                  # Boot F1's lobby port (unused by every other test file)
PORT_F2 = "48847"                  # Boot F2's lobby port (unused by every other test file)
ALL_IDS = [8, 9, 10, 11, 12, 13, 14]   # the craft's soldiers = C + H (F3326); t09.log "seated to seat 1: count=7
                                       # soldierIds=[8, 9, 10, 11, 12, 13, 14]"
SEAT_ALL = 7                       # t09.log: "count=7 ...; refusal at index 7" (P8b-2 T0-9's seat-everyone recipe)
COOP_SEAT_1 = 1
TURN_SCREEN = "NextTurnState"      # vanilla's "Turn 1" screen
KEY_WAIT_S = 3.0                   # one real key closes a released Turn-1 screen (EQ8's bound)

# ----- the aliens-crashed battle_end (AMENDMENT P8b-1 section 4 S-E) -----
REASON = "aliensCrashed"
ABORTED = False
IN_EXIT_AREA = 1
VERDICTS = [(0, "win"), (1, "win")]   # both seats are X-COM in a parallel co-op skirmish

# ----- waits -----
ACTIVE_WAIT_S = 30.0               # Boot E1: the host's phase Active (the client's battle_ready arrived)
CRASH_WAIT_S = 5.0                 # the host's AliensCrashState after its briefing OK (T0-5: at once)
END_WAIT_S = 10.0                  # the client applies the host's battle_end
PHASE_WAIT_S = 10.0                # Boot E2: the host leaves Handshake after the release
DEBRIEF_WAIT_S = 10.0              # a DebriefingState after an AliensCrashState OK
RESULT_WAIT_S = 5.0                # the host's resultSent after its DebriefingState
POLL_S = 0.05


# ===================== probes =====================


def record(gc):
    """This machine's event_state.battleEnd (W2-P7's session-lifetime record; {} when absent)."""
    try:
        r = event_state(gc).get("battleEnd")
    except Exception as e:  # a dead instance
        return {"error": short(e, 200)}
    return r if isinstance(r, dict) else {}


def rec_brief(r):
    keys = ("emitted", "applied", "seq", "reason", "aborted", "inExitArea", "perSeatVerdict", "tally",
            "actionIdAtEmit", "hBuckets", "skirmish", "latchedMs", "tornDownMs", "teardownInDrain",
            "desyncAtTeardown", "bstatePushesAtTeardown", "queueDepthAtTeardown", "lastSeqApplied", "hashVerify",
            "inventoryOpenAtTeardown", "resultSent", "resultReceived", "resultBytes", "resultReceivedMs",
            "resultWaitPasses", "resultDropped", "debriefDisplayOnly", "error")
    return {k: r.get(k) for k in keys if k in r}


def forced(gc):
    """event_state.invForcedCloses (W2-P8 S-C1: the client's inventory force-closes)."""
    v = es(gc).get("invForcedCloses")
    return v if isinstance(v, dict) else {}


def dump(gc):
    """One machine's probe dump (the FIXTURE-STOP rule's evidence)."""
    try:
        bs = battle_state(gc)
        e = es(gc)
        q = e.get("equip") or {}
        return {"stack": stack(gc), "phase": e.get("phase"), "turn": bs.get("turn"), "inBattle": bs.get("inBattle"),
                "desyncSeen": e.get("desyncSeen"), "bstatePushes": e.get("coopClientBStatePushes"),
                "lastSeqEmitted": e.get("lastSeqEmitted"), "lastSeqApplied": e.get("lastSeqApplied"),
                "queueDepth": e.get("queueDepth"),
                "equip": {k: q.get(k) for k in ("phase", "hostOpen", "openAnnounced", "abortPending", "screen",
                                                "entries", "closes", "forceCloseSkips", "barrierDone")},
                "invForcedCloses": e.get("invForcedCloses"), "battleEnd": rec_brief(record(gc)),
                "view": view_brief(inv_view(gc))}
    except Exception as ex:  # a dead instance
        return {"error": short(ex, 200)}


def debrief(gc):
    r = gc.cmd({"cmd": "debrief_state"})
    return {k: r.get(k) for k in ("shown", "onTop", "displayOnly", "widgets", "page", "parseErrors")
            + DEBRIEF_FIELDS}


def live_aliens(gc):
    return [{"id": u["id"], "type": u.get("type"), "status": u.get("status")}
            for u in battle_state(gc).get("units", [])
            if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]


def hold(client, **kw):
    req = {"cmd": "hold_battle_ready"}
    req.update(kw)
    r = client.cmd(req)
    return {k: r.get(k) for k in ("ok", "error", "armed", "held", "sent")}


def bucket_diff(host, client):
    """Every hash_now {full:true} bucket that differs - with ruling SA-5 (F3364): while the host is in phase
    Handshake its revealHostile is skipped and must be ABSENT from the host's hash_now. Returns (diff, note)."""
    hh, ch = hashes(host), hashes(client)
    handshake = es(host).get("phase") == "Handshake"
    skip = {"revealHostile"} if handshake else set()
    diff = sorted(k for k in (set(hh) | set(ch)) - skip if hh.get(k) != ch.get(k))
    note = {"handshake": handshake, "revealHostile": [hh.get("revealHostile"), ch.get("revealHostile")]}
    if handshake and "revealHostile" in hh:
        note["error"] = (f"the host is in phase Handshake but its hash_now carries revealHostile "
                         f"{hh['revealHostile']!r} (want ABSENT: W1-P8 allocates it at onReady)")
    return diff, note


def common_fails(host, client, what):
    """The common asserts before an ending (both machines in the battle). Phase Active: test_w2_prebattle_equip's
    tail. Phase Handshake (Boot E2): the same checks with SA-5's bucket rule."""
    if es(host).get("phase") != "Handshake":
        return tail_fails(host, client, what)
    fails = []
    got, _ = wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    if not got:
        fails.append(f"{what}: the client never caught up (host lastSeqEmitted {es(host).get('lastSeqEmitted')}, "
                     f"client lastSeqApplied {es(client).get('lastSeqApplied')})")
    diff, note = bucket_diff(host, client)
    if diff:
        fails.append(f"{what}: hash_now full buckets differ: {diff} (want every bucket EQUAL but revealHostile, "
                     f"SA-5)")
    if note.get("error"):
        fails.append(f"{what}: {note['error']}")
    eh, ec = es(host), es(client)
    if eh.get("desyncSeen") or ec.get("desyncSeen"):
        fails.append(f"{what}: desyncSeen host={eh.get('desyncSeen')} client={ec.get('desyncSeen')} (want false)")
    if ec.get("turnMirrorFired") != 0:
        fails.append(f"{what}: client turnMirrorFired={ec.get('turnMirrorFired')} (want 0)")
    if ec.get("coopClientBStatePushes") != 0 or eh.get("coopClientBStatePushes") != 0:
        fails.append(f"{what}: coopClientBStatePushes host={eh.get('coopClientBStatePushes')} "
                     f"client={ec.get('coopClientBStatePushes')} (want 0 on both)")
    if ec.get("invLocalWrites") != 0:
        fails.append(f"{what}: client invLocalWrites={ec.get('invLocalWrites')} (want 0)")
    cv = inv_view(client)
    if cv.get("open") and cv.get("preBattle"):
        hp = pile_ids(items_by_id(host))
        if ground_ids(cv) != hp:
            fails.append(f"{what}: STOP-IF 8 - the client's pre-battle ground {ground_ids(cv)} != the host's pile "
                         f"ids {hp}")
    return fails


# ===================== the spine =====================


def stage_aliens(host, client, ctx):
    """T0-5's staging on both machines (client first, F607): every live alien -> STATUS_DEAD. The record keeps
    the ids, the bucket diff after the client's half alone (evidence: the write is hashed) and after both."""
    rec = {}
    try:
        rec["aliensHost"] = live_aliens(host)
        rec["aliensClient"] = live_aliens(client)
        ids = [a["id"] for a in rec["aliensHost"]]
        rec["ids"] = ids
        rec["client"] = {}
        rec["host"] = {}
        for i, aid in enumerate(ids):
            rc = client.cmd({"cmd": "battle_set_unit_state", "unit": aid, "status": STATUS_DEAD})
            rec["client"][aid] = {k: rc.get(k) for k in ("ok", "error", "status")}
            if i == 0:
                rec["diffAfterClientOnly"], _ = bucket_diff(host, client)
            rh = host.cmd({"cmd": "battle_set_unit_state", "unit": aid, "status": STATUS_DEAD})
            rec["host"][aid] = {k: rh.get(k) for k in ("ok", "error", "status")}
        rec["diff"], rec["hashNote"] = bucket_diff(host, client)
        rec["liveAfter"] = {"host": live_aliens(host), "client": live_aliens(client)}
        rec["turn"] = [turn(host), turn(client)]
        rec["hostPhase"] = es(host).get("phase")
    except Exception as e:
        rec["error"] = short(e, 400)
    ctx["staged"] = rec
    print(f"STAGE {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    return rec


def staged_fails(ctx, what):
    s = ctx.get("staged")
    if not s:
        return [f"{what}: FIXTURE - nothing staged"]
    if s.get("error"):
        return [f"{what}: FIXTURE - the staging failed: {s['error']}"]
    fails = []
    if s.get("ids") != ALIEN_IDS:
        fails.append(f"{what}: FIXTURE - the host's live aliens {s.get('aliensHost')} (want ids {ALIEN_IDS}, t05.log)")
    for side in ("client", "host"):
        bad = {a: r for a, r in (s.get(side) or {}).items() if not r.get("ok") or r.get("status") != STATUS_DEAD}
        if bad:
            fails.append(f"{what}: FIXTURE - the {side}'s battle_set_unit_state answers {bad}")
    if s.get("diff"):
        fails.append(f"{what}: FIXTURE - buckets differ after the staging: {s['diff']}")
    if (s.get("hashNote") or {}).get("error"):
        fails.append(f"{what}: FIXTURE - {s['hashNote']['error']}")
    la = s.get("liveAfter") or {}
    if la.get("host") or la.get("client"):
        fails.append(f"{what}: FIXTURE - live aliens after the staging host {la.get('host')} client "
                     f"{la.get('client')} (want none on both)")
    return fails


def spine_e1(host, client, ctx):
    """Boot E1's spine: the client's briefing (<= 30 s); the host in phase Active; the client's close_briefing ->
    its pre-battle screen; the staging."""
    rec = {}
    g0, d0 = wait_until(lambda: has(client, "BriefingState"), EQ1_WAIT_S, 0.1)
    g1, d1 = wait_until(lambda: es(host).get("phase") == "Active", ACTIVE_WAIT_S, 0.1)
    c = client.cmd({"cmd": "close_briefing"}) if g0 else {"error": "no client BriefingState"}
    g2, d2 = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    rec.update({"clientBriefingWithin": d0 if g0 else None, "hostActiveWithin": d1 if g1 else None,
                "clientClose": {k: c.get(k) for k in ("ok", "error")}, "clientScreenWithin": d2 if g2 else None})
    if g0 and g2:
        stage_aliens(host, client, ctx)
    rec.update({"host": dump(host), "client": dump(client)})
    print(f"SPINE E1: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not (g0 and g1 and g2 and top(host) == "BriefingState"):
        raise AssertionError(f"spine: Boot E1's client screen / host briefing in phase Active never held ({rec})")


def spine_e2(host, client, ctx):
    """Boot E2's spine (Boot E3 reuses it, ctx tag "E3"): the client's briefing (<= 30 s) with its battle_ready
    held (the host stays in phase Handshake); the client's close_briefing -> its pre-battle screen; the staging."""
    tag = ctx.get("tag", "E2")
    rec = {"arm": ctx.get("arm")}
    g0, d0 = wait_until(lambda: has(client, "BriefingState"), EQ1_WAIT_S, 0.1)
    rec["hold1"] = hold(client)
    c = client.cmd({"cmd": "close_briefing"}) if g0 else {"error": "no client BriefingState"}
    g2, d2 = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    rec.update({"clientBriefingWithin": d0 if g0 else None,
                "clientClose": {k: c.get(k) for k in ("ok", "error")}, "clientScreenWithin": d2 if g2 else None})
    if g0 and g2:
        stage_aliens(host, client, ctx)
    rec.update({"host": dump(host), "client": dump(client)})
    print(f"SPINE {tag}: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not (g0 and g2 and rec["hold1"].get("held") is True and rec["host"].get("phase") == "Handshake"
            and top(host) == "BriefingState"):
        raise AssertionError(f"spine: Boot {tag}'s client screen / host briefing in phase Handshake never held ({rec})")


# ===================== the ending (shared GREEN cells) =====================


def pre_ending(host, client, row, ctx, want_phase):
    """The precondition and the common asserts right before the host's briefing OK; returns (fails, base)."""
    fails = []
    if not screen_up(client):
        fails.append(f"{row}: precondition absent - no client pre-battle screen (client {dump(client)})")
    if top(host) != "BriefingState":
        fails.append(f"{row}: precondition absent - the host is not in its briefing (host stack {stack(host)})")
    if es(host).get("phase") != want_phase:
        fails.append(f"{row}: precondition absent - host phase {es(host).get('phase')!r} (want {want_phase})")
    fails += staged_fails(ctx, row)
    fails += common_fails(host, client, f"{row} (before the ending)")
    hrec, crec = record(host), record(client)
    for name, r in (("host", hrec), ("client", crec)):
        if r.get("emitted") != 0 or r.get("applied") != 0:
            fails.append(f"{row}: {name} battleEnd before the ending {rec_brief(r)} (want emitted 0, applied 0)")
    base = {"forceCloseSkips": equip(client).get("forceCloseSkips"), "invForcedCloses": forced(client).get("count"),
            "b0": es(client).get("coopClientBStatePushes"), "host": dump(host), "client": dump(client)}
    return fails, base


def host_close(host, ev):
    """The host's close_briefing (T0-5): vanilla's no-aliens branch pushes AliensCrashState."""
    r = host.cmd({"cmd": "close_briefing"})
    g, d = wait_until(lambda: top(host) == "AliensCrashState", CRASH_WAIT_S)
    ev["hostClose"] = {"close": {k: r.get(k) for k in ("ok", "error")}, "crashWithin": d if g else None,
                       "hostStack": stack(host), "hostPhase": es(host).get("phase"),
                       "abortPending": equip(host).get("abortPending"), "emitted": record(host).get("emitted")}
    if not g:
        return [f"FIXTURE - the host's briefing OK left top {top(host)!r}, not AliensCrashState (host stack "
                f"{stack(host)}; T0-5)"]
    return []


def client_hold(client):
    """The client's top sampled every 0.25 s for HOST_HOLD_S: the distinct tops that are not its pre-battle
    InventoryState, in first-seen order ([] = its equip screen held the top throughout)."""
    seen = []
    t0 = time.time()
    while True:
        t = top(client)
        if t != "InventoryState" and t not in seen:
            seen.append(t)
        if time.time() - t0 >= HOST_HOLD_S:
            return seen
        time.sleep(0.25)


def ending_green(host, client, row, ev, base):
    """EQ24's GREEN cells after the client applied the host's battle_end (EQ24, EQ24b): the host-OK part (the
    hold, the host's OK), then the client part (the client's AliensCrashState, its OK and the display-only debrief,
    and every check). Fills ev; returns the failures."""
    ending_host_ok(host, client, ev)
    return ending_client(host, client, row, ev, base)


def ending_host_ok(host, client, ev):
    """The host-OK part of EQ24's GREEN cells: the client's pre-battle screen holds while the host's
    AliensCrashState is up, then the host's OK -> its DebriefingState and the debrief result. Collects into ev
    (clientHold, hostOk); ending_client checks it."""
    # 1. the client's pre-battle screen stays until the host's OK (the teardown waits for the debrief result)
    h = {"seen": client_hold(client), "view": view_brief(inv_view(client)),
         "tornDownMs": record(client).get("tornDownMs"), "resultWaitPasses": record(client).get("resultWaitPasses"),
         "forceCloseSkips": equip(client).get("forceCloseSkips"), "invForcedCloses": forced(client).get("count")}
    ev["clientHold"] = h
    # 2. the host's OK on its AliensCrashState -> its DebriefingState, the debrief result sent
    hp = host.cmd({"cmd": "dismiss_popup"}) if top(host) == "AliensCrashState" else {"note": f"host top {top(host)}"}
    g1, d1 = wait_until(lambda: top(host) == "DebriefingState", DEBRIEF_WAIT_S)
    g2, d2 = wait_until(lambda: record(host).get("resultSent") == 1, RESULT_WAIT_S)
    ev["hostOk"] = {"press": {k: hp.get(k) for k in ("ok", "handled", "error", "note")},
                    "debriefWithin": d1 if g1 else None, "resultSentWithin": d2 if g2 else None,
                    "hostStack": stack(host)}


def ending_client(host, client, row, ev, base, host_ok=True):
    """The client part of EQ24's GREEN cells after the client applied the host's battle_end: the client's
    AliensCrashState, its OK and the display-only debrief. Prints the row's EVIDENCE line, then checks the whole
    ending: with host_ok (EQ24, EQ24b) also the host-OK part's cells; without it (EQ24c: its host pressed the OK
    before the release) F2757's counters are read here instead of after the hold. Returns the failures."""
    fails = []
    if not host_ok:
        # F2757's counters (they reset only in initBattleAuthority(), so they outlive the client's teardown)
        ev["clientF2757"] = {"forceCloseSkips": equip(client).get("forceCloseSkips"),
                             "invForcedCloses": forced(client).get("count")}
    # 3. the client's AliensCrashState
    g3, d3 = wait_until(lambda: top(client) == "AliensCrashState", CLIENT_LEAVE_S, 0.1)
    ev["clientCrash"] = {"within": d3 if g3 else None, "stack": stack(client), "record": rec_brief(record(client)),
                         "equip": dump(client).get("equip")}
    # 4. the client's OK on its AliensCrashState -> its display-only DebriefingState
    cp = client.cmd({"cmd": "dismiss_popup"}) if g3 else {"note": f"client top {top(client)}"}
    g4, d4 = wait_until(lambda: top(client) == "DebriefingState", DEBRIEF_WAIT_S)
    ev["clientOk"] = {"press": {k: cp.get(k) for k in ("ok", "handled", "error", "note")},
                      "debriefWithin": d4 if g4 else None, "stack": stack(client)}
    hrec, crec = record(host), record(client)
    hdeb, cdeb = debrief(host), debrief(client)
    ev["end"] = {"hostRecord": rec_brief(hrec), "clientRecord": rec_brief(crec), "hostDebrief": hdeb,
                 "clientDebrief": cdeb, "hostDesyncSeen": es(host).get("desyncSeen"), "host": dump(host),
                 "client": dump(client)}
    evidence(row, ev)
    # --- the host's battle_end (P8b-1 section 4 S-E) ---
    hseq = hrec.get("seq")
    if hrec.get("emitted") != 1:
        fails.append(f"{row}: host battleEnd.emitted={hrec.get('emitted')} (want 1)")
    if not isinstance(hseq, int) or hseq <= 0:
        fails.append(f"{row}: host battleEnd.seq={hseq} (want > 0)")
    for k, want in (("reason", REASON), ("aborted", ABORTED), ("inExitArea", IN_EXIT_AREA)):
        if hrec.get(k) != want:
            fails.append(f"{row}: host battleEnd.{k}={hrec.get(k)!r} (want {want!r})")
    if verdicts(hrec) != VERDICTS:
        fails.append(f"{row}: host battleEnd.perSeatVerdict={hrec.get('perSeatVerdict')} (want {VERDICTS})")
    if tally(hrec).get("liveAliens") != 0:
        fails.append(f"{row}: host battleEnd.tally={hrec.get('tally')} (want liveAliens 0)")
    if sorted(hrec.get("hBuckets") or []) != H_BUCKETS:
        fails.append(f"{row}: host battleEnd.hBuckets={hrec.get('hBuckets')} (want {H_BUCKETS})")
    if ev["end"]["hostDesyncSeen"]:
        fails.append(f"{row}: host desyncSeen={ev['end']['hostDesyncSeen']} (want false)")
    # --- the client applied it ---
    if crec.get("applied") != 1 or crec.get("seq") != hseq:
        fails.append(f"{row}: client battleEnd applied={crec.get('applied')} seq={crec.get('seq')} (want 1, the "
                     f"host's seq {hseq})")
    for k in ("reason", "aborted", "inExitArea"):
        if crec.get(k) != hrec.get(k):
            fails.append(f"{row}: client battleEnd.{k}={crec.get(k)!r} != the host's {hrec.get(k)!r}")
    if verdicts(crec) != verdicts(hrec) or tally(crec) != tally(hrec):
        fails.append(f"{row}: client battleEnd verdicts/tally {crec.get('perSeatVerdict')} {crec.get('tally')} != "
                     f"the host's {hrec.get('perSeatVerdict')} {hrec.get('tally')}")
    # --- the hold and F2757 ---
    h = ev["clientHold"] if host_ok else ev["clientF2757"]
    if host_ok:
        if h["seen"] != []:
            fails.append(f"{row}: the client's top left its pre-battle screen before the host's OK (tops seen "
                         f"{h['seen']} within {HOST_HOLD_S} s; want [] - the teardown waits for the host's debrief "
                         f"result)")
        if not (h["view"].get("preBattle") is True and h["view"].get("top") is True):
            fails.append(f"{row}: after the hold the client's view {h['view']} (want its pre-battle screen on top)")
        if h["tornDownMs"] not in (0, None):
            fails.append(f"{row}: the client was torn down before the host's OK (tornDownMs {h['tornDownMs']})")
    f0, f1 = base.get("forceCloseSkips"), h.get("forceCloseSkips")
    if not (isinstance(f0, int) and isinstance(f1, int) and f1 > f0):
        fails.append(f"{row}: client equip.forceCloseSkips {f0} -> {f1} (want it to grow: the battle_end force-close "
                     f"skips the pre-battle screen, F2757)")
    if h.get("invForcedCloses") != base.get("invForcedCloses"):
        fails.append(f"{row}: client invForcedCloses.count {base.get('invForcedCloses')} -> {h.get('invForcedCloses')} "
                     f"(want unchanged, F2757)")
    # --- the host's OK and its debriefing ---
    if host_ok:
        if (ev["hostOk"]["press"].get("handled")) != "AliensCrashState":
            fails.append(f"{row}: the host's OK answered {ev['hostOk']['press']} (want handled AliensCrashState)")
        if ev["hostOk"]["debriefWithin"] is None:
            fails.append(f"{row}: no host DebriefingState within {DEBRIEF_WAIT_S} s of its OK (host stack "
                         f"{ev['hostOk']['hostStack']})")
        if ev["hostOk"]["resultSentWithin"] is None:
            fails.append(f"{row}: host battleEnd.resultSent={hrec.get('resultSent')} (want 1)")
        for k, want in (("shown", True), ("onTop", True), ("displayOnly", False), ("page", 0), ("parseErrors", 0)):
            if hdeb.get(k) != want:
                fails.append(f"{row}: host debrief_state.{k}={hdeb.get(k)!r} (want {want!r})")
        if hdeb.get("widgets") != DEBRIEF_WIDGETS:
            fails.append(f"{row}: host debrief_state.widgets={hdeb.get('widgets')} (want {DEBRIEF_WIDGETS})")
    # --- the client's AliensCrashState (Q10 a) ---
    if not g3:
        fails.append(f"{row}: the client's top {top(client)!r} {CLIENT_LEAVE_S} s after the host's OK (want "
                     f"AliensCrashState; client stack {ev['clientCrash']['stack']})")
    elif any("InventoryState" in s or "BattlescapeState" in s for s in ev["clientCrash"]["stack"]):
        fails.append(f"{row}: the client's stack {ev['clientCrash']['stack']} under its AliensCrashState still holds "
                     f"the battle (want the teardown's setState)")
    # --- the client's teardown record (P7's contract) ---
    for k, want in (("skirmish", True), ("teardownInDrain", False), ("desyncAtTeardown", False),
                    ("queueDepthAtTeardown", 0), ("lastSeqApplied", hseq), ("bstatePushesAtTeardown", base.get("b0")),
                    ("resultReceived", 1), ("resultDropped", 0), ("debriefDisplayOnly", 1)):
        if crec.get(k) != want:
            fails.append(f"{row}: client battleEnd.{k}={crec.get(k)!r} (want {want!r})")
    hv = crec.get("hashVerify") if isinstance(crec.get("hashVerify"), dict) else {}
    if (hv.get("seq") != hseq or hv.get("kind") != "battle_end"
            or sorted(hv.get("buckets") or []) != sorted(hrec.get("hBuckets") or [])):
        fails.append(f"{row}: client battleEnd.hashVerify={crec.get('hashVerify')} (want seq {hseq}, kind battle_end, "
                     f"buckets = the host's hBuckets)")
    hbytes, cbytes = hrec.get("resultBytes"), crec.get("resultBytes")
    if not (isinstance(hbytes, int) and hbytes > 0 and cbytes == hbytes):
        fails.append(f"{row}: resultBytes host={hbytes} client={cbytes} (want equal and > 0)")
    rms, tdn = crec.get("resultReceivedMs"), crec.get("tornDownMs")
    if not (isinstance(rms, int) and rms > 0 and isinstance(tdn, int) and tdn >= rms):
        fails.append(f"{row}: client tornDownMs={tdn} resultReceivedMs={rms} (want tornDownMs >= resultReceivedMs > 0: "
                     f"the teardown waited for the host's debrief result)")
    # --- the client's OK and its display-only debriefing ---
    if g3 and (ev["clientOk"]["press"].get("handled")) != "AliensCrashState":
        fails.append(f"{row}: the client's OK answered {ev['clientOk']['press']} (want handled AliensCrashState)")
    if not g4:
        fails.append(f"{row}: no client DebriefingState within {DEBRIEF_WAIT_S} s of its OK (client stack "
                     f"{ev['clientOk']['stack']})")
    for k, want in (("shown", True), ("onTop", True), ("displayOnly", True), ("page", 0), ("parseErrors", 0)):
        if cdeb.get(k) != want:
            fails.append(f"{row}: client debrief_state.{k}={cdeb.get(k)!r} (want {want!r})")
    if cdeb.get("widgets") != DEBRIEF_WIDGETS:
        fails.append(f"{row}: client debrief_state.widgets={cdeb.get('widgets')} (want {DEBRIEF_WIDGETS})")
    for k in DEBRIEF_FIELDS:
        if debrief_view(cdeb).get(k) != debrief_view(hdeb).get(k):
            fails.append(f"{row}: client debrief_state.{k}={cdeb.get(k)!r} != the host's {hdeb.get(k)!r} (page-2 prefixes stripped, AUD-A07)")
    return fails


# ===================== rows =====================


def eq24_no_aliens_start(host, client, ctx):
    ev = {}
    pre, base = pre_ending(host, client, "EQ24", ctx, "Active")
    ev["base"] = base
    if pre:
        evidence("EQ24", ev)
        finish(pre)
    fx = host_close(host, ev)
    if fx:
        evidence("EQ24", ev)
        finish([f"EQ24: {m}" for m in fx])
    g, d = wait_until(lambda: record(client).get("applied") == 1, END_WAIT_S, 0.1)
    ev["clientEndWithin"] = d if g else None
    if not g:
        ev["noEnd"] = {"host": dump(host), "client": dump(client)}
        evidence("EQ24", ev)
        finish([f"EQ24: no battle_end reached the client within {END_WAIT_S} s of the host's briefing OK (client "
                f"battleEnd {rec_brief(record(client))}, host battleEnd emitted {record(host).get('emitted')}, host "
                f"top {top(host)!r}); the client stays on its pre-battle screen (top {top(client)!r}, preBattle "
                f"{inv_view(client).get('preBattle')}) - RED: abandonPreparedOffer is a no-op once the offer was "
                f"emitted (F2759)"])
    finish(ending_green(host, client, "EQ24", ev, base))


def eq24b_no_aliens_in_handshake(host, client, ctx):
    ev = {"arm": ctx.get("arm")}
    released = False
    try:
        pre, base = pre_ending(host, client, "EQ24b", ctx, "Handshake")
        ev["base"] = base
        if hold(client).get("held") is not True:
            pre.append(f"EQ24b: precondition absent - the client's battle_ready is not held ({hold(client)})")
        if pre:
            evidence("EQ24b", ev)
            finish(pre)
        # the host's briefing OK in phase Handshake
        fx = host_close(host, ev)
        if fx:
            evidence("EQ24b", ev)
            finish([f"EQ24b: {m}" for m in fx])
        # the release
        tr = time.time()
        ev["release"] = hold(client, on=False)
        released = True
        g0, d0 = wait_until(lambda: es(host).get("phase") != "Handshake", PHASE_WAIT_S)
        g1, d1 = wait_until(lambda: record(client).get("applied") == 1, END_WAIT_S, 0.1)
        ev["afterRelease"] = {"hostLeftHandshakeWithin": d0 if g0 else None, "clientEndWithin": d1 if g1 else None,
                              "sinceRelease": round(time.time() - tr, 3), "hostPhase": es(host).get("phase"),
                              "abortPending": equip(host).get("abortPending"),
                              "hostEmitted": record(host).get("emitted")}
        if not g1:
            ev["noEnd"] = {"host": dump(host), "client": dump(client)}
            evidence("EQ24b", ev)
            finish([f"EQ24b: no battle_end reached the client within {END_WAIT_S} s of the release (client battleEnd "
                    f"{rec_brief(record(client))}, host battleEnd emitted {record(host).get('emitted')}, host phase "
                    f"{es(host).get('phase')!r}; host equip.abortPending after its briefing OK "
                    f"{ev['hostClose'].get('abortPending')}, after the release {ev['afterRelease']['abortPending']}); "
                    f"the client stays on its pre-battle screen (top {top(client)!r}) - RED: no Handshake latch"])
        fails = []
        hc = ev["hostClose"]
        if hc.get("hostPhase") != "Handshake" or hc.get("abortPending") is not True or hc.get("emitted") != 0:
            fails.append(f"EQ24b: after the host's briefing OK phase {hc.get('hostPhase')!r} abortPending "
                         f"{hc.get('abortPending')} battleEnd.emitted {hc.get('emitted')} (want Handshake, true, 0: "
                         f"the latch, nothing on the wire before Active)")
        if ev["release"].get("sent") is not True:
            fails.append(f"EQ24b: the release sent no held battle_ready ({ev['release']})")
        if not g0:
            fails.append(f"EQ24b: the host never left phase Handshake within {PHASE_WAIT_S} s of the release")
        if ev["afterRelease"]["abortPending"] is not False:
            fails.append(f"EQ24b: host equip.abortPending={ev['afterRelease']['abortPending']} after the release (want "
                         f"false: cleared at Active)")
        fails += ending_green(host, client, "EQ24b", ev, base)
        finish(fails)
    finally:
        if not released:
            rest = hold(client)
            if rest.get("armed") or rest.get("held"):
                rel = hold(client, on=False)
                print(f"[w2p8b-se] EQ24b cleanup: released the hold {rel}; host phase {es(host).get('phase')}",
                      flush=True)


def eq24c_host_ok_in_handshake(host, client, ctx):
    """EQ24c (S-E.3, SE-4, F3684): the host dismisses 'all aliens killed' while still in phase Handshake; the
    battle end must still reach the second player once its game has loaded (the release)."""
    ev = {"arm": ctx.get("arm")}
    released = False
    try:
        # (1) the precondition: Boot E2's spine state with the client's battle_ready held
        pre, base = pre_ending(host, client, "EQ24c", ctx, "Handshake")
        ev["base"] = base
        if hold(client).get("held") is not True:
            pre.append(f"EQ24c: precondition absent - the client's battle_ready is not held ({hold(client)})")
        if pre:
            evidence("EQ24c", ev)
            finish(pre)
        # (2) the host's briefing OK in phase Handshake -> its AliensCrashState
        fx = host_close(host, ev)
        if fx:
            evidence("EQ24c", ev)
            finish([f"EQ24c: {m}" for m in fx])
        # (3) the host's OK on its AliensCrashState (dismiss_popup = the real btnOkClick) -> its DebriefingState
        hp = host.cmd({"cmd": "dismiss_popup"})
        g, d = wait_until(lambda: top(host) == "DebriefingState", DEBRIEF_WAIT_S)
        ev["hostCrashOk"] = {"press": {k: hp.get(k) for k in ("ok", "handled", "error")},
                             "debriefWithin": d if g else None, "hostStack": stack(host)}
        # (4) snapshot A: the host's debriefing is up in phase Handshake, nothing has gone out
        hr, cr, cv = record(host), record(client), inv_view(client)
        a = {"hostTop": top(host), "hostPhase": es(host).get("phase"), "abortPending": equip(host).get("abortPending"),
             "emitted": hr.get("emitted"), "resultSent": hr.get("resultSent"), "clientApplied": cr.get("applied"),
             "clientTop": top(client), "clientView": view_brief(cv)}
        ev["A"] = a
        afails = []
        if hp.get("handled") != "AliensCrashState":
            afails.append(f"EQ24c: the host's OK on its AliensCrashState answered {ev['hostCrashOk']['press']} (want "
                          f"handled AliensCrashState)")
        for k, want in (("hostTop", "DebriefingState"), ("hostPhase", "Handshake"), ("abortPending", True),
                        ("emitted", 0), ("resultSent", 0), ("clientApplied", 0), ("clientTop", "InventoryState")):
            if a.get(k) != want:
                afails.append(f"EQ24c: snapshot A {k}={a.get(k)!r} (want {want!r})")
        if not (a["clientView"].get("preBattle") is True and a["clientView"].get("top") is True):
            afails.append(f"EQ24c: snapshot A client view {a['clientView']} (want its pre-battle screen on top)")
        if afails:
            evidence("EQ24c", ev)
            finish(afails)
        # (5) the release; (6) the host's debriefing OK is never pressed
        tr = time.time()
        ev["release"] = hold(client, on=False)
        released = True
        g0, d0 = wait_until(lambda: es(host).get("phase") != "Handshake", PHASE_WAIT_S)
        g1, d1 = wait_until(lambda: record(client).get("applied") == 1, END_WAIT_S, 0.1)
        g2, d2 = wait_until(lambda: record(host).get("resultSent") == 1, RESULT_WAIT_S) if g1 else (None, None)
        cv = inv_view(client)
        ev["afterRelease"] = {"hostLeftHandshakeWithin": d0 if g0 else None, "clientEndWithin": d1 if g1 else None,
                              "resultSentWithin": d2 if g2 else None, "sinceRelease": round(time.time() - tr, 3),
                              "hostPhase": es(host).get("phase"), "abortPending": equip(host).get("abortPending"),
                              "hostEmitted": record(host).get("emitted"),
                              "hostResultSent": record(host).get("resultSent"), "hostTop": top(host),
                              "clientTop": top(client), "clientPreBattle": cv.get("preBattle")}
        ar = ev["afterRelease"]
        if not g1:
            ev["noEnd"] = {"host": dump(host), "client": dump(client)}
            evidence("EQ24c", ev)
            finish([f"EQ24c: no battle_end after the release (F3684): the client's battleEnd "
                    f"{rec_brief(record(client))} (applied 1 never seen within {END_WAIT_S} s), its top "
                    f"{ar['clientTop']!r}, preBattle {ar['clientPreBattle']}; snapshot A {a}; after the release the "
                    f"host phase {ar['hostPhase']!r}, equip.abortPending {ar['abortPending']}, battleEnd emitted "
                    f"{ar['hostEmitted']}, resultSent {ar['hostResultSent']} - RED: the host's debriefing deleted the "
                    f"battle in phase Handshake, so the held battle_end never goes out (F3731)"])
        fails = []
        if ev["release"].get("sent") is not True:
            fails.append(f"EQ24c: the release sent no held battle_ready ({ev['release']})")
        if ar["hostPhase"] != "Ended":
            fails.append(f"EQ24c: host phase {ar['hostPhase']!r} after the release (want Ended; left Handshake within "
                         f"{ar['hostLeftHandshakeWithin']} s)")
        if ar["abortPending"] is not False:
            fails.append(f"EQ24c: host equip.abortPending={ar['abortPending']} after the release (want false)")
        if not g2:
            fails.append(f"EQ24c: host battleEnd.resultSent={record(host).get('resultSent')} within {RESULT_WAIT_S} s "
                         f"of the client's battle_end (want 1: the held debrief result goes out after the release)")
        fails += ending_client(host, client, "EQ24c", ev, base, host_ok=False)
        finish(fails)
    finally:
        if not released:
            rest = hold(client)
            if rest.get("armed") or rest.get("held"):
                rel = hold(client, on=False)
                print(f"[w2p8b-se] EQ24c cleanup: released the hold {rel}; host phase {es(host).get('phase')}",
                      flush=True)


# ===================== S-F: nothing to equip (owner D215 a) =====================


def brief_equip(gc):
    q = equip(gc)
    return {k: q.get(k) for k in ("phase", "hostOpen", "openAnnounced", "ready", "counted", "pile", "entryDone",
                                  "entries", "screen", "okPressed", "barrierDone", "endSyncs", "closes",
                                  "heldTurnScreenPresses")}


def presses(gc):
    """event_state.equip.heldTurnScreenPresses (S-A.1's probe): the closes of a held Turn-1 screen swallowed."""
    return equip(gc).get("heldTurnScreenPresses")


def screen_probes(host):
    """The host's screen check and covered driver, pinned unchanged across the equip phase (P8b-1 section 2: the
    host screen check never closes or toggles a pre-battle screen, STOP-IF 12; the covered driver never steps)."""
    e = es(host)
    return {"hostScreensCloses": (e.get("hostScreens") or {}).get("closes"), "hostCovered": e.get("hostCovered")}


def spine_f(host, client, ctx):
    """Boots F1/F2's spine: both briefings (the client's <= 30 s, D210 b), the host in phase Active (the client's
    battle_ready arrived), turn 0 on both; the host's screen probes recorded as the row's baseline. Closes nothing."""
    tag = ctx.get("tag")
    g0, d0 = wait_until(lambda: has(client, "BriefingState"), EQ1_WAIT_S, 0.1)
    g1, d1 = wait_until(lambda: es(host).get("phase") == "Active", ACTIVE_WAIT_S, 0.1)
    ctx["base"] = screen_probes(host)
    rec = {"clientBriefingWithin": d0 if g0 else None, "hostActiveWithin": d1 if g1 else None,
           "turn": [turn(host), turn(client)], "base": ctx["base"], "refusal": ctx.get("refusal"),
           "hostEquip": brief_equip(host), "clientEquip": brief_equip(client), "host": dump(host),
           "client": dump(client)}
    print(f"SPINE {tag}: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    cq = equip(client)
    if not (g0 and g1 and top(host) == "BriefingState" and top(client) == "BriefingState" and rec["turn"] == [0, 0]
            and "heldTurnScreenPresses" in cq and cq.get("pile") == list(PILE)):
        raise AssertionError(f"spine: Boot {tag}'s two briefings in phase Active at turn 0, the client's equip.pile "
                             f"{list(PILE)}, never held ({rec})")


def turn_screen_held(gc, host, client, who, row, ev):
    """D215 a's hold on `gc`'s Turn-1 screen while the equip phase is open: ONE real key (inject_input SDLK_RETURN;
    NextTurnState::handle turns a KEYDOWN into close()), then the close_nextturn lever (the real
    NextTurnState::close; never dismiss_popup, which pops without close(), F3113). After each: the Turn-1 screen
    still on top, turn 0 on both machines, heldTurnScreenPresses +1 (P8b-1 section 4 S-F: the hold counts every
    close() it swallows). Fills ev[who + "Hold"]; returns the failures."""
    fails = []
    p0 = presses(gc)
    base = p0 if isinstance(p0, int) else 0
    rec = {"presses0": p0}
    k = gc.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN})
    g1, d1 = wait_until(lambda: presses(gc) == base + 1, CLICK_WAIT_S)
    rec["key"] = {"ok": k.get("ok"), "pressesWithin": d1 if g1 else None, "presses": presses(gc),
                  "stack": stack(gc), "turn": [turn(host), turn(client)]}
    if rec["key"]["stack"][-1:] == [TURN_SCREEN]:
        c = gc.cmd({"cmd": "close_nextturn"})
        g2, d2 = wait_until(lambda: presses(gc) == base + 2, CLICK_WAIT_S)
        rec["lever"] = {"answer": {k2: c.get(k2) for k2 in ("ok", "handled", "error")},
                        "pressesWithin": d2 if g2 else None, "presses": presses(gc), "stack": stack(gc),
                        "turn": [turn(host), turn(client)]}
    ev[who + "Hold"] = rec
    rk = rec["key"]
    if rk["stack"][-1:] != [TURN_SCREEN] or rk["pressesWithin"] is None:
        fails.append(f"{row}: one real key on the {who}'s Turn-1 screen left top {rk['stack'][-1:]} with "
                     f"heldTurnScreenPresses {p0} -> {rk['presses']} (want {TURN_SCREEN} still on top and +1: held "
                     f"while the equip phase is open, D215 a)")
    if rk["turn"] != [0, 0]:
        fails.append(f"{row}: turn host/client {rk['turn']} after the key on the {who}'s Turn-1 screen (want 0 on both)")
    lv = rec.get("lever")
    if not lv:
        fails.append(f"{row}: close_nextturn not run on the {who} (its Turn-1 screen was gone after the key)")
    else:
        if lv["answer"].get("handled") != "NextTurnState::close":
            fails.append(f"{row}: close_nextturn on the {who} answered {lv['answer']} (want handled "
                         f"NextTurnState::close)")
        if lv["stack"][-1:] != [TURN_SCREEN] or lv["pressesWithin"] is None:
            fails.append(f"{row}: close_nextturn on the {who}'s Turn-1 screen left top {lv['stack'][-1:]} with "
                         f"heldTurnScreenPresses {rk['presses']} -> {lv['presses']} (want {TURN_SCREEN} still on top "
                         f"and +1)")
        if lv["turn"] != [0, 0]:
            fails.append(f"{row}: turn host/client {lv['turn']} after close_nextturn on the {who} (want 0 on both)")
    return fails


def turn_screen_released(gc, who, row, ev):
    """After the equip end `gc`'s Turn-1 screen is still on top (the hold kept it; it never closed) and ONE real key
    closes it: BattlescapeState on top within KEY_WAIT_S, no held press counted. Fills ev[who + "Release"]."""
    fails = []
    p = presses(gc)
    rec = {"stackBefore": stack(gc), "pressesBefore": p}
    if rec["stackBefore"][-1:] != [TURN_SCREEN]:
        fails.append(f"{row}: after the equip end the {who}'s top is {rec['stackBefore'][-1:]} (want its Turn-1 screen "
                     f"still up: it closes on the player's own key, D215 a; stack {rec['stackBefore']})")
    else:
        k = gc.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN})
        g, d = wait_until(lambda: top(gc) == "BattlescapeState", KEY_WAIT_S)
        rec.update({"key": k.get("ok"), "battlescapeWithin": d if g else None, "stack": stack(gc),
                    "pressesAfter": presses(gc)})
        if not g:
            fails.append(f"{row}: one real key on the {who}'s released Turn-1 screen left {rec['stack']} (want "
                         f"BattlescapeState on top within {KEY_WAIT_S} s)")
        if rec["pressesAfter"] != p:
            fails.append(f"{row}: the {who}'s key after the equip end counted a held press ({p} -> "
                         f"{rec['pressesAfter']}; want unchanged: the hold ends with the equip phase)")
    ev[who + "Release"] = rec
    return fails


def partner_turn_screen(gc, who, ev):
    """The partner's own Turn-1 screen after the equip end (recorded, EQ8's shape): one real key when it is up."""
    rec = {"stack": stack(gc)}
    if rec["stack"][-1:] == [TURN_SCREEN]:
        k = gc.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN})
        g, d = wait_until(lambda: top(gc) == "BattlescapeState", KEY_WAIT_S)
        rec.update({"key": k.get("ok"), "battlescapeWithin": d if g else None, "stackAfter": stack(gc)})
    ev[who + "TurnScreen"] = rec


def barrier_ended(host, client):
    return (equip(host).get("barrierDone") is True and equip(host).get("phase") == "ended"
            and equip(client).get("phase") == "ended" and turn(host) == 1 and turn(client) == 1
            and not has(host, "InventoryState") and not has(client, "InventoryState"))


def probe_fails(host, row, ev):
    after = screen_probes(host)
    ev["probesAfter"] = after
    base = ev.get("base") or {}
    fails = []
    for k in ("hostScreensCloses", "hostCovered"):
        if base.get(k) != after.get(k):
            fails.append(f"{row}: host {k} changed across the equip phase: {base.get(k)} -> {after.get(k)} (want "
                         f"unchanged, P8b-1 section 2 / STOP-IF 12)")
    return fails


def eq25_spectator(host, client, ctx):
    """EQ25 (S-F, D215 a; Boot F1): the client commands no soldier (a spectator)."""
    ev = {"base": ctx.get("base")}
    # 1. the client's briefing OK while the host still reads its briefing
    c = client.cmd({"cmd": "close_briefing"})
    g, d = wait_until(lambda: top(client) == TURN_SCREEN, ENTRY_WAIT_S)
    e = {"close": {k: c.get(k) for k in ("ok", "error")}, "turnScreenWithin": d if g else None,
         "clientStack": stack(client), "hostStack": stack(host), "turn": [turn(host), turn(client)],
         "clientEquip": brief_equip(client), "clientView": view_brief(inv_view(client)),
         "clientBanner": battle_state(client).get("coopWaitText")}
    ev["entry"] = e
    if not g:
        evidence("EQ25", ev)
        red = e["clientStack"][-1:] == ["BattlescapeState"] and not any(TURN_SCREEN in s for s in e["clientStack"])
        finish([f"EQ25: the client's top {e['clientStack'][-1:]} {ENTRY_WAIT_S} s after its briefing OK (want "
                f"{TURN_SCREEN} at once, D215 a; client stack {e['clientStack']}, turn host/client {e['turn']}, client "
                f"equip {e['clientEquip']})"
                + (" - RED: the client on its map, no Turn-1 screen (S-A's interim: nothing is pushed for a seat "
                   "with nothing to equip)" if red else "")])
    fails = []
    if any("InventoryState" in s for s in e["clientStack"]) or e["clientEquip"].get("screen"):
        fails.append(f"EQ25: the client (no soldier) holds an equip screen (stack {e['clientStack']}, equip.screen "
                     f"{e['clientEquip'].get('screen')}; want none)")
    if e["turn"] != [0, 0]:
        fails.append(f"EQ25: turn host/client {e['turn']} at the client's Turn-1 screen (want 0 on both)")
    if e["hostStack"][-1:] != ["BriefingState"]:
        fails.append(f"EQ25: FIXTURE - the host left its briefing before its own close (host stack {e['hostStack']})")
    # 2. the hold: a real key, then close_nextturn
    fails += turn_screen_held(client, host, client, "client", "EQ25", ev)
    # 3. the host's briefing OK -> its pre-battle screen on its own soldier; the client's Turn-1 screen stays
    hc = host.cmd({"cmd": "close_briefing"})
    g3, d3 = wait_until(lambda: screen_up(host), ENTRY_WAIT_S)
    hv = inv_view(host)
    ev["hostEntry"] = {"close": {k: hc.get(k) for k in ("ok", "error")}, "screenWithin": d3 if g3 else None,
                       "hostView": view_brief(hv), "clientStack": stack(client), "turn": [turn(host), turn(client)],
                       "clientPresses": presses(client)}
    if not g3 or hv.get("unitId") not in ALL_IDS:
        fails.append(f"EQ25: the host's pre-battle screen {view_brief(hv)} within {ENTRY_WAIT_S} s of its briefing OK "
                     f"(want it on top on one of its own soldiers {ALL_IDS})")
    if ev["hostEntry"]["clientStack"][-1:] != [TURN_SCREEN]:
        fails.append(f"EQ25: the client's Turn-1 screen went away when the host's equip opened (client stack "
                     f"{ev['hostEntry']['clientStack']})")
    # 4. the host's OK (the real click) -> the barrier -> turn 1 on both
    o = ok_press(host)
    g4, d4 = wait_until(lambda: barrier_ended(host, client), BARRIER_WAIT_S, 0.1)
    ev["barrier"] = {"click": o.get("error") or o.get("ok"), "within": d4 if g4 else None,
                     "turn": [turn(host), turn(client)], "hostEquip": brief_equip(host),
                     "clientEquip": brief_equip(client), "hostStack": stack(host), "clientStack": stack(client)}
    if not g4:
        fails.append(f"EQ25: no barrier within {BARRIER_WAIT_S} s of the host's OK (turn host/client "
                     f"{ev['barrier']['turn']}, host equip {ev['barrier']['hostEquip']}, client equip phase "
                     f"{ev['barrier']['clientEquip'].get('phase')}; want barrierDone, the phase ended on both, turn 1 "
                     f"on both, no InventoryState left)")
    # 5. the client's Turn-1 screen is still up and one key closes it; 6. the host's own Turn-1 screen (recorded)
    fails += turn_screen_released(client, "client", "EQ25", ev)
    partner_turn_screen(host, "host", ev)
    fails += probe_fails(host, "EQ25", ev)
    evidence("EQ25", ev)
    fails += tail_fails(host, client, "EQ25")
    finish(fails)


def eq26_host_nothing(host, client, ctx):
    """EQ26 (S-F, D215 a; Boot F2): every craft soldier is the client's; the host commands none."""
    ev = {"base": ctx.get("base"), "refusal": ctx.get("refusal")}
    # 1. the host's briefing OK while the client still reads its briefing
    hc = host.cmd({"cmd": "close_briefing"})
    g, d = wait_until(lambda: top(host) == TURN_SCREEN and not has(host, "InventoryState"), ENTRY_WAIT_S)
    hv = inv_view(host)
    e = {"close": {k: hc.get(k) for k in ("ok", "error")}, "turnScreenWithin": d if g else None,
         "hostStack": stack(host), "clientStack": stack(client), "turn": [turn(host), turn(client)],
         "hostView": view_brief(hv), "hostEquip": brief_equip(host),
         "hostSelected": battle_state(host).get("selectedId"), "hostProbes": screen_probes(host)}
    ev["entry"] = e
    if not g:
        evidence("EQ26", ev)
        uid = e["hostView"].get("unitId")
        red = (e["hostStack"][-1:] == ["InventoryState"] and e["hostView"].get("preBattle") is True
               and (uid in ALL_IDS or uid in (None, -1)))
        finish([f"EQ26: the host's top {e['hostStack'][-1:]} {ENTRY_WAIT_S} s after its briefing OK (want "
                f"{TURN_SCREEN} with no InventoryState on its stack, D215 a; host stack {e['hostStack']}, its "
                f"inventory_view {e['hostView']}, host equip {e['hostEquip']}, host screen checks "
                f"{e['hostProbes']})"
                + (f" - RED: the host's pre-battle equip screen opened on "
                   f"{'client soldier ' + str(uid) if uid in ALL_IDS else 'no soldier'} (the host commands none)"
                   if red else "")])
    fails = []
    if e["turn"] != [0, 0]:
        fails.append(f"EQ26: turn host/client {e['turn']} at the host's Turn-1 screen (want 0 on both)")
    if e["clientStack"][-1:] != ["BriefingState"]:
        fails.append(f"EQ26: FIXTURE - the client left its briefing before its own close (client stack "
                     f"{e['clientStack']})")
    # 2. the hold: a real key, then close_nextturn
    fails += turn_screen_held(host, host, client, "host", "EQ26", ev)
    # 3. the client's briefing OK -> its pre-battle screen on its own soldier; the host's Turn-1 screen stays
    cc = client.cmd({"cmd": "close_briefing"})
    g3, d3 = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    cv = inv_view(client)
    hp = pile_ids(items_by_id(host))
    ev["clientEntry"] = {"close": {k: cc.get(k) for k in ("ok", "error")}, "screenWithin": d3 if g3 else None,
                         "clientView": view_brief(cv), "ground": ground_ids(cv), "hostPile": hp,
                         "hostStack": stack(host), "turn": [turn(host), turn(client)], "hostPresses": presses(host)}
    if not g3 or cv.get("unitId") not in ALL_IDS:
        fails.append(f"EQ26: the client's pre-battle screen {view_brief(cv)} within {ENTRY_WAIT_S} s of its briefing "
                     f"OK (want it on top on one of its own soldiers {ALL_IDS})")
    elif ground_ids(cv) != hp:
        fails.append(f"EQ26: STOP-IF 8 - the client's pre-battle ground {ground_ids(cv)} != the host's pile ids {hp}")
    if ev["clientEntry"]["hostStack"][-1:] != [TURN_SCREEN]:
        fails.append(f"EQ26: the host's Turn-1 screen went away when the client's equip opened (host stack "
                     f"{ev['clientEntry']['hostStack']})")
    # 4. the client's OK (the real click) -> the barrier -> turn 1 on both
    o = ok_press(client)
    g4, d4 = wait_until(lambda: barrier_ended(host, client), BARRIER_WAIT_S, 0.1)
    ev["barrier"] = {"click": o.get("error") or o.get("ok"), "within": d4 if g4 else None,
                     "turn": [turn(host), turn(client)], "hostEquip": brief_equip(host),
                     "clientEquip": brief_equip(client), "hostStack": stack(host), "clientStack": stack(client),
                     "hostSelected": battle_state(host).get("selectedId")}
    if not g4:
        fails.append(f"EQ26: no barrier within {BARRIER_WAIT_S} s of the client's OK (turn host/client "
                     f"{ev['barrier']['turn']}, host equip {ev['barrier']['hostEquip']}, client equip phase "
                     f"{ev['barrier']['clientEquip'].get('phase')}; want barrierDone, the phase ended on both, turn 1 "
                     f"on both, no InventoryState left)")
    # 5. the host's Turn-1 screen is still up and one key closes it; 6. the client's own Turn-1 screen (recorded)
    fails += turn_screen_released(host, "host", "EQ26", ev)
    partner_turn_screen(client, "client", ev)
    fails += probe_fails(host, "EQ26", ev)
    evidence("EQ26", ev)
    fails += tail_fails(host, client, "EQ26")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine (a failure there fails the
# run, and the row after it fails on its own preconditions).
STEPS_E1 = ((None, spine_e1),
            ("EQ24", eq24_no_aliens_start))
STEPS_E2 = ((None, spine_e2),
            ("EQ24b", eq24b_no_aliens_in_handshake))
STEPS_E3 = ((None, spine_e2),
            ("EQ24c", eq24c_host_ok_in_handshake))
STEPS_F1 = ((None, spine_f),
            ("EQ25", eq25_spectator))
STEPS_F2 = ((None, spine_f),
            ("EQ26", eq26_host_nothing))


def check_boot(host, client, seated, tag):
    hb = battle_state(host)
    assert hb.get("mapFingerprint") == MAP_FP, (
        f"host mapFingerprint {hb.get('mapFingerprint')!r} (baked MAP_FP {MAP_FP!r}, SEED_MAP {SEED_MAP})")
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == C_IDS, f"seated client units {seated_uids} (baked C {C_IDS})"
    h_ids = sorted(u["id"] for u in hb["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids == H_IDS, f"host-seat soldiers {h_ids} (baked H {H_IDS})"
    q = event_state(host).get("equip")
    assert isinstance(q, dict) and "abortPending" in q, f"host event_state lacks the W2-P8b equip probe: {q!r}"
    print(f"[w2p8b-se] boot {tag} ok: MAP_FP={MAP_FP!r} mission={hb.get('missionType')} seated={seated_uids} "
          f"H={h_ids} host stack={stack(host)} client stack={stack(client)}", flush=True)


def boot_e1(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT_E1)
    seated = {}
    session.bring_up_to_briefings(host, client, seated, seat_count=2,
                                  pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    check_boot(host, client, seated, "E1")
    return {}


def boot_e2(host, client, port=PORT_E2, tag="E2"):
    bring_up_lobby_roster_pinned(host, client, port)
    seated = {}
    ctx = {}

    def pre_newbattle(h, c):
        ctx["arm"] = hold(c, on=True)
        assert ctx["arm"].get("ok") and ctx["arm"].get("armed") is True, f"hold_battle_ready {{on: true}}: {ctx['arm']}"

    session.bring_up_to_briefings(host, client, seated, seat_count=2,
                                  pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}),
                                  pre_newbattle=pre_newbattle)
    check_boot(host, client, seated, tag)
    return ctx


def boot_e3(host, client):
    """Boot E3 (S-E.3, row EQ24c) = Boot E2 on its own lobby port; spine_e2 reads the tag."""
    ctx = boot_e2(host, client, PORT_E3, "E3")
    ctx["tag"] = "E3"
    return ctx


def check_boot_f(host, client, seated, tag, want_seated, want_host):
    """Boots F1/F2: MAP_FP, the seating (the client's units, the host's own soldiers) and the craft pile on both."""
    hb = battle_state(host)
    assert hb.get("mapFingerprint") == MAP_FP, (
        f"host mapFingerprint {hb.get('mapFingerprint')!r} (baked MAP_FP {MAP_FP!r}, SEED_MAP {SEED_MAP})")
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == want_seated, f"seated client units {seated_uids} (want {want_seated})"
    h_ids = sorted(u["id"] for u in hb["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids == want_host, f"host-seat soldiers {h_ids} (want {want_host})"
    # the HOST only: bring_up_to_briefings returns at the host's briefing, before the client holds the battle
    # (the client's equip probe is checked by spine_f once its briefing is up)
    q = event_state(host).get("equip")
    assert isinstance(q, dict) and "heldTurnScreenPresses" in q, f"host event_state lacks the W2-P8b equip probe: {q!r}"
    assert q.get("pile") == list(PILE), f"host equip.pile {q.get('pile')} (want {list(PILE)})"
    print(f"[w2p8b-sf] boot {tag} ok: MAP_FP={MAP_FP!r} mission={hb.get('missionType')} seated={seated_uids} "
          f"H={h_ids} host stack={stack(host)} client stack={stack(client)}", flush=True)


def boot_f1(host, client):
    """Boot F1 (S-F, EQ25): no soldier seated to the client (seat_count 0 = drive_to_battlescape's
    seat_client=False: no newbattle_seat_soldier call), so the client is a spectator; the host keeps ALL_IDS."""
    bring_up_lobby_roster_pinned(host, client, PORT_F1)
    seated = {}
    session.bring_up_to_briefings(host, client, seated, seat_count=0,
                                  pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    check_boot_f(host, client, seated, "F1", [], ALL_IDS)
    return {"tag": "F1"}


def boot_f2(host, client):
    """Boot F2 (S-F, EQ26): P8b-2 T0-9's seat-everyone recipe - SEAT_ALL soldiers seated to the client, then index
    SEAT_ALL must refuse (the craft has no more); the host commands no soldier."""
    bring_up_lobby_roster_pinned(host, client, PORT_F2)
    seated = {}
    ctx = {"tag": "F2"}

    def pre_ok(h):
        r = h.cmd({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": SEAT_ALL})
        ctx["refusal"] = {k: r.get(k) for k in ("ok", "error")}
        assert not r.get("ok"), (f"T0-9: newbattle_seat_soldier index {SEAT_ALL} answered {ctx['refusal']} (want the "
                                 f"refusal: the craft seats {SEAT_ALL})")
        h.ok({"cmd": "set_seed", "seed": SEED_MAP})

    session.bring_up_to_briefings(host, client, seated, seat_count=SEAT_ALL, pre_ok=pre_ok)
    check_boot_f(host, client, seated, "F2", ALL_IDS, [])
    return ctx


# (boot name, user-dir tag, bring-up, steps)
BOOTS = (("E1", "e1", boot_e1, STEPS_E1),
         ("E2", "e2", boot_e2, STEPS_E2),
         ("E3", "e3", boot_e3, STEPS_E3),
         ("F1", "f1", boot_f1, STEPS_F1),
         ("F2", "f2", boot_f2, STEPS_F2))
ROWS = [n for _, _, _, steps in BOOTS for n, _ in steps if n]


def run_boot(name, tag, boot, steps, results):
    """One boot: bring-up, then its steps in order (each row ONE run). Returns False when the bring-up or a spine
    step failed."""
    host = GameClient("host", None, make_user_dir(f"w2p8b_prebattle_equip_end_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"w2p8b_prebattle_equip_end_{tag}_client"))
    spine_ok = True
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails this boot's rows
            print(f"FAIL boot {name}: {type(e).__name__}: {e}", flush=True)
            return False
        for row, fn in steps:
            try:
                fn(host, client, ctx)
                if row:
                    results[row] = True
                    print(f"PASS {row}", flush=True)
            except Exception as e:
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                if row:
                    results[row] = False
                    print(f"FAIL {row}: {kind}{e}", flush=True)
                else:
                    spine_ok = False
                    print(f"SPINE FAIL {fn.__name__}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p8b-se] shutdown boot {name} {gc.name}: {short(e)}", flush=True)
    return spine_ok


def main():
    t0 = time.time()
    results = {}
    spine_ok = True
    for name, tag, boot, steps in BOOTS:
        tb = time.time()
        spine_ok = run_boot(name, tag, boot, steps, results) and spine_ok
        print(f"[w2p8b-se] boot {name} done in {time.time() - tb:.1f}s", flush=True)
    passed = [n for n in ROWS if results.get(n)]
    failed = [n for n in ROWS if not results.get(n)]
    print(f"\ntest_w2_prebattle_equip_end: {len(passed)}/{len(ROWS)} passed "
          f"(pass={passed} fail={failed}{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (not failed and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
