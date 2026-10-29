"""Regression test: a mod hit script that stores the animation frame in a unit tag
must not raise a battle desync alarm.

Player report (X-Com Files, SEPARATE campaign, parallel turns, a host-started
battle): "saveBlob diverged ... sidestart" at the first turn-2 side start, after an
alien turn in which one soldier was hit. The host's save shows that soldier carrying
the X-Com Files HitFX tags (LAST_HIT_FRAME = the battlescape animation frame at the
hit, LAST_HIT_TYPE, LAST_HIT_POWER). The animation frame is per-machine display
state, so a tag copied from it differs between two machines that each work out the
hit, and a machine that never runs the script never has the tag at all.

In a co-op battle only the host runs the battle: the hit, its damageUnit script and
the tag the script writes happen on the host. The other player applies the host's
events, whose unit delta carries every unit's script tags, and the battle hash
compares them. This test proves that path with the Coop_HitFrame_Test mod, whose
damageUnit script writes the frame (COOP_HIT_FRAME) and a hit counter
(COOP_HIT_COUNT) into the victim's tags, the same shape as HitFX.

One boot, the mod on both machines: a two-player co-op skirmish (terror mission, map
seed 1, the default parallel turns, the client commands two soldiers, every unit no
player commands pinned so it cannot act). Steps:
  1. the client's first soldier C gets a stun rod and stands next to a Sectoid (test
     commands, both machines); the client orders a melee hit through the order path,
     which the host runs, up to SWINGS times, until the host's tags show that the
     script ran;
  2. the victim's tags are equal on both machines with the hit counter written, every
     unit's tags are equal, every hash bucket is equal, neither machine raised a
     desync and the client never ran a battle state of its own;
  3. one full turn (both players press END TURN, through the alien side back to the
     player side): the same checks at the new side start.

PASS (exit 0) / FAIL (exit 2: a check failed, a precondition never held or a step
timed out).

Run:  python tools/coop_test/test_coop_hit_frame_tag.py
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, pin_ai_neutral  # noqa: E402
from test_delta_core import end_turn_cycle, short  # noqa: E402
from test_host_combat import bring_up_lobby_roster_pinned  # noqa: E402
from test_client_shoot import (snap, common_fails, give_both, place, set_tu_both, send_intent, jt,  # noqa: E402
                               TU_MAX)

MOD_NAME = "Coop_HitFrame_Test"
MOD = os.path.join(HERE, "mods", MOD_NAME)
MOD_ACTIVE_LINE = "- Coop_HitFrame_Test v1.0"
KEY = "49261"                       # this file's lobby key
MISSION = "STR_TERROR_MISSION"
SEED_MAP = 1
MAP_FP = -3.451266327757785e+18     # host battle_state.mapFingerprint for MISSION on SEED_MAP (the tiles below need it)
COOP_SEAT_1 = 1
FACTION_PLAYER, FACTION_HOSTILE = 0, 1
VICTIM = 1000001                    # a Sectoid Soldier on this map
C_TILE, C_DIR = (24, 24, 0), 0      # open ground; C faces north
V_TILE, V_DIR = (24, 23, 0), 4      # the tile C faces; the victim faces C
SEED_SWING = 1                      # the host's seed right before each order: the rod hits on the first swing here
SWINGS = 4
STUN_ROD = "STR_STUN_ROD"
TAG_FRAME, TAG_COUNT = 0, 1         # raw tag index = the mod's definition order (the only BattleUnit tags loaded)
ORDER_S = 60
LOG_S = 10


def tags(gc, uid):
    """The unit's raw script tag values on this machine, trailing zeros trimmed."""
    r = gc.cmd({"cmd": "field_poke", "class": "unit", "id": uid, "field": "tags"})
    return r.get("before") if r.get("ok") else {"error": r.get("error")}


def tag(t, i):
    if not isinstance(t, list):
        return None
    return t[i] if len(t) > i else 0


def all_tags(gc):
    return {u["id"]: tags(gc, u["id"]) for u in battle_state(gc).get("units", [])}


def mod_active(gc):
    """True once this machine's openxcom.log lists the mod as active (bounded read)."""
    path = os.path.join(gc.user_dir, "openxcom.log")
    deadline = time.time() + LOG_S
    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if MOD_ACTIVE_LINE in f.read():
                    return True
        except OSError:
            pass
        if time.time() >= deadline:
            return False
        time.sleep(0.25)


def boot(host, client):
    bring_up_lobby_roster_pinned(host, client, KEY)
    seated = {}
    session.drive_to_battlescape(host, client, seated, mission=MISSION, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    fp = (hs.get("mapFingerprint"), cs.get("mapFingerprint"))
    assert fp == (MAP_FP, MAP_FP), f"mapFingerprint host/client {fp} (want {MAP_FP!r} on both)"
    for gc in (host, client):
        assert mod_active(gc), f"{gc.name}: openxcom.log never listed {MOD_ACTIVE_LINE!r}"
    pinned = pin_ai_neutral(host, client, tag="hitframe")
    assert pinned, "pin_ai_neutral pinned no unit"
    mine = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_1
                  and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert mine, f"the client commands no soldier: {[(u['id'], u.get('coop')) for u in hs['units']]}"
    v = session.units_by_id(hs).get(VICTIM) or {}
    assert v.get("faction") == FACTION_HOSTILE and not v.get("isOut"), f"victim {VICTIM} at bring-up: {v}"
    session.wait_host_idle(host, client, timeout=30)
    session.assert_hash_clean(host, client, full=True, what="bring-up")
    print(f"[hitframe] boot ok: {MISSION} turn {hs.get('turn')} client soldiers {mine} pinned {len(pinned)}",
          flush=True)
    return mine[0]


def stage(host, client, c_id):
    rod, _ = give_both(host, client, c_id, STUN_ROD)
    st = {"rod": rod, "C": place(host, client, c_id, C_TILE, C_DIR),
          "victim": place(host, client, VICTIM, V_TILE, V_DIR)}
    st["tagsBefore"] = {"host": tags(host, VICTIM), "client": tags(client, VICTIM)}
    return st


def swing(host, client, c_id, rod, notes):
    set_tu_both(host, client, c_id, TU_MAX)
    host.ok({"cmd": "set_seed", "seed": SEED_SWING})
    req = {"cmd": "battle_intent", "kind": "melee", "actor": c_id,
           "plan": {"weapon": rod, "target": jt(V_TILE), "terrainPart": 0, "targetUnit": VICTIM,
                    "targetPos": jt(V_TILE)}}
    return send_intent(host, client, req, notes, timeout=ORDER_S)


def checks(host, client, before, what):
    fails = []
    try:
        session.wait_host_idle(host, client, timeout=30)
    except Exception as e:
        fails.append(f"the host never went idle: {short(e)}")
    vh, vc = tags(host, VICTIM), tags(client, VICTIM)
    if not (isinstance(vh, list) and tag(vh, TAG_COUNT) >= 1 and vh == vc):
        fails.append(f"victim {VICTIM} tags (frame, count, ...) host={vh} client={vc} "
                     f"(want equal, with the hit counter written)")
    th, tc = all_tags(host), all_tags(client)
    diff = [(k, th.get(k), tc.get(k)) for k in sorted(set(th) | set(tc)) if th.get(k) != tc.get(k)]
    if diff:
        fails.append(f"unit tags differ between the machines (id, host, client): {diff}")
    fails += common_fails(host, client, before, what)
    hs, cs = battle_state(host), battle_state(client)
    print("EVIDENCE %s: %s" % (what, json.dumps({
        "victim": {"host": vh, "client": vc},
        "turn": [hs.get("turn"), cs.get("turn")], "side": [hs.get("side"), cs.get("side")],
        "unitsWithTags": sorted(k for k, t in th.items() if t)}, default=str)), flush=True)
    return [f"{what}: {f}" for f in fails]


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("hitframe_host", mods=[MOD]))
    client = GameClient("client", None, make_user_dir("hitframe_client", mods=[MOD]))
    fails, notes = [], []
    try:
        try:
            c_id = boot(host, client)
            st = stage(host, client, c_id)
        except Exception as e:
            fails.append(f"bring-up / staging: {short(e, 800)}")
            c_id = st = None
        if st is not None:
            print("EVIDENCE staged: %s" % json.dumps({"C": c_id, **st}, default=str), flush=True)
            before = snap(host, client)
            hit = 0
            for n in range(1, SWINGS + 1):
                r = swing(host, client, c_id, st["rod"], notes)
                print("[hitframe] swing %d: sent %s answer %s; host victim tags %s"
                      % (n, r.get("sent"), r.get("answer"), tags(host, VICTIM)), flush=True)
                if r.get("answer") != "end":
                    fails.append(f"swing {n}: the host did not run the order (sent {r.get('sent')}, answer "
                                 f"{r.get('answer')}, resp {r.get('resp')}, notes {notes})")
                    break
                if tag(tags(host, VICTIM), TAG_COUNT):
                    hit = n
                    break
            if not fails and not hit:
                fails.append(f"the stun rod never hit victim {VICTIM} in {SWINGS} swings (host tags "
                             f"{tags(host, VICTIM)}): the script never ran")
            if hit:
                fails += checks(host, client, before, "hit")
                turn0 = end_turn_cycle(host, client, notes)
                turn1 = battle_state(host).get("turn")
                if notes or not (isinstance(turn1, int) and isinstance(turn0, int) and turn1 > turn0):
                    fails.append(f"the turn did not cycle: turn {turn0} -> {turn1}, notes {notes}")
                fails += checks(host, client, before, "next turn")
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception:
                pass

    print("==== RESULT ====")
    for f in fails:
        print("FAIL " + f)
    print(f"test_coop_hit_frame_tag: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    if fails:
        sys.exit(2)
    print("PASS: the hit script's tags match on both machines through the next side start")
    sys.exit(0)


if __name__ == "__main__":
    main()
