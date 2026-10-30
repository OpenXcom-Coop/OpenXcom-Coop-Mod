"""Minimal vanilla control for Separate Campaign TCP bring-up.

Uses the same shared_fixture/session path as the ROSIGMA three-month test, but
loads no extra mods.  This isolates transport/bootstrap failures from mod load.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture


def main():
    js = shared_fixture.bring_up(
        "sep_tcp_vanilla", (48986, 48987, 48286),
        campaign_mode="coop", host_base="HostBase", client_base="ClientBase")
    try:
        host_state = js.host.ok({"cmd": "get_coop"})
        client_state = js.client.ok({"cmd": "get_coop"})
        assert host_state.get("coopCampaign") is True, host_state
        assert client_state.get("coopCampaign") is True, client_state
        assert host_state.get("onConnect") == 1, host_state
        assert client_state.get("onConnect") == 1, client_state
        print("PASS vanilla Separate Campaign TCP session reached geoscape")
    finally:
        js.shutdown()


if __name__ == "__main__":
    main()
