"""SAVE & QUIT on the host's wait dialog (62) over an open practice screen must not write the practice battle to disk.
Without the fix a Ufopaedia preview's save crashes the next load (its stand-in soldiers are in no base); an equipment
screen's save loads as a battle and keeps the craft marked in the battlescape. Vanilla has no save path there.
  Boot preview_save_quit: bring_up("practice_save_preview", (49532, 49533, 46972)):
    PV(host) + non-vacuity; client.kill(); the host's 62 on top over the preview; coop_dialog_save_quit;
    list_save_confirm {name: "practice_save_preview"}; within 60 s ending_state.mainMenu; exactly one new .sav. Cell
    clean_save (fails without the fix, measured 2 of 2 runs: battleGame: at line 1275, mission:
    STR_CRAFT_DEPLOYMENT_PREVIEW): the .sav has no line `battleGame:` and no header line starting `mission:`. Cell
    load_survives (fails without the fix, measured 2 of 2 runs: the host dies, frames Soldier::getName <-
    BattleUnit::BattleUnit <- SavedBattleGame::load <- SavedGame::load): the host's load_save {file} -> alive HOLD s
    later, get_coop.inBattle false, stack [GeoscapeState], no CRASH.
  Boot equipment_save_quit: bring_up("practice_save_equipment", (49534, 49535, 46973)):
    the host's equipment screen (open_craft_equipment, craft_inventory) + non-vacuity; kill; 62; SAVE & QUIT as in
    preview_save_quit (name "practice_save_equipment"). Cell clean_save: no `battleGame:` and no `inBattlescape: true`
    line in the .sav (without the fix, 2 of 2 runs: battleGame: at line 1248, inBattlescape: true at line 714, the
    SKYRANGER). Cell load_survives as in preview_save_quit (without the fix, 2 of 2 runs: alive, [GeoscapeState],
    inBattle true).
Count rows (N = 3 fresh SHARED boots each; a row fails on >= 1 host death and passes on 0 deaths):
    equipment_resync_count: boots practice_resync1..3 on (49546, 49547, 46979): the host's equipment screen +
      non-vacuity; the client's force_resync (replica, sent); within W the client re-adopts (CL push / pop
      LoadGameState, push GeoscapeState), then the host alive HOLD s later. The client's adoption ends in
      COOP_READY_CLIENT on the host, whose getSavedBattle()->getBattleGame() derefs the equipment battle's null
      BattlescapeState (without the fix, one run: the host died, connectionTCP.cpp :36875).
    equipment_chat_count: boots practice_chat1..3 on (49548, 49549, 46980): the host's equipment screen +
      non-vacuity; the host's keyChat (inject_input); within W battle_state.chatActive true, then the host alive HOLD s
      later. ChatMenu::draw reads getSavedBattle()->getBattleGame() (without the fix, one run: the host died,
      ChatMenu.cpp :244; the plain geoscape and the preview stayed alive).
    Cells: guards per boot (setup guard, the equipment screen, the trigger sent); non-vacuity: every surviving
      construction reached its effect; no host death in N (fails without the fix). A dead host's shutdown is
      tolerated (its CRASH is the evidence).
W = 10 s at 0.25 s polls, HOLD = 2 s. HL = the host's openxcom.log from the size noted before the kill. CRASH = new
crashlogs/crash_*.log since the row started (first 4 frames). Drive, setup guard (stacks [GeoscapeState], localSeat
0 / 1, has_battle false, the host's lobbyMode 1), CAPTURE and shutdown from test_practice_rejoin (main-guarded); a host
that dies on a cell that checks the fix is tolerated at shutdown. EVIDENCE before each verdict; a failed row prints ONE
CAPTURE line (incl. the file's first 30 battle lines); every row runs after a failure; ONE run; exit 0 iff every row
passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_practice_rejoin as prj  # noqa: E402  (main-guarded: X, boot, practice, drop, capture, shut, run, cr)

W, HOLD, MAIN_MENU_S, GEO = prj.W, prj.HOLD, 60.0, prj.GEO
pr, q, stack, wait_until = prj.pr, prj.q, prj.stack, prj.wait_until
BASELINE_PREVIEW = ("without the fix: 2 of 2 runs battleGame: + header mission: STR_CRAFT_DEPLOYMENT_PREVIEW in the "
                    ".sav; the host dies in load_save (Soldier::getName <- BattleUnit::BattleUnit <- "
                    "SavedBattleGame::load <- SavedGame::load)")
BASELINE_EQUIPMENT = ("without the fix: 2 of 2 runs battleGame: + inBattlescape: true (the SKYRANGER) in the .sav; "
                      "load_save -> alive, [GeoscapeState], inBattle true")
N_COUNT, SETTLE = 3, prj.SETTLE
CL_ADOPT = [pr.PUSH + "LoadGameState", pr.POP + "LoadGameState", pr.PUSH + GEO]
BASELINE_RESYNC = ("without the fix, one run: the host died 0.85 s after the client's force_resync, "
                   "BattlescapeState::getBattleGame <- onTCPMessage (connectionTCP.cpp :36875, COOP_READY_CLIENT)")
BASELINE_CHAT = ("without the fix, one run: the host died 0.7 s after keyChat, BattlescapeState::getBattleGame <- "
                 "ChatMenu::draw (ChatMenu.cpp :244) <- Game::run; controls (plain geoscape, preview) alive")


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
    if not r.cell("guard: SAVE & QUIT -> ListSaveState", listed, [a, stack(h)]):
        return prj.capture(r, x, n_hl)
    b = q(h, {"cmd": "list_save_confirm", "name": name})
    menu = b.get("ok") and wait_until(lambda: q(h, {"cmd": "ending_state"}).get("mainMenu"), MAIN_MENU_S)
    new = sorted(set(session.save_files(h.user_dir)) - files0)
    savs = [f for f in new if f.endswith(".sav")]
    r.ev["SAVE & QUIT"] = {"confirm": b, "mainMenu": menu, "new files": new, "stack": stack(h)}
    if not r.cell(f"guard: within {MAIN_MENU_S:.0f} s ending_state.mainMenu, exactly one new .sav", menu and len(savs) == 1,
                  r.ev["SAVE & QUIT"]):
        return prj.capture(r, x, n_hl)
    r.ev["SAV"], head = read_sav(os.path.join(h.user_dir, savs[0]))
    r.ev["SAV"]["file"] = savs[0]
    sv = r.ev["SAV"]
    if kind == "preview":
        r.cell("clean_save: the .sav has no line `battleGame:` and no header line starting `mission:`",
               sv["battleGame: line"] is None and not sv["header mission"], sv)
    else:
        r.cell("clean_save: no `battleGame:` and no `inBattlescape: true` line in the .sav",
               sv["battleGame: line"] is None and not sv["inBattlescape: true lines"], sv)
    rep = q(h, {"cmd": "load_save", "file": os.path.basename(savs[0])})
    time.sleep(HOLD)
    alive = pr.alive(h)
    if not alive:
        time.sleep(1.0)  # the crash handler's files
    crash = pr.crash_info(crash0)
    st, ib = (stack(h), prj.coop(h, "inBattle")["inBattle"]) if alive else (["<dead>"], None)
    x.host_died_in_row = not alive
    r.ev["load_survives"] = {"load_save": rep, "alive": alive, "stack": st, "inBattle": ib, "CRASH": crash,
                     "rc": h.proc.poll() if h.proc else None}
    r.cell(f"load_survives: the host's load_save -> alive {HOLD:.0f} s later, inBattle false, stack [{GEO}], no CRASH",
           rep.get("ok") and alive and ib is False and st == [GEO] and not crash, r.ev["load_survives"])
    if r.fails:
        prj.capture(r, x, n_hl, crash, {"battle head": head})


def t_resync(x, n_cl):
    """the client's force_resync -> (sent ok, reply, effect: the client re-adopted the streamed world)"""
    rep = q(x.client, {"cmd": "force_resync"})
    return (rep.get("role") == "replica" and rep.get("sent") is True, rep,
            lambda: pr.in_order(pr.log_lines(x.client, n_cl), CL_ADOPT))


def t_chat(x, n_cl):
    """the host's keyChat -> (sent ok, reply, effect: battle_state.chatActive true on the host)"""
    key = prj.cr.read_key(x.host.user_dir, "keyChat")
    time.sleep(SETTLE)
    rep = dict(q(x.host, {"cmd": "inject_input", "kind": "key", "key": key}), key=key)
    return rep.get("ok") is True and key is not None, rep, lambda: q(x.host, {"cmd": "battle_state"}).get("chatActive") is True


def count_row(rid, base, ports, trigger, baseline, results, walls):
    """N fresh SHARED boots: setup guard, the host's equipment screen, the trigger, W for its effect, HOLD; a host death
    is one count"""
    t0, r, deaths, recs = time.time(), pr.Row(rid, baseline), 0, []
    for k in range(1, N_COUNT + 1):
        x, rec, died = prj.X(f"{base}{k}"), {"boot": f"{base}{k}"}, False
        try:
            if prj.boot(r, x, ports, False) and prj.practice(r, x, "equipment"):
                rec["equipment"], rec["non-vacuity"] = r.ev.pop("equipment(host)", None), r.ev.pop("non-vacuity")
                n_cl, before = pr.log_size(x.client), pr.crash_names()
                ok, rec["trigger"], effect = trigger(x, n_cl)
                if r.cell(f"guard: {x.tag} trigger sent", ok, rec["trigger"]):
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
            r.cell(f"guard: {x.tag} exception", False, prj.short(e))
        finally:
            prj.shut(r, x, tolerate_host=died)
        recs.append(rec)
    r.ev["constructions"] = recs
    r.cell("non-vacuity: every surviving construction reached its effect",
           all(c.get("effect") for c in recs if c.get("host died") is False), [c.get("effect") for c in recs])
    r.cell(f"no host death in {N_COUNT} constructions", deaths == 0, f"{deaths}/{N_COUNT} died")
    walls[rid] = r.ev["wall s"] = round(time.time() - t0, 1)
    r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    prj.run("preview_save_quit", "practice_save_preview", (49532, 49533, 46972), save_quit_row, results, walls,
            args=("preview", "practice_save_preview"), baseline=BASELINE_PREVIEW)
    prj.run("equipment_save_quit", "practice_save_equipment", (49534, 49535, 46973), save_quit_row, results, walls,
            args=("equipment", "practice_save_equipment"), baseline=BASELINE_EQUIPMENT)
    count_row("equipment_resync_count", "practice_resync", (49546, 49547, 46979), t_resync, BASELINE_RESYNC, results,
              walls)
    count_row("equipment_chat_count", "practice_chat", (49548, 49549, 46980), t_chat, BASELINE_CHAT, results, walls)
    rows = ("preview_save_quit", "equipment_save_quit", "equipment_resync_count", "equipment_chat_count")
    failed = [rid for rid in rows if not results.get(rid)]
    print(f"\ntest_practice_save_quit: {len(rows) - len(failed)}/{len(rows)} passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
