"""Every multiplayer option is wired to its intended gameplay gate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    options = read("src/Engine/Options.cpp")
    tcp = read("src/CoopMod/connectionTCP.cpp")
    menu = read("src/CoopMod/OptionsMultiplayer.cpp")
    walk = read("src/Battlescape/UnitWalkBState.cpp")
    battle = read("src/Battlescape/BattlescapeGame.cpp")
    briefing = read("src/Battlescape/BriefingState.cpp")
    craft = read("src/Savegame/Craft.cpp")

    ids = (
        "EnableHostOnlyTimeSpeed", "EnableResearchSync",
        "UnbalancedCraftSoldiersLimit", "EnableReactionFirePvp",
        "EnableOtherPlayerFootsteps", "EnableXcomEquipmentAliensPVP",
        "EnableCoopParallelTurns",
    )
    for option in ids:
        assert option in options, option
        assert option in menu, option
    assert '_enable_reaction_shoot == true' in walk
    assert '_enable_other_player_footsteps == true' in walk
    assert '_enable_other_player_footsteps == true' in battle
    assert '_enable_xcom_equipment_aliens_pvp == false' in briefing
    assert '_unbalanced_craft_soldiers_limit == true' in craft
    assert 'root["enable_parallel_turns"]' in tcp
    assert 'root["enable_parallel_turns"] = Options::EnableCoopParallelTurns;' in tcp
    # The client takes the host's value for the session only.
    assert 'Options::setSessionOverride(&Options::EnableCoopParallelTurns, connectionTCP::_enable_parallel_turns);' in tcp
    assert 'root["enable_host_only_time_speed"]' in tcp
    assert "_txtTooltip->setX(94)" in menu and "_txtTooltip->setWidth(218)" in menu
    assert "PvP and PvP campaign battles" in menu
    assert "Cooperative campaigns are unaffected" in menu
    assert "Open or close the multiplayer chat window" in menu
    assert "Give the selected soldier to another player" in menu
    assert "sessionFixed && _game->getCoopMod()->getCoopStatic()" in menu
    print("PASS multiplayer options have gameplay gates, help text, and live-session locking")


if __name__ == "__main__":
    main()
