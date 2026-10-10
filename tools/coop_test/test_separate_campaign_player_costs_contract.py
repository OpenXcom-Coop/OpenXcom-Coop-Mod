"""Static guards for Separate player-scoped Base Info and Monthly Costs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    econ = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    costs = (ROOT / "src/Basescape/MonthlyCostsState.cpp").read_text(encoding="utf-8")
    report = (ROOT / "src/Geoscape/MonthlyReportState.cpp").read_text(encoding="utf-8")
    info = (ROOT / "src/Basescape/BaseInfoState.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")

    assert "int localPlayerMaintenance(Game* game)" in econ
    assert "int playerMaintenance(Game* game, const std::string& playerName)" in econ
    assert "base->isOwnedByPlayer(playerName)" in econ
    assert "SeparateEcon::playerMaintenance(" in costs
    assert "_base->getOwnerPlayerName()" in costs
    assert "localPlayerMaintenanceBonus" not in costs
    assert "getCountryFunding()" in costs
    assert "getPlayerIncomeShare" not in costs
    assert "SeparateEcon::localPlayerMaintenance(_game)" in report
    assert "localPlayerMaintenanceBonus" not in report
    assert "getPlayerIncomeShare" not in report
    assert "_txtPlayerBonus" not in report
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    assert "getSeparatePlayerMaintenanceBonus" not in saved
    assert "int baseMaintenance = getBaseMaintenance();" in saved
    assert "_separateCampaign.getPlayerFunds(playerName)" in saved
    assert "const int64_t normalNet = countryFunding - playerMaintenance;" in saved
    assert "normalNet / static_cast<int64_t>(_coopPlayers.size())" in saved
    assert "const int64_t playerCosts = normalNet - balanceDelta;" in saved
    assert "_separatePlayerCosts[playerName] = playerCosts;" in saved
    assert "playerFunds->back() += balanceDelta;" in saved
    assert "base->isOwnedByPlayer(playerName)" in saved
    separate_con = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    assert 'playerReader.tryRead("funds", player.funds)' in separate_con
    assert 'playerWriter.write("funds", entry.second.funds)' in separate_con
    assert "lastPlayerCosts" not in separate_con
    assert 'tr("STR_PLAYERS_COSTS")' in report
    assert "_txtPlayerCosts->setY(49);" in report
    assert "_txtBonus->setY(57);" in report
    assert "_txtDesc->setY(57);" in report
    assert "_txtDesc->setY(65);" in report
    assert "for (const std::string& playerName : save->getCoopPlayers())" in geo
    assert "playerBase->getMonthlyMaintenace()" in geo
    assert "playerBase->getPersonnelMaintenance()" in geo
    assert "save->setSeparateFundsContext(playerName);" in geo
    assert "(save->getFunds() - ownInitialCosts) / playerCount" in geo
    assert "separateMonthlyPlayerFunds" in geo
    assert "player->funds.push_back(value.asInt64())" in geo
    assert "if (_game->getCoopMod()->isSharedCampaign()" in geo
    monthly_report = (ROOT / "src/Geoscape/MonthlyReportState.cpp").read_text(encoding="utf-8")
    assert 'root["separatePlayerFunds"] = playerFunds;' in monthly_report
    assert "const int displayedSoldiers = connectionTCP::isSeparateCampaignStatic()" in info
    assert "_base->getSoldiers()->size()" in info
    assert "keep the reservation in Used Quarters" in info
    basescape = (ROOT / "src/Basescape/BasescapeState.cpp").read_text(encoding="utf-8")
    mini = (ROOT / "src/Basescape/MiniBaseView.cpp").read_text(encoding="utf-8")
    assert "getSeparatePlayerFunds(" in basescape
    assert "_base->getOwnerPlayerName()" in basescape
    assert "own bases fill the left-hand slots" in mini
    assert "if (_bases->at(i) && !_bases->at(i)->_isForeignBase)" in mini
    assert "if (_bases->at(i) && _bases->at(i)->_isForeignBase)" in mini
    assert "_displaySlots[slot]" in mini
    print("PASS Separate costs contract: full income, local-owner maintenance, "
          "no Player Bonus, and divided own-base opening balance")


if __name__ == "__main__":
    main()
