"""Contract for the ROSIGMA two-project-per-player research-tree test."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    test = (ROOT / "tools/coop_test/test_separate_campaign_research_tree_progression.py").read_text(encoding="utf-8")
    server = (ROOT / "src/CoopMod/TestServer.cpp").read_text(encoding="utf-8")

    assert 'host_difficulty=host_faction' in test
    assert 'client_difficulty=client_faction' in test
    assert test.count('run_case(') >= 3  # definition + same + different
    assert 'for number in range(2)' in test
    assert 'for base in ("HostBase", "ClientBase")' in test
    assert '"considerDebugMode": consider_debug' in test
    assert 'ui_host["topics"] == normal_host["topics"]' in test
    assert 'ui_client["topics"] == normal_client["topics"]' in test
    assert 'set(ui_host["topics"]) == set(ui_client["topics"])' in test
    assert 'req.get("considerDebugMode", false).asBool()' in server
    assert 'cmd == "separate_research_side_effects"' in server
    print("PASS ROSIGMA same/different-faction research progression coverage contract")


if __name__ == "__main__":
    main()
