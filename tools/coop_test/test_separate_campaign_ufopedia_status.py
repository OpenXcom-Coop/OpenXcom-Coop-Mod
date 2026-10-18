"""Separate Campaign Ufopaedia read/hidden marks are player-scoped and persisted host-side."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import separate_campaign_fixture as fixture


RULE = "STR_MEDI_KIT"


def status(gc):
    return gc.ok({"cmd": "separate_ufopedia_status", "rule": RULE})


def main():
    js = fixture.bring_up("sep_ufopedia_status", (49070, 49071, 48370))
    host, client = js.host, js.client
    try:
        assert status(host)["localStatus"] == 0
        assert status(client)["localStatus"] == 0

        changed = client.ok({"cmd": "separate_ufopedia_status",
                             "rule": RULE, "status": 1})
        assert changed["localStatus"] == 1, changed
        host.wait_for(
            "client Ufopaedia mark persisted on host",
            lambda: (lambda s: s if s["players"].get("ClientPlayer") == 1 else None)(
                status(host)),
            timeout=30,
        )
        host_view = status(host)
        assert host_view["localStatus"] == 0, host_view
        assert host_view["players"].get("HostPlayer") is None, host_view
        assert host_view["players"].get("ClientPlayer") == 1, host_view

        host_changed = host.ok({"cmd": "separate_ufopedia_status",
                                "rule": RULE, "status": 2})
        assert host_changed["localStatus"] == 2, host_changed
        final = status(host)["players"]
        assert final["HostPlayer"] == 2 and final["ClientPlayer"] == 1, final

        roundtrip = host.ok({"cmd": "separate_profile_roundtrip"})
        persisted = {p["name"]: p.get("ufopediaRuleStatus", {}).get(RULE)
                     for p in roundtrip["players"]}
        assert persisted == {"HostPlayer": 2, "ClientPlayer": 1}, persisted
        print("PASS Separate Ufopaedia: host/client marks remain independent, synced and serialized")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
