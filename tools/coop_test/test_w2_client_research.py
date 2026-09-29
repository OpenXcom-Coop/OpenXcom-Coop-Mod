"""W2-P4r S-R - test_w2_client_research.py: in a SEPARATE campaign battle whose
host has research sync OFF, every research-based weapon check reads the research
of the unit's OWNER (owner D149 = (a); spec rewrite/prompts/w2p4r_research_list.md
section (f), as amended by PLAN REVIEW + AMENDMENT D1 (PR-R1 = ST1, PR-R2 = ST2,
PR-R3 = ST3) and AMENDMENT D2 (F1400, F1402-F1405)).

Before W2-P4r the second player's game swaps its own world for the host's at
battle entry, so both machines only know the HOST's research during the battle
(F1176): the guest G cannot fire the plasma pistol its player researched and
can fire the heavy plasma only the host researched. After W2-P4r the client
ships its own list on battle_accept and keeps a copy; each check routes by the
unit's seat tag. Eight scenarios, ONE boot, in this order:

  C16r-s  the store and the mode (no press). First the PR-R1 precondition:
          event_state.researchMode {campaign true, shared false, sync false,
          coopBattle true, separate true} on both machines and the client's
          localSeat == G's coop == 1. Then: seats[1] {stored true, count Nc,
          unknown 0} equal on both, seats[0].stored false; the client's
          liveCount == Nh (the adopted host world, F1176); research_check
          {seat0, seat1} on both: PISTOL, PCLIP, PSI {false, true} and HEAVY,
          HCLIP {true, false} (the lists are told apart by NAME); is_researched
          in battle HEAVY and HCLIP true, the other three false, on both.
          W2-P8 S-D1 re-point (A.10, F2638): the boot's pre hook grew (below),
          so Nc and Nh are read at run time, never baked (F3041).
          RED: seats[1].stored false (no writer), research_check pistol seat 1
          false.
  C16r-u  the owner rule at canUseWeapon (Q-R2 (a)): can_use_weapon {G, item,
          action} for snap, hit, auto with berserk true, and none - the calls
          reaction fire, berserk and the AI make - on both machines, first with
          the pistol, then with the heavy plasma. GREEN: pistol true x4, heavy
          false x4 on both. RED: pistol false x4, heavy true x4.
  C16r    the client-researched pistol through the client's REAL UI: TAB G,
          the right-hand box, clear_warning, key 50. GREEN: the key starts
          targeting (cursorType aim, warningText not RESEARCH_TEXT); HOME, host
          set_seed SEED_R1, one click on TGT1 -> admitted {intent, shoot, G};
          the `shot` cue {actor G, weapon pistol}; G TU = max - snap - 4 (the
          first south shot turns G 0 -> 4, F1400) and the clip -1 on both.
          RED: refused locally (cursorType 1, RESEARCH_TEXT, nothing sent).
  C16r-f  the mode is read at each check (Q-R3 (a)). Leg 1: set_research_sync
          true on both (client first) -> separate false on both, research_check
          pistol seat 1 false -> the pistol press is refused locally with
          RESEARCH_TEXT, nothing sent. Leg 2: set_research_sync false -> separate
          true, seat 1 true -> the press starts targeting, SEED_R2, click TGT2
          -> admitted, `shot` weapon pistol, G TU = max - snap (already facing
          south). RED: leg 2 refused locally.
  C16r-m  the host-only heavy plasma through the REAL UI (the mirror). GREEN:
          refused locally (cursorType 1, BattlescapeState on top, RESEARCH_TEXT,
          nothing sent, no click made). RED: the key starts targeting; SEED_R3,
          click TGT3 -> sent and admitted.
  C16r-h  the host's admission reads the owner's list (a modified client): host
          set_seed SEED_R4, then the client's battle_intent shoot_req(G, snap,
          heavy, clip, TGT3). GREEN: answered deny - lastDeny not_researched,
          coopWaitText RESEARCH_TEXT, host intentsReceived.shoot.denied +1, host
          lastSeqEmitted unchanged, G TU and clip unchanged on both. RED:
          answered end (admitted and executed).
  C16r-i  W2-P8 S-D1 (owner D168 = a): the second player's inventory names
          items by the research of the soldier's OWNER. Staging (both
          machines, client first): G right pistol + PCLIP (clear_hands), left
          heavy + HCLIP, a pistol and a heavy on G's tile; H (the first host
          soldier) right heavy + HCLIP (clear_hands), left pistol + PCLIP, a
          pistol and a heavy on H's tile. Client, G's inventory
          (battle_open_inventory, 0.3 s): hover = inventory_click on the hand
          with an empty cursor, read the _txtItem Text, one right-click
          returns the item (F3025); Alt hover = the same click with mod alt,
          then inject_input modstate none (F3029); the psi-strength line
          (textStatLine4, a HIDDEN widget in battle: its text is asserted as
          the only proof of that read, F3031); then, re-opened, quick search
          (key 113, one letter per key 0.3 s apart, Enter applies, 113 clears;
          ground stacks only, F3033): "pistol" and "artifact".
          GREEN: hover pistol "Plasma Pistol [6]", heavy "Alien Artifact [11]";
          Alt pistol "DAMAGE>\\x010-104", heavy "Alien Artifact"; psi line
          "P.Str>\\x01<n>"; "pistol" shows the ground pistol and hides the
          heavy, "artifact" hides the pistol and shows the heavy. Host control
          (both builds): H hover heavy "Heavy Plasma [11]", pistol "Alien
          Artifact [6]"; Alt heavy "DAMAGE>\\x010-230", pistol "Alien
          Artifact". RED (the host's research on the client, TASK 0 F3025-
          F3033): the client reads like the host (hover pistol "Alien Artifact
          [6]", heavy "Heavy Plasma [11]", Alt pistol "Alien Artifact", heavy
          "DAMAGE>\\x010-230", psi line "", "pistol" hides both, "artifact"
          shows the pistol and hides the heavy). Recorded code-only (F3027,
          F3028, F3030): the ammo-name read (no nameAsAmmo on stock data), the
          category search (no categories) and the Alt tooltip's own article
          reads (InventoryState :1843/:1851). The host cannot open a partner's
          inventory (vanilla refusal, F3032): no host-views-G leg.
  C16r-j  W2-P8 S-D1 (owner D213 = b): the displays outside the inventory
          follow the owner's research too. Client: UnitInfoState on G (TAB G +
          the stats button, ESC closes, F3035); the melee damage preview (TAB
          G, 0.3 s, key 109 mod ctrl, the InfoboxState text read before its
          ~1.9 s auto-close, F3037); host control the same on H. GREEN:
          UnitInfoState "PSIONIC STRENGTH" and its value shown; melee
          "Heavy Plasma\\n?-?\\n\\nPlasma Pistol\\n0-0"; host control (both
          builds): H's psi line hidden, melee "Plasma Pistol\\n?-?\\n\\nHeavy
          Plasma\\n0-0". RED: psi label and value hidden; melee
          "Heavy Plasma\\n0-0\\n\\nPlasma Pistol\\n?-?". LAST STEP OF THE FILE
          (it changes the client's live research, F3038/F3039): the Alt aiming
          preview by a same-boot pixel check - G's pistol snap aim, HOME, the
          selector parked on TGT1, screen_pixels of a 96x80 region without and
          with the Alt latch; then discover_research PISTOL, PCLIP, PSI into
          the client's LIVE (adopted host) world; re-aim and capture again.
          The no-Alt captures must be equal (the capture is stable) and each
          Alt capture must differ from its no-Alt one (the text drew). GREEN:
          the two Alt captures are equal (G's display already read G's own
          research). RED: they differ (TASK 0: 114 px; the display read the
          live world). The mana reads are recorded code-only (no mana on stock
          data, F3036).

Common asserts (spec (f), after wait_host_idle, every row): hash_now {full:true}
every bucket EQUAL; desyncSeen false on both; client coopClientBStatePushes
unchanged and host 0; the W2-P2 delta must-be-0 counters on both; every lever
item created on both with equal ids (both()). An admitted order: host
closedContexts gains exactly one {origin intent, kind shoot, actorId G}, its evs
are in the client's log with the same seq and kind, one bt_action_end, client
coopIntentsSent.shoot +1, inFlight null at the end. A refused press: nothing
sent (client inFlight null and coopIntentsSent unchanged, host lastSeqEmitted
and intentsReceived unchanged), G TU and clip unchanged on both. G's TU is set
to its max on both (client first) before every firing row.

PR-R2 / D2 (F1403): warningText stays set after a refusal, so every press sends
clear_warning to the client right before the key and asserts the text AFTER the
key: RESEARCH_TEXT for a refusal (plus cursorType 1 and BattlescapeState on top),
not RESEARCH_TEXT for a key that starts targeting (cursorType aim). F1404: after
an admitted shot the client stays in aim, so each later row first sends the F503
cancel click.

FIXTURE (TASK 0 T0-16, docs rewrite/w2p4r-task0/constants.md): the SEPARATE
guest battle of test_coop_separate_guest_battle.py (session.
bring_up_separate_guest_battle), the host's options.cfg EnableResearchSync false,
pre_mission_start = client discover_research STR_PLASMA_PISTOL then host
discover_research STR_HEAVY_PLASMA; pin_ai_neutral right after the battle
starts. The map, the Skyranger's place, G's tile, max TU, firing and the item
ids are rolled per boot (F1399): G is found by NAME, its tile, max TU and the
item ids are read at run time, the snap cost is SNAP_PCT of the max TU
(tuSnap 30 for both weapons, T0-16e). Only the target OFFSETS from G's
deployment tile and the seeds are baked. G's firing is pinned to FIRING_PIN on
both machines (client first) before any shot (D2 / F1405, WV-D86); the S-R red
builder re-proved SEED_R1..R4 = 1 with the pin (3 boots each order, the same
impact tile every boot: TGT1, TGT2, TGT3, TGT3).
W2-P8 S-D1 boot extension (draft section 3.4; TASK 0 T0-D1..T0-D3, AMENDMENT
P8-4e, docs rewrite/w2p8-task0/sd/): pre_mission_start = client
discover_research STR_PLASMA_PISTOL, STR_PLASMA_PISTOL_CLIP, STR_PSI_LAB, then
host STR_HEAVY_PLASMA, STR_HEAVY_PLASMA_CLIP; the client's options.cfg
psiStrengthEval true; both machines' oxceShowAccuracyOnCrosshair 2 (the Alt
aiming text, F3039). H = the first host soldier (coop 0, not out) by id order.
No other row reads the added topics; C16r-s names them.

RED-THEN-GREEN (spec (d)). Commit S-R.1 (this file, the probes researchMode /
research_check / can_use_weapon, the levers set_research_sync / clear_warning,
the writer-less store) is run ONCE: exit 2, 0/6, each row with its RED. Commit
S-R.2 is run ONCE with this file unchanged: exit 0, 6/6. W2-P8 S-D1.1 (the
boot extension, the C16r-s re-point, C16r-i, C16r-j) is run ONCE: exit 2 on
exactly C16r-i and C16r-j, 6/8; S-D1.2 with this file unchanged: exit 0, 8/8.
Each scenario prints ONE "EVIDENCE <id>:" line with both machines' fields
BEFORE its green conditions are checked; main() runs every scenario even after
an earlier one failed.

WV-D99 / WV-D100: one run is the result. Exit 0 only when all eight scenarios
pass, 2 otherwise (a bring-up failure is also 2). A pixel-check control
failure in C16r-j is a failure, never retried. WV-D95: run in the foreground
to completion.

Run:  python tools/coop_test/test_w2_client_research.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral
from test_rw_turn_baton import RHAND_NTH, click_nth
from test_rw_seat_pacing import tab_select, SDLK_HOME
from test_w2_delta_core import short, both
from test_w2_delta_items import items_by_id
from test_w2_client_shoot import (give_both, send_intent, shoot_req, await_press, press, menu_rows, snap, collect,
                                  ctx_view, chain_of, admitted_fails, common_fails, finish, press_view, shot_payloads,
                                  shot_brief, mine, count_of, recv_of, cancel_client_aim, ubrief, RHAND_CENTRE,
                                  KEY_SNAP, CURSOR_AIM)
from test_w2_host_combat import ev_tuples

# ----- bring-up (TASK 0 T0-16a/b) -----
PORT = "48978"
GUEST_NAME = "Guest Zzz"
G_SEAT = 1
PISTOL, PCLIP = "STR_PLASMA_PISTOL", "STR_PLASMA_PISTOL_CLIP"
HEAVY, HCLIP = "STR_HEAVY_PLASMA", "STR_HEAVY_PLASMA_CLIP"
PSI = "STR_PSI_LAB"               # the psi requirement on stock xcom1 (W2-P8 S-D1 T0 BOOT)
CLIENT_TOPICS = (PISTOL, PCLIP, PSI)     # pre_mission_start on the client (W2-P8 S-D1 boot extension)
HOST_TOPICS = (HEAVY, HCLIP)             # pre_mission_start on the host
TOPICS = (PISTOL, PCLIP, HEAVY, HCLIP, PSI)
MODE_WANT = {"campaign": True, "shared": False, "sync": False, "coopBattle": True, "separate": True}
HOST_OPTIONS = {"EnableResearchSync": False, "oxceShowAccuracyOnCrosshair": 2}
CLIENT_OPTIONS = {"psiStrengthEval": True, "oxceShowAccuracyOnCrosshair": 2}

# ----- the construction (T0-16c/d/e; D2) -----
TGT_OFF = {"TGT1": (0, 2, 0), "TGT2": (0, 3, 0), "TGT3": (0, 4, 0)}   # from G's deployment tile, due south
SEED_R1 = 1                       # pistol snap -> TGT1, the first shot of a green run
SEED_R2 = 1                       # pistol snap -> TGT2, after TGT1's shot
SEED_R3 = 1                       # heavy snap -> TGT3, the red order (nothing fired before it)
SEED_R4 = 1                       # heavy snap -> TGT3, right after SEED_R3's shot
FIRING_PIN = 120                  # G's firing on both machines (D2 / F1405; the FIRING_120 precedent)
TU_MAX = 255                      # battle_set_unit_state tu: clamped to the unit's max TU
SNAP_PCT = 30                     # tuSnap of both weapons (xcom1 items.rul): snap = floor(max TU x 30 / 100)
SOUTH = 4                         # every target is due south of G; G deploys facing 0
RESEARCH_TEXT = "Unable to use alien artifact until researched!"   # STR_UNABLE_TO_USE_ALIEN_ARTIFACT_UNTIL_RESEARCHED (en-US)
CURSOR_NORMAL = 1                 # battle_state.cursorType CT_NORMAL
CAN_USE_CALLS = (("snap", False), ("hit", False), ("auto", True), ("none", False))   # (action, berserk)

# ----- W2-P8 S-D1 (TASK 0 T0-D1..T0-D3 at 98d209f6c, AMENDMENT P8-4e, F3024-F3043) -----
SETTLE = 0.3                      # a key injected right after a state opens is lost without it (F2888)
TXT_ITEM = (128, 140, 160, 9)     # InventoryState _txtItem (T0-D1, F3025)
TXT_AMMO = (254, 64, 66, 24)      # InventoryState _txtAmmo (recorded only)
PSI_LINE = (245, 56, 70, 9)       # textStatLine4, the psi-strength line: hidden in battle, text asserted (F3031)
QS_RECT = (244, 140, 40, 9)       # the quick-search TextEdit (T0-D2)
STATS_RECT = (107, 177, 164, 23)  # the battlescape unit-stats button -> UnitInfoState (F3035)
UI_PSI_LABEL = (8, 137, 140, 9)   # UnitInfoState "PSIONIC STRENGTH"
UI_PSI_VALUE = (150, 137, 18, 9)  # UnitInfoState psi-strength number
KEY_Q, KEY_ENTER, KEY_ESC, KEY_M = 113, 13, 27, 109   # quick search toggle, apply, close, ctrl-M melee preview
HIDDEN_X = 1000000                # inventory_view ground x of an item the search hides (T0-D2)
ARTIFACT = "Alien Artifact"       # STR_ALIEN_ARTIFACT (en-US)
PISTOL_NAME, HEAVY_NAME = "Plasma Pistol", "Heavy Plasma"
W_PISTOL, W_HEAVY = 6, 11         # getTotalWeight() with the clip loaded (T0 D1c/D1h "[6]" / "[11]")
DMG_PISTOL = "DAMAGE>\x010-104"   # the Alt damage tooltip (T0 POS_D1D2c)
DMG_HEAVY = "DAMAGE>\x010-230"    # (T0 D1c/D1h)
PSI_LINE_RE = re.compile(r"P\.Str>\x01([0-9]+)")      # the green psi line shape (F3031)
MELEE_G = f"{HEAVY_NAME}\n?-?\n\n{PISTOL_NAME}\n0-0"  # G (left heavy, right pistol) by G's owner: pistol only
MELEE_G_RED = f"{HEAVY_NAME}\n0-0\n\n{PISTOL_NAME}\n?-?"   # by the host's research (T0 D3melee_c)
MELEE_H = f"{PISTOL_NAME}\n?-?\n\n{HEAVY_NAME}\n0-0"  # H (left pistol, right heavy) by the host (T0 D3melee_h)
MELEE_WAIT = 1.9                  # the melee InfoboxState auto-closes ~1.93 s after it opens (F3037)
AIM_TILE = "TGT1"                 # the Alt aiming selector tile (T0 D3aim: G's deployment tile + (0, 2, 0))
AIM_REGION = (-40, -40, 96, 80)   # screen_pixels region around the tile's screen position (T0 D3aim)


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def rmode(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return es.get("researchMode")


def mode_view(m):
    return {k: (m or {}).get(k) for k in ("campaign", "shared", "sync", "coopBattle", "separate", "liveCount")}


def seat_entry(m, seat):
    for e in (m or {}).get("seats") or []:
        if e.get("seat") == seat:
            return {k: e.get(k) for k in ("stored", "count", "unknown")}
    return None


def rcheck(gc, topic):
    """research_check {topic} on one machine as {seat: researched} (+ the raw reply)."""
    r = gc.cmd({"cmd": "research_check", "topic": topic})
    seats = {e.get("seat"): e.get("researched") for e in (r.get("seats") or [])} if r.get("ok") else None
    return {"seats": seats, "separate": r.get("separate"), "ok": r.get("ok"), "error": r.get("error")}


def rcheck_both(host, client):
    return {t: {"host": rcheck(host, t), "client": rcheck(client, t)} for t in TOPICS}


def isr(gc, topic):
    r = gc.cmd({"cmd": "is_researched", "topic": topic})
    return r.get("researched") if r.get("ok") else f"error {r}"


def isr_all(host, client):
    return {n: {t: isr(gc, t) for t in TOPICS} for n, gc in (("host", host), ("client", client))}


def sync_both(host, client, enabled):
    """set_research_sync on both machines, client first (the two-machine lever rule)."""
    rc = client.cmd({"cmd": "set_research_sync", "enabled": enabled})
    rh = host.cmd({"cmd": "set_research_sync", "enabled": enabled})
    assert rc.get("ok") and rh.get("ok"), f"set_research_sync {enabled} failed: host={rh} client={rc}"
    return {"host": rh.get("sync"), "client": rc.get("sync")}


def tu_max_both(host, client, uid):
    return both(host, client, {"cmd": "battle_set_unit_state", "unit": uid, "tu": TU_MAX}, ("tu",))["tu"]


def snap_cost(max_tu):
    return max_tu * SNAP_PCT // 100


def turn_cost(d):
    """TU of G's pre-shot turn from facing `d` to SOUTH (1 TU per octant)."""
    k = abs(d - SOUTH) % 8
    return min(k, 8 - k)


def g_now(host, client, ctx, wid, aid):
    """G's TU, facing and the clip quantity on both machines."""
    uh = session.units_by_id(battle_state(host)).get(ctx["G"]) or {}
    uc = session.units_by_id(battle_state(client)).get(ctx["G"]) or {}
    ih, ic = items_by_id(host), items_by_id(client)
    return {"tu": (uh.get("tu"), uc.get("tu")), "dir": (uh.get("direction"), uc.get("direction")),
            "clip": ((ih.get(aid) or {}).get("qty"), (ic.get(aid) or {}).get("qty")),
            "weaponOwner": ((ih.get(wid) or {}).get("owner"), (ic.get(wid) or {}).get("owner"))}


# ===================== the client's real-UI press =====================


def ui_press(host, client, ctx, key, tile=None, before_click=None):
    """The client's REAL-UI press (spec (f)): TAB-select G, the right-hand box
    (ActionMenuState), clear_warning (D2), the row's key. When the key starts
    targeting (cursorType aim) and `tile` is given: HOME and one self-verified
    left click on `tile` (`before_click` runs right before the click). A key the
    client refuses makes no click. Returns the evidence."""
    G = ctx["G"]
    ev = {"clicked": False}
    ev["tab"] = tab_select(client, G)
    assert ev["tab"], f"TAB never selected G on the client (selectedId {battle_state(client).get('selectedId')})"
    if battle_state(client).get("cursorType") == CURSOR_AIM:
        click_nth(client, RHAND_NTH)   # F503: this click only cancels the aim
        ev["aimCancelled"] = battle_state(client).get("cursorType")
    r = click_nth(client, RHAND_NTH)
    assert (r.get("baseX"), r.get("baseY")) == RHAND_CENTRE, f"right-hand click landed off the box: {r}"
    client.wait_for("client ActionMenuState on top",
                    lambda: client.cmd({"cmd": "list_widgets"}).get("state", "").endswith("ActionMenuState") or None,
                    timeout=5)
    ev["rows"] = menu_rows(client)
    cw = client.ok({"cmd": "clear_warning"})
    ev["warningCleared"] = cw.get("warningText")
    press(client, key)
    client.wait_for("client BattlescapeState on top after the row key",
                    lambda: top(client) == "BattlescapeState" or None, timeout=5)
    bs = battle_state(client)
    ev["topAfterKey"] = top(client)
    ev["cursorAfterKey"] = bs.get("cursorType")
    ev["warningAfterKey"] = bs.get("warningText")
    if ev["cursorAfterKey"] == CURSOR_AIM and tile is not None:
        press(client, SDLK_HOME)
        time.sleep(0.15)
        pr = client.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
        ev["clickPos"] = {k: pr.get(k) for k in ("verified", "winX", "winY")}
        assert pr.get("verified"), f"precondition: map_tile_click_pos did not verify {tile} on the client: {pr}"
        if before_click:
            before_click()
        client.ok({"cmd": "inject_input", "kind": "click", "x": pr["winX"], "y": pr["winY"], "button": "left"})
        ev["clicked"] = True
    return ev


def run_press(host, client, ctx, key, tile=None, seed=None):
    """One real-UI press and its aftermath: the press, the wait for it to show as
    sent (then its end) or quiet, wait_host_idle, the record. Returns
    (before, rec, pv, outcome, notes)."""
    notes = []
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    pv = {}
    before_click = (lambda: host.ok({"cmd": "set_seed", "seed": seed})) if seed is not None else None
    try:
        pv = ui_press(host, client, ctx, key, tile, before_click)
    except Exception as e:
        notes.append(f"real-UI press: {short(e)}")
    out = await_press(host, client, before, notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    return before, rec, pv, out, notes


def refused_fails(before, rec, pv, g0, g1, what):
    """A press the client must refuse locally (PR-R2 / D2): cursorType 1 and
    BattlescapeState on top right after the key, the warning changed from the
    cleared "" to RESEARCH_TEXT, nothing sent, no click, G unchanged on both."""
    fails = []
    if pv.get("cursorAfterKey") != CURSOR_NORMAL or pv.get("topAfterKey") != "BattlescapeState":
        fails.append(f"{what}: after the key cursorType {pv.get('cursorAfterKey')} top {pv.get('topAfterKey')} "
                     f"(want {CURSOR_NORMAL} and BattlescapeState: refused locally)")
    if pv.get("warningCleared") != "" or pv.get("warningAfterKey") != RESEARCH_TEXT:
        fails.append(f"{what}: warningText {pv.get('warningCleared')!r} after clear_warning -> "
                     f"{pv.get('warningAfterKey')!r} after the key (want '' -> {RESEARCH_TEXT!r})")
    if pv.get("clicked"):
        fails.append(f"{what}: a target click was made (want none)")
    if rec["client"]["inFlight"] is not None or rec["client"]["coopIntentsSent"] != before["client"]["coopIntentsSent"]:
        fails.append(f"{what}: client inFlight {rec['client']['inFlight']} coopIntentsSent "
                     f"{before['client']['coopIntentsSent']}->{rec['client']['coopIntentsSent']} (want nothing sent)")
    if (rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]
            or rec["host"]["intentsReceived"] != before["host"]["intentsReceived"]):
        fails.append(f"{what}: host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                     f"intentsReceived {before['host']['intentsReceived']}->{rec['host']['intentsReceived']} "
                     f"(want unchanged)")
    if g1["tu"] != g0["tu"] or g1["clip"] != g0["clip"] or g0["tu"][0] != g0["tu"][1] or g0["clip"][0] != g0["clip"][1]:
        fails.append(f"{what}: G tu host/client {g0['tu']}->{g1['tu']} clip {g0['clip']}->{g1['clip']} "
                     f"(want unchanged and equal on both)")
    return fails


def shot_fails(host, before, rec, pv, g0, g1, G, weapon, what):
    """A press that must start targeting and become one admitted shot of
    `weapon` by G; G pays the snap plus the turn to SOUTH, the clip -1."""
    fails = []
    if pv.get("cursorAfterKey") != CURSOR_AIM or pv.get("warningAfterKey") == RESEARCH_TEXT:
        fails.append(f"{what}: after the key cursorType {pv.get('cursorAfterKey')} warningText "
                     f"{pv.get('warningAfterKey')!r} (want {CURSOR_AIM} and not {RESEARCH_TEXT!r}: targeting starts)")
    if not pv.get("clicked"):
        fails.append(f"{what}: no target click was made")
    f, cx = admitted_fails(before, rec, "shoot", G)
    fails += [f"{what}: {m}" for m in f]
    if cx:
        shots = shot_payloads(host, chain_of(rec, cx.get("actionId")))
        cues = [((p or {}).get("actor"), (p or {}).get("weapon")) for _, p in shots]
        if cues != [(G, weapon)]:
            fails.append(f"{what}: `shot` cues (actor, weapon) {cues} (want exactly [({G}, {weapon})])")
    max_tu, d0 = g0["tu"][0], g0["dir"][0]
    known = isinstance(max_tu, int) and isinstance(d0, int) and g0["dir"][0] == g0["dir"][1]
    want_tu = max_tu - snap_cost(max_tu) - turn_cost(d0) if known else None
    want_clip = g0["clip"][0] - 1 if isinstance(g0["clip"][0], int) else None
    if not known or g1["tu"] != (want_tu, want_tu) or g0["tu"][0] != g0["tu"][1]:
        fails.append(f"{what}: G tu host/client {g0['tu']}->{g1['tu']} (want {want_tu} on both: max - snap "
                     f"{snap_cost(max_tu) if known else None} - turn {turn_cost(d0) if known else None} "
                     f"from dir {g0['dir']})")
    if g1["clip"] != (want_clip, want_clip) or g0["clip"][0] != g0["clip"][1]:
        fails.append(f"{what}: clip host/client {g0['clip']}->{g1['clip']} (want {want_clip} on both)")
    return fails


def g_tile(ctx, name):
    o = TGT_OFF[name]
    g = ctx["gTile"]
    return (g[0] + o[0], g[1] + o[1], g[2] + o[2])


# ===================== scenarios =====================


def c16r_s_store(host, client, ctx):
    G = ctx["G"]
    mh, mc = rmode(host), rmode(client)
    ec = event_state(client)
    uh = session.units_by_id(battle_state(host)).get(G) or {}
    uc = session.units_by_id(battle_state(client)).get(G) or {}
    before = snap(host, client)
    rc = rcheck_both(host, client)
    ib = isr_all(host, client)
    seats = {n: {s: seat_entry(m, s) for s in range(4)} for n, m in (("host", mh), ("client", mc))}
    print(f"EVIDENCE C16r-s: researchMode host={mode_view(mh)} client={mode_view(mc)}; seats host={seats['host']} "
          f"client={seats['client']}; client localSeat={ec.get('localSeat')} G coop host={uh.get('coop')} "
          f"client={uc.get('coop')}; pre-mission is_researched={ctx['preIsr']} liveCount Nh={ctx['Nh']} "
          f"Nc={ctx['Nc']}; research_check={rc}; is_researched in battle={ib}", flush=True)
    fails = []
    # PR-R1 (ST1): the fixture precondition, asserted first in every run.
    for n, m in (("host", mh), ("client", mc)):
        got = {k: (m or {}).get(k) for k in MODE_WANT}
        if got != MODE_WANT:
            fails.append(f"precondition (PR-R1): {n} researchMode {got} (want {MODE_WANT})")
    if not (ec.get("localSeat") == uh.get("coop") == uc.get("coop") == G_SEAT):
        fails.append(f"precondition (PR-R1): client localSeat {ec.get('localSeat')} G coop host={uh.get('coop')} "
                     f"client={uc.get('coop')} (want all {G_SEAT})")
    want_pre = {"host": {t: t in HOST_TOPICS for t in TOPICS}, "client": {t: t in CLIENT_TOPICS for t in TOPICS}}
    if ctx["preIsr"] != want_pre:
        fails.append(f"precondition: is_researched at the end of pre_mission_start {ctx['preIsr']} (want {want_pre})")
    # the store and the mode
    want1 = {"stored": True, "count": ctx["Nc"], "unknown": 0}
    for n in ("host", "client"):
        if seats[n][G_SEAT] != want1:
            fails.append(f"{n} researchMode.seats[{G_SEAT}] {seats[n][G_SEAT]} (want {want1})")
        if (seats[n][0] or {}).get("stored") is not False:
            fails.append(f"{n} researchMode.seats[0] {seats[n][0]} (want stored false: seat 0 is the live world)")
    if (mc or {}).get("liveCount") != ctx["Nh"]:
        fails.append(f"client liveCount {(mc or {}).get('liveCount')} (want Nh {ctx['Nh']}: the adopted host world)")
    want_rc = {t: {0: t in HOST_TOPICS, G_SEAT: t in CLIENT_TOPICS} for t in TOPICS}
    for t in TOPICS:
        for n in ("host", "client"):
            got = rc[t][n]["seats"] or {}
            if {s: got.get(s) for s in (0, G_SEAT)} != want_rc[t]:
                fails.append(f"{n} research_check {t} seats {got} (want {want_rc[t]})")
    want_ib = {t: t in HOST_TOPICS for t in TOPICS}
    for n in ("host", "client"):
        if ib[n] != want_ib:
            fails.append(f"{n} is_researched in battle {ib[n]} (want {want_ib}: the live world is the host's)")
    fails += common_fails(host, client, before, "C16r-s")
    finish(fails)


def c16r_u_can_use(host, client, ctx):
    G = ctx["G"]
    before = snap(host, client)
    ids, got = {}, {}
    for label, item, ammo in (("pistol", PISTOL, PCLIP), ("heavy", HEAVY, HCLIP)):
        wid, aid = give_both(host, client, G, item, ammo)
        ids[label] = (wid, aid)
        got[label] = {}
        for action, berserk in CAN_USE_CALLS:
            row = {}
            for n, gc in (("host", host), ("client", client)):
                r = gc.cmd({"cmd": "can_use_weapon", "unit": G, "item": wid, "action": action, "berserk": berserk})
                row[n] = r.get("canUse") if r.get("ok") else f"error {r.get('error')}"
                row[n + "Msg"] = r.get("message")
            got[label][f"{action}{'/berserk' if berserk else ''}"] = row
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        got["notes"] = f"wait_host_idle: {short(e)}"
    print(f"EVIDENCE C16r-u: items={ids} canUseWeapon={got}", flush=True)
    fails = [got["notes"]] if "notes" in got else []
    for label, want in (("pistol", True), ("heavy", False)):
        for call, row in got[label].items():
            if row["host"] is not want or row["client"] is not want:
                fails.append(f"can_use_weapon {label} {call} host={row['host']} client={row['client']} "
                             f"(want {want} on both)")
    fails += common_fails(host, client, before, "C16r-u")
    finish(fails)


def c16r_pistol(host, client, ctx):
    G = ctx["G"]
    aim0 = cancel_client_aim(client)
    pw, pc = give_both(host, client, G, PISTOL, PCLIP)
    ctx["pistol"] = (pw, pc)
    tmax = tu_max_both(host, client, G)
    g0 = g_now(host, client, ctx, pw, pc)
    tgt = g_tile(ctx, "TGT1")
    before, rec, pv, out, notes = run_press(host, client, ctx, KEY_SNAP, tgt, SEED_R1)
    g1 = g_now(host, client, ctx, pw, pc)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", G)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    print(f"EVIDENCE C16r: pistol={pw} clip={pc} tuMax={tmax} snap={snap_cost(tmax)} target TGT1={tgt} "
          f"aimCancel={aim0} press={pv} outcome={out}; {press_view(before, rec)}; newContexts={new}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain]}; shots={shot_brief(shot_payloads(host, chain))}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; G before={g0} after={g1}; "
          f"G host={ubrief(rec['uh'].get(G))} client={ubrief(rec['uc'].get(G))}; diff={rec['diff']} "
          f"desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    fails += shot_fails(host, before, rec, pv, g0, g1, G, pw, "C16r")
    fails += common_fails(host, client, before, "C16r")
    finish(fails)


def c16r_f_mode(host, client, ctx):
    G = ctx["G"]
    fails = []
    assert "pistol" in ctx, "C16r gave G no pistol (its give failed), so this row has no weapon"
    pw, pc = ctx["pistol"]
    # ---- leg 1: research sync ON -> the check reads the live (host) world
    aim0 = cancel_client_aim(client)
    s1 = sync_both(host, client, True)
    m1 = {"host": mode_view(rmode(host)), "client": mode_view(rmode(client))}
    rc1 = {"host": rcheck(host, PISTOL), "client": rcheck(client, PISTOL)}
    tmax1 = tu_max_both(host, client, G)
    g0 = g_now(host, client, ctx, pw, pc)
    b1, r1, pv1, o1, n1 = run_press(host, client, ctx, KEY_SNAP)
    g1 = g_now(host, client, ctx, pw, pc)
    # ---- leg 2: research sync OFF again -> the owner's list, read at this check
    aim1 = cancel_client_aim(client)
    s2 = sync_both(host, client, False)
    m2 = {"host": mode_view(rmode(host)), "client": mode_view(rmode(client))}
    rc2 = {"host": rcheck(host, PISTOL), "client": rcheck(client, PISTOL)}
    tmax2 = tu_max_both(host, client, G)
    g2 = g_now(host, client, ctx, pw, pc)
    tgt = g_tile(ctx, "TGT2")
    b2, r2, pv2, o2, n2 = run_press(host, client, ctx, KEY_SNAP, tgt, SEED_R2)
    g3 = g_now(host, client, ctx, pw, pc)
    new2 = ctx_view(b2, r2)
    hits2 = mine(new2, "intent", "shoot", G)
    aid2 = hits2[0]["actionId"] if len(hits2) == 1 else None
    chain2 = chain_of(r2, aid2)
    print(f"EVIDENCE C16r-f: pistol={pw} clip={pc}; LEG1 sync={s1} mode={m1} research_check={rc1} tuMax={tmax1} "
          f"aimCancel={aim0} press={pv1} outcome={o1}; {press_view(b1, r1)}; G before={g0} after={g1}; "
          f"diff={r1['diff']} notes={n1}; LEG2 sync={s2} mode={m2} research_check={rc2} tuMax={tmax2} "
          f"aimCancel={aim1} target TGT2={tgt} press={pv2} outcome={o2}; {press_view(b2, r2)}; newContexts={new2}; "
          f"action={aid2} chain={[(e['seq'], e['kind']) for e in chain2]}; "
          f"shots={shot_brief(shot_payloads(host, chain2))}; G before={g2} after={g3}; diff={r2['diff']} "
          f"desync={r2['dsc']}; notes={n2}", flush=True)
    # leg 1
    fails += [f"leg 1: {m}" for m in n1]
    for n in ("host", "client"):
        if s1[n] is not True or m1[n]["separate"] is not False:
            fails.append(f"leg 1: {n} sync {s1[n]} separate {m1[n]['separate']} (want sync true, separate false)")
        if (rc1[n]["seats"] or {}).get(G_SEAT) is not False:
            fails.append(f"leg 1: {n} research_check {PISTOL} seats {rc1[n]['seats']} (want seat {G_SEAT} false)")
    fails += refused_fails(b1, r1, pv1, g0, g1, "leg 1")
    fails += [f"leg 1: {m}" for m in common_fails(host, client, b1, "C16r-f leg 1")]
    # leg 2
    fails += [f"leg 2: {m}" for m in n2]
    for n in ("host", "client"):
        if s2[n] is not False or m2[n]["separate"] is not True:
            fails.append(f"leg 2: {n} sync {s2[n]} separate {m2[n]['separate']} (want sync false, separate true)")
        if (rc2[n]["seats"] or {}).get(G_SEAT) is not True:
            fails.append(f"leg 2: {n} research_check {PISTOL} seats {rc2[n]['seats']} (want seat {G_SEAT} true)")
    fails += shot_fails(host, b2, r2, pv2, g2, g3, G, pw, "leg 2")
    fails += [f"leg 2: {m}" for m in common_fails(host, client, b2, "C16r-f leg 2")]
    finish(fails)


def c16r_m_mirror(host, client, ctx):
    G = ctx["G"]
    aim0 = cancel_client_aim(client)
    hw, hc = give_both(host, client, G, HEAVY, HCLIP)
    ctx["heavy"] = (hw, hc)
    tmax = tu_max_both(host, client, G)
    g0 = g_now(host, client, ctx, hw, hc)
    tgt = g_tile(ctx, "TGT3")
    before, rec, pv, out, notes = run_press(host, client, ctx, KEY_SNAP, tgt, SEED_R3)
    g1 = g_now(host, client, ctx, hw, hc)
    new = ctx_view(before, rec)
    hits = mine(new, "intent", "shoot", G)
    aid = hits[0]["actionId"] if len(hits) == 1 else None
    chain = chain_of(rec, aid)
    print(f"EVIDENCE C16r-m: heavy={hw} clip={hc} tuMax={tmax} target TGT3={tgt} aimCancel={aim0} press={pv} "
          f"outcome={out}; {press_view(before, rec)}; newContexts={new}; action={aid} "
          f"chain={[(e['seq'], e['kind']) for e in chain]}; shots={shot_brief(shot_payloads(host, chain))}; "
          f"host evs={ev_tuples(rec['hev'])} client evs={ev_tuples(rec['cev'])}; G before={g0} after={g1}; "
          f"diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    fails += refused_fails(before, rec, pv, g0, g1, "C16r-m")
    if new:
        fails.append(f"C16r-m: host closedContexts gained {new} (want none: nothing executed)")
    fails += common_fails(host, client, before, "C16r-m")
    finish(fails)


def c16r_h_admission(host, client, ctx):
    G = ctx["G"]
    notes = []
    aim0 = cancel_client_aim(client)
    assert "heavy" in ctx, "C16r-m gave G no heavy plasma (its give failed), so this row has no weapon"
    hw, hc = ctx["heavy"]
    tmax = tu_max_both(host, client, G)
    g0 = g_now(host, client, ctx, hw, hc)
    tgt = g_tile(ctx, "TGT3")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": SEED_R4})
    req = shoot_req(G, "snap", hw, hc, tgt)
    si = send_intent(host, client, req, notes, timeout=30)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    rec = collect(host, client, seq0)
    g1 = g_now(host, client, ctx, hw, hc)
    new = ctx_view(before, rec)
    print(f"EVIDENCE C16r-h: heavy={hw} clip={hc} tuMax={tmax} target TGT3={tgt} aimCancel={aim0} request={req} "
          f"intent={ {k: si[k] for k in ('sent', 'iseq', 'answer')} } resp={si['resp']}; {press_view(before, rec)}; "
          f"banner={rec['clientUi']['banner']!r}; newContexts={new}; host evs={ev_tuples(rec['hev'])}; "
          f"G before={g0} after={g1}; diff={rec['diff']} desync={rec['dsc']}; notes={notes}", flush=True)
    fails = list(notes)
    if not si["sent"]:
        fails.append(f"battle_intent shoot answered {si['resp']} (want sent: an iseq)")
    else:
        if si["answer"] != "deny":
            fails.append(f"the host answered {si['answer']!r} (want deny)")
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != "not_researched":
            fails.append(f"client lastDeny {rec['client']['lastDeny']} (want {{iseq {si['iseq']}, reason "
                         f"not_researched}})")
        if rec["clientUi"]["banner"] != RESEARCH_TEXT:
            fails.append(f"client coopWaitText {rec['clientUi']['banner']!r} (want {RESEARCH_TEXT!r})")
        sd = (count_of(rec["client"]["coopIntentsSent"], "shoot") - count_of(before["client"]["coopIntentsSent"],
                                                                              "shoot"),
              recv_of(rec["host"]["intentsReceived"], "shoot", "denied")
              - recv_of(before["host"]["intentsReceived"], "shoot", "denied"),
              recv_of(rec["host"]["intentsReceived"], "shoot", "admitted")
              - recv_of(before["host"]["intentsReceived"], "shoot", "admitted"))
        if sd != (1, 1, 0):
            fails.append(f"client coopIntentsSent.shoot / host intentsReceived.shoot denied / admitted = +{sd} "
                         f"(want +1 / +1 / +0)")
    if rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"] or new:
        fails.append(f"host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                     f"newContexts={new} (want nothing executed)")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"client inFlight at the end {rec['client']['inFlight']} (want null)")
    if g1["tu"] != g0["tu"] or g1["clip"] != g0["clip"] or g0["tu"][0] != g0["tu"][1] or g0["clip"][0] != g0["clip"][1]:
        fails.append(f"G tu host/client {g0['tu']}->{g1['tu']} clip {g0['clip']}->{g1['clip']} (want unchanged and "
                     f"equal on both)")
    fails += common_fails(host, client, before, "C16r-h")
    finish(fails)


# ===================== W2-P8 S-D1 helpers (the TASK 0 recipes, docs rewrite/w2p8-task0/sd/t0_sd.py) =====================


def sd_lw(gc):
    return gc.cmd({"cmd": "list_widgets"})


def sd_rect(w):
    return (w.get("x"), w.get("y"), w.get("w"), w.get("h"))


def sd_at(r, rc):
    """Every widget of the list_widgets reply `r` on rect `rc`, as [{v, t}]."""
    return [{"v": w.get("visible"), "t": w.get("text")} for w in r.get("widgets", []) if sd_rect(w) == rc]


def sd_text(r, rc):
    """The text of the ONE widget on `rc` (None unless exactly one widget sits there)."""
    hits = sd_at(r, rc)
    return hits[0]["t"] if len(hits) == 1 else None


def sd_inv(gc):
    return gc.cmd({"cmd": "inventory_view"})


def sd_wait(pred, timeout, interval=0.02):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True, round(time.time() - t0, 3)
        time.sleep(interval)
    return bool(pred()), round(time.time() - t0, 3)


def sd_key(gc, k, mod=None):
    req = {"cmd": "inject_input", "kind": "key", "key": k}
    if mod:
        req["mod"] = mod
    return gc.cmd(req)


def sd_modnone(gc):
    return gc.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"}).get("ok")


def sd_stage(host, client, G, H):
    """T0 STAGE: G right pistol + PCLIP (clear_hands), left heavy + HCLIP, a pistol and a heavy on G's tile;
    H right heavy + HCLIP (clear_hands), left pistol + PCLIP, a pistol and a heavy on H's tile. Both machines,
    client first, equal ids (both()). Returns {key: (weaponId, ammoId)}."""
    wk, gk = ("weaponId", "ammoId", "weaponSlot"), ("weaponId",)
    rows = (("gR", G, PISTOL, PCLIP, {"clear_hands": True}, wk), ("gL", G, HEAVY, HCLIP, {"slot": "left"}, wk),
            ("gGp", G, PISTOL, None, {"slot": "ground"}, gk), ("gGh", G, HEAVY, None, {"slot": "ground"}, gk),
            ("hR", H, HEAVY, HCLIP, {"clear_hands": True}, wk), ("hL", H, PISTOL, PCLIP, {"slot": "left"}, wk),
            ("hGp", H, PISTOL, None, {"slot": "ground"}, gk), ("hGh", H, HEAVY, None, {"slot": "ground"}, gk))
    ids = {}
    for key, uid, item, ammo, extra, keys in rows:
        req = dict({"cmd": "battle_give", "unit": uid, "item": item}, **extra)
        if ammo:
            req["ammo"] = ammo
        r = both(host, client, req, keys)
        ids[key] = (r.get("weaponId"), r.get("ammoId"))
    return ids


def sd_open(gc, uid):
    r = gc.cmd({"cmd": "battle_open_inventory", "unit": uid})
    time.sleep(SETTLE)
    v = sd_inv(gc)
    return {"ok": r.get("ok"), "error": r.get("error"), "open": v.get("open"), "top": v.get("top"),
            "unitId": v.get("unitId")}


def sd_opened(o, uid):
    return bool(o.get("ok") and o.get("open") and o.get("top") and o.get("unitId") == uid)


def sd_close(gc):
    if not sd_inv(gc).get("open"):
        return "not open"
    r = gc.cmd({"cmd": "battle_close_inventory"})
    got, dt = sd_wait(lambda: "InventoryState" not in session.states_stripped(gc), 3.0)
    return {"ok": r.get("ok"), "closed": got, "t": dt}


def sd_hover(gc, slot, want_id, mod=None):
    """T0-D1 (F3025/F3029): a left click on `slot` with an empty cursor runs the mouse-over before the pick; read
    _txtItem; (Alt: clear the latch); one right-click returns the item."""
    ev = {"cursor0": sd_inv(gc).get("selectedItem")}
    req = {"cmd": "inventory_click", "slot": slot}
    if mod:
        req["mod"] = mod
    ev["click"] = gc.cmd(req).get("ok")
    ev["picked"] = sd_wait(lambda: sd_inv(gc).get("selectedItem") == want_id, 2.0)[0]
    w = sd_lw(gc)
    ev["item"] = sd_text(w, TXT_ITEM)
    ev["ammo"] = sd_text(w, TXT_AMMO)
    if mod:
        ev["modClear"] = sd_modnone(gc)
    ev["rclick"] = gc.cmd({"cmd": "inventory_click", "slot": slot, "button": "right"}).get("ok")
    ev["returned"] = sd_wait(lambda: sd_inv(gc).get("selectedItem") == -1, 2.0)[0]
    return ev


def sd_hover_ok(ev, alt):
    return bool(ev.get("cursor0") == -1 and ev.get("click") and ev.get("picked") and ev.get("rclick")
                and ev.get("returned") and (ev.get("modClear") if alt else True))


def sd_ground_x(gc, ids):
    g = {e.get("id"): e.get("x") for e in sd_inv(gc).get("ground", [])}
    return {i: g.get(i) for i in ids}


def sd_search(gc, word, ids):
    """T0-D2 (F3033): key 113 opens the quick search, one letter per key 0.3 s apart, Enter applies; the ground
    x of each staged item (HIDDEN_X = hidden); 113 again clears the search."""
    ev = {"word": word, "before": sd_ground_x(gc, ids)}
    sd_key(gc, KEY_Q)
    time.sleep(SETTLE)
    ev["field"] = [h["v"] for h in sd_at(sd_lw(gc), QS_RECT)]
    for ch in word:
        sd_key(gc, ord(ch))
        time.sleep(SETTLE)
    sd_key(gc, KEY_ENTER)
    time.sleep(SETTLE)
    ev["applied"] = sd_ground_x(gc, ids)
    sd_key(gc, KEY_Q)
    time.sleep(SETTLE)
    ev["cleared"] = sd_ground_x(gc, ids)
    ev["top"] = top(gc)
    return ev


def sd_unit_info(gc, uid):
    """T0-D3 (F3035): TAB `uid`, the battlescape stats button (by rect), UnitInfoState's psi label + value, ESC."""
    ev = {"tab": tab_select(gc, uid)}
    vis = [w for w in sd_lw(gc).get("widgets", []) if w.get("interactive") and w.get("visible")]
    nth = [i for i, w in enumerate(vis) if sd_rect(w) == STATS_RECT]
    ev["statsNth"] = nth
    if not ev["tab"] or len(nth) != 1:
        return ev
    gc.cmd({"cmd": "click_widget", "nth": nth[0]})
    ev["opened"] = sd_wait(lambda: top(gc) == "UnitInfoState", 3.0)[0]
    time.sleep(SETTLE)
    w = sd_lw(gc)
    ev["title"] = sd_text(w, (16, 4, 288, 17))
    ev["label"] = sd_at(w, UI_PSI_LABEL)
    ev["value"] = sd_at(w, UI_PSI_VALUE)
    sd_key(gc, KEY_ESC)
    ev["closed"] = sd_wait(lambda: top(gc) == "BattlescapeState", 3.0)[0]
    return ev


def sd_melee(gc, uid):
    """T0-D3 (F3037): TAB `uid`, 0.3 s, ctrl-M; the InfoboxState text before its ~1.9 s auto-close."""
    ev = {"tab": tab_select(gc, uid)}
    time.sleep(SETTLE)
    ev["key"] = sd_key(gc, KEY_M, mod="ctrl").get("ok")
    ev["opened"], ev["openT"] = sd_wait(lambda: top(gc) == "InfoboxState", MELEE_WAIT)
    ev["modClear"] = sd_modnone(gc)
    w = sd_lw(gc)
    ev["state"] = (w.get("state") or "").replace("class OpenXcom::", "")
    ev["texts"] = [x.get("text") for x in w.get("widgets", []) if "text" in x]
    ev["closed"] = sd_wait(lambda: top(gc) == "BattlescapeState", 4.0, 0.1)[0]
    return ev


def sd_diff(a, b):
    """Differing pixels of two equal-length captures (None when either is missing or the lengths differ)."""
    if not a or not b or len(a) != len(b):
        return None
    return sum(1 for x, y in zip(a, b) if x != y)


def sd_aim_capture(client, G, tile):
    """T0-D3 (F3039): TAB G, the right-hand box, key 50 (snap aim), HOME, map_tile_click_pos parks the selector on
    `tile`, screen_pixels of the region without then with the Alt latch, latch cleared, one hand click cancels the
    aim (F503). Returns (evidence, {noalt, alt})."""
    ev = {"tab": tab_select(client, G)}
    if battle_state(client).get("cursorType") == CURSOR_AIM:
        click_nth(client, RHAND_NTH)   # F503: this click only cancels an earlier aim
    r = click_nth(client, RHAND_NTH)
    ev["rhand"] = (r.get("baseX"), r.get("baseY"))
    ev["menu"] = sd_wait(lambda: top(client) == "ActionMenuState", 3.0)[0]
    time.sleep(SETTLE)
    press(client, KEY_SNAP)
    sd_wait(lambda: top(client) == "BattlescapeState", 3.0)
    ev["cursor"] = battle_state(client).get("cursorType")
    px = {}
    if ev["cursor"] != CURSOR_AIM:
        return ev, px
    press(client, SDLK_HOME)
    time.sleep(SETTLE)
    p = client.cmd({"cmd": "map_tile_click_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    ev["verified"] = p.get("verified")
    s = client.cmd({"cmd": "map_tile_screen_pos", "x": tile[0], "y": tile[1], "z": tile[2]})
    ev["screen"] = (s.get("screenX"), s.get("screenY"))
    region = {"x": (s.get("screenX") or 0) + AIM_REGION[0], "y": (s.get("screenY") or 0) + AIM_REGION[1],
              "w": AIM_REGION[2], "h": AIM_REGION[3]}
    ev["region"] = region
    time.sleep(SETTLE)
    px["noalt"] = client.cmd(dict({"cmd": "screen_pixels"}, **region)).get("pixels")
    client.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "alt"})
    time.sleep(0.5)
    px["alt"] = client.cmd(dict({"cmd": "screen_pixels"}, **region)).get("pixels")
    ev["modClear"] = sd_modnone(client)
    time.sleep(0.3)
    ev["len"] = (len(px["noalt"] or []), len(px["alt"] or []))
    ev["altVsNoalt"] = sd_diff(px["noalt"], px["alt"])
    click_nth(client, RHAND_NTH)   # F503: cancels the aim
    ev["cursorAfterCancel"] = battle_state(client).get("cursorType")
    return ev, px


def sd_cleanup(host, client):
    """Never leave an Alt latch or an open inventory behind a failed step."""
    for gc in (client, host):
        try:
            sd_modnone(gc)
            sd_close(gc)
        except Exception:
            pass


def c16r_i_inventory(host, client, ctx):
    G, H = ctx["G"], ctx["H"]
    notes = []
    aim0 = cancel_client_aim(client)
    before = snap(host, client)
    ids = sd_stage(host, client, G, H)
    gP, gH, hHv, hP = ids["gR"][0], ids["gL"][0], ids["hR"][0], ids["hL"][0]
    gGround = [ids["gGp"][0], ids["gGh"][0]]
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after staging: {short(e)}")
    c, h = {}, {}
    try:
        c["open"] = sd_open(client, G)
        if sd_opened(c["open"], G):
            c["hoverPistol"] = sd_hover(client, "STR_RIGHT_HAND", gP)
            c["hoverHeavy"] = sd_hover(client, "STR_LEFT_HAND", gH)
            c["altPistol"] = sd_hover(client, "STR_RIGHT_HAND", gP, mod="alt")
            c["altHeavy"] = sd_hover(client, "STR_LEFT_HAND", gH, mod="alt")
            c["psiLine"] = sd_at(sd_lw(client), PSI_LINE)
        c["close"] = sd_close(client)
        c["open2"] = sd_open(client, G)
        if sd_opened(c["open2"], G):
            c["searchPistol"] = sd_search(client, "pistol", gGround)
            c["searchArtifact"] = sd_search(client, "artifact", gGround)
        c["close2"] = sd_close(client)
        h["open"] = sd_open(host, H)
        if sd_opened(h["open"], H):
            h["hoverHeavy"] = sd_hover(host, "STR_RIGHT_HAND", hHv)
            h["hoverPistol"] = sd_hover(host, "STR_LEFT_HAND", hP)
            h["altHeavy"] = sd_hover(host, "STR_RIGHT_HAND", hHv, mod="alt")
            h["altPistol"] = sd_hover(host, "STR_LEFT_HAND", hP, mod="alt")
            h["psiLine"] = sd_at(sd_lw(host), PSI_LINE)
        h["close"] = sd_close(host)
    except Exception as e:
        notes.append(f"recipe: {type(e).__name__}: {short(e)}")
    finally:
        sd_cleanup(host, client)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    print(f"EVIDENCE C16r-i: G={G} H={H} aimCancel={aim0} ids={ids}; client(G)={c}; host(H)={h}; notes={notes}",
          flush=True)
    fails = list(notes)
    # recipe preconditions (reached on both builds in TASK 0)
    for who, d, uid, keys in (("client", c, G, ("open", "open2")), ("host", h, H, ("open",))):
        for k in keys:
            if not sd_opened(d.get(k) or {}, uid):
                fails.append(f"precondition: {who} battle_open_inventory {uid} ({k}) {d.get(k)} (want open, on top)")
        for k in [k for k in d if k.startswith(("hover", "alt"))]:
            if not sd_hover_ok(d[k], k.startswith("alt")):
                fails.append(f"precondition: {who} {k} pick/return {d[k]} (want picked from an empty cursor and "
                             f"returned)")
    for k in ("searchPistol", "searchArtifact"):
        s = c.get(k) or {}
        if (s.get("field") != [True] or s.get("top") != "InventoryState"
                or any(x in (None, HIDDEN_X) for x in list((s.get("before") or {}).values())
                       + list((s.get("cleared") or {}).values()))):
            fails.append(f"precondition: client {k} {s} (want the field shown, both ground items shown before "
                         f"and after the search, InventoryState on top)")
    # GREEN: G's inventory reads G's owner's research (D168 a)
    want_c = {"hoverPistol": f"{PISTOL_NAME} [{W_PISTOL}]", "hoverHeavy": f"{ARTIFACT} [{W_HEAVY}]",
              "altPistol": DMG_PISTOL, "altHeavy": ARTIFACT}
    for k, want in want_c.items():
        got = (c.get(k) or {}).get("item")
        if got != want:
            fails.append(f"client G {k} text {got!r} (want {want!r}: G's owner's research)")
    pl = c.get("psiLine") or []
    if len(pl) != 1 or not PSI_LINE_RE.fullmatch(pl[0].get("t") or ""):
        fails.append(f"client G psi-strength line (hidden widget) {pl} (want 'P.Str>\\x01<n>': G's owner has "
                     f"{PSI})")
    for k, shown, hidden in (("searchPistol", gGround[0], gGround[1]), ("searchArtifact", gGround[1], gGround[0])):
        ap = (c.get(k) or {}).get("applied") or {}
        if ap.get(shown) in (None, HIDDEN_X) or ap.get(hidden) != HIDDEN_X:
            fails.append(f"client quick search {(c.get(k) or {}).get('word')!r} ground x {ap} (want {shown} shown, "
                         f"{hidden} hidden: names by G's owner's research)")
    # host control: H's views by the host's research, both builds
    want_h = {"hoverHeavy": f"{HEAVY_NAME} [{W_HEAVY}]", "hoverPistol": f"{ARTIFACT} [{W_PISTOL}]",
              "altHeavy": DMG_HEAVY, "altPistol": ARTIFACT}
    for k, want in want_h.items():
        got = (h.get(k) or {}).get("item")
        if got != want:
            fails.append(f"host control H {k} text {got!r} (want {want!r})")
    fails += common_fails(host, client, before, "C16r-i")
    finish(fails)


def c16r_j_displays(host, client, ctx):
    G, H = ctx["G"], ctx["H"]
    notes = []
    aim0 = cancel_client_aim(client)
    tmax = tu_max_both(host, client, G)
    before = snap(host, client)
    ev, px1, px2 = {}, {}, {}
    tile = g_tile(ctx, AIM_TILE)
    try:
        ev["uiC"] = sd_unit_info(client, G)
        ev["uiH"] = sd_unit_info(host, H)
        ev["meleeC"] = sd_melee(client, G)
        ev["meleeH"] = sd_melee(host, H)
        # LAST STEP OF THE FILE (F3039): capture, discover into the client's LIVE world, capture again
        ev["aim1"], px1 = sd_aim_capture(client, G, tile)
        ev["discover"] = [{k: r.get(k) for k in ("ok", "researched", "error")}
                          for r in (client.cmd({"cmd": "discover_research", "topic": t}) for t in CLIENT_TOPICS)]
        ev["aim2"], px2 = sd_aim_capture(client, G, tile)
    except Exception as e:
        notes.append(f"recipe: {type(e).__name__}: {short(e)}")
    finally:
        sd_cleanup(host, client)
    ev["noaltDiff"] = sd_diff(px1.get("noalt"), px2.get("noalt"))
    ev["altDiff"] = sd_diff(px1.get("alt"), px2.get("alt"))
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    print(f"EVIDENCE C16r-j: G={G} H={H} tuMax={tmax} aimCancel={aim0} aimTile={tile} {ev}; notes={notes}",
          flush=True)
    fails = list(notes)
    # recipe preconditions (reached on both builds in TASK 0)
    for k, uid in (("uiC", G), ("uiH", H)):
        u = ev.get(k) or {}
        if not (u.get("tab") and len(u.get("statsNth") or []) == 1 and u.get("opened") and u.get("closed")):
            fails.append(f"precondition: {k} UnitInfoState on {uid} {u} (want TAB, one stats button, opened, closed)")
        elif len(u.get("label") or []) != 1 or len(u.get("value") or []) != 1:
            fails.append(f"precondition: {k} psi label/value widgets {u.get('label')} {u.get('value')} (want one each)")
    for k in ("meleeC", "meleeH"):
        m = ev.get(k) or {}
        if not (m.get("tab") and m.get("key") and m.get("opened") and m.get("state") == "InfoboxState"
                and m.get("closed")):
            fails.append(f"precondition: {k} melee preview {m} (want TAB, ctrl-M, InfoboxState read, auto-closed)")
    for k in ("aim1", "aim2"):
        a = ev.get(k) or {}
        if not (a.get("rhand") == RHAND_CENTRE and a.get("menu") and a.get("cursor") == CURSOR_AIM
                and a.get("verified") and a.get("len") == (AIM_REGION[2] * AIM_REGION[3],) * 2
                and a.get("modClear") and (a.get("altVsNoalt") or 0) > 0 and a.get("cursorAfterCancel") != CURSOR_AIM):
            fails.append(f"precondition: {k} Alt aiming capture {a} (want the snap aim, the selector parked, "
                         f"{AIM_REGION[2]}x{AIM_REGION[3]} px, the Alt text drawn, the aim cancelled)")
    if (ev.get("aim1") or {}).get("region") != (ev.get("aim2") or {}).get("region"):
        fails.append(f"precondition: capture regions differ {(ev.get('aim1') or {}).get('region')} vs "
                     f"{(ev.get('aim2') or {}).get('region')}")
    if ev.get("discover") != [{"ok": True, "researched": True, "error": None}] * len(CLIENT_TOPICS):
        fails.append(f"precondition: client discover_research {CLIENT_TOPICS} {ev.get('discover')} (want researched)")
    if ev["noaltDiff"] != 0:
        fails.append(f"pixel control: the no-Alt captures differ by {ev['noaltDiff']} px (want 0: the capture is "
                     f"stable; a flaky pixel result is a STOP, never a retry)")
    # GREEN (D213 b): the displays read G's owner's research
    u = ev.get("uiC") or {}
    lab, val = (u.get("label") or [{}])[0], (u.get("value") or [{}])[0]
    if not (lab.get("v") is True and val.get("v") is True and str(val.get("t") or "").isdigit()):
        fails.append(f"client UnitInfoState on G psi label {u.get('label')} value {u.get('value')} (want both shown, "
                     f"a number: G's owner has {PSI})")
    got = (ev.get("meleeC") or {}).get("texts")
    if got != [MELEE_G]:
        fails.append(f"client melee preview on G {got!r} (want {[MELEE_G]!r}: G's owner researched the pistol only)")
    if ev["altDiff"] != 0:
        fails.append(f"client Alt aiming preview: the Alt captures before/after the live-world discovery differ by "
                     f"{ev['altDiff']} px (want 0: G's display reads G's owner's research, not the live world)")
    # host control: H's displays by the host's research, both builds
    uh = ev.get("uiH") or {}
    if any(x.get("v") is not False for x in (uh.get("label") or []) + (uh.get("value") or [])):
        fails.append(f"host control H UnitInfoState psi label {uh.get('label')} value {uh.get('value')} (want hidden)")
    got = (ev.get("meleeH") or {}).get("texts")
    if got != [MELEE_H]:
        fails.append(f"host control H melee preview {got!r} (want {[MELEE_H]!r})")
    fails += common_fails(host, client, before, "C16r-j")
    finish(fails)


SCENARIOS = (("C16r-s", c16r_s_store), ("C16r-u", c16r_u_can_use), ("C16r", c16r_pistol), ("C16r-f", c16r_f_mode),
             ("C16r-m", c16r_m_mirror), ("C16r-h", c16r_h_admission), ("C16r-i", c16r_i_inventory),
             ("C16r-j", c16r_j_displays))


# ===================== bring-up =====================


def boot(host, client):
    ctx = {}
    pre_rec = {}

    def pre(h, c):
        for t in CLIENT_TOPICS:   # W2-P8 S-D1 boot extension: + PCLIP, PSI on the client
            c.ok({"cmd": "discover_research", "topic": t})
        for t in HOST_TOPICS:     # + HCLIP on the host
            h.ok({"cmd": "discover_research", "topic": t})
        pre_rec["isr"] = isr_all(h, c)
        pre_rec["Nh"] = (rmode(h) or {}).get("liveCount")
        pre_rec["Nc"] = (rmode(c) or {}).get("liveCount")

    host.spawn()
    host.connect()
    client.spawn()
    client.connect()
    session.bring_up_separate_guest_battle(host, client, port=PORT, pre_mission_start=pre)
    session.wait_host_idle(host, client, timeout=30)
    ctx["preIsr"], ctx["Nh"], ctx["Nc"] = pre_rec.get("isr"), pre_rec.get("Nh"), pre_rec.get("Nc")
    hs, cs = battle_state(host), battle_state(client)
    gh = [u for u in hs.get("units", []) if u.get("name") == GUEST_NAME]
    gc_ = [u for u in cs.get("units", []) if u.get("name") == GUEST_NAME]
    assert len(gh) == 1 and len(gc_) == 1 and gh[0]["id"] == gc_[0]["id"], (
        f"guest {GUEST_NAME!r} by name: host={[u.get('id') for u in gh]} client={[u.get('id') for u in gc_]} "
        f"(want exactly one, the same id)")
    g = gh[0]
    ctx["G"] = g["id"]
    ctx["gTile"] = (g["x"], g["y"], g["z"])
    hsold = sorted(u["id"] for u in hs.get("units", []) if u.get("isPlayerSoldier") and u.get("coop") == 0
                   and u.get("name") != GUEST_NAME and not u.get("isOut"))
    assert hsold, "no host soldier (coop 0, not out) for the W2-P8 S-D1 host control H"
    ctx["H"] = hsold[0]
    pinned = pin_ai_neutral(host, client, tag="w2p4r-sr")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    fp = both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": ctx["G"], "stat": "firing",
                             "value": FIRING_PIN}, ("tu",))
    for gc in (host, client):
        es = event_state(gc)
        assert isinstance(es.get("researchMode"), dict), (
            f"{gc.name} event_state lacks researchMode: {es.get('researchMode')!r}")
    session.wait_host_idle(host, client, timeout=30)
    session.assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p4r-sr] boot ok: G={ctx['G']} H={ctx['H']} tile={ctx['gTile']} dir={g.get('direction')} coop={g.get('coop')} "
          f"targets={ {k: g_tile(ctx, k) for k in TGT_OFF} } pinned={len(pinned)} firing={FIRING_PIN} ({fp.get('ok')}) "
          f"pre is_researched={ctx['preIsr']} Nh={ctx['Nh']} Nc={ctx['Nc']} mapFP={hs.get('mapFingerprint')}",
          flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49886, make_user_dir("w2p4r_client_research_host", options=HOST_OPTIONS))
    client = GameClient("client", 49887, make_user_dir("w2p4r_client_research_client", options=CLIENT_OPTIONS))
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
                print(f"[w2p4r-sr] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_client_research: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
