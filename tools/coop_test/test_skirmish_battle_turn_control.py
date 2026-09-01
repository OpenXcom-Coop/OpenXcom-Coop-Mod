"""A SKIRMISH (NEW BATTLE > COOP) battle must run the coop turn-init handshake.

Reported symptom: a battle reached through Main Menu > NEW BATTLE > COOP > host
lobby > BATTLE SETTINGS > OK never initialises coop. Both machines sit on the
tactical map with

    coopTurn=0, playerTurn=3, activeSync=False, battleInit=False

forever. Because `_battleInit` never flips, `_isActivePlayerSync` is never set on
either side, and every coop battle state (ProjectileFlyBState, MeleeAttackBState,
PsiAttackBState, ...) gates its packet send on `_isActivePlayerSync == true`.
Nothing a unit does is replicated: the two machines simulate independently and
drift apart. Control is never split either - `BattleUnit::isSelectable` falls
through to the vanilla "all player units selectable" branch on BOTH machines.

The equivalent SHARED campaign battle initialises correctly
(test_shared_battle_turn_control.py reaches coopTurn=2), so this is specific to
the skirmish entry path.

The test drives the REAL flow (the same one as test_skirmish_flow.py step 7) and
asserts, in order:

  1. the coop-init gate actually fires: `battleInit` true on both machines, with
     the observed value of every sub-condition printed on failure so a red run
     names the blocker instead of just "false";
  2. exactly ONE machine owns the simulation (`coopTurn==2` + `activeSync`);
  3. control is split - the two machines' selectable unit sets are disjoint;
  4. replication works end to end: a shot fired from the simulation owner lands
     on BOTH machines (the victim's health/stun match), which is the consequence
     the missing handshake actually costs.

Run:  python tools/coop_test/test_skirmish_battle_turn_control.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import test_skirmish_flow as SK

PORT = "47973"


def states(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def top(gc):
    return states(gc)[-1].split("::")[-1]


def has(gc, name):
    return any(name in s for s in states(gc))


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def drain_to_tactical(host, client, rounds=12):
    """BattlescapeState::think() - which runs the coop-init handshake that sets
    _battleInit - only ticks while BattlescapeState is the TOP state. Dismiss
    whatever sits over it until both machines are on the tactical map."""
    for _ in range(rounds):
        moved = False
        for gc in (host, client):
            if top(gc) != "BattlescapeState":
                gc.cmd({"cmd": "dismiss_popup"})
                moved = True
        time.sleep(1.0)
        if not moved and all(top(gc) == "BattlescapeState" for gc in (host, client)):
            return


# ---- the coop-init gate, sub-condition by sub-condition ---------------------
#
# BattlescapeState.cpp:1284
#   getCoopStatic() && isCoopSession() && !_battleInit && !isBusy()
#   && side == FACTION_PLAYER && getPanicHandled() && !isPreview()
#   && !_clientPanicHandle
GATE = [
    ("coopStatic", True),
    ("coopSession", True),
    ("isBusy", False),
    ("panicHandled", True),
    ("isPreview", False),
    ("clientPanicHandle", False),
]


def gate_report(b):
    """Which sub-conditions of the init gate hold, as a printable line."""
    bits = []
    for key, want in GATE:
        got = b.get(key)
        bits.append(f"{key}={got}{'' if got == want else f'(want {want})'}")
    bits.append(f"side={b.get('side')}(want 0)")
    return " ".join(bits)


def gate_blockers(b):
    bad = [f"{k}={b.get(k)} (want {w})" for k, w in GATE if b.get(k) != w]
    if b.get("side") != 0:
        bad.append(f"side={b.get('side')} (want 0 = FACTION_PLAYER)")
    return bad


def snap(host, client):
    out = {}
    for tag, gc in (("host", host), ("client", client)):
        b = battle(gc)
        units = b.get("units", [])
        out[tag] = {
            "raw": b,
            "inBattle": b.get("inBattle"),
            "battleInit": b.get("battleInit"),
            "coopSession": b.get("coopSession"),
            "coopStatic": b.get("coopStatic"),
            "coopCampaign": b.get("coopCampaign"),
            "coopGamemode": b.get("coopGamemode"),
            "coopTurn": b.get("coopTurn"),
            "playerTurn": b.get("playerTurn"),
            "activeSync": b.get("activeSync"),
            "host": b.get("host"),
            "serverOwner": b.get("serverOwner"),
            "waitBC": b.get("waitBC"),
            "waitBH": b.get("waitBH"),
            "top": top(gc),
            "selectable": sorted(u["id"] for u in units if u.get("selectable")),
            "coop0": sorted(u["id"] for u in units if u.get("coop") == 0),
            "coopN": sorted(u["id"] for u in units
                            if u.get("coop") is not None and u["coop"] != 0),
            "gate": gate_report(b),
        }
    return out


def describe(r):
    lines = []
    for tag in ("host", "client"):
        m = r[tag]
        lines.append(
            f"\n    {tag:6}: battleInit={m['battleInit']} coopTurn={m['coopTurn']} "
            f"playerTurn={m['playerTurn']} activeSync={m['activeSync']} "
            f"host={m['host']} serverOwner={m['serverOwner']} "
            f"gamemode={m['coopGamemode']} coopCampaign={m['coopCampaign']} "
            f"waitBC={m['waitBC']} waitBH={m['waitBH']} top={m['top']}"
            f"\n            gate: {m['gate']}"
            f"\n            coop0={m['coop0']} coopN={m['coopN']} "
            f"selectable={m['selectable']}")
    return "".join(lines)


def wait_for_init(host, client, timeout=90):
    """Bounded wait for the handshake to settle, draining popups so the
    battlescape keeps ticking. Returns the last snapshot either way."""
    deadline = time.time() + timeout
    r = snap(host, client)
    while time.time() < deadline:
        r = snap(host, client)
        on_turn = sum(1 for t in ("host", "client") if r[t]["coopTurn"] == 2)
        if r["host"]["battleInit"] and r["client"]["battleInit"] and on_turn == 1:
            return r
        drain_to_tactical(host, client, rounds=2)
        time.sleep(2.0)
    return r


# ---- replication: an action by the sim owner must reach the peer -------------

def unit_pos(gc, uid):
    for u in battle(gc).get("units", []):
        if u["id"] == uid:
            return (u["x"], u["y"], u["z"])
    return None


def assert_replication(host, client, r):
    """Walk a unit on whichever machine owns the simulation and prove the peer
    saw it move.

    This is the payload of the missing handshake: UnitWalkBState (like
    ProjectileFlyBState / MeleeAttackBState / PsiAttackBState) only emits a
    packet while `_isActivePlayerSync` is true, so with the handshake skipped
    the unit walks on the driver's machine only and the two worlds diverge.
    A walk is used rather than a shot because a shot can legitimately miss -
    a position is unambiguous.
    """
    owner_tag = "host" if r["host"]["activeSync"] else "client"
    owner = host if owner_tag == "host" else client
    peer = client if owner_tag == "host" else host

    ob = battle(owner)
    movers = [u for u in ob["units"]
              if u.get("faction") == 0 and u.get("selectable") and not u.get("isOut")
              and u.get("tu", 0) > 8]
    assert movers, f"{owner_tag} (the sim owner) can command no unit with TU to " \
                   f"spend: {[(u['id'], u.get('coop'), u.get('selectable'), u.get('tu')) for u in ob['units']]}"

    # first unit that can actually reach an adjacent tile
    moved = None
    for u in movers:
        before = (u["x"], u["y"], u["z"])
        assert unit_pos(peer, u["id"]) == before, \
            f"unit {u['id']} starts at {before} on {owner_tag} but at " \
            f"{unit_pos(peer, u['id'])} on the peer - the machines are already apart"
        owner.cmd({"cmd": "battle_action", "action": "select", "unit": u["id"]})
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
            res = owner.cmd({"cmd": "battle_action", "action": "move", "unit": u["id"],
                             "x": before[0] + dx, "y": before[1] + dy, "z": before[2]})
            if res.get("ok"):
                moved = (u["id"], before, (before[0] + dx, before[1] + dy, before[2]))
                break
        if moved:
            break
    assert moved, "no commandable unit could step to any adjacent tile - " \
                  "the driver failed, not the replication"
    uid, before, want = moved
    print(f"    walk driven from {owner_tag}: unit {uid} {before} -> {want}")

    # the walk must land on the DRIVER first (else the driver, not coop, failed)
    deadline = time.time() + 45
    while time.time() < deadline and unit_pos(owner, uid) == before:
        time.sleep(0.5)
    after_o = unit_pos(owner, uid)
    assert after_o != before, \
        f"unit {uid} never moved even on {owner_tag} (still {before}) - " \
        f"the driver failed, not the replication"

    while time.time() < deadline:
        if unit_pos(peer, uid) == after_o:
            print(f"PASS replication: the walk reached BOTH machines "
                  f"(unit {uid}: {before} -> {after_o})")
            return
        time.sleep(0.5)

    raise AssertionError(
        f"REPLICATION BROKEN: unit {uid} walked {before} -> {after_o} on "
        f"{owner_tag}, but the peer still has it at {unit_pos(peer, uid)} - "
        f"the two machines have diverged")


def main():
    host = GameClient("host", 48770, make_user_dir("skirm_turn_host"))
    client = GameClient("client", 48771, make_user_dir("skirm_turn_client"))
    fail = None
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        # --- the real skirmish flow, exactly as a player walks it -------------
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
        # bounce back into the lobby and out again, exactly as test_skirmish_flow
        # step 6 does, so this test covers the same path a player walks
        host.ok({"cmd": "newbattle_coop"})
        host.wait_for("host lobby again",
                      lambda: session.has_state(host, "LobbyMenu") or None, timeout=60)
        host.wait_for("button offered again",
                      lambda: SK.lobby(host).get("buttonVisible") or None, timeout=60)
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host at battle settings again",
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
        # BEFORE draining: this is the state a driver sees if it stops as soon as
        # BattlescapeState exists. think() (and therefore the coop-init gate) only
        # runs while _popups is empty and BattlescapeState is the top state, so a
        # coop "Waiting for <peer>" warning sitting on top freezes battleInit at
        # false - the reported symptom, and NOT an engine failure.
        print("undrained (popups still up):" + describe(snap(host, client)))
        drain_to_tactical(host, client)
        print("both machines reached the skirmish battlescape")

        # --- 1. the init gate must fire --------------------------------------
        r = wait_for_init(host, client)
        detail = describe(r)
        errs = []
        for tag in ("host", "client"):
            if not r[tag]["battleInit"]:
                bl = gate_blockers(r[tag]["raw"]) or ["<all sub-conditions hold>"]
                errs.append(f"{tag}: battleInit never set; blocking sub-conditions: "
                            + ", ".join(bl))
        if errs:
            raise AssertionError("skirmish coop turn-init NEVER RAN:" + detail
                                 + "\n  errors:\n    - " + "\n    - ".join(errs))
        print("PASS init: coop turn-init ran on both machines (battleInit true)" + detail)

        # --- 2. exactly one machine owns the simulation ----------------------
        on_turn = [t for t in ("host", "client") if r[t]["coopTurn"] == 2]
        sync = [t for t in ("host", "client") if r[t]["activeSync"]]
        assert len(on_turn) == 1, \
            f"exactly one machine must have coopTurn==2, got {on_turn or 'none'}:{detail}"
        assert sync == on_turn, \
            f"activeSync {sync or 'nobody'} must match the machine on turn {on_turn}:{detail}"
        print(f"PASS turn: {on_turn[0]} owns the simulation "
              f"(coopTurn=2, activeSync=True); the peer waits")

        # --- 3. control is split --------------------------------------------
        hsel, csel = set(r["host"]["selectable"]), set(r["client"]["selectable"])
        assert not (hsel & csel), \
            f"BUG: both machines command the same units {sorted(hsel & csel)}:{detail}"
        assert hsel or csel, f"nobody can command anything:{detail}"
        print(f"PASS split: host commands {sorted(hsel)}, client commands {sorted(csel)} "
              "- disjoint")

        # --- 4. actions actually replicate -----------------------------------
        assert_replication(host, client, r)

        print("ALL SKIRMISH BATTLE-TURN-CONTROL TESTS PASSED")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
