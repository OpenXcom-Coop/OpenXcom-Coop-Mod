"""W2-A12b - test_w2_text_fidelity.py: each player reads its own language on the SHARED cannot-reequip list (F6780), the
SHARED geoscape alerts (F6783) and a SEPARATE partner's craft window (F6784) (AUD-A12, owner D226 (a)). Spec
rewrite/prompts/w2a12b_text_fidelity.md (f) + ORCHESTRATOR RULINGS (session 394eb5c7, R-A12b-T0-1); TASK 0 constants
rewrite/w2a12b-task0/CONSTANTS.md (F7747-F7758). The host stays en-US (its texts are the guards), the client runs
`language: fr` (German keeps "SKYRANGER", F7536); lobby ports 47348 / 47349 (F7526), control ports ephemeral.

Boot A (SHARED, shared_fixture.bring_up "w2a12ba"): G:A (G-lang) the client's own Skyranger reads "PATROUILLE", the
host's "PATROLLING". Rows in order, the battle last:
  A12b-1  arrival row (B-15): host buy STR_RIFLE x1; skip 6 game days (speed 5) to ItemsArrivingState on top of BOTH
          (the hit may be the client's); items_arriving_rows: clientRows == ["Fusil"] [RED], G:hostRows == ["Rifle"].
  A12b-2  rearm alert (B-12): host sells INTERCEPTOR-2's clips to 0, craft_force {craft_id 2, ammo 0, STR_REARMING};
          skip 180 game minutes (speed 4) to CraftErrorState on both; its Text captions: clientSentence == [FR_REARM]
          [RED], G:hostSentence == [EN_REARM]; then craft 2 STR_READY.
  A12b-3  cannot-reequip (F6780): test_w2_campaign_followups' boot-1 sells, battle (SEED_S), strip squad[0], autoEnd,
          loadGamePushes0, kill_unit_real {faction 1}, ending, procedure; CannotReequipState rows sorted (R-C-1):
          clientCraft == 3 x "MERCURE-1" [RED]; G:hostRows == HOST_ROWS (Rifle Clip 3, R-A12b-T0-1); G:clientItems ==
          the French names; G:qty the client's (item key, qty) == the host's.
Boot B (SEPARATE, session.new_campaign + geo.wait_both_ready):
  A12b-4  partner craft (F6784): host spawn_mission_site STR_ALIEN_TERROR at base + (0.35, 0.10), craft_force
          SKYRANGER-1 STR_OUT at base + (0.05, 0) to site:<id>, speed idx 0; the client's mirror Skyranger polled to
          STR_OUT (<= 10 s; landing comes at ~76 s): name == "MERCURE-1" and status (displayStatus) == "DESTINATION :
          SITE DE TERREUR-<id>" [RED]; G:coop true, G:mirrorStatus STR_OUT, G:hostOwn == "DESTINATION: TERROR
          SITE-<id>", G:clientOwn == "PATROUILLE".

RED (commit 1: the geo_state craft `name` probe + this file, product untouched; ONE run, exit 2): exactly the [RED]
cells fail (the client shows the host's "Rifle", English sentence, "SKYRANGER-1", "DESTINATION: TERROR SITE-<id>");
every G: cell passes. GREEN (commit 2): every cell passes. French text is written as escapes from the TASK 0 constants.
An EVIDENCE line precedes every verdict; every row runs after a failure; a precondition miss fails its row on a
`fixture` cell after a CAPTURE line, a boot miss fails its rows "boot" with ONE CAPTURE line (FIXTURE-STOP).
WV-D99 / WV-D100: one run, no skip path; exit 0 only when G:A and every row pass, else 2. WV-D95: foreground.

Run:  python tools/coop_test/test_w2_text_fidelity.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients
import geo
import session
import shared_fixture
import test_w2_battle_end_campaign as camp
import test_w2_battle_end_separate as b1
import test_w2_campaign_followups as fu
from test_w2_battle_end_campaign import stack, top, wait_until, short

FR = {"language": "fr"}
PORTS = {"A": "47348", "B": "47349"}   # F7526: the lobby ports TASK 0 used
# TASK 0 CONSTANTS (deployed standard\xcom1\Language fr.yml / en-US.yml, sha256 equal to bin\standard): the en values
# are rendered by the host, the fr values by the French client or composed by vanilla's tr(key).arg(...) rule.
FR_PATROLLING, EN_PATROLLING = "PATROUILLE", "PATROLLING"   # STR_PATROLLING fr :289 / en-US :287 (G-lang)
FR_RIFLE, EN_RIFLE = "Fusil", "Rifle"                        # STR_RIFLE fr :827 / en-US :825
CLIPS = ("STR_STINGRAY_MISSILES", "STR_CANNON_ROUNDS_X50")  # INTERCEPTOR-2's clips (craftWeapons.rul, TASK 0 (iii))
EN_REARM = "Not enough Stingray Missiles to rearm INTERCEPTOR-2 at HostBase"   # rendered on both (TASK 0 (iii))
FR_REARM = "Pas assez de Missile Stingray pour r\u00e9armer INTERCEPTEUR-2 \u00e0 HostBase"   # fr :206 :532 :567 :243
HOST_ROWS = [["Rifle Clip", "3", "SKYRANGER-1"], ["Rifle", "1", "SKYRANGER-1"],
             ["Grenade", "1", "SKYRANGER-1"]]               # the host's CannotReequipState rows (R-A12b-T0-1)
ITEMS = {"Rifle Clip": ("STR_RIFLE_CLIP", "Chargeur de Fusil"), "Rifle": ("STR_RIFLE", "Fusil"),
         "Grenade": ("STR_GRENADE", "Grenade")}             # en-US :826 / :825 / :839 -> key, fr :828 / :827 / :841
FR_CRAFT = "MERCURE-1"                            # STR_CRAFTNAME {0}-{1} (fr :243) with STR_SKYRANGER (fr :564)
FR_DEST = "DESTINATION : SITE DE TERREUR-{}"      # STR_DESTINATION_UC_ fr :293 with STR_TERROR_SITE fr :378
EN_DEST = "DESTINATION: TERROR SITE-{}"           # STR_DESTINATION_UC_ en-US :291 with STR_TERROR_SITE en-US :376
M1 = "the second player reads the host's arrival row (F6783)"
M2 = "the second player reads the host's alert text (F6783)"
M3 = "the second player's cannot-reequip list names the craft in the host's language (F6780)"
M4 = "the partner's craft window reads the owner's language (F6784)"
HOST_OWN = "the host keeps its own language"
EN_ROUTE_S, TOPS_S, STORES_S, SITE_S, PROBE_S = 30, 20, 30, 30, 10
SKIP = ("hit", "game_minutes", "timed_out", "dismissed")   # the skip_ingame_time fields an EVIDENCE line keeps
ORDER = ("G:A", "A12b-1", "A12b-2", "A12b-3", "A12b-4")


# ===================== probes =====================


def safe(fn):
    try:
        return fn()
    except Exception as e:
        return {"probeError": short(e)}


def crafts(gc, mirror):
    """The crafts (with their base name) of the real bases (mirror False) or the coop mirror bases (True), geo_state."""
    out = []
    for b in gc.ok({"cmd": "geo_state"}).get("bases") or []:
        if bool(b.get("coopBase") or b.get("coopIcon")) == mirror:
            out += [dict(c, base=b.get("name")) for c in b.get("crafts") or []]
    return out


def craft(gc, ctype, cid=None, mirror=False):
    return next((c for c in crafts(gc, mirror) if c.get("type") == ctype and cid in (None, c.get("id"))), {})


def captions(gc):
    """The top state's non-empty plain Text captions (TextButtons excluded), list_widgets."""
    return [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets") or []
            if str(w.get("type", "")).endswith("::Text") and w.get("text")]


def dump(gc):
    """The FIXTURE-STOP dump of one machine: stack, items_arriving_rows, list_widgets texts, followup_state rows and
    the geo_state crafts."""
    keys = ("base", "id", "type", "coop", "name", "status", "displayStatus")
    return {"stack": safe(lambda: stack(gc)),
            "items_arriving_rows": safe(lambda: gc.cmd({"cmd": "items_arriving_rows"})),
            "list_widgets": safe(lambda: [[str(w.get("type")).replace("class OpenXcom::", ""), w.get("text")]
                                          for w in gc.cmd({"cmd": "list_widgets"}).get("widgets") or []
                                          if w.get("text")]),
            "followup_state": safe(lambda: {k: v for k, v in gc.cmd({"cmd": "followup_state"}).items()
                                            if k in ("state", "isTop", "rows", "error")}),
            "crafts": safe(lambda: [{k: c.get(k) for k in keys} for mr in (False, True) for c in crafts(gc, mr)])}


def capture(label, err, m):
    dumps = json.dumps({gc.name: dump(gc) for gc in m}, sort_keys=True, default=str)
    print(f"CAPTURE {label} (missed: {err}): {dumps}", flush=True)


def miss(label, err, m):
    """FIXTURE-STOP: ONE CAPTURE line with both machines' dumps, then raise."""
    capture(label, err, m)
    raise camp.FixtureMiss(f"{label}: {err[:600]}")


def tops(m, cls, label, ev):
    """`cls` on top of BOTH machines (the skip's hit may be either machine's, R-A12b-T0-1)."""
    for gc in m:
        ok, secs = wait_until(lambda gc=gc: top(gc) == cls, TOPS_S, 0.1)
        ev.setdefault("tops", {})[gc.name] = [ok, secs]
        if not ok:
            miss(label, f"{gc.name} top {top(gc)} after {secs}s (want {cls})", m)


def drain(m):
    out = {gc.name: geo.drain_popups(gc)[0] for gc in m}
    geo.slow_clock(*m)
    return out


# ===================== verdicts =====================


def verdict(label, cells, results):
    """cells = [(name, got, want, note)]: ONE EVIDENCE line (every cell), then PASS / FAIL naming each failing cell."""
    print(f"EVIDENCE {label}: " + "; ".join(f"{n} {'ok' if g == w else 'BAD'} got={g!a} want={w!a}"
                                             for n, g, w, _ in cells), flush=True)
    bad = [c for c in cells if c[1] != c[2]]
    if bad:
        print(f"FAIL {label}: " + " | ".join(f"{n}: got {g!a}, want {w!a}" + (f" - {note}" if note else "")
                                             for n, g, w, note in bad), flush=True)
    else:
        print(f"PASS {label}", flush=True)
    results[label] = not bad


def run_row(rid, fn, results, walls, m, cleanup=None):
    """One row: its steps and cells (fn(ev)), its cleanup (always), an EVIDENCE context line, the verdict."""
    t0, ev = time.time(), {}
    try:
        cells = fn(ev)
    except camp.FixtureMiss as e:
        cells = [("fixture", short(e), "ok", "FIXTURE-STOP (CAPTURE above)")]
    except Exception as e:
        capture(rid, short(e), m)
        cells = [("run", short(e), "ok", "FIXTURE-STOP")]
    if cleanup:
        ev["cleanup"] = safe(cleanup)
    walls[rid] = ev["wall"] = round(time.time() - t0, 2)
    print(f"EVIDENCE {rid} context: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)
    verdict(rid, cells, results)


# ===================== Boot A rows (SHARED) =====================


def row_arrival(host, client, ev):
    m = (host, client)
    geo.slow_clock(host, client)
    ev["predrain"] = {gc.name: geo.drain_popups(gc)[0] for gc in m}
    buy = host.cmd({"cmd": "buy", "item": "STR_RIFLE", "count": 1})
    ev["buy"] = {k: buy.get(k) for k in ("ok", "error")}
    en_route = lambda gc: any(t.get("rule") == "STR_RIFLE" for b in gc.ok({"cmd": "geo_state"})["bases"]
                              for t in b.get("transfers") or [])
    for gc in m:
        ok, secs = wait_until(lambda gc=gc: en_route(gc), EN_ROUTE_S)
        ev.setdefault("enRoute", {})[gc.name] = [ok, secs]
        if not ok:
            miss("A12b-1 buy", f"no STR_RIFLE transfer on the {gc.name} after {secs}s ({ev['buy']})", m)
    ev["skip"] = {k: v for k, v in geo.skip_ingame_time(host, client, 60 * 24 * 6, speed_idx=5, real_timeout=220,
                                                        interest=geo.popup("ItemsArrivingState")).items() if k in SKIP}
    tops(m, "ItemsArrivingState", "A12b-1 arrival", ev)
    rows = ev["rows"] = {gc.name: gc.cmd({"cmd": "items_arriving_rows"}).get("rows") for gc in m}
    return [("clientRows", rows["client"], [FR_RIFLE], M1), ("G:hostRows", rows["host"], [EN_RIFLE], HOST_OWN)]


def row_rearm(host, client, ev):
    m = (host, client)
    stores = lambda gc: session._campaign_base0(gc).get("items") or {}
    stock = stores(host)
    ev["sells"] = [(c, stock[c], host.cmd({"cmd": "sell", "item": c, "count": stock[c]}).get("ok"))
                   for c in CLIPS if stock.get(c, 0) > 0]
    ok, secs = wait_until(lambda: all(stores(gc).get(c, 0) == 0 for gc in m for c in CLIPS), STORES_S)
    if not ok:
        miss("A12b-2 sells", f"clip stock not 0 on both after {secs}s ({ev['sells']})", m)
    cf = host.cmd({"cmd": "craft_force", "craft_id": 2, "ammo": 0, "status": "STR_REARMING"})
    ev["rearming"] = {k: cf.get(k) for k in ("ok", "status", "error")}
    if not cf.get("ok"):
        miss("A12b-2 craft_force", f"host craft_force INTERCEPTOR-2 STR_REARMING answered {cf}", m)
    ev["skip"] = {k: v for k, v in geo.skip_ingame_time(host, client, 180, speed_idx=4,
                                                        interest=geo.popup("CraftErrorState")).items() if k in SKIP}
    tops(m, "CraftErrorState", "A12b-2 alert", ev)
    cap = ev["captions"] = {gc.name: captions(gc) for gc in m}
    return [("clientSentence", cap["client"], [FR_REARM], M2), ("G:hostSentence", cap["host"], [EN_REARM], HOST_OWN)]


def row_reequip(js, ev):
    host, client = js.host, js.client
    m = (host, client)
    ctx = {"boot": "A12b-3"}
    stock = fu.base_items(host)
    ev["sells"] = [(t, stock[t], host.cmd({"cmd": "sell", "item": t, "count": stock[t]}).get("ok"))
                   for t in fu.LOADOUT_TYPES if stock.get(t, 0) > 0]
    ok, secs = wait_until(lambda: all(fu.base_items(gc).get(t, 0) == 0 for gc in m for t in fu.LOADOUT_TYPES), STORES_S)
    if not ok:
        miss("A12b-3 sells", f"loadout stock not 0 on both after {secs}s ({ev['sells']})", m)
    squad, uid = fu.battle(js, ctx, m)   # camp.capture (a CAPTURE line) + FixtureMiss on a miss
    rh, rc = b1.both(host, client, {"cmd": "battle_strip_unit", "unit": uid[squad[0]]})
    ev["squad"], ev["strip"] = squad, {"host": rh.get("deleted"), "client": rc.get("deleted")}
    if not (rh.get("ok") and rc.get("ok") and rh.get("deleted")
            and sorted(rh["deleted"]) == sorted(rc.get("deleted") or [])):
        camp.capture("A12b-3 strip", f"battle_strip_unit answered host {rh} client {rc}", m)
    ae = host.cmd({"cmd": "set_option", "name": "battleAutoEnd", "value": True})
    if ae.get("value") is not True:
        camp.capture("A12b-3 battleAutoEnd", f"host set_option battleAutoEnd answered {ae}", m)
    ctx["loadGamePushes0"] = camp.log_count(client, camp.LOADGAME_PUSH)   # R-A12b-T0-1 (the join-time push, F7752)
    k = host.cmd({"cmd": "battle_action", "action": "kill_unit_real", "faction": 1})
    if not k.get("ok") or sorted(k.get("killed") or []) != fu.HOSTILES:
        camp.capture("A12b-3 kill", f"kill_unit_real faction 1 answered {k} (want the 15 hostiles)", m)
    fu.ending(host, client, ctx, m)
    fu.procedure(js, ctx)
    hr, cr = ctx["host"]["rows"].get("CannotReequipState"), ctx["client"]["rows"].get("CannotReequipState")
    ev["rows"] = {"host": hr, "client": cr}
    ev["procedure"] = {"ending": ctx.get("ending"), "debOk": ctx["deb"]["ok"], "adopt": ctx.get("adopt"),
                       "clientChain": (ctx["client"].get("record") or {}).get("chain"),
                       "clientScreens": ctx["client"].get("screens"), "hostScreens": ctx["host"].get("screens"),
                       "zeroDisk": ctx.get("zeroDisk"), "loadGamePushes": ctx.get("loadGamePushes"),
                       "fatalVoteArmed": ctx.get("fatalVoteArmed")}
    if hr is None or cr is None:
        miss("A12b-3 rows", f"CannotReequipState rows not read on both machines (host {hr!r}, client {cr!r})", m)
    en_key = {en: v[0] for en, v in ITEMS.items()}
    fr_key = {v[1]: v[0] for v in ITEMS.values()}
    return [("clientCraft", [r[2] for r in sorted(cr)], [FR_CRAFT] * len(HOST_ROWS), M3),
            ("G:hostRows", sorted(hr), sorted(HOST_ROWS), "TASK 0's en-US rows (R-A12b-T0-1)"),
            ("G:clientItems", sorted(r[0] for r in cr), sorted(v[1] for v in ITEMS.values()), "the French item names"),
            ("G:qty", sorted((fr_key.get(r[0], r[0]), r[1]) for r in cr),
             sorted((en_key.get(r[0], r[0]), r[1]) for r in hr), "the client's (item key, qty) == the host's")]


# ===================== Boot B row (SEPARATE) =====================


def row_partner(host, client, ev):
    m = (host, client)
    b0, sky = session._campaign_base0(host), session._campaign_skyranger(host)
    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR", "deployment": "STR_TERROR_MISSION",
                    "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    sid = ev["siteId"] = site["site_id"]
    on_host = lambda: any(s.get("id") == sid for s in host.ok({"cmd": "geo_state"}).get("missionSites") or [])
    ok, secs = wait_until(on_host, SITE_S)
    if not ok:
        miss("A12b-4 site", f"mission site {sid} not on the host after {secs}s", m)
    cf = host.ok({"cmd": "craft_force", "craft_id": sky["id"], "status": "STR_OUT", "lon": b0["lon"] + 0.05,
                  "lat": b0["lat"], "dest": f"site:{sid}", "fuel": 999999, "lowFuel": False})
    sp = host.cmd({"cmd": "geo_set_speed", "idx": 0})
    ev["craft_force"] = {k: cf.get(k) for k in ("ok", "craft_id", "status", "displayStatus")}
    ev["geo_set_speed"] = {k: sp.get(k) for k in ("ok", "error")}
    ok, secs = wait_until(lambda: craft(client, "STR_SKYRANGER", mirror=True).get("status") == "STR_OUT", PROBE_S, 0.25)
    mirror = craft(client, "STR_SKYRANGER", mirror=True)
    own_h, own_c = craft(host, "STR_SKYRANGER", sky["id"]), craft(client, "STR_SKYRANGER")
    ev.update(mirrorOutS=[ok, secs], mirror=mirror, hostOwn=own_h, clientOwn=own_c,
              speed={gc.name: gc.cmd({"cmd": "geo_state"}).get("timeSpeedIndex") for gc in m},
              hostTop=top(host))
    return [("name", mirror.get("name"), FR_CRAFT, M4),
            ("status", mirror.get("displayStatus"), FR_DEST.format(sid), M4),
            ("G:coop", mirror.get("coop"), True, "the client's mirror of the host's Skyranger"),
            ("G:mirrorStatus", mirror.get("status"), "STR_OUT", f"polled {secs}s"),
            ("G:hostOwn", own_h.get("displayStatus"), EN_DEST.format(sid), HOST_OWN),
            ("G:clientOwn", own_c.get("displayStatus"), FR_PATROLLING, "the client's own Skyranger renders French")]


# ===================== boots =====================


def boot_a(results, walls):
    t0, js, crash0 = time.time(), None, session._crash_log_snapshot()
    rows = ("G:A", "A12b-1", "A12b-2", "A12b-3")
    try:
        try:
            js = shared_fixture.bring_up("w2a12ba", (0, 0, PORTS["A"]), client_options=FR)
        except Exception as e:
            print(f"CAPTURE A: boot miss {short(e, 800)} (bring_up shut both machines down)", flush=True)
            for rid in rows:
                verdict(rid, [("boot", short(e), "ok", "FIXTURE-STOP")], results)
            return
        host, client = js.host, js.client
        m = (host, client)
        walls["A bring-up"] = round(time.time() - t0, 2)
        sky = {gc.name: safe(lambda gc=gc: craft(gc, "STR_SKYRANGER", 1)) for gc in m}
        own = json.dumps({gc.name: safe(lambda gc=gc: crafts(gc, False)) for gc in m}, sort_keys=True, default=str)
        print(f"EVIDENCE boot A: walls={walls}; own crafts={own}", flush=True)
        verdict("G:A", [("G:lang", sky["client"].get("displayStatus"), FR_PATROLLING,
                         "the client's own Skyranger renders French (TASK 0 G-lang)"),
                        ("G:hostLang", sky["host"].get("displayStatus"), EN_PATROLLING, HOST_OWN)], results)
        run_row("A12b-1", lambda ev: row_arrival(host, client, ev), results, walls, m, cleanup=lambda: drain(m))
        run_row("A12b-2", lambda ev: row_rearm(host, client, ev), results, walls, m,
                cleanup=lambda: [host.cmd({"cmd": "craft_force", "craft_id": 2, "status": "STR_READY"}), drain(m)])
        run_row("A12b-3", lambda ev: row_reequip(js, ev), results, walls, m)
    except Exception as e:
        print(f"CAPTURE A: {short(e, 800)}", flush=True)
        for rid in rows:
            if rid not in results:
                verdict(rid, [("run", short(e), "ok", "FIXTURE-STOP")], results)
    finally:
        if js is not None:
            try:
                js.shutdown()
            except Exception as e:
                print(f"[w2a12b] shutdown A: {short(e)}", flush=True)
        walls["A"] = round(time.time() - t0, 2)
        crashes = sorted(session._crash_log_snapshot() - crash0)
        print(f"[w2a12b] boot A walls={walls} newCrashLogs={crashes}", flush=True)


def boot_b(results, walls):
    t0, crash0 = time.time(), session._crash_log_snapshot()
    host = GameClient("host", 0, make_user_dir("w2a12bb_host"))
    client = GameClient("client", 0, make_user_dir("w2a12bb_client", options=FR))
    m = (host, client)
    try:
        try:
            for step in (host.spawn, client.spawn, host.connect, client.connect):
                step()
            session.new_campaign(host, client, port=PORTS["B"])
            geo.wait_both_ready(host, client)
        except Exception as e:
            capture("B: boot miss", short(e, 800), m)
            verdict("A12b-4", [("boot", short(e), "ok", "FIXTURE-STOP")], results)
            return
        walls["B bring-up"] = round(time.time() - t0, 2)
        run_row("A12b-4", lambda ev: row_partner(host, client, ev), results, walls, m)
    finally:
        try:
            shutdown_clients(host, client)
        except Exception as e:
            print(f"[w2a12b] shutdown B: {short(e)}", flush=True)
        walls["B"] = round(time.time() - t0, 2)
        crashes = sorted(session._crash_log_snapshot() - crash0)
        print(f"[w2a12b] boot B walls={walls} newCrashLogs={crashes}", flush=True)


def main():
    t0, results, walls = time.time(), {}, {}
    boot_a(results, walls)
    boot_b(results, walls)
    failed = [k for k in ORDER if not results.get(k)]
    print(f"\ntest_w2_text_fidelity: {len(ORDER) - len(failed)}/{len(ORDER)} passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s (walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
