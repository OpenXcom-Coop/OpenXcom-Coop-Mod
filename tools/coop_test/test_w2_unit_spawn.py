"""W2-P3 S-C - test_w2_unit_spawn.py: a unit the host creates mid-battle (a
conversion) appears on the second player's machine with the host's id, built
from the host's own saved record, together with its special built-in weapon -
and a special weapon the host removes is removed there too (spec
rewrite/prompts/w2p3_nonplayer_origins.md section (f) "test_w2_unit_spawn.py
(S-C)", sections (b)9-(b)13, amendment B1 (ST8, RQ2, RQ5, RQ7, RQ9, RQ10,
RQ11); ledger `## W2-P3 TASK 0b` (F857-F862) and `## W2-P3 TASK 0d` (F887,
F888); owner ruling D128 = (b)).

Before S-C, on the W2-P3 base, a unit add is unsupported by the delta
(W2-P2 (b)2): the host logs it once as `deltaUnsupported`, the hash reports the
divergence, and the second player freezes (F860: at the snap's bt_action_end,
first bucket `items`). A special weapon in `itemsAdded` is unsupported the
same way (MJ-5).

Two scenarios, ONE boot, in this order (TASK 0b's C12a capture order):

  C12a-1  conversion with a special weapon. H (host seat) gets a loaded
          STR_RIFLE (battle_give, BOTH: rifle RIFLE_ID, clip CLIP_ID), H on
          C12A_H_TILE, S (client seat) on C12A_S_TILE (BOTH);
          battle_set_unit_state {unit S, spawnUnit STR_SECTOID_LEADER,
          spawnUnitFaction 1, respawn true} on BOTH (the S-C.1 lever fields,
          absorbed on the host); H tu TU_MAX (BOTH); host set_seed SEED_C12A,
          host battle_fire {unit H, snap, C12A_FLOOR}. The snap hits the floor;
          at the projectile's end BattlescapeGame::convertInfected() converts S
          (F858: the snap need not hit S) into L = L_ID, which owns the
          ALIEN_PSI_WEAPON X = X_ID. The host dismisses its own "has been
          killed" infobox when one shows (F425; F861: none shows in the
          harness). Then L is pinned on BOTH (psiSkill 0, reactions 0, tu 0 +
          refill).
          GREEN: host `closedContexts` {origin host, kind shoot, actorId H,
          nestedIn 0, hasFinal true} for H's action, whose evs (host log, and
          the client log holds them) are exactly shot -> hit -> spawn ->
          bt_action_end; the spawn payload is {unit L, cause convert, from S};
          that spawn ev's delta (host `deltaRing` entry of its seq) has
          unitsAdded 1 ([L]) and itemsAdded >= 1 (X among them); on BOTH: L
          with id L_ID, type STR_SECTOID_LEADER, faction hostile, on S's former
          tile; S status DEAD, onTile false; L specialWeapons [X] and
          psiWeapon X; item X special true, owner L, type ALIEN_PSI_WEAPON;
          the itemIdCtr bucket equal; the pin of L applied on both.
          RED (TASK 0d / F860): host (shot)(hit)(bt_action_end)(reveal 0), no
          spawn ev; host deltaUnsupported +2 (the unit add, the special-weapon
          item add); the client freezes at the bt_action_end, first bucket
          `items`; L and X exist on the host only; the client refuses the pin
          of L ("no such unit id").
  C12a-2  the special weapon removed (ST8: runs at red too). battle_set_unit_state
          {unit L, spawnUnit STR_SECTOID_SOLDIER, spawnUnitFaction 1, respawn
          true} on BOTH; H tu TU_MAX (BOTH); host set_seed SEED_C12A2, host
          battle_fire {unit H, snap, C12A_FLOOR}; L converts into M = M_ID and
          L's special weapon X is removed (convertUnit -> itemDropInventory ->
          removeSpecialWeapons, F859); M is pinned on BOTH.
          GREEN: H's second action = shot -> hit -> spawn -> bt_action_end in
          a host context {origin host, kind shoot, actorId H}; the spawn
          payload is {unit M, cause convert, from L}; that spawn ev's delta has
          unitsAdded 1 ([M]) and itemsRemoved containing X; X absent on both;
          L specialWeapons [] and psiWeapon -1 on both, L DEAD and off its tile
          on both; M with id M_ID, type STR_SECTOID_SOLDIER, hostile, on
          C12A_S_TILE on both.
          RED (TASK 0b capture, ST8): the client refuses the L staging ("no
          such unit id"); the host converts L into M and removes X (host
          deltaUnsupported +1 more: the unit add of M); the client stays frozen
          at C12a-1's seq.

Common asserts (spec (f) as amended by B1 RQ5): W2-P2's common asserts
(hash_now {full:true} ALL buckets EQUAL; desyncSeen false on both; client
coopClientBStatePushes unchanged and host 0; client deltaEvsApplied increased;
deltaUnresolved, deltaUnsupported, deltaRemoveMissing, deltaAddExisting 0 on
both; lever-made items created on BOTH with equal ids; staging writes on BOTH
with equal responses); host contextBeginRefused 0; contextsOpened grew by
exactly the number of contexts the scenario closed; every chain ev carries the
id of a context the scenario closed; each context has exactly one
bt_action_end, its last ev, recorded in closedContexts (endSeq); no `sync`
inside a context; the client log holds the host's seqs/kinds/actionIds.
contextsClosedAtEndTurn is a diagnostic (printed, never asserted, RQ5). The
client DESYNC line's `kind` label is never asserted (F888: `?` for a
bt_action_end).

Probes: event_state deltaRing (S-C.1, B1 RQ7: the host's last 32 attached
deltas by seq, each with unitsAddedIds / itemsAddedIds / itemsRemovedIds),
lastDelta (unitsAdded), closedContexts, contextsOpened, contextBeginRefused,
cueCounts; battle_state units[] type, originalFaction, spawnUnit, respawn,
specialWeapons (the ids of the special weapons the unit owns), psiWeapon
(getSpecialWeapon(BT_PSIAMP), -1 when none), status, onTile; battle_items
special / owner / type; the host's `[coop-cue] <kind> seq <n> actionId <id>:
<payload>` log line for the cue payloads; hash_now {full:true}.

Bring-up (deterministic, never searched here; ledger `## W2-P3 TASK 0b`,
scratch w2p3/T0b/constants.md): set_seed SEED_ROSTER on the HOST right before
its open_new_battle; the DEFAULT NEW BATTLE map with set_seed SEED_MAP right
before newbattle_ok, seat_count=2, MAP_FP asserted on both; the unit order
UNIT_ORDER asserted (L = last unit id + 1); session.pin_ai_neutral (pins A).
Every lever pair applies to the CLIENT first, then the HOST (F607). The
seeds are set on the HOST immediately before the press that starts the chain.

RED-THEN-GREEN (spec (d) row S-C). Commit S-C.1 (this file, the lever fields,
the deltaRing and unit/item probes, field_poke support; product behaviour
unchanged) is run ONCE and both scenarios must FAIL with the RED above;
commit S-C.2 (unitsAdded, the special-weapon branches, the spawn cues) is run
ONCE and both must PASS. Each scenario prints ONE "EVIDENCE <id>:" line with
both machines' fields BEFORE its green conditions are checked; main() runs
every scenario even after an earlier one failed and prints "PASS <id>" /
"FAIL <id>: <message>". Every wait is bounded; a wait that times out is
recorded in the EVIDENCE line and fails the scenario.

WV-D99 / WV-D100: one run is the result. No skip path, no second boot, no
alternative map or actor. Exit 0 only when both scenarios pass, 2 otherwise
(a bring-up failure is also 2). WV-D95: run in the foreground to completion.

Run:  python tools/coop_test/test_w2_unit_spawn.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, pin_ai_neutral, assert_hash_clean
from test_w2_delta_core import probes, diff_buckets, desync_record, short, both, tele_both, common_fails, finish, \
    delta_view, hashes
from test_w2_host_combat import evs_since, ev_tuples, cue_probes, cue_delta
from test_w2_ai_origins import (host_payloads, ctx_probes, new_closed, opened_delta, ctx_of, ctx_view, sv,
                                bring_up_lobby_roster_pinned)
from test_w2_reaction_prox import context_fails

# ----- bring-up (W2-P3 TASK 0b, ledger `## W2-P3 TASK 0b`, T0b constants.md "Common bring-up") -----
SEED_ROSTER = 1                  # set_seed on the HOST right before its open_new_battle (F501)
SEED_MAP = 1                     # set_seed in pre_ok right before newbattle_ok; DEFAULT NEW BATTLE (no mission)
MAP_FP = -4.48310638993e+18      # host AND client battle_state.mapFingerprint (STR_UFO_GROUND_ASSAULT, small scout)
SEATED = [8, 9]                  # the client seat's soldiers
A_ID = 1000000                   # the only alien, pinned by session.pin_ai_neutral
UNIT_ORDER = [8, 9, 10, 11, 12, 13, 14, 1000000]   # battle_state.units order = _units order (L = last id + 1)
FIRST_LEVER_ITEM_ID = 60         # 60 items at start (ids 0..59): the first lever-made item is 60
PORT = "48635"
TU_MAX = 255                     # battle_set_unit_state tu: clamped to the unit's max TU

# ----- C12a (T0b constants.md "C12a"; F857-F862) -----
S_ID, H_ID = 8, 10               # S: client seat (converted); H: host seat (the shooter)
C12A_H_TILE, C12A_H_DIR = (4, 6, 0), 0
C12A_S_TILE, C12A_S_DIR = (8, 6, 0), 0   # off H's line of fire
C12A_FLOOR = (4, 3, 0)           # empty floor tile 3 north of H: every snap lands here (impact 0)
RIFLE_ID, CLIP_ID = 60, 61       # battle_give {unit H, STR_RIFLE, ammo STR_RIFLE_CLIP, clear_hands} on both
SEED_C12A = 1                    # host set_seed right before the first battle_fire
SEED_C12A2 = 2                   # host set_seed right before the second battle_fire
L_ID, L_TYPE = 1000001, "STR_SECTOID_LEADER"
X_ID, X_TYPE = 62, "ALIEN_PSI_WEAPON"   # L's special weapon (items.rul:1506), itemIdCtr 62 -> 63
M_ID, M_TYPE = 1000002, "STR_SECTOID_SOLDIER"
FACTION_HOSTILE = 1
STATUS_DEAD = 6                  # src/Mod/Unit.h enum UnitStatus
CHAIN = ["shot", "hit", "spawn", "bt_action_end"]   # H's snap: one floor hit (T0b 3/3), then the conversion
PAYLOAD_KINDS = ("shot", "hit", "spawn", "death", "corpse")
UNIT_KEYS = ("type", "faction", "originalFaction", "status", "isOut", "onTile", "x", "y", "z", "direction", "tu",
             "health", "spawnUnit", "respawn", "specialWeapons", "psiWeapon")


# ===================== small probes =====================


def units(gc):
    return session.units_by_id(battle_state(gc))


def items(gc):
    """battle_items as {id: the full item record} (every BattleItem this machine holds)."""
    r = gc.cmd({"cmd": "battle_items"})
    assert r.get("ok"), f"battle_items failed on {gc.name}: {r}"
    return {it["id"]: it for it in r.get("items", [])}


def uview(u):
    if not u:
        return None
    return {k: u.get(k) for k in UNIT_KEYS}


def iview(it):
    if not it:
        return None
    return {k: it.get(k) for k in ("type", "owner", "slot", "special", "onTile")}


def xyz(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def ring_of(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return es.get("deltaRing")


def ring_at(ring, seq):
    for r in ring or []:
        if r.get("seq") == seq:
            return r
    return None


def ring_view(r):
    if not r:
        return None
    return {k: r.get(k) for k in ("seq", "kind", "units", "unitsAdded", "items", "itemsAdded", "itemsRemoved",
                                  "unitsAddedIds", "itemsAddedIds", "itemsRemovedIds", "battle")}


# ===================== levers =====================


def both_rec(host, client, req, keys, fails, what):
    """`req` on BOTH machines (client first, F607), never raising: a refusal on
    either machine or a response that differs on `keys` is appended to
    `fails`. Returns (host response, client response)."""
    rc = client.cmd(dict(req))
    rh = host.cmd(dict(req))
    if not rh.get("ok") or not rc.get("ok"):
        fails.append(f"{what}: host ok={rh.get('ok')} error={rh.get('error')!r}; client ok={rc.get('ok')} "
                     f"error={rc.get('error')!r} (want ok on both)")
    else:
        vh, vc = tuple(rh.get(k) for k in keys), tuple(rc.get(k) for k in keys)
        if vh != vc:
            fails.append(f"{what}: responses differ on {keys}: host={vh} client={vc} (want equal)")
    return rh, rc


def pin_both(host, client, uid, fails, what):
    """session.pin_ai_neutral's three set_stat calls for one unit, on BOTH
    machines (client first): psiSkill 0, reactions 0, tu 0 + refill."""
    out = {}
    for stat, extra in (("psiSkill", {}), ("reactions", {}), ("tu", {"refill": True})):
        req = dict({"cmd": "battle_action", "action": "set_stat", "unit": uid, "stat": stat, "value": 0}, **extra)
        rh, rc = both_rec(host, client, req, ("tu",), fails, f"{what} set_stat {stat} 0")
        out[stat] = {"host": (rh.get("ok"), rh.get("tu"), rh.get("error")),
                     "client": (rc.get("ok"), rc.get("tu"), rc.get("error"))}
    return out


# ===================== the snap =====================


def host_chain_idle(host, dismissed):
    """HOST only: no BState queued or running, no action context open, and no
    vanilla infobox on top - an InfoboxState on top is dismissed (host only,
    F425) and recorded in `dismissed`."""
    lw = host.cmd({"cmd": "list_widgets"}).get("state", "")
    if "Infobox" in lw:
        dismissed.append((lw.split(">")[-1], host.cmd({"cmd": "dismiss_popup"}).get("handled")))
        return None
    bs = battle_state(host)
    return (bs.get("pendingStates") == 0 and not bs.get("isBusy")
            and event_state(host).get("busyOwnerSeat") == -1) or None


def client_settled(host, client):
    """The client froze (desyncSeen), or it applied every ev the host emitted
    with both queues empty and the host idle (session.wait_host_idle's
    predicate)."""
    ec, eh = event_state(client), event_state(host)
    if ec.get("desyncSeen"):
        return "froze"
    return (eh.get("busyOwnerSeat") == -1 and ec.get("lastSeqApplied", 0) == eh.get("lastSeqEmitted", 0)
            and ec.get("queueDepth") == 0 and eh.get("queueDepth") == 0) and "caught up" or None


def snap(host, client, seed, notes):
    """H tu TU_MAX (BOTH), host set_seed `seed`, host battle_fire {unit H, snap,
    C12A_FLOOR}; bounded waits: the host chain idle (host only), then the
    client caught up or frozen. Returns the scenario record."""
    both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "tu": TU_MAX}, ("tu",))
    before = {"host": probes(host), "client": probes(client)}
    cb = {"host": ctx_probes(host), "client": ctx_probes(client)}
    kb = {"host": cue_probes(host), "client": cue_probes(client)}
    seq0 = before["host"]["lastSeqEmitted"] or 0
    host.ok({"cmd": "set_seed", "seed": seed})
    fire = host.cmd({"cmd": "battle_fire", "unit": H_ID, "mode": "snap", "x": C12A_FLOOR[0], "y": C12A_FLOOR[1],
                     "z": C12A_FLOOR[2]})
    if not fire.get("ok"):
        notes.append(f"battle_fire refused: {fire}")
    dismissed = []
    try:
        host.wait_for("host chain idle", lambda: host_chain_idle(host, dismissed), timeout=30)
    except Exception as e:
        notes.append(f"host chain wait: {short(e)}")
    settled = None
    try:
        settled = client.wait_for("client caught up or froze", lambda: client_settled(host, client), timeout=30)
    except Exception as e:
        notes.append(f"client wait: {short(e)}")
    ph, pc = probes(host), probes(client)
    ca = {"host": ctx_probes(host), "client": ctx_probes(client)}
    ka = {"host": cue_probes(host), "client": cue_probes(client)}
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    pl = host_payloads(host, [e["seq"] for e in hev if e["kind"] in PAYLOAD_KINDS])
    hh, hc = hashes(host), hashes(client)
    return {"seed": seed, "notes": notes, "fire": {k: fire.get(k) for k in ("ok", "error", "tuCost", "tuHave",
                                                                          "weaponId", "ammoId")},
            "dismissed": dismissed, "settled": settled, "before": before, "cb": cb, "ca": ca, "kb": kb, "ka": ka,
            "seq0": seq0, "hev": hev, "cev": cev, "pl": pl, "ph": ph, "pc": pc,
            "uh": units(host), "uc": units(client), "ih": items(host), "ic": items(client),
            "ring": ring_of(host), "clientRing": ring_of(client),
            "closed": new_closed(cb["host"], ca["host"]), "opened": opened_delta(cb["host"], ca["host"]),
            "itemIdCtr": (hh.get("itemIdCtr"), hc.get("itemIdCtr")),
            "diff": sorted(k for k in set(hh) | set(hc) if hh.get(k) != hc.get(k)),
            "desync": desync_record(client, pc["desyncSeen"])}


def payload(rec, e):
    return (rec["pl"].get(e["seq"]) or {}).get("payload") or {}


def snap_evidence(rec, what):
    ph, pc = rec["ph"], rec["pc"]
    cb, ca = rec["cb"]["host"], rec["ca"]["host"]
    cues = [(e["seq"], e["kind"], e["actionId"], payload(rec, e)) for e in rec["hev"] if e["kind"] in PAYLOAD_KINDS]
    ring = [ring_view(r) for r in (rec["ring"] or []) if (r.get("seq") or 0) > rec["seq0"]]
    desync = rec["desync"] and {k: rec["desync"].get(k) for k in ("bucket", "seq")}   # F888: never the kind label
    return (f"{what} seed={rec['seed']} fire={rec['fire']} infoboxes dismissed={rec['dismissed']} client "
            f"wait={rec['settled']}; host evs since seq {rec['seq0']}={ev_tuples(rec['hev'])} client evs="
            f"{ev_tuples(rec['cev'])} (seq, kind, actionId, h); host cues (seq, kind, actionId, payload)={cues}; "
            f"host deltaRing since seq {rec['seq0']}={ring}; client deltaRing={rec['clientRing']}; "
            f"closedContexts(new, host)={[ctx_view(c) for c in rec['closed']]}; contextsOpened delta(host)="
            f"{rec['opened']}; contextsClosedAtEndTurn(host, diagnostic)={cb['contextsClosedAtEndTurn']}->"
            f"{ca['contextsClosedAtEndTurn']}; contextBeginRefused(host)={ca['contextBeginRefused']}; "
            f"armingDeferrals(host)={cb['armingDeferrals']}->{ca['armingDeferrals']}; cueCounts delta host="
            f"{cue_delta(rec['kb']['host']['cueCounts'], rec['ka']['host']['cueCounts'])} client="
            f"{cue_delta(rec['kb']['client']['cueCounts'], rec['ka']['client']['cueCounts'])}; itemIdCtr "
            f"host/client={rec['itemIdCtr']}; diff={rec['diff']}; desyncSeen host={ph['desyncSeen']} client="
            f"{pc['desyncSeen']} desync(bucket, seq)={desync}; host {delta_view(rec['before']['host'])}->"
            f"{delta_view(ph)}; client {delta_view(rec['before']['client'])}->{delta_view(pc)}; host lastDelta="
            f"{ph['lastDelta']} client lastDelta={pc['lastDelta']}; notes={rec['notes']}")


def units_evidence(rec, ids):
    return {uid: {"host": uview(rec["uh"].get(uid)), "client": uview(rec["uc"].get(uid))} for uid in ids}


def items_evidence(rec, ids):
    return {iid: {"host": iview(rec["ih"].get(iid)), "client": iview(rec["ic"].get(iid))} for iid in ids}


# ===================== checks =====================


def chain_fails(rec, what):
    """H's snap: the action of the first `shot` since seq0 is a host context
    {origin host, kind shoot, actorId H, nestedIn 0, hasFinal true} whose evs
    are exactly CHAIN. Returns (fails, its evs, the spawn ev or None)."""
    fails = []
    shots = [e for e in rec["hev"] if e["kind"] == "shot"]
    if not shots:
        return [f"{what}: no `shot` ev in the host log since seq {rec['seq0']} (host evs {sv(rec['hev'])})"], [], None
    aid = shots[0]["actionId"]
    evs = [e for e in rec["hev"] if aid and e["actionId"] == aid]
    kinds = [e["kind"] for e in evs]
    if not aid or kinds != CHAIN:
        fails.append(f"{what}: H's action {aid} evs {sv(evs)} (want exactly {CHAIN}; host evs {sv(rec['hev'])})")
    c = ctx_of(rec["closed"], aid) if aid else None
    if not c or (c.get("origin"), c.get("kind"), c.get("actorId"), c.get("nestedIn"), c.get("hasFinal")) != (
            "host", "shoot", H_ID, 0, True):
        fails.append(f"{what}: H's action context {aid} = {ctx_view(c)} (want origin host, kind shoot, actorId "
                     f"{H_ID}, nestedIn 0, hasFinal true)")
    sp = payload(rec, shots[0])
    if sp.get("actor") != H_ID or sp.get("action") != "snap":
        fails.append(f"{what}: the shot payload {sp or None} (want actor {H_ID}, action snap)")
    spawns = [e for e in rec["hev"] if e["kind"] == "spawn"]
    if len(spawns) != 1:
        fails.append(f"{what}: `spawn` evs in the host log {sv(spawns)} (want exactly one, in H's action {aid})")
    return fails, evs, (spawns[0] if spawns else None)


def spawn_fails(rec, spawn, unit_id, from_id, what):
    """The spawn cue {unit, cause convert, from} and its own delta (the host
    deltaRing entry of its seq) with unitsAdded exactly [unit_id]."""
    fails = []
    if not spawn:
        return [f"{what}: no `spawn` ev (want spawn {{unit {unit_id}, cause convert, from {from_id}}})"], None
    p = payload(rec, spawn)
    if (p.get("unit"), p.get("cause"), p.get("from")) != (unit_id, "convert", from_id):
        fails.append(f"{what}: spawn seq {spawn['seq']} payload {p or None} (want unit {unit_id}, cause convert, "
                     f"from {from_id})")
    r = ring_at(rec["ring"], spawn["seq"])
    if not r:
        fails.append(f"{what}: the host deltaRing has no entry for the spawn ev's seq {spawn['seq']} (want its "
                     f"delta: unitsAdded [{unit_id}])")
    elif r.get("unitsAdded") != 1 or r.get("unitsAddedIds") != [unit_id]:
        fails.append(f"{what}: the spawn ev's delta {ring_view(r)} (want unitsAdded 1, unitsAddedIds [{unit_id}])")
    return fails, r


def unit_fails(rec, uid, want, what):
    """`want` = {field: value} on BOTH machines' battle_state unit `uid`."""
    fails = []
    for name, u in (("host", rec["uh"].get(uid)), ("client", rec["uc"].get(uid))):
        if not u:
            fails.append(f"{what}: unit {uid} absent on the {name} (want {want})")
            continue
        got = {k: u.get(k) for k in want}
        if got != want:
            fails.append(f"{what}: unit {uid} on the {name} {got} (want {want})")
    return fails


# ===================== scenarios =====================


def c12a_convert(host, client, ctx):
    notes = []
    fails = []
    g = both(host, client, {"cmd": "battle_give", "unit": H_ID, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                            "clear_hands": True}, ("weaponId", "ammoId"))
    tele_both(host, client, H_ID, C12A_H_TILE, C12A_H_DIR)
    tele_both(host, client, S_ID, C12A_S_TILE, C12A_S_DIR)
    st = both(host, client, {"cmd": "battle_set_unit_state", "unit": S_ID, "spawnUnit": L_TYPE,
                             "spawnUnitFaction": FACTION_HOSTILE, "respawn": True},
              ("spawnUnit", "spawnUnitFaction", "respawn"))
    staged_diff = diff_buckets(host, client)
    s_staged = {"host": uview(units(host).get(S_ID)), "client": uview(units(client).get(S_ID))}
    rec = snap(host, client, SEED_C12A, notes)
    pin = pin_both(host, client, L_ID, fails, "pin L (both)")
    ctx["c12a1"] = rec
    fails0, evs, spawn = chain_fails(rec, "C12a-1")
    ring_fails, sring = spawn_fails(rec, spawn, L_ID, S_ID, "C12a-1")
    print(f"EVIDENCE C12a-1: rifle={g.get('weaponId')} clip={g.get('ammoId')} H {C12A_H_TILE}/{C12A_H_DIR} S "
          f"{C12A_S_TILE}/{C12A_S_DIR} floor {C12A_FLOOR}; S staging response spawnUnit/spawnUnitFaction/respawn="
          f"{(st.get('spawnUnit'), st.get('spawnUnitFaction'), st.get('respawn'))} S staged={s_staged} stagedDiff="
          f"{staged_diff}; H's action evs={sv(evs)}; spawn={spawn and (spawn['seq'], spawn['actionId'])} its delta="
          f"{ring_view(sring)}; units={units_evidence(rec, [S_ID, H_ID, L_ID])}; items="
          f"{items_evidence(rec, [RIFLE_ID, CLIP_ID, X_ID])}; pin L={pin}; {snap_evidence(rec, 'C12a-1')}",
          flush=True)
    fails = list(notes) + fails
    if (g.get("weaponId"), g.get("ammoId")) != (RIFLE_ID, CLIP_ID):
        fails.append(f"battle_give H: rifle/clip {(g.get('weaponId'), g.get('ammoId'))} (want "
                     f"{(RIFLE_ID, CLIP_ID)})")
    if (st.get("spawnUnit"), st.get("spawnUnitFaction"), st.get("respawn")) != (L_TYPE, FACTION_HOSTILE, True):
        fails.append(f"S staging response {(st.get('spawnUnit'), st.get('spawnUnitFaction'), st.get('respawn'))} "
                     f"(want {(L_TYPE, FACTION_HOSTILE, True)})")
    if staged_diff:
        fails.append(f"buckets differ after the staging: {staged_diff} (want none)")
    fails += fails0 + ring_fails
    if sring and X_ID not in (sring.get("itemsAddedIds") or []):
        fails.append(f"C12a-1: the spawn ev's delta itemsAddedIds {sring.get('itemsAddedIds')} (want itemsAdded >= 1 "
                     f"with X {X_ID})")
    fails += unit_fails(rec, L_ID, {"type": L_TYPE, "faction": FACTION_HOSTILE, "x": C12A_S_TILE[0],
                                    "y": C12A_S_TILE[1], "z": C12A_S_TILE[2], "onTile": True, "isOut": False,
                                    "specialWeapons": [X_ID], "psiWeapon": X_ID}, "C12a-1 L")
    fails += unit_fails(rec, S_ID, {"status": STATUS_DEAD, "onTile": False}, "C12a-1 S")
    for name, it in (("host", rec["ih"].get(X_ID)), ("client", rec["ic"].get(X_ID))):
        if not it or (it.get("type"), it.get("special"), it.get("owner")) != (X_TYPE, True, L_ID):
            fails.append(f"C12a-1: item X {X_ID} on the {name} {iview(it)} (want type {X_TYPE}, special true, "
                         f"owner {L_ID})")
    if rec["itemIdCtr"][0] != rec["itemIdCtr"][1]:
        fails.append(f"C12a-1: itemIdCtr bucket host/client {rec['itemIdCtr']} (want equal: no client mint)")
    fails += context_fails(rec, "C12a-1")
    fails += common_fails(host, client, rec["before"], {}, "C12a-1")
    finish(fails)


def c12a_special_removed(host, client, ctx):
    notes = []
    fails = []
    rh, rc = both_rec(host, client, {"cmd": "battle_set_unit_state", "unit": L_ID, "spawnUnit": M_TYPE,
                                     "spawnUnitFaction": FACTION_HOSTILE, "respawn": True},
                      ("spawnUnit", "spawnUnitFaction", "respawn"), fails, "L staging (both)")
    staging = {"host": (rh.get("ok"), rh.get("spawnUnit"), rh.get("spawnUnitFaction"), rh.get("respawn"),
                        rh.get("error")),
               "client": (rc.get("ok"), rc.get("spawnUnit"), rc.get("spawnUnitFaction"), rc.get("respawn"),
                          rc.get("error"))}
    l_before = {"host": uview(units(host).get(L_ID)), "client": uview(units(client).get(L_ID))}
    x_before = {"host": iview(items(host).get(X_ID)), "client": iview(items(client).get(X_ID))}
    rec = snap(host, client, SEED_C12A2, notes)
    pin = pin_both(host, client, M_ID, fails, "pin M (both)")
    fails0, evs, spawn = chain_fails(rec, "C12a-2")
    ring_fails, sring = spawn_fails(rec, spawn, M_ID, L_ID, "C12a-2")
    x_gone = {"host": X_ID not in rec["ih"], "client": X_ID not in rec["ic"]}
    removed_in = [ring_view(r) for r in (rec["ring"] or []) if (r.get("seq") or 0) > rec["seq0"]
                  and X_ID in (r.get("itemsRemovedIds") or [])]
    print(f"EVIDENCE C12a-2: L staging (ok, spawnUnit, spawnUnitFaction, respawn, error)={staging}; L before the "
          f"snap={l_before}; X before the snap={x_before}; H's action evs={sv(evs)}; spawn="
          f"{spawn and (spawn['seq'], spawn['actionId'])} its "
          f"delta={ring_view(sring)}; deltas removing X {X_ID}={removed_in}; X gone={x_gone}; units="
          f"{units_evidence(rec, [L_ID, M_ID])}; items={items_evidence(rec, [X_ID])}; pin M={pin}; "
          f"{snap_evidence(rec, 'C12a-2')}", flush=True)
    fails = list(notes) + fails
    for name in ("host", "client"):
        xb = x_before[name]
        if not xb or (xb.get("special"), xb.get("owner")) != (True, L_ID):
            fails.append(f"C12a-2 precondition: item X {X_ID} on the {name} before the snap {xb} (want L's special "
                         f"weapon: special true, owner {L_ID})")
    fails += fails0 + ring_fails
    if sring and X_ID not in (sring.get("itemsRemovedIds") or []):
        fails.append(f"C12a-2: the spawn ev's delta itemsRemovedIds {sring.get('itemsRemovedIds')} (want X {X_ID} "
                     f"among them)")
    if not x_gone["host"] or not x_gone["client"]:
        fails.append(f"C12a-2: item X {X_ID} present after the snap host={not x_gone['host']} client="
                     f"{not x_gone['client']} (want absent on both)")
    fails += unit_fails(rec, L_ID, {"status": STATUS_DEAD, "onTile": False, "specialWeapons": [], "psiWeapon": -1},
                        "C12a-2 L")
    fails += unit_fails(rec, M_ID, {"type": M_TYPE, "faction": FACTION_HOSTILE, "x": C12A_S_TILE[0],
                                    "y": C12A_S_TILE[1], "z": C12A_S_TILE[2], "onTile": True, "isOut": False},
                        "C12a-2 M")
    if rec["itemIdCtr"][0] != rec["itemIdCtr"][1]:
        fails.append(f"C12a-2: itemIdCtr bucket host/client {rec['itemIdCtr']} (want equal: no client mint)")
    fails += context_fails(rec, "C12a-2")
    fails += common_fails(host, client, rec["before"], {}, "C12a-2")
    finish(fails)


SCENARIOS = (("C12a-1", c12a_convert), ("C12a-2", c12a_special_removed))


# ===================== bring-up =====================


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, baked "
        f"MAP_FP={MAP_FP!r} (default NEW BATTLE, SEED_MAP {SEED_MAP})")
    assert seated.get("soldierIds") == SEATED, f"seated {seated.get('soldierIds')} (baked {SEATED})"
    order = ([u["id"] for u in hs.get("units", [])], [u["id"] for u in cs.get("units", [])])
    assert order == (UNIT_ORDER, UNIT_ORDER), f"battle_state unit order host/client={order} (baked {UNIT_ORDER})"
    pinned = pin_ai_neutral(host, client, tag="w2p3-sc")
    assert pinned == [A_ID], f"pin_ai_neutral pinned {pinned} (baked [{A_ID}])"
    ih, ic = items(host), items(client)
    assert (len(ih), max(ih) + 1, len(ic), max(ic) + 1) == (FIRST_LEVER_ITEM_ID,) * 4, (
        f"items at start host n={len(ih)} max={max(ih)} client n={len(ic)} max={max(ic)} (baked "
        f"{FIRST_LEVER_ITEM_ID} items, ids 0..{FIRST_LEVER_ITEM_ID - 1})")
    for gc in (host, client):
        es = event_state(gc)
        u0 = session.units_by_id(battle_state(gc)).get(S_ID) or {}
        i0 = next(iter(items(gc).values()), {})
        assert (isinstance(es.get("deltaRing"), list) and isinstance((es.get("lastDelta") or {}), dict)
                and isinstance(es.get("closedContexts"), list) and isinstance(es.get("contextsOpened"), dict)
                and all(k in u0 for k in ("type", "originalFaction", "spawnUnit", "respawn", "specialWeapons",
                                          "psiWeapon"))
                and "special" in i0), (
            f"{gc.name} lacks the S-C.1 probes: deltaRing={es.get('deltaRing')!r} closedContexts="
            f"{es.get('closedContexts')!r} unit {S_ID} keys={sorted(u0)} item keys={sorted(i0)}")
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[w2p3-sc] boot ok: SEED_MAP={SEED_MAP} MAP_FP={MAP_FP!r} turn={hs['turn']} seated={SEATED} "
          f"order={UNIT_ORDER} pinned={pinned} items={len(ih)} probes host={ctx_probes(host)} "
          f"client={ctx_probes(client)} host deltaRing={len(ring_of(host))} entries", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49856, make_user_dir("w2p3_unit_spawn_host"))
    client = GameClient("client", 49857, make_user_dir("w2p3_unit_spawn_client"))
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
                print(f"[w2p3-sc] shutdown {gc.name}: {short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_unit_spawn: {len(passed)}/{len(SCENARIOS)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
