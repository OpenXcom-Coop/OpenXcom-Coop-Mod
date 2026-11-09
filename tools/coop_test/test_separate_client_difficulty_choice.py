"""A joining SEPARATE client chooses its own difficulty only when the mod gives a
difficulty level its own starting base.

Mods such as 40K define startingBaseExperienced ... startingBaseSuperhuman and
use the difficulty screen as a faction screen, so each player picks. Every
other campaign, X-Com Files included, starts the client on the host's
difficulty with no extra screen.

  one_base_master  Mod Coop_MasterOneBase_Test: a master mod on top of xcom1
                   with one starting base, as X-Com Files is. The host starts
                   the campaign; the client must go straight to base placement.
  faction_bases    Mod Coop_FactionBases_Test: gives Veteran its own starting
                   base. The client must get the difficulty screen, pick
                   Veteran, place its base, and both players reach the geoscape.

Each row boots its own pair and counts, in the client's engine log, how often
the client opened the difficulty screen (NewGameState). Before the fix, a
master mod other than xcom1 / xcom2 opened it (one_base_master fails, the
client stays on the screen), and a non-master mod never did (faction_bases
fails, the client never shows it).

EVIDENCE then PASS / FAIL per row; ONE run; exit 0 only if all pass, else 2.
Run:  py -3 tools/coop_test/test_separate_client_difficulty_choice.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture  # noqa: E402

MODS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods")
VETERAN = 2

ROWS = (
    # name, mod folder, ports (host, client, lobby), client difficulty, screens wanted
    ("one_base_master", "Coop_MasterOneBase_Test", (49756, 49757, 48456), None, 0),
    ("faction_bases", "Coop_FactionBases_Test", (49758, 49759, 48458), VETERAN, 1),
)


def difficulty_screens(user_dir):
    """How many times this machine opened the difficulty screen."""
    path = os.path.join(user_dir, "openxcom.log")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as log:
        return sum("push class OpenXcom::NewGameState" in line for line in log)


def stack(gc):
    try:
        return [s.split("::")[-1] for s in gc.cmd({"cmd": "get_state"}).get("states", [])]
    except Exception as e:  # noqa: BLE001
        return [f"<no reply: {type(e).__name__}>"]


def run_row(name, mod, ports, client_difficulty, want):
    js = shared_fixture.SharedSession(f"sep_diff_{name}", ports,
                                      mods=(os.path.join(MODS, mod),), campaign_mode="coop")
    error = None
    try:
        try:
            js._start(True, "HostBase", "ClientBase", None, client_difficulty,
                      "HostPlayer", "ClientPlayer")
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
        got = difficulty_screens(js.client_dir)
        print(f"EVIDENCE {name}: mod={mod} client difficulty screens={got} (want {want}) "
              f"bring-up={'ok' if error is None else error} "
              f"host stack={stack(js.host)} client stack={stack(js.client)}", flush=True)
    finally:
        js.shutdown()
    if got != want:
        return f"client opened the difficulty screen {got} time(s), want {want}"
    if error is not None:
        return f"the campaign did not start: {error}"
    return None


def main():
    failed = 0
    for name, mod, ports, client_difficulty, want in ROWS:
        try:
            problem = run_row(name, mod, ports, client_difficulty, want)
        except Exception as e:  # noqa: BLE001
            problem = f"{type(e).__name__}: {e}"
        if problem:
            failed += 1
            print(f"FAIL {name}: {problem}", flush=True)
        else:
            print(f"PASS {name}", flush=True)
    sys.exit(0 if failed == 0 else 2)


if __name__ == "__main__":
    main()
