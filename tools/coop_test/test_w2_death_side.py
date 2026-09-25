"""W2-H5 - test_w2_death_side.py: a dead or a still-unconscious unit stays off
its tile across side changes, on both machines (spec
rewrite/prompts/w2h5_dead_unit_relink.md section (b)4; F809, F817-F824; owner
ruling D138).

At `5f6bcee1d` the host's `side_transition` restates every unit's `pos`, dead
and unconscious ones included (coopEmitSideTransition), and the client's
perUnit applier links every unit that has a `pos` back onto its tile (the
side_transition perUnit `pos` branch, `setTile`). The host's out unit stays
off its tile (vanilla never re-links an out unit, F822), the client's is back
on it, the `synced` bucket (it mixes each unit's onTile) differs, and the
client freezes at the first side_transition after the death (F817-F819).
Three scenarios, TWO boots:

 Boot 1 - the default NEW BATTLE map (the W2-H5 trace fixture R1/R2): roster
 pinned with set_seed SEED_ROSTER on the HOST right before its
 open_new_battle, set_seed SEED_MAP_D right before newbattle_ok, MAP_FP_D
 asserted on both, pin_ai_neutral (the only alien A_ID stays alive and
 inert, so END TURN keeps the battle going). The HOST runs battle_action
 kill_unit_real on DS1_ID, waits for its status DEAD (F823: wait_host_idle
 alone returns while the unit is still COLLAPSING), then for the host to go
 idle with the client caught up; then the same for DS2_ID. Both machines
 press END TURN (the client first) and ONE full side cycle runs back to the
 player side, sampled (below).
  DS1  the host-seat (coop 0) soldier DS1_ID is killed.
  DS2  the client-seat (coop 1) soldier DS2_ID is killed.
 Boot 2 - STR_TERROR_MISSION map seed 1, test_w2_host_combat.py's own boot
 (roster pin, MAP_FP, pin_ai_neutral):
  DS3  that file's C5 stun-rod staging knocks alien A2 unconscious (stun
       120 against health 5: it stays out for the whole cycle), then the
       same sampled full cycle on A2.

THE SAMPLER. On every pass of the cycle loop the test reads, on BOTH
machines, the scenario unit's record (status, isOut, onTile, position,
health, stun) and the unit link of the tile at that position (tile_info
`unit`, Tile::getUnit, -1 for none), with the host's lastSeqEmitted and the
client's lastSeqApplied; a sample is kept whenever anything in it changed.
The EVIDENCE line prints, per host side_transition seq of the cycle, the
first sample of each machine taken at that seq (before the next
side_transition). A poll can miss a client side_transition (the client may
apply a whole backlog between two polls, test_rw_client_nextturn.py's
capture), so what covers EVERY side_transition deterministically is the
client's per-ev hash verify: each side_transition carries the host's `synced`
bucket, which mixes every unit's onTile, and the client verifies it after
applying the ev (CoopHashCheck::verify, the D138 `synced` arm). The samples
are the direct read wherever the poll caught one.

GREEN (each scenario, for its unit U; U's out status = DEAD for DS1/DS2,
UNCONSCIOUS for DS3):
 - before the cycle: U out with its status and onTile false on both
   machines, the tile at its position linking no unit on both;
 - the cycle completes on both machines (player side, turn + 1);
 - the host emitted exactly 3 side_transitions in the cycle and the client's
   event_log holds every one of them (applied, hash-verified);
 - every sample of the cycle, on each machine: U out with its status, onTile
   false, the tile at its position linking no unit;
 - after the cycle: the same on both machines;
 - the common W2 asserts (test_w2_delta_core.common_fails): hash_now full
   ALL buckets equal, desyncSeen false on both, client coopClientBStatePushes
   unchanged and host 0, client deltaEvsApplied increased, deltaUnresolved /
   deltaUnsupported / deltaRemoveMissing / deltaAddExisting 0 on both.

PROBE (the red commit, orchestrator ruling O1 on F830): tile_info gains ONE
read-only field `unit` - the id of the unit the tile links (Tile::getUnit),
-1 for none. Before it no probe read the tile half of BattleUnit::setTile's
two-way link (battle_state `onTile` is the unit half). No product behaviour.

RED (stage H5-red, product untouched, ONE run): DS1/DS2 - the client freezes
with desyncSeen true, bucket `synced`, at the first side_transition after
the deaths, the client's dead units onTile true while the host's are false.
DS3 - expected the same (F824, CANDIDATE), recorded as it happens.

Each scenario prints ONE "EVIDENCE <id>:" line BEFORE its green conditions
are checked, then "PASS <id>" or "FAIL <id>: <message>"; main() runs every
scenario even after an earlier one failed. Every wait is bounded; a wait that
times out is recorded in the EVIDENCE line and fails the scenario. WV-D99 /
WV-D100: one run is the result, no skip path. Exit 0 only when all three
scenarios pass, 2 otherwise (a bring-up failure fails every scenario of that
boot). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_death_side.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_rw_turn_baton import dismiss_next_turn_if_present
from test_w2_delta_core import (probes, diff_buckets, desync_record, short, both, tele_both, tu_both,
                                common_fails, finish, delta_view)
import test_w2_host_combat as hc   # DS3: the terror-map boot and the C5 stun-rod staging

# ----- boot 1: the default NEW BATTLE map (W2-H5 trace fixture R1/R2) -----
SEED_MAP_D = 1
MAP_FP_D = -4.48310638993e+18    # host battle_state.mapFingerprint (default map, SEED_MAP_D, roster pinned)
DS1_ID = 10                      # host-seat (coop 0) soldier "Henryk Kaminski", spawn (14,20,1) (trace R1)
DS2_ID = 8                       # client-seat (coop 1) soldier "Henryk Pawlowski", spawn (14,19,1) (trace R2)
A_ID = 1000000                   # the only alien, pinned; alive through the cycle
PORT_D = "48628"

FACTION_PLAYER = 0
FACTION_HOSTILE = 1
COOP_SEAT_0, COOP_SEAT_1 = 0, 1
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus
STATUS_UNCONSCIOUS = 7
CYCLE_SIDE_TRANSITIONS = 3       # player -> hostile -> neutral -> player
CYCLE_TIMEOUT = 60
FROZEN_HOLD = 3.0                # the host is back on the player side and the client latched desyncSeen
LOG_TAIL = 256                   # CoopEventLog::kCapacity
UNIT_KEYS = ("status", "isOut", "onTile", "x", "y", "z", "health", "stun")


# ===================== probes =====================


def top(gc):
    return session.top_state(gc)


def tile_link(gc, u):
    """The unit id the tile at unit record `u`'s position links (tile_info
    `unit`: Tile::getUnit, -1 for none)."""
    r = gc.cmd({"cmd": "tile_info", "x": u.get("x"), "y": u.get("y"), "z": u.get("z")})
    if not r.get("ok"):
        return f"tile_info failed: {r.get('error')}"
    return r.get("unit", "tile_info has no `unit` field")


def recs(gc, bs, uids):
    """{uid: {UNIT_KEYS..., tileUnit}} from battle_state `bs` of machine `gc`."""
    ub = session.units_by_id(bs)
    out = {}
    for uid in uids:
        u = ub.get(uid)
        if not u:
            out[uid] = None
            continue
        v = {k: u.get(k) for k in UNIT_KEYS}
        v["tileUnit"] = tile_link(gc, u)
        out[uid] = v
    return out


def evs_since(gc, seq0):
    r = gc.cmd({"cmd": "event_log", "tail": LOG_TAIL})
    assert r.get("ok"), f"event_log failed on {gc.name}: {r}"
    return [(e.get("seq"), e.get("kind"), e.get("actionId")) for e in r.get("events", [])
            if (e.get("seq") or 0) > seq0]


def out_fails(name, uid, u, status, what):
    """U out with `status`, onTile false, the tile at its position linking no unit."""
    if not u:
        return [f"{what}: {name} has no unit {uid}"]
    fails = []
    if u.get("status") != status or u.get("isOut") is not True or u.get("onTile") is not False:
        fails.append(f"{what}: {name} unit {uid} status={u.get('status')} isOut={u.get('isOut')} "
                     f"onTile={u.get('onTile')} (want status {status}, isOut true, onTile false)")
    if u.get("tileUnit") != -1:
        fails.append(f"{what}: {name} tile ({u.get('x')},{u.get('y')},{u.get('z')}) links unit "
                     f"{u.get('tileUnit')} (want none, -1)")
    return fails


# ===================== driving =====================


def host_out_done(host, uid, status):
    """HOST only: `uid` has `status` and no BState is queued or running."""
    bs = battle_state(host)
    u = session.units_by_id(bs).get(uid) or {}
    return (u.get("status") == status and bs.get("pendingStates") == 0 and not bs.get("isBusy")) or None


def settle_on_battlescape(gc, timeout=20):
    def ready():
        dismiss_next_turn_if_present(gc)
        bs = battle_state(gc)
        return (top(gc) == "BattlescapeState" and bs.get("panicHandled")
                and bs.get("pendingStates") == 0) or None
    gc.wait_for(f"{gc.name} on BattlescapeState after the cycle", ready, timeout=timeout)


def cycle_sampled(host, client, uids, notes):
    """Both machines press END TURN (the client first; the host presses once it
    paints END TURN 1/2), then ONE full side cycle. Every pass closes the
    host's NextTurnState (the real close() path), dismisses an Infobox on the
    host, closes the client's NextTurnState, and reads both machines' records
    of `uids` (recs) with the host's lastSeqEmitted and the client's
    lastSeqApplied; a sample is kept whenever anything in it changed. Ends
    when both machines are back on the player side at turn0 + 1 ("cycled"),
    when the host is back and the client has held desyncSeen for FROZEN_HOLD
    seconds ("frozen"), or at CYCLE_TIMEOUT ("timeout"). After "cycled" both
    settle on BattlescapeState and the host goes idle with the client caught
    up. Returns (turn0, outcome, samples)."""
    turn0 = battle_state(host).get("turn")
    samples = []
    outcome = "not started"
    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None, timeout=20)
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        t_press = time.time()
        deadline = t_press + CYCLE_TIMEOUT
        last_key = None
        frozen_since = None
        outcome = "timeout"
        while time.time() < deadline:
            lw = host.cmd({"cmd": "list_widgets"}).get("state", "")
            if "NextTurnState" in lw:
                r = host.cmd({"cmd": "close_nextturn"})
                assert r.get("ok"), f"close_nextturn failed on the host: {r}"
            if "Infobox" in lw:
                host.cmd({"cmd": "dismiss_popup"})
            dismiss_next_turn_if_present(client)
            eh, ec = event_state(host), event_state(client)
            hs, cs = battle_state(host), battle_state(client)
            s = {"hSeq": eh.get("lastSeqEmitted"), "cSeq": ec.get("lastSeqApplied"),
                 "hTS": (hs.get("turn"), hs.get("side")), "cTS": (cs.get("turn"), cs.get("side")),
                 "cDesync": ec.get("desyncSeen"), "host": recs(host, hs, uids), "client": recs(client, cs, uids)}
            key = json.dumps(s, sort_keys=True, default=str)
            if key != last_key:
                last_key = key
                s["t"] = round(time.time() - t_press, 2)
                samples.append(s)
            host_back = hs.get("side") == FACTION_PLAYER and (hs.get("turn") or -1) >= turn0 + 1
            client_back = cs.get("side") == FACTION_PLAYER and (cs.get("turn") or -1) >= turn0 + 1
            if host_back and client_back:
                outcome = "cycled"
                break
            if host_back and ec.get("desyncSeen"):
                frozen_since = frozen_since or time.time()
                if time.time() - frozen_since >= FROZEN_HOLD:
                    outcome = "frozen"
                    break
            time.sleep(0.03)
        if outcome == "cycled":
            settle_on_battlescape(host)
            settle_on_battlescape(client)
            session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"end-turn cycle: {short(e)}")
    if outcome != "cycled":
        hs, cs = battle_state(host), battle_state(client)
        notes.append(f"cycle outcome {outcome}: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')}) (want both on the player side at turn "
                     f"{(turn0 or 0) + 1})")
    return turn0, outcome, samples


def per_transition(samples, st_seqs, uid):
    """{seq: {host, client}}: for each host side_transition seq, the first
    sample of each machine taken at that seq (host lastSeqEmitted / client
    lastSeqApplied in [seq, next side_transition seq)); "unsampled" when the
    poll caught none."""
    table = {}
    for i, sq in enumerate(st_seqs):
        nxt = st_seqs[i + 1] if i + 1 < len(st_seqs) else None

        def inside(v):
            return v is not None and v >= sq and (nxt is None or v < nxt)
        h = next((x["host"].get(uid) for x in samples if inside(x["hSeq"])), "unsampled")
        c = next((x["client"].get(uid) for x in samples if inside(x["cSeq"])), "unsampled")
        table[sq] = {"host": h, "client": c}
    return table


def sample_fails(samples, uid, status):
    """Every sample of the cycle, on each machine: U out with `status`, onTile
    false, its tile linking no unit. One message per machine, listing the
    offending samples as (host seq, client seq, record)."""
    fails = []
    for name in ("host", "client"):
        bad = []
        for x in samples:
            u = x[name].get(uid)
            if out_fails(name, uid, u, status, "sample"):
                bad.append((x["hSeq"], x["cSeq"], u))
        if bad:
            fails.append(f"{name} unit {uid} not off its tile in {len(bad)} of {len(samples)} cycle samples, first "
                         f"(host seq, client seq, record)={bad[:3]} (want status {status}, onTile false, tile "
                         f"link -1 in every sample)")
    return fails


# ===================== scenario body (shared) =====================


def run_cycle_and_collect(host, client, uids, before, notes):
    """The sampled cycle plus everything a verdict reads afterwards."""
    seq1 = event_state(host).get("lastSeqEmitted") or 0
    pre = {"host": recs(host, battle_state(host), uids), "client": recs(client, battle_state(client), uids)}
    pre_tops = (top(host), top(client))
    pre_diff = diff_buckets(host, client)
    turn0, outcome, samples = cycle_sampled(host, client, uids, notes)
    hev, cev = evs_since(host, seq1), evs_since(client, seq1)
    st_host = [e[0] for e in hev if e[1] == "side_transition"]
    st_client = [e[0] for e in cev if e[1] == "side_transition"]
    after = {"host": recs(host, battle_state(host), uids), "client": recs(client, battle_state(client), uids)}
    ph, pc = probes(host), probes(client)
    return {"before": before, "seq1": seq1, "pre": pre, "preTops": pre_tops, "preDiff": pre_diff,
            "turn0": turn0, "outcome": outcome, "samples": samples, "hev": hev, "cev": cev,
            "stHost": st_host, "stClient": st_client, "after": after, "ph": ph, "pc": pc,
            "desyncClient": desync_record(client, pc["desyncSeen"]),
            "desyncHost": desync_record(host, ph["desyncSeen"]),
            "endDiff": diff_buckets(host, client), "notes": notes}


def verdict(sid, uid, status, host, client, c, staging):
    """Print the scenario's EVIDENCE line, then assert its GREEN."""
    table = per_transition(c["samples"], c["stHost"], uid)
    print(f"EVIDENCE {sid}: unit {uid} staging={staging}; before the cycle host={c['pre']['host'].get(uid)} "
          f"client={c['pre']['client'].get(uid)} tops={c['preTops']} diff={c['preDiff']}; cycle turn {c['turn0']} "
          f"outcome={c['outcome']} samples={len(c['samples'])}; host side_transitions={c['stHost']} client applied "
          f"side_transitions={c['stClient']}; per side_transition (seq: host, client)={table}; client desyncSeen="
          f"{c['pc']['desyncSeen']} desync={c['desyncClient']} host desyncSeen={c['ph']['desyncSeen']} "
          f"desync={c['desyncHost']}; host evs since seq {c['seq1']}={c['hev']} client evs={c['cev']}; after the "
          f"cycle host={c['after']['host'].get(uid)} client={c['after']['client'].get(uid)} diffAfter="
          f"{c['endDiff']}; host {delta_view(c['before']['host'])}->{delta_view(c['ph'])}; client "
          f"{delta_view(c['before']['client'])}->{delta_view(c['pc'])}; notes={c['notes']}", flush=True)
    fails = list(c["notes"])
    fails += staging.get("fails", [])
    for name in ("host", "client"):
        fails += out_fails(name, uid, c["pre"][name].get(uid), status, "before the cycle")
    if len(c["stHost"]) != CYCLE_SIDE_TRANSITIONS:
        fails.append(f"host side_transitions in the cycle {c['stHost']} (want exactly {CYCLE_SIDE_TRANSITIONS})")
    missing = [s for s in c["stHost"] if s not in c["stClient"]]
    if missing:
        fails.append(f"client event_log lacks host side_transition seq(s) {missing} (client applied "
                     f"{c['stClient']}; want every one applied and hash-verified)")
    fails += sample_fails(c["samples"], uid, status)
    for name in ("host", "client"):
        fails += out_fails(name, uid, c["after"][name].get(uid), status, "after the cycle")
    fails += common_fails(host, client, c["before"], {}, sid)
    finish(fails)


# ===================== boot 1: DS1 + DS2 =====================


def boot_default(host, client):
    hc.bring_up_lobby_roster_pinned(host, client, PORT_D)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP_D}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP_D and cs.get("mapFingerprint") == MAP_FP_D, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP_D={MAP_FP_D!r} (default map, SEED_MAP_D {SEED_MAP_D})")
    pinned = pin_ai_neutral(host, client, tag="w2h5-ds12")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    ub = session.units_by_id(hs)
    for uid, seat in ((DS1_ID, COOP_SEAT_0), (DS2_ID, COOP_SEAT_1)):
        u = ub.get(uid) or {}
        assert (u.get("faction") == FACTION_PLAYER and u.get("coop") == seat and not u.get("isOut")
                and u.get("onTile")), (f"unit {uid} at bring-up: faction={u.get('faction')} coop={u.get('coop')} "
                                       f"isOut={u.get('isOut')} onTile={u.get('onTile')} (want a live player "
                                       f"soldier of seat {seat} on its tile)")
    a = ub.get(A_ID) or {}
    assert a.get("faction") == FACTION_HOSTILE and not a.get("isOut"), f"alien {A_ID} at bring-up: {a}"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2h5-ds] boot 1 ok: default map MAP_FP={MAP_FP_D!r} turn={hs.get('turn')} seated="
          f"{seated.get('soldierIds')} pinned={pinned} DS1 {DS1_ID}={ub[DS1_ID].get('name')} "
          f"({ub[DS1_ID].get('x')},{ub[DS1_ID].get('y')},{ub[DS1_ID].get('z')}) DS2 {DS2_ID}="
          f"{ub[DS2_ID].get('name')} ({ub[DS2_ID].get('x')},{ub[DS2_ID].get('y')},{ub[DS2_ID].get('z')})",
          flush=True)


def kill_real(host, client, uid, notes):
    """HOST kill_unit_real on `uid`, then its status DEAD with no BState (F823),
    then the host idle with the client caught up. Returns the lever's answer."""
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
    try:
        host.wait_for(f"host unit {uid} DEAD (status {STATUS_DEAD}), no BState",
                      lambda: host_out_done(host, uid, STATUS_DEAD), timeout=30)
    except Exception as e:
        notes.append(f"host kill chain of {uid}: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the kill of {uid}: {short(e)}")
    return r


def ds12_stage(host, client):
    notes = []
    before = {"host": probes(host), "client": probes(client)}
    k1 = kill_real(host, client, DS1_ID, notes)
    k2 = kill_real(host, client, DS2_ID, notes)
    staging = {}
    for sid, uid, k in (("DS1", DS1_ID, k1), ("DS2", DS2_ID, k2)):
        f = []
        if not k.get("ok") or k.get("killed") != [uid]:
            f.append(f"kill_unit_real answered {k} (want ok, killed [{uid}])")
        staging[sid] = {"kill": k, "fails": f}
    c = run_cycle_and_collect(host, client, (DS1_ID, DS2_ID), before, notes)
    return c, staging


# ===================== boot 2: DS3 =====================


def ds3_stage(host, client):
    notes = []
    before = {"host": probes(host), "client": probes(client)}
    f = []
    g = both(host, client, {"cmd": "battle_give", "unit": hc.H_ID, "item": "STR_STUN_ROD", "clear_hands": True},
             ("weaponId", "ammoId"))
    tele_both(host, client, hc.H_ID, hc.C5_H_TILE, hc.C5_H_DIR)
    tele_both(host, client, hc.A2_ID, hc.C5_A2_TILE, hc.C5_A2_DIR)
    both(host, client, {"cmd": "battle_set_unit_state", "unit": hc.A2_ID, "health": hc.C5_A2_HEALTH},
         ("health", "stun", "status"))
    tu_both(host, client, hc.H_ID)
    staged_diff = diff_buckets(host, client)
    if staged_diff:
        f.append(f"buckets differ after the staging: {staged_diff} (want none)")
    cursor0 = None
    try:
        cursor0 = hc.open_hand_menu_host(host)
        host.ok({"cmd": "set_seed", "seed": hc.SEED_C5})
        hc.press(host, hc.KEY_ITEM4)
        host.wait_for("host stun chain finished (A2 UNCONSCIOUS, no BState)",
                      lambda: hc.host_chain_done(host, hc.A2_ID, STATUS_UNCONSCIOUS), timeout=30)
    except Exception as e:
        notes.append(f"host stun: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the stun: {short(e)}")
    c = run_cycle_and_collect(host, client, (hc.A2_ID,), before, notes)
    staging = {"rod": g.get("weaponId"), "H": (hc.H_ID, hc.C5_H_TILE, hc.C5_H_DIR),
               "A2": (hc.A2_ID, hc.C5_A2_TILE, hc.C5_A2_DIR, hc.C5_A2_HEALTH), "cursorType": cursor0,
               "stagedDiff": staged_diff, "fails": f}
    return c, staging


# ===================== main =====================


def run_boot(tag, boot_fn, stage_fn, scenarios, results):
    """One boot: bring-up, the stage, then each scenario's verdict. A failure
    before the verdicts fails every scenario of this boot."""
    host = GameClient("host", 49860, make_user_dir(f"w2h5_death_side_{tag}_host"))
    client = GameClient("client", 49861, make_user_dir(f"w2h5_death_side_{tag}_client"))
    try:
        try:
            boot_fn(host, client)
            c, staging = stage_fn(host, client)
        except Exception as e:
            for sid, _uid, _status in scenarios:
                results[sid] = False
                print(f"FAIL {sid}: boot/stage {type(e).__name__}: {e}", flush=True)
            return
        for sid, uid, status in scenarios:
            try:
                verdict(sid, uid, status, host, client, c, staging.get(sid, staging))
                results[sid] = True
                print(f"PASS {sid}", flush=True)
            except Exception as e:
                results[sid] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {sid}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h5-ds] shutdown {gc.name}: {short(e)}", flush=True)


def main():
    t0 = time.time()
    results = {}
    order = ["DS1", "DS2", "DS3"]
    run_boot("ds12", boot_default, ds12_stage,
             (("DS1", DS1_ID, STATUS_DEAD), ("DS2", DS2_ID, STATUS_DEAD)), results)
    run_boot("ds3", hc.boot, ds3_stage, (("DS3", hc.A2_ID, STATUS_UNCONSCIOUS),), results)
    passed = [n for n in order if results.get(n)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_death_side: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
