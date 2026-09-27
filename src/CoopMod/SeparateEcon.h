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
}
}
