"""Screenshot driver for PR #87: VoteMenu, the skirmish EQUIP CRAFT lock, and
the clipboard-paste target menus.

NOT a test (the name deliberately avoids the test_*.py glob CI runs): it drives
real game instances through the harness and saves a PNG of each UI surface the
PR touches, so the visuals can be reviewed without playing the flows by hand.

Scenes
------
  1  campaign VoteMenu, freshly opened on BOTH machines (WAITING rows + TIME:)
  2  the same vote after a YES majority        -> VOTE PASSED + CLOSE (host)
  3  a second vote answered NO                 -> VOTE FAILED (client)
  4  a third request inside the 60s starter cooldown
                                               -> COOP_DLG_VOTE_COOLDOWN (host)
  5  the abandon-mission VoteMenu over a LIVE shared battle (both machines),
     which also shows the battlescape-themed VoteMenu palette
  6  the skirmish (NEW BATTLE > COOP) lobby: host BATTLE SETTINGS, client with
     no action button, the host's confirm-equip-craft gate
     (COOP_DLG_CONFIRM_EQUIP_CRAFT), the client's lobby once the craft is
     locked (EQUIP CRAFT appears), and the client's craft screen
  7  the clipboard paste targets (HostMenu / DirectConnect / AddServerMenu)
     with their IP / port TextEdits visible

Every scene is independent and wrapped: one failure does not stop the rest, and
the run still exits 0 as long as at least one PNG was written.

Process discipline: the harness takes a MACHINE-WIDE lock and every group uses
fixed ports, so the groups run strictly one after another and each pair is shut
down before the next one spawns.

Usage:  python tools/coop_test/shoot_pr87_ui.py [outdir]
        (outdir defaults to .\\pr87_shots, relative to the current directory)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import shared_fixture

# ---- configuration --------------------------------------------------------

# Free port block: nothing else in tools/coop_test/ uses 493xx. Each triple is
# (host test port, client test port, coop session port).
PORTS_VOTE = (49300, 49301, 49302)      # scenes 1-4: campaign vote pair
PORTS_BATTLE = (49304, 49305, 49306)    # scene 5: SHARED battle pair
PORTS_SKIRMISH = (49308, 49309, 49310)  # scene 6: skirmish lobby pair
PORT_MENUS = 49312                      # scene 7: single instance, no session

# Let the POPUP_BOTH open animation finish before the frame is grabbed; the
# same value scenario_upgrade_shots.py uses.
SETTLE = 1.2

VOTE_COOLDOWN_CODE = 558   # COOP_DLG_VOTE_COOLDOWN
CONFIRM_EQUIP_CODE = 557   # COOP_DLG_CONFIRM_EQUIP_CRAFT

# Candidate TestServer commands for the two paste-target menus that have no
# wired handler today. ServerList::btnDirectConnectClick / btnAddServerClick are
# public, so a one-line handler would make these reachable; probing by name
# keeps this driver working the day one is added instead of hard-coding a skip.
DIRECT_CONNECT_CMDS = ("server_list_direct_connect", "server_list_direct",
                       "open_direct_connect", "direct_connect")
ADD_SERVER_CMDS = ("server_list_add_server", "server_list_add",
                   "open_add_server", "add_server_menu")

# ---- bookkeeping ----------------------------------------------------------

OUTDIR = None
SHOTS = []      # absolute paths actually written
RESULTS = []    # (scene id, title, "PASS"/"SKIP", note)


class Unreachable(Exception):
    """No TestServer command path reaches this UI - a recorded SKIP, not a bug."""


def shot(gc, name):
    """Settle a frame, then save <OUTDIR>/<name> from `gc`'s window."""
    time.sleep(SETTLE)
    path = os.path.join(OUTDIR, name)
    gc.ok({"cmd": "screenshot", "path": path})
    SHOTS.append(path)
    print("    shot " + name)
    return path


def scene(sid, title, fn, *args):
    """Run one scene; record PASS/SKIP instead of letting it kill the run."""
    print("--- scene %s: %s" % (sid, title))
    try:
        fn(*args)
    except Unreachable as e:
        RESULTS.append((sid, title, "SKIP", str(e)))
        print("SKIP scene %s: %s" % (sid, e))
    except Exception as e:
        RESULTS.append((sid, title, "SKIP", "%s: %s" % (type(e).__name__, e)))
        print("SKIP scene %s: %s: %s" % (sid, type(e).__name__, e))
    else:
        RESULTS.append((sid, title, "PASS", ""))
        print("PASS scene %s" % sid)


def group(scene_ids, fn):
    """Run a process group; if its bring-up dies, every scene it owns that has
    not already reported becomes a SKIP with the bring-up error."""
    try:
        fn()
    except Exception as e:
        done = set(sid for sid, _t, _s, _n in RESULTS)
        note = "group bring-up failed: %s: %s" % (type(e).__name__, e)
        for sid, title in scene_ids:
            if sid not in done:
                RESULTS.append((sid, title, "SKIP", note))
                print("SKIP scene %s: %s" % (sid, note))


# ---- small probes ---------------------------------------------------------

def wait_state(gc, name, timeout=90, interval=0.5):
    return gc.wait_for("%s: %s" % (gc.name, name),
                       lambda: session.has_state(gc, name),
                       timeout=timeout, interval=interval)


def wait_vote(gc, desc, predicate, timeout=30):
    return gc.wait_for(
        "%s: %s" % (gc.name, desc),
        lambda: (lambda s: s if predicate(s) else None)(gc.ok({"cmd": "vote_state"})),
        timeout=timeout, interval=0.25)


def wait_dialog(gc, code, desc, timeout=20):
    return gc.wait_for(
        "%s: %s" % (gc.name, desc),
        lambda: (lambda s: s if (s.get("present") and s.get("code") == code)
                 else None)(gc.ok({"cmd": "coop_dialog_info"})),
        timeout=timeout, interval=0.25)


def lobby(gc):
    return gc.cmd({"cmd": "lobby_state"})


def close_votes(*clients):
    """Close a finished VoteMenu wherever one is still up. Tolerant on purpose:
    vote_close errors out when there is no menu or it has not finished."""
    for gc in clients:
        gc.cmd({"cmd": "vote_close"})


# ==== scenes 1-4: campaign / geoscape votes ================================

def scene_01(host, client):
    """A fresh vote: both machines open a VoteMenu with WAITING rows + TIME:."""
    r = host.ok({"cmd": "vote_request", "action": "test_vote",
                 "title": "SCREENSHOT VOTE",
                 "question": "Capture the VoteMenu for PR #87?"})
    assert r.get("accepted"), "host vote_request was rejected: %r" % (r,)
    for gc in (host, client):
        wait_vote(gc, "VoteMenu open",
                  lambda s: s.get("active") and s.get("menuOpen"))
    shot(host, "01_host_votemenu_open.png")
    shot(client, "02_client_votemenu_open.png")


def scene_02(host, client):
    """The peer votes YES: 2/2 majority -> VOTE PASSED, CLOSE offered."""
    cast = client.ok({"cmd": "vote_cast", "yes": True})
    assert cast.get("accepted"), "client vote_cast was rejected: %r" % (cast,)
    v = wait_vote(host, "vote PASSED",
                  lambda s: s.get("finished") and s.get("passed"))
    assert v.get("menuStatus") == "VOTE PASSED", v
    shot(host, "03_host_vote_passed.png")


def scene_03(host, client):
    """A second vote, answered NO. With two seats requiredYes is 2, so the
    starter's automatic YES plus one NO settles it as VOTE FAILED."""
    close_votes(host, client)
    # The host started the previous vote, so its seat is inside the 60s starter
    # cooldown; expire every seat's cooldown rather than sleep it out.
    host.ok({"cmd": "vote_clear_cooldown"})
    r = host.ok({"cmd": "vote_request", "action": "test_vote",
                 "title": "SCREENSHOT VOTE (NO)",
                 "question": "Reject this one for the FAILED screenshot?"})
    assert r.get("accepted"), "second host vote_request was rejected: %r" % (r,)
    for gc in (host, client):
        wait_vote(gc, "second VoteMenu open",
                  lambda s: s.get("active") and s.get("menuOpen"))
    cast = client.ok({"cmd": "vote_cast", "yes": False})
    assert cast.get("accepted"), "client NO vote was rejected: %r" % (cast,)
    v = wait_vote(client, "vote FAILED",
                  lambda s: s.get("finished") and not s.get("passed"))
    assert v.get("menuStatus") == "VOTE FAILED", v
    shot(client, "04_client_vote_failed.png")


def scene_04(host, client):
    """No vote_clear_cooldown this time: the host's own request is refused
    locally and it gets the COOP_DLG_VOTE_COOLDOWN warning."""
    close_votes(host, client)
    r = host.ok({"cmd": "vote_request", "action": "test_vote",
                 "title": "SCREENSHOT VOTE (COOLDOWN)",
                 "question": "This request is inside the starter cooldown."})
    assert r.get("accepted") is False, \
        "expected a local cooldown rejection, got %r" % (r,)
    wait_dialog(host, VOTE_COOLDOWN_CODE, "vote cooldown dialog")
    shot(host, "05_host_vote_cooldown.png")
    host.cmd({"cmd": "coop_dialog_back"})


def group_campaign_votes():
    host = GameClient("host", PORTS_VOTE[0], make_user_dir("pr87_vote_host"))
    client = GameClient("client", PORTS_VOTE[1], make_user_dir("pr87_vote_client"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        session.new_campaign(host, client, port=str(PORTS_VOTE[2]),
                             host_name="AliceHost", client_name="BobClient",
                             host_base="Alice Base", client_base="Bob Base")
        scene("1", "geoscape VoteMenu open on both machines", scene_01, host, client)
        scene("2", "VOTE PASSED", scene_02, host, client)
        scene("3", "VOTE FAILED", scene_03, host, client)
        scene("4", "vote starter cooldown dialog", scene_04, host, client)
    finally:
        host.shutdown(); client.shutdown()


# ==== scene 5: the abandon-mission VoteMenu over a live battle =============

def _geo(gc):
    return gc.ok({"cmd": "geo_state"})


def _base0(gc):
    for b in _geo(gc)["bases"]:
        if not b.get("coopBase") and not b.get("coopIcon"):
            return b
    raise AssertionError("no real base")


def _roster(gc):
    out = []
    for b in gc.ok({"cmd": "get_soldiers"})["bases"]:
        out.extend(b["soldiers"])
    return out


def _skyranger(gc):
    for c in _base0(gc)["crafts"]:
        if "SKYRANGER" in c["type"]:
            return c
    raise AssertionError("no skyranger")


def bring_up_battle(host, client):
    """Fly a two-soldier shared squad into a terror site and reach the tactical
    map on BOTH machines. Same recipe as test_vote_abort_battle.py."""
    b0 = _base0(host)
    blon, blat = b0["lon"], b0["lat"]
    cid = _skyranger(host)["id"]
    rh = sorted(s["id"] for s in _roster(host))
    squad = [rh[0], rh[1]]

    # one host-owned seat + one client-owned seat, agreed on both machines
    for gc in (host, client):
        for slot, sid in enumerate(squad):
            gc.ok({"cmd": "set_soldier_owner", "soldier_id": sid, "owner": slot})
    # the starting Skyranger ships FULL - empty it before boarding the squad
    for sid in rh:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": False})
    for sid in squad:
        host.ok({"cmd": "craft_assign", "craft_id": cid, "soldier_id": sid, "on": True})

    def _aboard(gc):
        return sorted(s["id"] for s in _roster(gc) if s["craftId"] == cid)

    for gc in (host, client):
        gc.wait_for("%s squad aboard" % gc.name,
                    lambda gc=gc: (_aboard(gc) == sorted(squad)) or None,
                    timeout=40, interval=0.5)

    site = host.ok({"cmd": "spawn_mission_site", "mission": "STR_ALIEN_TERROR",
                    "deployment": "STR_TERROR_MISSION", "lon": blon + 0.35,
                    "lat": blat + 0.10, "race": "STR_SECTOID", "hours": 240})
    site_id = site["site_id"]
    host.wait_for("site on host",
                  lambda: any(s["id"] == site_id for s in _geo(host)["missionSites"]) or None,
                  timeout=30)
    host.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
             "lon": blon + 0.34, "lat": blat + 0.10, "dest": "site:%d" % site_id,
             "fuel": 999999, "lowFuel": False})

    def _landing_prompt():
        if session.has_state(host, "ConfirmLandingState"):
            return True
        host.cmd({"cmd": "geo_set_speed", "idx": 2})  # not geo_run: it auto-declines
        return None

    host.wait_for("ConfirmLandingState on host", _landing_prompt,
                  timeout=90, interval=0.5)
    host.ok({"cmd": "confirm_landing"})
    for gc in (host, client):
        gc.wait_for("%s entered the battle" % gc.name,
                    lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                    timeout=180, interval=1.0)
    for gc in (host, client):
        wait_state(gc, "BriefingState", timeout=120)
        gc.ok({"cmd": "close_briefing"})
    for gc in (host, client):
        wait_state(gc, "InventoryState", timeout=120)
        gc.ok({"cmd": "battle_inventory", "action": "ok"})
    for gc in (host, client):
        wait_state(gc, "BattlescapeState", timeout=120)


def scene_05(host, client):
    """ABORT in a co-op battle opens the abandon-mission vote on both machines
    (the battlescape keeps running underneath it)."""
    host.ok({"cmd": "battle_action", "action": "abort"})
    for gc in (host, client):
        v = wait_vote(gc, "abandon-mission VoteMenu",
                      lambda s: s.get("active") and s.get("menuOpen"), timeout=25)
        assert v["action"] == "abandon_mission", \
            "%s: ABORT opened the wrong vote: %r" % (gc.name, v)
    # Both shots have to land inside the vote's 30s deadline; 2 x SETTLE is
    # nowhere near it.
    shot(host, "06_host_battle_votemenu.png")
    shot(client, "07_client_battle_votemenu.png")


def group_battle_vote():
    js = shared_fixture.bring_up("pr87bat", PORTS_BATTLE)
    host, client = js.host, js.client
    try:
        bring_up_battle(host, client)
        scene("5", "abandon-mission VoteMenu over a live shared battle",
              scene_05, host, client)
        # Leave the battle the only safe way: the peer's YES carries the
        # majority, the host runs abortMissionByVote -> debriefing -> geoscape.
        try:
            session.coop_abort_battle(host, client)
        except Exception as e:
            print("  note: coop_abort_battle teardown failed: %s: %s"
                  % (type(e).__name__, e))
    finally:
        js.shutdown()


# ==== scene 6: the skirmish lobby and the EQUIP CRAFT lock =================

def skirmish_bring_up(host, client, port):
    """NEW BATTLE > COOP on both machines: host hosts, client joins, both
    dismiss the 'player joined' popup."""
    host.ok({"cmd": "open_new_battle"})
    wait_state(host, "NewBattleState")
    host.ok({"cmd": "newbattle_coop"})
    wait_state(host, "ServerList")
    host.ok({"cmd": "server_list_host"})
    wait_state(host, "HostMenu")
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv",
             "port": str(port), "player": "HostPlayer"})
    wait_state(host, "LobbyMenu")

    client.ok({"cmd": "open_new_battle"})
    wait_state(client, "NewBattleState")
    client.ok({"cmd": "newbattle_coop"})
    wait_state(client, "ServerList")
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": str(port),
               "player": "ClientPlayer"})
    for gc in (host, client):
        wait_state(gc, "LobbyMenu")
        gc.wait_for("%s join popup" % gc.name,
                    lambda gc=gc: session.has_state(gc, "Profile"), timeout=60)
        gc.ok({"cmd": "profile_ok"})
    host.wait_for("host action button offered",
                  lambda: lobby(host).get("buttonVisible") or None,
                  timeout=60, interval=0.5)


def scene_06(host, client):
    """Host lobby (BATTLE SETTINGS) -> client lobby with no button -> the
    confirm-equip-craft gate -> the client's lobby once the craft is locked
    (EQUIP CRAFT) -> the client's craft screen."""
    hs = lobby(host)
    print("    host lobby button: %r visible=%s"
          % (hs.get("buttonText"), hs.get("buttonVisible")))
    shot(host, "08_host_skirmish_lobby.png")

    cs = lobby(client)
    print("    client lobby button: %r visible=%s (pre-lock)"
          % (cs.get("buttonText"), cs.get("buttonVisible")))
    shot(client, "09_client_skirmish_lobby_prelock.png")

    # BATTLE SETTINGS takes the host back to the NEW BATTLE setup screen; the
    # client stays in the lobby.
    host.ok({"cmd": "lobby_action"})
    host.wait_for("host at BATTLE SETTINGS",
                  lambda: (not session.has_state(host, "LobbyMenu")) or None,
                  timeout=30, interval=0.5)
    wait_state(host, "NewBattleState", timeout=30)

    # The first EQUIP CRAFT click in a hosted custom battle is the one-way
    # craft-lock confirmation, not the equipment screen.
    host.ok({"cmd": "newbattle_equip"})
    wait_dialog(host, CONFIRM_EQUIP_CODE, "confirm-equip-craft gate")
    shot(host, "10_host_confirm_equip_craft.png")
    host.ok({"cmd": "coop_dialog_yes"})

    # The lock is broadcast: only now does the client's lobby offer EQUIP CRAFT.
    client.wait_for(
        "client EQUIP CRAFT offered",
        lambda: (lambda s: s if (s.get("buttonVisible")
                                 and "EQUIP" in (s.get("buttonText") or "").upper())
                 else None)(lobby(client)),
        timeout=90, interval=0.5)
    shot(client, "11_client_skirmish_lobby_postlock.png")

    # The client's button reuses the NewBattleState EQUIP CRAFT handler under
    # its lobby, so CraftInfoState opens ON TOP of the lobby.
    client.ok({"cmd": "lobby_action"})
    wait_state(client, "CraftInfoState", timeout=60)
    shot(client, "12_client_craft_equipment.png")


def group_skirmish():
    host = GameClient("host", PORTS_SKIRMISH[0], make_user_dir("pr87_skirm_host"))
    client = GameClient("client", PORTS_SKIRMISH[1], make_user_dir("pr87_skirm_client"))
    try:
        host.spawn(); client.spawn()
        host.connect(); client.connect()
        skirmish_bring_up(host, client, PORTS_SKIRMISH[2])
        scene("6", "skirmish lobby + EQUIP CRAFT lock", scene_06, host, client)
    finally:
        host.shutdown(); client.shutdown()


# ==== scene 7: the clipboard paste targets =================================

def try_cmds(gc, names):
    """Send each candidate command until one reports ok. Raises Unreachable
    listing what was tried (an unknown cmd answers with an error, no side
    effect), so a missing TestServer hook is a recorded SKIP, not a crash."""
    tried = []
    for name in names:
        r = gc.cmd({"cmd": name})
        if r.get("ok"):
            return name
        tried.append("%s (%s)" % (name, r.get("error")))
    raise Unreachable("no TestServer command opens this menu; tried: "
                      + "; ".join(tried))


def open_server_browser(gc):
    """A fresh instance at the server browser via NEW BATTLE > COOP."""
    if not session.has_state(gc, "ServerList"):
        if not session.has_state(gc, "NewBattleState"):
            gc.ok({"cmd": "open_new_battle"})
            wait_state(gc, "NewBattleState")
        gc.ok({"cmd": "newbattle_coop"})
        wait_state(gc, "ServerList")


def scene_07_hostmenu(gc):
    """HostMenu: the port TextEdit that got setAllowClipboardPaste. On a fresh
    instance (isConnected() == -1) init() shows the server/port/password row."""
    open_server_browser(gc)
    gc.ok({"cmd": "server_list_host"})
    wait_state(gc, "HostMenu")
    st = gc.cmd({"cmd": "host_menu_state"})
    assert st.get("controlsVisible"), \
        "HostMenu opened with its hosting controls hidden: %r" % (st,)
    shot(gc, "13_host_hostmenu.png")
    gc.cmd({"cmd": "host_menu_cancel"})


def scene_07_directconnect(gc):
    """DirectConnect: IP + port TextEdits, both paste-enabled by this PR."""
    open_server_browser(gc)
    try_cmds(gc, DIRECT_CONNECT_CMDS)
    wait_state(gc, "DirectConnect", timeout=30)
    shot(gc, "14_host_directconnect.png")
    gc.cmd({"cmd": "pop_state"})


def scene_07_addserver(gc):
    """AddServerMenu: IP + port TextEdits, both paste-enabled by this PR."""
    open_server_browser(gc)
    try_cmds(gc, ADD_SERVER_CMDS)
    wait_state(gc, "AddServerMenu", timeout=30)
    shot(gc, "15_host_addservermenu.png")
    gc.cmd({"cmd": "pop_state"})


def group_menus():
    gc = GameClient("host", PORT_MENUS, make_user_dir("pr87_menus"))
    try:
        gc.spawn(); gc.connect()
        scene("7a", "HostMenu (port field)", scene_07_hostmenu, gc)
        scene("7b", "DirectConnect (IP + port fields)", scene_07_directconnect, gc)
        scene("7c", "AddServerMenu (IP + port fields)", scene_07_addserver, gc)
    finally:
        gc.shutdown()


# ==== driver ===============================================================

GROUPS = (
    ([("1", "geoscape VoteMenu open on both machines"),
      ("2", "VOTE PASSED"),
      ("3", "VOTE FAILED"),
      ("4", "vote starter cooldown dialog")], group_campaign_votes),
    ([("5", "abandon-mission VoteMenu over a live shared battle")], group_battle_vote),
    ([("6", "skirmish lobby + EQUIP CRAFT lock")], group_skirmish),
    ([("7a", "HostMenu (port field)"),
      ("7b", "DirectConnect (IP + port fields)"),
      ("7c", "AddServerMenu (IP + port fields)")], group_menus),
)


def main(outdir):
    global OUTDIR
    OUTDIR = os.path.abspath(outdir)
    os.makedirs(OUTDIR, exist_ok=True)
    print("PR #87 UI shots -> %s" % OUTDIR)

    # Strictly sequential: the harness lock is machine-wide and the ports are
    # fixed, so each pair must be down before the next one comes up.
    for scene_ids, fn in GROUPS:
        group(scene_ids, fn)

    print("")
    print("==== SUMMARY ====")
    for sid, title, status, note in RESULTS:
        line = "%-4s %-4s %s" % (status, sid, title)
        if note:
            line += "\n         reason: %s" % note
        print(line)
    print("")
    print("%d file(s) written:" % len(SHOTS))
    for p in SHOTS:
        print("  " + p)
    if not SHOTS:
        print("NO SHOTS TAKEN")
        return 1
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(".", "pr87_shots")
    sys.exit(main(out))
