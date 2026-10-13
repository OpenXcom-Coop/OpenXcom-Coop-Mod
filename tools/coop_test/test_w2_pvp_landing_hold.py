"""W2-H38 - test_w2_pvp_landing_hold.py: in a gm3 PvP campaign the X-COM player's "Waiting for <host>" box (CoopState(3)) stays from
its YES on the landing prompt until its borrowed battle starts. The host's routine save-progress reply does not close it, the landing
prompt is not pushed a second time, the X-COM player's globe never becomes its top screen in between, and no position snapshot of that
globe reaches the alien host while the host borrows the X-COM world.

Spec: docs rewrite/prompts/w2h38_borrow_hold_pop.md, section (f) (owner D250, O1 (a); QC-4 (a), VL-C-1; QH37-5 (a); QH38-1..6 (a);
F14834, F14846). TASK 0: docs rewrite/w2h38-task0/sa/CONSTANTS.md (red premise boots a / b, green premise boots c / d with E1 only, 2/2
each; the hold's title "Waiting for HostPlayer" / "Disconnect" is EVIDENCE, never asserted).

Boot L: gm3 (the HOST plays the aliens), lobby key 48046, dirs w2h38_l_host / w2h38_l_client. Bring-up: PF.start_pvp_campaign
(alien_player="host"); HOST0 / CLIENT0 (G3C1's bring_up, copied with the key as a parameter); preconditions gamemode 3 on both, host
noBases true, client noBases false, the client's real base X, its non-coop Skyranger SKY, >= 2 soldiers; geo.slow_clock; crash baseline.
Staging: G3C1.stage_landing (the landing prompt on the client). A bring-up or staging miss is a FIXTURE-STOP: ONE "CAPTURE L:" line (or
G3C1's "CAPTURE C:" line) and every cell FAILs "boot".
Row H1 (one PASS / FAIL line per cell, one EVIDENCE line, one ROW line; a cell whose precondition was never reached FAILs "blocked"):
  the client's log cursor; client set_seed 1 + confirm_landing; every 0.1 s until both battle_state.inBattle (<= 60 s) one sample
  (client coop_dialog_info, its stack, the host's pvpBorrow.borrowed; F15127); session.briefings_to_battlescape; H1-common; the client
  log's "CLIENT phase Active" line (<= 5 s); the screen record ([coop-ui] lines after the cursor; WIN = the events strictly between the
  hand-off line HAND and the first BattlescapeState push after it, ENTRY); both pvpBorrow records.
  H1-entry  both inBattle, the spine, the host's borrow record, the client's held record, HAND / ENTRY / ACTIVE, >= 2 post-borrow samples.
  H1-hold   every pre-entry sample's top is CoopState with code 3; WIN ends with its only CoopState pop, at depth 1 (the entry's unwind).
  H1-prompt WIN pushes no ConfirmLandingState and no sample's client stack holds one.
  H1-top    no event in WIN but its last has depth 1 (the client's GeoscapeState never on top between HAND and ENTRY).
  H1-snap   host pvpBorrow.positionsSkipped (W2-H37's count, absent = 0) == 0.
  H1-common desyncSeen false on both, 0 new crash files since the confirm, hash_now full EQUAL. No battle end, no debriefing OK.
RED (R1, the unchanged product): 2/6 - FAIL H1-hold, H1-prompt, H1-top, H1-snap; PASS H1-entry, H1-common. GREEN (G1): 6/6.

WV-D95 / WV-D99 / WV-D100: ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_w2_pvp_landing_hold.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import test_w2_battle_end_separate as BES  # noqa: E402
import test_d250_campaign_battle_gm3 as G3C1  # noqa: E402

KEY = "48046"
SEED_L = 1                    # set on the X-COM CLIENT right before its confirm_landing (as G3C1 and W2-H37)
SQUAD = 2
POLL_S = 0.1
BOTH_IN_S = 60
LOG_S = 5
HAND = "[coop-pvp] client: landing handed to the alien host"
OFFER = "[coop-handshake] battle_offer accepted"
ACTIVE = "[coop-handshake] CLIENT phase Active"
ALL_CELLS = ["H1-entry", "H1-hold", "H1-prompt", "H1-top", "H1-snap", "H1-common"]


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


def capture_boot(err, host, client):
    cap = {}
    for gc in (host, client):
        try:
            bs = battle_state(gc)
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": G3C1.stack(gc), "battle": {k: bs.get(k) for k in ("inBattle", "phase", "side", "turn")},
                            "event_state": {k: v for k, v in event_state(gc).items() if k in ("phase", "desyncSeen", "battleEnd")},
                            "coop_dialog_info": gc.cmd({"cmd": "coop_dialog_info"}), "get_coop": gc.cmd({"cmd": "get_coop"}),
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE L: (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)


def common(host, client, crash0):
    """(ok, detail): desyncSeen false on both, 0 new crash files since crash0, every hash bucket EQUAL."""
    eh, ec = event_state(host), event_state(client)
    new = sorted(G3C1.crash_set() - crash0)
    bad = []
    if eh.get("desyncSeen") is not False or ec.get("desyncSeen") is not False:
        bad.append(f"desyncSeen host {eh.get('desyncSeen')!r} client {ec.get('desyncSeen')!r} (want false on both)")
    if new:
        bad.append(f"{len(new)} new crash file(s) since the confirm (first {os.path.basename(new[0])})")
    try:
        session.assert_hash_clean(host, client, full=True)
    except Exception as e:  # noqa: BLE001
        bad.append(f"hash_now full: {str(e)[:400]}")
    return not bad, "; ".join(bad) or "desyncSeen false on both, 0 new crash files, hash_now full EQUAL"


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
    return client0, xb


def sample(host, client, t_c):
    """H1's monitor sample: the client's coop_dialog_info, then its stack (top; entered = a BattlescapeState in it), then the host's
    pvpBorrow.borrowed. The dialog is read first so a sample never pairs a pre-entry stack with a post-entry dialog (F15127)."""
    dlg = client.cmd({"cmd": "coop_dialog_info"})
    stk = G3C1.stack(client)
    hb = (G3C1.coop(host).get("pvpBorrow") or {}).get("borrowed")
    s = {"t": round(time.time() - t_c, 2), "top": stk[-1] if stk else None, "entered": "BattlescapeState" in stk,
         "prompt": "ConfirmLandingState" in stk, "borrowed": hb}
    if not s["entered"]:
        s.update(code=dlg.get("code"), title=dlg.get("title"), backText=dlg.get("backText"))
    return s


def screen_record(client, cursor):
    """The client's [coop-ui] / HAND / OFFER / ACTIVE lines after the cursor, in order: (stamp, kind, (op, type, depth) or None)."""
    try:
        with open(os.path.join(client.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace", newline="") as f:
            f.seek(cursor)
            lines = f.read().splitlines()
    except OSError:
        lines = []
    out = []
    for ln in lines:
        stamp = ln[1:ln.index("]")] if ln.startswith("[") and "]" in ln else None
        i = ln.find("[coop-ui] ")
        if i >= 0:
            rest = ln[i + len("[coop-ui] "):]
            op = "push" if rest.startswith("push ") else "pop" if rest.startswith("pop ") else None
            j = rest.rfind(" depth=")
            if op and j > 0:
                body = rest[len(op) + 1:j].strip()
                out.append((stamp, "ui", (op, body.split("::")[-1], int(rest[j + len(" depth="):].strip()))))
            continue
        for kind, lit in (("HAND", HAND), ("OFFER", OFFER), ("ACTIVE", ACTIVE)):
            if lit in ln:
                out.append((stamp, kind, None))
    return out


def row_h1(host, client, client0, ev, phases, t0):
    sky = client0["sky"]
    crash0 = G3C1.crash_set()
    cursor = geo._log_cursor(client)
    sd, cl = client.cmd({"cmd": "set_seed", "seed": SEED_L}), client.cmd({"cmd": "confirm_landing"})
    t_c = time.time()
    if not sd.get("ok") or not cl.get("ok"):
        capture_boot(f"client set_seed {sd} / confirm_landing {cl}", host, client)
    ev["stacksAfterConfirm"] = [G3C1.stack(host), G3C1.stack(client)]
    mon, both = [], False
    while time.time() - t_c < BOTH_IN_S:
        mon.append(sample(host, client, t_c))
        if G3C1.in_battle(host) and G3C1.in_battle(client):
            both = True
            break
        time.sleep(POLL_S)
    secs = round(time.time() - t_c, 2)
    ev.update(bothInS=secs, inBattle=[G3C1.in_battle(host), G3C1.in_battle(client)],
              stacksAtBothIn=[G3C1.stack(host), G3C1.stack(client)])
    phases["bothIn"] = round(time.time() - t0, 1)
    sp_ok, sp_detail = False, "not run (not both inBattle)"
    if both:
        try:
            session.briefings_to_battlescape(host, client)
            sp_ok, sp_detail = True, "spine passed"
        except Exception as e:  # noqa: BLE001
            sp_detail = f"session.briefings_to_battlescape raised: {str(e)[:300]} (stacks {[G3C1.stack(host), G3C1.stack(client)]})"
    phases["spine"] = round(time.time() - t0, 1)
    c_ok, c_detail = common(host, client, crash0)
    phases["common"] = round(time.time() - t0, 1)

    def has_active():
        return any(k == "ACTIVE" for _s, k, _e in screen_record(client, cursor))
    BES.wait_until(has_active, LOG_S)
    rec = screen_record(client, cursor)
    phases["record"] = round(time.time() - t0, 1)
    hp, cp = G3C1.coop(host).get("pvpBorrow") or {}, G3C1.coop(client).get("pvpBorrow") or {}
    hand = next((i for i, r in enumerate(rec) if r[1] == "HAND"), None)
    entry = None if hand is None else next((i for i in range(hand + 1, len(rec)) if rec[i][1] == "ui"
                                            and rec[i][2][:2] == ("push", "BattlescapeState")), None)
    win = [] if entry is None else [r[2] for r in rec[hand + 1:entry] if r[1] == "ui"]
    stamp = lambda kind: next((r[0] for r in rec if r[1] == kind), None)  # noqa: E731
    pre = [s for s in mon if not s["entered"]]
    post = [s for s in pre if (s.get("borrowed") or 0) >= 1]
    ebad = [] if both else [f"inBattle host/client {ev['inBattle']} {secs} s after the confirm (want both <= {BOTH_IN_S} s)"]
    ebad += [] if sp_ok or not both else [sp_detail]
    ebad += [f"host pvpBorrow.{k} {hp.get(k)!r} (want {w!r})" for k, w in
             (("borrowed", 1), ("active", True), ("targetKind", "site"), ("targetMirror", True), ("craftType", sky["type"]),
              ("craftId", sky["id"])) if hp.get(k) != w]
    ebad += [f"client pvpBorrow.held {cp.get('held')!r} (want 1)"] if cp.get("held") != 1 else []
    ebad += [f"client pvpBorrow.released {cp.get('released')!r} (want absent or 0)"] if cp.get("released") not in (None, 0) else []
    ebad += [f"the screen record lacks {n}" for n, ok in (("HAND", hand is not None), ("an ENTRY after HAND", entry is not None),
                                                         ("ACTIVE", stamp("ACTIVE") is not None)) if not ok]
    ebad += [f"{len(post)} post-borrow sample(s) (want >= 2)"] if len(post) < 2 else []
    cell("H1-entry", not ebad, "; ".join(ebad) or f"both inBattle {secs} s, spine passed; host pvpBorrow borrowed 1, active, site "
         f"(mirror), {sky['type']}-{sky['id']}; client held 1; HAND / ENTRY / ACTIVE in the record; {len(post)} post-borrow samples")
    if entry is None or not pre:
        block(["H1-hold", "H1-prompt", "H1-top"], "no HAND -> ENTRY window in the client's screen record or no pre-entry sample")
    else:
        hbad = [f"t {s['t']}: top {s['top']} code {s.get('code')!r}" for s in pre if s["top"] != "CoopState" or s.get("code") != 3]
        pops = [e for e in win if e[:2] == ("pop", "CoopState")]
        last_ok = bool(win) and win[-1] == ("pop", "CoopState", 1) and len(pops) == 1
        cell("H1-hold", not hbad and last_ok,
             f"{len(hbad)}/{len(pre)} pre-entry samples without the hold on top" + (f" (first {hbad[0]})" if hbad else "")
             + f"; WIN's last event {win[-1] if win else None}, CoopState pops in WIN {len(pops)} (want the hold on top in every "
             f"pre-entry sample and WIN ending with its only CoopState pop at depth 1)")
        pushes = sum(1 for e in win if e[:2] == ("push", "ConfirmLandingState"))
        seen = [s["t"] for s in mon if s["prompt"]]
        cell("H1-prompt", pushes == 0 and not seen, f"{pushes} ConfirmLandingState push(es) in WIN, {len(seen)} sample(s) with "
             f"ConfirmLandingState in the client's stack {seen[:6]} (want 0 / 0)")
        early = [e for e in win[:-1] if e[2] == 1]
        cell("H1-top", not early, f"{len(early)} event(s) in WIN before its last at depth 1 {early[:3]} (want none: the client's "
             f"GeoscapeState never on top between the hand-off and the battle entry)")
    if hp.get("borrowed") != 1:
        block(["H1-snap"], "the host never borrowed the X-COM world (H1-entry)")
    else:
        sk = hp.get("positionsSkipped") or 0
        cell("H1-snap", sk == 0, f"host pvpBorrow.positionsSkipped {hp.get('positionsSkipped')!r} (want absent / 0: no snapshot of the "
             f"X-COM globe reached the host while it borrowed)")
    cell("H1-common", c_ok, c_detail)
    rle = []
    for s in mon:
        key = [s["top"], s.get("code"), s.get("borrowed")]
        if rle and rle[-1][2:] == key:
            rle[-1][1] = s["t"]
        else:
            rle.append([s["t"], s["t"]] + key)
    bh, bc = battle_state(host), battle_state(client)
    ev.update(samples=rle, preEntry=len(pre), postBorrow=len(post),
              hold=sorted({f"{s.get('title')!r} / {s.get('backText')!r}" for s in pre if s.get("code") == 3}),
              win=win, stamps={k: stamp(k) for k in ("HAND", "OFFER", "ACTIVE")}, entryStamp=rec[entry][0] if entry is not None else None,
              pvpBorrowHost=hp, pvpBorrowClient=cp, mapFingerprint=[bh.get("mapFingerprint"), bc.get("mapFingerprint")],
              turn=[bh.get("turn"), bc.get("turn")])


def run(host, client, phases, t0):
    ev = {}
    client0, xb = bring_up(host, client, KEY, ev)
    phases["bringUp"] = round(time.time() - t0, 1)
    try:
        G3C1.stage_landing(host, client, xb, client0, ev)
    except G3C1.FixtureMiss as e:
        raise FixtureMiss(f"G3C1.stage_landing: {e}")
    phases["staging"] = round(time.time() - t0, 1)
    row_h1(host, client, client0, ev, phases, t0)
    ev["phases"] = phases
    evidence("H1", ev)
    row_verdict("H1", ALL_CELLS)


def main():
    host = GameClient("host", None, make_user_dir("w2h38_l_host"))
    client = GameClient("client", None, make_user_dir("w2h38_l_client"))
    t0, phases = time.time(), {}
    try:
        run(host, client, phases, t0)
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
    print(f"\n==== W2-H38 gm3 landing hold: {len(RESULTS) - len(fails)}/{len(ALL_CELLS)} cells PASS, "
          f"wall {time.time() - t0:.1f} s ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(ALL_CELLS) else 2)


if __name__ == "__main__":
    main()
