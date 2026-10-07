"""R4-L6 row SV1 (PRD r4 T4.6, D92, D101, D136 (b)): a quick-save during the host's own autoshot waits for the shots,
and the resumed battle holds the after-shot state.

Spec: docs repo rewrite/prompts/r4l6_lifecycle_rows_lint.md section (f) SV1, with AMENDMENT R4-L6-1 M1 (RESUME through
session.press_back_when_shown), M2 (every staging pair waits on the seq barrier) and M3 (one lane crash folder).
Constants: rewrite/r4l6-task0/CONSTANTS.md (T0-4, three boots at 5e80b4965: deferral +1 on 3/3, chain 7.4-11.5 s,
clip 20 -> 17 on 3/3, no unit hit).

Fixture: a SEPARATE campaign guest battle (session.bring_up_separate_guest_battle, key 48562). S = the host squad's
first battle unit, stripped on both (client first, deleted sets equal, barrier), given a rifle + clip and full TU on
both (test_w2_delta_core.both), the host's fire dial at 1. T = the tile AIM_STEPS steps from S along its facing,
clamped into the map, same level. The host fires an autoshot at T and requests a quick-save at once. After the shot
context closes and the deferred save is written, `post` is recorded on both; both quit; the host resumes the file
with a client on an EMPTY user dir (key 48563) and presses RESUME.

Cells: S1 deferred, S2 the chain ran, S3 the file holds the after-shot state, S4 pre-quit agreement, S5 resumed,
S6 the resumed battle holds `post`, S7 no shot replayed on the client, S8 plays on, S9 zero-disk + no crash.
One EVIDENCE line, then one line per cell, then the verdict. Exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_r4_save_mid_shot.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import test_w2_delta_core as dc  # noqa: E402

KEY, RESUME_KEY = "48562", "48563"
AIM_STEPS = 4            # CONSTANTS.md T0-4: the target rule
AUTO_SHOTS = 3           # CONSTANTS.md T0-4: an autoshot spends 3 rounds of the clip (20 -> 17 on 3/3 boots)
CHAIN_MIN_S = 1.0        # CONSTANTS.md T0-4 bar: the chain outlasts SaveGameState's warm-up (7.4-11.5 s measured)
TU_FULL = 255            # battle_set_unit_state tu: clamped to the unit's max TU
FIRE_DIAL = 1            # the host's battleFireSpeed (seat 0): the slowest shot
EQUAL = "battle_ready saveBlob EQUAL"
MISMATCH = "battle_ready saveBlob MISMATCH"


def units(gc):
    return {u["id"]: u for u in session.battle_state(gc)["units"]}


def item_qty(gc, item_id):
    for it in gc.cmd({"cmd": "battle_items"}).get("items", []):
        if it.get("id") == item_id:
            return it.get("qty")
    return None


def wait_seat_dial(host, client, seat, which, value, timeout=15):
    """Both machines' speed table hold `value` for `seat`'s `which` dial (test_w2_client_shoot.wait_seat_dial)."""
    def ok():
        for gc in (host, client):
            sp = session.event_state(gc).get("speed") or {}
            ent = [s for s in sp.get("seats", []) if s.get("seat") == seat]
            if not ent or ent[0].get(which) != value:
                return None
        return True
    host.wait_for(f"seat {seat} {which} dial {value} on both", ok, timeout=timeout, interval=0.2)


def strip_both(host, client, uid):
    """test_w2_client_items.strip_both's shape: client first, deleted sets equal, then the seq barrier (M2)."""
    rc = client.cmd({"cmd": "battle_strip_unit", "unit": uid})
    rh = host.cmd({"cmd": "battle_strip_unit", "unit": uid})
    assert rh.get("ok") and rc.get("ok"), f"battle_strip_unit {uid}: host={rh} client={rc}"
    dh, dc_ = set(rh.get("deleted") or []), set(rc.get("deleted") or [])
    assert dh == dc_, f"battle_strip_unit {uid} deleted sets differ: host={sorted(dh)} client={sorted(dc_)}"
    session.wait_seq_barrier(host, client)
    return sorted(dh)


def post_snap(gc, sid, clip):
    """S's x/y/z/tu/status, the clip's qty, turn, side, mapFingerprint, every unit's id/status/health/stun/x/y/z and the
    turn mode (spec (f) SV1 `post`)."""
    bs = session.battle_state(gc)
    s = next(u for u in bs["units"] if u["id"] == sid)
    return {"S": {k: s.get(k) for k in ("x", "y", "z", "tu", "status")}, "clipQty": item_qty(gc, clip),
            "turn": bs.get("turn"), "side": bs.get("side"), "mapFingerprint": bs.get("mapFingerprint"),
            "units": sorted([u["id"], u["status"], u["health"], u["stun"], u["x"], u["y"], u["z"]] for u in bs["units"]),
            "turnMode": session.event_state(gc).get("turnMode")}


def sav_entries(path, section):
    """{id: {key: raw value}} for the top-level scalar keys of each `battleGame:` -> `<section>:` entry of a .sav."""
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    ind = lambda l: len(l) - len(l.lstrip(" "))  # noqa: E731
    i = lines.index("battleGame:")
    j = next(k for k in range(i + 1, len(lines)) if lines[k].strip() == section + ":" and ind(lines[k]) == 2)
    out, cur, eind, fi = {}, None, None, None
    for line in lines[j + 1:]:
        if not line.strip():
            continue
        if ind(line) <= 2 and not line.lstrip().startswith("- "):
            break
        st = line.lstrip()
        if st.startswith("- ") and (eind is None or ind(line) == eind):
            eind, cur, st, fi = ind(line), {}, st[2:], ind(line) + 2
        elif cur is None or ind(line) != fi:
            continue
        m = re.match(r"([A-Za-z_]+):\s*(.*)$", st)
        if m:
            cur[m.group(1)] = m.group(2)
            if m.group(1) == "id":
                out[int(m.group(2))] = cur
    return out


def log_count(gc, needle):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if needle in line)


def stack(gc):
    return [s.replace("class OpenXcom::", "") for s in session.states(gc)]


def main():
    host_dir = make_user_dir("r4sv_host")
    client_dir = make_user_dir("r4sv_client")
    host = GameClient("host", 1, host_dir)
    client = GameClient("client", 2, client_dir)
    client2_dir = None
    cells = {}
    ev = {}
    crash0 = session._crash_log_snapshot()
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        host_squad, _guest_local = session.bring_up_separate_guest_battle(host, client, port=KEY)
        sid = [u for u in session.battle_state(host)["units"]
               if u.get("soldierId") in host_squad and not u.get("isOut")][0]["id"]
        ev["S"] = sid
        ev["stripped"] = strip_both(host, client, sid)
        g = dc.both(host, client, {"cmd": "battle_give", "unit": sid, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP",
                                   "clear_hands": True}, ("weaponId", "ammoId"))
        rifle, clip = g["weaponId"], g["ammoId"]
        ev["rifle"], ev["clip"] = rifle, clip
        ev["tu"] = dc.both(host, client, {"cmd": "battle_set_unit_state", "unit": sid, "tu": TU_FULL}, ("tu",))["tu"]
        host.ok({"cmd": "set_option", "name": "battleFireSpeed", "value": FIRE_DIAL})
        wait_seat_dial(host, client, 0, "fire", FIRE_DIAL)
        u = units(host)[sid]
        size = host.cmd({"cmd": "find_doors", "limit": 1})
        d = u["direction"]
        t = (min(max(u["x"] + AIM_STEPS * session.DIR_DX[d], 0), size["mapSizeX"] - 1),
             min(max(u["y"] + AIM_STEPS * session.DIR_DY[d], 0), size["mapSizeY"] - 1), u["z"])
        ev["Spos"], ev["Sdir"], ev["T"] = (u["x"], u["y"], u["z"]), d, t
        qty0 = item_qty(host, clip)
        ctx0 = {c.get("actionId") for c in (session.event_state(host).get("closedContexts") or [])}
        b0 = session.battle_state(host)
        deferrals0 = b0.get("coopSaveDeferrals")
        pre = {x["id"]: (x["status"], x["health"], x["x"], x["y"], x["z"]) for x in b0["units"]}
        saves0 = set(session.save_files(host_dir))
        ev["qty0"], ev["deferrals0"] = qty0, deferrals0
        ev["fire"] = host.ok({"cmd": "battle_fire", "unit": sid, "mode": "auto", "x": t[0], "y": t[1], "z": t[2]})
        t_fire = time.time()
        host.ok({"cmd": "save_game_ui", "type": "quick_battle"})

        def shot_closed():
            new = [c for c in (session.event_state(host).get("closedContexts") or []) if c.get("actionId") not in ctx0]
            return [c for c in new if c.get("origin") == "host" and c.get("kind") == "shoot"
                    and c.get("actorId") == sid] or None

        ev["ctx"] = host.wait_for("the host autoshot's context closed", shot_closed, timeout=60, interval=0.1)
        ev["chainS"] = round(time.time() - t_fire, 2)
        new_files, pending = set(), None
        deadline = time.time() + 30
        while time.time() < deadline:
            pending = session.battle_state(host).get("coopSavePending")
            new_files = set(session.save_files(host_dir)) - saves0
            if pending is False and new_files:
                break
            time.sleep(0.2)
        b1 = session.battle_state(host)
        ev["pending"], ev["newFiles"] = pending, sorted(new_files)
        ev["deferrals1"] = b1.get("coopSaveDeferrals")
        ev["deferredAt"], ev["writtenAt"] = b1.get("coopSaveDeferredAt"), b1.get("coopSaveDeferredWrittenAt")
        cells["S1"] = (pending is False and len(new_files) == 1 and isinstance(deferrals0, int)
                       and ev["deferrals1"] == deferrals0 + 1,
                       f"coopSaveDeferrals {deferrals0} -> {ev['deferrals1']} (want +1), coopSavePending {pending}, "
                       f"new save files {sorted(new_files)} (want exactly 1)")
        session.wait_seq_barrier(host, client)
        post, post_c = post_snap(host, sid, clip), post_snap(client, sid, clip)
        now = {x[0]: (x[1], x[2], x[4], x[5], x[6]) for x in post["units"]}
        ev["post"] = post
        ev["hit"] = {i: (pre.get(i), v) for i, v in now.items() if i != sid and pre.get(i) != v}  # recorded only
        cells["S2"] = (qty0 is not None and post["clipQty"] == qty0 - AUTO_SHOTS and post_c["clipQty"] == post["clipQty"]
                       and ev["chainS"] >= CHAIN_MIN_S,
                       f"clip qty {qty0} -> host {post['clipQty']} / client {post_c['clipQty']} (want {qty0} - "
                       f"{AUTO_SHOTS} on both), chain {ev['chainS']} s (want >= {CHAIN_MIN_S})")
        if len(new_files) == 1:
            sav = os.path.join(host_dir, next(iter(new_files)))
            su, si = sav_entries(sav, "units").get(sid, {}), sav_entries(sav, "items").get(clip, {})
            ev["sav"] = {"file": os.path.basename(sav), "S.tu": su.get("tu"), "S.status": su.get("status"),
                         "clip.ammoqty": si.get("ammoqty")}
            cells["S3"] = (si.get("ammoqty") == str(post["clipQty"]) and su.get("tu") == str(post["S"]["tu"])
                           and su.get("status") == str(post["S"]["status"]),
                           f".sav clip ammoqty {si.get('ammoqty')} / S tu {su.get('tu')} status {su.get('status')} "
                           f"(want {post['clipQty']} / {post['S']['tu']} / {post['S']['status']})")
        else:
            cells["S3"] = (False, f"no single new save file: {sorted(new_files)}")
        cells["S4"] = (post == post_c, f"post equal on both: {post == post_c} (keys that differ: "
                                       f"{[k for k in post if post[k] != post_c.get(k)]}; S {post['S']})")
        ev["clientDiskPreQuit"] = session.save_files(client_dir)

        host.shutdown(); client.shutdown()
        client2_dir = make_user_dir("r4sv_client2")
        host = GameClient("host", 3, host_dir)
        client = GameClient("client", 4, client2_dir)
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        eq0, mm0 = log_count(host, EQUAL), log_count(host, MISMATCH)
        t_res = time.time()
        session.resume_campaign_battle(host, client, ev["sav"]["file"], port=RESUME_KEY, timeout=180)
        ev["resumeS"] = round(time.time() - t_res, 1)
        try:  # bounded settle: the host's battle_ready verdict line and phase Active follow the client's load
            host.wait_for("host battle_ready verdict", lambda: (session.battle_state(host).get("phase") == "Active" and
                          log_count(host, EQUAL) + log_count(host, MISMATCH) > eq0 + mm0) or None, timeout=30)
        except TimeoutError:
            pass
        bh, bc = session.battle_state(host), session.battle_state(client)
        ah, ac = bh.get("authority") or {}, bc.get("authority") or {}
        desync = [session.event_state(gc).get("desyncSeen") for gc in (host, client)]
        eq, mm = log_count(host, EQUAL) - eq0, log_count(host, MISMATCH) - mm0
        cells["S5"] = (bh.get("inBattle") and bc.get("inBattle") and bh.get("phase") == "Active"
                       and bc.get("phase") == "Active" and ah.get("battleId") and ah.get("battleId") == ac.get("battleId")
                       and eq == 1 and mm == 0 and desync == [False, False],
                       f"inBattle {bh.get('inBattle')}/{bc.get('inBattle')}, phase {bh.get('phase')}/{bc.get('phase')}, "
                       f"battleId {ah.get('battleId')}/{ac.get('battleId')}, saveBlob EQUAL +{eq} MISMATCH +{mm}, "
                       f"desyncSeen {desync}")
        seen = {}

        def holds():
            seen["h"], seen["c"] = post_snap(host, sid, clip), post_snap(client, sid, clip)
            return (seen["h"] == post and seen["c"] == post) or None
        try:
            host.wait_for("the resumed battle holds post on both", holds, timeout=30, interval=1.0)
        except TimeoutError:
            pass
        diff = {gc: [k for k in post if (seen.get(gc) or {}).get(k) != post[k]] for gc in ("h", "c")}
        cells["S6"] = (seen.get("h") == post and seen.get("c") == post,
                       f"keys that differ from post: host {diff['h']} / client {diff['c']} (want none); "
                       f"resumed S {(seen.get('h') or {}).get('S')} clip {(seen.get('h') or {}).get('clipQty')}")
        shots = [e for e in session.event_log(client, tail=100) if e.get("kind") == "shot"]
        cells["S7"] = (not shots, f"resumed client shot evs {shots} (want none)")
        try:
            session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
            for gc in (host, client):
                gc.wait_for(f"{gc.name} on BattlescapeState after RESUME",
                            lambda gc=gc: (session.top_state(gc) == "BattlescapeState") or None, timeout=60, interval=0.5)
            tops = [stack(host), stack(client)]
            ev["tops"] = tops
            assert not any(s in st for st in tops for s in ("HostMenu", "LobbyMenu")), f"HostMenu/LobbyMenu: {tops}"
            guest = [x for x in session.battle_state(host)["units"]
                     if x.get("isPlayerSoldier") and "Guest" in (x.get("name") or "")]
            assert len(guest) == 1, f"guest battle unit: {guest}"
            session.assert_t_cmd(host, client, guest[0]["soldierId"], host_squad[0], host_check=False, what="SV1")
            cells["S8"] = (True, f"both tops BattlescapeState {tops}; T-CMD admit + deny passed")
        except (AssertionError, TimeoutError, RuntimeError) as e:
            cells["S8"] = (False, f"{type(e).__name__}: {str(e)[:400]}")
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                ev.setdefault("shutdown", []).append(f"{gc.name}: {e}")
    crash_new = sorted(session._crash_log_snapshot() - crash0)
    disk = (ev.get("clientDiskPreQuit"), session.save_files(client2_dir) if client2_dir else None)
    cells["S9"] = (disk == ([], []) and not crash_new,
                   f"client save files pre-quit {disk[0]} / resumed {disk[1]} (want [] / []), new crash files {crash_new}")
    print(f"EVIDENCE SV1: {ev}", flush=True)
    fails = 0
    for name in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"):
        ok, detail = cells.get(name, (False, "not reached: " + str(ev.get("error"))))
        fails += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)
    print("SV1 %s (%d of 9 cells failed)" % ("PASS" if not fails else "FAIL", fails), flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
