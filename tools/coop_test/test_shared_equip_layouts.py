"""W2-H69 - test_shared_equip_layouts.py (EQL): in a SHARED co-op battle the second player's copy of the
soldiers' saved loadouts - each battle soldier's equipment layout, personal layout and personal-layout armor -
equals the host's from turn 1 (L-MGP1-1). Spec docs rewrite/prompts/w2h69_shared_equip_layouts.md (f); pins from
rewrite/w2h69-task0/sa/CONSTANTS.md (TASK 0, h69a-red); orchestrator rulings R-H69-0 (fix (a): the host's equip-end
signal carries every battle soldier's gear record and the second player adopts it at turn 1, SHARED only),
R-H69-2 (G-unchanged, below) and QH69-1 .. QH69-6 (a).

Today the host's pre-battle barrier runs vanilla's close (InventoryState::saveEquipmentLayout), which writes the
battle soldiers' layouts into the host's world only; the second player pops its screen without OK and its copy
stays empty until the post-battle world arrives (F19703; test_shared_landing red since W2-G1). A personal layout
the HOST saves on its own pre-battle screen has the same window (F19710).

Boot S (SHARED, one battle; rows L, P): shared_fixture.bring_up -> session.bring_up_shared_mixed_battle(js, OWNERS,
to_tactical=False) -> the client's shared_resync_stats.requests = R0 -> EQSH's spine (spine_both_briefings,
spine_units: H = squad[0] seat 0, C = squad[1] seat 1) -> staging while both briefings are up (H and C stripped,
then L1 to C and L2 to H by battle_give, client first) -> spine_open_screens -> row L's order: C's grenade picked
and placed STR_BELT MOVE_FROM -> MOVE_TO on the client's screen (one inv_move the host performs) -> row P's save:
the host's screen on H, the personal-save key on the HOST -> session.equip_both_ready -> the reads (turn 1 on both;
base 0 by name, the world_dump key; every equality polled every POLL_S up to LAYOUT_WAIT_S, then read once more).
  L  L-host (the host's C layout = the client's arrangement, its H layout = L2), L-equal (every soldier of base 0:
     the client's layout = the host's, stored order), L-moved (the client's C layout holds the grenade at MOVE_TO),
     L-sent / L-adopted (event_state.equip.gearRecords = 2 on the host / the client), L-noresync (the client's
     requests = R0), L-hash (drained within DRAIN_S, hash_now buckets equal, desyncSeen false on both).
  P  P-host (within ANSWER_WAIT_S the host's H personal = L2 with personalArmor = H's armor), P-equal (every soldier
     of base 0: the client's personal and personalArmor = the host's).
Boot P (SEPARATE; row G, D209: no SEPARATE adoption of host records): session.bring_up_separate_guest_battle with
a pre_landing snapshot -> turn 1 on both.
  G  G-wrote (the host's own squad layouts non-empty on the host), G-unchanged (R-H69-2: in a SEPARATE battle the
     client's world is the host's battle world and its own world is held in coopSepEntrySnapshot(), F19961 - so the
     client's battle world at turn 1 equals, per soldier id, the host's own-base snapshot taken in the same
     pre_landing), G-nosend / G-noadopt (gearRecords 0 or absent on the host / the client).

RED (today, 5 of 13): L-equal, L-moved, L-sent, L-adopted, P-equal. Each row prints ONE "EVIDENCE <row>:" line,
then one PASS / FAIL line per cell and its ROW verdict; every row runs after a failure; a precondition miss ends its
row (later cells "not reached"); a boot miss fails every row of that boot with ONE CAPTURE line. WV-D99 / WV-D100:
ONE run is the result, no skip; exit 0 only when every cell passes, else 2. WV-D95: run in the foreground to
completion.

Run:  python tools/coop_test/test_shared_equip_layouts.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import shared_fixture
from harness import GameClient, make_user_dir, shutdown_clients
from session import battle_state
from test_delta_core import both, short, diff_buckets
from test_delta_items import items_by_id
from test_client_items import strip_both
from test_prebattle_equip import (ANSWER_WAIT_S, stack, es, equip, turn, inv_view, view_brief, wait_until,
                                     goto_unit, drained, BELT, GRENADE_T)
from test_prebattle_equip_tools import (L1_GIVE, L2_GIVE, KEY_SETTLE_S, layouts, unit_sig, layout_sig, key,
                                           harness_keys)
from test_prebattle_equip_shared import (OWNERS, spine_both_briefings, spine_units, spine_open_screens,
                                            move_in_c)

TAG_S, TAG_P = "w2h69_s", "w2h69_p"   # user dirs s<slot>_w2h69_s_host / _client, s<slot>_w2h69_p_host / _client
PORTS_S = (49251, 49252, 49251)      # (host test label, client test label, the SHARED session key); W2-H69's keys
KEY_P = "49252"                      # boot P's SEPARATE session key; GameClient labels 49251 / 49252
MOVE_FROM, MOVE_TO = (0, 0), (1, 0)  # C's grenade on STR_BELT (EQSH EQ28s (b)); landed on both in 0.20 s at TASK 0
GEAR_RECORDS = 2                     # one gear record per battle soldier: the squad's H and C
LAYOUT_WAIT_S = 5.0                  # >= 3 x the slowest TASK 0 adoption (complete before equip_both_ready returned)
POLL_S = 0.2
DRAIN_S = 10.0
TURN_WAIT_S = 30.0                   # boot P: turn 1 on both after drive_both_to_tactical (TASK 0: 0.1 s)
CELLS = {"L": ("L-host", "L-equal", "L-moved", "L-sent", "L-adopted", "L-noresync", "L-hash"),
         "P": ("P-host", "P-equal"),
         "G": ("G-wrote", "G-unchanged", "G-nosend", "G-noadopt")}
results = {}


# ===================== reporting =====================


def cell(name, ok, msg=""):
    results[name] = bool(ok)
    print(f"PASS {name}" if ok else f"FAIL {name}: {msg}", flush=True)


def rest_not_reached(row, why):
    for c in CELLS[row]:
        if c not in results:
            cell(c, False, f"not reached - {why}")


def row_verdict(row):
    n = sum(1 for c in CELLS[row] if results.get(c))
    print(f"ROW {row}: {'PASS' if n == len(CELLS[row]) else 'FAIL'} ({n}/{len(CELLS[row])} cells)", flush=True)


def evidence(row, fields):
    print(f"EVIDENCE {row}: " + json.dumps(fields, sort_keys=True, default=str), flush=True)


def capture(boot, pair, e):
    rec = {"error": short(e, 600)}
    for g in pair:
        if g is None:
            continue
        try:
            rec[g.name] = {"stack": stack(g), "turn": turn(g), "equip": equip(g), "view": view_brief(inv_view(g))}
        except Exception as x:  # a dead instance
            rec[g.name] = short(x, 200)
    print(f"CAPTURE boot {boot}: " + json.dumps(rec, sort_keys=True, default=str), flush=True)


# ===================== probes =====================


def poll(pred):
    """`pred` every POLL_S up to LAYOUT_WAIT_S, then read once more. Returns (holds, seconds or None)."""
    got, dt = wait_until(pred, LAYOUT_WAIT_S, POLL_S)
    return (True, dt) if got else (bool(pred()), None)


def gear_of(gc, base=None):
    """soldier_layouts of `base` by name (default: this machine's first own base) -> (base name,
    {soldier id: [layout, personal, personalArmor]}), each layout in stored order."""
    req = {"cmd": "soldier_layouts"}
    if base is not None:
        req["base"] = base
    r = gc.cmd(req)
    if not r.get("ok"):
        raise AssertionError(f"soldier_layouts {base!r} on the {gc.name}: {r.get('error')}")
    return r.get("base"), {s["id"]: [s.get("layout") or [], s.get("personal") or [], s.get("personalArmor")]
                           for s in r.get("soldiers") or []}


def records(gc):
    return equip(gc).get("gearRecords")   # absent (None) before W2-H69's G1


def requests(gc):
    return gc.ok({"cmd": "shared_resync_stats"}).get("requests")


def armor_of(gc, uid):
    for u in battle_state(gc).get("units", []):
        if u.get("id") == uid:
            return u.get("armor")
    return None


def base0(gc):
    return gc.ok({"cmd": "geo_state"})["bases"][0]["name"]


def brief(g):
    """{id: [layout signature, personal signature, personalArmor]} for the evidence lines."""
    return {i: [layout_sig(v[0]), layout_sig(v[1]), v[2]] for i, v in g.items()}


# ===================== boot S =====================


def stage(host, client, ctx):
    """Both briefings up, client first (F607): H and C stripped, then L1 to C and L2 to H (S25: staged items)."""
    c, h = ctx["C"], ctx["H"]
    session.wait_seq_barrier(host, client)  # F21396: the host's first evs applied before staging (R-LT13-1)
    rec = {"stripped": {"C": strip_both(host, client, c), "H": strip_both(host, client, h)}, "ids": {}}
    for uid, give in ((c, L1_GIVE), (h, L2_GIVE)):
        for t, extra in give:
            req = {"cmd": "battle_give", "unit": uid, "item": t}
            req.update(extra)
            r = both(host, client, req, ("weaponId", "ammoId", "weaponSlot"))
            rec["ids"][f"{uid}:{t}"] = [r["weaponId"], r["ammoId"], r["weaponSlot"]]
    ih, ic = items_by_id(host), items_by_id(client)
    rec["sig"] = {"C": [unit_sig(ih, c), unit_sig(ic, c)], "H": [unit_sig(ih, h), unit_sig(ic, h)]}
    rec["diff"] = diff_buckets(host, client)
    ctx["keys"] = {n: v[0] for n, v in harness_keys(host).items()}
    rec["hostLiveKeys"] = layouts(host).get("keys")
    print(f"STAGE {json.dumps(rec, sort_keys=True, default=str)}", flush=True)
    for u in ("C", "H"):
        if not rec["sig"][u][0] or rec["sig"][u][0] != rec["sig"][u][1]:
            raise AssertionError(f"staging: {u} host {rec['sig'][u][0]} client {rec['sig'][u][1]} (want equal, non-empty)")
    if rec["diff"]:
        raise AssertionError(f"staging: hash_now buckets differ {rec['diff']}")
    if rec["hostLiveKeys"] != ctx["keys"]:
        raise AssertionError(f"FIXTURE - the host's live keys {rec['hostLiveKeys']} != its harness keys {ctx['keys']}")
    ctx["sigH"] = rec["sig"]["H"][0]


def row_l(host, client, ctx, name):
    c, h = ctx["C"], ctx["H"]
    ev = {"C": c, "H": h, "base0": name, "sigC": ctx["sigC"], "sigH": ctx["sigH"], "R0": ctx["R0"]}

    def lay_equal():
        _, hg = gear_of(host, name)
        _, cg = gear_of(client, name)
        return set(hg) == set(cg) and all(cg[i][0] == hg[i][0] for i in hg)

    def moved():
        _, cg = gear_of(client, name)
        return any(x.get("type") == GRENADE_T and x.get("slot") == BELT and (x.get("x"), x.get("y")) == MOVE_TO
                   for x in (cg.get(c) or [[]])[0])

    def host_ok():
        _, hg = gear_of(host, name)
        return c in hg and h in hg and layout_sig(hg[c][0]) == ctx["sigC"] and layout_sig(hg[h][0]) == ctx["sigH"]

    ok = {"L-host": poll(host_ok), "L-equal": poll(lay_equal), "L-moved": poll(moved),
          "L-sent": poll(lambda: records(host) == GEAR_RECORDS), "L-adopted": poll(lambda: records(client) == GEAR_RECORDS)}
    _, hg = gear_of(host, name)
    _, cg = gear_of(client, name)
    got, dd = wait_until(lambda: drained(host, client), DRAIN_S, 0.1)
    eh, ec = es(host), es(client)
    ev.update({"within": {k: v[1] for k, v in ok.items()}, "host": brief(hg), "client": brief(cg),
               "hostLayoutsRaw": {c: hg.get(c, [None])[0], h: hg.get(h, [None])[0]},
               "clientLayoutsRaw": {c: cg.get(c, [None])[0], h: cg.get(h, [None])[0]},
               "gearRecords": [records(host), records(client)], "requests": requests(client),
               "drainedWithin": dd if got else None, "diff": diff_buckets(host, client),
               "desyncSeen": [eh.get("desyncSeen"), ec.get("desyncSeen")], "turn": [turn(host), turn(client)]})
    evidence("L", ev)
    cell("L-host", ok["L-host"][0], f"the host's C layout {ev['host'].get(c)} / H {ev['host'].get(h)} (want C {ctx['sigC']}: "
         f"the client's arrangement, H L2 {ctx['sigH']})")
    diff = {i: [hg[i][0], cg.get(i, [None])[0]] for i in hg if cg.get(i, [None])[0] != hg[i][0]}
    cell("L-equal", ok["L-equal"][0], f"the client's layout differs from the host's for soldier(s) {sorted(diff)} "
         f"(host / client {json.dumps(diff, default=str)[:600]}) within {LAYOUT_WAIT_S} s of turn 1 (F19703)")
    cell("L-moved", ok["L-moved"][0], f"the client's C layout {ev['client'].get(c)} holds no {GRENADE_T} at {BELT} {MOVE_TO}")
    cell("L-sent", ok["L-sent"][0], f"the host's equip.gearRecords {ev['gearRecords'][0]!r} (want {GEAR_RECORDS})")
    cell("L-adopted", ok["L-adopted"][0], f"the client's equip.gearRecords {ev['gearRecords'][1]!r} (want {GEAR_RECORDS})")
    cell("L-noresync", ev["requests"] == ctx["R0"], f"the client's shared_resync_stats.requests {ctx['R0']} -> "
         f"{ev['requests']} (want unchanged: no restream)")
    cell("L-hash", got and not ev["diff"] and ev["desyncSeen"] == [False, False],
         f"drained {ev['drainedWithin']}, buckets differ {ev['diff']}, desyncSeen {ev['desyncSeen']} (want drained, "
         f"none, false on both)")


def row_p(host, client, ctx, name, p):
    h = ctx["H"]
    ev = {"H": h, "base0": name, "save": p}

    def pers_equal():
        _, hg = gear_of(host, name)
        _, cg = gear_of(client, name)
        return set(hg) == set(cg) and all(cg[i][1:] == hg[i][1:] for i in hg)

    pe = poll(pers_equal)
    _, hg = gear_of(host, name)
    _, cg = gear_of(client, name)
    diff = {i: [hg[i][1:], cg.get(i, [None, None, None])[1:]] for i in hg if cg.get(i, [None, None, None])[1:] != hg[i][1:]}
    ev.update({"equalWithin": pe[1], "personalDiff": diff})
    evidence("P", ev)
    hp = p["hostH"]
    cell("P-host", p.get("savedWithin") is not None and layout_sig(hp.get("personal")) == ctx["sigH"]
         and p.get("armorH") and hp.get("personalArmor") == p["armorH"],
         f"the host's H personal {layout_sig(hp.get('personal'))} armor {hp.get('personalArmor')!r} (want L2 "
         f"{ctx['sigH']} within {ANSWER_WAIT_S} s, armor {p.get('armorH')!r})")
    cell("P-equal", pe[0], f"the client's personal / personalArmor differ from the host's for soldier(s) {sorted(diff)} "
         f"(host / client {json.dumps(diff, default=str)[:600]}; F19710)")


def boot_s():
    js, host, client, ctx = None, None, None, {}
    try:
        js = shared_fixture.bring_up(TAG_S, PORTS_S)
        host, client = js.host, js.client
        _, _, ctx["squad"] = session.bring_up_shared_mixed_battle(js, OWNERS, to_tactical=False)
        ctx["R0"] = requests(client)
        spine_both_briefings(host, client, ctx)
        spine_units(host, client, ctx)
        stage(host, client, ctx)
        spine_open_screens(host, client, ctx)
    except Exception as e:
        capture("S", (host, client), e)
        for row in ("L", "P"):
            rest_not_reached(row, "boot (see CAPTURE boot S)")
            row_verdict(row)
        if js is not None:
            try:
                js.shutdown()
            except Exception as x:
                print(f"[w2h69] boot S shutdown: {short(x)}", flush=True)
        return
    try:
        c, h = ctx["C"], ctx["H"]
        pre = {"L": None, "P": None}
        nav, mv, p = [], {}, {"nav": []}
        try:
            if not goto_unit(client, c, [c], nav):
                pre["L"] = f"the client's screen never showed C {c} ({nav})"
            elif not move_in_c(host, client, ctx, c, MOVE_FROM, MOVE_TO, mv):
                pre["L"] = f"C's grenade never landed at {BELT} {MOVE_TO} on both ({mv})"
            ctx["sigC"] = unit_sig(items_by_id(host), c)
            print(f"MOVE C: {json.dumps({'nav': nav, 'move': mv, 'sigC': ctx['sigC']}, default=str)}", flush=True)
            if not goto_unit(host, h, [h], p["nav"]):
                pre["P"] = f"the host's screen never showed H {h} ({p['nav']})"
            else:
                time.sleep(KEY_SETTLE_S)
                p["press"] = key(host, ctx["keys"]["keyInvSavePersonalEquipment"])
                got, dt = wait_until(lambda: layout_sig(layouts(host, h).get("personal")) == ctx["sigH"],
                                     ANSWER_WAIT_S)
                p["savedWithin"] = dt if got else None
            p["hostH"] = {k: layouts(host, h).get(k) for k in ("personal", "personalArmor")}
            p["armorH"] = armor_of(host, h)
        except Exception as e:
            pre = {k: v or f"construction: {short(e, 400)}" for k, v in pre.items()}
        try:
            session.equip_both_ready(host, client)
            name = base0(host)
            if base0(client) != name:
                raise AssertionError(f"base 0 is {name!r} on the host, {base0(client)!r} on the client")
        except Exception as e:
            pre = {k: v or f"turn 1 / base 0: {short(e, 400)}" for k, v in pre.items()}
            name = None
        for row, fn, args in (("L", row_l, ()), ("P", row_p, (p,))):
            if pre[row]:
                evidence(row, {"precondition": pre[row], "stacks": [stack(host), stack(client)], "save": p})
                rest_not_reached(row, pre[row])
            else:
                try:
                    fn(host, client, ctx, name, *args)
                except Exception as e:
                    rest_not_reached(row, short(e, 400))
            row_verdict(row)
    finally:
        try:
            js.shutdown()
        except Exception as e:
            print(f"[w2h69] boot S shutdown: {short(e)}", flush=True)


# ===================== boot P (SEPARATE, row G) =====================


def row_g(host, client, host_squad, snap):
    hb, hg = gear_of(host)
    cb, cg = gear_of(client)
    sb, sg = snap["host"]
    wrote = {s: len((hg.get(s) or [[]])[0]) for s in host_squad}
    missing = sorted(i for i in sg if i not in cg)
    changed = {i: [sg[i], cg[i]] for i in sg if i in cg and cg[i] != sg[i]}
    rec = [records(host), records(client)]
    evidence("G", {"hostBase": hb, "hostSquad": host_squad, "hostSquadLayoutLens": wrote, "clientBase": cb,
                   "clientBattleWorld": brief(cg), "hostSnapshotBase": sb, "hostSnapshot": brief(sg),
                   "clientOwnSnapshot": [snap["client"][0], brief(snap["client"][1])], "snapshotRecords": snap["equip"],
                   "gearRecords": rec, "missing": missing, "changed": changed, "turn": [turn(host), turn(client)]})
    cell("G-wrote", bool(host_squad) and all(wrote.values()), f"the host's own squad layout lengths {wrote} (want "
         f"non-empty: the host's close wrote records it could send)")
    cell("G-unchanged", bool(sg) and cb == sb and not missing and not changed,
         f"the client's battle world {cb!r} vs the host's pre_landing snapshot {sb!r}: missing ids {missing}, changed "
         f"{json.dumps(changed, default=str)[:600]} (want equal per id: no SEPARATE adoption, D209)")
    cell("G-nosend", rec[0] in (0, None), f"the host's equip.gearRecords {rec[0]!r} (want 0 or absent: SEPARATE)")
    cell("G-noadopt", rec[1] in (0, None), f"the client's equip.gearRecords {rec[1]!r} (want 0 or absent: SEPARATE)")


def boot_p():
    host = GameClient("host", PORTS_S[0], make_user_dir(f"{TAG_P}_host"))
    client = GameClient("client", PORTS_S[1], make_user_dir(f"{TAG_P}_client"))
    snap = {}
    try:
        try:
            host.spawn()
            client.spawn()
            host.connect()
            client.connect()

            def pre_landing(h, c):
                snap["host"] = gear_of(h)     # R-H69-2: the world the client's battle copy is built from
                snap["client"] = gear_of(c)   # its own base (held in coopSepEntrySnapshot() during the battle)
                snap["equip"] = [records(h), records(c)]

            host_squad, _guest = session.bring_up_separate_guest_battle(host, client, port=KEY_P,
                                                                        pre_landing=pre_landing)
            got, _ = wait_until(lambda: turn(host) == 1 and turn(client) == 1, TURN_WAIT_S, POLL_S)
            if not got or "host" not in snap:
                raise AssertionError(f"turn host {turn(host)} client {turn(client)} (want 1 on both), pre_landing "
                                     f"snapshot {'taken' if 'host' in snap else 'missing'}")
        except Exception as e:
            capture("P", (host, client), e)
            rest_not_reached("G", "boot (see CAPTURE boot P)")
            row_verdict("G")
            return
        try:
            row_g(host, client, host_squad, snap)
        except Exception as e:
            rest_not_reached("G", short(e, 400))
        row_verdict("G")
    finally:
        try:
            shutdown_clients(host, client)
        except Exception as e:
            print(f"[w2h69] boot P shutdown: {short(e)}", flush=True)


def main():
    t0 = time.time()
    boot_s()
    boot_p()
    cells = [c for row in ("L", "P", "G") for c in CELLS[row]]
    failed = [c for c in cells if not results.get(c)]
    print(f"\ntest_shared_equip_layouts: {len(cells) - len(failed)}/{len(cells)} cells passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
