"""W2-P7 S-C-C - test_w2_campaign_followups_separate.py: in a SEPARATE campaign the second player, after its own OK and
its return to its own world, sees the host's after-battle screens (promotions, medals) with the host's soldiers named
`[HostPlayer] Name` and its own guest plain; the host names the guest `[ClientPlayer] Guest Zzz` (docs
rewrite/prompts/w2p7_sc_design.md section 3.4, AMENDMENT P7-6 section 4.4, the P7-6 C re-pin at 2e177ff39 section 4
row F5, PR-C1..PR-C10; owner D154, D177 (a); MR5, MR11). SEPARATE shows no base screen (no CannotReequipState, D154).

Before S-C-C: the client's OK returns it to its own geoscape (S-C-B1's coopSeparateReturn) and nothing follows.

Fixture (one boot, port 47212): test_w2_battle_end_separate._stage_common(..., guest_kill, ...) - B1's guest's-OWN-kill
construction (SEED_P 2, MAP_FP_P, KEEP's TU 0; F5445/F5446/F5449/F5450) - with the data-only mod Coop_Medal_Test on both
machines (make_user_dir mods, as test_w2_battle_end_separate_diary.py): every surviving participant earns
STR_COOP_MEDAL_TEST (PR-20), and the guest's kill promotes it. Pre-cell (FIXTURE-STOP): B1's guards plus the host's
merged "Guest Zzz" copy with kills >= 1, rankString RANK_F5 and the medal.

The procedure and the cells are test_w2_campaign_followups.py's (imported): both debrief_state snapshots, the client's
OK (its stack right after it, every follow-up read with followup_state while on top, then dismissed), the host's OK +
drain (read the same way). Cells, in order (a failed cell ends the row):
  (1) both debriefings equal after PR-10 stripping, the client's display-only;
  (2) the client's chain == CHAIN_F5 == its stack after the OK == the host's drained follow-ups (no CannotReequipState)
      [RED];
  (3) the client's PromotionsState rows == [["Guest Zzz", RANK_TR_F5, BASE]];
  (4) the client's CommendationState: the medal title, the HOST_MEDALS_F5 host soldiers `[HostPlayer] <name>`, "Guest
      Zzz" plain;
  (5) both debriefings' page-2 names: the other seat's soldiers `[<seat name>] `, own plain;
  (6) the host's PromotionsState [["[ClientPlayer] Guest Zzz", ...]] and CommendationState (host names plain,
      `[ClientPlayer] Guest Zzz`), both machines' rows equal after PR-10 stripping (P6-8); both on their geoscapes,
      the client zero-disk, no LoadGameState pushed, host fatalVote.armed 0.
RED (commit S-C-C.1, product untouched): F5 fails on exactly cell 2 - the client's chain is empty. GREEN (S-C-C.2):
F5 passes. ONE "EVIDENCE F5:" line, then "PASS F5" or "FAIL F5: <message>". WV-D95/D99/D100: ONE foreground run, no
skip path; exit 0 only when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_w2_campaign_followups_separate.py
"""

import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import test_w2_battle_end_separate as b1
import test_w2_campaign_followups as fu
from harness import GameClient, make_user_dir

# ----- pins (sources in the comments) -----
PORT = "47212"                                     # the re-pin section 4: C's SEPARATE block 47212-47214
GUEST = "Guest Zzz"                                # session.bring_up_separate_guest_battle's renamed guest
RANK_F5, RANK_TR_F5 = "STR_SERGEANT", "Sergeant"   # the merged copy after the guest's kill (B1 evidence 3/3; red capture)
BASE = "HostBase"                                  # the host's base (the guest's coop-base mirror carries its name, F5629)
CHAIN_F5 = ["CommendationState", "PromotionsState"]   # re-pin F5 (2) = the host's drain (red-build capture)
HOST_MEDALS_F5 = 3                                 # host soldiers awarded the medal on this boot (red-build capture)


def precheck_f5(copy):
    comms = [c.get("type") for c in ((copy.get("diary") or {}).get("commendations") or [])]
    if (copy.get("kills") or 0) < 1 or copy.get("rankString") != RANK_F5 or fu.MEDAL_TYPE not in comms:
        return (f"the host's merged {GUEST!r} copy kills={copy.get('kills')!r} rankString={copy.get('rankString')!r} "
                f"commendations={comms} (want kills >= 1, {RANK_F5}, {fu.MEDAL_TYPE}: Coop_Medal_Test on both?)")
    return None


def stage(host, client, ctx):
    b1._stage_common("F5", host, client, ctx, PORT, b1.guest_kill, precheck_f5)
    names = [fu.strip_prefix(s.get("name")) for s in (ctx["hostDebrief"].get("soldiers") or [])]   # raw (PR-10)
    ctx["owners"] = fu.owners_of(host, names)
    if GUEST not in ctx["owners"] or len(ctx["owners"]) != len(names):
        b1.capture("F5 owners", f"page-2 names {names} -> owners {ctx['owners']}", (host, client))


def f5_cells(ctx):
    owners = ctx["owners"]
    host_names = sorted(n for n, o in owners.items() if n != GUEST)

    def promo_client():
        got = ctx["client"]["rows"].get("PromotionsState")
        return [] if got == [[GUEST, RANK_TR_F5, BASE]] else [
            f"client PromotionsState rows {got} != {[[GUEST, RANK_TR_F5, BASE]]}"]

    def medals_client():
        got = ctx["client"]["rows"].get("CommendationState") or []
        prefixed = sorted(r[0][len("[HostPlayer] "):] for r in got if r and r[0].startswith("[HostPlayer] "))
        f = []
        if [fu.MEDAL_TR, ""] not in got or not any(r and r[0] == GUEST for r in got):
            f.append(f"client CommendationState rows {got} lack the {fu.MEDAL_TR!r} title or a plain {GUEST!r}")
        if len(prefixed) != HOST_MEDALS_F5 or not set(prefixed) <= set(host_names):
            f.append(f"client CommendationState host rows {prefixed} (want {HOST_MEDALS_F5} of {host_names}, each "
                     f"`[HostPlayer] <name>`)")
        return f

    def host_rows():
        must = (lambda base: [] if base == [[GUEST, RANK_TR_F5, BASE]] else
                [f"host PromotionsState rows (stripped) {base} != {[[GUEST, RANK_TR_F5, BASE]]}"])
        return (fu.rows_cell(ctx, "PromotionsState", owners, must) + fu.rows_cell(ctx, "CommendationState", owners)
                + fu.cell_end(ctx))
    return [
        ("1 both debriefings, the client's display-only", lambda: fu.cell_debriefs(ctx)),
        ("2 the client's chain", lambda: fu.cell_chain(ctx, CHAIN_F5, False, "no follow-up")),
        ("3 the client's PromotionsState rows", promo_client),
        ("4 the client's CommendationState rows", medals_client),
        ("5 page-2 [Player] prefixes on both", lambda: fu.cell_page2(ctx, owners)),
        ("6 the host's rows; both on their geoscapes", host_rows),
    ]


def main():
    t0, results, ctx, pre = time.time(), {}, {"boot": "F5"}, None
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 0, make_user_dir("w2p7scc_f5_host", mods=[fu.MEDAL_MOD]))
    client = GameClient("client", 0, make_user_dir("w2p7scc_f5_client", mods=[fu.MEDAL_MOD]))
    try:
        try:
            host.spawn(); client.spawn(); host.connect(); client.connect()
            stage(host, client, ctx)
        except Exception as e:
            pre = f"pre-cell (FIXTURE-STOP) {fu.short(e, 800)}"
        if pre is None:
            try:
                fu.procedure(types.SimpleNamespace(host=host, client=client), ctx, shared=False)
            except Exception as e:
                pre = f"procedure (the OKs and follow-up reads) raised {fu.short(e, 800)}"
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["newCrashLogs"] = new_crash
        try:
            ctx["end"] = {"host": b1.view(host), "client": b1.view(client)}
        except Exception as e:
            ctx["end"] = f"probe failed: {fu.short(e)}"
        if pre:
            results["F5"] = pre
        else:
            ctx["cells"] = fu.check_row("F5", f5_cells(ctx), results)
        if new_crash:
            results["F5"] = (results["F5"] + " | " if results["F5"] else "") + f"new crash log(s): {new_crash}"
        fu.evidence("F5", ctx)
        print("PASS F5" if results["F5"] is None else f"FAIL F5: {results['F5']}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[w2p7-scc] shutdown {gc.name}: {fu.short(e)}", flush=True)
    ok = results.get("F5", "missing") is None
    print(f"\ntest_w2_campaign_followups_separate: {1 if ok else 0}/1 passed (pass={['F5'] if ok else []} "
          f"fail={[] if ok else ['F5']}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
