"""OF2 S-A - a battle mod script on the second player's soldier reads the research of the player who owns it
(owner D263 (a), D258 (b); spec docs rewrite/prompts/of2_mod_script_player_reads.md, AMENDMENT OF2-1 section 6;
TASK 0 docs rewrite/of2-task0/sa/CONSTANTS.md; F1375, F11470-F11480, F11920-F11939).
In a SEPARATE campaign with research sync off each player has its own research. Every battle-rule mod script
today reads the HOST's research, also for the second player's soldier. The test MOD Coop_ScriptResearch_Test
(both machines) writes one BattleUnit tag per hook = 1 + isResearched(STR_PLASMA_PISTOL), read through
battle_game.getGeoscapeGame: 0 = the hook never ran, 1 = the host's research (not researched), 2 = the second
player's (researched). The client researched STR_PLASMA_PISTOL, the host did not (CR's boot).
ONE boot (test_w2_client_research's research-separate guest battle, lobby key 48998, the MOD on both machines);
four rows in this order:
  SR0  after battle entry, before any order: SR0-all (every live unit's COOP_SR_TURN == 1 on both machines: the
       first turn's newTurnUnit ran before the second player's research list was stored, VL-OF2-2), SR0-common.
  SR1  one turn round (test_w2_delta_core.end_turn_cycle, aliens under pin_ai_neutral): SR1-G (G's COOP_SR_TURN
       == 2 on both), SR1-H (H's == 1 on both), SR1-common.
  SR2  the client presses G's mod skill (TAB, SKILLS by rect, KEY_SKILL), then the host presses H's: SR2-G (G's
       COOP_SR_SKILL == 2 on both), SR2-H (H's == 1 on both), SR2-intent (the host's intentsReceivedLog holds G's
       skill), SR2-common.
  SR3  LAST (it stuns G and H): host battle_action kill_unit_real {stun} on G, then on H: SR3-G (G's COOP_SR_HIT /
       DMG / SPEC == 2 on both), SR3-H (H's == 1 on both), SR3-state (both stunned, not dead, battle running),
       SR3-common.
Common cell (every row): after wait_host_idle, test_w2_client_shoot.common_fails empty (hash_now full every bucket
EQUAL, desyncSeen false on both, the client's coopClientBStatePushes unchanged and the host's 0), every live unit's
tags equal on both machines (field_poke peek), and no crash file since the boot.
RED (commit A1, unchanged build): exactly SR1-G, SR2-G, SR3-G FAIL (G reads 1). GREEN (A2): every cell PASS.
Each row prints ONE "EVIDENCE <row>:" line, one PASS/FAIL line per cell, then its verdict; every row runs after a
failure. A boot failure prints ONE "CAPTURE boot:" line and fails every row "boot"; a missed construction step
prints ONE "CAPTURE <row>:" line and fails that row's cells.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, 2 otherwise.
Run:  python tools/coop_test/test_w2_script_research.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral
import test_w2_client_research as CR
from test_w2_client_shoot import snap, common_fails, await_press, press, menu_rows
from test_w2_client_grenade import cancel_client_targeting
from test_w2_delta_core import end_turn_cycle, both, short
from test_rw_turn_baton import click_nth
from test_rw_seat_pacing import tab_select

PORT = "48998"
HOST_DIR, CLIENT_DIR = "of2_script_research_host", "of2_script_research_client"
MOD_NAME = "Coop_ScriptResearch_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_ScriptResearch_Test v1.0"
SKILL = "STR_COOP_TEST_SR_SKILL"
SKILLS_RECT = (288, 25, 32, 24)   # found by rect: its nth moves per boot (28 / 29, F11478)
KEY_SKILL = 49                    # the first (only) skill row
# raw field_poke tag index = the MOD's definition order, equal on both machines (F11472)
TAG_TURN, TAG_SKILL, TAG_HIT, TAG_DMG, TAG_SPEC = 0, 1, 2, 3, 4
TAG_NAMES = {TAG_TURN: "COOP_SR_TURN", TAG_SKILL: "COOP_SR_SKILL", TAG_HIT: "COOP_SR_HIT", TAG_DMG: "COOP_SR_DMG",
             TAG_SPEC: "COOP_SR_SPEC"}
HOST_R, OWNER_R = 1, 2            # 1 + isResearched(STR_PLASMA_PISTOL): the host's research / the second player's
MIN_LIVE_PLAYERS = 3              # SR3 stuns G and H; the battle must keep running (F11032)
STATUS_UNCONSCIOUS = 7
SCRIPT_S = 2.0                    # the host's own skill script ran (TASK 0: 0.1 s)
FOLLOW_S = 5.0                    # the client's tags follow the host's (TASK 0: SR2-H 0.55 / 0.56 s)
STUN_FOLLOW_S = 10.0              # SR3 (TASK 0: 1.31 s after the lever)
POLL_S = 0.1
MENU_S = 5.0
CELLS = {"SR0": ("SR0-all", "SR0-common"), "SR1": ("SR1-G", "SR1-H", "SR1-common"),
         "SR2": ("SR2-G", "SR2-H", "SR2-intent", "SR2-common"),
         "SR3": ("SR3-G", "SR3-H", "SR3-state", "SR3-common")}


def pairs(host, client):
    return (("host", host), ("client", client))


def tags(gc, uid):   # field_poke peek: the unit's raw tag list, trailing zeros trimmed
    r = gc.cmd({"cmd": "field_poke", "class": "unit", "id": uid, "field": "tags"})
    return r.get("before") if r.get("ok") else {"error": r.get("error")}


def tag_val(t, idx):
    if not isinstance(t, list):
        return None
    return t[idx] if len(t) > idx else 0


def all_tags(gc):
    return {u["id"]: tags(gc, u["id"]) for u in battle_state(gc).get("units", []) if not u.get("isOut")}


def unit(gc, uid):
    u = session.units_by_id(battle_state(gc)).get(uid) or {}
    return {k: u.get(k) for k in ("id", "coop", "health", "stun", "status", "isOut")}


def live_players(gc):
    return sorted(u["id"] for u in battle_state(gc).get("units", []) if u.get("isPlayerSoldier") and not u.get("isOut"))


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def skills_nth(gc):
    vis = [w for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("visible") and w.get("interactive")]
    return next((n for n, w in enumerate(vis) if (w.get("x"), w.get("y"), w.get("w"), w.get("h")) == SKILLS_RECT), None)


def capture(host, client, what):
    cap = {}
    for n, gc in pairs(host, client):
        cap[n] = {"log": log_lines(gc)[-40:]}
        for c in ("get_state", "battle_state", "event_state", "coop_dialog_info"):
            try:
                cap[n][c] = gc.cmd({"cmd": c})
            except Exception as e:
                cap[n][c] = f"error {short(e)}"
    print(f"CAPTURE {what}: {json.dumps(cap, default=str)}", flush=True)


def joined(fails):
    return "; ".join(fails) or None


def common(host, client, before, what, crash0):
    fails = []
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        fails.append(f"wait_host_idle: {short(e)}")
    fails += common_fails(host, client, before, what)
    th, tc = all_tags(host), all_tags(client)
    if th != tc:
        diff = [(k, th.get(k), tc.get(k)) for k in sorted(set(th) | set(tc)) if th.get(k) != tc.get(k)]
        fails.append(f"live unit tags differ between the machines (id, host, client): {diff}")
    new = sorted(session._crash_log_snapshot() - crash0)
    return fails + ([f"new crash file(s) {new}"] if new else [])


def tag_cell(name, uid, vals, idxs, want):
    """vals = {"host": tags, "client": tags}: every tag in idxs == want on BOTH machines (0 = the hook never ran)."""
    f = []
    for i in idxs:
        h, c = tag_val(vals["host"], i), tag_val(vals["client"], i)
        if not (h == c == want):
            f.append(f"{name} ({uid}) {TAG_NAMES[i]} host {h} client {c} (want {want} on both; 0 = the hook never "
                     f"ran, {HOST_R} = the host's research, {OWNER_R} = the second player's)")
    return joined(f)


def boot(host, client):   # = CR's boot (CR :1525-:1576) with lobby key PORT, plus OF2's boot guards
    ctx, pre_rec = {}, {}

    def pre(h, c):
        for gc, topics in ((c, CR.CLIENT_TOPICS), (h, CR.HOST_TOPICS), (c, CR.PEDIA_CLIENT_TOPICS),
                           (h, CR.PEDIA_HOST_TOPICS)):
            for t in topics:
                gc.ok({"cmd": "discover_research", "topic": t})
        pre_rec["isr"] = CR.isr_all(h, c)
        pre_rec["Nh"] = (CR.rmode(h) or {}).get("liveCount")
        pre_rec["Nc"] = (CR.rmode(c) or {}).get("liveCount")

    for gc in (host, client):
        gc.spawn()
        gc.connect()
    session.bring_up_separate_guest_battle(host, client, port=PORT, pre_mission_start=pre)
    session.wait_host_idle(host, client, timeout=30)
    ctx["preIsr"], ctx["Nh"], ctx["Nc"] = pre_rec.get("isr"), pre_rec.get("Nh"), pre_rec.get("Nc")
    hs, cs = battle_state(host), battle_state(client)
    gh = [u for u in hs.get("units", []) if u.get("name") == CR.GUEST_NAME]
    gc_ = [u for u in cs.get("units", []) if u.get("name") == CR.GUEST_NAME]
    assert len(gh) == 1 and len(gc_) == 1 and gh[0]["id"] == gc_[0]["id"] and gh[0].get("coop") == 1, (
        f"guest by name: host={[(u.get('id'), u.get('coop')) for u in gh]} "
        f"client={[(u.get('id'), u.get('coop')) for u in gc_]} (want one, the same id, coop 1)")
    ctx["G"], ctx["gTile"] = gh[0]["id"], (gh[0]["x"], gh[0]["y"], gh[0]["z"])
    hsold = sorted(u["id"] for u in hs.get("units", []) if u.get("isPlayerSoldier") and u.get("coop") == 0
                   and u.get("name") != CR.GUEST_NAME and not u.get("isOut"))
    assert hsold, "no host soldier (coop 0, not out)"
    ctx["H"] = hsold[0]
    pinned = pin_ai_neutral(host, client, tag="of2-sr")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": ctx["G"], "stat": "firing",
                        "value": CR.FIRING_PIN}, ("tu",))
    guard = {}
    for n, gc in pairs(host, client):
        m = CR.rmode(gc)
        lines = log_lines(gc)
        guard[n] = {"mode": {k: (m or {}).get(k) for k in CR.MODE_WANT}, "seat1": CR.seat_entry(m, 1),
                    "live": live_players(gc), "modActive": sum(1 for ln in lines if MOD_ACTIVE_LINE in ln),
                    "errors": [ln for ln in lines if "[ERROR]" in ln][:5]}
        g = guard[n]
        assert g["mode"] == CR.MODE_WANT, f"{n} researchMode {g['mode']} (want {CR.MODE_WANT})"
        assert (g["seat1"] or {}).get("stored") is True, f"{n} seats[1] {g['seat1']} (want stored true)"
        assert len(g["live"]) >= MIN_LIVE_PLAYERS, f"{n} live player soldiers {g['live']} (want >= {MIN_LIVE_PLAYERS})"
        assert g["modActive"] >= 1 and not g["errors"], (
            f"{n} log: {g['modActive']} line(s) with {MOD_ACTIVE_LINE!r}, [ERROR] lines {g['errors']} "
            "(want >= 1 and none)")
    ctx["localSeat"] = event_state(client).get("localSeat")
    assert ctx["localSeat"] == 1, f"client localSeat {ctx['localSeat']} (want 1)"
    session.wait_host_idle(host, client, timeout=30)
    session.assert_hash_clean(host, client, full=True, what="bring-up")
    ctx["guard"], ctx["pinned"] = guard, len(pinned)
    ctx["mapFP"], ctx["turn"] = hs.get("mapFingerprint"), hs.get("turn")
    return ctx


def row_sr0(ev, res, host, client, st):
    ev["boot"] = st["ctx"]
    th, tc = all_tags(host), all_tags(client)
    ev["live"] = len(th)
    ev["turnTag"] = {n: sorted({json.dumps(tag_val(v, TAG_TURN)) for v in t.values()})
                     for n, t in (("host", th), ("client", tc))}
    ev["G"] = {"host": th.get(st["G"]), "client": tc.get(st["G"])}
    ev["H"] = {"host": th.get(st["H"]), "client": tc.get(st["H"])}
    f = [f"{n} unit {uid} {TAG_NAMES[TAG_TURN]} {tag_val(v, TAG_TURN)} (want {HOST_R}; 0 = the MOD did not run)"
         for n, t in (("host", th), ("client", tc)) for uid, v in sorted(t.items()) if tag_val(v, TAG_TURN) != HOST_R]
    if not th:
        f.append("no live unit on the host")
    res["SR0-all"] = joined(f)
    res["SR0-common"] = joined(common(host, client, st["bootSnap"], "SR0", st["crash0"]))


def row_sr1(ev, res, host, client, st):
    G, H = st["G"], st["H"]
    before, notes = snap(host, client), []
    turn0 = battle_state(host).get("turn")
    t = time.time()
    end_turn_cycle(host, client, notes)
    ev["wall"], ev["notes"], ev["turn0"] = round(time.time() - t, 2), notes, turn0
    ev["after"] = view = {n: {"turn": battle_state(gc).get("turn"), "side": battle_state(gc).get("side"),
                              "top": session.top_state(gc)} for n, gc in pairs(host, client)}
    miss = list(notes) + [f"{n} turn {v['turn']} side {v['side']} top {v['top']} (want turn {turn0 + 1}, side 0, "
                          "BattlescapeState)" for n, v in view.items()
                          if v["turn"] != turn0 + 1 or v["side"] != 0 or v["top"] != "BattlescapeState"]
    if miss:
        capture(host, client, "SR1")
        res.update({c: f"construction: {joined(miss)}" for c in CELLS["SR1"]})
        return
    ev["G"] = gv = {n: tags(gc, G) for n, gc in pairs(host, client)}
    ev["H"] = hv = {n: tags(gc, H) for n, gc in pairs(host, client)}
    res["SR1-G"] = tag_cell("G", G, gv, (TAG_TURN,), OWNER_R)
    res["SR1-H"] = tag_cell("H", H, hv, (TAG_TURN,), HOST_R)
    res["SR1-common"] = joined(common(host, client, before, "SR1", st["crash0"]))


def open_skills(gc, uid, ev):
    """TAB-select `uid`, cancel a client's leftover targeting, click SKILLS by rect, SkillMenuState on top within
    MENU_S with one skill row. Fills `ev`; returns why the construction missed, or None."""
    ev["tab"] = tab_select(gc, uid)
    if not ev["tab"]:
        return f"TAB never selected {uid} on the {gc.name} (selectedId {battle_state(gc).get('selectedId')})"
    if gc.name == "client":
        ev["targeting"] = cancel_client_targeting(gc)
    ev["skillsNth"] = nth = skills_nth(gc)
    if nth is None:
        return f"no visible interactive widget at SKILLS_RECT {SKILLS_RECT} on the {gc.name}"
    r = click_nth(gc, nth)
    ev["click"] = (r.get("baseX"), r.get("baseY"))
    try:
        gc.wait_for(f"{gc.name} SkillMenuState", lambda: session.top_state(gc) == "SkillMenuState" or None,
                    timeout=MENU_S, interval=POLL_S)
    except Exception as e:
        return f"SkillMenuState not on top of the {gc.name} within {MENU_S} s: {short(e)}"
    ev["rows"] = menu_rows(gc)
    return None if ev["rows"] == 1 else f"menu_rows({gc.name}) {ev['rows']} (want 1)"


def row_sr2(ev, res, host, client, st):
    G, H = st["G"], st["H"]
    before = snap(host, client)
    seen = max([e.get("iseq", 0) for e in event_state(host).get("intentsReceivedLog") or []] or [0])
    ev["client"], ev["host"] = cev, hev = {}, {}
    miss = open_skills(client, G, cev)
    if not miss:   # the client presses G's skill: the order path (D147: the host runs the script)
        b2, notes = snap(host, client), []
        press(client, KEY_SKILL)
        cev["out"] = out = await_press(host, client, b2, notes)
        try:
            session.wait_host_idle(host, client, timeout=30)
        except Exception as e:
            notes.append(f"wait_host_idle: {short(e)}")
        cev["notes"] = notes
        if out.get("state") != "sent":
            miss = f"the client's skill order: await_press {out} (want state sent); notes {notes}"
    if not miss:   # the host presses H's skill (W2-H28: one host action, its ev carries the tag)
        miss = open_skills(host, H, hev)
    if not miss:
        t0 = time.time()
        press(host, KEY_SKILL)
        while time.time() - t0 < SCRIPT_S and not tag_val(tags(host, H), TAG_SKILL):
            time.sleep(POLL_S)
        hev["tScript"] = round(time.time() - t0, 2)
        while time.time() - t0 < FOLLOW_S and tags(client, H) != tags(host, H):
            time.sleep(POLL_S)
        hev["tFollow"] = round(time.time() - t0, 2)
        try:
            host.wait_for("host BattlescapeState after the press",
                          lambda: session.top_state(host) == "BattlescapeState" or None,
                          timeout=MENU_S, interval=POLL_S)
        except Exception as e:
            miss = f"host top {session.top_state(host)} after its skill press (want BattlescapeState): {short(e)}"
    if miss:
        capture(host, client, "SR2")
        res.update({c: f"construction: {miss}" for c in CELLS["SR2"]})
        return
    logn = [e for e in event_state(host).get("intentsReceivedLog") or [] if e.get("iseq", 0) > seen]
    ev["intentLogNew"] = logn
    ev["G"] = gv = {n: tags(gc, G) for n, gc in pairs(host, client)}
    ev["H"] = hv = {n: tags(gc, H) for n, gc in pairs(host, client)}
    res["SR2-G"] = tag_cell("G", G, gv, (TAG_SKILL,), OWNER_R)
    res["SR2-H"] = tag_cell("H", H, hv, (TAG_SKILL,), HOST_R)
    got = [(e.get("kind"), e.get("actorId"), e.get("skill")) for e in logn]
    res["SR2-intent"] = (None if got == [("skill", G, SKILL)] else
                         f"host intentsReceivedLog new {logn} (want one {{kind skill, actorId {G}, skill {SKILL}}})")
    res["SR2-common"] = joined(common(host, client, before, "SR2", st["crash0"]))


def stun(host, client, uid, rec):
    """Host kill_unit_real {stun} on `uid`, then the F11477 settle: host not busy with pendingStates 0, status
    STATUS_UNCONSCIOUS on both, wait_host_idle, the client's tags equal the host's. Returns a construction miss."""
    t0 = time.time()
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid, "stun": True})
    rec["reply"] = {k: r.get(k) for k in ("ok", "killed", "error")}
    if not r.get("ok") or r.get("killed") != [uid]:
        return f"kill_unit_real {{unit {uid}, stun true}} answered {rec['reply']} (want ok, killed [{uid}])"
    waits = (("host not busy, pendingStates 0", lambda: (lambda b: b.get("isBusy") is False
              and b.get("pendingStates") == 0)(battle_state(host)), 30),
             ("status unconscious on both", lambda: unit(host, uid).get("status") == STATUS_UNCONSCIOUS
              and unit(client, uid).get("status") == STATUS_UNCONSCIOUS, 30))
    for what, fn, to in waits:
        try:
            host.wait_for(what, lambda: fn() or None, timeout=to, interval=POLL_S)
        except Exception as e:
            rec.setdefault("waits", []).append(f"{what}: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        rec.setdefault("waits", []).append(f"wait_host_idle: {short(e)}")
    while time.time() - t0 < STUN_FOLLOW_S and tags(client, uid) != tags(host, uid):
        time.sleep(POLL_S)
    rec["tFollow"] = round(time.time() - t0, 2)
    rec["unit"] = {n: unit(gc, uid) for n, gc in pairs(host, client)}
    return None


def row_sr3(ev, res, host, client, st):
    G, H = st["G"], st["H"]
    before = snap(host, client)
    ev["G"], ev["H"] = grec, hrec = {}, {}
    miss = stun(host, client, G, grec) or stun(host, client, H, hrec)
    if miss:
        capture(host, client, "SR3")
        res.update({c: f"construction: {miss}" for c in CELLS["SR3"]})
        return
    gv = grec["tags"] = {n: tags(gc, G) for n, gc in pairs(host, client)}
    hv = hrec["tags"] = {n: tags(gc, H) for n, gc in pairs(host, client)}
    res["SR3-G"] = tag_cell("G", G, gv, (TAG_HIT, TAG_DMG, TAG_SPEC), OWNER_R)
    res["SR3-H"] = tag_cell("H", H, hv, (TAG_HIT, TAG_DMG, TAG_SPEC), HOST_R)
    f = list(grec.get("waits", [])) + list(hrec.get("waits", []))
    for name, uid in (("G", G), ("H", H)):
        for n, gc in pairs(host, client):
            u = unit(gc, uid)
            if u.get("status") != STATUS_UNCONSCIOUS or u.get("isOut") is not True or not (u.get("health") or 0) > 0:
                f.append(f"{n} {name} ({uid}) {u} (want status {STATUS_UNCONSCIOUS}, isOut true, health > 0)")
    ev["live"] = live = {n: live_players(gc) for n, gc in pairs(host, client)}
    ev["stack"] = stack = {n: session.states_stripped(gc) for n, gc in pairs(host, client)}
    if not live["host"] or live["host"] != live["client"]:
        f.append(f"live player soldiers host {live['host']} client {live['client']} (want equal, >= 1)")
    for n, s in stack.items():
        if "BattlescapeState" not in s or "DebriefingState" in s:
            f.append(f"{n} state stack {s} (want the battle running: BattlescapeState, no DebriefingState)")
    res["SR3-state"] = joined(f)
    res["SR3-common"] = joined(common(host, client, before, "SR3", st["crash0"]))


ROWS = (("SR0", row_sr0), ("SR1", row_sr1), ("SR2", row_sr2), ("SR3", row_sr3))


def report(rid, ev, res):
    print(f"EVIDENCE {rid}: {json.dumps(ev, default=str)}", flush=True)
    for c in CELLS[rid]:
        f = res.get(c, "not reached")
        print(f"PASS {c}" if f is None else f"FAIL {c}: {f}", flush=True)
    bad = [c for c in CELLS[rid] if res.get(c, "not reached") is not None]
    print(f"PASS {rid}" if not bad else f"FAIL {rid}: {', '.join(bad)}", flush=True)
    return bad


def run_row(rid, fn, host, client, st):
    ev, res = {}, {}
    try:
        fn(ev, res, host, client, st)
    except Exception as e:
        ev["error"] = msg = short(e, 500)
        for c in CELLS[rid]:
            res.setdefault(c, f"the row raised before this cell: {msg}")
    return report(rid, ev, res)


def main():
    t_start = time.time()
    host = GameClient("host", 1, make_user_dir(HOST_DIR, mods=[MOD_DIR], options=CR.HOST_OPTIONS))
    client = GameClient("client", 2, make_user_dir(CLIENT_DIR, mods=[MOD_DIR], options=CR.CLIENT_OPTIONS))
    failed = []
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:
            print(f"boot failed: {short(e, 600)}", flush=True)
            capture(host, client, "boot")
            for rid, _ in ROWS:
                failed += report(rid, {"error": "boot"}, {c: "boot" for c in CELLS[rid]})
        else:
            st = {"ctx": ctx, "G": ctx["G"], "H": ctx["H"], "crash0": session._crash_log_snapshot(),
                  "bootSnap": snap(host, client)}
            for rid, fn in ROWS:
                failed += run_row(rid, fn, host, client, st)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[of2-sr] shutdown {gc.name}: {short(e)}", flush=True)
    n = sum(len(v) for v in CELLS.values())
    print(f"\ntest_w2_script_research: {n - len(failed)}/{n} cells passed (fail={failed}) in "
          f"{round(time.time() - t_start, 1)} s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
