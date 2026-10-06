"""W2-P7 S-C-B1 - test_w2_battle_end_separate.py: a SEPARATE campaign's second player ends on its own display-only
debriefing and, at its own OK, returns to ITS OWN world with its guest soldier's full record applied by origin id
(docs rewrite/prompts/w2p7_sc_design.md section 3.2, AMENDMENT P7-6 section 4.2 row C28P, PR-1/PR-12..PR-15,
P7-6 Q1 (a); owner D155 (a), D156 (a), D178 (a), D199 (a); mechanism rulings MR4, MR6, MR12).

Before S-C-B1 (F2491, F387): a SEPARATE campaign client's battle-end latch never arms, so the second player stays on
the battle map while only the host debriefs; its soldier's results are lost.

Construction (CONSTANTS rewrite/w2p7sc-task0/t0/CONSTANTS.md T0-6 (iv), the guest's OWN kill, pinned 3/3 at seed 1;
the design body "the guest kills the last alien" and the TASK-0 pin, NOT the AMENDMENT 4.2 row-header's
`kill_unit_real {faction:1}` shorthand - see FINDINGS F5445): SEPARATE, host set_seed SEED_P right before
coop_mission_start (SEED_P re-hunted for 558349bc8, F5449/F5450: the terror map MAP_FP_P, guest battle unit id 9,
15 hostiles 1000000-1000014); then host kill_unit_real {unit} for every hostile except KEEP (1000000, a Sectoid soldier far from
every cyberdisc), the chain settled after each (F4665: isBusy false AND pendingStates 0); KEEP teleported onto a free
tile adjacent to the guest (both machines, client first, F607), KEEP facing the guest; the guest faced to KEEP by
single-octant turn intents (T-CMD's F394/F395 shape); KEEP health 1; the guest a rifle + clip and TU max; KEEP's TU
zeroed so it cannot reaction-fire (orchestrator ruling, F5446); host set_seed SEED_P again; the CLIENT's battle_intent
snap shot -> KEEP dead, murdererId == the guest (the merged copy gets the kill, rank and medal); END TURN both; the
host's NextTurnState close; the host's debriefing.

Fixture `f` (pre_mission_start, on the client's own geoscape BEFORE the battle, T0-5): set the client's funds to its
own funds + 1234567 (MARKER) and capture the own-world guest record (OWN_BEFORE). Once the host debriefs: the host's
merged copy (COPY = host soldier_record {name:"Guest Zzz"}) and the host's copy of the client's world (H0 =
coop_file_info {role:"host_copy_of_client"}.fnv1a64) - both before any OK.

Row C28P. The GREEN cells are numbered and checked in order; a failed cell ends its row and the rest are "not reached":
  (1) the client's display-only DebriefingState, equal to the host's on the seven content fields with page-2 names
      prefix-stripped (PR-10).
  (2) the client's OK first -> its top GeoscapeState with no CoopState / LoadGameState (none pushed, P6-4);
      geo_state.funds == MARKER (D180: only the marker changes); soldier_record {id: guest_id}'s currentStats, rank,
      recovery, missions, kills, stuns and name == COPY's; missions == OWN_BEFORE.missions + 1; initialStats and
      coopName == OWN_BEFORE's (F2529, D155 keeps init stats and the name); battleEnd.sepReturn == {ownLoaded 1,
      guestsApplied 1, guestsMissing 0, pushed 1}; the host's coop_file_info.fnv1a64 != H0 within FNV_S (the return's
      push changed the host's copy).
  (3) the host's OK + drain -> the host's soldier_record {name:"Guest Zzz"} finds no alive match (F366: the living
      merged copy is deleted); the client zero-disk; host fatalVote.armed 0.
Pre-cell guard (a failure is a FIXTURE-STOP: one CAPTURE line, then the row FAILs "pre-cell"): bring-up, the map pin
(mapFingerprint both == MAP_FP_P), the guest-kill construction (KEEP dead by the guest, status DEAD + murdererId ==
the guest's battle unit id on the host), the host's DebriefingState within DEBRIEF_S, shown/onTop/displayOnly False and
title "Aliens defeated", host fatalVote.armed 0.

RED (commit S-C-B1.1: probes/record zeros and the row, product untouched): C28P fails on exactly cell 1 - the client
never shows a DebriefingState (it stays on the battle map, F387). GREEN (commit S-C-B1.2): C28P passes.
WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

W2-P7 S-C-B2.1 (D181, AMENDMENT P7-6 section 4.3) adds a second boot C28P-dead: every hostile and the guest killed
(seed-independent, host kill_unit_real), so the guest is a casualty. GREEN (commit S-C-B2.2): the death reaches the
client's own world - "Guest Zzz" is in the client's MEMORIAL with a death, its base no longer lists it
(sepReturn.deadApplied 1, one PR-16 [coop-roster] line), and the host's merged memorial copy is removed at its OK
(memorialRemoved 1). RED (this commit, B1 green in place): B1 applies only the alive rows, so the dead guest is still
alive in the client's base (cell 2 red); C28P still passes.

W2-P7 S-C-C.1 (PR-C7, the P7-6 C re-pin at 2e177ff39): cell 2 walks the client's after-battle screens down to its
geoscape; a LAST cell 4 checks the client's chain. RED: exactly cell 4 of both rows (the chain is empty).

W2-P7 S-C-B2.3.1 (F5553, V-C3; the P7-6 B2.3 pin PB-3/PB-8): C28P-dead's `pre_extra` seeds ARMOR_SEED on the client's own
guest before the battle (guarded on the host's battle unit and OWN_BEFORE); a LAST cell 5 checks the client's dead guest
lies in DEFAULT_ARMOR, as the host's buried copy (vanilla's killSoldier(true) reset). RED: it keeps ARMOR_SEED.

Run:  python tools/coop_test/test_w2_battle_end_separate.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
from harness import GameClient, make_user_dir

# ----- TASK 0 pins (docs rewrite/w2p7sc-task0/t0/CONSTANTS.md) -----
SEED_P = 2                          # re-hunted for 558349bc8 (seed 1's shot under-damaged, KEEP survived - F5446/F5449)
MAP_FP_P = -5.253482715141827e+18   # seed 2 terror map fingerprint, equal host+client, guest-credited kill 3/3 (F5450)
KEEP = 1000000                      # CONSTANTS T0-6 (iv): the Sectoid soldier kept for the guest's shot
MARKER_DELTA = 1234567              # CONSTANTS T0-5 / AMENDMENT 4.2 `f`: client set_funds {value: funds + 1234567}
STATUS_DEAD = 6                     # p7t0_common STATUS_DEAD

# ----- this file's constants -----
COOP_PORT = "47206"                 # AMENDMENT P7-6 section 4 (F4545): B1/B2 = 47204-47206 (C28P)
COOP_PORT_DEAD = "47205"            # C28P-dead's boot (same B1/B2 block; distinct so the two sequential boots never reuse a socket)
PR16_LITERAL = "S-C-B2 SEPARATE return"   # PR-16/D218: each applied death + each removed host memorial copy logs one [coop-roster] line with this cause
ROSTER_NAMES = ("HostPlayer", "ClientPlayer")     # session.new_campaign's defaults (PR-10's `[<roster name>] `)
DEBRIEF_FIELDS = ("title", "recoveryHeader", "rows", "total", "rating", "soldiers", "recovered")
RECORD_FIELDS = ("currentStats", "rank", "recovery", "missions", "kills", "stuns", "name")
DEBRIEF_S = 60          # the host's DebriefingState after the kill
CLIENT_DEBRIEF_S = 20   # cell 1: the client's display-only DebriefingState after the host's
OK_S = 10               # a machine's GeoscapeState after its own OK
DRAIN_S = 60            # the host's OK + follow-ups down to its GeoscapeState
FNV_S = 30              # cell 2: the host's copy-of-client changes after the return's push (AMENDMENT 4.2 "within 30 s")
WAIT_TOPS = ("VoteMenu", "BattlescapeState", "SaveGameState")   # never dismissed by a drain (not ours to pop)
LOADGAME_PUSH = "push class OpenXcom::LoadGameState"           # the [coop-ui] state-push log line (P6-4)
# W2-P7 S-C-C.1 PR-C7 (F5621): the after-battle screens; their OK is a plain popState = dismiss_popup (F5628).
FOLLOWUPS = ("CommendationLateState", "CommendationState", "PromotionsState", "CannotReequipState")
CHAIN_C28P = ["PromotionsState"]              # A.10: the host's drained follow-ups, 2 equal red-build runs (guest promoted)
CHAIN_C28P_DEAD = ["CommendationLateState"]   # A.10: the same 2 runs (the dead guest, DebriefingState :778, F4532)
ARMOR_SEED = "STR_PERSONAL_ARMOR_UC"   # B2.3 pin PB-3: bin/standard/xcom1/armors.rul :28 (client seed_soldier_armor)
DEFAULT_ARMOR = "STR_NONE_UC"          # B2.3 pin PB-3: the soldier type's default armor, xcom1/soldiers.rul :41


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


def unit(gc, uid):
    return session.units_by_id(battle_state(gc)).get(uid) or {}


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


def soldier_recs(gc, sid=None, name=None):
    """soldier_record's records list (F2520): every soldier of this machine's world matching id/name."""
    req = {"cmd": "soldier_record"}
    if sid is not None:
        req["id"] = sid
    if name is not None:
        req["name"] = name
    r = gc.cmd(req)
    return r.get("records") or [], {k: r.get(k) for k in ("ok", "count", "error")}


def soldier_rec(gc, sid=None, name=None):
    """The first matching soldier_record record ({} when none)."""
    recs, _meta = soldier_recs(gc, sid=sid, name=name)
    return recs[0] if recs else {}


def coop_fnv(gc, role):
    r = gc.cmd({"cmd": "coop_file_info", "role": role})
    return r.get("fnv1a64"), {k: r.get(k) for k in ("ok", "present", "bytes", "error")}


def log_count(gc, literal):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if literal in ln)
    except OSError:
        return 0


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


def view(gc):
    """One machine's state for the EVIDENCE line (every field from an existing probe)."""
    es = event_state(gc)
    return {"stack": stack(gc), "phase": es.get("phase"),
            "coopBattle": (es.get("researchMode") or {}).get("coopBattle"),
            "fatalVoteArmed": (es.get("fatalVote") or {}).get("armed"),
            "battleEnd": es.get("battleEnd")}


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
                            "units": [{k: u.get(k) for k in ("id", "faction", "name", "status", "health", "isOut",
                                                             "murdererId", "x", "y", "z", "direction", "tu")}
                                      for u in bs.get("units", []) if u.get("faction") != 2],
                            "debrief": gc.cmd({"cmd": "debrief_state"})}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(f"{name}: {err[:600]}")


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


def client_ok_through_followups(client, ctx, key):
    """PR-C7: OK as today; wait <= OK_S for the stack ["GeoscapeState"] + T (T in FOLLOWUPS, no CoopState/LoadGameState)
    -> ctx[key]["clientChain"] = T; dismiss_popup each FOLLOWUPS top; then today's geo_clean wait."""
    ok1, slot = press_ok(client), ctx.setdefault(key, {})
    if not ok1["pressed"]:
        return ok1, False, 0
    def shaped():
        st = stack(client)
        good = (st[:1] == ["GeoscapeState"] and all(s in FOLLOWUPS for s in st[1:])
                and not any(("CoopState" in s or "LoadGameState" in s) for s in st))
        if good:
            slot["clientChain"] = st[1:]
        return good
    wait_until(shaped, OK_S)
    t0 = time.time()
    while top(client) in FOLLOWUPS and time.time() - t0 < OK_S:
        client.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.25)
    ok, secs = wait_until(lambda: geo_clean(client), OK_S)
    return ok1, ok, secs


def host_followups(screens, shared=False):
    """PR-C7: a drain's FOLLOWUPS tops in push order; repeats and (SEPARATE, F5421) CannotReequipState dropped."""
    tops = [s.get("top") for s in screens or [] if s.get("top") in FOLLOWUPS[:4 if shared else 3]]
    return [t for i, t in enumerate(tops) if i == 0 or tops[i - 1] != t][::-1]


def cell_client_chain(host, client, ctx, key, host_key, pinned):
    """PR-C7 LAST cell: the client's battleEnd.chain == the stack it showed after its OK, non-empty, == the host's
    drained follow-ups and == the pinned constant (A.10). RED (S-C-C.1): the client's chain is empty."""
    chain, seen = record(client).get("chain"), (ctx.get(key) or {}).get("clientChain")
    want = host_followups((ctx.get(host_key) or {}).get("screens"))
    ctx["chainCell"] = {"chain": chain, "clientChain": seen, "hostFollowups": want, "pinned": pinned}
    if not chain:
        return [f"the client's chain is empty: battleEnd.chain={chain!r}, its stack after the OK {seen!r} (want "
                f"{pinned!r}; the host drained {want!r})"]
    return [f"client battleEnd.chain={chain!r} != {n} {v!r}" for n, v in
            (("its stack after the OK", seen), ("the host's drained follow-ups", want), ("the pinned", pinned))
            if chain != v]


# ===================== construction helpers (adapted from TASK 0 t_kill.py) =====================


def both(host, client, req):
    """A per-machine staging lever sent to BOTH machines, client first (F607). Returns (host resp, client resp)."""
    rc = client.cmd(dict(req))
    rh = host.cmd(dict(req))
    session.wait_seq_barrier(host, client)  # W2-U8c (F6495)
    return rh, rc


def chain_settled(host, client, stable=1.0, timeout=45, interval=0.2, want_live=None):
    """After a host kill_unit_real: the host idle (not isBusy, pendingStates 0, BattlescapeState top, [live hostiles ==
    want_live when given], host lastSeqEmitted == client lastSeqApplied) held `stable` s (F4665: wait_host_idle passed
    mid cyberdisc-explosion chain). Returns (ok, secs, samples)."""
    samples, t0, idle_since, last = [], time.time(), None, None
    while time.time() - t0 < timeout:
        bs = battle_state(host)
        eh, ec = event_state(host), event_state(client)
        live = sum(1 for u in bs.get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
        tp = top(host)
        s = (bool(bs.get("isBusy")), bs.get("pendingStates"), tp, live,
             eh.get("lastSeqEmitted"), ec.get("lastSeqApplied"), eh.get("busyOwnerSeat"))
        if s != last:
            samples.append((round(time.time() - t0, 2),) + s)
            last = s
        idle = (not s[0] and s[1] == 0 and tp == "BattlescapeState"
                and (want_live is None or live == want_live) and s[4] == s[5])
        if idle:
            idle_since = idle_since or time.time()
            if time.time() - idle_since >= stable:
                return True, round(time.time() - t0, 2), samples
        else:
            idle_since = None
        time.sleep(interval)
    return False, round(time.time() - t0, 2), samples


def order_done(host, client):
    """The client's battle_intent settled: no intent in flight, both queues drained, the host idle (t_kill order_done)."""
    ec, eh = event_state(client), event_state(host)
    bh = battle_state(host)
    return (ec.get("inFlight") is None and battle_state(client).get("coopPendingIntent") is None
            and eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0 and not bh.get("isBusy")
            and bh.get("pendingStates") == 0)


def end_turn_both(host, client):
    """SEPARATE ending: END TURN client then host (end_turn_button), gated on the host painting END TURN 1/2."""
    client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
    wait_until(lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2", 20)
    host.cmd({"cmd": "battle_action", "action": "end_turn_button"})


def close_host_nextturn(host, timeout=60):
    wait_until(lambda: "NextTurnState" in (host.cmd({"cmd": "list_widgets"}).get("state") or "")
               or any("DebriefingState" in s for s in stack(host)), timeout)
    if any("DebriefingState" in s for s in stack(host)):
        return None
    return host.cmd({"cmd": "dismiss_popup"})


def guest_kill(host, client, gid, ctx, shot_seed=SEED_P, fixture_stop=True):
    """CONSTANTS T0-6 (iv): the guest's OWN kill of the last alien, KEEP's TU zeroed first so it cannot reaction-fire
    (orchestrator ruling, F5446: KEEP reaction-fired and killed the guest). Fills ctx['construction'] and returns the
    shot outcome. With fixture_stop (the test), raises FixtureMiss after a CAPTURE line if the kill does not reproduce
    at `shot_seed`; the seed re-hunt calls with fixture_stop=False to inspect every seed."""
    m = (host, client)
    con = ctx.setdefault("construction", {})
    # 1. kill every hostile except KEEP, the chain settled after each
    others = [u["id"] for u in battle_state(host).get("units", [])
              if u.get("faction") == 1 and not u.get("isOut") and u["id"] != KEEP]
    con["others"] = others
    for uid in others:
        host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        chain_settled(host, client, stable=1.0, timeout=45, want_live=None)
    live = sorted(u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
    gnow = unit(host, gid)
    con["afterKills"] = {"liveHostiles": live, "guestOut": gnow.get("isOut"), "guestPos": session.pos_of(gnow)
                         if gnow.get("x") is not None else None}
    if live != [KEEP] or gnow.get("isOut"):
        capture("guest-kill: kill others", f"live hostiles {live} (want [{KEEP}]) / guest out {gnow.get('isOut')}", m)
    # 2. KEEP onto a free tile adjacent to the guest, facing the guest
    tile = session._t_cmd_adjacent_free_tile(host, gnow)
    gpos = session.pos_of(gnow)
    face_guest = session._dir_to(tile, gpos)
    rh, rc = both(host, client, {"cmd": "battle_teleport_unit", "unit": KEEP, "x": tile[0], "y": tile[1],
                                 "z": tile[2], "dir": face_guest})
    con["teleport"] = {"tile": tile, "faceGuest": face_guest, "host": rh.get("ok"), "client": rc.get("ok")}
    # 3. face the guest to KEEP by single-octant turn intents (client)
    to_dir = session._dir_to(gpos, tile)
    for d in session._octant_chain(gnow.get("direction"), to_dir):
        base = event_state(client).get("lastSeqApplied", 0)
        session.send_turn(client, gid, d)
        session.wait_turn_settled(host, client, base)
    con["faced"] = {"toDir": to_dir, "guestDir": unit(host, gid).get("direction")}
    # 4. KEEP health 1, the guest's rifle + clip and TU max
    both(host, client, {"cmd": "battle_set_unit_state", "unit": KEEP, "health": 1})
    gh, gc_ = both(host, client, {"cmd": "battle_give", "unit": gid, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                                  "clear_hands": True})
    weapon, ammo = gh.get("weaponId"), gh.get("ammoId")
    con["give"] = {"host": {k: gh.get(k) for k in ("ok", "weaponId", "ammoId", "error")},
                   "client": {k: gc_.get(k) for k in ("ok", "weaponId", "ammoId", "error")}}
    if weapon is None or weapon != gc_.get("weaponId") or ammo != gc_.get("ammoId"):
        capture("guest-kill: battle_give", f"rifle/clip ids differ or missing {con['give']}", m)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": gid, "tu": 255})
    # KEEP's TU zeroed so it cannot reaction-fire (orchestrator ruling; F5446 KEEP reacted and killed the guest)
    rh0, rc0 = both(host, client, {"cmd": "battle_set_unit_state", "unit": KEEP, "tu": 0})
    con["keepTuZero"] = {"host": rh0.get("tu"), "client": rc0.get("tu")}
    # 5. the shot at `shot_seed`
    k = unit(host, KEEP)
    host.cmd({"cmd": "set_seed", "seed": shot_seed})
    r = client.cmd({"cmd": "battle_intent", "kind": "shoot", "actor": gid,
                    "plan": {"action": "snap", "weapon": weapon, "ammo": ammo,
                             "target": {"x": k["x"], "y": k["y"], "z": k["z"]}, "targetUnit": KEEP,
                             "forceFire": False}})
    done, secs = wait_until(lambda: order_done(host, client), 45, 0.1)
    time.sleep(0.5)
    kh = unit(host, KEEP)
    con["shot"] = {"shotSeed": shot_seed, "resp": {kk: r.get(kk) for kk in ("ok", "iseq", "error", "sent")},
                   "done": done, "secs": secs,
                   "keepHost": {kk: kh.get(kk) for kk in ("status", "health", "murdererId", "killedBy", "isOut")},
                   "keepClient": {kk: unit(client, KEEP).get(kk) for kk in ("status", "health", "murdererId")},
                   "guestHost": {kk: unit(host, gid).get(kk) for kk in ("tu", "health", "direction", "isOut")}}
    con["killed"] = (kh.get("status") == STATUS_DEAD and kh.get("murdererId") == gid)
    if not con["killed"] and fixture_stop:
        capture("guest-kill: the shot", f"KEEP not killed by the guest at shot seed {shot_seed}: "
                f"keepHost={con['shot']['keepHost']} (want status {STATUS_DEAD}, murdererId {gid})", m)
    return con["shot"]


# ===================== bring-up, staging, ending (pre-cell) =====================


def kill_all_and_guest(host, client, gid, ctx):
    """C28P-dead construction (AMENDMENT P7-6 section 4.3; seed-independent, no guest shot): kill EVERY hostile (the chain
    settled after each, F4665), then kill the guest itself (host kill_unit_real {unit: <guest's battle unit id>}). The
    guest's death then reaches the owner's world (D181); it needs no killer credit (F4536) and no seed."""
    m = (host, client)
    con = ctx.setdefault("construction", {})
    hostiles = [u["id"] for u in battle_state(host).get("units", [])
                if u.get("faction") == 1 and not u.get("isOut")]
    con["hostiles"] = hostiles
    for uid in hostiles:
        host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        chain_settled(host, client, stable=1.0, timeout=45, want_live=None)
    host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": gid})
    chain_settled(host, client, stable=1.0, timeout=45, want_live=None)
    live = sorted(u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
    gnow = unit(host, gid)
    con["afterKills"] = {"liveHostiles": live, "guestStatus": gnow.get("status"), "guestOut": gnow.get("isOut")}
    if live:
        capture("dead-kill: hostiles remain", f"live hostiles {live} (want none left to kill)", m)
    if gnow.get("status") != STATUS_DEAD:
        capture("dead-kill: guest not dead", f"guest (unit {gid}) status {gnow.get('status')!r} (want DEAD "
                f"{STATUS_DEAD}) after host kill_unit_real", m)


def _stage_common(rid, host, client, ctx, port, kill_fn, precheck, pre_extra=None):
    """The pre-cell part shared by C28P and C28P-dead: the SEPARATE battle on SEED_P with the T0-5 marker, `kill_fn`'s
    ending construction, the ending, and the host's debriefing - plus COPY / H0 / OWN_BEFORE. `precheck(copy)` returns a
    reason string (or None) the host's merged 'Guest Zzz' copy must satisfy. Fills ctx; raises FixtureMiss (after a
    CAPTURE line)."""
    m = (host, client)

    def marker(h, c):
        g0 = c.cmd({"cmd": "geo_state"})
        mv = int(g0.get("funds")) + MARKER_DELTA
        c.ok({"cmd": "set_funds", "value": mv})
        ctx["marker"] = mv
        if pre_extra is not None:   # W2-P7 S-C-B2.3.1 PB-8: before OWN_BEFORE and the battle-entry snapshot (F6221)
            pre_extra(h, c, ctx)
        ctx["ownBefore"] = soldier_rec(c, name="Guest Zzz")

    def seed_pin(h, c):
        h.ok({"cmd": "set_seed", "seed": SEED_P})

    try:
        host_squad, guest_id = session.bring_up_separate_guest_battle(
            host, client, port=port, pre_mission_start=marker, pre_landing=seed_pin)
    except Exception as e:
        capture("bring_up_separate_guest_battle", short(e, 800), m)
    ctx["hostSquad"] = host_squad
    ctx["guestId"] = guest_id
    fp = (battle_state(host).get("mapFingerprint"), battle_state(client).get("mapFingerprint"))
    ctx["mapFingerprint"] = fp
    if fp != (MAP_FP_P, MAP_FP_P):
        capture("map pin", f"mapFingerprint (host, client) {fp} (want both {MAP_FP_P!r}, SEED_P {SEED_P})", m)
    guests = [u for u in battle_state(host).get("units", []) if "Guest" in (u.get("name") or "")]
    if len(guests) != 1:
        capture("guest unit", f"expected one battle unit named 'Guest*', got {[u.get('name') for u in guests]}", m)
    gid = guests[0]["id"]
    ctx["guestBattleId"] = gid

    kill_fn(host, client, gid, ctx)

    ctx["loadGamePushes0"] = log_count(client, LOADGAME_PUSH)
    end_turn_both(host, client)
    close_host_nextturn(host)
    ok, secs = wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    ctx["ending"] = {"reached": ok, "secs": secs, "hostStack": stack(host)}
    if not ok:
        capture("host debriefing", f"no host DebriefingState within {DEBRIEF_S}s of the kill ({ctx['ending']})", m)
    hdeb = host.cmd({"cmd": "debrief_state"})
    ctx["hostDebrief"] = hdeb
    bad = [f"host debrief_state.{k}={hdeb.get(k)!r} (want {w!r})"
           for k, w in (("shown", True), ("onTop", True), ("displayOnly", False), ("title", "Aliens defeated"))
           if hdeb.get(k) != w]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    if armed != 0:
        bad.append(f"host fatalVote.armed={armed!r} (want 0: no S-V vote, F4544)")
    if bad:
        capture("host debriefing pin", "; ".join(bad), m)
    # COPY (the host's merged copy) and H0 (the host's copy of the client blob), both before any OK
    ctx["copy"] = soldier_rec(host, name="Guest Zzz")
    ctx["h0"], ctx["h0meta"] = coop_fnv(host, "host_copy_of_client")
    reason = precheck(ctx["copy"])
    if reason:
        capture("merged-copy precondition", reason, m)


def _precheck_alive(copy):
    if copy.get("kills", 0) < 1:
        return (f"the host's merged 'Guest Zzz' copy has kills {copy.get('kills')!r} after the debriefing "
                f"(want >= 1: the guest's shot was credited)")
    return None


def stage(rid, host, client, ctx):
    """C28P pre-cell: the guest's OWN kill of the last alien (the live merged copy is credited the kill / rank)."""
    _stage_common(rid, host, client, ctx, COOP_PORT, guest_kill, _precheck_alive)


def _precheck_dead(copy):
    if not copy.get("dead"):
        return (f"the host's merged 'Guest Zzz' copy is not dead after the debriefing (where={copy.get('where')!r} "
                f"dead={copy.get('dead')!r}): the guest kill did not reach the host memorial")
    return None


def seed_guest_armor(h, c, ctx):
    """C28P-dead `pre_extra` (B2.3 pin section 5): the client's own guest wears ARMOR_SEED (seed_soldier_armor, no store
    change)."""
    sid = soldier_rec(c, name="Guest Zzz").get("id")
    r = c.cmd({"cmd": "seed_soldier_armor", "soldier_id": sid, "armor": ARMOR_SEED})
    ctx["armorSeed"] = {"soldierId": sid, "resp": {k: r.get(k) for k in ("ok", "armor", "error")}}
    if r.get("armor") != ARMOR_SEED:
        capture("armor seed", f"client seed_soldier_armor {ctx['armorSeed']} (want armor {ARMOR_SEED!r})", (h, c))


def armored_kill_all_and_guest(host, client, gid, ctx):
    """C28P-dead construction with the armor guard: the host's guest battle unit and OWN_BEFORE wear ARMOR_SEED."""
    worn = {"hostUnit": unit(host, gid).get("armor"), "ownBefore": (ctx.get("ownBefore") or {}).get("armor")}
    ctx["armorWorn"] = worn
    if worn != {"hostUnit": ARMOR_SEED, "ownBefore": ARMOR_SEED}:
        capture("armor worn", f"guest armor {worn} (want both {ARMOR_SEED!r})", (host, client))
    kill_all_and_guest(host, client, gid, ctx)


def _precheck_dead_armor(copy):
    reason = _precheck_dead(copy)
    if reason is None and copy.get("armor") != DEFAULT_ARMOR:
        reason = f"the host's buried 'Guest Zzz' copy wears {copy.get('armor')!r} (want {DEFAULT_ARMOR!r}, vanilla's reset)"
    return reason


def stage_dead(rid, host, client, ctx):
    """C28P-dead pre-cell: every hostile and the guest killed (seed-independent), so the host's memorial copy is dead."""
    _stage_common(rid, host, client, ctx, COOP_PORT_DEAD, armored_kill_all_and_guest, _precheck_dead_armor,
                  pre_extra=seed_guest_armor)


# ===================== cells =====================


def cell_debriefs(host, client, ctx):
    """Cell 1 (the RED cell): the client's display-only debriefing, equal to the host's (PR-10 stripped)."""
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


def cell_client_return(host, client, ctx):
    """Cell 2: the client's OK -> its own geoscape; funds == MARKER; the guest's record applied; sepReturn; the host's
    copy-of-client changed."""
    ok1, ok, secs = client_ok_through_followups(client, ctx, "clientReturn")   # PR-C7
    pushes = log_count(client, LOADGAME_PUSH) - ctx["loadGamePushes0"]
    rec = soldier_rec(client, sid=ctx["guestId"])
    before = ctx.get("ownBefore") or {}
    copy = ctx.get("copy") or {}
    g = client.cmd({"cmd": "geo_state"})
    crec = record(client)
    sep = crec.get("sepReturn") if isinstance(crec.get("sepReturn"), dict) else {}
    ctx["clientReturn"].update({"ok": ok1, "reached": ok, "secs": secs, "clientStack": stack(client),
                                "loadGamePushes": pushes, "funds": g.get("funds"), "returnedRecord": rec,
                                "sepReturn": sep})
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"client OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not ok:
        f.append(f"client not on a clean GeoscapeState within {OK_S}s of its OK (stack {stack(client)})")
        return f
    if pushes != 0:
        f.append(f"client pushed {pushes} LoadGameState(s) since the ending (want 0: in-place return, P6-4)")
    if g.get("funds") != ctx.get("marker"):
        f.append(f"client geo_state.funds={g.get('funds')!r} (want the MARKER {ctx.get('marker')!r}, D180)")
    for k in RECORD_FIELDS:
        if rec.get(k) != copy.get(k):
            f.append(f"returned guest soldier_record.{k}={rec.get(k)!r} != the host COPY's {copy.get(k)!r}")
    if rec.get("missions") != (before.get("missions") or 0) + 1:
        f.append(f"returned guest missions={rec.get('missions')!r} (want OWN_BEFORE.missions "
                 f"{before.get('missions')!r} + 1)")
    if rec.get("initialStats") != before.get("initialStats"):
        f.append(f"returned guest initialStats changed (F2529): {rec.get('initialStats')!r} != OWN_BEFORE's "
                 f"{before.get('initialStats')!r}")
    if rec.get("coopName") != before.get("coopName"):
        f.append(f"returned guest coopName={rec.get('coopName')!r} != OWN_BEFORE's {before.get('coopName')!r}")
    want_sep = {"ownLoaded": 1, "guestsApplied": 1, "guestsMissing": 0, "pushed": 1}
    bad_sep = {k: (sep.get(k), w) for k, w in want_sep.items() if sep.get(k) != w}
    if bad_sep:
        f.append(f"client battleEnd.sepReturn mismatch (key: (got, want)) = {bad_sep}")
    fnv_ok, fsecs = wait_until(lambda: coop_fnv(host, "host_copy_of_client")[0] not in (ctx.get("h0"), None, ""),
                               FNV_S)
    cur_fnv, _m = coop_fnv(host, "host_copy_of_client")
    ctx["clientReturn"]["hostCopyFnv"] = {"h0": ctx.get("h0"), "now": cur_fnv, "waited": fsecs}
    if not fnv_ok:
        f.append(f"host coop_file_info.fnv1a64={cur_fnv!r} still == H0 {ctx.get('h0')!r} after {FNV_S}s "
                 f"(the return's push should change the host's copy)")
    return f


def cell_host_ok(host, client, ctx):
    """Cell 3: the host's OK + drain -> the merged copy gone (F366); the client zero-disk; fatalVote.armed 0."""
    ok1 = press_ok(host)
    reached, screens = drain(host) if ok1["pressed"] else (False, [])
    recs, meta = soldier_recs(host, name="Guest Zzz")
    alive = [r for r in recs if not r.get("dead")]
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    ctx["hostOk"] = {"ok": ok1, "reached": reached, "screens": screens, "hostStack": stack(host),
                     "guestRecords": recs, "fatalVoteArmed": armed}
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    if not reached:
        f.append(f"host not on GeoscapeState within {DRAIN_S}s of its OK (stack {stack(host)}, screens {screens})")
    if alive:
        f.append(f"host still lists an alive 'Guest Zzz' after its OK (F366: the living merged copy must be deleted): "
                 f"{alive}")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        f.append(str(e))
    if armed != 0:
        f.append(f"host fatalVote.armed={armed!r} after the ending (want 0)")
    return f


def c28p_cells(host, client, ctx):
    return [
        ("1 the client's display-only debriefing, equal to the host's", lambda: cell_debriefs(host, client, ctx)),
        ("2 the client's OK first; its own world with the guest's record", lambda: cell_client_return(host, client, ctx)),
        ("3 the host's OK + drain; the merged copy gone", lambda: cell_host_ok(host, client, ctx)),
        ("4 the client's chain", lambda: cell_client_chain(host, client, ctx, "clientReturn", "hostOk", CHAIN_C28P)),
    ]


# ===================== C28P-dead cells (W2-P7 S-C-B2.1, D181) =====================


def cell_dead_return(host, client, ctx):
    """C28P-dead cell 2 (the RED cell): the client's OK -> its own geoscape; the guest reaches the client's MEMORIAL
    with a death and its base no longer lists it (D181); sepReturn.deadApplied 1; one PR-16 [coop-roster] line in the
    client log. RED: the guest is still alive in the client's base (B1 applies alive rows only; the dead guest is not in
    the host's bases so B1's payload carries no row for it)."""
    ok1, ok, secs = client_ok_through_followups(client, ctx, "deadReturn")   # PR-C7
    recs, meta = soldier_recs(client, sid=ctx["guestId"])
    crec = record(client)
    sep = crec.get("sepReturn") if isinstance(crec.get("sepReturn"), dict) else {}
    pr16 = log_count(client, PR16_LITERAL)
    dead_rec = next((r for r in recs if r.get("dead")), None)
    base_rec = next((r for r in recs if r.get("where") == "base"), None)
    ctx["deadReturn"].update({"ok": ok1, "reached": ok, "secs": secs, "clientStack": stack(client),
                              "records": recs, "sepReturn": sep, "pr16": pr16})
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"client OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not ok:
        f.append(f"client not on a clean GeoscapeState within {OK_S}s of its OK (stack {stack(client)})")
        return f
    if dead_rec is None:
        f.append(f"client soldier_record id={ctx['guestId']} is not dead after the return (B1 applies alive rows "
                 f"only): {recs}")
    elif not dead_rec.get("death"):
        f.append(f"client's dead guest has no death record (D181 carries the YAML's death): {dead_rec}")
    if base_rec is not None:
        f.append(f"client's base still lists the guest after the return (D181: the dead guest leaves the base): "
                 f"{base_rec}")
    if sep.get("deadApplied") != 1:
        f.append(f"client battleEnd.sepReturn.deadApplied={sep.get('deadApplied')!r} (want 1)")
    if pr16 != 1:
        f.append(f"client PR-16 [coop-roster] '{PR16_LITERAL}' line count {pr16} (want exactly 1: the applied death)")
    return f


def cell_host_memorial(host, client, ctx):
    """C28P-dead cell 3: the host's OK + drain -> the host's memorial copy of the dead guest is gone
    (coopRemoveGuestMemorialCopies, memorialRemoved 1); the client zero-disk; fatalVote.armed 0."""
    ok1 = press_ok(host)
    reached, screens = drain(host) if ok1["pressed"] else (False, [])
    recs, meta = soldier_recs(host, name="Guest Zzz")
    hrec = record(host)
    mem = hrec.get("memorialRemoved")
    armed = (event_state(host).get("fatalVote") or {}).get("armed")
    ctx["hostMemorial"] = {"ok": ok1, "reached": reached, "screens": screens, "hostStack": stack(host),
                           "guestRecords": recs, "memorialRemoved": mem, "fatalVoteArmed": armed}
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    if not reached:
        f.append(f"host not on GeoscapeState within {DRAIN_S}s of its OK (stack {stack(host)}, screens {screens})")
    if recs:
        f.append(f"host still lists a 'Guest Zzz' memorial copy after its OK (D181: coopRemoveGuestMemorialCopies "
                 f"should delete the tagged dead copy): {recs}")
    if mem != 1:
        f.append(f"host battleEnd.memorialRemoved={mem!r} (want 1)")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        f.append(str(e))
    if armed != 0:
        f.append(f"host fatalVote.armed={armed!r} after the ending (want 0)")
    return f


def cell_dead_armor(host, client, ctx):
    """C28P-dead LAST cell 5 (B2.3 pin section 5; F5553, V-C3): the client's dead guest lies in DEFAULT_ARMOR, == the host's
    buried copy (COPY). RED: it keeps ARMOR_SEED (the overlay copies no armor key)."""
    recs, _meta = soldier_recs(client, sid=ctx["guestId"])
    got = next((r for r in recs if r.get("dead")), {}).get("armor")
    want = (ctx.get("copy") or {}).get("armor")
    ctx["deadArmor"] = {"client": got, "copy": want, "records": len(recs)}
    if got != DEFAULT_ARMOR or got != want:
        return [f"the client's dead guest wears {got!r} (want its default armor {DEFAULT_ARMOR!r} == the host COPY's {want!r})"]
    return []


def c28p_dead_cells(host, client, ctx):
    return [
        ("1 the client's display-only debriefing, equal to the host's", lambda: cell_debriefs(host, client, ctx)),
        ("2 the client's OK first; the dead guest reaches its memorial", lambda: cell_dead_return(host, client, ctx)),
        ("3 the host's OK + drain; the host memorial copy removed", lambda: cell_host_memorial(host, client, ctx)),
        ("4 the client's chain", lambda: cell_client_chain(host, client, ctx, "deadReturn", "hostMemorial",
                                                           CHAIN_C28P_DEAD)),
        ("5 the client's dead guest is buried in its default armor", lambda: cell_dead_armor(host, client, ctx)),
    ]


# ===================== one row =====================


def run_row(rid, host, client, results, walls, stage_fn, cells_fn):
    """One boot (host/client already spawned + connected): stage (pre-cell), then the cells in order; ONE EVIDENCE
    line, then PASS / FAIL."""
    t0, ctx = time.time(), {"row": rid}
    crash0 = session._crash_log_snapshot()
    verdict = None
    try:
        try:
            stage_fn(rid, host, client, ctx)
        except Exception as e:
            verdict = (f"pre-cell (FIXTURE-STOP) {e if isinstance(e, FixtureMiss) else short(e, 800)}", None)
        if verdict is None:
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
        try:
            ctx["end"] = {"host": view(host), "client": view(client)}
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
        walls[rid] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    # Two sequential boots (fresh host/client each): C28P (the B1 alive-return row) then C28P-dead (W2-P7 S-C-B2.1, D181).
    boots = [("C28P", stage, c28p_cells), ("C28P-dead", stage_dead, c28p_dead_cells)]
    for rid, stage_fn, cells_fn in boots:
        slug = rid.lower().replace("-", "_")
        host = GameClient("host", 0, make_user_dir(f"w2p7scb1_{slug}_host"))
        client = GameClient("client", 0, make_user_dir(f"w2p7scb1_{slug}_client"))
        try:
            host.spawn(); client.spawn(); host.connect(); client.connect()
            run_row(rid, host, client, results, walls, stage_fn, cells_fn)
        finally:
            for gc in (host, client):
                try:
                    gc.shutdown()
                except Exception as e:
                    print(f"[w2p7-scb1] shutdown {gc.name}: {short(e)}", flush=True)
    order = ["C28P", "C28P-dead"]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_battle_end_separate: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
