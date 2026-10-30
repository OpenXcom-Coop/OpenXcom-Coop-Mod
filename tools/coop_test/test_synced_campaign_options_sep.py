"""test_synced_campaign_options_sep.py (SEPARATE): row separate_join_values, the join takes the host's 14.

One table for every session kind, SEPARATE included: the host's value at join governs both players' own worlds for the
session.

ONE SEPARATE boot: session.new_campaign(campaign_mode="coop") on lobby key 47246, host user dir = HOST_OPTS, client =
defaults. OWN_FILE = each machine's options.cfg read after the bring-up, the 16 ids parsed.

| row | cell that fails without the fix |
|---|---|
| separate_join_values | client option_values of the 14 == the client defaults (not the host's); client own lacks the 14
|

Each row prints ONE "EVIDENCE <id>:" line then PASS/FAIL. Exit 0 only when every row passes, 2 otherwise; no exit 3, no
retry; run in the foreground to completion.

Run:  python tools/coop_test/test_synced_campaign_options_sep.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import GameClient, make_user_dir  # noqa: E402
import session  # noqa: E402

LOBBY_PORT = 47246                      # SEPARATE coop rendezvous
CTRL = (49244, 49245)                   # ephemeral control-socket LABELS

IDS14 = ["storageLimitsEnforced", "canSellLiveAliens", "fieldPromotions", "oxceAutomaticPromotions",
         "oxceWoundedDefendBaseIf", "aggressiveRetaliation", "allowBuildingQueue", "craftLaunchAlways",
         "anytimePsiTraining", "canTransferCraftsWhileAirborne", "retainCorpses",
         "oxceAlternateCraftEquipmentManagement", "oxceManualPromotions", "oxceGeoscapeEventsInstantDelivery"]
CONTROLS = ["oxceAutoSell", "oxcePersonalLayoutIncludingArmor"]
IDS16 = IDS14 + CONTROLS

HOST_OPTS = {"storageLimitsEnforced": True, "canSellLiveAliens": True, "fieldPromotions": True,
             "oxceAutomaticPromotions": False, "oxceWoundedDefendBaseIf": 50, "aggressiveRetaliation": True,
             "allowBuildingQueue": True, "craftLaunchAlways": True, "anytimePsiTraining": True,
             "canTransferCraftsWhileAirborne": True, "retainCorpses": True,
             "oxceAlternateCraftEquipmentManagement": True, "oxceManualPromotions": True,
             "oxceGeoscapeEventsInstantDelivery": False, "oxceAutoSell": True,
             "oxcePersonalLayoutIncludingArmor": False}
CLIENT_DEF = {"storageLimitsEnforced": False, "canSellLiveAliens": False, "fieldPromotions": False,
              "oxceAutomaticPromotions": True, "oxceWoundedDefendBaseIf": 100, "aggressiveRetaliation": False,
              "allowBuildingQueue": False, "craftLaunchAlways": False, "anytimePsiTraining": False,
              "canTransferCraftsWhileAirborne": False, "retainCorpses": False,
              "oxceAlternateCraftEquipmentManagement": False, "oxceManualPromotions": False,
              "oxceGeoscapeEventsInstantDelivery": True, "oxceAutoSell": False,
              "oxcePersonalLayoutIncludingArmor": True}
HOST_14 = {k: HOST_OPTS[k] for k in IDS14}
CDEF_14 = {k: CLIENT_DEF[k] for k in IDS14}

MENU_S = 60


def short(e):
    s = f"{type(e).__name__}: {e}"
    return s if len(s) <= 400 else s[:400] + "..."


def sos(gc):
    r = gc.cmd({"cmd": "synced_options_state"})
    return {k: v for k, v in r.items() if k not in ("ok", "advanced")}


def ov(gc, ids):
    return gc.cmd({"cmd": "option_values", "ids": ids}).get("values") or {}


def synced_chat(st):
    return [(m.get("player"), m.get("text")) for m in (st.get("chat") or [])
            if "changed" in (m.get("text") or "") and " to " in (m.get("text") or "")]


def norm(v):
    if v == "true":
        return True
    if v == "false":
        return False
    import re
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def read_cfg(gc):
    import re
    with open(os.path.join(gc.user_dir, "options.cfg"), "r", encoding="utf-8") as f:
        text = f.read()
    out = {}
    for i in IDS16:
        hits = re.findall(r"^\s*" + re.escape(i) + r":\s*(\S+)\s*$", text, re.M)
        out[i] = norm(hits[0]) if hits else None
    return out


def vdiff(a, b, ids):
    a, b = a or {}, b or {}
    return {k: (a.get(k), b.get(k)) for k in ids if a.get(k) != b.get(k)}


class Row:
    def __init__(self, rid):
        self.rid = rid
        self.fails, self.passed, self.ev = [], [], {}
        self.t0 = time.time()

    def cell(self, name, ok, detail=""):
        (self.passed if ok else self.fails).append(name if ok else f"{name}: {detail}")


def row_separate_join_values(r, host, client, own_file):
    hov, cov = ov(host, IDS14), ov(client, IDS14)
    hs, cs = sos(host), sos(client)
    r.ev.update(host_sos=hs, client_sos=cs, host_ov=ov(host, IDS16), client_ov=ov(client, IDS16), ownFile=own_file)
    # control: host reads its own HOST_OPTS.
    r.cell("host_boot", not vdiff(hov, HOST_14, IDS14), f"host option_values vs HOST_OPTS {vdiff(hov, HOST_14, IDS14)}")
    # FIX: client option_values of the 14 == host's; without the fix they are the client defaults.
    r.cell("join_values", not vdiff(cov, hov, IDS14), f"client vs host option_values {vdiff(cov, hov, IDS14)}")
    # FIX: client own holds the 14 == client defaults; without the fix own lacks the 14.
    own = cs.get("own") or {}
    r.cell("own_14", all(k in own for k in IDS14) and not vdiff(own, CDEF_14, IDS14),
           f"client own: missing {[k for k in IDS14 if k not in own]} diff {vdiff(own, CDEF_14, IDS14)}")
    # control: the join happened.
    r.cell("table_join", (cs.get("tablesApplied"), cs.get("lastTableFrom")) == (1, "join"),
           f"client tablesApplied {cs.get('tablesApplied')} lastTableFrom {cs.get('lastTableFrom')!r}")
    # control: no synced-option-change chat from the silent join.
    r.cell("chat_silent", not synced_chat(hs) and not synced_chat(cs),
           f"synced chat host {synced_chat(hs)} client {synced_chat(cs)}")
    # control: the per-player controls keep each machine's own boot value.
    hctrl, cctrl = ov(host, CONTROLS), ov(client, CONTROLS)
    r.cell("controls", not vdiff(hctrl, {k: HOST_OPTS[k] for k in CONTROLS}, CONTROLS)
           and not vdiff(cctrl, {k: CLIENT_DEF[k] for k in CONTROLS}, CONTROLS),
           f"controls host {hctrl} client {cctrl}")
    # guard: no shared value leaked to either options.cfg.
    d = {"host": vdiff(read_cfg(host), own_file.get("host"), IDS16),
         "client": vdiff(read_cfg(client), own_file.get("client"), IDS16)}
    r.cell("g_file", not d["host"] and not d["client"], f"options.cfg differs from OWN_FILE {d}")


def main():
    t0 = time.time()
    host = GameClient("host", CTRL[0], make_user_dir("synced_campaign_options_sep_host", options=HOST_OPTS))
    client = GameClient("client", CTRL[1], make_user_dir("synced_campaign_options_sep_client"))
    results = {}
    try:
        host.spawn()
        client.spawn()
        host.connect()
        client.connect()
        session.new_campaign(host, client, port=str(LOBBY_PORT), campaign_mode="coop")
        own_file = {"host": read_cfg(host), "client": read_cfg(client)}
        print(f"[synced_campaign_options_sep] bring-up {time.time() - t0:.1f}s OWN_FILE {own_file}", flush=True)
        r = Row("separate_join_values")
        try:
            row_separate_join_values(r, host, client, own_file)
        except Exception as e:
            r.cell("exception", False, short(e))
        r.ev["cellsPassed"] = r.passed
        r.ev["wallS"] = round(time.time() - r.t0, 1)
        print(f"EVIDENCE separate_join_values: {r.ev}", flush=True)
        if r.fails:
            results["separate_join_values"] = False
            print(f"FAIL separate_join_values: {len(r.fails)} cell(s): " + " | ".join(r.fails), flush=True)
        else:
            results["separate_join_values"] = True
            print("PASS separate_join_values", flush=True)
    except Exception as e:
        results["separate_join_values"] = False
        print(f"FAIL separate_join_values: pre (bring-up) {short(e)}", flush=True)
    finally:
        for gc in (host, client):
            try:
                gc.shutdown()
            except Exception as e:
                print(f"[synced_campaign_options_sep] shutdown {gc.name}: {short(e)}", flush=True)
    ok = results.get("separate_join_values") is True
    print(f"\ntest_synced_campaign_options_sep: {'1/1' if ok else '0/1'} passed in {time.time() - t0:.1f}s", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
