"""Contract for settling same-faction private research at month zero."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")
    separate_h = (ROOT / "src/CoopMod/SeparateCon.h").read_text(encoding="utf-8")
    separate_cpp = (ROOT / "src/CoopMod/SeparateCon.cpp").read_text(encoding="utf-8")
    assert "coopFile->getSeparateCampaign().getPlayer(owner)" in tcp
    assert "replaceCompletedResearch(owner, clientProfile->completedResearch)" in tcp
    assert "separate.setFactionResearch(owner, clientFactionResearch)" in tcp
    assert "determineAlienMissions();" in geo
    settled = geo.index("// Private Separate research must still start identically")
    streamed = geo.index("streamSharedWorldToClient()", settled)
    assert settled < streamed
    assert "peerProfile->faction == hostProfile->faction" in geo[settled:streamed]
    assert "replaceCompletedResearch(players[i], hostProfile->completedResearch)" in geo[settled:streamed]
    assert "replaceCompletedResearch" in separate_h
    assert "_players[playerName].completedResearch = research" in separate_cpp
    print("PASS same-faction private research baseline settles before first world stream")


if __name__ == "__main__":
    main()
