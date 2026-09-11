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

class SavedBattleGame;

/**
 * W1-P13a (rewrite wave 1, WAVE1-RUNBOOK.md SPEC 9): the ENGINE half of
 * `side_transition` + `side_begin` - both machines changing sides together
 * at a turn boundary.
 *
 * `side_transition` is a RESTATE (not a delta) of every unit/tile/item the
 * frozen schema names, built by walking the state AFTER
 * SavedBattleGame::endTurn() has already run (no pre-snapshot needed).
 * `side_begin` follows immediately, carrying no stats/tile data - it exists
 * only to tell every machine which seats are active for the new side.
 *
 * ALL LOGIC LIVES IN src/CoopMod (body: connectionTCP.cpp, next to the other
 * R2/R3-P1 scaffolding). The vanilla files get exactly FOUR thin guarded
 * calls: BattlescapeGame::endTurn() (this header's coopEmitSideTransition()),
 * BattlescapeGame::think()'s non-player branch
 * (BattleAuthority.h's coopSuppressNonPlayerThink()), and two calls inside
 * NextTurnState.cpp (this header's coopSuppressBugHuntCheck() and
 * coopSuppressNextTurnLifecycle()) - see those declarations' own comments.
 */

/// HOST-ONLY, called from BattlescapeGame::endTurn() at the point control
/// regains it after SavedBattleGame::endTurn() has fully returned (including
/// past any terrain-explosion detour that function can take - see the call
/// site's own comment for why that is the one point reached exactly once per
/// completed side transition). Self-guarded (isCoopBattle() &&
/// coopBattleAuthority().hostSim) - a no-op everywhere else, so SP and every
/// non-coop battle are byte-identical.
///
/// Builds and emits ONE `side_transition` restate (perUnit/perTile/perItem,
/// newTurn, newSide, the nine-bucket boundary `h`), then ONE `side_begin`
/// (side, turn, activeSeats) once that has gone out. Flushes the coop
/// hostile-vision bitmap (CoopFog::authorHostilePass) BEFORE computing `h`,
/// so `h.revealHostile` cannot race CoopEmit::sendEv()'s own authoring pass
/// for the same envelope (WV-D39 / SS2.W4).
void coopEmitSideTransition(SavedBattleGame* save);

/// W1-P13a (REV E.1 D-5): true iff NextTurnState's ctor must NOT run
/// vanilla's checkBugHuntMode() on this machine. `_bughuntMode` is
/// serialized and is NOT on saveBlobExcludedTopKey, so it rides the
/// `saveBlob` bucket inside this packet's own boundary sweep - bughunt must
/// therefore stay strictly host-authoritative. Self-guarded: false (vanilla
/// runs normally) outside an active coop battle, and on the host itself;
/// true only for a client inside an active coop battle.
bool coopSuppressBugHuntCheck(const SavedBattleGame* save);

/// W1-P13a (REV E.1 S-3 / WV-D51): true iff NextTurnState::close() must skip
/// vanilla's post-dismissal battle-lifecycle work (the tally, the
/// areAllEnemiesNeutralized() mind-control conversion, finishBattle(), the
/// autosave) and perform ONLY the presentation-layer dismissal
/// (cleanupDeleted() + popState(), both still run unconditionally by the
/// caller before this is even checked). A coop CLIENT's own NextTurnState
/// push carries no local authority to end the battle, convert units, or
/// autosave - those stay host-authoritative until a later packet wires them
/// across the wire. Self-guarded: false (vanilla runs normally) outside an
/// active coop battle, and on the host itself; true only for a client inside
/// an active coop battle.
bool coopSuppressNextTurnLifecycle(const SavedBattleGame* save);

}
