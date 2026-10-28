"""W2-H92 (owner D304 (a), 2026-10-20; trace docs rewrite/w2-resume-dafc8555/reports/cap-sepclock.md F24245-F24257; F24270-F24299):
a popup on the CLIENT stops the host's geoscape clock within one step, in SHARED and SEPARATE (F20500 / R-BH-1: geoscape time runs
only while both players are on the geoscape). Unchanged and not asserted here: dogfights keep time running, the host's own popups,
H23-VL1's client catch-up, the 1000 ms grace as the lost-heartbeat fallback, the speed buttons and the ally speed markers.
Mod Coop_PopupClock_Test on both machines: no alien mission in the first month, and STR_H92_IDLE (no waves) for P's landed UFO, so
the forced client popup is a row's only popup. Probe geo_clock (TEST-ONLY, read-only): one machine's clock to the second + its top.
One fresh boot pair per campaign mode (D297 (a)); each is ONE scenario at the fastest speed (both machines idx 5, one step = one game
day = 1440 min): a control stretch with no popup, then one client-only popup held HOLD_S (> the host's 1000 ms grace), then closed.
  S = SHARED: the host's shared_alert UfoLostState (SharedEcon::hostAlert; the host's own copy pops nothing) -> the client's
      alertApply popup (an apply-time popup).
  P = SEPARATE: a landed detected UFO on the host's base (spawn_ufo, STR_H92_IDLE), its mirror detected on the client, then the
      host's ufo_alert (the ctor broadcasts ufo_popup; the host shows nothing) -> the client's think-time UfoDetectedState (GS :1797).
Rows / cells (every sample reads the host first, then the client: a sampled lead is never larger than the true one):
  X-P0 control (S, P): with no popup on either machine for P0_S, each machine's fast time runs at P0_LO..P0_HI game minutes per wall
       second (the base's measured spread, R1; measured between the first and the last clock change), with >= P0_MIN_STEPS changes;
       GUARD: neither machine shows a popup in the window.
  X-P1 (S, P): from the host's last read before the client's popup push to the end of the hold, the host's clock advances by at
       most ONE step (P1-adv <= 1440 min) and changes at most once (P1-steps <= 1). GUARD: the host shows no popup of its own and the
       client's popup stays on top through the hold. Red at the base: the full-speed heartbeat sent with the popup queued credits the
       host a whole step, then the host walks one tick per step until the grace runs out.
  P-P2 (P only): from the client's pop until both run again (the client has caught up the host's held clock and the host has stepped
       again), the host's lead over the client never exceeds one step (<= 1440 min). Red at the base: the stale credit's step, then a
       second credited step while the client's first step after the pop walks 0 ticks (F24249), before its catch-up.
  S-P2 GUARD (S only): the host's clock runs again after the client's pop (the hold ends; passes at the base).
Red at the base (0b8bee213 + this file's probe): exit 2, RED exactly on S-P1-adv (1441.0), S-P1-steps (13), P-P1-adv (1440.917 ..
2880.917), P-P1-steps (12 .. 13), P-P2-lead (2881.0 .. 4320.917) (7 runs); every P0 and guard cell passes (S-P2-run: 41.9 ..
45.4 ms).
EVIDENCE then PASS / FAIL per cell; ONE run; every row runs after a failure; exit 0 only if all pass, else 2 (WV-D99 / WV-D100).
WV-D95: one foreground run per invocation.
Run: py -3 tools/coop_test/test_popup_clock.py
"""
import datetime
import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
from harness import GameClient, make_user_dir, shutdown_clients  # noqa: E402

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods", "Coop_PopupClock_Test")
BOOT_S = ("w2h92s", (49800, 49801, 47804))      # SHARED; lobby 47804
BOOT_P = ("w2h92p", (49802, 49803, 47806))      # SEPARATE; lobby 47806
SPEED, STEP_MIN = 5, 1440.0                      # idx 5 = one game day per step
WARM_S, P0_S, HOLD_S, PUSH_S, AFTER_S = 0.3, 1.0, 1.5, 5.0, 5.0
# P0 band (R1): at the base 0b8bee213 (+ this file's probe), 6 runs gave 24 rates of 16105.0 .. 17588.8 game min / wall s (the SHARED
# client, whose clock the host's heartbeat assigns, 16105.0 .. 17540.7; the other three 17168.3 .. 17588.8); band = min x 0.93 ..
# max x 1.07, rounded out to 100. A per-step wait for the other machine would halve the rate (one step per two timer fires).
P0_LO, P0_HI, P0_MIN_STEPS = 15000.0, 18900.0, 6
UFO = dict(type="STR_SMALL_SCOUT", mission="STR_H92_IDLE", region="STR_NORTH_AMERICA", race="STR_SECTOID", trajectory="P0",
           state="landed", hours=24 * 365)
EPOCH = datetime.datetime(1999, 1, 1)
OPTS = {"autosave": False}                        # no day-10 / day-20 geoscape autosave window inside a row


def short(e, n=500):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= n else s[:n] + "..."


def clock(gc):
    """(game minutes since 1999-01-01 as a float, top typeid tail, raw geo_clock reply)."""
    r = gc.cmd({"cmd": "geo_clock"})
    top = str(r.get("top", "")).split("::")[-1]
    if not r.get("ok"):
        return None, top, r
    d = datetime.datetime(r["year"], r["month"], r["day"], r["hour"], r["minute"], r["second"])
    return (d - EPOCH).total_seconds() / 60.0, top, r


def sample(x):
    t = time.time()
    hm, ht, hr = clock(x.host)
    cm, ct, cr = clock(x.client)
    return {"t": t, "h": hm, "c": cm, "hTop": ht, "cTop": ct, "hr": hr, "cr": cr}


def changes(rows, key):
    """[(t, minutes)] at every sample whose `key` clock differs from the previous sample's."""
    out, prev = [], None
    for s in rows:
        v = s[key]
        if v is not None and prev is not None and v != prev:
            out.append((s["t"], v))
        prev = v if v is not None else prev
    return out


def rate(rows, key):
    ch = changes(rows, key)
    if len(ch) < 2:
        return None, len(ch)
    (t0, m0), (t1, m1) = ch[0], ch[-1]
    return round((m1 - m0) / (t1 - t0), 1), len(ch)


def ms(t, t0):
    return round((t - t0) * 1000.0, 1)


class Row:
    def __init__(self, rid):
        self.rid, self.fails, self.ev, self.n = rid, [], {}, 0

    def cell(self, name, ok, detail):
        self.n += 1
        print(f"{'PASS' if ok else 'FAIL'} {self.rid}-{name}: {detail}", flush=True)
        if not ok:
            self.fails.append(name)
        return ok


def set_speed(x, idx):
    for gc in (x.host, x.client):
        gc.cmd({"cmd": "geo_set_speed", "idx": idx})


def run_scenario(x, mode, trigger, popup_type, results):
    """P0, then the client-only popup (P1), then its close (P2 in SEPARATE). Rows go to results[rid] = passed."""
    tag = "S" if mode == "shared" else "P"
    # ---- P0: fast time, no popup
    r0 = Row(f"{tag}-P0")
    set_speed(x, SPEED)
    time.sleep(WARM_S)
    rows, t0 = [], time.time()
    while time.time() - t0 < P0_S:
        rows.append(sample(x))
    tops = sorted({s["hTop"] for s in rows} | {s["cTop"] for s in rows})
    tops_by = {"host": sorted({s["hTop"] for s in rows}), "client": sorted({s["cTop"] for s in rows})}
    hr_, hn = rate(rows, "h")
    cr_, cn = rate(rows, "c")
    r0.ev = {"samples": len(rows), "hostRate": hr_, "hostChanges": hn, "clientRate": cr_, "clientChanges": cn, "tops": tops_by,
             "hStart": rows[0]["h"], "hEnd": rows[-1]["h"], "cEnd": rows[-1]["c"]}
    print(f"EVIDENCE {r0.rid}: {json.dumps(r0.ev, sort_keys=True)}", flush=True)
    r0.cell("guard", tops == ["GeoscapeState"], f"tops in the window {tops}")
    for who, rt, n in (("host", hr_, hn), ("client", cr_, cn)):
        r0.cell(f"{who}-rate", rt is not None and n >= P0_MIN_STEPS and P0_LO <= rt <= P0_HI,
                f"{who} {rt} game min / wall s over {n} changes (want {P0_LO}..{P0_HI}, >= {P0_MIN_STEPS} changes)")
    results[r0.rid] = not r0.fails
    # ---- P1: the client-only popup
    r1 = Row(f"{tag}-P1")
    pre = sample(x)
    tt = time.time()
    tr = trigger(x)
    rows = [pre]
    push_i = None
    while time.time() - tt < PUSH_S:
        s = sample(x)
        rows.append(s)
        if popup_type in s["cTop"]:
            push_i = len(rows) - 1
            break
    if push_i is None:
        r1.ev = {"trigger": tr, "lastTops": [rows[-1]["hTop"], rows[-1]["cTop"]]}
        print(f"EVIDENCE {r1.rid}: {json.dumps(r1.ev, sort_keys=True, default=str)}", flush=True)
        r1.cell("guard", False, f"no {popup_type} on the client within {PUSH_S} s of the trigger")
        results[r1.rid] = False
        return
    base_i = push_i - 1
    h_base = rows[base_i]["h"]
    t_push = rows[push_i]["t"]
    while time.time() - t_push < HOLD_S:
        rows.append(sample(x))
    hold = rows[base_i:]
    h_vals = [s["h"] for s in hold if s["h"] is not None]
    h_max = max(h_vals)
    host_ch = changes(hold, "h")
    host_tops = sorted({s["hTop"] for s in hold})
    client_tops = sorted({s["cTop"] for s in rows[push_i:]})
    last = rows[-1]
    r1.ev = {"trigger": {k: tr.get(k) for k in ("ok", "error", "type", "race", "ufo_id")}, "triggerToPushMs": ms(t_push, tt),
             "hBase": h_base, "hMax": h_max, "advMin": round(h_max - h_base, 3),
             "hostChanges": [(ms(t, t_push), round(m - h_base, 3)) for t, m in host_ch],
             "leadAtPush": None if rows[push_i]["c"] is None else round(rows[push_i]["h"] - rows[push_i]["c"], 3),
             "hostTops": host_tops, "clientTops": client_tops,
             "hostEnd": {k: last["hr"].get(k) for k in ("stepped", "peerAgeMs", "peerSpeed")},
             "clientEnd": {k: last["cr"].get(k) for k in ("hostTicks", "applied", "pending")}}
    print(f"EVIDENCE {r1.rid}: {json.dumps(r1.ev, sort_keys=True, default=str)}", flush=True)
    r1.cell("guard", host_tops == ["GeoscapeState"] and client_tops == [popup_type],
            f"host tops {host_tops}, client tops from the push {client_tops}")
    r1.cell("adv", h_max - h_base <= STEP_MIN,
            f"the host advanced {round(h_max - h_base, 3)} game min from its last read before the push to the hold's end (want <= {STEP_MIN})")
    r1.cell("steps", len(host_ch) <= 1, f"the host's clock changed {len(host_ch)} times after that read (want <= 1)")
    results[r1.rid] = not r1.fails
    # ---- the client closes its popup; P2 (SEPARATE) until both run again
    h_held = last["h"]
    d, _hit, on_geo = geo._walk(x.client)
    t_pop = time.time()
    rows2, done_i = [], None
    while time.time() - t_pop < AFTER_S:
        s = sample(x)
        rows2.append(s)
        if (done_i is None and s["c"] is not None and s["h"] is not None and s["c"] >= h_held and s["h"] > h_held):
            done_i = len(rows2) - 1
        if done_i is not None and time.time() - rows2[done_i]["t"] > 0.3:
            break
    win = rows2[:done_i + 1] if done_i is not None else rows2
    leads = [(s["t"], s["h"] - s["c"]) for s in win if s["h"] is not None and s["c"] is not None]
    peak = max(leads, key=lambda v: v[1]) if leads else (t_pop, None)
    ev2 = {"dismissed": d, "onGeo": on_geo, "hHeld": h_held, "bothRunMs": ms(rows2[done_i]["t"], t_pop) if done_i is not None else None,
           "peakLead": None if peak[1] is None else round(peak[1], 3), "peakAtMs": ms(peak[0], t_pop),
           "leadSeries": [(ms(t, t_pop), round(v, 1)) for t, v in leads][:: max(1, len(leads) // 40)],
           "hostChanges": [(ms(t, t_pop), round(m - h_held, 3)) for t, m in changes(win, "h")],
           "clientChanges": [(ms(t, t_pop), round(m - h_held, 3)) for t, m in changes(win, "c")]}
    rid2 = f"{tag}-P2"
    print(f"EVIDENCE {rid2}: {json.dumps(ev2, sort_keys=True, default=str)}", flush=True)
    r2 = Row(rid2)
    r2.cell("run", done_i is not None and on_geo, f"both run again {ev2['bothRunMs']} ms after the pop (popped {d}, geoscape on top {on_geo})")
    if mode == "separate":
        r2.cell("lead", peak[1] is not None and peak[1] <= STEP_MIN,
                f"the host's peak lead over the client from the pop until both run again {ev2['peakLead']} game min (want <= {STEP_MIN})")
    results[rid2] = not r2.fails


def shared_trigger(x):
    return x.host.cmd({"cmd": "shared_alert", "cls": "UfoLostState", "msg": "W2-H92"})


def boot_s():
    tag, ports = BOOT_S
    js = shared_fixture.bring_up(tag, ports, mods=(MOD,), host_options=OPTS, client_options=OPTS)
    return SimpleNamespace(host=js.host, client=js.client, shutdown=js.shutdown)


def boot_p():
    tag, (hp, cp, lp) = BOOT_P
    host = GameClient("host", hp, make_user_dir(f"{tag}_host", mods=(MOD,), options=OPTS))
    client = GameClient("client", cp, make_user_dir(f"{tag}_client", mods=(MOD,), options=OPTS))
    try:
        [f() for f in (host.spawn, client.spawn, host.connect, client.connect)]
        session.new_campaign(host, client, port=str(lp), campaign_mode="coop")
        geo.wait_both_ready(host, client)
    except BaseException:
        shutdown_clients(host, client)
        raise
    return SimpleNamespace(host=host, client=client, shutdown=lambda: shutdown_clients(host, client))


def stage_p(x):
    """A landed detected UFO on the host's base; wait for its detected mirror on the client. Returns the host's ufo id."""
    set_speed(x, 0)
    g = x.host.cmd({"cmd": "geo_state"})
    base = next(b for b in g["bases"] if not b.get("coopBase") and not b.get("coopIcon"))
    r = x.host.cmd({"cmd": "spawn_ufo", **UFO, "lon": base["lon"], "lat": base["lat"]})
    if not r.get("ok"):
        raise RuntimeError(f"spawn_ufo: {r}")
    t0 = time.time()
    while time.time() - t0 < 15.0:
        cu = [u for u in x.client.cmd({"cmd": "geo_state"}).get("ufos", []) if u.get("coop") and u.get("detected")]
        if cu:
            print(f"EVIDENCE P-stage: {json.dumps({'hostUfo': r.get('ufo_id'), 'clientMirror': cu[0], 'waitS': round(time.time() - t0, 2)}, default=str)}",
                  flush=True)
            return r["ufo_id"]
        time.sleep(0.1)
    raise RuntimeError("no detected mirror of the host's UFO on the client within 15 s")


def boot(name, up, body, rids, results, walls):
    t0, x = time.time(), None
    try:
        x = up()
        walls[name + " bring-up"] = round(time.time() - t0, 1)
        body(x, results)
    except Exception as e:
        print(f"CAPTURE {name}: {short(e, 3000)}", flush=True)
    finally:
        for rid in rids:
            if rid not in results:
                results[rid] = False
                print(f"FAIL {rid}: not reached", flush=True)
        try:
            if x is not None:
                geo.settle(x.host, x.client, speed_idx=0)
        except Exception as e:
            print(f"[w2h92] {name} settle: {short(e)}", flush=True)
        try:
            x is not None and x.shutdown()
        except Exception as e:
            print(f"[w2h92] {name} shutdown: {short(e)}", flush=True)
        walls[name] = round(time.time() - t0, 1)


def body_s(x, results):
    run_scenario(x, "shared", shared_trigger, "UfoLostState", results)


def body_p(x, results):
    uid = stage_p(x)
    run_scenario(x, "separate", lambda x: x.host.cmd({"cmd": "ufo_alert", "ufo_id": uid}), "UfoDetectedState", results)


def main():
    t0, results, walls = time.time(), {}, {}
    boot("S", boot_s, body_s, ("S-P0", "S-P1", "S-P2"), results, walls)
    boot("P", boot_p, body_p, ("P-P0", "P-P1", "P-P2"), results, walls)
    order = ("S-P0", "S-P1", "S-P2", "P-P0", "P-P1", "P-P2")
    failed = [rid for rid in order if not results.get(rid)]
    for rid in order:
        print(f"{'PASS' if results.get(rid) else 'FAIL'} {rid}", flush=True)
    print(f"\ntest_popup_clock: {len(order) - len(failed)}/{len(order)} passed (fail={failed}) walls {walls} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
