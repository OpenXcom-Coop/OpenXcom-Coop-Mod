"""Separate feeds soldiers to normal craft deployment in Shared roster order."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "src/Battlescape/BattlescapeGenerator.cpp"


def main():
    text = GENERATOR.read_text(encoding="utf-8")
    assert "std::vector<Soldier*> deploymentSoldiers;" in text
    assert "std::vector<Soldier*> hostSoldiers;" in text
    assert "std::vector<Soldier*> clientSoldiers;" in text
    host_first = "deploymentSoldiers.push_back(hostSoldiers[i]);"
    client_second = "deploymentSoldiers.push_back(clientSoldiers[i]);"
    assert text.index(host_first) < text.index(client_second)
    assert text.count("for (auto* soldier : deploymentSoldiers)") == 3
    assert "leftHalf" not in text and "splitSeparate" not in text
    print("PASS Separate craft order contract: host/client soldiers alternate like "
          "Shared and the craft rules retain complete placement authority")


if __name__ == "__main__":
    main()
