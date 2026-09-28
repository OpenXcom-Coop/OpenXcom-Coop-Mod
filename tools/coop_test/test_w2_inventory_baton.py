"""W2-P8 S-C1 - test_w2_inventory_baton.py: traditional mode, the in-battle
inventory and the baton (owner D130: the baton holder moves items in its own
soldiers' inventory; the other player may open its own soldiers' inventory to
LOOK, and every placement is refused with "Not your turn - waiting for <name>",
the host too, V12). Spec docs rewrite/prompts/w2p8_inventory.md: S-C1 PINNED
STAGE TEXT (AMENDMENT P8-3), AMENDMENT P8-3a (C7: item ids from each row's own
staging record), AMENDMENT P8-3b.

ALL FOUR ROWS ARE DECLARED GREEN AT RED (OR2 (a), F2409; the W2-P7 S-D1
precedent): S-A put the baton check at the inventory execution points on both
machines, and onIntent's not_your_go term refuses a forged order before any
per-kind branch. This file is the regression proof of D130's traditional rule on
the real UI.

ONE boot (T0-8 B's traditional boot, docs rewrite/w2p8-task0/t0_common.py
boot_traditional :103-:116: roster-pinned lobby, pre_ok_traditional, MAP_FP,
pin_ai_neutral, the baton on seat 0 on both; the paperdoll option on both as in
test_w2_inventory.py). Rows in this order, every row ONE run, every row restages
on its own P8-2 T0-1 tile with the K0 kit through client-first lever pairs:
  IB1  client LOOK off-baton (baton 0). The client opens C's inventory
       (battle_open_inventory), picks the grenade (belt (1,0)), drops it on
       STR_LEFT_HAND, right-clicks, closes. The screen opens; the drop gives
       invGuard.last {site drop, op move, decision baton}, client
       coopLocalExecBlocked +1, invLastWarning "Not your turn - waiting for
       HostPlayer", client coopIntentsSent unchanged, host intentsReceived and
       lastSeqEmitted unchanged; the grenade stays on the cursor until the
       right-click, then -1; EQUAL.
  IB4  forged off-baton order (baton 0): client battle_intent {kind inv_move,
       actor C, plan {op move, item <the row's grenade>, to {STR_LEFT_HAND, 0,
       0}}}: client lastDeny.reason not_your_go; host closedContexts gains
       nothing; nothing executed; EQUAL.
  (the pass: host battle_action end_turn_button -> coopActiveSeat 1 on both; T0-5
       = F2408. Not a row: its record is printed and IB3 / IB2 need it.)
  IB3  host LOOK off-baton (V12, baton 1). The host opens H's inventory, picks H's
       grenade, drops it on STR_LEFT_HAND, right-clicks, closes: host
       invGuard.last {site drop, op move, decision baton}, host
       coopLocalExecBlocked +1, host invLastWarning "Not your turn - waiting for
       ClientPlayer", H unchanged on both, host syncEvsEmitted +0; EQUAL.
  IB2  the baton holder moves (baton 1): client IV3 on C (grenade belt (1,0) ->
       STR_LEFT_HAND): admitted - host closedContexts +1 {intent, inv_move, C},
       the grenade STR_LEFT_HAND owner C on both, C TU 64 - 4 on both; EQUAL.

Common asserts (after wait_host_idle, test_w2_inventory.common_fails): hash_now
full EQUAL; desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client invLocalWrites 0; host inventory_view.open false; the client's
invGuard as the row names it.

Each row prints ONE "EVIDENCE <id>:" line with both machines' fields before its
conditions are checked; every row runs after an earlier failure; "PASS <id>" /
"FAIL <id>: <message>". Exit 0 only when every row passes, 2 otherwise (a
bring-up failure is also 2). WV-D99 / WV-D100: one run is the result. WV-D95: run
in the foreground to completion.

Run:  python tools/coop_test/test_w2_inventory_baton.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, assert_hash_clean, pin_ai_neutral
import test_w2_inventory as inv
from test_w2_inventory import (C_ID, H_ID, BELT, LH, RIFLE, RIFLE_CLIP, PISTOL_CLIP, GRENADE, STAGE_H, ROW_DIR,
                               OPTS, TU_MAX, C_TU_MAX, TU_BELT_TO_HAND, stack, inv_view, selected, click, pick,
                               right_click_return, close_client, open_client, open_fails, order_done, evidence,
                               finish, wait_until, iview, count_of, new_contexts, common_fails, admitted_fails,
                               nothing_sent_fails, item_fails, tu_fails, give, drop, give_primed, snap, collect,
                               rec_view, inv_req, send_intent, staged_fails)
from test_w2_delta_core import diff_buckets, short
from test_w2_delta_items import items_by_id
from test_w2_client_items import strip_both
import test_w2_client_shoot as cs
import test_w2_host_combat as hc
from test_rw_turn_baton import pre_ok_traditional
from test_rw_turn_mode import live_mode, TRADITIONAL

# ----- constants (P8-2 T0-1 tiles, all z 0 and empty open tiles; P8-2 T0-1 "Max TU C 64, H 58") -----
IB1_TILE = (2, 33, 0)             # P8-2 T0-1 STAGE_C
IB4_TILE = (0, 34, 0)             # P8-2 T0-1 IV2 tile
IB2_TILE = (1, 33, 0)             # P8-2 T0-1 IV4 tile
IB3_H_TILE = STAGE_H              # P8-2 T0-1 STAGE_H (48,24,0)
H_TU_MAX = 58
PASS_WAIT_S = 10.0                # T0-5 (F2408): the baton 0 -> 1 on both within 0.1 s of the host's END TURN
CLICK_WAIT_S = 2.0
ORDER_TIMEOUT_S = 20

# ----- texts (en-US STR_COOP_DENY_NOT_YOUR_GO "Not your turn - waiting for {0}", R3.5; the seat names
# repro_atom_walk.HOST_PLAYER / CLIENT_PLAYER) -----
TEXT_NOT_YOUR_GO_HOST = "Not your turn - waiting for HostPlayer"      # on the client, baton 0
TEXT_NOT_YOUR_GO_CLIENT = "Not your turn - waiting for ClientPlayer"  # on the host, baton 1


def restage_c(host, client, key, tile):
    """test_w2_inventory.restage (ST5 a, kit K0) with C's tile for this file's row `key`."""
    inv.ROW_TILE[key] = tile
    return inv.restage(host, client, key, "K0")


def restage_h(host, client, tile):
    """test_w2_inventory.restage (:356-:368, :391) kit K0 for unit H, copied; the teleport is
    test_w2_client_shoot.place (re-entrant, CLAUDE.local.md S2) instead of tele_both."""
    rec = {"tile": tile}
    rec["place"] = cs.place(host, client, H_ID, tile, ROW_DIR)
    rec["stripped"] = strip_both(host, client, H_ID)
    ids = {}
    ids["rifle"] = give(host, client, H_ID, RIFLE, "right")
    ids["beltClip"] = give(host, client, H_ID, RIFLE_CLIP, BELT, 0, 0)
    ids["grenade"] = give(host, client, H_ID, GRENADE, BELT, 1, 0)
    ids["primed"] = give_primed(host, client, H_ID, 3, 0)
    ids["groundClip"] = drop(host, client, tile, RIFLE_CLIP)
    ids["groundPistolClip"] = drop(host, client, tile, PISTOL_CLIP)
    rec["ids"] = ids
    rec["tu"] = cs.set_tu_both(host, client, H_ID, TU_MAX)
    return rec


def seats(host, client):
    return {"host": event_state(host).get("coopActiveSeat"), "client": event_state(client).get("coopActiveSeat")}


def baton_precondition(host, client, want, what):
    s = seats(host, client)
    if s != {"host": want, "client": want}:
        return [f"precondition ({what}): coopActiveSeat {s} (want {want} on both)"]
    return []


# ===================== rows =====================


def ib1_client_look(host, client, ctx):
    notes = []
    leftover = inv.ensure_closed(client, notes)
    st = restage_c(host, client, "IB1", IB1_TILE)
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    pre = baton_precondition(host, client, 0, "IB1")
    before = snap(host, client)
    ww0 = event_state(client).get("invWarningWrites")
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = returned = False
    if opened:
        picked = pick(client, ev, "pick", BELT, 1, 0, g)
        if picked:
            gc0 = inv.guard_counts(inv.probes(client))
            ev["drop"] = click(client, slot=LH, x=0, y=0)
            _, ev["dropWaited"] = wait_until(lambda: inv.guard_counts(inv.probes(client)) != gc0, CLICK_WAIT_S)
            ec = event_state(client)
            ev["afterDrop"] = {"cursor": selected(client), "invGuardLast": (ec.get("invGuard") or {}).get("last"),
                               "blocked": ec.get("coopLocalExecBlocked"), "invLastWarning": ec.get("invLastWarning"),
                               "invWarningWrites": (ww0, ec.get("invWarningWrites")),
                               "sent": ec.get("coopIntentsSent"), "inFlight": ec.get("inFlight")}
            returned = right_click_return(client, ev, "rightClick", BELT, 1, 0)
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IB1", {"staging": st, "stagedDiff": staged, "seats": seats(host, client), "ui": ev,
                     "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + list(pre) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IB1")
    elif not picked:
        fails.append(f"IB1: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want {g})")
    else:
        ad = ev["afterDrop"]
        if ad["cursor"] != g:
            fails.append(f"IB1: client selectedItem {ad['cursor']} after the refused drop (want {g}: still selected)")
        if ad["blocked"] != (before["client"]["coopLocalExecBlocked"] or 0) + 1:
            fails.append(f"IB1: client coopLocalExecBlocked {before['client']['coopLocalExecBlocked']} -> "
                         f"{ad['blocked']} (want +1)")
        if ad["invLastWarning"] != TEXT_NOT_YOUR_GO_HOST:
            fails.append(f"IB1: client invLastWarning {ad['invLastWarning']!r} (want {TEXT_NOT_YOUR_GO_HOST!r})")
        if not returned:
            fails.append(f"IB1: the right-click left {ev['rightClick'].get('cursor')} on the cursor (want -1)")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IB1: the client's screen did not close: {ev.get('close')}")
    fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IB1")
    fails += tu_fails(rec, C_TU_MAX, "IB1")
    fails += nothing_sent_fails(before, rec, "IB1")
    fails += common_fails(host, client, before, {"baton": 1},
                          {"site": "drop", "op": "move", "decision": "baton", "itemId": g, "actorId": C_ID}, "IB1")
    finish(fails)


def ib4_forged_order(host, client, ctx):
    notes = []
    leftover = inv.ensure_closed(client, notes)
    st = restage_c(host, client, "IB4", IB4_TILE)
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    pre = baton_precondition(host, client, 0, "IB4")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    req = inv_req(C_ID, g, LH, 0, 0)
    si = send_intent(host, client, req, notes)
    rec = collect(host, client, seq0)
    new = new_contexts(before["host"]["closedContexts"], rec["host"]["closedContexts"])
    evidence("IB4", {"staging": st, "stagedDiff": staged, "seats": seats(host, client), "req": req,
                     "intent": {k: v for k, v in si.items() if k != "resp"}, "resp": si["resp"],
                     "newContexts": new, "row": rec_view(before, rec, st["ids"]), "notes": notes,
                     "leftover": leftover})
    fails = list(notes) + list(pre) + staged_fails(st, staged)
    if not si["sent"]:
        fails.append(f"IB4: battle_intent answered {si['resp']} (want sent: an iseq)")
    else:
        ld = rec["client"]["lastDeny"] or {}
        if ld.get("iseq") != si["iseq"] or ld.get("reason") != "not_your_go":
            fails.append(f"IB4: client lastDeny {rec['client']['lastDeny']} (want {{iseq {si['iseq']}, reason "
                         f"not_your_go}})")
    if new or rec["host"]["lastSeqEmitted"] != before["host"]["lastSeqEmitted"]:
        fails.append(f"IB4: host lastSeqEmitted {before['host']['lastSeqEmitted']}->{rec['host']['lastSeqEmitted']} "
                     f"newContexts={new} (want nothing executed)")
    if rec["client"]["inFlight"] is not None:
        fails.append(f"IB4: client inFlight after the deny {rec['client']['inFlight']} (want null)")
    fails += item_fails(rec, g, {"owner": C_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}, "IB4")
    fails += tu_fails(rec, C_TU_MAX, "IB4")
    fails += common_fails(host, client, before, {}, None, "IB4")
    finish(fails)


def pass_baton(host, client):
    """T0-5 (F2408): the host's END TURN hands the baton 0 -> 1 on both. Not a row."""
    out = {"before": seats(host, client)}
    r = host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    out["endTurn"] = {k: r.get(k) for k in ("ok", "error")}
    got, out["waited"] = wait_until(lambda: seats(host, client) == {"host": 1, "client": 1}, PASS_WAIT_S)
    out["after"] = seats(host, client)
    out["ok"] = bool(got)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        out["idleErr"] = short(e)
    print("EVIDENCE pass: " + repr(out), flush=True)
    return out


def ib3_host_look(host, client, ctx):
    notes = []
    leftover = inv.ensure_closed(client, notes)
    hst = restage_h(host, client, IB3_H_TILE)
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    gh = hst["ids"]["grenade"]
    pre = baton_precondition(host, client, 1, "IB3")
    if not (ctx.get("pass") or {}).get("ok"):
        pre.append(f"precondition (IB3): the baton pass failed ({ctx.get('pass')})")
    before = snap(host, client)
    hb0 = event_state(host)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    ro = host.cmd({"cmd": "battle_open_inventory", "unit": H_ID})
    ev["open"] = {k: ro.get(k) for k in ("ok", "opened", "error")}
    hv = inv_view(host)
    ev["openView"] = {k: hv.get(k) for k in ("open", "top", "unitId", "selectedItem")}
    opened = bool(ro.get("opened")) and hv.get("top") is True and hv.get("unitId") == H_ID
    picked = returned = False
    if opened:
        picked = pick(host, ev, "pick", BELT, 1, 0, gh)
        if picked:
            gc0 = inv.guard_counts(inv.probes(host))
            ev["drop"] = click(host, slot=LH, x=0, y=0)
            _, ev["dropWaited"] = wait_until(lambda: inv.guard_counts(inv.probes(host)) != gc0, CLICK_WAIT_S)
            eh = event_state(host)
            ev["afterDrop"] = {"cursor": selected(host), "invGuard": eh.get("invGuard"),
                               "blocked": eh.get("coopLocalExecBlocked"), "invLastWarning": eh.get("invLastWarning"),
                               "invWarningWrites": (hb0.get("invWarningWrites"), eh.get("invWarningWrites"))}
            returned = right_click_return(host, ev, "rightClick", BELT, 1, 0)
        rc = host.cmd({"cmd": "battle_close_inventory"})
        gone, _ = wait_until(lambda: "InventoryState" not in stack(host), CLICK_WAIT_S)
        ev["close"] = {"ok": rc.get("ok"), "error": rc.get("error"), "closed": bool(gone)}
    session.wait_host_idle(host, client, timeout=30)
    rec = collect(host, client, seq0)
    hb1 = event_state(host)
    evidence("IB3", {"staging": hst, "stagedDiff": staged, "seats": seats(host, client), "ui": ev,
                     "hostSync": (hb0.get("syncEvsEmitted"), hb1.get("syncEvsEmitted")),
                     "row": rec_view(before, rec, {"hGrenade": gh}), "notes": notes})
    fails = list(notes) + list(pre)
    if staged:
        fails.append(f"buckets differ after the staging: {staged} (want none)")
    if hst["tu"] != H_TU_MAX:
        fails.append(f"precondition: H's TU after the staging {hst['tu']} (want {H_TU_MAX})")
    if not opened:
        fails.append(f"IB3: the host's inventory did not open on H ({ev['open']}, {ev['openView']})")
    elif not picked:
        fails.append(f"IB3: the host's click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor "
                     f"(want {gh})")
    else:
        ad = ev["afterDrop"]
        gl = (ad["invGuard"] or {}).get("last") or {}
        want_last = {"site": "drop", "op": "move", "decision": "baton", "itemId": gh, "actorId": H_ID}
        if {k: gl.get(k) for k in want_last} != want_last:
            fails.append(f"IB3: host invGuard.last {gl} (want {want_last})")
        if ad["blocked"] != (hb0.get("coopLocalExecBlocked") or 0) + 1:
            fails.append(f"IB3: host coopLocalExecBlocked {hb0.get('coopLocalExecBlocked')} -> {ad['blocked']} "
                         f"(want +1)")
        if ad["invLastWarning"] != TEXT_NOT_YOUR_GO_CLIENT:
            fails.append(f"IB3: host invLastWarning {ad['invLastWarning']!r} (want {TEXT_NOT_YOUR_GO_CLIENT!r})")
        if ad["cursor"] != gh:
            fails.append(f"IB3: host selectedItem {ad['cursor']} after the refused drop (want {gh})")
        if not returned:
            fails.append(f"IB3: the host's right-click left {ev['rightClick'].get('cursor')} on the cursor (want -1)")
        if not ev["close"]["closed"]:
            fails.append(f"IB3: the host's screen did not close: {ev['close']}")
    ih, ic = iview(rec["ih"], gh), iview(rec["ic"], gh)
    want = {"owner": H_ID, "slot": BELT, "slotX": 1, "slotY": 0, "onTile": False}
    for m, it in (("host", ih), ("client", ic)):
        if {k: (it or {}).get(k) for k in want} != want:
            fails.append(f"IB3: {m} H grenade {it} (want {want}: H unchanged)")
    th, tc = (rec["uh"].get(H_ID) or {}).get("tu"), (rec["uc"].get(H_ID) or {}).get("tu")
    if (th, tc) != (H_TU_MAX, H_TU_MAX):
        fails.append(f"IB3: H tu host={th} client={tc} (want {H_TU_MAX} on both: H unchanged)")
    if hb1.get("syncEvsEmitted") != hb0.get("syncEvsEmitted"):
        fails.append(f"IB3: host syncEvsEmitted {hb0.get('syncEvsEmitted')} -> {hb1.get('syncEvsEmitted')} "
                     f"(want +0)")
    fails += common_fails(host, client, before, {}, None, "IB3")
    finish(fails)


def ib2_baton_holder_moves(host, client, ctx):
    notes = []
    leftover = inv.ensure_closed(client, notes)
    st = restage_c(host, client, "IB2", IB2_TILE)
    session.wait_host_idle(host, client, timeout=30)
    staged = diff_buckets(host, client)
    g = st["ids"]["grenade"]
    pre = baton_precondition(host, client, 1, "IB2")
    if not (ctx.get("pass") or {}).get("ok"):
        pre.append(f"precondition (IB2): the baton pass failed ({ctx.get('pass')})")
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev = {"leftover": leftover}
    opened = open_client(client, ev)
    picked = False
    if opened:
        picked = pick(client, ev, "pick", BELT, 1, 0, g)
        if picked:
            ev["drop"] = click(client, slot=LH, x=0, y=0)
            ev["sent"] = inv.wait_sent(host, client, before)
            got, ev["orderWaited"] = wait_until(lambda: order_done(host, client), ORDER_TIMEOUT_S, 0.1)
            if not got:
                notes.append(f"the order never finished in {ORDER_TIMEOUT_S} s")
        close_client(client, ev)
    rec = collect(host, client, seq0)
    evidence("IB2", {"staging": st, "stagedDiff": staged, "seats": seats(host, client), "ui": ev,
                     "row": rec_view(before, rec, st["ids"]), "notes": notes})
    fails = list(notes) + list(pre) + staged_fails(st, staged)
    if not opened:
        fails += open_fails(ev, "IB2")
    elif not picked:
        fails.append(f"IB2: the click on STR_BELT (1,0) put {ev['pick'].get('cursor')} on the cursor (want {g})")
    else:
        f, cx = admitted_fails(before, rec, "IB2")
        fails += f
        fails += item_fails(rec, g, {"owner": C_ID, "slot": LH, "onTile": False}, "IB2")
        fails += tu_fails(rec, C_TU_MAX - TU_BELT_TO_HAND, "IB2")
        if not (isinstance(ev.get("close"), dict) and ev["close"]["closed"]):
            fails.append(f"IB2: the client's screen did not close: {ev.get('close')}")
    fails += common_fails(host, client, before, {"sent": 1},
                          {"site": "drop", "op": "move", "decision": "sent", "itemId": g, "actorId": C_ID}, "IB2")
    finish(fails)


# ===================== bring-up =====================


def boot_traditional(host, client):
    """Copied from docs rewrite/w2p8-task0/t0_common.py boot_traditional (:103-:116; P8-3 S-C1 TASK 0 "the baton
    file's boot = T0-8 B's"): test_w2_client_baton.boot minus its skill mod - roster-pinned lobby,
    pre_ok_traditional (CoopTurnMode traditional on the host + set_seed 1), MAP_FP, pin_ai_neutral, H check,
    coopActiveSeat 0 on both, wait_host_idle, hash clean."""
    hc.bring_up_lobby_roster_pinned(host, client, hc.PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=hc.MISSION, seat_count=2,
                                 pre_ok=pre_ok_traditional)
    modes = {gc.name: live_mode(gc) for gc in (host, client)}
    assert modes == {"host": TRADITIONAL, "client": TRADITIONAL}, f"live battle mode {modes}"
    hs, cs_ = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == hc.MAP_FP and cs_.get("mapFingerprint") == hc.MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs_.get('mapFingerprint')!r}")
    pinned = pin_ai_neutral(host, client, tag="w2p8-t0b")
    assert pinned, "pin_ai_neutral pinned nothing"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == hc.COOP_SEAT_0
                   and u.get("faction") == hc.FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]}"
    seats_ = {gc.name: event_state(gc).get("coopActiveSeat") for gc in (host, client)}
    assert seats_ == {"host": 0, "client": 0}, f"coopActiveSeat {seats_}"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="traditional bring-up")
    print(f"BOOT traditional ok: modes={modes} seats={seats_} seated={seated} pinned={len(pinned)}", flush=True)
    return seated


def boot(host, client):
    seated = boot_traditional(host, client)
    sid_to_uid = {u.get("soldierId"): u["id"] for u in battle_state(host)["units"] if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == inv.SEATED, f"seated client units {seated_uids} (baked {inv.SEATED})"
    for gc in (host, client):
        es = event_state(gc)
        assert (isinstance(es.get("invLocalWrites"), int) and isinstance(es.get("invLastWarning"), str)
                and isinstance(es.get("invGuard"), dict)), f"{gc.name} event_state lacks the W2-P8 probes: {es}"
        assert gc.cmd({"cmd": "inventory_view"}).get("ok"), f"{gc.name}: inventory_view is not a known command"
    return {}


SCENARIOS = (("IB1", ib1_client_look), ("IB4", ib4_forged_order), ("PASS", None), ("IB3", ib3_host_look),
             ("IB2", ib2_baton_holder_moves))


def main():
    t0 = time.time()
    host = GameClient("host", 49940, make_user_dir("w2p8_baton_host", options=OPTS))
    client = GameClient("client", 49941, make_user_dir("w2p8_baton_client", options=OPTS))
    results = {}
    rows = [n for n, fn in SCENARIOS if fn]
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            if fn is None:
                try:
                    ctx["pass"] = pass_baton(host, client)
                except Exception as e:
                    ctx["pass"] = {"ok": False, "err": short(e)}
                    print(f"EVIDENCE pass: {ctx['pass']}", flush=True)
                continue
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
                print(f"[w2p8-sc1-baton] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n in rows if results.get(n)]
    failed = [n for n in rows if not results.get(n)]
    print(f"\ntest_w2_inventory_baton: {len(passed)}/{len(rows)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
