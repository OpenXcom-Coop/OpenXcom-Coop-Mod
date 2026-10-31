"""test_battle_end_separate_diary.py: in a SEPARATE campaign the client's soldier who fought in the host's battle
keeps this mission in its diary, its kills under it and the medals the host awarded, in the one shared save as the
client reads it after its OK (equal to the host's record).

The construction is battle_end_helpers' guest kill (BES._stage_common with BES.guest_kill: the client's soldier
"Guest Zzz" makes the OWN kill of the last alien at SEED_P). On BOTH machines the data-only mod
tools/coop_test/mods/Coop_Medal_Test is loaded (one commendation STR_COOP_MEDAL_TEST, criteria totalMissions [1]: every
surviving participant earns it on its first mission), so the host awards the guest the medal in its debriefing and the
host's record of it (COPY, read before any OK) carries it, with a diary kill under this mission's id. OWN_BEFORE is the
client's record of the guest from before the battle.

The cells are numbered and checked in order; a failed cell ends its row and the rest are "not reached". In both rows,
cell 1 is the client's display-only debriefing, equal to the host's; cell 3 is the host's OK + drain (the guest stays
one living soldier, the client's); cell 4 is the client's after-battle chain, equal to the host's drained follow-ups
and to CHAIN_DIARY.

Row mission_and_medal (boot 1, port 47220), cell 2: after its OK the client's record of the guest has exactly one new
diary mission id (OWN_BEFORE's list + [newId]), the host COPY's id (one save: one mission list), resolving to the same
mission (type, region, success); and the commendations equal the host COPY's and include STR_COOP_MEDAL_TEST.

Row kills_listed (boot 2, port 47221), cell 2: the client's record of the guest lists this battle's kills under the new
mission id, the host COPY's id, one for one with the host COPY's kills and on the same turns.

No skip path; exit 0 only when every row passes, 2 otherwise.

Run:  python tools/coop_test/test_battle_end_separate_diary.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import battle_end_helpers as BES
from harness import GameClient, make_user_dir

# ----- this file's constants -----
MEDAL_TYPE = "STR_COOP_MEDAL_TEST"        # Coop_Medal_Test's one commendation (criteria totalMissions [1])
MEDAL_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_Medal_Test")
COOP_PORT_MEDAL = "47220"                 # mission_and_medal's boot
COOP_PORT_KILL = "47221"                  # kills_listed's boot
# Both rows' client after-battle chain = the host's drained follow-ups (equal in two capture runs).
CHAIN_DIARY = ["CommendationState", "PromotionsState"]


def precheck_diary(copy):
    """The host's 'Guest Zzz' record must carry this battle in its diary before any OK: the guest's kill was
    credited, exactly one mission id (a fresh guest on its first battle), a kill under it, and the host-awarded medal.
    A miss is a setup failure (the mod did not load, or the kill was not credited)."""
    if copy.get("kills", 0) < 1:
        return (f"the host's 'Guest Zzz' record has kills {copy.get('kills')!r} (want >= 1: the guest's shot was "
                f"credited)")
    diary = copy.get("diary") or {}
    ids = diary.get("missionIdList") or []
    if len(ids) != 1:
        return (f"the host's record diary.missionIdList={ids} (want exactly one mission id: a fresh guest on its "
                f"first battle)")
    host_id = ids[0]
    kills = [k for k in (diary.get("killList") or []) if k.get("mission") == host_id]
    if not kills:
        return (f"the host's record diary.killList has no kill with mission=={host_id}: {diary.get('killList')}")
    comms = [c.get("type") for c in (diary.get("commendations") or [])]
    if MEDAL_TYPE not in comms:
        return (f"the host's record did not earn {MEDAL_TYPE} (commendations {comms}): is Coop_Medal_Test loaded "
                f"on both machines?")
    return None


def medal_stage(rid, host, client, ctx):
    """mission_and_medal pre-cell: the guest's-own-kill construction on COOP_PORT_MEDAL, with the diary precheck."""
    BES._stage_common(rid, host, client, ctx, COOP_PORT_MEDAL, BES.guest_kill, precheck_diary)


def kill_stage(rid, host, client, ctx):
    """kills_listed pre-cell: the guest's-own-kill construction on COOP_PORT_KILL, with the diary precheck."""
    BES._stage_common(rid, host, client, ctx, COOP_PORT_KILL, BES.guest_kill, precheck_diary)


def _client_return(host, client, ctx):
    """Press the client's OK, wait for its clean geoscape, read the client's soldier_record of the guest. Returns
    (fails, rec): `fails` is the OK/geoscape failures (empty when the client returned cleanly)."""
    ok1, ok, secs = BES.client_ok_through_followups(client, ctx, "clientReturn")   # walks its after-battle screens
    rec = BES.soldier_rec(client, sid=ctx["guestId"])
    ctx.setdefault("clientReturn", {}).update({"ok": ok1, "reached": ok, "secs": secs,
                                               "clientStack": BES.stack(client), "returnedRecord": rec})
    f = []
    if not ok1["pressed"]:
        f.append(ok1["note"])
    elif (ok1.get("resp") or {}).get("handled") != "DebriefingState":
        f.append(f"client OK answered {ok1.get('resp')} (want handled DebriefingState)")
    if not ok:
        f.append(f"client not on a clean GeoscapeState within {BES.OK_S}s of its OK (stack {BES.stack(client)})")
    return f, rec


def cell_medal(host, client, ctx):
    """mission_and_medal cell 2: the client's record of the guest gains this mission's id (the host COPY's), it
    resolves to the host COPY's mission, and the commendations == the host COPY's and include the medal."""
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
    # (1) the returned diary = OWN_BEFORE's list + exactly one new mission id
    if ret_ids[:len(before_ids)] != before_ids or len(new_ids) != 1:
        return [f"the client's guest diary.missionIdList={ret_ids} != OWN_BEFORE's {before_ids} + [newId] "
                f"(this mission is not in the client's record)"]
    new_id = new_ids[0]
    host_id = copy_ids[-1] if copy_ids else None
    if new_id != host_id:
        return [f"the client's new diary mission id {new_id} != the host COPY's {host_id} (one save: one mission list)"]
    rmiss = {m.get("id"): m for m in (rdiary.get("missions") or []) if isinstance(m, dict)}
    cmiss = {m.get("id"): m for m in (cdiary.get("missions") or []) if isinstance(m, dict)}
    rm, cm = (rmiss.get(new_id) or {}), (cmiss.get(host_id) or {})
    out = []
    # (2) the new id resolves on the client to the host COPY's mission (type, region, success)
    for k in ("found", "type", "region", "success"):
        if rm.get(k) != cm.get(k):
            out.append(f"the client's mission[{new_id}].{k}={rm.get(k)!r} != host COPY mission[{host_id}].{k}={cm.get(k)!r}")
    # (3) commendations == the host COPY's and include the medal
    rcomm = sorted((c.get("type"), c.get("noun"), c.get("level")) for c in (rdiary.get("commendations") or []))
    ccomm = sorted((c.get("type"), c.get("noun"), c.get("level")) for c in (cdiary.get("commendations") or []))
    if rcomm != ccomm:
        out.append(f"the client's guest commendations {rcomm} != host COPY's {ccomm} (the client's record keeps "
                   f"the host's medals)")
    if not any(c.get("type") == MEDAL_TYPE for c in (rdiary.get("commendations") or [])):
        out.append(f"the client's guest commendations lack {MEDAL_TYPE}: {rdiary.get('commendations')}")
    return out


def cell_kill(host, client, ctx):
    """kills_listed cell 2: the client's record of the guest lists this battle's kills under the new mission id, the
    host COPY's id, one for one with the host COPY's kills, on the same turns."""
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
    # (1) a kill under the new mission id exists, and that id is the host COPY's (one save: one mission list)
    if not rkills:
        return [f"the client's guest has no kill with the new mission id (newId={new_id}, its killList="
                f"{rdiary.get('killList')})"]
    out = []
    if new_id != host_id:
        out.append(f"the client's new diary mission id {new_id} != the host COPY's {host_id}")
    if len(rkills) != len(ckills):
        out.append(f"the client's guest has {len(rkills)} kill(s) under mission {new_id}, the host COPY has "
                   f"{len(ckills)} under mission {host_id} (want one for one)")
    for rk, ck in zip(rkills, ckills):
        if rk.get("turn") != ck.get("turn"):
            out.append(f"the client's kill turn {rk.get('turn')!r} != host COPY turn {ck.get('turn')!r}")
    return out


def medal_cells(host, client, ctx):
    return [
        ("1 the client's display-only debriefing, equal to the host's", lambda: BES.cell_debriefs(host, client, ctx)),
        ("2 the guest's diary records this mission and the host's medal", lambda: cell_medal(host, client, ctx)),
    ] + chain_cells(host, client, ctx)


def kill_cells(host, client, ctx):
    return [
        ("1 the client's display-only debriefing, equal to the host's", lambda: BES.cell_debriefs(host, client, ctx)),
        ("2 the guest's kills are listed under this mission's id", lambda: cell_kill(host, client, ctx)),
    ] + chain_cells(host, client, ctx)


def chain_cells(host, client, ctx):
    """Cell 3 = the host's OK + drain (BES.cell_host_ok), cell 4 = the client's follow-up chain."""
    return [
        ("3 the host's OK + drain; the guest stays the client's", lambda: BES.cell_host_ok(host, client, ctx)),
        ("4 the client's chain",
         lambda: BES.cell_client_chain(host, client, ctx, "clientReturn", "hostOk", CHAIN_DIARY)),
    ]


def main():
    t0, results, walls = time.time(), {}, {}
    # Two sequential boots (fresh host/client each), the Coop_Medal_Test mod loaded on BOTH machines via make_user_dir.
    boots = [("mission_and_medal", medal_stage, medal_cells), ("kills_listed", kill_stage, kill_cells)]
    for rid, stage_fn, cells_fn in boots:
        slug = rid.lower().replace("-", "_")
        host = GameClient("host", 0, make_user_dir(f"battle_end_separate_diary_{slug}_host", mods=[MEDAL_MOD]))
        client = GameClient("client", 0, make_user_dir(f"battle_end_separate_diary_{slug}_client", mods=[MEDAL_MOD]))
        try:
            host.spawn(); client.spawn(); host.connect(); client.connect()
            BES.run_row(rid, host, client, results, walls, stage_fn, cells_fn)
        finally:
            for gc in (host, client):
                try:
                    gc.shutdown()
                except Exception as e:
                    print(f"[test_battle_end_separate_diary] shutdown {gc.name}: {BES.short(e)}", flush=True)
    order = ["mission_and_medal", "kills_listed"]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_battle_end_separate_diary: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) in "
          f"{time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
