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
#include <string>
#include <json/json.h>

namespace OpenXcom
{
class Game;

/**
 * W2-P9 (spec rewrite/prompts/w2p9_synced_options.md, AMENDMENT P9-1 PR-1..PR-7, PR-13; owner D134, D160 a, D161 a):
 * one set of battle rules per co-op session. The host's globals are the session table; every machine writes the
 * shared value into its own in-memory option. Declarations only; bodies in connectionTCP.cpp. Main thread only.
 */
namespace CoopSyncedOptions
{
/// PR-1: a row; type/pointer from Options::getOptionInfo() by id; step/min/max = vanilla's Advanced-screen rule.
struct Row { const char *id; int step; int min; int max; };
/// PR-1: THE ONLY LIST - 15 ids = 14 visible rows (11 OXC + 3 OXCE) + the hidden unload option. W2-P10 appends.
static const Row TABLE[] = {
	{ "battleInstantGrenade", 1, 0, 1 },
	{ "battleExplosionHeight", 1, 0, 3 },
	{ "oxceEnableOffCentreShooting", 1, 0, 1 },
	{ "oxceUniformShootingSpread", 1, 0, 1 },
	{ "allowPsiStrengthImprovement", 1, 0, 1 },
	{ "allowPsionicCapture", 1, 0, 1 },
	{ "weaponSelfDestruction", 1, 0, 1 },
	{ "alienBleeding", 1, 0, 1 },
	{ "sneakyAI", 1, 0, 1 },
	{ "battleAutoEnd", 1, 0, 1 },
	{ "disableAutoEquip", 1, 0, 1 },
	{ "includePrimeStateInSavedLayout", 1, 0, 1 },
	{ "battleUFOExtenderAccuracy", 1, 0, 1 },
	{ "oxceReactionFireThreshold", 5, 0, 100 },
	{ "oxceInventoryUnloadFixedWeapons", 1, 0, 1 },
};
static const int TABLE_SIZE = (int)(sizeof(TABLE) / sizeof(TABLE[0]));

/// PR-3: true while the layer holds this machine's own values (session role != None).
bool active();
/// PR-3: the main-thread activation edge; the FIRST statement of connectionTCP::updateCoopTask(). Binds @a game
/// (submit, the client apply funnel and the chat line need it).
void tick(Game *game);
/// PR-3: activates now when the session role wants it (every submit / apply path calls it first).
void ensureActive();
/// PR-3: writes the own values back and drops them (CoopSession::resetSession()).
void deactivate();
/// PR-5: a change request (the Advanced-screen divert and the harness lever); false when inactive.
bool submit(const std::string &id, int value);
/// PR-4: RAII guard, the first statement of Options::save / load / resetDefault; inert unless active().
struct FileGuard
{
	enum Kind { SAVE, LOAD, RESET };
	explicit FileGuard(Kind kind);
	~FileGuard();
	Kind _kind;
	bool _armed;
	int _stash[TABLE_SIZE];
};
/// PR-13: the test-only apply hold (lever synced_apply_hold), read by the host latch (PR-6).
void setHoldArmed(bool on);
bool holdArmed();
/// The 15 current globals {id: bool|int} (the probe, the join table, battle_offer.hostRules).
Json::Value currentValues();
/// PR-13: the layer's own fields of the synced_options_state probe (active, version, values, own, queue, ...).
void stateView(Json::Value &out);
}

/// PR-6: the host's between-actions apply latch, beside the SPEC 16 pause latch in updateCoopTask().
void coopSyncedOptionsPump(Game *game, bool quiescent);
/// PR-7: the client apply funnel ("join" table, "offer" hostRules, "set" one id; @a player = a set's requester, for
/// its chat line).
void coopSyncedApplyFromHost(const Json::Value &values, int version, const char *source,
	const std::string &player = std::string());
}
