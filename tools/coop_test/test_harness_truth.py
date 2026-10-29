"""test_harness_truth.py: the harness reports what a run really did. Rows timelog_exit_codes, turn_stall_spanned,
fall_stall_spanned, death_stall_spanned, live_death_stall, refused_teleport_stops and failed_bringup_reaps, in this
order; each machine is down before the next row.
timelog_exit_codes (no game): four child scripts import harness and end by an uncaught assert, an uncaught raise,
sys.exit(2) and a clean return, with OXC_TIMELOG pointing at a temp tl.csv. Each child's timelog test_end row must
report its real process exit code (when broken, an uncaught exception, rc 1, is logged exit=0: cells assert_exit,
raise_exit).
turn_stall_spanned / fall_stall_spanned / death_stall_spanned (no game): a ghost's dirsShown / phasesShown list what
each client frame drew of a fixed schedule, so a frame stall leaves whole windows out. Fake records and fake machines
(Fake: cmd answers a copy of its answer, any other command is a fixture error) go through the real gp.turn_fails,
tc.fall_row and hc.death_row: the quiet cell passes, every defect cell fails, and the stall cell, whose left-out
entries the record's own maxGapMs spans, must pass (turn_stall, fall_stall, death_stall: an exact compare fails them).
live_death_stall (lobby 47238, labels 49435 / 49436, user dirs harness_truth_live_*, coopGhostStepper on both): the
client's slow_top {BattlescapeState, 50 ms} around hc.row_host_kill makes every client frame >= 50 ms, so A's death
record leaves >= 2 of its 6 interior octants out. Cells: record_has_gap (the record carries maxGapMs >= 50) and
kill_check_passes (row_host_kill raises nothing on host_kill_death's lists).
refused_teleport_stops (test_pause_on_leave.run_alien_turn_kill's own bring-up, ports 49970-49972, user dirs
pause_alien_turn_*): a refusal stand-in, installed per INSTANCE on host._send / client._send by a wrapper of
pause_on_leave._alien_turn_bring_up (never by patching harness.GameClient), refuses the host leg of the FIRST
battle_teleport_unit the host sees. run_alien_turn_kill sends that leg only after the client's ok, so the client's
soldier already stands on the tile; the hook records both machines' positions of the soldier through GameClient._send on
the instance. Later teleports are counted and sent. run_alien_turn_kill must stop there (FAIL, exit 1) instead of
staging on with the soldier moved on the client alone (cell stops_at_refusal).
failed_bringup_reaps (run_alien_turn_kill's own bring-up again): a stand-in for the module attribute
pause_on_leave.sid.bring_up_lobby runs the real lobby dance, then raises. The machines are _alien_turn_bring_up's own
frame locals (spawned_by); run_alien_turn_kill's failed bring-up must shut both games down before the error propagates
(cell both_games_shut; when broken, both are left running).
Each row prints "EVIDENCE <id>:" then "PASS <id>" or "FAIL <id>: ..."; a guard miss (setup failure) or a boot miss adds
one "CAPTURE <id>:" line. ONE foreground run, no skip path, every row runs after a failure; exit 0 only
when every row passes, 2 otherwise. Never pair this file with test_pause_on_leave* in one K=2 batch
(refused_teleport_stops and failed_bringup_reaps run its bring-up). Run: python tools/coop_test/test_harness_truth.py
"""

import contextlib, copy, io, json, os, shutil, subprocess, sys, tempfile, time, types  # noqa: E401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness  # noqa: E402
import test_pause_on_leave as pause_on_leave  # noqa: E402
import session  # noqa: E402
import test_host_combat as hc  # noqa: E402
import test_ghost_projectile as gp  # noqa: E402
import test_turn_cues as tc  # noqa: E402

# (name, body, the process exit code the child must give)
CHILDREN = (("child_assert.py", 'assert False, "deliberate"', 1),
            ("child_raise.py", 'raise RuntimeError("deliberate")', 1),
            ("child_exit2.py", "sys.exit(2)", 2),
            ("child_clean.py", "pass", 0))
NAMED_CHILDREN = {"child_assert.py": "assert_exit", "child_raise.py": "raise_exit"}
REFUSAL = {"ok": False, "error": "stand-in: host leg refused"}
class GuardMiss(Exception): pass  # a guard cell failed: setup failure


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

def row_timelog_exit_codes(r):
    tmp = r.tmp = tempfile.mkdtemp(prefix="harness_truth_timelog_")
    tl = os.path.join(tmp, "tl.csv")
    env = {k: v for k, v in os.environ.items() if k != "OXC_TIMELOG_SPAWNS"}
    env.update(OXC_TIMELOG=tl, OXC_AGENT="harness-truth-child")
    kids, r.childCapture = r.ev.setdefault("children", []), []
    for name, body, want in CHILDREN:
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write("import sys\nsys.path.insert(0, %r)\nimport harness\n%s\n" % (HERE, body))
        p = subprocess.run([sys.executable, path], env=env, cwd=tmp, capture_output=True, text=True, timeout=60)
        err = [ln for ln in p.stderr.splitlines() if ln.strip()]
        kids.append({"child": name, "rc": p.returncode, "want": want, "stderrLast": err[-1] if err else ""})
        r.childCapture.append({"child": name, "stdout": p.stdout.splitlines()[-5:], "stderr": err[-5:]})
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
              ("child_exit2.py exit=2", kids[2]["testEnd"] == ["2"], kids[2]),
              ("child_clean.py exit=0", kids[3]["testEnd"] == ["0"], kids[3])])
    for k in kids[:2]:
        r.cell("%s: %s test_end exit=1 (its rc)" % (NAMED_CHILDREN[k["child"]], k["child"]), k["testEnd"] == ["1"], k,
               "the timelog test_end row says exit=%s for a run that exited 1" % k["testEnd"][0])

def spawned_by(exc, fn):  # the machines a failed bring-up spawned: its own frame's locals (the caller never got them)
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code is fn.__code__:
            return [tb.tb_frame.f_locals.get(k) for k in ("host", "client")]
        tb = tb.tb_next
    return []

def row_refused_teleport_stops(r):
    st = r.ev["standIn"] = {"fired": 0, "refusal": None, "clientBefore": 0, "clientAfter": 0, "hostAfter": 0,
                            "teleports": []}
    orig, t0, code = pause_on_leave._alien_turn_bring_up, time.time(), None

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

    pause_on_leave._alien_turn_bring_up = bring_up
    try:
        pause_on_leave.run_alien_turn_kill()
        code = "returned"
    except SystemExit as e:  # run_alien_turn_kill ends in sys.exit and shuts its machines down itself
        code = e.code
    finally:
        pause_on_leave._alien_turn_bring_up = orig
        r.ev["exit"], r.ev["runAlienTurnS"] = code, round(time.time() - t0, 1)
    ref = st["refusal"] or {}
    r.guards([("the stand-in fired once", st["fired"] == 1, st),
              ("at the refusal the client's soldier stood on the refused tile and the host's did not",
               ref.get("clientPos") == ref.get("tile") and isinstance(ref.get("hostPos"), list)
               and ref.get("hostPos") != ref.get("tile"), ref)])
    ca, ha = st["clientAfter"], st["hostAfter"]
    r.cell("stops_at_refusal: run_alien_turn_kill stops at the refusal (0 client / 0 host teleports after it, exit 1)",
           ca == 0 and ha == 0 and code == 1, {"clientAfter": ca, "hostAfter": ha, "exit": code},
           "run_alien_turn_kill staged on after the host refused tile %s the client had accepted: %d client / "
           "%d host teleports followed, exit %s" % (tuple(ref["tile"]), ca, ha, code))

# ---- turn / fall / death stall rows (no game): fake records through the real checks ----
# (cell, the record's list, its maxGapMs): the quiet cell, the named stall cell, then the defect cells
TURN_CELLS = (("turn_quiet", [6, 7, 0, 1], 4), ("turn_stall", [6, 0, 1], 45), ("turn_short_gap", [6, 0, 1], 20),
              ("turn_two_left_out", [6, 1], 45), ("turn_out_of_order", [6, 0, 7, 1], 200))
FALL_CELLS = (("fall_quiet", list(range(8)), 5), ("fall_stall", [0, 1, 2, 4, 5, 6, 7], 40),
              ("fall_short_gap", [0, 1, 2, 4, 5, 6, 7], 25), ("fall_first_left_out", list(range(1, 8)), 100))
DEATH_CELLS = (("death_quiet", [4, 5, 6, 7, 0, 1, 2, 3], 4), ("death_stall", [4, 5, 6, 1, 2, 3], 113),
               ("death_short_gap", [4, 5, 6, 1, 2, 3], 50), ("death_first_left_out", [5, 6, 7, 0, 1, 2, 3], 200))
DEATH_CUE = ('[06-10-2026_00-00-00.000]\t[INFO]\t[coop-cue] death seq 12 actionId 1: '
         '{"damageType":1,"front":false,"instant":false,"outcome":"dead","unit":1000000}\n')

class Fake:  # a machine stand-in: cmd answers a deep copy of answers[cmd]; any other command is a fixture error
    def __init__(self, name, answers, user_dir=None):
        self.name, self.answers, self.user_dir = name, answers, user_dir
    def cmd(self, req):
        if req.get("cmd") not in self.answers:
            raise RuntimeError("fixture error: fake %s was sent %s" % (self.name, short(req)))
        return copy.deepcopy(self.answers[req["cmd"]])
def host_dt():  # every death / effect count 0, no record
    return {"death": {"counts": {k: 0 for k in hc.DEATH_COUNT_KEYS}, "queued": 0, "ring": []},
            "effects": dict({k: {"count": 0, "ring": []} for k in ("medikit", "prime", "panic")},
                            fall={"enqueued": 0, "completed": 0, "cut": 0, "ring": [], "seen": []})}
def host_cg():  # the host combatGhost all zero
    kinds = ("shot", "hit", "explosion", "melee", "psi")
    return dict({g: {k: 0 for k in kinds} for g in ("enqueued", "completed", "cut")}, live=0, ring=[])

def turn_cell(dirs, gap, tmp=None):  # C's 4-octant turn 6 -> 2 before its shot, through gp.turn_fails
    tr = {"seq": 30, "actionId": 5, "unit": gp.C_ID, "fromDir": 6, "toDir": 2, "octants": 4, "durationMs": 120,
          "seat": gp.COOP_SEAT_1, "endedBy": "natural", "dirsShown": dirs, "poseShown": gp.STATUS_TURNING,
          "maxGapMs": gap, "endStamp": 8}
    tv = {"actionId": 5, "hostChain": [(30, "turn"), (31, "shot")], "clientChain": [(30, "turn", 5), (31, "shot", 5)],
          "turnSeq": 30, "turnPayload": {"unit": gp.C_ID, "fromDir": 6, "toDir": 2, "turretOnly": False, "tuAfter": 56},
          "turnRecords": [tr], "turnCounts": {"host": {}, "client": {}}, "pace": {"host": 30, "client": 30},
          "shotRecords": [{"seq": 31, "afterTurnSeq": 30, "waitMs": 0, "maxGapMs": 3, "startStamp": 9, "ms": 0,
                           "steps": 0, "cut": False}]}
    return gp.turn_fails({"seq0": 0}, tv, gp.C_ID, gp.COOP_SEAT_1, 6, 2, [6, 7, 0, 1], {"host": 60, "client": 60})

def fall_cell(phases, gap, tmp=None):  # U's fall (21,14,1) -> (21,14,0), through tc.fall_row
    rec = {"seq": 41, "unit": tc.U_ID, "from": {"x": 21, "y": 14, "z": 1}, "to": {"x": 21, "y": 14, "z": 0},
           "paceMs": 30, "phasesShown": phases, "anchors": ["trailing"], "landedAtStart": True, "levels": 1,
           "startedTop": "BattlescapeState", "cut": False, "waitMs": 120, "endedBy": "natural", "maxGapMs": gap}
    ccg = {g: {"melee": 0, "psi": 0} for g in ("enqueued", "completed", "cut")}
    host = Fake("host", {"event_state": {"ok": True, "rngSeed": 7, "displayTwo": host_dt(), "combatGhost": host_cg()}})
    client = Fake("client", {"event_state": {
        "ok": True, "rngSeed": 7, "speed": {"floor": {"xcom": 30}}, "combatGhost": ccg,
        "displayTwo": {"effects": {"fall": {"enqueued": 1, "completed": 1, "cut": 0, "ring": [rec], "seen": []}}}}})
    snap = {"dt": {"host": host_dt(), "client": {"effects": {"fall": {"enqueued": 0, "completed": 0, "cut": 0}}}},
            "cg": {"host": host_cg(), "client": ccg}, "rng": 7}
    return tc.fall_row(host, client, {}, snap, {"seq": 41})

def death_cell(dirs, gap, tmp):  # A's host_kill death record (seq 12, actionId 1), through hc.death_row
    uh = {"id": hc.A_ID, "deathFrames": 3, "deathSounds": [10], "fallPhase": 2, "health": 0, "overKill": 0, "status": 6}
    rec = {"Ic": 100, "Is": 33, "actionId": 1, "dirsShown": dirs, "endedBy": "out", "frames": 3, "fromDir": 4,
           "front": False, "headStartedAtEnqueue": False, "holdMs": 12, "instant": False, "isOutMs": 698, "octants": 7,
           "outcome": "dead", "overKill": 0, "phasesShown": [0, 1, 2], "popMs": 898, "respawn": False, "seq": 12,
           "sound": 10, "startedAfterSeq": 0, "tc": 398, "unit": hc.A_ID, "unitDyingCleared": False,
           "unitDyingSet": False, "maxGapMs": gap}
    after = {"completed": 1, "cut": 0, "enqueued": 1, "instant": 0, "started": 1}
    host = Fake("host", {"event_state": {"ok": True, "rngSeed": 3, "displayTwo": host_dt()},
                         "battle_state": {"ok": True, "units": [uh]}}, user_dir=tmp)
    client = Fake("client", {"event_state": {"ok": True, "rngSeed": 9, "displayTwo": {"death": {
        "counts": after, "queued": 0, "ring": [rec]}}}, "battle_state": {"ok": True, "units": [dict(uh, fallPhase=0)]}})
    snap = {"dt": {"host": host_dt(), "client": {"death": {
        "counts": {k: 0 for k in hc.DEATH_COUNT_KEYS}, "queued": 0, "ring": []}}}, "rng": 9}
    return hc.death_row("host_kill_death", host, client, snap, [  # want exactly as row_host_kill (seq 12, actionId 1)
        {"seq": 12, "actionId": 1, "unit": hc.A_ID, "payload": hc.KILL_DEATH, "front": False, "fromDir": hc.KILL_A_DIR,
         "octants": 7, "respawn": False, "Is": hc.DEATH_IS_TURN, "sounds": hc.SECTOID_DEATH_SOUNDS,
         "startedAfterSeq": 0, "overKill": hc.OVERKILL_NONE, "endedBy": "out", "unitDyingSet": False,
         "dirsShown": hc.DIRS_4_TO_3, "phasesShown": hc.PHASES_ALL}])

def fake_row(r, cell_fn, cells, field, what):
    """Each cell ONE call of the real check on the fakes (its own EVIDENCE print kept off stdout). Guards: the quiet
    cell returns [], every defect cell >= 1 fail, every fail names `field`. Named: the stall cell returns []."""
    out = r.ev["cellFails"] = {}
    for name, lst, gap in cells:
        with contextlib.redirect_stdout(io.StringIO()):
            out[name] = {"list": lst, "maxGapMs": gap, "fails": cell_fn(lst, gap, r.tmp)}
    quiet, (named, _, gap) = cells[0][0], cells[1]
    r.guards([("%s returns []" % quiet, out[quiet]["fails"] == [], out[quiet])]
             + [("%s fails (no gap explains it)" % n, len(out[n]["fails"]) >= 1, out[n]) for n, _, _ in cells[2:]]
             + [("every fail names %s" % field, all(field in m for c in out.values() for m in c["fails"]), out)])
    r.cell("%s: a record whose left-out entries its %d ms frame gap spans passes" % (named, gap),
           out[named]["fails"] == [], out[named], what)
def row_turn_stall_spanned(r):
    fake_row(r, turn_cell, TURN_CELLS, "dirsShown",
             "turn_fails failed a turn record whose left-out octant a 45 ms frame gap explains")
def row_fall_stall_spanned(r):
    fake_row(r, fall_cell, FALL_CELLS, "phasesShown",
             "fall_row failed a fall record whose left-out phase a 40 ms frame gap explains")
def row_death_stall_spanned(r):
    # the fake host's user_dir: its openxcom.log holds the death cue
    r.tmp = tempfile.mkdtemp(prefix="harness_truth_death_")
    with open(os.path.join(r.tmp, "openxcom.log"), "w", encoding="ascii", newline="\n") as f:
        f.write(DEATH_CUE)
    fake_row(r, death_cell, DEATH_CELLS, "Shown",
             "death_row failed a death record whose left-out octants a 113 ms frame gap explains")

# ---- live_death_stall: test_host_combat's host_kill under the client's slow_top ----
LIVE_LOBBY, LIVE_LABELS, GHOST = "47238", (49435, 49436), {"coopGhostStepper": True}
SLOW_ON = {"cmd": "slow_top", "type": "BattlescapeState", "ms": 50, "timeoutMs": 60000}
DEATH_FAIL_PREFIX = "host_kill_death: client death record seq"

def row_live_death_stall(r):
    t0, ev = time.time(), r.ev
    r.machines = [harness.GameClient(n, p, harness.make_user_dir("harness_truth_live_" + n, options=GHOST))
                  for n, p in zip(("host", "client"), LIVE_LABELS)]
    host, client = r.machines
    old, hc.PORT = hc.PORT, LIVE_LOBBY
    try:
        hc.boot(host, client)
    finally:
        hc.PORT = old
    ev["bootS"], raised = round(time.time() - t0, 1), None
    ev["slowOn"] = client.cmd(dict(SLOW_ON))
    try:
        hc.row_host_kill(host, client, {})
    except AssertionError as e:
        raised = str(e)
    finally:
        ev["slowOff"] = safe(lambda: client.cmd({"cmd": "slow_top", "off": True}))
        r.dump = {gc.name: safe(lambda gc=gc: session.event_state(gc)) for gc in r.machines}  # CAPTURE's state
        ev["killS"] = round(time.time() - t0 - ev["bootS"], 1)
    es = r.dump["client"] if isinstance(r.dump["client"], dict) else {}
    mine = [x for x in ((es.get("displayTwo") or {}).get("death") or {}).get("ring") or [] if x.get("unit") == hc.A_ID]
    rec = mine[-1] if mine else {}
    ds, mg = rec.get("dirsShown"), rec.get("maxGapMs")
    ev["record"] = {"recordsForA": len(mine), "seq": rec.get("seq"), "dirsShown": ds,
                    "leftOut": [d for d in hc.DIRS_4_TO_3 if d not in (ds or [])],
                    "phasesShown": rec.get("phasesShown"), "maxGapMs": rec.get("maxGapMs", "absent"),
                    "holdMs": rec.get("holdMs"), "endedBy": rec.get("endedBy")}
    ev["raised"] = raised
    slow_off = ev["slowOff"].get("slow") or {} if isinstance(ev["slowOff"], dict) else {}
    parts = raised.split("; ") if raised is not None else []
    r.guards([("boot", True, ev["bootS"]),
              ("slow_top armed", (ev["slowOn"].get("slow") or {}).get("armed") is True, ev["slowOn"]),
              ("slowedPasses >= 20 after", (slow_off.get("slowedPasses") or 0) >= 20, ev["slowOff"]),
              ("exactly one client death record for A, endedBy out", len(mine) == 1 and rec.get("endedBy") == "out",
               ev["record"]),
              ("its dirsShown != DIRS_4_TO_3 (the stall left octants out)",
               isinstance(ds, list) and ds != hc.DIRS_4_TO_3, ev["record"]),
              ("every raised part is host_kill_death's death record",
               all(p.startswith(DEATH_FAIL_PREFIX) for p in parts), parts)])
    r.cell("record_has_gap: the client's death record carries maxGapMs, an int >= 50 (every client frame >= 50 ms)",
           isinstance(mg, int) and not isinstance(mg, bool) and mg >= 50, ev["record"],
           "the client's death record has no maxGapMs")
    r.cell("kill_check_passes: row_host_kill passes host_kill_death (its left-out octants are whole windows one "
           "frame gap spans)", raised is None,
           raised, "host_kill_death failed a death record whose left-out octants the client's frame stall explains")

# ---- failed_bringup_reaps: run_alien_turn_kill's bring-up fails after both games joined the lobby ----
BRINGUP_RAISE = "stand-in: the bring-up failed after both games joined the lobby"

def row_failed_bringup_reaps(r):
    st = r.ev["standIn"] = {"fired": 0, "pids": None}
    orig, t0, exc, seen = pause_on_leave.sid.bring_up_lobby, time.time(), None, []

    def stand_in(host, client, port):  # what _alien_turn_bring_up calls: the real lobby dance, then the failure
        seen[:] = [host, client]
        orig(host, client, port)
        st["fired"] += 1
        st["pids"] = {gc.name: gc.proc.pid if gc.proc else None for gc in seen}
        raise RuntimeError(BRINGUP_RAISE)

    pause_on_leave.sid.bring_up_lobby = stand_in
    try:
        pause_on_leave.run_alien_turn_kill()
    except (Exception, SystemExit) as e:
        exc = e
    finally:
        pause_on_leave.sid.bring_up_lobby = orig
    found = [gc for gc in (spawned_by(exc, pause_on_leave._alien_turn_bring_up) if exc is not None else [])
             if gc is not None]
    r.machines = found or list(seen)  # read before any cleanup; exec_row then shuts down what still runs
    alive = {gc.name: gc.proc is not None and gc.proc.poll() is None for gc in r.machines}
    r.ev.update(exc="%s: %s" % (type(exc).__name__, exc) if exc is not None else "run_alien_turn_kill returned",
                alive=alive,
                rc={gc.name: gc.proc.poll() if gc.proc else None for gc in r.machines},
                raiseS=round(time.time() - t0, 1))
    r.guards([("the stand-in fired once", st["fired"] == 1, st),
              ("run_alien_turn_kill raised the stand-in's RuntimeError",
               type(exc) is RuntimeError and str(exc) == BRINGUP_RAISE, r.ev["exc"]),
              ("two machines, each with a proc", len(found) == 2 and all(gc.proc is not None for gc in found),
               [gc.name for gc in found])])
    left = [n for n, a in alive.items() if a]
    r.cell("both_games_shut: run_alien_turn_kill's failed bring-up shut both games down", not left, alive,
           "run_alien_turn_kill's bring-up failed with both games running and left %s running" % " and ".join(left))
ROWS = (("timelog_exit_codes", row_timelog_exit_codes), ("turn_stall_spanned", row_turn_stall_spanned),
        ("fall_stall_spanned", row_fall_stall_spanned), ("death_stall_spanned", row_death_stall_spanned),
        ("live_death_stall", row_live_death_stall), ("refused_teleport_stops", row_refused_teleport_stops),
        ("failed_bringup_reaps", row_failed_bringup_reaps))

def capture(r):
    if r.rid == "timelog_exit_codes":
        return {"tmp": r.tmp, "children": getattr(r, "childCapture", None)}
    if r.rid in ("turn_stall_spanned", "fall_stall_spanned", "death_stall_spanned"):
        return {"cellFails": r.ev.get("cellFails")}
    dirs = [gc.user_dir for gc in r.machines] or [os.path.join(harness.TEST_ROOT, "s%d_pause_alien_turn_%s" % (
        harness.HARNESS_SLOT, m)) for m in ("host", "client")]
    return {"standIn": r.ev.get("standIn"), "exit": r.ev.get("exit"), "eventState": getattr(r, "dump", None),
            "logTails": {os.path.basename(d): tail(os.path.join(d, "openxcom.log")) for d in dirs}}
def exec_row(rid, fn):
    r, t0 = Row(rid), time.time()
    try:
        fn(r)
    except GuardMiss as e: r.err = "GUARD %s" % e
    except Exception as e: r.err = "%s: %s" % (type(e).__name__, short(str(e), 800))
    # every machine down before the next row (run_alien_turn_kill shuts its own; a boot miss leaves them up)
    for gc in r.machines:
        if gc.proc is not None and gc.proc.poll() is None:
            safe(gc.shutdown)
    if rid in ("refused_teleport_stops", "live_death_stall") and r.err and "bootS" not in r.ev:
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
    print("\ntest_harness_truth: %d/%d passed (pass=%s fail=%s) in %.1fs" % (
        len(passed), len(order), passed, failed, time.time() - t0), flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
