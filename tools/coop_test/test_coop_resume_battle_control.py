"""SPEC 18 (r4 T4) S1 - SEPARATE mid-battle save/resume, DRAIN-FIRST (D101),
re-pointed to the rewrite model (F376/E63.3) on the E72 Lightning-roof
mid-walk fixture (D121).

The canonical mid-battle-resume proof: a SEPARATE campaign co-op battle
(host's own squad + a CLIENT guest merged in via the two-world merge, SPEC 19
Branch B) is saved WHILE the host's own soldier has a multi-step walk in
flight (>=2 steps pending) - the save must DEFER until the walk drains (M8),
so the file holds the POST-walk state, never a mid-tile WALKING snapshot.
Both instances are killed and relaunched from disk; the pair RESUMES through
the r4 disk-resume handshake (M2/M3/M4): the split control is restored (by
NAME - F376, Branch B mints the guest's battle soldierId on the host), the
turn mode and the walked unit's exact post-walk state survive untouched (the
client never replays the walk), the resumed `battle_ready` hashes EQUAL, and
after the host's RESUME click both machines land on BattlescapeState with no
HostMenu/LobbyMenu left over (M4). The CLIENT then commands its own guest one
step (admitted) and is refused on a host soldier (T-CMD, SPEC 19).

Fixture (E72/D121): the rolled campaign map clusters the host squad beside
the Skyranger, so no long HOST real-click walk exists there. D121 controls
the map instead - the host's campaign base gets a LIGHTNING (a large flat
walkable roof), the mission is a landed SMALL-SCOUT UFO (a deterministic
small map), the sole alien is teleported into the UFO at the ACCESS_LIFT tile
(LOS wall-blocked - no spot-halt), and the host walks to the first far
destination whose click needs no camera re-centring, so the walker stays
on-screen for the whole walk. W2-H3 (F465, D137, D140, D141): vanilla paces
only an on-screen walk (911ca487f UnitWalkBState.cpp:100 `onScreen`, :279
interval 0 off-screen); a re-centred click left the walker off-screen, the
walk ran unpaced and could end before the save request arrived. The HOST
boots with `battlescapeScale` 5 (SCALE_SCREEN): the battlescape fills the
640x400 window instead of 320x200, so a long walk and its walker fit on one
view (D141). Lifted from the
orchestrator's proven R1(d)/R1(f) scratch script (r1d_e72.py) - see that file
for the measured 3-boot evidence.

split_report/assert_split/settle_and_assert are REWRITTEN here (F376, same
function names so test_shared_resume_battle_control.py's `import ... as rc`
keeps working) to the rewrite model: phase/hostSim/localSeat/battleId/
coopSession plus the (name, coop) set, identified BY NAME (never battleInit/
coopTurn/selectable, which the pre-rewrite engine no longer produces).
`bring_up_mixed_battle` (the pre-rewrite Skyranger+terror-site fixture) is
DELETED; S1 builds its own Lightning-roof fixture instead (D121 supersedes
the plain SPEC 19 session bring-up for THIS scenario's mid-walk precondition).

Run:  python tools/coop_test/test_coop_resume_battle_control.py
Exit 0 = pass; 2 = failure (split broken / never resumed / hash mismatch).
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_spec16_pause_on_leave as s16

PORT = "47960"
RESUME_PORT = "47961"
QUICKSAVE = "_quick_.asav"
STATUS_STANDING = 0
STATUS_WALKING = 1


# ---- thin local aliases (kept: still referenced throughout this file) ------

def states(gc):
    return session.states(gc)


def has(gc, name):
    return session.has_state(gc, name)


def top(gc):
    return session.top_state(gc)


def battle(gc):
    return session.battle_state(gc)


# ---- split_report / assert_split / settle_and_assert (F376 rewrite) --------

def split_report(host, client):
    """Per-machine split snapshot, the rewrite model (F376): phase, hostSim,
    localSeat, battleId, coopSession, and the (soldierId, name, coop) set of
    every player-soldier unit. NO term on battleInit/coopTurn/selectable - the
    pre-rewrite signals F376 retired (this engine never sets battleInit and
    isSelectable is plain vanilla; see the old predicates quoted below).

    OLD (pre-rewrite, retired): battleInit==True both, exactly one machine
    coopTurn==2, the two machines' selectable id-sets disjoint.
    NEW (this rewrite): phase=="Active" both, hostSim True/False, localSeat
    0/1, battleId equal non-zero, coopSession True both, the (name, coop) set
    equal on both machines BY NAME.
    """
    out = {}
    for tag, gc in (("host", host), ("client", client)):
        bs = battle(gc)
        auth = bs.get("authority", {})
        units = [u for u in bs.get("units", []) if u.get("isPlayerSoldier")]
        out[tag] = {
            "phase": bs.get("phase"),
            "hostSim": auth.get("hostSim"),
            "localSeat": auth.get("localSeat"),
            "battleId": auth.get("battleId"),
            "coopSession": bs.get("coopSession"),
            "units": sorted((u["soldierId"], u.get("name"), u["coop"]) for u in units),
        }
    return out


def assert_split(host, client, phase, expected):
    """The rewrite-model split invariant (F376).

    `expected`: {name: coop_seat} - the roster this battle was assembled with
    (built from names known at bring-up time, since the guest's BATTLE
    soldierId is only minted once the battle starts - Branch B, F376).

    phase=="Active" both; hostSim True (host) / False (client); localSeat 0
    (host) / 1 (client); battleId equal and non-zero; coopSession True both;
    the (name, coop) set == `expected` on BOTH machines.
    """
    r = split_report(host, client)
    h, c = r["host"], r["client"]
    detail = (
        f"\n  [{phase}] observed:"
        f"\n    host  : phase={h['phase']} hostSim={h['hostSim']} localSeat={h['localSeat']} "
        f"battleId={h['battleId']} coopSession={h['coopSession']}"
        f"\n            units(soldierId,name,coop)={h['units']}"
        f"\n    client: phase={c['phase']} hostSim={c['hostSim']} localSeat={c['localSeat']} "
        f"battleId={c['battleId']} coopSession={c['coopSession']}"
        f"\n            units(soldierId,name,coop)={c['units']}"
    )
    errs = []
    if h["phase"] != "Active" or c["phase"] != "Active":
        errs.append(f"phase not 'Active' on both (host={h['phase']!r} client={c['phase']!r})")
    if h["hostSim"] is not True or c["hostSim"] is not False:
        errs.append(f"authority.hostSim wrong (host={h['hostSim']!r} want True, "
                    f"client={c['hostSim']!r} want False)")
    if h["localSeat"] != 0 or c["localSeat"] != 1:
        errs.append(f"authority.localSeat wrong (host={h['localSeat']!r} want 0, "
                    f"client={c['localSeat']!r} want 1)")
    if not h["battleId"] or h["battleId"] != c["battleId"]:
        errs.append(f"battleId not equal/non-zero (host={h['battleId']!r} client={c['battleId']!r})")
    if not (h["coopSession"] and c["coopSession"]):
        errs.append(f"coopSession not true on both (host={h['coopSession']!r} client={c['coopSession']!r})")
    by_name_h = {(name, coop) for _sid, name, coop in h["units"]}
    by_name_c = {(name, coop) for _sid, name, coop in c["units"]}
    want = set(expected.items())
    if by_name_h != want:
        errs.append(f"host (name,coop) set != expected: expected={sorted(want)} got={sorted(by_name_h)}")
    if by_name_c != want:
        errs.append(f"client (name,coop) set != expected: expected={sorted(want)} got={sorted(by_name_c)}")

    if errs:
        raise AssertionError(f"[{phase}] split BROKEN:" + detail + "\n  errors:\n    - "
                             + "\n    - ".join(errs))
    print(f"PASS [{phase}] split intact:" + detail)
    return r


def settle_and_assert(host, client, phase, expected, timeout=60):
    """Bounded settle (re-poll assert_split - the fields it reads,
    battle_state/event_state, are plain getters valid regardless of either
    machine's UI stack) then assert_split.

    Deliberately does NOT call session.drive_both_to_tactical or press
    anything on either machine's stack: a resumed CLIENT sits on
    COOP_DLG_CLIENT_RESUME_HOLD (68) until `campaign_begun` arrives, and
    CoopState::previous() (the coop_dialog_back lever) treats ANY press on
    that specific dialog code as the issue #91 give-up path - it calls
    disconnectTCP() unconditionally, regardless of the button's visibility.
    Captured via log inspection (WV-D77): drive_both_to_tactical's generic
    "any CoopState top -> coop_dialog_back" clause fired on the client's hold
    mid-settle, producing an immediate onClientDrop/full teardown - a bug in
    THIS helper's prior use of that generic drain, not an engine defect. The
    caller is responsible for the ONE correct click (the HOST's RESUME on its
    own wait dialog, after every read-only assertion here has passed) and for
    then waiting (never clicking) for the client's hold to clear on its own.

    On the unfixed engine after a resume this simply never settles, so the
    bounded wait elapses and the last assert_split failure is raised with the
    observed (broken) state."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            return assert_split(host, client, phase, expected)
        except AssertionError as e:
            last_err = e
            time.sleep(1.0)
    raise last_err


# ---- the E72 (D121) Lightning-roof mid-walk fixture ------------------------

def _sav_unit_block(path, uid):
    """The raw YAML lines for battle unit `uid` in the .sav at `path` - a
    plain text scan (no full YAML parse needed for the two fields this file
    reads: status/position)."""
    if not os.path.exists(path):
        return f"(no file {path})"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    out, grab = [], False
    for ln in lines:
        s = ln.rstrip("\n")
        if s.strip() == f"- id: {uid}":
            grab = True
            out = [s]
            continue
        if grab:
            if s.lstrip().startswith("- id:"):
                break
            out.append(s)
            if len(out) > 45:
                break
    return "\n".join(out) if out else f"(unit id {uid} not found)"


def _sav_status_pos(path, uid):
    blk = _sav_unit_block(path, uid)
    m = re.search(r"^\s*status:\s*(\S+)", blk, re.M)
    status = int(m.group(1)) if m and m.group(1).lstrip("-").isdigit() else None
    mp = re.search(r"^\s*position:\s*\[([^\]]+)\]", blk, re.M)
    pos = tuple(int(v.strip()) for v in mp.group(1).split(",")) if mp else None
    return status, pos, blk


def bring_up_lightning_roof_separate(host, client, port=PORT):
    """The E72/D121 fixture (lifted from the orchestrator's proven r1d_e72.py,
    STAGE_LIGHTNING + guest_seat + STAGE_UFO): a SEPARATE campaign whose host
    base carries a LIGHTNING (not the default Skyranger) seating 3 host
    soldiers + the client's guest, flown to a landed STR_SMALL_SCOUT UFO and
    entered live via coop_mission_start.

    Returns (host_squad, guest_local_id, name_by_squad) where `name_by_squad`
    is {name: 0 for the 3 host soldiers} + {"Guest Zzz": 1} - the (name,coop)
    roster this battle was assembled with, for assert_split's `expected`.
    """
    session.new_campaign(host, client, port=port)

    # ---- (i) give the host base a LIGHTNING; seat 3 host soldiers on it ----
    sc = host.ok({"cmd": "spawn_craft", "type": "STR_LIGHTNING", "weapon": "STR_NONE"})
    lightning_id = sc["craft_id"]

    hb = session._campaign_own_roster_base(host)
    host_base_name = hb["name"]
    name_by_id = {s["id"]: s["name"] for s in hb["soldiers"]}
    rh = sorted(name_by_id)
    for sid in rh:
        host.cmd({"cmd": "craft_assign", "craft_id": lightning_id, "soldier_id": sid, "on": False})
    host_squad = rh[:3]
    for sid in host_squad:
        r = host.cmd({"cmd": "craft_assign", "craft_id": lightning_id, "soldier_id": sid, "on": True})
        assert r.get("seated"), f"host soldier {sid} not seated on Lightning: {r}"

    # ---- the client's guest, transferred + seated on the host LIGHTNING ----
    cb = session._campaign_own_roster_base(client)
    spare = next(s for s in cb["soldiers"] if not s.get("craft"))["name"]
    client.ok({"cmd": "rename_soldier", "name": spare, "newName": "Guest Zzz"})
    tr = client.ok({"cmd": "transfer_to_coop_base", "name": "Guest", "toBase": host_base_name})
    assert tr.get("transferred"), f"guest transfer failed: {tr}"
    client.ok({"cmd": "visit_coop_base", "base": host_base_name})
    client.wait_for("client inside host base",
                    lambda: client.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = client.wait_for(
        "guest visible at host base",
        lambda: (lambda r: r if any("Guest" in s["name"] for s in r["soldiers"]) else None)(
            client.ok({"cmd": "base_report", "coop": True})), timeout=40)
    guest_local_id = next(s for s in rep["soldiers"] if "Guest" in s["name"])["id"]
    lightning_peer = next((c for c in rep["crafts"] if "LIGHTNING" in c["type"]), None)
    assert lightning_peer, f"no LIGHTNING in client base_report crafts: {[c['type'] for c in rep['crafts']]}"
    client.ok({"cmd": "craft_assign", "soldier_id": guest_local_id, "craft_id": lightning_peer["id"],
               "coop": True, "on": True})
    client.ok({"cmd": "open_soldiers", "base": host_base_name})
    client.wait_for("client soldiers screen", lambda: has(client, "SoldiersState") or None, timeout=30)
    client.ok({"cmd": "soldiers_ok"})
    client.ok({"cmd": "leave_base"})
    client.wait_for("client back on geoscape",
                    lambda: (not client.cmd({"cmd": "get_coop"}).get("insideCoopBase")) or None, timeout=60)
    print(f"squad assembled: host soldiers {host_squad} (coop==0) + client guest "
          f"{guest_local_id} 'Guest Zzz' (coop==1), on the Lightning")

    session.drain_host_coop_notice(host)

    # ---- (ii) a landed SMALL-SCOUT UFO; fly the Lightning to it ------------
    b0 = session._campaign_base0(host)
    ufo = host.cmd({"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH",
                    "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID", "trajectory": "P0",
                    "state": "landed", "lon": b0["lon"] + 0.30, "lat": b0["lat"] + 0.10, "hours": 240})
    assert ufo.get("ok") and ufo.get("ufo_id") is not None, f"spawn_ufo failed: {ufo}"
    ufo_id = ufo["ufo_id"]
    host.ok({"cmd": "craft_force", "craft_id": lightning_id, "status": "STR_OUT",
             "lon": b0["lon"] + 0.29, "lat": b0["lat"] + 0.10, "dest": f"ufo:{ufo_id}",
             "fuel": 999999, "lowFuel": False})

    def landing_prompt():
        if has(host, "ConfirmLandingState"):
            return True
        t = states(host)[-1]
        if "CoopState" in t:
            host.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in t:
            host.cmd({"cmd": "dismiss_popup"})
        host.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None

    host.wait_for("host landing prompt", landing_prompt, timeout=120, interval=0.5)
    ms = host.ok({"cmd": "coop_mission_start"})
    assert ms.get("inBattle"), f"coop_mission_start did not enter battle: {ms}"
    host.wait_for("host briefing", lambda: has(host, "BriefingState"), timeout=60, interval=0.5)
    assert session.drive_both_to_tactical(host, client), (
        f"drive_both_to_tactical timed out host={states(host)[-3:]} client={states(client)[-3:]}")
    print("both machines reached the battlescape (live SEPARATE Lightning-roof battle)")

    name_by_squad = {name_by_id[sid]: 0 for sid in host_squad}
    name_by_squad["Guest Zzz"] = 1
    return host_squad, guest_local_id, name_by_squad


def _guest_battle_id(gc, name_substr="Guest"):
    bs = battle(gc)
    units = [u for u in bs["units"] if u.get("isPlayerSoldier") and name_substr in (u.get("name") or "")]
    assert len(units) == 1, f"expected exactly one player unit named {name_substr!r}, got {units}"
    return units[0]["soldierId"]


def _host_squad_battle_units(gc, host_squad):
    bs = battle(gc)
    return [u for u in bs["units"] if u.get("soldierId") in host_squad and not u.get("isOut")]


def stage_alien_and_walk(host, client, walker_id):
    """SPEC 16's proven staging (test_spec16_pause_on_leave.py): park the sole
    alien on the UFO's own ACCESS_LIFT column (LOS wall-blocked - no F394
    spot-halt), then pick a far destination the walker reaches while staying
    on-screen and start a real-click walk. Returns (elevator, dest, lw,
    pending) once the walk is observed >=2-pending mid-flight.

    W2-H3 (F465, D137, D140, D141): vanilla paces a walk only while the walker
    is on screen (911ca487f UnitWalkBState.cpp:100/:279). If the destination is
    off the HOME view, map_tile_click_pos re-centres the camera on it
    (`centered` true), the walker leaves the view and the walk runs unpaced.
    So, with the walker selected, each candidate (length order, then candidate
    order, both unchanged) is probed after HOME, and the FIRST one whose click
    pixel is found without re-centring is the destination; a candidate that
    needs re-centring is skipped. The host's full-window battlescape
    (`battlescapeScale` 5, see main()) keeps the long candidates on the HOME
    view (D141)."""
    aliens = s16._find_alien(host)
    assert aliens, "S1-PRECOND: no living alien on this boot"
    alien = aliens[0]
    walker = next(u for u in battle(host)["units"] if u["id"] == walker_id)

    lx, ly, ds_id, ds_info = s16._locate_ufo_lift_column(host)
    assert lx is not None, f"S1-PRECOND: no rare UFO lift/hull dataset column found: {ds_info}"
    elevator = (lx, ly, 1)
    away = s16._away_direction(walker, (lx, ly))
    session.place_deterministic(
        host, client, [{"lever": "battle_teleport_unit", "unit": alien["id"],
                        "x": lx, "y": ly, "z": 1, "dir": away}],
        what="park alien in UFO")
    print(f"[stage] alien {alien['id']} parked at UFO lift {elevator} (dir={away})")

    occupied = {(u["x"], u["y"], u["z"]) for u in battle(host)["units"] if not u.get("isOut")}
    # HOME centres on the SELECTED unit, so select the walker before probing.
    assert s16._select_by_tab(host, walker_id), "S1-PRECOND: could not TAB-select the walker"
    dest = None
    probed = []
    for length in (10, 12, 8, 6, 5, 4):
        if length * 4 > walker.get("tu", 0):
            continue
        cands = s16._far_destinations(host, walker, elevator, occupied, length=length, want=5)
        for c in cands:
            t = c[1][-1]
            # HOME before every probe: a probe that re-centres moves the camera.
            host.ok({"cmd": "inject_input", "kind": "key", "key": s16.SDLK_HOME})
            time.sleep(0.15)
            pr = host.cmd({"cmd": "map_tile_click_pos", "x": t[0], "y": t[1], "z": t[2]})
            probed.append((length, t, pr.get("centered"), pr.get("verified")))
            if pr.get("verified") and pr.get("centered") is False:
                dest = t
                break
        if dest is not None:
            break
    assert dest is not None, (
        f"S1-PRECOND: no far destination is clickable without re-centring the camera after "
        f"HOME (walker tu={walker.get('tu')}); (length, dest, centered, verified): {probed}")
    print(f"[stage] on-screen dest={dest} length={length}; "
          f"(length, dest, centered, verified) probed: {probed}")

    prev = session.walk_action_id(host)
    assert s16._click_walk(host, dest), "S1-PRECOND: map_tile_click_pos never verified (dest off-view)"
    lw, pending = s16._poll_walk_until_pending(host, prev, min_pending=2, timeout=25)
    if lw is None:
        # F420 (D126, owner): on-timeout diagnostic ONLY. The mid-walk-pending poll
        # gave up (pending stayed < 2 within the window); dump the staging/walk state
        # on BOTH machines before the assertion below fails. Fires ONLY on the failure
        # path; the window is UNCHANGED; this is NOT a second poll and NOT a masking
        # wait - it captures the rare K=2 no-desync stall family (F419) for a future run.
        print("[F420 poll_walk_until_pending TIMEOUT] pending=%s prev_action_id=%s"
              % (pending, prev), flush=True)
        for _nm, _gc in (("host", host), ("client", client)):
            _es = session.event_state(_gc); _lw = _es.get("lastWalk") or {}
            _steps = _lw.get("steps") or []; _planned = _lw.get("plannedLen", 0)
            print("  [%s] ok=%s lastSeqApplied=%s lastSeqEmitted=%s queueDepth=%s "
                  "lastWalk{actionId=%s(prev=%s) active=%s plannedLen=%s steps=%s pending=%s}"
                  % (_nm, _es.get("ok"), _es.get("lastSeqApplied"), _es.get("lastSeqEmitted"),
                     _es.get("queueDepth"), _lw.get("actionId"), prev, _lw.get("active"),
                     _planned, len(_steps), _planned - len(_steps)), flush=True)
    assert lw is not None and pending >= 2, (
        f"S1-PRECOND: walk never reached >=2-pending mid-flight (pending={pending})")
    print(f"[walk] pending={pending} plannedLen={lw.get('plannedLen')} dest={dest}")
    return elevator, dest, lw, pending


def main():
    host_dir = make_user_dir("crbc_host", options={"battleXcomSpeed": 200, "battlescapeScale": 5})
    client_dir = make_user_dir("crbc_client")
    host = GameClient("host", 47861, host_dir)
    client = GameClient("client", 47862, client_dir)
    fail = None
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()

        host_squad, guest_local_id, expected_names = bring_up_lightning_roof_separate(host, client, port=PORT)

        guest_battle_id = _guest_battle_id(host)
        assert _guest_battle_id(client) == guest_battle_id, (
            "guest battle soldierId differs between machines - not a shared live battle")
        expected_seats = {sid: 0 for sid in host_squad}
        expected_seats[guest_battle_id] = 1
        session.assert_t_split(host, client, expected_seats, what="S1 pre-save live split")

        walker_id = _host_squad_battle_units(host, host_squad)[0]["id"]
        walker_before = next(u for u in battle(host)["units"] if u["id"] == walker_id)
        pos_before = (walker_before["x"], walker_before["y"], walker_before["z"])

        elevator, dest, lw, pending = stage_alien_and_walk(host, client, walker_id)

        before_files = set(session.save_files(host_dir))
        deferrals_before = battle(host).get("coopSaveDeferrals")
        r = host.ok({"cmd": "save_game_ui", "type": "quick_battle"})
        # DEFERRAL (D101/M8), read from the game's own record. F448 (owner
        # D136 = (b), WV-D77): the old check had to OBSERVE the latch armed
        # with no file yet, a window that closes when the walk drains. A walk
        # whose remaining steps run off-screen (interval 0) and halt on TU
        # (F450) drains within ~25-200 ms of the request, and each battle_state
        # reply reaches the test ~50 ms after the game handled it (F460), so
        # the first look can land after the deferred write (REGRESSION K=2:
        # deferred -> halt +22 ms -> written +25 ms; the first poll saw the new
        # file with the latch already cleared). The game now records every
        # deferral (`coopSaveDeferrals`, bumped at "[coop-save] deferred until
        # quiescent") and the tick of the deferred write
        # (`coopSaveDeferredWrittenAt`, at "[coop-save] written"), and the
        # host's `lastWalk.endTick` is the tick its walk ended. So: wait for
        # the new file (the F406 bound, unchanged - SaveGameState::think()'s
        # 10-frame warmup still runs first and K=2 slows frames), assert the
        # save was deferred exactly once across the request, and - after the
        # file exists (below) - that the deferred write came no earlier than
        # the walk's end.
        immediate_files = set()
        poll_iters = 0
        t_start = time.time()
        deadline = t_start + 30.0
        while time.time() < deadline:
            poll_iters += 1
            immediate_files = set(session.save_files(host_dir)) - before_files
            if immediate_files:
                break
            time.sleep(0.1)
        elapsed = time.time() - t_start
        deferrals_after = battle(host).get("coopSaveDeferrals")
        assert isinstance(deferrals_before, int) and deferrals_after == deferrals_before + 1, (
            f"M8 VACUITY: the mid-walk save request (pending={pending}) was not deferred "
            f"exactly once - coopSaveDeferrals {deferrals_before} -> {deferrals_after} "
            f"after {poll_iters} poll(s)/{elapsed:.1f}s: {r}")
        print(f"PASS M8 deferral: coopSaveDeferrals {deferrals_before} -> {deferrals_after} "
              f"(walk pending={pending}, new file after {poll_iters} poll(s)/{elapsed:.1f}s)")

        # drain the walk to its own natural end
        for _ in range(150):
            if not (session.event_state(host).get("lastWalk") or {}).get("active"):
                break
            time.sleep(0.2)
        time.sleep(0.5)
        walker_after = next(u for u in battle(host)["units"] if u["id"] == walker_id)
        pos_after = (walker_after["x"], walker_after["y"], walker_after["z"])
        assert pos_after != pos_before, (
            f"VACUITY: the walk never changed the walker's tile (still {pos_before}) - "
            f"the deferral proof is vacuous without a real mid-walk save")

        sp_after = None
        new_files = set()
        for _ in range(50):
            sp_after = battle(host).get("coopSavePending")
            new_files = set(session.save_files(host_dir)) - before_files
            if sp_after is False and new_files:
                break
            time.sleep(0.2)
        assert sp_after is False, f"M8: coopSavePending never cleared after the walk drained: {sp_after}"
        assert len(new_files) == 1, f"M8: expected exactly one new save file, got {sorted(new_files)}"
        savpath = os.path.join(host_dir, next(iter(new_files)))
        print(f"PASS M8: coopSavePending cleared, one new save written -> {savpath}")

        # F448 (D136): the deferred write came no earlier than the walk's end -
        # both are the host's own SDL_GetTicks(), read once the file exists.
        rec = battle(host)
        walk_end = (session.event_state(host).get("lastWalk") or {}).get("endTick")
        written_at = rec.get("coopSaveDeferredWrittenAt")
        assert (isinstance(walk_end, int) and walk_end > 0 and isinstance(written_at, int)
                and written_at >= walk_end), (
            f"M8: the deferred save was not written after the walk ended (deferral broken): "
            f"coopSaveDeferredWrittenAt={written_at} lastWalk.endTick={walk_end} "
            f"coopSaveDeferredAt={rec.get('coopSaveDeferredAt')}")
        print(f"PASS M8 write-after-walk-end: coopSaveDeferredWrittenAt={written_at} >= "
              f"lastWalk.endTick={walk_end} (deferred at {rec.get('coopSaveDeferredAt')})")

        sav_status, sav_pos, sav_block = _sav_status_pos(savpath, walker_id)
        assert sav_status == STATUS_STANDING, (
            f"M8: the written save's walker status={sav_status} (want STANDING={STATUS_STANDING}, "
            f"never WALKING={STATUS_WALKING}) - the file does not hold the post-walk state:\n{sav_block}")
        assert sav_pos == pos_after, (
            f"M8: the written save's walker position={sav_pos} != the live post-drain position "
            f"{pos_after} - the file does not hold the post-walk state:\n{sav_block}")
        print(f"PASS M8: the .sav holds the walker's exact post-drain state "
              f"(status={sav_status}, pos={sav_pos})")

        # ---- record `post` on BOTH machines, right after the drain ---------
        def _snapshot(gc):
            bs = battle(gc)
            es = session.event_state(gc)
            wu = next(u for u in bs["units"] if u["id"] == walker_id)
            return {
                "walker_pos": (wu["x"], wu["y"], wu["z"]),
                "walker_tu": wu["tu"],
                "walker_status": wu["status"],
                "turn": bs.get("turn"),
                "side": bs.get("side"),
                "mapFingerprint": bs.get("mapFingerprint"),
                "unit_ids": sorted(u["id"] for u in bs["units"]),
                "turnMode": es.get("turnMode"),
                "deployment": bs.get("deployment"),
            }

        post_host = _snapshot(host)
        post_client = _snapshot(client)
        assert post_host == post_client, (
            f"pre-quit snapshots differ between machines:\n  host={post_host}\n  client={post_client}")
        post = post_host
        print(f"post-drain snapshot recorded (both machines agree): {post}")

        session.assert_client_zero_disk(client_dir)
        host.shutdown(); client.shutdown()

        # relaunch: host reuses its dir (save present); client gets an EMPTY dir.
        host = GameClient("host", 47863, host_dir)
        client = GameClient("client", 47864, make_user_dir("crbc_client2"))
        host.spawn(); client.spawn()
        host.connect(); client.connect()

        session.resume_campaign_battle(host, client, os.path.basename(savpath), port=RESUME_PORT,
                                       timeout=180)

        for gc, tag in ((host, "host"), (client, "client")):
            bs = battle(gc)
            assert bs.get("inBattle"), f"{tag}: not inBattle after resume: {bs}"
            assert bs.get("phase") == "Active", f"{tag}: phase={bs.get('phase')!r} after resume"
        auth_h = battle(host).get("authority", {})
        auth_c = battle(client).get("authority", {})
        assert auth_h.get("battleId") and auth_h.get("battleId") == auth_c.get("battleId"), (
            f"battleId not equal/non-zero after resume: host={auth_h.get('battleId')} "
            f"client={auth_c.get('battleId')}")

        # battle_ready saveBlob EQUAL (log) + desyncSeen==false both
        logp = os.path.join(host.user_dir, "openxcom.log")
        lines = []
        if os.path.exists(logp):
            with open(logp, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        mism = [ln for ln in lines if "battle_ready saveBlob MISMATCH" in ln]
        eq = [ln for ln in lines if "battle_ready saveBlob EQUAL" in ln]
        assert not mism, f"host log carries a battle_ready saveBlob MISMATCH: {mism[-1]}"
        assert eq, "host log never logged 'battle_ready saveBlob EQUAL' after resume"
        for gc, tag in ((host, "host"), (client, "client")):
            assert not session.event_state(gc).get("desyncSeen"), f"{tag}: desyncSeen after resume"
        print(f"PASS resume hash: {eq[-1].strip()}, desyncSeen false both")

        settle_and_assert(host, client, "after resume", expected_names)

        for gc, tag in ((host, "host"), (client, "client")):
            snap = _snapshot(gc)
            assert snap == post, (
                f"{tag}: post-resume snapshot != pre-quit `post`:\n  post={post}\n  {tag}={snap}")
        # "never replay the walk" (D101): CAPTURED (WV-D77) that lastSeqApplied
        # is NOT 0 after a resume - SS2.W5's battle-entry side-begin reveal
        # restate legitimately sends its own bt_ev(kind=reveal) to re-sync FOV
        # on ANY battle entry (fresh join or resume alike), so lastSeqApplied
        # advances for a reason that has nothing to do with the walk. The
        # walker's snapshot equality (asserted above) already proves the
        # client received the post-drain state directly; this checks the
        # narrower, correct claim - no WALK event for this unit was ever
        # applied on the resumed client.
        client_events = session.event_log(client, tail=100)
        walk_replays = [e for e in client_events if e.get("kind") == "walk"]
        assert not walk_replays, (
            f"client applied walk event(s) after resume (a replay, not a direct "
            f"post-drain snapshot): {walk_replays}")
        assert post["walker_status"] != STATUS_WALKING, "post snapshot itself is WALKING - unsound"
        print(f"PASS resumed state == post-drain snapshot on both machines; "
              f"no walk event replayed on the client")

        # PARALLEL mode (this battle's turnMode, D-22-restored): CAPTURED
        # (WV-D77, cross-checked against test_rw_end_turn_tally.py's own L1 -
        # "parallel emits NOTHING at entry... the raw tally is the reset()
        # default, not a live recompute") that coopEndTurnTally has NO end-
        # turn arm/tally concept until the first real END TURN press - a
        # PARALLEL battle (fresh entry OR resumed, neither ever pressed END
        # TURN here) reads the reset() default {turn:0,side:'',count:0,
        # needed:0,ready:[]}, not {count:0,needed:2} (that shape is
        # TRADITIONAL mode's two-seat entry tally, test_rw_turn_baton.py/
        # test_rw_end_turn_tally.py BOOT C - S3 exercises that mode).
        RESET_TALLY = {"turn": 0, "side": "", "count": 0, "needed": 0, "ready": [], "activeSeat": -1}
        for gc, tag in ((host, "host"), (client, "client")):
            tally = session.event_state(gc).get("coopEndTurnTally", {})
            assert tally == RESET_TALLY, (
                f"{tag}: PARALLEL-mode tally after resume is not the reset() "
                f"default {RESET_TALLY}: {tally}")
        print(f"PASS tally after resume (PARALLEL, reset default, no end-turn activity "
              f"yet): {RESET_TALLY}")

        # host's RESUME click - CoopState(62) -> BattlescapeState, no HostMenu/LobbyMenu
        host.ok({"cmd": "coop_dialog_back"})
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} on BattlescapeState after RESUME",
                        lambda gc=gc: (top(gc) == "BattlescapeState") or None, timeout=60, interval=0.5)
            assert not has(gc, "HostMenu") and not has(gc, "LobbyMenu"), (
                f"{tag}: HostMenu/LobbyMenu still on stack after RESUME: {states(gc)}")
        print("PASS M4: both machines on BattlescapeState after RESUME, no HostMenu/LobbyMenu")

        # E63.3's T-CMD reuse is scoped to the ADMIT + DENY legs only (spec (f)
        # S1 text: "the CLIENT walks one of its own units one step -> action_end
        # both -> assert_hash_clean"; the deny leg is what E63.3 adds). The
        # host click-select-refusal leg (T-CMD leg 3) is SPEC 19's own coverage
        # on a FRESH battle entry, not part of this scenario - host_check=False.
        session.assert_t_cmd(host, client, guest_battle_id, host_squad[0],
                             host_check=False, what="S1 after resume")

        session.assert_client_zero_disk(client.user_dir)
        print("PASS zero-disk: resumed client user dir clean")
        print("ALL SPEC 18 S1 SEPARATE MID-BATTLE RESUME TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()
    finally:
        host.shutdown(); client.shutdown()

    if fail:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
