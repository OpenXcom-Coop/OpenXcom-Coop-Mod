"""Older PvP campaign saves are upgraded to one world, the X-COM player's, in both layouts: every base owned by the
X-COM player by name, the alien player's world dropped, header saveSchema 4. The upgrade writes <stem>_upgraded.sav and
never touches the original, and the upgraded file loads on the host.
- The host plays X-COM (game mode 2): the host file's body already is the X-COM world; the alien player's world is
  embedded in coopClientSaves.
- The host plays the aliens (game mode 3): the X-COM player's world is the host file's one coopClientSaves world and
  becomes the body, under the host's header with that world's own clock. When that world is past its first month the
  alien player's alien missions, UFOs, mission sites and alien bases come along (the UFOs no longer detected); the rest
  of the alien player's world goes. A mid-battle save the alien host made in the X-COM world keeps its battle, and the
  battle's target, held only in the alien player's world, is copied in. A save made before the X-COM player's first
  base reached the host becomes the host's new-game world without bases at month -1.

ONE host instance, no lobby (dir pvp_old_upgrade_host). First commands: pvp_one_world {gamemode 2, on true} and
{gamemode 3, on true}, read back from coop_sides (oneWorldHostPlaysXcom true, oneWorldHostPlaysAliens true). Saves
folder (xcom1/):
  pvp_xcom_host_geoscape.sav          host plays X-COM, this build's host save at the Geoscape: schema 2, the alien
                                      player's stand-in world embedded (fixtures/)
  pvp_gm2_battle.sav                  an older version's mid-battle save, game mode 2, nothing embedded (fixtures/)
  pvp_gm3_battle.sav                  an older version's mid-battle save, game mode 3, no coopBattleProtocol (fixtures/)
  pvp_embed_host.sav                  synth.pvp_embed_host(): schema 2, game mode 2, HostBase, roster HostGuy / Bob, the
                                      alien player's world (ClientBase) embedded
  pvp_embed_host_stamp4.sav           the same with its ONE header line saveSchema 2 -> 4 (CRLF-aware split)
  pvp_xcom_host_geoscape_next.sav     the upgraded Geoscape save with its ONE header line saveSchema 4 -> 5 (written
                                      once that upgrade exists)
  pvp_alien_host_geoscape.sav         host plays the aliens, this build's host save at the Geoscape: schema 2, outer
                                      base AlienHQ, the X-COM player's world (month -1, XcomBase) embedded (fixtures/)
  pvp_alien_host_borrowed_battle.sav  host plays the aliens, this build's host save mid-battle in the X-COM player's
                                      world: header coopPvpBorrowed (a landing at a terror site), the X-COM world with
                                      its battleGame embedded, the site in the alien player's world (fixtures/)
  pvp_alien_host_start.sav            host plays the aliens, the host's campaign-start autosave: month -1, one base,
                                      nothing embedded (fixtures/; captured from _autogeo_.asav right after the start)
  pvp_alien_host_start_synth.sav      pvp_alien_host_geoscape.sav with its coopClientSaves block removed and its ONE body
                                      line monthsPassed 0 -> -1 (a SAVE & QUIT before the X-COM world reached the host)
  pvp_alien_host_no_xcom.sav          pvp_alien_host_geoscape.sav with its coopClientSaves block removed (month 0)
  pvp_alien_host_ironman.sav          pvp_alien_host_geoscape.sav with ONE header line ironman: true
  pvp_gm3_battle_newer.sav            pvp_gm3_battle.sav with ONE header line coopBattleProtocol: 2
  pvp_dual_host.sav / pvp_dual_client.sav  synth.pvp_dual_host() / synth.pvp_dual_client(): a schema-1 PvP pair
Expected values (base names, lon / lat, coopbaseid, soldier and craft ids, funds, discovered, ids, object counts,
times, battle keys and units, the borrowed-battle record) are read from the source files at run time and printed in
EVIDENCE.

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
  alien_host_old_battle   upgrade_detect of the older version's game-mode-3 battle save and of its copy under another
                          battle protocol: both current (the load refuses them with its own message, as before)
  xcom_host_loads         load_save_menu of the upgraded Geoscape save: HostMenu within LOAD_S, no ErrorMessageState,
                          no SaveUpgradeDialogState; get_coop.gamemode 2; geo_state: every base's ownerPlayerName is
                          the first roster name, worldFunds (the world's own funds: before START HOST this machine is
                          not seat 0 yet, so geo_state.funds shows the alien player's amount) == the source's last
                          funds
  xcom_host_battle_loads  disconnect_to_menu, then load_save_menu of the upgraded battle save: HostMenu within LOAD_S;
                          ONE conversion line whose counts == GM2_CONVERT; no refusal line
  alien_host_detect       upgrade_detect of the alien-host Geoscape, borrowed-battle, start, start-synth and ironman
                          saves: each legacy / embed / needsUpgrade true / schema 2
  alien_host_geo_file     upgrade_run of the alien-host Geoscape save: success, no errors; header saveSchema 4,
                          coopCampaignType 0, coopPlayers unchanged, no coopPvpBorrowed, no battle keys, time == the
                          embedded world's header time, no ironman; body coop_gamemode 3, coop_save_owner_player_id 0,
                          no_bases false, saveID == the source body's, no coopClientSaves, no separateCampaign; bases
                          equal to the embedded world's in order (no AlienHQ), each ownerplayername the second roster
                          name, every base and dead soldier with coop 0 ownerplayerid 1; funds, discovered, ids,
                          monthsPassed, daysPassed == the embedded world's; the embedded world is at month -1, so the
                          ufos / alienMissions / missionSites / alienBases counts == the embedded world's; report lines
                          "Schema 4: ...", "All N base(s) now belong to <name>.", "Dropped the alien player's world (M
                          base(s))." (M = the outer bases)
  alien_host_borrow_file  the same for the borrowed-battle save (its embedded world is past its first month), plus:
                          header mission, target, craftOrBase, turn, coopBattleProtocol, coopBattleId == the source
                          header's; battleGame turn and unit ids == the embedded world's; the alien player's alien
                          missions, UFOs, mission sites and alien bases are in the one world under their own ids
                          (counts == the alien player's), the UFOs other than the battle target without detected,
                          hyperDetected and id, the alien bases with their discovered flag, alienStrategy == the alien
                          player's; ids: never lower than the embedded world's, the X-COM player's craft and soldier
                          counters unchanged, the alien player's other counters raised to at least its own; the battle
                          target (the record's kind and coop id): exactly one entry in its list, inBattlescape true (an
                          alien base also discovered true), id == the craft's dest.id (a site or alien base keeps the
                          alien player's id, a UFO takes the craft's), the record's craft without its coopDest key and
                          with the embedded world's dest.type, ids[dest.type] > dest.id; report adds "Kept the alien
                          player's N alien mission(s), U UFO(s), S site(s) and B alien base(s)."
  alien_host_start_file   upgrade_run of the start and start-synth saves: each success; header saveSchema 4, no
                          coopPvpBorrowed, time == the source header's; body monthsPassed -1, no bases, coop_gamemode 3,
                          coop_save_owner_player_id 0, no_bases false, no coopClientSaves, funds and saveID == the
                          source's; report lines "Schema 4: ...", "The X-COM player places its first base when the
                          campaign resumes.", "Removed M base(s) of the alien player."
  alien_host_ironman_file upgrade_run of the ironman save: header ironman true, header name ends with the
                          " (upgraded to ...)" suffix; the Geoscape file's body checks hold
  alien_host_refused      upgrade_run of the no-X-COM save (month 0): success false, the refusal names "The X-COM
                          player's world is missing from this save", no upgraded file
  upgrade_summary         the replies of xcom_host_geo_file, xcom_host_synth_file, alien_host_geo_file,
                          alien_host_borrow_file and alien_host_start_file: each a success, and no report line is
                          "Schema 3: PvP campaign keeps one world per player."
  alien_host_loads        disconnect_to_menu, load_save_menu of the upgraded alien-host Geoscape save, then the same
                          for the upgraded ironman save: each HostMenu within LOAD_S, no ErrorMessageState, no
                          SaveUpgradeDialogState; get_coop.gamemode 3; geo_state base names == the upgraded file's, each
                          ownerPlayerName the second roster name, no AlienHQ; worldFunds == the embedded world's last
                          funds
  two_world_summary       pvp_one_world {gamemode 2, on false}; upgrade_run of the schema-1 PvP pair (client Carol,
                          host HostGuy): success, upgraded header saveSchema 2, one coopClientSaves entry, no report line
                          starts with "Schema 3:" or "Schema 4:"; then pvp_one_world {gamemode 2, on true}, read back
  common                  0 new crash files; the host alive; every placed file's sha256 unchanged; every other file in
                          the saves folder ends in _upgraded.sav; both one-world switches read back on
Without the fix (both switches on): exit 2, 10/18 - FAIL alien_host_old_battle, alien_host_geo_file,
alien_host_borrow_file, alien_host_start_file, alien_host_ironman_file, alien_host_refused, upgrade_summary,
alien_host_loads. With it: 18/18.

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
ALIEN_HOST_NEWER = "pvp_gm3_battle_newer.sav"
SYNTH = "pvp_embed_host.sav"
STAMP4 = "pvp_embed_host_stamp4.sav"
NEXT = "pvp_xcom_host_geoscape_next.sav"
A_GEO = "pvp_alien_host_geoscape.sav"
A_BORROW = "pvp_alien_host_borrowed_battle.sav"
A_START = "pvp_alien_host_start.sav"
A_START_SYNTH = "pvp_alien_host_start_synth.sav"
A_NO_XCOM = "pvp_alien_host_no_xcom.sav"
A_IRON = "pvp_alien_host_ironman.sav"
DUAL_HOST, DUAL_CLIENT = "pvp_dual_host.sav", "pvp_dual_client.sav"
DUAL_CLIENT_NAME, DUAL_HOST_NAME = "Carol", "HostGuy"
SYNTH_BASES, SYNTH_OWNER, SYNTH_SOLDIERS = ["HostBase"], "HostGuy", [1, 2]
STAND_IN_BASE = "AlienHQ"
SCHEMA_LINE = "Schema 4: the PvP campaign is now one world, the X-COM player's."
FIRST_BASE_LINE = "The X-COM player places its first base when the campaign resumes."
OLD_STEP_LINE = "Schema 3: PvP campaign keeps one world per player."
MISSING_XCOM = "The X-COM player's world is missing from this save"
WRITTEN_PREFIX = "Upgraded save written: "
BATTLE_KEYS = ("mission", "target", "craftOrBase", "turn", "coopBattleProtocol", "coopBattleId")
ALIEN_LISTS = ("alienMissions", "ufos", "missionSites", "alienBases")
# the borrowed-battle record's target kind -> (list, coop id key, craft destination key)
TARGET_KINDS = {"ufo": ("ufos", "coopUfoId", "coopDestUfoId"),
                "site": ("missionSites", "coopMissionId", "coopDestMissionId"),
                "alienBase": ("alienBases", "coopAlienBaseId", "coopDestAlienBaseId")}
LOAD_S, LOG_S, MENU_S = 30, 10, 30
CELLS = ["xcom_host_detect", "xcom_host_geo_file", "xcom_host_battle_file", "xcom_host_synth_file",
         "xcom_host_stamp_guard", "alien_host_old_battle", "xcom_host_loads", "xcom_host_battle_loads",
         "alien_host_detect", "alien_host_geo_file", "alien_host_borrow_file", "alien_host_start_file",
         "alien_host_ironman_file", "alien_host_refused", "upgrade_summary", "alien_host_loads", "two_world_summary",
         "common"]
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


def load_docs(text):
    """(header, body) of a two-document save text. The upgrade writes a battle's tile-size bytes (written "\\x04" by
    the game) as raw control bytes inside their quotes, which the game reads back but PyYAML refuses: they are put
    back as escapes first."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", lambda m: "\\x%02x" % ord(m.group()), text)
    docs = list(yaml.load_all(text, Loader=LOADER))
    return (docs[0] or {}), ((docs[1] or {}) if len(docs) > 1 else {})


def read_save(path):
    with open(path, encoding="utf-8") as f:
        return load_docs(f.read())


def embedded_worlds(body):
    """(header, body) of every world embedded in body's coopClientSaves."""
    return [load_docs(base64.b64decode(entry["blob"]).decode("utf-8")) for entry in body.get("coopClientSaves") or []]


def embedded_bases(body):
    """Base count of every world embedded in body's coopClientSaves (None when nothing is embedded)."""
    worlds = embedded_worlds(body)
    if not worlds:
        return None
    return sum(len(b.get("bases") or []) for _, b in worlds)


def split_header(data):
    """(header text, rest from the document separator line on) of a save's bytes; CRLF-aware."""
    text = data.decode("utf-8")
    m = re.search(r"\n---[ \t]*\r?\n", text)
    if not m:
        raise FixtureMiss("no document separator")
    return text[:m.start() + 1], text[m.start() + 1:]


def restamp(data, old, new):
    """data with its ONE header line 'saveSchema: old' -> 'saveSchema: new' (CRLF-aware: the header ends at the first
    document separator line after the first line)."""
    head, rest = split_header(data)
    new_head, n = re.subn(r"(?m)^saveSchema: %d(\r?)$" % old, lambda mm: "saveSchema: %d%s" % (new, mm.group(1)), head)
    if n != 1:
        raise FixtureMiss(f"restamp {old} -> {new}: {n} header line(s) (want 1)")
    return (new_head + rest).encode("utf-8")


def add_header_line(data, line):
    """data with ONE header line added right before the document separator line, in the file's own line ending."""
    head, rest = split_header(data)
    eol = "\r\n" if head.endswith("\r\n") else "\n"
    return (head + line + eol + rest).encode("utf-8")


def drop_embedded(data):
    """data without its body's coopClientSaves block (that line up to the next line that starts a key at column 0)."""
    text = data.decode("utf-8")
    new, n = re.subn(r"(?ms)^coopClientSaves:[^\n]*\n(?:[ \t-][^\n]*\n)*", "", text)
    if n != 1:
        raise FixtureMiss(f"coopClientSaves block: {n} match(es) (want 1)")
    return new.encode("utf-8")


def set_month(data, old, new):
    """data with its ONE body line 'monthsPassed: old' -> 'monthsPassed: new' (CRLF-aware)."""
    head, rest = split_header(data)
    new_rest, n = re.subn(r"(?m)^monthsPassed: %d(\r?)$" % old, lambda mm: "monthsPassed: %d%s" % (new, mm.group(1)),
                          rest)
    if n != 1:
        raise FixtureMiss(f"monthsPassed {old} -> {new}: {n} body line(s) (want 1)")
    return (head + new_rest).encode("utf-8")


def base_shape(b):
    return {"name": b.get("name"), "lon": b.get("lon"), "lat": b.get("lat"), "coopbaseid": b.get("coopbaseid"),
            "soldiers": [s.get("id") for s in b.get("soldiers") or []],
            "crafts": [(c.get("type"), c.get("id")) for c in b.get("crafts") or []],
            "facilities": len(b.get("facilities") or [])}


def detect(host, name):
    r = host.cmd({"cmd": "upgrade_detect", "file": name})
    return {k: r.get(k) for k in ("ok", "kind", "variant", "schema", "needsUpgrade", "error")}


def upgrade(host, name, **extra):
    r = host.cmd(dict({"cmd": "upgrade_run", "host": name}, **extra))
    return {k: r.get(k) for k in ("ok", "success", "needsUpgrade", "errors", "warnings", "errorMessage", "report",
                                  "upgradedPath")}


def upgraded_name(name):
    return name[:-4] + "_upgraded.sav"


def lines_bad(report, want):
    """The one-world report lines, from the schema-4 line to the 'Upgraded save written' line, against want."""
    report = report or []
    if SCHEMA_LINE not in report:
        return [f"report {report} has no line {SCHEMA_LINE!r}"]
    i = report.index(SCHEMA_LINE)
    j = next((k for k in range(i, len(report)) if report[k].startswith(WRITTEN_PREFIX)), len(report))
    got = report[i:j]
    return [] if got == want else [f"one-world report lines {got} (want {want})"]


def report_bad(report, owned, owner, dropped):
    want = [SCHEMA_LINE, f"All {owned} base(s) now belong to {owner}."]
    if dropped is not None:
        want.append(f"Dropped the alien player's world ({dropped} base(s)).")
    return lines_bad(report, want)


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
    for k in ALIEN_LISTS:
        counts[k] = (len(ob.get(k) or []), len(ub.get(k) or []))
        bad += [] if counts[k][0] == counts[k][1] else [f"{k} count {counts[k][1]} (want {counts[k][0]})"]
    bad += report_bad(run.get("report"), len(want_bases), owner, dropped)
    summary = {"roster": roster, "bases": got_bases, "owners": owners, "soldiers": soldiers,
               "funds": (ob.get("funds") or [])[-1:], "discovered": len(ob.get("discovered") or []), "ids": ob.get("ids"),
               "counts": counts, "dropped": dropped, "report": run.get("report"),
               "header": {k: uh.get(k) for k in ("saveSchema", "coopCampaignType", "coopPlayers")},
               "body": {k: ub.get(k) for k in ("coop_gamemode", "coop_save_owner_player_id", "no_bases")}}
    return bad, summary


def craft_of(body, ctype, cid):
    for b in body.get("bases") or []:
        for c in b.get("crafts") or []:
            if c.get("type") == ctype and c.get("id") == cid:
                return c
    return None


def carried_bad(ob, xb, ub, target):
    """Problems with the alien player's alien missions, UFOs, mission sites and alien bases in the one world (ob = the
    alien player's body, xb = the embedded X-COM body, ub = the upgraded body, target = (list, coop key, coop id) of
    the battle target or None); returns (problems, summary)."""
    bad = []
    keys = {"alienMissions": "uniqueID", "ufos": "uniqueId", "missionSites": "coopMissionId",
            "alienBases": "coopAlienBaseId"}
    summary = {}
    for k in ALIEN_LISTS:
        own = xb.get(k) or []
        if own:
            raise FixtureMiss(f"the embedded X-COM world holds {len(own)} {k} of its own")
        src, got = ob.get(k) or [], ub.get(k) or []
        summary[k] = (len(src), len(got))
        bad += [] if len(got) == len(src) else [f"{k} count {len(got)} (want the alien player's {len(src)})"]
        by_key = {o.get(keys[k]): o for o in got}
        for o in src:
            g = by_key.get(o.get(keys[k]))
            if g is None:
                bad.append(f"{k} {keys[k]} {o.get(keys[k])} not carried")
                continue
            is_target = target is not None and target[0] == k and o.get(target[1]) == target[2]
            if k == "ufos":
                if not is_target:
                    bad += [f"ufo {o.get('uniqueId')} still has {f}" for f in ("detected", "hyperDetected", "id")
                            if f in g]
            elif k != "alienMissions" and not is_target:
                bad += [] if g.get("id") == o.get("id") else [f"{k} {o.get(keys[k])} id {g.get('id')} (want {o.get('id')})"]
            if k == "alienBases":
                want = True if is_target else o.get("discovered")
                bad += [] if g.get("discovered") == want else [f"alien base {o.get(keys[k])} discovered {g.get('discovered')}"]
            if k == "alienMissions":
                for f in ("uniqueID", "type", "region", "race", "liveUfos"):
                    bad += [] if g.get(f) == o.get(f) else [f"mission {o.get('uniqueID')} {f} {g.get(f)!r} (want {o.get(f)!r})"]
    bad += [] if ub.get("alienStrategy") == ob.get("alienStrategy") else ["alienStrategy is not the alien player's"]
    return bad, summary


def ids_bad(ob, xb, ub):
    """The one world's id counters: never lower than the X-COM world's; its craft and soldier counters unchanged; the
    alien player's other counters raised to at least its own."""
    oids, xids, uids = ob.get("ids") or {}, xb.get("ids") or {}, ub.get("ids") or {}
    keep = {"STR_SOLDIER", "STR_WAY_POINT"} | {c.get("type") for w in (ob, xb) for b in w.get("bases") or []
                                               for c in b.get("crafts") or []}
    bad = [f"ids {k} {uids.get(k)} below the X-COM world's {v}" for k, v in xids.items() if (uids.get(k) or 0) < v]
    bad += [f"ids {k} {uids.get(k)} (want the X-COM world's {xids.get(k)})" for k in sorted(keep & set(xids))
            if uids.get(k) != xids.get(k)]
    bad += [f"ids {k} {uids.get(k)} below the alien player's {v}" for k, v in oids.items()
            if k not in keep and (uids.get(k) or 0) < v]
    return bad


def alien_file_bad(src, up, run, ironman=False):
    """Problems with the upgrade of an alien-host save that embeds the X-COM player's world; returns (problems,
    summary). The upgraded file must be the embedded X-COM world under the host's header."""
    if not run.get("success") or run.get("errors"):
        return [f"upgrade_run {run} (want success, no errors)"], {"run": run}
    if not os.path.exists(up):
        return [f"no upgraded file {os.path.basename(up)}"], {"run": run}
    oh, ob = read_save(src)
    worlds = embedded_worlds(ob)
    if len(worlds) != 1:
        raise FixtureMiss(f"{os.path.basename(src)}: {len(worlds)} embedded world(s) (want 1)")
    xh, xb = worlds[0]
    uh, ub = read_save(up)
    roster = oh.get("coopPlayers") or []
    owner = roster[1] if len(roster) > 1 else None
    battle = "battleGame" in xb
    carry = (xb.get("monthsPassed") or 0) >= 0
    record = oh.get("coopPvpBorrowed") or {}
    bad = []
    for k, v in (("saveSchema", 4), ("coopCampaignType", 0)):
        bad += [] if uh.get(k) == v else [f"header {k} {uh.get(k)!r} (want {v!r})"]
    bad += [] if uh.get("coopPlayers") == roster else [f"header coopPlayers {uh.get('coopPlayers')} (want {roster})"]
    bad += ["header still has coopPvpBorrowed"] if "coopPvpBorrowed" in uh else []
    bad += [] if uh.get("time") == xh.get("time") else [f"header time {uh.get('time')} (want the X-COM world's {xh.get('time')})"]
    if battle:
        bad += [f"header {k} {uh.get(k)!r} (want {oh.get(k)!r})" for k in BATTLE_KEYS if uh.get(k) != oh.get(k)]
    else:
        bad += [f"header still has {k}" for k in BATTLE_KEYS if k in uh]
    if ironman:
        bad += [] if uh.get("ironman") is True else [f"header ironman {uh.get('ironman')!r} (want true)"]
        name = uh.get("name") or ""
        bad += [] if re.search(r" \(upgraded to .+\)$", name) else [f"header name {name!r} (want the upgraded suffix)"]
    else:
        bad += ["header has ironman"] if "ironman" in uh else []
    for k, v in (("coop_gamemode", 3), ("coop_save_owner_player_id", 0), ("no_bases", False)):
        bad += [] if ub.get(k) == v else [f"body {k} {ub.get(k)!r} (want {v!r})"]
    bad += [] if ub.get("saveID") == ob.get("saveID") else [f"body saveID {ub.get('saveID')} (want {ob.get('saveID')})"]
    bad += [f"body still has {k}" for k in ("coopClientSaves", "separateCampaign") if k in ub]
    want_bases = [base_shape(b) for b in xb.get("bases") or []]
    got_bases = [base_shape(b) for b in ub.get("bases") or []]
    bad += [] if got_bases == want_bases else [f"bases {got_bases} (want the X-COM world's {want_bases})"]
    bad += [f"base {STAND_IN_BASE} kept"] if any(b.get("name") == STAND_IN_BASE for b in ub.get("bases") or []) else []
    owners = [b.get("ownerplayername") for b in ub.get("bases") or []]
    bad += [] if owners and all(o == owner for o in owners) else [f"base owners {owners} (want each {owner!r})"]
    soldiers = [(s.get("id"), s.get("coop"), s.get("ownerplayerid"))
                for b in ub.get("bases") or [] for s in b.get("soldiers") or []]
    dead = [(s.get("id"), s.get("coop"), s.get("ownerplayerid")) for s in ub.get("deadSoldiers") or []]
    bad += [f"soldier {i} coop {c} ownerplayerid {o} (want 1)" for i, c, o in soldiers + dead if (c or 0) == 0 and o != 1]
    for k in ("funds", "discovered", "monthsPassed", "daysPassed"):
        bad += [] if ub.get(k) == xb.get(k) else [f"body {k} {ub.get(k)!r} (want the X-COM world's {xb.get(k)!r})"]
    summary = {"roster": roster, "bases": got_bases, "owners": owners, "soldiers": soldiers, "dead": dead,
               "carry": carry, "battle": battle, "time": xh.get("time"), "month": xb.get("monthsPassed"),
               "funds": (xb.get("funds") or [])[-1:], "ids": {"xcom": xb.get("ids"), "alien": ob.get("ids"),
                                                              "upgraded": ub.get("ids")},
               "report": run.get("report"), "record": record,
               "header": {k: uh.get(k) for k in ("saveSchema", "coopCampaignType", "coopPlayers", "ironman", "name")},
               "body": {k: ub.get(k) for k in ("coop_gamemode", "coop_save_owner_player_id", "no_bases", "saveID")}}
    target = None
    if battle and record.get("kind") == "landing" and record.get("targetMirror"):
        kind = record.get("targetKind")
        if kind not in TARGET_KINDS:
            raise FixtureMiss(f"borrowed-battle record target kind {kind!r}")
        target = TARGET_KINDS[kind][:2] + (record.get("targetCoopId"),)
    if carry:
        cb, summary["carried"] = carried_bad(ob, xb, ub, target)
        bad += cb
        bad += ids_bad(ob, xb, ub)
    else:
        for k in ALIEN_LISTS:
            n0, n1 = len(xb.get(k) or []), len(ub.get(k) or [])
            bad += [] if n0 == n1 else [f"{k} count {n1} (want the X-COM world's {n0})"]
        bad += [] if ub.get("ids") == xb.get("ids") else [f"body ids {ub.get('ids')} (want the X-COM world's {xb.get('ids')})"]
    if battle:
        xbg, ubg = xb.get("battleGame") or {}, ub.get("battleGame") or {}
        xid, uid = [u.get("id") for u in xbg.get("units") or []], [u.get("id") for u in ubg.get("units") or []]
        bad += [] if ubg and uid == xid else [f"battleGame unit ids {uid} (want {xid})"]
        bad += [] if ubg.get("turn") == xbg.get("turn") else [f"battleGame turn {ubg.get('turn')} (want {xbg.get('turn')})"]
        summary["battleGame"] = {"turn": xbg.get("turn"), "units": xid}
    if target is not None:
        tb, summary["target"] = target_bad(ob, xb, ub, record)
        bad += tb
    want = [SCHEMA_LINE, f"All {len(want_bases)} base(s) now belong to {owner}.",
            f"Dropped the alien player's world ({len(ob.get('bases') or [])} base(s))."]
    if carry:
        n = {k: len(ob.get(k) or []) for k in ALIEN_LISTS}
        want.append(f"Kept the alien player's {n['alienMissions']} alien mission(s), {n['ufos']} UFO(s), "
                    f"{n['missionSites']} site(s) and {n['alienBases']} alien base(s).")
    bad += lines_bad(run.get("report"), want)
    return bad, summary


def target_bad(ob, xb, ub, record):
    """Problems with the borrowed battle's target in the one world; returns (problems, summary)."""
    lst, coop_key, dest_key = TARGET_KINDS[record.get("targetKind")]
    coop_id = record.get("targetCoopId")
    src = [o for o in ob.get(lst) or [] if o.get(coop_key) == coop_id]
    if len(src) != 1:
        raise FixtureMiss(f"the alien player's {lst} with {coop_key} {coop_id}: {len(src)} (want 1)")
    xcraft = craft_of(xb, record.get("craftType"), record.get("craftId"))
    if xcraft is None or not (xcraft.get("dest") or {}).get("type"):
        raise FixtureMiss(f"the X-COM world's craft {record.get('craftType')} {record.get('craftId')}: {xcraft}")
    got = [o for o in ub.get(lst) or [] if o.get(coop_key) == coop_id]
    craft = craft_of(ub, record.get("craftType"), record.get("craftId")) or {}
    dest = craft.get("dest") or {}
    summary = {"list": lst, "coopId": coop_id, "found": len(got), "craftDest": dest, "xcomDest": xcraft.get("dest"),
               "sourceId": src[0].get("id")}
    if len(got) != 1:
        return [f"{lst} entries with {coop_key} {coop_id}: {len(got)} (want 1)"], summary
    t = got[0]
    summary["target"] = {k: t.get(k) for k in ("id", "inBattlescape", "discovered", "detected")}
    bad = [] if t.get("inBattlescape") is True else [f"target inBattlescape {t.get('inBattlescape')!r} (want true)"]
    if lst == "alienBases":
        bad += [] if t.get("discovered") is True else [f"target discovered {t.get('discovered')!r} (want true)"]
    # A site or an alien base keeps the alien player's id, as every carried object does; a UFO (the alien
    # player's world never names one) takes the id the craft's destination names.
    want_id = (xcraft.get("dest") or {}).get("id") if lst == "ufos" else src[0].get("id")
    bad += [] if t.get("id") == want_id else [f"target id {t.get('id')} (want {want_id})"]
    bad += [] if dest.get("id") == t.get("id") else [f"craft dest id {dest.get('id')} (want the target's {t.get('id')})"]
    bad += [] if dest.get("type") == xcraft["dest"]["type"] else [f"craft dest type {dest.get('type')} (want {xcraft['dest']['type']})"]
    bad += [f"craft still has {dest_key}"] if dest_key in craft else []
    counter = (ub.get("ids") or {}).get(dest.get("type")) or 0
    bad += [] if counter > (dest.get("id") or 0) else [f"ids {dest.get('type')} {counter} (want above {dest.get('id')})"]
    return bad, summary


def start_file_bad(src, up, run):
    """Problems with the upgrade of an alien-host save that holds no X-COM world (month -1); returns (problems,
    summary)."""
    if not run.get("success") or run.get("errors"):
        return [f"upgrade_run {run} (want success, no errors)"], {"run": run}
    if not os.path.exists(up):
        return [f"no upgraded file {os.path.basename(up)}"], {"run": run}
    oh, ob = read_save(src)
    uh, ub = read_save(up)
    bad = [] if uh.get("saveSchema") == 4 else [f"header saveSchema {uh.get('saveSchema')!r} (want 4)"]
    bad += ["header still has coopPvpBorrowed"] if "coopPvpBorrowed" in uh else []
    bad += [] if uh.get("time") == oh.get("time") else [f"header time {uh.get('time')} (want {oh.get('time')})"]
    for k, v in (("monthsPassed", -1), ("coop_gamemode", 3), ("coop_save_owner_player_id", 0), ("no_bases", False)):
        bad += [] if ub.get(k) == v else [f"body {k} {ub.get(k)!r} (want {v!r})"]
    bad += [f"body bases {[b.get('name') for b in ub.get('bases')]} (want none)"] if ub.get("bases") else []
    bad += ["body still has coopClientSaves"] if "coopClientSaves" in ub else []
    for k in ("funds", "saveID"):
        bad += [] if ub.get(k) == ob.get(k) else [f"body {k} {ub.get(k)!r} (want {ob.get(k)!r})"]
    removed = len(ob.get("bases") or [])
    bad += lines_bad(run.get("report"), [SCHEMA_LINE, FIRST_BASE_LINE, f"Removed {removed} base(s) of the alien player."])
    return bad, {"removed": removed, "report": run.get("report"), "time": oh.get("time"),
                 "body": {k: ub.get(k) for k in ("monthsPassed", "coop_gamemode", "coop_save_owner_player_id",
                                                 "no_bases", "saveID")}, "funds": (ob.get("funds") or [])[-1:]}


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
    x["replies"]["xcom_host_geo_file"] = run
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
    x["replies"]["xcom_host_synth_file"] = run
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


def row_old_battle(x, ev):
    got = {n: detect(x["host"], n) for n in (ALIEN_HOST, ALIEN_HOST_NEWER)}
    ev["oldBattle"] = got
    bad = [f"{n}: {g} (want current)" for n, g in got.items() if g.get("kind") != "current"]
    cell("alien_host_old_battle", not bad, "; ".join(bad) or f"{', '.join(got)}: both current")


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


def to_menu(x, ev, tag):
    """disconnect_to_menu once a save was loaded; returns the problems."""
    host = x["host"]
    if not x.get("loaded"):
        return []
    host.ok({"cmd": "disconnect_to_menu"})
    ok, s = wait(lambda: "MainMenuState" in stack(host) or None, MENU_S, 0.1)
    ev[tag] = {"s": s, "stack": stack(host)}
    return [] if ok else [f"not back at the main menu: {stack(host)} after {s} s"]


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
    bad = to_menu(x, ev, "menu")
    if bad:
        cell("xcom_host_battle_loads", False, bad[0])
        return
    conv0 = sum(1 for ln in log_text(host).splitlines() if OB.CONVERT in ln)
    bad = load_menu(host, up, ev, "battleLoad")
    x["loaded"] = True
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


def row_alien_detect(x, ev):
    names = (A_GEO, A_BORROW) + ((A_START,) if x["haveStart"] else ()) + (A_START_SYNTH, A_IRON)
    got = {n: detect(x["host"], n) for n in names}
    ev["detect"] = got
    want = {"kind": "legacy", "variant": "embed", "needsUpgrade": True, "schema": 2}
    bad = [f"{n}: {g} (want {want})" for n, g in got.items() if any(g.get(k) != v for k, v in want.items())]
    cell("alien_host_detect", not bad, "; ".join(bad) or f"{', '.join(got)}: each legacy / embed / needsUpgrade / schema 2")


def row_alien_geo_file(x, ev):
    src, up = os.path.join(x["dir"], A_GEO), os.path.join(x["dir"], upgraded_name(A_GEO))
    run = upgrade(x["host"], A_GEO)
    x["replies"]["alien_host_geo_file"] = run
    bad, ev["geo"] = alien_file_bad(src, up, run)
    cell("alien_host_geo_file", not bad, "; ".join(bad) or
         f"one world: the X-COM world's {len(ev['geo']['bases'])} base(s) owned by {ev['geo']['roster'][1]}, its clock "
         f"{ev['geo']['time']}, month {ev['geo']['month']}; the alien player's world dropped")


def row_alien_borrow_file(x, ev):
    src, up = os.path.join(x["dir"], A_BORROW), os.path.join(x["dir"], upgraded_name(A_BORROW))
    run = upgrade(x["host"], A_BORROW)
    x["replies"]["alien_host_borrow_file"] = run
    bad, ev["borrow"] = alien_file_bad(src, up, run)
    if not bad and not ev["borrow"].get("battle"):
        bad.append("the embedded X-COM world holds no battleGame")
    t = ev["borrow"].get("target") or {}
    cell("alien_host_borrow_file", not bad, "; ".join(bad) or
         f"one world with its battle; target {t.get('list')} {t.get('coopId')} as id {(t.get('target') or {}).get('id')}"
         f" in battle; the alien player's objects carried {ev['borrow'].get('carried')}")


def row_alien_start_file(x, ev):
    bad = []
    names = ((A_START,) if x["haveStart"] else ()) + (A_START_SYNTH,)
    for n in names:
        run = upgrade(x["host"], n)
        x["replies"]["alien_host_start_file " + n] = run
        b, ev[n] = start_file_bad(os.path.join(x["dir"], n), os.path.join(x["dir"], upgraded_name(n)), run)
        bad += [f"{n}: {p}" for p in b]
    cell("alien_host_start_file", not bad, "; ".join(bad) or
         f"{', '.join(names)}: each the host's world at month -1 without bases, waiting for the X-COM player's first base")


def row_alien_ironman_file(x, ev):
    src, up = os.path.join(x["dir"], A_IRON), os.path.join(x["dir"], upgraded_name(A_IRON))
    run = upgrade(x["host"], A_IRON)
    bad, ev["ironman"] = alien_file_bad(src, up, run, ironman=True)
    cell("alien_host_ironman_file", not bad, "; ".join(bad) or
         f"ironman kept, name {ev['ironman'].get('header', {}).get('name')!r}; the Geoscape file's checks hold")


def row_alien_refused(x, ev):
    run = upgrade(x["host"], A_NO_XCOM)
    up = upgraded_name(A_NO_XCOM)
    ev["refused"] = {"run": run, "upgraded": os.path.exists(os.path.join(x["dir"], up))}
    text = " ".join(list(run.get("errors") or []) + [run.get("errorMessage") or ""])
    bad = [f"upgrade_run success {run.get('success')!r} (want false)"] if run.get("success") is not False else []
    bad += [] if MISSING_XCOM in text else [f"refusal {text!r} (want {MISSING_XCOM!r})"]
    bad += [f"upgraded file {up} written"] if ev["refused"]["upgraded"] else []
    cell("alien_host_refused", not bad, "; ".join(bad) or f"refused: {text.strip()}")


def row_summary(x, ev):
    want = ["xcom_host_geo_file", "xcom_host_synth_file", "alien_host_geo_file", "alien_host_borrow_file"] + \
        [k for k in x["replies"] if k.startswith("alien_host_start_file ")]
    ev["summary"] = {k: (x["replies"].get(k) or {}).get("report") for k in want}
    bad = []
    for k in want:
        run = x["replies"].get(k) or {}
        bad += [] if run.get("success") is True else [f"{k}: not a success"]
        bad += [f"{k}: report line {OLD_STEP_LINE!r}"] if OLD_STEP_LINE in (run.get("report") or []) else []
    bad += [] if any(k.startswith("alien_host_start_file ") for k in want) else ["no start upgrade reply"]
    cell("upgrade_summary", not bad, "; ".join(bad) or f"{len(want)} upgrades, each a success, no two-world line")


def row_alien_loads(x, ev):
    host, d = x["host"], x["dir"]
    bad = []
    for n, tag in ((A_GEO, "geo"), (A_IRON, "ironman")):
        up = upgraded_name(n)
        if not os.path.exists(os.path.join(d, up)):
            bad.append(f"no upgraded file {up}")
            continue
        b = to_menu(x, ev, tag + "Menu")
        if b:
            bad += b
            break
        b = load_menu(host, up, ev, tag)
        x["loaded"] = True
        if not b:
            _, ub = read_save(os.path.join(d, up))
            c = host.cmd({"cmd": "get_coop"})
            g = host.cmd({"cmd": "geo_state"})
            names = [bb.get("name") for bb in g.get("bases") or []]
            owners = [bb.get("ownerPlayerName") for bb in g.get("bases") or []]
            want_names = [bb.get("name") for bb in ub.get("bases") or []]
            ev[tag].update({"gamemode": c.get("gamemode"), "names": names, "owners": owners,
                            "worldFunds": g.get("worldFunds"), "funds": g.get("funds"), "localSeat": c.get("localSeat"),
                            "geoError": g.get("error")})
            b += [] if c.get("gamemode") == 3 else [f"get_coop.gamemode {c.get('gamemode')!r} (want 3)"]
            b += [] if names == want_names else [f"geo_state bases {names} (want {want_names})"]
            b += [f"geo_state base {STAND_IN_BASE}"] if STAND_IN_BASE in names else []
            b += [] if owners and all(o == x["alienOwner"] for o in owners) else \
                [f"geo_state base owners {owners} (want each {x['alienOwner']!r})"]
            b += [] if g.get("worldFunds") == x["alienFunds"] else \
                [f"geo_state worldFunds {g.get('worldFunds')!r} (want {x['alienFunds']})"]
        bad += [f"{up}: {p}" for p in b]
    cell("alien_host_loads", not bad, "; ".join(bad) or
         f"both upgraded saves at HostMenu; game mode 3; bases owned by {x['alienOwner']}, no {STAND_IN_BASE}; "
         f"funds {x['alienFunds']}")


def row_two_world(x, ev):
    host, d = x["host"], x["dir"]
    off = host.cmd({"cmd": "pvp_one_world", "gamemode": 2, "on": False})
    ev["off"] = off
    bad = [] if off.get("oneWorldHostPlaysXcom") is False else [f"switch off read back {off}"]
    try:
        run = upgrade(host, DUAL_HOST, client=DUAL_CLIENT, clientName=DUAL_CLIENT_NAME, hostName=DUAL_HOST_NAME)
        ev["run"] = run
        up = os.path.join(d, upgraded_name(DUAL_HOST))
        if run.get("success") is True and os.path.exists(up):
            uh, ub = read_save(up)
            ev["upgraded"] = {"saveSchema": uh.get("saveSchema"), "embedded": len(ub.get("coopClientSaves") or [])}
            bad += [] if uh.get("saveSchema") == 2 else [f"upgraded saveSchema {uh.get('saveSchema')!r} (want 2)"]
            bad += [] if len(ub.get("coopClientSaves") or []) == 1 else \
                [f"{len(ub.get('coopClientSaves') or [])} coopClientSaves entries (want 1)"]
            bad += [f"report line {ln!r}" for ln in run.get("report") or [] if ln.startswith(("Schema 3:", "Schema 4:"))]
        else:
            bad.append(f"upgrade_run {run} (want success and an upgraded file)")
    finally:
        on = host.cmd({"cmd": "pvp_one_world", "gamemode": 2, "on": True})
        ev["on"] = on
    bad += [] if on.get("oneWorldHostPlaysXcom") is True else [f"switch on read back {on}"]
    cell("two_world_summary", not bad, "; ".join(bad) or
         "two-world upgrade with the switch off: schema 2, one embedded world, no one-world lines; switch back on")


def row_common(x, ev):
    host, d = x["host"], x["dir"]
    crashes = sorted(crash_set() - x["crash0"])
    changed = [n for n, h in x["placed"].items() if not os.path.exists(os.path.join(d, n)) or sha(os.path.join(d, n)) != h]
    extra = sorted(set(os.listdir(d)) - set(x["placed"]))
    stray = [n for n in extra if not n.endswith("_upgraded.sav")]
    s = host.cmd({"cmd": "coop_sides"}) if alive(host) else {}
    sides = {k: s.get(k) for k in ("oneWorldHostPlaysXcom", "oneWorldHostPlaysAliens")}
    ev["common"] = {"crashes": crashes, "alive": alive(host), "changed": changed, "added": extra, "sides": sides}
    bad = [f"{len(crashes)} new crash file(s) {crashes}"] if crashes else []
    bad += [] if alive(host) else ["host process exited"]
    bad += [f"placed file(s) changed {changed}"] if changed else []
    bad += [f"file(s) added that are not upgrades {stray}"] if stray else []
    bad += [] if all(v is True for v in sides.values()) else [f"one-world switches {sides} (want both on)"]
    cell("common", not bad, "; ".join(bad) or
         f"0 new crash files; host alive; {len(x['placed'])} placed files unchanged; added {extra}; both switches on")


ROWS = [("detect", row_detect), ("geo_file", row_geo_file), ("battle_file", row_battle_file),
        ("synth_file", row_synth_file), ("stamp_guard", row_stamp_guard), ("old_battle", row_old_battle),
        ("loads", row_loads), ("battle_loads", row_battle_loads), ("alien_detect", row_alien_detect),
        ("alien_geo_file", row_alien_geo_file), ("alien_borrow_file", row_alien_borrow_file),
        ("alien_start_file", row_alien_start_file), ("alien_ironman_file", row_alien_ironman_file),
        ("alien_refused", row_alien_refused), ("summary", row_summary), ("alien_loads", row_alien_loads),
        ("two_world", row_two_world), ("common", row_common)]
ROW_CELL = dict(zip([r for r, _ in ROWS], CELLS))


def write(d, name, data):
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)


def place(x):
    """The saves folder: the fixture copies (make_user_dir) plus the synth and derived files. Checks the Geoscape
    saves' preconditions and reads their expected values."""
    d = x["dir"]
    with open(os.path.join(d, SYNTH), "w", encoding="utf-8", newline="") as f:
        f.write(synth.pvp_embed_host())
    with open(os.path.join(d, SYNTH), "rb") as f:
        write(d, STAMP4, restamp(f.read(), 2, 4))
    with open(os.path.join(d, A_GEO), "rb") as f:
        geo = f.read()
    write(d, A_START_SYNTH, set_month(drop_embedded(geo), 0, -1))
    write(d, A_NO_XCOM, drop_embedded(geo))
    write(d, A_IRON, add_header_line(geo, "ironman: true"))
    with open(os.path.join(d, ALIEN_HOST), "rb") as f:
        write(d, ALIEN_HOST_NEWER, add_header_line(f.read(), "coopBattleProtocol: 2"))
    with open(os.path.join(d, DUAL_HOST), "w", encoding="utf-8", newline="") as f:
        f.write(synth.pvp_dual_host())
    with open(os.path.join(d, DUAL_CLIENT), "w", encoding="utf-8", newline="") as f:
        f.write(synth.pvp_dual_client())
    names = (GEO, BATTLE, ALIEN_HOST, SYNTH, STAMP4, A_GEO, A_BORROW, A_START_SYNTH, A_NO_XCOM, A_IRON,
             ALIEN_HOST_NEWER, DUAL_HOST, DUAL_CLIENT) + ((A_START,) if x["haveStart"] else ())
    x["placed"] = {n: sha(os.path.join(d, n)) for n in names}
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
    # the alien-host Geoscape save: game mode 3, two unique names, the stand-in base outside, ONE embedded X-COM world
    # with a named base that has soldiers and a craft
    h, b = read_save(os.path.join(d, A_GEO))
    roster = h.get("coopPlayers") or []
    worlds = embedded_worlds(b)
    xbases = [(bb.get("name"), len(bb.get("soldiers") or []), len(bb.get("crafts") or []))
              for _, wb in worlds for bb in wb.get("bases") or []]
    pre = {"saveSchema": h.get("saveSchema"), "coop": h.get("coop"), "coop_gamemode": b.get("coop_gamemode"),
           "roster": roster, "bases": [bb.get("name") for bb in b.get("bases") or []], "embedded": len(worlds),
           "xcomBases": xbases}
    x["alienPre"] = pre
    ok = (pre["saveSchema"] == 2 and pre["coop"] is True and pre["coop_gamemode"] == 3 and len(roster) == 2
          and all(roster) and roster[0] != roster[1] and STAND_IN_BASE in pre["bases"] and len(worlds) == 1
          and any(n and s and c for n, s, c in xbases))
    if not ok:
        raise FixtureMiss(f"{A_GEO} precondition: {pre}")
    x["alienOwner"], x["alienFunds"] = roster[1], (worlds[0][1].get("funds") or [None])[-1]
    # the borrowed-battle save: a landing record whose target is in the alien player's world, the embedded X-COM
    # world in battle with the record's craft heading for it
    h, b = read_save(os.path.join(d, A_BORROW))
    rec = h.get("coopPvpBorrowed") or {}
    worlds = embedded_worlds(b)
    kind = TARGET_KINDS.get(rec.get("targetKind"))
    xb = worlds[0][1] if len(worlds) == 1 else {}
    craft = craft_of(xb, rec.get("craftType"), rec.get("craftId")) or {}
    pre = {"record": rec, "protocol": h.get("coopBattleProtocol"), "embedded": len(worlds),
           "battleGame": "battleGame" in xb, "craft": {k: craft.get(k) for k in ("dest", "inBattlescape")},
           "target": [o.get("id") for o in b.get(kind[0]) or [] if o.get(kind[1]) == rec.get("targetCoopId")]
           if kind else None}
    x["borrowPre"] = pre
    ok = (rec.get("kind") == "landing" and rec.get("targetMirror") is True and kind is not None
          and h.get("coopBattleProtocol") == 1 and len(worlds) == 1 and "battleGame" in xb
          and craft.get("inBattlescape") is True and (craft.get("dest") or {}).get("type") not in (None, "STR_WAY_POINT")
          and len(pre["target"]) == 1)
    if not ok:
        raise FixtureMiss(f"{A_BORROW} precondition: {pre}")
    if x["haveStart"]:
        h, b = read_save(os.path.join(d, A_START))
        pre = {"saveSchema": h.get("saveSchema"), "coop": h.get("coop"), "coop_gamemode": b.get("coop_gamemode"),
               "monthsPassed": b.get("monthsPassed"), "embedded": len(b.get("coopClientSaves") or []),
               "no_bases": b.get("no_bases"), "bases": len(b.get("bases") or [])}
        x["startPre"] = pre
        ok = (pre["saveSchema"] == 2 and pre["coop"] is True and pre["coop_gamemode"] == 3 and pre["monthsPassed"] == -1
              and pre["embedded"] == 0 and pre["no_bases"] is True and pre["bases"] >= 1)
        if not ok:
            raise FixtureMiss(f"{A_START} precondition: {pre}")


def boot(x, ev):
    host = x["host"]
    try:
        host.spawn()
        host.connect()
    except Exception as e:  # noqa: BLE001
        raise FixtureMiss(f"spawn / connect: {type(e).__name__}: {str(e)[:300]}")
    r2 = host.cmd({"cmd": "pvp_one_world", "gamemode": 2, "on": True})
    r3 = host.cmd({"cmd": "pvp_one_world", "gamemode": 3, "on": True})
    s = host.cmd({"cmd": "coop_sides"})
    ev["switch"] = {"set": [r2, r3], "read": {k: s.get(k) for k in ("oneWorldHostPlaysXcom", "oneWorldHostPlaysAliens")}}
    if s.get("oneWorldHostPlaysXcom") is not True or s.get("oneWorldHostPlaysAliens") is not True:
        raise FixtureMiss(f"one-world switches not on: {ev['switch']}")
    place(x)
    ev["placed"] = x["placed"]
    ev["pre"] = {"xcomHost": x["pre"], "alienHost": x["alienPre"], "borrow": x["borrowPre"], "start": x.get("startPre")}
    ev["expected"] = {"owner": x["geoOwner"], "funds": x["geoFunds"], "dropped": x["geoDropped"],
                      "alienOwner": x["alienOwner"], "alienFunds": x["alienFunds"], "haveStart": x["haveStart"]}


def main():
    t0 = time.time()
    fixtures = [GEO, BATTLE, ALIEN_HOST, A_GEO, A_BORROW, A_START]
    have_start = os.path.exists(os.path.join(FIXTURES, A_START))
    saves = tuple(os.path.join(FIXTURES, n) for n in fixtures if n != A_START or have_start)
    ud = make_user_dir(TAG, saves=saves)
    x = {"host": GameClient("host", None, ud), "dir": os.path.join(ud, "xcom1"), "crash0": crash_set(),
         "replies": {}, "haveStart": have_start}
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
    print(f"\n==== older PvP saves upgraded to one world, both layouts: "
          f"{len(RESULTS) - len(fails)}/{len(CELLS)} cells PASS, wall {time.time() - t0:.1f} s, "
          f"cpu {cpu_load().get('cpu')} % ====", flush=True)
    for n in fails:
        print(f"  FAIL {n}", flush=True)
    sys.exit(0 if not fails and len(RESULTS) == len(CELLS) else 2)


if __name__ == "__main__":
    main()
