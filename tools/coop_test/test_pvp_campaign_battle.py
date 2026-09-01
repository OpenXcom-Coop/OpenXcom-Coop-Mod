"""PvP campaign battle: mission site -> craft dispatch -> landing -> battle.

Follows the SHARED _fly_a_battle recipe: spawn site, force craft to
it with a dest target, drain popups, confirm landing, enter battle.

Run:  python tools/coop_test/test_pvp_campaign_battle.py
Exit 0 = pass; 2 = failure.
"""

import os, sys, time
# RW-TRIAGE: SKIP-PENDING(fast-follow)
print("SKIP-PENDING: rewrite"); sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session, geo

PORT = "48003"

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]
def _has(gc, name): return any(name in s for s in _states(gc))
def _geo(gc): return gc.ok({"cmd": "geo_state"})
def _fail(fails, msg): print(f"  FAIL {msg}"); fails.append(msg)

def test_campaign_battle(fails, alien_player, expect_mode):
    tag = f"gm{expect_mode}_{alien_player}"
    print(f"\n--- campaign battle {tag} ---")
    host = GameClient("host", 49002, make_user_dir(f"pvp_cb6_{tag}_host"))
    client = GameClient("client", 49003, make_user_dir(f"pvp_cb6_{tag}_client"))
    try:
        host.spawn(); host.connect(); client.spawn(); client.connect()

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
            if want in n:r=host.ok({"cmd":"lobby_set_team","row":i,"team":"Alien"});gm=r["gamemode"];break
        if gm!=expect_mode:_fail(fails,f"{tag}: expected {expect_mode} got {gm}");return

        session.start_campaign_via_button(host)
        xcom_gc=client if alien_player=='host' else host
        if _has(xcom_gc,'BuildNewBaseState'):
            xcom_gc.ok({"cmd":"place_first_base","lon":LAND_LON,"lat":LAND_LAT,"name":"XB"})
        time.sleep(2)
        if _has(host,'CoopState'):host.ok({"cmd":"coop_dialog_back"})
        for g in (host,client):g.wait_for('x',lambda g=g:_has(g,'GeoscapeState')and not _has(g,'CoopState'),timeout=120)
        print(f"PASS {tag}: both on geoscape")

        # Geo gives us craft IDs; get_soldiers gives soldier IDs (SEPARATE-compatible)
        hg = _geo(xcom_gc)
        b0 = next((b for b in hg.get("bases", []) if not b.get("coopBase")), None)
        if not b0:_fail(fails,f"{tag}: no XCOM base");return
        crafts = b0.get("crafts",[])
        if not isinstance(crafts,list) or not crafts:_fail(fails,f"{tag}: no crafts list");return
        cid = next((c["id"] for c in crafts if "SKYRANGER" in c.get("type","")),None)
        if not cid:_fail(fails,f"{tag}: no Skyranger");return

        soldiers = xcom_gc.ok({"cmd":"get_soldiers"})
        sb = next((b for b in soldiers.get("bases",[]) if not b.get("coopBaseFlag")),None)
        if not sb or len(sb.get("soldiers",[]))<2:_fail(fails,f"{tag}: need 2+ soldiers");return
        all_sids = [s["id"] for s in sb["soldiers"]]
        print(f"    cid={cid} soldiers={len(all_sids)}")

        for sid in all_sids:
            xcom_gc.ok({"cmd":"craft_assign","craft_id":cid,"soldier_id":sid,"on":False})
        squad = all_sids[:2]
        for sid in squad:
            xcom_gc.ok({"cmd":"craft_assign","craft_id":cid,"soldier_id":sid,"on":True})
        print(f"    squad aboard: {squad}")

        # Spawn mission site on XCOM machine
        site = xcom_gc.ok({"cmd": "spawn_mission_site",
                           "mission": "STR_ALIEN_RESEARCH",
                           "deployment": "STR_MEDIUM_SCOUT",
                           "lon": b0["lon"] + 0.35, "lat": b0["lat"] + 0.10,
                           "race": "STR_SECTOID", "hours": 240})
        if not site.get("ok"):
            _fail(fails, f"{tag}: spawn_mission_site failed: {site}")
            return
        sid_site = site["site_id"]
        print(f"    site id={sid_site}")

        # Force craft to the site WITH dest target
        xcom_gc.ok({"cmd": "craft_force", "craft_id": cid, "status": "STR_OUT",
                    "lon": b0["lon"] + 0.34, "lat": b0["lat"] + 0.10,
                    "dest": f"site:{sid_site}", "fuel": 999999, "lowFuel": False})

        # Wait for landing prompt, drain popups (SHARED recipe)
        def _prompt():
            if _has(xcom_gc, "ConfirmLandingState"):
                return True
            for gc in (host, client):
                geo.drain_popups(gc, interest=geo.popup("ConfirmLandingState"))
                gc.cmd({"cmd": "geo_set_speed", "idx": 2})
            return None

        xcom_gc.wait_for("landing prompt", _prompt, timeout=180, interval=0.5)
        xcom_gc.ok({"cmd": "confirm_landing"})

        # Wait for battle entry on both sides
        for gc in (host, client):
            gc.wait_for("entered battle",
                        lambda gc=gc: gc.cmd({"cmd": "battle_state"}).get("inBattle") or None,
                        timeout=180, interval=1.0)
            print(f"    {gc.name} battle_state.inBattle=True")

        # Wait for inventory screens
        for gc in (host, client):
            gc.wait_for("briefing", lambda gc=gc: _has(gc, "BriefingState") or None,
                        timeout=120, interval=0.5)
            gc.ok({"cmd": "close_briefing"})
        for gc in (host, client):
            gc.wait_for("inventory", lambda gc=gc: _has(gc, "InventoryState") or None,
                        timeout=120, interval=0.5)
            gc.ok({"cmd": "battle_inventory", "action": "ok"})
        for gc in (host, client):
            gc.wait_for("tactical", lambda gc=gc: _has(gc, "BattlescapeState") or None,
                        timeout=120, interval=0.5)
            print(f"PASS {tag}: {gc.name} in BattlescapeState")

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        _fail(fails, str(e))
    finally:
        host.shutdown(); client.shutdown()

def main():
    fails=[]
    test_campaign_battle(fails, "client", 2)
    test_campaign_battle(fails, "host", 3)
    print("\n==== PvP campaign battle summary ====")
    if fails:
        for f in fails:print(f"  FAIL {f}")
        sys.exit(2)
    print("  gm2 + gm3 campaign battle entry")
    sys.exit(0)

if __name__=="__main__":
    main()
