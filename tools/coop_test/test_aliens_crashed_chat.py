"""A co-op battle that starts with every alien dead ends on vanilla's "all aliens killed" screen (AliensCrashState) on
both machines. The second player's teardown keeps its battle but sets its BattlescapeState to null (connectionTCP.cpp
:37721), so its chat box's camera line (ChatMenu::draw -> SavedBattleGame::getBattleGame()) must not read that screen:
ChatMenu::draw reads it only while isBattlescapeStateLive says it is live (ChatMenu.cpp :244). Without that check the
second player's game died 50-51 ms after its chat key, on 2 of 2 boots.
  Row chat_on_aliens_crashed_screen, skirmish, boots aliens_crashed_chat1..3 (GameClient host 49604 / client 49605, lobby
    port "46991"): the roster-pinned lobby + bring_up_to_briefings (seat_count 2, pre_ok set_seed SEED_MAP 1, as in
    test_prebattle_equip_end); its spine (main-guarded imports): the client's BriefingState within
    CLIENT_BRIEFING_WAIT_S, the host's phase Active within ACTIVE_WAIT_S, the client's close_briefing -> its pre-battle
    screen within ENTRY_WAIT_S; GUARD: the client's keyChat there (a live screen) -> chatActive true within W, alive HOLD
    s later, keyChat again -> chatActive false; stage_aliens (every live alien dead on both, client first); host_close
    (the host's top AliensCrashState); the client applies the host's battle_end within END_WAIT_S; ending_host_ok (the
    host's DebriefingState, resultSent); client non-vacuity: top AliensCrashState within CLIENT_LEAVE_S, no
    BattlescapeState on its stack, has_battle true, isPreview false; trigger: the client's keyChat (inject_input ok);
    effect: its chatActive true within W.
  Cells: G per boot (setup, spine, staging, the endings, non-vacuity, trigger sent); GUARD in every construction;
    non-vacuity: every surviving client reached its effect; FIX: no client death in N constructions (the crash it
    guards: BattlescapeState::getBattleGame <- ChatMenu::draw (ChatMenu.cpp :245) <- Game::run).
W = 10 s at POLL 0.25 s, HOLD = 2 s, SETTLE 0.3 s before every key, N = 3 fresh boots; alive / CRASH / CAPTURE / shutdown
as test_briefing_battle_reads (main-guarded; a client that died on the trigger is tolerated at shutdown). EVIDENCE before
the verdict; a failed row prints ONE CAPTURE line per failed construction; ONE run; exit 0 iff the row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_briefing_battle_reads as bbr  # noqa: E402  (main-guarded: count_row, boot_skirmish, guard, press_chat, chat_on, ...)
import test_prebattle_equip as peq  # noqa: E402  (main-guarded: screen_up)
import test_prebattle_equip_end as pe  # noqa: E402  (main-guarded: its spine pieces, the waits, SEED_MAP)

PORTS = (49604, 49605, "46991")
BRF, BS, ACS = bbr.BRF, bbr.BS, "AliensCrashState"
q, stack, wait_until = bbr.q, bbr.stack, bbr.wait_until
KNOWN_CRASH = ("the crash this row guards: on 2 of 2 boots without the live-screen check, the client died 50-51 ms after its "
               "keyChat on its AliensCrashState, BattlescapeState::getBattleGame <- ChatMenu::draw (ChatMenu.cpp :245) <- "
               "Game::run")


def boot(r, x, rec):
    return bbr.boot_skirmish(r, x, rec, PORTS, pre_ok=lambda gc: gc.ok({"cmd": "set_seed", "seed": pe.SEED_MAP}))


def staged_ok(s):
    sides = [v for side in ("client", "host") for v in (s.get(side) or {}).values()]
    return bool(s.get("ids") and not s.get("error") and sides and all(v.get("ok") and v.get("status") == pe.STATUS_DEAD for v in sides)
                and not s.get("diff") and s.get("liveAfter") == {"host": [], "client": []})


def construct_to_trigger(r, x, rec):
    """The construction up to the trigger -> (trigger time, effect) or None"""
    h, c = x.host, x.client
    t = time.time()
    g0 = wait_until(lambda: BRF in stack(c), pe.CLIENT_BRIEFING_WAIT_S, 0.1)
    d0 = round(time.time() - t, 2)
    g1 = g0 and wait_until(lambda: pe.es(h).get("phase") == "Active", pe.ACTIVE_WAIT_S, 0.1)
    cl = q(c, {"cmd": "close_briefing"}) if g1 else {}
    g2 = bool(cl.get("ok") and wait_until(lambda: peq.screen_up(c), pe.ENTRY_WAIT_S, 0.1))
    rec["spine"] = {"client briefing s": d0 if g0 else None, "host Active": bool(g1), "client close": cl, "screen_up": g2,
                    "host": stack(h), "client": stack(c)}
    if not r.cell(f"guard: {x.tag} spine: the client's {BRF}, the host's phase Active, the client's close_briefing -> its pre-battle screen",
                  g2, rec["spine"]):
        return None
    ok, rec["GUARD"] = bbr.guard(r, x.tag, c, "on its pre-battle screen (a live BattlescapeState under it)")
    if not ok:
        return None
    ctx, ev = {}, {}
    s = pe.stage_aliens(h, c, ctx)
    rec["staged"] = {k: s.get(k) for k in ("ids", "liveAfter", "diff", "error")}
    if not r.cell(f"guard: {x.tag} stage_aliens: every live alien dead on both, buckets equal", staged_ok(s), rec["staged"]):
        return None
    fx = pe.host_close(h, ev)
    ap = not fx and wait_until(lambda: pe.record(c).get("applied") == 1, pe.END_WAIT_S, 0.1)
    rec["host close"] = {"fails": fx, "client applied": bool(ap), "host": stack(h)}
    if not r.cell(f"guard: {x.tag} host_close -> the host's top {ACS}; the client applies its battle_end within {pe.END_WAIT_S:.0f} s", ap,
                  rec["host close"]):
        return None
    pe.ending_host_ok(h, c, ev)
    rec["host ok"] = ho = {k: (ev.get("hostOk") or {}).get(k) for k in ("debriefWithin", "resultSentWithin", "hostStack")}
    if not r.cell(f"guard: {x.tag} ending_host_ok -> the host's DebriefingState, resultSent", ho["debriefWithin"] is not None
                  and ho["resultSentWithin"] is not None, ho):
        return None
    top = wait_until(lambda: stack(c)[-1:] == [ACS], pe.CLIENT_LEAVE_S, 0.1)
    bs = q(c, {"cmd": "battle_state"})
    rec["client"] = v = {"stack": stack(c), "has_battle": q(c, {"cmd": "world_state"}).get("has_battle"), "isPreview": bs.get("isPreview")}
    if not r.cell(f"guard: {x.tag} client non-vacuity: top {ACS} within {pe.CLIENT_LEAVE_S} s, no {BS} on its stack, has_battle true, "
                  f"isPreview false", top and BS not in v["stack"] and v["has_battle"] is True and v["isPreview"] is False, v):
        return None
    rec["stacks before trigger"] = {"host": stack(h), "client": stack(c)}
    rec["trigger"] = rep = bbr.press_chat(c)
    t1 = time.time()
    if not r.cell(f"guard: {x.tag} the client's keyChat sent", rep.get("ok") is True, rep):
        return None
    return t1, lambda: bbr.chat_on(c) is True


def main():
    t0, results, walls = time.time(), {}, {}
    bbr.count_row("chat_on_aliens_crashed_screen", "aliens_crashed_chat", KNOWN_CRASH, boot, construct_to_trigger, "client", results, walls)
    failed = [rid for rid in ("chat_on_aliens_crashed_screen",) if not results.get(rid)]
    print(f"\ntest_aliens_crashed_chat: {1 - len(failed)}/1 passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
