"""R5-U5 S-C rows X1-X5 (boot X; owner aud-E1-13, VL-U5-6, QU5-8 (a)): in a SEPARATE campaign a soldier given during the
battle belongs to its receiver afterwards - a host soldier given to the partner leaves the host's world and joins the
partner's as a guest at the host's base, the partner's guest given to the host stays in the host's world as an ordinary
host soldier and leaves the partner's, a soldier who died after being given stays in the giver's memorial, and the
debriefing names a given soldier as its receiver's. Boot X: SEPARATE co-op, the mixed squad of
session.bring_up_separate_guest_battle (three host soldiers and the client's guest "Guest Zzz" on the host's craft), coop
port 47602, dirs r5u5_x_host / r5u5_x_client.

Spec: docs repo rewrite/prompts/r5u5_battle_gift_order.md AMENDMENT R5U5-1 section 6 (f) (ORCHESTRATOR RULINGS on it:
QU5-C-1 .. QU5-C-8 (a)) with ORCHESTRATOR RULING R-U5-SC-1: the host renames H1 and H2 before the mission (names no roster
rolls, the "Guest Zzz" device; two SEPARATE worlds started in the same second roll the same roster, F14082) and every name +
initialStats rule uses those names; X4-host compares the kept guest's id with the battle copy's id (COPY_ID, F14084).
Constants: rewrite/r5u5-task0/sc/CONSTANTS.md (boots Xp2, Xa, Xb, Xc).

Pins (Xa, Xb, Xc): squad [1, 2, 3], the client's guest id 8; H1 = 1, H2 = 2 (soldierId squad[0] / squad[1]), renamed on the
host to H1_NAME / H2_NAME; G = 9 (the unit named "Guest Zzz": the merged copy, COPY_ID); seats {1: 0, 2: 0, 3: 0, 9: 1} on
both; CRAFT 1, CRAFT_TYPE "STR_SKYRANGER", FIRST_OWN 0; HOST_BASE_COOP and the hostile count per boot (probes).
  X1  the three gifts by lever (host {1, owner 1}, host {2, owner 1}, client {9, owner 0}; each landing before the next,
      each receiver dismisses its notice): X1-gifts (precondition), X1-owner (the host's records carry the receivers as
      owners), X1-common.
  X2  the ending (C28P-dead's order): every live hostile killed, then H2, END TURN on both, the host's NextTurnState
      closed: X2-end (precondition; then HREC1 / HREC2 / COPY are read), X2-names (both page-2 lists name a given soldier
      as its receiver's).
  X3  the client's OK through its follow-ups: X3-ok (precondition), X3-client (G left the client's world, H1 arrived as a
      guest at the host's base, H2 did not, the return's sepReturn counts).
  X4  the host's OK and its drain: X4-ok (precondition), X4-host (G kept as a host soldier with a fresh id, H1 gone),
      X4-dead (H2 in the host's memorial as the host's: a declared guard, PASS on both builds).
  X5  both worlds: X5-one (G and H1 live exactly once, H2 in exactly one memorial: a declared guard, PASS on both builds),
      X5-common (no new crash file since the bring-up; the client wrote no save).
Red at C1 (the base build): X1-owner, X2-names, X3-client, X4-host. Every other cell PASS.

A soldier in the other world is found by name AND equal initialStats (F13600), never by a display name alone. One
EVIDENCE line per row, then one PASS/FAIL line per cell, then the row verdict. Every row runs after a failure; a cell
whose precondition failed FAILs "not reached (<cell> failed)". A boot step past its bound prints ONE CAPTURE X line and
fails every row "boot". Ids come from probes (S25). WV-D95: run in the foreground to completion. WV-D99 / WV-D100: ONE run
is the result, no skip path; exit 0 only when every cell passes, else 2.

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

PORT = "47602"                            # the coop session port (AMENDMENT R5U5-1 section 3: free)
STEP_S = 30                               # every bounded staging wait (TASK 0: gifts land in 0.1 s)
KILL_S = 45                               # chain_settled after each kill (TASK 0: 2.2-2.6 s)
DEBRIEF_S = 60                            # the host's DebriefingState after END TURN (TASK 0: 0.05 s)
CLIENT_DEBRIEF_S = 20                     # the client's display-only DebriefingState (TASK 0: 0.05 s)
OK_S = 10                                 # a machine's geoscape after its OK (SEP's OK_S; TASK 0: 0.05 s)
DRAIN_S = 60                              # the host's OK + follow-ups down to its GeoscapeState
SQUAD, GUEST_ID, H1, H2, G = [1, 2, 3], 8, 1, 2, 9
COPY_ID = G                               # the battle copy's id (lastId + 1; R-U5-SC-1, F14084)
GUEST_NAME = "Guest Zzz"                  # session.bring_up_separate_guest_battle's renamed client guest
H1_NAME, H2_NAME = "Qqq One", "Qqq Two"   # R-U5-SC-1: the host's renames (no roster pool name holds "Qqq")
CRAFT_TYPE = "STR_SKYRANGER"              # TASK 0 (Xp2, Xa, Xb, Xc)
TITLE = "Aliens defeated"                 # TASK 0 / OF2 S-C
STATUS_DEAD = 6
HOST_ROSTER, CLIENT_ROSTER = SEP.ROSTER_NAMES     # ("HostPlayer", "ClientPlayer")
ROWS = (("X1", ("X1-gifts", "X1-owner", "X1-common")), ("X2", ("X2-end", "X2-names")), ("X3", ("X3-ok", "X3-client")),
        ("X4", ("X4-ok", "X4-host", "X4-dead")), ("X5", ("X5-one", "X5-common")))
BRIEF = ("id", "where", "baseIndex", "name", "coopName", "owner", "coop", "craftId", "coopCraft", "coopCraftType",
         "missions", "kills", "rank", "recovery")

units = G3F.units
not_reached = OWN.not_reached


def recs(gc, sid=None, name=None):
    return SEP.soldier_recs(gc, sid=sid, name=name)[0]


def brief(rr):
    return [{k: r.get(k) for k in BRIEF} for r in rr]


def bases(gc):
    return gc.cmd({"cmd": "get_soldiers"}).get("bases") or []


def same_stats(rr, ref):
    """The records of `rr` whose initialStats equal `ref`'s (a soldier found across worlds, F13600)."""
    want = (ref or {}).get("initialStats")
    return [r for r in rr if want is not None and r.get("initialStats") == want]


def lives_dead(rr):
    return [sum(1 for r in rr if r.get("where") != "dead"), sum(1 for r in rr if r.get("where") == "dead")]


def bring_up(host, client):
    """bring_up_separate_guest_battle on PORT with the pre-mission hook (R-U5-SC-1's renames, then the roster pins), the pins
    and guards, pin_ai_neutral, the host idle, every hash bucket EQUAL, then the crash baseline."""
    m, pre = (host, client), {}

    def roster(h, c):
        rolled = [(recs(h, sid=s) or [{}])[0].get("name") for s in (H1, H2)]
        pre["rolled"] = rolled
        pre["rename"] = [h.cmd({"cmd": "rename_soldier", "name": n or "?", "newName": new}).get("ok")
                         for n, new in zip(rolled, (H1_NAME, H2_NAME))]
        hb = [b for b in bases(h) if any(s.get("id") == H1 for s in b.get("soldiers") or [])]
        pre["HOST_BASE_COOP"] = hb[0].get("coopBaseId") if hb else None
        pre["CRAFT"] = next((s.get("craftId") for b in hb for s in b["soldiers"] if s.get("id") == H1), None)
        pre["H1"], pre["H2"] = recs(h, sid=H1), recs(h, sid=H2)
        cb = bases(c)
        pre["FIRST_OWN"] = next((i for i, b in enumerate(cb) if not b.get("coopBaseFlag") and not b.get("coopIcon")), None)
        pre["guestCoopBase"] = [s.get("coopBase") for b in cb for s in b.get("soldiers") or [] if s.get("name") == GUEST_NAME]
        pre["OWN0"] = recs(c, name=GUEST_NAME)
        pre["clientH1"], pre["clientH2"] = recs(c, name=H1_NAME), recs(c, name=H2_NAME)

    GF.guarded("X", lambda: (host.spawn(), client.spawn(), host.connect(), client.connect()), m)
    squad, guest = GF.guarded("X", lambda: session.bring_up_separate_guest_battle(host, client, port=PORT,
                                                                                  pre_mission_start=roster), m)
    view, own0 = {}, pre.get("OWN0") or []
    guard = {"OWN0": brief(own0), "FIRST_OWN": pre.get("FIRST_OWN"), "CRAFT": pre.get("CRAFT"),
             "HOST_BASE_COOP": pre.get("HOST_BASE_COOP"), "guestCoopBase": pre.get("guestCoopBase"),
             "clientNamed": brief(same_stats(pre.get("clientH1") or [], (pre.get("H1") or [{}])[0])
                                  + same_stats(pre.get("clientH2") or [], (pre.get("H2") or [{}])[0]))}
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
        assert view == want, f"boot X pins {view} (want {want})"
        o = own0[0] if len(own0) == 1 else {}
        assert (len(own0) == 1 and o.get("baseIndex") == pre["FIRST_OWN"] and o.get("coopCraft") == pre["CRAFT"]
                and o.get("coopCraftType") == CRAFT_TYPE and pre["guestCoopBase"] == [pre["HOST_BASE_COOP"]]
                and pre["HOST_BASE_COOP"] is not None), f"boot X guard OWN0 {guard} (want one record: baseIndex FIRST_OWN, " \
                                                        f"coopCraft CRAFT, {CRAFT_TYPE}, coopBase HOST_BASE_COOP)"
        assert not guard["clientNamed"], f"boot X guard: client records named {H1_NAME!r} / {H2_NAME!r} with H1's / " \
                                         f"H2's initialStats {guard['clientNamed']} (want none)"
    GF.guarded("X", pins, m)
    GF.guarded("X", lambda: session.pin_ai_neutral(host, client, tag="r5u5x"), m)
    GF.guarded("X", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    GF.guarded("X", lambda: session.assert_hash_clean(host, client, full=True, what="boot X"), m)
    return dict(view, **{k: guard[k] for k in ("FIRST_OWN", "CRAFT", "HOST_BASE_COOP")}, rolled=pre.get("rolled")), pre, \
        session._crash_log_snapshot()


def row_x1(host, client, ctx, crash0):
    cells, ev = {}, {}
    landed, miss = KEEP.lever_gifts([(host, H1, 1), (host, H2, 1), (client, G, 0)], host, client, ev)
    got = [GF.coops(host, client, u) for u in (H1, H2, G)]
    ok = landed and got == [[1, 1], [1, 1], [0, 0]]
    cells["X1-gifts"] = (ok, f"H1 / H2 / G coop host/client {got} (want [1, 1] / [1, 1] / [0, 0], each landing within "
                             f"{STEP_S} s){'; ' + miss if miss else ''}")
    ev["giftLines"] = GF.gift_lines(host)[-3:]
    if ok:
        rr = [recs(host, sid=H1), recs(host, sid=H2), recs(host, name=GUEST_NAME)]
        ev["hostRecs"] = [brief(r) for r in rr]
        oc = [[[x.get("owner"), x.get("coop")] for x in lst] for lst in rr]
        cells["X1-owner"] = (oc == [[[1, 1]], [[1, 1]], [[0, 0]]],
                             f"host soldier_record {{id: {H1}}} / {{id: {H2}}} / {{name: {GUEST_NAME!r}}} [owner, coop] {oc} "
                             f"(want [[1, 1]] / [[1, 1]] / exactly one [0, 0]: the host writes the receiver into a "
                             f"SEPARATE soldier's owner, EC1)")
    else:
        not_reached(cells, ("X1-owner",), "X1-gifts failed")
    cells["X1-common"] = G3F.common(host, client, crash0)
    return cells, ev


def debrief_view(gc):
    d = gc.cmd({"cmd": "debrief_state"})
    return {k: d.get(k) for k in ("shown", "onTop", "displayOnly", "title")}, [s.get("name") for s in d.get("soldiers") or []]


def row_x2(host, client, ctx, crash0):
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
    end_ok = (ds == [False, False] and bool(hostiles) and all(k[2] for k in kills) and ok2 and h2 == [STATUS_DEAD] * 2
              and dok and hview == {"shown": True, "onTop": True, "displayOnly": False, "title": TITLE}
              and (be.get("reason"), be.get("aborted")) == ("aliensDown", False) and cok)
    cells["X2-end"] = (end_ok, f"desyncSeen {ds}; {len(hostiles)} hostiles, every kill settled within {KILL_S} s "
                               f"{all(k[2] for k in kills)}; H2 settled {ok2}, status host/client {h2} (want 6 / 6); the host's "
                               f"DebriefingState {dok} ({dsecs} s) {hview} (want shown, onTop, not displayOnly, {TITLE!r}); "
                               f"battleEnd {ev['battleEnd']} (want aliensDown, not aborted); the client's display-only "
                               f"DebriefingState {cok} ({csecs} s) {cview}")
    copies = recs(host, name=GUEST_NAME)
    ctx.update(end=end_ok, HREC1=(recs(host, sid=H1) or [{}])[0], HREC2=(recs(host, sid=H2) or [{}])[0],
               COPY=copies[0] if copies else {})
    ev["records"] = {k: brief([ctx[k]]) for k in ("HREC1", "HREC2", "COPY")}
    if not end_ok:
        not_reached(cells, ("X2-names",), "X2-end failed")
        return cells, ev
    hp, cp = f"[{CLIENT_ROSTER}] ", f"[{HOST_ROSTER}] "
    want = {"host": ([hp + H1_NAME, GUEST_NAME], [H1_NAME, hp + GUEST_NAME]),
            "client": ([H1_NAME, cp + GUEST_NAME], [cp + H1_NAME, GUEST_NAME])}
    got = {"host": hnames, "client": cnames}
    bad = [f"{side} page 2 {got[side]} lacks {n!r}" for side, (yes, _no) in want.items() for n in yes if n not in got[side]]
    bad += [f"{side} page 2 {got[side]} holds {n!r}" for side, (_yes, no) in want.items() for n in no if n in got[side]]
    cells["X2-names"] = (not bad, "; ".join(bad) + " (the debriefing names a given soldier as its receiver's, VL-U5-C1)"
                         if bad else f"host page 2 {hnames}; client page 2 {cnames}")
    return cells, ev


def row_x3(host, client, ctx, crash0):
    cells, ev = {}, {}
    ok1, reached, secs = SEP.client_ok_through_followups(client, ev, "ret")
    ok = ok1.get("pressed") is True and reached
    cells["X3-ok"] = (ok, f"client OK {ok1}; geo_clean {reached} within {OK_S} s ({secs} s); chain "
                          f"{(ev.get('ret') or {}).get('clientChain')}")
    ctx.update(cG=recs(client, name=GUEST_NAME), cH1=recs(client, name=H1_NAME), cH2=recs(client, name=H2_NAME))
    sep = SEP.record(client).get("sepReturn") or {}
    ev.update(sepReturn=sep, guest=brief(ctx["cG"]), H1=brief(ctx["cH1"]), H2=brief(ctx["cH2"]),
              id8=brief(recs(client, sid=GUEST_ID)))
    if not ok or not ctx.get("end"):
        not_reached(cells, ("X3-client",), "X3-ok failed" if not ok else "X2-end failed")
        return cells, ev
    pre, h1, h2 = ctx["pre"], ctx["HREC1"], ctx["HREC2"]
    bad = []
    counts = [len(recs(client, sid=GUEST_ID)), len(ctx["cG"])]
    if counts != [0, 0]:
        bad.append(f"(a) client soldier_record {{id: {GUEST_ID}}} / {{name: {GUEST_NAME!r}}} counts {counts} (want 0 / 0)")
    arr = same_stats(ctx["cH1"], h1)
    if len(arr) != 1:
        bad.append(f"(b) client records named {H1_NAME!r} with HREC1's initialStats: {len(arr)} (want exactly one)")
    else:
        a = arr[0]
        seated = a.get("recovery") == 0
        w = {"where": "base", "baseIndex": pre["FIRST_OWN"], "owner": 1, "coop": 1, "coopName": H1_NAME,
             "missions": h1.get("missions"), "kills": h1.get("kills"), "rank": h1.get("rank"),
             "currentStats": h1.get("currentStats"), "coopCraft": pre["CRAFT"] if seated else -1,
             "coopCraftType": CRAFT_TYPE if seated else ""}
        diff = {k: [a.get(k), v] for k, v in w.items() if a.get(k) != v}
        nid = len(recs(client, sid=a.get("id")))
        cb = [s.get("coopBase") for b in bases(client) for s in b.get("soldiers") or [] if s.get("id") == a.get("id")]
        ev["arrived"] = {"id": a.get("id"), "idCount": nid, "getSoldiersCoopBase": cb}
        if diff:
            bad.append(f"(b) H1's record differs [got, want] {diff}")
        if nid != 1:
            bad.append(f"(b) soldier_record {{id: {a.get('id')}}} count {nid} (want 1)")
        if cb != [pre["HOST_BASE_COOP"]]:
            bad.append(f"(b) get_soldiers coopBase of id {a.get('id')} {cb} (want [{pre['HOST_BASE_COOP']}])")
    if same_stats(ctx["cH2"], h2):
        bad.append(f"(c) client records named {H2_NAME!r} with HREC2's initialStats {brief(same_stats(ctx['cH2'], h2))} "
                   f"(want none)")
    ws = {"ownLoaded": 1, "guestsApplied": 0, "guestsMissing": 0, "deadApplied": 0, "giftedAway": 1, "giftedIn": 1,
          "giftedInFailed": 0, "pushed": 1}
    gs = {k: sep.get(k) for k in ws}
    if gs != ws:
        bad.append(f"(d) sepReturn {gs} (want {ws})")
    cells["X3-client"] = (not bad, "; ".join(bad) if bad else
                          f"G left, H1 arrived as id {ev['arrived']['id']} (a guest at base {pre['HOST_BASE_COOP']}), "
                          f"no H2, sepReturn {gs}")
    return cells, ev


def row_x4(host, client, ctx, crash0):
    cells, ev = {}, {}
    okh = SEP.press_ok(host)
    reached, screens = SEP.drain(host, timeout=DRAIN_S) if okh["pressed"] else (False, [])
    ok = okh["pressed"] and reached
    cells["X4-ok"] = (ok, f"host OK {okh}; GeoscapeState {reached} within {DRAIN_S} s; screens {screens}")
    ctx.update(hG=recs(host, name=GUEST_NAME), hH1=recs(host, name=H1_NAME), hH2=recs(host, name=H2_NAME))
    r1, r2 = recs(host, sid=H1), recs(host, sid=H2)
    ev.update(guest=brief(ctx["hG"]), id1=brief(r1), H1=brief(ctx["hH1"]), id2=brief(r2), H2=brief(ctx["hH2"]),
              battleEnd={k: SEP.record(host).get(k) for k in ("memorialRemoved", "reason")})
    if not ok:
        not_reached(cells, ("X4-host", "X4-dead"), "X4-ok failed")
        return cells, ev
    if not ctx.get("end"):
        not_reached(cells, ("X4-host",), "X2-end failed")
    else:
        bad, lg = [], ctx["hG"]
        if len(lg) != 1:
            bad.append(f"(a) host soldier_record {{name: {GUEST_NAME!r}}} count {len(lg)} (want exactly one)")
        else:
            g = lg[0]
            w = {"where": "base", "owner": 0, "coop": 0, "coopName": GUEST_NAME, "coopCraft": -1, "coopCraftType": "",
                 "missions": ctx["COPY"].get("missions")}
            diff = {k: [g.get(k), v] for k, v in w.items() if g.get(k) != v}
            nid = len(recs(host, sid=g.get("id")))
            if diff:
                bad.append(f"(a) the kept guest differs [got, want] {diff}")
            if g.get("id") == COPY_ID or nid != 1:
                bad.append(f"(a) the kept guest's id {g.get('id')} (want != the battle copy's {COPY_ID}), held by {nid} "
                           f"record(s) (want 1)")
        h1s = same_stats(ctx["hH1"], ctx["HREC1"])
        if r1 or h1s:
            bad.append(f"(b) host soldier_record {{id: {H1}}} count {len(r1)} (want 0); records named {H1_NAME!r} with "
                       f"HREC1's initialStats {len(h1s)} (want 0)")
        cells["X4-host"] = (not bad, "; ".join(bad) if bad else
                            f"G kept as id {lg[0].get('id')} (owner 0, coop 0, unseated); H1 left the host's world")
    dv = [[r.get("where"), r.get("owner"), r.get("coop")] for r in r2]
    cells["X4-dead"] = (dv == [["dead", 999, 0]], f"host soldier_record {{id: {H2}}} [where, owner, coop] {dv} (want "
                                                  f"exactly one [dead, 999, 0]: the giver's memorial)")
    return cells, ev


def row_x5(host, client, ctx, crash0):
    cells, ev = {}, {}
    have = all(k in ctx for k in ("cG", "cH1", "cH2", "hG", "hH1", "hH2")) and ctx.get("end")
    if not have:
        not_reached(cells, ("X5-one",), "X2-end, X3 or X4 failed")
    else:
        census = {"G": [lives_dead(same_stats(ctx[k], ctx["COPY"])) for k in ("hG", "cG")],
                  "H1": [lives_dead(same_stats(ctx[k], ctx["HREC1"])) for k in ("hH1", "cH1")],
                  "H2": [lives_dead(same_stats(ctx[k], ctx["HREC2"])) for k in ("hH2", "cH2")]}
        ev["census"] = census
        tot = {k: [sum(x[0] for x in v), sum(x[1] for x in v)] for k, v in census.items()}
        ok = tot["G"] == [1, 0] and tot["H1"] == [1, 0] and tot["H2"] == [0, 1] and census["H2"][0][1] == 1
        cells["X5-one"] = (ok, f"[living, dead] host / client by name + initialStats {census} (want G and H1 living "
                               f"exactly once in no memorial, H2 living nowhere and dead in the host's memorial only)")
    zd = None
    try:
        session.assert_client_zero_disk(client.user_dir)
    except AssertionError as e:
        zd = str(e)[:300]
    crash = sorted(session._crash_log_snapshot() - crash0)
    cells["X5-common"] = (not crash and zd is None, f"new crash files since the bring-up {crash} (want none); the client's "
                                                    f"zero-disk {zd or 'ok'}")
    return cells, ev


def main():
    t0 = time.time()
    host = GameClient("host", None, make_user_dir("r5u5_x_host"))
    client = GameClient("client", None, make_user_dir("r5u5_x_client"))
    rows, fails = dict(ROWS), 0
    try:
        try:
            boot, pre, crash0 = bring_up(host, client)
            print(f"[r5u5] boot X: {json.dumps(boot, default=str)}", flush=True)
        except G3F.Miss:
            fails = G3F.fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE X line)")
        else:
            ctx = {"pre": pre}
            for row, fn in (("X1", row_x1), ("X2", row_x2), ("X3", row_x3), ("X4", row_x4), ("X5", row_x5)):
                fails += G3F.run_row(row, rows[row], lambda fn=fn: fn(host, client, ctx, crash0))
    finally:
        G3F.shut(host, client)
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_battle_gift_separate: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
