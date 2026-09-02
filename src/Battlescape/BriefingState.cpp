/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "BriefingState.h"
#include "BattlescapeState.h"
#include "BattlescapeGame.h"
#include "AliensCrashState.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Interface/TextButton.h"
#include "../Interface/Text.h"
#include "../Interface/Window.h"
#include "InventoryState.h"
#include "NextTurnState.h"
#include "../Mod/Mod.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Ufo.h"
#include "../Mod/AlienDeployment.h"
#include "../Mod/RuleUfo.h"
#include "../Engine/Options.h"
#include "../Engine/RNG.h"
#include "../Engine/Screen.h"
#include "../Menu/CutsceneState.h"
#include "../Savegame/AlienMission.h"
#include "../Mod/RuleAlienMission.h"
#include "../CoopMod/CoopHandshake.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Briefing screen.
 * @param game Pointer to the core game.
 * @param craft Pointer to the craft in the mission.
 * @param base Pointer to the base in the mission.
 * @param infoOnly Only show static info, when briefing is re-opened during the battle.
 * @param customBriefing Pointer to a custom briefing (used for Reinforcements notification).
 */
BriefingState::BriefingState(Craft *craft, Base *base, bool infoOnly, BriefingData *customBriefing) : _infoOnly(infoOnly), _disableCutsceneAndMusic(false)
{
	Options::baseXResolution = Options::baseXGeoscape;
	Options::baseYResolution = Options::baseYGeoscape;
	_game->getScreen()->resetDisplay(false);

	_screen = true;
	// Create objects
	_window = new Window(this, 320, 200, 0, 0);
	_btnOk = new TextButton(120, 18, 100, 164);
	_txtTitle = new Text(300, 32, 16, 24);
	_txtTarget = new Text(300, 17, 16, 40);
	_txtCraft = new Text(300, 17, 16, 56);
	_txtBriefing = new Text(274, 94, 16, 72);

	auto* battleSave = _game->getSavedGame()->getSavedBattle();

	std::string mission = battleSave->getMissionType();
	AlienDeployment *deployment = _game->getMod()->getDeployment(mission);
	if (mission == "STR_BASE_DEFENSE")
	{
		AlienDeployment* customDeployment = _game->getMod()->getDeployment(battleSave->getAlienCustomDeploy());
		if (customDeployment && !customDeployment->getBriefingData().desc.empty())
		{
			deployment = customDeployment;
		}
	}
	else
	{
		Ufo* ufo = 0;
		if (!deployment && craft)
		{
			ufo = dynamic_cast <Ufo*> (craft->getDestination());
			if (ufo) // landing site or crash site.
			{
				std::string ufoMissionName = ufo->getRules()->getType();
				if (!battleSave->getAlienCustomMission().empty())
				{
					// fake underwater UFO
					ufoMissionName = battleSave->getAlienCustomMission();
				}
				deployment = _game->getMod()->getDeployment(ufoMissionName);
			}
		}
	}

	// W1-P2 (WAVE1-RUNBOOK.md SS2.W1, WV-D9/WV-D28): a coop machine that did not
	// GENERATE this mission may have no Craft and no Ufo, so the
	// craft->getDestination() fallback above cannot run and `deployment` stays
	// null for every mission whose type is not itself a deployment name (the
	// normal case for STR_UFO_CRASH_RECOVERY) - which would drop this briefing
	// into the "should never happen" generic branch below. battle_offer carries
	// the HOST's already-resolved AlienDeployment type precisely for this. ONE
	// guarded coop call: a pure pass-through (and silent) in SP and outside a
	// coop battle, so vanilla is byte-identical.
	deployment = CoopHandshake::resolveBriefingDeployment(_game, deployment);

	std::string title = mission;
	std::string desc = title + "_BRIEFING";
	if (!deployment && !customBriefing) // none defined - should never happen, but better safe than sorry i guess.
	{
		setStandardPalette("PAL_GEOSCAPE", 0);
		_musicId = "GMDEFEND";
		_window->setBackground(_game->getMod()->getSurface("BACK16.SCR"));
	}
	else
	{
		BriefingData data = customBriefing ? *customBriefing : deployment->getBriefingData();
		setStandardPalette("PAL_GEOSCAPE", data.palette);
		_window->setBackground(_game->getMod()->getSurface(data.background));
		_txtCraft->setY(56 + data.textOffset);
		_txtBriefing->setY(72 + data.textOffset);
		_txtTarget->setVisible(data.showTarget);
		_txtCraft->setVisible(data.showCraft);
		_cutsceneId = data.cutscene;
		_musicId = data.music;
		if (!data.title.empty())
		{
			title = data.title;
		}
		if (!data.desc.empty())
		{
			desc = data.desc;
		}
	}
	_disableCutsceneAndMusic = _infoOnly && !customBriefing;

	add(_window, "window", "briefing");
	add(_btnOk, "button", "briefing");
	add(_txtTitle, "text", "briefing");
	add(_txtTarget, "text", "briefing");
	add(_txtCraft, "text", "briefing");
	add(_txtBriefing, "text", "briefing");

	centerAllSurfaces();

	// Set up objects
	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&BriefingState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&BriefingState::btnOkClick, Options::keyOk);
	_btnOk->onKeyboardPress((ActionHandler)&BriefingState::btnOkClick, Options::keyCancel);

	_txtTitle->setBig();
	_txtTarget->setBig();
	_txtCraft->setBig();

	// W1-P2 (SS2.W1 RE-MINT SUPPRESSION, WV-D28/WV-D42): on a coop host this
	// whole body already ran BEFORE the battle_offer was built -
	// CoopHandshake::mintMissionLabels() is a line-for-line replica of it - and
	// the offer told the client exactly what it produced. Re-running it here
	// would give the host DIFFERENT labels seconds later, so the two players
	// would read different mission names; the divergence is invisible to the
	// hash because strTarget/strCraftOrBase are saveBlob-hash-excluded
	// (SharedEcon.cpp:3974). The guard covers the FULL body, not just the
	// operation-name block, because the craft branch below writes strTarget
	// FIRST (the destination name) and the operation-name block then overwrites
	// it - guarding only the second half lets the first half clobber the name
	// the offer already shipped (traced by test_rw_mission_labels.py).
	// ONE guarded coop call; false in SP and for any battle with no coop
	// mission identity, so vanilla is byte-identical.
	if (!_infoOnly && !CoopHandshake::missionLabelsAlreadyMinted(battleSave))
	{
		std::string s;
		if (craft)
		{
			if (craft->getDestination())
			{
				s = craft->getDestination()->getName(_game->getLanguage());
				battleSave->setMissionTarget(s);
			}

			s = tr("STR_CRAFT_").arg(craft->getName(_game->getLanguage()));
			battleSave->setMissionCraftOrBase(s);
		}
		else if (base)
		{
			s = tr("STR_BASE_UC_").arg(base->getName());
			battleSave->setMissionCraftOrBase(s);
		}

		// random operation names
		if (craft || base)
		{
			if (!_game->getMod()->getOperationNamesFirst().empty())
			{
				std::ostringstream ss;
				int pickFirst = RNG::seedless(0, _game->getMod()->getOperationNamesFirst().size() - 1);
				ss << _game->getMod()->getOperationNamesFirst().at(pickFirst);
				if (!_game->getMod()->getOperationNamesLast().empty())
				{
					int pickLast = RNG::seedless(0, _game->getMod()->getOperationNamesLast().size() - 1);
					ss << " " << _game->getMod()->getOperationNamesLast().at(pickLast);
				}
				s = ss.str();
				battleSave->setMissionTarget(s);
			}
		}
	}

	if (!_game->getMod()->getOperationNamesFirst().empty())
		_txtTarget->setText(tr("STR_OPERATION_UC").arg(battleSave->getMissionTarget()));
	else
		_txtTarget->setText(battleSave->getMissionTarget());

	_txtCraft->setText(battleSave->getMissionCraftOrBase());

	_txtTitle->setText(tr(title));

	bool isPreview = battleSave->isPreview();
	if (isPreview)
	{
		if (battleSave->getCraftForPreview())
		{
			if (battleSave->getCraftForPreview()->getId() == RuleCraft::DUMMY_CRAFT_ID)
			{
				// we're using the same alienDeployment for the real craft preview and for the dummy craft preview,
				// but we want to have different briefing texts
				desc = desc + "_DUMMY";
			}
		}
		else
		{
			// base preview
			desc = desc + "_PREVIEW";
		}
	}
	_txtBriefing->setWordWrap(true);
	_txtBriefing->setText(tr(desc));

	if (_infoOnly) return;

	if (!isPreview && base && mission == "STR_BASE_DEFENSE")
	{
		auto* am = base->getRetaliationMission();

		// And make sure the base is unmarked (but only for vanilla retaliations, not for instant retaliations)
		if (am)
		{
			base->setRetaliationTarget(false);
		}

		if (am && am->getRules().isMultiUfoRetaliation())
		{
			// Remember that more UFOs may be coming
			am->setMultiUfoRetaliationInProgress(true);
		}
	}
}

/**
 *
 */
BriefingState::~BriefingState()
{

}

void BriefingState::init()
{
	State::init();
	if (_disableCutsceneAndMusic) return;

	if (!_cutsceneId.empty())
	{
		_game->pushState(new CutsceneState(_cutsceneId));

		// don't play the cutscene again when we return to this state
		_cutsceneId = "";
	}
	else
	{
		_game->getMod()->playMusic(_musicId);
	}
}

/**
 * Closes the window.
 * @param action Pointer to an action.
 */
void BriefingState::btnOkClick(Action *)
{
	_game->popState();
	Options::baseXResolution = Options::baseXBattlescape;
	Options::baseYResolution = Options::baseYBattlescape;
	_game->getScreen()->resetDisplay(false);
	if (_infoOnly) return;

	BattlescapeState *bs = new BattlescapeState;
	bs->getBattleGame()->spawnFromPrimedItems();
	BattlescapeTally tally = bs->getBattleGame()->tallyUnits();
	bool isPreview = _game->getSavedGame()->getSavedBattle()->isPreview();
	if (tally.liveAliens > 0 || isPreview)
	{
		_game->pushState(bs);
		_game->getSavedGame()->getSavedBattle()->setBattleState(bs);
		_game->pushState(new NextTurnState(_game->getSavedGame()->getSavedBattle(), bs));
		if (isPreview)
		{
			// skip InventoryState
			_game->getSavedGame()->getSavedBattle()->startFirstTurn();
			return;
		}
		// W1-P4 (WAVE1-RUNBOOK.md SS4 / ruling D3 = WV-D9 + WV-D34; MECHANISM
		// PINNED by WV-D43): in a coop battle the PRE-BATTLE EQUIP SCREEN IS
		// FROZEN on both machines for this wave. The host's equip would run
		// AFTER CoopHandshake::offerBattle() already snapshotted the blob the
		// client loads (connectionTCP.cpp:3544), so every item moved on this
		// screen is a silent items/saveBlob divergence - a gap the harness never
		// caught because no test ever equipped. Un-freezing belongs to the
		// synchronized-equip initiative (`inventory_move`), not to this wave.
		//
		// THE startFirstTurn() CALL IS NOT OPTIONAL (WV-D43). This push is the
		// host's ONLY non-preview route into SavedBattleGame::startFirstTurn():
		// grepping the tree finds exactly two callers, the preview branch three
		// lines above and InventoryState::btnOkClick (InventoryState.cpp:1174).
		// Skipping the push WITHOUT replacing that call would leave the host at
		// `_turn == 0` while the thin client's RW-FIX-TURN mirror forces 1 -
		// resurrecting the exact saveBlob divergence class that fix was built to
		// close - and would also skip randomizeItemLocations() / resetUnitTiles()
		// / the per-unit prepareNewTurn(false) / newTurnUpdateScripts()
		// (SavedBattleGame.cpp:1235-1260). So this branch is deliberately
		// byte-for-byte the preview path above; it is not a new mechanism.
		//
		// ONE guarded coop call. It is false in SP and outside a coop battle, so
		// the vanilla push below is byte-identical - proved by the mandatory SP
		// battle smoke, which must still land on
		// ['BattlescapeState','NextTurnState','InventoryState']. The
		// player-visible refusal is raised inside the hook, through the
		// _txtCoopWait presenter (SPIKE-RUNBOOK.md SS2.6), never vanilla
		// _warning.
		if (CoopHandshake::freezePreBattleEquip(_game))
		{
			_game->getSavedGame()->getSavedBattle()->startFirstTurn();
			return;
		}
		_game->pushState(new InventoryState(false, bs, 0));
	}
	else
	{
		Options::baseXResolution = Options::baseXGeoscape;
		Options::baseYResolution = Options::baseYGeoscape;
		_game->getScreen()->resetDisplay(false);
		delete bs;
		_game->pushState(new AliensCrashState);
	}
}

}
