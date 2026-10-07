"""W2-U8f - test_w2_bringup_leak_sweep.py: a bring-up that fails after its games started shuts them down (docs
rewrite/prompts/w2u8f_bringup_leak_sweep.md (f); R-U8d2-1 and its R3 sweep, F9051-F9060).
Ten test helpers start game processes where no clean-up can reach them: when they raise after the spawn, both games
keep running after Python exits (a plain Popen, no reaper; F9062). Each row makes ONE helper fail right after its
games started, through a stand-in that rebinds only a name in the helper's own module (never harness.GameClient) and
is restored in a finally, then reads every machine's Popen.poll() right after the call, before any test clean-up:
- Kind G (S1, TL, CL, RD, RS, 18, SP, BD): <module>.GameClient (sp: sp.harness, a namespace copy of harness) ->
  StandInGC, which raises right after the real connect() of the last of the row's machines.
- Kind P (CN): cn.GameClient -> StandInGC (record only); cn.session -> a namespace copy whose drive_to_battlescape is a
  recorded no-op; cn.battle_state -> a stub that raises (the first raising line after the protected bring-up).
- Kind W (GR): shared_fixture.bring_up -> a fake that builds the real SharedSession, records both machines BEFORE it
  spawns and connects them (no campaign), and replaces js.host.ok per INSTANCE by one that raises on geo_state.
  gr.boot catches that raise and returns; its own "CAPTURE ... (boot miss)" print is kept in EVIDENCE (bootPrinted).
Rows U8f-S1, -TL, -CL, -RD, -RS, -18, -SP, -BD, -CN, -GR: guards G1 the stand-in fired once (CN: and the drive was
skipped once), G2 the helper raised exactly the stand-in's RuntimeError (GR: boot returned None), G3 the row's machine
count, each with a proc, G4 every machine alive at the fire, G5 the bystander alive after the call. Named reds
<X>-reap: right after the call every machine has exited rc 0 through the harness shutdown (before the fix: alive).
A bystander game (label 49647, user dir w2u8f_bystander) boots first and runs through every row; row U8f-X (the
negative control) checks it was alive after every row and quits rc 0 at the end. exec_row shuts down every row
machine still running (harness.shutdown_clients), never the bystander.
Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard miss (FIXTURE-STOP) or a boot miss adds
ONE "CAPTURE <id>:" line. WV-D95/D99/D100: ONE foreground run, no skip path, every row runs after a failure; exit 0 only
when every row passes, 2 otherwise. Run: python tools/coop_test/test_w2_bringup_leak_sweep.py
"""

import contextlib, io, json, os, sys, time, types  # noqa: E401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_spec16_pause_on_leave as s16  # noqa: E402
import test_rw_teleport_lever as trl  # noqa: E402
import test_w2_client_landing as cl  # noqa: E402
import repro_door_deterministic as rdd  # noqa: E402
import repro_atom_spot as ras  # noqa: E402
import test_spec18_midbattle_resume as s18  # noqa: E402
import sp_smoke as sp  # noqa: E402
import test_coop_basedef_temp_ufo_uaf as ba  # noqa: E402
import test_rw_m2_corpse_node as cn  # noqa: E402
import test_w2_geo_event_replica as gr  # noqa: E402

BYSTANDER = ("u8f-bystander", 49647, "w2u8f_bystander")
GR_SPEC = ("w2u8f_geo", (49645, 49646, 47651), None)
class GuardMiss(Exception): pass  # a guard cell failed: FIXTURE-STOP


class StandInGC(harness.GameClient):
    """W2-U8f stand-in (test only): records every instance a helper builds while installed; when `want` is set, raises
    right after the real connect() of the last of `want` instances (every machine spawned and connected)."""
    made, want, fired, text, alive_at_fire = [], 0, 0, None, None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        StandInGC.made.append(self)

    def connect(self, *a, **k):
        r = super().connect(*a, **k)
        if StandInGC.want and len(StandInGC.made) == StandInGC.want and self is StandInGC.made[-1] and not StandInGC.fired:
            StandInGC.fired += 1
            StandInGC.alive_at_fire = [gc.proc is not None and gc.proc.poll() is None for gc in StandInGC.made]
            raise RuntimeError(StandInGC.text)
        return r


def short(x, n=300):
    s = x if isinstance(x, str) else json.dumps(x, default=str, sort_keys=True)
    return s if len(s) <= n else s[:n] + "..."
def safe(f):
    try: return f()
    except Exception as e: return "unreachable: %s" % short(str(e))
def tail(path, n=15):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [ln.rstrip() for ln in f.read().splitlines()][-n:]
    except OSError as e:
        return ["unreadable: %s" % e]
def alive_now(gcs):
    return [gc.proc is not None and gc.proc.poll() is None for gc in gcs]
def ns_of(mod, **over):  # a namespace copy of a module's public names, some replaced (the module itself untouched)
    d = {k: v for k, v in vars(mod).items() if not k.startswith("_")}
    d.update(over)
    return types.SimpleNamespace(**d)

class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.err, self.cap, self.machines, self.dump = rid, [], {}, None, None, [], None
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok:
            self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
    def guards(self, checks):  # every guard is judged and recorded; any miss stops the row before its named cell
        for name, ok, detail in checks:
            self.cell(name, ok, detail, guard=True)
        missed = [c["cell"] for c in self.cells if c["guard"] and not c["pass"]]
        if missed:
            raise GuardMiss("; ".join(missed))

# ---- the Kind P (cn) and Kind W (gr) stand-ins ----
ST = {"driveSkipped": 0, "rec": [], "printed": []}

def cn_drive(*a, **k):  # cn.session.drive_to_battlescape: a recorded no-op
    ST["driveSkipped"] += 1

def cn_battle_state(gc):  # cn.battle_state: the first raising line after one_bringup's protected bring-up
    StandInGC.fired += 1
    StandInGC.alive_at_fire = alive_now(StandInGC.made)
    raise RuntimeError(StandInGC.text)

def gr_ok(self, obj):  # js.host.ok, per INSTANCE: raises on geo_state, otherwise the real GameClient.ok
    if obj.get("cmd") == "geo_state":
        StandInGC.fired += 1
        StandInGC.alive_at_fire = alive_now(ST["rec"])
        raise RuntimeError(StandInGC.text)
    return harness.GameClient.ok(self, obj)

def gr_fake(tag, ports, wait_ready=True, host_base="HostBase", client_base="ClientBase", mods=(), transport="tcp",
            host_options=None, client_options=None):  # Kind W: the real SharedSession, spawned + connected, no campaign
    js = shared_fixture.SharedSession(tag, ports, mods=mods, transport=transport, host_options=host_options,
                                      client_options=client_options)
    ST["rec"][:] = [js.host, js.client]  # recorded BEFORE the spawn: a failed spawn or connect is still reachable
    js.host.spawn(); js.client.spawn(); js.host.connect(); js.client.connect()
    js.host.ok = types.MethodType(gr_ok, js.host)
    return js

def gr_call():  # gr.boot prints its own boot-miss CAPTURE line: keep it in EVIDENCE, re-print every other line
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return gr.boot(GR_SPEC, (), {}, {})
    finally:
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        ST["printed"] = [ln for ln in lines if ln.startswith("CAPTURE")]
        for ln in lines:
            if not ln.startswith("CAPTURE"):
                print(ln, flush=True)

# ---- the ten rows: (rid, cell prefix, module, helper, F code, want, bindings, call) ----
G = "GameClient"
SPECS = (
    ("U8f-S1", "S1", s16, "_bring_up", "F9051", 2, lambda: [(s16, G, StandInGC)],
     lambda: s16._bring_up("w2u8f", 9, s16.SPEC16_S1_SEED)),
    ("U8f-TL", "TL", trl, "bring_up", "F9052", 2, lambda: [(trl, G, StandInGC)],
     lambda: trl.bring_up("w2u8f", "STR_SUPPLY_SHIP", "47650", 49640, 49641)),
    ("U8f-CL", "CL", cl, "boot_pair", "F9053", 2, lambda: [(cl, G, StandInGC)], lambda: cl.boot_pair("w2u8f")),
    ("U8f-RD", "RD", rdd, "bring_up", "F9054", 2, lambda: [(rdd, G, StandInGC)], lambda: rdd.bring_up()),
    ("U8f-RS", "RS", ras, "bring_up_lightning", "F9055", 2, lambda: [(ras, G, StandInGC)],
     lambda: ras.bring_up_lightning()),
    ("U8f-18", "18", s18, "_build_midbattle_save", "F9056", 2, lambda: [(s18, G, StandInGC)],
     lambda: s18._build_midbattle_save("s18mr_w2u8f", 49642)),
    ("U8f-SP", "SP", sp, "main", "F9057", 1, lambda: [(sp, "harness", ns_of(harness, GameClient=StandInGC))],
     lambda: sp.main()),
    ("U8f-BD", "BD", ba, "main", "F9058", 2, lambda: [(ba, G, StandInGC)], lambda: ba.main()),
    ("U8f-CN", "CN", cn, "one_bringup", "F9059", 0,
     lambda: [(cn, G, StandInGC), (cn, "session", ns_of(session, drive_to_battlescape=cn_drive)),
              (cn, "battle_state", cn_battle_state)],
     lambda: cn.one_bringup(62, cn.SEED_KILLED, cn.FINGERPRINT_KILLED)),
    ("U8f-GR", "GR", gr, "boot", "F9060", 0, lambda: [(shared_fixture, "bring_up", gr_fake)], gr_call),
)
WANT_N = {"U8f-SP": 1}  # machines per row (every other row: 2)

def standin_row(r, by, cid, mod, helper, fcode, want, bind, call):
    name = "%s.%s" % (mod.__name__, helper)
    StandInGC.made, StandInGC.fired, StandInGC.alive_at_fire = [], 0, None
    StandInGC.want, StandInGC.text = want, "W2-U8f stand-in: %s bring-up failed after its games started (%s)" % (
        r.rid, fcode)
    ST["driveSkipped"], ST["rec"], ST["printed"] = 0, [], []
    r.machines = ST["rec"] if r.rid == "U8f-GR" else StandInGC.made  # filled by the bring-up: exec_row reaches them
    saved, raised, ret, ms, alive, rc, done, by_alive = [], None, "not called", [], [], [], [], None
    try:
        for obj, attr, val in bind():
            saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, val)
        try:
            ret = call()
        except (Exception, SystemExit) as e:
            raised = [type(e).__name__, str(e)]
        ms = list(r.machines)  # read at once, before any clean-up
        alive, rc = alive_now(ms), [gc.proc.poll() if gc.proc else None for gc in ms]
        done, by_alive = [gc._shutdown_proc is gc.proc for gc in ms], by.proc.poll() is None
    finally:
        for obj, attr, orig in reversed(saved):
            setattr(obj, attr, orig)
    r.dump = {gc.name: safe(lambda gc=gc: session.states(gc)) if a else "exited rc %s" % c
              for gc, a, c in zip(ms, alive, rc)}  # CAPTURE's state (after the reads)
    si = {"fired": StandInGC.fired, "aliveAtFire": StandInGC.alive_at_fire,
          "pids": {gc.name: gc.proc.pid if gc.proc else None for gc in ms}}
    if r.rid == "U8f-CN":
        si["driveSkipped"] = ST["driveSkipped"]
    r.ev.update(helper=name, machines=[gc.name for gc in ms], standIn=si, raised=raised,
                returned=repr(ret) if raised is None else None, alive=alive, rc=rc, shutdownDone=done,
                bystander=by_alive)
    if r.rid == "U8f-GR":
        r.ev["bootPrinted"] = ST["printed"]
    n, text = WANT_N.get(r.rid, 2), StandInGC.text
    r.guards([("G1 the stand-in fired once" + (" and the drive was skipped once" if r.rid == "U8f-CN" else ""),
               StandInGC.fired == 1 and (r.rid != "U8f-CN" or ST["driveSkipped"] == 1), si),
              (("G2 gr.boot returned None with no exception" if r.rid == "U8f-GR" else
                "G2 %s raised exactly the stand-in's RuntimeError" % name),
               (raised is None and ret is None) if r.rid == "U8f-GR" else raised == ["RuntimeError", text],
               {"raised": raised, "returned": r.ev["returned"]}),
              ("G3 %d machine(s), each with a proc" % n, len(ms) == n and all(gc.proc is not None for gc in ms),
               r.ev["machines"]),
              ("G4 every machine alive at the fire", bool(StandInGC.alive_at_fire) and all(StandInGC.alive_at_fire),
               si),
              ("G5 the bystander alive after the call", by_alive, by_alive)])
    left = [gc.name for gc, a in zip(ms, alive) if a]
    msg = ("%s's failed bring-up left %s running (%s)" % (name, " and ".join(left), fcode) if left else
           "%s's failed bring-up: rc %s, shutdownDone %s (%s)" % (name, rc, done, fcode))
    r.cell("%s-reap: %s's failed bring-up shut every game it started down (rc 0)" % (cid, name),
           not left and rc == [0] * n and all(done), {"alive": alive, "rc": rc, "shutdownDone": done}, msg)

BY_SEEN = {}  # rid -> the bystander alive after that row (exec_row, after the row's clean-up)

def u8f_x(r, by):
    alive_end, err = by.proc.poll() is None, None
    try:
        harness.shutdown_clients(by)
    except Exception as e:
        err = short(str(e))
    r.ev.update(bystanderAfterRows=dict(BY_SEEN), aliveAtEnd=alive_end, pid=by.proc.pid, rc=by.proc.poll(),
                shutdownErr=err)
    every = len(BY_SEEN) == len(SPECS) and all(BY_SEEN.values())
    r.cell("X: the bystander was alive after every row, and its shutdown at the end gives rc 0",
           every and alive_end and by.proc.poll() == 0 and err is None, r.ev,
           "the clean-up reached a game the helper did not start, or the bystander did not quit rc 0")

ROWS = tuple((s[0], (lambda r, by, s=s: standin_row(r, by, *s[1:]))) for s in SPECS) + (("U8f-X", u8f_x),)

def capture(r):
    return {"standIn": r.ev.get("standIn"), "raised": r.ev.get("raised"), "states": r.dump,
            "logTails": {os.path.basename(gc.user_dir): tail(os.path.join(gc.user_dir, "openxcom.log"))
                         for gc in r.machines if gc.user_dir}}
def exec_row(rid, fn, by):
    r, t0 = Row(rid), time.time()
    try:
        fn(r, by)
    except GuardMiss as e: r.err = "GUARD %s" % e
    except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    ms = list(r.machines)
    live = [gc for gc in ms if gc.proc is not None and gc.proc.poll() is None]  # never the bystander
    if ms:
        try:
            harness.shutdown_clients(*live)
        except Exception as e:
            r.ev["cleanupErr"] = short(str(e))
        r.ev["rcAfterCleanup"] = [gc.proc.poll() if gc.proc else None for gc in ms]
    if rid != "U8f-X":
        BY_SEEN[rid] = by.proc.poll() is None
    r.ev["wall"] = round(time.time() - t0, 1)
    if r.err:
        r.cap = safe(lambda: capture(r))
    return r
def report(r, results):
    r.ev["cells"] = [[c["cell"], "guard" if c["guard"] else "row", c["pass"]] for c in r.cells]
    print("EVIDENCE %s: %s" % (r.rid, json.dumps(r.ev, default=str)), flush=True)
    if r.err:
        print("CAPTURE %s: %s" % (r.rid, json.dumps(r.cap, default=str)), flush=True)
    fails = ["%s%s: %s" % ("GUARD " if c["guard"] else "", c["cell"], c["msg"]) for c in r.cells if not c["pass"]]
    fails += [r.err] if r.err and not r.err.startswith("GUARD") else []
    results[r.rid] = not fails
    print("PASS %s" % r.rid if not fails else "FAIL %s: %s" % (r.rid, " || ".join(fails)), flush=True)

def main():
    t0, results, order = time.time(), {}, [rid for rid, _ in ROWS]
    by = harness.GameClient(BYSTANDER[0], BYSTANDER[1], harness.make_user_dir(BYSTANDER[2]))
    try:
        by.spawn(); by.connect()
    except Exception as e:  # a bystander boot miss fails every row "boot (bystander)" with ONE CAPTURE line
        print("CAPTURE U8f-bystander: %s" % json.dumps({"error": "%s: %s" % (type(e).__name__, short(str(e), 800)),
                                                         "logTail": tail(os.path.join(by.user_dir, "openxcom.log"))}),
              flush=True)
        safe(lambda: harness.shutdown_clients(by))
        for rid in order:
            print("EVIDENCE %s: %s" % (rid, json.dumps({"boot": "bystander"})), flush=True)
            print("FAIL %s: boot (bystander)" % rid, flush=True)
            results[rid] = False
    else:
        for rid, fn in ROWS:
            report(exec_row(rid, fn, by), results)
    passed, failed = [x for x in order if results.get(x)], [x for x in order if not results.get(x)]
    print("\ntest_w2_bringup_leak_sweep: %d/%d passed (pass=%s fail=%s) in %.1fs" % (
        len(passed), len(order), passed, failed, time.time() - t0), flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
