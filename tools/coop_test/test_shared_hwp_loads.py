"""In SHARED, a tank (HWP) loaded onto or unloaded from a craft on the craft equipment screen - by the arrows, the
clear key or a craft loadout template - ends as a host-applied craft_equip end-state on both machines; without the fix
it stays on the clicking machine until a world re-copy reverts the client (the only carrier of the host's move).
SKY / HostBase index / option OFF / seats from sbe.setup. V(gc) = base_screen_op {op: craft_vehicles, base: HostBase,
craft_id: SKY, craft_type: STR_SKYRANGER} (vehicles, order, vehicleAmmo, spaceUsed, customDeployment); ST(gc) =
geo_state HostBase items; SKYI(gc) = base_report HostBase SKY items; reqs = the client's
shared_resync_stats.requests. move(gc, item, n) = the craft_equip test command (the real CES move; its `moved` only
says the item is on the screen's list, so verdicts read V and ST). W = 10 s at 0.25 s; RW 5 s; AP 30.
park = host open_soldiers (no heartbeat), release = unpark + reqs over RW + converge (test_shared_craft_loads'
helpers); every row starts with converge + client shared_reset_resync_stats, again after a setup that moved a tank.
strip = host move -n for every type in the host's V.
Each row's main cell fails without the fix:
Boot shared (SHARED, 49441 / 49442 / 47935; stock TC 2, shells 60, TLC 1 on both):
  hwp_load_1 parked client TC +1 (deploy_mark on both first); main cell: the host's V {} after W.
  hwp_load_2 parked client TC -1; main cell: the host's V {TC: 1} after W.
  hwp_load_3 host TLC +1 (deploy_mark on both); main cell: reqs +1 within W or V unequal.
  hwp_load_4 host TLC -1; main cell: as hwp_load_3.
  hwp_load_5 parked client template load (SKYI + TC 1); main cell: the host's V {} after W.
  hwp_load_6 client raw craft_equip {TC, 2}; main cell: "vehicles not routed" within W (cleanup: ONE close_screens on
  the client).
  hwp_load_7 js.finish().
Boot separate (SEPARATE, tag hwp_loads_separate, labels 49443 / 49444, lobby 47936): hwp_load_8 (guard): 4 of the
  client's SKY crew off by craft_assign to make room for a tank (spaceAvailable >= 4, EVIDENCE), client TC +1 -> its
  V {TC: 1}, stores TC -1 / shells -AP; both shared_stats unchanged 1 s later.
A row whose main cell fails evaluates no later cell. EVIDENCE line per row before its verdict; a failed row prints ONE
CAPTURE line (both machines' V, SKYI, ST, shared_stats, shared_resync_stats, stacks); a boot miss fails its rows
"boot". Every row runs after a failure. ONE run; exit 0 iff everything passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_shared_base_equip as sbe  # noqa: E402  (main-guarded: X, setup, q / stack / wait_until)
import test_shared_craft_loads as cl  # noqa: E402  (main-guarded: park, release, converge, guard, sky, st, rs, watch, timed, Row)
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402
from test_shared_base_equip import q, stack, wait_until  # noqa: E402
from test_shared_base_writes import bso  # noqa: E402

TAG_SHARED, PORTS_SHARED = "hwp_loads_shared", (49441, 49442, 47935)
TAG_SEPARATE, LABELS_SEPARATE, LOBBY_SEPARATE = "hwp_loads_separate", (49443, 49444), "47936"
HB, CB, GEO, SKYR = "HostBase", "ClientBase", "GeoscapeState", "STR_SKYRANGER"
TC, TLC, SH = "STR_TANK_CANNON", "STR_TANK_LASER_CANNON", "STR_HWP_CANNON_SHELLS"
AP, W, POLL, RW, SETTLE, SPACE0 = 30, 10.0, 0.25, cl.RW, 1.0, 6  # AP 30, RW 5 s, spaceAvailable 6 with no tank
NOT_ROUTED = "vehicles not routed"
ROWS_SHARED, ROWS_SEPARATE = ["hwp_load_%d" % n for n in range(1, 8)], ["hwp_load_8"]
ORDER = ROWS_SHARED + ROWS_SEPARATE


def V(gc, x, base=HB, cid=None):
    r = bso(gc, op="craft_vehicles", base=base, craft_id=x.sky if cid is None else cid, craft_type=SKYR)
    return {k: r.get(k) for k in ("vehicles", "order", "vehicleAmmo", "spaceUsed", "spaceAvailable", "customDeployment", "error")}


def vk(v):
    return [v.get(k) for k in ("vehicles", "order", "vehicleAmmo", "spaceUsed")]


def mark(gc, x):
    return bso(gc, op="deploy_mark", base=HB, craft_id=x.sky, craft_type=SKYR)


def move(gc, x, item, n, base=HB, cid=None):
    return q(gc, {"cmd": "craft_equip", "item": item, "count": n, "base": base, "craft_id": x.sky if cid is None else cid})


def stats3(gc):
    r = q(gc, {"cmd": "shared_stats"})
    return {k: r.get(k) for k in ("cmd", "applyCount", "failCount", "lastFail")}


def same(x, cd=None):
    """V (vehicles, order, vehicleAmmo, spaceUsed), SKYI and ST equal on both; customDeployment equal (== cd when given)."""
    vh, vc = V(x.host, x), V(x.client, x)
    d = [vh.get("customDeployment"), vc.get("customDeployment")]
    return vk(vh) == vk(vc) and (d == [cd, cd] if cd is not None else d[0] == d[1]) and cl.equal(x)


def both_v(x):
    return {g.name: V(g, x) for g in (x.host, x.client)}


class Row(cl.Row):
    def report(self, results):
        self.evidence()
        if self.fails:
            for g in (self.x.host, self.x.client):
                b = self.x.base
                cid = getattr(self.x, "sky_s", None) if b == CB else None
                self.cap[g.name] = {"V": V(g, self.x, b, cid), "SKYI": cl.sky(g, cid or self.x.sky, b), "ST": cl.st(g, b),
                                    "shared_stats": q(g, {"cmd": "shared_stats"}), "shared_resync_stats": q(g, {"cmd": "shared_resync_stats"}),
                                    "stack": stack(g)}
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def guard_v(r, x, want, tag):
    v = both_v(x)
    r.ev["V " + tag] = v
    return r.cell(f"guard: V.vehicles == {want} on both ({tag})", all(e.get("vehicles") == want for e in v.values()), v)


def strip(r, x):
    """host move -n for every type in the host's V, then converge (without the fix: by the re-copy) + reset."""
    v = V(x.host, x).get("vehicles") or {}
    mv = [move(x.host, x, t, -n) for t, n in sorted(v.items())]
    r.ev["strip"] = {"host V": v, "moves": mv}
    return not mv or cl.guard(r, x, "after the strip")


def parked(r, x, act, cd=None):
    """park, the client's act, then until V / SKYI / ST equal on both within W; the host's V read after W; release always."""
    a = w = None
    if not cl.park(r, x):
        return a, w, cl.release(r, x)
    try:
        a = act()
        if a is not None:
            got, s = cl.timed(lambda: same(x, cd), W)
            w = {"equal": bool(got), "s": s, "V": both_v(x), "ST equal": cl.st(x.host) == cl.st(x.client)}
    finally:
        rel = cl.release(r, x)
    return a, w, rel


def check_sync(r, w, rel):
    if r.cell("V / SKYI / ST not equal on both within W", w["equal"], w):
        r.cell("the client asked for a world re-copy over RW after the unpark", rel["over RW"]["reqs"] == 0, rel["over RW"])


def client_move(x, r, n, reach_cell):
    """hwp_load_1 (n = +1, deploy_mark on both first) / hwp_load_2 (n = -1): the parked client moves one TC."""
    h, c = x.host, x.client
    if not cl.guard(r, x):
        return
    # hwp_load_2's setup: the host loads it (client on its geoscape)
    if n < 0 and (V(h, x).get("vehicles") or {}).get(TC) != 1:
        r.ev["setup move"] = move(h, x, TC, 1)
        if not cl.guard(r, x, "after the setup"):
            return r.evidence()
    if not guard_v(r, x, {} if n > 0 else {TC: 1}, "start"):
        return r.evidence()
    if n > 0:
        dm = r.ev["deploy_mark"] = {g.name: mark(g, x) for g in (h, c)}
        if not r.cell("non-vacuity: deploy_mark -> customDeployment true on both", all(v.get("customDeployment") is True
                                                                                       for v in dm.values()), dm):
            return r.evidence()

    def act():
        s0 = cl.st(c)
        mv = move(c, x, TC, n)
        return {"move": mv, "client V at once": V(c, x), "client ST diff": cl.diff(s0, cl.st(c))}
    a, w, rel = parked(r, x, act, False if n > 0 else None)
    r.ev.update({"act": a, "over W": w})
    r.evidence()
    if not (rel["ok"] and a and w):
        return
    if not r.cell("non-vacuity: the client's V (customDeployment false after a load) / ST at once", a["move"].get("moved") is True
                  and a["client V at once"].get("vehicles") == ({TC: 1} if n > 0 else {})
                  and (n < 0 or a["client V at once"].get("customDeployment") is False) and a["client ST diff"] == {TC: -n, SH: -AP * n}, a):
        return
    host_v = w["V"]["host"].get("vehicles")
    if not r.cell(reach_cell, host_v == ({TC: 1} if n > 0 else {}), {"host V after W": w["V"]["host"]}):
        return
    check_sync(r, w, rel)


def host_move(x, r, n, recopy_cell):
    """hwp_load_3 (n = +1, deploy_mark on both first; strip first) / hwp_load_4 (n = -1): the host moves the TLC,
    the client on its geoscape."""
    h, c = x.host, x.client
    if not cl.guard(r, x):
        return
    if n > 0 and not strip(r, x):
        return r.evidence()
    if not guard_v(r, x, {} if n > 0 else {TLC: 1}, "start"):
        return r.evidence()
    if n > 0:
        dm = r.ev["deploy_mark"] = {g.name: mark(g, x) for g in (h, c)}
        if not r.cell("non-vacuity: deploy_mark -> customDeployment true on both", all(v.get("customDeployment") is True
                                                                                       for v in dm.values()), dm):
            return r.evidence()
    s0 = cl.st(h)
    mv = move(h, x, TLC, n)
    v1, sd = V(h, x), cl.diff(s0, cl.st(h))
    t0, first, eq = time.time(), None, None
    while time.time() - t0 < W:  # until V / SKYI / ST equal on both (customDeployment false after a load); the client's reqs each poll
        if (cl.rs(c)[0] or 0) > 0 and first is None:
            first = round(time.time() - t0, 2)
        if same(x, False if n > 0 else None):
            eq = round(time.time() - t0, 2)
            break
        time.sleep(POLL)
    vv = both_v(x)
    over = cl.watch(x, RW)
    cv = cl.converge(x)  # the cleanup without the fix (the re-copy lands on the client's geoscape)
    r.ev.update({"move": mv, "host V at once": v1, "host ST diff": sd, "first req s": first, "equal s": eq, "V after": vv, "over RW": over,
                 "converge": [cv["ok"], cv["s"]]})
    r.evidence()
    if not r.cell("guard: converge after the row", cv["ok"], cv):
        return
    if not r.cell("non-vacuity: the host's V / customDeployment / ST at once", mv.get("moved") is True
                  and v1.get("vehicles") == ({TLC: 1} if n > 0 else {}) and (n < 0 or v1.get("customDeployment") is False)
                  and sd == {TLC: -n}, [mv, v1, sd]):
        return
    if not r.cell(recopy_cell, first is None and vk(vv["host"]) == vk(vv["client"]),
                  {"first req s": first, "V after": vv}):
        return
    r.cell("V / SKYI / ST not equal on both within W", eq is not None, eq)
    r.cell("the client asked for a world re-copy over RW", over["reqs"] == 0, over)


def row_template_load(x, r):
    h, c = x.host, x.client
    if not (cl.guard(r, x) and guard_v(r, x, {}, "start")):
        return r.evidence()
    items = dict(cl.sky(h, x.sky) or {})
    items[TC] = 1
    rep = q(c, {"cmd": "shared_cmd", "jcmd": "equip_template", "baseId": x.hb_index,
                "payload": {"kind": "loadout", "index": 1, "name": "", "items": items}})
    got, s = cl.timed(lambda: all(bso(g, op="read", index=1).get("loadout") == items for g in (h, c)), W)
    r.ev["template"] = {"items": items, "shared_cmd": rep, "read 1 equal s": s}
    if not r.cell("guard: template 1 (SKYI + TC 1) on both within W", rep.get("ok") and got, r.ev["template"]):
        return r.evidence()

    def act():
        k0 = cl.sky(c, x.sky)
        if not cl.open_ces(r, c, HB, x.sky):
            return None
        load = bso(c, op="loadout_load", index=1)
        s_load = stack(c)
        cl.close_ces(r, c)
        return {"loadout_load": load, "stack after load": s_load, "stack after OK": stack(c), "client V": V(c, x),
                "client SKYI unchanged": cl.sky(c, x.sky) == k0}
    a, w, rel = parked(r, x, act)
    r.ev.update({"act": a, "over W": w})
    r.evidence()
    if not (rel["ok"] and a and w):
        return
    if not r.cell("non-vacuity: the client's V {TC: 1}, its SKYI unchanged, its stack GeoscapeState only", a["loadout_load"].get("ok")
                  and a["client V"].get("vehicles") == {TC: 1} and a["client SKYI unchanged"] and a["stack after OK"] == [GEO], a):
        return
    if not r.cell("the client's craft loadout template load left its tank on the client",
                  w["V"]["host"].get("vehicles") == {TC: 1}, {"host V after W": w["V"]["host"]}):
        return
    check_sync(r, w, rel)


def row_raw_command(x, r):
    h, c = x.host, x.client
    if not (cl.guard(r, x) and strip(r, x)):
        return r.evidence()
    v = both_v(x)
    r.ev["V start"] = v
    if not r.cell(f"guard: V {{}} and spaceAvailable {SPACE0} on both", all(e.get("vehicles") == {} and e.get("spaceAvailable") == SPACE0
                                                                          for e in v.values()), v):
        return r.evidence()
    s0, f0, ts0 = {g.name: cl.st(g) for g in (h, c)}, stats3(c), time.time()
    rep = q(c, {"cmd": "shared_cmd", "jcmd": "craft_equip", "baseId": x.hb_index,
                "payload": {"craftId": x.sky, "craftType": SKYR, "item": TC, "count": 2}})
    refused = applied = None
    while time.time() - ts0 < W:
        f = stats3(c)
        if (f.get("failCount") or 0) > (f0.get("failCount") or 0):
            refused = [round(time.time() - ts0, 2), f.get("lastFail")]
            break
        if all(V(g, x).get("vehicles") == {TC: 1} for g in (h, c)) and cl.st(h) == cl.st(c):
            applied = round(time.time() - ts0, 2)
            break
        time.sleep(POLL)
    box = None
    if refused:  # the cleanup without the fix: ONE close_screens on the client (the refusal box)
        wait_until(lambda: any("CoopState" in e for e in stack(c)), 3.0)
        box = {"stack": stack(c), "close_screens": q(c, {"cmd": "close_screens"})}
        wait_until(lambda: stack(c)[-1:] == [GEO], 5.0)
        box["after"] = stack(c)
    time.sleep(SETTLE)
    f1, over = stats3(c), (cl.watch(x, RW) if refused is None else None)  # RW is a with-fix cell's window only
    v1, s1 = both_v(x), {g.name: cl.diff(s0[g.name], cl.st(g)) for g in (h, c)}
    r.ev.update({"shared_cmd": rep, "failCount before": f0, "refused": refused, "applied s": applied, "box": box, "V after": v1,
                 "ST diff": s1, "client stats after 1 s": f1, "over RW": over})
    r.evidence()
    if not r.cell("the host refuses an HWP on the craft", refused is None, {"refused [s, lastFail]": refused, "box": box}):
        return
    if r.cell("V.vehicles {TC: 1} on both within W", applied is not None and all(e.get("vehicles") == {TC: 1} for e in v1.values()), v1):
        r.cell("ST diff == {TC -1, shells -AP} on both", all(d == {TC: -1, SH: -AP} for d in s1.values()), s1)
    r.cell("the client's failCount changed after a 1 s settle", f1.get("failCount") == f0.get("failCount"), [f0, f1])
    r.cell("the client asked for a world re-copy over RW", over["reqs"] == 0, over)


def row_separate_stays_local(x, r):
    """SEPARATE (guard): 4 of the client's SKY crew off by craft_assign to make room, then its TC load stays local and
    sends nothing."""
    h, c = x.host, x.client
    rep = q(c, {"cmd": "base_report", "base": CB})
    x.sky_s = sid = next((e.get("id") for e in rep.get("crafts") or [] if e.get("type") == SKYR), None)
    crew = [s.get("id") for s in rep.get("soldiers") or [] if s.get("craft") == sid]
    gv = [q(c, {"cmd": "give_items", "item": it, "count": n, "base": CB}) for it, n in ((TC, 1), (SH, AP))]
    off = [q(c, {"cmd": "craft_assign", "soldier_id": i, "craft_id": sid, "base": CB, "on": False}) for i in crew[:4]]
    v0 = V(c, x, CB, sid)
    stg = {"ClientBase SKY": sid, "crew": crew, "give_items": gv, "craft_assign off": off, "client V after the staging": v0}
    print(f"EVIDENCE hwp_load_8 (staging): {json.dumps(stg, sort_keys=True, default=str)}", flush=True)
    r.ev["staging"] = stg
    if not (r.cell("guard: a ClientBase SKYRANGER with >= 4 crew, stock given", sid is not None and len(crew) >= 4 and all(g.get("ok") for g in gv), stg)
            and r.cell("guard: craft_assign took 4 crew off (spaceAvailable >= 4)", all(o.get("seated") is False for o in off) and len(off) == 4
                       and (v0.get("spaceAvailable") or 0) >= 4 and v0.get("vehicles") == {}, stg)):
        return r.evidence()
    s0, st0, k0 = {g.name: sbe.stats3(g) for g in (h, c)}, cl.st(c, CB), cl.sky(c, sid, CB)
    mv = move(c, x, TC, 1, CB, sid)
    v1, d = V(c, x, CB, sid), cl.diff(st0, cl.st(c, CB))
    time.sleep(SETTLE)
    s1 = {g.name: sbe.stats3(g) for g in (h, c)}
    r.ev.update({"move": mv, "client V": v1, "client ST diff": d, "client SKYI unchanged": cl.sky(c, sid, CB) == k0,
                 "shared_stats before / 1 s after": [s0, s1]})
    r.evidence()
    r.cell("the client's own SKY V != {TC: 1} after its load", v1.get("vehicles") == {TC: 1} and v1.get("vehicleAmmo") == [AP], v1)
    r.cell("the client's ClientBase stores not TC -1 / shells -AP", d == {TC: -1, SH: -AP}, d)
    r.cell("shared_stats cmd / applyCount / failCount changed", s0 == s1, [s0, s1])


def finish(x, r):
    cl.finish(x, r)


def stock(x):
    """The SHARED boot's stock (guard): give_items TC 2, shells 2 x AP, TLC 1 on both (client first); ST and chkItems
    equal. Raises on a miss."""
    gv = {g.name: [q(g, {"cmd": "give_items", "item": it, "count": n, "base": HB}) for it, n in ((TC, 2), (SH, 2 * AP), (TLC, 1))]
          for g in (x.client, x.host)}
    eq, s = cl.timed(lambda: cl.st(x.host) == cl.st(x.client), W)
    chk = [q(g, {"cmd": "shared_checksum"}).get("chkItems") for g in (x.host, x.client)]
    x.setup = {"give_items": gv, "ST equal s": s, "chkItems": chk, "V": both_v(x)}
    if not (all(e.get("ok") for v in gv.values() for e in v) and eq and chk[0] == chk[1]):
        raise RuntimeError(f"SHARED boot stock: {json.dumps(x.setup, default=str)}")


def run_rows(x, rows, results, walls):
    for rid, fn in rows:
        r, t1 = Row(rid, x), time.time()
        if getattr(x, "setup", None):
            r.ev["stock"] = {"chkItems": x.setup["chkItems"], "V": x.setup["V"]}
        try:
            fn(x, r)
        except Exception as e:
            r.cell(f"guard: {rid} exception", False, sbe.short(e))
        for g in (x.host, x.client):  # a stopped row leaves no screen behind (a re-copy in flight is waited out first)
            before = stack(g)
            if not cl.is_dead(before) and (before or [""])[-1] != GEO:
                if any("CoopState" in e or "LoadGameState" in e for e in before) and x.base == HB:
                    wait_until(lambda: cl.settled(stack(g)), cl.CONV)
                if stack(g)[-1:] != [GEO]:
                    rep = q(g, {"cmd": "close_screens"})
                    wait_until(lambda: stack(g)[-1:] == [GEO], 5.0)
                    r.cap[f"{g.name} cleanup"] = {"before": before, "close_screens": rep, "after": stack(g)}
        walls[rid] = round(time.time() - t1, 1)
        r.report(results)


def boot_shared(results, walls):
    t0, js, x = time.time(), None, None
    try:
        try:
            js = shared_fixture.bring_up(TAG_SHARED, PORTS_SHARED)
            x = sbe.X(js.host, js.client, js)
            sbe.setup(x)  # option OFF on both, seats differ, the SKYRANGER, the HostBase index (raises on a miss)
            stock(x)
            walls["boot " + TAG_SHARED] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails every row of this boot "boot" with ONE CAPTURE line
            return cl.boot_miss(TAG_SHARED, e, ROWS_SHARED, results, x)
        run_rows(x, (("hwp_load_1", lambda x, r: client_move(x, r, 1, "the client's tank load never reached the host")),
                     ("hwp_load_2",
                      lambda x, r: client_move(x, r, -1, "the client's tank unload never reached the host")),
                     ("hwp_load_3",
                      lambda x, r: host_move(x, r, 1, "the host's tank load reached the client only through a "
                                                      "world re-copy")),
                     ("hwp_load_4",
                      lambda x, r: host_move(x, r, -1, "the host's tank unload reached the client only through a "
                                                       "world re-copy")),
                     ("hwp_load_5", row_template_load), ("hwp_load_6", row_raw_command), ("hwp_load_7", finish)),
                 results, walls)
    finally:
        if js is not None:
            cl.down(TAG_SHARED, results, js.shutdown)


def boot_separate(results, walls):
    t0 = time.time()
    h = GameClient("host", LABELS_SEPARATE[0], make_user_dir(TAG_SEPARATE + "_host"))
    c = GameClient("client", LABELS_SEPARATE[1], make_user_dir(TAG_SEPARATE + "_client"))
    x = sbe.X(h, c, base=CB)
    try:
        try:
            h.spawn(), c.spawn(), h.connect(), c.connect()
            session.new_campaign(h, c, port=LOBBY_SEPARATE, campaign_mode="coop")
            geo.wait_both_ready(h, c)
            x.seats = {g.name: q(g, {"cmd": "get_coop"}).get("localSeat") for g in (h, c)}
            walls["boot " + TAG_SEPARATE] = round(time.time() - t0, 1)
        except Exception as e:  # a boot miss fails hwp_load_8 "boot" with ONE CAPTURE line
            return cl.boot_miss(TAG_SEPARATE, e, ROWS_SEPARATE, results, x)
        run_rows(x, (("hwp_load_8", row_separate_stays_local),), results, walls)
    finally:
        cl.down(TAG_SEPARATE, results, lambda: shutdown_clients(h, c))


def main():
    t0, results, walls = time.time(), {}, {}
    boot_shared(results, walls)
    boot_separate(results, walls)
    failed = [rid for rid in ORDER if not results.get(rid)]
    downs = sorted(k for k, v in results.items() if k.startswith("shutdown") and not v)
    print(f"\ntest_shared_hwp_loads: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed + downs}) "
          f"walls {json.dumps(walls)} in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed or downs else 0


if __name__ == "__main__":
    sys.exit(main())
