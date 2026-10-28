"""MG-B S-A row CB2: a saved PvE2 (gamemode 4) co-op Custom Battle, hosted from the battle's pause menu, continues for both
players through CONTINUE BATTLE with no dialog, and the "X-COM moves first" opening does not run again (owner Q283-5 (a);
D270 (b): PvE2 stays legal in Custom Battle; D225 (a): CONTINUE BATTLE on the rewrite's handshake; QMB2-1 (a): this cell
lives in its own file). The sibling rows PG (D238 (a)) and CB1 are test_skirmish_saved_battle_join.py, whose helpers this
file imports.

Spec: docs repo rewrite/prompts/mgb2_common.md (rulings, R3, QMB2-1 .. QMB2-5 (a)), mgb2_sa_continue.md (this stage,
section (f) row CB2), mgb2_sb_convert.md (stage S-B). Constants: rewrite/mgb2-task0/sa/CONSTANTS.md (TASK 0 boots c, d, g
at dfe41388b). Lobby key 49208.

Seed pair: R5-U8's gm4 bring-up as test_pve2_turns.bring_up does it (steps copied, not imported): the host's
set_seed SEED_ROSTER; the client on Alien (gamemode 2), then the host's own row on Alien (gamemode 4); STR_MEDIUM_SCOUT on
map seed 1; both briefings and both pre-battle equip screens; pin_ai_neutral and every live unit's reactions 0; then the
opening: the host closes its Turn 1 screen, every NextTurnState closes, both settle on side 0 of turn 2 (the host's "PvE2
opening" line once). The seed's P2 (per unit coop, faction, isOut, x, y, z), side and turn are read; every bucket EQUAL;
the host saves. Resume pair: a fresh host with the save (no option change) and a clean client.
  CB2  host load_save_menu; open_pause_coop; host_menu_host; the client joins; CONTINUE BATTLE; the client in battle
       (bound 120 s), read 2 s later: no CoopState 62 / 68 and no CampaignTeamRefusedState on either stack, both tops
       BattlescapeState, no BriefingState on the client; coopGamemode 4 on both; phase Active and desyncSeen false on both;
       side / turn == the saved ones on both; per unit host == client == P2; every bucket EQUAL; the host's "PvE2 opening"
       line count after the resume 0 (CANDIDATE F18789).
RED on the unchanged product: CB2 ("the saved PvE2 Custom Battle never reached the second player", evidence as CB1's G3).
GREEN (EA1-EA6): CB2 PASS.

One EVIDENCE line (every sub-read), one PASS / FAIL line, the row verdict. A boot step past its bound prints ONE CAPTURE
line and fails the cell "boot". WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run is the result, no
skip path; exit 0 only when the cell passes, else 2.

Run:  python tools/coop_test/test_skirmish_saved_pve2_continue.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import pvp_fixture as PF  # noqa: E402
from test_delta_core import both  # noqa: E402
import test_skirmish_saved_battle_join as J  # noqa: E402

KEY, SAVE2 = "49208", "mgb_cb2.sav"
SEED_ROSTER, SEED, MISSION2 = 1, 1, "STR_MEDIUM_SCOUT"   # R5-U8 boot B's constants (TASK 0 boots c, d: equal)
GM_PVE2 = 4
BRIEF_S = 60             # each briefing (TASK 0: <= 1 s)
OPENING_S = 60           # side 0 of turn 2 on both after the host's Turn 1 close (TASK 0: 3.2 s)
N_OPEN = "R5-U8: PvE2 opening"
CELLS = ("CB2",)
top, bs, es = J.top, J.bs, J.es


def drive_to_side0(host, client, want_turn, bound):
    """R5-U8's drive_to_side0 (copied): every 0.25 s close any NextTurnState on either machine; done when, on two polls 1 s
    apart, side 0 and turn `want_turn` on both, both tops BattlescapeState, the host's pendingStates 0 and not isBusy."""
    t, hits, closes, last = time.time(), [], [], None
    while time.time() - t < bound:
        for gc in (host, client):
            if top(gc) == "NextTurnState":
                closes.append((gc.name, round(time.time() - t, 2), gc.cmd({"cmd": "close_nextturn"}).get("handled")))
        hb, cb = bs(host), bs(client)
        last = {"side": [hb.get("side"), cb.get("side")], "turn": [hb.get("turn"), cb.get("turn")],
                "tops": [top(host), top(client)], "pending": hb.get("pendingStates"), "busy": hb.get("isBusy")}
        if (last["side"] == [0, 0] and last["turn"] == [want_turn] * 2 and last["pending"] == 0 and not last["busy"]
                and last["tops"] == ["BattlescapeState"] * 2):
            hits.append(time.time() - t)
            if hits[-1] - hits[0] >= 1.0:
                return True, round(time.time() - t, 2), closes, last
            time.sleep(1.0)
            continue
        hits = []
        time.sleep(0.25)
    return False, round(time.time() - t, 2), closes, last


def seed_pair():
    """The CB2 seed pair (gm4); returns (save path, seed record) or raises J.Miss after ONE CAPTURE line."""
    host_dir = make_user_dir("mgb_cb2s_host")
    host, client = GameClient("host", 0, host_dir), GameClient("client", 0, make_user_dir("mgb_cb2s_client"))
    m, rec = (host, client), {}

    def boot():
        host.spawn(), client.spawn(), host.connect(), client.connect()
        host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
        rec["gm2"] = PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client")[0]
        row = PF.row_for(host, "HostPlayer")
        rec["gm"] = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"}).get("gamemode")
        host.wait_for("both lobby rows Alien", lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                      and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], timeout=10, interval=0.25)
        if rec["gm"] != GM_PVE2:
            raise AssertionError(f"lobby gamemode {rec['gm']} (want {GM_PVE2})")
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
        if top(host) != "NewBattleState":
            raise AssertionError(f"host stack {J.stack(host)} (want NewBattleState on top)")
        host.ok({"cmd": "newbattle_mission", "type": MISSION2}), host.ok({"cmd": "set_seed", "seed": SEED})
        host.ok({"cmd": "newbattle_ok"})
        for gc in (host, client):
            gc.wait_for(f"{gc.name} briefing", lambda gc=gc: session.has_state(gc, "BriefingState"), timeout=BRIEF_S)
        host.ok({"cmd": "click_widget", "match": "ok"})
        session.dismiss_client_briefing(client)
        session.equip_both_ready(host, client)
        rec["pinned"] = session.pin_ai_neutral(host, client, tag="mgb-cb2")
        for uid in sorted(u["id"] for u in bs(host).get("units", []) if not u.get("isOut")):
            both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": "reactions", "value": 0},
                 ("tu",))
        rec["hostClose"] = host.cmd({"cmd": "dismiss_popup"})   # the host's Turn 1 screen
        done, rec["openingS"], rec["closes"], last = drive_to_side0(host, client, 2, OPENING_S)
        if not done:
            raise AssertionError(f"opening: side 0 of turn 2 on both not settled in {OPENING_S} s: {last}")
        session.wait_host_idle(host, client, timeout=J.STEP_S)
        session.assert_hash_clean(host, client, full=True, what="CB2 seed")

    try:
        J.guarded("CB2 seed", boot, m)
        hb, cb = bs(host), bs(client)
        rec.update(P2=J.ptable(hb), sideTurn=[[b.get("side"), b.get("turn")] for b in (hb, cb)], fp=hb.get("mapFingerprint"),
                   opening=J.log_count(host, N_OPEN), gamemode=[hb.get("coopGamemode"), cb.get("coopGamemode")])
        if (rec["opening"] != 1 or rec["P2"] != J.ptable(cb) or rec["sideTurn"] != [[0, 2], [0, 2]]
                or rec["gamemode"] != [GM_PVE2] * 2):
            J.missed("CB2 seed", f"seed precondition: {rec} (want one opening line, P2 equal on both, side 0 turn 2, gm 4)",
                     m)
        J.guarded("CB2 seed", lambda: host.ok({"cmd": "save_game", "file": SAVE2}), m)
        path = os.path.join(host_dir, "xcom1", SAVE2)
        if not J.wait_until(lambda: os.path.exists(path), 10, 0.2)[0]:
            J.missed("CB2 seed", f"save_game wrote no {path} in 10 s", m)
        return path, rec
    finally:
        J.shut(host, client)


def row_cb2():
    try:
        save, seed = seed_pair()
    except J.Miss:
        return J.boot_failed("CB2", CELLS, "CB2 seed", {"boot": "seed pair miss"})
    host, client = GameClient("host", 0, make_user_dir("mgb_cb2r_host", saves=[save])), GameClient(
        "client", 0, make_user_dir("mgb_cb2r_client"))
    ev = {"seed": seed}

    def cb2(ev):
        host.ok({"cmd": "open_pause_coop"})
        host.wait_for("HostMenu", lambda: session.has_state(host, "HostMenu"), timeout=J.STEP_S)
        host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "SavedBattle", "port": KEY, "player": "HostPlayer"})
        host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=J.STEP_S)
        J.join(host, client, KEY)
        host.wait_for("CONTINUE BATTLE offered", lambda: (lambda ls: ls.get("buttonVisible") and ls.get(
            "buttonText") == "CONTINUE BATTLE")(host.cmd({"cmd": "lobby_state"})), timeout=J.STEP_S)
        ok, text = J.continue_battle(host, client, ev, "the saved PvE2 Custom Battle never reached the second player")
        if ev["arrival"]["clientInBattleS"] is None:
            return False, text
        hb, cb, eh, ec = bs(host), bs(client), es(host), es(client)
        hok, hdetail = J.hash_cell(host, client, "CB2")
        p, ph, pc = seed["P2"], J.ptable(hb), J.ptable(cb)
        r = ev["cb2"] = {"refusedState": [bool(session.has_state(g, "CampaignTeamRefusedState")) for g in (host, client)],
                         "gamemode": [hb.get("coopGamemode"), cb.get("coopGamemode")],
                         "phase": [eh.get("phase"), ec.get("phase")], "desync": [eh.get("desyncSeen"), ec.get("desyncSeen")],
                         "sideTurn": [[b.get("side"), b.get("turn")] for b in (hb, cb)],
                         "opening": J.log_count(host, N_OPEN),
                         "diff": {k: [ph.get(k), pc.get(k), p.get(k)] for k in set(ph) | set(pc) | set(p)
                                  if not ph.get(k) == pc.get(k) == p.get(k)}}
        ok = (ok and r["refusedState"] == [False, False] and r["gamemode"] == [GM_PVE2] * 2
              and r["phase"] == ["Active"] * 2 and r["desync"] == [False, False] and r["sideTurn"] == seed["sideTurn"]
              and not r["diff"] and hok and r["opening"] == 0)
        return ok, (f"{text}; CampaignTeamRefusedState host/client {r['refusedState']} (want none); coopGamemode "
                    f"{r['gamemode']} (want 4 on both); phase {r['phase']} (want Active on both); desyncSeen {r['desync']} "
                    f"(want False/False); side/turn {r['sideTurn']} (want the saved {seed['sideTurn']}); units differing "
                    f"host/client/P2 {r['diff']} (want none); {hdetail}; host '{N_OPEN}' lines after the resume "
                    f"{r['opening']} (want 0)")

    try:
        try:
            J.load_saved(host, client, SAVE2, "CB2 resume")
        except J.Miss:
            return J.boot_failed("CB2", CELLS, "CB2 resume", ev)
        return J.report("CB2", CELLS, J.run_cells(CELLS, {"CB2": (True, cb2)}, ev), ev)
    finally:
        J.shut(host, client)


def main():
    t0 = time.time()
    fails = row_cb2()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_skirmish_saved_pve2_continue: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
