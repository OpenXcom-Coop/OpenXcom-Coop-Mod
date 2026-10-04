#include "SeparateResearchModeWarningState.h"

#include "connectionTCP.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{
SeparateResearchModeWarningState::SeparateResearchModeWarningState()
{
	_screen = false;
	_window = new Window(this, 316, 160, 2, 20, POPUP_BOTH);
	_text = new Text(296, 92, 12, 35);
	_useSeparate = new TextButton(148, 24, 8, 142);
	_keepShared = new TextButton(148, 24, 164, 142);
	setInterface("craftError");
	add(_window, "window", "craftError");
	add(_text, "text1", "craftError");
	add(_useSeparate, "button", "craftError");
	add(_keepShared, "button", "craftError");
	centerAllSurfaces();
	setWindowBackground(_window, "craftError");
	_text->setAlign(ALIGN_CENTER);
	_text->setVerticalAlign(ALIGN_MIDDLE);
	_text->setWordWrap(true);
	_text->setText("Players selected different factions. Separate Research is recommended. You can change this later in Multiplayer Settings.");
	_useSeparate->setText("Use Separate Research");
	_useSeparate->onMouseClick((ActionHandler)&SeparateResearchModeWarningState::btnUseSeparateClick);
	_useSeparate->onKeyboardPress((ActionHandler)&SeparateResearchModeWarningState::btnUseSeparateClick, Options::keyOk);
	_keepShared->setText("Keep Shared Research");
	_keepShared->onMouseClick((ActionHandler)&SeparateResearchModeWarningState::btnKeepSharedClick);
	_keepShared->onKeyboardPress((ActionHandler)&SeparateResearchModeWarningState::btnKeepSharedClick, Options::keyCancel);
}

void SeparateResearchModeWarningState::btnUseSeparateClick(Action*)
{
	Options::EnableResearchSync = false;
	if (_game->getCoopMod())
	{
		_game->getCoopMod()->_enable_research_sync = false;
		if (_game->getSavedGame())
			_game->getSavedGame()->setSeparateResearchSharingEnabled(false, _game->getMod());
		Json::Value root;
		root["state"] = "research_sync_option";
		root["enabled"] = false;
		_game->getCoopMod()->sendTCPPacketData(root.toStyledString());
	}
	_game->popState();
}

void SeparateResearchModeWarningState::btnKeepSharedClick(Action*)
{
	// Explicit opt-in: keep the host-authoritative Shared Research setting. The
	// player can still change it later from Multiplayer Settings.
	_game->popState();
}
}
