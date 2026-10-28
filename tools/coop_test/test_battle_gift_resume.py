"""R5-U5 S-B row V1 (boot V; owner D235-VL4: a gift lasts until the mission ends; D240 (a)): two gifts survive a mid-battle
save and its resume in a SEPARATE campaign, and a received unit can be given back after it. Boot V: SEPARATE co-op, the
mixed squad of session.bring_up_separate_guest_battle (three host soldiers and the client's guest "Guest Zzz" on the host's
craft), coop port 47603, the resume on port 47604, dirs r5u5_v_host / r5u5_v_client and r5u5_v2_host / r5u5_v2_client.

Spec: docs repo rewrite/prompts/r5u5_battle_gift_order.md section (f) test_battle_gift_resume.py (ORCHESTRATOR RULINGS
QU5-1 .. QU5-11 (a); ruling R-U5-SB-1). Constants: rewrite/r5u5-task0/sb/CONSTANTS.md (boots Va, Vb).

Pins (Va, Vb): squad [1, 2, 3]; H1 = the unit whose soldierId is the squad's first (1, seat 0); G = the unit named
"Guest Zzz" (9: the merged copy's fresh id, seat 1).
  V1  the host gives H1 to the client and the client gives G to the host (levers), the host saves the battle
      (save_game_ui quick_battle, test_midbattle_resume's step), both processes end, a fresh host2 / client2 resume
      it (session.resume_campaign_battle, the host's RESUME): V1-gifts (precondition: H1 coop 1, G coop 0 on both),
      V1-save (precondition: exactly one new save file, S18 _wait_new_save), V1-resume (precondition: the call returns,
      both tops BattlescapeState), V1-kept (H1 coop 1, G coop 0 on host2 and client2), V1-cmd (client2's turn of H1
      admitted; client2's turn of G denied not_your_unit), V1-give (client2 gives H1 back: H1 coop 0 on both),
      V1-common (host2 and client2).
Red at B1: none (F12909: a disk resume rebuilds the seat store from the loaded tags). Each receiver presses OK on its gift
notice (EVIDENCE).

"The order lands" = the unit's coop is the target on both machines within STEP_S. "Admitted" = one new host context
{intent, turn, H1} and H1 faces the new direction on both. One EVIDENCE line, then one PASS/FAIL line per cell, then the
row verdict. A boot step past its bound prints ONE CAPTURE line and fails the row "boot"; a cell whose precondition failed
FAILs "not reached"; a missed save / resume step fails its cell with a CAPTURE line. Common cell: every hash bucket EQUAL,
desyncSeen false on both, no new crash file since the first bring-up. Ids come from probes (S25). WV-D95: run in the
foreground to completion. WV-D99 / WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.

Run:  python tools/coop_test/test_battle_gift_resume.py
"""

import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_battle_gift as GF  # noqa: E402
import test_battle_gift_keep as KEEP  # noqa: E402
import test_midbattle_resume as S18  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402

PORT, PORT2 = "47603", "47604"           # the coop session port of the battle and of its resume
STEP_S = 30                               # every bounded wait (TASK 0: each step <= 5 s)
SAVE_S = 15                               # S18's bound for the save file
RESUME_S = 180                            # the spec's resume_campaign_battle timeout (TASK 0: 6.4-6.5 s)
SQUAD, H1, G = [1, 2, 3], 1, 9            # Va, Vb
GUEST_NAME = "Guest Zzz"
ROWS = (("V1", ("V1-gifts", "V1-save", "V1-resume", "V1-kept", "V1-cmd", "V1-give", "V1-common")),)

units, top = G3F.units, G3F.top
not_reached = OWN.not_reached


def bring_up(host, client):
    """session.bring_up_separate_guest_battle on PORT, then the pins (H1 by soldierId, G by name)."""
    m = (host, client)
    GF.guarded("V", lambda: (host.spawn(), client.spawn(), host.connect(), client.connect()), m)
    squad, guest = GF.guarded("V", lambda: session.bring_up_separate_guest_battle(host, client, port=PORT), m)
    crash0 = session._crash_log_snapshot()
    uh, uc = units(host), units(client)
    view = {"squad": squad, "h1": sorted(i for i, u in uh.items() if u.get("soldierId") == squad[0]),
            "g": sorted(i for i, u in uh.items() if u.get("name") == GUEST_NAME),
            "seats": [[(u.get(i) or {}).get("coop") for i in (H1, G)] for u in (uh, uc)]}
    want = {"squad": SQUAD, "h1": [H1], "g": [G], "seats": [[0, 1], [0, 1]]}

    def pins():
        assert view == want, f"boot V pins {view} (want {want})"
    GF.guarded("V", pins, m)
    GF.guarded("V", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return dict(view, guestId=guest), crash0


def save(host, client, ev):
    """The host's quick battle save at a quiescent moment; exactly one new file; both processes end."""
    GF.idle(host, client, ev)
    before = set(session.save_files(host.user_dir))
    ev["saveReply"] = host.cmd({"cmd": "save_game_ui", "type": "quick_battle"})
    new = sorted(S18._wait_new_save(host.user_dir, before, timeout=SAVE_S))
    ev["newSaves"] = new
    G3F.shut(host, client)
    return new


def resume(host, host2, client2, savefile, ev):
    """The save copied into host2's fresh dir; resume_campaign_battle; the host's RESUME (codes 60 / 62); both tops."""
    dst = os.path.join(host2.user_dir, savefile)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(os.path.join(host.user_dir, savefile), dst)
    host2.spawn(); client2.spawn(); host2.connect(); client2.connect()
    t0 = time.time()
    session.resume_campaign_battle(host2, client2, os.path.basename(savefile), port=PORT2, timeout=RESUME_S)
    ev["press"] = session.press_back_when_shown(host2, "host2 RESUME", codes=(60, 62), timeout=STEP_S)
    ok, ev["topsS"] = wait_until(lambda: top(host2) == "BattlescapeState" and top(client2) == "BattlescapeState",
                                 STEP_S, 0.25)
    ev["resumeS"] = round(time.time() - t0, 2)
    return ok


def row_v1(host, client, crash0, later):
    cells, ev = {}, {"sel0": GF.sels(host, client)}
    landed, miss = KEEP.lever_gifts([(host, H1, 1), (client, G, 0)], host, client, ev)
    got = [GF.coops(host, client, H1), GF.coops(host, client, G)]
    cells["V1-gifts"] = (landed and got == [[1, 1], [0, 0]],
                         f"H1 / G coop host/client {got} (want [1, 1] / [0, 0], each landing within {STEP_S} s)"
                         f"{'; ' + miss if miss else ''}")
    ev["giftLines"] = GF.gift_lines(host)[-3:]
    if not cells["V1-gifts"][0]:
        not_reached(cells, ROWS[0][1][1:], "V1-gifts failed")
        ev["commonFirstPair"] = G3F.common(host, client, crash0)
        return cells, ev
    ev["hashBeforeSave"] = G3F.hash_now(host, client)
    try:
        new = save(host, client, ev)
        cells["V1-save"] = (len(new) == 1, f"new save files in the host dir {new} (want exactly one within {SAVE_S} s); "
                                           f"save_game_ui {ev['saveReply']}")
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:500]}"
        GF.capture("V1", err, (host, client))
        cells["V1-save"] = (False, f"staging: {err}")
    if not cells["V1-save"][0]:
        not_reached(cells, ROWS[0][1][2:], "V1-save failed")
        return cells, ev
    host2 = GameClient("host2", None, make_user_dir("r5u5_v2_host"))
    client2 = GameClient("client2", None, make_user_dir("r5u5_v2_client"))
    later.extend([host2, client2])
    try:
        ok = resume(host, host2, client2, ev["newSaves"][0], ev)
        cells["V1-resume"] = (ok, f"resume_campaign_battle on {PORT2} returned; RESUME {ev['press']}; tops host2/client2 "
                                  f"{[top(host2), top(client2)]} (want BattlescapeState on both within {STEP_S} s; "
                                  f"{ev['topsS']} s)")
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:500]}"
        GF.capture("V1", err, (host2, client2))
        cells["V1-resume"] = (False, f"staging: {err}")
    if not cells["V1-resume"][0]:
        not_reached(cells, ROWS[0][1][3:], "V1-resume failed")
        return cells, ev
    kept = [GF.coops(host2, client2, H1), GF.coops(host2, client2, G)]
    cells["V1-kept"] = (kept == [[1, 1], [0, 0]], f"H1 / G coop host2/client2 {kept} (want [1, 1] / [0, 0])")
    h_ok, h_txt = KEEP.turn_cell(host2, client2, H1, ev.setdefault("cmdH1", {}))
    to = ((units(client2).get(G) or {}).get("direction", 0) + 2) % 8
    d_ok, d_txt = OWN.deny_cell(OWN.partner_turn(host2, client2, G, to, ev.setdefault("cmdG", {"toDir": to})), G)
    cells["V1-cmd"] = (h_ok and d_ok, f"turn of H1: {h_txt} | turn of G: {d_txt}")
    gv = ev.setdefault("give", {})
    gv["lever"] = client2.cmd({"cmd": "battle_gift", "unit_id": H1, "owner": 0})
    g_ok, g_txt = GF.lands(host2, client2, H1, 0, gv)
    gv["cleared"] = [GF.clear_popups(host2), GF.clear_popups(client2)]
    cells["V1-give"] = (g_ok, f"client2 lever battle_gift {{{H1}, owner 0}} {gv['lever']}: {g_txt}")
    ev["giftLines2"] = GF.gift_lines(host2)[-2:]
    ev["convertLines"] = [ln for ln in G3F.log_lines(host2) if "[coop-convert]" in ln]
    cells["V1-common"] = G3F.common(host2, client2, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u5_v_host"))
    client = GameClient("client", None, make_user_dir("r5u5_v_client"))
    later, rows, fails = [], dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client)
            print(f"[r5u5] boot V: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE V line)")
        else:
            fails += G3F.run_row("V1", rows["V1"], lambda: row_v1(host, client, crash0, later))
    finally:
        G3F.shut(host, client, *later)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_resume: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
