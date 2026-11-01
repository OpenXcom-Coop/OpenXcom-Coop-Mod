"""test_fatal_vote_partner.py: the fatal-wounds vote after a partner's kill (partner_kill_vote) and in PvP (pvp_vote).
Staging, answers, the dismiss_popup rule and the shared assertions: test_fatal_vote.py (whose helpers this file runs).
partner_kill_vote runs on test_client_shoot's snap_kill terror bring-up, pvp_vote on test_battle_end_rules' gm2
boot_pvp.

  partner_kill_vote  the client's own real-UI snap kills the last alien (snap_kill: SEED_MAP 1 terror map, C = 8 with a
      rifle at C_TILE, A = 1000000 at A_TILE with health 1, set_seed SEED_SNAP_KILL right before the click). The 12
      other hostiles die first (one host kill_unit_real each, auto-end still off), then stage_vote turns auto-end on
      and wounds the client's C2 = 9 (client first). Expected: the host never shows the question (it does not vote)
      and opens the vote only after the shot's chain: the open ev's seq > the shot context's bt_action_end seq
      (relations only); host CoopFatalVoteHold + the Wait line naming the client; the client's question (N 1); client
      OK -> close end -> NextTurnState -> battle_end with last_alien_down's battle_end values (measured: the terror
      ending matches them) and the display-only debriefing equal to the host's (the terror debriefing has no fixed
      values; no death-ghost wait is built or asserted).
  pvp_vote  gm2: the host is X-COM (seat 0), the client the aliens (seat 1). GM2_HOST_SOLDIER = 8 wounded; host
      kill_unit_real {faction: 1}. Expected: voters [0] (the alien seat never votes), the host's own question, the
      alien client stays on BattlescapeState with no question while Open and applies the open and close evs; host OK
      -> close end -> NextTurnState -> battle_end -> test_battle_end_rules' pvp_elimination assertion set (the alien
      client's display-only debriefing).

A build whose fatalVote probe answers but that has no vote (one run, exit 2):
  partner_kill_vote  open: host top ConfirmEndMissionState (it asked while the client's chain ran) with no Wait line
      and busyOwnerSeat -1; client top BattlescapeState; both fatalVote records at zero. answer: client OK not
      pressed. close: both fatalVote records at zero. ending: not run.
  pvp_vote  open and close: both fatalVote records at zero. ending: runs and passes; the close-before-battle_end
      line fails.

one run is the result; no skip path, one boot per row. Exit 0 only when both rows pass, 2 otherwise.
run in the foreground to completion.

Run:  python tools/coop_test/test_fatal_vote_partner.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
import test_battle_end as tbe
import test_battle_end_rules as rules
import test_client_shoot as cs
import test_fatal_vote as fvt

ROW_PORT = {"partner_kill_vote": "48547", "pvp_vote": "48548"}
FACTION_HOSTILE = 1
STATUS_DEAD = 6
TERROR_HOSTILES = list(range(1000000, 1000013))   # the terror map's 13 hostiles at boot
GM2_HOST_SOLDIER = 8                              # gm2: X-COM [8..14] all seat 0


def boot_terror(host, client, port):
    """test_client_shoot.boot (the roster-pinned terror bring-up); its lobby key (an inert rendezvous key) is
    pointed at this row's port first."""
    cs.PORT = port
    return cs.boot(host, client)


def shoot_end(host):
    """The bt_action_end seq of the client's shot (the host's closed intent context of kind shoot by C), or None."""
    ends = [x.get("endSeq") for x in event_state(host).get("closedContexts") or []
            if x.get("origin") == "intent" and x.get("kind") == "shoot" and x.get("actorId") == cs.C_ID]
    return ends[-1] if ends else None


def stage_snap_kill(r):
    """The other hostiles killed first, then test_client_shoot's snap_kill staging (without its ghost_option_off
    option toggle and camera_follow camera)."""
    h, c = r.host, r.client
    ae = h.cmd({"cmd": "set_option", "name": "battleAutoEnd"}).get("value")
    hs = battle_state(h)
    hostiles = sorted(u["id"] for u in hs.get("units", []) if u.get("originalFaction") == FACTION_HOSTILE
                      and not u.get("isOut"))
    if ae is not False or hostiles != TERROR_HOSTILES:
        r.fail("pre", f"before the kills: battleAutoEnd {ae!r} (want False), live hostiles {hostiles} "
                      f"(want {TERROR_HOSTILES})")
    kills = {}
    for x in [u for u in hostiles if u != cs.A_ID]:
        resp = h.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": x})
        ok, secs = fvt.wait_until(lambda x=x: ((session.units_by_id(battle_state(h)).get(x) or {}).get("status")
                                               == STATUS_DEAD and battle_state(h).get("pendingStates") == 0), 30, 0.1)
        kills[x] = secs
        if not ok or resp.get("killed") != [x]:
            r.fail("pre", f"kill_unit_real {x} answered {resp}; dead and idle={ok} after {secs}s")
    try:
        session.wait_host_idle(h, c, timeout=30)
    except Exception as e:
        r.fail("pre", f"wait_host_idle after the kills: {fvt.short(e)}")
    staging = {"kills": kills, "aim0": cs.cancel_client_aim(c),
               "rifle": cs.give_both(h, c, cs.C_ID, "STR_RIFLE", "STR_RIFLE_CLIP"),
               "C": cs.place(h, c, cs.C_ID, cs.C_TILE, cs.SNAP_C_DIR),
               "A": cs.place(h, c, cs.A_ID, cs.A_TILE, cs.A_DIR),
               "Ahealth": cs.both(h, c, {"cmd": "battle_set_unit_state", "unit": cs.A_ID, "health": cs.A_HEALTH},
                                  ("health", "stun", "status")),
               "tu": cs.set_tu_both(h, c, cs.C_ID, cs.TU_MAX)}
    cs.set_firing_both(h, c, cs.C_ID)
    r.ev["snapKill"] = staging


def partner_kill_verdict(hrec, crec, cend, hend, b0, cleft, extra, hold, hdeb, cdeb):
    """last_alien_down's battle_end values (measured: the terror ending matches them) and the debriefing checks
    (both shown, the client's display-only and equal to the host's) without fixed values for the host's."""
    f, exp = [], tbe.ROW_EXPECT["last_alien_down"]
    hrec, crec = hrec if isinstance(hrec, dict) else {}, crec if isinstance(crec, dict) else {}
    hdeb, cdeb = hdeb if isinstance(hdeb, dict) else {}, cdeb if isinstance(cdeb, dict) else {}
    hseq = hrec.get("seq")
    for who, rec in (("host", hrec), ("client", crec)):
        for k in ("reason", "aborted", "inExitArea"):
            if rec.get(k) != exp[k]:
                f.append(f"{who} battleEnd.{k}={rec.get(k)!r} (want {exp[k]!r})")
        if tbe.verdicts(rec) != exp["verdicts"] or tbe.tally(rec) != exp["tally"]:
            f.append(f"{who} battleEnd verdicts {rec.get('perSeatVerdict')} tally {rec.get('tally')} (want "
                     f"{exp['verdicts']}, {exp['tally']})")
    for k, want in (("emitted", 1), ("evsAfter", 0), ("actionIdAtEmit", 0)):
        if hrec.get(k) != want:
            f.append(f"host battleEnd.{k}={hrec.get(k)!r} (want {want})")
    if not isinstance(hseq, int) or hseq <= 0 or crec.get("applied") != 1 or crec.get("seq") != hseq:
        f.append(f"battleEnd seq host {hseq} / client applied {crec.get('applied')} seq {crec.get('seq')}")
    hv = crec.get("hashVerify") if isinstance(crec.get("hashVerify"), dict) else {}
    if crec.get("desyncAtTeardown") is not False or hv.get("seq") != hseq or hv.get("kind") != "battle_end":
        f.append(f"client desyncAtTeardown {crec.get('desyncAtTeardown')!r} hashVerify {crec.get('hashVerify')}")
    if not any("DebriefingState" in s for s in hend["stack"]) or hend["desyncSeen"] is not False:
        f.append(f"host stack {hend['stack']} desyncSeen {hend['desyncSeen']}")
    if not cleft["ok"] or cend["top"] != "DebriefingState" or hold != []:
        f.append(f"client end top {cend['top']} (reached {cleft}), host hold {hold} (want DebriefingState, [])")
    for who, deb, disp in (("host", hdeb, False), ("client", cdeb, True)):
        if (deb.get("shown"), deb.get("onTop"), deb.get("displayOnly")) != (True, True, disp):
            f.append(f"{who} debrief_state shown/onTop/displayOnly {deb.get('shown')}/{deb.get('onTop')}/"
                     f"{deb.get('displayOnly')} (want True/True/{disp})")
    for k in tbe.DEBRIEF_FIELDS:
        if tbe.debrief_view(cdeb).get(k) != tbe.debrief_view(hdeb).get(k):
            f.append(f"client debrief_state.{k}={cdeb.get(k)!r} != the host's {hdeb.get(k)!r} "
                     f"(page-2 prefixes stripped)")
    return f + extra


def pvp_elimination_verdict(hrec, crec, cend, hend, b0, cleft, extra, hold, hdeb, cdeb):
    """test_battle_end_rules' pvp_elimination assertion set (measured: the gm2 vote ending matches it)."""
    return rules.row_verdict("pvp_elimination", rules.ROW_EXPECT["pvp_elimination"], hrec, crec, cend, hend, b0, cleft,
                             extra, hold, hdeb, cdeb)


def row_partner_kill_vote(r):
    h, c = r.host, r.client
    stage_snap_kill(r)
    census = fvt.stage_vote(r, [cs.C2_ID], seat_pins=((0, cs.H_ID), (1, cs.C_ID)))
    try:
        r.ev["press"] = cs.aim_click(c, cs.KEY_SNAP, cs.A_TILE,
                                     lambda: h.ok({"cmd": "set_seed", "seed": cs.SEED_SNAP_KILL}))
    except Exception as e:
        r.fail("pre", f"the client's real-UI snap: {fvt.short(e)}")
    ok, trace = fvt.detect_open(r)
    if not ok:
        r.fail("open", f"host top neither {fvt.QUESTION} nor {fvt.HOLD} within {fvt.OPEN_S}s of the click: {trace}")
    r.ev["ghostAtOpen"] = ((event_state(c).get("displayTwo") or {}).get("death") or {}).get("queued")
    got, secs = fvt.wait_until(lambda: shoot_end(h) is not None, fvt.STEP_S, 0.1)
    end_seq = shoot_end(h)
    r.ev["shotEndSeq"] = end_seq
    if end_seq is None:
        r.fail("open", f"the client's shot context never closed on the host ({secs}s)")
    fvt.check_open(r, [1], 1, end_seq or 0, trace)
    if not fvt.answer(r, c, "OK", "answer"):
        r.ending = "the client's OK was not pressed"
    fvt.check_close(r, "end", {1: True}, {"answerSent": "yes", "questionPushed": 1, "questionClosedByClose": 0})
    fvt.ending(r, census, partner_kill_verdict)


def row_pvp_vote(r):
    census = fvt.stage_vote(r, [GM2_HOST_SOLDIER], seat_pins=((0, GM2_HOST_SOLDIER),))
    resp = r.host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": FACTION_HOSTILE})
    r.ev["kill"] = resp
    if not resp.get("ok") or resp.get("killed") != [rules.A_ID]:
        r.fail("pre", f"kill_unit_real faction {FACTION_HOSTILE} answered {resp} (want ok, killed [{rules.A_ID}])")
    ok, trace = fvt.detect_open(r)
    if not ok:
        r.fail("open", f"host top neither {fvt.QUESTION} nor {fvt.HOLD} within {fvt.OPEN_S}s of the kill: {trace}")
    fvt.check_open(r, [0], 1, r.ev["preSeq"] or 0, trace)
    if not fvt.answer(r, r.host, "OK", "answer"):
        r.ending = "the host's OK was not pressed"
    fvt.check_close(r, "end", {0: True}, {"answerSent": "", "questionPushed": 0, "questionClosedByClose": 0})
    fvt.ending(r, census, pvp_elimination_verdict)


ROWS = (("partner_kill_vote", boot_terror, row_partner_kill_vote), ("pvp_vote", rules.boot_pvp, row_pvp_vote))


def main():
    return fvt.run_rows("test_fatal_vote_partner", ROWS, ROW_PORT, "fatal_vote_partner")


if __name__ == "__main__":
    sys.exit(main())
