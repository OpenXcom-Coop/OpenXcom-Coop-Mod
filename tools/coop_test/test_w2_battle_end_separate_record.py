"""W2-P7 S-C-B2.3 - test_w2_battle_end_separate_record.py: a SEPARATE guest's record follow-ups - the mission-id remap
when the owner's world already holds a mission (F5549) and the owner's diary under a host with diaries off (F5554)
(docs rewrite/prompts/w2p7_sc_design.md: the P7-6 C re-pin section 5 (Q-C1 a) and the P7-6 B2.3 pin section 5, PB-4..PB-8;
veto V-C4; owner D155 (a), D202 (a)).

Both rows use C28P's guest's-OWN-kill construction (b1.guest_kill at b1.SEED_P 2 with b1's map pin, B1's 3/3 pin) through
b1._stage_common with a `pre_extra` hook (PB-8) that runs on the client's own geoscape before OWN_BEFORE and the
battle-entry snapshot: the client's test lever `mission_stats_pad {count: 1, soldierId: <the guest>}` (PB-7) appends one
MissionStatistics (type coop_test_pad) to the client's world and its id to the guest's diary. Both campaigns are fresh
(F6232): the pad gets id 0, the host's mission id 0, the return's new id 1.

Row C28P-shift (boot 1, port 47204; the F5549 guard row): the return keeps the owner's own diary id 0 (the pad, F5548's
tail rule), appends the host's mission as id 1 (== COPY's mission 0 on type, region, success; sepReturn.missionCopied 1)
and moves every copied kill to mission 1 with turn + 300. Expected PASS on the red and the green (the tip's B2 code); a
red here is a B2 defect (B23-2).

Row C28P-nodiary (boot 2, port 47222; F5554, V-C4): the host boots with soldierDiaries off (make_user_dir options), the
client with it on; Coop_Medal_Test on both. GREEN (S-C-B2.3.2): the returned guest's diary ids == OWN_BEFORE's [0] +
[newId], its commendations == COPY's incl. STR_COOP_MEDAL_TEST, its kills under mission 1 as many as COPY's under mission
0. RED (S-C-B2.3.1): V5 serializes the guest row under the host's option (no `diary`) and the overlay removes the owner's
diary - the returned guest has no diary (cell 2).

Pre-cell guards (a miss is a FIXTURE-STOP: a CAPTURE line, then the row FAILs "pre-cell"): b1's (bring-up, map pin, the
guest's kill, the host debriefing pin, fatalVote 0); the pad reply ids [0]; OWN_BEFORE's diary ids OWN_IDS with
missions[0] = the pad; COPY's kills >= 1, diary ids COPY_IDS and a kill under mission 0; C28P-nodiary also the option
guard (host soldierDiaries false, client true) and COPY's medal.
WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when both rows pass, 2 otherwise.

Run:  python tools/coop_test/test_w2_battle_end_separate_record.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_w2_battle_end_separate as b1
import test_w2_battle_end_separate_diary as dia
from harness import GameClient, make_user_dir

# ----- this file's constants (the P7-6 B2.3 pin section 5) -----
PORT_SHIFT = "47204"        # PB-6: B's reserved, unused port (block comment test_w2_battle_end_separate.py :77)
PORT_NODIARY = "47222"      # PB-6: B's reserved, unused port (block comment test_w2_battle_end_separate_diary.py :44)
PAD_TYPE = "coop_test_pad"  # PB-7: mission_stats_pad's MissionStatistics type
OWN_IDS = [0]               # F6232: the client's fresh world -> the pad's id 0, appended to the guest's diary
COPY_IDS = [0, 0]           # F6232: the contributed pad id 0 + the host's own mission id 0 (the host's fresh world)
RETURNED_IDS = [0, 1]       # F6232: the owner's own 0 kept (F5548) + newId = size() == 1 (coopSeparateReturn)
TURN_SHIFT = 300            # F6232: (newId 1 - hostId 0) * 300 (makeTurnUnique; the overlay's kill remap)
OPTION = "soldierDiaries"   # PB-4 / F6222: the host's per-player OXC option (Options.cpp :203, default true)
RELOAD_WAIT_S = 10          # R-B23-1 (F6361): bound on the wait for the client's world reload before the pad


# ===================== pre_extra hooks and the pre-cell guards =====================


def read_options(h, c, ctx):
    """Both machines' raw soldierDiaries (option_values, TestServer :8684) into ctx['options']."""
    ctx["options"] = {gc.name: (gc.cmd({"cmd": "option_values", "ids": [OPTION]}).get("values") or {}).get(OPTION)
                      for gc in (h, c)}
    return ctx["options"]


def wait_world_reloaded(h, c, ctx):
    """R-B23-1 (F6361): BasescapeState::btnGeoscapeClick clears insideCoopBase BEFORE its LoadGameState replaces the
    client's world (the load runs 10 frames later), so session.py's "client back on geoscape" wait can return while
    the outgoing world is still live. Wait (bounded RELOAD_WAIT_S) until the client's top state is GeoscapeState and
    no LoadGameState is on its stack; a timeout is a FIXTURE-STOP (CAPTURE of both machines, the row FAILs)."""
    ready = lambda st: st if st and st[-1] == "GeoscapeState" and not any("LoadGameState" in x for x in st) else None
    t0 = time.time()
    try:
        st = c.wait_for("client world reload done", lambda: ready(b1.stack(c)), timeout=RELOAD_WAIT_S)
    except TimeoutError as e:
        b1.capture("world reload", f"client stack {b1.stack(c)} after {RELOAD_WAIT_S} s (want top GeoscapeState, "
                                   f"no LoadGameState): {b1.short(e)}", (h, c))
    ctx["worldReady"] = {"waited": round(time.time() - t0, 2), "stack": st}


def pad(h, c, ctx):
    """`pre_extra` (C28P-shift): the client's mission_stats_pad {count: 1, soldierId: the guest}; reply ids [0]."""
    read_options(h, c, ctx)   # evidence only here (C28P-nodiary guards it)
    wait_world_reloaded(h, c, ctx)   # R-B23-1: never pad the outgoing world (F6361)
    sid = b1.soldier_rec(c, name="Guest Zzz").get("id")
    r = c.cmd({"cmd": "mission_stats_pad", "count": 1, "soldierId": sid})
    ctx["pad"] = {"soldierId": sid, "resp": {k: r.get(k) for k in ("ok", "ids", "size", "error")}}
    if r.get("ids") != [0]:
        b1.capture("pad", f"client mission_stats_pad {ctx['pad']} (want ids [0], F6232)", (h, c))


def pad_nodiary(h, c, ctx):
    """`pre_extra` (C28P-nodiary): the option guard (host soldierDiaries false, client true), then `pad`."""
    vals = read_options(h, c, ctx)
    if vals != {"host": False, "client": True}:
        b1.capture("option guard", f"option_values {OPTION} {vals} (want host False, client True)", (h, c))
    pad(h, c, ctx)


def precheck(ctx, copy, medal=False):
    """OWN_BEFORE (read right after the pad) and COPY (the host's merged copy, before any OK). Returns a reason or None."""
    own = (ctx.get("ownBefore") or {}).get("diary") or {}
    cd = copy.get("diary") or {}
    om = (own.get("missions") or [{}])[0]
    bad = []
    if own.get("missionIdList") != OWN_IDS or not om.get("found") or om.get("type") != PAD_TYPE:
        bad.append(f"OWN_BEFORE diary.missionIdList={own.get('missionIdList')} missions={own.get('missions')} "
                   f"(want {OWN_IDS}, missions[0] found with type {PAD_TYPE!r})")
    if (copy.get("kills", 0) < 1 or cd.get("missionIdList") != COPY_IDS
            or not any(k.get("mission") == 0 for k in cd.get("killList") or [])):
        bad.append(f"COPY kills={copy.get('kills')!r} diary.missionIdList={cd.get('missionIdList')} "
                   f"killList={cd.get('killList')} (want kills >= 1, {COPY_IDS}, >= 1 kill with mission 0)")
    if medal and dia.MEDAL_TYPE not in [x.get("type") for x in cd.get("commendations") or []]:
        bad.append(f"COPY commendations {cd.get('commendations')} lack {dia.MEDAL_TYPE} (is Coop_Medal_Test loaded?)")
    return "; ".join(bad) or None


def shift_stage(rid, host, client, ctx):
    b1._stage_common(rid, host, client, ctx, PORT_SHIFT, b1.guest_kill, lambda copy: precheck(ctx, copy),
                     pre_extra=pad)


def nodiary_stage(rid, host, client, ctx):
    b1._stage_common(rid, host, client, ctx, PORT_NODIARY, b1.guest_kill, lambda copy: precheck(ctx, copy, True),
                     pre_extra=pad_nodiary)


# ===================== cells =====================


def diaries(ctx):
    """(the returned guest's diary, COPY's diary)."""
    rec = (ctx.get("clientReturn") or {}).get("returnedRecord") or {}
    return rec.get("diary") or {}, (ctx.get("copy") or {}).get("diary") or {}


def kills_under(diary, mission):
    return sorted((k for k in diary.get("killList") or [] if k.get("mission") == mission),
                  key=lambda k: k.get("turn") or 0)


def cell_shift_ids(host, client, ctx):
    """C28P-shift cell 2: after the client's return, ids == RETURNED_IDS; id 0 = the pad; id 1 == COPY's mission 0;
    sepReturn.missionCopied 1."""
    f, _rec = dia._client_return(host, client, ctx)
    if f:
        return f
    rd, cd = diaries(ctx)
    rm = {m.get("id"): m for m in rd.get("missions") or []}
    cm = {m.get("id"): m for m in cd.get("missions") or []}
    sep = b1.record(client).get("sepReturn") or {}
    ctx["shift"] = {"retIds": rd.get("missionIdList"), "retMissions": rd.get("missions"),
                    "copyMissions": cd.get("missions"), "sepReturn": sep}
    out = []
    if rd.get("missionIdList") != RETURNED_IDS:
        out.append(f"returned diary.missionIdList={rd.get('missionIdList')} (want {RETURNED_IDS}: the owner's own 0 "
                   f"kept, the host's mission appended as 1)")
    r0 = rm.get(0) or {}
    if not r0.get("found") or r0.get("type") != PAD_TYPE:
        out.append(f"returned mission[0]={r0} (want found, type {PAD_TYPE!r})")
    for k in ("found", "type", "region", "success"):
        if (rm.get(1) or {}).get(k) != (cm.get(0) or {}).get(k):
            out.append(f"returned mission[1].{k}={(rm.get(1) or {}).get(k)!r} != COPY mission[0].{k}="
                       f"{(cm.get(0) or {}).get(k)!r}")
    if sep.get("missionCopied") != 1:
        out.append(f"client battleEnd.sepReturn.missionCopied={sep.get('missionCopied')!r} (want 1)")
    return out


def cell_shift_kills(host, client, ctx):
    """C28P-shift cell 3: the returned kills under mission 1 == COPY's under mission 0 (>= 1), each turn + TURN_SHIFT;
    no returned kill keeps mission 0."""
    rd, cd = diaries(ctx)
    rk, ck = kills_under(rd, 1), kills_under(cd, 0)
    ctx["shiftKills"] = {"ret": rd.get("killList"), "copy": cd.get("killList")}
    out = []
    if not ck or len(rk) != len(ck):
        out.append(f"returned kills under mission 1: {len(rk)}, COPY's under mission 0: {len(ck)} (want equal, >= 1)")
    out += [f"returned kill turn {r.get('turn')!r} != COPY's {c.get('turn')!r} + {TURN_SHIFT}"
            for r, c in zip(rk, ck) if r.get("turn") != (c.get("turn") or 0) + TURN_SHIFT]
    if kills_under(rd, 0):
        out.append(f"returned kills keep mission 0: {kills_under(rd, 0)}")
    return out


def cell_nodiary(host, client, ctx):
    """C28P-nodiary cell 2 (the RED cell, F5554): the returned diary ids == OWN_BEFORE's [0] + [newId], commendations ==
    COPY's incl. the medal, kills under mission 1 as many as COPY's under mission 0. RED: no diary at all."""
    f, _rec = dia._client_return(host, client, ctx)
    if f:
        return f
    rd, cd = diaries(ctx)
    comms = lambda d: sorted((x.get("type"), x.get("noun"), x.get("level")) for x in d.get("commendations") or [])
    ctx["nodiary"] = {"retIds": rd.get("missionIdList"), "retComms": comms(rd), "copyComms": comms(cd),
                      "retKills": rd.get("killList"), "copyKills": cd.get("killList")}
    out = []
    if rd.get("missionIdList") != RETURNED_IDS:
        own_ids = ((ctx.get("ownBefore") or {}).get("diary") or {}).get("missionIdList")
        out.append(f"returned diary.missionIdList={rd.get('missionIdList')} (want OWN_BEFORE's {own_ids} + [newId] = "
                   f"{RETURNED_IDS}: the host's diaries-off guest row dropped the owner's diary)")
    if comms(rd) != comms(cd) or dia.MEDAL_TYPE not in [c[0] for c in comms(rd)]:
        out.append(f"returned commendations {comms(rd)} != COPY's {comms(cd)} or lack {dia.MEDAL_TYPE}")
    if len(kills_under(rd, 1)) != len(kills_under(cd, 0)):
        out.append(f"returned kills under mission 1: {len(kills_under(rd, 1))} != COPY's under mission 0: "
                   f"{len(kills_under(cd, 0))}")
    return out


def debriefs(host, client, ctx):
    return ("1 the client's display-only debriefing, equal to the host's", lambda: b1.cell_debriefs(host, client, ctx))


def host_ok(n, host, client, ctx):
    return (f"{n} the host's OK + drain; the merged copy gone", lambda: b1.cell_host_ok(host, client, ctx))


def shift_cells(host, client, ctx):
    return [debriefs(host, client, ctx),
            ("2 the returned diary keeps the owner's mission 0 and appends the host's as 1",
             lambda: cell_shift_ids(host, client, ctx)),
            ("3 the returned kills move to mission 1, turn + 300", lambda: cell_shift_kills(host, client, ctx)),
            host_ok(4, host, client, ctx)]


def nodiary_cells(host, client, ctx):
    return [debriefs(host, client, ctx),
            ("2 a diaries-off host keeps the owner's diary, this mission and the medal",
             lambda: cell_nodiary(host, client, ctx)),
            host_ok(3, host, client, ctx)]


def main():
    t0, results, walls = time.time(), {}, {}
    # Two sequential boots (fresh host/client each): C28P-shift (default options, no mod), then C28P-nodiary (the
    # host's soldierDiaries off for that boot, Coop_Medal_Test on both).
    boots = [("C28P-shift", shift_stage, shift_cells, None, []),
             ("C28P-nodiary", nodiary_stage, nodiary_cells, {OPTION: False}, [dia.MEDAL_MOD])]
    for rid, stage_fn, cells_fn, host_options, mods in boots:
        slug = rid.lower().replace("-", "_")
        host = GameClient("host", 0, make_user_dir(f"w2p7scb23_{slug}_host", mods=mods, options=host_options))
        client = GameClient("client", 0, make_user_dir(f"w2p7scb23_{slug}_client", mods=mods))
        try:
            host.spawn(); client.spawn(); host.connect(); client.connect()
            b1.run_row(rid, host, client, results, walls, stage_fn, cells_fn)
        finally:
            for gc in (host, client):
                try:
                    gc.shutdown()
                except Exception as e:
                    print(f"[w2p7-scb23] shutdown {gc.name}: {b1.short(e)}", flush=True)
    order = ["C28P-shift", "C28P-nodiary"]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_battle_end_separate_record: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
