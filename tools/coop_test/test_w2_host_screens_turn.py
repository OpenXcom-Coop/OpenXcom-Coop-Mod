"""W2-P8 S-C2 - test_w2_host_screens_turn.py: parallel mode, the host's screens across a
side change and a battle end: the partner's END TURN flips the side under the host's
screen, the host's inventory closes itself when the side changes, the enemy AI waits
behind the host's Esc menu, a hot-grenade end turn runs under the host's screen, and a
partner's knockout of the last alien ends the battle while the host's screen is open.
Spec docs rewrite/prompts/w2p8_inventory.md: owner D166 = B, D187-D191; J1 (F2330);
AMENDMENT P8-4 section 4.2 (C2-6: a grenade-free END TURN flips at once today, so HS9
is declared green at red and HS8b exercises the `endturn` drive; C2-9; the rows and
the named red) with the draft rewrite/prompts/w2p8_sc2_sr_sd_draft.md section 1.8;
AMENDMENT P8-4b (TASK 0 pins, rulings 4 and 5).

ONE boot = test_w2_inventory.boot (as test_w2_host_screens.py). Rows in this order,
every row ONE run; each of HS8, HS9, HS8b ends with a full side cycle (turn + 1 on
both, test_rw_turn_baton.drive_full_cycle, P8-3b ruling 2); HS10 ends the battle, so
it is LAST:
  HS8   (J1 / F2330, the host twin of V13) the host presses END TURN (1/2), opens
        H's inventory and picks H's grenade (belt (1,0)); the client presses END
        TURN: the side flips with NextTurnState over the host's inventory; the
        test closes it (close_nextturn). RED (F2894, ruling 5): the host's
        InventoryState is the top again during the alien side, re-initialised on
        an alien with H's grenade on the cursor, hostScreens.closes.byReason.side
        +0, the side not progressing. GREEN: at the first read after the
        close_nextturn (no host input in between) hostScreens.closes.byReason.side
        +1 and byScreen.inventory +1; the host's INVENTORY key, armed in-game
        before the close (TestServer battle_arm_key, ruling SC2-G1 / F2924: the
        alien side lasts ~80 ms, two harness round trips exceed it), fires on the
        first frame of the alien side with the battlescape on top and opens
        nothing (no InventoryState on the host between the fire and the next
        turn's NextTurnState); the grenade STR_BELT (1,0) on both; turn + 1 on
        both; EQUAL.
  HS9   (D188; declared GREEN at red, C2-6) the host presses END TURN, opens its
        Esc menu (PauseState); the client presses END TURN; the test closes the
        NextTurnState over the menu; 5 s of samples with PauseState on top: the
        host's side stays the alien side, host contextsOpened.ai +0,
        hostCovered.steps +0; after the menu closes the alien side runs and the
        next turn starts on both; EQUAL.
  HS8b  (M1 `endturn`, C2-6, T0-S6b) a primed grenade (fuse 0) dropped on an empty
        tile on both; the host presses END TURN and opens H's inventory; the
        client presses END TURN: host contextsOpened.endturn +1 (the precondition:
        a hot-grenade end turn opens the `endturn` context). RED (ruling 4): the
        end turn frozen under the host's inventory: side 0 after SAMPLE_S, host top
        InventoryState, hostCovered.steps +0. GREEN: the end turn runs under the
        screen - hostCovered.byOrigin.endturn > 0 and NextTurnState over the
        host's inventory with the side flipped; after close_nextturn
        hostScreens.closes.byReason.side +1; turn + 1 on both; EQUAL. The grenade
        explodes under the host's screen in both builds (F2895): never asserted.
  HS10  (F2641 / F2642, T0-S7) every alien but the lowest id killed
        (kill_unit_real, context-less); battleAutoEnd on both; the last alien on
        (24,23,0) health 5, C on (24,24,0) facing it with a stun rod; the host
        opens H's inventory and picks the grenade; client stun-rod melee (seed 1).
        RED: the knockout frozen; no battle end within END_WINDOW_S while the
        host's screen is open. GREEN: with the host's inventory never closed by
        the test, the battle ends (the test closes the host's NextTurnState when it
        is on top, W2-P7's recipe): host battleEnd.emitted 1 and evsAfter 0, client
        battleEnd.applied 1, both machines on their DebriefingState (the client's
        display-only), no InventoryState left on either machine, no crash file,
        desyncAtTeardown false on both.

Common asserts (HS8, HS9, HS8b; after wait_host_idle): hash_now full EQUAL; desyncSeen
false on both; client coopClientBStatePushes unchanged and host 0; client
invLocalWrites 0 and invGuard unchanged; no screen left open; no new crash file; host
hostCovered.byOrigin moves only on intent / endturn (STOP-IF 20). A red row's cleanup
(the host's cursor item back through inventory_cursor_clear, its screen closed) lets
the frozen side change finish; it is recorded and is a no-op on a green run.

Constants: the P8-4b pin table (T0-S6 / T0-S6b / T0-S7 rows; docs
rewrite/w2p8-task0/sc2/, t0_sc2.py --koseed 1), each with its source line below. Item
ids come from each row's staging record (C7). Lever pairs go to the CLIENT first
(F607); player-unit teleports go HOST first, checked (P8-4b ruling 3,
place_host_first); HS10's ALIEN teleport stays client-first (a host-first alien
teleport makes the host's next reveal ev carry state the client lacks and latches a
client desync, F607 - reproduced at S-C2.1's dispatch tip) after a check of the host
leg's refusal causes (the alien standing and not out on the host). One "EVIDENCE <id>:"
line per row before its checks; every row runs after an earlier failure; exit 0 only
when every row passes, 2 otherwise. WV-D99 / WV-D100: one run is the result. WV-D95:
run in the foreground to completion.

Run:  python tools/coop_test/test_w2_host_screens_turn.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
from test_w2_inventory import (C_ID, H_ID, BELT, GRENADE, STAGE_H, OPTS, TU_MAX, stack, units, inv_view,
                               evidence, finish, wait_until, new_contexts, read_inventory_key)
from test_w2_inventory_held import (STATUS_UNCONSCIOUS, KEY_SETTLE_S, CLOSE_KEY, place_host_first, read_key,
                                    restage_h, settle, crash_exception_lines, log_mark, ui_lines, dnum,
                                    item_both, dismiss_nts_all)
import test_w2_host_screens as hs
from test_w2_host_screens import (snap_hs, top, crash_census, hscr, hclose, hcov, hcov_origin, ctx_count, press, give_hands,
                                  set_state_both, open_host_inventory, host_pick, send_order, release,
                                  hs_common_fails, boot, KO_C_TILE, KO_C_DIR, KO_T_TILE, KO_T_DIR, KO_HEALTH,
                                  SEED_KO, STUN_ROD, jt)
from test_w2_delta_core import short, both
from test_w2_delta_items import items_by_id
import test_w2_client_shoot as cs
from test_rw_turn_baton import drive_full_cycle

# ----- P8-4b T0-S6/S6b row: "parallel; host END TURN first | grenade-free partner END TURN flips at once under both
# screens (F2893); HS8 at red the host's inventory re-inits on an alien with H's grenade on the cursor (F2894);
# HS8b: the hot grenade explodes 4 ms into the endturn context under the host's screen - only the context close and
# the flip wait (F2895)" (t0_sc2.py t0s6_hs8 :727, t0s6_hs9 :773, t0s6b :806) -----
HOT_TILE = (34, 24, 0)            # t0_sc2.py :262: an empty road tile (P8-3b T0-4's shot target)
TEXT_END_TURN_1_OF_2 = "END TURN 1/2"   # the host's END TURN tally after its own press (T0-S6 arm record)
ARM_WAIT_S = 5.0
FLIP_WAIT_S = 30.0
SAMPLE_S = 5.0                    # the draft section 1.8 HS9: "sample 5 s"; T0-S6b's window (5 s of samples)
SIDE_SAMPLE_S = 3.0               # HS8's red record: the alien side does not progress under the host's screen
ARM_TIMEOUT_MS = 10000            # HS8: battle_arm_key's deadline (ruling SC2-G1)
ALIEN_END_WAIT_S = 10.0           # HS8: the armed key's record is read once the alien side is over (its next
                                  # NextTurnState seen by the lever), within this
CYCLE_S = 90                      # t0_sc2.py cycle_to_next: drive_full_cycle(timeout=90)
SIDE_ALIEN = 1
# ----- P8-4b T0-S7 row: "12 aliens killed by id; the last on (24,23,0) health 5; C (24,24,0) dir 0 stun rod; seed 1
# | the end turn runs inside the partner's intent context (closed at endTurn entry); battle ends after the host's
# NTS closes (P7 recipe) (F2896)" (t0_sc2.py t0s7 :845) -----
KILL_WAIT_S = 30.0
END_WINDOW_S = 10.0               # T0-S7: melee send -> both DebriefingState 1.615 s (x 6)
END_AFTER_S = 30.0                # a red row's released knockout -> both DebriefingState


# ===================== helpers =====================


def bsv(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("turn", "side", "selectedId", "isBusy", "pendingStates", "coopEndTurnText")}


def arm_host(host):
    """The host's own END TURN press first (T0-S6): its tally shows 1/2."""
    r = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    got, dt = wait_until(lambda: battle_state(host).get("coopEndTurnText") == TEXT_END_TURN_1_OF_2, ARM_WAIT_S, 0.05)
    return {"resp": {k: r.get(k) for k in ("ok", "error")}, "armed": bool(got), "waited": dt, "host": bsv(host)}


def client_end_turn(client):
    r = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    return {k: r.get(k) for k in ("ok", "error")}


def flip_watch(host, t0, timeout=FLIP_WAIT_S):
    """t0_sc2.py flip_watch :676-:686: the first host sample with a NextTurnState on the stack or the side
    changed."""
    side0 = battle_state(host).get("side")
    while time.time() - t0 < timeout:
        stk = stack(host)
        side = battle_state(host).get("side")
        if "NextTurnState" in stk or side != side0:
            v = inv_view(host)
            return {"t": round(time.time() - t0, 3), "stack": stk, "side": side,
                    "view": {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem")}}
        time.sleep(0.03)
    return None


def cycle(host, client, turn0):
    """turn + 1 on both (P8-3b ruling 2: test_rw_turn_baton.drive_full_cycle), every NextTurnState closed through
    its real close(), then the host idle (t0_sc2.py cycle_to_next :709-:724)."""
    rec = {}
    try:
        drive_full_cycle(host, client, turn0, timeout=CYCLE_S)
        rec["returned"] = True
    except Exception as e:
        rec["err"] = short(e, 600)
    rec["hostNts"] = dismiss_nts_all(host)
    rec["clientNts"] = dismiss_nts_all(client)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec["idleErr"] = short(e)
    rec["after"] = {"host": bsv(host), "client": bsv(client)}
    return rec


def cycle_fails(cyc, turn0, what):
    fails = []
    if "err" in cyc:
        fails.append(f"FIXTURE-STOP (P8-3b ruling 2): {what}: drive_full_cycle failed: {cyc['err']} (host "
                     f"{cyc.get('hostNts')}, client {cyc.get('clientNts')})")
    for n in ("host", "client"):
        a = cyc["after"][n]
        if (a.get("side"), a.get("turn")) != (0, turn0 + 1):
            fails.append(f"{what}: the {n} after the cycle side {a.get('side')} turn {a.get('turn')} (want side 0, turn "
                         f"{turn0 + 1})")
    if "idleErr" in cyc:
        fails.append(f"{what}: {cyc['idleErr']}")
    return fails


# ===================== rows =====================


def hs8_side_change(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"H": restage_h(host, client, STAGE_H, "K0", placer=place_host_first)}
    staged = settle(host, client)
    g = st["H"]["ids"]["grenade"]
    turn0 = battle_state(host).get("turn")
    before = snap_hs(host, client)
    hmark = log_mark(host)
    ev = {"arm": arm_host(host)}
    opened = open_host_inventory(host, H_ID, ev)
    picked = host_pick(host, ev, "pick", BELT, 1, 0, g) if opened else False
    flip, after_nts, key_row, red = None, {}, None, {}
    if ev["arm"]["armed"] and opened and picked:
        t0 = time.time()
        ev["clientEndTurn"] = client_end_turn(client)
        flip = flip_watch(host, t0)
        if flip and top(host) == "NextTurnState":
            # ruling SC2-G1 (F2924): the host's INVENTORY key is armed in-game BEFORE the close, for the first frame
            # of the alien side with the battlescape on top (the alien side is over before a harness press lands)
            k = read_inventory_key(host.user_dir)
            ra = host.cmd({"cmd": "battle_arm_key", "key": k, "side": SIDE_ALIEN, "timeoutMs": ARM_TIMEOUT_MS})
            arm = {kk: ra.get(kk) for kk in ("ok", "armed", "frame", "error")}
            rn = host.cmd({"cmd": "close_nextturn"})
            eh = event_state(host)          # the first read after the close: no host input in between
            after_nts = {"close": {k: rn.get(k) for k in ("ok", "handled", "error")},
                         "hostScreens": eh.get("hostScreens"), "stack": stack(host), "side": bsv(host)["side"]}
            if (dnum(hclose(before["host"], "byReason", "side"), hclose(eh, "byReason", "side")) or 0) > 0:
                # GREEN path: the armed INVENTORY key during the alien side (the host twin of IH5's OR3 a); its
                # record is read once the lever saw the next turn's NextTurnState (or the arm expired)
                def side_over():
                    ak = event_state(host).get("armKey") or {}
                    return ak if (ak.get("nextTurnFrame", -1) >= 0 or ak.get("expired")) else None
                _, waited = wait_until(side_over, ALIEN_END_WAIT_S, 0.05)
                v = inv_view(host)
                key_row = {"key": k, "arm": arm, "armKey": event_state(host).get("armKey"), "waited": waited,
                           "stack": stack(host), "host": bsv(host),
                           "view": {kk: v.get(kk) for kk in ("open", "top", "unitId", "selectedItem")}}
            else:
                # the RED record (F2894): the host's screen back on top during the alien side
                v = inv_view(host)
                red["view"] = {kk: v.get(kk) for kk in ("open", "top", "unitId", "selectedItem")}
                samples = []
                t1 = time.time()
                while time.time() - t1 < SIDE_SAMPLE_S:
                    samples.append({"t": round(time.time() - t1, 2), "top": top(host), "host": bsv(host)})
                    time.sleep(0.5)
                red["samples"] = samples
    rel = release(host, notes, "HS8")
    cyc = cycle(host, client, turn0)
    end = {"grenade": item_both(host, client, g)}
    evidence("HS8", {"staging": st, "stagedDiff": staged, "ui": ev, "flip": flip, "afterNts": after_nts,
                     "key": key_row, "red": red, "release": rel, "cycle": cyc, "end": end,
                     "hostUi": ui_lines(host, hmark)[-16:], "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"HS8: buckets differ after the staging: {staged}")
    if not ev["arm"]["armed"]:
        fails.append(f"precondition (T0-S6): the host's END TURN did not arm ({ev['arm']})")
    elif not opened or not picked:
        fails.append(f"precondition (HS8): the host's inventory on H / the grenade pick ({ev})")
    elif flip is None or "InventoryState" not in (flip.get("stack") or []) or flip["stack"][-1] != "NextTurnState":
        fails.append(f"precondition (T0-S6): the side flip with NextTurnState over the host's inventory ({flip})")
    else:
        # the RED cell (S-C2.1, F2894): the screen re-inits on an alien, no side close; GREEN (J1): closed at the
        # first pump after the NextTurnState, before any host input
        ds = dnum(hclose(before["host"], "byReason", "side"), hclose(after_nts, "byReason", "side"))
        di = dnum(hclose(before["host"], "byScreen", "inventory"), hclose(after_nts, "byScreen", "inventory"))
        if (ds, di) != (1, 1) or "InventoryState" in (after_nts.get("stack") or []):
            fails.append(f"HS8: after close_nextturn host hostScreens.closes byReason.side +{ds}, byScreen.inventory "
                         f"+{di}, stack {after_nts.get('stack')} (want +1 / +1, no InventoryState; red record {red})")
        elif key_row is None:
            fails.append("HS8: the host's INVENTORY key was not armed for the alien side")
        else:
            ak = key_row.get("armKey") or {}
            if not (key_row["arm"].get("ok") and key_row["arm"].get("armed")):
                fails.append(f"HS8: battle_arm_key did not arm the host's INVENTORY key ({key_row['arm']})")
            elif not ak.get("fired") or ak.get("sideAtFire") != SIDE_ALIEN or ak.get("topBefore") != "BattlescapeState":
                fails.append(f"HS8: the armed INVENTORY key did not fire on the alien side with the battlescape on "
                             f"top (want fired, sideAtFire {SIDE_ALIEN}, topBefore BattlescapeState; {ak})")
            elif ak.get("nextTurnFrame", -1) < 0:
                fails.append(f"HS8: the lever saw no next-turn NextTurnState within {ALIEN_END_WAIT_S} s of the "
                             f"close ({ak})")
            elif ak.get("inventoryPushesSinceFire") != 0:
                fails.append(f"HS8: the host's INVENTORY key during the alien side opened a screen: "
                             f"inventoryPushesSinceFire {ak.get('inventoryPushesSinceFire')} before the next "
                             f"NextTurnState (want 0; {ak})")
    want_belt = {"owner": H_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
    for n in ("host", "client"):
        if {k: (end["grenade"][n] or {}).get(k) for k in want_belt} != want_belt:
            fails.append(f"HS8: the {n}'s grenade {end['grenade'][n]} (want {want_belt})")
    fails += cycle_fails(cyc, turn0, "HS8")
    fails += hs_common_fails(host, client, before, crash0, "HS8")
    finish(fails)


def hs9_pause_holds_ai(host, client, ctx):
    notes = []
    crash0 = crash_census()
    turn0 = battle_state(host).get("turn")
    before = snap_hs(host, client)
    hmark = log_mark(host)
    ev = {"arm": arm_host(host)}
    k_opt = read_key(host.user_dir, "keyBattleOptions")
    press(host, k_opt)
    opened, ev["pauseWaited"] = wait_until(lambda: top(host) == "PauseState", 3.0, 0.02)
    ev["pauseStack"] = stack(host)
    flip, samples, closed = None, [], {}
    if ev["arm"]["armed"] and opened:
        t0 = time.time()
        ev["clientEndTurn"] = client_end_turn(client)
        flip = flip_watch(host, t0)
        if flip and top(host) == "NextTurnState":
            rn = host.cmd({"cmd": "close_nextturn"})
            ev["closeNts"] = {k: rn.get(k) for k in ("ok", "handled", "error")}
        s0 = snap_hs(host, client)
        t1 = time.time()
        while time.time() - t1 < SAMPLE_S:
            eh = event_state(host)
            samples.append({"t": round(time.time() - t1, 2), "top": top(host), "host": bsv(host),
                            "ai": ctx_count(eh, "ai") - ctx_count(s0["host"], "ai"),
                            "steps": dnum(hcov(s0["host"]).get("steps"), hcov(eh).get("steps"))})
            time.sleep(0.5)
        if top(host) == "PauseState":
            time.sleep(KEY_SETTLE_S)
            press(host, read_key(host.user_dir, CLOSE_KEY))
            got, _ = wait_until(lambda: top(host) != "PauseState", 3.0, 0.02)
            closed = {"ok": bool(got), "stack": stack(host)}
    rel = release(host, notes, "HS9")
    cyc = cycle(host, client, turn0)
    evidence("HS9", {"ui": ev, "flip": flip, "samples": samples, "pauseClosed": closed, "release": rel, "cycle": cyc,
                     "hostUi": ui_lines(host, hmark)[-12:], "notes": notes})
    fails = list(notes)
    if not ev["arm"]["armed"] or not opened:
        fails.append(f"precondition (HS9): the host's END TURN / PauseState ({ev})")
    elif flip is None or "PauseState" not in (flip.get("stack") or []) or flip["stack"][-1] != "NextTurnState":
        fails.append(f"precondition (T0-S6): the side flip with NextTurnState over the host's PauseState ({flip})")
    else:
        bad = [s for s in samples if s["top"] != "PauseState" or s["host"].get("side") != SIDE_ALIEN
               or s["ai"] != 0 or s["steps"] != 0]
        if not samples or bad:
            fails.append(f"HS9: with PauseState on top the host's alien side must hold (side {SIDE_ALIEN}, "
                         f"contextsOpened.ai +0, hostCovered.steps +0); offending samples {bad[:3]}")
        if not closed.get("ok"):
            fails.append(f"HS9: the host's PauseState did not close ({closed})")
    fails += cycle_fails(cyc, turn0, "HS9")
    fails += hs_common_fails(host, client, before, crash0, "HS9")
    finish(fails)


def hs8b_hot_grenade(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"hot": both(host, client, {"cmd": "battle_drop", "x": HOT_TILE[0], "y": HOT_TILE[1], "z": HOT_TILE[2],
                                     "item": GRENADE, "prime": True, "fuse": 0}, ("ids",))["ids"]}
    st["H"] = place_host_first(host, client, H_ID, STAGE_H, 2)
    staged = settle(host, client)
    gid = st["hot"][0]
    st["hotItem"] = item_both(host, client, gid)
    turn0 = battle_state(host).get("turn")
    before = snap_hs(host, client)
    hmark = log_mark(host)
    ev = {"arm": arm_host(host)}
    opened = open_host_inventory(host, H_ID, ev)
    window, after_nts = {}, {}
    if ev["arm"]["armed"] and opened:
        t0 = time.time()
        ev["clientEndTurn"] = client_end_turn(client)
        samples, flipped = [], None
        while time.time() - t0 < SAMPLE_S:
            eh, stk = event_state(host), stack(host)
            s = {"t": round(time.time() - t0, 2), "endturn": ctx_count(eh, "endturn") - ctx_count(before["host"],
                                                                                                "endturn"),
                 "top": stk[-1] if stk else None, "stack": stk, "host": bsv(host),
                 "coveredEndturn": dnum(hcov_origin(before["host"], "endturn"), hcov_origin(eh, "endturn")),
                 "steps": dnum(hcov(before["host"]).get("steps"), hcov(eh).get("steps"))}
            samples.append(s)
            if "NextTurnState" in stk:
                flipped = s
                break
            time.sleep(0.25)
        window = {"samples": samples, "flipped": flipped}
        if flipped and top(host) == "NextTurnState":
            rn = host.cmd({"cmd": "close_nextturn"})
            eh = event_state(host)          # the first read after the close
            after_nts = {"close": {k: rn.get(k) for k in ("ok", "handled", "error")},
                         "hostScreens": eh.get("hostScreens"), "stack": stack(host)}
    rel = release(host, notes, "HS8b")
    if rel:
        window["afterRelease"] = flip_watch(host, time.time())
    cyc = cycle(host, client, turn0)
    cc = [c for c in new_contexts(before["host"]["closedContexts"], event_state(host).get("closedContexts"))
          if c.get("origin") == "endturn"]
    end = {"hotGrenade": {"host": gid in items_by_id(host), "client": gid in items_by_id(client)},
           "endturnContexts": cc}
    evidence("HS8b", {"staging": st, "stagedDiff": staged, "ui": ev, "window": window, "afterNts": after_nts,
                      "release": rel, "cycle": cyc, "end": end, "hostUi": ui_lines(host, hmark)[-12:],
                      "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"HS8b: buckets differ after the staging: {staged}")
    samples = window.get("samples") or []
    if not ev["arm"]["armed"] or not opened:
        fails.append(f"precondition (HS8b): the host's END TURN / inventory ({ev})")
    elif not any(s["endturn"] >= 1 for s in samples):
        fails.append(f"precondition (T0-S6b): host contextsOpened.endturn +0 after the client's END TURN (want +1: "
                     f"the hot grenade opens the endturn context, F2862); samples {samples[:2]}")
    else:
        f = window.get("flipped")
        if f is None:
            last = samples[-1] if samples else {}
            # the RED cell (ruling 4): frozen under the host's inventory
            fails.append(f"HS8b: the end turn did not run under the host's inventory within {SAMPLE_S} s (last "
                         f"sample: side {(last.get('host') or {}).get('side')}, top {last.get('top')}, "
                         f"hostCovered.steps +{last.get('steps')}, byOrigin.endturn +{last.get('coveredEndturn')})")
        else:
            if f["stack"][-2:] != ["InventoryState", "NextTurnState"]:
                fails.append(f"HS8b: the host's stack at the flip {f['stack']} (want NextTurnState over "
                             f"InventoryState)")
            if not isinstance(f.get("coveredEndturn"), int) or f["coveredEndturn"] <= 0:
                fails.append(f"HS8b: host hostCovered.byOrigin.endturn +{f.get('coveredEndturn')} at the flip (want > 0)")
            ds = dnum(hclose(before["host"], "byReason", "side"), hclose(after_nts, "byReason", "side"))
            if ds != 1 or "InventoryState" in (after_nts.get("stack") or []):
                fails.append(f"HS8b: after close_nextturn host hostScreens.closes.byReason.side +{ds}, stack "
                             f"{after_nts.get('stack')} (want +1, no InventoryState)")
    fails += cycle_fails(cyc, turn0, "HS8b")
    fails += hs_common_fails(host, client, before, crash0, "HS8b")
    finish(fails)


def kill_all_but_one(host, client):
    hb = battle_state(host)
    aliens = sorted(u["id"] for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut"))
    rec = {"aliens": aliens, "last": aliens[0] if aliens else None, "kills": []}
    for a in aliens[1:]:
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": a})
        done, dt = wait_until(lambda: not battle_state(host).get("isBusy") and battle_state(host).get(
            "pendingStates") == 0 and top(host) == "BattlescapeState", KILL_WAIT_S, 0.1)
        rec["kills"].append({"id": a, "killed": r.get("killed"), "error": r.get("error"), "waited": dt,
                             "top": top(host)})
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec["idleErr"] = short(e)
    hb = battle_state(host)
    rec["liveHostile"] = sorted(u["id"] for u in hb["units"] if u.get("faction") == 1 and not u.get("isOut"))
    return rec


def place_alien(host, client, uid, tile, d):
    """HS10's alien onto `tile`: the host leg's refusal causes checked first (P8-4b ruling 3's intent: the alien
    standing and not out on the host, the tile's own check left to the lever), then test_w2_client_shoot.place
    (client first, F607: a host-first ALIEN teleport latches a client desync, reproduced at the dispatch tip)."""
    uh = units(host).get(uid) or {}
    assert uh.get("status") == 0 and not uh.get("isOut"), f"staging: alien {uid} on the host {uh} (want standing)"
    return cs.place(host, client, uid, tile, d)


def hs10_battle_end(host, client, ctx):
    notes = []
    crash0 = crash_census()
    kills = kill_all_but_one(host, client)
    last = kills["last"]
    st = {"H": restage_h(host, client, STAGE_H, "K0", placer=place_host_first)}
    st["rod"] = give_hands(host, client, C_ID, STUN_ROD)
    st["C"] = place_host_first(host, client, C_ID, KO_C_TILE, KO_C_DIR)
    st["A"] = place_alien(host, client, last, KO_T_TILE, KO_T_DIR) if last is not None else None
    st["autoEnd"] = {n: gc.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True}).get("value")
                     for n, gc in (("client", client), ("host", host))}
    if last is not None:
        st["Aset"] = set_state_both(host, client, last, health=KO_HEALTH, stun=0, fatalWounds=[0] * 6)
    st["cTu"] = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    g = st["H"]["ids"]["grenade"]
    before = snap_hs(host, client)
    be0 = {"host": event_state(host).get("battleEnd"), "client": event_state(client).get("battleEnd")}
    hmark, cmark = log_mark(host), log_mark(client)
    ev = {}
    opened = open_host_inventory(host, H_ID, ev)
    picked = host_pick(host, ev, "pick", BELT, 1, 0, g) if opened else False
    order, admitted, tops, ended, red = {}, False, [], False, {}

    def run_to_end(window, record):
        lastpair = None
        t0 = time.time()
        while time.time() - t0 < window:
            try:
                pair = (top(host), top(client))
            except Exception as e:
                record.append({"t": round(time.time() - t0, 2), "err": short(e)})
                return False
            if pair != lastpair:
                record.append({"t": round(time.time() - t0, 2), "host": stack(host), "client": stack(client)})
                lastpair = pair
            if pair[0] == "NextTurnState":
                rn = host.cmd({"cmd": "close_nextturn"})
                record.append({"t": round(time.time() - t0, 2), "closeNts": rn.get("handled") or rn.get("error")})
            if pair == ("DebriefingState", "DebriefingState"):
                return True
            time.sleep(0.05)
        return False
    if last is not None and opened and picked and last == (kills["liveHostile"] or [None])[0]:
        host.ok({"cmd": "set_seed", "seed": SEED_KO})
        order, admitted = send_order(host, client, {"cmd": "battle_intent", "kind": "melee", "actor": C_ID,
                                                    "plan": {"weapon": st["rod"], "target": jt(KO_T_TILE),
                                                             "terrainPart": 0, "targetUnit": last,
                                                             "targetPos": jt(KO_T_TILE)}}, before)
        if admitted:
            ended = run_to_end(END_WINDOW_S, tops)
            if not ended:
                # the RED record, then the cleanup (the cursor back, the screen closed, the knockout released)
                red = {"hostStack": stack(host), "clientStack": stack(client),
                       "alien": {n: (units(gc).get(last) or {}).get("status") for n, gc in (("host", host),
                                                                                           ("client", client))},
                       "battleEnd": event_state(host).get("battleEnd", {}).get("emitted")}
                red["release"] = release(host, notes, "HS10")
                red["tops"] = []
                red["ended"] = run_to_end(END_AFTER_S, red["tops"])
    time.sleep(1.0)
    final = {"hostStack": stack(host), "clientStack": stack(client),
             "hostBattleEnd": event_state(host).get("battleEnd"), "clientBattleEnd": event_state(client).get("battleEnd")}
    for n, gc in (("host", host), ("client", client)):
        d = gc.cmd({"cmd": "debrief_state"})
        final[n + "Debrief"] = {k: d.get(k) for k in ("ok", "shown", "onTop", "displayOnly", "title")}
    nc = sorted(crash_census() - crash0)
    evidence("HS10", {"kills": kills, "staging": st, "stagedDiff": staged, "ui": ev,
                      "order": {k: v for k, v in order.items() if k != "t0"}, "tops": tops, "ended": ended, "red": red,
                      "final": final, "battleEndBefore": be0, "newCrashFiles": nc,
                      "hostUi": ui_lines(host, hmark)[-16:], "clientUi": ui_lines(client, cmark)[-12:],
                      "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"HS10: buckets differ after the staging: {staged}")
    if last is None or kills["liveHostile"] != [last] or kills.get("idleErr"):
        fails.append(f"precondition (T0-S7): every alien but {last} killed (live hostile {kills['liveHostile']}, "
                     f"{kills.get('idleErr')})")
    elif not opened or not picked:
        fails.append(f"precondition (HS10): the host's inventory on H / the grenade pick ({ev})")
    elif not admitted:
        fails.append(f"precondition (HS10): the client's melee on the last alien was not admitted ({order})")
    elif not ended:
        # the RED cell (S-C2.1): the knockout frozen, no battle end while the host's screen is open
        fails.append(f"HS10: the battle did not end within {END_WINDOW_S} s with the host's inventory open (the test "
                     f"closed only NextTurnStates; red record {red.get('hostStack')}, alien status "
                     f"{red.get('alien')})")
    else:
        hbe, cbe = final["hostBattleEnd"] or {}, final["clientBattleEnd"] or {}
        if hbe.get("emitted") != 1 or hbe.get("evsAfter") != 0:
            fails.append(f"HS10: host battleEnd emitted {hbe.get('emitted')} evsAfter {hbe.get('evsAfter')} (want 1 / 0)")
        if cbe.get("applied") != 1:
            fails.append(f"HS10: client battleEnd.applied {cbe.get('applied')} (want 1)")
        if hbe.get("desyncAtTeardown") or cbe.get("desyncAtTeardown"):
            fails.append(f"HS10: desyncAtTeardown host={hbe.get('desyncAtTeardown')} client="
                         f"{cbe.get('desyncAtTeardown')} (want false on both)")
        hd, cd = final["hostDebrief"], final["clientDebrief"]
        if not (hd.get("shown") and hd.get("onTop")) or not (cd.get("shown") and cd.get("onTop") and cd.get(
                "displayOnly")):
            fails.append(f"HS10: debriefs host={hd} client={cd} (want both shown on top, the client's display-only)")
    for n in ("hostStack", "clientStack"):
        if "InventoryState" in (final[n] or []):
            fails.append(f"HS10: an InventoryState is left on the {n[:-5]} ({final[n]})")
    if nc:
        fails.append(f"HS10: new crash file(s) {nc}: {crash_exception_lines(nc)}")
    finish(fails)


SCENARIOS = (("HS8", hs8_side_change), ("HS9", hs9_pause_holds_ai), ("HS8b", hs8b_hot_grenade),
             ("HS10", hs10_battle_end))


def main():
    t0 = time.time()
    host = GameClient("host", 49960, make_user_dir("w2p8_hsturn_host", options=OPTS))
    client = GameClient("client", 49961, make_user_dir("w2p8_hsturn_client", options=OPTS))
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
                print(f"[w2p8-sc2] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_host_screens_turn: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
