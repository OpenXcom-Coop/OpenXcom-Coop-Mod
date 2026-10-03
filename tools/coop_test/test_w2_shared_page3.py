"""W2-P7 S-C-D1 - test_w2_shared_page3.py: the SHARED second player's debriefing page 3 (the recovered items) has live
Sell and Transfer buttons on the world it adopted in place, and the page-3 counts, the autosell marks and the hidden
buttons stay in step on both machines whoever sells (docs rewrite/prompts/w2p7_sc_design.md section 3.5, AMENDMENT
P7-7 sections 2-4: PR-22..PR-28, P7-7 Q2 (a); owner D154, D176; mechanism rulings MR1, MR14).

Before S-C-D1 (F2491, F2506, F5589): the client's display-only debriefing never shows Sell / Transfer (V3 fill forces
_showSellButton false and _base null), and a SHARED page-3 sale or transfer - the host's own included - returns
before vanilla's page-3 bookkeeping (decreaseRecoveredItemCount, setAutosell, hideSellTransferButtons), so the
page-3 counts never drop on either machine.

Fixture (AMENDMENT P7-7 section 3 FX-S / FX-B; P7-7 RULINGS R-D1-2): shared_fixture.bring_up(tag, (0, 0, PORT));
FX-B (boot 2 only) first builds a second shared base from the client (test_shared_equip_transfer :109's
build_new_base call) and waits for both machines to hold 2 bases, then (R-D1-2, F5688: a lift-only base has
availableStores 0 and vanilla refuses any item transfer to it) the host fac_builds STR_GENERAL_STORES next to the
lift, waits for both machines to list it and sets its buildTime 0 on BOTH (the FX-CT pattern); then
test_w2_battle_end_campaign.stage() (S-C-A's SHARED ending: SEED_S 1,
MAP_FP_S, the 15 hostiles killed, the host's debriefing == HOST_DEBRIEF: recovered Sectoid Corpse 10, Plasma Pistol
8, ...). Pre-cell (a failure is a FIXTURE-STOP: one CAPTURE line, then every row of the boot FAILs "pre-cell"): the
client's display-only DebriefingState on top and battleEnd.worldAdopted 1 within ADOPT_S (15 s, CONSTANTS T0-S2),
then both machines on page 2 (the recovered items: STATS -> LOOT through click_widget, debrief_state.page 2).

Probes and levers (PR-28): screen_rows (the top Sell / Transfer screen's rows; {autosell: [types]} the saved
autosell marks; {recovered: [types]} the topmost debriefing's page-3 remaining counts, getRecoveredItemCount - the
debriefing's own list widget is drawn once at init and never re-rendered, vanilla included, F5687), screen_set_amount,
screen_pick_base; every button press is a real click_widget on its caption (SELL, TRANSFER, Sell/Sack, Transfer, OK,
Cancel). "recovered[X]" below = screen_rows {recovered: [X]} (P7-7 RULINGS R-D1-1); "page-3 rows" = every type whose
recovered count is > 0, with that count; debrief_state.recovered (the widget) is compared nowhere.

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot 1 (port 47250): D1a, then D1b.
  D1a (1) both page 2: sellVisible true, transferVisible false.
      (2) the client's SELL -> top SellState; its screen_rows (name, qty) == its page-3 rows.
      (3) screen_set_amount {T, 3}, Sell/Sack -> the client's SellState gone within SCREEN_S; recovered[T] == 7 on both;
          world_diff empty; the host's funds increased and equal on both; autosell[T] false on both.
  D1b (1) the host's SELL -> screen_set_amount {U, 2} -> Sell/Sack: the HOST's recovered[U] == 6 within SCREEN_S.
      (2) the client's recovered[U] == 6.
      (3) the client's SELL, then the host's SELL selling its remaining U (6): the client's top stays SellState and its
          screen_rows lose the U row (rebuilt, not popped).
      (4) the client sets every remaining row to its qty, Sell/Sack: both page 2 sellVisible and transferVisible false;
          autosell true for every recovered type on both; world_diff empty.
  Boot 2 (port 47251, FX-B): D1c.
  D1c (0) guard (R-D1-2): "Second Base" availableStores > 0 on both machines.
      (1) both page 2: transferVisible true.
      (2) the client's TRANSFER -> TransferBaseState; screen_pick_base {0, 1} -> TransferItemsState, rows == page 3.
      (3) screen_set_amount {T, 4}, Transfer, OK -> top DebriefingState within SCREEN_S; recovered[T] == 6 on both;
          shared_checksum chkTransfers +1 on both; world_diff empty.
Guard on every row: host event_state.fatalVote.armed 0; no new crash log; the client zero-disk at the end.

RED (commit S-C-D1.1: probes, levers and rows, product untouched): D1a fails on cell 1 (the client's sellVisible
false), D1b on cell 1 (the host's recovered[U] stays 8, F2506 / F5589), D1c on cell 1 (the client's transferVisible
false). GREEN (commit S-C-D1.2): every row passes.
Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE
foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_page3.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import event_state
import shared_fixture
from harness import LAND_LON, LAND_LAT
import test_w2_battle_end_campaign as camp

# ----- pins (AMENDMENT P7-7 section 3 FX-S; S-C-A's HOST_DEBRIEF = docs rewrite/w2p7sc-task0/t0/CONSTANTS.md T0-6 (ii)) -----
T, U = "STR_SECTOID_CORPSE", "STR_PLASMA_PISTOL"       # FX-S: T and U (looked up by type, S25)
T_QTY, U_QTY = 10, 8                                   # camp.HOST_DEBRIEF recovered: Sectoid Corpse 10, Plasma Pistol 8
RECOVERED_TYPES = ["STR_PLASMA_RIFLE", "STR_PLASMA_RIFLE_CLIP", "STR_PLASMA_PISTOL", "STR_PLASMA_PISTOL_CLIP",
                   "STR_SMALL_LAUNCHER", "STR_STUN_BOMB", "STR_ALIEN_GRENADE", "STR_SECTOID_CORPSE"]  # HOST_DEBRIEF's 8 rows
D1A_SELL, D1B_SELL, D1C_XFER = 3, 2, 4                 # P7-7 section 3.1's amounts
BOOT_PORT = {"B1": "47250", "B2": "47251"}             # P7-7 section 3 (S26, F5582): D1 = 47250-47252
SECOND_BASE, LIFT_X, LIFT_Y = "Second Base", 3, 3      # FX-B: test_shared_equip_transfer :109's call
STORES, STORES_X, STORES_Y = "STR_GENERAL_STORES", 4, 3  # R-D1-2: next to the lift (3, 3); pinned by the D1 red's capture
ADOPT_S = camp.ADOPT_S  # 15 s (CONSTANTS T0-S2)
SCREEN_S = 10           # P7-7 section 3.1: "within 10 s"
PAGE_S = 5              # a debriefing page flip / a screen push after a real click
EQUAL_S = 10            # a shared_apply's effect may lag one round trip
BASES_S = 45            # FX-B: the second base on both machines (test_shared_equip_transfer's wait)


class FixtureMiss(Exception):
    pass


# ===================== probes =====================


def short(e, n=400):
    return camp.short(e, n)


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=0.25):
    return camp.wait_until(pred, timeout, interval)


def record(gc):
    return camp.record(gc)


def deb(gc):
    return gc.cmd({"cmd": "debrief_state"})


def rows(gc, **kw):
    req = {"cmd": "screen_rows"}
    req.update(kw)
    return gc.cmd(req)


def counts(gc, types):
    """recovered[type] for each type = the topmost debriefing's page-3 remaining count (screen_rows {recovered})."""
    return rows(gc, recovered=list(types)).get("recovered") or {}


def autosell(gc, types):
    return rows(gc, autosell=list(types)).get("autosell") or {}


def as_int(s):
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return None


def screen_view(r):
    """A screen_rows reply as [(name, qty)] - qty = the remaining column (cells[1])."""
    return [(row["cells"][0], as_int(row["cells"][1])) for row in (r.get("rows") or [])]


def funds(gc):
    return gc.ok({"cmd": "geo_state"}).get("funds")


def stock(gc, item, base=0):
    """Base <base>'s stores count of <item> (geo_state; base 0 = the debriefing's base, HostBase)."""
    bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
    return (bases[base].get("items") or {}).get(item, 0) if len(bases) > base else None


def second_base_stores(gc):
    r = gc.cmd({"cmd": "base_report", "base": SECOND_BASE})
    return r.get("availableStores") if r.get("ok") else None


def transfers_chk(gc):
    return gc.cmd({"cmd": "shared_checksum"}).get("chkTransfers")


def base_count(gc):
    return len(gc.ok({"cmd": "geo_state"}).get("bases") or [])


def rec_keys(gc):
    """The battleEnd record keys P7-7 names for the report (page3, worldAdoptDeferredPasses, forced, adoptFailed)."""
    r = record(gc)
    return {k: r.get(k) for k in ("page3", "worldAdoptDeferredPasses", "forced", "adoptFailed", "worldAdopted",
                                  "worldHeld", "returnPending")}


def view(gc):
    d = deb(gc)
    return {"stack": stack(gc), "record": rec_keys(gc),
            "debrief": {k: d.get(k) for k in ("shown", "onTop", "displayOnly", "page", "sellVisible",
                                              "transferVisible")}}


def click(gc, caption):
    r = gc.cmd({"cmd": "click_widget", "match": caption})
    return {k: r.get(k) for k in ("ok", "text", "error")}


def set_amount(gc, amount, item=None, row=None):
    req = {"cmd": "screen_set_amount", "amount": amount}
    if item is not None:
        req["item"] = item
    if row is not None:
        req["row"] = row
    r = gc.cmd(req)
    return {k: r.get(k) for k in ("ok", "row", "name", "before", "after", "okVisible", "topAfter", "error")}


def screen_up(gc, cls):
    """Top == cls and (for a Sell / Transfer screen) its widgets exist (init() ran, F5573)."""
    if top(gc) != cls:
        return False
    if cls in ("SellState", "TransferItemsState"):
        return rows(gc).get("screen") is True
    return True


def open_screen(gc, caption, cls, ctx, key):
    c = click(gc, caption)
    ok, secs = wait_until(lambda: screen_up(gc, cls), PAGE_S)
    ctx[key] = {"click": c, "up": ok, "secs": secs, "stack": stack(gc)}
    return [] if ok else [f"{gc.name} {caption!r} -> top {top(gc)!r} within {PAGE_S}s (want {cls}; click {c})"]


def to_page2(gc):
    """Flip this machine's debriefing to page 2 (the recovered items) with real clicks: STATS (page 0), LOOT (page 1)."""
    t0 = time.time()
    while time.time() - t0 < PAGE_S:
        d = deb(gc)
        if d.get("page") == 2 and d.get("onTop") is True:
            return True
        if d.get("onTop") is not True:
            return False
        cap = {0: "STATS", 1: "LOOT"}.get(d.get("page"))
        if cap:
            click(gc, cap)
        time.sleep(0.3)
    return deb(gc).get("page") == 2


def back_to_debrief(gc):
    """Row hygiene for a row that shares a boot: Cancel any Sell / Transfer screen this machine still shows."""
    for _ in range(3):
        t = top(gc)
        if t in ("SellState", "TransferItemsState", "TransferBaseState", "TransferConfirmState"):
            click(gc, "Cancel")
            wait_until(lambda: top(gc) != t, PAGE_S)
        else:
            break
    return top(gc) == "DebriefingState"


def world_same(host, client, ctx, key):
    last = {}

    def same():
        last["d"] = shared_fixture.world_diff(host, client)
        return not last["d"]
    ok, secs = wait_until(same, EQUAL_S, 0.5)
    ctx[key] = {"equal": ok, "secs": secs, "diff": (last.get("d") or [])[:20]}
    return [] if ok else [f"world_diff not empty after {EQUAL_S}s: {(last.get('d') or [])[:8]}"]


def count_is(gcs, item, want, ctx, key, timeout=SCREEN_S):
    """recovered[item] == want on every machine in gcs within timeout."""
    seen = {}

    def hit():
        for gc in gcs:
            seen[gc.name] = counts(gc, [item]).get(item)
        return all(v == want for v in seen.values())
    ok, secs = wait_until(hit, timeout)
    ctx[key] = {"want": want, "seen": dict(seen), "ok": ok, "secs": secs}
    return [] if ok else [f"recovered[{item}] {seen} after {timeout}s (want {want} on {[g.name for g in gcs]})"]


def evidence(rid, obj):
    camp.evidence(rid, obj)


def capture(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's stack, battleEnd record and debrief_state (whole), then raise."""
    cap = {}
    for gc in machines:
        try:
            cap[gc.name] = {"stack": stack(gc), "battleEnd": record(gc), "debrief": deb(gc),
                            "screen": rows(gc, recovered=RECOVERED_TYPES)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


# ===================== fixtures (pre-cell) =====================


def fx_b(js, ctx):
    """FX-B: the client builds a second shared base on the geoscape (test_shared_equip_transfer :109); both hold 2."""
    host, client = js.host, js.client
    r = client.cmd({"cmd": "build_new_base", "lon": LAND_LON, "lat": LAND_LAT, "name": SECOND_BASE,
                    "liftX": LIFT_X, "liftY": LIFT_Y})
    ctx["fxB"] = {"build": {k: r.get(k) for k in ("ok", "cost", "affordable", "error")}}
    if not r.get("ok"):
        capture("FX-B build_new_base", f"answered {ctx['fxB']['build']}", (host, client))
    ok, secs = wait_until(lambda: base_count(host) == 2 and base_count(client) == 2, BASES_S, 0.5)
    ctx["fxB"].update({"bases": [base_count(host), base_count(client)], "secs": secs})
    if not ok:
        capture("FX-B second base", f"base counts (host, client) {ctx['fxB']['bases']} after {BASES_S}s", (host, client))
    # R-D1-2 (F5688): General Stores next to the lift, host-built (SHARED: one fac_build shared_cmd applied on both),
    # then buildTime 0 on BOTH (FX-CT's set_facility_build_time pattern, F5434).
    fb = host.cmd({"cmd": "fac_build", "facility": STORES, "base": SECOND_BASE, "x": STORES_X, "y": STORES_Y})
    ctx["fxB"]["facBuild"] = {k: fb.get(k) for k in ("ok", "error")}

    def stores_index(gc):
        bases = gc.ok({"cmd": "geo_state"}).get("bases") or []
        facs = (bases[1].get("facilities") or []) if len(bases) > 1 else []
        hits = [i for i, f in enumerate(facs) if f.get("type") == STORES and f.get("x") == STORES_X
                and f.get("y") == STORES_Y]
        return hits[0] if hits else None
    ok, secs = wait_until(lambda: stores_index(host) is not None and stores_index(client) is not None, BASES_S, 0.5)
    idx = {gc.name: stores_index(gc) for gc in (host, client)}
    ctx["fxB"]["storesIndex"] = {"index": idx, "secs": secs}
    if not (fb.get("ok") and ok and idx["host"] == idx["client"]):
        capture("FX-B general stores", f"fac_build {ctx['fxB']['facBuild']}, stores index {idx} after {BASES_S}s",
                (host, client))
    sets = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "set_facility_build_time", "baseId": 1, "index": idx["host"], "time": 0})
        sets[gc.name] = {k: r.get(k) for k in ("ok", "type", "x", "y", "buildTime", "error")}
    ctx["fxB"]["buildTime0"] = sets
    if not all(s.get("ok") and s.get("type") == STORES and s.get("buildTime") == 0 for s in sets.values()):
        capture("FX-B stores buildTime", f"set_facility_build_time answered {sets}", (host, client))
    av = {gc.name: second_base_stores(gc) for gc in (host, client)}
    ctx["fxB"]["availableStores"] = av
    if not all(isinstance(v, (int, float)) and v > 0 for v in av.values()):
        capture("FX-B stores available", f"{SECOND_BASE} availableStores {av} (want > 0 on both)", (host, client))


def pre_cell(js, ctx, two_bases):
    """FX-S (+ FX-B), then the client's display-only debriefing adopted in place, then both on page 2."""
    host, client = js.host, js.client
    m = (host, client)
    if two_bases:
        fx_b(js, ctx)
    try:
        camp.stage("D1", js, ctx)
    except camp.FixtureMiss as e:
        raise FixtureMiss(f"camp.stage: {e}")
    ok, secs = wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                   and d.get("displayOnly") is True)(deb(client)), camp.CLIENT_DEBRIEF_S)
    ctx["clientDebrief"] = {"ok": ok, "secs": secs}
    if not ok:
        capture("client debriefing", f"no client display-only DebriefingState on top within {camp.CLIENT_DEBRIEF_S}s",
                m)
    ok, secs = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
    ctx["adopted"] = {"ok": ok, "secs": secs, "client": rec_keys(client)}
    if not ok:
        capture("client adoption", f"client battleEnd.worldAdopted != 1 within {ADOPT_S}s", m)
    p = {gc.name: to_page2(gc) for gc in m}
    ctx["page2"] = p
    if not all(p.values()):
        capture("page 2", f"debriefing page 2 reached {p}", m)
    ctx["start"] = {"host": view(host), "client": view(client), "counts": {"host": counts(host, RECOVERED_TYPES),
                                                                          "client": counts(client, RECOVERED_TYPES)}}


# ===================== cells =====================


def buttons(host, client, ctx, key, sell, transfer):
    """Both machines' page-2 Sell / Transfer visibility (debrief_state) == (sell, transfer)."""
    f, seen = [], {}
    for gc in (host, client):
        d = deb(gc)
        seen[gc.name] = {k: d.get(k) for k in ("page", "onTop", "sellVisible", "transferVisible")}
        if d.get("page") != 2:
            f.append(f"{gc.name} debrief_state.page={d.get('page')!r} (want 2)")
        if sell is not None and d.get("sellVisible") is not sell:
            f.append(f"{gc.name} sellVisible={d.get('sellVisible')!r} (want {sell})")
        if transfer is not None and d.get("transferVisible") is not transfer:
            f.append(f"{gc.name} transferVisible={d.get('transferVisible')!r} (want {transfer})")
    ctx[key] = seen
    return f


def rows_match_page3(gc, ctx, key):
    """The top screen's rows == this machine's page-3 rows (R-D1-1): exactly the types whose recovered count is > 0,
    each row's remaining qty == that count (screen_rows {recovered}, the debriefing below the screen)."""
    r = rows(gc, recovered=RECOVERED_TYPES)
    got = {row.get("item"): as_int(row["cells"][1]) for row in (r.get("rows") or [])}
    want = {t: n for t, n in (r.get("recovered") or {}).items() if isinstance(n, int) and n > 0}
    ctx[key] = {"screen": screen_view(r), "items": [row.get("item") for row in (r.get("rows") or [])],
                "recovered": r.get("recovered")}
    f = [] if got == want and len(got) == len(r.get("rows") or []) else [
        f"{gc.name} screen_rows {got} != its page-3 rows {want}"]
    return f


def sell_and_close(gc, item, amount, ctx, key, host=None):
    """screen_set_amount {item, amount}, then Sell/Sack: the SellState gone (top DebriefingState) within SCREEN_S.
    With `host`: the host's base-0 stock of <item> and funds around the sale (evidence: the sale applied)."""
    w0 = {"stock": stock(host, item), "funds": funds(host)} if host is not None else None
    a = set_amount(gc, amount, item=item)
    f = [] if a.get("ok") and a.get("after") == amount else [f"{gc.name} screen_set_amount {item} {amount}: {a}"]
    c = click(gc, "Sell/Sack") if not f else {}
    ok, secs = wait_until(lambda: top(gc) == "DebriefingState", SCREEN_S) if not f else (False, 0)
    ctx[key] = {"set": a, "click": c, "closed": ok, "secs": secs, "stack": stack(gc)}
    if host is not None:
        w1 = {}

        def moved():
            w1.update({"stock": stock(host, item), "funds": funds(host)})
            return w1["stock"] != w0["stock"]
        applied, asecs = wait_until(moved, EQUAL_S) if ok else (False, 0)
        ctx[key]["hostWorld"] = {"item": item, "before": w0, "after": w1, "applied": applied, "secs": asecs}
    if not f and not ok:
        f.append(f"{gc.name} SellState not closed within {SCREEN_S}s of Sell/Sack (stack {stack(gc)})")
    return f


def d1a_cells(host, client, ctx):
    def c2():
        return open_screen(client, "SELL", "SellState", ctx, "clientSell") or rows_match_page3(client, ctx, "clientRows")

    def c3():
        f0 = funds(host)
        f = sell_and_close(client, T, D1A_SELL, ctx, "clientSale", host=host)
        if f:
            return f
        f = count_is((host, client), T, T_QTY - D1A_SELL, ctx, "countT")
        f += world_same(host, client, ctx, "world")
        hf, cf = funds(host), funds(client)
        ctx["funds"] = {"before": f0, "host": hf, "client": cf}
        if not (isinstance(hf, int) and isinstance(f0, int) and hf > f0 and cf == hf):
            f.append(f"funds before {f0} host {hf} client {cf} (want the host's increased and equal on both)")
        a = {gc.name: autosell(gc, [T]).get(T) for gc in (host, client)}
        ctx["autosellT"] = a
        if any(v is not False for v in a.values()):
            f.append(f"autosell[{T}] {a} (want False on both: {D1A_SELL} of {T_QTY} sold)")
        return f
    return [
        ("1 both page 2: sellVisible true, transferVisible false",
         lambda: buttons(host, client, ctx, "buttons", True, False)),
        ("2 the client's page-3 SellState lists its page-3 rows", c2),
        ("3 the client's page-3 sale reaches both machines", c3),
    ]


def d1b_cells(host, client, ctx):
    def c1():
        ctx["hygiene"] = {gc.name: back_to_debrief(gc) and to_page2(gc) for gc in (host, client)}
        f = open_screen(host, "SELL", "SellState", ctx, "hostSell")
        if f:
            return f
        ctx["hostItems"] = [row.get("item") for row in (rows(host).get("rows") or [])]
        f = sell_and_close(host, U, D1B_SELL, ctx, "hostSale", host=host)
        return f or count_is((host,), U, U_QTY - D1B_SELL, ctx, "countUHost")

    def c3():
        f = open_screen(client, "SELL", "SellState", ctx, "clientSell2") or open_screen(host, "SELL", "SellState", ctx,
                                                                                        "hostSell2")
        if f:
            return f
        f = sell_and_close(host, U, U_QTY - D1B_SELL, ctx, "hostSale2", host=host)
        if f:
            return f
        tops = []

        def gone():
            t = top(client)
            if t not in tops:
                tops.append(t)
            return t == "SellState" and all(row.get("item") != U for row in (rows(client).get("rows") or []))
        ok, secs = wait_until(gone, SCREEN_S)
        ctx["clientRebuilt"] = {"ok": ok, "secs": secs, "tops": tops, "rows": screen_view(rows(client))}
        f = [] if ok else [f"the client's SellState still lists {U} after {SCREEN_S}s (tops {tops})"]
        if tops != ["SellState"]:
            f.append(f"the client's top left SellState while the host sold (tops {tops}; want rebuilt, not popped)")
        return f

    def c4():
        r = rows(client)
        sets = []
        for i, row in enumerate(r.get("rows") or []):
            want = (as_int(row["cells"][1]) or 0) + (as_int(row["cells"][2]) or 0)
            sets.append(set_amount(client, want, row=i))
        ctx["clientSetAll"] = sets
        f = [f"client screen_set_amount row {s.get('row')}: {s}" for s in sets if not s.get("ok")]
        if f or not sets:
            return f or ["the client's page-3 SellState lists no row"]
        c = click(client, "Sell/Sack")
        ok, secs = wait_until(lambda: top(client) == "DebriefingState", SCREEN_S)
        ctx["clientSaleAll"] = {"click": c, "closed": ok, "secs": secs}
        if not ok:
            return [f"the client's SellState not closed within {SCREEN_S}s (stack {stack(client)})"]
        ok, secs = wait_until(lambda: not buttons(host, client, {}, "x", False, False), SCREEN_S)
        f = buttons(host, client, ctx, "buttonsEnd", False, False)
        a = {gc.name: autosell(gc, RECOVERED_TYPES) for gc in (host, client)}
        ctx["autosellEnd"] = a
        for n, m in a.items():
            bad = {k: v for k, v in m.items() if v is not True}
            if bad or set(m) != set(RECOVERED_TYPES):
                f.append(f"{n} autosell {m} (want True for every recovered type)")
        return f + world_same(host, client, ctx, "worldEnd")
    return [
        ("1 the host's page-3 sale drops the host's own count", c1),
        ("2 the client's count follows", lambda: count_is((client,), U, U_QTY - D1B_SELL, ctx, "countUClient")),
        ("3 the client's open page-3 SellState rebuilds on the host's sale", c3),
        ("4 the client sells the rest: buttons hidden and autosell marks on both", c4),
    ]


def d1c_cells(host, client, ctx):
    def c0():
        av = {gc.name: second_base_stores(gc) for gc in (host, client)}
        ctx["secondBaseStores"] = av
        return [] if all(isinstance(v, (int, float)) and v > 0 for v in av.values()) else [
            f"{SECOND_BASE} availableStores {av} (want > 0 on both: R-D1-2 FIXTURE-STOP of D1c)"]

    def c2():
        f = open_screen(client, "TRANSFER", "TransferBaseState", ctx, "clientXferBase")
        if f:
            return f
        p = client.cmd({"cmd": "screen_pick_base", "from": 0, "to": 1})
        ok, secs = wait_until(lambda: screen_up(client, "TransferItemsState"), PAGE_S)
        ctx["pick"] = {"resp": {k: p.get(k) for k in ("ok", "debrief", "error")}, "up": ok, "secs": secs}
        if not (p.get("ok") and p.get("debrief") is True and ok):
            return [f"screen_pick_base {{0, 1}}: {ctx['pick']} (stack {stack(client)})"]
        return rows_match_page3(client, ctx, "clientXferRows")

    def c3():
        x0 = {gc.name: transfers_chk(gc) for gc in (host, client)}
        a = set_amount(client, D1C_XFER, item=T)
        ctx["xferSet"] = a
        if not (a.get("ok") and a.get("after") == D1C_XFER):
            return [f"client screen_set_amount {T} {D1C_XFER}: {a} (stack {stack(client)})"]
        f = open_screen(client, "Transfer", "TransferConfirmState", ctx, "xferConfirm")
        if f:
            return f
        c = click(client, "OK")
        ok, secs = wait_until(lambda: top(client) == "DebriefingState", SCREEN_S)
        ctx["xferOk"] = {"click": c, "closed": ok, "secs": secs, "stack": stack(client)}
        if not ok:
            return [f"the client's transfer screens not closed within {SCREEN_S}s (stack {stack(client)})"]
        f = count_is((host, client), T, T_QTY - D1C_XFER, ctx, "countT")
        x1 = {}

        def plus_one():
            for gc in (host, client):
                x1[gc.name] = transfers_chk(gc)
            return all(isinstance(x0[n], int) and x1[n] == x0[n] + 1 for n in x0)
        ok, secs = wait_until(plus_one, EQUAL_S)
        ctx["chkTransfers"] = {"before": x0, "after": x1, "ok": ok, "secs": secs}
        if not ok:
            f.append(f"shared_checksum chkTransfers {x0} -> {x1} (want +1 on both)")
        return f + world_same(host, client, ctx, "world")
    return [
        ("0 guard: the second base has store space on both (R-D1-2)", c0),
        ("1 both page 2: transferVisible true", lambda: buttons(host, client, ctx, "buttons", None, True)),
        ("2 the client's page-3 TransferItemsState lists its page-3 rows", c2),
        ("3 the client's page-3 transfer reaches both machines", c3),
    ]


# ===================== one boot =====================


def run_cells(rid, cells_fn, host, client, ctx):
    """The row's cells in order; returns the verdict (None = pass)."""
    cells = cells_fn(host, client, ctx)
    ctx["cells"] = []
    for i, (name, fn) in enumerate(cells):
        try:
            f = fn()
        except Exception as e:
            f = [f"{type(e).__name__}: {short(e, 600)}"]
        ctx["cells"].append({"cell": name, "pass": not f, "fails": f})
        if f:
            rest = [c[0].split(" ")[0] for c in cells[i + 1:]]
            return f"cell {name}: " + "; ".join(f) + (f" | cells {rest} not reached" if rest else "")
    return None


def guard(host, client, crash0, ctx, last):
    """Every row: host fatalVote.armed 0, no new crash log; the boot's last row: the client zero-disk."""
    f = []
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


def run_boot(boot, tag, rows_spec, two_bases, results, walls):
    """One boot: bring-up + pre-cell, then each row (EVIDENCE, PASS / FAIL)."""
    t0, js, pre = time.time(), None, {}
    crash0 = session._crash_log_snapshot()
    miss = None
    try:
        try:
            js = shared_fixture.bring_up(tag, (0, 0, BOOT_PORT[boot]))
            pre_cell(js, pre, two_bases)
        except Exception as e:
            miss = f"pre-cell (FIXTURE-STOP) {e if isinstance(e, FixtureMiss) else short(e, 800)}"
        for n, (rid, cells_fn) in enumerate(rows_spec):
            tr = time.time()
            ctx = {"row": rid, "boot": boot, "pre": pre if n == 0 else {"see": rows_spec[0][0]}}
            verdict = miss
            if verdict is None:
                verdict = run_cells(rid, cells_fn, js.host, js.client, ctx)
                g = guard(js.host, js.client, crash0, ctx, n == len(rows_spec) - 1)
                if g:
                    verdict = (verdict + " | " if verdict else "") + "guard: " + "; ".join(g)
                try:
                    ctx["end"] = {"host": view(js.host), "client": view(js.client)}
                except Exception as e:
                    ctx["end"] = f"probe failed: {short(e)}"
            ctx["wall"] = round(time.time() - tr, 1)
            evidence(rid, ctx)
            results[rid] = verdict is None
            print(f"PASS {rid}" if verdict is None else f"FAIL {rid}: {verdict}", flush=True)
    finally:
        if js is not None:
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2p7-scd1] shutdown: {short(e)}", flush=True)
        walls[boot] = round(time.time() - t0, 1)


BOOTS = (("B1", "w2p7scd1_b1", (("D1a", d1a_cells), ("D1b", d1b_cells)), False),
         ("B2", "w2p7scd1_b2", (("D1c", d1c_cells),), True))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, rows_spec, two_bases in BOOTS:
        run_boot(boot, tag, rows_spec, two_bases, results, walls)
    order = [rid for _, _, rs, _ in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_page3: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
