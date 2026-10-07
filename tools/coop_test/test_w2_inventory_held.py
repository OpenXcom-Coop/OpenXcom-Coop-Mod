"""W2-P8 S-C1 - test_w2_inventory_held.py: parallel mode, the in-battle inventory
while an action runs (held placements, V11), the host's own inventory changes
reaching the second player at once (the host `sync`, Q7 (a)), and the client's
inventory screen closing by itself when its soldier goes down, when the side
changes and when the battle ends (the force-close, Q9 (a)). Spec docs
rewrite/prompts/w2p8_inventory.md: owner D130; S-C1 PINNED STAGE TEXT (AMENDMENT
P8-3); AMENDMENT P8-3a (C1-C7, rulings Q1-Q6); AMENDMENT P8-3b (the S-C1 TASK 0
pins and rulings 1-6, which move IH6 to its own boot). W2-P8 S-C2 (owner D166 = B,
D187-D191; AMENDMENT P8-4 section 4.2, P8-4 RULINGS, AMENDMENT P8-4b) re-points
IH8 (the partner's walk runs under the host's inventory) and adds IH9 (boot 3).

Boot 1 = test_w2_inventory.boot (the roster-pinned terror boot, paperdoll option
on both). Rows in this order, every row ONE run, every row restages (IH6 kills
C2 and IH7 ends the battle, so IH7 is last):
  IH1a  held placement, same unit (V11, Q8 a, OR1 a). T0-4 window: host H snap
        shot at dial 1. The client opens C's inventory; on the client's first
        `shot` cue it picks the grenade (belt (1,0)) and drops it on
        STR_LEFT_HAND: lastDeny busy, coopPendingIntent {inv_move, C},
        invLastWarning = the held text, invWarningWrites +1, the grenade on the
        cursor. Then a second drop on belt (2,0). RED: the second drop's
        invGuard.last.decision "inflight" (S-A's D150 step), invGuard.counts.held
        +0. GREEN: invGuard.last {site drop, op move, decision held}, counts.held
        +1, invWarningWrites +1 and invLastWarning the held text again,
        coopIntentsSent.inv_move unchanged by it. After the host's end the held
        order resubmits and is admitted: grenade STR_LEFT_HAND owner C, C TU 60 on
        both, the cursor empty; EQUAL.
  IH1b  right-click cancels a held order (F1970); declared GREEN at red (S-A
        section 8.1 step 8). The same first drop, then a right-click:
        coopPendingIntent null, the cursor empty, the grenade STR_BELT (1,0) on
        both; after the host's end nothing resubmits (coopIntentsSent.inv_move +1
        over the row, no inv_move context), invWarningWrites +1 over the row; EQUAL.
  IH1c  a held walk blocks a placement (V11 cross-order, F2404). On the cue: a
        client walk order for C2 -> lastDeny busy, coopPendingIntent {walk, C2};
        then the client opens C's inventory and drops the grenade on
        STR_LEFT_HAND. RED: the drop is sent (invGuard.last decision sent,
        coopIntentsSent.inv_move +1), the walk is lost; after the host's end the
        grenade moves and C2 stays. GREEN: invGuard.last decision held, nothing
        sent, invLastWarning the held text, invWarningWrites +1,
        coopPendingIntent {walk, C2} unchanged; after the host's end C2 stands on
        the walk's destination on both and the grenade is still on the cursor; a
        right-click returns it (STR_BELT (1,0) on both); EQUAL.
  IH8   the F2329 gate with the partner's walk RUNNING under the host's screen
        (T0-10; re-pointed by W2-P8 S-C2: AMENDMENT P8-4 section 4.2, the draft
        rewrite/prompts/w2p8_sc2_sr_sd_draft.md section 1.6, owner D166 = B;
        P8-4b ruling 1: the host camera on the lane's middle (11,27,0) and the
        client's xcom dial 40, so the walk lasts ~2.3 s, F2886). Host opens H's
        inventory; a client walk order for C (12,26,0) -> (9,29,0) is admitted
        (host contextsOpened.intent +1, isBusy); inside the walk the host moves
        H's grenade belt (1,0) -> STR_LEFT_HAND with real clicks; both machines
        are sampled until the walk is over or WALK_UNDER_S. The latch (S-C1,
        both builds): pending true after the drop, sets.move +1, heldByGate > 0
        while the walk's context is open. RED (S-C2.1 build: the walk frozen
        under the host's screen, F2071/F2410): C still on (12,26,0) and the
        client's H grenade still STR_BELT (1,0) after the window. GREEN: while
        the host's inventory_view.open is still true, the walk's context is
        closed, C stands on (9,29,0) on both and the client holds H's grenade
        STR_LEFT_HAND and H TU 58 - 4 (the walk's evs carried H's change,
        F2402, D189 c). Then the host closes: pending false, emptyFlushes +>= 1,
        host syncEvsEmitted +0 over the row; EQUAL. The client's dial goes back
        to its boot value at the row's end.
  IH5   V13 side change (T0-7). The client opens C's inventory and picks the
        grenade; client END TURN ready; host END TURN. RED: at the client's side
        flip inventory_view.open true (NextTurnState above it) and
        invForcedCloses.count +0. GREEN: invForcedCloses.byReason.side +1, no
        InventoryState on the client's stack at the flip, inventory_view.open
        false, the grenade STR_BELT (1,0) on both; during the alien side the
        client's INVENTORY key opens nothing (inventory_view.open false,
        coopWaitText unchanged, OR3 a). Turn 2 through
        test_rw_turn_baton.drive_full_cycle (P8-3b ruling 2); EQUAL. The red
        run's cleanup (ruling 3) acts on the rebound screen: inventory_cursor_clear,
        then battle_close_inventory (a no-op at green: the screen is gone).
  IH2   host placement sync (Q7 a; F1133). (a) the host opens and closes H's
        inventory with no placement: RED sets.close +0; GREEN sets.close +1,
        emptyFlushes +1, host syncEvsEmitted +0. (b) the host moves H's grenade
        belt (1,0) -> STR_LEFT_HAND with real clicks and both machines are sampled
        with the host's screen open: RED host syncEvsEmitted +0 and the client's H
        grenade still STR_BELT (1,0) (T0-3, F2088); GREEN sets.move +1, host
        syncEvsEmitted +1, client syncEvsApplied +1, H's grenade STR_LEFT_HAND and
        H TU 58 - 4 on both while the screen is open. The heal step; EQUAL.
  IH3   host reload key (F1133). H: rifle (no clip) STR_RIGHT_HAND, clip belt
        (0,0); host TAB-selects H and presses its reload key. RED: host
        syncEvsEmitted +0, the client's rifle ammo [r, r, r] while the host's is
        [clip, r, r, r] (F2091). GREEN: sets.reload +1, host syncEvsEmitted +1,
        rifle ammo [clip, r, r, r] and H's TU equal on both before any other host
        ev. The heal step; EQUAL.
  IH7   battle end with the client's screen open (F1972, F2398, F2399; T0-9).
        The client opens C's inventory and picks the grenade; the host aborts
        (test_w2_battle_end.end_e2). RED: client
        battleEnd.inventoryOpenAtTeardown true, invForcedCloses.byReason.battle_end
        +0. GREEN: byReason.battle_end +1, inventoryOpenAtTeardown false. Both:
        the client's top = the display-only DebriefingState within DEBRIEF_S, no
        new crash file, host battleEnd.emitted 1 and evsAfter 0, exactly one
        client `[coop-ui] pop ... InventoryState` line. Never reads inventory_view
        after the teardown (ruling 5).
Boot 2 (P8-3b ruling 1, F2802):
  IH6   unit out under an open screen (N21 = F1940; T0-6). C2 on (4,32,0),
        stripped, a grenade belt (1,0); the client opens C2's inventory and picks
        the grenade; host battle_action kill_unit_real {C2}. No click (J2). RED:
        the client dies within 5 s (a new crash log, the client process gone) -
        a named FAIL carrying the crash log's exception line. GREEN: no crash file,
        the force-close fires no later than the first applied ev after which C2
        is out or has no tile (its InventoryState pop line precedes the next
        applied ev), invForcedCloses.byReason.unit_out +1, C2 dead on both, the
        grenade where the host's evs put it on both; EQUAL.
Boot 3 (W2-P8 S-C2: AMENDMENT P8-4 C2-3 and Q1 (a); P8-4b T0-S9 pins, F2884; alone,
the IH6 precedent, because its red cell ends the client):
  IH9   a COVERED client inventory whose soldier goes down (F2856). C2 on
        (4,32,0) dir 6, stripped, a grenade belt (1,0), TU 58; the client opens
        C2's inventory and covers it with the inventory's Ufopaedia key
        (keyGeoUfopedia from its options.cfg -> UfopaediaStartState); host
        battle_action kill_unit_real {C2}; then the client closes the cover
        (keyCancel). RED: the client dies within 5 s of the close (a new crash
        log, Inventory.cpp:378 via InventoryState::think; the client process
        gone) - a named FAIL carrying the crash log's exception line. GREEN:
        invForcedCloses.coveredDetach +1 while covered, byReason.unit_out +1
        after the close, no InventoryState on the client, no crash file, C2 dead
        on both; EQUAL.
The heal step (tail of IH2 and IH3, not a row): the client turns C one octant;
its context's evs carry whatever host change the client still lacks (F2402).
EVIDENCE prints that context's evs with their delta shapes (ruling 4). Then EQUAL.

Common asserts (after wait_host_idle): hash_now full EQUAL; desyncSeen false on
both; client coopClientBStatePushes unchanged and host 0; client invLocalWrites 0;
host inventory_view.open false; client invGuard as the row names it.

Constants: the P8-3b pin table (T0-4, T0-6, T0-7, T0-9, T0-10, T0-11 rows; evidence
and scripts docs rewrite/w2p8-task0/sc1/, t0_sc1.py) and P8-2 T0-1 (tiles, max TU);
S-C2's IH8 / IH9 pins: the P8-4b pin table (T0-S1, T0-S9 rows; docs
rewrite/w2p8-task0/sc2/, t0_sc2.py). Item ids come from each row's staging record
(C7), never literals. Every lever pair goes to the CLIENT first (F607), except the
teleports IH8 and IH9 stage (P8-4b ruling 3: host leg first, checked, then the
client leg; place_host_first). Each row prints ONE "EVIDENCE <id>:" line with both
machines' fields before its conditions are checked; every row runs after an earlier
failure; "PASS <id>" / "FAIL <id>: <message>". Exit 0 only when every row passes, 2
otherwise (a bring-up failure is also 2). WV-D99 / WV-D100: one run is the result.
WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_inventory_held.py
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
import test_w2_inventory as inv
from test_w2_inventory import (C_ID, H_ID, BELT, LH, RIFLE, RIFLE_CLIP, PISTOL_CLIP, GRENADE, STAGE_H, ROW_DIR,
                               OPTS, TU_MAX, C_TU_MAX, TU_BELT_TO_HAND, stack, units, inv_view, selected, click,
                               pick, right_click_return, close_client, open_client, open_fails, order_done,
                               evidence, finish, wait_until, iview, count_of, new_contexts, guard_counts,
                               guard_last, common_fails, item_fails, tu_fails, give, drop, give_primed,
                               read_inventory_key, rec_view)
from test_w2_delta_core import diff_buckets, short
from test_w2_delta_items import items_by_id, unit_view
from test_w2_host_combat import evs_since, ev_tuples
from test_w2_client_items import strip_both
import test_w2_client_shoot as cs
from test_rw_turn_baton import drive_full_cycle, dismiss_next_turn_if_present
from test_rw_seat_pacing import tab_select
from test_w2_thin_client_tripwire import read_reload_key
from test_w2_battle_end import end_e2, DEBRIEF_S

# ----- units and TU (test_w2_inventory.py :154-:156; P8-2 T0-1) -----
C2_ID = 9                         # test_w2_inventory.py SEATED [8, 9] (:154); P8-3a Q5 (a)
H_TU_MAX = 58                     # P8-2 T0-1: "Max TU C 64, H 58"
C2_TU_MAX = 58                    # P8-3b T0-6 row: C2 "TU 58"
STATUS_DEAD = 6                   # src/Mod/Unit.h UnitStatus (test_w2_host_combat.py STATUS_DEAD)
STATUS_UNCONSCIOUS = 7

# ----- P8-3b T0-4 row (IH1a/b/c): "fire dial 1 on seat 0 (wait_seat_dial); H (14,24,0) dir 2, rifle + clip via
# give_both; set_seed 1 before each fire; battle_fire snap at (34,24,0), tuCost 14 (impact tile (40,25,0)); C K0 on
# STAGE_C (2,33,0) (window A) / (0,34,0) (window B); C2 (4,32,0) dir 6, walk dest (1,32,0)"; window 8775-10206 ms
# (3 boots) >= 3 x the longest in-window sequence 814 ms (F2797) -----
FIRE_DIAL = 1
FIRE_SEED = 1
FIRE_MODE = "snap"
H_FIRE_TILE, H_FIRE_DIR = (14, 24, 0), 2
H_FIRE_TARGET = (34, 24, 0)
FIRE_TU = 14
IH1A_TILE = (2, 33, 0)            # T0-4 window A (STAGE_C)
IH1B_TILE = (0, 33, 0)            # T0-4 pins no window-2 tile: P8-2 T0-1's IV1 tile (an empty open row tile), so C
                                  # never teleports onto its own tile (CLAUDE.local.md S2)
IH1C_TILE = (0, 34, 0)            # T0-4 window B
C2_TILE, C2_DIR = (4, 32, 0), 6   # T0-4 (IH1c) and T0-6 (IH6, Q5 a)
C2_DEST = (1, 32, 0)              # T0-4: 3 tiles west along y=32
# ----- P8-3b T0-10 row (IH8): "C tele (12,26,0) dir 2, TU 64; walk dest (9,29,0) (T0-2's read_lane, dir 5); H = T0-11
# shape 2 staging; H's grenade belt (1,0) -> STR_LEFT_HAND"; the walk froze 0.124 s after the send; host lastSeqEmitted
# and syncEvsEmitted flat 4.56 s (F2796) -----
IH8_C_TILE, IH8_C_DIR = (12, 26, 0), 2
IH8_WALK_DEST = (9, 29, 0)
IH8_SAMPLE_EVERY_S = 0.1
# ----- W2-P8 S-C2 (P8-4b pin table): T0-S1 row: "C (12,26,0) dir 2 -> (9,29,0) 3 tiles / (10,28,0) 2 tiles; host
# camera battle_camera_center (11,27,0) (on-screen) + client battleXcomSpeed 40 + wait_seat_dial(seat 1, "xcom",
# 40)"; measured "on-screen dial 40: 3 tiles 2339 ms, 2 tiles 1554-1559 ms (3 boots); off-screen walks run at
# interval 0 (~270 ms) at any dial (F2886); longest host sequence inside a window = IH8's pick+drop 202 ms".
# P8-4b ruling 1: every S-C2 walk-window row (IH8 included) pins the camera and the dial. -----
LANE_MID = (11, 27, 0)            # the host camera's centre for an on-screen partner walk (t0_sc2.py LANE_MID)
WALK_DIAL = 40                    # the client's battleXcomSpeed = seat 1's xcom dial (CoopSpeed, t0_sc2.dial_xcom)
WALK_UNDER_S = 6.0                # a 3-tile walk (2339 ms uncovered) must end under the host's screen within this;
                                  # a covered BattlescapeState steps at most once per frame (F2617), so > 2.5 x
KEY_SETTLE_S = 0.3                # P8-4b ruling 2 (F2888): a key injected right after a state opens is lost
# ----- W2-P8 S-C2 (P8-4b pin table) T0-S9 row (IH9): "C2 (4,32,0) dir 6, stripped, grenade belt (1,0), TU 58;
# client opens C2's inventory; cover = keyGeoUfopedia 117 (UfopaediaStartState, 0.102 s), close = keyCancel 27";
# F2884: "covered client inventory, host kill_unit_real {C2} -> notOnTop +2, then closing the cover crashes the
# client 0.527 s later (Inventory.cpp:378 via InventoryState::think)". The keys are read from the machine's own
# options.cfg (117 and 27 in T0-S9). -----
COVER_KEY = "keyGeoUfopedia"      # InventoryState :227 (_btnOk -> btnUfopaediaClick)
CLOSE_KEY = "keyCancel"           # UfopaediaStartState :114 (_btnOk -> btnOkClick)
COVER_WAIT_S = 2.0                # T0-S9: covered 0.102 s after the key
# ----- P8-3b T0-11 row (IH2 a): "shape 2: restage_h STAGE_H (48,24,0) dir 2, K0, H TU 58" -----
# ----- P8-3b T0-7 row (IH5): "C K0 on (1,33,0) dir 2"; the client stack at the flip [.., BattlescapeState,
# InventoryState, NextTurnState] (F2799); at turn 2 the screen rebinds to C2 with C's grenade on the cursor (F2801) --
IH5_TILE = (1, 33, 0)
TURN0 = 1                         # the boot's first player turn (battle_state.turn at bring-up)
# ----- P8-3b T0-9 row (IH7): "C K0 on STAGE_C (2,33,0); host abort + dismiss_popup"; the client's display-only
# DebriefingState 0.103 s after the confirm (F2803) -----
IH7_TILE = (2, 33, 0)
# ----- P8-3b T0-6 row + ruling 1 (IH6): "C2 (4,32,0) dir 6 (Q5 a), stripped, grenade belt (1,0), TU 58; host
# kill_unit_real {C2}"; RED = "the client dies within 5 s of the host kill_unit_real" -----
CRASH_WATCH_S = 5.0

# ----- texts (en-US; exact text) -----
TEXT_HELD = "Please wait for HostPlayer's action to finish"   # OR1 (a) = showPending's STR_COOP_WAIT_FOR_PLAYER_ACTION
                                                               # (F1965); T0-4 A atDeny invLastWarning

# ----- waits -----
CUE_WAIT_S = 30.0                 # the host's fire -> the client's first shot cue (T0-4: 124 ms)
DENY_WAIT_S = 3.0                 # T0-4: the busy deny 125-315 ms after the cue
CLICK_WAIT_S = 2.0
ORDER_TIMEOUT_S = 30.0            # the window (<= 10.2 s) plus the held order's resubmit / walk
FREEZE_WAIT_S = 5.0               # T0-10: frozen 0.124 s after the walk's send
WALK_WAIT_S = 15.0
FLIP_WAIT_S = 30.0
SYNC_WAIT_S = 3.0                 # P8-2 T0-3: the F1133 negative control sampled at 0 s and 3 s
LATCH_WAIT_S = 2.0                # C3: the close latch runs at ~InventoryState, one frame after the pop
KEY_READ_S = 0.5                  # F2097: a text is read within 0.5 s of the press

SC1_KEYS = ("invHostDirty", "invForcedCloses", "invWarningWrites", "syncEvsEmitted", "syncEvsApplied",
            "contextsOpened", "cueCounts", "battleEnd", "deltaEvsEmitted")


# ===================== probes =====================


def probes_sc1(gc):
    """test_w2_inventory.probes()' keys plus the S-C1 probes."""
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in inv.PROBE_KEYS + SC1_KEYS}


def snap_sc1(host, client):
    return {"host": probes_sc1(host), "client": probes_sc1(client)}


def collect_sc1(host, client, seq0):
    rec = inv.collect(host, client, seq0)
    rec["host"], rec["client"] = probes_sc1(host), probes_sc1(client)
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
# Copied verbatim from docs rewrite/w2p8-task0/sc1/t0_sc1.py :77-:138 (P8-3a ruling: helpers outside session.py are
# copied with a source-line comment, never re-implemented).

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
    """t0_sc1.py :145-:149: every crash_*.log (session._crash_log_snapshot) and every .dmp, in this lane's own crash
    folder and under this lane's own user dirs (W2-U8h F9563: never another lane's)."""
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


# ===================== staging (client first, F607) =====================


def settle(host, client):
    session.wait_host_idle(host, client, timeout=30)
    return diff_buckets(host, client)


def restage_c(host, client, key, tile):
    """test_w2_inventory.restage (ST5 a, kit K0) with C's tile for this file's row `key` (the P8-3b pin)."""
    inv.ROW_TILE[key] = tile
    return inv.restage(host, client, key, "K0")


def place_host_first(host, client, uid, tile, d):
    """W2-P8 S-C2 (AMENDMENT P8-4b ruling 3, F2888): test_w2_client_shoot.place (re-entrant: a unit already on the
    tile on both keeps its facing, CLAUDE.local.md S2) with the HOST leg first and checked, then the client leg: a
    host refusal (e.g. "not STATUS_STANDING") never leaves the client teleported alone (both() sends the client
    first, F607). The tile's own check is the lever's refusal (F2897). Only for player units: a host-first teleport
    of an ALIEN makes the host's next reveal ev carry state the client lacks (F607, reproduced for S-C2)."""
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
    session.wait_seq_barrier(host, client)  # W2-U8c (F6495)
    return {"teleported": tuple(tile), "dir": rh.get("dir")}


def read_key(user_dir, name):
    """Options::<name> as the process wrote it to its own options.cfg (docs rewrite/w2p8-task0/sc2/t0_sc2.py
    :64-:69, copied: test_w2_inventory.read_inventory_key's pattern for any key)."""
    with open(os.path.join(user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        m = re.search(r"^\s*" + name + r":\s*(-?\d+)\s*$", f.read(), re.M)
    assert m, f"PREMISE: no {name} in {user_dir}/options.cfg"
    return int(m.group(1))


def xcom_dial_of(gc, seat=1):
    """Seat `seat`'s xcom dial in this machine's SPEC 17 speed table (event_state `speed`)."""
    ent = [s for s in ((event_state(gc).get("speed") or {}).get("seats") or []) if s.get("seat") == seat]
    return ent[0].get("xcom") if ent else None


def set_xcom_dial(host, client, value):
    """The partner's walk pace is seat 1's xcom dial: set it on the client and wait until both tables hold it
    (docs rewrite/w2p8-task0/sc2/t0_sc2.py dial_xcom :340-:344, copied; P8-4b ruling 1)."""
    client.ok({"cmd": "set_option", "name": "battleXcomSpeed", "value": value})
    return cs.wait_seat_dial(host, client, 1, "xcom", value)


def camera_lane(host, tile=LANE_MID):
    """P8-4b ruling 1 (F2886): the host camera on the partner's walk lane (battle_camera_center, camera-only), so
    the walk steps at the dial's pace instead of UnitWalkBState's off-screen interval 0."""
    r = host.cmd({"cmd": "battle_camera_center", "x": tile[0], "y": tile[1], "z": tile[2]})
    assert r.get("ok"), f"battle_camera_center {tile} failed on the host: {r}"
    return {k: r.get(k) for k in ("centerX", "centerY", "centerZ", "viewLevel")}


def cover_inventory(gc, rec):
    """P8-4b T0-S9 row: the inventory's Ufopaedia key (keyGeoUfopedia from `gc`'s own options.cfg) puts
    UfopaediaStartState over the open InventoryState (docs rewrite/w2p8-task0/sc2/t0_sc2.py cover_inventory
    :90-:100, the pinned key path; P8-4b ruling 2: KEY_SETTLE_S after the screen opened). Fills `rec`; returns
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
    """test_w2_inventory.restage (:356-:391) for unit H, copied: kit "K0" (rifle RH, rifle clip belt (0,0), grenade
    belt (1,0), primed grenade belt (3,0), a rifle clip and a pistol clip on the tile) or "IV6" (rifle RH with no
    clip, rifle clip belt (0,0)). The teleport is test_w2_client_shoot.place (re-entrant: a unit already on the
    tile is not teleported onto it, CLAUDE.local.md S2) instead of tele_both; W2-P8 S-C2's rows pass
    `placer=place_host_first` (P8-4b ruling 3)."""
    rec = {"tile": tile}
    rec["place"] = (placer or cs.place)(host, client, H_ID, tile, ROW_DIR)
    rec["stripped"] = strip_both(host, client, H_ID)
    ids = {}
    if kit == "K0":
        ids["rifle"] = give(host, client, H_ID, RIFLE, "right")
        ids["beltClip"] = give(host, client, H_ID, RIFLE_CLIP, BELT, 0, 0)
        ids["grenade"] = give(host, client, H_ID, GRENADE, BELT, 1, 0)
        ids["primed"] = give_primed(host, client, H_ID, 3, 0)
        ids["groundClip"] = drop(host, client, tile, RIFLE_CLIP)
        ids["groundPistolClip"] = drop(host, client, tile, PISTOL_CLIP)
    elif kit == "IV6":
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
    click: never a click on a screen whose unit may be dead, J2), then closed when it is the top state (a
    battle_close_inventory under another state would pop that state, F2734). Recorded, never silent."""
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


# ===================== the T0-4 window =====================


def fire_setup(host, client):
    """T0-4's staging for H's shot (P8-3b T0-4 row); re-entrant per row."""
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
        fails.append(f"precondition ({what}): host battle_fire {f} (want ok, tuCost {FIRE_TU}; P8-3b T0-4)")
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
    """The first drop inside the window: denied busy and held (Q2 a: the item stays on the cursor)."""
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


def ih1a_held_same_unit(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    ws = fire_setup(host, client)
    st = restage_c(host, client, "IH1a", IH1A_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_sc1(host, client)
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
    rec = collect_sc1(host, client, seq0)
    evidence("IH1a", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "ui": ev, "window": win,
                      "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if not opened:
        fails += open_fails(ev, "IH1a")
        finish(fails + common_fails(host, client, before, {}, None, "IH1a"))
    fails += fire_fails(win, "IH1a")
    if not dropped:
        fails.append(f"IH1a: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the cursor "
                     f"(want the grenade {g})")
    else:
        fails += first_drop_fails(win, g, before, "IH1a")
        a, b = win["atDeny"], win.get("afterDrop2") or {}
        # the RED cell (S-C1.1): S-A's silent D150 `inflight`; GREEN (S-C1.2, V11 / Q8 a): `held`
        fails += guard_decision_fails(b.get("invGuard"), {"site": "drop", "op": "move", "decision": "held",
                                                           "itemId": g, "actorId": C_ID}, "IH1a second drop")
        dh = dnum(held_of(a), held_of(b))
        if dh != 1:
            fails.append(f"IH1a second drop: client invGuard.counts.held {held_of(a)} -> {held_of(b)} (want +1)")
        dw = dnum(a.get("invWarningWrites"), b.get("invWarningWrites"))
        if dw != 1 or b.get("invLastWarning") != TEXT_HELD:
            fails.append(f"IH1a second drop: client invWarningWrites +{dw}, invLastWarning {b.get('invLastWarning')!r} "
                         f"(want +1 and {TEXT_HELD!r}: the held text shown again)")
        if count_of(b.get("sent"), "inv_move") != count_of(a.get("sent"), "inv_move"):
            fails.append(f"IH1a second drop: client coopIntentsSent {a.get('sent')} -> {b.get('sent')} (want inv_move "
                         f"unchanged: nothing sent)")
        if b.get("cursor") != g:
            fails.append(f"IH1a second drop: client selectedItem {b.get('cursor')} (want the grenade {g})")
        # after the host's end: the held order resubmitted and admitted
        new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
        mv = [c for c in new if c.get("origin") == "intent" and c.get("kind") == "inv_move" and c.get("actorId") == C_ID]
        if len(mv) != 1:
            fails.append(f"IH1a: host closedContexts gained {len(mv)} {{intent, inv_move, {C_ID}}} (want 1: the "
                         f"resubmitted held order; new contexts {new})")
        if win.get("endCursor") != -1:
            fails.append(f"IH1a: client selectedItem after the resubmit's answer {win.get('endCursor')} (want -1)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": LH, "onTile": False}, "IH1a")
        fails += tu_fails(rec, C_TU_MAX - TU_BELT_TO_HAND, "IH1a")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "held", "itemId": g, "actorId": C_ID}, "IH1a")
    finish(fails)


def ih1b_right_click_cancel(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    ws = fire_setup(host, client)
    st = restage_c(host, client, "IH1b", IH1B_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_sc1(host, client)
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
    rec = collect_sc1(host, client, seq0)
    evidence("IH1b", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "ui": ev, "window": win,
                      "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if not opened:
        fails += open_fails(ev, "IH1b")
        finish(fails + common_fails(host, client, before, {}, None, "IH1b"))
    fails += fire_fails(win, "IH1b")
    want_belt = {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
    if not dropped:
        fails.append(f"IH1b: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the cursor "
                     f"(want the grenade {g})")
    else:
        fails += first_drop_fails(win, g, before, "IH1b")
        r = win.get("afterRightClick") or {}
        if not returned or r.get("cursor") != -1:
            fails.append(f"IH1b: client selectedItem after the right-click {r.get('cursor')} (want -1)")
        if r.get("pending") is not None:
            fails.append(f"IH1b: client coopPendingIntent after the right-click {r.get('pending')} (want null: the held "
                         f"order cancelled)")
        for m in ("host", "client"):
            got = {k: ((win.get("grenadeAfterRightClick") or {}).get(m) or {}).get(k) for k in want_belt}
            if got != want_belt:
                fails.append(f"IH1b: {m} grenade after the right-click {win['grenadeAfterRightClick'][m]} "
                             f"(want {want_belt})")
        new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
        mv = [c for c in new if c.get("kind") == "inv_move"]
        if mv:
            fails.append(f"IH1b: host closedContexts gained inv_move context(s) {mv} (want none: nothing resubmits)")
        ds = count_of(rec["client"]["coopIntentsSent"], "inv_move") - count_of(
            before["client"]["coopIntentsSent"], "inv_move")
        if ds != 1:
            fails.append(f"IH1b: client coopIntentsSent.inv_move +{ds} over the row (want +1: the first send only)")
        dw = dnum(before["client"]["invWarningWrites"], rec["client"]["invWarningWrites"])
        if dw != 1:
            fails.append(f"IH1b: client invWarningWrites +{dw} over the row (want +1: the first drop's held text)")
        fails += item_fails(rec, g, want_belt, "IH1b")
        fails += tu_fails(rec, C_TU_MAX, "IH1b")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID}, "IH1b")
    finish(fails)


def ih1c_held_walk_blocks(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    ws = fire_setup(host, client)
    st = restage_c(host, client, "IH1c", IH1C_TILE)
    st["c2Place"] = cs.place(host, client, C2_ID, C2_TILE, C2_DIR)
    st["c2Tu"] = cs.set_tu_both(host, client, C2_ID, TU_MAX)
    occ = {(u["x"], u["y"], u["z"]) for u in battle_state(host)["units"] if not u.get("isOut")}
    lane = [(C2_TILE[0] - i, C2_TILE[1], C2_TILE[2]) for i in (1, 2, 3)]
    st["laneOpen"] = [session.tile_is_open_ground(host, t[0], t[1], t[2], occ - {tuple(C2_TILE)}) for t in lane]
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_sc1(host, client)
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
    rec = collect_sc1(host, client, seq0)
    evidence("IH1c", {"fireSetup": ws, "staging": st, "stagedDiff": staged, "ui": ev, "window": win,
                      "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if st["c2Tu"] != C2_TU_MAX or not all(st["laneOpen"]):
        fails.append(f"precondition: C2 TU {st['c2Tu']} (want {C2_TU_MAX}), lane {lane} open {st['laneOpen']}")
    fails += fire_fails(win, "IH1c")
    wd = win.get("atWalkDeny") or {}
    if not win.get("busyDeny") or (wd.get("pending") or {}).get("kind") != "walk" or \
            (wd.get("pending") or {}).get("actorId") != C2_ID:
        fails.append(f"precondition (IH1c): the walk for C2 was not held busy inside the window (lastDeny "
                     f"{wd.get('lastDeny')}, coopPendingIntent {wd.get('pending')}; want {{kind walk, actorId {C2_ID}}})")
    if not opened:
        fails += open_fails(ev, "IH1c")
    elif not picked:
        fails.append(f"IH1c: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the cursor "
                     f"(want the grenade {g})")
    else:
        b0, b1 = win.get("beforeDrop") or {}, win.get("afterDrop") or {}
        # the RED cell (S-C1.1): the drop is sent and the walk is lost; GREEN (S-C1.2, V11 / Q8 a): held
        fails += guard_decision_fails(b1.get("invGuard"), {"site": "drop", "op": "move", "decision": "held",
                                                           "itemId": g, "actorId": C_ID}, "IH1c drop")
        if count_of(b1.get("sent"), "inv_move") != count_of(b0.get("sent"), "inv_move"):
            fails.append(f"IH1c drop: client coopIntentsSent {b0.get('sent')} -> {b1.get('sent')} (want inv_move "
                         f"unchanged: nothing sent)")
        p = b1.get("pending") or {}
        if p.get("kind") != "walk" or p.get("actorId") != C2_ID:
            fails.append(f"IH1c drop: client coopPendingIntent after the drop {b1.get('pending')} (want {{kind walk, "
                         f"actorId {C2_ID}}} unchanged: the held walk kept)")
        dw = dnum(b0.get("invWarningWrites"), b1.get("invWarningWrites"))
        if dw != 1 or b1.get("invLastWarning") != TEXT_HELD:
            fails.append(f"IH1c drop: client invWarningWrites +{dw}, invLastWarning {b1.get('invLastWarning')!r} "
                         f"(want +1 and {TEXT_HELD!r})")
        # after the host's end
        if win["c2End"] != {"host": C2_DEST, "client": C2_DEST}:
            fails.append(f"IH1c: C2 after the host's end {win['c2End']} (want {C2_DEST} on both: the held walk "
                         f"resubmitted)")
        if win.get("endCursor") != g:
            fails.append(f"IH1c: client selectedItem after the host's end {win.get('endCursor')} (want the grenade "
                         f"{g} still on the cursor: nothing was sent for it)")
        if (ev.get("rightClick") or {}).get("cursor") != -1:
            fails.append(f"IH1c: the right-click {ev.get('rightClick')} (want the cursor -1)")
        fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IH1c")
        fails += tu_fails(rec, C_TU_MAX, "IH1c")
    fails += common_fails(host, client, before, {},
                          {"site": "drop", "op": "move", "decision": "held", "itemId": g, "actorId": C_ID}, "IH1c")
    dh = dnum(held_of(before["client"]), held_of(rec["client"]))
    if dh != 1:
        fails.append(f"IH1c: client invGuard.counts.held +{dh} over the row (want +1)")
    finish(fails)


def ih8_open_context_gate(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    hst = restage_h(host, client, STAGE_H, "K0", placer=place_host_first)
    ct = place_host_first(host, client, C_ID, IH8_C_TILE, IH8_C_DIR)
    ctu = cs.set_tu_both(host, client, C_ID, TU_MAX)
    staged = settle(host, client)
    gh = hst["ids"]["grenade"]
    ev = {"leftover": leftover, "cPlace": ct, "cTu": ctu}
    # P8-4b ruling 1 (F2886): the walk steps at the dial's pace only on-screen on the host
    dial0 = xcom_dial_of(host)
    ev["camera"] = camera_lane(host)
    ev["dial"] = {"boot": dial0, "set": WALK_DIAL, "tables": set_xcom_dial(host, client, WALK_DIAL)}
    before = snap_sc1(host, client)
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
                         "dest": {"x": IH8_WALK_DEST[0], "y": IH8_WALK_DEST[1], "z": IH8_WALK_DEST[2]}})
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
                if (walk_ctx and s["C"] == {"host": IH8_WALK_DEST, "client": IH8_WALK_DEST}
                        and s["clientApplied"] == s["hostSeq"] and ec.get("queueDepth") == 0):
                    done = s
                    break
                time.sleep(IH8_SAMPLE_EVERY_S)
        rc = host.cmd({"cmd": "battle_close_inventory"})
        gone, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
        ev["hostClose"] = {"ok": rc.get("ok"), "error": rc.get("error"), "gone": bool(gone),
                           "msAfterSend": ms_since(t_send)}
        arrived, ev["walkWaited"] = wait_until(lambda: unit_pos(host, C_ID) == IH8_WALK_DEST
                                               and unit_pos(client, C_ID) == IH8_WALK_DEST, WALK_WAIT_S)
        ev["walkArrived"] = bool(arrived)
        try:
            session.wait_host_idle(host, client, timeout=30)
        except Exception as e:
            notes.append(f"IH8: host never idle after the walk: {short(e)}")
        # the pump consumer's pass after the walk's context closed (a no-op wait while the latch is clear)
        _, ev["latchClearWaited"] = wait_until(lambda: dirty(probes_sc1(host)).get("pending") is False, LATCH_WAIT_S)
    try:
        ev["dialBack"] = set_xcom_dial(host, client, dial0) if dial0 is not None else "no boot dial read"
    except Exception as e:
        notes.append(f"IH8: the client's dial did not go back to {dial0}: {short(e)}")
    rec = collect_sc1(host, client, seq0)
    evidence("IH8", {"staging": {"H": hst, "C": ct}, "stagedDiff": staged, "ui": ev, "samples": samples,
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
        fails.append(f"precondition (T0-10): C's walk was not admitted under the host's screen ({ev.get('admitted')}, "
                     f"walk {ev.get('walk')})")
    elif not (picked and dropped):
        fails.append(f"IH8: the host's clicks did not move H's grenade belt (1,0) -> STR_LEFT_HAND (pick "
                     f"{ev.get('pick')}, drop {ev.get('drop')})")
    else:
        d0 = before["host"]["invHostDirty"] or {}
        after_drop = [s for s in samples if s["t"] * 1000 >= (ev["drop"].get("msAfterSend") or 0)]
        first = after_drop[0] if after_drop else None
        open_ctx = [s for s in samples if not s["walkCtx"]]
        held_open = [dnum(d0.get("heldByGate"), dirty(s).get("heldByGate")) for s in open_ctx]
        # the S-C1 latch (both builds): set by the drop, held by the gate while the walk's context is open
        if not first or dirty(first).get("pending") is not True:
            fails.append(f"IH8: host invHostDirty.pending at the first sample after the drop "
                         f"{dirty(first).get('pending') if first else None} (want true)")
        dm = dnum(dirty_sets(before["host"], "move"), dirty_sets(rec["host"], "move"))
        if dm != 1:
            fails.append(f"IH8: host invHostDirty.sets.move +{dm} (want +1)")
        held_ints = [h for h in held_open if isinstance(h, int)]
        if not held_ints or max(held_ints) <= 0:
            fails.append(f"IH8: host invHostDirty.heldByGate while the walk's context was open {held_open} (want > 0)")
        # the RED cell (S-C2.1, D166 today): the walk frozen under the host's screen; GREEN (S-C2.2, D166 = B): it
        # runs to its end while the host's screen is open, and its evs carry H's change (F2402, D189 c)
        if done is None:
            last = samples[-1] if samples else {}
            fails.append(f"IH8: the walk did not end under the host's open inventory within {WALK_UNDER_S} s of the "
                         f"send (last sample: C {last.get('C')}, walk context closed {bool(last.get('walkCtx'))}, "
                         f"host screen open {last.get('hostScreenOpen')}, client H {last.get('clientH')})")
        else:
            if done["hostScreenOpen"] is not True:
                fails.append(f"IH8: the walk ended with the host's inventory_view.open {done['hostScreenOpen']} "
                             f"(want true: under the screen)")
            cg = done["clientH"]["grenade"] or {}
            if {k: cg.get(k) for k in ("owner", "slot")} != {"owner": H_ID, "slot": LH}:
                fails.append(f"IH8: the client's H grenade when the walk ended under the host's screen {cg} (want "
                             f"owner {H_ID} slot {LH}: the walk's evs carried the host's change)")
            if done["clientH"]["tu"] != H_TU_MAX - TU_BELT_TO_HAND:
                fails.append(f"IH8: the client's H TU when the walk ended under the host's screen "
                             f"{done['clientH']['tu']} (want {H_TU_MAX - TU_BELT_TO_HAND})")
        if not ev.get("walkArrived"):
            fails.append(f"IH8: C did not reach {IH8_WALK_DEST} on both (host {unit_pos(host, C_ID)}, client "
                         f"{unit_pos(client, C_ID)})")
        da = rec["host"]["invHostDirty"] or {}
        if da.get("pending") is not False:
            fails.append(f"IH8: host invHostDirty.pending after the walk {da.get('pending')} (want false)")
        de = dnum((d0 or {}).get("emptyFlushes"), da.get("emptyFlushes"))
        if not isinstance(de, int) or de < 1:
            fails.append(f"IH8: host invHostDirty.emptyFlushes +{de} over the row (want >= 1: the walk's evs carried "
                         f"H's change)")
        dsync = dnum(before["host"]["syncEvsEmitted"], rec["host"]["syncEvsEmitted"])
        if dsync != 0:
            fails.append(f"IH8: host syncEvsEmitted +{dsync} over the row (want +0)")
        ih, ic = iview(rec["ih"], gh), iview(rec["ic"], gh)
        want = {"owner": H_ID, "slot": LH, "onTile": False}
        for m, it in (("host", ih), ("client", ic)):
            if {k: (it or {}).get(k) for k in want} != want:
                fails.append(f"IH8: {m} H grenade {it} (want {want})")
        th, tc = (rec["uh"].get(H_ID) or {}).get("tu"), (rec["uc"].get(H_ID) or {}).get("tu")
        if (th, tc) != (H_TU_MAX - TU_BELT_TO_HAND,) * 2:
            fails.append(f"IH8: H tu host={th} client={tc} (want {H_TU_MAX - TU_BELT_TO_HAND} on both)")
    fails += common_fails(host, client, before, {}, None, "IH8")
    finish(fails)


def dismiss_nts_all(gc):
    """Every NextTurnState on `gc`'s stack, top first, through the REAL close() path
    (test_rw_turn_baton.dismiss_next_turn_if_present): one pass over the counted states."""
    n = sum(1 for s in stack(gc) if s == "NextTurnState")
    out = []
    for _ in range(n):
        out.append(dismiss_next_turn_if_present(gc))
    return {"counted": n, "closed": out, "stack": stack(gc)}


def ih5_side_change(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = restage_c(host, client, "IH5", IH5_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    before = snap_sc1(host, client)
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
        # OR3 (a): the client's INVENTORY key during the alien side opens nothing - pressed only once the force-close
        # closed the screen (at red it is still open under NextTurnState, which the key would close instead)
        if flip and flip["view"].get("open") is False:
            key_row = {"dismiss": dismiss_next_turn_if_present(client), "stack": stack(client),
                       "side": battle_state(client).get("side")}
            key_row["bannerBefore"] = battle_state(client).get("coopWaitText")
            key = read_inventory_key(client.user_dir)
            client.ok({"cmd": "inject_input", "kind": "key", "key": key})
            time.sleep(KEY_READ_S)
            key_row.update({"key": key, "view": inv_view(client), "bannerAfter": battle_state(client).get("coopWaitText"),
                            "stackAfter": stack(client), "sideAfter": battle_state(client).get("side")})
        # turn 2 on both (P8-3b ruling 2: test_rw_turn_baton.drive_full_cycle)
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
        # the red run's cleanup (ruling 3): the rebound screen's cursor item back, then closed (a no-op at green)
        v = inv_view(client)
        if v.get("open"):
            cycle["cleanup"] = {"view": {k: v.get(k) for k in ("top", "unitId", "selectedItem")},
                                "cursorClear": client.cmd({"cmd": "inventory_cursor_clear"})}
            if v.get("top"):
                close_client(client, cycle["cleanup"])
    cycle["uiLines"] = {"client": ui_lines(client, cmark), "host": ui_lines(host, hmark)}
    rec = collect_sc1(host, client, seq0)
    evidence("IH5", {"staging": st, "stagedDiff": staged, "ui": ev, "flip": flip, "alienKey": key_row,
                     "cycle": cycle, "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C_TU_MAX, "C")
    if not opened:
        fails += open_fails(ev, "IH5")
    elif not picked:
        fails.append(f"IH5: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the cursor "
                     f"(want the grenade {g})")
    elif not ev.get("host1of2"):
        fails.append(f"precondition (T0-7): the host never showed END TURN 1/2 after the client's ready "
                     f"({ev.get('ready')})")
    elif flip is None:
        fails.append(f"precondition (T0-7): no NextTurnState on the client within {FLIP_WAIT_S} s of the host's END "
                     f"TURN ({ev.get('hostEndTurn')}, client stack {stack(client)})")
    else:
        # the RED cell (S-C1.1): the screen stays open under NextTurnState, no force-close
        if "InventoryState" in flip["stack"] or flip["view"].get("open") is not False:
            fails.append(f"IH5: at the client's side flip the stack is {flip['stack']} and inventory_view.open "
                         f"{flip['view'].get('open')} (want no InventoryState: force-closed)")
        dsd = dnum(forced_reason(before["client"], "side"), forced_reason({"invForcedCloses": flip["invForcedCloses"]},
                                                                           "side"))
        if dsd != 1:
            fails.append(f"IH5: client invForcedCloses.byReason.side +{dsd} at the flip (want +1; invForcedCloses "
                         f"{flip['invForcedCloses']})")
        want_belt = {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
        for m in ("host", "client"):
            got = {k: (flip["grenade"][m] or {}).get(k) for k in want_belt}
            if got != want_belt:
                fails.append(f"IH5: {m} grenade at the flip {flip['grenade'][m]} (want {want_belt})")
        if key_row is not None:
            if key_row["view"].get("open") is not False or key_row["bannerAfter"] != key_row["bannerBefore"] or \
                    key_row["side"] == 0:
                fails.append(f"IH5: the client's INVENTORY key during the alien side {key_row} (want the screen "
                             f"closed and coopWaitText unchanged, OR3 a, on the alien side)")
        if "err" in cycle:
            fails.append(f"FIXTURE-STOP (P8-3b ruling 2): drive_full_cycle failed: {cycle['err']} (host "
                         f"{cycle.get('hostNts')}, client {cycle.get('clientNts')}, NTS push/pop lines "
                         f"{cycle['uiLines']})")
        t2 = cycle.get("turn2") or {}
        if t2.get("host") != {"side": 0, "turn": TURN0 + 1} or t2.get("client") != {"side": 0, "turn": TURN0 + 1}:
            fails.append(f"IH5: after the cycle {t2} (want side 0, turn {TURN0 + 1} on both)")
    if inv_view(client).get("open") is not False:
        fails.append(f"IH5: the client's inventory is still open at the row's end ({inv_view(client)}, stack "
                     f"{stack(client)})")
    fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IH5")
    fails += common_fails(host, client, before, {}, None, "IH5")
    finish(fails)


def heal_step(host, client):
    """The tail of IH2 and IH3 (not a row): the client turns C one octant (session.send_turn, F394/F395). Its
    context's evs carry any host change the client still lacks (F2402); returns that context's evs with the delta
    shape each one carried (host openxcom.log, P8-3b ruling 4)."""
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


def ih2_host_placement_sync(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    hst = restage_h(host, client, STAGE_H, "K0")
    staged = settle(host, client)
    gh = hst["ids"]["grenade"]
    before = snap_sc1(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    # (a) open and close with no placement (T0-11)
    ra = host.cmd({"cmd": "battle_open_inventory", "unit": H_ID})
    ev["aOpen"] = {k: ra.get(k) for k in ("ok", "opened", "error")}
    rca = host.cmd({"cmd": "battle_close_inventory"})
    gone_a, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
    ev["aClose"] = {"ok": rca.get("ok"), "error": rca.get("error"), "gone": bool(gone_a)}
    c0 = dirty_sets(before["host"], "close")

    def latched_and_consumed():
        p = probes_sc1(host)
        return dirty_sets(p, "close") != c0 and dirty(p).get("pending") is False
    _, ev["aLatchWaited"] = wait_until(latched_and_consumed, LATCH_WAIT_S)
    session.wait_host_idle(host, client, timeout=30)
    mid = snap_sc1(host, client)
    # (b) a real host placement, sampled with the host's screen open
    rb = host.cmd({"cmd": "battle_open_inventory", "unit": H_ID})
    ev["bOpen"] = {k: rb.get(k) for k in ("ok", "opened", "error")}
    b_open = bool(rb.get("opened")) and inv_view(host).get("top") is True
    picked = dropped = False
    sample = {}
    if b_open:
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
            sample["host"] = probes_sc1(host)
            sample["client"] = probes_sc1(client)
            sample["hostViewOpen"] = inv_view(host).get("open")
    rcb = host.cmd({"cmd": "battle_close_inventory"})
    gone_b, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
    ev["bClose"] = {"ok": rcb.get("ok"), "error": rcb.get("error"), "gone": bool(gone_b)}
    session.wait_host_idle(host, client, timeout=30)
    heal = heal_step(host, client)
    rec = collect_sc1(host, client, seq0)
    evidence("IH2", {"staging": hst, "stagedDiff": staged, "ui": ev,
                     "a": {"hostDirty": (before["host"]["invHostDirty"], mid["host"]["invHostDirty"]),
                           "hostSync": (before["host"]["syncEvsEmitted"], mid["host"]["syncEvsEmitted"])},
                     "b": {k: (v if k not in ("host", "client") else {kk: v.get(kk) for kk in SC1_KEYS[:5]})
                           for k, v in sample.items()},
                     "heal": heal, "row": rec_view(before, rec, {"hGrenade": gh}), "notes": notes})
    fails = list(notes) + staged_fails(hst, staged, H_TU_MAX, "H")
    # (a) the RED cell (S-C1.1): sets.close +0
    if not (ra.get("opened") and gone_a):
        fails.append(f"IH2 (a): the host's open/close did not run ({ev['aOpen']}, {ev['aClose']})")
    dc = dnum(dirty_sets(before["host"], "close"), dirty_sets(mid["host"], "close"))
    de = dnum(dirty(before["host"]).get("emptyFlushes"), dirty(mid["host"]).get("emptyFlushes"))
    dsa = dnum(before["host"]["syncEvsEmitted"], mid["host"]["syncEvsEmitted"])
    if (dc, de, dsa) != (1, 1, 0):
        fails.append(f"IH2 (a): host invHostDirty.sets.close +{dc}, emptyFlushes +{de}, syncEvsEmitted +{dsa} (want "
                     f"+1 / +1 / +0: the close latched, its flush found an empty delta)")
    # (b) the RED cell (S-C1.1): no sync, the client's H lags (T0-3, F2088)
    if not b_open:
        fails.append(f"IH2 (b): the host's inventory did not open on H ({ev['bOpen']})")
    elif not (picked and dropped):
        fails.append(f"IH2 (b): the host's clicks did not move H's grenade (pick {ev.get('pick')}, drop "
                     f"{ev.get('drop')})")
    else:
        dm = dnum(dirty_sets(mid["host"], "move"), dirty_sets(sample["host"], "move"))
        dsb = dnum(mid["host"]["syncEvsEmitted"], sample["host"]["syncEvsEmitted"])
        dap = dnum(mid["client"]["syncEvsApplied"], sample["client"]["syncEvsApplied"])
        if (dm, dsb, dap) != (1, 1, 1):
            fails.append(f"IH2 (b): with the host's screen open: host invHostDirty.sets.move +{dm}, host "
                         f"syncEvsEmitted +{dsb}, client syncEvsApplied +{dap} (want +1 / +1 / +1)")
        want = {"owner": H_ID, "slot": LH, "onTile": False}
        for m in ("host", "client"):
            got = {k: (sample["grenade"][m] or {}).get(k) for k in want}
            if got != want:
                fails.append(f"IH2 (b): {m} H grenade with the host's screen open {sample['grenade'][m]} "
                             f"(want {want})")
        if sample["tu"] != {"host": H_TU_MAX - TU_BELT_TO_HAND, "client": H_TU_MAX - TU_BELT_TO_HAND}:
            fails.append(f"IH2 (b): H tu with the host's screen open {sample['tu']} (want "
                         f"{H_TU_MAX - TU_BELT_TO_HAND} on both)")
        if sample.get("hostViewOpen") is not True:
            fails.append(f"IH2 (b): the host's screen was not open at the sample ({sample.get('hostViewOpen')})")
    if not gone_b:
        fails.append(f"IH2: the host's screen did not close ({ev['bClose']})")
    if "waitErr" in heal:
        fails.append(f"IH2 heal step: {heal['waitErr']}")
    fails += common_fails(host, client, before, {}, None, "IH2")
    finish(fails)


def ih3_host_reload_key(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    hst = restage_h(host, client, STAGE_H, "IV6")
    staged = settle(host, client)
    rifle, clip = hst["ids"]["rifle"], hst["ids"]["beltClip"]
    ev = {"leftover": leftover, "tab": tab_select(host, H_ID)}
    key = read_reload_key(host.user_dir)
    ev["key"] = key
    before = snap_sc1(host, client)
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
              "hostEvs": ev_tuples(evs_since(host, seq0)), "host": probes_sc1(host), "client": probes_sc1(client)}
    session.wait_host_idle(host, client, timeout=30)
    heal = heal_step(host, client)
    rec = collect_sc1(host, client, seq0)
    evidence("IH3", {"staging": hst, "stagedDiff": staged, "ui": ev,
                     "sample": {k: (v if k not in ("host", "client") else {kk: v.get(kk) for kk in SC1_KEYS[:5]})
                                for k, v in sample.items()},
                     "heal": heal, "row": rec_view(before, rec, {"rifle": rifle, "clip": clip}), "notes": notes})
    fails = list(notes) + staged_fails(hst, staged, H_TU_MAX, "H")
    r_empty = [rifle, rifle, rifle]                 # F2091 / F2092: an empty rifle [r, r, r]
    r_loaded = [clip, rifle, rifle, rifle]          # a loaded one [clip, r, r, r]
    if not ev["tab"]:
        fails.append(f"precondition: TAB never selected H on the host (selectedId {battle_state(host).get('selectedId')})")
    if (ev["rifleBefore"]["host"] or {}).get("ammo") != r_empty or (ev["rifleBefore"]["client"] or {}).get("ammo") != r_empty:
        fails.append(f"precondition: H's rifle before the key {ev['rifleBefore']} (want ammo {r_empty} on both)")
    if not loaded:
        fails.append(f"IH3: the host's reload key (key {key}) did not load H's rifle on the host "
                     f"({sample['rifle']['host']})")
    else:
        # the RED cell (S-C1.1): no sync, the client's rifle stays [r, r, r] (F1133)
        dr = dnum(dirty_sets(before["host"], "reload"), dirty_sets(sample["host"], "reload"))
        dsy = dnum(before["host"]["syncEvsEmitted"], sample["host"]["syncEvsEmitted"])
        if (dr, dsy) != (1, 1):
            fails.append(f"IH3: host invHostDirty.sets.reload +{dr}, host syncEvsEmitted +{dsy} (want +1 / +1)")
        for m in ("host", "client"):
            if (sample["rifle"][m] or {}).get("ammo") != r_loaded:
                fails.append(f"IH3: {m} rifle ammo {(sample['rifle'][m] or {}).get('ammo')} before any other host ev "
                             f"(want {r_loaded})")
        if sample["tu"]["host"] != sample["tu"]["client"]:
            fails.append(f"IH3: H tu {sample['tu']} (want equal on both)")
        if [e[1] for e in sample["hostEvs"]] != ["sync"] or any(e[2] != 0 for e in sample["hostEvs"]):
            fails.append(f"IH3: host evs since the key {sample['hostEvs']} (want exactly one `sync`, actionId 0)")
    if "waitErr" in heal:
        fails.append(f"IH3 heal step: {heal['waitErr']}")
    fails += common_fails(host, client, before, {}, None, "IH3")
    finish(fails)


def ih7_battle_end(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = restage_c(host, client, "IH7", IH7_TILE)
    staged = settle(host, client)
    g = st["ids"]["grenade"]
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = pick(client, ev, "pick", BELT, 1, 0, g) if opened else False
    pre = []
    try:
        assert_hash_clean(host, client, full=True, what="IH7 before the ending")
    except AssertionError as e:
        pre.append(f"IH7: hash_now full before the ending: {short(e, 600)}")
    before = snap_sc1(host, client)
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
        out["ending"] = end_e2(host, client, ending)
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
    evidence("IH7", {"staging": st, "stagedDiff": staged, "ui": ev, "ending": ending, "out": out,
                     "invForcedClosesBefore": before["client"]["invForcedCloses"], "notes": notes})
    fails = list(notes) + list(pre) + staged_fails(st, staged, C_TU_MAX, "C") + list(ending)
    if not opened:
        fails += open_fails(ev, "IH7")
    elif not picked:
        fails.append(f"IH7: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the cursor "
                     f"(want the grenade {g})")
    else:
        cbe = (out.get("client") or {}).get("battleEnd") or {}
        hbe = (out.get("host") or {}).get("battleEnd") or {}
        if not out.get("applied"):
            fails.append(f"IH7: the client never applied battle_end within {DEBRIEF_S} s ({cbe})")
        # the RED cell (S-C1.1): the teardown found the InventoryState; no force-close
        dbe = dnum(forced_reason(before["client"], "battle_end"),
                   forced_reason({"invForcedCloses": (out.get("client") or {}).get("invForcedCloses")}, "battle_end"))
        if dbe != 1:
            fails.append(f"IH7: client invForcedCloses.byReason.battle_end +{dbe} (want +1; "
                         f"{(out.get('client') or {}).get('invForcedCloses')})")
        if cbe.get("inventoryOpenAtTeardown") is not False:
            fails.append(f"IH7: client battleEnd.inventoryOpenAtTeardown {cbe.get('inventoryOpenAtTeardown')} "
                         f"(want false: the screen closed before the teardown)")
        deb = (out.get("client") or {}).get("debrief") or {}
        if out.get("clientDebriefAt") is None or not (deb.get("shown") and deb.get("onTop") and deb.get("displayOnly")):
            fails.append(f"IH7: the client's top is not the display-only DebriefingState within {DEBRIEF_S} s "
                         f"(debrief_state {deb}, stack {(out.get('client') or {}).get('stack')})")
        if hbe.get("emitted") != 1 or hbe.get("evsAfter") != 0:
            fails.append(f"IH7: host battleEnd emitted {hbe.get('emitted')} evsAfter {hbe.get('evsAfter')} (want 1 / 0)")
        inv_pops = [ln for ln in out["popLines"]["client"] if "[coop-ui] pop" in ln and "InventoryState" in ln]
        if len(inv_pops) != 1:
            fails.append(f"IH7: the client's `[coop-ui] pop ... InventoryState` lines {inv_pops} (want exactly one)")
    if out["newCrashFiles"]:
        fails.append(f"IH7: new crash file(s) {out['newCrashFiles']}: {crash_exception_lines(out['newCrashFiles'])}")
    finish(fails)


def ih6_unit_out(host, client, ctx):
    notes = []
    leftover = ensure_closed_safe(client, notes)
    st = {"c2Place": cs.place(host, client, C2_ID, C2_TILE, C2_DIR), "c2Stripped": strip_both(host, client, C2_ID)}
    g2 = give(host, client, C2_ID, GRENADE, BELT, 1, 0)
    st["ids"] = {"grenade": g2}
    st["tu"] = cs.set_tu_both(host, client, C2_ID, TU_MAX)
    staged = settle(host, client)
    before = snap_sc1(host, client)
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
        # the RED cell (P8-3b ruling 1, F2802): the client dies within CRASH_WATCH_S of the kill
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
            # the force-close's timing (ruling 1): the first host ev after which C2 is out or has no tile
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
            rec = collect_sc1(host, client, seq0)
            out["row"] = rec_view(before, rec, {"grenade": g2})
    evidence("IH6", {"staging": st, "stagedDiff": staged, "ui": ev, "died": died, "out": out, "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C2_TU_MAX, "C2")
    if not opened:
        fails.append(f"IH6: the client's inventory did not open on C2 ({ev['open']}, {ev['openView']})")
    elif not picked:
        fails.append(f"IH6: the click on STR_BELT (1,0) put {ev.get('pick', {}).get('cursor')} on the cursor "
                     f"(want C2's grenade {g2})")
    elif died is not None:
        # the RED cell (S-C1.1, F2802)
        fails.append(f"IH6: the client DIED {died['afterS']} s after the host's kill_unit_real {{C2}} with its "
                     f"inventory open (exit code {died.get('exitCode')}; new crash file(s) {out['newCrashFiles']}; "
                     f"exception {out['crashLines']})")
    else:
        if out["newCrashFiles"]:
            fails.append(f"IH6: new crash file(s) {out['newCrashFiles']}: {out['crashLines']}")
        c2 = out.get("C2") or {}
        if (c2.get("host") or {}).get("status") != STATUS_DEAD or (c2.get("client") or {}).get("status") != STATUS_DEAD:
            fails.append(f"IH6: C2 {c2} (want dead on both)")
        duo = dnum(forced_reason(before["client"], "unit_out"),
                   forced_reason({"invForcedCloses": out.get("invForcedCloses")}, "unit_out"))
        if duo != 1:
            fails.append(f"IH6: client invForcedCloses.byReason.unit_out +{duo} (want +1; {out.get('invForcedCloses')})")
        if (out.get("clientView") or {}).get("open") is not False:
            fails.append(f"IH6: client inventory_view after the death {out.get('clientView')} (want open false)")
        gr = out.get("grenade") or {}
        if gr.get("host") != gr.get("client") or gr.get("host") is None:
            fails.append(f"IH6: C2's grenade host={gr.get('host')} client={gr.get('client')} (want where the host's evs "
                         f"put it, equal on both)")
        o = out.get("order") or {}
        if out.get("outSeq") is None:
            fails.append(f"IH6: no host ev put C2 out or off its tile ({out.get('hostDeltas')})")
        elif len(o.get("popAt") or []) != 1 or (o.get("nextAppliedAt") and o["popAt"][0] > o["nextAppliedAt"][0]):
            fails.append(f"IH6: the client's InventoryState pop {o} (want exactly one, before the first ev applied "
                         f"after seq {out.get('outSeq')})")
        if "idleErr" in out:
            fails.append(f"IH6: {out['idleErr']}")
        fails += common_fails(host, client, before, {}, None, "IH6")
    finish(fails)


def ih9_covered_unit_out(host, client, ctx):
    """W2-P8 S-C2 (AMENDMENT P8-4 C2-3, P8-4 RULINGS Q1 (a); P8-4b T0-S9 row, F2884): the client's inventory is
    covered by another screen when its soldier dies; the crash comes when the cover closes."""
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
    before = snap_sc1(host, client)
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
            time.sleep(0.5)          # the client applies the host's death + corpse evs (T0-S9: 0.66 s)
            out["whileCovered"] = {"invForcedCloses": event_state(client).get("invForcedCloses"),
                                   "stack": stack(client), "view": inv_view(client),
                                   "C2": unit_view(units(client).get(C2_ID))}
            # close the cover (P8-4b T0-S9: keyCancel), then watch the client for CRASH_WATCH_S
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
            rec = collect_sc1(host, client, seq0)
            out["row"] = rec_view(before, rec, {"grenade": g2})
    evidence("IH9", {"staging": st, "stagedDiff": staged, "ui": ev, "died": died, "out": out,
                     "invForcedClosesBefore": before["client"]["invForcedCloses"], "notes": notes})
    fails = list(notes) + staged_fails(st, staged, C2_TU_MAX, "C2")
    f0 = before["client"]["invForcedCloses"] or {}
    if not opened:
        fails.append(f"IH9: the client's inventory did not open on C2 ({ev['open']}, {ev['openView']})")
    elif not covered:
        fails.append(f"FIXTURE-STOP (P8-4b T0-S9): the client's {COVER_KEY} did not cover its inventory ({cov})")
    elif died is not None:
        # the RED cell (S-C2.1, F2856 = F2884): the covered screen thinks before the next pump pass and draws a
        # tileless unit (Inventory.cpp:378)
        fails.append(f"IH9: the client DIED at {died.get('at')} ({died}) with its inventory covered and C2 dead "
                     f"(new crash file(s) {out['newCrashFiles']}; exception {out['crashLines']}; invForcedCloses while "
                     f"covered {(out.get('whileCovered') or {}).get('invForcedCloses')})")
    else:
        if out["newCrashFiles"]:
            fails.append(f"IH9: new crash file(s) {out['newCrashFiles']}: {out['crashLines']}")
        wc = (out.get("whileCovered") or {})
        dcd = dnum(f0.get("coveredDetach"), (wc.get("invForcedCloses") or {}).get("coveredDetach"))
        if dcd != 1:
            fails.append(f"IH9: client invForcedCloses.coveredDetach +{dcd} while covered (want +1; "
                         f"{wc.get('invForcedCloses')}, stack {wc.get('stack')})")
        if "UfopaediaStartState" not in (wc.get("stack") or []) or "InventoryState" not in (wc.get("stack") or []):
            fails.append(f"IH9: the client's stack while covered {wc.get('stack')} (want InventoryState under "
                         f"UfopaediaStartState: the detach happens under the cover)")
        ac = out.get("afterClose") or {}
        duo = dnum(forced_reason(before["client"], "unit_out"),
                   forced_reason({"invForcedCloses": ac.get("invForcedCloses")}, "unit_out"))
        if duo != 1:
            fails.append(f"IH9: client invForcedCloses.byReason.unit_out +{duo} after the cover closed (want +1; "
                         f"{ac.get('invForcedCloses')})")
        if "InventoryState" in (ac.get("stack") or []) or (ac.get("view") or {}).get("open") is not False:
            fails.append(f"IH9: the client's inventory after the cover closed: stack {ac.get('stack')}, view "
                         f"{ac.get('view')} (want closed)")
        c2 = out.get("C2") or {}
        if (c2.get("host") or {}).get("status") != STATUS_DEAD or (c2.get("client") or {}).get("status") != STATUS_DEAD:
            fails.append(f"IH9: C2 {c2} (want dead on both)")
        if "idleErr" in out:
            fails.append(f"IH9: {out['idleErr']}")
        fails += common_fails(host, client, before, {}, None, "IH9")
    finish(fails)


BOOT1 = (("IH1a", ih1a_held_same_unit), ("IH1b", ih1b_right_click_cancel), ("IH1c", ih1c_held_walk_blocks),
         ("IH8", ih8_open_context_gate), ("IH5", ih5_side_change), ("IH2", ih2_host_placement_sync),
         ("IH3", ih3_host_reload_key), ("IH7", ih7_battle_end))
BOOT2 = (("IH6", ih6_unit_out),)
BOOT3 = (("IH9", ih9_covered_unit_out),)   # W2-P8 S-C2 (P8-4 section 4.2: "IH9 ... BOOT3, alone")


# ===================== bring-up =====================


def boot(host, client):
    """test_w2_inventory.boot (the held boot, P8-3b) plus the S-C1 probes' presence (zeros)."""
    ctx = inv.boot(host, client)
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("invHostDirty"), dict) and isinstance(es.get("invForcedCloses"), dict)
                and isinstance(es.get("invWarningWrites"), int) and "held" in ((es.get("invGuard") or {}).get("counts")
                                                                               or {})
                and "inventoryOpenAtTeardown" in (es.get("battleEnd") or {})
                and "coveredDetach" in (es.get("invForcedCloses") or {})), (
            f"{gc.name} event_state lacks the W2-P8 S-C1/S-C2 probes: invHostDirty={es.get('invHostDirty')!r} "
            f"invForcedCloses={es.get('invForcedCloses')!r} invWarningWrites={es.get('invWarningWrites')!r} "
            f"invGuard={es.get('invGuard')!r}")
    assert battle_state(host).get("turn") == TURN0, f"host turn {battle_state(host).get('turn')} (want {TURN0})"
    print(f"[w2p8-sc1] boot ok: invHostDirty host={event_state(host).get('invHostDirty')} invForcedCloses client="
          f"{event_state(client).get('invForcedCloses')}", flush=True)
    return ctx


def run_boot(tag, rows, results):
    host = GameClient("host", 49930, make_user_dir(f"w2p8_held_{tag}_host", options=OPTS))
    client = GameClient("client", 49931, make_user_dir(f"w2p8_held_{tag}_client", options=OPTS))
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
                print(f"[w2p8-sc1] shutdown {gc.name} (boot {tag}): {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    run_boot("b1", BOOT1, results)
    run_boot("b2", BOOT2, results)
    run_boot("b3", BOOT3, results)
    order = [n for n, _ in BOOT1 + BOOT2 + BOOT3]
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_inventory_held: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
