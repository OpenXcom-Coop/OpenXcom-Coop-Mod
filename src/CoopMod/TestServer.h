#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
 * Copyright 2023-2026 XComCoopTeam (https://www.moddb.com/mods/openxcom-coop-mod)
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
#include <atomic>
#include <deque>
#include <mutex>
#include <string>
#include <thread>

#include <json/json.h>

namespace OpenXcom
{

class Game;

/**
 * Automation/test command server. Only active when the OXC_TEST_PORT
 * environment variable is set: listens on 127.0.0.1:<port> for one client
 * speaking newline-delimited JSON commands, and executes them on the main
 * thread via pump() (called once per frame from Game::run). Lets an external
 * driver load saves, host/join coop sessions, inspect soldiers/coop state and
 * trigger soldier transfers without a human at the keyboard.
 */
class TestServer
{
public:
	static TestServer& instance();

	// Reads OXC_TEST_PORT; if set, starts the listener thread. Safe to call
	// more than once. Called from Game::run() startup.
	void startFromEnvironment(Game* game);
	// Executes queued commands on the main thread. Called once per frame.
	void pump();
	// Stops the listener thread (called from shutdown).
	void stop();

private:
	TestServer() = default;
	void ioThread(int port);
	std::string execute(const std::string& line);
	/// TEST-ONLY `pump_hold` (see its comment in TestServer.cpp). True = @a line was that command and @a resp holds
	/// its final reply. Lives beside pump(), not in execute(), because it waits on the inbox pump() drains.
	bool pumpHold(const std::string& line, std::string& resp);
	/// PRD-J10 hooks. execute()'s command chain is at MSVC's 128-block nesting
	/// limit (C1061), so newer commands get their own dispatcher; execute() tries
	/// this one first. True = @a cmd was handled here.
	bool executeShared10(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// Second sub-dispatcher: after an upstream rebase re-stacked commands onto the
	/// chain it tipped C1061 again, so the back half of execute()'s chain lives here.
	/// execute() tries this after executeShared10. True = @a cmd was handled here.
	bool executeShared11(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	bool executeBaseScreens(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// Third sub-dispatcher: battlescape item/fire introspection + drivers (issue #74).
	/// execute() tries this FIRST, so it never grows execute()'s own if/else chain.
	bool executeBattle12(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// Fourth sub-dispatcher: battle-lane introspection
	/// (event_log/event_state/hash_now/corrupt_bucket/corrupt_next_blob/
	/// battle_intent/inject_ev), plus the
	/// deterministic placement test commands battle_teleport_unit/
	/// battle_teleport_all (TEST-ONLY: applied to each machine independently
	/// by the harness with identical absolute arguments; emit nothing; never
	/// call from product code). Same C1061-avoidance reason as the three
	/// dispatchers above.
	bool executeIntrospect13(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// Join-check hooks (server browser rows, the incompatible-mods screen, the
	/// reported build version and mod list). executeIntrospect13 tries it first.
	bool executeJoinChecks14(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// PvP side and one-world layout probes (coop_sides, pvp_one_world). executeJoinChecks14 tries it first.
	bool executeSides15(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// The alien player's globe probes (globe_view, alien_view, xcom_base_found, place_craft, xcom_detect_ufo).
	bool executeAlienGlobe16(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// The alien player's information screens probe (alien_screens). executeSides15 tries it first.
	bool executeAlienScreens17(const std::string& cmd, const Json::Value& req, Json::Value& resp);
	/// PvP one-world probes (pvp_funds_shown, send_peer_message, pvp_bases_found). executeSides15 tries it first.
	bool executePvpWorld16(const std::string& cmd, const Json::Value& req, Json::Value& resp);

	Game* _game = nullptr;
	std::thread _thread;
	std::atomic<bool> _running{false};
	std::mutex _mutex;
	std::deque<std::string> _inbox;
	std::deque<std::string> _outbox;
};

}
