"""W2-H21d S-1 (F8980 routed, F9196; spec rewrite/prompts/w2h21d_preview_battle_paths.md (f), QH21d-4 a, QH21d-5 a; TASK 0
rewrite/w2h21d-task0/s1/CONSTANTS.md): SAVE & QUIT on the host's wait dialog (62) over an open practice screen writes the practice
battle to disk. A Ufopaedia preview's save crashes the next load (its stand-in soldiers are in no base); an equipment screen's save
loads as a battle and keeps the craft marked in the battlescape. Vanilla has no save path there.
  Boot Q1 bring_up("w2h21sqa", (49532, 49533, 46972)):
    H21d-Q1 (named RED) PV(host) + non-vacuity; client.kill(); the host's 62 on top over the preview; coop_dialog_save_quit;
        list_save_confirm {name: "w2h21sqa"}; within 60 s ending_state.mainMenu; exactly one new .sav. RED 1: the .sav has no line
        `battleGame:` and no header line starting `mission:` (TASK 0 2/2: battleGame: at line 1274, mission: STR_CRAFT_DEPLOYMENT_PREVIEW).
        RED 2: the host's load_save {file} -> alive HOLD s later, get_coop.inBattle false, stack [GeoscapeState], no CRASH (TASK 0 2/2:
        the host dies, frames Soldier::getName <- BattleUnit::BattleUnit <- SavedBattleGame::load <- SavedGame::load).
  Boot Q2 bring_up("w2h21sqb", (49534, 49535, 46973)):
    H21d-Q2 (named RED) the host's P4 (open_craft_equipment, craft_inventory) + non-vacuity; kill; 62; SAVE & QUIT as Q1 (name
        "w2h21sqb"). RED 1: no `battleGame:` and no `inBattlescape: true` line in the .sav (TASK 0 2/2: battleGame: at 1247,
        inBattlescape: true at 713, the SKYRANGER). RED 2 as Q1's (TASK 0 2/2: alive, [GeoscapeState], inBattle true).
W = 10 s at 0.25 s polls, HOLD = 2 s. HL = the host's openxcom.log from the size noted before the kill. CRASH = new crashlogs/crash_*.log
since the row started (first 4 frames). Drive, setup guard (stacks [GeoscapeState], localSeat 0 / 1, has_battle false, the host's
lobbyMode 1), CAPTURE and shutdown from test_w2_practice_rejoin (main-guarded); a host that dies on RED 2 is tolerated at shutdown.
EVIDENCE before each verdict; a failed row prints ONE CAPTURE line (incl. the file's first 30 battle lines); every row runs after a
failure; ONE run (WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_w2_practice_rejoin as prj  # noqa: E402  (main-guarded: practice, drop, capture, run)

W, HOLD, MAIN_MENU_S, GEO = prj.W, prj.HOLD, 60.0, prj.GEO
pr, q, stack, wait_until = prj.pr, prj.q, prj.stack, prj.wait_until
RED_Q1 = ("named red: TASK 0 2/2 battleGame: + header mission: STR_CRAFT_DEPLOYMENT_PREVIEW in the .sav; the host dies in "
          "load_save (Soldier::getName <- BattleUnit::BattleUnit <- SavedBattleGame::load <- SavedGame::load)")
RED_Q2 = ("named red: TASK 0 2/2 battleGame: + inBattlescape: true (the SKYRANGER) in the .sav; load_save -> alive, "
          "[GeoscapeState], inBattle true")


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


def main():
    t0, results, walls = time.time(), {}, {}
    prj.run("H21d-Q1", "w2h21sqa", (49532, 49533, 46972), save_quit_row, results, walls, args=("P1", "w2h21sqa"), task0=RED_Q1)
    prj.run("H21d-Q2", "w2h21sqb", (49534, 49535, 46973), save_quit_row, results, walls, args=("P4", "w2h21sqb"), task0=RED_Q2)
    failed = [rid for rid in ("H21d-Q1", "H21d-Q2") if not results.get(rid)]
    print(f"\ntest_w2_practice_save_quit: {2 - len(failed)}/2 passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
