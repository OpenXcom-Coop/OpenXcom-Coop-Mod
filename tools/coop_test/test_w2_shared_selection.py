"""W2-P7 S-C-E1 - test_w2_shared_selection.py: in a SHARED campaign both players on the same Sell screen edit ONE
shared list of pending amounts (owner D184 (a)); the host holds the list and applies its current list at whoever's
confirm (D203: a confirm racing an edit is let through), a second confirm of the same selection counts as done (MR8),
the other player's screen stays open, rebuilt with the new stock and zero amounts (D204 (a)), a world change on the
base keeps the shared amounts, clamped (F2161), and the list covers the normal, page-3 and forced Sell screens (MR16)
(docs rewrite/prompts/w2p7_sc_design.md section 4, AMENDMENT P7-8 sections 3-4: PR-37..PR-46; MR7, MR8, MR16;
Q-P8-1..Q-P8-3 (a)).

Before S-C-E1 (design section 4, F2161, F6106): each machine's Sell screen keeps its own amounts - the other player
never sees them, a confirm sends the confirmer's own list, a rebuild after any world change resets every amount to 0,
and the store probe sel_state is an empty stub.

Fixtures (AMENDMENT P7-8 section 4.1):
  SEL  = shared_fixture.bring_up(tag, (0, 0, "47260")), geoscape only; X = STR_RIFLE, Y = STR_PISTOL; pre-cell (a
         failure is a FIXTURE-STOP: one CAPTURE line, every row of the boot FAILs "pre-cell"): the first get_soldiers
         soldier of base 0 owned by seat 1 (the client), taken off its craft by the host's craft_assign {on: false}
         and off-craft on both machines. Each row starts by turning every hold off, dismissing any box and cancelling
         any Sell screen on both machines, restages X and Y with give_items {+STAGE} on both (client first, S25), then
         opens open_screen {screen: "sell"} on both (the real SellState, init() binds it); rows end both screens with
         Cancel unless the row closes them.
  FXST = test_w2_shared_forced_storage.fx_st (FX-ST, AMENDMENT P7-7 section 3; boot 2's T pins) with OPTS =
         {storageLimitsEnforced, canSellLiveAliens, oxceAutoSell} on BOTH user dirs (oxceAutoSell: P7-7 RULINGS R-D1-3,
         getAutosell reads false while the local option is off) and set_autosell {T, on: true} on both (client first)
         before the battle; pre-cell adds screen_rows {autosell: [T]} true on both after the client's adoption.
  Probes / levers: sel_state (PR-46: {localSeat, keys: {key: {rows, editors, eseqs, rev, viewers}}}, key
  "<screen>|<variant>|<baseIdx>|<extra>": `sell|n|0|` normal, `sell|d|0|` page 3, `sell|f|0|` forced), set_autosell
  {item, on} (PR-46, TEST-ONLY world write), screen_rows / screen_set_amount (the top Sell screen; columns name,
  remaining, amount, value), shared_update_defer {on} (a "hold": that machine's per-frame SharedEcon drain waits;
  every client hold is released within HOLD_MAX_S of the host's world change, F4529 / F5840), the host's `sell` lever
  (unbound: applied as sent, PR-39 (iv), F6126), click_widget on the real captions (Sell/Sack, Cancel, SELL), and
  dismiss_popup ONLY on an ErrorMessageState top / coop_dialog_back ONLY on a CoopState top (F4333).

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot SEL (port 47260): E-a, E-e, E-c, E-d, E-b, E-f.
  E-a (1) client X = 3 -> the host's X amount 3 within SEL_S.
      (2) host Y = 2 -> the client's Y amount 2 within SEL_S.
      (3) sel_state `sell|n|0|` on both: rows {i:STR_RIFLE: 3, i:STR_PISTOL: 2}, equal rev, viewers [0, 1]; both
          screens' "Value of Sales" text equal.
  E-e (1) client X = 3, Y = 2 (local check only).
      (2) the host's `sell {X, <stock - 2>}` (the lever): the client's top stays SellState (rebuilt: X lists the new
          stock 2), its X amount 2 (clamped to the stock) and Y amount 2 (survived).
      (3) the host's X amount 2 and Y amount 2.
  E-c (1) client X = 1, then a wait of up to SEL_S for the host's sel_state to show it (EVIDENCE only, never a
          failed cell); host hold on; host X = 5; client Sell/Sack.
      (2) host hold off: within PAGE_S the client's SellState gone, no CoopState on either; X stock == before - 5 on
          both (D203: the host applies its current list); the host's top SellState, every amount 0 (D204).
  E-d (1) client X = 2; host screen_set_amount {X, 2} (no change when shared); client hold on; host Sell/Sack ->
          the host's SellState gone within PAGE_S.
      (2) client Sell/Sack; client hold off: within PAGE_S its SellState gone, no CoopState on either, X stock ==
          before - 2 on both (one sale, MR8), the client's shared_stats.lastFail == coop_sel_dup (PR-45).
  E-b (1) client Y = 1 and its own soldier's row = 1; the host's screen_rows lists no row named after that soldier
          (MR7); the host's sel_state rows hold s:<id>: 1 and i:STR_PISTOL: 1 within SEL_S.
      (2) host Sell/Sack: its SellState gone within PAGE_S; the client's top stays SellState (rebuilt), every amount
          0 (D204); Y stock -1 on both; that soldier gone from base 0 on both (get_soldiers); no CoopState.
  E-f (1) client X = 1 -> the host's X amount 1 within SEL_S.
      (2) client Cancel: the host's sel_state viewers [0], rows {i:STR_RIFLE: 1}, its X amount 1.
      (3) host Cancel: the key absent from sel_state on both within SEL_S.
      (4) client open_screen sell: every amount 0; sel_state rows {} viewers [1] on both.
  Boot FXST (port 47261): E-p (before the OKs), then E-s (after them).
  E-p (1) the client's page-3 Sell (page 2 -> SELL): its T amount == T_QTY (vanilla's autosell pre-fill) and the
          host's sel_state `sell|d|0|` rows == {i:T: T_QTY} within SEL_S (Q-P8-2 (a): the lone opener seeds).
      (2) client T = 4; the host's page-3 Sell: its T amount 4 within SEL_S.
      (3) host Sell/Sack: its SellState gone within PAGE_S; the client's stays (rebuilt): T lists T_QTY - 4, amount
          0; recovered[T] == T_QTY - 4 and autosell[T] false on both.
  E-s (1) test_w2_shared_forced_storage.both_oks_forced: both forced SellStates, boxes dismissed; N = the fewest
          rifles that clear the host's base (base_report usedStores / availableStores, rifle size 0.2, Base::
          storesOverfull's integer rule), computed on each boot (first construction, red build: used 118.4 /
          available 65 -> N 267; E-p's green sale of 4 corpses (size 0.4) changes the stores, so a literal would not
          transfer, F6239).
      (2) client Rifle = N - 1 (its OK stays hidden) -> the host's Rifle amount N - 1 within SEL_S, OK hidden on both.
      (3) host Rifle = N: OK visible on both; client Sell/Sack: both forced SellStates close themselves within
          SCREEN_S (tops GeoscapeState), world_diff empty, no CoopState.
Guard on every row: no new crash log; FXST rows also host event_state.fatalVote.armed 0; the client zero-disk at
each boot's end.

RED (commit S-C-E1.1: probes, the autosell lever and these rows; product untouched): E-a, E-f fail on cell 1 (the
host's X amount stays 0), E-e on cell 2 (the client's rebuilt amounts are 0), E-c on cell 2 (X stock before - 1: the
client's own list was applied), E-d on cell 2 (X stock before - 4: two sales), E-b on cell 1 (the host's sel_state
holds no key), E-p on cell 1 (the host's sel_state holds no key), E-s on cell 2 (the host's Rifle amount 0). GREEN
(commit S-C-E1.2): every row passes.
Each row prints ONE "EVIDENCE <id>:" line (both machines' sel_state at the row's end), then "PASS <id>" or "FAIL
<id>: <message>". WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_selection.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import event_state
import shared_fixture
import test_w2_battle_end_campaign as camp
import test_w2_shared_page3 as p3
import test_w2_shared_forced_storage as fst

# ----- pins (AMENDMENT P7-8 section 4 / 4.1) -----
X, Y = "STR_RIFLE", "STR_PISTOL"         # SEL: X and Y (looked up by type, S25)
STAGE = 10                               # each SEL row's give_items {X, Y} on both (client first; >= 5 for E-c/E-d)
SEL_KEY = "sell|n|0|"                    # SharedEcon::sellKey of base 0, normal (P7-7 PR-30 key format, P7-8 PR-37)
PAGE3_KEY = "sell|d|0|"                  # base 0's page-3 Sell
FORCED_KEY = "sell|f|0|"                 # base 0's forced storage Sell
BOOT_PORT = {"SEL": "47260", "FXST": "47261"}   # AMENDMENT P7-8 section 4 (S26, F6118): E1 = 47260 (SEL), 47261 (FXST)
OPTS_FXST = {"storageLimitsEnforced": True, "canSellLiveAliens": True, "oxceAutoSell": True}  # P7-8 section 4.1 FXST
T, T_QTY = fst.T, fst.T_QTY              # FX-ST boot 2: STR_SECTOID_CORPSE, page-3 count 10 (the D2 file's pins)
RIFLE, RIFLE_SIZE = fst.RIFLE, fst.RIFLE_SIZE   # CONSTANTS T0-S3 (ii): STR_RIFLE, size 0.2
E_C_CLIENT, E_C_HOST = 1, 5              # P7-8 section 4.1 E-c's amounts
E_P_SET = 4                              # P7-8 section 4.1 E-p (2)
SEL_DUP = "coop_sel_dup"                 # PR-45: a duplicate confirm, answered as a success
SELL_OK, CANCEL = "Sell/Sack", "Cancel"  # SellState's captions (F5572)
STORAGE_MARK = fst.STORAGE_MARK          # "STORAGE SPACE EXCEEDED"
SEL_S = 3                                # P7-8 section 4: a cross-machine amount
PAGE_S = p3.PAGE_S                       # 5 s: a screen push / close after a real click or a release
ANSWER_S = fst.ANSWER_S                  # 2.5 s
SCREEN_S = fst.SCREEN_S                  # 10 s
EQUAL_S = fst.EQUAL_S                    # 10 s: a shared_apply's effect may lag one round trip
OFF_CRAFT_S = 30                         # SEL pre-cell: the soldier off its craft on both (test_shared_craft_capacity's wait)


class FixtureMiss(Exception):
    pass


MISSES = (FixtureMiss, fst.FixtureMiss, p3.FixtureMiss, camp.FixtureMiss)


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


def rows(gc, **kw):
    return p3.rows(gc, **kw)


def as_int(s):
    return p3.as_int(s)


def row_of(r, item):
    """(remaining, amount) of the row whose item type == item in a screen_rows reply ((None, None) if absent)."""
    for row in r.get("rows") or []:
        if row.get("item") == item:
            c = row.get("cells") or []
            return (as_int(c[1]) if len(c) > 1 else None), (as_int(c[2]) if len(c) > 2 else None)
    return None, None


def amount(gc, item):
    return row_of(rows(gc), item)[1]


def amounts(r):
    """{name: amount} of every row of a screen_rows reply."""
    return {(row.get("cells") or [""])[0]: as_int((row.get("cells") or ["", "", ""])[2]) for row in r.get("rows") or []}


def all_zero(r):
    a = amounts(r)
    return bool(a) and all(v == 0 for v in a.values())


def sales_text(r):
    """SellState's _txtSales (xcom1 en-US STR_VALUE_OF_SALES: "VALUE OF SALES> {ALT}{0}")."""
    for t in r.get("texts") or []:
        if "VALUE OF SALES" in (t or "").upper():
            return t
    return None


def ok_visible(r):
    return fst.ok_visible(r, SELL_OK)


def sel_all(gc):
    r = gc.cmd({"cmd": "sel_state"})
    return {"ok": r.get("ok"), "localSeat": r.get("localSeat"), "keys": r.get("keys"), "error": r.get("error")}


def sel(gc, key):
    """This machine's sel_state entry for key, None when absent (or the probe failed)."""
    k = sel_all(gc).get("keys")
    return k.get(key) if isinstance(k, dict) else None


def sel_rows(gc, key):
    e = sel(gc, key)
    return (e.get("rows") or {}) if isinstance(e, dict) else None


def stock(gc, item):
    """Base 0's stores count of item (geo_state; base 0 = HostBase, the shared base every row uses)."""
    bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
    return (bases[0].get("items") or {}).get(item, 0) if bases else None


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


def screen_ready(gc):
    """Top SellState and its list built (init() ran, F5573)."""
    if top(gc) != "SellState":
        return False
    r = rows(gc)
    return r.get("screen") is True and len(r.get("rows") or []) > 0


def roster(gc):
    """Base 0's soldiers (get_soldiers)."""
    b = gc.cmd({"cmd": "get_soldiers"}).get("bases") or []
    return (b[0].get("soldiers") or []) if b else []


def name_match(cell, name):
    """A Sell row's name cell for the soldier `name` (getName(true) may append "/<statString>" and shorten the name)."""
    if not isinstance(cell, str) or not isinstance(name, str):
        return False
    if cell == name:
        return True
    head = cell.split("/")[0]
    return "/" in cell and bool(head) and name.startswith(head)


def soldier_row(r, name):
    for i, row in enumerate(r.get("rows") or []):
        if row.get("item") == "" and name_match((row.get("cells") or [""])[0], name):
            return i
    return None


def view(gc):
    """One machine's end-of-row state for the EVIDENCE line."""
    r = rows(gc)
    return {"stack": stack(gc), "sel": sel_all(gc), "shared": sstats(gc),
            "screen": {"state": r.get("state"), "amounts": {k: v for k, v in amounts(r).items() if v},
                       "sales": sales_text(r), "okVisible": ok_visible(r)}}


def evidence(rid, obj):
    camp.evidence(rid, obj)


def capture(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's stack, sel_state, top screen rows, base 0 stock and roster, shared stats
    (whole), then raise."""
    cap = {}
    for gc in machines:
        try:
            cap[gc.name] = {"stack": stack(gc), "sel": sel_all(gc), "screen": rows(gc, autosell=[T], recovered=[T]),
                            "geo": {"bases0items": ((gc.ok({"cmd": "geo_state"}).get("bases") or [{}])[0]
                                                    .get("items"))},
                            "roster0": roster(gc), "shared": sstats(gc), "dialog": fst.dialog(gc),
                            "battleEnd": camp.record(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


def poll(fn, timeout, interval=0.2):
    """Poll fn() -> (done, value) until done or timeout; returns (done, value, secs)."""
    t0, last = time.time(), None
    while True:
        done, last = fn()
        if done:
            return True, last, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, last, round(time.time() - t0, 2)
        time.sleep(interval)


def wait_amount(gc, item, want, timeout=SEL_S):
    return poll(lambda: (lambda a: (a == want, a))(amount(gc, item)), timeout)


def settled_stock(host, client, item, timeout=EQUAL_S):
    """Poll until both machines report the same base-0 stock of item; returns (ok, {host, client}, secs)."""
    return poll(lambda: (lambda h, c: (h == c and h is not None, {"host": h, "client": c}))(stock(host, item),
                                                                                         stock(client, item)),
                timeout)


# ===================== fixtures =====================


def sel_pre(js, ctx):
    """SEL pre-cell: the first base-0 soldier owned by seat 1, off its craft on both (host craft_assign {on: false})."""
    host, client = js.host, js.client
    m = (host, client)
    own = [s for s in roster(host) if s.get("owner") == 1 and not s.get("dead")]
    if not own:
        capture("SEL client soldier", f"no base-0 soldier owned by seat 1 (host roster {roster(host)})", m)
    s = own[0]
    ctx["soldier"] = {"id": s.get("id"), "name": s.get("name"), "craftId": s.get("craftId"), "craft": s.get("craft")}
    if s.get("craftId", -1) != -1:
        r = host.cmd({"cmd": "craft_assign", "craft_id": s["craftId"], "soldier_id": s["id"], "on": False})
        ctx["soldier"]["unassign"] = {k: r.get(k) for k in ("ok", "error")}

    def off():
        v = {}
        for gc in m:
            hit = [x for x in roster(gc) if x.get("id") == s["id"]]
            v[gc.name] = hit[0].get("craftId") if hit else "absent"
        return all(c == -1 for c in v.values()), v
    ok, v, secs = poll(off, OFF_CRAFT_S, 0.5)
    ctx["soldier"]["offCraft"] = {"ok": ok, "craftId": v, "secs": secs}
    if not ok:
        capture("SEL soldier off craft", f"soldier {s['id']} craftId (host, client) {v} after {OFF_CRAFT_S}s", m)


def fxst_pre(js, ctx):
    """FXST pre-cell: set_autosell {T, on} on both (client first) before the battle, fst.fx_st (FX-ST, boot 2's T
    pins), then screen_rows {autosell: [T]} true on both after the client's adoption."""
    host, client = js.host, js.client
    m = (host, client)
    sa = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "set_autosell", "item": T, "on": True})
        sa[gc.name] = {k: r.get(k) for k in ("ok", "item", "autosell", "error")}
    ctx["setAutosell"] = sa
    if not all(v.get("ok") and v.get("autosell") is True for v in sa.values()):
        capture("FXST set_autosell", f"set_autosell {T} on answered {sa} (want autosell True on both)", m)
    fst.fx_st(js, ctx, "ST2")
    a = {gc.name: p3.autosell(gc, [T]).get(T) for gc in m}
    ctx["autosellAfterAdoption"] = a
    if not all(v is True for v in a.values()):
        capture("FXST autosell", f"screen_rows autosell[{T}] {a} after the client's adoption (want True on both)", m)


def row_start(host, client, ctx, stage_items=True):
    """SEL row hygiene: holds off, boxes dismissed, every Sell screen cancelled (both back on GeoscapeState); X and Y
    restaged on both (client first); open_screen sell on both, ready. A miss is a FIXTURE-STOP (CAPTURE)."""
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
            elif t == "SellState":
                h["cancelled"].append(f"{gc.name}:{click(gc, CANCEL)}")
                wait_until(lambda gc=gc: top(gc) != "SellState", PAGE_S)
                busy = True
        if not busy and time.time() - t0 > 0.6:
            break
        time.sleep(0.2)
    h["stacks"] = {gc.name: stack(gc) for gc in m}
    ctx["start"] = h
    if not all(top(gc) == "GeoscapeState" for gc in m):
        capture("row start", f"not both on GeoscapeState after the hygiene (stacks {h['stacks']})", m)
    if stage_items:
        give = {}
        for item in (X, Y):
            for gc in (client, host):   # client first (F607)
                r = gc.cmd({"cmd": "give_items", "item": item, "count": STAGE})
                give[f"{gc.name}:{item}"] = {k: r.get(k) for k in ("ok", "stored", "error")}
        ctx["give"] = give
        bad = [k for k, v in give.items() if not v.get("ok")]
        if bad or any(give[f"host:{i}"].get("stored") != give[f"client:{i}"].get("stored") for i in (X, Y)):
            capture("row give_items", f"answered {give}", m)
    opened = {}
    for gc in (host, client):
        r = gc.cmd({"cmd": "open_screen", "screen": "sell"})
        opened[gc.name] = {k: r.get(k) for k in ("ok", "error")}
    ok, secs = wait_until(lambda: screen_ready(host) and screen_ready(client), PAGE_S)
    ctx["open"] = {"resp": opened, "ready": ok, "secs": secs}
    if not ok:
        capture("row open_screen sell", f"both SellStates not ready within {PAGE_S}s ({opened}; stacks "
                f"{[stack(gc) for gc in m]})", m)
    ctx["stock0"] = {gc.name: {X: stock(gc, X), Y: stock(gc, Y)} for gc in m}


def set_ok(gc, value, ctx, key, item=None, row=None):
    a = set_amount(gc, value, item=item, row=row)
    ctx[key] = a
    return [] if a.get("ok") and a.get("after") == value else [
        f"{gc.name} screen_set_amount {item if item else 'row %s' % row} {value}: {a}"]


def cross(gc, item, want, ctx, key, timeout=SEL_S):
    ok, got, secs = wait_amount(gc, item, want, timeout)
    ctx[key] = {"want": want, "got": got, "ok": ok, "secs": secs}
    return [] if ok else [f"{gc.name}'s {item} amount {got} {timeout}s after the other machine's edit (want {want})"]


def gone(gc, ctx, key, timeout=PAGE_S, cls="SellState"):
    ok, secs = wait_until(lambda: top(gc) != cls, timeout, 0.1)
    ctx[key] = {"ok": ok, "secs": secs, "stack": stack(gc)}
    return [] if ok else [f"{gc.name}'s {cls} still on top {timeout}s later (stack {stack(gc)})"]


def stays_rebuilt(gc, item, total, ctx, key, timeout=SCREEN_S):
    """gc's top stays SellState while the world changes and its list is rebuilt: item's remaining + amount == total
    (the new stock). Returns the failures; ctx[key] holds the tops seen and the rebuilt row."""
    tops = []

    def rebuilt():
        t = top(gc)
        if t not in tops:
            tops.append(t)
        if t != "SellState":
            return False, None
        rem, amt = row_of(rows(gc), item)
        return (rem is not None and amt is not None and rem + amt == total), (rem, amt)
    ok, last, secs = poll(rebuilt, timeout)
    ctx[key] = {"ok": ok, "tops": tops, "row": last, "secs": secs}
    f = [] if ok else [f"{gc.name}'s SellState not rebuilt with {item} total {total} within {timeout}s (row {last}, "
                       f"tops {tops})"]
    if tops != ["SellState"]:
        f.append(f"{gc.name}'s top left SellState while the world changed (tops {tops}; want it rebuilt, not popped)")
    return f


def no_box(host, client, ctx, key):
    cs = [gc.name for gc in (host, client) if not no_coopstate(gc)]
    ctx[key] = {gc.name: stack(gc) for gc in (host, client)}
    return [f"a CoopState on {cs}'s stack"] if cs else []


# ===================== SEL rows =====================


def e_a_cells(host, client, ctx):
    def c1():
        row_start(host, client, ctx)
        return set_ok(client, 3, ctx, "c1set", item=X) or cross(host, X, 3, ctx, "c1host")

    def c2():
        return set_ok(host, 2, ctx, "c2set", item=Y) or cross(client, Y, 2, ctx, "c2client")

    def c3():
        want = {f"i:{X}": 3, f"i:{Y}": 2}
        last = {}

        def same():
            last.update({gc.name: sel(gc, SEL_KEY) for gc in (host, client)})
            h, c = last["host"] or {}, last["client"] or {}
            return (h.get("rows") == want and c.get("rows") == want and h.get("rev") == c.get("rev")
                    and h.get("viewers") == [0, 1] and c.get("viewers") == [0, 1]), dict(last)
        ok, got, secs = poll(same, SEL_S)
        ctx["c3sel"] = {"ok": ok, "sel": got, "secs": secs}
        f = [] if ok else [f"sel_state {SEL_KEY} (host, client) {got} (want rows {want}, equal rev, viewers [0, 1])"]
        sales = {gc.name: sales_text(rows(gc)) for gc in (host, client)}
        ctx["c3sales"] = sales
        if not (sales["host"] and sales["host"] == sales["client"]):
            f.append(f"the screens' Value of Sales texts {sales} (want equal)")
        return f
    return [
        ("1 the client's X edit reaches the host's screen", c1),
        ("2 the host's Y edit reaches the client's screen", c2),
        ("3 one store on both: rows, rev, viewers; equal sale values", c3),
    ]


def e_e_cells(host, client, ctx):
    def c1():
        row_start(host, client, ctx)
        return set_ok(client, 3, ctx, "c1x", item=X) or set_ok(client, 2, ctx, "c1y", item=Y)

    def c2():
        s0 = stock(host, X)
        r = host.cmd({"cmd": "sell", "item": X, "count": s0 - 2})
        ctx["c2sell"] = {"stock0": s0, "count": s0 - 2, "resp": {k: r.get(k) for k in ("ok", "sent", "error")}}
        if not (r.get("ok") and r.get("sent")):
            return [f"host sell {X} {s0 - 2}: {ctx['c2sell']}"]
        f = stays_rebuilt(client, X, 2, ctx, "c2rebuilt")
        if f:
            return f
        ok, a, secs = poll(lambda: (lambda r2: (lambda v: (v == {X: 2, Y: 2}, v))({X: row_of(r2, X)[1],
                                                                                    Y: row_of(r2, Y)[1]}))(rows(client)),
                           SEL_S)
        ctx["c2amounts"] = {"ok": ok, "amounts": a, "secs": secs}
        return [] if ok else [f"the client's rebuilt amounts {a} {SEL_S}s after the rebuild (want {X} 2 (clamped to "
                              f"its stock 2) and {Y} 2 (survived), F2161)"]

    def c3():
        return cross(host, X, 2, ctx, "c3x") + cross(host, Y, 2, ctx, "c3y")
    return [
        ("1 the client's local amounts X 3, Y 2", c1),
        ("2 the host's lever sale rebuilds the client's screen; its amounts survive, clamped", c2),
        ("3 the host's screen shows the same amounts", c3),
    ]


def e_c_cells(host, client, ctx):
    def c1():
        row_start(host, client, ctx)
        ctx["before"] = {gc.name: stock(gc, X) for gc in (host, client)}
        f = set_ok(client, E_C_CLIENT, ctx, "c1set", item=X)
        if f:
            return f
        seen, rv, secs = poll(lambda: (lambda r: (bool(r) and r.get(f"i:{X}") == E_C_CLIENT, r))(sel_rows(host, SEL_KEY)),
                              SEL_S)
        ctx["c1hostSel"] = {"seen": seen, "rows": rv, "secs": secs}   # EVIDENCE only (never a failed cell)
        ctx["c1hold"] = hold(host, True)
        if ctx["c1hold"] is not True:
            return [f"host shared_update_defer on answered deferred={ctx['c1hold']!r}"]
        f = set_ok(host, E_C_HOST, ctx, "c1hostSet", item=X)
        if f:
            hold(host, False)
            return f
        ctx["c1click"] = click(client, SELL_OK)
        return []

    def c2():
        ctx["c2release"] = hold(host, False)
        f = gone(client, ctx, "c2gone") + no_box(host, client, ctx, "c2stacks")
        if f:
            return f
        ok, st, secs = settled_stock(host, client, X)
        want = ctx["before"]["host"] - E_C_HOST
        ctx["c2stock"] = {"ok": ok, "stock": st, "want": want, "secs": secs}
        if not (ok and st["host"] == want and st["client"] == want):
            return [f"X stock (host, client) {st} after the confirm (want before {ctx['before']} - {E_C_HOST} = {want} "
                    f"on both: the host applies its current list, D203)"]
        ok, r, secs = poll(lambda: (lambda rr: (screen_ready(host) and all_zero(rr), amounts(rr)))(rows(host)),
                           SCREEN_S)
        ctx["c2host"] = {"ok": ok, "amounts": r, "top": top(host), "secs": secs}
        return [] if ok else [f"the host's top {top(host)} amounts {r} (want SellState, every amount 0, D204)"]
    return [
        ("1 client X 1; host held; host X 5; the client confirms", c1),
        ("2 released: the client's screen closes; the host applied its current list (5); host amounts 0", c2),
    ]


def e_d_cells(host, client, ctx):
    def c1():
        row_start(host, client, ctx)
        ctx["before"] = {gc.name: stock(gc, X) for gc in (host, client)}
        f = set_ok(client, 2, ctx, "c1client", item=X) or set_ok(host, 2, ctx, "c1host", item=X)
        if f:
            return f
        ctx["c1hold"] = hold(client, True)
        if ctx["c1hold"] is not True:
            return [f"client shared_update_defer on answered deferred={ctx['c1hold']!r}"]
        ctx["c1click"] = click(host, SELL_OK)
        f = gone(host, ctx, "c1hostGone")
        ctx["tChange"] = time.time()
        if f:
            hold(client, False)
        return f

    def c2():
        ctx["c2click"] = click(client, SELL_OK)
        ctx["c2release"] = hold(client, False)
        ctx["heldAfterChangeS"] = round(time.time() - ctx["tChange"], 2)
        f = gone(client, ctx, "c2gone") + no_box(host, client, ctx, "c2stacks")
        if f:
            return f
        ok, st, secs = settled_stock(host, client, X)
        want = ctx["before"]["host"] - 2
        ctx["c2stock"] = {"ok": ok, "stock": st, "want": want, "secs": secs}
        if not (ok and st["host"] == want and st["client"] == want):
            return [f"X stock (host, client) {st} after both confirms (want before {ctx['before']} - 2 = {want} on both: "
                    f"one sale, MR8)"]
        ok, s, secs = poll(lambda: (lambda x: (x.get("lastFail") == SEL_DUP, x))(sstats(client)), ANSWER_S)
        ctx["c2stats"] = {"ok": ok, "stats": s, "secs": secs}
        return [] if ok else [f"the client's shared_stats {s} (want lastFail {SEL_DUP!r}, PR-45)"]
    return [
        ("1 both at X 2; client held; the host confirms and its screen closes", c1),
        ("2 the client's duplicate confirm: one sale, no box, coop_sel_dup", c2),
    ]


def e_b_cells(host, client, ctx):
    sold = ctx["pre"]["soldier"] if "soldier" in ctx.get("pre", {}) else ctx["boot"]["soldier"]

    def c1():
        row_start(host, client, ctx)
        f = set_ok(client, 1, ctx, "c1y", item=Y)
        if f:
            return f
        idx = soldier_row(rows(client), sold["name"])
        ctx["c1soldierRow"] = idx
        if idx is None:
            return [f"the client's SellState lists no row for its soldier {sold['name']!r} (id {sold['id']})"]
        f = set_ok(client, 1, ctx, "c1s", row=idx)
        if f:
            return f
        hr = rows(host)
        hidx = soldier_row(hr, sold["name"])
        ctx["c1hostRow"] = hidx
        if hidx is not None:
            return [f"the host's SellState lists the client's soldier {sold['name']!r} (row {hidx}; want none, MR7)"]
        want = {f"s:{sold['id']}": 1, f"i:{Y}": 1}
        ok, got, secs = poll(lambda: (lambda r: (r == want, r))(sel_rows(host, SEL_KEY)), SEL_S)
        ctx["c1hostSel"] = {"ok": ok, "rows": got, "secs": secs}
        return [] if ok else [f"the host's sel_state {SEL_KEY} rows {got} (want {want})"]

    def c2():
        y0 = {gc.name: stock(gc, Y) for gc in (host, client)}
        ctx["c2click"] = click(host, SELL_OK)
        f = gone(host, ctx, "c2hostGone")
        if f:
            return f
        f = stays_rebuilt(client, Y, y0["client"] - 1, ctx, "c2rebuilt")
        if f:
            return f
        ok, a, secs = poll(lambda: (lambda r: (all_zero(r), amounts(r)))(rows(client)), SEL_S)
        ctx["c2clientAmounts"] = {"ok": ok, "amounts": {k: v for k, v in (a or {}).items() if v}, "secs": secs}
        if not ok:
            return [f"the client's rebuilt amounts {ctx['c2clientAmounts']['amounts']} (want every amount 0, D204)"]
        ok, st, secs = settled_stock(host, client, Y)
        ctx["c2stock"] = {"ok": ok, "stock": st, "before": y0, "secs": secs}
        if not (ok and st["host"] == y0["host"] - 1 and st["client"] == y0["client"] - 1):
            return [f"Y stock {y0} -> {st} (want -1 on both)"]
        ok, v, secs = poll(lambda: (lambda h, c: (not h and not c, {"host": h, "client": c}))(
            [s for s in roster(host) if s.get("id") == sold["id"]], [s for s in roster(client) if s.get("id") == sold["id"]]),
            EQUAL_S)
        ctx["c2soldier"] = {"ok": ok, "left": v, "secs": secs}
        if not ok:
            return [f"soldier {sold['id']} still in base 0 {v} (want sacked on both, MR7: the client's row rode the "
                    f"host's confirm)"]
        return no_box(host, client, ctx, "c2stacks")
    return [
        ("1 the client's Y 1 and own soldier row reach the host's store; the host's list hides the soldier (MR7)", c1),
        ("2 the host confirms the shared list: Y -1, the client's soldier sacked, the client's screen rebuilt at 0", c2),
    ]


def e_f_cells(host, client, ctx):
    def c1():
        row_start(host, client, ctx)
        return set_ok(client, 1, ctx, "c1set", item=X) or cross(host, X, 1, ctx, "c1host")

    def c2():
        ctx["c2click"] = click(client, CANCEL)
        f = gone(client, ctx, "c2gone")
        if f:
            return f
        want = {f"i:{X}": 1}
        ok, got, secs = poll(lambda: (lambda e: (isinstance(e, dict) and e.get("viewers") == [0]
                                                 and e.get("rows") == want, e))(sel(host, SEL_KEY)), SEL_S)
        ctx["c2hostSel"] = {"ok": ok, "sel": got, "secs": secs}
        if not ok:
            return [f"the host's sel_state {SEL_KEY} {got} after the client's Cancel (want viewers [0], rows {want})"]
        a = amount(host, X)
        ctx["c2hostX"] = a
        return [] if a == 1 else [f"the host's X amount {a} after the client left (want 1: the list stays)"]

    def c3():
        ctx["c3click"] = click(host, CANCEL)
        f = gone(host, ctx, "c3gone")
        if f:
            return f
        ok, got, secs = poll(lambda: (lambda h, c: (h is None and c is None, {"host": h, "client": c}))(
            sel(host, SEL_KEY), sel(client, SEL_KEY)), SEL_S)
        ctx["c3sel"] = {"ok": ok, "sel": got, "secs": secs}
        return [] if ok else [f"sel_state {SEL_KEY} {got} after the last viewer left (want the key absent on both)"]

    def c4():
        r = client.cmd({"cmd": "open_screen", "screen": "sell"})
        ok, secs = wait_until(lambda: screen_ready(client), PAGE_S)
        ctx["c4open"] = {"resp": {k: r.get(k) for k in ("ok", "error")}, "ready": ok, "secs": secs}
        if not ok:
            return [f"the client's reopened SellState not ready within {PAGE_S}s (stack {stack(client)})"]
        rr = rows(client)
        ctx["c4amounts"] = {k: v for k, v in amounts(rr).items() if v}
        if not all_zero(rr):
            return [f"the client's reopened amounts {ctx['c4amounts']} (want every amount 0)"]
        ok, got, secs = poll(lambda: (lambda h, c: (all(isinstance(e, dict) and e.get("rows") == {} and
                                                        e.get("viewers") == [1] for e in (h, c)),
                                                    {"host": h, "client": c}))(sel(host, SEL_KEY), sel(client, SEL_KEY)),
                             SEL_S)
        ctx["c4sel"] = {"ok": ok, "sel": got, "secs": secs}
        return [] if ok else [f"sel_state {SEL_KEY} {got} after the reopen (want rows {{}} viewers [1] on both)"]
    return [
        ("1 the client's X 1 reaches the host", c1),
        ("2 the client leaves: the host keeps the list", c2),
        ("3 the host leaves: the key is gone on both", c3),
        ("4 a lone reopen starts at zero", c4),
    ]


# ===================== FXST rows =====================


def fxst_hygiene(host, client, ctx):
    """Holds off, boxes dismissed, every Sell screen cancelled back to the debriefing (rows sharing a boot)."""
    fst.hygiene(host, client, ctx)
    ctx["backToDebrief"] = {gc.name: p3.back_to_debrief(gc) for gc in (host, client)}


def e_p_cells(host, client, ctx):
    def c1():
        fxst_hygiene(host, client, ctx)
        if not p3.to_page2(client):
            return [f"the client's debriefing did not reach page 2 (stack {stack(client)})"]
        f = p3.open_screen(client, "SELL", "SellState", ctx, "c1open")
        if f:
            return f
        ok, _s = wait_until(lambda: screen_ready(client), PAGE_S)
        rem, amt = row_of(rows(client), T)
        ctx["c1clientT"] = {"remaining": rem, "amount": amt, "ready": ok}
        if amt != T_QTY:
            return [f"the client's page-3 {T} amount {amt} (want {T_QTY}: vanilla's autosell pre-fill, SellState :279)"]
        want = {f"i:{T}": T_QTY}
        ok, got, secs = poll(lambda: (lambda r: (r == want, r))(sel_rows(host, PAGE3_KEY)), SEL_S)
        ctx["c1hostSel"] = {"ok": ok, "rows": got, "secs": secs}
        return [] if ok else [f"the host's sel_state {PAGE3_KEY} rows {got} (want {want}: the lone opener's pre-fill "
                              f"seeds the list, Q-P8-2 (a))"]

    def c2():
        f = set_ok(client, E_P_SET, ctx, "c2set", item=T)
        if f:
            return f
        if not p3.to_page2(host):
            return [f"the host's debriefing did not reach page 2 (stack {stack(host)})"]
        f = p3.open_screen(host, "SELL", "SellState", ctx, "c2hostOpen")
        if f:
            return f
        return cross(host, T, E_P_SET, ctx, "c2hostT")

    def c3():
        ctx["c3click"] = click(host, SELL_OK)
        f = gone(host, ctx, "c3hostGone")
        if f:
            return f
        f = stays_rebuilt(client, T, T_QTY - E_P_SET, ctx, "c3rebuilt")
        if f:
            return f
        ok, ra, secs = poll(lambda: (lambda v: (v == (T_QTY - E_P_SET, 0), v))(row_of(rows(client), T)), SEL_S)
        ctx["c3clientT"] = {"ok": ok, "remainingAmount": ra, "secs": secs}
        if not ok:
            return [f"the client's rebuilt page-3 {T} (remaining, amount) {ra} (want ({T_QTY - E_P_SET}, 0))"]
        f = p3.count_is((host, client), T, T_QTY - E_P_SET, ctx, "c3count")
        a = {gc.name: p3.autosell(gc, [T]).get(T) for gc in (host, client)}
        ctx["c3autosell"] = a
        if any(v is not False for v in a.values()):
            f.append(f"autosell[{T}] {a} (want False on both: {E_P_SET} of {T_QTY} sold)")
        return f
    return [
        ("1 the client's pre-filled page-3 list seeds the host's store", c1),
        ("2 the client's edit is what the host's page-3 Sell opens with", c2),
        ("3 the host confirms the shared list; the client's page 3 rebuilt", c3),
    ]


def clear_n(b):
    """The fewest rifles whose sale clears the base: Base::storesOverfull(offset) = (int)((used + offset) * 100) >
    (int)(available * 100), offset = -(n * 0.2) (SellState::changeByValue's _spaceChange)."""
    used, cap = b.get("usedStores"), b.get("availableStores")
    if not isinstance(used, (int, float)) or not isinstance(cap, (int, float)):
        return None
    n, capacity = 0, int(cap * 100)
    while int((used + (-(n * RIFLE_SIZE))) * 100) > capacity and n < 100000:
        n += 1
    return n


def e_s_cells(host, client, ctx):
    def c1():
        fxst_hygiene(host, client, ctx)
        f = fst.both_oks_forced(host, client, ctx, "c1", "SellState", STORAGE_MARK, fst.storage_record)
        if f:
            return f
        f = fst.boxes_to_screens(host, client, ctx, "c1boxes", "SellState")
        if f:
            return f
        b = fst.base0(host)
        n = clear_n(b)
        rem, amt = row_of(rows(client), RIFLE)
        ctx["c1n"] = {"used": b.get("usedStores"), "available": b.get("availableStores"), "N": n,
                      "clientRifle": [rem, amt]}
        ctx["N"] = n
        if not (isinstance(n, int) and n >= 2 and isinstance(rem, int) and rem >= n):
            return [f"N {n} from the host's base {ctx['c1n']} (want 2 <= N <= the client's listed rifles {rem})"]
        return []

    def c2():
        n = ctx["N"]
        f = set_ok(client, n - 1, ctx, "c2set", item=RIFLE)
        if f:
            return f
        if ctx["c2set"].get("okVisible") is not False:
            return [f"the client's {SELL_OK} visible={ctx['c2set'].get('okVisible')!r} at Rifle {n - 1} (want False: "
                    f"still over by one rifle)"]
        f = cross(host, RIFLE, n - 1, ctx, "c2host")
        if f:
            return f
        v = ok_visible(rows(host))
        ctx["c2hostOk"] = v
        return [] if v is False else [f"the host's {SELL_OK} visible={v!r} at Rifle {n - 1} (want False)"]

    def c3():
        n = ctx["N"]
        f = set_ok(host, n, ctx, "c3set", item=RIFLE)
        if f:
            return f
        if ctx["c3set"].get("okVisible") is not True:
            return [f"the host's {SELL_OK} visible={ctx['c3set'].get('okVisible')!r} at Rifle {n} (want True)"]
        ok, v, secs = poll(lambda: (lambda x: (x is True, x))(ok_visible(rows(client))), SEL_S)
        ctx["c3clientOk"] = {"ok": ok, "visible": v, "secs": secs}
        if not ok:
            return [f"the client's {SELL_OK} visible={v!r} {SEL_S}s after the host's Rifle {n} (want True)"]
        ctx["c3click"] = click(client, SELL_OK)
        ok, secs = wait_until(lambda: top(host) == "GeoscapeState" and top(client) == "GeoscapeState", SCREEN_S)
        ctx["c3closed"] = {"ok": ok, "secs": secs, "stacks": {gc.name: stack(gc) for gc in (host, client)}}
        if not ok:
            return [f"the forced SellStates did not both close themselves within {SCREEN_S}s (stacks "
                    f"{ctx['c3closed']['stacks']})"]
        return p3.world_same(host, client, ctx, "c3world") + no_box(host, client, ctx, "c3stacks")
    return [
        ("1 both OKs: both forced SellStates up; N from the host's base", c1),
        ("2 the client's Rifle N - 1 reaches the host's forced screen; still over on both", c2),
        ("3 the host's Rifle N clears it on both; the client's confirm closes both forced screens", c3),
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


def guard(host, client, crash0, ctx, last, battle):
    """Every row: no new crash log; a battle boot also host fatalVote.armed 0; the boot's last row: client zero-disk."""
    f = []
    if battle:
        armed = (event_state(host).get("fatalVote") or {}).get("armed")
        if armed != 0:
            f.append(f"host fatalVote.armed={armed!r} (want 0, F4544)")
    new_crash = sorted(session._crash_log_snapshot() - crash0)
    ctx["newCrashLogs"] = new_crash
    if new_crash:
        f.append(f"new crash log(s): {new_crash}")
    if last:
        try:
            session.assert_client_zero_disk(client.user_dir)
        except AssertionError as e:
            f.append(str(e))
    return f


def bring_up_sel(tag, port):
    return shared_fixture.bring_up(tag, (0, 0, port))


def bring_up_fxst(tag, port):
    return fst.bring_up(tag, port, OPTS_FXST)


def run_boot(boot, tag, up_fn, pre_fn, rows_spec, battle, results, walls):
    """One boot: bring-up + pre_fn(js, pre) (pre-cell), then each row (EVIDENCE, PASS / FAIL)."""
    t0, js, pre = time.time(), None, {}
    crash0 = session._crash_log_snapshot()
    miss = None
    try:
        try:
            js = up_fn(tag, BOOT_PORT[boot])
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
                    print(f"[w2p7-sce1] release shared_update_defer: {short(e)}", flush=True)
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2p7-sce1] shutdown: {short(e)}", flush=True)
        walls[boot] = round(time.time() - t0, 1)


BOOTS = (("SEL", "w2p7sce1_sel", bring_up_sel, sel_pre,
          (("E-a", e_a_cells), ("E-e", e_e_cells), ("E-c", e_c_cells), ("E-d", e_d_cells), ("E-b", e_b_cells),
           ("E-f", e_f_cells)), False),
         ("FXST", "w2p7sce1_fxst", bring_up_fxst, fxst_pre, (("E-p", e_p_cells), ("E-s", e_s_cells)), True))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, up_fn, pre_fn, rows_spec, battle in BOOTS:
        run_boot(boot, tag, up_fn, pre_fn, rows_spec, battle, results, walls)
    order = [rid for _, _, _, _, rs, _ in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_selection: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
