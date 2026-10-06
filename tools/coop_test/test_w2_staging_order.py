"""W2-U8c: a host staging lever can ship a `reveal` ev in its frame (F6471), so a client-first pair waits on
session.wait_seq_barrier before the next client step (F6495); a settle wait reads the client before the host (F6561).
ONE run; EVIDENCE before each verdict; every row runs after a failure; exit 0 only when all pass, else 2. Cells: [named]
(the red), [guard] (red and green), [other]. U8c-4 guard / U8c-3: a fake pair vs wait_seq_barrier + wait_host_idle / the
10 settle waits V1-V6, V8-V11. U8c-G guard / U8c-1 / U8c-2 (Boots A / B / C): dc.both / session.place_deterministic /
bes.both under the client hold (the U8b stand-in, F8167). TASK 0: docs rewrite/w2u8c-task0/CONSTANTS.md (P1, P2)."""
import json
import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, shutdown_clients
import session
from session import event_state
import test_w2_delta_core as dc
import test_w2_client_shoot as cs
from test_w2_host_combat import bring_up_lobby_roster_pinned
import test_w2_battle_end_separate as bes
import test_w2_client_selection as csel
import test_w2_prebattle_equip as peq
import repro_door_deterministic as rdd
import repro_atom_turn as rat
import test_rw_feedback as rwf
import test_rw_retry_cancel as rwr
import test_rw_turn_mode as rwt

BOOTS = {"A": (49415, "47232"), "B": (49417, "47234"), "C": (49419, "47236")}   # labels, lobby (F8169)
HOLD_S, CALIBRATE, HELD_MIN_S, FAKE_TIMEOUT_S, OUTCOME_S = 3.0, 200, 1.0, 5, 6.0
A_AT = {"unit": cs.A_ID, "x": cs.A_TILE[0], "y": cs.A_TILE[1], "z": cs.A_TILE[2], "dir": cs.A_DIR}
TELE_A = dict(A_AT, cmd="battle_teleport_unit")
HEALTH_A = {"cmd": "battle_set_unit_state", "unit": cs.A_ID, "health": cs.A_HEALTH}
STAGE = ((TELE_A, ("to", "dir")), (HEALTH_A, ("health", "stun", "status")))   # A's teleport, then A's health
NAMED_1 = "session.place_deterministic let the client run on before it applied the host's reveal ev (F6495)"
NAMED_2 = ("test_w2_battle_end_separate.both let the next client lever run before the client applied the host's "
           "reveal ev (F6495, F6471)")


class FakeMachine:
    """One machine of a fake pair (no game): the host's pending reveal ships right after its first event_state
    answer; the client applies it on its third event_state read after the ship; every read is logged as served."""
    wait_for = GameClient.wait_for   # the harness poll itself
    ok = GameClient.ok

    def __init__(self, pair, name):
        self.pair, self.name = pair, name

    def cmd(self, obj):
        p, c = self.pair, obj.get("cmd")
        if self.name == "client" and c == "event_state" and p.applied < p.emitted:
            p.lag -= 1
            p.applied, p.lagged = (p.emitted, p.lagged) if p.lag < 0 else (p.applied, p.lagged + 1)
        p.log.append({"who": self.name, "cmd": c, "emitted": p.emitted, "applied": p.applied, "pending": p.pending})
        r = {("host", "event_state"): {"lastSeqEmitted": p.emitted, "lastSeqApplied": p.emitted, "phase": "Active",
                                       "coopDoorEvsEmitted": 1,
                                       "lastWalk": {"actionId": 2, "active": False, "restate": {"halted": False}}},
             ("client", "event_state"): {"lastSeqApplied": p.applied, "lastSeqEmitted": 0},
             ("host", "reveal_state"): {"unpublished": p.pending},
             ("host", "battle_state"): {"inBattle": True, "units": [], "isBusy": False, "pendingStates": 0},
             ("any", "get_state"): {"states": ["BattlescapeState"]}}.get(("any" if c == "get_state" else self.name, c))
        if r is None:
            raise RuntimeError(f"fake {self.name}: unexpected command {obj} (fixture error)")
        if c == "event_state":
            r.update(queueDepth=0, busyOwnerSeat=-1, desyncSeen=False)
        if self.name == "host" and c == "event_state" and not p.shipped:   # the reveal ships right after this answer
            p.emitted, p.pending, p.shipped, p.lag = p.emitted + 1, False, True, 2
        return dict(r, ok=True)


def poll(pred):
    def run(h, c):
        t0 = time.time()
        while time.time() - t0 < FAKE_TIMEOUT_S:
            if pred(h, c):
                return True
            time.sleep(0.01)
        return False
    return run


FAKE_GUARDS = (("session.wait_seq_barrier", lambda h, c: session.wait_seq_barrier(h, c, timeout=5), False),
               ("session.wait_host_idle", lambda h, c: session.wait_host_idle(h, c, timeout=5), True))
FAKE_WAITS = (("session.settle_reveal", lambda h, c: session.settle_reveal(h, c, timeout=5), True),
              ("repro_atom_turn.settle_reveal", lambda h, c: rat.settle_reveal(h, c, timeout=5), True),
              ("test_rw_feedback.settle_emits", lambda h, c: rwf.settle_emits(h, c, timeout=5), True),
              ("test_rw_retry_cancel.settle_emits", lambda h, c: rwr.settle_emits(h, c, timeout=5), True),
              ("test_rw_turn_mode.settle_emits", lambda h, c: rwt.settle_emits(h, c, timeout=5), True),
              ("session.wait_walk_settled", lambda h, c: session.wait_walk_settled(h, c, 1, timeout=5), False),
              ("test_w2_client_selection.caught_up", poll(csel.caught_up), False),
              ("test_w2_prebattle_equip.drained", poll(peq.drained), False),
              ("test_w2_battle_end_separate.chain_settled",
               lambda h, c: bes.chain_settled(h, c, stable=0.0, timeout=5, interval=0.05), False),
              ("repro_door_deterministic.wait_door_fired", lambda h, c: rdd.wait_door_fired(h, c, 0, timeout=5), False))


def fake_row(row, calls, guard_row):
    """A call's flag: U8c-4 - it must see a stale client (lagged >= 1); U8c-3 - a reveal-settle function."""
    fails = []
    for name, fn, flag in calls:
        pair = types.SimpleNamespace(emitted=7, applied=7, pending=True, shipped=False, lag=0, lagged=0, log=[])
        t0, err, res = time.time(), None, None
        try:
            res = fn(FakeMachine(pair, "host"), FakeMachine(pair, "client"))
        except Exception as e:
            err = dc.short(e, 200)
        seq = [x for x in pair.log if x["cmd"] in ("event_state", "reveal_state")]   # truth at the last seq read
        r = {"secs": round(time.time() - t0, 2), "err": err,
             "settled": err is None and res is not False and not (isinstance(res, tuple) and res[:1] == (False,)),
             "last": seq[-1] if seq else None, "shipped": pair.shipped, "lagged": pair.lagged, "reads": len(pair.log),
             "readSeq": " ".join(f"{x['who'][0]}:{x['cmd']}" for x in pair.log[-24:])}
        print(f"EVIDENCE {row} {name}: {json.dumps(r)}", flush=True)
        last = r["last"] or {}
        if not r["settled"] or r["secs"] > FAKE_TIMEOUT_S:
            fails.append(("guard", f"{name} did not return settled in {FAKE_TIMEOUT_S} s: {r['secs']} s {r['err']}"))
        if last.get("emitted") != last.get("applied"):
            fails.append(("guard" if guard_row else "named",
                          f"{name} returned while the client had not applied host seq {last.get('emitted')} "
                          f"(applied {last.get('applied')}) at its own last read: it reads the host first (F6561)"))
        if not guard_row and flag and last.get("pending") is not False:
            fails.append(("guard", f"{name} returned with the host's reveal pending at its last read: {last}"))
        if guard_row and (not r["shipped"] or (flag and r["lagged"] < 1)):
            fails.append(("guard", f"{name}: vacuous (shipped={r['shipped']} lagged={r['lagged']})"))
    return fails


def read_line(gc):
    while b"\n" not in gc.buf:
        chunk = gc.sock.recv(65536)
        if not chunk:
            raise ConnectionError(f"{gc.name}: socket closed")
        gc.buf += chunk
    line, gc.buf = gc.buf.split(b"\n", 1)
    return line


def held_send(self, obj):
    """GameClient._send, first dropping the answers owed to the probes; one-shot: holds the client after A's move."""
    st = self._hold
    owed, st["owed"] = st["owed"], 0
    t_send = time.time()
    self.sock.sendall((json.dumps(obj) + "\n").encode())
    for _ in range(owed):
        read_line(self)
    resp = json.loads(read_line(self))
    if owed and "afterHold" not in st["trace"]:
        st["trace"]["afterHold"] = {"cmd": obj.get("cmd"), "sentAfterHeldS": round(t_send - st["trace"]["heldAt"], 3),
                                    "answeredAfterS": round(time.time() - t_send, 3)}
    if st["armed"] and obj.get("cmd") == "battle_teleport_unit" and obj.get("unit") == cs.A_ID and resp.get("ok"):
        st["armed"] = False
        probe = (json.dumps({"cmd": "battle_state"}) + "\n").encode()
        tc = time.time()
        self.sock.sendall(probe * CALIBRATE)
        for _ in range(CALIBRATE):
            read_line(self)
        per = (time.time() - tc) / CALIBRATE
        n = max(CALIBRATE, int(HOLD_S / max(per, 1e-5)))
        t0 = time.time()
        self.sock.sendall(probe * n)   # the client's pump is busy from here ...
        read_line(self)                # ... once its first probe is answered
        st["owed"] = n - 1
        st["trace"].update({"perProbeMs": round(per * 1000, 3), "n": n, "firstAnswerS": round(time.time() - t0, 3),
                            "heldAt": time.time()})
    return resp


def arm_hold(client):
    client._hold = {"armed": True, "owed": 0, "trace": {}}
    client._send = types.MethodType(held_send, client)
    return client._hold["trace"]


def disarm_hold(client):
    if "_send" in vars(client):
        if client._hold["owed"]:
            client.cmd({"cmd": "battle_state"})
        del client._send


def es_keys(gc):
    e = event_state(gc)
    return {k: e.get(k) for k in session.SEQ_BARRIER_KEYS}


def capture(what, cap, host, client):
    for gc in (host, client):
        try:
            cap[gc.name] = es_keys(gc)
        except Exception as e:
            cap[gc.name] = dc.short(e, 120)
    print(f"CAPTURE {what}: {json.dumps(cap, default=str)}", flush=True)


def shutdown(host, client):
    try:
        shutdown_clients(host, client)
    except Exception as e:
        print(f"[w2u8c] shutdown: {dc.short(e)}", flush=True)


def boot(x):
    label, lobby = BOOTS[x]
    host = GameClient("host", label, make_user_dir(f"w2u8c_{x.lower()}_host"))
    client = GameClient("client", label + 1, make_user_dir(f"w2u8c_{x.lower()}_client"))
    t0 = time.time()
    try:
        bring_up_lobby_roster_pinned(host, client, lobby)
        seated = {}
        session.drive_to_battlescape(host, client, seated, mission=cs.MISSION, seat_count=2,
                                     pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": cs.SEED_MAP}))
        hs = session.battle_state(host)
        fp = (hs.get("mapFingerprint"), session.battle_state(client).get("mapFingerprint"))
        assert fp == (cs.MAP_FP, cs.MAP_FP), f"mapFingerprint host/client {fp} (baked {cs.MAP_FP!r})"
        sid = {u.get("soldierId"): u["id"] for u in hs["units"] if u.get("soldierId") is not None}
        seated_uids = [sid.get(s) for s in seated.get("soldierIds", [])]
        assert seated_uids == cs.SEATED, f"seated client units {seated_uids} (baked {cs.SEATED})"
        pinned = session.pin_ai_neutral(host, client, tag="w2u8c")
        assert pinned, "pin_ai_neutral pinned no NONE-seat non-player unit"
        session.wait_host_idle(host, client, timeout=30)
        session.assert_hash_clean(host, client, full=True, what="w2u8c boot")
        pc = cs.place(host, client, cs.C_ID, cs.C_TILE, cs.C16_C_DIR)
        c_on = [cs.upos(cs.units(g).get(cs.C_ID)) for g in (host, client)]
        assert c_on == [tuple(cs.C_TILE)] * 2, f"C on host/client {c_on}, want {cs.C_TILE} on both"
    except Exception as e:
        capture(f"boot {x}", {"error": dc.short(e), "wallS": round(time.time() - t0, 1)}, host, client)
        shutdown(host, client)
        return None, None, f"boot {x}: {dc.short(e)}"
    print(f"EVIDENCE boot {x}: wall {time.time() - t0:.1f}s ended {time.strftime('%H:%M:%S')} MAP_FP ok "
          f"seated={seated_uids} pinned={len(pinned)} C={pc} on {c_on}", flush=True)
    return host, client, None


def outcome(host, client, s0):
    """Poll until the client latched a desync or caught up (never a barrier here: a red client freezes)."""
    t0 = time.time()
    while time.time() - t0 < OUTCOME_S:
        c, h = event_state(client), event_state(host)
        if c.get("desyncSeen") or (c.get("lastSeqApplied") == h.get("lastSeqEmitted")
                                   and c.get("queueDepth") == 0 and h.get("queueDepth") == 0):
            break
        time.sleep(0.1)
    seen = bool(event_state(client).get("desyncSeen"))
    evs = [(e.get("seq"), e.get("kind")) for e in session.event_log(host, tail=40) if (e.get("seq") or 0) > s0]
    return {"outcomeS": round(time.time() - t0, 2), "clientDesync": seen,
            "hostDesync": bool(event_state(host).get("desyncSeen")), "desyncRecord": dc.desync_record(client, seen),
            "diffBuckets": dc.diff_buckets(host, client), "client": es_keys(client), "host": es_keys(host),
            "hostEvs": evs, "hostReveals": sum(1 for _, k in evs if k == "reveal")}


def construct(row, host, client):
    """U8c-G dc.both x2; U8c-1 place_deterministic (an AssertionError is recorded), then dc.both; U8c-2 bes.both x2."""
    raised, errs = None, []
    if row == "U8c-1":
        try:
            session.place_deterministic(host, client, [dict(A_AT, lever="battle_teleport_unit")], what="U8c-1")
        except AssertionError as e:
            raised = str(e)
    for req, keys in (STAGE[1:] if row == "U8c-1" else STAGE):
        if row == "U8c-2":
            rh, rc = bes.both(host, client, dict(req))
            errs += [] if rh.get("ok") and rc.get("ok") else [f"{req['cmd']}: host={rh} client={rc}"]
            continue
        try:
            dc.both(host, client, dict(req), keys)
        except Exception as e:
            errs.append(dc.short(e, 300))
    return {"raised": raised, "errors": errs}


def judge(row, info, out):
    """[] when clean; the named red only on its exact signature (U8c-1: TASK 0 P2 (i); U8c-2: the F6471 desync)."""
    if (not info["raised"] and not info["errors"] and not out["clientDesync"] and not out["hostDesync"]
            and out["diffBuckets"] == []):
        return []
    rec = out["desyncRecord"] or {}
    if (row == "U8c-1" and "HASH MISMATCH" in (info["raised"] or "") and not info["errors"]
            and not out["clientDesync"] and not out["hostDesync"] and out["diffBuckets"] == []):
        return [("named", NAMED_1)]
    if (row == "U8c-2" and out["clientDesync"] and rec.get("kind") == "reveal" and not out["hostDesync"]
            and not info["errors"]):
        return [("named", f"{NAMED_2}: client DESYNC bucket={rec.get('bucket')} seq={rec.get('seq')}")]
    return [("guard" if row == "U8c-G" else "other",
             f"outcome: raised={(info['raised'] or '')[:200]!r} errors={info['errors']} desync client="
             f"{out['clientDesync']} host={out['hostDesync']} record={rec} diff={out['diffBuckets']}")]


def live_row(row, x):
    host, client, err = boot(x)
    if err:
        return [("guard", err)]
    fails = []
    try:
        s0 = event_state(host).get("lastSeqEmitted") or 0
        trace = arm_hold(client)
        info = construct(row, host, client)
        out = outcome(host, client, s0)
        disarm_hold(client)
        print(f"EVIDENCE {row}: {json.dumps(dict(s0=s0, hold=trace, **info, **out), default=str)}", flush=True)
        if not (trace.get("heldAt") and (trace.get("n") or 0) >= CALIBRATE
                and ((trace.get("afterHold") or {}).get("answeredAfterS") or 0) >= HELD_MIN_S):
            fails.append(("guard", f"the hold did not fire or did not hold the next client command: {trace}"))
        if out["hostReveals"] < 1:
            fails.append(("guard", f"the host shipped no reveal ev after seq {s0}: {out['hostEvs']}"))
        fails += judge(row, info, out)
    except Exception as e:
        fails.append(("guard", f"{row} run: {dc.short(e)}"))
        capture(row, {"hold": getattr(client, "_hold", {}).get("trace")}, host, client)
    finally:
        shutdown(host, client)
    return fails


ROWS = (("U8c-4", lambda: fake_row("U8c-4", FAKE_GUARDS, True)),
        ("U8c-3", lambda: fake_row("U8c-3", FAKE_WAITS, False)),
        ("U8c-G", lambda: live_row("U8c-G", "A")),
        ("U8c-1", lambda: live_row("U8c-1", "B")),
        ("U8c-2", lambda: live_row("U8c-2", "C")))


def main():
    t0 = time.time()
    results, walls = {}, {}
    for name, fn in ROWS:
        tr = time.time()
        try:
            fails = fn()
        except Exception as e:
            fails = [("guard", f"row crashed: {dc.short(e)}")]
        walls[name], results[name] = round(time.time() - tr, 1), fails
        print(f"FAIL {name}: {len(fails)} cell(s)" if fails else f"PASS {name}", flush=True)
        for kind, msg in fails:
            print(f"  [{kind}] {msg}", flush=True)
    passed, failed = [n for n, _ in ROWS if not results[n]], [n for n, _ in ROWS if results[n]]
    print(f"\ntest_w2_staging_order: {len(passed)}/{len(ROWS)} rows passed (pass={passed} fail={failed}) "
          f"in {time.time() - t0:.1f}s (row walls {walls})", flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
