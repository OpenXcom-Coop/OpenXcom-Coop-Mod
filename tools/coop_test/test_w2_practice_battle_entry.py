"""W2-H21d S-2 (F8980 routed, F9198; spec rewrite/prompts/w2h21d_preview_battle_paths.md (f), QH21d-4 a, QH21d-5 a, ruling
R-H21d-S2-T0-1 a; TASK 0 rewrite/w2h21d-task0/s2/CONSTANTS.md): a SEPARATE second player whose practice screen (a Ufopaedia craft
preview, a base craft equipment screen) is open when the host's joint battle starts loses its own-world progress when the battle ends.
coopSepEntrySnapshot reads the practice battle as a started battle and skips the battle-entry snapshot (sepSnapshot 0); at its OK the
return loads the stale own-world blob and the pre-mission MARKER funds are lost (TASK 0: E1 2/2, E2 2/2 on the gated drive; the C28P-shape
control passes).
  Boot E1 GameClient 49536 / 49537, bring_up_separate_guest_battle(port "46974"), dirs w2h21ena_host / _client:
    H21d-E1 (named RED) G: setup (pre_mission_start) + MARKER = the client's funds + 1234567; pre_landing PV(client), non-vacuity (top
        BattlescapeState, isPreview true, inBattle true); the entry. G: the practice screen still open at the entry (CL: its top's pop
        after LABELS). RED 1: the client's battleEnd.sepSnapshot == 1 and CL holds SNAP (TASK 0: 0, absent). G: every hostile killed by
        the host (chains settled), END TURN both, NextTurnState, the host's DebriefingState; H0 = the host's host_copy_of_client fnv; G:
        the client's display-only DebriefingState; its OK through its follow-ups. RED 2: the client top GeoscapeState with no CoopState /
        LoadGameState, geo_state.funds == MARKER, inBattle false, sepReturn.ownLoaded 1 (TASK 0: funds == funds0). Within W the host
        copy's fnv != H0, its dump has no `battleGame:` and no `inBattlescape: true` line; the host's OK + drain -> [GeoscapeState]; the
        client zero-disk.
  Boot E2 49538 / 49539, port "46975", dirs w2h21enb_host / _client:
    H21d-E2 (named RED) as E1 with the client's P4 (open_craft_equipment, craft_inventory; non-vacuity top InventoryState over
        CraftEquipmentState, inBattle true). R-H21d-S2-T0-1 (a): the fixture's drive_both_to_tactical OKs any top InventoryState and
        closed the practice inventory before the battle blob landed (F9535), so this row's drive first waits <= W for the client's
        battle_state.phase "Active" (its entry ran), then runs the fixture's own drive.
W = 10 s at 0.25 s polls; the host's debriefing 60 s, the client's 20 s. CL = the client's openxcom.log from the size noted at
pre_landing. A boot / G cell miss ends the row (later cells "not reached", one CAPTURE line); RED 1 does not end it. EVIDENCE before each
verdict; a failed row prints ONE CAPTURE line; every row runs after a failure; ONE run (WV-D95); exit 0 iff every row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402
import test_w2_battle_end_separate as be  # noqa: E402  (main-guarded: chain_settled, end_turn_both, close_host_nextturn, ...)
import test_w2_client_research as cr  # noqa: E402  (main-guarded: read_key)
import test_w2_preview_restream as pr  # noqa: E402  (main-guarded: pv, alive, log_*, crash_*, Row)
from harness import GameClient, make_user_dir  # noqa: E402
from session import battle_state  # noqa: E402

W, HOST_DEB_S, CLIENT_DEB_S = 10.0, 60, 20
GEO, BS, INV, CES = "GeoscapeState", "BattlescapeState", "InventoryState", "CraftEquipmentState"
SNAP = "[coop-debrief] client: SEPARATE battle-entry own-world snapshot taken"
LABELS = "mission labels applied from battle_offer"
POP = "pop  class OpenXcom::"
KEYS = ("[coop-debrief]", "[coop-ui]", "battle_offer", LABELS)
RED = "named red: TASK 0 2/2 sepSnapshot 0, no SNAP line, funds after the return == funds0 (the MARKER lost)"
q, stack, short, wait_until = pr.q, pr.stack, pr.short, pr.wait_until


class Stop(Exception):
    pass


class X:
    def __init__(self, tag, port):
        self.tag, self.port, self.host, self.client, self.keys = tag, port, None, None, None
        self.n_cl, self.top, self.marker, self.copy_head, self.crash0 = 0, None, None, [], set()


def msg(lines):
    return [ln.split("\t")[-1][:220] for ln in lines]


def coop(gc, *keys):
    c = q(gc, {"cmd": "get_coop"})
    return {k: c.get(k) for k in keys}


def dump(gc):
    if gc is None or not pr.alive(gc):
        return "<dead or absent>"
    bs = q(gc, {"cmd": "battle_state"})
    rec = be.record(gc)
    return {"stack": stack(gc), "get_coop": coop(gc, "localSeat", "lobbyMode", "inBattle", "coopDialog", "insideCoopBase"),
            "world_state": {k: v for k, v in q(gc, {"cmd": "world_state"}).items() if k in ("has_battle", "error")},
            "battle_state": {k: bs.get(k) for k in ("inBattle", "isPreview", "phase", "turn", "error")},
            "battleEnd": {k: rec.get(k) for k in ("sepSnapshot", "sepReturn", "debriefOkBranch")}}


def capture(r, x):
    if r.cap:
        return
    cl = msg(pr.log_lines(x.client, x.n_cl)) if x.client is not None else []
    r.cap.update({"CL": [ln for ln in cl if any(k in ln for k in KEYS)][-30:], "CRASH": pr.crash_info(x.crash0),
                  "host log": msg(pr.log_lines(x.host)[-20:]) if x.host is not None else [],
                  "host": dump(x.host), "client": dump(x.client), "host copy battle head": x.copy_head})


def host_copy(host):
    """the host's copy of the client's world: its fnv, then dump_coop_file on the HOST -> host.user_dir/xcom1/<key>"""
    info = q(host, {"cmd": "coop_file_info", "role": "host_copy_of_client"})
    key = info.get("key")
    out = {"key": key, "fnv": info.get("fnv1a64")}
    path = os.path.join(host.user_dir, "xcom1", key or "?")
    if key and os.path.exists(path):
        os.remove(path)
    out["dump"] = q(host, {"cmd": "dump_coop_file", "key": key}).get("ok") if key else None
    if not os.path.exists(path):
        return dict(out, error="no dump file"), []
    with open(path, "rb") as f:
        lines = f.read().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    bg = [i for i, ln in enumerate(lines) if ln.strip() == "battleGame:"]
    out.update({"lines": len(lines), "battleGame": [i + 1 for i in bg],
                "inBattlescape true": [i + 1 for i, ln in enumerate(lines) if ln.strip() == "inBattlescape: true"]})
    return out, (lines[bg[0]:bg[0] + 30] if bg else [])


def practice(r, x, kind):
    """pre_landing: P1 = W2-H21c's PV(client); P4 = the client's own base's first craft, its inventory. The non-vacuity cell."""
    c = x.client
    r.ev["pre_landing stacks"] = {"host": stack(x.host), "client": stack(c)}
    if kind == "P1":
        ok, r.ev["PV(client)"] = pr.pv(c, x.keys)
        x.top = BS
    else:
        a = q(c, {"cmd": "open_craft_equipment"})
        b = wait_until(lambda: CES in stack(c), W) and q(c, {"cmd": "craft_inventory"})
        ok = bool(a.get("ok") and b and b.get("opened") and wait_until(lambda: pr.on_top(c, INV), W))
        r.ev["P4(client)"], x.top = {"open_craft_equipment": a, "craft_inventory": b}, INV
    pre, ib = q(c, {"cmd": "battle_state"}).get("isPreview"), coop(c, "inBattle")["inBattle"]
    r.ev["non-vacuity"] = nv = {"stack": stack(c), "isPreview": pre, "inBattle": ib}
    good = ok and pr.on_top(c, x.top) and ib is True and (pre is True if kind == "P1" else CES in nv["stack"])
    what = "BattlescapeState, isPreview true" if kind == "P1" else "InventoryState over CraftEquipmentState"
    if not r.cell(f"G: non-vacuity: the client's {kind} open (top {what}, inBattle true)", good, nv):
        raise Stop("non-vacuity")
    x.n_cl = pr.log_size(c)


def gated(r, orig):
    """R-H21d-S2-T0-1 (a): wait <= W for the client's battle_state.phase "Active" (its entry ran), then the fixture's own drive"""
    def drive(h, c, *a, **k):
        t = time.time()
        ok = wait_until(lambda: q(c, {"cmd": "battle_state"}).get("phase") == "Active", W)
        r.ev["gate"] = {"active": bool(ok), "s": round(time.time() - t, 2)}
        return orig(h, c, *a, **k)
    return drive


def entry_row(r, x, kind):
    h, c = x.host, x.client

    def marker(hh, cc):
        su = {gc.name: [stack(gc), coop(gc, "localSeat")["localSeat"], q(gc, {"cmd": "world_state"}).get("has_battle")] for gc in (hh, cc)}
        su["host lobbyMode"], su["client insideCoopBase"] = coop(hh, "lobbyMode")["lobbyMode"], coop(cc, "insideCoopBase")["insideCoopBase"]
        r.ev["setup"] = su
        if not r.cell("G: setup (client [GeoscapeState] seat 1, host seat 0, has_battle false both, host lobbyMode 1, client outside "
                      "a coop base)", su["client"] == [[GEO], 1, False] and su["host"][1:] == [0, False]
                      and su["host lobbyMode"] == 1 and su["client insideCoopBase"] is False, su):
            raise Stop("setup")
        f0 = int(q(cc, {"cmd": "geo_state"}).get("funds"))
        x.marker = f0 + be.MARKER_DELTA
        s = q(cc, {"cmd": "set_funds", "value": x.marker})
        r.ev["marker"] = {"funds0": f0, "MARKER": x.marker, "set_funds": s.get("ok")}
        if not r.cell("G: MARKER set", s.get("ok") and q(cc, {"cmd": "geo_state"}).get("funds") == x.marker, r.ev["marker"]):
            raise Stop("marker")

    orig = session.drive_both_to_tactical
    if kind == "P4":
        session.drive_both_to_tactical = gated(r, orig)
    try:
        session.bring_up_separate_guest_battle(h, c, port=x.port, pre_mission_start=marker,
                                               pre_landing=lambda hh, cc: practice(r, x, kind))
    except Stop:
        return capture(r, x)
    except Exception as e:
        r.cell("G: the entry (bring_up_separate_guest_battle to both tactical)", False, short(e, 600))
        return capture(r, x)
    finally:
        session.drive_both_to_tactical = orig
    cl = msg(pr.log_lines(c, x.n_cl))
    i_lab = next((i for i, ln in enumerate(cl) if LABELS in ln), None)
    i_pop = next((i for i, ln in enumerate(cl) if POP + x.top in ln), None)
    r.ev["entry CL"] = [ln for ln in cl if any(k in ln for k in KEYS)][:12]
    if not r.cell(f"G: the practice screen still open at the entry (CL: pop {x.top} after '{LABELS}')",
                  i_lab is not None and i_pop is not None and i_pop > i_lab, {"labels at": i_lab, "pop at": i_pop}):
        return capture(r, x)
    sep_snap, snap = be.record(c).get("sepSnapshot"), any(SNAP in ln for ln in cl)
    r.ev["RED 1"] = red1 = {"sepSnapshot": sep_snap, "SNAP in CL": snap}
    r.cell("RED 1: the client's battleEnd.sepSnapshot == 1 and CL holds SNAP", sep_snap == 1 and snap, red1)
    hostiles = [u["id"] for u in battle_state(h).get("units", []) if u.get("faction") == 1 and not u.get("isOut")]
    settled = []
    for uid in hostiles:
        h.cmd({"cmd": "battle_action", "action": "kill_unit_real", "unit": uid})
        settled.append(be.chain_settled(h, c, stable=1.0, timeout=45)[0])
    live = [u["id"] for u in battle_state(h).get("units", []) if u.get("faction") == 1 and not u.get("isOut")]
    be.end_turn_both(h, c)
    r.ev["nextturn"] = be.close_host_nextturn(h)
    deb = wait_until(lambda: "DebriefingState" in stack(h), HOST_DEB_S)
    r.ev["ending"] = {"hostiles": len(hostiles), "settled": settled.count(True), "live after": live, "host stack": stack(h)}
    if not r.cell(f"G: every hostile killed (chains settled), the host's DebriefingState within {HOST_DEB_S} s",
                  deb and hostiles and not live and all(settled), r.ev["ending"]):
        return capture(r, x)
    r.ev["H0"] = h0 = be.coop_fnv(h, "host_copy_of_client")[0]
    shown = lambda d: d.get("shown") is True and d.get("onTop") is True and d.get("displayOnly") is True  # noqa: E731
    if not r.cell(f"G: the client's display-only DebriefingState within {CLIENT_DEB_S} s",
                  wait_until(lambda: shown(q(c, {"cmd": "debrief_state"})), CLIENT_DEB_S), stack(c)):
        return capture(r, x)
    ctx = {}
    ok1, ok, _secs = be.client_ok_through_followups(c, ctx, "ret")
    sep = be.record(c).get("sepReturn") or {}
    r.ev["RED 2"] = red2 = {"ok": ok1, "geo_clean": be.geo_clean(c), "stack": stack(c), "funds": q(c, {"cmd": "geo_state"}).get("funds"),
                            "MARKER": x.marker, "inBattle": coop(c, "inBattle")["inBattle"], "sepReturn": sep, "chain": ctx.get("ret")}
    r.cell("RED 2: the client top GeoscapeState with no CoopState / LoadGameState, geo_state.funds == MARKER, inBattle false, "
           "sepReturn.ownLoaded 1", ok1.get("pressed") and ok and red2["geo_clean"] and red2["funds"] == x.marker
           and red2["inBattle"] is False and sep.get("ownLoaded") == 1, red2)
    changed = wait_until(lambda: be.coop_fnv(h, "host_copy_of_client")[0] not in (h0, None, ""), W)
    info, x.copy_head = host_copy(h)
    r.ev["host copy"] = dict(info, H0=h0, changed=bool(changed))
    r.cell(f"within {W:.0f} s the host copy's fnv != H0, its dump has no `battleGame:` and no `inBattlescape: true` line",
           changed and info.get("lines") and not info.get("battleGame") and not info.get("inBattlescape true"), r.ev["host copy"])
    okh = be.press_ok(h)
    reached, screens = be.drain(h) if okh["pressed"] else (False, [])
    r.ev["host OK"] = {"ok": okh, "screens": screens, "stack": stack(h)}
    r.cell("the host's OK + drain -> [GeoscapeState]", reached and stack(h) == [GEO], r.ev["host OK"])
    files = session.save_files(c.user_dir)
    r.cell("the client zero-disk", files == [], files)
    if r.fails:
        capture(r, x)


def run(rid, tag, ports, kind, results, walls):
    t0, x, r = time.time(), X(tag, ports[2]), pr.Row(rid, RED)
    x.crash0 = pr.crash_names()
    try:
        try:
            x.host = GameClient("host", ports[0], make_user_dir(tag + "_host"))
            x.client = GameClient("client", ports[1], make_user_dir(tag + "_client"))
            for gc in (x.host, x.client):
                gc.spawn()
            for gc in (x.host, x.client):
                gc.connect()
            x.keys = {"ufo": cr.read_key(x.client.user_dir, "keyGeoUfopedia"), "cancel": cr.read_key(x.client.user_dir, "keyCancel")}
        except Exception as e:
            r.cell(f"boot {tag}", False, short(e, 300))
            capture(r, x)
        else:
            entry_row(r, x, kind)
    except Exception as e:
        r.cell(f"G: {rid} exception", False, short(e, 600))
        capture(r, x)
    finally:
        for gc in (x.client, x.host):
            if gc is None:
                continue
            try:
                gc.shutdown()
            except Exception as e:
                r.cell(f"{tag} shutdown ({gc.name})", False, short(e, 300))
                r.cap.setdefault("shutdown", short(e, 300))
    r.ev["CRASH"] = pr.crash_info(x.crash0)
    walls[rid] = r.ev["wall s"] = round(time.time() - t0, 1)
    r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    run("H21d-E1", "w2h21ena", (49536, 49537, "46974"), "P1", results, walls)
    run("H21d-E2", "w2h21enb", (49538, 49539, "46975"), "P4", results, walls)
    failed = [rid for rid in ("H21d-E1", "H21d-E2") if not results.get(rid)]
    print(f"\ntest_w2_practice_battle_entry: {2 - len(failed)}/2 passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
