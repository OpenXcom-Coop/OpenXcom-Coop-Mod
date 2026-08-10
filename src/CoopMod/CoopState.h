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
#include "../Menu/OptionsBaseState.h"
#include "../Engine/Screen.h"
#include "../Geoscape/Globe.h"

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class GeoscapeState;

/**
 * Named dialog codes for CoopState. CoopState is a multi-purpose wait/prompt
 * dialog selected by a raw int passed to its constructor. Explicit values so
 * nothing renumbers (the ints appear in logs and harness tests).
 *
 * Only the codes that participate in the campaign-wait lifecycle (and the two
 * save/load wait dialogs) are named here so far; the remaining placeholder
 * codes scattered through the coop states are still raw literals pending a
 * future documentation pass (out of scope for PRD-01).
 */
enum CoopDialogCode {
	COOP_DLG_CLIENT_LOAD_WAIT = 52, // client "loading" wait
	COOP_DLG_HOST_SAVE_WAIT   = 54, // host "saving" wait
	COOP_DLG_WAIT_BASES       = 60, // host waits for every client to place a base
	// Host waits on a peer to be ready: either loading a streamed world or gone
	// and expected back. These used to be two codes (62 resume-ack, 64 freeze)
	// that rendered the same dialog and needed a suppression rule to stop them
	// stacking two RESUME buttons. One code, and the wording follows the peer's
	// actual presence (CoopState::waitingTitle) instead of the push site's guess
	// - so a client that drops mid-wait re-words the dialog it is already in.
	COOP_DLG_WAIT_PLAYERS     = 62,
	COOP_DLG_CLIENT_HOLD      = 65, // client placed base, holds until host resumes
	COOP_DLG_CLIENT_RESUME_HOLD = 68, // rejoined client holds until host resumes
	COOP_DLG_SHARED_FAIL       = 556, // PRD-J10: the host rejected a SHARED command
	COOP_DLG_CONFIRM_EQUIP_CRAFT = 557, // lock the Custom Battle craft before equipment
	COOP_DLG_VOTE_COOLDOWN = 558, // a seat tried to start another vote too soon
};

/**
 * Options window shown for loading/saving/quitting the game.
 * Not to be confused with the Game Options window
 * for changing game settings during runtime.
 */
class CoopState : public State
{
  private:
	OptionsOrigin _origin = OPT_GEOSCAPE;
	Window *_window;
	Text *_txtTitle;
	TextButton *_btnMessage, *_btnBack, *_btnYes;
	// issues #79/#81: the host's escape hatch out of a campaign wait that a
	// missing peer may never end. Only ever built/shown for isHostWaitDialog().
	TextButton *_btnSaveQuit, *_btnAbandon;
	int global_state = 0;
	int state_counter = 0;
	int _value = 0; // optional dialog-specific numeric value
	// PRD-11 C13: retry bookkeeping for the client load-wait dialog (52). When
	// the host replies "busy", wait ~2s (_loadWaitTicks at the 500ms gate) then
	// re-send request_load_progress, up to a bounded number of retries.
	int _loadRetries = 0;
	int _loadWaitTicks = 0;
	// issue #91: the client's resume hold (68) has no button and no timeout, so a
	// release that never arrives is a permanent freeze. Counts consecutive think
	// gates spent held WHILE the host is demonstrably back on its geoscape (see
	// CoopState::think); _holdGaveUp latches the disconnect offer so it is built
	// once.
	int _holdWatchTicks = 0;
	bool _holdGaveUp = false;
  public:
	/// Creates the Pause state.
	CoopState(int state, int value = 0);
	/// Cleans up the Pause state.
	~CoopState();
	void loadCoop(Action *);
	void previous(Action *);
	void btnYesClick(Action *);
	/// issue #81: SAVE & QUIT - write a save, then leave for the main menu.
	void btnSaveQuitClick(Action *);
	/// issue #81: ABANDON GAME - leave for the main menu, writing nothing.
	void btnAbandonClick(Action *);
	void loadWorld();
	/// Issues #79/#81: place a host-wait dialog's title + button row, measured
	/// from the window. `withAction` puts RESUME/BEGIN in the row instead of
	/// the escape hatch.
	void layoutWaitRows(bool withAction);
	/// Issues #79/#81: flip a host-wait dialog between WAITING (escape hatch)
	/// and READY (RESUME/BEGIN). The two are mutually exclusive.
	void setWaitAction(bool ready);
	/// What this host-wait dialog is waiting on, worded from the peer's CURRENT
	/// presence rather than from whatever the push site assumed.
	std::string waitingTitle() const;
	/// The same dialog's wording once the wait is over.
	std::string readyTitle() const;
	/// Is the thing this host-wait dialog waits for satisfied right now?
	bool waitSatisfied() const;
	void setGlobe(Globe *globe);
	void setBaseName(std::string name);
	/// Which dialog this is (see the state-code blocks in the constructor).
	int getStateCode() const { return global_state; }
	/// Introspection for the test harness: the current title / back-button text
	/// and whether the back button is visible.
	std::string getTitleText() const;
	std::string getBackText() const;
	bool isBackVisible() const;
	int getWindowHeight() const;
	/// Same introspection for the host's SAVE & QUIT / ABANDON GAME buttons.
	std::string getSaveQuitText() const;
	bool isSaveQuitVisible() const;
	std::string getAbandonText() const;
	bool isAbandonVisible() const;
	/// True for the HOST-side campaign waits that block on a peer who may never
	/// come back (60/62/64). Issues #79/#81: these - and only these - carry the
	/// SAVE & QUIT / ABANDON GAME escape hatch, so the host is never trapped.
	static bool isHostWaitDialog(int code)
	{
		return code == COOP_DLG_WAIT_BASES
			|| code == COOP_DLG_WAIT_PLAYERS;
	}
	/// True for the campaign-wait family (60/62/64/65/67): dialogs that manage
	/// their own lifetime and must never be popped by save/load-progress handlers.
	bool isCampaignWaitDialog() const
	{
		return global_state == COOP_DLG_WAIT_BASES
			|| global_state == COOP_DLG_WAIT_PLAYERS
			|| global_state == COOP_DLG_CLIENT_HOLD
			|| global_state == COOP_DLG_CLIENT_RESUME_HOLD;
	}
	/// Runs the timers and handles popups.
	void think() override;
};

/**
 * Click-to-dismiss notice raised once a battle desync diagnostic bundle has been
 * written (SharedEcon::captureDesyncReport). Its own class rather than a CoopState
 * code or an InfoboxOKState because:
 *  - it is nearly always raised OVER a live battle, where CoopState's geoscape
 *    window is the documented dialog/dismiss trap;
 *  - InfoboxOKState's constructor REPLICATES itself to the peer when the local
 *    machine is the host, and each machine's report names its own local path -
 *    the peer must never be shown this one;
 *  - it has to hold a full filesystem path plus a "where to send it" sentence,
 *    which does not fit InfoboxOKState's 255x61 big-font title.
 * Palette handling mirrors GiftNoticeState: adopt the screen underneath, and in
 * battle use the co-op lobby's geoscape/saveMenus combination under the battle
 * palette. NOTHING is captured here - the bundle is already on disk by the time
 * this is pushed, so a dialog the player leaves sitting cannot spoil it.
 */
class CoopDesyncNoticeState : public State
{
  private:
	Window *_window;
	Text *_txtHeadline;
	Text *_txtMessage;
	TextButton *_btnOk;
	TextButton *_btnOpenFolder;
	TextButton *_btnReport;
	std::string _headline;
	std::string _message;
	std::string _zipPath;     ///< the diagnostic bundle zip
	std::string _openTarget;  ///< the folder OPEN FOLDER opens (the reports dir)
	std::string _reportUrl;   ///< the prefilled GitHub new-issue URL
	void buildLayout();
  public:
	/// PRD-I4: message + attribution headline + one-click UX (open folder / prefilled
	/// GitHub issue). No auto-upload; the buttons only shell out to the OS helper.
	CoopDesyncNoticeState(const std::string &message, const std::string &headline,
						  const std::string &zipPath, const std::string &reportUrl);
	/// Harness introspection: what this notice says / would open.
	std::string getMessageText() const;
	std::string getHeadlineText() const { return _headline; }
	std::string getReportUrl() const { return _reportUrl; }
	std::string getOpenFolderTarget() const { return _openTarget; }
	std::string getZipPath() const { return _zipPath; }
	void btnOkClick(Action *);
	void btnOpenFolderClick(Action *);
	void btnReportClick(Action *);
	/// Test hook: the values the LAST-raised notice would open, kept after the modal
	/// is dismissed so a harness poll made later can still read them.
	static std::string s_lastHeadline;
	static std::string s_lastMessage;
	static std::string s_lastReportUrl;
	static std::string s_lastOpenTarget;
	static std::string s_lastZipPath;
	static int s_raiseCount;
};

}
