"""R5-U8b (CAP-2) row B4 (PvE2 boot with test mod Coop_ArmorMult_Test on both machines): an armor-damaging hit on a PvE2 alien
whose current armor exceeds the second player's maximum armor desyncs the second player (its delta applier clamps current armor to
its own, unadjusted maximum; the `synced` bucket mixes current armor).

Spec: docs repo rewrite/prompts/w2h35c_r5u8b_captures.md (f) test_r5_pve2_armor_mod.py, with ruling R-CAP2-1 RN-2 (the host's
`resync_hold` armed before the shot, a 6 s window instead of the seq barrier). Constants: rewrite/r5u8bf-task0/CONSTANTS.md (TASK 0
boots Mp / Ma / Mb, Mc / Md on the base + TP1 build). TASK 0 verdicts: B4 CONFIRMED (SEED_B4 3); B1, B3, B2 CONFIRMED
(test_r5_pve2_built.py).

Boot (key 48866): test_r5_pve2's bring-up (the PF lobby to gamemode 4, STR_MEDIUM_SCOUT, SEED_ROSTER / SEED_MAP 1, both briefings
and equip screens, pin_ai_neutral, reactions 0, both Turn 1 screens closed, the stable settle at side 0 turn 2), the mod in both user
dirs (make_user_dir(..., mods=[MOD_DIR])); C1 (1000000) to C1_TILE and H1 (1000002) to H1_TILE, two tiles apart, TU 54 on both.
  B4  B4-pre: every alien's host armorMax = int(base x 0.5) + 20 (difficulty 0), armorCur equal on both, every hash bucket EQUAL,
      desyncSeen false on both. Then H1 TU max (both), the host's `resync_hold` on, host `set_seed SEED_B4`, host `battle_fire
      {unit H1, aimed, C1's tile, tu 255}`, and a WINDOW_S window from the shot sampling both machines' C1 armorCur, desyncSeen and
      event seq (a sample is seq-consistent when the client's applied seq equals the host's emitted seq around both armor reads).
      B4-hit: the host's C1 armorCur changed in the window and every side above ARMOR_BASE (precondition). B4-armor: every
      seq-consistent sample and the read at the window's end show C1's armorCur equal on both. B4-hash: every bucket EQUAL at the
      window's end, desyncSeen false on both in every sample, no new crash file. The hold is released after the reads.
B4 is the file's only row and the boot's last action (on the red build the client freezes at the hit). No common cell (B4-hash is it).
RED at 2R: B4-armor, B4-hash; B4-pre and B4-hit PASS.
B4-hit compares with ARMOR_BASE (SECTOID_ARMOR0, the client's maximum on the red build); the spec's text "the client's armorMax" would
equal the host's own maximum after 2G and fail there (F15445).

One EVIDENCE line, then one PASS/FAIL line per cell, then the row verdict. A boot step past its bound prints ONE CAPTURE M line and
fails every cell "boot"; a staging step past its bound fails them "staging". WV-D95: run in the foreground to completion. WV-D99 /
WV-D100: ONE run is the result, no skip path; exit 0 only when every cell passes, else 2.

Run:  python tools/coop_test/test_r5_pve2_armor_mod.py
"""

import contextlib
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import event_state  # noqa: E402
import pvp_fixture as PF  # noqa: E402
from test_w2_delta_core import both, tele_both, tu_both  # noqa: E402
import test_r5_pve2 as PVE  # noqa: E402
from test_w2_battle_end_rules import wait_until  # noqa: E402
from test_r5_pvp_gm3 import (Miss, stack, top, log_count, capture, guarded, reactions_zero, hash_now, verdict,  # noqa: E402
                             fail_all, shut)

KEY = "48866"                     # this file's lobby key (spec (G))
MOD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_ArmorMult_Test")
SEED_ROSTER, SEED_MAP = 1, 1
MISSION = "STR_MEDIUM_SCOUT"
GAMEMODE_PVE2 = 4
MAP_FP = 7.136941435423656e+17
ALIEN_IDS = [1000000, 1000001, 1000002, 1000003, 1000004]
ARMOR_BASE = [4, 3, 3, 2, 2]      # SECTOID_ARMOR0 front / left / right / rear / under (armors.rul), every alien of the boot
ARMOR_MULT, ARMOR_ABS = 0.5, 20   # xcom1 difficulty 0 aimAndArmorMultipliers[0]; the mod's armorMultipliersAbs (pinned)
ARMOR_MAX_HOST = [int(b * ARMOR_MULT) + ARMOR_ABS for b in ARMOR_BASE]   # [22, 21, 21, 21, 21] (Mp / Ma / Mb / Mc / Md)
H1_ID, H1_TILE, H1_DIR = 1000002, (27, 13, 0), 2   # the host's seat-0 alien (test_r5_pve2 H1)
C1_ID, C1_TILE, C1_DIR = 1000000, (27, 11, 0), 2   # the client's seat-1 alien, two tiles north of H1 (test_r5_pve2 C1)
TU = 54
SEED_B4 = 3                       # the 1..40 hunt's first seed whose aimed shot lowers C1's armor (Mp; Ma, Mb, Mc, Md repeat it)
WINDOW_S = 6.0                    # R-CAP2-1 RN-2
MIN_SAMPLES = 5                   # a window with fewer samples is vacuous (WV-D83; ~15 samples quiet, six reads each)
STEP_S, BOOT_S = 30, 60
ROWS = (("B4", ("B4-pre", "B4-hit", "B4-armor", "B4-hash")),)


def ub(gc):
    return {u["id"]: u for u in gc.cmd({"cmd": "battle_state"}).get("units", [])}


def p3(u):
    return (u.get("x"), u.get("y"), u.get("z"))


def miss(err, machines):
    capture("M", err, machines)
    raise Miss("M")


def bring_up(host, client):
    """test_r5_pve2.bring_up with this file's key (no A1-bleed phases); the mod is in both user dirs already."""
    m, boot = (host, client), {}
    guarded("M", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    guarded("M", lambda: host.ok({"cmd": "set_seed", "seed": SEED_ROSTER}), m)
    boot["gm2"] = guarded("M", lambda: PF.start_pvp_skirmish_lobby(host, client, KEY, alien_player="client"), m)[0]
    row = guarded("M", lambda: PF.row_for(host, "HostPlayer"), m)
    boot["lobbyGamemode"] = guarded("M", lambda: host.ok({"cmd": "lobby_set_team", "row": row, "team": "Alien"}),
                                    m).get("gamemode")
    ok, secs = wait_until(lambda: PF._lobby(host).get("playerTeams") == ["Alien", "Alien"]
                          and PF._lobby(client).get("playerTeams") == ["Alien", "Alien"], 10, 0.25)
    if not ok:
        miss(f"step 3: both lobby rows Alien not shown in {secs} s", m)
    guarded("M", lambda: host.ok({"cmd": "lobby_action"}), m)
    guarded("M", lambda: host.wait_for("host at battle settings",
                                       lambda: (not session.has_state(host, "LobbyMenu")) or None), m)
    if top(host) != "NewBattleState":
        miss(f"step 4: host stack {stack(host)} (want NewBattleState on top)", m)
    guarded("M", lambda: host.ok({"cmd": "newbattle_mission", "type": MISSION}), m)
    guarded("M", lambda: host.ok({"cmd": "set_seed", "seed": SEED_MAP}), m)
    guarded("M", lambda: host.ok({"cmd": "newbattle_ok"}), m)
    for gc in m:
        ok, secs = wait_until(lambda gc=gc: session.has_state(gc, "BriefingState")
                              or log_count(host, PVE.N_REFUSE_RX) > 0, BOOT_S, 0.1)
        if not ok or log_count(host, PVE.N_REFUSE_RX) > 0:
            miss(f"step 5: {gc.name} BriefingState {ok} after {secs} s; host refusal lines "
                 f"{log_count(host, PVE.N_REFUSE_RX)}", m)
    guarded("M", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    guarded("M", lambda: session.dismiss_client_briefing(client), m)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            session.equip_both_ready(host, client)
    except Exception as e:
        print(buf.getvalue(), end="", flush=True)
        miss(f"step 6: equip_both_ready: {type(e).__name__}: {str(e)[:500]}", m)
    boot["pinned"] = guarded("M", lambda: session.pin_ai_neutral(host, client, tag="r5u8bf"), m)
    guarded("M", lambda: reactions_zero(host, client), m)
    guarded("M", lambda: session.dismiss_battle_start_overlays(client), m)
    guarded("M", lambda: session.dismiss_battle_start_overlays(host), m)
    boot["settle"] = PVE.settle(host, client)   # its own CAPTURE line and Miss on a missed settle
    hb, cb = host.cmd({"cmd": "battle_state"}), client.cmd({"cmd": "battle_state"})
    pins = [log_count(host, PVE.N_EQUAL), log_count(host, PVE.N_MISMATCH), hb.get("coopGamemode"), cb.get("coopGamemode"),
            hb.get("mapFingerprint"), cb.get("mapFingerprint")]
    if pins != [1, 0, GAMEMODE_PVE2, GAMEMODE_PVE2, MAP_FP, MAP_FP]:
        miss(f"step 9: [saveBlob EQUAL, MISMATCH, gamemode h/c, MAP_FP h/c] {pins} (want [1, 0, 4, 4, {MAP_FP}, {MAP_FP}])", m)
    return boot, session._crash_log_snapshot()


def stage(host, client):
    m = (host, client)
    ev = {"c1": guarded("M staging", lambda: tele_both(host, client, C1_ID, C1_TILE, C1_DIR).get("to"), m),
          "h1": guarded("M staging", lambda: tele_both(host, client, H1_ID, H1_TILE, H1_DIR).get("to"), m)}
    for uid in (C1_ID, H1_ID):
        guarded("M staging", lambda uid=uid: both(host, client, {"cmd": "battle_action", "action": "set_stat", "unit": uid,
                                                                 "stat": "tu", "value": TU, "refill": True}, ("tu",)), m)
    guarded("M staging", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)
    uh, uc = ub(host), ub(client)
    at = [p3(uh[C1_ID]), p3(uc[C1_ID]), p3(uh[H1_ID]), p3(uc[H1_ID])]
    if at != [C1_TILE, C1_TILE, H1_TILE, H1_TILE]:
        capture("M staging", f"C1 / H1 host / client {at}", m)
        raise Miss("M staging")
    return ev


def sample(host, client, t0):
    """One window sample: the host's emitted seq around its C1 read, the client's applied seq around its C1 read."""
    e1 = event_state(host)
    hc = (ub(host).get(C1_ID) or {}).get("armorCur")
    e2 = event_state(host)
    a1 = event_state(client)
    cc = (ub(client).get(C1_ID) or {}).get("armorCur")
    a2 = event_state(client)
    seq = [e1.get("lastSeqEmitted"), e2.get("lastSeqEmitted"), a1.get("lastSeqApplied"), a2.get("lastSeqApplied")]
    return {"t": round(time.time() - t0, 3), "host": hc, "client": cc, "consistent": len(set(seq)) == 1, "seq": seq,
            "desync": [bool(e2.get("desyncSeen")), bool(a2.get("desyncSeen"))]}


def row_b4(host, client, staged, crash0):
    ev = {"staged": staged}
    uh, uc = ub(host), ub(client)
    pre_hash = hash_now(host, client)
    pre_ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    off = {i: [uh[i].get("armorMax"), uh[i].get("armorCur"), uc[i].get("armorCur")] for i in ALIEN_IDS
           if uh[i].get("armorMax") != ARMOR_MAX_HOST or uh[i].get("armorCur") != uc[i].get("armorCur")}
    cells = {"B4-pre": (not off and pre_hash == "all buckets EQUAL" and pre_ds == [False, False],
                        f"aliens off [host armorMax, host armorCur, client armorCur] {off} (want host max {ARMOR_MAX_HOST}, "
                        f"cur equal); hash {pre_hash}; desyncSeen host/client {pre_ds} (want False/False)")}
    pre_cur = uh[C1_ID].get("armorCur")
    ev["preC1"] = {"host": [pre_cur, uh[C1_ID].get("armorMax")], "client": [uc[C1_ID].get("armorCur"), uc[C1_ID].get("armorMax")]}
    ev["tu"] = tu_both(host, client, H1_ID)
    ev["hold"] = host.ok({"cmd": "resync_hold", "on": True})
    seq0 = event_state(host).get("lastSeqEmitted") or 0
    host.ok({"cmd": "set_seed", "seed": SEED_B4})
    t0 = time.time()
    ev["fire"] = host.cmd({"cmd": "battle_fire", "unit": H1_ID, "mode": "aimed", "x": C1_TILE[0], "y": C1_TILE[1],
                           "z": C1_TILE[2], "tu": 255})
    win = []
    while time.time() - t0 < WINDOW_S:
        win.append(sample(host, client, t0))
        time.sleep(0.1)
    end_t = round(time.time() - t0, 3)
    uh1, uc1 = ub(host), ub(client)
    end = {"host": uh1[C1_ID].get("armorCur"), "client": uc1[C1_ID].get("armorCur"), "clientMax": uc1[C1_ID].get("armorMax")}
    hashed = hash_now(host, client)
    end_ds = [event_state(host).get("desyncSeen"), event_state(client).get("desyncSeen")]
    crash = sorted(session._crash_log_snapshot() - crash0)
    ev.update(window={"start": 0.0, "end": end_t, "n": len(win), "consistent": sum(1 for s in win if s["consistent"])},
              samples=[[s["t"], s["host"], s["client"], s["consistent"], s["desync"]] for s in win], windowEnd=end,
              health=[uh1[C1_ID].get("health"), uc1[C1_ID].get("health")], status=[uh1[C1_ID].get("status"),
                                                                                    uc1[C1_ID].get("status")],
              evs=[(e.get("seq"), e.get("kind")) for e in (host.cmd({"cmd": "event_log", "tail": 40}).get("events") or [])
                   if (e.get("seq") or 0) > seq0],
              desyncFrozen=[(gc.cmd({"cmd": "battle_state"}).get("authority") or {}).get("desyncFrozen") for gc in (host, client)],
              dialog=[gc.cmd({"cmd": "coop_dialog_info"}) for gc in (host, client)])
    ev["release"] = host.ok({"cmd": "resync_hold", "on": False})
    full = ev["window"]["end"] >= WINDOW_S and len(win) >= MIN_SAMPLES
    changed_at = next((s["t"] for s in win if s["host"] != pre_cur), None)
    hc = end["host"] or []
    above = len(hc) == len(ARMOR_BASE) and all(hc[k] > ARMOR_BASE[k] for k in range(len(hc)))
    differ = [[s["t"], s["host"], s["client"]] for s in win if s["consistent"] and s["host"] != s["client"]]
    ds_at = next((s["t"] for s in win if any(s["desync"])), None)
    cells["B4-hit"] = (changed_at is not None and above and full,
                       f"host C1 armorCur {pre_cur} -> {hc} first changed at {changed_at} s (want a change in the window); "
                       f"every side above ARMOR_BASE {ARMOR_BASE} {above}; window 0.0-{end_t} s, {len(win)} samples "
                       f"(want >= {WINDOW_S} s, >= {MIN_SAMPLES})")
    cells["B4-armor"] = (full and not differ and end["host"] == end["client"],
                         f"C1 armorCur at the window end host {end['host']} client {end['client']} (want equal; client max "
                         f"{end['clientMax']}); seq-consistent samples differing [t, host, client] {differ[:4]} "
                         f"(want none of {ev['window']['consistent']})")
    cells["B4-hash"] = (full and hashed == "all buckets EQUAL" and ds_at is None and end_ds == [False, False] and not crash,
                        f"hash at the window end {hashed}; desyncSeen first true at {ds_at} s, at the end host/client "
                        f"{end_ds} (want never); new crash files {crash} (want none)")
    return cells, ev


def boot_m():
    host = GameClient("host", None, make_user_dir("r5u8bf_m_host", mods=[MOD_DIR]))
    client = GameClient("client", None, make_user_dir("r5u8bf_m_client", mods=[MOD_DIR]))
    try:
        try:
            boot, crash0 = bring_up(host, client)
        except Miss:
            return fail_all(ROWS, "boot (FIXTURE-STOP, see the CAPTURE M line)")
        try:
            staged = stage(host, client)
        except Miss:
            return fail_all(ROWS, "staging (see the CAPTURE M staging line)")
        try:
            cells, ev = row_b4(host, client, staged, crash0)
        except Exception as e:
            cells, ev = {}, {"error": f"{type(e).__name__}: {str(e)[:600]}"}
            try:
                host.cmd({"cmd": "resync_hold", "on": False})
            except Exception:
                pass
        ev["boot"] = {k: boot.get(k) for k in ("gm2", "lobbyGamemode", "pinned", "settle")}
        return verdict("B4", dict(ROWS)["B4"], cells, ev)
    finally:
        shut(host, client)


def main():
    t0 = time.time()
    fails = boot_m()
    print("ALL ROWS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_r5_pve2_armor_mod: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
