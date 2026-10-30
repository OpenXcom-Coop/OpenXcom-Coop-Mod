"""test_base_partner_pointer.py: the co-op partner's pointer and name on a SHARED base inventory screen. The partner's
pointer shows anywhere on the screen with its name beside it, only while both players are on the same pile. It travels
as a `base_equip_ptr {key, seat, x, y, on}` snapshot on the SNAP_EQUIP_PTR conflation slot (the pre-battle equip
pointer's): the raw position on the 320x200 Inventory surface, sent at a 50 ms rate, a 1 s keepalive, stale after
3 s, the name drawn at (+10, +4) from the pointer.
The boot (SHARED, key 49409, dirs base_partner_pointer_host / _client): shared_fixture.bring_up +
test_shared_base_equip's setup (its helpers imported, never edited); spine: both machines open HostBase's Soldiers
inventory (test_shared_base_equip's open_soldier_screen; the same pile on both).
Reads: drawn = event_state.equip.presence.drawn (the partner overlay's draw record, one per machine); counters, keys and
snapshots = event_state.equip.basePresence (screen, localKey, sent, recv, dropped, last, peer, peerAgeMs; absent = 0 /
false / "", as on a build without this feature); every `sent` / `recv` cell reads the row's delta; the inventory offset
(invX, invY) = the observer's cursor_pos.
move(gc, pt) = inject_input {kind motion} at ((invX + x) * SCALE, (invY + y) * SCALE), then cursor_pos until it reads
(invX + x, invY + y) within MOTION_S, re-injected once (a new state re-reads the OS mouse); else ONE CAPTURE line and the
row's cells are "not reached (motion)".
  client_pointer   move(client, PT1); poll the host up to W_PTR: client_pointer_drawn, client_pointer_pos (the host's
                   invX / invY + PT1), client_pointer_name (CLIENT_NAME, shown at the pointer + (10, 4))
  host_pointer     move(host, PT2); poll the client up to W_PTR: host_pointer_drawn, host_pointer_pos, host_pointer_name
                   (HOST_NAME)
  resting_pointer  no input for REST_S: keepalive_while_resting (the host still draws the client's pointer at the end;
                   the client's sent delta over the rest in [REST_S - 1, REST_S + 1]: the 1 s keepalive)
  client_ok        the client's real OK (inventory_click ok); W_PTR: ok_sends_pointer_off (the host's peer = the client's
                   explicit `on false`, a new receive), pointer_hidden_after_ok (guard: the host's drawn.ptr false); then
                   the client's soldiers_ok
  other_pile       the client opens SKY's Equipment inventory (test_shared_base_equip's open_craft_screen),
                   move(client, PT1); watch the host for W_PTR: peer_key_is_client_key (the host's peer.key = the client's
                   localKey, which differs from the host's), host_draws_nothing (guard: the host draws nothing
                   throughout), client_draws_nothing (guard: the client draws nothing of the host: the host's snapshot
                   names the Soldiers pile); then test_shared_base_equip's close_craft_screen
  geoscape_quiet   the host's real OK, soldiers_ok; both on the geoscape; QUIET_S after the host's last.on reads false:
                   nothing_sent_on_geoscape (guard: neither machine's sent grows, both last.on false)
  crash_check      no_new_crash_file (guard: no new crash file in this lane's crash folder, both games alive)
On a build without this feature, 9 of the 14 cells fail: client_pointer_drawn, client_pointer_pos, client_pointer_name,
host_pointer_drawn, host_pointer_pos, host_pointer_name, keepalive_while_resting, ok_sends_pointer_off,
peer_key_is_client_key; the 5 guards pass. With it, 14 / 14 pass. One EVIDENCE line per row, one PASS / FAIL line per
cell, then the row verdict; every row runs after a failure (a precondition miss ends its own row, its later cells "not
reached"); a spine miss fails every row "spine" with ONE CAPTURE line. Run in the foreground to completion. ONE run is
the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_base_partner_pointer.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_shared_base_equip as sbe  # noqa: E402  (main-guarded: setup, screens, q / stack)
from test_shared_base_equip import q, stack, open_soldier_screen, open_craft_screen, close_craft_screen  # noqa: E402

TAG, PORTS = "base_partner_pointer", (49409, 49409, 49409)  # the two labels are inert, the third is the lobby key
HB, GEO, INV = "HostBase", "GeoscapeState", "InventoryState"
PT1, PT2 = (150, 120), (60, 150)  # on the Inventory surface, on no widget of the base screens
SCALE = 2                         # the harness window / logical ratio (cursor_pos measured)
HOST_NAME, CLIENT_NAME = "HostPlayer", "ClientPlayer"  # the player names the SHARED boot gives, drawn beside the pointer
NAME_DX, NAME_DY = 10, 4          # the name's top-left from the pointer's tip
MOTION_S, W_PTR, REST_S, QUIET_S = 1.0, 2.0, 3.0, 2.0
POLL, SAMPLE_S, SCREEN_S = 0.05, 0.25, 30.0
CELLS = {
    "client_pointer": ["client_pointer_drawn", "client_pointer_pos", "client_pointer_name"],
    "host_pointer": ["host_pointer_drawn", "host_pointer_pos", "host_pointer_name"],
    "resting_pointer": ["keepalive_while_resting"],
    "client_ok": ["ok_sends_pointer_off", "pointer_hidden_after_ok"],
    "other_pile": ["peer_key_is_client_key", "host_draws_nothing", "client_draws_nothing"],
    "geoscape_quiet": ["nothing_sent_on_geoscape"],
    "crash_check": ["no_new_crash_file"],
}
ORDER = ["client_pointer", "host_pointer", "resting_pointer", "client_ok", "other_pile", "geoscape_quiet", "crash_check"]
EV = {}  # every row's EVIDENCE, by row id, plus the spine (kept for a caller of main)


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


class Shim:
    """test_shared_base_equip's open / close helpers record guard cells on a row; a row keeps their failures as evidence."""
    def __init__(self):
        self.fails = []

    def cell(self, name, ok, detail=""):
        if not ok:
            self.fails.append(f"{name}: {detail}")
        return bool(ok)


# ===================== probes =====================


def top(gc):
    return (stack(gc) or [""])[-1]


def equip(gc):
    return q(gc, {"cmd": "event_state"}).get("equip") or {}


def drawn(gc):
    """The partner overlay's draw record on gc (absent = {})."""
    return (equip(gc).get("presence") or {}).get("drawn") or {}


def bp(gc):
    """event_state.equip.basePresence on gc (absent = {}: reads 0 / false / "")."""
    return equip(gc).get("basePresence") or {}


def num(d, k):
    v = d.get(k)
    return v if isinstance(v, int) else 0


def cpos(gc):
    r = q(gc, {"cmd": "cursor_pos"})
    return {k: r.get(k) for k in ("x", "y", "invX", "invY", "error")}


def look(x):
    """EVIDENCE: each machine's top state, cursor_pos, equip presence object and basePresence object."""
    out = {}
    for gc in (x.host, x.client):
        e = equip(gc)
        out[gc.name] = {"top": top(gc), "cursor": cpos(gc), "presence": e.get("presence"), "basePresence": e.get("basePresence")}
    return out


def drawn_of(lk, name):
    return (lk[name]["presence"] or {}).get("drawn") or {}


def poll(pred, timeout):
    """(the predicate's last value, seconds waited) after at most `timeout`."""
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v, round(time.time() - t0, 3)
        time.sleep(POLL)


def watch(preds, timeout):
    """Sample every predicate each POLL for the WHOLE `timeout`: {name: seconds of its first true, None = never true}."""
    t0, first = time.time(), {k: None for k in preds}
    while True:
        el = round(time.time() - t0, 3)
        for k, f in preds.items():
            if first[k] is None and f():
                first[k] = el
        if el >= timeout:
            return first
        time.sleep(POLL)


def alive(gc):
    if gc.proc is None or gc.proc.poll() is not None:
        return False
    return bool(q(gc, {"cmd": "ping"}).get("pong"))


def click(gc, widget):
    r = q(gc, {"cmd": "inventory_click", "widget": widget})
    return r.get("error") or r.get("ok")


def at(gc, pt):
    """Where gc draws a partner pointer at pt: gc's own Inventory top-left (cursor_pos) + pt."""
    c = cpos(gc)
    return [(c.get("invX") or 0) + pt[0], (c.get("invY") or 0) + pt[1]]


def move(gc, pt, ev):
    """A real mouse motion to pt on gc's Inventory surface; True once cursor_pos reads it (one re-inject: a new state
    re-reads the OS mouse)."""
    c0 = cpos(gc)
    want = [(c0.get("invX") or 0) + pt[0], (c0.get("invY") or 0) + pt[1]]
    tries, got = [], False
    for _ in range(2):
        r = q(gc, {"cmd": "inject_input", "kind": "motion", "x": want[0] * SCALE, "y": want[1] * SCALE})
        got, dt = poll(lambda: (lambda c: [c.get("x"), c.get("y")] == want)(cpos(gc)), MOTION_S)
        tries.append({"inject": r.get("error") or r.get("ok"), "waited": dt, "cursor": cpos(gc)})
        if got:
            break
    got = bool(got) and None not in (c0.get("invX"), c0.get("invY")) and min(c0.get("invX"), c0.get("invY")) >= 0
    ev["move " + gc.name] = {"pt": list(pt), "want": want, "inv": [c0.get("invX"), c0.get("invY")], "tries": tries}
    if not got:
        cap = {"machine": gc.name, "want": want, "before": c0, "tries": tries, "stack": stack(gc)}
        print(f"CAPTURE motion: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    return got


def to_geo(gc, rec):
    """A row stopped early leaves no screen behind (recorded)."""
    if top(gc) != GEO:
        rec.append({gc.name: {"close_screens": q(gc, {"cmd": "close_screens"}), "before": stack(gc)}})
        poll(lambda: top(gc) == GEO, 5.0)


# ===================== spine =====================


def spine(x):
    h, c = x.host, x.client
    sbe.setup(x)
    x.coop = {gc.name: {k: v for k, v in q(gc, {"cmd": "get_coop"}).items() if k in ("localSeat", "clientName", "hostName", "peer")}
              for gc in (h, c)}
    sh = Shim()
    opened = {gc.name: open_soldier_screen(sh, gc) for gc in (h, c)}
    tops = {gc.name: top(gc) for gc in (h, c)}
    eq = {gc.name: equip(gc) for gc in (h, c)}
    x.spine = {"ids": x.ids, "names": {"H": x.H, "C": x.C, "C2": x.C2}, "sky": x.sky, "hbIndex": x.hb_index, "seats": x.seats,
               "coop": x.coop, "opened": opened, "tops": tops, "cursor": {gc.name: cpos(gc) for gc in (h, c)},
               "presence": {n: "presence" in e for n, e in eq.items()},
               "basePresence": {n: e.get("basePresence") for n, e in eq.items()}, "open fails": sh.fails}
    if not all(opened.values()) or any(t != INV for t in tops.values()):
        raise RuntimeError(f"spine: both HostBase Soldiers inventories on top: {x.spine}")


# ===================== rows =====================


def draw_row(x, r, mover, obs, pt, name, p):
    """client_pointer / host_pointer: mover's pointer at pt; the observer draws it at its own Inventory top-left + pt with
    the mover's name."""
    if not move(mover, pt, r.ev):
        r.why = "motion"
        return
    want = at(obs, pt)
    _, r.ev["within"] = poll(lambda: (lambda d: d.get("ptr") is True and [d.get("x"), d.get("y")] == want)(drawn(obs)), W_PTR)
    lk = r.ev["look"] = look(x)
    d = drawn_of(lk, obs.name)
    xy = [d.get("x"), d.get("y")]
    absent = "" if lk[obs.name]["basePresence"] is not None else f" ({obs.name} basePresence absent)"
    r.cell(f"{p}_drawn", d.get("ptr") is True,
           f"{obs.name} drawn.ptr {d.get('ptr')} (want true within {W_PTR} s of {mover.name}'s motion; waited {r.ev['within']})"
           + absent)
    r.cell(f"{p}_pos", d.get("ptr") is True and xy == want, f"{obs.name} drawn at {xy} (want {want} = its invX / invY + {list(pt)})"
           + absent)
    nxy = [d.get("nameX"), d.get("nameY")]
    r.cell(f"{p}_name", d.get("nameShown") is True and d.get("name") == name
           and nxy == [(d.get("x") or 0) + NAME_DX, (d.get("y") or 0) + NAME_DY],
           f"{obs.name} name {d.get('name')!r} shown {d.get('nameShown')} at {nxy} (want {name!r} shown at the pointer + "
           f"({NAME_DX}, {NAME_DY}))" + absent)


def row_client_pointer(x, r):
    draw_row(x, r, x.client, x.host, PT1, CLIENT_NAME, "client_pointer")


def row_host_pointer(x, r):
    draw_row(x, r, x.host, x.client, PT2, HOST_NAME, "host_pointer")


def row_resting_pointer(x, r):
    h, c = x.host, x.client
    s0, samples, t0 = num(bp(c), "sent"), [], time.time()
    while time.time() - t0 < REST_S:
        samples.append(drawn(h).get("ptr"))
        time.sleep(SAMPLE_S)
    r.ev["restS"] = round(time.time() - t0, 2)
    s1 = num(bp(c), "sent")
    lk = r.ev["look"] = look(x)
    end = drawn_of(lk, "host").get("ptr")
    r.ev.update(clientSent=[s0, s1], hostDrawnSamples=samples)
    r.cell("keepalive_while_resting", end is True and REST_S - 1 <= s1 - s0 <= REST_S + 1,
           f"host drawn.ptr {end} at the end of the {r.ev['restS']} s rest (want true; samples true "
           f"{sum(1 for v in samples if v is True)} of {len(samples)}); client sent {s0} -> {s1} (want +{REST_S - 1:g} .. "
           f"+{REST_S + 1:g}: the 1 s keepalive)")


def row_client_ok(x, r):
    h, c, cs = x.host, x.client, x.seats.get("client")
    b0 = bp(h)
    r.ev["host before"] = {"peer": b0.get("peer"), "recv": b0.get("recv"), "drawn": drawn(h)}
    r.ev["ok click"] = click(c, "ok")

    def off():
        pe = bp(h).get("peer") or {}
        return pe.get("state") == "base_equip_ptr" and pe.get("seat") == cs and pe.get("on") is False
    first = watch({"off": off, "hidden": lambda: drawn(h).get("ptr") is not True,
                   "closed": lambda: INV not in stack(c)}, W_PTR)
    r.ev["first true (s)"] = first
    lk = r.ev["look"] = look(x)
    b1 = lk["host"]["basePresence"] or {}
    if first["closed"] is None:
        r.why = f"precondition: the client's OK did not close its screen within {W_PTR} s ({stack(c)})"
        return
    r.cell("ok_sends_pointer_off", first["off"] is not None and off() and num(b1, "recv") > num(b0, "recv"),
           f"host peer {b1.get('peer')} (want state base_equip_ptr, seat {cs}, on false within {W_PTR} s of the client's OK; "
           f"first {first['off']}); host recv {b0.get('recv')} -> {b1.get('recv')} (want a new receive)")
    r.cell("pointer_hidden_after_ok", first["hidden"] is not None and drawn_of(lk, "host").get("ptr") is not True,
           f"host drawn.ptr {drawn_of(lk, 'host').get('ptr')} (want false within {W_PTR} s; first {first['hidden']})")
    r.ev["soldiers_ok"] = q(c, {"cmd": "soldiers_ok"}).get("ok")
    r.ev["client at geoscape"] = poll(lambda: top(c) == GEO, SCREEN_S)


def row_other_pile(x, r):
    h, c = x.host, x.client
    to_geo(c, r.ev.setdefault("cleanup before", []))
    sh = Shim()
    if not open_craft_screen(sh, x, c):
        r.why, r.ev["open"] = "precondition: the client's SKY Equipment inventory did not open", sh.fails
        return
    try:
        if not move(c, PT1, r.ev):
            r.why = "motion"
            return
        ck, hk = bp(c).get("localKey") or "", bp(h).get("localKey") or ""
        r.ev["localKey"] = {"client": ck, "host": hk}
        first = watch({"key": lambda: ck != "" and (bp(h).get("peer") or {}).get("key") == ck,
                       "hostDrawn": lambda: drawn(h).get("ptr") is True}, W_PTR)
        r.ev["first true (s)"] = first
        lk = r.ev["look"] = look(x)
        cd = drawn_of(lk, "client")
        r.cell("peer_key_is_client_key", first["key"] is not None and ck != hk,
               f"host peer.key {((lk['host']['basePresence'] or {}).get('peer') or {}).get('key')!r} (want the client's localKey "
               f"{ck!r} within {W_PTR} s, first {first['key']}; non-empty and not the host's {hk!r})")
        r.cell("host_draws_nothing", first["hostDrawn"] is None,
               f"host drawn.ptr first true at {first['hostDrawn']} s (want never within {W_PTR} s: another pile)")
        r.cell("client_draws_nothing", cd.get("ptr") is not True,
               f"client drawn.ptr {cd.get('ptr')} at the end of {W_PTR} s (want false: the host's snapshot names its Soldiers pile)")
    finally:
        close_craft_screen(sh, c)
        r.ev["close fails"] = sh.fails
        poll(lambda: top(c) == GEO, 10.0)


def row_geoscape_quiet(x, r):
    h, c = x.host, x.client
    if top(h) != INV:
        r.why = f"precondition: the host's Soldiers inventory is not on top ({stack(h)})"
        return
    r.ev["ok click"] = click(h, "ok")
    poll(lambda: INV not in stack(h), 10.0)
    r.ev["soldiers_ok"] = q(h, {"cmd": "soldiers_ok"}).get("ok")
    geo, r.ev["geoWithin"] = poll(lambda: top(h) == GEO and top(c) == GEO, SCREEN_S)
    if not geo:
        r.why = f"precondition: both on the geoscape ({stack(h)} / {stack(c)})"
        return
    _, r.ev["hostOffWithin"] = poll(lambda: (bp(h).get("last") or {}).get("on") is not True, W_PTR)
    s0 = {gc.name: num(bp(gc), "sent") for gc in (h, c)}
    time.sleep(QUIET_S)
    lk = r.ev["look"] = look(x)
    s1 = {n: num(lk[n]["basePresence"] or {}, "sent") for n in ("host", "client")}
    last = {n: ((lk[n]["basePresence"] or {}).get("last") or {}).get("on") for n in ("host", "client")}
    r.ev.update(sent=[s0, s1], lastOn=last)
    r.cell("nothing_sent_on_geoscape", s1 == s0 and not any(v is True for v in last.values()),
           f"sent {s0} -> {s1} over {QUIET_S} s on the geoscape (want unchanged); last.on {last} (want false / absent on both)")


def row_crash_check(x, r):
    crash = sorted(session._crash_log_snapshot() - x.crash0)
    up = {gc.name: alive(gc) for gc in (x.host, x.client)}
    r.ev.update(newCrashFiles=crash, alive=up, tops={gc.name: stack(gc) for gc in (x.host, x.client)})
    r.cell("no_new_crash_file", not crash and all(up.values()), f"new crash files {crash} (want none); alive {up} (want both)")


FNS = {"client_pointer": row_client_pointer, "host_pointer": row_host_pointer, "resting_pointer": row_resting_pointer,
       "client_ok": row_client_ok, "other_pile": row_other_pile, "geoscape_quiet": row_geoscape_quiet,
       "crash_check": row_crash_check}


def main(tag=TAG, ports=PORTS, extra=None):
    t0, results, walls, js, x = time.time(), {}, {}, None, None
    crash0 = session._crash_log_snapshot()
    try:
        try:
            js = shared_fixture.bring_up(tag, ports)
            x = sbe.X(js.host, js.client, js)
            x.crash0 = crash0
            spine(x)
            walls["spine"] = round(time.time() - t0, 1)
            print(f"EVIDENCE spine: {json.dumps(x.spine, sort_keys=True, default=str)}", flush=True)
            EV["spine"] = x.spine
        except Exception as e:  # a spine miss fails every row "spine" with ONE CAPTURE line
            cap = {"error": sbe.short(e, 3000)}
            if x is not None:
                for g in (x.host, x.client):
                    cap[f"{g.name} stack"] = stack(g)
                    cap[f"{g.name} cursor_pos"] = cpos(g)
                    cap[f"{g.name} basePresence"] = equip(g).get("basePresence")
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
                r.why = sbe.short(e)
                r.ev["exception"] = sbe.short(e)
            walls[rid] = round(time.time() - t1, 1)
            r.report(results)
        if extra:
            extra(x)
    finally:
        if js is not None:
            js.shutdown()
        walls["total"] = round(time.time() - t0, 1)
    return results, walls


if __name__ == "__main__":
    res, wl = main()
    allc = [cname for rid in ORDER for cname in CELLS[rid]]
    failed = [cname for cname in allc if not res.get(cname)]
    print(f"\ntest_base_partner_pointer: {len(allc) - len(failed)}/{len(allc)} cells passed (fail={failed}) "
          f"walls {json.dumps(wl)}", flush=True)
    sys.exit(2 if failed else 0)
