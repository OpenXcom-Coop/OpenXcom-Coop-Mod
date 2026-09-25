"""W2-P2 S-H - test_w2_hash_coverage.py: every synced field is in a hash
bucket, and the second player checks the whole-save hash (spec
rewrite/prompts/w2p2_delta_core.md amendments A5 (A5.2, A5.5), A7 and A8;
owner rulings D138 and D144 = (a); Q-H5 = (a) raw status, F608).

Before stage S-H, seven hash buckets cover part of what the delta syncs; the
rest (facing, armour, reaction hands, surrender flags, script tags, item ammo
links, medikit charges, UFO doors, node types, turn and side...) is only inside
`saveBlob`, which the second player never checks (a carried `saveBlob` is
logged and ignored, F470). After S-H one new bucket, `synced`, holds the 33
delta fields no other bucket covers (A5.2), every event carries it, every
bt_action_end and side_transition carries `saveBlob`, and the second player
compares both. Three scenarios, ONE boot, in this order (HC3 LAST: it freezes
the second player on purpose):

  HC1  Per-field coverage. For each of the 33 A5.2 rows the CLIENT runs the
       test-only `field_poke` lever (one field written with the delta
       applier's own setter, every bucket hashed by name plus saveBlob, the
       field restored with the same setter - all inside one command). The row
       is covered when the poke moves `synced` away from the host's value S0
       and the restore brings it back, while no legacy bucket moves. RED
       (commit S-H.1): `synced` is absent from the lever's buckets on every
       row, and every legacy bucket is unchanged by every poke (the field is
       uncovered today). A row whose poke MOVES a legacy bucket means the A5.2
       table is wrong (STOP-IF H4) and is printed as LEGACY-MOVED. The three
       `tags` rows ([7] at script tag index 1, which no registered tag names
       for unit H on this ruleset) can make the poked battle document
       unparseable; such a row's saveBlob column reads `unserializable`
       (F746), and since `synced` is hashed from the raw values the row is
       still evidence. The lever always restores (F747) and every row prints
       its restoredValue.
  HC2  Carriage + client checks. Host real-UI kneel toggle of H, host
       real-UI walk of H (HC2_H_TILE -> HC2_WALK_DEST), both machines press
       END TURN and the full side cycle runs. GREEN: over that window the
       client compared `synced` once per applied ev (side_begin included,
       Q-H8) and `saveBlob` once per bt_action_end + side_transition (its
       own event_log kinds); no desync; common asserts. RED: the client's
       hashVerifyCounts has no `synced` / `saveBlob` entry.
  HC3  The saveBlob arm. A client-only currStats poke on H2 (`set_stat
       reactions`: serialized, in no bucket, not in the delta, N20) makes
       `saveBlob` the ONLY differing hash (precondition); then a host kneel
       toggle of H. GREEN: the client freezes with bucket `saveBlob` at the
       seq of the kneel's bt_action_end (the kneel ev itself passes). RED:
       client desyncSeen stays false after that bt_action_end.

Common asserts (spec (f)): hash_now {full:true} - ALL buckets EQUAL on both
machines (never a hard-coded count); desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; client deltaEvsApplied increased;
deltaUnresolved, deltaUnsupported, deltaRemoveMissing and deltaAddExisting 0
on both.

FIXTURE (deterministic, never searched here; AMENDMENT A8, owner D144 = (a)).
The classic parallel skirmish bring-up (raw.bring_up_lobby +
session.drive_to_battlescape, seat_count=2) with `newbattle_craft
STR_LIGHTNING` before seating (repro_door_deterministic's route) and set_seed
SEED_MAP right before newbattle_ok, asserted against the baked MAP_FP, then
session.pin_ai_neutral. The Lightning's own UFO door is the doorBits row's
tile (session.lightning_door: exactly one LIGHTNIN entry, WV-D87). Constants
from the S-H.1 precalc boot on this map (2026-09-24): H, H2, A and A's items,
the door, the HC2 walk (open ground, two steps, path_probe-reachable, >= 21
tiles from the only alien). Every staging write goes to BOTH machines, the
client first (F607), and the responses are asserted equal. The fuseEnabled
row needs an item whose fuse timer is set (BattleItem::setFuseEnabled is a
no-op at fuse -1, and no item starts primed): HC1 gives H2 a STR_GRENADE with
fuse 20 on both machines (ids asserted equal) - 20 cannot reach 0 in the one
side cycle this file runs.

RED-THEN-GREEN (spec (d), Q4 = b). Commit S-H.1 (this file, `field_poke`, the
hash-verify probes - no product behaviour) is run ONCE and every scenario must
FAIL with its named red evidence; commit S-H.2 (the `synced` bucket, the `h`
sites, the verify arm) is run ONCE and every scenario must PASS. Each scenario
prints ONE "EVIDENCE <id>:" line with both machines' fields (HC1 also prints
one HC1-ROW line per row) BEFORE its green conditions are checked; main() runs
every scenario even after an earlier one failed and prints "PASS <id>" /
"FAIL <id>: <message>". Every wait is bounded; a wait that times out is
recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when all three scenarios pass, 2
otherwise (a bring-up failure is also 2).

Run:  python tools/coop_test/test_w2_hash_coverage.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
from test_rw_seat_pacing import tab_select, real_click_walk
import test_w2_delta_core as dc

# ----- AMENDMENT A8 map (S-H.1 precalc, 2026-09-24): default NEW BATTLE
# mission (STR_UFO_GROUND_ASSAULT, small scout, farmland), craft STR_LIGHTNING -----
SEED_MAP = 1
CRAFT = "STR_LIGHTNING"
MAP_FP = -5.194867395711193e+18  # host battle_state.mapFingerprint on SEED_MAP 1 with the Lightning
H_ID = 10                        # first host-seat (coop 0) soldier; stats/loadout random per boot (F488)
H2_ID = 11                       # second host-seat soldier (HC3's client-only currStats poke, HC1's grenade)
A_ID = 1000000                   # the only alien: Sectoid Soldier, spawn (27,12,0)
A_ITEMS = {56: ("STR_PLASMA_PISTOL", "STR_RIGHT_HAND"), 58: ("STR_PLASMA_PISTOL_CLIP", "STR_BELT"),
           59: ("STR_MIND_PROBE", "STR_BACK_PACK")}   # 60 items at start: first lever-minted id = 60
A_WEAPON = 56                    # HC1's item rows (ammo [57, 56, 56, 56]: clip 57 in slot 0, slots 1-3 self)
A_CLIP = 57
NODE_ID = 0
HC_UFO_DOOR = (22, 5, 1)         # the Lightning's own UFO door: westwall part, closed at start
HC_UFO_DOOR_PART = "westwall"
HC_UFO_DOOR_BIT = 1              # doorBits: 1 west, 2 north, 4 floor
HC2_H_TILE, HC2_H_DIR = (9, 0, 0), 6          # open ground, facing west
HC2_WALK_DEST = (7, 0, 0)                      # path_probe: 2 steps, TU 8, reachable on both machines
HC2_WALK_PATH = [(8, 0, 0), (7, 0, 0)]
FUSE_ITEM = "STR_GRENADE"        # the fuseEnabled row's item (given to H2's left hand, fuse 20)
FUSE_TURNS = 20
REACTIONS_POKE = 7               # HC3: client-only reactions = current + 7

PORT = "48627"
FACTION_PLAYER = 0
COOP_SEAT_0 = 0
SDLK_K = 107                     # Options::keyBattleKneel default (repro_atom_kneel.py)
STATUS_STANDING, STATUS_TURNING = 0, 3        # src/Mod/Unit.h enum UnitStatus
NODE_TYPE_DANGEROUS = 0x04                     # src/Savegame/Node.h Node::TYPE_DANGEROUS
LEGACY_BUCKETS = ("terrain", "fire", "smoke", "items", "unitsCore", "unitsStats", "itemIdCtr")
HASH_PROBES = ("hashVerifyCounts", "lastHashVerify", "saveBlobUsLast", "saveBlobUsMax",
               "saveBlobVerifyUsLast", "saveBlobVerifyUsMax", "lastSeqEmitted", "lastSeqApplied",
               "desyncSeen")


def neg(b, ctx):
    return not b


# The 33 A5.2 rows that no legacy bucket covers, in the table's order:
# (row, class, target, field, value from `before`). Targets: "H" (unit H), "door"
# (the Lightning door tile), "node", "weapon" (A's pistol), "fuse" (H2's
# primed grenade), "battle".
HC1_ROWS = (
    ("unit.onTile", "unit", "H", "onTile", neg),
    ("unit.dir", "unit", "H", "dir", lambda b, c: (b + 1) % 8),
    ("unit.turretDir", "unit", "H", "turretDir", lambda b, c: (b + 1) % 8),
    ("unit.status", "unit", "H", "status", lambda b, c: STATUS_TURNING),
    ("unit.floating", "unit", "H", "floating", neg),
    ("unit.armor", "unit", "H", "armor", lambda b, c: [b[0] - 1] + list(b[1:])),
    ("unit.wantsToSurrender", "unit", "H", "wantsToSurrender", neg),
    ("unit.isSurrendering", "unit", "H", "isSurrendering", neg),
    ("unit.moraleRestored", "unit", "H", "moraleRestored", lambda b, c: b + 1),
    ("unit.spawnUnit", "unit", "H", "spawnUnit", lambda b, c: c["aType"]),
    ("unit.respawn", "unit", "H", "respawn", neg),
    ("unit.spawnUnitFaction", "unit", "H", "spawnUnitFaction",
     lambda b, c: "player" if b == "hostile" else "hostile"),
    ("unit.alreadyRespawned", "unit", "H", "alreadyRespawned", neg),
    ("unit.reactPref", "unit", "H", "reactPref", lambda b, c: "STR_LEFT_HAND"),
    ("unit.reactOffLeft", "unit", "H", "reactOffLeft", neg),
    ("unit.reactOffRight", "unit", "H", "reactOffRight", neg),
    ("unit.tags", "unit", "H", "tags", lambda b, c: [7]),
    ("tile.doorBits", "tile", "door", "doorBits", lambda b, c: b ^ HC_UFO_DOOR_BIT),
    ("node.type", "node", "node", "type", lambda b, c: b ^ NODE_TYPE_DANGEROUS),
    ("item.previousOwner", "item", "weapon", "previousOwner", lambda b, c: H_ID),
    ("item.unit", "item", "weapon", "unit", lambda b, c: H_ID),
    ("item.ammo", "item", "weapon", "ammo", lambda b, c: [-1] + list(b[1:])),
    ("item.fuseEnabled", "item", "fuse", "fuseEnabled", neg),
    ("item.medikit", "item", "weapon", "medikit", lambda b, c: [b[0] + 1, b[1], b[2]]),
    ("item.droppedOnAlienTurn", "item", "weapon", "droppedOnAlienTurn", neg),
    ("item.xcomProperty", "item", "weapon", "xcomProperty", neg),
    ("item.tags", "item", "weapon", "tags", lambda b, c: [7]),
    ("battle.objectivesDestroyed", "battle", "battle", "objectivesDestroyed", lambda b, c: b + 1),
    ("battle.moduleMap", "battle", "battle", "moduleMap", lambda b, c: [b["columns"], 0, 1, 1]),
    ("battle.bughuntMode", "battle", "battle", "bughuntMode", neg),
    ("battle.turn", "battle", "battle", "turn", lambda b, c: b + 1),
    ("battle.side", "battle", "battle", "side", lambda b, c: "hostile"),
    ("battle.tags", "battle", "battle", "tags", lambda b, c: [7]),
)


# ===================== small probes =====================


def hash_probes(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in HASH_PROBES}


def tile_index(t, size_x, size_y):
    return t[2] * size_y * size_x + t[1] * size_x + t[0]


def host_synced(host):
    """S0: the host's own `synced` bucket (hash_now names it only once it exists)."""
    r = host.cmd({"cmd": "hash_now", "buckets": ["synced"]})
    return (r.get("h") or {}).get("synced") if r.get("ok") else None


def target_of(target, ctx):
    return {"H": {"id": H_ID}, "door": {"i": ctx["doorIndex"]}, "node": {"id": NODE_ID},
            "weapon": {"id": A_WEAPON}, "fuse": {"id": ctx["fuseItemId"]}, "battle": {}}[target]


def since(before, after, key):
    return (after or {}).get(key, 0) - (before or {}).get(key, 0)


# ===================== driving =====================


def host_kneel(host, client, uid, notes, wait_client=True):
    """ONE host real-UI kneel toggle of `uid` (TAB-select, SDLK_K - the
    repro_atom_kneel driver). Waits, bounded, for the host's kneel state to
    flip and the host to go idle; with wait_client also for the client to
    catch up (session.wait_host_idle). Returns (kneeled before, kneeled after
    on the host, host lastSeqEmitted before the key)."""
    if not tab_select(host, uid):
        notes.append(f"TAB never selected {uid} on the host (selectedId {battle_state(host).get('selectedId')})")
        return None, None, None
    k0 = dc.units(host)[uid].get("kneeled")
    s0 = event_state(host).get("lastSeqEmitted", 0)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
    try:
        host.wait_for("host kneel toggled and host idle",
                      lambda: (dc.units(host)[uid].get("kneeled") != k0
                               and event_state(host).get("busyOwnerSeat") == -1
                               and event_state(host).get("lastSeqEmitted", 0) > s0) or None, timeout=20)
    except Exception as e:
        notes.append(f"host kneel: {dc.short(e)}")
    if wait_client:
        try:
            session.wait_host_idle(host, client, timeout=30)
        except Exception as e:
            notes.append(f"wait_host_idle after the kneel: {dc.short(e)}")
    return k0, dc.units(host)[uid].get("kneeled"), s0


def host_walk(host, client, uid, dest, notes):
    """ONE real-UI walk order for `uid` on the host (TAB-select, one click on
    `dest`); bounded waits for the host's walk chain, then for the host to go
    idle with the client caught up. Returns the host's lastWalk."""
    if not tab_select(host, uid):
        notes.append(f"TAB never selected {uid} on the host for the walk")
        return {}
    prev = session.walk_action_id(host)
    try:
        real_click_walk(host, dest)
        host.wait_for("host walk chain finished", lambda: dc.walk_done(host, prev) or None, timeout=30)
    except Exception as e:
        notes.append(f"host walk: {dc.short(e)}")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the walk: {dc.short(e)}")
    return session.last_walk(host) or {}


def action_end_of(host, first_seq, kind):
    """The first `kind` ev with seq >= first_seq in the host's event_log, and
    the seq of the bt_action_end of the same actionId: (ev seq, end seq,
    actionId) - None where absent."""
    evs = [e for e in session.event_log(host, 120) if e.get("seq", 0) >= first_seq]
    ev = next((e for e in evs if e.get("kind") == kind), None)
    if not ev:
        return None, None, None
    end = next((e for e in evs if e.get("kind") == "bt_action_end" and e.get("actionId") == ev.get("actionId")),
               None)
    return ev.get("seq"), (end or {}).get("seq"), ev.get("actionId")


# ===================== scenarios =====================


def hc1(host, client, ctx):
    notes = []
    fails = []
    # The fuseEnabled row's item: a primed grenade in H2's left hand, both machines, ids equal.
    g = dc.both(host, client, {"cmd": "battle_give", "unit": H2_ID, "item": FUSE_ITEM, "slot": "left",
                               "fuse": FUSE_TURNS}, ("weaponId", "weaponSlot"))
    ctx["fuseItemId"] = g["weaponId"]
    # The spawnUnit row's value: A's own unit type (a read-only field_poke peek names it).
    ctx["aType"] = client.cmd({"cmd": "field_poke", "class": "unit", "id": A_ID,
                               "field": "spawnUnit"}).get("unitType")
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after the grenade: {dc.short(e)}")
    try:
        assert_hash_clean(host, client, full=True, what="HC1 start")
    except AssertionError as e:
        fails.append(f"hash_now full not clean before HC1: {dc.short(e, 600)}")
    rows = []
    for n, (row, cls, target, field, value_of) in enumerate(HC1_ROWS, 1):
        tgt = target_of(target, ctx)
        s0 = host_synced(host)
        peek = client.cmd(dict({"cmd": "field_poke", "class": cls, "field": field}, **tgt))
        rec = {"n": n, "row": row, "S0": s0, "err": None}
        if not peek.get("ok"):
            rec["err"] = f"peek: {peek.get('error')}"
            rows.append(rec)
            continue
        before = peek.get("before")
        value = value_of(before, ctx)
        r = client.cmd(dict({"cmd": "field_poke", "class": cls, "field": field, "value": value,
                             "restore": True}, **tgt))
        rec.update({"before": before, "value": value, "errors": r.get("errors")})
        if not r.get("ok"):
            rec["err"] = f"poke: {r.get('error')}"
        # Recorded for every row, a refused or failed poke included: the lever
        # always restores (S-H.1b, F747), so restoredValue shows a failed restore.
        bk = r.get("buckets") or {}
        b0, b1, b2 = bk.get("before") or {}, bk.get("poked") or {}, bk.get("restored") or {}
        sb = r.get("saveBlob") or {}
        # A saveBlob the lever could not serialize (F746: an unregistered script
        # tag) is reported as "unserializable"; the row stays evidence for `synced`.
        sb_col = ("unserializable" if sb.get("poked") == "unserializable"
                  else ("changed" if sb.get("poked") != sb.get("before") else "unchanged"))
        rec.update({
            "poked": r.get("poked"), "restoredValue": r.get("restoredValue"),
            "leverBuckets": sorted(b1),
            "legacyMoved": [k for k in LEGACY_BUCKETS if b1.get(k) != b0.get(k)],
            "legacyNotRestored": [k for k in LEGACY_BUCKETS if b2.get(k) != b0.get(k)],
            "legacyAbsent": [k for k in LEGACY_BUCKETS if k not in b1],
            "syncedInLever": "synced" in b1,
            "syncedPoked": b1.get("synced"), "syncedRestored": b2.get("synced"),
            "saveBlob": sb_col,
            "saveBlobRestored": sb.get("restored") == sb.get("before"),
        })
        rows.append(rec)
    try:
        assert_hash_clean(host, client, full=True, what="HC1 end (every poke restored)")
        end_clean = True
    except AssertionError as e:
        end_clean = False
        fails.append(f"hash_now full not clean after HC1: {dc.short(e, 600)}")

    for rec in rows:
        tag = " LEGACY-MOVED" if rec.get("legacyMoved") else ""
        print(f"HC1-ROW {rec['n']:2d} {rec['row']}:{tag} before={json.dumps(rec.get('before'))} "
              f"value={json.dumps(rec.get('value'))} poked={json.dumps(rec.get('poked'))} "
              f"restored={json.dumps(rec.get('restoredValue'))} legacyMoved={rec.get('legacyMoved')} "
              f"legacyNotRestored={rec.get('legacyNotRestored')} syncedInLever={rec.get('syncedInLever')} "
              f"S0={rec.get('S0')} syncedPoked={rec.get('syncedPoked')} syncedRestored={rec.get('syncedRestored')} "
              f"saveBlob={rec.get('saveBlob')} saveBlobRestored={rec.get('saveBlobRestored')} "
              f"err={rec.get('err')} errors={rec.get('errors')}", flush=True)
    ok_rows = [r for r in rows if not r.get("err")]
    print(f"EVIDENCE HC1: rows={len(rows)}/{len(HC1_ROWS)} answered={len(ok_rows)} "
          f"errors={[(r['row'], r['err']) for r in rows if r.get('err')]}; "
          f"syncedInLever on {sum(1 for r in ok_rows if r.get('syncedInLever'))} row(s); "
          f"legacyMoved on {[r['row'] for r in ok_rows if r.get('legacyMoved')]}; "
          f"legacyNotRestored on {[r['row'] for r in ok_rows if r.get('legacyNotRestored')]}; "
          f"notRestored on {[r['row'] for r in rows if r.get('restoredValue') != r.get('before')]}; "
          f"pokeNoEffect on {[r['row'] for r in ok_rows if r.get('poked') == r.get('before')]}; "
          f"saveBlobChanged on {[r['row'] for r in ok_rows if r.get('saveBlob') == 'changed']}; "
          f"saveBlobUnserializable on {[r['row'] for r in ok_rows if r.get('saveBlob') == 'unserializable']}; "
          f"host S0 synced={sorted({r.get('S0') for r in rows}, key=str)}; "
          f"leverBuckets={ok_rows[0].get('leverBuckets') if ok_rows else None}; "
          f"fuse item {ctx['fuseItemId']} door i={ctx['doorIndex']} A type={ctx['aType']}; "
          f"hash clean after={end_clean}; notes={notes}", flush=True)

    for r in rows:
        if r.get("err"):
            fails.append(f"{r['row']}: {r['err']}")
            continue
        why = []
        if r.get("poked") == r.get("before"):
            why.append(f"the poke changed nothing (before={r.get('before')} poked={r.get('poked')})")
        if r.get("restoredValue") != r.get("before"):
            why.append(f"restoredValue {r.get('restoredValue')} != before {r.get('before')}")
        if r.get("legacyMoved"):
            why.append(f"the poke moved legacy bucket(s) {r['legacyMoved']} (A5.2 table wrong, STOP-IF H4)")
        if r.get("legacyNotRestored"):
            why.append(f"legacy bucket(s) {r['legacyNotRestored']} not restored")
        if r.get("legacyAbsent"):
            why.append(f"legacy bucket(s) {r['legacyAbsent']} missing from the lever")
        if not r.get("syncedInLever"):
            why.append("'synced' is not among the lever's buckets")
        else:
            if r.get("S0") is None:
                why.append("host hash_now has no 'synced'")
            if r.get("syncedPoked") == r.get("S0"):
                why.append(f"poked synced == S0 {r.get('S0')} (field not covered)")
            if r.get("syncedRestored") != r.get("S0"):
                why.append(f"restored synced {r.get('syncedRestored')} != S0 {r.get('S0')}")
        if why:
            fails.append(f"{r['row']}: " + "; ".join(why))
    if len(rows) != len(HC1_ROWS):
        fails.append(f"only {len(rows)} of {len(HC1_ROWS)} rows ran")
    dc.finish(notes + fails)


def hc2(host, client, ctx):
    notes = []
    dc.tele_both(host, client, H_ID, HC2_H_TILE, HC2_H_DIR)
    dc.tu_both(host, client, H_ID)
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        notes.append(f"wait_host_idle after staging: {dc.short(e)}")
    before = {"host": dc.probes(host), "client": dc.probes(client)}
    ch0, hh0 = hash_probes(client), hash_probes(host)
    k0, k1, _ = host_kneel(host, client, H_ID, notes)
    hw = host_walk(host, client, H_ID, HC2_WALK_DEST, notes)
    turn0 = dc.end_turn_cycle(host, client, notes)
    hs, cs = battle_state(host), battle_state(client)
    ch1, hh1 = hash_probes(client), hash_probes(host)
    seq0, seq1 = ch0["lastSeqApplied"] or 0, ch1["lastSeqApplied"] or 0
    log = session.event_log(client, 256)
    window = [e for e in log if seq0 < e.get("seq", 0) <= seq1]
    covered = bool(log) and min(e.get("seq", 0) for e in log) <= seq0 + 1
    kinds = [e.get("kind") for e in window]
    ends = sum(1 for k in kinds if k in ("bt_action_end", "side_transition"))
    d_seq = seq1 - seq0
    d_synced = since(ch0["hashVerifyCounts"], ch1["hashVerifyCounts"], "synced")
    d_sb = since(ch0["hashVerifyCounts"], ch1["hashVerifyCounts"], "saveBlob")
    print(f"EVIDENCE HC2: H kneeled {k0}->{k1}; walk executed={dc.executed_path(hw)}; "
          f"turn {turn0} -> host=({hs.get('turn')},{hs.get('side')}) client=({cs.get('turn')},{cs.get('side')}); "
          f"client lastSeqApplied {seq0}->{seq1} (d={d_seq}), window kinds={kinds} (log covers window={covered}); "
          f"bt_action_end+side_transition={ends}; client hashVerifyCounts {ch0['hashVerifyCounts']}->"
          f"{ch1['hashVerifyCounts']} (d synced={d_synced}, d saveBlob={d_sb}); "
          f"client lastHashVerify={ch1['lastHashVerify']}; host saveBlobUs last/max "
          f"{hh1['saveBlobUsLast']}/{hh1['saveBlobUsMax']}; client saveBlobVerifyUs last/max "
          f"{ch1['saveBlobVerifyUsLast']}/{ch1['saveBlobVerifyUsMax']}; desyncSeen host={hh1['desyncSeen']} "
          f"client={ch1['desyncSeen']}; notes={notes}", flush=True)
    fails = list(notes)
    if k0 is None or k1 == k0:
        fails.append(f"the host kneel did not toggle H ({k0}->{k1})")
    if dc.executed_path(hw) != HC2_WALK_PATH:
        fails.append(f"walk executed {dc.executed_path(hw)} (want {HC2_WALK_PATH})")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER,
                                                                             turn0 + 1, FACTION_PLAYER):
        fails.append(f"not on player turn {turn0 + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')})")
    if not covered:
        fails.append(f"the client event_log tail does not reach back to seq {seq0 + 1}")
    if d_seq <= 0 or ends <= 0:
        fails.append(f"empty window (d lastSeqApplied={d_seq}, action ends+side transitions={ends})")
    if d_synced != d_seq:
        fails.append(f"client compared 'synced' {d_synced} time(s) over {d_seq} applied ev(s) (want equal)")
    if d_sb != ends:
        fails.append(f"client compared 'saveBlob' {d_sb} time(s) over {ends} bt_action_end+side_transition "
                     f"ev(s) (want equal)")
    fails += dc.common_fails(host, client, before, {}, "HC2")
    dc.finish(fails)


def hc3(host, client, ctx):
    notes = []
    before = {"host": dc.probes(host), "client": dc.probes(client)}
    ch0 = hash_probes(client)
    r0 = dc.units(client)[H2_ID].get("reactions")
    rs = client.cmd({"cmd": "battle_action", "action": "set_stat", "unit": H2_ID, "stat": "reactions",
                     "value": (r0 or 0) + REACTIONS_POKE})
    r1c, r1h = dc.units(client)[H2_ID].get("reactions"), dc.units(host)[H2_ID].get("reactions")
    pre_diff = dc.diff_buckets(host, client)
    k0, k1, s0 = host_kneel(host, client, H_ID, notes, wait_client=False)
    kneel_seq, end_seq, action_id = action_end_of(host, (s0 or 0) + 1, "kneel")
    try:
        client.wait_for("client froze or applied the kneel's bt_action_end",
                        lambda: (event_state(client).get("desyncSeen")
                                 or (end_seq is not None
                                     and event_state(client).get("lastSeqApplied", 0) >= end_seq)) or None,
                        timeout=30)
    except Exception as e:
        notes.append(f"client wait: {dc.short(e)}")
    pc = dc.probes(client)
    ch1 = hash_probes(client)
    dsc = dc.desync_record(client, pc["desyncSeen"])
    print(f"EVIDENCE HC3: H2 reactions client {r0}->{r1c} (set_stat ok={rs.get('ok')}) host {r1h}; "
          f"hash diff before the kneel={pre_diff}; host kneel H {k0}->{k1} actionId={action_id} "
          f"kneel seq={kneel_seq} bt_action_end seq={end_seq}; client desyncSeen "
          f"{before['client']['desyncSeen']}->{pc['desyncSeen']} desync={dsc}; client lastSeqApplied "
          f"{ch0['lastSeqApplied']}->{ch1['lastSeqApplied']}; client hashVerifyCounts {ch0['hashVerifyCounts']}->"
          f"{ch1['hashVerifyCounts']}; client lastHashVerify={ch1['lastHashVerify']}; notes={notes}", flush=True)
    fails = list(notes)
    if not rs.get("ok") or r1c != (r0 or 0) + REACTIONS_POKE:
        fails.append(f"client set_stat reactions: {rs} (reactions {r0}->{r1c})")
    if pre_diff != ["saveBlob"]:
        fails.append(f"hash diff before the kneel {pre_diff} (want exactly ['saveBlob'] - precondition)")
    if k0 is None or k1 == k0 or end_seq is None:
        fails.append(f"the host kneel did not complete (kneeled {k0}->{k1}, bt_action_end seq {end_seq})")
    if before["client"]["desyncSeen"]:
        fails.append("client desyncSeen was already true before HC3")
    if not pc["desyncSeen"]:
        fails.append(f"client desyncSeen false after the kneel's bt_action_end (seq {end_seq}) "
                     f"(want true, bucket saveBlob)")
    if not dsc or dsc.get("bucket") != "saveBlob" or dsc.get("seq") != end_seq:
        fails.append(f"client desync {dsc} (want bucket saveBlob at the kneel's bt_action_end seq {end_seq}; "
                     f"the kneel ev seq {kneel_seq} must pass)")
    dc.finish(fails)


SCENARIOS = (("HC1", hc1), ("HC2", hc2), ("HC3", hc3))


# ===================== bring-up =====================


def boot(host, client):
    raw.bring_up_lobby(host, client, PORT)
    seated = {}
    craft = {}

    def pin_craft(h):
        craft["r"] = h.ok({"cmd": "newbattle_craft", "type": CRAFT})

    session.drive_to_battlescape(host, client, seated, seat_count=2, pre_seat=pin_craft,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    assert (craft.get("r") or {}).get("selected") == CRAFT, f"newbattle_craft: {craft.get('r')}"
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (SEED_MAP {SEED_MAP}, {CRAFT})")
    pinned = pin_ai_neutral(host, client, tag="w2p2-sh")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids[:2] == [H_ID, H2_ID], f"host-seat soldiers {h_ids} (baked H={H_ID}, H2={H2_ID})"
    assert A_ID in session.units_by_id(hs), f"no unit {A_ID} (baked A)"
    items = {i["id"]: i for i in host.cmd({"cmd": "battle_items"}).get("items", [])}
    for iid, (itype, islot) in A_ITEMS.items():
        it = items.get(iid) or {}
        assert (it.get("type"), it.get("slot"), it.get("owner")) == (itype, islot, A_ID), (
            f"A item {iid}: {it} (baked {itype} in {islot})")
    assert (items.get(A_WEAPON) or {}).get("ammo", [None])[0] == A_CLIP, f"A weapon {items.get(A_WEAPON)}"
    door, mx, my = session.lightning_door(host)
    assert (door["x"], door["y"], door["z"], door["part"]) == HC_UFO_DOOR + (1,), (
        f"Lightning door {door} (baked {HC_UFO_DOOR} {HC_UFO_DOOR_PART})")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    ctx = {"doorIndex": tile_index(HC_UFO_DOOR, mx, my)}
    ph = dc.probes(host)
    print(f"[w2p2-sh] boot ok: MAP_FP={MAP_FP!r} craft={CRAFT} turn={hs['turn']} H={H_ID} H2={H2_ID} "
          f"pinned={pinned} door={door} ctx={ctx} host deltaArmed={ph['deltaArmed']}", flush=True)
    return ctx


def main():
    t0 = time.time()
    host = GameClient("host", 49850, make_user_dir("w2p2_hash_coverage_host"))
    client = GameClient("client", 49851, make_user_dir("w2p2_hash_coverage_client"))
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
                print(f"[w2p2-sh] shutdown {gc.name}: {dc.short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_hash_coverage: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
