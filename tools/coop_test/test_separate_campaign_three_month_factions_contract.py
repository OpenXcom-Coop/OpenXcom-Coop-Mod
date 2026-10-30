"""Static wiring contract for the mod-loaded three-month faction harness."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    server = (ROOT / "src/CoopMod/TestServer.cpp").read_text(encoding="utf-8")
    newgame = (ROOT / "src/Menu/NewGameState.cpp").read_text(encoding="utf-8")
    session = (ROOT / "tools/coop_test/session.py").read_text(encoding="utf-8")
    harness = (ROOT / "tools/coop_test/harness.py").read_text(encoding="utf-8")
    runtime = (ROOT / "tools/coop_test/test_separate_campaign_three_month_factions.py").read_text(encoding="utf-8")
    assert 'cmd == "separate_faction_mission_state"' in server
    assert 'req.isMember("difficulty")' in server
    assert server.count('req.isMember("campaign")') >= 4
    assert "harnessSelectDifficulty" in newgame
    assert "host_difficulty=None, client_difficulty=None" in session
    assert 'metadata = os.path.join(src, "metadata.yml")' in harness
    assert "mod_id = match.group(1)" in harness
    assert '"set_ending", "ending": 0' in runtime
    assert "range(1, 4)" in runtime
    assert '"HostPlayer" in seen_owners' in runtime
    assert '"ClientPlayer" in seen_owners' in runtime
    print("PASS three-month Separate faction harness wiring")


if __name__ == "__main__":
    main()
