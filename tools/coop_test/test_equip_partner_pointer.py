"""test_equip_partner_pointer.py: the co-op partner's mouse pointer and name on the pre-battle equip screen. Each
player sees the partner's pointer anywhere on the screen, with the partner's name in small text beside it; never
between PvP opponents, never in battle. The pointer is drawn whatever soldier either screen shows, at its raw position
on the 320x200 Inventory surface (50 ms send rate, 1 s keepalive, 3 s stale), as the game's arrow with the name at
(+10, +4) in the `weight` colour. The test commands `inject_input {kind motion}` and `cursor_pos` move and read the
mouse.

Boot coop (co-op, key LOBBY_KEY, dirs equip_partner_pointer_coop_host / equip_partner_pointer_coop_client):
test_prebattle_equip.py's spine (copied, never imported): the roster-pinned lobby, bring_up_to_briefings with SEED_MAP,
MAP_FP, the client seated on C [8, 9], the host on H [10..14]; the client closes its briefing first (its pre-battle
screen on C1), then the host (its screen on its first soldier). Rows in order:
  client_to_host  move(client, CLIENT_PT); poll the host's presence up to W_PTR: client_to_host-sent,
                  client_to_host-seen, client_to_host-drawn, client_to_host-name
  host_to_client  move(host, HOST_PT); poll the client's presence up to W_PTR: host_to_client-drawn,
                  host_to_client-name
  pointer_moves   move(client, MOVED_PT); poll the host up to W_PTR; rest REST_S: pointer_moves-follow,
                  pointer_moves-rest, pointer_moves-quiet
  turn_one        real OK (ready) presses, client then host; turn 1 on both; move(host, CLIENT_PT); END_S:
                  turn_one-gone, turn_one-quiet
  coop            boot coop's guards: coop-pre (both screens up, phase open, different soldiers), coop-motion
                  (every move reached)
Boot pvp (PvP gm2, X-COM equipment for aliens on, key LOBBY_KEY after boot coop's shutdown, dirs
equip_partner_pointer_pvp_host / equip_partner_pointer_pvp_client): test_alien_equip.py's boot client_aliens (copied)
to both pre-battle screens (the host X-COM, the client the alien seat).
  pvp_opponents   move(client, CLIENT_PT), move(host, HOST_PT); W_PTR: pvp_opponents-none, pvp_opponents-pre
move(gc, pt) = inject_input {kind motion} at ((invX + bx) * SCALE, (invY + by) * SCALE), then cursor_pos until it reads
(invX + bx, invY + by) within MOTION_S, else ONE CAPTURE line and the row fails "motion". A new state re-reads the OS mouse,
so every read follows its own motion. presence = event_state.equip.presence (absent = 0 / false).

A build without the partner pointer fails client_to_host-sent, client_to_host-seen, client_to_host-drawn,
client_to_host-name, host_to_client-drawn, host_to_client-name, pointer_moves-follow, pointer_moves-rest and
pointer_moves-quiet (9 of 15) and passes coop-pre, coop-motion, turn_one-gone, turn_one-quiet, pvp_opponents-none and
pvp_opponents-pre.

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

# ----- pinned setup values (the spine's as in test_prebattle_equip.py) -----
LOBBY_KEY = "49283"                # boot coop, then boot pvp after its shutdown
SEED_MAP = 1                       # set_seed right before newbattle_ok
MAP_FP = -4.48310638993e+18        # the host's mapFingerprint at SEED_MAP 1
C_IDS = [8, 9]                     # the client's seated units
H_IDS = [10, 11, 12, 13, 14]       # the host's own soldiers
SEED_PVP, MISSION_PVP = 1, "STR_SMALL_SCOUT"   # test_alien_equip.py's boot client_aliens
SCALE = 2                          # window 640x400 / the 320x200 logical screen (cursor_pos measured)
CLIENT_PT, HOST_PT, MOVED_PT = (150, 120), (60, 150), (230, 60)   # on the Inventory surface; off OK / PREV / NEXT
CLIENT_NAME, HOST_NAME = "ClientPlayer", "HostPlayer"   # get_coop's peer field on host / client
NAME_DX, NAME_DY = 10, 4           # the name's top-left from the pointer's tip
MOTION_S, W_PTR, REST_S, MOVES_MAX = 1.0, 2.0, 3.0, 12
TURN_WAIT_S, END_S, POLL_S = 5.0, 2.0, 0.05
BRIEFING_WAIT_S, ENTRY_WAIT_S, SCREEN_S, ANSWER_WAIT_S, SAMPLE_S = 30.0, 5.0, 15.0, 3.0, 0.25
MOVES_COOP = 4                     # boot coop's motions: client_to_host, host_to_client, pointer_moves, turn_one
EXPECTED_RC = (0, 3221226505)
ROWS_COOP = (("client_to_host", ("client_to_host-sent", "client_to_host-seen", "client_to_host-drawn",
                                 "client_to_host-name")),
             ("host_to_client", ("host_to_client-drawn", "host_to_client-name")),
             ("pointer_moves", ("pointer_moves-follow", "pointer_moves-rest", "pointer_moves-quiet")),
             ("turn_one", ("turn_one-gone", "turn_one-quiet")),
             ("coop", ("coop-pre", "coop-motion")))
ROWS_PVP = (("pvp_opponents", ("pvp_opponents-none", "pvp_opponents-pre")),)
CPU_CSV = os.path.join(tempfile.gettempdir(), "equip_partner_pointer_cpu_s%d.csv" % harness.HARNESS_SLOT)


# ===================== small probes (copied from test_prebattle_equip.py) =====================


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


# ===================== boot coop (test_prebattle_equip.py's spine, copied) =====================


def boot_coop(host, client):
    m = (host, client)
    ctx = {"m": m, "moves": [], "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("coop", lambda: bring_up_lobby_roster_pinned(host, client, LOBBY_KEY), m)
    seated = {}
    G3F.guarded("coop", lambda: session.bring_up_to_briefings(
        host, client, seated, seat_count=2, pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    hb = battle_state(host)
    sid = {u.get("soldierId"): u["id"] for u in hb.get("units", []) if u.get("soldierId") is not None}
    got = {"mapFingerprint": hb.get("mapFingerprint"), "seated": [sid.get(s) for s in seated.get("soldierIds", [])],
           "hIds": sorted(u["id"] for u in hb.get("units", []) if u.get("coop") == 0 and u.get("faction") == 0
                          and not u.get("isOut"))}
    ctx["boot"].update(got)
    if (got["mapFingerprint"], got["seated"], got["hIds"]) != (MAP_FP, C_IDS, H_IDS):
        miss("coop", f"the spine: {got} (want MAP_FP {MAP_FP}, seated {C_IDS}, H {H_IDS})", m)
    ok, ctx["boot"]["clientBriefingS"] = wait_until(lambda: has(client, "BriefingState"), BRIEFING_WAIT_S, 0.1)
    if not ok:
        miss("coop", f"no client BriefingState within {BRIEFING_WAIT_S} s", m)
    ctx["boot"]["clientClose"] = client.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), ENTRY_WAIT_S)
    if not ok:
        miss("coop", f"the client's pre-battle screen not up within {ENTRY_WAIT_S} s after its briefing closed", m)
    ctx["boot"]["hostClose"] = host.cmd({"cmd": "close_briefing"}).get("ok")
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("coop", f"the host's pre-battle screen not up within {SCREEN_S} s after its briefing closed", m)
    at_screens(ctx, host, client)
    b = ctx["boot"]
    units = [b["views"][n].get("unitId") for n in ("host", "client")]
    ctx["coop-pre"] = (all(screen_up(gc) for gc in m) and b["phase"] == ["open", "open"] and units[0] != units[1],
                    f"screens up {[screen_up(gc) for gc in m]}, equip.phase {b['phase']} (want open on both), unitId "
                    f"host/client {units} (want different), Inventory top-left {ctx['inv']}")
    print(f"[test_equip_partner_pointer] boot coop: {json.dumps(b, sort_keys=True, default=str)}", flush=True)
    return ctx


def row_client_to_host(host, client, ctx, ev):
    ev["move"] = move(client, ctx, CLIENT_PT)
    hi = ctx["inv"]["host"]
    want = [hi[0] + CLIENT_PT[0], hi[1] + CLIENT_PT[1]]

    def seen():
        p = pres(host) or {}
        pe = p.get("peer") or {}
        return drawn_at(host, want) and [pe.get("x"), pe.get("y")] == list(CLIENT_PT)
    got, ev["within"] = wait_until(seen, W_PTR)
    lk = ev["look"] = look(host, client)
    ph, pc = P(lk, "host"), P(lk, "client")
    s, pe, d = pc.get("sent") or {}, ph.get("peer") or {}, ph.get("drawn") or {}
    absent = "" if pc and ph else f" (presence host {'present' if ph else 'absent'}, client {'present' if pc else 'absent'})"
    return {"client_to_host-sent": (s.get("on") is True and [s.get("x"), s.get("y")] == list(CLIENT_PT)
                                    and (pc.get("ptrSent") or 0) >= 1,
                                    f"client presence.sent {s}, ptrSent {pc.get('ptrSent')} (want on true at "
                                    f"{list(CLIENT_PT)}, ptrSent >= 1)" + absent),
            "client_to_host-seen": (pe.get("seat") == ctx["seat"]["client"] and pe.get("on") is True
                                    and [pe.get("x"), pe.get("y")] == list(CLIENT_PT),
                                    f"host presence.peer {pe} (want seat {ctx['seat']['client']}, on true, "
                                    f"{list(CLIENT_PT)} within {W_PTR} s; waited {ev['within']})" + absent),
            "client_to_host-drawn": (d.get("ptr") is True and [d.get("x"), d.get("y")] == want,
                          f"host drawn ptr {d.get('ptr')} at {[d.get('x'), d.get('y')]} (want true at {want})" + absent),
            "client_to_host-name": (d.get("name") == CLIENT_NAME and d.get("nameShown") is True
                         and [d.get("nameX"), d.get("nameY")] == [(d.get("x") or 0) + NAME_DX, (d.get("y") or 0) + NAME_DY],
                         f"host drawn name {d.get('name')!r} shown {d.get('nameShown')} at {[d.get('nameX'), d.get('nameY')]} "
                         f"(want {CLIENT_NAME!r} shown at the pointer + ({NAME_DX}, {NAME_DY}))" + absent)}


def row_host_to_client(host, client, ctx, ev):
    ev["move"] = move(host, ctx, HOST_PT)
    ci = ctx["inv"]["client"]
    want = [ci[0] + HOST_PT[0], ci[1] + HOST_PT[1]]
    got, ev["within"] = wait_until(lambda: drawn_at(client, want), W_PTR)
    lk = ev["look"] = look(host, client)
    d = P(lk, "client").get("drawn") or {}
    absent = "" if P(lk, "client") else " (client presence absent)"
    return {"host_to_client-drawn": (d.get("ptr") is True and [d.get("x"), d.get("y")] == want,
                          f"client drawn ptr {d.get('ptr')} at {[d.get('x'), d.get('y')]} (want true at {want} within "
                          f"{W_PTR} s; waited {ev['within']})" + absent),
            "host_to_client-name": (d.get("name") == HOST_NAME and d.get("nameShown") is True,
                         f"client drawn name {d.get('name')!r} shown {d.get('nameShown')} (want {HOST_NAME!r} shown)" + absent)}


def row_pointer_moves(host, client, ctx, ev):
    c0 = sent(client)
    ev["move"] = move(client, ctx, MOVED_PT)
    hi = ctx["inv"]["host"]
    want = [hi[0] + MOVED_PT[0], hi[1] + MOVED_PT[1]]
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
    return {"pointer_moves-follow": (bool(got), f"host drawn ptr {d.get('ptr')} at {[d.get('x'), d.get('y')]} (want "
                                                f"true at {want} within {W_PTR} s: the newest position replaced "
                                                f"{list(CLIENT_PT)})"),
            "pointer_moves-rest": (rest is not None and REST_S - 1 <= rest <= REST_S + 1 and bool(samples)
                          and all(x is True for x in samples),
                          f"client ptrSent {c1} -> {c2} over the {ev['restS']} s rest (want +{REST_S - 1:g} .. "
                          f"+{REST_S + 1:g}: the 1 s keepalive); host drawn.ptr true in "
                          f"{sum(1 for x in samples if x is True)} of {len(samples)} samples (want all)"),
            "pointer_moves-quiet": (rest is not None and rest <= 1 + REST_S and whole <= MOVES_MAX,
                           f"client ptrSent +{rest} over the rest (want <= {1 + REST_S:g}), +{whole} over the row (want <= "
                           f"{MOVES_MAX}; ptrSent {c0} -> {c2})")}


def row_turn_one(host, client, ctx, ev):
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
    ev["move"] = move(host, ctx, CLIENT_PT)
    time.sleep(END_S)
    lk = ev["look"] = look(host, client)
    end = {gc.name: sent(gc) or 0 for gc in m}
    ev.update(ptrSent={"turn1": at1, "end": end}, phase=[equip(gc).get("phase") for gc in m],
              turn=[turn(host), turn(client)], hash=G3F.hash_now(host, client),
              desyncSeen=[es(gc).get("desyncSeen") for gc in m])
    up = alive(host)
    crash = sorted(session._crash_log_snapshot() - ctx["crash0"])
    dr = {n: (P(lk, n).get("drawn") or {}).get("ptr") for n in ("host", "client")}
    return {"turn_one-gone": (not any(dr.values()), f"drawn.ptr host/client {dr} {END_S} s after turn 1 (want false / "
                                                    f"absent on both: the screens closed)"),
            "turn_one-quiet": (all(end[n] <= at1[n] + 1 for n in end) and up and not crash,
                          f"ptrSent at turn 1 {at1} -> {end} at +{END_S} s (want at most +1 each: one `on false`); host "
                          f"alive {up}; new crash files {crash} (want none)")}


def row_coop(host, client, ctx, ev):
    mv = ctx["moves"]
    ev.update(boot=ctx["boot"], moves=mv)
    return {"coop-pre": ctx["coop-pre"],
            "coop-motion": (len(mv) == MOVES_COOP and all(x["reached"] for x in mv),
                         f"{sum(1 for x in mv if x['reached'])} of {len(mv)} motions reached cursor_pos within {MOTION_S} s "
                         f"(want {MOVES_COOP} of {MOVES_COOP}: "
                         f"{[(x['machine'], x['want'], x['waited']) for x in mv]})")}


# ===================== boot pvp (test_alien_equip.py's boot client_aliens, copied) =====================


def lobby_client_aliens(host, client, key):
    """test_alien_equip.py's lobby_client_aliens: the client joins and takes the Alien team (gamemode 2)."""
    BER.raw.skirmish_host(host, key)
    BER.raw.skirmish_client_at_browser(client)
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": key, "player": BER.raw.CLIENT_PLAYER})
    host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
    client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
    host.ok({"cmd": "profile_ok"})
    client.ok({"cmd": "profile_ok"})
    host.wait_for("start offered", lambda: BER.raw.lobby(host).get("buttonVisible") or None)
    r = host.ok({"cmd": "lobby_set_team", "row": BER.gm2_row_for(host, BER.raw.CLIENT_PLAYER), "team": "Alien"})
    time.sleep(1)   # the change_team broadcast settles on the client
    return r.get("gamemode")


def drive_pvp(host, client):
    """test_alien_equip.py's drive: Small Scout, set_seed, newbattle_ok, both briefings up."""
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at battle settings", lambda: (not session.has_state(host, "LobbyMenu")) or None)
    r = host.cmd({"cmd": "newbattle_mission", "type": MISSION_PVP})
    assert r.get("ok"), f"newbattle_mission {MISSION_PVP}: {r}"
    host.ok({"cmd": "set_seed", "seed": SEED_PVP})
    host.ok({"cmd": "newbattle_ok"})
    host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"), timeout=60)
    client.wait_for("client briefing", lambda: session.has_state(client, "BriefingState") or None, timeout=90)


def boot_pvp(host, client):
    m = (host, client)
    ctx = {"m": m, "moves": [], "boot": {}, "crash0": session._crash_log_snapshot()}
    G3F.guarded("pvp", lambda: (host.spawn(), host.connect(), client.spawn(), client.connect()), m)
    G3F.guarded("pvp", lambda: host.ok({"cmd": "set_seed", "seed": SEED_PVP}), m)
    ctx["boot"]["gm"] = G3F.guarded("pvp", lambda: lobby_client_aliens(host, client, LOBBY_KEY), m)
    G3F.guarded("pvp", lambda: drive_pvp(host, client), m)
    G3F.guarded("pvp", lambda: host.ok({"cmd": "click_widget", "match": "ok"}), m)
    ok, ctx["boot"]["hostScreenS"] = wait_until(lambda: screen_up(host), SCREEN_S)
    if not ok:
        miss("pvp", "the host's pre-battle screen never came up", m)
    G3F.guarded("pvp", lambda: session.dismiss_client_briefing(client), m)
    ok, ctx["boot"]["clientScreenS"] = wait_until(lambda: screen_up(client), SCREEN_S)
    if not ok:
        miss("pvp", f"the client's (alien seat) pre-battle screen not up within {SCREEN_S} s", m)
    at_screens(ctx, host, client)
    print(f"[test_equip_partner_pointer] boot pvp: {json.dumps(ctx['boot'], sort_keys=True, default=str)}", flush=True)
    return ctx


def row_pvp_opponents(host, client, ctx, ev):
    ev["boot"] = ctx["boot"]
    ev["moves"] = [move(client, ctx, CLIENT_PT), move(host, ctx, HOST_PT)]
    time.sleep(W_PTR)
    lk = ev["look"] = look(host, client)
    ph, pc = P(lk, "host"), P(lk, "client")
    vals = {n: {"ptrSent": p.get("ptrSent") or 0, "drawn": bool((p.get("drawn") or {}).get("ptr"))}
            for n, p in (("host", ph), ("client", pc))}
    pre = ctx["boot"].get("gm") == 2 and all(screen_up(gc) for gc in (host, client))
    return {"pvp_opponents-none": (all(v == {"ptrSent": 0, "drawn": False} for v in vals.values()),
                         f"{vals} after {W_PTR} s (want ptrSent 0 and drawn.ptr false on both; absent = 0 / false)"),
            "pvp_opponents-pre": (pre and len(ev["moves"]) == 2,
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
        print(f"[test_equip_partner_pointer] boot {tag} shut down: {rc}", flush=True)


FN_COOP = {"client_to_host": row_client_to_host, "host_to_client": row_host_to_client,
           "pointer_moves": row_pointer_moves, "turn_one": row_turn_one, "coop": row_coop}
FN_PVP = {"pvp_opponents": row_pvp_opponents}


def main():
    t0 = time.time()
    cpu = None
    try:
        cpu = subprocess.Popen(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-y", "-f", "CSV",
                                "-o", CPU_CSV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"[test_equip_partner_pointer] typeperf not started: {e}", flush=True)
    try:
        fails = run_boot("coop", ROWS_COOP, boot_coop, FN_COOP, "equip_partner_pointer_coop_host",
                         "equip_partner_pointer_coop_client")
        fails += run_boot("pvp", ROWS_PVP, boot_pvp, FN_PVP, "equip_partner_pointer_pvp_host",
                          "equip_partner_pointer_pvp_client")
    finally:
        if cpu is not None:
            cpu.terminate()
            cpu.wait(timeout=10)
    n = sum(len(order) for _, order in ROWS_COOP + ROWS_PVP)
    print(f"\ntest_equip_partner_pointer: {n - fails}/{n} cells passed ({'PASS' if not fails else 'FAIL'}) in "
          f"{time.time() - t0:.1f}s; CPU mean {cpu_mean()} %; typeperf rc {cpu.returncode if cpu else None}", flush=True)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
