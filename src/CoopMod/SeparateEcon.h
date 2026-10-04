#pragma once

#include <string>
#include <cstdint>
#include <json/json.h>

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
