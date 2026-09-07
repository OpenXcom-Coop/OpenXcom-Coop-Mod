"""One-time seed hunt (SPEC 0e-4, owner D11). NOT a regression member. Boots host+client on
--mission with seeds 1..N (fixed order), set_seed on the host right before newbattle_ok, and
reports per seed: mapFingerprint, the predicate verdict, and the host-log mismatch line if the
handshake refused. Stops at the first --stop-after matches. Exit 0 = found; 3 = budget exhausted."""
import argparse, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
import session
import repro_atom_walk as W

ADOPT_RE = re.compile(r"\[coop-itemid\] WV-D61: adopted coopItemIdCtr (\d+) \(derived (\d+)\)")
REFUSE_SIG = "battle_ready saveBlob MISMATCH"

def log_text(gc):
    try:
        with open(os.path.join(gc.user_dir, "openxcom.log"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""

def predicate(name, host, client):
    st = session.battle_state(host)
    npc = [u for u in st.get("units", []) if u.get("faction") != session.FACTION_PLAYER]
    if name == "killed":
        return any(u.get("status") == 6 for u in npc), {"killed": [u["id"] for u in npc if u.get("status") == 6]}
    if name == "stunned":
        return any(u.get("status") == 7 for u in npc), {"stunned": [u["id"] for u in npc if u.get("status") == 7]}
    if name in ("itemid-divergent", "itemid-agreed"):
        time.sleep(2)
        pairs = [(int(m.group(1)), int(m.group(2))) for m in ADOPT_RE.finditer(log_text(client))]
        adopted = client.cmd({"cmd": "event_state"}).get("itemIdCtrAdopted", 0)
        diverged = any(c != d for c, d in pairs)
        ok = (adopted > 0 or pairs) and (diverged if name == "itemid-divergent" else not diverged)
        return bool(ok), {"adopted": adopted, "pairs": pairs}
    raise SystemExit(f"unknown predicate {name}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mission", required=True)
    ap.add_argument("--want", required=True, choices=["killed", "stunned", "itemid-divergent", "itemid-agreed"])
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--stop-after", type=int, default=1)
    ap.add_argument("--craft", default=None)
    ap.add_argument("--race", default=None)
    a = ap.parse_args()
    found = []
    for n in range(1, a.seeds + 1):
        port = str(48600 + n)
        host = GameClient("hunt-host", 49600 + n * 2, make_user_dir(f"hunt_{a.want}_host_{n}"))
        client = GameClient("hunt-client", 49601 + n * 2, make_user_dir(f"hunt_{a.want}_client_{n}"))
        seated = {}
        verdict = None
        try:
            W.bring_up_lobby(host, client, port)
            def pins(h):
                if a.craft: h.ok({"cmd": "newbattle_craft", "type": a.craft})
                if a.race: h.ok({"cmd": "newbattle_race", "race": a.race})
            try:
                session.drive_to_battlescape(host, client, seated, mission=a.mission, pre_seat=pins,
                                             pre_ok=lambda h: h.ok({"cmd": "set_seed", "seed": n}))
            except TimeoutError as e:
                refused = REFUSE_SIG in log_text(host)
                verdict = {"seed": n, "refused_handshake": refused, "error": str(e)[:160]}
                print(f"seed {n}: HANDSHAKE {'REFUSED (pre-existing battle_ready saveBlob mismatch)' if refused else 'TIMEOUT'}", flush=True)
                continue
            fp = session.battle_state(host).get("mapFingerprint")
            ok, detail = predicate(a.want, host, client)
            verdict = {"seed": n, "mapFingerprint": fp, "match": ok, **detail}
            print(f"seed {n}: fingerprint={fp} {'MATCH' if ok else 'no'} {detail}", flush=True)
            if ok:
                found.append(verdict)
                if len(found) >= a.stop_after:
                    break
        finally:
            host.shutdown(); client.shutdown()
    print("RESULT hunt_seed:", {"want": a.want, "mission": a.mission, "found": found})
    sys.exit(0 if found else 3)

if __name__ == "__main__":
    main()
