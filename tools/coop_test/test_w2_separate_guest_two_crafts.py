"""W2-H19b - test_w2_separate_guest_two_crafts.py: in SEPARATE every guest the client seats on any host craft flies with
that craft, and a same-process reconnect refills the host's guest roster (docs rewrite/prompts/
w2h19b_guest_store_per_craft.md (f); F6989, F6987; H19-Q4 (a), D226 (a), D104, D156, P7-6 VL2; TASK 0
rewrite/w2h19b-task0/CONSTANTS.md "Run 3"; R-H19b-T0-1..3). Before W2-H19b the host keeps ONE guest roster per player,
so a craft whose roster the client did not send last lands without its guest. ONE boot (lobby key 47347, F7526); the
host's set_seed b1.SEED_P before every coop_mission_start; guests are read BY NAME on the host. Rows, one session:
  H19b-1 battle1_two (Guest Zzz on Skyranger 1, Guest Yyy on the SECOND spawned Skyranger, id 3), land craft 1 ->
         (1) the host's battle guests == ["Guest Zzz"]; (2) the host's soldiers[1] at the landing prompt == 2
  H19b-2 end_battle, returns("client"), land_craft(3) -> (1) guard ["Guest Yyy"]; (2) soldiers[1] at the prompt == 2
  H19b-3 end_battle, returns("host"), rejoin (save, same-process drop, join_tcp, RESUME) -> (1) guard: the host's
         recvSeats == [1] within 5 s of both geoscapes (F6987, W2-H19 Y2); (2) soldiers[1] == 2
Pre-cell steps are guards (a miss = FIXTURE-STOP: ONE CAPTURE line, later rows "not reached"); cells are independent.
RED (product untouched): H19b-1 cells 1+2, H19b-2 cell 2, H19b-3 cell 2. GREEN: all. ONE "EVIDENCE <id>:" line, then
PASS/FAIL per row. WV-D95/D99/D100: ONE foreground run, no skip path; exit 0 only when every row passes, else 2.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
from session import battle_state, has_state
import test_w2_battle_end_separate as b1
import test_w2_separate_guest_second_battle as h19

PORT, TAG = "47347", "w2h19b"   # F7526: lobby key 47347 has 0 matches in tools/ + src/ at every w2* / rewrite* tip
SEAT = 1                # the client's seat = the index of the host's guestContrib.soldiers
ZZZ, YYY, SKY = "Guest Zzz", "Guest Yyy", "STR_SKYRANGER"
C2_ID = 3               # R-H19b-T0-1: the SECOND spawned Skyranger (craft ids are per type; Interceptor 2 shadows id 2)
SENT_S = 5.0            # the client's sent == 2 after leave_base (TASK 0 P3: 0.10 s)
UNSEAT_S = 10.0         # the host's ClientBase mirror shows the client's unseat (TASK 0: first poll)
FNV_S = 30.0            # R-H19b-T0-2: the host's copy-of-client changes after the client's return (TASK 0: first poll)
STORE_S = 5.0           # the host's store refilled after the client's return, before the drop (TASK 0: first poll)
REFILL_S = 5.0          # H19b-3: the host's store within 5 s of both geoscapes (TASK 0 P10: 0.30 s)
DROP_S, JOIN_S, GEO_S = 30.0, 120.0, 60.0
SESSION = h19.SESSION   # each row's ctx once its stage passed, read by the next row (h19.boot's "not reached" gate)
gc_ = h19.gcontrib
names = lambda h: sorted(g.get("name") for g in h19.guests(h))   # noqa: E731 the (f) helper: the host's battle guests

def store(snap):
    return (snap.get("soldiers") or [None, None])[SEAT]

def dlg(gc):
    return {k: v for k, v in gc.cmd({"cmd": "coop_dialog_info"}).items() if k in ("present", "code", "backVisible")}

def dialogs(h, c):
    try:
        return {gc.name: dlg(gc) for gc in (h, c)}
    except Exception as e:
        return b1.short(e)

def miss(ctx, name, err, h, c):
    """h19.miss (base_report {coop}, [coop-debrief]/[coop-gift] lines, b1.capture's event_states) + coop_dialog_info."""
    ctx["missDialogs"] = dialogs(h, c)
    h19.miss(ctx, name, err, h, c)

def run(ctx, h, c, segs):
    """h19.run_segments; any exception is ONE capture through miss() (an h19 helper's own miss adds the dialogs)."""
    def guard(name, fn):
        def go():
            try:
                fn()
            except b1.FixtureMiss:
                ctx.setdefault("missDialogs", dialogs(h, c))
                raise
            except Exception as e:
                miss(ctx, name, b1.short(e, 800), h, c)
        return name, go
    h19.run_segments(ctx, h, c, [guard(n, f) for n, f in segs])

def wait_for(ctx, h, c, name, pred, timeout, interval, err):
    ok, secs = b1.wait_until(pred, timeout, interval)
    ctx.setdefault("waits", {})[name] = secs
    if not ok:
        miss(ctx, name, err(), h, c)

def crafts(gc, coop, cid):   # base_report ({coop: true} = the peer's base seen here): (type, soldiers) of id `cid`
    r = gc.cmd({"cmd": "base_report", "coop": True} if coop else {"cmd": "base_report"})
    return [(x.get("type"), x.get("soldiers")) for x in r.get("crafts") or [] if x.get("id") == cid], r.get("name")

def second_guest(h, c, ctx):
    """pre_mission_start hook (Zzz on Skyranger 1): two host Skyrangers, the second = craft 2 (R-H19b-T0-1) + two host
    soldiers; the client unseats one own soldier (R-H19b-T0-3) -> Guest Yyy -> transfer -> seat on craft 2 from the
    visited base -> leave; guard: the client's sent == 2 within SENT_S (0 during the visit, F6983)."""
    g = ctx.setdefault("second", {})
    hb = session._campaign_own_roster_base(h)
    base = ctx["hostBase"] = hb["name"]
    ctx["c1"] = session._campaign_skyranger(h)["id"]
    g["spawns"] = [h.cmd({"cmd": "spawn_craft", "type": SKY}).get("craft_id") for _ in range(2)]
    c2 = ctx["c2"] = g["spawns"][1]
    g["c2SameId"], name = crafts(h, False, c2)
    if c2 != C2_ID or name != base or [t for t, _n in g["c2SameId"]] != [SKY]:
        miss(ctx, "second_guest craft 2", f"spawns {g['spawns']}, host base_report {name!r} crafts with id {c2}: "
             f"{g['c2SameId']} (want exactly one, id {C2_ID}, {SKY}; R-H19b-T0-1)", h, c)
    free = sorted(s["id"] for s in hb["soldiers"] if s.get("craftId") == -1 and "Guest" not in s["name"])[:2]
    g["hostSeats"] = [h.cmd({"cmd": "craft_assign", "craft_id": c2, "soldier_id": sid, "on": True,
                             "base": base}).get("seated") for sid in free]
    if g["hostSeats"] != [True, True]:
        miss(ctx, "second_guest host seats", f"host soldiers {free} on craft {c2}: {g['hostSeats']}", h, c)
    cb = session._campaign_own_roster_base(c)
    on1 = sorted(s["id"] for s in cb["soldiers"] if s.get("craftId") == 1 and "Guest" not in s["name"])
    mirror1 = lambda: [n for t, n in crafts(h, True, 1)[0] if t == SKY]   # noqa: E731 the host's ClientBase mirror
    sky1 = mirror1()
    if not on1 or len(sky1) != 1:
        miss(ctx, "second_guest unseat pre", f"client soldiers on craft 1 {on1}, host mirror Skyranger 1 {sky1}", h, c)
    x, want = on1[-1], [sky1[0] - 1]
    ru = c.cmd({"cmd": "craft_assign", "craft_id": 1, "soldier_id": x, "on": False, "base": cb["name"]})
    g["unseat"] = {"id": x, "resp": {k: ru.get(k) for k in ("ok", "seated", "error")},
                   "clientCraftId": b1.soldier_rec(c, sid=x).get("craftId")}
    if not (ru.get("ok") and ru.get("seated") is False and g["unseat"]["clientCraftId"] == -1):
        miss(ctx, "second_guest unseat", f"client unseat {g['unseat']} (want unseated, craftId -1)", h, c)
    wait_for(ctx, h, c, "second_guest unseat host", lambda: mirror1() == want, UNSEAT_S, 0.1,
             lambda: f"the host's mirror Skyranger 1 != {want} within {UNSEAT_S}s (R-H19b-T0-3)")
    spare = next(s["name"] for s in session._campaign_own_roster_base(c)["soldiers"] if s["id"] == x)
    g["rename"] = c.cmd({"cmd": "rename_soldier", "name": spare, "newName": YYY}).get("ok")
    g["transfer"] = c.cmd({"cmd": "transfer_to_coop_base", "name": "Yyy", "toBase": base}).get("transferred")
    if not (g["rename"] and g["transfer"]):
        miss(ctx, "second_guest Yyy", f"rename {g['rename']}, transfer {g['transfer']} ({spare!r} -> {YYY})", h, c)
    c.ok({"cmd": "visit_coop_base", "base": base})
    c.wait_for("client inside host base", lambda: c.cmd({"cmd": "get_coop"}).get("insideCoopBase") or None, timeout=60)
    def seen():
        r = c.ok({"cmd": "base_report", "coop": True})
        yy = [s for s in r.get("soldiers") or [] if s.get("name") == YYY]
        sky = [cr for cr in r.get("crafts") or [] if cr.get("id") == c2 and cr.get("type") == SKY]
        return yy[0] if (yy and len(sky) == 1) else None
    yy = c.wait_for(f"Guest Yyy and Skyranger {c2} at host base", seen, timeout=40)
    g["visit"] = {"yyy": {k: yy.get(k) for k in ("id", "craft", "coopCraft", "coopBase")}, "clientSent": gc_(c)["sent"]}
    r = c.cmd({"cmd": "craft_assign", "soldier_id": yy["id"], "craft_id": c2, "coop": True, "on": True})
    g["assign"] = {k: r.get(k) for k in ("ok", "seated", "craftId", "error")}
    if not (r.get("ok") and r.get("seated")):
        miss(ctx, "second_guest seat Yyy", f"craft_assign coop Yyy on craft {c2} answered {g['assign']}", h, c)
    c.ok({"cmd": "open_soldiers", "base": base})
    c.wait_for("client soldiers screen", lambda: has_state(c, "SoldiersState"), timeout=30)
    for cmd in ("soldiers_ok", "leave_base"):
        c.ok({"cmd": cmd})
    session.wait_back_on_geoscape(c, "client back on geoscape")
    wait_for(ctx, h, c, "second_guest sent", lambda: gc_(c).get("sent") == 2, SENT_S, 0.1,
             lambda: f"client guestContrib {gc_(c)} within {SENT_S}s (want sent 2)")

def battle1_two(h, c, ctx, port):
    """bring_up_separate_guest_battle + second_guest; pre_landing: both gcontribs, set_seed SEED_P. No guest guard."""
    def pin(hh, cc):
        ctx["battle1Prompt"] = {"host": gc_(hh), "client": gc_(cc)}
        hh.ok({"cmd": "set_seed", "seed": b1.SEED_P})
    ctx["hostSquad"], ctx["guestId"] = session.bring_up_separate_guest_battle(
        h, c, port=port, pre_landing=pin, pre_mission_start=lambda hh, cc: second_guest(hh, cc, ctx))
    ctx["battle1"] = {"guests": h19.guests(h), "tops": (b1.top(h), b1.top(c)),
                      "mapFingerprint": (battle_state(h).get("mapFingerprint"), battle_state(c).get("mapFingerprint"))}

def land_craft(h, c, ctx, key, cid):
    """h19.land with the craft id as a parameter; both gcontribs at the landing prompt."""
    L = ctx.setdefault(key, {"craft": cid})
    session.drain_host_coop_notice(h)
    b0 = session._campaign_base0(h)
    sid = h.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})["site_id"]
    h.wait_for("site on host", lambda: any(x["id"] == sid for x in h.ok({"cmd": "geo_state"})["missionSites"]) or None,
               timeout=30)
    h.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT", "lon": b0["lon"] + 0.34,
          "lat": b0["lat"] + 0.10, "dest": f"site:{sid}", "fuel": 999999, "lowFuel": False})
    def landing_prompt():
        if has_state(h, "ConfirmLandingState"):
            return True
        t = session.states(h)[-1]
        if "CoopState" in t:
            h.cmd({"cmd": "coop_dialog_back"})
        elif "GeoscapeState" not in t:
            h.cmd({"cmd": "dismiss_popup"})
        h.cmd({"cmd": "geo_set_speed", "idx": 2})
        return None
    h.wait_for("host landing prompt", landing_prompt, timeout=120, interval=0.5)
    L["atPrompt"] = {"host": gc_(h), "client": gc_(c)}
    h.ok({"cmd": "set_seed", "seed": b1.SEED_P})
    h.ok({"cmd": "coop_mission_start"})
    h.wait_for("host entered", lambda: battle_state(h).get("inBattle") or None, timeout=120, interval=1.0)
    h.wait_for("host briefing", lambda: has_state(h, "BriefingState"), timeout=60, interval=0.5)
    if not session.drive_both_to_tactical(h, c):
        raise TimeoutError(f"drive_both_to_tactical timed out (host={b1.stack(h)[-3:]} client={b1.stack(c)[-3:]})")
    L["entry"] = {"tops": [b1.top(h), b1.top(c)], "guests": h19.guests(h),
                  "mapFingerprint": (battle_state(h).get("mapFingerprint"), battle_state(c).get("mapFingerprint"))}
    if L["entry"]["tops"] != ["BattlescapeState", "BattlescapeState"]:
        miss(ctx, key + " tactical", f"tops (host, client) {L['entry']['tops']} (want both BattlescapeState)", h, c)

def returns_host(h, c, ctx):
    """returns("host"); the host's copy-of-client fnv changes (R-H19b-T0-2); recvSeats [1] (drop store non-vacuous)."""
    f0 = ctx["fnv0"] = b1.coop_fnv(h, "host_copy_of_client")[0]
    h19.returns(h, c, ctx, "host")
    wait_for(ctx, h, c, "predrop fnv", lambda: b1.coop_fnv(h, "host_copy_of_client")[0] not in (f0, None, ""),
             FNV_S, 0.1, lambda: f"the host's copy-of-client fnv still {f0} {FNV_S}s after the client's return")
    wait_for(ctx, h, c, "predrop store", lambda: gc_(h).get("recvSeats") == [SEAT], STORE_S, 0.05,
             lambda: f"host guestContrib {gc_(h)} {STORE_S}s after the client's return (want recvSeats [1])")
    ctx["predrop"] = {"host": gc_(h), "client": gc_(c)}

def clear_profiles(h, c):   # the Profile popups a join pushes; returns None
    [gc.cmd({"cmd": "profile_ok"}) for gc in (h, c) if has_state(gc, "Profile")]

def rejoin(h, c, ctx, port):
    """Host save_game; client disconnect_to_menu -> MainMenuState; host coopSession false, dialog 62, recvSeats []
    (cell 1's negative control); the SAME client join_tcp; Profiles cleared; client 68; host RESUME; both geoscapes;
    the host's store every 0.25 s for REFILL_S (the cells); guard: the client's Zzz / Yyy coopCraft == c1 / c2."""
    J = ctx.setdefault("rejoin", {})
    t = J.setdefault("timings", {})
    J["save"] = h.cmd({"cmd": "save_game", "file": TAG + ".sav"}).get("ok")
    if not J["save"]:
        miss(ctx, "rejoin save_game", f"host save_game ok {J['save']}", h, c)
    t0 = time.time()
    J["disconnect"] = c.cmd({"cmd": "disconnect_to_menu"}).get("ok")
    for key, pred in (("clientMenu", lambda: b1.top(c) == "MainMenuState"),
                      ("hostNoSession", lambda: not h.cmd({"cmd": "get_coop"}).get("coopSession")),
                      ("host62", lambda: dlg(h).get("code") == 62)):
        wait_for(ctx, h, c, "rejoin drop " + key, pred, DROP_S, 0.1,
                 lambda: f"stacks {b1.stack(h)} / {b1.stack(c)}, host dialog {dlg(h)} {DROP_S}s after the drop")
        t[key] = round(time.time() - t0, 2)
    J["afterDrop"] = gc_(h)
    if J["afterDrop"].get("recvSeats") != []:
        miss(ctx, "rejoin drop store", f"host guestContrib {J['afterDrop']} after the drop (want recvSeats [])", h, c)
    t1 = time.time()
    J["join"] = c.cmd({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"}).get("ok")
    def joined():
        clear_profiles(h, c)
        if dlg(c).get("code") == 68:
            t.setdefault("client68", round(time.time() - t1, 2))
        if (lambda d: d.get("code") == 62 and d.get("backVisible"))(dlg(h)):
            t.setdefault("hostResume", round(time.time() - t1, 2))
        return "client68" in t and "hostResume" in t
    wait_for(ctx, h, c, "rejoin join", joined, JOIN_S, 0.2,
             lambda: f"join {J['join']}: client 68 / host RESUME seen at {t} (dialogs {dialogs(h, c)})")
    clear_profiles(h, c)
    J["resume"] = {k: v for k, v in h.cmd({"cmd": "coop_dialog_back"}).items() if k in ("ok", "code", "error")}
    t2 = time.time()
    wait_for(ctx, h, c, "rejoin geo", lambda: clear_profiles(h, c) or (b1.geo_clean(h) and b1.geo_clean(c)),
             GEO_S, 0.1, lambda: f"stacks {b1.stack(h)} / {b1.stack(c)} {GEO_S}s after RESUME {J['resume']}")
    t3 = time.time()
    t.update({"bothGeoFromResume": round(t3 - t2, 2), "bothGeoFromDrop": round(t3 - t0, 2)})
    ref = J["refill"] = []
    while True:
        snap = gc_(h)
        v, dt = (snap.get("recvSeats"), store(snap)), round(time.time() - t3, 2)
        if not ref or tuple(ref[-1][1:]) != v:
            ref.append((dt,) + v)
        if v == ([SEAT], 2) or dt >= REFILL_S:
            break
        time.sleep(0.25)
    J["final"] = {"host": gc_(h), "client": gc_(c)}
    J["coopCraft"] = [sorted({r.get("coopCraft") for r in b1.soldier_recs(c, name=n)[0]}) for n in (ZZZ, YYY)]
    if J["coopCraft"] != [[ctx["c1"]], [ctx["c2"]]]:
        miss(ctx, "rejoin seats", f"the client's own Guest Zzz / Guest Yyy coopCraft {J['coopCraft']} (want "
             f"[[{ctx['c1']}], [{ctx['c2']}]]: the host's served copy lost a seat, P7-6 VL2)", h, c)

def cell_names(h, ctx, want, msg):
    g = ctx["guestNames"] = names(h)
    return [] if g == want else [msg] if not g else [f"the host's battle guests {g} (want {want})"]

def cell_store(n, when):
    return [] if n == 2 else ["the host stores 1 of the client's 2 seated guests (one roster per player, F6989)"] \
        if n == 1 else [f"the host's guestContrib.soldiers[1] {n!r} {when} (want 2)"]

def cell_refill(ctx):
    first = ctx["refillAt"] = next((r[0] for r in ctx["rejoin"]["refill"] if r[1] == [SEAT]), None)
    return [] if first is not None else [f"the host's recvSeats never [1] within {REFILL_S}s of both geoscapes "
                                         f"(F6987: a same-process reconnect never resends the roster)"]

def every(cells):
    """b1.run_row ends a row at its first failed cell; these cells are independent ((f): H19b-1 names both red), so
    ONE run_row cell checks each and names each failure; ctx["cellsAll"] holds every cell's result."""
    def cells_fn(h, c, ctx):
        def check():
            out, fails = ctx.setdefault("cellsAll", []), []
            for name, fn in cells(h, c, ctx):
                try:
                    f = fn()
                except Exception as e:
                    f = [b1.short(e, 600)]
                out.append({"cell": name, "pass": not f, "fails": f})
                fails += [f"({name.split(' ')[0]}) {m}" for m in f]
            return fails
        return [("1-2", check)]
    return cells_fn

def stage(prev, segs):
    """A row's pre-cell stage: carry the previous row's ids, run segs(h, c, ctx); SESSION[rid] once it passed."""
    def stage_fn(rid, h, c, ctx):
        if prev:
            ctx.update({k: SESSION[prev][k] for k in ("guestId", "c1", "c2", "hostBase")})
        run(ctx, h, c, segs(h, c, ctx))
        SESSION[rid] = ctx
    return stage_fn

MSG1 = "the guest seated on the landing craft is not in the battle: the host kept only the other craft's roster (F6989)"
ROWS = [
    ("H19b-1", stage(None, lambda h, c, x: [("battle1_two", lambda: battle1_two(h, c, x, PORT))]),
     every(lambda h, c, x: [("1 the guest seated on craft 1 is in battle 1", lambda: cell_names(h, x, [ZZZ], MSG1)),
                            ("2 the host stores both seated guests at the craft-1 prompt",
                             lambda: cell_store(store(x["battle1Prompt"]["host"]), "at the craft-1 prompt"))]), None),
    ("H19b-2", stage("H19b-1", lambda h, c, x: [("end_battle1", lambda: h19.end_battle(h, c, x, "end1")),
                                                ("returns_client", lambda: h19.returns(h, c, x, "client")),
                                                ("land_c2", lambda: land_craft(h, c, x, "land2", x["c2"]))]),
     every(lambda h, c, x: [("1 the guest seated on craft 2 is in battle 2", lambda: cell_names(
         h, x, [YYY], "Guest Yyy, seated on the landing craft, is not in battle 2")),
         ("2 the host stores both seated guests at the craft-2 prompt",
          lambda: cell_store(store(x["land2"]["atPrompt"]["host"]), "at the craft-2 prompt"))]), "H19b-1"),
    ("H19b-3", stage("H19b-2", lambda h, c, x: [("end_battle2", lambda: h19.end_battle(h, c, x, "end2")),
                                                ("returns_host", lambda: returns_host(h, c, x)),
                                                ("rejoin", lambda: rejoin(h, c, x, PORT))]),
     every(lambda h, c, x: [("1 the host's store refilled within 5 s of both geoscapes", lambda: cell_refill(x)),
                            ("2 the host stores both seated guests after the rejoin",
                             lambda: cell_store(store(x["rejoin"]["final"]["host"]), "after the rejoin"))]), "H19b-2")]

def main():
    t0, results, walls = time.time(), {}, {}
    h19.boot("H19b", PORT, ROWS, results, walls)   # spawn/connect (miss: ONE CAPTURE, rows FAIL "boot"), run_row
    order = [r[0] for r in ROWS]
    passed, failed = [r for r in order if results.get(r)], [r for r in order if not results.get(r)]
    print(f"\ntest_w2_separate_guest_two_crafts: {len(passed)}/{len(order)} passed (pass={passed} fail={failed}) "
          f"in {time.time() - t0:.1f}s (walls {walls})", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
