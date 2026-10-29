"""test_debrief_fidelity.py: on a co-op debriefing each player reads the title and the recovery header
in its own language, and a Custom Battle debriefing names the other player's soldiers `[Player] Name` on page 2.

Two boots, one ending each; both debriefings are read once and no OK is pressed (each boot ends at shutdown):
  Boot german_client  host en-US (label 49351), client `language: de` (49352); test_battle_end.boot on lobby
          47341, then stage_last_alien_down + end_last_alien_down (last_alien_down, the last alien down). Rows
          german_client_title, german_client_names.
  Boot german_host  host `language: de` (49353), client en-US (49354); lobby 47342, stage_host_abort +
          end_host_abort (host_abort, the host's abort: end_last_alien_down waits on the host's English
          "END TURN 1/2"). Rows german_host_title, german_host_names.
S = the host's battle_state player-soldier units {id, rawName, coop}, both get_coop {hostName, clientName,
coopStatic} and both synced_options_state.localSeat, taken after the bring-up and before the ending.

  german_client_title  the client's title == "UFO wurde geborgen" (de.yml :206), recoveryHeader == "UFO-BERGUNG"
         (de.yml :226).
  german_client_names  each machine's page-2 names == its view, as sorted lists: for each row raw = the name with
         a leading `[HostPlayer] ` / `[ClientPlayer] ` removed and its seat = the S unit with that rawName; the host
         names seat 0 raw and seat 1 `[<host clientName>] raw`; the client names seat 1 raw and seat 0
         `[<client clientName>] raw`.
  german_host_title  the client's title == "UFO is not recovered" (en-US).
  german_host_names  as german_client_names on the abort's seven rows.
Guard cells (prefix guard:) check the setup the rows rely on: the bring-up (MAP_FP, hash clean); the staging,
ending and both debriefings reached; both debriefs shown and on top, the client display-only, widgets ==
DEBRIEF_WIDGETS, page 0, parseErrors 0; S's seats (2 x coop 1, 5 x coop 0); host clientName "ClientPlayer" and
client "HostPlayer", the client's coopStatic true, localSeat host 0 / client 1 (in S and at the debriefing);
page-2 deltas and tbe.debrief_view soldiers equal on both; page-1 rows' (qty, score, recovery) and total equal.
Boot german_client: tbe.pin_view(host) == HOST_DEBRIEF["last_alien_down"], the client's rating "BEWERTUNG> OK".
Boot german_host: the host's title "UFO wurde nicht geborgen" and rating "BEWERTUNG> SCHLECHT!", the client's
rating "RATING> POOR!", both recoveryHeader "" (the empty key and the client's own :558),
tbe.pin_view(host) == HOST_DEBRIEF["host_abort"] with that German title and rating.

A client that shows the host's debriefing text fails german_client_title on clientTitle and clientHeader (the
host's "UFO is recovered" / "UFO RECOVERY") and german_host_title on clientTitle (the German host's "UFO wurde
nicht geborgen"); a debriefing that leaves every name plain fails german_client_names and german_host_names on
hostPage2 and clientPage2. The guard cells pass either way.

German item text is non-ASCII and soldier names change per boot: neither is pinned; the expected
page 2 comes from S. An EVIDENCE line precedes every verdict; every row runs after a failure; a boot miss fails its
rows "boot" with ONE CAPTURE line (setup failure). One run is the result, no skip path, one boot
per row pair. Exit 0 only when every row and every guard cell passes, 2 otherwise. Run it in the foreground.

Run:  python tools/coop_test/test_debrief_fidelity.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir
from session import battle_state
import repro_atom_walk as raw
import test_battle_end as tbe

DE = {"language": "de"}
# rendered by a running German machine, else the deployed de.yml (sha256 ce1779f3..., equal to
# bin\standard).
DE_UFO_RECOVERED = "UFO wurde geborgen"             # STR_UFO_IS_RECOVERED, de.yml :206
DE_UFO_RECOVERY = "UFO-BERGUNG"                     # STR_UFO_RECOVERY, de.yml :226
DE_UFO_NOT_RECOVERED = "UFO wurde nicht geborgen"   # STR_UFO_IS_NOT_RECOVERED, rendered by boot german_host's host
EN_UFO_NOT_RECOVERED = "UFO is not recovered"       # en-US, tbe.HOST_DEBRIEF["host_abort"]
DE_RATING_OK = "BEWERTUNG> OK"                      # rendered by boot german_client's client
DE_RATING_POOR = "BEWERTUNG> SCHLECHT!"             # rendered by boot german_host's host
EN_RATING_POOR = "RATING> POOR!"                    # rendered by boot german_host's client
SEATS = [0, 0, 0, 0, 0, 1, 1]                       # S: ids 8, 9 coop 1; ids 10-14 coop 0
TITLE_NOTE = "the second player reads the host's title and header"
NAMES_NOTE = "a Custom Battle debrief names no player"
BOOTS = (
    ("german_client", {"host": (49351, "debrief_fidelity_german_client_host", None),
                       "client": (49352, "debrief_fidelity_german_client_client", DE), "port": "47341",
                       "stage": tbe.stage_last_alien_down, "end": tbe.end_last_alien_down,
                       "rows": ("german_client_title", "german_client_names")}),
    ("german_host", {"host": (49353, "debrief_fidelity_german_host_host", DE),
                     "client": (49354, "debrief_fidelity_german_host_client", None), "port": "47342",
                     "stage": tbe.stage_host_abort, "end": tbe.end_host_abort,
                     "rows": ("german_host_title", "german_host_names")}),
)


# ===================== probes =====================


def safe(fn):
    try:
        return fn()
    except Exception as e:
        return {"probeError": tbe.short(e)}


def snapshot(gc):
    """get_coop {hostName, clientName, coopStatic} and synced_options_state.localSeat of one machine."""
    c = safe(lambda: tbe.coop(gc))
    so = safe(lambda: gc.cmd({"cmd": "synced_options_state"}))
    v = {k: c.get(k) for k in ("hostName", "clientName", "coopStatic")}
    v["localSeat"] = so.get("localSeat")
    for name, d in (("get_coop", c), ("synced_options_state", so)):
        if "probeError" in d:
            v[f"{name}Error"] = d["probeError"]
    return v


def soldier_units(gc):
    return [{"id": u.get("id"), "rawName": u.get("rawName"), "coop": u.get("coop")}
            for u in battle_state(gc).get("units") or [] if u.get("isPlayerSoldier")]


def capture(gc):
    """The setup-failure dump of one machine (every probe the rows read)."""
    return {"stack": safe(lambda: tbe.stack(gc)), "snapshot": snapshot(gc), "units": safe(lambda: soldier_units(gc)),
            "debrief": safe(lambda: gc.cmd({"cmd": "debrief_state"}))}


def bare(name):
    return next((name[len(p):] for p in tbe.SEAT_PREFIXES if isinstance(name, str) and name.startswith(p)), name)


def names(deb):
    return sorted(str(s.get("name")) for s in deb.get("soldiers") or [] if isinstance(s, dict))


def view(deb, seat_of, own_seat, peer):
    """Each page-2 row's raw name, prefixed `[<peer>] ` when its S seat is not this machine's (sorted)."""
    out = []
    for s in deb.get("soldiers") or []:
        r = bare(s.get("name")) if isinstance(s, dict) else s
        seat = seat_of.get(r)
        out.append(f"<{r!r}: no S unit>" if seat is None else r if seat == own_seat else f"[{peer}] {r}")
    return sorted(str(n) for n in out)


# ===================== verdicts =====================


def verdict(label, cells, results):
    """cells = [(name, got, want, note)]: ONE EVIDENCE line (every cell), then PASS / FAIL naming each failing cell."""
    print(f"EVIDENCE {label}: " + "; ".join(f"{n} {'ok' if g == w else 'BAD'} got={g!r} want={w!r}"
                                             for n, g, w, _ in cells), flush=True)
    bad = [c for c in cells if c[1] != c[2]]
    if bad:
        print(f"FAIL {label}: " + " | ".join(f"{n}: got {g!r}, want {w!r}" + (f" - {note}" if note else "")
                                             for n, g, w, note in bad), flush=True)
    else:
        print(f"PASS {label}", flush=True)
    results[label] = not bad


def guard_cells(bid, units, s_snap, d_snap, hdeb, cdeb, steps):
    shape = lambda d: (d.get("shown"), d.get("onTop"), d.get("displayOnly"), d.get("widgets"), d.get("page"),
                       d.get("parseErrors"))
    page1 = lambda d: [(r.get("qty"), r.get("score"), r.get("recovery")) for r in d.get("rows") or []
                       if isinstance(r, dict)]
    snaps = (s_snap["host"], d_snap["host"], s_snap["client"], d_snap["client"])
    cells = [
        ("guard:boot", "ok", "ok", "the bring-up: MAP_FP, hash clean"),
        ("guard:ending", steps, [], "staging, ending, host DebriefingState, client end top"),
        ("guard:hostDebrief", shape(hdeb), (True, True, False, tbe.DEBRIEF_WIDGETS, 0, 0),
         "shown, onTop, displayOnly, widgets, page, parseErrors"),
        ("guard:clientDebrief", shape(cdeb), (True, True, True, tbe.DEBRIEF_WIDGETS, 0, 0),
         "shown, onTop, displayOnly, widgets, page, parseErrors"),
        ("guard:seats", sorted((u.get("coop") for u in units), key=repr), SEATS, "S: the host's player-soldier units"),
        ("guard:clientName", tuple(s.get("clientName") for s in snaps),
         (raw.CLIENT_PLAYER, raw.CLIENT_PLAYER, raw.HOST_PLAYER, raw.HOST_PLAYER), "host S/debrief, client S/debrief"),
        ("guard:coopStatic", (s_snap["client"].get("coopStatic"), d_snap["client"].get("coopStatic")), (True, True),
         "client S/debrief"),
        ("guard:localSeat", tuple(s.get("localSeat") for s in snaps), (0, 0, 1, 1), "host S/debrief, client S/debrief"),
        ("guard:page2Deltas", [s.get("deltas") for s in cdeb.get("soldiers") or [] if isinstance(s, dict)],
         [s.get("deltas") for s in hdeb.get("soldiers") or [] if isinstance(s, dict)], "client vs host"),
        ("guard:page2Stripped", tbe.debrief_view(cdeb)["soldiers"], tbe.debrief_view(hdeb)["soldiers"],
         "tbe.debrief_view soldiers, client vs host"),
        ("guard:page1Rows", page1(cdeb), page1(hdeb), "(qty, score, recovery), client vs host"),
        ("guard:total", cdeb.get("total"), hdeb.get("total"), "client vs host"),
    ]
    if bid == "german_client":
        cells += [("guard:hostPin", tbe.pin_view(hdeb), tbe.HOST_DEBRIEF["last_alien_down"],
                   "tbe.pin_view(host) == HOST_DEBRIEF last_alien_down"),
                  ("guard:clientRating", cdeb.get("rating"), DE_RATING_OK, "the German client renders its own rating")]
    else:
        cells += [("guard:hostTitle", hdeb.get("title"), DE_UFO_NOT_RECOVERED, "the German host"),
                  ("guard:hostRating", hdeb.get("rating"), DE_RATING_POOR, "the German host"),
                  ("guard:clientRating", cdeb.get("rating"), EN_RATING_POOR, "the English client renders its own rating"),
                  ("guard:recoveryHeaders", (hdeb.get("recoveryHeader"), cdeb.get("recoveryHeader")), ("", ""),
                   "host, client: the empty key and the client's own :558"),
                  ("guard:hostPin", tbe.pin_view(hdeb),
                   dict(tbe.HOST_DEBRIEF["host_abort"], title=DE_UFO_NOT_RECOVERED, rating=DE_RATING_POOR),
                   "HOST_DEBRIEF host_abort with the German title and rating")]
    return cells


def row_cells(rid, seat_of, d_snap, hdeb, cdeb):
    if rid == "german_client_title":
        return [("clientTitle", cdeb.get("title"), DE_UFO_RECOVERED, TITLE_NOTE),
                ("clientHeader", cdeb.get("recoveryHeader"), DE_UFO_RECOVERY, TITLE_NOTE)]
    if rid == "german_host_title":
        return [("clientTitle", cdeb.get("title"), EN_UFO_NOT_RECOVERED, TITLE_NOTE)]
    return [("hostPage2", names(hdeb), view(hdeb, seat_of, 0, d_snap["host"].get("clientName")), NAMES_NOTE),
            ("clientPage2", names(cdeb), view(cdeb, seat_of, 1, d_snap["client"].get("clientName")), NAMES_NOTE)]


# ===================== one boot =====================


def run_boot(bid, cfg, results):
    t0 = time.time()
    (hl, hd, ho), (cl, cd, co) = cfg["host"], cfg["client"]
    host = GameClient("host", hl, make_user_dir(hd, options=ho))
    client = GameClient("client", cl, make_user_dir(cd, options=co))
    walls = {}
    try:
        try:
            tbe.boot(host, client, cfg["port"])
        except Exception as e:
            err = tbe.short(e)
            print(f"CAPTURE {bid}: boot miss {err}; host={capture(host)}; client={capture(client)}", flush=True)
            verdict(f"guard:{bid}", [("guard:boot", err, "ok", "the bring-up: MAP_FP, hash clean (setup failure)")], results)
            for rid in cfg["rows"]:
                verdict(rid, [("boot", err, "ok", "SETUP-FAILURE")], results)
            return
        walls["bringUp"] = round(time.time() - t0, 2)
        units = soldier_units(host)
        s_snap = {"host": snapshot(host), "client": snapshot(client)}
        pre, ending = [], []
        t1 = time.time()
        staging = cfg["stage"](host, client, pre)
        t2 = time.time()
        end_resp = cfg["end"](host, client, ending)
        deb_ok, deb_s = tbe.wait_until(lambda: any("DebriefingState" in s for s in tbe.stack(host)), tbe.DEBRIEF_S,
                                       0.1)
        if not deb_ok:
            ending.append(f"host DebriefingState not reached within {deb_s}s of the ending")
        cl_ok, cl_s = tbe.wait_until(lambda: tbe.top(client) in tbe.CLIENT_END_TOPS, tbe.CLIENT_LEAVE_S, 0.25)
        if not cl_ok or tbe.top(client) != "DebriefingState":
            ending.append(f"client top {tbe.top(client)} after {cl_s}s (want DebriefingState)")
        walls.update(stage=round(t2 - t1, 2), endingToDebriefs=round(time.time() - t2, 2), hostDebriefS=deb_s,
                     clientDebriefS=cl_s)
        hdeb, cdeb = (safe(lambda gc=gc: gc.cmd({"cmd": "debrief_state"})) for gc in (host, client))
        d_snap = {"host": snapshot(host), "client": snapshot(client)}
        print(f"EVIDENCE boot {bid}: walls={walls}; S units={units}; S snapshots={s_snap}; debrief snapshots={d_snap}; "
              f"host stack={safe(lambda: tbe.stack(host))}; client stack={safe(lambda: tbe.stack(client))}; "
              f"staging={staging}; ending={end_resp}; pre fails={pre}; ending fails={ending}; "
              f"host debrief_state={hdeb}; client debrief_state={cdeb}", flush=True)
        steps = [f"pre-ending: {m}" for m in pre] + [f"ending: {m}" for m in ending]
        verdict(f"guard:{bid}", guard_cells(bid, units, s_snap, d_snap, hdeb, cdeb, steps), results)
        seat_of = {u.get("rawName"): u.get("coop") for u in units}
        for rid in cfg["rows"]:
            verdict(rid, row_cells(rid, seat_of, d_snap, hdeb, cdeb), results)
    except Exception as e:
        print(f"CAPTURE {bid}: {type(e).__name__}: {e}; host={capture(host)}; client={capture(client)}", flush=True)
        for label in (f"guard:{bid}",) + tuple(cfg["rows"]):
            if label not in results:
                verdict(label, [("run", tbe.short(e), "ok", "SETUP-FAILURE")], results)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[test_debrief_fidelity] shutdown {gc.name}: {tbe.short(e)}", flush=True)
        walls["total"] = round(time.time() - t0, 2)
        print(f"[test_debrief_fidelity] boot {bid} walls={walls} start={t0:.1f} end={time.time():.1f}", flush=True)


# ===================== main =====================


def main():
    t0 = time.time()
    results = {}
    for bid, cfg in BOOTS:
        run_boot(bid, cfg, results)
    rows = [rid for _, cfg in BOOTS for rid in cfg["rows"]]
    guards = [f"guard:{bid}" for bid, _ in BOOTS]
    failed = [k for k in guards + rows if not results.get(k)]
    print(f"\ntest_debrief_fidelity: rows {sum(1 for r in rows if results.get(r))}/{len(rows)} passed, guards "
          f"{sum(1 for g in guards if results.get(g))}/{len(guards)} passed (fail={failed}) in {time.time() - t0:.1f}s",
          flush=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
