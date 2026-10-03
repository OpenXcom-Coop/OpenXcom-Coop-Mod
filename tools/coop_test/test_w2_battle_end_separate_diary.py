"""W2-P7 S-C-B2 - test_w2_battle_end_separate_diary.py: a SEPARATE campaign guest's diary and medals reach the owner's
world. This mission's statistics record is copied into the owner's world with its own id; the guest's diary mission ids
and kills are remapped onto it; the host's awarded commendations ride the YAML and the owner's world records them as the
host awarded them (docs rewrite/prompts/w2p7_sc_design.md section 3.3, AMENDMENT P7-6 section 4.3; owner D155 (a),
D202 (a), D218; mechanism ruling MR13; P7-6 Q1 (a)).

The construction is C28P's guest's-OWN-kill path (CONSTANTS rewrite/w2p7sc-task0/t0/CONSTANTS.md T0-6 (iv), re-pinned
SEED_P=2 for 558349bc8), imported from test_w2_battle_end_separate (b1). On BOTH machines the data-only mod
tools/coop_test/mods/Coop_Medal_Test is loaded (PR-20: one commendation STR_COOP_MEDAL_TEST, criteria totalMissions [1]
- every surviving participant earns it on its first mission), so the host awards the guest the medal in its debriefing
and its merged copy (COPY) carries it. Both boots use the guest-kill construction: the kill gives COPY both the medal
(any survivor earns totalMissions [1]) and a diary kill under this mission's host id.

Row C28P-medal (boot 1, diary-file port 47220). After the client's OK it returns to its own world (B1 green). GREEN
(commit S-C-B2.2): the returned guest's diary gains exactly one NEW mission id (OWN_BEFORE's list + [newId], MR13); the
new id resolves in the owner's world to the host COPY's mission (type, region, success); and the commendations equal the
host COPY's and include STR_COOP_MEDAL_TEST. RED (this commit, B1 green in place): B1 copies only D155's scalar keys, not
the diary, so the returned guest's diary lacks the new mission id (cell 2 red).

Row C28P-kill (boot 2, diary-file port 47221). GREEN: the returned guest's killList carries this battle's kills under
the NEW mission id, each turn remapped turn += (newId - hostId) * 300, matching the host COPY's kills under its host id.
RED: the returned guest has no kill with the new mission id (the diary is not copied; cell 2 red).

WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_battle_end_separate_diary.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import test_w2_battle_end_separate as b1
from harness import GameClient, make_user_dir

# ----- this file's constants -----
MEDAL_TYPE = "STR_COOP_MEDAL_TEST"        # Coop_Medal_Test's one commendation (criteria totalMissions [1], PR-20)
MEDAL_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Medal_Test")
COOP_PORT_MEDAL = "47220"                 # AMENDMENT P7-6 section 4 (F4545): the diary file = 47220-47222
COOP_PORT_KILL = "47221"


def precheck_diary(copy):
    """The host's merged 'Guest Zzz' copy must carry this battle in its diary before any OK: the guest's kill was
    credited, exactly one mission id (a fresh guest on its first battle), a kill under it, and the host-awarded medal
    (D202 (a)). A miss is a FIXTURE-STOP (the mod did not load, or the kill was not credited)."""
    if copy.get("kills", 0) < 1:
        return (f"the host's merged 'Guest Zzz' copy has kills {copy.get('kills')!r} (want >= 1: the guest's shot was "
                f"credited)")
    diary = copy.get("diary") or {}
    ids = diary.get("missionIdList") or []
    if len(ids) != 1:
        return (f"the host's merged copy diary.missionIdList={ids} (want exactly one mission id: a fresh guest on its "
                f"first battle)")
    host_id = ids[0]
    kills = [k for k in (diary.get("killList") or []) if k.get("mission") == host_id]
    if not kills:
        return (f"the host's merged copy diary.killList has no kill with mission=={host_id}: {diary.get('killList')}")
    comms = [c.get("type") for c in (diary.get("commendations") or [])]
    if MEDAL_TYPE not in comms:
        return (f"the host's merged copy did not earn {MEDAL_TYPE} (commendations {comms}): is Coop_Medal_Test loaded "
                f"on both machines?")
    return None


def medal_stage(rid, host, client, ctx):
    """C28P-medal pre-cell: the guest's-own-kill construction at the diary file's medal port, with the medal precheck."""
    b1._stage_common(rid, host, client, ctx, COOP_PORT_MEDAL, b1.guest_kill, precheck_diary)


def kill_stage(rid, host, client, ctx):
    """C28P-kill pre-cell: the guest's-own-kill construction at the diary file's kill port, with the medal precheck."""
    b1._stage_common(rid, host, client, ctx, COOP_PORT_KILL, b1.guest_kill, precheck_diary)


def _client_return(host, client, ctx):
    """Press the client's OK, wait for its own clean geoscape, read the returned guest's soldier_record. Returns
    (fails, rec): `fails` is the OK/geoscape failures (empty when the client returned cleanly, B1 green)."""
    ok1 = b1.press_ok(client)
    ok, secs = b1.wait_until(lambda: b1.geo_clean(client), b1.OK_S) if ok1["pressed"] else (False, 0)
    rec = b1.soldier_rec(client, sid=ctx["guestId"])
    ctx.setdefault("clientReturn", {}).update({"ok": ok1, "reached": ok, "secs": secs,
                                               "clientStack": b1.stack(client), "returnedRecord": rec})
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"client OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not ok:
        f.append(f"client not on a clean GeoscapeState within {b1.OK_S}s of its OK (stack {b1.stack(client)})")
    return f, rec


def cell_medal(host, client, ctx):
    """C28P-medal cell 2 (the RED cell): the returned guest's diary gains this mission's id (MR13), it resolves to the
    host COPY's mission, and the commendations == the host COPY's and include the medal (D202 a). RED: the diary lacks
    the new mission id (B1 does not copy the diary)."""
    f, rec = _client_return(host, client, ctx)
    if f:
        return f
    before = ctx.get("ownBefore") or {}
    copy = ctx.get("copy") or {}
    bdiary, rdiary, cdiary = (before.get("diary") or {}), (rec.get("diary") or {}), (copy.get("diary") or {})
    before_ids = bdiary.get("missionIdList") or []
    ret_ids = rdiary.get("missionIdList") or []
    copy_ids = cdiary.get("missionIdList") or []
    new_ids = [i for i in ret_ids if i not in before_ids]
    ctx["medal"] = {"beforeIds": before_ids, "retIds": ret_ids, "copyIds": copy_ids,
                    "retComms": rdiary.get("commendations"), "copyComms": cdiary.get("commendations")}
    # (1, the RED check) the returned diary = OWN_BEFORE's list + exactly one new mission id (MR13)
    if ret_ids[:len(before_ids)] != before_ids or len(new_ids) != 1:
        return [f"returned guest diary.missionIdList={ret_ids} != OWN_BEFORE's {before_ids} + [newId] "
                f"(this mission was not copied into the owner's world, MR13)"]
    new_id = new_ids[0]
    host_id = copy_ids[-1] if copy_ids else None
    rmiss = {m.get("id"): m for m in (rdiary.get("missions") or []) if isinstance(m, dict)}
    cmiss = {m.get("id"): m for m in (cdiary.get("missions") or []) if isinstance(m, dict)}
    rm, cm = (rmiss.get(new_id) or {}), (cmiss.get(host_id) or {})
    out = []
    # (2) the new id resolves in the owner's world to the host COPY's mission (type, region, success)
    for k in ("found", "type", "region", "success"):
        if rm.get(k) != cm.get(k):
            out.append(f"returned mission[{new_id}].{k}={rm.get(k)!r} != host COPY mission[{host_id}].{k}={cm.get(k)!r}")
    # (3) commendations == the host COPY's and include the medal (D202 a)
    rcomm = sorted((c.get("type"), c.get("noun"), c.get("level")) for c in (rdiary.get("commendations") or []))
    ccomm = sorted((c.get("type"), c.get("noun"), c.get("level")) for c in (cdiary.get("commendations") or []))
    if rcomm != ccomm:
        out.append(f"returned guest commendations {rcomm} != host COPY's {ccomm} (D202 a)")
    if not any(c.get("type") == MEDAL_TYPE for c in (rdiary.get("commendations") or [])):
        out.append(f"returned guest commendations lack {MEDAL_TYPE}: {rdiary.get('commendations')}")
    return out


def cell_kill(host, client, ctx):
    """C28P-kill cell 2 (the RED cell): the returned guest's killList carries this battle's kills under the NEW mission
    id, turn remapped turn += (newId - hostId) * 300 (MR13), matching the host COPY. RED: no kill with the new mission
    id (B1 does not copy the diary)."""
    f, rec = _client_return(host, client, ctx)
    if f:
        return f
    before = ctx.get("ownBefore") or {}
    copy = ctx.get("copy") or {}
    bdiary, rdiary, cdiary = (before.get("diary") or {}), (rec.get("diary") or {}), (copy.get("diary") or {})
    before_ids = bdiary.get("missionIdList") or []
    ret_ids = rdiary.get("missionIdList") or []
    copy_ids = cdiary.get("missionIdList") or []
    new_ids = [i for i in ret_ids if i not in before_ids]
    new_id = new_ids[0] if len(new_ids) == 1 else None
    host_id = copy_ids[-1] if copy_ids else None
    rkills = sorted((k for k in (rdiary.get("killList") or []) if new_id is not None and k.get("mission") == new_id),
                    key=lambda k: k.get("turn") or 0)
    ckills = sorted((k for k in (cdiary.get("killList") or []) if k.get("mission") == host_id),
                    key=lambda k: k.get("turn") or 0)
    ctx["kill"] = {"newId": new_id, "hostId": host_id, "retKills": rdiary.get("killList"),
                   "copyKills": cdiary.get("killList")}
    # (1, the RED check) a kill under the new mission id exists
    if not rkills:
        return [f"returned guest has no kill with the new mission id (newId={new_id}, returned killList="
                f"{rdiary.get('killList')}): the diary/kills were not remapped into the owner's world (MR13)"]
    out = []
    if len(rkills) != len(ckills):
        out.append(f"returned guest has {len(rkills)} kill(s) under mission {new_id}, the host COPY has {len(ckills)} "
                   f"under mission {host_id} (MR13: the kills are copied 1:1)")
    offset = (new_id - host_id) * 300
    for rk, ck in zip(rkills, ckills):
        want = (ck.get("turn") or 0) + offset
        if rk.get("turn") != want:
            out.append(f"returned kill turn {rk.get('turn')!r} != host COPY turn {ck.get('turn')!r} + "
                       f"(newId {new_id} - hostId {host_id}) * 300 = {want}")
    return out


def c28p_medal_cells(host, client, ctx):
    return [
        ("1 the client's display-only debriefing, equal to the host's", lambda: b1.cell_debriefs(host, client, ctx)),
        ("2 the guest's diary records this mission and the host's medal", lambda: cell_medal(host, client, ctx)),
    ]


def c28p_kill_cells(host, client, ctx):
    return [
        ("1 the client's display-only debriefing, equal to the host's", lambda: b1.cell_debriefs(host, client, ctx)),
        ("2 the guest's kills are remapped under the new mission id", lambda: cell_kill(host, client, ctx)),
    ]


def main():
    t0, results, walls = time.time(), {}, {}
    # Two sequential boots (fresh host/client each), the Coop_Medal_Test mod loaded on BOTH machines via make_user_dir.
    boots = [("C28P-medal", medal_stage, c28p_medal_cells), ("C28P-kill", kill_stage, c28p_kill_cells)]
    for rid, stage_fn, cells_fn in boots:
        slug = rid.lower().replace("-", "_")
        host = GameClient("host", 0, make_user_dir(f"w2p7scb2_{slug}_host", mods=[MEDAL_MOD]))
        client = GameClient("client", 0, make_user_dir(f"w2p7scb2_{slug}_client", mods=[MEDAL_MOD]))
        try:
            host.spawn(); client.spawn(); host.connect(); client.connect()
            b1.run_row(rid, host, client, results, walls, stage_fn, cells_fn)
        finally:
            for gc in (host, client):
                try:
                    gc.shutdown()
                except Exception as e:
                    print(f"[w2p7-scb2] shutdown {gc.name}: {b1.short(e)}", flush=True)
    order = ["C28P-medal", "C28P-kill"]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_battle_end_separate_diary: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
