"""W2-P7 S-C-E2 - test_w2_shared_selection_presence.py: on a SHARED Sell screen each player sees "Also on this screen:
<the other player>" while both have it open, the rows the other player changed last are drawn in the screen's second
button colour, a confirm whose confirmer sees none of the list's rows (the other player's soldier row, MR7) still
applies the list, a player who disconnects leaves the list, and the forced Alien Containment screen is shared by both
players after a battle (owner D184 (a), D203: "as if both players were sitting at the same computer looking at the
same screen"; D175, MR7, MR9; V-E3, V-E4) (docs rewrite/prompts/w2p7_sc_design.md section 4, AMENDMENT P7-8 sections
3-4: PR-47..PR-51; the E1 green rulings: F6341 folded into S-C-E2). D243 (owner 2026-10-05): the label sits just above
the OK/Cancel buttons while another player has the same screen open; in a SHARED campaign the Sell list is ALWAYS one
text row shorter (the label's row), with or without the other player - row E2-gs (commit S-C-E2.1b).

Before S-C-E2 (design section 4, F6110, F6341): no label is drawn and a row's colour is vanilla's (secondary while its
amount is above 0, whoever set it); a Sell confirm is built from the confirmer's VISIBLE rows (SellState :725), so a
list holding only the other player's soldier row submits nothing; the host keeps a disconnected client among a
list's viewers (its close never leaves: disconnect_to_menu drops the transport first, F6110); the forced containment
screens keep each machine's own amounts.

Fixtures (AMENDMENT P7-8 section 4.2; a pre-cell failure is a FIXTURE-STOP: one CAPTURE line, every row of the boot
FAILs "pre-cell"):
  PRES = SEL (test_w2_shared_selection.sel_pre on shared_fixture.bring_up(tag, (0, 0, "47265")): the first base-0
         soldier owned by seat 1, off its craft on both) + the roster names (save_markers.coopPlayers); rows restage
         X = STR_RIFLE and Y = STR_PISTOL with give_items on both (client first, S25) and open the REAL Sell screens
         (open_screen {sell}, host first) through test_w2_shared_selection.row_start.
  CT2  = FX-CT (test_w2_shared_forced_containment: {storageLimitsEnforced} on BOTH user dirs, STR_ALIEN_CONTAINMENT
         at (0, 3) built on both, STR_SECTOID_SOLDIER x 10 on both = the capacity) with TWO stuns: host
         battle_action {kill_unit_real, unit, stun: true} on units 1000000 and 1000001 (each chain settled: isBusy
         false and pendingStates 0, F4665; each unconscious, status 7, on both; then the queues drained and hash_now
         full equal), test_w2_shared_forced_storage.stage_x with kill_expect = the 13 other hostiles; pre-cell: the host
         debriefing's "LIVE ALIENS RECOVERED" 2, the client's adoption, both stunned units of type L (used 12, free -2).
  Labels: "Also on this screen: <the other seat's roster name>" (STR_COOP_ALSO_ON_SCREEN, D203, PR-50 (iii)).
  Colours: screen_rows rows[i].color (column 0's colour, TextList::harnessCellColor, PR-51), secondaryColor (the
  list's), highlightColor (the top screen's interface button2, F6112, V-E4).

Rows (the GREEN cells, checked in order; a failed cell ends its row and the rest are reported "not reached"):
  Boot PRES (port 47265): E-h, E2-se, E2-gs, E-g (last: the client disconnects).
  E-h  (1) both Sell screens: the host's textItems hold "Also on this screen: ClientPlayer" visible, the client's
           "Also on this screen: HostPlayer" visible, within SEL_S.
       (2) client X = 2: on the host X's color == highlightColor (within SEL_S); on the client X's color ==
           secondaryColor.
       (3) host Y = 1: on the client Y's color == highlightColor (within SEL_S).
       (4) client Sell/Sack: its SellState gone within PAGE_S; the host's top stays SellState (rebuilt: X lists the new
           stock), and within SEL_S no row in highlightColor, every amount 0, the label hidden.
  E2-se (1) (F6341, MR7, V-E3) the client sets ONLY its own soldier's row to 1; the host's screen_rows lists no row
           named after that soldier (MR7); the host's sel_state sell|n|0| rows == {s:<id>: 1} within SEL_S.
       (2) host Sell/Sack: its SellState gone within PAGE_S; that soldier gone from base 0 on both within EQUAL_S
           (sacked); the client's top stays SellState (rebuilt), every amount 0; no CoopState.
  E2-gs (D243; geometry = list_widgets on the top state: the first TextList's rect, the Cancel button's rect, every
           Text starting with the label's head; test_w2_shared_selection_screens.geo_cell)
       (1) the host alone opens Sell: its list height == SHARED_LIST_H (120 - 8 = 112: one text row shorter than
           vanilla's 120) and no label visible, within SEL_S.
       (2) the client opens Sell too: on both the list height stays 112 and a VISIBLE label names the other player, its
           rect between the list's bottom and the Cancel button's top, within SEL_S.
       (3) the host Cancels: the client's list height stays 112, its label hidden, within SEL_S.
  E-g  (1) host open_screen sell, then client open_screen sell: the host's sel_state sell|n|0| viewers [0, 1] within
           SEL_S (R-E2-2, F6449: no label clause here - E-h (1) asserts the label).
       (2) client disconnect_to_menu: within DROP_S the host's sel_state sell|n|0| viewers [0].
  Boot CT2 (port 47264): E2-cf.
  E2-cf (1) both OKs (test_w2_shared_forced_storage.both_oks_forced, class ManageAlienContainmentState, mark "ALIEN
           CONTAINMENT LIMITS EXCEEDED"); both boxes dismissed: both forced screens up.
       (2) client L = 1 (its Remove Selected stays hidden) -> the host's L amount 1 within SEL_S, Remove Selected
           hidden on both.
       (3) host L = 2: Remove Selected visible on both; client Remove Selected: both forced screens close themselves
           within SCREEN_S (tops GeoscapeState); prisoners (L stock) 10 on both; world_diff empty; no CoopState.
Guard on every row: no new crash log; CT2 also host event_state.fatalVote.armed 0; the client zero-disk at each
boot's end.

RED (commit S-C-E2.1: screen_push, the row colours and textItems, these rows; product untouched): E-h fails on cell 1
(no label), E2-se on cell 2 (the soldier stays in base 0 on both: the host's confirm submitted nothing, F6341), E-g on
cell 2 (the host's viewers stay [0, 1], F6110), E2-cf on cell 2 (the host's L amount stays 0). RED (commit
S-C-E2.1b, D243, test only): E2-gs fails on cell 1 (the list keeps vanilla's 120). GREEN (commit S-C-E2.2): every row
passes.
Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE foreground
run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_shared_selection_presence.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state
import test_w2_shared_forced_storage as fst
import test_w2_shared_forced_containment as fct
import test_w2_shared_selection as e1
import test_w2_shared_selection_screens as scr

# ----- pins (AMENDMENT P7-8 section 4 / 4.2) -----
X, Y = e1.X, e1.Y                        # STR_RIFLE, STR_PISTOL (SEL's X and Y, looked up by type, S25)
SEL_KEY = e1.SEL_KEY                     # "sell|n|0|"
E_H_X, E_H_Y = 2, 1                      # P7-8 section 4.2 E-h's amounts
SELL_OK, CANCEL = e1.SELL_OK, e1.CANCEL  # "Sell/Sack", "Cancel"
L = fct.L                                # STR_SECTOID_SOLDIER (FX-CT's live alien)
STUN_UNITS = (1000000, 1000001)          # CT2: two of the live-recoverable sectoids 1000000-1000009 (CONSTANTS F5438)
LIVE_FILL = fct.LIVE_FILL                # 10 = the containment's capacity (FX-CT)
LIVE_RECOVERED = 2                       # CT2 pre-cell: the host debriefing's LIVE ALIENS RECOVERED
PRISONERS_AFTER = LIVE_FILL + LIVE_RECOVERED - 2   # E2-cf (3): "prisoners 10 on both"
E2CF_CLIENT, E2CF_HOST = 1, 2            # P7-8 section 4.2 E2-cf's amounts
MACS, CONT_OK, CONT_MARK = fct.MACS, fct.CONT_OK, fct.CONT_MARK
BOOT_PORT = {"PRES": "47265", "CT2": "47264"}    # AMENDMENT P7-8 section 4 (S26, F6118): E2 = 47264 (CT2), 47265 (PRES)
SEL_S, PAGE_S, SCREEN_S, EQUAL_S = e1.SEL_S, e1.PAGE_S, e1.SCREEN_S, e1.EQUAL_S
DROP_S = 10                              # P7-8 section 4.2 E-g (2): "within 10 s"
BUSY_S, UNIT_S = fct.BUSY_S, fct.UNIT_S  # 30 s / 10 s (F4665; status 7 on both)

MISSES = scr.MISSES


# ===================== probes =====================


def short(e, n=400):
    return scr.short(e, n)


def stack(gc):
    return scr.stack(gc)


def top(gc):
    return scr.top(gc)


def wait_until(pred, timeout, interval=0.2):
    return scr.wait_until(pred, timeout, interval)


def poll(fn, timeout, interval=0.2):
    return scr.poll(fn, timeout, interval)


def rows(gc, **kw):
    return scr.rows(gc, **kw)


def row_color(r, item):
    """(amount, color) of the row whose item type == item."""
    for row in r.get("rows") or []:
        if row.get("item") == item:
            c = row.get("cells") or []
            return (scr.as_int(c[2]) if len(c) > 2 else None), row.get("color")
    return None, None


def highlighted(r):
    """The names of the rows drawn in the screen's highlight colour."""
    hc = r.get("highlightColor")
    return [(row.get("cells") or [""])[0] for row in (r.get("rows") or []) if hc is not None and row.get("color") == hc]


def sel(gc, key):
    return scr.sel(gc, key)


# ===================== fixtures =====================


def pres_pre(js, ctx):
    """PRES pre-cell: SEL's soldier off its craft, the roster names."""
    e1.sel_pre(js, ctx)
    ctx["names"] = scr.roster_names(js.host)
    if len(ctx["names"]) != 2:
        e1.capture("PRES names", f"coopPlayers {ctx['names']} (want 2 names)", (js.host, js.client))


def stun_two(js, ctx):
    """CT2's two stuns (PR-35's lever, FX-CT's settle and mirror checks per unit), then one full hash check."""
    host, client = js.host, js.client
    m = (host, client)
    ctx["stun"] = {"units": {}}
    for uid in STUN_UNITS:
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid, "stun": True})
        rec = {"resp": {k: r.get(k) for k in ("ok", "killed", "error")}}
        ctx["stun"]["units"][uid] = rec
        if not (r.get("ok") and r.get("killed") == [uid]):
            fst.capture("CT2 stun", f"kill_unit_real {{unit {uid}, stun}} answered {rec['resp']}", m)
        ok, secs = wait_until(lambda: (lambda b: b.get("isBusy") is False and b.get("pendingStates") == 0)(
            battle_state(host)), BUSY_S)
        rec["settled"] = {"ok": ok, "secs": secs}
        if not ok:
            fst.capture("CT2 stun settle", f"host isBusy / pendingStates not settled within {BUSY_S}s after unit {uid} "
                        f"(F4665)", m)
        ok, secs = wait_until(lambda: fct.unit_of(host, uid).get("status") == 7
                              and fct.unit_of(client, uid).get("status") == 7, UNIT_S)
        hu, cu = fct.unit_of(host, uid), fct.unit_of(client, uid)
        keys = ("status", "isOut", "health", "stun", "type", "onTile")
        rec["unit"] = {"host": {k: hu.get(k) for k in keys}, "client": {k: cu.get(k) for k in keys}, "secs": secs}
        rec["type"] = hu.get("type")
        if not ok:
            fst.capture("CT2 unconscious", f"unit {uid} {rec['unit']} (want status 7 on both)", m)
    try:
        session.wait_host_idle(host, client, timeout=20)
        hh, _ch = session.assert_hash_clean(host, client, full=True, what="after the CT2 stuns")
        ctx["stun"]["hash"] = sorted(hh)
    except Exception as e:
        fst.capture("CT2 stun mirror", f"{type(e).__name__}: {str(e)[:700]} (F5575: the client mirror of the stuns)", m)


def ct2_pre(js, ctx):
    """CT2 pre-cell: FX-CT's geoscape half (the facility, LIVE x LIVE_FILL on both), the two-stun ending, the live-alien
    row 2, the adoption, both stunned units of type L."""
    host, client = js.host, js.client
    m = (host, client)
    fb = host.cmd({"cmd": "fac_build", "facility": fct.CONTAINMENT, "x": fct.CT_X, "y": fct.CT_Y})
    ok, secs = wait_until(lambda: fct.facility_index(host) is not None and fct.facility_index(client) is not None, 45,
                          0.5)
    idx = {gc.name: fct.facility_index(gc) for gc in m}
    ctx["fxCT"] = {"facBuild": {k: fb.get(k) for k in ("ok", "error")}, "index": idx, "secs": secs}
    if not (fb.get("ok") and ok and idx["host"] == idx["client"] == fct.CT_INDEX):
        fst.capture("CT2 facility", f"fac_build {ctx['fxCT']['facBuild']}, index {idx} (want {fct.CT_INDEX} on both)", m)
    sets = {}
    for gc in (client, host):   # client first (F607)
        r = gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": fct.CT_INDEX, "time": 0})
        sets[gc.name] = {k: r.get(k) for k in ("ok", "type", "x", "y", "buildTime", "error")}
    ctx["fxCT"]["buildTime0"] = sets
    if not all(s.get("ok") and s.get("type") == fct.CONTAINMENT and s.get("buildTime") == 0 for s in sets.values()):
        fst.capture("CT2 buildTime", f"set_facility_build_time answered {sets}", m)
    give = {}
    for gc in (client, host):
        r = gc.cmd({"cmd": "give_items", "item": fct.LIVE, "count": LIVE_FILL})
        give[gc.name] = {k: r.get(k) for k in ("ok", "stored", "error")}
    ctx["fxCT"]["give"] = give
    if not (give["host"].get("ok") and give["client"].get("ok") and give["host"].get("stored") == LIVE_FILL
            and give["client"].get("stored") == LIVE_FILL):
        fst.capture("CT2 give_items", f"answered {give} (want {LIVE_FILL} stored on both)", m)
    fst.stage_x(js, ctx, pre_kill=stun_two, kill_expect=[u for u in fst.HOSTILES if u not in STUN_UNITS])
    live = [r for r in (ctx["hostDebrief"].get("rows") or []) if r.get("item") == fct.LIVE_ROW]
    ctx["fxCT"]["liveRow"] = live
    if not (len(live) == 1 and live[0].get("qty") == LIVE_RECOVERED):
        fst.capture("CT2 live aliens recovered", f"host debriefing rows {ctx['hostDebrief'].get('rows')} (want "
                    f"{fct.LIVE_ROW!r} {LIVE_RECOVERED})", m)
    fst.client_adopted(js, ctx)
    types = {uid: u.get("type") for uid, u in ctx["stun"]["units"].items()}
    if any(t != L for t in types.values()):
        fst.capture("CT2 L", f"the stunned units' types {types} (want the pinned L {L!r})", m)


# ===================== PRES rows =====================


def boot_of(ctx):
    return scr.boot_of(ctx)


def e_h_cells(host, client, ctx):
    names = boot_of(ctx)["names"]

    def c1():
        e1.row_start(host, client, ctx)
        return scr.labels_cell(host, client, names, ctx, "c1labels")

    def c2():
        f = e1.set_ok(client, E_H_X, ctx, "c2set", item=X)
        if f:
            return f
        last = {}

        def host_hl():
            r = rows(host)
            last.update({"row": row_color(r, X), "highlightColor": r.get("highlightColor")})
            return last["row"] == (E_H_X, r.get("highlightColor")) and r.get("highlightColor") is not None, dict(last)
        ok, got, secs = poll(host_hl, SEL_S)
        ctx["c2host"] = {"ok": ok, "seen": got, "secs": secs}
        if not ok:
            return [f"the host's {X} (amount, color) {got.get('row')} {SEL_S}s after the client's edit (want ({E_H_X}, "
                    f"highlightColor {got.get('highlightColor')}): a row another player set is highlighted, D203)"]
        rc = rows(client)
        ctx["c2client"] = {"row": row_color(rc, X), "secondaryColor": rc.get("secondaryColor")}
        if row_color(rc, X)[1] != rc.get("secondaryColor"):
            return [f"the client's own {X} color {row_color(rc, X)[1]} (want secondaryColor {rc.get('secondaryColor')}: "
                    f"a row the player set itself keeps vanilla's colour)"]
        return []

    def c3():
        f = e1.set_ok(host, E_H_Y, ctx, "c3set", item=Y)
        if f:
            return f

        def client_hl():
            r = rows(client)
            return row_color(r, Y) == (E_H_Y, r.get("highlightColor")) and r.get("highlightColor") is not None, {
                "row": row_color(r, Y), "highlightColor": r.get("highlightColor")}
        ok, got, secs = poll(client_hl, SEL_S)
        ctx["c3client"] = {"ok": ok, "seen": got, "secs": secs}
        return [] if ok else [f"the client's {Y} (amount, color) {got.get('row')} {SEL_S}s after the host's edit (want "
                              f"({E_H_Y}, highlightColor {got.get('highlightColor')}))"]

    def c4():
        s0 = ctx["stock0"]["host"][X]
        ctx["c4click"] = e1.click(client, SELL_OK)
        f = e1.gone(client, ctx, "c4clientGone")
        if f:
            return f
        f = e1.stays_rebuilt(host, X, s0 - E_H_X, ctx, "c4hostRebuilt")
        if f:
            return f

        def cleared():
            r = rows(host)
            v = {"highlighted": highlighted(r), "nonZero": {k: a for k, a in e1.amounts(r).items() if a},
                 "labels": scr.label_items(r), "top": r.get("state")}
            return (r.get("state") == "SellState" and not v["highlighted"] and e1.all_zero(r)
                    and scr.label_hidden(r)), v
        ok, got, secs = poll(cleared, SEL_S)
        ctx["c4host"] = {"ok": ok, "seen": got, "secs": secs}
        return [] if ok else [f"the host's rebuilt screen {got} {SEL_S}s on (want no row in highlightColor, every amount "
                              f"0, the label hidden: the list cleared and the client left)"]
    return [
        ("1 both Sell screens name the other player", c1),
        ("2 the client's edit is highlighted on the host's screen, not on its own", c2),
        ("3 the host's edit is highlighted on the client's screen", c3),
        ("4 the client's confirm: the host's rebuilt screen has no highlight, zero amounts, no label", c4),
    ]


def e2_se_cells(host, client, ctx):
    sold = scr.soldier_of(ctx)

    def c1():
        e1.row_start(host, client, ctx)
        idx = e1.soldier_row(rows(client), sold["name"])
        ctx["c1soldierRow"] = idx
        if idx is None:
            return [f"the client's SellState lists no row for its soldier {sold['name']!r} (id {sold['id']})"]
        f = e1.set_ok(client, 1, ctx, "c1s", row=idx)
        if f:
            return f
        hidx = e1.soldier_row(rows(host), sold["name"])
        ctx["c1hostRow"] = hidx
        if hidx is not None:
            return [f"the host's SellState lists the client's soldier {sold['name']!r} (row {hidx}; want none, MR7)"]
        want = {f"s:{sold['id']}": 1}
        ok, got, secs = poll(lambda: (lambda r: (r == want, r))(e1.sel_rows(host, SEL_KEY)), SEL_S)
        ctx["c1hostSel"] = {"ok": ok, "rows": got, "secs": secs}
        return [] if ok else [f"the host's sel_state {SEL_KEY} rows {got} (want {want})"]

    def c2():
        ctx["c2click"] = e1.click(host, SELL_OK)
        f = e1.gone(host, ctx, "c2hostGone")
        if f:
            return f
        ok, v, secs = poll(lambda: (lambda h, c: (not h and not c, {"host": h, "client": c}))(
            [s.get("id") for s in e1.roster(host) if s.get("id") == sold["id"]],
            [s.get("id") for s in e1.roster(client) if s.get("id") == sold["id"]]), EQUAL_S)
        ctx["c2soldier"] = {"ok": ok, "inBase0": v, "secs": secs}
        if not ok:
            return [f"soldier {sold['id']} still in base 0 {v} {EQUAL_S}s after the host's Sell/Sack (want sacked on "
                    f"both: the host's confirm applies the shared list although the host sees none of its rows, F6341, "
                    f"V-E3)"]
        ok, secs = wait_until(lambda: e1.screen_ready(client), SCREEN_S)
        ctx["c2clientTop"] = {"ok": ok, "secs": secs, "stack": stack(client)}
        if not ok:
            return [f"the client's top {top(client)!r} after the host's sale (want its SellState, rebuilt)"]
        ok, a, secs = poll(lambda: (lambda r: (e1.all_zero(r), {k: v2 for k, v2 in e1.amounts(r).items() if v2}))(
            rows(client)), SEL_S)
        ctx["c2clientAmounts"] = {"ok": ok, "nonZero": a, "secs": secs}
        if not ok:
            return [f"the client's rebuilt amounts {a} (want every amount 0, D204)"]
        return e1.no_box(host, client, ctx, "c2stacks")
    return [
        ("1 only the client's own soldier row is on the shared list; the host's list hides it (MR7)", c1),
        ("2 the host's Sell/Sack applies the list it cannot see (F6341, V-E3)", c2),
    ]


def e2_gs_cells(host, client, ctx):
    """D243 on Sell: the SHARED list is one row shorter with or without the other player; the label sits between the
    list and the buttons while both are on the screen."""
    names = boot_of(ctx)["names"]

    def open_sell(gc, key):
        r = gc.cmd({"cmd": "open_screen", "screen": "sell"})
        ok, secs = wait_until(lambda: e1.screen_ready(gc), PAGE_S)
        ctx[key] = {"resp": {k: r.get(k) for k in ("ok", "error")}, "ready": ok, "secs": secs}
        if not ok:
            e1.capture(f"E2-gs open_screen sell ({gc.name})", f"SellState not ready ({ctx[key]})", (host, client))

    def c1():
        scr.hygiene(host, client, ctx)
        open_sell(host, "c1open")
        return scr.geo_cell((host,), "SellState", ctx, "c1geo")

    def c2():
        open_sell(client, "c2open")
        return scr.geo_cell((host, client), "SellState", ctx, "c2geo", names=names)

    def c3():
        ctx["c3cancel"] = e1.click(host, CANCEL)
        f = e1.gone(host, ctx, "c3hostGone")
        return f or scr.geo_cell((client,), "SellState", ctx, "c3geo")
    return [
        ("1 the host alone: its Sell list is one row shorter, no label (D243)", c1),
        ("2 the client joins: both lists one row shorter, each label between the list and the buttons", c2),
        ("3 the host leaves: the client's list stays one row shorter, its label hidden", c3),
    ]


def e_g_cells(host, client, ctx):
    def c1():
        scr.hygiene(host, client, ctx)
        opened = {}
        for gc in (host, client):   # host first: the client joins a screen the host already shows
            r = gc.cmd({"cmd": "open_screen", "screen": "sell"})
            ok, secs = wait_until(lambda gc=gc: e1.screen_ready(gc), PAGE_S)
            opened[gc.name] = {"resp": {k: r.get(k) for k in ("ok", "error")}, "ready": ok, "secs": secs}
        ctx["c1open"] = opened
        if not all(v["ready"] for v in opened.values()):
            e1.capture("E-g open_screen sell", f"both SellStates not ready ({opened})", (host, client))
        ok, got, secs = poll(lambda: (lambda e: (isinstance(e, dict) and e.get("viewers") == [0, 1], e))(
            sel(host, SEL_KEY)), SEL_S)
        ctx["c1hostSel"] = {"ok": ok, "sel": got, "secs": secs}
        return [] if ok else [f"the host's sel_state {SEL_KEY} {got} (want viewers [0, 1])"]

    def c2():
        r = client.cmd({"cmd": "disconnect_to_menu"})
        ctx["c2disconnect"] = {k: r.get(k) for k in ("ok", "error")}
        ok, got, secs = poll(lambda: (lambda e: (isinstance(e, dict) and e.get("viewers") == [0], e))(
            sel(host, SEL_KEY)), DROP_S, 0.5)
        ctx["c2hostSel"] = {"ok": ok, "sel": got, "secs": secs, "hostStack": stack(host)}
        return [] if ok else [f"the host's sel_state {SEL_KEY} {got} {DROP_S}s after the client's disconnect (want "
                              f"viewers [0]: the dropped seat leaves every shared screen, PR-48)"]
    return [
        ("1 both on one Sell screen: the host's store lists both viewers", c1),
        ("2 the client disconnects: the host drops its seat from the list", c2),
    ]


# ===================== CT2 row =====================


def e2_cf_cells(host, client, ctx):
    def c1():
        f = fst.both_oks_forced(host, client, ctx, "c1", MACS, CONT_MARK)
        if f:
            return f
        return fst.boxes_to_screens(host, client, ctx, "c1boxes", MACS)

    def c2():
        f = e1.set_ok(client, E2CF_CLIENT, ctx, "c2set", item=L)
        if f:
            return f
        if ctx["c2set"].get("okVisible") is not False:
            return [f"the client's {CONT_OK} visible={ctx['c2set'].get('okVisible')!r} at L {E2CF_CLIENT} (want False: "
                    f"still over the limit)"]
        f = scr.cross(host, L, E2CF_CLIENT, ctx, "c2host", mac=True)
        if f:
            return f
        v = scr.ok_visible(rows(host), CONT_OK)
        ctx["c2hostOk"] = v
        return [] if v is False else [f"the host's {CONT_OK} visible={v!r} at L {E2CF_CLIENT} (want False)"]

    def c3():
        f = e1.set_ok(host, E2CF_HOST, ctx, "c3set", item=L)
        if f:
            return f
        if ctx["c3set"].get("okVisible") is not True:
            return [f"the host's {CONT_OK} visible={ctx['c3set'].get('okVisible')!r} at L {E2CF_HOST} (want True)"]
        ok, v, secs = poll(lambda: (lambda x: (x is True, x))(scr.ok_visible(rows(client), CONT_OK)), SEL_S)
        ctx["c3clientOk"] = {"ok": ok, "visible": v, "secs": secs}
        if not ok:
            return [f"the client's {CONT_OK} visible={v!r} {SEL_S}s after the host's L {E2CF_HOST} (want True)"]
        ctx["c3click"] = e1.click(client, CONT_OK)
        ok, secs = wait_until(lambda: top(host) == "GeoscapeState" and top(client) == "GeoscapeState", SCREEN_S)
        ctx["c3closed"] = {"ok": ok, "secs": secs, "stacks": {gc.name: stack(gc) for gc in (host, client)}}
        if not ok:
            return [f"the forced containment screens did not both close themselves within {SCREEN_S}s (stacks "
                    f"{ctx['c3closed']['stacks']})"]
        ok, got, secs = poll(lambda: (lambda v: (v == {"host": PRISONERS_AFTER, "client": PRISONERS_AFTER}, v))(
            {gc.name: fst.stock_of(gc, L) for gc in (host, client)}), EQUAL_S)
        ctx["c3prisoners"] = {"ok": ok, "stock": got, "secs": secs}
        if not ok:
            return [f"{L} stock {got} (want {PRISONERS_AFTER} on both)"]
        return scr.world_same(host, client, ctx, "c3world") + e1.no_box(host, client, ctx, "c3stacks")
    return [
        ("1 both OKs: both forced containment screens up", c1),
        ("2 the client's L 1 reaches the host's forced screen; still over on both", c2),
        ("3 the host's L 2 clears it on both; the client's confirm closes both forced screens", c3),
    ]


# ===================== boots =====================


def bring_up_ct2(tag, port):
    return fst.bring_up(tag, port, fct.OPTS_CT)


BOOTS = (("PRES", "w2p7sce2_pres", scr.bring_up_sel, pres_pre,
          (("E-h", e_h_cells), ("E2-se", e2_se_cells), ("E2-gs", e2_gs_cells), ("E-g", e_g_cells)), False),
         ("CT2", "w2p7sce2_ct2", bring_up_ct2, ct2_pre, (("E2-cf", e2_cf_cells),), True))


def main():
    t0, results, walls = time.time(), {}, {}
    for boot, tag, up_fn, pre_fn, rows_spec, battle in BOOTS:
        scr.run_boot(boot, tag, BOOT_PORT[boot], up_fn, pre_fn, rows_spec, battle, results, walls)
    order = [rid for _, _, _, _, rs, _ in BOOTS for rid, _ in rs]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_shared_selection_presence: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (boot walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
