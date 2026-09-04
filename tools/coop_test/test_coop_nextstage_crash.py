"""Coop multi-stage (next-stage) transition: host must not crash and BOTH
players must advance to the next stage.

Repro of the player report (TFTD, 2.0.30 nightly, SEPARATE coop): a 2-stage
STR_ALIEN_BASE_ASSAULT (alien colony) is cleared on stage 1; killing the last
alien crashes the HOST (use-after-free in BattlescapeGame::handleStateCoop, via
the coop pump updateCoopTask, because finishBattle's coop host next-stage branch
pops the BattlescapeState but leaves SavedBattleGame::_battleState dangling and
never completes the coop handshake).

The fixture is the player's own mid-battle host save (scrubbed): coop SEPARATE,
mid stage-1 STR_ALIEN_BASE_ASSAULT, nextStage = STR_ALIEN_COLONY_P2.

  BASELINE (unfixed exe): the host process dies right after the kill.
  FIXED: no crash; both machines end up in stage 2 (STR_ALIEN_COLONY_P2).

Run:  python tools/coop_test/test_coop_nextstage_crash.py
Exit 0 = pass; 2 = failure (crash / stuck / did not advance).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient
from tftd_common import make_tftd_user_dir
import session
import harness

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SAVE_SRC = os.environ.get("TFTD_SAVE") or os.path.join(FIX, "tftd_base_assault.sav")
SAVE = "tftd_base_assault.sav"
PORT = "47955"


def tftd_data_present():
    """This repro needs the proprietary TFTD (xcom2) game data staged next to the
    exe. CI stages only the UFO data, so skip cleanly there instead of failing."""
    exe_dir = os.path.dirname(harness.EXE)
    return os.path.isdir(os.path.join(exe_dir, "TFTD", "GEODATA"))


def states(gc):
    return gc.cmd({"cmd": "get_state"})["states"]


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def alive(gc):
    b = battle(gc)
    return b, [u for u in b.get("units", []) if not u.get("isOut")]


def mission(gc):
    return battle(gc).get("missionType")


def proc_dead(gc):
    return gc.proc is not None and gc.proc.poll() is not None


def main():
    if not tftd_data_present():
        print("SKIP: TFTD (xcom2) game data not staged next to the exe "
              "(no TFTD/GEODATA) - this repro is TFTD-only.")
        sys.exit(0)
    if not os.path.exists(SAVE_SRC):
        print(f"SKIP: fixture {SAVE_SRC} not found.")
        sys.exit(0)
    host_dir = make_tftd_user_dir("nsc_host", saves=[SAVE_SRC])
    client_dir = make_tftd_user_dir("nsc_client")  # empty (zero-disk client)
    host = GameClient("host", 47951, host_dir)
    client = GameClient("client", 47952, client_dir)
    fail = None
    try:
        host.spawn(); client.spawn()
        host.connect(timeout=120); client.connect(timeout=120)

        # resume the mid-battle stage-1 save into a live coop battle on both. The
        # scrubbed fixture's coopPlayers are HostPlayer/ClientPlayer (the harness
        # defaults); host_tcp/join_tcp are refused for any other identity.
        session.resume_campaign_battle(host, client, SAVE, port=PORT, timeout=180)

        hb = battle(host)
        print(f"host in battle: mission={hb.get('missionType')} turn={hb.get('turn')} "
              f"side={hb.get('side')} coopSession={hb.get('coopSession')} host={hb.get('host')}")
        assert hb.get("missionType") == "STR_ALIEN_BASE_ASSAULT", \
            f"unexpected stage-1 mission {hb.get('missionType')}"

        _, hostile = None, None
        hb, units = alive(host)
        hostile = [u for u in units if u.get("faction") == 1]
        print(f"stage-1 alive aliens on host: {sorted(u['id'] for u in hostile)}")

        # KILL the last alien(s): faithful lethal path -> UnitDieBState drops
        # inventory, spawns corpses, sends coop death packets.
        print("killing all remaining aliens on the HOST (faction=1)...")
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
        print("kill_unit_real ->", r)

        # let the deaths settle (UnitDieBState runs across frames)
        host.wait_for("all aliens dead on host",
                      lambda: (not [u for u in alive(host)[1] if u.get("faction") == 1]) or None,
                      timeout=30, interval=1.0)
        print("all aliens dead; driving end-of-turn into finishBattle "
              "(battle_autoend -> close_nextturn)...")
        # This is the win -> NextTurnState::close -> BattlescapeState::finishBattle,
        # which on the coop host with a nextStage takes the next-stage branch.
        ba = host.cmd({"cmd": "battle_autoend"})
        print("battle_autoend ->", ba)
        cn = host.cmd({"cmd": "close_nextturn"})
        print("close_nextturn ->", cn)

        # THE DISCRIMINATOR: does the HOST actually ENTER the stage-2 battlescape?
        #   BASELINE - the host use-after-free crashes in its own coop pump (proc/
        #     socket dies), OR (when the freed memory survives) hangs forever on the
        #     "please wait" CoopState: its stack is [GeoscapeState, CoopState] with NO
        #     BattlescapeState, even though getSavedBattle() already holds the rebuilt
        #     STR_ALIEN_COLONY_P2 map (so mission alone is NOT proof of entry). -> FAIL.
        #   FIXED - the host's stack carries a live BattlescapeState (it entered).
        # get_state only lists the Game state stack (no battle deref), so it is safe to
        # poll even while _battleState dangles - unlike battle_state, which we only read
        # once the host has provably entered.
        def host_stack():
            return states(host)

        print("waiting for the HOST to ENTER the stage-2 battlescape...")
        deadline = time.time() + 60
        host_entered = False
        while time.time() < deadline:
            time.sleep(1.5)
            if proc_dead(host):
                raise AssertionError(
                    f"HOST CRASHED on next-stage transition: process exited rc="
                    f"{host.proc.returncode} (0x{host.proc.returncode & 0xffffffff:08x})")
            try:
                st = host_stack()
            except Exception as e:
                raise AssertionError(f"HOST CRASHED on next-stage transition: {e}")
            if any("BattlescapeState" in s for s in st):
                host_entered = True
                print(f"host entered the battlescape (top={[s.split('::')[-1] for s in st[-2:]]})")
                break
        if not host_entered:
            raise AssertionError(
                f"HOST STUCK: never entered the stage-2 battlescape within 60s "
                f"(top={[s.split('::')[-1] for s in host_stack()[-2:]]}) - the coop "
                f"multi-stage handshake did not complete for the host (hang repro)")
        hb = battle(host)
        assert hb.get("missionType") == "STR_ALIEN_COLONY_P2" and hb.get("inBattle"), \
            f"host entered a battlescape but not stage 2: {hb.get('missionType')}"

        # both machines must be in stage 2, synced (battleInit true on both).
        print("host advanced; confirming the CLIENT is in stage 2 too...")
        for gc, tag in ((host, "host"), (client, "client")):
            gc.wait_for(f"{tag} in stage 2",
                        lambda gc=gc: (battle(gc).get("missionType") == "STR_ALIEN_COLONY_P2"
                                       and battle(gc).get("inBattle")) or None,
                        timeout=90, interval=2.0)
        # let the coop turn handshake settle, then sanity-check both are initialised.
        time.sleep(4)
        hb, cb = battle(host), battle(client)
        print(f"host : mission={hb.get('missionType')} inBattle={hb.get('inBattle')} "
              f"battleInit={hb.get('battleInit')} coopTurn={hb.get('coopTurn')}")
        print(f"client: mission={cb.get('missionType')} inBattle={cb.get('inBattle')} "
              f"battleInit={cb.get('battleInit')} coopTurn={cb.get('coopTurn')}")
        assert hb.get("battleInit") and cb.get("battleInit"), \
            "both machines reached stage 2 but the coop battle did not initialise on both"
        print("PASS: both machines advanced to STR_ALIEN_COLONY_P2 (stage 2), no crash, "
              "coop battle initialised on both")
    except Exception as e:
        fail = e
        print(f"[FAIL] {e}")
        for tag, gc in (("host", host), ("client", client)):
            try:
                print(f"  {tag} states: {states(gc)[-4:]}")
                print(f"  {tag} battle: mission={mission(gc)} inBattle={battle(gc).get('inBattle')}")
            except Exception as ee:
                print(f"  {tag}: unreachable ({ee})")
    finally:
        host.shutdown(); client.shutdown()

    sys.exit(2 if fail else 0)


if __name__ == "__main__":
    main()
