"""Every multiplayer option is wired to its intended gameplay gate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    options = read("src/Engine/Options.cpp")
    tcp = read("src/CoopMod/connectionTCP.cpp")
    menu = read("src/CoopMod/OptionsMultiplayer.cpp")
    host_menu = read("src/CoopMod/HostMenu.cpp")
    walk = read("src/Battlescape/UnitWalkBState.cpp")
    craft = read("src/Savegame/Craft.cpp")

    ids = (
        "EnableHostOnlyTimeSpeed", "EnableResearchSync",
        "UnbalancedCraftSoldiersLimit", "EnableReactionFirePvp",
        "EnableOtherPlayerFootsteps", "EnableXcomEquipmentAliensPVP",
    )
    for option in ids:
        assert option in options, option
        assert option in menu, option
    # Reaction fire on a walk in PvP: UnitWalkBState asks the battle code, which reads the host's option.
    assert "!coopPvpWalkReactionOff()" in walk
    assert "&& !connectionTCP::_enable_reaction_shoot;" in tcp
    # The other player's footsteps: every walk sound goes through one gate that reads the option.
    assert "coopWalkSoundSilenced(_unit, _action.sneak, false)" in walk
    assert "!coopWalkSoundSilenced(actor, action.sneak, true)" in tcp
    assert "!connectionTCP::_enable_other_player_footsteps" in tcp
    # X-COM equipment for the aliens in PvP: the pre-battle equip rule reads the option.
    assert "&& connectionTCP::_enable_xcom_equipment_aliens_pvp;" in tcp
    assert '_unbalanced_craft_soldiers_limit == true' in craft
    # The turn mode is the host's lobby choice, not a multiplayer menu option. Every battle offer
    # carries it and the client takes the offer's value for that battle.
    assert '"CoopTurnMode", &CoopTurnMode' in options
    assert "CoopTurnMode" not in menu
    assert "coopSessionTurnModeFromOptions()" in host_menu
    assert 'offer["turnMode"] = coopTurnModeName(mode);' in tcp
    assert 'g_pendingClient.turnMode = offer.get("turnMode", "").asString();' in tcp
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
