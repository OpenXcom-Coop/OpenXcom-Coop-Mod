"""MG-A-FS2 / AMENDMENT FS2-A row S2M (owner D282 (b) over H24-VL3, VL-FS2A-2; spec rewrite/prompts/fs2_sa_part2_rearm.md (f), ORCHESTRATOR
RULINGS QA-1..QA-6; TASK 0 rewrite/fs2a-task0/sa/CONSTANTS.md): a partner lost between part 1 and part 2 of a CUSTOM-BATTLE Cydonia,
mid-stream. Part 2 WAITS on the host; the partner rejoins from the server list, RESUME appears, part 2 is offered again and both play
it. Moved here from test_stage2_failed_start.py; its Row / run_boot / CAPTURE helpers are copied from there.

ONE boot (boot M, lobby key KEY, dirs w2fs2a_s2m_host / _client / _client2): test_multistage.py's boot_a (imported, unchanged). The
client arms hold_blob_ack {on: true} (reply armed true) before ms1_trigger, so the host's stage-2 blob waits after its first chunk:
the window W2 (host phase Handshake battleId 2, client hold_blob_ack.held >= 1); client.kill(); the host observed W; client2 rejoins
the custom battle (test_skirmish_flow.skirmish_client_at_browser, then join_tcp with this key and the host's clientName); RESUME; part 2
(session.briefings_to_battlescape(host, client2)).

  S2M-1 GUARD stage-2 offer out (precondition): ms1_trigger guards []; host phase Handshake battleId 2; client hold_blob_ack.held >= 1;
        host log +1 hand-off; PART2(host) mapFingerprint FP2. A failure ends the row.
  S2M-2 RED   PARK +1 and UNWIND +0 (red today: PARK 0).
  S2M-3 GUARD the host waits inside part 2: at W the stack ends [BriefingState, CoopState], dialog 62 backVisible false,
        battle_state.inBattle true, phase Idle, mapFingerprint FP2.
  S2M-4 RED   the rejoin reaches RESUME: host resumeAck true within RJ, RESUME pressed, REJOIN_GUARD +0 (red today: resumeAck never
        true, that line +1).
  S2M-5 RED   part 2 starts for both: within 60 s of RESUME REARM +1 and OFFER +1; the spine to turn 1; PART2 on host and client2:
        phase Active, equal battleId > 2, turn 1, missionType MT2, mapFingerprint FP2, xcom XCOM2; UNWIND 0. With no RESUME it fails at
        once ("no RESUME").
  S2M-6 GUARD CRASH 0.
W = 15 s, POLL = 0.2 s, RJ = 60 s; UNWIND / PARK / REARM / OFFER / PART2 / CRASH as test_stage2_failed_start.py. EVIDENCE before
each verdict; a failed row prints ONE CAPTURE line. ONE foreground run, no skip path; exit 0 only when every
cell passes, else 2. Red (R1, the unchanged build): FAIL S2M-2, S2M-4, S2M-5; every other cell passes. Green (G1): every cell passes.

Run:  python tools/coop_test/test_stage2_custom_rearm.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import test_multistage as ms1  # noqa: E402
from test_multistage import FACTION_PLAYER  # noqa: E402
import test_skirmish_flow as SK  # noqa: E402

KEY = "48585"
W, POLL, RJ = 15.0, 0.2, 60.0
UNWIND, PARK = "W2-H24: failed battle start (", "part 2 waits for the partner"
REARM, OFFER = "MG-A-FS2 - the waiting part 2 re-armed", "battle_offer sent (battleId="
HANDOFF = "stage hand-off - battle 1 -> 2 offered (stageOf)"
REJOIN_GUARD = "offerRejoinBattle() called while the battle is not"
MT2 = "STR_MARS_THE_FINAL_ASSAULT"
FP2 = -5.150191488730903e+18                               # the host's part 2 at the window (TASK 0 Ma = Mb = Mc)
XCOM2 = {8: 1, 9: 1, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0}   # X-COM id -> seat in part 2 (TASK 0 3/3)
NAME = "ClientPlayer"                                      # host get_coop.clientName at bring-up (TASK 0 3/3; read at run time)
BRF, COOP = "BriefingState", "CoopState"


class Stop(Exception):
    """a WAIT timed out: the row ends here"""


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def rc(gc):
    return None if gc is None or gc.proc is None else gc.proc.poll()


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


def coop(gc):
    return {k: v for k, v in q(gc, {"cmd": "get_coop"}).items() if k in ("onConnect", "coopSession", "resumeAck", "coopDialog",
                                                                      "clientName", "error")}


def part2(gc):
    b = q(gc, {"cmd": "battle_state"})
    return {"phase": b.get("phase"), "battleId": (b.get("authority") or {}).get("battleId"), "turn": b.get("turn"),
            "missionType": b.get("missionType"), "mapFingerprint": b.get("mapFingerprint"), "inBattle": b.get("inBattle"),
            "xcom": {u["id"]: u.get("coop") for u in b.get("units") or [] if u.get("faction") == FACTION_PLAYER and not u.get("isOut")},
            "error": b.get("error")}


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]


def wait(desc, pred, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(POLL)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))


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


def part2_cells(r, cid, host, c2, ctx, n_k, spine):
    """S2X-8 / S2M-5: REARM +1 and OFFER +1 within 60 s of RESUME, the spine, PART2 on both, UNWIND 0."""
    if "t_resume" not in ctx:
        return r.cell(cid, "RED", "part 2 starts for both", False, {"no RESUME": True})
    n_r, evd = ctx["n_resume"], {}
    try:
        evd["rearm s"] = wait("REARM and OFFER", lambda: since(host, n_r, REARM) and since(host, n_r, OFFER), 60.0)
        evd["spine"] = spine(host, c2)
    except Exception as e:
        evd["wait"] = short(e, 400)
    hp, cp = part2(host), part2(c2)
    evd.update({"REARM": since(host, n_r, REARM), "OFFER": since(host, n_r, OFFER), "PART2 host": hp, "PART2 client2": cp,
                "UNWIND": since(host, n_k, UNWIND)})
    ok = (len(evd["REARM"]) == 1 and len(evd["OFFER"]) == 1 and "wait" not in evd and not evd["UNWIND"]
          and hp.get("battleId") == cp.get("battleId") and isinstance(hp.get("battleId"), int) and hp["battleId"] > 2
          and all(p.get("phase") == "Active" and p.get("turn") == 1 and p.get("missionType") == MT2 and p.get("mapFingerprint") == ctx["FP2"]
                  and p.get("xcom") == ctx["XCOM2"] for p in (hp, cp)))
    r.cell(cid, "RED", "part 2 starts for both: within 60 s of RESUME REARM +1 and OFFER +1, the spine to turn 1, PART2 host == client2: "
           "Active, battleId > 2, turn 1, %s, mapFingerprint FP2, xcom XCOM2; UNWIND 0 (red today: no RESUME)" % MT2, ok, evd)


def capture(rid, host, ctx):
    live = [(gc.name, gc) for gc in (host, ctx.get("client2")) if gc is not None and rc(gc) is None and gc.proc is not None]
    cap = {n: {"stack": stack(gc), "event": ev(gc), "battle": part2(gc), "coop": coop(gc), "dialog": dlg(gc)} for n, gc in live}
    cap["host rc"] = rc(host)
    cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(host) if "[coop" in ln][-15:]
    print("CAPTURE %s: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)


def run_boot(rid, tag, boot, row, failed):
    """One boot, its row, then every machine shut down (kill() already reaped a killed client) -> the row passed."""
    t0, ok, ctx = time.time(), False, {}
    host = GameClient("host", 1, make_user_dir(tag + "_host"))
    client = GameClient("client", 2, make_user_dir(tag + "_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            info = boot(host, client, ctx)
            print("[w2fs2a] %s boot ok: %s (%.1f s)" % (rid, json.dumps(info, default=str), time.time() - t0), flush=True)
        except Exception as e:
            print("EVIDENCE %s boot: %s\nFAIL %s: boot (FIXTURE-STOP)" % (rid, short(e, 600), rid), flush=True)
            capture(rid, host, {"client2": client})
            info = None
        if info is not None:
            ok = row(host, client, crash0, ctx)
    finally:
        for gc in (ctx.get("client2"), client, host):
            try:
                if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown()
            except Exception as e:
                print("FAIL %s shutdown (%s): %s" % (rid, gc.name, short(e, 300)), flush=True)
                failed.append("%s shutdown %s" % (rid, gc.name))
    return ok


def boot_m(host, client, ctx):
    ms1.PORT_A = KEY  # boot M: MS1's boot A on this file's lobby key
    info = ms1.boot_a(host, client)
    ctx["name"] = coop(host).get("clientName") or NAME
    return dict(info, name=ctx["name"])


def rejoin_custom(host, ctx, n_j, evd):
    """client2 rejoins the custom battle from the server list (test_skirmish_rejoin_battle.rejoin_skirmish's two calls), RESUME"""
    try:
        c2 = ctx["client2"] = GameClient("client2", 3, make_user_dir("w2fs2a_s2m_client2"))
        c2.spawn(); c2.connect()
        SK.skirmish_client_at_browser(c2)
        evd["join_tcp"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": ctx["name"]})
        evd["resumeAck s"] = wait("host resumeAck", lambda: coop(host).get("resumeAck") is True, RJ)
        if session.has_state(host, "Profile"):
            evd["host profile_ok"] = q(host, {"cmd": "profile_ok"})
            time.sleep(0.5)
        ctx["n_resume"] = len(log(host))
        evd["RESUME"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        ctx["t_resume"] = time.time()
    except Exception as e:  # a timed-out wait or a machine gone: S2M-4's own evidence
        evd["wait"] = short(e, 300)
    c2 = ctx.get("client2")
    evd.update({"host coop": coop(host), "host stack": stack(host), "host dialog": dlg(host), "client2 stack": stack(c2) if c2 else None,
                "client2 dialog": dlg(c2) if c2 else None, "rejoin guard": since(host, n_j, REJOIN_GUARD)})
    return evd["host coop"].get("resumeAck") is True and (evd.get("RESUME") or {}).get("ok") is True and not evd["rejoin guard"]


def row_s2m(host, client, crash0, ctx):
    r = Row("S2M", ["S2M-%d" % i for i in range(1, 6)])
    ctx.update({"FP2": FP2, "XCOM2": XCOM2})
    try:
        hold = q(client, {"cmd": "hold_blob_ack", "on": True})
        n_h = len(log(host))
        g = ms1.ms1_trigger(host, client, ctx)
        t1, held, he = time.time(), None, {}
        while time.time() - t1 < 30.0:
            he, held = ev(host), q(client, {"cmd": "hold_blob_ack"}).get("held")
            if he.get("phase") == "Handshake" and he.get("battleId") == 2 and isinstance(held, int) and held >= 1:
                break
            time.sleep(POLL)
        win, hp, handoff = round(time.time() - t1, 2), part2(host), since(host, n_h, HANDOFF)
        ok1 = (not g and hold.get("armed") is True and len(handoff) == 1 and he.get("phase") == "Handshake" and he.get("battleId") == 2
               and isinstance(held, int) and held >= 1 and hp.get("mapFingerprint") == FP2)
        r.cell("S2M-1", "GUARD", "stage-2 offer out (custom battle, mid-stream): ms1_trigger guards [], host Handshake battleId 2, client "
               "hold_blob_ack.held >= 1, host log +1 hand-off, PART2(host) mapFingerprint FP2 %r" % FP2, ok1,
               {"guards": g, "hold": hold, "handoff": handoff, "host": {k: v for k, v in he.items() if k != "stage"}, "held": held,
                "s to the window": win, "hostStack": stack(host), "PART2 host": hp})
        if not ok1:
            raise Stop("S2M-1 (precondition) failed")
        n_k = len(log(host))
        client.kill()
        tk, polls = time.time(), []
        first = dict(ev(host), t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append([round(time.time() - tk, 2), stack(host), ev(host).get("phase"), dlg(host).get("code")])
            time.sleep(POLL)
        park, unw, hs1, d, hp1 = since(host, n_k, PARK), since(host, n_k, UNWIND), stack(host), dlg(host), part2(host)
        path = {"first poll after the kill": {k: v for k, v in first.items() if k != "stage"},
                "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first.get("phase"), "?"),
                "host after": [p for i, p in enumerate(polls) if i == 0 or p[1:] != polls[i - 1][1:]]}
        r.cell("S2M-2", "RED", "PARK +1 and UNWIND +0 (red today: PARK 0)", len(park) == 1 and not unw,
               {"PARK": park, "UNWIND": unw, "path": path})
        r.cell("S2M-3", "GUARD", "the host waits inside part 2: stack ends [BriefingState, CoopState], dialog 62 backVisible false, "
               "inBattle true, phase Idle, mapFingerprint FP2", hs1[-2:] == [BRF, COOP] and d.get("code") == 62
               and d.get("backVisible") is False and hp1.get("inBattle") is True and hp1.get("phase") == "Idle"
               and hp1.get("mapFingerprint") == FP2, {"stack": hs1, "dialog": d, "PART2 host": hp1, "coop": coop(host)})
        evd, n_j = {}, len(log(host))
        r.cell("S2M-4", "RED", "the rejoin reaches RESUME: resumeAck true within %.0f s, RESUME pressed, offerRejoinBattle guard +0 (red "
               "today: resumeAck never true, that line +1)" % RJ, rejoin_custom(host, ctx, n_j, evd), evd)
        part2_cells(r, "S2M-5", host, ctx["client2"], ctx, n_k, lambda h, c: session.briefings_to_battlescape(h, c))
    except Exception as e:  # the precondition, a timed-out wait, or a lever / kill() that raised: the row ends here
        r.stop(short(e))
    new = sorted(session._crash_log_snapshot() - crash0)
    r.cell("S2M-6", "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's baseline)", not new, new)
    if r.fails:
        capture("S2M", host, ctx)
    print(("PASS S2M" if not r.fails else "FAIL S2M: %s" % " ".join(r.fails)), flush=True)
    return not r.fails


def main():
    t0, failed = time.time(), []
    results = {"S2M": run_boot("S2M", "w2fs2a_s2m", boot_m, row_s2m, failed)}
    bad = [rid for rid, ok in results.items() if not ok] + failed
    print("\ntest_stage2_custom_rearm: %d/1 rows passed (fail=%s) in %.1fs" % (sum(results.values()), bad, time.time() - t0),
          flush=True)
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
