"""W2-H9 (owner D199 = (a); D211/D212 working assumption (a)) - a SEPARATE co-op
client never starts a battle from its OWN craft. The red rows.

Before W2-H9 a SEPARATE client whose own craft reached a landable target got the
vanilla landing prompt, and YES generated a single-player battle in its own world
(F2201: CoopHandshake::offerBattle() no-ops off the host). When the host then
landed, the client accepted the host's offer and its solo battle and world were
thrown away (F2207/F2208). Cydonia confirmed from the client's own craft is the
same defect at a second entry point (F2447).

After W2-H9, on a SEPARATE client only: no landing prompt, the craft turns back to
base and the client sees H9TEXT (CraftErrorState); confirming Cydonia from its own
craft shows the same message and starts nothing.

  H9-1  own landing blocked      client craft -> own site: refusal, craft home, no
                                 re-fire over 10 s of client clock, host untouched.
  H9-2  the F2208 sequence       host holds its landing prompt; the client's own
                                 craft arrives (refused); the host lands; the client
                                 joins the host's battle from its geoscape.
  H9-6  own Cydonia blocked      client open_cydonia + confirm_cydonia: refusal,
                                 no BriefingState, craft untouched.

Each row is its own boot and ONE run. The controls (host guest battle, SHARED
client landing, single player) are test_w2_client_landing_controls.py.

Run:  python tools/coop_test/test_w2_client_landing.py
Exit 0 = every row PASS; 2 = any row FAIL.
"""

import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, EXE, TEST_ROOT  # noqa: E402
import session  # noqa: E402

H9TEXT = ("In co-op only the host's craft can start a mission. Seat your soldiers "
          "on the host's craft to take part.")
F2201_MARKER = "[coop-handshake] offerBattle() called on a non-host machine - ignoring"
H9_LOG = "[coop-h9]"
OFFER_ACCEPTED = "[coop-handshake] battle_offer accepted"
KEEP = ["ConfirmLandingState", "CraftErrorState"]
# F2707 / ruling H9-G1: states H9-1's host must never show. The post-flush drain keeps
# them on top (never cleared), so the host top check still fails on them by name.
HOST_NEVER = ["CraftErrorState", "ConfirmLandingState", "BriefingState"]
CRASH_DIR = os.path.join(os.path.dirname(EXE), "crashlogs")
PUSH_RE = re.compile(r"\[coop-ui\] push (?:class )?(?:OpenXcom::)?(\w+) depth=")

T0 = time.time()


def log(msg):
    print("[%7.1fs] %s" % (time.time() - T0, msg), flush=True)


class RowFail(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise RowFail(msg)


# ---- shared helpers (copied into each W2-H9 file; session.py is never edited) ----

def strip(s):
    return s.replace("class OpenXcom::", "")


def stack(gc):
    return [strip(s) for s in session.states(gc)]


def top_of(gc):
    st = stack(gc)
    return st[-1] if st else ""


def crash_files():
    return set(glob.glob(os.path.join(CRASH_DIR, "crash_*")))


def log_lines(gc):
    p = os.path.join(gc.user_dir, "openxcom.log")
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def log_count(gc, needle):
    return sum(1 for line in log_lines(gc) if needle in line)


def pushes(gc, state_name):
    """WV-D112 screen record: how many times `state_name` was pushed on gc."""
    n = 0
    for line in log_lines(gc):
        m = PUSH_RE.search(line)
        if m and m.group(1) == state_name:
            n += 1
    return n


def probe(gc):
    es = gc.cmd({"cmd": "event_state"})
    return es.get("coopClientBattleRefused"), es.get("coopClientBattleRefusedLast")


def texts_of_top(gc):
    """(top state type, [plain Text contents]) from list_widgets."""
    lw = gc.cmd({"cmd": "list_widgets"})
    texts = [w.get("text") for w in lw.get("widgets", [])
             if "text" in w and "TextButton" not in w.get("type", "")]
    return strip(lw.get("state", "")), texts


def base0(gc):
    for b in gc.ok({"cmd": "geo_state"})["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base")


def skyranger(gc):
    for c in base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("no skyranger")


def own_roster_base(gc):
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        if not b["coopBaseFlag"] and not b.get("coopIcon") and b["soldiers"]:
            return b
    raise AssertionError("no real base with soldiers")


def seat_three(gc, tag):
    """Unseat all, seat the 3 lowest ids of the own roster base on the own Skyranger."""
    rb = own_roster_base(gc)
    bname = rb["name"]
    cid = skyranger(gc)["id"]
    ids = sorted(s["id"] for s in rb["soldiers"])
    for sid in ids:
        gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False,
                "base": bname})
    squad = ids[:3]
    for sid in squad:
        r = gc.cmd({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True,
                    "base": bname})
        check(r.get("seated"), "FIXTURE: %s soldier %s not seated: %s" % (tag, sid, r))
    log("%s: seated %s on own Skyranger %s at base %s" % (tag, squad, cid, bname))
    return cid, squad


def send_to_new_site(gc, tag, cid):
    b0 = base0(gc)
    site = gc.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                  "deployment": "STR_TERROR_MISSION", "lon": b0["lon"] + 0.35,
                  "lat": b0["lat"] + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    gc.wait_for("%s site listed" % tag,
                lambda: any(s["id"] == site_id and not s.get("coop")
                            for s in gc.ok({"cmd": "geo_state"})["missionSites"]) or None,
                timeout=30)
    gc.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
           "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10, "dest": "site:%d" % site_id,
           "fuel": 999999, "lowFuel": False})
    sk = skyranger(gc)
    check(sk["status"] == "STR_OUT" and sk.get("destKind") == "site"
          and sk.get("destId") == site_id,
          "FIXTURE: %s own skyranger not OUT to its own site %d: %s" % (tag, site_id, sk))
    log("%s: own site %d spawned; Skyranger %s OUT to it" % (tag, site_id, cid))
    return site_id


def world(gc):
    """Own-world numbers: funds, own base names, own soldier ids, own crafts.
    Mission sites are NOT compared (time runs on the host)."""
    g = gc.ok({"cmd": "geo_state"})
    s = gc.ok({"cmd": "get_soldiers"})
    own_b = [b for b in g["bases"] if not b.get("coopBase") and not b.get("coopIcon")]
    own_s = [b for b in s["bases"] if not b["coopBaseFlag"] and not b.get("coopIcon")]
    return {
        "funds": g.get("funds"),
        "ownBases": sorted(b["name"] for b in own_b),
        "ownSoldierIds": sorted(x["id"] for b in own_s for x in b["soldiers"]),
        "ownCrafts": sorted([c["type"], c["id"], c["status"], c.get("destKind")]
                            for b in own_b for c in b.get("crafts", [])),
    }


def world_except_craft(w, cid):
    """The same world with the own Skyranger `cid` left out."""
    out = dict(w)
    out["ownCrafts"] = [c for c in w["ownCrafts"]
                        if not ("SKYRANGER" in c[0] and c[1] == cid)]
    return out


def drain_one(gc, keep):
    top = top_of(gc)
    if "GeoscapeState" in top:
        return
    if "CoopState" in top:
        gc.cmd({"cmd": "coop_dialog_back"})
    else:
        gc.cmd({"cmd": "dismiss_popup", "keep": list(keep)})


def arrival_poll(gc, tag, others, timeout=60):
    """Every 0.5 s up to 60 s on gc: stop on top ConfirmLandingState (RED path) or
    CraftErrorState (GREEN path); otherwise drain popups (never the kept states) and
    run the clock at geo_set_speed idx 2. `others` are drained the same way, so a
    host prompt already up stays up (it is kept)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        top = top_of(gc)
        if "ConfirmLandingState" in top:
            log("%s arrival: top ConfirmLandingState" % tag)
            return "ConfirmLandingState"
        if "CraftErrorState" in top:
            log("%s arrival: top CraftErrorState" % tag)
            return "CraftErrorState"
        drain_one(gc, KEEP)
        gc.cmd({"cmd": "geo_set_speed", "idx": 2})
        for m in others:
            drain_one(m, KEEP)
            m.cmd({"cmd": "geo_set_speed", "idx": 2})
        time.sleep(0.5)
    raise RowFail("FIXTURE: %s craft never arrived in %ds (client stack %s)"
                  % (tag, timeout, stack(gc)[-3:]))


def drive_solo_to_battlescape(gc, tag, timeout=120):
    """Red evidence only: drain the client's solo battle entry to BattlescapeState."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        top = top_of(gc)
        if "BattlescapeState" in top:
            return True
        if "BriefingState" in top:
            gc.cmd({"cmd": "close_briefing"})
        elif "InventoryState" in top:
            gc.cmd({"cmd": "battle_inventory", "action": "ok"})
        elif "CoopState" in top:
            gc.cmd({"cmd": "coop_dialog_back"})
        else:
            gc.cmd({"cmd": "dismiss_popup"})
        time.sleep(0.7)
    log("%s: never reached BattlescapeState (stack %s)" % (tag, stack(gc)[-3:]))
    return False


def vacuity_guard(host, client, tag):
    """Every SEPARATE boot: the client is a connected, non-owner, SEPARATE, PvE seat."""
    c = client.cmd({"cmd": "get_coop"})
    h = host.cmd({"cmd": "get_coop"})
    ok = (c.get("coopStatic") is True and c.get("serverOwner") is False
          and c.get("shared") is False and c.get("gamemode") in (0, 1)
          and h.get("serverOwner") is True)
    check(ok, "VACUITY %s: client coopStatic=%r serverOwner=%r shared=%r gamemode=%r; "
              "host serverOwner=%r" % (tag, c.get("coopStatic"), c.get("serverOwner"),
                                        c.get("shared"), c.get("gamemode"),
                                        h.get("serverOwner")))
    log("%s vacuity guard: client coopStatic=True serverOwner=False shared=False "
        "gamemode=%s; host serverOwner=True" % (tag, c.get("gamemode")))


def boot_pair(tag):
    host = GameClient("host", 1, make_user_dir("w2h9_%s_host" % tag))
    client = GameClient("client", 2, make_user_dir("w2h9_%s_client" % tag))
    host.spawn(); client.spawn(); host.connect(); client.connect()
    return host, client


def shutdown_pair(host, client):
    for gc in (host, client):
        if gc is None:
            continue
        try:
            gc.shutdown()
        except Exception as e:  # report, never mask the row verdict
            log("%s shutdown: %r" % (gc.name, e))


def dump(tag, host, client):
    """Probe dump of both machines (STOP-IF 2 evidence)."""
    for gc, who in ((host, "HOST"), (client, "CLIENT")):
        try:
            es = gc.cmd({"cmd": "event_state"})
            gco = gc.cmd({"cmd": "get_coop"})
            bs = gc.cmd({"cmd": "battle_state"})
            log("DUMP %s %s: stack=%s phase=%s battleId=%s hostSim=%s desyncSeen=%s "
                "refused=%s last=%r coopStatic=%s serverOwner=%s shared=%s gamemode=%s "
                "inBattle=%s missionType=%s" % (
                    tag, who, stack(gc)[-4:], es.get("phase"), es.get("battleId"),
                    es.get("hostSim"), es.get("desyncSeen"),
                    es.get("coopClientBattleRefused"), es.get("coopClientBattleRefusedLast"),
                    gco.get("coopStatic"), gco.get("serverOwner"), gco.get("shared"),
                    gco.get("gamemode"), bs.get("inBattle"), bs.get("missionType")))
        except Exception as e:
            log("DUMP %s %s failed: %r" % (tag, who, e))


# ---- H9-1: own landing blocked ---------------------------------------------------

def row_h9_1():
    host = client = None
    crash_before = crash_files()
    try:
        host, client = boot_pair("1")
        session.new_campaign(host, client, port="48483")
        vacuity_guard(host, client, "H9-1")
        w0_host, w0_client = world(host), world(client)
        p0 = probe(client)
        check(p0 == (0, ""), "H9-1 probe baseline: client refused/last = %r, want (0, '')" % (p0,))
        cid, squad = seat_three(client, "CLIENT")
        send_to_new_site(client, "CLIENT", cid)
        path = arrival_poll(client, "CLIENT", (host,))

        if path == "ConfirmLandingState":
            # RED (commit 1): the prompt appeared. Capture the F2201 solo battle.
            p1 = probe(client)
            shot = os.path.join(TEST_ROOT, "w2h9_h9_1_prompt_s%s.png"
                                % os.environ.get("OXC_HARNESS_SLOT", "0"))
            client.cmd({"cmd": "screenshot", "path": shot})
            log("H9-1 RED: screenshot lever check %s exists=%s size=%s" % (
                shot, os.path.exists(shot), os.path.getsize(shot) if os.path.exists(shot) else 0))
            r = client.cmd({"cmd": "confirm_landing"})
            log("H9-1 RED: client confirm_landing -> %s" % r)
            entered = None
            deadline = time.time() + 30
            while time.time() < deadline and not entered:
                st = stack(client)
                entered = next((s for s in reversed(st)
                                if s in ("BriefingState", "BattlescapeState")), None)
                if not entered:
                    time.sleep(0.25)
            bs = client.cmd({"cmd": "battle_state"})
            es = client.cmd({"cmd": "event_state"})
            time.sleep(3)  # house log flush
            marker = log_count(client, F2201_MARKER)
            named = (p1 == (0, "") and entered is not None and bs.get("inBattle") is True
                     and es.get("battleId") == 0 and es.get("phase") == "Idle" and marker == 1)
            log("RED-EVIDENCE H9-1: probe=%r; after confirm_landing client stack top=%s "
                "entered=%s inBattle=%s missionType=%s battleId=%s phase=%s F2201-marker=%d; "
                "as named=%s" % (p1, top_of(client), entered, bs.get("inBattle"),
                                  bs.get("missionType"), es.get("battleId"), es.get("phase"),
                                  marker, named))
            raise RowFail("H9-1: client arrival popped ConfirmLandingState - W2-H9 refusal "
                          "expected; confirm_landing then started the solo battle "
                          "(inBattle=%s battleId=%s phase=%s F2201 marker=%d)"
                          % (bs.get("inBattle"), es.get("battleId"), es.get("phase"), marker))

        # GREEN (commit 2): the refusal.
        state, texts = texts_of_top(client)
        check("CraftErrorState" in state, "H9-1: client top %s, want CraftErrorState" % state)
        check(H9TEXT in texts, "H9-1: CraftErrorState Text %r != H9TEXT" % (texts,))
        p1 = probe(client)
        check(p1 == (1, "landing:%d" % cid),
              "H9-1: client probe %r, want (1, 'landing:%d')" % (p1, cid))
        sk = skyranger(client)
        check(sk["id"] == cid and sk["status"] == "STR_OUT" and sk.get("destKind") == "base",
              "H9-1: craft %s status=%s destKind=%s, want STR_OUT / base"
              % (cid, sk["status"], sk.get("destKind")))
        aboard = sorted(s["id"] for s in own_roster_base(client)["soldiers"]
                        if s.get("craftId") == cid)
        check(aboard == sorted(squad), "H9-1: soldiers aboard %s %s, want %s"
              % (cid, aboard, sorted(squad)))
        check(client.cmd({"cmd": "get_coop"}).get("inBattle") is False,
              "H9-1: client get_coop.inBattle is not False")
        shot = os.path.join(TEST_ROOT, "w2h9_h9_1_refusal_s%s.png"
                            % os.environ.get("OXC_HARNESS_SLOT", "0"))
        client.cmd({"cmd": "screenshot", "path": shot})
        check(os.path.exists(shot) and os.path.getsize(shot) > 0,
              "H9-1: refusal screenshot not saved at %s" % shot)
        log("H9-1: refusal screenshot saved %s (%d bytes)" % (shot, os.path.getsize(shot)))
        time.sleep(3)  # house log flush
        check(pushes(client, "ConfirmLandingState") == 0,
              "H9-1: client ConfirmLandingState pushes %d, want 0"
              % pushes(client, "ConfirmLandingState"))
        check(pushes(client, "BriefingState") == 0,
              "H9-1: client BriefingState pushes %d, want 0" % pushes(client, "BriefingState"))
        log("PASS H9-1 refusal: CraftErrorState Text == H9TEXT; probe (1, 'landing:%d'); "
            "craft STR_OUT -> base; squad %s still aboard; 0 ConfirmLandingState / "
            "BriefingState pushes; inBattle false" % (cid, sorted(squad)))

        # No re-fire: dismiss the refusal and run the client clock 10 s.
        client.cmd({"cmd": "dismiss_popup"})
        deadline = time.time() + 10
        while time.time() < deadline:
            drain_one(client, ())
            client.cmd({"cmd": "geo_set_speed", "idx": 2})
            drain_one(host, ())
            time.sleep(0.5)
        time.sleep(3)  # house log flush
        p2 = probe(client)
        check(p2[0] == 1, "H9-1: probe %r after 10 s of client clock, want 1 (re-fired?)" % (p2,))
        check(pushes(client, "ConfirmLandingState") == 0,
              "H9-1: a ConfirmLandingState was pushed after the refusal (re-fire)")
        # F2707 / ruling H9-G1: the host clock runs through the flush, so a natural geoscape
        # popup (UfoDetectedState at K=2) can reach the host after the loop's last drain.
        # Clear it with the loop's own step; HOST_NEVER states are kept, never cleared.
        host_top = top_of(host)
        drain_one(host, HOST_NEVER)
        if "GeoscapeState" not in host_top:
            log("H9-1: host top %s after the flush -> drain step (F2707)" % host_top)
        check("GeoscapeState" in top_of(host), "H9-1: host top %s, want GeoscapeState"
              % top_of(host))
        check(pushes(host, "CraftErrorState") == 0, "H9-1: host CraftErrorState pushes %d, want 0"
              % pushes(host, "CraftErrorState"))
        for name in ("ConfirmLandingState", "BriefingState"):
            check(pushes(host, name) == 0, "H9-1: host %s pushes %d, want 0"
                  % (name, pushes(host, name)))
        check(log_count(host, H9_LOG) == 0, "H9-1: host logged %d [coop-h9] lines, want 0"
              % log_count(host, H9_LOG))
        w1_host, w1_client = world(host), world(client)
        check(w1_host == w0_host, "H9-1: host world changed: %s -> %s"
              % (json.dumps(w0_host), json.dumps(w1_host)))
        check(world_except_craft(w1_client, cid) == world_except_craft(w0_client, cid),
              "H9-1: client world changed beyond craft %d: %s -> %s"
              % (cid, json.dumps(w0_client), json.dumps(w1_client)))
        for gc, who in ((host, "host"), (client, "client")):
            check(gc.cmd({"cmd": "event_state"}).get("desyncSeen") is False,
                  "H9-1: %s desyncSeen" % who)
            check(gc.cmd({"cmd": "get_coop"}).get("coopStatic") is True,
                  "H9-1: %s coopStatic is not True" % who)
        new_crash = sorted(crash_files() - crash_before)
        check(not new_crash, "H9-1: new crashlog files %s" % new_crash)
        log("PASS H9-1 no re-fire + host untouched: probe %r after 10 s; 0 ConfirmLandingState "
            "pushes; host top GeoscapeState, 0 CraftErrorState / ConfirmLandingState / "
            "BriefingState pushes, 0 [coop-h9] lines; "
            "host world == W0; client world == W0 except craft %d; desyncSeen false and "
            "coopStatic true on both; no new crashlog" % (p2, cid))
    except Exception:
        if host is not None and client is not None:
            dump("H9-1", host, client)
        raise
    finally:
        shutdown_pair(host, client)


# ---- H9-2: the F2208 sequence ------------------------------------------------------

def row_h9_2():
    host = client = None
    try:
        host, client = boot_pair("2")
        session.new_campaign(host, client, port="48484")
        vacuity_guard(host, client, "H9-2")
        p0 = probe(client)
        check(p0 == (0, ""), "H9-2 probe baseline: client refused/last = %r, want (0, '')" % (p0,))
        # 1) the host's craft arrives first; its prompt is HELD (d179 boot 2 steps).
        hcid, _ = seat_three(host, "HOST")
        session.drain_host_coop_notice(host)
        send_to_new_site(host, "HOST", hcid)
        hpath = arrival_poll(host, "HOST", (client,))
        check(hpath == "ConfirmLandingState",
              "FIXTURE H9-2: host arrival reached %s, want its ConfirmLandingState" % hpath)
        w1 = world(client)
        log("H9-2 W1 (client, host prompt held): %s" % json.dumps(w1))
        # 2) the client's own craft to its own site; never dismiss the host's prompt.
        ccid, _ = seat_three(client, "CLIENT")
        send_to_new_site(client, "CLIENT", ccid)
        cpath = arrival_poll(client, "CLIENT", (host,))
        check(session.has_state(host, "ConfirmLandingState"),
              "FIXTURE H9-2: host prompt gone before the host landing: %s" % stack(host)[-3:])

        if cpath == "ConfirmLandingState":
            # RED (commit 1): the client lands its own craft -> solo battle (F2201).
            client.cmd({"cmd": "confirm_landing"})
            drive_solo_to_battlescape(client, "CLIENT")
            time.sleep(1.0)
            bs_c = client.cmd({"cmd": "battle_state"})
            es_c = client.cmd({"cmd": "event_state"})
            before = world(client)
            log("RED-EVIDENCE H9-2 at host coop_mission_start: client inBattle=%s "
                "missionType=%s battleId=%s phase=%s; client funds/bases W1=%s/%s, "
                "in its solo battle=%s/%s" % (
                    bs_c.get("inBattle"), bs_c.get("missionType"), es_c.get("battleId"),
                    es_c.get("phase"), w1["funds"], w1["ownBases"], before["funds"],
                    before["ownBases"]))
            host.ok({"cmd": "coop_mission_start"})
            host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"),
                          timeout=60, interval=0.5)
            host.cmd({"cmd": "close_briefing"})
            both = session.drive_both_to_tactical(host, client)
            time.sleep(5)
            try:
                client.wait_for("client phase Active",
                                lambda: client.cmd({"cmd": "event_state"}).get("phase")
                                == "Active" or None, timeout=30, interval=0.5)
            except TimeoutError as e:
                log("H9-2 RED: %s" % e)
            es_c2 = client.cmd({"cmd": "event_state"})
            after = world(client)
            time.sleep(3)  # house log flush
            brief = pushes(client, "BriefingState")
            marker = log_count(client, F2201_MARKER)
            named = (bs_c.get("inBattle") is True and es_c.get("battleId") == 0
                     and brief == 2 and marker == 1)
            log("RED-EVIDENCE H9-2 after the offer: drive_both_to_tactical=%s client phase=%s "
                "battleId=%s; client BriefingState pushes=%d F2201-marker=%d; client funds "
                "%s -> %s, own bases %s -> %s (F2207/F2208); as named=%s" % (
                    both, es_c2.get("phase"), es_c2.get("battleId"), brief, marker,
                    w1["funds"], after["funds"], w1["ownBases"], after["ownBases"], named))
            raise RowFail("H9-2: the client was in its own battle when the host's offer "
                          "arrived (inBattle=%s missionType=%s battleId=%s; BriefingState "
                          "pushes %d; F2201 marker %d; funds %s -> %s)" % (
                              bs_c.get("inBattle"), bs_c.get("missionType"),
                              es_c.get("battleId"), brief, marker, w1["funds"],
                              after["funds"]))

        # GREEN (commit 2): refused; the client waits on its geoscape.
        check(cpath == "CraftErrorState", "H9-2: client arrival reached %s" % cpath)
        client.cmd({"cmd": "dismiss_popup"})
        client.wait_for("client back on its geoscape",
                        lambda: "GeoscapeState" in top_of(client) or None, timeout=10,
                        interval=0.25)
        check(client.cmd({"cmd": "get_coop"}).get("inBattle") is False,
              "H9-2: client inBattle at the host's coop_mission_start")
        wc = world(client)
        check(world_except_craft(wc, ccid) == world_except_craft(w1, ccid),
              "H9-2: client world changed beyond craft %d before the host landing: %s -> %s"
              % (ccid, json.dumps(w1), json.dumps(wc)))
        log("PASS H9-2 at the host's coop_mission_start: client on GeoscapeState, inBattle "
            "false, world == W1 except craft %d" % ccid)
        host.ok({"cmd": "coop_mission_start"})
        host.wait_for("host briefing", lambda: session.has_state(host, "BriefingState"),
                      timeout=60, interval=0.5)
        host.cmd({"cmd": "close_briefing"})
        check(session.drive_both_to_tactical(host, client),
              "H9-2: drive_both_to_tactical timed out (host=%s client=%s)"
              % (stack(host)[-3:], stack(client)[-3:]))
        time.sleep(5)
        client.wait_for("client phase Active",
                        lambda: client.cmd({"cmd": "event_state"}).get("phase") == "Active"
                        or None, timeout=30, interval=0.5)
        es_h = host.cmd({"cmd": "event_state"})
        es_c = client.cmd({"cmd": "event_state"})
        check(es_c.get("phase") == "Active", "H9-2: client phase %s" % es_c.get("phase"))
        check(isinstance(es_h.get("battleId"), int) and es_h.get("battleId") > 0
              and es_c.get("battleId") == es_h.get("battleId"),
              "H9-2: battleId client %s host %s" % (es_c.get("battleId"), es_h.get("battleId")))
        check(es_c.get("hostSim") is False, "H9-2: client hostSim %s" % es_c.get("hostSim"))
        fh = host.cmd({"cmd": "battle_state"}).get("mapFingerprint")
        fc = client.cmd({"cmd": "battle_state"}).get("mapFingerprint")
        check(fh is not None and fh == fc, "H9-2: mapFingerprint host %s client %s" % (fh, fc))
        time.sleep(3)  # house log flush
        brief = pushes(client, "BriefingState")
        check(brief == 1, "H9-2: client BriefingState pushes %d, want 1 (the join's)" % brief)
        check(log_count(client, F2201_MARKER) == 0, "H9-2: client F2201 marker %d, want 0"
              % log_count(client, F2201_MARKER))
        check(log_count(client, OFFER_ACCEPTED) == 1, "H9-2: client battle_offer accepted %d, "
              "want 1" % log_count(client, OFFER_ACCEPTED))
        check(probe(client)[0] == 1, "H9-2: client probe %r, want 1" % (probe(client),))
        for gc, who in ((host, "host"), (client, "client")):
            check(gc.cmd({"cmd": "event_state"}).get("desyncSeen") is False,
                  "H9-2: %s desyncSeen" % who)
        log("PASS H9-2 the host's landing: client phase Active, battleId %s == host, hostSim "
            "false, mapFingerprint equal, 1 BriefingState push, F2201 marker 0, battle_offer "
            "accepted 1, probe 1, desyncSeen false on both" % es_c.get("battleId"))
    except Exception:
        if host is not None and client is not None:
            dump("H9-2", host, client)
        raise
    finally:
        shutdown_pair(host, client)


# ---- H9-6: own Cydonia blocked -----------------------------------------------------

def row_h9_6():
    host = client = None
    try:
        host, client = boot_pair("6")
        session.new_campaign(host, client, port="48489")
        vacuity_guard(host, client, "H9-6")
        w0_host = world(host)
        p0 = probe(client)
        check(p0 == (0, ""), "H9-6 probe baseline: client refused/last = %r, want (0, '')" % (p0,))
        cid, _ = seat_three(client, "CLIENT")
        sk0 = skyranger(client)
        client.ok({"cmd": "open_cydonia", "craft_id": cid})
        client.wait_for("client ConfirmCydoniaState",
                        lambda: session.has_state(client, "ConfirmCydoniaState"), timeout=15,
                        interval=0.25)
        t_yes = time.time()
        client.ok({"cmd": "confirm_cydonia"})
        path = None
        deadline = time.time() + 30
        while time.time() < deadline and path is None:
            st = stack(client)
            if st and "CraftErrorState" in st[-1]:
                path = "CraftErrorState"
            elif any("BriefingState" in s for s in st):
                path = "BriefingState"
            else:
                time.sleep(0.25)
        elapsed = time.time() - t_yes

        if path == "BriefingState":
            # RED (commit 1): the solo Mars battle.
            p1 = probe(client)
            bs = client.cmd({"cmd": "battle_state"})
            time.sleep(3)  # house log flush
            brief = pushes(client, "BriefingState")
            marker = log_count(client, F2201_MARKER)
            named = brief >= 1 and marker == 1 and p1 == (0, "")
            log("RED-EVIDENCE H9-6: after confirm_cydonia client stack=%s inBattle=%s "
                "missionType=%s; BriefingState pushes=%d F2201-marker=%d probe=%r; as named=%s"
                % (stack(client)[-3:], bs.get("inBattle"), bs.get("missionType"), brief,
                   marker, p1, named))
            raise RowFail("H9-6: confirm_cydonia on the client pushed BriefingState (solo Mars "
                          "battle %s) - W2-H9 refusal expected (F2201 marker %d, probe %r)"
                          % (bs.get("missionType"), marker, p1))

        # GREEN (commit 2): the refusal.
        check(path == "CraftErrorState", "H9-6: no CraftErrorState and no BriefingState "
              "within 30 s (client stack %s)" % stack(client)[-3:])
        check(elapsed <= 5.0, "H9-6: refusal took %.1f s, want <= 5 s" % elapsed)
        state, texts = texts_of_top(client)
        check(H9TEXT in texts, "H9-6: CraftErrorState Text %r != H9TEXT" % (texts,))
        st = stack(client)
        check(not any("ConfirmCydoniaState" in s for s in st),
              "H9-6: ConfirmCydoniaState still on the stack %s" % st)
        check(any("GeoscapeState" in s for s in st), "H9-6: GeoscapeState gone %s" % st)
        check(client.cmd({"cmd": "get_coop"}).get("inBattle") is False,
              "H9-6: client inBattle is not False")
        p1 = probe(client)
        check(p1 == (1, "cydonia:%d" % cid), "H9-6: client probe %r, want (1, 'cydonia:%d')"
              % (p1, cid))
        sk1 = skyranger(client)
        check((sk1["status"], sk1.get("destKind")) == (sk0["status"], sk0.get("destKind")),
              "H9-6: craft %d (status, destKind) %s -> %s" % (
                  cid, (sk0["status"], sk0.get("destKind")),
                  (sk1["status"], sk1.get("destKind"))))
        time.sleep(3)  # house log flush
        check(pushes(client, "BriefingState") == 0, "H9-6: client BriefingState pushes %d, "
              "want 0" % pushes(client, "BriefingState"))
        check(world(host) == w0_host, "H9-6: host world changed")
        check(log_count(host, H9_LOG) == 0, "H9-6: host logged %d [coop-h9] lines"
              % log_count(host, H9_LOG))
        log("PASS H9-6: refusal in %.1f s; Text == H9TEXT; ConfirmCydoniaState gone, "
            "GeoscapeState kept; inBattle false; 0 BriefingState pushes; probe (1, "
            "'cydonia:%d'); craft (status, destKind) unchanged; host world == W0, 0 "
            "[coop-h9] lines" % (elapsed, cid))
    except Exception:
        if host is not None and client is not None:
            dump("H9-6", host, client)
        raise
    finally:
        shutdown_pair(host, client)


ROWS = (("H9-1", row_h9_1), ("H9-2", row_h9_2), ("H9-6", row_h9_6))


def main():
    failed = []
    walls = []
    for name, fn in ROWS:
        t = time.time()
        try:
            fn()
            print("[PASS] %s" % name, flush=True)
        except Exception as e:
            failed.append(name)
            print("[FAIL] %s: %s: %s" % (name, type(e).__name__, e), flush=True)
        walls.append((name, time.time() - t))
    print("\n==== W2-H9 red rows summary ====")
    for name, w in walls:
        print("  %-5s %-4s wall %.1fs" % (name, "FAIL" if name in failed else "PASS", w))
    print("  total wall %.1fs; FAILED: %s" % (time.time() - T0, ", ".join(failed) or "none"))
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
