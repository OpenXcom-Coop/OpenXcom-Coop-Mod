"""Older PvP campaign saves where the host plays X-COM (game mode 2) are upgraded to one world: the X-COM world that
already is the host file's body, every base owned by the X-COM player by name, the alien player's embedded world
dropped, header saveSchema 4. The upgrade writes <stem>_upgraded.sav and never touches the original, and the upgraded
file loads on the host. Saves where the host plays the aliens (game mode 3) keep today's routing.

ONE host instance, no lobby (dir pvp_old_upgrade_host). First command: pvp_one_world {gamemode 2, on true}, read back
from coop_sides (oneWorldHostPlaysXcom true, oneWorldHostPlaysAliens false). Saves folder (xcom1/):
  pvp_xcom_host_geoscape.sav       this build's host save at the Geoscape: schema 2, game mode 2, the alien player's
                                   stand-in world embedded in coopClientSaves (fixtures/)
  pvp_gm2_battle.sav               an older version's mid-battle save, game mode 2, nothing embedded (fixtures/)
  pvp_gm3_battle.sav               an older version's mid-battle save, game mode 3 (fixtures/)
  pvp_embed_host.sav               synth.pvp_embed_host(): schema 2, game mode 2, HostBase, roster HostGuy / Bob, the
                                   alien player's world (ClientBase) embedded
  pvp_embed_host_stamp4.sav        the same with its ONE header line saveSchema 2 -> 4 (CRLF-aware split)
  pvp_xcom_host_geoscape_next.sav  the upgraded Geoscape save with its ONE header line saveSchema 4 -> 5 (written
                                   once that upgrade exists)
Expected values (base names, lon / lat, coopbaseid, soldier and craft ids, funds, discovered, ids, object counts,
battle keys and units) are read from the source files at run time and printed in EVIDENCE.

  xcom_host_detect        upgrade_detect of the Geoscape, battle and synth saves: each legacy / embed / needsUpgrade
                          true / schema 2
  xcom_host_geo_file      upgrade_run of the Geoscape save: success, no errors; the upgraded file: header saveSchema 4,
                          coopCampaignType 0, coopPlayers unchanged, no coopPvpBorrowed; body coop_gamemode 2,
                          coop_save_owner_player_id 0, no_bases false, no coopClientSaves, no separateCampaign; bases
                          equal in order (name, lon, lat, coopbaseid, soldier ids, craft ids, facility count), each
                          ownerplayername the first roster name; every base soldier with coop 0 has ownerplayerid 0;
                          funds, discovered, ids equal; ufos / alienMissions / missionSites / alienBases counts equal;
                          the one-world report lines, in order: "Schema 4: ...", "All N base(s) now belong to <name>.",
                          "Dropped the alien player's world (M base(s))." (M = the embedded world's bases)
  xcom_host_battle_file   the same for the mid-battle save (no "Dropped" line: nothing embedded), plus header mission,
                          target, craftOrBase, turn equal, no coopBattleProtocol, battleGame turn and unit ids equal
  xcom_host_synth_file    the same for the synth save, plus bases == [HostBase] owned by HostGuy, soldiers 1 and 2
                          ownerplayerid 0, "Dropped the alien player's world (1 base(s))."
  xcom_host_stamp_guard   upgrade_detect of the stamp-4 file: legacy / embed / schema 3, and its upgrade succeeds with
                          stamp 4 and no coopClientSaves; upgrade_detect of the stamp-5 file: unknown_future
  alien_host_untouched    upgrade_detect of the game-mode-3 battle save: current (its one-world switch is off)
  xcom_host_loads         load_save_menu of the upgraded Geoscape save: HostMenu within LOAD_S, no ErrorMessageState,
                          no SaveUpgradeDialogState; get_coop.gamemode 2; geo_state: every base's ownerPlayerName is
                          the first roster name, worldFunds (the world's own funds: before START HOST this machine is
                          not seat 0 yet, so geo_state.funds shows the alien player's amount) == the source's last
                          funds
  xcom_host_battle_loads  disconnect_to_menu, then load_save_menu of the upgraded battle save: HostMenu within LOAD_S;
                          ONE conversion line whose counts == GM2_CONVERT; no refusal line
  common                  0 new crash files; the host alive; every placed file's sha256 unchanged; every other file in
                          the saves folder ends in _upgraded.sav
Without the fix: exit 2, 2/9 - FAIL xcom_host_detect, xcom_host_geo_file, xcom_host_battle_file, xcom_host_synth_file,
xcom_host_stamp_guard, xcom_host_loads, xcom_host_battle_loads (the saves load as they are, so nothing is upgraded);
PASS alien_host_untouched, common. With it: 9/9.

One EVIDENCE line per row, one PASS / FAIL line per cell; every row runs after a failure. A boot miss prints ONE
CAPTURE line and FAILs every cell "boot". ONE run is the result, no skip path; exit 0 only when every cell passes,
else 2.

Run:  python tools/coop_test/test_pvp_old_save_upgrade.py
"""

import base64
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "fixtures"))

import yaml  # noqa: E402

from harness import GameClient, make_user_dir, cpu_load  # noqa: E402
import synth  # noqa: E402
import test_campaign_resume_roles as RR  # noqa: E402  (pure helpers: capture, stack, crash_set, wait, alive)
import test_old_battle_resume as OB  # noqa: E402  (CONVERT, CONVERT_RE, REFUSAL)
from test_old_pvp_battle_resume import GM2_CONVERT  # noqa: E402

# ----- fixture values -----
TAG = "pvp_old_upgrade_host"
FIXTURES = os.path.join(HERE, "fixtures")
GEO = "pvp_xcom_host_geoscape.sav"
BATTLE = "pvp_gm2_battle.sav"
ALIEN_HOST = "pvp_gm3_battle.sav"
SYNTH = "pvp_embed_host.sav"
STAMP4 = "pvp_embed_host_stamp4.sav"
NEXT = "pvp_xcom_host_geoscape_next.sav"
SYNTH_BASES, SYNTH_OWNER, SYNTH_SOLDIERS = ["HostBase"], "HostGuy", [1, 2]
SCHEMA_LINE = "Schema 4: the PvP campaign is now one world, the X-COM player's."
WRITTEN_PREFIX = "Upgraded save written: "
LOAD_S, LOG_S, MENU_S = 30, 10, 30
CELLS = ["xcom_host_detect", "xcom_host_geo_file", "xcom_host_battle_file", "xcom_host_synth_file",
         "xcom_host_stamp_guard", "alien_host_untouched", "xcom_host_loads", "xcom_host_battle_loads", "common"]
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
stack, crash_set, wait, alive = RR.stack, RR.crash_set, RR.wait, RR.alive


class FixtureMiss(Exception):
    pass


RESULTS = []          # (cell, ok, detail)


def cell(name, ok, detail):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}", flush=True)


def block(names, why):
    for n in names:
        if n not in {x[0] for x in RESULTS}:
            cell(n, False, why)


def evidence(row, ev):
    print(f"EVIDENCE {row}: {json.dumps(ev, sort_keys=True, default=str)}", flush=True)


def log_text(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_save(path):
    """(header, body) of a two-document save file. The upgrade writes a battle's tile-size bytes (written "\\x04" by
    the game) as raw control bytes inside their quotes, which the game reads back but PyYAML refuses: they are put
    back as escapes first."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", lambda m: "\\x%02x" % ord(m.group()), text)
    docs = list(yaml.load_all(text, Loader=LOADER))
    return (docs[0] or {}), ((docs[1] or {}) if len(docs) > 1 else {})


def embedded_bases(body):
    """Base count of every world embedded in body's coopClientSaves (None when nothing is embedded)."""
    worlds = body.get("coopClientSaves") or []
    if not worlds:
        return None
    n = 0
    for entry in worlds:
        docs = list(yaml.load_all(base64.b64decode(entry["blob"]).decode("utf-8"), Loader=LOADER))
        n += len((docs[1] or {}).get("bases") or [])
    return n


def restamp(data, old, new):
    """data with its ONE header line 'saveSchema: old' -> 'saveSchema: new' (CRLF-aware: the header ends at the first
    document separator line after the first line)."""
    text = data.decode("utf-8")
    m = re.search(r"\n---[ \t]*\r?\n", text)
    if not m:
        raise FixtureMiss(f"restamp {old} -> {new}: no document separator")
    head, rest = text[:m.start()], text[m.start():]
    new_head, n = re.subn(r"(?m)^saveSchema: %d(\r?)$" % old, lambda mm: "saveSchema: %d%s" % (new, mm.group(1)), head)
    if n != 1:
        raise FixtureMiss(f"restamp {old} -> {new}: {n} header line(s) (want 1)")
    return (new_head + rest).encode("utf-8")


def base_shape(b):
    return {"name": b.get("name"), "lon": b.get("lon"), "lat": b.get("lat"), "coopbaseid": b.get("coopbaseid"),
            "soldiers": [s.get("id") for s in b.get("soldiers") or []],
            "crafts": [(c.get("type"), c.get("id")) for c in b.get("crafts") or []],
            "facilities": len(b.get("facilities") or [])}


def detect(host, name):
    r = host.cmd({"cmd": "upgrade_detect", "file": name})
    return {k: r.get(k) for k in ("ok", "kind", "variant", "schema", "needsUpgrade", "error")}


def upgrade(host, name):
    r = host.cmd({"cmd": "upgrade_run", "host": name})
    return {k: r.get(k) for k in ("ok", "success", "needsUpgrade", "errors", "warnings", "errorMessage", "report",
                                  "upgradedPath")}


def upgraded_name(name):
    return name[:-4] + "_upgraded.sav"


def report_bad(report, owned, owner, dropped):
    """The one-world report lines, in order, from the schema-4 line to the 'Upgraded save written' line."""
    want = [SCHEMA_LINE, f"All {owned} base(s) now belong to {owner}."]
    if dropped is not None:
        want.append(f"Dropped the alien player's world ({dropped} base(s)).")
    report = report or []
    if SCHEMA_LINE not in report:
        return [f"report {report} has no line {SCHEMA_LINE!r}"]
    i = report.index(SCHEMA_LINE)
    j = next((k for k in range(i, len(report)) if report[k].startswith(WRITTEN_PREFIX)), len(report))
    got = report[i:j]
    return [] if got == want else [f"one-world report lines {got} (want {want})"]


def file_bad(src, up, run, dropped):
    """Problems with the upgrade of src (run = upgrade_run's reply, up = the upgraded file's path); returns
    (problems, summary for EVIDENCE)."""
    if not run.get("success") or run.get("errors"):
        return [f"upgrade_run {run} (want success, no errors)"], {"run": run}
    if not os.path.exists(up):
        return [f"no upgraded file {os.path.basename(up)}"], {"run": run}
    oh, ob = read_save(src)
    uh, ub = read_save(up)
    roster = oh.get("coopPlayers") or []
    owner = roster[0] if roster else None
    bad = []
    for k, v in (("saveSchema", 4), ("coopCampaignType", 0)):
        bad += [] if uh.get(k) == v else [f"header {k} {uh.get(k)!r} (want {v!r})"]
    bad += [] if uh.get("coopPlayers") == roster else [f"header coopPlayers {uh.get('coopPlayers')} (want {roster})"]
    bad += ["header still has coopPvpBorrowed"] if "coopPvpBorrowed" in uh else []
    for k, v in (("coop_gamemode", 2), ("coop_save_owner_player_id", 0), ("no_bases", False)):
        bad += [] if ub.get(k) == v else [f"body {k} {ub.get(k)!r} (want {v!r})"]
    bad += [f"body still has {k}" for k in ("coopClientSaves", "separateCampaign") if k in ub]
    want_bases = [base_shape(b) for b in ob.get("bases") or []]
    got_bases = [base_shape(b) for b in ub.get("bases") or []]
    bad += [] if got_bases == want_bases else [f"bases {got_bases} (want {want_bases})"]
    owners = [b.get("ownerplayername") for b in ub.get("bases") or []]
    bad += [] if owners and all(o == owner for o in owners) else [f"base owners {owners} (want each {owner!r})"]
    soldiers = [(s.get("id"), s.get("coop"), s.get("ownerplayerid"))
                for b in ub.get("bases") or [] for s in b.get("soldiers") or []]
    bad += [f"soldier {i} coop {c} ownerplayerid {o} (want 0)" for i, c, o in soldiers if (c or 0) == 0 and o != 0]
    for k in ("funds", "discovered", "ids"):
        bad += [] if ub.get(k) == ob.get(k) else [f"body {k} {ub.get(k)!r} (want {ob.get(k)!r})"]
    counts = {}
    for k in ("ufos", "alienMissions", "missionSites", "alienBases"):
        counts[k] = (len(ob.get(k) or []), len(ub.get(k) or []))
        bad += [] if counts[k][0] == counts[k][1] else [f"{k} count {counts[k][1]} (want {counts[k][0]})"]
    bad += report_bad(run.get("report"), len(want_bases), owner, dropped)
    summary = {"roster": roster, "bases": got_bases, "owners": owners, "soldiers": soldiers,
               "funds": (ob.get("funds") or [])[-1:], "discovered": len(ob.get("discovered") or []), "ids": ob.get("ids"),
               "counts": counts, "dropped": dropped, "report": run.get("report"),
               "header": {k: uh.get(k) for k in ("saveSchema", "coopCampaignType", "coopPlayers")},
               "body": {k: ub.get(k) for k in ("coop_gamemode", "coop_save_owner_player_id", "no_bases")}}
    return bad, summary


# ----- rows -----

def row_detect(x, ev):
    got = {n: detect(x["host"], n) for n in (GEO, BATTLE, SYNTH)}
    ev["detect"] = got
    want = {"kind": "legacy", "variant": "embed", "needsUpgrade": True, "schema": 2}
    bad = [f"{n}: {g} (want {want})" for n, g in got.items() if any(g.get(k) != v for k, v in want.items())]
    cell("xcom_host_detect", not bad, "; ".join(bad) or f"{', '.join(got)}: each legacy / embed / needsUpgrade / schema 2")


def row_geo_file(x, ev):
    src = os.path.join(x["dir"], GEO)
    run = upgrade(x["host"], GEO)
    bad, ev["geo"] = file_bad(src, os.path.join(x["dir"], upgraded_name(GEO)), run, x["geoDropped"])
    cell("xcom_host_geo_file", not bad, "; ".join(bad) or
         f"one world, {len(ev['geo']['bases'])} base(s) owned by {ev['geo']['roster'][0]}, "
         f"{x['geoDropped']} embedded base(s) dropped")


def row_battle_file(x, ev):
    src, up = os.path.join(x["dir"], BATTLE), os.path.join(x["dir"], upgraded_name(BATTLE))
    run = upgrade(x["host"], BATTLE)
    bad, ev["battle"] = file_bad(src, up, run, None)
    if os.path.exists(up) and run.get("success"):
        oh, ob = read_save(src)
        uh, ub = read_save(up)
        keys = ("mission", "target", "craftOrBase", "turn")
        bad += [f"header {k} {uh.get(k)!r} (want {oh.get(k)!r})" for k in keys if uh.get(k) != oh.get(k)]
        bad += ["header has coopBattleProtocol"] if "coopBattleProtocol" in uh else []
        obg, ubg = ob.get("battleGame") or {}, ub.get("battleGame") or {}
        oid, uid = [u.get("id") for u in obg.get("units") or []], [u.get("id") for u in ubg.get("units") or []]
        bad += [] if ubg and uid == oid else [f"battleGame unit ids {uid} (want {oid})"]
        bad += [] if ubg.get("turn") == obg.get("turn") else [f"battleGame turn {ubg.get('turn')} (want {obg.get('turn')})"]
        ev["battle"]["battle"] = {"header": {k: oh.get(k) for k in keys}, "units": oid, "turn": obg.get("turn")}
    cell("xcom_host_battle_file", not bad, "; ".join(bad) or
         "one world, battle header keys, battleGame turn and unit ids kept, nothing embedded to drop")


def row_synth_file(x, ev):
    src, up = os.path.join(x["dir"], SYNTH), os.path.join(x["dir"], upgraded_name(SYNTH))
    run = upgrade(x["host"], SYNTH)
    bad, ev["synth"] = file_bad(src, up, run, 1)
    if os.path.exists(up) and run.get("success"):
        _, ub = read_save(up)
        bases = ub.get("bases") or []
        names, owners = [b.get("name") for b in bases], [b.get("ownerplayername") for b in bases]
        bad += [] if names == SYNTH_BASES else [f"bases {names} (want {SYNTH_BASES})"]
        bad += [] if owners == [SYNTH_OWNER] * len(SYNTH_BASES) else [f"owners {owners} (want {SYNTH_OWNER})"]
        sol = {s.get("id"): s.get("ownerplayerid") for b in bases for s in b.get("soldiers") or []}
        bad += [f"soldier {i} ownerplayerid {sol.get(i)!r} (want 0)" for i in SYNTH_SOLDIERS if sol.get(i) != 0]
    cell("xcom_host_synth_file", not bad, "; ".join(bad) or
         f"bases {SYNTH_BASES} owned by {SYNTH_OWNER}; soldiers {SYNTH_SOLDIERS} ownerplayerid 0; one embedded base dropped")


def row_stamp_guard(x, ev):
    host, d = x["host"], x["dir"]
    bad = []
    g4 = detect(host, STAMP4)
    want4 = {"kind": "legacy", "variant": "embed", "schema": 3}
    bad += [f"{STAMP4}: {g4} (want {want4})"] if any(g4.get(k) != v for k, v in want4.items()) else []
    run4 = upgrade(host, STAMP4)
    up4 = os.path.join(d, upgraded_name(STAMP4))
    ev["stamp4"] = {"detect": g4, "run": run4}
    if run4.get("success") and os.path.exists(up4):
        uh, ub = read_save(up4)
        ev["stamp4"]["upgraded"] = {"saveSchema": uh.get("saveSchema"), "coopClientSaves": "coopClientSaves" in ub}
        bad += [] if uh.get("saveSchema") == 4 else [f"{STAMP4} upgraded saveSchema {uh.get('saveSchema')!r} (want 4)"]
        bad += [f"{STAMP4} upgraded still has coopClientSaves"] if "coopClientSaves" in ub else []
    else:
        bad.append(f"{STAMP4} upgrade_run {run4} (want success and an upgraded file)")
    geo_up = os.path.join(d, upgraded_name(GEO))
    if os.path.exists(geo_up):
        with open(geo_up, "rb") as f:
            data = restamp(f.read(), 4, 5)
        with open(os.path.join(d, NEXT), "wb") as f:
            f.write(data)
        x["placed"][NEXT] = sha(os.path.join(d, NEXT))
        g5 = detect(host, NEXT)
        ev["next"] = g5
        bad += [] if g5.get("kind") == "unknown_future" else [f"{NEXT}: {g5} (want unknown_future)"]
    else:
        bad.append(f"{NEXT} not reached: no {upgraded_name(GEO)}")
    cell("xcom_host_stamp_guard", not bad, "; ".join(bad) or
         f"{STAMP4} legacy / embed / schema 3, upgraded to stamp 4 with nothing embedded; {NEXT} unknown_future")


def row_alien_host(x, ev):
    g = detect(x["host"], ALIEN_HOST)
    ev["alienHost"] = g
    cell("alien_host_untouched", g.get("kind") == "current",
         f"{ALIEN_HOST}: {g}" + ("" if g.get("kind") == "current" else " (want current)"))


def load_menu(host, name, ev, tag):
    """load_save_menu of name; HostMenu, ErrorMessageState or SaveUpgradeDialogState within LOAD_S. Returns the
    problems."""
    host.ok({"cmd": "load_save_menu", "file": name})
    ends = ("HostMenu", "ErrorMessageState", "SaveUpgradeDialogState")
    _, s = wait(lambda: any(e in stack(host) for e in ends) or None, LOAD_S, 0.1)
    st = stack(host)
    ev[tag] = {"s": s, "stack": st}
    bad = [] if "HostMenu" in st else [f"host stack {st} after {s} s (want HostMenu within {LOAD_S} s)"]
    bad += [f"{e} on the stack" for e in ends[1:] if e in st]
    return bad


def row_loads(x, ev):
    host, d = x["host"], x["dir"]
    up = upgraded_name(GEO)
    if not os.path.exists(os.path.join(d, up)):
        cell("xcom_host_loads", False, f"no upgraded file {up}")
        return
    bad = load_menu(host, up, ev, "geoLoad")
    if not bad:
        c = host.cmd({"cmd": "get_coop"})
        g = host.cmd({"cmd": "geo_state"})
        owners = [b.get("ownerPlayerName") for b in g.get("bases") or []]
        ev["geoLoad"].update({"gamemode": c.get("gamemode"), "owners": owners, "worldFunds": g.get("worldFunds"),
                              "funds": g.get("funds"), "localSeat": c.get("localSeat"), "geoError": g.get("error")})
        bad += [] if c.get("gamemode") == 2 else [f"get_coop.gamemode {c.get('gamemode')!r} (want 2)"]
        bad += [] if owners and all(o == x["geoOwner"] for o in owners) else \
            [f"geo_state base owners {owners} (want each {x['geoOwner']!r})"]
        bad += [] if g.get("worldFunds") == x["geoFunds"] else \
            [f"geo_state worldFunds {g.get('worldFunds')!r} (want {x['geoFunds']})"]
    x["loaded"] = True
    cell("xcom_host_loads", not bad, "; ".join(bad) or
         f"HostMenu after {ev['geoLoad']['s']} s; game mode 2; every base owned by {x['geoOwner']}; funds {x['geoFunds']}")


def row_battle_loads(x, ev):
    host, d = x["host"], x["dir"]
    up = upgraded_name(BATTLE)
    if not os.path.exists(os.path.join(d, up)):
        cell("xcom_host_battle_loads", False, f"no upgraded file {up}")
        return
    if x.get("loaded"):
        host.ok({"cmd": "disconnect_to_menu"})
        ok, s = wait(lambda: "MainMenuState" in stack(host) or None, MENU_S, 0.1)
        ev["menu"] = {"s": s, "stack": stack(host)}
        if not ok:
            cell("xcom_host_battle_loads", False, f"not back at the main menu: {stack(host)} after {s} s")
            return
    conv0 = sum(1 for ln in log_text(host).splitlines() if OB.CONVERT in ln)
    bad = load_menu(host, up, ev, "battleLoad")
    wait(lambda: any(OB.CONVERT in ln or OB.REFUSAL in ln for ln in log_text(host).splitlines()) or None, LOG_S, 0.25)
    text = log_text(host)
    conv = [ln.split("\t")[-1] for ln in text.splitlines() if OB.CONVERT in ln]
    refused = [ln.split("\t")[-1] for ln in text.splitlines() if OB.REFUSAL in ln]
    m = OB.CONVERT_RE.search(conv[0]) if len(conv) == 1 else None
    got = (tuple(int(v) for v in m.groups()[:5]) + m.groups()[5:]) if m else None
    ev["battleLoad"].update({"convertBefore": conv0, "convert": conv, "refusal": refused[-1:], "parsed": got})
    bad += [] if got == GM2_CONVERT else [f"{len(conv)} conversion line(s), parsed {got} (want one with {GM2_CONVERT})"]
    bad += [f"refusal line {refused[-1]!r}"] if refused else []
    cell("xcom_host_battle_loads", not bad, "; ".join(bad) or
         f"HostMenu after {ev['battleLoad']['s']} s; one conversion line {got}; no refusal")


def row_common(x, ev):
    host, d = x["host"], x["dir"]
    crashes = sorted(crash_set() - x["crash0"])
    changed = [n for n, h in x["placed"].items() if not os.path.exists(os.path.join(d, n)) or sha(os.path.join(d, n)) != h]
    extra = sorted(set(os.listdir(d)) - set(x["placed"]))
    stray = [n for n in extra if not n.endswith("_upgraded.sav")]
    ev["common"] = {"crashes": crashes, "alive": alive(host), "changed": changed, "added": extra}
    bad = [f"{len(crashes)} new crash file(s) {crashes}"] if crashes else []
    bad += [] if alive(host) else ["host process exited"]
    bad += [f"placed file(s) changed {changed}"] if changed else []
    bad += [f"file(s) added that are not upgrades {stray}"] if stray else []
    cell("common", not bad, "; ".join(bad) or
         f"0 new crash files; host alive; {len(x['placed'])} placed files unchanged; added {extra}")


ROWS = [("detect", row_detect), ("geo_file", row_geo_file), ("battle_file", row_battle_file),
        ("synth_file", row_synth_file), ("stamp_guard", row_stamp_guard), ("alien_host", row_alien_host),
        ("loads", row_loads), ("battle_loads", row_battle_loads), ("common", row_common)]
ROW_CELL = dict(zip([r for r, _ in ROWS], CELLS))


def place(x):
    """The saves folder: three fixture copies (make_user_dir) plus the synth file and its stamp-4 copy. Checks the
    Geoscape save's precondition and reads its expected values."""
    d = x["dir"]
    with open(os.path.join(d, SYNTH), "w", encoding="utf-8", newline="") as f:
        f.write(synth.pvp_embed_host())
    with open(os.path.join(d, SYNTH), "rb") as f:
        data = restamp(f.read(), 2, 4)
    with open(os.path.join(d, STAMP4), "wb") as f:
        f.write(data)
    x["placed"] = {n: sha(os.path.join(d, n)) for n in (GEO, BATTLE, ALIEN_HOST, SYNTH, STAMP4)}
    h, b = read_save(os.path.join(d, GEO))
    roster = h.get("coopPlayers") or []
    bases = b.get("bases") or []
    pre = {"saveSchema": h.get("saveSchema"), "coop_gamemode": b.get("coop_gamemode"), "roster": roster,
           "bases": [(bb.get("name"), len(bb.get("soldiers") or []), len(bb.get("crafts") or [])) for bb in bases],
           "embedded": len(b.get("coopClientSaves") or [])}
    x["pre"] = pre
    ok = (pre["saveSchema"] == 2 and pre["coop_gamemode"] == 2 and len(roster) == 2 and all(roster)
          and roster[0] != roster[1] and any(n and s and c for n, s, c in pre["bases"]) and pre["embedded"] == 1)
    if not ok:
        raise FixtureMiss(f"{GEO} precondition: {pre}")
    x["geoOwner"], x["geoFunds"] = roster[0], (b.get("funds") or [None])[-1]
    x["geoDropped"] = embedded_bases(b)


def boot(x, ev):
    host = x["host"]
    try:
        host.spawn()
        host.connect()
    except Exception as e:  # noqa: BLE001
        raise FixtureMiss(f"spawn / connect: {type(e).__name__}: {str(e)[:300]}")
    r = host.cmd({"cmd": "pvp_one_world", "gamemode": 2, "on": True})
    s = host.cmd({"cmd": "coop_sides"})
    ev["switch"] = {"set": r, "read": {k: s.get(k) for k in ("oneWorldHostPlaysXcom", "oneWorldHostPlaysAliens")}}
    if s.get("oneWorldHostPlaysXcom") is not True or s.get("oneWorldHostPlaysAliens") is not False:
        raise FixtureMiss(f"one-world switch for game mode 2 not on: {ev['switch']}")
    place(x)
    ev["placed"] = x["placed"]
    ev["pre"] = x["pre"]
    ev["expected"] = {"owner": x["geoOwner"], "funds": x["geoFunds"], "dropped": x["geoDropped"]}


def main():
    t0 = time.time()
    saves = tuple(os.path.join(FIXTURES, n) for n in (GEO, BATTLE, ALIEN_HOST))
    ud = make_user_dir(TAG, saves=saves)
    x = {"host": GameClient("host", None, ud), "dir": os.path.join(ud, "xcom1"), "crash0": crash_set()}
    ev = {"cpu0": cpu_load()}
    booted = False
    try:
        boot(x, ev)
        booted = True
    except FixtureMiss as e:
        cap = RR.capture(str(e), x["host"])
        print(f"CAPTURE boot: {json.dumps(cap, sort_keys=True, default=str)}", flush=True)
        block(CELLS, f"boot ({str(e)[:200]})")
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"CAPTURE boot: {json.dumps(RR.capture(err, x['host']), sort_keys=True, default=str)}", flush=True)
        block(CELLS, f"boot (error {err[:200]})")
    evidence("boot", ev)
    if booted:
        for row, fn in ROWS:
            rev, rt = {}, time.time()
            try:
                fn(x, rev)
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {str(e)[:300]}"
                print(f"[ERROR] row {row}: {err}", flush=True)
                print(f"CAPTURE {row}: {json.dumps(RR.capture(err, x['host']), sort_keys=True, default=str)}", flush=True)
                block([ROW_CELL[row]], f"error {err[:200]}")
            rev["wall"] = round(time.time() - rt, 1)
            evidence(row, rev)
    try:
        if alive(x["host"]):
            x["host"].shutdown()
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] shutdown host: {e}", flush=True)
    fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n==== older PvP saves where the host plays X-COM, upgraded to one world: "
          f"{len(RESULTS) - len(fails)}/{len(CELLS)} cells PASS, wall {time.time() - t0:.1f} s, "
          f"cpu {cpu_load().get('cpu')} % ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(CELLS) else 2)


if __name__ == "__main__":
    main()
