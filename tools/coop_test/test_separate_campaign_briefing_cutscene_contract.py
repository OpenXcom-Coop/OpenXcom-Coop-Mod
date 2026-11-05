"""Regression guards for one host-sent Separate briefing cutscene."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    briefing = (ROOT / "src/Battlescape/BriefingState.cpp").read_text(
        encoding="utf-8")
    init = briefing.split("void BriefingState::init()", 1)[1].split(
        "void BriefingState::loadCoop()", 1)[0]

    assert "isSeparateCampaign()" in init
    assert "getServerOwner()" in init
    assert "playHere = _game->getCoopMod()->getServerOwner()" in init
    assert "allow_cutscene = true" in init
    assert "if (playHere)" in init
    assert '_cutsceneId = ""' in init

    print("PASS Separate briefing cutscene is created once by the server host")


if __name__ == "__main__":
    main()
