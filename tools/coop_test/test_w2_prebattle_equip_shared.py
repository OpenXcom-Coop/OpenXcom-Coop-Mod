"""W2-P8b - test_w2_prebattle_equip_shared.py: a layout the second player saves on the
pre-battle equip screen in a SHARED campaign (stage S-C, orchestrator ruling SC-1 /
F3506). Q9 (a) / D209 a: in SHARED the second player's saved layouts - its soldier's
personal layout and a global layout - are saved by the HOST into the one shared world
(in a skirmish or SEPARATE they stay local and are lost, test_w2_prebattle_equip_tools
EQ17/EQ18). AMENDMENT P8b-1 section 4 S-C pins the mechanism: `btnCreatePersonalTemplate
Click` and `saveGlobalLayout` in SHARED send `inv_bulk {op save_personal | save_global,
template, index?}` (a tracked intent, like `inv_move`) with the created template and let
vanilla's local write run; the host performs the layout write (spec docs
rewrite/prompts/w2p8b_prebattle_equip.md: the draft's (f) EQ18 "the saved layout lands
per Q9"; P8b-1 section 5 "SHARED save: host world"; AMENDMENT P8b-2 (staged items,
F3327)).

Before S-C.2 (product untouched, commits S-C.1 / S-C.1b) the save is vanilla on the
second player's own machine: its copy of the world holds the layout, the host's does
not, nothing is sent.

Boot S (ONE boot, a SHARED campaign, rows in this order; each row ONE run):
shared_fixture.bring_up (shared_fixture.py :251: new SHARED campaign, world streamed,
both on the geoscape) -> session.bring_up_shared_mixed_battle(js, OWNERS,
to_tactical=False) (session.py :2464: the roster's first two soldiers stamped owner
seat 0 / seat 1 on both machines - test_shared_battle.py's `mixed` squad, :202 - flown
to a fresh terror site and landed; returns with the host's briefing up) -> S-H's spine
up to the equip screens (session.briefings_to_battlescape :2179 without its
equip_both_ready: the client's briefing (<= 90 s), the host's briefing OK
(click_widget ok), dismiss_client_briefing) -> both pre-battle screens up and the
host's equip-open announce. C = the client-owned soldier's unit, H = the host-owned
one (their coop seat asserted on both machines).
Staging (both briefings up, client first, F607; staged items only, P8b-2): C stripped
on both machines, then L = a rifle loaded with a rifle clip in STR_RIGHT_HAND + a
grenade on STR_BELT (0,0) (battle_give; test_w2_prebattle_equip_tools's L1).
Keys: as test_w2_prebattle_equip_tools (the harness options.cfg, else Options.cpp's
defaults; the live values on both machines must match, F3507); the personal save is
the plain keyInvSavePersonalEquipment (F3505), the global save vanilla's Ctrl+1
(InventoryState::handle; index 0).
  EQ21  the client's screen on C: (a) keyInvSavePersonalEquipment; (b) Ctrl+1. GREEN
        (Q9 a, SHARED): (a) the HOST's C personal layout (equip_layouts) = L and the
        client's = the host's, one `inv_bulk` sent (client coopIntentsSent) and
        received (host intentsReceivedLog) for it, none denied; (b) the HOST's global
        layout 0 = L and the client's = the host's, one `inv_bulk` for it, none
        denied; C's items unchanged on both. RED: each save lands in the client's world
        only (the client's layout = L, the host's unchanged, 0 `inv_bulk` sent).
  RED (commit S-C.1b): EQ21 fails on its RED cell.

Common asserts: hash_now {full:true} every bucket EQUAL after the queues drain;
desyncSeen false on both; the client's turnMirrorFired 0; coopClientBStatePushes 0 on
both; the client's invLocalWrites 0; both pre-battle screens still up and turn 0 on
both; the client's pre-battle ground ids = its own pile ids (STOP-IF 8; the pile is the
client's equip.pile, the offer's) and the pile ids equal on both machines.

Each row prints ONE "EVIDENCE <id>:" line before its conditions are checked, then
"PASS <id>" / "FAIL <id>: <message>" (the RED cell first). Every wait is bounded.
WV-D99 / WV-D100: one run is the result; no skip path, no second boot. Exit 0 only when
every row passes, 2 otherwise (a bring-up or spine failure is also 2). WV-D95: run in
the foreground to completion.

Run:  python tools/coop_test/test_w2_prebattle_equip_shared.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
from session import battle_state
from test_w2_delta_core import both, short, diff_buckets, desync_record
from test_w2_delta_items import items_by_id
from test_w2_client_items import strip_both
from test_w2_prebattle_equip import (ENTRY_WAIT_S, ANSWER_WAIT_S, LAND_WAIT_S, DRAIN_WAIT_S, stack, has, es, equip,
                                     turn, in_battle, inv_view, view_brief, ground_ids, wait_until, evidence, finish,
                                     goto_unit, drained, pre_screen_fails)
from test_w2_prebattle_equip_tools import (L1_GIVE, SDLK_1, GLOBAL_INDEX, KEY_SETTLE_S, layouts, sent_bulk,
                                           host_bulk_log, host_bulk_denied, unit_sig, layout_sig, unit_dump, key,
                                           clear_mod, harness_keys)

TAG = "w2p8b_eqsh"                 # the two user dirs: s<slot>_w2p8b_eqsh_host / _client
PORTS = (49926, 49927, 48834)      # (host test label, client test label, the SHARED session port); unused elsewhere
OWNERS = {0: 0, 1: 1}              # test_shared_battle.py :202 `mixed`: squad[0] -> seat 0 (host), squad[1] -> seat 1
CLIENT_BRIEFING_WAIT_S = 90.0      # S-H's spine (session.briefings_to_battlescape): the client's briefing <= 90 s
HOST_SCREEN_WAIT_S = 10.0


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
        fails.append(f"{what}: STOP-IF 8 - the client's pre-battle ground {ground_ids(cv)} is not its own pile "
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
    """S-H's spine, first half: the client's briefing while the host's is up (D210 b)."""
    got, dt = wait_until(lambda: has(client, "BriefingState") and in_battle(client), CLIENT_BRIEFING_WAIT_S, 0.2)
    rec = {"clientBriefingWithin": dt if got else None, "hostStack": stack(host), "clientStack": stack(client),
           "turn": [turn(host), turn(client)]}
    print(f"SPINE both briefings: {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    if not got or not has(host, "BriefingState"):
        raise AssertionError(f"spine: both briefings are not up ({rec})")


def spine_stage(host, client, ctx):
    """Staging (client first, F607; staged items only): C stripped, then L; the keys; the layout baselines."""
    c = ctx["C"]
    rec = {"C": c, "ids": {}}
    ctx["staged"] = rec
    try:
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
    """S-H's spine, second half without equip_both_ready: the host's briefing OK (click_widget ok), then
    dismiss_client_briefing - both pre-battle equip screens up, the host's equip-open announce."""
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


# ===================== EQ21 =====================


def save_leg(host, client, ctx, ev, name, press, read, sig_l):
    """One save: `press()`, then wait (bounded) for the host's layout (`read(gc)`) = L and the client's = the
    host's. Returns the fails, the RED cell first."""
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
        red = " - RED: the save landed in the client's world only" if h == b["host"] and c == sig_l else ""
        fails.append(f"EQ21 {name}: the host's layout {b['host']} -> {h} (want L {sig_l}: the host saves it into the "
                     f"shared world, Q9 a){red} (the client's {b['client']} -> {c}, inv_bulk sent {sent})")
    if c != sig_l:
        fails.append(f"EQ21 {name}: FIXTURE - the client's layout {b['client']} -> {c} (want L {sig_l}: vanilla's local "
                     f"write runs on the client too)")
    if sent != 1:
        fails.append(f"EQ21 {name}: client coopIntentsSent.inv_bulk +{sent} (want +1: one inv_bulk save order)")
    if len(new_log) != 1:
        fails.append(f"EQ21 {name}: the host received {len(new_log)} inv_bulk ({new_log}; want 1)")
    if rec["hostInvBulkDenied"][1] != rec["hostInvBulkDenied"][0]:
        fails.append(f"EQ21 {name}: the host denied inv_bulk {rec['hostInvBulkDenied']} (want none)")
    if rec["inFlight"] is not None:
        fails.append(f"EQ21 {name}: the client still has an order in flight {rec['inFlight']}")
    return fails


def eq21_shared_saves(host, client, ctx):
    c = ctx.get("C")
    fails = pre_screen_fails(host, client, "EQ21", host_too=True)
    s = ctx.get("staged") or {}
    if not s.get("sigL") or s.get("error") or not ctx.get("keys") or not ctx.get("pile"):
        fails.append(f"EQ21: the spine did not complete (staged {s.get('error')}, pile {ctx.get('pile')})")
    nav = []
    if not fails:
        if not goto_unit(client, c, [c], nav):
            fails.append(f"EQ21: the client's screen never showed C {c} ({nav})")
        elif inv_view(client).get("selectedItem") != -1:
            fails.append(f"EQ21: the client's cursor holds {inv_view(client).get('selectedItem')} (want empty)")
    if fails:
        evidence("EQ21", {"nav": nav, "C": c})
        finish([f.replace("EQ21: ", "EQ21: precondition absent - ") for f in fails])
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
    evidence("EQ21", ev)
    ci = ev["cItems"]
    if not (ci["hostPost"] == ci["hostPre"] == ci["clientPost"] == ci["clientPre"] == sig_l) or not ev["cDumpEqual"]:
        fails.append(f"EQ21: C's items changed or differ ({ci}, dumps equal {ev['cDumpEqual']}; want L unchanged on "
                     f"both: a save moves no item)")
    for side, v in ev["views"].items():
        if not (v.get("open") and v.get("top") and v.get("preBattle")):
            fails.append(f"EQ21: the {side}'s pre-battle screen is not on top ({v})")
    if ev["turn"] != [0, 0]:
        fails.append(f"EQ21: turn host/client {ev['turn']} (want 0 on both)")
    fails += tail_fails(host, client, ctx, "EQ21")
    finish(fails)


# (name, fn): a named step is a row (PASS/FAIL line); a None step is the fixture spine.
STEPS = ((None, spine_both_briefings),
         (None, spine_units),
         (None, spine_stage),
         (None, spine_open_screens),
         ("EQ21", eq21_shared_saves))
ROWS = [n for n, _ in STEPS if n]


def main():
    t0 = time.time()
    results = {}
    spine_ok = True
    try:
        js = shared_fixture.bring_up(TAG, PORTS)
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
        print(f"[w2p8b-sc] boot S ok: squad={squad} host stack={stack(host)} client stack={stack(client)}", flush=True)
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
            print(f"[w2p8b-sc] shutdown: {short(e)}", flush=True)
        passed = [n for n in ROWS if results.get(n)]
        failed = [n for n in ROWS if not results.get(n)]
        print(f"\ntest_w2_prebattle_equip_shared: {len(passed)}/{len(ROWS)} passed (pass={passed} fail={failed}"
              f"{'' if spine_ok else ' SPINE FAILED'}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if (results and all(results.values()) and spine_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
