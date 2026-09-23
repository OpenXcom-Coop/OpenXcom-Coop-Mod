#include "SeparateEcon.h"

#include "connectionTCP.h"
#include "SharedEcon.h"
#include "../Engine/Game.h"
#include "../Engine/State.h"
#include "../Geoscape/ConfirmLandingState.h"
#include "../Geoscape/GeoscapeState.h"
#include "../Geoscape/ConfirmCydoniaState.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/Armor.h"

#include <algorithm>

namespace OpenXcom
{
namespace SeparateEcon
{
namespace
{
int findBaseIndex(Game* game, const Base* base)
{
	if (!game || !game->getSavedGame() || !base) return -1;
	auto* bases = game->getSavedGame()->getBases();
	for (size_t i = 0; i < bases->size(); ++i)
		if (bases->at(i) == base) return static_cast<int>(i);
	return -1;
}

Craft* resolveCraft(Game* game, const Json::Value& obj)
{
	if (!game || !game->getSavedGame()) return nullptr;
	auto* bases = game->getSavedGame()->getBases();
	int bi = obj.get("baseId", -1).asInt();
	if (bi < 0 || bi >= static_cast<int>(bases->size())) return nullptr;
	int id = obj.get("craftId", -1).asInt();
	std::string type = obj.get("craftType", "").asString();
	for (Craft* craft : *bases->at(bi)->getCrafts())
		if (craft->getId() == id && craft->getRules()->getType() == type) return craft;
	return nullptr;
}

GeoscapeState* geo(Game* game)
{
	if (!game) return nullptr;
	for (State* state : game->getStates())
		if (GeoscapeState* gs = dynamic_cast<GeoscapeState*>(state)) return gs;
	return nullptr;
}

Json::Value craftMessage(const char* state, Game* game, Craft* craft)
{
	Json::Value msg;
	msg["state"] = state;
	msg["baseId"] = findBaseIndex(game, craft ? craft->getBase() : nullptr);
	msg["craftId"] = craft ? craft->getId() : -1;
	msg["craftType"] = craft ? craft->getRules()->getType() : "";
	return msg;
}
}

bool onMessage(Game* game, const std::string& state, const Json::Value& obj)
{
	if (state == "separate_land_prompt")
	{
		if (game && game->getCoopMod() && !game->getCoopMod()->getServerOwner())
		{
			Craft* craft = resolveCraft(game, obj);
			GeoscapeState* gs = geo(game);
			if (craft && craft->getDestination() && gs)
			{
				game->getCoopMod()->clearLandingResolved(craft->getId());
				gs->popup(new ConfirmLandingState(craft, nullptr, nullptr,
					obj.get("shade", 0).asInt(), true));
			}
		}
		return true;
	}
	if (state == "separate_land_reply")
	{
		if (game && game->getCoopMod() && game->getCoopMod()->getServerOwner())
		{
			Craft* craft = resolveCraft(game, obj);
			GeoscapeState* gs = geo(game);
			if (craft && gs)
				gs->sharedLandingReply(craft, obj.get("yes", false).asBool(),
					obj.get("patrol", false).asBool());
		}
		return true;
	}
	if (state == "separate_land_close")
	{
		if (game && game->getCoopMod() && !game->getCoopMod()->getServerOwner())
			game->getCoopMod()->markLandingResolved(obj.get("craftId", -1).asInt());
		return true;
	}
	if (state == "separate_cydonia_request")
	{
		if (game && game->getCoopMod() && game->getCoopMod()->getServerOwner())
		{
			Craft* craft = resolveCraft(game, obj);
			if (craft && !game->getSavedGame()->getSavedBattle())
			{
				ConfirmCydoniaState* confirm = new ConfirmCydoniaState(craft);
				game->pushState(confirm);
				confirm->btnYesClick(nullptr);
			}
		}
		return true;
	}
	return false;
}

void submitLocalCmd(Game* game, const std::string& cmd, int baseId,
	const Json::Value& payload)
{
	if (!game || !game->getCoopMod() || game->getCoopMod()->isSharedCampaign()) return;
	SharedEcon::submitCommandEngine(game, cmd, baseId, payload, true);
}

int baseIndex(Game* game, const Base* base)
{
	return findBaseIndex(game, base);
}

bool allowsForeignBaseCommand(const std::string& cmd, bool remote)
{
	// Player-facing exceptions agreed for a foreign Separate base. Commands in
	// the second group are host simulation results, never remote player requests.
	if (cmd == "buy" || cmd == "craft_equip" || cmd == "craft_rearm"
		|| cmd == "craft_assign")
		return true;
	return !remote && (
		cmd == "research_done" || cmd == "fac_done" || cmd == "prod_done"
		|| cmd == "transfer_arrived" || cmd == "base_destroyed"
		|| cmd == "patrol_prompt" || cmd == "base_damaged"
		|| cmd == "alien_base_found" || cmd == "alert" || cmd == "day_tick"
		|| cmd == "land_prompt" || cmd == "land_close");
}

bool validateCraftAssign(Game* game, const Json::Value& payload, Base* base,
	int seat, int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!game || !base) { failReason = "base not found"; return false; }
	Craft* craft = nullptr;
	int id = payload.get("craftId", -1).asInt();
	std::string type = payload.get("craftType", "").asString();
	for (Craft* candidate : *base->getCrafts())
		if (candidate->getId() == id && candidate->getRules()->getType() == type)
		{ craft = candidate; break; }
	if (!craft) { failReason = "craft not found"; return false; }

	int soldierId = payload.get("soldierId", -1).asInt();
	int soldierOwner = payload.get("soldierOwner", seat).asInt();
	Soldier* soldier = nullptr;
	for (Soldier* candidate : *base->getSoldiers())
		if (candidate->getId() == soldierId
			&& candidate->getOwnerPlayerId() == soldierOwner)
		{ soldier = candidate; break; }
	if (!soldier) { failReason = "soldier not found"; return false; }
	if (soldier->getOwnerPlayerId() != seat)
		{ failReason = "soldier not owned by player"; return false; }

	bool onOff = payload.get("onOff", false).asBool();
	if (soldier->getCraft() && soldier->getCraft()->getStatus() == "STR_OUT")
		{ failReason = "craft out on mission"; return false; }
	if (onOff && soldier->getCraft() != craft)
	{
		if (!soldier->hasFullHealth())
			{ failReason = "STR_SOLDIER_NOT_APPROVED"; return false; }
		int space = std::max(0, craft->getMaxUnitsClamped() / 2
			- craft->getSpaceUsedByOwner(seat));
		if (craft->validateAddingSoldier(space, soldier) != CPE_None)
			{ failReason = "STR_NOT_ENOUGH_CRAFT_SPACE"; return false; }
	}
	return true;
}

void submitCraftEquip(Game* game, Craft* craft, const std::string& itemType,
	int desiredOnCraft)
{
	if (!craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["item"] = itemType;
	p["count"] = desiredOnCraft;
	submitLocalCmd(game, "craft_equip", findBaseIndex(game, craft->getBase()), p);
}

void submitCraftRearm(Game* game, Craft* craft, int slot,
	const std::string& weaponType)
{
	if (!craft) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["slot"] = slot;
	p["weapon"] = weaponType;
	submitLocalCmd(game, "craft_rearm", findBaseIndex(game, craft->getBase()), p);
}

void submitCraftAssign(Game* game, Craft* craft, Soldier* soldier, bool onOff)
{
	if (!craft || !soldier) return;
	Json::Value p;
	p["craftId"] = craft->getId();
	p["craftType"] = craft->getRules()->getType();
	p["soldierId"] = soldier->getId();
	p["soldierOwner"] = soldier->getOwnerPlayerId();
	p["onOff"] = onOff;
	submitLocalCmd(game, "craft_assign", findBaseIndex(game, craft->getBase()), p);
}

void submitSoldierArmor(Game* game, Base* base, Soldier* soldier,
	const std::string& armorType)
{
	if (!base || !soldier) return;
	Json::Value p;
	p["soldierId"] = soldier->getId();
	p["armor"] = armorType;
	submitLocalCmd(game, "soldier_armor", findBaseIndex(game, base), p);
}

void hostLandingPrompt(Game* game, Craft* craft, int seat, int shade)
{
	if (!game || !craft || !(game->getCoopMod()->isSharedCampaign() || game->getCoopMod()->isSeparateCampaign())
		|| game->getCoopMod()->isSharedCampaign() || !game->getCoopMod()->getServerOwner()) return;
	Json::Value msg = craftMessage("separate_land_prompt", game, craft);
	msg["initiatorSeat"] = seat;
	msg["shade"] = shade;
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}

void submitLandReply(Game* game, Craft* craft, bool yes, bool patrol)
{
	if (!game || !craft) return;
	Json::Value msg = craftMessage("separate_land_reply", game, craft);
	msg["yes"] = yes;
	msg["patrol"] = patrol;
	if (game->getCoopMod()->getServerOwner())
		onMessage(game, "separate_land_reply", msg);
	else
		game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}

void broadcastLandClose(Game* game, Craft* craft)
{
	if (!game || !craft || !game->getCoopMod()->getServerOwner()) return;
	Json::Value msg = craftMessage("separate_land_close", game, craft);
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}

void requestCydonia(Game* game, Craft* craft)
{
	if (!game || !craft || !game->getCoopMod()) return;
	Json::Value msg = craftMessage("separate_cydonia_request", game, craft);
	if (game->getCoopMod()->getServerOwner()) onMessage(game, "separate_cydonia_request", msg);
	else game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}
}
}
