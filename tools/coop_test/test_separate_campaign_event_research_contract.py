"""Mod events must replicate their host-selected Shared Research outcome."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    separate = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    geo = (ROOT / "src/Geoscape/GeoscapeState.cpp").read_text(encoding="utf-8")

    host = separate[separate.index("void hostGeoscapeEvent("):]
    assert "isSeparateCampaign()" in host
    assert "_enable_research_sync" in host
    assert "getDiscoveredResearch()" in host
    assert 'msg["state"] = "separate_geoscape_event"' in host
    assert 'msg["discoveredResearch"] = discovered' in host
    assert "resolvedResearchName = researchName" in host
    assert "eventRule->getResearchList()" in host
    assert 'msg["researchName"] = resolvedResearchName' in host
    assert 'msg["bonusResearchName"] = bonusResearchName' in host

    apply = separate[separate.index('state == "separate_geoscape_event"'):]
    apply = apply[:apply.index('state == "separate_apply"')]
    adopt = apply.index('obj["discoveredResearch"]')
    popup = apply.index("new GeoscapeEventState")
    assert adopt < popup
    assert "!candidate->_isForeignBase" in apply
    assert "addFinishedResearch(" in apply
    assert "addFinishedResearchSimple(rule)" not in apply

    # Adopting the host's discovered list before constructing the event prevents
    # the replica from rolling a different random reward. The replica never
    # re-runs the vanilla side effects (removed projects, spawned items and
    # events, counters): they roll its own RNG, so the host sends its results
    # instead (research_effects, world_extras and the event's rewards).
    finish = apply.index("addFinishedResearch(")
    assert finish < popup
    assert "handlePrimaryResearchSideEffects(" not in apply
    rewards = apply.index("applyEventRewards(")
    assert rewards < popup
    assert "adoptedArticle" in apply
    assert "if (article.empty()) article = adoptedArticle" in apply
    restore = apply.index("setReplicatedResearchNames")
    queue = apply.index("gs->popup(eventState)")
    assert popup < restore < queue
    assert "SeparateEcon::hostGeoscapeEvent" in geo

    event_h = (ROOT / "src/Geoscape/GeoscapeEventState.h").read_text(encoding="utf-8")
    assert "getResearchName()" in event_h
    assert "getBonusResearchName()" in event_h
    assert "setReplicatedResearchNames" in event_h

    event_cpp = (ROOT / "src/Geoscape/GeoscapeEventState.cpp").read_text(encoding="utf-8")
    ufopaedia = (ROOT / "src/Ufopaedia/Ufopaedia.cpp").read_text(encoding="utf-8")
    assert "Ufopaedia::openReplicatedEventArticle" in event_cpp
    forced = ufopaedia[ufopaedia.index("bool Ufopaedia::openReplicatedEventArticle"):]
    assert "state->articleList.push_back(article)" in forced
    assert "game->pushState(createArticleState(std::move(state)))" in forced

    print("PASS Separate mod events replicate research state and Ufopaedia article names")


if __name__ == "__main__":
    main()
