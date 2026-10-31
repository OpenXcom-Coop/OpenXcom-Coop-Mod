"""test_prebattle_equip_rejoin.py: pre-battle equip in traditional turn mode, and a player who leaves and rejoins
during the pre-battle equip.

The host closes its briefing BEFORE the second player's battle_ready arrives (the handshake window, phase Handshake):
its equip screen opens, shows only its own soldiers, and the equip-open announce goes out once the battle is Active.
The test-only client hook `hold_battle_ready` makes the window deterministic. Pre-battle placements and priming are
TU-free orders the host performs. A player who leaves during the pre-battle equip and rejoins returns to its equip
screen, with its ready state as it was.

Without the fix the host's battle file goes out only when the host closes its own briefing and the host's pre-battle
equip is frozen: its briefing OK starts turn 1 at once and no equip screen opens.

Boot traditional (ONE boot): the roster-pinned lobby (set_seed SEED_ROSTER before open_new_battle),
session.bring_up_to_briefings (the client seated C1, C2; the host keeps H) with pre_ok = set_seed SEED_MAP then
CoopTurnMode traditional on the host (test_turn_baton.py's recipe, in that order) and pre_newbattle = the CLIENT's
hold_battle_ready {on: true}; the host's mapFingerprint = MAP_FP.
  host_equips_in_handshake: (1) wait <= 30 s for the client's BriefingState (the client holds the battle while the
      host reads its briefing) with its battle_ready stashed (the host stays in phase Handshake); staging as soon as
      both machines hold the battle (C1, C2 and every H soldier stripped on both, then one each of STAGE_TYPES_PILE on
      the pile, client first); (2) host close_briefing; (3) host inventory_click {widget: next} x3; (4) the host moves
      the staged clip from the pile to its current soldier's belt (0,0); (5) the client's hold_battle_ready {on:
      false}. Pass: after (2) the host's top is its pre-battle InventoryState (preBattle), turn 0, phase Handshake;
      (3) visits only H ids, in phase Handshake; (4) lands on the host, still Handshake and equip.openAnnounced false;
      after (5): the host's phase Active, equip.openAnnounced true (the announce `sync`), the clip on that soldier's
      belt (0,0) on the client too, turn 0 on both, turnMode traditional on both. Without the fix: the host's briefing
      OK starts turn 1 (the freeze) with no equip screen.
The placement rows. The spine after host_equips_in_handshake: C1's kit staged (client first: C1 gets a rifle loaded
with a clip in STR_RIGHT_HAND, a STR_GRENADE on STR_BELT (1,0) and a STR_PROXIMITY_GRENADE on STR_BELT (2,0),
battle_give; the ids recorded), then the client's close_briefing -> its pre-battle screen on C1. quick_unload,
prime_unprime and default_fuse are this boot's LAST rows: without the fix each writes on the client alone, and that
divergence fails every later row of the boot.
  baton_free_placement: the host holds the traditional baton at turn 0; the client moves the first pile STR_GRENADE to
      C1's STR_BELT (0,0). Pass: it lands there on both, the client's invGuard.counts.baton unchanged. Without the
      fix: refused at the client's execution point by the baton term (`not_your_go`, invGuard.counts.baton +1); the
      item then leaves the client's cursor by a right-click (vanilla's return).
  quick_unload: a Shift-click on C1's loaded rifle in STR_RIGHT_HAND. Pass: the rifle stays in STR_RIGHT_HAND
      unloaded, its clip on the ground at PILE, on both; the client's invLocalWrites 0. Without the fix: vanilla's
      `quickUnload && !_tu` branch writes on the client alone (invLocalWrites > 0, buckets unequal).
  prime_unprime: a right-click on C1's STR_GRENADE -> the client's PrimeGrenadeState -> key 3; then a right-click
      again. Pass: fuse 3 on both, then -1 on both. Without the fix: fuse 3 on the client alone, -1 on the host.
  default_fuse: the default fuse (Inventory.cpp's BFT_INSTANT branch): a right-click on C1's STR_PROXIMITY_GRENADE.
      Pass: its default fuse (0) on both. Without the fix: on the client alone, -1 on the host.
The leave and rejoin boots. The leave is test_pause_on_leave.py's: the client's disconnect_to_menu -> its main menu;
the host notices the drop and holds its pause dialog COOP_DLG_WAIT_PLAYERS (62). The rejoin is
test_skirmish_rejoin_battle.py's scenario_rejoin_and_resume: the player comes back in a fresh process (NEW BATTLE >
COOP > browser > join), holds on COOP_DLG_CLIENT_RESUME_HOLD (68); the host's dialog offers RESUME (the join's Profile
popup cleared as it appears); the host presses RESUME (coop_dialog_back). Boots leave_on_screen and leave_in_briefing:
the roster-pinned lobby (their own lobby ports), parallel turn mode, session.bring_up_to_briefings with pre_ok =
set_seed SEED_MAP; MAP_FP, C, H and PILE as Boot traditional.
Boot leave_on_screen spine: the client's briefing (<= 30 s); the host's close_briefing -> its pre-battle screen; the
client's close_briefing -> its pre-battle screen; the host's equip-open announce applied on the client.
  leave_not_ready: the client is not ready and leaves; the host is paused (dialog 62 over its pre-battle screen); the
      player rejoins; the host presses RESUME. Pass: the rejoiner's pre-battle screen on top (preBattle) on one of C,
      okPressed false, its equip.pile = PILE and its ground ids = the host's pile ids; the host's pre-battle screen
      back on top; equip phase open and turn 0 on both. Without the fix: no equip screen after the rejoin (the rejoin
      offer carries no `equip`).
  leave_ready: the (leave_not_ready) rejoiner presses OK (ready: host equip.ready[1] true, okPressed true) and leaves;
      the player rejoins in a second fresh process; RESUME. Pass: the rejoiner's pre-battle screen with okPressed
      true, host equip.ready[1] true, and 1.5 s after the screen its line "Waiting for HostPlayer to finish equipping"
      visible; then the host's OK (the real click) -> turn 1 on both, equip phase ended on both, host barrierDone.
      Without the fix: no equip screen after the rejoin (leave_not_ready's rejoiner has no screen either, so the ready
      press is recorded as absent; the leave, the rejoin and RESUME still run).
Boot leave_in_briefing spine: the client's briefing (<= 30 s); the client's close_briefing -> its pre-battle screen
while the host still reads its briefing (phase Active).
  leave_in_host_briefing: the client leaves while the host is still in its briefing; the host's pause dialog 62 covers
      the briefing (asserted); the player rejoins - the rejoin offer is built with no host BattlescapeState and
      equip.openAnnounced false (the client holds the battle while the host reads its briefing, asserted); the host
      presses RESUME; the host's briefing is back on top (asserted); the host presses its briefing's OK (the real
      click, click_widget). Pass: the rejoiner's pre-battle screen (preBattle on one of C, okPressed false, equip.pile
      = PILE, ground = the host's pile ids) while the host still reads its briefing; after the host's OK its
      pre-battle screen and the equip-open announce on both (equip.openAnnounced true on the rejoiner); turn 0 on
      both. Without the fix: no equip screen after the rejoin (the rejoiner lands without an equip phase).

Common asserts (after the release): hash_now {full:true} every bucket EQUAL after the queues drain; desyncSeen false
on both; the client's turnMirrorFired 0; coopClientBStatePushes 0 on both; the client's invLocalWrites 0; while the
client's pre-battle screen is open, its ground ids = the host's pile ids. The hold is always released at the end of
host_equips_in_handshake (recorded), so a failed row never leaves the host in phase Handshake.

Constants: SEED_ROSTER 1, SEED_MAP 1, MAP_FP (measured in traditional turn mode: the same fingerprint as the parallel
boot), C [8, 9], H [10..14], PILE (14, 19, 1) (measured: pile=[14, 19, 1] C=[8, 9] H=[10, 11, 12, 13, 14]).

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked, then "PASS <id>" / "FAIL <id>:
<message>"; main() runs every row of every boot (traditional, leave_on_screen, leave_in_briefing, in that order) even
after an earlier one failed; a boot's bring-up failure fails that boot's rows. Every wait is bounded. One run is the
result; no skip path, no re-boot. Exit 0 only when every row passes, 2 otherwise (a bring-up or spine failure is also
2). Run in the foreground to completion.

Run:  python tools/coop_test/test_prebattle_equip_rejoin.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
from test_delta_core import both, short, diff_buckets, hashes
from test_delta_items import items_by_id
from test_host_combat import bring_up_lobby_roster_pinned
from test_client_items import strip_both
from test_turn_mode import set_mode, TRADITIONAL
from test_prebattle_equip import (SEED_MAP, MAP_FP, C_IDS, H_IDS, PILE, COOP_SEAT_0, FACTION_PLAYER, BELT,
                                     CLIENT_BRIEFING_WAIT_S, ANSWER_WAIT_S, CLICK_WAIT_S, stack, top, has, es, equip,
                                     turn, in_battle, inv_view, view_brief, item_view, wait_until, evidence, finish,
                                     click, pick_ground, next_press, tail_fails,
                                     C1, GROUND, RIGHT_HAND, RIFLE_T, CLIP_T, GRENADE_T, ENTRY_WAIT_S, LAND_WAIT_S,
                                     screen_up, goto_unit, pre_screen_fails, first_of_type, weapon_view, on_pile,
                                     tus, ok_press, pile_ids, ground_ids, drained, TEXT_WAIT_HOST, LINE_READ_S,
                                     TURN_WAIT_S, DRAIN_WAIT_S)
from test_skirmish_rejoin_battle import rejoin_skirmish, dialog, in_battle_save

PORT = "48792"                     # this file's lobby port (unused by every other test file)
STAGE_TYPES_PILE = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE")   # the four staged types
HOST_NEXT_PRESSES = 3              # host_equips_in_handshake: "host next x3"
PHASE_WAIT_S = 10.0                # the host reaches phase Active after the release
MOVE_WAIT_S = 5.0

# ----- C1's kit and the placement rows (baton_free_placement, quick_unload, prime_unprime, default_fuse) -----
PROX_T = "STR_PROXIMITY_GRENADE"
C1_KIT = ((RIFLE_T, {"ammo": CLIP_T}),                           # C1's loaded rifle, STR_RIGHT_HAND (quick_unload)
          (GRENADE_T, {"slot": BELT, "slotX": 1, "slotY": 0}),   # prime_unprime's grenade
          (PROX_T, {"slot": BELT, "slotX": 2, "slotY": 0}))      # default_fuse's proximity grenade
GRENADE_CELL = (1, 0)              # STR_BELT cells of the two staged grenades
PROX_CELL = (2, 0)
BATON_TARGET_CELL = (0, 0)         # baton_free_placement's target: C1's STR_BELT (0,0)
SDLK_3 = 51                        # PrimeGrenadeState: _button[3]->onKeyboardPress(..., SDLK_3)
FUSE_KEYED = 3                     # prime_unprime: key 3 -> fuse 3
FUSE_NONE = -1                     # an unprimed grenade
FUSE_DEFAULT_INSTANT = 0           # RuleItem::getFuseTimerDefault() for BFT_INSTANT (STR_PROXIMITY_GRENADE)
TEXT_NOT_YOUR_GO = "Not your turn - waiting for HostPlayer"   # STR_COOP_DENY_NOT_YOUR_GO (the refusal's line, evidence)

# ----- leave and rejoin during the pre-battle equip (rows leave_not_ready, leave_ready, leave_in_host_briefing) -----
PORT_LEAVE_ON_SCREEN = "48835"     # Boot leave_on_screen's lobby port (unused by every other test file)
PORT_LEAVE_IN_BRIEFING = "48836"   # Boot leave_in_briefing's lobby port (unused by every other test file)
CLIENT_PLAYER = "ClientPlayer"     # the rejoiner's player name (the seat's original player)
COOP_DLG_WAIT_PLAYERS = 62         # the host's pause-on-leave dialog
COOP_DLG_CLIENT_RESUME_HOLD = 68   # the rejoiner's hold until the host's RESUME
SEAT_CLIENT = 1
LEAVE_WAIT_S = 30.0                # the leaver reaches its main menu
PAUSE_WAIT_S = 30.0                # the host notices the drop and raises its pause dialog
REJOIN_WAIT_S = 90.0               # the rejoiner holds the battle (test_skirmish_rejoin_battle.py's bound: 240 s)
RESUME_OFFER_WAIT_S = 60.0         # the host's pause dialog offers RESUME
RELEASE_WAIT_S = 30.0              # RESUME releases the rejoiner's hold and closes the host's dialog
ACTIVE_WAIT_S = 30.0               # Boot leave_in_briefing: the host's phase Active (the client's battle_ready arrived)


def stage_pile(host, client, ctx):
    """C1, C2 and every H soldier stripped on both machines, then one each of STAGE_TYPES_PILE on PILE (client
    first; staged ids, never stock ids)."""
    rec = {}
    try:
        rec["stripped"] = {uid: strip_both(host, client, uid) for uid in C_IDS + H_IDS}
        ids = {}
        for t in STAGE_TYPES_PILE:
            r = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                     ("ids",))
            ids[t] = r["ids"][0]
        rec["ids"] = ids
        # The host allocates its hostile reveal set at onReady, i.e. at phase Active, and hash_now omits the key
        # until then: while the host is in phase Handshake every bucket but revealHostile is compared, and
        # revealHostile must be ABSENT from the host's hash_now (present - equal or not - is a FAIL); otherwise
        # every bucket is compared.
        hh, ch = hashes(host), hashes(client)
        rec["hostPhase"] = es(host).get("phase")
        handshake = rec["hostPhase"] == "Handshake"
        skip = {"revealHostile"} if handshake else set()
        rec["diff"] = sorted(k for k in (set(hh) | set(ch)) - skip if hh.get(k) != ch.get(k))
        rec["revealHostile"] = [hh.get("revealHostile"), ch.get("revealHostile")]
        if handshake and "revealHostile" in hh:
            rec["revealHostileError"] = (f"the host is in phase Handshake but its hash_now carries revealHostile "
                                         f"{hh['revealHostile']!r} (want ABSENT: it is allocated at onReady)")
    except Exception as e:
        rec["error"] = short(e, 400)
    ctx["staged"] = rec
    print(f"STAGE {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    return rec


def hold(client, **kw):
    req = {"cmd": "hold_battle_ready"}
    req.update(kw)
    r = client.cmd(req)
    return {k: r.get(k) for k in ("ok", "error", "armed", "held", "sent")}


def row_host_equips_in_handshake(host, client, ctx):
    ev = {"arm": ctx.get("arm")}
    fails = []
    try:
        # (1) the client holds the battle during the host's briefing, battle_ready stashed
        got, dt = wait_until(lambda: has(client, "BriefingState"), CLIENT_BRIEFING_WAIT_S, 0.1)
        ev["clientBriefingWithin"] = dt if got else None
        ev["hold1"] = hold(client)
        ev["phase1"] = {"host": es(host).get("phase"), "client": es(client).get("phase"),
                        "clientStack": stack(client), "hostStack": stack(host)}
        if got and in_battle(client):
            stage_pile(host, client, ctx)
        # (2) host close_briefing in phase Handshake
        r = host.cmd({"cmd": "close_briefing"})
        g2, d2 = wait_until(lambda: not has(host, "BriefingState"), 10.0)
        g3, d3 = wait_until(lambda: top(host) == "InventoryState" and inv_view(host).get("preBattle") is True, 5.0)
        hv = inv_view(host)
        ev["afterOk"] = {"close": {k: r.get(k) for k in ("ok", "error")}, "briefingGoneWithin": d2 if g2 else None,
                         "screenWithin": d3 if g3 else None, "hostTurn": turn(host), "hostStack": stack(host),
                         "hostPhase": es(host).get("phase"), "hostEquip": equip(host), "view": view_brief(hv)}
        if not (g3 and hv.get("preBattle") is True and ev["afterOk"]["hostTurn"] == 0):
            evidence("host_equips_in_handshake", ev)
            fails.append(f"host_equips_in_handshake: the host's briefing OK left turn {ev['afterOk']['hostTurn']} with "
                         f"no pre-battle "
                         f"screen (host stack {ev['afterOk']['hostStack']}, inventory_view {view_brief(hv)}; without "
                         f"the fix: the freeze starts turn 1 at the host's briefing OK)")
            finish(fails)   # raises; the `finally` below still releases the hold
        if ev["afterOk"]["hostPhase"] != "Handshake":
            fails.append(f"host_equips_in_handshake: the host's phase after its briefing OK "
                         f"{ev['afterOk']['hostPhase']!r} (want Handshake: "
                         f"the client's battle_ready is held; hold {ev['hold1']})")
        # (3) host next x3, in phase Handshake
        start = hv.get("unitId")
        presses = []
        for _ in range(HOST_NEXT_PRESSES):
            next_press(host, presses)
        seen = [start] + [p["to"] for p in presses]
        ev["next"] = {"seen": seen, "presses": presses, "phase": es(host).get("phase")}
        # (4) the host moves the staged clip from the pile to its current soldier's belt (0,0)
        cur = inv_view(host).get("unitId")
        clip = ((ctx.get("staged") or {}).get("ids") or {}).get("STR_RIFLE_CLIP")
        mv = {"unit": cur, "stagedClip": clip, "pick": {}}
        item = pick_ground(host, clip, mv["pick"]) if clip is not None else None
        mv["item"] = item
        want = {"owner": cur, "slot": BELT, "slotX": 0, "slotY": 0}
        if item is not None:
            mv["drop"] = click(host, slot=BELT, x=0, y=0)

            def on_host():
                a = item_view(items_by_id(host), item)
                return a and all(a.get(k) == v for k, v in want.items())

            g4, d4 = wait_until(on_host, CLICK_WAIT_S)
            mv["hostWithin"] = d4 if g4 else None
        mv["hostPhase"] = es(host).get("phase")
        mv["openAnnounced"] = equip(host).get("openAnnounced")
        mv["clientItem"] = item_view(items_by_id(client), item) if item is not None else None
        ev["move"] = mv
        # (5) release the client's battle_ready
        tr = time.time()
        ev["release"] = hold(client, on=False)
        g5, d5 = wait_until(lambda: es(host).get("phase") == "Active", PHASE_WAIT_S)
        g6, d6 = wait_until(lambda: equip(host).get("openAnnounced") is True, ANSWER_WAIT_S)

        def on_client():
            b = item_view(items_by_id(client), item)
            return item is not None and b and all(b.get(k) == v for k, v in want.items())

        g7, d7 = wait_until(on_client, MOVE_WAIT_S)
        ev["afterRelease"] = {"activeWithin": d5 if g5 else None, "announceWithin": d6 if g6 else None,
                              "clientMoveWithin": d7 if g7 else None, "sinceRelease": round(time.time() - tr, 3),
                              "hostEquip": equip(host), "clientEquip": equip(client),
                              "itemHost": item_view(items_by_id(host), item) if item is not None else None,
                              "itemClient": item_view(items_by_id(client), item) if item is not None else None,
                              "turn": [turn(host), turn(client)],
                              "turnMode": [es(host).get("turnMode"), es(client).get("turnMode")]}
        evidence("host_equips_in_handshake", ev)
        if not all(u in H_IDS for u in seen) or len(set(seen)) < 2:
            fails.append(f"host_equips_in_handshake: the host's NEXT x{HOST_NEXT_PRESSES} visited {seen} (want only H "
                         f"ids {H_IDS}, and a real change of soldier)")
        if ev["next"]["phase"] != "Handshake":
            fails.append(f"host_equips_in_handshake: the host's phase during NEXT {ev['next']['phase']!r} (want "
                         f"Handshake)")
        if staged_error(ctx):
            fails.append(f"host_equips_in_handshake: {staged_error(ctx)}")
        if item is None:
            fails.append(f"host_equips_in_handshake: the host did not pick the staged clip {clip} ({mv['pick']})")
        elif mv.get("hostWithin") is None:
            fails.append(f"host_equips_in_handshake: the host's own move {item} -> {want} did not land on the host "
                         f"({item_view(items_by_id(host), item)})")
        if mv["hostPhase"] != "Handshake" or mv["openAnnounced"] is not False:
            fails.append(f"host_equips_in_handshake: before the release host phase {mv['hostPhase']!r} openAnnounced "
                         f"{mv['openAnnounced']} (want Handshake, false: no announce before Active)")
        if ev["release"].get("sent") is not True:
            fails.append(f"host_equips_in_handshake: the release sent no held battle_ready ({ev['release']})")
        ar = ev["afterRelease"]
        if ar["activeWithin"] is None:
            fails.append(f"host_equips_in_handshake: the host never reached phase Active within {PHASE_WAIT_S} s of "
                         f"the release")
        if ar["announceWithin"] is None:
            fails.append(f"host_equips_in_handshake: host equip.openAnnounced {ar['hostEquip'].get('openAnnounced')} "
                         f"after Active (want true: the equip-open announce `sync`)")
        if ar["clientMoveWithin"] is None:
            fails.append(f"host_equips_in_handshake: the host's move is not on the client: {ar['itemClient']} (want "
                         f"{want} within {MOVE_WAIT_S} s)")
        if ar["turn"] != [0, 0]:
            fails.append(f"host_equips_in_handshake: turn host/client {ar['turn']} (want 0 on both)")
        if ar["turnMode"] != ["traditional", "traditional"]:
            fails.append(f"host_equips_in_handshake: FIXTURE - turnMode host/client {ar['turnMode']} (want traditional "
                         f"on both)")
        fails += tail_fails(host, client, "host_equips_in_handshake")
        # after the release (host Active) every bucket incl. revealHostile is EQUAL - and
        # revealHostile is PRESENT on both (the tail's diff alone would pass a key absent on both).
        hh, ch = hashes(host), hashes(client)
        rh = [hh.get("revealHostile"), ch.get("revealHostile")]
        if not ("revealHostile" in hh and "revealHostile" in ch and rh[0] == rh[1]):
            fails.append(f"host_equips_in_handshake: after the release revealHostile host/client {rh} (want present "
                         f"and EQUAL on both)")
    finally:
        # never leave the host in phase Handshake: release whatever is still held (recorded)
        rest = hold(client)
        if rest.get("armed") or rest.get("held"):
            rel = hold(client, on=False)
            wait_until(lambda: es(host).get("phase") == "Active", PHASE_WAIT_S)
            print(f"[prebattle_equip_rejoin] host_equips_in_handshake cleanup: released the hold {rel}; host phase "
                  f"{es(host).get('phase')}", flush=True)
    finish(fails)


def staged_error(ctx):
    s = ctx.get("staged")
    if not s:
        return "nothing staged (the client held no battle during the host's briefing)"
    if s.get("error"):
        return f"the staging failed: {s['error']}"
    if s.get("diff"):
        return f"buckets differ after the staging: {s['diff']}"
    if s.get("revealHostileError"):
        return s["revealHostileError"]
    return None


# ===================== the baton, quick unload, the fuse sites =====================


def stage_c1_kit(host, client, ctx):
    """The spine after host_equips_in_handshake: C1's kit staged (battle_give, client first; the client's briefing
    is still up, so its screen opens on the staged kit), then the client's close_briefing -> its pre-battle screen
    on C1. Records ctx['kit']; raises (a spine failure) when either step fails."""
    rec = {"ids": {}}
    ctx["kit"] = rec
    try:
        for t, extra in C1_KIT:
            req = {"cmd": "battle_give", "unit": C1, "item": t}
            req.update(extra)
            r = both(host, client, req, ("weaponId", "ammoId", "weaponSlot"))
            rec["ids"][t] = r["weaponId"]
            if t == RIFLE_T:
                rec["rifleAmmo"] = r["ammoId"]
        rec["diff"] = diff_buckets(host, client)
        rec["turn"] = [turn(host), turn(client)]
    except Exception as e:
        rec["error"] = short(e, 400)
    c = client.cmd({"cmd": "close_briefing"})
    got, dt = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    nav = []
    rec["entry"] = {"close": {k: c.get(k) for k in ("ok", "error")}, "screenWithin": dt if got else None,
                    "unitId": inv_view(client).get("unitId"), "clientStack": stack(client)}
    rec["entry"]["toC1"] = {"reached": goto_unit(client, C1, C_IDS, nav) if got else None, "presses": nav}
    print(f"STAGE kit {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if rec.get("error") or rec.get("diff"):
        raise AssertionError(f"spine: C1's kit staging failed ({rec.get('error')}; buckets differ {rec.get('diff')})")
    if not got or not rec["entry"]["toC1"]["reached"]:
        raise AssertionError(f"spine: the client's pre-battle screen on C1 never came up ({rec['entry']})")


def kit_row_pre(host, client, ctx, row):
    fails = pre_screen_fails(host, client, row)
    s = ctx.get("kit") or {}
    if not s.get("ids") or s.get("error") or s.get("diff"):
        fails.append(f"{row}: C1's kit staging did not complete ({s})")
    if not fails and inv_view(client).get("unitId") != C1:
        fails.append(f"{row}: the client's screen shows {inv_view(client).get('unitId')} (want C1 {C1})")
    if not fails and inv_view(client).get("selectedItem") != -1:
        fails.append(f"{row}: the client's cursor holds {inv_view(client).get('selectedItem')} (want empty)")
    return fails


def guard_counts(gc):
    return dict((es(gc).get("invGuard") or {}).get("counts") or {})


def row_baton_free_placement(host, client, ctx):
    fails = kit_row_pre(host, client, ctx, "baton_free_placement")
    ev = {}
    if fails:
        evidence("baton_free_placement", ev)
        finish([f.replace("baton_free_placement: ", "baton_free_placement: precondition absent - ") for f in fails])
    g0, ec0 = guard_counts(client), es(client)
    tu0 = tus(host, client, C1)
    item0 = first_of_type(client, GRENADE_T)
    ev["pick"] = {}
    item = pick_ground(client, item0, ev["pick"]) if item0 is not None else None
    want = {"owner": C1, "slot": BELT, "slotX": BATON_TARGET_CELL[0], "slotY": BATON_TARGET_CELL[1]}
    got = None
    if item is not None:
        ev["drop"] = click(client, slot=BELT, x=BATON_TARGET_CELL[0], y=BATON_TARGET_CELL[1])

        def landed():
            a, b = item_view(items_by_id(host), item), item_view(items_by_id(client), item)
            return all(a and b and a.get(k) == v and b.get(k) == v for k, v in want.items())

        def refused():
            return guard_counts(client).get("baton", 0) > g0.get("baton", 0)

        got, dt = wait_until(lambda: landed() or refused(), LAND_WAIT_S, 0.1)
        ev["answeredWithin"] = dt if got else None
        got = landed()
    ec = es(client)
    ev["refusal"] = {"invGuardCounts": [g0, guard_counts(client)], "invGuardLast": (ec.get("invGuard") or {}).get("last"),
                     "invLastWarning": [ec0.get("invLastWarning"), ec.get("invLastWarning")],
                     "invWarningWrites": [ec0.get("invWarningWrites"), ec.get("invWarningWrites")],
                     "cursor": inv_view(client).get("selectedItem"), "turnMode": [es(host).get("turnMode"),
                                                                                  ec.get("turnMode")]}
    # a refusal leaves the item on the client's cursor: vanilla's right-click return takes it back (a pick is
    # display only; nothing was sent). Only with an item on it (an empty-cursor right-click primes a grenade).
    if inv_view(client).get("selectedItem") != -1:
        ev["return"] = click(client, slot=GROUND, x=0, y=0, button="right")
        wait_until(lambda: inv_view(client).get("selectedItem") == -1, CLICK_WAIT_S)
    ih, ic = items_by_id(host), items_by_id(client)
    ev.update({"grenadeOnPile": item0, "item": item, "want": want, "itemHost": item_view(ih, item),
               "itemClient": item_view(ic, item), "c1Tu": [tu0, tus(host, client, C1)],
               "cursorAfter": inv_view(client).get("selectedItem"), "turn": [turn(host), turn(client)]})
    evidence("baton_free_placement", ev)
    if item0 is None:
        fails.append(f"baton_free_placement: precondition absent - no {GRENADE_T} on the client's pile ground")
    elif item is None:
        fails.append(f"baton_free_placement: the pile grenade was not picked ({ev['pick']})")
    elif not got:
        fails.append(f"baton_free_placement: the grenade {item} host={ev['itemHost']} client={ev['itemClient']} (want "
                     f"{want} on both; "
                     f"without the fix: refused by the traditional baton at the client's execution point - "
                     f"invGuard.counts.baton {g0.get('baton')} -> {guard_counts(client).get('baton')}, line "
                     f"{ev['refusal']['invLastWarning'][1]!r} (the baton text is {TEXT_NOT_YOUR_GO!r}))")
    if guard_counts(client).get("baton", 0) != g0.get("baton", 0):
        fails.append(f"baton_free_placement: the client's invGuard.counts.baton {g0.get('baton')} -> "
                     f"{guard_counts(client).get('baton')} (want unchanged: the baton does not gate pre-battle "
                     f"placements)")
    if ev["cursorAfter"] != -1:
        fails.append(f"baton_free_placement: the client's cursor holds {ev['cursorAfter']} (want empty)")
    fails += tail_fails(host, client, "baton_free_placement")
    finish(fails)


def row_quick_unload(host, client, ctx):
    fails = kit_row_pre(host, client, ctx, "quick_unload")
    s = ctx.get("kit") or {}
    rifle, clip = (s.get("ids") or {}).get(RIFLE_T), s.get("rifleAmmo")
    ev = {"rifle": rifle, "clip": clip}
    if not fails:
        ih, ic = items_by_id(host), items_by_id(client)
        ev["before"] = {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)}
        for side in ("host", "client"):
            w = ev["before"][side] or {}
            if not (w.get("owner") == C1 and w.get("slot") == RIGHT_HAND and w.get("ammo") == [clip]):
                fails.append(f"quick_unload: the {side}'s rifle {rifle} {w} (want C1's, in {RIGHT_HAND}, loaded with "
                             f"{clip})")
    if fails:
        evidence("quick_unload", ev)
        finish([f.replace("quick_unload: ", "quick_unload: precondition absent - ") for f in fails])
    lw0 = es(client).get("invLocalWrites")
    ev["shiftClick"] = click(client, slot=RIGHT_HAND, x=0, y=0, mod="shift")

    def unloaded(its):
        w = weapon_view(its, rifle) or {}
        return w.get("owner") == C1 and w.get("slot") == RIGHT_HAND and w.get("ammo") == [] \
            and on_pile(item_view(its, clip))

    got, dt = wait_until(lambda: unloaded(items_by_id(host)) and unloaded(items_by_id(client)), LAND_WAIT_S, 0.1)
    ih, ic = items_by_id(host), items_by_id(client)
    lw1 = es(client).get("invLocalWrites")
    ev.update({"within": dt if got else None, "after": {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)},
               "clipAfter": {"host": item_view(ih, clip), "client": item_view(ic, clip)},
               "invLocalWrites": [lw0, lw1], "diff": diff_buckets(host, client),
               "invGuardLast": (es(client).get("invGuard") or {}).get("last"),
               "cursor": inv_view(client).get("selectedItem"), "c1Tu": tus(host, client, C1),
               "turn": [turn(host), turn(client)]})
    evidence("quick_unload", ev)
    if not got:
        fails.append(f"quick_unload: after the Shift-click rifle host={ev['after']['host']} "
                     f"client={ev['after']['client']}, "
                     f"clip {clip} host={ev['clipAfter']['host']} client={ev['clipAfter']['client']} (want the rifle in "
                     f"{RIGHT_HAND} unloaded and the clip on the ground at {PILE} on both within {LAND_WAIT_S} s)")
    if lw1 != lw0:
        fails.append(f"quick_unload: the client's invLocalWrites {lw0} -> {lw1} (want unchanged; without the fix "
                     f"vanilla's quick-unload branch writes on the client alone; buckets differ {ev['diff']})")
    if ev["cursor"] != -1:
        fails.append(f"quick_unload: the client's cursor holds {ev['cursor']} (want empty)")
    fails += tail_fails(host, client, "quick_unload")
    finish(fails)


def fuses(host, client, iid):
    return [(item_view_fuse(items_by_id(host), iid)), (item_view_fuse(items_by_id(client), iid))]


def item_view_fuse(its, iid):
    return (its.get(iid) or {}).get("fuse")


def right_click_c1(client, cell):
    return click(client, slot=BELT, x=cell[0], y=cell[1], button="right")


def row_prime_unprime(host, client, ctx):
    fails = kit_row_pre(host, client, ctx, "prime_unprime")
    g = ((ctx.get("kit") or {}).get("ids") or {}).get(GRENADE_T)
    ev = {"grenade": g}
    if not fails:
        ev["fuseBefore"] = fuses(host, client, g)
        ih = items_by_id(host)
        v = item_view(ih, g) or {}
        if not (v.get("owner") == C1 and v.get("slot") == BELT and (v.get("slotX"), v.get("slotY")) == GRENADE_CELL
                and ev["fuseBefore"] == [FUSE_NONE, FUSE_NONE]):
            fails.append(f"prime_unprime: the staged grenade {g} {v} fuse host/client {ev['fuseBefore']} (want C1's, "
                         f"{BELT} {GRENADE_CELL}, unprimed on both)")
    if fails:
        evidence("prime_unprime", ev)
        finish([f.replace("prime_unprime: ", "prime_unprime: precondition absent - ") for f in fails])
    # 1. right-click -> PrimeGrenadeState on the client -> key 3
    ev["rightClick1"] = right_click_c1(client, GRENADE_CELL)
    g1, d1 = wait_until(lambda: top(client) == "PrimeGrenadeState", CLICK_WAIT_S)
    ev["primeScreenWithin"] = d1 if g1 else None
    if g1:
        k = client.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_3})
        ev["key3"] = {"ok": k.get("ok"), "error": k.get("error")}
        g2, d2 = wait_until(lambda: top(client) == "InventoryState", CLICK_WAIT_S)
        ev["primeScreenClosedWithin"] = d2 if g2 else None
    got3, d3 = wait_until(lambda: fuses(host, client, g) == [FUSE_KEYED, FUSE_KEYED], ANSWER_WAIT_S, 0.1)
    ev["primed"] = {"within": d3 if got3 else None, "fuse": fuses(host, client, g), "clientTop": top(client)}
    # 2. right-click again -> unprime
    ev["rightClick2"] = right_click_c1(client, GRENADE_CELL)
    got4, d4 = wait_until(lambda: fuses(host, client, g) == [FUSE_NONE, FUSE_NONE], ANSWER_WAIT_S, 0.1)
    ev["unprimed"] = {"within": d4 if got4 else None, "fuse": fuses(host, client, g), "clientTop": top(client)}
    ev.update({"invGuardLast": (es(client).get("invGuard") or {}).get("last"),
               "invLocalWrites": es(client).get("invLocalWrites"), "c1Tu": tus(host, client, C1),
               "turn": [turn(host), turn(client)]})
    evidence("prime_unprime", ev)
    if not g1:
        fails.append(f"prime_unprime: the right-click on {g} opened no PrimeGrenadeState on the client (top "
                     f"{top(client)!r})")
    elif ev.get("primeScreenClosedWithin") is None:
        fails.append(f"prime_unprime: key 3 left the client on {top(client)!r} (want its InventoryState back on top)")
    if not got3:
        fails.append(f"prime_unprime: after key 3 the fuse host/client {ev['primed']['fuse']} (want [{FUSE_KEYED}, "
                     f"{FUSE_KEYED}] within {ANSWER_WAIT_S} s; without the fix: the fuse written on the client alone)")
    if not got4:
        fails.append(f"prime_unprime: after the second right-click the fuse host/client {ev['unprimed']['fuse']} (want "
                     f"[{FUSE_NONE}, {FUSE_NONE}] within {ANSWER_WAIT_S} s)")
    fails += tail_fails(host, client, "prime_unprime")
    finish(fails)


def row_default_fuse(host, client, ctx):
    fails = kit_row_pre(host, client, ctx, "default_fuse")
    p = ((ctx.get("kit") or {}).get("ids") or {}).get(PROX_T)
    ev = {"proximity": p}
    if not fails:
        ev["fuseBefore"] = fuses(host, client, p)
        v = item_view(items_by_id(host), p) or {}
        if not (v.get("owner") == C1 and v.get("slot") == BELT and (v.get("slotX"), v.get("slotY")) == PROX_CELL
                and ev["fuseBefore"] == [FUSE_NONE, FUSE_NONE]):
            fails.append(f"default_fuse: the staged proximity grenade {p} {v} fuse host/client {ev['fuseBefore']} "
                         f"(want C1's, {BELT} {PROX_CELL}, unprimed on both)")
    if fails:
        evidence("default_fuse", ev)
        finish([f.replace("default_fuse: ", "default_fuse: precondition absent - ") for f in fails])
    ev["rightClick"] = right_click_c1(client, PROX_CELL)
    got, dt = wait_until(lambda: fuses(host, client, p) == [FUSE_DEFAULT_INSTANT, FUSE_DEFAULT_INSTANT], ANSWER_WAIT_S,
                         0.1)
    ev.update({"within": dt if got else None, "fuse": fuses(host, client, p), "clientTop": top(client),
               "invGuardLast": (es(client).get("invGuard") or {}).get("last"),
               "invLocalWrites": es(client).get("invLocalWrites"), "turn": [turn(host), turn(client)]})
    evidence("default_fuse", ev)
    if not got:
        fails.append(f"default_fuse: after the right-click the fuse host/client {ev['fuse']} (want the default "
                     f"[{FUSE_DEFAULT_INSTANT}, {FUSE_DEFAULT_INSTANT}] within {ANSWER_WAIT_S} s; without the fix: "
                     f"written on the client alone)")
    if ev["clientTop"] != "InventoryState":
        fails.append(f"default_fuse: the client's top {ev['clientTop']!r} (want its InventoryState: an instant fuse "
                     f"opens no timer screen)")
    fails += tail_fails(host, client, "default_fuse")
    finish(fails)


# ===================== leave and rejoin during the pre-battle equip =====================


def dump(gc):
    """One machine's probe dump (the evidence for a setup failure): stack, phase, authority, turn, the equip probe,
    the top CoopState dialog and the inventory view."""
    try:
        bs = battle_state(gc)
        e = es(gc)
        d = dialog(gc)
        a = bs.get("authority") or {}
        return {"stack": stack(gc), "phase": e.get("phase"), "peerAbsent": a.get("peerAbsent"),
                "battleId": a.get("battleId"), "turn": bs.get("turn"), "inBattle": bs.get("inBattle"),
                "equip": e.get("equip"), "turnMirrorFired": e.get("turnMirrorFired"),
                "dialog": {k: d.get(k) for k in ("present", "code", "title", "backText", "backVisible")},
                "view": view_brief(inv_view(gc))}
    except Exception as ex:  # a dead instance
        return {"error": short(ex, 200)}


def ready_of(gc, seat=SEAT_CLIENT):
    r = equip(gc).get("ready") or []
    return r[seat] if len(r) > seat else None


def host_paused(host):
    d = dialog(host)
    return bool(d.get("present") and d.get("code") == COOP_DLG_WAIT_PLAYERS)


def leave_to_menu(host, client, rec):
    """The leave of test_pause_on_leave.py: the client's disconnect_to_menu -> its main menu; the host notices the
    drop (get_coop coopSession false) and raises its pause dialog COOP_DLG_WAIT_PLAYERS. Fills rec."""
    t = time.time()
    r = client.cmd({"cmd": "disconnect_to_menu"})
    rec["disconnect"] = {k: r.get(k) for k in ("ok", "error")}
    g1, d1 = wait_until(lambda: top(client) == "MainMenuState", LEAVE_WAIT_S, 0.2)
    g2, d2 = wait_until(lambda: not host.cmd({"cmd": "get_coop"}).get("coopSession"), PAUSE_WAIT_S, 0.1)
    g3, d3 = wait_until(lambda: host_paused(host), PAUSE_WAIT_S, 0.1)
    rec.update({"leaverMenuWithin": d1 if g1 else None, "hostNoticedWithin": d2 if g2 else None,
                "hostPausedWithin": d3 if g3 else None, "sinceLeave": round(time.time() - t, 3),
                "leaverStack": stack(client), "host": dump(host)})


def rejoin_and_resume(host, ctx, tag, rec):
    """The rejoin of test_skirmish_rejoin_battle.py's scenario_rejoin_and_resume: the player comes back in a fresh
    process (NEW BATTLE > COOP > browser > join) and holds the running battle on COOP_DLG_CLIENT_RESUME_HOLD; the
    host's pause dialog offers RESUME (the join's Profile popup cleared as it appears); the host presses RESUME
    (coop_dialog_back); the rejoiner's hold and the host's dialog close. Returns the rejoiner (a new GameClient,
    registered in ctx['clients'] for the boot's shutdown). Fills rec; rec['resumed'] is True when every step
    happened within its bound."""
    gc = GameClient(f"client-{tag}", None, make_user_dir(f"prebattle_equip_rejoin_{tag}"))
    ctx["clients"].append(gc)
    gc.spawn()
    gc.connect()
    t = time.time()
    rejoin_skirmish(gc, ctx["port"], CLIENT_PLAYER)
    g1, d1 = wait_until(lambda: in_battle_save(gc), REJOIN_WAIT_S, 0.25)
    h = dialog(gc)
    rec.update({"inBattleWithin": d1 if g1 else None, "hold": {k: h.get(k) for k in ("present", "code", "title")},
                "rejoinerStackHeld": stack(gc)})

    def resume_offered():
        if session.has_state(host, "Profile"):
            host.cmd({"cmd": "profile_ok"})
            return None
        return dialog(host).get("backVisible") or None

    g2, d2 = wait_until(resume_offered, RESUME_OFFER_WAIT_S, 0.2) if g1 else (None, None)
    hd = dialog(host)
    rec.update({"resumeOfferedWithin": d2 if g2 else None,
                "hostDialog": {k: hd.get(k) for k in ("present", "code", "title", "backText", "backVisible")},
                "hostBeforeResume": dump(host)})
    g3 = None
    if g2:
        r = host.cmd({"cmd": "coop_dialog_back"})
        rec["resume"] = {k: r.get(k) for k in ("ok", "error")}
        g3, d3 = wait_until(lambda: not dialog(gc).get("present") and not dialog(host).get("present"),
                            RELEASE_WAIT_S, 0.05)
        rec["releasedWithin"] = d3 if g3 else None
    rec["resumed"] = bool(g1 and h.get("code") == COOP_DLG_CLIENT_RESUME_HOLD and g2 and g3)
    rec["sinceRejoin"] = round(time.time() - t, 3)
    return gc


def after_resume(host, rj, rec):
    """The rejoiner's screen after RESUME (<= ENTRY_WAIT_S from the release) and both machines' views."""
    got, dt = wait_until(lambda: screen_up(rj), ENTRY_WAIT_S)
    rec["screenWithin"] = dt if got else None
    rec["rejoiner"] = dump(rj)
    rec["host"] = dump(host)
    rec["rejoinerGround"] = ground_ids(inv_view(rj))
    rec["hostPile"] = pile_ids(items_by_id(host))
    rec["turn"] = [turn(host), turn(rj)]
    return bool(got)


def rejoin_fixture_fails(row, rec):
    if not rec.get("resumed"):
        return [f"{row}: FIXTURE - the rejoin did not complete (rejoiner inBattle within {rec.get('inBattleWithin')}, "
                f"hold {rec.get('hold')}, RESUME offered within {rec.get('resumeOfferedWithin')} host dialog "
                f"{rec.get('hostDialog')}, released within {rec.get('releasedWithin')})"]
    return []


def rejoin_screen_checks(row, host, rj, rec, ok_pressed, host_screen=True):
    """The checks every rejoin row shares: the rejoiner's pre-battle screen (the check of the fix first), its OK
    look, the pile, the host's screen (not for leave_in_host_briefing: the host still reads its briefing), the equip
    phase and turn 0 on both."""
    fails = []
    rv = (rec.get("rejoiner") or {}).get("view") or {}
    eq = (rec.get("rejoiner") or {}).get("equip") or {}
    if rec.get("screenWithin") is None:
        fails.append(f"{row}: the rejoiner's top is {top(rj)!r} {ENTRY_WAIT_S} s after RESUME released its hold (want "
                     f"its pre-battle InventoryState; without the fix: no equip screen after the rejoin - rejoiner "
                     f"equip.phase {eq.get('phase')!r}, stack {(rec.get('rejoiner') or {}).get('stack')})")
    else:
        if rv.get("unitId") not in C_IDS:
            fails.append(f"{row}: the rejoiner's screen shows unit {rv.get('unitId')} (want one of C {C_IDS})")
        if rv.get("okPressed") is not ok_pressed:
            fails.append(f"{row}: the rejoiner's okPressed={rv.get('okPressed')} (want {ok_pressed})")
        if rec.get("rejoinerGround") != rec.get("hostPile"):
            fails.append(f"{row}: the rejoiner's ground ids {rec.get('rejoinerGround')} != the host's pile ids "
                         f"{rec.get('hostPile')} (want the pile)")
    if eq.get("pile") != list(PILE):
        fails.append(f"{row}: the rejoiner's equip.pile={eq.get('pile')} (want {list(PILE)})")
    hv = (rec.get("host") or {}).get("view") or {}
    if host_screen and not (hv.get("open") and hv.get("top") and hv.get("preBattle")):
        fails.append(f"{row}: the host's pre-battle screen is not back on top (host stack "
                     f"{(rec.get('host') or {}).get('stack')}, view {hv})")
    phases = [((rec.get("host") or {}).get("equip") or {}).get("phase"), eq.get("phase")]
    if phases != ["open", "open"]:
        fails.append(f"{row}: equip.phase host/rejoiner {phases} (want open on both)")
    if rec.get("turn") != [0, 0]:
        fails.append(f"{row}: turn host/rejoiner {rec.get('turn')} (want 0 on both)")
    return fails


def spine_leave_on_screen(host, client, ctx):
    """Boot leave_on_screen's spine: the client's briefing (<= 30 s); the host's close_briefing -> its pre-battle
    screen; the client's close_briefing -> its pre-battle screen; the host's equip-open announce applied on the
    client; the queues drained."""
    rec = {}
    g0, d0 = wait_until(lambda: has(client, "BriefingState"), CLIENT_BRIEFING_WAIT_S, 0.1)
    rec["clientBriefingWithin"] = d0 if g0 else None
    r = host.cmd({"cmd": "close_briefing"})
    g1, d1 = wait_until(lambda: screen_up(host), ENTRY_WAIT_S)
    c = client.cmd({"cmd": "close_briefing"})
    g2, d2 = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    g3, d3 = wait_until(lambda: equip(host).get("openAnnounced") is True and equip(client).get("openAnnounced") is True,
                        ANSWER_WAIT_S)
    g4, d4 = wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    rec.update({"hostClose": {k: r.get(k) for k in ("ok", "error")}, "hostScreenWithin": d1 if g1 else None,
                "clientClose": {k: c.get(k) for k in ("ok", "error")}, "clientScreenWithin": d2 if g2 else None,
                "announcedWithin": d3 if g3 else None, "drainedWithin": d4 if g4 else None,
                "host": dump(host), "client": dump(client)})
    print(f"SPINE leave_on_screen: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not (g0 and g1 and g2 and g3 and g4):
        raise AssertionError(f"spine: Boot leave_on_screen's equip screens never came up on both machines ({rec})")


def spine_leave_in_briefing(host, client, ctx):
    """Boot leave_in_briefing's spine: the client's briefing (<= 30 s); the client's close_briefing -> its
    pre-battle screen while the host still reads its briefing; the host in phase Active (the client's battle_ready
    arrived)."""
    rec = {}
    g0, d0 = wait_until(lambda: has(client, "BriefingState"), CLIENT_BRIEFING_WAIT_S, 0.1)
    rec["clientBriefingWithin"] = d0 if g0 else None
    c = client.cmd({"cmd": "close_briefing"})
    g1, d1 = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    g2, d2 = wait_until(lambda: es(host).get("phase") == "Active", ACTIVE_WAIT_S, 0.1)
    rec.update({"clientClose": {k: c.get(k) for k in ("ok", "error")}, "clientScreenWithin": d1 if g1 else None,
                "hostActiveWithin": d2 if g2 else None, "host": dump(host), "client": dump(client)})
    print(f"SPINE leave_in_briefing: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not (g0 and g1 and g2 and top(host) == "BriefingState"):
        raise AssertionError(f"spine: Boot leave_in_briefing's client screen / host briefing never held ({rec})")


def row_leave_not_ready(host, client, ctx):
    ev = {"before": {"host": dump(host), "client": dump(client)}}
    pre = []
    if not screen_up(host):
        pre.append(f"leave_not_ready: precondition absent - no host pre-battle screen (host {ev['before']['host']})")
    if not screen_up(client):
        pre.append(f"leave_not_ready: precondition absent - no client pre-battle screen (client "
                   f"{ev['before']['client']})")
    if ready_of(host) is not False or inv_view(client).get("okPressed") is not False:
        pre.append(f"leave_not_ready: precondition absent - the client is ready (host equip.ready[1] {ready_of(host)}, "
                   f"client okPressed {inv_view(client).get('okPressed')})")
    if pre:
        evidence("leave_not_ready", ev)
        finish(pre)
    # 1. the client (not ready) leaves; the host is paused over its pre-battle screen
    ev["leave"] = {}
    leave_to_menu(host, client, ev["leave"])
    hs = stack(host)
    ev["paused"] = {"hostStack": hs, "hostView": view_brief(inv_view(host)), "hostReady": equip(host).get("ready"),
                    "turn": turn(host)}
    lv = ev["leave"]
    if not (lv.get("leaverMenuWithin") is not None and lv.get("hostNoticedWithin") is not None
            and lv.get("hostPausedWithin") is not None and hs[-2:] == ["InventoryState", "CoopState"]
            and inv_view(host).get("preBattle") is True):
        evidence("leave_not_ready", ev)
        finish([f"leave_not_ready: FIXTURE - the host is not paused over its pre-battle screen after the leave (leave "
                f"{lv}, host stack {hs})"])
    # 2. the player rejoins; the host presses RESUME
    ev["rejoin"] = {}
    rj = rejoin_and_resume(host, ctx, "leave_on_screen_client2", ev["rejoin"])
    ctx["client"] = rj
    fails = rejoin_fixture_fails("leave_not_ready", ev["rejoin"])
    if fails:
        evidence("leave_not_ready", ev)
        finish(fails)
    # 3. the checks
    ev["after"] = {}
    after_resume(host, rj, ev["after"])
    evidence("leave_not_ready", ev)
    fails += rejoin_screen_checks("leave_not_ready", host, rj, ev["after"], False)
    if ready_of(host) is not False:
        fails.append(f"leave_not_ready: host equip.ready[1]={ready_of(host)} after the rejoin (want false: the client "
                     f"never pressed OK)")
    fails += tail_fails(host, rj, "leave_not_ready")
    finish(fails)


def row_leave_ready(host, client, ctx):
    ev = {"before": {"host": dump(host), "client": dump(client)}}
    fails = []
    # 1. the client presses OK (ready) on its pre-battle screen - the real click
    if screen_up(client) and screen_up(host) and inv_view(client).get("okPressed") is False:
        c = ok_press(client)
        g, d = wait_until(lambda: ready_of(host) is True, ANSWER_WAIT_S)
        ev["readyPress"] = {"click": c.get("error") or c.get("ok"), "hostReadyWithin": d if g else None,
                            "okPressed": inv_view(client).get("okPressed"), "hostReady": equip(host).get("ready")}
        if not (g and ev["readyPress"]["okPressed"] is True):
            fails.append(f"leave_ready: FIXTURE - the client's OK press did not make it ready ({ev['readyPress']})")
    else:
        ev["readyPress"] = {"absent": True, "clientStack": stack(client), "clientView": view_brief(inv_view(client)),
                            "hostView": view_brief(inv_view(host))}
        fails.append(f"leave_ready: no client pre-battle screen to press OK on before the leave (client stack "
                     f"{ev['readyPress']['clientStack']}; without the fix: no equip screen after leave_not_ready's "
                     f"rejoin)")
    pressed = ev["readyPress"].get("hostReadyWithin") is not None
    # 2. the client leaves; the host keeps its ready flag while it is away
    ev["leave"] = {}
    leave_to_menu(host, client, ev["leave"])
    hs = stack(host)
    ev["paused"] = {"hostStack": hs, "hostReady": equip(host).get("ready"), "turn": turn(host),
                    "hostView": view_brief(inv_view(host))}
    lv = ev["leave"]
    if not (lv.get("leaverMenuWithin") is not None and lv.get("hostNoticedWithin") is not None
            and lv.get("hostPausedWithin") is not None and hs[-2:] == ["InventoryState", "CoopState"]):
        evidence("leave_ready", ev)
        finish(fails + [f"leave_ready: FIXTURE - the host is not paused over its pre-battle screen after the leave "
                        f"(leave {lv}, host stack {hs})"])
    # 3. the player rejoins (a second fresh process); RESUME
    ev["rejoin"] = {}
    rj = rejoin_and_resume(host, ctx, "leave_on_screen_client3", ev["rejoin"])
    ctx["client"] = rj
    rf = rejoin_fixture_fails("leave_ready", ev["rejoin"])
    if rf:
        evidence("leave_ready", ev)
        finish(fails + rf)
    # 4. the rejoiner's screen, ready kept, the waiting line naming the host
    ev["after"] = {}
    got = after_resume(host, rj, ev["after"])
    if got:
        time.sleep(LINE_READ_S)
        v = inv_view(rj)
        ev["after"]["line"] = {"text": v.get("lineText"), "visible": v.get("lineVisible"), "readAtS": LINE_READ_S}
    ev["after"]["hostReady"] = equip(host).get("ready")
    ev["after"]["rejoinerReady"] = equip(rj).get("ready")
    # 5. the host's OK (the real click) -> turn 1 on both
    ev["hostOk"] = {}
    if screen_up(host):
        c = ok_press(host)
        g, d = wait_until(lambda: turn(host) == 1 and turn(rj) == 1, TURN_WAIT_S)
        ev["hostOk"] = {"click": c.get("error") or c.get("ok"), "turnWithin": d if g else None}
    ev["hostOk"].update({"turn": [turn(host), turn(rj)], "phase": [equip(host).get("phase"), equip(rj).get("phase")],
                         "barrierDone": equip(host).get("barrierDone"), "host": dump(host), "rejoiner": dump(rj)})
    evidence("leave_ready", ev)
    fails += rejoin_screen_checks("leave_ready", host, rj, ev["after"], True)
    hr = ev["after"]["hostReady"] or []
    if pressed and (hr[SEAT_CLIENT] if len(hr) > SEAT_CLIENT else None) is not True:
        fails.append(f"leave_ready: host equip.ready {hr} after the rejoin (want seat {SEAT_CLIENT} true: the ready "
                     f"flag kept across the leave)")
    if ev["after"].get("screenWithin") is not None:
        rr = ev["after"]["rejoinerReady"] or []
        if (rr[SEAT_CLIENT] if len(rr) > SEAT_CLIENT else None) is not True:
            fails.append(f"leave_ready: the rejoiner's equip.ready {rr} (want seat {SEAT_CLIENT} true: its own ready "
                         f"kept)")
        ln = ev["after"].get("line") or {}
        if not (ln.get("text") == TEXT_WAIT_HOST and ln.get("visible") is True):
            fails.append(f"leave_ready: the rejoiner's line at +{LINE_READ_S} s {ln.get('text')!r} "
                         f"visible={ln.get('visible')} (want {TEXT_WAIT_HOST!r} visible)")
    ho = ev["hostOk"]
    if ho.get("turnWithin") is None:
        fails.append(f"leave_ready: after the host's OK turn host/rejoiner {ho.get('turn')} (want 1 on both within "
                     f"{TURN_WAIT_S} s; host screen up before the press: {bool(ho.get('click'))})")
    else:
        if ho.get("phase") != ["ended", "ended"]:
            fails.append(f"leave_ready: equip.phase host/rejoiner {ho.get('phase')} after turn 1 (want ended on both)")
        if ho.get("barrierDone") is not True:
            fails.append(f"leave_ready: host equip.barrierDone={ho.get('barrierDone')} (want true)")
    fails += tail_fails(host, rj, "leave_ready")
    finish(fails)


def row_leave_in_host_briefing(host, client, ctx):
    """The client leaves during the host's briefing; the host's pause-on-leave dialog covers the briefing; the
    player rejoins (the rejoin offer is built with no host BattlescapeState and openAnnounced false, while the host
    reads its briefing); the host presses RESUME; its briefing is back on top; the rejoiner lands on its equip
    screen while the host still reads its briefing; the host presses its briefing's OK (the real click); the host's
    equip-open announce reaches the rejoiner."""
    ev = {"before": {"host": dump(host), "client": dump(client)}}
    pre = []
    if top(host) != "BriefingState":
        pre.append(f"leave_in_host_briefing: precondition absent - the host is not in its briefing (host stack "
                   f"{stack(host)})")
    if not screen_up(client):
        pre.append(f"leave_in_host_briefing: precondition absent - no client pre-battle screen (client "
                   f"{ev['before']['client']})")
    if es(host).get("phase") != "Active":
        pre.append(f"leave_in_host_briefing: precondition absent - host phase {es(host).get('phase')!r} (want Active: "
                   f"the client's battle_ready arrived)")
    if pre:
        evidence("leave_in_host_briefing", ev)
        finish(pre)
    # 1. the client leaves during the host's briefing; 2. the host's pause dialog covers the briefing
    ev["leave"] = {}
    leave_to_menu(host, client, ev["leave"])
    hs = stack(host)
    ev["paused"] = {"hostStack": hs, "hostEquip": equip(host)}
    lv = ev["leave"]
    if not (lv.get("leaverMenuWithin") is not None and lv.get("hostNoticedWithin") is not None
            and lv.get("hostPausedWithin") is not None and hs[-2:] == ["BriefingState", "CoopState"]):
        evidence("leave_in_host_briefing", ev)
        finish([f"leave_in_host_briefing: FIXTURE - the host's pause dialog does not cover its briefing after the "
                f"leave (leave {lv}, host stack {hs})"])
    # 3. the player rejoins; 4. the host presses RESUME
    ev["rejoin"] = {}
    rj = rejoin_and_resume(host, ctx, "leave_in_briefing_client2", ev["rejoin"])
    ctx["client"] = rj
    fails = rejoin_fixture_fails("leave_in_host_briefing", ev["rejoin"])
    hb = ev["rejoin"].get("hostBeforeResume") or {}
    hbe = hb.get("equip") or {}
    if "BattlescapeState" in (hb.get("stack") or []) or hbe.get("openAnnounced") is not False \
            or hbe.get("hostOpen") is not False:
        fails.append(f"leave_in_host_briefing: FIXTURE - the rejoin offer was not built while the host reads its "
                     f"briefing (host stack "
                     f"{hb.get('stack')}, equip.hostOpen {hbe.get('hostOpen')}, openAnnounced {hbe.get('openAnnounced')}; "
                     f"want no BattlescapeState, both false)")
    # 5. the host's briefing is back on top
    g0, d0 = wait_until(lambda: top(host) == "BriefingState", ENTRY_WAIT_S)
    ev["briefingBack"] = {"within": d0 if g0 else None, "hostStack": stack(host)}
    if not g0:
        fails.append(f"leave_in_host_briefing: FIXTURE - after RESUME the host's top is {top(host)!r}, not its "
                     f"briefing (host stack {stack(host)})")
    if fails:
        evidence("leave_in_host_briefing", ev)
        finish(fails)
    # the rejoiner on its equip screen while the host still reads its briefing
    ev["after"] = {}
    after_resume(host, rj, ev["after"])
    ev["after"]["hostTopAtScreen"] = top(host)
    # 6. the host presses its briefing's OK (the real click on the top state's OK button)
    c = host.cmd({"cmd": "click_widget", "match": "ok"})
    g1, d1 = wait_until(lambda: screen_up(host), ENTRY_WAIT_S)
    g2, d2 = wait_until(lambda: equip(host).get("openAnnounced") is True and equip(rj).get("openAnnounced") is True,
                        ANSWER_WAIT_S)
    g3, d3 = wait_until(lambda: drained(host, rj), DRAIN_WAIT_S, 0.1)
    ev["hostOk"] = {"click": {k: c.get(k) for k in ("ok", "error")}, "hostScreenWithin": d1 if g1 else None,
                    "announcedWithin": d2 if g2 else None, "drainedWithin": d3 if g3 else None,
                    "host": dump(host), "rejoiner": dump(rj), "rejoinerGround": ground_ids(inv_view(rj)),
                    "hostPile": pile_ids(items_by_id(host)), "turn": [turn(host), turn(rj)]}
    evidence("leave_in_host_briefing", ev)
    fails += rejoin_screen_checks("leave_in_host_briefing", host, rj, ev["after"], False, host_screen=False)
    if ev["after"].get("screenWithin") is not None and ev["after"]["hostTopAtScreen"] != "BriefingState":
        fails.append(f"leave_in_host_briefing: the host's top was {ev['after']['hostTopAtScreen']!r} when the "
                     f"rejoiner's screen came up "
                     f"(want its BriefingState: the rejoiner equips while the host still reads its briefing)")
    if c.get("error") or not g1:
        fails.append(f"leave_in_host_briefing: FIXTURE - the host's briefing OK click {ev['hostOk']['click']} left no "
                     f"host pre-battle screen (host stack {(ev['hostOk']['host'] or {}).get('stack')})")
    if not g2:
        fails.append(f"leave_in_host_briefing: equip.openAnnounced host/rejoiner {equip(host).get('openAnnounced')}/"
                     f"{equip(rj).get('openAnnounced')} {ANSWER_WAIT_S} s after the host's briefing OK (want true on "
                     f"both: the host's equip-open announce reaches the rejoiner)")
    ho = ev["hostOk"]
    if ev["after"].get("screenWithin") is not None and ho["rejoinerGround"] != ho["hostPile"]:
        fails.append(f"leave_in_host_briefing: after the host's OK the rejoiner's ground ids {ho['rejoinerGround']} != "
                     f"the host's pile ids {ho['hostPile']}")
    if ho["turn"] != [0, 0]:
        fails.append(f"leave_in_host_briefing: turn host/rejoiner {ho['turn']} after the host's briefing OK (want 0 on "
                     f"both)")
    fails += tail_fails(host, rj, "leave_in_host_briefing")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine (a failure there fails the
# run, and the rows after it fail on their own preconditions).
STEPS_TRADITIONAL = (("host_equips_in_handshake", row_host_equips_in_handshake),
           (None, stage_c1_kit),
           ("baton_free_placement", row_baton_free_placement),
           ("quick_unload", row_quick_unload),
           ("prime_unprime", row_prime_unprime),
           ("default_fuse", row_default_fuse))
STEPS_LEAVE_ON_SCREEN = ((None, spine_leave_on_screen),
            ("leave_not_ready", row_leave_not_ready),
            ("leave_ready", row_leave_ready))
STEPS_LEAVE_IN_BRIEFING = ((None, spine_leave_in_briefing),
            ("leave_in_host_briefing", row_leave_in_host_briefing))


def boot_traditional(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    ctx = {}

    def pre_ok(h):
        h.ok({"cmd": "set_seed", "seed": SEED_MAP})
        set_mode(h, TRADITIONAL)

    def pre_newbattle(h, c):
        ctx["arm"] = hold(c, on=True)
        assert ctx["arm"].get("ok") and ctx["arm"].get("armed") is True, f"hold_battle_ready {{on: true}}: {ctx['arm']}"

    session.bring_up_to_briefings(host, client, seated, seat_count=2, pre_ok=pre_ok, pre_newbattle=pre_newbattle)
    hb = battle_state(host)
    assert hb.get("mapFingerprint") == MAP_FP, (
        f"host mapFingerprint {hb.get('mapFingerprint')!r} (baked MAP_FP {MAP_FP!r}, SEED_MAP {SEED_MAP})")
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == C_IDS, f"seated client units {seated_uids} (baked C {C_IDS})"
    h_ids = sorted(u["id"] for u in hb["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids == H_IDS, f"host-seat soldiers {h_ids} (baked H {H_IDS})"
    print(f"[prebattle_equip_rejoin] boot traditional ok: MAP_FP={MAP_FP!r} seated={seated_uids} H={h_ids} "
          f"arm={ctx['arm']} host stack={stack(host)} client stack={stack(client)}", flush=True)
    return ctx


def boot_rejoin(port):
    def boot(host, client):
        bring_up_lobby_roster_pinned(host, client, port)
        seated = {}
        session.bring_up_to_briefings(host, client, seated, seat_count=2,
                                      pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
        hb = battle_state(host)
        assert hb.get("mapFingerprint") == MAP_FP, (
            f"host mapFingerprint {hb.get('mapFingerprint')!r} (baked MAP_FP {MAP_FP!r}, SEED_MAP {SEED_MAP})")
        sid_to_uid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
        seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
        assert seated_uids == C_IDS, f"seated client units {seated_uids} (baked C {C_IDS})"
        h_ids = sorted(u["id"] for u in hb["units"] if u.get("coop") == COOP_SEAT_0
                       and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
        assert h_ids == H_IDS, f"host-seat soldiers {h_ids} (baked H {H_IDS})"
        print(f"[prebattle_equip_rejoin] boot (lobby {port}) ok: MAP_FP={MAP_FP!r} seated={seated_uids} H={h_ids} "
              f"host stack={stack(host)} client stack={stack(client)}", flush=True)
        return {"port": port, "clients": []}
    return boot


# (boot name, user-dir tag, bring-up, steps)
BOOTS = (("traditional", "traditional", boot_traditional, STEPS_TRADITIONAL),
         ("leave_on_screen", "leave_on_screen", boot_rejoin(PORT_LEAVE_ON_SCREEN), STEPS_LEAVE_ON_SCREEN),
         ("leave_in_briefing", "leave_in_briefing", boot_rejoin(PORT_LEAVE_IN_BRIEFING), STEPS_LEAVE_IN_BRIEFING))
ROWS = [n for _, _, _, steps in BOOTS for n, _ in steps if n]


def run_boot(name, tag, boot, steps, results):
    """One boot: bring-up, then its steps in order (each row ONE run). Returns False when the bring-up or a spine
    step failed. Every instance the boot spawned (the rejoiners too) is shut down at its end."""
    host = GameClient("host", None, make_user_dir(f"prebattle_equip_rejoin_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"prebattle_equip_rejoin_{tag}_client"))
    spine_ok = True
    ctx = {"clients": []}
    try:
        try:
            ctx = boot(host, client)
            ctx.setdefault("clients", [])
        except Exception as e:  # a bring-up failure fails this boot's rows
            print(f"FAIL boot {name}: {type(e).__name__}: {e}", flush=True)
            return False
        for row, fn in steps:
            try:
                fn(host, ctx.get("client", client), ctx)
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
        for gc in [host, client] + list(ctx.get("clients", [])):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[prebattle_equip_rejoin] shutdown boot {name} {gc.name}: {short(e)}", flush=True)
    return spine_ok


def main():
    t0 = time.time()
    results = {}
    spine_ok = True
    for name, tag, boot, steps in BOOTS:
        tb = time.time()
        spine_ok = run_boot(name, tag, boot, steps, results) and spine_ok
        print(f"[prebattle_equip_rejoin] boot {name} done in {time.time() - tb:.1f}s", flush=True)
    passed = [n for n in ROWS if results.get(n)]
    failed = [n for n in ROWS if not results.get(n)]
    print(f"\ntest_prebattle_equip_rejoin: {len(passed)}/{len(ROWS)} passed "
          f"(pass={passed} fail={failed}{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (not failed and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
