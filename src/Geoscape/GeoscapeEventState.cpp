/*
 * Copyright 2010-2019 OpenXcom Developers.
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */
#include "GeoscapeEventState.h"
#include "GeoscapeState.h"
#include <algorithm>
#include <map>
#include "../Basescape/SellState.h"
#include "../CoopMod/SharedEcon.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/RNG.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Interface/TextButton.h"
#include "../Interface/ToggleTextButton.h"
#include "../Interface/Window.h"
#include "../Menu/CutsceneState.h"
#include "../Menu/ErrorMessageState.h"
#include "../Mod/City.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleEvent.h"
#include "../Mod/RuleInterface.h"
#include "../Mod/RuleRegion.h"
#include "../Mod/RuleSoldier.h"
#include "../Mod/RuleVideo.h"
#include "../Savegame/Base.h"
#include "../Savegame/GeoscapeEvent.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/Region.h"
#include "../Savegame/ResearchDiary.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Transfer.h"
#include "../Ufopaedia/Ufopaedia.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Geoscape Event window.
 * @param geoEvent Pointer to the event.
 */
GeoscapeEventState::GeoscapeEventState(const RuleEvent& eventRule,
	const std::string& ownerPlayerName, bool coopShared,
	const GeoscapeEventDisplay* replicated) : _ownerPlayerName(ownerPlayerName), _eventRule(eventRule), _coopShared(coopShared)
{
	_screen = false;

	// Create objects
	_window = new Window(this, 256, 176, 32, 12, POPUP_BOTH);
	_txtTitle = new Text(236, 32, 42, 23);
	_txtMessage = new Text(236, 96, 42, 58);
	_btnOk = new TextButton(108, 18, 48, 158);
	_btnItemsArriving = new ToggleTextButton(108, 18, 164, 158);
	_txtItem = new Text(114, 9, 44, 58);
	_txtQuantity = new Text(94, 9, 182, 58);
	_lstTransfers = new TextList(216, 80, 42, 69);

	// Set palette
	setInterface("geoscapeEvent");

	add(_window, "window", "geoscapeEvent");
	add(_txtTitle, "text1", "geoscapeEvent");
	add(_txtMessage, "text2", "geoscapeEvent");
	add(_btnOk, "button", "geoscapeEvent");
	add(_btnItemsArriving, "button", "geoscapeEvent");
	add(_txtItem, "text2", "geoscapeEvent");
	add(_txtQuantity, "text2", "geoscapeEvent");
	add(_lstTransfers, "list", "geoscapeEvent");

	centerAllSurfaces();

	// Set up objects
	_window->setBackground(_game->getMod()->getSurface(_eventRule.getBackground()));

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setWordWrap(true);
	_txtTitle->setText(tr(_eventRule.getName()));

	_txtMessage->setVerticalAlign(ALIGN_TOP);
	_txtMessage->setWordWrap(true);
	_txtMessage->setText(tr(_eventRule.getDescription()));
	if (_eventRule.alignBottom())
	{
		_txtMessage->setVerticalAlign(ALIGN_BOTTOM);
	}
	_txtMessage->setScrollable(true);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)& GeoscapeEventState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&GeoscapeEventState::btnOkClick, Options::keyOk);
	_btnOk->onKeyboardPress((ActionHandler)&GeoscapeEventState::btnOkClick, Options::keyCancel);

	_btnItemsArriving->setText(tr("STR_ITEMS_ARRIVING"));
	_btnItemsArriving->onMouseClick((ActionHandler)&GeoscapeEventState::btnItemsArrivingClick);

	_txtItem->setText(tr("STR_ITEM"));
	_txtQuantity->setText(tr("STR_QUANTITY_UC"));

	_lstTransfers->setColumns(2, 155, 41);
	_lstTransfers->setSelectable(true);
	_lstTransfers->setBackground(_window);
	_lstTransfers->setMargin(2);

	if (replicated)
	{
		// Display-only copy of the host's result: the authoritative host already
		// applied this event (funds, transfers, missions, research and RNG).
		if (!replicated->place.empty())
		{
			_txtTitle->setText(tr(_eventRule.getName()).arg(replicated->place));
			_txtMessage->setText(tr(_eventRule.getDescription()).arg(replicated->place));
		}
		for (const auto& row : replicated->rows)
			addTransferRow(row.first, row.second);
	}
	else
	{
		eventLogic();
	}

	_txtItem->setVisible(false);
	_txtQuantity->setVisible(false);
	_lstTransfers->setVisible(false);

	if (_eventRule.getInvert())
	{
		_btnItemsArriving->setText(tr("STR_SUMMARY"));
	}
	else if (_lstTransfers->getTexts() == 0 || !Options::oxceGeoscapeEventsInstantDelivery)
	{
		_btnOk->setX((_btnOk->getX() + _btnItemsArriving->getX()) / 2);
		_btnItemsArriving->setVisible(false);
	}
}

void GeoscapeEventState::addTransferRow(const std::string& itemType, const std::string& quantity)
{
	_lstTransfers->addRow(2, tr(itemType).c_str(), quantity.c_str());
	_display.rows.push_back(std::make_pair(itemType, quantity));
}

/**
 * Helper performing event logic.
 */
void GeoscapeEventState::eventLogic()
{
	if (coopReplicaDisplay()) return; // coop: a SHARED replica draws the host's picks; only the host runs this logic
	if (!_eventRule.getAdhocMissionScriptTags().empty())
	{
		auto* geo = _game->getGeoscapeState();
		geo->determineAlienMissions(false, &_eventRule, _ownerPlayerName);
	}

	SavedGame *save = _game->getSavedGame();
	Base *hq = save->getBases()->front();
	if (!_ownerPlayerName.empty())
		for (Base* candidate : *save->getBases())
			if (candidate && candidate->isOwnedByPlayer(_ownerPlayerName))
			{
				hq = candidate;
				break;
			}
	const Mod *mod = _game->getMod();
	const RuleEvent &rule = _eventRule;
	const bool playerFactionScore = !_ownerPlayerName.empty()
		&& _game->getCoopMod()->isSeparateCampaign()
		&& save->getSeparateCampaign().haveDifferentFactions();
	// coop Separate host: capture the rewards below for the replica.
	const SharedEcon::EventRewardSnapshot rewardsBefore = SharedEcon::snapshotEventRewards(_game, hq);

	RuleRegion *regionRule = nullptr;
	City* city = nullptr;
	if (!rule.getRegionList().empty())
	{
		size_t pickRegion = RNG::generate(0, rule.getRegionList().size() - 1);
		auto& regionName = rule.getRegionList().at(pickRegion);
		regionRule = _game->getMod()->getRegion(regionName, true);
		_coopRegion = regionName; // coop: the host's region pick, sent as an id
		std::string place = tr(regionName);

		if (rule.isCitySpecific())
		{
			size_t cities = regionRule->getCities()->size();
			if (cities > 0)
			{
				size_t pickCity = RNG::generate(0, cities - 1);
				city = regionRule->getCities()->at(pickCity);
				place = city->getName(_game->getLanguage());
				_coopCity = (int)pickCity; // coop
			}
		}

		_display.place = place;
		std::string titlePlus = tr(rule.getName()).arg(place);
		_txtTitle->setText(titlePlus);

		std::string messagePlus = tr(rule.getDescription()).arg(place);
		_txtMessage->setText(messagePlus);
	}

	// even if the event isn't city-specific, we'll still pick one city randomly to represent the region (and maybe even a country)
	if (regionRule)
	{
		if (!rule.isCitySpecific())
		{
			size_t cities = regionRule->getCities()->size();
			if (cities > 0)
			{
				size_t pickCity = RNG::generate(0, cities - 1);
				city = regionRule->getCities()->at(pickCity);
			}
		}
	}

	// 1. give/take score points
	if (playerFactionScore)
	{
		save->getSeparateCampaign().ensureFactionScores(
			save->getCoopPlayers(), save->getResearchScores().size());
		save->getSeparateCampaign().addFactionScore(_ownerPlayerName, rule.getPoints());
	}
	else if (regionRule)
	{
		for (auto* region : *_game->getSavedGame()->getRegions())
		{
			if (region->getRules() == regionRule)
			{
				region->addActivityXcom(rule.getPoints());
				break;
			}
		}
	}
	else
	{
		save->addResearchScore(rule.getPoints());
	}

	// 2. give/take funds (Separate: the event owner's wallet)
	{
		SeparateFundsScope wallet(save,
			_game->getCoopMod()->isSeparateCampaign() ? _ownerPlayerName : std::string());
		save->setFunds(save->getFunds() + rule.getFunds());
	}

	// Separate: a soldier the event spawns belongs to the event's owner (their
	// seat), as a hire belongs to its purchaser; without it the soldier stays
	// unowned (999) and no player's roster shows it.
	int spawnedSoldierOwner = -1;
	if (_game->getCoopMod()->isSeparateCampaign() && !_ownerPlayerName.empty())
	{
		const std::vector<std::string>& players = save->getCoopPlayers();
		auto seat = std::find(players.begin(), players.end(), _ownerPlayerName);
		if (seat != players.end())
			spawnedSoldierOwner = (int)(seat - players.begin());
	}

	// 3. spawn/transfer persons (soldiers, engineers, scientists, ...)
	const std::string& spawnedPersonType = rule.getSpawnedPersonType();
	if (rule.getSpawnedPersons() > 0 && !spawnedPersonType.empty())
	{
		if (spawnedPersonType == "STR_SCIENTIST")
		{
			Transfer* t = new Transfer(24);
			t->setOwnerPlayerName(_ownerPlayerName);
			t->setScientists(rule.getSpawnedPersons());
			hq->getTransfers()->push_back(t);
		}
		else if (spawnedPersonType == "STR_ENGINEER")
		{
			Transfer* t = new Transfer(24);
			t->setOwnerPlayerName(_ownerPlayerName);
			t->setEngineers(rule.getSpawnedPersons());
			hq->getTransfers()->push_back(t);
		}
		else
		{
			RuleSoldier* ruleSoldier = mod->getSoldier(spawnedPersonType);
			if (ruleSoldier)
			{
				for (int i = 0; i < rule.getSpawnedPersons(); ++i)
				{
					Transfer* t = new Transfer(24);
					t->setOwnerPlayerName(_ownerPlayerName);
					int nationality = _game->getSavedGame()->selectSoldierNationalityByLocation(_game->getMod(), ruleSoldier, city);
					Soldier* s = mod->genSoldier(save, ruleSoldier, nationality);
					YAML::YamlRootNodeReader reader(rule.getSpawnedSoldierTemplate(), "(spawned soldier template)");
					s->load(reader, mod, save, mod->getScriptGlobal(), true); // load from soldier template
					if (!rule.getSpawnedPersonName().empty())
					{
						s->setName(tr(rule.getSpawnedPersonName()));
					}
					else
					{
						s->genName();
					}
					if (spawnedSoldierOwner >= 0)
						s->setOwnerPlayerId(spawnedSoldierOwner);
					t->setSoldier(s);
					hq->getTransfers()->push_back(t);
				}
			}
		}
	}

	// 3. spawn/transfer multiple soldiers into the HQ
	{
		std::map<const RuleSoldier*, int> soldiersToTransfer;

		for (auto& pair : rule.getEveryMultiSoldierList())
		{
			const RuleSoldier* soldierRule = mod->getSoldier(pair.first, true);
			if (soldierRule)
			{
				soldiersToTransfer[soldierRule] += pair.second;
			}
		}

		if (!rule.getRandomMultiSoldierList().empty())
		{
			size_t pickSoldier = RNG::generate(0, rule.getRandomMultiSoldierList().size() - 1);
			auto& sublist = rule.getRandomMultiSoldierList().at(pickSoldier);
			for (auto& pair : sublist)
			{
				const RuleSoldier* soldierRule = mod->getSoldier(pair.first, true);
				if (soldierRule)
				{
					soldiersToTransfer[soldierRule] += pair.second;
				}
			}
		}

		for (auto& ts : soldiersToTransfer)
		{
			for (int i = 0; i < ts.second; ++i)
			{
				Transfer* t = new Transfer(24);
				t->setOwnerPlayerName(_ownerPlayerName);
				int nationality = _game->getSavedGame()->selectSoldierNationalityByLocation(_game->getMod(), ts.first, city);
				Soldier* s = mod->genSoldier(save, ts.first, nationality);
				YAML::YamlRootNodeReader reader(rule.getSpawnedSoldierTemplate(), "(spawned soldier template)");
				s->load(reader, mod, save, mod->getScriptGlobal(), true); // load from soldier template
				{
					// reset what may have been loaded
					s->genName();
				}
				if (spawnedSoldierOwner >= 0)
					s->setOwnerPlayerId(spawnedSoldierOwner);
				t->setSoldier(s);
				hq->getTransfers()->push_back(t);
			}
		}
	}

	// 3. spawn/transfer item into the HQ
	std::map<std::string, int> itemsToTransfer;

	for (auto& pair : rule.getEveryMultiItemList())
	{
		const RuleItem *itemRule = mod->getItem(pair.first, true);
		if (itemRule)
		{
			itemsToTransfer[itemRule->getType()] += pair.second;
		}
	}

	for (auto& itemName : rule.getEveryItemList())
	{
		const RuleItem *itemRule = mod->getItem(itemName, true);
		if (itemRule)
		{
			itemsToTransfer[itemRule->getType()] += 1;
		}
	}

	if (!rule.getRandomItemList().empty())
	{
		size_t pickItem = RNG::generate(0, rule.getRandomItemList().size() - 1);
		const RuleItem *randomItem = mod->getItem(rule.getRandomItemList().at(pickItem), true);
		if (randomItem)
		{
			itemsToTransfer[randomItem->getType()] += 1;
		}
	}

	if (!rule.getRandomMultiItemList().empty())
	{
		size_t pickItem = RNG::generate(0, rule.getRandomMultiItemList().size() - 1);
		auto& sublist = rule.getRandomMultiItemList().at(pickItem);
		for (auto& pair : sublist)
		{
			const RuleItem* itemRule = mod->getItem(pair.first, true);
			if (itemRule)
			{
				itemsToTransfer[itemRule->getType()] += pair.second;
			}
		}
	}

	if (!rule.getWeightedItemList().empty())
	{
		const RuleItem *randomItem = mod->getItem(rule.getWeightedItemList().choose(), true);
		if (randomItem)
		{
			itemsToTransfer[randomItem->getType()] += 1;
		}
	}

	for (auto& ti : itemsToTransfer)
	{
		if (rule.getInvert())
		{
			RuleItem* r = mod->getItem(ti.first, true);
			int removed = 0;
			for (auto* xbase : *save->getBases())
			{
				if (!_ownerPlayerName.empty() && !xbase->isOwnedByPlayer(_ownerPlayerName))
					continue;
				int bQty = xbase->getStorageItems()->getItem(r);
				if (bQty > 0)
				{
					int toRemove = std::min(bQty, ti.second);
					xbase->getStorageItems()->removeItem(r, toRemove);
					ti.second -= toRemove;
					removed += toRemove;
				}
				if (ti.second <= 0) break; // already removed enough
			}
			if (ti.second > 0)
			{
				for (auto* xbase : *save->getBases())
				{
					if (!_ownerPlayerName.empty() && !xbase->isOwnedByPlayer(_ownerPlayerName))
						continue;
					for (auto* xcraft : *xbase->getCrafts())
					{
						int cQty = xcraft->getItems()->getItem(r);
						if (cQty > 0 && xcraft->getStatus() != "STR_OUT")
						{
							int toRemove = std::min(cQty, ti.second);
							xcraft->getItems()->removeItem(r, toRemove);
							ti.second -= toRemove;
							removed += toRemove;
						}
						if (ti.second <= 0) break; // already removed enough
					}
					if (ti.second <= 0) break; // already removed enough
				}
			}

			std::ostringstream ss;
			ss << -removed;
			addTransferRow(ti.first, ss.str());
		}
		else if (Options::oxceGeoscapeEventsInstantDelivery)
		{
			hq->getStorageItems()->addItem(mod->getItem(ti.first, true), ti.second);

			std::ostringstream ss;
			ss << ti.second;
			addTransferRow(ti.first, ss.str());
		}
		else
		{
			Transfer* t = new Transfer(1);
			t->setOwnerPlayerName(_ownerPlayerName);
			t->setItems(mod->getItem(ti.first, true), ti.second);
			hq->getTransfers()->push_back(t);
		}
	}

	// 3b. spawn craft into the HQ
	const RuleCraft* craftRule = mod->getCraft(rule.getSpawnedCraftType(), true);
	if (craftRule)
	{
		Craft* craft = new Craft(craftRule, hq, save->getId(craftRule->getType()));
		craft->initFixedWeapons(mod);
		if (Options::oxceGeoscapeEventsInstantDelivery)
		{
			// same as manufacture
			craft->checkup();
			hq->getCrafts()->push_back(craft);
		}
		else
		{
			// same as buy
			craft->setStatus("STR_REFUELLING");
			Transfer* t = new Transfer(1);
			t->setOwnerPlayerName(_ownerPlayerName);
			t->setCraft(craft);
			hq->getTransfers()->push_back(t);
		}
	}

	_display.rewards = SharedEcon::describeEventRewards(_game, hq, rewardsBefore);

	// 4. give bonus research
	std::vector<const RuleResearch*> possibilities;

	for (auto* rRule : rule.getResearchList())
	{
		if (!save->isResearchedForBase(rRule->getName(), hq, false)
			|| save->hasUndiscoveredGetOneFree(rRule, true))
		{
			possibilities.push_back(rRule);
		}
	}

	// coop: the client's copy of a SEPARATE paired certain event (fired by the host's certain_event_fire with
	// research sync on) learns the host's topic instead of rolling its own - the research sync below is skipped for a paired copy, so its own
	// roll split the two players' research. The host's topic only if it is new to this player too; never a roll of its own.
	const std::pair<std::string, std::string>* coopHostPick = _coopShared ? _coopHostPick : nullptr;
	_coopHostPick = nullptr; // one window per arm
	if (coopHostPick)
	{
		const RuleResearch* hostResearch = coopHostPick->first.empty() ? nullptr : mod->getResearch(coopHostPick->first, false);
		bool hostTopicOpen = false;
		for (auto* p : possibilities)
			hostTopicOpen = hostTopicOpen || p == hostResearch;
		possibilities.clear();
		if (hostTopicOpen)
			possibilities.push_back(hostResearch);
	}
	std::vector<const RuleResearch*> topicsToCheck;
	if (!possibilities.empty())
	{
		size_t pickResearch = RNG::generate(0, possibilities.size() - 1);
		const RuleResearch *eventResearch = possibilities.at(pickResearch);
		_coopPickResearch = eventResearch->getName(); // coop: the host sends it with certain_event_fire (GeoscapeState::fireGeoscapeEvent)

		std::string name = eventResearch->getLookup().empty() ? eventResearch->getName() : eventResearch->getLookup();
		bool alreadyResearched = save->isResearchedForBase(name, hq, false); // this player has seen the pedia article already

		auto addResearchDiaryEntryForEvent = [&](const RuleResearch* discoveredResearch, DiscoverySourceType sourceType, const RuleEvent* sourceEvent, const RuleResearch* sourceResearch)
		{
			if (!save->isResearched(discoveredResearch, false) && !save->isResearchRuleStatusDisabled(discoveredResearch->getName()))
			{
				ResearchDiaryEntry* entry = new ResearchDiaryEntry(discoveredResearch);
				entry->setDate(save->getTime());
				entry->source.type = sourceType;
				if (sourceType == DiscoverySourceType::EVENT)
				{
					entry->source.event = sourceEvent;
					entry->source.name = sourceEvent->getName();
				}
				else // sourceType == DiscoverySourceType::FREE_FROM
				{
					entry->source.research = sourceResearch;
					entry->source.name = sourceResearch->getName();
				}
				save->addResearchDiaryEntry(entry);
			}
		};

		addResearchDiaryEntryForEvent(eventResearch, DiscoverySourceType::EVENT, &rule, nullptr);
		save->addFinishedResearch(eventResearch, mod, hq, true);
		topicsToCheck.push_back(eventResearch);
		_researchName = alreadyResearched ? "" : eventResearch->getName();

		if (!eventResearch->getLookup().empty())
		{
			const RuleResearch *lookupResearch = mod->getResearch(eventResearch->getLookup(), true);
			addResearchDiaryEntryForEvent(lookupResearch, DiscoverySourceType::EVENT, &rule, nullptr);
			save->addFinishedResearch(lookupResearch, mod, hq, true);
			_researchName = alreadyResearched ? "" : lookupResearch->getName();
		}

		const RuleResearch *syncBonus = nullptr;
		// coop: with the host's pick, the host's bonus (when this player does not know it yet) instead of a roll of its own
		const RuleResearch* coopHostBonus = coopHostPick && !coopHostPick->second.empty() ? mod->getResearch(coopHostPick->second, false) : nullptr;
		if (auto* bonus = coopHostPick ? (coopHostBonus && !save->isResearched(coopHostBonus, false) ? coopHostBonus : nullptr) : save->selectGetOneFree(eventResearch, hq))
		{
			syncBonus = bonus;
			_coopPickBonus = bonus->getName(); // coop: sent with certain_event_fire
			addResearchDiaryEntryForEvent(bonus, DiscoverySourceType::FREE_FROM, nullptr, eventResearch);
			save->addFinishedResearch(bonus, mod, hq, true);
			topicsToCheck.push_back(bonus);
			_bonusResearchName = bonus->getName();

			if (!bonus->getLookup().empty())
			{
				const RuleResearch *bonusLookup = mod->getResearch(bonus->getLookup(), true);
				addResearchDiaryEntryForEvent(bonusLookup, DiscoverySourceType::FREE_FROM, nullptr, eventResearch);
				save->addFinishedResearch(bonusLookup, mod, hq, true);
				_bonusResearchName = bonusLookup->getName();
			}
		}

		// coop SEPARATE research sync: research from an event the other player does
		// not also get (a random one, or a certain one they did not qualify for)
		// reaches them like a completed project, so both players can read the report.
		if (!_coopShared)
		{
			_game->getCoopMod()->sendResearchSync(alreadyResearched ? nullptr : eventResearch, syncBonus, eventResearch, hq, true); // coop: this world spawns the topics' events too (below)
		}
	}

	// Side effects:
	// 1. remove obsolete research projects from all bases
	// 2. handle items spawned by research
	// 3. handle events spawned by research
	const size_t coopEventsBefore = save->getGeoscapeEvents().size(); // coop
	// coop Separate: the host mirrors what the side effects changed
	// (research_effects, world_extras); the replica never re-runs them. A SHARED
	// replica still runs this eventLogic itself, so SHARED keeps the plain call.
	if (_game->getCoopMod()->isSeparateCampaign())
		SharedEcon::hostResearchSideEffects(_game, topicsToCheck, hq);
	else
		save->handlePrimaryResearchSideEffects(topicsToCheck, mod, hq);
	if (!_coopShared) // coop: the research sync above gives the other player these topics, so its world spawns the same events
		coopMarkResearchEvents(_game, coopEventsBefore);

	if (Options::oxceGeoscapeDebugLogMaxEntries > 0)
	{
		std::ostringstream ss;
		ss << "gameTime: " << save->getTime()->getFullString();
		ss << " eventPopup: " << rule.getName();
		save->getGeoscapeDebugLog().push_back(ss.str());
	}
}

/**
 *
 */
GeoscapeEventState::~GeoscapeEventState()
{
	// Empty by design
}

/**
 * Initializes the state.
 */
void GeoscapeEventState::init()
{
	State::init();

	if (!_eventRule.getMusic().empty())
	{
		_game->getMod()->playMusic(_eventRule.getMusic());
	}
}

/**
 * Closes the window and shows a pedia article if needed.
 * @param action Pointer to an action.
 */
void GeoscapeEventState::btnOkClick(Action *)
{
	_game->popState();

	if (!_eventRule.getCutscene().empty())
	{
		_game->pushState(new CutsceneState(_eventRule.getCutscene()));
		if (_game->getSavedGame()->getEnding() == END_NONE)
		{
			const RuleVideo* videoRule = _game->getMod()->getVideo(_eventRule.getCutscene(), true);
			if (videoRule->getWinGame()) _game->getSavedGame()->setEnding(END_WIN);
			if (videoRule->getLoseGame()) _game->getSavedGame()->setEnding(END_LOSE);
		}
		// coop: a window both machines show plays its cutscene at each player's own OK -
		// SHARED, and in SEPARATE co-op (not PvP: the alien side shows no event) a paired certain event or an event spawned by shared
		// research (main #197); only an ending is relayed (the first OK ends both campaigns); a private SEPARATE event keeps the relay
		if (_game->getCoopMod()->getCoopStatic() == true && _game->getSavedGame()->getEnding() == END_NONE // coop
			&& (_game->getCoopMod()->isSharedCampaign() || (_coopShared // coop
				&& _game->getCoopMod()->getCoopGamemode() != 2 && _game->getCoopMod()->getCoopGamemode() != 3))) // coop
			_game->getCoopMod()->allow_cutscene = false; // coop: CutsceneState::init skips the relay; GeoscapeState::init re-arms the latch
	}

	if (_game->getSavedGame()->getEnding() == END_NONE)
	{
		Base* base = _game->getSavedGame()->getCoopHqBase(); // coop: the stores check reads the base the rewards went to
		if (_game->getSavedGame()->getMonthsPassed() > -1 && Options::storageLimitsEnforced && base != 0 && base->storesOverfull())
		{
			_game->pushState(new SellState(base, 0));
			_game->pushState(new ErrorMessageState(tr("STR_STORAGE_EXCEEDED").arg(base->getName()), _palette, _game->getMod()->getInterface("debriefing")->getElement("errorMessage")->color, "BACK01.SCR", _game->getMod()->getInterface("debriefing")->getElement("errorPalette")->color));
		}
	}

	if (!_bonusResearchName.empty())
	{
		if (_replicatedResearchNames)
			Ufopaedia::openReplicatedEventArticle(_game, _bonusResearchName);
		else
			Ufopaedia::openArticle(_game, _bonusResearchName);
	}
	if (!_researchName.empty())
	{
		if (_replicatedResearchNames)
			Ufopaedia::openReplicatedEventArticle(_game, _researchName);
		else
			Ufopaedia::openArticle(_game, _researchName);
	}
}

/**
 * Toggles the view between the description and the ItemsArriving list.
 * @param action Pointer to an action.
 */
void GeoscapeEventState::btnItemsArrivingClick(Action *)
{
	if (_btnItemsArriving->getPressed())
	{
		_txtMessage->setVisible(false);

		_txtItem->setVisible(true);
		_txtQuantity->setVisible(true);
		_lstTransfers->setVisible(true);
	}
	else
	{
		_txtItem->setVisible(false);
		_txtQuantity->setVisible(false);
		_lstTransfers->setVisible(false);

		_txtMessage->setVisible(true);
	}
}

// coop: read-only accessors for the coop event relay and the geo_event_probe.
CoopEventPicks GeoscapeEventState::coopPicks() const
{
	CoopEventPicks p;
	p.region = _coopRegion; p.city = _coopCity; p.rows = _coopRows;
	p.research = _researchName; p.bonus = _bonusResearchName;
	return p;
}

std::vector<std::string> GeoscapeEventState::coopTexts() const
{
	std::vector<std::string> t{ _txtTitle->getText(), _txtMessage->getText() };
	for (size_t r = 0; r < _lstTransfers->getTexts(); ++r)
	{
		t.push_back(_lstTransfers->getCellText(r, 0));
		t.push_back(_lstTransfers->getCellText(r, 1));
	}
	return t;
}

// coop: a SHARED replica's window is drawn from the host's picks (ids), in this machine's own language.
const CoopEventPicks* GeoscapeEventState::_coopArmed = nullptr;
const std::pair<std::string, std::string>* GeoscapeEventState::_coopHostPick = nullptr; // coop
void GeoscapeEventState::coopArmHostPick(const std::pair<std::string, std::string>* pick) { _coopHostPick = pick; }
void GeoscapeEventState::coopArmDisplay(const CoopEventPicks* picks) { _coopArmed = picks; }

// coop: SEPARATE co-op with shared research. A topic both players learn spawns its event in
// both worlds - the researcher's side effects (GeoscapeState::time1Day, eventLogic) and the other player's research sync receiver
// (GeoscapeState::think, main #197) - each copy on its own timer. Marks the events spawned since `from` as windows both worlds hold,
// so btnOkClick plays their cutscene at each player's own OK without the relay. Not SHARED (one world), not with separate research,
// not PvP (the alien side never shows an event, GeoscapeState::fireGeoscapeEvent), not when the sender's world spawned nothing.
void GeoscapeEventState::coopMarkResearchEvents(Game* game, size_t from, bool senderSideEffects)
{
	connectionTCP* coop = game ? game->getCoopMod() : nullptr;
	SavedGame* save = game ? game->getSavedGame() : nullptr;
	if (!senderSideEffects || !coop || !save || !coop->getCoopStatic() || coop->isSharedCampaign() || !coop->_enable_research_sync
		|| coop->getCoopGamemode() == 2 || coop->getCoopGamemode() == 3)
		return;
	std::vector<GeoscapeEvent*>& events = save->getGeoscapeEvents();
	for (size_t i = from; i < events.size(); ++i)
		events[i]->setCoopBothWorlds(true);
}

bool GeoscapeEventState::coopReplicaDisplay()
{
	if (!_coopArmed) return false;
	const CoopEventPicks p = *_coopArmed;
	_coopArmed = nullptr; // one window per arm
	_coopRegion = p.region; _coopCity = p.city; _coopRows = p.rows;
	_researchName = p.research; _bonusResearchName = p.bonus;
	if (!_coopRegion.empty())
	{
		RuleRegion* regionRule = _game->getMod()->getRegion(_coopRegion, true);
		std::string place = tr(_coopRegion);
		if (_coopCity >= 0 && _coopCity < (int)regionRule->getCities()->size())
			place = regionRule->getCities()->at(_coopCity)->getName(_game->getLanguage());
		_txtTitle->setText(tr(_eventRule.getName()).arg(place));
		_txtMessage->setText(tr(_eventRule.getDescription()).arg(place));
	}
	for (const auto& row : _coopRows)
	{
		std::ostringstream ss;
		ss << row.second;
		_lstTransfers->addRow(2, tr(row.first).c_str(), ss.str().c_str());
	}
	return true;
}

}
