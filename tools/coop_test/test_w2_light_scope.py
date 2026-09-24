"""W2-P2 S-L - test_w2_light_scope.py: the second player's light recompute
mirrors vanilla's scope (owner ruling M6, 2026-09-24; spec
rewrite/prompts/w2p2_delta_core.md AMENDMENT A4, section A4.5; orchestrator
rulings Q-L1 = (a), Q-L2 = (a), Q-L4 = (a)).

Light is display state: it is in no hash bucket and no serializer, so no
existing check can see it. The second player's machine today recomputes the
WHOLE map every time a delta changes any tile (4.0-6.4 ms per event on the
6400-tile default map, F517) and never when a unit moves. Vanilla recomputes a
small area around each change and the whole map only at turn end. This test
compares both machines' light tile by tile (the `light_census` probe, whole
map, all four layers plus shade) and reads the client's recompute counters.
Three scenarios, ONE boot, in this order (A4.5: LS3's tile changes would make
today's client recompute the whole map and heal LS1's stale light before LS2
could show it).

The battle runs AT NIGHT (owner D142 = a, amendment A6): maximum darkness
(15) from the NEW BATTLE settings. Mechanism A6 (1): before the host's game
starts, this test writes `darkness: 15` into the host's new-battle config
(<host user dir>/xcom1/battle.cfg, the file NewBattleState::load() reads with
cfgReader["darkness"] when the NEW BATTLE screen opens); test-only, no src
change. By day (S-L.1's run, F603: globalShade 0, ambient 15 on 6237/6400
tiles) a unit's light never beats the ambient layer, so no census difference
could show. Boot precondition on BOTH machines: light_census globalShade ==
15, and after light_recompute the census `units` layer is non-zero on H's
tile.

  LS1  plain walk. H is staged at C15_H_TILE on BOTH machines, both recompute
       light (baseline census equal), then the host walks H to C15_WALK_DEST
       with a real-UI click. GREEN: census equal; client lightLocalCalls
       delta >= 2 (one per walk_step); lightWholeCalls delta 0.
  LS2  turn end, no tile change; stages its own stale light (A6, F606): after
       LS1 (and its classifier), TU refilled and light_recompute on BOTH
       machines (baseline census equal), then the host walks H back along the
       C15 path to C15_H_TILE with a real-UI click (moves H's personal light;
       the census right after the walk is evidence only, no classifier), then
       both press END TURN, full cycle back to the player side. The map has no
       fire or smoke, so the side transitions carry no tiles. GREEN: census
       equal; client lightWholeCalls delta over the cycle == the number of
       side_transition evs the client applied in the cycle (its event_log),
       and the client's last light recompute at each of those seqs was
       whole-map (its `[coop-light] seq=` log line - the per-seq record of
       `lastLight`).
  LS3  burning floor (tile + unit). H gets specab 2 (SPECAB_BURNFLOOR) on BOTH
       machines, is staged at C15B_H_TILE, both recompute light (baseline),
       the client's light timing windows are zeroed (light_probe_reset), then
       set_seed SEED_C15 and the host walks H 3 steps to C15B_WALK_DEST; the
       walked tiles ignite on the host (fire 3 / smoke 12, S-A precalc).
       GREEN: census equal; lightWholeCalls delta 0; lightLocalCalls
       delta >= 3; client deltaApplyUsMax (the window) <= BAR_L_US.

RED (commits S-L.1 and S-L.1b: this file, the three levers and the probes;
product behaviour untouched), the A4.5 RED column as amended by A6: LS1
census `units` layer differs (classifier CLIENT-stale) and client
lightLocalCalls delta 0; LS2 client lightWholeCalls delta 0 over the cycle
and the census differs (the walk back left the client stale); LS3 client
lightWholeCalls delta >= 3 and deltaApplyUsMax >= 4 ms (at night LS3 may
also show a census difference: recorded, not a stop). BAR_L_US is None until
the orchestrator sets it from
the S-L.0 measurement; while it is None, LS3's bar check fails with
"BAR_L not set (S-L.0 pending)".

Common to every scenario (A4.5), after the action settles (wait_host_idle):
light census equal on all four layers and shade; hash_now {full:true} all
buckets EQUAL (assert_hash_clean); desyncSeen false on both; deltaUnresolved,
deltaUnsupported, deltaRemoveMissing, deltaAddExisting 0 on both. LS1 and LS3
start from a baseline: light_recompute on BOTH machines, then census equal
(STOP-IF L2 when it differs - identical synced state must give identical
light), personalLight true on both, nonZero.units > 0.

STALENESS CLASSIFIER (R7, on every census mismatch): light_recompute on BOTH
machines, a second census, and per machine the tiles the recompute changed
(= that machine was stale) with counts and the first 10, then the verdict:
CLIENT-stale (the client rule missed a region), HOST-stale only (vanilla's
own history dependence, A4 note N5 - STOP-IF L3 / Q-L3 at green), BOTH-stale
or NEITHER-stale. Every census taken is also written as raw bytes (LL_MAX
bytes per tile, tile index order) to the machine's user dir, path printed.

FIXTURE (deterministic, never searched here): test_w2_delta_core.py's boot -
the default NEW BATTLE map, set_seed SEED_MAP right before newbattle_ok,
asserted against the baked MAP_FP, pin_ai_neutral - plus the night config
above, and its constants reused verbatim. Every staging write goes to BOTH
machines and the responses are
asserted equal. set_seed on the HOST immediately before LS3's walk order.

Each scenario prints ONE "EVIDENCE <id>:" line (both machines' fields) before
its conditions are checked; main() runs every scenario even after an earlier
one failed and prints "PASS <id>" / "FAIL <id>: <message>". Every wait is
bounded; a wait that times out is recorded in the EVIDENCE line and fails the
scenario. WV-D99 / WV-D100: one run is the result, no skip path, no second
boot. Exit 0 only when all three pass, 2 otherwise (a bring-up failure is
also 2).

Run:  python tools/coop_test/test_w2_light_scope.py
"""

import base64
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
from session import battle_state, event_state, event_log, pin_ai_neutral, assert_hash_clean
import repro_atom_walk as raw
import test_w2_delta_core as dc

# ----- test_w2_delta_core.py's constants, verbatim (A4.5) -----
SEED_MAP = 1
MAP_FP = -4.48310638993e+18      # host battle_state.mapFingerprint on SEED_MAP 1
H_ID = 10                        # first host-seat (coop 0) soldier
TU_MAX = 255                     # battle_set_unit_state tu: clamped to the unit's max TU
C15_H_TILE, C15_H_DIR = (1, 6, 0), 2      # H starts here facing east
C15_WALK_DEST = (3, 6, 0)                 # real_click_walk dest; OBSERVED path (1,6)->(2,6)->(3,6)
C15_WALK_PATH = [(2, 6, 0), (3, 6, 0)]
C15B_H_TILE, C15B_H_DIR = (1, 34, 0), 2   # burning-floor walker
C15B_WALK_DEST = (4, 34, 0)               # OBSERVED 3 steps (2,34)->(3,34)->(4,34), CULTIVAT #3
C15B_WALK_PATH = [(2, 34, 0), (3, 34, 0), (4, 34, 0)]
SEED_C15 = 1                              # all 3 walked tiles ignite on the host (fire 3, smoke 12)
SPECAB_BURNFLOOR = 2                      # src/Mod/Unit.h enum SpecialAbility
FACTION_PLAYER = 0
COOP_SEAT_0 = 0

# ----- test_w2_light_scope.py (S-L) -----
PORT = "48624"
# A6 (owner D142 = a): the battle runs at maximum darkness. NewBattleState's
# darkness slider range is 0-15; the host's new-battle config lives in the
# master user folder (Options::getMasterUserFolder() = <user dir>/xcom1/).
DARKNESS = 15
NEW_BATTLE_CFG = os.path.join("xcom1", "battle.cfg")
# LS2's walk back along the C15 path (A6 / F606): from C15_WALK_DEST to C15_H_TILE.
C15_BACK_DEST = C15_H_TILE
C15_BACK_PATH = [(2, 6, 0), (1, 6, 0)]
# LS3's client apply-cost bar in microseconds (A4.5 BAR_L). The orchestrator
# sets it from the S-L.0 measurement; None until then.
BAR_L_US = None
LAYERS = ("ambient", "fire", "items", "units")
ZERO_PROBES = ("deltaUnresolved", "deltaUnsupported", "deltaRemoveMissing", "deltaAddExisting")
PROBE_KEYS = ("desyncSeen", "coopClientBStatePushes", "lastSeqEmitted", "lastSeqApplied",
              "deltaEvsEmitted", "deltaEvsApplied", "deltaUnresolved", "deltaAddExisting",
              "deltaRemoveMissing", "deltaUnsupported", "deltaApplyUsLast", "deltaApplyUsMax",
              "lastDelta", "lightLocalCalls", "lightWholeCalls", "lightUsMax", "lastLight")
# noteClientLight's per-recompute log line (the per-seq record of lastLight).
LIGHT_RE = re.compile(r"\[coop-light\] seq=(\d+) kind=(\S*) layer=(\d+) pos=\((-?\d+),(-?\d+),(-?\d+)\) "
                      r"radius=(\d+) terrain=(\d) whole=(\d) us=(\d+)")


# ===================== probes =====================


def probes(gc):
    es = event_state(gc)
    assert es.get("ok"), f"event_state failed on {gc.name}: {es}"
    return {k: es.get(k) for k in PROBE_KEYS}


def census(gc, tag):
    """light_census {dump:true} on `gc`; the dump is decoded to `bytes` and
    written to <user_dir>/light_<tag>.bin (`path`)."""
    r = gc.cmd({"cmd": "light_census", "dump": True})
    assert r.get("ok"), f"light_census failed on {gc.name}: {r}"
    data = base64.b64decode(r.pop("dump"))
    assert len(data) == r["mapSizeXYZ"] * len(LAYERS), (
        f"light_census dump on {gc.name}: {len(data)} bytes for {r['mapSizeXYZ']} tiles")
    path = os.path.join(gc.user_dir, f"light_{tag}.bin")
    with open(path, "wb") as f:
        f.write(data)
    r["bytes"] = data
    r["path"] = path
    return r


def census_mismatch(ch, cc):
    """The census fields that differ between two machines: layer names,
    'shade', 'mapSizeXYZ'."""
    out = [l for l in LAYERS if ch["layers"][l] != cc["layers"][l]]
    if ch["shade"] != cc["shade"]:
        out.append("shade")
    if ch["mapSizeXYZ"] != cc["mapSizeXYZ"]:
        out.append("mapSizeXYZ")
    return out


def tile_diffs(a, b):
    """Tile indices whose LL_MAX light bytes differ between dumps a and b."""
    n = min(len(a), len(b)) // len(LAYERS)
    w = len(LAYERS)
    return [i for i in range(n) if a[w * i:w * i + w] != b[w * i:w * i + w]]


def coords(c, i):
    sx, sy = c["mapSizeX"], c["mapSizeY"]
    return (i % sx, (i // sx) % sy, i // (sx * sy))


def fmt_tiles(ca, cb, idx, n=10):
    """First `n` of `idx` as '(x,y,z) a[4] b[4]'."""
    w = len(LAYERS)
    return [f"{coords(ca, i)} {list(ca['bytes'][w * i:w * i + w])} {list(cb['bytes'][w * i:w * i + w])}"
            for i in idx[:n]]


def census_view(c):
    return {"layers": c["layers"], "shade": c["shade"], "nonZero": c["nonZero"],
            "personalLight": c["personalLight"], "globalShade": c["globalShade"], "dump": c["path"]}


def tile_light(c, t):
    """The LL_MAX light bytes [ambient, fire, items, units] of tile `t` in
    census `c` (tile index = x + y*sizeX + z*sizeX*sizeY, as coords())."""
    i = t[0] + t[1] * c["mapSizeX"] + t[2] * c["mapSizeX"] * c["mapSizeY"]
    w = len(LAYERS)
    return list(c["bytes"][w * i:w * i + w])


def tiles_light(ch, cc, tiles):
    """{'x,y,z': {'host': [4], 'client': [4]}} for each tile in `tiles`."""
    return {f"{t[0]},{t[1]},{t[2]}": {"host": tile_light(ch, t), "client": tile_light(cc, t)} for t in tiles}


def write_night_cfg(user_dir):
    """A6 mechanism (1): the host's new-battle config with the darkness slider
    at DARKNESS, written before the game starts, so NewBattleState::load()
    reads it when the NEW BATTLE screen opens (every other key falls back to
    the same default index the no-file path selects)."""
    path = os.path.join(user_dir, NEW_BATTLE_CFG)
    with open(path, "w", encoding="ascii", newline="\n") as f:
        f.write(f"darkness: {DARKNESS}\n")
    return path


def cfg_darkness(user_dir):
    """The `darkness:` value in the machine's battle.cfg as the game last
    wrote it (NewBattleState::save(), called again at newbattle_ok), or the
    reason it could not be read."""
    path = os.path.join(user_dir, NEW_BATTLE_CFG)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            m = re.search(r"^darkness:\s*(\d+)", f.read(), re.M)
    except OSError as e:
        return f"unreadable: {e}"
    return int(m.group(1)) if m else "no darkness key"


def classify(host, client, ch0, cc0, tag):
    """The staleness classifier (A4.5, R7): light_recompute on BOTH machines,
    a second census, and per machine the tiles the recompute changed."""
    rh, rc = host.cmd({"cmd": "light_recompute"}), client.cmd({"cmd": "light_recompute"})
    if not (rh.get("ok") and rc.get("ok")):
        return {"verdict": "light_recompute failed", "host": rh, "client": rc}
    ch1, cc1 = census(host, tag + "_recomputed"), census(client, tag + "_recomputed")
    hs, cs = tile_diffs(ch0["bytes"], ch1["bytes"]), tile_diffs(cc0["bytes"], cc1["bytes"])
    post = tile_diffs(ch1["bytes"], cc1["bytes"])
    if cs and not hs:
        verdict = "CLIENT-stale"
    elif hs and not cs:
        verdict = "HOST-stale only"
    elif hs and cs:
        verdict = "BOTH-stale"
    else:
        verdict = "NEITHER-stale"
    if post or census_mismatch(ch1, cc1):
        verdict += " (census still differs after the recompute on both: hidden input)"
    return {"verdict": verdict,
            "hostStale": len(hs), "hostStaleFirst (before after)": fmt_tiles(ch0, ch1, hs),
            "clientStale": len(cs), "clientStaleFirst (before after)": fmt_tiles(cc0, cc1, cs),
            "postRecomputeDiff": len(post), "postRecomputeFirst (host client)": fmt_tiles(ch1, cc1, post),
            "dumps": {"host": ch1["path"], "client": cc1["path"]}}


def census_check(host, client, ch, cc, tag):
    """Census equality (all four layers and shade); on a mismatch the
    classifier runs. Returns (fails, evidence)."""
    mism = census_mismatch(ch, cc)
    diff = tile_diffs(ch["bytes"], cc["bytes"])
    ev = {"mismatch": mism, "tilesDiffer": len(diff), "first (host client)": fmt_tiles(ch, cc, diff),
          "host": census_view(ch), "client": census_view(cc), "classifier": None}
    fails = []
    if mism or diff:
        ev["classifier"] = classify(host, client, ch, cc, tag)
        fails.append(f"light census differs {mism}: {len(diff)} tile(s), first (host client) "
                     f"{ev['first (host client)']}; classifier {ev['classifier']['verdict']}")
    return fails, ev


def baseline(host, client, tag):
    """light_recompute on BOTH machines, then the baseline census. Returns
    (evidence, error, (host census, client census)); error names STOP-IF L2
    when the census differs. The censuses are None when the recompute failed."""
    rh, rc = host.cmd({"cmd": "light_recompute"}), client.cmd({"cmd": "light_recompute"})
    if not (rh.get("ok") and rc.get("ok")):
        return ({"recompute": {"host": rh, "client": rc}},
                f"baseline light_recompute failed: host={rh} client={rc}", (None, None))
    ch, cc = census(host, tag + "_baseline"), census(client, tag + "_baseline")
    mism = census_mismatch(ch, cc)
    diff = tile_diffs(ch["bytes"], cc["bytes"])
    ev = {"mismatch": mism, "tilesDiffer": len(diff), "first (host client)": fmt_tiles(ch, cc, diff),
          "host": census_view(ch), "client": census_view(cc),
          "recomputeUs": {"host": rh.get("us"), "client": rc.get("us")}}
    if mism or diff:
        return ev, (f"STOP-IF L2: baseline light census differs after light_recompute on both machines "
                    f"{mism}: {len(diff)} tile(s), first (host client) {ev['first (host client)']}; "
                    f"dumps host={ch['path']} client={cc['path']}"), (ch, cc)
    if not (ch["personalLight"] is True and cc["personalLight"] is True):
        return ev, (f"baseline: personalLight host={ch['personalLight']} client={cc['personalLight']} "
                    f"(want true on both)"), (ch, cc)
    if not (ch["nonZero"]["units"] > 0 and cc["nonZero"]["units"] > 0):
        return ev, (f"baseline: nonZero.units host={ch['nonZero']['units']} "
                    f"client={cc['nonZero']['units']} (want > 0: no unit light to move)"), (ch, cc)
    return ev, None, (ch, cc)


def light_lines(gc, seqs, timeout=5.0):
    """{seq: [(kind, layer, pos, radius, terrain, whole, us), ...]} from the
    machine's own openxcom.log `[coop-light]` lines, for every seq in `seqs`,
    read with a bounded wait for the log write to land."""
    path = os.path.join(gc.user_dir, "openxcom.log")
    want = set(seqs)
    deadline = time.time() + timeout
    found = {}
    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        found = {}
        for m in LIGHT_RE.finditer(text):
            s = int(m.group(1))
            if s in want:
                found.setdefault(s, []).append(
                    (m.group(2), int(m.group(3)), (int(m.group(4)), int(m.group(5)), int(m.group(6))),
                     int(m.group(7)), int(m.group(8)), int(m.group(9)), int(m.group(10))))
        if want <= set(found) or time.time() >= deadline:
            return found
        time.sleep(0.25)


def light_view(p):
    return {k: p[k] for k in ("lightLocalCalls", "lightWholeCalls", "lightUsMax", "deltaApplyUsLast",
                              "deltaApplyUsMax", "deltaEvsApplied", "lastSeqApplied", "lastLight")}


def common_fails(host, client, ph, pc, what):
    """A4.5 common checks after the action (the census is checked by the
    caller): hash_now full clean, desyncSeen false, the four must-be-0 delta
    probes 0 on both."""
    fails = []
    try:
        assert_hash_clean(host, client, full=True, what=what)
    except AssertionError as e:
        fails.append(f"hash_now full not clean: {dc.short(e, 600)}")
    if ph["desyncSeen"] or pc["desyncSeen"]:
        fails.append(f"desyncSeen host={ph['desyncSeen']} client={pc['desyncSeen']} (want false on both)")
    for k in ZERO_PROBES:
        for name, p in (("host", ph), ("client", pc)):
            if p[k] != 0:
                fails.append(f"{name} {k}={p[k]} (want 0)")
    return fails


def delta_of(before, after, key):
    return (after[key] or 0) - (before[key] or 0)


def finish(fails):
    if fails:
        raise AssertionError("; ".join(fails))


# ===================== scenarios =====================


def ls1(host, client, ctx):
    notes = []
    dc.tele_both(host, client, H_ID, C15_H_TILE, C15_H_DIR)
    dc.tu_both(host, client, H_ID)
    base, berr, (bh, bc) = baseline(host, client, "LS1")
    if berr:
        print(f"EVIDENCE LS1: baseline={base}", flush=True)
        raise AssertionError(berr)
    h_tiles = [C15_H_TILE] + C15_WALK_PATH
    before = {"host": probes(host), "client": probes(client)}
    hw = dc.host_walk(host, client, C15_WALK_DEST, None, notes)
    ph, pc = probes(host), probes(client)
    ch, cc = census(host, "LS1_after"), census(client, "LS1_after")
    walk_light = {"baseline": tiles_light(bh, bc, h_tiles), "after": tiles_light(ch, cc, h_tiles)}
    cfails, cev = census_check(host, client, ch, cc, "LS1_after")
    d_local = delta_of(before["client"], pc, "lightLocalCalls")
    d_whole = delta_of(before["client"], pc, "lightWholeCalls")
    print(f"EVIDENCE LS1: walk executed={dc.executed_path(hw)}; baseline mismatch={base['mismatch']} "
          f"nonZero host={base['host']['nonZero']} client={base['client']['nonZero']} "
          f"personalLight host={base['host']['personalLight']} client={base['client']['personalLight']} "
          f"globalShade host={base['host']['globalShade']} client={base['client']['globalShade']}; "
          f"H path tile light [ambient,fire,items,units]={walk_light}; "
          f"after census={cev}; client lightLocalCalls delta={d_local} lightWholeCalls delta={d_whole}; "
          f"client light {light_view(before['client'])}->{light_view(pc)}; "
          f"host desyncSeen={ph['desyncSeen']} client desyncSeen={pc['desyncSeen']}; "
          f"host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; notes={notes}", flush=True)
    fails = list(notes)
    if dc.executed_path(hw) != C15_WALK_PATH:
        fails.append(f"walk executed {dc.executed_path(hw)} (want {C15_WALK_PATH})")
    fails += cfails
    if d_local < 2:
        fails.append(f"client lightLocalCalls delta={d_local} (want >= 2: one per walk_step)")
    if d_whole != 0:
        fails.append(f"client lightWholeCalls delta={d_whole} (want 0)")
    fails += common_fails(host, client, ph, pc, "LS1")
    finish(fails)


def ls2(host, client, ctx):
    notes = []
    # A6 / F606: LS2 stages its own stale light instead of depending on LS1's
    # leftover (LS1's classifier recomputes both machines and heals it).
    dc.tu_both(host, client, H_ID)
    base, berr, (bh, bc) = baseline(host, client, "LS2")
    if berr:
        print(f"EVIDENCE LS2: baseline={base}", flush=True)
        raise AssertionError(berr)
    h_tiles = [C15_WALK_DEST] + C15_BACK_PATH
    pre_walk = probes(client)
    hw = dc.host_walk(host, client, C15_BACK_DEST, None, notes)
    # Evidence only: the census right after the walk, BEFORE the cycle. No
    # classifier here (its light_recompute would heal the staged stale light).
    ch0, cc0 = census(host, "LS2_walked"), census(client, "LS2_walked")
    d0 = tile_diffs(ch0["bytes"], cc0["bytes"])
    pre = {"mismatch": census_mismatch(ch0, cc0), "tilesDiffer": len(d0),
           "first (host client)": fmt_tiles(ch0, cc0, d0)}
    before = {"host": probes(host), "client": probes(client)}
    walk_light = {"baseline": tiles_light(bh, bc, h_tiles), "walked": tiles_light(ch0, cc0, h_tiles)}
    walk_calls = {k: delta_of(pre_walk, before["client"], k) for k in ("lightLocalCalls", "lightWholeCalls")}
    seq0 = before["client"]["lastSeqApplied"] or 0
    turn0 = dc.end_turn_cycle(host, client, notes)
    hs, cs = battle_state(host), battle_state(client)
    ph, pc = probes(host), probes(client)
    log = event_log(client, tail=250)
    st_seqs = [e["seq"] for e in log if e.get("seq", 0) > seq0 and e.get("kind") == "side_transition"]
    kinds = [(e["seq"], e["kind"]) for e in log if e.get("seq", 0) > seq0]
    lines = light_lines(client, st_seqs)
    ch, cc = census(host, "LS2_after"), census(client, "LS2_after")
    walk_light["after cycle"] = tiles_light(ch, cc, h_tiles)
    cfails, cev = census_check(host, client, ch, cc, "LS2_after")
    d_local = delta_of(before["client"], pc, "lightLocalCalls")
    d_whole = delta_of(before["client"], pc, "lightWholeCalls")
    print(f"EVIDENCE LS2: baseline mismatch={base['mismatch']} globalShade host={base['host']['globalShade']} "
          f"client={base['client']['globalShade']}; walk back executed={dc.executed_path(hw)}; "
          f"client light calls during the walk={walk_calls}; "
          f"H path tile light [ambient,fire,items,units]={walk_light}; "
          f"census after the walk, before the cycle={pre}; turn {turn0} -> host=({hs.get('turn')},"
          f"{hs.get('side')}) client=({cs.get('turn')},{cs.get('side')}); client evs applied in the cycle="
          f"{kinds}; side_transition seqs={st_seqs}; client [coop-light] lines at those seqs={lines}; "
          f"after census={cev}; client lightWholeCalls delta={d_whole} lightLocalCalls delta={d_local}; "
          f"client light {light_view(before['client'])}->{light_view(pc)}; "
          f"host desyncSeen={ph['desyncSeen']} client desyncSeen={pc['desyncSeen']}; "
          f"host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; notes={notes}", flush=True)
    fails = list(notes)
    if dc.executed_path(hw) != C15_BACK_PATH:
        fails.append(f"walk back executed {dc.executed_path(hw)} (want {C15_BACK_PATH})")
    if (hs.get("turn"), hs.get("side"), cs.get("turn"), cs.get("side")) != (turn0 + 1, FACTION_PLAYER,
                                                                             turn0 + 1, FACTION_PLAYER):
        fails.append(f"not on player turn {turn0 + 1} on both: host=({hs.get('turn')},{hs.get('side')}) "
                     f"client=({cs.get('turn')},{cs.get('side')})")
    if not st_seqs:
        fails.append(f"the client applied no side_transition in the cycle (evs {kinds})")
    fails += cfails
    if d_whole != len(st_seqs):
        fails.append(f"client lightWholeCalls delta={d_whole} (want {len(st_seqs)}: one per side_transition "
                     f"applied, seqs {st_seqs})")
    for s in st_seqs:
        last = (lines.get(s) or [None])[-1]
        if not last or last[5] != 1:
            fails.append(f"side_transition seq {s}: last light recompute {last} (want whole-map)")
    fails += common_fails(host, client, ph, pc, "LS2")
    finish(fails)


def ls3(host, client, ctx):
    notes = []
    sa = dc.both(host, client, {"cmd": "battle_set_unit_state", "unit": H_ID, "specab": SPECAB_BURNFLOOR},
                 ("specab",))
    dc.tele_both(host, client, H_ID, C15B_H_TILE, C15B_H_DIR)
    dc.tu_both(host, client, H_ID)
    base, berr, _ = baseline(host, client, "LS3")
    if berr:
        print(f"EVIDENCE LS3: specab={sa.get('specab')} baseline={base}", flush=True)
        raise AssertionError(berr)
    rr = client.cmd({"cmd": "light_probe_reset"})
    if not rr.get("ok"):
        notes.append(f"light_probe_reset on the client: {rr}")
    before = {"host": probes(host), "client": probes(client)}
    path0 = {t: dc.tile(host, t) for t in C15B_WALK_PATH}
    hw = dc.host_walk(host, client, C15B_WALK_DEST, SEED_C15, notes)
    path1 = {t: dc.tile(host, t) for t in C15B_WALK_PATH}
    ph, pc = probes(host), probes(client)
    ch, cc = census(host, "LS3_after"), census(client, "LS3_after")
    cfails, cev = census_check(host, client, ch, cc, "LS3_after")
    d_local = delta_of(before["client"], pc, "lightLocalCalls")
    d_whole = delta_of(before["client"], pc, "lightWholeCalls")
    changed = [t for t in C15B_WALK_PATH if path0[t] != path1[t]]
    fire = {f"{t[0]},{t[1]}": {"before": (path0[t] or {}).get("fire"), "after": (path1[t] or {}).get("fire"),
                               "smoke": (path1[t] or {}).get("smoke")} for t in C15B_WALK_PATH}
    print(f"EVIDENCE LS3: specab={sa.get('specab')} seed={SEED_C15} walk executed={dc.executed_path(hw)}; "
          f"host walked tiles changed={changed} fire={fire}; light_probe_reset={rr}; "
          f"client lightWholeCalls delta={d_whole} lightLocalCalls delta={d_local} "
          f"deltaApplyUsMax(window)={pc['deltaApplyUsMax']} lightUsMax(window)={pc['lightUsMax']} "
          f"lastLight={pc['lastLight']}; BAR_L_US={BAR_L_US}; baseline mismatch={base['mismatch']}; "
          f"after census={cev}; client light {light_view(before['client'])}->{light_view(pc)}; "
          f"host desyncSeen={ph['desyncSeen']} client desyncSeen={pc['desyncSeen']}; "
          f"host lastDelta={ph['lastDelta']} client lastDelta={pc['lastDelta']}; notes={notes}", flush=True)
    fails = list(notes)
    if dc.executed_path(hw) != C15B_WALK_PATH:
        fails.append(f"walk executed {dc.executed_path(hw)} (want {C15B_WALK_PATH})")
    if not changed:
        fails.append("the burning floor changed no walked tile on the host (SEED_C15 premise)")
    fails += cfails
    if d_whole != 0:
        fails.append(f"client lightWholeCalls delta={d_whole} (want 0)")
    if d_local < 3:
        fails.append(f"client lightLocalCalls delta={d_local} (want >= 3)")
    if BAR_L_US is None:
        fails.append("BAR_L not set (S-L.0 pending)")
    elif (pc["deltaApplyUsMax"] or 0) > BAR_L_US:
        fails.append(f"client deltaApplyUsMax(window)={pc['deltaApplyUsMax']} us (want <= BAR_L_US {BAR_L_US})")
    fails += common_fails(host, client, ph, pc, "LS3")
    finish(fails)


SCENARIOS = (("LS1", ls1), ("LS2", ls2), ("LS3", ls3))


# ===================== bring-up =====================


def night_precondition(host, client):
    """A6 boot precondition on BOTH machines: light_census globalShade ==
    DARKNESS, and after light_recompute the census `units` layer is non-zero
    on H's tile. Prints one EVIDENCE line; returns the failure text or None."""
    c0 = {"host": census(host, "boot"), "client": census(client, "boot")}
    rh, rc = host.cmd({"cmd": "light_recompute"}), client.cmd({"cmd": "light_recompute"})
    c1 = {"host": census(host, "boot_recomputed"), "client": census(client, "boot_recomputed")}
    pos = {}
    for name, gc in (("host", host), ("client", client)):
        u = session.units_by_id(battle_state(gc)).get(H_ID) or {}
        pos[name] = (u.get("x"), u.get("y"), u.get("z"))
    h_light = {name: (tile_light(c1[name], pos[name]) if None not in pos[name] else None) for name in pos}
    shade = {name: c0[name]["globalShade"] for name in c0}
    cfg = {"host": cfg_darkness(host.user_dir), "client": cfg_darkness(client.user_dir)}
    print(f"EVIDENCE boot-night: host battle.cfg darkness after newbattle_ok={cfg['host']} "
          f"(client {cfg['client']}); globalShade host={shade['host']} client={shade['client']} "
          f"(want {DARKNESS}); nonZero before recompute host={c0['host']['nonZero']} "
          f"client={c0['client']['nonZero']}; light_recompute ok host={rh.get('ok')} client={rc.get('ok')}; "
          f"after recompute nonZero host={c1['host']['nonZero']} client={c1['client']['nonZero']}; "
          f"H={H_ID} tile host={pos['host']} client={pos['client']} light [ambient,fire,items,units] "
          f"host={h_light['host']} client={h_light['client']}; dumps host={c1['host']['path']} "
          f"client={c1['client']['path']}", flush=True)
    if shade["host"] != DARKNESS or shade["client"] != DARKNESS:
        return (f"night precondition: globalShade host={shade['host']} client={shade['client']} "
                f"(want {DARKNESS}; host battle.cfg darkness={cfg['host']})")
    if not (rh.get("ok") and rc.get("ok")):
        return f"night precondition: light_recompute failed host={rh} client={rc}"
    if not all(h_light[n] and h_light[n][3] > 0 for n in h_light):
        return (f"night precondition: units light on H's tile host={h_light['host']} "
                f"client={h_light['client']} (want units > 0 on both)")
    return None


def boot(host, client):
    cfg_path = write_night_cfg(host.user_dir)
    print(f"[w2p2-sl] night config written before the host starts: {cfg_path} (darkness: {DARKNESS})",
          flush=True)
    raw.bring_up_lobby(host, client, PORT)
    seated = {}
    session.drive_to_battlescape(host, client, seated, seat_count=2,
                                 pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP}))
    hs, cs = battle_state(host), battle_state(client)
    assert hs.get("mapFingerprint") == MAP_FP and cs.get("mapFingerprint") == MAP_FP, (
        f"mapFingerprint host={hs.get('mapFingerprint')!r} client={cs.get('mapFingerprint')!r}, "
        f"baked MAP_FP={MAP_FP!r} (SEED_MAP {SEED_MAP})")
    pinned = pin_ai_neutral(host, client, tag="w2p2-sl")
    assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
    h_ids = sorted(u["id"] for u in hs["units"] if u.get("coop") == COOP_SEAT_0
                   and u.get("faction") == FACTION_PLAYER and not u.get("isOut"))
    assert h_ids and h_ids[0] == H_ID, f"first host-seat soldier {h_ids[:1]} (baked H={H_ID})"
    session.wait_host_idle(host, client, timeout=30)
    assert_hash_clean(host, client, full=True, what="bring-up")
    nerr = night_precondition(host, client)
    assert nerr is None, nerr
    ph = probes(host)
    print(f"[w2p2-sl] boot ok: MAP_FP={MAP_FP!r} turn={hs['turn']} H={H_ID} pinned={pinned} "
          f"DARKNESS={DARKNESS} SEED_C15={SEED_C15} BAR_L_US={BAR_L_US} "
          f"host lastSeqEmitted={ph['lastSeqEmitted']}", flush=True)
    return {}


def main():
    t0 = time.time()
    host = GameClient("host", 49844, make_user_dir("w2p2_light_scope_host"))
    client = GameClient("client", 49845, make_user_dir("w2p2_light_scope_client"))
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
                print(f"[w2p2-sl] shutdown {gc.name}: {dc.short(e)}", flush=True)
    passed = [n for n, _ in SCENARIOS if results.get(n)]
    failed = [n for n, _ in SCENARIOS if not results.get(n)]
    print(f"\ntest_w2_light_scope: {len(passed)}/{len(SCENARIOS)} passed "
          f"(pass={passed} fail={failed}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
