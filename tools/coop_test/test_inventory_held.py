"""test_inventory_held.py: parallel mode, the in-battle inventory while an action runs (held placements), the host's
own inventory changes reaching the second player at once (the host `sync`), and the client's inventory screen closing
by itself when its soldier goes down, when the side changes and when the battle ends (the force-close).

Boot 1 = test_inventory.boot (the roster-pinned terror boot, paperdoll option on both). Rows in this order, every row
ONE run, every row restages (unit_out_closes kills C2 and battle_end_closes ends the battle, so battle_end_closes is
last):
  held_same_unit: a held placement on the same unit. The shot window: the host's H fires a snap shot at fire dial 1.
      The client opens C's inventory; on the client's first `shot` cue it picks the grenade (belt (1,0)) and drops it
      on STR_LEFT_HAND: lastDeny busy, coopPendingIntent {inv_move, C}, invLastWarning = the held text,
      invWarningWrites +1, the grenade on the cursor. Then a second drop on belt (2,0): invGuard.last {site drop, op
      move, decision held}, counts.held +1, invWarningWrites +1 and invLastWarning the held text again,
      coopIntentsSent.inv_move unchanged by it. After the host's end the held order resubmits and is admitted:
      grenade STR_LEFT_HAND owner C, C TU 60 on both, the cursor empty; EQUAL. When broken: the second drop's
      invGuard.last.decision is "inflight" and invGuard.counts.held +0.
  right_click_cancels_held: a right-click cancels a held order. The same first drop, then a right-click:
      coopPendingIntent null, the cursor empty, the grenade STR_BELT (1,0) on both; after the host's end nothing
      resubmits (coopIntentsSent.inv_move +1 over the row, no inv_move context), invWarningWrites +1 over the row;
      EQUAL.
  held_walk_blocks_drop: a held walk blocks a placement (an order of another kind). On the cue: a client walk order
      for C2 -> lastDeny busy, coopPendingIntent {walk, C2}; then the client opens C's inventory and drops the
      grenade on STR_LEFT_HAND: invGuard.last decision held, nothing sent, invLastWarning the held text,
      invWarningWrites +1, coopPendingIntent {walk, C2} unchanged; after the host's end C2 stands on the walk's
      destination on both and the grenade is still on the cursor; a right-click returns it (STR_BELT (1,0) on both);
      EQUAL. When broken: the drop is sent (invGuard.last decision sent, coopIntentsSent.inv_move +1) and the walk
      is lost; after the host's end the grenade moves and C2 stays.
  partner_walk_under_host_screen: the host inventory latch with the partner's walk RUNNING under the host's screen
      (the host camera on the walk lane's middle (11,27,0) and the client's xcom dial 40, so the walk lasts ~2.3 s).
      Host opens H's inventory; a client walk order for C (12,26,0) -> (9,29,0) is admitted (host
      contextsOpened.intent +1, isBusy); inside the walk the host moves H's grenade belt (1,0) -> STR_LEFT_HAND with
      real clicks; both machines are sampled until the walk is over or WALK_UNDER_S. The latch: pending true after
      the drop, sets.move +1, heldByGate > 0 while the walk's context is open. Passes when, while the host's
      inventory_view.open is still true, the walk's context is closed, C stands on (9,29,0) on both and the client
      holds H's grenade STR_LEFT_HAND and H TU 58 - 4 (the walk's evs carried H's change). Then the host closes:
      pending false, emptyFlushes +>= 1, host syncEvsEmitted +0 over the row; EQUAL. The client's dial goes back to
      its boot value at the row's end. When broken (the walk frozen under the host's screen): C still on (12,26,0)
      and the client's H grenade still STR_BELT (1,0) after the window.
  side_change_closes: the side change closes the client's screen. The client opens C's inventory and picks the
      grenade; client END TURN ready; host END TURN. Passes when invForcedCloses.byReason.side +1, no InventoryState
      on the client's stack at the flip, inventory_view.open false, the grenade STR_BELT (1,0) on both; during the
      alien side the client's INVENTORY key opens nothing (inventory_view.open false, coopWaitText unchanged). Turn 2
      through test_turn_baton.drive_full_cycle; EQUAL. When broken: at the client's side flip inventory_view.open is
      true (NextTurnState above it) and invForcedCloses.count +0; the row's cleanup then acts on the rebound screen:
      inventory_cursor_clear, then battle_close_inventory (a no-op when the screen is gone).
  host_placement_sync: host placement sync, in two steps. Open and close only: the host opens and closes H's
      inventory with no placement: sets.close +1, emptyFlushes +1, host syncEvsEmitted +0 (when broken sets.close
      +0). The move: the host moves H's grenade belt (1,0) -> STR_LEFT_HAND with real clicks and both machines are
      sampled with the host's screen open: sets.move +1, host syncEvsEmitted +1, client syncEvsApplied +1, H's
      grenade STR_LEFT_HAND and H TU 58 - 4 on both while the screen is open (when broken host syncEvsEmitted +0 and
      the client's H grenade still STR_BELT (1,0)). The heal step; EQUAL.
  host_reload_key: host reload key. H: rifle (no clip) STR_RIGHT_HAND, clip belt (0,0); host TAB-selects H and presses
      its reload key. Passes when sets.reload +1, host syncEvsEmitted +1, rifle ammo [clip, r, r, r] and H's TU
      equal on both before any other host ev. When broken: host syncEvsEmitted +0, the client's rifle ammo [r, r, r]
      while the host's is [clip, r, r, r]. The heal step; EQUAL.
  battle_end_closes: battle end with the client's screen open. The client opens C's inventory and picks the grenade;
      the host aborts (test_battle_end.end_host_abort). Passes when byReason.battle_end +1 and
      inventoryOpenAtTeardown false. When broken: client battleEnd.inventoryOpenAtTeardown true,
      invForcedCloses.byReason.battle_end +0. Either way: the client's top = the display-only DebriefingState within
      DEBRIEF_S, no new crash file, host battleEnd.emitted 1 and evsAfter 0, exactly one client `[coop-ui] pop ...
      InventoryState` line. Never reads inventory_view after the teardown.
Boot 2 (alone, because when broken its row ends the client):
  unit_out_closes: unit out under an open screen. C2 on (4,32,0), stripped, a grenade belt (1,0); the client opens
      C2's inventory and picks the grenade; host battle_action kill_unit_real {C2}. No click (the unit may be dead).
      Passes when there is no crash file, the force-close fires no later than the first applied ev after which C2 is
      out or has no tile (its InventoryState pop line precedes the next applied ev),
      invForcedCloses.byReason.unit_out +1, C2 dead on both, the grenade where the host's evs put it on both; EQUAL.
      When broken: the client dies within 5 s (a new crash log, the client process gone) - a named FAIL carrying the
      crash log's exception line.
Boot 3 (alone, like boot 2, because when broken its row ends the client):
  covered_unit_out: a COVERED client inventory whose soldier goes down. C2 on (4,32,0) dir 6, stripped, a grenade
      belt (1,0), TU 58; the client opens C2's inventory and covers it with the inventory's Ufopaedia key
      (keyGeoUfopedia from its options.cfg -> UfopaediaStartState); host battle_action kill_unit_real {C2}; then the
      client closes the cover (keyCancel). Passes when invForcedCloses.coveredDetach +1 while covered,
      byReason.unit_out +1 after the close, no InventoryState on the client, no crash file, C2 dead on both; EQUAL.
      When broken: the client dies within 5 s of the close (a new crash log, Inventory.cpp:378 via
      InventoryState::think; the client process gone) - a named FAIL carrying the crash log's exception line.
The heal step (tail of host_placement_sync and host_reload_key, not a row): the client turns C one octant; its
context's evs carry whatever host change the client still lacks. EVIDENCE prints that context's evs with their delta
shapes. Then EQUAL.

Common asserts (after wait_host_idle): hash_now full EQUAL; desyncSeen false on both; client coopClientBStatePushes
unchanged and host 0; client invLocalWrites 0; host inventory_view.open false; client invGuard as the row names it.

Constants: measured values (tiles, max TU, timing windows; each block below quotes what was measured). Item ids come
from each row's staging record, never literals. Every staging command pair goes to the CLIENT first, except the
teleports partner_walk_under_host_screen and covered_unit_out stage (host leg first, checked, then the client leg;
place_host_first). Each row prints ONE "EVIDENCE <id>:" line with both machines' fields before its conditions are
checked; every row runs after an earlier failure; "PASS <id>" / "FAIL <id>: <message>". Exit 0 only when every row
passes, 2 otherwise (a bring-up failure is also 2). One run is the result; run it in the foreground to completion.

Run:  python tools/coop_test/test_inventory_held.py
"""

import datetime
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import harness
import session
from session import battle_state, event_state, assert_hash_clean
import test_inventory as inv
from test_inventory import (C_ID, H_ID, BELT, LH, RIFLE, RIFLE_CLIP, PISTOL_CLIP, GRENADE, STAGE_H, ROW_DIR,
                               OPTS, TU_MAX, C_TU_MAX, TU_BELT_TO_HAND, stack, units, inv_view, selected, click,
                               pick, right_click_return, close_client, open_client, open_fails, order_done,
                               evidence, finish, wait_until, iview, count_of, new_contexts, guard_counts,
                               guard_last, common_fails, item_fails, tu_fails, give, drop, give_primed,
                               read_inventory_key, rec_view)
from test_delta_core import diff_buckets, short
from test_delta_items import items_by_id, unit_view
from test_host_combat import evs_since, ev_tuples
from test_client_items import strip_both
import test_client_shoot as cs
from test_turn_baton import drive_full_cycle, dismiss_next_turn_if_present
from test_seat_pacing import tab_select
from test_thin_client_tripwire import read_reload_key
from test_battle_end import end_host_abort, DEBRIEF_S

# ----- units and TU (test_inventory.py C_ID / H_ID / SEATED; measured max TU) -----
C2_ID = 9                         # test_inventory.py SEATED [8, 9]
H_TU_MAX = 58                     # measured: "Max TU C 64, H 58"
C2_TU_MAX = 58                    # measured: C2 "TU 58"
STATUS_DEAD = 6                   # src/Mod/Unit.h UnitStatus (test_host_combat.py STATUS_DEAD)
STATUS_UNCONSCIOUS = 7

# ----- the host's shot window (held_same_unit, right_click_cancels_held, held_walk_blocks_drop), measured: "fire dial
# 1 on seat 0 (wait_seat_dial); H (14,24,0) dir 2, rifle + clip via give_both; set_seed 1 before each fire;
# battle_fire snap at (34,24,0), tuCost 14 (impact tile (40,25,0)); C belt_and_ground on STAGE_C (2,33,0) (window A) /
# (0,34,0) (window B); C2 (4,32,0) dir 6, walk dest (1,32,0)"; window 8775-10206 ms (3 boots) >= 3 x the longest
# in-window sequence 814 ms -----
FIRE_DIAL = 1
FIRE_SEED = 1
FIRE_MODE = "snap"
H_FIRE_TILE, H_FIRE_DIR = (14, 24, 0), 2
H_FIRE_TARGET = (34, 24, 0)
FIRE_TU = 14
HELD_SAME_UNIT_TILE = (2, 33, 0)  # window A (STAGE_C)
RIGHT_CLICK_TILE = (0, 33, 0)     # no measured second-window tile: test_inventory's open_and_look tile (an empty open
                                  # row tile), so C never teleports onto its own tile
HELD_WALK_TILE = (0, 34, 0)       # window B
C2_TILE, C2_DIR = (4, 32, 0), 6   # measured for held_walk_blocks_drop and unit_out_closes
C2_DEST = (1, 32, 0)              # 3 tiles west along y=32
# ----- partner_walk_under_host_screen, measured: "C tele (12,26,0) dir 2, TU 64; walk dest (9,29,0) (read_lane, dir
# 5); H = the host_placement_sync staging; H's grenade belt (1,0) -> STR_LEFT_HAND"; when broken the walk froze 0.124 s
# after the send and host lastSeqEmitted and syncEvsEmitted stayed flat for 4.56 s -----
PARTNER_WALK_C_TILE, PARTNER_WALK_C_DIR = (12, 26, 0), 2
PARTNER_WALK_DEST = (9, 29, 0)
PARTNER_WALK_SAMPLE_S = 0.1
# ----- the on-screen partner walk, measured: "C (12,26,0) dir 2 -> (9,29,0) 3 tiles / (10,28,0) 2 tiles; host camera
# battle_camera_center (11,27,0) (on-screen) + client battleXcomSpeed 40 + wait_seat_dial(seat 1, "xcom", 40)";
# "on-screen dial 40: 3 tiles 2339 ms, 2 tiles 1554-1559 ms (3 boots); off-screen walks run at interval 0 (~270 ms) at
# any dial; longest host sequence inside a window = partner_walk_under_host_screen's pick+drop 202 ms".
# Every walk-window row pins the camera and the dial. -----
LANE_MID = (11, 27, 0)            # the host camera's centre for an on-screen partner walk
WALK_DIAL = 40                    # the client's battleXcomSpeed = seat 1's xcom dial (CoopSpeed)
WALK_UNDER_S = 6.0                # a 3-tile walk (2339 ms uncovered) must end under the host's screen within this;
                                  # a covered BattlescapeState steps at most once per frame, so > 2.5 x
KEY_SETTLE_S = 0.3                # a key injected right after a state opens is lost
# ----- covered_unit_out, measured: "C2 (4,32,0) dir 6, stripped, grenade belt (1,0), TU 58; client opens C2's
# inventory; cover = keyGeoUfopedia 117 (UfopaediaStartState, 0.102 s), close = keyCancel 27"; when broken: "covered
# client inventory, host kill_unit_real {C2} -> notOnTop +2, then closing the cover crashes the client 0.527 s later
# (Inventory.cpp:378 via InventoryState::think)". The keys are read from the machine's own options.cfg (117 and 27
# when measured). -----
COVER_KEY = "keyGeoUfopedia"      # InventoryState :227 (_btnOk -> btnUfopaediaClick)
CLOSE_KEY = "keyCancel"           # UfopaediaStartState :114 (_btnOk -> btnOkClick)
COVER_WAIT_S = 2.0                # measured: covered 0.102 s after the key
# ----- host_placement_sync, measured: "restage_h STAGE_H (48,24,0) dir 2, belt_and_ground, H TU 58" -----
# ----- side_change_closes, measured: "C belt_and_ground on (1,33,0) dir 2"; when broken the client stack at the flip
# is [.., BattlescapeState, InventoryState, NextTurnState] and at turn 2 the screen rebinds to C2 with C's grenade on
# the cursor --
SIDE_CHANGE_TILE = (1, 33, 0)
TURN0 = 1                         # the boot's first player turn (battle_state.turn at bring-up)
# ----- battle_end_closes, measured: "C belt_and_ground on STAGE_C (2,33,0); host abort + dismiss_popup"; the client's
# display-only DebriefingState 0.103 s after the confirm -----
BATTLE_END_TILE = (2, 33, 0)
# ----- unit_out_closes, measured: "C2 (4,32,0) dir 6, stripped, grenade belt (1,0), TU 58; host kill_unit_real
# {C2}"; when broken "the client dies within 5 s of the host kill_unit_real" -----
CRASH_WATCH_S = 5.0

# ----- texts (en-US; exact text) -----
TEXT_HELD = "Please wait for HostPlayer's action to finish"   # showPending's STR_COOP_WAIT_FOR_PLAYER_ACTION; the
                                                               # measured invLastWarning at the busy deny

# ----- waits -----
CUE_WAIT_S = 30.0                 # the host's fire -> the client's first shot cue (measured: 124 ms)
DENY_WAIT_S = 3.0                 # measured: the busy deny 125-315 ms after the cue
CLICK_WAIT_S = 2.0
ORDER_TIMEOUT_S = 30.0            # the window (<= 10.2 s) plus the held order's resubmit / walk
FREEZE_WAIT_S = 5.0               # when broken the walk froze 0.124 s after its send
WALK_WAIT_S = 15.0
FLIP_WAIT_S = 30.0
SYNC_WAIT_S = 3.0                 # measured: the no-sync negative control sampled at 0 s and 3 s
LATCH_WAIT_S = 2.0                # the close latch runs at ~InventoryState, one frame after the pop
KEY_READ_S = 0.5                  # a text is read within 0.5 s of the press

HELD_PROBE_KEYS = ("invHostDirty", "invForcedCloses", "invWarningWrites", "syncEvsEmitted", "syncEvsApplied",
                   "contextsOpened", "cueCounts", "battleEnd", "deltaEvsEmitted")


# ===================== probes =====================


def probes_held(gc):
    """test_inventory.probes()' keys plus the held-inventory probes (HELD_PROBE_KEYS)."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in inv.PROBE_KEYS + HELD_PROBE_KEYS}


def snap_held(host, client):
    return {"host": probes_held(host), "client": probes_held(client)}


def collect_held(host, client, seq0):
    rec = inv.collect(host, client, seq0)
    rec["host"], rec["client"] = probes_held(host), probes_held(client)
    return rec


def held_of(p):
    return (((p or {}).get("invGuard") or {}).get("counts") or {}).get("held")


def dirty(p):
    return (p or {}).get("invHostDirty") or {}


def dirty_sets(p, k):
    return (dirty(p).get("sets") or {}).get(k)


def forced(p):
    return (p or {}).get("invForcedCloses") or {}


def forced_reason(p, k):
    return (forced(p).get("byReason") or {}).get(k)


def dnum(a, b):
    """b - a for two probe numbers (None when either is missing: the probe is absent)."""
    return (b - a) if isinstance(a, int) and isinstance(b, int) else None


def client_ui(client):
    ec, bc = event_state(client), battle_state(client)
    return {"lastDeny": ec.get("lastDeny"), "pending": bc.get("coopPendingIntent"), "cursor": selected(client),
            "invLastWarning": ec.get("invLastWarning"), "invWarningWrites": ec.get("invWarningWrites"),
            "invGuard": ec.get("invGuard"), "sent": ec.get("coopIntentsSent"), "inFlight": ec.get("inFlight"),
            "banner": bc.get("coopWaitText")}


def item_both(host, client, iid):
    return {"host": iview(items_by_id(host), iid), "client": iview(items_by_id(client), iid)}


def unit_pos(gc, uid):
    u = units(gc).get(uid) or {}
    return (u.get("x"), u.get("y"), u.get("z"))


def ms_since(t0):
    return round((time.time() - t0) * 1000)


# ===================== logs + crash files =====================

TS_RE = re.compile(r"^\[(\d\d-\d\d-\d{4}_\d\d-\d\d-\d\d\.\d{3})\]")
DELTA_RE = re.compile(r"\[coop-delta\] attached to seq (\d+) kind=(\S+) \((\d+) bytes\): (.*)$")


def log_path(gc):
    return os.path.join(gc.user_dir, "openxcom.log")


def log_mark(gc):
    try:
        return os.path.getsize(log_path(gc))
    except OSError:
        return 0


def log_lines_since(gc, mark):
    try:
        with open(log_path(gc), "rb") as f:
            f.seek(mark)
            data = f.read()
        return data.decode("utf-8", errors="replace").splitlines()
    except OSError as e:
        return [f"unreadable: {e}"]


def ts_of(line):
    m = TS_RE.match(line)
    if not m:
        return None
    return datetime.datetime.strptime(m.group(1), "%d-%m-%Y_%H-%M-%S.%f").timestamp()


def deltas_since(gc, mark):
    out = {}
    for ln in log_lines_since(gc, mark):
        m = DELTA_RE.search(ln)
        if not m:
            continue
        seq = int(m.group(1))
        txt = m.group(4)
        try:
            d = json.loads(txt)
        except ValueError:
            d = {"_truncated": txt[:400]}
        out[seq] = {"ts": ts_of(ln), "kind": m.group(2), "bytes": int(m.group(3)), "delta": d}
    return out


def delta_shape(d):
    """{class: ids (units/items/tiles) or keys (battle)} of one delta."""
    if not isinstance(d, dict):
        return d
    s = {}
    for k, v in d.items():
        if k == "battle" and isinstance(v, dict):
            s[k] = sorted(v.keys())
        elif isinstance(v, list):
            s[k] = [({"id": e.get("id"), "f": sorted(x for x in e.keys() if x != "id")}
                     if isinstance(e, dict) else e) for e in v]
        else:
            s[k] = v
    return s


def crash_files():
    """Every crash_*.log (session._crash_log_snapshot) and every .dmp, in this harness slot's own crash folder and
    under this slot's own user dirs (never another slot's)."""
    hits = set(session._crash_log_snapshot())
    for root in (harness.CRASH_DIR, os.path.join(harness.TEST_ROOT, "s%d_*" % harness.HARNESS_SLOT)):
        hits |= set(glob.glob(os.path.join(root, "**", "*.dmp"), recursive=True))
    return hits


def crash_exception_lines(paths):
    """The exception line of each new crash_*.log (the `SEH exception ...` / `Code =` line)."""
    out = {}
    for p in sorted(paths):
        if not p.endswith(".log"):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                hit = [ln.strip() for ln in f if "exception" in ln.lower() or "Code =" in ln]
            out[os.path.basename(p)] = hit[:2]
        except OSError as e:
            out[os.path.basename(p)] = [f"unreadable: {e}"]
    return out


def ui_lines(gc, mark, needle="[coop-ui] p"):
    return [ln for ln in log_lines_since(gc, mark) if needle in ln]


# ===================== staging (client first) =====================


def settle(host, client):
    session.wait_host_idle(host, client, timeout=30)
    return diff_buckets(host, client)


def restage_c(host, client, key, tile):
    """test_inventory.restage (kit belt_and_ground) with C's tile for this file's row `key` (a measured tile)."""
    inv.ROW_TILE[key] = tile
    return inv.restage(host, client, key, "belt_and_ground")


def place_host_first(host, client, uid, tile, d):
    """test_client_shoot.place (re-entrant: a unit already on the tile on both keeps its facing) with the HOST leg
    first and checked, then the client leg: a host refusal (e.g. "not STATUS_STANDING") never leaves the client
    teleported alone (both() sends the client first). The tile's own check is the teleport command's refusal. Only
    for player units: a host-first teleport of an ALIEN makes the host's next reveal ev carry state the client
    lacks."""
    uh, uc = units(host).get(uid) or {}, units(client).get(uid) or {}
    if all((u.get("x"), u.get("y"), u.get("z")) == tuple(tile) for u in (uh, uc)):
        return {"kept": tuple(tile), "dir": (uh.get("direction"), uc.get("direction"))}
    req = {"cmd": "battle_teleport_unit", "unit": uid, "x": tile[0], "y": tile[1], "z": tile[2], "dir": d}
    rh = host.cmd(dict(req))
    assert rh.get("ok"), f"staging {req}: the host leg refused ({rh}); the client leg was not sent"
    rc = client.cmd(dict(req))
    assert rc.get("ok"), f"staging {req}: the client leg refused ({rc}) after the host's ok ({rh})"
    assert (rh.get("to"), rh.get("dir")) == (rc.get("to"), rc.get("dir")), (
        f"staging {req} differs: host={(rh.get('to'), rh.get('dir'))} client={(rc.get('to'), rc.get('dir'))}")
    session.wait_seq_barrier(host, client)
    return {"teleported": tuple(tile), "dir": rh.get("dir")}


def read_key(user_dir, name):
    """Options::<name> as the process wrote it to its own options.cfg (test_inventory.read_inventory_key's pattern
    for any key)."""
    with open(os.path.join(user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        m = re.search(r"^\s*" + name + r":\s*(-?\d+)\s*$", f.read(), re.M)
    assert m, f"PREMISE: no {name} in {user_dir}/options.cfg"
    return int(m.group(1))


def xcom_dial_of(gc, seat=1):
    """Seat `seat`'s xcom dial in this machine's co-op speed table (event_state `speed`)."""
    ent = [s for s in ((event_state(gc).get("speed") or {}).get("seats") or []) if s.get("seat") == seat]
    return ent[0].get("xcom") if ent else None


def set_xcom_dial(host, client, value):
    """The partner's walk pace is seat 1's xcom dial: set it on the client and wait until both tables hold it."""
    client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": value})
    return cs.wait_seat_dial(host, client, 1, "xcom", value)


def camera_lane(host, tile=LANE_MID):
    """The host camera on the partner's walk lane (battle_camera_center, camera-only), so the walk steps at the
    dial's pace instead of UnitWalkBState's off-screen interval 0."""
    r = host.cmd({"cmd": "battle_camera_center", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert r.get("ok"), f"battle_camera_center {tile} failed on the host: {r}"
    return {k: r.get(k) for k in ("centerX", "centerY", "centerZ", "viewLevel")}


def cover_inventory(gc, rec):
    """The inventory's Ufopaedia key (keyGeoUfopedia from `gc`'s own options.cfg) puts UfopaediaStartState over
    the open InventoryState (KEY_SETTLE_S after the screen opened: a key sent sooner is lost). Fills `rec`; returns
    True when the InventoryState is on the stack and another state is on top of it."""
    time.sleep(KEY_SETTLE_S)
    key = read_key(gc.user_dir, COVER_KEY)
    rec["key"] = key
    gc.ok({"cmd": "inject_input", "kind": "key", "key": key})
    got, dt = wait_until(lambda: (lambda s: "InventoryState" in s and s[-1] != "InventoryState")(stack(gc)),
                         COVER_WAIT_S, 0.02)
    rec["covered"], rec["waited"], rec["stack"] = bool(got), dt, stack(gc)
    return bool(got)


def restage_h(host, client, tile, kit, placer=None):
    """test_inventory.restage for unit H, copied: kit "belt_and_ground" (rifle RH, rifle clip belt (0,0), grenade
    belt (1,0), primed grenade belt (3,0), a rifle clip and a pistol clip on the tile) or "load_rifle" (rifle RH with
    no clip, rifle clip belt (0,0)). The teleport is test_client_shoot.place (re-entrant: a unit already on the tile
    is not teleported onto it) instead of tele_both; the walk-window rows pass `placer=place_host_first`."""
    rec = {"tile": tile}
    rec["place"] = (placer or cs.place)(host, client, H_ID, tile, ROW_DIR)
    rec["stripped"] = strip_both(host, client, H_ID)
    ids = {}
    if kit == "belt_and_ground":
        ids["rifle"] = give(host, client, H_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, H_ID, RIFLE_CLIP, BELT, 0, 0)
        ids["grenade"] = give(host, client, H_ID, GRENADE, BELT, 1, 0)
        ids["primed"] = give_primed(host, client, H_ID, 3, 0)
        ids["groundClip"] = drop(host, client, tile, RIFLE_CLIP)
        ids["groundPistolClip"] = drop(host, client, tile, PISTOL_CLIP)
    elif kit == "load_rifle":
        ids["rifle"] = give(host, client, H_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, H_ID, RIFLE_CLIP, BELT, 0, 0)
    else:
        raise AssertionError(f"unknown kit {kit!r}")
    rec["ids"] = ids
    rec["tu"] = cs.set_tu_both(host, client, H_ID, TU_MAX)
    return rec


def staged_fails(rec, diff, tu_want, who):
    fails = []
    if diff:
        fails.append(f"buckets differ after the staging: {diff} (want none)")
    if rec["tu"] != tu_want:
        fails.append(f"precondition: {who}'s TU after the staging {rec['tu']} (want {tu_want})")
    return fails


def ensure_closed_safe(client, notes):
    """A client inventory an earlier row left open: its cursor item returned through inventory_cursor_clear (no
    click: never a click on a screen whose unit may be dead), then closed when it is the top state (a
    battle_close_inventory under another state would pop that state). Recorded, never silent."""
    v = inv_view(client)
    if not v.get("open"):
        return None
    rec = {"view": {k: v.get(k) for k in ("top", "unitId", "selectedItem")}}
    rec["cursorClear"] = client.cmd({"cmd": "inventory_cursor_clear"})
    if v.get("top"):
        r = client.cmd({"cmd": "battle_close_inventory"})
        got, _ = wait_until(lambda: "InventoryState" not in stack(client), CLICK_WAIT_S)
        rec["close"] = {"ok": r.get("ok"), "error": r.get("error"), "closed": bool(got)}
    else:
        rec["close"] = f"not closed: not the top state (stack {stack(client)})"
    notes.append(f"an earlier row left the client's inventory open: {rec}")
    return rec


# ===================== the host's shot window =====================


def fire_setup(host, client):
    """The measured staging for H's shot; re-entrant per row."""
    rec = {}
    host.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": FIRE_DIAL})
    dial = cs.wait_seat_dial(host, client, 0, "fire", FIRE_DIAL)
    rec["dial"] = {n: [s for s in (v or []) if s.get("seat") == 0] for n, v in dial.items()}
    rec["hRifle"], rec["hClip"] = cs.give_both(host, client, H_ID, RIFLE, RIFLE_CLIP)
    rec["hPlace"] = cs.place(host, client, H_ID, H_FIRE_TILE, H_FIRE_DIR)
    rec["hTu"] = cs.set_tu_both(host, client, H_ID, TU_MAX)
    return rec


def client_cue_shot(client):
    return (event_state(client).get("cueCounts") or {}).get("shot") or 0


def fire_and_cue(host, client, win):
    """Host set_seed + battle_fire snap; returns the time of the client's first `shot` cue (None: no cue)."""
    cue0 = client_cue_shot(client)
    host.ok({"cmd": "set_seed", "seed": FIRE_SEED})
    t_fire = time.time()
    rf = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": FIRE_MODE, "x": H_FIRE_TARGET[0],
                   "y": H_FIRE_TARGET[1], "z": H_FIRE_TARGET[2]})
    win["fire"] = {k: rf.get(k) for k in ("ok", "error", "tuCost")}
    got, _ = wait_until(lambda: client_cue_shot(client) > cue0, CUE_WAIT_S, 0.01)
    win["cue"] = {"ok": bool(got), "fireToCueMs": ms_since(t_fire)}
    return time.time() if got else None


def fire_fails(win, what):
    fails = []
    f = win.get("fire") or {}
    if not f.get("ok") or f.get("tuCost") != FIRE_TU:
        fails.append(f"precondition ({what}): host battle_fire {f} (want ok, tuCost {FIRE_TU})")
    if not (win.get("cue") or {}).get("ok"):
        fails.append(f"precondition ({what}): no client `shot` cue within {CUE_WAIT_S} s of the fire ({win.get('cue')})")
    return fails


def first_drop(client, ev, win, g, before):
    """In the window: pick the grenade (belt (1,0)), drop it on STR_LEFT_HAND, wait for the busy deny."""
    t_cue = win["tCue"]
    picked = pick(client, ev, "pick", BELT, 1, 0, g)
    win["pickMs"] = ms_since(t_cue)
    if not picked:
        return False
    ev["drop1"] = click(client, slot=LH, x=0, y=0)
    ld0 = before["client"]["lastDeny"]

    def denied():
        ld = event_state(client).get("lastDeny")
        return ld if (ld != ld0 and (ld or {}).get("reason") == "busy") else None
    dn, _ = wait_until(denied, DENY_WAIT_S, 0.02)
    win["denyMs"] = ms_since(t_cue)
    win["busyDeny"] = dn
    win["atDeny"] = client_ui(client)
    return True


def first_drop_fails(win, g, before, what):
    """The first drop inside the window: denied busy and held (the item stays on the cursor)."""
    fails = []
    a = win.get("atDeny") or {}
    if not win.get("busyDeny"):
        fails.append(f"precondition ({what}): the first drop was not denied busy within {DENY_WAIT_S} s inside the "
                     f"host's shot window (client lastDeny {a.get('lastDeny')})")
    p = a.get("pending") or {}
    if p.get("kind") != "inv_move" or p.get("actorId") != C_ID:
        fails.append(f"{what}: client coopPendingIntent after the busy deny {a.get('pending')} (want {{kind inv_move, "
                     f"actorId {C_ID}}})")
    if a.get("cursor") != g:
        fails.append(f"{what}: client selectedItem after the busy deny {a.get('cursor')} (want the grenade {g})")
    if a.get("invLastWarning") != TEXT_HELD:
        fails.append(f"{what}: client invLastWarning after the busy deny {a.get('invLastWarning')!r} "
                     f"(want {TEXT_HELD!r})")
    d = dnum(before["client"]["invWarningWrites"], a.get("invWarningWrites"))
    if d != 1:
        fails.append(f"{what}: client invWarningWrites +{d} at the busy deny (want +1: the held text written)")
    return fails


def wait_order(host, client, notes, timeout=ORDER_TIMEOUT_S):
    got, dt = wait_until(lambda: order_done(host, client), timeout, 0.1)
    if not got:
        notes.append(f"the host's action and the held order never finished in {timeout} s")
    return dt


def guard_decision_fails(g_after, want_last, what):
    gl = (g_after or {}).get("last") or {}
    got = {k: gl.get(k) for k in want_last}
    return [] if got == want_last else [f"{what}: client invGuard.last {gl} (want {want_last})"]


# ===================== rows =====================


def held_same_unit(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    ws = fire_setup(host, client)
    st = restage_c(host, client, "held_same_unit", HELD_SAME_UNIT_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    win = {}
    opened = open_client(client, ev)
    dropped = False
    if opened:
        win["tCue"] = fire_and_cue(host, client, win)
        if win["tCue"]:
            dropped = first_drop(client, ev, win, g, before)
            if dropped:
                g1 = (win["atDeny"].get("invGuard") or {}).get("counts") or {}
                ev["drop2"] = click(client, slot=BELT, x=2, y=0)
                _, win["drop2Waited"] = wait_until(
                    lambda: ((event_state(client).get("invGuard") or {}).get("counts") or {}) != g1, CLICK_WAIT_S)
                win["drop2Ms"] = ms_since(win["tCue"])
                win["afterDrop2"] = client_ui(client)
        win["orderWait"] = wait_order(host, client, notes)
        win["endCursor"] = selected(client)
        close_client(client, ev)
    win.pop("tCue", None)
    rec = collect_held(host, client, seq0)
    evidence("held_same_unit", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "ui": ev, "window": win,
                                "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if not opened:
        fails += open_fails(ev, "held_same_unit")
        finish(fails + common_fails(host, client, before, {}, None, "held_same_unit"))
    fails += fire_fails(win, "held_same_unit")
    if not dropped:
        fails.append(f"held_same_unit: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the "
                     f"cursor (want the grenade {g})")
    else:
        fails += first_drop_fails(win, g, before, "held_same_unit")
        a, b = win["atDeny"], win.get("afterDrop2") or {}
        # when broken the second drop gets a silent `inflight`; otherwise `held`
        fails += guard_decision_fails(b.get("invGuard"), {"site": "drop", "op": "move", "decision": "held",
                                                           "itemId": g, "actorId": C_ID}, "held_same_unit second drop")
        dh = dnum(held_of(a), held_of(b))
        if dh != 1:
            fails.append(f"held_same_unit second drop: client invGuard.counts.held {held_of(a)} -> {held_of(b)} (want "
                         f"+1)")
        dw = dnum(a.get("invWarningWrites"), b.get("invWarningWrites"))
        if dw != 1 or b.get("invLastWarning") != TEXT_HELD:
            fails.append(f"held_same_unit second drop: client invWarningWrites +{dw}, invLastWarning "
                         f"{b.get('invLastWarning')!r} (want +1 and {TEXT_HELD!r}: the held text shown again)")
        if count_of(b.get("sent"), "inv_move") != count_of(a.get("sent"), "inv_move"):
            fails.append(f"held_same_unit second drop: client coopIntentsSent {a.get('sent')} -> {b.get('sent')} (want "
                         f"inv_move unchanged: nothing sent)")
        if b.get("cursor") != g:
            fails.append(f"held_same_unit second drop: client selectedItem {b.get('cursor')} (want the grenade {g})")
        # after the host's end: the held order resubmitted and admitted
        new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
        mv = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "inv_move" and c.get("actorId") == C_ID]
        if len(mv) != 1:
            fails.append(f"held_same_unit: host closedContexts gained {len(mv)} {{intent, inv_move, {C_ID}}} (want 1: "
                         f"the resubmitted held order; new contexts {new})")
        if win.get("endCursor") != -1:
            fails.append(f"held_same_unit: client selectedItem after the resubmit's answer {win.get('endCursor')} "
                         f"(want -1)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": LH, "onTile": False}, "held_same_unit")
        fails += tu_fails(rec, C_TU_MAX - TU_BELT_TO_HAND, "held_same_unit")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "held", "itemId": g, "actorId": C_ID},
                          "held_same_unit")
    finish(fails)


def right_click_cancels_held(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    ws = fire_setup(host, client)
    st = restage_c(host, client, "right_click_cancels_held", RIGHT_CLICK_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    win = {}
    opened = open_client(client, ev)
    dropped = returned = False
    if opened:
        win["tCue"] = fire_and_cue(host, client, win)
        if win["tCue"]:
            dropped = first_drop(client, ev, win, g, before)
            if dropped:
                returned = right_click_return(client, ev, "rightClick", BELT, 1, 0)
                win["rightClickMs"] = ms_since(win["tCue"])
                win["afterRightClick"] = client_ui(client)
                win["grenadeAfterRightClick"] = item_both(host, client, g)
        win["orderWait"] = wait_order(host, client, notes)
        close_client(client, ev)
    win.pop("tCue", None)
    rec = collect_held(host, client, seq0)
    evidence("right_click_cancels_held", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "ui": ev, "window": win,
                                          "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if not opened:
        fails += open_fails(ev, "right_click_cancels_held")
        finish(fails + common_fails(host, client, before, {}, None, "right_click_cancels_held"))
    fails += fire_fails(win, "right_click_cancels_held")
    want_belt = {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
    if not dropped:
        fails.append(f"right_click_cancels_held: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on "
                     f"the cursor (want the grenade {g})")
    else:
        fails += first_drop_fails(win, g, before, "right_click_cancels_held")
        r = win.get("afterRightClick") or {}
        if not returned or r.get("cursor") != -1:
            fails.append(f"right_click_cancels_held: client selectedItem after the right-click {r.get('cursor')} (want "
                         f"-1)")
        if r.get("pending") is not None:
            fails.append(f"right_click_cancels_held: client coopPendingIntent after the right-click {r.get('pending')} "
                         f"(want null: the held order cancelled)")
        for m in ("host", "client"):
            got = {k: ((win.get("grenadeAfterRightClick") or {}).get(m) or {}).get(k) for k in want_belt}
            if got != want_belt:
                fails.append(f"right_click_cancels_held: {m} grenade after the right-click "
                             f"{win['grenadeAfterRightClick'][m]} (want {want_belt})")
        new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
        mv = [c for c in new if c.get("kind") == "inv_move"]
        if mv:
            fails.append(f"right_click_cancels_held: host closedContexts gained inv_move context(s) {mv} (want none: "
                         f"nothing resubmits)")
        ds = count_of(rec["client"]["coopIntentsSent"], "inv_move") - count_of(
            before["client"]["coopIntentsSent"], "inv_move")
        if ds != 1:
            fails.append(f"right_click_cancels_held: client coopIntentsSent.inv_move +{ds} over the row (want +1: the "
                         f"first send only)")
        dw = dnum(before["client"]["invWarningWrites"], rec["client"]["invWarningWrites"])
        if dw != 1:
            fails.append(f"right_click_cancels_held: client invWarningWrites +{dw} over the row (want +1: the first "
                         f"drop's held text)")
        fails += item_fails(rec, g, want_belt, "right_click_cancels_held")
        fails += tu_fails(rec, C_TU_MAX, "right_click_cancels_held")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID},
                          "right_click_cancels_held")
    finish(fails)


def held_walk_blocks_drop(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    ws = fire_setup(host, client)
    st = restage_c(host, client, "held_walk_blocks_drop", HELD_WALK_TILE)
    st["c2Place"] = cs.place(host, client, C2_ID, C2_TILE, C2_DIR)
    st["c2Tu"] = cs.set_tu_both(host, client, C2_ID, TU_MAX)
    occ = {(u["x"], u["y"], u["z"]) for u in battle_state(host)["units"] if not u.get("isOut")}
    lane = [(C2_TILE[0] - i, C2_TILE[1], C2_TILE[2]) for i in (1, 2, 3)]
    st["laneOpen"] = [session.tile_is_open_ground(host, t[0], t[1], t[2], occ - {tuple(C2_TILE)}) for t in lane]
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    win = {}
    opened = picked = False
    win["tCue"] = fire_and_cue(host, client, win)
    if win["tCue"]:
        rw = client.cmd({"cmd": "battle_intent", "kind": "walk", "actor": C2_ID,
                         "dest": {"x": C2_DEST[0], "y": C2_DEST[1], "z": C2_DEST[2]}})
        win["walk"] = {k: rw.get(k) for k in ("ok", "iseq", "error")}
        ld0 = before["client"]["lastDeny"]

        def denied():
            ld = event_state(client).get("lastDeny")
            return ld if (ld != ld0 and (ld or {}).get("reason") == "busy") else None
        win["busyDeny"], _ = wait_until(denied, DENY_WAIT_S, 0.02)
        win["walkDenyMs"] = ms_since(win["tCue"])
        win["atWalkDeny"] = client_ui(client)
        opened = open_client(client, ev)
        if opened:
            picked = pick(client, ev, "pick", BELT, 1, 0, g)
            if picked:
                win["beforeDrop"] = client_ui(client)
                g1 = (win["beforeDrop"].get("invGuard") or {}).get("counts") or {}
                ev["drop"] = click(client, slot=LH, x=0, y=0)
                _, win["dropWaited"] = wait_until(
                    lambda: ((event_state(client).get("invGuard") or {}).get("counts") or {}) != g1, CLICK_WAIT_S)
                win["dropMs"] = ms_since(win["tCue"])
                win["afterDrop"] = client_ui(client)
    win["orderWait"] = wait_order(host, client, notes)
    win["endCursor"] = selected(client) if opened else None
    win["c2End"] = {"host": unit_pos(host, C2_ID), "client": unit_pos(client, C2_ID)}
    if opened and win["endCursor"] == g:
        right_click_return(client, ev, "rightClick", BELT, 1, 0)
    if opened:
        close_client(client, ev)
    win.pop("tCue", None)
    rec = collect_held(host, client, seq0)
    evidence("held_walk_blocks_drop", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "ui": ev, "window": win,
                                       "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if st["c2Tu"] != C2_TU_MAX or not all(st["laneOpen"]):
        fails.append(f"precondition: C2 TU {st['c2Tu']} (want {C2_TU_MAX}), lane {lane} open {st['laneOpen']}")
    fails += fire_fails(win, "held_walk_blocks_drop")
    wd = win.get("atWalkDeny") or {}
    if not win.get("busyDeny") or (wd.get("pending") or {}).get("kind") != "walk" or \
            (wd.get("pending") or {}).get("actorId") != C2_ID:
        fails.append(f"precondition (held_walk_blocks_drop): the walk for C2 was not held busy inside the window "
                     f"(lastDeny "
                     f"{wd.get('lastDeny')}, coopPendingIntent {wd.get('pending')}; want {{kind walk, actorId {C2_ID}}})")
    if not opened:
        fails += open_fails(ev, "held_walk_blocks_drop")
    elif not picked:
        fails.append(f"held_walk_blocks_drop: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on "
                     f"the cursor (want the grenade {g})")
    else:
        b0, b1 = win.get("beforeDrop") or {}, win.get("afterDrop") or {}
        # when broken the drop is sent and the walk is lost; otherwise the drop is held
        fails += guard_decision_fails(b1.get("invGuard"), {"site": "drop", "op": "move", "decision": "held",
                                                           "itemId": g, "actorId": C_ID}, "held_walk_blocks_drop drop")
        if count_of(b1.get("sent"), "inv_move") != count_of(b0.get("sent"), "inv_move"):
            fails.append(f"held_walk_blocks_drop drop: client coopIntentsSent {b0.get('sent')} -> {b1.get('sent')} "
                         f"(want inv_move unchanged: nothing sent)")
        p = b1.get("pending") or {}
        if p.get("kind") != "walk" or p.get("actorId") != C2_ID:
            fails.append(f"held_walk_blocks_drop drop: client coopPendingIntent after the drop {b1.get('pending')} "
                         f"(want {{kind walk, actorId {C2_ID}}} unchanged: the held walk kept)")
        dw = dnum(b0.get("invWarningWrites"), b1.get("invWarningWrites"))
        if dw != 1 or b1.get("invLastWarning") != TEXT_HELD:
            fails.append(f"held_walk_blocks_drop drop: client invWarningWrites +{dw}, invLastWarning "
                         f"{b1.get('invLastWarning')!r} (want +1 and {TEXT_HELD!r})")
        # after the host's end
        if win["c2End"] != {"host": C2_DEST, "client": C2_DEST}:
            fails.append(f"held_walk_blocks_drop: C2 after the host's end {win['c2End']} (want {C2_DEST} on both: the "
                         f"held walk resubmitted)")
        if win.get("endCursor") != g:
            fails.append(f"held_walk_blocks_drop: client selectedItem after the host's end {win.get('endCursor')} "
                         f"(want the grenade {g} still on the cursor: nothing was sent for it)")
        if (ev.get("rightClick") or {}).get("cursor") != -1:
            fails.append(f"held_walk_blocks_drop: the right-click {ev.get('rightClick')} (want the cursor -1)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                            "held_walk_blocks_drop")
        fails += tu_fails(rec, C_TU_MAX, "held_walk_blocks_drop")
    fails += common_fails(host, client, before, {},
                          {"site": "drop", "op": "move", "decision": "held", "itemId": g, "actorId": C_ID},
                          "held_walk_blocks_drop")
    dh = dnum(held_of(before["client"]), held_of(rec["client"]))
    if dh != 1:
        fails.append(f"held_walk_blocks_drop: client invGuard.counts.held +{dh} over the row (want +1)")
    finish(fails)


def partner_walk_under_host_screen(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    hst = restage_h(host, client, STAGE_H, "belt_and_ground", placer=place_host_first)
    ct = place_host_first(host, client, C_ID, PARTNER_WALK_C_TILE, PARTNER_WALK_C_DIR)
    ctu = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    gh = hst["ids"]["grenade"]
    ev = {"leftover": leftover, "cPlace": ct, "cTu": ctu}
    # the walk steps at the dial's pace only when it is on-screen on the host
    dial0 = xcom_dial_of(host)
    ev["camera"] = camera_lane(host)
    ev["dial"] = {"boot": dial0, "set": WALK_DIAL, "tables": set_xcom_dial(host, client, WALK_DIAL)}
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ro = host.cmd({"cmd": "battle_open_inventory", "unit": H_ID})
    ev["hostOpen"] = {k: ro.get(k) for k in ("ok", "opened", "error")}
    hv = inv_view(host)
    ev["hostOpenView"] = {k: hv.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    host_open = bool(ro.get("opened")) and hv.get("top") is True and hv.get("unitId") == H_ID
    admitted = picked = dropped = False
    samples = []
    done = None
    if host_open:
        cc0 = before["host"]["closedContexts"]
        t_send = time.time()
        rw = client.cmd({"cmd": "battle_intent", "kind": "walk", "actor": C_ID,
                         "dest": {"x": PARTNER_WALK_DEST[0], "y": PARTNER_WALK_DEST[1], "z": PARTNER_WALK_DEST[2]}})
        ev["walk"] = {k: rw.get(k) for k in ("ok", "iseq", "error")}
        ci0 = (before["host"]["contextsOpened"] or {}).get("intent") or 0

        def is_admitted():
            ci = (event_state(host).get("contextsOpened") or {}).get("intent") or 0
            return ci > ci0 and battle_state(host).get("isBusy")
        admitted, ev["admitWaited"] = wait_until(is_admitted, FREEZE_WAIT_S, 0.02)
        ev["admitted"] = {"ok": bool(admitted), "hostContextsOpened": event_state(host).get("contextsOpened"),
                          "C": {"host": unit_pos(host, C_ID), "client": unit_pos(client, C_ID)}}
        if admitted:
            ev["pick"] = click(host, slot=BELT, x=1, y=0)
            picked, _ = wait_until(lambda: selected(host) == gh, CLICK_WAIT_S, 0.02)
            ev["pick"]["cursor"] = selected(host)
            if picked:
                ev["drop"] = click(host, slot=LH, x=0, y=0)
                dropped, _ = wait_until(lambda: selected(host) == -1, CLICK_WAIT_S, 0.02)
                ev["drop"]["cursor"] = selected(host)
                ev["drop"]["msAfterSend"] = ms_since(t_send)
                ev["hostInvGuard"] = event_state(host).get("invGuard")
            # sample both machines until the walk is over (its context closed, C on the destination on both, the
            # client caught up) or WALK_UNDER_S after the send - the host's screen stays open throughout
            while time.time() - t_send < WALK_UNDER_S:
                eh, ec = event_state(host), event_state(client)
                hvs = inv_view(host)
                walk_ctx = [c for c in new_contexts(cc0, eh.get("closedContexts")) if c.get("origin") == "intent"
                            and c.get("kind") == "walk" and c.get("actorId") == C_ID]
                s = {"t": round(time.time() - t_send, 2), "hostSeq": eh.get("lastSeqEmitted"),
                     "clientApplied": ec.get("lastSeqApplied"), "hostSync": eh.get("syncEvsEmitted"),
                     "invHostDirty": eh.get("invHostDirty"), "isBusy": battle_state(host).get("isBusy"),
                     "C": {"host": unit_pos(host, C_ID), "client": unit_pos(client, C_ID)},
                     "walkCtx": walk_ctx, "hostScreenOpen": hvs.get("open"), "hostScreenTop": hvs.get("top"),
                     "clientH": {"grenade": iview(items_by_id(client), gh), "tu": inv.tu_of(client, H_ID)}}
                samples.append(s)
                if (walk_ctx and s["C"] == {"host": PARTNER_WALK_DEST, "client": PARTNER_WALK_DEST}
                        and s["clientApplied"] == s["hostSeq"] and ec.get("queueDepth") == 0):
                    done = s
                    break
                time.sleep(PARTNER_WALK_SAMPLE_S)
        rc = host.cmd({"cmd": "battle_close_inventory"})
        gone, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
        ev["hostClose"] = {"ok": rc.get("ok"), "error": rc.get("error"), "gone": bool(gone),
                           "msAfterSend": ms_since(t_send)}
        arrived, ev["walkWaited"] = wait_until(lambda: unit_pos(host, C_ID) == PARTNER_WALK_DEST
                                               and unit_pos(client, C_ID) == PARTNER_WALK_DEST, WALK_WAIT_S)
        ev["walkArrived"] = bool(arrived)
        try:
            session.wait_host_idle(host, client, timeout=30)
        except Exception as e:
            notes.append(f"partner_walk_under_host_screen: host never idle after the walk: {short(e)}")
        # the pump consumer's pass after the walk's context closed (a no-op wait while the latch is clear)
        _, ev["latchClearWaited"] = wait_until(lambda: dirty(probes_held(host)).get("pending") is False, LATCH_WAIT_S)
    try:
        ev["dialBack"] = set_xcom_dial(host, client, dial0) if dial0 is not None else "no boot dial read"
    except Exception as e:
        notes.append(f"partner_walk_under_host_screen: the client's dial did not go back to {dial0}: {short(e)}")
    rec = collect_held(host, client, seq0)
    evidence("partner_walk_under_host_screen",
             {"staging": {"H": hst, "C": ct}, "stagedDiff": staged, "ui": ev, "samples": samples,
              "doneUnderScreen": done,
              "hostDirty": {"before": before["host"]["invHostDirty"], "after": rec["host"]["invHostDirty"]},
              "hostSync": (before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"]),
              "row": rec_view(before, rec, {"hGrenade": gh}), "notes": notes})
    fails = list(notes) + staged_fails(hst, staged, H_TU_MAX, "H")
    if ctu != C_TU_MAX:
        fails.append(f"precondition: C's TU after the staging {ctu} (want {C_TU_MAX})")
    if not host_open:
        fails.append(f"precondition: the host's inventory did not open on H ({ev['hostOpen']}, {ev['hostOpenView']})")
    elif not admitted:
        fails.append(f"precondition: C's walk was not admitted under the host's screen ({ev.get('admitted')}, "
                     f"walk {ev.get('walk')})")
    elif not (picked and dropped):
        fails.append(f"partner_walk_under_host_screen: the host's clicks did not move H's grenade belt (1,0) -> "
                     f"STR_LEFT_HAND (pick {ev.get('pick')}, drop {ev.get('drop')})")
    else:
        d0 = before["host"]["invHostDirty"] or {}
        after_drop = [s for s in samples if s["t"] * 1000 >= (ev["drop"].get("msAfterSend") or 0)]
        first = after_drop[0] if after_drop else None
        open_ctx = [s for s in samples if not s["walkCtx"]]
        held_open = [dnum(d0.get("heldByGate"), dirty(s).get("heldByGate")) for s in open_ctx]
        # the latch: set by the drop, held by the gate while the walk's context is open
        if not first or dirty(first).get("pending") is not True:
            fails.append(f"partner_walk_under_host_screen: host invHostDirty.pending at the first sample after the "
                         f"drop {dirty(first).get('pending') if first else None} (want true)")
        dm = dnum(dirty_sets(before["host"], "move"), dirty_sets(rec["host"], "move"))
        if dm != 1:
            fails.append(f"partner_walk_under_host_screen: host invHostDirty.sets.move +{dm} (want +1)")
        held_ints = [h for h in held_open if isinstance(h, int)]
        if not held_ints or max(held_ints) <= 0:
            fails.append(f"partner_walk_under_host_screen: host invHostDirty.heldByGate while the walk's context was "
                         f"open {held_open} (want > 0)")
        # when broken the walk is frozen under the host's screen; otherwise it runs to its end while the host's
        # screen is open, and its evs carry H's change
        if done is None:
            last = samples[-1] if samples else {}
            fails.append(f"partner_walk_under_host_screen: the walk did not end under the host's open inventory within "
                         f"{WALK_UNDER_S} s of the "
                         f"send (last sample: C {last.get('C')}, walk context closed {bool(last.get('walkCtx'))}, "
                         f"host screen open {last.get('hostScreenOpen')}, client H {last.get('clientH')})")
        else:
            if done["hostScreenOpen"] is not True:
                fails.append(f"partner_walk_under_host_screen: the walk ended with the host's inventory_view.open "
                             f"{done['hostScreenOpen']} (want true: under the screen)")
            cg = done["clientH"]["grenade"] or {}
            if {k: cg.get(k) for k in ("owner", "slot")} != {"owner": H_ID, "slot": LH}:
                fails.append(f"partner_walk_under_host_screen: the client's H grenade when the walk ended under the "
                             f"host's screen {cg} (want "
                             f"owner {H_ID} slot {LH}: the walk's evs carried the host's change)")
            if done["clientH"]["tu"] != H_TU_MAX - TU_BELT_TO_HAND:
                fails.append(f"partner_walk_under_host_screen: the client's H TU when the walk ended under the host's "
                             f"screen {done['clientH']['tu']} (want {H_TU_MAX - TU_BELT_TO_HAND})")
        if not ev.get("walkArrived"):
            fails.append(f"partner_walk_under_host_screen: C did not reach {PARTNER_WALK_DEST} on both (host "
                         f"{unit_pos(host, C_ID)}, client {unit_pos(client, C_ID)})")
        da = rec["host"]["invHostDirty"] or {}
        if da.get("pending") is not False:
            fails.append(f"partner_walk_under_host_screen: host invHostDirty.pending after the walk "
                         f"{da.get('pending')} (want false)")
        de = dnum((d0 or {}).get("emptyFlushes"), da.get("emptyFlushes"))
        if not isinstance(de, int) or de < 1:
            fails.append(f"partner_walk_under_host_screen: host invHostDirty.emptyFlushes +{de} over the row (want >= "
                         f"1: the walk's evs carried H's change)")
        dsync = dnum(before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"])
        if dsync != 0:
            fails.append(f"partner_walk_under_host_screen: host syncEvsEmitted +{dsync} over the row (want +0)")
        ih, ic = iview(rec["ih"], gh), iview(rec["ic"], gh)
        want = {"owner": H_ID, "slot": LH, "onTile": False}
        for m, it in (("host", ih), ("client", ic)):
            if {k: (it or {}).get(k) for k in want} != want:
                fails.append(f"partner_walk_under_host_screen: {m} H grenade {it} (want {want})")
        th, tc = (rec["uh"].get(H_ID) or {}).get("tu"), (rec["uc"].get(H_ID) or {}).get("tu")
        if (th, tc) != (H_TU_MAX - TU_BELT_TO_HAND,) * 2:
            fails.append(f"partner_walk_under_host_screen: H tu host={th} client={tc} (want "
                         f"{H_TU_MAX - TU_BELT_TO_HAND} on both)")
    fails += common_fails(host, client, before, {}, None, "partner_walk_under_host_screen")
    finish(fails)


def dismiss_nts_all(gc):
    """Every NextTurnState on `gc`'s stack, top first, through the REAL close() path
    (test_turn_baton.dismiss_next_turn_if_present): one pass over the counted states."""
    n = sum(1 for s in stack(gc) if s == "NextTurnState")
    out = []
    for _ in range(n):
        out.append(dismiss_next_turn_if_present(gc))
    return {"counted": n, "closed": out, "stack": stack(gc)}


def side_change_closes(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = restage_c(host, client, "side_change_closes", SIDE_CHANGE_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = pick(client, ev, "pick", BELT, 1, 0, g) if opened else False
    flip = None
    key_row = None
    cycle = {}
    cmark, hmark = log_mark(client), log_mark(host)
    turn0 = battle_state(host).get("turn")
    if opened and picked:
        tally = event_state(client).get("coopEndTurnTally") or {}
        rr = client.cmd({"cmd": "battle_end_turn_ready", "turn": tally.get("turn", 0), "ready": True})
        ev["ready"] = {k: rr.get(k) for k in ("ok", "error")}
        h12, ev["host1of2Waited"] = wait_until(
            lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20.0)
        ev["host1of2"] = bool(h12)
        re_ = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        ev["hostEndTurn"] = {k: re_.get(k) for k in ("ok", "error")}
        t_end = time.time()
        got, _ = wait_until(lambda: any(s == "NextTurnState" for s in stack(client)), FLIP_WAIT_S, 0.03)
        if got:
            flip = {"t": round(time.time() - t_end, 3), "stack": stack(client), "view": inv_view(client),
                    "invForcedCloses": event_state(client).get("invForcedCloses"),
                    "side": battle_state(client).get("side"), "hostStack": stack(host)}
            flip["grenade"] = item_both(host, client, g)
        # the client's INVENTORY key during the alien side opens nothing - pressed only once the force-close closed
        # the screen (when broken it is still open under NextTurnState, which the key would close instead)
        if flip and flip["view"].get("open") is False:
            key_row = {"dismiss": dismiss_next_turn_if_present(client), "stack": stack(client),
                       "side": battle_state(client).get("side")}
            key_row["bannerBefore"] = battle_state(client).get("coopWaitText")
            key = read_inventory_key(client.user_dir)
            client.ok({"cmd": "inject_input", "kind": "key", "key": key})
            time.sleep(KEY_READ_S)
            key_row.update({"key": key, "view": inv_view(client), "bannerAfter": battle_state(client).get("coopWaitText"),
                            "stackAfter": stack(client), "sideAfter": battle_state(client).get("side")})
        # turn 2 on both (test_turn_baton.drive_full_cycle)
        try:
            drive_full_cycle(host, client, turn0, timeout=60)
            cycle["returned"] = True
        except Exception as e:
            cycle["err"] = short(e, 600)
        cycle["hostNts"] = dismiss_nts_all(host)
        cycle["clientNts"] = dismiss_nts_all(client)
        cycle["turn2"] = {"host": {k: battle_state(host).get(k) for k in ("side", "turn")},
                          "client": {k: battle_state(client).get(k) for k in ("side", "turn")},
                          "clientStack": stack(client), "clientView": inv_view(client)}
        # cleanup when the screen was not force-closed: the rebound screen's cursor item back, then closed
        # (otherwise a no-op)
        v = inv_view(client)
        if v.get("open"):
            cycle["cleanup"] = {"view": {k: v.get(k) for k in ("top", "unitId", "selectedItem")},
                                "cursorClear": client.cmd({"cmd": "inventory_cursor_clear"})}
            if v.get("top"):
                close_client(client, cycle["cleanup"])
    cycle["uiLines"] = {"client": ui_lines(client, cmark), "host": ui_lines(host, hmark)}
    rec = collect_held(host, client, seq0)
    evidence("side_change_closes", {"staging": st, "stagedDiff": staged, "ui": ev, "flip": flip, "alienKey": key_row,
                                    "cycle": cycle, "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if not opened:
        fails += open_fails(ev, "side_change_closes")
    elif not picked:
        fails.append(f"side_change_closes: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the "
                     f"cursor (want the grenade {g})")
    elif not ev.get("host1of2"):
        fails.append(f"precondition: the host never showed END TURN 1/2 after the client's ready "
                     f"({ev.get('ready')})")
    elif flip is None:
        fails.append(f"precondition: no NextTurnState on the client within {FLIP_WAIT_S} s of the host's END "
                     f"TURN ({ev.get('hostEndTurn')}, client stack {stack(client)})")
    else:
        # when broken the screen stays open under NextTurnState, with no force-close
        if "InventoryState" in flip["stack"] or flip["view"].get("open") is not False:
            fails.append(f"side_change_closes: at the client's side flip the stack is {flip['stack']} and "
                         f"inventory_view.open {flip['view'].get('open')} (want no InventoryState: force-closed)")
        dsd = dnum(forced_reason(before["client"], "side"), forced_reason({"invForcedCloses": flip["invForcedCloses"]},
                                                                           "side"))
        if dsd != 1:
            fails.append(f"side_change_closes: client invForcedCloses.byReason.side +{dsd} at the flip (want +1; "
                         f"invForcedCloses {flip['invForcedCloses']})")
        want_belt = {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
        for m in ("host", "client"):
            got = {k: (flip["grenade"][m] or {}).get(k) for k in want_belt}
            if got != want_belt:
                fails.append(f"side_change_closes: {m} grenade at the flip {flip['grenade'][m]} (want {want_belt})")
        if key_row is not None:
            if key_row["view"].get("open") is not False or key_row["bannerAfter"] != key_row["bannerBefore"] or \
                    key_row["side"] == 0:
                fails.append(f"side_change_closes: the client's INVENTORY key during the alien side {key_row} (want "
                             f"the screen closed and coopWaitText unchanged, on the alien side)")
        if "err" in cycle:
            fails.append(f"SETUP-FAILURE: drive_full_cycle failed: {cycle['err']} (host "
                         f"{cycle.get('hostNts')}, client {cycle.get('clientNts')}, NTS push/pop lines "
                         f"{cycle['uiLines']})")
        t2 = cycle.get("turn2") or {}
        if t2.get("host") != {"side": 0, "turn": TURN0 + 1} or t2.get("client") != {"side": 0, "turn": TURN0 + 1}:
            fails.append(f"side_change_closes: after the cycle {t2} (want side 0, turn {TURN0 + 1} on both)")
    if inv_view(client).get("open") is not False:
        fails.append(f"side_change_closes: the client's inventory is still open at the row's end ({inv_view(client)}, "
                     f"stack {stack(client)})")
    fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False},
                        "side_change_closes")
    fails += common_fails(host, client, before, {}, None, "side_change_closes")
    finish(fails)


def heal_step(host, client):
    """The tail of host_placement_sync and host_reload_key (not a row): the client turns C one octant
    (session.send_turn). Its context's evs carry any host change the client still lacks; returns that context's
    evs with the delta shape each one carried (host openxcom.log)."""
    out = {}
    hmark = log_mark(host)
    es0 = event_state(host)
    seq0 = es0.get("lastSeqEmitted") or 0
    cc0 = es0.get("closedContexts") or []
    cdir = (units(host).get(C_ID) or {}).get("direction")
    to = (cdir + 1) % 8
    base = event_state(client).get("lastSeqApplied", 0)
    rt = session.send_turn(client, C_ID, to)
    out["turn"] = {"from": cdir, "toDir": to, "resp": {k: rt.get(k) for k in ("ok", "iseq", "error")}}
    try:
        session.wait_turn_settled(host, client, base)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        out["waitErr"] = short(e)
    es1 = event_state(host)
    ctx = [c for c in new_contexts(cc0, es1.get("closedContexts")) if c.get("origin") == "intent"
           and c.get("kind") == "turn" and c.get("actorId") == C_ID]
    aid = ctx[0]["actionId"] if len(ctx) == 1 else None
    hev = evs_since(host, seq0)
    dl = deltas_since(host, hmark)
    out["ctxEvs"] = [{"seq": e["seq"], "kind": e["kind"], "actionId": e["actionId"],
                      "delta": delta_shape((dl.get(e["seq"]) or {}).get("delta"))} for e in hev if e["actionId"] == aid]
    out["otherEvs"] = ev_tuples([e for e in hev if e["actionId"] != aid])
    out["lastDelta"] = es1.get("lastDelta")
    return out


def host_placement_sync(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    hst = restage_h(host, client, STAGE_H, "belt_and_ground")
    staged = settle(host, client)
    gh = hst["ids"]["grenade"]
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    # open and close only: no placement
    ra = host.cmd({"cmd": "battle_open_inventory", "unit": H_ID})
    ev["emptyOpen"] = {k: ra.get(k) for k in ("ok", "opened", "error")}
    rca = host.cmd({"cmd": "battle_close_inventory"})
    empty_gone, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
    ev["emptyClose"] = {"ok": rca.get("ok"), "error": rca.get("error"), "gone": bool(empty_gone)}
    c0 = dirty_sets(before["host"], "close")

    def latched_and_consumed():
        p = probes_held(host)
        return dirty_sets(p, "close") != c0 and dirty(p).get("pending") is False
    _, ev["emptyLatchWaited"] = wait_until(latched_and_consumed, LATCH_WAIT_S)
    session.wait_host_idle(host, client, timeout=30)
    mid = snap_held(host, client)
    # the move: a real host placement, sampled with the host's screen open
    rb = host.cmd({"cmd": "battle_open_inventory", "unit": H_ID})
    ev["moveOpen"] = {k: rb.get(k) for k in ("ok", "opened", "error")}
    move_open = bool(rb.get("opened")) and inv_view(host).get("top") is True
    picked = dropped = False
    sample = {}
    if move_open:
        ev["pick"] = click(host, slot=BELT, x=1, y=0)
        picked, _ = wait_until(lambda: selected(host) == gh, CLICK_WAIT_S)
        ev["pick"]["cursor"] = selected(host)
        if picked:
            ev["drop"] = click(host, slot=LH, x=0, y=0)
            dropped, _ = wait_until(lambda: selected(host) == -1, CLICK_WAIT_S)
            ev["drop"]["cursor"] = selected(host)
            ev["hostInvGuard"] = event_state(host).get("invGuard")
            s0 = mid["host"]["syncEvsEmitted"]

            def synced():
                c = iview(items_by_id(client), gh) or {}
                return c.get("slot") == LH and (event_state(host).get("syncEvsEmitted") or 0) > (s0 or 0)
            _, sample["waited"] = wait_until(synced, SYNC_WAIT_S, 0.1)
            sample["grenade"] = item_both(host, client, gh)
            sample["tu"] = {"host": inv.tu_of(host, H_ID), "client": inv.tu_of(client, H_ID)}
            sample["host"] = probes_held(host)
            sample["client"] = probes_held(client)
            sample["hostViewOpen"] = inv_view(host).get("open")
    rcb = host.cmd({"cmd": "battle_close_inventory"})
    move_gone, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
    ev["moveClose"] = {"ok": rcb.get("ok"), "error": rcb.get("error"), "gone": bool(move_gone)}
    session.wait_host_idle(host, client, timeout=30)
    heal = heal_step(host, client)
    rec = collect_held(host, client, seq0)
    evidence("host_placement_sync",
             {"staging": hst, "stagedDiff": staged, "ui": ev,
              "openCloseOnly": {"hostDirty": (before["host"]["invHostDirty"], mid["host"]["invHostDirty"]),
                                "hostSync": (before["host"]["syncEvsEmitted"], mid["host"]["syncEvsEmitted"])},
              "move": {k: (v if k not in ("host", "client") else {kk: v.get(kk) for kk in HELD_PROBE_KEYS[:5]})
                       for k, v in sample.items()},
              "heal": heal, "row": rec_view(before, rec, {"hGrenade": gh}), "notes": notes})
    fails = list(notes) + staged_fails(hst, staged, H_TU_MAX, "H")
    # open and close only: when broken sets.close +0
    if not (ra.get("opened") and empty_gone):
        fails.append(f"host_placement_sync open/close: the host's open/close did not run ({ev['emptyOpen']}, "
                     f"{ev['emptyClose']})")
    dc = dnum(dirty_sets(before["host"], "close"), dirty_sets(mid["host"], "close"))
    de = dnum(dirty(before["host"]).get("emptyFlushes"), dirty(mid["host"]).get("emptyFlushes"))
    dsa = dnum(before["host"]["syncEvsEmitted"], mid["host"]["syncEvsEmitted"])
    if (dc, de, dsa) != (1, 1, 0):
        fails.append(f"host_placement_sync open/close: host invHostDirty.sets.close +{dc}, emptyFlushes +{de}, "
                     f"syncEvsEmitted +{dsa} (want +1 / +1 / +0: the close latched, its flush found an empty delta)")
    # the move: when broken there is no sync and the client's H lags
    if not move_open:
        fails.append(f"host_placement_sync move: the host's inventory did not open on H ({ev['moveOpen']})")
    elif not (picked and dropped):
        fails.append(f"host_placement_sync move: the host's clicks did not move H's grenade (pick {ev.get('pick')}, "
                     f"drop {ev.get('drop')})")
    else:
        dm = dnum(dirty_sets(mid["host"], "move"), dirty_sets(sample["host"], "move"))
        dsb = dnum(mid["host"]["syncEvsEmitted"], sample["host"]["syncEvsEmitted"])
        dap = dnum(mid["client"]["syncEvsApplied"], sample["client"]["syncEvsApplied"])
        if (dm, dsb, dap) != (1, 1, 1):
            fails.append(f"host_placement_sync move: with the host's screen open: host invHostDirty.sets.move +{dm}, "
                         f"host syncEvsEmitted +{dsb}, client syncEvsApplied +{dap} (want +1 / +1 / +1)")
        want = {"owner": H_ID, "slot": LH, "onTile": False}
        for m in ("host", "client"):
            got = {k: (sample["grenade"][m] or {}).get(k) for k in want}
            if got != want:
                fails.append(f"host_placement_sync move: {m} H grenade with the host's screen open "
                             f"{sample['grenade'][m]} (want {want})")
        if sample["tu"] != {"host": H_TU_MAX - TU_BELT_TO_HAND, "client": H_TU_MAX - TU_BELT_TO_HAND}:
            fails.append(f"host_placement_sync move: H tu with the host's screen open {sample['tu']} (want "
                         f"{H_TU_MAX - TU_BELT_TO_HAND} on both)")
        if sample.get("hostViewOpen") is not True:
            fails.append(f"host_placement_sync move: the host's screen was not open at the sample "
                         f"({sample.get('hostViewOpen')})")
    if not move_gone:
        fails.append(f"host_placement_sync: the host's screen did not close ({ev['moveClose']})")
    if "waitErr" in heal:
        fails.append(f"host_placement_sync heal step: {heal['waitErr']}")
    fails += common_fails(host, client, before, {}, None, "host_placement_sync")
    finish(fails)


def host_reload_key(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    hst = restage_h(host, client, STAGE_H, "load_rifle")
    staged = settle(host, client)
    rifle, clip = hst["ids"]["rifle"], hst["ids"]["beltClip"]
    ev = {"leftover": leftover, "tab": tab_select(host, H_ID)}
    key = read_reload_key(host.user_dir)
    ev["key"] = key
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev["rifleBefore"] = item_both(host, client, rifle)
    host.ok({"cmd": "inject_input", "kind": "key", "key": key})
    loaded, ev["reloadWaited"] = wait_until(
        lambda: clip in ((iview(items_by_id(host), rifle) or {}).get("ammo") or []), CLICK_WAIT_S)
    ev["hostLoaded"] = bool(loaded)
    s0 = before["host"]["syncEvsEmitted"] or 0

    def synced():
        return ((iview(items_by_id(client), rifle) or {}).get("ammo") == (iview(items_by_id(host), rifle) or {}).get("ammo")
                and (event_state(host).get("syncEvsEmitted") or 0) > s0)
    _, ev["syncWaited"] = wait_until(synced, SYNC_WAIT_S, 0.1)
    sample = {"rifle": item_both(host, client, rifle), "tu": {"host": inv.tu_of(host, H_ID),
                                                              "client": inv.tu_of(client, H_ID)},
              "hostEvs": ev_tuples(evs_since(host, seq0)), "host": probes_held(host), "client": probes_held(client)}
    session.wait_host_idle(host, client, timeout=30)
    heal = heal_step(host, client)
    rec = collect_held(host, client, seq0)
    evidence("host_reload_key",
             {"staging": hst, "stagedDiff": staged, "ui": ev,
              "sample": {k: (v if k not in ("host", "client") else {kk: v.get(kk) for kk in HELD_PROBE_KEYS[:5]})
                         for k, v in sample.items()},
              "heal": heal, "row": rec_view(before, rec, {"rifle": rifle, "clip": clip}), "notes": notes})
    fails = list(notes) + staged_fails(hst, staged, H_TU_MAX, "H")
    r_empty = [rifle, rifle, rifle]                 # an empty rifle [r, r, r]
    r_loaded = [clip, rifle, rifle, rifle]          # a loaded one [clip, r, r, r]
    if not ev["tab"]:
        fails.append(f"precondition: TAB never selected H on the host (selectedId {battle_state(host).get('selectedId')})")
    if (ev["rifleBefore"]["host"] or {}).get("ammo") != r_empty or (ev["rifleBefore"]["client"] or {}).get("ammo") != r_empty:
        fails.append(f"precondition: H's rifle before the key {ev['rifleBefore']} (want ammo {r_empty} on both)")
    if not loaded:
        fails.append(f"host_reload_key: the host's reload key (key {key}) did not load H's rifle on the host "
                     f"({sample['rifle']['host']})")
    else:
        # when broken there is no sync and the client's rifle stays [r, r, r]
        dr = dnum(dirty_sets(before["host"], "reload"), dirty_sets(sample["host"], "reload"))
        dsy = dnum(before["host"]["syncEvsEmitted"], sample["host"]["syncEvsEmitted"])
        if (dr, dsy) != (1, 1):
            fails.append(f"host_reload_key: host invHostDirty.sets.reload +{dr}, host syncEvsEmitted +{dsy} (want +1 / "
                         f"+1)")
        for m in ("host", "client"):
            if (sample["rifle"][m] or {}).get("ammo") != r_loaded:
                fails.append(f"host_reload_key: {m} rifle ammo {(sample['rifle'][m] or {}).get('ammo')} before any "
                             f"other host ev (want {r_loaded})")
        if sample["tu"]["host"] != sample["tu"]["client"]:
            fails.append(f"host_reload_key: H tu {sample['tu']} (want equal on both)")
        if [e[1] for e in sample["hostEvs"]] != ["sync"] or any(e[2] != 0 for e in sample["hostEvs"]):
            fails.append(f"host_reload_key: host evs since the key {sample['hostEvs']} (want exactly one `sync`, "
                         f"actionId 0)")
    if "waitErr" in heal:
        fails.append(f"host_reload_key heal step: {heal['waitErr']}")
    fails += common_fails(host, client, before, {}, None, "host_reload_key")
    finish(fails)


def battle_end_closes(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = restage_c(host, client, "battle_end_closes", BATTLE_END_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = pick(client, ev, "pick", BELT, 1, 0, g) if opened else False
    pre = []
    try:
        assert_hash_clean(host, client, full=True, what="battle_end_closes before the ending")
    except AssertionError as e:
        pre.append(f"battle_end_closes: hash_now full before the ending: {short(e, 600)}")
    before = snap_held(host, client)
    for name in ("host", "client"):
        be = before[name]["battleEnd"] or {}
        if be.get("emitted") != 0 or be.get("applied") != 0 or be.get("inventoryOpenAtTeardown") is not False:
            pre.append(f"precondition: {name} battleEnd before the ending {be} (want emitted 0, applied 0, "
                       f"inventoryOpenAtTeardown false)")
    crash0 = crash_files()
    cmark, hmark = log_mark(client), log_mark(host)
    out = {}
    ending = []
    if opened and picked:
        t0 = time.time()
        out["ending"] = end_host_abort(host, client, ending)
        applied, out["appliedWaited"] = wait_until(
            lambda: ((event_state(client).get("battleEnd") or {}).get("applied") or 0) >= 1, DEBRIEF_S, 0.05)
        deb, out["debriefWaited"] = wait_until(lambda: session.top_state(client) == "DebriefingState", DEBRIEF_S, 0.05)
        out["clientDebriefAt"] = round(time.time() - t0, 3) if deb else None
        out["applied"] = bool(applied)
        time.sleep(1.0)                  # the teardown's pops reach the log
        ec, eh = event_state(client), event_state(host)
        out["client"] = {"battleEnd": ec.get("battleEnd"), "invForcedCloses": ec.get("invForcedCloses"),
                         "stack": stack(client),
                         "debrief": {k: v for k, v in client.cmd({"cmd": "debrief_state"}).items()
                                     if k in ("ok", "shown", "onTop", "displayOnly")}}
        out["host"] = {"battleEnd": eh.get("battleEnd"), "stack": stack(host)}
    out["popLines"] = {"client": ui_lines(client, cmark), "host": ui_lines(host, hmark)}
    out["newCrashFiles"] = sorted(crash_files() - crash0)
    evidence("battle_end_closes", {"staging": st, "stagedDiff": staged, "ui": ev, "ending": ending, "out": out,
                                   "invForcedClosesBefore": before["client"]["invForcedCloses"], "notes": notes})
    fails = list(notes) + list(pre) + staged_fails(st, staged, C_TU_MAX, "C") + list(ending)
    if not opened:
        fails += open_fails(ev, "battle_end_closes")
    elif not picked:
        fails.append(f"battle_end_closes: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the "
                     f"cursor (want the grenade {g})")
    else:
        cbe = (out.get("client") or {}).get("battleEnd") or {}
        hbe = (out.get("host") or {}).get("battleEnd") or {}
        if not out.get("applied"):
            fails.append(f"battle_end_closes: the client never applied battle_end within {DEBRIEF_S} s ({cbe})")
        # when broken the teardown finds the InventoryState, with no force-close
        dbe = dnum(forced_reason(before["client"], "battle_end"),
                   forced_reason({"invForcedCloses": (out.get("client") or {}).get("invForcedCloses")}, "battle_end"))
        if dbe != 1:
            fails.append(f"battle_end_closes: client invForcedCloses.byReason.battle_end +{dbe} (want +1; "
                         f"{(out.get('client') or {}).get('invForcedCloses')})")
        if cbe.get("inventoryOpenAtTeardown") is not False:
            fails.append(f"battle_end_closes: client battleEnd.inventoryOpenAtTeardown "
                         f"{cbe.get('inventoryOpenAtTeardown')} (want false: the screen closed before the teardown)")
        deb = (out.get("client") or {}).get("debrief") or {}
        if out.get("clientDebriefAt") is None or not (deb.get("shown") and deb.get("onTop") and deb.get("displayOnly")):
            fails.append(f"battle_end_closes: the client's top is not the display-only DebriefingState within "
                         f"{DEBRIEF_S} s (debrief_state {deb}, stack {(out.get('client') or {}).get('stack')})")
        if hbe.get("emitted") != 1 or hbe.get("evsAfter") != 0:
            fails.append(f"battle_end_closes: host battleEnd emitted {hbe.get('emitted')} evsAfter "
                         f"{hbe.get('evsAfter')} (want 1 / 0)")
        inv_pops = [ln for ln in out["popLines"]["client"] if "[coop-ui] pop" in ln and "InventoryState" in ln]
        if len(inv_pops) != 1:
            fails.append(f"battle_end_closes: the client's `[coop-ui] pop ... InventoryState` lines {inv_pops} (want "
                         f"exactly one)")
    if out["newCrashFiles"]:
        fails.append(f"battle_end_closes: new crash file(s) {out['newCrashFiles']}: "
                     f"{crash_exception_lines(out['newCrashFiles'])}")
    finish(fails)


def unit_out_closes(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = {"c2Place": cs.place(host, client, C2_ID, C2_TILE, C2_DIR), "c2Stripped": strip_both(host, client, C2_ID)}
    g2 = give(host, client, C2_ID, GRENADE, BELT, 1, 0)
    st["ids"] = {"grenade": g2}
    st["tu"] = cs.set_tu_both(host, client, C2_ID, TU_MAX)
    staged = settle(host, client)
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    r = client.cmd({"cmd": "battle_open_inventory", "unit": C2_ID})
    ev["open"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    v = inv_view(client)
    ev["openView"] = {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    opened = bool(r.get("opened")) and v.get("top") is True and v.get("unitId") == C2_ID
    picked = pick(client, ev, "pick", BELT, 1, 0, g2) if opened else False
    out = {}
    died = None
    rec = None
    if opened and picked:
        crash0 = crash_files()
        cmark, hmark = log_mark(client), log_mark(host)
        t_kill = time.time()
        kr = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": C2_ID})
        out["kill"] = {k: kr.get(k) for k in ("ok", "killed", "error")}
        # when broken the client dies within CRASH_WATCH_S of the kill
        while time.time() - t_kill < CRASH_WATCH_S:
            rc_ = client.proc.poll() if client.proc else None
            if rc_ is not None:
                died = {"exitCode": rc_, "afterS": round(time.time() - t_kill, 3)}
                break
            try:
                event_state(client)
            except (OSError, ConnectionError, ValueError) as e:
                time.sleep(0.2)
                died = {"exitCode": client.proc.poll() if client.proc else None,
                        "afterS": round(time.time() - t_kill, 3), "probeError": short(e)}
                break
            time.sleep(0.1)
        time.sleep(0.5)
        out["newCrashFiles"] = sorted(crash_files() - crash0)
        out["crashLines"] = crash_exception_lines(out["newCrashFiles"])
        out["clientLogTail"] = [ln for ln in log_lines_since(client, cmark)
                                if "[coop-delta] applied seq" in ln or "[coop-ui] p" in ln][-20:]
        if died is None:
            dead, out["hostDeadWaited"] = wait_until(
                lambda: (units(host).get(C2_ID) or {}).get("status") == STATUS_DEAD
                and not battle_state(host).get("isBusy"), 30.0, 0.1)
            cdead, out["clientDeadWaited"] = wait_until(
                lambda: (units(client).get(C2_ID) or {}).get("status") == STATUS_DEAD, 15.0, 0.05)
            try:
                session.wait_host_idle(host, client, timeout=30)
            except Exception as e:
                out["idleErr"] = short(e)
            out["clientView"] = inv_view(client)
            out["clientStack"] = stack(client)
            out["invForcedCloses"] = event_state(client).get("invForcedCloses")
            out["C2"] = {"host": unit_view(units(host).get(C2_ID)), "client": unit_view(units(client).get(C2_ID))}
            out["grenade"] = item_both(host, client, g2)
            # the force-close's timing: the first host ev after which C2 is out or has no tile
            dl = deltas_since(host, hmark)
            out_seq = None
            for s in sorted(dl):
                for u in (dl[s]["delta"].get("units") or []) if isinstance(dl[s]["delta"], dict) else []:
                    if isinstance(u, dict) and u.get("id") == C2_ID and (
                            u.get("status") in (STATUS_DEAD, STATUS_UNCONSCIOUS) or u.get("onTile") is False):
                        out_seq = s
                        break
                if out_seq is not None:
                    break
            out["outSeq"] = out_seq
            out["hostDeltas"] = {s: {"kind": d["kind"], "shape": delta_shape(d["delta"])} for s, d in sorted(dl.items())}
            lines = log_lines_since(client, cmark)
            pop_i = [i for i, ln in enumerate(lines) if "[coop-ui] pop" in ln and "InventoryState" in ln]
            applied_re = re.compile(r"\[coop-delta\] applied seq (\d+):")
            nxt = [i for i, ln in enumerate(lines) if applied_re.search(ln)
                   and out_seq is not None and int(applied_re.search(ln).group(1)) > out_seq]
            at = [i for i, ln in enumerate(lines) if applied_re.search(ln)
                  and out_seq is not None and int(applied_re.search(ln).group(1)) == out_seq]
            out["order"] = {"popAt": pop_i, "outSeqAppliedAt": at, "nextAppliedAt": nxt[:1]}
            rec = collect_held(host, client, seq0)
            out["row"] = rec_view(before, rec, {"grenade": g2})
    evidence("unit_out_closes",
                         {"staging": st, "stagedDiff": staged, "ui": ev, "died": died, "out": out, "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C2_TU_MAX, "C2")
    if not opened:
        fails.append(f"unit_out_closes: the client's inventory did not open on C2 ({ev['open']}, {ev['openView']})")
    elif not picked:
        fails.append(f"unit_out_closes: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the "
                     f"cursor (want C2's grenade {g2})")
    elif died is not None:
        # broken: the client died
        fails.append(f"unit_out_closes: the client DIED {died['afterS']} s after the host's kill_unit_real {{C2}} with "
                     f"its inventory open (exit code {died.get('exitCode')}; new crash file(s) {out['newCrashFiles']}; "
                     f"exception {out['crashLines']})")
    else:
        if out["newCrashFiles"]:
            fails.append(f"unit_out_closes: new crash file(s) {out['newCrashFiles']}: {out['crashLines']}")
        c2 = out.get("C2") or {}
        if (c2.get("host") or {}).get("status") != STATUS_DEAD or (c2.get("client") or {}).get("status") != STATUS_DEAD:
            fails.append(f"unit_out_closes: C2 {c2} (want dead on both)")
        duo = dnum(forced_reason(before["client"], "unit_out"),
                   forced_reason({"invForcedCloses": out.get("invForcedCloses")}, "unit_out"))
        if duo != 1:
            fails.append(f"unit_out_closes: client invForcedCloses.byReason.unit_out +{duo} (want +1; "
                         f"{out.get('invForcedCloses')})")
        if (out.get("clientView") or {}).get("open") is not False:
            fails.append(f"unit_out_closes: client inventory_view after the death {out.get('clientView')} (want open "
                         f"false)")
        gr = out.get("grenade") or {}
        if gr.get("host") != gr.get("client") or gr.get("host") is None:
            fails.append(f"unit_out_closes: C2's grenade host={gr.get('host')} client={gr.get('client')} (want where "
                         f"the host's evs put it, equal on both)")
        o = out.get("order") or {}
        if out.get("outSeq") is None:
            fails.append(f"unit_out_closes: no host ev put C2 out or off its tile ({out.get('hostDeltas')})")
        elif len(o.get("popAt") or []) != 1 or (o.get("nextAppliedAt") and o["popAt"][0] > o["nextAppliedAt"][0]):
            fails.append(f"unit_out_closes: the client's InventoryState pop {o} (want exactly one, before the first ev "
                         f"applied after seq {out.get('outSeq')})")
        if "idleErr" in out:
            fails.append(f"unit_out_closes: {out['idleErr']}")
        fails += common_fails(host, client, before, {}, None, "unit_out_closes")
    finish(fails)


def covered_unit_out(host, client, ctx):
    """The client's inventory is covered by another screen when its soldier dies; when broken the client crashes
    when the cover closes."""
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = {"c2Place": place_host_first(host, client, C2_ID, C2_TILE, C2_DIR),
          "c2Stripped": strip_both(host, client, C2_ID)}
    g2 = give(host, client, C2_ID, GRENADE, BELT, 1, 0)
    st["ids"] = {"grenade": g2}
    st["tu"] = cs.set_tu_both(host, client, C2_ID, TU_MAX)
    staged = settle(host, client)
    ev = {"leftover": leftover}
    r = client.cmd({"cmd": "battle_open_inventory", "unit": C2_ID})
    ev["open"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    v = inv_view(client)
    ev["openView"] = {k: v.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    opened = bool(r.get("opened")) and v.get("top") is True and v.get("unitId") == C2_ID
    cov = {}
    covered = cover_inventory(client, cov) if opened else False
    ev["cover"] = cov
    before = snap_held(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    out = {}
    died = None
    rec = None
    if opened and covered:
        crash0 = crash_files()
        cmark = log_mark(client)
        t_kill = time.time()
        kr = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": C2_ID})
        out["kill"] = {k: kr.get(k) for k in ("ok", "killed", "error")}

        def client_c2_dead():
            if client.proc is not None and client.proc.poll() is not None:
                return "exited"
            return (units(client).get(C2_ID) or {}).get("status") == STATUS_DEAD
        try:
            cd, out["clientDeadWaited"] = wait_until(client_c2_dead, 15.0, 0.05)
        except (OSError, ConnectionError, ValueError) as e:
            cd = "exited"
            out["probeErrorAtKill"] = short(e)
        if cd == "exited":
            died = {"exitCode": client.proc.poll() if client.proc else None, "afterKillS": round(time.time() - t_kill, 3),
                    "at": "the kill"}
        else:
            hd, out["hostDeadWaited"] = wait_until(
                lambda: (units(host).get(C2_ID) or {}).get("status") == STATUS_DEAD
                and not battle_state(host).get("isBusy"), 30.0, 0.1)
            out["hostDead"] = bool(hd)
            time.sleep(0.5)          # the client applies the host's death + corpse evs (measured: 0.66 s)
            out["whileCovered"] = {"invForcedCloses": event_state(client).get("invForcedCloses"),
                                   "stack": stack(client), "view": inv_view(client),
                                   "C2": unit_view(units(client).get(C2_ID))}
            # close the cover (keyCancel), then watch the client for CRASH_WATCH_S
            time.sleep(KEY_SETTLE_S)
            k_close = read_key(client.user_dir, CLOSE_KEY)
            out["closeKey"] = k_close
            t_close = time.time()
            client.ok({"cmd": "inject_input", "kind": "key", "key": k_close})
            while time.time() - t_close < CRASH_WATCH_S:
                rc_ = client.proc.poll() if client.proc else None
                if rc_ is not None:
                    died = {"exitCode": rc_, "afterCloseS": round(time.time() - t_close, 3), "at": "the cover close"}
                    break
                try:
                    event_state(client)
                except (OSError, ConnectionError, ValueError) as e:
                    time.sleep(0.2)
                    died = {"exitCode": client.proc.poll() if client.proc else None,
                            "afterCloseS": round(time.time() - t_close, 3), "probeError": short(e),
                            "at": "the cover close"}
                    break
                time.sleep(0.1)
        time.sleep(0.5)
        out["newCrashFiles"] = sorted(crash_files() - crash0)
        out["crashLines"] = crash_exception_lines(out["newCrashFiles"])
        out["clientLog"] = [ln for ln in log_lines_since(client, cmark)
                            if "[coop-inv]" in ln or "[coop-ui] p" in ln][-20:]
        if died is None:
            out["afterClose"] = {"invForcedCloses": event_state(client).get("invForcedCloses"), "stack": stack(client),
                                 "view": inv_view(client)}
            try:
                session.wait_host_idle(host, client, timeout=30)
            except Exception as e:
                out["idleErr"] = short(e)
            out["C2"] = {"host": unit_view(units(host).get(C2_ID)), "client": unit_view(units(client).get(C2_ID))}
            out["grenade"] = item_both(host, client, g2)
            rec = collect_held(host, client, seq0)
            out["row"] = rec_view(before, rec, {"grenade": g2})
    evidence("covered_unit_out", {"staging": st, "stagedDiff": staged, "ui": ev, "died": died, "out": out,
                                  "invForcedClosesBefore": before["client"]["invForcedCloses"], "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C2_TU_MAX, "C2")
    f0 = before["client"]["invForcedCloses"] or {}
    if not opened:
        fails.append(f"covered_unit_out: the client's inventory did not open on C2 ({ev['open']}, {ev['openView']})")
    elif not covered:
        fails.append(f"SETUP-FAILURE: the client's {COVER_KEY} did not cover its inventory ({cov})")
    elif died is not None:
        # broken: the covered screen thinks before the next pump pass and draws a tileless unit
        # (Inventory.cpp:378)
        fails.append(f"covered_unit_out: the client DIED at {died.get('at')} ({died}) with its inventory covered and "
                     f"C2 dead "
                     f"(new crash file(s) {out['newCrashFiles']}; exception {out['crashLines']}; invForcedCloses while "
                     f"covered {(out.get('whileCovered') or {}).get('invForcedCloses')})")
    else:
        if out["newCrashFiles"]:
            fails.append(f"covered_unit_out: new crash file(s) {out['newCrashFiles']}: {out['crashLines']}")
        wc = (out.get("whileCovered") or {})
        dcd = dnum(f0.get("coveredDetach"), (wc.get("invForcedCloses") or {}).get("coveredDetach"))
        if dcd != 1:
            fails.append(f"covered_unit_out: client invForcedCloses.coveredDetach +{dcd} while covered (want +1; "
                         f"{wc.get('invForcedCloses')}, stack {wc.get('stack')})")
        if "UfopaediaStartState" not in (wc.get("stack") or []) or "InventoryState" not in (wc.get("stack") or []):
            fails.append(f"covered_unit_out: the client's stack while covered {wc.get('stack')} (want InventoryState "
                         f"under UfopaediaStartState: the detach happens under the cover)")
        ac = out.get("afterClose") or {}
        duo = dnum(forced_reason(before["client"], "unit_out"),
                   forced_reason({"invForcedCloses": ac.get("invForcedCloses")}, "unit_out"))
        if duo != 1:
            fails.append(f"covered_unit_out: client invForcedCloses.byReason.unit_out +{duo} after the cover closed "
                         f"(want +1; {ac.get('invForcedCloses')})")
        if "InventoryState" in (ac.get("stack") or []) or (ac.get("view") or {}).get("open") is not False:
            fails.append(f"covered_unit_out: the client's inventory after the cover closed: stack {ac.get('stack')}, "
                         f"view {ac.get('view')} (want closed)")
        c2 = out.get("C2") or {}
        if (c2.get("host") or {}).get("status") != STATUS_DEAD or (c2.get("client") or {}).get("status") != STATUS_DEAD:
            fails.append(f"covered_unit_out: C2 {c2} (want dead on both)")
        if "idleErr" in out:
            fails.append(f"covered_unit_out: {out['idleErr']}")
        fails += common_fails(host, client, before, {}, None, "covered_unit_out")
    finish(fails)


MAIN_BOOT_ROWS = (("held_same_unit", held_same_unit), ("right_click_cancels_held", right_click_cancels_held),
                  ("held_walk_blocks_drop", held_walk_blocks_drop),
                  ("partner_walk_under_host_screen", partner_walk_under_host_screen),
                  ("side_change_closes", side_change_closes), ("host_placement_sync", host_placement_sync),
                  ("host_reload_key", host_reload_key), ("battle_end_closes", battle_end_closes))
UNIT_OUT_BOOT_ROWS = (("unit_out_closes", unit_out_closes),)
COVERED_BOOT_ROWS = (("covered_unit_out", covered_unit_out),)   # alone: when broken the row ends the client


# ===================== bring-up =====================


def boot(host, client):
    """test_inventory.boot plus a check that the held-inventory probes are present (zeros)."""
    ctx = inv.boot(host, client)
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("invHostDirty"), dict) and isinstance(es.get("invForcedCloses"), dict)
                and isinstance(es.get("invWarningWrites"), int) and "held" in ((es.get("invGuard") or {}).get("counts")
                                                                               or {})
                and "inventoryOpenAtTeardown" in (es.get("battleEnd") or {})
                and "coveredDetach" in (es.get("invForcedCloses") or {})), (
            f"{gc.name} event_state lacks the held-inventory probes: invHostDirty={es.get('invHostDirty')!r} "
            f"invForcedCloses={es.get('invForcedCloses')!r} invWarningWrites={es.get('invWarningWrites')!r} "
            f"invGuard={es.get('invGuard')!r}")
    assert battle_state(host).get("turn") == TURN0, f"host turn {battle_state(host).get('turn')} (want {TURN0})"
    print(f"[inventory_held] boot ok: invHostDirty host={event_state(host).get('invHostDirty')} invForcedCloses client="
          f"{event_state(client).get('invForcedCloses')}", flush=True)
    return ctx


def run_boot(tag, rows, results):
    host = GameClient("host", 49930, make_user_dir(f"inventory_held_{tag}_host", options=OPTS))
    client = GameClient("client", 49931, make_user_dir(f"inventory_held_{tag}_client", options=OPTS))
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails every row of this boot
            print(f"FAIL boot {tag}: {type(e).__name__}: {e}", flush=True)
            for name, _ in rows:
                results[name] = False
                print(f"FAIL {name}: bring-up of boot {tag} failed", flush=True)
            return
        for name, fn in rows:
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
                print(f"[inventory_held] shutdown {gc.name} (boot {tag}): {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    run_boot("main", MAIN_BOOT_ROWS, results)
    run_boot("unit_out", UNIT_OUT_BOOT_ROWS, results)
    run_boot("covered", COVERED_BOOT_ROWS, results)
    order = [n for n, _ in MAIN_BOOT_ROWS + UNIT_OUT_BOOT_ROWS + COVERED_BOOT_ROWS]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_inventory_held: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
