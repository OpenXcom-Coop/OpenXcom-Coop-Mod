"""test_craft_alienbase_target.py: an X-COM craft sent to the other player's alien base (a mirror on its machine) keeps that
destination across a geoscape save and reload, as a craft sent to a UFO or mission-site mirror does since issue #28 (R-H48-0, lead
L-H44-1). Today every save strips the mirror and the craft node names no co-op id for it, so Craft::load makes the destination a waypoint
at the base's spot and the craft arrives with "has reached WAY POINT-1 / Now patrolling".

Spec: docs rewrite/prompts/w2h48_craft_alienbase_target.md (stage S-A, (d) and (f), FX48-1 .. FX48-12) and its ORCHESTRATOR RULINGS
(QH48-1 .. QH48-7 (a)); R-H48-0 / VL-H48-1, L-H44-1, issue #28 (the UFO / site relink), D199 / D211 (the SEPARATE client's refusal, W2-H9),
QC4B-4 (a) (W2-H44: an alien base keeps its co-op id across its owner's save); F17280-F17284, F17360-F17378, F17560-F17579. TASK 0 pins:
docs rewrite/w2h48-task0/sa/CONSTANTS.md (Ka-S / Ka-P on the unchanged build = W2-H44's green, Kg-S / Kg-P on E1-E6, then restored).

Keys "49134" / "49135" (bring-up / resume lobby). Boot S (dirs w2h48_s_*), SEPARATE gm0: R1 (the client's Skyranger CSKY -> the host's
alien base HCOOP), R2 (the host's Skyranger HSKY -> the client's base CCOOP), R4 (both save files, the ids), R5 (the control: the client's
Interceptor 2 CINT -> the host's crashed UFO UCOOP), S-common. Boot P (dirs w2h48_p_*), gm3 with the host on the Alien team: P-mode, R3
(CSKY -> the alien host's base ACOOP), R4-gm3, R5-gm3, P-common. Each boot: targets on their OWNER (spawn_alien_base +
host_alien_base_found; spawn_ufo crashed) and the peer's mirror; seats; craft_force to "alienBaseCoop:" / "ufoCoop:" + the co-op id; the
host's quick save (SaveGameState) then the named save (PyYAML: host world + client blob); both end; the host respawns on its dir, client2
on an EMPTY dir; boot S session.resume_campaign, boot P the RR copy through host_menu_host; the relink phase (idx 0), the
arrival phase (idx 2); every popup recorded then closed with dismiss_popup (a landing is never confirmed). AB(n) = "DESTINATION: ALIEN
BASE-" + n, n = the mirror's live Target id (m0 before the save, m1 after the resume; destKind is "other" for a base and a waypoint
alike, F17290). R1-arrive = the H9 refusal; R2- / R3-arrive = ConfirmLandingState at the base; R5-arrive = CINT turned home (destKind
"base" at a poll, or back at X in a base status right after "ufo": the leg is shorter than one poll, TASK 0). A staging miss prints ONE
"CAPTURE S:" / "CAPTURE P:" line and FAILs the boot's remaining cells "boot".
RED (R1, the unchanged build; TASK 0 Ka-S / Ka-P): exit 2, 12/21 - FAIL R1-relink, R1-arrive, R2-relink, R2-arrive, R4-client, R4-host,
R3-relink, R3-arrive, R4-gm3 ("DESTINATION: WAY POINT-1"; CraftPatrolState "has reached WAY POINT-1"; the key absent). GREEN (G1 = E1-E6;
TASK 0 Kg-S / Kg-P): 21/21.
ONE foreground run, no skip path; exit 0 only when every cell passes, else 2.
Run:  python tools/coop_test/test_craft_alienbase_target.py
"""

import base64
import glob
import json
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402
import geo  # noqa: E402
import pvp_fixture as PF  # noqa: E402
import yaml  # noqa: E402

# ----- TASK 0 pins (docs rewrite/w2h48-task0/sa/CONSTANTS.md) -----
K1, K2 = "49134", "49135"                                               # FX48-1: bring-up lobby / resume lobby
TAGS, SAVE = {"S": "w2h48_s", "P": "w2h48_p"}, {"S": "w2h48_s.sav", "P": "w2h48_p.sav"}   # FX48-6
TARGETS = {"hab": ("host", "base", "X", (0.10, 0.35)), "ufo": ("host", "ufo", "X", (-0.35, 0.10)),     # FX48-3 / FX48-10: owner,
           "cab": ("client", "base", "H", (0.10, -0.30))}                                          # kind, from base, offset
CRAFTS = {"CSKY": ("client", "SKYRANGER", None, "X", (0.10, -0.15), "hab"),                         # FX48-4 / FX48-5: owner, type,
          "CINT": ("client", "INTERCEPTOR", 2, "X", (-0.35, -0.40), "ufo"),                         # id (None = the first), home,
          "HSKY": ("host", "SKYRANGER", None, "H", (0.10, 0.45), "cab")}                            # start offset, target
UFO = {"type": "STR_SMALL_SCOUT", "mission": "STR_ALIEN_RESEARCH", "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID",
       "trajectory": "P0", "state": "crashed", "speed": 0, "hours": 240}
BOOTS = {"S": {"targets": ["hab", "ufo", "cab"], "crafts": ["CSKY", "CINT", "HSKY"], "mode": (0, 0, False, False),
               "row": {"CSKY": "R1", "HSKY": "R2"}, "file": {"CSKY": "R4-client", "HSKY": "R4-host"}, "ids": "R4-ids", "cint": "R5-relink"},
         "P": {"targets": ["hab", "ufo"], "crafts": ["CSKY", "CINT"], "mode": (3, 3, True, False),
               "row": {"CSKY": "R3"}, "file": {"CSKY": "R4-gm3"}, "ids": "R4-gm3-ids", "cint": "R5-gm3"}}
SEATS = 2                                                                # FX48-4
MIRROR_S, SAVE_S, RELINK_S, ARRIVE_S = 30, 90, 10, 90                   # FX48-11 (TASK 0: each >= 2 x its measured value)
RELINK_POLL, ARRIVE_POLL, NEAR, FAR = 0.25, 0.4, 0.01, 0.05             # FX48-8 / FX48-9 / the arrival point / FX48-5
H9TEXT = "In co-op only the host's craft can start a mission. Seat your soldiers on the host's craft to take part."   # FX48-12
AB = "DESTINATION: ALIEN BASE-"                                         # FX48-12: AB(n) = AB + n
HOME = ("STR_REFUELLING", "STR_REARMING", "STR_REPAIRS", "STR_READY")
CK = ("type", "id", "name", "status", "destKind", "destId", "displayStatus", "lon", "lat")
ROWS = {"S": {"R1": ["R1-before", "R1-relink", "R1-arrive"], "R2": ["R2-before", "R2-relink", "R2-arrive"],
              "R4": ["R4-client", "R4-host", "R4-ids"], "R5": ["R5-file", "R5-relink", "R5-arrive"], "S-common": ["S-common"]},
        "P": {"P-mode": ["P-mode"], "R3": ["R3-before", "R3-relink", "R3-arrive"], "R4-gm3": ["R4-gm3", "R4-gm3-ids"],
              "R5-gm3": ["R5-gm3"], "P-common": ["P-common"]}}
RED = {"R1-relink", "R1-arrive", "R2-relink", "R2-arrive", "R4-client", "R4-host", "R3-relink", "R3-arrive", "R4-gm3"}
RESULTS, EV, BOOT = [], {}, {"tag": "S"}      # (cell, ok, detail); per boot: every value read (EVIDENCE); the boot in flight

class FixtureMiss(Exception): pass

def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)

def block(names, why):
    done = {x[0] for x in RESULTS}
    for n in names:
        if n not in done:
            cell(n, False, f"blocked: {why}")

def row_verdict(row, names):
    bad = [n for n, ok, _ in RESULTS if n in names and not ok]
    print(f"ROW {row}: {'PASS' if not bad else 'FAIL'}" + (f" ({len(bad)} failing: {bad})" if bad else ""), flush=True)

def load():
    """CPU % and the count of the owner's game processes (S24), recorded beside every wall."""
    try:
        v = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor | Measure-Object -Property "
                            "LoadPercentage -Average).Average; @(Get-Process | Where-Object { $_.ProcessName -like 'Wardogs*' }).Count"],
                           capture_output=True, text=True, timeout=60).stdout.split()
        return {"cpu": v[0] if v else None, "wardogs": v[1] if len(v) > 1 else None}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:120]}

# ----- probes and one-line helpers -----
def sub(d, ks): return {k: d.get(k) for k in ks}
def other(o): return "client" if o == "host" else "host"
def gs(gc): return gc.ok({"cmd": "geo_state"})
def abases(gc): return [sub(a, ("id", "coopId", "coop", "discovered")) for a in gc.ok({"cmd": "alien_base_state"}).get("alienBases") or []]
def mir(abs_, cid): return next((a for a in abs_ if a["coop"] and a["coopId"] == cid), None)
def ufo(u): return sub(u, ("id", "coopId", "coop", "status"))
def stack(gc): return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
def evs(gc): return sub(gc.cmd({"cmd": "event_state"}), ("desyncSeen", "coopClientBattleRefused", "coopClientBattleRefusedLast"))
def coopv(gc): return sub(gc.cmd({"cmd": "get_coop"}), ("gamemode", "noBases", "localSeat"))
def mtuple(h, c): return (h["gamemode"], c["gamemode"], h["noBases"], c["noBases"])
def dist(c, pt): return math.hypot(c["lon"] - pt[0], c["lat"] - pt[1]) if c else 9.0
def add(p, d): return (p[0] + d[0], p[1] + d[1])
def ds(c): return f"{(c or {}).get('displayStatus')!r} {(c or {}).get('status')}"
def crash_set(): return set(glob.glob(os.path.join(harness.CRASH_DIR, "crash_*")))
def cmp(c): return c and [c.get(k) for k in ("displayStatus", "status", "destKind")] + [round(c[k] or 0, 4) for k in ("lon", "lat")]

def own(g, icon=False):    # the machine's own real base, or (icon=True) the peer's coop-icon base, in a geo_state
    return next((b for b in g.get("bases", []) if bool(b.get("coopIcon")) == icon and (icon or not b.get("coopBase"))), None)

def pick(b, kind, cid=None):
    c = next((c for c in (b or {}).get("crafts", []) if kind in c.get("type", "") and not c.get("coop") and cid in (None, c.get("id"))),
             None)
    return (c["type"], c["id"]) if c else None

def craft(g, key, icon=False):
    c = next((c for c in (own(g, icon) or {}).get("crafts", []) if (c.get("type"), c.get("id")) == tuple(key)
              and (icon or not c.get("coop"))), None)
    return sub(c, CK) if c else None

def ok_ds(c, m):          # AB(the mirror's Target id) on a STR_OUT craft (the -before and -relink cells)
    return bool(c and m and c.get("displayStatus") == AB + str(m["id"]) and c.get("status") == "STR_OUT")

def wait(pred, timeout, interval=0.1):
    t0 = time.time()
    while True:
        v = pred()
        if v or time.time() - t0 >= timeout:
            return v or None, round(time.time() - t0, 2)
        time.sleep(interval)

def capture(err, *machines):
    """ONE CAPTURE line (stack, get_coop, event_state, alien_base_state, every geo_state craft, the log tail per machine); boot FAIL."""
    cap = {}
    for gc in (g for g in machines if g is not None and g.proc is not None and g.proc.poll() is None):
        try:
            with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as fh:
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[-40:]
            cap[gc.name] = {"stack": stack(gc), "get_coop": gc.cmd({"cmd": "get_coop"}), "event_state": evs(gc), "alienBases": abases(gc),
                            "crafts": [dict(sub(c, CK), base=b.get("name")) for b in gs(gc).get("bases", []) for c in b.get("crafts", [])],
                            "log_tail": tail}
        except Exception as e:  # noqa: BLE001
            cap[gc.name] = f"probe failed: {e!r}"[:300]
    print(f"CAPTURE {BOOT['tag']}: {json.dumps({'missed': err, 'machines': cap}, sort_keys=True, default=str)}", flush=True)
    raise FixtureMiss(err)

def read_save(path):
    """The host world and the client blob (coopClientSaves) of a save (CAP1's read_save): craft nodes, alienBases, waypoints."""
    def world(d):
        return {"crafts": [dict({k: v for k, v in c.items() if k not in ("items", "weapons", "vehicles", "soldiers")}, base=b.get("name"))
                           for b in (d or {}).get("bases") or [] for c in b.get("crafts") or []],
                "alienBases": (d or {}).get("alienBases") or [], "waypoints": (d or {}).get("waypoints")}
    out, loader = {"file": os.path.basename(path), "bytes": os.path.getsize(path)}, getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8", errors="replace") as fh:
        docs = [d for d in yaml.load_all(fh, Loader=loader) if isinstance(d, dict)]
    for d in docs:
        if "bases" in d:
            out["world"] = world(d)
        for e in d.get("coopClientSaves") or []:
            raw = e.get("blob")
            blob = (base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)).decode("utf-8", errors="replace")
            out["blob"] = world(next((x for x in yaml.load_all(blob, Loader=loader) if isinstance(x, dict) and "bases" in x), None))
    return out

def node_cell(name, files, part, base, key, field, cid, dtype, ev):
    """In BOTH saves the craft node (part = the host world / the client blob) carries field == cid (and dest.type == dtype)."""
    got = {k: next((c for c in (f.get(part) or {}).get("crafts", []) if c.get("base") == base and (c["type"], c["id"]) == tuple(key)),
                   None) for k, f in files.items()}
    ev.setdefault("nodes", {})[name] = got
    bad = [f"{k}: {'no node' if n is None else {'dest': n.get('dest'), field: n.get(field, 'absent')}}" for k, n in got.items()
           if n is None or n.get(field) != cid or (dtype and (n.get("dest") or {}).get("type") != dtype)]
    cell(name, not bad, f"both saves' {part} {key[0]} {key[1]}: " + ("; ".join(bad) + f" (want {field} {cid})" if bad else
                                                                       f"{field} == {cid}" + (f", dest {dtype}" if dtype else "")))

def target(owner, peer, kind, pt, ev, tag):
    """FX48-3: a REAL alien base discovered on its owner, or the host's crashed UFO; the peer's mirror (owner's co-op id) <= MIRROR_S."""
    if kind == "base":
        sp = owner.ok({"cmd": "spawn_alien_base", "lon": pt[0], "lat": pt[1], "race": "STR_SECTOID"})
        owner.ok({"cmd": "host_alien_base_found", "alien_base_id": sp["alien_base_id"]})
        real = next((a for a in abases(owner) if not a["coop"] and a["id"] == sp["alien_base_id"]), None)
        pool = lambda: [a for a in abases(peer) if a["discovered"]]  # noqa: E731
    else:
        sp = owner.ok(dict(UFO, cmd="spawn_ufo", lon=pt[0], lat=pt[1]))
        real = next((ufo(u) for u in gs(owner).get("ufos", []) if not u.get("coop") and u.get("id") == sp.get("ufo_id")), None)
        pool = lambda: [ufo(u) for u in gs(peer).get("ufos", [])]  # noqa: E731
    mirror, s = wait(lambda: real and mir(pool(), real["coopId"]), MIRROR_S)
    ev[tag] = {"point": pt, "spawn": sp, "real": real, "mirror0": mirror, "mirrorS": s}
    if not real or not mirror:
        capture(f"FX48-3 {tag}: real {real}, the peer's mirror {mirror} within {MIRROR_S} s", owner, peer)
    return dict(real, point=pt)

def seat(gc, key, peer):
    """FX48-4: the two lowest-id own-base soldiers; the next by id while none is aboard."""
    sb = next(x for x in gc.ok({"cmd": "get_soldiers"})["bases"] if not x.get("coopBaseFlag") and not x.get("coopIcon"))
    res = []
    for sid in sorted(s["id"] for s in sb["soldiers"]):
        if len(res) >= SEATS and any(r["seated"] for r in res):
            break
        r = gc.cmd({"cmd": "craft_assign", "craft_id": key[1], "base": sb["name"], "soldier_id": sid, "on": True})
        res.append({"soldier": sid, "seated": bool(r.get("seated")), "error": r.get("error")})
    if not any(r["seated"] for r in res):
        capture(f"FX48-4 no soldier aboard {key} on {gc.name}: {res}", gc, peer)
    return res

def save(host, client, name, ev):
    """FX48-6: the host's quick save through SaveGameState, 2 s, drain, then the named save_game; both read with PyYAML."""
    qpath, spath = (os.path.join(host.user_dir, "xcom1", f) for f in ("_quick_.asav", name))
    t0 = time.time()
    q = host.cmd({"cmd": "save_game_ui", "type": "quick"})
    okq, sq = wait(lambda: os.path.exists(qpath) and os.path.getmtime(qpath) >= t0 - 1, SAVE_S, 0.2)
    time.sleep(2.0)
    geo.drain_popups(host)
    n = host.cmd({"cmd": "save_game", "file": name})
    okn, sn = wait(lambda: os.path.exists(spath) and os.path.getsize(spath) > 0, SAVE_S, 0.2)
    time.sleep(1.0)
    if not okq or not okn:
        capture(f"FX48-6 save: quick {q} on disk {okq}, named {n} on disk {okn}", host, client)
    files = {"quick": read_save(qpath), "named": read_save(spath)}
    ev["save"] = {"quickS": sq, "namedS": sn, "files": files}
    if any("blob" not in f or "world" not in f for f in files.values()):
        capture("FX48-6 a save without its host world or the client blob (coopClientSaves)", host, client)
    return files

def resume_rr(host, client, save_file, port):
    """CAP2's copy of test_campaign_resume_roles.resume_campaign: START HOST through the real host window."""
    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (resume)", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": port, "player": "HostPlayer"})
    host.wait_for("resume lobby", lambda: session.has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected resume lobby, got {ls}"
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})
    client.wait_for("client resume lobby", lambda: session.has_state(client, "LobbyMenu"))
    session.resume_campaign_via_button(host, "ClientPlayer")
    host.wait_for("client world ack", lambda: host.cmd({"cmd": "get_coop"}).get("resumeAck") or None, timeout=120)
    session.press_back_when_shown(host, "host RESUME", codes=(60, 62))
    client.wait_for("resume session up", lambda: "GeoscapeState" in session.states(client)[-1] if session.states(client) else None,
                    timeout=120)

def relaunch(x, ev):
    """FX48-7: both end; the host respawns on its dir, client2 on an EMPTY dir; boot S session.resume_campaign, boot P resume_rr."""
    t0 = time.time()
    x["client"].shutdown(); x["host"].shutdown()
    host = x["host"] = GameClient("host", None, x["host"].user_dir)
    c2 = x["client2"] = GameClient("client2", None, make_user_dir(x["tag"] + "_client2"))
    host.spawn(); host.connect(timeout=240); c2.spawn(); c2.connect(timeout=240)
    try:
        if x["boot"] == "S":
            session.resume_campaign(host, c2, SAVE["S"], port=K2)
        else:
            resume_rr(host, c2, SAVE["P"], K2)
    except Exception as e:  # noqa: BLE001
        capture(f"FX48-7 resume: {type(e).__name__}: {str(e)[:300]}", host, c2)
    ev["resumeS"] = round(time.time() - t0, 2)
    return host, c2

def popups(gc, t0, snap):
    """Every popup on gc: recorded (stack, list_widgets texts, the crafts; event_state on a CraftErrorState), then dismiss_popup."""
    out = []
    for _ in range(8):
        st = stack(gc)
        if not st or st[-1] == "GeoscapeState":
            break
        rec = {"t": round(time.time() - t0, 2), "machine": gc.name, "top": st[-1], "stack": st, "crafts": snap(),
               "texts": [w.get("text") for w in gc.cmd({"cmd": "list_widgets"}).get("widgets", []) if w.get("text")]}
        if rec["top"] == "CraftErrorState":
            rec["ev"] = evs(gc)
        r = gc.cmd({"cmd": "dismiss_popup"})
        rec["dismiss"] = r.get("handled") or r.get("error")
        out.append(rec)
        if r.get("wait") or not r.get("ok") or rec["top"] == "ConfirmLandingState":   # a landing prompt re-pops each tick: next poll
            break
    return out

def relink(host, c2, snap, checks, ev):
    """FX48-8: geo_set_speed idx 0 on both every poll, RELINK_POLL polls, <= RELINK_S; the first poll time at which each check holds."""
    t1, polls, first, pops = time.time(), [], {}, []
    while True:
        for gc in (host, c2):
            gc.cmd({"cmd": "geo_set_speed", "idx": 0})
        v = dict(snap(), t=round(time.time() - t1, 2))
        polls.append(v)
        first.update({n: v["t"] for n, fn in checks.items() if n not in first and fn(v)})
        for gc in (host, c2):
            pops += popups(gc, t1, snap)
        if len(first) == len(checks) or time.time() - t1 >= RELINK_S:
            break
        time.sleep(RELINK_POLL)
    ev["relink"] = {"polls": polls, "first": first, "popups": pops, "s": round(time.time() - t1, 2)}
    return polls, first

def arrival(host, c2, snap, owners, ev, home):
    """FX48-9: idx 2, ARRIVE_POLL polls, <= ARRIVE_S, until each craft in owners {name: machine} arrived: its first popup naming it on its
    machine (client2's H9 refusal names no craft: CSKY's), or CINT's turn home ("base", or at `home` in a base status right after "ufo")."""
    t2, events, arr, prev = time.time(), [], {}, snap()
    while time.time() - t2 < ARRIVE_S and not set(owners) <= set(arr):
        for gc in (host, c2):
            for rec in popups(gc, t2, snap):
                events.append(rec)
                blob = " ".join(rec["texts"]).upper()
                for n, m in owners.items():
                    if n not in arr and m == gc.name and (str((rec["crafts"].get(n) or {}).get("name") or "?").upper() in blob or (
                            n == "CSKY" and rec["top"] == "CraftErrorState" and H9TEXT in rec["texts"])):
                        arr[n] = rec
        cur = snap()
        for n in owners:
            a, b = prev.get(n) or {}, cur.get(n) or {}
            if [a.get(k) for k in ("destKind", "displayStatus", "status")] != [b.get(k) for k in ("destKind", "displayStatus", "status")]:
                events.append({"t": round(time.time() - t2, 2), "craft": n, "from": a, "to": b})
                if n == "CINT" and n not in arr and (b.get("destKind") == "base" or (
                        a.get("destKind") == "ufo" and b.get("destKind") == "none" and b.get("status") in HOME and dist(b, home) <= NEAR)):
                    arr[n] = {"t": events[-1]["t"], "kind": b.get("destKind"), "craft": b, "from": a}
        prev = cur
        for gc in (host, c2):
            gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(ARRIVE_POLL)
    ev["arrival"] = {"events": events, "arrived": {n: a.get("t") for n, a in arr.items()}, "s": round(time.time() - t2, 2), "final": snap()}
    return events, arr

def patrols(events, machine, name):
    return [e["t"] for e in events if e.get("machine") == machine and e.get("top") == "CraftPatrolState"
            and str(name).upper() in " ".join(e.get("texts") or []).upper()]

def boot(b, x, ev):
    """FX48-2 .. FX48-11 for boot b: bring-up, staging, the save, the resume, the relink and arrival phases, and every cell."""
    B, m = BOOTS[b], {"host": x["host"], "client": x["client"]}
    for gc in m.values():
        gc.spawn(); gc.connect(timeout=240)
    try:
        if b == "S":
            session.new_campaign(m["host"], m["client"], port=K1)
        else:
            ev["lobbyGamemode"] = PF.start_pvp_campaign(m["host"], m["client"], K1, alien_player="host")
    except Exception as e:  # noqa: BLE001
        capture(f"FX48-2 / FX48-10 bring-up: {type(e).__name__}: {str(e)[:300]}", *m.values())
    geo.slow_clock(m["host"], m["client"])
    mode0 = ev["mode"] = {n: coopv(gc) for n, gc in m.items()}
    bases = {"X": own(gs(m["client"])), "H": own(gs(m["host"]))}
    keys = {n: pick(bases[CRAFTS[n][3]], CRAFTS[n][1], CRAFTS[n][2]) for n in B["crafts"]}
    ev["bases"] = dict({k: v and {q: v.get(q) for q in ("name", "lon", "lat")} for k, v in bases.items()}, crafts=keys)
    if mtuple(mode0["host"], mode0["client"]) != B["mode"] or not all(keys.values()):
        capture(f"FX48-2 / FX48-10 preconditions: modes {mode0} (want {B['mode']}), bases / crafts {ev['bases']}", *m.values())
    pos = {k: (v["lon"], v["lat"]) for k, v in bases.items() if v}
    tg = {t: target(m[TARGETS[t][0]], m[other(TARGETS[t][0])], TARGETS[t][1], add(pos[TARGETS[t][2]], TARGETS[t][3]), ev, t)
          for t in B["targets"]}
    ev["seats"] = {n: seat(m[CRAFTS[n][0]], keys[n], m[other(CRAFTS[n][0])]) for n in B["crafts"] if CRAFTS[n][1] == "SKYRANGER"}
    geo.slow_clock(m["host"], m["client"])
    at = {n: add(pos[CRAFTS[n][3]], CRAFTS[n][4]) for n in B["crafts"]}                             # FX48-5
    to = {n: ("ufoCoop:" if CRAFTS[n][5] == "ufo" else "alienBaseCoop:") + str(tg[CRAFTS[n][5]]["coopId"]) for n in B["crafts"]}
    ev["force"] = {n: m[CRAFTS[n][0]].ok({"cmd": "craft_force", "craft_id": keys[n][1], "status": "STR_OUT", "fuel": 999999,
                                          "lowFuel": False, "lon": at[n][0], "lat": at[n][1], "dest": to[n]}) for n in B["crafts"]}
    geo.slow_clock(m["host"], m["client"])
    reads, live, sky = [("host@before", evs(m["host"])), ("client@before", evs(m["client"]))], dict(m), list(B["row"])
    bt = [t for t in B["targets"] if TARGETS[t][1] == "base"]

    def snap():
        g, a = {n: gs(gc) for n, gc in live.items()}, {n: abases(gc) for n, gc in live.items()}
        out = {n: craft(g[CRAFTS[n][0]], keys[n]) for n in B["crafts"]}
        out["peer"] = {f"{n}@{other(CRAFTS[n][0])}": craft(g[other(CRAFTS[n][0])], keys[n], True) for n in sky}
        out.update({t: mir(a[other(TARGETS[t][0])], tg[t]["coopId"]) for t in bt})       # the mirror on the craft's machine
        return out
    b0 = ev["before"] = snap()
    for n in sky:
        t = CRAFTS[n][5]
        cell(f"{B['row'][n]}-before", ok_ds(b0[n], b0[t]), f"{CRAFTS[n][0]} {n} {ds(b0[n])}, want {AB}{b0[t] and b0[t]['id']} (m0 = its "
             f"mirror of {t} co-op id {tg[t]['coopId']}) STR_OUT")
    files = save(m["host"], m["client"], SAVE[b], ev)
    part = {"client": "blob", "host": "world"}
    for n, name in B["file"].items():
        node_cell(name, files, part[CRAFTS[n][0]], bases[CRAFTS[n][3]]["name"], keys[n], "coopDestAlienBaseId", tg[CRAFTS[n][5]]["coopId"],
                  "STR_ALIEN_BASE", ev)
    if b == "S":
        node_cell("R5-file", files, "blob", bases["X"]["name"], keys["CINT"], "coopDestUfoId", tg["ufo"]["coopId"], None, ev)
    host, c2 = relaunch(x, ev)
    live.update(host=host, client=c2)
    if b == "P":
        m1 = ev["modeAfter"] = {"host": coopv(host), "client2": coopv(c2)}
        got = [mtuple(mode0["host"], mode0["client"]), mtuple(m1["host"], m1["client2"])]
        cell("P-mode", got == [B["mode"]] * 2, f"(gamemode host, client, noBases host, client) before {got[0]}, after the resume (client2) "
             f"{got[1]}, want {B['mode']} both")
    checks = {f"{B['row'][n]}-relink": (lambda v, n=n: ok_ds(v[n], v[CRAFTS[n][5]])) for n in sky}
    checks.update({B["cint"]: lambda v: (v["CINT"] or {}).get("destKind") == "ufo", B["ids"]: lambda v: all(v[t] for t in bt)})
    polls, first = relink(host, c2, snap, checks, ev)
    for n in B["crafts"]:
        tp = tg[CRAFTS[n][5]]["point"]
        if (polls[0][n] or {}).get("status") != "STR_OUT" or dist(polls[0][n], tp) < FAR:
            capture(f"FX48-5 {n} at the first probe after the resume: {polls[0][n]} (want STR_OUT >= {FAR} rad from {tp})", host, c2)
    reads += [("host@relink", evs(host)), ("client2@relink", evs(c2))]
    for n in sky:
        cn, t = f"{B['row'][n]}-relink", CRAFTS[n][5]
        v = next((p for p in polls if p["t"] == first.get(cn)), polls[-1])
        cell(cn, cn in first, f"{n} {ds(v[n])} at {v['t']} s, want {AB}{v[t] and v[t]['id']} (m1 = the live mirror) STR_OUT within "
             f"{RELINK_S} s")
    ci = polls[-1]["CINT"] or {}
    cell(B["cint"], B["cint"] in first, f"client2 CINT destKind 'ufo' at {first[B['cint']]} s" if B["cint"] in first else
         f"client2 CINT destKind {ci.get('destKind')!r} {ci.get('displayStatus')!r}, want 'ufo' within {RELINK_S} s")
    bad = [] if B["ids"] in first else [f"live mirrors {[polls[-1][t] for t in bt]}"]
    for t in bt:
        got = {k: next((a for a in (f.get(part[TARGETS[t][0]]) or {}).get("alienBases", []) if a.get("id") == tg[t]["id"]), None)
               for k, f in files.items()}
        ev.setdefault("ids", {})[t] = got
        bad += [f"{k} {t}: {a and a.get('coopAlienBaseId', 'absent')}" for k, a in got.items()
                if not a or a.get("coopAlienBaseId") != tg[t]["coopId"]]
    cell(B["ids"], not bad, "; ".join(bad) or f"live mirrors at {first[B['ids']]} s; both saves' real bases carry coopAlienBaseId "
         f"{[tg[t]['coopId'] for t in bt]}")
    base = evs(c2)
    owners = {n: ("client2" if CRAFTS[n][0] == "client" else "host") for n in (B["crafts"] if b == "S" else sky)}
    events, arr = arrival(host, c2, snap, owners, ev, pos["X"])
    after = evs(c2)
    ev["refused"] = {"before": base, "after": after}
    for n in sky:
        a, cn, tp = arr.get(n) or {}, f"{B['row'][n]}-arrive", tg[CRAFTS[n][5]]["point"]
        c, pt, e = (a.get("crafts") or {}).get(n), patrols(events, owners[n], (b0[n] or {}).get("name")), a.get("ev") or {}
        head = f"{owners[n]} {n} arrival top {a.get('top')!r} at {a.get('t')} s texts {a.get('texts')}; CraftPatrolState naming {n} at {pt}"
        if b == "S" and n == "CSKY":            # the SEPARATE client's own craft never starts a battle
            ok = (a.get("top") == "CraftErrorState" and H9TEXT in a.get("texts", []) and not pt and (c or {}).get("destKind") == "base"
                  and e.get("coopClientBattleRefused") == (base.get("coopClientBattleRefused") or 0) + 1
                  and e.get("coopClientBattleRefusedLast") == f"landing:{keys[n][1]}")
            cell(cn, ok, f"{head}; refused {base.get('coopClientBattleRefused')} -> {e.get('coopClientBattleRefused')} last "
                 f"{e.get('coopClientBattleRefusedLast')!r}; {n} destKind {(c or {}).get('destKind')!r} (want CraftErrorState H9TEXT, +1, "
                 f"'landing:{keys[n][1]}', 'base', no patrol)")
        else:                                   # vanilla's landing prompt (the host; the gm3 X-COM client)
            ok = a.get("top") == "ConfirmLandingState" and dist(c, tp) <= NEAR and not pt and (
                owners[n] == "host" or after.get("coopClientBattleRefused") == base.get("coopClientBattleRefused"))
            cell(cn, ok, f"{head}; {n} {dist(c, tp):.4f} rad from the base; client2 refused {base.get('coopClientBattleRefused')} -> "
                 f"{after.get('coopClientBattleRefused')} (want ConfirmLandingState within {NEAR} rad, no patrol)")
    if b == "S":
        a, pi = arr.get("CINT") or {}, patrols(events, "client2", (b0["CINT"] or {}).get("name"))
        cell("R5-arrive", a.get("kind") in ("base", "none") and not pi, f"CINT {(a.get('from') or {}).get('destKind')!r} -> "
             f"{a.get('kind')!r} {(a.get('craft') or {}).get('status')} at {a.get('t')} s (want 'base', or home at X); CraftPatrolState "
             f"naming CINT at {pi}")
    reads += [("host@arrival", evs(host)), ("client2@arrival", after)]
    new = sorted(crash_set() - x["crash0"])
    bad = [f"{k} desyncSeen {v.get('desyncSeen')!r}" for k, v in reads if v.get("desyncSeen") is not False]
    bad += [f"{len(new)} new crash file(s) (first {os.path.basename(new[0])})"] if new else []
    ev["common"] = {"reads": reads, "newCrash": new}
    cell(f"{b}-common", not bad, "; ".join(bad) or f"desyncSeen false at {len(reads)} reads ({', '.join(k for k, _ in reads)}); "
         f"0 new crash files")

def row_ev(b, row, ev):
    """A row's EVIDENCE: ids, mirrors, the craft at each read (cmp), the peer's view, save nodes, arrival popups / transitions, walls."""
    rl, ar = ev.get("relink") or {}, ev.get("arrival") or {}
    crafts = dict({v: k for k, v in BOOTS[b]["row"].items()}, R5="CINT", **{"R5-gm3": "CINT"})
    polls, before = rl.get("polls") or [], ev.get("before") or {}
    if row in crafts:
        n = crafts[row]
        t, owner = CRAFTS[n][5], "client2" if CRAFTS[n][0] == "client" else "host"
        sel = [p for i, p in enumerate(polls) if i in (0, len(polls) - 1) or p["t"] in (rl.get("first") or {}).values()]
        return {"target": ev.get(t), "force": (ev.get("force") or {}).get(n), "before": cmp(before.get(n)), "mirror0": before.get(t),
                "peerBefore": before.get("peer"), "nodes": ev.get("nodes"), "refused": ev.get("refused"),
                "relink": {"first": rl.get("first"), "polls": len(polls), "s": rl.get("s"),
                           "at": [{"t": p["t"], n: cmp(p.get(n)), "mirror": p.get(t), "peer": p.get("peer")} for p in sel]},
                "arrival": [sub(e, ("t", "machine", "top", "texts", "dismiss", "ev")) | {n: cmp((e.get("crafts") or {}).get(n))}
                            for e in ar.get("events", []) if e.get("machine") == owner]
                + [{"t": e["t"], "from": cmp(e["from"]), "to": cmp(e["to"])} for e in ar.get("events", []) if e.get("craft") == n],
                "arrivedS": (ar.get("arrived") or {}).get(n), "final": cmp((ar.get("final") or {}).get(n))}
    if row.startswith("R4"):
        sv = ev.get("save") or {}
        return {"nodes": ev.get("nodes"), "ids": ev.get("ids"), "saveS": [sv.get("quickS"), sv.get("namedS")],
                "files": {k: {"bytes": f.get("bytes"), **{p: {q: (f.get(p) or {}).get(q) for q in ("alienBases", "waypoints")}
                                                         for p in ("world", "blob")}} for k, f in (sv.get("files") or {}).items()}}
    if row == "P-mode":
        return sub(ev, ("lobbyGamemode", "mode", "modeAfter"))
    return dict(sub(ev, ("common", "mode", "bases", "seats", "resumeS", "wall", "load0", "load1", "error")), arrivalS=ar.get("s"),
                relinkPopups=[sub(e, ("t", "machine", "top", "texts", "dismiss")) for e in rl.get("popups", [])])

def run_boot(b, tag=None):
    """One boot (S or P): host and client, the rows, then every machine shut down; EVIDENCE and ROW lines per row."""
    BOOT["tag"], tag = b, tag or TAGS[b]
    x = {"boot": b, "tag": tag, "host": GameClient("host", None, make_user_dir(tag + "_host")),
         "client": GameClient("client", None, make_user_dir(tag + "_client")), "client2": None, "crash0": crash_set()}
    ev = EV[b] = {"load0": load()}
    t0, cells = time.time(), [c for r in ROWS[b].values() for c in r]
    try:
        boot(b, x, ev)
    except FixtureMiss as e:
        block(cells, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        ev["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"[ERROR] boot {b}: {ev['error']}", flush=True)
        block(cells, f"error {ev['error']}")
    finally:
        ev["wall"] = round(time.time() - t0, 1)
        for gc in (x["client2"], x["client"], x["host"]):
            try:
                if gc is not None and gc.proc is not None:
                    gc.shutdown()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR] shutdown {gc.name}: {e}", flush=True)
        ev["load1"] = load()
        for row, names in ROWS[b].items():
            print(f"EVIDENCE {row}: {json.dumps(row_ev(b, row, ev), sort_keys=True, default=str)}", flush=True)
            row_verdict(row, names)
    return ev

def main():
    t0 = time.time()
    for b in ("S", "P"):
        run_boot(b)
    allc = [c for b in ROWS for r in ROWS[b].values() for c in r]
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== W2-H48 craft -> mirrored alien base across a save and reload: {len(RESULTS) - len(fails)}/{len(allc)} cells PASS, "
          f"wall {time.time() - t0:.1f} s, cpu {EV.get('S', {}).get('load0')} -> {EV.get('P', {}).get('load1')} ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}{' (expected red)' if n in RED else ''}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(allc) else 2)

if __name__ == "__main__":
    main()
