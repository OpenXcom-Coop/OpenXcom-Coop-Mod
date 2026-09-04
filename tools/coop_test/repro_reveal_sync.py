"""RW-REVEAL-SYNC (rewrite spike, SPIKE-RUNBOOK.md SS2.4a): fog of war is GAME
STATE - the dedicated repro.

Revealed tiles used to be treated as presentation: each machine computed its own
tile FOV and the saveBlob hash MASKED the per-tile `discovered` bits out of
binTiles so the divergence could not be seen. Owner ruling 2026-09-02 reversed
that. The host is now the sole author of `discovered` bits, ships them as
presence-gated `reveal` deltas attached at the ONE emit choke
(CoopEmit::sendEv), a thin client's own tile-FOV sweep is suppressed
(TileEngine::calculateTilesInFOV), and the fog mask is GONE from the hash - so
`hash_now full` now VERIFIES reveals instead of hiding them.

W1-P8 (WAVE1-RUNBOOK.md SS2.W4 / SS2.W5, rulings D2 / WV-D8 / WV-D31 / WV-D39)
EXTENDED THIS FILE in four directions, and the sweep is NINE buckets now:

  * DUAL-SET fog. Both machines hold BOTH sides' reveal sets. The player side is
    still the vanilla per-tile Tile bits (so SP stays bit-identical); the hostile
    side is a coop-owned byte-per-tile bitmap that never writes Tile, hashed as
    its own out-of-band bucket `revealHostile`. Every parity assert below now
    covers BOTH sets.
  * G-2. Selection no longer authors shared fog: a host TAB storm emits ZERO
    reveal evs - proved WITH an action-attributed positive control in the same
    session, so "zero" cannot be the vacuous kind.
  * WR-5 carriage + ordering. ONE `reveal` per envelope, and it is the ACTING
    side's; any other side's bits ride their OWN bt_ev{kind:"reveal"} emitted
    from the same choke immediately afterwards, in the same seq stream.
  * The NINTH bucket's own desync lever, `corrupt_bucket revealHostile`, plus a
    gm2 (PvP, client=Alien) fixture and a single-player smoke.

Seven sessions, each freshly booted (two of them deliberately break the battle):

  test_reveal_sync_e2e()      (a) 8/8 unmasked + exact fog parity BEFORE any
                                  action - i.e. the bring-up gap (the host
                                  reveals several hundred tiles after the
                                  handshake blob is snapshotted, plus the
                                  void-tile baseline the blob cannot carry at
                                  all) is closed by the quiescent flush;
                              (b) >= 10 mixed turn/kneel actions across BOTH
                                  seats, with fog parity + 8/8 after each;
                              (c) flush idempotence - once drained, further
                                  quiescent ticks emit nothing;
                              (d) an absolute `base` restate (SS2.4a's other
                                  revealDelta shape) applies cleanly and
                                  changes nothing.

  test_reveal_drop_detected() FORCED MISMATCH #1 (RB-D26 `reveal_drop` lever):
                              the host computes and PUBLISHES one delta but
                              never ships it, so the client is permanently
                              behind. Asserts the divergence is REAL (live
                              per-part counts differ, and the host has nothing
                              left unpublished, so no later delta will heal it)
                              and that the now-unmasked saveBlob bucket SEES it.

  test_reveal_base_bad_n()    FORCED MISMATCH #2 (RB-D26 `reveal_base bad_n`):
                              a `base` restate advertising the wrong `n`.
                              SS2.4a: "mismatch = desync, never partial apply" -
                              asserts freeze + bt_desync + bundle + banner, the
                              same R3-P2 mismatch pattern repro_atom_kneel.py's
                              corrupt_bucket proof uses.

  test_g2_selection_decoupled()
                              SS2.W5's G-2 proof, in two halves in ONE session:
                              (+) POSITIVE CONTROL - real ACTIONS are driven
                                  until the host is OBSERVED attaching a reveal
                                  delta, so the counter is provably live AND
                                  reveals are provably still authored;
                              (-) a host TAB/selection storm that provably
                                  CHANGES the selection emits ZERO reveal evs
                                  and does not move `lastSeqEmitted` at all.

  test_dual_side_ordering()   SS2.W4/WR-5 carriage: ONE action whose envelope
                              carries the ACTING side's `reveal` while the OTHER
                              side's bits ride their own `ev reveal` at the very
                              next seq. Ends with FORCED MISMATCH #3 -
                              `corrupt_bucket revealHostile` - which only the
                              NEW ninth bucket can see.

  test_reveal_hostile_gm2()   gm2 (PVP, ClientPlayer on the Alien team): the
                              HOSTILE set is non-empty on BOTH machines and
                              EQUAL, with all nine buckets EQUAL.

  test_reveal_sp_smoke()      SINGLE PLAYER, one instance: the SS2.W5 selection
                              gate is OFF, no hostile storage is allocated, and
                              `hash_now full` OMITS `revealHostile` entirely
                              (WR-26: key ABSENT, never zero) - i.e. the
                              player-side path is untouched by this packet.

FIXTURE: the same live 2-player skirmish + SELECTION RULE + bounded re-roll loop
repro_atom_turn.py/repro_atom_kneel.py use (REVIEW4 IR-4), reused here by inline
copy - this file's own precedent is repro_atom_kneel.py, whose precedent is
repro_atom_turn.py, whose precedent is test_rw_faction_setup.py. seat_count=2 so
the CLIENT owns two real units and the mixed burst can drive different actors.

Run:  python tools/coop_test/repro_reveal_sync.py
"""

import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, assert_reveal_parity, host_reveal_emits

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
# Raised from 5 by the WV-D5 fixture-pinning sweep: SELECTION RULE (c)
# rejects more generations than (a)+(b) did, and a re-roll is the CORRECT
# response to a fixture that cannot prove the property.
MAX_REROLLS = 15

SDLK_TAB = 9    # Options::keyBattleNextUnit default
SDLK_K = 107    # Options::keyBattleKneel default (SDLK_k, Options.cpp:337)

MIXED_ACTIONS = 10  # packet text: ">= 10 mixed turn/kneel across BOTH seats"

# W1-P8 (SS2.W4 / WV-D31): the sweep went 8 -> 9 - the 7 BattleHashSet members
# plus saveBlob plus revealHostile. Named, not hard-coded inline, because SS1's
# WAVE-1 ADDITIONS trap says a later packet must never "fix" a 9-bucket sweep
# back to 8.
BUCKETS = 9

TAB_STORM_PRESSES = 24

# SS2.6's desync row, verbatim from bin/common/Language/en-US.yml (W1-P4: the
# banner assert below is EXACT now, not "non-empty").
STR_DESYNC_HALTED_TEXT = "Desync detected - battle halted (rejoin arrives in a later build)"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top_state(gc):
    st = states(gc)
    return st[-1] if st else None


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def units_by_id(battle_state_resp):
    return {u["id"]: u for u in battle_state_resp.get("units", [])}


def skirmish_host(host, port, player="HostPlayer"):
    host.ok({"cmd": "open_new_battle"})
    host.wait_for("host new battle", lambda: session.has_state(host, "NewBattleState"))
    host.ok({"cmd": "newbattle_coop"})
    host.wait_for("host browser", lambda: session.has_state(host, "ServerList"))
    host.ok({"cmd": "server_list_host"})
    host.wait_for("host window", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": port, "player": player})
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"))


def skirmish_client_at_browser(client):
    client.ok({"cmd": "open_new_battle"})
    client.wait_for("client new battle", lambda: session.has_state(client, "NewBattleState"))
    client.ok({"cmd": "newbattle_coop"})
    client.wait_for("client browser", lambda: session.has_state(client, "ServerList"))


def bring_up_lobby(host, client, port):
    host.spawn(); host.connect()
    client.spawn(); client.connect()

    skirmish_host(host, port)
    skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: lobby(host).get("buttonVisible") or None)


# dismiss_battle_start_overlays() MOVED TO session.py by W1-P4 (harness ripple,
# IR2-1) - see the shared helper's docstring.


def drive_to_battlescape(host, client, seated_holder, seat_count=2):
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None)
    assert top_state(host) == "NewBattleState", \
        f"host should land on the NEW BATTLE setup screen, stack={states(host)}"

    soldier_ids = []
    for i in range(seat_count):
        seat_resp = host.ok({"cmd": "newbattle_seat_soldier", "seat": COOP_SEAT_1, "index": i})
        soldier_ids.append(seat_resp["soldierId"])
    seated_holder["soldierIds"] = soldier_ids

    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)

    # WV-D56 (FX-1): the snapshot/offer now move to AFTER startFirstTurn() -
    # i.e. to this click, not to newbattle_ok. "client battlescape" can only be
    # waited for AFTER it, never before (the client learns nothing until then).
    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)

    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    time.sleep(3)

    # W1-P3 (SS1 WAVE-1 ADDITIONS trap 2 / WV-D9): the client now enters the
    # battle through a read-only BriefingState pushed OVER its
    # BattlescapeState, so every fixture that DRIVES the client must dismiss
    # it explicitly - injected input would otherwise land on the briefing and
    # screen-projection probes would compute against the GEOSCAPE viewport the
    # briefing holds. No-op on a stack with no BriefingState.
    session.dismiss_client_briefing(client)


def has_door_within(gc, x, y, z, radius=2):
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            ti = gc.cmd({"cmd": "tile_info", "x": x + dx, "y": y + dy, "z": z})
            if not ti.get("ok"):
                continue
            for part in ti.get("parts", {}).values():
                if part.get("isDoor") or part.get("isUfoDoor"):
                    return True
    return False


def qualifying_actor(host, soldier_id):
    """REVIEW4 IR-4 SELECTION RULE, reused from repro_atom_turn.py: (a) no
    hostile currently spotted, (b) no door within 2 tiles of the actor.

    RULE (c) - added by the WV-D5 fixture-pinning sweep (2026-09-03). RB-D15 and
    WV-D18 require an "open-ground, no-door, NO-ENEMY-LOS" actor, and (a)+(b)
    cover only the first two: (a) asks whether a hostile is ALREADY spotted at
    t=0, which is silent on whether this actor's ROTATION will bring one into
    view. Vanilla aborts a BA_NONE turn mid-chain the moment
    getUnitsSpottedThisTurn() grows (UnitTurnBState.cpp:117). The predicate is
    session.actor_is_contact_free() - THE one shared copy (session.py).
    """
    st = host.cmd({"cmd": "battle_state"})
    if not st.get("ok") or not st.get("inBattle"):
        return None
    if st.get("spotted"):
        return None  # rule (a)
    for u in units_by_id(st).values():
        if u.get("soldierId") == soldier_id:
            if has_door_within(host, u["x"], u["y"], u["z"], radius=2):
                return None  # rule (b)
            if not session.actor_is_contact_free(st, u, "reveal_sync"):
                return None  # rule (c)
            return u
    return None


def bring_up_qualifying_battle(tag):
    """Returns (host, client, actor_unit_dict, soldier_ids)."""
    for attempt in range(1, MAX_REROLLS + 1):
        port = str(48396 + attempt)
        host_dir = make_user_dir(f"repro_reveal_{tag}_host_{attempt}")
        client_dir = make_user_dir(f"repro_reveal_{tag}_client_{attempt}")
        host = GameClient("host", 49130 + attempt * 2, host_dir)
        client = GameClient("client", 49131 + attempt * 2, client_dir)
        seated = {}
        try:
            bring_up_lobby(host, client, port)
            drive_to_battlescape(host, client, seated)

            actor = qualifying_actor(host, seated["soldierIds"][0])
            if actor is not None:
                print(f"[repro_reveal_sync/{tag}] fixture qualifies on attempt "
                      f"{attempt}/{MAX_REROLLS} (actor unit id={actor['id']}, "
                      f"pos=({actor['x']},{actor['y']},{actor['z']}))")
                return host, client, actor, seated["soldierIds"]

            print(f"[repro_reveal_sync/{tag}] re-roll {attempt}/{MAX_REROLLS}: fixture did "
                  "not qualify - tearing down and retrying")
            host.shutdown()
            client.shutdown()
        except Exception:
            host.shutdown()
            client.shutdown()
            raise

    raise RuntimeError(f"repro_reveal_sync/{tag}: no qualifying fixture in {MAX_REROLLS} boots")


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


APPLY_RE = re.compile(r"applied (add delta|base restate) at seq (\d+) \(side=(\w+)")
ATTACH_RE = re.compile(r"attached reveal delta \((\d+) tiles, side=(\w+)\) to (.+)$")


def client_reveal_applies(client):
    """Every reveal the CLIENT has applied so far, as (shape, seq, side) - the
    only place the SEQ of a reveal is observable from outside, which is what
    makes SS2.W4/WR-5's "in seq order" an assertion rather than a hope."""
    out = []
    for ln in log_lines(client):
        m = APPLY_RE.search(ln)
        if m:
            out.append((m.group(1), int(m.group(2)), m.group(3)))
    return out


def host_reveal_attaches(host):
    """Every delta the HOST has attached, as (tiles, side, carrier). `carrier`
    is the envelope it went onto - either the acting envelope itself
    ("bt_ev kind=turn") or, for a non-acting side, its OWN reveal ev."""
    out = []
    for ln in log_lines(host):
        m = ATTACH_RE.search(ln)
        if m:
            out.append((int(m.group(1)), m.group(2), m.group(3).strip()))
    return out


def assert_dual_reveal_parity(host, client, what="", samples=10, extra_positions=()):
    """SS2.W4: assert_reveal_parity's PLAYER-side layers, plus the same
    per-part equality for the HOSTILE set and for the void-tile census.

    The hostile set is coop-owned storage with no serialized representation, so
    NOTHING but this probe can see it - the saveBlob bucket cannot, and its own
    `revealHostile` bucket only says "the two 64-bit digests differ", never which
    part drifted. And `discoveredVoid` is the one number that covers the
    player-side void-tile hash hole (W1-P15 item 2): fog on tiles that are
    Tile::isVoid() on both machines is inside no bucket at all.
    """
    tag = f" {what}" if what else ""
    hr = assert_reveal_parity(host, client, what, samples=samples,
                              extra_positions=extra_positions)
    cr = client.cmd({"cmd": "reveal_state"})
    assert cr.get("ok"), f"client reveal_state unusable{tag}: {cr}"

    assert hr["hostile"]["allocated"] and cr["hostile"]["allocated"], (
        f"the HOSTILE reveal set is not allocated on both machines{tag}: "
        f"host={hr['hostile']} client={cr['hostile']}")
    assert hr["hostile"]["size"] == cr["hostile"]["size"] == hr["mapSizeXYZ"], (
        f"hostile bitmap size mismatch{tag}: host={hr['hostile']} client={cr['hostile']} "
        f"map={hr['mapSizeXYZ']}")
    for part in ("floor", "westwall", "northwall"):
        assert hr["hostile"][part] == cr["hostile"][part], (
            f"HOSTILE-side discovered {part} MISMATCH{tag}: host={hr['hostile'][part]} "
            f"client={cr['hostile'][part]} - the host's side:\"hostile\" deltas did not "
            "reach the client, or one machine authored a hostile set of its own")
        assert hr["player"][part] == cr["player"][part], (
            f"PLAYER-side discovered {part} MISMATCH{tag}: host={hr['player'][part]} "
            f"client={cr['player'][part]}")
    assert hr["discoveredVoid"] == cr["discoveredVoid"], (
        f"discoveredVoid MISMATCH{tag}: host={hr['discoveredVoid']} "
        f"client={cr['discoveredVoid']} - a fog divergence confined to VOID tiles, which "
        "no hash bucket can see (W1-P15 item 2)")
    assert hr["unpublishedHostile"] is False, (
        f"host still owes hostile-side reveal bits{tag}: {hr}")
    return hr


def host_reveal_drops(host):
    """How many times the RB-D26 `reveal_drop` lever has actually eaten a delta,
    read from the HOST's own log - the precise signal that the one-shot fired
    (it stays armed through every action that reveals nothing)."""
    try:
        with open(os.path.join(host.user_dir, "openxcom.log"), "r", errors="replace") as f:
            return sum(1 for ln in f if "reveal_drop lever fired" in ln)
    except OSError:
        return 0


def event_seq_baseline(client):
    return client.cmd({"cmd": "event_state"}).get("lastSeqApplied", 0)


def wait_settled(host, client, baseline, timeout=15):
    """queueDepth back to 0 on BOTH machines AND the client's lastSeqApplied
    past `baseline` - same contract as repro_atom_turn.py's own helper."""
    def settled():
        hs = host.cmd({"cmd": "event_state"})
        cs = client.cmd({"cmd": "event_state"})
        return bool(hs.get("ok") and cs.get("ok")
                    and hs.get("queueDepth") == 0 and cs.get("queueDepth") == 0
                    and cs.get("lastSeqApplied", 0) > baseline)
    client.wait_for("action settled (new seq applied, queueDepth 0 on both machines)",
                    settled, timeout=timeout)


def select_away_from(host, avoid_ids, max_tabs=12):
    """Tab-cycle the HOST's own selection onto a HOST-OWNED unit (coop==0) that
    is not in `avoid_ids`. Same surprise repro_atom_kneel.py documents: the
    battle's inherited initial selection is not seat-filtered and is often one
    of the fixture's client-seated soldiers."""
    for _ in range(max_tabs):
        st = host.cmd({"cmd": "battle_state"})
        sel = st.get("selectedId")
        if sel and sel not in avoid_ids:
            unit = units_by_id(st).get(sel)
            if unit and unit.get("coop") == COOP_SEAT_0:
                return sel
        host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
        time.sleep(0.1)
    raise AssertionError(f"could not select a HOST-OWNED unit outside {avoid_ids}")


def client_turn_by(host, client, actor_id, delta):
    """Turn by `delta` 45-degree steps from wherever the actor is NOW (1..7), so
    the rotation is always a real one - a 0-tick turn would cost no TU and give
    UnitTurnBState nothing to do, which is not the path this repro means to
    exercise. Returns the direction it landed on."""
    cur = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]["direction"]
    to_dir = (cur + delta) % 8
    baseline = event_seq_baseline(client)
    r = client.ok({"cmd": "battle_intent", "kind": "turn", "actor": actor_id, "toDir": to_dir})
    assert r.get("iseq"), f"battle_intent(turn) did not mint an iseq: {r}"
    wait_settled(host, client, baseline)
    got = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]["direction"]
    assert got == to_dir, f"client turn on {actor_id} landed on dir {got}, wanted {to_dir}"
    return to_dir


def client_kneel(host, client, actor_id):
    was = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]["kneeled"]
    baseline = event_seq_baseline(client)
    r = client.ok({"cmd": "battle_intent", "kind": "kneel", "actor": actor_id, "kneel": not was})
    assert r.get("iseq"), f"battle_intent(kneel) did not mint an iseq: {r}"
    wait_settled(host, client, baseline)
    now = units_by_id(client.cmd({"cmd": "battle_state"}))[actor_id]["kneeled"]
    assert now != was, f"client kneel on {actor_id} did not toggle (still {now})"


def host_kneel(host, client, host_unit_id):
    """The HOST seat's OWN local input (RB-D19 origin="host") - the other half
    of "across BOTH seats"."""
    was = units_by_id(host.cmd({"cmd": "battle_state"}))[host_unit_id]["kneeled"]
    baseline = event_seq_baseline(client)
    host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_K})
    wait_settled(host, client, baseline)
    now = units_by_id(host.cmd({"cmd": "battle_state"}))[host_unit_id]["kneeled"]
    assert now != was, f"host-local kneel on {host_unit_id} did not toggle (still {now})"


def test_reveal_sync_e2e():
    host, client, actor, soldier_ids = bring_up_qualifying_battle("e2e")
    try:
        actor_a = actor["id"]
        cs = client.cmd({"cmd": "battle_state"})
        actor_b = next(u for u in cs["units"] if u.get("soldierId") == soldier_ids[1])["id"]

        # --- (a) pre-action: unmasked 9/9 + exact fog parity, BOTH sides ---
        rs = assert_dual_reveal_parity(host, client, "pre-action (bring-up gap closed)",
                                       samples=24,
                                       extra_positions=[(actor["x"], actor["y"], actor["z"])])
        pre_h, _ = assert_hash_clean(host, client, full=True, what="pre-action")
        assert "revealHostile" in pre_h, (
            f"the ninth bucket is missing pre-action ({sorted(pre_h)}) - the hostile "
            "storage was never allocated, so WR-26 omitted it and every hostile-side "
            "assertion below would be vacuous")
        assert len(pre_h) == BUCKETS, (
            f"hash_now full returned {len(pre_h)} buckets, expected {BUCKETS} ({sorted(pre_h)})")
        assert rs["hostile"]["floor"] > 0, (
            f"the HOSTILE reveal set is empty pre-action: {rs['hostile']} - the host's "
            "coop-only hostile FOV pass authored nothing")
        # SS2.W4 BASELINE (WR-1 / WV-D39), asserted where it happens rather than
        # inferred from the equality above: the hostile set has NO save
        # representation, so it cannot ride the handshake blob - the host seeds its
        # published mirror EMPTY and ships the whole set as the FIRST ev after
        # phase Active. Without this the "hostile sets are equal" assertion could
        # be satisfied by both machines simply being empty.
        # NOTE (IR2-3): the assertion is deliberately NOT "no battle_ready
        # mismatch" - CoopHandshake::onReady does not compare `h` at all
        # (connectionTCP.cpp, "not compared at handshake"), so that would be
        # vacuous.
        entry_bases = [a for a in client_reveal_applies(client)
                       if a[0] == "base restate" and a[2] == "hostile"]
        assert entry_bases, (
            "the client never applied a side:\"hostile\" `base` restate - the SS2.W4 "
            "BASELINE never ran, so the client's hostile set was never seeded from the "
            "host at all")
        assert entry_bases[0][1] == 1, (
            f"the hostile BASELINE restate landed at seq {entry_bases[0][1]}, not seq 1 - "
            "SS2.W4/WR-1 requires it to be the host's FIRST ev after phase Active")
        print(f"PASS (a): pre-action {len(pre_h)}/{BUCKETS} buckets EQUAL (saveBlob UNMASKED "
              f"over binTiles, incl. the new revealHostile) and BOTH sides' fog identical - "
              f"player floor/west/north = {rs['floor']}/{rs['westwall']}/{rs['northwall']}, "
              f"hostile = {rs['hostile']['floor']}/{rs['hostile']['westwall']}/"
              f"{rs['hostile']['northwall']} of {rs['mapSizeXYZ']} tiles, "
              f"discoveredVoid = {rs['discoveredVoid']}")

        # --- (b) >= 10 mixed turn/kneel across BOTH seats, checked after each ---
        for i in range(MIXED_ACTIONS):
            which = i % 5
            if which == 0:
                d = client_turn_by(host, client, actor_a, 2)
                label = f"client turn A -> {d}"
            elif which == 1:
                client_kneel(host, client, actor_a)
                label = "client kneel A"
            elif which == 2:
                d = client_turn_by(host, client, actor_b, 3)
                label = f"client turn B -> {d}"
            elif which == 3:
                client_kneel(host, client, actor_b)
                label = "client kneel B"
            else:
                host_unit = select_away_from(host, {actor_a, actor_b})
                host_kneel(host, client, host_unit)
                label = f"HOST-seat kneel (unit {host_unit}, origin=host)"

            u = units_by_id(client.cmd({"cmd": "battle_state"}))
            probe = [(u[actor_a]["x"], u[actor_a]["y"], u[actor_a]["z"]),
                     (u[actor_b]["x"], u[actor_b]["y"], u[actor_b]["z"])]
            assert_dual_reveal_parity(host, client, f"after action {i + 1} ({label})",
                                      samples=10, extra_positions=probe)
            h, _ = assert_hash_clean(host, client, full=True,
                                     what=f"after action {i + 1} ({label})")
            assert len(h) == BUCKETS, \
                f"expected {BUCKETS} buckets after action {i + 1}, got {sorted(h)}"
            print(f"PASS (b) action {i + 1}/{MIXED_ACTIONS}: {label} - BOTH sides' fog "
                  f"parity + {BUCKETS}/{BUCKETS}")

        # --- (c) flush idempotence: nothing left unpublished, and further
        # quiescent ticks emit no further reveal ev ---
        emits_before = host_reveal_emits(host)
        seq_before = host.cmd({"cmd": "event_state"})["lastSeqEmitted"]
        time.sleep(2.0)  # many quiescent pump ticks
        emits_after = host_reveal_emits(host)
        seq_after = host.cmd({"cmd": "event_state"})["lastSeqEmitted"]
        assert seq_after == seq_before, (
            f"host kept emitting while idle: lastSeqEmitted {seq_before} -> {seq_after} - "
            "CoopReveal::flushQuiescent is not idempotent (it should find nothing "
            "unpublished on the second tick)")
        assert emits_after == emits_before, (
            f"host attached {emits_after - emits_before} further reveal delta(s) while idle")
        assert host.cmd({"cmd": "reveal_state"})["unpublished"] is False, \
            "host still reports unpublished reveal bits after settling"
        print(f"PASS (c): flush idempotent - 2s of quiescent ticks emitted nothing "
              f"(lastSeqEmitted stayed {seq_after}, reveal deltas stayed {emits_after})")

        # --- (d) absolute `base` restate (SS2.4a's other revealDelta shape) ---
        baseline = event_seq_baseline(client)
        host.ok({"cmd": "reveal_base"})
        wait_settled(host, client, baseline)
        assert client.cmd({"cmd": "event_state"})["desyncSeen"] is False, \
            "a VALID base restate must not desync the client"
        assert_dual_reveal_parity(host, client, "after a valid base restate")
        post_h, _ = assert_hash_clean(host, client, full=True, what="after a valid base restate")
        assert len(post_h) == BUCKETS, f"expected {BUCKETS} buckets, got {sorted(post_h)}"
        print("PASS (d): a valid absolute `base` restate applied cleanly - fog parity and "
              f"{len(post_h)}/{BUCKETS} buckets still EQUAL, no desync")

        # --- (e) the same for the HOSTILE set: SS2.W4's other `base` shape ---
        baseline = event_seq_baseline(client)
        host.ok({"cmd": "reveal_base", "side": "hostile"})
        wait_settled(host, client, baseline)
        assert client.cmd({"cmd": "event_state"})["desyncSeen"] is False, \
            "a VALID hostile base restate must not desync the client"
        rs_e = assert_dual_reveal_parity(host, client, "after a hostile base restate")
        h_e, _ = assert_hash_clean(host, client, full=True, what="after a hostile base restate")
        assert len(h_e) == BUCKETS, f"expected {BUCKETS} buckets, got {sorted(h_e)}"
        applies = client_reveal_applies(client)
        hostile_bases = [a for a in applies if a[0] == "base restate" and a[2] == "hostile"]
        assert len(hostile_bases) >= 2, (
            "the client applied fewer than two hostile `base` restates - the SS2.W4 "
            f"BASELINE one at entry and this lever's one: {applies}")
        print(f"PASS (e): a side:\"hostile\" absolute `base` restate applied cleanly at seq "
              f"{hostile_bases[-1][1]} - hostile set still "
              f"{rs_e['hostile']['floor']}/{rs_e['hostile']['westwall']}/"
              f"{rs_e['hostile']['northwall']} on both machines, {len(h_e)}/{BUCKETS} EQUAL")

        print(f"PASS test_reveal_sync_e2e: ALL scenarios (pre-action {BUCKETS}/{BUCKETS}, "
              f"{MIXED_ACTIONS} mixed actions across both seats, flush idempotence, "
              "player and hostile base restates) passed in one session")
    finally:
        host.shutdown()
        client.shutdown()


def test_reveal_drop_detected():
    """FORCED MISMATCH #1 (RB-D26 `reveal_drop`). The host computes and PUBLISHES
    one delta but never ships it. Because reveal is MONOTONE - a published bit is
    never re-sent - the client is behind FOREVER, which is exactly the failure
    class the old binTiles fog mask made invisible."""
    host, client, actor, soldier_ids = bring_up_qualifying_battle("drop")
    try:
        assert_reveal_parity(host, client, "before the drop")
        before_h, _ = assert_hash_clean(host, client, full=True, what="before the drop")

        host.ok({"cmd": "reveal_drop"})

        # The lever is a ONE-SHOT on the next NON-EMPTY delta: attachDelta()
        # checks the flag only after computeDelta() found something, so an action
        # that reveals nothing leaves it armed (verified in code, and needed here
        # - measured on this fixture, only ~2 of 10 mixed actions reveal anything
        # at all once the bring-up sweep has covered the neighbourhood). So drive
        # actions until the HOST's own log says the lever actually fired, rather
        # than assuming any particular action reveals something.
        actor_a = actor["id"]
        actor_b = next(u for u in client.cmd({"cmd": "battle_state"})["units"]
                       if u.get("soldierId") == soldier_ids[1])["id"]
        fired = False
        for i in range(24):
            try:
                if i % 3 == 2:
                    client_kneel(host, client, actor_a if (i % 6 == 2) else actor_b)
                else:
                    client_turn_by(host, client, actor_a if (i % 2 == 0) else actor_b, 1)
            except Exception as e:  # out of TU / denied - keep trying other actors
                print(f"[repro_reveal_sync/drop] action {i} skipped: {e}")
                continue
            if host_reveal_drops(host):
                fired = True
                print(f"[repro_reveal_sync/drop] reveal_drop lever fired on action {i + 1}")
                break
        assert fired, ("reveal_drop never had a non-empty delta to eat in 24 actions - the "
                       "actors revealed nothing at all, so this proof would be vacuous")

        hr = host.cmd({"cmd": "reveal_state"})
        cr = client.cmd({"cmd": "reveal_state"})
        assert (hr["floor"], hr["westwall"], hr["northwall"]) != \
               (cr["floor"], cr["westwall"], cr["northwall"]), (
            f"the lever fired but the two machines' fog still matches: host={hr} client={cr}")

        assert hr["unpublished"] is False, (
            "the dropped delta was not marked published - it would be re-sent on the next "
            f"flush and the divergence would silently heal, defeating the lever: {hr}")
        print(f"PASS drop: live fog DIVERGED and stays diverged - host floor/west/north = "
              f"{hr['floor']}/{hr['westwall']}/{hr['northwall']} vs client "
              f"{cr['floor']}/{cr['westwall']}/{cr['northwall']}, host has nothing unpublished")

        # THE POINT OF THE UNMASK: the joint hash must now SEE it. Before this
        # packet saveBlobMaskFowBinTiles zeroed exactly these bits, so a
        # host/client fog divergence produced a perfectly clean 8/8.
        hh = host.cmd({"cmd": "hash_now", "full": True})["h"]
        ch = client.cmd({"cmd": "hash_now", "full": True})["h"]
        assert hh["saveBlob"] != ch["saveBlob"], (
            "saveBlob is still EQUAL after a real fog-of-war divergence - the binTiles fog "
            f"mask is back, or the dropped delta touched only void tiles.\n  host: {hh}\n"
            f"  client: {ch}\n  fog: host={hr} client={cr}")
        other = {k: (hh[k], ch[k]) for k in hh if k != "saveBlob" and hh[k] != ch[k]}
        assert not other, (
            f"buckets other than saveBlob diverged too, so this is not a clean fog-only "
            f"proof: {other}")
        assert before_h["saveBlob"] != hh["saveBlob"], (
            "the host's own saveBlob did not move at all, so the pre/post comparison above "
            "cannot be attributed to the dropped reveal")
        print(f"PASS drop: the UNMASKED saveBlob bucket caught it (host={hh['saveBlob']} "
              f"client={ch['saveBlob']}) and every other bucket stayed EQUAL - before "
              "RW-REVEAL-SYNC this exact divergence hashed clean 8/8")
    finally:
        host.shutdown()
        client.shutdown()


def test_reveal_base_bad_n():
    """FORCED MISMATCH #2 (RB-D26 `reveal_base bad_n`). SS2.4a: a `base` restate
    whose `n` does not equal the receiver's getMapSizeXYZ() is a DESYNC - freeze
    + bt_desync + bundle + banner - and NEVER a partial apply. Same mismatch
    pattern as repro_atom_kneel.py's corrupt_bucket proof (R3-P2)."""
    host, client, actor, soldier_ids = bring_up_qualifying_battle("badn")
    try:
        assert_reveal_parity(host, client, "before the bad-n restate")
        fog_before = client.cmd({"cmd": "reveal_state"})

        host.ok({"cmd": "reveal_base", "bad_n": True})

        client.wait_for("client event_state.desyncSeen becomes true",
                        lambda: client.cmd({"cmd": "event_state"}).get("desyncSeen") or None,
                        timeout=15)
        es = client.cmd({"cmd": "event_state"})
        assert es.get("desyncSeen") is True, f"client did not latch desyncSeen: {es}"
        print("PASS bad_n: client latched desyncSeen after a base restate with a wrong n")

        # "never partial apply": the client's own fog is byte-identical to what
        # it was before the bad restate arrived.
        fog_after = client.cmd({"cmd": "reveal_state"})
        for part in ("floor", "westwall", "northwall"):
            assert fog_after[part] == fog_before[part], (
                f"the rejected base restate PARTIALLY applied: {part} went "
                f"{fog_before[part]} -> {fog_after[part]} (SS2.4a forbids this)")
        print(f"PASS bad_n: nothing was applied - client fog unchanged at "
              f"{fog_after['floor']}/{fog_after['westwall']}/{fog_after['northwall']}")

        bundle_glob = os.path.join(client.user_dir, "desync-reports", "desync-*.zip")
        bundles = glob.glob(bundle_glob)
        assert bundles, f"no desync bundle file found under {bundle_glob}"
        print(f"PASS bad_n: desync bundle written on the client: {bundles[0]}")

        with open(os.path.join(host.user_dir, "openxcom.log"), "r", errors="replace") as f:
            host_log = f.read()
        assert "bt_desync" in host_log, \
            "host log has no 'bt_desync' line - the client's report never reached the host"
        line = next(ln for ln in host_log.splitlines() if "bt_desync" in ln)
        assert "reveal" in line, (
            f"the host's bt_desync line does not name the `reveal` bucket: {line.strip()}")
        print(f"PASS bad_n: host recorded the peer report: {line.strip()}")

        # EXACT TEXT, not merely non-empty (W1-P4): coop battle ENTRY now raises
        # its own _txtCoopWait notice (the pre-battle equip freeze), so a
        # non-emptiness check would no longer prove showDesyncHalted() fired.
        banner = client.cmd({"cmd": "battle_state"}).get("coopWaitText", "")
        assert banner == STR_DESYNC_HALTED_TEXT, (
            f"client banner is {banner!r}, expected STR_COOP_DESYNC_HALTED "
            f"{STR_DESYNC_HALTED_TEXT!r} - showDesyncHalted() never fired")
        print(f"PASS bad_n: client banner shown: {banner!r}")
    finally:
        # A desync-frozen battle has no path back (SS2.8 "no partial repair").
        host.shutdown()
        client.shutdown()


def test_g2_selection_decoupled():
    """SS2.W5 / ruling D2 = WV-D8: "reveals are authored by ACTIONS and side-begin
    restates only. Selection changes / TAB must not author shared fog."

    BOTH HALVES RUN IN ONE SESSION, and the negative half is deliberately the
    second one. "The selection storm emitted ZERO reveal evs" is a statement
    about an ABSENCE, and an absence proves nothing unless the same run has
    already shown the counter moving - a dead counter, a host that stopped
    emitting entirely, or a fixture whose TAB never reached the map would all
    produce a perfectly green zero. `repro_atom_turn.py`'s run_no_reveal_case is
    the precedent; SS2.W5 made the coupling deterministic enough to afford the
    STRONGER, action-attributed form of it:

      (+) real client ACTIONS are driven until the HOST's own log is OBSERVED
          attaching a reveal delta - so reveals are provably still authored, by
          an ACTION, in this very battle, and the counter this test reads is
          provably live;
      (-) then a host TAB storm that provably CHANGES the selection at least
          twice emits no reveal delta at all and does not move `lastSeqEmitted`
          by even one - a stronger statement than "no reveal field", since it
          also rules out an empty carrier ev.
    """
    host, client, actor, soldier_ids = bring_up_qualifying_battle("g2")
    try:
        actor_a = actor["id"]
        cs = client.cmd({"cmd": "battle_state"})
        actor_b = next(u for u in cs["units"] if u.get("soldierId") == soldier_ids[1])["id"]
        assert_dual_reveal_parity(host, client, "before the G-2 proof")

        # --- (+) POSITIVE CONTROL: an ACTION authors fog -----------------------
        emits_before = host_reveal_emits(host)
        fired_on = None
        for i in range(24):
            try:
                client_turn_by(host, client, actor_a if (i % 2 == 0) else actor_b, 2)
            except Exception as e:  # out of TU / denied - keep trying the other actor
                print(f"[repro_reveal_sync/g2] action {i} skipped: {e}")
                continue
            if host_reveal_emits(host) > emits_before:
                fired_on = i + 1
                break
        assert fired_on is not None, (
            "24 client turn actions authored NO fog at all, so the selection-storm half "
            "below would be vacuous - the counter this test reads was never shown to move")
        emits_after_action = host_reveal_emits(host)
        print(f"PASS (+) positive control: an ACTION authored fog on attempt {fired_on} - "
              f"host attached reveal deltas {emits_before} -> {emits_after_action}. "
              "ACTIONS still reveal; the counter below is live.")

        assert_dual_reveal_parity(host, client, "after the positive-control action")

        # --- (-) the selection storm authors NOTHING ---------------------------
        # Settle first, so nothing already in flight can be mistaken for storm
        # traffic, and snapshot every observable the storm could move.
        time.sleep(1.5)
        rs_before = host.cmd({"cmd": "reveal_state"})
        emits_pre_storm = host_reveal_emits(host)
        seq_pre_storm = host.cmd({"cmd": "event_state"})["lastSeqEmitted"]
        assert rs_before["unpublished"] is False, (
            f"host still owes reveal bits before the storm, so the storm's own "
            f"contribution could not be isolated: {rs_before}")

        seen_selection = []
        for _ in range(TAB_STORM_PRESSES):
            sel = host.cmd({"cmd": "battle_state"}).get("selectedId")
            if sel is not None and (not seen_selection or seen_selection[-1] != sel):
                seen_selection.append(sel)
            host.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
            time.sleep(0.12)
        sel = host.cmd({"cmd": "battle_state"}).get("selectedId")
        if sel is not None and (not seen_selection or seen_selection[-1] != sel):
            seen_selection.append(sel)
        # THE STORM'S OWN PREMISE. A TAB storm that never actually changed the
        # selection would make the zero below meaningless for a second reason.
        assert len(set(seen_selection)) >= 2, (
            f"the TAB storm never changed the host's selection ({seen_selection}) - it "
            "was swallowed by an overlay or the fixture has one selectable unit, so this "
            "assertion would prove nothing")

        # Give the quiescent flush many ticks to publish anything the storm might
        # have authored. Without this the zero could just mean "not yet".
        time.sleep(2.5)

        emits_post_storm = host_reveal_emits(host)
        seq_post_storm = host.cmd({"cmd": "event_state"})["lastSeqEmitted"]
        rs_after = host.cmd({"cmd": "reveal_state"})

        assert emits_post_storm == emits_pre_storm, (
            f"the host attached {emits_post_storm - emits_pre_storm} reveal delta(s) during "
            f"a {TAB_STORM_PRESSES}-press TAB storm - selection is authoring shared fog "
            "again (SS2.W5 / D2)")
        assert seq_post_storm == seq_pre_storm, (
            f"lastSeqEmitted moved {seq_pre_storm} -> {seq_post_storm} during the TAB storm - "
            "the storm emitted evs even if they carried no reveal field")
        for part in ("floor", "westwall", "northwall"):
            assert rs_after[part] == rs_before[part], (
                f"the host's own {part} count moved {rs_before[part]} -> {rs_after[part]} "
                "during a pure selection storm - a selection change authored tile FOV")
            assert rs_after["hostile"][part] == rs_before["hostile"][part], (
                f"the hostile set's {part} count moved during a pure selection storm")
        assert rs_after["coopSuppressSelectionFov"] is True, (
            "the SS2.W5 selection-FOV gate reports itself OFF inside a co-op battle: "
            f"{rs_after}")
        print(f"PASS (-) G-2: {TAB_STORM_PRESSES} TAB presses over "
              f"{len(set(seen_selection))} distinct selections emitted ZERO reveal evs "
              f"(deltas stayed {emits_post_storm}, lastSeqEmitted stayed {seq_post_storm}) "
              "and moved no fog counter on either side's set")

        assert_dual_reveal_parity(host, client, "after the selection storm")
        # SS1's WAVE-1 ADDITIONS trap: a NEW assertion says "ALL buckets EQUAL",
        # never a hard-coded count. assert_hash_clean already proves the two key
        # SETS are identical and every value matches; naming the new bucket is what
        # keeps that from being vacuous if the bucket silently disappeared.
        h, _ = assert_hash_clean(host, client, full=True, what="after the selection storm")
        assert "revealHostile" in h, f"the revealHostile bucket vanished: {sorted(h)}"
        print(f"PASS test_g2_selection_decoupled: positive control + zero-ev storm, all "
              f"{len(h)} buckets EQUAL throughout (incl. revealHostile)")
    finally:
        host.shutdown()
        client.shutdown()


def test_dual_side_ordering():
    """SS2.W4 / WR-5: "ONE `reveal` PER ENVELOPE... the attached `reveal` is the
    ACTING side's; any OTHER side's pending bits ship as their own
    `bt_ev{kind:"reveal", reveal:{side:...}}` emitted from the same choke
    immediately afterwards, in the same seq stream."

    ARRANGING THE PREMISE, honestly. Wave 1 has no alien turn (WV-D25), so
    nothing in a wave-1 fixture can MOVE an alien, and a forced re-sweep of an
    unmoved alien discovers nothing new. The RB-D26 lever
    `reveal_hostile_pass {"republish": true}` therefore makes the host FORGET
    what the hostile side has already published, ARMED so that it fires inside
    the NEXT emit rather than on the next pump tick. It changes no live state on
    either machine - reveal is monotone, so the client re-applies bits it already
    holds - and leaves every bucket where it was. What is then observed is
    entirely real product behaviour: WHICH envelope carries WHICH side, and in
    what seq order.

    Ends with FORCED MISMATCH #3: `corrupt_bucket revealHostile` on the CLIENT.
    It is last because it permanently diverges the hostile set (poked straight
    into coop storage, bypassing emit, so no later delta heals it), and it is
    poked on the CLIENT for exactly that reason - on the HOST the corrupted bits
    would become "live but unpublished" and the very next delta would ship them.
    """
    host, client, actor, soldier_ids = bring_up_qualifying_battle("dual")
    try:
        actor_a = actor["id"]
        cs = client.cmd({"cmd": "battle_state"})
        actor_b = next(u for u in cs["units"] if u.get("soldierId") == soldier_ids[1])["id"]
        assert_dual_reveal_parity(host, client, "before the WR-5 carriage proof")

        pair = None
        for i in range(16):
            seen = len(client_reveal_applies(client))
            attaches = len(host_reveal_attaches(host))
            host.ok({"cmd": "reveal_hostile_pass", "republish": True})
            try:
                client_turn_by(host, client, actor_a if (i % 2 == 0) else actor_b, 2)
            except Exception as e:
                print(f"[repro_reveal_sync/dual] action {i} skipped: {e}")
                continue
            # client_turn_by() already waited for the action to settle; this extra
            # beat lets the FOLLOW-UP ev (the non-acting side's own reveal, emitted
            # from the same choke right after the action's envelope) land and be
            # applied before the client log is read.
            time.sleep(1.2)
            new_applies = client_reveal_applies(client)[seen:]
            new_attaches = host_reveal_attaches(host)[attaches:]
            players = [a for a in new_applies if a[2] == "player"]
            hostiles = [a for a in new_applies if a[2] == "hostile"]
            if players and hostiles:
                pair = (players[-1], hostiles[-1], new_attaches)
                print(f"[repro_reveal_sync/dual] both sides revealed on action {i + 1}")
                break
            print(f"[repro_reveal_sync/dual] action {i + 1}: applies={new_applies} - "
                  "no player-side reveal on that envelope, retrying")
        assert pair is not None, (
            "16 actions never produced a single action that revealed for BOTH sides, so "
            "the WR-5 carriage assertion has no premise to stand on")

        player_apply, hostile_apply, attaches = pair
        # (1) SEQ ORDER: the other side's ev is the very NEXT seq after the acting
        # side's envelope - "immediately afterwards, in the same seq stream".
        assert hostile_apply[1] == player_apply[1] + 1, (
            f"the hostile reveal did not immediately follow the acting envelope: "
            f"player at seq {player_apply[1]}, hostile at seq {hostile_apply[1]} "
            f"(applies: {client_reveal_applies(client)[-6:]})")
        # (2) CARRIAGE: the acting side rode the ACTION's own envelope, the other
        # side rode an ev of its own. One `reveal` per envelope, never an array.
        acting_carriers = [a for a in attaches if a[1] == "player"]
        other_carriers = [a for a in attaches if a[1] == "hostile"]
        assert acting_carriers and "kind=turn" in acting_carriers[-1][2], (
            f"the ACTING side's delta did not ride the action's own envelope: {attaches}")
        assert other_carriers and "OWN bt_ev" in other_carriers[-1][2], (
            f"the non-acting side's delta did not ride its own reveal ev: {attaches}")
        print(f"PASS WR-5: acting side (player, {acting_carriers[-1][0]} tiles) on the "
              f"action's own envelope at seq {player_apply[1]}; the other side (hostile, "
              f"{other_carriers[-1][0]} tiles) on its OWN bt_ev at seq {hostile_apply[1]}")

        assert_dual_reveal_parity(host, client, "after the dual-side action")
        h, _ = assert_hash_clean(host, client, full=True, what="after the dual-side action")
        assert "revealHostile" in h, f"the revealHostile bucket vanished: {sorted(h)}"
        print(f"PASS: all {len(h)} buckets still EQUAL after an action that revealed for "
              "both sides")

        # --- FORCED MISMATCH #3: only the NINTH bucket can see this -----------
        before_h = h
        assert client.ok({"cmd": "corrupt_bucket", "name": "revealHostile"}).get("ok"), \
            "corrupt_bucket revealHostile was refused - the lever does not know the bucket"
        hh = host.cmd({"cmd": "hash_now", "full": True})["h"]
        ch = client.cmd({"cmd": "hash_now", "full": True})["h"]
        assert hh["revealHostile"] != ch["revealHostile"], (
            f"the hostile set was corrupted on the client and revealHostile is still EQUAL "
            f"(host={hh['revealHostile']} client={ch['revealHostile']}) - the new bucket "
            "does not actually hash the coop bitmap")
        other = {k: (hh[k], ch[k]) for k in hh if k != "revealHostile" and hh[k] != ch[k]}
        assert not other, (
            f"buckets other than revealHostile diverged too, so this is not a clean "
            f"hostile-fog-only proof: {other}")
        assert before_h["revealHostile"] == hh["revealHostile"], (
            "the HOST's own revealHostile moved, so the divergence cannot be attributed "
            "to the client-side poke")
        hr = host.cmd({"cmd": "reveal_state"})
        cr = client.cmd({"cmd": "reveal_state"})
        assert (hr["hostile"]["floor"], hr["hostile"]["westwall"], hr["hostile"]["northwall"]) \
            != (cr["hostile"]["floor"], cr["hostile"]["westwall"], cr["hostile"]["northwall"]), (
            f"corrupt_bucket revealHostile changed the digest but not the census - "
            f"host={hr['hostile']} client={cr['hostile']}")
        print(f"PASS corrupt_bucket revealHostile: the NINTH bucket caught it "
              f"(host={hh['revealHostile']} client={ch['revealHostile']}) and every other "
              "bucket stayed EQUAL - before W1-P8 this divergence was hashed by nothing")
    finally:
        host.shutdown()
        client.shutdown()


def bring_up_gm2_lobby(host, client, port):
    """test_rw_faction_setup.py's gm2 drive: the same skirmish lobby flow, with
    ClientPlayer moved to the Alien team BEFORE BATTLE SETTINGS, which is what
    makes assignSeatsAndFactions() produce gamemode 2 (host = X-Com at seat 0,
    client = the mission's real aliens at seat 1)."""
    bring_up_lobby(host, client, port)
    names = lobby(host).get("players", [])
    row = next(i for i, n in enumerate(names) if "ClientPlayer" in n)
    r = host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"})
    assert r.get("gamemode") == 2, f"expected gamemode 2 (PVP, client=Alien), got {r}"
    time.sleep(1)  # let the change_team broadcast settle (pvp_fixture.py precedent)


def test_reveal_hostile_gm2():
    """SS2.W4's gm2 clause: with a seat actually COMMANDING the hostile side, the
    HOSTILE reveal set must be non-empty on BOTH machines and EQUAL - which is
    what makes "both machines hold both sides' sets, both synced, both inside the
    hash" a measured fact rather than a design intention.

    No actions are driven here (wave 1 streams no alien turn - WV-D25/IR2-9), so
    this fixture needs no actor pinning: it reads state only.
    """
    port = "48420"
    host_dir = make_user_dir("repro_reveal_gm2_host")
    client_dir = make_user_dir("repro_reveal_gm2_client")
    host = GameClient("host", 49180, host_dir)
    client = GameClient("client", 49181, client_dir)
    try:
        bring_up_gm2_lobby(host, client, port)

        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings",
                      lambda: (not session.has_state(host, "LobbyMenu")) or None)
        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=30)
        # WV-D56 (FX-1): snapshot/offer move to AFTER startFirstTurn() - i.e.
        # to this click. "client battlescape" can only be waited for AFTER it.
        host.ok({"cmd": "click_widget", "match": "ok"})
        host.wait_for("host battlescape",
                      lambda: session.has_state(host, "BattlescapeState"), timeout=30)
        session.dismiss_battle_start_overlays(host)
        client.wait_for("client battlescape",
                        lambda: session.has_state(client, "BattlescapeState"), timeout=60)
        time.sleep(3)
        session.dismiss_client_briefing(client)
        time.sleep(2)

        hs = host.cmd({"cmd": "battle_state"})
        assert hs.get("coopGamemode") == 2, \
            f"host battle_state.coopGamemode={hs.get('coopGamemode')}, expected 2 (gm2)"
        hostiles = [u for u in hs.get("units", []) if u.get("faction") == 1]
        assert hostiles, "gm2 fixture generated no FACTION_HOSTILE units at all"

        rs = assert_dual_reveal_parity(host, client, "gm2 entry")
        assert rs["hostile"]["floor"] > 0, (
            f"gm2: the HOSTILE reveal set is EMPTY on the host ({rs['hostile']}) with "
            f"{len(hostiles)} alien(s) on the map - the coop-only hostile FOV pass never "
            "authored anything, so every hostile-side assertion in this wave is vacuous")
        h, _ = assert_hash_clean(host, client, full=True, what="gm2 entry")
        assert "revealHostile" in h, \
            f"gm2: the revealHostile bucket is missing, got {sorted(h)}"
        print(f"PASS gm2: {len(hostiles)} alien(s) commanded by seat 1; hostile reveal set "
              f"floor/west/north = {rs['hostile']['floor']}/{rs['hostile']['westwall']}/"
              f"{rs['hostile']['northwall']} of {rs['mapSizeXYZ']} tiles, NON-EMPTY and "
              f"EQUAL on both machines, all {len(h)} buckets EQUAL")
    finally:
        host.shutdown()
        client.shutdown()


def test_reveal_sp_smoke():
    """SINGLE PLAYER, ONE instance: the packet's "SP smoke proves the player-side
    path bit-identical".

    Three things are asserted, and together they cover both halves of this
    packet's SP promise:
      * SS2.W5's selection-FOV gate reports itself OFF (`coopSuppressSelectionFov`
        is `isCoopBattle()`, which is false here) - so `updateSoldierInfo(true)`
        still runs vanilla's full `calculateFOV(selectedUnit)`, tiles included;
      * no hostile storage is allocated and `hash_now {full:true}` OMITS
        `revealHostile` entirely - WR-26's "key ABSENT, not zero";
      * a real SP battle boots, reveals fog, and survives a TAB storm with its
        fog monotone (reveal never goes backwards).
    """
    gc = GameClient("sp", 48796, make_user_dir("repro_reveal_sp"))
    try:
        gc.spawn()
        gc.connect()
        gc.ok({"cmd": "open_new_battle"})
        gc.wait_for("new battle screen", lambda: session.has_state(gc, "NewBattleState"))
        gc.ok({"cmd": "newbattle_ok"})
        gc.wait_for("briefing", lambda: session.has_state(gc, "BriefingState"), timeout=120)
        gc.ok({"cmd": "close_briefing"})
        gc.wait_for("battlescape", lambda: session.has_state(gc, "BattlescapeState"), timeout=120)
        session.dismiss_battle_start_overlays(gc, timeout=30)

        rs = gc.cmd({"cmd": "reveal_state"})
        assert rs.get("ok"), f"reveal_state failed in SP: {rs}"
        assert rs["coopSuppressSelectionFov"] is False, (
            "the SS2.W5 selection-FOV suppression is ACTIVE in single player - the coop "
            f"guard leaked out of a co-op battle and SP is no longer bit-identical: {rs}")
        assert rs["hostile"]["allocated"] is False, (
            f"SP allocated coop hostile reveal storage: {rs['hostile']}")
        assert rs["floor"] > 0, f"SP battle revealed no fog at all: {rs}"
        assert rs["unpublished"] is False and rs["hostSim"] is False

        h = gc.cmd({"cmd": "hash_now", "full": True})["h"]
        assert "revealHostile" not in h, (
            f"SP's hash_now full carries revealHostile ({sorted(h)}) - WR-26 requires the "
            "key to be ABSENT, not zero, wherever the coop storage is unallocated")
        assert h, f"SP hash_now full returned nothing: {h}"

        before = (rs["floor"], rs["westwall"], rs["northwall"])
        for _ in range(8):
            gc.ok({"cmd": "inject_input", "kind": "key", "key": SDLK_TAB})
            time.sleep(0.12)
        time.sleep(0.5)
        rs2 = gc.cmd({"cmd": "reveal_state"})
        after = (rs2["floor"], rs2["westwall"], rs2["northwall"])
        assert all(a >= b for a, b in zip(after, before)), (
            f"SP fog went BACKWARDS across a TAB storm: {before} -> {after}")
        assert rs2["coopSuppressSelectionFov"] is False
        assert gc.cmd({"cmd": "battle_state"})["inBattle"], "SP battle fell over"
        print(f"PASS SP smoke: selection-FOV gate OFF, no hostile storage, "
              f"{len(h)} buckets with revealHostile ABSENT, fog "
              f"{before} -> {after} across a TAB storm, discoveredVoid={rs2['discoveredVoid']}")
    finally:
        gc.shutdown()


def main():
    test_reveal_sync_e2e()
    test_g2_selection_decoupled()
    test_dual_side_ordering()
    test_reveal_hostile_gm2()
    test_reveal_sp_smoke()
    test_reveal_drop_detected()
    test_reveal_base_bad_n()
    print("ALL RW-REVEAL-SYNC TESTS PASSED")


if __name__ == "__main__":
    main()
