"""test_campaign_followups_separate.py: in a SEPARATE campaign the second player, after its own OK and
its return to its own world, sees the host's after-battle screens (promotions, medals) with the host's soldiers named
`[HostPlayer] Name` and its own guest plain; the host names the guest `[ClientPlayer] Guest Zzz`. SEPARATE shows no
base screen (no CannotReequipState).

Without this, the client's OK returns it to its own geoscape (coopSeparateReturn) and nothing follows.

Fixture (one boot, port 47212): test_battle_end_separate._stage_common(..., guest_kill, ...) - the guest's OWN kill
construction of test_battle_end_separate's guest_returns_alive row (SEED_P 2, MAP_FP_P, KEEP's TU 0) - with the
data-only mod Coop_Medal_Test on both machines (make_user_dir mods, as test_battle_end_separate_diary.py): every
surviving participant earns STR_COOP_MEDAL_TEST, and the guest's kill promotes it. Pre-cell (setup failure): that row's
pre-cell guards plus the host's merged "Guest Zzz" copy with kills >= 1, rankString GUEST_RANK and the medal.

The procedure and the cells are test_campaign_followups.py's (imported): both debrief_state snapshots, the client's
OK (its stack right after it, every follow-up read with followup_state while on top, then dismissed), the host's OK +
drain (read the same way). Cells, in order (a failed cell ends the row):
  (1) both debriefings equal after the [Player] prefix is stripped, the client's display-only;
  (2) the client's chain == FOLLOWUP_CHAIN == its stack after the OK == the host's drained follow-ups (no
      CannotReequipState);
  (3) the client's PromotionsState rows == [["Guest Zzz", GUEST_RANK_TR, BASE]];
  (4) the client's CommendationState: the medal title, the HOST_MEDALS host soldiers `[HostPlayer] <name>`, "Guest
      Zzz" plain;
  (5) both debriefings' page-2 names: the other seat's soldiers `[<seat name>] `, own plain;
  (6) the host's PromotionsState [["[ClientPlayer] Guest Zzz", ...]] and CommendationState (host names plain,
      `[ClientPlayer] Guest Zzz`), both machines' rows equal after the prefix is stripped; both on their geoscapes,
      the client zero-disk, no LoadGameState pushed, host fatalVote.armed 0.
A client that shows no follow-up (its chain is empty) fails on exactly cell 2. ONE "EVIDENCE separate_followups:" line,
then "PASS separate_followups" or "FAIL separate_followups: <message>". ONE foreground run, no skip path; exit 0 only
when the row passes, 2 otherwise.

Run:  python tools/coop_test/test_campaign_followups_separate.py
"""

import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session
import test_battle_end_separate as BES
import test_campaign_followups as fu
from harness import GameClient, make_user_dir

# ----- pins -----
PORT = "47212"                                     # the co-op session port
GUEST = "Guest Zzz"                                # session.bring_up_separate_guest_battle's renamed guest
GUEST_RANK, GUEST_RANK_TR = "STR_SERGEANT", "Sergeant"   # the merged copy after the guest's kill (3/3 boots)
BASE = "HostBase"                                  # the host's base (the guest's coop-base mirror carries its name)
FOLLOWUP_CHAIN = ["CommendationState", "PromotionsState"]   # the host's drained follow-ups
HOST_MEDALS = 3                                    # host soldiers awarded the medal on this boot


def precheck_copy(copy):
    comms = [c.get("type") for c in ((copy.get("diary") or {}).get("commendations") or [])]
    if (copy.get("kills") or 0) < 1 or copy.get("rankString") != GUEST_RANK or fu.MEDAL_TYPE not in comms:
        return (f"the host's merged {GUEST!r} copy kills={copy.get('kills')!r} rankString={copy.get('rankString')!r} "
                f"commendations={comms} (want kills >= 1, {GUEST_RANK}, {fu.MEDAL_TYPE}: Coop_Medal_Test on both?)")
    return None


def stage(host, client, ctx):
    BES._stage_common("separate_followups", host, client, ctx, PORT, BES.guest_kill, precheck_copy)
    names = [fu.strip_prefix(s.get("name")) for s in (ctx["hostDebrief"].get("soldiers") or [])]   # raw names
    ctx["owners"] = fu.owners_of(host, names)
    if GUEST not in ctx["owners"] or len(ctx["owners"]) != len(names):
        BES.capture("page-2 owners", f"page-2 names {names} -> owners {ctx['owners']}", (host, client))


def followup_cells(ctx):
    owners = ctx["owners"]
    host_names = sorted(n for n, o in owners.items() if n != GUEST)

    def promo_client():
        got = ctx["client"]["rows"].get("PromotionsState")
        return [] if got == [[GUEST, GUEST_RANK_TR, BASE]] else [
            f"client PromotionsState rows {got} != {[[GUEST, GUEST_RANK_TR, BASE]]}"]

    def medals_client():
        got = ctx["client"]["rows"].get("CommendationState") or []
        prefixed = sorted(r[0][len("[HostPlayer] "):] for r in got if r and r[0].startswith("[HostPlayer] "))
        f = []
        if [fu.MEDAL_TR, ""] not in got or not any(r and r[0] == GUEST for r in got):
            f.append(f"client CommendationState rows {got} lack the {fu.MEDAL_TR!r} title or a plain {GUEST!r}")
        if len(prefixed) != HOST_MEDALS or not set(prefixed) <= set(host_names):
            f.append(f"client CommendationState host rows {prefixed} (want {HOST_MEDALS} of {host_names}, each "
                     f"`[HostPlayer] <name>`)")
        return f

    def host_rows():
        must = (lambda base: [] if base == [[GUEST, GUEST_RANK_TR, BASE]] else
                [f"host PromotionsState rows (stripped) {base} != {[[GUEST, GUEST_RANK_TR, BASE]]}"])
        return (fu.rows_cell(ctx, "PromotionsState", owners, must) + fu.rows_cell(ctx, "CommendationState", owners)
                + fu.cell_end(ctx))
    return [
        ("1 both debriefings, the client's display-only", lambda: fu.cell_debriefs(ctx)),
        ("2 the client's chain", lambda: fu.cell_chain(ctx, FOLLOWUP_CHAIN, False, "no follow-up")),
        ("3 the client's PromotionsState rows", promo_client),
        ("4 the client's CommendationState rows", medals_client),
        ("5 page-2 [Player] prefixes on both", lambda: fu.cell_page2(ctx, owners)),
        ("6 the host's rows; both on their geoscapes", host_rows),
    ]


def main():
    t0, results, ctx, pre = time.time(), {}, {"boot": "separate_followups"}, None
    crash0 = session._crash_log_snapshot()
    host = GameClient("host", 0, make_user_dir("campaign_followups_separate_host", mods=[fu.MEDAL_MOD]))
    client = GameClient("client", 0, make_user_dir("campaign_followups_separate_client", mods=[fu.MEDAL_MOD]))
    try:
        try:
            host.spawn(); client.spawn(); host.connect(); client.connect()
            stage(host, client, ctx)
        except Exception as e:
            pre = f"pre-cell (setup failure) {fu.short(e, 800)}"
        if pre is None:
            try:
                fu.procedure(types.SimpleNamespace(host=host, client=client), ctx, shared=False)
            except Exception as e:
                pre = f"procedure (the OKs and follow-up reads) raised {fu.short(e, 800)}"
        new_crash = sorted(session._crash_log_snapshot() - crash0)
        ctx["newCrashLogs"] = new_crash
        try:
            ctx["end"] = {"host": BES.view(host), "client": BES.view(client)}
        except Exception as e:
            ctx["end"] = f"probe failed: {fu.short(e)}"
        if pre:
            results["separate_followups"] = pre
        else:
            ctx["cells"] = fu.check_row("separate_followups", followup_cells(ctx), results)
        if new_crash:
            results["separate_followups"] = ((results["separate_followups"] + " | "
                                              if results["separate_followups"] else "")
                                             + f"new crash log(s): {new_crash}")
        fu.evidence("separate_followups", ctx)
        print("PASS separate_followups" if results["separate_followups"] is None
              else f"FAIL separate_followups: {results['separate_followups']}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[test_campaign_followups_separate] shutdown {gc.name}: {fu.short(e)}", flush=True)
    ok = results.get("separate_followups", "missing") is None
    print(f"\ntest_campaign_followups_separate: {1 if ok else 0}/1 passed (pass={['separate_followups'] if ok else []} "
          f"fail={[] if ok else ['separate_followups']}) in {time.time() - t0:.1f}s", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
