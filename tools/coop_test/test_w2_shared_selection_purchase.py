"""W2-P7 S-C-E3 - test_w2_shared_selection_purchase.py: in a SHARED campaign the Purchase/Hire screen joins the shared
selection the Sell, Transfer and Alien Containment screens use since S-C-E1 / S-C-E2 (owner D242 (b), D184 (a), D203,
D204 (a), D243; MR8, MR10): two players on the Purchase screen of the same base edit ONE list of pending amounts, the
label naming the other player sits above OK/Cancel and the rows the other player changed last are drawn in the
screen's highlight colour, whoever confirms buys the list as the host holds it (a confirm racing an edit is let
through), a second confirm of the same list counts as done, a refused purchase keeps the screen and the list, another
player's purchase no longer wipes an order being built, and the Purchase screen opened from "not enough equipment to
re-equip" shares its own list whose purchase lowers the missing counts on both machines (docs
rewrite/prompts/w2p7_sc_design.md AMENDMENT P7-9: PR-54..PR-63; Q-P9-1..Q-P9-3 (a)).

Before S-C-E3 (P7-9 F6619, F6623, F6626, F6628): each machine's Purchase screen keeps its own amounts - the other
player never sees them, the store (sel_state) holds no buy key, a confirm sends the confirmer's own list and closes
the screen before the host answers, a rebuild after any world change resets every amount to 0, and the SHARED
reequip Purchase never lowers the missing counts.

Fixtures (AMENDMENT P7-9 section 4; a pre-cell failure is a FIXTURE-STOP: one CAPTURE line, every row of the boot
FAILs "pre-cell"):
  BUY = shared_fixture.bring_up(tag, (0, 0, "47321")), geoscape only; X = STR_RIFLE ($3,000), Y = STR_PISTOL ($800),
        S = STR_SOLDIER ($40,000) (xcom1 items.rul / soldiers.rul costBuy). Pre-cell: both machines' funds equal
        (funds0), base 0's base_report free quarters (availableQuarters - usedQuarters) >= 2 on both, the roster
        names (save_markers.coopPlayers, seat 0 = the host). Each row turns every hold off, dismisses any box
        (ErrorMessageState / CoopState only, F4333), cancels every Purchase screen with its real Cancel (both back on
        GeoscapeState), restores funds0 on both (client first) when they moved, then opens open_screen {screen:
        "purchase"} on both (host first; the REAL screen, its init() binds it, key buy|n|0|) and waits one pump after
        its rows show (a Purchase list is built in the constructor, so screen_rows.screen does not prove init() ran).
        No row reads base stock: a purchase adds transfers, so rows assert incoming_transfers deltas (no give_items).
  REQ = shared_fixture.bring_up(tag, (0, 0, "47322")); pre-cell: screen_push {screen: "cannot_reequip", base: 0,
        missing: [{STR_RIFLE, 3, "SKYRANGER-1"}, {STR_PISTOL, 2, "SKYRANGER-1"}]} on both (client first; vanilla's
        own push, CraftEquipmentState :1230), both tops CannotReequipState with equal followup_state rows; key
        buy|r|0| (its Purchase opens from click_widget PURCHASE/RECRUIT).
  Probes / levers: screen_rows / screen_set_amount on a top PurchaseState (PR-63 (i): columns name, cost, stock,
  amount - read here with the test-local prow_of; textItems, rows[i].color, secondaryColor, highlightColor from
  "buyMenu"), screen_state.funds (the constructor-time funds text: a change proves a rebuild), sel_state (PR-46),
  incoming_transfers (+ soldierOwners, scientists, engineers, PR-63 (iii)), screen_push {cannot_reequip} (PR-63
  (ii)), followup_state, list_widgets (E2.1b's geometry), set_funds (both, client first), the host's `buy` lever
  (unbound: never opens a selection, applied as sent, PR-56 (iv), P9-6), shared_update_defer {on} (a "hold",
  released within HOLD_MAX_S of the other machine's world change, F4529 / F5840), click_widget on the real captions
  (OK, Cancel, PURCHASE/RECRUIT, F6641), coop_dialog_back ONLY on a CoopState top, dismiss_popup ONLY on an
  ErrorMessageState top (F4333).

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot BUY (port 47321): P-a, P-k, P-l, P-e, P-c, P-d, P-r, P-h.
  P-a (D184) (1) client X = 3 -> the host's X amount 3 within SEL_S.
      (2) host Y = 2 -> the client's Y amount 2 within SEL_S.
      (3) sel_state buy|n|0| on both: rows {i:STR_RIFLE: 3, i:STR_PISTOL: 2}, equal rev, viewers [0, 1]; both
          screens' "Cost of Purchases" texts equal.
  P-k (D203, V-P5) (1) client X = 2: on the host X's color == highlightColor within SEL_S; on the client X's color
          == secondaryColor.
      (2) host Y = 1: on the client Y's color == highlightColor within SEL_S.
      (3) host OK: its PurchaseState gone within PAGE_S; the client's top stays PurchaseState, rebuilt
          (screen_state.funds changed), no row in highlightColor, every amount 0, the label hidden within SCREEN_S.
  P-l (D243 by analogy, V-P4; list_widgets on the top state)
      (1) both screens show a VISIBLE label "Also on this screen: <the other's roster name>" whose rect lies between
          the list's bottom and the Cancel button's top, within SEL_S.
      (2) on both the list is exactly one text row shorter than vanilla's 120-px list (PURCHASE_LIST_H - ROW_H).
      (3) client Cancel: the host's label hidden within SEL_S, its list height unchanged.
  P-e (F2161, V-P6) (1) client X = 3, Y = 2 (local check only).
      (2) the host's `buy {STR_GRENADE, 1}` (the lever): the client's top stays PurchaseState, rebuilt (screen_state.
          funds changed), its X 3 and Y 2 survive.
      (3) the host's X 3 and Y 2.
  P-c (D203) (1) client X = 1, then a wait of up to SEL_S for the host's sel_state to show it (EVIDENCE only, never a
          failed cell); host hold on; host X = 5; client OK.
      (2) host hold off: within PAGE_S the client's PurchaseState gone, no CoopState on either;
          incoming_transfers.items[STR_RIFLE] == before + 5 on both (D203: the host applies its current list); the
          host's top PurchaseState rebuilt (funds changed), every amount 0 (D204).
  P-d (MR8) (1) client X = 2; host screen_set_amount {X, 2} (no change when shared); client hold on; host OK -> the
          host's PurchaseState gone within PAGE_S.
      (2) client OK; client hold off: within PAGE_S its PurchaseState gone, no CoopState on either, incoming X ==
          before + 2 on both (one purchase), the client's shared_stats.lastFail == coop_sel_dup.
  P-r (MR10, Q-P9-2 (a), V-P1) (1) client X = 4 (local); set_funds {1000} on both (client first); client OK: within
          PAGE_S the client's top CoopState (556) with PurchaseState directly under it; sel_state buy|n|0| rows
          {i:STR_RIFLE: 4}, rev unchanged by the refusal, on both.
      (2) coop_dialog_back; funds0 restored on both; client OK: within PAGE_S its PurchaseState gone; incoming X ==
          before + 4 on both; the host's PurchaseState rebuilt (funds changed), every amount 0.
  P-h (OWNER?-P9-1 = D254 (b)) (1) client S = 1, host X = 1 -> the host's S amount 1 within SEL_S; sel_state
          buy|n|0| rows {h:STR_SOLDIER: 1, i:STR_RIFLE: 1}, editors {h:STR_SOLDIER: 1, i:STR_RIFLE: 0} on both.
      (2) host OK: its PurchaseState gone within PAGE_S; incoming soldiers == before + 1 and X == before + 1 on both
          within EQUAL_S; the client's screen rebuilt (funds changed), every amount 0; the new soldierOwners entry ==
          HIRE_OWNER (1, the client who set the Soldier row) on both within EQUAL_S (D254 (b), S32 commit E3.1b).
  Boot REQ (port 47322): P-q.
  P-q (Q-P9-3 (a), V-P3) (1) client PURCHASE/RECRUIT: its top PurchaseState with X 3, Y 2 (vanilla's pre-fill) and
          the host's sel_state buy|r|0| rows {i:STR_RIFLE: 3, i:STR_PISTOL: 2} within SEL_S; client Y = 0.
      (2) host PURCHASE/RECRUIT: its X 3 and Y 0 (adopted, not its own pre-fill) within SEL_S; sel_state buy|r|0|
          viewers [0, 1] on both.
      (3) host OK: its PurchaseState gone, top CannotReequipState, followup_state rows [["Pistol", "2",
          "SKYRANGER-1"]] within PAGE_S; incoming X == before + 3 and Y unchanged on both; the client's amounts all
          0 within SEL_S.
      (4) client Cancel: its top CannotReequipState with the same rows.
Guard on every row: no new crash log; the client zero-disk at each boot's end.

RED (commit S-C-E3.1: the Purchase probe, the reequip lever, the hire owners; product untouched): P-a, P-h fail on
cell 1 (the host's amount stays 0), P-k on cell 1 (the host's X is not drawn in highlightColor), P-l on cell 1 (no
label), P-e on cell 2 (the client's rebuilt amounts are 0), P-c on cell 2 (X before + 1: the client's own list was
bought), P-d on cell 2 (X before + 4: two purchases), P-r on cell 1 (the client's screen closed before the refusal:
no PurchaseState under the box), P-q on cell 1 (the host's sel_state holds no buy|r|0| key). GREEN (commit
S-C-E3.2): every row passes.
Each row prints ONE "EVIDENCE <id>:" line (both machines' sel_state, screen and incoming transfers at the row's end),
then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every
row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_selection_purchase.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
import test_w2_shared_forced_storage as fst
import test_w2_shared_selection as e1
import test_w2_shared_selection_screens as scr
import test_w2_shared_selection_presence as pres

# ----- pins (AMENDMENT P7-9 section 4) -----
X, Y, S = "STR_RIFLE", "STR_PISTOL", "STR_SOLDIER"   # xcom1 costBuy 3000 / 800 / 40000 (items.rul, soldiers.rul)
GRENADE = "STR_GRENADE"                  # P-e's lever purchase (xcom1 costBuy 300)
BUY_KEY = "buy|n|0|"                     # SharedEcon::buyKey(base 0, normal) (P7-9 PR-54)
REQ_KEY = "buy|r|0|"                     # SharedEcon::buyKey(base 0, reequip) (P7-9 PR-54, PR-61)
BOOT_PORT = {"BUY": "47321", "REQ": "47322"}   # AMENDMENT P7-9 section 4 (S26, F6635)
OK, CANCEL = "OK", "Cancel"              # PurchaseState's captions (xcom1 en-US STR_OK / STR_CANCEL)
PURCHASE_RECRUIT = "PURCHASE/RECRUIT"    # CannotReequipState's button (xcom1 en-US STR_PURCHASE_RECRUIT, F6641)
P_C_CLIENT, P_C_HOST = 1, 5              # P7-9 section 4 P-c's amounts
P_R_SET, P_R_FUNDS = 4, 1000             # P7-9 section 4 P-r: 4 x $3,000 > $1,000
SEL_DUP = e1.SEL_DUP                     # "coop_sel_dup" (PR-45: a duplicate confirm, answered as a success)
SHARED_FAIL = scr.SHARED_FAIL            # 556 = CoopState COOP_DLG_SHARED_FAIL
MIN_FREE_QUARTERS = 2                    # BUY pre-cell (P-h hires one soldier)
REQ_CRAFT = "SKYRANGER-1"
REQ_MISSING = [{"item": X, "qty": 3, "craft": REQ_CRAFT}, {"item": Y, "qty": 2, "craft": REQ_CRAFT}]
REQ_AFTER = [["Pistol", "2", REQ_CRAFT]]   # P-q (3): the rifles bought, the pistols still missing (xcom1 en-US STR_PISTOL)
HIRE_OWNER = 1                           # D254 (b) (OWNER?-P9-1): the client set the Soldier row: seat 1 owns the hire
ROW_H = scr.ROW_H                        # 8 px: one small-font text row (TextList::updateVisible)
PURCHASE_LIST_H = 120                    # PurchaseState :111 TextList(287, 120, 8, 54) (F6630: Sell's geometry)
SHARED_PURCHASE_LIST_H = PURCHASE_LIST_H - ROW_H   # D243 by analogy (V-P4): one text row shorter in SHARED
SETTLE_S = 0.2                           # one pump after a Purchase list shows: its init() runs after the push
SEL_S = e1.SEL_S                         # 3 s: a cross-machine amount
PAGE_S = e1.PAGE_S                       # 5 s: a screen push / close after a real click or a release
ANSWER_S = e1.ANSWER_S                   # 2.5 s
SCREEN_S = e1.SCREEN_S                   # 10 s
EQUAL_S = e1.EQUAL_S                     # 10 s: a shared_apply's effect may lag one round trip


class FixtureMiss(scr.FixtureMiss):
    pass


MISSES = scr.MISSES


# ===================== probes =====================


def short(e, n=400):
    return scr.short(e, n)


def stack(gc):
    return e1.stack(gc)


def top(gc):
    return e1.top(gc)


def wait_until(pred, timeout, interval=0.2):
    return e1.wait_until(pred, timeout, interval)


def poll(fn, timeout, interval=0.2):
    return e1.poll(fn, timeout, interval)


def rows(gc, **kw):
    return e1.rows(gc, **kw)


def as_int(s):
    return scr.as_int(s)


def prow_of(r, item):
    """(stock, amount) of the Purchase row whose item type == item (columns name, cost, stock, amount)."""
    for row in r.get("rows") or []:
        if row.get("item") == item:
            c = row.get("cells") or []
            return (as_int(c[2]) if len(c) > 2 else None), (as_int(c[3]) if len(c) > 3 else None)
    return None, None


def pamount(gc, item):
    return prow_of(rows(gc), item)[1]


def pamounts(r):
    """{name: amount} of every Purchase row (amount = cells[3])."""
    out = {}
    for row in r.get("rows") or []:
        c = row.get("cells") or []
        out[c[0] if c else ""] = as_int(c[3]) if len(c) > 3 else None
    return out


def pall_zero(r):
    a = pamounts(r)
    return bool(a) and all(v == 0 for v in a.values())


def prow_color(r, item):
    """(amount, color) of the Purchase row whose item type == item."""
    for row in r.get("rows") or []:
        if row.get("item") == item:
            c = row.get("cells") or []
            return (as_int(c[3]) if len(c) > 3 else None), row.get("color")
    return None, None


def cost_text(r):
    """PurchaseState's _txtPurchases (xcom1 en-US STR_COST_OF_PURCHASES "Cost of Purchases>{ALT}{0}")."""
    for t in r.get("texts") or []:
        if "COST OF PURCHASES" in (t or "").upper():
            return t
    return None


def funds_text(gc):
    """screen_state.funds: the top PurchaseState's constructor-time funds text (None when the top is not one)."""
    r = gc.cmd({"cmd": "screen_state"})
    return r.get("funds") if r.get("top") == "purchase" else None


def incoming(gc):
    r = gc.cmd({"cmd": "incoming_transfers"})
    return {k: r.get(k) for k in ("ok", "items", "soldiers", "soldierOwners", "scientists", "engineers", "error")}


def inc_item(gc, item):
    return ((incoming(gc).get("items") or {}).get(item, 0))


def followup(gc):
    r = gc.cmd({"cmd": "followup_state"})
    return {k: r.get(k) for k in ("ok", "state", "isTop", "rows", "error")}


def purchase_ready(gc):
    """Top PurchaseState with its list built."""
    if top(gc) != "PurchaseState":
        return False
    r = rows(gc)
    return r.get("state") == "PurchaseState" and r.get("screen") is True and len(r.get("rows") or []) > 0


def sel(gc, key):
    return e1.sel(gc, key)


def sel_rows(gc, key):
    return e1.sel_rows(gc, key)


def view(gc):
    """One machine's end-of-row state for the EVIDENCE line."""
    r = rows(gc)
    v = {"stack": stack(gc), "sel": e1.sel_all(gc), "shared": fst.sstats(gc), "incoming": incoming(gc),
         "screen": {"state": r.get("state")}}
    if r.get("state") == "PurchaseState":
        v["screen"].update({"amounts": {k: a for k, a in pamounts(r).items() if a}, "funds": funds_text(gc),
                            "cost": cost_text(r), "labels": scr.label_items(r), "highlighted": pres.highlighted(r)})
    if top(gc) == "CannotReequipState":
        v["followup"] = followup(gc)
    return v


def evidence(rid, obj):
    scr.evidence(rid, obj)


def capture(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's stack, sel_state, top screen rows (whole), funds, incoming transfers,
    follow-up rows, shared stats and dialog, then raise."""
    cap = {}
    for gc in machines:
        try:
            cap[gc.name] = {"stack": stack(gc), "sel": e1.sel_all(gc), "screen": rows(gc), "funds": scr.funds(gc),
                            "screenFunds": funds_text(gc), "incoming": incoming(gc), "followup": followup(gc),
                            "shared": fst.sstats(gc), "dialog": scr.dialog(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


# ===================== fixtures =====================


def buy_pre(js, ctx):
    """BUY pre-cell: funds0 equal on both, base 0's free quarters >= MIN_FREE_QUARTERS on both, the roster names."""
    host, client = js.host, js.client
    m = (host, client)
    ctx["names"] = scr.roster_names(host)
    ctx["funds0"] = {gc.name: scr.funds(gc) for gc in m}
    q = {}
    for gc in m:
        r = gc.cmd({"cmd": "base_report"})
        q[gc.name] = {k: r.get(k) for k in ("ok", "name", "availableQuarters", "usedQuarters")}
    ctx["quarters"] = q
    free = {n: (v.get("availableQuarters") or 0) - (v.get("usedQuarters") or 0) for n, v in q.items()}
    if (len(ctx["names"]) != 2 or ctx["funds0"]["host"] is None or ctx["funds0"]["host"] != ctx["funds0"]["client"]
            or not all(f >= MIN_FREE_QUARTERS for f in free.values())):
        capture("BUY pre-cell", f"coopPlayers {ctx['names']} (want 2), funds {ctx['funds0']} (want equal), free "
                f"quarters {free} (want >= {MIN_FREE_QUARTERS} on both)", m)


def req_pre(js, ctx):
    """REQ pre-cell: screen_push {cannot_reequip} on both (client first); both tops CannotReequipState with equal
    followup_state rows; the roster names and funds0."""
    host, client = js.host, js.client
    m = (host, client)
    ctx["names"] = scr.roster_names(host)
    ctx["funds0"] = {gc.name: scr.funds(gc) for gc in m}
    pushed = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "screen_push", "screen": "cannot_reequip", "base": 0, "missing": REQ_MISSING})
        pushed[gc.name] = {k: r.get(k) for k in ("ok", "screen", "base", "error")}
    ok, secs = wait_until(lambda: all(top(gc) == "CannotReequipState" for gc in m), PAGE_S)
    time.sleep(SETTLE_S)   # one pump: CannotReequipState fills its rows in init() (:110-:124)
    fu = {gc.name: followup(gc) for gc in m}
    ctx["reequip"] = {"push": pushed, "up": ok, "secs": secs, "followup": fu}
    if not (ok and all(v.get("isTop") is True and v.get("rows") for v in fu.values())
            and fu["host"].get("rows") == fu["client"].get("rows")):
        capture("REQ pre-cell", f"screen_push cannot_reequip {pushed}; tops CannotReequipState {ok}; followup_state "
                f"{fu} (want equal, non-empty rows on both)", m)


def hygiene(host, client, ctx):
    """Holds off; boxes dismissed (ErrorMessageState / CoopState only, F4333); every Purchase screen cancelled with
    its real Cancel - both machines back on GeoscapeState (a miss is a FIXTURE-STOP)."""
    m = (host, client)
    h = {"holds": {gc.name: e1.hold(gc, False) for gc in m}, "dismissed": [], "cancelled": []}
    t0 = time.time()
    while time.time() - t0 < SCREEN_S:
        busy = False
        for gc in m:
            t = top(gc)
            if t in ("ErrorMessageState", "CoopState"):
                h["dismissed"].append(f"{gc.name}:{fst.dismiss_box(gc)}")
                busy = True
            elif t == "PurchaseState":
                h["cancelled"].append(f"{gc.name}:{e1.click(gc, CANCEL)}")
                wait_until(lambda gc=gc: top(gc) != "PurchaseState", PAGE_S)
                busy = True
        if not busy and time.time() - t0 > 0.6:
            break
        time.sleep(0.2)
    h["stacks"] = {gc.name: stack(gc) for gc in m}
    ctx["hygiene"] = h
    if not all(top(gc) == "GeoscapeState" for gc in m):
        capture("row hygiene", f"not both on GeoscapeState after the hygiene (stacks {h['stacks']})", m)


def open_buy(gc, ctx, key):
    """open_screen {screen: "purchase"} (base 0); ready, then one pump for its init(); a miss is a FIXTURE-STOP."""
    r = gc.cmd({"cmd": "open_screen", "screen": "purchase"})
    ok, secs = wait_until(lambda: purchase_ready(gc), PAGE_S)
    time.sleep(SETTLE_S)
    ctx[key] = {"resp": {k: r.get(k) for k in ("ok", "error")}, "ready": ok, "secs": secs}
    if not ok:
        capture(f"open_screen purchase ({gc.name})", f"PurchaseState not ready within {PAGE_S}s ({ctx[key]}; stack "
                f"{stack(gc)})", (gc,))


def buy_start(host, client, ctx):
    """BUY row start: hygiene, funds0 restored on both (client first) when they moved, both Purchase screens open."""
    hygiene(host, client, ctx)
    scr.restore_funds(host, client, ctx, scr.boot_of(ctx))
    for gc in (host, client):
        open_buy(gc, ctx, f"open_{gc.name}")
    ctx["funds0Text"] = {gc.name: funds_text(gc) for gc in (host, client)}


# ===================== cell helpers =====================


def set_ok(gc, value, ctx, key, item=None, row=None):
    return e1.set_ok(gc, value, ctx, key, item=item, row=row)


def pcross(gc, item, want, ctx, key, timeout=SEL_S):
    ok, got, secs = poll(lambda: (lambda a: (a == want, a))(pamount(gc, item)), timeout)
    ctx[key] = {"want": want, "got": got, "ok": ok, "secs": secs}
    return [] if ok else [f"{gc.name}'s {item} amount {got} {timeout}s after the other machine's edit (want {want})"]


def gone(gc, ctx, key, timeout=PAGE_S):
    return e1.gone(gc, ctx, key, timeout, cls="PurchaseState")


def no_box(host, client, ctx, key):
    return e1.no_box(host, client, ctx, key)


def stays_rebuilt(gc, ctx, key, want=None, timeout=SCREEN_S):
    """gc's top stays PurchaseState while the world changes and the screen is rebuilt (screen_state.funds differs from
    the row start's), then (want) its amounts {item: n} equal want - else every amount 0 - within the timeout."""
    tops, f0 = [], ctx["funds0Text"][gc.name]

    def rebuilt():
        t = top(gc)
        if t not in tops:
            tops.append(t)
        if t != "PurchaseState":
            return False, None
        fx, r = funds_text(gc), rows(gc)
        got = {i: prow_of(r, i)[1] for i in want} if want else {k: a for k, a in pamounts(r).items() if a}
        done = fx is not None and fx != f0 and (got == want if want else pall_zero(r))
        return done, {"funds": fx, "amounts": got}
    ok, last, secs = poll(rebuilt, timeout)
    ctx[key] = {"ok": ok, "tops": tops, "funds0": f0, "seen": last, "secs": secs}
    what = f"amounts {want}" if want else "every amount 0"
    f = [] if ok else [f"{gc.name}'s PurchaseState not rebuilt (funds text != {f0!r}) with {what} within {timeout}s "
                       f"(seen {last}, tops {tops})"]
    if tops != ["PurchaseState"]:
        f.append(f"{gc.name}'s top left PurchaseState while the world changed (tops {tops}; want it rebuilt, not popped)")
    return f


def inc_settled(host, client, before, want_delta, ctx, key, field="items", item=X, timeout=EQUAL_S):
    """incoming_transfers on both: items[item] (or `soldiers`) == before + want_delta within timeout."""
    def val(gc):
        r = incoming(gc)
        return (r.get("items") or {}).get(item, 0) if field == "items" else r.get(field)
    ok, got, secs = poll(lambda: (lambda v: (all(v[n] == before[n] + want_delta for n in v), v))(
        {gc.name: val(gc) for gc in (host, client)}), timeout)
    ctx[key] = {"ok": ok, "before": before, "got": got, "delta": want_delta, "secs": secs}
    what = f"items[{item}]" if field == "items" else field
    return [] if ok else [f"incoming {what} (host, client) {before} -> {got} (want +{want_delta} on both)"]


def sel_both(host, client, key, pred, timeout=SEL_S):
    last = {}

    def both():
        last.update({gc.name: sel(gc, key) for gc in (host, client)})
        return all(isinstance(v, dict) and pred(v) for v in last.values()), dict(last)
    return poll(both, timeout)


def pgeo(gc):
    """list_widgets on the top state (E2.1b's scr.geometry): the list rect, the buttons by caption, the labels."""
    return scr.geometry(gc)


def label_between(g, want_label):
    """(ok, why): a VISIBLE label whose text == want_label lies between the list's bottom and Cancel's top."""
    lst, cancel = g.get("list") or {}, (g.get("buttons") or {}).get(CANCEL) or {}
    hit = [t for t in g.get("labels") or [] if t.get("visible") is True and t.get("text") == want_label]
    if not hit:
        return False, f"no visible label {want_label!r} (labels {g.get('labels')})"
    t = hit[0]
    if not (isinstance(lst.get("y"), int) and isinstance(lst.get("h"), int) and isinstance(cancel.get("y"), int)):
        return False, f"list {lst} / {CANCEL} {cancel} rects missing"
    bottom = lst["y"] + lst["h"]
    if not (t["y"] >= bottom and t["y"] + t["h"] <= cancel["y"]):
        return False, (f"label rect y {t['y']}..{t['y'] + t['h']} not between the list's bottom {bottom} and the "
                       f"{CANCEL} button's top {cancel['y']} (D243)")
    return True, ""


# ===================== BUY rows =====================


def p_a_cells(host, client, ctx):
    def c1():
        buy_start(host, client, ctx)
        return set_ok(client, 3, ctx, "c1set", item=X) or pcross(host, X, 3, ctx, "c1host")

    def c2():
        return set_ok(host, 2, ctx, "c2set", item=Y) or pcross(client, Y, 2, ctx, "c2client")

    def c3():
        want = {f"i:{X}": 3, f"i:{Y}": 2}
        ok, got, secs = sel_both(host, client, BUY_KEY, lambda v: v.get("rows") == want and v.get("viewers") == [0, 1])
        ctx["c3sel"] = {"ok": ok, "sel": got, "secs": secs}
        revs = {n: (v or {}).get("rev") for n, v in (got or {}).items()}
        if not (ok and revs.get("host") == revs.get("client")):
            return [f"sel_state {BUY_KEY} (host, client) {got} (want rows {want}, equal rev, viewers [0, 1])"]
        cost = {gc.name: cost_text(rows(gc)) for gc in (host, client)}
        ctx["c3cost"] = cost
        return [] if cost["host"] and cost["host"] == cost["client"] else [
            f"the screens' Cost of Purchases texts {cost} (want equal)"]
    return [
        ("1 the client's X edit reaches the host's Purchase screen", c1),
        ("2 the host's Y edit reaches the client's", c2),
        ("3 one store on both: rows, rev, viewers; equal purchase costs", c3),
    ]


def p_k_cells(host, client, ctx):
    def c1():
        buy_start(host, client, ctx)
        f = set_ok(client, 2, ctx, "c1set", item=X)
        if f:
            return f

        def host_hl():
            r = rows(host)
            hc = r.get("highlightColor")
            return hc is not None and prow_color(r, X)[1] == hc, {"row": prow_color(r, X), "highlightColor": hc}
        ok, got, secs = poll(host_hl, SEL_S)
        ctx["c1host"] = {"ok": ok, "seen": got, "secs": secs}
        if not ok:
            return [f"the host's {X} (amount, color) {got.get('row')} {SEL_S}s after the client's edit (want color == "
                    f"highlightColor {got.get('highlightColor')}: a row another player set is highlighted, D203)"]
        rc = rows(client)
        ctx["c1client"] = {"row": prow_color(rc, X), "secondaryColor": rc.get("secondaryColor")}
        return [] if prow_color(rc, X)[1] == rc.get("secondaryColor") else [
            f"the client's own {X} color {prow_color(rc, X)[1]} (want secondaryColor {rc.get('secondaryColor')})"]

    def c2():
        f = set_ok(host, 1, ctx, "c2set", item=Y)
        if f:
            return f

        def client_hl():
            r = rows(client)
            hc = r.get("highlightColor")
            return hc is not None and prow_color(r, Y)[1] == hc, {"row": prow_color(r, Y), "highlightColor": hc}
        ok, got, secs = poll(client_hl, SEL_S)
        ctx["c2client"] = {"ok": ok, "seen": got, "secs": secs}
        return [] if ok else [f"the client's {Y} (amount, color) {got.get('row')} {SEL_S}s after the host's edit (want "
                              f"color == highlightColor {got.get('highlightColor')})"]

    def c3():
        ctx["c3click"] = e1.click(host, OK)
        f = gone(host, ctx, "c3hostGone") or stays_rebuilt(client, ctx, "c3clientRebuilt")
        if f:
            return f

        def cleared():
            r = rows(client)
            v = {"highlighted": pres.highlighted(r), "labels": scr.label_items(r), "top": r.get("state")}
            return r.get("state") == "PurchaseState" and not v["highlighted"] and scr.label_hidden(r), v
        ok, got, secs = poll(cleared, SEL_S)
        ctx["c3client"] = {"ok": ok, "seen": got, "secs": secs}
        return [] if ok else [f"the client's rebuilt screen {got} {SEL_S}s on (want no row in highlightColor and the "
                              f"label hidden: the list cleared and the host left)"]
    return [
        ("1 the client's edit is highlighted on the host's screen, not on its own", c1),
        ("2 the host's edit is highlighted on the client's screen", c2),
        ("3 the host's OK: the client's rebuilt screen has no highlight, zero amounts, no label", c3),
    ]


def p_l_cells(host, client, ctx):
    names = scr.boot_of(ctx)["names"]

    def geo_both(machines, check, key, timeout=SEL_S):
        last = {}

        def all_ok():
            out = True
            for gc in machines:
                g = pgeo(gc)
                ok, why = check(gc, g)
                last[gc.name] = {"ok": ok, "why": why, "geo": g}
                out = out and ok
            return out, dict(last)
        ok, got, secs = poll(all_ok, timeout)
        ctx[key] = {"ok": ok, "secs": secs, "seen": got}
        return [] if ok else [f"{gc.name}: {got[gc.name]['why']} {timeout}s on" for gc in machines if not got[gc.name]["ok"]]

    def height_ok(g):
        h = (g.get("list") or {}).get("h")
        return h == SHARED_PURCHASE_LIST_H, (f"list height {h} (want {SHARED_PURCHASE_LIST_H}, vanilla "
                                             f"{PURCHASE_LIST_H}: one text row shorter in SHARED, D243)")

    def c1():
        buy_start(host, client, ctx)
        return geo_both((host, client), lambda gc, g: label_between(g, scr.label_text(names, 0 if gc.name == "host" else 1)),
                        "c1geo")

    def c2():
        return geo_both((host, client), lambda gc, g: height_ok(g), "c2geo", timeout=0.5)

    def c3():
        ctx["c3cancel"] = e1.click(client, CANCEL)
        f = gone(client, ctx, "c3clientGone")
        if f:
            return f

        def host_ok(gc, g):
            shown = [t for t in g.get("labels") or [] if t.get("visible") is True]
            ok, why = height_ok(g)
            if shown:
                return False, f"a label is visible {shown} (want none: the client left)"
            return (g.get("top") == "PurchaseState" and ok), (why if not ok else f"top {g.get('top')}")
        return geo_both((host,), host_ok, "c3geo")
    return [
        ("1 both screens name the other player in a label between the list and the buttons", c1),
        ("2 both lists are one text row shorter than vanilla's (D243)", c2),
        ("3 the client leaves: the host's label hidden, its list height unchanged", c3),
    ]


def p_e_cells(host, client, ctx):
    def c1():
        buy_start(host, client, ctx)
        return set_ok(client, 3, ctx, "c1x", item=X) or set_ok(client, 2, ctx, "c1y", item=Y)

    def c2():
        r = host.cmd({"cmd": "buy", "item": GRENADE, "count": 1})
        ctx["c2buy"] = {k: r.get(k) for k in ("ok", "sent", "error")}
        if not (r.get("ok") and r.get("sent")):
            return [f"host buy {GRENADE} 1: {ctx['c2buy']}"]
        return stays_rebuilt(client, ctx, "c2rebuilt", want={X: 3, Y: 2})

    def c3():
        return pcross(host, X, 3, ctx, "c3x") + pcross(host, Y, 2, ctx, "c3y")
    return [
        ("1 the client's local amounts X 3, Y 2", c1),
        ("2 the host's lever purchase rebuilds the client's screen; its amounts survive", c2),
        ("3 the host's screen shows the same amounts", c3),
    ]


def p_c_cells(host, client, ctx):
    def c1():
        buy_start(host, client, ctx)
        ctx["before"] = {gc.name: inc_item(gc, X) for gc in (host, client)}
        f = set_ok(client, P_C_CLIENT, ctx, "c1set", item=X)
        if f:
            return f
        seen, rv, secs = poll(lambda: (lambda r: (bool(r) and r.get(f"i:{X}") == P_C_CLIENT, r))(sel_rows(host, BUY_KEY)),
                              SEL_S)
        ctx["c1hostSel"] = {"seen": seen, "rows": rv, "secs": secs}   # EVIDENCE only (never a failed cell)
        ctx["c1hold"] = e1.hold(host, True)
        if ctx["c1hold"] is not True:
            return [f"host shared_update_defer on answered deferred={ctx['c1hold']!r}"]
        f = set_ok(host, P_C_HOST, ctx, "c1hostSet", item=X)
        if f:
            e1.hold(host, False)
            return f
        ctx["c1click"] = e1.click(client, OK)
        return []

    def c2():
        ctx["c2release"] = e1.hold(host, False)
        f = gone(client, ctx, "c2gone") + no_box(host, client, ctx, "c2stacks")
        if f:
            return f
        f = inc_settled(host, client, ctx["before"], P_C_HOST, ctx, "c2incoming")
        if f:
            return [f[0] + f" (D203: the host buys its current list, {P_C_HOST})"]
        return stays_rebuilt(host, ctx, "c2hostRebuilt")
    return [
        ("1 client X 1; host held; host X 5; the client confirms", c1),
        ("2 released: the client's screen closes; the host bought its current list (5); host amounts 0", c2),
    ]


def p_d_cells(host, client, ctx):
    def c1():
        buy_start(host, client, ctx)
        ctx["before"] = {gc.name: inc_item(gc, X) for gc in (host, client)}
        f = set_ok(client, 2, ctx, "c1client", item=X) or set_ok(host, 2, ctx, "c1host", item=X)
        if f:
            return f
        ctx["c1hold"] = e1.hold(client, True)
        if ctx["c1hold"] is not True:
            return [f"client shared_update_defer on answered deferred={ctx['c1hold']!r}"]
        ctx["c1click"] = e1.click(host, OK)
        f = gone(host, ctx, "c1hostGone")
        ctx["tChange"] = time.time()
        if f:
            e1.hold(client, False)
        return f

    def c2():
        ctx["c2click"] = e1.click(client, OK)
        ctx["c2release"] = e1.hold(client, False)
        ctx["heldAfterChangeS"] = round(time.time() - ctx["tChange"], 2)
        f = gone(client, ctx, "c2gone") + no_box(host, client, ctx, "c2stacks")
        if f:
            return f
        f = inc_settled(host, client, ctx["before"], 2, ctx, "c2incoming")
        if f:
            return [f[0] + " (one purchase, MR8)"]
        ok, s, secs = poll(lambda: (lambda x: (x.get("lastFail") == SEL_DUP, x))(fst.sstats(client)), ANSWER_S)
        ctx["c2stats"] = {"ok": ok, "stats": s, "secs": secs}
        return [] if ok else [f"the client's shared_stats {s} (want lastFail {SEL_DUP!r}, PR-45)"]
    return [
        ("1 both at X 2; client held; the host confirms and its screen closes", c1),
        ("2 the client's duplicate confirm: one purchase, no box, coop_sel_dup", c2),
    ]


def p_r_cells(host, client, ctx):
    boot = scr.boot_of(ctx)

    def c1():
        buy_start(host, client, ctx)
        ctx["before"] = {gc.name: inc_item(gc, X) for gc in (host, client)}
        f = set_ok(client, P_R_SET, ctx, "c1set", item=X)
        if f:
            return f
        want = {f"i:{X}": P_R_SET}
        seen, s0, secs = sel_both(host, client, BUY_KEY, lambda v: v.get("rows") == want)
        ctx["c1before"] = {"seen": seen, "sel": s0, "secs": secs}   # EVIDENCE only: the rev the refusal must not move
        ctx["c1funds"] = scr.set_funds_both(host, client, P_R_FUNDS)
        ctx["c1click"] = e1.click(client, OK)
        ok, secs = wait_until(lambda: top(client) == "CoopState" and stack(client)[-2:-1] == ["PurchaseState"]
                              and scr.dialog(client).get("code") == SHARED_FAIL, PAGE_S, 0.1)
        ctx["c1box"] = {"ok": ok, "secs": secs, "stack": stack(client), "dialog": scr.dialog(client),
                        "shared": fst.sstats(client)}
        if not ok:
            return [f"the client's stack {stack(client)} / dialog {scr.dialog(client)} {PAGE_S}s after its refused "
                    f"purchase (want CoopState {SHARED_FAIL} directly over its PurchaseState, MR10)"]
        after = {gc.name: sel(gc, BUY_KEY) for gc in (host, client)}
        ctx["c1after"] = after
        f = []
        for n, v in after.items():
            rev0 = ((s0 or {}).get(n) or {}).get("rev")
            if not isinstance(v, dict) or v.get("rows") != want or rev0 is None or v.get("rev") != rev0:
                f.append(f"{n}'s sel_state {BUY_KEY} {v} (want rows {want}, rev {rev0} unchanged by the refusal)")
        return f

    def c2():
        ctx["c2back"] = fst.dismiss_box(client) if top(client) == "CoopState" else None
        ctx["c2funds"] = scr.set_funds_both(host, client, boot["funds0"]["host"])
        ok, secs = wait_until(lambda: top(client) == "PurchaseState", PAGE_S)
        ctx["c2top"] = {"ok": ok, "secs": secs, "stack": stack(client)}
        if not ok:
            return [f"the client's top {top(client)!r} after coop_dialog_back (want its PurchaseState)"]
        ctx["c2click"] = e1.click(client, OK)
        f = gone(client, ctx, "c2gone")
        if f:
            return f
        f = inc_settled(host, client, ctx["before"], P_R_SET, ctx, "c2incoming")
        return f or stays_rebuilt(host, ctx, "c2hostRebuilt")
    return [
        ("1 a refused purchase keeps the client's screen and the shared list (MR10)", c1),
        ("2 the retried purchase applies; the host's screen rebuilt at zero (D204)", c2),
    ]


def p_h_cells(host, client, ctx):
    def c1():
        buy_start(host, client, ctx)
        ctx["before"] = {gc.name: incoming(gc) for gc in (host, client)}
        f = set_ok(client, 1, ctx, "c1s", item=S) or set_ok(host, 1, ctx, "c1x", item=X)
        if f:
            return f
        f = pcross(host, S, 1, ctx, "c1hostS")
        if f:
            return f
        want = {f"h:{S}": 1, f"i:{X}": 1}
        weds = {f"h:{S}": 1, f"i:{X}": 0}
        ok, got, secs = sel_both(host, client, BUY_KEY, lambda v: v.get("rows") == want and v.get("editors") == weds)
        ctx["c1sel"] = {"ok": ok, "sel": got, "secs": secs}
        return [] if ok else [f"sel_state {BUY_KEY} (host, client) {got} (want rows {want}, editors {weds})"]

    def c2():
        ctx["c2click"] = e1.click(host, OK)
        f = gone(host, ctx, "c2hostGone")
        if f:
            return f
        b = ctx["before"]
        f = inc_settled(host, client, {n: v.get("soldiers") for n, v in b.items()}, 1, ctx, "c2soldiers",
                        field="soldiers")
        f = f or inc_settled(host, client, {n: (v.get("items") or {}).get(X, 0) for n, v in b.items()}, 1, ctx,
                             "c2items")

        def new_owners():   # D254 (b): the new soldierOwners entry == HIRE_OWNER on both machines (P-h step (2))
            owners = {}
            for gc in (host, client):
                now = list(incoming(gc).get("soldierOwners") or [])
                for o in b[gc.name].get("soldierOwners") or []:
                    if o in now:
                        now.remove(o)
                owners[gc.name] = now
            return all(v == [HIRE_OWNER] for v in owners.values()), owners
        ok, owners, secs = poll(new_owners, EQUAL_S)
        ctx["c2hireOwner"] = {"ok": ok, "newEntries": owners, "HIRE_OWNER": HIRE_OWNER, "secs": secs}
        fo = [] if ok else [f"the new soldierOwners entry (host, client) {owners} (want [{HIRE_OWNER}] on both within "
                            f"{EQUAL_S}s, D254 (b))"]
        return f or stays_rebuilt(client, ctx, "c2clientRebuilt") or fo
    return [
        ("1 the client's Soldier row and the host's X row are on one shared list", c1),
        ("2 the host's OK hires the soldier and buys X; the client's screen rebuilt at zero", c2),
    ]


# ===================== REQ row =====================


def p_q_cells(host, client, ctx):
    pre = ctx["pre"] if "reequip" in ctx.get("pre", {}) else ctx["boot"]

    def open_req(gc, key):
        c = e1.click(gc, PURCHASE_RECRUIT)
        ok, secs = wait_until(lambda: purchase_ready(gc), PAGE_S)
        time.sleep(SETTLE_S)
        ctx[key] = {"click": c, "ready": ok, "secs": secs, "stack": stack(gc)}
        return [] if ok else [f"{gc.name} {PURCHASE_RECRUIT!r} -> top {top(gc)!r} within {PAGE_S}s (want PurchaseState)"]

    def c1():
        ctx["before"] = {gc.name: {X: inc_item(gc, X), Y: inc_item(gc, Y)} for gc in (host, client)}
        f = open_req(client, "c1open")
        if f:
            return f
        r = rows(client)
        pre_fill = {X: prow_of(r, X)[1], Y: prow_of(r, Y)[1]}
        ctx["c1clientPreFill"] = pre_fill
        if pre_fill != {X: 3, Y: 2}:
            return [f"the client's reequip Purchase amounts {pre_fill} (want vanilla's pre-fill {X} 3, {Y} 2)"]
        want = {f"i:{X}": 3, f"i:{Y}": 2}
        ok, got, secs = poll(lambda: (lambda v: (v == want, v))(sel_rows(host, REQ_KEY)), SEL_S)
        ctx["c1hostSel"] = {"ok": ok, "rows": got, "secs": secs}
        if not ok:
            return [f"the host's sel_state {REQ_KEY} rows {got} {SEL_S}s after the client opened its reequip Purchase "
                    f"(want {want}: the lone opener's pre-fill seeds the list)"]
        return set_ok(client, 0, ctx, "c1y0", item=Y)

    def c2():
        f = open_req(host, "c2open")
        if f:
            return f
        ok, got, secs = poll(lambda: (lambda r: ((prow_of(r, X)[1], prow_of(r, Y)[1]) == (3, 0),
                                                 (prow_of(r, X)[1], prow_of(r, Y)[1])))(rows(host)), SEL_S)
        ctx["c2hostAmounts"] = {"ok": ok, "xy": got, "secs": secs}
        if not ok:
            return [f"the host's reequip Purchase ({X}, {Y}) {got} (want (3, 0): adopted, not its own pre-fill)"]
        ok, got, secs = sel_both(host, client, REQ_KEY, lambda v: v.get("viewers") == [0, 1])
        ctx["c2sel"] = {"ok": ok, "sel": got, "secs": secs}
        return [] if ok else [f"sel_state {REQ_KEY} (host, client) {got} (want viewers [0, 1])"]

    def c3():
        ctx["c3click"] = e1.click(host, OK)
        ok, fu, secs = poll(lambda: (lambda v: (top(host) == "CannotReequipState" and v.get("isTop") is True
                                                and v.get("rows") == REQ_AFTER, v))(followup(host)), PAGE_S)
        ctx["c3host"] = {"ok": ok, "followup": fu, "secs": secs, "stack": stack(host)}
        if not ok:
            return [f"the host's stack {stack(host)} / followup_state {fu} {PAGE_S}s after its OK (want top "
                    f"CannotReequipState with rows {REQ_AFTER})"]
        b = ctx["before"]
        f = inc_settled(host, client, {n: v[X] for n, v in b.items()}, 3, ctx, "c3x")
        f = f or inc_settled(host, client, {n: v[Y] for n, v in b.items()}, 0, ctx, "c3y", item=Y)
        if f:
            return f
        ok, a, secs = poll(lambda: (lambda r: (top(client) == "PurchaseState" and pall_zero(r),
                                               {k: v for k, v in pamounts(r).items() if v}))(rows(client)), SEL_S)
        ctx["c3clientAmounts"] = {"ok": ok, "nonZero": a, "secs": secs, "stack": stack(client)}
        return [] if ok else [f"the client's reequip Purchase amounts {a} / top {top(client)!r} (want PurchaseState, "
                              f"every amount 0: the list was bought)"]

    def c4():
        ctx["c4cancel"] = e1.click(client, CANCEL)
        ok, fu, secs = poll(lambda: (lambda v: (top(client) == "CannotReequipState" and v.get("isTop") is True
                                                and v.get("rows") == REQ_AFTER, v))(followup(client)), PAGE_S)
        ctx["c4client"] = {"ok": ok, "followup": fu, "secs": secs, "preRows": pre["reequip"]["followup"]}
        return [] if ok else [f"the client's followup_state {fu} after its Cancel (want top CannotReequipState with rows "
                              f"{REQ_AFTER}: the purchase lowered its missing counts too)"]
    return [
        ("1 the client's reequip Purchase seeds the shared list with its pre-fill", c1),
        ("2 the host's reequip Purchase adopts the list", c2),
        ("3 the host's OK buys the list; its missing counts drop; the client's amounts clear", c3),
        ("4 the client's missing counts dropped too", c4),
    ]


# ===================== one boot =====================


def run_boot(boot, tag, port, pre_fn, rows_spec, results, walls):
    """One boot: bring-up + pre_fn(js, pre) (pre-cell), then each row (EVIDENCE, PASS / FAIL)."""
    t0, js, pre = time.time(), None, {}
    crash0 = session._crash_log_snapshot()
    miss = None
    try:
        try:
            js = shared_fixture.bring_up(tag, (0, 0, port))
            pre_fn(js, pre)
        except Exception as e:
            miss = f"pre-cell (FIXTURE-STOP) {e if isinstance(e, MISSES) else short(e, 800)}"
        for n, (rid, cells_fn) in enumerate(rows_spec):
            tr = time.time()
            ctx = {"row": rid, "boot": pre if n > 0 else {}, "pre": pre if n == 0 else {"see": rows_spec[0][0]}}
            verdict = miss
            if verdict is None:
                verdict, ctx["cells"] = scr.run_cells(cells_fn(js.host, js.client, ctx))
                g = e1.guard(js.host, js.client, crash0, ctx, n == len(rows_spec) - 1, False)
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
                    print(f"[w2p7-sce3] release shared_update_defer: {short(e)}", flush=True)
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2p7-sce3] shutdown: {short(e)}", flush=True)
        walls[boot] = round(time.time() - t0, 1)


BOOTS = (("BUY", "w2p7sce3_buy", buy_pre,
          (("P-a", p_a_cells), ("P-k", p_k_cells), ("P-l", p_l_cells), ("P-e", p_e_cells), ("P-c", p_c_cells),
           ("P-d", p_d_cells), ("P-r", p_r_cells), ("P-h", p_h_cells))),
         ("REQ", "w2p7sce3_req", req_pre, (("P-q", p_q_cells),)))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, pre_fn, rows_spec in BOOTS:
        run_boot(boot, tag, BOOT_PORT[boot], pre_fn, rows_spec, results, walls)
    order = [rid for _, _, _, rs in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_selection_purchase: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
