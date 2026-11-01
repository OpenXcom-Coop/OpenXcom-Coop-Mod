"""Row campaign_rearm: a partner lost between part 1 and part 2 of a SHARED campaign Cydonia. Part 2 WAITS on the host
(battle kept, part 1's results in it); after the rejoin and the host's RESUME part 2 is offered again and both play it.
The custom-battle case is test_stage2_custom_rearm.py.

ONE boot (boot_cydonia, lobby key KEY, dirs campaign_rearm_host / _client / _client2): test_multistage_campaign.py's
boot_campaign steps copied (its Cydonia step is a closure) with WORLD0 read and the real-play stack:
open_select_destination {CRAFT, STR_SKYRANGER} right before open_cydonia, so confirm_cydonia's two pops leave
[GeoscapeState, BriefingState]. Then stage_guards, kill_all(ALIEN_IDS), client hold_battle_ready, close_end_turn, the
hold window (host phase Handshake battleId 2, client battle_ready held), client.kill(), the host observed for W, client2
rejoins (test_failed_battle_start.py's rejoin() copied with the key and tag as parameters, ending at RESUME), then
part 2 (test_multistage.run_spine).

  campaign_rearm_1 GUARD stage-2 offer out (precondition): stage-1 guards empty; host stage emitted 1 / toBattleId 2 /
        nextStage FINAL at the close; host log +1 hand-off, +1 OFFER (battleId=2); host phase Handshake battleId 2;
        client held; host stack at the window [GeoscapeState, BriefingState]; PART2(host) mapFingerprint FP2. A
        failure ends the row.
  campaign_rearm_2 FIX   PARK +1 and UNWIND +0 (without the fix: PARK 0).
  campaign_rearm_3 GUARD the host waits inside part 2: at W the stack ends [GeoscapeState, BriefingState, CoopState],
        dialog 62 backVisible false, world_state.has_battle true, phase Idle, PART2(host) mapFingerprint FP2.
  campaign_rearm_4 GUARD SKY at W equals SKY0.   campaign_rearm_5 GUARD MARKS at W equal MARKS0 (1).
  campaign_rearm_6 GUARD WORLD at W equals WORLD0.
  campaign_rearm_7 FIX   the rejoin reaches RESUME: host resumeAck true within RJ, RESUME pressed, RESUMED_GUARD +0,
        client2 never > 30 s on CoopState 52 (without the fix: resumeAck never true, that line +1).
  campaign_rearm_8 FIX   part 2 starts for both: within 60 s of RESUME REARM +1 and OFFER +1; run_spine(host,
        client2) to turn 1; PART2 on host and client2: phase Active, equal battleId > 2, turn 1, missionType MT2,
        mapFingerprint FP2, xcom XCOM2; UNWIND still 0. With no RESUME it fails at once ("no RESUME").
  campaign_rearm_9 GUARD CRASH 0.
W = 15 s, POLL = 0.2 s, RJ = 60 s. UNWIND / PARK / REARM / OFFER = host log lines with those needles since the kill
(REARM / OFFER: since the RESUME press). PART2(m) = battle_state (phase, battleId, turn, missionType, mapFingerprint,
xcom). SKY = host geo_state entries of CRAFT; MARKS = host save_game, then the "inBattlescape: true" lines; WORLD =
(own-base soldier ids, usedStores rounded to 6 places, totalSoldiers). CRASH = session._crash_log_snapshot() delta.
EVIDENCE before each verdict; a failed row prints ONE CAPTURE line. ONE foreground run, no skip path; exit 0 only when
every cell passes, else 2. Without the fix campaign_rearm_2, campaign_rearm_7 and campaign_rearm_8 fail and every
other cell passes; with it every cell passes.

Run:  python tools/coop_test/test_stage2_failed_start.py
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
from session import pin_ai_neutral, assert_hash_clean  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import test_multistage_campaign as multistage_campaign  # noqa: E402
from test_multistage import run_spine, FACTION_PLAYER  # noqa: E402
from test_multistage_end import stage_guards, kill_all, close_end_turn, bview, MISSION_LANDING  # noqa: E402
from test_cydonia_coop_start import _craft_and_soldiers, _seat, _aboard  # noqa: E402

KEY = "48586"
W, POLL, RJ = 15.0, 0.2, 60.0
UNWIND, PARK = "failed battle start (", "part 2 waits for the partner"
REARM, OFFER = "the waiting part 2 re-armed", "battle_offer sent (battleId="
HANDOFF, OFFER2 = "stage hand-off - battle 1 -> 2 offered (stageOf)", "battle_offer sent (battleId=2,"
RESUMED_GUARD = "offerResumedBattle() called outside a disk resume (phase="
MISSION_FINAL = MT2 = "STR_MARS_THE_FINAL_ASSAULT"
FP2 = 3.1168362819169787e+18          # the host's part 2 at the window (equal on three boots)
XCOM2 = {1: 0, 2: 1}                   # X-COM id -> seat in part 2 (3 of 3 boots)
NAME = "ClientPlayer"                  # host get_coop.clientName at bring-up (3 of 3 boots; read at run time)
GEO, BRF, COOP = "GeoscapeState", "BriefingState", "CoopState"


class Stop(Exception):
    """a WAIT timed out: the row ends here"""


def short(e, n=400):
    return ("%s: %s" % (type(e).__name__, e))[:n]


def q(gc, obj):
    try:
        return gc.cmd(obj)
    except Exception as e:  # a dead or gone machine is a value
        return {"error": short(e, 200)}


def rc(gc):
    return None if gc is None or gc.proc is None else gc.proc.poll()


def stack(gc):
    r = q(gc, {"cmd": "get_state"})
    return [s.replace("class OpenXcom::", "") for s in r.get("states", [])] if "states" in r else r


def ev(gc):
    try:
        e = session.event_state(gc)
    except Exception as ex:
        return {"error": short(ex, 160)}
    return {k: e.get(k) for k in ("phase", "battleId", "desyncSeen", "stage")}


def dlg(gc):
    r = q(gc, {"cmd": "coop_dialog_info"})
    return {k: r.get(k) for k in ("present", "code", "title", "backVisible", "error")}


def coop(gc):
    return {k: v for k, v in q(gc, {"cmd": "get_coop"}).items() if k in ("onConnect", "coopSession", "resumeAck", "coopDialog",
                                                                      "clientName", "error")}


def part2(gc):
    b = q(gc, {"cmd": "battle_state"})
    return {"phase": b.get("phase"), "battleId": (b.get("authority") or {}).get("battleId"), "turn": b.get("turn"),
            "missionType": b.get("missionType"), "mapFingerprint": b.get("mapFingerprint"), "inBattle": b.get("inBattle"),
            "xcom": {u["id"]: u.get("coop") for u in b.get("units") or [] if u.get("faction") == FACTION_PLAYER and not u.get("isOut")},
            "error": b.get("error")}


def sky(host):
    g = q(host, {"cmd": "geo_state"})
    out = [{k: c.get(k) for k in ("status", "destKind", "destId")}
           for b in g.get("bases") or [] for c in b.get("crafts") or [] if c.get("id") == multistage_campaign.CRAFT]
    return out or {"missing craft": multistage_campaign.CRAFT, "error": g.get("error")}


def world(host):
    s, br = q(host, {"cmd": "get_soldiers"}), q(host, {"cmd": "base_report"})
    ids = sorted(x.get("id") for b in s.get("bases") or [] if not b.get("coopBaseFlag") and not b.get("coopIcon")
                 for x in b.get("soldiers") or [])
    used = br.get("usedStores")
    return {"soldierIds": ids, "usedStores": round(used, 6) if isinstance(used, float) else used,
            "totalSoldiers": br.get("totalSoldiers"), "errors": [s.get("error"), br.get("error")]}


def log(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    return open(p, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(p) else []


def since(gc, n0, needle):
    return [ln.split("\t")[-1][:220] for ln in log(gc)[n0:] if needle in ln]


def marks(host, fname):
    """host save_game (a direct SavedGame::save), then every `inBattlescape: true` line with its key path"""
    rep, path, out, keys = q(host, {"cmd": "save_game", "file": fname}), os.path.join(host.user_dir, "xcom1", fname), [], []
    if rep.get("ok") is not True or not os.path.exists(path):
        return {"reply": rep, "file": "missing", "flags": None}
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, s in enumerate((ln.rstrip("\r\n") for ln in f), 1):
            ind, body = len(s) - len(s.lstrip(" ")), s.strip()
            if not body or body.startswith("#"):
                continue
            if body.startswith("- "):
                ind, body = ind + 2, body[2:]
            while keys and keys[-1][0] >= ind:
                keys.pop()
            m = re.match(r"([A-Za-z_][A-Za-z0-9_]*):", body)
            keys += [(ind, m.group(1))] if m else []
            out += ["%d %s" % (n, "/".join(k for _, k in keys))] if "inBattlescape: true" in s else []
    return {"reply": rep.get("ok"), "flags": out}


def wait(desc, pred, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return round(time.time() - t0, 2)
        time.sleep(POLL)
    raise Stop("WAIT %s: timed out after %.0f s" % (desc, timeout))


class Row:
    def __init__(self, rid, cells):
        self.rid, self.cells, self.fails, self.done = rid, cells, [], set()

    def cell(self, cid, kind, label, ok, evid):
        print("EVIDENCE %s: %s" % (cid, json.dumps(evid, sort_keys=True, default=str)), flush=True)
        print("%s %s %s: %s" % ("PASS" if ok else "FAIL", cid, kind, label), flush=True)
        self.done.add(cid)
        self.fails += [] if ok else [cid]

    def stop(self, why):
        print("EVIDENCE %s stop: %s" % (self.rid, why), flush=True)
        for cid in [c for c in self.cells if c not in self.done]:
            print("FAIL %s: not reached (%s)" % (cid, str(why)[:160]), flush=True)
            self.fails.append(cid)


def boot_cydonia(host, client, ctx):
    """test_multistage_campaign.boot_campaign's steps (copied) + WORLD0 + open_select_destination right before
    open_cydonia."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    session.new_campaign(host, client, port=KEY, campaign_mode="shared")
    craft, roster, base = _craft_and_soldiers(host)
    if craft != multistage_campaign.CRAFT or roster[:2] != multistage_campaign.SQUAD:
        raise RuntimeError("craft %s roster %s (want craft %s, roster starting %s)"
                           % (craft, roster, multistage_campaign.CRAFT, multistage_campaign.SQUAD))
    _seat(host, craft, roster, base)
    for gc in (host, client):
        gc.ok({"cmd": "set_soldier_owner", "soldier_id": roster[0], "owner": 0})
        gc.ok({"cmd": "set_soldier_owner", "soldier_id": roster[1], "owner": 1})
    host.wait_for("shared squad seated", lambda: (_aboard(host, craft) == multistage_campaign.SQUAD) or None,
                  timeout=30)
    for gc in (host, client):
        for topic in multistage_campaign.RESEARCH:
            r = gc.cmd({"cmd": "discover_research", "topic": topic})
            if not (r.get("ok") and r.get("researched") is True):
                raise RuntimeError("%s discover_research %s: %s" % (gc.name, topic, r))
    ctx["WORLD0"], ctx["name"] = world(host), coop(host).get("clientName") or NAME
    sds = host.cmd({"cmd": "open_select_destination", "craft_id": multistage_campaign.CRAFT,
                    "craft_type": "STR_SKYRANGER"})
    if sds.get("ok") is not True or sds.get("depth") != 2:
        raise RuntimeError("open_select_destination answered %s (want ok, depth 2)" % sds)
    host.ok({"cmd": "open_cydonia", "craft_id": craft})
    host.wait_for("Cydonia confirmation", lambda: session.has_state(host, "ConfirmCydoniaState") or None)
    host.ok({"cmd": "set_seed", "seed": multistage_campaign.SEED})
    host.ok({"cmd": "confirm_cydonia"})
    ctx["stackAfterConfirm"] = stack(host)
    session.briefings_to_battlescape(host, client)
    hb, cb = bview(host), bview(client)
    bad = []
    if hb.get("mapFingerprint") != multistage_campaign.MAP_FP or cb.get("mapFingerprint") != multistage_campaign.MAP_FP:
        bad.append("mapFingerprint host=%r client=%r (want %r)"
                   % (hb.get("mapFingerprint"), cb.get("mapFingerprint"), multistage_campaign.MAP_FP))
    if (hb.get("side"), hb.get("turn"), hb.get("missionType")) != (FACTION_PLAYER, 1, MISSION_LANDING):
        bad.append("host (side, turn, mission)=%s" % ((hb.get("side"), hb.get("turn"), hb.get("missionType")),))
    if hb.get("xcom") != multistage_campaign.SEATS or cb.get("xcom") != multistage_campaign.SEATS:
        bad.append("X-COM seats host=%s client=%s (want %s)"
                   % (hb.get("xcom"), cb.get("xcom"), multistage_campaign.SEATS))
    if bad:
        raise RuntimeError("bring-up checks: " + "; ".join(bad))
    pinned = pin_ai_neutral(host, client, tag="campaign-rearm")
    if sorted(pinned) != multistage_campaign.ALIEN_IDS:
        raise RuntimeError("pin_ai_neutral pinned %s (want %s)" % (pinned, multistage_campaign.ALIEN_IDS))
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    return {"mapFingerprint": hb.get("mapFingerprint"), "pinned": len(pinned), "stackAfterConfirm": ctx["stackAfterConfirm"],
            "WORLD0": ctx["WORLD0"], "name": ctx["name"]}


def rejoin(host, ctx, key, tag, n_j, evd):
    """client2 rejoins (test_failed_battle_start.py rejoin(), the key and tag as parameters), ending at RESUME -> RESUME pressed"""
    on52 = {"since": None, "max s": 0.0}
    try:
        c2 = ctx["client2"] = GameClient("client2", 3, make_user_dir(tag + "_client2"))
        c2.spawn(); c2.connect()
        evd["join_tcp"] = c2.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": ctx["name"]})
    except Exception as e:
        evd["join"] = short(e)
        return False

    def sample():  # client2's longest unbroken stretch on CoopState 52 ("Loading...")
        on52["since"] = (on52["since"] or time.time()) if dlg(c2).get("code") == 52 else None
        on52["max s"] = max(on52["max s"], round(time.time() - on52["since"], 1) if on52["since"] else 0.0)
    try:
        evd["resumeAck s"] = wait("host resumeAck", lambda: sample() or coop(host).get("resumeAck") is True, RJ)
        if session.has_state(host, "Profile"):
            evd["host profile_ok"] = q(host, {"cmd": "profile_ok"})
            time.sleep(0.5)
        ctx["n_resume"] = len(log(host))
        evd["RESUME"] = session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
        ctx["t_resume"] = time.time()
    except Exception as e:  # a timed-out wait or a machine gone: campaign_rearm_7's own evidence
        evd["wait"] = short(e, 300)
    evd.update({"host coop": coop(host), "host stack": stack(host), "host dialog": dlg(host), "client2 stack": stack(c2),
                "client2 dialog": dlg(c2), "client2 longest on 52 s": on52["max s"], "resumed guard": since(host, n_j, RESUMED_GUARD)})
    return (evd["host coop"].get("resumeAck") is True and (evd.get("RESUME") or {}).get("ok") is True and not evd["resumed guard"]
            and on52["max s"] <= 30.0)


def part2_cells(r, cid, host, c2, ctx, n_k, spine):
    """campaign_rearm_8: REARM +1 and OFFER +1 within 60 s of RESUME, the spine, PART2 on both, UNWIND 0."""
    if "t_resume" not in ctx:
        return r.cell(cid, "FIX", "part 2 starts for both", False, {"no RESUME": True})
    n_r, evd = ctx["n_resume"], {}
    try:
        evd["rearm s"] = wait("REARM and OFFER", lambda: since(host, n_r, REARM) and since(host, n_r, OFFER), 60.0)
        evd["spine"] = spine(host, c2)
    except Exception as e:
        evd["wait"] = short(e, 400)
    hp, cp = part2(host), part2(c2)
    evd.update({"REARM": since(host, n_r, REARM), "OFFER": since(host, n_r, OFFER), "PART2 host": hp, "PART2 client2": cp,
                "UNWIND": since(host, n_k, UNWIND)})
    ok = (len(evd["REARM"]) == 1 and len(evd["OFFER"]) == 1 and "wait" not in evd and not evd["UNWIND"]
          and hp.get("battleId") == cp.get("battleId") and isinstance(hp.get("battleId"), int) and hp["battleId"] > 2
          and all(p.get("phase") == "Active" and p.get("turn") == 1 and p.get("missionType") == MT2 and p.get("mapFingerprint") == ctx["FP2"]
                  and p.get("xcom") == ctx["XCOM2"] for p in (hp, cp)))
    r.cell(cid, "FIX", "part 2 starts for both: within 60 s of RESUME REARM +1 and OFFER +1, the spine to turn 1, PART2 host == client2: "
           "Active, battleId > 2, turn 1, %s, mapFingerprint FP2, xcom XCOM2; UNWIND 0 (without the fix: no RESUME)"
           % MT2, ok, evd)


def row_campaign_rearm(host, client, crash0, ctx):
    r = Row("campaign_rearm", ["campaign_rearm_%d" % i for i in range(1, 9)])
    ctx.update({"FP2": FP2, "XCOM2": XCOM2})
    try:
        g = []
        stage_guards(host, client, ctx, g)
        kill_all(host, client, multistage_campaign.ALIEN_IDS, g, "stage 1")
        hold = q(client, {"cmd": "hold_battle_ready", "on": True})
        n_h = len(log(host))
        close_end_turn(host, client, g)
        hs = ev(host).get("stage")
        hs = hs if isinstance(hs, dict) else {}
        t1, held, he = time.time(), None, {}
        while time.time() - t1 < 30.0:
            he, held = ev(host), q(client, {"cmd": "hold_battle_ready"}).get("held")
            if he.get("phase") == "Handshake" and he.get("battleId") == 2 and held is True:
                break
            time.sleep(POLL)
        win, hp = round(time.time() - t1, 2), part2(host)
        handoff, offer2, st = since(host, n_h, HANDOFF), since(host, n_h, OFFER2), stack(host)
        ok1 = (not g and hold.get("armed") is True and hs.get("emitted") == 1 and hs.get("toBattleId") == 2
               and hs.get("nextStage") == MISSION_FINAL and len(handoff) == 1 and len(offer2) == 1 and he.get("phase") == "Handshake"
               and he.get("battleId") == 2 and held is True and st == [GEO, BRF] and hp.get("mapFingerprint") == FP2)
        r.cell("campaign_rearm_1", "GUARD", "stage-2 offer out: guards empty, host stage emitted 1 / toBattleId 2 / "
               "nextStage %s, +1 hand-off, +1 battle_offer (battleId=2), host Handshake battleId 2, client held, host "
               "stack [GeoscapeState, BriefingState], PART2(host) "
               "mapFingerprint FP2 %r" % (MISSION_FINAL, FP2), ok1,
               {"guards": g, "hold": hold, "hostStageAtClose": hs, "handoff": handoff, "offer2": offer2, "host": he, "held": held,
                "s to the window": win, "hostStack": st, "PART2 host": hp, "stackAfterConfirm": ctx.get("stackAfterConfirm")})
        if not ok1:
            raise Stop("campaign_rearm_1 (precondition) failed")
        sky0, marks0, n_k = sky(host), marks(host, "campaign_rearm_prekill.sav"), len(log(host))
        client.kill()
        tk, polls = time.time(), []
        first = dict(ev(host), t=round(time.time() - tk, 2))
        while time.time() - tk < W:
            polls.append([round(time.time() - tk, 2), stack(host), ev(host).get("phase"), dlg(host).get("code")])
            time.sleep(POLL)
        park, unw, hs1, d, hp1 = since(host, n_k, PARK), since(host, n_k, UNWIND), stack(host), dlg(host), part2(host)
        path = {"first poll after the kill": {k: v for k, v in first.items() if k != "stage"},
                "loss path": {"Idle": "-2 receive", "Handshake": "-3 send"}.get(first.get("phase"), "?"),
                "host after": [p for i, p in enumerate(polls) if i == 0 or p[1:] != polls[i - 1][1:]]}
        r.cell("campaign_rearm_2", "FIX", "PARK +1 and UNWIND +0 (without the fix: PARK 0)", len(park) == 1 and not unw,
               {"PARK": park, "UNWIND": unw, "path": path})
        hasb = q(host, {"cmd": "world_state"}).get("has_battle")
        r.cell("campaign_rearm_3", "GUARD", "the host waits inside part 2: stack ends [GeoscapeState, BriefingState, "
               "CoopState], dialog 62 backVisible false, has_battle true, phase Idle, mapFingerprint FP2",
               hs1[-3:] == [GEO, BRF, COOP] and d.get("code") == 62
               and d.get("backVisible") is False and hasb is True and hp1.get("phase") == "Idle" and hp1.get("mapFingerprint") == FP2,
               {"stack": hs1, "dialog": d, "has_battle": hasb, "PART2 host": hp1, "coop": coop(host)})
        s1, m1, w1 = sky(host), marks(host, "campaign_rearm_after.sav"), world(host)
        r.cell("campaign_rearm_4", "GUARD", "SKY at W equals SKY0", isinstance(sky0, list) and s1 == sky0,
               {"SKY0": sky0, "SKY": s1})
        paths = [[f.split(" ", 1)[-1] for f in m.get("flags") or []] for m in (marks0, m1)]
        r.cell("campaign_rearm_5", "GUARD", "MARKS at W equal MARKS0 (1: the mission is not undone)",
               marks0.get("flags") is not None and m1.get("flags") is not None and len(paths[0]) == 1
               and paths[1] == paths[0], {"MARKS0": marks0, "MARKS": m1})
        r.cell("campaign_rearm_6", "GUARD", "WORLD at W equals WORLD0 (part 1 not yet debriefed)",
               w1 == ctx["WORLD0"] and not any(w1["errors"]),
               {"WORLD0": ctx["WORLD0"], "WORLD": w1})
        evd, n_j = {}, len(log(host))
        r.cell("campaign_rearm_7", "FIX", "the rejoin reaches RESUME: resumeAck true within %.0f s, RESUME pressed, "
               "offerResumedBattle guard +0, client2 never > 30 s on 52 (without the fix: resumeAck never true, that "
               "line +1)" % RJ, rejoin(host, ctx, KEY, "campaign_rearm", n_j, evd), evd)
        part2_cells(r, "campaign_rearm_8", host, ctx["client2"], ctx, n_k, lambda h, c: run_spine(h, c))
    except Exception as e:  # the precondition, a timed-out wait, or a raising test command / kill(): the row ends here
        r.stop(short(e))
    new = sorted(session._crash_log_snapshot() - crash0)
    r.cell("campaign_rearm_9", "GUARD", "CRASH 0 (no new crash_*.log in this lane's crash folder since the row's "
           "baseline)", not new, new)
    if r.fails:
        capture("campaign_rearm", host, ctx)
    print(("PASS campaign_rearm" if not r.fails else "FAIL campaign_rearm: %s" % " ".join(r.fails)), flush=True)
    return not r.fails


def capture(rid, host, ctx):
    live = [(gc.name, gc) for gc in (host, ctx.get("client2")) if gc is not None and rc(gc) is None and gc.proc is not None]
    cap = {n: {"stack": stack(gc), "event": ev(gc), "battle": part2(gc), "coop": coop(gc), "dialog": dlg(gc)} for n, gc in live}
    cap["host rc"] = rc(host)
    cap["HL"] = [ln.split("\t")[-1][:200] for ln in log(host) if "[coop" in ln][-15:]
    print("CAPTURE %s: %s" % (rid, json.dumps(cap, sort_keys=True, default=str)), flush=True)


def run_boot(rid, tag, boot, row, failed):
    """One boot, its row, then every machine shut down (kill() already reaped a killed client) -> the row passed."""
    t0, ok, ctx = time.time(), False, {}
    host = GameClient("host", 1, make_user_dir(tag + "_host"))
    client = GameClient("client", 2, make_user_dir(tag + "_client"))
    crash0 = session._crash_log_snapshot()
    try:
        try:
            info = boot(host, client, ctx)
            print("[stage2_failed_start] %s boot ok: %s (%.1f s)"
                  % (rid, json.dumps(info, default=str), time.time() - t0), flush=True)
        except Exception as e:
            print("EVIDENCE %s boot: %s\nFAIL %s: boot (setup failure)" % (rid, short(e, 600), rid), flush=True)
            capture(rid, host, {"client2": client})
            info = None
        if info is not None:
            ok = row(host, client, crash0, ctx)
    finally:
        for gc in (ctx.get("client2"), client, host):
            try:
                if gc is not None and gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown()
            except Exception as e:
                print("FAIL %s shutdown (%s): %s" % (rid, gc.name, short(e, 300)), flush=True)
                failed.append("%s shutdown %s" % (rid, gc.name))
    return ok


def main():
    t0, failed = time.time(), []
    results = {"campaign_rearm": run_boot("campaign_rearm", "campaign_rearm", boot_cydonia, row_campaign_rearm, failed)}
    bad = [rid for rid, ok in results.items() if not ok] + failed
    print("\ntest_stage2_failed_start: %d/1 rows passed (fail=%s) in %.1fs" % (sum(results.values()), bad, time.time() - t0),
          flush=True)
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
