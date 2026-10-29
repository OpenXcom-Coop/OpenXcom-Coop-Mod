"""test_base_visit_pointer.py: in a SEPARATE campaign, while the base's owner and a visiting partner are both on that
base's Soldiers inventory, each sees the other's pointer and name, and the visitor's held pile item leaves the owner's
pile and is drawn under the visitor's pointer, exactly as they are drawn in SHARED (test_base_partner_pointer,
test_base_partner_held). This holds only on the same pile: the key is the base's _coop_base_id (the owner's base and the
visitor's mirror carry the same id) + the pile. No SEPARATE equip sync is added, and the read-only partner view
(test_base_partner_view) stays SHARED-only.
The boot (SEPARATE, key 49418, dirs base_visit_pointer_host / _client): settle session.new_campaign +
geo.wait_both_ready; guest_move the fixture's own step (a visitor sees only its own soldiers at a peer base, as
test_coop_peer_equip_screens shows, so the host first transfers one of its soldiers to ClientBase); host_visit the host
visits ClientBase from its geoscape (insideCoopBase, the guest listed); owner_screen the client (OWNER) opens
ClientBase's Soldiers inventory; visitor_screen the host (VISITOR) opens its view of it (the mirror). Preconditions: an
InventoryState on top of both; PILE_TYPE's cell >= 2 entries on both screens (preferred value + test_base_partner_held's
rule, logged). A spine miss = every row FAIL "spine" with ONE CAPTURE line.
Reads: drawn = event_state.equip.presence.drawn; keys / snapshots = event_state.equip.basePresence (localKey, peer, recv,
held; absent or unregistered reads "" / -1 / false, as on a build without this feature); a cell's count =
inventory_view.ground entries at (x, y); the inventory offset = the observer's cursor_pos; move(gc, pt) =
test_base_partner_pointer's real motion recipe.
  both_pointers      move(host, PT1), poll the client up to W_PTR; move(client, PT2), poll the host up to W_PTR:
                     client_pointer_on_host (the host draws the client's pointer at its invX / invY + PT2 with
                     CLIENT_NAME at + (10, 4)), host_pointer_on_client (the client draws the host's at PT1 with HOST_NAME)
  visitor_held_item  the host lifts PILE_TYPE's cell (real left click), then right-clicks: owner_pile_drops (the client's
                     count one lower within W_PTR while the host holds), owner_draws_held_item (the client draws its
                     held.local under the host's pointer), owner_pile_back (the count back within W_PTR of the right
                     click, owner_pile_drops seen first)
  visitor_leaves     the host's real OK, soldiers_ok, leave_base, session.wait_back_on_geoscape; poll the client up to
                     W_PTR: leave_sends_pointer_off (the client's peer = the host's explicit on false, a new receive),
                     pointer_hidden_after_leave (guard: the client's drawn.ptr false)
  different_bases    the host opens HostBase's Soldiers inventory (its own base), move(host, PT1); watch the client for
                     W_PTR: peer_key_is_host_key (the client's peer.key = the host's localKey, non-empty and not the
                     client's), no_pointer_drawn (guard: neither draws a pointer)
  crash_check        both close their screens; no_new_crash_file (guard: no new crash file in this lane's crash folder,
                     both games alive)
On a build without this feature, 7 of the 10 cells fail: client_pointer_on_host, host_pointer_on_client,
owner_pile_drops, owner_draws_held_item, owner_pile_back, leave_sends_pointer_off, peer_key_is_host_key; the 3 guards
pass. With it, 10 / 10 pass. One EVIDENCE line per row, one PASS / FAIL line per cell, then the row verdict; every row
runs after a failure (a precondition miss ends its own row, its later cells "not reached"); every row ends with both
cursors empty (recorded). Run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when
every cell passes, else 2.

Run:  python tools/coop_test/test_base_visit_pointer.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
import test_shared_base_equip as h20  # noqa: E402  (main-guarded: q / stack, screens, wait_until, short)
import test_base_partner_pointer as bpp  # noqa: E402  (main-guarded: move, cpos, drawn, bp, top, alive, PT1 / PT2)
import test_base_partner_held as bph  # noqa: E402  (main-guarded: view, cur, types, count, kinds, local, under, lift)
from test_shared_base_equip import q, stack, open_soldier_screen, close_soldier_screen  # noqa: E402

TAG, LOBBY = "base_visit_pointer", "49418"  # the lobby key; the two GameClient labels are inert
HB, CB, GEO, INV, GROUND = "HostBase", "ClientBase", "GeoscapeState", "InventoryState", "STR_GROUND"
PT1, PT2 = bpp.PT1, bpp.PT2        # test_base_partner_pointer's points: on the Inventory surface, on no widget of the base screens
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"  # session.new_campaign's names; the overlay names the peer
NAME_DX, NAME_DY = bpp.NAME_DX, bpp.NAME_DY
PILE_PIN = "STR_PISTOL_CLIP"       # preferred; else the first type (by its lowest host cell) with a cell of >= 2 entries on both
W_PTR, W, VISIT_S, POLL = 2.0, 10.0, 60.0, 0.05
CELLS = {
    "both_pointers": ["client_pointer_on_host", "host_pointer_on_client"],
    "visitor_held_item": ["owner_pile_drops", "owner_draws_held_item", "owner_pile_back"],
    "visitor_leaves": ["leave_sends_pointer_off", "pointer_hidden_after_leave"],
    "different_bases": ["peer_key_is_host_key", "no_pointer_drawn"],
    "crash_check": ["no_new_crash_file"],
}
# visitor_leaves before different_bases: different_bases needs the visit ended
ORDER = ["both_pointers", "visitor_held_item", "visitor_leaves", "different_bases", "crash_check"]
EV = {}  # every row's EVIDENCE, by row id, plus the spine (kept for a caller of main)


class Row(bpp.Row):
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


class X:
    def __init__(self, host, client):
        self.host, self.client = host, client
        self.seats, self.spine, self.crash0, self.pile, self.pile_cell, self.guest = {}, {}, set(), None, {}, None


# ===================== probes =====================


def peer(gc):
    return bpp.bp(gc).get("peer") or {}


def key(gc):
    return bpp.bp(gc).get("localKey") or ""


def look(x):
    """EVIDENCE: each machine's top state, cursor_pos, drawn record, basePresence (localKey, peer, recv, held)."""
    out = {}
    for gc in (x.host, x.client):
        b = bpp.bp(gc)
        out[gc.name] = {"top": bpp.top(gc), "cursor": bpp.cpos(gc), "cursorItem": bph.cur(gc),
                        "drawn": {k: bpp.drawn(gc).get(k) for k in ("ptr", "x", "y", "name", "nameShown", "nameX", "nameY", "held")},
                        "basePresence": {k: b.get(k) for k in ("screen", "localKey", "peer", "recv", "sent", "held")}}
    return out


def drawn_at(gc, want, name):
    """gc draws the partner's pointer at `want` with `name` shown at the pointer + (NAME_DX, NAME_DY)."""
    d = bpp.drawn(gc)
    return (d.get("ptr") is True and [d.get("x"), d.get("y")] == want and d.get("nameShown") is True and d.get("name") == name
            and [d.get("nameX"), d.get("nameY")] == [want[0] + NAME_DX, want[1] + NAME_DY])


def ready(x, r):
    """A row's head: both base screens on top, both cursors empty (an earlier row's leftover is recorded and cleared)."""
    for gc in (x.host, x.client):
        if bpp.top(gc) != INV:
            raise bph.Stop(f"precondition: {gc.name}'s base inventory screen on top ({stack(gc)})")
        if bph.cur(gc) not in (None, -1):
            r.ev.setdefault("leftover", {})[gc.name] = [bph.cur(gc), bph.give_back(gc, r.ev, "leftover " + gc.name)]


def ends(x, r):
    r.ev["cursors at end"] = {gc.name: bph.cur(gc) for gc in (x.host, x.client) if bpp.top(gc) == INV}


# ===================== spine =====================


def pick_pile(x):
    """PILE_TYPE by its preferred value, else test_base_partner_held's rule (the first type, by its lowest ground cell on the
    host, with a cell of >= 2 on both)."""
    m = {gc.name: bph.kinds(gc) for gc in (x.host, x.client)}
    ok = lambda t: all(any(n >= 2 for n in (m[g].get(t) or {}).values()) for g in m)  # noqa: E731
    x.pile = PILE_PIN if ok(PILE_PIN) else next((t for t in sorted(m["host"], key=lambda t: min(m["host"][t])) if ok(t)), None)
    x.pile_cell = {g: next((list(c) for c, n in sorted((m[g].get(x.pile) or {}).items()) if n >= 2), None) for g in m}
    return {"kinds": {g: {t: {f"{a},{b}": n for (a, b), n in v.items()} for t, v in m[g].items()} for g in m},
            "PILE_TYPE": [PILE_PIN, x.pile], "pileCell": x.pile_cell}


def spine(x):
    h, c, sp = x.host, x.client, {}
    for gc in (h, c):
        x.seats[gc.name] = q(gc, {"cmd": "get_coop"}).get("localSeat")
    t0 = time.time()
    session.wait_seq_barrier(h, c)  # settle before staging
    sp["settle barrier (s)"] = round(time.time() - t0, 2)
    sol = q(h, {"cmd": "base_report", "base": HB}).get("soldiers") or []
    g = next((s for s in sol if s.get("craft") == -1), sol[0] if sol else {})
    x.guest = g.get("name")
    sp["guest_move guest"] = [g.get("id"), x.guest, g.get("craft")]
    sp["guest_move transfer"] = q(h, {"cmd": "transfer_to_coop_base", "name": x.guest or "?", "toBase": CB})
    listed = lambda gc, req: any(s.get("name") == x.guest for s in q(gc, req).get("soldiers") or [])  # noqa: E731
    sp["guest_move client lists the guest"] = h20.converge(lambda: listed(c, {"cmd": "base_report", "base": CB}))
    sp["host_visit visit"] = q(h, {"cmd": "visit_coop_base", "base": CB})
    sp["host_visit inside"] = bpp.poll(lambda: q(h, {"cmd": "get_coop"}).get("insideCoopBase") is True, VISIT_S)
    sp["host_visit basescape"] = bpp.poll(lambda: bpp.top(h) == "BasescapeState", 30.0)
    sp["host_visit host lists the guest"] = h20.converge(lambda: listed(h, {"cmd": "base_report", "coop": True}))
    rep = {"owner": q(c, {"cmd": "base_report", "base": CB}), "visitor": q(h, {"cmd": "base_report", "coop": True})}
    sp["base ids"] = {k: [v.get("name"), v.get("coopBaseFlag"), v.get("coopBaseId"), v.get("totalSoldiers")] for k, v in rep.items()}
    sh = bpp.Shim()
    sp["owner_screen client open"] = open_soldier_screen(sh, c, base=CB)
    sp["visitor_screen host open"] = open_soldier_screen(sh, h, base=CB)
    sp["open fails"] = sh.fails
    sp["tops"] = {gc.name: stack(gc) for gc in (h, c)}
    sp["client dialog"] = {k: v for k, v in q(c, {"cmd": "coop_dialog_info"}).items() if k in ("present", "code", "title")}
    sp["units"] = {gc.name: bph.view(gc).get("unitId") for gc in (h, c)}
    sp["cursor"] = {gc.name: bpp.cpos(gc) for gc in (h, c)}
    sp["basePresence"] = {gc.name: bpp.bp(gc) for gc in (h, c)}
    sp["pins"] = pick_pile(x) if all(bpp.top(gc) == INV for gc in (h, c)) else None
    x.spine = {"seats": x.seats, "steps": sp}
    if not (all(bpp.top(gc) == INV for gc in (h, c)) and x.pile and None not in x.pile_cell.values()):
        raise RuntimeError(f"spine: {x.spine}")


# ===================== rows =====================


def row_both_pointers(x, r):
    h, c = x.host, x.client
    ready(x, r)
    for p, mover, obs, pt, name in (("host_pointer_on_client", h, c, PT1, HOST_NAME),
                                    ("client_pointer_on_host", c, h, PT2, CLIENT_NAME)):
        if not bpp.move(mover, pt, r.ev):
            r.cell(p, False, f"not reached (motion: {mover.name} to {list(pt)})")
            continue
        want = bpp.at(obs, pt)
        _, r.ev[p + " within"] = bpp.poll(lambda: drawn_at(obs, want, name), W_PTR)
        d = bpp.drawn(obs)
        r.ev[p + " drawn"] = {k: d.get(k) for k in ("ptr", "x", "y", "name", "nameShown", "nameX", "nameY")}
        r.ev[p + " keys"] = {gc.name: [key(gc), peer(gc).get("key")] for gc in (h, c)}
        r.cell(p, drawn_at(obs, want, name), f"{obs.name} draws {r.ev[p + ' drawn']} (want ptr true at {want} = its invX / invY + "
                                             f"{list(pt)}, name {name!r} shown at + ({NAME_DX}, {NAME_DY}) within {W_PTR} s of "
                                             f"{mover.name}'s motion; waited {r.ev[p + ' within']}); keys {r.ev[p + ' keys']}")
    ends(x, r)


def row_visitor_held_item(x, r):
    h, c = x.host, x.client
    ready(x, r)
    cc = x.pile_cell["client"]
    n0 = r.ev["clientCount0"] = bph.count(c, cc)
    r.ev["hostPick id"] = bph.lift(h, r.ev, "hostPick", x.pile, slot=GROUND, x=x.pile_cell["host"][0], y=x.pile_cell["host"][1])
    first = r.ev["first true (s)"] = bph.seen({"drop": lambda: bph.count(c, cc) == n0 - 1,
                                               "draw": lambda: bph.under(c, bph.local(c))}, W_PTR)
    r.ev["client held"], r.ev["clientCount"] = bph.show(c), bph.count(c, cc)
    r.cell("owner_pile_drops", first["drop"] is not None,
           f"the client's count at {cc} {n0} -> {r.ev['clientCount']} (want {n0 - 1} within "
           f"{W_PTR} s while the host holds {r.ev['hostPick id']}; first {first['drop']})")
    r.cell("owner_draws_held_item", first["draw"] is not None,
           f"the client draws {r.ev['client held']} (want its held.local, != -1, under the "
           f"host's pointer at (x - {bph.HALF[0]}, y - {bph.HALF[1]}) within {W_PTR} s)")
    bph.give_back(h, r.ev, "hostReturn")
    back = r.ev["back within (s)"] = bph.seen({"back": lambda: bph.count(c, cc) == n0}, W_PTR)["back"]
    r.ev["clientCount after"] = bph.count(c, cc)
    r.cell("owner_pile_back", first["drop"] is not None and back is not None,
           f"the client's count at {cc} {r.ev['clientCount after']} (want back to {n0} within {W_PTR} s of the host's right click, "
           f"after owner_pile_drops {'seen' if first['drop'] is not None else 'NOT seen'}; back {back})")
    ends(x, r)


def row_visitor_leaves(x, r):
    h, c, hs = x.host, x.client, x.seats.get("host")
    ready(x, r)
    b0 = bpp.bp(c)
    r.ev["client before"] = {"peer": b0.get("peer"), "recv": b0.get("recv"), "drawn": bpp.drawn(c).get("ptr")}

    def off():
        pe = peer(c)
        return (pe.get("state") == "base_equip_ptr" and pe.get("seat") == hs and pe.get("on") is False
                and bpp.num(bpp.bp(c), "recv") > bpp.num(b0, "recv"))
    hidden = lambda: bpp.drawn(c).get("ptr") is not True  # noqa: E731
    r.ev["ok click"] = bpp.click(h, "ok")
    if not h20.wait_until(lambda: INV not in stack(h), W, POLL):
        raise bph.Stop(f"precondition: the host's OK closes its screen ({stack(h)})")
    r.ev["after OK first true (s)"] = bph.seen({"off": off, "hidden": hidden}, W_PTR)
    r.ev["soldiers_ok"] = q(h, {"cmd": "soldiers_ok"}).get("ok")
    h20.wait_until(lambda: "SoldiersState" not in stack(h), W, POLL)
    r.ev["leave_base"] = q(h, {"cmd": "leave_base"})
    r.ev["back on geoscape"] = session.wait_back_on_geoscape(h, "the host back on its own geoscape")
    first = r.ev["first true (s)"] = bph.seen({"off": off, "hidden": hidden}, W_PTR)
    lk = r.ev["look"] = look(x)
    r.cell("leave_sends_pointer_off", first["off"] is not None,
           f"client peer {lk['client']['basePresence']['peer']} recv {b0.get('recv')} -> "
           f"{lk['client']['basePresence']['recv']} (want state base_equip_ptr, seat {hs}, on false, "
           f"a new receive, within {W_PTR} s of the host's return; first {first['off']})")
    r.cell("pointer_hidden_after_leave", first["hidden"] is not None,
           f"client drawn.ptr {lk['client']['drawn']['ptr']} (want false within {W_PTR} s; "
           f"first {first['hidden']})")
    r.ev["cursors at end"] = {"host": "left the base", "client": bph.cur(c)}


def row_different_bases(x, r):
    h, c = x.host, x.client
    if bpp.top(c) != INV or bpp.top(h) != GEO:
        raise bph.Stop(f"precondition: the client on ClientBase's inventory, the host on its geoscape ({stack(c)} / {stack(h)})")
    sh = bpp.Shim()
    if not open_soldier_screen(sh, h, base=HB):
        raise bph.Stop(f"precondition: the host's HostBase Soldiers inventory opens ({sh.fails})")
    if not bpp.move(h, PT1, r.ev):
        raise bph.Stop("precondition: the host's motion (CAPTURE motion above)")
    hk, ck = key(h), key(c)
    r.ev["localKey"] = {"host": hk, "client": ck}
    r.ev["host base"] = {k: q(h, {"cmd": "base_report", "base": HB}).get(k) for k in ("name", "coopBaseId")}
    drew = lambda: any(bpp.drawn(gc).get("ptr") is True for gc in (h, c))  # noqa: E731
    first = r.ev["first true (s)"] = bpp.watch({"key": lambda: hk != "" and peer(c).get("key") == hk, "drawn": drew}, W_PTR)
    lk = r.ev["look"] = look(x)
    r.cell("peer_key_is_host_key", first["key"] is not None and hk != ck,
           f"client peer.key {peer(c).get('key')!r} (want the host's localKey "
           f"{hk!r} within {W_PTR} s, first {first['key']}; non-empty and not the "
           f"client's {ck!r})")
    r.cell("no_pointer_drawn", first["drawn"] is None,
           f"a drawn pointer first at {first['drawn']} s (want none on either machine within "
           f"{W_PTR} s: different bases); drawn {[lk[n]['drawn']['ptr'] for n in ('host', 'client')]}")
    ends(x, r)


def row_crash_check(x, r):
    sh = bpp.Shim()
    for gc in (x.host, x.client):
        if bpp.top(gc) == INV:
            close_soldier_screen(sh, gc)
    r.ev["close fails"], r.ev["tops"] = sh.fails, {gc.name: stack(gc) for gc in (x.host, x.client)}
    crash = sorted(session._crash_log_snapshot() - x.crash0)
    up = {gc.name: bpp.alive(gc) for gc in (x.host, x.client)}
    r.ev.update(newCrashFiles=crash, alive=up)
    r.cell("no_new_crash_file", not crash and all(up.values()), f"new crash files {crash} (want none); alive {up} (want both)")


FNS = {"both_pointers": row_both_pointers, "visitor_held_item": row_visitor_held_item, "visitor_leaves": row_visitor_leaves,
       "different_bases": row_different_bases, "crash_check": row_crash_check}


def main(tag=TAG, lobby=LOBBY, extra=None):
    t0, results, walls = time.time(), {}, {}
    crash0 = session._crash_log_snapshot()
    h = GameClient("host", int(lobby), make_user_dir(tag + "_host"))
    c = GameClient("client", int(lobby), make_user_dir(tag + "_client"))
    x = X(h, c)
    x.crash0 = crash0
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=lobby)  # SEPARATE (campaign_mode "coop", the default)
            walls["ready"] = geo.wait_both_ready(h, c)
            spine(x)
            walls["spine"] = round(time.time() - t0, 1)
            print(f"EVIDENCE spine: {json.dumps(x.spine, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = x.spine
        except Exception as e:  # a spine miss fails every row "spine" with ONE CAPTURE line
            cap = {"error": h20.short(e, 4000)}
            for g in (h, c):
                cap[g.name] = {"stack": stack(g), "view": bph.view(g), "basePresence": bpp.bp(g),
                               "dialog": q(g, {"cmd": "coop_dialog_info"})}
            print(f"CAPTURE spine: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = cap
            for rid in ORDER:
                for cname in CELLS[rid]:
                    results[cname] = False
                    print(f"FAIL {cname}: spine", flush=True)
                print(f"ROW {rid}: FAIL spine", flush=True)
            return results, walls
        for rid in ORDER:
            r, t1 = Row(rid), time.time()
            try:
                FNS[rid](x, r)
            except Exception as e:
                r.why = h20.short(e, 900)
                r.ev["stopped"] = r.why
                r.ev["cleanup"] = {gc.name: bph.give_back(gc, r.ev, "cleanup " + gc.name) for gc in (h, c) if bpp.top(gc) == INV}
            walls[rid] = round(time.time() - t1, 1)
            r.report(results)
        if extra:
            extra(x)
    finally:
        shutdown_clients(h, c)
        walls["total"] = round(time.time() - t0, 1)
    return results, walls


if __name__ == "__main__":
    res, wl = main()
    allc = [cname for rid in ORDER for cname in CELLS[rid]]
    failed = [cname for cname in allc if not res.get(cname)]
    print(f"\ntest_base_visit_pointer: {len(allc) - len(failed)}/{len(allc)} cells passed (fail={failed}) "
          f"walls {json.dumps(wl)}", flush=True)
    sys.exit(2 if failed else 0)
