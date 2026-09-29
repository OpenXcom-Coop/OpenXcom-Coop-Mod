"""W2-P8b - test_w2_prebattle_equip_rejoin.py: pre-battle equip, Boot W (traditional turn
mode). Stage S-A's row EQ1b: the host closes its briefing BEFORE the second player's
battle_ready arrives (the handshake window, phase Handshake) - its equip screen opens,
shows only its own soldiers, and the equip-open announce goes out once the battle is
Active (spec docs rewrite/prompts/w2p8b_prebattle_equip.md: owner D174 a, D206 c, D210 b;
AMENDMENT P8b-1 section 4 steps 4 and 10, section 5 (Boot W, EQ1b), section 8; P8b-1
RULINGS Q16 (a): the test-only client lever `hold_battle_ready` makes the window
deterministic; AMENDMENT P8b-2 (the TASK 0 constants F3314-F3331)). Later stages add
their rows to this file: S-B EQ10b, EQ11b, EQ13, EQ13b (L); S-D's boots R1 (EQ21, EQ22)
and R2 (EQ23).

Before S-A.2 (product untouched, commit S-A.1) the host's battle file goes out only
when the host closes its own briefing and the host's pre-battle equip is frozen: its
briefing OK starts turn 1 at once and no equip screen opens.

Boot W (ONE boot): the roster-pinned lobby (set_seed SEED_ROSTER before
open_new_battle), session.bring_up_to_briefings (the client seated C1, C2; the host
keeps H) with pre_ok = set_seed SEED_MAP then CoopTurnMode traditional on the host
(test_rw_turn_baton.py's recipe, in TASK 0's order) and pre_newbattle = the CLIENT's
hold_battle_ready {on: true}; the host's mapFingerprint = MAP_FP.
  EQ1b  (1) wait <= 30 s for the client's BriefingState (the client holds the battle
        while the host reads its briefing, D210 b) with its battle_ready stashed (the
        host stays in phase Handshake); staging as soon as both machines hold the battle
        (C1, C2 and every H soldier stripped on both, then one each of STAGE_TYPES on the
        pile, client first); (2) host close_briefing; (3) host inventory_click {widget:
        next} x3; (4) the host moves the staged clip from the pile to its current
        soldier's belt (0,0); (5) the client's hold_battle_ready {on: false}.
        GREEN: after (2) the host's top is its pre-battle InventoryState (preBattle), turn
        0, phase Handshake; (3) visits only H ids, in phase Handshake; (4) lands on the
        host, still Handshake and equip.openAnnounced false; after (5): the host's phase
        Active, equip.openAnnounced true (the announce `sync`), the clip on that soldier's
        belt (0,0) on the client too, turn 0 on both, turnMode traditional on both.
        RED: the host's briefing OK starts turn 1 (the freeze) with no equip screen.
  RED (commit S-A.1): EQ1b fails on its RED cell.
Stage S-B's rows (AMENDMENT P8b-1 section 4 S-B and section 5; owner D205 a, D207 a:
pre-battle placements and priming are TU-free orders the host performs). The spine
after EQ1b: S-B's staging (client first, F607: C1 gets a rifle loaded with a clip in
STR_RIGHT_HAND, a STR_GRENADE on STR_BELT (1,0) and a STR_PROXIMITY_GRENADE on STR_BELT
(2,0), battle_give; the ids recorded), then the client's close_briefing -> its
pre-battle screen on C1. EQ11b, EQ13 and EQ13b are this boot's LAST rows (P8b-1 section
5 (L)): at red each writes on the client alone, and that divergence fails every later
row of the boot.
  EQ10b the baton (F3118): the host holds the traditional baton at turn 0; the client
        moves the first pile STR_GRENADE to C1's STR_BELT (0,0). GREEN: it lands there
        on both, the client's invGuard.counts.baton unchanged. RED: refused at the
        client's execution point by the baton term (`not_your_go`, invGuard.counts.baton
        +1); the item then leaves the client's cursor by a right-click (vanilla's
        return).
  EQ11b quick unload (F3111): a Shift-click on C1's loaded rifle in STR_RIGHT_HAND.
        GREEN: the rifle stays in STR_RIGHT_HAND unloaded, its clip on the ground at PILE,
        on both; the client's invLocalWrites 0. RED: vanilla's `quickUnload && !_tu`
        branch writes on the client alone (invLocalWrites > 0, buckets unequal).
  EQ13  prime / unprime (F2760): a right-click on C1's STR_GRENADE -> the client's
        PrimeGrenadeState -> key 3; then a right-click again. GREEN: fuse 3 on both,
        then -1 on both. RED: fuse 3 on the client alone, -1 on the host.
  EQ13b the default fuse (Inventory.cpp's BFT_INSTANT branch): a right-click on C1's
        STR_PROXIMITY_GRENADE. GREEN: its default fuse (0) on both. RED: on the client
        alone, -1 on the host.
  RED (commit S-B.1): exactly EQ10b, EQ11b, EQ13, EQ13b fail, each on its RED cell;
  EQ1b passes.

Common asserts (after the release): hash_now {full:true} every bucket EQUAL after the
queues drain; desyncSeen false on both; the client's turnMirrorFired 0;
coopClientBStatePushes 0 on both; the client's invLocalWrites 0; while the client's
pre-battle screen is open, its ground ids = the host's pile ids (STOP-IF 8). The hold is
always released at the end of EQ1b (recorded), so a failed row never leaves the host in
phase Handshake.

Constants (AMENDMENT P8b-2 / docs rewrite/w2p8b-task0/t0/logs, F3326): SEED_ROSTER 1,
SEED_MAP 1, MAP_FP (tseed_traditional.log: the same fingerprint as the parallel boot),
C [8, 9], H [10..14], PILE (14, 19, 1) (tseed_traditional.log "[seed] pile=[14, 19, 1]
C=[8, 9] H=[10, 11, 12, 13, 14]").

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked, then
"PASS <id>" / "FAIL <id>: <message>"; main() runs every row even after an earlier one
failed. Every wait is bounded. WV-D99 / WV-D100: one run is the result; no skip path, no
second boot. Exit 0 only when every row passes, 2 otherwise (a bring-up or spine failure
is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_prebattle_equip_rejoin.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
from test_w2_delta_core import both, short, diff_buckets, hashes
from test_w2_delta_items import items_by_id
from test_w2_host_combat import bring_up_lobby_roster_pinned
from test_w2_client_items import strip_both
from test_rw_turn_mode import set_mode, TRADITIONAL
from test_w2_prebattle_equip import (SEED_MAP, MAP_FP, C_IDS, H_IDS, PILE, COOP_SEAT_0, FACTION_PLAYER, BELT,
                                     EQ1_WAIT_S, ANSWER_WAIT_S, CLICK_WAIT_S, stack, top, has, es, equip, turn,
                                     in_battle, inv_view, view_brief, item_view, wait_until, evidence, finish,
                                     click, pick_ground, next_press, tail_fails,
                                     C1, GROUND, RIGHT_HAND, RIFLE_T, CLIP_T, GRENADE_T, ENTRY_WAIT_S, LAND_WAIT_S,
                                     screen_up, goto_unit, pre_screen_fails, first_of_type, weapon_view, on_pile,
                                     tus)

PORT = "48792"                     # this file's lobby port (unused by every other test file)
STAGE_TYPES_W = ("STR_RIFLE", "STR_RIFLE_CLIP", "STR_GRENADE", "STR_PROXIMITY_GRENADE")   # TASK 0's four (F3327)
HOST_NEXT_PRESSES = 3              # EQ1b cell: "host next x3"
PHASE_WAIT_S = 10.0                # the host reaches phase Active after the release
MOVE_WAIT_S = 5.0

# ----- S-B (AMENDMENT P8b-1 section 4 S-B, section 5 rows EQ10b, EQ11b, EQ13, EQ13b) -----
PROX_T = "STR_PROXIMITY_GRENADE"
SB_GIVE_W = ((RIFLE_T, {"ammo": CLIP_T}),                           # C1's loaded rifle, STR_RIGHT_HAND (EQ11b)
             (GRENADE_T, {"slot": BELT, "slotX": 1, "slotY": 0}),   # EQ13's grenade
             (PROX_T, {"slot": BELT, "slotX": 2, "slotY": 0}))      # EQ13b's proximity grenade
GRENADE_CELL = (1, 0)              # STR_BELT cells of the two staged grenades
PROX_CELL = (2, 0)
EQ10B_CELL = (0, 0)                # EQ10b's target: C1's STR_BELT (0,0)
SDLK_3 = 51                        # PrimeGrenadeState: _button[3]->onKeyboardPress(..., SDLK_3)
FUSE_KEYED = 3                     # EQ13: key 3 -> fuse 3
FUSE_NONE = -1                     # an unprimed grenade
FUSE_DEFAULT_INSTANT = 0           # RuleItem::getFuseTimerDefault() for BFT_INSTANT (STR_PROXIMITY_GRENADE)
TEXT_NOT_YOUR_GO = "Not your turn - waiting for HostPlayer"   # STR_COOP_DENY_NOT_YOUR_GO (EQ10b's RED, evidence)


def stage_w(host, client, ctx):
    """C1, C2 and every H soldier stripped on both machines, then one each of STAGE_TYPES_W on PILE (client
    first, F607; P8b-2: staged ids, never stock ids)."""
    rec = {}
    try:
        rec["stripped"] = {uid: strip_both(host, client, uid) for uid in C_IDS + H_IDS}
        ids = {}
        for t in STAGE_TYPES_W:
            r = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                     ("ids",))
            ids[t] = r["ids"][0]
        rec["ids"] = ids
        # F3364 / ruling SA-5 (W1-P8: the host allocates its hostile reveal set at onReady, i.e. at phase Active;
        # hash_now omits the key until then): while the host is in phase Handshake every bucket but revealHostile
        # is compared, and revealHostile must be ABSENT from the host's hash_now (present - equal or not - is a
        # FAIL); otherwise every bucket is compared.
        hh, ch = hashes(host), hashes(client)
        rec["hostPhase"] = es(host).get("phase")
        handshake = rec["hostPhase"] == "Handshake"
        skip = {"revealHostile"} if handshake else set()
        rec["diff"] = sorted(k for k in (set(hh) | set(ch)) - skip if hh.get(k) != ch.get(k))
        rec["revealHostile"] = [hh.get("revealHostile"), ch.get("revealHostile")]
        if handshake and "revealHostile" in hh:
            rec["revealHostileError"] = (f"the host is in phase Handshake but its hash_now carries revealHostile "
                                         f"{hh['revealHostile']!r} (want ABSENT: W1-P8 allocates it at onReady)")
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


def eq1b_host_equips_in_handshake(host, client, ctx):
    ev = {"arm": ctx.get("arm")}
    fails = []
    try:
        # (1) the client holds the battle during the host's briefing, battle_ready stashed
        got, dt = wait_until(lambda: has(client, "BriefingState"), EQ1_WAIT_S, 0.1)
        ev["clientBriefingWithin"] = dt if got else None
        ev["hold1"] = hold(client)
        ev["phase1"] = {"host": es(host).get("phase"), "client": es(client).get("phase"),
                        "clientStack": stack(client), "hostStack": stack(host)}
        if got and in_battle(client):
            stage_w(host, client, ctx)
        # (2) host close_briefing in phase Handshake
        r = host.cmd({"cmd": "close_briefing"})
        g2, d2 = wait_until(lambda: not has(host, "BriefingState"), 10.0)
        g3, d3 = wait_until(lambda: top(host) == "InventoryState" and inv_view(host).get("preBattle") is True, 5.0)
        hv = inv_view(host)
        ev["afterOk"] = {"close": {k: r.get(k) for k in ("ok", "error")}, "briefingGoneWithin": d2 if g2 else None,
                         "screenWithin": d3 if g3 else None, "hostTurn": turn(host), "hostStack": stack(host),
                         "hostPhase": es(host).get("phase"), "hostEquip": equip(host), "view": view_brief(hv)}
        if not (g3 and hv.get("preBattle") is True and ev["afterOk"]["hostTurn"] == 0):
            evidence("EQ1b", ev)
            fails.append(f"EQ1b: the host's briefing OK left turn {ev['afterOk']['hostTurn']} with no pre-battle "
                         f"screen (host stack {ev['afterOk']['hostStack']}, inventory_view {view_brief(hv)}; RED: the "
                         f"freeze starts turn 1 at the host's briefing OK)")
            finish(fails)   # raises; the `finally` below still releases the hold
        if ev["afterOk"]["hostPhase"] != "Handshake":
            fails.append(f"EQ1b: the host's phase after its briefing OK {ev['afterOk']['hostPhase']!r} (want Handshake: "
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
        evidence("EQ1b", ev)
        if not all(u in H_IDS for u in seen) or len(set(seen)) < 2:
            fails.append(f"EQ1b: the host's NEXT x{HOST_NEXT_PRESSES} visited {seen} (want only H ids {H_IDS}, and a "
                         f"real change of soldier)")
        if ev["next"]["phase"] != "Handshake":
            fails.append(f"EQ1b: the host's phase during NEXT {ev['next']['phase']!r} (want Handshake)")
        if staged_error(ctx):
            fails.append(f"EQ1b: {staged_error(ctx)}")
        if item is None:
            fails.append(f"EQ1b: the host did not pick the staged clip {clip} ({mv['pick']})")
        elif mv.get("hostWithin") is None:
            fails.append(f"EQ1b: the host's own move {item} -> {want} did not land on the host "
                         f"({item_view(items_by_id(host), item)})")
        if mv["hostPhase"] != "Handshake" or mv["openAnnounced"] is not False:
            fails.append(f"EQ1b: before the release host phase {mv['hostPhase']!r} openAnnounced "
                         f"{mv['openAnnounced']} (want Handshake, false: no announce before Active)")
        if ev["release"].get("sent") is not True:
            fails.append(f"EQ1b: the release sent no held battle_ready ({ev['release']})")
        ar = ev["afterRelease"]
        if ar["activeWithin"] is None:
            fails.append(f"EQ1b: the host never reached phase Active within {PHASE_WAIT_S} s of the release")
        if ar["announceWithin"] is None:
            fails.append(f"EQ1b: host equip.openAnnounced {ar['hostEquip'].get('openAnnounced')} after Active (want "
                         f"true: the equip-open announce `sync`)")
        if ar["clientMoveWithin"] is None:
            fails.append(f"EQ1b: the host's move is not on the client: {ar['itemClient']} (want {want} within "
                         f"{MOVE_WAIT_S} s)")
        if ar["turn"] != [0, 0]:
            fails.append(f"EQ1b: turn host/client {ar['turn']} (want 0 on both)")
        if ar["turnMode"] != ["traditional", "traditional"]:
            fails.append(f"EQ1b: FIXTURE - turnMode host/client {ar['turnMode']} (want traditional on both)")
        fails += tail_fails(host, client, "EQ1b")
        # F3364 / ruling SA-5: after the release (host Active) every bucket incl. revealHostile is EQUAL - and
        # revealHostile is PRESENT on both (the tail's diff alone would pass a key absent on both).
        hh, ch = hashes(host), hashes(client)
        rh = [hh.get("revealHostile"), ch.get("revealHostile")]
        if not ("revealHostile" in hh and "revealHostile" in ch and rh[0] == rh[1]):
            fails.append(f"EQ1b: after the release revealHostile host/client {rh} (want present and EQUAL on both)")
    finally:
        # never leave the host in phase Handshake: release whatever is still held (recorded)
        rest = hold(client)
        if rest.get("armed") or rest.get("held"):
            rel = hold(client, on=False)
            wait_until(lambda: es(host).get("phase") == "Active", PHASE_WAIT_S)
            print(f"[w2p8b-sa] EQ1b cleanup: released the hold {rel}; host phase {es(host).get('phase')}", flush=True)
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


# ===================== S-B: the baton, quick unload, the fuse sites =====================


def stage_sb_w(host, client, ctx):
    """The spine after EQ1b: S-B's staging on C1 (battle_give, client first, F607; the client's briefing is still
    up, so its screen opens on the staged kit), then the client's close_briefing -> its pre-battle screen on C1.
    Records ctx['sb']; raises (a spine failure) when either step fails."""
    rec = {"ids": {}}
    ctx["sb"] = rec
    try:
        for t, extra in SB_GIVE_W:
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
    print(f"STAGE S-B {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if rec.get("error") or rec.get("diff"):
        raise AssertionError(f"spine: S-B's staging failed ({rec.get('error')}; buckets differ {rec.get('diff')})")
    if not got or not rec["entry"]["toC1"]["reached"]:
        raise AssertionError(f"spine: the client's pre-battle screen on C1 never came up ({rec['entry']})")


def sb_w_pre(host, client, ctx, row):
    fails = pre_screen_fails(host, client, row)
    s = ctx.get("sb") or {}
    if not s.get("ids") or s.get("error") or s.get("diff"):
        fails.append(f"{row}: S-B's staging did not complete ({s})")
    if not fails and inv_view(client).get("unitId") != C1:
        fails.append(f"{row}: the client's screen shows {inv_view(client).get('unitId')} (want C1 {C1})")
    if not fails and inv_view(client).get("selectedItem") != -1:
        fails.append(f"{row}: the client's cursor holds {inv_view(client).get('selectedItem')} (want empty)")
    return fails


def guard_counts(gc):
    return dict((es(gc).get("invGuard") or {}).get("counts") or {})


def eq10b_baton(host, client, ctx):
    fails = sb_w_pre(host, client, ctx, "EQ10b")
    ev = {}
    if fails:
        evidence("EQ10b", ev)
        finish([f.replace("EQ10b: ", "EQ10b: precondition absent - ") for f in fails])
    g0, ec0 = guard_counts(client), es(client)
    tu0 = tus(host, client, C1)
    item0 = first_of_type(client, GRENADE_T)
    ev["pick"] = {}
    item = pick_ground(client, item0, ev["pick"]) if item0 is not None else None
    want = {"owner": C1, "slot": BELT, "slotX": EQ10B_CELL[0], "slotY": EQ10B_CELL[1]}
    got = None
    if item is not None:
        ev["drop"] = click(client, slot=BELT, x=EQ10B_CELL[0], y=EQ10B_CELL[1])

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
    evidence("EQ10b", ev)
    if item0 is None:
        fails.append(f"EQ10b: precondition absent - no {GRENADE_T} on the client's pile ground")
    elif item is None:
        fails.append(f"EQ10b: the pile grenade was not picked ({ev['pick']})")
    elif not got:
        fails.append(f"EQ10b: the grenade {item} host={ev['itemHost']} client={ev['itemClient']} (want {want} on both; "
                     f"RED: refused by the traditional baton at the client's execution point - invGuard.counts.baton "
                     f"{g0.get('baton')} -> {guard_counts(client).get('baton')}, line "
                     f"{ev['refusal']['invLastWarning'][1]!r} (the baton text is {TEXT_NOT_YOUR_GO!r}))")
    if guard_counts(client).get("baton", 0) != g0.get("baton", 0):
        fails.append(f"EQ10b: the client's invGuard.counts.baton {g0.get('baton')} -> "
                     f"{guard_counts(client).get('baton')} (want unchanged: the baton does not gate pre-battle "
                     f"placements)")
    if ev["cursorAfter"] != -1:
        fails.append(f"EQ10b: the client's cursor holds {ev['cursorAfter']} (want empty)")
    fails += tail_fails(host, client, "EQ10b")
    finish(fails)


def eq11b_quick_unload(host, client, ctx):
    fails = sb_w_pre(host, client, ctx, "EQ11b")
    s = ctx.get("sb") or {}
    rifle, clip = (s.get("ids") or {}).get(RIFLE_T), s.get("rifleAmmo")
    ev = {"rifle": rifle, "clip": clip}
    if not fails:
        ih, ic = items_by_id(host), items_by_id(client)
        ev["before"] = {"host": weapon_view(ih, rifle), "client": weapon_view(ic, rifle)}
        for side in ("host", "client"):
            w = ev["before"][side] or {}
            if not (w.get("owner") == C1 and w.get("slot") == RIGHT_HAND and w.get("ammo") == [clip]):
                fails.append(f"EQ11b: the {side}'s rifle {rifle} {w} (want C1's, in {RIGHT_HAND}, loaded with {clip})")
    if fails:
        evidence("EQ11b", ev)
        finish([f.replace("EQ11b: ", "EQ11b: precondition absent - ") for f in fails])
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
    evidence("EQ11b", ev)
    if not got:
        fails.append(f"EQ11b: after the Shift-click rifle host={ev['after']['host']} client={ev['after']['client']}, "
                     f"clip {clip} host={ev['clipAfter']['host']} client={ev['clipAfter']['client']} (want the rifle in "
                     f"{RIGHT_HAND} unloaded and the clip on the ground at {PILE} on both within {LAND_WAIT_S} s)")
    if lw1 != lw0:
        fails.append(f"EQ11b: the client's invLocalWrites {lw0} -> {lw1} (want unchanged: RED - vanilla's quick-unload "
                     f"branch wrote on the client alone; buckets differ {ev['diff']})")
    if ev["cursor"] != -1:
        fails.append(f"EQ11b: the client's cursor holds {ev['cursor']} (want empty)")
    fails += tail_fails(host, client, "EQ11b")
    finish(fails)


def fuses(host, client, iid):
    return [(item_view_fuse(items_by_id(host), iid)), (item_view_fuse(items_by_id(client), iid))]


def item_view_fuse(its, iid):
    return (its.get(iid) or {}).get("fuse")


def right_click_c1(client, cell):
    return click(client, slot=BELT, x=cell[0], y=cell[1], button="right")


def eq13_prime_unprime(host, client, ctx):
    fails = sb_w_pre(host, client, ctx, "EQ13")
    g = ((ctx.get("sb") or {}).get("ids") or {}).get(GRENADE_T)
    ev = {"grenade": g}
    if not fails:
        ev["fuseBefore"] = fuses(host, client, g)
        ih = items_by_id(host)
        v = item_view(ih, g) or {}
        if not (v.get("owner") == C1 and v.get("slot") == BELT and (v.get("slotX"), v.get("slotY")) == GRENADE_CELL
                and ev["fuseBefore"] == [FUSE_NONE, FUSE_NONE]):
            fails.append(f"EQ13: the staged grenade {g} {v} fuse host/client {ev['fuseBefore']} (want C1's, "
                         f"{BELT} {GRENADE_CELL}, unprimed on both)")
    if fails:
        evidence("EQ13", ev)
        finish([f.replace("EQ13: ", "EQ13: precondition absent - ") for f in fails])
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
    evidence("EQ13", ev)
    if not g1:
        fails.append(f"EQ13: the right-click on {g} opened no PrimeGrenadeState on the client (top {top(client)!r})")
    elif ev.get("primeScreenClosedWithin") is None:
        fails.append(f"EQ13: key 3 left the client on {top(client)!r} (want its InventoryState back on top)")
    if not got3:
        fails.append(f"EQ13: after key 3 the fuse host/client {ev['primed']['fuse']} (want [{FUSE_KEYED}, {FUSE_KEYED}] "
                     f"within {ANSWER_WAIT_S} s; RED: the fuse written on the client alone)")
    if not got4:
        fails.append(f"EQ13: after the second right-click the fuse host/client {ev['unprimed']['fuse']} (want "
                     f"[{FUSE_NONE}, {FUSE_NONE}] within {ANSWER_WAIT_S} s)")
    fails += tail_fails(host, client, "EQ13")
    finish(fails)


def eq13b_default_fuse(host, client, ctx):
    fails = sb_w_pre(host, client, ctx, "EQ13b")
    p = ((ctx.get("sb") or {}).get("ids") or {}).get(PROX_T)
    ev = {"proximity": p}
    if not fails:
        ev["fuseBefore"] = fuses(host, client, p)
        v = item_view(items_by_id(host), p) or {}
        if not (v.get("owner") == C1 and v.get("slot") == BELT and (v.get("slotX"), v.get("slotY")) == PROX_CELL
                and ev["fuseBefore"] == [FUSE_NONE, FUSE_NONE]):
            fails.append(f"EQ13b: the staged proximity grenade {p} {v} fuse host/client {ev['fuseBefore']} (want C1's, "
                         f"{BELT} {PROX_CELL}, unprimed on both)")
    if fails:
        evidence("EQ13b", ev)
        finish([f.replace("EQ13b: ", "EQ13b: precondition absent - ") for f in fails])
    ev["rightClick"] = right_click_c1(client, PROX_CELL)
    got, dt = wait_until(lambda: fuses(host, client, p) == [FUSE_DEFAULT_INSTANT, FUSE_DEFAULT_INSTANT], ANSWER_WAIT_S,
                         0.1)
    ev.update({"within": dt if got else None, "fuse": fuses(host, client, p), "clientTop": top(client),
               "invGuardLast": (es(client).get("invGuard") or {}).get("last"),
               "invLocalWrites": es(client).get("invLocalWrites"), "turn": [turn(host), turn(client)]})
    evidence("EQ13b", ev)
    if not got:
        fails.append(f"EQ13b: after the right-click the fuse host/client {ev['fuse']} (want the default "
                     f"[{FUSE_DEFAULT_INSTANT}, {FUSE_DEFAULT_INSTANT}] within {ANSWER_WAIT_S} s; RED: written on the "
                     f"client alone)")
    if ev["clientTop"] != "InventoryState":
        fails.append(f"EQ13b: the client's top {ev['clientTop']!r} (want its InventoryState: an instant fuse opens no "
                     f"timer screen)")
    fails += tail_fails(host, client, "EQ13b")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine (a failure there fails the
# run, and the rows after it fail on their own preconditions).
STEPS = (("EQ1b", eq1b_host_equips_in_handshake),
         (None, stage_sb_w),
         ("EQ10b", eq10b_baton),
         ("EQ11b", eq11b_quick_unload),
         ("EQ13", eq13_prime_unprime),
         ("EQ13b", eq13b_default_fuse))
ROWS = [n for n, _ in STEPS if n]


def boot(host, client):
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
    print(f"[w2p8b-sa] boot W ok: MAP_FP={MAP_FP!r} seated={seated_uids} H={h_ids} arm={ctx['arm']} "
          f"host stack={stack(host)} client stack={stack(client)}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49922, make_user_dir("w2p8b_prebattle_equip_w_host"))
    client = GameClient("client", 49923, make_user_dir("w2p8b_prebattle_equip_w_client"))
    results = {}
    spine_ok = True
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in STEPS:
            try:
                fn(host, client, ctx)
                if name:
                    results[name] = True
                    print(f"PASS {name}", flush=True)
            except Exception as e:
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                if name:
                    results[name] = False
                    print(f"FAIL {name}: {kind}{e}", flush=True)
                else:
                    spine_ok = False
                    print(f"SPINE FAIL {fn.__name__}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p8b-sa] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n in ROWS if results.get(n)]
    failed = [n for n in ROWS if not results.get(n)]
    print(f"\ntest_w2_prebattle_equip_rejoin: {len(passed)}/{len(ROWS)} passed "
          f"(pass={passed} fail={failed}{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (not failed and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
