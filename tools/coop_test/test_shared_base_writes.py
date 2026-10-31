"""In SHARED, base-screen writes outside the soldier gear record (test_shared_base_equip.py) end equal on both machines
through the host: a rename on the base inventory, a saved layout / craft loadout template, a personal layout's armor
(the client's own soldier synced, the partner's put back at once); the armor screen refuses the partner's soldier "not
your soldier". Without the fix each stays on one machine or applies to the partner.
H / C / C2 as in test_shared_base_equip.setup(): the first HostBase soldier owned by the host's seat / the first /
second owned by the client's. W = 10 s at 0.25 s polls; a key's local effect <= 5 s; "nothing sent" cells after a
1 s settle. Global layout 0 = equip_layouts {index: 0} inside that machine's open soldier screen; loadout 0 and
lastSelectedArmor = the test-only command base_screen_op {op: read}. A row whose main cell (the one that fails without
the fix) fails evaluates no later cell.
SHARED boot (ports 49421 / 49422 / 47924, option OFF, STR_PERSONAL_ARMOR 4 on both):
  base_write_1 client screen: rename C "Ripley B". Without the fix the host's C never shows "Ripley B" in W. Cleanup
        (with or without the fix): rename back, W.
  base_write_2 client screen: rename H "Vasquez B". Refused before any write: the reply keeps H's name and neither
        machine shows "Vasquez B" (host W). Without the read-only partner rule the reply says "Vasquez B".
  base_write_3 (guard) host screen open; client soldier_rename {C2, "Hicks B"} lands; host close: "Hicks B" on both.
  base_write_4 client screen: select C, Ctrl+1, close. Without the fix the host's global 0 is still [] after W (its
        screen open); with it slot 0 is equal.
  base_write_5 client SKY equipment screen: loadout_save {index: 0}, OK. Without the fix the host's loadout 0 is still
        {} after W; with it they are equal.
  base_write_6 client soldier_armor {H, A1}. Without the fix the host's H wears A1 (cleanup: host -> A0); with it the
        request is refused "not your soldier".
  base_write_7 (guard, last in the SHARED boot) js.finish(): world equality (names included) + replica zero-disk.
Armor boot (SHARED, ports 49425 / 49426 / 47926, STR_PERSONAL_ARMOR 4 and STR_POWER_SUIT 4 on both):
  base_write_8 C: A2, personal saved with it, A1; client screen key 108 (client's C A2). Without the fix the host's C
        is still A1 after W.
  base_write_9 H (host staging): A2, personal + one grenade, A1; client screen key 108 on H. Nothing changes on
        either machine within 5 s. Without the read-only partner rule H takes the personal's grenades on the client's
        screen.
EVIDENCE line per row before its verdict; a failed row prints ONE CAPTURE line (soldier_layouts, get_soldiers, geo_state
items, shared_stats, equip_layouts {index: 0}, read {index: 0}, stacks; both machines). A boot miss fails its rows
"boot" with one CAPTURE line. Every row runs after a failure. ONE run; exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_shared_base_equip as sbe  # noqa: E402  (main-guarded: setup, screens, q / stack / wait_until)
from test_shared_base_equip import q, stack, wait_until, open_soldier_screen, close_soldier_screen  # noqa: E402

TAG_SHARED, PORTS_SHARED = "base_writes_shared", (49421, 49422, 47924)
TAG_ARMOR, PORTS_ARMOR = "base_writes_armor", (49425, 49426, 47926)
HB, GEO = "HostBase", "GeoscapeState"
A0, A1, A2 = "STR_NONE_UC", "STR_PERSONAL_ARMOR_UC", "STR_POWER_SUIT_UC"
I1, I2, GREN = "STR_PERSONAL_ARMOR", "STR_POWER_SUIT", "STR_GRENADE"
W, KEY_W, SETTLE, KEY_SETTLE, SDLK_1 = 10.0, 5.0, 1.0, 0.3, 49
NOT_YOURS = "not your soldier"
ROWS_SHARED = ["base_write_%d" % n for n in range(1, 8)]
ROWS_ARMOR = ["base_write_8", "base_write_9"]
ORDER = ROWS_SHARED + ROWS_ARMOR


def converge(pred, timeout=W):
    t0 = time.time()
    return wait_until(pred, timeout), round(time.time() - t0, 2)


def roster(gc, base=HB):
    """get_soldiers {id: soldier} of `base` on gc (name, owner, armor)."""
    b = next((b for b in q(gc, {"cmd": "get_soldiers"}).get("bases") or [] if b.get("name") == base), {})
    return {s.get("id"): s for s in b.get("soldiers") or []}


def names(gc, base=HB):
    return {i: s.get("name") for i, s in roster(gc, base).items()}


def armor(gc, sid):
    return (roster(gc).get(sid) or {}).get("armor")


def items(gc, base=HB):
    return next((b.get("items") or {} for b in q(gc, {"cmd": "geo_state"}).get("bases") or [] if b.get("name") == base), {})


def stocks(gc):
    return [items(gc).get(i, 0) for i in (I1, I2)]


def slot0(gc):
    """(global, globalArmor, globalName) of layout template 0, or None (the probe needs gc's base screen open)."""
    r = q(gc, {"cmd": "equip_layouts", "index": 0})
    return None if r.get("error") else [r.get("global"), r.get("globalArmor"), r.get("globalName")]


def bso(gc, **kw):
    return q(gc, dict({"cmd": "base_screen_op"}, **kw))


def keys(gc):
    return q(gc, {"cmd": "equip_layouts"}).get("keys") or {}


def key(gc, sym):
    time.sleep(KEY_SETTLE)  # a freshly opened / reselected screen takes the key on its next frame
    return q(gc, {"cmd": "inject_input", "kind": "key", "key": sym})


def ctrl1(gc):
    """Ctrl+1 on gc's open screen: the latched Ctrl is cleared only after the local save (or 5 s), ALWAYS."""
    time.sleep(KEY_SETTLE)
    rep = q(gc, {"cmd": "inject_input", "kind": "key", "key": SDLK_1, "mod": "ctrl"})
    try:
        saved, s = converge(lambda: (slot0(gc) or [None])[0], KEY_W)
    finally:
        clr = q(gc, {"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    return {"inject": rep, "clear": clr, "within s": s, "slot0": slot0(gc), "saved": bool(saved)}


def personal(gc, sid, base=HB):
    r = q(gc, {"cmd": "soldier_layouts", "base": base})
    e = next((s for s in r.get("soldiers") or [] if s.get("id") == sid), {})
    return [i.get("type") for i in e.get("personal") or []], e.get("personalArmor")


def grenades(gc, nm):
    g = q(gc, {"cmd": "inventory_ground"})
    u = next((u for u in g.get("soldiers") or [] if u.get("name") == nm), {})
    return sum(1 for v in (u.get("slots") or {}).values() for e in v if e.get("item") == GREN)


class X:
    def __init__(self, host, client, js=None, base=HB):
        self.js, self.host, self.client, self.base = js, host, client, base
        self.H = self.C = self.C2 = self.sky = self.hb_index = None
        self.ids, self.opts, self.seats, self.first = {}, {}, {}, {}

    def three(self):
        """Both machines' (name, armor) of H, C and C2: each row's EVIDENCE start / end."""
        out = {}
        for gc in (self.host, self.client):
            R = roster(gc, self.base)
            out[gc.name] = {k: [(R.get(i) or {}).get("name"), (R.get(i) or {}).get("armor")] for k, i in self.ids.items()}
        return out


class Row:
    def __init__(self, rid, x):
        self.rid, self.x, self.fails, self.cap, self.printed = rid, x, [], {}, False
        self.ev = {"seats": x.seats, "ids": x.ids, "first": x.first}

    def evidence(self):
        if not self.printed:
            self.printed = True
            print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)

    def cell(self, name, ok, detail=""):
        if not ok:
            self.fails.append(f"{name}: {detail}")
        return bool(ok)

    def report(self, results):
        self.evidence()
        if self.fails:
            b = self.x.base
            for gc in (self.x.host, self.x.client):
                self.cap[f"{gc.name} soldier_layouts {b}"] = q(gc, {"cmd": "soldier_layouts", "base": b})
                self.cap[f"{gc.name} get_soldiers"] = [(i, s.get("name"), s.get("owner"), s.get("armor")) for i, s in roster(gc, b).items()]
                self.cap[f"{gc.name} geo_state items {b}"] = items(gc, b)
                self.cap[f"{gc.name} shared_stats"] = q(gc, {"cmd": "shared_stats"})
                self.cap[f"{gc.name} equip_layouts 0"] = q(gc, {"cmd": "equip_layouts", "index": 0})
                self.cap[f"{gc.name} read 0"] = bso(gc, op="read", index=0)
                self.cap[f"{gc.name} stack (after cleanup)"] = stack(gc)
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def screen_rename(r, gc, old, new, tag):
    """gc's soldier screen: base_screen_op rename {old -> new}, close; the reply."""
    if not open_soldier_screen(r, gc):
        return {}
    rep = bso(gc, op="rename", name=old, text=new)
    r.ev[tag] = rep
    close_soldier_screen(r, gc)
    return rep


def set_armor(r, x, sender, sid, arm, tag):
    """setup: soldier_armor from `sender`; both machines wear `arm` within W (guard cell)."""
    rep = q(sender, {"cmd": "soldier_armor", "soldier_id": sid, "armor": arm, "base": HB})
    got, s = converge(lambda: armor(x.host, sid) == arm and armor(x.client, sid) == arm)
    r.ev[tag] = [rep, s]
    return r.cell(f"guard: {tag} on both", rep.get("moved") is True and got, [rep, armor(x.host, sid), armor(x.client, sid)])


def row_client_renames_own(x, r):
    h, c, cid, first = x.host, x.client, x.ids["C"], x.first["C"]
    r.ev["start"] = x.three()
    n0 = {gc.name: names(gc) for gc in (h, c)}
    rep = screen_rename(r, c, first, "Ripley B", "rename")
    cn = names(c).get(cid)
    got, s = converge(lambda: names(h).get(cid) == "Ripley B") if cn == "Ripley B" else (False, 0.0)
    n1 = {gc.name: names(gc) for gc in (h, c)}
    r.ev.update({"wait s": s, "end": x.three()})
    back = screen_rename(r, c, "Ripley B", first, "cleanup rename")  # cleanup, with or without the fix
    r.ev["cleanup"] = [back, converge(lambda: names(h).get(cid) == first)]
    r.evidence()
    nv = r.cell("non-vacuity: reply soldierName 'Ripley B'", rep.get("soldierName") == "Ripley B", rep)
    if not (r.cell("non-vacuity: the client's C 'Ripley B' after the close", cn == "Ripley B", cn) and nv):
        return
    if not r.cell("the client's base-screen rename never reached the host", got, f"host C {n1['host'].get(cid)!r}"):
        return
    other = sorted(i for i in n0["host"] if i != cid and any(n0[m].get(i) != n1[m].get(i) for m in n0))
    r.cell("another soldier's name changed", not other, [(i, n0["host"].get(i), n1["host"].get(i), n1["client"].get(i)) for i in other])


def row_partner_rename_refused(x, r):
    h, c, hid, first = x.host, x.client, x.ids["H"], x.first["H"]
    r.ev["start"] = x.three()
    rep = screen_rename(r, c, first, "Vasquez B", "rename")
    cn, hn = names(c).get(hid), names(h).get(hid)  # at once after the close
    r.ev.update({"at once": {"client": cn, "host": hn}})
    if cn != first:  # cleanup (a build without the read-only partner rule kept the rename): rename H back on the
        # client's screen
        r.ev["cleanup"] = [screen_rename(r, c, "Vasquez B", first, "cleanup rename"), names(c).get(hid)]
    moved, s = converge(lambda: names(h).get(hid) != first)
    r.ev.update({"host watched s": s, "end": x.three()})
    r.evidence()
    # a partner's soldier on a SHARED base screen is read-only - the rename is refused before any write.
    r.cell("the reply soldierName stays H's name (a partner's soldier is not renamed)", rep.get("soldierName") == first,
           rep)
    r.cell("the client's H changed at once", cn == first, f"client H {cn!r}, host H {hn!r}")
    r.cell("the host's H changed within W", not moved, names(h).get(hid))


def row_host_screen_keeps_rename(x, r):
    h, c, c2 = x.host, x.client, x.ids["C2"]
    r.ev["start"] = x.three()
    if not open_soldier_screen(r, h):
        return
    rep = q(c, {"cmd": "soldier_rename", "soldierId": c2, "name": "Hicks B"})
    got, s = converge(lambda: names(h).get(c2) == "Hicks B")
    top = stack(h)
    close_soldier_screen(r, h)
    nh, nc = names(h).get(c2), names(c).get(c2)
    x.first["C2"] = "Hicks B" if nh == nc == "Hicks B" else x.first["C2"]
    r.ev.update({"soldier_rename": rep, "wait s": s, "host stack at change": top, "end": x.three()})
    r.evidence()
    r.cell("guard: client soldier_rename sent", rep.get("ok") is True, rep)
    r.cell("guard: the host's C2 'Hicks B' within W with its InventoryState on top", got and top[-1:] == ["InventoryState"],
           [names(h).get(c2), top])
    r.cell("the host's base-screen OK put C2's old name back (no mark refresh)", nh == nc == "Hicks B", f"host {nh!r} client {nc!r}")


def row_layout_template_syncs(x, r):
    h, c = x.host, x.client
    r.ev["start"] = x.three()
    if not open_soldier_screen(r, c):
        return
    sel = bso(c, op="select", name=x.first["C"])
    k = ctrl1(c)
    close_soldier_screen(r, c)
    r.ev.update({"select": sel, "ctrl1": k})
    cs = k["slot0"]
    nv = r.cell("non-vacuity: select C", sel.get("ok") is True and sel.get("id") == x.ids["C"], sel)
    if not (r.cell("non-vacuity: the client's global 0 non-empty within 5 s", k["saved"] and cs and cs[0], k) and nv):
        r.evidence()
        return
    hs, s = None, 0.0
    if open_soldier_screen(r, h):
        _v, s = converge(lambda: slot0(h) == cs)
        hs = slot0(h)
        close_soldier_screen(r, h)
    r.ev.update({"host slot0": hs, "wait s": s, "end": x.three()})
    r.evidence()
    if not r.cell("guard: the host's slot 0 readable on its screen", hs is not None, hs):
        return
    if not r.cell("the client's layout template never reached the host", bool(hs[0]), f"host global {hs[0]}"):
        return
    r.cell("the host's (global, globalArmor, globalName) != the client's", hs == cs, [hs, cs])


def row_loadout_template_syncs(x, r):
    h, c = x.host, x.client
    sky = (next((cr for cr in q(c, {"cmd": "base_report", "base": HB}).get("crafts") or [] if cr.get("id") == x.sky), {})
           .get("items"))
    r.ev.update({"start": x.three(), "sky items (client)": sky, "host read before": bso(h, op="read", index=0)})
    rep = q(c, {"cmd": "open_craft_equipment", "base": HB, "craft_id": x.sky})
    if not r.cell("guard: client open_craft_equipment SKY", rep.get("ok") and rep.get("craftId") == x.sky
                  and wait_until(lambda: stack(c)[-1:] == ["CraftEquipmentState"], 30), [rep, stack(c)]):
        return
    save = bso(c, op="loadout_save", index=0)
    ok = q(c, {"cmd": "craft_equipment_ok"})
    r.cell("guard: client craft_equipment_ok", ok.get("ok") and wait_until(lambda: "CraftEquipmentState" not in stack(c), 30),
           [ok, stack(c)])
    cr = bso(c, op="read", index=0)
    _v, s = converge(lambda: (lambda hr: [hr.get("loadout"), hr.get("loadoutName")])(bso(h, op="read", index=0))
                     == [cr.get("loadout"), cr.get("loadoutName")])
    hr = bso(h, op="read", index=0)
    r.ev.update({"loadout_save": save, "client read": cr, "host read": hr, "wait s": s})
    r.evidence()
    if not r.cell("non-vacuity: the client's loadout 0 == the SKY's items (non-empty)", sky and cr.get("loadout") == sky,
                  [cr.get("loadout"), sky]):
        return
    if not r.cell("the client's craft loadout template never reached the host", bool(hr.get("loadout")), hr):
        return
    r.cell("the host's (loadout, loadoutName) != the client's", [hr.get("loadout"), hr.get("loadoutName")]
           == [cr.get("loadout"), cr.get("loadoutName")], [hr, cr])


def row_partner_armor_refused(x, r):
    h, c, hid = x.host, x.client, x.ids["H"]
    r.ev["start"] = x.three()
    st0 = [items(h).get(I1, 0), items(c).get(I1, 0)]
    f0 = q(c, {"cmd": "shared_stats"}).get("failCount")
    rep = q(c, {"cmd": "soldier_armor", "soldier_id": hid, "armor": A1, "base": HB})
    how, s = converge(lambda: "applied" if armor(h, hid) == A1 else
                      ("refused" if q(c, {"cmd": "shared_stats"}).get("failCount") != f0 else None))
    s1 = q(c, {"cmd": "shared_stats"})
    ah, ac, st1 = armor(h, hid), armor(c, hid), [items(h).get(I1, 0), items(c).get(I1, 0)]
    r.ev.update({"soldier_armor": rep, "settled": how, "wait s": s, "client failCount": [f0, s1.get("failCount")],
                 "lastFail": s1.get("lastFail"), "client stack": stack(c), "stock " + I1: [st0, st1], "end": x.three()})
    if how == "applied":  # cleanup without the fix: the host re-armors H
        r.ev["cleanup"] = [q(h, {"cmd": "soldier_armor", "soldier_id": hid, "armor": A0, "base": HB}),
                           converge(lambda: armor(h, hid) == A0 and armor(c, hid) == A0)]
    r.evidence()
    if not r.cell("non-vacuity: reply moved", rep.get("moved") is True, rep):
        return
    if not r.cell("the host applied the client's armor choice for the host's soldier", ah != A1,
                  f"host H {ah}, client H {ac}"):
        return
    r.cell("the client's failCount did not grow by one", s1.get("failCount") == (f0 or 0) + 1, [f0, s1.get("failCount")])
    r.cell(f"lastFail is not '{NOT_YOURS}'", s1.get("lastFail") == NOT_YOURS, s1.get("lastFail"))
    r.cell("H's armor changed", ah == ac == A0, [ah, ac])
    r.cell(f"the {I1} stock changed", st1 == st0, [st0, st1])


def row_world_equal(x, r):
    r.ev["start"] = r.ev["end"] = x.three()
    r.ev["world_diff now"] = shared_fixture.world_diff(x.host, x.client)
    r.ev["client save files now"] = session.save_files(x.js.client_dir)
    r.evidence()
    try:
        x.js.finish()
    except AssertionError as e:
        r.cell("js.finish", False, sbe.short(e, 1500))


def snap_personal(x):
    h, c = x.host, x.client
    return {"stocks": [stocks(h), stocks(c)], "lastSelectedArmor": [bso(g, op="read", index=0).get("lastSelectedArmor") for g in (h, c)],
            "client requests": q(c, {"cmd": "shared_resync_stats"}).get("requests"), "client failCount":
            q(c, {"cmd": "shared_stats"}).get("failCount"), "chkItems": [q(g, {"cmd": "shared_checksum"}).get("chkItems") for g in (h, c)]}


def row_personal_armor_syncs(x, r):
    h, c, cid, cn = x.host, x.client, x.ids["C"], x.first["C"]
    r.ev["start"] = x.three()
    if not set_armor(r, x, c, cid, A2, "setup C POWER"):
        return
    if not open_soldier_screen(r, c):
        return
    kk = keys(c)
    sel = bso(c, op="select", name=cn)
    r.ev["setup key 115"] = [sel, key(c, kk.get("keyInvSavePersonalEquipment")),
                             converge(lambda: personal(c, cid)[1] == A2, KEY_W)]
    close_soldier_screen(r, c)
    if not (r.cell("guard: the client's personal of C saved with POWER", personal(c, cid)[1] == A2 and personal(c, cid)[0],
                   personal(c, cid)) and set_armor(r, x, c, cid, A1, "setup C PERSONAL")):
        return
    b0 = snap_personal(x)
    if not open_soldier_screen(r, c):
        return
    sel = bso(c, op="select", name=cn)
    k108 = key(c, kk.get("keyInvLoadPersonalEquipment"))
    worn, s5 = converge(lambda: armor(c, cid) == A2, KEY_W)
    cst = stocks(c)
    got, s = converge(lambda: armor(h, cid) == A2) if worn else (False, 0.0)
    close_soldier_screen(r, c)
    time.sleep(SETTLE)
    b1 = snap_personal(x)
    r.ev.update({"select": sel, "key 108": k108, "client C POWER s": s5, "client stocks on screen": cst, "wait s": s,
                 "before": b0, "after": b1, "end": x.three()})
    r.evidence()
    nv = r.cell("non-vacuity: the client's C POWER within 5 s", worn, armor(c, cid))
    if not (r.cell("non-vacuity: the client's stocks PERSONAL +1 / POWER -1",
                   cst == [b0["stocks"][1][0] + 1, b0["stocks"][1][1] - 1], [b0["stocks"][1], cst]) and nv):
        return
    if not r.cell("the client's template armor change never reached the host", got, f"host C {armor(h, cid)}"):
        return
    r.cell("the host's stocks != the client's", b1["stocks"][0] == b1["stocks"][1], b1["stocks"])
    r.cell("the client's failCount changed", b1["client failCount"] == b0["client failCount"],
           [b0["client failCount"], b1["client failCount"]])
    r.cell("lastSelectedArmor differs or changed", b1["lastSelectedArmor"][0] == b1["lastSelectedArmor"][1]
           and b1["lastSelectedArmor"] == b0["lastSelectedArmor"], [b0["lastSelectedArmor"], b1["lastSelectedArmor"]])
    r.cell("the client asked for a resync", b1["client requests"] == b0["client requests"],
           [b0["client requests"], b1["client requests"]])


def row_partner_personal_readonly(x, r):
    h, c, hid, hn = x.host, x.client, x.ids["H"], x.first["H"]
    r.ev["start"] = x.three()
    if not set_armor(r, x, h, hid, A2, "setup H POWER"):
        return
    if not open_soldier_screen(r, h):
        return
    kk = keys(h)
    sel = bso(h, op="select", name=hn)
    belt = q(h, {"cmd": "inventory_move", "name": hn, "item": GREN, "slot": "belt"})
    k115 = key(h, kk.get("keyInvSavePersonalEquipment"))
    saved = converge(lambda: personal(h, hid)[1] == A2 and GREN in personal(h, hid)[0], KEY_W)
    drop = q(h, {"cmd": "inventory_move", "name": hn, "item": GREN, "slot": "ground", "from": "unit"})
    close_soldier_screen(r, h)
    r.ev["setup"] = {"select": sel, "belt": belt, "key 115": k115, "saved": saved, "drop": drop}
    synced = converge(lambda: personal(c, hid) == personal(h, hid))
    r.ev["setup"]["client record of H"] = [personal(c, hid), synced]
    if not (r.cell("guard: the host's staging (grenade on, key 115, grenade off)", sel.get("ok") and belt.get("moved") is True
                   and saved[0] and drop.get("moved") is True, r.ev["setup"])
            and r.cell("guard: the client's record of H's personal == the host's", synced[0], personal(c, hid))
            and set_armor(r, x, h, hid, A1, "setup H PERSONAL")):
        r.evidence()
        return
    want = personal(c, hid)[0].count(GREN)
    s0, a0 = stocks(c), q(h, {"cmd": "shared_stats"}).get("applyCount")
    if not open_soldier_screen(r, c):
        return
    sel = bso(c, op="select", name=hn)
    g0 = grenades(c, hn)
    k108 = key(c, kk.get("keyInvLoadPersonalEquipment"))
    got, s5 = converge(lambda: grenades(c, hn) != g0, KEY_W)  # the whole key window, any change
    g1, ac, ah, s1 = grenades(c, hn), armor(c, hid), armor(h, hid), stocks(c)
    time.sleep(SETTLE)
    a1 = q(h, {"cmd": "shared_stats"}).get("applyCount")
    close_soldier_screen(r, c)
    r.ev.update({"select": sel, "key 108": k108, "grenades before / after / personal": [g0, g1, want, s5],
                 "armor client / host": [ac, ah], "client stocks": [s0, s1], "host applyCount": [a0, a1], "end": x.three()})
    r.evidence()
    # the personal-layout key does nothing on the host's soldier on the client's SHARED base screen.
    r.cell("H's grenades changed on the client's screen within 5 s of key 108 (read-only)", not got,
           [g0, g1, want, s5])
    r.cell("the client re-armored the host's soldier", ac == A1, f"client H {ac}, host H {ah}")
    r.cell("the client's stocks changed", s1 == s0, [s0, s1])
    r.cell("the host's applyCount changed within 1 s of the key", a1 == a0, [a0, a1])
    r.cell("the host's H is not PERSONAL", ah == A1, ah)


def boot_miss(tag, e, rids, results, x=None):
    cap = {"error": sbe.short(e, 1500)}
    if x is not None:
        for g in (x.host, x.client):
            cap[f"{g.name} get_state"] = stack(g)
            cap[f"{g.name} get_soldiers {x.base}"] = [(i, s.get("name"), s.get("owner")) for i, s in roster(g, x.base).items()]
    print(f"CAPTURE boot {tag} (boot miss): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    for rid in rids:
        results[rid] = False
        print(f"EVIDENCE {rid}: {json.dumps({'boot': 'miss'})}\nFAIL {rid}: boot", flush=True)


def run_rows(x, rows, results, walls):
    for rid, fn in rows:
        r, t1 = Row(rid, x), time.time()
        try:
            fn(x, r)
        except Exception as e:
            r.cell(f"guard: {rid} exception", False, sbe.short(e))
        for g in (x.host, x.client):  # a stopped row (or base_write_6's refusal box with the fix, CoopState 556)
            # leaves no screen behind
            before = stack(g)
            if (before or [""])[-1] != GEO:
                rep = q(g, {"cmd": "close_screens"})
                wait_until(lambda: (stack(g) or [""])[-1] == GEO, 5.0)
                r.cap[f"{g.name} cleanup"] = {"before": before, "close_screens": rep, "after": stack(g)}
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)


def shared_boot(tag, ports, gifts, rids, rows, results, walls):
    t0, js, x = time.time(), None, None
    try:
        try:
            js = shared_fixture.bring_up(tag, ports)
            x = X(js.host, js.client, js)
            sbe.setup(x)  # option OFF on both, seats differ, H / C / C2, the SKYRANGER, the HostBase index (raises on a miss)
            x.first = {k: getattr(x, k) for k in ("H", "C", "C2")}
            x.ids = {k: x.ids[k] for k in ("H", "C", "C2")}
            given = {gc.name: [q(gc, {"cmd": "give_items", "item": i, "count": 4, "base": HB}).get("stored") for i in gifts]
                     for gc in (x.host, x.client)}
            it = {gc.name: [items(gc).get(i, 0) for i in (I1, I2)] for gc in (x.host, x.client)}
            chk = [q(gc, {"cmd": "shared_checksum"}).get("chkItems") for gc in (x.host, x.client)]
            if not (given["host"] == given["client"] and None not in given["host"] and it["host"] == it["client"]
                    and chk[0] == chk[1]):
                raise RuntimeError(f"fixture: stocks given {given} items {it} chkItems {chk}")
            walls["boot " + tag] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every row of this boot "boot" with ONE CAPTURE line
            return boot_miss(tag, e, rids, results, x)
        run_rows(x, rows, results, walls)
    finally:
        if js is not None:
            js.shutdown()


def main():
    t0, results, walls = time.time(), {}, {}
    shared_boot(TAG_SHARED, PORTS_SHARED, [I1], ROWS_SHARED,
                (("base_write_1", row_client_renames_own), ("base_write_2", row_partner_rename_refused),
                 ("base_write_3", row_host_screen_keeps_rename), ("base_write_4", row_layout_template_syncs),
                 ("base_write_5", row_loadout_template_syncs), ("base_write_6", row_partner_armor_refused),
                 ("base_write_7", row_world_equal)), results, walls)
    shared_boot(TAG_ARMOR, PORTS_ARMOR, [I1, I2], ROWS_ARMOR,
                (("base_write_8", row_personal_armor_syncs), ("base_write_9", row_partner_personal_readonly)),
                results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    print(f"\ntest_shared_base_writes: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
