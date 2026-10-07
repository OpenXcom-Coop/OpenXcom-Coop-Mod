"""W2-H21d S-1 (F8980 routed, F9196; spec rewrite/prompts/w2h21d_preview_battle_paths.md (f), QH21d-4 a, QH21d-5 a; TASK 0
rewrite/w2h21d-task0/s1/CONSTANTS.md): SAVE & QUIT on the host's wait dialog (62) over an open practice screen writes the practice
battle to disk. A Ufopaedia preview's save crashes the next load (its stand-in soldiers are in no base); an equipment screen's save
loads as a battle and keeps the craft marked in the battlescape. Vanilla has no save path there.
  Boot Q1 bring_up("w2h21sqa", (49532, 49533, 46972)):
    H21d-Q1 (named RED) PV(host) + non-vacuity; client.kill(); the host's 62 on top over the preview; coop_dialog_save_quit;
        list_save_confirm {name: "w2h21sqa"}; within 60 s ending_state.mainMenu; exactly one new .sav. RED 1: the .sav has no line
        `battleGame:` and no header line starting `mission:` (TASK 0 2/2: battleGame: at line 1275, mission: STR_CRAFT_DEPLOYMENT_PREVIEW).
        RED 2: the host's load_save {file} -> alive HOLD s later, get_coop.inBattle false, stack [GeoscapeState], no CRASH (TASK 0 2/2:
        the host dies, frames Soldier::getName <- BattleUnit::BattleUnit <- SavedBattleGame::load <- SavedGame::load).
  Boot Q2 bring_up("w2h21sqb", (49534, 49535, 46973)):
    H21d-Q2 (named RED) the host's P4 (open_craft_equipment, craft_inventory) + non-vacuity; kill; 62; SAVE & QUIT as Q1 (name
        "w2h21sqb"). RED 1: no `battleGame:` and no `inBattlescape: true` line in the .sav (TASK 0 2/2: battleGame: at line 1248,
        inBattlescape: true at line 714, the SKYRANGER). RED 2 as Q1's (TASK 0 2/2: alive, [GeoscapeState], inBattle true).
Count rows (orchestrator ruling R-H21d-S1-1, R-H21-T0-1: N = 3 fresh SHARED boots each; red = >= 1 host death, green = 0 deaths):
    H21d-R5 (named RED; F9398) boots w2h21sqr1..3 on (49546, 49547, 46979): the host's P4 + non-vacuity; the client's force_resync
        (replica, sent); within W the client re-adopts (CL push / pop LoadGameState, push GeoscapeState), then the host alive HOLD s
        later. The client's adoption ends in COOP_READY_CLIENT on the host, whose getSavedBattle()->getBattleGame() derefs the
        equipment battle's null BattlescapeState (side capture w2h21prx1: the host died, connectionTCP.cpp :36875).
    H21d-R6 (named RED; F9403) boots w2h21sqk1..3 on (49548, 49549, 46980): the host's P4 + non-vacuity; the host's keyChat
        (inject_input); within W battle_state.chatActive true, then the host alive HOLD s later. ChatMenu::draw reads
        getSavedBattle()->getBattleGame() (side capture w2h21prx6a: the host died, ChatMenu.cpp :244; controls none / P1 alive).
    Cells: G per boot (setup guard, P4, the trigger sent); non-vacuity: every surviving construction reached its effect; RED: no
        host death in N. A dead host's shutdown is tolerated (its CRASH is the evidence).
W = 10 s at 0.25 s polls, HOLD = 2 s. HL = the host's openxcom.log from the size noted before the kill. CRASH = new crashlogs/crash_*.log
since the row started (first 4 frames). Drive, setup guard (stacks [GeoscapeState], localSeat 0 / 1, has_battle false, the host's
lobbyMode 1), CAPTURE and shutdown from test_w2_practice_rejoin (main-guarded); a host that dies on a RED cell is tolerated at shutdown.
EVIDENCE before each verdict; a failed row prints ONE CAPTURE line (incl. the file's first 30 battle lines); every row runs after a
failure; ONE run (WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_w2_practice_rejoin as prj  # noqa: E402  (main-guarded: X, boot, practice, drop, capture, shut, run, cr)

W, HOLD, MAIN_MENU_S, GEO = prj.W, prj.HOLD, 60.0, prj.GEO
pr, q, stack, wait_until = prj.pr, prj.q, prj.stack, prj.wait_until
RED_Q1 = ("named red: TASK 0 2/2 battleGame: + header mission: STR_CRAFT_DEPLOYMENT_PREVIEW in the .sav; the host dies in "
          "load_save (Soldier::getName <- BattleUnit::BattleUnit <- SavedBattleGame::load <- SavedGame::load)")
RED_Q2 = ("named red: TASK 0 2/2 battleGame: + inBattlescape: true (the SKYRANGER) in the .sav; load_save -> alive, "
          "[GeoscapeState], inBattle true")
N_COUNT, SETTLE = 3, prj.SETTLE
CL_ADOPT = [pr.PUSH + "LoadGameState", pr.POP + "LoadGameState", pr.PUSH + GEO]
RED_R5 = ("named red: side capture w2h21prx1 1/1 the host died 0.85 s after the client's force_resync, BattlescapeState::getBattleGame "
          "<- onTCPMessage (connectionTCP.cpp :36875, COOP_READY_CLIENT)")
RED_R6 = ("named red: side capture w2h21prx6a 1/1 the host died 0.7 s after keyChat, BattlescapeState::getBattleGame <- "
          "ChatMenu::draw (ChatMenu.cpp :244) <- Game::run; controls (plain geoscape, P1 preview) alive")


def read_sav(path):
    with open(path, "rb") as f:
        lines = f.read().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    sep = lines.index("---") if "---" in lines else len(lines)
    bi = lines.index("battleGame:") if "battleGame:" in lines else None
    return {"lines": len(lines), "battleGame: line": None if bi is None else bi + 1,
            "header mission": [ln for ln in lines[:sep] if ln.startswith("mission:")],
            "inBattlescape: true lines": [i + 1 for i, ln in enumerate(lines) if "inBattlescape: true" in ln]}, \
        (lines[bi:bi + 30] if bi is not None else [])


def save_quit_row(r, x, kind, name):
    h, crash0 = x.host, pr.crash_names()
    if not prj.practice(r, x, kind):
        return
    ok, n_hl, _before = prj.drop(r, x)
    if not ok:
        return
    files0 = set(session.save_files(h.user_dir))
    a = q(h, {"cmd": "coop_dialog_save_quit"})
    listed = a.get("ok") and wait_until(lambda: session.has_state(h, "ListSaveState"), W)
    if not r.cell("G: SAVE & QUIT -> ListSaveState", listed, [a, stack(h)]):
        return prj.capture(r, x, n_hl)
    b = q(h, {"cmd": "list_save_confirm", "name": name})
    menu = b.get("ok") and wait_until(lambda: q(h, {"cmd": "ending_state"}).get("mainMenu"), MAIN_MENU_S)
    new = sorted(set(session.save_files(h.user_dir)) - files0)
    savs = [f for f in new if f.endswith(".sav")]
    r.ev["SAVE & QUIT"] = {"confirm": b, "mainMenu": menu, "new files": new, "stack": stack(h)}
    if not r.cell(f"G: within {MAIN_MENU_S:.0f} s ending_state.mainMenu, exactly one new .sav", menu and len(savs) == 1,
                  r.ev["SAVE & QUIT"]):
        return prj.capture(r, x, n_hl)
    r.ev["SAV"], head = read_sav(os.path.join(h.user_dir, savs[0]))
    r.ev["SAV"]["file"] = savs[0]
    sv = r.ev["SAV"]
    if kind == "P1":
        r.cell("RED 1: the .sav has no line `battleGame:` and no header line starting `mission:`",
               sv["battleGame: line"] is None and not sv["header mission"], sv)
    else:
        r.cell("RED 1: no `battleGame:` and no `inBattlescape: true` line in the .sav",
               sv["battleGame: line"] is None and not sv["inBattlescape: true lines"], sv)
    rep = q(h, {"cmd": "load_save", "file": os.path.basename(savs[0])})
    time.sleep(HOLD)
    alive = pr.alive(h)
    if not alive:
        time.sleep(1.0)  # the crash handler's files
    crash = pr.crash_info(crash0)
    st, ib = (stack(h), prj.coop(h, "inBattle")["inBattle"]) if alive else (["<dead>"], None)
    x.host_died_on_red = not alive
    r.ev["RED 2"] = {"load_save": rep, "alive": alive, "stack": st, "inBattle": ib, "CRASH": crash,
                     "rc": h.proc.poll() if h.proc else None}
    r.cell(f"RED 2: the host's load_save -> alive {HOLD:.0f} s later, inBattle false, stack [{GEO}], no CRASH",
           rep.get("ok") and alive and ib is False and st == [GEO] and not crash, r.ev["RED 2"])
    if r.fails:
        prj.capture(r, x, n_hl, crash, {"battle head": head})


def t_resync(x, n_cl):
    """R5: the client's force_resync -> (sent ok, reply, effect: the client re-adopted the streamed world)"""
    rep = q(x.client, {"cmd": "force_resync"})
    return (rep.get("role") == "replica" and rep.get("sent") is True, rep,
            lambda: pr.in_order(pr.log_lines(x.client, n_cl), CL_ADOPT))


def t_chat(x, n_cl):
    """R6: the host's keyChat -> (sent ok, reply, effect: battle_state.chatActive true on the host)"""
    key = prj.cr.read_key(x.host.user_dir, "keyChat")
    time.sleep(SETTLE)
    rep = dict(q(x.host, {"cmd": "inject_input", "kind": "key", "key": key}), key=key)
    return rep.get("ok") is True and key is not None, rep, lambda: q(x.host, {"cmd": "battle_state"}).get("chatActive") is True


def count_row(rid, base, ports, trigger, task0, results, walls):
    """N fresh SHARED boots: setup guard, the host's P4, the trigger, W for its effect, HOLD; a host death is one count"""
    t0, r, deaths, recs = time.time(), pr.Row(rid, task0), 0, []
    for k in range(1, N_COUNT + 1):
        x, rec, died = prj.X(f"{base}{k}"), {"boot": f"{base}{k}"}, False
        try:
            if prj.boot(r, x, ports, False) and prj.practice(r, x, "P4"):
                rec["P4"], rec["non-vacuity"] = r.ev.pop("P4(host)", None), r.ev.pop("non-vacuity")
                n_cl, before = pr.log_size(x.client), pr.crash_names()
                ok, rec["trigger"], effect = trigger(x, n_cl)
                if r.cell(f"G: {x.tag} trigger sent", ok, rec["trigger"]):
                    wait_until(lambda: not pr.alive(x.host) or effect(), W)
                    rec["effect"] = bool(effect())
                    time.sleep(HOLD)
                    died = not pr.alive(x.host)
                    if died:
                        time.sleep(1.0)  # the crash handler's files
                    rec.update({"host died": died, "CRASH": pr.crash_info(before),
                                "host stack": "<dead>" if died else stack(x.host)})
                    deaths += died
                    if died:
                        prj.capture(r, x, 0, rec["CRASH"])
        except Exception as e:
            r.cell(f"G: {x.tag} exception", False, prj.short(e))
        finally:
            prj.shut(r, x, tolerate_host=died)
        recs.append(rec)
    r.ev["constructions"] = recs
    r.cell("non-vacuity: every surviving construction reached its effect",
           all(c.get("effect") for c in recs if c.get("host died") is False), [c.get("effect") for c in recs])
    r.cell(f"RED: no host death in {N_COUNT} constructions", deaths == 0, f"{deaths}/{N_COUNT} died")
    walls[rid] = r.ev["wall s"] = round(time.time() - t0, 1)
    r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    prj.run("H21d-Q1", "w2h21sqa", (49532, 49533, 46972), save_quit_row, results, walls, args=("P1", "w2h21sqa"), task0=RED_Q1)
    prj.run("H21d-Q2", "w2h21sqb", (49534, 49535, 46973), save_quit_row, results, walls, args=("P4", "w2h21sqb"), task0=RED_Q2)
    count_row("H21d-R5", "w2h21sqr", (49546, 49547, 46979), t_resync, RED_R5, results, walls)
    count_row("H21d-R6", "w2h21sqk", (49548, 49549, 46980), t_chat, RED_R6, results, walls)
    rows = ("H21d-Q1", "H21d-Q2", "H21d-R5", "H21d-R6")
    failed = [rid for rid in rows if not results.get(rid)]
    print(f"\ntest_w2_practice_save_quit: {len(rows) - len(failed)}/{len(rows)} passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
