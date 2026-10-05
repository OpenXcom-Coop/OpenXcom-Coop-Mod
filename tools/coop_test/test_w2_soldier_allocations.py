"""W2-H16b (S-9..S-11; D226 a; spec rewrite/prompts/w2h16b_soldier_allocations.md (f) + A1.5; TASK 0 rewrite/w2h16b-task0):
crew seats from the crew-armor ctrl-click and the crew keys, and martial / psi allocations made on one machine reach the shared
world; the training screens and the crew keys touch only the clicker's own soldiers (AUD-A48). Mod Coop_Allocation_Test: ONE
gym place + ONE psi-lab place at (0, 3), index 9 (F6668). Boot A (SHARED): H16b-1..7, 9, 10, 11; Boot B (SEPARATE): H16b-8.
S0 = flags off, wounds healed, seats via the craft_assign lever, both equal, requests R0; clicks at the alloc_screen_probe
row centre (ctrl: mod ctrl then modstate none, F6180); keys z 122 / x 120; poll = both machines' flags + seats every 0.25 s
for 3 s, cells at its end; close = OK until GeoscapeState, requests == R0 (STOP-IF 5). RED: all rows but H16b-8 fail on
their named cells; GREEN: all pass. "G:" = guard (red and green; a miss prints one CAPTURE). ONE run; exit 0 iff all pass.
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

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Allocation_Test")
BOOT_A, BOOT_B = ("w2h16ba", (49320, 49321, 47300)), ("w2h16bb", (49322, 49323), "47302")
FAC, FAC_IDX, KEY_Z, KEY_X = "STR_H16B_TRAINING", 9, 122, 120     # TASK 0 F6668; Options.cpp :528-534
POLL_S, POLL_I, GEO, POP, H, C = 3.0, 0.25, "GeoscapeState", "CoopState", "host", "client"
SCREEN = {"martial": "AllocateTrainingState", "psi": "AllocatePsiTrainingState",
          "craft_armor": "CraftArmorState", "craft_soldiers": "CraftSoldiersState"}
PERSONAL, NONE = "STR_PERSONAL_ARMOR_UC", "STR_NONE_UC"
SS_KEYS = ("cmd", "okCount", "failCount", "applyCount", "unknownCount", "lastFail")
OWN = "the %s screen lists the partner's soldiers (AUD-A48): %d rows, listing %s"

short = lambda e, n=600: (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E731
stack = session.states_stripped
top = lambda gc: (stack(gc) or [""])[-1]  # noqa: E731
ss = lambda gc: {k: v for k, v in gc.cmd({"cmd": "shared_stats"}).items() if k in SS_KEYS}  # noqa: E731
req = lambda gc: gc.cmd({"cmd": "shared_resync_stats"}).get("requests")  # noqa: E731
aprobe = lambda gc: gc.cmd({"cmd": "alloc_screen_probe"})  # noqa: E731
ids_of = lambda p: [w.get("soldierId") for w in (p or {}).get("rows", [])]  # noqa: E731
status_of = lambda p, sid: next((w.get("status") for w in (p or {}).get("rows", []) if w.get("soldierId") == sid), None)  # noqa
record = lambda gc, sid: (gc.cmd({"cmd": "soldier_record", "id": sid}).get("records") or [{}])[0]  # noqa: E731
craft = lambda gc, sid: record(gc, sid).get("craftId")  # noqa: E731
crafts = lambda gc: {s["id"]: s.get("craft") for s in gc.ok({"cmd": "base_report"})["soldiers"]}  # noqa: E731
store = lambda gc: gc.ok({"cmd": "base_report"}).get("storage", {}).get("STR_PERSONAL_ARMOR", 0)  # noqa: E731
free_gym = lambda gc: gc.ok({"cmd": "soldier_training_probe", "ids": []})["bases"][0]["freeTraining"]  # noqa: E731
lever = lambda gc, sid, **kv: gc.ok(dict({"cmd": "set_soldier_training", "soldierId": sid}, **kv))  # noqa: E731
listing = lambda p, ids: ids_of(p) == ids and p.get("listing") == "own"  # noqa: E731
pong = lambda *gcs: all(gc.cmd({"cmd": "ping"}).get("pong") for gc in gcs)  # noqa: E731
class Miss(Exception):  # a blocking guard missed: the row stops
    pass
def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout and not pred():
        time.sleep(interval)
    return pred()
def flags(gc, ids):
    """soldier_training_probe of `ids`: {id: {tr, rtwh, psi, rec, psiSkill}} (None: not found)."""
    return {s["id"]: ({"tr": s["training"], "rtwh": s["rtwh"], "psi": s["psiTraining"], "rec": s["recovery"],
                       "psiSkill": s["stats"]["psiSkill"]} if s.get("found") else None)
            for s in gc.ok({"cmd": "soldier_training_probe", "ids": list(ids)})["soldiers"]}
def snap(gc, ids):
    return {i: dict(v, craft=craft(gc, i)) for i, v in flags(gc, ids).items()}
def armor(gc, ids):
    every = [s for b in gc.ok({"cmd": "get_soldiers"}).get("bases", []) for s in b.get("soldiers", [])]
    return {i: next((s.get("armor") for s in every if s["id"] == i), None) for i in ids}
def capture(tag, x, ids, why):
    cap = {}
    for gc in (x.host, x.client):
        try:
            rec = {i: {k: record(gc, i).get(k) for k in ("craftId", "owner", "recovery", "armor")} for i in ids}
            cap[gc.name] = {"soldier_training_probe": gc.cmd({"cmd": "soldier_training_probe", "ids": list(ids)}), "soldier_record": rec,
                            "alloc_screen_probe": aprobe(gc), "shared_stats": ss(gc), "stack": stack(gc)}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
class Row:
    def __init__(self, rid, x, ids):
        self.rid, self.x, self.ids, self.ev, self.fails, self.passed = rid, x, ids, {}, [], []
        self.R0, self.popups, self.captured = {}, [], False
    def cell(self, name, ok, detail=""):
        (self.passed if ok else self.fails).append(name if ok else f"{name}: {detail}")
        if not ok and name.startswith("G:") and not self.captured:   # FIXTURE-STOP dump (STOP-IF 3)
            self.captured = True
            capture(self.rid, self.x, self.ids, name)
        return ok
    def need(self, name, ok, detail=""):
        if not self.cell(name, ok, detail):
            raise Miss(name)
    def report(self, results):
        self.ev["cellsPassed"] = self.passed
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else
              f"FAIL {self.rid}: {len(self.fails)} cell(s): " + " | ".join(self.fails), flush=True)
def seat_to(x, want, timeout=6.0):
    """Seats {id: 1 | -1} by the craft_assign lever (S-8 path), sent from a machine whose OWN seat differs (host first)."""
    h, c = x.host, x.client
    ch, cc = crafts(h), crafts(c)
    for i, w in want.items():
        gc = h if ch.get(i) != w else (c if cc.get(i) != w else None)
        if gc is not None:
            gc.ok({"cmd": "craft_assign", "soldier_id": i, "craft_id": 1, "on": w == 1})
    both = lambda a, b: all(a.get(i) == w and b.get(i) == w for i, w in want.items())  # noqa: E731
    return wait_until(lambda: both(crafts(h), crafts(c)), timeout, 0.2)
def stage(x, r, tag, want):
    """set_soldier_training {id: {field: value}} on the client, then the host (S25); G: both machines hold it."""
    for gc in (x.client, x.host):
        for i, kv in want.items():
            lever(gc, i, **kv)
    f = r.ev[tag] = {gc.name: flags(gc, list(want)) for gc in (x.host, x.client)}
    k = {"training": "tr", "rtwh": "rtwh", "psiTraining": "psi", "psiSkill": "psiSkill"}
    bad = [(n, i, f2) for n in f for i, kv in want.items() for f2, v in kv.items() if f[n][i][k[f2]] != v]
    r.need(f"G:{tag} staged", not bad, f"(machine, id, field) {bad}")
def s0(x, r, seats=None, extra=None, tag="S0"):
    h, c = x.host, x.client
    want = {i: dict({"training": False, "rtwh": False, "psiTraining": False}, **(extra or {}).get(i, {})) for i in x.ids}
    for gc in (c, h):
        for i in x.ids:
            lever(gc, i, **want[i])
        for i in sorted(x.wounded):
            gc.ok({"cmd": "set_soldier_recovery", "soldierId": i, "days": 0})
    x.wounded.clear()
    seats = seats or {i: 1 for i in x.ids}
    seated = seat_to(x, seats)
    f, k = {gc.name: flags(gc, x.ids) for gc in (h, c)}, {gc.name: crafts(gc) for gc in (h, c)}
    r.ev[tag] = {"flags": f, "crafts": k}
    r.need(f"G:{tag} equal", seated and f[H] == f[C] and k[H] == k[C] and all(k[H][i] == w for i, w in seats.items()),
           f"seated {seated} flags {f} crafts {k}")
    r.R0 = {gc.name: req(gc) for gc in (h, c)}
def open_screen(gc, r, kind, tag):
    gc.ok({"cmd": "open_alloc_screen", "kind": kind} if kind in ("martial", "psi") else
          {"cmd": "open_screen", "screen": kind, "craft_id": 1})
    r.need(f"G:{tag} {gc.name} {SCREEN[kind]}", wait_until(lambda: top(gc) == SCREEN[kind], 3.0), stack(gc))
    p = wait_until(lambda: (lambda q: q if q.get("rows") or q.get("error") else None)(aprobe(gc)), 2.0) or aprobe(gc)
    r.need(f"G:{tag} {gc.name} probe", p.get("ok") and p.get("kind") == kind and p.get("rows"), p)   # STOP-IF 9
    r.ev[f"{tag} {gc.name} open [listing, [row, id, status]]"] = [
        p.get("listing"), [[w.get("row"), w.get("soldierId"), w.get("status")] for w in p["rows"]]]
    return p
def click(gc, r, sid, tag, ctrl=False):
    p = aprobe(gc)
    row = [w for w in p.get("rows", []) if w.get("soldierId") == sid]
    r.need(f"G:{tag} {gc.name} row of {sid}", row and "wx" in row[0], p)
    gc.ok(dict({"cmd": "inject_input", "kind": "click", "x": row[0]["wx"], "y": row[0]["wy"]}, **({"mod": "ctrl"} if ctrl else {})))
    if ctrl:
        gc.ok({"cmd": "inject_input", "kind": "modstate", "mod": "none"})
    r.ev[f"{tag} {gc.name} click {sid} [row, wx, wy, ctrl]"] = [row[0]["row"], row[0]["wx"], row[0]["wy"], ctrl]
def close(x, r, gc, tag):
    for _ in range(4):
        t = top(gc)
        if t == GEO:
            break
        if t == POP:
            r.popups.append([tag, gc.name, gc.cmd({"cmd": "screen_state"}).get("title")])
        gc.cmd({"cmd": "coop_dialog_back"} if t == POP else {"cmd": "click_widget", "match": "OK"})
        wait_until(lambda: top(gc) != t, 1.0)
    r.need(f"G:{tag} {gc.name} closed", wait_until(lambda: top(gc) == GEO, 3.0), stack(gc))
    now = {m.name: req(m) for m in (x.host, x.client)}
    r.need(f"G:{tag} requests", now == r.R0, f"requests {now} vs R0 {r.R0} (STOP-IF 5)")
def step(x, r, tag, gc, ids, kind=None, sid=None, sym=None, ctrl=False, done=True):
    """[Open `kind` on gc;] click `sid` (ctrl) or press `sym`; poll `ids` 3 s; e[H] / e[C] = the poll end, e["top"] /
    e["rows"] = gc's top state and rows [id, status] there; close the opened screen when `done`. Returns (open probe, e)."""
    p = open_screen(gc, r, kind, tag) if kind else None
    if sid is not None:
        click(gc, r, sid, tag, ctrl)
    if sym is not None:
        gc.ok({"cmd": "inject_input", "kind": "key", "key": sym})
    t0, n = time.time(), 0
    while True:
        e, n = {"t": round(time.time() - t0, 2), H: snap(x.host, ids), C: snap(x.client, ids)}, n + 1
        if e["t"] >= POLL_S:
            break
        time.sleep(POLL_I)
    e["samples"], e["top"] = n, top(gc)
    e["rows"] = [[w.get("soldierId"), w.get("status")] for w in aprobe(gc).get("rows", [])]
    r.ev[f"{tag} poll end ({gc.name})"] = e
    if done and kind:
        close(x, r, gc, tag)
    return p, e
def row_1(x, r):   # crew-armor ctrl-click OFF (client)
    h, c, C1 = x.host, x.client, x.C1
    s0(x, r)
    a0 = ss(h)["applyCount"]
    p, e = step(x, r, "ctrl", c, [C1], "craft_armor", sid=C1, ctrl=True, done=False)
    st, da = next((s for i, s in e["rows"] if i == C1), None), ss(h)["applyCount"] - a0
    r.ev["client C1 status, host applyCount delta"] = [st, da]
    r.cell("G:rows own", ids_of(p) == x.C, ids_of(p))
    r.cell("G:ctrl seen, client seat, cell", [e["top"], e[C][C1]["craft"], st] == [SCREEN["craft_armor"], -1, "NONE"],
           [e["top"], e[C][C1], st])
    r.cell("seat", [e[H][C1]["craft"], da] == [-1, 1], "the client's crew-armor seat stayed on its machine (S-9a): "
           f"host C1 craft {e[H][C1]['craft']}, host applyCount +{da}")
    close(x, r, c, "ctrl")
def row_2(x, r):   # crew-armor ctrl-click ON (client), OFF (host)
    h, c, C1, H1 = x.host, x.client, x.C1, x.H1
    s0(x, r, seats={i: (-1 if i == C1 else 1) for i in x.ids})
    _p, e = step(x, r, "(1)", c, [C1], "craft_armor", sid=C1, ctrl=True)
    r.cell("G:(1) client seat", e[C][C1]["craft"] == 1, e[C][C1])
    r.cell("(1)", e[H][C1]["craft"] == 1, f"the client's crew-armor seat stayed on its machine (S-9a): host C1 craft {e[H][C1]['craft']}")
    p, e = step(x, r, "(2)", h, [H1], "craft_armor", sid=H1, ctrl=True)
    r.cell("G:(2) host rows own, host seat", [ids_of(p), e[H][H1]["craft"]] == [x.H, -1], [ids_of(p), e[H][H1]])
    r.cell("(2)", e[C][H1]["craft"] == -1, f"the host's crew-armor seat stayed on its machine (S-9a): client H1 craft {e[C][H1]['craft']}")
def row_3(x, r):   # crew hotkeys z / x (client); crew C1, C2 only (roster positions < 4, F6169)
    c, keep = x.client, [x.C1, x.C2]
    s0(x, r, seats={i: (1 if i in keep else -1) for i in x.ids})
    pos = {i: x.ids.index(i) for i in keep}
    r.cell("G:roster positions", all(v < min(len(x.C), len(x.H)) for v in pos.values()), pos)
    open_screen(c, r, "craft_soldiers", "open")
    for name, sym, site in (("z", KEY_Z, "S-9c"), ("x", KEY_X, "S-9b")):
        if name == "x":
            r.need("G:restage", seat_to(x, {i: 1 for i in keep}), "C1, C2 back on craft 1")
        _p, e = step(x, r, name, c, keep, sym=sym)
        r.cell(f"G:{name} client seats, alive", all(e[C][i]["craft"] == -1 for i in keep) and pong(c)
               and e["top"] == SCREEN["craft_soldiers"], [e[C], e["top"]])
        r.cell(name, all(e[H][i]["craft"] == -1 for i in keep),
               f"the crew hotkey stayed local ({site}): host C1, C2 craft {[e[H][i]['craft'] for i in keep]}")
    close(x, r, c, "close")
def row_4(x, r):   # martial click, own rows, both directions (A1.5 H16b-4')
    h, c, C1, H1 = x.host, x.client, x.C1, x.H1
    s0(x, r)
    p, e = step(x, r, "(1)", c, [C1], "martial", sid=C1)
    r.cell("(0) client rows", listing(p, x.C), OWN % ("martial", len(ids_of(p)), p.get("listing")))
    r.cell("G:(1) client C1", e[C][C1]["tr"] is True, e[C][C1])
    r.cell("(1)", e[H][C1]["tr"] is True, f"the client's martial click stayed on its machine (S-10a): host C1 training {e[H][C1]['tr']}")
    stage(x, r, "(2) restage", {C1: {"training": False}, H1: {"training": True}})
    p, e = step(x, r, "(2)", h, [H1], "martial", sid=H1)
    r.cell("(0b) host rows", listing(p, x.H), OWN % ("martial", len(ids_of(p)), p.get("listing")))
    r.cell("G:(2) host H1", e[H][H1]["tr"] is False, e[H][H1])
    r.cell("(2)", e[C][H1]["tr"] is False, f"the host's martial click stayed on its machine (S-10a): client H1 training {e[C][H1]['tr']}")
def row_5(x, r):   # the last gym place, both at once (the client's applies held)
    h, c, C1, H1 = x.host, x.client, x.C1, x.H1
    s0(x, r)
    open_screen(c, r, "martial", "open")
    try:
        r.need("G:defer on", c.ok({"cmd": "shared_update_defer", "on": True}).get("deferred") is True)
        open_screen(h, r, "martial", "open")
        a0 = ss(h)["applyCount"]
        click(h, r, H1, "host")
        r.cell("G:host H1", wait_until(lambda: flags(h, [H1])[H1]["tr"], 1.0), flags(h, [H1]))
        wait_until(lambda: ss(h)["applyCount"] > a0, 1.0)   # green: the host's own apply lands before the client's click
        da, r.ev["client freeTraining before its click (stale world)"] = ss(h)["applyCount"] - a0, free_gym(c)
        click(c, r, C1, "client")
        r.cell("G:stale click", wait_until(lambda: flags(c, [C1])[C1]["tr"], 1.0), flags(c, [C1]))
        time.sleep(1.0)
    finally:
        c.cmd({"cmd": "shared_update_defer", "on": False})
    _p, e = step(x, r, "poll", c, [C1, H1])
    free, v = {gc.name: free_gym(gc) for gc in (h, c)}, {m: [e[m][H1]["tr"], e[m][C1]["tr"]] for m in (H, C)}
    r.ev["[H1, C1] training, freeTraining, host applyCount delta after its click"] = [v, free, da]
    r.cell("race", all(w == [True, False] for w in v.values()) and all(f == 0 for f in free.values()) and da == 1,
           f"two trainees in a one-place gym; the worlds disagree: [H1, C1] training {v}, freeTraining {free}, host applyCount +{da}")
    close(x, r, c, "close")
    close(x, r, h, "close")
def row_6(x, r):   # queue when healed + the add-all key, own soldiers only (A1.5 H16b-6')
    h, c, C1, C2, H1 = x.host, x.client, x.C1, x.C2, x.H1
    s0(x, r)
    for gc in (c, h):
        for i in (C2, H1):
            gc.ok({"cmd": "set_soldier_recovery", "soldierId": i, "days": 5})
    x.wounded.update({C2, H1})
    w = {gc.name: {i: v["rec"] for i, v in flags(gc, [C2, H1]).items()} for gc in (h, c)}
    r.need("G:wounded", all(v == 5 for m in w.values() for v in m.values()), w)
    p, e = step(x, r, "(1)", c, [C2], "martial", sid=C2, done=False)
    r.cell("G:C2 status", status_of(p, C2) != status_of(p, C1), [status_of(p, C1), status_of(p, C2)])
    r.cell("G:(1) client C2 rtwh", e[C][C2]["rtwh"] is True, e[C][C2])
    r.cell("(1)", e[H][C2]["rtwh"] is True, f"the client's queue click stayed on its machine (S-10a): host C2 rtwh {e[H][C2]['rtwh']}")
    stage(x, r, "(2) restage", {C2: {"training": False, "rtwh": False, "psiTraining": False}})
    _p, e = step(x, r, "(2)", c, [C1, C2, H1], sym=KEY_Z)
    v, q = {m: [e[m][C1]["tr"], e[m][C2]["rtwh"]] for m in (H, C)}, [e[C][H1]["rtwh"], e[H][H1]["rtwh"]]
    r.cell("G:(2) client C1 training, C2 rtwh", v[C] == [True, True], v[C])
    r.cell("(2)", v[H] == [True, True], f"the client's add-all key stayed on its machine (S-10c): host [C1 training, C2 rtwh] {v[H]}")
    r.cell("(3)", q == [False, False], f"the client's add-all key queued the partner's soldier (AUD-A48): H1 rtwh [client, host] {q}")
    close(x, r, c, "close")
def row_7(x, r):   # psi: own rows, click, remove-all, the open-screen clean-up (A1.5 H16b-7')
    h, c, C1, C2, H1, H2 = x.host, x.client, x.C1, x.C2, x.H1, x.H2
    s0(x, r)
    p, e = step(x, r, "(1)", c, [C1], "psi", sid=C1)
    r.cell("(0) client rows", listing(p, x.C), OWN % ("psi", len(ids_of(p)), p.get("listing")))
    r.cell("G:(1) client C1", e[C][C1]["psi"] is True, e[C][C1])
    r.cell("(1)", e[H][C1]["psi"] is True, f"the client's psi click stayed on its machine (S-11a): host C1 psiTraining {e[H][C1]['psi']}")
    stage(x, r, "(2) restage", {C1: {"psiTraining": True}})
    _p, e = step(x, r, "(2)", h, [C1], "psi", sym=KEY_X)
    v = [e[H][C1]["psi"], e[C][C1]["psi"]]
    r.cell("(2)", v == [True, True], f"the host's remove-all key took the partner's soldier out (AUD-A48): C1 psiTraining [host, client] {v}")
    s0(x, r, extra={H1: {"psiTraining": True}}, tag="(3) S0")
    _p, e = step(x, r, "(3)", h, [H1], "psi", sym=KEY_X)
    r.cell("G:(3) host H1", e[H][H1]["psi"] is False, e[H][H1])
    r.cell("(3)", e[C][H1]["psi"] is False, f"the host's remove-all key stayed on its machine (S-11b): client H1 psiTraining {e[C][H1]['psi']}")
    s0(x, r, extra={C2: {"psiTraining": True, "psiSkill": 100}}, tag="(4) S0")
    _p, e = step(x, r, "(4)", c, [C2], "psi")
    r.cell("G:(4) client C2 cleared", e[C][C2]["psi"] is False, e[C][C2])
    r.cell("(4)", e[H][C2]["psi"] is False,
           f"the client's open-screen clean-up stayed on its machine (S-11c): host C2 psiTraining {e[H][C2]['psi']}")
    s0(x, r, extra={H2: {"psiTraining": True, "psiSkill": 100}}, tag="(5) S0")
    _p, e = step(x, r, "(5)", c, [H2], "psi")
    v = [e[C][H2]["psi"], e[H][H2]["psi"]]
    r.cell("(5)", v == [True, True], f"the client's psi screen cleared the partner's soldier (AUD-A48): H2 psiTraining [client, host] {v}")
def row_9(x, r):   # the crew keys keep the partner's soldier seated (C1, H1 at roster positions < 4, F6169)
    h, c, C1, H1, keep = x.host, x.client, x.C1, x.H1, [x.C1, x.H1]
    s0(x, r, seats={i: (1 if i in keep else -1) for i in x.ids})
    pos = {i: x.ids.index(i) for i in keep}
    r.cell("G:roster positions", all(v < min(len(x.C), len(x.H)) for v in pos.values()), pos)
    _p, e = step(x, r, "z", c, keep, "craft_soldiers", sym=KEY_Z)
    r.cell("G:z client C1, alive", e[C][C1]["craft"] == -1 and pong(c), e[C][C1])
    v = [e[C][H1]["craft"], e[H][H1]["craft"]]
    r.cell("(z) partner", v == [1, 1], f"the client's crew key unseated the partner's soldier (AUD-A48): H1 craft [client, host] {v}")
    r.cell("(z) host", e[H][C1]["craft"] == -1, f"the client's crew key stayed on its machine (S-9c): host C1 craft {e[H][C1]['craft']}")
    r.need("G:restage", seat_to(x, {C1: 1, H1: 1}), "C1, H1 back on craft 1")
    _p, e = step(x, r, "x", h, keep, "craft_soldiers", sym=KEY_X)
    r.cell("G:x host H1, alive", e[H][H1]["craft"] == -1 and pong(h, c), e[H][H1])
    v = [e[H][C1]["craft"], e[C][C1]["craft"]]
    r.cell("(x) partner", v == [1, 1], f"the host's crew key unseated the partner's soldier (AUD-A48): C1 craft [host, client] {v}")
    r.cell("(x) client", e[C][H1]["craft"] == -1, f"the host's crew key stayed on its machine (S-9b): client H1 craft {e[C][H1]['craft']}")
def refuse(x, r, gc, tag, jcmd, payload, sid, field):
    """gc's shared_cmd for the partner's soldier: G: gc failCount +1, the popup, the flag unchanged; cell: lastFail."""
    f0 = ss(gc)["failCount"]
    gc.ok({"cmd": "shared_cmd", "jcmd": jcmd, "baseId": 0, "payload": payload})
    r.cell(f"G:{tag} {gc.name} failCount +1", wait_until(lambda: ss(gc)["failCount"] == f0 + 1, 3.0), ss(gc))
    r.cell(f"G:{tag} popup", wait_until(lambda: top(gc) == POP, 2.0), stack(gc))
    lf = ss(gc)["lastFail"]
    r.ev[f"{tag} {gc.name} lastFail, popup title"] = [lf, gc.cmd({"cmd": "screen_state"}).get("title")]
    _p, e = step(x, r, tag, gc, [sid])
    r.cell(f"G:{tag} flag unchanged", e[H][sid][field] is False and e[C][sid][field] is False, [e[H][sid], e[C][sid]])
    r.cell(tag, lf == "not your soldier", f"the host answered {lf!r} instead of 'not your soldier'")
    gc.cmd({"cmd": "coop_dialog_back"})
    r.need(f"G:{tag} popup closed", wait_until(lambda: top(gc) == GEO, 3.0), stack(gc))
def row_10(x, r):   # the host refuses the partner's soldier
    h, c, C1, H1 = x.host, x.client, x.C1, x.H1
    s0(x, r)
    for gc in (h, c):
        gc.ok({"cmd": "shared_reset_stats"})
    a0 = ss(h)["applyCount"]
    refuse(x, r, c, "(1)", "soldier_training", {"soldierId": H1, "training": True, "rtwh": False}, H1, "tr")
    refuse(x, r, h, "(2)", "soldier_psi_training", {"soldierId": C1, "psi": True}, C1, "psi")
    r.cell("G:host applyCount unchanged (1)-(2)", ss(h)["applyCount"] == a0, ss(h))
    a1 = ss(h)["applyCount"]
    c.ok({"cmd": "shared_cmd", "jcmd": "soldier_training", "baseId": 0, "payload": {"soldierId": C1, "training": True, "rtwh": False}})
    _p, e = step(x, r, "(3)", c, [C1])
    da, v = ss(h)["applyCount"] - a1, [e[H][C1]["tr"], e[C][C1]["tr"]]
    r.cell("(3)", v == [True, True] and da == 1, f"the control stayed untrained: C1 training [host, client] {v}, "
           f"host applyCount +{da}, client lastFail {ss(c)['lastFail']!r}")
    close(x, r, c, "(3)")   # the red control raises the unknown-command popup on the client (recorded in popups)
def row_11(x, r):   # the client's reset-armor key keeps the partner's armor (OC-A1-1 (a))
    h, c, C1, H1, pair = x.host, x.client, x.C1, x.H1, [x.C1, x.H1]
    s0(x, r)
    st0 = {gc.name: store(gc) for gc in (h, c)}
    for gc in (c, h):
        for i in pair:
            gc.ok({"cmd": "seed_soldier_armor", "soldier_id": i, "armor": PERSONAL})
    r.ev["armor seeded"] = a = {gc.name: armor(gc, pair) for gc in (h, c)}
    r.need("G:seed", all(v == PERSONAL for m in a.values() for v in m.values()), a)
    c.ok({"cmd": "craft_deequip_armor"})
    t0 = time.time()
    while time.time() - t0 < POLL_S:
        time.sleep(POLL_I)
        a = {gc.name: armor(gc, pair) for gc in (h, c)}
    d, n = {gc.name: store(gc) - st0[gc.name] for gc in (h, c)}, sum(1 for i in pair if a[H][i] == NONE)
    r.ev["armor end, store delta, reset count"], v, now = [a, d, n], [a[H][H1], a[C][H1]], {m.name: req(m) for m in (h, c)}
    r.cell("G:C1 reset", a[H][C1] == NONE and a[C][C1] == NONE, a)
    r.cell("G:store", d[H] == d[C] == n, f"store delta {d} vs {n} reset (R-H16b-T0-4: +2 on red)")
    r.cell("G:requests", now == r.R0, f"requests {now} vs R0 {r.R0} (STOP-IF 5)")
    r.cell("partner armor", v == [PERSONAL, PERSONAL],
           f"the client's armor-reset key stripped the partner's soldier (aud-E1-11): H1 armor [host, client] {v}")
def row_8(x, r):   # SEPARATE stays local (Boot B; guard row)
    h, c = x.host, x.client
    s_0, r.R0 = {gc.name: ss(gc) for gc in (h, c)}, {gc.name: req(gc) for gc in (h, c)}
    r.ev["fac_build"] = c.cmd({"cmd": "fac_build", "facility": FAC, "x": 0, "y": 3}).get("ok")    # local in SEPARATE
    r.need("G:facility", wait_until(lambda: fac_index(c) == FAC_IDX, 10), fac_index(c))
    bt = c.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": FAC_IDX, "time": 0})
    b0 = c.ok({"cmd": "soldier_training_probe", "ids": []})["bases"][0]
    r.need("G:buildTime0, capacities", bt.get("buildTime") == 0 and (b0["psiLabs"], b0["training"]) == (1, 1), [bt, b0])
    sid = open_screen(c, r, "martial", "martial")["rows"][0]["soldierId"]
    click(c, r, sid, "martial")
    close(x, r, c, "martial")
    sida = open_screen(c, r, "craft_armor", "armor")["rows"][0]["soldierId"]
    r.need("G:seated", craft(c, sida) == 1, craft(c, sida))
    click(c, r, sida, "armor", ctrl=True)
    time.sleep(2.0)
    own, s_1 = r.ev["own [training, seat]"], r.ev["shared_stats after"] = [flags(c, [sid])[sid]["tr"], craft(c, sida)], \
        {gc.name: ss(gc) for gc in (h, c)}
    r.cell("own flag, own seat", own == [True, -1], own)
    r.cell("shared_stats unchanged", all(s_0[m][k] == s_1[m][k] for m in s_0 for k in ("cmd", "applyCount")), [s_0, s_1])
    close(x, r, c, "armor")
def run_row(rid, fn, x, results, ids):
    r, t0 = Row(rid, x, ids), time.time()
    try:
        fn(x, r)
    except Miss:
        pass
    except Exception as e:
        r.cell("G:exception", False, short(e, 800))
    finally:
        try:
            x.client.cmd({"cmd": "shared_update_defer", "on": False})
            for gc in (gc for gc in (x.host, x.client) if top(gc) != GEO):
                r.ev.setdefault("cleanup", []).append([gc.name, stack(gc), gc.cmd({"cmd": "close_screens"}).get("ok"),
                                                       wait_until(lambda: top(gc) == GEO, 3.0)])
            r.ev["end probes"] = {gc.name: {"flags": flags(gc, x.ids), "crafts": crafts(gc), "shared_stats": ss(gc),
                                            "requests": req(gc), "stack": stack(gc)} for gc in (x.host, x.client)}
        except Exception as e:
            r.ev["cleanupError"] = short(e)
        r.cell("G:no popup", not r.popups or rid == "H16b-10", r.popups)
        r.ev["popups"], r.ev["wallS"] = r.popups, round(time.time() - t0, 1)
        r.report(results)
    return r.ev["wallS"]
def boot_miss(tag, e, rids, results):
    print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
    for rid in rids:
        results[rid] = False
        print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)
def fac_index(gc):
    facs = ((gc.cmd({"cmd": "geo_state"}).get("bases") or [{}])[0]).get("facilities") or []
    return next((i for i, f in enumerate(facs) if (f.get("type"), f.get("x"), f.get("y")) == (FAC, 0, 3)), None)
def setup_a(x):
    """Boot A: the facility (index 9) and its capacities on both, the roster and the picks (STOP-IF 9). Raises on a miss."""
    h, c = x.host, x.client
    ev = {"fac_build": h.cmd({"cmd": "fac_build", "facility": FAC, "x": 0, "y": 3}).get("ok"),
          "listed": wait_until(lambda: fac_index(h) == FAC_IDX and fac_index(c) == FAC_IDX, 10)}
    ev["buildTime"] = {gc.name: gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": FAC_IDX, "time": 0}).get("buildTime")
                       for gc in (c, h)} if ev["listed"] else None
    ev["capacities"] = {gc.name: gc.ok({"cmd": "soldier_training_probe", "ids": []})["bases"][0] for gc in (h, c)}
    seat = ev["seats"] = {gc.name: gc.cmd({"cmd": "synced_options_state"}).get("localSeat") for gc in (h, c)}
    rep = {gc.name: [(s["id"], s["owner"]) for s in gc.ok({"cmd": "base_report"})["soldiers"]] for gc in (h, c)}
    x.ids, ev["roster (id, owner)"] = [i for i, _o in rep[H]], rep
    x.C, x.H = [i for i, o in rep[H] if o == seat[C]], [i for i, o in rep[H] if o == seat[H]]
    if not (ev["listed"] and ev["buildTime"] == {H: 0, C: 0} and rep[H] == rep[C] and len(x.C) >= 2 and len(x.H) >= 2
            and all((b["psiLabs"], b["training"]) == (1, 1) for b in ev["capacities"].values())):
        raise RuntimeError(f"facility / capacities / rosters / picks (STOP-IF 9): {json.dumps(ev, default=str)}")
    x.C1, x.C2, x.H1, x.H2 = x.C[0], x.C[1], x.H[0], x.H[1]
    ev.update({"C1 C2 H1 H2": [x.C1, x.C2, x.H1, x.H2], "C": x.C, "H": x.H})
    print(f"EVIDENCE Boot A: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
ROWS_A = (("H16b-1", row_1), ("H16b-2", row_2), ("H16b-3", row_3), ("H16b-4", row_4), ("H16b-5", row_5), ("H16b-6", row_6),
          ("H16b-7", row_7), ("H16b-9", row_9), ("H16b-10", row_10), ("H16b-11", row_11))
def boot(results, walls, tag, rows, up, down, setup=None):
    """up() -> (host, client); a miss fails every row of the boot "boot" with one CAPTURE line."""
    t0, x = time.time(), type("X", (), {})()
    x.wounded, x.ids = set(), list(range(1, 9))
    try:
        try:
            x.host, x.client = up()
            walls[tag + " bring-up"] = round(time.time() - t0, 1)
            setup and setup(x)
        except Exception as e:
            return boot_miss(tag, e, [rid for rid, _f in rows], results)
        for rid, fn in rows:
            ids = [1] if rid == "H16b-8" else {"H16b-3": [x.C1, x.C2], "H16b-6": [x.C1, x.C2, x.H1],
                                               "H16b-7": [x.C1, x.C2, x.H1, x.H2]}.get(rid, [x.C1, x.H1])
            walls[rid] = run_row(rid, fn, x, results, ids)
    finally:
        down(x)
        walls[tag] = round(time.time() - t0, 1)
def up_a():
    js = UP["js"] = shared_fixture.bring_up(BOOT_A[0], BOOT_A[1], mods=(MOD,))
    return js.host, js.client
def up_b():
    (tag, labels, lobby) = BOOT_B
    h, c = UP["b"] = (GameClient("host", labels[0], make_user_dir(tag + "_host", mods=(MOD,))),
                      GameClient("client", labels[1], make_user_dir(tag + "_client", mods=(MOD,))))
    h.spawn(), c.spawn(), h.connect(), c.connect()
    session.new_campaign(h, c, port=lobby, campaign_mode="coop")
    geo.wait_both_ready(h, c)
    return h, c
UP = {}
def main():
    t0, results, walls = time.time(), {}, {}
    boot(results, walls, BOOT_A[0], ROWS_A, up_a, lambda x: UP.get("js") and UP["js"].shutdown(), setup_a)
    boot(results, walls, BOOT_B[0], (("H16b-8", row_8),), up_b, lambda x: UP.get("b") and shutdown_clients(*UP["b"]))
    failed = [n for n in ("H16b-%d" % k for k in range(1, 12)) if not results.get(n)]
    print(f"\ntest_w2_soldier_allocations: {11 - len(failed)}/11 passed (fail={failed}) walls {walls} in {time.time() - t0:.1f}s")
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
