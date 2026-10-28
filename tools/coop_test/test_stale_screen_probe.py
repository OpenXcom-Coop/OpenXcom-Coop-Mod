"""RV-U13 stage S-B (spec rewrite/prompts/rvu13_harness_hardening.md (f) `test_stale_screen_probe.py`, rows S0 and S1; QV13-1 (a),
QV13-3 (a); TASK 0 rewrite/rvu13-task0/sb/CONSTANTS.md and PREWALK.md): TestServer probes read a battle screen that was popped and
freed (F10980, F9920). SavedBattleGame keeps its _battleState after Game::popState queues the BattlescapeState for deletion (F11352),
and seven TestServer sites trust the non-null pointer (F11351: the executeBattle12 head, battle_set_unit_state, can_use_weapon,
battle_camera_center and three battle_state reads), so a probe in that window reads freed memory (F10980: one battle_state killed the
client, 0xC0000005 in BattlescapeGame::getStates). The S-B green asks connectionTCP::isBattlescapeStateLive at the seven sites (F11353).
  Boot S (key "48699", dirs rvu13_b_host / rvu13_b_client): session.bring_up_separate_guest_battle(host, client, port="48699"); both
  tops BattlescapeState within 60 s; pins read live on the client's live screen (S25): G = its unit with coop 1, I = the lowest-id item
  G owns in its battle_items, T = G's tile. A miss = FIXTURE-STOP: ONE "CAPTURE boot:" line and every row FAILs "boot".
  S0 (GUARD, non-vacuity) the client probes while its BattlescapeState is on the stack: S0-state battle_state ok, hud present,
  cursorType != -1, pendingStates an int; S0-screen map_tile_screen_pos {T} no error; S0-canuse can_use_weapon {G, I, snap} no error,
  canUse present; S0-camera battle_camera_center {T} no error.
  S1 the stale window: host disconnect_to_menu; the client polled with get_state / coop_dialog_info only, <= 15 s, until dialog 21;
  then 2.0 s. S1-pre GUARD: the leave ok, client stack exactly [GoToMainMenuState, CoopState], dialog 21 "Server connection lost",
  get_coop.inBattle true, world_state.has_battle true, host top MainMenuState. RED cells, each probe followed by a ping that answers:
  S1-state battle_state ok, inBattle true, isBusy false, pendingStates 0, panicHandled false, currentActionActorId -1, mouseOverIcons
  false, cursorType -1, hiddenMovementShown false, coopWaitText / coopEndTurnText / warningText "", coopEndTurnArmed / coopOffBatonGray
  false, no hud key; S1-screen map_tile_screen_pos {T} error "no BattlescapeState"; S1-canuse can_use_weapon {G, I, snap} error
  "can_use_weapon: no live battle"; S1-camera battle_camera_center {T} error "battle_camera_center: no BattlescapeState"; S1-panic
  battle_set_unit_state {G, panicPending true} error "battle_set_unit_state: no live BattlescapeGame" and 0 new crash files in this
  lane's crash folder since the baseline. EVIDENCE only: client coop_dialog_back -> top MainMenuState within 30 s, world_state.has_save
  false; host ping.
Rules: an S1 probe (or its ping) that raises FAILs that cell "client gone" and every later S1 cell (no retry, no reconnect); a client
that is dead at the end after an S1 RED cell failed is reaped with its own exit code (those cells hold the failure). Outside the S1
cells no machine is probed with battle_state, an executeBattle12 command, can_use_weapon, battle_camera_center or battle_set_unit_state
while its stack holds no BattlescapeState and its world holds a battle (F10980). EVIDENCE before each verdict; a failed row prints ONE
CAPTURE line (the four safe probes per machine, new crash files, 40 engine log lines per machine); every row runs after a failure.
ONE run (WV-D95: run to completion in the foreground; WV-D99 / WV-D100: no SKIP, no retry); exit 0 iff every cell passes, else 2.
Red (S-B commit B1, the unchanged TestServer): exactly S1-state, S1-screen, S1-canuse, S1-camera, S1-panic FAIL (the stale screen
answers, or the first probe ends the client and the later cells FAIL "client gone"); S0-state, S0-screen, S0-canuse, S0-camera, S1-pre
PASS.
"""
import json
import os
import sys
import time
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402

KEY, TAG, POLL = "48699", "rvu13_b", 0.25
BS, CS, GOTO, MENU = "BattlescapeState", "CoopState", "GoToMainMenuState", "MainMenuState"
S0_CELLS = ("S0-state", "S0-screen", "S0-canuse", "S0-camera")
S1_CELLS = ("S1-pre", "S1-state", "S1-screen", "S1-canuse", "S1-camera", "S1-panic")
S1_STATE = {"ok": True, "inBattle": True, "isBusy": False, "pendingStates": 0, "panicHandled": False, "currentActionActorId": -1,
            "mouseOverIcons": False, "cursorType": -1, "hiddenMovementShown": False, "coopWaitText": "", "coopEndTurnText": "",
            "coopEndTurnArmed": False, "coopOffBatonGray": False, "warningText": ""}


class Gone(Exception):
    """an S1 probe or its ping raised: the client is gone"""


def short(e, n=300):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead machine is a value
        return {"probeError": short(e, 200)}


def alive(gc):
    return gc is not None and gc.proc is not None and gc.proc.poll() is None


def stack(gc):
    r = q(gc, {"cmd": "get_state"})
    return [r["probeError"]] if "probeError" in r else [s.replace("class OpenXcom::", "") for s in r.get("states", [])]


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "probeError") if k in r}


def safe4(gc):
    """the four probes that never read a battle screen (F10980)"""
    c, w = q(gc, {"cmd": "get_coop"}), q(gc, {"cmd": "world_state"})
    return {"stack": stack(gc), "coop_dialog_info": dlg(gc),
            "get_coop": {k: c.get(k) for k in ("onConnect", "inBattle", "hasSave", "probeError") if k in c},
            "world_state": {k: w.get(k) for k in ("has_save", "has_battle", "probeError") if k in w}}


def tail(gc, n=40):
    p = os.path.join(gc.user_dir, "openxcom.log") if gc is not None and gc.user_dir else ""
    if not p or not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1][:200] for ln in f][-n:]


def new_crashes(x):
    return sorted(os.path.basename(p) for p in session._crash_log_snapshot() - x.cr0)


def capture(x, what):
    cap = {n: (safe4(gc) if alive(gc) else "not alive (rc=%s)" % (gc.proc.poll() if gc is not None and gc.proc else None))
           for n, gc in (("host", x.host), ("client", x.client))}
    cap["new crash files"] = new_crashes(x)
    cap["host log"], cap["client log"] = tail(x.host), tail(x.client)
    print("CAPTURE %s: %s" % (what, json.dumps(cap, sort_keys=True, default=str)), flush=True)


class Row:
    def __init__(self, rid, cells, x):
        self.rid, self.cells, self.x, self.fails, self.done, self.t0 = rid, cells, x, [], set(), time.time()

    def cell(self, cid, kind, label, ok, ev):
        print("EVIDENCE %s: %s" % (cid, json.dumps(ev, sort_keys=True, default=str)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def rest(self, why):
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: %s" % (cid, why), flush=True)
            self.done.add(cid)
            self.fails.append(cid)

    def end(self, results, walls):
        walls[self.rid] = round(time.time() - self.t0, 1)
        if self.fails and self.x.err is None:
            capture(self.x, self.rid)
        results[self.rid] = not self.fails
        print(("PASS %s" % self.rid) if not self.fails else ("FAIL %s: %s" % (self.rid, " ".join(self.fails))), flush=True)


def boot():
    """boot S to tactical, then the live pins G / I / T and the crash baseline; a miss = ONE CAPTURE boot line"""
    x = SimpleNamespace(host=None, client=None, err=None, G=None, I=None, T=None, cr0=session._crash_log_snapshot(), gone=None,
                        red_failed=False)
    try:
        x.host = GameClient("host", 1, make_user_dir(TAG + "_host"))
        x.client = GameClient("client", 2, make_user_dir(TAG + "_client"))
        x.host.spawn(); x.client.spawn(); x.host.connect(); x.client.connect()
        squad = session.bring_up_separate_guest_battle(x.host, x.client, port=KEY)
        t0, tops = time.time(), None
        while time.time() - t0 < 60.0:
            tops = [stack(x.host)[-1:], stack(x.client)[-1:]]
            if tops == [[BS], [BS]]:
                break
            time.sleep(POLL)
        if tops != [[BS], [BS]]:
            raise RuntimeError("both tops BattlescapeState not reached within 60 s: %s" % tops)
        units = x.client.cmd({"cmd": "battle_state"}).get("units") or []
        g = [u for u in units if u.get("coop") == 1]
        if len(g) != 1:
            raise RuntimeError("the client's coop-1 units: %s (want exactly one, the guest)" % [u.get("id") for u in g])
        x.G, x.T = g[0]["id"], (g[0]["x"], g[0]["y"], g[0]["z"])
        own = sorted((it for it in x.client.cmd({"cmd": "battle_items"}).get("items") or [] if it.get("owner") == x.G),
                     key=lambda it: it["id"])
        if not own:
            raise RuntimeError("G %s owns no item in the client's battle_items" % x.G)
        x.I = own[0]["id"]
        x.cr0 = session._crash_log_snapshot()
        print("EVIDENCE boot: %s" % json.dumps({"squad": squad, "tops s": round(time.time() - t0, 2), "G": x.G, "G name": g[0].get("name"),
                                                 "I": x.I, "I type": own[0].get("type"), "T": x.T,
                                                 "client faction-0 (id, coop)": [[u.get("id"), u.get("coop")] for u in units
                                                                                 if u.get("faction") == 0]},
                                                default=str), flush=True)
    except Exception as e:
        x.err = short(e, 600)
        capture(x, "boot")
    return x


def row_s0(x, results, walls):
    r, c = Row("S0", S0_CELLS, x), x.client
    if x.err:
        r.rest("boot (%s)" % x.err[:160])
        return r.end(results, walls)
    b = q(c, {"cmd": "battle_state"})
    r.cell("S0-state", "GUARD", "client battle_state on its live screen: ok, hud present, cursorType != -1, pendingStates an int",
           b.get("ok") is True and "hud" in b and b.get("cursorType") not in (None, -1) and type(b.get("pendingStates")) is int,
           {k: b.get(k) for k in list(S1_STATE) + ["hud", "error", "probeError"] if k in b})
    t = {"x": x.T[0], "y": x.T[1], "z": x.T[2]}
    s = q(c, dict(t, cmd="map_tile_screen_pos"))
    r.cell("S0-screen", "GUARD", "client map_tile_screen_pos %s: no error" % (x.T,), "error" not in s and "probeError" not in s, s)
    u = q(c, {"cmd": "can_use_weapon", "unit": x.G, "item": x.I, "action": "snap"})
    r.cell("S0-canuse", "GUARD", "client can_use_weapon {unit %s, item %s, snap}: no error, canUse present" % (x.G, x.I),
           "error" not in u and "probeError" not in u and "canUse" in u, u)
    m = q(c, dict(t, cmd="battle_camera_center"))
    r.cell("S0-camera", "GUARD", "client battle_camera_center %s: no error" % (x.T,), "error" not in m and "probeError" not in m, m)
    r.end(results, walls)


def s1_probe(x, obj):
    """one S1 probe and its ping -> (reply, pong); raises Gone (no retry, no reconnect)"""
    for o in (obj, {"cmd": "ping"}):
        try:
            rep = x.client.cmd(o)
        except Exception as e:
            x.gone = "%s%s raised %s" % ("ping after " if o is not obj else "", obj["cmd"], short(e, 200))
            raise Gone(x.gone)
        if o is obj:
            first = rep
    return first, rep


def row_s1(x, results, walls):
    r, h, c = Row("S1", S1_CELLS, x), x.host, x.client
    if x.err:
        r.rest("boot (%s)" % x.err[:160])
        return r.end(results, walls)
    ev = {"disconnect_to_menu": q(h, {"cmd": "disconnect_to_menu"})}
    t0 = time.time()
    while time.time() - t0 < 15.0:
        if dlg(c).get("code") == 21 and stack(c):
            ev["dialog 21 s"] = round(time.time() - t0, 2)
            break
        time.sleep(POLL)
    if "dialog 21 s" in ev:
        time.sleep(2.0)
    pre, hs = safe4(c), stack(h)
    ev.update(client=pre, host_stack=hs)
    d = pre["coop_dialog_info"]
    ok = (ev["disconnect_to_menu"].get("ok") is True and "dialog 21 s" in ev and pre["stack"] == [GOTO, CS] and d.get("code") == 21
          and d.get("title") == "Server connection lost" and pre["get_coop"].get("inBattle") is True
          and pre["world_state"].get("has_battle") is True and hs[-1:] == [MENU])
    r.cell("S1-pre", "GUARD", "the window: host disconnect_to_menu ok and top MainMenuState; within 15 s (+2.0 s) the client on "
           "[GoToMainMenuState, CoopState], dialog 21 \"Server connection lost\", get_coop.inBattle true, world_state.has_battle true", ok, ev)
    if not ok:
        r.rest("not reached (S1-pre missed: the stale window was not reached)")
        return r.end(results, walls)
    t = {"x": x.T[0], "y": x.T[1], "z": x.T[2]}
    cells = (
        ("S1-state", "client battle_state: ok, inBattle true, isBusy false, pendingStates 0, panicHandled false, currentActionActorId -1, "
         "mouseOverIcons false, cursorType -1, hiddenMovementShown false, the banner texts \"\" and flags false, no hud key; ping answers",
         {"cmd": "battle_state"},
         lambda p: all(p.get(k) == v and type(p.get(k)) is type(v) for k, v in S1_STATE.items()) and "hud" not in p),
        ("S1-screen", "client map_tile_screen_pos %s: error exactly \"no BattlescapeState\"; ping answers" % (x.T,),
         dict(t, cmd="map_tile_screen_pos"), lambda p: p.get("error") == "no BattlescapeState"),
        ("S1-canuse", "client can_use_weapon {unit %s, item %s, snap}: error exactly \"can_use_weapon: no live battle\"; ping answers"
         % (x.G, x.I), {"cmd": "can_use_weapon", "unit": x.G, "item": x.I, "action": "snap"},
         lambda p: p.get("error") == "can_use_weapon: no live battle"),
        ("S1-camera", "client battle_camera_center %s: error exactly \"battle_camera_center: no BattlescapeState\"; ping answers" % (x.T,),
         dict(t, cmd="battle_camera_center"), lambda p: p.get("error") == "battle_camera_center: no BattlescapeState"),
        ("S1-panic", "client battle_set_unit_state {unit %s, panicPending true}: error exactly \"battle_set_unit_state: no live "
         "BattlescapeGame\"; ping answers; 0 new crash files in this lane's crash folder since the baseline" % x.G,
         {"cmd": "battle_set_unit_state", "unit": x.G, "panicPending": True},
         lambda p: p.get("error") == "battle_set_unit_state: no live BattlescapeGame"),
    )
    for cid, label, obj, check in cells:
        if x.gone:
            ok, evc, label = False, {"client gone": x.gone}, "client gone (%s)" % x.gone[:160]
        else:
            try:
                rep, pong = s1_probe(x, obj)
                shown = {k: rep.get(k) for k in list(S1_STATE) + ["hud", "error"] if k in rep} if cid == "S1-state" else rep
                ok, evc = check(rep) and pong.get("pong") is True, {"reply": shown, "ping": pong}
            except Gone as e:
                ok, evc, label = False, {"client gone": str(e)}, "client gone (%s)" % str(e)[:160]
        if cid == "S1-panic":
            evc["new crash files"] = new_crashes(x)
            ok = ok and not evc["new crash files"]
        r.cell(cid, "RED", label, ok, evc)
        x.red_failed = x.red_failed or not ok
    out = {}
    if alive(c) and not x.gone:
        out["coop_dialog_back"] = q(c, {"cmd": "coop_dialog_back"})
        t1, out["MainMenuState s"] = time.time(), None
        while time.time() - t1 < 30.0:
            if stack(c)[-1:] == [MENU]:
                out["MainMenuState s"] = round(time.time() - t1, 2)
                break
            time.sleep(POLL)
        out["client world_state"] = safe4(c)["world_state"]
    else:
        out["client"] = "gone (%s)" % x.gone
    out["host ping"] = q(h, {"cmd": "ping"})
    print("EVIDENCE S1 exit (EVIDENCE only): %s" % json.dumps(out, sort_keys=True, default=str), flush=True)
    r.end(results, walls)


def shut(x):
    """both machines; a client dead after an S1 RED cell failed is reaped with its own exit code -> the shutdown failures"""
    failed = []
    for gc in (x.client, x.host):
        if gc is None or gc.proc is None:
            continue
        try:
            if gc is x.client and x.gone and alive(gc):
                try:  # a client gone in S1 may still be inside its crash handler: give it the harness's own 15 s
                    gc.proc.wait(timeout=15)
                except Exception:
                    pass
            if gc is x.client and x.red_failed and not alive(gc):
                rc = gc.proc.poll()
                print("EVIDENCE shutdown client: dead after an S1 RED cell failed (%s), exit code %s; reaped with it" % (x.gone, rc),
                      flush=True)
                gc.shutdown(expected_returncodes=(rc,))
            else:
                gc.shutdown()
        except Exception as e:
            print("FAIL shutdown (%s): %s" % (gc.name, short(e)), flush=True)
            failed.append("shutdown " + gc.name)
    return failed


def main():
    t0, results, walls = time.time(), {}, {}
    x = boot()
    walls["boot"] = round(time.time() - t0, 1)
    row_s0(x, results, walls)
    row_s1(x, results, walls)
    failed = shut(x) + [rid for rid in ("S0", "S1") if not results.get(rid)]
    print("\ntest_stale_screen_probe: %d/2 rows passed (fail=%s) walls %s in %.1fs"
          % (sum(1 for rid in ("S0", "S1") if results.get(rid)), failed, json.dumps(walls), time.time() - t0), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
