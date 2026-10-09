"""W2-H13 (D220 b; spec rewrite/prompts/w2h13_udp_rejoin_spare.md (f); F3701, F3702). Boot UB: rendezvous_stub.py
carries a HOST > PUBLIC skirmish over UDP; the client joins via join_rendezvous. U1: the client leaves, the host
keeps the paused battle and re-lists. U2: client2 joins the re-listed room, RESUME, equal state. FIXTURE-STOP on a
staging miss. Verdicts follow the teardown (H13-T1, F4565). WV-D95/D99/D100: ONE run; exit 0 only all PASS, else 2.
U3 (W2-H24 S-B, docs rewrite/prompts/w2h24_failed_battle_start.md AMENDMENT H24-2 section 2, D259 (a), QH24-3 (a), F9980;
TASK 0 rewrite/w2h24-task0/sb/CONSTANTS.md T0-B2): its own boot after U1 / U2's teardown on the same stub (key 48583,
w2h24_u3_host / _client): the client's hold_battle_ready keeps the host in Handshake, the client is killed, the host is
observed for W_U. U3-1 RED UNWIND +1 "(partner dropped)", U3-2 RED the host on a bare main menu with the session ended
(as a refused skirmish start), U3-3 GUARD CRASH 0 under H13-T1 (after U3's teardown). Red: U1, U2 PASS; U3 FAIL U3-1, U3-2."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, EXE
import session
from session import assert_hash_clean, battle_state, event_state
from test_skirmish_rejoin_battle import (drop_client_mid_battle, dialog, in_battle_save, top, settle_on_tactical,
                                         clear_popups, COOP_DLG_WAIT_PLAYERS, COOP_DLG_CLIENT_RESUME_HOLD)
from repro_atom_kneel import skirmish_client_at_browser
from rendezvous_stub import RendezvousStub

PORT_U13 = "48511"             # this file's lobby key (in-process only; the host binds an ephemeral UDP port)
REFUSAL = "offerRejoinBattle() called while the battle is not paused"
HOST_TERM_RC = 0xC0000409      # H13-T1 (F4565)
TERM_LINE = "std::terminate called (no active exception)."
CRASH_HEAD = ("==== Crash/Log", "Time:", "Version:", "Compiled:", "Module:", "ImageBase:", "Mods:")
from harness import CRASH_DIR  # noqa: E402  (W2-U8h F9563: this lane's own crash folder)
COOP_KEYS = ("udpActive", "rendezvousActive", "onConnect", "coopSession", "inBattle")
IDLE_S = 30
U3_KEY = "48583"               # W2-H24 S-B row U3's lobby key (in-process only)
W_U = 35.0                     # U3's window: TASK 0 T0-B2 read the UDP loss at 17.4 s after the kill; + 15 s, up to 5 s
UNWIND, UNMARKED = "W2-H24: failed battle start (", "battle marks cleared=0, crafts sent home=0"

class FixtureMiss(Exception):
    pass

def short(e, n=300):
    s = str(e).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."

def evidence(rid, obj):
    print(f"EVIDENCE {rid}: {json.dumps(obj, sort_keys=True, default=str)}", flush=True)

def need(value, msg):
    if not value:
        raise AssertionError(msg)
    return value

def coop(gc):
    return {k: v for k, v in gc.cmd({"cmd": "get_coop"}).items() if k in COOP_KEYS}

def auth(gc):
    bs = battle_state(gc)
    return bs.get("phase"), (bs.get("authority") or {})

def log_lines(gc, needle):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "r", encoding="utf-8", errors="replace") as f:
            return [ln.rstrip() for ln in f if needle in ln]
    except OSError:
        return []

def stub_report(stub, tag):
    """Event counts plus every event but the per-frame tcp_in/tcp_out and repeat verified UDP_REGISTERs."""
    evs = stub.events()
    counts = {k: sum(1 for e in evs if e["ev"] == k) for k in {e["ev"] for e in evs}}
    print(f"{tag} counts={json.dumps(counts, sort_keys=True)}", flush=True)
    for e in evs:
        if not (e["ev"] in ("tcp_in", "tcp_out") or (e["ev"] == "UDP_REGISTER" and e.get("hmac") == "ok"
                                                     and not e.get("first"))):
            print(f"  {tag} " + json.dumps({k: v for k, v in e.items() if k not in ("msg", "req")}, sort_keys=True))

def probe(fn, gc):
    try:
        v = fn(gc)
        return {a: b for a, b in v.items() if not (isinstance(b, list) and len(b) > 20)} if isinstance(v, dict) else v
    except Exception as e:
        return f"probe failed: {short(e)}"

def capture(name, err, machines, stub):
    """FIXTURE-STOP record: each machine's battle_state (lists > 20 dropped), get_coop, dialog, stack; stub events."""
    cap = {gc.name: {k: probe(fn, gc) for k, fn in (("stack", session.states), ("battle_state", battle_state),
                                                    ("get_coop", lambda g: g.cmd({"cmd": "get_coop"})),
                                                    ("dialog", dialog))} for gc in machines}
    print(f"CAPTURE {name} (missed: {err}): {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
    stub_report(stub, "CAPTURE-STUB")

def staging(ctx, name, err, machines, stub):
    capture(name, err, machines, stub)
    ctx["staging"] = f"{name}: {err}"
    return [f"staging: {ctx['staging']}"]

def step(name, fn, machines, stub):
    try:
        return fn()
    except Exception as e:
        capture(name, short(e, 800), machines, stub)
        raise FixtureMiss(f"{name}: {short(e, 400)}")

def host_public(host, port):
    """HOST > PUBLIC on lobby key `port` -> LobbyMenu (<= 60 s)."""
    for c, state in (("open_new_battle", "NewBattleState"), ("newbattle_coop", "ServerList"),
                     ("server_list_host", "HostMenu")):
        host.ok({"cmd": c})
        host.wait_for(f"host {state}", lambda state=state: session.has_state(host, state))
    host.ok(dict(cmd="host_menu_host", visibility=2, server="TestSrv", port=port, player="HostPlayer"))
    host.wait_for("host lobby", lambda: session.has_state(host, "LobbyMenu"), timeout=60)

def stage_boot(host, client, stub, ctx):
    """Boot UB (f) steps (1)-(6); the stub and OXC_RENDEZVOUS_CONFIG are up before this runs (main)."""
    m = (host, client)
    def to_battle():
        for gc in m:
            gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=90)
            gc.ok({"cmd": "profile_ok"})
        host.wait_for("BATTLE SETTINGS offered", lambda: host.cmd({"cmd": "lobby_state"}).get("buttonVisible") or None)
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host off LobbyMenu", lambda: (not session.has_state(host, "LobbyMenu")) or None)
        host.ok({"cmd": "set_seed", "seed": 1})
        host.ok({"cmd": "newbattle_ok"})
        for gc in m:
            gc.wait_for(f"{gc.name} in the battle", lambda gc=gc: in_battle_save(gc) or None, timeout=180, interval=1.0)
        settle_on_tactical(((host, "host"), (client, "client")))
    def active():
        for gc in m:
            gc.wait_for(f"{gc.name} Active", lambda gc=gc: auth(gc)[0] == "Active" or None, timeout=60, interval=0.5)
        hc = coop(host)
        need(hc.get("udpActive") is True and hc.get("onConnect") == 1, f"host get_coop {hc}")
        ready = sorted(e["to"] for e in stub.events("PEER_READY") if e["room"] == ctx["room1"] and e["sent"])
        need(ready == ["ClientPlayer", "HostPlayer"], f"stub PEER_READY for room1 sent to {ready} (want both)")
        ha, ca = auth(host)[1], auth(client)[1]
        ctx["B0"] = need(ha.get("battleId"), f"host battleId {ha.get('battleId')}")
        need(ca.get("battleId") == ctx["B0"], f"B0: host battleId {ctx['B0']} != client {ca.get('battleId')}")
        session.wait_host_idle(host, client, timeout=IDLE_S)
        assert_hash_clean(host, client, full=True, what="Boot UB")
        evidence("boot", {"room1": ctx["room1"], "B0": ctx["B0"], "stub": [stub.tcp_port, stub.udp_port],
                          "mapFingerprint": {"host": battle_state(host).get("mapFingerprint"),
                                             "client": battle_state(client).get("mapFingerprint")},
                          "hostCoop": hc, "clientCoop": coop(client), "peerReady": ready, "hash": "clean (full)"})
    step("(1) host and client spawn and connect", lambda: [(gc.spawn(), gc.connect()) for gc in m], m, stub)
    step("(2) host HOST > PUBLIC -> LobbyMenu (<= 60 s)", lambda: host_public(host, PORT_U13), m, stub)
    ctx["room1"] = step("(3) room1 = stub.wait_room(HostPlayer, 30 s)", lambda: need(
        stub.wait_room("HostPlayer", timeout=30), "no room by HostPlayer within 30 s"), m, stub)
    step("(4) client join_rendezvous room1", lambda: (skirmish_client_at_browser(client), client.ok(
        {"cmd": "join_rendezvous", "room": ctx["room1"], "player": "ClientPlayer"})), m, stub)
    step("(5) profile_ok, lobby_action, set_seed 1, newbattle_ok, both in the battle, settle", to_battle, m, stub)
    step("(6) both Active, host udpActive + onConnect 1, PEER_READY to both, B0, hash clean", active, m, stub)

def u1(host, client, stub, ctx):
    try:
        drop_client_mid_battle(host, client)
    except Exception as e:
        return staging(ctx, "U1 drop_client_mid_battle", short(e, 800), (host, client), stub)
    (phase, a), d, hc = auth(host), dialog(host), coop(host)
    ctx["room2"] = room2 = stub.wait_room("HostPlayer", after=ctx["room1"], timeout=30)
    evidence("U1", {"phase": phase, "authority": a, "B0": ctx["B0"], "hostCoop": hc, "relist": room2,
                    "hostCoopAfterRelist": coop(host),
                    "dialog": {k: d.get(k) for k in ("present", "code", "title", "backVisible", "backText")}})
    if phase == "Idle" and a.get("battleId") == 0:
        return ["UDP leave reset the paused battle (host phase Idle, battleId 0)"]
    f = [] if phase == "Active" and a.get("battleId") == ctx["B0"] else [
        f"host phase {phase} battleId {a.get('battleId')} (want Active, B0 {ctx['B0']})"]
    f += [f"host {k} {a.get(k)} (want true)" for k in ("hostSim", "peerAbsent", "peerLeftByChoice")
          if a.get(k) is not True]
    title = d.get("title") or ""
    if d.get("code") != COOP_DLG_WAIT_PLAYERS or "has left the battle" not in title or "reconnect" not in title:
        f.append(f"host dialog code {d.get('code')} title {title!r} (want {COOP_DLG_WAIT_PLAYERS}, "
                 "'has left the battle' + 'reconnect')")
    return f + ([] if room2 else ["no relisted room by HostPlayer within 30 s"])

def u2(host, client, stub, ctx):
    m, f = [host], []
    def wait(desc, gc, pred, timeout=120):
        try:
            return gc.wait_for(desc, pred, timeout=timeout, interval=0.5) and True
        except Exception as e:
            return f.append(short(e)) or False
    if not ctx.get("room2"):
        return staging(ctx, "U2 room2 = stub.wait_room(HostPlayer, after=room1, 30 s)", "no room2 within 30 s", m, stub)
    l0 = len(log_lines(host, REFUSAL))
    client2 = ctx["client2"] = GameClient("rejoin", None, make_user_dir("w2h13_udp_rejoin"))
    m.append(client2)
    try:
        client2.spawn()
        client2.connect()
        skirmish_client_at_browser(client2)
        client2.ok({"cmd": "join_rendezvous", "room": ctx["room2"], "player": "ClientPlayer"})
    except Exception as e:
        return staging(ctx, "U2 client2 spawn, browser, join_rendezvous room2", short(e, 800), m, stub)
    outcome, refusals, deadline = "timeout", [], time.time() + 120
    while outcome == "timeout" and time.time() < deadline:   # poll the host log each 1 s: fail early on L0+1
        refusals = log_lines(host, REFUSAL)[l0:]
        outcome = "refused" if refusals else "in" if in_battle_save(client2) else time.sleep(1.0) or "timeout"
    c2in = in_battle_save(client2)
    rec = {"room2": ctx["room2"], "L0": l0, "outcome": outcome, "refusals": refusals, "client2InBattle": c2in,
           "hostAuth": auth(host), "hostCoop": coop(host), "client2Coop": coop(client2),
           "client2Stack": session.states(client2)}
    if outcome != "in":
        evidence("U2", rec)
        if outcome == "timeout":
            return staging(ctx, "U2 client2 in the battle (<= 120 s)", "no refusal line, client2 not in the battle",
                           m, stub)
        return (["rejoin refused (phase Idle)"] if not c2in and "(phase=0" in refusals[0]
                else [f"rejoin refused ({refusals[0][-160:]}; client2 in the battle {c2in})"])
    ok = (wait("client2 held on dialog 68 over BattlescapeState", client2, lambda: (
        session.has_state(client2, "BattlescapeState")
        and dialog(client2).get("code") == COOP_DLG_CLIENT_RESUME_HOLD) or None, timeout=60)
        and wait("host dialog offers RESUME", host, lambda: (  # the join's Profile popup sits over the dialog
            clear_popups(host), dialog(host).get("backVisible"))[1] or None))
    if ok:
        host.ok({"cmd": "coop_dialog_back"})
        ok = all(wait(f"{gc.name} top BattlescapeState", gc, lambda gc=gc: (top(gc) == "BattlescapeState") or None)
                 for gc in (host, client2))
    ok = ok and all(wait(f"{gc.name} phase Active", gc, lambda gc=gc: (auth(gc)[0] == "Active") or None)
                    for gc in (host, client2))
    if ok:
        try:
            session.wait_host_idle(host, client2, timeout=IDLE_S)
            assert_hash_clean(host, client2, full=True, what="after RESUME")
        except Exception as e:
            f.append(f"idle/hash after RESUME: {short(e, 500)}")
    (hp, ha), (cp, ca), hc = auth(host), auth(client2), coop(host)
    ds, late = [event_state(gc).get("desyncSeen") for gc in (host, client2)], log_lines(host, REFUSAL)[l0:]
    rec.update(phase=[hp, cp], hostAuthority=ha, client2Authority=ca, hostCoopAfter=hc, client2CoopAfter=coop(client2),
               desyncSeen=ds, refusalsAfter=late, hostDialog=dialog(host))
    evidence("U2", rec)
    f += [] if hp == cp == "Active" else [f"phase host {hp} client2 {cp} (want Active on both)"]
    f += [] if ha.get("peerAbsent") is False else [f"host peerAbsent {ha.get('peerAbsent')} (want false)"]
    f += [] if ha.get("battleId") == ca.get("battleId") == ctx["B0"] else [
        f"battleId host {ha.get('battleId')} client2 {ca.get('battleId')} (want B0 {ctx['B0']})"]
    f += [] if hc.get("udpActive") is True else [f"host udpActive {hc.get('udpActive')} (want true)"]
    f += [f"host refusal lines after L0: {late}"] if late else []
    if any(ds):
        from test_w2_delta_core import desync_record
        f.append(f"desyncSeen host/client2 {ds}: " + "; ".join(
            short(desync_record(gc, True), 600) for gc, seen in zip((host, client2), ds) if seen))
    return f

ROWS = (("U1", u1), ("U2", u2))

def u3(stub, out):
    """W2-H24 S-B row U3 on its own boot (same stub, after U1 / U2's teardown): a co-op skirmish start over UDP whose partner is
    killed while the host waits in Handshake. Fills `out` (machines, cells, EVIDENCE, CAPTURE); verdicts print after U3's teardown."""
    host = out["host"] = GameClient("host", None, make_user_dir("w2h24_u3_host"))
    client = out["client"] = GameClient("client", None, make_user_dir("w2h24_u3_client"))
    m, rec = (host, client), out.setdefault("ev", {})
    last = ([r["room_id"] for r in stub.rooms()] or [None])[-1]
    def to_handshake():
        for gc in m:
            gc.wait_for(f"{gc.name} join popup", lambda gc=gc: session.has_state(gc, "Profile"), timeout=90)
            gc.ok({"cmd": "profile_ok"})
        host.wait_for("BATTLE SETTINGS offered", lambda: host.cmd({"cmd": "lobby_state"}).get("buttonVisible") or None)
        host.ok({"cmd": "lobby_action"})
        host.wait_for("host off LobbyMenu", lambda: (not session.has_state(host, "LobbyMenu")) or None)
        host.ok({"cmd": "set_seed", "seed": 1})
        need(client.ok({"cmd": "hold_battle_ready", "on": True}).get("armed") is True, "client hold_battle_ready not armed")
        host.ok({"cmd": "newbattle_ok"})
        host.wait_for("host Handshake + client held", lambda: (auth(host)[0] == "Handshake" and client.cmd(
            {"cmd": "hold_battle_ready"}).get("held") is True) or None, timeout=60, interval=0.2)
    step("U3 (1) host and client spawn and connect", lambda: [(gc.spawn(), gc.connect()) for gc in m], m, stub)
    step("U3 (2) host HOST > PUBLIC -> LobbyMenu (<= 60 s)", lambda: host_public(host, U3_KEY), m, stub)
    room = step(f"U3 (3) room = stub.wait_room(HostPlayer, after={last}, 30 s)", lambda: need(
        stub.wait_room("HostPlayer", after=last, timeout=30), "no room by HostPlayer within 30 s"), m, stub)
    step("U3 (4) client join_rendezvous", lambda: (skirmish_client_at_browser(client), client.ok(
        {"cmd": "join_rendezvous", "room": room, "player": "ClientPlayer"})), m, stub)
    step("U3 (5) profile_ok, lobby_action, set_seed 1, hold armed, newbattle_ok, host Handshake + client held (<= 60 s)",
         to_handshake, m, stub)
    l0 = len(log_lines(host, UNWIND))
    rec.update(room=room, atKill={"auth": auth(host), "hostCoop": coop(host)})
    client.kill()
    tk, polls, detect = time.time(), [], None
    while time.time() - tk < W_U:
        st, (ph, a), oc = session.states_stripped(host), auth(host), host.cmd({"cmd": "get_coop"}).get("onConnect")
        detect = detect or (round(time.time() - tk, 2) if oc != 1 and ph == "Idle" else None)
        polls.append([round(time.time() - tk, 2), st, ph, oc])
        time.sleep(0.2)
    st, (ph, a), hc, d = session.states_stripped(host), auth(host), coop(host), dialog(host)
    has_save, unw = host.cmd({"cmd": "world_state"}).get("has_save"), log_lines(host, UNWIND)[l0:]
    rec.update(loss_read_s=detect, host={"stack": st, "phase": ph, "authority": a, "hostCoop": hc, "has_save": has_save,
               "dialog": {k: d.get(k) for k in ("present", "code", "title", "backVisible")}}, UNWIND=unw,
               polls=[p for i, p in enumerate(polls) if i == 0 or p[1:] != polls[i - 1][1:]])
    out["cells"] = {
        "U3-1": (len(unw) == 1 and "(partner dropped)" in unw[0] and UNMARKED in unw[0],
                 f'RED UNWIND +1 reading "(partner dropped)" and "{UNMARKED}" (red today: 0 lines, T0-B2)'),
        "U3-2": (st == ["MainMenuState"] and has_save is False and hc.get("coopSession") is False and hc.get("onConnect") == -1
                 and d.get("present") is False, "RED the host lands on a bare main menu, the session ended (D259 (a)): stack "
                 "['MainMenuState'], has_save false, coopSession false, onConnect -1, no coop dialog (red today: [BriefingState, "
                 "CoopState] 62, T0-B2)")}
    out["capture"] = {"host stack": st, "phase": ph, "authority": a, "get_coop": hc, "dialog": rec["host"]["dialog"], "UNWIND": unw,
                      "HL": [ln[-200:] for ln in log_lines(host, "") if "coop-handshake" in ln or "[coop" in ln][-15:]}

def teardown(host, client, client2):
    """client2, client: rc 0; then the host under ruling H13-T1. Returns (record, failures)."""
    rec, fails = {}, []
    crash_files = lambda: set(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else set()  # noqa: E731
    for gc in [g for g in (client2, client) if g is not None and g.proc is not None]:
        try:
            gc.shutdown()
        except Exception as e:
            fails.append(f"{gc.name} shutdown: {short(e)}")
        rec[gc.name] = gc.proc.returncode
    if host.proc is not None:
        before = crash_files()
        try:
            host.shutdown(expected_returncodes=(0, HOST_TERM_RC))
        except Exception as e:
            fails.append(f"host shutdown: {short(e)}")
        rc, new = host.proc.returncode, sorted(crash_files() - before)
        logs = [n for n in new if n.endswith(".log")]
        body = [ln.strip() for n in logs for ln in open(os.path.join(CRASH_DIR, n), "r", errors="replace").read()
                .splitlines() if ln.strip() and not ln.startswith(CRASH_HEAD)]
        dmps = [n for n in new if n.endswith(".dmp")] + [os.path.join(r, n) for r, _d, ns in os.walk(host.user_dir)
                                                         for n in ns if n.endswith(".dmp")]
        rec["host"] = {"rc": rc, "crashLogs": logs, "crashText": body, "dmps": dmps}
        fails += [f"host .dmp {dmps}"] if dmps else []
        if rc == HOST_TERM_RC and (len(logs) != 1 or body != [TERM_LINE]):
            fails.append(f"host rc 0xC0000409 with crash text {body} in {logs} (H13-T1 accepts only {TERM_LINE!r})")
    return rec, fails

def crash_set():
    return set(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else set()

def u3_verdict(o):
    """U3's EVIDENCE, cell lines and verdict, after U3's own teardown (H13-T1, F4565). Returns the failed cells."""
    trec, tf = o.get("teardown", ({}, ["no U3 teardown"]))
    evidence("U3", dict(o.get("ev", {}), staging=o.get("staging"), error=o.get("error"), crashRow=o.get("crashRow"),
                        teardown={"rc": trec, "failures": tf}))
    cells, fails = o.get("cells") or {}, []
    for cid in ("U3-1", "U3-2"):
        ok, label = cells.get(cid, (False, f"not reached ({o.get('staging') or o.get('error')})"))
        print(f"{'PASS' if ok else 'FAIL'} {cid} {label}", flush=True)
        fails += [] if ok else [cid]
    ok3 = not o.get("crashRow") and not tf
    print(f"{'PASS' if ok3 else 'FAIL'} U3-3 GUARD CRASH 0: no new crash file during the row ({o.get('crashRow')}) and U3's "
          f"teardown clean under H13-T1 ({tf})", flush=True)
    fails += [] if ok3 else ["U3-3"]
    if fails and o.get("capture"):
        print(f"CAPTURE U3: {json.dumps(o['capture'], sort_keys=True, default=str)}", flush=True)
    print("PASS U3" if not fails else "FAIL U3: " + " ".join(fails), flush=True)
    return fails

def main():
    t0, ctx, results, u3o = time.time(), {}, {}, {}
    hdir = make_user_dir("w2h13_udp_host")
    stub = RendezvousStub(dll_dir=os.path.dirname(EXE), log_path=os.path.join(hdir, "stub_events.jsonl")).start()
    os.environ["OXC_RENDEZVOUS_CONFIG"] = stub.write_config(os.path.join(hdir, "stub.json"))  # before ANY spawn
    host = GameClient("host", None, hdir)
    client = GameClient("client", None, make_user_dir("w2h13_udp_client"))
    try:
        try:
            try:
                stage_boot(host, client, stub, ctx)
                ctx["booted"] = True
            except FixtureMiss as e:
                ctx["boot"] = str(e)
            for rid, fn in ROWS:
                if not ctx.get("booted") or ctx.get("staging"):
                    results[rid] = [f"boot (FIXTURE-STOP) {ctx['boot']}" if not ctx.get("booted")
                                    else f"staging ({ctx['staging']})"]
                    continue
                try:
                    results[rid] = fn(host, client, stub, ctx)
                except Exception as e:
                    capture(f"{rid} raised", short(e, 800), [g for g in (host, client, ctx.get("client2")) if g], stub)
                    results[rid] = [f"{type(e).__name__}: {short(e, 600)}"]
        finally:
            rec, tfails = teardown(host, client, ctx.get("client2"))
        cr3 = crash_set()                                   # W2-H24 S-B: U3 on its own boot, same stub
        try:
            u3(stub, u3o)
        except FixtureMiss as e:
            u3o["staging"] = str(e)
        except Exception as e:
            capture("U3 raised", short(e, 800), [g for g in (u3o.get("host"), u3o.get("client")) if g], stub)
            u3o["error"] = f"{type(e).__name__}: {short(e, 600)}"
        u3o["crashRow"] = sorted(crash_set() - cr3)
        if u3o.get("host") is not None:
            u3o["teardown"] = teardown(u3o["host"], u3o["client"], None)
    finally:
        stub.stop()                                         # after every shutdown (stub risk 4)
        os.environ.pop("OXC_RENDEZVOUS_CONFIG", None)
    stub_report(stub, "STUB")
    evidence("teardown", {"rc": rec, "failures": tfails})
    for rid, _fn in ROWS:
        results[rid] = list(results.get(rid, ["not run"])) + [f"teardown: {t}" for t in tfails]
        print(f"PASS {rid}" if not results[rid] else f"FAIL {rid}: " + "; ".join(results[rid]), flush=True)
    results["U3"] = u3_verdict(u3o)
    rows = [r for r, _fn in ROWS] + ["U3"]
    failed = [r for r in rows if results[r]]
    print(f"\ntest_w2_udp_rejoin: {len(rows) - len(failed)}/{len(rows)} passed (fail={failed}) in "
          f"{time.time() - t0:.1f}s", flush=True)
    return 0 if not failed else 2

if __name__ == "__main__":
    sys.exit(main())
