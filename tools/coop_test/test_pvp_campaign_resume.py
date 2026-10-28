"""PvP campaign resume (D250-U S-D on rewrite/merge-main; docs rewrite/prompts/d250u_sd_merge_main.md):
  - gm2 mid-battle: the release line's gm2 battle save (fixtures/pvp_gm2_battle.sav, made by `main`)
    converts at the host's menu load (D246-U S-C1) and resumes through the real host window
    (host_menu_host, R-D250-SC4A-1; L-SC5-6): verify BOTH in battle (also proves the battle-free
    buildCoopStub loads clean as the phase-one geoscape without null-derefing on an empty roster).
  - gm3 mid-battle: the release line's gm3 battle save holds no alien world, so the host's menu load
    refuses it with the repair line (owner D284 (c) amended, VL-D284-1; L-SC5-6): D246-U S-C2's row G3
    check (test_old_pvp_gm3_refused), host only.
  - geoscape [P4]: bring up a gm2 campaign, save it (embeds buildCoopStub as the
    alien client's blob), resume with fresh processes, and assert the client
    lands in the minimal unplaced/unnamed EMPTY stub - no host base name, no
    placed base, no roster - while the host's own base+roster come back intact.

Run:  python tools/coop_test/test_pvp_campaign_resume.py
Exit 0 = pass; 2 = failure.
"""

import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import pvp_fixture
import test_old_pvp_gm3_refused as SC2  # the gm3 leg's refusal check (D246-U S-C2 row G3; D284 (c))

PORT = "49229"  # D250-U S-D lobby key (was 48003, shared with three other PvP files)
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]
def _has(gc, name): return any(name in s for s in _states(gc))
def _fail(fails, msg): print(f"  FAIL {msg}"); fails.append(msg)

def resume_campaign_battle(host, client, save_file, port, host_name="HostPlayer", client_name="ClientPlayer", timeout=120,
                           interval=2.0):
    """session.resume_campaign_battle copied (D250-U S-D; R-D250-SC4A-1 (a), L-SC5-6) with ONE change: the host's START HOST
    goes through the real host window (host_menu_host visibility 0 -> HostMenu::hostTCPGame), not the host_tcp lever, so the
    resume passes the host window's PvP-mode keep (D250-U S-C4a, W2-H46). The same copy as test_campaign_resume_gm2.py."""
    host.ok({"cmd": "load_save_menu", "file": save_file})
    host.wait_for("host window (battle resume)", lambda: session.has_state(host, "HostMenu"))
    host.ok({"cmd": "host_menu_host", "visibility": 0, "server": "TestSrv", "port": port, "player": host_name})
    host.wait_for("resume lobby", lambda: session.has_state(host, "LobbyMenu"))
    ls = host.ok({"cmd": "lobby_state"})
    assert ls["lobbyMode"] == 2, f"expected resume lobby, got {ls}"
    client.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": client_name})
    client.wait_for("client resume lobby", lambda: session.has_state(client, "LobbyMenu"))
    session.resume_campaign_via_button(host, client_name)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if host.cmd({"cmd": "battle_state"}).get("inBattle") and client.cmd({"cmd": "battle_state"}).get("inBattle"):
            print("battle resume: BOTH machines report inBattle")
            return
        time.sleep(interval)
    raise TimeoutError(f"battle resume: both machines did not enter the battle within {timeout}s: host {session.states(host)[-3:]} / "
                       f"client {session.states(client)[-3:]}")

def test_resume(fails, save_file, tag):
    print(f"\n--- resume {tag} ---")
    host_dir = make_user_dir(f"pvp_res_v2_{tag}_host")
    client_dir = make_user_dir(f"pvp_res_v2_{tag}_client")
    src = os.path.join(FIXTURES, save_file)
    dst_dir = os.path.join(host_dir, "xcom1")
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, os.path.join(dst_dir, save_file))

    host = GameClient("host", 49580, host_dir)
    client = GameClient("client", 49581, client_dir)
    try:
        host.spawn(); host.connect(); client.spawn(); client.connect()
        resume_campaign_battle(host, client, save_file, port=PORT,
                               host_name="HostPlayer", client_name="ClientPlayer",
                               timeout=240)
        for gc, label in ((host, "host"), (client, "client")):
            bs = gc.ok({"cmd": "battle_state"})
            st = _states(gc)
            if not bs.get("inBattle"):
                _fail(fails, f"{tag}: {label} not in battle (top={st[-3:]})")
                return
            print(f"PASS {tag}: {label} inBattle, top={st[-1].split('::')[-1]}")
    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown(); client.shutdown()

def test_gm3_refused(fails):
    """gm3 mid-battle leg (owner D284 (c) amended; L-SC5-6; QSC2-2 (a)): the release line's gm3 battle save carries no world of
    the alien player, so the host's menu load refuses it and ONLY that refusal names where to ask for a repair (VL-D284-1). One
    host, no client (the refusal comes before any session). The check is D246-U S-C2's row G3: SC2.load (ErrorMessageState the
    top, no HostMenu / LobbyMenu / BattlescapeState, 1 refusal line, 0 convert lines), SC2.text_bad (the box and the log field
    == SC2.TEXT_GM3), SC2.press_ok (the real OK -> MainMenuState)."""
    tag = "gm3"
    print(f"\n--- resume {tag}: the release-made gm3 battle save is refused at the menu load (D284 (c)) ---")
    host_dir = make_user_dir(f"pvp_res_v2_{tag}_host")
    dst_dir = os.path.join(host_dir, "xcom1")
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(os.path.join(FIXTURES, "pvp_gm3_battle.sav"), os.path.join(dst_dir, "pvp_gm3_battle.sav"))
    host = GameClient("host", None, host_dir)
    try:
        host.spawn(); host.connect()
        ev = {}
        b, bad = SC2.load(host, "G3", ev)
        bad += SC2.text_bad(b, ev["log"], SC2.TEXT_GM3)
        if b is not None:
            bad += SC2.press_ok(host, ev)
        if bad:
            _fail(fails, f"{tag}: " + "; ".join(bad))
        else:
            print(f"PASS {tag}: refused at the menu load with the repair line (box after {ev['boxS']} s; 1 refusal line, "
                  f"0 convert lines); OK -> MainMenuState after {ev['ok']['s']} s")
    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, f"{tag}: {e}")
    finally:
        host.shutdown()

REJOIN_PORT = "49230"  # D250-U S-D lobby key (was 48009)

def _geo(gc):
    return gc.ok({"cmd": "geo_state"})

def _real_bases(geo):
    """The client's/host's OWN bases - excluding coop mirror icons, which are
    display-only globe markers (coopIcon) and legitimately carry the peer's
    name/placement. A world-level leak is a REAL base (not a mirror) that
    belongs to the other player."""
    return [b for b in geo.get("bases", [])
            if not b.get("coopBase") and not b.get("coopIcon")]

def _assert_empty_stub(cbases, host_names, fails, tag):
    """cbases = the CLIENT's REAL bases after a geoscape resume. buildCoopStub
    hands the alien client exactly ONE unplaced, unnamed, EMPTY base - never the
    host's placed, named bases + roster (the full-world synthesis this P4
    replaces leaked those). Assert: at least one base (never zero - a 0-base
    world crashes on unguarded getBases()->front()); every real base is at
    lon/lat 0, unnamed, and carries no soldiers; and no host base name is
    present."""
    if len(cbases) < 1:
        _fail(fails, f"{tag}: client has ZERO real bases (stub must carry one unplaced base)")
        return
    for b in cbases:
        nm = b.get("name") or ""
        if nm:
            _fail(fails, f"{tag}: client base carries a name {nm!r} (stub base must be unnamed)")
        if nm and nm in host_names:
            _fail(fails, f"{tag}: client carries HOST base {nm!r} (base-identity leak!)")
        if abs(b.get("lon", 0.0)) > 1e-9 or abs(b.get("lat", 0.0)) > 1e-9:
            _fail(fails, f"{tag}: client base is PLACED at ({b.get('lon')},{b.get('lat')}) "
                         f"(stub base must be unplaced)")
    total = sum(b.get("soldiers", 0) for b in cbases)
    if total != 0:
        _fail(fails, f"{tag}: client stub carries {total} soldiers (host roster leak!)")

def _base_summary(geo):
    return [(b.get("name"), round(b.get("lon", 0.0), 4), round(b.get("lat", 0.0), 4),
             b.get("soldiers"), b.get("coopBase"), b.get("coopIcon"))
            for b in geo.get("bases", [])]

def test_rejoin_no_leak(fails):
    """gm2 GEOSCAPE resume leg: the alien client rejoins into the minimal
    buildCoopStub world, never the host's full world.

    Why geoscape and not mid-battle: a mid-battle resume streams the host's live
    world+battle in phase two (SEND_FILE_CLIENT_SAVE) ON TOP of the stub, so the
    client legitimately ends holding the host's world there - the stub is only
    its transient phase-one geoscape. It is a pure geoscape resume where the stub
    IS the client's final world, so that is where the no-leak guarantee is
    asserted.

    Flow: bring up a gm2 campaign to the geoscape (host=XCOM with a placed,
    named base + roster; client=alien). The host saves - SavedGame::save embeds
    buildCoopStub as the client blob. Fresh processes resume that save; the host
    streams the embedded stub to the client. Assert the client's geoscape is the
    empty unplaced/unnamed stub (no host base name, no placed base, no soldiers),
    and the host's own base+roster came back intact."""
    tag = "gm2-geo"
    print(f"\n--- {tag}: geoscape resume streams the minimal stub, no host base/roster ---")

    # ---- 1) bring up a gm2 geoscape campaign live, then save it ----
    h1 = GameClient("host1", 49590, make_user_dir("pvp_geo_h1"))
    c1 = GameClient("client1", 49591, make_user_dir("pvp_geo_c1"))
    save_name = "pvp_gm2_geo_stub.sav"
    saved_path = None
    host_names = set(); host_soldiers = 0
    h1_dir = h1.user_dir
    try:
        h1.spawn(); h1.connect(); c1.spawn(); c1.connect()
        gm = pvp_fixture.start_pvp_campaign(h1, c1, REJOIN_PORT, alien_player="client")
        if gm != 2:
            _fail(fails, f"{tag}: expected gamemode 2 (host=XCOM/client=alien), got {gm}")
            return
        hgeo = _geo(h1)
        host_real = _real_bases(hgeo)
        host_names = {b.get("name") for b in host_real if b.get("name")}
        host_soldiers = sum(b.get("soldiers", 0) for b in host_real)
        print(f"  host real bases={sorted(host_names)} soldiers={host_soldiers}")
        if not host_names or host_soldiers < 1:
            _fail(fails, f"{tag}: premise broken - host has no named base/roster to protect "
                         f"(names={host_names} soldiers={host_soldiers})")
            return
        # SavedGame::save runs the embed loop -> buildCoopStub for the gm2 client.
        h1.ok({"cmd": "save_game", "file": save_name})
        time.sleep(1)
        rels = [f for f in session.save_files(h1_dir) if os.path.basename(f) == save_name]
        if not rels:
            _fail(fails, f"{tag}: save_game wrote no {save_name} (found {session.save_files(h1_dir)})")
            return
        saved_path = os.path.join(h1_dir, rels[0])
    except Exception as e:
        print(f"[ERROR] {tag} bringup: {e}")
        _fail(fails, f"{tag}: bringup {e}")
    finally:
        h1.shutdown(); c1.shutdown()
    if saved_path is None or any(f.startswith(tag) for f in fails):
        return

    # ---- 2) resume that geoscape save with fresh processes ----
    h2 = GameClient("host2", 49592, make_user_dir("pvp_geo_h2"))
    c2 = GameClient("client2", 49593, make_user_dir("pvp_geo_c2"))
    dst_dir = os.path.join(h2.user_dir, "xcom1")
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(saved_path, os.path.join(dst_dir, save_name))
    try:
        h2.spawn(); h2.connect(); c2.spawn(); c2.connect()
        session.resume_campaign(h2, c2, save_name, port=REJOIN_PORT,
                                host_name="HostPlayer", client_name="ClientPlayer")

        # the client resumed into buildCoopStub, NOT the host's world
        c2geo = _geo(c2)
        print(f"  client geoscape bases={_base_summary(c2geo)}")
        _assert_empty_stub(_real_bases(c2geo), host_names, fails, f"{tag} client")

        # the host's own placed base + roster came back intact
        h2geo = _geo(h2)
        h2_real = _real_bases(h2geo)
        h2_names = {b.get("name") for b in h2_real if b.get("name")}
        h2_soldiers = sum(b.get("soldiers", 0) for b in h2_real)
        print(f"  host after resume bases={sorted(h2_names)} soldiers={h2_soldiers}")
        if h2_names != host_names:
            _fail(fails, f"{tag}: host base names changed across resume: "
                         f"{sorted(host_names)} -> {sorted(h2_names)}")
        if h2_soldiers != host_soldiers:
            _fail(fails, f"{tag}: host roster changed across resume: "
                         f"{host_soldiers} -> {h2_soldiers}")
        if not any(f.startswith(tag) for f in fails):
            print(f"PASS {tag}: alien client resumed into the empty unplaced/unnamed stub "
                  f"(no host base {sorted(host_names)}, 0 soldiers); host world intact "
                  f"({host_soldiers} soldiers)")
    except Exception as e:
        print(f"[ERROR] {tag} resume: {e}")
        _fail(fails, f"{tag}: resume {e}")
    finally:
        h2.shutdown(); c2.shutdown()

def main():
    fails=[]
    test_resume(fails, "pvp_gm2_battle.sav", "gm2")
    test_gm3_refused(fails)
    test_rejoin_no_leak(fails)
    print("\n==== PvP campaign resume summary ====")
    if fails:
        for f in fails:print(f"  FAIL {f}")
        sys.exit(2)
    print("  gm2 mid-battle resume PASS; gm3 release save refused with the repair line PASS; "
          "gm2 client-rejoin stub (no host placed/named base leak) PASS")
    sys.exit(0)

if __name__=="__main__":
    main()
