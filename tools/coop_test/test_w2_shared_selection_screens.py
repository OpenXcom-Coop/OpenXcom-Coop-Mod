"""W2-P7 S-C-E2 - test_w2_shared_selection_screens.py: in a SHARED campaign the Transfer and Alien Containment screens
share ONE list of pending amounts per screen, as the Sell screen does since S-C-E1 (owner D184 (a), D203; MR7, MR9,
MR10, MR16): an amount either player sets shows on the other player's screen with a label naming that player, a
rejected Transfer keeps the list and the screen (MR10), the other player's screen stays open after a confirm, rebuilt
at zero (D204 (a)), and a confirm whose confirmer sees none of the list's rows (the other player's soldier rows are
hidden, MR7) still applies the list (F6341, V-E3) (docs rewrite/prompts/w2p7_sc_design.md section 4, AMENDMENT P7-8
sections 3-4: PR-47..PR-51; the E1 green rulings: F6341 folded into S-C-E2). D243 (owner 2026-10-05): the label sits
just above the OK/Cancel buttons while another player has the same screen open; in a SHARED campaign the Transfer list
is ALWAYS one text row shorter (the label's row), with or without the other player; Alien Containment keeps its list
(its gap above the buttons holds the label) - rows E2-gx / E2-gc (commit S-C-E2.1b).

Before S-C-E2 (design section 4, F6341): TransferItemsState and ManageAlienContainmentState are not on the shared
selection - each machine keeps its own amounts, the other player never sees them, the store (sel_state) holds no
xfer / cont key and no label is drawn; a Transfer confirm built from the confirmer's visible rows only submits
nothing when the list holds only the other player's soldier row (TransferItemsState :774, F6341's Transfer shape).

Fixtures (AMENDMENT P7-8 section 4.2; a pre-cell failure is a FIXTURE-STOP: one CAPTURE line, every row of the boot
FAILs "pre-cell"):
  XFER = SEL (test_w2_shared_selection.sel_pre on shared_fixture.bring_up(tag, (0, 0, "47262")): the first base-0
         soldier owned by seat 1, off its craft on both) + test_w2_shared_page3.fx_b (the client builds "Second Base",
         the host fac_builds its General Stores, buildTime 0 on both, R-D1-2). Each row turns every hold off,
         dismisses any box, cancels any base screen on both, restores the boot's funds on both (client first),
         restages STR_RIFLE x XFER_STAGE with give_items on both (client first, S25), then opens the REAL screens on
         both (host first): screen_push {transfer_base, base 0} (BasescapeState :686), screen_pick_base {0, 1}
         (TransferBaseState :162) -> TransferItemsState, key xfer|n|0|1.
  E2-xe staging (this file's construction, F6453; F6341 on Transfer, F6451): host fac_build STR_LIVING_QUARTERS at "Second Base"
         (QUARTERS_X, QUARTERS_Y) next to its lift, both machines list it, buildTime 0 on both (client first) - the
         Transfer screen refuses a soldier row while the destination has no free quarters (TransferItemsState :1398).
  CONT = SEL (port 47263) + FX-CT's geoscape half (host fac_build STR_ALIEN_CONTAINMENT at (0, 3), index 9 on both,
         set_facility_build_time 0 on both, give_items {STR_SECTOID_SOLDIER, 4} on both, client first); the row opens
         screen_push {containment, base 0, prisonType 0} on both (BasescapeState :904; key cont|n|0|p0).
  Probes / levers: screen_push (PR-51), screen_rows (+ textItems [{text, visible}], rows[i].color, secondaryColor,
  highlightColor, PR-51), screen_set_amount, screen_pick_base, sel_state (PR-46), set_funds (both, client first),
  click_widget on the real captions (Transfer, OK, Cancel, Remove Selected), coop_dialog_back ONLY on a CoopState top,
  dismiss_popup ONLY on an ErrorMessageState top (F4333).
  Labels: "Also on this screen: <the other seat's roster name>" (STR_COOP_ALSO_ON_SCREEN, D203, PR-50 (iii); the
  roster = save_markers.coopPlayers, seat 0 = the host).

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot XFER (port 47262): E2-xa, E2-xr, E2-xe, E2-gx.
  E2-xa (1) client Rifle = 3 -> the host's Rifle amount 3 within SEL_S.
        (2) host Rifle = 4 -> the client's Rifle amount 4 within SEL_S; both screens' textItems hold the label naming
            the other player, visible.
  E2-xr (1) client Rifle = 4 (local); set_funds {-1} on both (client first; R-E2-1: HostBase and Second Base share
            coordinates, so the transfer costs $0 and only funds below 0 fail transferValidate's funds check, F6447,
            F6448); client Transfer -> OK: within PAGE_S the client's top CoopState (556) with TransferItemsState
            directly under it; sel_state xfer|n|0|1 rows {i:STR_RIFLE: 4}, rev unchanged by the rejected confirm, on
            both (MR10).
        (2) coop_dialog_back; funds restored on both; client Transfer -> OK: within PAGE_S the client's
            TransferItemsState and TransferBaseState gone; the host's top stays TransferItemsState (rebuilt), every
            amount 0 (D204); shared_checksum.chkTransfers +1 on both; world_diff empty.
  E2-xe (1) (F6341, MR7, V-E3) the client sets ONLY its own soldier's row to 1; the host's screen_rows lists no row
            named after that soldier (MR7); the host's sel_state xfer|n|0|1 rows == {s:<id>: 1} within SEL_S.
        (2) host Transfer -> OK: within PAGE_S the host's TransferItemsState and TransferBaseState gone; the soldier
            left base 0 on both within EQUAL_S (in transit); chkTransfers +1 on both; the client's top stays
            TransferItemsState (rebuilt), every amount 0; no CoopState.
  E2-gx (D243; geometry = list_widgets on the top state: the first TextList's rect, the Cancel button's rect, every
            Text starting with the label's head)
        (1) the host alone opens the Transfer screen (base 0 -> 1): its list height == SHARED_LIST_H (128 - 8 = 120:
            one text row shorter than vanilla's 128) and no label visible, within SEL_S.
        (2) the client opens it too: on both the list height stays 120 and a VISIBLE label names the other player, its
            rect between the list's bottom and the Cancel button's top, within SEL_S.
        (3) the host Cancels: the client's list height stays 120, its label hidden, within SEL_S.
  Boot CONT (port 47263): E2-ca, E2-gc.
  E2-ca (1) client L = 2 -> the host's L amount 2 within SEL_S; both screens' labels visible.
        (2) host Remove Selected: its screen gone within PAGE_S; the client's ManageAlienContainmentState stays (rebuilt
            in place), every amount 0; L stock 2 and STR_SECTOID_CORPSE +2 on both; world_diff empty.
  E2-gc (D243) (1) the host alone opens containment: its list height == 112 (vanilla, unchanged), no label visible.
        (2) the client opens it too: both lists 112; on both a VISIBLE label names the other player, its rect between the
            list's bottom and the Cancel button's top (the containment's gap above its buttons), within SEL_S.
Guard on every row: no new crash log; the client zero-disk at each boot's end.

RED (commit S-C-E2.1: screen_push, the row colours and textItems, these rows; product untouched): E2-xa, E2-xe and
E2-ca fail on cell 1 (the host's amount stays 0 / the host's sel_state holds no xfer key), E2-xr on cell 1 (sel_state
lacks the key). RED (commit S-C-E2.1b, D243, test only): E2-gx fails on cell 1 (the list keeps vanilla's 128), E2-gc
on cell 2 (no label). GREEN (commit S-C-E2.2): every row passes.
Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE foreground
run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_selection_screens.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
import test_w2_battle_end_campaign as camp
import test_w2_shared_page3 as p3
import test_w2_shared_forced_storage as fst
import test_w2_shared_forced_containment as fct
import test_w2_shared_selection as e1

# ----- pins (AMENDMENT P7-8 section 4 / 4.2) -----
RIFLE = "STR_RIFLE"                      # XFER's item (looked up by type, S25)
XFER_STAGE = 20                          # XFER: give_items {STR_RIFLE, 20} on both (P7-8 section 4.2)
XFER_KEY = "xfer|n|0|1"                  # SharedEcon::xferKey(base 0 -> base 1, normal) (P7-7 PR-30 format, P7-8 PR-37)
CONT_KEY = "cont|n|0|p0"                 # SharedEcon::contKey(base 0, prisonType 0, normal)
E2XA_CLIENT, E2XA_HOST = 3, 4            # P7-8 section 4.2 E2-xa's amounts
E2XR_SET = 4                             # E2-xr's Rifle amount
E2XR_FUNDS = -1                          # R-E2-1 (F6447/F6448): the $0 base 0 -> 1 transfer fails only below 0 funds
E2CA_SET = 2                             # E2-ca's L amount
L = fct.L                                # STR_SECTOID_SOLDIER (FX-CT's live alien)
L_FILL = 4                               # CONT: give_items {STR_SECTOID_SOLDIER, 4} on both
CORPSE = "STR_SECTOID_CORPSE"            # an executed sectoid's geoscape corpse (containmentApply :947-:956)
CONTAINMENT, CT_X, CT_Y, CT_INDEX = fct.CONTAINMENT, fct.CT_X, fct.CT_Y, fct.CT_INDEX   # CONSTANTS T0-S3 (i) F5434/F5435
SECOND_BASE = p3.SECOND_BASE             # FX-B's base (index 1)
QUARTERS, QUARTERS_X, QUARTERS_Y = "STR_LIVING_QUARTERS", 2, 3   # E2-xe staging: next to Second Base's lift (3, 3)
LABEL_HEAD = "Also on this screen: "     # STR_COOP_ALSO_ON_SCREEN "Also on this screen: {0}" (D203, PR-50 (iii))
# D243 (owner 2026-10-05): the label sits just above the OK/Cancel buttons; in a SHARED campaign the Sell and Transfer
# lists are ALWAYS one text row shorter (the label's row), Alien Containment keeps its list (its gap above the buttons
# holds the label). Vanilla list heights = the screens' constructors: SellState :110 TextList(287, 120, 8, 54),
# TransferItemsState :82 TextList(287, 128, 8, 44), ManageAlienContainmentState :91 TextList(286, 112, 8, 53); one
# small-font text row = 8 px (FONT_SMALL height 9 + spacing -1, TextList::updateVisible).
ROW_H = 8
VANILLA_LIST_H = {"SellState": 120, "TransferItemsState": 128, "ManageAlienContainmentState": 112}
SHARED_LIST_H = {"SellState": 120 - ROW_H, "TransferItemsState": 128 - ROW_H, "ManageAlienContainmentState": 112}
XFER_OK, CONFIRM_OK, CANCEL = "Transfer", "OK", "Cancel"   # TransferItemsState / TransferConfirmState captions (F5572)
CONT_OK = fct.CONT_OK                    # "Remove Selected" (2-button layout: canSellLiveAliens off)
MACS = "ManageAlienContainmentState"
SHARED_FAIL = 556                        # CoopState COOP_DLG_SHARED_FAIL (CoopState.h :56)
BOOT_PORT = {"XFER": "47262", "CONT": "47263"}   # AMENDMENT P7-8 section 4 (S26, F6118): E2 = 47262 (XFER), 47263 (CONT)
SEL_S = e1.SEL_S                         # 3 s: a cross-machine amount (P7-8 section 4)
PAGE_S = e1.PAGE_S                       # 5 s: a screen push / close after a real click
SCREEN_S = e1.SCREEN_S                   # 10 s
EQUAL_S = e1.EQUAL_S                     # 10 s: a shared_apply's effect may lag one round trip
BASES_S = p3.BASES_S                     # 45 s: a facility on both machines


class FixtureMiss(Exception):
    pass


MISSES = e1.MISSES + (FixtureMiss, e1.FixtureMiss)
SCREENS = ("TransferConfirmState", "TransferItemsState", "TransferBaseState", "SellState", MACS)


# ===================== probes =====================


def short(e, n=400):
    return camp.short(e, n)


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=0.2):
    return camp.wait_until(pred, timeout, interval)


def poll(fn, timeout, interval=0.2):
    return e1.poll(fn, timeout, interval)


def rows(gc, **kw):
    return p3.rows(gc, **kw)


def as_int(s):
    return p3.as_int(s)


def row_of(r, item, mac=False):
    """(remaining, amount) of the row whose item type == item: Sell / Transfer columns 1 / 2, containment 2 / 3."""
    for row in r.get("rows") or []:
        if row.get("item") == item:
            c = row.get("cells") or []
            a, b = (2, 3) if mac else (1, 2)
            return (as_int(c[a]) if len(c) > a else None), (as_int(c[b]) if len(c) > b else None)
    return None, None


def amount(gc, item, mac=False):
    return row_of(rows(gc), item, mac)[1]


def amounts(r, mac=False):
    """{name: amount} of every row of a screen_rows reply."""
    col = 3 if mac else 2
    out = {}
    for row in r.get("rows") or []:
        c = row.get("cells") or []
        out[c[0] if c else ""] = as_int(c[col]) if len(c) > col else None
    return out


def all_zero(r, mac=False):
    a = amounts(r, mac)
    return bool(a) and all(v == 0 for v in a.values())


def sel_all(gc):
    return e1.sel_all(gc)


def sel(gc, key):
    return e1.sel(gc, key)


def sel_rows(gc, key):
    return e1.sel_rows(gc, key)


def sstats(gc):
    return fst.sstats(gc)


def hold(gc, on):
    return fst.hold(gc, on)


def click(gc, caption):
    return p3.click(gc, caption)


def set_amount(gc, value, item=None, row=None):
    return p3.set_amount(gc, value, item=item, row=row)


def no_coopstate(gc):
    return fst.no_coopstate(gc)


def dialog(gc):
    return fst.dialog(gc)


def funds(gc):
    return gc.ok({"cmd": "geo_state"}).get("funds")


def stock(gc, item, base=0):
    return p3.stock(gc, item, base)


def roster(gc):
    return e1.roster(gc)


def transfers_chk(gc):
    return p3.transfers_chk(gc)


def ok_visible(r, caption):
    return fst.ok_visible(r, caption)


def screen_ready(gc, cls):
    """Top == cls and its list holds rows (init() ran, F5573)."""
    if top(gc) != cls:
        return False
    r = rows(gc)
    return r.get("state") == cls and r.get("screen") is True and len(r.get("rows") or []) > 0


def roster_names(gc):
    """The campaign's seat -> roster name list (save_markers.coopPlayers; seat 0 = the host)."""
    return list(gc.cmd({"cmd": "save_markers"}).get("coopPlayers") or [])


def label_text(names, seat):
    """The label machine `seat` shows while the other player has the same screen open (one other player)."""
    other = 1 - seat
    return LABEL_HEAD + (names[other] if 0 <= other < len(names) else "?")


def label_items(r):
    """Every textItem whose text starts with the label's head (visible or not)."""
    return [t for t in (r.get("textItems") or []) if str(t.get("text") or "").startswith(LABEL_HEAD)]


def label_shown(r, text):
    """True when a VISIBLE textItem's text == text (asserted by text and visibility, never position: D243)."""
    return any(t.get("text") == text and t.get("visible") is True for t in (r.get("textItems") or []))


def label_hidden(r):
    """True when no textItem starting with the label's head is visible."""
    return not any(t.get("visible") is True for t in label_items(r))


def labels_cell(host, client, names, ctx, key, timeout=SEL_S):
    """Both machines' top screens show the label naming the other player, visible, within timeout."""
    want = {"host": label_text(names, 0), "client": label_text(names, 1)}
    last = {}

    def both():
        for gc in (host, client):
            last[gc.name] = label_items(rows(gc))
        return all(any(t.get("text") == want[n] and t.get("visible") is True for t in last[n]) for n in want), dict(last)
    ok, got, secs = poll(both, timeout)
    ctx[key] = {"ok": ok, "want": want, "labels": got, "secs": secs}
    return [] if ok else [f"the screens' label textItems (host, client) {got} {timeout}s on (want a visible textItem "
                          f"{want['host']!r} on the host and {want['client']!r} on the client, D203)"]


def geometry(gc):
    """list_widgets on the top state (rects in screen pixels): its first TextList {x, y, w, h, rows}, every TextButton
    by caption, every Text starting with the label's head {text, visible, x, y, w, h}."""
    ws = gc.cmd({"cmd": "list_widgets"}).get("widgets") or []

    def kind(w):
        return str(w.get("type") or "").rsplit("::", 1)[-1].split(" ")[-1]
    lst = next(({k: w.get(k) for k in ("x", "y", "w", "h")} for w in ws if kind(w) == "TextList"), None)
    if lst and isinstance(lst.get("h"), int):
        lst["rows"] = -(-lst["h"] // ROW_H)   # TextList::updateVisible: one row per started ROW_H
    return {"top": top(gc), "list": lst,
            "buttons": {str(w.get("text")): {k: w.get(k) for k in ("x", "y", "w", "h", "visible")}
                        for w in ws if kind(w) == "TextButton"},
            "labels": [{k: w.get(k) for k in ("text", "visible", "x", "y", "w", "h")} for w in ws
                       if kind(w) == "Text" and str(w.get("text") or "").startswith(LABEL_HEAD)]}


def geo_ok(g, cls, want_label):
    """(ok, why) for one machine's geometry: its top is cls; its list height is SHARED_LIST_H[cls] (D243); with
    want_label a VISIBLE label whose text == want_label lies between the list's bottom and the Cancel button's top;
    without, no label is visible."""
    lst, cancel = g.get("list") or {}, (g.get("buttons") or {}).get(CANCEL) or {}
    if g.get("top") != cls or not isinstance(lst.get("h"), int):
        return False, f"top {g.get('top')!r} / list {lst} (want {cls} with its list)"
    if lst["h"] != SHARED_LIST_H[cls]:
        return False, (f"list height {lst['h']} ({lst.get('rows')} rows; want {SHARED_LIST_H[cls]}, vanilla "
                       f"{VANILLA_LIST_H[cls]}: D243)")
    shown = [t for t in g.get("labels") or [] if t.get("visible") is True]
    if not want_label:
        return (not shown), ("" if not shown else f"a label is visible {shown} (want none: nobody else on the screen)")
    hit = [t for t in shown if t.get("text") == want_label]
    if not hit:
        return False, f"no visible label {want_label!r} (labels {g.get('labels')})"
    t, bottom = hit[0], lst["y"] + lst["h"]
    if not (isinstance(cancel.get("y"), int) and t["y"] >= bottom and t["y"] + t["h"] <= cancel["y"]):
        return False, (f"label rect y {t['y']}..{t['y'] + t['h']} not between the list's bottom {bottom} and the "
                       f"{CANCEL} button's top {cancel.get('y')} (D243)")
    return True, ""


def geo_cell(machines, cls, ctx, key, names=None, timeout=SEL_S):
    """Every machine in `machines` passes geo_ok within timeout: with names, each shows the label naming the other
    seat (host = seat 0); without, none shows a label."""
    last = {}

    def all_ok():
        out = True
        for gc in machines:
            g = geometry(gc)
            want = label_text(names, 0 if gc.name == "host" else 1) if names else None
            ok, why = geo_ok(g, cls, want)
            last[gc.name] = {"ok": ok, "why": why, "geo": g}
            out = out and ok
        return out, dict(last)
    ok, got, secs = poll(all_ok, timeout)
    ctx[key] = {"ok": ok, "secs": secs, "seen": got}
    return [] if ok else [f"{gc.name}: {got[gc.name]['why']} {timeout}s on" for gc in machines if not got[gc.name]["ok"]]


def view(gc):
    """One machine's end-of-row state for the EVIDENCE line."""
    r = rows(gc)
    return {"stack": stack(gc), "sel": sel_all(gc), "shared": sstats(gc),
            "screen": {"state": r.get("state"), "amounts": {k: v for k, v in amounts(r, r.get("state") == MACS).items()
                                                            if v},
                       "labels": label_items(r), "highlightColor": r.get("highlightColor"),
                       "secondaryColor": r.get("secondaryColor")}}


def evidence(rid, obj):
    camp.evidence(rid, obj)


def capture(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's stack, sel_state, top screen rows (whole), base 0 and 1 stock, roster,
    shared stats, the dialog, then raise."""
    cap = {}
    for gc in machines:
        try:
            bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
            cap[gc.name] = {"stack": stack(gc), "sel": sel_all(gc), "screen": rows(gc),
                            "bases": [{"name": b.get("name"), "items": b.get("items"), "facilities": b.get("facilities"),
                                       "transfers": b.get("transfers")} for b in bases[:2]],
                            "funds": funds(gc), "roster0": roster(gc), "shared": sstats(gc), "dialog": dialog(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


# ===================== fixtures =====================


def hygiene(host, client, ctx):
    """Holds off; boxes dismissed (ErrorMessageState / CoopState only, F4333); every base screen cancelled with its
    real Cancel - both machines back on GeoscapeState (a miss is a FIXTURE-STOP)."""
    m = (host, client)
    h = {"holds": {gc.name: hold(gc, False) for gc in m}, "dismissed": [], "cancelled": []}
    t0 = time.time()
    while time.time() - t0 < SCREEN_S:
        busy = False
        for gc in m:
            t = top(gc)
            if t in ("ErrorMessageState", "CoopState"):
                h["dismissed"].append(f"{gc.name}:{fst.dismiss_box(gc)}")
                busy = True
            elif t in SCREENS:
                h["cancelled"].append(f"{gc.name}:{t}:{click(gc, CANCEL)}")
                wait_until(lambda gc=gc, t=t: top(gc) != t, PAGE_S)
                busy = True
        if not busy and time.time() - t0 > 0.6:
            break
        time.sleep(0.2)
    h["stacks"] = {gc.name: stack(gc) for gc in m}
    ctx["hygiene"] = h
    if not all(top(gc) == "GeoscapeState" for gc in m):
        capture("row hygiene", f"not both on GeoscapeState after the hygiene (stacks {h['stacks']})", m)


def give(host, client, item, count, ctx, key):
    """give_items {item, count} on both, client first (F607); equal `stored` or a FIXTURE-STOP."""
    g = {}
    for gc in (client, host):
        r = gc.cmd({"cmd": "give_items", "item": item, "count": count})
        g[gc.name] = {k: r.get(k) for k in ("ok", "stored", "error")}
    ctx[key] = g
    if not (g["host"].get("ok") and g["client"].get("ok") and g["host"].get("stored") == g["client"].get("stored")):
        capture(f"give_items {item}", f"answered {g}", (host, client))


def set_funds_both(host, client, value):
    out = {}
    for gc in (client, host):   # client first (test_shared_purchase AC1c's pattern)
        r = gc.cmd({"cmd": "set_funds", "value": value})
        out[gc.name] = {k: r.get(k) for k in ("ok", "funds", "error")}
    return out


def open_xfer(host, client, ctx):
    """Both machines (host first): screen_push {transfer_base, base 0}, then screen_pick_base {0, 1}; both
    TransferItemsStates ready (a miss is a FIXTURE-STOP)."""
    m = (host, client)
    o = {}
    for gc in m:
        r = gc.cmd({"cmd": "screen_push", "screen": "transfer_base", "base": 0})
        ok, secs = wait_until(lambda gc=gc: top(gc) == "TransferBaseState", PAGE_S)
        time.sleep(0.2)   # one pump: TransferBaseState's own init() runs first (F5573)
        p = gc.cmd({"cmd": "screen_pick_base", "from": 0, "to": 1})
        o[gc.name] = {"push": {k: r.get(k) for k in ("ok", "screen", "base", "error")}, "baseUp": ok, "secs": secs,
                      "pick": {k: p.get(k) for k in ("ok", "from", "to", "debrief", "error")}}
    ok, secs = wait_until(lambda: screen_ready(host, "TransferItemsState") and screen_ready(client, "TransferItemsState"),
                          PAGE_S)
    ctx["openXfer"] = {"resp": o, "ready": ok, "secs": secs}
    if not ok or any(v["pick"].get("debrief") is not False for v in o.values()):
        capture("open the Transfer screens", f"both TransferItemsStates (normal, base 0 -> 1) not ready within {PAGE_S}s "
                f"({o}; stacks {[stack(gc) for gc in m]})", m)


def open_cont(host, client, ctx):
    """Both machines (host first): screen_push {containment, base 0, prisonType 0}; both screens ready."""
    m = (host, client)
    o = {}
    for gc in m:
        r = gc.cmd({"cmd": "screen_push", "screen": "containment", "base": 0, "prisonType": 0})
        o[gc.name] = {k: r.get(k) for k in ("ok", "screen", "base", "prisonType", "error")}
    ok, secs = wait_until(lambda: screen_ready(host, MACS) and screen_ready(client, MACS), PAGE_S)
    ctx["openCont"] = {"resp": o, "ready": ok, "secs": secs}
    if not ok:
        capture("open the containment screens", f"both {MACS}s not ready within {PAGE_S}s ({o}; stacks "
                f"{[stack(gc) for gc in m]})", m)


def xfer_pre(js, ctx):
    """XFER pre-cell: SEL's soldier off its craft, FX-B's second base with stores, the roster names, the boot funds."""
    e1.sel_pre(js, ctx)
    p3.fx_b(js, ctx)
    ctx["names"] = roster_names(js.host)
    ctx["funds0"] = {gc.name: funds(gc) for gc in (js.host, js.client)}
    if len(ctx["names"]) != 2 or ctx["funds0"]["host"] != ctx["funds0"]["client"]:
        capture("XFER names / funds", f"coopPlayers {ctx['names']} (want 2 names), funds {ctx['funds0']} (want equal)",
                (js.host, js.client))


def cont_pre(js, ctx):
    """CONT pre-cell: SEL's soldier off its craft, then FX-CT's geoscape half: the containment facility at (0, 3) built
    and complete on both, L x L_FILL on both (client first), the roster names."""
    host, client = js.host, js.client
    m = (host, client)
    e1.sel_pre(js, ctx)
    fb = host.cmd({"cmd": "fac_build", "facility": CONTAINMENT, "x": CT_X, "y": CT_Y})
    ok, secs = wait_until(lambda: fct.facility_index(host) is not None and fct.facility_index(client) is not None,
                          BASES_S, 0.5)
    idx = {gc.name: fct.facility_index(gc) for gc in m}
    ctx["cont"] = {"facBuild": {k: fb.get(k) for k in ("ok", "error")}, "index": idx, "secs": secs}
    if not (fb.get("ok") and ok and idx["host"] == idx["client"] == CT_INDEX):
        capture("CONT facility", f"fac_build {ctx['cont']['facBuild']}, index {idx} (want {CT_INDEX} on both)", m)
    sets = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": CT_INDEX, "time": 0})
        sets[gc.name] = {k: r.get(k) for k in ("ok", "type", "buildTime", "error")}
    ctx["cont"]["buildTime0"] = sets
    if not all(s.get("ok") and s.get("type") == CONTAINMENT and s.get("buildTime") == 0 for s in sets.values()):
        capture("CONT buildTime", f"set_facility_build_time answered {sets}", m)
    give(host, client, L, L_FILL, ctx["cont"], "give")
    ctx["names"] = roster_names(host)
    if len(ctx["names"]) != 2:
        capture("CONT names", f"coopPlayers {ctx['names']} (want 2 names)", m)


def restore_funds(host, client, ctx, boot):
    """The boot's funds on both (client first) when either machine's moved (E2-xr sets them to 0)."""
    f0 = boot["funds0"]["host"]
    now = {gc.name: funds(gc) for gc in (host, client)}
    if any(v != f0 for v in now.values()):
        ctx.setdefault("fundsRestored", []).append({"was": now, "set": set_funds_both(host, client, f0)})


def xfer_start(host, client, ctx, boot):
    """XFER row start: hygiene, the boot's funds restored on both (client first) when they moved, STR_RIFLE restaged
    on both (client first), both Transfer screens open."""
    hygiene(host, client, ctx)
    restore_funds(host, client, ctx, boot)
    give(host, client, RIFLE, XFER_STAGE, ctx, "give")
    open_xfer(host, client, ctx)
    ctx["stock0"] = {gc.name: {RIFLE: stock(gc, RIFLE)} for gc in (host, client)}


def stage_quarters(host, client, ctx):
    """E2-xe: STR_LIVING_QUARTERS at Second Base (QUARTERS_X, QUARTERS_Y) built on both, buildTime 0 on both."""
    m = (host, client)

    def q_index(gc):
        bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
        facs = (bases[1].get("facilities") or []) if len(bases) > 1 else []
        hits = [i for i, f in enumerate(facs) if f.get("type") == QUARTERS and f.get("x") == QUARTERS_X
                and f.get("y") == QUARTERS_Y]
        return hits[0] if hits else None
    fb = host.cmd({"cmd": "fac_build", "facility": QUARTERS, "base": SECOND_BASE, "x": QUARTERS_X, "y": QUARTERS_Y})
    ok, secs = wait_until(lambda: q_index(host) is not None and q_index(client) is not None, BASES_S, 0.5)
    idx = {gc.name: q_index(gc) for gc in m}
    ctx["quarters"] = {"facBuild": {k: fb.get(k) for k in ("ok", "error")}, "index": idx, "secs": secs}
    if not (fb.get("ok") and ok and idx["host"] == idx["client"]):
        capture("E2-xe quarters", f"fac_build {ctx['quarters']['facBuild']}, index {idx} after {BASES_S}s (want "
                f"equal on both)", m)
    sets = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "set_facility_build_time", "baseId": 1, "index": idx["host"], "time": 0})
        sets[gc.name] = {k: r.get(k) for k in ("ok", "type", "buildTime", "error")}
    ctx["quarters"]["buildTime0"] = sets
    if not all(s.get("ok") and s.get("type") == QUARTERS and s.get("buildTime") == 0 for s in sets.values()):
        capture("E2-xe quarters buildTime", f"set_facility_build_time answered {sets}", m)
    q = {}
    for gc in m:
        r = gc.cmd({"cmd": "base_report", "base": SECOND_BASE})
        q[gc.name] = {k: r.get(k) for k in ("availableQuarters", "usedQuarters", "ok")}
    ctx["quarters"]["report"] = q


# ===================== cell helpers =====================


def set_ok(gc, value, ctx, key, item=None, row=None):
    return e1.set_ok(gc, value, ctx, key, item=item, row=row)


def cross(gc, item, want, ctx, key, timeout=SEL_S, mac=False):
    ok, got, secs = poll(lambda: (lambda a: (a == want, a))(amount(gc, item, mac)), timeout)
    ctx[key] = {"want": want, "got": got, "ok": ok, "secs": secs}
    return [] if ok else [f"{gc.name}'s {item} amount {got} {timeout}s after the other machine's edit (want {want})"]


def gone(gc, ctx, key, classes, timeout=PAGE_S):
    """Every class in `classes` leaves gc's stack within timeout."""
    ok, secs = wait_until(lambda: not any(c in stack(gc) for c in classes), timeout, 0.1)
    ctx[key] = {"ok": ok, "secs": secs, "stack": stack(gc)}
    return [] if ok else [f"{gc.name}'s {classes} still on its stack {timeout}s later (stack {stack(gc)})"]


def stays_rebuilt(gc, cls, item, total, ctx, key, mac=False, timeout=SCREEN_S):
    """gc's top stays cls while the world changes and the list is rebuilt: item's remaining + amount == total (the new
    stock). Returns the failures; ctx[key] holds the tops seen and the rebuilt row."""
    tops = []

    def rebuilt():
        t = top(gc)
        if t not in tops:
            tops.append(t)
        if t != cls:
            return False, None
        rem, amt = row_of(rows(gc), item, mac)
        return (rem is not None and amt is not None and rem + amt == total), (rem, amt)
    ok, last, secs = poll(rebuilt, timeout)
    ctx[key] = {"ok": ok, "tops": tops, "row": last, "secs": secs}
    f = [] if ok else [f"{gc.name}'s {cls} not rebuilt with {item} total {total} within {timeout}s (row {last}, tops "
                       f"{tops})"]
    if tops != [cls]:
        f.append(f"{gc.name}'s top left {cls} while the world changed (tops {tops}; want it rebuilt, not popped)")
    return f


def zeros(gc, ctx, key, mac=False, timeout=SEL_S):
    ok, a, secs = poll(lambda: (lambda r: (all_zero(r, mac), {k: v for k, v in amounts(r, mac).items() if v}))(rows(gc)),
                       timeout)
    ctx[key] = {"ok": ok, "nonZero": a, "secs": secs}
    return [] if ok else [f"{gc.name}'s amounts {a} {timeout}s on (want every amount 0, D204)"]


def chk_plus_one(host, client, x0, ctx, key):
    x1 = {}

    def plus_one():
        for gc in (host, client):
            x1[gc.name] = transfers_chk(gc)
        return all(isinstance(x0[n], int) and x1[n] == x0[n] + 1 for n in x0)
    ok, secs = wait_until(plus_one, EQUAL_S)
    ctx[key] = {"before": x0, "after": dict(x1), "ok": ok, "secs": secs}
    return [] if ok else [f"shared_checksum chkTransfers {x0} -> {x1} (want +1 on both)"]


def no_box(host, client, ctx, key):
    return e1.no_box(host, client, ctx, key)


def world_same(host, client, ctx, key):
    return p3.world_same(host, client, ctx, key)


def soldier_row(r, name):
    return e1.soldier_row(r, name)


def soldier_of(ctx):
    return ctx["pre"]["soldier"] if "soldier" in ctx.get("pre", {}) else ctx["boot"]["soldier"]


def boot_of(ctx):
    return ctx["pre"] if "names" in ctx.get("pre", {}) else ctx["boot"]


# ===================== XFER rows =====================


def e2_xa_cells(host, client, ctx):
    names = boot_of(ctx)["names"]

    def c1():
        xfer_start(host, client, ctx, boot_of(ctx))
        return set_ok(client, E2XA_CLIENT, ctx, "c1set", item=RIFLE) or cross(host, RIFLE, E2XA_CLIENT, ctx, "c1host")

    def c2():
        f = set_ok(host, E2XA_HOST, ctx, "c2set", item=RIFLE) or cross(client, RIFLE, E2XA_HOST, ctx, "c2client")
        return f or labels_cell(host, client, names, ctx, "c2labels")
    return [
        ("1 the client's Rifle edit reaches the host's Transfer screen", c1),
        ("2 the host's Rifle edit reaches the client's; both screens name the other player", c2),
    ]


def e2_xr_cells(host, client, ctx):
    boot = boot_of(ctx)

    def c1():
        xfer_start(host, client, ctx, boot)
        f = set_ok(client, E2XR_SET, ctx, "c1set", item=RIFLE)
        if f:
            return f
        want = {f"i:{RIFLE}": E2XR_SET}
        seen, s0, secs = poll(lambda: (lambda h, c: (isinstance(h, dict) and isinstance(c, dict) and h.get("rows") == want
                                                     and c.get("rows") == want, {"host": h, "client": c}))(
            sel(host, XFER_KEY), sel(client, XFER_KEY)), SEL_S)
        ctx["c1before"] = {"seen": seen, "sel": s0, "secs": secs}   # EVIDENCE only: the rev the confirm must not move
        ctx["c1funds0"] = set_funds_both(host, client, E2XR_FUNDS)
        f = p3.open_screen(client, XFER_OK, "TransferConfirmState", ctx, "c1confirm")
        if f:
            return f
        ctx["c1ok"] = click(client, CONFIRM_OK)
        ok, secs = wait_until(lambda: top(client) == "CoopState" and stack(client)[-2:-1] == ["TransferItemsState"]
                              and dialog(client).get("code") == SHARED_FAIL, PAGE_S, 0.1)
        ctx["c1box"] = {"ok": ok, "secs": secs, "stack": stack(client), "dialog": dialog(client),
                        "shared": sstats(client)}
        if not ok:
            return [f"the client's stack {stack(client)} / dialog {dialog(client)} {PAGE_S}s after its rejected Transfer "
                    f"(want CoopState {SHARED_FAIL} directly over its TransferItemsState, MR10)"]
        after = {gc.name: sel(gc, XFER_KEY) for gc in (host, client)}
        ctx["c1after"] = after
        if not all(isinstance(v, dict) for v in after.values()):
            return [f"sel_state lacks the key {XFER_KEY} (host, client) {after} after the rejected Transfer (want rows "
                    f"{want}, the rev unchanged, on both)"]
        f = []
        for n, v in after.items():
            rev0 = ((s0 or {}).get(n) or {}).get("rev")
            if v.get("rows") != want or rev0 is None or v.get("rev") != rev0:
                f.append(f"{n}'s sel_state {XFER_KEY} {v} (want rows {want}, rev {rev0} unchanged by the rejected "
                         f"confirm)")
        return f

    def c2():
        ctx["c2back"] = fst.dismiss_box(client) if top(client) == "CoopState" else None
        ctx["c2funds"] = set_funds_both(host, client, boot["funds0"]["host"])
        x0 = {gc.name: transfers_chk(gc) for gc in (host, client)}
        s0 = ctx["stock0"]["host"][RIFLE]
        f = p3.open_screen(client, XFER_OK, "TransferConfirmState", ctx, "c2confirm")
        if f:
            return f
        ctx["c2ok"] = click(client, CONFIRM_OK)
        f = gone(client, ctx, "c2gone", ("TransferItemsState", "TransferBaseState", "TransferConfirmState"))
        if f:
            return f
        f = stays_rebuilt(host, "TransferItemsState", RIFLE, s0 - E2XR_SET, ctx, "c2hostRebuilt")
        if f:
            return f
        f = zeros(host, ctx, "c2hostZeros")
        if f:
            return f
        return chk_plus_one(host, client, x0, ctx, "c2chk") + world_same(host, client, ctx, "c2world")
    return [
        ("1 a rejected Transfer keeps the client's screen and the shared list (MR10)", c1),
        ("2 the retried Transfer applies; the host's screen rebuilt at zero (D204)", c2),
    ]


def e2_xe_cells(host, client, ctx):
    sold = soldier_of(ctx)

    def c1():
        hygiene(host, client, ctx)
        restore_funds(host, client, ctx, boot_of(ctx))
        stage_quarters(host, client, ctx)
        xfer_start(host, client, ctx, boot_of(ctx))
        idx = soldier_row(rows(client), sold["name"])
        ctx["c1soldierRow"] = idx
        if idx is None:
            return [f"the client's TransferItemsState lists no row for its soldier {sold['name']!r} (id {sold['id']})"]
        f = set_ok(client, 1, ctx, "c1s", row=idx)
        if f:
            return f
        hidx = soldier_row(rows(host), sold["name"])
        ctx["c1hostRow"] = hidx
        if hidx is not None:
            return [f"the host's TransferItemsState lists the client's soldier {sold['name']!r} (row {hidx}; want none, "
                    f"MR7)"]
        want = {f"s:{sold['id']}": 1}
        ok, got, secs = poll(lambda: (lambda r: (r == want, r))(sel_rows(host, XFER_KEY)), SEL_S)
        ctx["c1hostSel"] = {"ok": ok, "rows": got, "secs": secs}
        return [] if ok else [f"the host's sel_state {XFER_KEY} rows {got} (want {want})"]

    def c2():
        x0 = {gc.name: transfers_chk(gc) for gc in (host, client)}
        f = p3.open_screen(host, XFER_OK, "TransferConfirmState", ctx, "c2confirm")
        if f:
            return f
        ctx["c2ok"] = click(host, CONFIRM_OK)
        f = gone(host, ctx, "c2hostGone", ("TransferItemsState", "TransferBaseState", "TransferConfirmState"))
        if f:
            return f
        ok, v, secs = poll(lambda: (lambda h, c: (not h and not c, {"host": h, "client": c}))(
            [s.get("id") for s in roster(host) if s.get("id") == sold["id"]],
            [s.get("id") for s in roster(client) if s.get("id") == sold["id"]]), EQUAL_S)
        ctx["c2soldier"] = {"ok": ok, "inBase0": v, "secs": secs}
        if not ok:
            return [f"soldier {sold['id']} still in base 0 {v} {EQUAL_S}s after the host's Transfer (want in transit on "
                    f"both: the host's confirm applies the shared list although the host sees none of its rows, F6341, "
                    f"V-E3)"]
        f = chk_plus_one(host, client, x0, ctx, "c2chk")
        if f:
            return f
        ok, secs = wait_until(lambda: screen_ready(client, "TransferItemsState"), SCREEN_S)
        ctx["c2clientTop"] = {"ok": ok, "secs": secs, "stack": stack(client)}
        if not ok:
            return [f"the client's top {top(client)!r} after the host's Transfer (want its TransferItemsState, rebuilt)"]
        return zeros(client, ctx, "c2clientZeros") + no_box(host, client, ctx, "c2stacks")
    return [
        ("1 only the client's own soldier row is on the shared list; the host's list hides it (MR7)", c1),
        ("2 the host's Transfer applies the list it cannot see (F6341, V-E3)", c2),
    ]


def open_one(gc, screen, ctx, key):
    """ONE machine opens the real screen: "xfer" = screen_push {transfer_base, base 0} + screen_pick_base {0, 1};
    "cont" = screen_push {containment, base 0, prisonType 0}; ready or a FIXTURE-STOP."""
    cls = "TransferItemsState" if screen == "xfer" else MACS
    if screen == "xfer":
        r = gc.cmd({"cmd": "screen_push", "screen": "transfer_base", "base": 0})
        wait_until(lambda: top(gc) == "TransferBaseState", PAGE_S)
        time.sleep(0.2)   # one pump: TransferBaseState's own init() runs first (F5573)
        p = gc.cmd({"cmd": "screen_pick_base", "from": 0, "to": 1})
        resp = {"push": {k: r.get(k) for k in ("ok", "error")}, "pick": {k: p.get(k) for k in ("ok", "debrief", "error")}}
    else:
        r = gc.cmd({"cmd": "screen_push", "screen": "containment", "base": 0, "prisonType": 0})
        resp = {k: r.get(k) for k in ("ok", "error")}
    ok, secs = wait_until(lambda: screen_ready(gc, cls), PAGE_S)
    ctx[key] = {"resp": resp, "ready": ok, "secs": secs}
    if not ok:
        capture(f"open the {cls} ({gc.name})", f"not ready within {PAGE_S}s ({resp}; stack {stack(gc)})", (gc,))


def e2_gx_cells(host, client, ctx):
    """D243 on Transfer: the SHARED list is one row shorter with or without the other player; the label sits between
    the list and the buttons while both are on the screen."""
    names = boot_of(ctx)["names"]

    def c1():
        hygiene(host, client, ctx)
        restore_funds(host, client, ctx, boot_of(ctx))
        open_one(host, "xfer", ctx, "c1open")
        return geo_cell((host,), "TransferItemsState", ctx, "c1geo")

    def c2():
        open_one(client, "xfer", ctx, "c2open")
        return geo_cell((host, client), "TransferItemsState", ctx, "c2geo", names=names)

    def c3():
        ctx["c3cancel"] = click(host, CANCEL)
        f = gone(host, ctx, "c3hostGone", ("TransferItemsState",))
        return f or geo_cell((client,), "TransferItemsState", ctx, "c3geo")
    return [
        ("1 the host alone: its Transfer list is one row shorter, no label (D243)", c1),
        ("2 the client joins: both lists one row shorter, each label between the list and the buttons", c2),
        ("3 the host leaves: the client's list stays one row shorter, its label hidden", c3),
    ]


# ===================== CONT row =====================


def e2_ca_cells(host, client, ctx):
    names = boot_of(ctx)["names"]

    def c1():
        hygiene(host, client, ctx)
        open_cont(host, client, ctx)
        ctx["stock0"] = {gc.name: {L: stock(gc, L), CORPSE: stock(gc, CORPSE)} for gc in (host, client)}
        f = set_ok(client, E2CA_SET, ctx, "c1set", item=L) or cross(host, L, E2CA_SET, ctx, "c1host", mac=True)
        return f or labels_cell(host, client, names, ctx, "c1labels")

    def c2():
        ctx["c2click"] = click(host, CONT_OK)
        f = gone(host, ctx, "c2hostGone", (MACS,))
        if f:
            return f
        f = stays_rebuilt(client, MACS, L, ctx["stock0"]["client"][L] - E2CA_SET, ctx, "c2clientRebuilt", mac=True)
        if f:
            return f
        f = zeros(client, ctx, "c2clientZeros", mac=True)
        if f:
            return f
        s0 = ctx["stock0"]
        want = {gc.name: {L: s0[gc.name][L] - E2CA_SET, CORPSE: s0[gc.name][CORPSE] + E2CA_SET} for gc in (host, client)}
        ok, got, secs = poll(lambda: (lambda v: (v == want, v))({gc.name: {L: stock(gc, L), CORPSE: stock(gc, CORPSE)}
                                                                 for gc in (host, client)}), EQUAL_S)
        ctx["c2stock"] = {"ok": ok, "stock": got, "want": want, "secs": secs}
        if not ok:
            return [f"stock {got} (want {want}: {E2CA_SET} {L} removed, {E2CA_SET} {CORPSE} added on both)"]
        return world_same(host, client, ctx, "c2world")
    return [
        ("1 the client's removal amount reaches the host's containment screen; both name the other player", c1),
        ("2 the host's Remove Selected applies; the client's screen rebuilt in place at zero", c2),
    ]


def e2_gc_cells(host, client, ctx):
    """D243 on Alien Containment: the list keeps its vanilla height; the label sits in the gap above the buttons."""
    names = boot_of(ctx)["names"]

    def c1():
        hygiene(host, client, ctx)
        open_one(host, "cont", ctx, "c1open")
        return geo_cell((host,), MACS, ctx, "c1geo")

    def c2():
        open_one(client, "cont", ctx, "c2open")
        return geo_cell((host, client), MACS, ctx, "c2geo", names=names)
    return [
        ("1 the host alone: its containment list keeps its vanilla height, no label (D243)", c1),
        ("2 the client joins: both lists unchanged, each label in the gap above the buttons", c2),
    ]


# ===================== one boot =====================


def run_cells(cells):
    """The row's cells in order -> (verdict (None = pass), cell records). A fixture miss is a FIXTURE-STOP."""
    out = []
    for i, (name, fn) in enumerate(cells):
        try:
            f = fn()
        except MISSES as e:
            out.append({"cell": name, "pass": False, "fixtureStop": str(e)})
            return f"FIXTURE-STOP in cell {name}: {e}", out
        except Exception as e:
            f = [f"{type(e).__name__}: {short(e, 600)}"]
        out.append({"cell": name, "pass": not f, "fails": f})
        if f:
            rest = [c[0].split(" ")[0] for c in cells[i + 1:]]
            return f"cell {name}: " + "; ".join(f) + (f" | cells {rest} not reached" if rest else ""), out
    return None, out


def guard(host, client, crash0, ctx, last, battle=False):
    return e1.guard(host, client, crash0, ctx, last, battle)


def run_boot(boot, tag, port, up_fn, pre_fn, rows_spec, battle, results, walls, prefix="w2p7-sce2"):
    """One boot: bring-up + pre_fn(js, pre) (pre-cell), then each row (EVIDENCE, PASS / FAIL)."""
    t0, js, pre = time.time(), None, {}
    crash0 = session._crash_log_snapshot()
    miss = None
    try:
        try:
            js = up_fn(tag, port)
            pre_fn(js, pre)
        except Exception as e:
            miss = f"pre-cell (FIXTURE-STOP) {e if isinstance(e, MISSES) else short(e, 800)}"
        for n, (rid, cells_fn) in enumerate(rows_spec):
            tr = time.time()
            ctx = {"row": rid, "boot": pre if n > 0 else {}, "pre": pre if n == 0 else {"see": rows_spec[0][0]}}
            verdict = miss
            if verdict is None:
                verdict, ctx["cells"] = run_cells(cells_fn(js.host, js.client, ctx))
                g = guard(js.host, js.client, crash0, ctx, n == len(rows_spec) - 1, battle)
                if g:
                    verdict = (verdict + " | " if verdict else "") + "guard: " + "; ".join(g)
            if js is not None:
                try:
                    ctx["end"] = {"host": view(js.host), "client": view(js.client)}
                except Exception as e:
                    ctx["end"] = f"probe failed: {short(e)}"
            ctx.pop("boot", None)
            ctx["wall"] = round(time.time() - tr, 1)
            evidence(rid, ctx)
            results[rid] = verdict is None
            print(f"PASS {rid}" if verdict is None else f"FAIL {rid}: {verdict}", flush=True)
    finally:
        if js is not None:
            for gc in (js.host, js.client):   # every TEST-ONLY hold off before the shutdown (inert unless armed)
                try:
                    gc.cmd({"cmd": "shared_update_defer", "on": False})
                except Exception as e:
                    print(f"[{prefix}] release shared_update_defer: {short(e)}", flush=True)
            try:
                js.shutdown()
            except Exception as e:
                print(f"[{prefix}] shutdown: {short(e)}", flush=True)
        walls[boot] = round(time.time() - t0, 1)


def bring_up_sel(tag, port):
    return shared_fixture.bring_up(tag, (0, 0, port))


BOOTS = (("XFER", "w2p7sce2_xfer", bring_up_sel, xfer_pre,
          (("E2-xa", e2_xa_cells), ("E2-xr", e2_xr_cells), ("E2-xe", e2_xe_cells), ("E2-gx", e2_gx_cells)), False),
         ("CONT", "w2p7sce2_cont", bring_up_sel, cont_pre, (("E2-ca", e2_ca_cells), ("E2-gc", e2_gc_cells)), False))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, up_fn, pre_fn, rows_spec, battle in BOOTS:
        run_boot(boot, tag, BOOT_PORT[boot], up_fn, pre_fn, rows_spec, battle, results, walls)
    order = [rid for _, _, _, _, rs, _ in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_selection_screens: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
