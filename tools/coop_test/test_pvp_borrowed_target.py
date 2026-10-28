"""W2-H37 - test_pvp_borrowed_target.py: a gm3 PvP campaign battle keeps its target. While the alien host runs the battle in the
X-COM client's borrowed world (D250-U S-C1), the borrowed Skyranger keeps heading for the battle's mission site (the mirror H4 rebuilt)
and that site stays in the borrowed world from the X-COM player's YES through the battle start; a won battle's debriefing is the
mission site's on both machines, not a base defence.

Spec: docs rewrite/prompts/w2h37_borrowed_target_sweep.md, section (f) (owner D250, O1 (a); R-D250-SC1-1; VL-C-5; F14620, F14621;
QH37-1..6 (a)). TASK 0 pins: docs rewrite/w2h37-task0/sa/CONSTANTS.md (TITLE_WIN_H37 from boots c and d on the instrumented build
plus E1-E3, 2/2; the chain L1-L6 traced on boots a and b, 2/2).

Boot H: gm3 (the HOST plays the aliens), lobby key 48043, dirs w2h37_h_host / w2h37_h_client. Bring-up: PF.start_pvp_campaign
(alien_player="host"); HOST0 / CLIENT0 (G3C1's bring_up, copied with the key as a parameter); preconditions gamemode 3 on both, host
noBases true, client noBases false, the client's real base X, its non-coop Skyranger SKY, >= 2 soldiers; geo.slow_clock; crash baseline.
Staging: G3C1.stage_landing (research sync off, TOPIC, the squad of two, the host site at X + (0.35, 0.10), its client mirror,
craft_force, the landing prompt on the client). A bring-up or staging miss is a FIXTURE-STOP: ONE "CAPTURE H:" line (or G3C1's
"CAPTURE C:" line) and every remaining cell FAILs "boot".
Rows and cells (one PASS / FAIL line per cell, one EVIDENCE line and one ROW line per row; a row whose precondition was never reached
FAILs each of its cells "blocked: <why>"):
  H1 the borrowed battle keeps its target: client set_seed 1 + confirm_landing; the host's geo_state sampled every 0.1 s until both
     inBattle (<= 60 s); session.briefings_to_battlescape; a sample; assert_hash_clean(full=True); a sample. TARGET = the host's
     get_coop.pvpBorrow.targetCoopId after the spine. The sample's craft = SKY's type / id, coop false, in the base named X (coopBase /
     coopIcon false); absent = a pre-borrow sample.
     H1-entry (both inBattle, the spine, the host's pvpBorrow record, >= 2 post-borrow samples), H1-dest (every post-borrow sample:
     destKind "site", destId == the id of the coop site with coopId TARGET), H1-target (every post-borrow sample: exactly one coop site,
     coopId TARGET), H1-common (desyncSeen false on both, 0 new crash files since the confirm, hash_now full EQUAL).
  H2 the battle ends as the mission's: host G2F.kill_all faction 1; while the host has no DebriefingState: client END TURN +
     BES.close_host_nextturn(host); H2-end (the host's DebriefingState <= 60 s, displayOnly false; the client's display-only one
     <= 20 s), H2-title (host title == TITLE_WIN_H37, client == host), H2-common (desyncSeen false on both, 0 new crash files since H1).
     No debriefing OK is pressed: the boot shuts down after H2's EVIDENCE line (the return is D250-U S-C2's).
RED (R1, the unchanged product: the snapshot sweep deletes the mirror, F14620 / F14621): 4/7 - FAIL H1-dest, H1-target, H2-title.
GREEN (G1): 7/7.

WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_pvp_borrowed_target.py
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_battle_end_separate as BES  # noqa: E402
import test_campaign_battle_gm3 as G3C1  # noqa: E402
import test_campaign_battle_gm2 as G2F  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h37-task0/sa/CONSTANTS.md) -----
KEY = "48043"
SEED = 1                                  # set on the X-COM CLIENT right before its confirm_landing
TITLE_WIN_H37 = "Aliens defeated"         # T0-4 boots c and d (E1-E3 in), host and client, 2/2; the red shows "Base is saved"
SQUAD = 2
# ----- bounds -----
BOTH_IN_S = 60
DEBRIEF_S = 60
CLIENT_DEBRIEF_S = 20
POLL_S = 0.1
ALL_CELLS = ["H1-entry", "H1-dest", "H1-target", "H1-common", "H2-end", "H2-title", "H2-common"]


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, f"blocked: {why}")


def evidence(row, obj):
    print(f"EVIDENCE {row}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)


def row_verdict(row, names):
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)


def stack(gc):
    return session.states_stripped(gc)


def crash_set():
    return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))


def capture_boot(err, host, client):
    cap = {}
    for gc in (host, client):
        try:
            bs = battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")},
                            "event_state": {k: v for k, v in event_state(gc).items() if k in ("phase", "desyncSeen", "battleEnd")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": gc.cmd({"cmd": "get_coop"}),
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE H: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def common(host, client, crash0, hash_full):
    """(ok, detail): desyncSeen false on both, 0 new crash files since crash0, and (H1) every hash bucket EQUAL."""
    eh, ec = event_state(host), event_state(client)
    new = sorted(crash_set() - crash0)
    bad = []
    if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False:
        bad.append(f"desyncSeen host {eh.get('desyncSeen')!r} client {ec.get('desyncSeen')!r} (want false on both)")
    if new:
        bad.append(f"{len(new)} new crash file(s) (first {os.path.basename(new[0])})")
    if hash_full:
        try:
            session.assert_hash_clean(host, client, full=True)
        except Exception as e:  # noqa: BLE001
            bad.append(f"hash_now full: {str(e)[:400]}")
    return not bad, "; ".join(bad) or ("desyncSeen false on both, 0 new crash files" + (", hash_now full EQUAL" if hash_full else ""))


def bring_up(host, client, key, ev):
    """G3C1's bring_up (copied, the key as a parameter): spawn, the gm3 campaign (the HOST on the Alien team), HOST0 / CLIENT0,
    geo.slow_clock. Its C-gm values are preconditions here (a miss = FIXTURE-STOP)."""
    host.spawn(); host.connect(); client.spawn(); client.connect()
    try:
        gm = PF.start_pvp_campaign(host, client, key, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture_boot(f"PF.start_pvp_campaign: {e}", host, client)
    ch, cc = G3C1.coop(host), G3C1.coop(client)
    hg, cg = host.ok({"cmd": "geo_state"}), client.ok({"cmd": "geo_state"})
    xb = next((b for b in cg.get("bases", []) if not b.get("coopBase") and not b.get("coopIcon")), None)
    sky = next((c for c in (xb or {}).get("crafts", []) if "SKYRANGER" in c.get("type", "") and not c.get("coop")), None)
    sb = next((b for b in client.ok({"cmd": "get_soldiers"}).get("bases", []) if not b.get("coopBaseFlag")), None)
    sids = sorted(s["id"] for s in (sb or {}).get("soldiers", []))
    host0 = {"noBases": ch.get("noBases"), "funds": hg.get("funds"), "realBases": G3C1.real_bases(hg)}
    client0 = {"noBases": cc.get("noBases"), "funds": cg.get("funds"), "realBases": G3C1.real_bases(cg),
               "sky": sky and {"type": sky.get("type"), "id": sky.get("id")}, "soldiers": sids}
    ev.update(lobbyGamemode=gm, HOST0=host0, CLIENT0=client0)
    geo.slow_clock(host, client)
    if not (ch.get("gamemode") == 3 and cc.get("gamemode") == 3 and ch.get("noBases") is True and cc.get("noBases") is False):
        capture_boot(f"gamemode host {ch.get('gamemode')} client {cc.get('gamemode')} (want 3 / 3); noBases host {ch.get('noBases')!r} "
                     f"client {cc.get('noBases')!r} (want true / false)", host, client)
    if not xb or not sky or len(sids) < SQUAD:
        capture_boot(f"the client has no real base / Skyranger / {SQUAD} soldiers (base {xb and xb.get('name')}, sky {sky}, "
                     f"soldiers {sids})", host, client)
    return host0, client0, xb


def sample(host, xb_name, sky, t_c):
    """The monitor sample on the HOST's geo_state (spec (f))."""
    g = host.ok({"cmd": "geo_state"})
    craft = None
    for b in g.get("bases", []):
        if b.get("name") == xb_name and not b.get("coopBase") and not b.get("coopIcon"):
            craft = next((c for c in b.get("crafts", []) if c.get("type") == sky["type"] and c.get("id") == sky["id"]
                          and not c.get("coop")), craft)
    return {"t": round(time.time() - t_c, 2), "borrowed": craft is not None, "destKind": craft and craft.get("destKind"),
            "destId": craft and craft.get("destId"), "status": craft and craft.get("status"),
            "sites": [{"id": m.get("id"), "coopId": m.get("coopId")} for m in g.get("missionSites", []) if m.get("coop")]}


def client_mirror_coop_id(client, mirror_id):
    return next((m.get("coopId") for m in client.ok({"cmd": "geo_state"}).get("missionSites", [])
                 if m.get("coop") and (mirror_id is None or m.get("id") == mirror_id)), None)


def row_h1(host, client, xb, client0, ev, ctx):
    names = ["H1-entry", "H1-dest", "H1-target", "H1-common"]
    sky = client0["sky"]
    ev["clientMirrorCoopId"] = client_mirror_coop_id(client, ev.get("siteClient"))
    crash0 = crash_set()
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED}), client.cmd({"cmd": "confirm_landing"})
    t_c = time.time()
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_landing {cl}", host, client)
    ev["stacksAfterConfirm"] = [stack(host), stack(client)]
    mon, both = [], False
    while time.time() - t_c < BOTH_IN_S:
        mon.append(sample(host, xb["name"], sky, t_c))
        if G3C1.in_battle(host) and G3C1.in_battle(client):
            both = True
            break
        time.sleep(POLL_S)
    secs = round(time.time() - t_c, 2)
    ev.update(bothInS=secs, inBattle=[G3C1.in_battle(host), G3C1.in_battle(client)], stacksAtBothIn=[stack(host), stack(client)])
    sp_ok, sp_detail = False, "not run (not both inBattle)"
    if both:
        try:
            session.briefings_to_battlescape(host, client)
            sp_ok, sp_detail = True, "spine passed"
        except Exception as e:  # noqa: BLE001
            sp_detail = f"session.briefings_to_battlescape raised: {str(e)[:300]} (stacks {[stack(host), stack(client)]})"
    mon.append(sample(host, xb["name"], sky, t_c))
    hp, cp = G3C1.coop(host).get("pvpBorrow") or {}, G3C1.coop(client).get("pvpBorrow") or {}
    target = hp.get("targetCoopId")
    post = [m for m in mon if m["borrowed"]]
    n_pre_hash = len(post)
    c_ok, c_detail = common(host, client, crash0, hash_full=True)
    mon.append(sample(host, xb["name"], sky, t_c))
    post = [m for m in mon if m["borrowed"]]
    ebad = [] if both else [f"inBattle host/client {ev['inBattle']} {secs} s after the confirm (want both <= {BOTH_IN_S} s)"]
    ebad += [] if sp_ok or not both else [sp_detail]
    ebad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in
             (("borrowed", 1), ("targetKind", "site"), ("targetMirror", True), ("craftType", sky["type"]), ("craftId", sky["id"]))
             if hp.get(k) != w]
    if n_pre_hash < 2:
        ebad.append(f"{n_pre_hash} post-borrow sample(s) before the hash (want >= 2)")
    cell("H1-entry", not ebad, "; ".join(ebad) or f"both inBattle {secs} s, spine passed; host pvpBorrow borrowed 1, site target "
         f"{target} (mirror), {sky['type']}-{sky['id']}; {len(post)} post-borrow samples")
    if not post:
        block(["H1-dest", "H1-target"], "no post-borrow sample (the host never borrowed the X-COM world)")
    else:
        dbad = []
        for m in post:
            want = next((s["id"] for s in m["sites"] if s["coopId"] == target), None)
            if m["destKind"] != "site" or m["destId"] is None or m["destId"] != want:
                dbad.append(f"t {m['t']}: destKind {m['destKind']!r} destId {m['destId']} (want 'site' / {want})")
        cell("H1-dest", not dbad, (f"{len(dbad)}/{len(post)} post-borrow samples off target, first {dbad[0]}" if dbad else
                                   f"{len(post)}/{len(post)} post-borrow samples: destKind 'site', destId == the mirror of {target}"))
        tbad = [f"t {m['t']}: coop sites {m['sites']} (want exactly one, coopId {target})" for m in post
                if len(m["sites"]) != 1 or m["sites"][0]["coopId"] != target]
        cell("H1-target", not tbad, (f"{len(tbad)}/{len(post)} post-borrow samples without the target, first {tbad[0]}" if tbad else
                                     f"{len(post)}/{len(post)} post-borrow samples: exactly one coop site, coopId {target}"))
    cell("H1-common", c_ok, c_detail)
    bh, bc = battle_state(host), battle_state(client)
    seq = []
    for m in post:
        if not seq or seq[-1][0] != m["destKind"]:
            seq.append([m["destKind"], 0])
        seq[-1][1] += 1
    ev.update(target=target, pvpBorrowHost=hp, pvpBorrowClient=cp, samples=len(mon), postBorrow=len(post),
              firstPostBorrowT=post[0]["t"] if post else None, destKindSeq=seq, siteCounts=sorted({len(m["sites"]) for m in post}),
              firstPost=post[0] if post else None, lastPost=post[-1] if post else None,
              turn=[bh.get("turn"), bc.get("turn")], mapFingerprint=[bh.get("mapFingerprint"), bc.get("mapFingerprint")],
              clientMirrorCoopIdAfterSpine=client_mirror_coop_id(client, None))
    if not (both and sp_ok):
        ctx["blocked"] = "the battle never started on both machines (H1-entry)"
    return names


def row_h2(host, client, ctx, ev):
    names = ["H2-end", "H2-title", "H2-common"]
    if ctx["blocked"]:
        block(names, ctx["blocked"])
        return names
    crash0 = crash_set()
    ev["kills"] = G2F.kill_all(host, client, 1, ev, "kills")
    ev["stacksAfterKills"] = [stack(host), stack(client)]
    if not any("DebriefingState" in s for s in stack(host)):
        ev["endTurn"] = client.cmd({"cmd": "battle_action", "action": "end_turn_button"})
        ev["closeNext"] = BES.close_host_nextturn(host)
    hok, hsecs = BES.wait_until(lambda: "DebriefingState" in stack(host), DEBRIEF_S)
    cok, csecs = BES.wait_until(lambda: (lambda d: d.get("shown") is True and d.get("displayOnly") is True)(
        client.cmd({"cmd": "debrief_state"})), CLIENT_DEBRIEF_S) if hok else (False, 0)
    hd, cd = host.cmd({"cmd": "debrief_state"}), client.cmd({"cmd": "debrief_state"})
    bad = [] if hok else [f"no host DebriefingState within {DEBRIEF_S} s (stack {stack(host)})"]
    if hok and (hd.get("shown") is not True or hd.get("displayOnly") is not False):
        bad.append(f"host debrief_state shown {hd.get('shown')!r} displayOnly {hd.get('displayOnly')!r} (want true / false)")
    if hok and not cok:
        bad.append(f"no client display-only DebriefingState within {CLIENT_DEBRIEF_S} s (shown {cd.get('shown')!r} displayOnly "
                   f"{cd.get('displayOnly')!r}, stack {stack(client)})")
    cell("H2-end", not bad, "; ".join(bad) or f"host DebriefingState {hsecs} s (displayOnly false), client display-only {csecs} s")
    if not hok:
        block(["H2-title"], "no host DebriefingState (H2-end)")
    else:
        ht, ct = hd.get("title"), cd.get("title")
        tbad = [] if ht == TITLE_WIN_H37 else [f"host title {ht!r} (want {TITLE_WIN_H37!r})"]
        tbad += [] if ct == ht else [f"client title {ct!r} != host {ht!r}"]
        cell("H2-title", not tbad, "; ".join(tbad) or f"title {ht!r} on both")
    cell("H2-common", *common(host, client, crash0, hash_full=False))
    ev.update(hostDebrief=BES.debrief_view(hd), clientDebrief=BES.debrief_view(cd), stacks=[stack(host), stack(client)],
              debriefS=[hsecs, csecs], positionsSkipped=(G3C1.coop(host).get("pvpBorrow") or {}).get("positionsSkipped"))
    return names


def run(host, client):
    ctx = {"blocked": None}
    ev1 = {}
    host0, client0, xb = bring_up(host, client, KEY, ev1)
    try:
        G3C1.stage_landing(host, client, xb, client0, ev1)
    except G3C1.FixtureMiss as e:
        raise FixtureMiss(f"G3C1.stage_landing: {e}")
    names = row_h1(host, client, xb, client0, ev1, ctx)
    evidence("H1", ev1)
    row_verdict("H1", names)
    ev2 = {}
    names = row_h2(host, client, ctx, ev2)
    evidence("H2", ev2)
    row_verdict("H2", names)


def main():
    host = GameClient("host", None, make_user_dir("w2h37_h_host"))
    client = GameClient("client", None, make_user_dir("w2h37_h_client"))
    t0 = time.time()
    try:
        run(host, client)
    except FixtureMiss as e:
        block(ALL_CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        block(ALL_CELLS, f"error {type(e).__name__}: {str(e)[:200]}")
    finally:
        try:
            host.shutdown()
        finally:
            client.shutdown()
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== W2-H37 gm3 borrowed battle target: {len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
