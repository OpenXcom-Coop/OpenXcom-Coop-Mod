"""W2-P7 S-C-A - test_w2_battle_end_campaign.py: a SHARED campaign's second player ends on its own display-only
debriefing, takes the host's post-battle world in place under it (MR1), and each player leaves its own debriefing
with its own OK (docs rewrite/prompts/w2p7_sc_design.md section 3.1, AMENDMENT P7-6 section 4.1 rows C28S / C28S-b,
PR-1..PR-11, the P7-6 TASK 0 RULINGS; owner D156 (a), D175, D176; mechanism rulings MR1-MR3; P7-5 Q4 (a)).

Before S-C-A (F2491, F2492): the client's battle-end latch arms only in a skirmish, so a SHARED campaign client stays
on the battle map until the host has closed every after-battle screen; the host's post-follow-up restream
(GeoscapeState :1029 -> MAP_RESULT_LOAD_PROGRESS -> CoopState(555) -> LoadGameState) then replaces its whole stack.

Fixture (one boot per row; TASK 0 ledger `## W2-P7 S-C TASK 0 (part 1) DONE`, docs rewrite/w2p7sc-task0/t0/
CONSTANTS.md): shared_fixture.bring_up(tag, (0, 0, PORT)); session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1},
pre_landing = host set_seed SEED_S) - T0-6 (i): SEED 1 pins the terror map (MAP_FP_S on both machines); host set_option
battleAutoEnd true; host battle_action kill_unit_real {faction: 1} kills the 15 hostiles (T0-6 (ii)); the host's
autoEnd NextTurnState is closed with dismiss_popup -> the host's DebriefingState, pinned (HOST_DEBRIEF). C28S-b first
wounds the host-owned soldier aboard (T0-6 (v): battle_set_unit_state {unit, health: start - WOUND_HP} on both
machines, client first; F4541). No END TURN is pressed (the autoEnd ends the battle), so F4665's wait never applies.

Rows (AMENDMENT P7-6 section 4.1). The GREEN cells are numbered and checked in order; a failed cell ends its row (every
later cell depends on it) and the rest are reported "not reached":
  C28S   (1) both debrief_state equal on the seven content fields with page-2 names prefix-stripped (PR-10); the
             client's shown, on top and display-only within CLIENT_DEBRIEF_S of the host's DebriefingState.
         (2) the client's battleEnd.worldAdopted 1 within ADOPT_S (T0-S2: 15 s); shared_checksum chk* equal.
         (3) the client's OK first: its top GeoscapeState with no CoopState / LoadGameState on its stack within OK_S
             (and no LoadGameState pushed over the whole row, P6-4); the host's top still DebriefingState.
         (4) the host's OK + drain: both tops GeoscapeState; event_state phase Idle and researchMode.coopBattle false on
             both; chk* equal; host battleEnd.worldPushed 1; debriefOkBranch "campaign-host" (host) and
             "campaign-client-shared" (client); the client zero-disk.
  C28S-b (1) as C28S (1).
         (2) the client's worldAdopted 1 within ADOPT_S (before the host's OK).
         (3) the host's OK first + drain to its GeoscapeState; then the client's top stays DebriefingState for
             HOST_HOLD_S (top_hold == []), worldAdopted still 1 and worldHeld 1 (no MAP_RESULT replacement, MR2).
         (4) the wounded soldier's get_soldiers craftId -1 and soldier_record recovery > 0 on BOTH machines
             (unassign_wounded, MR2).
         (5) the client's OK: its top GeoscapeState with no CoopState / LoadGameState within OK_S (none pushed over the
             row); chk* equal; debriefOkBranch "campaign-host" / "campaign-client-shared"; the client zero-disk.
Pre-cell guard (a failure is a FIXTURE-STOP: one CAPTURE line, then the row FAILs "pre-cell"): bring-up, the map pin,
the wound (C28S-b), autoEnd on, the kill, the host's DebriefingState within DEBRIEF_S, the host's debrief_state ==
HOST_DEBRIEF, host event_state.fatalVote.armed 0 (S-V's vote did not arm, F4544). Over the whole row: no new crash log.

RED (commit S-C-A.1: probes, holds and rows, product untouched): each row fails on exactly cell 1 - the client never
shows a DebriefingState (it stays on the battle map, F2491). GREEN (commit S-C-A.2): both rows pass.
Each row prints ONE "EVIDENCE <id>:" line (both machines' battleEnd records, tops, debriefs, cells), then "PASS <id>"
or "FAIL <id>: <message>"; both rows run. WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when both
rows pass, 2 otherwise.

Run:  python tools/coop_test/test_w2_battle_end_campaign.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
import shared_fixture

# ----- TASK 0 pins (docs rewrite/w2p7sc-task0/t0/CONSTANTS.md; logs sh1..sh3 = T0's three SHARED boots) -----
SEED_S = 1                          # CONSTANTS T0-6 (i): "SEED_S = SEED_P = 1"
MAP_FP_S = 5.690100025079999e+18    # CONSTANTS T0-6 (i): "Host mapFingerprint 5.690100025079999e+18 on every boot (client equal)"
HOSTILES = list(range(1000000, 1000015))   # CONSTANTS T0-6 (i): "15 hostiles 1000000-1000014"
WOUND_HP = 5                        # CONSTANTS T0-6 (v): "battle_set_unit_state {unit:1, health:start-5} both machines"
ADOPT_S = 15                        # CONSTANTS T0-S2: "C28S adoption timeout = 15 s"
# CONSTANTS T0-6 (ii) "Host debrief pin" = logs sh1/sh2/sh3 `M hostDebrief` (identical on 3/3 boots); `soldiers` as
# each row's deltas (names change per boot and are compared host-to-client only, test_w2_battle_end G10).
HOST_DEBRIEF = {
    "title": "Aliens defeated", "recoveryHeader": "",
    "rows": [{"item": "ALIEN CORPSES RECOVERED", "qty": 10, "recovery": False, "score": 50},
             {"item": "ALIEN ARTIFACTS RECOVERED", "qty": 22, "recovery": False, "score": 44},
             {"item": "CIVILIANS KILLED BY ALIENS", "qty": 1, "recovery": False, "score": -30},
             {"item": "CIVILIANS SAVED", "qty": 13, "recovery": False, "score": 390}],
    "total": 454, "rating": "RATING> GOOD!",
    "soldiers": [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    "recovered": [{"item": "Plasma Rifle", "qty": 1}, {"item": "  Plasma Rifle Clip", "qty": 2},
                  {"item": "Plasma Pistol", "qty": 8}, {"item": "  Plasma Pistol Clip", "qty": 16},
                  {"item": "Small Launcher", "qty": 1}, {"item": "  Stun Bomb", "qty": 3},
                  {"item": "Alien Grenade", "qty": 1}, {"item": "Sectoid Corpse", "qty": 10}],
}

# ----- this file's constants -----
ROW_PORT = {"C28S": "47200", "C28S-b": "47201"}   # AMENDMENT P7-6 section 4 (F4545): A = 47200-47202
ROSTER_NAMES = ("HostPlayer", "ClientPlayer")     # session.new_campaign's defaults (PR-10's `[<roster name>] `)
DEBRIEF_FIELDS = ("title", "recoveryHeader", "rows", "total", "rating", "soldiers", "recovered")
DEBRIEF_S = 60          # the host's DebriefingState after the kill (T0-6 (ii): 9.3-10.6 s)
CLIENT_DEBRIEF_S = 20   # cell 1: the client's display-only DebriefingState after the host's
OK_S = 10               # a machine's GeoscapeState after its own OK
DRAIN_S = 60            # the host's OK + follow-ups down to its GeoscapeState
EQUAL_S = 10            # chk* / a shared_apply's effect may lag one round trip (J10 debounce reasoning)
HOST_HOLD_S = 3         # C28S-b cell 3: the client's top sampled every 0.25 s (test_w2_battle_end HOST_HOLD_S)
WAIT_TOPS = ("VoteMenu", "BattlescapeState", "SaveGameState")   # never dismissed by a drain (not ours to pop)
LOADGAME_PUSH = "push class OpenXcom::LoadGameState"           # the [coop-ui] state-push log line (P6-4)


class FixtureMiss(Exception):
    pass


# ===================== small probes =====================


def short(e, n=400):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def stack(gc):
    return session.states_stripped(gc)


def top(gc):
    st = stack(gc)
    return st[-1] if st else None


def wait_until(pred, timeout, interval=0.25):
    """Poll `pred` until truthy or `timeout` s pass. Returns (ok, seconds)."""
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 >= timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def record(gc):
    """This machine's event_state.battleEnd ({} when absent)."""
    r = event_state(gc).get("battleEnd")
    return r if isinstance(r, dict) else {}


def chk(gc):
    """shared_checksum's chk* fields (the J10 world aggregates)."""
    r = gc.cmd({"cmd": "shared_checksum"})
    return {k: v for k, v in r.items() if k.startswith("chk")}


def chk_equal(host, client):
    """Poll up to EQUAL_S for equal chk* (non-empty). Returns (ok, secs, host chk, client chk)."""
    last = {}

    def same():
        last["h"], last["c"] = chk(host), chk(client)
        return bool(last["h"]) and last["h"] == last["c"]
    ok, secs = wait_until(same, EQUAL_S)
    return ok, secs, last.get("h"), last.get("c")


def strip_prefix(name):
    """PR-10: a leading `[<roster name>] ` is stripped so these rows stay exact after S-C-C's prefixes land."""
    for n in ROSTER_NAMES:
        p = f"[{n}] "
        if isinstance(name, str) and name.startswith(p):
            return name[len(p):]
    return name


def debrief_view(deb):
    """The seven content fields of a debrief_state with page-2 names prefix-stripped (PR-10)."""
    deb = deb if isinstance(deb, dict) else {}
    out = {k: deb.get(k) for k in DEBRIEF_FIELDS}
    out["soldiers"] = [{"name": strip_prefix(s.get("name")), "deltas": s.get("deltas")}
                       for s in (deb.get("soldiers") or []) if isinstance(s, dict)]
    return out


def pin_view(deb):
    """The pinned form (HOST_DEBRIEF): the seven fields, `soldiers` reduced to each row's deltas."""
    deb = deb if isinstance(deb, dict) else {}
    out = {k: deb.get(k) for k in DEBRIEF_FIELDS}
    out["soldiers"] = [s.get("deltas") for s in (deb.get("soldiers") or []) if isinstance(s, dict)]
    return out


def log_count(gc, literal):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if literal in ln)
    except OSError:
        return 0


def view(gc):
    """One machine's state for the EVIDENCE line (every field from an existing probe)."""
    es = event_state(gc)
    return {"stack": stack(gc), "phase": es.get("phase"),
            "coopBattle": (es.get("researchMode") or {}).get("coopBattle"),
            "fatalVoteArmed": (es.get("fatalVote") or {}).get("armed"),
            "battleEnd": es.get("battleEnd")}


def soldier_craft(gc, sid):
    for b in gc.cmd({"cmd": "get_soldiers"}).get("bases", []) or []:
        for s in b.get("soldiers", []) or []:
            if s.get("id") == sid:
                return s.get("craftId")
    return None


def soldier_recovery(gc, sid):
    r = gc.cmd({"cmd": "soldier_record", "id": sid})
    recs = r.get("records") or []
    return recs[0].get("recovery") if recs else None, {k: r.get(k) for k in ("ok", "count", "error")}


def press_ok(gc):
    """Press this machine's debriefing OK (dismiss_popup -> DebriefingState::btnOkClick) only when its top is
    DebriefingState; never dismisses anything else."""
    t = top(gc)
    if t != "DebriefingState":
        return {"pressed": False, "note": f"{gc.name} OK not pressed: {gc.name} top {t}"}
    r = gc.cmd({"cmd": "dismiss_popup"})
    return {"pressed": True, "resp": {k: r.get(k) for k in ("ok", "handled", "error")}}


def drain(gc, timeout=DRAIN_S, interval=0.4):
    """After the OK: dismiss this machine's follow-up screens down to its GeoscapeState (CoopState -> coop_dialog_back,
    WAIT_TOPS left alone). Returns (reached, screens)."""
    screens, t0 = [], time.time()
    while time.time() - t0 < timeout:
        t = top(gc) or ""
        if t == "GeoscapeState":
            return True, screens
        if any(n in t for n in WAIT_TOPS):
            time.sleep(interval)
            continue
        r = gc.cmd({"cmd": "coop_dialog_back"}) if "CoopState" in t else gc.cmd({"cmd": "dismiss_popup"})
        screens.append({"t": round(time.time() - t0, 2), "top": t,
                        "resp": r.get("handled") or r.get("error") or r.get("ok")})
        time.sleep(interval)
    return False, screens


def geo_clean(gc):
    """Top GeoscapeState and no CoopState / LoadGameState anywhere on the stack."""
    st = stack(gc)
    return bool(st) and st[-1] == "GeoscapeState" and not any(("CoopState" in s or "LoadGameState" in s) for s in st)


def top_hold(gc, secs=HOST_HOLD_S):
    """The distinct non-DebriefingState tops seen sampling this machine's top every 0.25 s ([] = held)."""
    seen, t0 = [], time.time()
    while True:
        t = top(gc)
        if t != "DebriefingState" and t not in seen:
            seen.append(t)
        if time.time() - t0 >= secs:
            return seen
        time.sleep(0.25)


def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def capture(name, err, machines):
    """FIXTURE-STOP: CAPTURE every machine's event_state, battle_state flags and stack (whole), then raise."""
    cap = {}
    for gc in machines:
        try:
            bs = battle_state(gc)
            cap[gc.name] = {"stack": stack(gc), "event_state": event_state(gc),
                            "battle": {k: bs.get(k) for k in ("inBattle", "isBusy", "pendingStates", "turn", "phase",
                                                              "mapFingerprint")},
                            "debrief": gc.cmd({"cmd": "debrief_state"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


# ===================== bring-up, staging, ending (pre-cell) =====================


def seed_pin(host, client):
    host.ok({"cmd": "set_seed", "seed": SEED_S})


def stage(rid, js, ctx, wound=False, holds=False):
    """The pre-cell part of every row: the SHARED battle on SEED_S, the optional wound and holds, autoEnd, the kill
    and the host's debriefing against HOST_DEBRIEF. Fills ctx; raises FixtureMiss (after a CAPTURE line)."""
    host, client = js.host, js.client
    m = (host, client)
    try:
        _h, _c, squad = session.bring_up_shared_mixed_battle(js, {0: 0, 1: 1}, pre_landing=seed_pin)
    except Exception as e:
        capture("bring_up_shared_mixed_battle", short(e, 800), m)
    ctx["squad"] = squad
    fp = (battle_state(host).get("mapFingerprint"), battle_state(client).get("mapFingerprint"))
    ctx["mapFingerprint"] = fp
    if fp != (MAP_FP_S, MAP_FP_S):
        capture("map pin", f"mapFingerprint (host, client) {fp} (want both {MAP_FP_S!r}, SEED_S {SEED_S})", m)
    if wound:
        units = {u.get("soldierId"): u for u in battle_state(host).get("units", []) if u.get("faction") == 0}
        u = units.get(squad[0]) or {}
        hp0 = u.get("health")
        if not isinstance(hp0, int) or u.get("id") is None:
            capture("wound", f"no live player unit for soldier {squad[0]}: {u}", m)
        want = hp0 - WOUND_HP
        rc = client.cmd({"cmd": "battle_set_unit_state", "unit": u["id"], "health": want})   # client first (F607)
        rh = host.cmd({"cmd": "battle_set_unit_state", "unit": u["id"], "health": want})
        ctx["wound"] = {"unit": u["id"], "soldier": squad[0], "health0": hp0, "want": want,
                        "host": {k: rh.get(k) for k in ("ok", "health", "error")},
                        "client": {k: rc.get(k) for k in ("ok", "health", "error")}}
        if not (rh.get("ok") and rc.get("ok") and rh.get("health") == want and rc.get("health") == want):
            capture("wound", f"battle_set_unit_state answered {ctx['wound']}", m)
    ae = host.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    ctx["autoEnd"] = ae.get("value")
    if ae.get("value") is not True:
        capture("battleAutoEnd", f"host set_option battleAutoEnd answered {ae}", m)
    if holds:
        hh = host.cmd({"cmd": "hold_world_stream", "on": True})
        ch = client.cmd({"cmd": "hold_world_adopt", "on": True})
        ctx["holds"] = {"host": hh, "client": ch}
        if not (hh.get("ok") and hh.get("armed") is True and ch.get("ok") and ch.get("armed") is True):
            capture("holds", f"hold levers answered {ctx['holds']}", m)
    ctx["loadGamePushes0"] = log_count(client, LOADGAME_PUSH)
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    ctx["kill"] = {k2: k.get(k2) for k2 in ("ok", "killed", "error")}
    if not k.get("ok") or sorted(k.get("killed") or []) != HOSTILES:
        capture("kill", f"kill_unit_real faction 1 answered {ctx['kill']} (want the 15 hostiles)", m)
    t0, closes, samples, last = time.time(), [], [], None
    while time.time() - t0 < DEBRIEF_S:
        hst = stack(host)
        if "DebriefingState" in hst:
            break
        s = (hst[-1] if hst else None, top(client))
        if s != last:
            samples.append((round(time.time() - t0, 2),) + s)
            last = s
        if hst and hst[-1] == "NextTurnState":
            closes.append(host.cmd({"cmd": "dismiss_popup"}).get("handled"))
        time.sleep(0.1)
    ctx["ending"] = {"secs": round(time.time() - t0, 2), "closes": closes, "samples": samples}
    if "DebriefingState" not in stack(host):
        capture("host debriefing", f"no host DebriefingState within {DEBRIEF_S}s of the kill ({ctx['ending']})", m)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ctx["hostDebrief"] = hdeb
    bad = [f"host debrief_state.{k}={hdeb.get(k)!r} (want {w!r})"
           for k, w in (("shown", True), ("onTop", True), ("displayOnly", False)) if hdeb.get(k) is not w]
    pv = pin_view(hdeb)
    bad += [f"host debrief_state.{k}={pv.get(k)!r} (want the T0 pin {HOST_DEBRIEF[k]!r})"
            for k in DEBRIEF_FIELDS if pv.get(k) != HOST_DEBRIEF[k]]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        bad.append(f"host fatalVote.armed={armed!r} (want 0: no S-V vote, F4544)")
    if bad:
        capture("host debriefing pin", "; ".join(bad), m)


# ===================== cells =====================


def cell_debriefs(host, client, ctx):
    """Cell 1 (every row): the client's display-only debriefing, equal to the host's (PR-10 stripped)."""
    ok, secs = wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                   and d.get("displayOnly") is True)(client.cmd({"cmd": "debrief_state"})),
                          CLIENT_DEBRIEF_S)
    hdeb, cdeb = host.cmd({"cmd": "debrief_state"}), client.cmd({"cmd": "debrief_state"})
    ctx["cell1"] = {"waited": secs, "clientStack": stack(client), "clientDebrief": cdeb}
    f = []
    if not ok:
        f.append(f"the client never showed a display-only DebriefingState within {CLIENT_DEBRIEF_S}s of the host's "
                 f"(client stack {stack(client)}, debrief_state shown={cdeb.get('shown')!r} onTop="
                 f"{cdeb.get('onTop')!r} displayOnly={cdeb.get('displayOnly')!r})")
        return f
    hv, cv = debrief_view(hdeb), debrief_view(cdeb)
    f += [f"client debrief_state.{k}={cv.get(k)!r} != the host's {hv.get(k)!r}" for k in DEBRIEF_FIELDS
          if cv.get(k) != hv.get(k)]
    if hdeb.get("displayOnly") is not False:
        f.append(f"host debrief_state.displayOnly={hdeb.get('displayOnly')!r} (want False)")
    return f


def cell_adopted(host, client, ctx, with_chk):
    """The client adopted the host's post-battle world in place (worldAdopted 1 within ADOPT_S) [+ chk* equal]."""
    ok, secs = wait_until(lambda: record(client).get("worldAdopted") == 1, ADOPT_S)
    crec = record(client)
    ctx["adopt"] = {"waited": secs, "client": {k: crec.get(k) for k in ("returnPending", "worldHeld", "worldAdopted",
                                                                       "heldAppliesAtAdopt", "okDeferred")}}
    if not ok:
        return [f"client battleEnd.worldAdopted={crec.get('worldAdopted')!r} after {ADOPT_S}s (want 1)"]
    if not with_chk:
        return []
    eq, esecs, hc, cc = chk_equal(host, client)
    ctx["adopt"]["chk"] = {"equal": eq, "secs": esecs, "host": hc, "client": cc}
    return [] if eq else [f"shared_checksum chk* host {hc} != client {cc} after {EQUAL_S}s"]


def client_ok_clean(client, ctx, key):
    """The client's OK -> its top GeoscapeState, no CoopState / LoadGameState on its stack (and none pushed)."""
    ok1 = press_ok(client)
    ok, secs = wait_until(lambda: geo_clean(client), OK_S) if ok1["pressed"] else (False, 0)
    pushes = log_count(client, LOADGAME_PUSH) - ctx["loadGamePushes0"]
    ctx[key] = {"ok": ok1, "reached": ok, "secs": secs, "clientStack": stack(client), "loadGamePushes": pushes}
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"client OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not ok:
        f.append(f"client not on a clean GeoscapeState within {OK_S}s of its OK (stack {stack(client)})")
    if pushes != 0:
        f.append(f"client pushed {pushes} LoadGameState(s) since the ending (want 0: in-place adoption, P6-4)")
    return f


def host_ok_drain(host, ctx, key):
    ok1 = press_ok(host)
    reached, screens = drain(host) if ok1["pressed"] else (False, [])
    ctx[key] = {"ok": ok1, "reached": reached, "screens": screens, "hostStack": stack(host)}
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"host OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not reached:
        f.append(f"host not on GeoscapeState within {DRAIN_S}s of its OK (stack {stack(host)}, screens {screens})")
    return f


def end_checks(host, client, ctx):
    """The rows' common tail: phase Idle / coopBattle false on both, chk* equal, the OK branches, worldPushed, zero-disk."""
    f = []
    for gc in (host, client):
        v = view(gc)
        if v["phase"] != "Idle":
            f.append(f"{gc.name} event_state.phase={v['phase']!r} (want 'Idle')")
        if v["coopBattle"] is not False:
            f.append(f"{gc.name} researchMode.coopBattle={v['coopBattle']!r} (want False)")
    eq, esecs, hc, cc = chk_equal(host, client)
    ctx["endChk"] = {"equal": eq, "secs": esecs, "host": hc, "client": cc}
    if not eq:
        f.append(f"shared_checksum chk* host {hc} != client {cc} after {EQUAL_S}s")
    hrec, crec = record(host), record(client)
    if hrec.get("worldPushed") != 1:
        f.append(f"host battleEnd.worldPushed={hrec.get('worldPushed')!r} (want 1)")
    if hrec.get("debriefOkBranch") != "campaign-host":
        f.append(f"host battleEnd.debriefOkBranch={hrec.get('debriefOkBranch')!r} (want 'campaign-host')")
    if crec.get("debriefOkBranch") != "campaign-client-shared":
        f.append(f"client battleEnd.debriefOkBranch={crec.get('debriefOkBranch')!r} (want 'campaign-client-shared')")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        f.append(str(e))
    return f


# ----- C28S -----


def c28s_cells(host, client, ctx):
    return [
        ("1 both debriefings, the client's display-only", lambda: cell_debriefs(host, client, ctx)),
        ("2 the client adopted in place, chk* equal", lambda: cell_adopted(host, client, ctx, True)),
        ("3 the client's OK first", lambda: client_ok_clean(client, ctx, "clientOk") + (
            [] if top(host) == "DebriefingState" else [f"host top={top(host)} after the client's OK (want "
                                                       f"DebriefingState)"])),
        ("4 the host's OK + drain, both on the geoscape", lambda: host_ok_drain(host, ctx, "hostOk") + (
            [] if top(client) == "GeoscapeState" else [f"client top={top(client)} after the host's OK (want "
                                                       f"GeoscapeState)"]) + end_checks(host, client, ctx)),
    ]


# ----- C28S-b -----


def c28sb_hold(host, client, ctx):
    f = host_ok_drain(host, ctx, "hostOk")
    if f:
        return f
    hold = top_hold(client)
    crec = record(client)
    ctx["clientHold"] = {"seen": hold, "worldAdopted": crec.get("worldAdopted"), "worldHeld": crec.get("worldHeld")}
    if hold != []:
        f.append(f"client hold saw {hold} within {HOST_HOLD_S}s after the host's OK (want [] - its debriefing on top)")
    if crec.get("worldAdopted") != 1:
        f.append(f"client battleEnd.worldAdopted={crec.get('worldAdopted')!r} after the host's OK (want still 1)")
    if crec.get("worldHeld") != 1:
        f.append(f"client battleEnd.worldHeld={crec.get('worldHeld')!r} after the host's OK (want 1: no MAP_RESULT "
                 f"replacement)")
    return f


def c28sb_wounded(host, client, ctx):
    sid = ctx["squad"][0]
    ok, secs = wait_until(lambda: soldier_craft(host, sid) == -1 and soldier_craft(client, sid) == -1, EQUAL_S)
    hr, hresp = soldier_recovery(host, sid)
    cr, cresp = soldier_recovery(client, sid)
    ctx["wounded"] = {"soldier": sid, "waited": secs, "craftId": {"host": soldier_craft(host, sid),
                                                                  "client": soldier_craft(client, sid)},
                      "recovery": {"host": hr, "client": cr}, "soldierRecord": {"host": hresp, "client": cresp}}
    f = []
    if not ok:
        f.append(f"wounded soldier {sid} craftId {ctx['wounded']['craftId']} after {EQUAL_S}s (want -1 on both)")
    for name, r in (("host", hr), ("client", cr)):
        if not isinstance(r, int) or r <= 0:
            f.append(f"{name} soldier_record {sid}.recovery={r!r} (want > 0)")
    return f


def c28sb_cells(host, client, ctx):
    return [
        ("1 both debriefings, the client's display-only", lambda: cell_debriefs(host, client, ctx)),
        ("2 the client adopted in place before the host's OK", lambda: cell_adopted(host, client, ctx, False)),
        ("3 the host's OK first; the client's debriefing holds", lambda: c28sb_hold(host, client, ctx)),
        ("4 the wounded soldier is off the craft on both (unassign_wounded)", lambda: c28sb_wounded(host, client, ctx)),
        ("5 the client's OK", lambda: client_ok_clean(client, ctx, "clientOk") + end_checks(host, client, ctx)),
    ]


# ===================== one row =====================


def run_row(rid, tag, port, stage_fn, cells_fn, results, walls, holds=False):
    """One boot: stage_fn(rid, js, ctx) (pre-cell), then the cells in order; ONE EVIDENCE line, then PASS / FAIL.
    `holds`: release both TEST-ONLY holds before the shutdown."""
    t0, ctx, js = time.time(), {"row": rid}, None
    crash0 = session._crash_log_snapshot()
    verdict = None
    try:
        try:
            js = shared_fixture.bring_up(tag, (0, 0, port))
            stage_fn(rid, js, ctx)
        except Exception as e:
            verdict = (f"pre-cell (FIXTURE-STOP) {e if isinstance(e, FixtureMiss) else short(e, 800)}", None)
        if verdict is None:
            host, client = js.host, js.client
            cells = cells_fn(host, client, ctx)
            ctx["cells"] = []
            for i, (name, fn) in enumerate(cells):
                try:
                    f = fn()
                except Exception as e:
                    f = [f"{type(e).__name__}: {short(e, 600)}"]
                ctx["cells"].append({"cell": name, "pass": not f, "fails": f})
                if f:
                    rest = [c[0].split(" ")[0] for c in cells[i + 1:]]
                    verdict = (f"cell {name}: " + "; ".join(f) + (f" | cells {rest} not reached" if rest else ""), i)
                    break
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        if js is not None:
            try:
                ctx["end"] = {"host": view(js.host), "client": view(js.client)}
            except Exception as e:
                ctx["end"] = f"probe failed: {short(e)}"
        ctx["newCrashLogs"] = new_crash
        if new_crash:
            msg = f"new crash log(s): {new_crash}"
            verdict = (verdict[0] + " | " + msg, verdict[1]) if verdict else (msg, None)
        evidence(rid, ctx)
        results[rid] = verdict is None
        print(f"PASS {rid}" if verdict is None else f"FAIL {rid}: {verdict[0]}", flush=True)
    finally:
        if js is not None:
            if holds:
                for gc, lever in ((js.host, "hold_world_stream"), (js.client, "hold_world_adopt")):
                    try:
                        gc.cmd({"cmd": lever, "on": False})
                    except Exception as e:
                        print(f"[w2p7-sca] release {lever}: {short(e)}", flush=True)
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2p7-sca] shutdown: {short(e)}", flush=True)
        walls[rid] = round(time.time() - t0, 1)


ROWS = (("C28S", "w2p7sca_c28s", c28s_cells, False), ("C28S-b", "w2p7sca_c28sb", c28sb_cells, True))


def main():
    t0, results, walls = time.time(), {}, {}
    for rid, tag, cells_fn, wound in ROWS:
        run_row(rid, tag, ROW_PORT[rid], lambda r, js, ctx, w=wound: stage(r, js, ctx, wound=w), cells_fn,
                results, walls)
    order = [r[0] for r in ROWS]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_battle_end_campaign: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
