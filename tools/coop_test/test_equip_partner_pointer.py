"""test_equip_partner_pointer.py (EQP): the co-op partner's mouse pointer and name on the pre-battle equip
screen. each player sees the partner's pointer anywhere on the screen; D295 (a): the partner's name in small
text beside it; D293 (a): never between PvP opponents; D292 (a): never in battle. Spec: docs repo
rewrite/prompts/eq2a_pointer.md (f) and the common file rewrite/prompts/eq2_partner_pointer.md; rulings QEQ2-1 .. QEQ2-5 (a)
drawn whatever soldier either screen shows, raw position on the 320x200 Inventory surface, 50 ms rate / 1 s
keepalive / 3 s stale, the game's arrow and the name at (+10, +4) in the `weight` colour, the TEST-ONLY TestServer levers
`inject_input {kind motion}` and `cursor_pos`. Constants: docs repo rewrite/eq2-task0/sa/CONSTANTS.md (TASK 0 boots a, b, p
on HEAD + A12; c, pc with A1-A11).

Boot A (co-op, key KEY_A, dirs eq2a_a_host / eq2a_a_client): PBE's spine (test_prebattle_equip.py, copied, never
imported): the roster-pinned lobby, bring_up_to_briefings with SEED_MAP, MAP_FP, the client seated on C [8, 9], the host on
H [10..14]; the client closes its briefing first (its pre-battle screen on C1), then the host (its screen on its first
soldier). Rows in order:
  C2H   move(client, PT1); poll the host's presence up to W_PTR: C2H-sent, C2H-seen, C2H-drawn, C2H-name
  H2C   move(host, PT2); poll the client's presence up to W_PTR: H2C-drawn, H2C-name
  MOVE  move(client, PT3); poll the host up to W_PTR; rest REST_S: MOVE-follow, MOVE-rest, MOVE-quiet
  END   real OK (ready) presses, client then host; turn 1 on both; move(host, PT1); END_S: END-gone, END-quiet
  A     boot A's guards: A-pre (both screens up, phase open, different soldiers: QEQ2-1), A-motion (every move reached)
Boot P (PvP gm2, X-COM equipment for aliens on, key KEY_A after boot A's shutdown, dirs eq2a_p_host / eq2a_p_client):
RAE's boot DA (test_alien_equip.py, copied) to both pre-battle screens (the host X-COM, the client the alien seat).
  PVP   move(client, PT1), move(host, PT2); W_PTR: PVP-none, PVP-pre
move(gc, pt) = inject_input {kind motion} at ((invX + bx) * SCALE, (invY + by) * SCALE), then cursor_pos until it reads
(invX + bx, invY + by) within MOTION_S, else ONE CAPTURE line and the row fails "motion". A new state re-reads the OS mouse,
so every read follows its own motion. presence = event_state.equip.presence (absent = 0 / false).

RED on HEAD + A12 (commit R1, the partner pointer not built): C2H-sent, C2H-seen, C2H-drawn, C2H-name, H2C-drawn, H2C-name,
MOVE-follow, MOVE-rest, MOVE-quiet (9 of 15); A-pre, A-motion, END-gone, END-quiet, PVP-none, PVP-pre PASS.

One EVIDENCE line per row (both tops, both inventory_view briefs, both cursor_pos, both presence objects, CPU at the row
start), one PASS / FAIL line per cell, then the row verdict; every row runs after a failure (a precondition miss ends its own
row, its cells "not reached"); a boot step past its bound prints ONE CAPTURE line and fails that boot's rows "boot".
run in the foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell
passes, else 2.

Run:  python tools/coop_test/test_equip_partner_pointer.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
from test_host_combat import bring_up_lobby_roster_pinned  # noqa: E402
import test_battle_end_rules as BER  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402

# ----- pins (rewrite/eq2-task0/sa/CONSTANTS.md; no value needed its replacement rule) -----
KEY_A = "49283"                    # boot A, then boot P after boot A's shutdown
SEED_MAP = 1                       # PBE: set_seed right before newbattle_ok
MAP_FP = -4.48310638993e+18        # PBE: the host's mapFingerprint at SEED_MAP 1
C_IDS = [8, 9]                     # PBE: the client's seated units
H_IDS = [10, 11, 12, 13, 14]       # PBE: the host's own soldiers
SEED_PVP, MISSION_PVP = 1, "STR_SMALL_SCOUT"   # RAE boot DA
SCALE = 2                          # window 640x400 / the 320x200 logical screen (cursor_pos measured)
PT1, PT2, PT3 = (150, 120), (60, 150), (230, 60)   # on the Inventory surface; off OK / PREV / NEXT
CLIENT_NAME, HOST_NAME = "ClientPlayer", "HostPlayer"   # get_coop's peer field on host / client
NAME_DX, NAME_DY = 10, 4           # the name's top-left from the pointer's tip
MOTION_S, W_PTR, REST_S, MOVES_MAX = 1.0, 2.0, 3.0, 12
TURN_WAIT_S, END_S, POLL_S = 5.0, 2.0, 0.05
EQ1_WAIT_S, ENTRY_WAIT_S, SCREEN_S, ANSWER_WAIT_S, SAMPLE_S = 30.0, 5.0, 15.0, 3.0, 0.25
MOVES_A = 4                        # boot A's motions: C2H, H2C, MOVE, END
EXPECTED_RC = (0, 3221226505)
ROWS_A = (("C2H", ("C2H-sent", "C2H-seen", "C2H-drawn", "C2H-name")),
          ("H2C", ("H2C-drawn", "H2C-name")),
          ("MOVE", ("MOVE-follow", "MOVE-rest", "MOVE-quiet")),
          ("END", ("END-gone", "END-quiet")),
          ("A", ("A-pre", "A-motion")))
ROWS_P = (("PVP", ("PVP-none", "PVP-pre")),)
CPU_CSV = os.path.join(tempfile.gettempdir(), "eq2a_cpu_s%d.csv" % harness.HARNESS_SLOT)


# ===================== small probes (copied from PBE) =====================


def stack(gc):
    try:
        return session.states_stripped(gc)
    except Exception as e:  # a dead instance
        return [f"<no stack: {str(e)[:120]}>"]


def top(gc):
    s = stack(gc)
    return s[-1] if s else None


def has(gc, name):
    return any(name in s for s in stack(gc))


def es(gc):
    return event_state(gc)


def equip(gc):
    return es(gc).get("equip") or {}


def turn(gc):
    return battle_state(gc).get("turn")


def alive(gc):
    if gc.proc is None or gc.proc.poll() is not None:
        return False
    try:
        return bool(gc.cmd({"cmd": "ping"}).get("pong"))
    except Exception:
        return False


def inv_view(gc):
    r = gc.cmd({"cmd": "inventory_view"})
    if not r.get("ok"):
        return {"error": r.get("error"), "open": None}
    return {k: r.get(k) for k in ("open", "top", "unitId", "selectedItem", "preBattle", "okPressed", "lineText",
                                  "lineVisible")}


def screen_up(gc):
    v = inv_view(gc)
    return v.get("open") is True and v.get("top") is True and v.get("preBattle") is True


def wait_until(pred, timeout, interval=POLL_S):
    """Poll `pred` (bounded). Returns (value or None, seconds waited)."""
    t0 = time.time()
    while True:
        v = pred()
        if v:
            return v, round(time.time() - t0, 3)
        if time.time() - t0 > timeout:
            return None, round(time.time() - t0, 3)
        time.sleep(interval)


def ok_press(gc):
    r = gc.cmd({"cmd": "inventory_click", "widget": "ok"})
    return r.get("error") or r.get("ok")


# ===================== the pointer probes =====================


def cpos(gc):
    r = gc.cmd({"cmd": "cursor_pos"})
    return {k: r.get(k) for k in ("x", "y", "invX", "invY", "error")}


def pres(gc):
    """This machine's presence object (None when the build has none)."""
    return equip(gc).get("presence")


def look(host, client):
    """EVIDENCE: each machine's top, inventory_view brief, cursor_pos and whole presence object."""
    return {gc.name: {"top": top(gc), "view": inv_view(gc), "cursor": cpos(gc), "presence": pres(gc)}
            for gc in (host, client)}


def P(lk, name):
    return lk[name]["presence"] or {}


def drawn_at(gc, want):
    d = (pres(gc) or {}).get("drawn") or {}
    return d.get("ptr") is True and [d.get("x"), d.get("y")] == want


def sent(gc):
    return (pres(gc) or {}).get("ptrSent")


def cpu_now():
    """The newest typeperf sample (% total), or None."""
    try:
        with open(CPU_CSV, encoding="utf-8", errors="replace") as f:
            rows = [ln.strip() for ln in f if ln.strip()]
        return round(float(rows[-1].split(",")[1].strip('"')), 1) if len(rows) > 1 else None
    except (OSError, ValueError, IndexError):
        return None


def cpu_mean():
    v = []
    try:
        with open(CPU_CSV, encoding="utf-8", errors="replace") as f:
            for ln in list(f)[1:]:
                try:
                    v.append(float(ln.split(",")[1].strip().strip('"')))
                except (ValueError, IndexError):
                    pass
    except OSError:
        return None
    return round(sum(v) / len(v), 1) if v else None


def move(gc, ctx, pt):
    """inject_input motion at ((invX + bx) * SCALE, (invY + by) * SCALE); cursor_pos must read (invX + bx, invY + by)
    within MOTION_S, else ONE CAPTURE line and the row fails "motion"."""
    inv = ctx["inv"][gc.name]
    want = [inv[0] + pt[0], inv[1] + pt[1]]
    r = gc.cmd({"cmd": "inject_input", "kind": "motion", "x": want[0] * SCALE, "y": want[1] * SCALE})
    got, dt = wait_until(lambda: (lambda c: [c.get("x"), c.get("y")] == want)(cpos(gc)), MOTION_S)
    rec = {"machine": gc.name, "pt": list(pt), "want": want, "inject": r.get("error") or r.get("ok"),
           "reached": bool(got), "waited": dt, "cursor": cpos(gc)}
    ctx["moves"].append(rec)
    if not got:
        G3F.capture("motion", f"{gc.name} cursor {rec['cursor']} (want {want} within {MOTION_S} s)", ctx["m"])
        raise AssertionError(f"motion: {gc.name}'s cursor {rec['cursor']} after the motion (want {want} within "
                             f"{MOTION_S} s)")
    return rec


def miss(tag, what, m):
    G3F.capture(tag, what, m)
    raise G3F.Miss(tag)


def at_screens(ctx, host, client):
    """Both machines on their pre-battle screens: each Inventory's top-left (cursor_pos) and the boot record."""
    ci = {gc.name: cpos(gc) for gc in (host, client)}
    ctx["inv"] = {n: (c.get("invX"), c.get("invY")) for n, c in ci.items()}
    ctx["boot"].update(cursor=ci, views={gc.name: inv_view(gc) for gc in (host, client)},
                       phase=[equip(gc).get("phase") for gc in (host, client)],
                       seat=[(battle_state(gc).get("authority") or {}).get("localSeat") for gc in (host, client)],
                       stacks=[stack(host), stack(client)])
    ctx["seat"] = dict(zip(("host", "client"), ctx["boot"]["seat"]))


# ===================== boot A (PBE's spine, copied) =====================


def boot_a(host, client):
    m = (host, client)
    ctx = {"m": m, "moves": [], "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("A", lambda: bring_up_lobby_roster_pinned(host, client, KEY_A), m)
    seated = {}
    G3F.guarded("A", lambda: session.bring_up_to_briefings(
        host, client, seated, seat_count=2, pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    hb = battle_state(host)
    sid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    got = {"mapFingerprint": hb.get("mapFingerprint"), "seated": [sid.get(s) for s in seated.get("soldierIds", [])],
           "hIds": sorted(u["id"] for u in hb.get("units", []) if u.get("coop") == 0 and u.get("faction") == 0
                          and not u.get("isOut"))}
    ctx["boot"].update(got)
    if (got["mapFingerprint"], got["seated"], got["hIds"]) != (MAP_FP, C_IDS, H_IDS):
        miss("A", f"PBE's spine: {got} (want MAP_FP {MAP_FP}, seated {C_IDS}, H {H_IDS})", m)
    ok, ctx["boot"]["clientBriefingS"] = wait_until(lambda: has(client, "BriefingState"), EQ1_WAIT_S, 0.1)
    if not ok:
        miss("A", f"no client BriefingState within {EQ1_WAIT_S} s", m)
    ctx["boot"]["clientClose"] = client.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    if not ok:
        miss("A", f"the client's pre-battle screen not up within {ENTRY_WAIT_S} s after its briefing closed", m)
    ctx["boot"]["hostClose"] = host.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("A", f"the host's pre-battle screen not up within {SCREEN_S} s after its briefing closed", m)
    at_screens(ctx, host, client)
    b = ctx["boot"]
    units = [b["views"][n].get("unitId") for n in ("host", "client")]
    ctx["A-pre"] = (all(screen_up(gc) for gc in m) and b["phase"] == ["open", "open"] and units[0] != units[1],
                    f"screens up {[screen_up(gc) for gc in m]}, equip.phase {b['phase']} (want open on both), unitId "
                    f"host/client {units} (want different: QEQ2-1), Inventory top-left {ctx['inv']}")
    print(f"[eq2a] boot A: {json.dumps(b, sort_keys=True, default=str)}", flush=True)
    return ctx


def row_c2h(host, client, ctx, ev):
    ev["move"] = move(client, ctx, PT1)
    hi = ctx["inv"]["host"]
    want = [hi[0] + PT1[0], hi[1] + PT1[1]]

    def seen():
        p = pres(host) or {}
        pe = p.get("peer") or {}
        return drawn_at(host, want) and [pe.get("x"), pe.get("y")] == list(PT1)
    got, ev["within"] = wait_until(seen, W_PTR)
    lk = ev["look"] = look(host, client)
    ph, pc = P(lk, "host"), P(lk, "client")
    s, pe, d = pc.get("sent") or {}, ph.get("peer") or {}, ph.get("drawn") or {}
    absent = "" if pc and ph else f" (presence host {'present' if ph else 'absent'}, client {'present' if pc else 'absent'})"
    return {"C2H-sent": (s.get("on") is True and [s.get("x"), s.get("y")] == list(PT1) and (pc.get("ptrSent") or 0) >= 1,
                         f"client presence.sent {s}, ptrSent {pc.get('ptrSent')} (want on true at {list(PT1)}, ptrSent >= 1)"
                         + absent),
            "C2H-seen": (pe.get("seat") == ctx["seat"]["client"] and pe.get("on") is True
                         and [pe.get("x"), pe.get("y")] == list(PT1),
                         f"host presence.peer {pe} (want seat {ctx['seat']['client']}, on true, {list(PT1)} within {W_PTR} s; "
                         f"waited {ev['within']})" + absent),
            "C2H-drawn": (d.get("ptr") is True and [d.get("x"), d.get("y")] == want,
                          f"host drawn ptr {d.get('ptr')} at {[d.get('x'), d.get('y')]} (want true at {want})" + absent),
            "C2H-name": (d.get("name") == CLIENT_NAME and d.get("nameShown") is True
                         and [d.get("nameX"), d.get("nameY")] == [(d.get("x") or 0) + NAME_DX, (d.get("y") or 0) + NAME_DY],
                         f"host drawn name {d.get('name')!r} shown {d.get('nameShown')} at {[d.get('nameX'), d.get('nameY')]} "
                         f"(want {CLIENT_NAME!r} shown at the pointer + ({NAME_DX}, {NAME_DY}))" + absent)}


def row_h2c(host, client, ctx, ev):
    ev["move"] = move(host, ctx, PT2)
    ci = ctx["inv"]["client"]
    want = [ci[0] + PT2[0], ci[1] + PT2[1]]
    got, ev["within"] = wait_until(lambda: drawn_at(client, want), W_PTR)
    lk = ev["look"] = look(host, client)
    d = P(lk, "client").get("drawn") or {}
    absent = "" if P(lk, "client") else " (client presence absent)"
    return {"H2C-drawn": (d.get("ptr") is True and [d.get("x"), d.get("y")] == want,
                          f"client drawn ptr {d.get('ptr')} at {[d.get('x'), d.get('y')]} (want true at {want} within "
                          f"{W_PTR} s; waited {ev['within']})" + absent),
            "H2C-name": (d.get("name") == HOST_NAME and d.get("nameShown") is True,
                         f"client drawn name {d.get('name')!r} shown {d.get('nameShown')} (want {HOST_NAME!r} shown)" + absent)}


def row_move(host, client, ctx, ev):
    c0 = sent(client)
    ev["move"] = move(client, ctx, PT3)
    hi = ctx["inv"]["host"]
    want = [hi[0] + PT3[0], hi[1] + PT3[1]]
    got, ev["followWithin"] = wait_until(lambda: drawn_at(host, want), W_PTR)
    c1, h1 = sent(client), (pres(host) or {}).get("ptrRecv")
    samples, tr = [], time.time()
    while time.time() - tr < REST_S:
        samples.append(((pres(host) or {}).get("drawn") or {}).get("ptr"))
        time.sleep(SAMPLE_S)
    ev["restS"] = round(time.time() - tr, 2)
    c2, h2 = sent(client), (pres(host) or {}).get("ptrRecv")
    ev.update(clientPtrSent=[c0, c1, c2], hostPtrRecv=[h1, h2], hostDrawnSamples=samples)
    lk = ev["look"] = look(host, client)
    ints = all(isinstance(x, int) for x in (c0, c1, c2))
    rest, whole = (c2 - c1, c2 - c0) if ints else (None, None)
    d = P(lk, "host").get("drawn") or {}
    return {"MOVE-follow": (bool(got), f"host drawn ptr {d.get('ptr')} at {[d.get('x'), d.get('y')]} (want true at {want} "
                                       f"within {W_PTR} s: the newest position replaced {list(PT1)})"),
            "MOVE-rest": (rest is not None and REST_S - 1 <= rest <= REST_S + 1 and bool(samples)
                          and all(x is True for x in samples),
                          f"client ptrSent {c1} -> {c2} over the {ev['restS']} s rest (want +{REST_S - 1:g} .. "
                          f"+{REST_S + 1:g}: the 1 s keepalive); host drawn.ptr true in "
                          f"{sum(1 for x in samples if x is True)} of {len(samples)} samples (want all)"),
            "MOVE-quiet": (rest is not None and rest <= 1 + REST_S and whole <= MOVES_MAX,
                           f"client ptrSent +{rest} over the rest (want <= {1 + REST_S:g}), +{whole} over the row (want <= "
                           f"{MOVES_MAX}; ptrSent {c0} -> {c2})")}


def row_end(host, client, ctx, ev):
    m = (host, client)
    ev["clientOk"] = ok_press(client)
    _, ev["hostSawReadyS"] = wait_until(lambda: (equip(host).get("ready") or [None, None])[1] is True, ANSWER_WAIT_S)
    ev["hostOk"] = ok_press(host)
    got, ev["turn1Within"] = wait_until(lambda: turn(host) == 1 and turn(client) == 1, TURN_WAIT_S)
    at1 = {gc.name: sent(gc) or 0 for gc in m}
    ev["atTurn1"] = look(host, client)
    if not got:
        raise AssertionError(f"precondition: turn host/client {[turn(host), turn(client)]} {TURN_WAIT_S} s after both "
                             f"OK presses (want 1 on both)")
    ev["move"] = move(host, ctx, PT1)
    time.sleep(END_S)
    lk = ev["look"] = look(host, client)
    end = {gc.name: sent(gc) or 0 for gc in m}
    ev.update(ptrSent={"turn1": at1, "end": end}, phase=[equip(gc).get("phase") for gc in m],
              turn=[turn(host), turn(client)], hash=G3F.hash_now(host, client),
              desyncSeen=[es(gc).get("desyncSeen") for gc in m])
    up = alive(host)
    crash = sorted(session._crash_log_snapshot() - ctx["crash0"])
    dr = {n: (P(lk, n).get("drawn") or {}).get("ptr") for n in ("host", "client")}
    return {"END-gone": (not any(dr.values()), f"drawn.ptr host/client {dr} {END_S} s after turn 1 (want false / absent on "
                                               f"both: the screens closed)"),
            "END-quiet": (all(end[n] <= at1[n] + 1 for n in end) and up and not crash,
                          f"ptrSent at turn 1 {at1} -> {end} at +{END_S} s (want at most +1 each: one `on false`); host "
                          f"alive {up}; new crash files {crash} (want none)")}


def row_a(host, client, ctx, ev):
    mv = ctx["moves"]
    ev.update(boot=ctx["boot"], moves=mv)
    return {"A-pre": ctx["A-pre"],
            "A-motion": (len(mv) == MOVES_A and all(x["reached"] for x in mv),
                         f"{sum(1 for x in mv if x['reached'])} of {len(mv)} motions reached cursor_pos within {MOTION_S} s "
                         f"(want {MOVES_A} of {MOVES_A}: {[(x['machine'], x['want'], x['waited']) for x in mv]})")}


# ===================== boot P (RAE's boot DA, copied) =====================


def lobby_e6(host, client, key):
    """RAE's lobby_e6: the client joins and takes the Alien team (gamemode 2)."""
    BER.raw.skirmish_host(host, key)
    BER.raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": BER.raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: BER.raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, BER.raw.CLIENT_PLAYER), "team": "Alien"})
    time.sleep(1)   # the change_team broadcast settles on the client (PSR PHASE 0)
    return r.get("gamemode")


def drive_p(host, client):
    """RAE's drive: Small Scout, set_seed, newbattle_ok, both briefings up."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    r = host.cmd({"cmd": "newbattle_mission", "type": MISSION_PVP})
    assert r.get("ok"), f"newbattle_mission {MISSION_PVP}: {r}"
    host.ok({"cmd": "set_seed", "seed": SEED_PVP})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)


def boot_p(host, client):
    m = (host, client)
    ctx = {"m": m, "moves": [], "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("P", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded("P", lambda: host.ok({"cmd": "set_seed", "seed": SEED_PVP}), m)
    ctx["boot"]["gm"] = G3F.guarded("P", lambda: lobby_e6(host, client, KEY_A), m)
    G3F.guarded("P", lambda: drive_p(host, client), m)
    G3F.guarded("P", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("P", "the host's pre-battle screen never came up", m)
    G3F.guarded("P", lambda: session.dismiss_client_briefing(client), m)
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), SCREEN_S)
    if not ok:
        miss("P", f"the client's (alien seat) pre-battle screen not up within {SCREEN_S} s", m)
    at_screens(ctx, host, client)
    print(f"[eq2a] boot P: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_pvp(host, client, ctx, ev):
    ev["boot"] = ctx["boot"]
    ev["moves"] = [move(client, ctx, PT1), move(host, ctx, PT2)]
    time.sleep(W_PTR)
    lk = ev["look"] = look(host, client)
    ph, pc = P(lk, "host"), P(lk, "client")
    vals = {n: {"ptrSent": p.get("ptrSent") or 0, "drawn": bool((p.get("drawn") or {}).get("ptr"))}
            for n, p in (("host", ph), ("client", pc))}
    pre = ctx["boot"].get("gm") == 2 and all(screen_up(gc) for gc in (host, client))
    return {"PVP-none": (all(v == {"ptrSent": 0, "drawn": False} for v in vals.values()),
                         f"{vals} after {W_PTR} s (want ptrSent 0 and drawn.ptr false on both: D293 (a); absent = 0 / false)"),
            "PVP-pre": (pre and len(ev["moves"]) == 2,
                        f"gamemode {ctx['boot'].get('gm')} (want 2), both pre-battle screens up {pre}, motions reached "
                        f"{[x['reached'] for x in ev['moves']]}")}


# ===================== the run =====================


def run_row(row, order, fn, host, client, ctx):
    ev = {"cpu": cpu_now()}
    try:
        cells = fn(host, client, ctx, ev)
    except Exception as e:
        ev["error"] = f"{type(e).__name__}: {str(e)[:600]}"
        cells = {}
    return G3F.verdict(row, order, cells, ev)


def run_boot(tag, rows, setup, fns, host_dir, client_dir):
    """One boot: setup (a miss fails every row "boot"), then every row in order, each after any failure."""
    host = GameClient("host", None, make_user_dir(host_dir))
    client = GameClient("client", None, make_user_dir(client_dir))
    try:
        try:
            ctx = setup(host, client)
        except Exception as e:
            if not isinstance(e, G3F.Miss):
                G3F.capture(tag, f"{type(e).__name__}: {str(e)[:600]}", (host, client))
            return G3F.fail_all(rows, f"boot (setup failure, see the CAPTURE {tag} line)")
        return sum(run_row(row, order, fns[row], host, client, ctx) for row, order in rows)
    finally:
        rc = {}
        for gc in (host, client):
            try:
                if gc.proc is not None and gc.proc.poll() is None:
                    gc.shutdown(expected_returncodes=EXPECTED_RC)
                rc[gc.name] = gc.proc.returncode if gc.proc is not None else None
            except Exception as e:
                rc[gc.name] = f"shutdown: {type(e).__name__}: {str(e)[:200]}"
        print(f"[eq2a] boot {tag} shut down: {rc}", flush=True)


FN_A = {"C2H": row_c2h, "H2C": row_h2c, "MOVE": row_move, "END": row_end, "A": row_a}
FN_P = {"PVP": row_pvp}


def main():
    t0 = time.time()
    cpu = None
    try:
        cpu = subprocess.Popen(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-y", "-f", "CSV",
                                "-o", CPU_CSV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[eq2a] typeperf not started: {e}", flush=True)
    try:
        fails = run_boot("A", ROWS_A, boot_a, FN_A, "eq2a_a_host", "eq2a_a_client")
        fails += run_boot("P", ROWS_P, boot_p, FN_P, "eq2a_p_host", "eq2a_p_client")
    finally:
        if cpu is not None:
            cpu.terminate()
            cpu.wait(timeout=10)
    n = sum(len(order) for _, order in ROWS_A + ROWS_P)
    print(f"\ntest_equip_partner_pointer: {n - fails}/{n} cells passed ({'PASS' if not fails else 'FAIL'}) in "
          f"{time.time() - t0:.1f}s; CPU mean {cpu_mean()} %; typeperf rc {cpu.returncode if cpu else None}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
