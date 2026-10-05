"""W2-H19 - test_w2_separate_guest_second_battle.py: in a SEPARATE campaign a guest the client seats on the host's craft
is in every battle that craft lands in one session, whichever player pressed OK first (D156), and a guest the client
unseats stays home (docs rewrite/prompts/w2h19_separate_second_battle_guest.md (f); F6860, R-SCF-2, F6986; D104, D155,
P7SC-MR6; TASK 0 rewrite/w2h19-task0/CONSTANTS.md). Before W2-H19 the host wipes its stored guest roster at its own
debriefing OK; a client that pressed OK first already resent it and never resends an unchanged one (F6977-F6979), and an
unseated guest is never reported (F6986).
Two boots (lobby keys 47345 / 47346, F6994); the host's set_seed b1.SEED_P before every coop_mission_start. The guest is
read BY NAME on the host (its merged copy has a fresh id):
  H19-1 (Boot A): battle1, end_battle, returns("client"), seat(on), land -> (1) exactly one host battle unit named
      Guest* in battle 2; (2) fresh: one host 'Guest Zzz' record, missions == the client's own after battle 1
  H19-2 (Boot B, guard): battle1, end_battle, returns("host"), seat(on), land -> cells (1), (2) as H19-1
  H19-3 (Boot B, after H19-2): end_battle, returns("host"), seat(off), land -> (1) no guest unit in battle 3
Pre-cell guard (a miss is a FIXTURE-STOP: one CAPTURE line, the row FAILs "pre-cell"): battle 1's one guest unit, both
debriefings, the OK order, the client's guestContrib.sent after the seat, the landing prompt, both on BattlescapeState.
H19-3 runs only when H19-2's stage passed ("not reached" otherwise); a boot miss FAILs its rows "boot".
RED (commit 1, product untouched): H19-1 cell 1 (0 guest units), H19-3 cell 1 (1 guest unit); H19-2 passes. GREEN: all.
Each row prints ONE "EVIDENCE <id>:" line, then "PASS <id>" or "FAIL <id>: <message>". WV-D95/D99/D100: ONE
foreground run, no skip path; exit 0 only when every row passes, 2 otherwise.
Run:  python tools/coop_test/test_w2_separate_guest_second_battle.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, event_state
from harness import GameClient, make_user_dir
import test_w2_battle_end_separate as b1

PORT_A, PORT_B = "47345", "47346"   # F6994: 0 matches in tools/ + src/ at every w2* / rewrite/* tip and the docs repo
TAG = "w2h19"
GUEST = "Guest Zzz"
SENT_S = 5.0                        # seat(): the client's guestContrib.sent within 5 s ((f); TASK 0 P6: first poll)
LOG_TAGS = ("[coop-debrief]", "[coop-gift]")
REC_KEYS = ("where", "id", "owner", "coop", "craftId", "missions", "kills", "dead")
SESSION = {}                        # Boot B: H19-2's ctx once its stage passed, read by H19-3 (one session)
stack = b1.stack


def gcontrib(gc):
    """This machine's event_state.guestContrib: `sent` = its last census count, `soldiers[s]` = the host's store."""
    g = event_state(gc).get("guestContrib")
    return g if isinstance(g, dict) else {"missing": g}


def guests(h):
    """The host's battle units named Guest* (by name: the merged copy carries a fresh soldier id)."""
    return [{k: u.get(k) for k in ("id", "name", "faction", "health", "isOut")}
            for u in battle_state(h).get("units", []) if "Guest" in (u.get("name") or "")]


def host_guest_recs(h):
    recs, _meta = b1.soldier_recs(h, name=GUEST)
    return [{k: r.get(k) for k in REC_KEYS} for r in recs]


def dump(gc):
    """FIXTURE-STOP extras: base_report {coop} and the [coop-debrief] / [coop-gift] log lines."""
    out = {}
    try:
        r = gc.cmd({"cmd": "base_report", "coop": True})
        keys = ("id", "name", "owner", "coopBase", "coopCraft", "craft")
        out["baseReportCoop"] = r.get("error") or [{k: s.get(k) for k in keys} for s in r.get("soldiers") or []]
    except Exception as e:
        out["baseReportCoop"] = b1.short(e)
    try:
        lines = open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace").read().splitlines()
        out["log"] = {t: [ln for ln in lines if t in ln][-12:] for t in LOG_TAGS}
    except OSError as e:
        out["log"] = str(e)
    return out


def miss(ctx, name, err, h, c):
    """FIXTURE-STOP: both dump()s into ctx (EVIDENCE), then b1.capture's ONE CAPTURE line + FixtureMiss."""
    ctx["missDump"] = {gc.name: dump(gc) for gc in (h, c)}
    b1.capture(name, err, (h, c))


def run_segments(ctx, h, c, segs):
    """A row's pre-cell stage: each (name, fn) in order; any other exception is ONE capture; the walls go to ctx."""
    t0 = time.time()
    for name, fn in segs:
        try:
            fn()
        except b1.FixtureMiss:
            raise
        except Exception as e:
            miss(ctx, name, b1.short(e, 800), h, c)
        ctx.setdefault("walls", {})[name] = round(time.time() - t0, 1)


def battle1(h, c, ctx, port):
    """bring_up_separate_guest_battle with the host's set_seed SEED_P at the landing prompt; guard: one guest unit."""
    def pin(hh, cc):
        ctx["battle1Prompt"] = {"host": gcontrib(hh), "client": gcontrib(cc)}
        hh.ok({"cmd": "set_seed", "seed": b1.SEED_P})
    squad, gid = session.bring_up_separate_guest_battle(h, c, port=port, pre_landing=pin)
    ctx["guestId"], ctx["hostSquad"] = gid, squad
    g = guests(h)
    ctx["battle1"] = {"guestUnits": g, "tops": (b1.top(h), b1.top(c)),
                      "mapFingerprint": (battle_state(h).get("mapFingerprint"), battle_state(c).get("mapFingerprint"))}
    if len(g) != 1:
        miss(ctx, "battle1 guest unit", f"expected one host battle unit named 'Guest*', got {g}", h, c)


def end_battle(h, c, ctx, key):
    """S-C-F again_stage's ending: kill_unit_real {faction: 1}, the chain settled (want_live 0, F4665), END TURN both,
    NextTurnState closed; the host's DebriefingState, the client's display-only one (b1.DEBRIEF_S, CLIENT_DEBRIEF_S)."""
    e = ctx.setdefault(key, {})
    live = sorted(u["id"] for u in battle_state(h).get("units", []) if u.get("faction") == 1 and not u.get("isOut"))
    k = h.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    e["kill"] = {"live": len(live), "killed": len(k.get("killed") or []), "ok": k.get("ok"), "error": k.get("error")}
    if not k.get("ok") or not live or sorted(k.get("killed") or []) != live:
        miss(ctx, key + " kill", f"kill_unit_real faction 1 answered {e['kill']} (want every live hostile)", h, c)
    settled, secs, samples = b1.chain_settled(h, c, stable=1.0, timeout=45, want_live=0)
    e["settled"] = {"ok": settled, "secs": secs}
    if not settled:
        miss(ctx, key + " chain settle", f"the host's kill chain not settled within 45s (F4665): {samples[-6:]}", h, c)
    e["guestsAfterKill"] = guests(h)
    b1.end_turn_both(h, c)
    b1.close_host_nextturn(h)
    ok, secs = b1.wait_until(lambda: "DebriefingState" in stack(h), b1.DEBRIEF_S)
    ok2, secs2 = b1.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("onTop") is True
                                        and d.get("displayOnly") is True)(c.cmd({"cmd": "debrief_state"})),
                               b1.CLIENT_DEBRIEF_S)
    e["debriefs"] = {"host": [ok, secs], "client": [ok2, secs2]}
    if not (ok and ok2):
        miss(ctx, key + " debriefings", f"host DebriefingState {ok} within {b1.DEBRIEF_S}s, client display-only "
             f"DebriefingState {ok2} within {b1.CLIENT_DEBRIEF_S}s (stacks {stack(h)} / {stack(c)})", h, c)
    e["atDebrief"] = {"host": gcontrib(h), "client": gcontrib(c)}


def returns(h, c, ctx, first):
    """The OK order (D156): "client" = the client's OK through its follow-ups while the host still shows its
    debriefing, then the host's OK + drain; "host" = the reverse. ctx["after"] = the client's own guest record."""
    r = ctx.setdefault("returns", {})
    ctx["okOrder"] = first

    def host_ok():
        ok = b1.press_ok(h)
        reached, screens = b1.drain(h) if ok["pressed"] else (False, [])
        r["host"] = {"ok": ok, "reached": reached, "screens": screens, "clientTop": b1.top(c),
                     "hostContrib": gcontrib(h)}
        if not (ok["pressed"] and reached):
            miss(ctx, "returns host OK", f"host OK {ok}, GeoscapeState {reached} (screens {screens})", h, c)

    def client_ok():
        ok1, ok, secs = b1.client_ok_through_followups(c, r, "client")
        r["client"].update({"ok": ok1, "reached": ok, "secs": secs, "hostTop": b1.top(h), "hostContrib": gcontrib(h)})
        if not (ok1["pressed"] and (ok1.get("resp") or {}).get("handled") == "DebriefingState" and ok):
            miss(ctx, "returns client OK", f"client OK {ok1}, a clean GeoscapeState {ok} (stack {stack(c)})", h, c)

    first_ok, second_ok, other = (client_ok, host_ok, h) if first == "client" else (host_ok, client_ok, c)
    first_ok()
    if b1.top(other) != "DebriefingState":
        miss(ctx, "returns OK order", f"{other.name} top {b1.top(other)} after the {first}'s OK (want its "
             f"DebriefingState: the {first} pressed OK first, D156)", h, c)
    second_ok()
    ctx["after"] = b1.soldier_rec(c, sid=ctx["guestId"])


def seat(h, c, ctx, on):
    """S-C-F's visit -> base_report {coop} -> craft_assign {coop, on} (ok, seated == on) -> open_soldiers / soldiers_ok
    -> leave_base; then the client's guestContrib.sent == (1 if on else 0) within SENT_S (0 during the visit, F6983)."""
    s = ctx.setdefault("seat", {"on": on})
    base = session._campaign_own_roster_base(h)["name"]
    c.ok({"cmd": "visit_coop_base", "base": base})
    c.wait_for("client inside host base", lambda: c.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    rep = c.wait_for("guest visible at host base",
                     lambda: (lambda r: r if any("Guest" in x["name"] for x in r["soldiers"]) else None)(
                         c.ok({"cmd": "base_report", "coop": True})), timeout=40)
    g = next(x for x in rep["soldiers"] if "Guest" in x["name"])
    craft = next(x for x in rep["crafts"] if "SKYRANGER" in x["type"])["id"]
    s["guest"] = {k: g.get(k) for k in ("id", "name", "craft", "coopCraft", "coopBase", "owner")}
    if g.get("id") != ctx["guestId"]:
        miss(ctx, "seat guest id", f"coop base guest id {g.get('id')} != battle 1's {ctx['guestId']}", h, c)
    r = c.cmd({"cmd": "craft_assign", "soldier_id": g["id"], "craft_id": craft, "coop": True, "on": on})
    s["assign"] = {k: r.get(k) for k in ("ok", "seated", "craftId", "error")}
    if not (r.get("ok") and r.get("seated") == on):
        miss(ctx, "seat craft_assign", f"craft_assign coop on={on} answered {s['assign']}", h, c)
    c.ok({"cmd": "open_soldiers", "base": base})
    c.wait_for("client soldiers screen", lambda: session.has_state(c, "SoldiersState") or None, timeout=30)
    c.ok({"cmd": "soldiers_ok"})
    c.ok({"cmd": "leave_base"})
    c.wait_for("client back on geoscape", lambda: (not c.cmd({"cmd": "get_coop"}).get("insideCoopBase")) or None,
               timeout=60)
    want = 1 if on else 0
    ok, secs = b1.wait_until(lambda: gcontrib(c).get("sent") == want, SENT_S, 0.1)
    s["sent"] = {"ok": ok, "secs": secs, "client": gcontrib(c), "want": want}
    if not ok:
        miss(ctx, "seat sent", f"client guestContrib {s['sent']['client']} within {SENT_S}s (want sent {want})", h, c)


def land(h, c, ctx, key):
    """S-C-F's site spawn, craft_force, landing prompt (both guestContribs and the host's Guest Zzz records there),
    set_seed SEED_P, coop_mission_start, drive_both_to_tactical; both on BattlescapeState."""
    L = ctx.setdefault(key, {})
    session.drain_host_coop_notice(h)
    b0 = session._campaign_base0(h)
    cid = session._campaign_skyranger(h)["id"]
    site = h.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                 "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    sid = site["site_id"]
    h.wait_for("site on host", lambda: any(x["id"] == sid for x in h.ok({"cmd": "geo_state"})["missionSites"]) or None,
               timeout=30)
    h.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
          "lat": b0["lat"] + 0.10, "dest": f"site:{sid}", "fuel": 999999, "lowFuel": False})
    def landing_prompt():
        if session.has_state(h, "ConfirmLandingState"):
            return True
        t = session.states(h)[-1]
        if "CoopState" in t:
            h.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in t:
            h.cmd({"cmd": "dismiss_popup"})
        h.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    h.wait_for("host landing prompt", landing_prompt, timeout=120, interval=0.5)
    L["atPrompt"] = {"host": gcontrib(h), "client": gcontrib(c), "hostGuestRecords": host_guest_recs(h)}
    h.ok({"cmd": "set_seed", "seed": b1.SEED_P})
    h.ok({"cmd": "coop_mission_start"})
    h.wait_for("host entered", lambda: battle_state(h).get("inBattle") or None, timeout=120, interval=1.0)
    h.wait_for("host briefing", lambda: session.has_state(h, "BriefingState"), timeout=60, interval=0.5)
    if not session.drive_both_to_tactical(h, c):
        raise TimeoutError(f"drive_both_to_tactical timed out (host={stack(h)[-3:]} client={stack(c)[-3:]})")
    tops = [b1.top(h), b1.top(c)]
    L["entry"] = {"tops": tops, "hostGuestRecords": host_guest_recs(h),
                  "mapFingerprint": (battle_state(h).get("mapFingerprint"), battle_state(c).get("mapFingerprint"))}
    if tops != ["BattlescapeState", "BattlescapeState"]:
        miss(ctx, key + " tactical", f"tops (host, client) {tops} (want both BattlescapeState)", h, c)


def fresh(h, ctx):
    """The host has exactly one 'Guest Zzz' record and its missions == the client's own after the previous battle."""
    recs, want = host_guest_recs(h), (ctx.get("after") or {}).get("missions")
    ctx["fresh"] = {"hostRecords": recs, "afterMissions": want}
    if len(recs) != 1:
        return [f"the host has {len(recs)} '{GUEST}' records in battle 2 (want exactly 1, the merged copy): {recs}"]
    if recs[0].get("missions") != want:
        return [f"the host's merged '{GUEST}' missions={recs[0].get('missions')!r} (want the client's own after "
                f"battle 1, {want!r})"]
    return []


def cell_guests(h, ctx, want, msg):
    """Exactly `want` host battle units named Guest*; `msg` names the other single outcome (the red)."""
    g = guests(h)
    ctx["guestUnits"] = g
    if len(g) == want:
        return []
    return [msg] if len(g) == 1 - want else [f"{len(g)} host battle units named Guest* (want {want}): {g}"]


def stage_battle2(first, port):
    """H19-1 / H19-2 pre-cell: battle1, end_battle, returns(first), seat(on), land (battle 2)."""
    def stage(rid, h, c, ctx):
        run_segments(ctx, h, c, [("battle1", lambda: battle1(h, c, ctx, port)),
                                 ("end_battle1", lambda: end_battle(h, c, ctx, "end1")),
                                 ("returns", lambda: returns(h, c, ctx, first)),
                                 ("seat_on", lambda: seat(h, c, ctx, True)),
                                 ("land2", lambda: land(h, c, ctx, "land2"))])
        SESSION[rid] = ctx
    return stage


def cells_battle2(why):
    def cells(h, c, ctx):
        return [("1 the guest is in battle 2", lambda: cell_guests(h, ctx, 1, f"the guest is not in battle 2 ({why})")),
                ("2 fresh: one host 'Guest Zzz' record, missions == the client's own after battle 1",
                 lambda: fresh(h, ctx))]
    return cells


def stage_h19_3(rid, h, c, ctx):
    """H19-3 pre-cell (Boot B, after H19-2): end_battle (battle 2), returns("host"), seat(off), land (battle 3)."""
    ctx["guestId"] = SESSION["H19-2"]["guestId"]
    run_segments(ctx, h, c, [("end_battle2", lambda: end_battle(h, c, ctx, "end2")),
                             ("returns", lambda: returns(h, c, ctx, "host")),
                             ("seat_off", lambda: seat(h, c, ctx, False)),
                             ("land3", lambda: land(h, c, ctx, "land3"))])


def cells_h19_3(h, c, ctx):
    return [("1 the unseated guest is not in battle 3", lambda: cell_guests(
        h, ctx, 0, "the guest the client unseated is in battle 3 (F6986)"))]


def boot(tag, port, rows, results, walls):
    """One boot (fresh host + client, lobby key `port`), then `rows` in order on that session."""
    t0 = time.time()
    print(f"[w2h19] boot {tag} start {time.strftime('%H:%M:%S')}", flush=True)
    h = GameClient("host", 0, make_user_dir(f"{TAG}_{tag}_host"))
    c = GameClient("client", 0, make_user_dir(f"{TAG}_{tag}_client"))
    try:
        try:
            h.spawn(); c.spawn(); h.connect(); c.connect()
        except Exception as e:
            try:
                b1.capture(f"boot {tag}", b1.short(e, 800), (h, c))   # the ONE CAPTURE line of a boot miss
            except b1.FixtureMiss:
                pass
            for rid, _s, _c, _n in rows:
                results[rid] = False
                print(f"FAIL {rid}: boot {tag} ({b1.short(e)})", flush=True)
            return
        for rid, stage_fn, cells_fn, needs in rows:
            if needs and needs not in SESSION:
                results[rid] = False
                print(f"FAIL {rid}: not reached ({needs}'s stage, pre-cell, did not pass)", flush=True)
                continue
            b1.run_row(rid, h, c, results, walls, stage_fn, cells_fn)
    finally:
        for gc in (h, c):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2h19] shutdown {gc.name}: {b1.short(e)}", flush=True)
        walls[f"boot{tag}"] = round(time.time() - t0, 1)
        print(f"[w2h19] boot {tag} end {time.strftime('%H:%M:%S')} wall {walls[f'boot{tag}']}s", flush=True)


def main():
    t0, results, walls = time.time(), {}, {}
    boot("A", PORT_A, [("H19-1", stage_battle2("client", PORT_A), cells_battle2("client pressed OK first; F6860"),
                        None)], results, walls)
    boot("B", PORT_B, [("H19-2", stage_battle2("host", PORT_B), cells_battle2("host pressed OK first; F6981"), None),
                       ("H19-3", stage_h19_3, cells_h19_3, "H19-2")], results, walls)
    order = ["H19-1", "H19-2", "H19-3"]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_separate_guest_second_battle: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) "
          f"in {time.time() - t0:.1f}s (walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
