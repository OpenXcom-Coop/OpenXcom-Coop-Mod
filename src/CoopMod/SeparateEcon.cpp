#include "SeparateEcon.h"

#include "connectionTCP.h"
#include "SharedEcon.h"
#include "../Engine/Game.h"
#include "../Engine/Logger.h"
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
#include "../Savegame/Vehicle.h"
#include "../Savegame/AlienMission.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/MissionSite.h"
#include "../Mod/RuleBaseFacility.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleEvent.h"
#include "../Mod/RuleResearch.h"
#include "../Mod/RuleItem.h"
#include "../Mod/Unit.h"
#include "../Mod/Mod.h"
#include "../Mod/Armor.h"

#include <algorithm>
#include <map>
#include <set>

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

std::string vehicleCraftKey(const Craft* craft)
{
	if (!craft || !craft->getBase()) return std::string();
	return craft->getBase()->getOwnerPlayerName() + ":"
		+ std::to_string(craft->getBase()->_coop_base_id) + ":"
		+ craft->getRules()->getType() + ":" + std::to_string(craft->getId());
}

void rebuildVehicleSelections(Game* game, Craft* craft, const RuleItem* item)
{
	if (!game || !game->getSavedGame() || !craft || !item) return;
	SavedGame* save = game->getSavedGame();
	const std::string key = vehicleCraftKey(craft);
	for (const std::string& player : save->getCoopPlayers())
		save->getSeparateCampaign().setVehicleSelection(
			player, key, item->getType(), 0);
	std::map<int, int> counts;
	for (Vehicle* vehicle : *craft->getVehicles())
		if (vehicle && vehicle->getRules() == item)
			++counts[vehicle->getCoop()];
	for (const auto& count : counts)
	{
		const std::string player = connectionTCP::seatName(count.first);
		if (!player.empty())
			save->getSeparateCampaign().setVehicleSelection(
				player, key, item->getType(), count.second);
	}
}
}

int normalizeSoldierIds(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !save->isCoopSave()
		|| save->getCampaignType() != CoopCampaignType::Separate)
	{
		return 0;
	}

	// Imported Separate bases used to retain their player-local Soldier ids.
	// Reserve every original id first so a replacement can never collide with a
	// later base whose roster has not been visited yet. Fill the lowest free id
	// instead of max+1 so player units always remain below MAX_SOLDIER_ID even in
	// long-running or heavily modded campaigns.
	int nextId = 1;
	std::set<int> reserved;
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		for (Soldier* soldier : *base->getSoldiers())
			if (soldier) reserved.insert(soldier->getId());
	}
	for (Soldier* soldier : *save->getDeadSoldiers())
		if (soldier) reserved.insert(soldier->getId());

	std::set<int> used;
	int changed = 0;
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		for (Soldier* soldier : *base->getSoldiers())
		{
			if (!soldier) continue;
			const int oldId = soldier->getId();
			if (used.insert(oldId).second) continue;

			while (reserved.count(nextId)) ++nextId;
			const int newId = nextId++;
			if (Craft* craft = soldier->getCraft())
				craft->remapPilotId(oldId, newId);
			soldier->setId(newId);
			used.insert(newId);
			reserved.insert(newId);
			++changed;
			Log(LOG_INFO) << "Separate Campaign: upgraded duplicate soldier id "
				<< oldId << " -> " << newId << " for " << soldier->getName();
		}
	}

	// New hires use SavedGame's STR_SOLDIER counter. Keep it beyond every
	// migrated/live/dead id or the next purchase could recreate the collision.
	int highestId = 0;
	for (int id : reserved) highestId = std::max(highestId, id);
	std::map<std::string, int> ids = save->getAllIds();
	if (ids["STR_SOLDIER"] <= highestId)
	{
		ids["STR_SOLDIER"] = highestId + 1;
		save->setAllIds(ids);
	}

	return changed;
}

int playerMaintenance(Game* game, const std::string& playerName)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !game->getCoopMod() || !game->getCoopMod()->isSeparateCampaign())
		return save ? save->getBaseMaintenance() : 0;

	int total = 0;
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		if (!playerName.empty() && base->isOwnedByPlayer(playerName))
		{
			total += base->getMonthlyMaintenace();
		}
	}
	return total;
}

int localPlayerMaintenance(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !game->getCoopMod() || !game->getCoopMod()->isSeparateCampaign())
		return save ? save->getBaseMaintenance() : 0;

	const std::string playerName = connectionTCP::seatName(connectionTCP::localSeat());
	int total = playerMaintenance(game, playerName);
	// Ownerless bases only exist in legacy saves before their ownership upgrade.
	for (Base* base : *save->getBases())
		if (base && base->getOwnerPlayerName().empty() && !base->_isForeignBase)
			total += base->getMonthlyMaintenace();
	return total;
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
			const std::string owner = obj.get("ownerPlayerName", "").asString();
			Base* researchBase = nullptr;
			for (Base* candidate : *game->getSavedGame()->getBases())
				if (candidate && (owner.empty()
					? !candidate->_isForeignBase : candidate->isOwnedByPlayer(owner)))
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
	// Ownership exists only to separate faction-restricted content. If every
	// player selected the same faction, old saves may still contain an owner on
	// a target, but that target is cooperative and must remain usable by both.
	if (!game->getSavedGame()
		|| !game->getSavedGame()->getSeparateCampaign().haveDifferentFactions())
		return true;
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
		const int capacity = craft->getMaxUnitsClamped();
		const int ownerAvailable = (capacity + 1) / 2
			- craft->getSpaceUsedByOwner(seat);
		const int physicalAvailable = capacity - craft->getSpaceUsed();
		const int space = std::max(0, std::min(ownerAvailable, physicalAvailable));
		if (craft->validateAddingSoldier(space, soldier) != CPE_None)
			{ failReason = "STR_NOT_ENOUGH_CRAFT_SPACE"; return false; }
	}
	return true;
}

bool validateVehicleEquip(Game* game, const Json::Value& payload, Base* base,
	int /*seat*/, int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!game || !base) { failReason = "base not found"; return false; }
	const RuleItem* item = game->getMod()->getItem(
		payload.get("item", "").asString(), false);
	if (!item || !item->getVehicleUnit())
		{ failReason = "unknown vehicle"; return false; }
	return true;
}

bool validateCraftEquip(Game* game, const Json::Value& payload, Base* base,
	int seat, int64_t& cost, std::string& failReason)
{
	cost = 0;
	if (!game || !base) { failReason = "base not found"; return false; }
	const RuleItem* item = game->getMod()->getItem(
		payload.get("item", "").asString(), false);
	if (!item) { failReason = "unknown item"; return false; }
	if (item->getVehicleUnit())
		return validateVehicleEquip(game, payload, base, seat, cost, failReason);
	if (!base->isOwnedByPlayer(connectionTCP::seatName(seat)))
	{
		failReason = "Only the base owner can change craft equipment";
		return false;
	}
	return true;
}

int vehicleSelectionCount(Game* game, Craft* craft,
	const std::string& itemType, int seat)
{
	if (!game || !game->getSavedGame() || !craft) return 0;
	const std::string player = connectionTCP::seatName(seat);
	CampaignData& profiles = game->getSavedGame()->getSeparateCampaign();
	const std::string key = vehicleCraftKey(craft);
	int selected = profiles.getVehicleSelection(player, key, itemType);
	if (selected == 0)
	{
		// Safe upgrade for saves created before vehicleSelections: Vehicle::coop
		// already persisted the controlling seat, so reconstruct the profile.
		for (const Vehicle* vehicle : *craft->getVehicles())
			if (vehicle && vehicle->getRules()->getType() == itemType
				&& vehicle->getCoop() == seat)
				++selected;
		if (selected > 0)
			profiles.setVehicleSelection(player, key, itemType, selected);
	}
	return selected;
}

void applyVehicleEquip(Game* game, Json::Value& payload, Base* base, int seat)
{
	if (!game || !base) return;
	Craft* craft = nullptr;
	const int craftId = payload.get("craftId", -1).asInt();
	const std::string craftType = payload.get("craftType", "").asString();
	for (Craft* candidate : *base->getCrafts())
		if (candidate->getId() == craftId
			&& candidate->getRules()->getType() == craftType)
		{ craft = candidate; break; }
	const RuleItem* item = game->getMod()->getItem(
		payload.get("item", "").asString(), false);
	if (!craft || !item || !item->getVehicleUnit()) return;

	ItemContainer* store = base->getStorageItems();
	const int current = vehicleSelectionCount(game, craft, item->getType(), seat);
	int target = std::max(0, payload.get("count", 0).asInt());
	int ownerSeat = base->isOwnedByPlayer(connectionTCP::seatName(1)) ? 1 : 0;
	if (target > current)
	{
		const int requestedAdd = target - current;
		int add = std::min(requestedAdd, store->getItem(item));
		const int size = item->getVehicleUnit()->getArmor()->getTotalSize();
		// The authoritative host must validate against the requesting player's
		// quota, not against the host process's local seat.
		add = std::min(add, craft->validateAddingVehicles(size, seat));
		const RuleItem* ammo = item->getVehicleClipAmmo();
		const int ammoPerVehicle = item->getVehicleClipsLoaded();
		if (ammo && ammoPerVehicle > 0)
			add = std::min(add, store->getItem(ammo) / ammoPerVehicle);
		for (int i = 0; i < add; ++i)
		{
			store->removeItem(item, 1);
			if (ammo && ammoPerVehicle > 0)
				store->removeItem(ammo, ammoPerVehicle);
			Vehicle* vehicle = new Vehicle(item, item->getVehicleClipSize(), size);
			vehicle->setCoop(seat);
			craft->getVehicles()->push_back(vehicle);
		}
		// A base owner has priority if both seats selected the only physical tank.
		if (seat == ownerSeat && add < requestedAdd)
		{
			int claim = requestedAdd - add;
			for (Vehicle* vehicle : *craft->getVehicles())
				if (claim > 0 && vehicle && vehicle->getRules() == item
					&& vehicle->getCoop() != ownerSeat)
				{
					vehicle->setCoop(ownerSeat);
					--claim;
				}
		}
	}
	else if (target < current)
	{
		const int remove = current - target;
		const RuleItem* ammo = item->getVehicleClipAmmo();
		const int ammoPerVehicle = item->getVehicleClipsLoaded();
		for (int i = 0; i < remove; ++i)
		{
			auto it = std::find_if(craft->getVehicles()->begin(),
				craft->getVehicles()->end(), [item, seat](Vehicle* vehicle)
				{
					return vehicle && vehicle->getRules() == item
						&& vehicle->getCoop() == seat;
				});
			if (it == craft->getVehicles()->end()) break;
			delete *it;
			craft->getVehicles()->erase(it);
			store->addItem(item, 1);
			if (ammo && ammoPerVehicle > 0)
				store->addItem(ammo, ammoPerVehicle);
		}
	}
	craft->resetCustomDeployment();
	// Vehicle count alone cannot replicate an owner-priority claim because the
	// count does not change. The host therefore appends the authoritative seat
	// allocation, and replicas adopt it after applying the physical inventory.
	if (connectionTCP::getHost())
	{
		Json::Value owners(Json::arrayValue);
		for (Vehicle* vehicle : *craft->getVehicles())
			if (vehicle && vehicle->getRules() == item)
				owners.append(vehicle->getCoop());
		payload["vehicleOwners"] = owners;
	}
	else if (payload["vehicleOwners"].isArray())
	{
		Json::ArrayIndex index = 0;
		for (Vehicle* vehicle : *craft->getVehicles())
			if (vehicle && vehicle->getRules() == item
				&& index < payload["vehicleOwners"].size())
				vehicle->setCoop(payload["vehicleOwners"][index++].asInt());
	}
	rebuildVehicleSelections(game, craft, item);
	payload["count"] = vehicleSelectionCount(game, craft, item->getType(), seat);
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
void CampaignData::clear()
{
	_players.clear();
	_loadedFromSave = false;
	_missionOwnerCursor = 0;
}

void CampaignData::load(const YAML::YamlNodeReader& reader)
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
		playerReader.tryRead("funds", player.funds);
		for (const auto& selection : playerReader["vehicleSelections"].children())
		{
			const std::string craft = selection["craft"].readVal<std::string>("");
			const std::string item = selection["item"].readVal<std::string>("");
			const int count = selection["count"].readVal<int>(0);
			if (!craft.empty() && !item.empty() && count > 0)
				player.vehicleSelections[craft][item] = count;
		}

	}
}

void CampaignData::save(YAML::YamlNodeWriter writer) const
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
		if (!entry.second.funds.empty())
			playerWriter.write("funds", entry.second.funds);
		if (!entry.second.vehicleSelections.empty())
		{
			auto selections = playerWriter["vehicleSelections"];
			selections.setAsSeq();
			for (const auto& craft : entry.second.vehicleSelections)
				for (const auto& item : craft.second)
					if (item.second > 0)
					{
						auto selection = selections.write();
						selection.setAsMap();
						selection.write("craft", craft.first);
						selection.write("item", item.first);
						selection.write("count", item.second);
					}
		}
	}
}

void CampaignData::ensurePlayers(const std::vector<std::string>& playerNames)
{
	for (const auto& name : playerNames)
		if (!name.empty())
			_players.emplace(name, PlayerState());
}

void CampaignData::ensurePlayerFunds(const std::vector<std::string>& playerNames,
	const std::vector<int64_t>& legacyFunds)
{
	ensurePlayers(playerNames);
	std::vector<int64_t> initial = legacyFunds;
	if (initial.empty()) initial.push_back(0);
	for (const auto& name : playerNames)
		if (!name.empty() && _players[name].funds.empty())
			_players[name].funds = initial;
}

std::vector<int64_t>* CampaignData::getPlayerFunds(const std::string& playerName)
{
	PlayerState* player = getPlayer(playerName);
	return player ? &player->funds : nullptr;
}

const std::vector<int64_t>* CampaignData::getPlayerFunds(const std::string& playerName) const
{
	const PlayerState* player = getPlayer(playerName);
	return player ? &player->funds : nullptr;
}

void CampaignData::setResearchSharingEnabled(bool enabled)
{
	_researchSharingEnabled = enabled;
}

void CampaignData::migrateLegacyResearch(const std::vector<std::string>& playerNames,
	const std::vector<std::string>& completedResearch)
{
	if (_loadedFromSave || playerNames.empty() || playerNames.front().empty())
		return;
	ensurePlayers(playerNames);
	for (const auto& research : completedResearch)
		addCompletedResearch(playerNames.front(), research);
	_loadedFromSave = true;
}

CampaignData::PlayerState* CampaignData::getPlayer(const std::string& playerName)
{
	auto it = _players.find(playerName);
	return it == _players.end() ? nullptr : &it->second;
}

const CampaignData::PlayerState* CampaignData::getPlayer(const std::string& playerName) const
{
	auto it = _players.find(playerName);
	return it == _players.end() ? nullptr : &it->second;
}

void CampaignData::setFaction(const std::string& playerName, const std::string& faction)
{
	if (!playerName.empty())
		_players[playerName].faction = faction;
}

void CampaignData::setFactionResearch(const std::string& playerName,
	const std::vector<std::string>& research)
{
	if (playerName.empty()) return;
	PlayerState& player = _players[playerName];
	player.factionResearch.insert(research.begin(), research.end());
}

bool CampaignData::hasFactionResearch(const std::string& playerName,
	const std::string& research) const
{
	const PlayerState* player = getPlayer(playerName);
	return player && player->factionResearch.find(research) != player->factionResearch.end();
}

bool CampaignData::addCompletedResearch(const std::string& playerName, const std::string& research)
{
	return !playerName.empty() && !research.empty()
		&& _players[playerName].completedResearch.insert(research).second;
}

void CampaignData::replaceCompletedResearch(const std::string& playerName,
	const std::set<std::string>& research)
{
	if (!playerName.empty())
		_players[playerName].completedResearch = research;
}

bool CampaignData::removeCompletedResearch(const std::string& playerName, const std::string& research)
{
	PlayerState* player = getPlayer(playerName);
	return player && player->completedResearch.erase(research) != 0;
}

bool CampaignData::completeResearch(const std::string& playerName, const std::string& research)
{
	// Profiles are exclusively the private-research store. Shared Research uses
	// SavedGame::_discovered, exactly like Shared Campaign.
	return addCompletedResearch(playerName, research);
}

bool CampaignData::hasCompletedResearch(const std::string& playerName, const std::string& research) const
{
	const PlayerState* player = getPlayer(playerName);
	return player && player->completedResearch.find(research) != player->completedResearch.end();
}

bool CampaignData::haveDifferentFactions() const
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

std::string CampaignData::nextMissionOwner(const std::vector<std::string>& playerNames)
{
	std::vector<std::string> valid;
	for (const auto& name : playerNames)
		if (!name.empty() && getPlayer(name)) valid.push_back(name);
	if (valid.empty()) return std::string();
	const std::string owner = valid[_missionOwnerCursor % valid.size()];
	_missionOwnerCursor = (_missionOwnerCursor + 1) % valid.size();
	return owner;
}

int CampaignData::getFactionDifficulty(const std::string& playerName, int fallback) const
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

int CampaignData::getVehicleSelection(const std::string& playerName,
	const std::string& craftKey, const std::string& itemType) const
{
	const PlayerState* player = getPlayer(playerName);
	if (!player) return 0;
	auto craft = player->vehicleSelections.find(craftKey);
	if (craft == player->vehicleSelections.end()) return 0;
	auto item = craft->second.find(itemType);
	return item == craft->second.end() ? 0 : item->second;
}

void CampaignData::setVehicleSelection(const std::string& playerName,
	const std::string& craftKey, const std::string& itemType, int count)
{
	if (playerName.empty() || craftKey.empty() || itemType.empty()) return;
	PlayerState& player = _players[playerName];
	if (count > 0)
		player.vehicleSelections[craftKey][itemType] = count;
	else
	{
		auto craft = player.vehicleSelections.find(craftKey);
		if (craft == player.vehicleSelections.end()) return;
		craft->second.erase(itemType);
		if (craft->second.empty()) player.vehicleSelections.erase(craft);
	}
}
}
}
