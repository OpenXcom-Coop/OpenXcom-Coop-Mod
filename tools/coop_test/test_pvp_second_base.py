"""PvP campaign: the X-COM player's later bases survive a drop, the month end and the host's save.

In a PvP campaign the X-COM player builds more bases after the first. A base built
on the client (host = alien, gamemode 3) lives in the client's own world; the host
keeps a copy of that world, serves it to the client when the client rejoins after a
drop, and embeds it in the host's save. A second base must be in that copy, or a
rejoin or a SAVE & QUIT after a drop brings the X-COM world back without it.

Each leg checks both machines after every step: the X-COM machine lists the bases
as its own, the alien machine shows each one once as the partner's base.

gm3 (host alien, client X-COM):
  build SecondBase -> client crashes and rejoins -> month end ->
  build ThirdBase -> client crashes, host SAVE & QUIT -> both reload that save
gm2 (host X-COM, client alien):
  build SecondBase -> month end -> host saves -> both leave and reload that save ->
  client crashes and rejoins

Run:  python tools/coop_test/test_pvp_second_base.py
Exit 0 = pass; 2 = failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir, LAND_LON, LAND_LAT
import geo
import pvp_fixture
import session

WAIT_PLAYERS = 62  # the host's "waiting for players" dialog
SECOND = ("SecondBase", LAND_LON + 0.05, LAND_LAT + 0.05)
THIRD = ("ThirdBase", LAND_LON - 0.05, LAND_LAT + 0.05)


def top(gc):
    st = session.states(gc)
    return st[-1].replace("class OpenXcom::", "") if st else ""


def to_geoscape(gc, what):
    """Leave a base view or close popups until the geoscape is on top."""
    def step():
        t = top(gc)
        if "GeoscapeState" in t:
            return True
        if "BasescapeState" in t:
            gc.cmd({"cmd": "leave_base"})
        else:
            gc.cmd({"cmd": "dismiss_popup"})
        return None
    gc.wait_for(what, step, timeout=60, interval=0.2)


def base_names(gc):
    """(own, partner) base names on this machine: real bases and the partner's bases shown on the globe."""
    own, partner = [], []
    for b in gc.ok({"cmd": "geo_state"}).get("bases", []):
        if b.get("coopIcon"):
            partner.append(b.get("name"))
        elif not b.get("coopBase"):
            own.append(b.get("name"))
    return own, partner


class Leg:
    def __init__(self, tag, fails, host, client, xcom_is_host):
        self.tag, self.fails = tag, fails
        self.host, self.client = host, client
        self.xcom_is_host = xcom_is_host
        self.expected = ["XcomBase"]

    @property
    def xcom(self):
        return self.host if self.xcom_is_host else self.client

    @property
    def alien(self):
        return self.client if self.xcom_is_host else self.host

    def check(self, step):
        """The X-COM machine owns every expected base once; the alien machine shows each once as the partner's."""
        own, _ = base_names(self.xcom)
        _, shown = base_names(self.alien)
        bad = []
        for name in self.expected:
            if own.count(name) != 1:
                bad.append(f"X-COM machine owns {own.count(name)} x {name!r} (own bases {own})")
            if shown.count(name) != 1:
                bad.append(f"alien machine shows {shown.count(name)} x {name!r} (partner bases {shown})")
        if bad:
            for b in bad:
                print(f"  FAIL {self.tag} {step}: {b}", flush=True)
                self.fails.append(f"{self.tag} {step}: {b}")
        else:
            print(f"PASS {self.tag} {step}: X-COM owns {own}, alien shows {shown}", flush=True)

    def wait_shown(self, step):
        """The partner's globe learns a new base from the builder's marker: wait for it before checking."""
        try:
            self.alien.wait_for(f"{self.tag} {step}: alien machine shows the new base",
                                lambda: all(n in base_names(self.alien)[1] for n in self.expected) or None,
                                timeout=10, interval=0.1)
        except TimeoutError:
            pass  # check() reports what is missing
        self.check(step)

    def host_copy(self):
        """Hash of the host's copy of the client's world."""
        return self.host.ok({"cmd": "coop_file_info", "role": "host_copy_of_client"}).get("fnv1a64")

    def build(self, base):
        name, lon, lat = base
        copy_before = None if self.xcom_is_host else self.host_copy()
        self.xcom.ok({"cmd": "set_funds", "value": 50000000})
        r = self.xcom.cmd({"cmd": "build_new_base", "lon": lon, "lat": lat, "name": name})
        if not r.get("ok"):
            raise RuntimeError(f"{self.tag}: build_new_base {name} -> {r}")
        to_geoscape(self.xcom, f"{self.tag}: X-COM machine back on the geoscape after building {name}")
        self.expected.append(name)
        self.wait_shown(f"after building {name}")
        if copy_before is not None:
            # The client crashes next. A world still on the wire when the client dies is lost under any rules, so give
            # one that was sent time to land; a copy that never changes is what the checks after the crash report.
            try:
                self.host.wait_for(f"{self.tag}: host copy of the client world after building {name}",
                                   lambda: self.host_copy() != copy_before or None, timeout=10, interval=0.05)
                print(f"    {self.tag}: the host's copy of the client world changed after building {name}", flush=True)
            except TimeoutError:
                print(f"    {self.tag}: the host's copy of the client world did not change after building {name}",
                      flush=True)

    def crash_client(self):
        """The client process dies (a crash or a lost connection); the host raises its waiting dialog."""
        self.client.kill()
        self.host.wait_for(f"{self.tag}: host waiting dialog after the client crash",
                           lambda: (lambda d: (d.get("present") and d.get("code") == WAIT_PLAYERS) or None)(
                               self.host.ok({"cmd": "coop_dialog_info"})),
                           timeout=60, interval=0.2)

    def new_client(self, label):
        c = GameClient("client", None, make_user_dir(f"pvp2b_{self.tag}_{label}"))
        c.spawn(); c.connect()
        self.client = c
        return c

    def rejoin(self, port):
        """A fresh client process rejoins the running campaign; the host presses RESUME."""
        self.crash_client()
        c = self.new_client("rejoin")
        c.ok({"cmd": "join_tcp", "ip": "127.0.0.1", "port": port, "player": "ClientPlayer"})

        def held():
            # both machines raise a "player joined" popup; close it as a player would
            for gc in (self.host, c):
                if session.has_state(gc, "Profile"):
                    gc.ok({"cmd": "profile_ok"})
            return (session.has_state(c, "CoopState") and not session.has_state(self.host, "Profile")
                    and self.host.ok({"cmd": "get_coop"}).get("resumeAck")) or None
        c.wait_for(f"{self.tag}: rejoined client loaded its world and holds for the host", held, timeout=60, interval=0.2)
        session.press_back_when_shown(self.host, f"{self.tag} host RESUME", codes=(60, 62))
        for gc, who in ((self.host, "host"), (c, "client")):
            to_geoscape(gc, f"{self.tag}: {who} on the geoscape after the rejoin")
        self.wait_shown("after the client rejoined")

    def month_end(self):
        h, c = self.host, self.client
        geo.slow_clock(h, c)
        mp0 = h.ok({"cmd": "geo_state"}).get("monthsPassed")
        h.ok({"cmd": "set_geo_day", "day": 28, "hour": 12})
        deadline = time.time() + 60
        while h.ok({"cmd": "geo_state"}).get("monthsPassed") == mp0:
            if time.time() > deadline:
                raise RuntimeError(f"{self.tag}: the month did not roll")
            geo.skip_ingame_time(h, c, minutes=60 * 24, speed_idx=5, real_timeout=30)
        for gc, who in ((h, "host"), (c, "client")):
            to_geoscape(gc, f"{self.tag}: {who} closed the month-end report")
        self.check("after the month-end report")

    def leave_both(self):
        for gc in (self.client, self.host):
            gc.ok({"cmd": "disconnect_to_menu"})
            gc.wait_for(f"{self.tag}: {gc.name} main menu", lambda gc=gc: "MainMenuState" in top(gc) or None,
                        timeout=60, interval=0.2)

    def reload(self, save_file, port):
        session.resume_campaign(self.host, self.client, save_file, port=port)
        for gc, who in ((self.host, "host"), (self.client, "client")):
            to_geoscape(gc, f"{self.tag}: {who} on the geoscape after the reload")
        self.wait_shown("after both reloaded the host's save")

    def host_quick_save(self):
        """The host saves through the real save path (it asks the client for its world first)."""
        path = os.path.join(self.host.user_dir, "xcom1", "_quick_.asav")
        self.host.ok({"cmd": "save_game_ui", "type": "quick"})
        self.host.wait_for(f"{self.tag}: host save written", lambda: os.path.exists(path) or None,
                           timeout=60, interval=0.2)
        to_geoscape(self.host, f"{self.tag}: host on the geoscape after saving")
        return "_quick_.asav"

    def host_save_and_quit_after_crash(self, name):
        """The client crashes; the host takes SAVE & QUIT on its waiting dialog (nothing to ask the client for)."""
        self.crash_client()
        self.host.ok({"cmd": "coop_dialog_save_quit"})
        self.host.wait_for(f"{self.tag}: save list", lambda: session.has_state(self.host, "ListSaveState") or None,
                           timeout=30, interval=0.2)
        self.host.ok({"cmd": "list_save_confirm", "name": name})
        self.host.wait_for(f"{self.tag}: host main menu after SAVE & QUIT",
                           lambda: "MainMenuState" in top(self.host) or None, timeout=60, interval=0.2)
        self.new_client("reload")
        return name + ".sav"


def run_leg(fails, alien_player, expect_gm):
    tag = f"gm{expect_gm}"
    print(f"\n--- {tag}: alien = {alien_player} ---", flush=True)
    port = {"gm3": "49531", "gm2": "49533"}[tag]
    reload_port = {"gm3": "49532", "gm2": "49534"}[tag]
    host = GameClient("host", None, make_user_dir(f"pvp2b_{tag}_host"))
    client = GameClient("client", None, make_user_dir(f"pvp2b_{tag}_client"))
    leg = Leg(tag, fails, host, client, xcom_is_host=(alien_player == "client"))
    try:
        host.spawn(); host.connect(); client.spawn(); client.connect()
        gm = pvp_fixture.start_pvp_campaign(host, client, port, alien_player=alien_player)
        if gm != expect_gm:
            raise RuntimeError(f"{tag}: expected gamemode {expect_gm}, got {gm}")
        leg.check("after the campaign start")
        leg.build(SECOND)
        if leg.xcom_is_host:
            leg.month_end()
            save_file = leg.host_quick_save()
            leg.leave_both()
            leg.reload(save_file, reload_port)
            leg.rejoin(reload_port)
        else:
            leg.rejoin(port)
            leg.month_end()
            leg.build(THIRD)
            save_file = leg.host_save_and_quit_after_crash("pvp_second_base")
            leg.reload(save_file, reload_port)
    except Exception as e:
        print(f"[ERROR] {tag}: {e}", flush=True)
        fails.append(f"{tag}: {e}")
    finally:
        leg.host.shutdown()
        leg.client.shutdown()


def main():
    fails = []
    t0 = time.time()
    run_leg(fails, "host", 3)
    run_leg(fails, "client", 2)
    print(f"\n==== PvP second base summary ({time.time() - t0:.1f}s) ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        sys.exit(2)
    print("  both game modes: every X-COM base survived the rejoin, the month end and the host's save")
    sys.exit(0)


if __name__ == "__main__":
    main()
