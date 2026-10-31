"""battle_end_helpers.py: shared helpers for the battle-ending tests (probes, the debriefing OK and drain, the
after-battle chain, chain_settled / end_turn_both / close_host_nextturn) and the Separate battle construction in which
the client's soldier "Guest Zzz" (session.bring_up_separate_guest_battle) makes the OWN kill of the last alien.

The construction (_stage_common with guest_kill): SEPARATE, host set_seed SEED_P right before coop_mission_start (the
terror map MAP_FP_P); every hostile except KEEP (1000000, a Sectoid soldier far from every cyberdisc) killed by ONE host
kill_units_real {units}, every chain settled once (isBusy false AND pendingStates 0); KEEP teleported onto a free tile
adjacent to the guest (both machines, client first), KEEP facing the guest; the guest faced to KEEP by single-octant
turn intents; KEEP health 1; the guest a rifle + clip and TU max; KEEP's TU zeroed so it cannot reaction-fire; host
set_seed SEED_P again; the CLIENT's battle_intent snap shot -> KEEP dead, murdererId == the guest; END TURN both; the
host's NextTurnState close; the host's debriefing. ctx["ownBefore"] = the client's record of the guest before the
battle, ctx["copy"] = the host's record of it once the host debriefs (before any OK).

The cells shared by the tests that use it: cell_debriefs (the client's display-only debriefing equals the host's),
cell_host_ok (the host's OK + drain; the guest stays one living soldier, the client's), cell_client_chain (the client's
after-battle chain). run_row runs one boot: the pre-cell staging, then the cells in order.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
from harness import GameClient, make_user_dir

# ----- pinned values (from capture runs) -----
SEED_P = 2                          # the guest's shot kills KEEP at this seed (at seed 1 the shot leaves KEEP alive)
MAP_FP_P = -5.253482715141827e+18   # seed 2 terror map fingerprint, equal host+client; the guest's kill in 3 of 3 runs
KEEP = 1000000                      # the Sectoid soldier kept for the guest's shot
STATUS_DEAD = 6                     # src/Mod/Unit.h enum UnitStatus
CLIENT_SEAT = 1                     # the client's soldier's owner / coop in a SEPARATE save

# ----- shared constants -----
ROSTER_NAMES = ("HostPlayer", "ClientPlayer")     # session.new_campaign's defaults (the page-2 name prefixes)
DEBRIEF_FIELDS = ("title", "recoveryHeader", "rows", "total", "rating", "soldiers", "recovered")
DEBRIEF_S = 60          # the host's DebriefingState after the kill
CLIENT_DEBRIEF_S = 20   # cell_debriefs: the client's display-only DebriefingState after the host's
OK_S = 10               # a machine's GeoscapeState after its own OK
DRAIN_S = 60            # the host's OK + follow-ups down to its GeoscapeState
WAIT_TOPS = ("VoteMenu", "BattlescapeState", "SaveGameState")   # never dismissed by a drain (not ours to pop)
LOADGAME_PUSH = "push class OpenXcom::LoadGameState"           # the [coop-ui] state-push log line
# The after-battle screens; their OK is a plain popState = dismiss_popup.
FOLLOWUPS = ("CommendationLateState", "CommendationState", "PromotionsState", "CannotReequipState")


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
    """soldier_record's records list: every soldier of this machine's world matching id/name."""
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


def log_count(gc, literal):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if literal in ln)
    except OSError:
        return 0


def strip_prefix(name):
    """A leading `[<roster name>] ` (the page-2 player prefix) is stripped, so the comparison ignores it."""
    for n in ROSTER_NAMES:
        p = f"[{n}] "
        if isinstance(name, str) and name.startswith(p):
            return name[len(p):]
    return name


def debrief_view(deb):
    """The seven content fields of a debrief_state with page-2 names prefix-stripped."""
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
    """A setup failure: CAPTURE every machine's event_state, battle_state flags and stack (whole), then raise."""
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
    """The client's OK; wait <= OK_S for the stack ["GeoscapeState"] + T (T in FOLLOWUPS, no CoopState/LoadGameState)
    -> ctx[key]["clientChain"] = T; dismiss_popup each FOLLOWUPS top; then the geo_clean wait."""
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
    """A drain's FOLLOWUPS tops in push order; repeats and (SEPARATE) CannotReequipState dropped."""
    tops = [s.get("top") for s in screens or [] if s.get("top") in FOLLOWUPS[:4 if shared else 3]]
    return [t for i, t in enumerate(tops) if i == 0 or tops[i - 1] != t][::-1]


def cell_client_chain(host, client, ctx, key, host_key, pinned):
    """The chain cell: the client's battleEnd.chain == the stack it showed after its OK, non-empty, == the host's
    drained follow-ups and == the pinned constant."""
    chain, seen = record(client).get("chain"), (ctx.get(key) or {}).get("clientChain")
    want = host_followups((ctx.get(host_key) or {}).get("screens"))
    ctx["chainCell"] = {"chain": chain, "clientChain": seen, "hostFollowups": want, "pinned": pinned}
    if not chain:
        return [f"the client's chain is empty: battleEnd.chain={chain!r}, its stack after the OK {seen!r} (want "
                f"{pinned!r}; the host drained {want!r})"]
    return [f"client battleEnd.chain={chain!r} != {n} {v!r}" for n, v in
            (("its stack after the OK", seen), ("the host's drained follow-ups", want), ("the pinned", pinned))
            if chain != v]


# ===================== construction helpers =====================


def both(host, client, req):
    """A per-machine staging test command sent to BOTH machines, client first. Returns (host resp, client resp)."""
    rc = client.cmd(dict(req))
    rh = host.cmd(dict(req))
    session.wait_seq_barrier(host, client)
    return rh, rc


def chain_settled(host, client, stable=1.0, timeout=45, interval=0.2, want_live=None):
    """After a host kill_unit_real: the host idle (not isBusy, pendingStates 0, BattlescapeState top, [live hostiles ==
    want_live when given], host lastSeqEmitted == client lastSeqApplied) held `stable` s (wait_host_idle alone can pass
    in the middle of a cyberdisc explosion chain). Returns (ok, secs, samples)."""
    samples, t0, idle_since, last = [], time.time(), None, None
    while time.time() - t0 < timeout:
        bs = battle_state(host)
        ec, eh = event_state(client), event_state(host)  # the client is read first
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
    """The client's battle_intent settled: no intent in flight, both queues drained, the host idle."""
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


def guest_kill(host, client, gid, ctx, shot_seed=SEED_P, raise_on_miss=True):
    """The guest's OWN kill of the last alien, KEEP's TU zeroed first so it cannot reaction-fire (otherwise KEEP can
    reaction-fire and kill the guest). Fills ctx['construction'] and returns the
    shot outcome. With raise_on_miss (the test), raises FixtureMiss after a CAPTURE line if the kill does not reproduce
    at `shot_seed`; with raise_on_miss=False a caller can inspect the shot at any seed."""
    m = (host, client)
    con = ctx.setdefault("construction", {})
    # 1. kill every hostile except KEEP in ONE host call (kill_units_real, the same ids in the same order), then ONE
    #    wait for every death chain to settle (the per-kill condition; the per-kill budgets summed)
    others = [u["id"] for u in battle_state(host).get("units", [])
              if u.get("faction") == 1 and not u.get("isOut") and u["id"] != KEEP]
    con["others"] = others
    if others:
        host.cmd({"cmd": "battle_action", "action": "kill_units_real", "units": others})
        chain_settled(host, client, stable=1.0, timeout=45 * len(others), want_live=None)
    live = sorted(u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
    gnow = unit(host, gid)
    con["afterKills"] = {"liveHostiles": live, "guestOut": gnow.get("isOut"), "guestPos": session.pos_of(gnow)
                         if gnow.get("x") is not None else None}
    if live != [KEEP] or gnow.get("isOut"):
        capture("guest-kill: kill others", f"live hostiles {live} (want [{KEEP}]) / guest out {gnow.get('isOut')}", m)
    # 2. KEEP onto a free tile adjacent to the guest, facing the guest
    tile = session._adjacent_free_tile(host, gnow)
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
    # KEEP's TU zeroed so it cannot reaction-fire (otherwise it can react and kill the guest)
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
    if not con["killed"] and raise_on_miss:
        capture("guest-kill: the shot", f"KEEP not killed by the guest at shot seed {shot_seed}: "
                f"keepHost={con['shot']['keepHost']} (want status {STATUS_DEAD}, murdererId {gid})", m)
    return con["shot"]


# ===================== bring-up, staging, ending (pre-cell) =====================


def _stage_common(rid, host, client, ctx, port, kill_fn, precheck, pre_extra=None):
    """The pre-cell staging: the SEPARATE battle on SEED_P, `kill_fn`'s ending construction, the ending, and the
    host's debriefing - plus COPY / OWN_BEFORE. `pre_extra(host, client, ctx)` runs on the geoscape before OWN_BEFORE.
    `precheck(copy)` returns a reason string (or None) the host's 'Guest Zzz' record must satisfy. Fills ctx; raises
    FixtureMiss (after a CAPTURE line)."""
    m = (host, client)

    def marker(h, c):
        if pre_extra is not None:   # before OWN_BEFORE
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

    ctx["loadGamePushes0"] = log_count(client, LOADGAME_PUSH)   # read by test_campaign_followups' cells
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
        bad.append(f"host fatalVote.armed={armed!r} (want 0: no fatal-wounds vote)")
    if bad:
        capture("host debriefing pin", "; ".join(bad), m)
    # COPY (the host's record of the guest), before any OK
    ctx["copy"] = soldier_rec(host, name="Guest Zzz")
    reason = precheck(ctx["copy"])
    if reason:
        capture("copy precondition", reason, m)


# ===================== cells =====================


def cell_debriefs(host, client, ctx):
    """The client's display-only debriefing, equal to the host's (page-2 prefixes stripped)."""
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


def cell_host_ok(host, client, ctx):
    """The host's OK + drain -> the guest stays one living soldier, the client's (owner and coop CLIENT_SEAT), at
    the host's base; the client zero-disk; fatalVote.armed 0."""
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
    oc = [[r.get("where"), r.get("owner"), r.get("coop")] for r in alive]
    if oc != [["base", CLIENT_SEAT, CLIENT_SEAT]]:
        f.append(f"host 'Guest Zzz' [where, owner, coop] {oc} after its OK (want exactly one living record, the "
                 f"client's: {[['base', CLIENT_SEAT, CLIENT_SEAT]]})")
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        f.append(str(e))
    if armed != 0:
        f.append(f"host fatalVote.armed={armed!r} after the ending (want 0)")
    return f


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
            verdict = (f"pre-cell (setup failure) {e if isinstance(e, FixtureMiss) else short(e, 800)}", None)
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
