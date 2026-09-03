#pragma once
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

#include "../Engine/State.h"
#include <map>
#include <algorithm>
#include <cmath>
#include "../Engine/Screen.h"
#include "../Geoscape/GeoscapeState.h"
#include "../Battlescape/BattlescapeState.h"
#include "../Savegame/BattleUnit.h"
#include "../Basescape/CraftInfoState.h"
#include "../Battlescape/BattlescapeGenerator.h"
#include "../Battlescape/BriefingState.h"
#include "../Engine/Action.h"
#include "../Engine/CrossPlatform.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/RNG.h"
#include "../Interface/ComboBox.h"
#include "../Interface/Frame.h"
#include "../Interface/Slider.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextEdit.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Mod/AlienDeployment.h"
#include "../Mod/AlienRace.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleAlienMission.h"
#include "../Mod/RuleCraft.h"
#include "../Mod/RuleGlobe.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleTerrain.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/MissionSite.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Ufo.h"

namespace OpenXcom
{

class TextButton;
class TextEdit;
class TextList;
class Window;
class Text;
class ComboBox;
class Slider;
class Frame;
class Craft;
class Screen;
class BattleUnit;
class File;

class HostMenu : public State
{
  private:
	TextButton *_btnCancel, *_tcpButtonHost;
	// coop (W1-P7 deliverable 6, WAVE1-RUNBOOK.md REV D owner ruling D-19 =
	// WV-D55): the HOST/lobby TURN MODE toggle, restoring the donor's shape
	// (`cbff7951d:HostMenu.cpp:812-834`). Flips Options::CoopTurnMode between
	// "parallel" and "traditional"; the label reflects it; visible only while the
	// rest of the hosting controls are.
	TextButton *_btnTurnMode;
	TextList *_lstSaves;
	TextEdit *_serverName, *_port, *_password;
	ComboBox *_cbxVisibility, *_cbxMaxPlayers, *_cbxRegions;
	Window *_window;
	Text *_txtTitle, *_lblServerName, *_lblPort, *_lblPassword;
	std::map<Surface *, bool> _surfaceBackup;
	std::vector<std::string> _visibilityTypes, _maxplayersTypes, _regionTypes;
	Craft *_craft;
	NewBattleSelectType _selectType;
	bool _isRightClick;
	std::vector<size_t> _filtered;
	static const int TFTD_DEPLOYMENTS = 22;
	std::string selectedRegion = "NORTH AMERICA";
	bool isListed = false;
	void convertUnits();
  public:
	/// Creates the New Host state.
	HostMenu();
	/// Cleans up the New Host state.
	~HostMenu();
	/// Resets state.
	void init() override;
	/// Handler for clicking the OK button
	void btnCancelClick(Action *action);
	void hostTCPGame(Action *action);
	void btnChatClick(Action* action);
	void cbxVisibilityChange(Action* action);
	void cbxMaxPlayersChange(Action* action);
	void cbxRegionChange(Action* action);
	/// Test hooks: drive the host window like a user would.
	void testHostWithVisibility(int comboIndex);
	/// Test hook: fill the host window's fields, then press START HOST.
	void testHostWithFields(int comboIndex, const std::string& server,
							const std::string& port, const std::string& password);
	bool hostControlsVisible() const;
	/// coop (W1-P7 deliverable 6, D-19): flips the HOST's remembered turn mode.
	/// The choice is per-MACHINE and per-SESSION - it is stamped onto every
	/// battle_offer this host sends (SS2.W1) and the client MIRRORS it, so only
	/// the host's setting ever matters and it only matters before a battle starts.
	void btnTurnModeClick(Action* action);
	/// coop (W1-P7 deliverable 6): keeps the toggle's label in sync with
	/// Options::CoopTurnMode and its visibility in sync with the rest of the
	/// hosting controls (hidden once a session is live).
	void updateTurnModeButton();
};

}
