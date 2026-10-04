#include "SeparateEcon.h"

#include "connectionTCP.h"
#include "SharedEcon.h"
#include "../Engine/Game.h"
#include "../Engine/State.h"
#include "../Geoscape/ConfirmLandingState.h"
#include "../Geoscape/GeoscapeState.h"
#include "../Geoscape/GeoscapeEventState.h"
#include "../Geoscape/ConfirmCydoniaState.h"
#include "../Savegame/Base.h"
#include "../Savegame/BaseFacility.h"
#include "../Savegame/Craft.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Ufo.h"
#include "../Savegame/AlienMission.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/MissionSite.h"
#include "../Mod/RuleBaseFacility.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleEvent.h"
#include "../Mod/RuleResearch.h"
#include "../Mod/Mod.h"
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
	if (state == "separate_geoscape_event")
	{
		if (game && game->getCoopMod() && !game->getCoopMod()->getServerOwner()
			&& game->getSavedGame() && game->getMod())
		{
			// The world stream replaces SavedGame, while this option lives in the
			// multiplayer session.  Keep both policy sources aligned before applying
			// an event so live play behaves exactly like the same save after reload.
			if (game->getSavedGame()->getSeparateCampaign().isResearchSharingEnabled()
				!= game->getCoopMod()->_enable_research_sync)
			{
				game->getSavedGame()->setSeparateResearchSharingEnabled(
					game->getCoopMod()->_enable_research_sync, game->getMod());
			}
			// The host already executed eventLogic and resolved any random research.
			// Adopt its canonical Shared Research list before constructing the event
			// state, so the replica cannot select a different event reward.
			Base* researchBase = nullptr;
			for (Base* candidate : *game->getSavedGame()->getBases())
				if (candidate && !candidate->_isForeignBase)
				{
					researchBase = candidate;
					break;
				}
			if (!researchBase && !game->getSavedGame()->getBases()->empty())
				researchBase = game->getSavedGame()->getBases()->front();

			std::string adoptedArticle;
			std::vector<const RuleResearch*> adoptedResearch;
			const Json::Value& discovered = obj["discoveredResearch"];
			for (Json::ArrayIndex i = 0; i < discovered.size(); ++i)
			{
				const std::string name = discovered[i].asString();
				if (!game->getSavedGame()->isResearched(name, false))
					if (RuleResearch* rule = game->getMod()->getResearch(name, false))
					{
						adoptedArticle = rule->getLookup().empty()
							? rule->getName() : rule->getLookup();
						game->getSavedGame()->addFinishedResearch(
							rule, game->getMod(), researchBase, true);
						adoptedResearch.push_back(rule);
					}
			}
			// Shared Campaign reaches this path through GeoscapeEventState::eventLogic,
			// which applies the primary research side effects after discovering the
			// event-selected topic.  Separate Campaign adopts the host's resolved
			// discovery snapshot first to avoid a second RNG roll, so eventLogic sees
			// those topics as already researched and deliberately skips that block.
			// Apply the same unlock chain explicitly for only the newly adopted topics.
			// This includes spawned items/events and custom counters used by large mods
			// to expose follow-up projects (for example XCOM Files' Secret Files).
			if (researchBase && !adoptedResearch.empty())
				game->getSavedGame()->handlePrimaryResearchSideEffects(
					adoptedResearch, game->getMod(), researchBase);
			if (RuleEvent* eventRule = game->getMod()->getEvent(
				obj.get("event", "").asString(), false))
				if (GeoscapeState* gs = geo(game))
				{
					const std::string owner = obj.get("ownerPlayerName", "").asString();
					GeoscapeEventState* eventState = new GeoscapeEventState(*eventRule, owner);
					std::string article = obj.get("researchName", "").asString();
					if (article.empty()) article = adoptedArticle;
					eventState->setReplicatedResearchNames(
						article,
						obj.get("bonusResearchName", "").asString());
					if (owner.empty() || owner == connectionTCP::seatName(connectionTCP::localSeat()))
						gs->popup(eventState);
					else
						delete eventState;
				}
		}
		return true;
	}
	if (state == "separate_apply")
	{
		// ownerPlayerName is the persistent Separate authority; _isForeignBase is
		// only a local presentation/permission cache.  A streamed or resumed world
		// may have been loaded before this process knew its final seat, so refresh
		// that cache before SharedEcon applies a host result.  In particular this
		// prevents a host-owned research_done from opening a completion popup on the
		// client.  Returning false intentionally passes the packet to the generic
		// validated command engine after the Separate preparation step.
		if (game && game->getCoopMod())
			game->getCoopMod()->refreshSeparateBaseOwnership();
		return false;
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

bool ownsCraft(Game* game, const Craft* craft)
{
	if (!game || !craft || !craft->getBase()) return false;
	if (!game->getCoopMod() || !game->getCoopMod()->isSeparateCampaign()) return true;
	// _isForeignBase is the local-view ownership flag derived from the persistent
	// owner player name by refreshSeparateBaseOwnership(). During an incoming
	// packet the static seat roster can briefly be unavailable/stale even though
	// that derivation has already completed; re-reading seatName here caused the
	// rightful client to reject its landing prompt.
	return !craft->getBase()->_isForeignBase;
}

std::string missionTargetOwner(const Target* target)
{
	if (!target) return std::string();
	std::string owner;
	if (const Ufo* ufo = dynamic_cast<const Ufo*>(target))
	{
		if (ufo->getMission()) owner = ufo->getMission()->getOwnerPlayerName();
	}
	else if (const MissionSite* site = dynamic_cast<const MissionSite*>(target))
	{
		owner = site->getOwnerPlayerName();
	}
	else if (const AlienBase* base = dynamic_cast<const AlienBase*>(target))
	{
		owner = base->getOwnerPlayerName();
	}
	return owner;
}

bool showMissionTargetOwner(Game* game)
{
	return game && game->getSavedGame() && game->getCoopMod()
		&& game->getCoopMod()->isSeparateCampaign()
		&& game->getSavedGame()->getSeparateCampaign().haveDifferentFactions();
}

bool ownsMissionTarget(Game* game, const Target* target)
{
	if (!game || !target || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign()) return true;
	const std::string owner = missionTargetOwner(target);
	if (owner.empty()) return true;
	return owner == connectionTCP::seatName(connectionTCP::localSeat());
}

bool showResearchCompletion(Game* game, const Base* base)
{
	if (!game || !base || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign())
		return true;
	// The multiplayer option is the campaign policy source. When research is
	// shared, a completed topic belongs to both player profiles and both players
	// receive the same completion dialog as Shared Campaign. In private mode the
	// host still simulates every base, but only that base's owner is notified.
	return game->getCoopMod()->_enable_research_sync || !base->_isForeignBase;
}

bool consumeSharedResearchItem(Game* game, Base* projectBase,
	const RuleResearch* research)
{
	if (!game || !projectBase || !research || !research->needItem()
		|| !research->destroyItem())
		return false;

	SavedGame* save = game->getSavedGame();
	if (!save) return false;

	if (game->getCoopMod() && game->getCoopMod()->isSeparateCampaign()
		&& game->getCoopMod()->_enable_research_sync)
	{
		for (Base* source : *save->getBases())
			if (source->getStorageItems()->getItem(research->getNeededItem()) > 0)
			{
				source->getStorageItems()->removeItem(research->getNeededItem(), 1);
				return true;
			}
		return false;
	}

	if (projectBase->getStorageItems()->getItem(research->getNeededItem()) > 0)
	{
		projectBase->getStorageItems()->removeItem(research->getNeededItem(), 1);
		return true;
	}
	return false;
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

void hostBaseDamaged(Game* game, Base* base, const Ufo* ufo)
{
	if (!game || !base || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign()
		|| !game->getCoopMod()->getServerOwner()) return;

	Json::Value payload;
	payload["ufoId"] = ufo ? ufo->getId() : -1;
	Json::Value facilities(Json::arrayValue);
	for (const BaseFacility* facility : *base->getFacilities())
	{
		if (!facility || !facility->getRules()) continue;
		Json::Value item;
		item["type"] = facility->getRules()->getType();
		item["x"] = facility->getX();
		item["y"] = facility->getY();
		item["buildTime"] = facility->getBuildTime();
		facilities.append(item);
	}
	payload["facilities"] = facilities;
	submitLocalCmd(game, "base_damaged", findBaseIndex(game, base), payload);
}

void hostLandingPrompt(Game* game, Craft* craft, int seat, int shade)
{
	if (!game || !craft || !(game->getCoopMod()->isSharedCampaign() || game->getCoopMod()->isSeparateCampaign())
		|| game->getCoopMod()->isSharedCampaign() || !game->getCoopMod()->getServerOwner()) return;
	Json::Value payload;
	payload["craftId"] = craft->getId();
	payload["craftType"] = craft->getRules()->getType();
	payload["initiatorSeat"] = seat;
	payload["shade"] = shade;
	submitLocalCmd(game, "land_prompt", findBaseIndex(game, craft->getBase()), payload);
}

void submitLandReply(Game* game, Craft* craft, bool yes, bool patrol)
{
	if (!game || !craft) return;
	if (game->getCoopMod()->getServerOwner())
	{
		GeoscapeState* gs = geo(game);
		if (gs)
			gs->sharedLandingReply(craft, yes, patrol, true /*hostDialogAnswered*/);
	}
	else
	{
		Json::Value payload;
		payload["craftId"] = craft->getId();
		payload["craftType"] = craft->getRules()->getType();
		payload["yes"] = yes;
		payload["patrol"] = patrol;
		submitLocalCmd(game, "land_reply", findBaseIndex(game, craft->getBase()), payload);
	}
}

void broadcastLandClose(Game* game, Craft* craft)
{
	if (!game || !craft || !game->getCoopMod()->getServerOwner()) return;
	Json::Value payload;
	payload["craftId"] = craft->getId();
	payload["craftType"] = craft->getRules()->getType();
	submitLocalCmd(game, "land_close", findBaseIndex(game, craft->getBase()), payload);
}

void requestCydonia(Game* game, Craft* craft)
{
	if (!game || !craft || !game->getCoopMod()) return;
	Json::Value msg = craftMessage("separate_cydonia_request", game, craft);
	if (game->getCoopMod()->getServerOwner()) onMessage(game, "separate_cydonia_request", msg);
	else game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}

void hostGeoscapeEvent(Game* game, const std::string& eventName,
	const std::string& researchName, const std::string& bonusResearchName,
	const std::string& ownerPlayerName)
{
	if (!game || eventName.empty() || !game->getCoopMod()
		|| !game->getCoopMod()->getServerOwner() || !game->getSavedGame()
		|| !game->getCoopMod()->isSeparateCampaign())
		return;
	Json::Value msg;
	msg["state"] = "separate_geoscape_event";
	msg["event"] = eventName;
	msg["ownerPlayerName"] = ownerPlayerName;
	std::string resolvedResearchName = researchName;
	if (resolvedResearchName.empty() && game->getMod())
		if (const RuleEvent* eventRule = game->getMod()->getEvent(eventName, false))
			for (const RuleResearch* rule : eventRule->getResearchList())
				if (rule && game->getSavedGame()->isResearched(rule, false))
				{
					resolvedResearchName = rule->getLookup().empty()
						? rule->getName() : rule->getLookup();
					break;
				}
	msg["researchName"] = resolvedResearchName;
	msg["bonusResearchName"] = bonusResearchName;
	Json::Value discovered(Json::arrayValue);
	if (game->getCoopMod()->_enable_research_sync)
		for (const RuleResearch* rule : game->getSavedGame()->getDiscoveredResearch())
			if (rule) discovered.append(rule->getName());
	msg["discoveredResearch"] = discovered;
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}
}
}
