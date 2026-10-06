"""W2-U8d - test_w2_harness_truth.py: the harness reports what a run really did (docs
rewrite/prompts/w2u8d_harness_truth.md (f)). STAGE 1 of the orchestrator's split (session b06ae2b9): rows U8d-T (F7624)
and U8d-S (F8172); the F6304 rows (U8d-W / -F / -X / -D) wait on owner decision D256.
U8d-T (no game): four child scripts import harness and end by an uncaught assert, an uncaught raise, sys.exit(2) and a
clean return, with OXC_TIMELOG pointing at a temp tl.csv. Each child's timelog test_end row must report its real process
exit code. The harness tracked only sys.exit, so an uncaught exception (rc 1) was logged exit=0 (named reds T-assert,
T-raise).
U8d-S (one boot: test_spec16_pause_on_leave.run_s2's own bring-up, ports 49970-49972, user dirs spec16s2_*): a refusal
stand-in, installed per INSTANCE on host._send / client._send by a wrapper of s16._s2_bring_up (never by patching
harness.GameClient), refuses the host leg of the FIRST battle_teleport_unit the host sees. run_s2 sends that leg only
after the client's ok, so the client's soldier already stands on the tile (T1); the hook records both machines'
positions of the soldier through GameClient._send on the instance. Later teleports are counted and sent. run_s2 must
stop there (FAIL, exit 1) instead of staging on with the soldier moved on the client alone (named red S-stop).
Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard miss (FIXTURE-STOP) or a boot miss adds
one "CAPTURE <id>:" line. WV-D95/D99/D100: ONE foreground run, no skip path, every row runs after a failure; exit 0 only
when every row passes, 2 otherwise. Never pair this file with test_spec16_pause_on_leave* in one K=2 batch (S26: U8d-S
runs run_s2's bring-up). Run: python tools/coop_test/test_w2_harness_truth.py
"""

import json, os, shutil, subprocess, sys, tempfile, time, types  # noqa: E401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402
import test_spec16_pause_on_leave as s16  # noqa: E402

# (name, body, the process exit code the child must give)
CHILDREN = (("u8d_t_assert.py", 'assert False, "W2-U8d deliberate"', 1),
            ("u8d_t_raise.py", 'raise RuntimeError("W2-U8d deliberate")', 1),
            ("u8d_t_exit2.py", "sys.exit(2)", 2),
            ("u8d_t_clean.py", "pass", 0))
NAMED_T = {"u8d_t_assert.py": "T-assert", "u8d_t_raise.py": "T-raise"}
REFUSAL = {"ok": False, "error": "W2-U8d stand-in: host leg refused (F8172)"}
class GuardMiss(Exception): pass  # a guard cell failed: FIXTURE-STOP


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

class Row:
    def __init__(self, rid):
        self.rid, self.cells, self.ev, self.err, self.cap, self.tmp, self.machines = rid, [], {}, None, None, None, []
    def cell(self, name, ok, detail, msg=None, guard=False):
        self.cells.append({"cell": name, "guard": guard, "pass": bool(ok)})
        if not ok:
            self.cells[-1]["msg"] = (msg + " | " if msg else "") + short(detail, 900)
    def guards(self, checks):  # every guard is judged and recorded; any miss stops the row before its named cells
        for name, ok, detail in checks:
            self.cell(name, ok, detail, guard=True)
        missed = [c["cell"] for c in self.cells if c["guard"] and not c["pass"]]
        if missed:
            raise GuardMiss("; ".join(missed))

def u8d_t(r):
    tmp = r.tmp = tempfile.mkdtemp(prefix="w2u8d_t_")
    tl = os.path.join(tmp, "tl.csv")
    env = {k: v for k, v in os.environ.items() if k != "OXC_TIMELOG_SPAWNS"}
    env.update(OXC_TIMELOG=tl, OXC_AGENT="w2u8d-child")
    kids, r.capT = r.ev.setdefault("children", []), []
    for name, body, want in CHILDREN:
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write("import sys\nsys.path.insert(0, %r)\nimport harness\n%s\n" % (HERE, body))
        p = subprocess.run([sys.executable, path], env=env, cwd=tmp, capture_output=True, text=True, timeout=60)
        err = [ln for ln in p.stderr.splitlines() if ln.strip()]
        kids.append({"child": name, "rc": p.returncode, "want": want, "stderrLast": err[-1] if err else ""})
        r.capT.append({"child": name, "stdout": p.stdout.splitlines()[-5:], "stderr": err[-5:]})
    try:
        with open(tl, encoding="utf-8") as f:
            rows = [ln for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        rows = []
    r.ev["tlRows"] = [ln.split(",", 3)[-1] for ln in rows]  # "event,detail" (stamp and agent left out)
    ends = {}
    for ln in rows:
        f = ln.split(",", 4)
        if len(f) == 5 and f[3] == "test_end":
            nm, _, ex = f[4].partition(" exit=")
            ends.setdefault(nm, []).append(ex)
    for k in kids:
        k["testEnd"] = ends.get(k["child"], [])
    r.guards([("rc 1 / 1 / 2 / 0", [k["rc"] for k in kids] == [w for _, _, w in CHILDREN], [k["rc"] for k in kids]),
              ("exactly one test_end row per child", all(len(k["testEnd"]) == 1 for k in kids),
               {k["child"]: k["testEnd"] for k in kids}),
              ("u8d_t_exit2.py exit=2", kids[2]["testEnd"] == ["2"], kids[2]),
              ("u8d_t_clean.py exit=0", kids[3]["testEnd"] == ["0"], kids[3])])
    for k in kids[:2]:
        r.cell("%s: %s test_end exit=1 (its rc)" % (NAMED_T[k["child"]], k["child"]), k["testEnd"] == ["1"], k,
               "the timelog test_end row says exit=%s for a run that exited 1 (F7624)" % k["testEnd"][0])

def spawned_by(exc, fn):  # the machines a failed bring-up spawned: its own frame's locals (run_s2 never got them)
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code is fn.__code__:
            return [tb.tb_frame.f_locals.get(k) for k in ("host", "client")]
        tb = tb.tb_next
    return []

def u8d_s(r):
    st = r.ev["standIn"] = {"fired": 0, "refusal": None, "clientBefore": 0, "clientAfter": 0, "hostAfter": 0,
                            "teleports": []}
    orig, t0, code = s16._s2_bring_up, time.time(), None

    def pos(gc, uid):  # through the class's _send: the hooks never see their own probe
        try:
            units = harness.GameClient._send(gc, {"cmd": "battle_state"}).get("units", [])
            u = [x for x in units if x.get("id") == uid]
            return [u[0].get("x"), u[0].get("y"), u[0].get("z")] if u else None
        except Exception as e:
            return "unreadable: %s" % short(str(e), 120)

    def bring_up(base_port):
        try:
            host, client = orig(base_port)
        except BaseException as e:
            r.machines = [gc for gc in spawned_by(e, orig) if gc is not None]
            raise
        r.machines, r.ev["bootS"] = [host, client], round(time.time() - t0, 1)

        def host_send(self, obj):
            if obj.get("cmd") != "battle_teleport_unit":
                return harness.GameClient._send(self, obj)
            tile = [obj.get("x"), obj.get("y"), obj.get("z")]
            if not st["fired"]:
                st["fired"], uid = 1, obj.get("unit")
                st["refusal"] = {"tile": tile, "unit": uid, "clientPos": pos(client, uid), "hostPos": pos(host, uid)}
                st["teleports"].append(["host", tile, "refused by the stand-in"])
                return dict(REFUSAL)
            st["hostAfter"] += 1
            rep = harness.GameClient._send(self, obj)
            st["teleports"].append(["host", tile, rep.get("ok")])
            return rep

        def client_send(self, obj):
            if obj.get("cmd") != "battle_teleport_unit":
                return harness.GameClient._send(self, obj)
            st["clientAfter" if st["fired"] else "clientBefore"] += 1
            rep = harness.GameClient._send(self, obj)
            st["teleports"].append(["client", [obj.get("x"), obj.get("y"), obj.get("z")], rep.get("ok")])
            return rep

        host._send, client._send = types.MethodType(host_send, host), types.MethodType(client_send, client)
        return host, client

    s16._s2_bring_up = bring_up
    try:
        s16.run_s2()
        code = "returned"
    except SystemExit as e:  # run_s2 ends in sys.exit and shuts its machines down itself
        code = e.code
    finally:
        s16._s2_bring_up = orig
        r.ev["exit"], r.ev["runS2S"] = code, round(time.time() - t0, 1)
    ref = st["refusal"] or {}
    r.guards([("the stand-in fired once", st["fired"] == 1, st),
              ("at the refusal the client's soldier stood on T1 and the host's did not",
               ref.get("clientPos") == ref.get("tile") and isinstance(ref.get("hostPos"), list)
               and ref.get("hostPos") != ref.get("tile"), ref)])
    ca, ha = st["clientAfter"], st["hostAfter"]
    r.cell("S-stop: run_s2 stops at the refusal (0 client / 0 host teleports after it, exit 1)",
           ca == 0 and ha == 0 and code == 1, {"clientAfter": ca, "hostAfter": ha, "exit": code},
           "run_s2 staged on after the host refused tile %s the client had accepted: %d client / %d host teleports "
           "followed, exit %s (F8172)" % (tuple(ref["tile"]), ca, ha, code))
ROWS = (("U8d-T", u8d_t), ("U8d-S", u8d_s))

def capture(r):
    if r.rid == "U8d-T":
        return {"tmp": r.tmp, "children": getattr(r, "capT", None)}
    dirs = [gc.user_dir for gc in r.machines] or [os.path.join(harness.TEST_ROOT, "s%d_spec16s2_%s" % (
        harness.HARNESS_SLOT, m)) for m in ("host", "client")]
    return {"standIn": r.ev.get("standIn"), "exit": r.ev.get("exit"),
            "logTails": {os.path.basename(d): tail(os.path.join(d, "openxcom.log")) for d in dirs}}
def exec_row(rid, fn):
    r, t0 = Row(rid), time.time()
    try:
        fn(r)
    except GuardMiss as e: r.err = "GUARD %s" % e
    except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    for gc in r.machines:  # every machine down before the next row (run_s2 shuts its own; a boot miss leaves them up)
        if gc.proc is not None and gc.proc.poll() is None:
            safe(gc.shutdown)
    if rid == "U8d-S" and r.err and "bootS" not in r.ev:
        r.err = "boot (%s)" % r.err
    r.ev["wall"] = round(time.time() - t0, 1)
    if r.err:
        r.cap = safe(lambda: capture(r))
    elif r.tmp and all(c["pass"] for c in r.cells):
        shutil.rmtree(r.tmp, ignore_errors=True)
    elif r.tmp:
        r.ev["kept"] = r.tmp
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
    t0, results = time.time(), {}
    for rid, fn in ROWS:
        report(exec_row(rid, fn), results)
    order = [rid for rid, _ in ROWS]
    passed, failed = [x for x in order if results.get(x)], [x for x in order if not results.get(x)]
    print("\ntest_w2_harness_truth: %d/%d passed (pass=%s fail=%s) in %.1fs" % (
        len(passed), len(order), passed, failed, time.time() - t0), flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
