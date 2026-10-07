"""W2-H21e (F9587 routed; spec rewrite/prompts/w2h21e_briefing_battle_reads.md (f), QH21e-2 a, QH21e-4 a, QH21e-5 a; TASK 0
rewrite/w2h21e-task0/CONSTANTS.md): a real co-op battle exists before its battle screen does. The host's BattlescapeState is built only
at its briefing's OK, so while the host reads its briefing SavedBattleGame::getBattleGame() reads a null BattlescapeState. Two co-op
paths read it there: the chat box's camera line (ChatMenu::draw, F9633) and the host's COOP_READY_CLIENT answer after the second
player adopts a streamed world (connectionTCP::onTCPMessage, F9634). Both kill the host (TASK 0 2/2 each).
  Row H21e-C1 (named RED; F9633) skirmish, boots w2h21efc1..3 (GameClient host 49602 / client 49603, lobby port "46990"):
    roster-pinned lobby + bring_up_to_briefings (seat_count 2); within W_BATTLE the client's BriefingState over its BattlescapeState;
    host non-vacuity: top BriefingState, no BattlescapeState on its stack, isPreview false, has_battle true, chatMenuExists on both;
    GUARD: the client's keyChat in its briefing (a live screen) -> chatActive true within W, alive HOLD s later, keyChat again ->
    chatActive false; trigger: the host's keyChat (inject_input ok); effect: the host's chatActive true within W.
  Row H21e-R1 (named RED; F9634) SHARED, boots w2h21efr1..3 (shared_fixture.bring_up ports 49606 / 49607 / 46992): the setup guard
    (test_w2_practice_rejoin.boot); bring_up_shared_mixed_battle(js, None, to_tactical=False); within W_BATTLE the client holds
    BattlescapeState AND BriefingState and its CL has `battle_offer accepted`; host non-vacuity as C1; trigger: the client's
    force_resync (role replica, sent true); HL `streaming authoritative world to client` and no `streamer busy` drop; effect: CL_ADOPT
    in order within W. The client's fate after its re-adoption (alive, top; F9646) is recorded, never a cell.
  Cells per row: G per boot (setup, both briefings, non-vacuity, trigger sent); GUARD in every C1 construction; non-vacuity: every
    surviving host reached its effect; RED: no host death in N constructions (TASK 0: C1 2/2, the host died 50-51 ms after keyChat,
    getBattleGame <- ChatMenu::draw; R1 2/2, 1.56-1.86 s after force_resync, getBattleGame <- onTCPMessage at connectionTCP.cpp :36892).
W = 10 s at POLL 0.25 s, HOLD = 2 s, SETTLE 0.3 s before every key (F2888), N = 3 fresh boots per row, W_BATTLE = 90 s. alive(gc) = the
process runs and `ping` answers. CRASH = new crashlogs/crash_*.log since the construction started (first 4 frames). HL / CL = the host's /
client's openxcom.log. A machine that died on the RED trigger (and R1's client) is tolerated at shutdown. EVIDENCE before each verdict;
a failed row prints ONE CAPTURE line per failed construction (both stacks, get_coop / world_state / battle_state on both, HL / CL tails,
CRASH); every row runs after a failure; ONE run (WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_w2_host_combat as hc  # noqa: E402  (main-guarded: bring_up_lobby_roster_pinned)
import test_w2_practice_rejoin as prj  # noqa: E402  (main-guarded: X, boot, q, stack, wait_until, short, pr, cr)
import test_w2_practice_save_quit as sq  # noqa: E402  (main-guarded: CL_ADOPT)
from harness import GameClient, make_user_dir  # noqa: E402

W, POLL, HOLD, SETTLE, N, W_BATTLE = 10.0, 0.25, 2.0, 0.3, 3, 90.0
BRF, BS = "BriefingState", "BattlescapeState"
PORTS_C1, PORTS_R1 = (49602, 49603, "46990"), (49606, 49607, 46992)
ACCEPT = "[coop-handshake] battle_offer accepted"
STREAM, BUSY = "[coop-shared] streaming authoritative world to client", "[coop-shared] resync request dropped: streamer busy"
pr, q, stack, wait_until, short = prj.pr, prj.q, prj.stack, prj.wait_until, prj.short
RED_C1 = ("named red: TASK 0 2/2 the host died 50-51 ms after its keyChat in its briefing, BattlescapeState::getBattleGame <- "
          "ChatMenu::draw (ChatMenu.cpp :245) <- Game::run")
RED_R1 = ("named red: TASK 0 2/2 the host died 1.56-1.86 s after the client's force_resync in the host's briefing, "
          "BattlescapeState::getBattleGame <- connectionTCP::onTCPMessage (connectionTCP.cpp :36892, COOP_READY_CLIENT) <- updateCoopTask")


class Row(pr.Row):
    """pr.Row with one CAPTURE line per failed construction, printed after the EVIDENCE line"""
    def __init__(self, rid, task0):
        super().__init__(rid, task0)
        self.caps = []

    def report(self, results):
        self.evidence()
        for tag, cap in self.caps:
            print(f"CAPTURE {self.rid} {tag}: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def snap(gc):
    """one machine's CAPTURE entry"""
    if gc is None:
        return "<absent>"
    if not pr.alive(gc):
        return {"dead": True, "rc": gc.proc.poll() if gc.proc else None}
    co, bs = q(gc, {"cmd": "get_coop"}), q(gc, {"cmd": "battle_state"})
    return {"stack": stack(gc), "get_coop": {k: co.get(k) for k in ("inBattle", "lobbyMode", "localSeat", "coopSession", "coopDialog")},
            "world_state": {k: v for k, v in q(gc, {"cmd": "world_state"}).items() if k in ("has_battle", "has_save", "error")},
            "battle_state": {k: bs.get(k) for k in ("isPreview", "phase", "turn", "chatActive", "chatMenuExists", "error")}}


def tail(gc):
    return [ln.split("\t")[-1][:200] for ln in pr.log_lines(gc)[-20:]] if gc is not None else []


def capture(x, crash):
    return {"host": snap(x.host), "client": snap(x.client), "HL": tail(x.host), "CL": tail(x.client), "CRASH": crash}


def chat_on(gc):
    return q(gc, {"cmd": "battle_state"}).get("chatActive")


def press_chat(gc):
    """keyChat as this process wrote it to its options.cfg, SETTLE s after the last input (F2888)"""
    key = prj.cr.read_key(gc.user_dir, "keyChat")
    time.sleep(SETTLE)
    return dict(q(gc, {"cmd": "inject_input", "kind": "key", "key": key}), key=key)


def guard(r, tag, gc, where):
    """GUARD: gc's keyChat on a live screen -> chatActive true within W, alive HOLD s later; keyChat again -> chatActive false"""
    a = press_chat(gc)
    on = a.get("ok") is True and bool(wait_until(lambda: chat_on(gc) is True, W))
    time.sleep(HOLD)
    al = pr.alive(gc)
    b = press_chat(gc) if al else {}
    off = b.get("ok") is True and bool(wait_until(lambda: chat_on(gc) is False, W))
    rec = {"open": a, "chatActive true": on, "alive": al, "close": b, "chatActive false": off}
    return r.cell(f"GUARD: {tag} the {gc.name}'s keyChat {where} -> chatActive true within {W:.0f} s, alive {HOLD:.0f} s later, "
                  f"keyChat again -> chatActive false", on and al and off, rec), rec


def watch(gc, t1, effect):
    """poll gc until it dies, its effect (seen within W) held HOLD s, or W + HOLD s passed -> (effect seen, death ms or None)"""
    t_eff = None
    while True:
        now = time.time()
        if not pr.alive(gc):
            return t_eff is not None, round((time.time() - t1) * 1000)
        if t_eff is None and now - t1 <= W and effect():
            t_eff = now
        if (t_eff and now - t_eff >= HOLD) or (not t_eff and now - t1 >= W + HOLD):
            return t_eff is not None, None
        time.sleep(POLL)


def host_nv(r, x, rec):
    """the host in its briefing: top BriefingState, no BattlescapeState, isPreview false, has_battle true; chatMenuExists on both"""
    bs = q(x.host, {"cmd": "battle_state"})
    rec["host"] = v = {"stack": stack(x.host), "isPreview": bs.get("isPreview"), "phase": bs.get("phase"),
                       "has_battle": q(x.host, {"cmd": "world_state"}).get("has_battle"),
                       "chatMenuExists": [bs.get("chatMenuExists"), q(x.client, {"cmd": "battle_state"}).get("chatMenuExists")]}
    ok = (v["stack"][-1:] == [BRF] and BS not in v["stack"] and v["isPreview"] is False and v["has_battle"] is True
          and v["chatMenuExists"] == [True, True])
    return r.cell(f"G: {x.tag} host non-vacuity: top {BRF}, no {BS} on its stack, isPreview false, has_battle true, chatMenuExists on "
                  f"both", ok, v)


def boot_skirmish(r, x, rec, ports, pre_ok=None):
    """two GameClients, the roster-pinned lobby, bring_up_to_briefings (the host's briefing up, nothing closed)"""
    try:
        x.host = GameClient("host", ports[0], make_user_dir(x.tag + "_host"))
        x.client = GameClient("client", ports[1], make_user_dir(x.tag + "_client"))
        hc.bring_up_lobby_roster_pinned(x.host, x.client, ports[2])
        session.bring_up_to_briefings(x.host, x.client, {}, seat_count=2, pre_ok=pre_ok)
        return True
    except Exception as e:
        return r.cell(f"G: {x.tag} boot", False, short(e, 600))


def boot_shared(r, x, rec):
    """test_w2_practice_rejoin.boot's SHARED bring-up + setup guard"""
    tmp = pr.Row("boot", None)
    ok = prj.boot(tmp, x, PORTS_R1, False)
    rec["setup"] = tmp.ev.get("setup " + x.tag)
    return ok or r.cell(f"G: {x.tag} boot", False, [tmp.fails, tmp.cap])


def c1(r, x, rec):
    """C1 up to the trigger -> (trigger time, effect) or None"""
    h, c = x.host, x.client
    both = wait_until(lambda: BS in stack(c) and stack(c)[-1:] == [BRF], W_BATTLE, 0.5)
    rec["client"] = stack(c)
    if not r.cell(f"G: {x.tag} the client's {BRF} over its {BS} within {W_BATTLE:.0f} s", both, rec["client"]):
        return None
    if not host_nv(r, x, rec):
        return None
    ok, rec["GUARD"] = guard(r, x.tag, c, "in its briefing (a live BattlescapeState under it)")
    if not ok:
        return None
    rec["stacks before trigger"] = {"host": stack(h), "client": stack(c)}
    rec["trigger"] = rep = press_chat(h)
    t1 = time.time()
    if not r.cell(f"G: {x.tag} the host's keyChat sent", rep.get("ok") is True, rep):
        return None
    return t1, lambda: chat_on(h) is True


def r1(r, x, rec):
    """R1 up to the trigger -> (trigger time, effect) or None"""
    h, c = x.host, x.client
    try:
        session.bring_up_shared_mixed_battle(x.js, None, to_tactical=False)
    except Exception as e:
        r.cell(f"G: {x.tag} bring_up_shared_mixed_battle", False, short(e, 600))
        return None
    both = wait_until(lambda: BS in stack(c) and BRF in stack(c), W_BATTLE, 0.5)
    acc = any(ACCEPT in ln for ln in pr.log_lines(c))
    rec["client"] = stack(c)
    if not r.cell(f"G: {x.tag} the client holds {BS} and {BRF} within {W_BATTLE:.0f} s, CL `{ACCEPT}`", both and acc, [rec["client"], acc]):
        return None
    if not host_nv(r, x, rec):
        return None
    x.n_cl, x.n_hl = pr.log_size(c), pr.log_size(h)
    rec["stacks before trigger"] = {"host": stack(h), "client": stack(c)}
    rec["trigger"] = rep = q(c, {"cmd": "force_resync"})
    t1 = time.time()
    if not r.cell(f"G: {x.tag} the client's force_resync (role replica, sent true)", rep.get("role") == "replica" and rep.get("sent") is True,
                  rep):
        return None
    return t1, lambda: pr.in_order(pr.log_lines(c, x.n_cl), sq.CL_ADOPT)


def r1_after(r, x, rec):
    """R1: the stream went out (no streamer-busy drop); the client's fate is recorded (F9646), never a cell"""
    hl = [ln.split("\t")[-1][:160] for ln in pr.log_lines(x.host, x.n_hl) if STREAM in ln or BUSY in ln]
    rec["CL_ADOPT"] = pr.in_order(pr.log_lines(x.client, x.n_cl), sq.CL_ADOPT)
    time.sleep(0.5)
    rec["client fate"] = {"alive": pr.alive(x.client), "stack": stack(x.client) if pr.alive(x.client) else "<dead>"}
    r.cell(f"G: {x.tag} HL `{STREAM}` and no streamer-busy drop", any(STREAM in ln for ln in hl) and not any(BUSY in ln for ln in hl), hl)


def shut(r, x, tolerate):
    """every machine of the construction; a machine named in `tolerate` may fail its shutdown (its CRASH is the evidence)"""
    for gc in (x.client, x.host):
        if gc is None:
            continue
        try:
            gc.shutdown()
        except Exception as e:
            if gc.name in tolerate:
                r.ev.setdefault("shutdown tolerated", []).append(f"{x.tag} {gc.name}: {short(e, 160)}")
            else:
                r.cell(f"{x.tag} shutdown ({gc.name})", False, short(e, 300))


def count_row(rid, base, task0, boot, construct, watched, results, walls, after=None, always=()):
    """N fresh boots: boot, construct up to the trigger, watch `watched` (host / client); a death is one count"""
    t0, r, deaths, recs = time.time(), Row(rid, task0), 0, []
    for k in range(1, N + 1):
        x, rec, died, n_f, tk = prj.X(f"{base}{k}"), {"boot": f"{base}{k}"}, False, len(r.fails), time.time()
        before = pr.crash_names()
        try:
            t = boot(r, x, rec) and construct(r, x, rec)
            if t:
                rec["effect"], dms = watch(getattr(x, watched), t[0], t[1])
                died = dms is not None
                if died:
                    time.sleep(1.0)  # the crash handler's files
                rec.update({watched + " died ms": dms, "CRASH": pr.crash_info(before)})
                deaths += died
                if after:
                    after(r, x, rec)
        except Exception as e:
            r.cell(f"G: {x.tag} exception", False, short(e))
        if died or len(r.fails) > n_f:
            r.caps.append((x.tag, capture(x, rec.get("CRASH") or pr.crash_info(before))))
        shut(r, x, set(always) | ({watched} if died else set()))
        rec["wall s"] = round(time.time() - tk, 1)
        recs.append(rec)
    r.ev["constructions"] = recs
    r.cell(f"non-vacuity: every surviving {watched} reached its effect",
           all(c.get("effect") for c in recs if c.get(watched + " died ms", 0) is None), [c.get("effect") for c in recs])
    r.cell(f"RED: no {watched} death in {N} constructions", deaths == 0, f"{deaths}/{N} died")
    walls[rid] = r.ev["wall s"] = round(time.time() - t0, 1)
    r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    count_row("H21e-C1", "w2h21efc", RED_C1, lambda r, x, rec: boot_skirmish(r, x, rec, PORTS_C1), c1, "host", results, walls)
    count_row("H21e-R1", "w2h21efr", RED_R1, boot_shared, r1, "host", results, walls, after=r1_after, always=("client",))
    rows = ("H21e-C1", "H21e-R1")
    failed = [rid for rid in rows if not results.get(rid)]
    print(f"\ntest_w2_briefing_battle_reads: {len(rows) - len(failed)}/{len(rows)} passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
