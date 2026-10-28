"""test_equip_partner_view.py: the pre-battle equip screen shows the partner's soldiers READ-ONLY.

Owner D288 (b) (equip design session D287): on the pre-battle equip screen PREV / NEXT step through every player-side
soldier with an inventory, this player's AND the partner's, in unit order, as the release line does; a partner's soldier
is shown read-only - an "Owner: <name>" line, UNLOAD / copy / paste hidden, and every click, tool and rename on it does
nothing. Not in battle; never between PvP opponents; a player with no soldier of its own
still skips the screen. Spec docs rewrite/prompts/eq1_partner_soldiers_readonly.md ((f), PINNED SETUP VALUES,
QEQ1-1 .. QEQ1-6 (a), VL-EQ1-1 .. VL-EQ1-8); every pin is TASK 0's (docs rewrite/eq1-task0/sa/CONSTANTS.md).

Boot V (ONE boot): S0 the roster-pinned lobby + session.bring_up_to_briefings (seat_count 2, set_seed SEED_MAP before
newbattle_ok; MAP_FP, C_IDS, H_IDS asserted). S1 staging with both machines holding the battle (D210 b; client first,
F607): C1 and H1 stripped; H1 = a loaded rifle (STR_RIGHT_HAND) + a grenade (STR_BELT 0,0); C1 = a loaded pistol
(STR_LEFT_HAND) + a smoke grenade (STR_BELT 1,0); one rifle clip dropped on PILE. S2 both screens up (client C1, host H1).
  PV1 / PV2  client / host cycle: NEXT x N_ALL from C1 / H1 = CYCLE_C / CYCLE_H; PREV = its [-2]; NEXT back. next, prev
  PV3 / PV6  client look on H1 / host look on C1: "Owner: HOST_NAME" / "Owner: CLIENT_NAME" visible, UNLOAD / copy /
             paste hidden.                                                                   reach, owner, buttons
  PV4  client clicks on H1 (pick, the pile clip, right click on the belt grenade, Shift-click + UNLOAD): no cursor item,
       no dialog, nothing moves or is sent.                                      pick, ground, prime, unload, sent
  PV5  client tools on H1 (clear, auto-equip, personal load / save, Ctrl+1, 1, F5, F9, copy / paste, the rename): nothing
       changes, no dialog, nothing sent; back on C1 the own look.  layout, personal, global, dialogs, rename, sent, back
  PV7  host on C1: pick, right click, personal save, Ctrl+1, clear / auto / load / 1, the rename.  pick, prime, personal,
       global, tools, rename
  PV8  the client moves C1's smoke grenade while the host views C1, the host moves H1's grenade while the client views
       H1: each lands on the viewer; forceCloseSkips unchanged; buckets equal.                  host, client, skips, hash
  PV9  turn 1 from partner views (host on C1, client on H1, both OK): turn 1, own selections. reach, turn, select, hash
RED (EQ-1 S-A, product untouched): exit 2, all 36 cells FAIL - PV1 / PV2 on their values (own-only cycles), PV3 .. PV9
"partner view not reached" (their other cells "not reached"); the spine passes. GREEN: exit 0, 36 / 36.
One EVIDENCE line per row, one PASS/FAIL line per cell, then the row verdict; every row runs after a failure. A boot miss
fails every row "boot" with ONE CAPTURE line. Cleanup inside a row (never needed at green): a cursor item ->
inventory_cursor_clear, a dialog -> ESC, each recorded. one foreground run is the result, no
skip path, no second boot. Exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_equip_partner_view.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state
from test_prebattle_equip import (
    SEED_MAP, MAP_FP, C_IDS, H_IDS, PILE, COOP_SEAT_0, FACTION_PLAYER, BELT, RIGHT_HAND, LEFT_HAND, BACK_PACK, GROUND,
    GROUND_COLS, RIFLE_T, CLIP_T, GRENADE_T, NAME_CLICK, UNFOCUS_CLICK, RENAME_LETTER, KEY_SETTLE_S, CLICK_WAIT_S,
    LAND_WAIT_S, TURN_WAIT_S, DRAIN_WAIT_S, ENTRY_WAIT_S, EQ1_WAIT_S, ANSWER_WAIT_S, SDLK_RETURN, click, inv_view,
    next_press, goto_unit, wait_until, evidence, stack, top, has, es, equip, turn, in_battle, drained, ammo_of, cell_of,
    pile_ids, strip_both, both, diff_buckets, items_by_id, bring_up_lobby_roster_pinned, short)

# ----- pins (TASK 0, docs rewrite/eq1-task0/sa/CONSTANTS.md: boots a = b, boot c green) -----
PORT = "49281"                     # this file's lobby key
DIRS = ("eq1_v_host", "eq1_v_client")
C1 = C_IDS[0]                      # 8: the client's first seated unit, its screen opens on it
H1 = 10                            # the host screen's first unit at S2
N_ALL = len(C_IDS) + len(H_IDS)    # 7: every player-side soldier with an inventory
CYCLE_C = [9, 10, 11, 12, 13, 14, 8]      # the client's NEXT order from C1 (unit order; boot c)
CYCLE_H = [11, 12, 13, 14, 8, 9, 10]      # the host's NEXT order from H1 (boot c)
OWNER_RECT = (28, 18, 210, 17)     # E10's owner line (list_widgets: a Text)
BUTTON_RECTS = {"unload": (288, 32, 32, 25), "create": (288, 90, 32, 22), "apply": (288, 113, 32, 22)}
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"   # the D216 lines at boots a / b; the owner lines at boot c
OWNER_TEXT = "Owner: {}"           # STR_COOP_EQUIP_OWNER (en-US)
PISTOL_T, PISTOL_CLIP_T, SMOKE_T = "STR_PISTOL", "STR_PISTOL_CLIP", "STR_SMOKE_GRENADE"
KEY_CLEAR, KEY_AUTO, KEY_LOAD_P, KEY_SAVE_P = 120, 122, 108, 115   # equip_layouts.keys at boots a / b
SDLK_1, SDLK_F5, SDLK_F9, SDLK_ESCAPE = 49, 286, 290, 27  # global layout 0; F5 / F9 open the save / load dialogs (boot a)
SETTLE_S = 1.0                     # the read after a refused tool / rename (boot p shows each change within it)
ROWS = (("PV1", ("next", "prev")), ("PV2", ("next", "prev")), ("PV3", ("reach", "owner", "buttons")),
        ("PV4", ("pick", "ground", "prime", "unload", "sent")),
        ("PV5", ("layout", "personal", "global", "dialogs", "rename", "sent", "back")),
        ("PV6", ("reach", "owner", "buttons")), ("PV7", ("pick", "prime", "personal", "global", "tools", "rename")),
        ("PV8", ("host", "client", "skips", "hash")), ("PV9", ("reach", "turn", "select", "hash")))

class Row:
    def __init__(self, name, cells):
        self.name, self.cells, self.res, self.ev = name, [f"{name}-{c}" for c in cells], {}, {}

    def cell(self, c, ok, msg=""):
        self.res.setdefault(f"{self.name}-{c}", (bool(ok), msg))

    def unreached(self, why):
        for c in self.cells:
            self.res.setdefault(c, (False, why))

def unit_items(its, uid):
    """`uid`'s items: {id: [type, slot, slotX, slotY, loaded ammo ids]}."""
    return {i: [it.get("type"), it.get("slot"), it.get("slotX"), it.get("slotY"), ammo_of(it, i)]
            for i, it in its.items() if it.get("owner") == uid and it.get("slot")}

def snap(host, client, uid):
    ih, ic = items_by_id(host), items_by_id(client)
    return {"items": [unit_items(ih, uid), unit_items(ic, uid)], "pile": [pile_ids(ih), pile_ids(ic)],
            "sent": es(client).get("coopIntentsSent")}

def fuses(host, client, iid):
    return [(items_by_id(gc).get(iid) or {}).get("fuse") for gc in (host, client)]

def names(host, client, uid):
    return [[(session.units_by_id(battle_state(gc)).get(uid) or {}).get(k) for k in ("name", "_name", "rawName")]
            for gc in (host, client)]

def layouts(host, client, uid):
    out = []
    for gc in (host, client):
        r = gc.cmd({"cmd": "equip_layouts", "index": 0, "unit": uid})
        out.append({"personal": r.get("personal"), "global": r.get("global")})
    return out

def counters(host, client):
    try:
        eh, ec = es(host), es(client)
        return {"sent": ec.get("coopIntentsSent"), "renames": (eh.get("renames") or {}).get("applied"),
                "skips": (ec.get("equip") or {}).get("forceCloseSkips"), "hostTurn": turn(host)}
    except Exception as e:  # a dead instance
        return {"error": short(e, 120)}

def look(gc):
    """The owner line (every Text at OWNER_RECT: [visible, text]) and the three buttons' `visible` (list_widgets)."""
    ws = gc.cmd({"cmd": "list_widgets"}).get("widgets") or []

    rect = lambda w: (w.get("x"), w.get("y"), w.get("w"), w.get("h"))  # noqa: E731
    owner = [[w.get("visible"), w.get("text")] for w in ws
             if rect(w) == OWNER_RECT and str(w.get("type")).split("::")[-1] == "Text"]
    buttons = {n: [w.get("visible") for w in ws if rect(w) == r and w.get("interactive")] for n, r in BUTTON_RECTS.items()}
    return {"owner": owner, "buttons": buttons, "unitId": inv_view(gc).get("unitId"), "top": top(gc)}

def key(gc, sym, mod=None):
    r = gc.cmd(dict({"cmd": "inject_input", "kind": "key", "key": sym}, **({"mod": mod} if mod else {})))
    time.sleep(KEY_SETTLE_S)
    if mod:
        gc.cmd({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    return r.get("error") or r.get("ok")

def rename(gc):
    """PEQ's rename recipe (P8-4c T0-R2): click the name field, one letter, click off it."""
    out = []
    for req in ({"kind": "click", "x": NAME_CLICK[0], "y": NAME_CLICK[1]}, {"kind": "key", "key": RENAME_LETTER[1]},
                {"kind": "click", "x": UNFOCUS_CLICK[0], "y": UNFOCUS_CLICK[1]}):
        out.append(gc.cmd(dict(req, cmd="inject_input")).get("ok"))
        time.sleep(KEY_SETTLE_S)
    return out

def cursor_after(gc):
    """Wait (bounded, CLICK_WAIT_S) for an item on the cursor; -1 when none came."""
    wait_until(lambda: inv_view(gc).get("selectedItem") not in (None, -1), CLICK_WAIT_S)
    return inv_view(gc).get("selectedItem")

def top_after(gc):
    """Wait (bounded) for another state over the screen; the top state then."""
    wait_until(lambda: top(gc) != "InventoryState", CLICK_WAIT_S)
    return top(gc)

def cleanup(gc, rec):
    """Never needed at green: a dialog over the screen -> ESC (never with the screen on top: there ESC is OK), then an
    item on the cursor -> inventory_cursor_clear. Each recorded."""
    for _ in range(3):
        t = top(gc)
        if t == "InventoryState":
            break
        rec.append({"esc": t, "ok": gc.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE}).get("ok")})
        wait_until(lambda: top(gc) == "InventoryState", CLICK_WAIT_S)
    if inv_view(gc).get("selectedItem") not in (None, -1):
        rec.append({"cursorCleared": gc.cmd({"cmd": "inventory_cursor_clear"}).get("cleared")})

def settle(host, client):
    time.sleep(SETTLE_S)
    wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)

def reach(gc, uid, own, row, cell=None):
    """The screen on `uid` (goto_unit's walk). False: `cell` fails and every other cell of the row is 'not reached'."""
    nav = []
    ok = goto_unit(gc, uid, own, nav) and inv_view(gc).get("unitId") == uid
    row.ev.setdefault("nav", {})[f"{gc.name}->{uid}"] = [p["to"] for p in nav]
    if ok:
        if cell:
            row.cell(cell, True)
        return True
    why = (f"partner view not reached: {gc.name} PREV/NEXT never showed {uid} (visited {[p['to'] for p in nav]}, "
           f"unitId {inv_view(gc).get('unitId')})")
    if cell:
        row.cell(cell, False, why)
    row.unreached(f"not reached ({why})")
    return False

def move(gc, iid, slot, xy, rec):
    """Two real clicks: pick `iid` from slot (x, y), drop it on STR_BACK_PACK (0, 0)."""
    rec["pick"] = click(gc, slot=slot, x=xy[0], y=xy[1])
    got, _ = wait_until(lambda: inv_view(gc).get("selectedItem") == iid, CLICK_WAIT_S)
    rec["picked"] = inv_view(gc).get("selectedItem")
    if got:
        rec["drop"] = click(gc, slot=BACK_PACK, x=0, y=0)
        wait_until(lambda: inv_view(gc).get("selectedItem") == -1, CLICK_WAIT_S)
    return rec

def in_pack(gc, iid, uid):
    it = items_by_id(gc).get(iid) or {}
    return it.get("owner") == uid and it.get("slot") == BACK_PACK and (it.get("slotX"), it.get("slotY")) == (0, 0)

def hash_cell(host, client, row):
    got, _ = wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    d = diff_buckets(host, client)
    row.ev["diff"] = d
    row.cell("hash", got and not d, f"drained {bool(got)}, hash_now buckets differ: {d} (want drained, every bucket EQUAL)")

def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.bring_up_to_briefings(host, client, seated, seat_count=2,
                                  pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hb = battle_state(host)
    assert hb.get("mapFingerprint") == MAP_FP, f"host mapFingerprint {hb.get('mapFingerprint')!r} (want {MAP_FP!r})"
    sid_to_uid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    seated_uids = [sid_to_uid.get(s) for s in seated.get("soldierIds", [])]
    assert seated_uids == C_IDS, f"seated client units {seated_uids} (want C {C_IDS})"
    h_ids = sorted(u["id"] for u in hb["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids == H_IDS, f"host-seat soldiers {h_ids} (want H {H_IDS})"
    print(f"[eq1] boot ok: MAP_FP={MAP_FP!r} seated={seated_uids} H={h_ids}", flush=True)

def s1_stage(host, client, ctx):
    got, dt = wait_until(lambda: has(client, "BriefingState") and in_battle(client) and in_battle(host), EQ1_WAIT_S, 0.1)
    rec = {"bothBriefingsWithin": dt if got else None, "stacks": [stack(host), stack(client)]}
    ctx["s1"] = rec
    if not got:
        raise AssertionError(f"S1: both machines do not hold the battle with their briefings up ({rec})")
    session.wait_seq_barrier(host, client)  # the host's first evs applied before staging
    rec["stripped"] = {uid: strip_both(host, client, uid) for uid in (C1, H1)}
    ids = {}
    for name, uid, t, extra in (("rifle", H1, RIFLE_T, {"ammo": CLIP_T}),
                                ("grenade", H1, GRENADE_T, {"slot": BELT, "slotX": 0, "slotY": 0}),
                                ("pistol", C1, PISTOL_T, {"slot": "left", "ammo": PISTOL_CLIP_T}),
                                ("smoke", C1, SMOKE_T, {"slot": BELT, "slotX": 1, "slotY": 0})):
        r = both(host, client, dict({"cmd": "battle_give", "unit": uid, "item": t}, **extra),
                 ("weaponId", "ammoId", "weaponSlot"))
        ids[name] = r["weaponId"]
        if extra.get("ammo"):
            ids[name + "Clip"] = r["ammoId"]
    d = both(host, client, {"cmd": "battle_drop", "x": PILE[0], "y": PILE[1], "z": PILE[2], "item": CLIP_T}, ("ids",))
    ids["pileClip"] = d["ids"][0]
    rec["ids"] = ids
    ih, ic = items_by_id(host), items_by_id(client)
    rec["units"] = {uid: [unit_items(ih, uid), unit_items(ic, uid)] for uid in (C1, H1)}
    rec["fuses"] = {n: fuses(host, client, ids[n]) for n in ("grenade", "smoke")}
    rec["diff"] = diff_buckets(host, client)
    if rec["diff"]:
        raise AssertionError(f"S1: buckets differ after the staging: {rec['diff']}")
    ctx["ids"] = ids

def s2_screens(host, client, ctx):
    rec = {"clientClose": client.cmd({"cmd": "close_briefing"}).get("ok")}
    ctx["s2"] = rec

    up = lambda gc: inv_view(gc).get("preBattle") is True and inv_view(gc).get("top") is True  # noqa: E731
    g1, rec["clientScreenWithin"] = wait_until(lambda: up(client), ENTRY_WAIT_S)
    rec["hostClose"] = host.cmd({"cmd": "close_briefing"}).get("ok")
    g2, rec["hostScreenWithin"] = wait_until(lambda: up(host), 10.0)
    g3, rec["announcedWithin"] = wait_until(lambda: equip(host).get("openAnnounced") is True, ANSWER_WAIT_S)
    rec["views"] = [inv_view(host), inv_view(client)]
    if not (g1 and g2 and g3):
        raise AssertionError(f"S2: the pre-battle screens are not both up and announced ({rec})")
    got = [(v.get("unitId"), v.get("selectedItem")) for v in rec["views"]]
    if got != [(H1, -1), (C1, -1)]:
        raise AssertionError(f"S2: host / client (unitId, cursor) {got} (want ({H1}, -1) / ({C1}, -1))")

def cycle_row(gc, start, cycle, row):
    ev, presses = row.ev, []
    ev["start"] = inv_view(gc).get("unitId")
    for _ in range(N_ALL):
        next_press(gc, presses)
    ev["seen"] = seen = [p["to"] for p in presses]
    row.cell("next", ev["start"] == start and seen == cycle,
             f"{gc.name} NEXT x{N_ALL} from {ev['start']} visited {seen} (want {cycle} from {start}: every player-side "
             f"soldier, own and partner's, unit order)")
    ev["prevClick"] = click(gc, widget="prev")
    wait_until(lambda: inv_view(gc).get("unitId") != seen[-1], CLICK_WAIT_S)
    ev["prev"] = inv_view(gc).get("unitId")
    row.cell("prev", ev["prev"] == cycle[-2], f"{gc.name} PREV -> {ev['prev']} (want {cycle[-2]})")
    ev["back"] = next_press(gc, [])

def look_row(gc, uid, own, want_text, row):
    if not reach(gc, uid, own, row, "reach"):
        return
    time.sleep(KEY_SETTLE_S)
    row.ev["look"] = lk = look(gc)
    row.cell("owner", lk["owner"] == [[True, want_text]],
             f"the Text at {OWNER_RECT} [visible, caption] = {lk['owner']} (want [[True, {want_text!r}]])")
    row.cell("buttons", lk["buttons"] == {n: [False] for n in BUTTON_RECTS},
             f"UNLOAD / copy / paste visible = {lk['buttons']} (want each hidden)")

def pv4(host, client, ctx, row):
    if not reach(client, H1, C_IDS, row):
        return
    ids, ev, clean = ctx["ids"], row.ev, []
    ev["cleanup"] = clean
    ev["before"] = b = snap(host, client, H1)
    ev["pick"] = {"click": click(client, slot=RIGHT_HAND), "cursor": cursor_after(client)}
    a = snap(host, client, H1)
    row.cell("pick", ev["pick"]["cursor"] == -1 and a["items"] == b["items"],
             f"left click on H1's {RIGHT_HAND}: client cursor {ev['pick']['cursor']}, H1 {b['items']} -> {a['items']} "
             f"(want cursor -1, H1 unchanged on both)")
    cleanup(client, clean)
    cell = cell_of(inv_view(client), ids["pileClip"])
    ev["ground"] = {"cell": cell}
    if cell is None or cell[0] is None or cell[0] >= GROUND_COLS:
        row.cell("ground", False, f"FIXTURE - the staged clip {ids['pileClip']} is not on the first ground page ({cell})")
    else:
        ev["ground"].update(click=click(client, slot=GROUND, x=cell[0], y=cell[1]), cursor=cursor_after(client))
        a = snap(host, client, H1)
        row.cell("ground", ev["ground"]["cursor"] == -1 and a["pile"] == b["pile"],
                 f"left click on the pile clip: client cursor {ev['ground']['cursor']}, pile {b['pile']} -> {a['pile']} "
                 f"(want cursor -1, the pile unchanged on both)")
    cleanup(client, clean)
    ev["prime"] = {"click": click(client, slot=BELT, x=0, y=0, button="right"), "top": top_after(client)}
    ev["prime"]["fuse"] = fuses(host, client, ids["grenade"])
    row.cell("prime", ev["prime"]["top"] == "InventoryState" and ev["prime"]["fuse"] == [-1, -1],
             f"right click on H1's belt grenade: client top {ev['prime']['top']}, fuse host/client {ev['prime']['fuse']} "
             f"(want InventoryState on top, fuse -1 on both)")
    cleanup(client, clean)
    ev["unload"] = {"shift": click(client, slot=RIGHT_HAND, mod="shift")}
    time.sleep(KEY_SETTLE_S)
    ev["unload"]["widget"] = click(client, widget="unload")
    cleanup(client, clean)
    settle(host, client)
    ev["unload"]["ammo"] = ammo = [ammo_of(items_by_id(gc).get(ids["rifle"]), ids["rifle"]) for gc in (host, client)]
    row.cell("unload", ammo == [[ids["rifleClip"]]] * 2,
             f"Shift-click + UNLOAD on H1's rifle: its ammo host/client {ammo} (want [{ids['rifleClip']}] on both)")
    cleanup(client, clean)
    ev["after"] = a = snap(host, client, H1)
    row.cell("sent", a["sent"] == b["sent"], f"client coopIntentsSent {b['sent']} -> {a['sent']} (want unchanged)")

def pv5(host, client, ctx, row):
    if not reach(client, H1, C_IDS, row):
        return
    ev, clean, p, dialogs = row.ev, [], {}, {}
    ev["cleanup"] = clean
    b, lb, nb, rb = snap(host, client, H1), layouts(host, client, H1), names(host, client, H1), counters(host, client)
    ev["before"] = {"snap": b, "layouts": lb, "names": nb, "counters": rb}
    for n, sym, mod in (("clear", KEY_CLEAR, None), ("auto", KEY_AUTO, None), ("loadP", KEY_LOAD_P, None),
                        ("saveP", KEY_SAVE_P, None), ("ctrl1", SDLK_1, "ctrl"), ("1", SDLK_1, None)):
        p[n] = key(client, sym, mod)
    for n, sym in (("F5", SDLK_F5), ("F9", SDLK_F9)):
        p[n] = key(client, sym)
        dialogs[n] = top_after(client)
        cleanup(client, clean)
    for w in ("create_template", "apply_template"):
        p[w] = click(client, widget=w)
        time.sleep(KEY_SETTLE_S)
    cleanup(client, clean)
    p["rename"] = rename(client)
    settle(host, client)
    cleanup(client, clean)
    a, la, na, ra = snap(host, client, H1), layouts(host, client, H1), names(host, client, H1), counters(host, client)
    ev.update(presses=p, dialogs=dialogs, after={"snap": a, "layouts": la, "names": na, "counters": ra})
    row.cell("layout", a["items"] == b["items"], f"H1's items host/client {b['items']} -> {a['items']} (want unchanged)")
    pers = [[x["personal"] for x in lb], [x["personal"] for x in la]]
    row.cell("personal", pers[0] == pers[1], f"H1's personal layout host/client {pers[0]} -> {pers[1]} (want unchanged)")
    glob = [[x["global"] for x in lb], [x["global"] for x in la]]
    row.cell("global", glob[0] == glob[1], f"global layout 0 host/client {glob[0]} -> {glob[1]} (want unchanged)")
    row.cell("dialogs", dialogs == {"F5": "InventoryState", "F9": "InventoryState"},
             f"the top after F5 / F9 {dialogs} (want InventoryState: no dialog)")
    row.cell("rename", na == nb and ra.get("renames") == rb.get("renames"),
             f"H1's names host/client {nb} -> {na}, host renames.applied {rb.get('renames')} -> {ra.get('renames')} "
             f"(want unchanged)")
    row.cell("sent", a["sent"] == b["sent"], f"client coopIntentsSent {b['sent']} -> {a['sent']} (want unchanged)")
    nav = []
    ev["backReached"] = goto_unit(client, C1, C_IDS, nav)
    time.sleep(KEY_SETTLE_S)
    ev["back"] = lk = look(client)
    own_ok = all(not v for v, _ in lk["owner"]) and lk["buttons"] == {n: [True] for n in BUTTON_RECTS}
    row.cell("back", ev["backReached"] and lk["unitId"] == C1 and own_ok,
             f"back on C1 ({[x['to'] for x in nav]}): unitId {lk['unitId']}, owner line {lk['owner']}, buttons "
             f"{lk['buttons']} (want C1, no visible owner line, the three buttons visible)")

def pv7(host, client, ctx, row):
    if not reach(host, C1, H_IDS, row):
        return
    ids, ev, clean = ctx["ids"], row.ev, []
    ev["cleanup"] = clean
    ev["before"] = b = snap(host, client, C1)
    ev["pick"] = {"click": click(host, slot=LEFT_HAND), "cursor": cursor_after(host)}
    a = snap(host, client, C1)
    row.cell("pick", ev["pick"]["cursor"] == -1 and a["items"] == b["items"],
             f"host left click on C1's {LEFT_HAND}: host cursor {ev['pick']['cursor']}, C1 {b['items']} -> {a['items']} "
             f"(want cursor -1, C1 unchanged on both)")
    cleanup(host, clean)
    ev["prime"] = {"click": click(host, slot=BELT, x=1, y=0, button="right"), "top": top_after(host)}
    ev["prime"]["fuse"] = fuses(host, client, ids["smoke"])
    row.cell("prime", ev["prime"]["top"] == "InventoryState" and ev["prime"]["fuse"] == [-1, -1],
             f"host right click on C1's belt smoke grenade: host top {ev['prime']['top']}, fuse host/client "
             f"{ev['prime']['fuse']} (want InventoryState on top, fuse -1 on both)")
    cleanup(host, clean)
    lb = layouts(host, client, C1)
    ev["saveP"] = key(host, KEY_SAVE_P)
    settle(host, client)
    la = layouts(host, client, C1)
    pers = [[x["personal"] for x in lb], [x["personal"] for x in la]]
    row.cell("personal", pers[0] == pers[1], f"C1's personal layout host/client {pers[0]} -> {pers[1]} (want unchanged)")
    ev["ctrl1"] = key(host, SDLK_1, mod="ctrl")
    settle(host, client)
    g = [lb[0]["global"], layouts(host, client, C1)[0]["global"]]
    row.cell("global", g[0] == g[1], f"the host's global layout 0 {g[0]} -> {g[1]} (want unchanged)")
    b2 = snap(host, client, C1)
    ev["tools"] = {n: key(host, s) for n, s in (("clear", KEY_CLEAR), ("auto", KEY_AUTO), ("loadP", KEY_LOAD_P),
                                                 ("1", SDLK_1))}
    settle(host, client)
    cleanup(host, clean)
    a = snap(host, client, C1)
    row.cell("tools", a["items"] == b2["items"], f"C1's items host/client {b2['items']} -> {a['items']} (want unchanged)")
    nb, rb = names(host, client, C1), counters(host, client)
    ev["rename"] = rename(host)
    settle(host, client)
    cleanup(host, clean)
    na, ra = names(host, client, C1), counters(host, client)
    ev["names"], ev["renames"] = [nb, na], [rb.get("renames"), ra.get("renames")]
    row.cell("rename", na == nb and ra.get("renames") == rb.get("renames"),
             f"C1's names host/client {nb} -> {na}, host renames.applied {ev['renames']} (want unchanged)")

def pv8(host, client, ctx, row):
    if not reach(host, C1, H_IDS, row):
        return
    ids, ev = ctx["ids"], row.ev
    s0 = counters(host, client).get("skips")
    ev["clientToC1"] = goto_unit(client, C1, C_IDS, [])
    ev["clientMove"] = move(client, ids["smoke"], BELT, (1, 0), {})
    got, dt = wait_until(lambda: in_pack(host, ids["smoke"], C1), LAND_WAIT_S, 0.1)
    hv = inv_view(host)
    ev["hostView"] = {"landedWithin": dt if got else None, "unitId": hv.get("unitId"), "cursor": hv.get("selectedItem")}
    row.cell("host", got and hv.get("unitId") == C1 and hv.get("selectedItem") == -1,
             f"the client's move of C1's smoke grenade {ids['smoke']} to {BACK_PACK} (0,0) on the host: {ev['hostView']} "
             f"(want landed within {LAND_WAIT_S} s, host unitId {C1}, cursor -1; client {ev['clientMove']})")
    ev["hostToH1"] = goto_unit(host, H1, H_IDS, [])
    if not reach(client, H1, C_IDS, row):
        return
    ev["hostMove"] = move(host, ids["grenade"], BELT, (0, 0), {})
    got, dt = wait_until(lambda: in_pack(client, ids["grenade"], H1), LAND_WAIT_S, 0.1)
    cv = inv_view(client)
    ev["clientView"] = {"landedWithin": dt if got else None, "unitId": cv.get("unitId"), "cursor": cv.get("selectedItem")}
    row.cell("client", got and cv.get("unitId") == H1 and cv.get("selectedItem") == -1,
             f"the host's move of H1's grenade {ids['grenade']} to {BACK_PACK} (0,0) on the client: {ev['clientView']} "
             f"(want landed within {LAND_WAIT_S} s, client unitId {H1}, cursor -1; host {ev['hostMove']})")
    wait_until(lambda: drained(host, client), DRAIN_WAIT_S, 0.1)
    ev["skips"] = [s0, counters(host, client).get("skips")]
    row.cell("skips", ev["skips"][0] == ev["skips"][1],
             f"client equip.forceCloseSkips {ev['skips'][0]} -> {ev['skips'][1]} over the row (want unchanged)")
    hash_cell(host, client, row)

def pv9(host, client, ctx, row):
    if not reach(host, C1, H_IDS, row) or not reach(client, H1, C_IDS, row):
        return
    ev = row.ev
    ev["atHostPress"] = inv_view(host).get("unitId")
    ev["hostOk"] = click(host, widget="ok")
    _, ev["hostReadyWithin"] = wait_until(lambda: (equip(host).get("ready") or [None])[0] is True, ANSWER_WAIT_S)
    ev["atClientPress"] = inv_view(client).get("unitId")
    ev["clientOk"] = click(client, widget="ok")
    t1 = time.time()
    row.cell("reach", [ev["atHostPress"], ev["atClientPress"]] == [C1, H1],
             f"partner view not reached at the presses: host {ev['atHostPress']} client {ev['atClientPress']} "
             f"(want {C1} / {H1})")
    got, dt = wait_until(lambda: turn(host) == 1 and turn(client) == 1, TURN_WAIT_S)
    ev["turnWithin"] = dt if got else None
    row.cell("turn", got, f"turn host/client {[turn(host), turn(client)]} {round(time.time() - t1, 2)} s after the "
                          f"client's OK (want 1 on both within {TURN_WAIT_S} s)")
    for gc in (client, host):   # each Turn-1 screen: PEQ EQ8's one real key
        wait_until(lambda: top(gc) == "NextTurnState", 3.0)
        if top(gc) == "NextTurnState":
            ev[f"{gc.name}Key"] = gc.cmd({"cmd": "inject_input", "kind": "key", "key": SDLK_RETURN}).get("ok")
            wait_until(lambda: top(gc) == "BattlescapeState", 3.0)

    sel = lambda: [battle_state(host).get("selectedId"), battle_state(client).get("selectedId")]  # noqa: E731
    got, dt = wait_until(lambda: sel()[0] in H_IDS and sel()[1] in C_IDS, TURN_WAIT_S)
    ev["selected"] = {"ids": sel(), "within": dt if got else None, "stacks": [stack(host), stack(client)]}
    row.cell("select", got, f"selectedId host/client {sel()} (want one of H {H_IDS} / one of C {C_IDS})")
    hash_cell(host, client, row)

FNS = {"PV1": lambda h, c, ctx, row: cycle_row(c, C1, CYCLE_C, row),
       "PV2": lambda h, c, ctx, row: cycle_row(h, H1, CYCLE_H, row),
       "PV3": lambda h, c, ctx, row: look_row(c, H1, C_IDS, OWNER_TEXT.format(HOST_NAME), row),
       "PV6": lambda h, c, ctx, row: look_row(h, C1, H_IDS, OWNER_TEXT.format(CLIENT_NAME), row),
       "PV4": pv4, "PV5": pv5, "PV7": pv7, "PV8": pv8, "PV9": pv9}

def capture(host, client):
    out = {}
    for gc in (host, client):
        try:
            b, e = battle_state(gc), es(gc)
            out[gc.name] = {"stack": stack(gc), "inBattle": b.get("inBattle"), "turn": b.get("turn"),
                            "mapFingerprint": b.get("mapFingerprint"), "phase": e.get("phase"), "equip": e.get("equip"),
                            "view": inv_view(gc)}
        except Exception as ex:
            out[gc.name] = {"error": short(ex, 200)}
    return out

def run(host, client, log=print):
    """Boot V, the spine and every row. Returns {cells: {cell: [ok, msg]}, ev: {row: evidence}, spine: [...], t: {...}}."""
    out = {"cells": {}, "ev": {}, "spine": [], "t": {"start": time.time()}}
    ctx = {}
    try:
        boot(host, client)
    except Exception as e:
        out["boot"] = f"{type(e).__name__}: {short(e, 400)}"
        log(f"CAPTURE boot: {json.dumps({'error': out['boot'], 'machines': capture(host, client)}, default=str)}")
        for name, cells in ROWS:
            for c in cells:
                out["cells"][f"{name}-{c}"] = [False, "boot"]
                log(f"FAIL {name}-{c}: boot")
            log(f"FAIL {name}: boot")
        return out
    out["t"]["boot"] = time.time()
    for fn in (s1_stage, s2_screens):
        try:
            fn(host, client, ctx)
        except Exception as e:
            out["spine"].append(f"{fn.__name__}: {type(e).__name__}: {short(e, 600)}")
            log(f"SPINE FAIL {fn.__name__}: {type(e).__name__}: {short(e, 600)}")
    out["ctx"] = {k: ctx.get(k) for k in ("s1", "s2", "ids")}
    log(f"SPINE {json.dumps(out['ctx'], sort_keys=True, default=str)}")
    out["t"]["spine"] = time.time()
    for name, cells in ROWS:
        row = Row(name, cells)
        c0, t0 = counters(host, client), time.time()
        try:
            FNS[name](host, client, ctx, row)
        except Exception as e:
            row.ev["exception"] = f"{type(e).__name__}: {short(e, 400)}"
            row.unreached(f"not reached ({row.ev['exception']})")
        row.unreached("not reached")
        row.ev["counters"], row.ev["wall"] = [c0, counters(host, client)], round(time.time() - t0, 2)
        evidence(name, row.ev)
        out["ev"][name] = row.ev
        for c in row.cells:
            ok, msg = row.res[c]
            out["cells"][c] = [ok, msg]
            log(f"PASS {c}" if ok else f"FAIL {c}: {msg}")
        bad = [c for c in row.cells if not row.res[c][0]]
        log(f"FAIL {name}: {bad}" if bad else f"PASS {name}")
    out["t"]["end"] = time.time()
    return out

def main():
    t0 = time.time()
    host = GameClient("host", 49928, make_user_dir(DIRS[0]))
    client = GameClient("client", 49929, make_user_dir(DIRS[1]))
    try:
        out = run(host, client, log=lambda s: print(s, flush=True))
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[eq1] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [c for c, (ok, _) in out["cells"].items() if ok]
    failed = [c for c, (ok, _) in out["cells"].items() if not ok]
    print(f"\ntest_equip_partner_view: {len(passed)}/{len(out['cells'])} cells passed (rows failing "
          f"{sorted({c.split('-')[0] for c in failed})}{'; SPINE FAILED' if out['spine'] else ''}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if (len(passed) == 36 and not out["spine"]) else 2

if __name__ == "__main__":
    sys.exit(main())
