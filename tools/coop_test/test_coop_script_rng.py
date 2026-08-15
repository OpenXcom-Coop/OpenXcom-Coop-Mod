"""PRD-P3 GAP-10 - mod script RNG is seed-replayed in a parallel co-op battle.

A mod battle script that draws the script-RNG bindings (randomChance / randomRange
on the SavedBattleGame `battle_game` register) runs on BOTH machines: the parallel
client reaches SavedBattleGame::newTurnUpdateScripts via BattlescapeGame::endTurn ->
_save->endTurn at every side close, exactly like the host. Before the fix the two
machines drew from their own diverged RNG streams, so every per-turn roll differed
(empirically: all 19 units' rolled scriptTags diverged host vs client).

The fix (SavedBattleGame::newTurnUpdateScripts) reseeds the global RNG to the
side-boundary seed the host stamps on `endTurn` (and the client adopts) around the
newTurnUnit/newTurnItem script loops, so both machines draw the SAME sequence over
the SAME units in the SAME order (the spawn_units B2 seed-replay pattern applied to
the whole loop; save+restore, a strict no-op when nothing draws).

The Coop_ScriptRng_Test mod's newTurnUnit script writes each roll into a per-unit
scriptTag (COOP_RNG_R / COOP_RNG_C). next_turn does NOT re-ship scriptTags, so a
divergent roll persists and shows up in the save_blob dump - the probe this test
reads. GREEN = every unit's tags match host vs client, and the whole save_blob hash
is byte-equal, at every turn boundary.

Run this file 5x for the post-fix stability check.
"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import test_battle_tripwire as TW

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "mods", "Coop_ScriptRng_Test")
SEED = int(os.environ.get("SCRIPT_RNG_SEED", "8031"))
TURNS = int(os.environ.get("SCRIPT_RNG_TURNS", "2"))


def blob(gc):
    r = gc.cmd({"cmd": "save_blob", "text": True})
    return r.get("hash"), r.get("text", "")


def tags_of(text):
    """{unit_id: (COOP_RNG_R, COOP_RNG_C)} from a save_blob text dump. The tag is
    associated with the nearest preceding `id:` line (units serialize `id:` before
    their `tags:` submap). A zero roll is omitted by ScriptValues::save (only
    non-default tags serialize), so a None means 'rolled 0', still a value."""
    out = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"\s+id:\s*(\d+)\s*$", line)
        if m:
            cur = int(m.group(1))
        mr = re.search(r"COOP_RNG_R:\s*(-?\d+)", line)
        if mr and cur is not None:
            out.setdefault(cur, [None, None])[0] = int(mr.group(1))
        mc = re.search(r"COOP_RNG_C:\s*(-?\d+)", line)
        if mc and cur is not None:
            out.setdefault(cur, [None, None])[1] = int(mc.group(1))
    return {k: tuple(v) for k, v in out.items()}


def check(host, client, label):
    hh, ht = blob(host)
    ch, ct = blob(client)
    htags, ctags = tags_of(ht), tags_of(ct)
    keys = sorted(set(htags) | set(ctags))
    diverged = [k for k in keys if htags.get(k) != ctags.get(k)]
    n_tags = ht.count("COOP_RNG_R")
    print(f"  {label}: tag-units={len(keys)} rawR={n_tags} "
          f"saveBlobEqual={hh == ch} diverged={len(diverged)}")
    for k in diverged[:5]:
        print(f"      unit {k}: host={htags.get(k)} client={ctags.get(k)}")
    assert n_tags > 0, (
        f"{label}: the newTurnUnit script never ran (0 COOP_RNG_R tags) - the mod "
        f"did not load or the hook did not fire; the check would be vacuous")
    assert not diverged, (
        f"{label}: {len(diverged)} unit script-RNG tag(s) DIVERGED host vs client - "
        f"GAP-10 seed-replay is not holding: {diverged[:8]}")
    assert hh == ch, (
        f"{label}: save_blob hash differs (host={hh} client={ch}) though tags matched "
        f"- a non-script divergence rode along; inspect the dump")
    return len(keys)


def main():
    opts = {"battleXcomSpeed": 2, "battleAlienSpeed": 2}
    host = client = None
    try:
        for attempt in range(1, TW.FIXTURE_TRIES + 1):
            host = GameClient("host", 48850, make_user_dir(
                "scriptrng_host", mods=[MOD],
                options=dict(opts, skipNextTurnScreen=True,
                             EnableCoopParallelTurns=True)))
            client = GameClient("client", 48851, make_user_dir(
                "scriptrng_client", mods=[MOD],
                options=dict(opts, EnableCoopParallelTurns=False)))
            for gc in (host, client):
                TW.write_battle_fixture(gc.user_dir)
            host.spawn(); host.connect()
            client.spawn(); client.connect()
            TW.bring_up_battle(host, client, seed=SEED)
            foes = [u["id"] for u in TW.battle(host)["units"]
                    if u.get("faction") == 1 and not u.get("isOut")]
            if len(foes) >= TW.MIN_HOSTILES:
                print(f"battle up; {len(foes)} live hostiles; the mod's newTurnUnit "
                      f"script is active on both machines")
                break
            print(f"attempt {attempt}: only {len(foes)} live hostiles, re-rolling")
            for gc in (host, client):
                gc.shutdown()
            host = client = None
        assert host is not None, "could not roll a viable fixture"

        # Turn 1 is the host-generated, streamed world: the client copies the host's
        # turn-1 tags, so it is a sanity check, not the fix under test.
        check(host, client, "turn 1 (streamed)")

        cycled = 0
        for _ in range(TURNS):
            t = TW.cycle_turn(host, client, timeout=300)
            if not TW.battle(host).get("inBattle") \
                    or not TW.battle(client).get("inBattle"):
                print("battle ended; stopping (cycled %d turn(s))" % cycled)
                break
            time.sleep(3)
            # A turn cycled on the CLIENT is a turn its newTurnUnit script ran
            # independently - the exact draw the fix must align.
            check(host, client, f"after turn {t}")
            cycled += 1
        assert cycled >= 1, ("no turn cycled - the client never ran an independent "
                             "newTurnUnit pass, so nothing was proven")
        print("PASS: script-RNG tags converge host==client across %d cycled turn(s)"
              % cycled)
    finally:
        for gc in (host, client):
            if gc is not None:
                try:
                    gc.shutdown()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
