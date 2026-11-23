"""test_client_desync_at_battle_end.py: a desync found on the battle's last envelope before `battle_end` does not strand
the second player on the battlescape.

The second player's machine (the client) stops applying the host's battle stream when it finds a desync, reports it,
and waits for the host's automatic repair. In a mission whose objective must be destroyed (objectiveType MUST_DESTROY),
the END TURN after the objective is gone runs BattlescapeGame::endTurn, which sends the hashed `side_transition` and
calls finishBattle (and so `battle_end`) in the same host frame. A desync the client finds on that `side_transition`
reaches the host after its battle has ended (phase no longer Active), and the host skips the repair. The client must
still leave the battle with the host's `battle_end` (to its display-only debriefing); a client that only ever
unfreezes through the repair stays on the frozen battlescape for good.

The only stock MUST_DESTROY deployment, STR_MARS_THE_FINAL_ASSAULT, ends in the win slideshow, whose separate
`cutscene` message moves a frozen client off the battlescape anyway. The Coop_MustDestroy_Test data mod (both
machines) clears its cutscenes, so the battle ends in the debriefing, as a mod's must-destroy mission does.

TWO boots, one row each: a skirmish of STR_MARS_THE_FINAL_ASSAULT with the mod (host set_seed 1 right before
newbattle_ok, two seats, AI pinned neutral), lobby key 48799. The objective counter is set to destroyed on both
machines (field_poke battle objectivesDestroyed 1, restore false, client first: no auto-end cascade), then END TURN
client then host. Each machine closes a NextTurnState whenever one is on top (as its player would). "Leaves the
battlescape" means no BattlescapeState left in that machine's state stack.
  control_no_desync     (control) no client-only change: the host reaches its DebriefingState, the client applies
                        `battle_end` (event_state battleEnd applied 1), leaves the battlescape and shows its
                        DebriefingState.
  desync_at_battle_end  the client alone sets its first soldier's reactions stat to 99 (`battle_action set_stat`)
                        right before the END TURN presses, so it finds the desync on the `side_transition`. The
                        client records the desync (desyncSeen true) and still applies `battle_end`, leaves the battlescape
                        within 60 s of the host's debriefing and shows its DebriefingState.
Every row also asserts no new crash file.

One EVIDENCE line per row, one PASS / FAIL line per row. One run is the result, no skip path. Exit 0 only when every
row passes, else 2. Run it in the foreground to completion.

Run:  python tools/coop_test/test_client_desync_at_battle_end.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import event_state, battle_state  # noqa: E402
import test_host_combat as HC  # noqa: E402

KEY = "48799"
MISSION = "STR_MARS_THE_FINAL_ASSAULT"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_MustDestroy_Test")
SEED_MAP = 1
DEBRIEF_S = 60
CLIENT_LEAVE_S = 60
POKE_REACTIONS = 99                # a client-only reactions value: kept through the side transition, saveBlob
BATTLE_END_KEYS = ("emitted", "applied", "seq", "reason", "lastSeqApplied", "queueDepthAtTeardown")
# a close aimed at a NextTurnState never presses OK on a debriefing that replaced it in between (substring match)
KEEP = ["DebriefingState"]
RESYNC_KEYS = ("desyncs", "offered", "completed", "released", "skipped", "lastSkip", "last", "frozen")


def short(e, n=300):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    return session.top_state(gc)


def probe(gc):
    es = event_state(gc)
    rs = gc.cmd({"cmd": "resync_state"})
    r = (rs.get("resync") or {}) if rs.get("ok") else {"error": rs.get("error")}
    be = es.get("battleEnd") or {}
    return {"top": top(gc), "desyncSeen": es.get("desyncSeen"), "phase": es.get("phase"),
            "queueDepth": es.get("queueDepth"), "lastSeqApplied": es.get("lastSeqApplied"),
            "lastSeqEmitted": es.get("lastSeqEmitted"), "battleEnd": {k: be.get(k) for k in BATTLE_END_KEYS},
            "resync": {k: r.get(k) for k in RESYNC_KEYS if k in r}}


def session_diff(host, client):
    from test_delta_core import diff_buckets
    return diff_buckets(host, client)


def both(host, client, req):
    rc = client.cmd(dict(req))
    rh = host.cmd(dict(req))
    session.wait_seq_barrier(host, client)
    return rh, rc


def wait_until(pred, timeout, interval=0.25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(interval)
    return bool(pred())


def bring_up(host, client, tag):
    HC.bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    pinned = session.pin_ai_neutral(host, client, tag=tag)
    session.wait_host_idle(host, client, timeout=30)
    assert pinned, f"pin_ai_neutral pinned nothing ({pinned})"
    session.assert_hash_clean(host, client, full=True, what=f"{tag} bring-up")


def run_row(rid, corrupt):
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 49910, make_user_dir(f"desync_battle_end_{rid}_host", mods=[MOD_DIR]))
    client = GameClient("client", 49911, make_user_dir(f"desync_battle_end_{rid}_client", mods=[MOD_DIR]))
    ev, fails = {}, []
    try:
        bring_up(host, client, rid)
        rh, rc = both(host, client, {"cmd": "field_poke", "class": "battle", "field": "objectivesDestroyed",
                                     "restore": False, "value": 1})
        ev["objective"] = {"host": {k: rh.get(k) for k in ("ok", "error")},
                           "client": {k: rc.get(k) for k in ("ok", "error")},
                           "mission": battle_state(host).get("missionType")}
        if not (rh.get("ok") and rc.get("ok")):
            fails.append(f"precondition: field_poke objectivesDestroyed answered {ev['objective']}")
        session.assert_hash_clean(host, client, full=True, what=f"{rid} after the objective poke")
        if corrupt:
            uid = min(u["id"] for u in battle_state(client)["units"] if u.get("faction") == 0 and not u.get("isOut"))
            c = client.cmd({"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions",
                            "value": POKE_REACTIONS})
            ev["corrupt"] = {"unit": uid, "ok": c.get("ok"), "error": c.get("error"),
                             "diff": session_diff(host, client)}
            if not c.get("ok"):
                fails.append(f"precondition: the client-only set_stat answered {ev['corrupt']}")
        ev["before"] = {"host": probe(host), "client": probe(client)}
        client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        ev["tally"] = wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20)
        host.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        t0, closes, samples, last = time.time(), [], [], None
        while time.time() - t0 < DEBRIEF_S:
            hst = stack(host)
            if "DebriefingState" in hst:
                break
            s = (hst[-1] if hst else None, top(client))
            if s != last:
                samples.append((round(time.time() - t0, 2),) + s)
                last = s
            if hst and hst[-1] == "NextTurnState":
                closes.append(host.cmd({"cmd": "dismiss_popup", "keep": KEEP}).get("type"))
            time.sleep(0.1)
        ev["hostEnding"] = {"secs": round(time.time() - t0, 2), "closes": closes, "samples": samples}
        if "DebriefingState" not in stack(host):
            fails.append(f"precondition: no host DebriefingState within {DEBRIEF_S}s of the END TURN presses")
        t1, client_closes = time.time(), []

        def client_left():
            cst = stack(client)
            if cst and cst[-1] == "NextTurnState":  # the client player closes its own turn screen
                client_closes.append(client.cmd({"cmd": "dismiss_popup", "keep": KEEP}).get("type"))
            return "BattlescapeState" not in stack(client)
        left = wait_until(client_left, CLIENT_LEAVE_S)
        ev["clientCloses"] = client_closes
        ev["clientStack"] = stack(client)
        ev["clientLeaveS"] = round(time.time() - t1, 2)
        ev["after"] = {"host": probe(host), "client": probe(client)}
        ca = ev["after"]["client"]
        if corrupt and ca.get("desyncSeen") is not True:
            fails.append(f"precondition: client desyncSeen {ca.get('desyncSeen')} (want True: the corruption was "
                         f"found)")
        if not left:
            fails.append(f"client still holds its BattlescapeState {CLIENT_LEAVE_S}s after the host's debriefing "
                         f"(queueDepth {ca.get('queueDepth')}, battleEnd {ca.get('battleEnd')}, host resync "
                         f"{ev['after']['host'].get('resync')})")
        if ca.get("top") != "DebriefingState":
            fails.append(f"client top {ca.get('top')} (want DebriefingState: the host's display-only debriefing)")
        if ca["battleEnd"].get("applied") != 1:
            fails.append(f"client battleEnd applied {ca['battleEnd'].get('applied')} (want 1)")
    except Exception as e:
        fails.append(f"{type(e).__name__}: {short(e, 600)}")
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[desync_at_battle_end] shutdown {gc.name}: {short(e, 200)}", flush=True)
    crash = sorted(session._crash_log_snapshot() - crash0)
    ev["newCrashFiles"] = crash
    if crash:
        fails.append(f"new crash files {crash} (want none)")
    print(f"EVIDENCE {rid}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    print(f"{'PASS' if not fails else 'FAIL'} {rid}{': ' + '; '.join(fails) if fails else ''}", flush=True)
    return not fails


def main():
    t0 = time.time()
    rows = (("control_no_desync", False), ("desync_at_battle_end", True))
    failed = [rid for rid, corrupt in rows if not run_row(rid, corrupt)]
    print(f"\ntest_client_desync_at_battle_end: {len(rows) - len(failed)}/{len(rows)} rows passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
