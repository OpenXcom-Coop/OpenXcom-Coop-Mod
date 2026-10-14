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

namespace OpenXcom
{

class BattlescapeState;
class SavedBattleGame;

/**
 * D247-U (owner D247 (a), OH1 (a); docs rewrite/prompts/d247u_hotseat_battle.md): the battle half of
 * the local HOTSEAT mode the NEW BATTLE screen arms (connectionTCP::_isHotseatActive, issue #136).
 * Player 1 commands X-COM on vanilla's player side; player 2 commands the aliens on vanilla's alien
 * side. One battle round is one vanilla round (X-COM, aliens, civilians): the turn counter, time units,
 * wounds, fire and reinforcements run as in a normal battle.
 *
 * MECHANISM (QD247-2, QD247-7): for player 2's turn FACTION_PLAYER and FACTION_HOSTILE swap on every
 * unit (convertToFaction() only - original factions stay, i.e. vanilla's mind-control state) and the
 * active side reads FACTION_PLAYER (SavedBattleGame::coopSetSide()), so every vanilla player rule
 * (selection, sight, the map, the HUD, END TURN) serves player 2. The swap is made when the aliens'
 * turn screen closes (BattlescapeState::init()) and undone at the top of BattlescapeGame::endTurn()
 * when player 2 ends the turn, so no side start ever runs while swapped (BattleUnit::prepareNewTurn()
 * reverts a swapped faction).
 *
 * MAPS (QD247-3): one stash holds the explored map of the player who is not at the keyboard (the vanilla
 * per-tile discovered bits, CoopFog.h's 3-bit byte); each hand-over swaps it with the live bits. Player
 * 2's first turn starts from an unexplored map, as main's does.
 *
 * Local only: no wire, no hash. Every function is a no-op unless coopHotseatBattle(), so single player
 * without the toggle and every co-op battle are byte-identical.
 */

/// True while a hotseat battle may run: the NEW BATTLE toggle is armed and this machine is in no co-op
/// session (connectionTCP::getCoopStatic() false; QD247-5).
bool coopHotseatBattle();

/// True during player 2's turn (factions swapped, the side reading FACTION_PLAYER).
bool coopHotseatAlienTurn();

/// BattlescapeState's constructor: a battle (or a mission stage) starts on player 1's turn, no stash.
void coopHotseatOnBattleStart(SavedBattleGame* s);

/// BattlescapeState::init()'s first statement: once the aliens' turn screen has closed (side
/// FACTION_HOSTILE right after player 1's turn), hand the battle to player 2.
void coopHotseatOnInit(BattlescapeState* bs, SavedBattleGame* s);

/// BattlescapeGame::endTurn()'s first statement: player 2 ended the turn - hand the battle back (the
/// side reads FACTION_HOSTILE again) before vanilla's end-of-side work runs.
void coopHotseatOnEndTurn(SavedBattleGame* s);

/// BattlescapeState::finishBattle()'s first statement: a battle that ends on player 2's turn (an abort)
/// gets its real factions and X-COM's explored map back before the debriefing reads them.
void coopHotseatOnFinishBattle(SavedBattleGame* s);

/// DebriefingState's constructor: hotseat is scoped to one skirmish (main DebriefingState :300-:314) -
/// clear the state and disarm the toggle.
void coopHotseatOnDebriefing();

/// Map::hiddenMovementShown(): true = force the HIDDEN MOVEMENT screen. In a hotseat battle every
/// non-player side (the end of player 2's turn, the civilians' turn) is hidden from both players.
bool coopHotseatHidesMap(const SavedBattleGame* s);

} // namespace OpenXcom
