"""test_host_screens.py: parallel mode, the second player's actions keep running while the host sits in any screen
(its inventory, the Esc menu, an info screen, the medi-kit screen, a message box); the host's screens refresh, return
a lost cursor item and close themselves when their soldier goes down; a covered inventory whose soldier goes down is
detached.

ONE boot = test_inventory.boot (the roster-pinned terror boot, paperdoll option on both; H = 10, C = 8, C2 = 9). Rows
in this order, every row ONE run, every row restages (knockout_closes_inventory, knockout_closes_menu and
knockout_covered_detach knock out H, H2 and H3, so they come last):
  walk_under_inventory: the host opens H's inventory; client walk order C (12,26,0) -> (9,29,0). Passes when the
      walk's context closes and C stands on the destination on both while the host's inventory_view.open is true;
      hostCovered.byOrigin.intent +> 0; then the host closes; EQUAL. When broken the walk is admitted and frozen (host
      contextsOpened.intent +1, isBusy, C still on its tile after HS_WALK_UNDER_S, hostCovered.steps +0).
  walk_under_pause: the same walk under the host's PauseState (its options key); passes as walk_under_inventory with
      PauseState on top throughout; the host closes it after.
  walk_under_unit_info: the same walk under the host's UnitInfoState on H (TAB H, the battlescape stats button by
      rect); passes as walk_under_inventory under UnitInfoState.
  walk_under_medikit: the host's MedikitState on C (H adjacent, a medi-kit in H's right hand; C one fatal wound);
      client walk order C two tiles away; then the host presses HEAL. Passes when the walk ends under MedikitState and
      the heal press closes it: host top BattlescapeState, host warningText "There is no one there!",
      hostScreens.medikitRefused +1, the kit's charges, H's TU and C's health and fatal wounds unchanged on both;
      EQUAL. When broken the walk is frozen and the heal applies to C.
  inventory_refreshes: the host opens H's inventory on (12,25,0); the client throws a rifle clip onto H's tile (seed
      1). Passes when, while the screen is open, the clip lies on H's tile on both and in the host's
      inventory_view.ground, hostScreens.refreshes +>= 1; EQUAL. When broken the throw is frozen (the clip still C's).
  cursor_item_returned: instant grenades on both; the host opens H's inventory on (12,20,0) and picks the rifle clip
      lying on H's tile; the client throws a primed grenade (fuse 0) at (12,22,0) (seed 2). Passes when, while the
      screen is open, the clip is gone on both, host selectedItem -1, hostScreens.cursorReturned +1, host
      invLastWarning "Order cancelled - item unavailable", H conscious on both; EQUAL. When broken the throw is frozen
      and the clip still on the host's cursor.
  knockout_closes_inventory: the host opens H's inventory on (24,23,0) and picks H's grenade (belt (1,0)); client
      stun-rod melee on H (seed 1). Leg 2: with the host's "has become unconscious" box on top, client walk order C2
      (4,32,0) -> (1,32,0). Then the box is dismissed. Leg 1 passes when H is unconscious on both,
      hostScreens.closes.byReason.unit_out +1 and byScreen.inventory +1, no InventoryState on the host, THEN the
      host's top InfoboxOKState whose text holds "has become unconscious"; leg 2 when C2 is on the destination on both
      with the box still up; after the dismiss the grenade lies among H's dropped items on (24,23,0) on both; EQUAL.
      When broken the melee is frozen, H conscious, no box.
  knockout_closes_menu: the host opens H2's action menu (TAB H2, the right-hand box); the client knocks H2 out. Passes
      when hostScreens.closes.byScreen.action_menu +1 (byReason.unit_out +1), no ActionMenuState when the box shows;
      the box dismissed; EQUAL. When broken the melee is frozen.
  knockout_covered_detach: the host opens H3's inventory and covers it (the inventory's Ufopaedia key); the client
      knocks H3 out. Passes when hostScreens.coveredDetach +1 while covered; the test dismisses the box and closes the
      cover: no new host crash file, then hostScreens.closes.byReason.unit_out +1, no InventoryState; EQUAL. When
      broken the melee is frozen and H3 conscious. (H and H2 lie unconscious after the two rows before and no test
      command revives a unit, so this row's target is the third host-seat soldier, H3 = 12.)

Common asserts, every row (after wait_host_idle): hash_now full EQUAL; desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; client invLocalWrites 0 and the client's invGuard unchanged; no host or
client screen left open; no new crash file; host hostCovered.byOrigin moves only on intent / endturn. A frozen row's
cleanup (after its window: the cursor item back through inventory_cursor_clear, the screen closed) lets the frozen
order finish so the next row starts clean; the cleanup is recorded in the row's EVIDENCE and is a no-op on a passing
run.

Constants: measured setup values, each with its measurement in the comment above it. Item ids come from each row's
staging record, never literals. Paired test commands go to the CLIENT first, except the teleports: host leg first,
checked, then the client leg (test_inventory_held.place_host_first). Every walk-window row pins the host camera on the
lane and the client's xcom dial 40; the other rows run at the boot's dial (30), as they were measured. A host key
right after a state opened waits KEY_SETTLE_S. Each row prints ONE "EVIDENCE <id>:" line with both machines' fields
before its conditions are checked; every row runs after an earlier failure; "PASS <id>" / "FAIL <id>: <message>". Exit
0 only when every row passes, 2 otherwise (a bring-up failure is also 2). One run is the result; run it in the
foreground to completion.

Run:  python tools/coop_test/test_host_screens.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state
import test_inventory as inv
from test_inventory import (C_ID, H_ID, BELT, LH, GROUND, RIFLE, RIFLE_CLIP, GRENADE, STAGE_H, OPTS, TU_MAX,
                               stack, units, inv_view, selected, click, order_done, evidence, finish, wait_until,
                               iview, new_contexts, give, drop, common_fails)
import test_inventory_held as held
from test_inventory_held import (C2_ID, STATUS_UNCONSCIOUS, C2_TILE, C2_DIR, C2_DEST, LANE_MID, WALK_DIAL,
                                    KEY_SETTLE_S, CLOSE_KEY, place_host_first, read_key, xcom_dial_of,
                                    set_xcom_dial, camera_lane, cover_inventory, restage_h, settle,
                                    crash_exception_lines, log_mark, ui_lines, dnum, item_both, unit_pos, ms_since,
                                    HELD_PROBE_KEYS)
from test_delta_core import short, both
from test_delta_items import items_by_id, unit_view
from test_client_items import strip_both, dismiss_host_box, items_of, charges
import test_client_shoot as cs
from test_host_combat import open_hand_menu_host, CURSOR_AIM
from test_turn_baton import RHAND_RECT, click_nth
from test_seat_pacing import tab_select

# ----- units (test_inventory.py :154-:156) -----
H2_ID = 11                        # the second host-seat soldier
H3_ID = 12                        # the third host-seat soldier (knockout_covered_detach's target; see the docstring)
RHAND_NTH = 25                    # click_widget nth of the right-hand box (test_host_combat.py :162)

# ----- the walks: C (12,26,0) dir 2 -> (9,29,0), 3 tiles, or (10,28,0), 2 tiles; the host camera centred on
# (11,27,0) (on screen), the client's battleXcomSpeed 40 and wait_seat_dial(seat 1, "xcom", 40). Measured on screen
# at dial 40 over 3 boots: 3 tiles 2339 ms, 2 tiles 1554-1559 ms (LANE_MID and WALK_DIAL: test_inventory_held) -----
WALK_C_TILE, WALK_C_DIR = (12, 26, 0), 2
WALK_DEST3 = (9, 29, 0)           # walk_under_inventory, walk_under_pause, walk_under_unit_info
WALK_DEST2 = (10, 28, 0)          # walk_under_medikit ("C two tiles away")
# The walk windows: the dial-40 step interval (40 ms) is longer than a frame, so a covered BattlescapeState's one
# step per frame keeps the uncovered pace; ~2 x the measured walk bounds a passing run, and each window is the whole
# extra time a frozen walk costs its row.
HS_WALK_UNDER_S = 4.5             # a 3-tile walk (2339 ms uncovered)
WALK2_UNDER_S = 3.5               # a 2-tile walk (1554-1559 ms uncovered)
BOOT_DIAL = 30                    # the boot's xcom dial; the throw and knockout rows were measured at it
# ----- the host's screens, as measured: the inventory opens and closes in ~100 ms; PauseState opens on
# keyBattleOptions (27) and closes on 27 after a 0.3 s settle; UnitInfoState opens on TAB H + click_widget nth 16
# (the stats button) and closes on 27; MedikitState opens from the hand box + key 49 in 954 ms -----
STATS_RECT = (107, 177, 164, 23)  # the battlescape stats button (click_widget nth 16)
SCREEN_WAIT_S = 3.0
# ----- the medi-kit: H (13,26,0) dir 6, a medi-kit in the right hand; C (12,26,0) wounds [0,0,1,0,0,0]; TAB H,
# the right-hand box nth 25, key 49; the heal button rect (190,120,30,20), key 51; end (220,140,20,20), key 27 -----
MED_H_TILE, MED_H_DIR = (13, 26, 0), 6
C_WOUNDS = [0, 0, 1, 0, 0, 0]
MEDIKIT = "STR_MEDI_KIT"
KEY_ITEM1 = 49                    # keyBattleActionItem1: USE MEDI-KIT (test_client_items KEY_ITEM1)
KEY_HEAL = 51                     # MedikitState SDLK_3: the heal button
TEXT_NO_ONE = "There is no one there!"   # xcom1 en-US STR_THERE_IS_NO_ONE_THERE (the partner's no_one_there deny)
WARN_READ_S = 1.0                 # the host's warning text is read within this of the press
# ----- the clip throw: C (12,27,0) dir 2 (facing reset via PARK (11,27,0)); H (12,25,0) dir 4; the clip given
# with clear_hands; seed 1: it landed on (12,25,0) on both in 4 runs of 4 -----
THROW_C_TILE, THROW_C_DIR = (12, 27, 0), 2
THROW_H_TILE, THROW_H_DIR = (12, 25, 0), 4
PARK_TILE = (11, 27, 0)
SEED_THROW = 1
# ----- the grenade throw: battleInstantGrenade on both; a grenade (fuse 0) thrown at (12,22,0); H (12,20,0) dir 4
# with a clip on its tile and its health raised to 500; C (12,27,0); seed 2: the clip was removed on both in 3 runs
# of 3, H conscious -----
BLAST_TARGET = (12, 22, 0)
BLAST_H_TILE, BLAST_H_DIR = (12, 20, 0), 4
H_HEALTH_RAISED = 500
SEED_BLAST = 2
TEXT_ITEM_MISSING = "Order cancelled - item unavailable"   # STR_COOP_DENY_ITEM_MISSING (test_inventory TEXT_DENY)
# ----- the knockout: C (24,24,0) dir 0 with a stun rod; the target on (24,23,0), health 5, no fatal wounds;
# battle_intent melee; seed 1: H and H2 unconscious on both in 3 runs of 3; the box "<name>\nhas become
# unconscious" at 1459-1715 ms (H staged with restage_h belt_and_ground (dir 2), H2 with place dir 4) -----
KO_C_TILE, KO_C_DIR = (24, 24, 0), 0
KO_T_TILE, KO_T_DIR = (24, 23, 0), 4
KO_HEALTH = 5
SEED_KO = 1
STUN_ROD = "STR_STUN_ROD"
TEXT_UNCONSCIOUS = "has become unconscious"
# ----- windows (about 3 x the longest measured order; the walk windows are above) -----
ORDER_UNDER_S = 5.5               # throws: the clip 556 ms, the grenade 1312 ms (a covered projectile moves one step
                                  # per frame instead of battleFireSpeed's 6, so the flight can take longer)
KO_UNDER_S = 4.5                  # the knockout box: 1459-1715 ms (a melee has no projectile)
MELEE_CLOSE_S = 2.0               # knockout_closes_inventory leg 2: the melee's context closes a few driven steps
                                  # after its box
ADMIT_WAIT_S = 5.0                # a partner order was admitted 0.124 s after the send
AFTER_WAIT_S = 20.0               # a frozen row's released order finishes within this after its cleanup
BOX_WAIT_S = 10.0

HS_KEYS = ("hostCovered", "hostScreens")


# ===================== probes =====================


def probes_hs(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in inv.PROBE_KEYS + HELD_PROBE_KEYS + HS_KEYS}


def snap_hs(host, client):
    return {"host": probes_hs(host), "client": probes_hs(client)}


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


from harness import CRASH_DIR  # noqa: E402  (this harness slot's own crash folder)


def crash_census():
    """Every file in the exe's crashlogs directory, where the crash handler writes each crash_*.log and .dmp
    (only new ones count). test_inventory_held.crash_files() globs the harness root and the whole exe tree
    recursively (~2 s a call), too slow for a census on every row."""
    try:
        return {os.path.join(CRASH_DIR, f) for f in os.listdir(CRASH_DIR)}
    except OSError:
        return set()


def hscr(p):
    return (p or {}).get("hostScreens") or {}


def hclose(p, group, k):
    return ((hscr(p).get("closes") or {}).get(group) or {}).get(k)


def hcov(p):
    return (p or {}).get("hostCovered") or {}


def hcov_origin(p, k):
    return (hcov(p).get("byOrigin") or {}).get(k)


def ctx_count(p, origin):
    return ((p or {}).get("contextsOpened") or {}).get(origin) or 0


def box_texts(gc):
    return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]


def pos(gc, uid):
    return unit_pos(gc, uid)


def status_both(host, client, uid):
    return {n: {k: (units(gc).get(uid) or {}).get(k) for k in ("status", "isOut", "health", "stun")}
            for n, gc in (("host", host), ("client", client))}


def unconscious_both(host, client, uid):
    return all((units(gc).get(uid) or {}).get("status") == STATUS_UNCONSCIOUS for gc in (host, client))


def press(gc, key):
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})


# ===================== staging (teleports host first; other paired test commands client first) =================


def set_state_both(host, client, uid, **fields):
    req = dict({"cmd": "battle_set_unit_state", "unit": uid}, **fields)
    return both(host, client, req, tuple(k for k in ("health", "stun", "status", "fatalWounds") if k in fields))


def give_hands(host, client, uid, item, **extra):
    """battle_give with clear_hands (both hands emptied first); returns the item id."""
    req = dict({"cmd": "battle_give", "unit": uid, "item": item, "clear_hands": True}, **extra)
    return both(host, client, req, ("weaponId", "ammoId"))["weaponId"]


def reset_facing(host, client, uid, tile, d):
    """Turn the unit to `d` on `tile`: PARK_TILE first, then the tile (never onto its own tile), host first."""
    a = place_host_first(host, client, uid, PARK_TILE, d)
    b = place_host_first(host, client, uid, tile, d)
    return {"park": a, "to": b}


def ensure_dial(host, client, value):
    """The client's xcom dial = `value` on both tables (a no-op when it already is)."""
    if xcom_dial_of(host) == value and xcom_dial_of(client) == value:
        return {"kept": value}
    return {"set": value, "tables": set_xcom_dial(host, client, value)}


def open_host_inventory(host, uid, ev):
    r = host.cmd({"cmd": "battle_open_inventory", "unit": uid})
    ev["hostOpen"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    v = inv_view(host)
    ev["hostOpenView"] = {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    return bool(r.get("opened")) and v.get("top") is True and v.get("unitId") == uid


def close_host_inventory(host):
    r = host.cmd({"cmd": "battle_close_inventory"})
    got, _ = wait_until(lambda: "InventoryState" not in stack(host), 2.0, 0.02)
    return {"ok": r.get("ok"), "error": r.get("error"), "gone": bool(got)}


def host_pick(host, ev, key, slot, x, y, want):
    ev[key] = click(host, slot=slot, x=x, y=y)
    got, dt = wait_until(lambda: selected(host) == want, 2.0, 0.02)
    ev[key]["cursor"] = selected(host)
    ev[key]["waited"] = dt
    return bool(got)


def open_hand_menu_unit(host, uid):
    """test_host_combat.open_hand_menu_host (:284-:304) for unit `uid`: TAB-select it on the host, then the
    right-hand box (one extra click first when it is still aiming) -> ActionMenuState."""
    assert tab_select(host, uid), f"TAB never selected {uid} on the host (selectedId " \
                                  f"{battle_state(host).get('selectedId')})"
    want = (RHAND_RECT[0] + RHAND_RECT[2] // 2, RHAND_RECT[1] + RHAND_RECT[3] // 2)
    cursor = [battle_state(host).get("cursorType")]
    if cursor[0] == CURSOR_AIM:
        r = click_nth(host, RHAND_NTH)
        assert (r.get("baseX"), r.get("baseY")) == want, f"right-hand click landed off the box: {r}"
        cursor.append(battle_state(host).get("cursorType"))
    r = click_nth(host, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == want, f"right-hand click landed off the box: {r}"
    host.wait_for("host ActionMenuState on top",
                  lambda: host.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState") or None,
                  timeout=5)
    return cursor


# ===================== the partner's order =====================


def send_order(host, client, req, before):
    """ONE battle_intent from the client; bounded wait until the host admits it (host contextsOpened.intent +1) or
    denies it (client lastDeny.iseq). Returns the record and whether it was admitted."""
    ci0 = ctx_count(before["host"], "intent")
    t0 = time.time()
    r = client.cmd(dict(req))
    out = {"resp": {k: r.get(k) for k in ("ok", "iseq", "error")}, "t0": t0}
    iseq = r.get("iseq") if r.get("ok") else None
    if not iseq:
        return out, False

    def answer():
        if ctx_count({"contextsOpened": event_state(host).get("contextsOpened")}, "intent") > ci0:
            return "admitted"
        if (event_state(client).get("lastDeny") or {}).get("iseq") == iseq:
            return "denied"
        return None
    got, out["answerWaited"] = wait_until(answer, ADMIT_WAIT_S, 0.02)
    out["answer"] = got
    if got == "denied":
        out["lastDeny"] = event_state(client).get("lastDeny")
    out["hostIsBusy"] = battle_state(host).get("isBusy")
    return out, got == "admitted"


def jt(t):
    return {"x": t[0], "y": t[1], "z": t[2]}


def walk_req(uid, dest):
    return {"cmd": "battle_intent", "kind": "walk", "actor": uid, "dest": jt(dest)}


def walk_done_fn(host, client, uid, dest, cc0):
    """The walk is over: its {intent, walk, uid} context closed on the host, the unit on `dest` on both, the
    client caught up and nothing held."""
    def done():
        eh, ec = event_state(host), event_state(client)
        ctx = [c for c in new_contexts(cc0, eh.get("closedContexts")) if c.get("origin") == "intent"
               and c.get("kind") == "walk" and c.get("actorId") == uid]
        return bool(ctx) and pos(host, uid) == tuple(dest) and pos(client, uid) == tuple(dest) and order_done(
            host, client)
    return done


def wait_under(host, client, done, window, t0, screen):
    """Poll `done` for up to `window` s from `t0` while the host's covering screen `screen` stays on top. Returns
    {done, ms, topAtDone, tops (every distinct host top seen)}."""
    tops = []
    while True:
        t = top(host)
        if not tops or tops[-1] != t:
            tops.append(t)
        if done():
            return {"done": True, "ms": ms_since(t0), "topAtDone": top(host), "tops": tops}
        if time.time() - t0 > window:
            return {"done": False, "ms": ms_since(t0), "topAtDone": None, "tops": tops,
                    "screenStillTop": top(host) == screen}
        time.sleep(0.05)


def frozen_sample(host, client, uid):
    """The record of a frozen order: where the partner's unit stands and what the host's chain holds."""
    return {"unit": {"host": pos(host, uid), "client": pos(client, uid)}, "hostIsBusy": battle_state(host).get("isBusy"),
            "hostCovered": event_state(host).get("hostCovered"), "hostStack": stack(host)}


def release(host, notes, what):
    """A frozen row's cleanup (a no-op on a passing row): the host's cursor item back through
    inventory_cursor_clear (no click), then every host screen this file opens closed from the top: an
    InventoryState through battle_close_inventory, a box through dismiss_host_box, anything else through its
    cancel key after KEY_SETTLE_S. A NextTurnState or a DebriefingState is never touched (the side cycle and the
    battle end handle them). Recorded."""
    rec = []
    for _ in range(4):
        t = top(host)
        if t in ("BattlescapeState", "NextTurnState", "DebriefingState") or t is None:
            break
        if t == "InventoryState":
            rec.append({"cursorClear": host.cmd({"cmd": "inventory_cursor_clear"})})
            r = host.cmd({"cmd": "battle_close_inventory"})
            wait_until(lambda: top(host) != "InventoryState", 2.0, 0.02)
            rec.append({"closed": t, "ok": r.get("ok"), "error": r.get("error"), "top": top(host)})
        elif "Infobox" in t:
            box = []
            dismiss_host_box(host, box)
            rec.append({"box": box})
        else:
            time.sleep(KEY_SETTLE_S)
            press(host, read_key(host.user_dir, CLOSE_KEY))
            wait_until(lambda: top(host) != t, 2.0, 0.02)
            rec.append({"closed": t, "by": CLOSE_KEY, "top": top(host)})
    if rec:
        notes.append(f"{what}: host screens closed by the test after the window: {rec}")
    return rec


def finish_order(host, client, notes, what, box=None):
    """After a release: bounded wait for the released order (a host box closed host-only meanwhile)."""
    t0 = time.time()
    while time.time() - t0 < AFTER_WAIT_S:
        if box is not None:
            dismiss_host_box(host, box)
        if order_done(host, client) and not battle_state(host).get("isBusy"):
            return round(time.time() - t0, 2)
        time.sleep(0.1)
    notes.append(f"{what}: the released order never finished within {AFTER_WAIT_S} s (host top {top(host)})")
    return None


# ===================== row wrap-up =====================


def hs_common_fails(host, client, before, crash0, what):
    """test_inventory.common_fails (hash, desync, pushes, invLocalWrites, host screen closed, the client's
    invGuard unchanged) plus: no new crash file, no screen left on either machine, and the host driver's origins
    (only intent / endturn may move)."""
    fails = common_fails(host, client, before, {}, None, what)
    nc = sorted(crash_census() - crash0)
    if nc:
        fails.append(f"{what}: new crash file(s) {nc}: {crash_exception_lines(nc)}")
    for n, gc in (("host", host), ("client", client)):
        t = top(gc)
        if t != "BattlescapeState":
            fails.append(f"{what}: the {n}'s top state at the row's end {t} (stack {stack(gc)}; want BattlescapeState)")
    b0, b1 = hcov(before["host"]).get("byOrigin") or {}, hcov(event_state(host)).get("byOrigin") or {}
    odd = {k: (b0.get(k), v) for k, v in b1.items() if k not in ("intent", "endturn") and v != b0.get(k)}
    if odd:
        fails.append(f"{what}: host hostCovered.byOrigin moved on {odd} (only intent / endturn may move)")
    return fails


def cov_delta(before, after, k):
    return dnum(hcov_origin(before, k), hcov_origin(after, k))


# ===================== walk rows =====================


def walk_row(host, client, name, open_screen, screen, close_screen, restage=False):
    """The three walk rows: `open_screen` puts the host's `screen` on top; the client's walk C -> WALK_DEST3 must
    end under it (when broken it stays frozen); `close_screen` closes it. walk_under_inventory restages H on STAGE_H
    (belt_and_ground); walk_under_pause and walk_under_unit_info use H where walk_under_inventory left it."""
    notes = []
    crash0 = crash_census()
    st = {"H": (restage_h(host, client, STAGE_H, "belt_and_ground", placer=place_host_first) if restage
                else pos(host, H_ID)),
          "C": place_host_first(host, client, C_ID, WALK_C_TILE, WALK_C_DIR)}
    st["cTu"] = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    ev = {"dial": ensure_dial(host, client, WALK_DIAL)}
    before = snap_hs(host, client)
    opened = open_screen(ev)
    ev["camera"] = camera_lane(host)
    order, admitted, under = {}, False, {}
    if opened:
        order, admitted = send_order(host, client, walk_req(C_ID, WALK_DEST3), before)
        if admitted:
            under = wait_under(host, client, walk_done_fn(host, client, C_ID, WALK_DEST3,
                                                         before["host"]["closedContexts"]),
                               HS_WALK_UNDER_S, order["t0"], screen)
            if not under["done"]:
                under["frozen"] = frozen_sample(host, client, C_ID)
            under["atDone"] = {"C": {"host": pos(host, C_ID), "client": pos(client, C_ID)},
                               "hostCovered": event_state(host).get("hostCovered")}
        ev["close"] = close_screen()
    rel = release(host, notes, name)
    after_s = finish_order(host, client, notes, name) if (admitted and not under.get("done")) else None
    after = snap_hs(host, client)
    evidence(name, {"staging": st, "stagedDiff": staged, "ui": ev, "order": {k: v for k, v in order.items()
                                                                             if k != "t0"},
                    "under": under, "release": rel, "afterReleaseS": after_s,
                    "hostCovered": (before["host"]["hostCovered"], after["host"]["hostCovered"]),
                    "C": {"host": unit_view(units(host).get(C_ID)), "client": unit_view(units(client).get(C_ID))},
                    "notes": notes})
    fails = list(notes) + held.staged_fails({"tu": st["cTu"]}, staged, inv.C_TU_MAX, "C")
    if not opened:
        fails.append(f"precondition ({name}): the host's {screen} did not open ({ev})")
    elif not admitted:
        fails.append(f"precondition ({name}): the client's walk was not admitted ({order})")
    else:
        # the walk must end under the host's screen (when broken it is admitted and frozen there)
        if not under.get("done"):
            fails.append(f"{name}: the walk did not end under the host's {screen} within {HS_WALK_UNDER_S} s "
                         f"({under.get('frozen')})")
        elif under.get("tops") != [screen]:
            fails.append(f"{name}: the host's tops while the walk ran {under.get('tops')} (want only {screen})")
        dc = cov_delta(before["host"], under.get("atDone") or {}, "intent") if under.get("done") else None
        if under.get("done") and (not isinstance(dc, int) or dc <= 0):
            fails.append(f"{name}: host hostCovered.byOrigin.intent +{dc} when the walk ended (want > 0)")
        if pos(host, C_ID) != WALK_DEST3 or pos(client, C_ID) != WALK_DEST3:
            fails.append(f"{name}: C host={pos(host, C_ID)} client={pos(client, C_ID)} (want {WALK_DEST3} on both)")
    fails += hs_common_fails(host, client, before, crash0, name)
    finish(fails)


def walk_under_inventory(host, client, ctx):
    def open_screen(ev):
        return open_host_inventory(host, H_ID, ev)

    walk_row(host, client, "walk_under_inventory", open_screen, "InventoryState", lambda: close_host_inventory(host),
             restage=True)


def walk_under_pause(host, client, ctx):
    def open_screen(ev):
        k = read_key(host.user_dir, "keyBattleOptions")
        ev["key"] = k
        press(host, k)
        got, ev["pauseWaited"] = wait_until(lambda: top(host) == "PauseState", SCREEN_WAIT_S, 0.02)
        ev["stack"] = stack(host)
        return bool(got)

    def close_screen():
        time.sleep(KEY_SETTLE_S)
        press(host, read_key(host.user_dir, CLOSE_KEY))
        got, _ = wait_until(lambda: top(host) == "BattlescapeState", 2.0, 0.02)
        return {"closed": bool(got), "stack": stack(host)}
    walk_row(host, client, "walk_under_pause", open_screen, "PauseState", close_screen)


def walk_under_unit_info(host, client, ctx):
    def open_screen(ev):
        ev["tab"] = tab_select(host, H_ID)
        lw = host.cmd({"cmd": "list_widgets"})
        vis = [w for w in lw.get("widgets", []) if w.get("interactive") and w.get("visible")]
        nth = [i for i, w in enumerate(vis) if (w.get("x"), w.get("y"), w.get("w"), w.get("h")) == STATS_RECT]
        ev["statsButton"] = nth
        if not ev["tab"] or len(nth) != 1:
            return False
        r = host.cmd({"cmd": "click_widget", "nth": nth[0]})
        ev["click"] = {k: r.get(k) for k in ("ok", "baseX", "baseY", "error")}
        got, ev["unitInfoWaited"] = wait_until(lambda: top(host) == "UnitInfoState", SCREEN_WAIT_S, 0.02)
        ev["stack"] = stack(host)
        return bool(got)

    def close_screen():
        time.sleep(KEY_SETTLE_S)
        press(host, read_key(host.user_dir, CLOSE_KEY))
        got, _ = wait_until(lambda: top(host) == "BattlescapeState", 2.0, 0.02)
        return {"closed": bool(got), "stack": stack(host)}
    walk_row(host, client, "walk_under_unit_info", open_screen, "UnitInfoState", close_screen)


# ===================== walk_under_medikit =====================


def walk_under_medikit(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"kit": give_hands(host, client, H_ID, MEDIKIT),
          "H": place_host_first(host, client, H_ID, MED_H_TILE, MED_H_DIR),
          "C": place_host_first(host, client, C_ID, WALK_C_TILE, WALK_C_DIR)}
    st["Cwounds"] = set_state_both(host, client, C_ID, fatalWounds=C_WOUNDS)
    st["hTu"] = cs.set_tu_both(host, client, H_ID, TU_MAX)
    st["cTu"] = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    kit = st["kit"]
    ev = {"dial": ensure_dial(host, client, WALK_DIAL)}
    before = snap_hs(host, client)
    ih0, ic0 = items_of(host), items_of(client)
    pre = {"kit": {"host": charges(ih0, kit), "client": charges(ic0, kit)},
           "Htu": {"host": inv.tu_of(host, H_ID), "client": inv.tu_of(client, H_ID)},
           "C": {n: {k: (units(gc).get(C_ID) or {}).get(k) for k in ("health", "wounds")}
                 for n, gc in (("host", host), ("client", client))}}
    opened = False
    try:
        ev["menu"] = open_hand_menu_host(host)
        time.sleep(KEY_SETTLE_S)
        press(host, KEY_ITEM1)
        opened, ev["medikitWaited"] = wait_until(lambda: top(host) == "MedikitState", SCREEN_WAIT_S, 0.02)
    except Exception as e:
        notes.append(f"walk_under_medikit: the host's medi-kit screen: {short(e)}")
    ev["stack"] = stack(host)
    ev["camera"] = camera_lane(host)
    order, admitted, under, press_rec = {}, False, {}, {}
    if opened:
        pre["HtuAtOpen"] = {"host": inv.tu_of(host, H_ID), "client": inv.tu_of(client, H_ID)}
        order, admitted = send_order(host, client, walk_req(C_ID, WALK_DEST2), before)
        if admitted:
            under = wait_under(host, client, walk_done_fn(host, client, C_ID, WALK_DEST2,
                                                         before["host"]["closedContexts"]),
                               WALK2_UNDER_S, order["t0"], "MedikitState")
            if not under["done"]:
                under["frozen"] = frozen_sample(host, client, C_ID)
        # the heal press: the patient has walked away (when broken C is still adjacent and the heal applies)
        s0 = snap_hs(host, client)
        time.sleep(KEY_SETTLE_S)
        press(host, KEY_HEAL)
        time.sleep(WARN_READ_S)
        ih1, ic1 = items_of(host), items_of(client)
        press_rec = {"top": top(host), "stack": stack(host), "warningText": battle_state(host).get("warningText"),
                     "medikitRefused": (dnum(hscr(s0["host"]).get("medikitRefused"),
                                             hscr(event_state(host)).get("medikitRefused"))),
                     "kit": {"host": charges(ih1, kit), "client": charges(ic1, kit)},
                     "Htu": {"host": inv.tu_of(host, H_ID), "client": inv.tu_of(client, H_ID)},
                     "C": {n: {k: (units(gc).get(C_ID) or {}).get(k) for k in ("health", "wounds")}
                           for n, gc in (("host", host), ("client", client))}}
    rel = release(host, notes, "walk_under_medikit")
    after_s = finish_order(host, client, notes, "walk_under_medikit") if (admitted and not under.get("done")) else None
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"walk_under_medikit: host never idle: {short(e)}")
    final = {"kit": {"host": charges(items_of(host), kit), "client": charges(items_of(client), kit)},
             "C": {n: {k: (units(gc).get(C_ID) or {}).get(k) for k in ("health", "wounds")}
                   for n, gc in (("host", host), ("client", client))}}
    ev["woundsCleared"] = set_state_both(host, client, C_ID, fatalWounds=[0] * 6)
    evidence("walk_under_medikit", {"staging": st, "stagedDiff": staged, "pre": pre, "ui": ev,
                                    "order": {k: v for k, v in order.items() if k != "t0"}, "under": under,
                                    "press": press_rec, "release": rel, "afterReleaseS": after_s, "final": final,
                                    "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"walk_under_medikit: buckets differ after the staging: {staged}")
    if not opened:
        fails.append(f"precondition (walk_under_medikit): the host's MedikitState did not open on C ({ev})")
    elif not admitted:
        fails.append(f"precondition (walk_under_medikit): the client's walk was not admitted under MedikitState "
                     f"({order})")
    else:
        if not under.get("done"):
            fails.append(f"walk_under_medikit: the walk did not end under the host's MedikitState within "
                         f"{WALK2_UNDER_S} s ({under.get('frozen')})")
        elif under.get("tops") != ["MedikitState"]:
            fails.append(f"walk_under_medikit: the host's tops while the walk ran {under.get('tops')} (want only "
                         f"MedikitState)")
        if press_rec.get("top") != "BattlescapeState":
            fails.append(f"walk_under_medikit: the host's top after the heal press {press_rec.get('top')} (want "
                         f"BattlescapeState: the press closes the screen)")
        if press_rec.get("warningText") != TEXT_NO_ONE:
            fails.append(f"walk_under_medikit: host warningText after the press {press_rec.get('warningText')!r} (want "
                         f"{TEXT_NO_ONE!r})")
        if press_rec.get("medikitRefused") != 1:
            fails.append(f"walk_under_medikit: host hostScreens.medikitRefused +{press_rec.get('medikitRefused')} "
                         f"(want +1)")
        if press_rec.get("kit") != pre["kit"]:
            fails.append(f"walk_under_medikit: the kit's charges {pre['kit']} -> {press_rec.get('kit')} (want "
                         f"unchanged on both)")
        if press_rec.get("Htu") != pre.get("HtuAtOpen"):
            fails.append(f"walk_under_medikit: H TU {pre.get('HtuAtOpen')} -> {press_rec.get('Htu')} (want unchanged "
                         f"on both)")
        if press_rec.get("C") != pre["C"]:
            fails.append(f"walk_under_medikit: C health / wounds {pre['C']} -> {press_rec.get('C')} (want unchanged on "
                         f"both)")
    fails += hs_common_fails(host, client, before, crash0, "walk_under_medikit")
    finish(fails)


# ===================== inventory_refreshes =====================


def inventory_refreshes(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"dial": ensure_dial(host, client, BOOT_DIAL),
          "H": place_host_first(host, client, H_ID, THROW_H_TILE, THROW_H_DIR)}
    st["hTu"] = cs.set_tu_both(host, client, H_ID, TU_MAX)
    st["clip"] = give_hands(host, client, C_ID, RIFLE_CLIP)
    st["C"] = reset_facing(host, client, C_ID, THROW_C_TILE, THROW_C_DIR)
    st["cTu"] = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    clip = st["clip"]
    ev = {}
    before = snap_hs(host, client)
    opened = open_host_inventory(host, H_ID, ev)
    ev["groundAtOpen"] = inv_view(host).get("ground")
    order, admitted, under = {}, False, {}
    want = {"onTile": True, "tx": THROW_H_TILE[0], "ty": THROW_H_TILE[1], "tz": THROW_H_TILE[2], "owner": -1}

    def landed():
        ih, ic = iview(items_by_id(host), clip) or {}, iview(items_by_id(client), clip) or {}
        return ({k: ih.get(k) for k in want} == want and {k: ic.get(k) for k in want} == want
                and order_done(host, client))
    if opened:
        host.ok({"cmd": "set_seed", "seed": SEED_THROW})
        order, admitted = send_order(host, client, {"cmd": "battle_intent", "kind": "throw", "actor": C_ID,
                                                    "plan": {"item": clip, "target": jt(THROW_H_TILE),
                                                             "targetUnit": -1}}, before)
        if admitted:
            under = wait_under(host, client, landed, ORDER_UNDER_S, order["t0"], "InventoryState")
            under["view"] = inv_view(host)
            under["hostScreens"] = event_state(host).get("hostScreens")
            under["clip"] = item_both(host, client, clip)
            if not under["done"]:
                under["frozen"] = frozen_sample(host, client, C_ID)
    if under.get("done"):
        ev["close"] = close_host_inventory(host)
    rel = release(host, notes, "inventory_refreshes")
    after_s = finish_order(host, client, notes, "inventory_refreshes") if (admitted and not under.get("done")) else None
    evidence("inventory_refreshes", {"staging": st, "stagedDiff": staged, "ui": ev,
                                     "order": {k: v for k, v in order.items() if k != "t0"},
                                     "under": under, "release": rel, "afterReleaseS": after_s,
                                     "clipEnd": item_both(host, client, clip), "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"inventory_refreshes: buckets differ after the staging: {staged}")
    if not opened:
        fails.append(f"precondition (inventory_refreshes): the host's inventory did not open on H ({ev})")
    elif not admitted:
        fails.append(f"precondition (inventory_refreshes): the client's throw was not admitted ({order})")
    else:
        # the clip lands under the open screen, which re-lays its ground (when broken the throw is frozen)
        if not under.get("done"):
            fails.append(f"inventory_refreshes: the clip did not land on H's tile {THROW_H_TILE} on both under the "
                         f"host's open "
                         f"inventory within {ORDER_UNDER_S} s (clip {under.get('clip')}, {under.get('frozen')})")
        else:
            if under.get("tops") != ["InventoryState"]:
                fails.append(f"inventory_refreshes: the host's tops while the throw ran {under.get('tops')} (want only "
                             f"InventoryState)")
            gl = [g for g in (under.get("view") or {}).get("ground") or [] if g.get("id") == clip]
            if len(gl) != 1 or not isinstance(gl[0].get("x"), int) or not isinstance(gl[0].get("y"), int):
                fails.append(f"inventory_refreshes: the host's inventory_view.ground with the screen open "
                             f"{under['view'].get('ground')} (want the clip {clip} in a laid-out cell)")
            dr = dnum(hscr(before["host"]).get("refreshes"), hscr({"hostScreens": under.get("hostScreens")}).get(
                "refreshes"))
            if not isinstance(dr, int) or dr < 1:
                fails.append(f"inventory_refreshes: host hostScreens.refreshes +{dr} with the screen open (want >= 1)")
    ce = item_both(host, client, clip)
    for n in ("host", "client"):
        if {k: (ce[n] or {}).get(k) for k in want} != want:
            fails.append(f"inventory_refreshes: the {n}'s clip at the row's end {ce[n]} (want {want})")
    fails += hs_common_fails(host, client, before, crash0, "inventory_refreshes")
    finish(fails)


# ===================== cursor_item_returned =====================


def cursor_item_returned(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"dial": ensure_dial(host, client, BOOT_DIAL),
          "instant": both(host, client, {"cmd": "set_option", "name": "battleInstantGrenade", "value": True},
                          ("ok",))["ok"],
          "H": place_host_first(host, client, H_ID, BLAST_H_TILE, BLAST_H_DIR)}
    st["Hset"] = set_state_both(host, client, H_ID, health=H_HEALTH_RAISED, stun=0)
    st["groundClip"] = drop(host, client, BLAST_H_TILE, RIFLE_CLIP)
    st["grenade"] = give_hands(host, client, C_ID, GRENADE, fuse=0)
    st["C"] = reset_facing(host, client, C_ID, THROW_C_TILE, THROW_C_DIR)
    st["cTu"] = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    clip, g = st["groundClip"], st["grenade"]
    ev = {}
    opened = open_host_inventory(host, H_ID, ev)
    picked = False
    if opened:
        ground = inv_view(host).get("ground") or []
        ev["ground"] = ground
        hit = [gi for gi in ground if gi.get("id") == clip]
        if hit:
            picked = host_pick(host, ev, "pick", GROUND, hit[0]["x"], hit[0]["y"], clip)
    before = snap_hs(host, client)
    order, admitted, under = {}, False, {}

    def gone_and_returned():
        return (clip not in items_by_id(host) and clip not in items_by_id(client) and selected(host) == -1
                and order_done(host, client))
    if opened and picked:
        host.ok({"cmd": "set_seed", "seed": SEED_BLAST})
        order, admitted = send_order(host, client, {"cmd": "battle_intent", "kind": "throw", "actor": C_ID,
                                                    "plan": {"item": g, "target": jt(BLAST_TARGET),
                                                             "targetUnit": -1}}, before)
        if admitted:
            under = wait_under(host, client, gone_and_returned, ORDER_UNDER_S, order["t0"], "InventoryState")
            eh = event_state(host)
            under["view"] = {k: v for k, v in inv_view(host).items() if k != "ground"}
            under["hostScreens"] = eh.get("hostScreens")
            under["invLastWarning"] = eh.get("invLastWarning")
            under["clip"] = {"host": clip in items_by_id(host), "client": clip in items_by_id(client)}
            under["H"] = status_both(host, client, H_ID)
            if not under["done"]:
                under["frozen"] = frozen_sample(host, client, C_ID)
    if under.get("done"):
        ev["close"] = close_host_inventory(host)
    rel = release(host, notes, "cursor_item_returned")
    after_s = (finish_order(host, client, notes, "cursor_item_returned") if (admitted and not under.get("done"))
               else None)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"cursor_item_returned: host never idle: {short(e)}")
    end = {"clip": {"host": clip in items_by_id(host), "client": clip in items_by_id(client)},
           "H": status_both(host, client, H_ID)}
    end["instantOff"] = both(host, client, {"cmd": "set_option", "name": "battleInstantGrenade", "value": False},
                             ("ok",))["ok"]
    evidence("cursor_item_returned", {"staging": st, "stagedDiff": staged, "ui": ev,
                                      "order": {k: v for k, v in order.items() if k != "t0"},
                                      "under": under, "release": rel, "afterReleaseS": after_s, "end": end,
                                      "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"cursor_item_returned: buckets differ after the staging: {staged}")
    if not opened:
        fails.append(f"precondition (cursor_item_returned): the host's inventory did not open on H ({ev})")
    elif not picked:
        fails.append(f"precondition (cursor_item_returned): the host's click on the clip's ground cell did not put "
                     f"{clip} on the cursor ({ev.get('pick')}, ground {ev.get('ground')})")
    elif not admitted:
        fails.append(f"precondition (cursor_item_returned): the client's throw was not admitted ({order})")
    else:
        # the blast removes the clip on both and the host's screen returns the cursor with the partner's
        # item_missing text (when broken the throw is frozen and the clip still on the host's cursor)
        if not under.get("done"):
            fails.append(f"cursor_item_returned: the clip {clip} was not gone on both with the host's cursor returned "
                         f"under the open "
                         f"inventory within {ORDER_UNDER_S} s (cursor {(under.get('view') or {}).get('selectedItem')}, "
                         f"clip present {under.get('clip')}, {under.get('frozen')})")
        else:
            if under.get("tops") != ["InventoryState"]:
                fails.append(f"cursor_item_returned: the host's tops while the throw ran {under.get('tops')} (want "
                             f"only InventoryState)")
            dr = dnum(hscr(before["host"]).get("cursorReturned"), hscr({"hostScreens": under.get("hostScreens")}).get(
                "cursorReturned"))
            if dr != 1:
                fails.append(f"cursor_item_returned: host hostScreens.cursorReturned +{dr} (want +1)")
            if under.get("invLastWarning") != TEXT_ITEM_MISSING:
                fails.append(f"cursor_item_returned: host invLastWarning {under.get('invLastWarning')!r} (want "
                             f"{TEXT_ITEM_MISSING!r})")
            hh = under.get("H") or {}
            if any((hh.get(n) or {}).get("status") != 0 or (hh.get(n) or {}).get("isOut") for n in ("host", "client")):
                fails.append(f"cursor_item_returned: H after the blast {hh} (want conscious on both)")
    if end["clip"] != {"host": False, "client": False}:
        fails.append(f"cursor_item_returned: the clip at the row's end {end['clip']} (want gone on both)")
    fails += hs_common_fails(host, client, before, crash0, "cursor_item_returned")
    finish(fails)


# ===================== knockout rows =====================


def ko_stage(host, client, target, st):
    """The knockout staging: the target's health KO_HEALTH, no stun, no fatal wound; a fresh stun rod on C
    (clear_hands) on KO_C_TILE facing it; C's TU max."""
    st["targetSet"] = set_state_both(host, client, target, health=KO_HEALTH, stun=0, fatalWounds=[0] * 6)
    st["rod"] = give_hands(host, client, C_ID, STUN_ROD)
    st["C"] = place_host_first(host, client, C_ID, KO_C_TILE, KO_C_DIR)
    st["cTu"] = cs.set_tu_both(host, client, C_ID, TU_MAX)


def melee_req(rod, target):
    return {"cmd": "battle_intent", "kind": "melee", "actor": C_ID,
            "plan": {"weapon": rod, "target": jt(KO_T_TILE), "terrainPart": 0, "targetUnit": target,
                     "targetPos": jt(KO_T_TILE)}}


def box_moment(host):
    """The host's stack, probes and box texts at the moment a box is on top."""
    return {"stack": stack(host), "hostScreens": event_state(host).get("hostScreens"), "texts": box_texts(host)}


def knockout_closes_inventory(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"dial": ensure_dial(host, client, BOOT_DIAL), "H": restage_h(host, client, KO_T_TILE, "belt_and_ground",
                                                                         placer=place_host_first)}
    ko_stage(host, client, H_ID, st)
    st["C2"] = place_host_first(host, client, C2_ID, C2_TILE, C2_DIR)
    st["c2Tu"] = cs.set_tu_both(host, client, C2_ID, TU_MAX)
    st["c2Lane"] = {k: v for k, v in host.cmd({"cmd": "path_probe", "unit": C2_ID, "x": C2_DEST[0], "y": C2_DEST[1],
                                                  "z": C2_DEST[2]}).items() if k in ("ok", "reachable", "steps", "error")}
    staged = settle(host, client)
    g, rod = st["H"]["ids"]["grenade"], st["rod"]
    ev = {}
    before = snap_hs(host, client)
    opened = open_host_inventory(host, H_ID, ev)
    picked = host_pick(host, ev, "pick", BELT, 1, 0, g) if opened else False
    order, admitted, leg1, leg2, box = {}, False, {}, {}, []

    def down_and_box():
        return unconscious_both(host, client, H_ID) and top(host) == "InfoboxOKState"
    if opened and picked:
        host.ok({"cmd": "set_seed", "seed": SEED_KO})
        order, admitted = send_order(host, client, melee_req(rod, H_ID), before)
        if admitted:
            leg1 = wait_under(host, client, down_and_box, KO_UNDER_S, order["t0"], "InventoryState")
            if leg1["done"]:
                leg1["moment"] = box_moment(host)
            else:
                leg1["frozen"] = frozen_sample(host, client, C_ID)
                leg1["H"] = status_both(host, client, H_ID)
    # a frozen melee's cleanup: the cursor back, the inventory closed, the melee released; then the box shows
    rel = []
    if admitted and not leg1.get("done"):
        rel = release(host, notes, "knockout_closes_inventory leg 1")
        leg1["afterRelease"] = {"boxWaited": wait_until(lambda: top(host) == "InfoboxOKState", BOX_WAIT_S, 0.05)[1]}
        leg1["afterRelease"]["moment"] = box_moment(host)
    # leg 2: a partner walk with the box on top
    if top(host) == "InfoboxOKState":
        leg2["meleeClosed"], leg2["meleeCloseWaited"] = wait_until(
            lambda: event_state(host).get("busyOwnerSeat") == -1 and not battle_state(host).get("isBusy"),
            MELEE_CLOSE_S, 0.05)
        b2 = snap_hs(host, client)
        o2, a2 = send_order(host, client, walk_req(C2_ID, C2_DEST), b2)
        leg2.update({"order": {k: v for k, v in o2.items() if k != "t0"}, "admitted": a2})
        leg2.update(wait_under(host, client, walk_done_fn(host, client, C2_ID, C2_DEST, b2["host"]["closedContexts"]),
                               HS_WALK_UNDER_S, o2["t0"], "InfoboxOKState"))
        leg2["topAfter"] = top(host)
        leg2["C2"] = {"host": pos(host, C2_ID), "client": pos(client, C2_ID)}
    dismiss_host_box(host, box)
    rel += release(host, notes, "knockout_closes_inventory")
    after_s = finish_order(host, client, notes, "knockout_closes_inventory", box)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"knockout_closes_inventory: host never idle: {short(e)}")
    end = {"H": status_both(host, client, H_ID), "grenade": item_both(host, client, g),
           "C2": {"host": pos(host, C2_ID), "client": pos(client, C2_ID)}}
    evidence("knockout_closes_inventory", {"staging": st, "stagedDiff": staged, "ui": ev,
                                           "order": {k: v for k, v in order.items() if k != "t0"},
                                           "leg1": leg1, "leg2": leg2, "box": box, "release": rel,
                                           "afterReleaseS": after_s, "end": end, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"knockout_closes_inventory: buckets differ after the staging: {staged}")
    if not (st["c2Lane"].get("reachable") and st["c2Lane"].get("steps") == 3):
        fails.append(f"precondition (knockout_closes_inventory leg 2): C2's lane {C2_TILE} -> {C2_DEST} {st['c2Lane']} "
                     f"(want reachable, 3 steps)")
    if not opened:
        fails.append(f"precondition (knockout_closes_inventory): the host's inventory did not open on H ({ev})")
    elif not picked:
        fails.append(f"precondition (knockout_closes_inventory): the host's click on belt (1,0) did not pick H's "
                     f"grenade {g} ({ev})")
    elif not admitted:
        fails.append(f"precondition (knockout_closes_inventory): the client's melee was not admitted ({order})")
    else:
        # leg 1: the inventory closes first, then the box shows (when broken the melee is frozen, H conscious, no box)
        if not leg1.get("done"):
            fails.append(f"knockout_closes_inventory leg 1: H was not knocked out with the host's box on top within "
                         f"{KO_UNDER_S} s (H {leg1.get('H')}, {leg1.get('frozen')})")
        else:
            m = leg1.get("moment") or {}
            if "InventoryState" in (m.get("stack") or []):
                fails.append(f"knockout_closes_inventory leg 1: the host's stack when the box showed {m.get('stack')} "
                             f"(want no InventoryState: the inventory closes before the box)")
            du = dnum(hclose(before["host"], "byReason", "unit_out"), hclose({"hostScreens": m.get("hostScreens")},
                                                                               "byReason", "unit_out"))
            di = dnum(hclose(before["host"], "byScreen", "inventory"), hclose({"hostScreens": m.get("hostScreens")},
                                                                                "byScreen", "inventory"))
            if (du, di) != (1, 1):
                fails.append(f"knockout_closes_inventory leg 1: host hostScreens.closes byReason.unit_out +{du}, "
                             f"byScreen.inventory +{di} (want +1 / +1)")
            if not any(TEXT_UNCONSCIOUS in (t or "") for t in m.get("texts") or []):
                fails.append(f"knockout_closes_inventory leg 1: the host's box texts {m.get('texts')} (want "
                             f"{TEXT_UNCONSCIOUS!r})")
        # leg 2: the partner's walk runs under the box
        if not leg2:
            fails.append(f"knockout_closes_inventory leg 2: no host box on top to walk under ({leg1})")
        elif not leg2.get("admitted"):
            fails.append(f"knockout_closes_inventory leg 2: C2's walk was not admitted under the host's box "
                         f"({leg2.get('order')})")
        elif not leg2.get("done") or leg2.get("tops") != ["InfoboxOKState"]:
            fails.append(f"knockout_closes_inventory leg 2: C2's walk did not end with the host's box still on top "
                         f"within {HS_WALK_UNDER_S} s (C2 {leg2.get('C2')}, tops {leg2.get('tops')})")
        want = {"onTile": True, "tx": KO_T_TILE[0], "ty": KO_T_TILE[1], "tz": KO_T_TILE[2], "owner": -1}
        for n in ("host", "client"):
            if {k: (end["grenade"][n] or {}).get(k) for k in want} != want:
                fails.append(f"knockout_closes_inventory: the {n}'s grenade {end['grenade'][n]} (want among H's "
                             f"dropped items {want})")
    if not unconscious_both(host, client, H_ID):
        fails.append(f"knockout_closes_inventory: H at the row's end {end['H']} (want unconscious on both)")
    fails += hs_common_fails(host, client, before, crash0, "knockout_closes_inventory")
    finish(fails)


def knockout_closes_menu(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"dial": ensure_dial(host, client, BOOT_DIAL),
          "H2": place_host_first(host, client, H2_ID, KO_T_TILE, KO_T_DIR),
          "H2stripped": strip_both(host, client, H2_ID)}
    st["H2rifle"] = give(host, client, H2_ID, RIFLE, "right")
    st["h2Tu"] = cs.set_tu_both(host, client, H2_ID, TU_MAX)
    ko_stage(host, client, H2_ID, st)
    staged = settle(host, client)
    rod = st["rod"]
    ev = {}
    before = snap_hs(host, client)
    opened = False
    try:
        ev["menu"] = open_hand_menu_unit(host, H2_ID)
        opened = top(host) == "ActionMenuState"
    except Exception as e:
        notes.append(f"knockout_closes_menu: the host's action menu on H2: {short(e)}")
    ev["stack"] = stack(host)
    order, admitted, under, box = {}, False, {}, []

    def down_and_box():
        return unconscious_both(host, client, H2_ID) and top(host) == "InfoboxOKState"
    if opened:
        host.ok({"cmd": "set_seed", "seed": SEED_KO})
        order, admitted = send_order(host, client, melee_req(rod, H2_ID), before)
        if admitted:
            under = wait_under(host, client, down_and_box, KO_UNDER_S, order["t0"], "ActionMenuState")
            if under["done"]:
                under["moment"] = box_moment(host)
            else:
                under["frozen"] = frozen_sample(host, client, C_ID)
                under["H2"] = status_both(host, client, H2_ID)
    dismiss_host_box(host, box)
    rel = release(host, notes, "knockout_closes_menu")
    after_s = finish_order(host, client, notes, "knockout_closes_menu", box)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"knockout_closes_menu: host never idle: {short(e)}")
    end = {"H2": status_both(host, client, H2_ID)}
    evidence("knockout_closes_menu", {"staging": st, "stagedDiff": staged, "ui": ev,
                                      "order": {k: v for k, v in order.items() if k != "t0"},
                                      "under": under, "box": box, "release": rel, "afterReleaseS": after_s,
                                      "end": end, "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"knockout_closes_menu: buckets differ after the staging: {staged}")
    if not opened:
        fails.append(f"precondition (knockout_closes_menu): the host's ActionMenuState did not open on H2 ({ev})")
    elif not admitted:
        fails.append(f"precondition (knockout_closes_menu): the client's melee was not admitted ({order})")
    elif not under.get("done"):
        fails.append(f"knockout_closes_menu: H2 was not knocked out with the host's box on top within {KO_UNDER_S} s "
                     f"(H2 {under.get('H2')}, {under.get('frozen')})")
    else:
        m = under.get("moment") or {}
        if "ActionMenuState" in (m.get("stack") or []):
            fails.append(f"knockout_closes_menu: the host's stack when the box showed {m.get('stack')} (want no "
                         f"ActionMenuState)")
        da = dnum(hclose(before["host"], "byScreen", "action_menu"), hclose({"hostScreens": m.get("hostScreens")},
                                                                              "byScreen", "action_menu"))
        du = dnum(hclose(before["host"], "byReason", "unit_out"), hclose({"hostScreens": m.get("hostScreens")},
                                                                           "byReason", "unit_out"))
        if (da, du) != (1, 1):
            fails.append(f"knockout_closes_menu: host hostScreens.closes byScreen.action_menu +{da}, byReason.unit_out "
                         f"+{du} (want +1 / +1)")
    if not unconscious_both(host, client, H2_ID):
        fails.append(f"knockout_closes_menu: H2 at the row's end {end['H2']} (want unconscious on both)")
    fails += hs_common_fails(host, client, before, crash0, "knockout_closes_menu")
    finish(fails)


def knockout_covered_detach(host, client, ctx):
    notes = []
    crash0 = crash_census()
    st = {"dial": ensure_dial(host, client, BOOT_DIAL),
          "H3": place_host_first(host, client, H3_ID, KO_T_TILE, KO_T_DIR),
          "H3stripped": strip_both(host, client, H3_ID)}
    st["H3rifle"] = give(host, client, H3_ID, RIFLE, "right")
    st["h3Tu"] = cs.set_tu_both(host, client, H3_ID, TU_MAX)
    ko_stage(host, client, H3_ID, st)
    staged = settle(host, client)
    rod = st["rod"]
    ev = {}
    opened = open_host_inventory(host, H3_ID, ev)
    cov = {}
    covered = cover_inventory(host, cov) if opened else False
    ev["cover"] = cov
    before = snap_hs(host, client)
    hmark = log_mark(host)
    order, admitted, under, closing, box = {}, False, {}, {}, []
    if opened and covered:
        host.ok({"cmd": "set_seed", "seed": SEED_KO})
        order, admitted = send_order(host, client, melee_req(rod, H3_ID), before)
        if admitted:
            under = wait_under(host, client, lambda: unconscious_both(host, client, H3_ID), KO_UNDER_S,
                               order["t0"], top(host))
            if under["done"]:
                # the host check runs at the pump after the driven step that put H3 down
                cd0 = hscr(before["host"]).get("coveredDetach") or 0
                _, under["detachWaited"] = wait_until(
                    lambda: (hscr(event_state(host)).get("coveredDetach") or 0) > cd0, 1.5, 0.05)
            under["moment"] = {"stack": stack(host), "hostScreens": event_state(host).get("hostScreens"),
                               "H3": status_both(host, client, H3_ID)}
            if under["done"]:
                # the box (if any) dismissed, then the cover closed; the uncovered inventory closes itself
                wait_until(lambda: top(host) == "InfoboxOKState", 3.0, 0.05)
                dismiss_host_box(host, box)
                time.sleep(KEY_SETTLE_S)
                closing["stackBefore"] = stack(host)
                if "UfopaediaStartState" in closing["stackBefore"][-1:]:
                    press(host, read_key(host.user_dir, CLOSE_KEY))
                    got, closing["invGoneWaited"] = wait_until(lambda: "InventoryState" not in stack(host), 3.0, 0.05)
                    closing["invGone"] = bool(got)
                closing["stackAfter"] = stack(host)
                closing["hostScreens"] = event_state(host).get("hostScreens")
                closing["hostAlive"] = host.proc is not None and host.proc.poll() is None
            else:
                under["frozen"] = frozen_sample(host, client, C_ID)
    rel = release(host, notes, "knockout_covered_detach")
    after_s = finish_order(host, client, notes, "knockout_covered_detach", box)
    dismiss_host_box(host, box)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"knockout_covered_detach: host never idle: {short(e)}")
    end = {"H3": status_both(host, client, H3_ID)}
    evidence("knockout_covered_detach", {"staging": st, "stagedDiff": staged, "ui": ev,
                                         "order": {k: v for k, v in order.items() if k != "t0"},
                                         "under": under, "closing": closing, "box": box, "release": rel,
                                         "afterReleaseS": after_s, "end": end, "hostUi": ui_lines(host, hmark)[-12:],
                                         "notes": notes})
    fails = list(notes)
    if staged:
        fails.append(f"knockout_covered_detach: buckets differ after the staging: {staged}")
    if not opened:
        fails.append(f"precondition (knockout_covered_detach): the host's inventory did not open on H3 ({ev})")
    elif not covered:
        fails.append(f"SETUP-FAILURE (the cover recipe on the host): the host's keyGeoUfopedia did not cover its "
                     f"inventory ({cov})")
    elif not admitted:
        fails.append(f"precondition (knockout_covered_detach): the client's melee was not admitted ({order})")
    elif not under.get("done"):
        # when broken the melee is frozen under the covering screen and H3 stays conscious
        fails.append(f"knockout_covered_detach: H3 was not knocked out under the host's covered inventory within "
                     f"{KO_UNDER_S} s (H3 {(under.get('moment') or {}).get('H3')}, {under.get('frozen')})")
    else:
        m = under.get("moment") or {}
        dcd = dnum(hscr(before["host"]).get("coveredDetach"), hscr({"hostScreens": m.get("hostScreens")}).get(
            "coveredDetach"))
        if dcd != 1:
            fails.append(f"knockout_covered_detach: host hostScreens.coveredDetach +{dcd} while covered (want +1; "
                         f"stack {m.get('stack')})")
        if not closing.get("hostAlive", True):
            fails.append(f"knockout_covered_detach: the host died after the cover closed ({closing})")
        du = dnum(hclose(before["host"], "byReason", "unit_out"), hclose({"hostScreens": closing.get("hostScreens")},
                                                                           "byReason", "unit_out"))
        di = dnum(hclose(before["host"], "byScreen", "inventory"), hclose({"hostScreens": closing.get("hostScreens")},
                                                                            "byScreen", "inventory"))
        if (du, di) != (1, 1) or not closing.get("invGone"):
            fails.append(f"knockout_covered_detach: after the cover closed: host closes byReason.unit_out +{du}, "
                         f"byScreen.inventory +{di}, "
                         f"InventoryState gone {closing.get('invGone')} (want +1 / +1 / true; {closing})")
    if not unconscious_both(host, client, H3_ID):
        fails.append(f"knockout_covered_detach: H3 at the row's end {end['H3']} (want unconscious on both)")
    fails += hs_common_fails(host, client, before, crash0, "knockout_covered_detach")
    finish(fails)


SCENARIOS = (("walk_under_inventory", walk_under_inventory), ("walk_under_pause", walk_under_pause),
             ("walk_under_unit_info", walk_under_unit_info), ("walk_under_medikit", walk_under_medikit),
             ("inventory_refreshes", inventory_refreshes), ("cursor_item_returned", cursor_item_returned),
             ("knockout_closes_inventory", knockout_closes_inventory), ("knockout_closes_menu", knockout_closes_menu),
             ("knockout_covered_detach", knockout_covered_detach))


# ===================== bring-up =====================


def boot(host, client):
    """test_inventory_held.boot (test_inventory.boot plus the held-inventory probes), then a check that both
    machines report the host-screen probes (hostCovered, hostScreens)."""
    ctx = held.boot(host, client)
    for gc in (host, client):
        es = event_state(gc)
        hc, hs = es.get("hostCovered"), es.get("hostScreens")
        assert (isinstance(hc, dict) and isinstance(hc.get("byOrigin"), dict) and isinstance(hs, dict)
                and isinstance(hs.get("closes"), dict) and "coveredDetach" in hs), (
            f"{gc.name} event_state lacks the host-screen probes: hostCovered={hc!r} hostScreens={hs!r}")
    d = xcom_dial_of(host)
    assert d == BOOT_DIAL, f"the boot's seat-1 xcom dial {d} (want {BOOT_DIAL})"
    print(f"[host-screens] boot ok: hostCovered={event_state(host).get('hostCovered')} "
          f"hostScreens={event_state(host).get('hostScreens')}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49950, make_user_dir("host_screens_host", options=OPTS))
    client = GameClient("client", 49951, make_user_dir("host_screens_client", options=OPTS))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            t_row = time.time()
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
            print(f"[host-screens] row {name} wall {time.time() - t_row:.1f}s", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[host-screens] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_host_screens: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
