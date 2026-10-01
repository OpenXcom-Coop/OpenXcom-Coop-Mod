"""W2-P8b - test_w2_prebattle_equip_tools.py: the pre-battle bulk tools for the second
player (stage S-C). Owner D207 a: every pre-battle tool works for the second player,
each executed by the host - the template buttons, the personal and the global
layouts, clear and auto-equip become ONE tracked `inv_bulk` order each (op apply /
clear / autoequip) that the host performs; Q9 (a) / D209 a: a layout the second
player SAVES is host-executed in SHARED only - in a skirmish it stays local and is
lost after the battle (spec docs rewrite/prompts/w2p8b_prebattle_equip.md: the
draft's (f) EQ16-EQ20; AMENDMENT P8b-1 section 4 S-C (the pinned stage text),
section 5 (Boot C, rows EQ16-EQ20 (L)) and section 8; AMENDMENT P8b-2 (the TASK 0
constants F3326/F3327: staged items, never stock ids)).

Before S-C.2 (product untouched, commit S-C.1) every one of these tools runs vanilla's
code on the second player's own machine: the client's copy of the soldier changes,
nothing is sent, the host's copy stays as it was (P8b-1 section 5's RED cell
"client-local writes / nothing sent"). The rows are (L) rows (P8b-1 section 5): at
red each one writes on the client alone. They share this boot, so at red the
divergence accumulates; each row's RED cell is therefore judged on its OWN per-machine
change - the host's target soldier unchanged by the row, the client's changed by it,
no `inv_bulk` sent - never on a state an earlier row left behind. At red nothing is
sent at all, so no host ev reaches the client and no in-game desync freezes it.

Boot C (ONE boot, parallel turn mode, rows in this order; each row ONE run): the
roster-pinned lobby (set_seed SEED_ROSTER before open_new_battle),
session.bring_up_to_briefings (the client seated C1, C2; the host keeps H), set_seed
SEED_MAP right before newbattle_ok, the host's mapFingerprint = MAP_FP. The fixture
spine is fixed at red and green:
  [both briefings up] -> [staging] -> [EQ27's staging] -> [client close_briefing, host
  close_briefing: both pre-battle screens up, the host's equip-open announce] -> [the
  client saves C2's personal layout] -> EQ16 -> EQ17 -> EQ18 -> EQ19 -> EQ20 -> EQ27.
Staging (both briefings up, client first, F607; staged items only, P8b-2): C1 and C2
stripped on both machines; C1 gets L1 = a rifle loaded with a rifle clip in
STR_RIGHT_HAND + a grenade on STR_BELT (0,0); C2 gets L2 = a pistol loaded with a
pistol clip in STR_LEFT_HAND + a smoke grenade on STR_BELT (1,0) (battle_give); one
rifle, one rifle clip and one grenade dropped on PILE (battle_drop), so every apply
finds its types on the pile whatever the stock pile holds (F3327). A layout is
compared by its signature: per item (type, slot, slotX/slotY (hands: none), loaded
ammo types, fuse), sorted.
The personal save (spine): the client's screen on C2, key keyInvSavePersonalEquipment
(vanilla btnCreatePersonalTemplateClick; Q9 a: a skirmish save is the client's own).
Keys: the harness options.cfg (make_user_dir's HERMETIC_OPTIONS) pins none of the
inventory keys, so each is Options.cpp's default (read from the client's options.cfg
when present, else the pinned default below); the equip_layouts probe's live Options
values must equal them on both machines (a fixture check). The global layout keys are
vanilla's digits (InventoryState::handle: Ctrl+1..9 saves, 1..9 applies; key 1 = index
0).
  EQ16  template (the template buttons): the client's screen on C1 -> inventory_click
        {widget: create_template} (UI-local, vanilla) -> NEXT to C2 -> inventory_click
        {widget: apply_template}. GREEN: C2's layout = L1 on the host AND the client
        (the same item ids), the host's C2 changed, one `inv_bulk` sent (client
        coopIntentsSent) and received (host intentsReceivedLog), none denied; C1
        unchanged on both.
  EQ17  personal (keyInvLoadPersonalEquipment, a plain key: InteractiveSurface
        keyboardPress fires only without Ctrl/Alt/Shift): the client's screen on C2
        (L1 after EQ16) -> the key. GREEN: C2 = L2 (its personal layout) on both, the
        host's C2 changed, one `inv_bulk`; and the spine's save landed per Q9 (a) in a
        skirmish: the client's C2 personal layout = L2, the host's unchanged, no
        `inv_bulk` sent by the save.
  EQ18  global (P8b-1 section 5 "global Ctrl+1 then 1"): the client's screen on C1 ->
        Ctrl+1 (vanilla saveGlobalLayout(0)) -> NEXT to C2 -> 1 (loadGlobalLayout(0)).
        The save is made on C1 and applied on C2: saving and applying C2's own layout
        would leave C2 as it was and prove nothing. GREEN: C2 = L1 on both, the host's C2
        changed, one `inv_bulk` for the apply; the save landed per Q9 (a) in a
        skirmish: the client's global layout 0 = L1, the host's unchanged, no
        `inv_bulk` sent by the save.
  EQ19  clear (keyInvClear): the client's screen on C1 -> the key. GREEN: C1 empty on
        both, its items on PILE on both, one `inv_bulk`.
  EQ20  auto-equip (keyInvAutoEquip): the client's screen on C1 (empty after EQ19) ->
        the key. GREEN: C1 holds items (vanilla autoEquip from the pile) - the same ids
        and fields on both - the host's C1 changed, one `inv_bulk`.
  RED (commit S-C.1): exactly EQ16-EQ20 fail, each on its RED cell - the host's target
  soldier unchanged by the row while the client's changed to the tool's result, and no
  `inv_bulk` sent (buckets then differ). A row whose tool did not change the client's
  own copy fails for another reason (FIXTURE, stated in its message).
  EQ27  (stage S-C.3, P8b-2c ruling SC-4, follows vanilla): a template the pile cannot fill
        shows vanilla's STR_NOT_ENOUGH_ITEMS_FOR_TEMPLATE line ("Not enough items to copy
        template!", InventoryState::_applyInventoryTemplate) on the screen of the player
        who applied it - the `inv_bulk` answer carries the flag. The template is TWO
        proximity grenades (PROX_T) and the pile holds exactly ONE when the client applies
        it, so exactly one template item is missing:
          staging (the spine step after the S-C staging, both briefings up): the pile's
          stock PROX_T counted, then PROX_T dropped on PILE until it holds EQ27_PILE_PROX
          (3); H1 and H2 stripped, H1 = PROX_T on STR_BELT (0,0) and (1,0), H2 = PROX_T on
          STR_BELT (0,0) (battle_give; the host control below);
          the row: the client clears C1 and C2 (keyInvClear, EQ19's tool: C1's EQ20 items
          and C2's L1 go to the pile, so the pile holds all EQ27_PILE_PROX) -> on C2 two
          Ctrl-clicks on the pile's PROX_T cell (vanilla's ctrl_fit: two inv_move orders,
          C2 = two PROX_T, the pile keeps ONE) -> inventory_click {widget:
          create_template} (UI-local, vanilla) -> NEXT to C1 (empty) -> inventory_click
          {widget: apply_template}: the host finds one PROX_T for two template cells.
        GREEN: the client's line shows the text (inventory_view lineText + lineVisible,
        polled from the press until LINE_READ_S after the answer: the line fades 1.2 s
        after a show, F3112, so it is read inside that window; the +LINE_READ_S read is
        recorded as evidence only - P8b-2d SC-8); the host's and the client's C1 are equal
        and hold the partial template
        (one PROX_T in one of C2's two template cells), the pile holds no PROX_T on either
        machine, one `inv_bulk` sent and received, none denied. RED (product untouched,
        the host logs "not every template item was on the ground" and answers without the
        flag): the client's line never shows the text - the partial apply itself already
        happens.
        CONTROL (vanilla, passes at red): the HOST applies the same short template (its
        screen on H1 -> create_template -> NEXT to H2 -> apply_template; H2's own PROX_T is
        the only one it finds) and the host's own line shows the text.
  RED (commit S-C.3a): exactly EQ27 fails, on its RED cell; EQ16-EQ20 pass (S-C.2).

Common asserts, every row: hash_now {full:true} every bucket EQUAL after the queues
drain; desyncSeen false on both; the client's turnMirrorFired 0; coopClientBStatePushes
0 on both; the client's invLocalWrites 0; both pre-battle screens still up and turn 0
on both; the client's pre-battle ground ids = its own PILE ids (STOP-IF 8: the screen
shows the pile) and the PILE ids equal on both machines.

Constants (AMENDMENT P8b-2 / docs rewrite/w2p8b-task0/t0/logs, F3326): SEED_ROSTER 1,
SEED_MAP 1, MAP_FP, C [8, 9], H [10..14], PILE (14, 19, 1) - imported from
test_w2_prebattle_equip.py (Boot A's bring-up, the same seed).

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked, then
"PASS <id>" / "FAIL <id>: <message>" (the RED cell first); main() runs every row even
after an earlier one failed. Every wait is bounded. WV-D99 / WV-D100: one run is the
result; no skip path, no second boot. Exit 0 only when every row passes, 2 otherwise (a
bring-up or spine failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_prebattle_equip_tools.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state
from test_w2_delta_core import both, short, diff_buckets, desync_record
from test_w2_delta_items import items_by_id
from test_w2_host_combat import bring_up_lobby_roster_pinned
from test_w2_client_items import strip_both
from test_w2_prebattle_equip import (SEED_MAP, MAP_FP, C_IDS, C1, C2, H_IDS, PILE, COOP_SEAT_0, FACTION_PLAYER,
                                     BELT, RIGHT_HAND, LEFT_HAND, RIFLE_T, CLIP_T, GRENADE_T, EQ1_WAIT_S,
                                     ENTRY_WAIT_S, ANSWER_WAIT_S, LAND_WAIT_S, DRAIN_WAIT_S, stack, has, es,
                                     equip, turn, in_battle, inv_view, view_brief, ground_ids, pile_ids, wait_until,
                                     evidence, finish, click, goto_unit, drained, pre_screen_fails, ammo_of, GROUND,
                                     GROUND_COLS, CLICK_WAIT_S)

PORT = "48833"                     # this file's lobby port (unused by every other test file)
PISTOL_T, PISTOL_CLIP_T, SMOKE_T = "STR_PISTOL", "STR_PISTOL_CLIP", "STR_SMOKE_GRENADE"
HANDS = (RIGHT_HAND, LEFT_HAND)
# the staged layouts (battle_give, client first): C1 = L1, C2 = L2
L1_GIVE = ((RIFLE_T, {"ammo": CLIP_T}),                                   # STR_RIGHT_HAND (battle_give's default)
           (GRENADE_T, {"slot": BELT, "slotX": 0, "slotY": 0}))
L2_GIVE = ((PISTOL_T, {"slot": "left", "ammo": PISTOL_CLIP_T}),           # STR_LEFT_HAND
           (SMOKE_T, {"slot": BELT, "slotX": 1, "slotY": 0}))
PILE_DROPS = (RIFLE_T, CLIP_T, GRENADE_T)   # L1's types on the pile, whatever the stock pile holds (F3327)

# the inventory keys (Options.cpp at 8b17af3c5 :357-360 and :540-541; harness.py HERMETIC_OPTIONS :327-342 sets
# none of them): SDL syms, used only when the client's options.cfg does not carry the key
KEY_DEFAULTS = {"keyInvCreateTemplate": 99,           # SDLK_c (EQ16 clicks the button instead)
                "keyInvApplyTemplate": 118,           # SDLK_v (EQ16 clicks the button instead)
                "keyInvClear": 120,                   # SDLK_x (EQ19)
                "keyInvAutoEquip": 122,               # SDLK_z (EQ20)
                "keyInvSavePersonalEquipment": 115,   # SDLK_s (the spine's personal save)
                "keyInvLoadPersonalEquipment": 108}   # SDLK_l (EQ17)
SDLK_1 = 49                        # InventoryState::handle: SDLK_0..SDLK_9; key 1 = global layout index 0
GLOBAL_INDEX = 0
KEY_SETTLE_S = 0.3
# EQ27 (S-C.3, SC-4): the short template = two PROX_T; the pile holds EQ27_PILE_PROX of them after the staging, two
# go to C2 (the template), ONE is left for C1's apply
PROX_T = "STR_PROXIMITY_GRENADE"
EQ27_PILE_PROX = 3
H1, H2 = H_IDS[0], H_IDS[1]        # the host control: H1 = the template source, H2 = its target
TEXT_SHORT = "Not enough items to copy template!"   # STR_NOT_ENOUGH_ITEMS_FOR_TEMPLATE (xcom1 en-US / en-GB)
LINE_READ_S = 1.5                  # F3112: the line fades 1.2 s after a show; read inside it, record +1.5 s


# ===================== probes =====================


def layouts(gc, unit=None):
    req = {"cmd": "equip_layouts", "index": GLOBAL_INDEX}
    if unit is not None:
        req["unit"] = unit
    r = gc.cmd(req)
    return {k: r.get(k) for k in ("ok", "error", "global", "globalArmor", "soldier", "personal", "personalArmor",
                                  "keys")}


def sent_bulk(gc):
    return int((es(gc).get("coopIntentsSent") or {}).get("inv_bulk", 0))


def host_bulk_log(gc):
    return [e for e in (es(gc).get("intentsReceivedLog") or []) if e.get("kind") == "inv_bulk"]


def host_bulk_denied(gc):
    return int(((es(gc).get("intentsReceived") or {}).get("inv_bulk") or {}).get("denied", 0))


def unit_items(its, uid):
    return {i: it for i, it in its.items() if it.get("owner") == uid and it.get("slot")}


def item_sig(its, iid):
    it = its[iid]
    hand = it.get("slot") in HANDS
    ammo = tuple(sorted((its.get(a) or {}).get("type", "?") for a in ammo_of(it, iid)))
    return [it.get("type"), it.get("slot"), -1 if hand else it.get("slotX"), -1 if hand else it.get("slotY"),
            list(ammo), it.get("fuse")]


def unit_sig(its, uid):
    return sorted(item_sig(its, i) for i in unit_items(its, uid))


def layout_sig(layout):
    out = []
    for li in layout or []:
        hand = li.get("slot") in HANDS
        out.append([li.get("type"), li.get("slot"), -1 if hand else li.get("x"), -1 if hand else li.get("y"),
                    sorted(li.get("ammo") or []), li.get("fuse")])
    return sorted(out)


def unit_dump(its, uid):
    """The unit's inventory items and their loaded ammo, every probed field (the host = client check)."""
    ids = set(unit_items(its, uid))
    for i in list(ids):
        ids |= set(ammo_of(its[i], i))
    return {i: its.get(i) for i in sorted(ids)}


def key(gc, sym, mod=None):
    req = {"cmd": "inject_input", "kind": "key", "key": sym}
    if mod:
        req["mod"] = mod
    r = gc.cmd(req)
    return {"key": sym, "mod": mod, "ok": r.get("ok"), "error": r.get("error")}


def clear_mod(gc):
    r = gc.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    return {"ok": r.get("ok"), "error": r.get("error")}


def harness_keys(gc):
    """The six inventory keys from this machine's harness options.cfg; a key the file does not carry is
    Options.cpp's default (KEY_DEFAULTS). Returns {name: [sym, source]}."""
    path = os.path.join(gc.user_dir, "options.cfg")
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    found = {}
    for line in lines:
        name, sep, value = line.strip().partition(":")
        if sep and name in KEY_DEFAULTS:
            found[name] = int(value.strip())
    return {n: ([found[n], "options.cfg"] if n in found else [d, "Options.cpp default"]) for n, d in KEY_DEFAULTS.items()}


# ===================== the common tail =====================


def tail_fails(host, client, what):
    """Every row's common asserts (both machines hold the battle)."""
    if not (in_battle(host) and in_battle(client)):
        return [f"{what}: common asserts not run - a machine holds no battle (host inBattle {in_battle(host)}, "
                f"client inBattle {in_battle(client)})"]
    fails = []
    got, _ = wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    if not got:
        fails.append(f"{what}: the client never caught up (host lastSeqEmitted {es(host).get('lastSeqEmitted')}, "
                     f"client lastSeqApplied {es(client).get('lastSeqApplied')})")
    d = diff_buckets(host, client)
    if d:
        fails.append(f"{what}: hash_now full buckets differ: {d} (want every bucket EQUAL)")
    eh, ec = es(host), es(client)
    if eh.get("desyncSeen") or ec.get("desyncSeen"):
        fails.append(f"{what}: desyncSeen host={eh.get('desyncSeen')} client={ec.get('desyncSeen')} "
                     f"({desync_record(client, ec.get('desyncSeen'))}; want false on both)")
    if ec.get("turnMirrorFired") != 0:
        fails.append(f"{what}: client turnMirrorFired={ec.get('turnMirrorFired')} (want 0)")
    if ec.get("coopClientBStatePushes") != 0 or eh.get("coopClientBStatePushes") != 0:
        fails.append(f"{what}: coopClientBStatePushes host={eh.get('coopClientBStatePushes')} "
                     f"client={ec.get('coopClientBStatePushes')} (want 0 on both)")
    if ec.get("invLocalWrites") != 0:
        fails.append(f"{what}: client invLocalWrites={ec.get('invLocalWrites')} (want 0)")
    ih, ic = items_by_id(host), items_by_id(client)
    cv = inv_view(client)
    if cv.get("open") and cv.get("preBattle") and ground_ids(cv) != pile_ids(ic):
        fails.append(f"{what}: STOP-IF 8 - the client's pre-battle ground {ground_ids(cv)} is not its own pile "
                     f"{PILE} {pile_ids(ic)}")
    if pile_ids(ih) != pile_ids(ic):
        fails.append(f"{what}: the pile ids differ: host {pile_ids(ih)} client {pile_ids(ic)}")
    return fails


# ===================== the spine =====================


def spine_both_briefings(host, client, ctx):
    """Both machines hold the battle with their briefings up (D210 b; S-A built it)."""
    got, dt = wait_until(lambda: has(client, "BriefingState") and in_battle(client), EQ1_WAIT_S, 0.1)
    rec = {"clientBriefingWithin": dt if got else None, "hostStack": stack(host), "clientStack": stack(client),
           "turn": [turn(host), turn(client)], "mapFingerprint": battle_state(client).get("mapFingerprint")}
    print(f"SPINE both briefings: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not got or not has(host, "BriefingState"):
        raise AssertionError(f"spine: both briefings are not up (client within {rec['clientBriefingWithin']}, host "
                             f"stack {rec['hostStack']}, client stack {rec['clientStack']})")
    if rec["mapFingerprint"] != MAP_FP:
        raise AssertionError(f"spine: client mapFingerprint {rec['mapFingerprint']!r} (want {MAP_FP!r})")


def spine_stage(host, client, ctx):
    """Staging (client first, F607; staged items only, P8b-2), the keys, the saved-layout baselines."""
    rec = {"ids": {}}
    ctx["staged"] = rec
    try:
        rec["stripped"] = {uid: strip_both(host, client, uid) for uid in (C1, C2)}
        for uid, gives in ((C1, L1_GIVE), (C2, L2_GIVE)):
            for t, extra in gives:
                req = {"cmd": "battle_give", "unit": uid, "item": t}
                req.update(extra)
                r = both(host, client, req, ("weaponId", "ammoId", "weaponSlot"))
                rec["ids"][f"{uid}:{t}"] = [r["weaponId"], r["ammoId"], r["weaponSlot"]]
        drops = []
        for t in PILE_DROPS:
            d = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": t},
                     ("ids",))
            drops.append([t, d["ids"][0]])
        rec["drops"] = drops
        rec["diff"] = diff_buckets(host, client)
        ih, ic = items_by_id(host), items_by_id(client)
        rec["sigL1"] = unit_sig(ih, C1)
        rec["sigL2"] = unit_sig(ih, C2)
        rec["sigClient"] = [unit_sig(ic, C1), unit_sig(ic, C2)]
        rec["turn"] = [turn(host), turn(client)]
        keys = harness_keys(client)
        rec["keys"] = keys
        rec["liveKeys"] = {"host": layouts(host).get("keys"), "client": layouts(client).get("keys")}
        rec["baseline"] = {"host": {"C1": layouts(host, C1), "C2": layouts(host, C2)},
                           "client": {"C1": layouts(client, C1), "C2": layouts(client, C2)}}
    except Exception as e:
        rec["error"] = short(e, 400)
    print(f"STAGE {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if rec.get("error"):
        raise AssertionError(f"spine: the staging failed: {rec['error']}")
    if rec["diff"]:
        raise AssertionError(f"spine: buckets differ after the staging: {rec['diff']}")
    if rec["sigClient"] != [rec["sigL1"], rec["sigL2"]] or not rec["sigL1"] or not rec["sigL2"]:
        raise AssertionError(f"spine: the staged layouts host L1 {rec['sigL1']} L2 {rec['sigL2']} client "
                             f"{rec['sigClient']} (want equal and non-empty)")
    want_keys = {n: v[0] for n, v in rec["keys"].items()}
    for side in ("host", "client"):
        if rec["liveKeys"][side] != want_keys:
            raise AssertionError(f"spine: FIXTURE - the {side}'s live inventory keys {rec['liveKeys'][side]} != the "
                                 f"harness options.cfg keys {want_keys}")
    ctx["keys"] = want_keys


def prox_on_pile(its):
    return sorted(i for i in pile_ids(its) if its[i].get("type") == PROX_T)


def spine_stage_eq27(host, client, ctx):
    """EQ27's staging (both briefings up, client first, F607; staged items only, P8b-2): the pile's stock PROX_T
    counted, then PROX_T dropped on PILE until it holds EQ27_PILE_PROX; H1 and H2 stripped, then H1 = PROX_T on
    STR_BELT (0,0) and (1,0) (the host control's template source) and H2 = PROX_T on STR_BELT (0,0) (its target)."""
    rec = {}
    ctx["eq27"] = rec
    try:
        ih, ic = items_by_id(host), items_by_id(client)
        rec["stockOnPile"] = {"host": prox_on_pile(ih), "client": prox_on_pile(ic)}
        if rec["stockOnPile"]["host"] != rec["stockOnPile"]["client"]:
            raise AssertionError(f"the pile's stock {PROX_T} differs: {rec['stockOnPile']}")
        need = EQ27_PILE_PROX - len(rec["stockOnPile"]["host"])
        if need < 0:
            raise AssertionError(f"the pile already holds {rec['stockOnPile']['host']} {PROX_T} (want <= "
                                 f"{EQ27_PILE_PROX})")
        drops = []
        for _ in range(need):
            d = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": PROX_T},
                     ("ids",))
            drops.append(d["ids"][0])
        rec["drops"] = drops
        rec["hStripped"] = {uid: strip_both(host, client, uid) for uid in (H1, H2)}
        gives = {}
        for uid, cells in ((H1, ((0, 0), (1, 0))), (H2, ((0, 0),))):
            for x, y in cells:
                r = both(host, client, {"cmd": "battle_give", "unit": uid, "item": PROX_T, "slot": BELT, "slotX": x,
                                        "slotY": y}, ("weaponId", "ammoId", "weaponSlot"))
                gives.setdefault(str(uid), []).append(r["weaponId"])
        rec["gives"] = gives
        rec["diff"] = diff_buckets(host, client)
        ih, ic = items_by_id(host), items_by_id(client)
        rec["pileProx"] = {"host": prox_on_pile(ih), "client": prox_on_pile(ic)}
        rec["sigH1"], rec["sigH2"] = unit_sig(ih, H1), unit_sig(ih, H2)
        rec["sigH1H2Client"] = [unit_sig(ic, H1), unit_sig(ic, H2)]
    except Exception as e:
        rec["error"] = short(e, 400)
    print(f"STAGE EQ27 {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if rec.get("error"):
        raise AssertionError(f"spine: EQ27's staging failed: {rec['error']}")
    if rec["diff"]:
        raise AssertionError(f"spine: buckets differ after EQ27's staging: {rec['diff']}")
    if len(rec["pileProx"]["host"]) != EQ27_PILE_PROX or rec["pileProx"]["host"] != rec["pileProx"]["client"]:
        raise AssertionError(f"spine: the pile's {PROX_T} {rec['pileProx']} (want {EQ27_PILE_PROX}, equal)")
    if rec["sigH1H2Client"] != [rec["sigH1"], rec["sigH2"]] or len(rec["sigH1"]) != 2 or len(rec["sigH2"]) != 1:
        raise AssertionError(f"spine: H1 {rec['sigH1']} H2 {rec['sigH2']} client {rec['sigH1H2Client']} (want two and "
                             f"one {PROX_T}, equal)")


def spine_open_screens(host, client, ctx):
    """The client closes its briefing (its pre-battle screen opens), then the host (its screen opens, the equip
    phase is announced)."""
    rec = {}
    ctx["screens"] = rec
    c = client.cmd({"cmd": "close_briefing"})
    g1, d1 = wait_until(lambda: inv_view(client).get("preBattle") is True and inv_view(client).get("top") is True,
                        ENTRY_WAIT_S)
    h = host.cmd({"cmd": "close_briefing"})
    g2, d2 = wait_until(lambda: inv_view(host).get("preBattle") is True and inv_view(host).get("top") is True, 10.0)
    g3, d3 = wait_until(lambda: equip(host).get("openAnnounced") is True, ANSWER_WAIT_S)
    rec.update({"clientClose": {k: c.get(k) for k in ("ok", "error")}, "clientScreenWithin": d1 if g1 else None,
                "hostClose": {k: h.get(k) for k in ("ok", "error")}, "hostScreenWithin": d2 if g2 else None,
                "announcedWithin": d3 if g3 else None, "clientView": view_brief(inv_view(client)),
                "hostView": view_brief(inv_view(host)), "hostEquip": equip(host), "clientEquip": equip(client),
                "turn": [turn(host), turn(client)]})
    print(f"SPINE screens: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not (g1 and g2 and g3):
        raise AssertionError(f"spine: the pre-battle screens are not both up and announced ({rec})")


def spine_save_personal(host, client, ctx):
    """The client's screen on C2 (L2), its personal-save key: vanilla btnCreatePersonalTemplateClick on the client
    (Q9 a in a skirmish). EQ17 judges where it landed; here only that the client's own copy took it."""
    rec = {}
    ctx["personal"] = rec
    nav = []
    rec["toC2"] = {"reached": goto_unit(client, C2, C_IDS, nav), "presses": nav}
    s0 = sent_bulk(client)
    rec["before"] = {"host": layouts(host, C2), "client": layouts(client, C2)}
    if rec["toC2"]["reached"]:
        time.sleep(KEY_SETTLE_S)
        rec["press"] = key(client, ctx["keys"]["keyInvSavePersonalEquipment"])
        got, dt = wait_until(lambda: layouts(client, C2).get("personal"), ANSWER_WAIT_S)
        rec["within"] = dt if got else None
    rec["line"] = {"text": inv_view(client).get("lineText"), "visible": inv_view(client).get("lineVisible")}
    rec["after"] = {"host": layouts(host, C2), "client": layouts(client, C2)}
    rec["sentBulk"] = [s0, sent_bulk(client)]
    back = []
    rec["backToC1"] = {"reached": goto_unit(client, C1, C_IDS, back), "presses": back}
    print(f"SPINE personal save: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not rec.get("within"):
        raise AssertionError(f"spine: the client's personal-save key left C2's personal layout "
                             f"{rec['after']['client'].get('personal')} on the client (want L2)")
    if not rec["backToC1"]["reached"]:
        raise AssertionError(f"spine: PREV/NEXT never returned to C1 ({back})")


# ===================== the rows =====================


def row_pre(host, client, ctx, row, uid):
    """Both pre-battle screens up, the spine done, the client's screen on `uid` with an empty cursor."""
    fails = pre_screen_fails(host, client, row, host_too=True)
    s = ctx.get("staged") or {}
    if not s.get("sigL1") or s.get("error") or s.get("diff") or not ctx.get("keys"):
        fails.append(f"{row}: the staging did not complete ({s.get('error')}, diff {s.get('diff')})")
    nav = []
    if not fails:
        if not goto_unit(client, uid, C_IDS, nav):
            fails.append(f"{row}: PREV/NEXT never reached {uid} on the client ({nav})")
        elif inv_view(client).get("selectedItem") != -1:
            fails.append(f"{row}: the client's cursor holds {inv_view(client).get('selectedItem')} (want empty)")
    return fails, nav


def snapshot(host, client):
    ih, ic = items_by_id(host), items_by_id(client)
    log = host_bulk_log(host)
    return {"ih": ih, "ic": ic, "sent": sent_bulk(client), "logIseqs": [e.get("iseq") for e in log],
            "denied": host_bulk_denied(host), "lastDeny": es(client).get("lastDeny"),
            "line": es(client).get("invLastWarning")}


def run_tool(host, client, ctx, row, target, other, press, want, want_text):
    """Press one bulk tool on the client (`press(ev)`), then wait (bounded) for the green outcome: the host's
    `target` layout satisfies `want(sig, host_pre_sig)`, the client's copy of `target` equals the host's (ids and
    fields), the pile ids equal, nothing in flight. Returns (ev, fails) with the RED cell first."""
    b = snapshot(host, client)
    ev = {"target": target, "want": want_text}
    press(ev)
    hpre, cpre = unit_sig(b["ih"], target), unit_sig(b["ic"], target)

    def landed():
        ih, ic = items_by_id(host), items_by_id(client)
        return (want(unit_sig(ih, target), hpre) and unit_dump(ih, target) == unit_dump(ic, target)
                and pile_ids(ih) == pile_ids(ic) and es(client).get("inFlight") is None)

    got, dt = wait_until(landed, LAND_WAIT_S, 0.1)
    ih, ic = items_by_id(host), items_by_id(client)
    hpost, cpost = unit_sig(ih, target), unit_sig(ic, target)
    new_log = [e for e in host_bulk_log(host) if e.get("iseq") not in b["logIseqs"]]
    sent = sent_bulk(client) - b["sent"]
    ev.update({"landedWithin": dt if got else None,
               "host": {"pre": hpre, "post": hpost}, "client": {"pre": cpre, "post": cpost},
               "hostDump": unit_dump(ih, target), "clientDump": unit_dump(ic, target),
               "other": {"uid": other, "hostPre": unit_sig(b["ih"], other), "hostPost": unit_sig(ih, other),
                         "clientPre": unit_sig(b["ic"], other), "clientPost": unit_sig(ic, other)},
               "invBulkSent": sent, "hostInvBulkLog": new_log,
               "hostInvBulkDenied": [b["denied"], host_bulk_denied(host)],
               "clientLastDeny": [b["lastDeny"], es(client).get("lastDeny")],
               "clientLine": [b["line"], es(client).get("invLastWarning"), inv_view(client).get("lineText")],
               "inFlight": es(client).get("inFlight"), "pile": {"host": pile_ids(ih), "client": pile_ids(ic)},
               "views": {"host": view_brief(inv_view(host)), "client": view_brief(inv_view(client))},
               "turn": [turn(host), turn(client)]})
    fails = []
    if hpost == hpre:
        fails.append(f"{row}: the host's {target} did not change ({hpre}) - RED: the client wrote alone (the client's "
                     f"{target} {cpre} -> {cpost}) and sent {sent} inv_bulk (want: the host performs one inv_bulk, "
                     f"{want_text})")
    elif not want(hpost, hpre):
        fails.append(f"{row}: the host's {target} {hpre} -> {hpost} (want {want_text})")
    if not want(cpost, cpre):
        fails.append(f"{row}: FIXTURE - the client's {target} {cpre} -> {cpost} (want {want_text}): the tool did not "
                     f"change the client's copy")
    if sent != 1:
        fails.append(f"{row}: client coopIntentsSent.inv_bulk +{sent} (want +1: one inv_bulk order)")
    if len(new_log) != 1:
        fails.append(f"{row}: the host received {len(new_log)} inv_bulk ({new_log}; want 1)")
    if ev["hostInvBulkDenied"][1] != ev["hostInvBulkDenied"][0]:
        fails.append(f"{row}: the host denied inv_bulk {ev['hostInvBulkDenied']} (want none)")
    if ev["hostDump"] != ev["clientDump"]:
        fails.append(f"{row}: {target}'s items differ: host {ev['hostDump']} client {ev['clientDump']}")
    o = ev["other"]
    if o["hostPost"] != o["hostPre"] or o["clientPost"] != o["clientPre"]:
        fails.append(f"{row}: the other soldier {other} changed: host {o['hostPre']} -> {o['hostPost']}, client "
                     f"{o['clientPre']} -> {o['clientPost']} (want unchanged)")
    if ev["inFlight"] is not None:
        fails.append(f"{row}: the client still has an order in flight {ev['inFlight']}")
    for side, v in ev["views"].items():
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"{row}: the {side}'s pre-battle screen is not on top ({v})")
    if ev["turn"] != [0, 0]:
        fails.append(f"{row}: turn host/client {ev['turn']} (want 0 on both)")
    return ev, fails


def is_sig(want_sig):
    return lambda sig, pre: sig == want_sig


def eq16_template(host, client, ctx):
    fails, nav = row_pre(host, client, ctx, "EQ16", C1)
    if fails:
        evidence("EQ16", {"nav": nav})
        finish([f.replace("EQ16: ", "EQ16: precondition absent - ") for f in fails])
    s = ctx["staged"]

    def press(ev):
        time.sleep(KEY_SETTLE_S)
        ev["create"] = click(client, widget="create_template")
        time.sleep(KEY_SETTLE_S)
        to = []
        ev["toC2"] = {"reached": goto_unit(client, C2, C_IDS, to), "presses": to}
        time.sleep(KEY_SETTLE_S)
        ev["apply"] = click(client, widget="apply_template")

    ev, fails = run_tool(host, client, ctx, "EQ16", C2, C1, press, is_sig(s["sigL1"]),
                         f"C1's staged layout L1 {s['sigL1']}")
    evidence("EQ16", ev)
    if not ev["toC2"]["reached"]:
        fails.append(f"EQ16: NEXT never reached C2 ({ev['toC2']})")
    fails += tail_fails(host, client, "EQ16")
    finish(fails)


def eq17_personal(host, client, ctx):
    fails, nav = row_pre(host, client, ctx, "EQ17", C2)
    p = ctx.get("personal") or {}
    if not p.get("within"):
        fails.append(f"EQ17: the spine's personal save did not land on the client ({p.get('after')})")
    if fails:
        evidence("EQ17", {"nav": nav, "personal": p})
        finish([f.replace("EQ17: ", "EQ17: precondition absent - ") for f in fails])
    s = ctx["staged"]
    base = s["baseline"]["host"]["C2"]
    q9 = {"clientPersonal": layout_sig(layouts(client, C2).get("personal")),
          "hostPersonal": layout_sig(layouts(host, C2).get("personal")),
          "hostBaseline": layout_sig(base.get("personal")), "saveSentBulk": p.get("sentBulk"),
          "clientSoldier": layouts(client, C2).get("soldier"), "hostSoldier": base.get("soldier")}

    def press(ev):
        time.sleep(KEY_SETTLE_S)
        ev["press"] = key(client, ctx["keys"]["keyInvLoadPersonalEquipment"])

    ev, fails = run_tool(host, client, ctx, "EQ17", C2, C1, press, is_sig(s["sigL2"]),
                         f"C2's personal layout = its staged layout L2 {s['sigL2']}")
    ev["q9"] = q9
    evidence("EQ17", ev)
    # Q9 (a) / D209 a in a skirmish: the save is the client's own - landed on its copy, not on the host's, not sent
    if q9["clientPersonal"] != s["sigL2"]:
        fails.append(f"EQ17: the client's C2 personal layout {q9['clientPersonal']} (want L2 {s['sigL2']}: the save "
                     f"landed on the client, Q9 a)")
    if q9["hostPersonal"] != q9["hostBaseline"]:
        fails.append(f"EQ17: the host's C2 personal layout {q9['hostBaseline']} -> {q9['hostPersonal']} (want "
                     f"unchanged: a skirmish save stays on the client, Q9 a / D209 a)")
    if (p.get("sentBulk") or [0, 0])[1] != (p.get("sentBulk") or [0, 0])[0]:
        fails.append(f"EQ17: the personal save sent inv_bulk {p.get('sentBulk')} (want nothing sent in a skirmish)")
    fails += tail_fails(host, client, "EQ17")
    finish(fails)


def eq18_global(host, client, ctx):
    fails, nav = row_pre(host, client, ctx, "EQ18", C1)
    if fails:
        evidence("EQ18", {"nav": nav})
        finish([f.replace("EQ18: ", "EQ18: precondition absent - ") for f in fails])
    s = ctx["staged"]
    base = s["baseline"]["host"]["C1"]
    save = {"hostBefore": layout_sig(layouts(host).get("global")),
            "clientBefore": layout_sig(layouts(client).get("global")),
            "c1Client": unit_sig(items_by_id(client), C1)}

    def press(ev):
        s0 = sent_bulk(client)
        time.sleep(KEY_SETTLE_S)
        save["ctrl1"] = key(client, SDLK_1, mod="ctrl")
        got, dt = wait_until(lambda: layouts(client).get("global"), ANSWER_WAIT_S)
        save["savedWithin"] = dt if got else None
        save["clearMod"] = clear_mod(client)
        save["sentBulk"] = [s0, sent_bulk(client)]
        save["clientAfter"] = layout_sig(layouts(client).get("global"))
        save["hostAfter"] = layout_sig(layouts(host).get("global"))
        to = []
        ev["toC2"] = {"reached": goto_unit(client, C2, C_IDS, to), "presses": to}
        time.sleep(KEY_SETTLE_S)
        ev["press1"] = key(client, SDLK_1)

    ev, fails = run_tool(host, client, ctx, "EQ18", C2, C1, press, is_sig(s["sigL1"]),
                         f"global layout {GLOBAL_INDEX} = C1's layout L1 {s['sigL1']}")
    save["hostLate"] = layout_sig(layouts(host).get("global"))
    save["hostBaseline"] = layout_sig(base.get("global"))
    ev["save"] = save
    evidence("EQ18", ev)
    if not ev["toC2"]["reached"]:
        fails.append(f"EQ18: NEXT never reached C2 ({ev['toC2']})")
    # Q9 (a) / D209 a in a skirmish: the save is the client's own - landed on its copy, not on the host's, not sent
    if save.get("savedWithin") is None or save["clientAfter"] != s["sigL1"]:
        fails.append(f"EQ18: the client's global layout {GLOBAL_INDEX} after Ctrl+1 {save['clientAfter']} (want C1's "
                     f"layout L1 {s['sigL1']}: the save landed on the client, Q9 a)")
    if save["hostAfter"] != save["hostBaseline"] or save["hostLate"] != save["hostBaseline"]:
        fails.append(f"EQ18: the host's global layout {GLOBAL_INDEX} {save['hostBaseline']} -> {save['hostAfter']} / "
                     f"{save['hostLate']} (want unchanged: a skirmish save stays on the client, Q9 a / D209 a)")
    if save["sentBulk"][1] != save["sentBulk"][0]:
        fails.append(f"EQ18: the Ctrl+1 save sent inv_bulk {save['sentBulk']} (want nothing sent in a skirmish)")
    fails += tail_fails(host, client, "EQ18")
    finish(fails)


def eq19_clear(host, client, ctx):
    fails, nav = row_pre(host, client, ctx, "EQ19", C1)
    if fails:
        evidence("EQ19", {"nav": nav})
        finish([f.replace("EQ19: ", "EQ19: precondition absent - ") for f in fails])

    def press(ev):
        time.sleep(KEY_SETTLE_S)
        ev["press"] = key(client, ctx["keys"]["keyInvClear"])

    b_items = items_by_id(host)
    c1_ids = sorted(unit_items(b_items, C1))
    ev, fails = run_tool(host, client, ctx, "EQ19", C1, C2, press, is_sig([]), "C1 empty")
    ih, ic = items_by_id(host), items_by_id(client)
    ev["c1ItemsOnPile"] = {"ids": c1_ids, "host": [i for i in c1_ids if i in pile_ids(ih)],
                           "client": [i for i in c1_ids if i in pile_ids(ic)]}
    evidence("EQ19", ev)
    if ev["c1ItemsOnPile"]["host"] != c1_ids or ev["c1ItemsOnPile"]["client"] != c1_ids:
        fails.append(f"EQ19: C1's items {c1_ids} on the pile: host {ev['c1ItemsOnPile']['host']} client "
                     f"{ev['c1ItemsOnPile']['client']} (want all of them on both)")
    fails += tail_fails(host, client, "EQ19")
    finish(fails)


def eq20_autoequip(host, client, ctx):
    fails, nav = row_pre(host, client, ctx, "EQ20", C1)
    if fails:
        evidence("EQ20", {"nav": nav})
        finish([f.replace("EQ20: ", "EQ20: precondition absent - ") for f in fails])

    def press(ev):
        time.sleep(KEY_SETTLE_S)
        ev["press"] = key(client, ctx["keys"]["keyInvAutoEquip"])

    ev, fails = run_tool(host, client, ctx, "EQ20", C1, C2, press, lambda sig, pre: bool(sig) and sig != pre,
                         "C1 auto-equipped from the pile (non-empty, changed)")
    evidence("EQ20", ev)
    fails += tail_fails(host, client, "EQ20")
    finish(fails)


def prox_cells(its, uid):
    """The (slot, slotX, slotY) of every PROX_T `uid` holds, sorted."""
    return sorted((it.get("slot"), it.get("slotX"), it.get("slotY")) for i, it in unit_items(its, uid).items()
                  if it.get("type") == PROX_T)


def settled(host, client, uid, want):
    """`want(host sig of uid)` holds, the unit's items and the pile ids equal on both, nothing in flight."""
    ih, ic = items_by_id(host), items_by_id(client)
    return (want(unit_sig(ih, uid)) and unit_dump(ih, uid) == unit_dump(ic, uid) and pile_ids(ih) == pile_ids(ic)
            and es(client).get("inFlight") is None)


def watch_line(gc, text, t0, stop):
    """Poll `gc`'s inventory line from t0 until `stop(now)` is true: the first time it shows `text` visibly
    (seconds after t0) or None, and the last read."""
    seen, last = None, {}
    while True:
        v = inv_view(gc)
        last = {"text": v.get("lineText"), "visible": v.get("lineVisible")}
        now = time.time() - t0
        if seen is None and last["text"] == text and last["visible"] is True:
            seen = round(now, 3)
        if stop(now, seen):
            return seen, last
        time.sleep(0.05)


def eq27_template_short(host, client, ctx):
    fails = pre_screen_fails(host, client, "EQ27", host_too=True)
    st = ctx.get("eq27") or {}
    if st.get("error") or st.get("diff") or not st.get("gives") or not ctx.get("keys"):
        fails.append(f"EQ27: the staging did not complete (EQ27 {st.get('error')}, diff {st.get('diff')}, keys "
                     f"{bool(ctx.get('keys'))})")
    ev = {"staged": {k: st.get(k) for k in ("stockOnPile", "drops", "gives", "pileProx")}}
    if fails:
        evidence("EQ27", ev)
        finish([f.replace("EQ27: ", "EQ27: precondition absent - ") for f in fails])
    known_prox = set(st["stockOnPile"]["host"]) | set(st["drops"])   # C7: the staging record's ids
    keys = ctx["keys"]
    setup = {}
    ev["setup"] = setup
    pre = []
    # 1. the client clears C1 (EQ20's items) and C2 (L1): every PROX_T of the pile is on the pile again
    for uid in (C1, C2):
        nav = []
        rec = {"reached": goto_unit(client, uid, C_IDS, nav), "nav": nav}
        if rec["reached"]:
            time.sleep(KEY_SETTLE_S)
            rec["press"] = key(client, keys["keyInvClear"])
            got, dt = wait_until(lambda: settled(host, client, uid, lambda sig: sig == []), LAND_WAIT_S, 0.1)
            rec["emptyWithin"] = dt if got else None
        setup[f"clear{uid}"] = rec
        if not rec.get("emptyWithin"):
            pre.append(f"EQ27: the client's clear of {uid} did not land empty on both ({rec})")
    ih, ic = items_by_id(host), items_by_id(client)
    setup["pileProx"] = {"host": prox_on_pile(ih), "client": prox_on_pile(ic)}
    if not pre and (len(setup["pileProx"]["host"]) != EQ27_PILE_PROX
                    or setup["pileProx"]["host"] != setup["pileProx"]["client"]):
        pre.append(f"EQ27: the pile's {PROX_T} after the clears {setup['pileProx']} (want {EQ27_PILE_PROX}, equal)")
    # 2. on C2: two Ctrl-clicks on the pile's PROX_T cell (vanilla ctrl_fit, two inv_move orders)
    moves = []
    setup["moves"] = moves
    if not pre:
        nav = []
        setup["toC2"] = {"reached": goto_unit(client, C2, C_IDS, nav), "nav": nav}
        if not setup["toC2"]["reached"]:
            pre.append(f"EQ27: PREV/NEXT never reached C2 on the client ({nav})")
    for n in ((1, 2) if not pre else ()):
        m = {}
        moves.append(m)
        v, its = inv_view(client), items_by_id(client)
        cells = [(g.get("x"), g.get("y"), g.get("id")) for g in (v.get("ground") or [])
                 if (its.get(g.get("id")) or {}).get("type") == PROX_T]
        m["cells"] = cells
        if not cells or cells[0][0] is None or cells[0][0] >= GROUND_COLS:
            pre.append(f"EQ27: no {PROX_T} cell on the first page of the client's ground ({cells})")
            break
        time.sleep(KEY_SETTLE_S)
        m["click"] = click(client, slot=GROUND, x=cells[0][0], y=cells[0][1], mod="ctrl")
        got, dt = wait_until(lambda: settled(host, client, C2, lambda sig: sum(1 for s in sig if s[0] == PROX_T) == n),
                             LAND_WAIT_S, 0.1)
        m["within"] = dt if got else None
        if not got:
            pre.append(f"EQ27: Ctrl-click {n} did not land a {PROX_T} on C2 on both ({m})")
            break
    ih, ic = items_by_id(host), items_by_id(client)
    tmpl = unit_sig(ih, C2)
    tmpl_cells = prox_cells(ih, C2)
    setup.update({"templateSig": tmpl, "templateCells": tmpl_cells, "c2Client": unit_sig(ic, C2),
                  "pileProxAfterMoves": {"host": prox_on_pile(ih), "client": prox_on_pile(ic)},
                  "c2Ids": sorted(unit_items(ih, C2))})
    if not pre and (len(tmpl) != 2 or len(tmpl_cells) != 2 or setup["c2Client"] != tmpl
                    or len(setup["pileProxAfterMoves"]["host"]) != 1
                    or setup["pileProxAfterMoves"]["host"] != setup["pileProxAfterMoves"]["client"]
                    or not set(setup["c2Ids"]) <= known_prox):
        pre.append(f"EQ27: C2 {tmpl} (client {setup['c2Client']}, ids {setup['c2Ids']} of the staged {sorted(known_prox)}) "
                   f"/ the pile's {PROX_T} {setup['pileProxAfterMoves']} (want C2 = two {PROX_T} on both, ONE left on the "
                   f"pile)")
    # 3. create the template on C2 (UI-local), NEXT to C1 (empty)
    if not pre:
        time.sleep(KEY_SETTLE_S)
        setup["create"] = click(client, widget="create_template")
        time.sleep(KEY_SETTLE_S)
        nav = []
        setup["toC1"] = {"reached": goto_unit(client, C1, C_IDS, nav), "nav": nav}
        if not setup["toC1"]["reached"] or inv_view(client).get("selectedItem") != -1:
            pre.append(f"EQ27: the client's screen never showed C1 with an empty cursor ({setup['toC1']}, cursor "
                       f"{inv_view(client).get('selectedItem')})")
    if pre:
        evidence("EQ27", ev)
        finish([f.replace("EQ27: ", "EQ27: precondition absent - ") for f in pre])

    # 4. the client applies the short template on C1
    b = snapshot(host, client)
    ev["lineBefore"] = {"text": inv_view(client).get("lineText"), "visible": inv_view(client).get("lineVisible")}
    time.sleep(KEY_SETTLE_S)
    t0 = time.time()
    ev["apply"] = click(client, widget="apply_template")
    landed = {}

    def stop(now, seen):
        if "at" not in landed and settled(host, client, C1, lambda sig: sig != []):
            landed["at"] = round(time.time() - t0, 3)
        if "at" in landed:
            return seen is not None or now >= landed["at"] + LINE_READ_S
        return now > LAND_WAIT_S

    seen, last = watch_line(client, TEXT_SHORT, t0, stop)
    landed_at = landed.get("at")
    at_read = None
    if landed_at is not None:
        wait = landed_at + LINE_READ_S - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
        v = inv_view(client)
        at_read = {"text": v.get("lineText"), "visible": v.get("lineVisible"), "t": round(time.time() - t0, 3)}
    ih, ic = items_by_id(host), items_by_id(client)
    new_log = [e for e in host_bulk_log(host) if e.get("iseq") not in b["logIseqs"]]
    c1_cells = prox_cells(ih, C1)
    ev.update({"landedWithin": landed_at, "clientLineSeen": seen, "clientLineLast": last,
               "clientLineAtRead": at_read, "c1": {"host": unit_sig(ih, C1), "client": unit_sig(ic, C1)},
               "c1Cells": c1_cells, "c1Ids": sorted(unit_items(ih, C1)),
               "c1DumpEqual": unit_dump(ih, C1) == unit_dump(ic, C1),
               "pileProx": {"host": prox_on_pile(ih), "client": prox_on_pile(ic)},
               "missing": len(tmpl_cells) - len([c for c in c1_cells if c in tmpl_cells]),
               "invBulkSent": sent_bulk(client) - b["sent"], "hostInvBulkLog": new_log,
               "hostInvBulkDenied": [b["denied"], host_bulk_denied(host)],
               "clientLastWarning": [b["line"], es(client).get("invLastWarning")]})

    # 5. the control: the HOST applies the same short template (vanilla, its own line)
    ctl = {}
    ev["hostControl"] = ctl
    nav = []
    ctl["toH1"] = {"reached": goto_unit(host, H1, H_IDS, nav), "nav": nav}
    if ctl["toH1"]["reached"] and inv_view(host).get("selectedItem") == -1:
        time.sleep(KEY_SETTLE_S)
        ctl["create"] = click(host, widget="create_template")
        time.sleep(KEY_SETTLE_S)
        nav2 = []
        ctl["toH2"] = {"reached": goto_unit(host, H2, H_IDS, nav2), "nav": nav2}
        ctl["h2Before"] = unit_sig(items_by_id(host), H2)
        if ctl["toH2"]["reached"]:
            time.sleep(KEY_SETTLE_S)
            t1 = time.time()
            ctl["apply"] = click(host, widget="apply_template")
            ctl["lineSeen"], ctl["lineLast"] = watch_line(
                host, TEXT_SHORT, t1, lambda now, seen: seen is not None or now > CLICK_WAIT_S + LINE_READ_S)
            got, dt = wait_until(lambda: settled(host, client, H2, lambda sig: True), LAND_WAIT_S, 0.1)
            ctl["settledWithin"] = dt if got else None
    ih, ic = items_by_id(host), items_by_id(client)
    ctl["h2After"] = {"host": unit_sig(ih, H2), "client": unit_sig(ic, H2)}
    ctl["h2Cells"] = prox_cells(ih, H2)
    ctl["h1Cells"] = prox_cells(ih, H1)
    ev["views"] = {"host": view_brief(inv_view(host)), "client": view_brief(inv_view(client))}
    ev["turn"] = [turn(host), turn(client)]
    evidence("EQ27", ev)

    if seen is None:
        fails.append(f"EQ27: the client's line never showed {TEXT_SHORT!r} after its apply (last read {last}, "
                     f"+{LINE_READ_S}s read {at_read}) - RED: the inv_bulk answer carries no 'not enough items' flag "
                     f"(the partial apply itself landed: C1 {ev['c1']['host']}, {ev['missing']} template item(s) "
                     f"missing)")
    if landed_at is None:
        fails.append(f"EQ27: the apply never landed on C1 on both within {LAND_WAIT_S}s (host {ev['c1']['host']}, "
                     f"client {ev['c1']['client']}, inFlight {es(client).get('inFlight')})")
    if not ev["c1DumpEqual"] or ev["c1"]["host"] != ev["c1"]["client"]:
        fails.append(f"EQ27: C1 differs: host {ev['c1']['host']} client {ev['c1']['client']}")
    if len(c1_cells) != 1 or c1_cells[0] not in tmpl_cells or len(ev["c1"]["host"]) != 1 \
            or not set(ev["c1Ids"]) <= known_prox:
        fails.append(f"EQ27: C1 {ev['c1']['host']} (ids {ev['c1Ids']}) is not the partial template: want ONE {PROX_T} "
                     f"in one of the template cells {tmpl_cells}")
    if ev["missing"] != 1:
        fails.append(f"EQ27: {ev['missing']} template item(s) missing (want exactly 1: the pile held one {PROX_T} for "
                     f"two cells)")
    if ev["pileProx"]["host"] or ev["pileProx"]["client"]:
        fails.append(f"EQ27: the pile still holds {PROX_T} {ev['pileProx']} (want none on both)")
    if ev["invBulkSent"] != 1:
        fails.append(f"EQ27: client coopIntentsSent.inv_bulk +{ev['invBulkSent']} (want +1: the apply)")
    if len(new_log) != 1:
        fails.append(f"EQ27: the host received {len(new_log)} inv_bulk ({new_log}; want 1)")
    if ev["hostInvBulkDenied"][1] != ev["hostInvBulkDenied"][0]:
        fails.append(f"EQ27: the host denied inv_bulk {ev['hostInvBulkDenied']} (want none)")
    if ctl.get("lineSeen") is None:
        fails.append(f"EQ27: CONTROL - the host's own apply of the short template never showed {TEXT_SHORT!r} on the "
                     f"host's line ({ctl})")
    if ctl["h2After"]["host"] != ctl["h2After"]["client"] or ctl["h2Cells"] != [(BELT, 0, 0)] \
            or ctl["h1Cells"] != [(BELT, 0, 0), (BELT, 1, 0)]:
        fails.append(f"EQ27: CONTROL - H2 host {ctl['h2After']['host']} client {ctl['h2After']['client']} cells "
                     f"{ctl['h2Cells']}, H1 cells {ctl['h1Cells']} (want H2 = its one {PROX_T} in the template's first "
                     f"cell on both, H1 unchanged)")
    for side, v in ev["views"].items():
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"EQ27: the {side}'s pre-battle screen is not on top ({v})")
    if ev["turn"] != [0, 0]:
        fails.append(f"EQ27: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, "EQ27")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine (a failure there fails the
# run, and the rows after it fail on their own preconditions).
STEPS = ((None, spine_both_briefings),
         (None, spine_stage),
         (None, spine_stage_eq27),
         (None, spine_open_screens),
         (None, spine_save_personal),
         ("EQ16", eq16_template),
         ("EQ17", eq17_personal),
         ("EQ18", eq18_global),
         ("EQ19", eq19_clear),
         ("EQ20", eq20_autoequip),
         ("EQ27", eq27_template_short))
ROWS = [n for n, _ in STEPS if n]


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
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
    print(f"[w2p8b-sc] boot C ok: MAP_FP={MAP_FP!r} mission={hb.get('missionType')} seated={seated_uids} H={h_ids} "
          f"host stack={stack(host)} client stack={stack(client)}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49924, make_user_dir("w2p8b_prebattle_equip_tools_host"))
    client = GameClient("client", 49925, make_user_dir("w2p8b_prebattle_equip_tools_client"))
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
                print(f"[w2p8b-sc] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n in ROWS if results.get(n)]
    failed = [n for n in ROWS if not results.get(n)]
    print(f"\ntest_w2_prebattle_equip_tools: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}"
          f"{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (not failed and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
