"""PvP mind control (psi): REAL cross-machine convergence [F5].

Originates a mind-control through the real coop send path and asserts BOTH
machines converge on the flip.  Unlike the old smoke test (which called the
receiver-side decoder and could only prove "didn't crash"), this drives the
attack the same way primaryAction does -- statePushBack(new PsiAttackBState)
on the ACTIVE machine (activeSync==true).  On that machine PsiAttackBState
takes its ORIGINATOR branch: it fires the psi_attack animation packet, then
ExplosionBState -> TileEngine::psiAttack rolls the MC and
BattlescapeGame::psiAttackMessage flips getCoop() / faction and sends the
authoritative psi_result packet.

Legacy PvP psi is the INVERTED-flip path: the psi_result receiver flips
getCoop() 0<->1 and forces the victim to FACTION_HOSTILE on the PEER, while
the attacker machine holds the victim at FACTION_PLAYER.  So we assert the
coop value is EQUAL across machines but the faction is OPPOSITE.

Determinism: the MC roll is stochastic, so we force the attacker's psiSkill /
psiStrength to 100 on BOTH machines (each independently simulates the battle)
and force the victim visible on both (the psiAttackMessage send guard needs
victim->getVisible()==true).  Without this the roll would usually miss,
psi_result would never fire, and the test would soft-pass -- the exact bug
this rewrite exists to kill.

Run:  python tools/coop_test/test_pvp_skirmish_psi.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture as PVP

PORT = "48000"

FACTION_PLAYER = 0
FACTION_HOSTILE = 1
FACTION_NEUTRAL = 2


def battle(gc):
    return gc.cmd({"cmd": "battle_state"})


def _fail(fails, msg):
    print(f"  FAIL {msg}")
    fails.append(msg)


def _unit(bs, uid):
    return next(u for u in bs["units"] if u["id"] == uid)


def test_psi(fails, alien_player, gamemode):
    tag = f"gm{gamemode}_{alien_player}"
    print(f"\n--- psi {tag} ---")

    host = GameClient("host", 48972, make_user_dir(f"pvp_psi_{tag}_host"))
    client = GameClient("client", 48973, make_user_dir(f"pvp_psi_{tag}_client"))
    try:
        host.spawn(); host.connect()
        client.spawn(); client.connect()

        gm = PVP.start_pvp_skirmish_battle(host, client, PORT,
                                           alien_player=alien_player)
        if gm != gamemode:
            _fail(fails, f"{tag}: expected {gamemode}, got {gm}")
            return

        hb = battle(host)
        cb = battle(client)

        # ATTACKER = the machine that currently OWNS the simulation
        # (activeSync==true).  This is NOT coopTurn -- only the activeSync
        # machine ships a packet, so the attack has to originate here.
        if hb.get("activeSync"):
            atk, peer, ab = host, client, hb
        elif cb.get("activeSync"):
            atk, peer, ab = client, host, cb
        else:
            _fail(fails, f"{tag}: neither machine has activeSync "
                  f"(host={hb.get('activeSync')} client={cb.get('activeSync')})")
            return
        atk_is_host = atk is host
        print(f"    attacker machine = {'host' if atk_is_host else 'client'} "
              f"(activeSync)")

        # On the attacker machine the local side is FACTION_PLAYER and the
        # opponent is FACTION_HOSTILE (per-machine PvP remap).
        mine = [u for u in ab["units"]
                if u.get("faction") == FACTION_PLAYER and not u.get("isOut")]
        enemies = [u for u in ab["units"]
                   if u.get("faction") == FACTION_HOSTILE and not u.get("isOut")]
        if not mine:
            _fail(fails, f"{tag}: no FACTION_PLAYER units on attacker machine")
            return
        if not enemies:
            _fail(fails, f"{tag}: no FACTION_HOSTILE units on attacker machine")
            return
        shooter = mine[0]
        target = enemies[0]
        print(f"    shooter={shooter['id']} (coop={shooter['coop']}) "
              f"target={target['id']} (coop={target['coop']})")

        # Arm the psi-amp on BOTH machines (nothing replicates a mid-battle
        # item spawn; ids only line up if both sides create it in step).
        for gc in (host, client):
            gc.ok({"cmd": "battle_give", "unit": shooter["id"],
                   "item": "STR_PSI_AMP",
                   "slot": "right", "clear_hands": True})
        time.sleep(1)

        # Force psi stats high on the attacker (both machines) and force the
        # victim visible (both machines) so the MC deterministically succeeds
        # and psiAttackMessage's send guard is satisfied.
        for gc in (host, client):
            r = gc.ok({"cmd": "battle_action", "action": "set_stat",
                       "unit": shooter["id"], "psiSkill": 100,
                       "psiStrength": 100, "refill": True})
            gc.ok({"cmd": "battle_action", "action": "set_stat",
                   "unit": target["id"], "visible": True})
        print(f"    set_stat: attacker psiSkill/psiStrength=100 refill; "
              f"target visible=true (both machines)")

        # Resolve the psi-amp id from the attacker machine.
        items = atk.cmd({"cmd": "battle_items"})["items"]
        amps = [i for i in items
                if i.get("type") == "STR_PSI_AMP"
                and i.get("owner") == shooter["id"]]
        if not amps:
            _fail(fails, f"{tag}: psi-amp not equipped on attacker machine")
            return
        amp_id = amps[0]["id"]

        # Snapshot the TARGET on both machines before the MC.
        h0 = _unit(battle(host), target["id"])
        c0 = _unit(battle(client), target["id"])
        pre_coop = h0["coop"]  # coop is machine-invariant before the MC
        print(f"    PRE  host  coop={h0['coop']} fac={h0['faction']} "
              f"mcId={h0.get('mindControllerId')} mc={h0.get('mindControlled')}")
        print(f"    PRE  client coop={c0['coop']} fac={c0['faction']} "
              f"mcId={c0.get('mindControllerId')} mc={c0.get('mindControlled')}")
        if h0["coop"] != c0["coop"]:
            print(f"    note: target coop differs pre-MC "
                  f"(host={h0['coop']} client={c0['coop']})")

        # Fire the REAL MC on the ATTACKER machine only.
        atk.cmd({"cmd": "battle_action", "action": "select",
                 "unit": shooter["id"]})
        res = atk.cmd({"cmd": "battle_action", "action": "psi_attack",
                       "unit": shooter["id"], "target": target["id"],
                       "weapon_id": amp_id})
        print(f"    psi_attack: ok={res.get('ok')} err={res.get('error','none')} "
              f"tuCost={res.get('tuCost')} tuHave={res.get('tuHave')} "
              f"activeSync={res.get('activeSync')} "
              f"targetVisible={res.get('targetVisible')}")

        # Poll until both machines flip the target's coop (or timeout).
        deadline = time.time() + 15
        ht = ct = None
        while time.time() < deadline:
            ht = _unit(battle(host), target["id"])
            ct = _unit(battle(client), target["id"])
            if ht["coop"] != pre_coop and ct["coop"] != pre_coop:
                break
            time.sleep(0.5)

        print(f"    POST host  coop={ht['coop']} fac={ht['faction']} "
              f"mcId={ht.get('mindControllerId')} mc={ht.get('mindControlled')}")
        print(f"    POST client coop={ct['coop']} fac={ct['faction']} "
              f"mcId={ct.get('mindControllerId')} mc={ct.get('mindControlled')}")

        atk_post = ht if atk_is_host else ct
        peer_post = ct if atk_is_host else ht

        # (1) coop flipped vs pre AND equal across both machines.
        if ht["coop"] == pre_coop or ct["coop"] == pre_coop:
            _fail(fails, f"{tag}: coop did NOT flip on both machines "
                  f"(pre={pre_coop} host={ht['coop']} client={ct['coop']})")
        elif ht["coop"] != ct["coop"]:
            _fail(fails, f"{tag}: coop disagrees across machines "
                  f"(host={ht['coop']} client={ct['coop']})")
        else:
            print(f"    PASS coop flipped {pre_coop}->{ht['coop']}, "
                  f"equal on both machines")

        # (2) faction inverted: PLAYER on attacker machine, HOSTILE on peer.
        if atk_post["faction"] != FACTION_PLAYER:
            _fail(fails, f"{tag}: attacker-machine target faction="
                  f"{atk_post['faction']} expected FACTION_PLAYER(0)")
        if peer_post["faction"] != FACTION_HOSTILE:
            _fail(fails, f"{tag}: peer-machine target faction="
                  f"{peer_post['faction']} expected FACTION_HOSTILE(1)")
        if (atk_post["faction"] == FACTION_PLAYER
                and peer_post["faction"] == FACTION_HOSTILE):
            print(f"    PASS faction inverted: attacker=PLAYER(0) peer=HOSTILE(1)")

        # (3) mindControllerId set (== shooter) on the attacker machine.
        if atk_post.get("mindControllerId") != shooter["id"]:
            _fail(fails, f"{tag}: attacker-machine mindControllerId="
                  f"{atk_post.get('mindControllerId')} expected {shooter['id']}")
        else:
            print(f"    PASS attacker mindControllerId={shooter['id']}")
        # Peer mindControllerId comes from the peer's own re-roll (the
        # psi_result receiver does not set it), so report it but do not gate on
        # it -- coop+faction convergence above is what psi_result guarantees.
        print(f"    peer mindControllerId={peer_post.get('mindControllerId')} "
              f"mindControlled={peer_post.get('mindControlled')}")

        # (4) item census identical across machines (no item desync).
        ih = len(host.cmd({"cmd": "battle_items"})["items"])
        ic = len(client.cmd({"cmd": "battle_items"})["items"])
        if ih != ic:
            _fail(fails, f"{tag}: item drift after psi: host={ih} client={ic}")
        else:
            print(f"    PASS item census {ih} identical on both machines")

    except Exception as e:
        traceback.print_exc()
        _fail(fails, f"{tag}: {e}")
    finally:
        host.shutdown()
        client.shutdown()


def main():
    fails = []
    test_psi(fails, "client", 2)
    test_psi(fails, "host", 3)

    print("\n==== PvP psi summary ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both gamemodes: real MC originated, both machines converged "
          "(coop flip equal, faction inverted, census intact)")
    sys.exit(0)


if __name__ == "__main__":
    main()
