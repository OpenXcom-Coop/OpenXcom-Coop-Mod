"""PvP campaign mid-battle resume: load gm2+gm3 saves, rejoin, verify battle.

Run:  python tools/coop_test/test_pvp_campaign_resume.py
Exit 0 = pass; 2 = failure.
"""

import os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session

PORT = "48003"
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

def _states(gc):
    return [s.replace("class OpenXcom::", "") for s in gc.cmd({"cmd":"get_state"})["states"]]
def _has(gc, name): return any(name in s for s in _states(gc))
def _fail(fails, msg): print(f"  FAIL {msg}"); fails.append(msg)

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
        session.resume_campaign_battle(host, client, save_file, port=PORT,
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

def main():
    fails=[]
    test_resume(fails, "pvp_gm2_battle.sav", "gm2")
    test_resume(fails, "pvp_gm3_battle.sav", "gm3")
    print("\n==== PvP campaign resume summary ====")
    if fails:
        for f in fails:print(f"  FAIL {f}")
        sys.exit(2)
    print("  gm2 + gm3 mid-battle resume PASS")
    sys.exit(0)

if __name__=="__main__":
    main()
