"""W2-H21 (R-H20bB-T0-1; F8598, F8599; spec rewrite/prompts/w2h21_restream_open_inventory_crash.md (f) as ruled by R-H21-T0-1 and
R-H21-R-1; TASK 0 rewrite/w2h21-task0/CONSTANTS.md): in SHARED, a world swap (a re-copy, or a battle start) that lands while the second
player's base inventory is open deletes the inventory's practice battle at once; the InventoryState is deleted a cycle later and its
destructor reads that deleted battle (T0-I, F8774 / F8775). Whether the read crashes depends on heap reuse (TASK 0, option OFF: craft
2/3, soldier 1/3, battle start 0/3; the first red run: re-copy 4/8, battle start 1/1), so ONE row repeats every path.
  H21-R (named red), 11 constructions, all run:
    k1..k3 battle start (Boot C ports, a fresh boot `w2h21c<k>` each): bring_up_shared_mixed_battle(js, None, to_tactical=False,
        pre_landing = the client's soldier inventory, h20.open_soldier_screen); non-vacuity: opened, CL `battle_offer accepted` then
        `pop  class OpenXcom::InventoryState`; poll 0.5 s up to 90 s. Lived: the client's stack holds BattlescapeState and BriefingState
        and no InventoryState / SoldiersState (it entered the battle), alive 2 s past that; the host alive; clean shutdown.
    k4..k11 re-copy (Boot A ports, boot `w2h21r<n>`, a fresh one after each crash): even k = the client's craft inventory
        (h20.open_craft_screen) + the CLIENT's force_resync (reply role replica, sent true); odd k = the client's soldier inventory
        (h20.open_soldier_screen) + the HOST's force_resync (role host). Non-vacuity: the screen on the client's stack, CL
        `push class OpenXcom::LoadGameState` then `pop  class OpenXcom::InventoryState`; poll 0.25 s up to W = 10 s. Lived: the
        client's stack == [GeoscapeState] within W (no inventory, no base screen, the hold box gone), alive 2 s past that, the host alive.
    RED: the client crashed in >= 1 of the 11 (counts per path; CRASH = the new crashlogs/crash_*.log, first 4 frames).
    GREEN: 0 of 11 crashed and every lived cell above passes, then js.finish() on the re-copy boot (both worlds equal, zero disk).
alive(gc) = the process runs and `ping` answers. CL = the client's openxcom.log after the size noted before the trigger. Setup guard
on every boot: h20.setup (option OFF on both, seats differ, H / C / C2 and SKY exist). A boot whose client crashed tolerates the
client's rc 3 at shutdown; a shutdown exception on a boot whose client lived fails the row. EVIDENCE before the verdict; a failed row
prints ONE CAPTURE line; ONE run (WV-D95); exit 0 iff the row passes, else 2.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import session  # noqa: E402
import shared_fixture  # noqa: E402
import test_w2_shared_base_equip as h20  # noqa: E402  (main-guarded)

PORTS_A, PORTS_C = (49482, 49483, 47942), (49486, 49487, 47944)
N_BATTLE, N_RECOPY, W, POLL, HOLD, W3, POLL3 = 3, 8, 10.0, 0.25, 2.0, 90.0, 0.5
GEO, INV = "GeoscapeState", "InventoryState"
PUSH_LGS, POP_INV = "push class OpenXcom::LoadGameState", "pop  class OpenXcom::InventoryState"
ACCEPT = "[coop-handshake] battle_offer accepted (battleId="
CRASH_DIR = harness.CRASH_DIR  # (W2-U8h F9563: this lane's own crash folder)
PATHS = ("battle start", "re-copy craft", "re-copy soldier")
q, stack, short = h20.q, h20.stack, h20.short


def alive(gc):
    return gc.proc is not None and gc.proc.poll() is None and bool(q(gc, {"cmd": "ping"}).get("pong"))


def log_size(gc):
    try:
        return os.path.getsize(os.path.join(gc.user_dir, "openxcom.log"))
    except OSError:
        return 0


def log_lines(gc, n0=0):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            f.seek(n0)
            txt = f.read().decode("utf-8", errors="replace")
    except OSError as e:
        return ["<%s>" % e]
    return [ln.rstrip("\r") for ln in txt.split("\n") if ln.strip()]


def ui(lines):
    """the screen record and the SHARED / handshake lines, message part only"""
    return [ln.split("\t")[-1] for ln in lines if "[coop-ui]" in ln or "[SHARED]" in ln or "[coop-handshake] battle_offer" in ln]


def crash_names():
    try:
        return set(os.listdir(CRASH_DIR))
    except OSError:
        return set()


def crash_info(before):
    """CRASH: every crash log written since `before`, with its first 4 frames"""
    out = []
    for name in sorted(crash_names() - before):
        if name.endswith(".log"):
            try:
                with open(os.path.join(CRASH_DIR, name), encoding="utf-8", errors="replace") as f:
                    fr = [ln.strip()[:150] for ln in f if ln.lstrip().startswith(("#0 ", "#1 ", "#2 ", "#3 "))]
            except OSError as e:
                fr = [str(e)]
            out.append({"file": name, "frames": fr[:4]})
    return out


def ordered(lines, first, then):
    i = next((k for k, ln in enumerate(lines) if first in ln), None)
    return i is not None and any(then in ln for ln in lines[i + 1:])


def capture(x, n_cl, crash):
    """both machines' stacks and shared_resync_stats, CL after n_cl, the host log's last 20 lines, CRASH"""
    return {"stacks": {gc.name: stack(gc) for gc in (x.host, x.client)},
            "shared_resync_stats": {gc.name: q(gc, {"cmd": "shared_resync_stats"}) for gc in (x.host, x.client)},
            "CL": ui(log_lines(x.client, n_cl))[-30:], "host log": log_lines(x.host)[-20:], "CRASH": crash}


class Row(h20.Row):
    def report(self, results):
        self.evidence()
        if self.fails:
            print(f"CAPTURE {self.rid}: {json.dumps(self.cap, sort_keys=True, default=str)}", flush=True)
        results[self.rid] = not self.fails
        print(f"PASS {self.rid}" if not self.fails else f"FAIL {self.rid}: " + " | ".join(self.fails), flush=True)


def boot(tag, ports, r):
    """bring_up + h20.setup -> (js, x); a miss fails the row's `boot` cell (its CAPTURE entry) and returns (None, None)."""
    js = x = None
    try:
        js = shared_fixture.bring_up(tag, ports)
        x = h20.X(js.host, js.client, js)
        h20.setup(x)
        r.x = x
        r.ev.setdefault("setup", {})[tag] = {"options": x.opts, "seats": x.seats, "H": x.H, "C": x.C, "C2": x.C2, "sky": x.sky}
        return js, x
    except Exception as e:
        r.cap["boot " + tag] = dict(capture(x, 0, []) if x is not None else {}, error=short(e, 1500))
        r.cell(f"boot {tag}", False, short(e, 300))
        if js is not None:
            end(js, r, "boot " + tag)
        return None, None


def end(js, r, what, died=False):
    """shut the boot down; a dead client's rc 3 is tolerated (its CRASH is the evidence), anything else fails `what` shutdown"""
    try:
        js.shutdown()
        return
    except Exception as e:
        msg = short(e, 300)
    if died and "host:" not in msg:
        r.ev.setdefault("shutdown, dead client (tolerated)", []).append(msg)
    else:
        r.cell(f"{what} shutdown", False, msg)


def poll(gc, t1, done, limit, interval):
    """(death time, time `done(stack)` first held); stops at the death, `done` held HOLD s, or `limit` s without it"""
    reached = None
    while True:
        now = time.time()
        if not alive(gc):
            return now, reached
        if reached is None and done(stack(gc)):
            reached = now
        if (reached and now - reached >= HOLD) or (not reached and now - t1 >= limit):
            return None, reached
        time.sleep(interval)


def ms(t, t1):
    return None if t is None else round((t - t1) * 1000)


def in_battle(s):
    return "BattlescapeState" in s and "BriefingState" in s and not ({INV, "SoldiersState"} & set(s))


def battle_start(r, k, c):
    """one battle-start construction on its own boot; returns (crashed, guard ok)"""
    js, x = boot("w2h21c%d" % k, PORTS_C, r)
    if js is None:
        return False, False
    pre, died, ok, n_f = {}, False, True, len(r.fails)
    try:
        def f(host, client):
            sol = q(client, {"cmd": "base_report", "base": h20.HB}).get("soldiers") or []
            pre["at base"] = [s.get("id") for s in sol if s.get("craft") == -1]
            pre["opened"] = h20.open_soldier_screen(r, client)
            pre["stack"] = stack(client)
            pre["n_cl"], pre["crashes"], pre["t"] = log_size(client), crash_names(), time.time()
        try:
            c["squad"] = session.bring_up_shared_mixed_battle(js, None, to_tactical=False, pre_landing=f)[2]
        except Exception as e:
            r.cell(f"G: k{k} bring_up_shared_mixed_battle", False, short(e, 600))
        c["pre_landing"] = {n: v for n, v in pre.items() if n in ("at base", "opened", "stack")}
        if not (pre.get("opened") and r.cell(f"G: k{k} the soldier inventory on the client's stack", pre["stack"][-1:] == [INV],
                                             pre["stack"])) or len(r.fails) > n_f:
            r.cap[f"k{k}"] = capture(x, pre.get("n_cl", 0), [])
            return False, False
        t1 = pre["t"]
        dead, reached = poll(x.client, t1, in_battle, W3, POLL3)
        if dead:
            time.sleep(0.5)  # the crash handler's files
        cl = log_lines(x.client, pre["n_cl"])
        c["CL"], died = ui(cl), dead is not None
        ok = r.cell(f"non-vacuity: k{k} CL battle_offer accepted then {POP_INV}", ordered(cl, ACCEPT, POP_INV), c["CL"])
        ok = r.cell(f"k{k}: the host died", x.host.proc.poll() is None, x.host.proc.poll()) and ok
        if died:
            c["crashed ms"], c["CRASH"] = ms(dead, t1), crash_info(pre["crashes"])
            r.cap[f"k{k} crash"] = capture(x, pre["n_cl"], c["CRASH"])
            return True, ok
        c["battle ms"], c["client stack"] = ms(reached, t1), stack(x.client)
        ok = r.cell(f"k{k}: the client never entered the battle (BattlescapeState + BriefingState, no inventory) within 90 s",
                    reached is not None, c["client stack"]) and ok
        if not ok:
            r.cap[f"k{k}"] = capture(x, pre["n_cl"], crash_info(pre["crashes"]))
        return False, ok
    finally:
        end(js, r, f"k{k}", died=died)


def recopy(r, x, k, c):
    """one re-copy construction on the live boot x; returns (crashed, guard ok)"""
    craft = c["path"] == "re-copy craft"
    base_screen = "CraftEquipmentState" if craft else "SoldiersState"
    opened = h20.open_craft_screen(r, x, x.client) if craft else h20.open_soldier_screen(r, x.client)
    c["stack before"] = st0 = stack(x.client)
    if not (opened and r.cell(f"G: k{k} the {c['path'][8:]} inventory on the client's stack", st0[-1:] == [INV] and base_screen in st0,
                              st0)):
        r.cap[f"k{k}"] = capture(x, 0, [])
        return False, False
    n_cl, before, trig = log_size(x.client), crash_names(), (x.client if craft else x.host)
    want = {"ok": True, "role": "replica", "sent": True} if craft else {"ok": True, "role": "host"}
    t1 = time.time()
    c["force_resync"] = rep = q(trig, {"cmd": "force_resync"})
    if not r.cell(f"non-vacuity: k{k} {trig.name} force_resync", all(rep.get(a) == b for a, b in want.items()), rep):
        r.cap[f"k{k}"] = capture(x, n_cl, [])
        return False, False
    dead, reached = poll(x.client, t1, lambda s: s == [GEO], W, POLL)
    if dead:
        time.sleep(0.5)  # the crash handler's files
    cl = log_lines(x.client, n_cl)
    c["CL"] = ui(cl)
    nv = r.cell(f"non-vacuity: k{k} CL {PUSH_LGS} then {POP_INV}", ordered(cl, PUSH_LGS, POP_INV), c["CL"])
    if dead:
        c["crashed ms"], c["CRASH"] = ms(dead, t1), crash_info(before)
        r.cap[f"k{k} crash"] = capture(x, n_cl, c["CRASH"])
        return True, nv
    c["geoscape ms"], c["client stack"] = ms(reached, t1), stack(x.client)
    ok = r.cell(f"k{k}: the client's {c['path'][8:]} inventory did not close to the geoscape within {W:.0f} s", reached is not None,
                c["client stack"])
    ok = r.cell(f"k{k}: the host died", x.host.proc.poll() is None, x.host.proc.poll()) and ok and nv
    if not ok:
        r.cap[f"k{k}"] = capture(x, n_cl, crash_info(before))
    return False, ok


def h21_r(results, walls):
    t0, r = time.time(), Row("H21-R", h20.X(None, None))
    js = x = None
    nboot, crashed = 0, []
    r.ev["constructions"] = cons = []
    try:
        for k in range(1, N_BATTLE + N_RECOPY + 1):
            path = PATHS[0] if k <= N_BATTLE else PATHS[1 + (k % 2)]
            c = {"k": k, "path": path}
            cons.append(c)
            if path == PATHS[0]:
                c["boot"] = "w2h21c%d" % k
                died, ok = battle_start(r, k, c)
            else:
                if js is None:
                    nboot += 1
                    js, x = boot("w2h21r%d" % nboot, PORTS_A, r)
                    if js is None:
                        return
                c["boot"] = "w2h21r%d" % nboot
                died, ok = recopy(r, x, k, c)
                if died:
                    end(js, r, f"k{k}", died=True)
                    js = x = None
            if died:
                crashed.append(k)
            if not ok or r.fails:
                return
        counts = {p: "%d/%d" % (sum(1 for c in cons if c["path"] == p and c.get("CRASH") is not None),
                                sum(1 for c in cons if c["path"] == p)) for p in PATHS}
        r.ev["crash counts"] = counts
        if not r.cell(f"the client crashed in {len(crashed)} of {len(cons)} constructions when a world swap landed on its open base "
                      f"inventory (F8598, F8669): " + ", ".join(f"{p} {n}" for p, n in counts.items()), not crashed,
                      [(c["k"], c["path"], c.get("crashed ms"), c.get("CRASH")) for c in cons if c.get("CRASH") is not None]):
            return
        try:
            js.finish()
        except AssertionError as e:
            r.cell("js.finish (both worlds equal, the replica's zero disk)", False, short(e, 1500))
    except Exception as e:
        r.cell("G: H21-R exception", False, short(e))
    finally:
        if js is not None:
            end(js, r, "H21-R")
        r.ev["re-copy boots"], r.ev["crashed"] = nboot, crashed
        walls["H21-R"] = r.ev["wall s"] = round(time.time() - t0, 1)
        r.report(results)


def main():
    t0, results, walls = time.time(), {}, {}
    h21_r(results, walls)
    failed = [rid for rid in ("H21-R",) if not results.get(rid)]
    print(f"\ntest_w2_restream_open_inventory: {1 - len(failed)}/1 passed (fail={failed}) walls {json.dumps(walls)} "
          f"in {time.time() - t0:.1f}s", flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
