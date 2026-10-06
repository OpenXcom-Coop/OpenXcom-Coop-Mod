"""Static guards for Separate player-scoped Base Info and Monthly Costs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    costs = (ROOT / "src/Basescape/MonthlyCostsState.cpp").read_text(encoding="utf-8")
    report = (ROOT / "src/Geoscape/MonthlyReportState.cpp").read_text(encoding="utf-8")
    info = (ROOT / "src/Basescape/BaseInfoState.cpp").read_text(encoding="utf-8")

    assert "int localPlayerMaintenance(Game* game)" in econ
    assert "base->isOwnedByPlayer(playerName)" in econ
    assert "SeparateEcon::localPlayerMaintenance(_game)" in costs
    assert "getPlayerIncomeShare" in costs
    assert "SeparateEcon::localPlayerMaintenance(_game)" in report
    assert "const int displayedSoldiers = connectionTCP::isSeparateCampaignStatic()" in info
    assert "_base->getSoldiers()->size()" in info
    assert "keep the reservation in Used Quarters" in info
    print("PASS Separate costs contract: resident roster display and local-owner "
          "income/maintenance presentation remain isolated")


if __name__ == "__main__":
    main()
