"""W2-H26 row CV (boot C, classic gamemode 1): a player-side conversion. Soldier H, staged to respawn as S_TYPE on the
player side, dies to C1's lever shot; the host builds the new unit P (SavedBattleGame::convertUnit copies H's
spawnUnitFaction onto it) and the second player builds its copy from the host's unit record (`unitsAdded`). The copy
must carry the host's spawnUnitFaction, so the spawn ev's `synced` hash matches and the battle goes on.

Spec: docs repo rewrite/prompts/w2h26_conversion_spawn_faction.md section (f) (orchestrator ruling R-U4-A-3, F11313;
Q-H26-1 (a): the TEST-ONLY `synced_census` probe and the recompute below; Q-H26-3 (a): CV-explain is a cell).
Constants: rewrite/w2h26-task0/CONSTANTS.md (TASK 0 boots Ca, Cb on the probe build, every pin equal).

Boot C (key 48744): R5-U4's boot C - the Skyranger's crew cut to its first KEEP soldiers, one STR_TANK_CANNON loaded,
STR_SMALL_SCOUT, roster and map seed 1 - then pin_ai_neutral, every live unit's reactions 0, the host idle.
Staging: the rifle on C1 (both, client first), C1 teleported to STAGE_S facing STAGE_DIR (place_deterministic), the
pre-shot synced_census on both, H's spawn staging {S_TYPE, player, respawn} (both). The action: host set_seed SEED_S,
host battle_fire {C1, snap, FLOOR_S, C1's TU}; the host's chain idle (host only: the client may be frozen), then at most
CLIENT_S s for the client's desyncSeen or its catch-up; then every read.
  CV-pre      MAP_FP_C and the bring-up ids on both; no unit P_ID before the shot; C1's rifle ids equal on both;
              place_deterministic ok; H's staging replies {S_TYPE, 0, true} on both; the pre-shot census_diff == []
              and synced_sum == hash_now synced on each machine
  CV-chain    exactly one new host context {host, shoot, C1}; its evs since seq0 have exactly CHAIN_KINDS; the spawn
              payload {unit P_ID, cause convert, from H}; the client's ev log holds the spawn ev's seq
  CV-unit     P_ID on both: S_TYPE, faction 0, originalFaction 0, not out, on H's tile; H status 6 on both
  CV-faction  synced_census: P_ID's spawnUnitFaction is "player" on the host AND on the client
  CV-sync     desyncSeen false on both; the client's lastSeqApplied == the host's lastSeqEmitted; every hash bucket
              EQUAL (saveBlob and revealHostile included)
  CV-census   the post-chain census_diff(host, client) == [] (every synced row of every unit, item, node, door tile
              and the battle)
  CV-explain  each machine's synced_sum == its hash_now synced; with a client `[coop-hash] DESYNC:` line: bucket
              synced, the spawn ev's seq, kind spawn, got == the client's synced, and the client census with ONLY
              P's spawnUnitFaction taken from the host recomputes to its expect; without one: host synced == client's
  CV-common   no new crash file
EVIDENCE only: P's census rows, every census_diff row, the DESYNC line, the client's lastHashVerify, the host's deltaRing
records after the spawn seq, both hash_now, the chain's seqs, host infoboxes, the wall and CPU.

RED on the unchanged build + the probe (commit A1): CV-faction, CV-sync, CV-census; every other cell PASS (CV-explain
proves P's spawnUnitFaction is the only synced row that differed at the spawn ev). GREEN (commit A2): every cell PASS.
One EVIDENCE line, one PASS/FAIL line per cell, then the row verdict; every cell is evaluated after a failure. A boot or
staging step past its bound prints ONE CAPTURE line and fails every cell "boot" / "staging". run in the
foreground to completion. ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.

Run:  python tools/coop_test/test_convert_spawn_faction.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, cpu_load  # noqa: E402
import session  # noqa: E402
from session import battle_state, event_state  # noqa: E402
import repro_atom_walk as RAW  # noqa: E402
import test_pvp_gm3 as G3F  # noqa: E402
from test_client_shoot import new_contexts  # noqa: E402
from test_delta_core import both  # noqa: E402
from test_host_combat import evs_since  # noqa: E402
from test_ai_origins import host_payloads  # noqa: E402

KEY = "48744"
SEED_ROSTER = SEED_MAP = SEED_S = 1
KEEP = 3                          # the crew rule: the Skyranger keeps its first three soldiers (C1, C2, H)
MAP_FP_C = -4.48310638993e+18     # both machines (TASK 0 Ca, Cb)
C1, C2, H = 8, 9, 10              # C1 / C2 the client's (seat 1), H the host's (seat 0)
TANK, ALIEN, P_ID = 1000000, 1000001, 1000002
S_TYPE = "STR_SECTOID_SOLDIER"    # what H converts into (no spawn unit of its own)
STAGE_S, STAGE_DIR = (20, 19, 0), 4   # C1's open-ground stage
FLOOR_S = (24, 19, 0)             # the snap target; the projectile's end converts H
CHAIN_KINDS = ["turn", "shot", "hit", "spawn", "bt_action_end"]
FACTION_PLAYER, STATUS_DEAD = 0, 6
STEP_S, CLIENT_S, LOG_FLUSH_S = 30, 15, 3
DESYNC_RE = re.compile(r"\[coop-hash\] DESYNC: bucket=(\S+) seq=(\d+) kind=(\S+) expect=([0-9a-f]+) got=([0-9a-f]+)")
CELLS = ("CV-pre", "CV-chain", "CV-unit", "CV-faction", "CV-sync", "CV-census", "CV-explain", "CV-common")

# ---- W2-H26 SYNCED_SUM (spec rewrite/prompts/w2h26_conversion_spawn_faction.md Appendix C; copied verbatim) ----
# The `synced` bucket of SharedEcon.cpp computeBattleHashes, recomputed from ONE TestServer `synced_census` reply:
# per entity an FNV that mixes a kind tag (1 unit, 2 door tile, 3 node, 4 item, 5 battle) and the id, then the rows
# in the bucket's own order; the bucket is the sum of the entity values mod 2**64, printed "%016x" like hash_now.
import copy

MASK64 = (1 << 64) - 1
FNV_OFFSET = 1469598103934665603
FNV_PRIME = 1099511628211
WIRE_FACTION = {"player": 0, "hostile": 1, "neutral": 2}  # field_poke's wire strings (TestServer coopFieldPokeFactionWire)
CENSUS_KINDS = ("units", "items", "nodes", "tiles")


def _mix(h, v):
    return ((h ^ (int(v) & MASK64)) * FNV_PRIME) & MASK64


def _mix_str(h, s):
    f = FNV_OFFSET
    for c in s.encode("utf-8"):
        f = ((f ^ c) * FNV_PRIME) & MASK64
    return ((h ^ f) * FNV_PRIME) & MASK64


def _mix_tags(h, tags):
    t = list(tags)
    while t and t[-1] == 0:
        t.pop()
    h = _mix(h, len(t))
    for v in t:
        h = _mix(h, v)
    return h


def _b(v):
    return 1 if v else 0


def unit_row(u):
    y = _mix(_mix(FNV_OFFSET, 1), u["id"])
    y = _mix(y, _b(u["onTile"]))
    y = _mix(y, u["dir"])
    y = _mix(y, u["turretDir"])
    y = _mix(y, u["status"])
    y = _mix(y, _b(u["floating"]))
    for a in u["armor"]:
        y = _mix(y, a)
    y = _mix(y, _b(u["wantsToSurrender"]))
    y = _mix(y, _b(u["isSurrendering"]))
    y = _mix(y, u["moraleRestored"])
    y = _mix_str(y, u["spawnUnit"])
    y = _mix(y, _b(u["respawn"]))
    y = _mix(y, WIRE_FACTION[u["spawnUnitFaction"]])
    y = _mix(y, _b(u["alreadyRespawned"]))
    y = _mix_str(y, u["reactPref"])
    y = _mix(y, _b(u["reactOffLeft"]))
    y = _mix(y, _b(u["reactOffRight"]))
    y = _mix_tags(y, u["tags"])
    y = _mix_str(y, u["name"])
    y = _mix_str(y, u["rawName"])
    y = _mix(y, u["seat"])  # the seat tag, right after the two names (SharedEcon.cpp computeBattleHashes)
    spec = sorted(u["specialWeapons"])
    y = _mix(y, len(spec))
    for s in spec:
        y = _mix(y, s)
    return y


def item_row(it):
    y = _mix(_mix(FNV_OFFSET, 4), it["id"])
    y = _mix(y, it["previousOwner"])
    y = _mix(y, it["unit"])
    for a in it["ammo"]:
        y = _mix(y, a)
    y = _mix(y, _b(it["fuseEnabled"]))
    for q in it["medikit"]:
        y = _mix(y, q)
    y = _mix(y, _b(it["droppedOnAlienTurn"]))
    y = _mix(y, _b(it["xcomProperty"]))
    return _mix_tags(y, it["tags"])


def battle_row(b):
    y = _mix(_mix(FNV_OFFSET, 5), 0)
    y = _mix(y, b["objectivesDestroyed"])
    for cell in b["moduleMap"]["cells"]:
        for v in cell:
            y = _mix(y, v)
    y = _mix(y, _b(b["bughuntMode"]))
    y = _mix(y, b["turn"])
    y = _mix(y, WIRE_FACTION[b["side"]])
    y = _mix_tags(y, b["tags"])
    rm = b["reinforcementsMemory"]
    y = _mix(y, len(rm))
    for k in sorted(rm):
        y = _mix_str(y, k)
        y = _mix(y, rm[k])
    return y


def synced_sum(c):
    """The `synced` bucket recomputed from one synced_census reply `c`, as 16 lowercase hex digits."""
    s = 0
    for t in c["tiles"]:
        s += _mix(_mix(_mix(FNV_OFFSET, 2), t["i"]), t["doorBits"])
    for n in c["nodes"]:
        s += _mix(_mix(_mix(FNV_OFFSET, 3), n["id"]), n["type"])
    for it in c["items"]:
        s += item_row(it)
    for u in c["units"]:
        s += unit_row(u)
    s += battle_row(c["battle"])
    return format(s & MASK64, "016x")


def census_diff(h, c):
    """Every row that differs between two synced_census replies: [(kind, id, field, host value, client value)];
    an entity on one machine only is one row with field "<entity>"."""
    out = []
    for kind in CENSUS_KINDS:
        key = "i" if kind == "tiles" else "id"
        hh = {e[key]: e for e in h[kind]}
        cc = {e[key]: e for e in c[kind]}
        for i in sorted(set(hh) | set(cc)):
            if i not in hh or i not in cc:
                out.append((kind, i, "<entity>", i in hh, i in cc))
                continue
            for f in sorted(set(hh[i]) | set(cc[i])):
                if hh[i].get(f) != cc[i].get(f):
                    out.append((kind, i, f, hh[i].get(f), cc[i].get(f)))
    for f in sorted(set(h["battle"]) | set(c["battle"])):
        if h["battle"].get(f) != c["battle"].get(f):
            out.append(("battle", 0, f, h["battle"].get(f), c["battle"].get(f)))
    return out


def patched(c, h, rows):
    """A copy of the client census `c` with ONLY the listed (kind, id, field) rows taken from the host census `h`."""
    p = copy.deepcopy(c)
    for kind, i, f in rows:
        if kind == "battle":
            p["battle"][f] = h["battle"][f]
            continue
        key = "i" if kind == "tiles" else "id"
        src = [e for e in h[kind] if e[key] == i][0]
        [e for e in p[kind] if e[key] == i][0][f] = src[f]
    return p
# ---- end SYNCED_SUM ----


def units(gc):
    return {u["id"]: u for u in battle_state(gc).get("units", [])}


def pos(u):
    return (u.get("x"), u.get("y"), u.get("z")) if u else None


def wait_until(pred, timeout, interval):
    t0 = time.time()
    while True:
        if pred():
            return True, round(time.time() - t0, 2)
        if time.time() - t0 > timeout:
            return False, round(time.time() - t0, 2)
        time.sleep(interval)


def cpu_pct():
    """EVIDENCE: the machine's total CPU over the last 2 s (S24; cpu_load, D307); None when unreadable."""
    return cpu_load()["cpu"]


def synced(gc):
    return (gc.cmd({"cmd": "hash_now", "buckets": ["synced"]}).get("h") or {}).get("synced")


def recompute(c):
    try:
        return synced_sum(c)
    except Exception as e:
        return f"recompute failed: {type(e).__name__}: {e}"


def val(host, client):
    """The synced_census on both machines: (census_diff, {machine: [recompute, hash_now synced]}, censuses)."""
    cens = {gc.name: gc.cmd({"cmd": "synced_census"}) for gc in (host, client)}
    sums = {gc.name: [recompute(cens[gc.name]), synced(gc)] for gc in (host, client)}
    if not all(c.get("ok") for c in cens.values()):
        return f"synced_census failed: { {k: c.get('error') for k, c in cens.items()} }", sums, cens
    return census_diff(cens["host"], cens["client"]), sums, cens


def p_row(cens, name):
    rows = [u for u in (cens.get(name) or {}).get("units") or [] if u.get("id") == P_ID]
    return rows[0] if rows else None


def desync_line(gc):
    """The last `[coop-hash] DESYNC:` line of this machine's openxcom.log, parsed; None without one."""
    last = None
    for ln in G3F.log_lines(gc):
        m = DESYNC_RE.search(ln)
        if m:
            last = {"bucket": m.group(1), "seq": int(m.group(2)), "kind": m.group(3), "expect": m.group(4),
                    "got": m.group(5)}
    return last


def host_chain_idle(host, dismissed):
    """R5-U4 TASK 0 (t0.py): the host's chain is idle; a host InfoboxState is dismissed host-only (EVIDENCE)."""
    lw = host.cmd({"cmd": "list_widgets"}).get("state", "")
    if "Infobox" in lw:
        dismissed.append((lw.split(">")[-1], host.cmd({"cmd": "dismiss_popup"}).get("handled")))
        return None
    bs = battle_state(host)
    return (bs.get("pendingStates") == 0 and not bs.get("isBusy") and event_state(host).get("busyOwnerSeat") == -1) or None


# ===================== boot C (R5-U4 TASK 0 boot_c: lobby, pre_seat, drive) =====================


def bring_up(host, client, ev):
    m = (host, client)

    def lobby():
        host.spawn(); host.connect(); client.spawn(); client.connect()
        host.ok({"cmd": "set_seed", "seed": SEED_ROSTER})
        RAW.skirmish_host(host, KEY)
        RAW.skirmish_client_at_browser(client)
        client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": KEY, "player": RAW.CLIENT_PLAYER})
        host.wait_for("host popup", lambda: session.has_state(host, "Profile"))
        client.wait_for("client popup", lambda: session.has_state(client, "Profile"))
        host.ok({"cmd": "profile_ok"}); client.ok({"cmd": "profile_ok"})
        host.wait_for("start offered", lambda: RAW.lobby(host).get("buttonVisible") or None)
    G3F.guarded("C lobby", lobby, m)
    pre = {}

    def pre_seat(h):
        r = h.cmd({"cmd": "newbattle_craft", "type": "STR_SKYRANGER"})
        assert r.get("ok"), f"newbattle_craft: {r}"
        br = h.cmd({"cmd": "base_report"})
        sky = [c for c in br.get("crafts") or [] if c.get("type") == "STR_SKYRANGER"]
        assert len(sky) == 1, f"base_report crafts {br.get('crafts')} (want exactly one STR_SKYRANGER)"
        cid, ctype = sky[0]["id"], sky[0]["type"]
        crew = [s["id"] for s in br.get("soldiers") or [] if s.get("craft") == cid]
        pre.update(crew0=crew, kept=crew[:KEEP], assign=[])
        for sid in crew[KEEP:]:
            a = h.cmd({"cmd": "craft_assign", "soldier_id": sid, "craft_id": cid, "on": False})
            pre["assign"].append((sid, a.get("ok"), a.get("seated"), a.get("error")))
        eq = h.cmd({"cmd": "craft_equip", "item": "STR_TANK_CANNON", "count": 1, "craft_id": cid})
        cv = h.cmd({"cmd": "base_screen_op", "op": "craft_vehicles", "craft_id": cid, "craft_type": ctype})
        pre.update(equip=eq.get("moved"), vehicles=cv.get("vehicles"))
        assert all(x[1] and x[2] is False for x in pre["assign"]), f"craft_assign off: {pre['assign']}"
        assert eq.get("moved") is True, f"craft_equip: {eq}"
        assert (cv.get("vehicles") or {}).get("STR_TANK_CANNON") == 1, f"craft_vehicles: {cv}"

    seated = {}
    G3F.guarded("C drive", lambda: session.drive_to_battlescape(
        host, client, seated, mission="STR_SMALL_SCOUT", seat_count=2, pre_seat=pre_seat,
        pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": SEED_MAP})), m)
    ev["preSeat"], ev["seated"] = pre, seated.get("soldierIds")
    ev["pinned"] = G3F.guarded("C pin", lambda: session.pin_ai_neutral(host, client, tag="w2h26"), m)
    G3F.guarded("C reactions", lambda: G3F.reactions_zero(host, client), m)
    G3F.guarded("C idle", lambda: session.wait_host_idle(host, client, timeout=STEP_S), m)


def stage(host, client, ev):
    m = (host, client)
    g = G3F.guarded("CV staging", lambda: both(host, client, {
        "cmd": "battle_give", "unit": C1, "item": "STR_RIFLE", "ammo": "STR_RIFLE_CLIP", "slot": "right",
        "clear_hands": True}, ("weaponId", "ammoId")), m)
    ev["rifle"] = [g.get("weaponId"), g.get("ammoId")]
    move = {"cmd": "battle_teleport_unit", "unit": C1, "x": STAGE_S[0], "y": STAGE_S[1], "z": STAGE_S[2],
            "dir": STAGE_DIR}
    res = G3F.guarded("CV staging", lambda: session.place_deterministic(host, client, [move], what="w2h26 CV"), m)
    ev["place"] = res[0][0]
    ev["preDiff"], ev["preSums"], _ = val(host, client)
    r = G3F.guarded("CV staging", lambda: both(host, client, {
        "cmd": "battle_set_unit_state", "unit": H, "spawnUnit": S_TYPE, "spawnUnitFaction": FACTION_PLAYER,
        "respawn": True}, ("spawnUnit", "spawnUnitFaction", "respawn")), m)
    ev["hStaging"] = [r.get("spawnUnit"), r.get("spawnUnitFaction"), r.get("respawn")]


def pre_cell(host, client, ev):
    bad = []
    hb, cb = battle_state(host), battle_state(client)
    uh, uc = units(host), units(client)
    ev["mapFp"] = [hb.get("mapFingerprint"), cb.get("mapFingerprint")]
    if ev["mapFp"] != [MAP_FP_C, MAP_FP_C]:
        bad.append(f"mapFingerprint host/client {ev['mapFp']} (want {MAP_FP_C} on both)")
    ids = {"seated": ev["seated"], "kept": ev["preSeat"].get("kept"),
           "tanks": [sorted(i for i, u in us.items() if u.get("type") == "STR_TANK_CANNON") for us in (uh, uc)],
           "alien": [(us.get(ALIEN) or {}).get("type") for us in (uh, uc)], "P": [P_ID in uh, P_ID in uc]}
    ev["ids"] = ids
    if ids != {"seated": [C1, C2], "kept": [C1, C2, H], "tanks": [[TANK], [TANK]], "alien": [S_TYPE, S_TYPE],
               "P": [False, False]}:
        bad.append(f"bring-up ids {ids} (want seated [{C1}, {C2}], kept [{C1}, {C2}, {H}], tank {TANK} and alien "
                   f"{ALIEN} {S_TYPE} on both, no unit {P_ID} before the shot)")
    if not all(isinstance(x, int) for x in ev["rifle"]):
        bad.append(f"C1's rifle ids {ev['rifle']} (want equal ints on both)")
    pl = ev["place"]
    c1 = [pos(uh.get(C1)), pos(uc.get(C1))]
    if not pl.get("ok") or (pl["to"]["x"], pl["to"]["y"], pl["to"]["z"], pl["dir"]) != STAGE_S + (STAGE_DIR,) \
            or c1 != [STAGE_S, STAGE_S]:
        bad.append(f"place_deterministic reply {pl}, C1 host/client {c1} (want {STAGE_S} dir {STAGE_DIR})")
    if ev["hStaging"] != [S_TYPE, FACTION_PLAYER, True]:
        bad.append(f"H staging replies {ev['hStaging']} (want [{S_TYPE}, 0, True] on both)")
    s = ev["preSums"]
    if ev["preDiff"] != [] or s["host"][0] != s["host"][1] or s["client"][0] != s["client"][1]:
        bad.append(f"pre-shot census_diff {ev['preDiff']} (want []); [recompute, hash_now synced] {s} (want equal)")
    return (not bad, "; ".join(bad) or f"MAP_FP_C, ids, rifle {ev['rifle']}, stage, H staging, pre-shot census equal")


def row_cv(host, client, crash0, ev):
    cells = {"CV-pre": pre_cell(host, client, ev)}
    uh0 = units(host)
    h_tile, tu = pos(uh0.get(H)), (uh0.get(C1) or {}).get("tu")
    e0 = event_state(host)
    seq0, ctx0 = e0.get("lastSeqEmitted") or 0, e0.get("closedContexts") or []
    host.ok({"cmd": "set_seed", "seed": SEED_S})
    fire = host.cmd({"cmd": "battle_fire", "unit": C1, "mode": "snap", "x": FLOOR_S[0], "y": FLOOR_S[1],
                     "z": FLOOR_S[2], "tu": tu})
    dismissed = []
    ev["chainIdle"] = wait_until(lambda: host_chain_idle(host, dismissed), STEP_S, 0.1)
    ev["clientDone"] = wait_until(lambda: event_state(client).get("desyncSeen") or event_state(client).get(
        "lastSeqApplied") == event_state(host).get("lastSeqEmitted"), CLIENT_S, 0.1)
    he, ce = event_state(host), event_state(client)
    dl = None
    if ce.get("desyncSeen"):
        wait_until(lambda: desync_line(client), LOG_FLUSH_S, 0.25)
        dl = desync_line(client)
    new = new_contexts(ctx0, he.get("closedContexts"))
    hev, cev = evs_since(host, seq0), evs_since(client, seq0)
    aid = new[0].get("actionId") if len(new) == 1 else None
    mine = [e for e in hev if e["actionId"] == aid]
    spawn = [e["seq"] for e in mine if e["kind"] == "spawn"]
    pl = host_payloads(host, spawn, timeout=LOG_FLUSH_S) if spawn else {}
    uh, uc = units(host), units(client)
    diff, sums, cens = val(host, client)
    ev.update(seq0=seq0, fire={k: fire.get(k) for k in ("ok", "error", "tuCost", "weaponId", "ammoId")},
              infoboxes=dismissed, newCtx=new, hostEvs=[(e["seq"], e["kind"], e["actionId"]) for e in hev],
              clientEvs=[(e["seq"], e["kind"], e["actionId"]) for e in cev],
              spawnPayload={s: v.get("payload") for s, v in pl.items()}, desyncLine=dl,
              lastHashVerify=ce.get("lastHashVerify"),
              deltaRing=[d for d in he.get("deltaRing") or [] if spawn and (d.get("seq") or 0) > spawn[0]],
              P={"host": p_row(cens, "host"), "client": p_row(cens, "client")}, censusDiff=diff, sums=sums,
              hashNow={gc.name: gc.cmd({"cmd": "hash_now", "full": True}).get("h") for gc in (host, client)})
    ch = []
    if len(new) != 1 or (new[0].get("origin"), new[0].get("kind"), new[0].get("actorId")) != ("host", "shoot", C1):
        ch.append(f"new host closedContexts {new} (want exactly one {{host, shoot, {C1}}})")
    if [e["kind"] for e in mine] != CHAIN_KINDS:
        ch.append(f"ev kinds of actionId {aid} {[e['kind'] for e in mine]} (want {CHAIN_KINDS})")
    sp = pl.get(spawn[0], {}).get("payload") if spawn else None
    if sp != {"unit": P_ID, "cause": "convert", "from": H}:
        ch.append(f"spawn payload {sp} (want {{unit {P_ID}, cause convert, from {H}}})")
    if not spawn or spawn[0] not in [e["seq"] for e in cev]:
        ch.append(f"client ev log seqs {[e['seq'] for e in cev]} lack the spawn ev {spawn}")
    cells["CV-chain"] = (not ch, "; ".join(ch) or f"one {{host, shoot, {C1}}} with {CHAIN_KINDS}, spawn payload ok, "
                                                   f"the client holds the spawn seq {spawn}")
    uv = [{k: (u.get(P_ID) or {}).get(k) for k in ("type", "faction", "originalFaction", "isOut")} for u in (uh, uc)]
    pp = [pos(uh.get(P_ID)), pos(uc.get(P_ID))]
    hs = [(uh.get(H) or {}).get("status"), (uc.get(H) or {}).get("status")]
    want = {"type": S_TYPE, "faction": FACTION_PLAYER, "originalFaction": FACTION_PLAYER, "isOut": False}
    cells["CV-unit"] = (uv == [want, want] and pp == [h_tile, h_tile] and hs == [STATUS_DEAD, STATUS_DEAD],
                        f"P {P_ID} host/client {uv} at {pp} (want {want} on H's tile {h_tile}); H status {hs} (want 6)")
    pf = [(ev["P"][k] or {}).get("spawnUnitFaction") for k in ("host", "client")]
    cells["CV-faction"] = (pf == ["player", "player"], f"P {P_ID} spawnUnitFaction host/client {pf} (want player on both)")
    he, ce = event_state(host), event_state(client)
    ds = [he.get("desyncSeen"), ce.get("desyncSeen")]
    seqs = [ce.get("lastSeqApplied"), he.get("lastSeqEmitted")]
    hashed = G3F.hash_now(host, client)
    cells["CV-sync"] = (ds == [False, False] and seqs[0] == seqs[1] and hashed == "all buckets EQUAL",
                        f"desyncSeen host/client {ds} (want False/False); client lastSeqApplied / host lastSeqEmitted "
                        f"{seqs} (want equal); hash {hashed}")
    cells["CV-census"] = (diff == [], f"post-chain census_diff(host, client) {diff} (want [])")
    ex = []
    for k in ("host", "client"):
        if sums[k][0] != sums[k][1]:
            ex.append(f"{k} [recompute, hash_now synced] {sums[k]} (want equal)")
    if dl:
        if dl["bucket"] != "synced" or dl["kind"] != "spawn" or not spawn or dl["seq"] != spawn[0]:
            ex.append(f"DESYNC line {dl} (want bucket synced, seq {spawn}, kind spawn)")
        if dl["got"] != sums["client"][1]:
            ex.append(f"DESYNC got {dl['got']} != the client's synced {sums['client'][1]}")
        try:
            ps = synced_sum(patched(cens["client"], cens["host"], [("units", P_ID, "spawnUnitFaction")]))
        except Exception as e:
            ps = f"patch failed: {type(e).__name__}: {e}"
        ev["patchedClient"] = ps
        if ps != dl["expect"]:
            ex.append(f"client census with only P's spawnUnitFaction from the host recomputes to {ps} (want the "
                      f"DESYNC expect {dl['expect']}): another synced row differed at the spawn ev")
    elif sums["host"][1] != sums["client"][1]:
        ex.append(f"no DESYNC line and synced host/client {sums['host'][1]} / {sums['client'][1]} (want equal)")
    cells["CV-explain"] = (not ex, "; ".join(ex) or (
        f"recompute == hash_now on both; DESYNC {dl['bucket']} seq {dl['seq']} explained by P's spawnUnitFaction alone "
        f"({ev.get('patchedClient')} == expect)" if dl else "recompute == hash_now on both; no DESYNC, synced equal"))
    crash = sorted(session._crash_log_snapshot() - crash0)
    cells["CV-common"] = (not crash, f"new crash files {crash} (want none)")
    return cells, ev


def boot_c(t0, cpu0):
    host = GameClient("host", None, make_user_dir("w2h26_c_host"))
    client = GameClient("client", None, make_user_dir("w2h26_c_client"))
    try:
        ev = {}
        try:
            bring_up(host, client, ev)
            crash0 = session._crash_log_snapshot()
        except G3F.Miss:
            return G3F.fail_all((("CV", CELLS),), "boot (FIXTURE-STOP, see the CAPTURE line)")
        try:
            stage(host, client, ev)
        except G3F.Miss:
            return G3F.fail_all((("CV", CELLS),), "staging (see the CAPTURE CV staging line)")

        def row():
            cells, out = row_cv(host, client, crash0, ev)
            out.update(wall=round(time.time() - t0, 1), cpu=[cpu0, cpu_pct()])
            return cells, out
        return G3F.run_row("CV", CELLS, row)
    finally:
        G3F.shut(host, client)


def main():
    t0 = time.time()
    fails = boot_c(t0, cpu_pct())
    print("ALL CELLS PASS" if not fails else f"FAILED: {fails} cell(s)", flush=True)
    print(f"test_convert_spawn_faction: {'PASS' if not fails else 'FAIL'} in {time.time() - t0:.1f}s", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == "__main__":
    main()
