#include "SeparateEcon.h"

#include "connectionTCP.h"
#include "SharedEcon.h"
#include "../Engine/Game.h"
#include "../Engine/Language.h"
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
#include "../Savegame/Transfer.h"
#include "../Savegame/Ufo.h"
#include "../Savegame/Vehicle.h"
#include "../Savegame/AlienMission.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/MissionSite.h"
#include "../Mod/RuleBaseFacility.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleEvent.h"
#include "../Mod/RuleResearch.h"
#include "../Mod/AlienDeployment.h"
#include "../Mod/RuleItem.h"
#include "../Mod/Unit.h"
#include "../Mod/Mod.h"
#include "../Mod/Armor.h"

#include <algorithm>
#include <map>
#include <set>
#include <sstream>

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

GeoscapeState* geo(Game* game)
{
	if (!game) return nullptr;
	for (State* state : game->getStates())
		if (GeoscapeState* gs = dynamic_cast<GeoscapeState*>(state)) return gs;
	return nullptr;
}
}

Craft* resolveCraft(Game* game, const Json::Value& obj)
{
	if (!game || !game->getSavedGame()) return nullptr;
	// The base by its index and key: a base_move can land between the sender
	// building the message and this machine reading it.
	Base* base = SharedEcon::resolveBaseReference(game, obj.get("baseId", -1).asInt(),
		obj.get("baseKey", 0).asInt());
	if (!base) return nullptr;
	int id = obj.get("craftId", -1).asInt();
	std::string type = obj.get("craftType", "").asString();
	for (Craft* craft : *base->getCrafts())
		if (craft->getId() == id && craft->getRules()->getType() == type) return craft;
	return nullptr;
}

Json::Value craftMessage(const char* state, Game* game, Craft* craft)
{
	Json::Value msg;
	msg["state"] = state;
	msg["baseId"] = findBaseIndex(game, craft ? craft->getBase() : nullptr);
	msg["baseKey"] = craft && craft->getBase() ? craft->getBase()->_coop_base_id : 0;
	msg["craftId"] = craft ? craft->getId() : -1;
	msg["craftType"] = craft ? craft->getRules()->getType() : "";
	return msg;
}

namespace
{
int seatForPlayerName(const std::string& playerName)
{
	if (playerName.empty()) return -1;
	for (int seat = 0; seat < connectionTCP::seatCount(); ++seat)
	{
		const std::string name = connectionTCP::seatName(seat);
		if (name == playerName) return seat;
	}
	return -1;
}

void reconcileVehicleOwners(Craft* craft)
{
	if (!craft || !craft->getBase()) return;
	const std::string baseOwner = craft->getBase()->getOwnerPlayerName();
	for (Vehicle* vehicle : *craft->getVehicles())
	{
		if (!vehicle) continue;
		if (vehicle->getOwnerPlayerName().empty())
		{
			// Vehicles from saves predating named ownership belong to the base
			// owner. This is stable across reconnects, unlike the old seat value.
			const std::string legacyOwner = !baseOwner.empty()
				? baseOwner : connectionTCP::seatName(vehicle->getCoop());
			vehicle->setOwnerPlayerName(legacyOwner);
		}
		const int seat = seatForPlayerName(vehicle->getOwnerPlayerName());
		if (seat >= 0) vehicle->setCoop(seat);
	}
}
}

void synchronizeVehicleOwners(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !save->isSeparateCoopCampaign())
	{
		return;
	}
	for (Base* base : *save->getBases())
		if (base)
			for (Craft* craft : *base->getCrafts())
				reconcileVehicleOwners(craft);
}

void trimInitialCraftCrews(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !save->isSeparateCoopCampaign()
		|| save->getMonthsPassed() != -1)
	{
		return;
	}
	const int playerCount = std::max(1,
		static_cast<int>(save->getCoopPlayers().size()));
	for (Base* base : *save->getBases())
	{
		if (!base || base->getOwnerPlayerName().empty()) continue;
		const int ownerSeat = seatForPlayerName(base->getOwnerPlayerName());
		if (ownerSeat < 0) continue;
		for (Craft* craft : *base->getCrafts())
		{
			if (!craft || craft->getMaxUnitsClamped() <= 0) continue;
			const int capacity = craft->getMaxUnitsClamped();
			// Divide odd capacities without creating extra physical places: the
			// first seats receive the remainder, all others receive the floor.
			const int quota = capacity / playerCount
				+ (ownerSeat < capacity % playerCount ? 1 : 0);
			int used = craft->getSpaceUsedByOwner(ownerSeat);
			if (used <= quota) continue;
			for (auto it = base->getSoldiers()->rbegin();
				it != base->getSoldiers()->rend() && used > quota; ++it)
			{
				Soldier* soldier = *it;
				if (!soldier || soldier->getCraft() != craft
					|| soldier->getOwnerPlayerId() != ownerSeat)
				{
					continue;
				}
				used -= soldier->getArmor()->getTotalSize();
				soldier->setCraft(nullptr);
			}
			craft->resetCustomDeployment();
		}
	}
}

int normalizeSoldierIds(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !save->isSeparateCoopCampaign())
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
	// Soldiers in transit are live soldiers too: a transfer can still hold a
	// player-local id from an imported world (PR #213 F12).
	auto livingSoldiers = [](Base* base)
	{
		std::vector<Soldier*> soldiers(base->getSoldiers()->begin(), base->getSoldiers()->end());
		for (Transfer* transfer : *base->getTransfers())
			if (transfer && transfer->getSoldier())
				soldiers.push_back(transfer->getSoldier());
		return soldiers;
	};
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		for (Soldier* soldier : livingSoldiers(base))
			if (soldier) reserved.insert(soldier->getId());
	}
	for (Soldier* soldier : *save->getDeadSoldiers())
		if (soldier) reserved.insert(soldier->getId());

	std::set<int> used;
	int changed = 0;
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		for (Soldier* soldier : livingSoldiers(base))
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

int normalizeCraftIds(Game* game)
{
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!save || !save->isSeparateCoopCampaign() || save->getSavedBattle())
	{
		return 0;
	}
	// The host owns every id. A replica adopts the host's already-unique world
	// and must never renumber a craft on its own.
	if (game->getCoopMod() && game->getCoopMod()->isCampaignReplica())
	{
		return 0;
	}

	// Vanilla gives every craft an id that is unique per craft type across the
	// whole world, and saves name a craft by that (type, id) pair: craft and UFO
	// destinations, escorts, interception orders, harness levers. Each player's
	// starting base was built in its own new-game world with its own id counters,
	// so the merged world held SKYRANGER-1 at two bases. The first base in world
	// order keeps its ids; a later duplicate takes the next free id of its type.
	// In-memory references (soldier seats, destinations) are pointers and follow
	// the craft. A craft in transit is a live craft too.
	auto livingCrafts = [](Base* base)
	{
		std::vector<Craft*> crafts(base->getCrafts()->begin(), base->getCrafts()->end());
		for (Transfer* transfer : *base->getTransfers())
			if (transfer && transfer->getCraft())
				crafts.push_back(transfer->getCraft());
		return crafts;
	};

	std::map<std::string, int> highest;
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		for (Craft* craft : livingCrafts(base))
			if (craft)
			{
				int& top = highest[craft->getRules()->getType()];
				top = std::max(top, craft->getId());
			}
	}

	// Raise each type's counter past every live id first, so a renumbered craft
	// and every later purchase or production get a fresh id.
	std::map<std::string, int> ids = save->getAllIds();
	bool raised = false;
	for (const auto& top : highest)
	{
		if (ids[top.first] <= top.second)
		{
			ids[top.first] = top.second + 1;
			raised = true;
		}
	}
	if (raised)
	{
		save->setAllIds(ids);
	}

	std::set<std::pair<std::string, int>> used;
	int changed = 0;
	for (Base* base : *save->getBases())
	{
		if (!base) continue;
		for (Craft* craft : livingCrafts(base))
		{
			if (!craft) continue;
			const std::string& type = craft->getRules()->getType();
			const int oldId = craft->getId();
			if (used.insert(std::make_pair(type, oldId)).second) continue;

			const int newId = save->getId(type);
			craft->setId(newId);
			used.insert(std::make_pair(type, newId));
			++changed;
			Log(LOG_INFO) << "Separate Campaign: duplicate craft id " << type << "-" << oldId
				<< " at " << base->getName() << " -> " << type << "-" << newId;
		}
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
		// An ownerless (legacy) base is the host's: billed once (PR #213 F13).
		const bool billed = base->getOwnerPlayerName().empty()
			? !save->getCoopPlayers().empty() && playerName == save->getCoopPlayers().front()
			: base->isOwnedByPlayer(playerName);
		if (!playerName.empty() && billed)
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
	if (state == "separate_ufopedia_status")
	{
		if (game && game->getCoopMod() && game->getCoopMod()->getServerOwner()
			&& game->getSavedGame())
		{
			const std::string rule = obj.get("rule", "").asString();
			const int status = obj.get("status", 0).asInt();
			const std::string player = game->getCoopMod()->getCurrentClientName();
			if (!player.empty() && !rule.empty() && status >= 0 && status <= 2)
				game->getSavedGame()->getSeparateCampaign().setUfopediaRuleStatus(
					player, rule, status);
		}
		return true;
	}
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
					}
			}
			// Private research: the host gave the event's topics to the owner's
			// profile, so adopt that profile's new topics at the owner's base.
			const Json::Value& ownerResearch = obj["ownerResearch"];
			if (!owner.empty() && researchBase && researchBase->isOwnedByPlayer(owner))
				for (Json::ArrayIndex i = 0; i < ownerResearch.size(); ++i)
				{
					const std::string name = ownerResearch[i].asString();
					if (!game->getSavedGame()->isResearchedForPlayer(name, owner, false))
						if (RuleResearch* rule = game->getMod()->getResearch(name, false))
						{
							adoptedArticle = rule->getLookup().empty()
								? rule->getName() : rule->getLookup();
							game->getSavedGame()->addFinishedResearch(
								rule, game->getMod(), researchBase, true);
						}
				}
			// The research side effects of these topics (obsolete projects, spawned
			// items and events, custom counters such as XCOM Files' Secret Files
			// unlocks) ran on the host and arrive as its results: research_effects and
			// world_extras. Re-running them here would roll this replica's own RNG
			// for a spawned event's countdown.
			// The event's own rewards at its owner's bases (items, crafts, persons).
			SharedEcon::applyEventRewards(game, obj["rewards"]);
			const Json::Value& playerFunds = obj["playerFunds"];
			if (playerFunds.isObject())
				for (const std::string& playerName : playerFunds.getMemberNames())
				{
					SeparateFundsScope wallet(game->getSavedGame(), playerName);
					game->getSavedGame()->setFundsRaw(playerFunds[playerName].asInt64());
				}
			if (RuleEvent* eventRule = game->getMod()->getEvent(
				obj.get("event", "").asString(), false))
				if (GeoscapeState* gs = geo(game))
				{
					// The replica only shows the host's result. Constructing the
					// window must not run eventLogic here: that would apply funds,
					// transfers, mission rolls and RNG to the replica a second time.
					if (owner.empty() || owner == connectionTCP::seatName(connectionTCP::localSeat()))
					{
						GeoscapeEventDisplay display;
						display.place = obj.get("place", "").asString();
						const Json::Value& rows = obj["rows"];
						for (Json::ArrayIndex i = 0; i < rows.size(); ++i)
							if (rows[i].isArray() && rows[i].size() == 2)
								display.rows.push_back(std::make_pair(
									rows[i][0].asString(), rows[i][1].asString()));
						GeoscapeEventState* eventState = new GeoscapeEventState(
							*eventRule, owner, false, &display);
						std::string article = obj.get("researchName", "").asString();
						if (article.empty()) article = adoptedArticle;
						eventState->setReplicatedResearchNames(
							article,
							obj.get("bonusResearchName", "").asString());
						gs->popup(eventState);
					}
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
	if (state == "separate_mission_research")
	{
		if (game && game->getCoopMod() && !game->getCoopMod()->getServerOwner()
			&& game->getSavedGame() && game->getMod())
		{
			const RuleResearch* research = game->getMod()->getResearch(
				obj.get("research", "").asString(), false);
			const std::string bonusName = obj.get("bonus", "").asString();
			const RuleResearch* bonus = bonusName.empty()
				? nullptr : game->getMod()->getResearch(bonusName, false);
			const AlienDeployment* deployment = game->getMod()->getDeployment(
				obj.get("deployment", "").asString(), false);
			if (research && deployment)
				game->getSavedGame()->handleResearchUnlockedByMissions(research,
					game->getMod(), deployment, nullptr,
					obj.get("ownerPlayerName", "").asString(), &bonus);
		}
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

void setUfopediaRuleStatus(Game* game, const std::string& rule, int status)
{
	if (!game || !game->getSavedGame() || rule.empty()) return;
	game->getSavedGame()->setUfopediaRuleStatus(rule, status);
	if (!game->getCoopMod() || !game->getCoopMod()->isSeparateCampaign()
		|| game->getCoopMod()->getServerOwner())
		return;
	Json::Value msg;
	msg["state"] = "separate_ufopedia_status";
	msg["rule"] = rule;
	msg["status"] = status;
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
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

std::string baseWalletOwner(Game* game, const Base* base)
{
	if (!game || !base || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign())
		return std::string();
	return base->getOwnerPlayerName();
}

bool showBaseNotification(Game* game, const Base* base)
{
	if (!game || !base || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign())
		return true;
	const std::string localName = connectionTCP::seatName(connectionTCP::localSeat());
	const std::string ownerName = base->getOwnerPlayerName();
	// Current Separate saves always have a persistent name. Keep _isForeignBase
	// only as a safe fallback for an old save while it is being upgraded.
	return ownerName.empty() ? !base->_isForeignBase : ownerName == localName;
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
		// Shared Research lets an item in any base unlock the topic. Take it from
		// the project's own base first, then from the same player's other bases,
		// and only then from another player's base.
		const RuleItem* needed = research->getNeededItem();
		std::vector<Base*> sources{ projectBase };
		for (Base* source : *save->getBases())
			if (source != projectBase
				&& source->getOwnerPlayerName() == projectBase->getOwnerPlayerName())
				sources.push_back(source);
		for (Base* source : *save->getBases())
			if (std::find(sources.begin(), sources.end(), source) == sources.end())
				sources.push_back(source);
		for (Base* source : sources)
			if (source->getStorageItems()->getItem(needed) > 0)
			{
				source->getStorageItems()->removeItem(needed, 1);
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
	// A visitor may buy, equip/crew with their own soldiers and vehicles, and
	// sack, rename or re-armor their own soldier stationed there (the validators
	// check the soldier's owner; armor comes from that base's stores, RU16).
	// Craft weapon rearm stays with the base owner (RU8).
	if (cmd == "buy" || cmd == "craft_equip" || cmd == "craft_assign"
		|| cmd == "sack" || cmd == "soldier_rename" || cmd == "soldier_armor")
		return true;
	return !remote && isHostSimulationResult(cmd);
}

bool allowsForeignBaseCommand(const std::string& cmd, bool remote,
	const Json::Value& payload, const Base* base, int seat)
{
	if (allowsForeignBaseCommand(cmd, remote)) return true;
	// RU17: a visitor may transfer their own soldiers out of another player's
	// base. Every entry must be one of the requester's soldiers there: items,
	// crafts, staff and the partner's soldiers stay with the base owner.
	if (cmd != "transfer" || !base) return false;
	const Json::Value& soldiers = payload["soldiers"];
	if (!soldiers.isArray() || soldiers.empty()) return false;
	if (payload["crafts"].isArray() && !payload["crafts"].empty()) return false;
	if (payload.get("scientists", 0).asInt() > 0 || payload.get("engineers", 0).asInt() > 0)
		return false;
	if (payload["items"].isArray())
		for (const auto& item : payload["items"])
			if (item.get("qty", 0).asInt() > 0) return false;
	for (const auto& id : soldiers)
	{
		const Soldier* owned = nullptr;
		for (const Soldier* s : *const_cast<Base*>(base)->getSoldiers())
			if (s->getId() == id.asInt() && s->getOwnerPlayerId() == seat) { owned = s; break; }
		if (!owned) return false;
	}
	return true;
}

bool isHostSimulationResult(const std::string& cmd)
{
	return cmd == "research_done" || cmd == "research_effects" || cmd == "world_extras"
		|| cmd == "fac_done" || cmd == "prod_done" || cmd == "transfer_arrived" || cmd == "base_destroyed"
		|| cmd == "patrol_prompt" || cmd == "base_damaged"
		|| cmd == "alien_base_found" || cmd == "alert" || cmd == "day_tick"
		|| cmd == "land_prompt" || cmd == "land_close";
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
	reconcileVehicleOwners(craft);
	int selected = 0;
	for (const Vehicle* vehicle : *craft->getVehicles())
		if (vehicle && vehicle->getRules()->getType() == itemType
			&& vehicle->getOwnerPlayerName() == player)
			++selected;
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
	const std::string playerName = connectionTCP::seatName(seat);
	int target = std::max(0, payload.get("count", 0).asInt());
	const std::string ownerPlayerName = base->getOwnerPlayerName();
	int ownerSeat = seatForPlayerName(ownerPlayerName);
	if (ownerSeat < 0) ownerSeat = 0;
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
			vehicle->setOwnerPlayerName(playerName);
			vehicle->setCoop(seat);
			craft->getVehicles()->push_back(vehicle);
		}
		// A base owner has priority if both seats selected the only physical tank.
		if (seat == ownerSeat && add < requestedAdd)
		{
			int claim = requestedAdd - add;
			for (Vehicle* vehicle : *craft->getVehicles())
				if (claim > 0 && vehicle && vehicle->getRules() == item
					&& vehicle->getOwnerPlayerName() != ownerPlayerName)
				{
					vehicle->setOwnerPlayerName(ownerPlayerName);
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
				craft->getVehicles()->end(), [item, &playerName](Vehicle* vehicle)
				{
					return vehicle && vehicle->getRules() == item
						&& vehicle->getOwnerPlayerName() == playerName;
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
	// count does not change. The host therefore appends persistent player names;
	// replicas derive their current runtime seats from those names.
	if (connectionTCP::getHost())
	{
		Json::Value owners(Json::arrayValue);
		for (Vehicle* vehicle : *craft->getVehicles())
			if (vehicle && vehicle->getRules() == item)
				owners.append(vehicle->getOwnerPlayerName());
		payload["vehicleOwners"] = owners;
	}
	else if (payload["vehicleOwners"].isArray())
	{
		Json::ArrayIndex index = 0;
		for (Vehicle* vehicle : *craft->getVehicles())
			if (vehicle && vehicle->getRules() == item
				&& index < payload["vehicleOwners"].size())
			{
				const std::string owner = payload["vehicleOwners"][index++].asString();
				vehicle->setOwnerPlayerName(owner);
				const int ownerSeat = seatForPlayerName(owner);
				if (ownerSeat >= 0) vehicle->setCoop(ownerSeat);
			}
	}
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
	const std::string& ownerPlayerName, const GeoscapeEventDisplay* display)
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
	// Private research: eventLogic gave the event's topics to the owner's
	// profile, not to the canonical list, so carry that profile instead.
	Json::Value ownerResearch(Json::arrayValue);
	if (!game->getCoopMod()->_enable_research_sync && !ownerPlayerName.empty())
		if (const auto* player = game->getSavedGame()->getSeparateCampaign().getPlayer(ownerPlayerName))
			for (const std::string& name : player->completedResearch)
				ownerResearch.append(name);
	msg["ownerResearch"] = ownerResearch;
	// The event may have changed its owner's wallet; the replica only displays
	// the event, so it adopts the authoritative balances instead.
	Json::Value playerFunds(Json::objectValue);
	for (const std::string& playerName : game->getSavedGame()->getCoopPlayers())
		playerFunds[playerName] = Json::Value::Int64(
			game->getSavedGame()->getSeparatePlayerFunds(playerName));
	msg["playerFunds"] = playerFunds;
	if (display)
	{
		msg["place"] = display->place;
		Json::Value rows(Json::arrayValue);
		for (const auto& row : display->rows)
		{
			Json::Value item(Json::arrayValue);
			item.append(row.first);
			item.append(row.second);
			rows.append(item);
		}
		msg["rows"] = rows;
		// What eventLogic gave or took at the owner's bases.
		Json::Value rewards;
		Json::CharReaderBuilder builder;
		std::istringstream text(display->rewards);
		std::string errors;
		if (!display->rewards.empty() && Json::parseFromStream(builder, text, &rewards, &errors))
			msg["rewards"] = rewards;
	}
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}
void hostMissionResearch(Game* game, const AlienDeployment* deployment,
	const RuleResearch* research, const RuleResearch* bonus,
	const std::string& ownerPlayerName)
{
	if (!game || !research || !deployment || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign()
		|| !game->getCoopMod()->getServerOwner())
		return;
	Json::Value msg;
	msg["state"] = "separate_mission_research";
	msg["deployment"] = deployment->getType();
	msg["research"] = research->getName();
	msg["bonus"] = bonus ? bonus->getName() : std::string();
	msg["ownerPlayerName"] = ownerPlayerName;
	game->getCoopMod()->sendTCPPacketData(msg.toStyledString());
}

void CampaignData::clear()
{
	_players.clear();
	_completedFactions.clear();
	_pendingFactionRechecks.clear();
	_pendingFactionFinaleOwner.clear();
	_loadedFromSave = false;
	_missionOwnerCursor = 0;
	_researchSharingEnabled = false;
	_researchModeKnown = false;
}

void CampaignData::load(const YAML::YamlNodeReader& reader)
{
	clear();
	if (!reader)
		return;

	_loadedFromSave = true;
	// The research mode the campaign last ran with. A save without the key
	// predates it and is treated as private research, the default.
	_researchModeKnown = true;
	reader.tryRead("researchSharing", _researchSharingEnabled);
	reader.tryRead("missionOwnerCursor", _missionOwnerCursor);
	std::vector<std::string> completedFactions;
	reader.tryRead("completedFactions", completedFactions);
	_completedFactions.insert(completedFactions.begin(), completedFactions.end());
	reader.tryRead("pendingFactionRechecks", _pendingFactionRechecks);
	reader.tryRead("pendingFactionFinaleOwner", _pendingFactionFinaleOwner);
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
		std::vector<std::string> disabled;
		playerReader.tryRead("disabledResearch", disabled);
		player.disabledResearch.insert(disabled.begin(), disabled.end());
		playerReader.tryRead("funds", player.funds);
		playerReader.tryRead("factionScores", player.factionScores);
		std::vector<std::string> generatedEvents;
		playerReader.tryRead("generatedEvents", generatedEvents);
		player.generatedEvents.insert(generatedEvents.begin(), generatedEvents.end());
		playerReader["missionRuns"].tryReadVal(player.missionRuns);
		playerReader["missionMarkers"].tryReadVal(player.missionMarkers);
		playerReader["ufopediaRuleStatus"].tryReadVal(player.ufopediaRuleStatus);
	}
}

void CampaignData::save(YAML::YamlNodeWriter writer) const
{
	writer.setAsMap();
	writer.write("version", 3);
	writer.write("researchSharing", _researchSharingEnabled);
	if (_missionOwnerCursor != 0)
		writer.write("missionOwnerCursor", _missionOwnerCursor);
	if (!_completedFactions.empty())
		writer.write("completedFactions", std::vector<std::string>(
			_completedFactions.begin(), _completedFactions.end()));
	if (!_pendingFactionRechecks.empty())
		writer.write("pendingFactionRechecks", _pendingFactionRechecks);
	if (!_pendingFactionFinaleOwner.empty())
		writer.write("pendingFactionFinaleOwner", _pendingFactionFinaleOwner);
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
		if (!entry.second.disabledResearch.empty())
			playerWriter.write("disabledResearch", std::vector<std::string>(
				entry.second.disabledResearch.begin(), entry.second.disabledResearch.end()));
		if (!entry.second.funds.empty())
			playerWriter.write("funds", entry.second.funds);
		if (!entry.second.factionScores.empty())
			playerWriter.write("factionScores", entry.second.factionScores);
		if (!entry.second.generatedEvents.empty())
			playerWriter.write("generatedEvents", std::vector<std::string>(
				entry.second.generatedEvents.begin(), entry.second.generatedEvents.end()));
		if (!entry.second.missionRuns.empty())
			playerWriter.write("missionRuns", entry.second.missionRuns);
		if (!entry.second.missionMarkers.empty())
			playerWriter.write("missionMarkers", entry.second.missionMarkers);
		if (!entry.second.ufopediaRuleStatus.empty())
			playerWriter.write("ufopediaRuleStatus", entry.second.ufopediaRuleStatus);
	}
}

void CampaignData::ensureFactionScores(const std::vector<std::string>& playerNames,
	size_t historySize)
{
	ensurePlayers(playerNames);
	if (historySize == 0) historySize = 1;
	for (const std::string& name : playerNames)
	{
		if (name.empty()) continue;
		std::vector<int>& scores = _players[name].factionScores;
		if (scores.size() > historySize)
			scores.erase(scores.begin(), scores.begin() + (scores.size() - historySize));
		else if (scores.size() < historySize)
			scores.insert(scores.begin(), historySize - scores.size(), 0);
	}
}

void CampaignData::newFactionScoreMonth(const std::vector<std::string>& playerNames,
	size_t historySize)
{
	ensureFactionScores(playerNames, historySize > 0 ? historySize - 1 : 0);
	for (const std::string& name : playerNames)
	{
		if (name.empty()) continue;
		std::vector<int>& scores = _players[name].factionScores;
		scores.push_back(0);
		if (scores.size() > historySize)
			scores.erase(scores.begin(), scores.begin() + (scores.size() - historySize));
	}
}

void CampaignData::addFactionScore(const std::string& playerName, int score)
{
	if (playerName.empty()) return;
	std::vector<int>& scores = _players[playerName].factionScores;
	if (scores.empty()) scores.push_back(0);
	scores.back() += score;
}

int CampaignData::getFactionScore(const std::string& playerName, size_t historyIndex) const
{
	const PlayerState* player = getPlayer(playerName);
	if (!player || historyIndex >= player->factionScores.size()) return 0;
	return player->factionScores[historyIndex];
}

int localFactionScore(Game* game, size_t historyIndex)
{
	if (!game || !game->getSavedGame() || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign()) return 0;
	const CampaignData& campaign = game->getSavedGame()->getSeparateCampaign();
	if (!campaign.haveDifferentFactions()) return 0;
	return campaign.getFactionScore(
		connectionTCP::seatName(connectionTCP::localSeat()), historyIndex);
}

bool CampaignData::wasEventGenerated(const std::string& playerName,
	const std::string& eventName) const
{
	const PlayerState* player = getPlayer(playerName);
	return player && player->generatedEvents.find(eventName) != player->generatedEvents.end();
}

void CampaignData::addGeneratedEvent(const std::string& playerName,
	const std::string& eventName)
{
	if (!playerName.empty() && !eventName.empty())
		_players[playerName].generatedEvents.insert(eventName);
}

int CampaignData::getMissionRuns(const std::string& playerName, const std::string& name) const
{
	const PlayerState* player = getPlayer(playerName);
	if (!player) return 0;
	auto found = player->missionRuns.find(name);
	return found == player->missionRuns.end() ? 0 : found->second;
}

void CampaignData::addMissionRun(const std::string& playerName, const std::string& name)
{
	if (!playerName.empty() && !name.empty()) ++_players[playerName].missionRuns[name];
}

int CampaignData::getMissionMarkerCount(const std::string& playerName,
	const std::string& name) const
{
	const PlayerState* player = getPlayer(playerName);
	if (!player) return 0;
	auto found = player->missionMarkers.find(name);
	return found == player->missionMarkers.end() ? 0 : found->second;
}

void CampaignData::addMissionMarker(const std::string& playerName, const std::string& name)
{
	if (!playerName.empty() && !name.empty()) ++_players[playerName].missionMarkers[name];
}

void CampaignData::reconcilePlayerNames(const std::vector<std::string>& roster)
{
	std::vector<std::string> stale;
	for (const auto& entry : _players)
		if (std::find(roster.begin(), roster.end(), entry.first) == roster.end())
			stale.push_back(entry.first);
	std::vector<std::string> missing;
	for (const auto& name : roster)
		if (!name.empty() && _players.find(name) == _players.end())
			missing.push_back(name);
	if (stale.empty() || missing.empty())
		return;
	if (stale.size() != 1 || missing.size() != 1)
	{
		Log(LOG_WARNING) << "[separate] " << stale.size() << " profile name(s) are not in the "
			<< "roster and " << missing.size() << " roster name(s) have no profile; "
			<< "no unambiguous mapping, profiles left unchanged";
		return;
	}
	const std::string& from = stale.front();
	const std::string& to = missing.front();
	_players[to] = _players[from];
	_players.erase(from);
	for (std::string& owner : _pendingFactionRechecks)
		if (owner == from) owner = to;
	if (_pendingFactionFinaleOwner == from)
		_pendingFactionFinaleOwner = to;
	Log(LOG_INFO) << "[separate] profile '" << from << "' now belongs to roster name '" << to << "'";
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
	{
		if (name.empty()) continue;
		std::vector<int64_t>& funds = _players[name].funds;
		if (funds.empty())
		{
			funds = initial;
		}
		else if (funds.size() > initial.size())
		{
			// Schema-2 player worlds could cross a month boundary at different
			// times. Schema 3 has one region/country timeline, and GraphsState
			// indexes those series with the local player's funds-history length.
			// Keep the newest entries (especially the current balance) and align
			// the history with the authoritative world's graph timeline.
			funds.erase(funds.begin(), funds.begin() + (funds.size() - initial.size()));
		}
		else if (funds.size() < initial.size())
		{
			// Extend the unknown older edge only; never change the current balance.
			funds.insert(funds.begin(), initial.size() - funds.size(), funds.front());
		}
	}
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
	_researchModeKnown = true;
}

bool CampaignData::disableResearch(const std::string& playerName, const std::string& research)
{
	return !playerName.empty() && !research.empty()
		&& _players[playerName].disabledResearch.insert(research).second;
}

bool CampaignData::enableResearch(const std::string& playerName, const std::string& research)
{
	PlayerState* player = getPlayer(playerName);
	return player && player->disabledResearch.erase(research) != 0;
}

bool CampaignData::isResearchDisabled(const std::string& playerName, const std::string& research) const
{
	const PlayerState* player = getPlayer(playerName);
	return player && player->disabledResearch.find(research) != player->disabledResearch.end();
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

void CampaignData::setUfopediaRuleStatus(const std::string& playerName,
	const std::string& rule, int status)
{
	if (!playerName.empty() && !rule.empty())
		_players[playerName].ufopediaRuleStatus[rule] = status;
}

bool CampaignData::getUfopediaRuleStatus(const std::string& playerName,
	const std::string& rule, int& status) const
{
	const PlayerState* player = getPlayer(playerName);
	if (!player) return false;
	auto it = player->ufopediaRuleStatus.find(rule);
	if (it == player->ufopediaRuleStatus.end()) return false;
	status = it->second;
	return true;
}

void CampaignData::migrateLegacyUfopediaStatus(
	const std::vector<std::string>& playerNames,
	const std::map<std::string, int>& status)
{
	if (playerNames.empty() || playerNames.front().empty()) return;
	PlayerState& host = _players[playerNames.front()];
	if (host.ufopediaRuleStatus.empty())
		host.ufopediaRuleStatus = status;
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

std::string CampaignData::getPlayerFaction(const std::string& playerName) const
{
	const PlayerState* player = getPlayer(playerName);
	return player ? player->faction : std::string();
}

bool CampaignData::isFactionCompleted(const std::string& faction) const
{
	return !faction.empty() && _completedFactions.count(faction) != 0;
}

bool CampaignData::isPlayerFactionCompleted(const std::string& playerName) const
{
	return isFactionCompleted(getPlayerFaction(playerName));
}

void CampaignData::completePlayerFaction(const std::string& playerName)
{
	const std::string faction = getPlayerFaction(playerName);
	if (!faction.empty()) _completedFactions.insert(faction);
}

void CampaignData::queueUnfinishedFactionRechecks(
	const std::vector<std::string>& playerNames)
{
	_pendingFactionRechecks.clear();
	std::set<std::string> queuedFactions;
	for (const std::string& name : playerNames)
	{
		const std::string faction = getPlayerFaction(name);
		if (faction.empty() || isFactionCompleted(faction)
			|| !queuedFactions.insert(faction).second)
			continue;
		_pendingFactionRechecks.push_back(name);
	}
}

bool CampaignData::allPlayerFactionsCompleted(const std::vector<std::string>& playerNames) const
{
	std::set<std::string> required;
	for (const std::string& name : playerNames)
	{
		const std::string faction = getPlayerFaction(name);
		if (!faction.empty()) required.insert(faction);
	}
	if (required.empty()) return false;
	for (const std::string& faction : required)
		if (!isFactionCompleted(faction)) return false;
	return true;
}

std::string CampaignData::nextMissionOwner(const std::vector<std::string>& playerNames)
{
	while (!_pendingFactionRechecks.empty())
	{
		const std::string owner = _pendingFactionRechecks.front();
		_pendingFactionRechecks.erase(_pendingFactionRechecks.begin());
		if (std::find(playerNames.begin(), playerNames.end(), owner) != playerNames.end()
			&& !isPlayerFactionCompleted(owner))
			return owner;
	}
	std::vector<std::string> valid;
	std::set<std::string> seenFactions;
	const bool distinctFactionCampaign = haveDifferentFactions();
	for (const auto& name : playerNames)
	{
		const PlayerState* player = getPlayer(name);
		if (name.empty() || !player || isPlayerFactionCompleted(name)) continue;
		// A, B, B is a two-faction campaign. Give faction B one generation
		// turn, not one turn per player, so its finale cannot be spawned twice.
		if (distinctFactionCampaign && !player->faction.empty()
			&& !seenFactions.insert(player->faction).second)
			continue;
		valid.push_back(name);
	}
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

bool resolveFactionFinalOutcome(Game* game, const std::string& ownerPlayerName,
	bool victory)
{
	if (!game || !game->getSavedGame() || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign() || ownerPlayerName.empty())
		return true;
	CampaignData& campaign = game->getSavedGame()->getSeparateCampaign();
	if (!campaign.haveDifferentFactions()) return true;
	// Starting a faction finale is a campaign-wide risk. Preserve the mod's
	// original loseGame behavior if that finale is lost or aborted.
	if (!victory) return true;
	campaign.completePlayerFaction(ownerPlayerName);
	const bool allCompleted = campaign.allPlayerFactionsCompleted(
		game->getSavedGame()->getCoopPlayers());
	if (!allCompleted)
		campaign.queueUnfinishedFactionRechecks(game->getSavedGame()->getCoopPlayers());
	return allCompleted;
}

std::string factionDisplayName(Game* game, const std::string& playerName)
{
	if (!game || !game->getSavedGame()) return playerName;
	const std::string faction = game->getSavedGame()->getSeparateCampaign()
		.getPlayerFaction(playerName);
	const std::string prefix = "difficulty:";
	if (faction.compare(0, prefix.size(), prefix) != 0 || !game->getLanguage())
		return faction.empty() ? playerName : faction;
	static const char* labels[] = {
		"STR_1_BEGINNER", "STR_2_EXPERIENCED", "STR_3_VETERAN",
		"STR_4_GENIUS", "STR_5_SUPERHUMAN"
	};
	const int difficulty = game->getSavedGame()->getSeparateCampaign()
		.getFactionDifficulty(playerName, -1);
	if (difficulty < 0 || difficulty >= static_cast<int>(sizeof(labels) / sizeof(labels[0])))
		return faction;
	return game->getLanguage()->getString(labels[difficulty]);
}

bool allowsFactionScript(Game* game, const std::string& ownerPlayerName)
{
	if (!game || !game->getSavedGame() || !game->getCoopMod()
		|| !game->getCoopMod()->isSeparateCampaign() || ownerPlayerName.empty())
		return true;
	return !game->getSavedGame()->getSeparateCampaign()
		.isPlayerFactionCompleted(ownerPlayerName);
}

}
}
