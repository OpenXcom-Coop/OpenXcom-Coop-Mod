"""W2-P2 S-B - test_w2_delta_items.py: every host event carries the item state
that changed since the previous event, including items the host created and
items it destroyed (spec rewrite/prompts/w2p2_delta_core.md section (f)
"test_w2_delta_items.py (S-B)", sections (b)1, (b)7, (b)8, (b)16; orchestrator
rulings Q2 = (a) and Q4 = (b), amendment A1; owner ruling D128 = (b)).

After stage S-A the delta carries units, tiles, nodes and the battle counters,
but no item: a corpse the host creates, a weapon a dead unit drops and a
grenade that blows itself and two clips away exist (or vanish) on the host
only, and the client freezes with the desync banner on the `items` bucket at
the next hash check. After stage S-B the delta carries `items`, `itemsAdded`
(the host's own BattleItem record, materialized on the client through the load
path with the host's id) and `itemsRemoved`. Two scenarios, ONE boot, in this
order:

  SB2  removal. A primed fuse-0 grenade and two rifle clips are dropped on
       SB2_GRENADE_TILE / SB2_ITEM_TILE (the same tile) with battle_drop on
       BOTH machines (ids asserted equal). Both machines press END TURN and the
       full side cycle runs back to the player side. At the end of the player
       turn the host detonates the grenade: the grenade is removed and HE 50 on
       the clips' own tile destroys both clips (TASK 0a precalc). RED (commit
       S-B.1, no item delta): the client freezes at the side_transition on
       `items` (grenade and clips destroyed on the host only). GREEN: common
       asserts at player turn N+1; the grenade id and >= 1 clip id absent on
       both; some host emission in the cycle had lastDelta.itemsRemoved >= 2.
  SB1  kill via lever. The host runs battle_action kill_unit_real on A (host
       only: overkill damage + checkForCasualties -> UnitDieBState chain ->
       the S-A `sync` flush). On the host A's inventory drops to its tile and
       a corpse item is created with the next host id. RED: the client
       freezes on `items` (the corpse and the dropped weapon exist on the host
       only). GREEN: common asserts; battle_items equal on both, including the
       corpse (type A_CORPSE, unitLink A, same id, same tile) and A's weapon
       (owner -1, on a tile, same tile, previousOwner A); A status DEAD and
       onTile false on both; >= 1 alien's morale lower than before on the host
       and equal on both; host lastDelta (from this kill) has itemsAdded >= 1,
       items >= 1, units >= 1 and battle key itemIdCtr.

WHY SB2 RUNS FIRST. The default map deploys ONE alien (A, amendment A1.3).
SB1 kills it, and a later END TURN with no live alien ends the battle
(BattlescapeGame::endTurn pushes NextTurnState with battleComplete, and
NextTurnState::close() calls finishBattle), so SB2's cycle can only run while
A is alive. At the red commit SB2 freezes the client, so SB1 runs on a frozen
client there (the S-A precedent, finding F495); the EVIDENCE line records the
client's desync latch from before the kill. At the green commit nothing freezes.

Common asserts (spec (f), after the action settles with wait_host_idle):
hash_now {full:true} - ALL buckets EQUAL on both machines (never a hard-coded
count); desyncSeen false on both; client coopClientBStatePushes unchanged and
host 0; client deltaEvsApplied increased; deltaUnresolved, deltaUnsupported,
deltaRemoveMissing and deltaAddExisting all 0 on both; the host's lastDelta
has the scenario's minimum class counts.

FIXTURE (deterministic, never searched here). The classic parallel skirmish
bring-up (raw.bring_up_lobby + session.drive_to_battlescape, seat_count=2),
pinned with set_seed SEED_MAP right before newbattle_ok, asserted against the
baked MAP_FP, then session.pin_ai_neutral (A cannot act). Every item a lever
creates is created on BOTH machines in the same order and the ids are
asserted equal. The constants come from the W2-P2 TASK 0a precalc (round 1,
default NEW BATTLE map, SEED_MAP 1): A = 1000000 at its spawn with the plasma
pistol A_WEAPON in its right hand; SB2 tile (7,3,0).

RED-THEN-GREEN (spec (d), Q4 = b). Commit S-B.1 (this file and the
battle_items probe fields previousOwner / unitLink / slotX / slotY /
fuseEnabled - no product behaviour) is run ONCE and every scenario must FAIL
with its named red evidence. Commit S-B.2 (the item delta) is run ONCE and
every scenario must PASS. Each scenario prints ONE "EVIDENCE <id>:" line with
both machines' fields BEFORE its green conditions are checked; main() runs
every scenario even after an earlier one failed and prints "PASS <id>" /
"FAIL <id>: <message>". Every wait is bounded; a wait that times out is
recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when both scenarios pass, 2 otherwise
(a bring-up failure is also 2).

Run:  python tools/coop_test/test_w2_delta_items.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_turn_baton import dismiss_next_turn_if_present
from test_w2_delta_core import (probes, diff_buckets, desync_record, short, both, settle_on_battlescape,
                                common_fails, finish, delta_view)

# ----- common (every W2-P2 test file; TASK 0a round 1, default map) -----
SEED_MAP = 1
MAP_FP = -4.48310638993e+18      # host battle_state.mapFingerprint on SEED_MAP 1
H_ID = 10                        # first host-seat (coop 0) soldier; stats/loadout random per boot (F488)
A_ID = 1000000                   # the only alien: Sectoid Soldier, spawn (27,12,0) dir 5, health 30
A_ITEMS = {56: ("STR_PLASMA_PISTOL", "STR_RIGHT_HAND"), 58: ("STR_PLASMA_PISTOL_CLIP", "STR_BELT"),
           59: ("STR_MIND_PROBE", "STR_BACK_PACK")}   # 60 items at start: first lever-minted id = 60
A_CORPSE = "STR_SECTOID_CORPSE"
RHAND_NTH = 25                   # click_widget nth of the right-hand box (RHAND_RECT centre base (296,172))
KEY_ITEM1, KEY_ITEM2, KEY_ITEM4, KEY_FUSE_0 = 49, 50, 52, 48   # PRIME/AIMED, SNAP, STUN (BA_HIT), fuse 0
TU_MAX = 255                     # battle_set_unit_state / battle_fire tu: clamped to the unit's max TU

# ----- test_w2_delta_items.py (S-B) -----
# SB1: kill_unit_real on A_ID at its spawn (27,12,0); corpse type A_CORPSE, dropped weapon STR_PLASMA_PISTOL (id 56).
A_WEAPON = 56                   # A_ITEMS: A's right-hand plasma pistol
SB2_GRENADE_TILE = (7, 3, 0)    # CULTIVAT #2, open, > 20 tiles from A
SB2_ITEM_TILE = (7, 3, 0)       # same tile: HE 50 at l=0 rolls 25..75 > clip armor 20 -> both clips always destroyed

PORT = "48623"
FACTION_PLAYER = 0
FACTION_HOSTILE = 1
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus
ITEM_KEYS = ("id", "type", "owner", "slot", "slotX", "slotY", "isAmmo", "qty", "onTile", "tx", "ty", "tz",
             "fuse", "fuseEnabled", "previousOwner", "unitLink", "ammo")


# ===================== small probes =====================


def top(gc):
    return session.top_state(gc)


def units(gc):
    return session.units_by_id(battle_state(gc))


def items_by_id(gc):
    """battle_items as {id: {field: value}} (every BattleItem this machine holds)."""
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed on {gc.name}: {r}"
    return {it["id"]: {k: it.get(k) for k in ITEM_KEYS} for it in r.get("items", [])}


def items_pair(ih, ic, ids):
    return {i: {"host": ih.get(i), "client": ic.get(i)} for i in ids}


def item_diff(ih, ic):
    """Host vs client item sets: ids on one machine only, and ids whose fields differ."""
    only_h = sorted(set(ih) - set(ic))
    only_c = sorted(set(ic) - set(ih))
    differ = {i: {k: [ih[i].get(k), ic[i].get(k)] for k in ITEM_KEYS if ih[i].get(k) != ic[i].get(k)}
              for i in sorted(set(ih) & set(ic)) if ih[i] != ic[i]}
    return {"hostOnly": {i: ih[i] for i in only_h}, "clientOnly": {i: ic[i] for i in only_c}, "differ": differ}


def tile_of(it):
    return (it["tx"], it["ty"], it["tz"]) if it and it.get("onTile") else None


def unit_view(u):
    if not u:
        return None
    return {k: u.get(k) for k in ("faction", "status", "health", "stun", "morale", "isOut", "onTile",
                                  "x", "y", "z", "unitFire")}


def host_evs_since(host, seq0):
    r = host.cmd({"cmd": "event_log", "tail": 200})
    return [(e.get("seq"), e.get("kind"), e.get("actionId")) for e in r.get("events", [])
            if (e.get("seq") or 0) > seq0]


# ===================== driving =====================


def end_turn_cycle_sampled(host, client, notes, timeout=60):
    """Both machines press END TURN (the client first; the host presses once it
    paints END TURN 1/2), then the full side cycle back to the player side on
    both, then both settle on BattlescapeState and the host goes idle with the
    client caught up (session.wait_host_idle).

    The host's `lastDelta` probe holds only the LAST non-empty delta it
    emitted, and a cycle emits several. So every loop pass reads it and keeps
    each distinct summary (by seq): "some emission in the cycle" is a summary
    this loop saw. The host stops at a NextTurnState after a non-neutral side
    change until it is closed; the pass reads lastDelta BEFORE closing it, so
    the summary of the transition that led there is read while the host is
    held. Every wait is bounded; a timeout is recorded in `notes` (evidence),
    never repeated. Returns (turn0, [summaries in seq order])."""
    turn0 = battle_state(host).get("turn")
    seen = {}

    def sample():
        ld = event_state(host).get("lastDelta")
        if isinstance(ld, dict) and ld.get("seq") is not None:
            seen.setdefault(ld["seq"], ld)

    try:
        client.ok({"cmd": "battle_action", "action": "end_turn_button"})
        host.wait_for("host paints END TURN 1/2 after the client's press",
                      lambda: battle_state(host).get("coopEndTurnText") == "END TURN 1/2" or None,
                      timeout=20)
        sample()
        host.ok({"cmd": "battle_action", "action": "end_turn_button"})
        deadline = time.time() + timeout
        cycled = False
        hs, cs = {}, {}
        while time.time() < deadline:
            held = "NextTurnState" in host.cmd({"cmd": "list_widgets"}).get("state", "")
            sample()
            if held:
                r = host.cmd({"cmd": "close_nextturn"})
                assert r.get("ok"), f"close_nextturn failed on the host: {r}"
            dismiss_next_turn_if_present(client)
            hs, cs = battle_state(host), battle_state(client)
            if (hs.get("side") == FACTION_PLAYER and hs.get("turn", -1) >= turn0 + 1
                    and cs.get("side") == FACTION_PLAYER and cs.get("turn", -1) >= turn0 + 1):
                cycled = True
                break
            time.sleep(0.05)
        sample()
        if not cycled:
            raise TimeoutError(f"full cycle did not complete within {timeout}s - host=({hs.get('turn')},"
                               f"{hs.get('side')}) client=({cs.get('turn')},{cs.get('side')})")
        settle_on_battlescape(host)
        settle_on_battlescape(client)
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"end-turn cycle: {short(e)}")
    sample()
    return turn0, [seen[k] for k in sorted(seen)]


def host_chain_done(host):
    """HOST only: A is DEAD, no BState is queued or running, BattlescapeState on top."""
    bs = battle_state(host)
    a = session.units_by_id(bs).get(A_ID) or {}
    return (a.get("status") == STATUS_DEAD and bs.get("pendingStates") == 0 and not bs.get("isBusy")
            and top(host) == "BattlescapeState") or None


# ===================== scenarios =====================


def sb2_removal(host, client, ctx):
    notes = []
    before = {"host": probes(host), "client": probes(client)}
    g = both(host, client, {"cmd": "battle_drop", "x": SB2_GRENADE_TILE[0], "y": SB2_GRENADE_TILE[1],
                            "z": SB2_GRENADE_TILE[2], "item": "STR_GRENADE", "prime": True, "fuse": 0},
             ("ids",))["ids"]
    c = both(host, client, {"cmd": "battle_drop", "x": SB2_ITEM_TILE[0], "y": SB2_ITEM_TILE[1],
                            "z": SB2_ITEM_TILE[2], "item": "STR_RIFLE_CLIP", "count": 2}, ("ids",))["ids"]
    ih0, ic0 = items_by_id(host), items_by_id(client)
    staged = items_pair(ih0, ic0, g + c)
    staged_diff = diff_buckets(host, client)
    turn0, seen = end_turn_cycle_sampled(host, client, notes)
    hs, cs = battle_state(host), battle_state(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    seq0 = before["host"]["lastSeqEmitted"] or 0
    cycle = [s for s in seen if (s.get("seq") or 0) > seq0]
    removed = [s for s in cycle if (s.get("itemsRemoved") or 0) >= 2]
    present = {i: {"host": i in ih, "client": i in ic} for i in g + c}
    print(f"EVIDENCE SB2: grenade={g} clips={c} on {SB2_GRENADE_TILE}/{SB2_ITEM_TILE} staged={staged} "
          f"stagedDiff={staged_diff}; turn {turn0} -> host=({hs.get('turn')},{hs.get('side')}) "
          f"client=({cs.get('turn')},{cs.get('side')}); present after the cycle={present}; "
          f"client desyncSeen={pc['desyncSeen']} desync={dsc} host desyncSeen={ph['desyncSeen']}; "
          f"diffAfterCycle={end_diff}; host lastDelta summaries in the cycle="
          f"{[(s.get('seq'), s.get('kind'), s.get('itemsRemoved'), s.get('items'), s.get('itemsAdded')) for s in cycle]} "
          f"(seq, kind, itemsRemoved, items, itemsAdded); host lastDelta={ph['lastDelta']} "
          f"client lastDelta={pc['lastDelta']}; host {delta_view(before['host'])}->{delta_view(ph)}; "
          f"client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}", flush=True)
    fails = list(notes)
    if len(g) != 1 or len(c) != 2:
        fails.append(f"staging minted grenade={g} clips={c} (want 1 and 2 ids)")
    for i in g:
        for name, it in (("host", ih0.get(i)), ("client", ic0.get(i))):
            if not it or it.get("fuse") != 0 or it.get("fuseEnabled") is not True:
                fails.append(f"{name} staged grenade {i}={it} (want fuse 0, fuseEnabled true)")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    for i in g:
        if i in ih or i in ic:
            fails.append(f"grenade {i} present after the cycle host={i in ih} client={i in ic} "
                         f"(want absent on both)")
    gone = [i for i in c if i not in ih and i not in ic]
    if not gone:
        fails.append(f"no clip absent on both after the cycle: {present} (want >= 1 of {c})")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER,
                                                                             turn0 + 1, FACTION_PLAYER):
        fails.append(f"not on player turn {turn0 + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')})")
    fails += common_fails(host, client, before, {}, "SB2")
    if not removed:
        fails.append(f"no host emission in the cycle had lastDelta.itemsRemoved >= 2 (summaries seen: "
                     f"{cycle})")
    finish(fails)


def sb1_kill(host, client, ctx):
    notes = []
    uh0, uc0 = units(host), units(client)
    aliens = sorted(uid for uid, u in uh0.items() if u.get("faction") == FACTION_HOSTILE)
    morale0 = {uid: uh0[uid].get("morale") for uid in aliens}
    ih0, ic0 = items_by_id(host), items_by_id(client)
    w0 = {"host": ih0.get(A_WEAPON), "client": ic0.get(A_WEAPON)}
    before = {"host": probes(host), "client": probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": A_ID})
    try:
        host.wait_for("host kill chain finished (A DEAD, no BState)", lambda: host_chain_done(host),
                      timeout=30)
    except Exception as e:
        notes.append(f"host kill chain: {short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the kill: {short(e)}")
    uh, uc = units(host), units(client)
    ih, ic = items_by_id(host), items_by_id(client)
    ph, pc = probes(host), probes(client)
    dsc = desync_record(client, pc["desyncSeen"])
    end_diff = diff_buckets(host, client)
    corpses = {"host": [i for i in ih.values() if i["type"] == A_CORPSE],
               "client": [i for i in ic.values() if i["type"] == A_CORPSE]}
    w1 = {"host": ih.get(A_WEAPON), "client": ic.get(A_WEAPON)}
    morale1 = {uid: {"host": (uh.get(uid) or {}).get("morale"), "client": (uc.get(uid) or {}).get("morale")}
               for uid in aliens}
    idiff = item_diff(ih, ic)
    print(f"EVIDENCE SB1: kill={r}; aliens (faction hostile before the kill)={aliens}; "
          f"A before host={unit_view(uh0.get(A_ID))} client={unit_view(uc0.get(A_ID))}; "
          f"A after host={unit_view(uh.get(A_ID))} client={unit_view(uc.get(A_ID))}; "
          f"weapon {A_WEAPON} before={w0} after={w1}; corpses={corpses}; "
          f"items total host={len(ih)} client={len(ic)} hostOnly={idiff['hostOnly']} "
          f"clientOnly={idiff['clientOnly']} differ={idiff['differ']}; morale before(host)={morale0} "
          f"after={morale1}; host evs since seq {seq0}={host_evs_since(host, seq0)}; "
          f"client desyncSeen {before['client']['desyncSeen']}->{pc['desyncSeen']} (latched before the kill: "
          f"{before['client']['desyncSeen']}) desync={dsc} host desyncSeen={ph['desyncSeen']}; "
          f"diffAfterKill={end_diff}; host syncEvsEmitted {before['host']['syncEvsEmitted']}->"
          f"{ph['syncEvsEmitted']} client syncEvsApplied {before['client']['syncEvsApplied']}->"
          f"{pc['syncEvsApplied']}; host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; "
          f"host {delta_view(before['host'])}->{delta_view(ph)}; "
          f"client {delta_view(before['client'])}->{delta_view(pc)}; notes={notes}", flush=True)
    fails = list(notes)
    if not r.get("ok") or r.get("killed") != [A_ID]:
        fails.append(f"kill_unit_real answered {r} (want ok, killed [{A_ID}])")
    for name, it in w0.items():
        if (not it or it.get("type") != A_ITEMS[A_WEAPON][0] or it.get("owner") != A_ID
                or it.get("slot") != A_ITEMS[A_WEAPON][1]):
            fails.append(f"{name} weapon {A_WEAPON} before the kill {it} (want {A_ITEMS[A_WEAPON]} held by A)")
    if idiff["hostOnly"] or idiff["clientOnly"] or idiff["differ"]:
        fails.append(f"battle_items differ: hostOnly={sorted(idiff['hostOnly'])} "
                     f"clientOnly={sorted(idiff['clientOnly'])} differ={idiff['differ']} (want equal)")
    hc_ids = [i["id"] for i in corpses["host"] if i.get("unitLink") == A_ID]
    if len(hc_ids) != 1:
        fails.append(f"host corpses linked to A: {hc_ids} (want exactly 1 {A_CORPSE} with unitLink {A_ID})")
    for cid in hc_ids:
        hcp, ccp = ih.get(cid), ic.get(cid)
        if not ccp:
            fails.append(f"corpse {cid} missing on the client (host {hcp})")
        elif ccp.get("unitLink") != A_ID or ccp.get("type") != A_CORPSE or tile_of(ccp) != tile_of(hcp) \
                or tile_of(hcp) is None:
            fails.append(f"corpse {cid} host={hcp} client={ccp} (want {A_CORPSE}, unitLink {A_ID}, "
                         f"the same tile on both)")
    for name, it in w1.items():
        if (not it or it.get("owner") != -1 or not it.get("onTile")
                or it.get("previousOwner") != A_ID):
            fails.append(f"{name} weapon {A_WEAPON} after the kill {it} (want owner -1, onTile, "
                         f"previousOwner {A_ID})")
    if tile_of(w1["host"]) != tile_of(w1["client"]):
        fails.append(f"weapon {A_WEAPON} tile host={tile_of(w1['host'])} client={tile_of(w1['client'])} "
                     f"(want the same)")
    for name, u in (("host", uh.get(A_ID)), ("client", uc.get(A_ID))):
        if not u or u.get("status") != STATUS_DEAD or u.get("onTile") is not False:
            fails.append(f"{name} A {unit_view(u)} (want status DEAD ({STATUS_DEAD}), onTile false)")
    lowered = [uid for uid in aliens if (morale1[uid]["host"] is not None and morale0[uid] is not None
                                         and morale1[uid]["host"] < morale0[uid])]
    if not lowered:
        fails.append(f"no alien's morale lower on the host after the kill: before={morale0} after={morale1}")
    for uid in lowered:
        if morale1[uid]["host"] != morale1[uid]["client"]:
            fails.append(f"alien {uid} morale host={morale1[uid]['host']} client={morale1[uid]['client']} "
                         f"(want equal)")
    fails += common_fails(host, client, before, {"itemsAdded": 1, "items": 1, "units": 1}, "SB1")
    ld = ph["lastDelta"] or {}
    if "itemIdCtr" not in (ld.get("battle") or []):
        fails.append(f"host lastDelta.battle={ld.get('battle')} (want the key itemIdCtr)")
    if not (ld.get("seq") or 0) > seq0:
        fails.append(f"host lastDelta.seq={ld.get('seq')} is not from this kill (host lastSeqEmitted "
                     f"before it {seq0})")
    finish(fails)


SCENARIOS = (("SB2", sb2_removal), ("SB1", sb1_kill))


# ===================== bring-up =====================


def boot(host, client):
    raw.bring_up_lobby(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p2-sb")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ph = probes(host)
    print(f"[w2p2-sb] boot ok: MAP_FP={MAP_FP!r} turn={hs['turn']} pinned={pinned} "
          f"host deltaArmed={ph['deltaArmed']} deltaSeeds={ph['deltaSeeds']}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49842, make_user_dir("w2p2_delta_items_host"))
    client = GameClient("client", 49843, make_user_dir("w2p2_delta_items_client"))
    results = {}
    try:
        try:
            ctx = boot(host, client)
        except Exception as e:  # a bring-up failure fails the whole run
            print(f"FAIL boot: {type(e).__name__}: {e}", flush=True)
            return 2
        for name, fn in SCENARIOS:
            try:
                fn(host, client, ctx)
                results[name] = True
                print(f"PASS {name}", flush=True)
            except Exception as e:
                results[name] = False
                kind = "" if isinstance(e, AssertionError) else f"{type(e).__name__}: "
                print(f"FAIL {name}: {kind}{e}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p2-sb] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_delta_items: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
