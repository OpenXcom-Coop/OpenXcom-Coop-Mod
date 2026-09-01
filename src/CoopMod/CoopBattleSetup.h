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

#include <vector>

namespace OpenXcom
{

class SavedBattleGame;

/**
 * R5-P1 (rewrite spike, SPIKE-RUNBOOK.md RB-D23): the ONE generation-time
 * pass that sets canonical per-unit factions and RB-D17 seat tags, replacing
 * the RB-D18 interim seatMap (a wire-only {"0":"player","1":"player"}
 * placeholder that never touched a BattleUnit). Called once by
 * CoopHandshake::offerBattle() (connectionTCP.cpp) right after vanilla
 * BattlescapeGenerator::run() has produced @a save - the same
 * generation-complete moment every offerBattle() call site already reaches
 * before it ships battle_offer. HOST-ONLY: a client never generates, so it
 * never calls this - it gets the real per-unit factions/seats over the wire
 * inside the streamed battle blob, and the real seat->faction store off the
 * battle_offer seatMap this pass produces (see connectionTCP.cpp). Body
 * lives in CoopState.cpp (existing .cpp, RB-D23 - no new .cpp in the spike).
 *
 * @a gamemode is connectionTCP::_coopGamemode (RB-D23's gamemode source):
 *
 *   0/1 (classic/SHARED) - every FACTION_PLAYER-original unit keeps
 *     FACTION_PLAYER; each one with a Soldier owner
 *     (BattleUnit::getGeoscapeSoldier()) is seat-tagged from that Soldier's
 *     OWN pre-generation Soldier::getCoop() ownership stamp (R4-P2's
 *     Cydonia/base-defense callers, and the SHARED ownership-sync sites in
 *     connectionTCP.cpp, already write it before generation runs - this
 *     pass only reads it back). Everything else - HWPs (no Soldier owner;
 *     the "craft owner rule" this packet's spec text mentions is not wired
 *     to any BattleUnit-reachable API in the spike, so HWPs fall back to
 *     unowned here, same as before this pass existed), civilians, and any
 *     real mission aliens - gets COOP_SEAT_NONE: nobody commands them.
 *
 *   2/3 (PvP) - the SAME generated battle (real X-COM soldiers +
 *     AlienDeployment-spawned aliens, exactly like SP - see pvp_fixture.py's
 *     "gamemode 2: host=XCOM, client=Alien" contract) is split by its
 *     EXISTING vanilla faction, never by soldier ownership: gamemode 2
 *     seats the FACTION_PLAYER group at seat 0 and the FACTION_HOSTILE group
 *     at seat 1; gamemode 3 inverts that (seat 0 hostile, seat 1 player).
 *     Whichever seat ends up commanding the FACTION_HOSTILE group has its
 *     units' AI modules cleared (BattleUnit::setAIModule(nullptr)) - they
 *     are human-commanded from here on, not the alien-turn AI. Civilians
 *     (FACTION_NEUTRAL) are never assigned a seat in any gamemode. Every
 *     unit this pass gives a real faction to gets it funneled through the
 *     new BattleUnit::setOriginalFaction() + the existing convertToFaction()
 *     - never a direct field write - so the "setOriginalFaction writes
 *     funneled through this ONE pass" half of RB-D23 holds even though gm2/3
 *     happens to reassert the SAME faction vanilla generation already gave
 *     the unit (PvP seat assignment here follows EXISTING faction, it never
 *     flips a real soldier's own side in the spike - only a future gm4
 *     swapper, deferred by RB-D16, would need convertToFaction() to actually
 *     change a value).
 *
 *   4 (PvE2) - DEFERRED (RB-D16): logs a warning and no-ops if ever called
 *     with gamemode 4. Callers must keep refusing gm4 at the handshake
 *     (connectionTCP.cpp's onOffer()) instead of reaching this function for
 *     it - this is a defensive fallback, not the refusal path itself.
 *
 * @a seats is the battle's active seat list (RB-D17 N-player guardrail - no
 * 2-seat assumption baked into the signature). The spike only ever calls
 * this with connectionTCP::seatCount()'s current {0..seatCount()-1} (2
 * seats: host=0, client=1, connectionTCP::localSeat()'s own transport
 * convention). Used two ways: (a) this pass calls
 * coopBattleAuthority().setSeatFaction() for every seat in @a seats,
 * replacing the interim map as the seat->faction store's populator; (b) in
 * the classic/SHARED branch, a Soldier::getCoop() value that is not present
 * in @a seats (stale/out-of-roster ownership) falls back to COOP_SEAT_NONE
 * rather than mis-seating a unit to a seat nobody occupies this battle.
 *
 * `Soldier::_cooptype` re-skin (donor BriefingState.cpp's alien-looking-unit
 * swap for a squad-vs-squad PvP hostile side) is NOT implemented here - r5
 * T3+ scope (SPIKE-RUNBOOK.md R5-P1 packet text). This pass only tags seat
 * + faction; it never touches BattleUnit::getUnitRules()/setUnitRulesCoop().
 */
void assignSeatsAndFactions(SavedBattleGame* save, int gamemode, const std::vector<int>& seats);

} // namespace OpenXcom
