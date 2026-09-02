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

Three sessions, each freshly booted (the last two deliberately break the battle):

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

FIXTURE: the same live 2-player skirmish + SELECTION RULE + bounded re-roll loop
repro_atom_turn.py/repro_atom_kneel.py use (REVIEW4 IR-4), reused here by inline
copy - this file's own precedent is repro_atom_kneel.py, whose precedent is
repro_atom_turn.py, whose precedent is test_rw_faction_setup.py. seat_count=2 so
the CLIENT owns two real units and the mixed burst can drive different actors.

Run:  python tools/coop_test/repro_reveal_sync.py
"""

import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import assert_hash_clean, assert_reveal_parity, host_reveal_emits

COOP_SEAT_0 = 0
COOP_SEAT_1 = 1
MAX_REROLLS = 5

SDLK_TAB = 9    # Options::keyBattleNextUnit default
SDLK_K = 107    # Options::keyBattleKneel default (SDLK_k, Options.cpp:337)

MIXED_ACTIONS = 10  # packet text: ">= 10 mixed turn/kneel across BOTH seats"

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
    client.wait_for("client battlescape",
                    lambda: session.has_state(client, "BattlescapeState"), timeout=60)
    time.sleep(3)

    host.ok({"cmd": "click_widget", "match": "ok"})
    host.wait_for("host battlescape",
                  lambda: session.has_state(host, "BattlescapeState"), timeout=30)
    session.dismiss_battle_start_overlays(host)

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
    hostile currently spotted, (b) no door within 2 tiles of the actor."""
    st = host.cmd({"cmd": "battle_state"})
    if not st.get("ok") or not st.get("inBattle"):
        return None
    if st.get("spotted"):
        return None  # rule (a)
    for u in units_by_id(st).values():
        if u.get("soldierId") == soldier_id:
            if has_door_within(host, u["x"], u["y"], u["z"], radius=2):
                return None  # rule (b)
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

        # --- (a) pre-action: unmasked 8/8 + exact fog parity ---
        rs = assert_reveal_parity(host, client, "pre-action (bring-up gap closed)",
                                  extra_positions=[(actor["x"], actor["y"], actor["z"])])
        pre_h, _ = assert_hash_clean(host, client, full=True, what="pre-action")
        assert len(pre_h) == 8, (
            f"hash_now full returned {len(pre_h)} buckets, expected 8 ({sorted(pre_h)})")
        print(f"PASS (a): pre-action {len(pre_h)}/8 buckets EQUAL (saveBlob UNMASKED over "
              f"binTiles) and fog of war identical - floor/west/north = {rs['floor']}/"
              f"{rs['westwall']}/{rs['northwall']} of {rs['mapSizeXYZ']} tiles")

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
            assert_reveal_parity(host, client, f"after action {i + 1} ({label})",
                                 samples=10, extra_positions=probe)
            h, _ = assert_hash_clean(host, client, full=True,
                                     what=f"after action {i + 1} ({label})")
            assert len(h) == 8, f"expected 8 buckets after action {i + 1}, got {sorted(h)}"
            print(f"PASS (b) action {i + 1}/{MIXED_ACTIONS}: {label} - fog parity + 8/8")

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
        assert_reveal_parity(host, client, "after a valid base restate")
        post_h, _ = assert_hash_clean(host, client, full=True, what="after a valid base restate")
        assert len(post_h) == 8, f"expected 8 buckets, got {sorted(post_h)}"
        print("PASS (d): a valid absolute `base` restate applied cleanly - fog parity and "
              f"{len(post_h)}/8 buckets still EQUAL, no desync")

        print("PASS test_reveal_sync_e2e: ALL scenarios (pre-action 8/8, "
              f"{MIXED_ACTIONS} mixed actions across both seats, flush idempotence, "
              "base restate) passed in one session")
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


def main():
    test_reveal_sync_e2e()
    test_reveal_drop_detected()
    test_reveal_base_bad_n()
    print("ALL RW-REVEAL-SYNC TESTS PASSED")


if __name__ == "__main__":
    main()
