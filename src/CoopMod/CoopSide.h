#pragma once
#include <string>

namespace OpenXcom
{

class SavedGame;

/**
 * Sides in a two-player PvP campaign, and whether a PvP game mode plays on the host's one world.
 *
 * Game mode 2: the host plays X-COM and the client plays the aliens.
 * Game mode 3: the host plays the aliens and the client plays X-COM.
 * Every other mode (solo, co-op, both players on the aliens) has no alien player here.
 *
 * Helpers that take a save decide from CoopSide::gamemode(save); pass the save in hand, or nullptr.
 * This header does not include connectionTCP.h, so save-file code can use it.
 */
namespace CoopSide
{

/// True for the two PvP game modes (2 and 3).
bool isPvpMode(int gamemode);
/// True when the host plays the aliens (game mode 3).
bool hostPlaysAliens(int gamemode);

/// True when this PvP game mode plays on the host's one world. Off for both modes by default.
bool pvpOneWorldEnabled(int gamemode);
/// Turns the one-world layout of a PvP game mode on or off for this process (test commands only).
void setPvpOneWorldEnabled(int gamemode, bool enabled);
/// pvpOneWorldEnabled() for the game mode that decides @a save's rules.
bool pvpOneWorld(const SavedGame* save);

/// The game mode that decides @a save's rules: the save's own mode once that mode plays on one world,
/// else the session's mode.
int gamemode(const SavedGame* save);

/// True when roster seat @a seat (0 = the host) plays the aliens in @a gamemode.
bool seatPlaysAliens(int gamemode, int seat);
/// True when the roster player @a playerName plays the aliens. False for a name not in the roster.
bool playerPlaysAliens(const SavedGame* save, const std::string& playerName);
/// True when this machine's player plays the aliens.
bool thisMachinePlaysAliens(const SavedGame* save);
/// True when the other player plays the aliens.
bool peerPlaysAliens(const SavedGame* save);
/// True when this machine shows the alien player's Geoscape screens. While a mode keeps two worlds those
/// screens follow the mission role (connectionTCP::getHost()); on one world this equals thisMachinePlaysAliens().
bool missionRolePlaysAliens(const SavedGame* save);

}

}
