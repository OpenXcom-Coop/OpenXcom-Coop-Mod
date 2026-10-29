"""ROSIGMA private research trees remain sane while both players progress.

Runs both a same-faction and a different-faction Separate Campaign. In each
campaign the host owner and client owner complete two projects each. After every
completion, both process replicas are checked through the exact research-list
query used by the UI (including its debug-mode parameter).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shared_fixture
from test_separate_campaign_three_month_factions import MOD_40K, MOD_ROSIGMA


BASE_OWNER = {"HostBase": "HostPlayer", "ClientBase": "ClientPlayer"}


def research_result(gc, base, consider_debug):
    return gc.ok({
        "cmd": "available_research",
        "base": base,
        "considerDebugMode": consider_debug,
    })


def assert_sane_matrix(js, label):
    snapshots = {}
    for base in BASE_OWNER:
        normal_host = research_result(js.host, base, False)
        ui_host = research_result(js.host, base, True)
        normal_client = research_result(js.client, base, False)
        ui_client = research_result(js.client, base, True)

        assert not ui_host["debugMode"], f"{label}: host strategic debug mode enabled"
        assert not ui_client["debugMode"], f"{label}: client strategic debug mode enabled"
        assert ui_host["topics"] == normal_host["topics"], {
            "label": label, "process": "host", "base": base,
            "normal": normal_host["topics"], "ui": ui_host["topics"]}
        assert ui_client["topics"] == normal_client["topics"], {
            "label": label, "process": "client", "base": base,
            "normal": normal_client["topics"], "ui": ui_client["topics"]}
        assert set(ui_host["topics"]) == set(ui_client["topics"]), {
            "label": label, "base": base,
            "hostReplica": ui_host["topics"], "clientReplica": ui_client["topics"]}
        snapshots[base] = list(ui_host["topics"])
    return snapshots


def complete_on_both_replicas(js, base, topic):
    # The live game applies an authoritative completion to both replicas. This
    # deterministic hook drives the same SavedGame completion/side-effect path
    # on each copy without waiting days or depending on ROSIGMA research costs.
    host_result = js.host.ok({
        "cmd": "separate_research_side_effects", "base": base, "topic": topic})
    client_result = js.client.ok({
        "cmd": "separate_research_side_effects", "base": base, "topic": topic})
    assert host_result["topic"] == client_result["topic"] == topic, {
        "host": host_result, "client": client_result}
    expected_owner = BASE_OWNER[base]
    assert host_result["baseOwnerPlayerName"] == expected_owner, host_result
    assert client_result["baseOwnerPlayerName"] == expected_owner, client_result


def run_case(tag, ports, host_faction, client_faction):
    js = shared_fixture.bring_up(
        tag, ports, mods=(MOD_40K, MOD_ROSIGMA), campaign_mode="coop",
        host_difficulty=host_faction, client_difficulty=client_faction,
        transport="tcp")
    try:
        js.host.ok({"cmd": "set_option", "name": "EnableResearchSync", "value": False})
        trees = assert_sane_matrix(js, f"{tag} initial")

        if host_faction == client_faction:
            assert set(trees["HostBase"]) == set(trees["ClientBase"]), trees

        completed = {"HostBase": [], "ClientBase": []}
        for base in ("HostBase", "ClientBase"):
            for number in range(2):
                current = assert_sane_matrix(js, f"{tag} before {base} research {number + 1}")
                candidates = [topic for topic in current[base]
                              if topic not in completed[base]]
                assert candidates, {
                    "case": tag, "base": base, "completed": completed[base],
                    "available": current[base]}
                topic = candidates[0]
                complete_on_both_replicas(js, base, topic)
                completed[base].append(topic)
                assert_sane_matrix(js, f"{tag} after {base} completed {topic}")

        print(
            f"PASS {tag}: host and client completed two private projects each; "
            "both research-tree replicas stayed filtered and consistent")
    finally:
        js.shutdown()


def main():
    for path in (MOD_40K, MOD_ROSIGMA):
        if not os.path.isdir(path):
            raise SystemExit(f"required mod directory not found: {path}")

    run_case("sep_rosigma_same_faction_progression", (49046, 49047, 48346), 0, 0)
    run_case("sep_rosigma_different_faction_progression", (49048, 49049, 48348), 0, 1)
    print("ALL ROSIGMA PRIVATE RESEARCH TREE PROGRESSION TESTS PASSED")


if __name__ == "__main__":
    main()
