"""Separate completion popups must follow its private/shared research policy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    tcp = (ROOT / "src/CoopMod/connectionTCP.cpp").read_text(encoding="utf-8")
    separate = (ROOT / "src/CoopMod/SeparateEcon.cpp").read_text(encoding="utf-8")
    shared = (ROOT / "src/CoopMod/SharedEcon.cpp").read_text(encoding="utf-8")

    handler = tcp[tcp.index("void connectionTCP::onTCPMessage"):]
    assert handler.index("SeparateEcon::onMessage") < handler.index("SharedEcon::onMessage")

    separate_handler = separate[separate.index("bool onMessage("):]
    assert 'state == "separate_apply"' in separate_handler
    assert "refreshSeparateBaseOwnership()" in separate_handler
    assert "return false;" in separate_handler

    research_apply = shared[shared.index("void researchDoneApply("):]
    research_apply = research_apply[:research_apply.index("void facDoneApply(")]
    assert "SeparateEcon::showResearchCompletion(game, base)" in research_apply

    policy = separate[separate.index("bool showResearchCompletion("):]
    policy = policy[:policy.index("bool allowsForeignBaseCommand(")]
    assert "_enable_research_sync || !base->_isForeignBase" in policy

    alert_apply = shared[shared.index("void alertApply("):]
    alert_apply = alert_apply[:alert_apply.index("void researchDoneApply(")]
    for popup in (
        "ResearchRequiredState",
        "NewPossibleResearchState",
        "NewPossibleManufactureState",
        "NewPossiblePurchaseState",
        "NewPossibleCraftState",
        "NewPossibleFacilityState",
    ):
        assert f'cls == "{popup}"' in alert_apply
    assert "researchUnlockAlert && !SeparateEcon::showResearchCompletion(game, base)" in alert_apply

    print("PASS Separate completion and unlock popups follow shared/private research policy")


if __name__ == "__main__":
    main()
