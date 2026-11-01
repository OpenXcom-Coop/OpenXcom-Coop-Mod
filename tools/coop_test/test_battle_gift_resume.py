"""test_battle_gift_resume.py: two gifts survive a mid-battle save and its resume in a SEPARATE campaign (a battle gift
lasts until the mission ends), and a received unit can be given back after it. One boot: SEPARATE co-op, the mixed
squad of session.bring_up_separate_guest_battle (three host soldiers and the client's guest "Guest Zzz" on the host's
craft), coop port 47603, the resume on port 47604, dirs battle_gift_resume_host / battle_gift_resume_client and
battle_gift_resume_host2 / battle_gift_resume_client2.

Pins (the same on two capture boots): squad [1, 2, 3]; H1 = the unit whose soldierId is the squad's first (1, seat 0);
G = the unit named "Guest Zzz" (16: the client's soldier keeps its own id in the one shared save, seat 1).
  gifts_survive_resume  the host gives H1 to the client and the client gives G to the host (the battle_gift test
      command), the host saves the battle (save_game_ui quick_battle, test_midbattle_resume's step), both processes
      end, a fresh host2 / client2 resume it (session.resume_campaign_battle, the host's RESUME): gifts_land
      (precondition: H1 coop 1, G coop 0 on both), battle_saved (precondition: exactly one new save file,
      test_midbattle_resume._wait_new_save), battle_resumed (precondition: the call returns, both tops
      BattlescapeState), gifts_kept (H1 coop 1, G coop 0 on host2 and client2), resumed_commands (client2's turn of H1
      admitted; client2's turn of G denied not_your_unit), give_back_after_resume (client2 gives H1 back: H1 coop 0 on
      both), resume_common (host2 and client2).
The resumed host rebuilds its seat store from the units' loaded seat tags, so the gifts survive. Each receiver presses
OK on its gift notice (EVIDENCE).

"The order lands" = the unit's coop is the target on both machines within STEP_S. "Admitted" = one new host context
{intent, turn, H1} and H1 faces the new direction on both. One EVIDENCE line, then one PASS/FAIL line per cell, then the
row verdict. A boot step past its bound prints ONE CAPTURE line and fails the row "boot"; a cell whose precondition
failed FAILs "not reached"; a missed save / resume step fails its cell with a CAPTURE line. Common cell: every hash
bucket EQUAL, desyncSeen false on both, no new crash file since the first bring-up. Ids come from probes. No skip path;
exit 0 only when every cell passes, else 2.

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
import test_midbattle_resume as MBR  # noqa: E402
from test_battle_end_rules import wait_until  # noqa: E402

PORT, PORT2 = "47603", "47604"           # the coop session port of the battle and of its resume
STEP_S = 30                               # every bounded wait (measured: each step <= 5 s)
SAVE_S = 15                               # test_midbattle_resume's bound for the save file
RESUME_S = 180                            # the resume_campaign_battle timeout (measured: 6.4-6.5 s)
SQUAD, H1, G = [1, 2, 3], 1, 16           # the same on two capture boots
GUEST_NAME = "Guest Zzz"
ROWS = (("gifts_survive_resume", ("gifts_land", "battle_saved", "battle_resumed", "gifts_kept", "resumed_commands",
                                  "give_back_after_resume", "resume_common")),)

units, top = G3F.units, G3F.top
not_reached = OWN.not_reached


def bring_up(host, client):
    """session.bring_up_separate_guest_battle on PORT, then the pins (H1 by soldierId, G by name)."""
    m = (host, client)
    GF.guarded("boot", lambda: (host.spawn(), client.spawn(), host.connect(), client.connect()), m)
    squad, guest = GF.guarded("boot", lambda: session.bring_up_separate_guest_battle(host, client, port=PORT), m)
    crash0 = session._crash_log_snapshot()
    uh, uc = units(host), units(client)
    view = {"squad": squad, "h1": sorted(i for i, u in uh.items() if u.get("soldierId") == squad[0]),
            "g": sorted(i for i, u in uh.items() if u.get("name") == GUEST_NAME),
            "seats": [[(u.get(i) or {}).get("coop") for i in (H1, G)] for u in (uh, uc)]}
    want = {"squad": SQUAD, "h1": [H1], "g": [G], "seats": [[0, 1], [0, 1]]}

    def pins():
        assert view == want, f"boot pins {view} (want {want})"
    GF.guarded("boot", pins, m)
    GF.guarded("boot", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    return dict(view, guestId=guest), crash0


def save(host, client, ev):
    """The host's quick battle save at a quiescent moment; exactly one new file; both processes end."""
    GF.idle(host, client, ev)
    before = set(session.save_files(host.user_dir))
    ev["saveReply"] = host.cmd({"cmd": "save_game_ui", "type": "quick_battle"})
    new = sorted(MBR._wait_new_save(host.user_dir, before, timeout=SAVE_S))
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


def row_gifts_survive_resume(host, client, crash0, later):
    cells, ev = {}, {"sel0": GF.sels(host, client)}
    landed, miss = KEEP.gifts_in_order([(host, H1, 1), (client, G, 0)], host, client, ev)
    got = [GF.coops(host, client, H1), GF.coops(host, client, G)]
    cells["gifts_land"] = (landed and got == [[1, 1], [0, 0]],
                           f"H1 / G coop host/client {got} (want [1, 1] / [0, 0], each landing within {STEP_S} s)"
                           f"{'; ' + miss if miss else ''}")
    ev["giftLines"] = GF.gift_lines(host)[-3:]
    if not cells["gifts_land"][0]:
        not_reached(cells, ROWS[0][1][1:], "gifts_land failed")
        ev["commonFirstPair"] = G3F.common(host, client, crash0)
        return cells, ev
    ev["hashBeforeSave"] = G3F.hash_now(host, client)
    try:
        new = save(host, client, ev)
        cells["battle_saved"] = (len(new) == 1, f"new save files in the host dir {new} (want exactly one within "
                                                f"{SAVE_S} s); save_game_ui {ev['saveReply']}")
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:500]}"
        GF.capture("gifts_survive_resume", err, (host, client))
        cells["battle_saved"] = (False, f"staging: {err}")
    if not cells["battle_saved"][0]:
        not_reached(cells, ROWS[0][1][2:], "battle_saved failed")
        return cells, ev
    host2 = GameClient("host2", None, make_user_dir("battle_gift_resume_host2"))
    client2 = GameClient("client2", None, make_user_dir("battle_gift_resume_client2"))
    later.extend([host2, client2])
    try:
        ok = resume(host, host2, client2, ev["newSaves"][0], ev)
        cells["battle_resumed"] = (ok, f"resume_campaign_battle on {PORT2} returned; RESUME {ev['press']}; tops "
                                       f"host2/client2 {[top(host2), top(client2)]} (want BattlescapeState on both "
                                       f"within {STEP_S} s; {ev['topsS']} s)")
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:500]}"
        GF.capture("gifts_survive_resume", err, (host2, client2))
        cells["battle_resumed"] = (False, f"staging: {err}")
    if not cells["battle_resumed"][0]:
        not_reached(cells, ROWS[0][1][3:], "battle_resumed failed")
        return cells, ev
    kept = [GF.coops(host2, client2, H1), GF.coops(host2, client2, G)]
    cells["gifts_kept"] = (kept == [[1, 1], [0, 0]], f"H1 / G coop host2/client2 {kept} (want [1, 1] / [0, 0])")
    h_ok, h_txt = KEEP.turn_cell(host2, client2, H1, ev.setdefault("cmdH1", {}))
    to = ((units(client2).get(G) or {}).get("direction", 0) + 2) % 8
    d_ok, d_txt = OWN.deny_cell(OWN.partner_turn(host2, client2, G, to, ev.setdefault("cmdG", {"toDir": to})), G)
    cells["resumed_commands"] = (h_ok and d_ok, f"turn of H1: {h_txt} | turn of G: {d_txt}")
    gv = ev.setdefault("give", {})
    gv["reply"] = client2.cmd({"cmd": "battle_gift", "unit_id": H1, "owner": 0})
    g_ok, g_txt = GF.lands(host2, client2, H1, 0, gv)
    gv["cleared"] = [GF.clear_popups(host2), GF.clear_popups(client2)]
    cells["give_back_after_resume"] = (g_ok, f"client2 battle_gift {{{H1}, owner 0}} {gv['reply']}: {g_txt}")
    ev["giftLines2"] = GF.gift_lines(host2)[-2:]
    ev["convertLines"] = [ln for ln in G3F.log_lines(host2) if "[coop-convert]" in ln]
    cells["resume_common"] = G3F.common(host2, client2, crash0)
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("battle_gift_resume_host"))
    client = GameClient("client", None, make_user_dir("battle_gift_resume_client"))
    later, rows, fails = [], dict(ROWS), 0
    try:
        try:
            boot, crash0 = bring_up(host, client)
            print(f"[test_battle_gift_resume] boot: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            fails += G3F.run_row("gifts_survive_resume", rows["gifts_survive_resume"],
                                 lambda: row_gifts_survive_resume(host, client, crash0, later))
    finally:
        G3F.shut(host, client, *later)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_resume: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
