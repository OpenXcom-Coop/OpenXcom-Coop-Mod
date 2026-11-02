"""test_prebattle_equip_shared.py: a layout the second player saves on the pre-battle equip screen in a SHARED
campaign. In SHARED the second player's saved layouts - its soldier's personal layout and a global layout - are saved
by the HOST into the one shared world (in a skirmish or SEPARATE they stay local and are lost,
test_prebattle_equip_tools.py). In SHARED, `btnCreatePersonalTemplateClick` and `saveGlobalLayout` send `inv_bulk {op
save_personal | save_global, template, index?}` (a tracked intent, like `inv_move`) with the created template and let
vanilla's local write run; the host performs the layout write.

Without the fix the save is vanilla on the second player's own machine: its copy of the world holds the layout, the
host's does not, nothing is sent.

ONE boot (a SHARED campaign, rows in this order - save_keeps_armor, saves_reach_host, save_while_order_in_flight; each
row ONE run): shared_fixture.bring_up (shared_fixture.py :251: new SHARED campaign, world streamed, both on the
geoscape; HOST_OPTIONS for the host only, save_keeps_armor) -> session.bring_up_shared_mixed_battle(js, OWNERS,
to_tactical=False) (session.py :2464: the roster's first two soldiers stamped owner seat 0 / seat 1 on both machines -
test_shared_battle.py's `mixed` squad, :202 - flown to a fresh terror site and landed; returns with the host's
briefing up) -> the steps of session.briefings_to_battlescape (:2179) up to the equip screens, without its
equip_both_ready: the client's briefing (<= 90 s), the host's briefing OK (click_widget ok), dismiss_client_briefing
-> both pre-battle screens up and the host's equip-open announce. C = the client-owned soldier's unit, H = the
host-owned one (their coop seat asserted on both machines).
Staging (both briefings up, client first; staged items only): C stripped on both machines, then L = a rifle loaded
with a rifle clip in STR_RIGHT_HAND + a grenade on STR_BELT (0,0) (battle_give; test_prebattle_equip_tools's L1).
Keys: as test_prebattle_equip_tools (the harness options.cfg, else Options.cpp's defaults; the live values on both
machines must match); the personal save is the plain keyInvSavePersonalEquipment, the global save vanilla's Ctrl+1
(InventoryState::handle; index 0).
  saves_reach_host: the client's screen on C: (a) keyInvSavePersonalEquipment; (b) Ctrl+1. Pass: (a) the HOST's C
      personal layout (equip_layouts) = L and the client's = the host's, one `inv_bulk` sent (client coopIntentsSent)
      and received (host intentsReceivedLog) for it, none denied; (b) the HOST's global layout 0 = L and the client's
      = the host's, one `inv_bulk` for it, none denied; C's items unchanged on both. Without the fix: each save lands
      in the client's world only (the client's layout = L, the host's unchanged, 0 `inv_bulk` sent).
  save_keeps_armor: (follows vanilla) a SHARED layout save keeps its armor half as vanilla does - the save dialog's
      "with armor" choice and oxcePersonalLayoutIncludingArmor ride the `inv_bulk` save payload. Two vanilla sites
      write the armor half, each right AFTER the co-op note - saveGlobalLayout(index, includingArmor) (only the save
      dialog's SAVE+ passes includingArmor true; Ctrl+digit, SAVE and Enter pass false) and
      btnCreatePersonalTemplateClick (reads oxcePersonalLayoutIncludingArmor); the host donor clears the global armor
      and uses the HOST's own option for the personal one. Fixture: the host boots with
      oxcePersonalLayoutIncludingArmor OFF (shared_fixture host_options), the client keeps the default ON (both read
      live through equip_layouts.personalLayoutIncludingArmor), so the host's own option can not stand in for the
      client's. The client's screen on C:
        (a) keyInventorySave (the probe's live keyInventorySave) opens InventorySaveState -> a bounded wait until
            list_widgets reports its layout list `hidden` false (the dialog's POPUP window hides every surface until
            its popup ends and a hidden surface ignores input; no fixed settle, the click is never repeated) ->
            click_widget on the list by type (its centre row) -> the name field appears (a precondition) ->
            NAME_LETTER typed into it -> the SAVE+ button (saveTemplate(true)). The row saved is the one global index
            whose layout changed on the client, never GLOBAL_INDEX. Pass: the host's global layout at that index = L
            with globalArmor = C's armor type and globalName = the name the client typed (equip_layouts.globalName),
            the client's the same, one `inv_bulk` sent and received, none denied. Without the fix: the host's
            globalArmor is empty (the layout half lands, the armor half is lost) and its name is unchanged.
        (b) C's grenade moved from STR_BELT (0,0) to (1,0) (an inv_move: the saved layout L_b then differs from
            saves_reach_host's L, so saves_reach_host's own save still changes the host's copy) ->
            keyInvSavePersonalEquipment. Pass: the host's C personal layout = L_b with personalArmor = C's armor type,
            the client's the same, one `inv_bulk`, none denied. Without the fix: the host's personalArmor is empty
            (its own option is off). Then the grenade goes back to (0,0) (C = L again for saves_reach_host).
      save_keeps_armor runs BEFORE saves_reach_host: its personal save is the first one, so the host's personalArmor
      changes in THIS row (after a passing saves_reach_host it would already hold the armor and save_keeps_armor (b)
      would pass vacuously).
  save_while_order_in_flight: (follows vanilla) a SHARED layout save pressed while C's own order is in flight is not
      dropped. The one client lock that drops it is sendClientIntent's lock on an in-flight tracked intent for the
      same actor; coopNoteInvLayoutSave does not take coopInvUnitOrderOutstanding or the held-order refusal. The
      in-flight order is held by the existing host test command defer_intents {ms: DEFER_MS, count: 1} (the next
      incoming bt_intent waits DEFER_MS before admission): C's grenade Ctrl-clicked to the ground (ctrl_ground, lands:
      C = L' = the loaded rifle) -> the host arms defer_intents -> C's rifle Ctrl-clicked to the ground (ctrl_ground:
      no cursor item, so vanilla's save is not refused) -> the client's inFlight shows that inv_move ->
      keyInvSavePersonalEquipment -> the host's intentsReceivedLog does not hold the order yet (the press happened
      while it was in flight; no wall-clock race: both reads are asserted). Pass: the host's C personal layout = the
      saved L' (the client's = the host's), one `inv_bulk` received for the save, none denied, and the held order also
      completes (the rifle and its clip on the pile on both, C empty). Without the fix: the save is dropped (the
      host's personal layout stays L; client invGuard "unsent").

Common asserts: hash_now {full:true} every bucket EQUAL after the queues drain; desyncSeen false on both; the client's
turnMirrorFired 0; coopClientBStatePushes 0 on both; the client's invLocalWrites 0; both pre-battle screens still up
and turn 0 on both; the client's pre-battle ground ids = its own pile ids (the pile is the client's equip.pile, the
offer's) and the pile ids equal on both machines.

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked, then "PASS <id>" / "FAIL <id>: <message>"
(the check of the fix first). Every wait is bounded. One run is the result; no skip path, no second boot. Exit 0 only
when every row passes, 2 otherwise (a bring-up or spine failure is also 2). Run in the foreground to completion.

Run:  python tools/coop_test/test_prebattle_equip_shared.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
from session import battle_state
from test_delta_core import both, short, diff_buckets, desync_record
from test_delta_items import items_by_id
from test_client_items import strip_both
from test_prebattle_equip import (ENTRY_WAIT_S, ANSWER_WAIT_S, LAND_WAIT_S, DRAIN_WAIT_S, stack, has, es, equip,
                                     turn, in_battle, inv_view, view_brief, ground_ids, wait_until, evidence, finish,
                                     goto_unit, drained, pre_screen_fails, click, screen_up, CLICK_WAIT_S, DEFER_MS,
                                     BELT, RIGHT_HAND, RIFLE_T, GRENADE_T)
from test_prebattle_equip_tools import (L1_GIVE, SDLK_1, GLOBAL_INDEX, KEY_SETTLE_S, layouts, sent_bulk,
                                           host_bulk_log, host_bulk_denied, unit_sig, unit_items, layout_sig, unit_dump,
                                           key, clear_mod, harness_keys)

TAG = "prebattle_equip_shared"     # the two user dirs: s<slot>_prebattle_equip_shared_host / _client
PORTS = (49926, 49927, 48834)      # (host test label, client test label, the SHARED session port); unused elsewhere
OWNERS = {0: 0, 1: 1}              # test_shared_battle.py :202 `mixed`: squad[0] -> seat 0 (host), squad[1] -> seat 1
CLIENT_BRIEFING_WAIT_S = 90.0      # session.briefings_to_battlescape's bound: the client's briefing <= 90 s
HOST_SCREEN_WAIT_S = 10.0
# save_keeps_armor: the HOST boots with vanilla's personal-save armor option OFF, the client keeps Options.cpp's
# default ON (both read live through equip_layouts.personalLayoutIncludingArmor)
HOST_OPTIONS = {"oxcePersonalLayoutIncludingArmor": False}
SDLK_F5 = 286                      # Options.cpp keyInventorySave default (SDL 1.2); the client's live value must match
N_GLOBAL = 20                      # Options.cpp oxceMaxEquipmentLayoutTemplates default: the save dialog's rows
SAVE_WAIT_S = 3.0                  # the save dialog opens / its popup ends (list_widgets `hidden`) / it closes
NAME_LETTER = ("x", 120)           # typed into the dialog's name field (the inject_input key = the SDL sym)
HELD_LAND_WAIT_S = DEFER_MS / 1000.0 + LAND_WAIT_S   # save_while_order_in_flight: the held order is admitted DEFER_MS
                                                     # after the host took it


def pile_of(client):
    p = equip(client).get("pile")
    return tuple(p) if isinstance(p, list) and len(p) == 3 else None


def pile_ids_at(its, pile):
    return sorted(i for i, it in its.items() if it.get("onTile") and (it.get("tx"), it.get("ty"), it.get("tz")) == pile)


def tail_fails(host, client, ctx, what):
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
    pile = ctx.get("pile")
    ih, ic = items_by_id(host), items_by_id(client)
    cv = inv_view(client)
    if cv.get("open") and cv.get("preBattle") and ground_ids(cv) != pile_ids_at(ic, pile):
        fails.append(f"{what}: the client's pre-battle ground {ground_ids(cv)} is not its own pile "
                     f"{pile} {pile_ids_at(ic, pile)}")
    if pile_ids_at(ih, pile) != pile_ids_at(ic, pile):
        fails.append(f"{what}: the pile ids differ: host {pile_ids_at(ih, pile)} client {pile_ids_at(ic, pile)}")
    return fails


# ===================== the spine =====================


def spine_units(host, client, ctx):
    """C / H: the squad's units (soldierId -> unit id, coop seat) on both machines."""
    squad = ctx["squad"]
    rec = {}
    for tag, gc in (("host", host), ("client", client)):
        us = {u.get("soldierId"): u for u in battle_state(gc).get("units", []) if u.get("soldierId") in squad}
        rec[tag] = {sid: [u.get("id"), u.get("coop")] for sid, u in us.items()}
    print(f"SPINE squad units: squad={squad} {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    want = {squad[0]: 0, squad[1]: 1}
    for tag in ("host", "client"):
        got = {sid: v[1] for sid, v in rec[tag].items()}
        if got != want:
            raise AssertionError(f"spine: the {tag}'s squad seats {got} (want {want}: OWNERS {OWNERS})")
    if rec["host"] != rec["client"]:
        raise AssertionError(f"spine: squad units differ host {rec['host']} client {rec['client']}")
    ctx["C"] = rec["host"][squad[1]][0]
    ctx["H"] = rec["host"][squad[0]][0]


def spine_both_briefings(host, client, ctx):
    """The steps of session.briefings_to_battlescape, first half: the client's briefing while the host's is up."""
    got, dt = wait_until(lambda: has(client, "BriefingState") and in_battle(client), CLIENT_BRIEFING_WAIT_S, 0.2)
    rec = {"clientBriefingWithin": dt if got else None, "hostStack": stack(host), "clientStack": stack(client),
           "turn": [turn(host), turn(client)]}
    print(f"SPINE both briefings: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not got or not has(host, "BriefingState"):
        raise AssertionError(f"spine: both briefings are not up ({rec})")


def spine_stage(host, client, ctx):
    """Staging (client first; staged items only): C stripped, then L; the keys; the layout baselines."""
    c = ctx["C"]
    rec = {"C": c, "ids": {}}
    ctx["staged"] = rec
    try:
        session.wait_seq_barrier(host, client)  # the host's first evs applied before staging
        rec["stripped"] = strip_both(host, client, c)
        for t, extra in L1_GIVE:
            req = {"cmd": "battle_give", "unit": c, "item": t}
            req.update(extra)
            r = both(host, client, req, ("weaponId", "ammoId", "weaponSlot"))
            rec["ids"][t] = [r["weaponId"], r["ammoId"], r["weaponSlot"]]
        rec["diff"] = diff_buckets(host, client)
        ih, ic = items_by_id(host), items_by_id(client)
        rec["sigL"] = unit_sig(ih, c)
        rec["sigClient"] = unit_sig(ic, c)
        rec["keys"] = harness_keys(client)
        rec["liveKeys"] = {"host": layouts(host).get("keys"), "client": layouts(client).get("keys")}
        rec["baseline"] = {"host": layouts(host, c), "client": layouts(client, c)}
        rec["turn"] = [turn(host), turn(client)]
    except Exception as e:
        rec["error"] = short(e, 400)
    print(f"STAGE {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if rec.get("error"):
        raise AssertionError(f"spine: the staging failed: {rec['error']}")
    if rec["diff"] or not rec["sigL"] or rec["sigClient"] != rec["sigL"]:
        raise AssertionError(f"spine: after the staging buckets differ {rec['diff']} / C host {rec['sigL']} client "
                             f"{rec['sigClient']} (want equal and non-empty)")
    want_keys = {n: v[0] for n, v in rec["keys"].items()}
    for side in ("host", "client"):
        if rec["liveKeys"][side] != want_keys:
            raise AssertionError(f"spine: FIXTURE - the {side}'s live inventory keys {rec['liveKeys'][side]} != the "
                                 f"harness options.cfg keys {want_keys}")
    for side in ("host", "client"):
        b = rec["baseline"][side]
        if b.get("soldier") is not True:
            raise AssertionError(f"spine: FIXTURE - the {side} has no geoscape soldier for C {c} ({b})")
    ctx["keys"] = want_keys


def spine_open_screens(host, client, ctx):
    """The steps of session.briefings_to_battlescape, second half without equip_both_ready: the host's briefing OK
    (click_widget ok), then dismiss_client_briefing - both pre-battle equip screens up, the host's equip-open
    announce."""
    rec = {}
    h = host.cmd({"cmd": "click_widget", "match": "ok"})
    session.dismiss_client_briefing(client)
    g1, d1 = wait_until(lambda: inv_view(client).get("preBattle") is True and inv_view(client).get("top") is True,
                        ENTRY_WAIT_S)
    g2, d2 = wait_until(lambda: inv_view(host).get("preBattle") is True and inv_view(host).get("top") is True,
                        HOST_SCREEN_WAIT_S)
    g3, d3 = wait_until(lambda: equip(host).get("openAnnounced") is True, ANSWER_WAIT_S)
    ctx["pile"] = pile_of(client)
    rec.update({"hostOk": {k: h.get(k) for k in ("ok", "error")}, "clientScreenWithin": d1 if g1 else None,
                "hostScreenWithin": d2 if g2 else None, "announcedWithin": d3 if g3 else None,
                "pile": ctx["pile"], "hostPile": equip(host).get("pile"), "clientView": view_brief(inv_view(client)),
                "hostView": view_brief(inv_view(host)), "hostStack": stack(host), "clientStack": stack(client),
                "turn": [turn(host), turn(client)]})
    print(f"SPINE screens: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not (g1 and g2 and g3) or ctx["pile"] is None:
        raise AssertionError(f"spine: the pre-battle screens are not both up and announced ({rec})")


# ===================== saves_reach_host =====================


def save_leg(host, client, ctx, ev, name, press, read, sig_l):
    """One save: `press()`, then wait (bounded) for the host's layout (`read(gc)`) = L and the client's = the
    host's. Returns the fails, the check of the fix first."""
    b = {"host": layout_sig(read(host)), "client": layout_sig(read(client)), "sent": sent_bulk(client),
         "log": [e.get("iseq") for e in host_bulk_log(host)], "denied": host_bulk_denied(host)}
    rec = {"before": {k: b[k] for k in ("host", "client")}}
    rec["press"] = press(rec)

    def landed():
        h, c = layout_sig(read(host)), layout_sig(read(client))
        return h == sig_l and c == h and es(client).get("inFlight") is None

    got, dt = wait_until(landed, LAND_WAIT_S, 0.1)
    h, c = layout_sig(read(host)), layout_sig(read(client))
    new_log = [e for e in host_bulk_log(host) if e.get("iseq") not in b["log"]]
    sent = sent_bulk(client) - b["sent"]
    rec.update({"landedWithin": dt if got else None, "after": {"host": h, "client": c}, "invBulkSent": sent,
                "hostInvBulkLog": new_log, "hostInvBulkDenied": [b["denied"], host_bulk_denied(host)],
                "inFlight": es(client).get("inFlight"), "clientLine": inv_view(client).get("lineText")})
    ev[name] = rec
    fails = []
    if h != sig_l:
        unfixed = (" - without the fix: the save landed in the client's world only"
                   if h == b["host"] and c == sig_l else "")
        fails.append(f"saves_reach_host {name}: the host's layout {b['host']} -> {h} (want L {sig_l}: the host saves "
                     f"it into the shared world){unfixed} (the client's {b['client']} -> {c}, inv_bulk sent {sent})")
    if c != sig_l:
        fails.append(f"saves_reach_host {name}: FIXTURE - the client's layout {b['client']} -> {c} (want L {sig_l}: "
                     f"vanilla's local write runs on the client too)")
    if sent != 1:
        fails.append(f"saves_reach_host {name}: client coopIntentsSent.inv_bulk +{sent} (want +1: one inv_bulk save "
                     f"order)")
    if len(new_log) != 1:
        fails.append(f"saves_reach_host {name}: the host received {len(new_log)} inv_bulk ({new_log}; want 1)")
    if rec["hostInvBulkDenied"][1] != rec["hostInvBulkDenied"][0]:
        fails.append(f"saves_reach_host {name}: the host denied inv_bulk {rec['hostInvBulkDenied']} (want none)")
    if rec["inFlight"] is not None:
        fails.append(f"saves_reach_host {name}: the client still has an order in flight {rec['inFlight']}")
    return fails


def row_saves_reach_host(host, client, ctx):
    c = ctx.get("C")
    fails = pre_screen_fails(host, client, "saves_reach_host", host_too=True)
    s = ctx.get("staged") or {}
    if not s.get("sigL") or s.get("error") or not ctx.get("keys") or not ctx.get("pile"):
        fails.append(f"saves_reach_host: the spine did not complete (staged {s.get('error')}, pile {ctx.get('pile')})")
    nav = []
    if not fails:
        if not goto_unit(client, c, [c], nav):
            fails.append(f"saves_reach_host: the client's screen never showed C {c} ({nav})")
        elif inv_view(client).get("selectedItem") != -1:
            fails.append(f"saves_reach_host: the client's cursor holds {inv_view(client).get('selectedItem')} (want "
                         f"empty)")
    if fails:
        evidence("saves_reach_host", {"nav": nav, "C": c})
        finish([f.replace("saves_reach_host: ", "saves_reach_host: precondition absent - ") for f in fails])
    sig_l = s["sigL"]
    ih0, ic0 = items_by_id(host), items_by_id(client)
    ev = {"C": c, "H": ctx.get("H"), "L": sig_l, "baseline": s["baseline"]}

    def press_personal(rec):
        time.sleep(KEY_SETTLE_S)
        return key(client, ctx["keys"]["keyInvSavePersonalEquipment"])

    def press_global(rec):
        time.sleep(KEY_SETTLE_S)
        k = key(client, SDLK_1, mod="ctrl")
        got, dt = wait_until(lambda: layouts(client).get("global"), ANSWER_WAIT_S)
        rec["clientSavedWithin"] = dt if got else None
        rec["clearMod"] = clear_mod(client)
        return k

    fails = save_leg(host, client, ctx, ev, "personal", press_personal, lambda gc: layouts(gc, c).get("personal"),
                     sig_l)
    fails += save_leg(host, client, ctx, ev, "global", press_global, lambda gc: layouts(gc).get("global"), sig_l)
    ih, ic = items_by_id(host), items_by_id(client)
    ev.update({"cItems": {"hostPre": unit_sig(ih0, c), "hostPost": unit_sig(ih, c), "clientPre": unit_sig(ic0, c),
                          "clientPost": unit_sig(ic, c)},
               "cDumpEqual": unit_dump(ih, c) == unit_dump(ic, c),
               "views": {"host": view_brief(inv_view(host)), "client": view_brief(inv_view(client))},
               "turn": [turn(host), turn(client)]})
    evidence("saves_reach_host", ev)
    ci = ev["cItems"]
    if not (ci["hostPost"] == ci["hostPre"] == ci["clientPost"] == ci["clientPre"] == sig_l) or not ev["cDumpEqual"]:
        fails.append(f"saves_reach_host: C's items changed or differ ({ci}, dumps equal {ev['cDumpEqual']}; want L "
                     f"unchanged on both: a save moves no item)")
    for side, v in ev["views"].items():
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"saves_reach_host: the {side}'s pre-battle screen is not on top ({v})")
    if ev["turn"] != [0, 0]:
        fails.append(f"saves_reach_host: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, ctx, "saves_reach_host")
    finish(fails)


# ===================== save_keeps_armor / save_while_order_in_flight =====================


def save_opts(gc):
    r = gc.cmd({"cmd": "equip_layouts"})
    return {"armorOpt": r.get("personalLayoutIncludingArmor"), "saveKey": r.get("keyInventorySave"),
            "error": r.get("error")}


def armor_of(gc, uid):
    for u in battle_state(gc).get("units", []):
        if u.get("id") == uid:
            return u.get("armor")
    return None


def global_at(gc, i):
    r = gc.cmd({"cmd": "equip_layouts", "index": i})
    return [layout_sig(r.get("global")), r.get("globalArmor"), r.get("globalName")]


def globals_of(gc):
    """{index: [layout signature, globalArmor, globalName]} for the save dialog's N_GLOBAL rows."""
    return {i: global_at(gc, i) for i in range(N_GLOBAL)}


def dialog_widgets(gc):
    w = gc.cmd({"cmd": "list_widgets"})
    return [{k: x.get(k) for k in ("idx", "type", "interactive", "visible", "hidden", "x", "y", "w", "h", "text")}
            for x in (w.get("widgets") or [])]


def of_type(ws, t):
    return [x for x in ws if t in str(x.get("type"))]


def personal_of(gc, c):
    r = layouts(gc, c)
    return [layout_sig(r.get("personal")), r.get("personalArmor")]


def settled_c(host, client, ctx, c, want):
    """`want(host sig of C)` holds, C's items and the pile ids equal on both, nothing in flight."""
    ih, ic = items_by_id(host), items_by_id(client)
    pile = ctx.get("pile")
    return (want(unit_sig(ih, c)) and unit_dump(ih, c) == unit_dump(ic, c)
            and pile_ids_at(ih, pile) == pile_ids_at(ic, pile) and es(client).get("inFlight") is None)


def item_of(its, uid, t, slot):
    for i, it in unit_items(its, uid).items():
        if it.get("type") == t and it.get("slot") == slot:
            return i
    return None


def move_in_c(host, client, ctx, c, frm, to, rec):
    """Pick C's item at STR_BELT `frm` onto the client's cursor (vanilla, local) and place it at `to` (one inv_move);
    True when it landed on both."""
    rec["pick"] = click(client, slot=BELT, x=frm[0], y=frm[1])
    got, _ = wait_until(lambda: inv_view(client).get("selectedItem") not in (None, -1), CLICK_WAIT_S)
    rec["picked"] = inv_view(client).get("selectedItem")
    if not got:
        return False
    time.sleep(KEY_SETTLE_S)
    rec["place"] = click(client, slot=BELT, x=to[0], y=to[1])
    got, dt = wait_until(lambda: settled_c(host, client, ctx, c, lambda sig: any(
        s[0] == GRENADE_T and s[1] == BELT and (s[2], s[3]) == tuple(to) for s in sig)) and
        inv_view(client).get("selectedItem") == -1, LAND_WAIT_S, 0.1)
    rec["within"] = dt if got else None
    return bool(got)


def layout_row_pre(host, client, ctx, row):
    """The head of the armor and in-flight rows: both pre-battle screens, the spine done, the client's screen on C,
    an empty cursor, nothing in flight."""
    c = ctx.get("C")
    fails = pre_screen_fails(host, client, row, host_too=True)
    s = ctx.get("staged") or {}
    if not s.get("sigL") or s.get("error") or not ctx.get("keys") or not ctx.get("pile"):
        fails.append(f"{row}: the spine did not complete (staged {s.get('error')}, pile {ctx.get('pile')})")
    nav = []
    if not fails:
        if not goto_unit(client, c, [c], nav):
            fails.append(f"{row}: the client's screen never showed C {c} ({nav})")
        elif inv_view(client).get("selectedItem") != -1:
            fails.append(f"{row}: the client's cursor holds {inv_view(client).get('selectedItem')} (want empty)")
        elif es(client).get("inFlight") is not None:
            fails.append(f"{row}: the client has an order in flight {es(client).get('inFlight')} (want none)")
    return fails, nav


def row_save_keeps_armor(host, client, ctx):
    c = ctx.get("C")
    fails, nav = layout_row_pre(host, client, ctx, "save_keeps_armor")
    ev = {"C": c, "nav": nav, "opts": {"host": save_opts(host), "client": save_opts(client)},
          "armor": {"host": armor_of(host, c), "client": armor_of(client, c)}}
    armor = ev["armor"]["host"]
    if not fails:
        o = ev["opts"]
        if o["host"]["armorOpt"] is not False or o["client"]["armorOpt"] is not True:
            fails.append(f"save_keeps_armor: FIXTURE - personalLayoutIncludingArmor host {o['host']['armorOpt']} "
                         f"client "
                         f"{o['client']['armorOpt']} (want host False from HOST_OPTIONS, client True: Options.cpp's "
                         f"default)")
        if o["client"]["saveKey"] != SDLK_F5:
            fails.append(f"save_keeps_armor: FIXTURE - the client's live keyInventorySave {o['client']['saveKey']} "
                         f"(want {SDLK_F5})")
        if not armor or ev["armor"]["client"] != armor:
            fails.append(f"save_keeps_armor: FIXTURE - C's armor host {armor!r} client {ev['armor']['client']!r} (want "
                         f"equal, non-empty)")
    if fails:
        evidence("save_keeps_armor", ev)
        finish([f.replace("save_keeps_armor: ", "save_keeps_armor: precondition absent - ") for f in fails])
    sig_l = ctx["staged"]["sigL"]

    # (a) the save dialog's SAVE+ (saveTemplate(true) -> saveGlobalLayout(row, true))
    a = {}
    ev["dialog"] = a
    g0 = {"host": globals_of(host), "client": globals_of(client)}
    b = {"sent": sent_bulk(client), "log": [e.get("iseq") for e in host_bulk_log(host)],
         "denied": host_bulk_denied(host)}
    time.sleep(KEY_SETTLE_S)
    a["f5"] = key(client, ev["opts"]["client"]["saveKey"])
    got, dt = wait_until(lambda: "InventorySaveState" in (stack(client) or [""])[-1], SAVE_WAIT_S)
    a["dialogWithin"] = dt if got else None
    a["widgetsAtOpen"] = dialog_widgets(client) if got else None
    # the dialog's POPUP window hides every surface until its popup ends and a hidden surface ignores input - wait
    # (bounded, the condition itself) until the layout list is no longer hidden; the click is never repeated
    shown = {}

    def list_shown():
        ws = dialog_widgets(client)
        lst = of_type(ws, "TextList")
        shown["widgets"] = ws
        return len(lst) == 1 and lst[0].get("hidden") is False

    g, d = wait_until(list_shown, SAVE_WAIT_S) if got else (None, None)
    a["listShownWithin"] = d if g else None
    ws = shown.get("widgets") or []
    a["widgets"] = ws
    plus = [x.get("text") for x in of_type(ws, "TextButton") if str(x.get("text")).endswith("+")]
    a["saveWithArmorText"] = plus
    # click_widget's `nth` counts the top state's VISIBLE InteractiveSurfaces in add() order (list_widgets' `visible`
    # and `interactive`); a Text is one too (the dialog title), so the layout list is found by its type
    live = [x for x in ws if x.get("visible") and x.get("interactive")]
    nth_list = [n for n, x in enumerate(live) if "TextList" in str(x.get("type"))]
    a["listNth"] = nth_list
    if g and len(plus) == 1 and len(nth_list) == 1:
        r = client.cmd({"cmd": "click_widget", "nth": nth_list[0]})   # the list's centre row (lstLayoutPress)
        a["row"] = {k: r.get(k) for k in ("ok", "error", "baseX", "baseY")}
        # the precondition: vanilla's name field appears on the pressed row (focused, caret at the end)
        edit = {}

        def name_field():
            e = of_type(dialog_widgets(client), "TextEdit")
            edit["w"] = e
            return len(e) == 1 and e[0].get("visible") is True and e[0].get("hidden") is False

        ge, de = wait_until(name_field, CLICK_WAIT_S)
        a["nameFieldWithin"] = de if ge else None
        a["editAfterRow"] = edit.get("w")
        if ge:
            a["typed"] = key(client, NAME_LETTER[1])   # the name the client types ends with this letter
            r = client.cmd({"cmd": "click_widget", "match": plus[0]})
            a["saveWithArmor"] = {k: r.get(k) for k in ("ok", "error", "text", "baseX", "baseY")}
            g2, d2 = wait_until(lambda: screen_up(client), SAVE_WAIT_S)
            a["closedWithin"] = d2 if g2 else None
    if "InventorySaveState" in (stack(client) or [""])[-1]:
        r = client.cmd({"cmd": "click_widget", "match": "CANCEL"})   # never leave the dialog over the later rows
        a["cancelled"] = {k: r.get(k) for k in ("ok", "error")}
        wait_until(lambda: screen_up(client), SAVE_WAIT_S)
    g1c = globals_of(client)
    changed = [i for i in range(N_GLOBAL) if g1c[i] != g0["client"][i]]
    a["changedOnClient"] = {i: {"before": g0["client"][i], "after": g1c[i]} for i in changed}
    idx = changed[0] if len(changed) == 1 else None
    a["index"] = idx
    typed_name = g1c[idx][2] if idx is not None else None   # vanilla wrote the name field's text on the client
    a["typedName"] = typed_name
    want_g = [sig_l, armor, typed_name]

    def dialog_landed():
        return (idx is not None and global_at(host, idx) == want_g and global_at(client, idx) == want_g
                and es(client).get("inFlight") is None)

    got, dt = wait_until(dialog_landed, LAND_WAIT_S, 0.2)
    new_log = [e for e in host_bulk_log(host) if e.get("iseq") not in b["log"]]
    a.update({"landedWithin": dt if got else None,
              "host": {"before": g0["host"].get(idx), "after": global_at(host, idx)} if idx is not None else None,
              "client": {"before": g0["client"].get(idx), "after": global_at(client, idx)} if idx is not None else None,
              "invBulkSent": sent_bulk(client) - b["sent"], "hostInvBulkLog": new_log,
              "hostInvBulkDenied": [b["denied"], host_bulk_denied(host)]})

    # (b) C = L_b (the grenade (0,0) -> (1,0)), then the personal save with the client's option ON
    p = {}
    ev["personal"] = p
    p["toLb"] = {}
    moved = move_in_c(host, client, ctx, c, (0, 0), (1, 0), p["toLb"])
    sig_lb = unit_sig(items_by_id(host), c)
    p["sigLb"] = sig_lb
    p0 = {"host": personal_of(host, c), "client": personal_of(client, c)}
    b = {"sent": sent_bulk(client), "log": [e.get("iseq") for e in host_bulk_log(host)],
         "denied": host_bulk_denied(host)}
    if moved:
        time.sleep(KEY_SETTLE_S)
        p["press"] = key(client, ctx["keys"]["keyInvSavePersonalEquipment"])
        g, d = wait_until(lambda: personal_of(client, c) == [sig_lb, armor], ANSWER_WAIT_S)
        p["clientSavedWithin"] = d if g else None
        g, d = wait_until(lambda: personal_of(host, c) == [sig_lb, armor] and personal_of(client, c) == [sig_lb, armor]
                          and es(client).get("inFlight") is None, LAND_WAIT_S, 0.2)
        p["landedWithin"] = d if g else None
    new_log = [e for e in host_bulk_log(host) if e.get("iseq") not in b["log"]]
    p.update({"host": {"before": p0["host"], "after": personal_of(host, c)},
              "client": {"before": p0["client"], "after": personal_of(client, c)},
              "invBulkSent": sent_bulk(client) - b["sent"], "hostInvBulkLog": new_log,
              "hostInvBulkDenied": [b["denied"], host_bulk_denied(host)]})
    p["back"] = {}
    restored = moved and move_in_c(host, client, ctx, c, (1, 0), (0, 0), p["back"])
    p["cAfter"] = {"host": unit_sig(items_by_id(host), c), "client": unit_sig(items_by_id(client), c)}
    ev["views"] = {"host": view_brief(inv_view(host)), "client": view_brief(inv_view(client))}
    ev["turn"] = [turn(host), turn(client)]
    evidence("save_keeps_armor", ev)

    fails = []
    # (a) the check of the fix first
    if a.get("listShownWithin") is None or a.get("nameFieldWithin") is None:
        fails.append(f"save_keeps_armor dialog: FIXTURE - the dialog's list never stopped being hidden or the name "
                     f"field never "
                     f"appeared (dialog {a.get('dialogWithin')}, list shown {a.get('listShownWithin')}, row {a.get('row')}, "
                     f"name field {a.get('nameFieldWithin')} {a.get('editAfterRow')})")
    if idx is None:
        fails.append(f"save_keeps_armor dialog: FIXTURE - {len(changed)} client global layout(s) changed "
                     f"({a['changedOnClient']}; "
                     f"dialog {a.get('dialogWithin')}, SAVE+ {a['saveWithArmorText']}, closed {a.get('closedWithin')}); "
                     f"want exactly one")
    else:
        h_after, c_after = a["host"]["after"], a["client"]["after"]
        client_ok = c_after == want_g and str(typed_name).endswith(NAME_LETTER[0]) \
            and typed_name != a["client"]["before"][2]
        if h_after[1] != armor:
            unfixed = (" - without the fix: the host's copy lacks the armor half (its layout " +
                   ("landed" if h_after[0] == sig_l else f"is {h_after[0]}") + ")") if client_ok else ""
            fails.append(f"save_keeps_armor dialog: the host's global layout {idx} armor {h_after[1]!r} (want "
                         f"{armor!r}: SAVE+ keeps the armor){unfixed} (host {a['host']}, client {a['client']})")
        if h_after[2] != typed_name:
            unfixed = (" - without the fix: the host's shared world keeps its old name (the save carries no name)"
                   if client_ok else "")
            fails.append(f"save_keeps_armor dialog: the host's global layout {idx} name {a['host']['before'][2]!r} -> "
                         f"{h_after[2]!r} (want the name the client typed {typed_name!r}){unfixed}")
        if h_after[0] != sig_l:
            fails.append(f"save_keeps_armor dialog: the host's global layout {idx} {h_after[0]} (want L {sig_l})")
        if not client_ok:
            fails.append(f"save_keeps_armor dialog: FIXTURE - the client's global layout {idx} {a['client']} (want [L, "
                         f"{armor!r}, "
                         f"a new name ending with the typed {NAME_LETTER[0]!r}]: vanilla's SAVE+ runs on the client)")
        if idx == GLOBAL_INDEX:
            fails.append(f"save_keeps_armor dialog: FIXTURE - the dialog saved index {idx} = saves_reach_host's Ctrl+1 "
                         f"index")
    if a["invBulkSent"] != 1 or len(a["hostInvBulkLog"]) != 1:
        fails.append(f"save_keeps_armor dialog: inv_bulk sent +{a['invBulkSent']} received {len(a['hostInvBulkLog'])} "
                     f"(want 1 and 1)")
    if a["hostInvBulkDenied"][1] != a["hostInvBulkDenied"][0]:
        fails.append(f"save_keeps_armor dialog: the host denied inv_bulk {a['hostInvBulkDenied']} (want none)")
    # (b)
    if not moved or sig_lb == sig_l:
        fails.append(f"save_keeps_armor personal: FIXTURE - C's grenade never moved to STR_BELT (1,0) on both "
                     f"({p['toLb']}, C {sig_lb})")
    else:
        h_after, c_after = p["host"]["after"], p["client"]["after"]
        if h_after[1] != armor:
            unfixed = " - without the fix: the host's copy lacks the armor half (the host used its own option, off)" \
                if c_after == [sig_lb, armor] else ""
            fails.append(f"save_keeps_armor personal: the host's C personal armor {p['host']['before'][1]!r} -> "
                         f"{h_after[1]!r} "
                         f"(want {armor!r}: the client's oxcePersonalLayoutIncludingArmor is on){unfixed}")
        if h_after[0] != sig_lb:
            fails.append(f"save_keeps_armor personal: the host's C personal layout {p['host']['before'][0]} -> "
                         f"{h_after[0]} (want L_b {sig_lb})")
        if c_after != [sig_lb, armor]:
            fails.append(f"save_keeps_armor personal: FIXTURE - the client's C personal {c_after} (want [L_b, "
                         f"{armor!r}]: vanilla's save with the option on)")
        if p["invBulkSent"] != 1 or len(p["hostInvBulkLog"]) != 1:
            fails.append(f"save_keeps_armor personal: inv_bulk sent +{p['invBulkSent']} received "
                         f"{len(p['hostInvBulkLog'])} (want 1 and 1)")
        if p["hostInvBulkDenied"][1] != p["hostInvBulkDenied"][0]:
            fails.append(f"save_keeps_armor personal: the host denied inv_bulk {p['hostInvBulkDenied']} (want none)")
    if not restored or p["cAfter"]["host"] != sig_l or p["cAfter"]["client"] != sig_l:
        fails.append(f"save_keeps_armor: FIXTURE - C not back to L after the row ({p['back']}, C {p['cAfter']}; want "
                     f"{sig_l})")
    for side, v in ev["views"].items():
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"save_keeps_armor: the {side}'s pre-battle screen is not on top ({v})")
    if ev["turn"] != [0, 0]:
        fails.append(f"save_keeps_armor: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, ctx, "save_keeps_armor")
    finish(fails)


def row_save_while_order_in_flight(host, client, ctx):
    c = ctx.get("C")
    fails, nav = layout_row_pre(host, client, ctx, "save_while_order_in_flight")
    ev = {"C": c, "nav": nav}
    if fails:
        evidence("save_while_order_in_flight", ev)
        finish([f.replace("save_while_order_in_flight: ", "save_while_order_in_flight: precondition absent "
                                                          "- ") for f in fails])
    ih0 = items_by_id(host)
    grenade, rifle = item_of(ih0, c, GRENADE_T, BELT), item_of(ih0, c, RIFLE_T, RIGHT_HAND)
    ev.update({"grenade": grenade, "rifle": rifle, "rifleAmmo": [a for a in (ih0.get(rifle) or {}).get("ammo") or []
                                                                  if a != rifle]})
    pre = []
    if grenade is None or rifle is None:
        pre.append(f"save_while_order_in_flight: C holds no grenade on STR_BELT or rifle in STR_RIGHT_HAND "
                   f"({unit_sig(ih0, c)})")
    # 1. C's grenade Ctrl-clicked to the ground (ctrl_ground): C = L' (the loaded rifle) on both
    if not pre:
        gx, gy = ih0[grenade].get("slotX"), ih0[grenade].get("slotY")
        time.sleep(KEY_SETTLE_S)
        ev["grenadeOut"] = click(client, slot=BELT, x=gx, y=gy, mod="ctrl")
        got, dt = wait_until(lambda: settled_c(host, client, ctx, c, lambda sig: all(s[0] != GRENADE_T for s in sig)),
                             LAND_WAIT_S, 0.1)
        ev["grenadeOutWithin"] = dt if got else None
        if not got:
            pre.append(f"save_while_order_in_flight: C's grenade {grenade} never reached the ground on both "
                       f"({ev['grenadeOut']})")
    sig_lp = unit_sig(items_by_id(host), c)
    ev["sigLp"] = sig_lp
    before = {"host": personal_of(host, c), "client": personal_of(client, c)}
    ev["personalBefore"] = before
    if not pre and before["host"][0] == sig_lp:
        pre.append(f"save_while_order_in_flight: the host's C personal layout is already L' {sig_lp} (want it to "
                   f"differ: saves_reach_host saved L)")
    if pre:
        evidence("save_while_order_in_flight", ev)
        finish([f.replace("save_while_order_in_flight: ", "save_while_order_in_flight: precondition absent "
                                                          "- ") for f in pre])

    # 2. the host holds the next bt_intent; C's rifle Ctrl-clicked to the ground (the held order, no cursor item)
    b = {"sent": sent_bulk(client), "log": [e.get("iseq") for e in host_bulk_log(host)],
         "denied": host_bulk_denied(host), "guard": es(client).get("invGuard")}
    r = host.cmd({"cmd": "defer_intents", "ms": DEFER_MS, "count": 1})
    ev["defer"] = {k: r.get(k) for k in ("ok", "error", "ms", "count")}
    time.sleep(KEY_SETTLE_S)
    ev["rifleOut"] = click(client, slot=RIGHT_HAND, mod="ctrl")
    got, dt = wait_until(lambda: (es(client).get("inFlight") or {}).get("actorId") == c, ANSWER_WAIT_S)
    order = es(client).get("inFlight")
    ev.update({"orderInFlightWithin": dt if got else None, "order": order})
    # 3. the personal save while that order is in flight
    save = {}
    ev["save"] = save
    if got and (order or {}).get("kind") == "inv_move":
        time.sleep(KEY_SETTLE_S)
        save["cursor"] = inv_view(client).get("selectedItem")
        save["press"] = key(client, ctx["keys"]["keyInvSavePersonalEquipment"])
        g, d = wait_until(lambda: personal_of(client, c)[0] == sig_lp, ANSWER_WAIT_S)
        save["clientSavedWithin"] = d if g else None
        save["hostLogAfterPress"] = [e.get("iseq") for e in (es(host).get("intentsReceivedLog") or [])]
        save["orderHeldAtPress"] = order.get("iseq") not in save["hostLogAfterPress"]
        save["inFlightAfterPress"] = es(client).get("inFlight")
    # 4. bounded: the save lands on the host and the held order completes
    pile = ctx.get("pile")

    def done():
        ih, ic = items_by_id(host), items_by_id(client)
        return (personal_of(host, c)[0] == sig_lp and personal_of(client, c)[0] == sig_lp
                and not unit_items(ih, c) and not unit_items(ic, c)
                and rifle in pile_ids_at(ih, pile) and rifle in pile_ids_at(ic, pile)
                and es(client).get("inFlight") is None)

    got, dt = wait_until(done, HELD_LAND_WAIT_S, 0.2)
    ih, ic = items_by_id(host), items_by_id(client)
    new_log = [e for e in host_bulk_log(host) if e.get("iseq") not in b["log"]]
    ev.update({"landedWithin": dt if got else None,
               "personalAfter": {"host": personal_of(host, c), "client": personal_of(client, c)},
               "c": {"host": unit_sig(ih, c), "client": unit_sig(ic, c)},
               "rifleOnPile": {"host": rifle in pile_ids_at(ih, pile), "client": rifle in pile_ids_at(ic, pile)},
               "rifleAmmoOnRifle": {"host": (ih.get(rifle) or {}).get("ammo"), "client": (ic.get(rifle) or {}).get("ammo")},
               "invBulkSent": sent_bulk(client) - b["sent"], "hostInvBulkLog": new_log,
               "hostInvBulkDenied": [b["denied"], host_bulk_denied(host)],
               "guard": {"before": b["guard"], "after": es(client).get("invGuard")},
               "inFlight": es(client).get("inFlight"), "lastDeny": es(client).get("lastDeny"),
               "views": {"host": view_brief(inv_view(host)), "client": view_brief(inv_view(client))},
               "turn": [turn(host), turn(client)]})
    evidence("save_while_order_in_flight", ev)

    fails = []
    h_after = ev["personalAfter"]["host"][0]
    if h_after != sig_lp:
        unfixed = (" - without the fix: the save pressed while C's order was in flight was dropped (the host's copy "
               "unchanged; "
               f"client inv_bulk sent +{ev['invBulkSent']})") if h_after == before["host"][0] else ""
        fails.append(f"save_while_order_in_flight: the host's C personal layout {before['host'][0]} -> {h_after} (want "
                     f"the saved L' {sig_lp}: the host's shared world receives every save){unfixed}")
    if not ev.get("orderInFlightWithin") or (order or {}).get("kind") != "inv_move":
        fails.append(f"save_while_order_in_flight: FIXTURE - C's rifle order never showed in flight on the client "
                     f"({order}, defer {ev['defer']}, click {ev['rifleOut']})")
    elif not save.get("orderHeldAtPress"):
        fails.append(f"save_while_order_in_flight: FIXTURE - the host had already admitted the order "
                     f"{order.get('iseq')} when the save was "
                     f"pressed (log {save.get('hostLogAfterPress')}): the press was not inside the hold")
    if save and (save.get("cursor") != -1 or not save.get("clientSavedWithin")):
        fails.append(f"save_while_order_in_flight: FIXTURE - the client's own save did not run (cursor "
                     f"{save.get('cursor')}, personal "
                     f"{ev['personalAfter']['client']}; want L' {sig_lp} written by vanilla)")
    if ev["personalAfter"]["client"][0] != h_after and h_after == sig_lp:
        fails.append(f"save_while_order_in_flight: the client's C personal {ev['personalAfter']['client'][0]} != the "
                     f"host's {h_after}")
    if ev["c"]["host"] or ev["c"]["client"] or not all(ev["rifleOnPile"].values()):
        fails.append(f"save_while_order_in_flight: the held order did not complete: C host {ev['c']['host']} client "
                     f"{ev['c']['client']}, rifle "
                     f"on the pile {ev['rifleOnPile']} (want C empty, the rifle on the pile on both)")
    if ev["rifleAmmoOnRifle"]["host"] != ev["rifleAmmoOnRifle"]["client"]:
        fails.append(f"save_while_order_in_flight: the rifle's ammo differs {ev['rifleAmmoOnRifle']}")
    if len(new_log) != 1:
        fails.append(f"save_while_order_in_flight: the host received {len(new_log)} inv_bulk after the press "
                     f"({new_log}; want 1: the save)")
    if ev["hostInvBulkDenied"][1] != ev["hostInvBulkDenied"][0]:
        fails.append(f"save_while_order_in_flight: the host denied inv_bulk {ev['hostInvBulkDenied']} (want none)")
    if ev["inFlight"] is not None:
        fails.append(f"save_while_order_in_flight: the client still has an order in flight {ev['inFlight']}")
    for side, v in ev["views"].items():
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"save_while_order_in_flight: the {side}'s pre-battle screen is not on top ({v})")
    if ev["turn"] != [0, 0]:
        fails.append(f"save_while_order_in_flight: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, ctx, "save_while_order_in_flight")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine. save_keeps_armor runs before
# saves_reach_host (its personal save is the boot's first, so the host's personalArmor changes in that row).
STEPS = ((None, spine_both_briefings),
         (None, spine_units),
         (None, spine_stage),
         (None, spine_open_screens),
         ("save_keeps_armor", row_save_keeps_armor),
         ("saves_reach_host", row_saves_reach_host),
         ("save_while_order_in_flight", row_save_while_order_in_flight))
ROWS = [n for n, _ in STEPS if n]


def main():
    t0 = time.time()
    results = {}
    spine_ok = True
    try:
        js = shared_fixture.bring_up(TAG, PORTS, host_options=HOST_OPTIONS)
    except Exception as e:  # a bring-up failure fails the whole run
        print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
        return 2
    host, client = js.host, js.client
    try:
        try:
            _, _, squad = session.bring_up_shared_mixed_battle(js, OWNERS, to_tactical=False)
        except Exception as e:
            print(f"FAIL boot: {type(e).__name__}: {e} (host {stack(host)}, client {stack(client)})", flush=True)
            return 2
        ctx = {"squad": squad}
        print(f"[prebattle_equip_shared] boot ok: squad={squad} host stack={stack(host)} client "
              f"stack={stack(client)}", flush=True)
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
        try:
            js.shutdown()
        except Exception as e:
            print(f"[prebattle_equip_shared] shutdown: {short(e)}", flush=True)
        passed = [n for n in ROWS if results.get(n)]
        failed = [n for n in ROWS if not results.get(n)]
        print(f"\ntest_prebattle_equip_shared: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}"
              f"{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (results and all(results.values()) and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
