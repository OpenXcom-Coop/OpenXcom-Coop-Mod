"""W2-H21d S-1 (F8980 routed, F9194; spec rewrite/prompts/w2h21d_preview_battle_paths.md (f), QH21d-4 a, QH21d-5 a; TASK 0
rewrite/w2h21d-task0/s1/CONSTANTS.md): a rejoin while the host has a practice screen open (a Ufopaedia craft preview, a base
equipment screen) never finishes. The host's rejoin arm reads the practice battle as a battle to resume, its resume_ack takes the
battle branch, offerResumedBattle refuses at lobbyMode 1, nothing sets resumeAck and the rejoined client holds on 68 (TASK 0 4/4;
T0-I TRACE: resumeBattlePending=1 with preview=1 / baseInv=1, then the refusal).
  Boot R1 bring_up("w2h21pra", (49526, 49527, 46970)); rejoined client label 49528, dir w2h21pra_client2:
    H21d-R1 (named RED) PV(host); non-vacuity: the host top BattlescapeState, isPreview true, inBattle true; client.kill(); the host's
        62 on top over the preview; client2 join_tcp. RED 1: within W_ACK the host's resumeAck true, HL holds RELEASE and no REFUSED
        (TASK 0: false / REFUSED, client2 on 68). profile_ok when a Profile is on top; RESUME (60, 62); within W client2 top
        GeoscapeState, coopDialog != 68; the host top BattlescapeState, isPreview true, no CoopState on its stack; END(host) ->
        [GeoscapeState], has_battle false; the worlds equal (host, client2); client2 zero-disk.
  Boot R2 (SEPARATE) GameClient 49529 / 49530, new_campaign(port "46971"); rejoined client label 49531, dir w2h21prb_client2:
    H21d-R2 (named RED) the client's own-soldier names; the host's P4 (open_craft_equipment, craft_inventory); non-vacuity: top
        InventoryState, inBattle true; kill; 62 over it; client2 joins. RED 1 as R1. RESUME; within W client2 top GeoscapeState,
        coopDialog != 68; the host top InventoryState, no CoopState; close P4 (battle_inventory ok, craft_equipment_ok) ->
        [GeoscapeState], inBattle false; client2's own-soldier names == before; client2 zero-disk.
W_ACK = 30 s (CONSTANTS: max(30 s, 3 x t_ack 2.42 s)) from client2's join_tcp; W = 10 s at 0.25 s polls, HOLD = 2 s. HL = the host's
openxcom.log from the size noted before the kill. Setup guard per boot: stacks [GeoscapeState], localSeat 0 / 1, has_battle false, the
host's lobbyMode 1 (a miss fails the boot's row `boot`, one CAPTURE line). A RED 1 miss leaves the row's later cells "not reached".
EVIDENCE before each verdict; a failed row prints ONE CAPTURE line; every row runs after a failure; ONE run (WV-D95); exit 0 iff every
row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_client_research as cr  # noqa: E402  (main-guarded: read_key)
import test_w2_preview_restream as pr  # noqa: E402  (main-guarded: pv, end_preview, alive, log_*, crash_*, Row)
from harness import GameClient, make_user_dir  # noqa: E402

W, POLL, HOLD, W_ACK, SETTLE = 10.0, 0.25, 2.0, 30.0, 0.3
GEO, BS, INV, CES, CS = "GeoscapeState", "BattlescapeState", "InventoryState", "CraftEquipmentState", "CoopState"
RELEASE = "[coop] restream adopted; the host wait dialog owns the release"
REFUSED = "offerResumedBattle() called outside a disk resume"
KEYS = ("restream adopted", "offerResumedBattle", "F3 battle resume", "[coop-session]", "streaming authoritative")
RED = ("named red: TASK 0 4/4 no resumeAck at W_ACK, REFUSED in HL, client2 on 68 "
       "(T0-I: resumeBattlePending=1 with preview=1 / baseInv=1)")
q, stack, short, wait_until = pr.q, pr.stack, pr.short, pr.wait_until


class X:
    def __init__(self, tag):
        self.tag, self.js, self.host, self.client, self.client2, self.keys = tag, None, None, None, None, None


def msg(lines):
    return [ln.split("\t")[-1][:220] for ln in lines]


def coop(gc, *keys):
    c = q(gc, {"cmd": "get_coop"})
    return {k: c.get(k) for k in keys}


def dump(gc):
    if gc is None or not pr.alive(gc):
        return "<dead or absent>"
    bs = q(gc, {"cmd": "battle_state"})
    return {"stack": stack(gc), "get_coop": coop(gc, "lobbyMode", "resumeAck", "inBattle", "coopDialog", "coopSession", "localSeat"),
            "world_state": {k: v for k, v in q(gc, {"cmd": "world_state"}).items() if k in ("has_battle", "has_save", "error")},
            "battle_state": {k: bs.get(k) for k in ("isPreview", "phase", "turn", "error")}}


def capture(r, x, n_hl=0, crash=None, extra=None):
    if r.cap:
        return
    r.cap.update({"HL": [ln for ln in msg(pr.log_lines(x.host, n_hl)) if any(k in ln for k in KEYS)][-20:],
                  "host log": msg(pr.log_lines(x.host)[-20:]), "CRASH": crash, "host": dump(x.host),
                  ("client2" if x.client2 else "client"): dump(x.client2 or x.client)}, **(extra or {}))


def own_names(gc):
    bases = q(gc, {"cmd": "get_soldiers"}).get("bases") or []
    return sorted(s.get("name") for b in bases if not b.get("coopBaseFlag") for s in b.get("soldiers") or [])


def practice(r, x, kind):
    """kind P1: W2-H21c's PV(host); P4: the host's own base's first craft, its inventory. The non-vacuity cell; False = not open"""
    h = x.host
    if kind == "P1":
        ok, r.ev["PV(host)"] = pr.pv(h, x.keys)
        want = BS
    else:
        a = q(h, {"cmd": "open_craft_equipment"})
        b = wait_until(lambda: CES in stack(h), W) and q(h, {"cmd": "craft_inventory"})
        ok = bool(a.get("ok") and b and b.get("opened") and wait_until(lambda: pr.on_top(h, INV), W))
        r.ev["P4(host)"], want = {"open_craft_equipment": a, "craft_inventory": b}, INV
    pre, ib = q(h, {"cmd": "battle_state"}).get("isPreview"), coop(h, "inBattle")["inBattle"]
    r.ev["non-vacuity"] = {"stack": stack(h), "isPreview": pre, "inBattle": ib}
    nv = ok and pr.on_top(h, want) and ib is True and (pre is True if kind == "P1" else True)
    what = "BattlescapeState, isPreview true" if kind == "P1" else "InventoryState"
    if not r.cell(f"non-vacuity: the host's {kind} open (top {what}, inBattle true)", nv, r.ev["non-vacuity"]):
        capture(r, x)
    return nv


def drop(r, x):
    """client.kill(); the host notices the drop and its 62 sits on top over the practice screen -> (ok, HL size, crash names)"""
    n_hl, before, h = pr.log_size(x.host), pr.crash_names(), x.host
    under = stack(h)[-1:]
    x.client.kill()
    gone = wait_until(lambda: coop(h, "coopSession")["coopSession"] is False, 60)
    on62 = gone and wait_until(lambda: stack(h)[-2:] == under + [CS] and q(h, {"cmd": "coop_dialog_info"}).get("code") == 62, W)
    r.ev["drop"] = {"noticed": gone, "host stack": stack(h), "dialog": q(h, {"cmd": "coop_dialog_info"}).get("code")}
    if not r.cell(f"G: the host's 62 on top over its {under}", on62, r.ev["drop"]):
        capture(r, x, n_hl)
    return bool(on62), n_hl, before


def rejoin_row(r, x, kind, label):
    h = x.host
    if kind == "P4":
        r.ev["own names before"] = names0 = own_names(x.client)
    if not practice(r, x, kind):
        return
    ok, n_hl, before = drop(r, x)
    if not ok:
        return
    x.client2 = c2 = GameClient("client", label, make_user_dir(x.tag + "_client2"))
    c2.spawn()
    c2.connect()
    j, t_join = q(c2, {"cmd": "join_tcp", "ip": "127.0.0.1", "port": str(x.coop_port), "player": "ClientPlayer"}), time.time()
    if not r.cell("G: client2 join_tcp", j.get("ok"), j):
        return capture(r, x, n_hl)
    ack = wait_until(lambda: coop(h, "resumeAck")["resumeAck"] is True, W_ACK)
    t_ack = round(time.time() - t_join, 2)
    rel = bool(ack) and wait_until(lambda: any(RELEASE in ln for ln in pr.log_lines(h, n_hl)), HOLD)
    refused = [ln for ln in msg(pr.log_lines(h, n_hl)) if REFUSED in ln]
    r.ev["RED 1"] = red1 = {"resumeAck": ack, "s": t_ack, "RELEASE": rel, "REFUSED": refused, "host stack": stack(h),
                            "client2": [stack(c2), coop(c2, "coopDialog")]}
    if not r.cell(f"RED 1: within {W_ACK:.0f} s the host's resumeAck true, HL holds RELEASE and no REFUSED", ack and rel and not refused,
                  red1):
        r.ev["not reached (RED 1 ends the row)"] = "RESUME, client2 geoscape, the host's screen, the close, world / names, zero-disk"
        return capture(r, x, n_hl, pr.crash_info(before))
    if pr.on_top(h, "Profile"):
        r.ev["profile_ok"] = q(h, {"cmd": "profile_ok"})
        wait_until(lambda: pr.on_top(h, CS), W)
    try:
        bk = session.press_back_when_shown(h, "host RESUME", codes=(60, 62), timeout=W)
    except Exception as e:
        bk = {"error": short(e, 400)}
    if not r.cell("RESUME (codes 60, 62) pressed", bk.get("ok"), bk):
        return capture(r, x, n_hl, pr.crash_info(before))
    c2geo = wait_until(lambda: pr.on_top(c2, GEO) and coop(c2, "coopDialog")["coopDialog"] != 68, W)
    r.cell(f"within {W:.0f} s client2 top {GEO}, coopDialog != 68", c2geo, dump(c2))
    want = BS if kind == "P1" else INV
    top = wait_until(lambda: pr.on_top(h, want) and CS not in stack(h), W)
    pre = q(h, {"cmd": "battle_state"}).get("isPreview")
    r.cell(f"the host top {want}" + (", isPreview true" if kind == "P1" else "") + ", no CoopState on its stack",
           top and (pre is True or kind == "P4"), [stack(h), pre])
    if kind == "P1":
        ok, r.ev["END(host)"] = pr.end_preview(h, x.keys)
        r.cell("END(host) -> [GeoscapeState], has_battle false", ok and q(h, {"cmd": "world_state"}).get("has_battle") is False,
               r.ev["END(host)"])
        try:
            shared_fixture.assert_world_equal(h, c2, "H21d-R1")
        except AssertionError as e:
            r.cell("the worlds equal (host, client2)", False, short(e, 1500))
    else:
        time.sleep(SETTLE)
        a = q(h, {"cmd": "battle_inventory", "action": "ok"})
        a2 = wait_until(lambda: INV not in stack(h), W) and q(h, {"cmd": "craft_equipment_ok"})
        closed = a.get("ok") and a2 and a2.get("ok") and wait_until(lambda: stack(h) == [GEO], W)
        r.ev["close P4"] = {"battle_inventory": a, "craft_equipment_ok": a2, "stack": stack(h)}
        r.cell("close P4 -> the host [GeoscapeState], inBattle false", closed and coop(h, "inBattle")["inBattle"] is False,
               r.ev["close P4"])
        names1 = own_names(c2)
        r.cell("client2's own-soldier names == before", names1 == names0, [names0, names1])
    files = session.save_files(c2.user_dir)
    r.cell("client2 zero-disk", files == [], files)
    if r.fails:
        capture(r, x, n_hl, pr.crash_info(before))


def boot(r, x, ports, separate):
    """bring-up + the setup guard; False = a boot miss (the row fails `boot`, one CAPTURE line)"""
    try:
        if separate:
            x.host = GameClient("host", ports[0], make_user_dir(x.tag + "_host"))
            x.client = GameClient("client", ports[1], make_user_dir(x.tag + "_client"))
            for gc in (x.host, x.client):
                gc.spawn()
            for gc in (x.host, x.client):
                gc.connect()
            session.new_campaign(x.host, x.client, port=str(ports[2]))
            geo.wait_both_ready(x.host, x.client)
        else:
            x.js = shared_fixture.bring_up(x.tag, ports)
            x.host, x.client = x.js.host, x.js.client
        x.coop_port = ports[2]
        x.keys = {"ufo": cr.read_key(x.host.user_dir, "keyGeoUfopedia"), "cancel": cr.read_key(x.host.user_dir, "keyCancel")}
        su = {gc.name: [stack(gc), coop(gc, "localSeat")["localSeat"], q(gc, {"cmd": "world_state"}).get("has_battle")]
              for gc in (x.host, x.client)}
        su["host lobbyMode"] = coop(x.host, "lobbyMode")["lobbyMode"]
        r.ev["setup " + x.tag] = dict(su, keys=x.keys)
        assert su == {"host": [[GEO], 0, False], "client": [[GEO], 1, False], "host lobbyMode": 1}, f"setup guard: {su}"
        return True
    except Exception as e:
        r.cap["boot " + x.tag] = {"error": short(e, 1500), "host": dump(x.host), "client": dump(x.client)}
        return r.cell(f"boot {x.tag}", False, short(e, 300))


def shut(r, x, tolerate_host=False):
    """every machine of the boot; the row's killed client is already reaped; a host death is tolerated only on a RED cell"""
    for gc in (x.client2, x.client, x.host):
        if gc is None:
            continue
        try:
            gc.shutdown()
        except Exception as e:
            if gc is x.host and tolerate_host:
                r.ev["shutdown, host died on a RED cell (tolerated)"] = short(e, 300)
            else:
                r.cell(f"{x.tag} shutdown ({gc.name})", False, short(e, 300))
                r.cap.setdefault("shutdown", short(e, 300))


def run(rid, tag, ports, row, results, walls, separate=False, args=(), task0=RED):
    t0, x, r = time.time(), X(tag), pr.Row(rid, task0)
    try:
        if boot(r, x, ports, separate):
            row(r, x, *args)
    except Exception as e:
        r.cell(f"G: {rid} exception", False, short(e))
        capture(r, x)
    finally:
        shut(r, x, tolerate_host=getattr(x, "host_died_on_red", False))
    walls[rid] = r.ev["wall s"] = round(time.time() - t0, 1)
    r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    run("H21d-R1", "w2h21pra", (49526, 49527, 46970), rejoin_row, results, walls, args=("P1", 49528))
    run("H21d-R2", "w2h21prb", (49529, 49530, 46971), rejoin_row, results, walls, separate=True, args=("P4", 49531))
    failed = [rid for rid in ("H21d-R1", "H21d-R2") if not results.get(rid)]
    print(f"\ntest_w2_practice_rejoin: {2 - len(failed)}/2 passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
