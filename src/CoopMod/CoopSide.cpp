#include "CoopSide.h"
#include <vector>
#include "connectionTCP.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace CoopSide
{

namespace
{
// The one-world layout of each PvP game mode: [0] = game mode 2, [1] = game mode 3.
bool g_pvpOneWorld[2] = { false, false };
}

bool isPvpMode(int gamemode)
{
	return gamemode == 2 || gamemode == 3;
}

bool hostPlaysAliens(int gamemode)
{
	return gamemode == 3;
}

bool pvpOneWorldEnabled(int gamemode)
{
	return isPvpMode(gamemode) && g_pvpOneWorld[gamemode - 2];
}

void setPvpOneWorldEnabled(int gamemode, bool enabled)
{
	if (isPvpMode(gamemode))
		g_pvpOneWorld[gamemode - 2] = enabled;
}

int gamemode(const SavedGame* save)
{
	// A one-world PvP save keeps its own mode, so a later session value (the host's DISCONNECT zeroes it)
	// never changes its rules. Every other save follows the session's mode.
	const int own = save ? save->getWorldGamemode() : 0;
	if (pvpOneWorldEnabled(own))
		return own;
	return connectionTCP::_coopGamemode;
}

bool pvpOneWorld(const SavedGame* save)
{
	return pvpOneWorldEnabled(gamemode(save));
}

bool seatPlaysAliens(int gamemode, int seat)
{
	if (seat < 0)
		return false;
	if (gamemode == 2)
		return seat != 0;
	if (gamemode == 3)
		return seat == 0;
	return false;
}

bool playerPlaysAliens(const SavedGame* save, const std::string& playerName)
{
	if (!save || playerName.empty())
		return false;
	const std::vector<std::string>& roster = save->getCoopPlayers();
	for (size_t seat = 0; seat < roster.size(); ++seat)
		if (roster[seat] == playerName)
			return seatPlaysAliens(gamemode(save), static_cast<int>(seat));
	return false;
}

bool thisMachinePlaysAliens(const SavedGame* save)
{
	const int mode = gamemode(save);
	if (pvpOneWorldEnabled(mode))
		return seatPlaysAliens(mode, connectionTCP::localSeat());
	// Two worlds: the machine that keeps the stand-in world without bases is flagged at start and load.
	return connectionTCP::no_bases;
}

bool peerPlaysAliens(const SavedGame* save)
{
	return seatPlaysAliens(gamemode(save), connectionTCP::getServerOwner() ? 1 : 0);
}

bool missionRolePlaysAliens(const SavedGame* save)
{
	const int mode = gamemode(save);
	if (pvpOneWorldEnabled(mode))
		return thisMachinePlaysAliens(save);
	const bool missionHost = connectionTCP::getHost();
	return (mode == 2 && !missionHost) || (mode == 3 && missionHost);
}

}

}
