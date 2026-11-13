"""PvP campaign (host X-COM, client alien): the host's saves complete after the alien player rejoins.

In gamemode 2 the alien player has no world of its own: it never places a base, and the alien
player holds the host's world as a replica. A host save must not wait on the alien machine. Before the
alien player has ever rejoined, a save writes at once. This test checks that it still does after
the alien client crashes and rejoins the running campaign, and after both players reload the
host's save.

Cells:
  fresh       host quick save in the freshly started campaign
  rejoin      alien client crashes and rejoins -> host quick save
  autosave    host autosave after that rejoin
  menu        host OPTIONS -> SAVE GAME -> new save after that rejoin
  reload      both leave, the host reloads the menu save, the client joins -> host quick save

Each save must be written within SAVE_S. A save that is still on the host's "Saving..." dialog
then is a failure. The test presses CANCEL there so the remaining cells still run.

Run:  python tools/coop_test/test_pvp_campaign_save_after_rejoin.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import pvp_fixture
import session

PORT = "49594"
RELOAD_PORT = "49595"
WAIT_PLAYERS = 62  # the host's "waiting for players" dialog
HOST_SAVE_WAIT = 54  # the host's "Saving..." dialog
SAVE_S = 15  # a save that asks nobody writes in well under a second
MENU_SAVE = "pvp_save_after_rejoin"


def top(gc):
    st = session.states(gc)
    return st[-1].replace("class OpenXcom::", "") if st else ""


def to_geoscape(gc, what):
    """Close popups until the geoscape is on top."""
    def step():
        if "GeoscapeState" in top(gc):
            return True
        gc.cmd({"cmd": "dismiss_popup"})
        return None
    gc.wait_for(what, step, timeout=60, interval=0.2)


def log_lines(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), "rb") as f:
            return f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


class Run:
    def __init__(self):
        self.fails = []
        self.host = GameClient("host", None, make_user_dir("pvpsar_host"))
        self.client = GameClient("client", None, make_user_dir("pvpsar_client"))

    def save_path(self, name):
        return os.path.join(self.host.user_dir, "xcom1", name)

    def check_save(self, cell, name, start):
        """Wait for host save `name` (started by `start()`) to be written; report the cell."""
        path = self.save_path(name)
        if os.path.exists(path):
            os.remove(path)
        client_log = len(log_lines(self.client))
        t0 = time.time()
        start()
        written = False
        while time.time() - t0 < SAVE_S:
            if os.path.exists(path):
                written = True
                break
            time.sleep(0.05)
        took = time.time() - t0
        dialog = self.host.cmd({"cmd": "coop_dialog_info"})
        if written:
            print(f"PASS {cell}: host wrote {name} in {took:.1f} s", flush=True)
        else:
            said = [l.split("\t")[-1] for l in log_lines(self.client)[client_log:] if "[coop-save]" in l]
            msg = (f"host save {name} not written after {SAVE_S} s: host top {top(self.host)} dialog code "
                   f"{dialog.get('code')} title {dialog.get('title')!r}; alien client said {said}")
            print(f"  FAIL {cell}: {msg}", flush=True)
            self.fails.append(f"{cell}: {msg}")
            if dialog.get("present") and dialog.get("code") == HOST_SAVE_WAIT:
                self.host.ok({"cmd": "coop_dialog_back"})  # CANCEL writes the save with what the host has
                self.host.wait_for(f"{cell}: {name} written after CANCEL", lambda: os.path.exists(path) or None,
                                   timeout=30, interval=0.1)
        to_geoscape(self.host, f"{cell}: host on the geoscape after saving")
        if "GeoscapeState" not in top(self.client):
            msg = f"alien client left on {session.states_stripped(self.client)} by the host's save"
            print(f"  FAIL {cell}: {msg}", flush=True)
            self.fails.append(f"{cell}: {msg}")
            to_geoscape(self.client, f"{cell}: client on the geoscape")

    def quick_save(self, cell):
        self.check_save(cell, "_quick_.asav", lambda: self.host.ok({"cmd": "save_game_ui", "type": "quick"}))

    def auto_save(self, cell):
        self.check_save(cell, "_autogeo_.asav", lambda: self.host.ok({"cmd": "save_game_ui", "type": "auto_geoscape"}))

    def menu_save(self, cell):
        def start():
            r = session.click_widget_ready(self.host, "options")
            if not r.get("ok"):
                raise RuntimeError(f"{cell}: click OPTIONS -> {r}")
            r = session.click_widget_ready(self.host, "save game")
            if not r.get("ok"):
                raise RuntimeError(f"{cell}: click SAVE GAME -> {r}")
            self.host.wait_for(f"{cell}: save list", lambda: session.has_state(self.host, "ListSaveState") or None,
                               timeout=30, interval=0.1)
            self.host.ok({"cmd": "list_save_confirm", "name": MENU_SAVE})
        self.check_save(cell, MENU_SAVE + ".sav", start)

    def rejoin(self, port):
        """The alien client's process dies; a fresh process rejoins the running campaign; the host presses RESUME."""
        self.client.kill()
        self.host.wait_for("host waiting dialog after the client crash",
                           lambda: (lambda d: (d.get("present") and d.get("code") == WAIT_PLAYERS) or None)(
                               self.host.ok({"cmd": "coop_dialog_info"})),
                           timeout=60, interval=0.2)
        c = GameClient("client", None, make_user_dir("pvpsar_client_rejoin"))
        c.spawn(); c.connect()
        self.client = c
        c.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

        def held():
            # both machines raise a "player joined" popup; close it as a player would
            for gc in (self.host, c):
                if session.has_state(gc, "Profile"):
                    gc.ok({"cmd": "profile_ok"})
            return (session.has_state(c, "CoopState") and not session.has_state(self.host, "Profile")
                    and self.host.ok({"cmd": "get_coop"}).get("resumeAck")) or None
        c.wait_for("rejoined client loaded its world and holds for the host", held, timeout=60, interval=0.2)
        session.press_back_when_shown(self.host, "host RESUME", codes=(60, 62))
        for gc, who in ((self.host, "host"), (c, "client")):
            to_geoscape(gc, f"{who} on the geoscape after the rejoin")

    def reload(self, save_file, port):
        for gc in (self.client, self.host):
            gc.ok({"cmd": "disconnect_to_menu"})
            gc.wait_for(f"{gc.name} main menu", lambda gc=gc: "MainMenuState" in top(gc) or None,
                        timeout=60, interval=0.2)
        session.resume_campaign(self.host, self.client, save_file, port=port)
        for gc, who in ((self.host, "host"), (self.client, "client")):
            to_geoscape(gc, f"{who} on the geoscape after the reload")

    def run(self):
        self.host.spawn(); self.host.connect(); self.client.spawn(); self.client.connect()
        gm = pvp_fixture.start_pvp_campaign(self.host, self.client, PORT, alien_player="client")
        if gm != 2:
            raise RuntimeError(f"expected gamemode 2, got {gm}")
        sides = self.client.ok({"cmd": "coop_sides"})
        if not sides.get("playsAliens"):
            raise RuntimeError(f"the alien client is not on the alien side: {sides}")
        self.quick_save("fresh")
        self.rejoin(PORT)
        self.quick_save("rejoin")
        self.auto_save("autosave")
        self.menu_save("menu")
        self.reload(MENU_SAVE + ".sav", RELOAD_PORT)
        sides = self.client.ok({"cmd": "coop_sides"})
        if sides.get("playsAliens") and sides.get("gamemode") == 2:
            print("PASS reload: the client came back on the alien side", flush=True)
        else:
            msg = (f"the client came back from the save off the alien side: playsAliens {sides.get('playsAliens')} "
                   f"gamemode {sides.get('gamemode')}")
            print(f"  FAIL reload: {msg}", flush=True)
            self.fails.append(f"reload: {msg}")
        self.quick_save("reload")


def main():
    t0 = time.time()
    r = Run()
    try:
        r.run()
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        r.fails.append(str(e))
    finally:
        r.host.shutdown()
        r.client.shutdown()
    print(f"\n==== PvP save after rejoin summary ({time.time() - t0:.1f}s) ====")
    if r.fails:
        for f in r.fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  every host save was written without waiting on the alien player")
    sys.exit(0)


if __name__ == "__main__":
    main()
