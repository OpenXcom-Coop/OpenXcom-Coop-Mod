"""B3 repro: two campaigns back-to-back without restart.

Starts a PvP campaign, aborts it, then starts a second one in the same
process. Checks base count after each campaign start to see if stale
data leaks from the first campaign.

Run:  python tools/coop_test/test_pvp_duplicate_bases.py
Exit 0 = pass; 2 = failure (repro confirmed).
"""

import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import session, geo

PORT = "48003"

def _states(gc):
	return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]
def _has(gc, name): return any(name in s for s in _states(gc))
def _geo(gc): return gc.ok({"cmd": "geo_state"})

def _dump_bases(gc, label):
	g = _geo(gc)
	bases = g.get("bases", [])
	for b in bases:
		print(f"    {label} base: name='{b.get('name','')}' coop={b.get('coopBase')} "
		      f"lon={b['lon']:.3f} lat={b['lat']:.3f}")
	return bases

def start_campaign_and_place(host, client, alien_player):
	"""Run campaign bringup, place XCOM base, return both to geoscape."""
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

def abort_to_main_menu(host, client):
	"""Directly push GoToMainMenuState to reset the world."""
	for g in (host, client):
		g.cmd({"cmd": "dismiss_popup"})
		time.sleep(1)
	for g in (host, client):
		g.cmd({"cmd": "dismiss_popup"})  # drain any CoopStates
		time.sleep(0.5)
	for g in (host, client):
		g.wait_for("mainmenu", lambda g=g: _has(g, "MainMenuState"), timeout=30)

def test_two_campaigns(fails, alien_player, expect_mode):
	tag = f"gm{expect_mode}_{alien_player}_2x"
	print(f"\n--- B3 two-campaign repro {tag} ---")

	host_dir = make_user_dir(f"pvp_b3x_{tag}_host")
	client_dir = make_user_dir(f"pvp_b3x_{tag}_client")

	host = GameClient("host", 49900, host_dir)
	client = GameClient("client", 49901, client_dir)
	try:
		host.spawn(); host.connect(); client.spawn(); client.connect()

		# ---- FIRST CAMPAIGN ----
		print(f"  --- campaign 1 ---")
		start_campaign_and_place(host, client, alien_player)

		xcom_gc = client if alien_player == 'host' else host
		print(f"  after campaign 1:")
		b1 = _dump_bases(xcom_gc, "XCOM")
		real1 = [b for b in b1 if not b.get("coopBase")]
		if len(real1) != 1:
			fails.append(f"{tag}: campaign 1 XCOM has {len(real1)} real bases")

		# ---- ABORT + RETURN TO MAIN MENU ----
		abort_to_main_menu(host, client)
		time.sleep(2)
		print(f"  in main menu: {_has(host,'MainMenuState')} {_has(client,'MainMenuState')}")

		# ---- SECOND CAMPAIGN ----
		print(f"  --- campaign 2 ---")
		start_campaign_and_place(host, client, alien_player)

		print(f"  after campaign 2:")
		b2 = _dump_bases(xcom_gc, "XCOM")
		real2 = [b for b in b2 if not b.get("coopBase")]
		if len(real2) != 1:
			fails.append(f"{tag}: campaign 2 XCOM has {len(real2)} real bases")
		else:
			print(f"PASS {tag}: no duplicate bases from prior campaign")

	except Exception as e:
		print(f"[ERROR] {tag}: {e}")
		fails.append(str(e))
	finally:
		host.shutdown(); client.shutdown()

def main():
	fails=[]
	test_two_campaigns(fails, "client", 2)
	test_two_campaigns(fails, "host", 3)
	print("\n==== B3 duplicate bases summary ====")
	if fails:
		for f in fails:print(f"  FAIL {f}")
		sys.exit(2)
	print("  B3 NOT reproduced (no stale-base leak)")
	sys.exit(0)

if __name__=="__main__":
	main()
