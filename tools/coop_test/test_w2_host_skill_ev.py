"""W2-H28 S-A - the host's own soldier-skill press reaches the second player in one host action (spec docs
rewrite/prompts/w2h28_host_skill_use_ev.md (f); TASK 0 docs rewrite/w2h28-task0/CONSTANTS.md; R-OF2-A-1; F11475,
F11561, F11564). The HOST's own press runs the skill's script on the host only and emits nothing, so the second
player keeps the soldier's old values (and hash_now differs) until the host's next ev of any kind.
ONE boot, OF2's measured fixture (test_w2_client_research's research-separate guest battle, lobby key 48987, OF2's
MOD Coop_ScriptResearch_Test on both machines); four rows in this order:
  HS0  bring-up: HS0-mod (mod-active line, 0 [ERROR] lines), HS0-units (G, H, live tags equal), HS0-common.
  HC   end_turn_cycle to turn 2: HC-turn (turn + 1, side 0, BattlescapeState on top of both), HC-common.
  HG   control, the second player's own skill order (TAB to G, SKILLS by rect, KEY_SKILL): HG-sent, HG-ctx
       ({intent, skill, G}; the host's intentsReceivedLog entry), HG-tags (equal, TAG_SKILL non-zero), HG-common.
  HH   the host's own skill press (TAB to H, SKILLS by rect, KEY_SKILL), LAST (its red leaves the split standing):
       HH-script (the host ran the script), HH-ev (one {host, skill, H} context whose evs are exactly [skill,
       bt_action_end], lastCue on both, no RW-UNSUPPORTED / "has no known actor" client line), HH-follow (the
       client's H tags equal the host's within FOLLOW_S, both H_TAGS_AFTER), HH-hash, HH-common.
Common cell: after wait_host_idle, test_w2_client_shoot.common_fails empty and no crash file since the boot.
RED (commit A1, unchanged build): exactly HH-ev, HH-follow, HH-hash FAIL. GREEN (A2): every cell PASS.
Each row prints ONE "EVIDENCE <row>:" line, one PASS/FAIL line per cell, then its verdict; every row runs after a
failure. A boot failure prints ONE "CAPTURE boot:" line and fails every row "boot"; a missed construction step
prints ONE "CAPTURE <row>:" line and fails that row's cells.
WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, 2 otherwise.
Run:  python tools/coop_test/test_w2_host_skill_ev.py
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
from test_w2_client_shoot import snap, probes, common_fails, await_press, press, menu_rows, new_contexts, mine
from test_w2_client_grenade import cancel_client_targeting
from test_w2_delta_core import end_turn_cycle, both, short, diff_buckets
from test_w2_host_combat import evs_since
from test_rw_turn_baton import click_nth
from test_rw_seat_pacing import tab_select

PORT = "48987"
HOST_DIR, CLIENT_DIR = "w2h28_host_skill_host", "w2h28_host_skill_client"
MOD_NAME = "Coop_ScriptResearch_Test"
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_ScriptResearch_Test v1.0"
SKILL = "STR_COOP_TEST_SR_SKILL"
SKILLS_RECT = (288, 25, 32, 24)   # found by rect: its nth moves per boot (29 / 28, F11478)
KEY_SKILL = 49                    # the first (only) skill row
TAG_SKILL = 1                     # COOP_SR_SKILL's raw index (F11472)
SCRIPT_S = 2.0                    # the host ran the script (TASK 0: 0.1 s on both boots)
FOLLOW_S = 5.0
POLL_S = 0.1
MENU_S = 5.0
H_TAGS_AFTER = [1, 1]             # CONSTANTS.md: host after its press, client after the next ev (Ha, Hb)
HASH_FAIL = "hash_now full not clean"
CELLS = {"HS0": ("HS0-mod", "HS0-units", "HS0-common"), "HC": ("HC-turn", "HC-common"),
         "HG": ("HG-sent", "HG-ctx", "HG-tags", "HG-common"),
         "HH": ("HH-script", "HH-ev", "HH-follow", "HH-hash", "HH-common")}


def pairs(host, client):
    return (("host", host), ("client", client))


def tags(gc, uid):   # field_poke peek: the unit's raw tag list, trailing zeros trimmed
    r = gc.cmd({"cmd": "field_poke", "class": "unit", "id": uid, "field": "tags"})
    return r.get("before") if r.get("ok") else {"error": r.get("error")}


def tag_on(t):
    return isinstance(t, list) and len(t) > TAG_SKILL and t[TAG_SKILL] != 0


def all_tags(gc):
    return {u["id"]: tags(gc, u["id"]) for u in battle_state(gc).get("units", []) if not u.get("isOut")}


def tu(gc, uid):
    return (session.units_by_id(battle_state(gc)).get(uid) or {}).get("tu")


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


def common(host, client, before, what, crash0):
    fails = []
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        fails.append(f"wait_host_idle: {short(e)}")
    fails += common_fails(host, client, before, what)
    new = sorted(session._crash_log_snapshot() - crash0)
    return fails + ([f"new crash file(s) {new}"] if new else [])


def joined(fails):
    return "; ".join(fails) or None


def open_skills(gc, uid, ev):
    """TAB-select `uid`, cancel a client's leftover targeting, click SKILLS by rect, SkillMenuState on top within
    MENU_S. Fills `ev`; returns why the construction missed, or None."""
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
    return None


def boot(host, client):   # OF2 t0.py boot() (= CR's boot) with lobby key PORT
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
    assert len(gh) == 1 and len(gc_) == 1 and gh[0]["id"] == gc_[0]["id"], (
        f"guest by name: host={[u.get('id') for u in gh]} client={[u.get('id') for u in gc_]}")
    ctx["G"], ctx["gTile"] = gh[0]["id"], (gh[0]["x"], gh[0]["y"], gh[0]["z"])
    hsold = sorted(u["id"] for u in hs.get("units", []) if u.get("isPlayerSoldier") and u.get("coop") == 0
                   and u.get("name") != CR.GUEST_NAME and not u.get("isOut"))
    assert hsold, "no host soldier (coop 0, not out)"
    ctx["H"] = hsold[0]
    pinned = pin_ai_neutral(host, client, tag="w2h28")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": ctx["G"], "stat": "firing",
                        "value": CR.FIRING_PIN}, ("tu",))
    for gc in (host, client):
        assert isinstance(event_state(gc).get("researchMode"), dict), f"{gc.name} event_state lacks researchMode"
    session.wait_host_idle(host, client, timeout=30)
    session.assert_hash_clean(host, client, full=True, what="bring-up")
    ctx["pinned"], ctx["mapFP"], ctx["turn"] = len(pinned), hs.get("mapFingerprint"), hs.get("turn")
    return ctx


def row_hs0(ev, res, host, client, st):
    ev["boot"], logs = st["ctx"], {}
    for n, gc in pairs(host, client):
        lines = log_lines(gc)
        logs[n] = {"active": sum(1 for ln in lines if MOD_ACTIVE_LINE in ln),
                   "errors": [ln for ln in lines if "[ERROR]" in ln][:5]}
    ev["log"] = logs
    res["HS0-mod"] = joined([f"{n} log: {v['active']} line(s) with {MOD_ACTIVE_LINE!r}, [ERROR] lines {v['errors']} "
                             "(want >= 1 and none)" for n, v in logs.items() if v["active"] < 1 or v["errors"]])
    fails, view = [], {}
    for n, gc in pairs(host, client):
        us = battle_state(gc).get("units", [])
        h = sorted(u["id"] for u in us if u.get("isPlayerSoldier") and u.get("coop") == 0
                   and u.get("name") != CR.GUEST_NAME and not u.get("isOut"))
        view[n] = {"G": [(u.get("id"), u.get("coop")) for u in us if u.get("name") == CR.GUEST_NAME],
                   "H": h[0] if h else None}
    ev["units"] = view
    if not (view["host"]["G"] == view["client"]["G"] == [(st["G"], 1)]):
        fails.append(f"G by name host {view['host']['G']} client {view['client']['G']} (want one ({st['G']}, coop 1))")
    if not (view["host"]["H"] == view["client"]["H"] == st["H"]):
        fails.append(f"H host {view['host']['H']} client {view['client']['H']} (want {st['H']} on both)")
    th, tc = all_tags(host), all_tags(client)
    ev["tags"] = {"live": len(th), "values": sorted({json.dumps(v) for v in th.values()}), "equal": th == tc}
    if th != tc:
        diff = [(k, th.get(k), tc.get(k)) for k in sorted(set(th) | set(tc)) if th.get(k) != tc.get(k)]
        fails.append(f"live unit tags differ (id, host, client): {diff}")
    res["HS0-units"] = joined(fails)
    res["HS0-common"] = joined(common(host, client, st["bootSnap"], "HS0", st["crash0"]))


def row_hc(ev, res, host, client, st):
    before, notes = snap(host, client), []
    turn0 = battle_state(host).get("turn")
    t = time.time()
    end_turn_cycle(host, client, notes)
    ev["wall"], ev["notes"], ev["turn0"] = round(time.time() - t, 2), notes, turn0
    ev["after"] = view = {n: {"turn": battle_state(gc).get("turn"), "side": battle_state(gc).get("side"),
                              "top": session.top_state(gc)} for n, gc in pairs(host, client)}
    fails = list(notes)
    for n, v in view.items():
        if v["turn"] != turn0 + 1 or v["side"] != 0 or v["top"] != "BattlescapeState":
            fails.append(f"{n} turn {v['turn']} side {v['side']} top {v['top']} (want turn {turn0 + 1}, side 0, "
                         "BattlescapeState)")
    res["HC-turn"] = joined(fails)
    res["HC-common"] = joined(common(host, client, before, "HC", st["crash0"]))


def row_hg(ev, res, host, client, st):
    G = st["G"]
    seen = max([e.get("iseq", 0) for e in event_state(host).get("intentsReceivedLog") or []] or [0])
    miss = open_skills(client, G, ev)
    if miss:
        capture(host, client, "HG")
        res.update({c: f"construction: {miss}" for c in CELLS["HG"]})
        return
    before, notes = snap(host, client), []
    ev["tu0"] = {n: tu(gc, G) for n, gc in pairs(host, client)}
    press(client, KEY_SKILL)
    ev["out"] = out = await_press(host, client, before, notes)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle: {short(e)}")
    ev["notes"] = notes
    ev["newCtx"] = new = new_contexts(before["host"]["closedContexts"], probes(host)["closedContexts"])
    ev["intentLogNew"] = logn = [e for e in event_state(host).get("intentsReceivedLog") or []
                                 if e.get("iseq", 0) > seen]
    ev["G"] = gt = {n: tags(gc, G) for n, gc in pairs(host, client)}
    ev["tu1"] = {n: tu(gc, G) for n, gc in pairs(host, client)}
    f = [] if ev["rows"] == 1 else [f"menu_rows(client) {ev['rows']} (want 1)"]
    if out.get("state") != "sent":
        f.append(f"await_press {out} (want state sent)")
    res["HG-sent"] = joined(f + notes)
    f = []
    if len(new) != 1 or len(mine(new, "intent", "skill", G)) != 1:
        f.append(f"new host closedContexts {new} (want exactly one {{origin intent, kind skill, actorId {G}}})")
    if [(e.get("kind"), e.get("actorId"), e.get("skill")) for e in logn] != [("skill", G, SKILL)]:
        f.append(f"host intentsReceivedLog new {logn} (want one {{kind skill, actorId {G}, skill {SKILL}}})")
    res["HG-ctx"] = joined(f)
    res["HG-tags"] = (None if gt["host"] == gt["client"] and tag_on(gt["host"]) else
                      f"G tags host {gt['host']} client {gt['client']} (want equal, index {TAG_SKILL} non-zero)")
    res["HG-common"] = joined(common(host, client, before, "HG", st["crash0"]))


def hh_ev_fails(H, seq0, new, hev, cev, eh, ec, clog):
    """HH-ev: one new {host, skill, H} context, its evs exactly [skill, bt_action_end], lastCue on both, clean log."""
    f, ctx = [], mine(new, "host", "skill", H)
    if len(new) != 1 or len(ctx) != 1:
        f.append(f"new host closedContexts {new} (want exactly one {{origin host, kind skill, actorId {H}}})")
    else:
        c, aid = ctx[0], ctx[0].get("actionId")
        if not (c.get("endSeq") or 0) > 0 or c.get("hasFinal") is not True:
            f.append(f"context {c} (want endSeq > 0 and hasFinal true)")
        if [(e["kind"], e["actionId"]) for e in hev] != [("skill", aid), ("bt_action_end", aid)]:
            f.append(f"host evs since seq {seq0}: {hev} (want exactly [skill, bt_action_end] on actionId {aid})")
        lc, want_p = eh.get("lastCue") or {}, {"actor": H, "unit": H, "skill": SKILL}
        if lc.get("kind") != "skill" or lc.get("actionId") != aid or lc.get("payload") != want_p:
            f.append(f"host lastCue {lc} (want kind skill, actionId {aid}, payload {want_p})")
        cmap = {e["seq"]: e["kind"] for e in cev}
        if not hev or any(cmap.get(e["seq"]) != e["kind"] for e in hev):
            f.append(f"client evs since seq {seq0}: {cev} (want the host's seqs applied)")
        cue_seq, clc = next((e["seq"] for e in hev if e["kind"] == "skill"), None), ec.get("lastCue") or {}
        if clc.get("kind") != "skill" or clc.get("seq") != cue_seq:
            f.append(f"client lastCue {clc} (want kind skill at seq {cue_seq})")
    bad = [ln for ln in clog if "RW-UNSUPPORTED" in ln or "has no known actor" in ln]
    if bad:
        f.append(f"client log since the press: {bad[:3]}")
    return f


def row_hh(ev, res, host, client, st):
    H = st["H"]
    miss = open_skills(host, H, ev)
    if not miss and ev.get("rows") != 1:
        miss = f"menu_rows(host) {ev.get('rows')} (want 1)"
    if miss:
        capture(host, client, "HH")
        res.update({c: f"construction: {miss}" for c in CELLS["HH"]})
        return
    before = snap(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    ev["before"] = {"hostLastSeqEmitted": seq0, "clientLastSeqApplied": before["client"]["lastSeqApplied"],
                    "tags": {n: tags(gc, H) for n, gc in pairs(host, client)},
                    "tu": {n: tu(gc, H) for n, gc in pairs(host, client)}, "diff": diff_buckets(host, client)}
    nh, nc = len(log_lines(host)), len(log_lines(client))
    t0 = time.time()
    press(host, KEY_SKILL)
    t_script = None   # HH-script (precondition: the press ran the script on the host)
    while t_script is None and time.time() - t0 < SCRIPT_S:
        if tag_on(tags(host, H)):
            t_script = round(time.time() - t0, 2)
        else:
            time.sleep(POLL_S)
    try:
        host.wait_for("host BattlescapeState after the press",
                      lambda: session.top_state(host) == "BattlescapeState" or None, timeout=MENU_S, interval=POLL_S)
    except Exception as e:
        ev["topWait"] = short(e)
    ev["tScript"], ev["hostTop"] = t_script, session.top_state(host)
    f = [] if t_script is not None else [f"host H tags {tags(host, H)}: index {TAG_SKILL} 0 {SCRIPT_S} s after press"]
    if ev["hostTop"] != "BattlescapeState":
        f.append(f"host top {ev['hostTop']} after the press (want BattlescapeState)")
    res["HH-script"] = joined(f)
    t_follow = None   # HH-follow: the client's H tags equal the host's script value, polled until FOLLOW_S
    while True:
        hv, cv = tags(host, H), tags(client, H)
        if hv == cv and tag_on(hv):
            t_follow = round(time.time() - t0, 2)
        if t_follow is not None or time.time() - t0 >= FOLLOW_S:
            break
        time.sleep(POLL_S)
    ev["follow"] = {"t": t_follow, "host": hv, "client": cv}
    if t_follow is None:
        res["HH-follow"] = f"client H tags {cv}, host {hv} {FOLLOW_S} s after the press (want equal)"
    else:
        res["HH-follow"] = (None if hv == cv == H_TAGS_AFTER else
                            f"H tags host {hv} client {cv} (want H_TAGS_AFTER {H_TAGS_AFTER} on both)")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        ev["idle"] = short(e)
    eh, ec = event_state(host), event_state(client)
    new = new_contexts(before["host"]["closedContexts"], eh.get("closedContexts"))
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    hlog, clog = log_lines(host)[nh:], log_lines(client)[nc:]
    ev.update({"newCtx": new, "hostEvs": hev, "clientEvs": cev, "hostLastCue": eh.get("lastCue"),
               "clientLastCue": ec.get("lastCue")})
    res["HH-ev"] = joined(hh_ev_fails(H, seq0, new, hev, cev, eh, ec, clog))
    fails = common(host, client, before, "HH", st["crash0"])   # the common cell, split
    res["HH-hash"] = joined([x for x in fails if x.startswith(HASH_FAIL)])
    res["HH-common"] = joined([x for x in fails if not x.startswith(HASH_FAIL)])
    ev["after"] = {"hostLastSeqEmitted": eh.get("lastSeqEmitted"), "clientLastSeqApplied": ec.get("lastSeqApplied"),
                   "tu": {n: tu(gc, H) for n, gc in pairs(host, client)},
                   "cueSkill": {n: (e.get("cueCounts") or {}).get("skill") for n, e in (("host", eh), ("client", ec))},
                   "hostContextsOpenedHost": (eh.get("contextsOpened") or {}).get("host"),
                   "diff": diff_buckets(host, client),
                   "hostLog": [ln.split("\t")[-1] for ln in hlog
                               if "[coop-ctx] host skill context" in ln or "[coop-cue] skill" in ln]}


ROWS = (("HS0", row_hs0), ("HC", row_hc), ("HG", row_hg), ("HH", row_hh))


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
                print(f"[w2h28] shutdown {gc.name}: {short(e)}", flush=True)
    n = sum(len(v) for v in CELLS.values())
    print(f"\ntest_w2_host_skill_ev: {n - len(failed)}/{n} cells passed (fail={failed}) in "
          f"{round(time.time() - t_start, 1)} s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
