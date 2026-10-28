"""R5-U6 S-D rows AE1-AE9 (boot DA, gm2 Small Scout: the client plays the aliens, seat 1; the host the seven X-COM
soldiers, seat 0; default options, so "Enable XCOM Equipment for Aliens in PVP" is on): the PvP alien seat equips its own
aliens on the pre-battle screen from the ONE X-COM craft pile both sides share (owner D236 (b), D274 and its 2026-10-13
confirmation, R-U6-OF3, QU6-6 (a)): a drop from either side lands on the pile and is visible to both, either side may take
anything on it, no refusal, the aliens' starting gear stays in their hands, and after the equip screen every drop lands on
the dropping unit's own tile.

Spec: docs repo rewrite/prompts/r5u6_pvp_options.md AMENDMENT U6-1.5.6 (f') with U6-1.7's run-time rules and the orchestrator
rulings R-U6-SD-1 / R-U6-SD-2 (D-1 as R-U6-SD-2 replaces it: every drop on the pile goes to the first free ground cell in
column-major order where the item fits, across the WHOLE ground grid, the screen scrolled to that cell's page first;
D-2: PISTOL = the first A_START item, right hand, left hand, then the rest by id, whose type is not on the pile; the U6-1.7
swap: no STR_RIFLE on the pile, so RIFLE is the lowest-column pile item that fits BACKPACK_CELL). Constants: docs repo
rewrite/r5u6-task0/sd/CONSTANTS.md (TASK 0 boots DAa, DAb, DAc, DAd on the unchanged build). No id is pinned (S25).

Boot DA (key 49065): set_seed 1, the client joins and takes the Alien team (gamemode 2), the PSR drive without its last line;
both briefings; R0 on each machine (A = the client seat's first unit with items, A_START, A_SPAWN); the host's briefing OK ->
its screen on H1 (PILE, PILE_IDS = G(host)); dismiss_client_briefing (a bounded wait for the client's top); CENSUS0.
  AE1  the alien seat's screen and its own gear: AE1-counted, AE1-screen, AE1-ground, AE1-gear
  AE2  the alien takes RIFLE from the pile into BACKPACK_CELL (the client's real UI): AE2-order, AE2-held, AE2-gone
  AE3  the alien's own PISTOL goes on the shared pile: AE3-order, AE3-pile, AE3-seen
  AE4  the X-COM player takes it onto H1_CELL (host-local real UI): AE4-held, AE4-gone
  AE5  the X-COM player drops it back on the pile: AE5-pile, AE5-seen
  AE6  the alien puts RIFLE back: AE6-back, AE6-seen
  AE7  turn 1 with X-COM gear (RIFLE into BACKPACK_CELL again, both OKs): AE7-turn, AE7-held, AE7-census
  AE8  a soldier's turn-1 drop lands on its own tile (host): AE8-ground, AE8-tile
  AE9  an alien's turn-1 drop lands on its own tile (host END TURN, the client's IV5-shaped drop): AE9-ground, AE9-order,
       AE9-tile
Common cell after each row (<row>-common): every hash bucket EQUAL, desyncSeen false on both, no new lane crash file.

RED on the unchanged build (commit D1): AE1-counted, AE1-screen, AE1-ground, AE2-order, AE2-held, AE2-gone, AE3-order,
AE3-pile, AE3-seen, AE4-held, AE4-gone, AE5-pile, AE5-seen, AE6-back, AE6-seen, AE7-held; every other cell PASS. One
EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot step past its
bound prints ONE CAPTURE line and fails every row "boot"; a staging step past its bound fails that row "staging".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every
cell passes, else 2. test_alien_equip_gm3.py imports this file's helpers.

Run:  python tools/coop_test/test_alien_equip.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_pvp_react_mc as RM  # noqa: E402
import test_prebattle_equip as PEQ  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402

KEY = "49065"
SEED = 1                          # set_seed on the host before its lobby and right before newbattle_ok (BER / PSR)
MISSION = "STR_SMALL_SCOUT"
GROUND, BACK, BELT, LH, RH = "STR_GROUND", "STR_BACK_PACK", "STR_BELT", "STR_LEFT_HAND", "STR_RIGHT_HAND"
SDLK_RIGHT, COLS, GROUND_ROWS = 275, 20, 3   # vanilla's ground-scroll key (keyBattleRight); one ground page is 20 x 3
STEP_S, SCREEN_S, LAND_S, ORDER_S, CLICK_S, POLL_S = 30, 15, 10, 20, 2, 0.1
ROWS = (("AE1", ("AE1-counted", "AE1-screen", "AE1-ground", "AE1-gear", "AE1-common")),
        ("AE2", ("AE2-order", "AE2-held", "AE2-gone", "AE2-common")),
        ("AE3", ("AE3-order", "AE3-pile", "AE3-seen", "AE3-common")),
        ("AE4", ("AE4-held", "AE4-gone", "AE4-common")),
        ("AE5", ("AE5-pile", "AE5-seen", "AE5-common")),
        ("AE6", ("AE6-back", "AE6-seen", "AE6-common")),
        ("AE7", ("AE7-turn", "AE7-held", "AE7-census", "AE7-common")),
        ("AE8", ("AE8-ground", "AE8-tile", "AE8-common")),
        ("AE9", ("AE9-ground", "AE9-order", "AE9-tile", "AE9-common")))


# ===================== shared helpers (test_alien_equip_gm3 imports them) =====================


def es(gc, key):
    return event_state(gc).get(key)


def wait_until(pred, timeout, interval=POLL_S):
    return PEQ.wait_until(pred, timeout, interval)


def iv(gc):
    return PEQ.inv_view(gc)


def G(gc):
    """The sorted ground ids of gc's open InventoryState ([] with none open)."""
    return PEQ.ground_ids(iv(gc))


def IT(gc):
    return PEQ.items_by_id(gc)


def pos(gc, uid):
    return G3F.pos(gc, uid)


def cursor(gc):
    return iv(gc).get("selectedItem")


def census(gc):
    r = gc.cmd({"cmd": "battle_items"})
    ids = [it["id"] for it in r.get("items", [])]
    return {"total": r.get("total"), "counts": r.get("counts"), "ids": sorted(ids), "dups": len(ids) - len(set(ids))}


def items_of(its, uid):
    return {i: (it.get("slot"), it.get("slotX"), it.get("slotY")) for i, it in its.items() if it.get("owner") == uid}


def on_tile(its, p):
    return sorted(i for i, it in its.items() if it.get("onTile") and it.get("owner") in (None, -1)
                  and (it.get("tx"), it.get("ty"), it.get("tz")) == tuple(p))


def at(its, iid, p):
    it = its.get(iid) or {}
    return (it.get("owner") in (None, -1) and it.get("slot") == GROUND
            and (it.get("tx"), it.get("ty"), it.get("tz")) == tuple(p))


def at_both(host, client, iid, p):
    return at(IT(host), iid, p) and at(IT(client), iid, p)


def owned(its, iid, uid, slot=None):
    it = its.get(iid) or {}
    return it.get("owner") == uid and (slot is None or it.get("slot") == slot)


def views(host, client, iid):
    return [PEQ.item_view(IT(host), iid), PEQ.item_view(IT(client), iid)]


def screen_on(gc, uid):
    v = iv(gc)
    return v.get("open") is True and v.get("top") is True and v.get("preBattle") is True and v.get("unitId") == uid


def sizes():
    """{type: (invWidth, invHeight)} from the ruleset the game reads (the Release deploy, F6757)."""
    p = os.path.join(os.path.dirname(os.path.abspath(harness.EXE)), "standard", "xcom1", "items.rul")
    d, cur = {}, None
    with open(p, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^  - type: (\S+)", line)
            if m:
                cur = m.group(1)
                d[cur] = [1, 1]
                continue
            m = re.match(r"^    inv(Width|Height): (\d+)", line)
            if m and cur:
                d[cur][0 if m.group(1) == "Width" else 1] = int(m.group(2))
    return {k: tuple(v) for k, v in d.items()}


SZ = sizes()
SLOTS = {}
PAGE = {}   # {machine name: the ground page its open pre-battle screen shows}; goto_page keeps it


def foot(t, x, y):
    w, h = SZ.get(t, (1, 1))
    return {(x + i, y + j) for i in range(w) for j in range(h)}


def free_cell(gc, its, uid, itype, slot=BACK):
    """U6-1.7: the first free `slot` cell, row-major, of `uid` where `itype` fits (cells minus the unit's items)."""
    if not SLOTS:
        SLOTS.update({k: {tuple(c) for c in v["cells"]} for k, v in (gc.cmd({"cmd": "inventory_view"}).get("slots") or {}).items()})
    cells, occ = SLOTS.get(slot) or set(), set()
    for it in its.values():
        if it.get("owner") == uid and it.get("slot") == slot and it.get("slotX") is not None:
            occ |= foot(it.get("type"), it["slotX"], it["slotY"])
    for y in sorted({c[1] for c in cells}):
        for x in sorted({c[0] for c in cells}):
            fp = foot(itype, x, y)
            if fp <= cells and not fp & occ:
                return (x, y)
    return None


def ground_layout(gc):
    """gc's laid-out ground [(id, x, y, type)]: the placed items (vanilla parks an item it does not place at x 1000000)."""
    its = IT(gc)
    return [(g["id"], g.get("x"), g.get("y"), (its.get(g["id"]) or {}).get("type")) for g in iv(gc).get("ground") or []
            if g.get("x") is not None and g.get("x") < 1000000]


def x_max(lay):
    """Inventory::arrangeGround's _xMax: the first column right of every placed item."""
    return max([x + SZ.get(t, (1, 1))[0] for _, x, _, t in lay] or [0])


def free_ground(gc, itype):
    """R-U6-SD-2 (replaces R-U6-SD-1 D-1's page-0 search): the first free ground cell where the item fits, column-major
    (x, then y) across the WHOLE ground grid (x past 19 = page 1, ...) on the pages the screen reaches (page p while the
    layout reaches column 20 * p, vanilla's ground-scroll rule); an item never straddles two pages. Absolute (x, y)."""
    lay = ground_layout(gc)
    occ = set()
    for _, x, y, t in lay:
        occ |= foot(t, x, y)
    w, h = SZ.get(itype, (1, 1))
    for x in range(COLS * (x_max(lay) // COLS + 1)):
        if x % COLS > COLS - w:
            continue
        for y in range(GROUND_ROWS - h + 1):
            if not foot(itype, x, y) & occ:
                return (x, y)
    return None


def goto_page(gc, page, rec):
    """scroll gc's pre-battle screen to ground page `page` with vanilla's ground-scroll key (keyBattleRight,
    InventoryState.cpp :269 -> Inventory::arrangeGround(1)) from the page PAGE records (0 at the screen's open; a
    re-layout keeps it): each press moves to the next page while the layout reaches past it, else back to page 0."""
    cur, presses = PAGE.get(gc.name, 0), 0
    xm = x_max(ground_layout(gc))
    while cur != page and presses <= xm // COLS + 1:
        gc.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RIGHT})
        time.sleep(0.2)
        presses += 1
        cur = cur + 1 if xm >= (cur + 1) * COLS else 0
    PAGE[gc.name] = cur
    rec.setdefault("scroll", []).append({"to": page, "presses": presses, "xMax": xm, "at": cur})
    return cur == page


def pick_ground(gc, iid, rec):
    """U6-1.7 ground-page rule with R-U6-SD-2's scroll: the screen to page c // 20 (goto_page, from the page it shows),
    then column c - 20 * (c // 20). Returns the id
    the pick put on the cursor (the item or a same-type stack-mate), or None."""
    v = iv(gc)
    cell = PEQ.cell_of(v, iid)
    rec.update(cell=cell, cursorBefore=v.get("selectedItem"))
    if cell is None:
        rec["error"] = f"{iid} is not on {gc.name}'s ground {PEQ.ground_ids(v)}"
        return None
    pages = cell[0] // COLS
    rec.update(mates=PEQ.mates_at(v, cell), pages=pages)
    goto_page(gc, pages, rec)
    rec["click"] = PEQ.click(gc, slot=GROUND, x=cell[0] - COLS * pages, y=cell[1])
    wait_until(lambda: cursor(gc) not in (None, -1), CLICK_S)
    rec["picked"] = cursor(gc)
    if rec["picked"] not in rec["mates"]:
        rec["error"] = f"the pick left {rec['picked']} on the cursor (want one of {rec['mates']})"
        return None
    return rec["picked"]


def pick_at(gc, slot, x, y, want, rec):
    rec["click"] = PEQ.click(gc, slot=slot, x=x or 0, y=y or 0)
    ok, _ = wait_until(lambda: cursor(gc) == want, CLICK_S)
    rec["picked"] = cursor(gc)
    return bool(ok)


def drop_at(gc, slot, x, y, rec):
    rec["drop"] = PEQ.click(gc, slot=slot, x=x, y=y)
    ok, _ = wait_until(lambda: cursor(gc) == -1, CLICK_S)
    rec["cursorAfter"] = cursor(gc)
    return bool(ok)


def drop_ground(gc, its, rec):
    """A drop on the pile at R-U6-SD-2's cell: the screen scrolled to the cell's page first, then the cell's column on it."""
    cell = free_ground(gc, (its.get(cursor(gc)) or {}).get("type"))
    rec["groundCell"] = cell
    if cell is None:
        return False
    page = cell[0] // COLS
    rec["groundPage"] = page
    return goto_page(gc, page, rec) and drop_at(gc, GROUND, cell[0] - COLS * page, cell[1], rec)


def clear_cursor(gc, ev, key):
    """An item left on a cursor by an earlier failed step goes back with ONE right-click (recorded, never silent)."""
    if cursor(gc) not in (None, -1):
        ev[key] = {"item": cursor(gc), "return": PEQ.click(gc, slot=BELT, x=0, y=0, button="right")}
        wait_until(lambda: cursor(gc) == -1, CLICK_S)


def order_done(host, client):
    """test_inventory.order_done: the client's slot empty, the host idle, the client caught up."""
    ec, eh = event_state(client), event_state(host)
    return (ec.get("inFlight") is None and battle_state(client).get("coopPendingIntent") is None
            and eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0)


def settle(host, client):
    return wait_until(lambda: order_done(host, client), ORDER_S)[1]


def drained(host, client):
    return wait_until(lambda: PEQ.drained(host, client), LAND_S)[1]


def before(host, client):
    return {"ctx": es(host, "closedContexts") or [], "sent": (es(client, "coopIntentsSent") or {}).get("inv_move", 0)}


def order_cell(host, client, b, actor):
    """Exactly one new host closedContexts entry {intent, inv_move, actor}; the client's coopIntentsSent.inv_move +1."""
    new = [RM.cv(c) for c in new_contexts(b["ctx"], es(host, "closedContexts"))]
    sent = (es(client, "coopIntentsSent") or {}).get("inv_move", 0)
    ok = (len(new) == 1 and (new[0]["origin"], new[0]["kind"], new[0]["actorId"]) == ("intent", "inv_move", actor)
          and sent == b["sent"] + 1)
    return ok, (f"new host closedContexts {new} (want exactly one {{intent, inv_move, {actor}}}); client inv_move sent "
                f"{b['sent']} -> {sent} (want +1)")


def r0(gc, seat):
    """U6-1.7 R0: A = `seat`'s first unit (battle_state.units order) owning an item in a slot; A_START; A_SPAWN."""
    its = IT(gc)
    a = next((u["id"] for u in battle_state(gc).get("units", []) if u.get("coop") == seat and not u.get("isOut")
              and any(it.get("owner") == u["id"] and it.get("slot") for it in its.values())), None)
    return {"A": a, "A_START": items_of(its, a), "A_SPAWN": pos(gc, a), "top": G3F.top(gc)}


def reads(ctx, host, xgc):
    """PISTOL (R-U6-SD-1 D-2), RIFLE (U6-1.7 swap rule), BACKPACK_CELL, the X-COM unit's cell for PISTOL (H1 / C1_CELL)."""
    ih, A = IT(host), ctx["A"]
    ast = ctx["R0"]["host"]["A_START"]
    ptypes = {(ih.get(i) or {}).get("type") for i in ctx["PILE_IDS"]}
    order = ([i for i, s in ast.items() if s[0] == RH] + [i for i, s in ast.items() if s[0] == LH]
             + sorted(i for i, s in ast.items() if s[0] not in (RH, LH)))
    ctx["PISTOL"] = next((i for i in order if (ih.get(i) or {}).get("type") not in ptypes), None)
    ctx["BP0"] = free_cell(xgc, ih, A, "STR_RIFLE")
    ctx["RIFLE"] = rifle_choice(xgc, ih, A, ctx["BP0"])
    ctx["BACKPACK_CELL"] = free_cell(xgc, ih, A, (ih.get(ctx["RIFLE"]) or {}).get("type"))
    ctx["X_CELL"] = free_cell(xgc, ih, ctx["X"], (ih.get(ctx["PISTOL"]) or {}).get("type"))
    ctx["types"] = {k: (ih.get(ctx[k]) or {}).get("type") for k in ("PISTOL", "RIFLE")}


def rifle_choice(gc, its, uid, cell):
    """U6-1.7 RIFLE: the pile's STR_RIFLE (PEQ first_of_type); none: the pile item with the lowest ground column (then
    row, then list order) whose footprint fits `uid`'s BACKPACK_CELL (computed for STR_RIFLE)."""
    rid = PEQ.first_of_type(gc, "STR_RIFLE")
    if rid is not None or cell is None:
        return rid
    occ = set()
    for it in its.values():
        if it.get("owner") == uid and it.get("slot") == BACK and it.get("slotX") is not None:
            occ |= foot(it.get("type"), it["slotX"], it["slotY"])
    ground = list(enumerate(iv(gc).get("ground") or []))
    for _, g in sorted(ground, key=lambda e: (e[1].get("x"), e[1].get("y"), e[0])):
        fp = foot((its.get(g["id"]) or {}).get("type"), cell[0], cell[1])
        if fp <= SLOTS.get(BACK, set()) and not fp & occ:
            return g["id"]
    return None


def close_turn_screens(host, client, timeout=STEP_S):
    """Every NextTurnState closed on both (close_nextturn) until both tops are BattlescapeState (RM.side_change idiom)."""
    rec, t0 = [], time.time()
    while time.time() - t0 < timeout and [G3F.top(host), G3F.top(client)] != ["BattlescapeState"] * 2:
        for gc in (host, client):
            if G3F.top(gc) == "NextTurnState":
                rec.append((gc.name, gc.cmd({"cmd": "close_nextturn"}).get("handled")))
        time.sleep(0.2)
    return {"closes": rec, "tops": [G3F.stack(host), G3F.stack(client)]}


def barrier(host, client, first, second, ev):
    """OK on `first` (its pre-battle screen), then on `second` where its screen is up (recorded); the barrier; turn screens."""
    for k, gc in (("firstOk", first), ("secondOk", second)):
        clear_cursor(gc, ev, k + "Cleared")
        ev[k] = PEQ.ok_press(gc) if PEQ.screen_up(gc) else f"{gc.name}: no pre-battle screen up"
        time.sleep(0.3)
    ok, ev["barrierS"] = wait_until(lambda: not any("InventoryState" in s for gc in (host, client) for s in G3F.stack(gc))
                                    and battle_state(host).get("turn") == 1 and battle_state(client).get("turn") == 1,
                                    SCREEN_S)
    ev["turnScreens"] = close_turn_screens(host, client)
    try:
        session.wait_host_idle(host, client, timeout=STEP_S)
    except Exception as e:
        ev["idleError"] = str(e)[:200]
    tops = [G3F.stack(host), G3F.stack(client)]
    turns = [battle_state(gc).get("turn") for gc in (host, client)]
    phases = [(es(gc, "equip") or {}).get("phase") for gc in (host, client)]
    ev.update(tops=tops, turns=turns, phases=phases)
    return (bool(ok) and turns == [1, 1] and phases == ["ended", "ended"]
            and not any("InventoryState" in s for st in tops for s in st),
            f"turn host/client {turns} (want 1 on both), equip.phase {phases} (want ended on both), stacks {tops} (want no "
            f"InventoryState), barrier {ev['barrierS']} s")


def census_cell(host, client, c0):
    ch, cc = census(host), census(client)
    return (ch == cc == c0 and ch["dups"] == 0,
            f"battle_items host total {ch['total']} / client {cc['total']} (want CENSUS0 {c0['total']}); counts and id sets "
            f"equal to CENSUS0 {ch == c0} / {cc == c0}; duplicate ids {ch['dups']} / {cc['dups']} (want 0)")


def own_unit(gc, seat, pile):
    """U6-1.7 S_OWN: `seat`'s first live soldier in unit order whose position is not PILE."""
    return next((u["id"] for u in battle_state(gc).get("units", []) if u.get("coop") == seat and u.get("faction") == 0
                 and not u.get("isOut") and (u.get("x"), u.get("y"), u.get("z")) != tuple(pile)), None)


def own_tile(host, client, actor_gc, uid, ev):
    """Own-tile row (U6-1.7): TU refill and a grenade in the left hand (both, client first), actor_gc's
    battle_open_inventory {uid}, a real click on STR_LEFT_HAND, a real click on STR_GROUND (0,0), the order's wait,
    battle_close_inventory. Returns the cells' reads; raises on a staging step (the row fails "staging")."""
    m = (host, client)
    ev["tu"] = G3F.guarded(f"staging {uid}", lambda: G3F.both(host, client, {"cmd": "battle_action", "action": "set_stat",
                                                                           "unit": uid, "refill": True}, ("tu",))["tu"], m)
    g = G3F.guarded(f"staging {uid}", lambda: G3F.both(host, client, {"cmd": "battle_give", "unit": uid, "item": "STR_GRENADE",
                                                                    "slot": "left", "clear_hands": True}, ("weaponId",)), m)
    ev["grenade"], ev["pos"] = g["weaponId"], [pos(host, uid), pos(client, uid)]
    b = before(host, client)
    r = actor_gc.cmd({"cmd": "battle_open_inventory", "unit": uid})
    ev["open"] = {k: r.get(k) for k in ("ok", "opened", "error")}
    opened = bool(r.get("opened")) and iv(actor_gc).get("unitId") == uid
    ground, tile = G(actor_gc), on_tile(IT(host), pos(host, uid))
    ev.update(ground=ground, tileIds=tile)
    if opened:
        p, d = {}, {}
        if pick_at(actor_gc, LH, 0, 0, ev["grenade"], p):
            drop_at(actor_gc, GROUND, 0, 0, d)
        ev.update(pick=p, drop=d, orderS=settle(host, client))
        ev["close"] = actor_gc.cmd({"cmd": "battle_close_inventory"}).get("ok")
        wait_until(lambda: "InventoryState" not in G3F.stack(actor_gc), CLICK_S)
    landed, ev["landS"] = wait_until(lambda: at_both(host, client, ev["grenade"], pos(host, uid)), LAND_S)
    ev["grenadeViews"] = views(host, client, ev["grenade"])
    return {"opened": opened, "ground": ground, "tile": tile, "landed": bool(landed), "before": b}


def lobby_e6(host, client, key):
    """BER.boot_e6's lobby with the key as a parameter: the client joins and takes the Alien team (gamemode 2)."""
    BER.raw.skirmish_host(host, key)
    BER.raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": BER.raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: BER.raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, BER.raw.CLIENT_PLAYER), "team": "Alien"})
    time.sleep(1)   # the change_team broadcast settles on the client (PSR PHASE 0)
    return r.get("gamemode")


def drive(host, client):
    """PSR drive_to_gm2_battlescape WITHOUT its last line (session.briefings_to_battlescape), then both briefings up."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert G3F.top(host) == "NewBattleState", f"host stack {G3F.stack(host)} (want NewBattleState on top)"
    r = host.cmd({"cmd": "newbattle_mission", "type": MISSION})
    assert r.get("ok"), f"newbattle_mission {MISSION}: {r}"
    host.ok({"cmd": "set_seed", "seed": SEED})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)


def bring_up(host, client, key, alien_player, tag, seat):
    """Spawn, the PvP lobby, the drive, both briefings, R0 on both (each before its own briefing closes)."""
    PAGE.clear()   # every pre-battle screen of this boot opens on ground page 0
    m = (host, client)
    G3F.guarded(tag, lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded(tag, lambda: host.ok({"cmd": "set_seed", "seed": SEED}), m)
    if alien_player == "client":
        gm = G3F.guarded(tag, lambda: lobby_e6(host, client, key), m)
    else:
        gm = G3F.guarded(tag, lambda: PF.start_pvp_skirmish_lobby(host, client, key, alien_player="host"), m)[0]
    G3F.guarded(tag, lambda: drive(host, client), m)
    R0 = {gc.name: G3F.guarded(tag, lambda gc=gc: r0(gc, seat), m) for gc in m}
    if R0["host"]["A"] is None or R0["host"]["A"] != R0["client"]["A"]:
        G3F.capture(tag, f"R0 {R0} (want one A on both)", m)
        raise G3F.Miss(tag)
    return {"gm": gm, "R0": R0, "A": R0["host"]["A"]}


def gear_cell(host, client, ctx):
    A = ctx["A"]
    got = [items_of(IT(host), A), items_of(IT(client), A)]
    want = [ctx["R0"]["host"]["A_START"], ctx["R0"]["client"]["A_START"]]
    inpile = sorted(set(want[0]) & set(ctx["PILE_IDS"]))
    return (got == want and want[0] == want[1] and not inpile,
            f"A's items host {got[0]} client {got[1]} (want A_START {want[0]} on both); A_START ids on the pile {inpile} (want none)")


def held_cells(host, client, iid, uid, slot, pile):
    vs = views(host, client, iid)
    return (all(owned(IT(gc), iid, uid, slot) for gc in (host, client)) and not at(IT(host), iid, pile)
            and not at(IT(client), iid, pile), f"{iid} host/client {vs} (want owner {uid}" + (f" in {slot}" if slot else "")
            + " on both, off the pile)")


# ===================== boot DA =====================


def setup_da(host, client):
    m = (host, client)
    ctx = bring_up(host, client, KEY, "client", "DA", 1)
    G3F.guarded("DA", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    up, ctx["hostScreenS"] = wait_until(lambda: PEQ.screen_up(host), SCREEN_S)
    if not up:
        G3F.capture("DA", "the host's pre-battle screen never came up", m)
        raise G3F.Miss("DA")
    v = iv(host)
    ctx.update(X=v.get("unitId"), PILE=tuple((es(host, "equip") or {}).get("pile") or ()), PILE_IDS=PEQ.ground_ids(v),
               cols={g["id"]: (g.get("x"), g.get("y")) for g in v.get("ground") or []})
    G3F.guarded("DA", lambda: session.dismiss_client_briefing(client), m)
    _, ctx["clientTopS"] = wait_until(lambda: (es(client, "equip") or {}).get("entryDone")
                                      and G3F.top(client) != "BattlescapeState", SCREEN_S)
    ctx["CENSUS0"] = census(host)
    ctx["census0Client"] = census(client) == ctx["CENSUS0"]
    reads(ctx, host, host)
    return ctx


def row_ae1(host, client, ctx, crash0):
    A, v = ctx["A"], iv(client)
    cnt = ((es(host, "equip") or {}).get("counted") or [])[:2]
    ev = {k: ctx[k] for k in ("gm", "R0", "X", "PILE", "PILE_IDS", "cols", "PISTOL", "RIFLE", "BP0", "BACKPACK_CELL",
                              "X_CELL", "types", "hostScreenS", "clientTopS", "census0Client")}
    ev.update(clientView=PEQ.view_brief(v), stacks=[G3F.stack(host), G3F.stack(client)],
              equip=[es(host, "equip"), es(client, "equip")])
    return {"AE1-counted": (cnt == [True, True], f"host equip.counted[:2] {cnt} (want [true, true])"),
            "AE1-screen": (G3F.top(client) == "InventoryState" and screen_on(client, A),
                           f"client top {G3F.top(client)}, inventory_view {PEQ.view_brief(v)} (want the pre-battle "
                           f"InventoryState on {A}; {ctx['clientTopS']} s)"),
            "AE1-ground": (G(client) == ctx["PILE_IDS"], f"G(client) {G(client)} (want PILE_IDS {ctx['PILE_IDS']})"),
            "AE1-gear": gear_cell(host, client, ctx),
            "AE1-common": G3F.common(host, client, crash0)}, ev


def row_ae2(host, client, ctx, crash0):
    A, bc, m = ctx["A"], ctx["BACKPACK_CELL"], (host, client)
    b, ev = before(host, client), {"candidate": ctx["RIFLE"], "cell": bc}
    if screen_on(client, A) and bc is not None:
        cand = rifle_choice(client, IT(client), A, ctx["BP0"])
        p, d = {}, {}
        got = pick_ground(client, cand, p)
        if got is not None:
            ctx["RIFLE"] = got
            drop_at(client, BACK, bc[0], bc[1], d)
            ev["orderS"] = settle(host, client)
            ev["landS"] = wait_until(lambda: all(owned(IT(gc), got, A, BACK) for gc in m), LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the client on {A} (top {G3F.top(client)})"
    R = ctx["RIFLE"]
    gone = screen_on(host, ctx["X"]) and R not in G(host)
    return {"AE2-order": order_cell(host, client, b, A),
            "AE2-held": held_cells(host, client, R, A, BACK, ctx["PILE"]),
            "AE2-gone": (gone, f"host screen on {ctx['X']} {screen_on(host, ctx['X'])}; RIFLE {R} in G(host) {R in G(host)} "
                         f"(want the screen up and RIFLE gone from it)"),
            "AE2-common": G3F.common(host, client, crash0)}, ev


def row_ae3(host, client, ctx, crash0):
    A, P = ctx["A"], ctx["PISTOL"]
    b, ev = before(host, client), {"PISTOL": P}
    s = ctx["R0"]["client"]["A_START"].get(P) or (None, 0, 0)
    if screen_on(client, A):
        p, d = {}, {}
        if pick_at(client, s[0], s[1], s[2], P, p):
            drop_ground(client, IT(client), d)
            ev["orderS"] = settle(host, client)
            ev["landS"] = wait_until(lambda: at_both(host, client, P, ctx["PILE"]), LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the client on {A} (top {G3F.top(client)})"
    return {"AE3-order": order_cell(host, client, b, A),
            "AE3-pile": (at_both(host, client, P, ctx["PILE"]), f"PISTOL {P} host/client {views(host, client, P)} (want at "
                         f"PILE {ctx['PILE']} on both)"),
            "AE3-seen": (P in G(host), f"PISTOL {P} in G(host) {P in G(host)} (want true: the X-COM player sees the drop)"),
            "AE3-common": G3F.common(host, client, crash0)}, ev


def row_ae4(host, client, ctx, crash0):
    A, P, H1, xc, m = ctx["A"], ctx["PISTOL"], ctx["X"], ctx["X_CELL"], (host, client)
    ev = {"PISTOL": P, "H1_CELL": xc}
    if screen_on(host, H1) and P in G(host) and xc is not None:
        p, d = {}, {}
        got = pick_ground(host, P, p)
        if got is not None:
            drop_at(host, BACK, xc[0], xc[1], d)
            ev["drainS"] = drained(host, client)
            ev["landS"] = wait_until(lambda: all(owned(IT(gc), P, H1) for gc in m), LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no PISTOL {P} on the host's ground (screen on {H1} {screen_on(host, H1)})"
    gone = screen_on(client, A) and P not in G(client)
    return {"AE4-held": held_cells(host, client, P, H1, None, ctx["PILE"]),
            "AE4-gone": (gone, f"client screen on {A} {screen_on(client, A)}; PISTOL {P} in G(client) {P in G(client)} (want "
                         f"the screen up and PISTOL gone from it)"),
            "AE4-common": G3F.common(host, client, crash0)}, ev


def row_ae5(host, client, ctx, crash0):
    A, P, H1, xc = ctx["A"], ctx["PISTOL"], ctx["X"], ctx["X_CELL"]
    ev = {"PISTOL": P}
    if screen_on(host, H1) and owned(IT(host), P, H1, BACK) and xc is not None:
        p, d = {}, {}
        if pick_at(host, BACK, xc[0], xc[1], P, p):
            drop_ground(host, IT(host), d)
            ev["drainS"] = drained(host, client)
            ev["landS"] = wait_until(lambda: at_both(host, client, P, ctx["PILE"]), LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"PISTOL {P} is not on H1 {H1} (host {PEQ.item_view(IT(host), P)})"
    seen = screen_on(client, A) and P in G(client)
    return {"AE5-pile": (at_both(host, client, P, ctx["PILE"]), f"PISTOL {P} host/client {views(host, client, P)} (want at "
                         f"PILE on both)"),
            "AE5-seen": (seen, f"client screen on {A} {screen_on(client, A)}; PISTOL {P} in G(client) {P in G(client)} "
                         f"(want both true)"),
            "AE5-common": G3F.common(host, client, crash0)}, ev


def row_ae6(host, client, ctx, crash0):
    A, R, bc = ctx["A"], ctx["RIFLE"], ctx["BACKPACK_CELL"]
    b, ev = before(host, client), {"RIFLE": R}
    if screen_on(client, A) and owned(IT(client), R, A, BACK) and bc is not None:
        p, d = {}, {}
        if pick_at(client, BACK, bc[0], bc[1], R, p):
            drop_ground(client, IT(client), d)
            ev["orderS"] = settle(host, client)
            ev["landS"] = wait_until(lambda: at_both(host, client, R, ctx["PILE"]), LAND_S)[1]
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the client with RIFLE {R} on A (client {PEQ.item_view(IT(client), R)})"
    ok, detail = order_cell(host, client, b, A)
    back = at_both(host, client, R, ctx["PILE"])
    return {"AE6-back": (ok and back, f"{detail}; RIFLE {R} host/client {views(host, client, R)} (want at PILE on both)"),
            "AE6-seen": (ok and R in G(host), f"AE6's order admitted {ok}; RIFLE {R} in G(host) {R in G(host)} (want both)"),
            "AE6-common": G3F.common(host, client, crash0)}, ev


def row_ae7(host, client, ctx, crash0):
    A, R, bc = ctx["A"], ctx["RIFLE"], ctx["BACKPACK_CELL"]
    ev = {"RIFLE": R}
    if screen_on(client, A) and R in G(client) and bc is not None:
        p, d = {}, {}
        if pick_ground(client, R, p) is not None:
            drop_at(client, BACK, bc[0], bc[1], d)
            ev["orderS"] = settle(host, client)
        ev.update(pick=p, drop=d)
    else:
        ev["step"] = f"no pre-battle screen on the client with RIFLE {R} on its ground"
    turn = barrier(host, client, host, client, ev)
    hashed = G3F.hash_now(host, client)
    ps = [pos(host, A), pos(client, A)]
    held = all(owned(IT(gc), R, A) for gc in (host, client))
    return {"AE7-turn": turn,
            "AE7-held": (held and ps == [ctx["R0"]["host"]["A_SPAWN"]] * 2 and hashed == "all buckets EQUAL",
                         f"RIFLE {R} host/client {views(host, client, R)} (want owner {A}); A at {ps} (want A_SPAWN "
                         f"{ctx['R0']['host']['A_SPAWN']} on both); hash {hashed}"),
            "AE7-census": census_cell(host, client, ctx["CENSUS0"]),
            "AE7-common": G3F.common(host, client, crash0, hashed)}, ev


def row_ae8(host, client, ctx, crash0):
    s = own_unit(host, 0, ctx["PILE"])
    ev = {"S_OWN": s, "sideTurn": [(battle_state(gc).get("side"), battle_state(gc).get("turn")) for gc in (host, client)]}
    if s is None:
        raise AssertionError(f"staging: no host soldier off the pile {ctx['PILE']}")
    r = own_tile(host, client, host, s, ev)
    return {"AE8-ground": (r["opened"] and r["ground"] == r["tile"], f"host inventory opened {r['opened']} {ev['open']}; "
                           f"G(host) {r['ground']} (want the ids on S_OWN's tile {r['tile']})"),
            "AE8-tile": (r["landed"], f"grenade {ev['grenade']} host/client {ev['grenadeViews']} (want at S_OWN's "
                         f"position {ev['pos'][0]} on both)"),
            "AE8-common": G3F.common(host, client, crash0)}, ev


def row_ae9(host, client, ctx, crash0):
    A, ev = ctx["A"], {}
    try:
        RM.side_change(host, client, host, 1, 1, ev)
    except Exception as e:
        raise AssertionError(f"staging: the host's END TURN: {str(e)[:300]}")
    r = own_tile(host, client, client, A, ev)
    return {"AE9-ground": (r["opened"] and r["ground"] == r["tile"], f"client inventory opened {r['opened']} {ev['open']}; "
                           f"G(client) {r['ground']} (want the ids on A's tile in IT(host) {r['tile']})"),
            "AE9-order": order_cell(host, client, r["before"], A),
            "AE9-tile": (r["landed"], f"grenade {ev['grenade']} host/client {ev['grenadeViews']} (want at A's position "
                         f"{ev['pos'][0]} on both)"),
            "AE9-common": G3F.common(host, client, crash0)}, ev


FN = {"AE1": row_ae1, "AE2": row_ae2, "AE3": row_ae3, "AE4": row_ae4, "AE5": row_ae5, "AE6": row_ae6, "AE7": row_ae7,
      "AE8": row_ae8, "AE9": row_ae9}


def run_boot(tag, rows, fns, setup, host_dir, client_dir):
    """One boot: setup (a Miss fails every row "boot"), then every row in order, each after any failure."""
    host = GameClient("host", None, make_user_dir(host_dir))
    client = GameClient("client", None, make_user_dir(client_dir))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            ctx = setup(host, client)
        except G3F.Miss:
            return G3F.fail_all(rows, f"boot (FIXTURE-STOP, see the CAPTURE {tag} line)")
        return sum(G3F.run_row(row, order, lambda r=row: fns[r](host, client, ctx, crash0)) for row, order in rows)
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = run_boot("DA", ROWS, FN, setup_da, "r5u6_da_host", "r5u6_da_client")
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_alien_equip: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
