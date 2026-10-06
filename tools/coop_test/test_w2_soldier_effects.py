"""W2-H18b (F6136, F6137, F6177, D226 a; spec rewrite/prompts/w2h18b_soldier_effects.md (e)-(f); TASK 0
w2h18b-task0/CONSTANTS.md): host-only soldier effects reach the SHARED replica. Mod Coop_SoldierEffects_Test: sick bay
STR_H18B_SICKBAY (+0.5 hp/day) at (0, 3), index 9 (F7408); the Avenger with one pilot seat; STR_SOLDIER dogfightExperience
100 %; pilots never survive an evacuation. Boot A (SHARED, one boot): H18b-1 stale day_tick cache (stock), H18b-2 sick-bay
fraction, H18b-3 daily pilot list reset, H18b-4 pilot dogfight award (last of Part A/B), H18b-5 crewless lost craft, H18b-6
crewed lost craft (last). Boot B (SEPARATE): H18b-7 guard row. Levers client first (S25). roll = TASK 0's exact one-day
recipe (guard: host day + 1, month unchanged). window = both probes every 0.25 s for 3 s; RED cells at the FIRST sample with
the client's requests == R0 (F7291). hold (Part C) = host SoldiersState the moment its craft is gone; release = close_screens.
clean = wait_resync_clear, drain client then host, 4 s after the window / release: requests == R0 through it is a verdict
when the replica matched at the first sample, else recorded (a repair restream on the red build, never a verdict).
RED: H18b-1..6 fail on the replica's cells, H18b-7 passes; GREEN: all pass. "G:" = guard (a miss prints one CAPTURE).
EVIDENCE then PASS / FAIL per row; every row runs after a failure; ONE run; exit 0 only if all pass, else 2.
"""

import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_SoldierEffects_Test")
BOOT_A = ("w2h18ba", (49384, 49385, 47364))
BOOT_B = ("w2h18bb", (49386, 49387), "47366")
FAC, FAC_IDX = "STR_H18B_SICKBAY", 9                  # TASK 0 F7408
AV, SKY, INT = "STR_AVENGER", "STR_SKYRANGER", "STR_INTERCEPTOR"
CRASHED, HOURS = 2, 72                                # ufo status crashed; xcom1 timePersonnel (TASK 0 F7419)
XP0, XP_STAGED = {"firing": 0, "reactions": 0, "bravery": 0}, {"firing": 2, "reactions": 2, "bravery": 20}
WIN_S, WIN_I, CLEAN_S, GEO = 3.0, 0.25, 4.0, "GeoscapeState"

short = lambda e, n=600: (lambda s: s if len(s) <= n else s[:n] + "...")(f"{type(e).__name__}: {e}")  # noqa: E731
stack = session.states_stripped
recs = lambda p: {s["id"]: s for s in p["soldiers"]}  # noqa: E731
fx = lambda gc, ids=None: gc.ok(dict({"cmd": "soldier_fx_probe"}, **({} if ids is None else {"ids": ids})))  # noqa: E731
rs = lambda gc: {k: v for k, v in gc.cmd({"cmd": "shared_resync_stats"}).items() if k in ("requests", "pending")}  # noqa
on_geo = lambda *gcs: all(stack(gc)[-1:] == [GEO] for gc in gcs)  # noqa: E731
key = lambda s: [s["firing"], s["reactions"], s["bravery"]]  # noqa: E731
has = lambda cs, cid, ct: any(c[1:] == [cid, ct] for c in cs)  # noqa: E731
pump = lambda h, c, speed=0: geo.skip_realtime(h, c, 1, speed_idx=speed, stuck_timeout=None)  # noqa: E731


class Miss(Exception):  # a guard missed: the row stops there (one CAPTURE line printed); the next row still runs
    pass


def wait_until(pred, timeout, interval=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    return pred()


def ss(gc):
    r = gc.cmd({"cmd": "shared_stats"})
    return {k: r.get(k) for k in ("cmd", "applyCount")}


def date(gc):
    t = gc.cmd({"cmd": "geo_state"}).get("time") or {}
    return [t.get(k) for k in ("year", "month", "day", "hour", "minute")]


def crafts(gc):  # [base index, id, type] of every craft of every base
    return [[i, c.get("id"), c.get("type")] for i, b in enumerate(gc.cmd({"cmd": "geo_state"}).get("bases") or [])
            for c in b.get("crafts") or []]


def tp(gc):  # transform_probe (first real base): soldiers [id, where, craftId], soldier transfers [id, hours] in list order
    r = gc.cmd({"cmd": "transform_probe"})
    return {"soldiers": [[s.get("id"), s.get("where"), s.get("craftId")] for s in r.get("soldiers") or []],
            "transfers": [[t.get("soldierId"), t.get("hours")] for t in r.get("transfers") or [] if t.get("kind") == "soldier"],
            "error": r.get("error")}


def fac_index(gc):
    facs = ((gc.cmd({"cmd": "geo_state"}).get("bases") or [{}])[0]).get("facilities") or []
    hits = [i for i, f in enumerate(facs) if (f.get("type"), f.get("x"), f.get("y")) == (FAC, 0, 3)]
    return hits[0] if hits else None


def ufo(gc, uid):
    return next((u for u in gc.cmd({"cmd": "geo_state"}).get("ufos") or [] if u.get("id") == uid), None)


def df_for(gc, cid, uid):
    return next((d for d in gc.cmd({"cmd": "dogfight_state"}).get("dogfights") or []
                 if (d.get("craftId"), d.get("ufoId"), d.get("craftType")) == (cid, uid, AV)), None)


def capture(tag, x, why):
    cap = {}
    for gc in (x.host, x.client):
        try:
            cap[gc.name] = {"soldier_fx_probe": gc.cmd({"cmd": "soldier_fx_probe"}), "transform_probe": tp(gc),
                            "crafts": crafts(gc), "stack": stack(gc), "shared_stats": gc.cmd({"cmd": "shared_stats"}),
                            "shared_resync_stats": gc.cmd({"cmd": "shared_resync_stats"}),
                            "dogfights": gc.cmd({"cmd": "dogfight_state"}).get("dogfights")}
        except Exception as e:
            cap[gc.name] = f"probe failed: {short(e)}"
    print(f"CAPTURE {tag} ({why}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)


class Row:
    def __init__(self, rid, x):
        self.rid, self.x, self.ev, self.fails, self.passed = rid, x, {}, [], []

    def cell(self, name, ok, detail=""):
        (self.passed.append(name) if ok else self.fails.append(f"{name}: {detail}"))
        return bool(ok)

    def need(self, name, ok, detail=""):
        if not self.cell("G:" + name, ok, detail):
            capture(self.rid, self.x, name)
            raise Miss(name)

    def report(self, results):
        self.ev["cellsPassed"] = self.passed
        print(f"EVIDENCE {self.rid}: {json.dumps(self.ev, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else
              f"FAIL {self.rid}: {len(self.fails)} cell(s): " + " | ".join(self.fails), flush=True)


def show(r, tag, read, x):
    for gc in (x.host, x.client):
        print(f"PROBE {r.rid} {tag} {gc.name}: {json.dumps(read(gc), sort_keys=True, default=str)}", flush=True)


def roll(r, x, tag):  # TASK 0 (ii) exact one-day roll: host set_geo_day {today, 23}; skip 120 game minutes at speed 4
    h, c = x.host, x.client
    h.ok({"cmd": "set_geo_day", "day": date(h)[2], "hour": 23})
    d1 = {gc.name: date(gc) for gc in (h, c)}
    sk = geo.skip_ingame_time(h, c, 120, speed_idx=4, real_timeout=30)
    d2 = {gc.name: date(gc) for gc in (h, c)}
    days = (datetime.date(*d2["host"][:3]) - datetime.date(*d1["host"][:3])).days
    r.ev[tag] = {"from": d1, "to": d2, "days": days, "skip": {k: sk.get(k) for k in ("game_minutes", "timed_out", "dismissed")}}
    r.need(tag, days == 1 and d2["host"][1] == d1["host"][1] and not sk.get("timed_out"), r.ev[tag])


def window(r, x, st, read):  # both probes every 0.25 s for 3 s; the RED cells read the FIRST sample (client requests == R0)
    samples, t0 = [], time.time()
    while True:
        t = round(time.time() - t0, 2)
        samples.append({"t": t, "host": read(x.host), "client": read(x.client), "req": rs(x.client)["requests"]})
        if t >= WIN_S:
            break
        time.sleep(WIN_I)
    st["t_ref"], st["reqs"] = time.time(), [s["req"] for s in samples]
    for tag, s in (("first", samples[0]), ("end", samples[-1])):
        for n in ("host", "client"):
            print(f"PROBE {r.rid} {tag} t={s['t']} {n}: {json.dumps(s[n], sort_keys=True, default=str)}", flush=True)
    r.ev["window [t, client requests]"] = [[s["t"], s["req"]] for s in samples]
    r.need("requestsFirst", samples[0]["req"] == st["r0"], f"client requests {samples[0]['req']} at the first sample, R0 {st['r0']}")
    return samples[0], samples[-1]


def stage_recovery(r, x, sid, days):  # set_soldier_recovery client then host; both probes read it back (guard)
    rep = {gc.name: gc.ok({"cmd": "set_soldier_recovery", "soldierId": sid, "days": days}).get("recovery") for gc in (x.client, x.host)}
    p = {gc.name: recs(fx(gc, [sid]))[sid] for gc in (x.host, x.client)}
    r.ev[f"staged id {sid} [reply, recovery, recoveryExact, daysToHeal]"] = {
        n: [rep[n], p[n]["recovery"], p[n]["recoveryExact"], p[n]["daysToHeal"]] for n in p}
    r.need("staged", all(rep[n] == days and p[n]["recovery"] == days and p[n]["recoveryExact"] == days for n in p), p)


def clean(r, x, st):
    h, c = x.host, x.client
    cl = r.ev["clean"] = {}
    if st.get("held"):                                 # a guard missed inside the hold: release it first
        cl["release"] = h.cmd({"cmd": "close_screens"}).get("popped")
        st["held"] = False
    if st.get("fights"):                               # H18b-4: the Avenger's fights close on both (speed-2 pump)
        av, uid, t0 = st["fights"][0], st["fights"][1], time.time()
        while time.time() - t0 < 60 and (df_for(h, av, uid) or df_for(c, av, uid)):
            pump(h, c, 2)
            time.sleep(0.2)
        cl["fightsCloseS"] = round(time.time() - t0, 1)
        r.need("fightsClosed", not df_for(h, av, uid) and not df_for(c, av, uid), cl)
    cl["pendingWait"] = geo.wait_resync_clear(c, timeout=10)
    cl["client"], cl["host"] = geo.drain_popups(c), geo.drain_popups(h)
    r.need("cleanGeoscape", wait_until(lambda: on_geo(h, c), 10, 0.2), f"stacks {stack(h)} / {stack(c)}")
    if "t_ref" not in st:
        return
    time.sleep(max(0.0, st["t_ref"] + CLEAN_S - time.time()))
    cl["requests"] = q = rs(c)
    reqs = sorted(set(st["reqs"] + [q["requests"]]))
    if st.get("matched"):
        r.cell("requests", reqs == [st["r0"]] and not q["pending"], f"client requests {reqs} / {q} vs R0 {st['r0']} (a repair fired)")
    else:
        r.ev["requests [R0, seen through the window and 4 s after] (recorded, not a verdict: the replica diverged)"] = [st["r0"], reqs]


def row_1(r, x, st):  # a healed one-day wound (stock, F7278)
    h, c = x.host, x.client
    s0 = {gc.name: ss(gc) for gc in (h, c)}
    roll(r, x, "primeRoll")
    r.ev["prime shared_stats [before, after] (day_tick + 1 on the host process's first roll, F7411)"] = {
        gc.name: [s0[gc.name], ss(gc)] for gc in (h, c)}
    stage_recovery(r, x, 3, 1)
    show(r, "S0", lambda gc: recs(fx(gc, [3])), x)
    st["r0"] = rs(c)["requests"]
    roll(r, x, "roll")
    first, _end = window(r, x, st, lambda gc: recs(fx(gc, [3])))
    hf, cf = first["host"][3], first["client"][3]
    r.ev["id 3 [recovery, recoveryExact, daysToHeal] host / client"] = [[hf[k], cf[k]] for k in ("recovery", "recoveryExact", "daysToHeal")]
    r.need("hostHealed", hf["recoveryExact"] == 0 and hf["daysToHeal"] == 0, hf)
    st["matched"] = r.cell("recovery", [cf["recoveryExact"], cf["daysToHeal"]] == [0, 0],
                           "a soldier healed on the host stays wounded on the replica (stale day_tick cache)"
                           if cf["recovery"] == 1 else f"client {cf}")


def row_2(r, x, st):  # sick-bay fraction (mod, F7277)
    h, c = x.host, x.client
    r.ev["fac_build"] = h.cmd({"cmd": "fac_build", "facility": FAC, "x": 0, "y": 3}).get("ok")
    r.need("facilityListed", wait_until(lambda: fac_index(h) == FAC_IDX and fac_index(c) == FAC_IDX, 10),
           f"index host {fac_index(h)} client {fac_index(c)} (want {FAC_IDX})")
    bt = {gc.name: gc.cmd({"cmd": "set_facility_build_time", "baseId": 0, "index": FAC_IDX, "time": 0}) for gc in (c, h)}
    r.need("buildTime0", all(v.get("ok") and v.get("type") == FAC and v.get("buildTime") == 0 for v in bt.values()), bt)
    sb = r.ev["bases [index, sickBayAbs, sickBayRel]"] = {
        gc.name: [[b["index"], b["sickBayAbs"], b["sickBayRel"]] for b in fx(gc, [])["bases"]] for gc in (h, c)}
    r.need("sickBay", all(v[:1] and v[0][1] == 0.5 for v in sb.values()), sb)
    stage_recovery(r, x, 4, 3)
    show(r, "S0", lambda gc: recs(fx(gc, [4])), x)
    st["r0"] = rs(c)["requests"]
    roll(r, x, "roll")
    first, _end = window(r, x, st, lambda gc: recs(fx(gc, [4])))
    hf, cf = first["host"][4], first["client"][4]
    ex = lambda s: [round(s["recoveryExact"], 4), s["daysToHeal"]]  # noqa: E731
    r.ev["id 4 [recoveryExact, daysToHeal] host / client"] = [ex(hf), ex(cf)]
    r.need("hostFraction", ex(hf) == [1.5, 1], hf)
    st["matched"] = r.cell("recovery", ex(cf) == ex(hf), "the replica's wound recovery is the host's rounded value (F6136)"
                           if cf["recoveryExact"] == 2 else f"client {cf}")


def row_3(r, x, st):  # the daily pilot list reset (mod)
    h, c = x.host, x.client
    rep = {gc.name: gc.ok(dict({"cmd": "set_soldier_dogfight_xp", "soldierId": 7}, **XP_STAGED)).get("dogfightXp")
           for gc in (c, h)}
    p = {gc.name: recs(fx(gc, [7]))[7]["dogfightXp"] for gc in (h, c)}
    r.ev["staged id 7 dogfightXp [reply, probe]"] = {n: [rep[n], p[n]] for n in p}
    r.need("staged", all(v == XP_STAGED for v in list(rep.values()) + list(p.values())), r.ev["staged id 7 dogfightXp [reply, probe]"])
    show(r, "S0", lambda gc: recs(fx(gc, [7])), x)
    st["r0"] = rs(c)["requests"]
    roll(r, x, "roll")
    first, _end = window(r, x, st, lambda gc: recs(fx(gc, [7])))
    hx, cx = first["host"][7]["dogfightXp"], first["client"][7]["dogfightXp"]
    r.ev["id 7 dogfightXp host / client"] = [hx, cx]
    r.need("hostReset", hx == XP0, hx)
    st["matched"] = r.cell("dogfightXp", cx == hx, "the replica keeps yesterday's pilot experience" if cx == XP_STAGED else f"client {cx}")


def row_4(r, x, st):  # pilot experience (mod, F7279): the test_shared_dogfight_dest crash recipe with the mod Avenger
    h, c = x.host, x.client
    b0 = next(b for b in h.ok({"cmd": "geo_state"})["bases"] if not b.get("coopBase") and not b.get("coopIcon"))
    sc = {gc.name: gc.ok({"cmd": "spawn_craft", "type": AV, "weapon": "STR_CANNON_UC"}).get("craft_id") for gc in (h, c)}
    r.need("avenger", sc["host"] == sc["client"], sc)
    av = sc["host"]
    asg = {gc.name: gc.cmd({"cmd": "assign_crew", "soldier_id": 1, "craft_id": av, "craft_type": AV}).get("ok") for gc in (c, h)}
    crew = {gc.name: [m.get("id") for m in gc.cmd({"cmd": "craft_pilots_probe", "craftId": av, "craftType": AV}).get("crew") or []]
            for gc in (h, c)}
    r.ev["avenger, assign_crew ok, crew before launch"] = [av, asg, crew]
    r.need("seat", all(asg.values()) and all(v == [1] for v in crew.values()), r.ev["avenger, assign_crew ok, crew before launch"])
    s0 = {gc.name: recs(fx(gc, [1]))[1] for gc in (h, c)}
    show(r, "S0", lambda gc: recs(fx(gc, [1])), x)
    uid = h.ok({"cmd": "spawn_ufo", "type": "STR_MEDIUM_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA",
                "race": "STR_SECTOID", "trajectory": "P0", "state": "flying", "speed": 1, "lon": b0["lon"] + 0.03,
                "lat": b0["lat"]})["ufo_id"]
    dmax = h.ok({"cmd": "set_ufo_damage", "ufo_id": uid, "damage": 0})["damageMax"]
    h.ok({"cmd": "set_ufo_damage", "ufo_id": uid, "damage": dmax // 2})
    t0 = time.time()
    while time.time() - t0 < 45 and ufo(c, uid) is None:
        pump(h, c)
        time.sleep(0.2)
    r.ev["ufo [id, damageMax, on the client s]"] = [uid, dmax, round(time.time() - t0, 1)]
    r.need("ufoOnClient", ufo(c, uid) is not None, "the client never materialised the UFO")
    c.ok({"cmd": "craft_order", "order": "target", "craft_id": av, "craft_type": AV, "ufo_id": uid})
    st["fights"], t1 = (av, uid), time.time()
    while time.time() - t1 < 120 and not (df_for(h, av, uid) and df_for(c, av, uid)):
        pump(h, c)
        time.sleep(0.2)
    pil = {gc.name: gc.cmd({"cmd": "craft_pilots_probe", "craftId": av, "craftType": AV}).get("pilots") for gc in (h, c)}
    r.ev["fights open s, pilots in the fight"] = [round(time.time() - t1, 1), pil]
    r.need("fightsOpen", bool(df_for(h, av, uid) and df_for(c, av, uid)), {gc.name: df_for(gc, av, uid) for gc in (h, c)})
    r.need("pilot", all(v == [1] for v in pil.values()), pil)
    st["r0"], t2, n, crashed = rs(c)["requests"], time.time(), 0, False
    while time.time() - t2 < 150 and not crashed:
        h.cmd({"cmd": "dogfight_action", "action": "aggressive", "craft_id": av, "ufo_id": uid})
        pump(h, c)
        n += 1
        crashed = (ufo(h, uid) or {}).get("status") == CRASHED
        if not crashed:
            time.sleep(0.2)
    r.ev["crash [s, aggressive iterations]"] = [round(time.time() - t2, 1), n]
    r.need("crash", crashed, ufo(h, uid))
    first, _end = window(r, x, st, lambda gc: recs(fx(gc, [1])))     # speed 0, right after the crash (CONSTANTS 5)
    hf, cf = first["host"][1], first["client"][1]
    r.ev["id 1 [firing, reactions, bravery] + dogfightXp: S0 host, host, S0 client, client"] = [
        [key(s), s["dogfightXp"]] for s in (s0["host"], hf, s0["client"], cf)]
    r.need("hostAward", [a - b for a, b in zip(key(hf), key(s0["host"]))] == [1, 1, 10]
           and hf["dogfightXp"] == {"firing": 1, "reactions": 1, "bravery": 10}, [key(s0["host"]), key(hf), hf["dogfightXp"]])
    same0 = key(cf) == key(s0["client"]) and cf["dogfightXp"] == s0["client"]["dogfightXp"]
    st["matched"] = r.cell("pilotXp", key(cf) == key(hf) and cf["dogfightXp"] == hf["dogfightXp"],
                           "the host's pilot experience never reached the replica (F6137)" if same0
                           else f"client {key(cf)} {cf['dogfightXp']} vs host {key(hf)} {hf['dogfightXp']}")


def lose(r, x, st, cid, ctype):  # host-only damage (the dogfight's outcome); the hold the moment the host's craft is gone
    h, t0 = x.host, time.time()
    r.ev["craft_force"] = {k: v for k, v in h.cmd({"cmd": "craft_force", "craft_id": cid, "damage": 100000}).items()
                           if k in ("ok", "craft_id", "error")}
    gone = wait_until(lambda: not has(crafts(h), cid, ctype), 3.0, 0.1)
    if gone:
        st["held"] = bool(h.cmd({"cmd": "open_screen", "screen": "soldiers"}).get("ok"))
    r.ev["host gone s, host stack at the hold"] = [round(time.time() - t0, 2), stack(h)]
    r.need("hostGone", gone, crafts(h))
    r.need("hold", st["held"] and stack(h)[-1:] == ["SoldiersState"], stack(h))


def release(r, x, st):
    r.ev["release popped"] = x.host.cmd({"cmd": "close_screens"}).get("popped")
    st["held"], st["t_ref"] = False, time.time()


part_c = lambda gc: {"crafts": crafts(gc), "tp": tp(gc)}  # noqa: E731


def row_5(r, x, st):  # a crewless craft lost (stock, F7281)
    h, c = x.host, x.client
    r.ev["geo_set_speed 0"] = [gc.cmd({"cmd": "geo_set_speed", "idx": 0}).get("ok") for gc in (h, c)]
    show(r, "S0", part_c, x)
    r.need("craftS0", all(has(crafts(gc), 2, INT) for gc in (h, c)), {gc.name: crafts(gc) for gc in (h, c)})
    st["r0"] = rs(c)["requests"]
    lose(r, x, st, 2, INT)
    first, end = window(r, x, st, part_c)
    release(r, x, st)
    kept, kept_end = has(first["client"]["crafts"], 2, INT), has(end["client"]["crafts"], 2, INT)
    r.ev["INTERCEPTOR-2 listed: host first, client first, client end"] = [has(first["host"]["crafts"], 2, INT), kept, kept_end]
    st["matched"] = r.cell("craft", not kept, f"a lost craft stays on the replica (still listed at the window's end: {kept_end})")


def row_6(r, x, st):  # a crewed craft lost: evacuation and a pilot killed (F6177; last in Boot A)
    h, c = x.host, x.client
    sp = {gc.name: gc.cmd({"cmd": "set_craft_pilots", "craftId": 1, "craftType": SKY, "pilots": [5]}) for gc in (c, h)}
    r.need("pilots", all(v.get("ok") and v.get("pilots") == [5] for v in sp.values()), sp)
    crew = {gc.name: [m.get("id") for m in gc.cmd({"cmd": "craft_pilots_probe", "craftId": 1, "craftType": SKY}).get("crew") or []]
            for gc in (h, c)}
    r.ev["SKYRANGER-1 crew S0"] = crew
    r.ev["crew training S0 (host; no probe reads a soldier in transfer)"] = {
        s["id"]: s["training"] for s in h.ok({"cmd": "soldier_training_probe", "ids": crew["host"]})["soldiers"]}
    r.need("crewS0", 5 in crew["host"] and crew["host"] == crew["client"], crew)
    show(r, "S0", part_c, x)
    want = [[i, HOURS] for i in crew["host"] if i != 5]
    st["r0"] = rs(c)["requests"]
    lose(r, x, st, 1, SKY)
    first, end = window(r, x, st, part_c)
    release(r, x, st)
    hp, cp = first["host"], first["client"]
    where = lambda p: {s[0]: s[1] for s in p["tp"]["soldiers"]}  # noqa: E731
    hw, cw = where(hp), where(cp)
    r.ev["first sample [SKYRANGER-1 listed, id 5 where, soldier transfers] host / client"] = [
        [has(p["crafts"], 1, SKY), w.get(5), p["tp"]["transfers"]] for p, w in ((hp, hw), (cp, cw))]
    r.need("hostOutcome", not has(hp["crafts"], 1, SKY) and hw.get(5) == "dead" and hp["tp"]["transfers"] == want,
           {"want transfers": want, "host": r.ev["first sample [SKYRANGER-1 listed, id 5 where, soldier transfers] host / client"][0]})
    sky = has(cp["crafts"], 1, SKY)
    c1 = r.cell("craft", not sky, "the lost craft and its crew stay on the replica: SKYRANGER-1 still listed")
    c2 = r.cell("crew", cp["tp"]["transfers"] == hp["tp"]["transfers"] and all(cw.get(i) == hw.get(i) for i in crew["host"]),
                f"client transfers {cp['tp']['transfers']}, crew where {[cw.get(i) for i in crew['host']]} vs host "
                f"{hp['tp']['transfers']}, {[hw.get(i) for i in crew['host']]}")
    c3 = r.cell("dead", cw.get(5) == "dead", f"the lost craft's pilot (id 5) is '{cw.get(5)}' on the replica")
    st["matched"] = c1 and c2 and c3


def row_7(r, x, st):  # SEPARATE keeps its own day (Boot B; guard row)
    h, c = x.host, x.client
    p = fx(c)
    own = [s for s in p["soldiers"] if s["baseIndex"] == 0]
    r.need("ownBase", p["bases"][:1] and p["bases"][0]["index"] == 0 and own, p["bases"])
    sid = own[0]["id"]
    s0 = {gc.name: ss(gc) for gc in (h, c)}
    rep = c.ok({"cmd": "set_soldier_recovery", "soldierId": sid, "days": 1})          # client only
    staged = recs(fx(c, [sid]))[sid]
    r.ev["soldier, reply, staged"] = [sid, rep.get("recovery"), staged]
    r.need("staged", rep.get("recovery") == 1 and staged["recovery"] == 1 and staged["baseIndex"] == 0, r.ev["soldier, reply, staged"])
    roll(r, x, "roll")
    after = recs(fx(c, [sid]))[sid]
    s1 = {gc.name: ss(gc) for gc in (h, c)}
    r.ev["after the roll: client soldier, shared_stats [before, after]"] = [after, s0, s1]
    r.cell("ownHeal", after["recoveryExact"] == 0 and after["recovery"] == 0, after)
    r.cell("sharedStats", s0 == s1, [s0, s1])


def run_row(rid, steps, x, results):
    r, st, t0 = Row(rid, x), {}, time.time()
    for step in steps:                                # the clean runs after a miss too, so the next row starts clean
        try:
            step(r, x, st)
        except Miss:
            pass
        except Exception as e:
            r.cell("exception in " + step.__name__, False, short(e, 800))
            capture(rid, x, "exception")
    r.ev["wallS"] = round(time.time() - t0, 1)
    r.report(results)


def boot_miss(tag, e, rids, results):
    print(f"CAPTURE {tag} (boot miss): {short(e, 1500)}", flush=True)
    for rid in rids:
        results[rid] = False
        print(f"EVIDENCE {rid}: {json.dumps({'boot': tag})}\nFAIL {rid}: boot", flush=True)


def boot_a(results, walls):
    (tag, ports), t0 = BOOT_A, time.time()
    rows = (("H18b-1", row_1), ("H18b-2", row_2), ("H18b-3", row_3), ("H18b-4", row_4), ("H18b-5", row_5), ("H18b-6", row_6))
    try:
        js = shared_fixture.bring_up(tag, ports, mods=(MOD,))
    except Exception as e:
        return boot_miss(tag, e, [rid for rid, _f in rows], results)
    walls[tag + " bring-up"] = round(time.time() - t0, 1)
    try:
        x = type("X", (), {"host": js.host, "client": js.client})
        for rid, fn in rows:
            run_row(rid, (fn, clean), x, results)
    finally:
        js.shutdown()
        walls[tag] = round(time.time() - t0, 1)


def boot_b(results, walls):
    (tag, labels, lobby), t0 = BOOT_B, time.time()
    h = GameClient("host", labels[0], make_user_dir(tag + "_host", mods=(MOD,)))
    c = GameClient("client", labels[1], make_user_dir(tag + "_client", mods=(MOD,)))
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=lobby, campaign_mode="coop")
            geo.wait_both_ready(h, c)
        except Exception as e:
            return boot_miss(tag, e, ["H18b-7"], results)
        walls[tag + " bring-up"] = round(time.time() - t0, 1)
        run_row("H18b-7", (row_7,), type("X", (), {"host": h, "client": c}), results)
    finally:
        shutdown_clients(h, c)
        walls[tag] = round(time.time() - t0, 1)


def main():
    t0, results, walls = time.time(), {}, {}
    boot_a(results, walls)
    boot_b(results, walls)
    order = ["H18b-%d" % n for n in range(1, 8)]
    failed = [n for n in order if not results.get(n)]
    print(f"\ntest_w2_soldier_effects: {len(order) - len(failed)}/{len(order)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
