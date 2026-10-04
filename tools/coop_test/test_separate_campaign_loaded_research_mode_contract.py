"""Loaded Separate saves must rebuild the selected research mode safely."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    saved = (ROOT / "src/Savegame/SavedGame.cpp").read_text(encoding="utf-8")
    start = saved.index("void SavedGame::setSeparateResearchSharingEnabled(")
    end = saved.index("bool SavedGame::isResearchedForPlayer(", start)
    body = saved[start:end]

    # The transient mode flag resets on load, so initialization must not return
    # early merely because its default already equals the requested OFF value.
    assert "isResearchSharingEnabled() == enabled" not in body
    assert "for (const auto* rule : _discovered)" in body
    assert "_separateCampaign.addCompletedResearch(player.first, rule->getName())" in body
    assert "for (const auto& player : _separateCampaign.getPlayers())" in body
    assert "_discovered.push_back(rule)" in body

    # An authoritative in-memory world load replaces SavedGame. The negotiated
    # mode must be restored immediately, rather than waiting for another lobby
    # handshake or a manual save/reload cycle.
    load = (ROOT / "src/Menu/LoadGameState.cpp").read_text(encoding="utf-8")
    adopt = load[load.index("_game->setSavedGame(s);"):]
    policy = adopt.index("setSeparateResearchSharingEnabled(")
    ownership = adopt.index("refreshSeparateBaseOwnership()")
    assert 'if (!_coopKey.empty()' in adopt
    assert "s->getCampaignType() == CoopCampaignType::Separate" in adopt
    assert "_game->getCoopMod()->_enable_research_sync" in adopt
    assert policy < ownership

    event = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    receive = event[event.index('state == "separate_geoscape_event"'):]
    receive = receive[:receive.index('state == "separate_apply"')]
    assert "setSeparateResearchSharingEnabled(" in receive
    assert "_enable_research_sync" in receive

    print("PASS loaded Separate saves rebuild private/shared research without losing discoveries")


if __name__ == "__main__":
    main()
