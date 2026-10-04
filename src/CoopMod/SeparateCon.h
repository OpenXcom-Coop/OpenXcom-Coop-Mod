#pragma once

#include <map>
#include <set>
#include <string>
#include <vector>

#include "../Engine/Yaml.h"

namespace OpenXcom
{

/**
 * Player-scoped strategic data for a one-world Separate campaign.
 *
 * The world itself remains host-authoritative and is stored by SavedGame. This
 * component only stores the state which must not leak between player factions:
 * faction identity and completed research. Research is private by default; the
 * optional Shared Research session policy copies completed topics immediately.
 * Transient scheduling state (for example whose mission turn is next) does not
 * belong here and intentionally resets when a session starts.
 */
class SeparateCon
{
public:
	struct PlayerState
	{
		std::string faction;
		// Immutable campaign-start research signature used to recognize faction
		// scripts even when Shared Research later merges the live trees.
		std::set<std::string> factionResearch;
		std::set<std::string> completedResearch;
	};

private:
	std::map<std::string, PlayerState> _players;
	bool _loadedFromSave = false;
	// Session policy controlled by the host's multiplayer option. It is not save
	// progression and is deliberately not serialized.
	bool _researchSharingEnabled = false;
	size_t _missionOwnerCursor = 0;

public:
	void clear();
	void load(const YAML::YamlNodeReader& reader);
	void save(YAML::YamlNodeWriter writer) const;

	void ensurePlayers(const std::vector<std::string>& playerNames);
	/// Upgrade an old one-world Separate save which only has global research.
	/// Existing discoveries belong to the host; peers never receive them implicitly.
	void migrateLegacyResearch(const std::vector<std::string>& playerNames,
		const std::vector<std::string>& completedResearch);
	bool wasLoadedFromSave() const { return _loadedFromSave; }
	bool isResearchSharingEnabled() const { return _researchSharingEnabled; }
	void setResearchSharingEnabled(bool enabled);
	const std::map<std::string, PlayerState>& getPlayers() const { return _players; }
	PlayerState* getPlayer(const std::string& playerName);
	const PlayerState* getPlayer(const std::string& playerName) const;

	void setFaction(const std::string& playerName, const std::string& faction);
	void setFactionResearch(const std::string& playerName,
		const std::vector<std::string>& research);
	bool hasFactionResearch(const std::string& playerName,
		const std::string& research) const;
	bool addCompletedResearch(const std::string& playerName, const std::string& research);
	void replaceCompletedResearch(const std::string& playerName,
		const std::set<std::string>& research);
	bool removeCompletedResearch(const std::string& playerName, const std::string& research);
	/// Complete for the owner only by default; with Shared Research enabled the
	/// exact same topic is granted immediately to every player, without prompts.
	bool completeResearch(const std::string& playerName, const std::string& research);
	bool hasCompletedResearch(const std::string& playerName, const std::string& research) const;
	bool haveDifferentFactions() const;
	/// Select one player for the next host-generated mission batch. Advancing one
	/// cursor preserves the single-player mission budget instead of running the
	/// generator once per player.
	std::string nextMissionOwner(const std::vector<std::string>& playerNames);
	int getFactionDifficulty(const std::string& playerName, int fallback) const;
};

}
