"""W2-H24 R-H24-G-1 / R-H24-G-2 (spec rewrite/prompts/w2h24_failed_battle_start.md ORCHESTRATOR RULINGS; TASK 0 in docs
rewrite/w2-resume-813981be/reports/w2h24x.md): a partner lost during a CAMPAIGN stage-2 offer does not take W2-H24's failed-start
unwind. A stage-2 offer (MG-A's multi-stage hand-off, hook H) is not a fresh start for coopUnwindFailedStart(): that helper is for a
fresh campaign landing (S-A, test_w2_failed_battle_start.py). This row guards only that the helper stays out of a stage-2 start: no
UNWIND line, no craft sent home and no battle mark cleared by it. What a failed stage-2 start does instead (the host's screens, the
world, the rejoin) is owned by MG-A's follow-up row, not by this file.

ONE boot: test_w2_multistage_campaign.py's boot D (SHARED campaign Cydonia, set_seed 1 right before confirm_cydonia, the stage-1
spine, pins, pin_ai_neutral, hash clean) on lobby key KEY, imported as-is. Then MS5's stage-1 kill-all trigger (the kill-all route as
MS1; test_w2_multistage_end.py's stage_guards, kill_all, close_end_turn - MS1's own ms1_trigger pins boot A's seats). The client arms
hold_battle_ready right before the host's NextTurnState close, so the host stays in phase Handshake on the stage-2 offer (battleId 2)
and the client holds its battle_ready; then client.kill() (TASK 0: the -2 receive path, the first host poll after the kill reads
phase Idle); the host is observed for W.

  S2X  S2X-1 GUARD stage-2 offer out (precondition): every stage-1 guard empty, the host's stage record emitted 1 / toBattleId 2 /
       nextStage STR_MARS_THE_FINAL_ASSAULT at the close, host log +1 "stage hand-off - battle 1 -> 2 offered (stageOf)" and +1
       "battle_offer sent (battleId=2", host phase Handshake battleId 2, the client's battle_ready held.
       S2X-2 RED no failed-start unwind: UNWIND lines after the kill = 0 (red today: 1, "(partner dropped) unwound - battle marks
       cleared=1, crafts sent home=0", TASK 0 2/2).
       S2X-3 GUARD craft not sent home by the helper: SKY (the host's geo_state entries of CRAFT_D: status, destKind, destId) at +W
       equals its pre-kill value. A guard, never red (ruling R-H24x-1 a): on every Cydonia route the craft has no destination
       (STR_READY, none, -1), so the helper's send-home branch cannot fire ("crafts sent home=0" today); it stays as a regression guard
       that nothing in a failed stage-2 start touches the craft.
       S2X-4 RED battle marks not cleared by the helper: MARKS count at +W equals the pre-kill count (TASK 0: 1,
       bases/crafts/inBattlescape; red today: 0).
       S2X-5 GUARD CRASH 0.
W = 15 s, POLL = 0.2 s. SKY = host geo_state crafts with id CRAFT_D. MARKS = host save_game, then the file's "inBattlescape: true"
lines with their key paths. UNWIND = host log lines with "W2-H24: failed battle start (" since the kill. CRASH =
session._crash_log_snapshot() delta at the row's end. A failed S2X-1 ends the row (later cells "not reached"). EVIDENCE before each
verdict; a failed row prints ONE CAPTURE line; WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every
cell passes, else 2. Red (commit A, the unchanged build): FAIL S2X-2 and S2X-4; S2X-1, S2X-3, S2X-5 pass.

Run:  python tools/coop_test/test_w2_stage2_failed_start.py
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import test_w2_multistage_campaign as ms5  # noqa: E402
from test_w2_multistage_end import stage_guards, kill_all, close_end_turn  # noqa: E402

KEY = "48586"
W, POLL = 15.0, 0.2
UNWIND = "W2-H24: failed battle start ("
HANDOFF, OFFER2 = "stage hand-off - battle 1 -> 2 offered (stageOf)", "battle_offer sent (battleId=2,"
MISSION_FINAL = "STR_MARS_THE_FINAL_ASSAULT"


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def rc(gc):
    return None if gc.proc is None else gc.proc.poll()


def stack(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.replace("class OpenXcom::", "") for s in r.get("states", [])] if "states" in r else r


def ev(gc):
    try:
        e = session.event_state(gc)
    except Exception as ex:
        return {"error": short(ex, 160)}
    return {k: e.get(k) for k in ("phase", "battleId", "desyncSeen", "stage")}


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "error")}


def sky(host):
    g = q(host, {"cmd": "geo_state"})
    out = [{k: c.get(k) for k in ("status", "destKind", "destId")}
           for b in g.get("bases") or [] for c in b.get("crafts") or [] if c.get("id") == ms5.CRAFT_D]
    return out or {"missing craft": ms5.CRAFT_D, "error": g.get("error")}


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]


def marks(host, fname):
    """host save_game (a direct SavedGame::save), then every `inBattlescape: true` line with its key path"""
    rep, path, out, keys = q(host, {"cmd": "save_game", "file": fname}), os.path.join(host.user_dir, "xcom1", fname), [], []
    if rep.get("ok") is not True or not os.path.exists(path):
        return {"reply": rep, "file": "missing", "flags": None}
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, s in enumerate((ln.rstrip("\r\n") for ln in f), 1):
            ind, body = len(s) - len(s.lstrip(" ")), s.strip()
            if not body or body.startswith("#"):
                continue
            if body.startswith("- "):
                ind, body = ind + 2, body[2:]
            while keys and keys[-1][0] >= ind:
                keys.pop()
            m = re.match(r"([A-Za-z_][A-Za-z0-9_]*):", body)
            keys += [(ind, m.group(1))] if m else []
            out += ["%d %s" % (n, "/".join(k for _, k in keys))] if "inBattlescape: true" in s else []
    return {"reply": rep.get("ok"), "flags": out}


class Row:
    def __init__(self, rid, cells):
        self.rid, self.cells, self.fails, self.done = rid, cells, [], set()

    def cell(self, cid, kind, label, ok, evid):
        print("EVIDENCE %s: %s" % (cid, json.dumps(evid, sort_keys=True, default=str)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        print("EVIDENCE %s stop: %s" % (self.rid, why), flush=True)
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)


def row_s2x(host, client, crash0, ctx):
    r = Row("S2X", ["S2X-1", "S2X-2", "S2X-3", "S2X-4"])
    try:
        g = []
        stage_guards(host, client, ctx, g)
        kill_all(host, client, ms5.ALIENS_D, g, "stage 1")
        ctx["hold"] = q(client, {"cmd": "hold_battle_ready", "on": True})
        n_h = len(log(host))
        close_end_turn(host, client, g)
        ctx["hostStageAtClose"] = ev(host).get("stage")
        t1, held, he = time.time(), None, {}
        while time.time() - t1 < 30.0:
            he, held = ev(host), q(client, {"cmd": "hold_battle_ready"}).get("held")
            if he.get("phase") == "Handshake" and he.get("battleId") == 2 and held is True:
                break
            time.sleep(POLL)
        hs = ctx["hostStageAtClose"] if isinstance(ctx["hostStageAtClose"], dict) else {}
        handoff, offer2 = since(host, n_h, HANDOFF), since(host, n_h, OFFER2)
        ok1 = (not g and ctx["hold"].get("armed") is True and hs.get("emitted") == 1 and hs.get("toBattleId") == 2
               and hs.get("nextStage") == MISSION_FINAL and len(handoff) == 1 and len(offer2) == 1
               and he.get("phase") == "Handshake" and he.get("battleId") == 2 and held is True)
        r.cell("S2X-1", "GUARD", "stage-2 offer out: stage-1 guards empty, host stage emitted 1 / toBattleId 2 / nextStage %s at the close, "
               "host log +1 hand-off and +1 battle_offer sent (battleId=2), host phase Handshake battleId 2, client battle_ready held"
               % MISSION_FINAL, ok1, {"guards": g, "hold": ctx["hold"], "hostStageAtClose": hs, "handoff": handoff, "offer2": offer2,
                                      "host": he, "held": held, "s to the window": round(time.time() - t1, 2)})
        if not ok1:
            raise RuntimeError("S2X-1 (precondition) failed")
        ctx["SKY0"], ctx["MARKS0"] = sky(host), marks(host, "w2h24x_s2x_prekill.sav")
        n_k = len(log(host))
        client.kill()
        tk, polls = time.time(), []
        ctx["first"] = dict({k: v for k, v in ev(host).items() if k != "stage"}, t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append([round(time.time() - tk, 2), stack(host), ev(host).get("phase"), dlg(host).get("code")])
            time.sleep(POLL)
        ctx["after"] = [p for i, p in enumerate(polls) if i == 0 or p[1:] != polls[i - 1][1:]]
        unw, s1, m1 = since(host, n_k, UNWIND), sky(host), marks(host, "w2h24x_s2x_after.sav")
        ctx["UNWIND"], ctx["SKY1"], ctx["MARKS1"] = unw, s1, m1
        path = {"first poll after the kill": ctx["first"],
                "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(ctx["first"].get("phase"), "?"),
                "host after": ctx["after"]}
        r.cell("S2X-2", "RED", "no failed-start unwind: UNWIND lines after the kill = 0 (red today: 1, TASK 0)", not unw,
               {"UNWIND": unw, "path": path})
        r.cell("S2X-3", "GUARD", "craft not sent home by the helper: SKY at +%.0f s equals its pre-kill value (never red: the Cydonia "
               "craft has no destination, crafts sent home=0 today)" % W,
               isinstance(ctx["SKY0"], list) and s1 == ctx["SKY0"], {"pre-kill": ctx["SKY0"], "after": s1})
        n0 = len(ctx["MARKS0"].get("flags") or [])
        r.cell("S2X-4", "RED", "battle marks not cleared by the helper: MARKS count at +%.0f s equals the pre-kill count (TASK 0: 1)" % W,
               ctx["MARKS0"].get("flags") is not None and m1.get("flags") is not None and n0 > 0 and len(m1["flags"]) == n0,
               {"pre-kill": ctx["MARKS0"], "after": m1})
    except Exception as e:  # the precondition, or a lever / kill() that raised: the row ends here
        r.stop(short(e))
    new = sorted(session._crash_log_snapshot() - crash0)
    r.cell("S2X-5", "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new, new)
    if r.fails:
        live = [(gc.name, gc) for gc in (host, client) if gc.proc is not None and gc.proc.poll() is None]
        cap = {"stacks": {n: stack(gc) for n, gc in live}, "event": {n: ev(gc) for n, gc in live},
               "host dialog": dlg(host) if rc(host) is None else None, "host rc": rc(host),
               "HL": [ln.split("\t")[-1][:200] for ln in log(host) if "coop-handshake" in ln or "[coop" in ln][-15:]}
        print("CAPTURE S2X: %s" % json.dumps(cap, sort_keys=True, default=str), flush=True)
    print(("PASS S2X" if not r.fails else "FAIL S2X: %s" % " ".join(r.fails)), flush=True)
    return not r.fails


def main():
    t0 = time.time()
    host = GameClient("host", 1, make_user_dir("w2h24x_s2x_host"))
    client = GameClient("client", 2, make_user_dir("w2h24x_s2x_client"))
    crash0, ctx, ok, failed = session._crash_log_snapshot(), {}, False, []
    try:
        ms5.PORT_D = KEY  # boot D on this file's own lobby key (an in-process key linking the host to its client)
        try:
            info = ms5.boot_d(host, client)
            print("[w2h24x] boot D ok: %s (%.1f s)" % (info, time.time() - t0), flush=True)
        except Exception as e:
            print("EVIDENCE S2X boot: %s\nFAIL S2X: boot (FIXTURE-STOP)" % short(e, 600), flush=True)
            info = None
        if info is not None:
            ok = row_s2x(host, client, crash0, ctx)
    finally:
        for gc in (client, host):  # kill() already reaped a killed client
            try:
                if gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown()
            except Exception as e:
                print("FAIL S2X shutdown (%s): %s" % (gc.name, short(e, 300)), flush=True)
                failed.append("shutdown " + gc.name)
    ok = ok and not failed
    print("\ntest_w2_stage2_failed_start: %d/1 rows passed (fail=%s) in %.1fs" % (1 if ok else 0, [] if ok else ["S2X"] + failed,
                                                                                 time.time() - t0), flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
