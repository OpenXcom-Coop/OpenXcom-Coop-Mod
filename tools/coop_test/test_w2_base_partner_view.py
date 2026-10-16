"""EQ-3 stage S-A (owner D294 b, D289 a, aud-E1-11; QEQ3-1 .. QEQ3-4 (a, QEQ3-3 b), R-EQ3-1; spec rewrite/prompts/eq3_base_screens.md +
rewrite/prompts/eq3a_readonly.md (f); TASK 0 rewrite/eq3-task0/sa/CONSTANTS.md): in a SHARED campaign the base inventory screen (Bases >
Soldiers > Inventory, a craft's Equipment > Inventory) shows the partner's soldiers READ-ONLY with EQ-1's look ("Owner: <partner>", no
UNLOAD / copy / paste); every click, key tool, rename, armor and avatar entry on them does nothing, so W2-H20's OK puts back no partner
record; a Ctrl+Alt open clears only this seat's soldiers' layouts. Every read-only proof is a REAL click or key on the base screen.
Boot S (SHARED, ports 49299 / 49300 / 49301, dirs eq3a_s_host / _client, oxceLinks on both, 4 STR_GRENADE given on both). H / C / C2 =
W2-H20's setup rule (S25: ids and names read at run time); HC = H when H is in SKY's crew, else the first host-owned SKY crew soldier.
Spine: S0 bring_up + h20.setup; S1 the host stages H (pistol in the left hand; personal = pistol + grenade); S2 the client stages C the
same way; S3 global slot 0 of both machines. A spine miss fails every row "spine" with ONE CAPTURE line.
  BV1 client soldier screen: NEXT until H. Cells reach, owner ("Owner: " + HOST_NAME at OWNER_RECT), buttons (unload / copy / paste hidden).
  BV2 client, on H: left click H's left hand, the first ground item, paperdoll left / right, key keyInventoryArmor: pick, ground, armor,
      avatar, armorkey (no item on the cursor, no SoldierArmorState / SoldierAvatarState).
  BV3 client, on H (R-EQ3-2 order): key load personal, the links menu's AUTO-EQUIP, key load again (staging), key auto-equip, key save
      personal, Ctrl+1, rename: load, links, auto, save, global, rename (nothing changes on either machine).
  BV8 client, own C: look and pick (own soldiers stay editable; guard).
  BV4 client OK: host, client (H's record == S1's on both), putback (the client's "partner record(s) put back" M of this OK equals a
      no-action baseline OK of the same screen right before it; R-EQ3-2, F21256: the screen's own re-save puts records back too).
  BV5 host soldier screen, on C: reach, owner ("Owner: " + CLIENT_NAME), buttons, pick, armor, load, putback.
  BV6 client SKY craft screen, on HC: reach, owner, pick.
  BV7 host SKY craft screen opened with Ctrl+Alt (set_touch_modifiers after the push, R-EQ3-2, F21255; last: it empties HC's layout):
      own (non-vacuity), partner (C's layout kept), putback (vs a no-action baseline OK), client.
RED (before EQ-3 S-A): 24 of 33 cells (spec (f) RED list). EVIDENCE line per row, one PASS / FAIL line per cell, the row verdict; every row
runs after a failure; a row stopped early reports its later cells "not reached". ONE foreground run (WV-D95, WV-D99, WV-D100); exit 0
iff every cell passes, else 2. TASK 0: boots a = b red (these 24), p (no A7-A9 / A11) red per gate, c green 33 / 33.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture  # noqa: E402
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded: setup, screens, q / stack / wait_until)
import test_w2_shared_base_writes as sbw  # noqa: E402  (main-guarded: keys, key, ctrl1, bso, personal, names)
from test_w2_shared_base_equip import q, stack, wait_until, open_soldier_screen, close_soldier_screen  # noqa: E402
from test_w2_shared_base_equip import open_craft_screen, close_craft_screen  # noqa: E402
from test_w2_shared_base_writes import keys, ctrl1, bso, personal, names  # noqa: E402

TAG, PORTS = "eq3a_s", (49299, 49300, 49301)  # BPV_PORTS (F20776; TASK 0 used 49302 as its lobby key)
HB, GEO, INV = "HostBase", "GeoscapeState", "InventoryState"
PISTOL, GREN, LEFT, GROUND = "STR_PISTOL", "STR_GRENADE", "STR_LEFT_HAND", "STR_GROUND"
LINKS_OPT = {"oxceLinks": "true"}
OWNER_RECT = (28, 18, 210, 17)  # EQ-1 E10's _txtCoopOwner
BUTTON_RECTS = {"unload": (288, 32, 32, 25), "create": (288, 90, 32, 22), "apply": (288, 113, 32, 22)}
LINKS_RECTS = ((213, 0, 23, 22), (213, 1, 23, 22))  # InventoryState's _btnLinks (two layouts)
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"  # TASK 0 boot c (the owner line's seat names)
OWNER_TEXT = "Owner: {}"  # STR_COOP_EQUIP_OWNER (en-US)
CYCLE_CAP, CLICK_W, NOCHANGE_W, W = 16, 2.0, 2.0, 10.0
NAME_CLICK, UNFOCUS_CLICK = (266, 29), (520, 150)  # PEQ's rename recipe (P8-4c T0-R2)
RENAME_KEYS = (120,)  # PEQ's RENAME_LETTER "x" (TASK 0 boot p: "zed" hits the screen's auto-equip / diary keys while the field
#                       takes no focus, and the diary stayed over the screen)
SDLK_ESCAPE = 27
MENU_SETTLE = 1.0  # TASK 0: the links menu takes its AUTO-EQUIP click only after its popup
PUTBACK = re.compile(r"\[SHARED\] base equip OK: (\d+) own record\(s\) sent, (\d+) partner record\(s\) put back")
CELLS = {
    "BV1": ["BV1-reach", "BV1-owner", "BV1-buttons"],
    "BV2": ["BV2-pick", "BV2-ground", "BV2-armor", "BV2-avatar", "BV2-armorkey"],
    "BV3": ["BV3-load", "BV3-save", "BV3-global", "BV3-auto", "BV3-links", "BV3-rename"],
    "BV8": ["BV8-look", "BV8-pick"],
    "BV4": ["BV4-host", "BV4-client", "BV4-putback"],
    "BV5": ["BV5-reach", "BV5-owner", "BV5-buttons", "BV5-pick", "BV5-armor", "BV5-load", "BV5-putback"],
    "BV6": ["BV6-reach", "BV6-owner", "BV6-pick"],
    "BV7": ["BV7-own", "BV7-partner", "BV7-putback", "BV7-client"],
}
ORDER = ["BV1", "BV2", "BV3", "BV8", "BV4", "BV5", "BV6", "BV7"]
EV = {}  # every row's EVIDENCE (TASK 0 dumps it as JSON)


class Row:
    def __init__(self, rid):
        self.rid, self.ev, self.got, self.why = rid, {}, {}, "row stopped"

    def cell(self, c, ok, detail=""):
        self.got[c] = (bool(ok), detail)
        return bool(ok)

    def report(self, results):
        EV[self.rid] = self.ev
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        fails = []
        for c in CELLS[self.rid]:
            ok, d = self.got.get(c, (False, f"not reached ({self.why})"))
            results[c] = ok
            print(f"PASS {c}" if ok else f"FAIL {c}: {json.dumps(d, default=str)[:900]}", flush=True)
            fails += [] if ok else [c]
        print(f"ROW {self.rid}: " + ("PASS" if not fails else "FAIL " + ",".join(fails)), flush=True)


def key(gc, sym):
    """SBW's key(); a missing sym is refused here (inject_input would press keyOk)."""
    return sbw.key(gc, sym) if sym else {"error": f"no key sym {sym!r}"}


def top(gc):
    return (stack(gc) or [""])[-1]


def view(gc):
    return q(gc, {"cmd": "inventory_view"})


def carried(gc, uid):
    """The unit's carried items on gc's open screen: sorted [slot, item, x, y] (inventory_ground)."""
    u = next((u for u in q(gc, {"cmd": "inventory_ground"}).get("soldiers") or [] if u.get("id") == uid), {})
    return sorted([s, e.get("item"), e.get("x"), e.get("y")] for s, v in (u.get("slots") or {}).items() for e in v)


def record(gc, sid):
    """gc's soldier_layouts record of soldier `sid` (layout, personal, armor; compact)."""
    L = q(gc, {"cmd": "soldier_layouts", "base": HB}).get("soldiers") or []
    return h20.compact(next((s for s in L if s.get("id") == sid), None))


def opt(gc, name):
    return (q(gc, {"cmd": "option_values", "ids": [name]}).get("values") or {}).get(name)


def cfg_key(gc, name):
    """A key option's sym from gc's own options.cfg (option_values reads bool / int options only)."""
    m = re.search(r"^\s*%s:\s*(\d+)\s*$" % name, open(os.path.join(gc.user_dir, "options.cfg"), encoding="utf-8").read(), re.M)
    return int(m.group(1)) if m else None


def look(gc):
    ws = q(gc, {"cmd": "list_widgets"}).get("widgets") or []
    rect = lambda w: (w.get("x"), w.get("y"), w.get("w"), w.get("h"))  # noqa: E731
    owner = [[w.get("visible"), w.get("text")] for w in ws if rect(w) == OWNER_RECT and str(w.get("type")).endswith("Text")]
    buttons = {n: [w.get("visible") for w in ws if rect(w) == r and w.get("interactive")] for n, r in BUTTON_RECTS.items()}
    return {"owner": owner, "buttons": buttons, "unitId": view(gc).get("unitId")}


def owner_ok(lk, name):
    return [True, OWNER_TEXT.format(name)] in lk["owner"]


def click(gc, **kw):
    r = q(gc, dict({"cmd": "inventory_click"}, **kw))
    return r.get("error") or r.get("ok")


def goto(gc, uid, rec):
    """NEXT (a real click) until the screen shows `uid`, at most CYCLE_CAP presses."""
    for _ in range(CYCLE_CAP):
        now = view(gc).get("unitId")
        rec.append(now)
        if now == uid:
            return True
        click(gc, widget="next")
        wait_until(lambda: view(gc).get("unitId") != now, CLICK_W)
    return view(gc).get("unitId") == uid


def cursor(gc):
    """The item on the cursor within CLICK_W (-1 = none came)."""
    wait_until(lambda: view(gc).get("selectedItem") not in (None, -1), CLICK_W)
    return view(gc).get("selectedItem")


def pushed(gc):
    """The top state within CLICK_W of a click that may push a screen."""
    wait_until(lambda: top(gc) != INV, CLICK_W)
    return top(gc)


def cleanup(gc, rec):
    """A screen over the inventory -> ESC; an item on the cursor -> inventory_cursor_clear. Each recorded (red only)."""
    for _ in range(3):
        t = top(gc)
        if t == INV:
            break
        rec.append({"esc": t, "ok": q(gc, {"cmd": "inject_input", "kind": "key", "key": SDLK_ESCAPE}).get("ok")})
        wait_until(lambda: top(gc) == INV, CLICK_W)
    if view(gc).get("selectedItem") not in (None, -1):
        rec.append({"cursorCleared": q(gc, {"cmd": "inventory_cursor_clear"}).get("cleared")})


def unchanged(read, a, window=NOCHANGE_W):
    """(`a` = the read BEFORE the action, the read after the window, changed?) - the first change ends the watch."""
    t0 = time.time()
    while time.time() - t0 < window:
        b = read()
        if b != a:
            return a, b, True
        time.sleep(0.25)
    return a, read(), False


def first_ground(gc):
    g = sorted(((e.get("x"), e.get("y")) for e in view(gc).get("ground") or [] if e.get("x") is not None))
    return g[0] if g else None


def log_path(gc):
    return os.path.join(gc.user_dir, "openxcom.log")


def putbacks(gc):
    try:
        with open(log_path(gc), encoding="utf-8", errors="replace") as fh:
            return [int(m.group(2)) for m in PUTBACK.finditer(fh.read())]
    except OSError as e:
        return [f"<log: {e}>"]


def ok_close(r, gc, n0, craft=False):
    """The screen's OK (a real click), then its parent's OK; the new put-back line's M (None when no line came)."""
    r.ev["ok click"] = click(gc, widget="ok")
    wait_until(lambda: INV not in stack(gc), 30)
    r.ev["parent ok"] = q(gc, {"cmd": "craft_equipment_ok" if craft else "soldiers_ok"}).get("ok")
    wait_until(lambda: top(gc) == GEO, 30)
    got = wait_until(lambda: len(putbacks(gc)) > n0, W)
    L = putbacks(gc)
    r.ev["putback lines"] = L[n0:]
    return L[-1] if got and L else None


def baseline(gc, x, craft=False):
    """R-EQ3-2 (3): a no-action open + OK of the same screen right before the row's own; its put-back M (F21256: the screen's re-save)."""
    n0, sh, r = len(putbacks(gc)), Shim(), Row("BV4")
    if not (open_craft_screen(sh, x, gc) if craft else open_soldier_screen(sh, gc)):
        return None, sh.fails
    return ok_close(r, gc, n0, craft), r.ev


def links_auto(gc, rec):
    """The links button (click_widget by index), then the menu's AUTO-EQUIP (click_widget by text)."""
    ws = [w for w in q(gc, {"cmd": "list_widgets"}).get("widgets") or [] if w.get("visible") and w.get("interactive")]
    nth = next((i for i, w in enumerate(ws) if (w.get("x"), w.get("y"), w.get("w"), w.get("h")) in LINKS_RECTS), None)
    rec["links nth"] = nth
    if nth is None:
        return False
    rec["links click"] = q(gc, {"cmd": "click_widget", "nth": nth})
    rec["menu"] = pushed(gc)
    if "LinksState" not in str(rec["menu"]):
        return False
    time.sleep(MENU_SETTLE)  # the menu's window pops up first and takes no click meanwhile (boots a / b: the click never landed)
    rec["auto click"] = q(gc, {"cmd": "click_widget", "match": "Auto-equip"})
    wait_until(lambda: top(gc) == INV, CLICK_W)
    rec["top after click"] = top(gc)
    return rec["top after click"] == INV


def rename(gc, rec):
    """PEQ's recipe: click the name field, type RENAME_KEYS, click off it."""
    out = [q(gc, {"cmd": "inject_input", "kind": "click", "x": NAME_CLICK[0], "y": NAME_CLICK[1]}).get("ok")]
    for k in RENAME_KEYS:
        time.sleep(0.3)
        out.append(q(gc, {"cmd": "inject_input", "kind": "key", "key": k}).get("ok"))
    time.sleep(0.3)
    out.append(q(gc, {"cmd": "inject_input", "kind": "click", "x": UNFOCUS_CLICK[0], "y": UNFOCUS_CLICK[1]}).get("ok"))
    rec["rename"] = out


def stage(r, gc, x, who, sid):
    """Spine S1 / S2: gc stages its own soldier on its own screen (levers: own soldiers only). The record of `sid`."""
    if not open_soldier_screen(r, gc):
        raise RuntimeError(f"{gc.name} screen did not open: {r.fails}")
    kk = keys(gc)
    st = {"start": carried(gc, sid), "strip": []}  # S54 / S25: the start loadout goes to the ground first (CONSTANTS.md)
    for _ in range(16):
        items = carried(gc, sid)
        if not items:
            break
        st["strip"].append(q(gc, {"cmd": "inventory_move", "name": who, "item": items[0][1], "slot": "ground", "from": "unit"}).get("moved"))
    st.update({"select": bso(gc, op="select", name=who).get("ok"),
          "pistol": q(gc, {"cmd": "inventory_move", "name": who, "item": PISTOL, "slot": "left"}).get("moved"),
          "belt": q(gc, {"cmd": "inventory_move", "name": who, "item": GREN, "slot": "belt"}).get("moved")})
    st["save key"] = key(gc, kk.get("keyInvSavePersonalEquipment")).get("ok")
    st["saved"] = sbw.converge(lambda: GREN in personal(gc, sid)[0] and PISTOL in personal(gc, sid)[0], 5.0)
    st["drop"] = q(gc, {"cmd": "inventory_move", "name": who, "item": GREN, "slot": "ground", "from": "unit"}).get("moved")
    st["carried"] = carried(gc, sid)
    st["slot0"] = sbw.slot0(gc)
    st["keys"] = kk
    close_soldier_screen(r, gc)
    st["record"] = record(gc, sid)
    other = x.client if gc is x.host else x.host
    st["peer equal"] = sbw.converge(lambda: record(other, sid) == record(gc, sid))
    if not (all(st[k] for k in ("select", "pistol", "belt", "drop")) and st["saved"][0] and st["peer equal"][0]
            and [c[1] for c in st["carried"]] == [PISTOL]):
        raise RuntimeError(f"stage {who}: {st}")
    return st


class Fx(h20.X):
    pass


class Shim:
    """h20's open / close helpers record G cells on a row; the spine keeps them."""
    def __init__(self):
        self.fails = []

    def cell(self, name, ok, detail=""):
        if not ok:
            self.fails.append(f"{name}: {detail}")
        return bool(ok)


def spine(x):
    h, c = x.host, x.client
    h20.setup(x)
    x.first = {k: getattr(x, k) for k in ("H", "C", "C2")}
    sol = q(h, {"cmd": "base_report", "base": HB}).get("soldiers") or []
    x.crew = {s.get("id"): s.get("craft") for s in sol}
    hs = [s.get("id") for s in sol if s.get("owner") == x.seats["host"] and x.crew.get(s.get("id")) == x.sky]
    x.HC = x.ids["H"] if x.ids["H"] in hs else (hs[0] if hs else None)
    x.host_ids = {s.get("id") for s in sol if s.get("owner") == x.seats["host"]}
    given = {gc.name: q(gc, {"cmd": "give_items", "item": GREN, "count": 4, "base": HB}).get("stored") for gc in (h, c)}
    x.links = {gc.name: opt(gc, "oxceLinks") for gc in (h, c)}
    x.armorkey = {gc.name: cfg_key(gc, "keyInventoryArmor") for gc in (h, c)}
    x.coop = {gc.name: q(gc, {"cmd": "get_coop"}) for gc in (h, c)}
    x.spine = {"given": given, "links": x.links, "armorkey": x.armorkey, "HC": x.HC, "crew": x.crew, "ids": x.ids,
               "names": x.first, "seats": x.seats, "coop": x.coop}
    if given["host"] != given["client"] or None in given.values() or x.HC is None:
        raise RuntimeError(f"fixture: {x.spine}")
    sh = Shim()
    x.S1 = stage(sh, h, x, x.H, x.ids["H"])
    x.S2 = stage(sh, c, x, x.C, x.ids["C"])
    x.spine.update(S1=x.S1, S2=x.S2, putbacks={gc.name: putbacks(gc) for gc in (h, c)})


def client_screen(x, results):
    """BV1, BV2, BV3, BV8, BV4 on ONE client soldier screen."""
    c, h, hid, cid = x.client, x.host, x.ids["H"], x.ids["C"]
    rows = {k: Row(k) for k in ("BV1", "BV2", "BV3", "BV8", "BV4")}
    r1, r2, r3, r8, r4 = (rows[k] for k in ("BV1", "BV2", "BV3", "BV8", "BV4"))
    r4.ev["baseline M"], r4.ev["baseline"] = baseline(c, x)
    n0 = len(putbacks(c))
    sh = Shim()
    opened = open_soldier_screen(sh, c)
    try:
        if not opened:
            for r in rows.values():
                r.why, r.ev["open"] = "the client's soldier screen did not open", sh.fails
            return
        kk = keys(c)
        r1.ev.update(keys=kk, nav=[])
        reached = r1.cell("BV1-reach", goto(c, hid, r1.ev["nav"]), r1.ev["nav"])
        lk = r1.ev["look"] = look(c)
        if reached:
            r1.cell("BV1-owner", owner_ok(lk, HOST_NAME), lk["owner"])
            r1.cell("BV1-buttons", not any(v for vs in lk["buttons"].values() for v in vs), lk["buttons"])
        else:
            r1.why = r2.why = r3.why = "H not reached"
        if reached:
            h_items = carried(c, hid)
            r2.ev["carried"] = h_items
            for cname, act in (("BV2-pick", lambda: click(c, slot=LEFT, x=0, y=0)),
                               ("BV2-ground", lambda: click(c, slot=GROUND, x=first_ground(c)[0], y=first_ground(c)[1]))):
                rec = {"click": act()}
                rec["cursor"] = cursor(c)
                rec["cleanup"] = []
                cleanup(c, rec["cleanup"])
                r2.ev[cname] = rec
                r2.cell(cname, rec["cursor"] == -1, rec)
            ak = x.armorkey.get("client")
            for cname, act, bad in (("BV2-armor", lambda: click(c, widget="paperdoll", button="left"), "SoldierArmorState"),
                                    ("BV2-avatar", lambda: click(c, widget="paperdoll", button="right"), "SoldierAvatarState"),
                                    ("BV2-armorkey", lambda: key(c, ak).get("ok"), "SoldierArmorState")):
                rec = {"click": act()}
                rec["top"] = pushed(c)
                rec["cleanup"] = []
                cleanup(c, rec["cleanup"])
                r2.ev[cname] = rec
                r2.cell(cname, rec["top"] == INV and bad not in str(stack(c)), rec)
            # BV3 (R-EQ3-2 (1)): load -> links AUTO-EQUIP -> load again (staging) -> key auto-equip -> save -> Ctrl+1 -> rename
            b0 = carried(c, hid)
            rec = {"key": key(c, kk.get("keyInvLoadPersonalEquipment")).get("ok")}
            rec["before/after/changed"] = unchanged(lambda: carried(c, hid), b0)
            r3.ev["load"] = rec
            r3.cell("BV3-load", not rec["before/after/changed"][2], rec)
            rec = {"links option": x.links.get("client"), "before": carried(c, hid)}
            if links_auto(c, rec):
                rec["after/changed"] = unchanged(lambda: carried(c, hid), rec["before"])[1:]
                r3.cell("BV3-links", rec["before"] == rec["after/changed"][0] and not rec["after/changed"][1], rec)
            else:
                r3.cell("BV3-links", False, ["FIXTURE: the links menu's AUTO-EQUIP was not reached", rec])
            rec["cleanup"] = []
            cleanup(c, rec["cleanup"])
            r3.ev["links"] = rec
            rec = {"key": key(c, kk.get("keyInvLoadPersonalEquipment")).get("ok")}  # staging: H back to its personal on red
            time.sleep(1.0)
            rec["carried"] = carried(c, hid)
            r3.ev["load again"] = rec
            a = carried(c, hid)
            rec = {"key": key(c, kk.get("keyInvAutoEquip")).get("ok")}
            rec["before/after/changed"] = unchanged(lambda: carried(c, hid), a)
            r3.ev["auto"] = rec
            r3.cell("BV3-auto", not rec["before/after/changed"][2], rec)
            p0 = personal(c, hid)
            rec = {"carried": carried(c, hid), "key": key(c, kk.get("keyInvSavePersonalEquipment")).get("ok")}
            rec["before/after/changed"] = unchanged(lambda: personal(c, hid), p0)
            r3.ev["save"] = rec
            r3.cell("BV3-save", not rec["before/after/changed"][2], rec)
            rec = ctrl1(c)
            rec["S3 client slot0"] = x.S2["slot0"]
            r3.ev["global"] = rec
            r3.cell("BV3-global", rec["slot0"] == x.S2["slot0"], rec)
            rec = {"before": [names(c).get(hid), names(h).get(hid)]}
            rename(c, rec)
            time.sleep(1.0)
            rec["client at once"] = names(c).get(hid)
            rec["host within W"] = sbw.converge(lambda: names(h).get(hid) != x.first["H"])
            r3.ev["rename"] = rec
            r3.cell("BV3-rename", rec["client at once"] == x.first["H"] and not rec["host within W"][0], rec)
        # BV8: own C stays editable
        r8.ev["nav"] = []
        if goto(c, cid, r8.ev["nav"]):
            lk = r8.ev["look"] = look(c)
            r8.cell("BV8-look", not any(v for v, _t in lk["owner"]) and all(v and all(v) for v in lk["buttons"].values()), lk)
            rec = {"click": click(c, slot=LEFT, x=0, y=0), "carried": carried(c, cid)}
            rec["picked"] = cursor(c)
            rec["right"] = click(c, slot=LEFT, x=0, y=0, button="right")
            wait_until(lambda: view(c).get("selectedItem") == -1, CLICK_W)
            rec["after"] = view(c).get("selectedItem")
            rec["cleanup"] = []
            cleanup(c, rec["cleanup"])
            r8.ev["pick"] = rec
            r8.cell("BV8-pick", rec["picked"] not in (None, -1) and rec["after"] == -1, rec)
        else:
            r8.why = "C not reached"
        # BV4: the client's OK
        m = ok_close(r4, c, n0)
        r4.cell("BV4-host", record(h, hid) == x.S1["record"], [record(h, hid), x.S1["record"]])
        got = sbw.converge(lambda: record(c, hid) == x.S1["record"])
        r4.cell("BV4-client", got[0], [record(c, hid), x.S1["record"], got[1]])
        mb = r4.ev["baseline M"]
        r4.cell("BV4-putback", None not in (m, mb) and m - mb == 0, {"M": m, "baseline M": mb, "lines": r4.ev.get("putback lines")})
        r4.ev.update(M=m, names=[names(c).get(hid), names(h).get(hid)], end={"host": record(h, hid), "client": record(c, hid)})
    finally:
        for r in rows.values():
            r.report(results)


def bv5(x, r):
    h, cid = x.host, x.ids["C"]
    r.ev["baseline M"], r.ev["baseline"] = baseline(h, x)
    n0 = len(putbacks(h))
    sh = Shim()
    if not open_soldier_screen(sh, h):
        r.why, r.ev["open"] = "the host's soldier screen did not open", sh.fails
        return
    kk, r.ev["nav"] = keys(h), []
    if not r.cell("BV5-reach", goto(h, cid, r.ev["nav"]), r.ev["nav"]):
        r.why = "C not reached"
        return
    lk = r.ev["look"] = look(h)
    r.cell("BV5-owner", owner_ok(lk, CLIENT_NAME), lk["owner"])
    r.cell("BV5-buttons", not any(v for vs in lk["buttons"].values() for v in vs), lk["buttons"])
    rec = {"click": click(h, slot=LEFT, x=0, y=0), "carried": carried(h, cid)}
    rec["cursor"], rec["cleanup"] = cursor(h), []
    cleanup(h, rec["cleanup"])
    r.ev["pick"] = rec
    r.cell("BV5-pick", rec["cursor"] == -1, rec)
    rec = {"click": click(h, widget="paperdoll", button="left")}
    rec["top"], rec["cleanup"] = pushed(h), []
    cleanup(h, rec["cleanup"])
    r.ev["armor"] = rec
    r.cell("BV5-armor", rec["top"] == INV, rec)
    b0 = carried(h, cid)
    rec = {"key": key(h, kk.get("keyInvLoadPersonalEquipment")).get("ok")}
    rec["before/after/changed"] = unchanged(lambda: carried(h, cid), b0)
    r.ev["load"] = rec
    r.cell("BV5-load", not rec["before/after/changed"][2], rec)
    m = ok_close(r, h, n0)
    r.ev["M"], mb = m, r.ev["baseline M"]
    r.cell("BV5-putback", None not in (m, mb) and m - mb == 0, {"M": m, "baseline M": mb, "lines": r.ev.get("putback lines")})


def bv6(x, r):
    c, hc = x.client, x.HC
    n0 = len(putbacks(c))
    sh = Shim()
    if not open_craft_screen(sh, x, c):
        r.why, r.ev["open"] = "the client's SKY craft screen did not open", sh.fails
        return
    r.ev["nav"] = []
    try:
        if not r.cell("BV6-reach", goto(c, hc, r.ev["nav"]), r.ev["nav"]):
            r.why = "HC not reached"
            return
        lk = r.ev["look"] = look(c)
        r.cell("BV6-owner", owner_ok(lk, HOST_NAME), lk["owner"])
        items = carried(c, hc)
        at = (items[0][0], items[0][2], items[0][3]) if items else (GROUND,) + tuple(first_ground(c) or (0, 0))
        rec = {"carried": items, "at": at, "click": click(c, slot=at[0], x=at[1], y=at[2])}
        rec["cursor"], rec["cleanup"] = cursor(c), []
        cleanup(c, rec["cleanup"])
        r.ev["pick"] = rec
        r.cell("BV6-pick", rec["cursor"] == -1, rec)
    finally:
        r.ev["M"] = ok_close(r, c, n0, craft=True)


def bv7(x, r):
    """R-EQ3-2 (2): the host's SKY craft screen, Ctrl+Alt by set_touch_modifiers AFTER the push (CraftEquipmentState reads the touch flags;
    a pushed state resets them, F21255). Own = HC; partner = C when in SKY's crew, else the first client-owned SKY crew soldier."""
    h, c, own_id = x.host, x.client, x.HC
    part = x.ids["C"] if x.crew.get(x.ids["C"]) == x.sky else next(
        (i for i, k in sorted(x.crew.items()) if k == x.sky and i not in x.host_ids), None)
    r.ev["own / partner"] = [own_id, part]
    if part is None:
        r.why = "FIXTURE: no client-owned SKY crew soldier"
        return
    r.ev["baseline M"], r.ev["baseline"] = baseline(h, x, craft=True)
    pre = record(h, part)
    n0 = len(putbacks(h))
    r.ev["open"] = q(h, {"cmd": "open_craft_equipment", "base": HB, "craft_id": x.sky})
    wait_until(lambda: "CraftEquipmentState" in stack(h), 30)
    r.ev["latch"] = q(h, {"cmd": "set_touch_modifiers", "ctrl": True, "alt": True})
    r.ev["inventory"] = q(h, {"cmd": "craft_inventory"})
    r.ev["clear"] = q(h, {"cmd": "set_touch_modifiers", "ctrl": False, "alt": False})
    if not wait_until(lambda: INV in stack(h), 30):
        r.why = "the host's Ctrl+Alt craft screen did not open"
        return
    own, partner = record(h, own_id), record(h, part)
    r.ev.update(own=own, partner=partner, pre=pre)
    if not r.cell("BV7-own", own is not None and not own["layout"], ["FIXTURE: Ctrl+Alt did not take (HC's layout kept)", own]):
        r.why = "Ctrl+Alt did not take"
    r.cell("BV7-partner", partner == pre and pre is not None, [partner, pre])
    m, mb = ok_close(r, h, n0, craft=True), r.ev["baseline M"]
    r.ev["M"] = m
    r.cell("BV7-putback", None not in (m, mb) and m - mb == 0, {"M": m, "baseline M": mb, "lines": r.ev.get("putback lines")})
    got = sbw.converge(lambda: record(c, part) == pre)
    r.cell("BV7-client", got[0], [record(c, part), pre, got[1]])


def to_geo(gc, rec):
    if top(gc) != GEO:
        rec.append({"close_screens": q(gc, {"cmd": "close_screens"}), "before": stack(gc)})
        wait_until(lambda: top(gc) == GEO, 5.0)


def run(x, results, walls, extra=None):
    t1 = time.time()
    client_screen(x, results)
    walls["client screen"] = round(time.time() - t1, 1)
    for rid, fn in (("BV5", bv5), ("BV6", bv6), ("BV7", bv7)):
        r, t1 = Row(rid), time.time()
        for g in (x.host, x.client):
            to_geo(g, r.ev.setdefault("cleanup before", []))
        try:
            fn(x, r)
        except Exception as e:
            r.why = h20.short(e)
            r.ev["exception"] = h20.short(e)
        for g in (x.host, x.client):
            to_geo(g, r.ev.setdefault("cleanup after", []))
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)
    if extra:
        extra(x)


def main(tag=TAG, ports=PORTS, extra=None):
    t0, results, walls, js, x = time.time(), {}, {}, None, None
    try:
        try:
            js = shared_fixture.bring_up(tag, ports, host_options=LINKS_OPT, client_options=LINKS_OPT)
            x = Fx(js.host, js.client, js)
            spine(x)
            walls["spine"] = round(time.time() - t0, 1)
            print(f"EVIDENCE spine: {json.dumps(x.spine, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = x.spine
        except Exception as e:  # a spine miss fails every row "spine" with ONE CAPTURE line
            cap = {"error": h20.short(e, 3000)}
            if x is not None:
                for g in (x.host, x.client):
                    cap[f"{g.name} stack"] = stack(g)
                    cap[f"{g.name} soldier_layouts"] = q(g, {"cmd": "soldier_layouts", "base": HB})
            print(f"CAPTURE spine: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = cap
            for rid in ORDER:
                for cname in CELLS[rid]:
                    results[cname] = False
                    print(f"FAIL {cname}: spine", flush=True)
                print(f"ROW {rid}: FAIL spine", flush=True)
            return results, walls
        run(x, results, walls, extra)
    finally:
        if js is not None:
            js.shutdown()
        walls["total"] = round(time.time() - t0, 1)
    return results, walls


if __name__ == "__main__":
    res, wl = main()
    allc = [cname for rid in ORDER for cname in CELLS[rid]]
    failed = [cname for cname in allc if not res.get(cname)]
    print(f"\ntest_w2_base_partner_view: {len(allc) - len(failed)}/{len(allc)} cells passed (fail={failed}) "
          f"walls {json.dumps(wl)}", flush=True)
    sys.exit(2 if failed else 0)
