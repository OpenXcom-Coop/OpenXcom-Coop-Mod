"""test_host_screens_turn.py: parallel mode, the host's screens across a side change and a battle end: the partner's
END TURN flips the side under the host's screen, the host's inventory closes itself when the side changes, the enemy
AI waits behind the host's Esc menu, a hot-grenade end turn runs under the host's screen, and a partner's knockout of
the last alien ends the battle while the host's screen is open.

ONE boot = test_inventory.boot (as test_host_screens.py). Rows in this order, every row ONE run; each of
side_change_closes_inventory, pause_holds_alien_side and hot_grenade_end_turn ends with a full side cycle (turn + 1 on
both, test_turn_baton.drive_full_cycle); knockout_ends_battle ends the battle, so it is LAST:
  side_change_closes_inventory: the host presses END TURN (1/2), opens H's inventory and picks H's grenade (belt
      (1,0)); the client presses END TURN: the side flips with NextTurnState over the host's inventory; the test
      closes it (close_nextturn). Passes when, at the first read after the close_nextturn (no host input in between),
      hostScreens.closes.byReason.side +1 and byScreen.inventory +1; the host's INVENTORY key, armed in-game before
      the close (TestServer battle_arm_key: the alien side lasts ~80 ms, two harness round trips exceed it), fires on
      the first frame of the alien side with the battlescape on top and opens nothing (no InventoryState on the host
      between the fire and the next turn's NextTurnState); the grenade STR_BELT (1,0) on both; turn + 1 on both;
      EQUAL. When broken the host's InventoryState is the top again during the alien side, re-initialised on an alien
      with H's grenade on the cursor, hostScreens.closes.byReason.side +0, the side not progressing.
  pause_holds_alien_side: the host presses END TURN, opens its Esc menu (PauseState); the client presses END TURN; the
      test closes the NextTurnState over the menu; 5 s of samples with PauseState on top: the host's side stays the
      alien side, host contextsOpened.ai +0, hostCovered.steps +0; after the menu closes the alien side runs and the
      next turn starts on both; EQUAL. This row also passes without the fix: a grenade-free END TURN flips at once, so
      hot_grenade_end_turn is the row that exercises the `endturn` drive.
  hot_grenade_end_turn: a primed grenade (fuse 0) dropped on an empty tile on both; the host presses END TURN and
      opens H's inventory; the client presses END TURN: host contextsOpened.endturn +1 (the precondition: a
      hot-grenade end turn opens the `endturn` context). Passes when the end turn runs under the screen:
      hostCovered.byOrigin.endturn > 0 and NextTurnState over the host's inventory with the side flipped; after
      close_nextturn hostScreens.closes.byReason.side +1; turn + 1 on both; EQUAL. When broken the end turn is frozen
      under the host's inventory: side 0 after SAMPLE_S, host top InventoryState, hostCovered.steps +0. The grenade
      explodes under the host's screen with or without the fix: never asserted.
  knockout_ends_battle: every alien but the lowest id killed (kill_unit_real, context-less); battleAutoEnd on both;
      the last alien on (24,23,0) health 5, C on (24,24,0) facing it with a stun rod; the host opens H's inventory and
      picks the grenade; client stun-rod melee (seed 1). Passes when, with the host's inventory never closed by the
      test, the battle ends (the test closes the host's NextTurnState when it is on top): host battleEnd.emitted 1 and
      evsAfter 0, client battleEnd.applied 1, both machines on their DebriefingState (the client's display-only), no
      InventoryState left on either machine, no crash file, desyncAtTeardown false on both. When broken the knockout
      is frozen: no battle end within END_WINDOW_S while the host's screen is open.

Common asserts (side_change_closes_inventory, pause_holds_alien_side, hot_grenade_end_turn; after wait_host_idle):
hash_now full EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and host 0; client
invLocalWrites 0 and invGuard unchanged; no screen left open; no new crash file; host hostCovered.byOrigin moves only
on intent / endturn. A failing row's cleanup (the host's cursor item back through inventory_cursor_clear, its screen
closed) lets the frozen side change finish; it is recorded and is a no-op on a passing run.

Constants: measured setup values, each with its measurement in the comment above it. Item ids come from each row's
staging record. Paired test commands go to the CLIENT first; player-unit teleports go HOST first, checked
(place_host_first); knockout_ends_battle's ALIEN teleport stays client-first (a host-first alien teleport makes the
host's next reveal ev carry state the client lacks and latches a client desync) after a check of the host leg's
refusal causes (the alien standing and not out on the host). One "EVIDENCE <id>:" line per row before its checks;
every row runs after an earlier failure; exit 0 only when every row passes, 2 otherwise. One run is the result; run it
in the foreground to completion.

Run:  python tools/coop_test/test_host_screens_turn.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
from test_inventory import (C_ID, H_ID, BELT, GRENADE, STAGE_H, OPTS, TU_MAX, stack, units, inv_view,
                               evidence, finish, wait_until, new_contexts, read_inventory_key)
from test_inventory_held import (STATUS_UNCONSCIOUS, KEY_SETTLE_S, CLOSE_KEY, place_host_first, read_key,
                                    restage_h, settle, crash_exception_lines, log_mark, ui_lines, dnum,
                                    item_both, dismiss_nts_all)
import test_host_screens as hs
from test_host_screens import (snap_hs, top, crash_census, hscr, hclose, hcov, hcov_origin, ctx_count, press, give_hands,
                                  set_state_both, open_host_inventory, host_pick, send_order, release,
                                  hs_common_fails, boot, KO_C_TILE, KO_C_DIR, KO_T_TILE, KO_T_DIR, KO_HEALTH,
                                  SEED_KO, STUN_ROD, jt)
from test_delta_core import short, both
from test_delta_items import items_by_id
import test_client_shoot as cs
from test_turn_baton import drive_full_cycle

# ----- the end turns, as measured: parallel, the host's END TURN first; a grenade-free partner END TURN flips the
# side at once under both screens; when broken, side_change_closes_inventory's host inventory re-inits on an alien
# with H's grenade on the cursor; in hot_grenade_end_turn the hot grenade explodes 4 ms into the endturn context
# under the host's screen, so only the context close and the flip are waited for -----
HOT_TILE = (34, 24, 0)            # an empty road tile (test_inventory_held's shot target)
TEXT_END_TURN_1_OF_2 = "END TURN 1/2"   # the host's END TURN tally after its own press
ARM_WAIT_S = 5.0
FLIP_WAIT_S = 30.0
SAMPLE_S = 5.0                    # pause_holds_alien_side samples 5 s; hot_grenade_end_turn's window (5 s of samples)
SIDE_SAMPLE_S = 3.0               # side_change_closes_inventory's record when broken: the alien side does not
                                  # progress under the host's screen
ARM_TIMEOUT_MS = 10000            # side_change_closes_inventory: battle_arm_key's deadline
ALIEN_END_WAIT_S = 10.0           # side_change_closes_inventory: the armed key's record is read once the alien side
                                  # is over (its next NextTurnState seen by the armed key), within this
CYCLE_S = 90                      # drive_full_cycle's timeout
SIDE_ALIEN = 1
# ----- the battle end, as measured: 12 aliens killed by id; the last on (24,23,0) health 5; C (24,24,0) dir 0 with
# a stun rod; seed 1: the end turn runs inside the partner's intent context (closed at endTurn entry); the battle
# ends after the host's NextTurnState closes -----
KILL_WAIT_S = 30.0
END_WINDOW_S = 10.0               # melee send -> both DebriefingState 1.615 s (x 6)
END_AFTER_S = 30.0                # a frozen row's released knockout -> both DebriefingState


# ===================== helpers =====================


def bsv(gc):
    b = battle_state(gc)
    return {k: b.get(k) for k in ("turn", "side", "selectedId", "isBusy", "pendingStates", "coopEndTurnText")}


def arm_host(host):
    """The host's own END TURN press first: its tally shows 1/2."""
    r = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    got, dt = wait_until(lambda: battle_state(host).get("coopEndTurnText") == TEXT_END_TURN_1_OF_2, ARM_WAIT_S, 0.05)
    return {"resp": {k: r.get(k) for k in ("ok", "error")}, "armed": bool(got), "waited": dt, "host": bsv(host)}


def client_end_turn(client):
    r = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    return {k: r.get(k) for k in ("ok", "error")}


def flip_watch(host, t0, timeout=FLIP_WAIT_S):
    """The first host sample with a NextTurnState on the stack or the side changed."""
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
    """turn + 1 on both (test_turn_baton.drive_full_cycle), every NextTurnState closed through its real close(),
    then the host idle."""
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
        fails.append(f"SETUP-FAILURE: {what}: drive_full_cycle failed: {cyc['err']} (host "
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


def side_change_closes_inventory(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"H": restage_h(host, client, STAGE_H, "belt_and_ground", placer=place_host_first)}
    staged = settle(host, client)
    g = st["H"]["ids"]["grenade"]
    turn0 = battle_state(host).get("turn")
    before = snap_hs(host, client)
    hmark = log_mark(host)
    ev = {"arm": arm_host(host)}
    opened = open_host_inventory(host, H_ID, ev)
    picked = host_pick(host, ev, "pick", BELT, 1, 0, g) if opened else False
    flip, after_nts, key_row, broken = None, {}, None, {}
    if ev["arm"]["armed"] and opened and picked:
        t0 = time.time()
        ev["clientEndTurn"] = client_end_turn(client)
        flip = flip_watch(host, t0)
        if flip and top(host) == "NextTurnState":
            # the host's INVENTORY key is armed in-game BEFORE the close, for the first frame of the alien side
            # with the battlescape on top (the alien side is over before a harness press lands)
            k = read_inventory_key(host.user_dir)
            ra = host.cmd({"cmd": "battle_arm_key", "key": k, "side": SIDE_ALIEN, "timeoutMs": ARM_TIMEOUT_MS})
            arm = {kk: ra.get(kk) for kk in ("ok", "armed", "frame", "error")}
            rn = host.cmd({"cmd": "close_nextturn"})
            eh = event_state(host)          # the first read after the close: no host input in between
            after_nts = {"close": {k: rn.get(k) for k in ("ok", "handled", "error")},
                         "hostScreens": eh.get("hostScreens"), "stack": stack(host), "side": bsv(host)["side"]}
            if (dnum(hclose(before["host"], "byReason", "side"), hclose(eh, "byReason", "side")) or 0) > 0:
                # the side close ran: the armed INVENTORY key during the alien side; its record is read once the
                # armed key saw the next turn's NextTurnState (or the arm expired)
                def side_over():
                    ak = event_state(host).get("armKey") or {}
                    return ak if (ak.get("nextTurnFrame", -1) >= 0 or ak.get("expired")) else None
                _, waited = wait_until(side_over, ALIEN_END_WAIT_S, 0.05)
                v = inv_view(host)
                key_row = {"key": k, "arm": arm, "armKey": event_state(host).get("armKey"), "waited": waited,
                           "stack": stack(host), "host": bsv(host),
                           "view": {kk: v.get(kk) for kk in ("open", "top", "unitId", "selectedItem")}}
            else:
                # no side close (when broken): the host's screen back on top during the alien side
                v = inv_view(host)
                broken["view"] = {kk: v.get(kk) for kk in ("open", "top", "unitId", "selectedItem")}
                samples = []
                t1 = time.time()
                while time.time() - t1 < SIDE_SAMPLE_S:
                    samples.append({"t": round(time.time() - t1, 2), "top": top(host), "host": bsv(host)})
                    time.sleep(0.5)
                broken["samples"] = samples
    rel = release(host, notes, "side_change_closes_inventory")
    cyc = cycle(host, client, turn0)
    end = {"grenade": item_both(host, client, g)}
    evidence("side_change_closes_inventory", {"staging": st, "stagedDiff": staged, "ui": ev, "flip": flip,
                                              "afterNts": after_nts, "key": key_row, "broken": broken,
                                              "release": rel, "cycle": cyc, "end": end,
                                              "hostUi": ui_lines(host, hmark)[-16:], "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"side_change_closes_inventory: buckets differ after the staging: {staged}")
    if not ev["arm"]["armed"]:
        fails.append(f"precondition (side_change_closes_inventory): the host's END TURN did not arm ({ev['arm']})")
    elif not opened or not picked:
        fails.append(f"precondition (side_change_closes_inventory): the host's inventory on H / the grenade pick "
                     f"({ev})")
    elif flip is None or "InventoryState" not in (flip.get("stack") or []) or flip["stack"][-1] != "NextTurnState":
        fails.append(f"precondition (side_change_closes_inventory): the side flip with NextTurnState over the host's "
                     f"inventory ({flip})")
    else:
        # the inventory closes at the first pump after the NextTurnState, before any host input (when broken it
        # re-inits on an alien, no side close)
        ds = dnum(hclose(before["host"], "byReason", "side"), hclose(after_nts, "byReason", "side"))
        di = dnum(hclose(before["host"], "byScreen", "inventory"), hclose(after_nts, "byScreen", "inventory"))
        if (ds, di) != (1, 1) or "InventoryState" in (after_nts.get("stack") or []):
            fails.append(f"side_change_closes_inventory: after close_nextturn host hostScreens.closes byReason.side "
                         f"+{ds}, byScreen.inventory "
                         f"+{di}, stack {after_nts.get('stack')} (want +1 / +1, no InventoryState; record when broken "
                         f"{broken})")
        elif key_row is None:
            fails.append("side_change_closes_inventory: the host's INVENTORY key was not armed for the alien side")
        else:
            ak = key_row.get("armKey") or {}
            if not (key_row["arm"].get("ok") and key_row["arm"].get("armed")):
                fails.append(f"side_change_closes_inventory: battle_arm_key did not arm the host's INVENTORY key "
                             f"({key_row['arm']})")
            elif not ak.get("fired") or ak.get("sideAtFire") != SIDE_ALIEN or ak.get("topBefore") != "BattlescapeState":
                fails.append(f"side_change_closes_inventory: the armed INVENTORY key did not fire on the alien side "
                             f"with the battlescape on "
                             f"top (want fired, sideAtFire {SIDE_ALIEN}, topBefore BattlescapeState; {ak})")
            elif ak.get("nextTurnFrame", -1) < 0:
                fails.append(f"side_change_closes_inventory: the armed key saw no next-turn NextTurnState within "
                             f"{ALIEN_END_WAIT_S} s of the close ({ak})")
            elif ak.get("inventoryPushesSinceFire") != 0:
                fails.append(f"side_change_closes_inventory: the host's INVENTORY key during the alien side opened a "
                             f"screen: inventoryPushesSinceFire {ak.get('inventoryPushesSinceFire')} before the next "
                             f"NextTurnState (want 0; {ak})")
    want_belt = {"owner": H_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
    for n in ("host", "client"):
        if {k: (end["grenade"][n] or {}).get(k) for k in want_belt} != want_belt:
            fails.append(f"side_change_closes_inventory: the {n}'s grenade {end['grenade'][n]} (want {want_belt})")
    fails += cycle_fails(cyc, turn0, "side_change_closes_inventory")
    fails += hs_common_fails(host, client, before, crash0, "side_change_closes_inventory")
    finish(fails)


def pause_holds_alien_side(host, client, ctx):
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
    rel = release(host, notes, "pause_holds_alien_side")
    cyc = cycle(host, client, turn0)
    evidence("pause_holds_alien_side", {"ui": ev, "flip": flip, "samples": samples, "pauseClosed": closed,
                                        "release": rel, "cycle": cyc, "hostUi": ui_lines(host, hmark)[-12:],
                                        "notes": notes})
    fails = list(notes)
    if not ev["arm"]["armed"] or not opened:
        fails.append(f"precondition (pause_holds_alien_side): the host's END TURN / PauseState ({ev})")
    elif flip is None or "PauseState" not in (flip.get("stack") or []) or flip["stack"][-1] != "NextTurnState":
        fails.append(f"precondition (pause_holds_alien_side): the side flip with NextTurnState over the host's "
                     f"PauseState ({flip})")
    else:
        bad = [s for s in samples if s["top"] != "PauseState" or s["host"].get("side") != SIDE_ALIEN
               or s["ai"] != 0 or s["steps"] != 0]
        if not samples or bad:
            fails.append(f"pause_holds_alien_side: with PauseState on top the host's alien side must hold (side "
                         f"{SIDE_ALIEN}, contextsOpened.ai +0, hostCovered.steps +0); offending samples {bad[:3]}")
        if not closed.get("ok"):
            fails.append(f"pause_holds_alien_side: the host's PauseState did not close ({closed})")
    fails += cycle_fails(cyc, turn0, "pause_holds_alien_side")
    fails += hs_common_fails(host, client, before, crash0, "pause_holds_alien_side")
    finish(fails)


def hot_grenade_end_turn(host, client, ctx):
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
    rel = release(host, notes, "hot_grenade_end_turn")
    if rel:
        window["afterRelease"] = flip_watch(host, time.time())
    cyc = cycle(host, client, turn0)
    cc = [c for c in new_contexts(before["host"]["closedContexts"], event_state(host).get("closedContexts"))
          if c.get("origin") == "endturn"]
    end = {"hotGrenade": {"host": gid in items_by_id(host), "client": gid in items_by_id(client)},
           "endturnContexts": cc}
    evidence("hot_grenade_end_turn", {"staging": st, "stagedDiff": staged, "ui": ev, "window": window,
                                      "afterNts": after_nts, "release": rel, "cycle": cyc, "end": end,
                                      "hostUi": ui_lines(host, hmark)[-12:], "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"hot_grenade_end_turn: buckets differ after the staging: {staged}")
    samples = window.get("samples") or []
    if not ev["arm"]["armed"] or not opened:
        fails.append(f"precondition (hot_grenade_end_turn): the host's END TURN / inventory ({ev})")
    elif not any(s["endturn"] >= 1 for s in samples):
        fails.append(f"precondition (hot_grenade_end_turn): host contextsOpened.endturn +0 after the client's END TURN "
                     f"(want +1: the hot grenade opens the endturn context); samples {samples[:2]}")
    else:
        f = window.get("flipped")
        if f is None:
            last = samples[-1] if samples else {}
            # when broken the end turn is frozen under the host's inventory
            fails.append(f"hot_grenade_end_turn: the end turn did not run under the host's inventory within {SAMPLE_S} "
                         f"s (last sample: side {(last.get('host') or {}).get('side')}, top {last.get('top')}, "
                         f"hostCovered.steps +{last.get('steps')}, byOrigin.endturn +{last.get('coveredEndturn')})")
        else:
            if f["stack"][-2:] != ["InventoryState", "NextTurnState"]:
                fails.append(f"hot_grenade_end_turn: the host's stack at the flip {f['stack']} (want NextTurnState "
                             f"over InventoryState)")
            if not isinstance(f.get("coveredEndturn"), int) or f["coveredEndturn"] <= 0:
                fails.append(f"hot_grenade_end_turn: host hostCovered.byOrigin.endturn +{f.get('coveredEndturn')} at "
                             f"the flip (want > 0)")
            ds = dnum(hclose(before["host"], "byReason", "side"), hclose(after_nts, "byReason", "side"))
            if ds != 1 or "InventoryState" in (after_nts.get("stack") or []):
                fails.append(f"hot_grenade_end_turn: after close_nextturn host hostScreens.closes.byReason.side +{ds}, "
                             f"stack {after_nts.get('stack')} (want +1, no InventoryState)")
    fails += cycle_fails(cyc, turn0, "hot_grenade_end_turn")
    fails += hs_common_fails(host, client, before, crash0, "hot_grenade_end_turn")
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
    """knockout_ends_battle's alien onto `tile`: the host leg's refusal causes checked first (the alien standing
    and not out on the host; the tile's own check is left to the teleport command), then test_client_shoot.place
    (client first: a host-first ALIEN teleport latches a client desync)."""
    uh = units(host).get(uid) or {}
    assert uh.get("status") == 0 and not uh.get("isOut"), f"staging: alien {uid} on the host {uh} (want standing)"
    return cs.place(host, client, uid, tile, d)


def knockout_ends_battle(host, client, ctx):
    notes = []
    crash0 = crash_census()
    kills = kill_all_but_one(host, client)
    last = kills["last"]
    st = {"H": restage_h(host, client, STAGE_H, "belt_and_ground", placer=place_host_first)}
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
    order, admitted, tops, ended, broken = {}, False, [], False, {}

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
                # the record when broken, then the cleanup (the cursor back, the screen closed, the knockout released)
                broken = {"hostStack": stack(host), "clientStack": stack(client),
                       "alien": {n: (units(gc).get(last) or {}).get("status") for n, gc in (("host", host),
                                                                                           ("client", client))},
                       "battleEnd": event_state(host).get("battleEnd", {}).get("emitted")}
                broken["release"] = release(host, notes, "knockout_ends_battle")
                broken["tops"] = []
                broken["ended"] = run_to_end(END_AFTER_S, broken["tops"])
    time.sleep(1.0)
    final = {"hostStack": stack(host), "clientStack": stack(client),
             "hostBattleEnd": event_state(host).get("battleEnd"), "clientBattleEnd": event_state(client).get("battleEnd")}
    for n, gc in (("host", host), ("client", client)):
        d = gc.cmd({"cmd": "debrief_state"})
        final[n + "Debrief"] = {k: d.get(k) for k in ("ok", "shown", "onTop", "displayOnly", "title")}
    nc = sorted(crash_census() - crash0)
    evidence("knockout_ends_battle", {"kills": kills, "staging": st, "stagedDiff": staged, "ui": ev,
                                      "order": {k: v for k, v in order.items() if k != "t0"}, "tops": tops,
                                      "ended": ended, "broken": broken, "final": final, "battleEndBefore": be0,
                                      "newCrashFiles": nc, "hostUi": ui_lines(host, hmark)[-16:],
                                      "clientUi": ui_lines(client, cmark)[-12:], "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"knockout_ends_battle: buckets differ after the staging: {staged}")
    if last is None or kills["liveHostile"] != [last] or kills.get("idleErr"):
        fails.append(f"precondition (knockout_ends_battle): every alien but {last} killed (live hostile "
                     f"{kills['liveHostile']}, {kills.get('idleErr')})")
    elif not opened or not picked:
        fails.append(f"precondition (knockout_ends_battle): the host's inventory on H / the grenade pick ({ev})")
    elif not admitted:
        fails.append(f"precondition (knockout_ends_battle): the client's melee on the last alien was not admitted "
                     f"({order})")
    elif not ended:
        # when broken the knockout is frozen, no battle end while the host's screen is open
        fails.append(f"knockout_ends_battle: the battle did not end within {END_WINDOW_S} s with the host's inventory "
                     f"open (the test "
                     f"closed only NextTurnStates; host stack at the window's end {broken.get('hostStack')}, alien "
                     f"status {broken.get('alien')})")
    else:
        hbe, cbe = final["hostBattleEnd"] or {}, final["clientBattleEnd"] or {}
        if hbe.get("emitted") != 1 or hbe.get("evsAfter") != 0:
            fails.append(f"knockout_ends_battle: host battleEnd emitted {hbe.get('emitted')} evsAfter "
                         f"{hbe.get('evsAfter')} (want 1 / 0)")
        if cbe.get("applied") != 1:
            fails.append(f"knockout_ends_battle: client battleEnd.applied {cbe.get('applied')} (want 1)")
        if hbe.get("desyncAtTeardown") or cbe.get("desyncAtTeardown"):
            fails.append(f"knockout_ends_battle: desyncAtTeardown host={hbe.get('desyncAtTeardown')} client="
                         f"{cbe.get('desyncAtTeardown')} (want false on both)")
        hd, cd = final["hostDebrief"], final["clientDebrief"]
        if not (hd.get("shown") and hd.get("onTop")) or not (cd.get("shown") and cd.get("onTop") and cd.get(
                "displayOnly")):
            fails.append(f"knockout_ends_battle: debriefs host={hd} client={cd} (want both shown on top, the client's "
                         f"display-only)")
    for n in ("hostStack", "clientStack"):
        if "InventoryState" in (final[n] or []):
            fails.append(f"knockout_ends_battle: an InventoryState is left on the {n[:-5]} ({final[n]})")
    if nc:
        fails.append(f"knockout_ends_battle: new crash file(s) {nc}: {crash_exception_lines(nc)}")
    finish(fails)


SCENARIOS = (("side_change_closes_inventory", side_change_closes_inventory),
             ("pause_holds_alien_side", pause_holds_alien_side), ("hot_grenade_end_turn", hot_grenade_end_turn),
             ("knockout_ends_battle", knockout_ends_battle))


def main():
    t0 = time.time()
    host = GameClient("host", 49960, make_user_dir("host_screens_turn_host", options=OPTS))
    client = GameClient("client", 49961, make_user_dir("host_screens_turn_client", options=OPTS))
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
                print(f"[host-screens] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_host_screens_turn: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
