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
class AlienDeployment;
class Target;
struct GeoscapeEventDisplay;

/** Host-authoritative protocol for the schema-3 SEPARATE campaign.
 *
 * Separate deliberately has its own wire namespace and policy layer.  Its
 * implementation reuses the internal validated command engine, but never exposes
 * SHARED protocol messages to Separate peers.
 */
namespace SeparateEcon
{
/// One item of a saved soldier equipment layout: the fields a world saves for
/// each EquipmentLayoutItem of its own layout templates.
struct LayoutTemplateItem
{
	std::string itemType;
	std::string slot;
	int slotX = 0;
	int slotY = 0;
	/// The ammo type in each ammo slot; an empty string is an empty slot.
	std::vector<std::string> ammo;
	int fuseTimer = -1;
	bool fixed = false;
};

/// A saved soldier equipment layout slot: its name, its armor (empty = none)
/// and its items.
struct LayoutTemplate
{
	std::string name;
	std::string armor;
	std::vector<LayoutTemplateItem> items;
	bool empty() const { return name.empty() && armor.empty() && items.empty(); }
};

/// A saved craft loadout slot: its name and its item counts by type.
struct CraftLoadoutTemplate
{
	std::string name;
	std::map<std::string, int> items;
	bool empty() const { return name.empty() && items.empty(); }
};

/// One player's saved soldier layouts and craft loadouts by slot index; a slot
/// missing from a map is empty. Read and written in the keys a world uses for
/// its own templates (globalEquipmentLayoutN, globalEquipmentLayoutNameN,
/// globalEquipmentLayoutArmorN, globalCraftLoadoutN, globalCraftLoadoutNameN),
/// so SavedGame::loadTemplates reads the same node.
struct EquipmentTemplates
{
	std::map<int, LayoutTemplate> layouts;
	std::map<int, CraftLoadoutTemplate> craftLoadouts;
	bool empty() const { return layouts.empty() && craftLoadouts.empty(); }
	void load(const YAML::YamlNodeReader& reader);
	void save(YAML::YamlNodeWriter writer) const;
};

/** Persisted player-scoped state for the one-world Separate campaign. */
class CampaignData
{
public:
	struct PlayerState
	{
		std::string faction;
		std::set<std::string> factionResearch;
		std::set<std::string> completedResearch;
		/// Topics this player's own discoveries disabled (private research).
		std::set<std::string> disabledResearch;
		std::vector<int64_t> funds;
		std::vector<int> factionScores;
		std::set<std::string> generatedEvents;
		std::map<std::string, int> missionRuns;
		std::map<std::string, int> missionMarkers;
		std::map<std::string, int> ufopediaRuleStatus;
		/// This player's saved soldier layouts and craft loadouts. The host's
		/// player keeps its own in the world's template slots instead, so its
		/// profile holds none.
		EquipmentTemplates equipmentTemplates;
	};
private:
	std::map<std::string, PlayerState> _players;
	std::set<std::string> _completedFactions;
	std::vector<std::string> _pendingFactionRechecks;
	/// Owner of a finished faction finale whose continue/end vote has not run.
	/// Persisted so a reload or a rejoin still holds the vote.
	std::string _pendingFactionFinaleOwner;
	bool _loadedFromSave = false;
	bool _researchSharingEnabled = false;
	/// The research mode has been decided: loaded from a save, or applied once.
	bool _researchModeKnown = false;
	size_t _missionOwnerCursor = 0;
public:
	void clear();
	void load(const YAML::YamlNodeReader& reader);
	void save(YAML::YamlNodeWriter writer) const;
	void ensurePlayers(const std::vector<std::string>& playerNames);
	/// Map profiles saved under a name the roster no longer carries onto the
	/// roster name that has no profile yet, so profile names always equal
	/// roster names. Only an unambiguous one-to-one match is
	/// renamed; anything else is logged and left as it is.
	void reconcilePlayerNames(const std::vector<std::string>& roster);
	void ensurePlayerFunds(const std::vector<std::string>& playerNames,
		const std::vector<int64_t>& legacyFunds);
	void ensureFactionScores(const std::vector<std::string>& playerNames,
		size_t historySize);
	void newFactionScoreMonth(const std::vector<std::string>& playerNames,
		size_t historySize);
	void addFactionScore(const std::string& playerName, int score);
	int getFactionScore(const std::string& playerName, size_t historyIndex) const;
	bool wasEventGenerated(const std::string& playerName, const std::string& eventName) const;
	void addGeneratedEvent(const std::string& playerName, const std::string& eventName);
	int getMissionRuns(const std::string& playerName, const std::string& name) const;
	void addMissionRun(const std::string& playerName, const std::string& name);
	int getMissionMarkerCount(const std::string& playerName, const std::string& name) const;
	void addMissionMarker(const std::string& playerName, const std::string& name);
	std::vector<int64_t>* getPlayerFunds(const std::string& playerName);
	const std::vector<int64_t>* getPlayerFunds(const std::string& playerName) const;
	void migrateLegacyResearch(const std::vector<std::string>& playerNames,
		const std::vector<std::string>& completedResearch);
	bool wasLoadedFromSave() const { return _loadedFromSave; }
	bool isResearchSharingEnabled() const { return _researchSharingEnabled; }
	void setResearchSharingEnabled(bool enabled);
	bool isResearchModeKnown() const { return _researchModeKnown; }
	bool disableResearch(const std::string& playerName, const std::string& research);
	bool enableResearch(const std::string& playerName, const std::string& research);
	bool isResearchDisabled(const std::string& playerName, const std::string& research) const;
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
	void setUfopediaRuleStatus(const std::string& playerName,
		const std::string& rule, int status);
	bool getUfopediaRuleStatus(const std::string& playerName,
		const std::string& rule, int& status) const;
	void migrateLegacyUfopediaStatus(const std::vector<std::string>& playerNames,
		const std::map<std::string, int>& status);
	bool haveDifferentFactions() const;
	std::string getPlayerFaction(const std::string& playerName) const;
	bool isFactionCompleted(const std::string& faction) const;
	bool isPlayerFactionCompleted(const std::string& playerName) const;
	void completePlayerFaction(const std::string& playerName);
	void queueUnfinishedFactionRechecks(const std::vector<std::string>& playerNames);
	bool allPlayerFactionsCompleted(const std::vector<std::string>& playerNames) const;
	const std::set<std::string>& getCompletedFactions() const { return _completedFactions; }
	const std::vector<std::string>& getPendingFactionRechecks() const { return _pendingFactionRechecks; }
	const std::string& getPendingFactionFinaleOwner() const { return _pendingFactionFinaleOwner; }
	void setPendingFactionFinaleOwner(const std::string& owner) { _pendingFactionFinaleOwner = owner; }
	std::string nextMissionOwner(const std::vector<std::string>& playerNames);
	int getFactionDifficulty(const std::string& playerName, int fallback) const;
};

/// Give every live soldier in Separate's unified world a globally unique id.
/// Returns the number of legacy/player-local collisions that were upgraded.
int normalizeSoldierIds(Game* game);
/// Give every live craft in Separate's unified world an id that is unique per
/// craft type, and raise the type counters past them. Host (or solo load) only;
/// a replica adopts the host's ids. Returns the number of crafts renumbered.
int normalizeCraftIds(Game* game);
/// Resolve persistent vehicle player names to the current runtime seats.
/// This must run after loading/rejoining and before a tactical deployment.
void synchronizeVehicleOwners(Game* game);
/// Apply Separate's per-player craft quota to template-assigned starting crews.
/// Only acts while a newly created campaign is still at month -1.
void trimInitialCraftCrews(Game* game);
/// Sum monthly maintenance for bases owned by this local Separate player.
int localPlayerMaintenance(Game* game);
/// Sum monthly maintenance for bases owned by the named Separate player.
int playerMaintenance(Game* game, const std::string& playerName);
/// Private faction-event score for the local player at a monthly history index.
/// Returns zero when all Separate players use the same faction.
int localFactionScore(Game* game, size_t historyIndex);
/// Resolve a faction-owned final mission. Returns true only when the original
/// global ending should continue. A loss keeps the mod's campaign-wide defeat,
/// while a win becomes global only after every distinct faction has completed.
bool resolveFactionFinalOutcome(Game* game, const std::string& ownerPlayerName,
	bool victory);
/// Return the localized New Game label for a player's difficulty-backed faction.
/// Non-difficulty faction identifiers are returned as-is.
std::string factionDisplayName(Game* game, const std::string& playerName);
/// Whether a faction-owned script may still generate content. Common scripts
/// and every non-Separate mode remain allowed.
bool allowsFactionScript(Game* game, const std::string& ownerPlayerName);
bool onMessage(Game* game, const std::string& state, const Json::Value& obj);
/// Store a local player's Ufopaedia mark and persist client changes on the host.
void setUfopediaRuleStatus(Game* game, const std::string& rule, int status);
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
/// Separate wallet that pays for host-simulated work at this base (its owner);
/// empty outside Separate, so the caller keeps the ordinary funds.
std::string baseWalletOwner(Game* game, const Base* base);
/// Host: the soldiers @a ids a production at @a base just spawned, from its
/// transfers. In Separate they belong to the base owner, as a hire belongs to
/// its purchaser; elsewhere their owner stays as it is.
std::vector<Soldier*> spawnedSoldiers(Game* game, Base* base, const std::vector<int>& ids);
/// Whether this local seat owns a base-scoped notification (production,
/// construction, and owner-less legacy arrivals).
bool showBaseNotification(Game* game, const Base* base);
/// Consume a Shared Research prerequisite from whichever Separate base owns it.
bool consumeSharedResearchItem(Game* game, Base* projectBase,
	const RuleResearch* research);
/// Separate-only host policy for commands targeting another player's base.
bool allowsForeignBaseCommand(const std::string& cmd, bool remote);
/// The same policy with the command's payload: a transfer out of @a base is
/// allowed when every entry is a soldier that @a seat owns there, and a
/// live soldier's transformation is allowed (its validator checks the owner).
bool allowsForeignBaseCommand(const std::string& cmd, bool remote,
	const Json::Value& payload, const Base* base, int seat);
/// Commands the host emits to mirror its own simulation (never player requests).
bool isHostSimulationResult(const std::string& cmd);
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
/// Client: send the host soldier layout slot @a index just saved on this
/// machine (name, armor and items together), so the host keeps it in this
/// player's profile. Does nothing outside a Separate client.
void submitLayoutTemplate(Game* game, int index);
/// Client: the same for craft loadout slot @a index.
void submitCraftLoadoutTemplate(Game* game, int index);
/// Host check of an equipment_template command: a Separate campaign, a
/// non-host player, a template kind and slot in range, and known item, slot
/// and armor types.
bool validateEquipmentTemplate(Game* game, const Json::Value& payload, Base* base,
	int seat, int64_t& cost, std::string& failReason);
/// Store the template slot an equipment_template command carries in the
/// sending player's profile (never in the world's own template slots).
void applyEquipmentTemplate(Game* game, Json::Value& payload, Base* base, int seat);
/// New campaign: a joining player's templates start as the starting base's
/// global templates for that player's @a difficulty, as Mod::newSave gives
/// a new world's own slots.
void setStartingTemplates(Game* game, const std::string& playerName, int difficulty);
/// Broadcast the host-authoritative post-bombardment facility layout.
void hostBaseDamaged(Game* game, Base* base, const Ufo* ufo);
void hostLandingPrompt(Game* game, Craft* craft, int seat, int shade);
void submitLandReply(Game* game, Craft* craft, bool yes, bool patrol);
void broadcastLandClose(Game* game, Craft* craft);
void requestCydonia(Game* game, Craft* craft);
/// A craft request message (requestCydonia): @a state plus the reference to
/// @a craft that resolveCraft reads back on the receiving machine.
Json::Value craftMessage(const char* state, Game* game, Craft* craft);
/// The craft a craftMessage names on this machine, or nullptr.
Craft* resolveCraft(Game* game, const Json::Value& obj);
/// Replicate research unlocked by a mission-site expiry (host only): the replica
/// applies the host's exact topic and getOneFree bonus to the same players.
void hostMissionResearch(Game* game, const AlienDeployment* deployment,
	const RuleResearch* research, const RuleResearch* bonus,
	const std::string& ownerPlayerName);
/// Replicate a mod geoscape event and its host-selected Shared Research result.
void hostGeoscapeEvent(Game* game, const std::string& eventName,
	const std::string& researchName, const std::string& bonusResearchName,
	const std::string& ownerPlayerName = std::string(),
	const GeoscapeEventDisplay* display = nullptr);
}
}
