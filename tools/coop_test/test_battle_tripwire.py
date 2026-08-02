"""PRD-P2: the battlescape drift tripwire.

INV being instrumented: after every replicated action host and peer hold identical
(id -> BattleItem) maps AND equal SavedBattleGame::_itemId counters. It is true at
generation (both machines generate the same battle deterministically) and it is the
first thing to drift once they simulate independently - a peer-side `new BattleItem`,
an un-scoped transient mint, a lost item.

P2 makes that invariant OBSERVABLE, two ways:

  3a  SharedEcon::attachWorldChecksum stamps chkBattleItemId / chkBattleCensus
      whenever a battle is live, so the harness' `shared_checksum` hook and
      `battle_state` expose both terms (session.battle_checksum /
      session.assert_battle_synced).
  3b  The host stamps the same two terms on the per-turn `next_turn` packet and the
      client compares them. A mismatch logs, notifies once per RESYNC_DEBOUNCE_MS
      through the in-battle warning banner, and raises `desyncSeen` - and does
      NOTHING else. It must never trigger the world restream: that replaces the
      whole state stack, which mid-battle means destroying the running battle.

What this test asserts:

  1. The terms exist, are non-negative and AGREE the moment the battle is up - on
     `battle_state` AND on the `shared_checksum` hook (3a), where they must appear
     only because a battle is live.
  2. Scripted actions keep them agreeing. Walks only, deliberately: an attack can
     legitimately mint items (a kill converts the unit and creates a corpse -
     Tier-A id-manifest work, PRD-P4), so a shot here would test P4's gaps, not
     P2's detector.
  3. Across a full turn cycle - the only thing that makes a `next_turn` packet
     cross - the tripwire agrees with ground truth: silent while the two term
     pairs are equal (the no-false-positive criterion), and if the battle drifted
     on its own during the alien turn (a real pre-existing engine gap, not
     something this test injected) then it must have FIRED. Asserting agreement
     with ground truth instead of blind silence is what keeps this test honest
     without making it flaky.
  4. Forced divergence: an uneven `battle_give` - one machine only - moves both
     terms apart. Within one turn the client's tripwire fires, and the battle is
     still live, still on the battlescape, and still playable (a walk driven after
     the fire still replicates), with no resync request sent.

The divergence lever is a TEST-ONLY use of an existing harness command; no
divergence mechanism ships in the game.

Battle fixture: the skirmish flow (NEW BATTLE > COOP), same path as
test_parallel_replay_decouple.py / test_skirmish_battle_turn_control.py.

Run:  python tools/coop_test/test_battle_tripwire.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as SK

PORT = "47979"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def has(gc, name):
    return any(name in s for s in states(gc))


def top(gc):
    return states(gc)[-1].split("::")[-1]


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def unit(b, uid):
    for u in b.get("units", []):
        if u["id"] == uid:
            return u
    return None


def pos(b, uid):
    u = unit(b, uid)
    return (u["x"], u["y"], u["z"]) if u else None


def terms(gc):
    return session.battle_checksum(gc)


def desync_seen(gc):
    b = battle(gc)
    assert "desyncSeen" in b, (
        f"battle_state carries no 'desyncSeen' - PRD-P2's tripwire flag is missing, "
        f"every assertion below would be vacuous: {sorted(b)}")
    return b["desyncSeen"]


def wait_until(fn, timeout, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ---- fixture ---------------------------------------------------------------

def drain_to_tactical(host, client, rounds=12):
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        time.sleep(1.0)
        if not moved and all(top(gc) == "BattlescapeState" for gc in (host, client)):
            return


def bring_up_battle(host, client):
    SK.skirmish_host(host, PORT)
    SK.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": PORT,
               "player": "ClientPlayer"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} join popup",
                    lambda gc=gc: session.has_state(gc, "Profile") or None, timeout=60)
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("BATTLE SETTINGS offered",
                  lambda: SK.lobby(host).get("buttonVisible") or None, timeout=60)
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None, timeout=60)
    host.ok({"cmd": "newbattle_ok"})

    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} in battle",
                    lambda gc=gc: battle(gc).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        if has(gc, "BriefingState"):
            gc.cmd({"cmd": "close_briefing"})
    for gc in (host, client):
        if has(gc, "InventoryState"):
            gc.cmd({"cmd": "battle_inventory", "action": "ok"})
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} tactical map",
                    lambda gc=gc: has(gc, "BattlescapeState") or None,
                    timeout=120, interval=0.5)
    drain_to_tactical(host, client)
    # nothing replicates at all until the co-op turn-init handshake has run
    for gc, tag in ((host, "host"), (client, "client")):
        gc.wait_for(f"{tag} co-op battle init",
                    lambda gc=gc: battle(gc).get("battleInit") or None,
                    timeout=90, interval=1.0)
    time.sleep(3)


# ---- driving ---------------------------------------------------------------

def drive_walk(driver, watcher, mover_id):
    """Walk `mover_id` one tile on the driver and wait for the WATCHER to mirror
    it, so the action provably crossed. Returns (before, landed)."""
    before = pos(battle(driver), mover_id)
    dest = None
    driver.cmd({"cmd": "battle_action", "action": "select", "unit": mover_id})
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        want = (before[0] + dx, before[1] + dy, before[2])
        r = driver.cmd({"cmd": "battle_action", "action": "move", "unit": mover_id,
                        "x": want[0], "y": want[1], "z": want[2]})
        if r.get("ok"):
            dest = want
            break
    assert dest, f"unit {mover_id} could not step to any adjacent tile"
    assert wait_until(lambda: pos(battle(driver), mover_id) != before, 45), \
        f"unit {mover_id} never moved on the driver - the DRIVER failed"
    landed = pos(battle(driver), mover_id)
    assert wait_until(lambda: pos(battle(watcher), mover_id) == landed, 45), \
        (f"the walk never replicated: driver has {mover_id} at {landed}, watcher at "
         f"{pos(battle(watcher), mover_id)}")
    return before, landed


def pick_driver(host, client):
    hb, cb = battle(host), battle(client)
    if session.can_drive(hb):
        return host, client, "host", "client", hb
    return client, host, "client", "host", cb


def movers(state, own_coop):
    return [u for u in state["units"]
            if u.get("faction") == 0 and u.get("selectable") and not u.get("isOut")
            and u.get("coop") == own_coop and u.get("tu", 0) > 20]


def cycle_turn(host, client, timeout=300):
    """Run the battle forward by one FULL turn - the only event that makes the host
    ship a `next_turn` packet (NextTurnState::close, host + FACTION_PLAYER).

    Co-op splits the player side: whoever is active presses END TURN, which hands
    over (PlayerTurnYour) rather than ending the game turn; only after BOTH players
    have passed does the alien side run and the turn number advance.
    """
    start = battle(host).get("turn")
    deadline = time.time() + timeout
    stalled = {}
    while time.time() < deadline:
        for gc in (host, client):
            b = battle(gc)
            if not b.get("inBattle"):
                return None  # battle ended under us
            state = top(gc)
            # The HOST's NextTurnState must close ITSELF. `dismiss_popup`
            # generic-pops it (TestServer: "just pop it to reach the tactical
            # map"), which skips NextTurnState::close() - and close() is where the
            # host BUILDS AND SENDS the `next_turn` packet the tripwire rides on.
            # skipNextTurnScreen (host only, see main()) closes it through the real
            # path after NEXT_TURN_DELAY.
            if state == "NextTurnState":
                if gc is host:
                    first = stalled.setdefault(id(gc), time.time())
                    if time.time() - first > 25:
                        print("NOTE: the host's NextTurnState did not self-close in "
                              "25s (a turn message suppresses the auto-close timer); "
                              "popping it, so THIS turn ships no `next_turn` stamp")
                        gc.cmd({"cmd": "dismiss_popup"})
                        stalled.pop(id(gc), None)
                    continue
                # The CLIENT pops it the way every other test does. Its own close()
                # ships nothing, and letting its auto-close timer run would race the
                # host's `click_close` (which also calls close(), from think()) -
                # two closes, two popState()s, one shredded battle stack.
                gc.cmd({"cmd": "dismiss_popup"})
                continue
            stalled.pop(id(gc), None)
            # BattlescapeState::think() drives the co-op turn handshake and only
            # ticks while the battlescape is the TOP state, so drain the infobox
            # popups the end-turn puts up. Never dismiss the battlescape itself
            # (session.NO_DISMISS_STATES).
            if state != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                continue
            if b.get("coopTurn") == 2 and session.can_drive(b):
                gc.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        now = battle(host).get("turn")
        if now is not None and start is not None and now > start:
            return now
        time.sleep(1.0)
    return False


def report(host, client, what):
    h, c = terms(host), terms(client)
    print(f"    {what}: host itemId={h[0]} census={h[1]} | "
          f"client itemId={c[0]} census={c[1]} | "
          f"desyncSeen host={desync_seen(host)} client={desync_seen(client)}")
    return h, c


def main():
    # skipNextTurnScreen, HOST ONLY: the "Turn N" screen then closes through
    # NextTurnState::close() on a 500 ms timer instead of waiting for a click, and
    # close() is where the host builds and ships the `next_turn` packet carrying the
    # tripwire stamp - without it this test could never fire 3b.
    #
    # NOT on the client: the client's hostile-side screen is already closed by the
    # host's `click_close` packet (NextTurnState::think -> _onClickClose -> close()),
    # and think() runs the auto-close timer straight afterwards, so a client with the
    # option on can close the SAME state twice - two popState()s, the second taking
    # the battlescape with it. That is a pre-existing co-op/option interaction, not
    # something P2 touches; the test simply does not walk into it.
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = GameClient("host", 48850,
                      make_user_dir("p2_tripwire_host",
                                    options=dict(opts, skipNextTurnScreen=True)))
    client = GameClient("client", 48851, make_user_dir("p2_tripwire_client", options=opts))
    fail = None
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()
        bring_up_battle(host, client)
        print("battle up on both machines")

        # --- 1. the terms exist, are real, and agree at generation -------------
        base = session.assert_battle_synced(host, client, "at battle start")
        assert base[0] > 0 and base[1] > 0, (
            f"the battle drift terms look empty at battle start: {base} - a "
            f"generated battle always holds items and has minted ids")
        assert not desync_seen(host) and not desync_seen(client), \
            "the tripwire is already latched before anything happened"
        print(f"PASS terms: itemIdCounter={base[0]} battleCensus={base[1]} agree on "
              f"both machines, tripwire clear")

        # 3a: the same two terms must ride the world checksum whenever a battle is
        # live, which is what puts them on the `shared_checksum` hook for free.
        for gc, tag in ((host, "host"), (client, "client")):
            chk = gc.cmd({"cmd": "shared_checksum"})
            for key in ("chkBattleItemId", "chkBattleCensus"):
                assert key in chk, (
                    f"{tag}'s shared_checksum carries no {key!r} while a battle is "
                    f"live - PRD-P2 3a did not reach attachWorldChecksum: "
                    f"{sorted(chk)}")
            assert (chk["chkBattleItemId"], chk["chkBattleCensus"]) == base, (
                f"{tag}'s shared_checksum battle terms "
                f"({chk['chkBattleItemId']}, {chk['chkBattleCensus']}) disagree with "
                f"its own battle_state {base} - two readings of one battle")
        print("PASS 3a: both machines stamp chkBattleItemId / chkBattleCensus on the "
              "world checksum while a battle is live")

        # --- 2. scripted actions keep the two machines in agreement -----------
        driver, watcher, dtag, wtag, db = pick_driver(host, client)
        print(f"simulation owner = {dtag}")
        own_coop = 0 if db["host"] else 1
        mine = movers(battle(driver), own_coop)
        assert mine, (f"{dtag} commands no unit with TU to spend: "
                      f"{[(u['id'], u.get('coop'), u.get('selectable'), u.get('tu')) for u in db['units']]}")
        mover_id = mine[0]["id"]
        for step in (1, 2, 3):
            before, landed = drive_walk(driver, watcher, mover_id)
            session.assert_battle_synced(host, client, f"after walk #{step}")
            print(f"PASS walk #{step}: {dtag} moved {mover_id} {before} -> {landed}, "
                  f"terms still equal")
        assert not desync_seen(host) and not desync_seen(client), \
            "the tripwire fired although the two machines still agree"

        # --- 3. a full turn: the tripwire agrees with ground truth -------------
        turn = cycle_turn(host, client)
        assert turn, (f"the battle never reached a new turn (turn="
                      f"{battle(host).get('turn')}, host top={top(host)}, "
                      f"client top={top(client)}) - no `next_turn` packet crossed, "
                      f"so the tripwire was never exercised")
        print(f"turn cycled to {turn}: the host shipped a `next_turn` stamp")
        h, c = report(host, client, "after the turn")
        clean_turn = (h == c)
        if clean_turn:
            assert not desync_seen(client) and not desync_seen(host), (
                "FALSE POSITIVE: the tripwire fired on a `next_turn` although both "
                f"machines carry identical terms ({h})")
            print("PASS silence: a clean battle crossed a full turn with the "
                  "tripwire quiet")
        else:
            # Not something this test injected: the battle drifted on its own during
            # the alien turn (a known engine gap - PRD-P3/P4 is what fixes those).
            # The tripwire's job is to CATCH that, so assert it did.
            assert desync_seen(client), (
                f"MISSED: the two machines drifted during the turn (host={h}, "
                f"client={c}) and the tripwire stayed silent")
            print(f"NOTE: the battle drifted on its own during the turn "
                  f"(host={h}, client={c}) - not injected by this test. The "
                  f"tripwire CAUGHT it, which is the assertion that matters; the "
                  f"silence criterion was covered by the walk steps above.")

        # --- 4. forced divergence: one-sided mint, detected within one turn ----
        # The lever is a test-only use of `battle_give` (nothing in the co-op
        # protocol replicates a mid-battle item spawn). No divergence mechanism
        # ships in the game.
        already = desync_seen(client)
        pre = terms(client)
        victim = battle(client)["units"][0]["id"]
        # slot=ground: createItemForTile mints an id off the SHARED counter and adds
        # the item to _items, so both terms move - and nothing in a unit's inventory
        # is disturbed.
        skew = client.cmd({"cmd": "battle_give", "unit": victim,
                           "item": "STR_STUN_ROD", "slot": "ground"})
        assert skew.get("ok"), f"could not skew the client: {skew}"
        hs, cs = terms(host), terms(client)
        assert cs != pre, (
            f"the injected mint did not move the client's own terms ({pre} -> {cs}) "
            f"- the lever is dead, so the detection assertion below would be vacuous")
        assert hs != cs, (
            f"the injected skew left the two machines in agreement ({hs} vs {cs})")
        print(f"injected a one-sided mint on the client (item id "
              f"{skew.get('weaponId')}): host={hs} client={cs}")

        before_stats = client.cmd({"cmd": "shared_resync_stats"})
        turn2 = cycle_turn(host, client)
        assert turn2, (f"the battle never reached another turn (turn="
                       f"{battle(host).get('turn')}) - the skew was never stamped")
        print(f"turn cycled to {turn2} with the skew in place")

        assert desync_seen(client), (
            f"TRIPWIRE MISSED the injected divergence: host={terms(host)} "
            f"client={terms(client)}, desyncSeen still False after turn {turn2}")
        if already:
            print("PASS detection: the client's tripwire is set (it had already "
                  "fired on the earlier self-inflicted drift)")
        else:
            print("PASS detection: the client's tripwire fired within one turn of "
                  "the injected divergence")

        # ... and NOTHING else happened.
        after_stats = client.cmd({"cmd": "shared_resync_stats"})
        assert after_stats.get("requests") == before_stats.get("requests"), (
            f"the battle tripwire asked for a world resync - a mid-battle restream "
            f"destroys the running battle: {before_stats} -> {after_stats}")
        assert not after_stats.get("pending"), \
            f"a resync is in flight after a battle desync: {after_stats}"
        for gc, tag in ((host, "host"), (client, "client")):
            b = battle(gc)
            assert b.get("inBattle"), \
                f"{tag} lost the battle after the tripwire fired: top={top(gc)}"
            assert has(gc, "BattlescapeState"), \
                f"{tag}'s battlescape left the state stack: {states(gc)[-4:]}"
        print("PASS no repair: no resync requested, both battles still live")

        # ... and the battle is still playable.
        driver, watcher, dtag, wtag, db = pick_driver(host, client)
        mine = movers(battle(driver), 0 if db["host"] else 1)
        assert mine, (f"{dtag} commands no unit able to act after the tripwire "
                      f"fired: {[(u['id'], u.get('coop'), u.get('tu')) for u in db['units']]}")
        before, landed = drive_walk(driver, watcher, mine[0]["id"])
        print(f"PASS playable: {dtag} still walked {mine[0]['id']} {before} -> "
              f"{landed} and {wtag} still mirrored it after the desync report")

        print("ALL BATTLE-TRIPWIRE TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
