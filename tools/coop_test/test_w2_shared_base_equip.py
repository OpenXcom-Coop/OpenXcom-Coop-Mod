"""W2-H20 (owner D255 a; spec rewrite/prompts/w2h20_shared_base_equip_sync.md (f), Q1 a .. Q9 a; TASK 0
rewrite/w2h20-task0/CONSTANTS.md; from U6 stage B's rewrite/u6-task0/stageB.patch, U6 Q4): in SHARED, OK on a base
equipment screen (soldier or craft inventory) sends the presser's OWN changed soldiers' gear to the host, which applies an
entry only for a soldier the sending seat owns (Q5 a); both machines end with the same record (layout, personal layout,
its armor); the partner's soldiers go back to their gear at open (aud-E1-11). Today nothing carries it (F7738-F7742).
Boot A (SHARED): bring_up("w2h20a", (48704, 48705, 47922)), oxceAlternateCraftEquipmentManagement OFF on both. H / C / C2
= the first HostBase soldier (base_report order) owned by the host's localSeat / the first / second owned by the client's
(names roll per boot, S25). rec(gc, n) = n's soldier_layouts {base: HostBase} entry on gc; whole record = (layout,
personal, personalArmor), exact. W = 10 s at 0.25 s polls (Q9 a); partner-unchanged cells read at once.
  H20-1 host: soldier screen, inventory_move {H, STR_PISTOL, left}, close. Non-vacuity: moved, host pistols in H 0 -> 1.
        (A) the client's whole record of H == the host's within W; (B) the host's records of the client's soldiers == before.
  H20-2 client: the same on C. (A) the host's C == the client's within W; (B) the client's records of the host's
        soldiers == the host's (F7741).
  H20-3 every HostBase soldier's whole record equal on both within W (F7742).
  H20-4 client: SKYRANGER craft screen, inventory_move {C2, STR_PISTOL, left}, close. Non-vacuity: moved, client pistols
        in C2 +1. (A) the host's C2 == the client's within W; (B) the client's records of the host's soldiers == the host's.
  H20-5 client: soldier screen, inventory_move {C, STR_PISTOL, ground, from: unit}, key keyInvSavePersonalEquipment,
        close. Non-vacuity: moved, key ok, the client's personal of C [] -> non-empty, its pistols in C 1 -> 0. The host's
        whole record of C == the client's within W.
  H20-6 owner gate (Q5 a): client shared_cmd soldier_equip {H: FORGED, C2: FORGED}; the client's failCount unchanged
        within W; the host's C2 layout == one item {STR_PISTOL, STR_LEFT_HAND, 0, 0}, the client's C2 == the host's, the
        host's H == before, the client's H == the host's.
  H20-7 js.finish(): world equality + replica zero-disk (guard; last in Boot A).
Boot B (SEPARATE, labels 48706 / 48707, lobby 47923): H20-8 client: ClientBase soldier screen, inventory_move {S,
  STR_PISTOL, left} (S = the first unit with an empty left hand), close: S's pistols 0 -> 1 on the client; both
  machines' shared_stats cmd / applyCount / failCount unchanged 1 s after the close (guard).
One EVIDENCE line per row (both machines' H, C, C2 at its start and end, compact) before its verdict; a failed row prints
ONE CAPTURE line (both machines' soldier_layouts, base_report, shared_stats, stacks; the editor's inventory_ground). A
boot miss fails its rows "boot" with one CAPTURE line. Every row runs after a failure. ONE run (WV-D95); exit 0 iff
every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

TAG_A, PORTS_A = "w2h20a", (48704, 48705, 47922)
TAG_B, LABELS_B, LOBBY_B = "w2h20b", (48706, 48707), "47923"
HB, CB, OPT, ITEM = "HostBase", "ClientBase", "oxceAlternateCraftEquipmentManagement", "STR_PISTOL"
W, POLL, GEO = 10.0, 0.25, "GeoscapeState"
FORGED = "l:\n  - {itemType: STR_PISTOL, slot: STR_LEFT_HAND}\n"
UNKNOWN = "unknown command: soldier_equip"
ROWS_A = ["H20-%d" % n for n in range(1, 8)]
ORDER = ROWS_A + ["H20-8"]


def short(e, n=600):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead socket is evidence, not a test error
        return {"error": short(e, 160)}


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:
        return ["<get_state: %s>" % short(e, 120)]


def wait_until(pred, timeout, interval=POLL):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v
        time.sleep(interval)


def converge(pred):
    """(the predicate's last value, seconds) after at most W."""
    t0 = time.time()
    v = wait_until(pred, W)
    return v, round(time.time() - t0, 2)


def layouts(gc, base=HB):
    """soldier_layouts {base} on gc -> {name: entry} (the W2-H20 probe)."""
    r = q(gc, {"cmd": "soldier_layouts", "base": base})
    return {s.get("name"): s for s in r.get("soldiers") or []}


def whole(e):
    return None if e is None else [e.get("layout"), e.get("personal"), e.get("personalArmor")]


def pistols(e):
    return None if e is None else sum(1 for i in e.get("layout") or [] if i.get("type") == ITEM)


def compact(e):
    if e is None:
        return None
    f = lambda L: ["%s@%s:%s,%s%s" % (i.get("type"), i.get("slot"), i.get("x"), i.get("y"),
                                      ("+" + "+".join(i["ammo"])) if i.get("ammo") else "") for i in L or []]
    return {"layout": f(e.get("layout")), "personal": f(e.get("personal")), "armor": e.get("personalArmor")}


def forged_one(e):
    L = (e or {}).get("layout") or []
    return len(L) == 1 and [L[0].get(k) for k in ("type", "slot", "x", "y")] == [ITEM, "STR_LEFT_HAND", 0, 0]


def stats3(gc):
    return {k: v for k, v in q(gc, {"cmd": "shared_stats"}).items() if k in ("cmd", "applyCount", "failCount")}


class X:
    def __init__(self, host, client, js=None, base=HB):
        self.js, self.host, self.client, self.base = js, host, client, base
        self.H = self.C = self.C2 = self.sky = self.hb_index = None
        self.ids, self.opts, self.seats = {}, {}, {}

    def three(self):
        """Both machines' records of H, C and C2 (compact): each row's EVIDENCE start / end."""
        out = {}
        for gc in (self.host, self.client):
            L = layouts(gc)
            out[gc.name] = {k: compact(L.get(n)) for k, n in (("H", self.H), ("C", self.C), ("C2", self.C2))}
        return out

    def own(self, L, side):
        return {n: e for n, e in L.items() if e.get("owner") == self.seats[side]}


class Row:
    def __init__(self, rid, x):
        self.rid, self.x, self.fails, self.cap, self.printed = rid, x, [], {}, False
        self.ev = {"options": x.opts, "seats": x.seats, "H": x.H, "C": x.C, "C2": x.C2}

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
            for gc in (self.x.host, self.x.client):
                self.cap[f"{gc.name} soldier_layouts {self.x.base}"] = q(gc, {"cmd": "soldier_layouts", "base": self.x.base})
                self.cap[f"{gc.name} base_report {self.x.base}"] = q(gc, {"cmd": "base_report", "base": self.x.base})
                self.cap[f"{gc.name} shared_stats"] = q(gc, {"cmd": "shared_stats"})
                self.cap[f"{gc.name} stack (after cleanup)"] = stack(gc)
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def open_soldier_screen(r, gc, base=HB):
    """open_soldiers -> SoldiersState -> soldiers_inventory (opened) -> InventoryState (stage B's open)."""
    rep = q(gc, {"cmd": "open_soldiers", "base": base})
    if not r.cell(f"G: {gc.name} open_soldiers {base}",
                  rep.get("ok") and wait_until(lambda: "SoldiersState" in stack(gc), 30), [rep, stack(gc)]):
        return False
    rep = q(gc, {"cmd": "soldiers_inventory"})
    return r.cell(f"G: {gc.name} soldiers_inventory",
                  rep.get("opened") is True and wait_until(lambda: "InventoryState" in stack(gc), 30), [rep, stack(gc)])


def close_soldier_screen(r, gc):
    """battle_inventory ok -> InventoryState gone -> soldiers_ok -> SoldiersState gone (stage B's close)."""
    rep = q(gc, {"cmd": "battle_inventory", "action": "ok"})
    r.cell(f"G: {gc.name} battle_inventory ok",
           rep.get("ok") and wait_until(lambda: "InventoryState" not in stack(gc), 30), [rep, stack(gc)])
    rep = q(gc, {"cmd": "soldiers_ok"})
    r.cell(f"G: {gc.name} soldiers_ok",
           rep.get("ok") and wait_until(lambda: "SoldiersState" not in stack(gc), 30), [rep, stack(gc)])


def open_craft_screen(r, x, gc):
    """open_craft_equipment {HostBase, SKY} -> CraftEquipmentState -> craft_inventory (opened) -> InventoryState."""
    rep = q(gc, {"cmd": "open_craft_equipment", "base": HB, "craft_id": x.sky})
    if not r.cell(f"G: {gc.name} open_craft_equipment {HB} {x.sky}", rep.get("ok") and rep.get("craftId") == x.sky
                  and wait_until(lambda: "CraftEquipmentState" in stack(gc), 30), [rep, stack(gc)]):
        return False
    rep = q(gc, {"cmd": "craft_inventory"})
    return r.cell(f"G: {gc.name} craft_inventory",
                  rep.get("opened") is True and wait_until(lambda: "InventoryState" in stack(gc), 30), [rep, stack(gc)])


def close_craft_screen(r, gc):
    """battle_inventory ok -> InventoryState gone -> craft_equipment_ok -> CraftEquipmentState gone."""
    rep = q(gc, {"cmd": "battle_inventory", "action": "ok"})
    r.cell(f"G: {gc.name} battle_inventory ok",
           rep.get("ok") and wait_until(lambda: "InventoryState" not in stack(gc), 30), [rep, stack(gc)])
    rep = q(gc, {"cmd": "craft_equipment_ok"})
    r.cell(f"G: {gc.name} craft_equipment_ok",
           rep.get("ok") and wait_until(lambda: "CraftEquipmentState" not in stack(gc), 30), [rep, stack(gc)])


def move(r, gc, args):
    """inventory_move; the editor's inventory_ground before / after is kept for the CAPTURE."""
    r.cap[f"{gc.name} inventory_ground before"] = g = q(gc, {"cmd": "inventory_ground"})
    rep = q(gc, dict({"cmd": "inventory_move", "item": ITEM}, **args))
    r.cap[f"{gc.name} inventory_ground after"] = q(gc, {"cmd": "inventory_ground"})
    r.ev["inventory_move"] = rep
    r.ev["ground"] = {"units": g.get("units"), ITEM: (g.get("items") or {}).get(ITEM)}
    return rep


def diffs(x):
    h, c = layouts(x.host), layouts(x.client)
    return sorted(n for n in set(h) | set(c) if whole(h.get(n)) != whole(c.get(n)))


def edit_row(x, r, editor, other, who, partner_side, craft=False):
    """H20-1 / H20-2 / H20-4: `editor` moves STR_PISTOL into the left hand of `who` on a base screen and presses OK."""
    name = getattr(x, who)
    r.ev["start"] = x.three()
    ed0 = layouts(editor)
    if not (open_craft_screen(r, x, editor) if craft else open_soldier_screen(r, editor)):
        return
    rep = move(r, editor, {"name": name, "slot": "left"})
    (close_craft_screen if craft else close_soldier_screen)(r, editor)
    ed1, ot1 = layouts(editor), layouts(other)
    p0, p1 = pistols(ed0.get(name)), pistols(ed1.get(name))
    nv = r.cell(f"non-vacuity: {editor.name} moved", rep.get("moved") is True, rep)
    nv = r.cell(f"non-vacuity: {ITEM} in the {editor.name}'s layout of {who} " + ("+1" if craft else "0 -> 1"),
                p0 is not None and p1 == p0 + 1 and (craft or p0 == 0), f"{p0} -> {p1}") and nv
    # (B), read at once after the close: the partner's soldiers as the editor's OK left them
    if editor is x.host:  # the host's records of the client's soldiers, before / after
        part = x.own(ed1, partner_side)
        changed = sorted(n for n in part if whole(ed0.get(n)) != whole(ed1.get(n)))
    else:  # the client's records of the host's soldiers == the host's
        part = x.own(ot1, partner_side)
        changed = sorted(n for n in part if whole(ed1.get(n)) != whole(ot1.get(n)))
    got, s = (converge(lambda: whole(layouts(other).get(name)) == whole(layouts(editor).get(name)))
              if nv else (False, 0.0))
    r.ev["wait s"] = s
    r.ev["(B) partner soldiers changed"] = changed
    r.ev["end"] = end = x.three()
    r.evidence()
    if not nv:
        r.cap[f"{editor.name} get_state"] = stack(editor)
        return
    where = "craft-screen" if craft else "base-screen"
    r.cell(f"(A) the {editor.name}'s {where} edit never reached the {other.name}", got,
           f"{other.name} {who} {end[other.name][who]} vs {editor.name} {who} {end[editor.name][who]}")
    r.cell(f"(B) the {editor.name}'s OK rewrote the {partner_side}'s soldiers"
           + ("" if craft or editor is x.host else " (F7741)"), not changed, f"{len(changed)} of {len(part)}: {changed}")


def h20_1(x, r):  # the host edits H
    edit_row(x, r, x.host, x.client, "H", "client")


def h20_2(x, r):  # the client edits C
    edit_row(x, r, x.client, x.host, "C", "host")


def h20_4(x, r):  # the client edits C2 on the craft screen
    edit_row(x, r, x.client, x.host, "C2", "host", craft=True)


def h20_3(x, r):
    r.ev["start"] = x.three()
    _d, s = converge(lambda: not diffs(x))
    k = diffs(x)
    r.ev["wait s"], r.ev["differ"] = s, k
    r.ev["end"] = x.three()
    r.evidence()
    r.cell(f"{len(k)} soldiers carry different gear on the two machines (F7742)", not k, k)


def h20_5(x, r):
    c, h, name = x.client, x.host, x.C
    r.ev["start"] = x.three()
    c0 = layouts(c).get(name)
    if not open_soldier_screen(r, c):
        return
    key = (q(c, {"cmd": "equip_layouts"}).get("keys") or {}).get("keyInvSavePersonalEquipment")
    rep = move(r, c, {"name": name, "slot": "ground", "from": "unit"})
    krep = q(c, {"cmd": "inject_input", "kind": "key", "key": key})
    saved = wait_until(lambda: (layouts(c).get(name) or {}).get("personal"), 5.0)  # the key lands on the next frame
    r.ev["key"], r.ev["inject_input"] = key, krep
    close_soldier_screen(r, c)
    c1 = layouts(c).get(name)
    nv = r.cell("non-vacuity: client moved", rep.get("moved") is True, rep)
    nv = r.cell("non-vacuity: key reply ok", krep.get("ok") is True and key is not None, [key, krep]) and nv
    nv = r.cell("non-vacuity: the client's personal of C [] -> non-empty",
                not (c0 or {}).get("personal") and bool((c1 or {}).get("personal")) and bool(saved),
                [compact(c0), compact(c1)]) and nv
    nv = r.cell(f"non-vacuity: {ITEM} in the client's layout of C 1 -> 0", pistols(c0) == 1 and pistols(c1) == 0,
                f"{pistols(c0)} -> {pistols(c1)}") and nv
    got, s = (converge(lambda: whole(layouts(h).get(name)) == whole(layouts(c).get(name))) if nv else (False, 0.0))
    r.ev["wait s"] = s
    r.ev["end"] = end = x.three()
    r.evidence()
    if nv:
        r.cell("the client's personal layout of C never reached the host", got,
               f"host C {end['host']['C']} vs client C {end['client']['C']}")


def h20_6(x, r):
    h, c = x.host, x.client
    r.ev["start"] = x.three()
    h0 = layouts(h)
    f0 = q(c, {"cmd": "shared_stats"}).get("failCount")
    entries = [{"id": x.ids["H"], "layout": FORGED}, {"id": x.ids["C2"], "layout": FORGED}]
    rep = q(c, {"cmd": "shared_cmd", "jcmd": "soldier_equip", "baseId": x.hb_index, "payload": {"soldiers": entries}})

    def settled():
        if q(c, {"cmd": "shared_stats"}).get("failCount") != f0:
            return "shared_fail"
        hc2 = layouts(h).get(x.C2)
        return "applied" if forged_one(hc2) and whole(layouts(c).get(x.C2)) == whole(hc2) else None
    how, s = converge(settled)
    s1 = q(c, {"cmd": "shared_stats"})
    h1, c1 = layouts(h), layouts(c)
    r.ev.update({"shared_cmd": rep, "settled": how, "wait s": s, "client failCount": [f0, s1.get("failCount")],
                 "client lastFail": s1.get("lastFail"), "client stack": stack(c),
                 "client dialog code": q(c, {"cmd": "coop_dialog_info"}).get("code")})
    r.ev["end"] = x.three()
    r.evidence()
    r.cell("G: shared_cmd sent", rep.get("ok") is True, rep)
    if not r.cell("the host does not know soldier_equip" if s1.get("lastFail") == UNKNOWN
                  else "the client's shared_fail count changed", s1.get("failCount") == f0,
                  f"client failCount {f0} -> {s1.get('failCount')}, lastFail {s1.get('lastFail')!r}"):
        return  # the gate cells below need the command applied
    r.cell("the host's C2 layout is not the forged one item", forged_one(h1.get(x.C2)), compact(h1.get(x.C2)))
    r.cell("the client's C2 != the host's", whole(c1.get(x.C2)) == whole(h1.get(x.C2)),
           [compact(c1.get(x.C2)), compact(h1.get(x.C2))])
    r.cell("the host's H != before (the owner gate)", whole(h1.get(x.H)) == whole(h0.get(x.H)),
           [compact(h0.get(x.H)), compact(h1.get(x.H))])
    r.cell("the client's H != the host's", whole(c1.get(x.H)) == whole(h1.get(x.H)),
           [compact(c1.get(x.H)), compact(h1.get(x.H))])


def h20_7(x, r):
    r.ev["start"] = r.ev["end"] = x.three()
    r.ev["world_diff now"] = shared_fixture.world_diff(x.host, x.client)
    r.ev["client save files now"] = session.save_files(x.js.client_dir)
    r.evidence()
    try:
        x.js.finish()
    except AssertionError as e:
        r.cell("js.finish", False, short(e, 1500))


def h20_8(x, r):
    h, c = x.host, x.client
    s0 = {gc.name: stats3(gc) for gc in (h, c)}
    L0 = layouts(c, CB)
    r.ev["client roster"] = [(n, e.get("id"), e.get("owner")) for n, e in L0.items()]
    if not open_soldier_screen(r, c, CB):
        return
    g = q(c, {"cmd": "inventory_ground"})
    S = next((u.get("name") for u in g.get("soldiers") or [] if "STR_LEFT_HAND" not in (u.get("slots") or {})), None)
    rep = move(r, c, {"name": S, "slot": "left"})
    close_soldier_screen(r, c)
    L1 = layouts(c, CB)
    time.sleep(1.0)  # a stray shared command from this OK would be counted by now
    s1 = {gc.name: stats3(gc) for gc in (h, c)}
    p0, p1 = pistols(L0.get(S)), pistols(L1.get(S))
    r.ev.update({"S": S, "start": {"client S": compact(L0.get(S))}, "end": {"client S": compact(L1.get(S))},
                 "shared_stats before": s0, "shared_stats after": s1})
    r.evidence()
    r.cell("non-vacuity: client moved", S is not None and rep.get("moved") is True, [S, rep])
    r.cell(f"{ITEM} in the client's layout of S 0 -> 1", p0 == 0 and p1 == 1, f"{p0} -> {p1}")
    r.cell("shared_stats cmd / applyCount / failCount changed", s0 == s1, [s0, s1])


def setup(x):
    for gc in (x.host, x.client):
        x.opts[gc.name] = q(gc, {"cmd": "option_values", "ids": [OPT]}).get("values")
        x.seats[gc.name] = q(gc, {"cmd": "get_coop"}).get("localSeat")
    rep = q(x.host, {"cmd": "base_report", "base": HB})
    sol = rep.get("soldiers") or []
    hs = [s for s in sol if s.get("owner") == x.seats["host"]]
    cs = [s for s in sol if s.get("owner") == x.seats["client"]]
    for k, s in (("H", hs[:1]), ("C", cs[:1]), ("C2", cs[1:2])):
        setattr(x, k, s[0]["name"] if s else None)
        x.ids[k] = s[0]["id"] if s else None
    crafts = rep.get("crafts") or []
    x.sky = next((c.get("id") for c in crafts if c.get("type") == "STR_SKYRANGER"), None)
    first = next((c.get("type") for c in crafts if c.get("id") == x.sky), None)  # open_craft_equipment matches by id
    idx = {gc.name: next((i for i, b in enumerate(q(gc, {"cmd": "get_soldiers"}).get("bases") or [])
                          if b.get("name") == HB), None) for gc in (x.host, x.client)}
    x.hb_index = idx["client"]
    probe = {gc.name: len(layouts(gc)) for gc in (x.host, x.client)}
    off = all((x.opts.get(n) or {}).get(OPT) is False for n in ("host", "client"))
    if not (x.H and x.C and x.C2 and off and x.seats["host"] != x.seats["client"] and first == "STR_SKYRANGER"
            and x.hb_index is not None and idx["host"] == idx["client"] and probe["host"] == probe["client"] == len(sol)):
        raise RuntimeError(f"fixture: H {x.H} C {x.C} C2 {x.C2} seats {x.seats} options {x.opts} sky {x.sky} "
                           f"{first} HostBase index {idx} soldier_layouts {probe} / base_report {len(sol)}")


def boot_miss(tag, e, rids, results, x=None):
    cap = {"error": short(e, 1500)}
    if x is not None:
        for g in (x.host, x.client):
            cap[f"{g.name} get_state"] = stack(g)
            cap[f"{g.name} base_report {x.base}"] = q(g, {"cmd": "base_report", "base": x.base})
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
            r.cell(f"G: {rid} exception", False, short(e))
        for g in (x.host, x.client):  # a stopped row (or H20-6's red shared-fail box, T0-5) leaves no screen behind
            before = stack(g)
            if (before or [""])[-1] != GEO:
                rep = q(g, {"cmd": "close_screens"})
                wait_until(lambda: (stack(g) or [""])[-1] == GEO, 5.0)
                r.cap[f"{g.name} cleanup"] = {"before": before, "close_screens": rep, "after": stack(g)}
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)


def boot_a(results, walls):
    t0, js, x = time.time(), None, None
    try:
        try:
            js = shared_fixture.bring_up(TAG_A, PORTS_A)
            x = X(js.host, js.client, js)
            setup(x)
            walls["boot A"] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every Boot A row "boot" with ONE CAPTURE line
            return boot_miss(TAG_A, e, ROWS_A, results, x)
        run_rows(x, (("H20-1", h20_1), ("H20-2", h20_2), ("H20-3", h20_3), ("H20-4", h20_4), ("H20-5", h20_5),
                     ("H20-6", h20_6), ("H20-7", h20_7)), results, walls)
    finally:
        if js is not None:
            js.shutdown()


def boot_b(results, walls):
    t0 = time.time()
    h = GameClient("host", LABELS_B[0], make_user_dir(TAG_B + "_host"))
    c = GameClient("client", LABELS_B[1], make_user_dir(TAG_B + "_client"))
    x = X(h, c, base=CB)
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=LOBBY_B, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            walls["boot B"] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails H20-8 "boot" with ONE CAPTURE line
            return boot_miss(TAG_B, e, ["H20-8"], results, x)
        run_rows(x, (("H20-8", h20_8),), results, walls)
    finally:
        shutdown_clients(h, c)


def main():
    t0, results, walls = time.time(), {}, {}
    boot_a(results, walls)
    boot_b(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    print(f"\ntest_w2_shared_base_equip: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
