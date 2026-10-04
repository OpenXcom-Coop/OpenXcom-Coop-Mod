#include "SeparateCon.h"

#include <algorithm>

namespace OpenXcom
{

void SeparateCon::clear()
{
	_players.clear();
	_loadedFromSave = false;
	_missionOwnerCursor = 0;
}

void SeparateCon::load(const YAML::YamlNodeReader& reader)
{
	clear();
	if (!reader)
		return;

	_loadedFromSave = true;
	reader.tryRead("missionOwnerCursor", _missionOwnerCursor);
	for (const auto& playerReader : reader["players"].children())
	{
		const std::string name = playerReader["name"].readVal<std::string>("");
		if (name.empty())
			continue;

		PlayerState& player = _players[name];
		playerReader.tryRead("faction", player.faction);
		std::vector<std::string> factionResearch;
		playerReader.tryRead("factionResearch", factionResearch);
		player.factionResearch.insert(factionResearch.begin(), factionResearch.end());
		std::vector<std::string> completed;
		playerReader.tryRead("completedResearch", completed);
		player.completedResearch.insert(completed.begin(), completed.end());

	}
}

void SeparateCon::save(YAML::YamlNodeWriter writer) const
{
	writer.setAsMap();
	writer.write("version", 3);
	if (_missionOwnerCursor != 0)
		writer.write("missionOwnerCursor", _missionOwnerCursor);
	auto playersWriter = writer["players"];
	playersWriter.setAsSeq();
	for (const auto& entry : _players)
	{
		auto playerWriter = playersWriter.write();
		playerWriter.setAsMap();
		playerWriter.write("name", entry.first);
		if (!entry.second.faction.empty())
			playerWriter.write("faction", entry.second.faction);
		if (!entry.second.factionResearch.empty())
		{
			std::vector<std::string> factionResearch(
				entry.second.factionResearch.begin(), entry.second.factionResearch.end());
			playerWriter.write("factionResearch", factionResearch);
		}
		if (!entry.second.completedResearch.empty())
		{
			std::vector<std::string> completed(entry.second.completedResearch.begin(), entry.second.completedResearch.end());
			playerWriter.write("completedResearch", completed);
		}
	}
}

void SeparateCon::ensurePlayers(const std::vector<std::string>& playerNames)
{
	for (const auto& name : playerNames)
		if (!name.empty())
			_players.emplace(name, PlayerState());
}

void SeparateCon::setResearchSharingEnabled(bool enabled)
{
	_researchSharingEnabled = enabled;
}

void SeparateCon::migrateLegacyResearch(const std::vector<std::string>& playerNames,
	const std::vector<std::string>& completedResearch)
{
	if (_loadedFromSave || playerNames.empty() || playerNames.front().empty())
		return;
	ensurePlayers(playerNames);
	for (const auto& research : completedResearch)
		addCompletedResearch(playerNames.front(), research);
	_loadedFromSave = true;
}

SeparateCon::PlayerState* SeparateCon::getPlayer(const std::string& playerName)
{
	auto it = _players.find(playerName);
	return it == _players.end() ? nullptr : &it->second;
}

const SeparateCon::PlayerState* SeparateCon::getPlayer(const std::string& playerName) const
{
	auto it = _players.find(playerName);
	return it == _players.end() ? nullptr : &it->second;
}

void SeparateCon::setFaction(const std::string& playerName, const std::string& faction)
{
	if (!playerName.empty())
		_players[playerName].faction = faction;
}

void SeparateCon::setFactionResearch(const std::string& playerName,
	const std::vector<std::string>& research)
{
	if (playerName.empty()) return;
	PlayerState& player = _players[playerName];
	player.factionResearch.insert(research.begin(), research.end());
}

bool SeparateCon::hasFactionResearch(const std::string& playerName,
	const std::string& research) const
{
	const PlayerState* player = getPlayer(playerName);
	return player && player->factionResearch.find(research) != player->factionResearch.end();
}

bool SeparateCon::addCompletedResearch(const std::string& playerName, const std::string& research)
{
	return !playerName.empty() && !research.empty()
		&& _players[playerName].completedResearch.insert(research).second;
}

void SeparateCon::replaceCompletedResearch(const std::string& playerName,
	const std::set<std::string>& research)
{
	if (!playerName.empty())
		_players[playerName].completedResearch = research;
}

bool SeparateCon::removeCompletedResearch(const std::string& playerName, const std::string& research)
{
	PlayerState* player = getPlayer(playerName);
	return player && player->completedResearch.erase(research) != 0;
}

bool SeparateCon::completeResearch(const std::string& playerName, const std::string& research)
{
	// Profiles are exclusively the private-research store. Shared Research uses
	// SavedGame::_discovered, exactly like Shared Campaign.
	return addCompletedResearch(playerName, research);
}

bool SeparateCon::hasCompletedResearch(const std::string& playerName, const std::string& research) const
{
	const PlayerState* player = getPlayer(playerName);
	return player && player->completedResearch.find(research) != player->completedResearch.end();
}

bool SeparateCon::haveDifferentFactions() const
{
	std::string first;
	for (const auto& entry : _players)
		if (!entry.second.faction.empty())
		{
			if (first.empty()) first = entry.second.faction;
			else if (entry.second.faction != first) return true;
		}
	return false;
}

std::string SeparateCon::nextMissionOwner(const std::vector<std::string>& playerNames)
{
	std::vector<std::string> valid;
	for (const auto& name : playerNames)
		if (!name.empty() && getPlayer(name)) valid.push_back(name);
	if (valid.empty()) return std::string();
	const std::string owner = valid[_missionOwnerCursor % valid.size()];
	_missionOwnerCursor = (_missionOwnerCursor + 1) % valid.size();
	return owner;
}

int SeparateCon::getFactionDifficulty(const std::string& playerName, int fallback) const
{
	const PlayerState* player = getPlayer(playerName);
	if (!player) return fallback;
	const std::string prefix = "difficulty:";
	if (player->faction.compare(0, prefix.size(), prefix) != 0) return fallback;
	try
	{
		return std::stoi(player->faction.substr(prefix.size()));
	}
	catch (...)
	{
		return fallback;
	}
}

}
