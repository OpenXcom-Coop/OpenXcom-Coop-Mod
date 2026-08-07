"""B3 repro: two PvP campaigns back-to-back in one process (no restart).

Story under test: "duplicate bases leak across campaigns" — after starting a
second PvP campaign in the same process, a stale base from the first campaign
supposedly survives as a duplicate.

The engine does NOT actually leak: campaign 2's `newgame_ok` calls
`Game::setSavedGame(save)`, which `delete`s the previous SavedGame and its whole
base list (real bases + any `_coopIcon` mirror). A base cannot cross campaigns.
This test proves that with a HARD assertion.

Two things this repro previously got wrong (both fixed here):
  1. Teardown: the old `abort_to_main_menu` drove `dismiss_popup`, which is a
     NO-OP on a bare GeoscapeState (there is no CoopState to pop between
     campaigns), so the process never returned to the main menu and the run
     ERRORED instead of testing anything. We now use `disconnect_to_menu` (the
     real teardown: disconnectTCP + resetSession + GoToMainMenuState) on BOTH
     machines and PROVE the process is pristine (MainMenuState up, no world,
     saveID 0) before starting campaign 2.
  2. Classifier: a "real base" is coopBase==false AND coopIcon==false — the
     engine's own predicate (TestServer.cpp). The old filter keyed only on
     coopBase, so it would misclassify a `_coopIcon` mirror (coopBase==false) as
     a real base.

NOTE (out of scope): a genuinely-visible WITHIN-campaign duplicate — a
SEPARATE-mode `_coopIcon` mirror base minted by the coopBase-family handlers
colliding with a real base of the same name — is a SEPARATE, still-open defect.
This cross-campaign test does not exercise or fix it.

Run:  python tools/coop_test/test_pvp_duplicate_bases.py
Exit 0 = pass; 2 = failure (a real duplicate/leak was observed).
"""

import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session

PORT = "48003"

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]
def _has(gc, name): return any(name in s for s in _states(gc))
def _geo(gc): return gc.ok({"cmd": "geo_state"})

def start_campaign_and_place(host, client, alien_player):
    """Run campaign bringup, place the XCOM first base, return both to geoscape."""
    xcom_gc = client if alien_player == 'host' else host

    host.ok({"cmd":"open_new_game","mode":"coop"})
    host.wait_for('x',lambda:_has(host,'NewGameState')); host.ok({"cmd":"newgame_ok"})
    host.wait_for('x',lambda:_has(host,'HostMenu'))
    host.ok({"cmd":"host_tcp","server":"TestSrv","port":PORT,"player":"HostPlayer"})
    host.wait_for('x',lambda:_has(host,'LobbyMenu'))
    client.ok({"cmd":"join_tcp","ip":"127.0.0.1","port":PORT,"player":"ClientPlayer"})
    client.wait_for('x',lambda:_has(client,'LobbyMenu'),timeout=120)
    for g in (host,client):g.wait_for('x',lambda g=g:_has(g,'Profile'));g.ok({"cmd":"profile_ok"})
    host.wait_for('x',lambda:host.cmd({"cmd":"lobby_state"}).get("startEligible"))
    ls=host.cmd({"cmd":"lobby_state"})
    want='ClientPlayer' if alien_player=='client' else 'HostPlayer'
    for i,n in enumerate(ls.get('players',[])):
        if want in n:host.ok({"cmd":"lobby_set_team","row":i,"team":"Alien"});break

    session.start_campaign_via_button(host)
    if _has(xcom_gc,'BuildNewBaseState'):
        xcom_gc.ok({"cmd":"place_first_base","lon":LAND_LON,"lat":LAND_LAT,"name":"XcomBase"})
    time.sleep(1)
    if _has(host,'CoopState'):host.ok({"cmd":"coop_dialog_back"})
    for g in (host,client):
        g.wait_for('x',lambda g=g:_has(g,'GeoscapeState')and not _has(g,'CoopState'),timeout=120)

def disconnect_both_to_menu(host, client):
    """Real teardown between campaigns: the `disconnect_to_menu` harness command
    runs the production abandon-to-main-menu path (disconnectTCP(true) +
    setServerOwner(false) + resetSession() + GoToMainMenuState). Then PROVE the
    process is pristine before campaign 2 is allowed to start: MainMenuState up,
    no live world (hasSave==false), coop identity reset (saveID==0)."""
    for g in (host, client):
        g.ok({"cmd": "disconnect_to_menu"})
    for label, g in (("host", host), ("client", client)):
        g.wait_for(f"{label} main menu",
                   lambda g=g: _has(g, "MainMenuState"), timeout=60)
        g.wait_for(f"{label} world torn down",
                   lambda g=g: (g.cmd({"cmd": "get_coop"}).get("hasSave") is False) or None,
                   timeout=30)
        c = g.cmd({"cmd": "get_coop"})
        assert c.get("hasSave") is False, \
            f"{label}: world NOT torn down between campaigns (hasSave={c.get('hasSave')})"
        assert c.get("saveID") == 0, \
            f"{label}: coop identity NOT reset between campaigns (saveID={c.get('saveID')})"
    print("  teardown proven: both machines at main menu, no world, saveID 0")

def assert_single_xcom_base(gc, fails, tag, camp):
    """Hard assertion: exactly one REAL base (coopBase==false AND coopIcon==false)
    named 'XcomBase' at the placed coordinates, no `_coopIcon` self-mirror named
    'XcomBase', and no other real bases. Reports the observed bases faithfully on
    any failure — never weaken this to hide a genuine duplicate."""
    bases = _geo(gc).get("bases", [])
    for b in bases:
        print(f"    [{tag} c{camp}] base name='{b.get('name','')}' "
              f"coopBase={b.get('coopBase')} coopIcon={b.get('coopIcon')} "
              f"lon={b.get('lon',0):.4f} lat={b.get('lat',0):.4f} "
              f"coopBaseId={b.get('coopBaseId')}")

    real = [b for b in bases if not b.get("coopBase") and not b.get("coopIcon")]
    xcom_real = [b for b in real if b.get("name") == "XcomBase"]
    icon_dupes = [b for b in bases if b.get("coopIcon") and b.get("name") == "XcomBase"]

    ok = True
    if len(real) != 1:
        fails.append(f"{tag} c{camp}: expected 1 real base, got {len(real)} "
                     f"({[b.get('name') for b in real]})")
        ok = False
    if len(xcom_real) != 1:
        fails.append(f"{tag} c{camp}: expected exactly 1 real 'XcomBase', got {len(xcom_real)}")
        ok = False
    else:
        b = xcom_real[0]
        if abs(b.get('lon', 0) - LAND_LON) > 1e-4 or abs(b.get('lat', 0) - LAND_LAT) > 1e-4:
            fails.append(f"{tag} c{camp}: XcomBase at wrong coords "
                         f"lon={b.get('lon')} lat={b.get('lat')}")
            ok = False
    if icon_dupes:
        fails.append(f"{tag} c{camp}: {len(icon_dupes)} _coopIcon mirror(s) named "
                     f"'XcomBase' — self-mirror duplicate")
        ok = False
    if ok:
        print(f"  PASS {tag} c{camp}: exactly 1 real XcomBase, no coopIcon self-mirror")

def test_two_campaigns(fails, alien_player, expect_mode):
    tag = f"gm{expect_mode}_{alien_player}_2x"
    print(f"\n--- B3 two-campaign repro {tag} ---")

    host_dir = make_user_dir(f"pvp_b3x_{tag}_host")
    client_dir = make_user_dir(f"pvp_b3x_{tag}_client")

    host = GameClient("host", 49900, host_dir)
    client = GameClient("client", 49901, client_dir)
    try:
        host.spawn(); host.connect(); client.spawn(); client.connect()

        xcom_gc = client if alien_player == 'host' else host

        # ---- FIRST CAMPAIGN ----
        print(f"  --- campaign 1 ---")
        start_campaign_and_place(host, client, alien_player)
        print(f"  after campaign 1:")
        assert_single_xcom_base(xcom_gc, fails, tag, 1)

        # ---- REAL TEARDOWN BACK TO MAIN MENU (proven pristine) ----
        disconnect_both_to_menu(host, client)
        time.sleep(2)  # let the listening socket on PORT settle before re-hosting

        # ---- SECOND CAMPAIGN (same process) ----
        print(f"  --- campaign 2 ---")
        start_campaign_and_place(host, client, alien_player)
        print(f"  after campaign 2:")
        assert_single_xcom_base(xcom_gc, fails, tag, 2)

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        fails.append(str(e))
    finally:
        host.shutdown(); client.shutdown()

def main():
    fails=[]
    test_two_campaigns(fails, "client", 2)   # gm2: client plays aliens (no_bases)
    test_two_campaigns(fails, "host", 3)     # gm3: host plays aliens (no_bases)
    print("\n==== B3 duplicate bases summary ====")
    if fails:
        for f in fails:print(f"  FAIL {f}")
        sys.exit(2)
    print("  no cross-campaign base leak: each campaign has exactly 1 real XcomBase")
    sys.exit(0)

if __name__=="__main__":
    main()
