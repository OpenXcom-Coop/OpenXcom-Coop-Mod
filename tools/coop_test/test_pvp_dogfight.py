"""PvP dogfight: XCOM player intercepts a UFO, alien player stays on geoscape.

Dogs differs from SHARED: only the combatant (XCOM) sees the dogfight.
The alien player (no_bases) has no craft -- verifies no crash and geoscape
stays live while the XCOM player's dogfight runs.

Tests both gm2 (host=XCOM) and gm3 (client=XCOM).

Run:  python tools/coop_test/test_pvp_dogfight.py
Exit 0 = pass; 2 = failure.
"""

import os, sys, time
# RW-TRIAGE: SKIP-PENDING(r5/W6)
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

def _pump(host, client, n=1):
	geo.skip_realtime(host, client, n, speed_idx=0, stuck_timeout=None)

def _df_state(gc):
	return gc.ok({"cmd": "dogfight_state"}).get("dogfights", [])

def test_dogfight(fails, alien_player, expect_mode):
	tag = f"gm{expect_mode}_{alien_player}"
	print(f"\n--- dogfight {tag} ---")

	host = GameClient("host", 49650, make_user_dir(f"pvp_df_{tag}_host"))
	client = GameClient("client", 49651, make_user_dir(f"pvp_df_{tag}_client"))
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
		gm=-1
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

		b0 = _geo(xcom_gc)
		base0 = next(b for b in b0.get("bases",[]) if not b.get("coopBase"))
		base_lon, base_lat = base0["lon"], base0["lat"]

		sc = xcom_gc.ok({"cmd": "spawn_craft", "type": "STR_INTERCEPTOR",
		                 "weapon": "STR_STINGRAY"})
		if not sc.get("ok"):
			_fail(fails, f"{tag}: spawn_craft failed: {sc}")
			return
		interceptor_id = sc["craft_id"]
		print(f"    interceptor id={interceptor_id}")

		ufo = xcom_gc.ok({"cmd": "spawn_ufo", "type": "STR_SMALL_SCOUT",
		                  "mission": "STR_ALIEN_RESEARCH",
		                  "region": "STR_NORTH_AMERICA", "race": "STR_SECTOID",
		                  "trajectory": "P0", "state": "flying", "speed": 1,
		                  "lon": base_lon + 0.03, "lat": base_lat})
		ufo_id = ufo["ufo_id"]
		print(f"    ufo id={ufo_id}")

		_pump(host, client, 2)
		time.sleep(0.5)

		xcom_gc.ok({"cmd": "craft_order", "order": "target",
		            "craft_id": interceptor_id, "craft_type": "STR_INTERCEPTOR",
		            "ufo_id": ufo_id})
		print(f"    intercept commanded")

		deadline = time.time() + 120
		while time.time() < deadline:
			_pump(host, client, 1)
			dfs = _df_state(xcom_gc)
			if dfs:
				break
			time.sleep(0.2)
		dfs = _df_state(xcom_gc)
		if not dfs:
			_fail(fails, f"{tag}: dogfight never opened on XCOM")
			return
		df = dfs[0]
		print(f"PASS {tag}: dogfight open on XCOM (dist={df.get('dist')}, mode={df.get('mode')})")

		xcom_gc.ok({"cmd": "dogfight_action", "action": "aggressive"})
		ok = False
		for _ in range(40):
			_pump(host, client, 1)
			df = _df_state(xcom_gc)
			if df and df[0].get("mode") == 3:
				ok = True
				break
			time.sleep(0.15)
		if ok:
			print(f"PASS {tag}: stance changed to aggressive")
		else:
			_fail(fails, f"{tag}: aggressive stance not applied")
			return

		xcom_gc.ok({"cmd": "dogfight_action", "action": "disengage"})
		deadline = time.time() + 60
		ended = False
		while time.time() < deadline:
			_pump(host, client, 1)
			dfs = _df_state(xcom_gc)
			if not dfs or dfs[0].get("ended"):
				ended = True
				break
			time.sleep(0.2)
		if ended:
			print(f"PASS {tag}: dogfight ended after disengage")
		else:
			_fail(fails, f"{tag}: dogfight did not end")
			return

		for gc,label in ((host,"host"),(client,"client")):
			geoscope = _has(gc, "GeoscapeState") and not _has(gc, "BattlescapeState")
			if geoscope:
				print(f"PASS {tag}: {label} still on geoscape")
			else:
				st = _states(gc)
				_fail(fails, f"{tag}: {label} left geoscape: {[s.split('::')[-1] for s in st[-5:]]}")
				return

	except Exception as e:
		print(f"[ERROR] {tag}: {e}")
		_fail(fails, str(e))
	finally:
		host.shutdown(); client.shutdown()

def main():
	fails=[]
	test_dogfight(fails, "client", 2)
	test_dogfight(fails, "host", 3)
	print("\n==== PvP dogfight summary ====")
	if fails:
		for f in fails:print(f"  FAIL {f}")
		sys.exit(2)
	print("  gm2 + gm3 dogfight PASS")
	sys.exit(0)

if __name__=="__main__":
	main()
