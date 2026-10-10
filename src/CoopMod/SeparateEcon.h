#pragma once

#include <string>
#include <cstdint>
#include <map>
#include <set>
#include <vector>
#include <json/json.h>
#include "../Engine/Yaml.h"

namespace OpenXcom
{
class Game;
class Craft;
class Base;
class Soldier;
class Ufo;
class RuleResearch;
class Target;

/** Host-authoritative protocol for the schema-3 SEPARATE campaign.
 *
 * Separate deliberately has its own wire namespace and policy layer.  Its
 * implementation reuses the internal validated command engine, but never exposes
 * SHARED protocol messages to Separate peers.
 */
namespace SeparateEcon
{
/** Persisted player-scoped state for the one-world Separate campaign. */
class CampaignData
{
public:
	struct PlayerState
	{
		std::string faction;
		std::set<std::string> factionResearch;
		std::set<std::string> completedResearch;
		std::vector<int64_t> funds;
		std::map<std::string, std::map<std::string, int> > vehicleSelections;
	};
private:
	std::map<std::string, PlayerState> _players;
	bool _loadedFromSave = false;
	bool _researchSharingEnabled = false;
	size_t _missionOwnerCursor = 0;
public:
	void clear();
	void load(const YAML::YamlNodeReader& reader);
	void save(YAML::YamlNodeWriter writer) const;
	void ensurePlayers(const std::vector<std::string>& playerNames);
	void ensurePlayerFunds(const std::vector<std::string>& playerNames,
		const std::vector<int64_t>& legacyFunds);
	std::vector<int64_t>* getPlayerFunds(const std::string& playerName);
	const std::vector<int64_t>* getPlayerFunds(const std::string& playerName) const;
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
	bool completeResearch(const std::string& playerName, const std::string& research);
	bool hasCompletedResearch(const std::string& playerName, const std::string& research) const;
	bool haveDifferentFactions() const;
	std::string nextMissionOwner(const std::vector<std::string>& playerNames);
	int getFactionDifficulty(const std::string& playerName, int fallback) const;
	int getVehicleSelection(const std::string& playerName,
		const std::string& craftKey, const std::string& itemType) const;
	void setVehicleSelection(const std::string& playerName,
		const std::string& craftKey, const std::string& itemType, int count);
};

/// Give every live soldier in Separate's unified world a globally unique id.
/// Returns the number of legacy/player-local collisions that were upgraded.
int normalizeSoldierIds(Game* game);
/// Sum monthly maintenance for bases owned by this local Separate player.
int localPlayerMaintenance(Game* game);
/// Sum monthly maintenance for bases owned by the named Separate player.
int playerMaintenance(Game* game, const std::string& playerName);
bool onMessage(Game* game, const std::string& state, const Json::Value& obj);
void submitLocalCmd(Game* game, const std::string& cmd, int baseId,
	const Json::Value& payload);
int baseIndex(Game* game, const Base* base);
/// True when a craft belongs to the player using this local game instance.
bool ownsCraft(Game* game, const Craft* craft);
/// True for this player's mission/UFO, or for an unowned legacy/shared target.
bool ownsMissionTarget(Game* game, const Target* target);
/// Persistent player-name owner of a faction target; empty means common.
std::string missionTargetOwner(const Target* target);
/// Owner labels are useful only when Separate players selected different factions.
bool showMissionTargetOwner(Game* game);
/// Whether this local seat should see a completion popup for this base.
/// Shared Research notifies both seats; private research only the base owner.
bool showResearchCompletion(Game* game, const Base* base);
/// Consume a Shared Research prerequisite from whichever Separate base owns it.
bool consumeSharedResearchItem(Game* game, Base* projectBase,
	const RuleResearch* research);
/// Separate-only host policy for commands targeting another player's base.
bool allowsForeignBaseCommand(const std::string& cmd, bool remote);
/// Separate-only craft assignment validation (ownership + per-seat half quota).
bool validateCraftAssign(Game* game, const Json::Value& payload, Base* base,
	int seat, int64_t& cost, std::string& failReason);
/// Reject ordinary equipment changes at a foreign base; vehicles are the only
/// visitor-selectable craft equipment in Separate Campaign.
bool validateCraftEquip(Game* game, const Json::Value& payload, Base* base,
	int seat, int64_t& cost, std::string& failReason);
/// Validate/apply Separate player vehicle selection without changing base ownership.
bool validateVehicleEquip(Game* game, const Json::Value& payload, Base* base,
	int seat, int64_t& cost, std::string& failReason);
void applyVehicleEquip(Game* game, Json::Value& payload, Base* base, int seat);
int vehicleSelectionCount(Game* game, Craft* craft,
	const std::string& itemType, int seat);
void submitCraftEquip(Game* game, Craft* craft, const std::string& itemType,
	int desiredOnCraft);
void submitCraftRearm(Game* game, Craft* craft, int slot,
	const std::string& weaponType);
void submitCraftAssign(Game* game, Craft* craft, Soldier* soldier, bool onOff);
void submitSoldierArmor(Game* game, Base* base, Soldier* soldier,
	const std::string& armorType);
/// Broadcast the host-authoritative post-bombardment facility layout.
void hostBaseDamaged(Game* game, Base* base, const Ufo* ufo);
void hostLandingPrompt(Game* game, Craft* craft, int seat, int shade);
void submitLandReply(Game* game, Craft* craft, bool yes, bool patrol);
void broadcastLandClose(Game* game, Craft* craft);
void requestCydonia(Game* game, Craft* craft);
/// Replicate a mod geoscape event and its host-selected Shared Research result.
void hostGeoscapeEvent(Game* game, const std::string& eventName,
	const std::string& researchName, const std::string& bonusResearchName,
	const std::string& ownerPlayerName = std::string());
}
}
