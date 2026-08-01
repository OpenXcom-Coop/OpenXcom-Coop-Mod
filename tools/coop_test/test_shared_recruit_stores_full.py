"""Repro: a FULL general store must not block recruiting personnel.

Reported bug: "if general stores are full you cannot recruit scientists /
soldiers / engineers, even if there is space in the living quarters."

ROOT CAUSE (SHARED co-op path) - src/CoopMod/SharedEcon.cpp:379

    if (base->storesOverfull(storeAdd)) { failReason = "STR_NOT_ENOUGH_STORE_SPACE"; return false; }

`buyValidate` accumulates `storeAdd` ONLY for TRANSFER_ITEM rows (SharedEcon.cpp:339);
a scientist / engineer / soldier row adds to `quartersAdd`, never to `storeAdd`, so
for a personnel-only hire `storeAdd == 0.0`. But `Base::storesOverfull(0.0)`
(Base.cpp:1083) returns true whenever the base is ALREADY at/over store capacity -
so the host rejects the hire with STR_NOT_ENOUGH_STORE_SPACE even though the hire
needs zero store space and quarters are free. (Contrast the transfer validator at
SharedEcon.cpp:773, which correctly gates its storesOverfull check behind both
`Options::storageLimitsEnforced` AND a non-zero store delta.)

The interactive gate in PurchaseState::increaseByValue is already correct -
personnel are gated only by quarters (PurchaseState.cpp:1314); the bad gate is the
host-side shared validator, so this only reproduces in a SHARED campaign.

WHAT THIS TEST ASSERTS (the CORRECT, post-fix behavior):
  * fill the shared base's general stores PAST capacity, leaving quarters free;
  * hire one soldier, one scientist, one engineer into that base;
  * each hire must be ACCEPTED (host applies it, no shared_fail).

On the CURRENT (buggy) code this test FAILS: every personnel hire comes back as
shared_fail 'STR_NOT_ENOUGH_STORE_SPACE'. That failure IS the repro. Once
SharedEcon.cpp:379 is fixed the three hires apply and the test passes.

Run:  python tools/coop_test/test_shared_recruit_stores_full.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
import session

# TransferType enum (src/Savegame/Transfer.h):
#   TRANSFER_ITEM=0 CRAFT=1 SOLDIER=2 SCIENTIST=3 ENGINEER=4
T_SOLDIER, T_SCIENTIST, T_ENGINEER = 2, 3, 4

SOLDIER = "STR_SOLDIER"
FILLER_ITEM = "STR_RIFLE"   # cheap, storable; size > 0 so a big pile overfills stores
FILLER_COUNT = 5000         # 5000 * rifle-size >> a fresh base's ~50 store units
STORE_FAIL = "STR_NOT_ENOUGH_STORE_SPACE"


def _report(gc, base=None):
    req = {"cmd": "base_report"}
    if base:
        req["base"] = base
    return gc.ok(req)


def _stats(gc):
    return gc.ok({"cmd": "shared_stats"})


def _free_quarters(gc, base=None):
    r = _report(gc, base)
    return r["availableQuarters"] - r["usedQuarters"], r


def _fill_stores(host, client):
    """Overfill the (index-0) shared base's general stores on BOTH machines - item
    COUNTS are part of the SHARED world checksum, so a host-only fill would desync
    and get auto-repaired away (the give_items idiom, see test_shared_commerce)."""
    for gc in (host, client):
        gc.ok({"cmd": "give_items", "item": FILLER_ITEM, "count": FILLER_COUNT})


def _attempt_hire(host, client, label, send):
    """Reset the SHARED protocol counters, fire one personnel hire from the client,
    and classify the host's answer: ('apply', None) = accepted, ('fail', reason) =
    rejected. Returns the classification (raises only on a genuine no-answer hang)."""
    for gc in (host, client):
        gc.ok({"cmd": "shared_reset_stats"})
    send()

    def outcome():
        s = _stats(client)
        if s["failCount"] >= 1:
            return ("fail", s["lastFail"])
        if s["applyCount"] >= 1:
            return ("apply", None)
        return None

    res = client.wait_for(f"host answered the {label} hire",
                          outcome, timeout=30, interval=0.5)
    # a rejection raises a CoopState popup on the initiating client - clear it so
    # the next attempt starts from a clean state stack.
    if res[0] == "fail":
        try:
            client.ok({"cmd": "coop_dialog_back"})
        except Exception:
            pass
    return res


def main():
    js = shared_fixture.bring_up("jrecruit", (48730, 48731, 48030))
    host, client = js.host, js.client
    try:
        base = _report(host)["name"]   # index-0 shared base (host's first base)

        # ---- preconditions --------------------------------------------------
        free0, r0 = _free_quarters(host, base)
        assert free0 >= 3, (
            f"setup: need >=3 free living-quarters at {base} to hire 3 people, "
            f"have {free0} (used={r0['usedQuarters']} avail={r0['availableQuarters']})")

        _fill_stores(host, client)

        # stores are now genuinely OVER capacity, and quarters are still free -
        # exactly the reported situation.
        for who, gc in (("host", host), ("client", client)):
            rr = _report(gc, base)
            assert rr["usedStores"] > rr["availableStores"], (
                f"setup: {who} stores not overfull "
                f"(used={rr['usedStores']} avail={rr['availableStores']})")
        free1, r1 = _free_quarters(host, base)
        assert free1 >= 3, f"setup: quarters no longer free after fill: {free1}"
        print(f"PASS setup: {base} stores OVERFULL "
              f"(used={r1['usedStores']}>avail={r1['availableStores']}), "
              f"{free1} living-quarters free")

        # ---- the hires: each must be ACCEPTED despite full stores -----------
        attempts = [
            ("soldier", lambda: client.ok(
                {"cmd": "buy", "item": SOLDIER, "count": 1, "kind": "soldier"})),
            ("scientist", lambda: client.ok(
                {"cmd": "shared_cmd", "jcmd": "buy", "baseId": 0,
                 "payload": {"items": [{"type": T_SCIENTIST, "rule": "", "qty": 1}]}})),
            ("engineer", lambda: client.ok(
                {"cmd": "shared_cmd", "jcmd": "buy", "baseId": 0,
                 "payload": {"items": [{"type": T_ENGINEER, "rule": "", "qty": 1}]}})),
        ]

        blocked = []
        for label, send in attempts:
            kind, reason = _attempt_hire(host, client, label, send)
            if kind == "apply":
                print(f"PASS {label}: hire accepted despite full stores")
            elif kind == "fail" and reason == STORE_FAIL:
                blocked.append(label)
                print(f"BUG  {label}: hire REJECTED '{reason}' with {free1} free quarters")
            else:
                raise AssertionError(
                    f"{label}: unexpected hire outcome kind={kind!r} reason={reason!r}")

        assert not blocked, (
            "BUG REPRODUCED - a full general store blocks personnel recruiting: "
            f"{blocked} rejected '{STORE_FAIL}' although {free1} living-quarters were "
            "free (SharedEcon.cpp:379 runs storesOverfull() on a zero-store hire)")

        # post-fix only: the three hires landed, the shared world is still one.
        js.finish()
        print("ALL RECRUIT-WITH-FULL-STORES TESTS PASSED")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
