"""Fresh Separate clients must choose their own difficulty/faction."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    state_h = (ROOT / "src/Menu/NewGameState.h").read_text(encoding="utf-8")
    state_cpp = (ROOT / "src/Menu/NewGameState.cpp").read_text(encoding="utf-8")
    session = (ROOT / "tools/coop_test/session.py").read_text(encoding="utf-8")

    start = tcp.index('stateString == "campaign_start"')
    end = tcp.index('stateString == "campaign_resume"', start)
    campaign_start = tcp[start:end]
    assert 'activeMaster == "xcom1" || activeMaster == "xcom2"' in campaign_start
    assert "&& !vanillaCampaign" in campaign_start
    selector = campaign_start.index(
        "new NewGameState(true, CoopCampaignType::Separate")
    inherited_save = campaign_start.index(
        "SavedGame* save = _game->getMod()->newSave((GameDifficulty)difficulty)")
    assert selector < inherited_save
    assert "return;" in campaign_start[selector:inherited_save]

    assert "bool _clientSeparateStart" in state_h
    assert "const std::vector<std::string>& coopPlayers" in state_h
    assert "if (_clientSeparateStart)" in state_cpp
    assert "beginInitialBasePlacement(_game, gs, base)" in state_cpp
    assert 'client.wait_for("client difficulty"' not in session

    print("PASS modded Separate clients choose faction; vanilla xcom1/xcom2 skip the extra dialog")


if __name__ == "__main__":
    main()
