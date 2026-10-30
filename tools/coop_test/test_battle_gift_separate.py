"""test_battle_gift_separate.py: in a SEPARATE campaign a soldier given during the battle belongs to its receiver
afterwards in the one shared save - a host soldier given to the partner stays at the host's base as the partner's
soldier, the partner's soldier given to the host stays there as the host's, a soldier who died after being given lies
in the receiver's memorial (the memorial lists the dead soldiers its player owns), and the debriefing names a given
soldier as its receiver's. One boot: SEPARATE co-op, the mixed squad of session.bring_up_separate_guest_battle (three
host soldiers and the client's soldier "Guest Zzz" seated on the host's craft), coop port 47602, dirs
battle_gift_separate_host / battle_gift_separate_client.

The host renames H1 and H2 before the mission, to names no roster rolls, and every record is found by those names (and
by id: one save, so each soldier is exactly one record with the same id on both machines).

Pins (ids are the same on both machines): squad [1, 2, 3], the client's soldier id 16; H1 = 1, H2 = 2 (soldierId
squad[0] / squad[1]), renamed on the host to H1_NAME / H2_NAME; G = 16 (the unit named "Guest Zzz"); seats
{1: 0, 2: 0, 3: 0, 16: 1} on both; HOST_BASE (the index of the base holding H1) per boot (probe). Boot guard: before
the mission G is one record on each machine, the client's (owner 1, coop 1), at HOST_BASE.
  gifts_during_battle  the three gifts by the battle_gift test command (host {1, owner 1}, host {2, owner 1}, client
      {16, owner 0}; each landing before the next, each receiver dismisses its notice): gifts_land (precondition),
      receivers_own (the host's records carry the receivers as owners), gifts_common.
  battle_ends  the ending (every live hostile killed, then H2, END TURN on both, the host's NextTurnState closed):
      mission_ended (precondition), debrief_names_receivers (both page-2 lists name a given soldier as its receiver's).
  client_return  the client's OK through its follow-ups: client_ok (precondition), client_save_updated (the client's
      copy of the save: G the host's, H1 the client's, both at HOST_BASE with this mission counted; H2 dead, the
      client's).
  host_drain  the host's OK and its drain: host_ok (precondition), host_save_updated (G and H1 as in
      client_save_updated), receiver_memorial (H2 in the memorial as the client's).
  both_machines  each_soldier_once (G, H1 and H2 exactly one record each, equal on both machines), machines_common (no
      new crash file since the bring-up; the client wrote no save).

One EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a
cell whose precondition failed FAILs "not reached (<cell> failed)". A boot step past its bound prints ONE CAPTURE boot
line and fails every row "boot". Ids come from probes. No skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_battle_gift_separate.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
import test_ownerless_units as OWN  # noqa: E402
import test_battle_gift as GF  # noqa: E402
import test_battle_gift_keep as KEEP  # noqa: E402
import test_battle_end_separate as SEP  # noqa: E402

PORT = "47602"                            # the coop session port (no other test uses it)
STEP_S = 30                               # every bounded staging wait (measured: gifts land in 0.1 s)
KILL_S = 45                               # chain_settled after each kill (measured: 2.2-2.6 s)
DEBRIEF_S = 60                            # the host's DebriefingState after END TURN (measured: 0.05 s)
CLIENT_DEBRIEF_S = 20                     # the client's display-only DebriefingState (measured: 0.05 s)
OK_S = 10                                 # a machine's geoscape after its OK (SEP's OK_S; measured: 0.05 s)
DRAIN_S = 60                              # the host's OK + follow-ups down to its GeoscapeState
SQUAD, GUEST_ID, H1, H2, G = [1, 2, 3], 16, 1, 2, 16
GUEST_NAME = "Guest Zzz"                  # session.bring_up_separate_guest_battle's renamed client soldier
H1_NAME, H2_NAME = "Qqq One", "Qqq Two"   # the host's renames (no roster pool name holds "Qqq")
TITLE = "Aliens defeated"
HOST_SEAT, CLIENT_SEAT = 0, 1             # a soldier's owner / coop in a SEPARATE save
HOST_ROSTER, CLIENT_ROSTER = SEP.ROSTER_NAMES     # ("HostPlayer", "ClientPlayer")
ROWS = (("gifts_during_battle", ("gifts_land", "receivers_own", "gifts_common")),
        ("battle_ends", ("mission_ended", "debrief_names_receivers")),
        ("client_return", ("client_ok", "client_save_updated")),
        ("host_drain", ("host_ok", "host_save_updated", "receiver_memorial")),
        ("both_machines", ("each_soldier_once", "machines_common")))
BRIEF = ("id", "where", "baseIndex", "name", "coopName", "owner", "coop", "craftId", "coopCraft", "coopCraftType",
         "missions", "kills", "rank", "recovery")
SAME = ("id", "where", "baseIndex", "name", "owner", "coop", "craftId", "missions", "kills", "rank", "recovery",
        "currentStats", "initialStats")    # the fields each_soldier_once compares across the two machines
WHO = (("G", GUEST_NAME, G), ("H1", H1_NAME, H1), ("H2", H2_NAME, H2))

units = G3F.units
not_reached = OWN.not_reached


def recs(gc, sid=None, name=None):
    return SEP.soldier_recs(gc, sid=sid, name=name)[0]


def brief(rr):
    return [{k: r.get(k) for k in BRIEF} for r in rr]


def bases(gc):
    return gc.cmd({"cmd": "get_soldiers"}).get("bases") or []


def save_view(gc):
    """G / H1 / H2 in this machine's save: the records by name and the number of records holding each id."""
    return {k: {"recs": recs(gc, name=n), "idCount": len(recs(gc, sid=i))} for k, n, i in WHO}


def given_records(view, keys, want):
    """The differences of `view`'s records `keys` from `want` (one record each, its id, the fields in want[key])."""
    bad = []
    for k, _n, i in WHO:
        if k not in keys:
            continue
        rr, n = view[k]["recs"], view[k]["idCount"]
        if len(rr) != 1 or n != 1:
            bad.append(f"{k}: records by name {len(rr)}, by id {i} {n} (want 1 / 1)")
            continue
        w = dict(want[k], id=i)
        diff = {f: [rr[0].get(f), v] for f, v in w.items() if rr[0].get(f) != v}
        if diff:
            bad.append(f"{k}: [got, want] {diff}")
    return bad


def expected(pre):
    """Each soldier's record after the mission: G the host's, H1 the client's, both at HOST_BASE; H2 dead, the
    client's; each with this mission counted."""
    hb, m = pre["HOST_BASE"], pre["missions"]
    return {"G": {"where": "base", "baseIndex": hb, "owner": HOST_SEAT, "coop": HOST_SEAT, "missions": m["G"] + 1},
            "H1": {"where": "base", "baseIndex": hb, "owner": CLIENT_SEAT, "coop": CLIENT_SEAT, "missions": m["H1"] + 1},
            "H2": {"where": "dead", "baseIndex": -1, "owner": CLIENT_SEAT, "coop": CLIENT_SEAT,
                   "missions": m["H2"] + 1}}


def bring_up(host, client):
    """bring_up_separate_guest_battle on PORT with the pre-mission hook (the host renames H1 and H2, then the record
    probes), the pins and the guard, pin_ai_neutral, the host idle, every hash bucket EQUAL, then the crash baseline."""
    m, pre = (host, client), {}

    def roster(h, c):
        rolled = [(recs(h, sid=s) or [{}])[0].get("name") for s in (H1, H2)]
        pre["rolled"] = rolled
        pre["rename"] = [h.cmd({"cmd": "rename_soldier", "name": n or "?", "newName": new}).get("ok")
                         for n, new in zip(rolled, (H1_NAME, H2_NAME))]
        pre["HOST_BASE"] = next((i for i, b in enumerate(bases(h))
                                 if any(s.get("id") == H1 for s in b.get("soldiers") or [])), None)
        pre["H1"], pre["H2"] = recs(h, sid=H1), recs(h, sid=H2)
        pre["guest"] = [recs(gc, name=GUEST_NAME) for gc in (h, c)]
        pre["missions"] = {"G": (pre["guest"][0] or [{}])[0].get("missions"),
                           "H1": (pre["H1"] or [{}])[0].get("missions"), "H2": (pre["H2"] or [{}])[0].get("missions")}

    GF.guarded("boot", lambda: (host.spawn(), client.spawn(), host.connect(), client.connect()), m)
    squad, guest = GF.guarded("boot", lambda: session.bring_up_separate_guest_battle(host, client, port=PORT,
                                                                                  pre_mission_start=roster), m)
    view = {}
    want = {"squad": SQUAD, "guestId": GUEST_ID, "rename": [True, True], "hostNames": [[H1_NAME], [H2_NAME]],
            "h1": [H1], "h2": [H2], "g": [G], "seats": [[0, 0, 0, 1]] * 2, "unitNames": [[H1_NAME, H2_NAME]] * 2}

    def pins():
        uh, uc = units(host), units(client)
        view.update({"squad": squad, "guestId": guest, "rename": pre.get("rename"),
                     "hostNames": [[r.get("name") for r in pre.get(k) or []] for k in ("H1", "H2")],
                     "h1": sorted(i for i, u in uh.items() if u.get("soldierId") == squad[0]),
                     "h2": sorted(i for i, u in uh.items() if u.get("soldierId") == squad[1]),
                     "g": sorted(i for i, u in uh.items() if u.get("name") == GUEST_NAME),
                     "seats": [[(u.get(i) or {}).get("coop") for i in (1, 2, 3, G)] for u in (uh, uc)],
                     "unitNames": [[(u.get(i) or {}).get("name") for i in (H1, H2)] for u in (uh, uc)]})
        assert view == want, f"boot pins {view} (want {want})"
        gv = [[[r.get(k) for k in ("id", "where", "baseIndex", "owner", "coop")] for r in rr] for rr in pre["guest"]]
        gw = [[[G, "base", pre["HOST_BASE"], CLIENT_SEAT, CLIENT_SEAT]]] * 2
        assert pre["HOST_BASE"] is not None and gv == gw and None not in pre["missions"].values(), \
            f"boot guard: {GUEST_NAME!r} records host / client [id, where, baseIndex, owner, coop] {gv} (want {gw}: " \
            f"one record, the client's, at the host's base {pre['HOST_BASE']}); missions {pre['missions']}"
    GF.guarded("boot", pins, m)
    GF.guarded("boot", lambda: session.pin_ai_neutral(host, client, tag="test_battle_gift_separate"), m)
    GF.guarded("boot", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    GF.guarded("boot", lambda: session.assert_hash_clean(host, client, full=True, what="boot"), m)
    return dict(view, HOST_BASE=pre["HOST_BASE"], missions=pre["missions"], rolled=pre.get("rolled")), pre, \
        session._crash_log_snapshot()


def row_gifts_during_battle(host, client, ctx, crash0):
    cells, ev = {}, {}
    landed, miss = KEEP.gifts_in_order([(host, H1, 1), (host, H2, 1), (client, G, 0)], host, client, ev)
    got = [GF.coops(host, client, u) for u in (H1, H2, G)]
    ok = landed and got == [[1, 1], [1, 1], [0, 0]]
    cells["gifts_land"] = (ok, f"H1 / H2 / G coop host/client {got} (want [1, 1] / [1, 1] / [0, 0], each landing "
                               f"within {STEP_S} s){'; ' + miss if miss else ''}")
    ev["giftLines"] = GF.gift_lines(host)[-3:]
    if ok:
        rr = [recs(host, sid=H1), recs(host, sid=H2), recs(host, name=GUEST_NAME)]
        ev["hostRecs"] = [brief(r) for r in rr]
        oc = [[[x.get("owner"), x.get("coop")] for x in lst] for lst in rr]
        cells["receivers_own"] = (oc == [[[1, 1]], [[1, 1]], [[0, 0]]],
                                  f"host soldier_record {{id: {H1}}} / {{id: {H2}}} / {{name: {GUEST_NAME!r}}} "
                                  f"[owner, coop] {oc} (want [[1, 1]] / [[1, 1]] / exactly one [0, 0]: the host writes "
                                  f"the receiver into a SEPARATE soldier's owner)")
    else:
        not_reached(cells, ("receivers_own",), "gifts_land failed")
    cells["gifts_common"] = G3F.common(host, client, crash0)
    return cells, ev


def debrief_view(gc):
    d = gc.cmd({"cmd": "debrief_state"})
    return {k: d.get(k) for k in ("shown", "onTop", "displayOnly", "title")}, [s.get("name") for s in d.get("soldiers") or []]


def row_battle_ends(host, client, ctx, crash0):
    cells, ev = {}, {}
    ds = [G3F.es(host, "desyncSeen"), G3F.es(client, "desyncSeen")]
    hostiles = [u["id"] for u in battle_state(host).get("units", []) if u.get("faction") == 1 and not u.get("isOut")]
    kills = []
    for uid in hostiles:
        r = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        ok, secs, _s = SEP.chain_settled(host, client, timeout=KILL_S)
        kills.append([uid, r.get("killed"), ok, secs])
    r2 = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": H2})
    ok2, secs2, _s = SEP.chain_settled(host, client, timeout=KILL_S)
    h2 = [(units(gc).get(H2) or {}).get("status") for gc in (host, client)]
    SEP.end_turn_both(host, client)
    nt = SEP.close_host_nextturn(host, timeout=DEBRIEF_S)
    dok, dsecs = SEP.wait_until(lambda: "DebriefingState" in SEP.stack(host), DEBRIEF_S)
    hview, hnames = debrief_view(host) if dok else ({}, [])
    be = SEP.record(host)
    cok, csecs = SEP.wait_until(lambda: debrief_view(client)[0] == {"shown": True, "onTop": True, "displayOnly": True,
                                                                    "title": TITLE}, CLIENT_DEBRIEF_S)
    cview, cnames = debrief_view(client)
    ev.update(desyncSeen=ds, hostiles=len(hostiles), kills=kills, killH2=[r2.get("killed"), ok2, secs2], H2status=h2,
              nextTurn=nt and {k: nt.get(k) for k in ("ok", "handled")}, hostDebriefS=dsecs, hostView=hview,
              battleEnd={k: be.get(k) for k in ("reason", "aborted")}, clientDebriefS=csecs, clientView=cview,
              pageHost=hnames, pageClient=cnames)
    end_ok = (ds == [False, False] and bool(hostiles) and all(k[2] for k in kills) and ok2
              and h2 == [SEP.STATUS_DEAD] * 2
              and dok and hview == {"shown": True, "onTop": True, "displayOnly": False, "title": TITLE}
              and (be.get("reason"), be.get("aborted")) == ("aliensDown", False) and cok)
    cells["mission_ended"] = (end_ok, f"desyncSeen {ds}; {len(hostiles)} hostiles, every kill settled within "
                                      f"{KILL_S} s {all(k[2] for k in kills)}; H2 settled {ok2}, status host/client "
                                      f"{h2} (want 6 / 6); the host's DebriefingState {dok} ({dsecs} s) {hview} (want "
                                      f"shown, onTop, not displayOnly, {TITLE!r}); battleEnd {ev['battleEnd']} (want "
                                      f"aliensDown, not aborted); the client's display-only DebriefingState {cok} "
                                      f"({csecs} s) {cview}")
    ctx["end"] = end_ok
    if not end_ok:
        not_reached(cells, ("debrief_names_receivers",), "mission_ended failed")
        return cells, ev
    hp, cp = f"[{CLIENT_ROSTER}] ", f"[{HOST_ROSTER}] "
    want = {"host": ([hp + H1_NAME, GUEST_NAME], [H1_NAME, hp + GUEST_NAME]),
            "client": ([H1_NAME, cp + GUEST_NAME], [cp + H1_NAME, GUEST_NAME])}
    got = {"host": hnames, "client": cnames}
    bad = [f"{side} page 2 {got[side]} lacks {n!r}" for side, (yes, _no) in want.items() for n in yes if n not in got[side]]
    bad += [f"{side} page 2 {got[side]} holds {n!r}" for side, (_yes, no) in want.items() for n in no if n in got[side]]
    cells["debrief_names_receivers"] = (not bad, "; ".join(bad)
                                        + " (the debriefing names a given soldier as its receiver's)"
                                        if bad else f"host page 2 {hnames}; client page 2 {cnames}")
    return cells, ev


def row_client_return(host, client, ctx, crash0):
    cells, ev = {}, {}
    ok1, reached, secs = SEP.client_ok_through_followups(client, ev, "ret")
    ok = ok1.get("pressed") is True and reached
    cells["client_ok"] = (ok, f"client OK {ok1}; geo_clean {reached} within {OK_S} s ({secs} s); chain "
                              f"{(ev.get('ret') or {}).get('clientChain')}")
    ctx["client"] = save_view(client)
    ev["records"] = {k: dict(v, recs=brief(v["recs"])) for k, v in ctx["client"].items()}
    if not ok or not ctx.get("end"):
        not_reached(cells, ("client_save_updated",), "client_ok failed" if not ok else "mission_ended failed")
        return cells, ev
    bad = given_records(ctx["client"], ("G", "H1", "H2"), expected(ctx["pre"]))
    cells["client_save_updated"] = (not bad, "; ".join(bad) + " (the client's copy of the save)" if bad else
                                    f"G the host's, H1 the client's, both at base {ctx['pre']['HOST_BASE']}; H2 dead, "
                                    f"the client's")
    return cells, ev


def row_host_drain(host, client, ctx, crash0):
    cells, ev = {}, {}
    okh = SEP.press_ok(host)
    reached, screens = SEP.drain(host, timeout=DRAIN_S) if okh["pressed"] else (False, [])
    ok = okh["pressed"] and reached
    cells["host_ok"] = (ok, f"host OK {okh}; GeoscapeState {reached} within {DRAIN_S} s; screens {screens}")
    ctx["host"] = save_view(host)
    ev["records"] = {k: dict(v, recs=brief(v["recs"])) for k, v in ctx["host"].items()}
    if not ok or not ctx.get("end"):
        not_reached(cells, ("host_save_updated", "receiver_memorial"),
                    "host_ok failed" if not ok else "mission_ended failed")
        return cells, ev
    want = expected(ctx["pre"])
    bad = given_records(ctx["host"], ("G", "H1"), want)
    cells["host_save_updated"] = (not bad, "; ".join(bad) if bad else
                                  f"G the host's (id {G}), H1 the client's (id {H1}), both at base "
                                  f"{ctx['pre']['HOST_BASE']}")
    bad = given_records(ctx["host"], ("H2",), want)
    cells["receiver_memorial"] = (not bad, "; ".join(bad) + " (a soldier who died after being given lies in the "
                                                          "receiver's memorial)" if bad else
                                  f"H2 dead once, owner {CLIENT_SEAT} (the client's memorial)")
    return cells, ev


def row_both_machines(host, client, ctx, crash0):
    cells, ev = {}, {}
    if not ("host" in ctx and "client" in ctx and ctx.get("end")):
        not_reached(cells, ("each_soldier_once",), "mission_ended, client_return or host_drain failed")
    else:
        bad = []
        for k, _n, i in WHO:
            hv, cv = ctx["host"][k], ctx["client"][k]
            if [len(hv["recs"]), hv["idCount"], len(cv["recs"]), cv["idCount"]] != [1, 1, 1, 1]:
                bad.append(f"{k}: records by name / id host {len(hv['recs'])} / {hv['idCount']}, client "
                           f"{len(cv['recs'])} / {cv['idCount']} (want one each)")
                continue
            diff = {f: [hv["recs"][0].get(f), cv["recs"][0].get(f)] for f in SAME
                    if hv["recs"][0].get(f) != cv["recs"][0].get(f)}
            if diff:
                bad.append(f"{k}: host / client differ {diff}")
        cells["each_soldier_once"] = (not bad, "; ".join(bad) if bad else
                                      "G, H1 and H2 one record each, equal on both machines")
    zd = None
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        zd = str(e)[:300]
    crash = sorted(session._crash_log_snapshot() - crash0)
    cells["machines_common"] = (not crash and zd is None, f"new crash files since the bring-up {crash} (want none); "
                                                          f"the client's zero-disk {zd or 'ok'}")
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("battle_gift_separate_host"))
    client = GameClient("client", None, make_user_dir("battle_gift_separate_client"))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, pre, crash0 = bring_up(host, client)
            print(f"[test_battle_gift_separate] boot: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (setup failure, see the CAPTURE boot line)")
        else:
            ctx = {"pre": pre}
            for row, fn in (("gifts_during_battle", row_gifts_during_battle), ("battle_ends", row_battle_ends),
                            ("client_return", row_client_return), ("host_drain", row_host_drain),
                            ("both_machines", row_both_machines)):
                fails += G3F.run_row(row, rows[row], lambda fn=fn: fn(host, client, ctx, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_separate: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
